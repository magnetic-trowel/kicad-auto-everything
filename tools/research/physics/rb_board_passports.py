# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Conductor passports on a real KiCad board: what each piece of copper is doing.

Round 3, real-board conductor understanding (prefix rb). Applies the round-2 lens CD
passport (docs/topics/physics/lens-cd.md) to a routed .kicad_pcb instead of a synthetic
board. Report: docs/topics/physics/real-board-passports.md.

Pipeline (no KiCad needed; reads the saved file):
  1. Parse nets, stackup, footprints/pads (rect, roundrect, oval, circle, custom), tracks,
     arcs, vias and zones. Zone fills: the saved filled_polygon is used; a zone with no fill
     on a layer is approximated by its outline minus other-net copper (flagged), and fills
     that overlap other-net copper are flagged as possibly stale.
  2. Infer roles from net names and footprints (printed as a log, overridable): ground,
     power rails, shunts (R <= 0.2 ohm), the driver IC that feeds them, the load connector,
     supply connectors, sense amplifiers across each shunt, the host connector, decaps.
  3. DC conductor model: every power-relevant net is rasterized on its own grid (cell
     coverage and face coverage by supersampling; 0.05 mm for small nets, 0.2 mm for planes),
     vias are barrels (rho*l/(pi*(d+t)*t), t = 20 um plating) contacting the cells they
     pierce, pads used as terminals are equipotential electrodes, shunts are lumped.
     One sparse factorization per connected component.
  4. DC passports: per-source current shares, I^2R attribution, current density, exact
     removal costs (rank-1: dZ_qp = i_p i_q / (g (1 - rho)); Woodbury for sets), leverage
     rho (exact for selected pieces, Johnson-Lindenstrauss sketch for all), dead copper,
     and common impedance at quiet ports (Kelvin sense of each shunt; amplifier ground vs
     host-connector ground), with Tellegen attribution and its cancellation index chi.
  5. HF (inductive limit) hot-loop passport with a stack-local magnetostatic model: every
     copper layer in a window around the driver is a sheet; the stored energy per face is
     (mu0/2) * sum over gaps h_g * H_g^2 with H_g the cumulative sheet current above gap g
     (parallel-plate limit, outer field optimised). It generalises "mu0*h*squares over the
     nearest plane" to a full stack, so a passive plane (another net) carries its eddy
     image current by itself. Gives loop L, where the HF current flows, energy by gap,
     exact via removal / Thevenin via-addition values, and the no-plane counterfactual.
  6. Switch-node charge to whom (parallel-plate C of the phase copper to adjacent layers).
  7. Floors (lens VP): Beckmann R >= R_s*d^2/A per phase pour, and a joint convex floor for
     the phase pours sharing the region around the driver (Frank-Wolfe on the relaxed
     density with a per-cell sum <= 1 and a total-area budget; the FW gap certifies it).

Model limits: quasi-static; DC is exact for the rasterized geometry (zone fills as saved,
copper thickness from the stackup, 20 C copper); no solder, lead-frame or package
resistance (pads are equipotential); HF model is local (no lateral fringing: narrow strips
over a plane are over-estimated by ~1.3-1.5x at w/h = 5-10; plane-pair via spreading is
accurate), lossless (perfect conductors above a few MHz), no package/ESL unless stated.

Usage:
  python -I rb_board_passports.py BOARD.kicad_pcb [--current 1.0] [--h-small 0.05]
         [--h-plane 0.2] [--h-hf 0.15] [--quick] [--no-hf] [--no-floor] [--sketch 48]
