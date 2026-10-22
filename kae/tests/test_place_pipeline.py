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


@pytest.mark.parametrize("arm", [[], ["--no-physics"]])
def test_place_cli_end_to_end(tmp_path, arm):
    src = _copy(tmp_path)
    out = tmp_path / "out" / "board.kicad_pcb"
    rep_path = tmp_path / "report.json"
    rc = main(["place", str(src), str(out), "--time", "45", "--seed", "1", "--writer", "sexpr",
               "--report", str(rep_path), *arm])
    rep = json.loads(rep_path.read_text())
    assert rc == 0 and rep["legal"] and rep["exact"] == []
    assert rep["physics"] is (not arm)
    assert "scorecard" in rep and rep["scorecard"]["structures"] >= 0   # both arms report physics
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
