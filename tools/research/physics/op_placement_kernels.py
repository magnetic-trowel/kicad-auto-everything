# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Placement-grade physics kernels that an optimizer can evaluate in a batch and differentiate.

1. Loop inductance of Manhattan (axis-aligned) 3-D loops by filament PEEC: each strip is
   split into n_w parallel sub-filaments carrying equal current; parallel pairs use the
   exact closed-form mutual inductance of parallel filaments (Grover), perpendicular pairs
   contribute nothing, self terms use the cross-section GMD. An ideal reference plane at
   depth h is an image loop (z -> -z - 2h, horizontal current reversed).
   Checked against Grover's rectangle formula and against the air microstrip L'.
2. With a plane close below, a lateral hot loop's inductance tracks path length x plane
   depth, not the enclosed area (the usual "minimize loop area" proxy).
3. Gradient of L w.r.t. a part position (central differences; autodiff gives the same in
   one backward pass) and batched timing.
4. Thermal Green's function of a convectively cooled board (thin fin):
   T(r) = P / (2 pi k t) * K0(r / lambda), lambda = sqrt(k t / h_sum), for several stackups.
5. Reflection of an unmitred 90-degree microstrip corner, |Gamma| ~ w Z0 C / 2.
6. 1-D power-tree law: at fixed copper area A, the loss of a tree of strips is minimized by
   width proportional to current (constant J), giving P_min = R_s (sum I_e l_e)^2 / A; the
   optimal split of area between nets is A_i proportional to sqrt(w_i) * sum(I l)_i.
   Applied to the trunk-and-branch baseline of op_topopt_pour.py.

