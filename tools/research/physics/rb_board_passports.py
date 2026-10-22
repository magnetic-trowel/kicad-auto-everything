# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Conductor passports on a real KiCad board: what each piece of copper is doing.

Round 3, real-board conductor understanding (prefix rb). Applies the round-2 lens CD
passport (docs/topics/physics/lens-cd.md) to a routed .kicad_pcb instead of a synthetic
board. Report: docs/topics/physics/real-board-passports.md.

Pipeline (no KiCad needed; reads the saved file):
  1. Parse nets, stackup, footprints/pads (rect, roundrect, oval, circle, custom), tracks
     (incl. KiCad 9 mask-opening tracks), arcs, vias and zones. Zone fills: the saved
     filled_polygon is used; a zone with no fill on a layer is approximated by its outline
     minus other-net copper (flagged); fills overlapping other-net copper are flagged stale.
  2. Infer roles from net names, values and footprints (printed as a log; --driver overrides):
     ground, rails, shunts (R <= 0.2 ohm), the driver IC that feeds them (or a regulator that
     drives an inductor), its bridge-return pins (ground pins next to the supply pin), the load
     connector, supply connectors, sense amplifiers across each shunt, the host connector, decaps.
  3. DC conductor model: each power-relevant net is rasterized on its own grid (cell and face
     coverage by supersampling; 0.05 mm for small nets, 0.2 mm for planes); vias and plated
     holes are barrels (rho*l/(pi*(d+t)*t), t = 20 um) contacting the cells they pierce;
     terminal pads are equipotential electrodes, except shunt pads, which stay bare copper with
     the resistive element attached along their facing edges (so Kelvin quality is computed).
     One sparse LU per connected component.
  4. DC passports: per-source shares, I^2R attribution, current density, exact removal costs
     (rank-1 dZ_qp = i_p i_q / (g (1 - rho)); Woodbury for sets), leverage rho (exact for
     selected pieces, Johnson-Lindenstrauss sketch for all), dead copper, and common impedance
     at quiet ports (shunt Kelvin taps; amplifier ground vs host ground) with Tellegen
     attribution, its cancellation index chi, and an outer-edge-tap counterfactual.
  5. HF (inductive limit) hot-loop passport, stack-local magnetostatic model: every copper
     layer in a window round the driver is a sheet, plus a component layer 0.3 mm above the
     parts' side that carries the part current paths (die leads, capacitor bodies), so all
     loop current is sheet current. Energy per face = (mu0/2) sum_g h_g H_g^2 with H_g the
     cumulative sheet current above gap g minus half the net stack current (parallel-plate
     limit; a plane of any net images what is above and below it). Driven by an EMF across
     the die's supply lead; ESL is a series term on a cut of each capacitor body. Gives loop L,
     energy by gap, current by layer and net, per-via shares with exact Woodbury removal
     values, exact Thevenin values for one added ground via at every legal site, the
     no-plane and swapped-plane counterfactuals, and the DC-vs-HF share of each via.
  6. Switch-node charge to whom (parallel-plate C of the phase copper to adjacent layers).
  7. Floors (lens VP): Beckmann R >= R_s*d^2/A per phase pour, and a joint convex floor for
     the pours sharing the region round the driver (Frank-Wolfe on the relaxed density with a
     per-cell sum <= 1 and a total-area budget; the FW gap certifies the bound).

