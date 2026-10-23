# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.joint.scorecard and kae.joint.loop with stand-in stages (no KiCad, no router)."""
import copy

from kae.joint.feedback import PartGeom
from kae.joint.loop import JointLoop, derive_seed
from kae.joint.scorecard import Scorecard, accept, physics_total


def card(unc=0, err=0, pe=0, mods=None):
    return Scorecard(placement_errors=pe, unconnected=unc, errors=err, modules=dict(mods or {}))


def test_accept_is_lexicographic_with_hard_guards():
    base = card(unc=2, err=0, mods={"a": 1.0})
    assert accept(base, card(unc=1, mods={"a": 1.0}))[0]                 # completion better
    assert accept(base, card(unc=2, mods={"a": 0.8}))[0]                 # physics better
    assert not accept(base, card(unc=2, mods={"a": 1.0}))[0]             # nothing better
    assert not accept(base, card(unc=3, mods={"a": 0.5}))[0]             # completion must not drop
    assert not accept(base, card(unc=1, err=1, mods={"a": 1.0}))[0]      # DRC errors must not rise
    assert not accept(base, card(unc=0, pe=1, mods={"a": 1.0}))[0]       # legality first
    assert not accept(base, card(unc=1, mods={"a": 1.2}))[0]             # physics must not worsen
    assert accept(base, card(unc=1, mods={"a": 1.002}))[0]               # within float tolerance
    # a module losing its value counts as missing, capped utilizations
    assert physics_total({"a": None, "b": 99.0, "c": 0.5}) == 3.0 + 5.0 + 0.5
    assert not accept(base, card(unc=1, mods={"a": None}))[0]


class Lay:
    def __init__(self, broken, poses, tag):
        self.broken = set(broken)       # connections still unrouted (by part ref)
        self.poses = dict(poses)
        self.tag = tag
        self.info = {}


class FakeStages:
    """A board of parts on a line; connection k is unrouted until part k is re-placed.
    Re-placing part 'BAD' makes a new error (rejected). Physics: each move adds 0.01 to
    module 'm' unless the part is 'GOOD'."""

    def __init__(self, broken=("R1", "R2"), bad=(), fail_replace=()):
        self.module_parts = {"m": ["u1"]}
        self.broken0 = broken
        self.bad = set(bad)
        self.fail_replace = set(fail_replace)
        self.calls = []

    def place(self, seed, time_s):
        self.calls.append(("place", seed))
        return Lay(self.broken0, {f"u{k}": (10.0 * k, 0.0, 0.0, "F") for k in range(4)}, "placed")

    def layout_from(self, path):
        return self.place(0, 0)

    def modules(self, lay, it, **kw):
        self.calls.append(("modules", it))
        return lay

    def route(self, lay, it, seed, time_s):
        self.calls.append(("route", it, seed))
        return lay

    def evaluate(self, lay, it):
        c = card(unc=len(lay.broken), err=len(getattr(lay, "errors", ())), mods={"m": 1.0})
        drc = {"unconnected_items": [
            {"items": [{"description": f"Pad 1 [N{r}] of {r} on F.Cu", "pos": {"x": 10.0 * int(r[1:]), "y": 0.0}},
                       {"description": f"Pad 2 [N{r}] of R0 on F.Cu", "pos": {"x": 10.0 * int(r[1:]) + 3.0, "y": 0.0}}]}
            for r in sorted(lay.broken)], "violations": []}
        return c, dict(drc=drc, recheck={})

    def geometry(self, lay):
        parts = {u: PartGeom(uuid=u, ref=f"R{u[1:]}", bbox=(p[0] - 1, -1, p[0] + 1, 1), locked=(u == "u0"))
                 for u, p in lay.poses.items()}
        return parts, (-5, -5, 50, 5), {u: g.center for u, g in parts.items()}, {u: g.ref for u, g in parts.items()}

    def repair(self, lay, window, history, it, seed, time_s, bump_refs=(), attempt=0):
        self.calls.append(("repair", it, seed, tuple(window.refs), attempt))
        assert history.total() > 0                 # failures were recorded as congestion history
        refs = set(window.refs)
        if refs & self.fail_replace:
            return None, dict(outcome="illegal after repair")
        new = copy.deepcopy(lay)
        new.broken = lay.broken - refs
        if refs & self.bad:
            new.errors = ("e",)
        return new, dict(seconds=1.0)

    def finish(self, lay, out):
        self.final = lay
        return dict(output=str(out))


def _run(stages, **kw):
    loop = JointLoop(stages, opts=dict(min_iter_s=0.0, reserve=0.0, max_parts=2, margin=1.0, **kw))
    return loop.run("out.kicad_pcb", time_s=1e6, seed=5)


def test_loop_repairs_until_clean_and_logs_iterations():
    st = FakeStages()
    rep = _run(st)
    assert rep["stop"] == "clean, nothing flagged"
    assert rep["final"]["unconnected"] == 0
    rows = rep["iterations"]
    assert rows[0]["unconnected"] == 2 and rows[0]["accepted"]
    assert all(r["accepted"] for r in rows[1:]) and len(rows) >= 2
    for r in rows[1:]:
        assert {"window", "unconnected", "errors", "physics", "accepted", "seconds"} <= set(r)
    assert ("place", derive_seed(5, 0)) in st.calls


def test_loop_reverts_worse_iterations_and_gives_up_on_exhausted_windows():
    st = FakeStages(broken=("R2",), bad=("R2",))
    rep = _run(st, max_attempts=2)
    assert rep["final"]["unconnected"] == 1 and rep["accepted"] == 0
    assert rep["stop"] == "no window left to try"
    attempts = [c[4] for c in st.calls if c[0] == "repair"]
    assert attempts == [0, 1]                  # retried once, larger, then exhausted
    assert st.final.tag == "placed" and not getattr(st.final, "errors", ())


def test_loop_counts_illegal_replacements_and_moves_on():
    st = FakeStages(broken=("R1", "R3"), fail_replace=("R1",))
    rep = _run(st, max_attempts=1)
    rows = rep["iterations"]
    assert any(r.get("why") == "illegal after repair" for r in rows)
    assert rep["final"]["unconnected"] == 1    # R3's connection repaired, R1's window failed


def test_loop_is_deterministic():
    a = _run(FakeStages(broken=("R1", "R2", "R3")))
    b = _run(FakeStages(broken=("R1", "R2", "R3")))
    strip = lambda rows: [{k: v for k, v in r.items() if k != "seconds"} for r in rows]  # noqa: E731
    assert strip(a["iterations"]) == strip(b["iterations"])


def test_loop_respects_the_time_budget():
    st = FakeStages(broken=("R1", "R2"))
    loop = JointLoop(st, opts=dict(min_iter_s=60.0, reserve=0.0))
    rep = loop.run("out.kicad_pcb", time_s=30.0, seed=0)
    assert rep["stop"].startswith("time") and not [c for c in st.calls if c[0] == "repair"]


def test_staged_baseline_has_no_iterations_and_no_modules():
    st = FakeStages()
    rep = _run(st, max_iters=0, modules=False)
    assert rep["stop"] == "iteration cap" and len(rep["iterations"]) == 1
    assert not [c for c in st.calls if c[0] == "modules"]
