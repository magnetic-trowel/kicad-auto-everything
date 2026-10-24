# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""`kae place` end to end on the fixture board, physics on and off."""
import json
import shutil
from pathlib import Path

import pytest
from shapely.geometry import Point

from kae.board import kicad_file
from kae.cli import main
from kae.place.pipeline import plan_budget

DATA = Path(__file__).parent / "data" / "board"
FIXTURE = DATA / "fixture.kicad_pcb"


def _copy(tmp_path):
    p = tmp_path / "in" / "board.kicad_pcb"
    p.parent.mkdir()
    shutil.copy(FIXTURE, p)
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(FIXTURE.with_suffix(ext), p.with_suffix(ext))
    return p


def test_budget_plan():
    assert plan_budget(900, 10) == 50.0          # small boards do not idle away a long timeout
    assert plan_budget(60, 400) == 41.0          # never past 0.85 * timeout - 10 s
    assert plan_budget(5, 10) == 5.0


@pytest.mark.parametrize("arm", [[], ["--no-physics"], ["--no-physics", "--stages", "seed,legalize"]])
def test_place_cli_end_to_end(tmp_path, arm):
    src = _copy(tmp_path)
    out = tmp_path / "out" / "board.kicad_pcb"
    rep_path = tmp_path / "report.json"
    rc = main(["place", str(src), str(out), "--time", "45", "--seed", "1", "--writer", "sexpr",
               "--report", str(rep_path), *arm])
    rep = json.loads(rep_path.read_text())
    assert rc == 0 and rep["legal"] and rep["exact"] == []
    assert rep["physics"] is ("--no-physics" not in arm)
    assert "scorecard" in rep and rep["scorecard"]["structures"] >= 0   # every arm reports physics
    assert ("anneal" in rep["stages"]) is ("seed,legalize" not in arm)
    assert json.loads(Path(str(out) + ".kae.json").read_text())["legal"] == rep["legal"]
    b0 = kicad_file.load(src).by_uuid()
    b1 = kicad_file.load(out)
    outline = b1.outline[0]
    for f in b1.footprints:
        f0 = b0[f.uuid]
        if f0.locked:
            assert (f.x, f.y, f.rot, f.side) == (f0.x, f0.y, f0.rot, f0.side)
            continue
        assert f.side == f0.side
        for p in f.pads:
            assert outline.buffer(1e-6).contains(Point(p.x, p.y)), (f.ref, p.number)


def test_read_only_numba_cache_is_copied(tmp_path, monkeypatch):
    """numba ignores a cache directory it cannot write to (the sandboxed snapshot), so the
    CLI copies it to a private directory before numba loads."""
    import os
    import sys

    from kae import cli
    src = tmp_path / "nc"
    (src / "kernels").mkdir(parents=True)
    (src / "kernels" / "k.nbi").write_text("index")
    monkeypatch.setenv("NUMBA_CACHE_DIR", str(src))
    monkeypatch.delitem(sys.modules, "numba", raising=False)
    real = os.access
    monkeypatch.setattr(os, "access", lambda p, m, **kw: False if (str(p) == str(src) and m == os.W_OK)
                        else real(p, m, **kw))
    used = cli._numba_cache()
    assert used is not None and used[0] == str(src)
    assert os.environ["NUMBA_CACHE_DIR"] == used[1] != str(src)
    assert (Path(used[1]) / "kernels" / "k.nbi").read_text() == "index"
    shutil.rmtree(used[1])
    monkeypatch.setattr(os, "access", real)          # a writable directory is used as it is
    monkeypatch.setenv("NUMBA_CACHE_DIR", str(src))
    assert cli._numba_cache() is None and os.environ["NUMBA_CACHE_DIR"] == str(src)


def test_escalation_drops_the_margin_then_relaxes_bodies():
    """Regression: relaxation existed only on the floorplan path (<= 40 items); every path
    now escalates (margin 0, then bodies without courtyards) when legalization leaves parts
    illegal."""
    from kae.place.pipeline import _escalate
    from kae.place.problem import Problem
    from kae.place.state import State, grid_violations
    P = Problem.build(kicad_file.load(FIXTURE))
    P.set_margin(30.0)                      # a margin no placement can honour
    st = State(P)
    for i in P.mov:
        st.X[i], st.Y[i] = P.ncx // 2, P.ncy // 2
    assert grid_violations(st)
    steps = _escalate(P, st, workers=2, seed=0, log=None, time_s=20.0)
    assert steps and steps[0]["step"] == "margin 0"
    assert P.margin == 0.0 and not grid_violations(st)


def test_local_replace_moves_only_the_subset_inside_its_window(tmp_path):
    """The module loop's local re-placement: only the named parts move, inside the window,
    and come back legal; everything else stays where the board has it."""
    from kae.place.pipeline import local_replace, place
    b = kicad_file.load(FIXTURE)
    res = place(b, seed=0, time_s=30.0, physics=False)
    for fp in b.footprints:                       # the placed board
        if fp.uuid in res.poses:
            fp.x, fp.y, fp.rot, _ = res.poses[fp.uuid]
    movable = [fp for fp in b.footprints if not fp.locked and fp.uuid in res.poses]
    sub = [fp.ref for fp in movable[:3]]
    xs = [fp.x for fp in movable[:3]]
    ys = [fp.y for fp in movable[:3]]
    win = (min(xs) - 4, min(ys) - 4, max(xs) + 4, max(ys) + 4)
    out = local_replace(b, sub, window_mm=win, time_s=20.0, seed=1, physics=False)
    assert set(out.report["parts"]) == set(sub)
    assert out.report["legal_grid"] and not out.report["exact"]
    assert {b.by_uuid()[u].ref for u in out.poses} == set(sub)


