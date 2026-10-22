# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Electric-field enhancement at copper corners and foil edges, and what it
does to the air-breakdown (discharge inception) voltage of a PCB gap.

Method: 2-D boundary-element (charge simulation) solve in a homogeneous
dielectric. Conductor outlines are split into straight panels with a uniform
surface charge each; the potential of a panel is integrated analytically;
collocation at panel midpoints plus a zero-net-charge condition and a free
potential offset. Surface field = sigma/eps. Panels are graded down to
l_min near the corner of interest.

Cases (gap g = 1 unit; the results scale with g):
  1  plan view: a rectangular pad/pour with a rounded corner of radius r,
     surrounded by a pour at constant clearance g (what KiCad's zone fill
     produces). E_max / (V/g) vs r/g.
  2  plan view: the end of a parallel run (corner of A facing a straight
     edge of B that continues past it). E_max / (V/g) vs r/g.
  3  cross section: coplanar copper foils of thickness t at gap g (homogeneous
     medium; for infinitely thin coplanar foils on an interface the field is
     the same as homogeneous). E_max / (V/g) vs t/g, square vs fully rounded
     edge.
  4  breakdown estimate for case 1 at real sizes in air: streamer/Townsend
     criterion with the quadratic effective-ionisation fit that reproduces
     the uniform-field formula V = 24.22*delta*d + 6.08*sqrt(delta*d) kV
     (d in cm; Kuffel, Zaengl and Kuffel), i.e. int (E - E0)^2 ds = K/C with
     E0 = 24.22*delta kV/cm and K/C = 6.08^2*delta kV^2/cm. Integrated along
     the corner-to-pour diagonal. Compared with the uniform-gap value.

Run (numpy, scipy, shapely; ~1-2 minutes):

    python tools/research/physics/tm_hv_field.py
