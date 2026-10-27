# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small filament PEEC (partial-element) inductance solver and power-layout experiments.

Workstream 4 (power). Conductors are axis-aligned bars (traces, pads, via barrels,
capacitor bodies) cut into parallel filaments. Partial inductances use the exact
Neumann integral for parallel filaments (Grover / Ruehli 1972):

    M = mu0/(4 pi) * [G(a2-b1) - G(a1-b1) - G(a2-b2) + G(a1-b2)],
    G(z) = z asinh(z/d) - sqrt(z^2 + d^2)

with the self term evaluated at the filament's geometric mean distance
(0.2235 (w + t) for a rectangle). Perpendicular filaments do not couple. A solid
reference plane is a perfect mirror (high-frequency / inductive limit): horizontal
currents image with reversed direction, vertical currents with the same
direction. The network (bars between named nodes) is solved by nodal analysis
with the full complex branch-impedance matrix R + j w L, so current crowding,
proximity effect and parallel-via sharing come out of the solve.

Run:  python pw_peec.py [validate|loops|scaling|vias|caps|kelvin|gate|all]

  validate  checks against closed forms (wire over plane, wide strip over plane)
  loops     lateral vs vertical vs internal-vertical commutation loops vs plane distance
  scaling   L vs w, h, l; best aspect ratio at fixed footprint area
  vias      N parallel vias between a top conductor and a plane; pitch effect
  caps      0402 decap mounting inductance (via placements) and pair orientation
  kelvin    sense-loop pickup V = M di/dt from a shunt and from a nearby hot loop
  gate      gate-loop L and common-source coupling, split vs stacked return

