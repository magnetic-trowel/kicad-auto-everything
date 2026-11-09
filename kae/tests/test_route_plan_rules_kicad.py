# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Born-right critical copper against KiCad's DRC: kae.route.critical on the synthetic board
(critical_fixtures) with rule-D pad ends adds no error and reaches pads by rule D; skipped
without KiCad."""
import pytest

import critical_fixtures as F
from kae.board import pcbnew_io
from kae.route import critical_write as W
from kae.route import drc

pytestmark = [pytest.mark.kicad,
              pytest.mark.skipif(not pcbnew_io.available(), reason="no Python with pcbnew")]


def test_critical_copper_born_right_passes_drc(tmp_path):
    from kae.route import critical
    src = F.write_board(tmp_path / "in")
    base = drc.errors(drc.run(src, tmp_path / "base.drc.json"))
    out = tmp_path / "out" / "board.kicad_pcb"
    out.parent.mkdir()
    rep, s = critical.route_critical(src, out, log=lambda *a: None)
    ent = rep["router"]["entries"]
    assert sum(v for k, v in ent.items() if k != "centre") > 0, ent       # rule D ends were drawn
    errs = drc.errors(drc.run(out, tmp_path / "out.drc.json"))
    mine = {r["uuid"] for r in W.routing(out) if r["locked"]}
    assert not [v for v in errs if {i.get("uuid") for i in v.get("items", [])} & mine], \
        [(v["type"], v["description"]) for v in errs]
    assert len(errs) <= len(base)