Runtime on the bldcpower board (32 mm round, 4 layers): about 2-3 min on one core, peak
memory about 1.5 GB with default grids (--quick: ~40 s). OMP_NUM_THREADS=1 is set here.
Deterministic (fixed seeds).
"""
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402

import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402
import shapely  # noqa: E402
from scipy import ndimage  # noqa: E402
from scipy.sparse.csgraph import connected_components  # noqa: E402
from shapely import affinity  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.ops import polygonize, unary_union  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pc_refplane import arc_points, first, kids, parse, rot, xy  # noqa: E402  (s-expression helpers)

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
RHO_CU = 1.72e-8          # ohm m at 20 C
TCR_CU = 0.0039           # 1/K
T_PLATE = 20e-6           # via barrel plating, m (IPC-6012 class 2 average)
GND_RE = re.compile(r'(^|[^A-Z])(A|D|P|S|C)?GND|^/?VSS|^0V$', re.I)
PWR_RE = re.compile(r'^/?(\+?\d+(\.\d+)?V\d*|\+[A-Z0-9_.]+|V(CC|DD|BUS|IN|SYS|BAT|MOT|M|PP|REG|CORE|CAP|S)[A-Z0-9_.]*|'
                    r'[AD]V(DD|CC)[A-Z0-9_]*|\d+V\d+|[0-9]+V[0-9]*_?[A-Z]*)$', re.I)
T0 = time.perf_counter()


def tic():
    return time.perf_counter()


def log(msg=""):
    print(msg, flush=True)


# ============================================================================ parsing
def pts_list(node):
    p = first(node, 'pts')
    out = []
    for e in (p[1:] if p else []):
        if isinstance(e, list) and e:
            if e[0] == 'xy':
                out.append((float(e[1]), float(e[2])))
            elif e[0] == 'arc':
                out.extend(arc_points(xy(first(e, 'start')), xy(first(e, 'mid')), xy(first(e, 'end')), 8))
    return out


def parse_ohms(val):
    """Resistance in ohms from a footprint value ('50m', 'KRL1220 50m', '0R05', 'R050', '20K', '5.1K', '120')."""
    v = val.replace('Ω', 'R').replace('ohm', 'R').replace('Ohm', 'R')
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*m(?:R)?(?![\w])', v)
    if m:
        return float(m.group(1)) * 1e-3
    m = re.search(r'(?<![\w.])(\d+)R(\d+)(?![\w.])', v)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.search(r'(?<![\w.])R(\d+)(?![\w.])', v)
    if m:
        return float(f"0.{m.group(1)}")
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*([kKM])?(?:R)?(?![\w.])', v)
    if m:
        return float(m.group(1)) * {None: 1.0, 'k': 1e3, 'K': 1e3, 'M': 1e6}[m.group(2)]
    m = re.search(r'(\d+)([kKMR])(\d+)', v)
    if m:
        return float(f"{m.group(1)}.{m.group(3)}") * {'k': 1e3, 'K': 1e3, 'M': 1e6, 'R': 1.0}[m.group(2)]
    return None


class KBoard:
    """A routed board: nets, stackup, pads, tracks, vias and zone fills (KiCad 6-9 s-expressions)."""

    def __init__(self, path):
        tree = parse(open(path, encoding='utf-8', errors='replace').read())
        self.version = (first(tree, 'version') or [None, '?'])[1]
        self.netname = {}
        for n in kids(tree, 'net'):
            if len(n) >= 3:
                self.netname[n[1]] = n[2]
        self._stackup(tree)
        self.fps, self.pads = [], []
        for fp in kids(tree, 'footprint') + kids(tree, 'module'):
            self._footprint(fp)
        self.tracks = []
        for s in kids(tree, 'segment'):
            self.tracks.append(dict(layer=first(s, 'layer')[1], net=self.net_of(s), w=float(first(s, 'width')[1]),
                                    pts=[xy(first(s, 'start')), xy(first(s, 'end'))]))
        for a in kids(tree, 'arc'):
            self.tracks.append(dict(layer=first(a, 'layer')[1], net=self.net_of(a), w=float(first(a, 'width')[1]),
                                    pts=arc_points(xy(first(a, 'start')), xy(first(a, 'mid')), xy(first(a, 'end')), 12)))
        self.vias = []
        for v in kids(tree, 'via'):
            ly = first(v, 'layers')
            ends = [n for n in (ly[1:] if ly else []) if n in self.z] or [self.cu[0], self.cu[-1]]
            x, y = xy(first(v, 'at'))
            self.vias.append(dict(x=x, y=y, size=float(first(v, 'size')[1]), drill=float(first(v, 'drill')[1]),
                                  net=self.net_of(v), layers=self.span(ends[0], ends[-1])))
        self.zones = []
        for z in kids(tree, 'zone'):
            if first(z, 'keepout') or first(z, 'rule_area'):
                continue
            net = self.net_of(z) or (first(z, 'net_name') or [None, ''])[1]
            if not net:
                continue
            lys = []
            for key in ('layer', 'layers'):
                e = first(z, key)
                for nm in (e[1:] if e else []):
                    if nm == '*.Cu':
                        lys += self.cu
                    elif nm == 'F&B.Cu':
                        lys += [self.cu[0], self.cu[-1]]
                    elif nm in self.z:
                        lys.append(nm)
            pts = pts_list(first(z, 'polygon')) if first(z, 'polygon') else []
            outline = Polygon(pts).buffer(0) if len(pts) >= 3 else Polygon()
            fills = {}
            for fpoly in kids(z, 'filled_polygon'):
                ly = first(fpoly, 'layer')[1]
                p2 = pts_list(fpoly)
                if len(p2) >= 3:
                    g = Polygon(p2).buffer(0)
                    fills[ly] = unary_union([fills[ly], g]) if ly in fills else g
            cs = first(z, 'connect_pads')
            clr = float(first(cs, 'clearance')[1]) if cs and first(cs, 'clearance') else 0.2
            self.zones.append(dict(net=net, layers=sorted(set(lys), key=self.cu.index), outline=outline,
                                   fills=fills, clearance=clr))
        self.outline = self._outline(tree)
        self._geo = {}

    # ---------------------------------------------------------------- helpers
    def net_of(self, node):
        n = first(node, 'net')
        if not n or len(n) < 2:
            return None
        if len(n) >= 3:
            return n[2]
        return self.netname.get(n[1], n[1])

    def _stackup(self, tree):
        lay = first(tree, 'layers')
        names = [e[1] for e in lay[1:] if isinstance(e, list) and len(e) > 2 and str(e[1]).endswith('.Cu')]
        su = first(first(tree, 'setup') or [], 'stackup')
        order, tcu, gap, er = [], {}, {}, {}
        if su:
            diel, ers, last = 0.0, [], None
            for e in kids(su, 'layer'):
                typ = (first(e, 'type') or [None, ''])[1]
                ths = [float(c[1]) for c in e if isinstance(c, list) and c and c[0] == 'thickness'
                       and re.match(r'^[\d.eE+-]+$', str(c[1]))]
                th = sum(ths)
                if str(e[1]).endswith('.Cu'):
                    order.append(e[1])
                    tcu[e[1]] = th or 0.035
                    if last is not None:
                        gap[(last, e[1])] = diel
                        er[(last, e[1])] = sum(t * x for t, x in ers) / max(1e-12, sum(t for t, _ in ers)) if ers else 4.5
                    last, diel, ers = e[1], 0.0, []
                elif typ in ('core', 'prepreg') or 'dielectric' in str(e[1]):
                    diel += th
                    epsr = first(e, 'epsilon_r')
                    ers.append((th, float(epsr[1]) if epsr else 4.5))
        if sorted(order) != sorted(names) or not all(gap.get((a, b), 0) > 0 for a, b in zip(order, order[1:])):
            th = float((first(first(tree, 'general') or [], 'thickness') or [0, 1.6])[1])
            def ordk(nm):
                return -1 if nm == 'F.Cu' else 999 if nm == 'B.Cu' else int(re.sub(r'\D', '', nm) or 0)
            order = sorted(names, key=ordk)
            n = max(1, len(order) - 1)
            tcu = {nm: 0.035 for nm in order}
            gap = {(a, b): th / n - 0.035 for a, b in zip(order, order[1:])}
            er = {k: 4.5 for k in gap}
            self.stackup_note = 'no usable stackup: copper spread evenly, 35 um'
        else:
            self.stackup_note = 'from file'
        self.cu, self.tcu, self.gap, self.er = order, tcu, gap, er
        self.z, zc = {}, 0.0
        for i, nm in enumerate(order):
            if i:
                zc += tcu[order[i - 1]] / 2 + gap[(order[i - 1], nm)] + tcu[nm] / 2
            self.z[nm] = zc
        self.rs = {nm: RHO_CU / (tcu[nm] * 1e-3) for nm in order}       # ohm per square

    def span(self, a, b):
        i, j = sorted((self.cu.index(a), self.cu.index(b)))
        return self.cu[i:j + 1]

    def _pad_poly(self, pd, shape):
        sz = first(pd, 'size')
        sx = float(sz[1])
        sy = float(sz[2]) if len(sz) > 2 else sx
        if shape == 'circle':
            g = Point(0, 0).buffer(sx / 2, quad_segs=8)
        elif shape == 'oval':
            if abs(sx - sy) < 1e-9:
                g = Point(0, 0).buffer(sx / 2, quad_segs=8)
            elif sx > sy:
                g = LineString([(-(sx - sy) / 2, 0), ((sx - sy) / 2, 0)]).buffer(sy / 2, quad_segs=8)
            else:
                g = LineString([(0, -(sy - sx) / 2), (0, (sy - sx) / 2)]).buffer(sx / 2, quad_segs=8)
        elif shape == 'roundrect':
            rr = first(pd, 'roundrect_rratio')
            r = min((float(rr[1]) if rr else 0.25) * min(sx, sy), 0.5 * min(sx, sy) - 1e-6)
            g = box(-sx / 2 + r, -sy / 2 + r, sx / 2 - r, sy / 2 - r).buffer(r, quad_segs=4) if r > 1e-6 \
                else box(-sx / 2, -sy / 2, sx / 2, sy / 2)
        else:
            g = box(-sx / 2, -sy / 2, sx / 2, sy / 2)
        if shape == 'custom':
            parts = [g]
            prims = first(pd, 'primitives')
            for pr in (prims[1:] if prims else []):
                if not isinstance(pr, list) or not pr:
                    continue
                w = float((first(pr, 'width') or [0, 0])[1])
                if pr[0] == 'gr_poly':
                    p = pts_list(pr)
                    if len(p) >= 3:
                        parts.append(Polygon(p).buffer(w / 2 if w > 0 else 0))
                elif pr[0] == 'gr_line':
                    parts.append(LineString([xy(first(pr, 'start')), xy(first(pr, 'end'))]).buffer(max(w, 1e-3) / 2))
                elif pr[0] == 'gr_circle':
                    c, e = xy(first(pr, 'center')), xy(first(pr, 'end'))
                    parts.append(Point(c).buffer(math.dist(c, e) + w / 2))
                elif pr[0] == 'gr_rect':
                    (x1, y1), (x2, y2) = xy(first(pr, 'start')), xy(first(pr, 'end'))
                    parts.append(box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)).buffer(w / 2))
                elif pr[0] == 'gr_arc' and first(pr, 'mid'):
                    parts.append(LineString(arc_points(xy(first(pr, 'start')), xy(first(pr, 'mid')),
                                                       xy(first(pr, 'end')), 8)).buffer(max(w, 1e-3) / 2))
            g = unary_union(parts)
        return g

    def _footprint(self, fp):
        at = first(fp, 'at')
        fx, fy = xy(at)
        fr = float(at[3]) if len(at) > 3 else 0.0
        props = {p[1]: p[2] for p in kids(fp, 'property') if len(p) > 2}
        ref = props.get('Reference') or next((t[2] for t in kids(fp, 'fp_text') if len(t) > 2 and t[1] == 'reference'), '?')
        val = props.get('Value') or next((t[2] for t in kids(fp, 'fp_text') if len(t) > 2 and t[1] == 'value'), '')
        rec = dict(ref=ref, value=val, lib=fp[1] if len(fp) > 1 and isinstance(fp[1], str) else '',
                   layer=(first(fp, 'layer') or [None, 'F.Cu'])[1], x=fx, y=fy, pads=[])
        for pd in kids(fp, 'pad'):
            num = pd[1] if len(pd) > 1 and isinstance(pd[1], str) else ''
            kind = pd[2] if len(pd) > 2 and isinstance(pd[2], str) else 'smd'
            shape = pd[3] if len(pd) > 3 and isinstance(pd[3], str) else 'rect'
            pat = first(pd, 'at')
            px, py = xy(pat)
            pr = float(pat[3]) if len(pat) > 3 else 0.0      # absolute orientation in board files
            dx, dy = rot(px, py, fr)
            cx, cy = fx + dx, fy + dy
            poly = affinity.translate(affinity.rotate(self._pad_poly(pd, shape), -pr, origin=(0, 0)), cx, cy)
            layers = []
            for nm in (first(pd, 'layers') or ['layers'])[1:]:
                if nm == '*.Cu':
                    layers += self.cu
                elif nm == 'F&B.Cu':
                    layers += [self.cu[0], self.cu[-1]]
                elif nm in self.z:
                    layers.append(nm)
            dr = first(pd, 'drill')
            dv = [float(v) for v in (dr[1:] if dr else []) if isinstance(v, str) and re.match(r'^[\d.]+$', v)]
            p = dict(ref=ref, num=num, kind=kind, x=cx, y=cy, poly=poly, layers=sorted(set(layers), key=self.cu.index),
                     drill=min(dv) if dv else 0.0, net=self.net_of(pd), fp=rec)
            rec['pads'].append(p)
            self.pads.append(p)
        self.fps.append(rec)

    def _outline(self, tree):
        lines = []
        for g in tree:
            if not (isinstance(g, list) and g and g[0] in ('gr_line', 'gr_arc', 'gr_rect', 'gr_poly', 'gr_circle')):
                continue
            if (first(g, 'layer') or [None, ''])[1] != 'Edge.Cuts':
                continue
            if g[0] == 'gr_line':
                lines.append(LineString([xy(first(g, 'start')), xy(first(g, 'end'))]))
            elif g[0] == 'gr_arc' and first(g, 'mid'):
                lines.append(LineString(arc_points(xy(first(g, 'start')), xy(first(g, 'mid')), xy(first(g, 'end')), 16)))
            elif g[0] == 'gr_rect':
                (x1, y1), (x2, y2) = xy(first(g, 'start')), xy(first(g, 'end'))
                lines.append(box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)).exterior)
            elif g[0] == 'gr_poly':
                p = pts_list(g)
                lines.append(LineString(p + p[:1]))
            elif g[0] == 'gr_circle':
                (cx, cy), (ex, ey) = xy(first(g, 'center')), xy(first(g, 'end'))
                lines.append(Point(cx, cy).buffer(math.hypot(ex - cx, ey - cy), quad_segs=32).exterior)
        polys = list(polygonize(unary_union(lines))) if lines else []
        return max(polys, key=lambda p: p.area) if polys else None

    # ---------------------------------------------------------------- copper geometry
    def fp(self, ref):
        return next(f for f in self.fps if f['ref'] == ref)

    def other_copper(self, net, layer):
        parts = [LineString(t['pts']).buffer(t['w'] / 2, quad_segs=4) for t in self.tracks
                 if t['layer'] == layer and t['net'] != net]
        parts += [p['poly'] for p in self.pads if layer in p['layers'] and p['net'] != net]
        parts += [Point(v['x'], v['y']).buffer(v['size'] / 2, quad_segs=6) for v in self.vias
                  if layer in v['layers'] and v['net'] != net]
        return unary_union(parts) if parts else Polygon()

    def fill_report(self):
        """Per zone and layer: saved fill used as is, or outline approximation; flag overlaps (stale fill)."""
        lines, self.fill_approx = [], {}
        for zi, z in enumerate(self.zones):
            for ly in z['layers']:
                if ly in z['fills']:
                    ov = z['fills'][ly].intersection(self.other_copper(z['net'], ly)).area
                    tag = 'saved fill' + (f'; OVERLAPS other-net copper by {ov:.2f} mm2 (stale fill?)' if ov > 0.02 else '')
                    lines.append((z['net'], ly, z['outline'].area, z['fills'][ly].area, tag))
                else:
                    g = z['outline']
                    if self.outline is not None:
                        g = g.intersection(self.outline)
                    g = g.difference(self.other_copper(z['net'], ly).buffer(z['clearance']))
                    self.fill_approx[(zi, ly)] = g
                    lines.append((z['net'], ly, z['outline'].area, g.area, 'NO saved fill: outline minus clearance (approx.)'))
        return lines

    def copper(self, net, layer):
        """Union of the net's copper on a layer: zone fills, tracks, pads, and via pads where they are functional."""
        key = (net, layer)
        if key in self._geo:
            return self._geo[key]
        parts = []
        for zi, z in enumerate(self.zones):
            if z['net'] == net and layer in z['layers']:
                if layer in z['fills']:
                    parts.append(z['fills'][layer])
                elif (zi, layer) in getattr(self, 'fill_approx', {}):
                    parts.append(self.fill_approx[(zi, layer)])
        parts += [LineString(t['pts']).buffer(t['w'] / 2, quad_segs=4) for t in self.tracks
                  if t['net'] == net and t['layer'] == layer]
        base = unary_union(parts) if parts else Polygon()
        end = (self.cu[0], self.cu[-1])
        extra = []
        for p in self.pads:
            if p['net'] == net and layer in p['layers']:
                if p['kind'] != 'thru_hole' or layer in end or base.intersects(p['poly']):
                    extra.append(p['poly'])
        for v in self.vias:
            if v['net'] == net and layer in v['layers']:
                c = Point(v['x'], v['y']).buffer(v['size'] / 2, quad_segs=6)
                if layer in (v['layers'][0], v['layers'][-1]) or base.intersects(c):
                    extra.append(c)
        g = unary_union([base] + extra) if extra else base
        self._geo[key] = g
        return g

    def area(self, net):
        return sum(self.copper(net, ly).area for ly in self.cu)


