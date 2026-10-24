# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.joint.scorecard and kae.joint.loop with stand-in stages (no KiCad, no router)."""
import copy
from pathlib import Path

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
    assert accept(base, card(unc=1, mods={"a": 1.08}))[0]                # a completion gain within the slack
    assert not accept(base, card(unc=1, mods={"a": 1.2}))[0]             # beyond the slack
    assert accept(base, card(unc=0, mods={"a": 1.15}))[0]                # two items gained: twice the slack
    assert accept(card(unc=1, mods={"a": 1.0}), card(unc=0, mods={"a": 2.5}))[0]   # clean outranks physics
    assert not accept(base, card(unc=0, err=1, mods={"a": 1.5}))[0]      # DRC must not rise
    assert not accept(base, card(unc=1, mods={"a": 1.08}), phys_slack=0.0)[0]   # strict reading
    assert not accept(base, card(unc=2, mods={"a": 1.002}))[0]           # equal completion: float noise
    assert not accept(base, card(unc=2, mods={"a": 1.05}))[0]            # equal completion: physics worse
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

    def __init__(self, broken=("R1", "R2"), bad=(), fail_replace=(), finisher=False):
        self.finisher = finisher
        self.releasable = False
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

    def route(self, lay, it, seed, time_s, finish=False):
        self.calls.append(("route", it, seed, finish))
        if finish and (self.finisher or getattr(lay, "released", False)):
            new = copy.deepcopy(lay)
            new.broken = set()
            new.tag = "finished"
            return new
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

    def repair(self, lay, window, history, it, seed, time_s, bump_refs=(), attempt=0, legal_refs=(), drc=None):
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

    def release_near(self, lay, spots):
        return ["m"] if self.releasable else []

    def release(self, lay, modules):
        new = copy.deepcopy(lay)
        new.released = True
        return new

    def finish(self, lay, out):
        self.writes = getattr(self, "writes", 0) + 1
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
    strip = lambda rows: [{k: v for k, v in r.items() if k != "seconds"} for r in rows]
    assert strip(a["iterations"]) == strip(b["iterations"])


def test_loop_respects_the_time_budget():
    st = FakeStages(broken=("R1", "R2"))
    loop = JointLoop(st, opts=dict(min_iter_s=60.0, reserve=0.0))
    rep = loop.run("out.kicad_pcb", time_s=30.0, seed=0)
    assert rep["stop"].startswith("time") and not [c for c in st.calls if c[0] == "repair"]


def test_staged_baseline_has_no_iterations_and_no_modules():
    st = FakeStages()
    rep = _run(st, max_iters=0, modules=False, finish=False)
    assert rep["stop"] == "iteration cap" and len(rep["iterations"]) == 1
    assert not [c for c in st.calls if c[0] == "modules"]


def test_a_failing_window_does_not_lose_the_incumbent():
    class Boom(FakeStages):
        def repair(self, *a, **k):
            raise RuntimeError("window exploded")
    st = Boom(broken=("R1",))
    rep = _run(st, max_attempts=1)
    assert rep["final"]["unconnected"] == 1 and st.final.tag == "placed"
    assert any("error" in (r.get("why") or "") for r in rep["iterations"][1:])


def test_finishing_stage_runs_in_its_reserve_and_is_judged_like_a_window():
    st = FakeStages(broken=("R2",), bad=("R2",), finisher=True)
    rep = _run(st, max_attempts=1, finish_min_s=0.0)
    last = rep["iterations"][-1]
    assert last.get("finish") and last["accepted"] and rep["final"]["unconnected"] == 0
    assert st.final.tag == "finished"
    assert [c for c in st.calls if c[0] == "route" and c[3]]          # one finishing route
    # without a finisher that helps, the incumbent stands
    st2 = FakeStages(broken=("R2",), bad=("R2",), finisher=False)
    rep2 = _run(st2, max_attempts=1, finish_min_s=0.0)
    assert rep2["iterations"][-1].get("finish") and not rep2["iterations"][-1]["accepted"]


