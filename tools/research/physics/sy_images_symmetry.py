# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Image theory, duality and symmetry-group checks for the round-2 SY lens (lens-sy.md).

numpy/scipy only; about 1 minute. Sections (run all, or name them):
  slit     The slit-cost law is a mode-III crack with images. Zero-width cuts in a resistor-network
           strip (R_s = 1, W = 20 mm, L = 100 mm). Compares FD with round 1's (pi/4)(dpsi/I)^2 and
           with the exact image-array forms: interior centred slit dR = -(2/pi) ln cos(pi q/2),
           edge notch dR = -(4/pi) ln cos(pi q/2), q = dpsi/I (edge factor exactly 2).
           Also the dual (Keller): a perfectly conducting needle ALONG the flow saves
           ~ (pi/4)(dphi/(R_s I))^2 for short needles.
  halo     Cancellation with imbalance. Flat loops (vertical moments) with and without a plane
           image (h = 0.1 mm); mirrored half-loops (+/-, 3 mm apart) with current imbalance eps.
           Halo radius vs eps against the floor eps^(1/3) (free) and eps^(1/5) (plane).
  share    Curie's principle for paralleled parts: same-end comb, reverse return (Z2), and a
           binary tree (transitive symmetry). Max/min current share.
  corners  Wedge exponents pi/alpha - 1 vs round-1 computed numbers; Babinet slot inductance
           (Booker) vs round 1's slotline formula and PEEC table.
  scales   The image-validity length l_d = R_s/(omega mu0) and the 3-D node-vs-loop crossover
           distance over a plane (patch dipole 2*eps0*A*V vs loop quadrupole).