# ============================================================================ roles
def infer_roles(b, args):
    """Read the board the way a reviewer would: names, values, footprints, adjacency. Returns a dict and a log."""
    L = []
    nets = sorted({p['net'] for p in b.pads if p['net']} | {t['net'] for t in b.tracks if t['net']}
                  | {z['net'] for z in b.zones})
    area = {n: b.area(n) for n in nets}
    gnds = [n for n in nets if GND_RE.search(n)]
    gnd = max(gnds, key=lambda n: area[n]) if gnds else max(nets, key=lambda n: area[n])
    L.append(f"ground: '{gnd}' (name matches GND, largest copper: {area[gnd]:.0f} mm2)")
    pwr = [n for n in nets if n != gnd and PWR_RE.search(n.split('/')[-1])]
    L.append("power rails by name: " + ", ".join(f"{n} ({area[n]:.0f} mm2)" for n in pwr))
    shunts = []
    for f in b.fps:
        if f['ref'][:1] == 'R' and len(f['pads']) == 2:
            ohm = parse_ohms(f['value'])
            nn = [p['net'] for p in f['pads']]
            if ohm is not None and ohm <= 0.2 and all(nn):
                shunts.append(dict(ref=f['ref'], ohm=ohm, nets=nn, fp=f))
    L.append("shunts (R <= 0.2 ohm from the value field): " + (", ".join(f"{s['ref']} {s['ohm'] * 1e3:.0f} mOhm "
                                                                     f"between {s['nets'][0]} and {s['nets'][1]}" for s in shunts) or 'none'))
    shunt_nets = {n for s in shunts for n in s['nets']}
    driver = None
    cands = []
    for f in b.fps:
        if f['ref'][:1] in 'UQ':
            fn = {p['net'] for p in f['pads']}
            score = len(fn & shunt_nets) * 10 + len(fn & set(pwr)) * 3 + (gnd in fn)
            if fn & set(pwr) and gnd in fn:
                cands.append((score, sum(1 for p in f['pads'] if p['net'] in set(pwr) | {gnd}), f))
    if args.driver:
        driver = b.fp(args.driver)
    elif cands:
        driver = max(cands, key=lambda t: (t[0], t[1]))[2]
    if driver is None:
        raise SystemExit("could not identify a power stage; pass --driver REF")
    dnets = {p['net'] for p in driver['pads']}

    def conn_rank(n):          # a supply rail arrives on a connector with few nets (power connector)
        cs = [len({p['net'] for p in f['pads']}) for f in b.fps if f['ref'][:1] in 'JPX'
              and any(p['net'] == n for p in f['pads']) and any(p['net'] == gnd for p in f['pads'])]
        return (min(cs) if cs else 999, -area[n])
    rail = min((n for n in dnets if n in pwr), key=conn_rank)
    L.append(f"driver: {driver['ref']} ({driver['value']}): pads on the rail '{rail}', on {gnd} "
             f"({sum(p['net'] == gnd for p in driver['pads'])} pads incl. exposed pad) and on "
             f"{len(dnets & shunt_nets)} shunt nets: this is the switching cell (integrated bridge)")
    phases = []
    for s in shunts:
        a, c = s['nets']
        if a not in dnets and c in dnets:
            a, c = c, a
        if a not in dnets:
            continue
        load = None
        for f in b.fps:
            if f['ref'][:1] in 'JPX' and any(p['net'] == c for p in f['pads']):
                load = f
        amp = None
        for f in b.fps:
            if f is not driver and f['ref'][:1] == 'U':
                fn = {p['net'] for p in f['pads']}
                if a in fn and c in fn:
                    amp = f
        phases.append(dict(shunt=s, net_in=a, net_out=c, load=load, amp=amp))
        L.append(f"phase via {s['ref']}: driver pin net '{a}' -> shunt -> '{c}' -> "
                 f"{load['ref'] + ' (' + load['value'] + ')' if load else 'no connector'}; sense amplifier "
                 f"{amp['ref'] + ' (' + amp['value'] + ')' if amp else 'none'} reads across the shunt (in-line phase sensing)")
    supplies = [f for f in b.fps if f['ref'][:1] in 'JPX' and any(p['net'] == rail for p in f['pads'])
                and any(p['net'] == gnd for p in f['pads'])]
    L.append("supply connectors (pads on the rail and ground): " + ", ".join(f"{f['ref']} ({f['value']})" for f in supplies)
             + ("; two of them carry the same rail: a daisy-chain bus passes through this board" if len(supplies) > 1 else ""))
    host = None
    others = [f for f in b.fps if f['ref'][:1] in 'JP' and f not in supplies
              and not any(f is ph['load'] for ph in phases) and any(p['net'] == gnd for p in f['pads'])]
    if others:
        host = max(others, key=lambda f: len({p['net'] for p in f['pads']}))
        L.append(f"host connector: {host['ref']} ({len({p['net'] for p in host['pads']})} nets incl. the sense outputs): "
                 f"its {gnd} pins are the reference the controller's ADC sees")
    decaps = []
    for f in b.fps:
        if f['ref'][:1] == 'C' and len(f['pads']) == 2 and {p['net'] for p in f['pads']} == {rail, gnd}:
            d = min(math.hypot(f['x'] - p['x'], f['y'] - p['y']) for p in driver['pads'] if p['net'] == rail)
            decaps.append((d, f))
    decaps.sort(key=lambda t: t[0])
    L.append("rail-ground capacitors by distance to the driver's rail pin: " + ", ".join(
        f"{f['ref']} {f['value']} {d:.1f} mm" for d, f in decaps))
    regs = []
    for n in pwr:
        if n == rail:
            continue
        pl = max((b.copper(n, ly).area for ly in b.cu), default=0)
        if b.outline is not None and pl > 0.3 * b.outline.area:
            src = [f for f in b.fps if f['ref'][:1] == 'U' and len(f['pads']) <= 8 and any(p['net'] == n for p in f['pads'])
                   and any(p['net'] in pwr and p['net'] != n for p in f['pads'])]
            if src and host and any(p['net'] == n for p in host['pads']):
                regs.append((n, src[0]))
                L.append(f"plane rail '{n}' ({pl:.0f} mm2 on one layer): regulator {src[0]['ref']} ({src[0]['value']}), "
                         f"exported through {host['ref']}")
    return dict(gnd=gnd, rail=rail, pwr=pwr, driver=driver, phases=phases, supplies=supplies, host=host,
                decaps=decaps, shunts=shunts, regs=regs, area=area), L