Deterministic, numpy only; each experiment takes seconds to about a minute.
Numbers quoted with [C] in docs/topics/physics/pdn-and-commutation.md come from here.
"""
import math
import sys

import numpy as np

MU0 = 4e-7 * math.pi
RHO = 1.72e-8
mm = 1e-3


class Net:
    def __init__(self, plane_z=None):
        self.f = []          # filaments: dict(axis, s0, s1, t1, t2, gmd, area, bar)
        self.bars = []       # (node_a, node_b, [filament indices])
        self.plane_z = plane_z
        self.alias = {}

    def tie(self, a, b):
        """Merge node b into node a (zero-impedance connection)."""
        self.alias[self.find(b)] = self.find(a)

    def find(self, a):
        while a in self.alias:
            a = self.alias[a]
        return a

    def bar(self, a, b, p0, axis, length, w, t, nw=1, nt=1):
        """Bar from node a (at p0) to node b (at p0 + length along axis).
        w = transverse width (in-plane for x/y bars: y or x; for z bars: x), t = second transverse (z for x/y, y for z)."""
        ids = []
        tr = [k for k in range(3) if k != axis]   # transverse axes, in order
        # for x bars: tr = [y, z] -> w along y, t along z; for y bars: tr = [x, z]; for z bars: tr = [x, y]
        for i in range(nw):
            for j in range(nt):
                c1 = p0[tr[0]] + (i + 0.5) * w / nw
                c2 = p0[tr[1]] + (j + 0.5) * t / nt
                fw, ft = w / nw, t / nt
                self.f.append(dict(axis=axis, s0=p0[axis], s1=p0[axis] + length, c=(c1, c2), tr=tr,
                                   gmd=0.2235 * (fw + ft), area=fw * ft))
                ids.append(len(self.f) - 1)
        self.bars.append((a, b, ids))
        return ids

    def via(self, a, b, x, y, z_top, z_bot, r=0.15 * mm, tp=25e-6, n=8):
        """Via barrel (tube) from node a at z_top down to node b at z_bot, as n filaments on a ring."""
        ids = []
        arc = 2 * math.pi * r / n
        for k in range(n):
            th = 2 * math.pi * (k + 0.5) / n
            self.f.append(dict(axis=2, s0=z_bot, s1=z_top, c=(x + r * math.cos(th), y + r * math.sin(th)), tr=[0, 1],
                               gmd=0.2235 * (arc + tp), area=arc * tp))
            ids.append(len(self.f) - 1)
        # current positive from a (top) to b (bottom) = -z direction: store sign
        self.bars.append((a, b, ids, -1))
        return ids

    # ------------------------------------------------------------------
    def _arrays(self):
        F = self.f
        ax = np.array([f["axis"] for f in F])
        s0 = np.array([f["s0"] for f in F])
        s1 = np.array([f["s1"] for f in F])
        xyz = np.zeros((len(F), 3))
        for i, f in enumerate(F):
            xyz[i, f["tr"][0]] = f["c"][0]
            xyz[i, f["tr"][1]] = f["c"][1]
        gmd = np.array([f["gmd"] for f in F])
        return ax, s0, s1, xyz, gmd

    @staticmethod
    def _mpar(a1, a2, b1, b2, d):
        def G(z):
            return z * np.arcsinh(z / d) - np.sqrt(z * z + d * d)
        return MU0 / (4 * math.pi) * (G(a2 - b1) - G(a1 - b1) - G(a2 - b2) + G(a1 - b2))

    def Lmatrix(self):
        ax, s0, s1, xyz, gmd = self._arrays()
        n = len(ax)
        L = np.zeros((n, n))
        for a in range(3):
            idx = np.nonzero(ax == a)[0]
            if len(idx) == 0:
                continue
            tr = [k for k in range(3) if k != a]
            P = xyz[idx][:, tr]
            d = np.sqrt(((P[:, None, :] - P[None, :, :]) ** 2).sum(-1))
            g = gmd[idx]
            d = np.where(d < 1e-12, g[:, None] * np.ones_like(d), d)
            M = self._mpar(s0[idx][:, None], s1[idx][:, None], s0[idx][None, :], s1[idx][None, :], d)
            L[np.ix_(idx, idx)] = M
            if self.plane_z is not None:
                zp = self.plane_z
                if a == 2:   # vertical: mirrored range, same direction
                    i0 = 2 * zp - s1[idx]
                    i1 = 2 * zp - s0[idx]
                    Pi = P
                    sgn = 1.0
                else:        # horizontal: mirrored z, reversed direction
                    i0, i1 = s0[idx], s1[idx]
                    Pi = P.copy()
                    Pi[:, 1] = 2 * zp - Pi[:, 1]   # tr[1] is z for x/y bars
                    sgn = -1.0
                di = np.sqrt(((P[:, None, :] - Pi[None, :, :]) ** 2).sum(-1))
                di = np.where(di < 1e-12, g[:, None] * np.ones_like(di), di)
                Mi = self._mpar(s0[idx][:, None], s1[idx][:, None], i0[None, :], i1[None, :], di)
                L[np.ix_(idx, idx)] += sgn * Mi
        return L

    def solve(self, port_p, port_n, f=1e8, inductive=True, extra_ground=("PLANE",)):
        """Return (Z, filament currents) for 1 A injected at port_p, returned at port_n."""
        L = self.Lmatrix()
        if np.linalg.eigvalsh(L).min() <= 0:
            raise ValueError("partial-inductance matrix not positive definite: filaments too coarse for the spacing")
        F = self.f
        n = len(F)
        lengths = np.array([fi["s1"] - fi["s0"] for fi in F])
        areas = np.array([fi["area"] for fi in F])
        R = RHO * lengths / areas
        w = 2 * math.pi * f
        Zb = (1e-6 if inductive else 1.0) * np.diag(R) + 1j * w * L
        port_p, port_n = self.find(port_p), self.find(port_n)
        if port_n in extra_ground:
            extra_ground = tuple(extra_ground) + (port_n,)
        nodes = {}
        for bb in self.bars:
            for nd in bb[:2]:
                nd = self.find(nd)
                if nd in extra_ground:
                    nd = port_n
                nodes.setdefault(nd, len(nodes))
        A = np.zeros((len(nodes), n))
        sign = np.ones(n)
        for bb in self.bars:
            a, b, ids = self.find(bb[0]), self.find(bb[1]), bb[2]
            s = bb[3] if len(bb) > 3 else 1
            a = port_n if a in extra_ground else a
            b = port_n if b in extra_ground else b
            for i in ids:
                # filament positive direction is +axis; bar current a->b is s*(+axis)
                A[nodes[a], i] += s
                A[nodes[b], i] -= s
                sign[i] = s
        keep = [k for nd, k in nodes.items() if nd != port_n]
        Ar = A[keep]
        Y = Ar @ np.linalg.solve(Zb, Ar.T)
        src = np.zeros(len(keep))
        kp = keep.index(nodes[port_p])
        src[kp] = 1.0
        v = np.linalg.solve(Y, src)
        I = np.linalg.solve(Zb, Ar.T @ v)
        Z = v[kp]
        phi = {nd: (v[keep.index(k)] if k in keep else 0.0) for nd, k in nodes.items()}
        self._last = dict(L=L, I=I, w=w, phi=phi)
        return Z, I

    def L_port(self, p, n, **kw):
        Z, _ = self.solve(p, n, **kw)
        return Z.imag / (2 * math.pi * kw.get("f", 1e8))

    def induced(self, path, I):
        """Open-circuit EMF (per unit j*omega, i.e. a mutual inductance in H) along a path of
        current-free probe segments [(p0, axis, length)], from filament currents I (A, +axis)."""
        ax, s0, s1, xyz, gmd = self._arrays()
        tot = 0.0
        for p0, axis, length in path:
            if length < 0:
                p0 = list(p0)
                p0[axis] += length
                length = -length
                sg = -1.0
            else:
                sg = 1.0
            q0, q1 = p0[axis], p0[axis] + length
            tr = [k for k in range(3) if k != axis]
            idx = np.nonzero(ax == axis)[0]
            P = xyz[idx][:, tr]
            q = np.array([p0[tr[0]], p0[tr[1]]])
            d = np.maximum(np.sqrt(((P - q) ** 2).sum(-1)), 1e-6)
            M = self._mpar(q0, q1, s0[idx], s1[idx], d)
            tot += sg * np.sum(M * I[idx])
            if self.plane_z is not None:
                zp = self.plane_z
                if axis == 2:
                    i0, i1 = 2 * zp - s1[idx], 2 * zp - s0[idx]
                    Pi = P
                    sgn = 1.0
                else:
                    i0, i1 = s0[idx], s1[idx]
                    Pi = P.copy()
                    Pi[:, 1] = 2 * zp - Pi[:, 1]
                    sgn = -1.0
                d = np.maximum(np.sqrt(((Pi - q) ** 2).sum(-1)), 1e-6)
                M = self._mpar(q0, q1, i0, i1, d)
                tot += sg * sgn * np.sum(M * I[idx])
        return tot


# ----------------------------------------------------------------------
# building blocks
# ----------------------------------------------------------------------
def strip_loop_over_plane(l, w, h, t=35e-6, nw=10):
    """U-shaped single conductor: post down to plane, strip of length l and width w at height h, post down.
    Return path = plane (image). Port between post foot (node P1 = plane) and start."""
    net = Net(plane_z=0.0)
    net.bar("A", "B", (0, -w / 2, h), 0, l, w, t, nw=nw)
    # vertical posts as wide flat bars (width w along y, thickness t along x) to the plane
    net.bar("PLANE", "A", (-t, -w / 2, 0.0), 2, h, t, w, nw=1, nt=nw)
    net.bar("PLANE2", "B", (l, -w / 2, 0.0), 2, h, t, w, nw=1, nt=nw)
    return net


def exp_validate():
    print("== validate")
    # 1. round wire (as a thin square bar) over a plane, long: L = mu0 l/(2 pi) ln(2h/r_eff)
    for h in (1 * mm, 5 * mm):
        l = 200 * mm
        a = 0.5 * mm
        net = Net(plane_z=0.0)
        net.bar("A", "B", (0, -a / 2, h - a / 2), 0, l, a, a, nw=4, nt=4)
        net.bar("PLANE", "A", (-a, -a / 2, 0), 2, h - a / 2, a, a, nw=2, nt=2)
        net.bar("PLANE", "B", (l, -a / 2, 0), 2, h - a / 2, a, a, nw=2, nt=2)
        # short both posts to plane: port in series at the first post foot -> use separate node
        net.bars[1] = ("P", "A", net.bars[1][2])
        L = net.L_port("P", "PLANE")
        r_eq = 0.4470 * a  # GMD of a square, = 0.2235*(a+a)
        th = MU0 * l / (2 * math.pi) * math.log(2 * h / r_eq)
        print(f"  square wire a=0.5 mm, h={h/mm:.0f} mm, l=200 mm: PEEC {L*1e9:6.2f} nH, ln-formula {th*1e9:6.2f} nH (no end posts)")
    # 2. wide strip over plane: L ~ mu0 h l / w (plus fringing)
    for h in (0.1 * mm, 0.2 * mm, 0.5 * mm):
        w, l = 10 * mm, 10 * mm
        net = strip_loop_over_plane(l, w, h, nw=_nw(w, h))
        net.bars[1] = ("P", "A", net.bars[1][2])
        net.bars[2] = ("PLANE", "B", net.bars[2][2])
        L = net.L_port("P", "PLANE")
        print(f"  strip w=10 mm l=10 mm h={h/mm:.1f} mm: PEEC {L*1e12:6.1f} pH, mu0 h l/w {MU0*h*l/w*1e12:6.1f} pH,"
              f" with w+2h {MU0*h*l/(w+2*h)*1e12:6.1f} pH")


# ----------------------------------------------------------------------
# commutation loops
# ----------------------------------------------------------------------
def _nw(w, h):
    """filaments across a strip: keep filament width below about h/3 near a plane"""
    return int(min(160, max(8, math.ceil(3 * w / h)))) if h else 8


def lateral_loop(l, w, s, h_plane, t=35e-6, nw=None, z0=0.0):
    """Go and return strips side by side on the top layer (z0), joined at both ends by cross bars.
    Port at the start of the go strip (models the cap terminals); far end is the switch pair."""
    net = Net(plane_z=(z0 - h_plane) if h_plane else None)
    nw = nw or _nw(w, h_plane)
    y_go = 0.0
    y_ret = w + s
    # go strip: from x=0 to x=l at y in [0, w]
    net.bar("G0", "G1", (0, y_go, z0), 0, l, w, t, nw=nw)
    # far-end cross bar (switch pair) along y from go strip to return strip
    net.bar("G1", "R1", (l, 0, z0), 1, w + s + w, w, t, nw=nw)
    # return strip x from 0..l, current flows -x: bar R0->R1 defined +x, current will be negative
    net.bar("R0", "R1", (0, y_ret, z0), 0, l, w, t, nw=nw)
    # near-end: capacitor body between R0 and port node, port between P and G0
    net.bar("P", "R0", (-w, 0, z0), 1, w + s + w, w, t, nw=nw)
    return net, ("G0", "P")


def vertical_loop(l, w, h1, h_plane=None, t=35e-6, nw=None, nvia=3, z0=0.0):
    """Go strip on top (z0), return strip directly underneath at z0-h1 (same width), via rows at the far
    end (switch side) and a cap-side via row. h_plane: optional solid plane a further h_plane below the return."""
    zr = z0 - h1
    net = Net(plane_z=(zr - h_plane) if h_plane else None)
    nw = nw or _nw(w, min(h1, h_plane or 1.0))
    net.bar("G0", "G1", (0, 0, z0), 0, l, w, t, nw=nw)
    net.bar("R0", "R1", (0, 0, zr - t), 0, l, w, t, nw=nw)
    for k in range(nvia):
        y = (k + 0.5) * w / nvia
        net.via("G1", "R1", l - 0.3 * mm, y, z0, zr, n=6)
    # cap side: port between top start G0 and a node P that connects down to R0 through vias
    for k in range(nvia):
        y = (k + 0.5) * w / nvia
        net.via("P", "R0", 0.3 * mm, y, z0, zr, n=6)
    return net, ("P", "G0")


def exp_loops():
    print("== loops: commutation-loop inductance, l = 4 mm (cap to switch pair), conductor w = 2 mm")
    l, w = 4 * mm, 2 * mm
    print("  lateral (go/return side by side on top, gap s = 0.5 mm; centreline enclosed area (l+w)*(w+s) = 15 mm2):")
    for hp in (None, 1.5 * mm, 0.5 * mm, 0.2 * mm, 0.1 * mm):
        net, (p, n) = lateral_loop(l, w, 0.5 * mm, hp)
        L = net.L_port(p, n)
        print(f"    plane at {('none' if hp is None else f'{hp/mm:.2f} mm'):>8s}: L = {L*1e9:6.3f} nH")
    print("  lateral with larger gap s = 3 mm (centreline area 30 mm2):")
    for hp in (None, 1.5 * mm, 0.1 * mm):
        net, (p, n) = lateral_loop(l, w, 3 * mm, hp)
        print(f"    plane at {('none' if hp is None else f'{hp/mm:.2f} mm'):>8s}: L = {net.L_port(p, n)*1e9:6.3f} nH")
    print("  vertical (return directly under the go strip, via rows at both ends, 3 vias each):")
    for h1 in (0.1 * mm, 0.2 * mm, 0.5 * mm, 1.5 * mm):
        net, (p, n) = vertical_loop(l, w, h1)
        L = net.L_port(p, n)
        net2, _ = vertical_loop(l, w, h1, nvia=1)
        L1 = net2.L_port(p, n)
        print(f"    h = {h1/mm:4.2f} mm: L = {L*1e9:6.3f} nH (1 via per end: {L1*1e9:6.3f} nH);"
              f" parallel-plate mu0 h l/w = {MU0*h1*l/w*1e9:6.3f} nH")
    print("  vertical through a 1.6 mm board (return on bottom) with an inner plane 0.2 mm under the return:")
    net, (p, n) = vertical_loop(l, w, 1.6 * mm, h_plane=0.2 * mm)
    print(f"    L = {net.L_port(p, n)*1e9:6.3f} nH")
    print("  wider loop (w = 6 mm, e.g. 3 caps across), l = 3 mm:")
    for h1 in (0.1 * mm, 0.2 * mm):
        net, (p, n) = vertical_loop(3 * mm, 6 * mm, h1, nvia=6)
        print(f"    internal vertical h = {h1/mm:.1f} mm: L = {net.L_port(p, n)*1e9:6.3f} nH")
    net, (p, n) = lateral_loop(3 * mm, 6 * mm, 0.5 * mm, 0.1 * mm)
    print(f"    lateral, plane 0.1 mm: L = {net.L_port(p, n)*1e9:6.3f} nH")


def exp_scaling():
    print("== scaling: internal-vertical loop, fixed footprint area A = l*w = 12 mm2, h = 0.1 mm")
    for l_, w_ in ((6, 2), (4, 3), (3, 4), (2, 6), (1.5, 8)):
        net, (p, n) = vertical_loop(l_ * mm, w_ * mm, 0.1 * mm, nvia=max(2, int(w_)))
        L = net.L_port(p, n)
        print(f"  l = {l_:3.1f} mm, w = {w_:3.1f} mm: L = {L*1e9:6.3f} nH  (mu0 h l/w = {MU0*0.1e-3*l_/w_*1e9:6.3f};"
              f" excess from vias/ends {L*1e9 - MU0*0.1e-3*l_/w_*1e9:6.3f})")
    print("  lateral loop over plane at 0.1 mm, l = 4 mm, w = 2 mm: L vs gap s")
    for s in (0.2, 0.5, 1.0, 2.0, 4.0):
        net, (p, n) = lateral_loop(4 * mm, 2 * mm, s * mm, 0.1 * mm)
        print(f"    s = {s:3.1f} mm: L = {net.L_port(p, n)*1e9:6.3f} nH")
    print("  lateral loop over plane at 0.1 mm, l = 4 mm, s = 0.5 mm: L vs conductor width w")
    for w_ in (0.5, 1.0, 2.0, 4.0):
        net, (p, n) = lateral_loop(4 * mm, w_ * mm, 0.5 * mm, 0.1 * mm)
        print(f"    w = {w_:3.1f} mm: L = {net.L_port(p, n)*1e9:6.3f} nH")


# ----------------------------------------------------------------------
# vias
# ----------------------------------------------------------------------
def exp_vias():
    print("== vias: N vias from a top strip (w = 3 mm) down to a plane at depth h; L of the via group")
    for h in (0.2 * mm, 0.5 * mm, 1.5 * mm):
        res = []
        for N, p in ((1, 0), (2, 0.5), (2, 1.0), (2, 2.0), (4, 0.5), (4, 1.0), (8, 0.5)):
            net = Net(plane_z=0.0)
            ys = [(-(N - 1) / 2 + k) * p * mm for k in range(N)]
            for y in ys:
                net.via("T", "PLANE", 0.0, y, h, 0.0, n=6)
            L = net.L_port("T", "PLANE")
            res.append((N, p, L))
        L1 = res[0][2]
        print(f"  h = {h/mm:.1f} mm: " + "; ".join(f"N={N} p={p:.1f}: {L*1e12:5.0f} pH ({L/L1:4.2f})" for N, p, L in res))
    print("  (ratios vs 1 via are the physical result; the ideal no-coupling ratio is 1/N. Absolute values are")
    print("   via-to-plane partial values, not loop inductances. Johnson's isolated-rod formula (h/5)(ln(4h/d)+1) nH, h, d in mm:")
    for h in (0.2, 0.5, 1.5):
        print(f"    Johnson h={h} mm, d=0.3 mm: {h/5*(math.log(4*h/0.3)+1)*1e3:5.0f} pH")


# ----------------------------------------------------------------------
# decoupling capacitor mounting
# ----------------------------------------------------------------------
def cap_mount(h, style, x0=0.0, y0=0.0, flip=False, net=None, tag="", port="PORT"):
    """0402 on the top layer over a plane at depth h (plane at z=0, top copper at z=h).
    style: 'trace' (0.8 mm traces to vias beyond pad ends), 'endvia' (via just beyond each pad),
    'vip' (via in pad), 'side' (two vias per pad on the long sides, close to the body), 'vip2' (2 per pad)."""
    if net is None:
        net = Net(plane_z=0.0)
    t = 35e-6
    z = h
    L0 = 1.0 * mm   # body length
    pw = 0.6 * mm   # pad width (y)
    # body at height: current path through the body modelled as a bar at z + 0.25 mm, 0.5 x 0.3 cross-section
    sgn = -1 if flip else 1
    xa, xb = x0 - sgn * L0 / 2, x0 + sgn * L0 / 2
    A, B = "A" + tag, "B" + tag
    # body bar from A to B (direction +x if not flipped)
    lo = min(xa, xb)
    # body: the MLCC's current path, a 1.0 x 0.5 mm bar 0.1 mm thick centred 0.25 mm above the pads
    ids = net.bar("bA" + tag, "bB" + tag, (lo, y0 - 0.25 * mm, z + 0.2 * mm), 0, L0, 0.5 * mm, 0.1 * mm, nw=8, nt=1)
    if flip:
        net.bars[-1] = ("bB" + tag, "bA" + tag, ids)
    # terminations: vertical end metallization pad -> body (0.25 mm tall, 30 um x 0.5 mm)
    net.bar(A, "bA" + tag, (xa - 15e-6, y0 - 0.25 * mm, z), 2, 0.25 * mm, 30e-6, 0.5 * mm, nw=1, nt=8)
    net.bar(B, "bB" + tag, (xb - 15e-6, y0 - 0.25 * mm, z), 2, 0.25 * mm, 30e-6, 0.5 * mm, nw=1, nt=8)
    # node A connects to the "supply" via, node B to the plane via; the supply via also goes to the plane
    # at the port (port opened at the top of the A-via). Via positions per style:
    if style == "trace":
        va = [(xa - sgn * 1.2 * mm, y0)]
        vb = [(xb + sgn * 1.2 * mm, y0)]
    elif style == "endvia":
        va = [(xa - sgn * 0.55 * mm, y0)]
        vb = [(xb + sgn * 0.55 * mm, y0)]
    elif style == "vip":
        va = [(xa, y0)]
        vb = [(xb, y0)]
    elif style == "vip2":
        va = [(xa, y0 - 0.2 * mm), (xa, y0 + 0.2 * mm)]
        vb = [(xb, y0 - 0.2 * mm), (xb, y0 + 0.2 * mm)]
    elif style == "side":
        va = [(xa, y0 - 0.65 * mm), (xa, y0 + 0.65 * mm)]
        vb = [(xb, y0 - 0.65 * mm), (xb, y0 + 0.65 * mm)]
    for k, (vx, vy) in enumerate(va):
        tn = f"ta{k}{tag}"
        _connect(net, A, tn, (xa, y0), (vx, vy), z, t)
        net.via(tn, port, vx, vy, z, 0.0, n=6)
    for k, (vx, vy) in enumerate(vb):
        tn = f"tb{k}{tag}"
        _connect(net, B, tn, (xb, y0), (vx, vy), z, t)
        net.via(tn, "PLANE", vx, vy, z, 0.0, n=6)
    return net


def _connect(net, a, b, p, q, z, t, w=0.5 * mm):
    """Manhattan connection on the top layer from point p (node a) to q (node b): x leg then y leg."""
    (x0, y0), (x1, y1) = p, q
    cur = a
    if abs(x1 - x0) > 1e-9:
        nxt = b if abs(y1 - y0) < 1e-9 else cur + "_" + b
        net.bar(cur, nxt, (min(x0, x1), y0 - w / 2, z), 0, abs(x1 - x0), w, t, nw=_nw(w, z))
        if x1 < x0:
            net.bars[-1] = (nxt, cur, net.bars[-1][2])
        cur = nxt
    if abs(y1 - y0) > 1e-9:
        net.bar(cur, b, (x1 - w / 2, min(y0, y1), z), 1, abs(y1 - y0), w, t, nw=_nw(w, z))
        if y1 < y0:
            net.bars[-1] = (b, cur, net.bars[-1][2])
    if abs(x1 - x0) <= 1e-9 and abs(y1 - y0) <= 1e-9:
        net.tie(a, b)  # via in pad: same node


def exp_caps():
    print("== caps: 0402 mounting loop inductance (body + pads + vias + plane image), top side")
    print("   Axotron measured (plane 0.3 mm): 0.63 nH (0.8 mm tracks to vias), 0.44 nH (via-in-pad)")
    for h in (0.1 * mm, 0.3 * mm, 1.0 * mm):
        row = []
        for st in ("trace", "endvia", "side", "vip", "vip2"):
            net = cap_mount(h, st)
            row.append((st, net.L_port("PORT", "PLANE")))
        print(f"  plane at {h/mm:.1f} mm: " + ", ".join(f"{s} {L*1e9:5.3f}" for s, L in row) + " nH")
    print("  two 0402s (end vias) side by side, centre pitch 1.0 mm, parallel: same vs alternating orientation")
    for h in (0.1 * mm, 0.3 * mm, 1.0 * mm):
        single = cap_mount(h, "endvia").L_port("PORT", "PLANE")
        out = []
        for flip in (False, True):
            net = cap_mount(h, "endvia", y0=-0.5 * mm, tag="1")
            net = cap_mount(h, "endvia", y0=0.5 * mm, flip=flip, net=net, tag="2")
            out.append(net.L_port("PORT", "PLANE"))
        print(f"  plane {h/mm:.1f} mm: single {single*1e9:5.3f} nH, pair same {out[0]*1e9:5.3f} nH"
              f" ({out[0]/single:4.2f}x), pair alternating {out[1]*1e9:5.3f} nH ({out[1]/single:4.2f}x)")


# ----------------------------------------------------------------------
# Kelvin sense pickup
# ----------------------------------------------------------------------
def exp_kelvin():
    print("== kelvin: inductive error in a shunt's sense voltage, V_err = L_err di/dt (plane 0.2 mm below top)")
    h = 0.2 * mm
    t = 35e-6
    zb = h + 0.3 * mm   # resistive element height (2512 body, 6.3 mm long, 3 mm wide)
    net = Net(plane_z=0.0)
    net.bar("IN", "s0", (-10 * mm, -1.5 * mm, h), 0, 6.85 * mm, 3 * mm, t, nw=_nw(3 * mm, h))   # feed x -10..-3.15
    net.bar("s0", "s1", (-3.15 * mm, -1.5 * mm, zb), 0, 6.3 * mm, 3 * mm, 0.1 * mm, nw=30, nt=1)  # body
    net.bar("s1", "OUT", (3.15 * mm, -1.5 * mm, h), 0, 7 * mm, 3 * mm, t, nw=_nw(3 * mm, h))
    net.bar("PLANE", "IN", (-10 * mm - t, -1.5 * mm, 0.0), 2, h, t, 3 * mm, nw=1, nt=_nw(3 * mm, h))
    net.bar("OUT", "P", (10.15 * mm, -1.5 * mm, 0.0), 2, h, t, 3 * mm, nw=1, nt=_nw(3 * mm, h))
    net.bars[-1] = ("P", "OUT", net.bars[-1][2])
    Z, I = net.solve("P", "PLANE")
    w = net._last["w"]
    phi = net._last["phi"]
    dphi = (phi[net.find("s1")] - phi[net.find("s0")]).imag / w   # inductive drop across the element (current flows s1 -> s0)
    xt = 3.15 * mm
    down1 = ((xt, 0, zb), 2, -(zb - h))      # from the element end down to the pad level
    up0 = ((-xt, 0, h), 2, zb - h)           # from the pad level up to the element end (reverse direction)
    routes = {
        "taps leave separately (+y), 6.3 mm apart, join at the amplifier 10 mm away": [
            down1, ((xt, 0, h), 1, 10 * mm), ((xt, 10 * mm, h), 0, -2 * xt), ((-xt, 10 * mm, h), 1, -10 * mm), up0],
        "taps converge 1.8 mm out (beside the body), then a tight pair to the amplifier": [
            down1, ((xt, 0, h), 1, 1.8 * mm), ((xt, 1.8 * mm, h), 0, -2 * xt + 0.2 * mm),
            ((-xt + 0.2 * mm, 1.8 * mm, h), 1, 8.2 * mm), ((-xt + 0.2 * mm, 10 * mm, h), 0, -0.2 * mm),
            ((-xt, 10 * mm, h), 1, -10 * mm), up0],
        "one sense trace runs back under the element (between element and plane)": [
            down1, ((xt, 0, h), 0, -2 * xt + 0.2 * mm), ((-xt + 0.2 * mm, 0, h), 1, 10 * mm),
            ((-xt + 0.2 * mm, 10 * mm, h), 0, -0.2 * mm), ((-xt, 10 * mm, h), 1, -10 * mm), up0],
    }
    print(f"  inductive drop across the element itself (with its image return): {dphi*1e12:6.0f} pH")
    for name, path in routes.items():
        Lerr = dphi - net.induced(path, I.real)
        print(f"  {name}: L_err = {Lerr*1e12:6.0f} pH -> {Lerr*1e9*1e3/1e3:5.2f} mV per A/us;"
              f" R = L_err/1 mOhm corner {1e-3/(2*math.pi*abs(Lerr))/1e3:6.0f} kHz")
    print("  (signal for comparison: 1 mOhm shunt at 20 A = 20 mV)")
    # nearby hot loop (lateral, 15 mm2) at 5 mm from a 30 mm2 sense loop vs a 1 mm2 loop
    hot, (p, n) = lateral_loop(4 * mm, 2 * mm, 0.5 * mm, h)
    Z, I = hot.solve(p, n)
    for area_name, ysep in (("30 mm2 sense loop (3 mm x 10 mm)", 3 * mm), ("1 mm2 sense loop (0.1 mm x 10 mm)", 0.1 * mm)):
        for dist in (3 * mm, 10 * mm):
            y0 = 4.5 * mm + dist
            path = [((-3 * mm, y0, h), 0, 10 * mm), ((7 * mm, y0, h), 1, ysep), ((7 * mm, y0 + ysep, h), 0, -10 * mm)]
            M = hot.induced(path, I.real)
            print(f"  hot loop (lateral, plane 0.2 mm) -> {area_name} at {dist/mm:.0f} mm: M = {abs(M)*1e15:8.1f} fH"
                  f" -> {abs(M)*5e9*1e3:7.3f} mV at 5 A/ns")


def exp_gate():
    print("== gate: gate-loop inductance (driver -> gate -> source -> driver), l = 10 mm, w = 0.5 mm")
    for label, builder in (("split, same layer, 1 mm gap, plane 0.2 mm", lambda: lateral_loop(10 * mm, 0.5 * mm, 1.0 * mm, 0.2 * mm)),
                           ("split, same layer, 0.2 mm gap, plane 0.2 mm", lambda: lateral_loop(10 * mm, 0.5 * mm, 0.2 * mm, 0.2 * mm)),
                           ("stacked on adjacent layers, 0.1 mm", lambda: vertical_loop(10 * mm, 0.5 * mm, 0.1 * mm, nvia=1))):
        net, (p, n) = builder()
        L = net.L_port(p, n)
        print(f"  {label:45s}: {L*1e9:5.2f} nH")
    # EPC criterion
    for name, rg, cgs in (("eGaN-like R_G 1.5 ohm, C_GS 0.6 nF", 1.5, 0.6e-9), ("Si MOSFET R_G 5 ohm, C_GS 3 nF", 5.0, 3e-9)):
        print(f"  EPC overshoot-free bound L_G <= (R_G)^2 C_GS / 4: {name}: {rg*rg*cgs/4*1e9:5.2f} nH")
    print("  common-source inductance: V_err = L_cs * di/dt; 0.2 nH x 5 A/ns = 1.0 V subtracted from the gate drive")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    exps = {"validate": exp_validate, "loops": exp_loops, "scaling": exp_scaling, "vias": exp_vias,
            "caps": exp_caps, "kelvin": exp_kelvin, "gate": exp_gate}
    for k, f in exps.items():
        if which in (k, "all"):
            f()
