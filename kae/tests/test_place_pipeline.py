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


def test_local_replace_holds_the_other_parts_where_the_board_has_them():
    """local_replace left every other movable part movable, modeled snapped to the grid and to
    a right angle (a part at 45 deg as 0 deg), and judged the re-placed parts against those
    stand-ins. The others are now locked at their real poses (as joint.replace does)."""
    from kae.place.pipeline import local_replace
    b = kicad_file.load(FIXTURE)
    movable = [fp for fp in b.footprints if not fp.locked and fp.on_board]
    sub, other = [fp.ref for fp in movable[:2]], movable[2]
    other.rot = 45.0
    out = local_replace(b, sub, time_s=5.0, seed=0, physics=False, moves_per_part=50)
    P = out.problem
    assert {P.parts[i].ref for i in P.mov} == set(sub)
    q = next(p for p in P.parts if p.uuid == other.uuid)
    assert not q.movable and q.fp.rot == 45.0 and (q.fp.x, q.fp.y) == (other.x, other.y)
    assert not b.by_uuid()[other.uuid].locked            # the caller's board is untouched


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


def _probe_fakes(monkeypatch, table, calls):
    from types import SimpleNamespace
    from kae.place import pipeline
    from kae.place.pipeline import Result
    from kae.route import bridge
    from kae.route import drc as kdrc

    def fake_place(board, seed=0, time_s=0, **kw):
        calls.setdefault("anneal_args", {})[seed] = dict(kw.get("anneal_args") or {})
        return Result(poses={"u": (0, 0, 0, "F")}, report=dict(scorecard=dict(total_linear=table[seed][0]), exact=[]),
                      state=None, problem=None)
    monkeypatch.setattr(pipeline, "place", fake_place)
    monkeypatch.setattr("kae.board.kicad_file.load", lambda p: SimpleNamespace(path=p))
    monkeypatch.setattr(kdrc, "stage_board", lambda out, inp, d: out)

    def fake_route(staged, out, seed=0, time_s=0, opts=None, log=None):
        k = int(Path(staged).parent.name.removeprefix("cand"))    # candidate k is placed with seed k
        calls.setdefault("probe_s", []).append(time_s)
        return dict(repair=dict(final=dict(unconnected=table[k][1])))
    monkeypatch.setattr(bridge, "route", fake_route)


def test_probe_select_keeps_the_placement_that_routes_within_the_physics_slack(monkeypatch, tmp_path):
    """--probe-select N: N placements (seeds), each routed briefly; the fewest open connections
    wins among the candidates within 10% of the best physics, physics breaking ties."""
    from types import SimpleNamespace
    from kae import cli
    # seed: (physics, unconnected): seed 1 routes best but costs 30% more physics; seed 2 is
    # within the slack and routes better than seed 0
    table = {0: (1.00, 5), 1: (1.30, 0), 2: (1.05, 2)}
    calls = {}
    _probe_fakes(monkeypatch, table, calls)
    a = SimpleNamespace(probe_select=3, time=600.0, seed=0, input=str(FIXTURE), writer="sexpr")
    res = cli._probe_select(a, None, {}, __import__("time").monotonic(), lambda *x, **k: dict(writer="fake"))
    ps = res.report["probe_select"]
    assert ps["chosen"] == 2 and [c["unconnected"] for c in ps["candidates"]] == [5, 0, 2]


def test_probe_select_jitters_later_seed_stages_and_probes_in_parallel(monkeypatch):
    """Candidates after the first start from a jittered seed stage (the user's anneal args kept);
    --probe-parallel P probes P at once, so each probe gets the time of N/P sequential ones."""
    from types import SimpleNamespace
    from kae import cli
    table = {0: (1.00, 5), 1: (1.02, 1), 2: (1.05, 2), 3: (1.01, 3)}
    seq, par = {}, {}
    _probe_fakes(monkeypatch, table, seq)
    a = SimpleNamespace(probe_select=4, time=1200.0, seed=0, input=str(FIXTURE), writer="sexpr",
                        probe_jitter=0.2, probe_parallel=1)
    kw = dict(anneal_args={"w_chan": 3})
    cli._probe_select(a, None, kw, __import__("time").monotonic(), lambda *x, **k: None)
    assert seq["anneal_args"][0] == {"w_chan": 3}
    assert all(seq["anneal_args"][k] == {"w_chan": 3, "seed_jitter": 0.2} for k in (1, 2, 3))
    assert kw == dict(anneal_args={"w_chan": 3})          # the caller's args are not mutated
    _probe_fakes(monkeypatch, table, par)
    a.probe_parallel = 2
    res = cli._probe_select(a, None, kw, __import__("time").monotonic(), lambda *x, **k: None)
    ps = res.report["probe_select"]
    assert ps["chosen"] == 1 and ps["parallel"] == 2
    assert [c["unconnected"] for c in ps["candidates"]] == [5, 1, 2, 3]
    assert min(par["probe_s"]) > max(seq["probe_s"]) * 1.5


