# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Analytic checks of the MBO pour solver on synthetic cases (venv Python).

    python synth.py [OUT_JSON]

Cases (grid units = cells):
  bubble2   double bubble (2 phases + exterior), areas pi*60^2 and pi*45^2
  bubble3   standard planar triple bubble, three equal areas
  corner    one phase of area A in the corner of a rectangle with free edges
  disc3     three phases filling a disc (areas 1/2, 3/10, 1/5)
  wulff     a single phase in open space, isotropic vs octagon kernel
  bubble2o  double bubble with the octagon kernel
Measured: 120 degree junction angles, 90 degree contact with the free edge, circle-fit
radius and residual of every arc, curvature additivity k12 + k23 + k31 = 0, Laplace law
dlam = sigma_K * kappa with sigma_K = s / sqrt(2 pi) for the Gaussian kernel, and facet
normals / side lengths of the Wulff shape.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geom  # noqa: E402
from mbo import MBO, schedule  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "fig")
S_FINAL = 5.0
SCHED = schedule(14, S_FINAL, 25, 80)
SIG_ISO = S_FINAL / np.sqrt(2 * np.pi)


def arcs_and_junctions(lab, pairs, lam=None, sig=SIG_ISO, excl=8):
    """Fit every p|q interface by a circle (excluding points near junctions), report
    radius, rms, signed curvature (positive when bulging into q), and junction angles."""
    J = geom.junctions(lab)
    Jxy = np.array([[j[0], j[1]] for j in J]) if J else np.zeros((0, 2))
    arcs = {}
    for p, q in pairs:
        pts = geom.interface_points(lab, p, q)
        if len(Jxy):
            d = np.min(np.linalg.norm(pts[:, None, :] - Jxy[None], axis=2), axis=1)
            pts = pts[d > excl]
        if len(pts) < 10:
            continue
        cx, cy, r, rms = geom.fit_circle(pts)
        # sign: centre inside p -> p is convex toward q -> curvature from p into q positive
        ci = (int(round(cy)), int(round(cx)))
        inside = 0 <= ci[0] < lab.shape[0] and 0 <= ci[1] < lab.shape[1]
        # decide by which side of the arc the centre is: sample along normal at midpoint
        mid = pts[len(pts) // 2]
        nvec = np.array([cx, cy]) - mid
        nvec /= np.linalg.norm(nvec)
        probe = np.round(mid + 4 * nvec).astype(int)
        side = lab[np.clip(probe[1], 0, lab.shape[0] - 1), np.clip(probe[0], 0, lab.shape[1] - 1)]
        sgn = 1.0 if side == p else -1.0
        kap = sgn / r if r < 1e4 else 0.0
        a = dict(r=r, rms=rms, kappa=kap, n=len(pts), centre=[cx, cy], pts=pts)
        if lam is not None:
            a["kappa_from_lam"] = (lam[p] - lam[q]) / sig
        arcs[(p, q)] = a
    jout = []
    for (x, y, ph) in J:
        sel = [a for (p, q), a in arcs.items() if p in ph and q in ph]
        if len(sel) != 3:
            continue
        # refine the junction: the point closest (least squares) to the three fitted arcs
        from scipy.optimize import least_squares as lsq

        def res(v):
            return [np.hypot(v[0] - a["centre"][0], v[1] - a["centre"][1]) - a["r"] for a in sel]
        Jr = lsq(res, [x, y]).x
        ts = [geom.tangent_at(Jr, a["pts"], (*a["centre"], a["r"])) for a in sel]
        jout.append(dict(xy=[float(Jr[0]), float(Jr[1])], pixel_xy=[x, y], phases=sorted(ph),
                         angles=geom.angles_between(ts).tolist()))
    return arcs, jout


def run(alive, P, lab0, target, kernel="iso", sched=SCHED, sigma=None):
    m = MBO(alive, P, kernel=kernel, target=target, sigma=sigma)
    lab = m.run(lab0, sched)
    return lab, m.lam


def show(ax, lab, title):
    ax.imshow(np.ma.masked_less(lab, 0), cmap="Set2", interpolation="nearest")
    ax.set_title(title, fontsize=9)
    ax.set_xticks([])
    ax.set_yticks([])


def summarize_arcs(arcs):
    return {f"{p}|{q}": dict(r=round(a["r"], 2), rms=round(a["rms"], 3),
                             kappa=round(a["kappa"], 5),
                             kappa_from_lam=round(a.get("kappa_from_lam", np.nan), 5))
            for (p, q), a in arcs.items()}


def case_bubble2(kernel="iso"):
    H = W = 340
    alive = np.ones((H, W), bool)
    lab = np.full((H, W), 2)
    lab[110:230, 80:175] = 0
    lab[120:220, 175:250] = 1
    A = [np.pi * 60 ** 2, np.pi * 45 ** 2]
    lab, lam = run(alive, 3, lab, [A[0], A[1], np.nan], kernel)
    arcs, J = arcs_and_junctions(lab, [(0, 2), (1, 2), (1, 0)], lam)
    k = {pq: a["kappa"] for pq, a in arcs.items()}
    add = k.get((0, 2), 0) - k.get((1, 2), 0) + k.get((1, 0), 0)  # k02 - k12 + k10 = 0
    # theory: standard double bubble with those areas (solve for radii)
    th = double_bubble_theory(A[0], A[1])
    return lab, dict(arcs=summarize_arcs(arcs), junctions=J, additivity=add, lam=lam.tolist(),
                     theory=th, areas=np.bincount(lab[lab >= 0].ravel()).tolist())


def double_bubble_theory(A1, A2):
    """Standard planar double bubble (A1 >= A2): junctions at (0, +-h); the three arcs
    make tangent-chord angles th1 = 120 + t, th2 = 120 - t, th0 = t (degrees) so the
    tangents meet at 120 deg; h = r_i sin(th_i) gives 1/r0 = 1/r2 - 1/r1."""
    from scipy.optimize import brentq

    def seg(r, th):
        return 0.5 * r * r * (2 * th - np.sin(2 * th))

    def areas_t(t):
        th1, th2, th0 = np.radians(120 + t), np.radians(120 - t), np.radians(t)
        r1, r2 = 1 / np.sin(th1), 1 / np.sin(th2)
        r0 = 1 / np.sin(th0) if t > 1e-9 else np.inf
        m0 = 0.0 if r0 == np.inf else seg(r0, th0)
        return seg(r1, th1) - m0, seg(r2, th2) + m0, r1, r2, r0

    t = brentq(lambda t: areas_t(t)[0] / areas_t(t)[1] - A1 / A2, 1e-9, 59.9) if A1 > A2 else 0.0
    a1, a2, r1, r2, r0 = areas_t(t)
    sc = np.sqrt(A1 / a1)
    return dict(r1=r1 * sc, r2=r2 * sc, r0=r0 * sc, t_deg=t,
                kappa02=1 / (r1 * sc), kappa12=1 / (r2 * sc), kappa10=1 / (r0 * sc))


def case_bubble3():
    H = W = 360
    alive = np.ones((H, W), bool)
    lab = np.full((H, W), 3)
    yy, xx = np.mgrid[:H, :W]
    ang = np.mod(np.arctan2(yy - 180, xx - 180), 2 * np.pi)
    rr = np.hypot(yy - 180, xx - 180)
    for k in range(3):
        lab[(rr < 85) & (ang >= k * 2 * np.pi / 3) & (ang < (k + 1) * 2 * np.pi / 3)] = k
    A = np.pi * 50 ** 2
    lab, lam = run(alive, 4, lab, [A, A, A, np.nan])
    pairs = [(0, 3), (1, 3), (2, 3), (0, 1), (1, 2), (2, 0)]
    arcs, J = arcs_and_junctions(lab, pairs, lam)
    return lab, dict(arcs=summarize_arcs(arcs), junctions=J, lam=lam.tolist())


def case_corner():
    """Quarter disc: radius R = sqrt(4A/pi) about the corner, 90 deg at both walls."""
    H, W, pad = 240, 300, 10
    alive = np.zeros((H + 2 * pad, W + 2 * pad), bool)
    alive[pad:-pad, pad:-pad] = True
    lab = np.full(alive.shape, 1)
    lab[pad:pad + 80, pad:pad + 80] = 0
    R = 90.0
    A = np.pi * R ** 2 / 4
    lab, lam = run(alive, 2, lab, [A, np.nan])
    wall = pad - 0.5
    pts = geom.interface_points(lab, 0, 1, purity=0.0)
    pts = pts[(pts[:, 0] > wall) & (pts[:, 1] > wall) & (pts[:, 0] < wall + 1.5 * R)
              & (pts[:, 1] < wall + 1.5 * R)]
    rr = np.linalg.norm(pts - wall, axis=1)
    out = []
    for ax in (0, 1):  # local line fit 3..20 cells from the wall x = wall (ax 0) / y = wall
        sel = (pts[:, ax] - wall > 3) & (pts[:, ax] - wall < 20)
        _, dvec, _ = geom.fit_line(pts[sel])
        wall_dir = np.array([0.0, 1.0]) if ax == 0 else np.array([1.0, 0.0])
        out.append(float(np.degrees(np.arccos(min(1, abs(np.dot(dvec, wall_dir)))))))
    mid = pts[(rr > 0) & (np.abs(np.degrees(np.arctan2(pts[:, 1] - wall, pts[:, 0] - wall)) - 45) < 30)]
    cx, cy, r, rms = geom.fit_circle(mid)
    return lab, dict(R_theory=R, r_mean=float(rr.mean()), r_min=float(rr.min()),
                     r_max=float(rr.max()), contact_angles=out,
                     kappa_mid_fit=1 / r, kappa_theory=1 / R,
                     kappa_from_lam=(lam[0] - lam[1]) / SIG_ISO, lam=lam.tolist())


def case_disc3():
    N = 340
    yy, xx = np.mgrid[:N, :N]
    R = 150
    rr = np.hypot(yy - N / 2, xx - N / 2)
    alive = rr < R
    ang = np.mod(np.arctan2(yy - N / 2, xx - N / 2), 2 * np.pi)
    fr = [0.5, 0.3, 0.2]
    cut = np.cumsum([0] + fr) * 2 * np.pi
    lab = np.zeros((N, N), int)
    for k in range(3):
        lab[(ang >= cut[k]) & (ang < cut[k + 1])] = k
    lab[~alive] = -1
    tot = alive.sum()
    lab, lam = run(alive, 3, lab, [fr[0] * tot, fr[1] * tot, np.nan])
    arcs, J = arcs_and_junctions(lab, [(0, 1), (1, 2), (2, 0)], lam)
    k = {pq: a["kappa"] for pq, a in arcs.items()}
    add = sum(k.values())
    # contact with the circle: angle between arc tangent and the disc boundary at the
    # meeting point (nearest point of the arc to the circle)
    contact = {}
    c0 = np.array([N / 2 - 0.5, N / 2 - 0.5])
    for (p, q) in [(0, 1), (1, 2), (2, 0)]:  # local line fit 3..20 cells from the rim
        pts = geom.interface_points(lab, p, q, purity=0.0)
        dist = R - np.linalg.norm(pts - c0, axis=1)
        sel = (dist > 3) & (dist < 20)
        if sel.sum() < 5:
            continue
        P0, dvec, _ = geom.fit_line(pts[sel])
        radial = (P0 - c0) / np.linalg.norm(P0 - c0)
        contact[f"{p}|{q}"] = float(np.degrees(np.arccos(min(1, abs(np.dot(dvec, radial))))))
    return lab, dict(arcs=summarize_arcs(arcs), junctions=J, additivity=add,
                     contact_angle_to_normal=contact, lam=lam.tolist())


def case_wulff(kernel, init="disc"):
    H = W = 300
    alive = np.ones((H, W), bool)
    yy, xx = np.mgrid[:H, :W]
    A = 140 * 140
    if init == "disc":
        lab = np.where(np.hypot(yy - 150, xx - 150) < np.sqrt(A / np.pi), 0, 1)
    else:
        lab = np.where((np.abs(yy - 150) < 70) & (np.abs(xx - 150) < 70), 0, 1)
    sf = 8.0 if kernel == "oct" else S_FINAL
    lab, lam = run(alive, 2, lab, [A, np.nan], kernel, sched=schedule(3 * sf, sf, 30, 100))
    ang, L = geom.boundary_normals(lab, 0)
    hist, edges = np.histogram(np.mod(ang, 180), bins=36, range=(0, 180), weights=L)
    near = np.minimum.reduce([np.abs(((ang - a + 90) % 180) - 90) for a in (0, 45, 90, 135)])
    frac_facet = float(L[near < 5].sum() / L.sum())
    per = geom.perimeter(lab, 0)
    # radial profile: support-function extents along 0/45/90/135 and 22.5 deg
    ys, xs = np.nonzero(lab == 0)
    cxy = np.array([xs.mean(), ys.mean()])
    ext = {}
    for a in (0, 22.5, 45, 67.5, 90, 112.5, 135, 157.5):
        d = np.array([np.cos(np.radians(a)), np.sin(np.radians(a))])
        proj = (np.c_[xs, ys] - cxy) @ d
        ext[a] = float(0.5 * (proj.max() - proj.min()))
    iso_q = per ** 2 / (4 * np.pi * A)
    apothem = np.sqrt(A / (8 * np.tan(np.pi / 8)))
    return lab, dict(init=init, octagon_apothem_theory=apothem,
                     octagon_circumradius_theory=apothem / np.cos(np.pi / 8),frac_len_within5deg_of_facets=frac_facet, perimeter=per,
                     perim_over_circle=per / (2 * np.sqrt(np.pi * A)),
                     regular_octagon_ratio=float(np.sqrt(8 * np.tan(np.pi / 8) / np.pi)),
                     half_width=ext, normal_hist=hist.tolist(), iso_quotient=iso_q)


def main(out=None):
    res = {}
    fig, axs = plt.subplots(2, 4, figsize=(14, 7))
    cases = [("bubble2", lambda: case_bubble2("iso")), ("bubble3", case_bubble3),
             ("corner", case_corner), ("disc3", case_disc3),
             ("wulff_iso", lambda: case_wulff("iso")), ("wulff_oct", lambda: case_wulff("oct")),
             ("wulff_oct_sqinit", lambda: case_wulff("oct", "square")),
             ("bubble2_oct", lambda: case_bubble2("oct"))]
    for ax, (name, fn) in zip(axs.ravel(), cases):
        lab, r = fn()
        res[name] = r
        show(ax, lab, name)
        print(name, json.dumps(r, default=float)[:1500], flush=True)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "synth.png"), dpi=110)
    with open(out or os.path.join(HERE, "synth_results.json"), "w") as f:
        json.dump(res, f, indent=1, default=float)