# ============================================================================ rasterization
def raster(geom, x0, y0, nx, ny, h, ss=3, fs=5):
    """Cell coverage (ny, nx) and face coverage fx (ny, nx-1), fy (ny-1, nx) by point sampling."""
    shapely.prepare(geom)
    sub = (np.arange(ss) + 0.5) / ss
    xs = (x0 + (np.arange(nx)[:, None] + sub[None, :]) * h).ravel()
    ys = (y0 + (np.arange(ny)[:, None] + sub[None, :]) * h).ravel()
    X, Y = np.meshgrid(xs, ys)
    cov = shapely.contains_xy(geom, X, Y).reshape(ny, ss, nx, ss).mean(axis=(1, 3))
    fsub = (np.arange(fs) + 0.5) / fs
    yf = (y0 + (np.arange(ny)[:, None] + fsub[None, :]) * h).ravel()
    xf = x0 + (np.arange(1, nx)) * h
    X, Y = np.meshgrid(xf, yf)
    fx = shapely.contains_xy(geom, X, Y).reshape(ny, fs, nx - 1).mean(axis=1)
    xg = (x0 + (np.arange(nx)[:, None] + fsub[None, :]) * h).ravel()
    yg = y0 + (np.arange(1, ny)) * h
    X, Y = np.meshgrid(xg, yg)
    fy = shapely.contains_xy(geom, X, Y).reshape(ny - 1, nx, fs).mean(axis=2)
    return cov, fx, fy