def test_seed_jitter_moves_the_seed_stage_deterministically():
    from kae.place import pipeline
    from kae.place.problem import Problem
    P = Problem.build(kicad_file.load(FIXTURE))
    net_w = {net.i: net.weight for net in P.nets}
    a, _ = pipeline._seed_state(P, [], net_w, 1, lambda m: None)
    b, _ = pipeline._seed_state(P, [], net_w, 1, lambda m: None, jitter=0.2)
    c, _ = pipeline._seed_state(P, [], net_w, 1, lambda m: None, jitter=0.2)
    assert (a.X != b.X).any() and (b.X == c.X).all() and (b.Y == c.Y).all()


def test_fixed_parts_keep_their_input_pose_and_the_rest_moves(tmp_path):
    """kae place --fix / --fix-class: fixed parts are obstacles at their input pose (as locked
    parts) and no stage moves them; the others are placed."""
    from kae.place import fixed
    b = kicad_file.load(FIXTURE)
    cls = fixed.classify(b)
    assert {c["ref"] for c in cls.values() if c["cls"] == "connectors"} >= {"J1"}
    u = fixed.fixed_uuids(b, ["connectors"], ["U4"])
    by = {f.uuid: f for f in b.footprints}
    assert {by[x].ref for x in u} >= {"J1", "U4"}
    with pytest.raises(ValueError):
        fixed.fixed_uuids(b, ["panels"])
    with pytest.raises(ValueError):
        fixed.fixed_uuids(b, [], ["NOPE1"])
    out = tmp_path / "out.kicad_pcb"
    rc = main(["place", str(FIXTURE), str(out), "--time", "20", "--no-physics", "--writer", "sexpr",
               "--drc", "off", "--fix", "U4,J1"])
    assert rc in (0, 3)
    o = {f.ref: f for f in kicad_file.load(out).footprints}
    i = {f.ref: f for f in b.footprints}
    for r in ("U4", "J1"):
        assert (o[r].x, o[r].y, o[r].rot % 360) == pytest.approx((i[r].x, i[r].y, i[r].rot % 360)) and o[r].side == i[r].side
    moved = [r for r in i if not i[r].locked and r not in ("U4", "J1") and r in o
             and (abs(o[r].x - i[r].x) > 1e-3 or abs(o[r].y - i[r].y) > 1e-3)]
    assert moved
    rep = json.loads(Path(str(out) + ".kae.json").read_text())
    assert rep["fixed"]["n"] == 2 and set(rep["fixed"]["refs"]) == {"U4", "J1"}


def test_relax_bodies_off_skips_the_step_and_relaxed_overlaps_are_hazards():
    """relax_bodies 'off': escalation never frees bodies. A relaxed part whose body
    ends up over another part is a 'block' hazard (an axial resistor or a USB receptacle over
    0402s cannot be assembled); one with nothing under it is 'info'."""
    from shapely.geometry import box as sbox
    from kae.place.pipeline import _escalate, body_hazards
    from kae.place.problem import Problem
    from kae.place.state import State, grid_violations
    b = kicad_file.load(FIXTURE)
    j1 = next(f for f in b.footprints if f.ref == "J1")
    j1.courtyard = []
    j1.body = [sbox(-6, -6, 6, 6)]                 # a big body around its two pins
    P = Problem.build(b)
    P.set_margin(30.0)
    st = State(P)
    for i in P.mov:
        st.X[i], st.Y[i] = P.ncx // 2, P.ncy // 2
    steps = _escalate(P, st, workers=2, seed=0, log=None, time_s=20.0, relax_ok=False)
    assert "bodies relaxed" not in [s["step"] for s in steps]
    assert not any(getattr(p, "relaxed", False) for p in P.parts)
    assert P.relaxed_body_hazards(st) == []
    # relaxed, with U1 moved under J1's body
    P2 = Problem.build(b)
    assert "J1" in P2.relax_bodies()
    st2 = State(P2)
    for p in P2.parts:
        if p.movable:
            st2.X[p.i], st2.Y[p.i] = P2.grid_of(p.x0, p.y0)
    ref = {p.ref: p.i for p in P2.parts}
    st2.X[ref["U1"]], st2.Y[ref["U1"]] = st2.X[ref["J1"]], st2.Y[ref["J1"]]
    rep = dict(hazards=[dict(code="other", objects=[])])
    hz = body_hazards(rep, P2, st2)
    j = [h for h in hz if h["objects"][:1] == ["J1"]]
    assert hz[0]["code"] == "other" and len(j) == 1
    assert j[0]["code"] == "body_overlap" and j[0]["severity"] == "block" and "U1" in j[0]["objects"]
    st2.X[ref["U1"]], st2.Y[ref["U1"]] = P2.grid_of(*P2.outline.bounds[2:])     # far away again
    st2.X[ref["U1"]] -= 200
    j = [h for h in body_hazards(rep, P2, st2) if h["objects"][:1] == ["J1"]]
    assert len([h for h in rep["hazards"] if h["code"].startswith("body_") and h["objects"][0] == "J1"]) == 1
    assert j[0]["code"] in ("body_overlap", "body_relaxed")
