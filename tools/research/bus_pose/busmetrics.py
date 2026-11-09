#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bus geometry of stored boards.

Usage: extract.py JOBFILE OUT.jsonl
  JOBFILE: one JSON per line {"board": id, "runs": [run dir, ...]}. The human run is always read
  first (it defines buses from the netlist and footprint geometry, which do not depend on placement).

One JSON line per (run, bus). Buses are found from pin adjacency on both ends, with lines traced
through two-pin series parts; multi-drop lines appear in every part pair they touch.

Read-only; KiCad not needed.
"""
import collections, glob, gzip, json, math, os, re, shutil, sys, tempfile, warnings

from kae.board.kicad_file import load  # noqa: E402
import numpy as np  # noqa: E402

warnings.simplefilter('ignore')
BASE = os.path.expanduser('~/kae-baselines/boards')
TMP = os.environ.get('BUS_TMP') or tempfile.gettempdir()
MIN_LINES = int(os.environ.get('BUS_MIN', '6'))
MAX_NET_PADS = 14
ADJ = 1.8


def is_power(n):
    u = (n or '').upper().lstrip('/').split('/')[-1]
    if not u:
        return True
    return (u.startswith('GND') or u.startswith('VSS') or u.startswith('AGND') or u.startswith('DGND')
            or u.startswith('VCC') or u.startswith('VDD') or u.startswith('+') or u.startswith('VBAT')
            or u.startswith('VBUS') or u.startswith('VIN') or u.startswith('VTT') or u.startswith('VREF')
            or u in ('3V3', '5V', '12V', '1V8', '1V2', 'VOUT', 'V+', 'V-', 'PWR', 'POWER'))


def read(run):
    p = os.path.join(run, 'output.kicad_pcb.gz')
    d = tempfile.mkdtemp(dir=TMP)
    try:
        q = os.path.join(d, 'b.kicad_pcb')
        with gzip.open(p, 'rb') as f, open(q, 'wb') as g:
            shutil.copyfileobj(f, g)
        return load(q, rules=False)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def pitch(pts):
    pts = np.asarray(pts, float)
    if len(pts) < 2:
        return np.inf
    d = np.hypot(pts[:, 0, None] - pts[:, 0], pts[:, 1, None] - pts[:, 1])
    d[d < 1e-3] = np.inf
    return float(np.median(d.min(1)))


def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', str(s))]


def detect(b):
    """[{a, b, lines: [{nets, pa, pb, via}]}] from a human board. pa/pb = pad key (index in footprint pads)."""
    fps = {f.ref: f for f in b.footprints if f.ref and f.pads}
    netpads = collections.defaultdict(list)
    for f in fps.values():
        for i, p in enumerate(f.pads):
            if p.net:
                netpads[p.net].append((f.ref, i))
    def elec(f):
        return [p for p in f.pads if p.net]
    big = {r for r, f in fps.items() if len(elec(f)) >= 6 and sum(1 for p in elec(f) if not is_power(p.net)) >= 4}
    # series contraction
    par = {n: n for n in netpads}
    def root(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    series = {}
    for r, f in fps.items():
        e = elec(f)
        if len(e) == 2 and r not in big:
            n1, n2 = e[0].net, e[1].net
            if n1 != n2 and not is_power(n1) and not is_power(n2):
                if len(netpads[n1]) <= 5 and len(netpads[n2]) <= 5:
                    par[root(n1)] = root(n2)
                    series.setdefault(frozenset((n1, n2)), r)
    groups = collections.defaultdict(list)
    for n in netpads:
        groups[root(n)].append(n)
    lines = []
    for g in groups.values():
        if any(is_power(n) for n in g):
            continue
        pads = [x for n in g for x in netpads[n]]
        if len(pads) > MAX_NET_PADS:
            continue
        ends = collections.defaultdict(list)
        for ref, i in pads:
            if ref in big:
                ends[ref].append(i)
        if len(ends) < 2:
            continue
        ser = sorted({r for k, r in series.items() if all(n in g for n in k)})
        lines.append(dict(nets=sorted(g), ends=dict(ends), ser=ser))
    # bus = pair of big parts, adjacency on both ends
    pits = {}
    for r in big:
        f = fps[r]
        pits[r] = pitch([(p.x, p.y) for p in f.pads if p.net and not is_power(p.net)])
    pairs = collections.defaultdict(list)
    for li, L in enumerate(lines):
        refs = sorted(L['ends'])
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                pairs[(refs[i], refs[j])].append(li)
    out = []
    for (a, b_), lis in pairs.items():
        if len(lis) < MIN_LINES:
            continue
        pa = np.array([[fps[a].pads[lines[l]['ends'][a][0]].x, fps[a].pads[lines[l]['ends'][a][0]].y] for l in lis])
        pb = np.array([[fps[b_].pads[lines[l]['ends'][b_][0]].x, fps[b_].pads[lines[l]['ends'][b_][0]].y] for l in lis])
        n = len(lis)
        comp = list(range(n))
        def r2(x):
            while comp[x] != x:
                comp[x] = comp[comp[x]]
                x = comp[x]
            return x
        da = np.hypot(pa[:, 0, None] - pa[:, 0], pa[:, 1, None] - pa[:, 1])
        db = np.hypot(pb[:, 0, None] - pb[:, 0], pb[:, 1, None] - pb[:, 1])
        adj = (da <= ADJ * pits[a]) & (db <= ADJ * pits[b_])
        for i in range(n):
            for j in range(i + 1, n):
                if adj[i, j]:
                    comp[r2(i)] = r2(j)
        cl = collections.defaultdict(list)
        for i in range(n):
            cl[r2(i)].append(i)
        def rec_of(idx, level):
            recs = []
            for i in idx:
                L = lines[lis[i]]
                recs.append(dict(nets=L['nets'], pa=L['ends'][a][0], pb=L['ends'][b_][0], ser=L['ser']))
            recs.sort(key=lambda x: natural(x['nets'][0]))
            return dict(a=a, b=b_, lines=recs, level=level, ncomp=len(cl), lcomp=max(len(v) for v in cl.values()))
        for c in cl.values():
            if len(c) >= MIN_LINES:
                out.append(rec_of(c, 'comp'))
        if len(cl) > 1 and n >= 8:
            out.append(rec_of(list(range(n)), 'pair'))
    out.sort(key=lambda x: -len(x['lines']))
    return out, fps


DQ_RE = re.compile(r'(?:^|[/_.\-])(?:DDR\d?_|MEM_|SD_|M\d_)?(?:DQ|D|DATA|IO)\[?(\d+)\]?$', re.I)


def dq_index(name):
    m = DQ_RE.search(str(name).split('/')[-1])
    if not m:
        return None
    return int(m.group(1))


def lnds(seq):
    """Longest non-decreasing subsequence length."""
    import bisect
    t = []
    for x in seq:
        k = bisect.bisect_right(t, x)
        if k == len(t):
            t.append(x)
        else:
            t[k] = x
    return len(t)


def lds_strict(seq):
    """Longest strictly decreasing subsequence (min number of non-decreasing chains, Dilworth)."""
    import bisect
    t = []
    for x in seq:
        v = -x
        k = bisect.bisect_left(t, v)
        if k == len(t):
            t.append(v)
        else:
            t[k] = v
    return len(t)


def planar(pa, pb, ca, cb):
    """Planarity of the a->b matching, in two frames: projection on the bus normal, and cyclic order around
    each part's centre starting from the direction to the other end. Max of the two = LIS measure.
    Returns (lis_frac, lds, inv_frac)."""
    n = len(pa)
    if n < 2:
        return 1.0, 1, 0.0
    u = cb - ca
    L = np.hypot(*u)
    if L < 1e-6:
        return 1.0, 1, 0.0
    u = u / L
    nv = np.array([-u[1], u[0]])
    # projection frame
    p = np.round((pa - ca) @ nv, 2)
    q = np.round((pb - cb) @ nv, 2)
    order = np.lexsort((q, p))
    qs = [float(x) for x in q[order]]
    lis1 = lnds(qs)
    lds1 = lds_strict(qs)
    # cyclic frame
    def ang(pts, c, d):
        v = pts - c
        return np.round(np.arctan2(v @ np.array([-d[1], d[0]]), v @ d), 2)
    pc = ang(pa, ca, u)
    qc = -ang(pb, cb, -u)
    order = np.lexsort((qc, pc))
    qs2 = [float(x) for x in qc[order]]
    lis2 = lnds(qs2)
    lds2 = lds_strict(qs2)
    dp = np.sign(p[:, None] - p[None, :])
    dq = np.sign(q[:, None] - q[None, :])
    iu = np.triu_indices(n, 1)
    inv = float(((dp * dq)[iu] < 0).sum()) / (n * (n - 1) / 2)
    return max(lis1, lis2) / n, min(lds1, lds2), inv


def orient(p, q, r):
    return (q[..., 0] - p[..., 0]) * (r[..., 1] - p[..., 1]) - (q[..., 1] - p[..., 1]) * (r[..., 0] - p[..., 0])


def nxing(a, b, c=None, d=None):
    """Proper crossings among segments a[i]-b[i] (c None), or between a-b and c-d."""
    if c is None:
        n = len(a)
        if n < 2:
            return 0
        i, j = np.triu_indices(n, 1)
        o1 = orient(a[i], b[i], a[j]); o2 = orient(a[i], b[i], b[j]); o3 = orient(a[j], b[j], a[i]); o4 = orient(a[j], b[j], b[i])
    else:
        if len(a) == 0 or len(c) == 0:
            return 0
        A, B = np.repeat(a, len(c), 0), np.repeat(b, len(c), 0)
        C, D = np.tile(c, (len(a), 1)), np.tile(d, (len(a), 1))
        o1 = orient(A, B, C); o2 = orient(A, B, D); o3 = orient(C, D, A); o4 = orient(C, D, B)
    return int(np.sum((o1 * o2 < 0) & (o3 * o4 < 0)))


def rot(P, c, q, mirror=False):
    v = P - c
    if mirror:
        v = v * np.array([-1.0, 1.0])
    for _ in range(q):
        v = np.stack((v[:, 1], -v[:, 0]), 1)
    return c + v


def seg_measure(pa, pb, ca, cb, ha, hb):
    u = (cb - ca) / max(np.hypot(*(cb - ca)), 1e-6)
    v = pb - pa
    Ln = np.hypot(v[:, 0], v[:, 1])
    fa = float(np.mean((pa - ca) @ u > 1e-3))
    fb = float(np.mean((pb - cb) @ (-u) > 1e-3))
    # port normal alignment
    pca = pa.mean(0) - ca
    pcb = pb.mean(0) - cb
    cosa = float((pca @ u) / max(np.hypot(*pca), 1e-6)) if np.hypot(*pca) > 0.2 * ha else None
    cosb = float((pcb @ -u) / max(np.hypot(*pcb), 1e-6)) if np.hypot(*pcb) > 0.2 * hb else None
    # parallelism
    w = v / Ln.clip(1e-6)[:, None]
    R = float(np.hypot(*w.mean(0)))
    return dict(L=float(Ln.sum()), Lmean=float(Ln.mean()), Lmax=float(Ln.max()),
                face_a=fa, face_b=fb, cos_a=cosa, cos_b=cosb, par=R)


def corridor(b, fps, bus_refs, pa, pb, ca, cb, side):
    """Foreign parts in the hull of the bus ends, and min free width along it, on the bus's outer layer."""
    from shapely.geometry import MultiPoint, Point
    hull = MultiPoint(np.vstack((pa, pb))).convex_hull
    res = dict(hull_area=float(hull.area))
    out_pads = out_parts = dec = ser = 0
    u = (cb - ca) / max(np.hypot(*(cb - ca)), 1e-6)
    nv = np.array([-u[1], u[0]])
    Lc = float(np.hypot(*(cb - ca)))
    sects = []
    tgt_layer = f'{side}.Cu'
    width_req = max(np.ptp((np.vstack((pa, pb)) - ca) @ nv), 1.0)
    # sections along the corridor
    N = 16
    stations = np.linspace(0.05, 0.95, N) * Lc
    blocked = [[] for _ in range(N)]
    for ref, f in fps.items():
        if ref in bus_refs:
            continue
        inh = 0
        cx, cy = f.x, f.y
        if hull.contains(Point(cx, cy)) and (f.side == side or any(p.drill for p in f.pads)):
            out_parts += 1
            elec = [p for p in f.pads if p.net]
            if len(elec) == 2:
                if any(is_power(p.net) for p in elec):
                    dec += 1
                else:
                    ser += 1
        for p in f.pads:
            on = (tgt_layer in p.layers) or p.drill > 0
            if not on:
                continue
            if hull.contains(Point(p.x, p.y)):
                inh += 1
            sx, sy = (p.size or (0.5, 0.5))
            r = max(sx, sy) / 2
            t = ((np.array([p.x, p.y]) - ca) @ u)
            s = ((np.array([p.x, p.y]) - ca) @ nv)
            for k, st in enumerate(stations):
                if abs(t - st) <= r:
                    blocked[k].append((s - r, s + r))
        out_pads += inh
    mn = np.inf
    w_ends = np.ptp((np.vstack((pa, pb)) - ca) @ nv)
    s0 = float(np.min((np.vstack((pa, pb)) - ca) @ nv))
    s1 = float(np.max((np.vstack((pa, pb)) - ca) @ nv))
    for iv in blocked:
        iv = sorted(iv)
        free = 0.0; cur = s0
        for lo, hi in iv:
            if hi < s0 or lo > s1:
                continue
            if lo > cur:
                free = max(free, lo - cur)
            cur = max(cur, hi)
        free = max(free, s1 - cur) if s1 > cur else free
        mn = min(mn, free)
    res.update(for_pads=out_pads, for_parts=out_parts, for_dec=dec, for_ser=ser, free_w=float(mn), span=float(w_ends), width_req=float(width_req))
    return res


