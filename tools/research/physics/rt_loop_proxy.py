# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Red-team check of the round-1 loop-proxy result ('MS2 picks the PEEC-best 96-98%, area 16-66%').

(a) reference  The 'truth' (PEECN in sl_loop_peec.py) splits each trace into 7 equal filaments with
               rectangle-GMD self terms. Its FastHenry check covers w/h = 0.3-5 at 100 MHz, while the
               contenders of the mixed family sit at median w/h ~ 13 (lens IN). Here an independent 2-D
               solve (per unit length, strip over a PEC plane, image method) compares N = 7 equal
               filaments with a converged, edge-graded discretisation and with Hammerstad-Jensen,
               for w/h = 0.5-50.
(b) decisions  Pick-best-of-10 at FIXED stackups (the only realistic decision set: one board, one
               stackup), re-using sl_loop_peec.py's loop families and PEECN unchanged, for several
               (w, h). Compares AREA, PERIM (total trace length, i.e. 'height x squares' at fixed w, h)
               and MS2. If PERIM ~ MS2, a corrected geometric rule does the job without a solver.
(c) redo       Lens IN's parts A and C (in_decision_quality.py, unchanged) on the same 600-loop mixed
               family, with PEECN replaced by a 3-D reference using 61 cosine-graded filaments per
               trace: is MS2's '+64% error on the winner' an MS2 error or a reference error?

Sections: python rt_loop_proxy.py [reference|decisions|redo|all]
Run: OMP_NUM_THREADS=1 python tools/research/physics/rt_loop_proxy.py   (about 30 s)
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sl_loop_peec as sl  # noqa: E402  (round-1 loop families, proxies and PEECN, unchanged)

MU0 = 4e-7 * math.pi


def lprime_filaments(w, h, t, edges):
    """HF L' (H/m) of a strip (sub-strips between `edges`, thickness t) at height h over a PEC plane.

    Minimum magnetic energy split (all sub-strips at one voltage), images at -h; self terms with the
    thin-rectangle GMD 0.2235 (b + t); mutuals with centre distances (exact enough for b << d).
    """
    xc = 0.5 * (edges[1:] + edges[:-1])
    b = np.diff(edges)
    n = len(xc)
    d = np.abs(xc[:, None] - xc[None, :])
    np.fill_diagonal(d, 0.2235 * (b + t))
    di = np.sqrt((xc[:, None] - xc[None, :]) ** 2 + (2 * h) ** 2)
    Lm = MU0 / (2 * math.pi) * np.log(di / d)       # partial self/mutual minus image mutual
    y = np.linalg.solve(Lm, np.ones(n))
    return 1.0 / y.sum()


def sec_reference():
    print("== reference: L' of a strip over a PEC plane; 7 equal filaments (PEECN's choice) vs converged vs Hammerstad")
    h, t = 0.1e-3, 35e-6
    print("   w/h    L'(7 equal)  L'(converged, 400 graded)  L'(HJ air)   7-fil error   HJ vs converged")
    for u in (0.5, 1, 2, 5, 13, 30, 50):
        w = u * h
        l7 = lprime_filaments(w, h, t, np.linspace(-w / 2, w / 2, 8))
        s = np.linspace(-1, 1, 401)
        graded = (w / 2) * np.sin(0.5 * math.pi * s)      # cosine grading: fine at both edges
        lc = lprime_filaments(w, h, t, graded)
        lhj = sl.lprime_ms(w, h)
        print(f"   {u:5.1f}   {l7*1e9:8.4f}        {lc*1e9:8.4f}                 {lhj*1e9:8.4f}     {(l7/lc-1)*100:+6.1f}%"
              f"        {(lhj/lc-1)*100:+6.1f}%   (nH/mm)")


def decision_fixed(w, h, n=300, k=10, trials=2000, seed=11):
    rng = np.random.default_rng(seed)
    rows = sl.sample_family(rng, n, plane=True, fixed=(w, h))
    ref, area, perim, ms2 = [], [], [], []
    for kind, pts, widths, hh in rows:
        p = sl.proxies(pts, widths, hh)
        ref.append(sl.loop_l_peec(pts, widths, hh, nf=7, plane=True))
        area.append(p["AREA"])
        perim.append(float(np.sum(sl.seg_lengths(pts))))
        ms2.append(p["MS2"])
    ref, cols = np.array(ref), {"AREA": np.array(area), "PERIM": np.array(perim), "MS2": np.array(ms2)}
    rr = np.random.default_rng(seed + 1)
    hits = {k_: 0 for k_ in cols}
    regret = {k_: [] for k_ in cols}
    for _ in range(trials):
        idx = rr.choice(n, k, replace=False)
        best = idx[np.argmin(ref[idx])]
        for name, v in cols.items():
            pick = idx[np.argmin(v[idx])]
            hits[name] += pick == best
            regret[name].append(ref[pick] / ref[best] - 1)
    return {k_: (hits[k_] / trials, np.percentile(regret[k_], 95)) for k_ in cols}