def test_congestion_weight_and_margin_are_settings_and_physics_is_traced():
    """Audit P5/P10: place_w_cong and place_margin (kae.route.constraints.DEFAULTS, so --set
    and KAE_ text variables reach them) default to the current behaviour (30, auto) and switch
    the RUDY term and the routing margin off at 0; P6: the report traces physics per stage."""
    from kae.place.pipeline import place
    from kae.route.constraints import DEFAULTS
    assert DEFAULTS["place_w_cong"] == 30.0 and DEFAULTS["place_margin"] < 0
    b = kicad_file.load(FIXTURE)
    on = place(b, seed=0, time_s=10, physics=True, workers=1).report
    assert "margin_set" not in on and on["w_cong"] == 30.0
    stages = [t["stage"] for t in on.get("physics_trace", [])]
    assert stages[:2] == ["seed", "anneal"] and all("total_linear" in t for t in on["physics_trace"])
    off = place(kicad_file.load(FIXTURE), seed=0, time_s=10, physics=True, workers=1,
                opts=dict(place_w_cong=0, place_margin=0)).report
    assert off["margin_set"] == 0.0 and off["margin_mm"] == 0.0
    assert off["w_cong"] == 0.0


def _row_board(tmp_path, width, waive=True):
    """Four 0402 resistors (courtyards 2.6 x 2.0 mm, IPC Level C 2.3 x 1.7) chained by nets on a
    board 2 mm tall: copper-to-edge (0.3 mm) leaves one row, so the drawn courtyards need
    3 x 2.6 mm of the 7.28 mm the pads can use on a 9.4 mm board (no fit), Level C 3 x 2.3 mm."""
    import critical_fixtures as cf
    parts = [(f"R{k + 1}", "1k", "Resistor_SMD:R_0402_1005Metric", 101.0 + 0.5 * k, 101.0, 0.0,
              [("1", f"N{k}", -0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive"),
               ("2", f"N{k + 1}", 0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive")], (1.3, 1.0)) for k in range(4)]
    old = cf.PARTS, cf.SIZE
    cf.PARTS, cf.SIZE = parts, (float(width), 2.0)
    try:
        p = cf.write_board(tmp_path / f"row{width}{'w' if waive else ''}")
    finally:
        cf.PARTS, cf.SIZE = old
    if waive:
        pro = json.loads(p.with_suffix(".kicad_pro").read_text())
        pro["board"]["design_settings"]["rule_severities"] = {"courtyards_overlap": "ignore"}
        p.with_suffix(".kicad_pro").write_text(json.dumps(pro))
    return p


def test_severity_ladder_falls_back_to_level_c_when_strict_cannot_fit(tmp_path):
    """strict_then_level_c (the default): drawn courtyards cannot fit the row, so strict leaves
    placement errors; level_c places again, legal with no shorts, and is kept with an info
    severity_fallback hazard naming the parts that share courtyard margin."""
    from kae.place.pipeline import ELECTRICAL, place, placement_errors
    p = _row_board(tmp_path, 9.4)
    res = place(kicad_file.load(p), seed=0, time_s=30.0, physics=False, workers=2, board_path=str(p))
    rep = res.report
    lad = rep["severity_ladder"]
    assert rep["severity_used"] == "level_c" and res.problem.cy_shrink > 0.1
    assert lad["mode"] == "strict_then_level_c" and lad["rungs"] == 2 and lad["chosen"] == "level_c"
    assert lad["strict"]["legal"] is False and lad["strict"]["relax_bodies"] == "off" and lad["fallback"]["errors"] > 0
    errs = placement_errors(res)
    assert errs == {} and not any(errs.get(t) for t in ELECTRICAL)
    hz = [h for h in rep["hazards"] if h["code"] == "severity_fallback"]
    assert len(hz) == 1 and hz[0]["severity"] == "info" and hz[0]["evidence"]["used"] == "level_c"
    assert hz[0]["evidence"]["margin_pairs"] and set(hz[0]["objects"]) <= {"R1", "R2", "R3", "R4"}


def test_severity_ladder_keeps_strict_when_it_fits(tmp_path):
    """A row with room for the drawn courtyards: strict is legal, no fallback, no hazard."""
    from kae.place.pipeline import place, placement_errors
    p = _row_board(tmp_path, 12.0)
    res = place(kicad_file.load(p), seed=0, time_s=30.0, physics=False, workers=2, board_path=str(p))
    lad = res.report["severity_ladder"]
    assert res.report["severity_used"] == "strict" and lad["rungs"] == 1 and lad["fallback"] is None
    assert placement_errors(res) == {} and res.problem.cy_shrink == 0.0
    assert not [h for h in res.report["hazards"] if h["code"] == "severity_fallback"]


def test_severity_ladder_is_one_strict_rung_where_the_project_keeps_courtyards(tmp_path):
    """Without a courtyard waiver level_c is strict: one rung, relax_bodies as set (here the
    body relaxation is the next softening step, there is no Level C rung before it)."""
    from kae.place.pipeline import place, resolve_severity
    p = _row_board(tmp_path, 9.4, waive=False)
    b = kicad_file.load(p)
    assert resolve_severity(b, str(p)) == "strict_then_level_c"
    res = place(b, seed=0, time_s=20.0, physics=False, workers=2, board_path=str(p))
    lad = res.report["severity_ladder"]
    assert res.report["severity_used"] == "strict" and lad["rungs"] == 1 and "note" in lad
    assert res.report["relax_bodies"] == "escalate"


def test_severity_ladder_trigger_takes_kicads_verdict_and_keeps_the_better_rung(tmp_path):
    """The caller's verify (kae.cli: write + KiCad loop) judges each rung within its share of
    the time: strict's ends at 55% of it, level_c's at the end. KiCad's placer errors
    (kicad_verdict) fire the fallback even when the exact check is clean; a level_c rung that
    leaves shorts loses to a strict one that leaves only courtyard overlaps."""
    import time
    from kae.place.pipeline import LADDER_STRICT_SHARE, place
    p = _row_board(tmp_path, 12.0)
    calls = []
    verdicts = iter([{"courtyards_overlap": 2}, {"shorting_items": 1}])

    def verify(r, end):
        calls.append((r.report["severity_used"], end))
        r.report["kicad_verdict"] = dict(errors=1, by_type=next(verdicts))
        return dict(clean=False)
    t0 = time.monotonic()
    res = place(kicad_file.load(p), seed=0, time_s=60.0, physics=False, workers=2, board_path=str(p), verify=verify)
    assert [c[0] for c in calls] == ["strict", "level_c"]
    assert calls[0][1] <= t0 + LADDER_STRICT_SHARE * 60.0 + 0.5 and calls[1][1] <= t0 + 60.0 + 0.5
    lad = res.report["severity_ladder"]
    assert lad["fallback"]["by_type"] == {"courtyards_overlap": 2} and lad["fallback"]["source"] == "exact check and KiCad DRC"
    assert lad["chosen"] == "strict" and res.report["severity_used"] == "strict" and res.verified == dict(clean=False)
    hz = [h for h in res.report["hazards"] if h["code"] == "severity_fallback"]
    assert len(hz) == 1 and hz[0]["evidence"]["used"] == "strict"


def test_a_single_problem_takes_the_ladder_as_level_c(tmp_path):
    """Problem.build cannot ladder: the default mode (the joint loop's windows) is level_c."""
    import pytest
    from kae.place.pipeline import resolve_severity
    from kae.place.problem import Problem
    p = _row_board(tmp_path, 9.4)
    b = kicad_file.load(p)
    assert Problem.build(b).severity_mode == "level_c"
    assert Problem.build(b, severity="strict_then_level_c").severity_mode == "level_c"
    assert resolve_severity(b, opts={"place_severity": "strict"}) == "strict"
    with pytest.raises(ValueError):
        resolve_severity(b, opts={"place_severity": "loose"})