def part_center(f):
    pts = np.array([[p.x, p.y] for p in f.pads if p.number != ''] or [[f.x, f.y]])
    return np.array([(pts[:, 0].min() + pts[:, 0].max()) / 2, (pts[:, 1].min() + pts[:, 1].max()) / 2]), float(max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1])) / 2), float(min(np.ptp(pts[:, 0]), np.ptp(pts[:, 1])) / 2)


def connected(b, nets):
    """nets: list of net names. Returns (opens, n_pads, vias, len_mm). Union-find over items by contact; zone nets -> None."""
    zones = {z.net for z in b.zones}
    if any(n in zones for n in nets):
        return None
    out_opens = 0; pads_total = 0; vias_total = 0; lenmm = 0.0
    pads_all = [(p, f) for f in b.footprints for p in f.pads if p.net in set(nets)]
    tr = [t for t in b._by_net.get('tr', {}).get('x', [])] if False else None
    for n in nets:
        pads = [p for p, f in pads_all if p.net == n]
        tracks = b_net_tracks.get(n, [])
        vias = b_net_vias.get(n, [])
        pads_total += len(pads)
        vias_total += len(vias)
        for t in tracks:
            lenmm += math.dist(t.start, t.end)
        items = []
        for p in pads:
            sx, sy = (p.size or (0.3, 0.3))
            items.append(('p', p.x, p.y, min(sx, sy) / 2, set(p.layers) if p.layers else {'*'}))
        for v in vias:
            items.append(('v', v.x, v.y, v.size / 2, set(v.layers)))
        for t in tracks:
            items.append(('t', t.start, t.end, t.width / 2, {t.layer}))
        m = len(items)
        par = list(range(m))
        def r(x):
            while par[x] != x:
                par[x] = par[par[x]]; x = par[x]
            return x
        for i in range(m):
            for j in range(i + 1, m):
                if r(i) == r(j):
                    continue
                if not (items[i][4] & items[j][4]):
                    continue
                d = idist(items[i], items[j])
                if d <= items[i][3] + items[j][3] + 0.01:
                    par[r(i)] = r(j)
        comps = len({r(i) for i in range(m) if items[i][0] == 'p'})
        out_opens += max(0, comps - 1) if pads else 0
    return out_opens, pads_total, vias_total, lenmm