# ============================================================================ DC network
class Net:
    """A conductance network: nodes (cells, via barrels, electrodes) and branches."""

    def __init__(self):
        self.nn = 0
        self.nx_, self.ny_, self.nnet, self.nlay, self.nkind = [], [], [], [], []
        self.ba, self.bb, self.bg, self.bkind, self.bnet, self.blay, self.bmx, self.bmy, self.bw = ([] for _ in range(9))
        self.bname = {}
        self.grids = {}

    def add_nodes(self, x, y, net, lay, kind):
        k = len(x)
        ids = np.arange(self.nn, self.nn + k)
        self.nn += k
        self.nx_.append(np.asarray(x, float))
        self.ny_.append(np.asarray(y, float))
        self.nnet.append(np.full(k, net, object))
        self.nlay.append(np.full(k, lay, object))
        self.nkind.append(np.full(k, kind))
        return ids

    def add_br(self, a, b, g, kind, net, lay, mx, my, w=None):
        a, b, g = np.atleast_1d(a), np.atleast_1d(b), np.atleast_1d(np.asarray(g, float))
        k = len(a)
        start = sum(len(x) for x in self.ba)
        self.ba.append(a)
        self.bb.append(b)
        self.bg.append(np.broadcast_to(g, (k,)).copy())
        self.bkind.append(np.full(k, kind))
        self.bnet.append(np.full(k, net, object))
        self.blay.append(np.full(k, lay, object))
        self.bmx.append(np.broadcast_to(np.asarray(mx, float), (k,)).copy())
        self.bmy.append(np.broadcast_to(np.asarray(my, float), (k,)).copy())
        self.bw.append(np.broadcast_to(np.asarray(np.nan if w is None else w, float), (k,)).copy())
        return np.arange(start, start + k)

    def finalize(self):
        cat = np.concatenate
        self.x, self.y = cat(self.nx_), cat(self.ny_)
        self.node_net, self.node_lay, self.node_kind = cat(self.nnet), cat(self.nlay), cat(self.nkind)
        self.a, self.b, self.g = cat(self.ba).astype(np.int64), cat(self.bb).astype(np.int64), cat(self.bg)
        self.kind, self.net, self.lay = cat(self.bkind), cat(self.bnet), cat(self.blay)
        self.mx, self.my, self.w = cat(self.bmx), cat(self.bmy), cat(self.bw)
        self.nb = len(self.a)
        n = self.nn
        A = sp.coo_matrix((np.ones(self.nb), (self.a, self.b)), shape=(n, n))
        self.ncomp, self.comp = connected_components(A + A.T, directed=False)
        self.G = self.laplacian(np.ones(self.nb, bool))
        self._lu = {}

    def laplacian(self, active):
        a, b, g = self.a[active], self.b[active], self.g[active]
        n = self.nn
        return sp.coo_matrix((np.r_[g, g, -g, -g], (np.r_[a, b, a, b], np.r_[a, b, b, a])), shape=(n, n)).tocsr()

    def factor(self):
        t0 = tic()
        deg = np.asarray(abs(self.G).sum(1)).ravel()
        order = np.argsort(self.comp, kind='stable')
        bounds = np.searchsorted(self.comp[order], np.arange(self.ncomp + 1))
        self.cnodes = [order[bounds[c]:bounds[c + 1]] for c in range(self.ncomp)]
        self.lu, self.free, self.root = {}, {}, {}
        for c, nodes in enumerate(self.cnodes):
            if len(nodes) < 2:
                continue
            r = nodes[np.argmax(deg[nodes])]
            fr = nodes[nodes != r]
            self.root[c], self.free[c] = r, fr
            self.lu[c] = spla.splu(self.G[fr][:, fr].tocsc(), permc_spec='COLAMD')
        self.t_factor = tic() - t0

    def solve(self, S, comps=None):
        """Potentials for injections S (n x m, current INTO the copper); one grounded node per component."""
        S = np.asarray(S, float)
        one = S.ndim == 1
        S = S[:, None] if one else S
        Phi = np.zeros_like(S)
        cs = self.lu.keys() if comps is None else comps
        for c in cs:
            if c not in self.lu:
                continue
            nodes = self.cnodes[c]
            tot = S[nodes].sum(0)
            if np.any(np.abs(tot) > 1e-7 * max(1.0, np.abs(S).max())):
                raise ValueError(f"injections do not balance on component {c} ({len(nodes)} nodes): {tot}")
            fr = self.free[c]
            sub = S[fr]
            nz = np.any(sub != 0, axis=0)
            if nz.any():
                Phi[np.ix_(fr, np.nonzero(nz)[0])] = self.lu[c].solve(np.ascontiguousarray(sub[:, nz]))
        return Phi[:, 0] if one else Phi

    def currents(self, Phi):
        return self.g[:, None] * (Phi[self.a] - Phi[self.b]) if Phi.ndim == 2 else self.g * (Phi[self.a] - Phi[self.b])

    def reff(self, br, chunk=64):
        """Exact effective resistance across each branch in br (one solve per branch)."""
        out = np.zeros(len(br))
        for s0 in range(0, len(br), chunk):
            bb = br[s0:s0 + chunk]
            S = np.zeros((self.nn, len(bb)))
            S[self.a[bb], np.arange(len(bb))] += 1.0
            S[self.b[bb], np.arange(len(bb))] -= 1.0
            P = self.solve(S, comps={self.comp[self.a[k]] for k in bb})
            out[s0:s0 + chunk] = P[self.a[bb], np.arange(len(bb))] - P[self.b[bb], np.arange(len(bb))]
        return out

    def leverage_sketch(self, k=48, seed=3):
        """Johnson-Lindenstrauss estimate of rho_b = g_b R_eff(b) for all branches (Spielman-Srivastava)."""
        rng = np.random.default_rng(seed)
        Q = rng.choice([-1.0, 1.0], size=(self.nb, k)) / math.sqrt(k)
        sg = np.sqrt(self.g)
        R = np.zeros((self.nn, k))
        np.add.at(R, self.a, sg[:, None] * Q)
        np.add.at(R, self.b, -sg[:, None] * Q)
        Y = self.solve(R)
        return self.g * ((Y[self.a] - Y[self.b]) ** 2).sum(1)

    def woodbury(self, B, Phi_p, Phi_q):
        """Exact change of Z_qp = s_q' G^+ s_p when the branch set B is removed (inf if it disconnects)."""
        B = np.asarray(B)
        k = len(B)
        S = np.zeros((self.nn, k))
        S[self.a[B], np.arange(k)] += 1.0
        S[self.b[B], np.arange(k)] -= 1.0
        P = self.solve(S, comps={self.comp[self.a[x]] for x in B})
        RBB = P[self.a[B]] - P[self.b[B]]
        M = np.diag(1.0 / self.g[B]) - RBB
        vp = Phi_p[self.a[B]] - Phi_p[self.b[B]]
        vq = Phi_q[self.a[B]] - Phi_q[self.b[B]]
        sol = np.linalg.lstsq(M, vp, rcond=1e-13)[0]
        if np.linalg.norm(M @ sol - vp) > 1e-6 * max(np.linalg.norm(vp), 1e-30):
            return np.inf             # the set is a cut for this source: removal disconnects it
        return float(vq @ sol)


