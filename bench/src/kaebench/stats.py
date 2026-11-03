# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Paired statistics for A/B comparisons of two methods on the same boards (stdlib only).

The board is the unit, paired across methods (docs/topics/verification/dev-eval-plan.md,
"Evaluation protocol"): exact McNemar for a binary outcome (clean or not), a paired sign-flip
permutation test for a fractional one (completion, cp1_mean), a 95 % bootstrap CI of the mean
paired difference resampled by repository (boards of one repository are not independent), and
Holm's correction when several secondaries are tested. Every function is deterministic: the
random ones take a seed.

kaeres (tools/kaeres) imports this file by path, so it must stay stdlib-only.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict


def mcnemar_exact(b, c):
    """Two-sided exact McNemar p-value from the discordant counts: b boards only A got right,
    c boards only B got right (binomial test of b against n = b + c at p = 0.5)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def sign_flip(diffs, n_perm=20000, seed=0):
    """Two-sided paired sign-flip permutation p-value for H0: mean difference 0. Exact over all
    2^m sign patterns of the m non-zero differences when m <= 16, else Monte Carlo with `seed`
    (p = (hits + 1) / (n_perm + 1), never 0)."""
    d = [x for x in diffs if x]
    m = len(d)
    if m == 0:
        return 1.0
    obs = abs(sum(d)) - 1e-12
    if m <= 16:
        hits = 0
        for mask in range(1 << m):
            s = sum(-x if mask >> i & 1 else x for i, x in enumerate(d))
            hits += abs(s) >= obs
        return hits / (1 << m)
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_perm):
        s = sum(x if rng.random() < 0.5 else -x for x in d)
        hits += abs(s) >= obs
    return (hits + 1) / (n_perm + 1)


def bootstrap_ci(diffs, clusters=None, n_boot=5000, seed=0, alpha=0.05):
    """(low, high) percentile CI of the mean of `diffs`, resampling whole clusters (e.g. the
    repository of each board) with replacement; each board its own cluster when None."""
    if not diffs:
        return (None, None)
    groups = defaultdict(list)
    for i, x in enumerate(diffs):
        groups[clusters[i] if clusters else i].append(x)
    sums = [(sum(v), len(v)) for v in groups.values()]
    rng = random.Random(seed)
    g = len(sums)
    means = []
    for _ in range(n_boot):
        s = n = 0
        for _ in range(g):
            a, b = sums[rng.randrange(g)]
            s += a
            n += b
        means.append(s / n)
    means.sort()
    lo = means[int(alpha / 2 * (n_boot - 1))]
    hi = means[int((1 - alpha / 2) * (n_boot - 1))]
    return (round(lo, 4), round(hi, 4))


def holm(pvals):
    """Holm-Bonferroni adjusted p-values, in the input order."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj, run = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * pvals[i]))
        adj[i] = run
    return adj


def cp_at_k(n, c, k):
    """Unbiased estimate of P(at least one of k attempts is clean) from n attempts with c clean
    (the pass@k estimator, 1 - C(n-c, k) / C(n, k)); None when k > n."""
    if k > n:
        return None
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def paired(a, b, boards=None, missing=0.0, clusters=None, binary=False, seed=0):
    """Compare per-board values of arm A and arm B.

    a, b: {board: value} (bool or number; None = no value). `boards`: the boards both arms were
    asked to do; a board in it that an arm lacks counts as `missing` (a failure, 0), so an arm
    that skips hard boards does not look better. Without `boards`, only boards both arms have
    are compared. `clusters`: {board: repository} for the bootstrap.

    Returns n, the arms' means, the mean difference B - A with its 95 % CI, the p-value
    (McNemar when `binary`, else sign-flip), and for binary outcomes the flipped boards."""
    if boards is None:
        boards = sorted(k for k in set(a) & set(b) if a[k] is not None and b[k] is not None)
    else:
        boards = sorted(boards)
    va = [float(missing if a.get(k) is None else a[k]) for k in boards]
    vb = [float(missing if b.get(k) is None else b[k]) for k in boards]
    diffs = [y - x for x, y in zip(va, vb)]
    out = dict(n=len(boards), missing_a=sum(1 for k in boards if a.get(k) is None),
               missing_b=sum(1 for k in boards if b.get(k) is None),
               mean_a=round(sum(va) / len(va), 4) if va else None,
               mean_b=round(sum(vb) / len(vb), 4) if vb else None,
               diff=round(sum(diffs) / len(diffs), 4) if diffs else None,
               ci=bootstrap_ci(diffs, [(clusters or {}).get(k, k) for k in boards] if clusters else None, seed=seed))
    if binary:
        gained = [k for k, x, y in zip(boards, va, vb) if y > x]
        lost = [k for k, x, y in zip(boards, va, vb) if y < x]
        out.update(test="mcnemar", p=round(mcnemar_exact(len(lost), len(gained)), 4), gained=gained, lost=lost)
    else:
        out.update(test="sign-flip", p=round(sign_flip(diffs, seed=seed), 4))
    return out


def verdict(r, alpha=0.05, higher_better=True):
    """'B better' / 'B worse' / 'no significant difference' for a paired() result."""
    if r.get("p") is None or r.get("diff") is None:
        return "n/a"
    if r["p"] < alpha:
        return "B better" if (r["diff"] > 0) == higher_better else "B worse"
    return "no significant difference"
