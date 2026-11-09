# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pair swaps of interchangeable parts on the placer's physics terms, after legal placement (E116).

The annealer already has an equal-footprint swap move, but it runs on a clock and on a congested board: a
placement can end with two identical decaps each serving the other's IC. Stage 1 (E116) found that a greedy
swap search over equal parts improves the placer's own physics term by over 10% on 27 of 138 merit boards,
over 50% on 11, on stored placements. This pass does that search at the end of placement: for each group of
parts with the same footprint shape and value (two-pad parts, same side: geometrically interchangeable, so
grid legality is preserved), try every pair and accept a swap when Terms.delta goes down. Swaps that would not
leave the exact check as clean as it was are rolled back all at once.

What it cannot do: on boards where the routed evaluator drops a shared-rail decap (E7, ownership below
BIND_P), swaps that serve shared rails show up in the placer term but not in the routed physics score;
report the placer term and judge on routed opens and physics together.
"""
from __future__ import annotations

import time
from collections import defaultdict

MIN_GAIN = 1e-6


def groups(P):
    """[[part index]] of movable two-pad parts with equal shape_key and non-empty value, 2 or more."""
    by = defaultdict(list)
    for i in P.mov:
        p = P.parts[i]
        if p.fp.value and len(p.fp.pads) == 2:
            by[(p.shape_key, p.fp.value)].append(i)
    return [g for g in by.values() if len(g) >= 2]


def polish(P, st, terms, time_s, check=None, log=None):
    """Greedy pair swaps, in place on st. `check()`: number of exact violations; if the pass leaves
    more than before, every swap is undone. Returns a report dict."""
    t0 = time.monotonic()
    grp = groups(P)
    rep = dict(groups=len(grp), parts=sum(len(g) for g in grp), tries=0, swaps=0)
    if not grp:
        return rep
    poses = {p.uuid: st.pose(p.i) for p in P.parts}
    start = float(terms.total(poses))
    rep["before"] = round(start, 6)
    hpwl0 = st.hpwl()
    undo = (st.X.copy(), st.Y.copy(), st.K.copy())
    before = len(check()) if check is not None else 0
    improved, gain = True, 0.0
    while improved and time.monotonic() - t0 < time_s:
        improved = False
        for g in grp:
            for ai in range(len(g)):
                for bi in range(ai + 1, len(g)):
                    if time.monotonic() - t0 >= time_s:
                        break
                    i, j = g[ai], g[bi]
                    if P.parts[i].side != P.parts[j].side:
                        continue
                    a, b = P.parts[i].uuid, P.parts[j].uuid
                    rep["tries"] += 1
                    d = float(terms.delta(poses, [a, b], {a: poses[b], b: poses[a]}))
                    if d < -MIN_GAIN:
                        poses[a], poses[b] = poses[b], poses[a]
                        st.X[i], st.X[j] = st.X[j], st.X[i]
                        st.Y[i], st.Y[j] = st.Y[j], st.Y[i]
                        st.K[i], st.K[j] = st.K[j], st.K[i]
                        gain -= d
                        rep["swaps"] += 1
                        improved = True
    rep["after"] = round(start - gain, 6)
    rep["hpwl_before"] = round(float(hpwl0), 3)
    rep["hpwl_after"] = round(float(st.hpwl()), 3)
    rep["seconds"] = round(time.monotonic() - t0, 2)
    if check is not None and rep["swaps"] and len(check()) > before:
        st.X[:], st.Y[:], st.K[:] = undo
        rep["undone"] = True
    if log:
        log(f"pair swaps: {rep['swaps']} on {rep['parts']} parts, term {rep['before']:.3f} -> {rep['after']:.3f}"
            f"{' (undone: exact check worse)' if rep.get('undone') else ''}")
    return rep