Model limits: quasi-static. DC is exact for the rasterized geometry (saved fills, stackup
copper thickness, 20 C copper, no solder, no lead-frame or package resistance). The HF model
is local: no lateral fringing, so narrow strips over a plane are over-estimated (x1.5 at
w/h = 5, about x3 at w/h = 1; plane-pair via spreading is exact); lossless (perfect
conductors, valid above the plane's imaging frequency, ~1 MHz here); part current paths and
the outer field (--h-out) are crude; use it for shares, rankings and relative changes.

Usage:
  python -I rb_board_passports.py BOARD.kicad_pcb [--current 1.0] [--h-small 0.05]
         [--h-plane 0.2] [--h-hf 0.15] [--quick] [--no-hf] [--no-floor] [--sketch 48]
Runtime on the bldcpower board (32 mm round, 4 layers; 111k DC nodes, 73k HF sheet cells): about 50 s on
one core, peak memory 2.2 GB with the default grids; --quick about 15 s and 0.7 GB; --no-hf 20 s, 0.6 GB.
OMP_NUM_THREADS=1 is set here. Deterministic (fixed seeds). Also runs on boards whose power stage is a
regulator driving an inductor (the switch node is then the 'phase'); on the other two test boards it takes
5-30 s.
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

        def tlayer(node):           # (layer "F.Cu"), or (layers "B.Cu" "B.Mask") for a track with a mask opening
            ly = first(node, 'layer')
            if ly:
                return ly[1], False
            lys = (first(node, 'layers') or ['layers'])[1:]
            return next((n for n in lys if n.endswith('.Cu')), None), any(n.endswith('.Mask') for n in lys)
        for s in kids(tree, 'segment'):
            ly, exposed = tlayer(s)
            self.tracks.append(dict(layer=ly, net=self.net_of(s), w=float(first(s, 'width')[1]), exposed=exposed,
                                    pts=[xy(first(s, 'start')), xy(first(s, 'end'))]))
        for a in kids(tree, 'arc'):
            ly, exposed = tlayer(a)
            self.tracks.append(dict(layer=ly, net=self.net_of(a), w=float(first(a, 'width')[1]), exposed=exposed,
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
                     drill=min(dv) if dv else 0.0, net=self.net_of(pd), fp=rec,
                     pinfunction=(first(pd, 'pinfunction') or [None, ''])[1],
                     pintype=(first(pd, 'pintype') or [None, ''])[1])
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
    L.append("shunts (R <= 0.2 ohm from the value field): " + (", ".join(
        f"{s['ref']} {s['ohm'] * 1e3:.0f} mOhm between {s['nets'][0]} and {s['nets'][1]}" for s in shunts) or 'none'))
    shunt_nets = {n for s in shunts for n in s['nets']}
    inductors = []
    for f in b.fps:
        if f['ref'][:1] == 'L' and len(f['pads']) == 2 and all(p['net'] for p in f['pads']):
            for k in (0, 1):
                sw, out = f['pads'][k]['net'], f['pads'][1 - k]['net']
                ics = [g for g in b.fps if g['ref'][:1] in 'UQ' and any(p['net'] == sw for p in g['pads'])]
                if sw != gnd and sw not in pwr and ics:
                    inductors.append(dict(L=f, sw=sw, out=out, ic=ics[0]))
                    break
    if inductors:
        L.append("inductors driven by an IC (switch nodes): " + ", ".join(
            f"{d['L']['ref']} {d['L']['value']}: {d['ic']['ref']} ({d['ic']['value']}) '{d['sw']}' -> '{d['out']}'" for d in inductors))
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
    elif cands and shunts:
        driver = max(cands, key=lambda t: (t[0], t[1]))[2]
    elif inductors:
        def has_rail(ic):
            return any(p['net'] in pwr or (p['net'] and p['net'] != gnd and sum(
                1 for f in b.fps if f['ref'][:1] == 'C' and {q['net'] for q in f['pads']} == {p['net'], gnd}) > 0)
                for p in ic['pads'] if p['net'] not in {d['sw'] for d in inductors})
        inductors.sort(key=lambda d: (d['ic']['ref'][:1] != 'U', not has_rail(d['ic'])))
        driver = inductors[0]['ic']
    elif cands:
        driver = max(cands, key=lambda t: (t[0], t[1]))[2]
    if driver is None:
        raise SystemExit("could not identify a power stage; pass --driver REF")
    dnets = {p['net'] for p in driver['pads']}
    swn = {d['sw'] for d in inductors if d['ic'] is driver}

    def ncaps(n):                # capacitors from this net to ground: an input rail is decoupled
        return sum(1 for f in b.fps if f['ref'][:1] == 'C' and len(f['pads']) == 2
                   and {p['net'] for p in f['pads']} == {n, gnd})

    def conn_rank(n):          # a supply rail arrives on a connector with few nets (power connector)
        cs = [len({p['net'] for p in f['pads']}) for f in b.fps if f['ref'][:1] in 'JPX'
              and any(p['net'] == n for p in f['pads']) and any(p['net'] == gnd for p in f['pads'])]
        return (min(cs) if cs else 999, -area[n])
    railc = [n for n in dnets if n in pwr and n not in swn] or \
        [n for n in dnets if n and n != gnd and n not in swn and ncaps(n) > 0
         and not re.search(r'FB|BS|BOOT|EN|COMP|SS|PG|ILIM|RT', n.split('/')[-1], re.I)]
    if not railc:
        raise SystemExit(f"could not identify the supply rail of {driver['ref']}; pass --driver REF")
    rail = min(railc, key=lambda n: (conn_rank(n)[0] if n in pwr else 500, -ncaps(n), -area[n]))
    gpads = [p for p in driver['pads'] if p['net'] == gnd]
    epad = max(gpads, key=lambda p: p['poly'].area) if gpads else None
    foot = [p for p in gpads if p is not epad and min(math.hypot(p['x'] - q['x'], p['y'] - q['y'])
                                                     for q in driver['pads'] if q['net'] == rail) <= 1.0]
    kind = ('the switching cell (integrated bridge with shunt-sensed outputs)' if dnets & shunt_nets else
             'the switching cell (regulator driving an inductor)' if swn else 'the main power consumer (no switch node found)')
    L.append(f"driver: {driver['ref']} ({driver['value']}): pads on the rail '{rail}', on {gnd} "
             f"({sum(p['net'] == gnd for p in driver['pads'])} pads) and on {len(dnets & shunt_nets)} shunt nets"
             f"{', switch node ' + ', '.join(swn) if swn else ''}: {kind}")
    if foot:
        L.append(f"bridge return pins: {', '.join(driver['ref'] + '.' + p['num'] for p in foot)} (ground pins next to the supply pin:"
                 f" the low-side current leaves the package there; taken as the DC return terminal and the HF die return)")
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
    if not phases:
        for d in inductors:
            if d['ic'] is driver:
                pl = next(p for p in d['L']['pads'] if p['net'] == d['sw'])
                phases.append(dict(shunt=None, net_in=d['sw'], net_out=d['out'], load=None, amp=None, inductor=d['L'], lpad=pl))
                L.append(f"switch node '{d['sw']}': {driver['ref']} pin -> {d['L']['ref']} ({d['L']['value']}) -> '{d['out']}'")
    supplies = [f for f in b.fps if f['ref'][:1] in 'JPX' and not f['ref'].startswith('PS') and any(p['net'] == rail for p in f['pads'])
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
                decaps=decaps, shunts=shunts, regs=regs, area=area, foot=foot, epad=epad), L


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
    permc = 'COLAMD'          # column ordering for splu; callers may choose 'MMD_AT_PLUS_A' (less fill on big boards)

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

    def xy_of(self, ids):
        """Node coordinates (works before finalize())."""
        x, y = np.concatenate(self.nx_), np.concatenate(self.ny_)
        return x[ids], y[ids]

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
            self.lu[c] = spla.splu(self.G[fr][:, fr].tocsc(), permc_spec=self.permc)
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




def add_shunt_body(N, b, s, pa, pb, h):
    """Resistive element of a 2-terminal shunt as parallel strips attached along the pads' facing (inner) edges.

    The pad copper itself stays ordinary copper (bare: solder and terminations in parallel are ignored, the
    worst case), so a sense tap anywhere on or near a pad sees the real copper drop. Returns the strip branches."""
    ca, cb = np.array([pa['x'], pa['y']]), np.array([pb['x'], pb['y']])
    u = (cb - ca) / np.linalg.norm(cb - ca)
    v = np.array([-u[1], u[0]])
    side = []
    for p, c, sgn in ((pa, ca, 1.0), (pb, cb, -1.0)):
        ids = np.concatenate([sel for ly, sel in pad_cells(N, b, p) if len(sel)])
        xy_ = np.stack(N.xy_of(ids), 1) - c
        sa, ta = xy_ @ (sgn * u), xy_ @ v
        inner = sa >= sa.max() - max(0.12, 1.5 * h)
        side.append((ids[inner], ta[inner]))
    lo = max(side[0][1].min(), side[1][1].min())
    hi = min(side[0][1].max(), side[1][1].max())
    nbins = max(4, int(round((hi - lo) / max(h, 0.1))))
    edges = np.linspace(lo - 1e-9, hi + 1e-9, nbins + 1)
    pairs = []
    for k in range(nbins):
        sel = [ids[(t >= edges[k]) & (t < edges[k + 1])] for ids, t in side]
        if len(sel[0]) and len(sel[1]):
            nodes = []
            for ids_, p in zip(sel, (pa, pb)):
                xs_, ys_ = N.xy_of(ids_)
                nd = N.add_nodes([float(xs_.mean())], [float(ys_.mean())], p['net'], 'electrode', 2)[0]
                N.add_br(np.full(len(ids_), nd), ids_, 500.0 / b.rs[p['layers'][0]], 4, p['net'], p['layers'][0], p['x'], p['y'])
                nodes.append(nd)
            pairs.append(nodes)
    m = len(pairs)
    out = []
    for na, nb_ in pairs:
        k = N.add_br(na, nb_, 1.0 / (s['ohm'] * m), 5, 'lumped', 'lumped', s['fp']['x'], s['fp']['y'])[0]
        N.bname[k] = s['ref']
        out.append(k)
    # outer-edge midpoints of both pads (where a non-Kelvin tap would sit), for the counterfactual
    outer = []
    for p, c, sgn in ((pa, ca, -1.0), (pb, cb, 1.0)):
        ids = np.concatenate([sel for ly, sel in pad_cells(N, b, p) if len(sel)])
        xy_ = np.stack(N.xy_of(ids), 1) - c
        sa = xy_ @ (sgn * u)
        ta = np.abs(xy_ @ v)
        score = sa - 0.5 * ta
        outer.append(int(ids[np.argmax(score)]))
    return out, [q[0] for q in pairs], [q[1] for q in pairs], outer


# ============================================================================ HF stack model
RIGID = 1e13          # 1/H: a 0.1 pH link (vias, electrodes)


def stack_A(nl):
    """Field in the nl+1 regions (above, gaps, below) from layer sheet currents: H_r = sum_{l<r} K_l - sum_l K_l / 2.

    The symmetric outer split is the field of the net stack current; a pure parallel-plate (difference) mode
    therefore has no field outside the stack, as for large plates."""
    T = np.zeros((nl + 1, nl))
    for r in range(nl + 1):
        T[r, :r] = 1.0
    return T - 0.5


def stack_M(gaps_mm, h_out):
    """Per-face energy matrix (H): E = 1/2 I' M I for face currents I on all layers (parallel-plate limit)."""
    nl = len(gaps_mm) + 1
    w = np.array([h_out] + list(gaps_mm) + [h_out]) * 1e-3
    A = stack_A(nl)
    return MU0 * A.T @ np.diag(w) @ A, w


class StackRaster:
    """All copper of all nets in a window on one grid: owning net per cell and face coverage, per layer.

    With bodies, a virtual component layer is put h_comp above the top copper: it carries the current paths of
    lumped parts (capacitor bodies, the driver's supply lead and paddle), so that every current in the loop is a
    sheet current that the planes can image (no current 'jumps' between pads)."""

    def __init__(self, b, window, h, nets_all, bodies=(), h_comp=0.3, side='top'):
        x0, y0, x1, y1 = window
        self.x0, self.y0, self.h = x0, y0, h
        self.nx, self.ny = int(round((x1 - x0) / h)), int(round((y1 - y0) / h))
        self.off = 1 if bodies else 0
        order = list(b.cu) if side == 'top' else list(reversed(b.cu))     # the stack seen from the parts' side
        self.layers = (['COMP'] if bodies else []) + order
        nl = self.nl = len(self.layers)

        def gap(u, v):
            return b.gap.get((u, v), b.gap.get((v, u)))
        self.gaps = ([h_comp] if bodies else []) + [gap(order[i], order[i + 1]) for i in range(len(order) - 1)]
        self.er = ([1.0] if bodies else []) + [b.er.get((order[i], order[i + 1]), b.er.get((order[i + 1], order[i]), 4.5))
                                                 for i in range(len(order) - 1)]
        wbox = box(x0, y0, x1, y1)
        items = [(net, ly, None) for net in nets_all for ly in b.cu] + [(name, 'COMP', g) for name, g in bodies]
        self.nets, subs = [], []
        best = np.zeros((nl, self.ny, self.nx))
        self.owner = -np.ones((nl, self.ny, self.nx), np.int64)
        for net, ly, g in items:
            g = b.copper(net, ly) if g is None else g
            if g.is_empty or not g.intersects(wbox):
                continue
            g = g.intersection(wbox.buffer(h))
            if g.is_empty or g.area < 1e-6:
                continue
            li = self.layers.index(ly)
            gx0, gy0, gx1, gy1 = g.bounds
            i0, i1 = max(0, int(math.floor((gx0 - x0) / h)) - 1), min(self.nx, int(math.ceil((gx1 - x0) / h)) + 1)
            j0, j1 = max(0, int(math.floor((gy0 - y0) / h)) - 1), min(self.ny, int(math.ceil((gy1 - y0) / h)) + 1)
            if i1 - i0 < 2 or j1 - j0 < 2:
                continue
            cov, fx, fy = raster(g, x0 + i0 * h, y0 + j0 * h, i1 - i0, j1 - j0, h, ss=3, fs=4)
            if net not in self.nets:
                self.nets.append(net)
            ni = self.nets.index(net)
            blk = best[li, j0:j1, i0:i1]
            upd = cov > blk
            self.owner[li, j0:j1, i0:i1][upd] = ni
            blk[upd] = cov[upd]
            subs.append((li, ni, j0, j1, i0, i1, fx, fy))
        self.FX = np.zeros((nl, self.ny, self.nx - 1))
        self.FY = np.zeros((nl, self.ny - 1, self.nx))
        for li, ni, j0, j1, i0, i1, fx, fy in subs:
            o = self.owner[li, j0:j1, i0:i1] == ni
            sx = self.FX[li, j0:j1, i0:i1 - 1]
            okx = o[:, :-1] & o[:, 1:]
            sx[okx] = fx[okx]
            sy = self.FY[li, j0:j1 - 1, i0:i1]
            oky = o[:-1, :] & o[1:, :]
            sy[oky] = fy[oky]

    def xy(self, j, i):
        return self.x0 + (i + 0.5) * self.h, self.y0 + (j + 0.5) * self.h

    def cells_of(self, li, net):
        if net not in self.nets:
            return np.zeros(0, int), np.zeros(0, int)
        return np.nonzero(self.owner[li] == self.nets.index(net))


def assemble_stack(sr, h_out, drop_layers=(), special=None):
    """Coupled sheet Laplacian (1/H): per face location, the layers present couple through M^-1.

    special: {(axis, j, i): dict(emf=bool, L=extra)} for faces of the component layer (layer 0): an EMF face
    drives the loop (Norton injections into every layer present there); L adds a series self-inductance (ESL)."""
    nl = sr.nl
    special = special or {}
    owner, FX, FY = sr.owner.copy(), sr.FX.copy(), sr.FY.copy()
    for li in drop_layers:
        owner[li], FX[li], FY[li] = -1, 0.0, 0.0
    ids = -np.ones(owner.shape, np.int64)
    m = owner >= 0
    n = int(m.sum())
    ids[m] = np.arange(n)
    M, w = stack_M(sr.gaps, h_out)
    rows, cols, vals, adj, faces, spec = [], [], [], [], [], []

    def emit(S, Y, na, nb):
        for p in range(len(S)):
            adj.append(np.stack([na[p], nb[p]], 1))
            for q in range(len(S)):
                y = Y[p, q]
                rows.extend([na[p], nb[p], na[p], nb[p]])
                cols.extend([na[q], nb[q], nb[q], na[q]])
                vals.extend([y, y, -y, -y])
    for axis, F in ((0, FX), (1, FY)):
        code = np.zeros(F.shape[1:], np.int64)
        for li in range(nl):
            code |= (F[li] > 0).astype(np.int64) << li
        sk = [(j, i) for (ax, j, i) in special if ax == axis]
        smask = np.zeros(F.shape[1:], bool)
        for j, i in sk:
            smask[j, i] = True
        for c in np.unique(code):
            if c == 0:
                continue
            S = [li for li in range(nl) if c >> li & 1]
            Minv = np.linalg.inv(M[np.ix_(S, S)])
            jj, ii = np.nonzero((code == c) & ~smask)
            if not len(jj):
                continue
            f = np.stack([F[li][jj, ii] for li in S])
            jb, ib = (jj, ii + 1) if axis == 0 else (jj + 1, ii)
            na = np.stack([ids[li, jj, ii] for li in S])
            nb = np.stack([ids[li, jb, ib] for li in S])
            sf = np.sqrt(f)
            emit(S, Minv[:, :, None] * sf[:, None, :] * sf[None, :, :], na, nb)
            faces.append((axis, S, jj, ii, f, Minv, na, nb))
        for j, i in sk:
            c = code[j, i]
            S = [li for li in range(nl) if c >> li & 1]
            if 0 not in S:
                continue
            f = np.array([F[li][j, i] for li in S])
            Meff = M[np.ix_(S, S)] / np.sqrt(np.outer(f, f))
            Meff[0, 0] += special[(axis, j, i)].get('L', 0.0)
            Y = np.linalg.inv(Meff)
            jb, ib = (j, i + 1) if axis == 0 else (j + 1, i)
            na = np.array([[ids[li, j, i]] for li in S])
            nb = np.array([[ids[li, jb, ib]] for li in S])
            emit(S, Y[:, :, None], na, nb)
            spec.append(dict(axis=axis, j=j, i=i, S=S, Y=Y, f=f, na=na[:, 0], nb=nb[:, 0], **special[(axis, j, i)]))
    G = sp.coo_matrix((np.concatenate([np.ravel(v) for v in vals]),
                       (np.concatenate([np.ravel(r) for r in rows]), np.concatenate([np.ravel(c) for c in cols]))),
                      shape=(n, n)).tocsr()
    return dict(G=G, ids=ids, owner=owner, n=n, faces=faces, spec=spec, adj=np.concatenate(adj), M=M, w=w, nl=nl, sr=sr)


def face_flows(st, phi):
    out = []
    for axis, S, jj, ii, f, Minv, na, nb in st['faces']:
        sf = np.sqrt(f)
        I = sf * (Minv @ (sf * (phi[na] - phi[nb])))
        out.append((axis, S, jj, ii, I, f))
    return out


def special_flows(st, phi, E=1.0):
    """Face currents at the special faces (EMF faces subtract the EMF in their component-layer entry)."""
    out = []
    for sf in st['spec']:
        d = phi[sf['na']] - phi[sf['nb']]
        if sf.get('emf'):
            d = d.copy()
            d[0] -= E
        out.append((sf, sf['Y'] @ d))
    return out


def gap_energy(st, flows, sflows=()):
    """Inductance x I^2 (H A^2) stored in each region (above, gaps, below), and in the extra series inductances."""
    A = stack_A(st['nl'])
    E = np.zeros(st['nl'] + 1)
    for axis, S, jj, ii, I, f in flows:
        Ip = np.zeros((st['nl'], I.shape[1]))
        Ip[S] = I / np.sqrt(f)
        H = A @ Ip
        E += MU0 * (st['w'][:, None] * H * H).sum(1)
    El = 0.0
    for sf, I in sflows:
        Ip = np.zeros(st['nl'])
        Ip[sf['S']] = I / np.sqrt(sf['f'])
        H = A @ Ip
        E += MU0 * st['w'] * H * H
        El += sf.get('L', 0.0) * I[0] ** 2
    return E, El


class StackSolver:
    """Lumped links (vias, electrodes, capacitors) on a stack Laplacian; one grounded node per conductor island."""

    def __init__(self, st):
        self.st, self.extra, self.n_extra = st, [], 0

    def node(self):
        self.n_extra += 1
        return self.st['n'] + self.n_extra - 1

    def link(self, a, b_, y, tag):
        self.extra.append((int(a), int(b_), float(y), tag))
        return len(self.extra) - 1

    def cell(self, li, x, y):
        sr = self.st['sr']
        i, j = int(math.floor((x - sr.x0) / sr.h)), int(math.floor((y - sr.y0) / sr.h))
        if 0 <= i < sr.nx and 0 <= j < sr.ny:
            return int(self.st['ids'][li, j, i]), int(self.st['owner'][li, j, i])
        return -1, -1

    def pad_cells(self, p, buf=0.3):
        sr, st = self.st['sr'], self.st
        if p['net'] not in sr.nets:
            return []
        ni = sr.nets.index(p['net'])
        out = []
        for ly in p['layers']:
            li = sr.layers.index(ly)
            x0, y0, x1, y1 = p['poly'].bounds
            i0, i1 = max(0, int((x0 - sr.x0) / sr.h) - 1), min(sr.nx, int((x1 - sr.x0) / sr.h) + 2)
            j0, j1 = max(0, int((y0 - sr.y0) / sr.h) - 1), min(sr.ny, int((y1 - sr.y0) / sr.h) + 2)
            if i1 <= i0 or j1 <= j0:
                continue
            ii, jj = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1))
            xs, ys = sr.x0 + (ii + 0.5) * sr.h, sr.y0 + (jj + 0.5) * sr.h
            ok = shapely.contains_xy(p['poly'].buffer(buf * sr.h), xs, ys) & (st['owner'][li, jj, ii] == ni)
            out += [(li, int(j_), int(i_)) for j_, i_ in zip(jj[ok], ii[ok])]
        return out

    def finalize(self):
        st = self.st
        n = st['n'] + self.n_extra
        G = st['G']
        if self.n_extra:
            G = sp.block_diag([G, sp.csr_matrix((self.n_extra, self.n_extra))]).tocsr()
        a = np.array([e[0] for e in self.extra], np.int64)
        bb = np.array([e[1] for e in self.extra], np.int64)
        y = np.array([e[2] for e in self.extra])
        if len(a):
            G = G + sp.coo_matrix((np.r_[y, y, -y, -y], (np.r_[a, bb, a, bb], np.r_[a, bb, bb, a])), shape=(n, n)).tocsr()
        adj = np.concatenate([st['adj'], np.stack([a, bb], 1)]) if len(a) else st['adj']
        A = sp.coo_matrix((np.ones(len(adj)), (adj[:, 0], adj[:, 1])), shape=(n, n))
        ncomp, comp = connected_components(A + A.T, directed=False)
        order = np.argsort(comp, kind='stable')
        roots = order[np.searchsorted(comp[order], np.arange(ncomp))]
        keep = np.ones(n, bool)
        keep[roots] = False
        self.keep = np.nonzero(keep)[0]
        self.n, self.G, self.comp, self.ncomp = n, G, comp, ncomp
        self.a_, self.b_, self.y_ = a, bb, y
        self.lu = spla.splu(G[self.keep][:, self.keep].tocsc(), permc_spec='COLAMD')

    def solve(self, S):
        S = np.asarray(S, float)
        one = S.ndim == 1
        S = S[:, None] if one else S
        X = np.zeros_like(S)
        X[self.keep] = self.lu.solve(np.ascontiguousarray(S[self.keep]))
        return X[:, 0] if one else X

    def woodbury_remove(self, links, phi):
        """Exact change of the loop inductance s'phi when the given links are removed."""
        links = np.asarray(links)
        k = len(links)
        a, bb, y = self.a_[links], self.b_[links], self.y_[links]
        E = np.zeros((self.n, k))
        E[a, np.arange(k)] += 1.0
        E[bb, np.arange(k)] -= 1.0
        P = self.solve(E)
        Mw = np.diag(1.0 / y) - (P[a] - P[bb])
        v = phi[a] - phi[bb]
        sol = np.linalg.lstsq(Mw, v, rcond=1e-14)[0]
        if np.linalg.norm(Mw @ sol - v) > 1e-6 * max(np.linalg.norm(v), 1e-30):
            return np.inf
        return float(v @ sol)

    def thevenin_add(self, pairs, phi, z_new, chunk=48):
        """Exact change of s'phi for each candidate link (u, v) added alone: -dphi^2 / (z_new + Z_th)."""
        out = np.zeros(len(pairs))
        for c0 in range(0, len(pairs), chunk):
            pc = pairs[c0:c0 + chunk]
            E = np.zeros((self.n, len(pc)))
            for k, (u, v) in enumerate(pc):
                E[u, k] += 1.0
                E[v, k] -= 1.0
            P = self.solve(E)
            for k, (u, v) in enumerate(pc):
                dv = phi[u] - phi[v]
                out[c0 + k] = -dv * dv / (z_new + P[u, k] - P[v, k])
        return out