"""
import math
import sys
import time

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

MU0 = 4e-7 * math.pi
EPS0 = 8.854187e-12
ETA0 = math.sqrt(MU0 / EPS0)


# ------------------------------------------------------------------------------------------
def strip_resistance(nx, ny, cut=None, needle=None, gbig=1e8):
    """Squares of a unit-R_s strip, nx columns (width) x ny rows (length), current along rows.
    cut = (row, i0, i1): remove vertical links between row and row+1 for columns i0..i1-1.
    needle = (col, j0, j1): vertical links in column col between rows j0..j1 get conductance gbig."""
    n = nx * ny
    idx = np.arange(n).reshape(ny, nx)
    # horizontal links (within a row)
    a1 = idx[:, :-1].ravel(); a2 = idx[:, 1:].ravel(); ga = np.ones(a1.size)
    # vertical links (between rows)
    b1 = idx[:-1, :].ravel(); b2 = idx[1:, :].ravel(); gb = np.ones(b1.size).reshape(ny - 1, nx)
    if cut is not None:
        r, i0, i1 = cut
        gb[r, i0:i1] = 0.0
    if needle is not None:
        c, j0, j1 = needle
        gb[j0:j1, c] = gbig
    gb = gb.ravel()
    e1 = np.concatenate([a1, b1]); e2 = np.concatenate([a2, b2]); g = np.concatenate([ga, gb])
    keep = g > 0
    e1, e2, g = e1[keep], e2[keep], g[keep]
    # terminals: row 0 to V=1 via conductance 2 (half cell), last row to V=0 via 2
    diag = np.bincount(e1, g, n) + np.bincount(e2, g, n)
    diag[idx[0, :]] += 2.0
    diag[idx[-1, :]] += 2.0
    A = sp.csc_matrix((np.concatenate([diag, -g, -g]),
                       (np.concatenate([np.arange(n), e1, e2]), np.concatenate([np.arange(n), e2, e1]))),
                      shape=(n, n))
    rhs = np.zeros(n)
    rhs[idx[0, :]] = 2.0
    v = spla.spsolve(A, rhs)
    I = (2.0 * (1.0 - v[idx[0, :]])).sum()
    return 1.0 / I


def sec_slit():
    print("== slit: zero-width cuts in a strip (R_s = 1), W = 20 mm, L = 100 mm; dR in squares")
    for a_mm in (0.1, 0.05):
        W, L = 20.0, 100.0
        nx, ny = int(round(W / a_mm)), int(round(L / a_mm))
        if a_mm < 0.1:
            ny = int(round(60.0 / a_mm))  # shorter strip for the fine check (ends still > 2W away)
        t0 = time.time()
        R0 = strip_resistance(nx, ny)
        print(f"  cell a = {a_mm} mm ({nx} x {ny}); base R = {R0:.4f} sq (ideal {ny/nx:.4f})")
        print("     cut                         q=dpsi/I  FD dR    (pi/4)q^2   exact-image   FD/exact")
        cases = []
        lens = (2.0, 5.0, 10.0, 15.0) if a_mm >= 0.1 else (5.0, 10.0)
        for ell in lens:
            n = int(round(ell / a_mm))
            i0 = nx // 2 - n // 2
            cases.append((f"interior, centred, {ell:4.1f} mm", (ny // 2, i0, i0 + n), n / nx, "int"))
        for ell in ((2.0, 5.0, 10.0) if a_mm >= 0.1 else (5.0,)):
            n = int(round(ell / a_mm))
            cases.append((f"edge notch, {ell:4.1f} mm", (ny // 2, 0, n), n / nx, "edge"))
        for name, cut, q, kind in cases:
            dR = strip_resistance(nx, ny, cut=cut) - R0
            quad = math.pi / 4 * q * q
            ex = -(2 / math.pi) * math.log(math.cos(math.pi * q / 2))
            if kind == "edge":
                ex *= 2
            print(f"     {name:27s} {q:6.3f}  {dR:8.5f}  {quad:8.5f}   {ex:8.5f}     {dR/ex:5.3f}")
        if a_mm >= 0.1:
            print("     dual: perfectly conducting needle ALONG the flow (centred), same lengths")
            print("     needle                      q=dphi/(Rs I)  FD dR    -(pi/4)q^2")
            for ell in (2.0, 5.0, 10.0, 15.0):
                n = int(round(ell / a_mm))
                j0 = ny // 2 - n // 2
                dR = strip_resistance(nx, ny, needle=(nx // 2, j0, j0 + n)) - R0
                q = n / nx
                print(f"     needle {ell:4.1f} mm along flow     {q:6.3f}       {dR:8.5f}  {-math.pi/4*q*q:8.5f}")
        print(f"   [{time.time()-t0:.1f} s]")


# ------------------------------------------------------------------------------------------
def bz_dipoles(src, pts):
    """B_z (units of mu0/4pi) at points pts (N,3) from vertical dipoles src [(m, x, y, z)]."""
    bz = np.zeros(len(pts))
    for m, x, y, z in src:
        d = pts - np.array([x, y, z])
        R2 = (d ** 2).sum(1)
        R = np.sqrt(R2)
        bz += m * (3 * d[:, 2] ** 2 / R2 - 1) / R ** 3
    return bz


def halo_radius(src, h, budget, rs, nphi=72):
    phis = np.linspace(0, 2 * np.pi, nphi, endpoint=False)
    worst = []
    for r in rs:
        pts = np.stack([r * np.cos(phis), r * np.sin(phis), np.full(nphi, h)], 1)
        worst.append(np.abs(bz_dipoles(src, pts)).max())
    worst = np.array(worst)
    above = np.nonzero(worst > budget)[0]
    if len(above) == 0:
        return rs[0]
    k = above[-1]
    if k + 1 >= len(rs):
        return rs[-1]
    # log interpolation between rs[k] and rs[k+1]
    w0, w1 = math.log(worst[k]), math.log(worst[k + 1])
    f = (math.log(budget) - w0) / (w1 - w0)
    return math.exp(math.log(rs[k]) + f * (math.log(rs[k + 1]) - math.log(rs[k])))


def exceed_area(src, h, budget, rs, nphi=180):
    """Area (m^2) of the region at height h where |B_z| > budget (polar, outermost crossing)."""
    phis = np.linspace(0, 2 * np.pi, nphi, endpoint=False)
    area = 0.0
    for ph in phis:
        pts = np.stack([rs * math.cos(ph), rs * math.sin(ph), np.full(len(rs), h)], 1)
        above = np.nonzero(np.abs(bz_dipoles(src, pts)) > budget)[0]
        R = rs[above[-1]] if len(above) else 0.0
        area += 0.5 * R * R * (2 * math.pi / nphi)
    return area


def sec_halo():
    print("== halo: flat-loop aggressor (moment 1), victim flat loops at the same height. 'cancel' splits it")
    print("   into mirrored half-loops (+/-0.5, 3 mm apart) with current imbalance eps. Budget set so that the")
    print("   single loop's worst-direction halo is 10 mm. Area = region where the budget is exceeded.")
    h, d = 0.1e-3, 3e-3
    rs = np.geomspace(1.0e-3, 0.3, 1200)
    for label, plane in (("free space", False), ("plane 0.1 mm below (PEC image)", True)):
        def with_images(src):
            if not plane:
                return src
            return src + [(-m, x, y, -z) for (m, x, y, z) in src]
        single = with_images([(1.0, 0.0, 0.0, h)])
        phis = np.linspace(0, 2 * np.pi, 72, endpoint=False)
        pts = np.stack([10e-3 * np.cos(phis), 10e-3 * np.sin(phis), np.full(72, h)], 1)
        budget = np.abs(bz_dipoles(single, pts)).max()
        R1 = halo_radius(single, h, budget, rs)
        A1 = exceed_area(single, h, budget, rs)
        n_exp = 3 if not plane else 5
        print(f"  {label}: single-loop halo {R1*1e3:.2f} mm, area {A1*1e6:.0f} mm^2")
        print("     eps    halo(mm) ratio  area ratio  floor eps^(1/n)  worst-dir field vs single (dB) at 10/30/100 mm"
              "  on the mirror plane at 10 mm (dB)")
        for eps in (0.0, 0.01, 0.03, 0.1, 0.2):
            pair = with_images([(0.5 * (1 + eps), -d / 2, 0.0, h), (-0.5 * (1 - eps), d / 2, 0.0, h)])
            Rp = halo_radius(pair, h, budget, rs)
            Ap = exceed_area(pair, h, budget, rs)
            dbs = []
            for r in (10e-3, 30e-3, 100e-3):
                p_ = np.stack([r * np.cos(phis), r * np.sin(phis), np.full(72, h)], 1)
                dbs.append(20 * math.log10(np.abs(bz_dipoles(pair, p_)).max() / np.abs(bz_dipoles(single, p_)).max()))
            pm = np.array([[0.0, 10e-3, h]])
            bm = abs(bz_dipoles(pair, pm)[0]) / abs(bz_dipoles(single, pm)[0])
            mdb = 20 * math.log10(bm) if bm > 1e-15 else -300.0
            floor = eps ** (1.0 / n_exp) if eps > 0 else float("nan")
            print(f"     {eps:4.2f}  {Rp*1e3:7.2f}  {Rp/R1:5.3f}   {Ap/A1:6.3f}      {floor:6.3f}        "
                  f"{dbs[0]:6.1f} {dbs[1]:6.1f} {dbs[2]:6.1f}                       {mdb:7.1f}")


# ------------------------------------------------------------------------------------------
def ladder_shares(N, r_seg, R_el, cfg):
    """Element currents for N parallel elements between a feed rail and a return rail."""
    nn = 2 * N
    G = np.zeros((nn, nn))

    def add(a, b, g):
        G[a, a] += g; G[b, b] += g; G[a, b] -= g; G[b, a] -= g
    for k in range(N - 1):
        add(k, k + 1, 1 / r_seg)
        add(N + k, N + k + 1, 1 / r_seg)
    for k in range(N):
        add(k, N + k, 1 / R_el)
    feed = {"same-end": 0, "reverse-return": 0, "centre feed, centre return": N // 2}[cfg]
    gnd = {"same-end": N, "reverse-return": 2 * N - 1, "centre feed, centre return": N + N // 2}[cfg]
    b = np.zeros(nn)
    b[feed] = 1.0
    keep = [i for i in range(nn) if i != gnd]
    v = np.zeros(nn)
    v[keep] = np.linalg.solve(G[np.ix_(keep, keep)], b[keep])
    return (v[:N] - v[N:]) / R_el


def tree_shares(levels, r_levels, R_el, perturb=0.0):
    """Binary feed tree and identical return tree to 2**levels elements. perturb: relative
    change of one level-1 branch (breaks the symmetry)."""
    N = 2 ** levels
    # node numbering: feed tree nodes (heap order 1..2N-1), return tree nodes offset
    nf = 2 * N  # heap indices 1..2N-1 used
    nn = 2 * nf
    G = np.zeros((nn, nn))

    def add(a, b, g):
        G[a, a] += g; G[b, b] += g; G[a, b] -= g; G[b, a] -= g
    for node in range(1, N):
        lvl = int(math.floor(math.log2(node)))
        for child in (2 * node, 2 * node + 1):
            r = r_levels[lvl]
            if perturb and node == 1 and child == 2:
                r *= (1 + perturb)
            add(node, child, 1 / r)
            add(nf + node, nf + child, 1 / r)
    leaves = list(range(N, 2 * N))
    for lf in leaves:
        add(lf, nf + lf, 1 / R_el)
    b = np.zeros(nn)
    b[1] = 1.0
    gnd = nf + 1
    keep = [i for i in range(nn) if i != gnd and i not in (0, nf)]
    v = np.zeros(nn)
    v[keep] = np.linalg.solve(G[np.ix_(keep, keep)], b[keep])
    return np.array([(v[lf] - v[nf + lf]) / R_el for lf in leaves])


def sec_share():
    print("== share: N = 8 paralleled elements, rail segment 1 mOhm, element 10 mOhm (round-1 case)")
    for cfg in ("same-end", "reverse-return", "centre feed, centre return"):
        I = ladder_shares(8, 1e-3, 10e-3, cfg)
        sym = np.abs(I - I[::-1]).max() / I.mean()
        print(f"  {cfg:28s} max/min {I.max()/I.min():5.2f}   |I_k - I_(N+1-k)|max/mean = {sym:.1e}")
    I = tree_shares(3, [1e-3, 1e-3, 1e-3], 10e-3)
    print(f"  {'binary tree (transitive)':28s} max/min {I.max()/I.min():5.3f}")
    I = tree_shares(3, [1e-3, 1e-3, 1e-3], 10e-3, perturb=0.2)
    print(f"  {'binary tree, one branch +20%':28s} max/min {I.max()/I.min():5.3f}")


# ------------------------------------------------------------------------------------------
def sec_corners():
    print("== corners: field/current near a wedge of interior angle alpha (in the domain where the")
    print("   field lives) scales as r^(pi/alpha - 1)")
    for name, alpha in (("thin edge / crack tip (2pi)", 2 * math.pi), ("re-entrant 270 deg", 1.5 * math.pi),
                        ("re-entrant 225 deg (inside of a 135 deg bend)", 1.25 * math.pi),
                        ("straight (180 deg)", math.pi), ("convex 90 deg", 0.5 * math.pi)):
        print(f"  {name:48s} exponent {math.pi/alpha - 1:+.3f}")
    print("  checks against round-1 [C] numbers:")
    print(f"   sharp 90 deg bend, peak J at 20/40/80 cells per width 2.6/3.3/4.1: ratios {3.3/2.6:.3f}, {4.1/3.3:.3f}"
          f" vs 2^(1/3) = {2**(1/3):.3f}")
    print(f"   pulse J^2 at the inside corner, 10 us/100 us/1 ms = 7.7/3.7/1.75: ratios {7.7/3.7:.3f}, {3.7/1.75:.3f}"
          f" per decade vs 10^(1/3) = {10**(1/3):.3f}  (<J^2> over a diffusion disk ~ rho^(-2/3) ~ t^(-1/3))")
    print(f"   HV corner field r/g 0.02 -> 0.05 -> 0.1: round-1 ratios 1.35, 1.26 vs (2.5)^(1/3) = {2.5**(1/3):.3f},"
          f" 2^(1/3) = {2**(1/3):.3f}")
    print("== Babinet (Booker): slot driving-point L = (eta0^2/4) * C of the complementary strip dipole")
    print("   C_dip = pi*eps0*l/(2*(ln(4l/g) - 1)) (thin dipole, equivalent radius g/4) -> L_slot = pi*mu0*l/(8*(ln(4l/g)-1))")
    print("   round 1 (two shorted slotline stubs): mu0*l/(2 ln(4l/g)); PEEC at h = 0.2 mm in parentheses")
    for (l_mm, g_mm, peec) in ((5, 0.1, 0.39), (10, 0.1, 0.79), (10, 0.4, 1.28), (20, 0.4, 2.34), (20, 0.5, None)):
        l, g = l_mm * 1e-3, g_mm * 1e-3
        L_b = math.pi * MU0 * l / (8 * (math.log(4 * l / g) - 1))
        L_r1 = MU0 * l / (2 * math.log(4 * l / g))
        ps = f"({peec:.2f})" if peec else ""
        print(f"   slot {l_mm:2d} x {g_mm:.1f} mm: Booker {L_b*1e9:5.2f} nH   round-1 {L_r1*1e9:5.2f} nH   ratio {L_b/L_r1:5.3f}  {ps}")
    # half-wave resonance and radiation resistance of the complementary pair
    print(f"   half-wave slot radiation resistance (Booker, free space): eta0^2/(4*73.1) = {ETA0**2/(4*73.1):.0f} ohm")


# ------------------------------------------------------------------------------------------
def sec_scales():
    print("== scales: a plane images a field pattern of lateral scale l when l >> l_d = R_s/(omega*mu0)")
    rs = 1.72e-8 / 35e-6
    print(f"   1 oz (R_s = {rs*1e3:.3f} mOhm/sq):")
    for f in (50, 5e3, 50e3, 500e3, 5e6, 50e6):
        print(f"     f = {f:>10.0f} Hz: l_d = {rs/(2*math.pi*f*MU0)*1e3:9.3f} mm")
    print("   frequency at which a structure of scale l is mirrored (l = l_d):")
    for name, l in (("trace return, l = h = 0.1 mm", 0.1e-3), ("via pair / gate loop, 1 mm", 1e-3),
                    ("hot loop, 5 mm", 5e-3), ("ADC ground region, 20 mm", 20e-3), ("whole board, 100 mm", 0.1)):
        print(f"     {name:32s} f = {rs/(2*math.pi*MU0*l)/1e3:9.1f} kHz")
    print("== 3-D node vs loop over a plane (r >> sizes, h = 0.1 mm, top-layer copper, air above)")
    print("   node: patch at V of area A_E -> vertical dipole p = 2 eps0 A_E V;  C_m = eps0 A_E A_v/(2 pi r^3)")
    print("   loop: moment m = I A_M at h with image -m -> M ~ (mu0/4pi) 18 h^2 A_M A_v / r^5 (flat victim)")
    h = 0.1e-3
    A_E, dvdt = 20e-6, 6e9      # 20 mm^2 switch node, 6 V/ns
    A_M, didt = 8e-6, 5.5e9     # 4 x 2 mm hot loop, 5.5 A/ns
    A_v = 1e-6                  # 1 mm^2 victim pad / loop
    print("     r(mm)  C_m(fF)   M(fH)    v_C @50ohm  v_C @1k   v_C @10k   v_M (mV)   [v in mV]")
    for r_mm in (3, 5, 10, 20, 40):
        r = r_mm * 1e-3
        Cm = EPS0 * A_E * A_v / (2 * math.pi * r ** 3)
        # exact two-dipole field for the magnetic case
        src = [(1.0, 0, 0, h), (-1.0, 0, 0, -h)]
        bz = bz_dipoles(src, np.array([[r, 0, h]]))[0]
        M = abs(MU0 / (4 * math.pi) * bz * A_M * A_v)
        vm = M * didt
        vc = [Z * Cm * dvdt for Z in (50, 1e3, 1e4)]
        print(f"     {r_mm:5d}  {Cm*1e15:7.3f}  {M*1e15:8.3f}   {vc[0]*1e3:8.4f}  {vc[1]*1e3:8.3f}  {vc[2]*1e3:8.2f}   {vm*1e3:8.4f}")
    for Z in (50, 1e3, 1e4):
        # crossover: Z*eps0*A_E*A_v/(2 pi r^3)*dvdt = (mu0/4pi)*18 h^2 A_M A_v/r^5 * didt
        r2 = (MU0 / (4 * math.pi) * 18 * h * h * A_M * didt) / (Z * EPS0 * A_E * dvdt / (2 * math.pi))
        print(f"   victim |Z| = {Z:6.0f} ohm: capacitive pickup exceeds magnetic beyond r = {math.sqrt(r2)*1e3:.1f} mm")


def sec_weave():
    print("== weave: a woven glass cloth is a 2-D lattice. Skew accumulates along directions perpendicular to a")
    print("   reciprocal-lattice vector with non-zero Dk amplitude (commensurate); elsewhere it stays bounded.")
    print("   Toy model Dk = 3.6 + A[cos(2pi x/px) + cos(2pi y/py)] + B cos(2pi x/px)cos(2pi y/py), A = 0.4")
    print("   (aligned-trace skew ~18 ps/in, like round 1's dDk 0.8), knuckle term B = kappa*A. Pair legs 0.3 mm apart,")
    print("   L = 50.8 mm (2 in); worst case over 64 pair positions. Skew in ps (per 2 in).")
    c0 = 2.998e8
    L, sp_ = 50.8e-3, 0.3e-3
    ds = 4e-6
    s = np.arange(0, L, ds)
    offs = [(u, v) for u in np.linspace(0, 1, 8, endpoint=False) for v in np.linspace(0, 1, 8, endpoint=False)]
    thetas = [0.0, 2.0, 5.0, 10.0, 15.0, 18.43, 22.0, 26.57, 30.0, 35.0, 40.0, 43.0, 45.0]
    for name, px, py in (("square-ish 2116-like (0.42 x 0.44 mm)", 0.423e-3, 0.438e-3),
                         ("square (0.45 x 0.45 mm)", 0.45e-3, 0.45e-3),
                         ("1080-like (0.42 x 0.54 mm)", 0.423e-3, 0.540e-3)):
        for kappa in (0.0, 0.5):
            A, B = 0.4, 0.5 * 0.4 if kappa else 0.0
            B = kappa * A
            row = []
            for th in thetas:
                t = math.radians(th)
                ux, uy = math.cos(t), math.sin(t)
                nx_, ny_ = -uy, ux  # transverse unit vector
                worst = 0.0
                for (u, v) in offs:
                    x0, y0 = u * px, v * py
                    sk = 0.0
                    for sign in (+1, -1):
                        x = x0 + sign * 0.5 * sp_ * nx_ + s * ux
                        y = y0 + sign * 0.5 * sp_ * ny_ + s * uy
                        cx, cy = np.cos(2 * np.pi * x / px), np.cos(2 * np.pi * y / py)
                        dk = 3.6 + A * (cx + cy) + B * cx * cy
                        sk += sign * np.sqrt(dk).sum() * ds / c0
                    worst = max(worst, abs(sk))
                row.append(worst * 1e12)
            print(f"  {name:38s} kappa={kappa:.1f}: " + "  ".join(f"{th:5.2f}deg {v:5.2f}" for th, v in zip(thetas, row)))


SECTIONS = {"slit": sec_slit, "halo": sec_halo, "share": sec_share, "corners": sec_corners, "scales": sec_scales,
            "weave": sec_weave}


def main(argv):
    names = [a for a in argv if a in SECTIONS] or list(SECTIONS)
    for n in names:
        t0 = time.time()
        SECTIONS[n]()
        print(f"   [{n}: {time.time()-t0:.1f} s]\n")


if __name__ == "__main__":
    main(sys.argv[1:])