def build_dc(b, nets, hnet, log_lines):
    """Rasterize the given nets (own grid each), add vias/THT barrels; returns the network and raster info."""
    N = Net()
    N.rasters = {}
    for net in nets:
        h = hnet[net]
        geoms = {ly: b.copper(net, ly) for ly in b.cu}
        geoms = {ly: g for ly, g in geoms.items() if not g.is_empty}
        if not geoms:
            continue
        bx = np.array([g.bounds for g in geoms.values()])
        x0 = math.floor(bx[:, 0].min() / h - 1) * h
        y0 = math.floor(bx[:, 1].min() / h - 1) * h
        nx = int(math.ceil((bx[:, 2].max() - x0) / h)) + 2
        ny = int(math.ceil((bx[:, 3].max() - y0) / h)) + 2
        for ly, g in geoms.items():
            cov, fx, fy = raster(g, x0, y0, nx, ny, h)
            mem = cov > 0
            mem[:, :-1] |= fx > 0
            mem[:, 1:] |= fx > 0
            mem[:-1, :] |= fy > 0
            mem[1:, :] |= fy > 0
            jj, ii = np.nonzero(mem)
            ids = -np.ones((ny, nx), np.int64)
            ids[jj, ii] = N.add_nodes(x0 + (ii + 0.5) * h, y0 + (jj + 0.5) * h, net, ly, 0)
            rs = b.rs[ly]
            a_, b_ = ids[:, :-1], ids[:, 1:]
            m = (fx > 0) & (a_ >= 0) & (b_ >= 0)
            jm, im = np.nonzero(m)
            N.add_br(a_[m], b_[m], fx[m] / rs, 0, net, ly, x0 + (im + 1) * h, y0 + (jm + 0.5) * h, fx[m] * h)
            a_, b_ = ids[:-1, :], ids[1:, :]
            m = (fy > 0) & (a_ >= 0) & (b_ >= 0)
            jm, im = np.nonzero(m)
            N.add_br(a_[m], b_[m], fy[m] / rs, 1, net, ly, x0 + (im + 0.5) * h, y0 + (jm + 1) * h, fy[m] * h)
            N.rasters[(net, ly)] = dict(x0=x0, y0=y0, nx=nx, ny=ny, h=h, ids=ids, cov=cov, fx=fx, fy=fy)
        N.grids[net] = (x0, y0, nx, ny, h)
    # via and through-hole barrels
    N.vias = []
    barrels = [dict(x=v['x'], y=v['y'], net=v['net'], layers=v['layers'], d=v['drill'], r_pad=v['size'] / 2, kind='via', src=v)
               for v in b.vias if v['net'] in N.grids]
    for p in b.pads:
        if p['kind'] == 'thru_hole' and p['drill'] > 0 and p['net'] in N.grids and len(p['layers']) > 1:
            barrels.append(dict(x=p['x'], y=p['y'], net=p['net'], layers=p['layers'], d=p['drill'],
                                r_pad=p['drill'] / 2 + 0.1, kind='pth', src=p))
    for bv in barrels:
        net, h = bv['net'], hnet[bv['net']]
        lys = bv['layers']
        bids = N.add_nodes([bv['x']] * len(lys), [bv['y']] * len(lys), net, 'barrel', 1)
        segs = []
        for k in range(len(lys) - 1):
            dz = (b.z[lys[k + 1]] - b.z[lys[k]]) * 1e-3
            r = RHO_CU * dz / (math.pi * (bv['d'] * 1e-3 + T_PLATE) * T_PLATE)
            segs.append(N.add_br(bids[k], bids[k + 1], 1.0 / r, 2, net, 'barrel', bv['x'], bv['y'])[0])
        rb = bv['d'] / 2 + T_PLATE * 1e3
        contacts = 0
        for k, ly in enumerate(lys):
            R = N.rasters.get((net, ly))
            if R is None:
                continue
            ic = (bv['x'] - R['x0']) / h - 0.5
            jc = (bv['y'] - R['y0']) / h - 0.5
            rad = max(rb, 0.75 * h) / h
            i0, i1 = int(math.floor(ic - rad - 1)), int(math.ceil(ic + rad + 1))
            j0, j1 = int(math.floor(jc - rad - 1)), int(math.ceil(jc + rad + 1))
            sel = []
            for j in range(max(0, j0), min(R['ny'], j1 + 1)):
                for i in range(max(0, i0), min(R['nx'], i1 + 1)):
                    if R['ids'][j, i] >= 0 and math.hypot(i - ic, j - jc) <= rad:
                        sel.append(R['ids'][j, i])
            if sel:
                N.add_br(np.full(len(sel), bids[k]), np.array(sel), 200.0 / b.rs[ly], 3, net, ly, bv['x'], bv['y'])
                contacts += 1
        N.vias.append(dict(bv, segs=segs, nodes=bids, contacts=contacts))
    return N


