# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decision quality of physics proxies: why choosing needs less than knowing (lens IN).

Round 1 found, by computation, that the microsecond proxy MS2 picks the PEEC-best of 10
hot-loop candidates 96-98 % of the time while plan-view loop area picks it 16-66 %, and
that "ranking matters more than accuracy". This script tests the information-theoretic
explanation on the same data (sl_loop_peec.py families and seeds, reused unchanged):

  A. Error split.  A proxy's log error e = log(proxy) - log(PEECN) is a common bias b
     (cancels in every comparison) plus a dispersion u.  Hypothesis: pick-best accuracy
     depends on sigma_u / s (s = spread of the true log L among candidates), measured
     where the decision is made.  Checked by re-drawing iid Gaussian errors around the
     true values (bias ignored) with sigma_u from (i) all loops, (ii) the contenders
     (best 20 % of true L), against the proxy's observed decisions on identical
     candidate sets.  Structured error is diagnosed by corr(e, true log L) and by
     corr(e, ln w/h), the variable plan-view area omits.
  B. Bias invariance.  A common +50 % bias changes no decision; idiosyncratic noise of
     the same size does.
  C. Optimizer's curse / Goodhart.  As selection strengthens (best of 10, 100, all 600)
     the proxy-selected loop's error drifts from the proxy's median error and the true
     regret of a misaligned proxy (area) grows; compared with the iid-noise curse
     e_k sigma_u^2 / sqrt(sigma_u^2 + s^2) (e_k = expected max of k standard normals).
  D. Sloppiness / active subspace.  Gradient covariance of log L (PEECN) with respect to
     log(a, b, w, h) of rectangular loops, over a plane and in free space: how many
     directions matter, and how well area and MS2 gradients align with the truth.
  E. Resolution.  Candidate sets drawn ever closer to an incumbent (scale delta): a
     smooth proxy (MS2) keeps its decision quality; a proxy with a nugget (MS2 on
     geometry snapped to a 0.5 mm routing grid) falls to chance once delta is below
     the grid.  Plus the routed-J nugget implied by round 1's joint P&R proxy study.
  F. Escalation threshold z from a cost ratio, z = Phi^-1(1 - c/L).
  G. Rule-reliability priors by origin (Jeffreys Beta posteriors from the genealogy
     counts in docs/topics/physics/rule-basis-set.md).