def sec_decisions():
    print("== decisions at a fixed stackup: pick-best-of-10 (PEECN truth), loop families of sl_loop_peec.py")
    print("   w (mm)  h (mm)  |  AREA  (p95 regret)  |  PERIM (p95 regret)  |  MS2  (p95 regret)")
    for w, h in ((0.5e-3, 0.2e-3), (2e-3, 0.1e-3), (4e-3, 0.1e-3), (0.3e-3, 1.5e-3), (1e-3, 0.5e-3)):
        r = decision_fixed(w, h)
        print(f"   {w*1e3:5.2f}   {h*1e3:5.2f}   | " + " | ".join(f"{name:5s} {r[name][0]*100:5.1f}% ({r[name][1]*100:5.1f}%)"
                                                            for name in ("AREA", "PERIM", "MS2")))


def filaments_graded(pts, widths, z, t, nf):
    """As sl.filaments_from_loop, but with cosine-graded filaments (fine at the trace edges)."""
    out = []
    n = len(pts)
    s = np.linspace(-1, 1, nf + 1)
    for k in range(n):
        (x0, y0), (x1, y1) = pts[k], pts[(k + 1) % n]
        w = widths[k]
        if abs(y1 - y0) < 1e-15:
            axis, a0, a1, c = 0, x0, x1, y0
        else:
            axis, a0, a1, c = 1, y0, y1, x0
        sign = 1.0 if a1 > a0 else -1.0
        lo, hi = min(a0, a1), max(a0, a1)
        e = (w / 2) * np.sin(0.5 * math.pi * s)
        for o, b in zip(0.5 * (e[1:] + e[:-1]), np.diff(e)):
            out.append((axis, lo, hi, sign, c + o, z, k, 0.2235 * (b + t)))
    return np.array(out, dtype=float)


def loop_l_graded(pts, widths, h, t=35e-6, nf=31):
    F = filaments_graded(pts, widths, h, t, nf)
    L = sl.l_matrix(F, 0.0)
    nseg = len(pts)
    B = np.zeros((len(F), nseg))
    B[np.arange(len(F)), F[:, 6].astype(int)] = 1.0
    K = B.T @ np.linalg.solve(L, B)
    return float(np.linalg.solve(K, np.ones(nseg)).sum())


def sec_redo_in():
    """Lens IN parts A and C on the same 600-loop mixed family, with PEECN replaced by a graded reference."""
    import in_decision_quality as idq  # noqa: E402  (lens IN analysis, unchanged)
    rows = sl.sample_family(np.random.default_rng(7), 600, True)
    res = sl.evaluate(rows, True)
    g = np.array([loop_l_graded(pts, widths, hh, nf=61) for _, pts, widths, hh in rows])
    p7 = np.array([r["PEECN"] for r in res])
    wh = np.array([r["w_over_h"] for r in res])
    print("== redo lens IN with a graded reference (61 cosine-graded filaments per trace); same 600 loops (seed 7)")
    for lo, hi in ((0, 3), (3, 10), (10, 20), (20, 60)):
        m = (wh >= lo) & (wh < hi)
        if m.any():
            print(f"   w/h {lo:2d}-{hi:2d}: n {m.sum():3d}; PEECN(7 equal) / graded median {np.median(p7[m]/g[m]):.3f}"
                  f" (p10 {np.percentile(p7[m]/g[m], 10):.3f}); MS2 / graded median {np.median(np.array([r['MS2'] for r in res])[m]/g[m]):.3f}")
    res_g = [dict(r, PEECN=gv) for r, gv in zip(res, g)]
    y, raw, est = idq.part_a_b_c("mixed family, GRADED reference", res_g)
    idq.part_c(y, raw, est)


if __name__ == "__main__":
    which = sys.argv[1:] or ["all"]
    if "all" in which or "reference" in which:
        sec_reference()
        print()
    if "all" in which or "decisions" in which:
        sec_decisions()
        print()
    if "all" in which or "redo" in which:
        sec_redo_in()
