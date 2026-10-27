# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mutual inductance between small current loops, with and without a ground
plane, as a literal "physical field" placement kernel (xd).

Neumann double sum over discretized polygon loops; a perfect ground plane at
z = 0 is modelled by an image loop (mirror z -> -z, reversed traversal).
Prints:
  A. coupling vs lateral distance for flat (axis normal to board) and
     standing (axis in the board plane) aggressor loops, free space vs plane;
  B. the 54.7 degree "magic angle" null between two in-plane-axis dipoles;
  C. a mirrored ("figure-8") pair of hot loops vs a single loop.

Run:  python tools/research/physics/xd_loop_coupling.py
Deterministic, < 20 s.
"""
import numpy as np

MU0 = 4e-7 * np.pi


def rect(center, size, normal, nseg=40):
    """Closed rectangular loop as an (N,3) point list. normal: 'z', 'x' or 'y'."""
    cx, cy, cz = center
    a, b = size
    pts2 = []
    for (x0, y0), (x1, y1) in [((-a/2, -b/2), (a/2, -b/2)), ((a/2, -b/2), (a/2, b/2)),
                               ((a/2, b/2), (-a/2, b/2)), ((-a/2, b/2), (-a/2, -b/2))]:
        for t in np.linspace(0, 1, nseg, endpoint=False):
            pts2.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
    pts2 = np.array(pts2)
    if normal == "z":
        p = np.c_[pts2[:, 0], pts2[:, 1], np.zeros(len(pts2))]
    elif normal == "x":
        p = np.c_[np.zeros(len(pts2)), pts2[:, 0], pts2[:, 1]]
    else:
        p = np.c_[pts2[:, 0], np.zeros(len(pts2)), pts2[:, 1]]
    return p + np.array([cx, cy, cz])


def segs(p):
    q = np.roll(p, -1, axis=0)
    return (p + q) / 2, q - p


def mutual(p1, p2):
    m1, d1 = segs(p1); m2, d2 = segs(p2)
    r = np.linalg.norm(m1[:, None, :] - m2[None, :, :], axis=2)
    return MU0 / (4 * np.pi) * ((d1 @ d2.T) / r).sum()


def image(p):
    q = p.copy(); q[:, 2] *= -1
    return q[::-1]   # mirrored and reversed traversal = image current


def mutual_plane(p1, p2):
    return mutual(p1, p2) + mutual(p1, image(p2))


def main():
    s = 3e-3   # 3 x 3 mm loops
    h = 0.5e-3 # loop centre height above the plane
    print("== A. 3x3 mm aggressor vs 3x3 mm flat victim loop, centres 0.5 mm above board; M in pH")
    print("   r(mm)  flat-flat free  flat-flat plane   standing-flat free  standing-flat plane  standing-standing(coaxial) plane")
    for r in (5e-3, 10e-3, 20e-3, 40e-3):
        vic = rect((r, 0, h), (s, s), "z")
        ag_flat = rect((0, 0, h), (s, s), "z")
        ag_st = rect((0, 0, h + s / 2), (s, s), "x")   # standing loop, axis along x, bottom edge at h
        vic_st = rect((r, 0, h + s / 2), (s, s), "x")
        vals = [mutual(ag_flat, vic), mutual_plane(ag_flat, vic),
                mutual(ag_st, vic), mutual_plane(ag_st, vic), mutual_plane(ag_st, vic_st)]
        print(f"   {r*1e3:5.0f}  " + "  ".join(f"{v*1e12:14.4f}" for v in vals))
    print("   flat loops over a plane: coupling falls ~ h^2/r^5 (plane image cancels the dipole);")
    print("   standing loops: the image adds, coupling stays dipole-like ~1/r^3 (doubled).")

    print("== B. two standing loops (axes both along x) 20 mm apart at angle phi from the axis; plane present")
    for phi in (0, 30, 45, 54.7, 60, 90):
        ph = np.radians(phi); r = 20e-3
        a = rect((0, 0, h + s / 2), (s, s), "x")
        b = rect((r * np.cos(ph), r * np.sin(ph), h + s / 2), (s, s), "x")
        print(f"   phi={phi:5.1f} deg: M = {mutual_plane(a, b)*1e12:8.4f} pH")
    print("   (dipole-dipole coupling ~ (1 - 3 cos^2 phi): null at 54.7 deg, the NMR 'magic angle')")

    print("== C. single 3x6 mm flat hot loop vs mirrored pair (two 3x3 mm, opposite current), free space")
    for r in (10e-3, 20e-3, 40e-3):
        for ang in (0, 90):
            ph = np.radians(ang)
            vic = rect((r * np.cos(ph), r * np.sin(ph), 0), (s, s), "z")
            single = rect((0, 0, 0), (s, 2 * s), "z")
            left = rect((0, -s / 2, 0), (s, s), "z")
            right = rect((0, s / 2, 0), (s, s), "z")[::-1]   # opposite circulation
            pair = mutual(left, vic) + mutual(right, vic)
            unbal = 0.6 * mutual(left, vic) + 0.4 * mutual(right, vic)
            ms = mutual(single, vic)
            print(f"   r={r*1e3:3.0f} mm dir={ang:3d} deg: single {ms*1e12:8.4f} pH, mirrored pair {pair*1e12:8.4f} pH "
                  f"({20*np.log10(abs(pair/ms)):6.1f} dB), 60/40 unbalanced {unbal*1e12/1.0:8.4f} pH ({20*np.log10(abs(unbal/ms)):6.1f} dB)")


if __name__ == "__main__":
    main()