Run:  python tools/research/physics/in_decision_quality.py      (~1 min, numpy + scipy)
"""

import math
import os
import sys

import numpy as np
from scipy.stats import beta, norm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sl_loop_peec as sl  # noqa: E402  (round-1 PEEC and proxies, reused unchanged)

PROX = ("AREA", "PP", "MS", "MS2", "PEEC1")


def e_max_normal(k, n=400000, seed=0):
    """Expected maximum of k independent standard normals (Monte Carlo)."""
    rng = np.random.default_rng(seed)
    return float(rng.standard_normal((n // k + 1, k)).max(axis=1).mean())


def log_estimates(res):
    """Proxy values for decisions (raw, as sl_loop_peec.decision uses them) and log estimates
    for error statistics. AREA is mapped to henries by a log-log fit (rank-preserving).
    PEEC1 goes negative for w/h >= 3 (one filament per wide trace); those loops get NaN logs."""
    y = np.log([r["PEECN"] for r in res])
    raw, est = {}, {}
    for p in PROX:
        v = np.array([r[p] for r in res], dtype=float)
        raw[p] = v
        lv = np.full(len(v), np.nan)
        ok = v > 0
        lv[ok] = np.log(v[ok])
        if p == "AREA":
            A = np.c_[np.ones(ok.sum()), lv[ok]]
            coef, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
            lv[ok] = A @ coef
        est[p] = lv
    return y, raw, est


def pct(log_ratio):
    """A log error expressed as a percentage: (exp(x) - 1) * 100."""
    return (math.exp(log_ratio) - 1) * 100


def robust_sd(x):
    x = x[np.isfinite(x)]
    return 1.4826 * float(np.median(np.abs(x - np.median(x))))


def decide(y, yhat, trials, k=10, seed=1):
    """Best-of-k decisions on the same candidate sets as sl_loop_peec.decision (seed 1)."""
    rng = np.random.default_rng(seed)
    hit, reg, sel = 0, [], []
    for _ in range(trials):
        idx = rng.choice(len(y), k, replace=False)
        pick = idx[np.argmin(yhat[idx])]
        best = idx[np.argmin(y[idx])]
        hit += pick == best
        reg.append(math.exp(y[pick] - y[best]) - 1)
        sel.append(pick)
    return hit / trials, np.array(reg), np.array(sel)


def gaussian_prediction(y, sigma, trials, k=10, reps=20, seed=1):
    """Same candidate sets, errors replaced by iid N(0, sigma^2): depends on sigma/s only."""
    rng_n = np.random.default_rng(99)
    hits, regs = [], []
    for _ in range(reps):
        yhat = y + rng_n.normal(0, sigma, len(y))
        h, r, _ = decide(y, yhat, trials, k, seed)
        hits.append(h)
        regs.append(np.median(r))
    return float(np.mean(hits)), float(np.mean(regs))


def part_a_b_c(label, res, trials=2000, k=10, contender_q=0.2):
    y, raw, est = log_estimates(res)
    s = float(np.std(y))
    cont = y <= np.quantile(y, contender_q)
    wh = np.array([r["w_over_h"] for r in res])
    print(f"\n== A/B {label}: {len(y)} loops, spread of true log L s = {s:.3f} "
          f"(x{math.exp(s):.2f} per sd); best of {k}, {trials} trials; contenders = best "
          f"{contender_q*100:.0f}% of true L (median w/h {np.median(wh[cont]):.1f} vs {np.median(wh):.1f} overall)")
    print(f"{'proxy':6s} {'bias':>7s} {'sd_all':>6s} {'sd_cont':>7s} {'corr(e,y)':>9s} {'corr(e,ln w/h)':>14s}"
          f" | {'observed':>8s} {'iid sd_all':>10s} {'iid sd_cont':>11s} | {'med regret':>10s}")
    out = {}
    for p in PROX:
        e = est[p] - y
        ok = np.isfinite(e)
        b, sa, sc = float(np.median(e[ok])), robust_sd(e), robust_sd(e[cont])
        cyc = np.corrcoef(e[ok & cont], y[ok & cont])[0, 1]
        cwh = np.corrcoef(e[ok], np.log(wh[ok]))[0, 1]
        hit, reg, _ = decide(y, raw[p], trials, k)
        pa, _ = gaussian_prediction(y, sa, trials, k)
        pc, _ = gaussian_prediction(y, sc, trials, k)
        out[p] = (hit, pa, pc)
        btxt = "(fit)" if p == "AREA" else f"{pct(b):+.1f}%"
        note = f"  [{(~ok).sum()} loops <= 0 nH]" if (~ok).any() else ""
        print(f"{p:6s} {btxt:>7s} {sa:6.3f} {sc:7.3f} {cyc:9.2f} {cwh:14.2f} | {hit*100:7.1f}%"
              f" {pa*100:9.1f}% {pc*100:10.1f}% | {np.median(reg)*100:9.1f}%{note}")
    # B. bias invariance and idiosyncratic noise of the same size
    rng = np.random.default_rng(5)
    h_bias, _, _ = decide(y, raw["MS2"] * 1.5, trials, k)
    h_noise, reg_n, _ = decide(y, raw["MS2"] * np.exp(rng.normal(0, math.log(1.5), len(y))), trials, k)
    print(f"  B: MS2 x1.5 (common bias): picks {h_bias*100:.1f}%;  MS2 x exp(N(0, ln 1.5)) per loop: "
          f"picks {h_noise*100:.1f}%, median regret {np.median(reg_n)*100:.1f}%")
    return y, raw, est


def part_c(y, raw, est, trials=600):
    """Selection strength: error of the proxy-selected candidate vs the proxy's median error."""
    print("\n== C. Optimizer's curse / Goodhart: error of the proxy-selected loop relative to the proxy's"
          " median error (as %), and true regret, as selection strengthens (mixed family)")
    s = float(np.std(y))
    print(f"  {'proxy':6s} " + " ".join(f"{'k='+str(k):>22s}" for k in (10, 100, 600)))
    for p in ("AREA", "PP", "MS2"):
        e = est[p] - y
        b = float(np.median(e[np.isfinite(e)]))
        cells = []
        for k in (10, 100, 600):
            tr = 1 if k >= len(y) else trials
            _, reg, sel = decide(y, raw[p], tr, k, seed=4)
            cells.append(f"{pct(np.mean(e[sel]) - b):+6.1f}% / {np.median(reg)*100:5.1f}%")
        print(f"  {p:6s} " + " ".join(f"{c:>22s}" for c in cells))
    su = robust_sd(est["MS2"] - y)
    for k in (10, 100, 600):
        print(f"  iid-noise prediction for MS2 (sd {su:.3f}), k={k}: "
              f"{pct(-e_max_normal(k) * su**2 / math.sqrt(su**2 + s**2)):+.2f}%")