def pt_seg(px, py, a, b):
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def seg_seg(a, b, c, d):
    def cr(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1 = cr(a, b, c); d2 = cr(a, b, d); d3 = cr(c, d, a); d4 = cr(c, d, b)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return 0.0
    return min(pt_seg(a[0], a[1], c, d), pt_seg(b[0], b[1], c, d), pt_seg(c[0], c[1], a, b), pt_seg(d[0], d[1], a, b))


def idist(x, y):
    tx, ty = x[0], y[0]
    if tx == 't' and ty == 't':
        return seg_seg(x[1], x[2], y[1], y[2])
    if tx == 't':
        return pt_seg(y[1], y[2], x[1], x[2])
    if ty == 't':
        return pt_seg(x[1], x[2], y[1], y[2])
    return math.hypot(x[1] - y[1], x[2] - y[2])


b_net_tracks = {}
b_net_vias = {}


def prepare_copper(b):
    global b_net_tracks, b_net_vias
    b_net_tracks = collections.defaultdict(list)
    b_net_vias = collections.defaultdict(list)
    for t in b.tracks:
        b_net_tracks[t.net].append(t)
    for v in b.vias:
        b_net_vias[v.net].append(v)


def others_segments(fps):
    by = collections.defaultdict(list)
    for f in fps.values():
        for p in f.pads:
            if p.net and not is_power(p.net):
                by[p.net].append((p.x, p.y))
    A, B, N = [], [], []
    for n, pts in by.items():
        if not 2 <= len(pts) <= 12:
            continue
        pts = list(pts)
        # MST
        P = np.array(pts)
        m = len(P)
        in_t = [0]
        rest = set(range(1, m))
        d = np.hypot(P[:, 0] - P[0, 0], P[:, 1] - P[0, 1])
        pa = [0] * m
        while rest:
            j = min(rest, key=lambda k: d[k])
            rest.discard(j)
            A.append(P[pa[j]])
            B.append(P[j])
            N.append(n)
            for k in rest:
                dk = np.hypot(*(P[k] - P[j]))
                if dk < d[k]:
                    d[k] = dk
                    pa[k] = j
    return np.array(A).reshape(-1, 2), np.array(B).reshape(-1, 2), N


def bus_record(b, fps, bus, human_fps, oxx):
    a, b_ = bus['a'], bus['b']
    if a not in fps or b_ not in fps:
        return None
    fa, fb = fps[a], fps[b_]
    idx = []
    pa, pb = [], []
    for ln in bus['lines']:
        try:
            pa.append((fa.pads[ln['pa']].x, fa.pads[ln['pa']].y))
            pb.append((fb.pads[ln['pb']].x, fb.pads[ln['pb']].y))
        except IndexError:
            return None
    pa, pb = np.array(pa), np.array(pb)
    ca, ha, ha2 = part_center(fa)
    cb, hb, hb2 = part_center(fb)
    lis, lds, inv = planar(pa, pb, ca, cb)
    xs = nxing(pa, pb)
    n = len(pa)
    r = dict(n=n, a=a, b=b_, a_val=fa.value, b_val=fb.value, a_lib=fa.lib_id, b_lib=fb.lib_id,
             a_pads=sum(1 for p in fa.pads if p.net), b_pads=sum(1 for p in fb.pads if p.net),
             a_rot=fa.rot, b_rot=fb.rot, a_side=fa.side, b_side=fb.side,
             lis=lis, lds=lds, inv=inv, xing=xs, xing_frac=xs / max(1, n * (n - 1) / 2))
    r.update(seg_measure(pa, pb, ca, cb, ha, hb))
    # rotation search: 16 combos in place
    best = dict(Lmin=np.inf, Lq=None, lismax=-1, lq=None, xmin=10**9, xq=None)
    table = []
    for qa in range(4):
        pa2 = rot(pa, ca, qa)
        for qb in range(4):
            pb2 = rot(pb, cb, qb)
            L = float(np.hypot(*(pb2 - pa2).T).sum())
            l, ds, _ = planar(pa2, pb2, ca, cb)
            xx = nxing(pa2, pb2)
            table.append((qa, qb, L, l, xx))
            if L < best['Lmin']:
                best['Lmin'] = L; best['Lq'] = (qa, qb)
            if (l, -L) > (best['lismax'], -best.get('lml', 1e9)):
                best['lismax'] = l; best['lml'] = L; best['lq'] = (qa, qb)
            if xx < best['xmin']:
                best['xmin'] = xx; best['xq'] = (qa, qb)
    r['rot_Lmin'] = best['Lmin']; r['rot_lismax'] = best['lismax']; r['rot_lml'] = best['lml']; r['rot_xmin'] = best['xmin']
    r['rot_cur_Lrank'] = sum(1 for t in table if t[2] < r['L'] - 1e-6)
    r['rot_cur_lrank'] = sum(1 for t in table if t[3] > lis + 1e-6)
    # with side flips (mirror)
    bl = -1; bml = 1e9
    for ma in (False, True):
        for mb in (False, True):
            for qa in range(4):
                pa2 = rot(pa, ca, qa, ma)
                for qb in range(4):
                    pb2 = rot(pb, cb, qb, mb)
                    l, _, _ = planar(pa2, pb2, ca, cb)
                    if l > bl:
                        bl = l
                        bml = float(np.hypot(*(pb2 - pa2).T).sum())
                    elif abs(l - bl) < 1e-9:
                        bml = min(bml, float(np.hypot(*(pb2 - pa2).T).sum()))
    r['mir_lismax'] = bl; r['mir_lml'] = bml
    # relative-pose ceiling: approach from N/E/S/W, abutted (2 mm gap), any rotation of each.
    ell = -1; elml = 1e9; eLmin = 1e12
    for dirn in range(4):
        d = np.array([[1, 0], [0, 1], [-1, 0], [0, -1]][dirn], float)
        span_a = np.ptp((pa - ca) @ np.array([d[0], d[1]])) if False else ha + ha2 * 0
        sep = max(np.ptp(np.vstack((pa, pb))[:, 0]) * 0, 0)
        for qa in range(4):
            pa2 = rot(pa, ca, qa)
            for qb in range(4):
                pb_rel = rot(pb, cb, qb) - cb
                # abut: separation from the extent of A and B along d
                exa = float(np.max((np.array([[p.x, p.y] for p in fa.pads]) - ca) @ d)) if qa % 2 == 0 else float(np.max(((rot(np.array([[p.x, p.y] for p in fa.pads]), ca, qa) - ca) @ d)))
                exb = float(np.max(-(np.array([[p.x, p.y] for p in fb.pads]) - cb) @ d)) if qb % 2 == 0 else float(np.max(-((rot(np.array([[p.x, p.y] for p in fb.pads]), cb, qb) - cb) @ d)))
                gap = 3.0
                c2 = ca + d * (exa + exb + gap)
                pb2 = c2 + pb_rel
                l, _, _ = planar(pa2, pb2, ca, c2)
                L2 = float(np.hypot(*(pb2 - pa2).T).sum())
                if l > ell + 1e-9 or (abs(l - ell) < 1e-9 and L2 < elml):
                    ell = l; elml = L2
                if L2 < eLmin:
                    eLmin = L2
    r['abut_lismax'] = ell; r['abut_lml'] = elml; r['abut_Lmin'] = eLmin
    # null: random planarity of this pinout from a random relative pose
    # foreign crossings
    bnets = {n for ln in bus['lines'] for n in ln['nets']}
    A, B = oxx(bnets)
    r['foreign_xing'] = nxing(pa, pb, A, B) if len(A) else 0
    # corridor
    r.update(corridor(b, fps, {a, b_} | {s for ln in bus['lines'] for s in ln['ser']}, pa, pb, ca, cb, fa.side))
    # series parts
    vals = []
    for ln, a0, b0 in zip(bus['lines'], pa, pb):
        for s in ln['ser']:
            if s in fps:
                f = fps[s]
                c = np.array([f.x, f.y])
                ab = b0 - a0
                Lab = np.hypot(*ab)
                if Lab < 1e-6:
                    continue
                t = float(((c - a0) @ ab) / (Lab * Lab))
                perp = float(abs((c - a0)[0] * ab[1] - (c - a0)[1] * ab[0]) / Lab)
                pa2 = [p for p in f.pads if p.net]
                axis = np.array([pa2[0].x - pa2[1].x, pa2[0].y - pa2[1].y]) if len(pa2) >= 2 else ab
                cang = float(abs(axis @ ab) / max(np.hypot(*axis) * Lab, 1e-6))
                vals.append((t, perp, cang, Lab))
    if vals:
        v = np.array(vals)
        r['ser_n'] = len(vals); r['ser_t'] = float(v[:, 0].mean()); r['ser_tstd'] = float(v[:, 0].std())
        r['ser_perp'] = float(v[:, 1].mean()); r['ser_perp_max'] = float(v[:, 1].max()); r['ser_cang'] = float(v[:, 2].mean())
    # connectivity
    ot, tp, tv, tl = 0, 0, 0, 0.0
    lopen = 0
    for ln in bus['lines']:
        c = connected(b, ln['nets'])
        if c is None:
            continue
        o, _, v, l = c
        ot += o; tv += v; tl += l
        if o > 0:
            lopen += 1
    r.update(opens=ot, lines_open=lopen, vias=tv, track_len=tl)
    # swap ceiling and null
    import random as _rd
    rng = _rd.Random(12345)
    names = [ln['nets'][0] for ln in bus['lines']]
    idx = [dq_index(nm) for nm in names]
    r['dq_lines'] = int(sum(1 for i in idx if i is not None))
    # permutation in projection frame
    def perm_of(q):
        u = (cb - ca) / max(np.hypot(*(cb - ca)), 1e-6)
        nv = np.array([-u[1], u[0]])
        pp = np.round((pa - ca) @ nv, 2)
        qq = np.round((q - cb) @ nv, 2)
        return pp, qq
    # DQ within-byte swap: for lines of a byte class, reassign so B order follows A order
    if sum(1 for i in idx if i is not None) >= 8:
        pp, qq = perm_of(pb)
        q_sw = pb.copy()
        for byte in sorted({i // 8 for i in idx if i is not None}):
            cls = [k for k, i in enumerate(idx) if i is not None and i // 8 == byte]
            if len(cls) < 2:
                continue
            by_a = sorted(cls, key=lambda k: pp[k])
            by_b = sorted(cls, key=lambda k: qq[k])
            tmp = pb.copy()
            for ka, kb in zip(by_a, by_b):
                q_sw[ka] = tmp[kb]
        l_sw, ld_sw, _ = planar(pa, q_sw, ca, cb)
        r['dq_bytes'] = len({i // 8 for i in idx if i is not None})
        r['swap_lis'] = l_sw; r['swap_lds'] = ld_sw
        r['swap_len'] = float(np.hypot(*(q_sw - pa).T).sum())
        # plus byte order free: order byte groups by mean A pos -> assign byte groups in B order
    lrs = []
    pb2 = pb.copy()
    n2 = len(pb)
    for _ in range(40):
        rng.shuffle(idxs := list(range(n2)))
        lr, _, _ = planar(pa, pb[idxs], ca, cb)
        lrs.append(lr)
    r['lis_rand'] = float(np.mean(lrs))
    # relative pose
    dc = cb - ca
    r['dist_c'] = float(np.hypot(*dc)); r['same_side'] = fa.side == fb.side
    r['rel_rot'] = (fa.rot - fb.rot) % 360 if fa.side == fb.side else (fa.rot + fb.rot) % 360
    r['ax_align'] = float(min(abs(dc[0]), abs(dc[1])) / max(1e-6, max(abs(dc[0]), abs(dc[1]))))
    r['half_a'] = ha; r['half_b'] = hb; r['n_ser'] = sum(len(ln['ser']) for ln in bus['lines'])
    r['nets_all'] = sorted({n for ln in bus['lines'] for n in ln['nets']})[:80]
    return r


def score_of(run):
    best = None
    for f in glob.glob(run + '/evals/*.json'):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        s = d.get('score')
        if s and (best is None or (s.get('score_version') or 0) >= (best.get('score_version') or 0)):
            best = s
    return best or {}


def process(job, out):
    bid = job['board']
    runs = job['runs']
    human = job.get('human')
    if human is None:
        cand = sorted(glob.glob(f'{BASE}/{bid}/runs/human.*.a0'))
        if not cand:
            return
        human = cand[0]
    H = read(human)
    buses, hfps = detect(H)
    if not buses:
        return
    # memory-part relations, measured in the human board
    for run in ([human] + [r for r in runs if r != human]):
        try:
            b = H if run == human else read(run)
        except Exception as e:
            print('ERR', run, e, file=sys.stderr)
            continue
        score = score_of(run)
        fps = {f.ref: f for f in b.footprints if f.ref and f.pads}
        prepare_copper(b)
        A_all = None
        sA, sB, sN = others_segments(fps)
        sN = np.array(sN, dtype=object)
        def oxx(bnets):
            m = ~np.isin(sN, list(bnets)) if len(sN) else np.array([], bool)
            return sA[m], sB[m]
        for k, bus in enumerate(buses):
            if bus['a'] not in fps or bus['b'] not in fps:
                continue
            try:
                r = bus_record(b, fps, bus, hfps, oxx)
            except Exception as e:
                print('ERR', bid, run, e, file=sys.stderr)
                continue
            if r is None:
                continue
            r.update(board=bid, run=os.path.basename(run), bus=k, level=bus['level'], ncomp=bus['ncomp'], lcomp=bus['lcomp'], legal=score.get('legal'), valid=score.get('valid'),
                     completion=score.get('completion'), unconnected=score.get('unconnected'), errors=score.get('errors'),
                     hpwl_ratio=score.get('hpwl_ratio'))
            out.write(json.dumps(r) + '\n')
        out.flush()


def main():
    os.makedirs(TMP, exist_ok=True)
    with open(sys.argv[2], 'a') as out:
        for line in open(sys.argv[1]):
            try:
                process(json.loads(line), out)
            except Exception as e:
                import traceback; traceback.print_exc(file=sys.stderr)
                print('FAIL', line[:200], e, file=sys.stderr)


if __name__ == '__main__':
    main()