class _SR:
    """Minimal synthetic StackRaster for the self-tests."""

    def __init__(self, owner, gaps, h):
        self.owner, self.gaps, self.h, self.nl = owner, gaps, h, owner.shape[0]
        self.ny, self.nx = owner.shape[1:]
        self.x0 = self.y0 = 0.0
        self.off = 0
        self.nets = sorted(set(owner[owner >= 0].ravel().tolist()))
        same_x = (owner[:, :, :-1] == owner[:, :, 1:]) & (owner[:, :, :-1] >= 0)
        same_y = (owner[:, :-1, :] == owner[:, 1:, :]) & (owner[:, :-1, :] >= 0)
        self.FX, self.FY = same_x.astype(float), same_y.astype(float)


def stack_selftest(h_out):
    """(1) strip over a plane: L = mu0 h l/w in this model; (2) via pair in a plane pair vs a plain sheet solve."""
    h = 0.1
    own = -np.ones((2, 40, 140), np.int64)
    own[1] = 0
    own[0, 15:25, 20:120] = 1
    st = assemble_stack(_SR(own, [0.2], h), h_out)
    sol = StackSolver(st)
    for j in range(15, 25):
        sol.link(st['ids'][0, j, 119], st['ids'][1, j, 119], RIGID, 'short')
    ea, eb = sol.node(), sol.node()
    for j in range(15, 25):
        sol.link(ea, st['ids'][0, j, 20], RIGID, 'a')
        sol.link(eb, st['ids'][1, j, 20], RIGID, 'b')
    sol.finalize()
    s = np.zeros(sol.n)
    s[ea], s[eb] = 1.0, -1.0
    L1 = float(s @ sol.solve(s))
    ex1 = MU0 * 0.2e-3 * 99 / 10
    h2, n2 = 0.25, 120
    own = np.zeros((2, n2, n2), np.int64)
    own[1] = 1
    st = assemble_stack(_SR(own, [1.0], h2), h_out)
    sol = StackSolver(st)
    j0, i1, i2 = n2 // 2, n2 // 2 - 20, n2 // 2 + 20
    sol.link(st['ids'][0, j0, i1], st['ids'][1, j0, i1], RIGID, 'via')
    sol.finalize()
    s = np.zeros(sol.n)
    s[st['ids'][0, j0, i2]], s[st['ids'][1, j0, i2]] = 1.0, -1.0
    L2 = float(s @ sol.solve(s))
    nn = n2 * n2
    idx = np.arange(nn).reshape(n2, n2)
    e = np.r_[np.stack([idx[:, :-1].ravel(), idx[:, 1:].ravel()], 1), np.stack([idx[:-1].ravel(), idx[1:].ravel()], 1)]
    Gs = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(nn, nn))
    Gs = (sp.diags(np.asarray((Gs + Gs.T).sum(1)).ravel()) - Gs - Gs.T).tocsc()
    keep = np.arange(1, nn)
    v = np.zeros(nn)
    rhs = np.zeros(nn)
    rhs[idx[j0, i2]], rhs[idx[j0, i1]] = 1.0, -1.0
    v[keep] = spla.splu(Gs[keep][:, keep]).solve(rhs[keep])
    ex2 = MU0 * 1.0e-3 * (v[idx[j0, i2]] - v[idx[j0, i1]])
    inf2 = MU0 * 1.0e-3 / math.pi * math.log(10.0 / (0.198 * h2))
    return L1, ex1, L2, ex2, inf2


def loop_bodies(roles, decaps, h):
    """Current paths of the lumped parts of the hot loop, drawn on the component layer.

    Driver: one conductor made of the paddle (exposed pad) and a 0.3 mm lead strip from each supply pin into it
    (lead + bond); the loop is driven by an EMF across that strip between the pin and the paddle. Capacitor: its
    body as a strip between its pad centres; internal ESL sits on a cut at mid-length."""
    from shapely.ops import nearest_points
    drv = roles['driver']
    gp = [p for p in drv['pads'] if p['net'] == roles['gnd']]
    ep = max(gp, key=lambda p: p['poly'].area)
    rails = [q for q in drv['pads'] if q['net'] == roles['rail']]
    meta = dict(die=f"@{drv['ref']}.die", ep=ep, vs=[], caps={}, ret=[])
    if roles.get('foot'):
        # die at the paddle centre; supply lead(s) and bridge-return lead(s) run to it (0.2 mm strips)
        D = (ep['x'], ep['y']) if ep['poly'].area >= 1.0 else \
            (np.mean([p['x'] for p in drv['pads']]), np.mean([p['y'] for p in drv['pads']]))
        die = []
        for p in rails:
            die.append(LineString([(p['x'], p['y']), D]).buffer(0.1, cap_style='round'))
            meta['vs'].append((p, (p['x'], p['y']), D))
        for p in roles['foot']:
            die.append(LineString([(p['x'], p['y']), D]).buffer(0.1, cap_style='round'))
        meta['ret'] = list(roles['foot'])
    else:
        if ep['poly'].area < 1.0:                # no exposed pad: the ground pin nearest the supply pin
            ep = min(gp, key=lambda p: math.hypot(p['x'] - rails[0]['x'], p['y'] - rails[0]['y']))
            meta['ep'] = ep
        die = [ep['poly']]
        for p in rails:
            q = nearest_points(ep['poly'], Point(p['x'], p['y']))[0]
            d = math.hypot(q.x - p['x'], q.y - p['y'])
            ux, uy = (q.x - p['x']) / d, (q.y - p['y']) / d
            die.append(LineString([(p['x'], p['y']), (q.x + 0.3 * ux, q.y + 0.3 * uy)]).buffer(0.15, cap_style='flat'))
            meta['vs'].append((p, (p['x'], p['y']), (q.x, q.y)))
        meta['ret'] = [ep]
    out = [(meta['die'], unary_union(die))]
    for f in decaps:
        pa = next(p for p in f['pads'] if p['net'] == roles['rail'])
        pb = next(p for p in f['pads'] if p['net'] == roles['gnd'])
        A, B = np.array([pa['x'], pa['y']]), np.array([pb['x'], pb['y']])
        u = (B - A) / np.linalg.norm(B - A)
        v = np.array([-u[1], u[0]])
        width = 0.9 * min(np.ptp(np.array(pp['poly'].exterior.coords) @ v) for pp in (pa, pb))
        out.append((f"@{f['ref']}", LineString([tuple(A), tuple(B)]).buffer(width / 2, cap_style='flat')))
        sz = re.search(r'(0201|0402|0603|0805|1206|1210)', f['lib'] + ' ' + f['value'])
        esl = {'0201': 0.1, '0402': 0.15, '0603': 0.2, '0805': 0.25, '1206': 0.3, '1210': 0.3}.get(sz.group(1) if sz else '', 0.25) * 1e-9
        meta['caps'][f['ref']] = (f"@{f['ref']}", pa, pb, tuple(A), tuple(B), esl, f)
    return out, meta