def rect_grad(a, b, w, h, plane, fn, d=0.02):
    """Central-difference gradient of log fn wrt log(a, b, w, h)."""
    x0 = np.log([a, b, w, h])
    g = np.zeros(4)
    for i in range(4):
        xp, xm = x0.copy(), x0.copy()
        xp[i] += d
        xm[i] -= d
        fp = fn(*np.exp(xp), plane)
        fm = fn(*np.exp(xm), plane)
        g[i] = (math.log(fp) - math.log(fm)) / (2 * d)
    return g


def peecn_rect(a, b, w, h, plane):
    return sl.loop_l_peec(sl.rect(a, b), [w] * 4, h, nf=7, plane=plane)


def ms2_rect(a, b, w, h, plane):
    return sl.proxies(sl.rect(a, b), [w] * 4, h)["MS2"]


def part_d(n=300):
    print(f"\n== D. Active subspace of log L (PEECN), rectangles, {n} samples, "
          "variables log(a, b, w, h): a, b 1.5-20 mm, w 0.15-4 mm, h 0.08-1.6 mm")
    rng = np.random.default_rng(21)
    samples = []
    while len(samples) < n:
        a, b = np.exp(rng.uniform(np.log(1.5e-3), np.log(20e-3), 2))
        w = math.exp(rng.uniform(math.log(0.15e-3), math.log(4e-3)))
        h = math.exp(rng.uniform(math.log(0.08e-3), math.log(1.6e-3)))
        if min(a, b) >= 3 * w:
            samples.append((a, b, w, h))
    area_dir = np.array([1, 1, 0, 0]) / math.sqrt(2)
    hsq_dir = np.array([0.5, 0.5, -1, 1]) / math.sqrt(2.5)   # perimeter x h / w
    for plane in (True, False):
        G = np.array([rect_grad(*s, plane, peecn_rect) for s in samples])
        C = G.T @ G / len(G)
        lam, V = np.linalg.eigh(C)
        lam, V = lam[::-1], V[:, ::-1]
        v1 = V[:, 0] * np.sign(V[0, 0])
        cos_area = np.abs(G @ area_dir) / np.linalg.norm(G, axis=1)
        cos_hsq = np.abs(G @ hsq_dir) / np.linalg.norm(G, axis=1)
        line = (f"  {'plane' if plane else 'free space':10s} eigenvalues (share) "
                + " ".join(f"{l/lam.sum():.3f}" for l in lam)
                + f"; v1 = (a {v1[0]:+.2f}, b {v1[1]:+.2f}, w {v1[2]:+.2f}, h {v1[3]:+.2f})")
        print(line)
        print(f"  {'':10s} |cos(grad, area direction)| median {np.median(cos_area):.2f} (p10 {np.percentile(cos_area,10):.2f});"
              f" |cos(grad, perimeter x h/w)| median {np.median(cos_hsq):.2f}"
              f"; cos(v1, area) {abs(v1 @ area_dir):.2f}, cos(v1, perim x h/w) {abs(v1 @ hsq_dir):.2f}")
        if plane:
            Gm = np.array([rect_grad(*s, plane, ms2_rect) for s in samples])
            cos_ms2 = np.sum(G * Gm, axis=1) / np.linalg.norm(G, axis=1) / np.linalg.norm(Gm, axis=1)
            print(f"  {'':10s} cos(grad PEECN, grad MS2) median {np.median(cos_ms2):.3f} (p10 {np.percentile(cos_ms2,10):.3f})")


def snap(x, q):
    return np.maximum(q, np.round(x / q) * q)


