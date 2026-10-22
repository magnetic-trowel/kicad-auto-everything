#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics-critic prototype: return-path and plane-integrity metrics from a .kicad_pcb.

Workstream 9 (physics critics). Reads a routed KiCad 6-10 board with *saved zone
fills* (refill first, e.g. `kicad-cli pcb drc --refill-zones --save-board`) and
computes, without KiCad:

  RET-COV   per edge-critical net: share of track length over the nearest adjacent
            reference fill (eroded by w/2 + k*h), void crossings, reference net
            identity, and RPQF-lite = estimated loop L / ideal loop L
            (a cheap stand-in for Cadence's return-path quality factor).
  RET-VIA   layer changes of edge-critical nets whose two reference planes differ,
            with the distance to the nearest return via (same net, both planes).
  PLANE-PERF  plane layers (one GND/power net fills >= 30 % of the board): foreign
            tracks on them, islands, and slots (holes > 2 mm) with half-wave f.
  PWR-TRACE GND/power nets connected by thin traces instead of pours.
  CAVITY    largest empty circle between GND stitching vias over two GND fills,
            and the resulting first cavity-mode estimate.

`--selftest` plants DRC-neutral faults in memory (slot under a net, a foreign track
through the plane, deleted return vias, swapped plane nets) plus benign controls,
and reports which critic fired at the planted site (mutation testing, idea V1).

Net roles come from name regexes here; the real system takes them from the role
model. With --roles FILE (written by suite_passports.py --roles-out), ground and power
nets come from the inferred roles where those exist (regex otherwise; a name-matched net
the inference rejects, or a switch node, is a signal), and every marker records its role
source. Edge-critical nets still come from FAST_RE. All thresholds are defaults to be replaced by budgets. On a board with no
reference fill at all, the VOID detour saturates at the 50 mm ray and RPQF-lite is
meaningless. Results on four open boards: docs/topics/physics/physics-critics.md.

Usage:  python3 -I pc_refplane.py BOARD.kicad_pcb [--json OUT] [--all-signals] [--roles ROLES.json]
                                  [--k 1.0] [--via-dmax 2.0] [--selftest] [--seed 1]
Each critic runs in isolation: an exception is recorded under "errors" and the others still run.
Needs:  shapely>=2, numpy, scipy.  Deterministic for a given --seed.
"""
import argparse
import json
import math
import random
import re
import sys
import time
import traceback

import numpy as np
from scipy.spatial import cKDTree
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.prepared import prep

MU0 = 4e-7 * math.pi
C0 = 299792458.0
TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')
GND_RE = re.compile(r'(^|[^A-Z])(A|D|P|S|C)?GND|^/?VSS|^0V$', re.I)
PWR_RE = re.compile(r'^/?(\+?\d+(\.\d+)?V\d*|\+[A-Z0-9_.]+|V(CC|DD|BUS|IN|SYS|BAT|MOT|M|PP|REG|CORE|CAP)[A-Z0-9_.]*|'
                    r'[AD]V(DD|CC)[A-Z0-9_]*|\d+V\d+|[0-9]+V[0-9]*_?[A-Z]*)$', re.I)
FAST_RE = re.compile(r'USB|D[PM]$|D[+-]$|^/?D[PN]\d|CLK|SCK|XTAL|XI$|XO$|OSC|SDIO|SD_?(CMD|DAT|CLK)|MMC|ETH|RGMII|'
                     r'RMII|MDI|TXD|RXD|TX[PN]|RX[PN]|PCIE|HDMI|TMDS|MIPI|CSI|DSI|LVDS|QSPI|MOSI|MISO|SWCLK|'
                     r'SWDIO|CAN_?[HL]|RF|ANT|^/?SW\d?$|LX', re.I)


# ----------------------------------------------------------------------------- parsing
def parse(text):
    stack = [[]]
    for m in TOK.finditer(text):
        t = m.group(0)
        if t == '(':
            stack.append([])
        elif t == ')':
            x = stack.pop()
            stack[-1].append(x)
        else:
            stack[-1].append(t[1:-1] if t[0] == '"' else t)
    return stack[0][0]


def kids(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def first(node, name):
    for c in node:
        if isinstance(c, list) and c and c[0] == name:
            return c
    return None


def xy(node):
    return float(node[1]), float(node[2])


def rot(x, y, deg):
    a = math.radians(deg)  # KiCad: y down, positive angle = counter-clockwise on screen
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def arc_points(s, m, e, n=8):
    """Points on the circle through s, m, e (start, mid, end), from s to e via m."""
    (x1, y1), (x2, y2), (x3, y3) = s, m, e
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return [s, e]
    ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1, a2, a3 = (math.atan2(p[1] - uy, p[0] - ux) for p in (s, m, e))

    def ccw(a, b):
        return (b - a) % (2 * math.pi)
    span = ccw(a1, a3)
    if ccw(a1, a2) > span:  # mid not on the ccw sweep: go the other way
        span -= 2 * math.pi
    return [(ux + r * math.cos(a1 + span * i / n), uy + r * math.sin(a1 + span * i / n)) for i in range(n + 1)]


class Board:
    def __init__(self, path, roles=None):
        tree = parse(open(path, encoding='utf-8', errors='replace').read())
        self.skipped = {}
        self.roles = roles
        self._rg = set(roles.get('ground', ())) if roles else set()
        self._rp = set(roles.get('power', ())) if roles else set()
        self._rs = set(roles.get('rejected_power', ())) | set(roles.get('switch_nodes', ())) if roles else set()
        self._sw = set(roles.get('switch_nodes', ())) if roles else set()
        self.netname = {}
        for n in kids(tree, 'net'):
            if len(n) >= 3:
                self.netname[n[1]] = n[2]
        self._stack(tree)
        self.segments, self.vias, self.pads = [], [], []
        self.fills = {}  # (layer, net) -> geometry
        if not self.cu:
            raise ValueError('no copper layers in the layer table')

        def guarded(kind, fn, node):
            try:
                fn(node)
            except (TypeError, ValueError, IndexError, KeyError, AttributeError):
                self.skipped[kind] = self.skipped.get(kind, 0) + 1
        guarded_seg = lambda s: self._track(s, [xy(first(s, 'start')), xy(first(s, 'end'))])  # noqa: E731
        guarded_arc = lambda a: self._track(a, arc_points(xy(first(a, 'start')), xy(first(a, 'mid')), xy(first(a, 'end'))))  # noqa: E731
        for s in kids(tree, 'segment'):
            guarded('segment', guarded_seg, s)
        for a in kids(tree, 'arc'):
            guarded('arc', guarded_arc, a)

        def via(v):
            ly = first(v, 'layers')
            x, y = xy(first(v, 'at'))
            sz = first(v, 'size')
            dr = first(v, 'drill')
            size = float(sz[1]) if sz else (float(dr[1]) + 0.2 if dr else 0.6)
            self.vias.append(dict(x=x, y=y, size=size, net=self._net(v),
                                  layers=self._span(ly[1], ly[2]) if ly and len(ly) >= 3 else list(self.cu),
                                  uuid=(first(v, 'uuid') or [None, None])[1]))
        for v in kids(tree, 'via'):
            guarded('via', via, v)
        for fp in kids(tree, 'footprint') + kids(tree, 'module'):
            guarded('footprint', self._footprint, fp)
        for z in kids(tree, 'zone'):
            net = self._net(z) or (first(z, 'net_name') or [None, ''])[1]
            if not net or first(z, 'keepout'):
                continue
            zl = first(z, 'layer')
            for fpoly in kids(z, 'filled_polygon'):
                fl = first(fpoly, 'layer') or zl
                pl = first(fpoly, 'pts')
                if not fl or not pl:
                    self.skipped['filled_polygon'] = self.skipped.get('filled_polygon', 0) + 1
                    continue
                layer = fl[1]
                pts = [xy(p) for p in pl if isinstance(p, list) and p[0] == 'xy']
                if len(pts) >= 3:
                    g = Polygon(pts).buffer(0)  # KiCad stores fractured (keyhole) polygons
                    key = (layer, net)
                    self.fills[key] = unary_union([self.fills[key], g]) if key in self.fills else g
        self.outline = self._outline(tree)
        self.area = self.outline.area if self.outline is not None else 0.0
        if self.area <= 0:   # no closed Edge.Cuts: the envelope of the copper
            parts = list(self.fills.values()) + [p['shape'] for p in self.pads]
            self.area = unary_union(parts).envelope.area if parts else 0.0
            self.area_src = 'copper envelope'
        else:
            self.area_src = 'Edge.Cuts'

    # ---- helpers
    def _net(self, node):
        n = first(node, 'net')
        if not n or len(n) < 2:
            return None
        if len(n) >= 3:
            return n[2]
        return self.netname.get(n[1], n[1])

    def _stack(self, tree):
        lay = first(tree, 'layers')
        names = [e[1] for e in lay[1:] if isinstance(e, list) and len(e) > 2 and str(e[1]).endswith('.Cu')]

        def order(nm):
            return -1 if nm == 'F.Cu' else 999 if nm == 'B.Cu' else int(re.sub(r'\D', '', nm) or 0)
        self.cu = sorted(names, key=order)
        self.z, self.er, self.tcu = {}, {}, {}
        su = first(first(tree, 'setup') or [], 'stackup')
        z, last_cu, er = 0.0, None, []
        if su:
            for e in kids(su, 'layer'):
                t = first(e, 'thickness')
                th = float(t[1]) if t and len(t) > 1 and re.match(r'^[\d.]+$', str(t[1])) else 0.0
                typ = (first(e, 'type') or [None, ''])[1]
                if str(e[1]).endswith('.Cu'):
                    self.z[e[1]] = z + th / 2
                    self.tcu[e[1]] = th or 0.035
                    if last_cu is not None and er:
                        self.er[(last_cu, e[1])] = sum(er) / len(er)
                    last_cu, er = e[1], []
                    z += th
                elif typ in ('core', 'prepreg') or 'dielectric' in str(e[1]):
                    z += th
                    epsr = first(e, 'epsilon_r')
                    er.append(float(epsr[1]) if epsr else 4.5)
        if len(self.z) != len(self.cu):  # no stackup: spread copper evenly over the board thickness
            th = float((first(first(tree, 'general') or [], 'thickness') or [0, 1.6])[1])
            n = max(1, len(self.cu) - 1)
            self.z = {nm: th * i / n for i, nm in enumerate(self.cu)}
            self.tcu = {nm: 0.035 for nm in self.cu}
        self.cu = sorted(self.cu, key=lambda nm: self.z[nm])

    def _span(self, a, b):
        if a not in self.z or b not in self.z:
            return list(self.cu)
        lo, hi = sorted((self.z[a], self.z[b]))
        return [nm for nm in self.cu if lo - 1e-9 <= self.z[nm] <= hi + 1e-9]

    def _track(self, node, pts):
        ly = first(node, 'layer') or [None] + [n for n in (first(node, 'layers') or [])[1:] if n.endswith('.Cu')]
        if len(ly) < 2 or ly[1] not in self.z:
            raise ValueError('track without a known copper layer')
        self.segments.append(dict(layer=ly[1], net=self._net(node),
                                  w=float(first(node, 'width')[1]), pts=pts,
                                  uuid=(first(node, 'uuid') or [None, None])[1]))

    def _footprint(self, fp):
        at = first(fp, 'at')
        fx, fy = xy(at)
        fr = float(at[3]) if len(at) > 3 else 0.0
        ref = next((p[2] for p in kids(fp, 'property') if len(p) > 2 and p[1] == 'Reference'),
                   next((p[2] for p in kids(fp, 'fp_text') if len(p) > 2 and p[1] == 'reference'), '?'))
        for pd in kids(fp, 'pad'):
            pat = first(pd, 'at')
            px, py = xy(pat)
            pr = float(pat[3]) if len(pat) > 3 else 0.0
            dx, dy = rot(px, py, fr)
            sz = first(pd, 'size')
            sx, sy = (float(sz[1]), float(sz[2])) if sz else (0.5, 0.5)
            ly = first(pd, 'layers') or ['layers']
            layers = set()
            for nm in ly[1:]:
                if nm in ('*.Cu', 'F&B.Cu'):
                    layers |= set(self.cu) if nm == '*.Cu' else {'F.Cu', 'B.Cu'}
                elif nm in self.z:
                    layers.add(nm)
            shape = affinity.translate(affinity.rotate(box(-sx / 2, -sy / 2, sx / 2, sy / 2), -pr, origin=(0, 0)),
                                       fx + dx, fy + dy)
            self.pads.append(dict(x=fx + dx, y=fy + dy, net=self._net(pd), layers=layers, shape=shape, ref=ref,
                                  through=pd[2] == 'thru_hole' if len(pd) > 2 else False))

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
                pts = [xy(p) for p in first(g, 'pts') if isinstance(p, list) and p[0] == 'xy']
                lines.append(LineString(pts + pts[:1]))
            elif g[0] == 'gr_circle':
                (cx, cy), (ex, ey) = xy(first(g, 'center')), xy(first(g, 'end'))
                lines.append(Point(cx, cy).buffer(math.hypot(ex - cx, ey - cy)).exterior)
        polys = list(polygonize(unary_union(lines))) if lines else []
        return max(polys, key=lambda p: p.area) if polys else None

    # ---- derived views
    def role(self, net):
        if not net:
            return 'none'
        if self.roles:
            if net in self._rg:
                return 'gnd'
            if net in self._rp:
                return 'power'
            if net in self._rs:
                return 'signal'
        return self.regex_role(net)

    @staticmethod
    def regex_role(net):
        if not net:
            return 'none'
        if GND_RE.search(net):
            return 'gnd'
        if PWR_RE.search(net.split('/')[-1]):
            return 'power'
        return 'signal'

    def role_src(self, net):
        """'inferred' when the role came from the passport role inference, else 'regex'."""
        if not net or not self.roles:
            return 'regex'
        return 'inferred' if net in self._rg or net in self._rp or net in self._rs else 'regex'

    def neighbors(self, layer):
        """Adjacent copper layers with dielectric distance h (mm) and eps_r."""
        i = self.cu.index(layer)
        out = []
        for j in (i - 1, i + 1):
            if 0 <= j < len(self.cu):
                other = self.cu[j]
                h = abs(self.z[other] - self.z[layer]) - (self.tcu[other] + self.tcu[layer]) / 2
                er = self.er.get((self.cu[min(i, j)], self.cu[max(i, j)]), 4.5)
                out.append((max(h, 0.02), other, er))
        return sorted(out)

    def ref_fill(self, layer):
        g = [geom for (ly, net), geom in self.fills.items() if ly == layer and self.role(net) in ('gnd', 'power')]
        return unary_union(g) if g else Polygon()

    def plane_layers(self, frac=0.30):
        out = {}
        for ly in self.cu:
            best = max(((g.area, net) for (l2, net), g in self.fills.items() if l2 == ly), default=(0, None))
            if best[1] and self.role(best[1]) in ('gnd', 'power') and best[0] >= frac * self.area:
                out[ly] = best[1]
        return out


# ----------------------------------------------------------------------------- physics
def lprime(w, h):
    """Microstrip partial loop inductance per length (H/m), Hammerstad/Wheeler; eps_r-free."""
    u = w / h
    if u <= 1:
        return MU0 / (2 * math.pi) * math.log(8 / u + u / 4)
    return MU0 / (u + 1.393 + 0.667 * math.log(u + 1.444))


def slot_l(d_left, d_right, er, z_slot=100.0):
    """Excess inductance (H) of a void crossed by a trace, modelled as two shorted slot-line
    stubs (lengths in mm to the void ends) in parallel. Uncalibrated proxy [I]."""
    v = C0 / math.sqrt((er + 1) / 2)
    dl, dr = d_left * 1e-3, d_right * 1e-3
    return z_slot / v * (dl * dr / (dl + dr)) if dl + dr > 0 else 0.0


# ----------------------------------------------------------------------------- critics
def is_fast(b, net, all_signals):
    r = b.role(net)
    return r == 'signal' and (all_signals or bool(FAST_RE.search(net or '')))


def critic_ret_cov(b, k=1.0, all_signals=False, ray_mm=50.0):
    refs = {ly: b.ref_fill(ly) for ly in b.cu}
    eroded = {}

    def er_fill(ly, m):
        key = (ly, round(m, 3))
        if key not in eroded:
            eroded[key] = refs[ly].buffer(-m)
        return eroded[key]
    own_void = {}
    for v in b.vias:
        own_void.setdefault(v['net'], []).append(Point(v['x'], v['y']).buffer(v['size'] / 2 + 0.6))
    for p in b.pads:
        own_void.setdefault(p['net'], []).append(p['shape'].buffer(0.6))
    own_void = {n: unary_union(g) for n, g in own_void.items()}
    nets, markers = {}, []
    for s in b.segments:
        if not is_fast(b, s['net'], all_signals) or s['layer'] not in b.z:
            continue
        line = LineString(s['pts'])
        if line.length < 1e-6:
            continue
        nb = b.neighbors(s['layer'])
        if not nb:
            continue
        h1, l1, er1 = nb[0]
        e1 = er_fill(l1, s['w'] / 2 + k * h1)
        cov1 = line.intersection(e1)
        cov_any, e2, h2 = cov1, None, None
        if len(nb) > 1:
            h2, l2, _ = nb[1]
            e2 = er_fill(l2, s['w'] / 2 + k * h2)
            cov_any = cov1.union(line.intersection(e2))
        rec = nets.setdefault(s['net'], dict(length=0.0, primary=0.0, any=0.0, l_ideal=0.0, l_est=0.0,
                                             crossings=0, hops=0, edges=0, ref_nets={}, max_detour_mm=0.0))
        L = line.length
        rec['length'] += L
        rec['primary'] += cov1.length
        rec['any'] += cov_any.length
        lp1 = lprime(s['w'], h1)
        rec['l_ideal'] += lp1 * L * 1e-3
        rec['l_est'] += lp1 * L * 1e-3  # excess terms are added per gap piece below
        mid = line.interpolate(0.5, normalized=True)
        for (ly, net), g in b.fills.items():
            if ly == l1 and b.role(net) in ('gnd', 'power') and g.distance(mid) < s['w']:
                rec['ref_nets'][net] = rec['ref_nets'].get(net, 0.0) + L
                break
        gaps = line.difference(cov1)
        ov = own_void.get(s['net'])
        edge_parts = gaps.intersection(refs[l1])
        if ov is not None:  # crowding at the net's own pads and vias is fan-out, not a defect
            edge_parts = edge_parts.difference(ov)
        for gp in getattr(edge_parts, 'geoms', [edge_parts]):
            if gp.is_empty or gp.geom_type != 'LineString' or gp.length < 0.05:
                continue
            p = gp.interpolate(0.5, normalized=True)  # over copper, closer than w/2 + k*h to its edge
            rec['l_est'] += lp1 * gp.length * 0.25e-3  # crowding penalty, small [I]
            rec['edges'] += 1
            markers.append(dict(critic='RET-EDGE', severity='info', net=s['net'], layer=s['layer'],
                                pos=[round(p.x, 3), round(p.y, 3)], measured=round(gp.length, 3), unit='mm',
                                detail=f"trace within w/2+{k}h of a reference edge on {l1} (h={h1:.3f} mm)",
                                fix='keep >= w/2 + 3h from plane edges and voids'))
        void_parts = gaps.difference(refs[l1])
        for gp in getattr(void_parts, 'geoms', [void_parts]):
            if gp.is_empty or gp.geom_type != 'LineString' or gp.length < 0.05:
                continue
            p = gp.interpolate(0.5, normalized=True)
            (x0, y0), (x1, y1) = gp.coords[0], gp.coords[-1]
            n = math.hypot(x1 - x0, y1 - y0) or 1.0
            nx, ny = -(y1 - y0) / n, (x1 - x0) / n
            ext = []
            for sg in (1, -1):  # distance along the perpendicular to the reference copper
                ray = LineString([(p.x, p.y), (p.x + sg * nx * ray_mm, p.y + sg * ny * ray_mm)])
                hit = ray.intersection(refs[l1])
                ext.append(min((p.distance(g) for g in getattr(hit, 'geoms', [hit]) if not g.is_empty),
                               default=ray_mm))
            if ov is not None and gp.within(ov.buffer(1e-6)) and max(ext) <= 2.0:
                continue  # the antipad of the net's own pad or via, not a plane void
            if e2 is not None and e2.contains(p):  # return hops to the farther plane
                rec['l_est'] += (lprime(s['w'], h2) - lp1) * gp.length * 1e-3
                rec['hops'] += 1
                markers.append(dict(critic='RET-HOP', severity='info', net=s['net'], layer=s['layer'],
                                    pos=[round(p.x, 3), round(p.y, 3)], measured=round(gp.length, 3), unit='mm',
                                    detail=f"no copper on near reference {l1}; return moves to {l2} (h={h2:.3f} mm)",
                                    fix='restore the near reference under the trace'))
                continue
            lx = slot_l(ext[0], ext[1], er1)
            rec['l_est'] += lp1 * gp.length * 1e-3 + lx  # unreferenced piece: double L' + detour
            rec['crossings'] += 1
            rec['max_detour_mm'] = max(rec['max_detour_mm'], min(ext))
            markers.append(dict(critic='RET-COV', severity='warning', net=s['net'], layer=s['layer'],
                                pos=[round(p.x, 3), round(p.y, 3)], measured=round(gp.length, 3), unit='mm',
                                detail=f"void under trace on ref {l1} (h={h1:.3f} mm); detour to plane "
                                       f"{min(ext):.1f}/{max(ext):.1f} mm; excess L~{lx * 1e9:.2f} nH [I]",
                                fix='move trace off the void, or bridge the void / add stitching'))
    for net, r in nets.items():
        r['primary_pct'] = round(100 * r['primary'] / r['length'], 1)
        r['any_pct'] = round(100 * r['any'] / r['length'], 1)
        r['rpqf_lite'] = round(r['l_est'] / r['l_ideal'], 3) if r['l_ideal'] else None
        pw = [n for n in r['ref_nets'] if b.role(n) == 'power']
        if pw:
            markers.append(dict(critic='RET-REFNET', severity='info', net=net, layer=None, pos=None,
                                measured=round(sum(r['ref_nets'][n] for n in pw), 2), unit='mm',
                                detail=f"references power net(s) {pw}; return crosses to GND through decaps",
                                ref_role_src={n_: b.role_src(n_) for n_ in pw},
                                fix='reference to GND, or place a stitching cap at each end'))
        for key in ('primary', 'any', 'l_est', 'l_ideal'):
            r.pop(key)
        r['length'] = round(r['length'], 2)
        r['ref_nets'] = sorted(r['ref_nets'])
        r['max_detour_mm'] = round(r['max_detour_mm'], 2)
    return nets, markers


def critic_ret_via(b, dmax=2.0, all_signals=False):
    ends = {}
    for s in b.segments:
        for pt in (s['pts'][0], s['pts'][-1]):
            ends.setdefault(s['net'], []).append((pt, s['layer']))
    fills_by_layer = {}
    for (ly, net), g in b.fills.items():
        if b.role(net) in ('gnd', 'power'):
            fills_by_layer.setdefault(ly, []).append((net, prep(g)))
    markers, n_checked = [], 0
    for v in b.vias:
        if not is_fast(b, v['net'], all_signals):
            continue
        used = sorted({ly for (pt, ly) in ends.get(v['net'], [])
                       if math.hypot(pt[0] - v['x'], pt[1] - v['y']) <= v['size'] / 2 + 1e-3})
        if len(used) < 2:
            continue
        n_checked += 1
        p = Point(v['x'], v['y']).buffer(v['size'] / 2 + 0.8)  # reach past the via's own antipad
        refs = set()
        for ly in used:
            nbs = b.neighbors(ly)
            if not nbs:
                continue
            _, l1, _ = nbs[0]
            for net, g in sorted(fills_by_layer.get(l1, []), key=lambda t: b.role(t[0]) != 'gnd'):
                if g.intersects(p):
                    refs.add((l1, net))
                    break
        if len(refs) < 2:
            continue
        nets = {n for _, n in refs}
        lys = {l for l, _ in refs}
        if len(nets) > 1:
            # return crosses nets through the nearest capacitor bridging them: plane-pair spreading
            # L = mu0*t/pi*ln(D/r) between the two vias, plus ~1 nH cap mounting [I]
            na, nb_ = sorted(nets)
            caps = {}
            for pd in b.pads:
                if pd['ref'].startswith('C') and pd['net'] in nets:
                    caps.setdefault(pd['ref'], {})[pd['net']] = (pd['x'], pd['y'])
            dist = min((math.dist(c[na], (v['x'], v['y'])) for c in caps.values() if na in c and nb_ in c),
                       default=None)
            if len(lys) >= 2:
                (la, lb) = sorted(lys, key=lambda l: b.z[l])[:2]
                t_pp = abs(b.z[lb] - b.z[la])
                l_x = (MU0 * t_pp * 1e-3 / math.pi * math.log(max(dist, 0.3) / 0.15) + 1e-9) if dist else None
            else:      # both used layers see the same reference layer, with different nets next to the via
                t_pp, l_x = 0.0, None
            markers.append(dict(critic='RET-VIA', severity='warning', net=v['net'], layer='/'.join(used),
                                pos=[v['x'], v['y']], measured=round(l_x * 1e9, 2) if l_x else None, unit='nH',
                                detail=f"reference changes net {sorted(nets)}: return through nearest bridging cap at "
                                       f"{dist if dist is None else round(dist, 1)} mm, est. +{'?' if not l_x else round(l_x * 1e9, 1)} nH "
                                       f"(plane gap {t_pp:.2f} mm) [I]; Ott: 5-10 nH"
                                       + ('' if len(lys) >= 2 else '; both nets on one reference layer: no plane-pair estimate'),
                                ref_role_src={n_: b.role_src(n_) for n_ in sorted(nets)},
                                fix='keep both segments on layers referenced to the same net, or add a stitching cap'))
            continue
        net = nets.pop()
        if len(lys) < 2:
            continue
        cands = [math.hypot(o['x'] - v['x'], o['y'] - v['y']) for o in b.vias
                 if o['net'] == net and lys <= set(o['layers'])]
        cands += [math.hypot(pd['x'] - v['x'], pd['y'] - v['y']) for pd in b.pads
                  if pd['net'] == net and pd['through'] and lys <= pd['layers']]
        d = min(cands, default=float('inf'))
        if d > dmax:
            markers.append(dict(critic='RET-VIA', severity='warning', net=v['net'], layer='/'.join(used),
                                pos=[v['x'], v['y']], measured=round(d, 2) if d < 1e9 else None, unit='mm',
                                detail=f"layer change {used} switches reference {sorted(lys)} of {net}; "
                                       f"nearest return via {d:.2f} mm > {dmax} mm",
                                ref_role_src={net: b.role_src(net)},
                                fix=f'add a {net} via within {dmax} mm'))
    return dict(checked=n_checked), markers


def critic_plane(b, frac=0.30, min_slot=2.0):
    out, markers = {}, []
    for ly, pnet in b.plane_layers(frac).items():
        g = b.fills[(ly, pnet)]
        polys = list(getattr(g, 'geoms', [g]))
        foreign = {}
        for s in b.segments:
            if s['layer'] == ly and s['net'] != pnet:
                foreign[s['net']] = foreign.get(s['net'], 0.0) + LineString(s['pts']).length
        nbs = b.neighbors(ly)
        er = nbs[0][2] if nbs else 4.5
        slots = []
        for pg in polys:
            for ring in getattr(pg, 'interiors', []):
                hole = Polygon(ring)
                mrr = hole.minimum_rotated_rectangle
                if mrr.geom_type == 'Polygon':
                    xs = list(mrr.exterior.coords)
                    ln = max(math.dist(xs[i], xs[i + 1]) for i in range(len(xs) - 1))
                else:      # degenerate hole (a line or a point)
                    x0_, y0_, x1_, y1_ = hole.bounds
                    ln = math.hypot(x1_ - x0_, y1_ - y0_)
                if ln >= min_slot:
                    slots.append((ln, hole.representative_point()))
        slots.sort(key=lambda t: -t[0])
        eeff = (er + 1) / 2
        out[ly] = dict(net=pnet, role_src=b.role_src(pnet),
                       coverage_pct=round(100 * g.area / b.area, 1) if b.area > 0 else None, islands=len(polys),
                       foreign_track_mm=round(sum(foreign.values()), 2), foreign_nets=len(foreign),
                       slots_ge_min=len(slots),
                       longest_slot_mm=round(slots[0][0], 2) if slots else 0.0,
                       slot_halfwave_ghz=round(C0 / (2 * slots[0][0] * 1e-3 * math.sqrt(eeff)) / 1e9, 2) if slots else None)
        for ln, pt in slots[:5]:
            markers.append(dict(critic='PLANE-PERF', severity='info', net=pnet, layer=ly,
                                pos=[round(pt.x, 3), round(pt.y, 3)], measured=round(ln, 2), unit='mm',
                                detail=f"slot in {pnet} plane; half-wave resonance ~"
                                       f"{C0 / (2 * ln * 1e-3 * math.sqrt(eeff)) / 1e9:.2f} GHz",
                                fix='move foreign copper off the plane layer, or shorten/bridge the slot'))
        if foreign:  # outer-layer pours carry signals by design; inner planes should not
            markers.append(dict(critic='PLANE-PERF', severity='info' if ly in ('F.Cu', 'B.Cu') else 'warning',
                                net=pnet, layer=ly, pos=None,
                                measured=out[ly]['foreign_track_mm'], unit='mm',
                                detail=f"{len(foreign)} foreign net(s) routed on the {pnet} plane layer",
                                fix='route on signal layers; keep plane layers solid'))
    return out, markers


def critic_pwr_trace(b, w_thin=0.4):
    out, markers = {}, []
    nets = {s['net'] for s in b.segments} | {n for (_, n) in b.fills}
    for net in sorted(n for n in nets if b.role(n) in ('gnd', 'power')):
        segs = [s for s in b.segments if s['net'] == net]
        fill_area = sum(g.area for (ly, n), g in b.fills.items() if n == net)
        pads = [p for p in b.pads if p['net'] == net]
        fills = {ly: prep(g.buffer(0.05)) for (ly, n), g in b.fills.items() if n == net}
        landing = [Point(v['x'], v['y']) for v in b.vias if v['net'] == net
                   and any(ly in fills and fills[ly].intersects(Point(v['x'], v['y']).buffer(v['size'] / 2 + 0.3))
                           for ly in v['layers'])]

        def plane_tied(p):  # on a same-net pour, or within 2 mm of a via that lands on one
            return (any(ly in fills and fills[ly].intersects(p['shape']) for ly in p['layers'])
                    or any(q.distance(Point(p['x'], p['y'])) <= 2.0 for q in landing))
        on_pour = sum(1 for p in pads if plane_tied(p))
        thin = [s for s in segs if s['w'] < w_thin]
        r_thin = sum(1.72e-8 * LineString(s['pts']).length * 1e-3 / (s['w'] * 1e-3 * b.tcu.get(s['layer'], 0.035) * 1e-3)
                     for s in thin)
        rec = dict(role=b.role(net), role_src=b.role_src(net), pads=len(pads), pads_on_pour=on_pour,
                   fill_area_mm2=round(fill_area, 1),
                   track_mm=round(sum(LineString(s['pts']).length for s in segs), 1),
                   thin_track_mm=round(sum(LineString(s['pts']).length for s in thin), 1),
                   thin_track_r_sum_mohm=round(r_thin * 1e3, 1))
        out[net] = rec
        if pads and (fill_area == 0 or on_pour < 0.5 * len(pads)) and rec['thin_track_mm'] > 0:
            markers.append(dict(critic='PWR-TRACE', severity='warning' if rec['role'] == 'gnd' else 'info',
                                net=net, layer=None, pos=None, measured=rec['thin_track_mm'], unit='mm',
                                detail=f"{len(pads) - on_pour}/{len(pads)} pads not on (or within 2 mm of a via to) a {net} pour; "
                                       f"{rec['thin_track_mm']} mm of track < {w_thin} mm wide",
                                fix='connect through a plane or pour; widen to the current budget'))
    return out, markers


def critic_cavity(b, frac=0.20, step=1.0):
    gl = [ly for ly in b.cu for (l2, n), g in b.fills.items()
          if l2 == ly and b.role(n) == 'gnd' and g.area >= frac * b.area]
    gl = sorted(set(gl), key=lambda l: b.z[l])
    out = {}
    for i in range(len(gl)):
        for j in range(i + 1, len(gl)):
            a, c = gl[i], gl[j]
            ga = unary_union([g for (l2, n), g in b.fills.items() if l2 == a and b.role(n) == 'gnd'])
            gc = unary_union([g for (l2, n), g in b.fills.items() if l2 == c and b.role(n) == 'gnd'])
            ov = ga.intersection(gc)
            if ov.area < 1:
                continue
            pts = np.array([[v['x'], v['y']] for v in b.vias if b.role(v['net']) == 'gnd'
                            and a in v['layers'] and c in v['layers']]
                           + [[p['x'], p['y']] for p in b.pads if b.role(p['net']) == 'gnd' and p['through']])
            x0, y0, x1, y1 = ov.bounds
            gx, gy = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
            pov = prep(ov)
            grid = np.array([(x, y) for x, y in zip(gx.ravel(), gy.ravel()) if pov.contains(Point(x, y))])
            if len(grid) == 0:
                continue
            if len(pts) == 0:
                r = float('inf')
                at = grid[0]
            else:
                d, _ = cKDTree(pts).query(grid)
                r = float(d.max())
                at = grid[int(d.argmax())]
            er = 4.5
            out[f'{a}|{c}'] = dict(overlap_mm2=round(ov.area, 1), stitch_vias=len(pts),
                                   max_empty_circle_d_mm=round(2 * r, 2),
                                   first_mode_ghz=round(C0 / (2 * math.sqrt(er) * 2 * r * 1e-3) / 1e9, 2) if 0 < r < 1e9 else 0,
                                   at=[round(float(at[0]), 2), round(float(at[1]), 2)])
    return out, []


def run_all(b, args, errors=None, timing=None):
    """Run every critic; a critic that raises is recorded in errors (if given) and yields empty results."""
    res, markers = {}, []
    for name, fn in (('RET-COV', lambda: critic_ret_cov(b, args.k, args.all_signals)),
                     ('RET-VIA', lambda: critic_ret_via(b, args.via_dmax, args.all_signals)),
                     ('PLANE-PERF', lambda: critic_plane(b)),
                     ('PWR-TRACE', lambda: critic_pwr_trace(b)),
                     ('CAVITY', lambda: critic_cavity(b))):
        t0 = time.perf_counter()
        try:
            r, m = fn()
        except Exception as e:      # noqa: BLE001  (one bad geometry must not lose the other critics)
            if errors is None:
                raise
            errors.append(dict(critic=name, error=f'{type(e).__name__}: {e}', trace=traceback.format_exc()[-1500:]))
            r, m = ({'checked': 0} if name == 'RET-VIA' else {}), []
        if timing is not None:
            timing[name] = round(time.perf_counter() - t0, 3)
        for mk in m:
            mk.setdefault('role_src', b.role_src(mk.get('net')))
        res[name] = r
        markers += m
    return res, markers


# ----------------------------------------------------------------------------- mutation self-test
def _near(markers, critic, pos, r=2.5):
    return any(m['critic'] == critic and m['pos'] and math.dist(m['pos'], pos) <= r for m in markers)


def selftest(b, args, sites=4):
    rng = random.Random(args.seed)
    base_res, base_m = run_all(b, args)
    planes = b.plane_layers()
    rows = []

    def cut(layer, geom):
        saved = {k: g for k, g in b.fills.items() if k[0] == layer}
        for k in saved:
            b.fills[k] = saved[k].difference(geom)
        return saved

    def restore(saved):
        b.fills.update(saved)

    fast = [s for s in b.segments if is_fast(b, s['net'], args.all_signals) and LineString(s['pts']).length > 3]
    rng.shuffle(fast)
    # M-SLOT: 12 x 0.6 mm void across a fast trace on its nearest reference; expect RET-COV at the site
    done = 0
    for s in fast:
        if done >= sites:
            break
        h1, l1, _ = b.neighbors(s['layer'])[0]
        line = LineString(s['pts'])
        mid = line.interpolate(0.5, normalized=True)
        if not b.ref_fill(l1).buffer(-1.0).contains(mid) or _near(base_m, 'RET-COV', (mid.x, mid.y), 6):
            continue
        ang = math.degrees(math.atan2(s['pts'][-1][1] - s['pts'][0][1], s['pts'][-1][0] - s['pts'][0][0]))
        slot = affinity.rotate(box(-0.3, -6, 0.3, 6), ang, origin=(0, 0))
        saved = cut(l1, affinity.translate(slot, mid.x, mid.y))
        _, m = run_all(b, args)
        restore(saved)
        rows.append(('M-SLOT', f"{s['net']}@{mid.x:.1f},{mid.y:.1f}",
                     _near(m, 'RET-COV', (mid.x, mid.y)) or _near(m, 'RET-HOP', (mid.x, mid.y)),
                     len(m) - len(base_m)))
        done += 1
    # M-TRACE-IN-PLANE: foreign 0.2 mm track (0.2 mm clearance) through the plane under a fast trace
    done = 0
    for s in fast:
        if done >= sites:
            break
        h1, l1, _ = b.neighbors(s['layer'])[0]
        if l1 not in planes:
            continue
        line = LineString(s['pts'])
        mid = line.interpolate(0.5, normalized=True)
        if not b.ref_fill(l1).buffer(-1.0).contains(mid) or _near(base_m, 'RET-COV', (mid.x, mid.y), 6):
            continue
        ang = math.degrees(math.atan2(s['pts'][-1][1] - s['pts'][0][1], s['pts'][-1][0] - s['pts'][0][0]))
        tr = affinity.translate(affinity.rotate(LineString([(0, -5), (0, 5)]), ang, origin=(0, 0)), mid.x, mid.y)
        saved = cut(l1, tr.buffer(0.1 + 0.2))
        b.segments.append(dict(layer=l1, net='MUT_FOREIGN', w=0.2, pts=list(tr.coords), uuid=None))
        _, m = run_all(b, args)
        b.segments.pop()
        restore(saved)
        hit = _near(m, 'RET-COV', (mid.x, mid.y)) and any(x['critic'] == 'PLANE-PERF' and x['layer'] == l1
                                                          and x['severity'] == 'warning' for x in m)
        rows.append(('M-TRACE-IN-PLANE', f"{s['net']}@{mid.x:.1f},{mid.y:.1f}", hit, len(m) - len(base_m)))
        done += 1
    # M-DEL-RETURN-VIA: remove same-net return vias within 3 mm of a fast layer-change via
    ends = {}
    for s in b.segments:
        for pt in (s['pts'][0], s['pts'][-1]):
            ends.setdefault(s['net'], []).append((pt, s['layer']))
    done = 0
    for v in [v for v in b.vias if is_fast(b, v['net'], args.all_signals)]:
        if done >= sites:
            break
        used = {ly for (pt, ly) in ends.get(v['net'], []) if math.dist(pt, (v['x'], v['y'])) <= v['size'] / 2 + 1e-3}
        if len(used) < 2 or _near(base_m, 'RET-VIA', (v['x'], v['y']), 0.1):
            continue
        tracked = {pt for s in b.segments for pt in (tuple(s['pts'][0]), tuple(s['pts'][-1]))}
        gone = [o for o in b.vias if b.role(o['net']) == 'gnd' and math.dist((o['x'], o['y']), (v['x'], v['y'])) <= 3.0
                and (o['x'], o['y']) not in tracked]
        if not gone:
            continue
        keep = b.vias
        b.vias = [o for o in keep if o not in gone]
        left = min((math.dist((o['x'], o['y']), (v['x'], v['y'])) for o in b.vias
                    if b.role(o['net']) == 'gnd' and set(o['layers']) >= set(b.cu)), default=1e9)
        if left <= args.via_dmax:  # a wired return via remains: equivalent mutant, not counted
            b.vias = keep
            rows.append(('M-DEL-RETURN-VIA', v['net'], 'equivalent', 0))
            done += 1
            continue
        _, m = run_all(b, args)
        b.vias = keep
        rows.append(('M-DEL-RETURN-VIA', v['net'], _near(m, 'RET-VIA', (v['x'], v['y']), 0.1), len(m) - len(base_m)))
        done += 1
    # M-SWAP-REF: swap the nets of the two inner plane layers if they differ
    inner = [ly for ly in planes if ly not in ('F.Cu', 'B.Cu')]
    if len(inner) >= 2 and planes[inner[0]] != planes[inner[1]]:
        a, c = inner[:2]
        na, nc = planes[a], planes[c]
        ga, gc = b.fills[(a, na)], b.fills[(c, nc)]
        b.fills[(a, nc)], b.fills[(c, na)] = ga, gc
        del b.fills[(a, na)], b.fills[(c, nc)]
        _, m = run_all(b, args)
        del b.fills[(a, nc)], b.fills[(c, na)]
        b.fills[(a, na)], b.fills[(c, nc)] = ga, gc
        def sig(ms):
            return sorted((x['critic'], x['net'], x['measured']) for x in ms if x['critic'] in ('RET-REFNET', 'RET-VIA'))
        rows.append(('M-SWAP-REF', f'{a}<->{c}', sig(m) != sig(base_m), len(m) - len(base_m)))
    # B-SLOT-FAR (control): same slot where no track on either adjacent layer is within 5 mm
    done = tries = 0
    while done < sites and tries < 400 and planes:
        tries += 1
        ly = sorted(planes)[rng.randrange(len(planes))]
        g = b.fills[(ly, planes[ly])]
        x0, y0, x1, y1 = g.bounds
        p = Point(rng.uniform(x0, x1), rng.uniform(y0, y1))
        adj = {l for _, l, _ in b.neighbors(ly)} | {ly}
        if not g.buffer(-7).contains(p):
            continue
        if any(s['layer'] in adj and is_fast(b, s['net'], args.all_signals) and LineString(s['pts']).distance(p) < 4
               for s in b.segments):
            continue
        saved = cut(ly, affinity.translate(box(-0.3, -6, 0.3, 6), p.x, p.y))
        _, m = run_all(b, args)
        restore(saved)
        fired = sum(1 for x in m if x['critic'] in ('RET-COV', 'RET-VIA', 'RET-HOP')) - \
            sum(1 for x in base_m if x['critic'] in ('RET-COV', 'RET-VIA', 'RET-HOP'))
        rows.append(('B-SLOT-FAR', ly, fired != 0, len(m) - len(base_m)))
        done += 1
    # B-ADD-VIA (control): an extra GND via in a plane region
    if planes:
        ly = sorted(planes)[0]
        p = b.fills[(ly, planes[ly])].buffer(-2).representative_point()
        b.vias.append(dict(x=p.x, y=p.y, size=0.6, net=planes[ly], layers=list(b.cu), uuid=None))
        _, m = run_all(b, args)
        b.vias.pop()
        fired = sum(1 for x in m if x['critic'] in ('RET-COV', 'RET-VIA')) - \
            sum(1 for x in base_m if x['critic'] in ('RET-COV', 'RET-VIA'))
        rows.append(('B-ADD-VIA', planes[ly], fired != 0, len(m) - len(base_m)))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('board')
    ap.add_argument('--json')
    ap.add_argument('--all-signals', action='store_true', help='treat every signal net as edge-critical')
    ap.add_argument('--k', type=float, default=1.0, help='coverage margin w/2 + k*h')
    ap.add_argument('--via-dmax', type=float, default=2.0, help='return-via distance limit (mm)')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--roles', help='roles JSON from suite_passports.py --roles-out (ground, power, switch nodes)')
    args = ap.parse_args(argv)
    t_start = time.perf_counter()
    roles = None
    if args.roles:
        try:
            with open(args.roles) as f:
                roles = json.load(f)
        except (OSError, ValueError) as e:
            print(f"roles file unreadable ({e}); using name regexes", file=sys.stderr)
    try:
        b = Board(args.board, roles=roles)
    except Exception as e:      # noqa: BLE001
        if args.json:
            with open(args.json, 'w') as f:
                json.dump(dict(summary=dict(board=args.board, error=f'{type(e).__name__}: {e}'), results={}, markers=[],
                               errors=[dict(critic='parse', error=f'{type(e).__name__}: {e}', trace=traceback.format_exc()[-1500:])]),
                          f, indent=1)
        print(f"parse failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    errors, timing = [], {}
    res, markers = run_all(b, args, errors, timing)
    cov = res['RET-COV']
    summary = dict(
        board=args.board, copper_layers=b.cu, board_area_mm2=round(b.area, 1),
        fast_nets=len(cov),
        fast_track_mm=round(sum(r['length'] for r in cov.values()), 1),
        ret_cov_primary_pct_lenweighted=round(sum(r['primary_pct'] * r['length'] for r in cov.values())
                                              / max(1e-9, sum(r['length'] for r in cov.values())), 1),
        void_crossings=sum(r['crossings'] for r in cov.values()),
        ref_hops=sum(r['hops'] for r in cov.values()),
        edge_crowding=sum(r['edges'] for r in cov.values()),
        rpqf_lite_worst=max((r['rpqf_lite'] or 0 for r in cov.values()), default=None),
        ret_via_checked=res['RET-VIA'].get('checked', 0),
        markers_by_critic={c: sum(1 for m in markers if m['critic'] == c)
                           for c in sorted({m['critic'] for m in markers})},
    )
    if roles is not None or b.skipped or errors:
        nets = {s['net'] for s in b.segments} | {n for (_, n) in b.fills} | {p['net'] for p in b.pads}
        nets.discard(None)
        summary.update(
            role_source='inferred roles where present, regex otherwise' if roles is not None else 'regex',
            roles_inferred=sum(1 for n in nets if b.role_src(n) == 'inferred'),
            role_changes_vs_regex={n: [b.regex_role(n), b.role(n)] for n in sorted(nets) if b.regex_role(n) != b.role(n)},
            markers_by_role_src={src: sum(1 for m in markers if m.get('role_src') == src) for src in ('regex', 'inferred')},
            board_area_src=b.area_src, skipped_items=b.skipped, critic_errors=len(errors),
            critic_time_s=timing, runtime_s=round(time.perf_counter() - t_start, 3))
    out = dict(summary=summary, results=res, markers=markers, errors=errors)
    if args.selftest:
        rows = selftest(b, args)
        out['selftest'] = [dict(op=o, site=s, detected=d, new_markers=n) for o, s, d, n in rows]
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(out, f, indent=1, default=str)
    print(json.dumps(summary, indent=1))
    if args.selftest:
        print(f"{'operator':18} {'site':28} detected  new_markers")
        for o, s, d, n in rows:
            print(f"{o:18} {str(s)[:28]:28} {str(d):9} {n}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
