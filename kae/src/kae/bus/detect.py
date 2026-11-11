# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bus detector for the bus-campaign census (deterministic, netlist + placement only).

A bus = nets meant to be routed as one object. Lines are nets joined through series two-pin
parts (A-R-B is one line). Evidence, combined:
  * part pair: >= 4 lines between the same two terminal parts (ICs, modules, connectors, big unknowns)
    whose pins are neighbours at both ends; a part-pair group is split by name stem;
  * names: index runs (D[0..7], DQ*, A0..A15, PA0..PA7), any sheet;
  * net classes: a declared class (not Default, not power) of >= 3 lines between the same two parts;
  * diff pairs (kae.circuit.roles._pairs) and groups of pairs sharing their ends (lanes);
  * matrix lines (nets with >= 4 switch/LED/diode pads);
  * taut strings: leftover lines whose straight-line strings run together (KRT detect_buses
    idea: togetherness within 1.5 mm, average link >= 0.55).
Output: list of dicts, one per bus.

Everything in this module reads only what a new, never-routed board has (netlist, net names and classes, pads and
their positions, footprints and part data). It never reads tracks or vias; kae/tests/test_bus.py checks that a board with
copper and the same board with its copper removed give the same buses.
"""
from __future__ import annotations
import math
import re
from collections import defaultdict, Counter
from dataclasses import dataclass

from kae.circuit.netlist import Netlist
from kae.circuit import roles as R

MIN_LINES = 4          # unnamed part-pair group
MIN_NAMED = 3          # index-named group sharing its two ends
MAX_LINE_PADS = 8      # a data line has at most this many copper pads (fly-by to 6 + 2 is the ceiling we keep)
MATRIX_PADS = 4
TERM_KINDS = ('ic', 'module', 'connector', 'unknown')
SERIES_KINDS = ('resistor', 'ferrite', 'inductor', 'capacitor', 'resistor_array')

AUTO = re.compile(r'^(N\$\d+|NET\$?\d+|NET[A-Z]{1,5}\d+_\d+|\$\$|NET_?[A-Z]*\d+_\d+|UNNAMED|UNCONNECTED|P\$\d+)')
INDEX = re.compile(r'^(?P<stem>.*?)(?P<open>[\[<(]?)(?P<idx>\d{1,3})(?P<close>[\]>)]?)(?P<suf>[_A-Z+\-#]{0,3})$')
RARR = re.compile(r'^(RN|RP|RA|R)\d+')
RARR_V = re.compile(r'\b\d+(\.\d+)?[KRM]?\d*\b|R[._]?ARRAY|CAT1[0-9]|EXB|CAY|YC1|RES', re.I)
FPGA = re.compile(r'XC[3-9][A-Z]{1,3}\d|XC7|ZYNQ|ARTIX|KINTEX|SPARTAN|VIRTEX|ICE40|ICE5LP|ECP5|LFE[35]|LCMXO|MACHXO|GW[12]A|GW5|CYCLONE|EP[2-4][A-Z]\d|10M[0-9]{2}|MAX10|5C[EGS][A-Z]|EFM2|TRION|FPGA|CPLD|XC[29]5', re.I)
DRAM = re.compile(r'(^|[^A-Z0-9])(LP)?DDR[2-5]?\b|SDRAM|^(MT4[0-9][A-Z]|MT5[0-9]|MT6[0-9][A-Z]|K4[ABHSTD][A-Z0-9]{3}|H5[A-Z0-9]{4}|IS4[2-7][A-Z]|AS4C|W632|W9[4-9]\w+|NT5|HYB\w|S27K\w+)|HYPERRAM|PSRAM|APS\d{4}', re.I)
SRAM = re.compile(r'\bSRAM|^(CY7C|IS6[0-9]|IDT71|AS6C|MT45W|HM62|LY6[0-9])|^62[0-9]{3,4}[A-Z]?\b', re.I)
NOR = re.compile(r'^(AT2[89]|SST39|S29|MX29|W29|MT29|K9F|27C[0-9]|28F|27SF|29F|SST27)|FLASH|EPROM', re.I)
BUFFER = re.compile(r'74[A-Z]{0,6}(24[0-9]|16[0-9]{2,3}|541|573|574|595|37[34]|138|4245|4T245|245)|SN74|TXB|TXS|LVC8T|BUFFER|TRANSCEIVER|LEVEL.SHIFT', re.I)
LCD_N = re.compile(r'LCD|TFT|RGB|^R[0-9]$|^G[0-9]$|^B[0-9]$|HSYNC|VSYNC|DOTCLK|DISP|^DB[0-9]|^D[0-9]+_?LCD|PIXEL|PCLK|DE$', re.I)
PORT_N = re.compile(r'^(P[A-Z]\d+|P\d+[_.]\d+|GPIO\d*|IO\d+|PIO\d*|D\d+|A\d+|PORT[A-Z]?\d*)$', re.I)


def _natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', str(s))]


def parse_name(short):
    """(stem, index, suffix) of a net name ending in an index, else None."""
    if not short or AUTO.match(short):
        return None
    m = INDEX.match(short)
    if not m:
        return None
    stem = m.group('stem').rstrip('_.-[(<')
    if not stem or len(stem) > 24:
        return None
    return stem, int(m.group('idx')), m.group('suf') or ''


def _pitch(pts):
    if len(pts) < 2:
        return 0.0
    nn = []
    for i, a in enumerate(pts):
        d = min((math.dist(a, b) for j, b in enumerate(pts) if j != i), default=math.inf)
        if d > 1e-3:
            nn.append(d)
    nn.sort()
    return nn[len(nn) // 2] if nn else 0.0


class Line:
    __slots__ = ('nets', 'terms', 'series', 'npads', 'name', 'key', 'iface', 'pair', 'auto', 'mpads', 'id', 'pads_xy', 'nc')

    def __init__(self):
        self.nets, self.terms, self.series = [], {}, []
        self.npads = 0
        self.name, self.key, self.iface, self.pair = '', None, None, None
        self.auto = True
        self.mpads = 0
        self.id = -1
        self.pads_xy = []
        self.nc = ''


def build(board):
    nl = Netlist.from_board(board)
    roles = R.infer_roles(nl)
    fps = board.footprints.values() if isinstance(board.footprints, dict) else board.footprints
    part = {}
    for fp in fps:
        pads = [p for p in fp.pads if p.kind != 'np_thru_hole']
        pr = roles.parts.get(fp.ref)
        k = pr.kind if pr else 'unknown'
        st = pr.subtype if pr else None
        npad = sum(1 for p in pads if p.net)
        if k in ('unknown', 'mounting_hole', 'mechanical') and npad >= 8 and re.match(r'^(J|P|CON|CN|X|JP|SV|PL|DB)\d', fp.ref or ''):
            k = 'connector'
        if k == 'unknown' and RARR.search(fp.ref or '') and npad in (4, 6, 8, 10, 16) and RARR_V.search(f'{fp.value} {fp.lib_id}'):
            k = 'resistor_array'
        part[fp.ref] = dict(fp=fp, kind=k, subtype=st, pads=pads, role=pr.role if pr else None)
    return nl, roles, part


def signal_nets(nl, roles):
    gs = set(roles.grounds)
    out = {}
    for net, nv in nl.nets.items():
        if not net or net in gs or net in roles.rails or nv.nn.unconnected:
            continue
        if len({(p.ref, p.number) for p in nv.pins}) < 2:
            continue
        out[net] = nv
    return out


def lines_of(board, nl, roles, part, sig):
    """Lines: nets contracted through series 2-pin parts."""
    padpos = {}
    for ref, pi in part.items():
        for p in pi['pads']:
            if p.net:
                padpos.setdefault((ref, p.number), []).append(p)
    # net pad lists
    net_pads = defaultdict(list)
    for ref, pi in part.items():
        for p in pi['pads']:
            if p.net and p.net in sig:
                net_pads[p.net].append((ref, p))
    parent = {n: n for n in sig}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    series_of = defaultdict(list)
    for ref, pi in part.items():
        if pi['kind'] not in SERIES_KINDS:
            continue
        ps = [p for p in pi['pads'] if p.net]
        groups = []
        if pi['kind'] == 'resistor_array' and len(ps) >= 4:
            byn = {}
            for p in ps:
                byn.setdefault(p.number, p)
            try:
                nums = sorted(byn, key=lambda s: int(s))
            except ValueError:
                nums = sorted(byn)
            n = len(nums)
            for i in range(n // 2):
                groups.append([byn[nums[i]], byn[nums[n - 1 - i]]])
        elif len(ps) == 2:
            groups.append(ps)
        for g in groups:
            a, b = g[0].net, g[1].net
            if not a or not b or a == b or a not in sig or b not in sig:
                continue
            # a series part must not bridge two heavily-loaded nets
            if len(net_pads[a]) > MAX_LINE_PADS or len(net_pads[b]) > MAX_LINE_PADS:
                continue
            # capacitors only in a pair path (AC coupling) or when each side is 2-pad: keep simple
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
            series_of[find(a)]  # touch
    # gather
    groups = defaultdict(list)
    for n in sig:
        groups[find(n)].append(n)
    lines = []
    for root, nets in sorted(groups.items()):
        ln = Line()
        ln.nets = sorted(nets)
        total_pads = 0
        terms = {}
        series = []
        for n in ln.nets:
            for ref, p in net_pads[n]:
                total_pads += 1
                pi = part[ref]
                if pi['kind'] in SERIES_KINDS:
                    # a pad of a series part counts as series if its opposite pad's net is in this line; else leaf
                    series.append(ref)
                    continue
                nsig = sum(1 for q in pi['pads'] if q.net and q.net in sig)
                if (pi['kind'] in TERM_KINDS and nsig >= 3) or nsig >= 8:
                    terms.setdefault(ref, []).append(p)
        ln.terms = terms
        ln.series = sorted(set(r for r in series if sum(1 for n in ln.nets for x, _p in net_pads[n] if x == r) >= 2))
        ln.npads = total_pads
        if len(ln.nets) == 1:
            nv = sig[ln.nets[0]]
            ln.name, ln.auto = nv.short, bool(nv.nn.auto or AUTO.match(nv.short or ''))
        else:
            names = [(sig[n].short, sig[n].nn.auto) for n in ln.nets]
            names.sort(key=lambda t: (t[1] or bool(AUTO.match(t[0] or '')), len(t[0])))
            ln.name, ln.auto = names[0][0], bool(names[0][1] or AUTO.match(names[0][0] or ''))
        ln.key = parse_name(ln.name) if not ln.auto else None
        ncs = sorted({sig[n].netclass or '' for n in ln.nets} - {'', 'Default'})
        ln.nc = ncs[0] if ncs else ''
        if ln.name:
            ln.iface = R.name_iface(ln.name)[0]
        lines.append(ln)
    for i, ln in enumerate(lines):
        ln.id = i
    return lines, net_pads


def line_pad(ln, ref, toward=None):
    ps = ln.terms[ref]
    if toward is None or len(ps) == 1:
        return ps[0]
    return min(ps, key=lambda p: math.dist((p.x, p.y), toward))


def term_centroid(lines, ref):
    pts = [(p.x, p.y) for ln in lines for p in ln.terms.get(ref, [])[:1]]
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def perm_metrics(pa, pb, eps):
    """pa, pb: lane end positions (same index = same lane). Returns dict with inversions, LIS, LDS, order."""
    n = len(pa)
    ca = (sum(p[0] for p in pa) / n, sum(p[1] for p in pa) / n)
    cb = (sum(p[0] for p in pb) / n, sum(p[1] for p in pb) / n)
    ux, uy = cb[0] - ca[0], cb[1] - ca[1]
    d = math.hypot(ux, uy) or 1.0
    ux, uy = ux / d, uy / d
    nx, ny = -uy, ux
    ta = [p[0] * nx + p[1] * ny for p in pa]
    tb = [p[0] * nx + p[1] * ny for p in pb]
    return perm_from(ta, tb, eps)


def perm_from(ta, tb, eps):
    n = len(ta)
    order = sorted(range(n), key=lambda i: (ta[i], tb[i]))
    A = [ta[i] for i in order]
    B = [tb[i] for i in order]
    inv = 0
    total = 0
    for i in range(n):
        for j in range(i + 1, n):
            if A[j] - A[i] <= eps:
                continue
            total += 1
            if B[i] - B[j] > eps:
                inv += 1
    # longest chain with no inversion (order-compatible): DP in A order
    lis = [1] * n
    lds = [1] * n
    for j in range(n):
        for i in range(j):
            if A[j] - A[i] > eps:
                if B[j] - B[i] > eps or abs(B[j] - B[i]) <= eps:
                    if lis[i] + 1 > lis[j]:
                        lis[j] = lis[i] + 1
                if B[i] - B[j] > eps:
                    if lds[i] + 1 > lds[j]:
                        lds[j] = lds[i] + 1
            else:  # same A position (column): counts as compatible with itself
                if abs(B[j] - B[i]) <= eps and lis[i] + 1 > lis[j]:
                    lis[j] = lis[i] + 1
    pi_b = sorted(range(n), key=lambda i: (tb[order[i]], i))
    rank = [0] * n
    for r, i in enumerate(pi_b):
        rank[i] = r
    return dict(inv=inv, pairs=total, lis=max(lis) if n else 0, lds=max(lds) if n else 0, order_a=order, order_b_rank=rank)


def cyc_lis(pa, pb, ca, cb):
    """Best cyclic LIS when both parts are treated as discs: order CCW at A, CW at B, best rotation."""
    n = len(pa)
    if n > 160 or n < 2:
        return None
    ang_a = [math.atan2(p[1] - ca[1], p[0] - ca[0]) for p in pa]
    ang_b = [-math.atan2(p[1] - cb[1], p[0] - cb[0]) for p in pb]
    oa = sorted(range(n), key=lambda i: ang_a[i])
    ob = sorted(range(n), key=lambda i: ang_b[i])
    posb = {x: i for i, x in enumerate(ob)}
    seq = [posb[i] for i in oa]
    best = 0
    import bisect
    for r in range(n):
        tails = []
        s = seq[r:] + seq[:r]
        # try both directions? rotation of b only; a fixed cut already covers mirrored half
        for x in s:
            k = bisect.bisect_left(tails, x)
            if k == len(tails):
                tails.append(x)
            else:
                tails[k] = x
        if len(tails) > best:
            best = len(tails)
        if best == n:
            break
    return best


def adj_groups(ls, pitch, a, b):
    """Components of lines whose pins are neighbours at both ends."""
    n = len(ls)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    pa = [(line_pad(l, a).x, line_pad(l, a).y) for l in ls]
    pb = [(line_pad(l, b).x, line_pad(l, b).y) for l in ls]
    ta = 2.6 * pitch[a] if pitch[a] else 5.0
    tb = 2.6 * pitch[b] if pitch[b] else 5.0
    for i in range(n):
        for j in range(i + 1, n):
            if math.dist(pa[i], pa[j]) <= ta and math.dist(pb[i], pb[j]) <= tb:
                parent[find(i)] = find(j)
    g = defaultdict(list)
    for i in range(n):
        g[find(i)].append(ls[i])
    return list(g.values())


def part_pitch(part, sig):
    out = {}
    for ref, pi in part.items():
        pts = [(p.x, p.y) for p in pi['pads'] if p.net and p.net in sig]
        out[ref] = _pitch(pts) if len(pts) >= 2 else 0.0
    return out


def pkg_of(pi):
    """Coarse end type."""
    if pi['kind'] == 'connector':
        return 'conn_' + (pi['subtype'] or 'other')
    txt = (pi['fp'].lib_id or '') + ' ' + (pi['fp'].value or '')
    t = txt.upper()
    pads = [p for p in pi['pads'] if p.net]
    for pat, name in (('BGA', 'bga'), ('WLCSP', 'bga'), ('LFBGA', 'bga'), ('TFBGA', 'bga'), ('QFN', 'qfn'), ('DFN', 'qfn'),
                      ('LGA', 'qfn'), ('TQFP', 'qfp'), ('LQFP', 'qfp'), ('QFP', 'qfp'), ('SSOP', 'so'), ('TSSOP', 'so'), ('SOIC', 'so'),
                      ('SOP', 'so'), ('TSOP', 'so'), ('DIP', 'dip'), ('SODIMM', 'sodimm'), ('DIMM', 'dimm')):
        if pat in t:
            return name
    if len(pads) >= 16:
        xs = sorted(round(p.x, 1) for p in pads)
        ys = sorted(round(p.y, 1) for p in pads)
        if len(set(xs)) > 5 and len(set(ys)) > 5 and all(p.kind == 'smd' for p in pads):
            return 'grid_or_perimeter'
    return pi['kind']


def classify_part(pi):
    """fpga | dram | sram | nor | buffer | mcu | ... from kae subtype + text."""
    fp = pi['fp']
    txt = ' '.join(str(x) for x in (fp.value, fp.fields.get('MPN', ''), fp.fields.get('Manufacturer Part Number', ''), fp.fields.get('Description', '')))
    st = pi['subtype'] or ''
    if st == 'fpga' or FPGA.search(txt):
        return 'fpga'
    tv = ' '.join(str(x) for x in (fp.value, fp.fields.get('MPN', ''), fp.fields.get('Manufacturer Part Number', '')))
    if st == 'mcu':
        return 'mcu'
    if DRAM.search(tv):
        return 'dram'
    if SRAM.search(tv):
        return 'sram'
    if NOR.search(tv):
        return 'flash'
    if BUFFER.search(tv):
        return 'buffer'
    if st in ('memory',):
        return 'memory'
    return st or pi['kind']


def refine_dram(part, lines):
    """A part with >= 8 DDR-named lines and at most 250 net pads is a DRAM even when its value says nothing
    (netlist evidence: names only; never copper)."""
    c = Counter()
    for l in lines:
        if l.iface == 'ddr' and re.search(r'DQ|DM|DQS|BA\d|^A\d|_A\d|ADDR|CKE|ODT', l.name or '', re.I):
            for r in l.terms:
                c[r] += 1
    for r, n in c.items():
        pi = part[r]
        if n >= 8 and pi.get('cls') not in ('fpga', 'mcu') and pi['kind'] in ('ic', 'unknown', 'module') and sum(1 for p in pi['pads'] if p.net) <= 250:
            pi['cls'] = 'dram'


def stem_family(ln):
    """A grouping stem key for a line: name stem with the sheet prefix."""
    if ln.key is None:
        return None
    return ln.key[0] + '|' + ln.key[2]


def detect(board, part, lines, pitch, sig, dpairs):
    """Returns list of bus dicts (lanes = Line objects, evidences)."""
    used = set()
    buses = []
    line_of = {}
    for ln in lines:
        for n in ln.nets:
            line_of[n] = ln
    # A. groups of diff pairs that share both end parts = lanes of pairs (exclude DDR and clocks)
    punits = defaultdict(list)
    for dp in dpairs:
        la, lb = line_of.get(dp.p), line_of.get(dp.n)
        if la is None or lb is None or la.id == lb.id:
            continue
        la.pair = lb.pair = dp
        common = sorted(set(la.terms) & set(lb.terms))
        if len(common) < 2 or dp.interface in ('ddr', 'clock', 'analog'):
            continue
        for i in range(len(common)):
            for j in range(i + 1, len(common)):
                punits[(common[i], common[j])].append((dp, la, lb))
    for (a, b), lst in sorted(punits.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        lst = [x for x in lst if x[1].id not in used and x[2].id not in used]
        if len(lst) >= 2:
            m = dict(lanes=[], ev=['pairs'], a=a, b=b, stem=None, pair_lanes=len(lst), ifaces=sorted({x[0].interface for x in lst}))
            for dp, la, lb in sorted(lst, key=lambda t: t[0].p):
                m['lanes'] += [la, lb]
                used.add(la.id); used.add(lb.id)
            buses.append(m)
    # B. DDR assembly: a DRAM part and its controller: bytes + addr/control group
    ddr_pairs = defaultdict(list)
    for ln in lines:
        if ln.id in used:
            continue
        for r in ln.terms:
            pass
    dram_refs = [r for r, pi in part.items() if pi.get('cls') == 'dram']
    for d in sorted(dram_refs):
        # controller = the other part sharing most lines with this DRAM
        cnt = Counter()
        for ln in lines:
            if ln.id in used or d not in ln.terms:
                continue
            for r in ln.terms:
                if r != d:
                    cnt[r] += 1
        if not cnt:
            continue
        ctrl, _n = max(sorted(cnt.items()), key=lambda kv: kv[1])
        ls = [l for l in lines if l.id not in used and d in l.terms and ctrl in l.terms]
        dq = defaultdict(list)
        other = []
        def sig_name(l):
            # the DRAM pin name when the net name says nothing
            p = line_pad(l, d)
            f = (p.pinfunction or '').upper()
            return f if re.match(r'^(LDQ|UDQ|DQ|DM|LDM|UDM|DQS|LDQS|UDQS)', f) else (l.name or '')
        for l in ls:
            s = sig_name(l)
            m_ = re.search(r'(?:^|[^A-Z])?(L|U)?DQ(\d+)$|(?:^|_)(L|U)?DQ[_\[]?(\d+)\]?$|DQ(\d+)$', s)
            md = re.search(r'(L|U)?DMI?\D*(\d*)$|(L|U)?DM_?(\d*)$', s)
            ms = re.search(r'(L|U)?DQS\D*(\d*)', s)
            if ms:
                g = ms.group(2)
                bidx = int(g) if g else ({'L': 0, 'U': 1}.get(ms.group(1), 0))
                dq[bidx].append(l)
            elif re.search(r'(^|[^A-Z])DQ[_\[]?\d', s):
                mm = re.search(r'DQ[_\[]?(\d+)', s)
                dq[int(mm.group(1)) // 8].append(l)
            elif re.search(r'(^|[^A-Z])(L|U)?DMI?\d*', s) and md:
                g = md.group(2)
                bidx = int(g) if g else ({'L': 0, 'U': 1}.get(md.group(1), 0))
                dq[bidx].append(l)
            else:
                other.append(l)
        if sum(len(v) for v in dq.values()) >= 6:
            for bidx, g in sorted(dq.items()):
                g = [l for l in g if l.id not in used]
                if len(g) >= 3:
                    for l in g:
                        used.add(l.id)
                    buses.append(dict(lanes=sorted(g, key=lambda l: _natural(l.name)), ev=['ddr_byte'], a=d, b=ctrl, stem=f'byte{bidx}'))
            ad = [l for l in other if l.id not in used]
            if len(ad) >= 4:
                for l in ad:
                    used.add(l.id)
                buses.append(dict(lanes=sorted(ad, key=lambda l: _natural(l.name)), ev=['ddr_addr'], a=d, b=ctrl, stem='addr'))
    # C. candidates: part pairs
    pairs = defaultdict(list)
    for ln in lines:
        if ln.npads > MAX_LINE_PADS:
            continue
        refs = sorted(ln.terms)
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                pairs[(refs[i], refs[j])].append(ln)
    order = sorted(pairs.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for (a, b), ls in order:
        ls = [l for l in ls if l.id not in used]
        if len(ls) < MIN_NAMED:
            continue
        # partition by name stem
        byk = defaultdict(list)
        rest = []
        for l in ls:
            k = stem_family(l)
            if k is not None:
                byk[k].append(l)
            else:
                rest.append(l)
        small = []
        for k, g in list(byk.items()):
            if len(g) < MIN_NAMED or len({l.key[1] for l in g}) < MIN_NAMED:
                small += g
                del byk[k]
        rest += small
        # named partitions become buses directly; merge unnamed rest later
        made = []
        for k, g in sorted(byk.items()):
            g = sorted(g, key=lambda l: (l.key[1], l.name))
            made.append(dict(lanes=g, ev=['names', 'partpair'], a=a, b=b, stem=k))
        # interface-merge: named partition absorbs rest lines of the same interface with pins adjacent
        # (QSPI/SD/DDR control pins share the iface family), else rest go to adjacency clustering
        rest_final = []
        for l in rest:
            placed = False
            if l.iface in ('qspi', 'emmc_sd', 'ddr', 'rgmii', 'video', 'spi', 'i2s'):
                for m in made:
                    if any(x.iface == l.iface for x in m['lanes']):
                        m['lanes'].append(l)
                        if 'iface_merge' not in m['ev']:
                            m['ev'].append('iface_merge')
                        placed = True
                        break
            if not placed:
                rest_final.append(l)
        rest = rest_final
        # iface-only groups among rest (e.g. SD_CMD, SD_CLK with SD_D0: handled above; QSPI with no index, RGMII)
        byi = defaultdict(list)
        rest2 = []
        for l in rest:
            if l.iface in ('qspi', 'emmc_sd', 'rgmii', 'ddr', 'spi', 'i2s'):
                byi[l.iface].append(l)
            else:
                rest2.append(l)
        for f, g in sorted(byi.items()):
            if len(g) >= 3:
                made.append(dict(lanes=sorted(g, key=lambda l: l.name), ev=['iface', 'partpair'], a=a, b=b, stem=f))
            else:
                rest2 += g
        # a declared net class (not Default, not a power class) between the same two parts
        bync = defaultdict(list)
        rest4 = []
        for l in rest2:
            if l.nc and not re.search(r'POWER|PWR|VCC|VDD|GND|SUPPLY|RAIL', l.nc, re.I):
                bync[l.nc].append(l)
            else:
                rest4.append(l)
        for nc, g in sorted(bync.items()):
            if len(g) >= MIN_NAMED:
                made.append(dict(lanes=sorted(g, key=lambda l: _natural(l.name)), ev=['netclass', 'partpair'], a=a, b=b, stem=nc))
            else:
                rest4 += g
        rest2 = rest4
        # same word prefix between the same two parts (TFT_CS, TFT_DC, TFT_MOSI; BUFFSPI_*); never power-ish words
        byp = defaultdict(list)
        rest3 = []
        for l in rest2:
            p = re.split(r'[_.\-]', l.name or '')[0] if ('_' in (l.name or '') or '-' in (l.name or '')) and not l.auto else ''
            if len(p) >= 2 and p not in ('NET', 'PIN', 'CH', 'SIG', 'A', 'D', 'B', 'SW', 'IN', 'OUT', 'EN', 'CON', 'CONN', 'J', 'U', 'P', 'NC'):
                byp[p].append(l)
            else:
                rest3.append(l)
        for p, g in sorted(byp.items()):
            if len(g) >= MIN_NAMED:
                made.append(dict(lanes=sorted(g, key=lambda l: _natural(l.name)), ev=['prefix', 'partpair'], a=a, b=b, stem=p))
            else:
                rest3 += g
        rest2 = rest3
        # adjacency clustering for the rest
        for g in adj_groups(rest2, pitch, a, b):
            if len(g) >= MIN_LINES:
                made.append(dict(lanes=sorted(g, key=lambda l: _natural(line_pad(l, a).number)), ev=['adj', 'partpair'], a=a, b=b, stem=None))
        for m in made:
            if len(m['lanes']) >= 2 and not any(l.id in used for l in m['lanes']):
                for l in m['lanes']:
                    used.add(l.id)
                buses.append(m)
    # names only: stem groups with no shared second part
    byk = defaultdict(list)
    for ln in lines:
        if ln.id in used or ln.key is None or ln.npads > MAX_LINE_PADS:
            continue
        byk[stem_family(ln)].append(ln)
    for k, g in sorted(byk.items(), key=lambda kv: kv[0] or ''):
        if len(g) < 4 or len({l.key[1] for l in g}) < 4:
            continue
        cov = Counter()
        for l in g:
            for r in l.terms:
                cov[r] += 1
        top = sorted(cov.items(), key=lambda kv: (-kv[1], kv[0]))
        if not top:
            continue
        a, ca = top[0]
        if ca < 0.75 * len(g):
            continue
        # partner parts
        partners = [r for r, c in top[1:] if c >= max(2, 0.4 * len(g))]
        if partners:
            b = partners[0]
            sub = [l for l in g if a in l.terms and b in l.terms]
            if len(sub) >= 4:
                for l in sub:
                    used.add(l.id)
                buses.append(dict(lanes=sorted(sub, key=lambda l: l.key[1]), ev=['names', 'cover'], a=a, b=b, stem=k))
    # matrix lines: >= MATRIX_PADS switch/LED/diode pads on one net
    mx = []
    for ln in lines:
        if ln.id in used:
            continue
        n = 0
        for net in ln.nets:
            for p in sig[net].pins:
                k = part[p.ref]['kind'] if p.ref in part else ''
                if k in ('switch', 'led', 'diode'):
                    n += 1
        ln.mpads = n
        if n >= MATRIX_PADS:
            mx.append(ln)
    if len(mx) >= 3:
        # one bus per controller hub (rows and columns each go to their part); stems split rows from columns
        byhub = defaultdict(list)
        for l in mx:
            if not l.terms:
                continue
            hub = max(sorted(l.terms), key=lambda r: sum(1 for q in part[r]['pads'] if q.net))
            k = re.sub(r'\d+$', '', l.key[0]) if l.key else ''
            byhub[(hub, k if l.key else '')].append(l)
        for (hub, k), g in sorted(byhub.items()):
            if len(g) >= 3:
                for l in g:
                    used.add(l.id)
                buses.append(dict(lanes=sorted(g, key=lambda l: _natural(l.name)), ev=['matrix'], a=hub, b=None, stem=k or 'matrix'))
    return buses, used


def taut_groups(lines, used, part, min_len=3.0, width=1.5, thresh=0.55):
    """KRT-style: straight strings between the two end pads, cluster by togetherness (average link)."""
    import numpy as np
    cand = []
    for ln in lines:
        if ln.id in used or len(ln.nets) > 1 or ln.npads > 4:
            continue
        ps = [p for r in ln.terms for p in ln.terms[r]] if len(ln.terms) >= 2 else None
        if ps is None:
            continue
        a, b = (ps[0].x, ps[0].y), (ps[-1].x, ps[-1].y)
        L = math.dist(a, b)
        if L < min_len:
            continue
        n = max(2, int(L / 0.5) + 1)
        xs = np.linspace(a[0], b[0], n)
        ys = np.linspace(a[1], b[1], n)
        cand.append((ln, np.stack([xs, ys], axis=1), L, a, b))
    if len(cand) < 4:
        return []
    if len(cand) > 400:
        cand = sorted(cand, key=lambda c: -c[2])[:400]
    m = len(cand)
    sim = np.zeros((m, m))
    for i in range(m):
        for j in range(i + 1, m):
            A, B = cand[i][1], cand[j][1]
            # quick bbox reject
            if A[:, 0].max() < B[:, 0].min() - width or B[:, 0].max() < A[:, 0].min() - width or \
               A[:, 1].max() < B[:, 1].min() - width or B[:, 1].max() < A[:, 1].min() - width:
                continue
            s, o = (A, B) if len(A) <= len(B) else (B, A)
            d = ((s[:, None, :] - o[None, :, :]) ** 2).sum(axis=2).min(axis=1)
            sim[i, j] = sim[j, i] = (d <= width * width).sum() / len(s)
    clus = [[i] for i in range(m)]
    while len(clus) > 1:
        best, bi, bj = -1.0, -1, -1
        for i in range(len(clus)):
            for j in range(i + 1, len(clus)):
                v = sim[np.ix_(clus[i], clus[j])].mean()
                if v > best:
                    best, bi, bj = v, i, j
        if best < thresh:
            break
        clus[bi] = clus[bi] + clus[bj]
        clus.pop(bj)
    out = []
    for c in clus:
        if len(c) >= 4:
            out.append([cand[i][0] for i in c])
    return out


def classify_kind(m, part):
    a, b = m['a'], m['b']
    ca, cb = part[a].get('cls') if a else None, part[b].get('cls') if b else None
    ka, kb = part[a]['kind'] if a else None, part[b]['kind'] if b else None
    sa, sb = part[a]['subtype'] if a else None, part[b]['subtype'] if b else None
    lanes = m['lanes']
    ifaces = Counter(l.iface for l in lanes if l.iface)
    names = ' '.join(l.name for l in lanes).upper()
    n = len(lanes)
    ev = m['ev']
    if 'matrix' in ev:
        return 'matrix_lines'
    if 'pairs' in ev:
        return 'serdes_lanes'
    if 'ddr_byte' in ev:
        return 'ddr_byte'
    if 'ddr_addr' in ev:
        return 'ddr_addr'
    mem = {ca, cb} & {'dram', 'sram', 'flash', 'memory'}
    if ifaces.get('qspi', 0) >= n * 0.6 or (('memory' in (ca, cb) or 'flash' in (ca, cb)) and ifaces.get('spi') and n <= 7) or \
       ('SPI' in names and n <= 8 and ('flash' in (ca, cb) or 'memory' in (ca, cb))):
        return 'qspi'
    if ifaces.get('emmc_sd', 0) >= n * 0.6:
        return 'sd_emmc'
    if ifaces.get('rgmii', 0) >= n * 0.6:
        return 'eth_mii'
    if mem and n >= 8 and 'dram' in (ca, cb):
        return 'ddr_addr' if re.search(r'(^| )(BA|A|MA|ADDR)', names) else 'ddr_byte'
    lcd = sum(1 for l in lanes if LCD_N.search(l.name or ''))
    if lcd >= n * 0.6 or (('ffc_fpc' in (sa, sb)) and n >= 16 and lcd >= n * 0.3):
        return 'parallel_lcd'
    if mem and n >= 6:
        return 'parallel_mem'
    if {ca, cb} == {'fpga'} and ka == kb == 'ic':
        return 'fpga_fpga'
    port = sum(1 for l in lanes if PORT_N.match(l.name or ''))
    connector = (ka == 'connector', kb == 'connector')
    if ca == 'fpga' or cb == 'fpga' or ca == 'mcu' or cb == 'mcu':
        if connector[0] or connector[1] or port >= n * 0.6:
            return 'gpio_bank'
    if connector[0] and connector[1]:
        return 'connector_ribbon'
    if connector[0] or connector[1]:
        if n >= 4:
            return 'connector_ribbon'
    if ifaces.get('i2s', 0) >= n * 0.6 or ifaces.get('spi', 0) >= n * 0.6:
        return 'spi_i2s'
    if port >= n * 0.6:
        return 'gpio_bank'
    return 'unknown'


def swap_class(kind, cls, ka, pi, m):
    """Swap class of one end; '' = none."""
    if kind == 'ddr_byte':
        return 'dq_bit_in_byte'
    if kind == 'matrix_lines':
        return 'matrix_free'
    if kind == 'serdes_lanes':
        return ''  # pair polarity can flip on PCIe/SATA; lanes rarely; report as none
    if cls == 'fpga':
        return 'fpga_io'
    if cls == 'buffer':
        return 'buffer_channel'
    if kind == 'parallel_mem' and cls == 'sram':
        return 'sram_free'
    if ka == 'connector' and pi['subtype'] in ('header', 'wire_to_board', None, 'other'):
        return 'conn_free'
    if cls == 'mcu' and kind in ('gpio_bank', 'unknown', 'connector_ribbon'):
        return 'mcu_gpio'
    return ''


def end_type(pi):
    c = pi.get('cls')
    if c in ('fpga', 'dram', 'sram', 'flash', 'mcu', 'buffer', 'memory') and pi['kind'] == 'ic':
        return c + ':' + pkg_of(pi)
    return pkg_of(pi)


def enrich(m, part, pitch):
    """The netlist-and-placement description of one detected bus (no copper)."""
    a, b = m['a'], m['b']
    lanes = m['lanes']
    n = len(lanes)
    kind = classify_kind(m, part)
    out = dict(kind=kind, width=n, ev=m['ev'], a=a, b=b, stem=m.get('stem'), ifaces=sorted({l.iface for l in lanes if l.iface}),
               nets=[l.nets for l in lanes], names=[l.name for l in lanes], series=sum(1 for l in lanes if len(l.nets) > 1),
               pair_lanes=m.get('pair_lanes', 0))
    a_pi = part[a]
    out['a_cls'] = a_pi.get('cls')
    out['a_kind'] = a_pi['kind']
    out['a_type'] = end_type(a_pi)
    out['a_pitch'] = round(pitch.get(a, 0), 3)
    if b is not None:
        b_pi = part[b]
        out['b_cls'] = b_pi.get('cls')
        out['b_kind'] = b_pi['kind']
        out['b_type'] = end_type(b_pi)
        out['b_pitch'] = round(pitch.get(b, 0), 3)
    else:
        b_pi = None
    # hub/far terminal when more than two terminals on most lanes
    term_counts = [len(l.terms) for l in lanes]
    multi = sum(1 for t in term_counts if t >= 3)
    out['multi_lanes'] = multi
    out['n_terms_max'] = max(term_counts) if term_counts else 0
    other_refs = sorted({r for l in lanes for r in l.terms})
    out['terms'] = other_refs if len(other_refs) <= 8 else other_refs[:8]
    eps_a = 0.3 * max(0.05, pitch.get(a, 0.0) or 0.3)
    dist = None
    perm = None
    if b is not None:
        # primary pair metrics at the pads of a and b
        pa = []
        pb = []
        keep = []
        for l in lanes:
            if a not in l.terms or b not in l.terms:
                continue
            p1 = line_pad(l, a)
            p2 = line_pad(l, b)
            pa.append((p1.x, p1.y))
            pb.append((p2.x, p2.y))
            keep.append(l)
        if len(keep) >= 2:
            eps_b = 0.3 * max(0.05, pitch.get(b, 0.0) or 0.3)
            perm = perm_metrics(pa, pb, min(eps_a, eps_b))
            ca = (sum(p[0] for p in pa) / len(pa), sum(p[1] for p in pa) / len(pa))
            cb = (sum(p[0] for p in pb) / len(pb), sum(p[1] for p in pb) / len(pb))
            dist = math.dist(ca, cb)
            cl = cyc_lis(pa, pb,
                           _centroid(part[a]), _centroid(part[b]))
            out['cyc_lis'] = cl
            out['end_a_span'] = round(max(math.dist(pa[i], pa[j]) for i in range(len(pa)) for j in range(i)) if len(pa) > 1 else 0.0, 2)
            out['end_b_span'] = round(max(math.dist(pb[i], pb[j]) for i in range(len(pb)) for j in range(i)) if len(pb) > 1 else 0.0, 2)
            out['lane_pad_pitch_a'] = round(_pitch(pa), 3)
            out['lane_pad_pitch_b'] = round(_pitch(pb), 3)
    if perm is not None:
        n2 = len(keep)
        out['perm'] = dict(inv=perm['inv'], pairs=perm['pairs'], lis=perm['lis'], lds=perm['lds'], n=n2,
                           order_a=[keep[i].name for i in perm['order_a']],
                           rank_b=perm['order_b_rank'])
    if dist is not None:
        out['dist'] = round(dist, 2)
    # swap classes
    sa = swap_class(kind, a_pi.get('cls'), a_pi['kind'], a_pi, m)
    sb = swap_class(kind, b_pi.get('cls'), b_pi['kind'], b_pi, m) if b_pi is not None else ''
    out['swap_a'] = sa
    out['swap_b'] = sb
    return out, keep if perm is not None else lanes


def _centroid(pi):
    ps = [(p.x, p.y) for p in pi['pads'] if p.net]
    if not ps:
        return (0.0, 0.0)
    return (sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps))


@dataclass
class BusSet:
    """The buses of a board. `buses` are row dicts (see `enrich`) in detection order; `raw` the matching detector groups
    (lanes are `Line`), aligned with `buses`; `pairs` the diff pairs as width-2 rows."""
    buses: list
    raw: list
    pairs: list
    part: dict
    pitch: dict
    sig: dict
    net_pads: dict
    lines: list
    roles: object
    copper: list   # the board's copper layer names


def detect_board(board):
    """Detect a board's buses. Reads only the netlist, parts and pin positions: never tracks or vias."""
    nl, roles, part = build(board)
    for pi in part.values():
        pi['cls'] = classify_part(pi)
    sig = signal_nets(nl, roles)
    pitch = part_pitch(part, sig)
    lines, net_pads = lines_of(board, nl, roles, part, sig)
    refine_dram(part, lines)
    buses, used = detect(board, part, lines, pitch, sig, roles.pairs)
    for g in taut_groups(lines, used, part):
        refs = Counter(r for l in g for r in l.terms)
        common = [r for r, c in refs.most_common() if c >= 0.5 * len(g)]
        a = common[0] if common else (sorted(refs)[0] if refs else None)
        b = common[1] if len(common) > 1 else None
        if a is None or b is None or a == b:   # no two dominant ends: a corridor with common ends only
            b = None
        for l in g:
            used.add(l.id)
        buses.append(dict(lanes=sorted(g, key=lambda l: l.name), ev=['taut'], a=a, b=b, stem=None))
    raw, rows = [], []
    for m in buses:
        if m['a'] is None:
            continue
        rows.append(enrich(m, part, pitch)[0])
        raw.append(m)
    pair_rows = []
    line_of = {n: ln for ln in lines for n in ln.nets}
    for dp in roles.pairs:
        la, lb = line_of.get(dp.p), line_of.get(dp.n)
        if la is None or lb is None or la.id == lb.id:
            continue
        pr = dict(kind='pair', p=dp.p, n=dp.n, iface=dp.interface, speed=dp.speed, conf=round(dp.confidence, 3), width=2,
                  ev=['pair'], nets=[la.nets, lb.nets], names=[la.name, lb.name], a=None, b=None)
        common = sorted(set(la.terms) & set(lb.terms))
        if len(common) >= 2:
            ends = sorted(common, key=lambda r: -sum(1 for q in part[r]['pads'] if q.net))[:2]
            pr['a'], pr['b'] = ends
            pr['a_type'], pr['b_type'] = end_type(part[ends[0]]), end_type(part[ends[1]])
            p1, p2 = line_pad(la, ends[0]), line_pad(la, ends[1])
            pr['dist'] = round(math.dist((p1.x, p1.y), (p2.x, p2.y)), 2)
            pr['_lanes'] = (la, lb)
        pair_rows.append(pr)
    cu = sorted({l for l in (board.layers or {}) if l.endswith('.Cu')} | set(board.stackup.copper if board.stackup and board.stackup.copper else ['F.Cu', 'B.Cu']))
    return BusSet(rows, raw, pair_rows, part, pitch, sig, net_pads, lines, roles, cu)