def part_e(trials=250, k=10):
    print(f"\n== E. Resolution: best of {k} candidates around an incumbent, log-normal scale delta")
    print("   incumbent: rectangle 12 x 6 mm, w 0.5 mm, h 0.2 mm; candidates vary a, b, w; h fixed")
    rng = np.random.default_rng(3)
    a0, b0, w0, h0 = 12e-3, 6e-3, 0.5e-3, 0.2e-3
    print(f"  {'delta':>6s} {'true spread':>11s} | {'MS2':>6s} {'AREA':>6s} {'MS2 on 0.5 mm grid':>19s} | chance {100/k:.0f}%")
    for delta in (0.3, 0.1, 0.03, 0.01):
        hits = {"MS2": 0, "AREA": 0, "GRID": 0}
        spreads = []
        for _ in range(trials):
            f = np.exp(rng.normal(0, delta, (k, 3)))
            a, b, w = a0 * f[:, 0], b0 * f[:, 1], w0 * f[:, 2]
            y = np.array([peecn_rect(a[i], b[i], w[i], h0, True) for i in range(k)])
            ms2 = np.array([ms2_rect(a[i], b[i], w[i], h0, True) for i in range(k)])
            area = a * b
            ag, bg = snap(a, 0.5e-3), snap(b, 0.5e-3)
            grid = np.array([ms2_rect(ag[i], bg[i], w[i], h0, True) for i in range(k)])
            best = np.argmin(y)
            spreads.append(np.std(np.log(y)))
            for name, v in (("MS2", ms2), ("AREA", area), ("GRID", grid)):
                # ties on the grid are broken at random, as a grid-based optimizer would
                cand = np.flatnonzero(v == v.min())
                hits[name] += rng.choice(cand) == best
        print(f"  {delta:6.2f} {np.median(spreads)*100:10.2f}% | {hits['MS2']/trials*100:5.1f}% "
              f"{hits['AREA']/trials*100:5.1f}% {hits['GRID']/trials*100:18.1f}%")
    # Routed-J nugget implied by round 1 (joint-place-route-experiment.md, proxy study):
    # 58 of 131 placement pairs within 3 % HPWL differed by more than 10 % in routed J.
    lo, hi = beta.ppf([0.025, 0.975], 58 + 0.5, 131 - 58 + 0.5)
    sd = lambda p: 0.10 / norm.ppf(1 - p / 2)
    print(f"  routed-J nugget from round 1: P(|dJ| > 10%) = 58/131 = {58/131:.2f} (95% CI {lo:.2f}-{hi:.2f})"
          f" -> sd of a pairwise dJ at equal HPWL {sd(58/131)*100:.0f}% ({sd(hi)*100:.0f}-{sd(lo)*100:.0f}%),"
          f" per placement {sd(58/131)/math.sqrt(2)*100:.0f}%")


def part_f():
    print("\n== F. Escalation threshold from a cost ratio: escalate while margin < z*sigma, z = Phi^-1(1 - c/L)")
    for c_over_l in (0.3, 0.16, 0.05, 0.01, 1.35e-3, 1e-4):
        print(f"  c/L = {c_over_l:<8g} -> z = {norm.ppf(1 - c_over_l):.2f}")


def part_g():
    print("\n== G. Rule reliability by origin (counts from rule-basis-set.md), Jeffreys Beta(0.5, 0.5) prior")
    rows = [("physics", 80, 91), ("simplicity proxy", 3, 23), ("manufacturing", 11, 16),
            ("habit / legacy", 0, 15), ("cognition/tool/legal/contested", 8, 15)]
    for name, right, n in rows:
        a, b = right + 0.5, n - right + 0.5
        lo, hi = beta.ppf([0.025, 0.975], a, b)
        print(f"  {name:31s} 'about right' {right:2d}/{n:2d}: mean {a/(a+b):.2f}, 95% CI {lo:.2f}-{hi:.2f}")
    a, b = 10 + 0.5, 5 + 0.5
    print(f"  habit / legacy 'wrong' 10/15: mean {a/(a+b):.2f}, 95% CI "
          f"{beta.ppf(0.025, a, b):.2f}-{beta.ppf(0.975, a, b):.2f}")


def main():
    np.set_printoptions(precision=3, suppress=True)
    rows_mixed = sl.sample_family(np.random.default_rng(7), 600, True)
    res_mixed = sl.evaluate(rows_mixed, True)
    rows_fixed = sl.sample_family(np.random.default_rng(11), 300, True, fixed=(0.5e-3, 0.2e-3))
    res_fixed = sl.evaluate(rows_fixed, True)
    part_a_b_c("fixed stackup (w 0.5 mm, h 0.2 mm)", res_fixed)
    y, raw, est = part_a_b_c("mixed widths and stackups", res_mixed)
    part_c(y, raw, est)
    part_d()
    part_e()
    part_f()
    part_g()


if __name__ == "__main__":
    main()