class HFModel:
    """Hot-loop model on a stack raster: vias and ties as rigid links, die EMF and capacitor ESL as special faces."""

    def __init__(self, b, sr, roles, meta, h_out):
        self.b, self.sr, self.roles, self.meta, self.h_out = b, sr, roles, meta, h_out
        self.barrels = [(v['x'], v['y'], v['net'], v['layers'], ('via', i)) for i, v in enumerate(b.vias)]
        self.barrels += [(p['x'], p['y'], p['net'], p['layers'], ('pth', i)) for i, p in enumerate(b.pads)
                         if p['kind'] == 'thru_hole' and p['drill'] > 0 and len(p['layers']) > 1]
        # vertical ties from part bodies to their pads (top copper cells under the pad, owned by the pad's net)
        self.ties = []
        top = sr.off
        die = sr.nets.index(meta['die'])
        groups = [(die, meta['ret'], [v[0] for v in meta['vs']])]
        groups += [(sr.nets.index(c[0]), [c[1]], [c[2]]) for c in meta['caps'].values()]
        tieside = {}
        for bi, side_a, side_b in groups:
            for side, pads in ((0, side_a), (1, side_b)):
                for pp in pads:
                    if pp['net'] not in sr.nets:
                        continue
                    ni = sr.nets.index(pp['net'])
                    x0, y0, x1, y1 = pp['poly'].bounds
                    i0, i1 = max(0, int((x0 - sr.x0) / sr.h) - 1), min(sr.nx, int((x1 - sr.x0) / sr.h) + 2)
                    j0, j1 = max(0, int((y0 - sr.y0) / sr.h) - 1), min(sr.ny, int((y1 - sr.y0) / sr.h) + 2)
                    ii, jj = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1))
                    xs, ys = sr.x0 + (ii + 0.5) * sr.h, sr.y0 + (jj + 0.5) * sr.h
                    ok = shapely.contains_xy(pp['poly'], xs, ys) & (sr.owner[0, jj, ii] == bi) & (sr.owner[top, jj, ii] == ni)
                    for j, i in zip(jj[ok], ii[ok]):
                        self.ties.append((int(j), int(i)))
                        tieside[(bi, int(j), int(i))] = side
        self.tieside = tieside
        self.emf = {}
        k = self._cut(die, [(P0, P1) for pin, P0, P1 in meta['vs']], 0.1)
        if not k:
            raise ValueError('no complete cut across the driver lead strip(s) for the EMF; try a finer --h-hf')
        for key in k:
            self.emf[key] = dict(emf=True)
        self.capcut = {}
        for ref, (name, pa, pb, A, B, esl, f) in meta['caps'].items():
            self.capcut[ref] = (self._cut(sr.nets.index(name), [(A, B)], 1.0) or [], esl)

    def _cut(self, own, segs, half_width):
        """Faces of component-layer conductor `own` across rows (or columns) near the midpoints of the segments P0-P1,
        all shifted together, such that removing them separates the cells tied to one side's pads from those tied to
        the other's (a complete cut)."""
        sr = self.sr
        o = sr.owner[0] == own
        jj, ii = np.nonzero(o)
        idx = -np.ones(o.shape, np.int64)
        idx[jj, ii] = np.arange(len(jj))
        e = []
        ok = o[:, :-1] & o[:, 1:] & (sr.FX[0] > 0)
        a_, b_ = np.nonzero(ok)
        e += [((0, int(j), int(i)), idx[j, i], idx[j, i + 1]) for j, i in zip(a_, b_)]
        ok = o[:-1, :] & o[1:, :] & (sr.FY[0] > 0)
        a_, b_ = np.nonzero(ok)
        e += [((1, int(j), int(i)), idx[j, i], idx[j + 1, i]) for j, i in zip(a_, b_)]
        sides = [np.array([idx[j, i] for (bi, j, i), sd in self.tieside.items() if bi == own and sd == s_]) for s_ in (0, 1)]
        if not len(sides[0]) or not len(sides[1]):
            return None
        for shift in range(0, 14):
            for sgn in ((0,) if shift == 0 else (-1, 1)):
                keys = set()
                for P0, P1 in segs:
                    P0, P1 = np.array(P0, float), np.array(P1, float)
                    mid = 0.5 * (P0 + P1)
                    d = P1 - P0
                    if abs(d[1]) >= abs(d[0]):
                        j = int(round((mid[1] - sr.y0) / sr.h - 1)) + sgn * shift
                        keys |= {k for k, _, _ in e if k[0] == 1 and k[1] == j
                                 and abs(sr.x0 + (k[2] + 0.5) * sr.h - mid[0]) <= half_width + sr.h}
                    else:
                        i = int(round((mid[0] - sr.x0) / sr.h - 1)) + sgn * shift
                        keys |= {k for k, _, _ in e if k[0] == 0 and k[2] == i
                                 and abs(sr.y0 + (k[1] + 0.5) * sr.h - mid[1]) <= half_width + sr.h}
                if not keys:
                    continue
                rest = [(u, v) for k, u, v in e if k not in keys]
                A = sp.coo_matrix((np.ones(len(rest)), ([u for u, v in rest], [v for u, v in rest])), shape=(len(jj), len(jj)))
                _, lab = connected_components(A + A.T, directed=False)
                if not set(lab[sides[0]]) & set(lab[sides[1]]):
                    return sorted(keys)
        return None

    def build(self, esl=True, add_link=None, drop_layers=(), drop_vias=(), cap_L=None):
        sr = self.sr
        special = dict(self.emf)
        for ref, (keys, l_esl) in self.capcut.items():
            lv = (cap_L or {}).get(ref, l_esl if esl else 0.0)
            for key in keys:
                special[key] = dict(L=lv * len(keys), cap=ref)
        st = assemble_stack(sr, self.h_out, drop_layers=drop_layers, special=special)
        sol = StackSolver(st)
        ids = st['ids']
        vias = []
        for x, y, net, lys, tag in self.barrels:
            if net not in sr.nets or tag in drop_vias:
                continue
            ni = sr.nets.index(net)
            cells = []
            for ly in lys:
                c, o = sol.cell(sr.layers.index(ly), x, y)
                if c >= 0 and o == ni:
                    cells.append(c)
            lk = [sol.link(c1, c2, RIGID, tag) for c1, c2 in zip(cells, cells[1:])]
            if lk:
                vias.append((tag, x, y, net, lk))
        for j, i in self.ties:
            if ids[0, j, i] >= 0 and ids[sr.off, j, i] >= 0:
                sol.link(ids[0, j, i], ids[sr.off, j, i], RIGID, ('tie',))
        if add_link is not None:
            sol.link(add_link[0], add_link[1], RIGID, ('new',))
        sol.finalize()
        J = np.zeros(sol.n)
        for sf in st['spec']:
            if sf.get('emf'):
                np.add.at(J, sf['na'], sf['Y'][:, 0])
                np.add.at(J, sf['nb'], -sf['Y'][:, 0])
        phi = sol.solve(J)
        I = sum(float(sf['Y'][0] @ (phi[sf['na']] - phi[sf['nb']]) - sf['Y'][0, 0]) for sf in st['spec'] if sf.get('emf'))
        return dict(st=st, sol=sol, vias=vias, phi=phi, I=I, L=1.0 / abs(I))


