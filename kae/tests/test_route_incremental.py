# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.incremental against live KiCad and Freerouting (skipped when missing): only the
open connections are routed, the fixed routing comes back untouched, the run is fast."""
import shutil
from pathlib import Path

import pytest

from kae.board import pcbnew_io, sexpr
from kae.route import critical_write as W
from kae.route import drc, freerouting
from kae.route.incremental import route_open

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def _have_tools():
    try:
        freerouting.command()
        drc.kicad_cli()
        return pcbnew_io.available()
    except Exception:
        return False


pytestmark = [pytest.mark.kicad, pytest.mark.skipif(not _have_tools(), reason="no pcbnew, Freerouting or kicad-cli")]


def test_route_open_keeps_fixed_routing_and_routes_the_rest(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    W.edit(FIXTURE, board, lock="all")                      # the fixture's routing, all fixed
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(FIXTURE.with_suffix(ext), board.with_suffix(ext))
    before = {r["uuid"] for r in W.routing(board)}
    out = tmp_path / "out.kicad_pcb"
    rep = route_open(board, out, seed=3, time_s=60, log=lambda m: None)
    assert rep["status"] in ("routed", "no_session"), rep.get("error")
    assert rep["router"]["settings"]["optimizer.enabled"] == "false"
    assert rep["router"]["settings"]["autorouter.max_passes"] == "3"   # pass 1, more only while open
    after = W.routing(out)
    kept = {r["uuid"] for r in after if r["locked"]}
    assert before <= kept                                   # fixed wiring comes back as it was
    text = out.read_text()
    assert sexpr.parse(sexpr.strip_blocks(text)) is not None
    if rep["status"] == "routed":
        assert len(after) >= len(before)
    assert rep["seconds"] < 60 + 40                         # budget plus the kill grace, at most