def pad_cells(N, b, pad, net=None):
    """Node ids of the cells under a pad (all its modelled layers)."""
    net = net or pad['net']
    out = []
    for ly in pad['layers']:
        R = N.rasters.get((net, ly))
        if R is None:
            continue
        h = R['h']
        x0, y0, x1, y1 = pad['poly'].bounds
        i0, i1 = max(0, int((x0 - R['x0']) / h) - 1), min(R['nx'], int((x1 - R['x0']) / h) + 2)
        j0, j1 = max(0, int((y0 - R['y0']) / h) - 1), min(R['ny'], int((y1 - R['y0']) / h) + 2)
        if i1 <= i0 or j1 <= j0:
            continue
        ii, jj = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1))
        xs, ys = R['x0'] + (ii + 0.5) * h, R['y0'] + (jj + 0.5) * h
        inside = shapely.contains_xy(pad['poly'], xs, ys) & (R['ids'][jj, ii] >= 0)
        sel = R['ids'][jj[inside], ii[inside]]
        if len(sel) == 0:
            d = np.hypot(xs - pad['x'], ys - pad['y'])
            d[R['ids'][jj, ii] < 0] = np.inf
            if np.isfinite(d.min()) and d.min() < 2 * h:
                k = np.unravel_index(np.argmin(d), d.shape)
                sel = np.array([R['ids'][jj[k], ii[k]]])
        out.append((ly, sel))
    return out


