# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Kernel source of the place terms (see kae.physics.jit, which loads this file twice: as
plain Python, the fallback, and compiled by numba with an on-disk cache). Module-level
functions only, so that numba can cache them; `jit` is the decorator the loader injects
(identity when the file is imported directly). Units: mm, nH, pF, K, W."""
import math

try:
    jit = _JIT          # noqa: F821  (injected by kae.physics.jit before execution)
except NameError:       # imported directly: plain Python
    def jit(f):
        return f

INF = math.inf
MU = 0.1                 # mu0 / 4 pi, nH/mm
ETA0 = 376.730313        # ohm
C0 = 299.792458          # mm/ns
TCU = 0.035
EPS0 = 8.8541878128e-3     # pF/mm
A2_NEAR = 0.3 ** 2       # mm^2: closest approach of two distinct conductors' axes (coupling)


@jit
def z0_air(w, h):
    u = max(w, 1e-6) / max(h, 1e-6)
    f = 6.0 + (2.0 * math.pi - 6.0) * math.exp(-((30.666 / u) ** 0.7528))
    return ETA0 / (2.0 * math.pi) * math.log(f / u + math.sqrt(1.0 + (2.0 / u) ** 2))


@jit
def deff(w, h):
    if h == INF:
        return INF
    a = 0.2235 * (w + TCU)
    return a * math.exp(z0_air(w, h) / C0 / (2.0 * MU))


@jit
def m_self(ln, d):
    if d < 1e-9:
        d = 1e-9
    return 2.0 * MU * (ln * math.asinh(ln / d) - math.sqrt(ln * ln + d * d) + d)


@jit
def G(u, d):
    return u * math.asinh(u / d) - math.sqrt(u * u + d * d)


@jit
def m_par(l1, l2, s, d):
    if d < 1e-9:
        d = 1e-9
    return MU * (G(s + l2, d) - G(s + l2 - l1, d) - G(s, d) + G(s - l1, d))


@jit
def xlogx(x):
    return x * math.log(x) if x > 1e-12 else 0.0


@jit
def collinear(l1, l2, g):
    return MU * (xlogx(l1 + l2 + g) - xlogx(l1 + g) - xlogx(l2 + g) + xlogx(g))


@jit
def strip_self(ln, w, h):
    a = 0.2235 * (w + TCU)
    de = deff(w, h)
    if de == INF:
        return m_self(ln, a)
    return m_self(ln, a) - m_self(ln, de)


@jit
def ties(z, r, d, h):
    """Two antiparallel vertical terminations of height z, distance d, from height h
    (d floored at the radius: coincident terminations carry no loop)."""
    d = max(d, r)
    if h == INF:
        return 2.0 * m_self(z, r) - 2.0 * m_par(z, z, 0.0, max(d, 1e-6))
    return 2.0 * (m_self(z, r) + collinear(z, z, 2.0 * h)) \
        - 2.0 * (m_par(z, z, 0.0, d) + m_par(z, z, -2.0 * h - z, d))


@jit
def via_return(h, d, r):
    d = max(d, 2.0 * r)
    return 2.0 * (m_self(h, r) + collinear(h, h, 0.0)) - 2.0 * (m_par(h, h, 0.0, d) + m_par(h, h, -2.0 * h, d))


@jit
def lnspan(p, z):
    """Antiderivative of ln sqrt(p^2 + z^2) in p."""
    if z > 0.0:
        return 0.5 * p * math.log(p * p + z * z) - p + z * math.atan(p / z)
    if p == 0.0:
        return 0.0
    return p * math.log(abs(p)) - p


@jit
def gmd_lin(d1, d2, z):
    """Geometric mean of sqrt(p^2 + z^2) for p running linearly from d1 to d2 (signed
    lateral offsets; a crossing pair has d1 d2 < 0 and a finite mean)."""
    if abs(d2 - d1) <= 1e-9 * (abs(d1) + abs(d2) + z) + 1e-12:
        q = 0.5 * (d1 + d2)
        return math.sqrt(q * q + z * z)
    return math.exp((lnspan(d2, z) - lnspan(d1, z)) / (d2 - d1))


@jit
def pair_mut(ax, ay, bx, by, cx, cy, dx, dy, dz, zi, adjacent, cos_min, dmin, dsep):
    """2 [M(j, k) - M(j, image k)] for horizontal segments j = A->B and k = C->D, k lying
    dz above or below j, with the plane image of k at vertical distance zi from j
    (inf: no plane). Pairs closer to perpendicular than cos_min give 0; adjacent pairs
    (sharing a corner) with |cos| < 0.7 use the corner formula. Otherwise the parallel-
    filament formula over the projected overlap with the geometric mean distance of the
    linearly varying offset, floored at dsep (antiparallel or non-adjacent pairs: two
    conductors on one layer cannot overlap) or dmin (the conductor's own GMD)."""
    ux = bx - ax
    uy = by - ay
    l1 = math.sqrt(ux * ux + uy * uy)
    vx = dx - cx
    vy = dy - cy
    l2 = math.sqrt(vx * vx + vy * vy)
    if l1 < 1e-9 or l2 < 1e-9:
        return 0.0
    ux /= l1
    uy /= l1
    c = (ux * vx + uy * vy) / l2
    if -cos_min < c < cos_min:
        return 0.0
    qx = cx - ax
    qy = cy - ay
    rx = dx - ax
    ry = dy - ay
    s0 = qx * ux + qy * uy
    s1 = rx * ux + ry * uy
    d1 = qx * uy - qy * ux
    d2 = rx * uy - ry * ux
    if s1 >= s0:
        lo = s0
        e1 = s1
    else:
        lo = s1
        e1 = s0
    e2 = e1 - l1
    e3 = lo - l1
    di = INF
    if adjacent and -0.7 < c < 0.7:
        R = math.hypot(dx - ax, dy - ay)
        a = min(l2 / (l1 + R), 1.0 - 1e-12)
        b = min(l1 / (l2 + R), 1.0 - 1e-12)
        m = c * (l1 * math.log((1 + a) / (1 - a)) + l2 * math.log((1 + b) / (1 - b)))
    else:
        d = gmd_lin(d1, d2, dz)
        fl = dsep if (c < 0.0 or not adjacent) else dmin
        if d < fl:
            # the conductors' axes cannot come closer than fl: the image sees the same
            # floored lateral offset
            if zi != INF:
                di = math.sqrt(max(fl * fl - dz * dz, 0.0) + zi * zi)
            d = fl
        elif zi != INF:
            di = gmd_lin(d1, d2, zi)
        m = G(e1, d) - G(e2, d) - G(lo, d) + G(e3, d)
        if c < 0:
            m = -m
    if zi != INF:
        if adjacent and -0.7 < c < 0.7:
            di = gmd_lin(d1, d2, zi)
        d = di
        mi = G(e1, d) - G(e2, d) - G(lo, d) + G(e3, d)
        if c > 0:
            m -= mi
        else:
            m += mi
    return 2.0 * MU * m


@jit
def lookup(H, x0, y0, res, x, y):
    i = int((x - x0) / res + 0.5)
    j = int((y - y0) / res + 0.5)
    if i < 0 or j < 0 or j >= H.shape[0] or i >= H.shape[1]:
        return -1
    return j * H.shape[1] + i


@jit
def loop_core(X, Y, C, S, GS, ti, tlx, tly, isbody, w, zb, bodyd, n, gnd, cos_min, clr, detour, thick, rvia,
              Hf, Hb, Nf, Nb, gmask, rx0, ry0, rres, px, py, hs):
    """Loop inductance (nH). clr: copper clearance (mm); px, py, hs: scratch arrays of
    length >= n."""
    sx = 0.0
    sy = 0.0
    for k in range(n):
        i = ti[k]
        c = C[i]
        s = S[i]
        ly = tly[k] * GS[i]
        x = X[i] + tlx[k] * c + ly * s
        y = Y[i] - tlx[k] * s + ly * c
        px[k] = x
        py[k] = y
        sx += x
        sy += y
    # reference-plane height per board side at the loop centroid; segments on opposite
    # sides of a stack with planes seen from both sides are shielded from each other
    side = GS[ti[0]]
    idx = lookup(Hf, rx0, ry0, rres, sx / n, sy / n)
    hF = INF if idx < 0 else Hf.flat[idx]
    hB = INF if idx < 0 else Hb.flat[idx]
    h = hF if side > 0 else hB
    shield = hF != INF and hB != INF
    A = 0.0
    B = 0.0
    for k in range(n):
        sk = GS[ti[k]]
        hk = hF if sk > 0 else hB
        if isbody[k]:
            z = zb[k]
            r = 0.2235 * (w[k] + TCU)
            A += ties(z, r, bodyd[k], hk)
            hs[k] = INF if hk == INF else hk + z
            A += strip_self(bodyd[k], w[k], hs[k])
        else:
            hs[k] = hk
    # board hops (optionally stretched about their midpoints)
    for k in range(n):
        if isbody[k]:
            continue
        k1 = k + 1 if k + 1 < n else 0
        ln = math.hypot(px[k1] - px[k], py[k1] - py[k]) * detour
        sk = strip_self(ln, w[k], hs[k])
        if k == gnd:
            B = sk
        else:
            A += sk
    MAB = 0.0
    for j in range(n):
        j1 = j + 1 if j + 1 < n else 0
        ax = px[j]
        ay = py[j]
        bx = px[j1]
        by = py[j1]
        if detour != 1.0 and not isbody[j]:
            mx = 0.5 * (ax + bx)
            my = 0.5 * (ay + by)
            ax = mx + (ax - mx) * detour
            ay = my + (ay - my) * detour
            bx = mx + (bx - mx) * detour
            by = my + (by - my) * detour
        for k in range(j + 1, n):
            k1 = k + 1 if k + 1 < n else 0
            cx = px[k]
            cy = py[k]
            dx = px[k1]
            dy = py[k1]
            if detour != 1.0 and not isbody[k]:
                mx = 0.5 * (cx + dx)
                my = 0.5 * (cy + dy)
                cx = mx + (cx - mx) * detour
                cy = my + (cy - my) * detour
                dx = mx + (dx - mx) * detour
                dy = my + (dy - my) * detour
            sj = GS[ti[j]]
            sk = GS[ti[k]]
            if shield and sj != sk:
                continue
            hj = hs[j]
            hk = hs[k]
            if hj == INF or hk == INF:
                zi = INF
                dz = thick if sj != sk else 0.0
            else:
                zi = hj + hk
                dz = abs(hj - hk)
            dmin = 0.2235 * (min(w[j], w[k]) + TCU)
            dsep = dmin
            if dz == 0.0 and not isbody[j] and not isbody[k]:
                dsep = 0.5 * (w[j] + w[k]) + clr
            adj = (k == j + 1 or (j == 0 and k == n - 1)) and hj == hk
            if k == j + 1 or not adj:
                m = pair_mut(ax, ay, bx, by, cx, cy, dx, dy, dz, zi, adj, cos_min, dmin, dsep)
            else:
                m = pair_mut(cx, cy, dx, dy, ax, ay, bx, by, dz, zi, adj, cos_min, dmin, dsep)
            if j == gnd or k == gnd:
                MAB += 0.5 * m
            else:
                A += m
    # vias where a board hop changes sides
    nth = 0
    for k in range(n):
        if isbody[k]:
            continue
        k1 = k + 1 if k + 1 < n else 0
        if GS[ti[k]] != GS[ti[k1]]:
            A += m_self(thick, rvia)
            for q in range(k + 1, n):
                if isbody[q]:
                    continue
                q1 = q + 1 if q + 1 < n else 0
                if GS[ti[q]] != GS[ti[q1]]:
                    d = math.hypot(px[k1] - px[q1], py[k1] - py[q1])
                    A -= 2.0 * m_par(thick, thick, 0.0, max(d, rvia))
            nth += 1
    if gnd < 0:
        return A
    lateral = A + B + 2.0 * MAB
    h = hs[gnd]
    if h == INF:
        return lateral
    g1 = gnd + 1 if gnd + 1 < n else 0
    N = Nf if GS[ti[gnd]] > 0 else Nb
    gx = 0.5 * (px[gnd] + px[g1])
    gy = 0.5 * (py[gnd] + py[g1])
    gi = lookup(N, rx0, ry0, rres, gx, gy)
    if gi < 0:
        return lateral
    net = N.flat[gi]
    if net < 0 or not gmask[net]:
        return lateral
    Cv = via_return(h, math.hypot(px[g1] - px[gnd], py[g1] - py[gnd]) * detour, rvia)
    if B + Cv <= 1e-12:
        return lateral
    return A + MAB + (B + MAB) * (Cv - MAB) / (B + Cv)


@jit
def cext(A, h):
    """Charge strength (pF) of a copper patch of area A at height h over a plane, seen from
    the air side: a square of side s with the per-length capacitance of an air microstrip,
    C'_air(s, h) = 1 / (c0 Z0_air(s, h)) (Hammerstad-Jensen), along it and its fringe f
    across its ends: s (2 C'_air - eps0 s / h). Within 4 % of a method-of-moments solve for
    s / h >= 1.5 (16 % low at s / h = 0.6)."""
    s = math.sqrt(A)
    cpa = 1e3 / (C0 * z0_air(s, h))
    return s * (2.0 * cpa - EPS0 * s / h)


@jit
def patches_near(XA, YA, AA, XV, YV, AV, h, eps_r, eps0):
    k = 1.0 / (4.0 * math.pi * eps0)
    cm = 0.0
    for a in range(XA.shape[0]):
        ca = cext(AA[a], h)
        for v in range(XV.shape[0]):
            rr = max(math.hypot(XA[a] - XV[v], YA[a] - YV[v]), 0.5 * (math.sqrt(AA[a]) + math.sqrt(AV[v])))
            p = k * (1.0 / rr - 1.0 / math.sqrt(rr * rr + 4.0 * h * h))
            cm += ca * cext(AV[v], h) * p
    return cm


@jit
def k0(x):
    if x <= 2.0:
        t = x / 3.75
        t2 = t * t
        i0 = 1.0 + t2 * (3.5156229 + t2 * (3.0899424 + t2 * (1.2067492 + t2 * (0.2659732 + t2 * (0.0360768
                                                                                               + t2 * 0.0045813)))))
        y = x * x / 4.0
        return -math.log(x / 2.0) * i0 + (-0.57721566 + y * (0.42278420 + y * (0.23069756 + y * (0.03488590 + y * (
            0.00262698 + y * (0.00010750 + y * 0.0000074))))))
    y = 2.0 / x
    return math.exp(-x) / math.sqrt(x) * (1.25331414 + y * (-0.07832358 + y * (0.02189568 + y * (-0.01062446 + y * (
        0.00587872 + y * (-0.00251540 + y * 0.00053208))))))


@jit
def k1(x):
    """Modified Bessel K1 (Abramowitz & Stegun 9.8.3, 9.8.7, 9.8.8; |rel err| < 1e-7)."""
    if x <= 2.0:
        t = x / 3.75
        t2 = t * t
        i1 = x * (0.5 + t2 * (0.87890594 + t2 * (0.51498869 + t2 * (0.15084934 + t2 * (0.02658733 + t2 * (
            0.00301532 + t2 * 0.00032411))))))
        y = x * x / 4.0
        return (x * math.log(x / 2.0) * i1 + 1.0 + y * (0.15443144 + y * (-0.67278579 + y * (-0.18156897 + y * (
            -0.01919402 + y * (-0.00110404 + y * -0.00004686)))))) / x
    y = 2.0 / x
    return math.exp(-x) / math.sqrt(x) * (1.25331414 + y * (0.23498619 + y * (-0.03655620 + y * (0.01504268 + y * (
        -0.00780353 + y * (0.00325614 + y * -0.00068245))))))


@jit
def fin_sum(tx, ty, IX, IY, a, lam):
    """sum over the image lattice (IX x IY) of K0(max(r, a)/lam)."""
    s = 0.0
    for p in range(IX.shape[0]):
        dx = tx - IX[p]
        for q in range(IY.shape[0]):
            dy = ty - IY[q]
            r = math.sqrt(dx * dx + dy * dy)
            if r < a:
                r = a
            s += k0(r / lam)
    return s


@jit
def shape_geo(P, closed):
    """centroid x, y, size, signed area, chord x, y of a polyline (k, 2)."""
    k = P.shape[0]
    cx = 0.0
    cy = 0.0
    for i in range(k):
        cx += P[i, 0]
        cy += P[i, 1]
    cx /= k
    cy /= k
    size = 0.0
    for i in range(k):
        size = max(size, abs(P[i, 0] - cx), abs(P[i, 1] - cy))
    area = 0.0
    if closed:
        for i in range(k):
            j = i + 1 if i + 1 < k else 0
            area += P[i, 0] * P[j, 1] - P[i, 1] * P[j, 0]
        area *= 0.5
    return cx, cy, 2.0 * size, area, P[k - 1, 0] - P[0, 0], P[k - 1, 1] - P[0, 1]


@jit
def dip_field(xa, ya, za, mx, my, mz, xv, yv, zv, vx, vy, vz):
    rx = xv - xa
    ry = yv - ya
    rz = zv - za
    R2 = rx * rx + ry * ry + rz * rz
    R = math.sqrt(R2)
    mr = (mx * rx + my * ry + mz * rz) / R2
    return (3.0 * mr * (vx * rx + vy * ry + vz * rz) - (mx * vx + my * vy + mz * vz)) / (R2 * R)


@jit
def seg_mut(ax, ay, az, bx, by, bz, cx, cy, cz, dx, dy, dz, a2, ng, gt, gw):
    """Neumann integral (mm; times mu0/4pi gives nH) of two straight filaments A = a->b and
    V = c->d: inner integral along V in closed form (asinh), outer along A by ng-point
    Gauss-Legendre. The squared distance to V's line is floored at a2 (conductors of
    finite section cannot coincide), which keeps crossing filaments finite."""
    ux = bx - ax
    uy = by - ay
    uz = bz - az
    la = math.sqrt(ux * ux + uy * uy + uz * uz)
    wx = dx - cx
    wy = dy - cy
    wz = dz - cz
    lv = math.sqrt(wx * wx + wy * wy + wz * wz)
    if la < 1e-9 or lv < 1e-9:
        return 0.0
    wx /= lv
    wy /= lv
    wz /= lv
    cs = (ux * wx + uy * wy + uz * wz) / la
    if -1e-12 < cs < 1e-12:
        return 0.0
    acc = 0.0
    for q in range(ng):
        px = ax + gt[q] * ux - cx
        py = ay + gt[q] * uy - cy
        pz = az + gt[q] * uz - cz
        t0 = px * wx + py * wy + pz * wz
        rho2 = px * px + py * py + pz * pz - t0 * t0
        if rho2 < a2:
            rho2 = a2
        rho = math.sqrt(rho2)
        acc += gw[q] * (math.asinh((lv - t0) / rho) + math.asinh(t0 / rho))
    return cs * la * acc


@jit
def path_segments(P, closed, z, image, out0, out1, start):
    """Write the straight segments of a path at height z into out0/out1 (start, end) from
    row `start` (closed: polygon; open: via up at the first point, vias down at the
    last, through the plane z = 0); with image, append the plane images (z mirrored,
    direction reversed). Returns the next free row."""
    k = P.shape[0]
    c = start
    if not closed:
        out0[c, 0] = P[0, 0]
        out0[c, 1] = P[0, 1]
        out0[c, 2] = 0.0
        out1[c, 0] = P[0, 0]
        out1[c, 1] = P[0, 1]
        out1[c, 2] = z
        c += 1
    nseg = k if closed else k - 1
    for i in range(nseg):
        j = i + 1 if i + 1 < k else 0
        out0[c, 0] = P[i, 0]
        out0[c, 1] = P[i, 1]
        out0[c, 2] = z
        out1[c, 0] = P[j, 0]
        out1[c, 1] = P[j, 1]
        out1[c, 2] = z
        c += 1
    if not closed:
        out0[c, 0] = P[k - 1, 0]
        out0[c, 1] = P[k - 1, 1]
        out0[c, 2] = z
        out1[c, 0] = P[k - 1, 0]
        out1[c, 1] = P[k - 1, 1]
        out1[c, 2] = 0.0
        c += 1
    if image:
        n = c - start
        for q in range(n):
            r = start + q
            out0[c, 0] = out1[r, 0]
            out0[c, 1] = out1[r, 1]
            out0[c, 2] = -out1[r, 2]
            out1[c, 0] = out0[r, 0]
            out1[c, 1] = out0[r, 1]
            out1[c, 2] = -out0[r, 2]
            c += 1
    return c


@jit
def segs_mutual(A0, A1, na, V0, V1, nv, a2, gt3, gw3, gt6, gw6):
    """mu0/4pi sum over segment pairs of seg_mut: 6-point outer rule for pairs closer than
    their summed lengths, 3-point otherwise."""
    m = 0.0
    for i in range(na):
        mx = 0.5 * (A0[i, 0] + A1[i, 0])
        my = 0.5 * (A0[i, 1] + A1[i, 1])
        mz = 0.5 * (A0[i, 2] + A1[i, 2])
        la = math.sqrt((A1[i, 0] - A0[i, 0]) ** 2 + (A1[i, 1] - A0[i, 1]) ** 2 + (A1[i, 2] - A0[i, 2]) ** 2)
        for j in range(nv):
            lv = math.sqrt((V1[j, 0] - V0[j, 0]) ** 2 + (V1[j, 1] - V0[j, 1]) ** 2 + (V1[j, 2] - V0[j, 2]) ** 2)
            ex = 0.5 * (V0[j, 0] + V1[j, 0]) - mx
            ey = 0.5 * (V0[j, 1] + V1[j, 1]) - my
            ez = 0.5 * (V0[j, 2] + V1[j, 2]) - mz
            near = ex * ex + ey * ey + ez * ez < (la + lv) ** 2
            # integrate along the longer segment's partner: outer over A
            if near:
                m += seg_mut(A0[i, 0], A0[i, 1], A0[i, 2], A1[i, 0], A1[i, 1], A1[i, 2],
                             V0[j, 0], V0[j, 1], V0[j, 2], V1[j, 0], V1[j, 1], V1[j, 2], a2, 6, gt6, gw6)
            else:
                m += seg_mut(A0[i, 0], A0[i, 1], A0[i, 2], A1[i, 0], A1[i, 1], A1[i, 2],
                             V0[j, 0], V0[j, 1], V0[j, 2], V1[j, 0], V1[j, 1], V1[j, 2], a2, 3, gt3, gw3)
    return MU * m


@jit
def loop_mutual_core(PA, ca, za, PV, cv, zv, h, gt3, gw3, gt6, gw6, sp, sd, vp, vd):
    """|M| (nH) between aggressor path PA (closed if ca) at za and victim PV (cv) at zv over
    the plane at height reference h (inf: free space). Far apart: point dipoles of the loop
    plus its image (closed: +A at +z, -A at -z; open: 2 z z^ x chord) against the victim's
    physical area vector; near: segment-pair Neumann integrals (inner closed form, outer
    Gauss) with the aggressor's plane images."""
    xa, ya, sa, aa, cha_x, cha_y = shape_geo(PA, ca)
    xv, yv, sv, av, chv_x, chv_y = shape_geo(PV, cv)
    r = math.hypot(xa - xv, ya - yv)
    big = max(sa, sv, 1e-3)
    if h == INF:
        if not (ca and cv):
            return 0.0
        if r >= 2.0 * big:
            return abs(MU * aa * av / (r * r * r))
        na = path_segments(PA, True, 0.0, False, sp, sd, 0)
        nv = path_segments(PV, True, 0.0, False, vp, vd, 0)
        return abs(segs_mutual(sp, sd, na, vp, vd, nv, A2_NEAR, gt3, gw3, gt6, gw6))
    if r >= 2.0 * big and r >= 4.0 * h:
        m = 0.0
        if cv:
            vx_, vy_, vz_, mvx, mvy, mvz = xv, yv, zv, 0.0, 0.0, av
        else:
            vx_, vy_, vz_, mvx, mvy, mvz = xv, yv, 0.5 * zv, -zv * chv_y, zv * chv_x, 0.0
        if ca:
            m += dip_field(xa, ya, za, 0.0, 0.0, aa, vx_, vy_, vz_, mvx, mvy, mvz)
            m += dip_field(xa, ya, -za, 0.0, 0.0, -aa, vx_, vy_, vz_, mvx, mvy, mvz)
        else:
            m += dip_field(xa, ya, 0.0, -2.0 * za * cha_y, 2.0 * za * cha_x, 0.0, vx_, vy_, vz_, mvx, mvy, mvz)
        return abs(MU * m)
    na = path_segments(PA, ca, za, True, sp, sd, 0)
    nv = path_segments(PV, cv, zv, False, vp, vd, 0)
    return abs(segs_mutual(sp, sd, na, vp, vd, nv, A2_NEAR, gt3, gw3, gt6, gw6))


@jit
def patches_cm_core(XA, YA, AA, XV, YV, AV, h, eps_r, eps0):
    """First-order mutual capacitance (pF) of two patch sets over a plane at h:
    C_m = sum C_a C_v p_av, p_av = (1/(4 pi eps0)) (1/r - 1/sqrt(r^2 + 4 h^2)), with the
    patches' air-side strengths (cext); far apart, the strength-weighted centroids."""
    ta = 0.0
    tv = 0.0
    sa = 0.0
    sv = 0.0
    ax = 0.0
    ay = 0.0
    vx = 0.0
    vy = 0.0
    for a in range(XA.shape[0]):
        ta += AA[a]
        sa += cext(AA[a], h)
        ax += XA[a] * AA[a]
        ay += YA[a] * AA[a]
    for v in range(XV.shape[0]):
        tv += AV[v]
        sv += cext(AV[v], h)
        vx += XV[v] * AV[v]
        vy += YV[v] * AV[v]
    ax /= ta
    ay /= ta
    vx /= tv
    vy /= tv
    ea = 0.0
    ev = 0.0
    for a in range(XA.shape[0]):
        ea = max(ea, abs(XA[a] - ax), abs(YA[a] - ay))
    for v in range(XV.shape[0]):
        ev = max(ev, abs(XV[v] - vx), abs(YV[v] - vy))
    r = math.hypot(ax - vx, ay - vy)
    k = 1.0 / (4.0 * math.pi * eps0)
    if r > 3.0 * (ea + ev) + 2.0 * h:
        p = k * (1.0 / r - 1.0 / math.sqrt(r * r + 4.0 * h * h))
        return sa * sv * p
    return patches_near(XA, YA, AA, XV, YV, AV, h, eps_r, eps0)


@jit
def fin_column(TX, TY, IX, IY, a, lam, out):
    """out[t] = sum over the image lattice of one source of K0(max(r, a)/lam), each target t."""
    for t in range(TX.shape[0]):
        out[t] = fin_sum(TX[t], TY[t], IX, IY, a, lam)


@jit
def fin_row(tx, ty, SX, SY, A, lam, out):
    """out[s] = sum over source s's image lattice (rows of SX, SY) of K0(max(r, a_s)/lam)."""
    for k in range(SX.shape[0]):
        out[k] = fin_sum(tx, ty, SX[k], SY[k], A[k], lam)
