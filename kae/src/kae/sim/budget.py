# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Budgets from the testbench: how much copper a structure may spend before a requirement fails.

The placer and the critical router price every structure as spend / allocation, with the
allocation from a closed form in kae.physics.priors unless the brief's structure carries a
`budget` (kae.physics.build Ctx.budget). This module derives that budget on the board's own
circuit wherever a testbench judges the structure, once per board, before or beside placement:

- cell: a series inductance is swept at the cell's insertion point (autotb LOOP_LINK) on the
  ideal circuit at every corner. The budget is the loop's ideal inductance (its capacitors'
  ESL, from the loop test) plus the largest added inductance at which every corner still meets
  the switch-node requirement.

Budgets are written beside the board (`board.budgets.json`) and reach a brief only through
`apply`, called by the methods that opt in (the critical router's --budgets). The evaluators
(score.py, critical_recheck) never apply them: they keep the closed-form allocations, so a
method's score is not changed by its own budgets.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from kae.physics import priors as PR

from .autotb import LOOP_LINK
from .testbench import fmt

SWEEP_NH = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0)
QUANTITY = {"cell": "L_nH"}                          # the brief budget key each kind sets


def _with_l(t, nh):
    """Test t with nh of series loop inductance at its insertion point (0: the 0 V link)."""
    u = copy.deepcopy(t)
    u.id = f"{t.id}@L={fmt(nh)}n"
    if nh > 0:
        def sub(ln):
            w = ln.split()
            return f"L{LOOP_LINK[1:]} {w[1]} {w[2]} {nh}n" if w and w[0] == LOOP_LINK else ln
        u.lines = [sub(ln) for ln in t.lines]
    return u


def _crossing(points, op, bound):
    """Largest L (nH) of the sorted (L, value) points at which `value op bound` still holds, by linear
    interpolation to the first failure; (L, note)."""
    ok = (lambda v: v <= bound) if op in ("<=", "<") else (lambda v: v >= bound)
    last = None
    for L, v in points:
        if v is None:
            return (last[0] if last else 0.0), f"did not converge at {fmt(L)} nH"
        if not ok(v):
            if last is None:
                return 0.0, f"fails with no added inductance ({fmt(v)} against {fmt(bound)})"
            (l0, v0), l1 = last, L
            return l0 + (l1 - l0) * (bound - v0) / (v - v0), ""
        last = (L, v)
    return points[-1][0], f"holds up to {fmt(points[-1][0])} nH, the sweep's end"


def cell_budgets(tests, ctx, jobs=8, timeout=600):
    """{structure id: budget dict} for the cell tests (kind cell with a <= requirement and the
    insertion point), from their sweep on the ideal circuit (ctx.rb is not used)."""
    from .evaluate import evaluate
    cells = [t for t in tests if t.kind == "cell" and t.structure and not t.unknown and t.requires
             and any(ln.startswith(LOOP_LINK + " ") for ln in t.lines)]
    loops = {t.id[len("loop:"):]: t for t in tests if t.kind == "loop" and not t.unknown}
    plan = [_with_l(t, nh) for t in cells for nh in SWEEP_NH] + [loops[t.id] for t in cells if t.id in loops]
    ideal_ctx = copy.copy(ctx)
    ideal_ctx.rb = None
    rep = evaluate(plan, ideal_ctx, jobs=jobs, timeout=timeout)
    by_id = {r["id"]: r for r in rep["tests"]}
    out = {}
    for t in cells:
        q = t.requires[0]
        worst = "hi" if q.op in ("<=", "<") else "lo"       # the requirement holds at every corner iff here
        points, failed = [], []
        for nh in SWEEP_NH:
            r = by_id[f"{t.id}@L={fmt(nh)}n"]
            row = next(x for x in r["requirements"] if x["meas"] == q.meas)
            if any(p.startswith("ideal") for p in r.get("problems") or []):
                failed.append(fmt(nh))
            points.append((nh, (row.get("ideal") or {}).get(worst)))
        extra, note = _crossing(points, q.op, q.bound)
        if failed:
            note = "; ".join(x for x in (note, f"corners failed at {', '.join(failed)} nH: the worst is over the rest") if x)
        lp = by_id.get(f"loop:{t.id}")
        l0 = ((lp or {}).get("info", {}).get("loop_nH", {}).get("ideal") or {}).get("typ")
        if l0 is None:
            continue                                   # no loop test: the budget has no reference
        value = l0 + extra
        basis = (f"simulated: {t.id}, {q.meas} {q.op} {fmt(q.bound)} at every corner: {fmt(extra)} nH above "
                 f"the {fmt(l0)} nH of its capacitors" + (f"; {note}" if note else ""))
        b = dict(value=round(value, 4), unit="nH", basis=basis, **{"class": "sim"},
                 detail=dict(test=t.id, ideal_loop_nH=l0, added_nH=round(extra, 4), sweep=points,
                             bound=q.bound, src=q.src))
        prev = out.get(t.structure)
        if prev is None or b["value"] < prev["value"]:     # a structure's phases: the tightest
            out[t.structure] = b
    return out


def prior_of(brief, sid):
    """The closed-form allocation the placer would use for structure sid (for comparison)."""
    s = next((x for x in brief.get("structures") or [] if x.get("id") == sid), None)
    if s is None or s.get("kind") != "commutation_cell":
        return None
    ex = s.get("excite") or {}
    v = ex.get("V") or ((brief.get("nets") or {}).get(s.get("rail")) or {}).get("volts") or PR.V_IN_UNKNOWN.value
    return PR.hot_loop_budget(s.get("class") or "unknown", v, t_sw_ns=ex.get("t_sw_ns")).value


def write(budgets, path, board_sha="", testbench_sha=""):
    Path(path).write_text(json.dumps(dict(version=1, board_sha256=board_sha, testbench_sha256=testbench_sha,
                                          budgets=budgets), indent=1) + "\n")


def load(path):
    return json.loads(Path(path).read_text()).get("budgets") or {}


def apply(brief, budgets):
    """Put each budget on its brief structure (`budget[L_nH]`); returns the ids applied."""
    done = []
    for s in brief.get("structures") or []:
        b = budgets.get(s.get("id"))
        if b is None:
            continue
        key = QUANTITY.get("cell") if s.get("kind") == "commutation_cell" else None
        if key is None:
            continue
        s.setdefault("budget", {})[key] = {k: b[k] for k in ("value", "unit", "basis", "class")}
        done.append(s["id"])
    return done