def test_local_replace_takes_net_weights_from_routing_feedback():
    """kae.joint's call: net_weights scale wirelength weights (an unrouted net pulls its pins
    together); the result is exactly legal for the moved parts and nothing else moves."""
    from kae.place.pipeline import local_replace, place
    b = kicad_file.load(FIXTURE)
    res = place(b, seed=0, time_s=30.0, physics=False)
    for fp in b.footprints:
        if fp.uuid in res.poses:
            fp.x, fp.y, fp.rot, _ = res.poses[fp.uuid]
    sub = [fp.ref for fp in b.footprints if not fp.locked and fp.uuid in res.poses][:4]
    out = local_replace(b, sub, time_s=15.0, seed=0, physics=False, net_weights={"SIG1": 10.0})
    assert not out.report["exact"]
    w = {n.name: n.weight for n in out.problem.nets}
    base = {n.name: n.weight for n in local_replace(b, sub, time_s=5.0, physics=False).problem.nets}
    assert abs(w["SIG1"] - 10.0 * base["SIG1"]) < 1e-9
    assert {b.by_uuid()[u].ref for u in out.poses} == set(sub)


def test_legal_grid_follows_the_exact_check():
    """The grid is a conservative prefilter (bodies for missing courtyards, outward rounding):
    a grid violator the exact check does not confirm does not make the result illegal; it is
    reported under grid_conservative by class."""
    from kae.place.pipeline import grid_verdict
    from kae.place.problem import Problem
    from kae.place.state import State
    P = Problem.build(kicad_file.load(FIXTURE))
    st = State(P)
    for i in P.mov:
        st.X[i], st.Y[i] = P.ncx // 2, P.ncy // 2
    i, j = P.mov[0], P.mov[1]
    v = grid_verdict(P, st, [dict(type="courtyards_overlap", refs=[P.parts[i].ref, P.parts[j].ref], parts=[i, j])])
    assert v["legal_grid"] is False
    v = grid_verdict(P, st, [])
    assert v["legal_grid"] is True and v["grid_conservative"]["count"] > 0


def test_local_replace_takes_congestion_history_and_a_fixed_move_budget():
    """kae.joint's hooks: cong_history adds static demand to the congestion bins (both
    engines, totals exact); moves_per_part replaces the clock, so a re-place repeats."""
    import numpy as np
    from kae.place.pipeline import local_replace, place
    b = kicad_file.load(FIXTURE)
    res = place(b, seed=0, time_s=30.0, physics=False)
    for fp in b.footprints:
        if fp.uuid in res.poses:
            fp.x, fp.y, fp.rot, _ = res.poses[fp.uuid]
    sub = [fp.ref for fp in b.footprints if not fp.locked and fp.uuid in res.poses][:4]
    seen = {}

    def hist(x0, y0, bsz, nbx, nby):
        seen["shape"] = (nbx, nby)
        a = np.zeros((nbx, nby))
        a[nbx // 2, nby // 2] = 5.0
        return a
    out1 = local_replace(b, sub, time_s=30.0, physics=False, cong_history=hist, moves_per_part=300)
    out2 = local_replace(b, sub, time_s=30.0, physics=False, cong_history=hist, moves_per_part=300)
    assert seen["shape"] and out1.report["anneal"]["cong_history"]["bins"] == 1
    assert out1.report["anneal"]["moves"] == out2.report["anneal"]["moves"]
    assert out1.poses == out2.poses


def test_probe_select_keeps_the_placement_that_routes_within_the_physics_slack(monkeypatch, tmp_path):
    """--probe-select N: N placements (seeds), each routed briefly; the fewest open connections
    wins among the candidates within 10% of the best physics, physics breaking ties."""
    from types import SimpleNamespace
    from kae import cli
    from kae.place import pipeline
    from kae.place.pipeline import Result
    from kae.route import bridge
    from kae.route import drc as kdrc
    # seed: (physics, unconnected): seed 1 routes best but costs 30% more physics; seed 2 is
    # within the slack and routes better than seed 0
    table = {0: (1.00, 5), 1: (1.30, 0), 2: (1.05, 2)}

    def fake_place(board, seed=0, time_s=0, **kw):
        return Result(poses={"u": (0, 0, 0, "F")}, report=dict(scorecard=dict(total_linear=table[seed][0]), exact=[]),
                      state=None, problem=None)
    monkeypatch.setattr(pipeline, "place", fake_place)
    monkeypatch.setattr("kae.board.kicad_file.load", lambda p: SimpleNamespace(path=p))
    monkeypatch.setattr(kdrc, "stage_board", lambda out, inp, d: out)
    routed = {}

    def fake_route(staged, out, seed=0, time_s=0, opts=None, log=None):
        k = len(routed)
        routed[k] = time_s
        return dict(repair=dict(final=dict(unconnected=table[k][1])))
    monkeypatch.setattr(bridge, "route", fake_route)
    a = SimpleNamespace(probe_select=3, time=600.0, seed=0, input=str(FIXTURE), writer="sexpr")
    res = cli._probe_select(a, None, {}, __import__("time").monotonic(), lambda *x, **k: dict(writer="fake"))
    ps = res.report["probe_select"]
    assert ps["chosen"] == 2 and [c["unconnected"] for c in ps["candidates"]] == [5, 0, 2]