def test_second_finish_releases_module_copper_on_open_corridors():
    st = FakeStages(broken=("R2",), bad=("R2",), finisher=False)
    st.releasable = True
    rep = _run(st, max_attempts=1, finish_min_s=0.0)
    fin = [r for r in rep["iterations"] if r.get("finish")]
    assert [r["finish"] for r in fin] == [True, "release"]
    assert fin[0]["accepted"] is False and fin[1]["accepted"] and fin[1]["released"] == ["m"]
    assert rep["final"]["unconnected"] == 0


def test_longer_budgets_give_more_attempts_and_no_iteration_cap():
    for budget, want in ((900.0, 2), (3600.0, 4), (9000.0, 7)):
        st = FakeStages(broken=("R2",), bad=("R2",))
        loop = JointLoop(st, opts=dict(min_iter_s=0.0, reserve=0.0, max_parts=2, margin=1.0, finish=False))
        rep = loop.run("out.kicad_pcb", time_s=budget, seed=5)
        attempts = [c[4] for c in st.calls if c[0] == "repair"]
        assert rep["max_attempts"] == want and attempts == list(range(want))
        assert rep["stop"] == "no window left to try"


def test_exhausted_windows_are_sampled_again_while_time_is_left():
    import time as _t

    class Slow(FakeStages):
        def repair(self, *a, **k):
            _t.sleep(0.02)
            return super().repair(*a, **k)
    st = Slow(broken=("R2",), bad=("R2",))
    loop = JointLoop(st, opts=dict(min_iter_s=0.0, reserve=0.0, max_parts=2, margin=1.0, finish=False,
                                   max_attempts=1, min_cycle_s=0.01, max_iters=5, patience_cycles=10))
    rep = loop.run("out.kicad_pcb", time_s=1e6, seed=5)
    seeds = [c[2] for c in st.calls if c[0] == "repair"]
    assert len(seeds) == 5 and len(set(seeds)) == 5 and rep["cycles"] == 5   # new seeds each cycle
    # patience: two full cycles in a row with nothing kept end the loop
    st2 = Slow(broken=("R2",), bad=("R2",))
    loop2 = JointLoop(st2, opts=dict(min_iter_s=0.0, reserve=0.0, max_parts=2, margin=1.0, finish=False,
                                     max_attempts=1, min_cycle_s=0.01))
    rep2 = loop2.run("out.kicad_pcb", time_s=1e6, seed=5)
    assert rep2["stop"] == "no improvement (cycle 1)" and len([c for c in st2.calls if c[0] == "repair"]) == 2


def test_incumbent_is_written_after_every_acceptance():
    st = FakeStages(broken=("R1", "R2"))
    rep = _run(st)
    kept = sum(1 for r in rep["iterations"][1:] if r.get("accepted"))
    assert st.writes == 1 + kept + 1            # iteration 0, each kept window, the final write


def test_last_mile_line_reads_counts():
    # lastmile.close reports joined/failed as counts; a len() on them killed every window
    from kae.joint.stages import last_mile_line
    assert last_mile_line(dict(joined=2, failed=1, ripped=5, seconds=3.2)) == "joined 2, failed 1, ripped 5 (3.2s)"
    assert last_mile_line(dict(error="RuntimeError: x", seconds=0.1)) == "error RuntimeError: x"
    assert last_mile_line(None) == "nothing"


def test_cli_first_route_skips_the_last_mile_only_when_the_loop_finishes(tmp_path, monkeypatch):
    import kae.joint.cli as cli
    import kae.joint.loop as L
    import kae.joint.stages as S
    seen = {}

    class Stub:
        def __init__(self, inp, wd, opts=None, log=None):
            seen["sopts"] = dict(opts)

    class Loop:
        def __init__(self, stages, opts=None, log=None):
            pass

        def run(self, out, **kw):
            return {}

    monkeypatch.setattr(S, "KaeStages", Stub)
    monkeypatch.setattr(L, "JointLoop", Loop)
    base = ["run", str(tmp_path / "in.kicad_pcb"), str(tmp_path / "out.kicad_pcb"), "--time", "10"]
    cli.main(base)
    assert seen["sopts"]["first_last_mile"] is False
    cli.main(base + ["--max-iters", "0"])
    assert "first_last_mile" not in seen["sopts"]          # staged: the bridge's default
    cli.main(base + ["--set", "first_last_mile=1"])
    assert seen["sopts"]["first_last_mile"] == 1


