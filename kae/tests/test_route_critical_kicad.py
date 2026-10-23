# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.critical against KiCad's DRC (the referee): the critical copper of the
synthetic board (critical_fixtures) and a joint module optimization of it add no error;
skipped without KiCad."""
import pytest

import critical_fixtures as F
from kae.board import pcbnew_io
from kae.route import critical_write as W
from kae.route import drc

pytestmark = [pytest.mark.kicad,
              pytest.mark.skipif(not pcbnew_io.available(), reason="no Python with pcbnew")]


def _errors(board, tmp):
    rep = drc.run(board, tmp / f"{board.stem}.drc.json")
    return drc.errors(rep), rep


def test_critical_copper_adds_no_drc_error(tmp_path):
    from kae.route import critical
    src = F.write_board(tmp_path / "in")
    base, _ = _errors(src, tmp_path)
    out = tmp_path / "out" / "board.kicad_pcb"
    out.parent.mkdir()
    rep, s = critical.route_critical(src, out, log=lambda *a: None)
    assert rep["tracks"] > 5 and rep["vias"] > 0
    errs, d = _errors(out, tmp_path)
    mine = {r["uuid"] for r in W.routing(out) if r["locked"]}
    assert not [v for v in errs if {i.get("uuid") for i in v.get("items", [])} & mine]
    assert len(errs) <= len(base), [v["type"] for v in errs]
    # fewer unconnected items than the bare input: the critical copper connects
    assert len(d.get("unconnected_items", [])) < len(drc.run(src, tmp_path / "b.json").get("unconnected_items", []))


def test_joint_poses_and_copper_pass_drc(tmp_path):
    from kae.board.kicad_file import load
    from kae.route.critical import write_joint
    from kae.route.critical_joint import optimize_modules
    src = F.write_board(tmp_path / "in")
    b = load(src)
    from kae.circuit.brief import build
    poses, copper, rep = optimize_modules(b, build(b), terms=None, locked=set(), time_s=120)
    (tmp_path / "out").mkdir()
    out = write_joint(src, tmp_path / "out" / "board.kicad_pcb", poses, copper)
    errs, _ = _errors(out, tmp_path)
    assert not errs, [(v["type"], v["description"]) for v in errs]


def test_run_without_bridge_writes_input_plus_locked_routing(tmp_path):
    from kae.route import critical
    src = F.write_board(tmp_path / "in")
    out = tmp_path / "out" / "board.kicad_pcb"
    rep = critical.run(src, out, time_s=120, bridge=False, log=lambda *a: None)
    assert rep["status"] == "ok" and rep["critical"]["tracks"] > 5
    text = out.read_text()
    assert W.GUARD_PREFIX not in text                      # guards never reach an output
    assert text.count("(footprint") == src.read_text().count("(footprint")
    items = W.routing(out)
    assert len(items) == rep["critical"]["tracks"] + rep["critical"]["vias"] and all(r["locked"] for r in items)