class Terminals:
    """Equipotential electrodes for pads and pad groups, added to a network before finalize()."""

    def __init__(self, N, b):
        self.N, self.b, self.pad_node, self.group = N, b, {}, {}

    def pad(self, p):
        key = id(p)
        if key in self.pad_node:
            return self.pad_node[key]
        cells = pad_cells(self.N, self.b, p)
        nid = self.N.add_nodes([p['x']], [p['y']], p['net'], 'electrode', 2)[0]
        nlinks = 0
        for ly, sel in cells:
            if len(sel):
                self.N.add_br(np.full(len(sel), nid), sel, 500.0 / self.b.rs[ly], 4, p['net'], ly, p['x'], p['y'])
                nlinks += len(sel)
        if nlinks == 0:
            raise ValueError(f"pad {p['ref']}.{p['num']} ({p['net']}) has no copper cells")
        self.pad_node[key] = nid
        return nid

    def group_of(self, name, pads):
        if name in self.group:
            return self.group[name]
        if len(pads) == 1:
            nid = self.pad(pads[0])
        else:
            nid = self.N.add_nodes([np.mean([p['x'] for p in pads])], [np.mean([p['y'] for p in pads])],
                                   pads[0]['net'], 'electrode', 2)[0]
            for p in pads:
                self.N.add_br(nid, self.pad(p), 1e6, 4, p['net'], 'group', p['x'], p['y'])
        self.group[name] = nid
        return nid