if __name__ == "__main__" and "--conv" not in sys.argv:
    main(sys.argv[1] if len(sys.argv) > 1 else None)


def convergence(fs=(1, 2, 3)):
    """Double bubble at grid refinement f (radii * f, kernel s = 5 sqrt(f) cells, so
    s/R -> 0 and s/cell -> inf): junction angles and radii vs theory."""
    out = []
    for f in fs:
        H = W = int(340 * f)
        alive = np.ones((H, W), bool)
        lab = np.full((H, W), 2)
        lab[int(110 * f):int(230 * f), int(80 * f):int(175 * f)] = 0
        lab[int(120 * f):int(220 * f), int(175 * f):int(250 * f)] = 1
        A = [np.pi * (60 * f) ** 2, np.pi * (45 * f) ** 2]
        s = S_FINAL * np.sqrt(f)
        lab, lam = run(alive, 3, lab, [A[0], A[1], np.nan], sched=schedule(14 * np.sqrt(f), s, 25, 80))
        arcs, J = arcs_and_junctions(lab, [(0, 2), (1, 2), (1, 0)], lam,
                                     sig=s / np.sqrt(2 * np.pi), excl=8 * np.sqrt(f))
        th = double_bubble_theory(*A)
        ys = sorted(j["xy"][1] for j in J)
        row = dict(f=f, s=s, angles=[j["angles"] for j in J],
                   max_angle_err=max(abs(a - 120) for j in J for a in j["angles"]),
                   r=[arcs[k]["r"] / f for k in [(0, 2), (1, 2), (1, 0)]],
                   r_theory=[th["r1"] / f, th["r2"] / f, th["r0"] / f],
                   half_chord=(ys[-1] - ys[0]) / 2 / f if len(ys) == 2 else None,
                   half_chord_theory=th["r1"] * np.sin(np.radians(120 + th["t_deg"])) / f)
        print("conv", json.dumps(row, default=float), flush=True)
        out.append(row)
    return out


if __name__ == "__main__" and "--conv" in sys.argv:
    json.dump(convergence(), open(os.path.join(HERE, "synth_convergence.json"), "w"),
              indent=1, default=float)
