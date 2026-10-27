# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Red-team statistics on the round-1 joint-vs-sequential placement/routing result.

Re-analyses the per-board routed objectives J published in
docs/topics/physics/joint-place-route-experiment.md (jpr_joint_vs_sequential.py, 5 seeds per
size). No re-run: the published table is the data. Prints sign tests (exact binomial), a paired
log-ratio bootstrap, and compares the effect with the run-to-run noise the doc reports for one
board and seed (seq J of 241, 290 and 337 across three runs).

Run: python tools/research/physics/rt_jpr_stats.py   (instant)
"""
import math

import numpy as np

# N, seed: seq, seqx, seq_long, seq_port, joint, joint_nophys  (from the published table)
J = {
    (30, 0): (381.5, 1173.5, 379.0, 375.5, 314.5, 335.5),
    (30, 1): (406.5, 819.5, 404.5, 443.5, 334.0, 347.5),
    (30, 2): (369.5, 504.5, 342.5, 369.5, 331.5, 337.0),
    (30, 3): (950.0, 764.3, 1244.5, 528.5, 539.5, 498.9),
    (30, 4): (403.0, 392.5, 398.0, 304.0, 376.0, 420.0),
    (50, 0): (2954.5, 745.0, 1945.5, 900.0, 1264.5, 1478.0),
    (50, 1): (809.2, 947.5, 692.5, 805.0, 719.0, 722.0),
    (50, 2): (904.9, 801.9, 891.0, 899.1, 687.5, 649.2),
    (50, 3): (1113.3, 443.9, 445.5, 460.7, 590.2, 594.5),
    (50, 4): (669.0, 415.0, 536.5, 535.5, 586.0, 558.0),
}
ARMS = ("seq", "seqx", "seq_long", "seq_port", "joint", "joint_nophys")


def binom_two_sided(k, n):
    """Exact two-sided sign-test p-value for k wins of n."""
    p = sum(math.comb(n, i) for i in range(n + 1) if abs(i - n / 2) >= abs(k - n / 2)) / 2 ** n
    return min(1.0, p)


def boot_ci(x, rng, b=20000):
    m = np.array([np.median(rng.choice(x, len(x), replace=True)) for _ in range(b)])
    return np.percentile(m, 2.5), np.percentile(m, 97.5)


def compare(a, b, sizes=(30, 50)):
    rng = np.random.default_rng(1)
    ia, ib = ARMS.index(a), ARMS.index(b)
    out = []
    for n in sizes + ((30, 50),):
        keys = [k for k in J if (k[0] in n if isinstance(n, tuple) else k[0] == n)]
        r = np.array([math.log(J[k][ia] / J[k][ib]) for k in keys])
        wins = int(np.sum(r < 0))
        lo, hi = boot_ci(r, rng)
        out.append((n, len(r), wins, binom_two_sided(wins, len(r)), np.median(r), lo, hi))
    return out


def main():
    print("== joint vs controls: wins (lower J), exact two-sided sign test, median log-ratio with bootstrap 95% CI")
    for ctrl in ("seq_long", "seq_port", "seq", "seqx", "joint_nophys"):
        for n, m, w, p, med, lo, hi in compare("joint", ctrl):
            lab = "all" if isinstance(n, tuple) else f"N={n}"
            print(f"   joint vs {ctrl:12s} {lab:5s}: {w}/{m} wins, p = {p:.3f}; median ratio {math.exp(med):.3f}"
                  f" (95% CI {math.exp(lo):.3f}-{math.exp(hi):.3f})")
    print("\n== run-to-run noise on one board and seed (doc: seq J = 241, 290, 337 across three runs)")
    x = np.array([241.0, 290.0, 337.0])
    sd_log = np.std(np.log(x), ddof=1)
    print(f"   sd of log J = {sd_log:.3f} (x{math.exp(sd_log):.2f}); a single paired log-ratio then has sd ~"
          f" {math.sqrt(2)*sd_log:.3f} (x{math.exp(math.sqrt(2)*sd_log):.2f})")
    print("   joint's median effect vs seq_long at N=30 is x0.83 (-17%): about 0.8 sd of one paired comparison")
    print("\n== joint vs its own start (seq): the only 10/10 result")
    for n, m, w, p, med, lo, hi in compare("joint", "seq"):
        lab = "all" if isinstance(n, tuple) else f"N={n}"
        print(f"   {lab:5s}: {w}/{m}, p = {p:.3f}, median ratio {math.exp(med):.3f}")


if __name__ == "__main__":
    main()