Run: python tools/research/physics/op_placement_kernels.py   (a few seconds; numpy + scipy)
Deterministic; prints the tables used in docs/topics/physics/physics-in-the-loop-optimization.md.
"""
import time

import numpy as np
from scipy.special import k0

MU0 = 4e-7 * np.pi


def _G(u, d):
    return u * np.arcsinh(u / d) - np.sqrt(u * u + d * d)


def filaments(poly, w, t=35e-6, nw=6, via_r=0.15e-3):
    """Closed axis-aligned polyline(s) (..., S, 3) -> sub-filaments (start, end, axis, gmd)."""
    p0, p1 = poly, np.roll(poly, -1, axis=-2)
    d = p1 - p0
    axis = np.argmax(np.abs(d), axis=-1)                      # (..., S)
    if not np.all(np.isclose(np.abs(d).sum(-1), np.abs(d).max(-1))):
        raise ValueError("segments must be axis-aligned")
    offs = (np.arange(nw) + 0.5) / nw * w - w / 2
    horiz = axis < 2
    # transverse in-plane direction for horizontal segments: x-seg -> y offset, y-seg -> x offset
    tdir = np.zeros(d.shape)
    tdir[..., 0] = (axis == 1)
    tdir[..., 1] = (axis == 0)
    a0 = p0[..., :, None, :] + offs[None, :, None] * tdir[..., :, None, :] * horiz[..., :, None, None]
    a1 = p1[..., :, None, :] + offs[None, :, None] * tdir[..., :, None, :] * horiz[..., :, None, None]
    gmd = np.where(horiz, 0.2235 * (w / nw + t), via_r)[..., :, None] * np.ones(nw)
    ax = np.repeat(axis[..., :, None], nw, axis=-1)
    shp = poly.shape[:-2] + (-1,)
    return (a0.reshape(shp + (3,)), a1.reshape(shp + (3,)), ax.reshape(shp), gmd.reshape(shp),
            nw)


def mutual(fa, fb, same):
    """Sum of mutual inductances between two filament sets (equal current per sub-filament)."""
    a0, a1, ax, g, nw = fa
    b0, b1, bx, gb, _ = fb
    par = ax[..., :, None] == bx[..., None, :]
    k = ax[..., :, None]
    i3 = np.arange(3)
    onehot = (k[..., None] == i3)                              # longitudinal axis mask
    da = a1 - a0
    db = b1 - b0
    sa = np.take_along_axis(da, ax[..., None], -1)[..., 0]
    sb = np.take_along_axis(db, bx[..., None], -1)[..., 0]
    sign = np.sign(sa)[..., :, None] * np.sign(sb)[..., None, :]
    # longitudinal coordinates along the shared axis
    xa0 = (a0[..., :, None, :] * onehot).sum(-1)
    xa1 = (a1[..., :, None, :] * onehot).sum(-1)
    xb0 = (b0[..., None, :, :] * onehot).sum(-1)
    xb1 = (b1[..., None, :, :] * onehot).sum(-1)
    lo_a, hi_a = np.minimum(xa0, xa1), np.maximum(xa0, xa1)
    lo_b, hi_b = np.minimum(xb0, xb1), np.maximum(xb0, xb1)
    tr = ((a0[..., :, None, :] - b0[..., None, :, :]) * ~onehot)
    dist = np.sqrt((tr ** 2).sum(-1))
    if same:
        n = dist.shape[-1]
        eye = np.eye(n, dtype=bool)
        dist = np.where(eye, g[..., :, None], dist)
    dist = np.maximum(dist, 1e-7)
    val = (_G(hi_a - lo_b, dist) - _G(lo_a - lo_b, dist) - _G(hi_a - hi_b, dist) + _G(lo_a - hi_b, dist))
    return MU0 / (4 * np.pi) * (np.where(par, sign * val, 0.0)).sum((-1, -2)) / nw**2


def loop_inductance(poly, w, t=35e-6, h_plane=None, nw=6):
    f = filaments(poly, w, t, nw)
    lval = mutual(f, f, True)
    if h_plane is not None:
        a0, a1, ax, g, n = f
        i0, i1 = a0.copy(), a1.copy()
        i0[..., 2] = -i0[..., 2] - 2 * h_plane
        i1[..., 2] = -i1[..., 2] - 2 * h_plane
        # PEC image: horizontal current reversed, vertical kept. Mirroring z already flips the
        # vertical component, so in both cases the image runs from mirrored end to mirrored start.
        j0, j1 = i1, i0
        lval = lval + mutual(f, (j0, j1, ax, g, n), False)
    return lval


def rect(a, b, z=0.0):
    return np.array([[0, 0, z], [a, 0, z], [a, b, z], [0, b, z]], float)


def grover_rect(a, b, r):
    """Grover/Rosa high-frequency inductance of an a x b rectangle of round wire radius r."""
    d = np.hypot(a, b)
    return MU0 / np.pi * (a * np.log(2 * a / r) + b * np.log(2 * b / r) + 2 * d
                          - a * np.arcsinh(a / b) - b * np.arcsinh(b / a) - 2 * (a + b))


def main():
    mm = 1e-3
    print("1) Checks")
    w_eq = 0.25 * mm / 0.2235
    l_f = loop_inductance(rect(10 * mm, 4 * mm), w_eq, t=0.0, nw=1)
    print(f"   10 x 4 mm loop, round wire r = 0.25 mm: model {l_f * 1e9:.2f} nH, "
          f"Grover {grover_rect(10 * mm, 4 * mm, 0.25 * mm) * 1e9:.2f} nH")
    # long strip over plane: per-length inductance from two lengths (end effects cancel)
    def strip_loop(length, w, h):
        return loop_inductance(rect(length, 40 * mm), w, h_plane=h, nw=12)
    for w, h in [(1.5 * mm, 0.1 * mm), (0.3 * mm, 0.17 * mm)]:
        lp = (strip_loop(80 * mm, w, h) - strip_loop(40 * mm, w, h)) / (2 * 40 * mm)
        u = w / h
        z0 = 376.73 / (u + 1.393 + 0.667 * np.log(u + 1.444)) if u >= 1 else 60 * np.log(8 / u + u / 4)
        print(f"   strip w={w / mm:.2f} mm over plane h={h / mm:.2f} mm: model {lp * 1e9 * 1e-3:.3f} nH/mm, "
              f"air-microstrip Z0/c {z0 / 299792458 * 1e9 * 1e-3:.3f} nH/mm, parallel-plate mu0 h/w "
              f"{MU0 * h / w * 1e9 * 1e-3:.3f} nH/mm")

    print("\n2) Lateral hot loop (strip w = 1.5 mm, 1 oz) vs depth of a solid plane below:")
    shapes = {"8 x 3 mm (24 mm2, perim 22)": rect(8 * mm, 3 * mm),
              "12 x 2 mm (24 mm2, perim 28)": rect(12 * mm, 2 * mm),
              "4.9 x 4.9 mm (24 mm2, perim 19.6)": rect(4.9 * mm, 4.9 * mm),
              "6 x 2 mm (12 mm2, perim 16)": rect(6 * mm, 2 * mm),
              "16 x 1.5 mm (24 mm2, perim 35)": rect(16 * mm, 1.5 * mm)}
    hs = [None, 1.5 * mm, 0.4 * mm, 0.2 * mm, 0.1 * mm]
    print("   " + " " * 34 + "".join(f"{('none' if h is None else f'h={h / mm:.1f}'):>9s}" for h in hs))
    for name, p in shapes.items():
        vals = [loop_inductance(p, 1.5 * mm, h_plane=h) * 1e9 for h in hs]
        print(f"   {name:34s}" + "".join(f"{v:9.2f}" for v in vals) + "  nH")

    print("\n3) Gradient of L w.r.t. moving the input-cap side of an 8 x 3 mm loop, plane at 0.2 mm:")
    base = rect(8 * mm, 3 * mm)
    eps = 1e-6

    def l_of(dx, h=0.2 * mm):
        p = base.copy()
        p[[1, 2], 0] += dx
        return loop_inductance(p, 1.5 * mm, h_plane=h)

    for h in (None, 0.2 * mm):
        g = (l_of(eps, h) - l_of(-eps, h)) / (2 * eps)
        print(f"   plane {'none' if h is None else f'{h / mm:.1f} mm':>6s}: L = {l_of(0, h) * 1e9:.2f} nH, "
              f"dL/dx = {g * 1e9 * 1e-3:.3f} nH per mm")
    batch = np.repeat(base[None], 1000, axis=0)
    batch[:, [1, 2], 0] += np.linspace(-2, 2, 1000)[:, None] * mm
    t0 = time.perf_counter()
    lb = loop_inductance(batch, 1.5 * mm, h_plane=0.2 * mm, nw=4)
    dt = time.perf_counter() - t0
    print(f"   batch of 1000 loops (4 segments x 4 sub-filaments, + image): {dt * 1e3:.0f} ms "
          f"({dt / 1000 * 1e6:.0f} us each, numpy, 1 core); L {lb.min() * 1e9:.2f}-{lb.max() * 1e9:.2f} nH")

    print("\n4) Thermal Green's function of a board in still air (h = 10 W/m2K per side):")
    k_fr4, k_cu, hc = 0.3, 390.0, 10.0
    stacks = {"2L 1.6 mm, no pours": 0.3 * 1.6e-3,
              "2L 1.6 mm, two 1 oz pours": k_fr4 * 1.6e-3 + 2 * k_cu * 35e-6,
              "4L 1.6 mm, 1 oz outer + 2 x 0.5 oz planes": k_fr4 * 1.6e-3 + k_cu * (2 * 35e-6 + 2 * 17.5e-6),
              "4L 1.6 mm, 2 oz outer + 2 x 1 oz planes": k_fr4 * 1.6e-3 + k_cu * (2 * 70e-6 + 2 * 35e-6)}
    for name, kt in stacks.items():
        lam = np.sqrt(kt / (2 * hc))
        th = [k0(d / lam) / (2 * np.pi * kt) for d in (5e-3, 10e-3, 20e-3, 40e-3)]
        print(f"   {name:42s} kt={kt * 1e3:6.2f} mW/K  lambda={lam * 1e3:5.1f} mm  "
              f"theta_mutual(5/10/20/40 mm) = " + "/".join(f"{x:.1f}" for x in th) + " K/W")

    print("\n5) Unmitred 90-degree corner, 50 ohm microstrip, excess C assumed 10-20 fF:")
    for f in (1e9, 10e9, 30e9):
        g1, g2 = [2 * np.pi * f * 50 * c / 2 for c in (10e-15, 20e-15)]
        print(f"   {f / 1e9:4.0f} GHz: |Gamma| = {g1:.3f}-{g2:.3f} ({20 * np.log10(g1):.0f} to {20 * np.log10(g2):.0f} dB)")

    print("\n6) 1-D power-tree law on the op_topopt_pour.py baseline (1 oz, R_s = 0.491 mOhm/sq):")
    rs = 1.72e-8 / 35e-6
    segs = [("trunk", 6.0, 3.5, 4.0), ("to A", 3.0, 15.36, 2.0), ("to C", 3.0, 5.66, 2.0), ("C to B", 2.0, 7.0, 1.5)]
    m = sum(i * l for _, i, l, _ in segs)
    area = sum(l * w for _, _, l, w in segs)
    p_act = rs * sum(i * i * l / w for _, i, l, w in segs)
    p_min = rs * m * m / area
    print(f"   sum I*l = {m:.1f} A*mm, strip area {area:.1f} mm2; widths {[round(w / i, 2) for _, i, _, w in segs]} mm/A")
    print(f"   1-D loss with drawn widths {p_act * 1e3:.1f} mW (R_loss {p_act / 36 * 1e3:.2f} mOhm); "
          f"optimum at same area and topology {p_min * 1e3:.1f} mW ({p_min / 36 * 1e3:.2f} mOhm)")
    m1, m2, atot = 100.0, 50.0, 100.0
    eq = rs * (m1**2 / 50 + m2**2 / 50)
    opt = rs * (m1 + m2) ** 2 / atot
    print(f"   two nets, sum(I l) = 100 and 50 A*mm sharing 100 mm2: equal split {eq * 1e3:.1f} mW, "
          f"split proportional to sum(I l) {opt * 1e3:.1f} mW ({(eq / opt - 1) * 100:.0f}% less loss)")


if __name__ == "__main__":
    main()