def run_hf(b, roles, N, Ib, sdef, col, args):
    gnd, rail, drv = roles['gnd'], roles['rail'], roles['driver']
    side = 'bottom' if drv['layer'] == b.cu[-1] else 'top'
    t0 = tic()
    L1, ex1, L2, ex2, inf2 = stack_selftest(args.h_out)
    wh = MU0 * 9.9e-3 / (5 + 1.393 + 0.667 * math.log(5 + 1.444))
    log("\n== HF hot loop (inductive limit, stack-local parallel-plate model)")
    log(f"   self-test: strip 1 x 9.9 mm over a plane 0.2 mm below: {L1 * 1e9:.4f} nH vs mu0*h*l/w {ex1 * 1e9:.4f} nH"
        f" (Wheeler with fringing {wh * 1e9:.3f} nH: the local model over-estimates narrow strips by x{L1 / wh:.2f});"
        f" via pair 10 mm apart in a 1.0 mm plane pair: {L2 * 1e9:.4f} nH vs mu0*h*squares {ex2 * 1e9:.4f} nH"
        f" (infinite plane (mu0 h/pi) ln(D/0.198 dx) = {inf2 * 1e9:.3f} nH)")
    near = [f for d, f in roles['decaps'] if d < 12.0]
    pts = [(p['x'], p['y']) for p in drv['pads']] + [(p['x'], p['y']) for f in near for p in f['pads']]
    drv_gnd = roles['foot'] or [p for p in drv['pads'] if p['net'] == gnd]
    for p in (q for q in drv['pads'] if q['net'] == gnd):       # the ground vias any driver ground pin can reach first
        gv = sorted((v for v in b.vias if v['net'] == gnd), key=lambda v: math.hypot(v['x'] - p['x'], v['y'] - p['y']))
        pts += [(v['x'], v['y']) for v in gv[:4]]
    for ph in roles['phases']:
        pts += [(p['x'], p['y']) for p in (ph['shunt']['fp']['pads'] if ph['shunt'] else ph['inductor']['pads'])]
        if ph['load']:
            pts += [(p['x'], p['y']) for p in ph['load']['pads']]
    xs, ys = zip(*pts)
    m = 3.0
    window = [min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m]
    if b.outline is not None:
        bx = b.outline.bounds
        window = [max(window[0], bx[0]), max(window[1], bx[1]), min(window[2], bx[2]), min(window[3], bx[3])]
    h = args.h_hf
    nets_all = sorted({p['net'] for p in b.pads if p['net']} | {t['net'] for t in b.tracks if t['net']}
                      | {z['net'] for z in b.zones})
    bodies, meta = loop_bodies(roles, near, h)
    sr = StackRaster(b, window, h, nets_all, bodies=bodies, h_comp=args.h_comp, side=side)
    hm = HFModel(b, sr, roles, meta, args.h_out)
    off = sr.off
    res = {}
    r0 = hm.build(esl=False)
    st = r0['st']
    log(f"   window ({window[0]:.1f}, {window[1]:.1f})-({window[2]:.1f}, {window[3]:.1f}) mm at {h} mm: {st['n']} sheet cells on"
        f" {len(b.cu)} copper layers + a component layer {args.h_comp} mm beyond {sr.layers[1]} (part bodies, driver lead and paddle);"
        f" {len(sr.nets)} conductors, every copper island one (passive nets carry eddy currents); outer-field thickness"
        f" {args.h_out} mm; loop driven by an EMF across the driver's supply lead; decaps {', '.join(f['ref'] for f in near)};"
        f" build + solve {tic() - t0:.1f} s")
    # each decap alone: exact Woodbury is not available for special faces, so open the others by re-assembly
    parts = []
    for ref in hm.capcut:
        r_ = hm.build(esl=False, cap_L={r2: (0.0 if r2 == ref else 1.0) for r2 in hm.capcut})   # others open (1 H)
        parts.append(f"{ref} alone {r_['L'] * 1e9:.2f} nH")
    log(f"   loop inductance seen by the die (copper + part current paths; no internal ESL, no bond wires): all decaps"
        f" {r0['L'] * 1e9:.2f} nH; " + "; ".join(parts))
    res['L_board'] = r0['L']
    t1 = tic()
    r1 = hm.build(esl=True)
    st, sol, phi, I, L = r1['st'], r1['sol'], r1['phi'], r1['I'], r1['L']
    cur = sol.y_ * (phi[sol.a_] - phi[sol.b_]) / abs(I)
    sfl = special_flows(st, phi)
    split = defaultdict(float)
    for sf, Iv in sfl:
        if 'cap' in sf:
            split[sf['cap']] += Iv[0] / abs(I)
    log("   adding generic internal ESL [I] (" + ", ".join(f"{r} {e * 1e9:.2f} nH" for r, (k, e) in hm.capcut.items())
        + f"): {L * 1e9:.2f} nH; HF current split among the capacitors: " + ", ".join(
            f"{r} {100 * abs(v):.0f}%" for r, v in split.items()) + f" ({tic() - t1:.1f} s)")
    res['L_esl'] = L
    res['split'] = dict(split)
    flows = face_flows(st, phi)
    E, El = gap_energy(st, flows, sfl)
    E, El = E / I ** 2, El / I ** 2
    names = ['beyond the parts'] + [f"{sr.layers[i]}-{sr.layers[i + 1]} ({sr.gaps[i]:.3f} mm)"
                                     for i in range(sr.nl - 1)] + ['beyond ' + sr.layers[-1]]
    log("   where the loop's magnetic energy sits (share of L): " + ", ".join(
        f"{n} {100 * e / L:.0f}%" for n, e in zip(names, E) if e > 0.005 * L) + f", internal ESL {100 * El / L:.0f}%"
        + f" (sum {100 * (E.sum() + El) / L:.1f}% of the solve)")
    res['Egap'] = {n: e / L for n, e in zip(names, E)}
    per = defaultdict(float)
    for axis, S, jj, ii, Iv, f in flows:
        for p, li in enumerate(S):
            o = st['owner'][li, jj, ii]
            for ni in np.unique(o):
                per[(li, sr.nets[ni])] += np.abs(Iv[p][o == ni]).sum() * h / abs(I)
    rows = sorted(((k, v) for k, v in per.items() if not k[1].startswith('@')), key=lambda t: -t[1])
    log("   HF current x length (A mm per A of loop current) by layer and net: " + "; ".join(
        f"{sr.layers[li]} {n.split('/')[-1]} {v:.1f}" for (li, n), v in rows[:8] if v > 0.3))
    res['per'] = dict(per)
    vrows = []
    for tag, x, y, net, lk in r1['vias']:
        vrows.append((max(abs(cur[k]) for k in lk), tag, x, y, net, lk))
    vrows.sort(key=lambda t: -t[0])
    hm.hf_via = {(round(x, 3), round(y, 3)): c for c, tag, x, y, net, lk in vrows}
    log("   vias in the HF loop (share of the loop current; exact removal by Woodbury):")
    chk = None
    for c, tag, x, y, net, lk in vrows[:9]:
        if c < 0.02:
            break
        dI = sol.woodbury_remove(lk, phi)
        L2 = 1.0 / abs(I + dI) if np.isfinite(dI) else np.inf
        if chk is None:
            chk = (tag, L2)
        log(f"     {net.split('/')[-1]:6s} {tag[0]} at {where(x, y)}: {100 * c:3.0f}%; removing it: "
            + ("disconnects" if not np.isfinite(L2) else f"L {1e12 * (L2 - L):+.0f} pH ({pct(L2 - L, L):+.1f}%)"))
    if chk:
        rb_ = hm.build(esl=True, drop_vias={chk[0]})
        log(f"     (check, first row by brute force: {1e12 * (rb_['L'] - L):+.0f} pH)")
    res['vias'] = [(c, x, y, net) for c, tag, x, y, net, lk in vrows[:12]]
    for li in range(off, sr.nl):
        o = sr.owner[li]
        if (o >= 0).sum() < 0.5 * o.size:
            continue
        main_net = sr.nets[Counter(o[o >= 0].ravel()).most_common(1)[0][0]]
        if main_net in (gnd, rail):
            continue
        t1 = tic()
        r2 = hm.build(esl=True, drop_layers=(li,))
        log(f"   counterfactual: remove the {main_net} plane ({sr.layers[li]}) from the window: L {L * 1e9:.2f} -> {r2['L'] * 1e9:.2f} nH"
            f" ({pct(r2['L'] - L, L):+.0f}%) ({tic() - t1:.1f} s)")
        res['plane_cf'] = (main_net, sr.layers[li], L, r2['L'])
    gi = sr.nets.index(gnd)
    plane_net = {li: sr.nets[Counter(sr.owner[li][sr.owner[li] >= 0].ravel()).most_common(1)[0][0]]
                 for li in range(off, sr.nl) if (sr.owner[li] >= 0).any()}
    # stackup counterfactual: if the ground plane is not the plane next to the parts' copper, swap the two planes
    planes = [li for li in range(off + 1, sr.nl - 1) if (sr.owner[li] >= 0).sum() >= 0.5 * sr.owner[li].size]
    gpl = [li for li in planes if plane_net.get(li) == gnd]
    if gpl and planes and planes[0] != gpl[0]:
        import copy
        a_, b_ = planes[0], gpl[0]
        sr2 = copy.copy(sr)
        sr2.owner, sr2.FX, sr2.FY = sr.owner.copy(), sr.FX.copy(), sr.FY.copy()
        for arr in (sr2.owner, sr2.FX, sr2.FY):
            arr[[a_, b_]] = arr[[b_, a_]]
        r3 = HFModel(b, sr2, roles, meta, args.h_out).build(esl=True)
        log(f"   stackup counterfactual: swap the {plane_net[a_]} plane ({sr.layers[a_]}) and the {gnd} plane ({sr.layers[b_]}) so that"
            f" {gnd} is next to the power stage: L {L * 1e9:.2f} -> {r3['L'] * 1e9:.2f} nH ({pct(r3['L'] - L, L):+.0f}%)")
        res['swap'] = (plane_net[a_], sr.layers[a_], sr.layers[b_], L, r3['L'])
    cx = np.mean([p['x'] for p in drv_gnd])
    cy = np.mean([p['y'] for p in drv_gnd])
    cand = []
    r = int(math.ceil(0.25 / h))
    for j in range(sr.ny):
        for i in range(sr.nx):
            x, y = sr.xy(j, i)
            if math.hypot(x - cx, y - cy) > 6.0 or st['owner'][off, j, i] != gi:
                continue
            blk = st['owner'][off, max(0, j - r):j + r + 1, max(0, i - r):i + r + 1]
            if np.any((blk >= 0) & (blk != gi)):
                continue
            lower, ok = None, True
            for li in range(off + 1, sr.nl):
                o = st['owner'][li, j, i]
                if o == gi and lower is None:
                    lower = li
                elif o >= 0 and o != gi and sr.nets[o] != plane_net.get(li):
                    ok = False          # would hit a foreign trace or pad (planes get an antipad)
            if ok and lower is not None:
                cand.append((i, j, int(st['ids'][off, j, i]), int(st['ids'][lower, j, i])))
    if cand:
        dI = sol.thevenin_add([(u, v) for _, _, u, v in cand], phi, 1.0 / RIGID)
        Lc = 1.0 / np.abs(I + dI)
        order = np.argsort(Lc)
        i, j, u, v = cand[order[0]]
        rb_ = hm.build(esl=True, add_link=(u, v))
        bx_, by_ = sr.xy(j, i)
        on_ep = meta['ep']['poly'].contains(Point(bx_, by_))
        log(f"   one more {gnd} via (exact Thevenin addition over {len(cand)} legal sites within 6 mm of the driver's ground pads):"
            f" best at {where(bx_, by_)}{' (in the exposed pad)' if on_ep else ''}: L {L * 1e9:.2f} -> {Lc[order[0]] * 1e9:.2f} nH"
            f" ({pct(Lc[order[0]] - L, L):+.0f}%; brute force {rb_['L'] * 1e9:.2f} nH); median site {pct(np.median(Lc) - L, L):+.1f}%;"
            " next: " + ", ".join(f"{where(*sr.xy(cand[o][1], cand[o][0]))} {pct(Lc[o] - L, L):+.0f}%" for o in order[1:5]))
        res['add'] = (bx_, by_, L, Lc[order[0]], rb_['L'], float(np.median(Lc)))
    log("   switch-node charge to whom (parallel-plate C of each phase net's copper in the window to adjacent layers):")
    res['charge'] = {}
    for ph in roles['phases']:
        for net in (ph['net_in'], ph['net_out']):
            if net not in sr.nets:
                continue
            ni = sr.nets.index(net)
            dest = defaultdict(float)
            for li in range(off, sr.nl):
                mine = sr.owner[li] == ni
                if not mine.any():
                    continue
                for lj in (li - 1, li + 1):
                    if not off <= lj < sr.nl:
                        continue
                    k = min(li, lj)
                    o2 = sr.owner[lj][mine]
                    for n2 in np.unique(o2[o2 >= 0]):
                        dest[sr.nets[n2]] += EPS0 * sr.er[k] * (h * 1e-3) ** 2 / (sr.gaps[k] * 1e-3) * np.sum(o2 == n2)
            tot = sum(dest.values())
            if tot > 0:
                res['charge'][net] = (tot, dict(dest))
                log(f"     {net.split('/')[-1]:10s}: {tot * 1e12:.2f} pF; " + ", ".join(
                    f"{n.split('/')[-1]} {100 * v / tot:.0f}%" for n, v in sorted(dest.items(), key=lambda t: -t[1])[:3])
                    + f"; displacement current {tot * 1e9 * 1e3:.1f} mA per V/ns of edge rate")
    feeds = [nm for nm in sdef if nm.startswith('feed')]
    if feeds:
        k = col[feeds[0]]
        rows = []
        for vv in N.vias:
            key = (round(vv['x'], 3), round(vv['y'], 3))
            if vv['segs'] and key in hm.hf_via:
                rows.append((hm.hf_via[key], np.abs(Ib[np.array(vv['segs']), k]).max(), vv))
        rows.sort(key=lambda t: -max(t[0], t[1]))
        log(f"   the same vias at DC ({feeds[0]}, share of the supply current) and in the HF loop (share of the loop current):")
        for hfc, dcc, vv in rows[:9]:
            log(f"     {vv['net'].split('/')[-1]:6s} {vv['kind']} at {where(vv['x'], vv['y'])}:"
                f" DC {100 * dcc:5.1f}%   HF {100 * hfc:5.1f}%")
    res['window'] = window
    return res