"""
import math

import numpy as np
from scipy.optimize import brentq
from shapely.geometry import Polygon, box


def rounded_box(x0, y0, x1, y1, r, qs=64):
    if r <= 0:
        return box(x0, y0, x1, y1)
    return box(x0 + r, y0 + r, x1 - r, y1 - r).buffer(r, quad_segs=qs)


def rings_of(geom):
    out = [np.asarray(geom.exterior.coords)]
    out += [np.asarray(i.coords) for i in geom.interiors]
    return out


def panelize(ring, focus, lmin, lmax, grade=0.15):
    pts = []
    for a, b in zip(ring[:-1], ring[1:]):
        stack = [(a, b)]
        while stack:
            p, q = stack.pop()
            m = 0.5 * (p + q)
            L = np.linalg.norm(q - p)
            d = min(np.linalg.norm(m - f) for f in focus)
            target = max(lmin, min(lmax, grade * d))
            if L > target:
                stack.append((m, q))
                stack.append((p, m))
            else:
                pts.append((p, q))
    return pts


def solve(conductors, focus, lmin, lmax):
    """conductors: list of (shapely geometry, potential). Returns panels."""
    A_, B_, V_, owner = [], [], [], []
    for ci, (geom, v) in enumerate(conductors):
        for ring in rings_of(geom):
            for p, q in panelize(ring, focus, lmin, lmax):
                A_.append(p); B_.append(q); V_.append(v); owner.append(ci)
    A_, B_ = np.array(A_), np.array(B_)
    mid = 0.5 * (A_ + B_)
    L = np.linalg.norm(B_ - A_, axis=1)
    M = influence(mid, A_, B_, L)
    n = len(L)
    S = np.zeros((n + 1, n + 1))
    S[:n, :n] = M
    S[:n, n] = 1.0
    S[n, :n] = L
    rhs = np.concatenate([np.array(V_, float), [0.0]])
    sol = np.linalg.solve(S, rhs)
    return dict(A=A_, B=B_, L=L, mid=mid, sigma=sol[:n], C=sol[n], owner=np.array(owner))


def influence(x, A_, B_, L):
    """Potential at points x from unit-sigma panels: -(1/2pi) int ln|x-s| ds (eps=1)."""
    t = (B_ - A_) / L[:, None]
    nrm = np.stack([-t[:, 1], t[:, 0]], axis=1)
    dx = x[:, None, :] - A_[None, :, :]
    u0 = np.einsum("ijk,jk->ij", dx, t)
    v0 = np.einsum("ijk,jk->ij", dx, nrm)

    def F(w):
        r2 = w * w + v0 * v0
        lnr = 0.5 * np.log(np.where(r2 > 0, r2, 1.0))
        at = np.where(np.abs(v0) > 1e-300, v0 * np.arctan(w / np.where(v0 == 0, 1, v0)), 0.0)
        return np.where(r2 > 0, w * lnr, 0.0) - w + at
    I = F(L[None, :] - u0) - F(-u0)
    return -I / (2 * math.pi)


def potential(sol, x):
    return influence(np.atleast_2d(x), sol["A"], sol["B"], sol["L"]) @ sol["sigma"] + sol["C"]


def case1(rr, g=1.0, size=10.0, ring_w=5.0):
    """Pad A (V=1) with corner radius r inside a pour B (V=0) at clearance g."""
    A = rounded_box(-size, -size, 0.0, 0.0, rr)
    inner = A.buffer(g, quad_segs=64)
    outer = A.buffer(g + ring_w, quad_segs=64)
    Bg = outer.difference(inner)
    corner = np.array([-rr, -rr]) if rr > 0 else np.array([0.0, 0.0])
    lmin = max(1e-3, rr / 40) if rr > 0 else 1e-3
    sol = solve([(A, 1.0), (Bg, 0.0)], [corner, np.array([0.0, 0.0])], lmin, 0.4)
    near = np.linalg.norm(sol["mid"] - corner, axis=1) < max(3 * rr, 0.3)
    onA = (sol["owner"] == 0) & near        # only the refined corner (others are coarse)
    emax = np.abs(sol["sigma"][onA]).max()
    # mid-edge reference: panel nearest (0, -size/2)
    k = np.argmin(np.linalg.norm(sol["mid"] - np.array([0.0, -size / 2]), axis=1))
    return sol, emax, abs(sol["sigma"][k]), corner


def case2(rr, g=1.0):
    """End of a parallel run: A's right edge faces B's long straight edge."""
    A = rounded_box(-10.0, -10.0, 0.0, 0.0, rr)
    Bg = box(g, -20.0, g + 5.0, 10.0)
    corner = np.array([-rr, -rr]) if rr > 0 else np.array([0.0, 0.0])
    lmin = max(1e-3, rr / 40) if rr > 0 else 1e-3
    sol = solve([(A, 1.0), (Bg, 0.0)], [corner, np.array([0.0, 0.0]), np.array([g, 0.0])], lmin, 0.4)
    near = np.linalg.norm(sol["mid"] - corner, axis=1) < max(3 * rr, 0.3)
    onA = (sol["owner"] == 0) & near
    emax = np.abs(sol["sigma"][onA]).max()
    k = np.argmin(np.linalg.norm(sol["mid"] - np.array([0.0, -5.0]), axis=1))
    return emax, abs(sol["sigma"][k])


def case3(t, re, g=1.0, w=8.0):
    """Cross-section: foils [-w,0]x[0,t] (V=1) and [g,g+w]x[0,t] (V=0)."""
    A = rounded_box(-w, 0.0, 0.0, t, re)
    Bg = rounded_box(g, 0.0, g + w, t, re)
    lmin = max(t / 400, re / 40 if re > 0 else 0)
    sol = solve([(A, 1.0), (Bg, 0.0)], [np.array([0.0, 0.0]), np.array([0.0, t]),
                                        np.array([g, 0.0]), np.array([g, t])], lmin, 0.3)
    onA = (sol["owner"] == 0) & (sol["mid"][:, 0] > -0.3)
    return np.abs(sol["sigma"][onA]).max(), sol


def breakdown_kv(sol, start, direction, gap_len, scale_mm, delta=1.0):
    """Scale model so 1 unit = scale_mm mm; integrate (E-E0)^2 along the path."""
    s = np.linspace(1e-4, gap_len - 1e-4, 1500)
    pts = start[None, :] + s[:, None] * direction[None, :]
    phi = potential(sol, pts)
    e_unit = np.abs(np.gradient(phi, s))            # V per unit length for 1 V
    d_cm = scale_mm / 10.0
    e_kv_cm = e_unit / d_cm                          # kV/cm per kV applied
    ds_cm = np.gradient(s) * d_cm
    E0 = 24.22 * delta
    KC = 6.08 ** 2 * delta

    def f(vkv):
        ex = np.clip(vkv * e_kv_cm - E0, 0, None)
        return np.sum(ex * ex * ds_cm) - KC
    return brentq(f, 0.01, 500.0)


def uniform_kv(d_mm, delta=1.0):
    d = d_mm / 10 * delta
    return 24.22 * d + 6.08 * math.sqrt(d)


if __name__ == "__main__":
    print("Case 1: pad corner inside a pour at constant clearance g (plan view)")
    sols = {}
    for rr in (0.0, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0):
        sol, emax, emid, corner = case1(rr)
        sols[rr] = (sol, corner)
        tag = " (sharp: grid-limited, l_min = g/1000)" if rr == 0 else ""
        print(f"    r/g={rr:4.2f}  E_max/(V/g) = {emax:5.2f}   mid-edge {emid:4.2f}{tag}")
    print("Case 2: end of a parallel run (A's corner where B's edge continues)")
    for rr in (0.0, 0.05, 0.2, 0.5, 1.0):
        emax, emid = case2(rr)
        print(f"    r/g={rr:4.2f}  E_max/(V/g) = {emax:5.2f}   mid-edge {emid:4.2f}")
    print("Case 3: cross-section, coplanar foils of thickness t at gap g")
    for g_mm in (0.25, 0.5, 1.0, 2.5, 6.0):
        for t_um in (35, 70):
            t = t_um / 1000 / g_mm
            sq = case3(t, 0.0)[0]
            rd = case3(t, t / 2 * 0.999)[0]
            print(f"    g={g_mm:4.2f} mm t={t_um} um (t/g={t:.3f})  E_max/(V/g): square edge {sq:5.2f}"
                  f" (grid-limited)  fully rounded edge {rd:5.2f}")
    print("Case 4: inception/breakdown estimate in air for case 1 (diagonal path), delta=1")
    diag = np.array([1.0, 1.0]) / math.sqrt(2)
    for g_mm in (0.5, 1.0, 3.0):
        ref = uniform_kv(g_mm)
        row = []
        for rr in (0.0, 0.05, 0.2, 0.5, 1.0, 2.0):
            sol, corner = sols[rr]
            start = corner + diag * rr if rr > 0 else corner.copy()
            v = breakdown_kv(sol, start, diag, 1.0, g_mm)
            row.append(f"r/g={rr}:{v:4.2f}")
        print(f"    g={g_mm} mm uniform-gap {ref:4.2f} kV | " + "  ".join(row) + " kV")
    print("Case 4b: same estimate for coplanar 35 um foils (cross-section), path along y = t/2")
    for g_mm in (0.5, 1.0, 3.0):
        t = 0.035 / g_mm
        out = []
        for name, re in (("square", 0.0), ("rounded", t / 2 * 0.999)):
            sol = case3(t, re)[1]
            v = breakdown_kv(sol, np.array([0.0, t / 2]), np.array([1.0, 0.0]), 1.0, g_mm)
            out.append(f"{name} {v:4.2f}")
        print(f"    g={g_mm} mm uniform-gap {uniform_kv(g_mm):4.2f} kV | 35 um foils: " + "  ".join(out) + " kV")
    print("    delta (relative air density) scales E0 and K/C: at 20 km (delta~0.072) use delta=0.072")
    sol, corner = sols[0.5]
    for delta in (1.0, 0.5, 0.072):
        v = breakdown_kv(sol, corner + diag * 0.5, diag, 1.0, 1.0, delta)
        print(f"    g=1 mm, r/g=0.5, delta={delta}: {v*1000:6.0f} V (uniform {uniform_kv(1.0, delta)*1000:5.0f} V;"
              " formula invalid near/below the Paschen minimum)")
