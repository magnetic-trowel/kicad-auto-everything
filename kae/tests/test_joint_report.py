# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What kae.joint reports to the commanding LLM: the "blocked" diagnosis, checks that did not
run, the --set keys, escalated window sizes, the kept board's last mile and partial runs.
Stand-in stages and stubs only (no KiCad, no router)."""
import copy
import json
import re
from pathlib import Path

from kae.joint.loop import DEFAULTS
from kae.joint.scorecard import Scorecard

from test_joint_loop import FakeStages, _run

PKG = [dict(ref="U1", balls=["A1"], summary="U1: 1 ball no routing can escape")]
DIAG = dict(blocked=[dict(net="N1", cause="rule", binding="clearance 0.2 mm")], congestion=[], summary=["N1: rule"],
            undiagnosed=0)


# ---- 1: the router's "blocked" diagnosis reaches the report
class Diagnosing(FakeStages):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.diagnosed = []

    def place(self, seed, time_s):
        lay = super().place(seed, time_s)
        lay.info = dict(route=dict(status="routed", blocked=dict(packages=PKG, summary=[PKG[0]["summary"]])))
        return lay

    def diagnose(self, lay, drc, it, time_s):
        self.diagnosed.append((lay.tag, it, time_s))
        return copy.deepcopy(DIAG)


def test_final_report_carries_the_blocked_diagnosis_and_escape_certificates():
    st = Diagnosing(broken=("R2",), bad=("R2",))
    rep = _run(st, max_attempts=1, finish=False)
    fin = rep["final"]
    assert fin["unconnected"] == 1 and st.diagnosed and st.diagnosed[0][0] == "placed"
    assert fin["blocked"]["blocked"] == DIAG["blocked"]
    assert fin["blocked"]["packages"] == PKG and fin["blocked"]["packages_iter"] == 0
    assert "final board" in fin["blocked_note"]


def test_final_report_uses_the_finishing_bridge_diagnosis_of_its_own_board():
    class Fin(Diagnosing):
        def route(self, lay, it, seed, time_s, finish=False):
            new = super().route(lay, it, seed, time_s, finish=finish)
            if finish:
                new = copy.deepcopy(new)
                new.broken = {"R2"}          # still open, but no new errors: physics better
                new.info = dict(route=dict(finish=True, blocked=dict(DIAG, summary=["from the finish"])))
            return new

        def evaluate(self, lay, it):
            c, fb = super().evaluate(lay, it)
            if (lay.info.get("route") or {}).get("finish"):
                c.modules = {"m": 0.5}
            return c, fb
    st = Fin(broken=("R2",), bad=("R2",))
    rep = _run(st, max_attempts=1, finish_min_s=0.0, finish_release=False)
    fin = rep["final"]
    assert fin["iter"] == rep["iterations"][-1]["iter"] and rep["iterations"][-1]["accepted"]
    assert fin["blocked"]["summary"] == ["from the finish"] and not st.diagnosed
    assert fin["blocked"]["packages"] == PKG          # the certificate of iteration 0 rides along


def test_clean_final_board_needs_no_diagnosis():
    st = Diagnosing()
    rep = _run(st)
    assert rep["final"]["blocked"] is None and rep["final"]["blocked_note"] == "nothing open" and not st.diagnosed


def test_route_carries_blocked_and_iteration_0_skips_it_when_a_finish_follows(tmp_path, monkeypatch):
    import kae.route.bridge as BR
    import kae.route.critical_write as W
    from kae.joint.stages import KaeStages, Layout
    seen = []

    def fake_route(inp, out, seed=0, time_s=0, workdir=None, opts=None, log=None):
        seen.append(dict(opts))
        Path(out).write_text("routed")
        return dict(status="routed", blocked=dict(packages=PKG), repair=dict(final=dict(errors=0, unconnected=3)))
    monkeypatch.setattr(BR, "route", fake_route)
    monkeypatch.setattr(W, "edit", lambda src, dst, **k: Path(dst).write_text(Path(src).read_text()))
    monkeypatch.setattr(W, "routing", lambda p: [])
    st = KaeStages(tmp_path / "in.kicad_pcb", tmp_path / "wd", opts=dict(first_blocked=False), log=lambda m: None)
    b = tmp_path / "placed.kicad_pcb"
    b.write_text("placed")
    new = st.route(Layout(board=str(b)), 0, seed=1, time_s=100.0)
    assert seen[-1]["blocked"] is False
    assert new.info["route"]["blocked"] == dict(packages=PKG)
    st.opts = {}                                       # no finish follows: the bridge's default
    st.route(Layout(board=str(b)), 0, seed=1, time_s=100.0)
    assert "blocked" not in seen[-1]


def test_cli_turns_the_first_diagnosis_off_only_when_the_loop_finishes(tmp_path, monkeypatch):
    seen = _cli(tmp_path, monkeypatch, [])
    assert seen["sopts"]["first_blocked"] is False
    seen = _cli(tmp_path, monkeypatch, ["--max-iters", "0"])
    assert "first_blocked" not in seen["sopts"]


# ---- 3: --set keys
def _cli(tmp_path, monkeypatch, extra, run=None):
    import kae.joint.cli as cli
    import kae.joint.loop as L
    import kae.joint.stages as S
    seen = {}

    class Stub:
        def __init__(self, inp, wd, opts=None, log=None):
            seen["sopts"] = dict(opts)

    class Loop:
        def __init__(self, stages, opts=None, log=None):
            seen["lopts"] = dict(opts)

        def run(self, out, **kw):
            return run(self, out) if run else {}

    monkeypatch.setattr(S, "KaeStages", Stub)
    monkeypatch.setattr(L, "JointLoop", Loop)
    report = tmp_path / "rep.json"
    seen["rc"] = cli.main(["run", str(tmp_path / "in.kicad_pcb"), str(tmp_path / "out.kicad_pcb"), "--time", "10",
                           "--report", str(report), *extra])
    seen["rep"] = json.loads(report.read_text())
    return seen


def test_cli_set_rejects_keys_nothing_reads(tmp_path, monkeypatch):
    seen = _cli(tmp_path, monkeypatch, ["--set", "marign=3"])
    assert seen["rc"] == 2 and seen["rep"]["status"] == "error" and "marign" in seen["rep"]["error"]
    assert "sopts" not in seen                          # nothing ran
    seen = _cli(tmp_path, monkeypatch, ["--set", "margin=3", "--set", "replace_margin=0.5", "--set", "escape_band=0",
                                        "--set", "bridge.neckdown=true"])
    assert seen["lopts"]["margin"] == 3                 # the loop's window margin
    assert seen["sopts"]["replace_margin"] == 0.5 and seen["sopts"]["escape_band"] == 0


def test_stage_keys_list_every_option_the_stages_read():
    from kae.joint import stages
    src = Path(stages.__file__).read_text()
    read = {a or b for a, b in re.findall(r'(?<![\w.])o\.get\("(\w+)"|self\.opts(?:\.get\(|\[)"(\w+)"', src)}
    assert read and read <= stages.STAGE_KEYS, sorted(read - stages.STAGE_KEYS)
    assert "margin" not in stages.STAGE_KEYS            # margin is the loop's alone
    doc = stages.KaeStages.__doc__
    assert "phys," not in doc and "route_share" not in doc


# ---- 4: checks that did not run read null
def test_scorecard_reports_unchecked_as_null():
    c = Scorecard(unconnected=10 ** 6, errors=10 ** 6, note="drc failed: timeout")
    c.checked.update(drc=False, physics=False)
    d = c.to_dict()
    assert d["unconnected"] is None and d["errors"] is None and d["physics"] is None and d["flagged"] is None
    assert d["legal"] is None and d["checked"] == dict(drc=False, physics=False, brief=True)
    assert d["note"] == "drc failed: timeout"
    assert 10 ** 6 not in json.loads(json.dumps(d)).values()
    ok = Scorecard(unconnected=2, modules={"a": 0.5}).to_dict()
    assert ok["unconnected"] == 2 and ok["physics"] == 0.5 and ok["checked"]["physics"] and ok["note"] is None


def test_evaluate_marks_failed_drc_and_recheck_as_not_checked(tmp_path, monkeypatch):
    import kae.route.critical_recheck as CR
    import kae.route.drc as D
    from kae.joint.stages import KaeStages, Layout

    def boom(*a, **k):
        raise RuntimeError("recheck exploded")

    def drc_fails(*a, **k):
        raise D.DrcError("kicad-cli timed out")
    monkeypatch.setattr(D, "stage_board", lambda src, proj, d: Path(src))
    monkeypatch.setattr(D, "run", drc_fails)
    monkeypatch.setattr(CR, "recheck", boom)
    st = KaeStages(tmp_path / "in.kicad_pcb", tmp_path / "wd", log=lambda m: None)
    st.brief = dict(structures=[dict(id="m")], nets={}, parts={})
    lay = Layout(board=str(tmp_path / "b.kicad_pcb"), stage={"m": dict(u=0.5)}, status={"m": "routed"})
    card, _ = st.evaluate(lay, 1)
    d = card.to_dict()
    assert d["unconnected"] is None and d["errors"] is None and d["physics"] is None
    assert d["checked"] == dict(drc=False, physics=False, brief=True)
    assert "drc failed" in d["note"] and "recheck failed" in d["note"]
    assert card.unconnected == 10 ** 6                  # acceptance keeps its sentinel
    st.brief_error = "ValueError: no netlist"           # a brief that failed: physics off, said so
    monkeypatch.setattr(D, "run", lambda *a, **k: dict(violations=[], unconnected_items=[]))
    card, _ = st.evaluate(lay, 2)
    assert card.checked == dict(drc=True, physics=False, brief=False) and "brief failed" in card.note


def test_loop_rows_carry_checked_and_note():
    class NoPhys(FakeStages):
        def evaluate(self, lay, it):
            c, fb = super().evaluate(lay, it)
            c.modules, c.note = {}, "physics not checked: recheck failed (RuntimeError: x)"
            c.checked["physics"] = False
            return c, fb
    rep = _run(NoPhys())
    for r in rep["iterations"]:
        if "unconnected" in r:
            assert r["physics"] is None and r["flagged"] is None and "recheck failed" in r["note"]
            assert r["checked"]["physics"] is False
    assert rep["stop"] == "clean, physics not checked" and rep["final"]["physics"] is None


# ---- 8: an exception after OUTPUT was written is a partial result
def test_cli_reports_partial_with_rows_when_a_stage_raises_after_output(tmp_path, monkeypatch):
    def raises_after_save(loop, out):
        loop.rep = dict(iterations=[dict(iter=0, unconnected=3)], seed=0)
        Path(out).write_text("board")
        raise RuntimeError("geometry exploded")
    seen = _cli(tmp_path, monkeypatch, [], run=raises_after_save)
    rep = seen["rep"]
    assert seen["rc"] == 0 and rep["status"] == "partial" and rep["output_exists"] is True
    assert rep["iterations"] == [dict(iter=0, unconnected=3)] and "geometry exploded" in rep["error"]

    def raises_before(loop, out):
        raise RuntimeError("place exploded")
    (tmp_path / "out.kicad_pcb").unlink()
    seen = _cli(tmp_path, monkeypatch, [], run=raises_before)
    assert seen["rc"] == 2 and seen["rep"]["status"] == "error" and seen["rep"]["output_exists"] is False