# ============================================================================ convex floor (lens VP)
def joint_floor(b, nets, terms, h, area_budget, domain, iters=150):
    """Frank-Wolfe on the relaxed density of several two-terminal pours sharing a domain.

    min sum_n R_n(rho_n)  s.t.  sum_n rho_n,c <= 1 per cell, sum rho h^2 <= area_budget, rho_n = 1 on the
    net's own terminal pads. Face conductance (rho_i + rho_j)/(2 R_s): compliance is convex in rho, so the
    Frank-Wolfe gap gives a certified lower bound for every layout (binary or not) on this grid and domain.
    """
    rs = b.rs[b.cu[0]]
    bx = domain.bounds
    x0, y0 = math.floor(bx[0] / h) * h - h, math.floor(bx[1] / h) * h - h
    nx, ny = int(math.ceil((bx[2] - x0) / h)) + 2, int(math.ceil((bx[3] - y0) / h)) + 2
    dom = raster(domain, x0, y0, nx, ny, h, ss=3, fs=2)[0] > 0.5
    fixed, start, elec = [], [], []
    for net, (pa, pb) in zip(nets, terms):
        el = [raster(p['poly'], x0, y0, nx, ny, h, ss=3, fs=2)[0] > 0.3 for p in (pa, pb)]
        fixed.append(el[0] | el[1])
        elec.append(el)
        start.append(raster(b.copper(net, b.cu[0]), x0, y0, nx, ny, h, ss=3, fs=2)[0])
    anyfixed = np.any(fixed, axis=0)
    dom = dom | anyfixed
    cells = np.nonzero(dom.ravel())[0]
    nc = len(cells)
    idx = -np.ones(ny * nx, np.int64)
    idx[cells] = np.arange(nc)
    J, I = np.divmod(cells, nx)
    E = []
    for dj, di in ((0, 1), (1, 0)):
        ok = (J + dj < ny) & (I + di < nx)
        nb = np.where(ok, (J + dj) * nx + (I + di), 0)
        ok &= dom.ravel()[nb]
        E.append(np.stack([np.arange(nc)[ok], idx[nb[ok]]], 1))
    E = np.concatenate(E)
    design = ~anyfixed.ravel()[cells]
    fixed_c = [f.ravel()[cells] for f in fixed]
    elec_c = [(np.nonzero(e[0].ravel()[cells])[0], np.nonzero(e[1].ravel()[cells])[0]) for e in elec]
    budget = area_budget / (h * h) - sum(f.sum() for f in fixed_c)

    def solve_net(k, rho):
        gf = (0.5 * (rho[E[:, 0]] + rho[E[:, 1]]) + 1e-6) / rs
        ea, eb = elec_c[k]
        big = 1e3 / rs
        a = np.r_[E[:, 0], ea, eb]
        c = np.r_[E[:, 1], np.full(len(ea), nc), np.full(len(eb), nc + 1)]
        g = np.r_[gf, np.full(len(ea) + len(eb), big)]
        G = sp.coo_matrix((np.r_[g, g, -g, -g], (np.r_[a, c, a, c], np.r_[a, c, c, a])), shape=(nc + 2, nc + 2)).tocsc()
        G = G + sp.diags(np.r_[np.full(nc, 1e-9 / rs), 0.0, 0.0])
        lu = spla.splu(G[:nc + 1, :nc + 1].tocsc(), permc_spec='COLAMD')
        s = np.zeros(nc + 1)
        s[nc] = 1.0
        v = lu.solve(s)
        dv = v[E[:, 0]] - v[E[:, 1]]
        e = 0.5 * dv * dv / rs
        grad = -(np.bincount(E[:, 0], e, nc) + np.bincount(E[:, 1], e, nc))
        return v[nc], grad

    def objective(rr):
        out = [solve_net(k, rr[k]) for k in range(len(nets))]
        return sum(o[0] for o in out), [o[1] for o in out], [o[0] for o in out]

    rho = [np.clip(s_.ravel()[cells], 0, 1) for s_ in start]
    for k in range(len(nets)):
        for k2 in range(len(nets)):
            rho[k2][fixed_c[k]] = 1.0 if k2 == k else 0.0
    tot = sum(rho)
    over = tot > 1
    for k in range(len(nets)):
        rho[k][over] /= tot[over]
    used = sum(r_[design].sum() for r_ in rho)
    if used > budget:
        for k in range(len(nets)):
            rho[k][design] *= budget / used
    f0, grads, R0 = objective(rho)
    f, best_lb, it = f0, -np.inf, 0
    for it in range(iters):
        gst = np.stack([-g for g in grads])
        gst[:, ~design] = -np.inf
        win = np.argmax(gst, 0)
        val = gst[win, np.arange(nc)]
        order = np.argsort(-val)
        order = order[design[order] & (val[order] > 0)]
        kf = int(min(len(order), math.floor(budget)))
        s = [np.where(fixed_c[k], 1.0, 0.0) for k in range(len(nets))]
        for k in range(len(nets)):
            sel = order[:kf][win[order[:kf]] == k]
            s[k][sel] = 1.0
        if kf < len(order):
            c = order[kf]
            s[win[c]][c] = budget - kf
        gap = sum(float(grads[k] @ (rho[k] - s[k])) for k in range(len(nets)))
        best_lb = max(best_lb, f - gap)
        if gap < 1e-3 * f:
            break
        g1 = 2.0 / (it + 3)
        trial = [rho[k] + g1 * (s[k] - rho[k]) for k in range(len(nets))]
        f1, gr1, _ = objective(trial)
        a2 = (f1 - f + gap * g1) / (g1 * g1)
        gam = min(1.0, max(1e-4, gap / (2 * a2))) if a2 > 0 else g1
        if abs(gam - g1) > 1e-6:
            cand = [rho[k] + gam * (s[k] - rho[k]) for k in range(len(nets))]
            fc, grc, _ = objective(cand)
            if fc < f1:
                trial, f1, gr1 = cand, fc, grc
        if f1 < f:
            rho, f, grads = trial, f1, gr1
    _, _, Rf = objective(rho)
    areas = [float(r_.sum()) * h * h for r_ in rho]
    return dict(f0=f0, R0=R0, lb=best_lb, f=f, Rf=Rf, areas=areas, iters=it + 1, cells=nc, rho=rho, cellsidx=cells,
                nx=nx, ny=ny, x0=x0, y0=y0)


def run_floor(b, roles, N, Ib, col, args):
    log("\n== Floors for the phase pours (lens VP): how much of their resistance is avoidable?")
    drv = roles['driver']
    top = next((p['layers'][0] for p in drv['pads'] if p['layers']), b.cu[0])
    rs = b.rs[top]
    nets, terms, areas, Racts, ds = [], [], [], [], []
    for ph in roles['phases']:
        pin = [p for p in drv['pads'] if p['net'] == ph['net_in']]
        spad = [p for p in ph['shunt']['fp']['pads'] if p['net'] == ph['net_in']] if ph['shunt'] else [ph['lpad']]
        if not pin or not spad or 'src' not in ph:
            continue
        g = b.copper(ph['net_in'], top)
        isl = max(getattr(g, 'geoms', [g]), key=lambda q: q.intersects(pin[0]['poly']) * q.area)
        d = pin[0]['poly'].distance(spad[0]['poly'])
        A = isl.area - pin[0]['poly'].area - spad[0]['poly'].area
        k = col[ph['src']]
        m = (N.net == ph['net_in']) & (N.kind <= 4)
        Ract = float((Ib[m, k] ** 2 / N.g[m]).sum())
        nets.append(ph['net_in'])
        terms.append((pin[0], spad[0]))
        areas.append(isl.area)
        Racts.append(Ract)
        ds.append(d)
        log(f"   {ph['net_in'].split('/')[-1]:8s}: pour {isl.area:.1f} mm2, pin-to-shunt-pad gap {d:.1f} mm;"
            f" actual copper R {fmt_r(Ract)};"
            f" Beckmann floor R_s d^2/A = {fmt_r(rs * d * d / A)}")
    if len(nets) < 2:
        log("   (joint floor needs two or more pours sharing a region; single-pour Beckmann floor only)")
        return None
    Atot = sum(areas)
    log(f"   joint Beckmann floor for {len(nets)} pours sharing {Atot:.1f} mm2: sum R >= R_s (sum d)^2 / A = "
        f"{fmt_r(rs * sum(ds) ** 2 / Atot)}; actual sum {fmt_r(sum(Racts))}")
    t0 = tic()
    outl = unary_union([z['outline'] for z in b.zones if z['net'] in nets and top in z['layers']])
    allnets = {p['net'] for p in b.pads if p['net']} | {t['net'] for t in b.tracks if t['net']} | {z['net'] for z in b.zones}
    others = unary_union([g for g in (b.copper(n, top) for n in allnets if n not in nets) if g.intersects(outl)])
    domain = unary_union([outl.difference(others)] + [b.copper(n, top) for n in nets])
    res = joint_floor(b, nets, terms, 0.1, Atot, domain, iters=50 if args.quick else 150)
    log(f"   joint convex floor (Frank-Wolfe, {res['iters']} iterations, {res['cells']} cells at 0.1 mm, {tic() - t0:.0f} s): same total"
        f" area, any split, region = the pours' zone outlines minus other nets' fixed copper (clearances ignored)")
    log(f"     actual layout in this relaxed model: sum R = {fmt_r(res['f0'])} (" + ", ".join(fmt_r(r) for r in res['R0'])
        + f"); certified floor >= {fmt_r(res['lb'])}; best relaxed design found {fmt_r(res['f'])}")
    log("     relaxed design per pour: " + ", ".join(f"{n.split('/')[-1]} {fmt_r(r)} on {a:.1f} mm2 (now {a0:.1f} mm2)"
                                              for n, r, a, a0 in zip(nets, res['Rf'], res['areas'], areas)))
    log(f"     => avoidable phase-copper loss within the allotted region: between {100 * max(0, 1 - res['f'] / res['f0']):.0f}% "
        f"(achieved by the relaxed design) and {100 * (1 - res['lb'] / res['f0']):.0f}% (certified bound)")
    return res


# ============================================================================ report
def fmt_r(r):
    return f"{r * 1e3:.3f} mOhm" if abs(r) >= 1e-4 else f"{r * 1e6:.1f} uOhm"


def pct(x, tot):
    return 100.0 * x / tot if tot else float('nan')