def test_a_restart_portfolio_finish_has_no_release_try():
    st = FakeStages(broken=("R2",), bad=("R2",), finisher=False)
    st.releasable = True
    st.finish_restarts = True
    rep = _run(st, max_attempts=1, finish_min_s=0.0)
    assert [r["finish"] for r in rep["iterations"] if r.get("finish")] == [True]


def test_window_restarts_keep_the_fewest_open(tmp_path, monkeypatch):
    import kae.route.incremental as I
    from kae.joint.stages import KaeStages
    opened = {0: 3, 7919: 1, 2 * 7919: 2}           # by seed offset: the second restart wins

    def fake(inp, out, seed=0, time_s=0, workdir=None, opts=None, log=None):
        Path(out).write_text(f"seed {seed}")
        return dict(status="routed", router=dict(incomplete=opened[seed - 5]))
    monkeypatch.setattr(I, "route_open", fake)
    st = KaeStages.__new__(KaeStages)
    st.opts, st.wd, st.log = dict(route_parallel=2), tmp_path, lambda m: None
    raw = tmp_path / "raw.kicad_pcb"
    rep = st._route_window(tmp_path / "in.kicad_pcb", raw, 1, 5, 60.0)
    assert rep["restart_kept"] == 1 and raw.read_text() == f"seed {5 + 7919}"
    st.opts = dict(route_parallel=1)                 # default: one run, as before
    rep = st._route_window(tmp_path / "in.kicad_pcb", raw, 2, 5, 60.0)
    assert "restarts" not in rep and raw.read_text() == "seed 5"


def test_route_rank_reads_both_routers_reports():
    from kae.joint.stages import route_rank
    assert route_rank(dict(repair=dict(final=dict(errors=0, unconnected=3)))) == (0, 3)
    assert route_rank(dict(drc=dict(errors=1, unconnected=2))) == (1, 2)                 # no repair rounds
    assert route_rank(dict(bridge=dict(repair=dict(final=dict(errors=0, unconnected=0))))) == (0, 0)  # critical_cli
    assert route_rank(dict(bridge=dict(drc=dict(errors=0, unconnected=9)))) == (0, 9)
    assert route_rank(None) == (float("inf"), float("inf"))


def test_window_router_budget_grows_after_timeouts_and_shrinks_back():
    from kae.joint.stages import KaeStages
    st = KaeStages.__new__(KaeStages)
    st.opts, st.log = dict(budget_s=9000.0), (lambda m: None)
    assert st.window_route_s == 60.0
    for want in (120.0, 240.0, 450.0, 450.0):          # cap: 5 % of the budget
        st._adapt_window_s(dict(router=dict(autorouter_stop="TIMED_OUT", seconds=40.0)))
        assert st.window_route_s == want
    st._adapt_window_s(dict(router=dict(autorouter_stop="COMPLETED", seconds=10.0)))
    assert st.window_route_s == 225.0
    st._adapt_window_s(dict(router=dict(autorouter_stop="COMPLETED", seconds=100.0)))
    assert st.window_route_s == 225.0


def test_no_window_restarts_after_a_timeout_or_with_many_open(tmp_path, monkeypatch):
    import kae.route.incremental as I
    from kae.joint.stages import KaeStages
    calls = []

    def fake(inp, out, seed=0, time_s=0, workdir=None, opts=None, log=None):
        calls.append(seed)
        Path(out).write_text("x")
        return dict(status="routed", router=fake.router)
    monkeypatch.setattr(I, "route_open", fake)
    st = KaeStages.__new__(KaeStages)
    st.opts, st.wd, st.log = dict(route_parallel=2), tmp_path, lambda m: None
    for router in (dict(incomplete=2, autorouter_stop="TIMED_OUT"), dict(incomplete=40, autorouter_stop="COMPLETED")):
        fake.router, calls[:] = router, []
        st._route_window(tmp_path / "in.kicad_pcb", tmp_path / "raw.kicad_pcb", 1, 5, 60.0)
        assert calls == [5]
