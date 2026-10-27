# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Copper under an inductor: what does a cut-out in a continuous plane actually remove?

Used by docs/topics/physics/derivation-audit.md (rule P13).  Hypothesis tested: a hole of radius a in an
otherwise continuous plane is a closed ring; by Faraday's law on that ring (lens CT, hole circulation) the
ring current opposes the AC flux through the hole once the plane's mirror length l_m = R_s/(pi mu0 f)
(lens LS) is below the hole size, i.e. above f_hole = R_s/(pi mu0 a).  So the eddy current does not
vanish; it moves to the rim.  Whether loss, inductance drop and shielding then fall or rise depends on
how strong the field is at the rim, i.e. on a relative to the winding radius.

Model (axisymmetric, quasi-static, thin sheet): a circular source loop (radius r_s, height z_s, 1 A peak)
stands for an unshielded drum-core inductor's leakage field; the plane is a resistive annulus a <= r <= b at
z = 0 discretized into graded concentric strips.  Exact coaxial mutual inductances (elliptic integrals,
4-point Gauss averaging over strip widths), GMD self terms, R_strip = R_s 2 pi r / w with
R_s = rho / min(t, delta).  Solve (R + j w M) I = -j w M_s I_s.  Mesh-converged to 0.1% (printed check).

Reports, relative to a solid plane: eddy loss, the source's inductance change, net flux through the hole,
and the field below the plane (shielding of a victim layer).  Absolute numbers belong to an air loop, not
a ferrite part (round 1 scales them by the part's external-field share); the ratios are the result.
Limits: axisymmetric (no slits, no off-axis parts), thin sheet (valid while l_m and delta exceed the cell
and copper thickness, here up to ~2 MHz), no ferrite.  Runs in about a second.

Run:  OMP_NUM_THREADS=1 python da_inductor_cutout.py
"""
import math

import numpy as np
from scipy.special import ellipe, ellipk

MU0 = 4e-7 * math.pi
RHO = 1.72e-8
mm = 1e-3
GL_X, GL_W = np.polynomial.legendre.leggauss(4)


def m_filaments(r1, z1, r2, z2):
    """Mutual inductance of coaxial circular filaments (Maxwell), vectorized."""
    r1, z1, r2, z2 = np.broadcast_arrays(r1, z1, r2, z2)
    k2 = 4 * r1 * r2 / ((r1 + r2) ** 2 + (z1 - z2) ** 2)
    k2 = np.clip(k2, 0.0, 1 - 1e-15)
    k = np.sqrt(k2)
    return MU0 * np.sqrt(r1 * r2) * ((2 / k - k) * ellipk(k2) - 2 / k * ellipe(k2))


def bz_loop(R, z0, rho, z):
    """Axial field of a unit-current loop (radius R, height z0) at (rho, z)."""
    R, z0, rho, z = np.broadcast_arrays(R, z0, rho, z)
    dz = z - z0
    den = (R + rho) ** 2 + dz ** 2
    m = 4 * R * rho / den
    return MU0 / (2 * math.pi) / np.sqrt(den) * (ellipk(m) + (R * R - rho * rho - dz * dz) /
                                                 ((R - rho) ** 2 + dz * dz) * ellipe(m))


def strips(a, b, h0, grow, r_fine=()):
    """Graded strip edges from a to b: fine (h0) at a and near each radius in r_fine, growing geometrically."""
    pts = sorted([a] + [r for r in r_fine if a < r < b])
    edges = [a]
    x = a
    while x < b:
        dist = min(abs(x - p) for p in pts)
        step = min(h0 * (1 + (grow - 1) * dist / h0) if dist > 0 else h0, 0.6 * mm)
        x = min(x + step, b)
        edges.append(x)
    return np.array(edges)


def solve(a, b, r_s, z_s, f, t=35e-6, h0=0.02 * mm):
    e = strips(a, b, h0, 1.08, r_fine=(r_s,))
    rc = 0.5 * (e[1:] + e[:-1])
    w = e[1:] - e[:-1]
    n = len(rc)
    # Gauss points across each strip
    rp = rc[:, None] + 0.5 * w[:, None] * GL_X[None, :]
    wp = 0.5 * GL_W[None, :]
    M = np.zeros((n, n))
    for p in range(4):
        for q in range(4):
            M += wp[0, p] * wp[0, q] * m_filaments(rp[:, p][:, None], 0.0, rp[:, q][None, :], 0.0)
    gmd = 0.2235 * w
    np.fill_diagonal(M, MU0 * rc * (np.log(8 * rc / gmd) - 2))
    ms = sum(wp[0, p] * m_filaments(r_s, z_s, rp[:, p], 0.0) for p in range(4))
    delta = math.sqrt(RHO / (math.pi * f * MU0))
    rs = RHO / min(t, delta)
    R = rs * 2 * math.pi * rc / w
    om = 2 * math.pi * f
    A = np.diag(R) + 1j * om * M
    I = np.linalg.solve(A, -1j * om * ms)
    dz = 1j * om * np.dot(ms, I)                       # change of the source's impedance (1 A source)
    p_eddy = 0.5 * np.sum(R * np.abs(I) ** 2)
    return dict(rc=rc, w=w, I=I, rs=rs, dL=dz.imag / om, dR=dz.real, p=p_eddy, n=n)


def flux_through(r0, r_s, z_s, sol):
    """Net flux through a circle of radius r0 in the plane z = 0 (source + strip currents)."""
    phi = m_filaments(r_s, z_s, r0, 0.0) * 1.0
    if sol is not None:
        phi = phi + np.dot(m_filaments(sol["rc"], 0.0, r0, 0.0), sol["I"])
    return complex(phi)


def bz_below(rho, zb, r_s, z_s, sol):
    b = bz_loop(r_s, z_s, rho, zb) * 1.0
    if sol is not None:
        b = b + np.dot(bz_loop(sol["rc"], 0.0, rho, zb), sol["I"])
    return complex(b)


def brms_below(rmax, zb, r_s, z_s, sol, n=80):
    """Area-weighted RMS of |Bz| over the disc r <= rmax at depth zb (a victim layer below the plane)."""
    rr = (np.arange(n) + 0.5) * rmax / n
    b = np.array([abs(bz_below(r, zb, r_s, z_s, sol)) for r in rr])
    return math.sqrt(np.sum(b * b * rr) / np.sum(rr))


def convergence():
    print("== mesh check (z_s = 0.6 mm, a = 2.0 mm): loss/solid and dL/solid vs rim cell size")
    for f in (500e3, 2e6):
        out = []
        for h0 in (0.02 * mm, 0.005 * mm, 0.002 * mm):
            ref = solve(0.05 * mm, 25 * mm, 2 * mm, 0.6 * mm, f, h0=h0)
            sol = solve(2.0 * mm, 25 * mm, 2 * mm, 0.6 * mm, f, h0=h0)
            out.append(f"h0 {h0/mm*1e3:3.0f} um: {sol['p']/ref['p']:.3f}, {sol['dL']/ref['dL']:.3f} (n={sol['n']})")
        print(f"   {f/1e3:5.0f} kHz: " + "; ".join(out))


def main():
    b = 25 * mm
    r_s = 2.0 * mm
    rs1 = RHO / 35e-6
    print("== Copper under an unshielded inductor: solid plane vs cut-out (1 oz plane, 25 mm radius)")
    print("   f_hole = R_s/(pi mu0 a): " + ", ".join(f"a = {a:.1f} mm -> {rs1/(math.pi*MU0*a*mm)/1e3:.0f} kHz"
                                               for a in (2.0, 3.5, 6.0)))
    l0 = MU0 * r_s * (math.log(8 * r_s / (0.3 * mm)) - 1.75)
    print(f"   source: loop r_s = {r_s/mm:.1f} mm (own L {l0*1e9:.1f} nH, air core), 1 A peak")
    for z_s in (0.6 * mm, 1.5 * mm):
        print(f"\n   source height above the plane z_s = {z_s/mm:.1f} mm")
        print("   f        hole a   loss/solid  dL/solid  dL (nH)   net flux through r=a (or 2 mm) / no plane   "
              "below the plane (z = -0.5 mm) / no plane: Bz at r=0, Bz rms over r<=8 mm")
        for f in (10e3, 50e3, 200e3, 500e3, 2e6):
            ref = solve(0.05 * mm, b, r_s, z_s, f, h0=0.005 * mm)
            for a in (0.05 * mm, 2.0 * mm, 3.5 * mm, 6.0 * mm):
                sol = ref if a == 0.05 * mm else solve(a, b, r_s, z_s, f, h0=0.005 * mm)
                a_ref = 2.0 * mm if a == 0.05 * mm else a
                phi0 = flux_through(a_ref * 0.999, r_s, z_s, None)
                phi = flux_through(a_ref * 0.999, r_s, z_s, sol)
                b0 = abs(bz_below(1e-6, -0.5 * mm, r_s, z_s, sol)) / abs(bz_below(1e-6, -0.5 * mm, r_s, z_s, None))
                brms = brms_below(8 * mm, -0.5 * mm, r_s, z_s, sol) / brms_below(8 * mm, -0.5 * mm, r_s, z_s, None)
                tag = "solid " if a == 0.05 * mm else f"{a/mm:.1f} mm"
                print(f"   {f/1e3:6.0f} kHz {tag}   {sol['p']/ref['p']:7.2f}   {sol['dL']/ref['dL']:7.2f}  "
                      f"{sol['dL']*1e9:7.3f}        {abs(phi)/abs(phi0):6.3f}                              "
                      f"{b0:.3f}   {brms:.3f}")
    print("\n   reading: above f_hole the ring still carries the eddy current, crowded at the rim.  A cut-out the size")
    print("   of the winding (a = r_s) keeps or raises the loss (1.05-1.4x at 0.5-2 MHz) and cuts the inductance drop")
    print("   only 12-23%, yet loses most shielding under the part: the worst of both.  Only a cut-out >= 2-3x the")
    print("   winding radius removes most loss and inductance drop (to 3-50%), and it then gives up the shielding of")
    print("   layers below (rms field 0.83-1.0 of no plane).  Default: keep the plane; if loss or Q must win, clear a")
    print("   region well beyond the part's field footprint, never a body-sized hole.")


if __name__ == "__main__":
    convergence()
    main()