def where(x, y):
    return f"({x:.2f}, {y:.2f})"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('board')
    ap.add_argument('--current', type=float, default=1.0, help='nominal current per source (A) for loss numbers')
    ap.add_argument('--h-small', type=float, default=0.05, help='grid for rails and phase nets (mm)')
    ap.add_argument('--h-plane', type=float, default=0.2, help='grid for ground and plane nets (mm)')
    ap.add_argument('--h-hf', type=float, default=0.15, help='grid for the HF stack window (mm)')
    ap.add_argument('--h-out', type=float, default=10.0, help='outer field thickness in the stack model (mm); large = '
                    'planes confine the field (the parallel-plate limit)')
    ap.add_argument('--h-comp', type=float, default=0.3, help='height of part current paths above the top copper (mm)')
    ap.add_argument('--sketch', type=int, default=48, help='JL sketch size for whole-board leverage')
    ap.add_argument('--driver', help='override the inferred switching-cell reference')
    ap.add_argument('--quick', action='store_true', help='coarser grids for a fast look')
    ap.add_argument('--no-hf', action='store_true')
    ap.add_argument('--no-floor', action='store_true')
    args = ap.parse_args(argv)
    if args.quick:
        args.h_small, args.h_plane, args.h_hf = 0.1, 0.25, 0.25
    I0 = args.current

    # ------------------------------------------------------------------ 1. load
    t0 = tic()
    b = KBoard(args.board)
    fills = b.fill_report()
    log(f"== Board {os.path.basename(args.board)}: file version {b.version}; copper "
        + ", ".join(f"{ly} {b.tcu[ly] * 1e3:.1f} um ({b.rs[ly] * 1e3:.2f} mOhm/sq)" for ly in b.cu) + f"; stackup {b.stackup_note}")
    log("   dielectric gaps: " + ", ".join(f"{a}-{c} {g:.3f} mm" for (a, c), g in b.gap.items())
        + f"; outline {b.outline.area if b.outline is not None else float('nan'):.0f} mm2; parsed in {tic() - t0:.1f} s")
    log(f"   {len(b.fps)} footprints, {len(b.pads)} pads, {len(b.tracks)} tracks, {len(b.vias)} vias, {len(b.zones)} zones")
    ex = [t for t in b.tracks if t.get('exposed')]
    if ex:
        log(f"   {len(ex)} tracks have a solder-mask opening (tinned copper): " + ", ".join(sorted({f"{t['net']} on {t['layer']}"
            f" ({sum(LineString(u['pts']).length for u in ex if u['net'] == t['net']):.1f} mm, w {t['w']} mm)" for t in ex}))
            + "; modelled as bare copper (solder would lower their resistance)")
    nst = sum('OVERLAPS' in f[4] for f in fills)
    nap = sum('NO saved' in f[4] for f in fills)
    log(f"   zone fills: {len(fills) - nap} zone layers use the saved filled_polygon, {nap} approximated from the outline,"
        f" {nst} overlap other-net copper (stale-fill check)")
    for f in fills:
        if f[4] != 'saved fill':
            log(f"     {f[0]} on {f[1]}: outline {f[2]:.1f} mm2, fill {f[3]:.1f} mm2: {f[4]}")

    # ------------------------------------------------------------------ 2. roles
    roles, L = infer_roles(b, args)
    log("\n== What the board is (inferred from names, values, footprints and adjacency)")
    for line in L:
        log("   - " + line)
    gnd, rail, drv, phases = roles['gnd'], roles['rail'], roles['driver'], roles['phases']

    # ------------------------------------------------------------------ 3. DC network, sources, ports
    t0 = tic()
    dc_nets = list(dict.fromkeys([gnd, rail] + [n for ph in phases for n in ((ph['net_in'], ph['net_out']) if ph['shunt']
                                                                             else (ph['net_in'],))]
                                 + [r[0] for r in roles['regs']]))
    hnet = {n: (args.h_plane if roles['area'][n] > 150 else args.h_small) for n in dc_nets}
    N = build_dc(b, dc_nets, hnet, L)
    T = Terminals(N, b)
    drv_gnd = roles['foot'] or [p for p in drv['pads'] if p['net'] == gnd]
    drv_rail = [p for p in drv['pads'] if p['net'] == rail]
    lumped = []
    for ph in phases:
        s = ph['shunt']
        if s is None:
            continue
        pa = next(p for p in s['fp']['pads'] if p['net'] == ph['net_in'])
        pb = next(p for p in s['fp']['pads'] if p['net'] == ph['net_out'])
        brs, ph['inA'], ph['inB'], ph['outer'] = add_shunt_body(N, b, s, pa, pb, hnet[ph['net_in']])
        for k in brs:
            lumped.append((s['ref'], k))
        ph['nbody'] = sum(1 for r_, _ in lumped if r_ == s['ref'])
    sdef, pdef = {}, {}
    for J in roles['supplies']:
        jr = [p for p in J['pads'] if p['net'] == rail]
        jg = [p for p in J['pads'] if p['net'] == gnd]
        sdef[f"feed {J['ref']}"] = [(T.group_of(f"{J['ref']}.rail", jr), 1.0), (T.group_of('drv.rail', drv_rail), -1.0),
                                     (T.group_of('drv.gnd', drv_gnd), 1.0), (T.group_of(f"{J['ref']}.gnd", jg), -1.0)]
    if len(roles['supplies']) >= 2:
        Ja, Jb = roles['supplies'][:2]
        sdef[f"bus {Ja['ref']}->{Jb['ref']}"] = [
            (T.group_of(f"{Ja['ref']}.rail", [p for p in Ja['pads'] if p['net'] == rail]), 1.0),
            (T.group_of(f"{Jb['ref']}.rail", [p for p in Jb['pads'] if p['net'] == rail]), -1.0),
            (T.group_of(f"{Jb['ref']}.gnd", [p for p in Jb['pads'] if p['net'] == gnd]), 1.0),
            (T.group_of(f"{Ja['ref']}.gnd", [p for p in Ja['pads'] if p['net'] == gnd]), -1.0)]
    for ph in phases:
        pin = [p for p in drv['pads'] if p['net'] == ph['net_in']]
        out = [p for p in ph['load']['pads'] if p['net'] == ph['net_out']] if ph['load'] else \
            ([ph['lpad']] if ph.get('lpad') else [])
        if pin and out:
            ph['src'] = f"phase {ph['net_in'].split('/')[-1]}"
            sdef[ph['src']] = [(T.group_of(f"drv.{ph['net_in']}", pin), 1.0), (T.group_of(f"load.{ph['net_out']}", out), -1.0)]
    host = roles['host']
    for net, reg in roles['regs']:
        rp = [p for p in reg['pads'] if p['net'] == net]
        rg = [p for p in reg['pads'] if p['net'] == gnd]
        hp = [p for p in host['pads'] if p['net'] == net]
        hg = [p for p in host['pads'] if p['net'] == gnd]
        if rp and rg and hp and hg:
            sdef[f"{net} export"] = [(T.group_of(f"reg.{net}", rp), 1.0), (T.group_of(f"host.{net}", hp), -1.0),
                                     (T.group_of('host.gnd', hg), 1.0), (T.group_of(f"reg.{net}.gnd", rg), -1.0)]
    for ph in phases:
        amp = ph.get('amp')
        if amp is None:
            continue
        ain = [p for p in amp['pads'] if p['net'] == ph['net_in']]
        aout = [p for p in amp['pads'] if p['net'] == ph['net_out']]
        tag = ph['net_in'].split('/')[-1]
        ph['port'] = f"Kelvin {amp['ref']} ({tag})"
        pdef[ph['port']] = [(T.group_of(f"amp.{amp['ref']}.in", ain), 1.0), (T.group_of(f"amp.{amp['ref']}.out", aout), -1.0)]
        ag = [p for p in amp['pads'] if p['net'] == gnd]
        if host and ag:
            pdef[f"gnd {amp['ref']}->{host['ref']}"] = [(T.group_of(f"amp.{amp['ref']}.gnd", ag), 1.0),
                                                       (T.group_of('host.gnd', [p for p in host['pads'] if p['net'] == gnd]), -1.0)]
    N.finalize()
    names = list(sdef) + list(pdef)
    if not sdef:
        log("\n   no DC source could be defined (no supply connector or switch-node load found); stopping after roles")
        return None
    S = np.zeros((N.nn, len(names)))
    for k, nm in enumerate(names):
        for node, c in (sdef.get(nm) or pdef.get(nm)):
            S[node, k] += c
    N.factor()
    log(f"\n== DC conductor model: {N.nn} nodes, {N.nb} branches, {N.ncomp} components; grids "
        + ", ".join(f"{n.split('/')[-1]} {hnet[n]} mm" for n in dc_nets)
        + f"; {len(N.vias)} via/PTH barrels; build {tic() - t0 - N.t_factor:.1f} s, factor {N.t_factor:.1f} s")
    t1 = tic()
    Phi = N.solve(S)
    Ib = N.currents(Phi)
    col = {nm: k for k, nm in enumerate(names)}
    srcs = list(sdef)
    Rself = {nm: float(S[:, col[nm]] @ Phi[:, col[nm]]) for nm in srcs}
    log(f"   sources: {', '.join(srcs)}; quiet ports: {', '.join(pdef)}; solved in {tic() - t1:.2f} s")

    # ------------------------------------------------------------------ 4. leverage and exactness checks
    t1 = tic()
    rho_sk = N.leverage_sketch(k=args.sketch)
    log(f"   leverage sketch ({args.sketch} solves, {tic() - t1:.1f} s): Foster check sum(rho) = {rho_sk.sum():.0f}"
        f" vs nodes - components = {N.nn - N.ncomp} (the sketch is unbiased)")
    face = N.kind <= 1
    ns = len(srcs)
    load_any = np.max(np.abs(Ib[:, :ns]), axis=1)
    top = np.argsort(-np.where(face, load_any, 0))[:400]
    via_br = np.concatenate([np.array(v['segs'], int) for v in N.vias if v['segs']] + [np.zeros(0, int)])
    p0 = 0
    kf = int(np.argmax(np.where(face, np.abs(Ib[:, p0]), 0)))
    kv = int(via_br[np.argmax(np.abs(Ib[via_br, p0]))]) if len(via_br) else kf
    sel = np.unique(np.r_[top, via_br, [k for _, k in lumped], kf, kv]).astype(int)
    t1 = tic()
    rho_ex = np.full(N.nb, np.nan)
    rho_ex[sel] = N.g[sel] * N.reff(sel)
    rel = np.abs(rho_sk[sel] - rho_ex[sel]) / np.maximum(rho_ex[sel], 1e-12)
    log(f"   exact leverage for {len(sel)} pieces (all barrels, shunts, 400 most loaded faces) in {tic() - t1:.1f} s;"
        f" sketch error on them: median {100 * np.median(rel):.0f}%")
    chk = []
    for k in (kf, kv):
        act = np.ones(N.nb, bool)
        act[k] = False
        G2 = N.laplacian(act)
        fr = N.free[N.comp[N.a[k]]]
        x = np.zeros(N.nn)
        x[fr] = spla.splu(G2[fr][:, fr].tocsc(), permc_spec='COLAMD').solve(S[fr, p0])
        d_bf = float(S[fr, p0] @ x[fr] - S[fr, p0] @ Phi[fr, p0])
        d_r1 = Ib[k, p0] ** 2 / (N.g[k] * (1 - rho_ex[k]))
        chk.append(abs(d_r1 - d_bf) / max(abs(d_bf), 1e-30))
    log(f"   exactness: rank-1 removal vs brute-force re-solve (a face and a via barrel on '{srcs[p0]}'): max rel. error {max(chk):.1e}")

    # ------------------------------------------------------------------ 5. budgets
    log(f"\n== DC budgets (unit current per source; loss at {I0:g} A); copper loss by net and layer")
    for nm in srcs:
        k = col[nm]
        loss = Ib[:, k] ** 2 / N.g
        by = defaultdict(float)
        for net in dc_nets:
            for ly in b.cu + ['barrel']:
                mm = (N.net == net) & (N.lay == ly) & (N.kind <= 3)
                if mm.any():
                    by[(net, ly)] += float(loss[mm].sum())
        tot = Rself[nm]
        parts = ", ".join(f"{n.split('/')[-1]}/{ly} {pct(v, tot):.0f}%"
                          for (n, ly), v in sorted(by.items(), key=lambda t: -t[1]) if v > 0.02 * tot)
        lump = sum(loss[k2] for _, k2 in lumped)
        log(f"   {nm:14s}: R = {fmt_r(tot)}" + (f" (shunt {fmt_r(lump)} + copper {fmt_r(tot - lump)})" if lump > 0 else "")
            + f"; P = {tot * I0 ** 2 * 1e3:.2f} mW at {I0:g} A; copper loss: {parts}")

    # ------------------------------------------------------------------ 6. vias
    log("\n== Vias and plated holes at DC: share of each source, exact leverage, exact removal cost (Woodbury on the barrel)")
    vrows = []
    for v in N.vias:
        if v['segs']:
            segs = np.array(v['segs'])
            cur = np.abs(Ib[segs, :ns]).max(0)
            vrows.append((cur.max(), v, cur, segs))
    vrows.sort(key=lambda t: -t[0])
    nlive = sum(1 for r in vrows if r[0] > 1e-3)
    log(f"   {len(vrows)} barrels in the modelled nets; {nlive} carry > 0.1% of some DC source, {len(vrows) - nlive} carry less")
    for cmax, v, cur, segs in vrows[:16]:
        k = int(np.argmax(cur))
        src = srcs[k]
        dz = N.woodbury(segs, Phi[:, col[src]], Phi[:, col[src]])
        txt = 'disconnects' if not np.isfinite(dz) else f"+{pct(dz, Rself[src]):.2f}% R({src})"
        log(f"   {v['kind']} {v['net'].split('/')[-1]:8s} at {where(v['x'], v['y'])} drill {v['d']:.2f}: "
            + ", ".join(f"{s} {100 * c:.1f}%" for s, c in zip(srcs, cur) if c > 0.01)
            + f"; rho {rho_ex[segs[np.argmax(np.abs(Ib[segs, k]))]]:.2f}; removal {txt}")

    # ------------------------------------------------------------------ 7. where the loss is
    log("\n== Where each source's copper loss is: near its terminals, its hottest 1 mm tile, peak current density")
    tcu_b = np.array([b.tcu.get(l, 0.035) for l in N.lay[face]]) * 1e-3
    for nm in srcs:
        k = col[nm]
        loss = Ib[face, k] ** 2 / N.g[face]
        tot = loss.sum()
        J = np.abs(Ib[face, k]) / np.maximum(N.w[face] * 1e-3 * tcu_b, 1e-18) / 1e6
        jm = int(np.argmax(J))
        txt = []
        for node, c in sdef[nm]:
            d = np.hypot(N.mx[face] - N.x[node], N.my[face] - N.y[node])
            sh = loss[d < 0.5].sum() / tot
            if sh > 0.02:
                txt.append(f"{100 * sh:.0f}% within 0.5 mm of the {N.node_net[node].split('/')[-1]} terminal"
                           f" at {where(N.x[node], N.y[node])}")
        key = np.floor(N.mx[face]).astype(int) * 100000 + np.floor(N.my[face]).astype(int)
        u, inv = np.unique(key, return_inverse=True)
        acc = np.bincount(inv, weights=loss)
        kk = int(np.argmax(acc))
        tx_, ty_ = u[kk] // 100000, u[kk] % 100000
        txt.append(f"hottest 1x1 mm tile ({tx_}-{tx_ + 1}, {ty_}-{ty_ + 1}) holds {100 * acc[kk] / tot:.0f}%")
        log(f"   {nm:14s}: " + "; ".join(txt) + f"; peak |J| {J[jm]:.0f} A/mm2 per A at {where(N.mx[face][jm], N.my[face][jm])}"
            f" ({N.net[face][jm].split('/')[-1]}, {N.lay[face][jm]})")

    for ph in phases:
        if 'src' not in ph or ph['shunt'] is None:
            continue
        k = col[ph['src']]
        cuk = (N.kind <= 3) & np.isin(N.net, [ph['net_in'], ph['net_out']])
        loss = Ib[cuk, k] ** 2 / N.g[cuk]
        tot = loss.sum()
        pts_ = shapely.points(N.mx[cuk], N.my[cuk])
        pin = unary_union([p['poly'] for p in drv['pads'] if p['net'] == ph['net_in']])
        dpin = shapely.distance(pin, pts_)
        pads_ = unary_union([p['poly'].buffer(0.05) for p in ph['shunt']['fp']['pads']])
        onpad = shapely.contains(pads_, pts_)
        isin = N.net[cuk] == ph['net_in']
        bands = [('pin pad and first 0.5 mm', isin & (dpin < 0.5)), ('0.5-1.5 mm from the pin', isin & (dpin >= 0.5) & (dpin < 1.5)),
                 ('shunt pads', onpad), ('rest of the pin-side pour', isin & (dpin >= 1.5) & ~onpad),
                 ('connector side (after the shunt)', ~isin & ~onpad)]
        log(f"   {ph['src']} copper loss by region ({fmt_r(tot)} total): " + ", ".join(
            f"{nm_} {100 * loss[m_].sum() / tot:.0f}%" for nm_, m_ in bands))

    # ------------------------------------------------------------------ 8. leverage
    log("\n== Irreplaceable copper (exact leverage rho: 1 = sole path; 0.5 = sheet; first-order prices are low by 1/(1-rho))")
    for nm in srcs:
        k = col[nm]
        cand = sel[(N.kind[sel] <= 1) & (np.abs(Ib[sel, k]) > 0.02)]
        hi = cand[rho_ex[cand] > 0.9]
        if len(hi):
            cost = Ib[hi, k] ** 2 / (N.g[hi] * np.maximum(1 - rho_ex[hi], 1e-12))
            w_ = hi[np.argmax(cost)]
            log(f"   {nm:14s}: {len(hi)} faces with rho > 0.9 carry > 2% of it; worst single-face removal at {where(N.mx[w_], N.my[w_])}"
                f" ({N.net[w_].split('/')[-1]}): +{pct(cost.max(), Rself[nm]):.1f}% R,"
                f" first-order +{pct(Ib[w_, k] ** 2 / N.g[w_], Rself[nm]):.3f}%"
                f" (x{1 / max(1 - rho_ex[w_], 1e-12):.0f})")
    okr = np.isfinite(rho_ex) & face & (load_any > 0.01)
    log(f"   exact price / first-order (Tellegen) price = 1/(1 - rho) over the {okr.sum()} loaded faces with exact rho: median"
        f" {np.median(1 / (1 - rho_ex[okr])):.2f}, 10-90% {np.percentile(1 / (1 - rho_ex[okr]), 10):.2f}-"
        f"{np.percentile(1 / (1 - rho_ex[okr]), 90):.2f}")
    for net in dc_nets:
        mm = face & (N.net == net)
        if mm.sum() > 100:
            log(f"   leverage map {net.split('/')[-1]:10s} (sketch): median {np.median(rho_sk[mm]):.2f};"
                f" faces with rho > 0.9: {100 * np.mean(rho_sk[mm] > 0.9):.1f}%")

    # ------------------------------------------------------------------ 9. dead copper
    log("\n== Dead copper at DC: islands and 1 mm tiles carrying < 0.1% of every modelled source")
    nodeflow = np.zeros(N.nn)
    smax = np.max(np.abs(Ib[:, :ns]), axis=1)
    np.maximum.at(nodeflow, N.a, smax)
    np.maximum.at(nodeflow, N.b, smax)
    for net in dc_nets:
        for ly in b.cu:
            R = N.rasters.get((net, ly))
            if R is None:
                continue
            ids = R['ids']
            mem = ids >= 0
            lab, nl = ndimage.label(mem)
            flow = np.where(mem, nodeflow[np.maximum(ids, 0)], 0.0)
            ca = R['h'] ** 2
            tot_area = mem.sum() * ca
            iflow = ndimage.maximum(flow, lab, np.arange(1, nl + 1)) if nl else np.zeros(0)
            iarea = ndimage.sum(mem, lab, np.arange(1, nl + 1)) * ca if nl else np.zeros(0)
            dead = np.nonzero(iflow < 1e-3)[0]
            dead_area = iarea[dead].sum()
            live = mem & ~np.isin(lab, dead + 1)
            ti = (np.arange(R['nx']) * R['h']).astype(int)
            tj = (np.arange(R['ny']) * R['h']).astype(int)
            tkey = tj[:, None] * 10000 + ti[None, :]
            u, inv = np.unique(tkey[live], return_inverse=True)
            tmax = np.zeros(len(u))
            np.maximum.at(tmax, inv, flow[live])
            idle = (np.bincount(inv) * ca)[tmax < 1e-3].sum()
            if tot_area > 0.5 and (dead_area > 0.1 or idle > 0.5):
                big = dead[np.argsort(-iarea[dead])][:3]
                bt = []
                for q in big:
                    jj, ii = np.nonzero(lab == q + 1)
                    cxy = (R['x0'] + (ii.mean() + 0.5) * R['h'], R['y0'] + (jj.mean() + 0.5) * R['h'])
                    bt.append(f"{iarea[q]:.2f} mm2 at {where(*cxy)}")
                log(f"   {net.split('/')[-1]:10s} {ly:6s}: {tot_area:6.1f} mm2; {len(dead)} dead islands ({dead_area:.1f} mm2)"
                    + (f", largest {', '.join(bt)}" if bt else "") + f"; idle 1 mm tiles inside live copper {idle:.1f} mm2"
                    f" ({100 * idle / tot_area:.0f}%)")
    flo = [(f['ref'], p['num'], p['poly'].area, p['layers']) for f in b.fps for p in f['pads']
           if p['net'] and p['net'].startswith('unconnected') and p['poly'].area > 1.0]
    if flo:
        log("   floating metal (unconnected pads > 1 mm2): " + ", ".join(f"{r}.{n} {a:.1f} mm2 on {'/'.join(l)}" for r, n, a, l in flo))

    # ------------------------------------------------------------------ 10. common impedance
    log("\n== Quiet ports that share copper with power current (common impedance): exact value and Tellegen attribution")
    keyt = np.array([f"{n.split('/')[-1]}/{l}" for n, l in zip(N.net, N.lay)], object)
    tx, ty = np.floor(N.mx / 0.5).astype(int), np.floor(N.my / 0.5).astype(int)
    lumped_idx = [k for _, k in lumped]
    for qn in pdef:
        q = col[qn]
        for pn in srcs:
            p = col[pn]
            Z = float(S[:, q] @ Phi[:, p])
            if abs(Z) < 1e-10:
                continue
            a_b = Ib[:, q] * Ib[:, p] / N.g
            lump = float(a_b[lumped_idx].sum())
            cu = Z - lump
            if qn.startswith('Kelvin'):
                if abs(lump) < 1e-9:
                    continue
                ph = next(x for x in phases if x.get('port') == qn)
                R0 = ph['shunt']['ohm']
                err = Z / R0 - 1
                ph_ = Phi[:, p]
                outer_err = ((ph_[ph['outer'][0]] - ph_[ph['inA']].mean()) + (ph_[ph['inB']].mean() - ph_[ph['outer'][1]])) / R0
                log(f"   {qn} <- {pn}: {fmt_r(Z)} per A for a {fmt_r(R0)} shunt: gain error {100 * err:+.2f}%"
                    f" (shared copper {100 * cu / R0:+.2f}%, uneven current across the element {100 * (lump - R0) / R0:+.2f}%);"
                    f" the copper part drifts {cu / R0 * TCR_CU * 1e6:+.0f} ppm/K. Counterfactual: taps at the pads' outer edges"
                    f" would read {100 * outer_err:+.1f}% ({outer_err * TCR_CU * 1e6:+.0f} ppm/K)")
            else:
                log(f"   {qn} <- {pn}: {cu * 1e6:+.2f} uOhm (= {cu * 1e6 * I0:+.2f} uV at {I0:g} A)")
            ac = a_b.copy()
            ac[lumped_idx] = 0
            if np.abs(ac).sum() == 0:
                continue
            chi = abs(ac.sum()) / np.abs(ac).sum()
            big = np.nonzero(np.abs(ac) > 1e-4 * np.abs(ac).max())[0]
            tiles = defaultdict(float)
            for kk in big:
                tiles[(keyt[kk], tx[kk], ty[kk])] += ac[kk]
            topt = sorted(tiles.items(), key=lambda t: -abs(t[1]))[:4]
            log(f"      chi = {chi:.2f}; largest terms (0.5 mm tiles): " + "; ".join(
                f"{k_[0]} at ({(k_[1] + 0.5) * 0.5:.2f}, {(k_[2] + 0.5) * 0.5:.2f}) {pct(v_, cu):+.0f}%" for k_, v_ in topt))

    # ------------------------------------------------------------------ 11-12. HF and floor
    hf = None
    if not args.no_hf:
        try:
            hf = run_hf(b, roles, N, Ib, sdef, col, args)
        except (ValueError, StopIteration) as e:
            log(f"\n== HF hot loop skipped: {e}")
    fl = run_floor(b, roles, N, Ib, col, args) if not args.no_floor else None
    log(f"\nTotal runtime {tic() - T0:.0f} s")
    return dict(board=b, roles=roles, N=N, Phi=Phi, Ib=Ib, S=S, col=col, sources=sdef, ports=pdef, hf=hf, floor=fl)


if __name__ == '__main__':
    main()
