# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tasks limited to the copper layers a board uses, through prepare and the scorer. Needs KiCad 10."""
import re
import shutil
from pathlib import Path

import pytest

from kaebench import prepare, score, tools
from kaebench.boardfiles import board_path

FIXTURE = Path(__file__).parent / "fixtures" / "two_pads.kicad_pcb"


def _have(fn):
    try:
        fn()
        return True
    except tools.ToolError:
        return False


pytestmark = pytest.mark.skipif(not (_have(tools.kicad_cli) and _have(tools.kicad_python)), reason="KiCad 10 not installed")
VIA = '\t(via (at 115 107) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1) (uuid "44444444-4444-4444-4444-444444444447"))\n'
ZONE = ('\t(zone (net 1) (net_name "N1") (layer "In1.Cu") (uuid "55555555-5555-5555-5555-555555555555") '
        '(hatch edge 0.5) (connect_pads (clearance 0.2)) (min_thickness 0.2) (fill yes (thermal_gap 0.5) '
        '(thermal_bridge_width 0.5)) (polygon (pts (xy 112 104.5) (xy 118 104.5) (xy 118 109) (xy 112 109))))\n')


def inner_board(layers=4, extra=""):
    """two_pads with `layers` declared copper layers; extra goes in as top-level items."""
    table = "".join(f'\t\t({2 * i + 2} "In{i}.Cu" signal)\n' for i in range(1, layers - 1))
    t = FIXTURE.read_text().replace('\t\t(2 "B.Cu" signal)\n', table + '\t\t(2 "B.Cu" signal)\n')
    end = t.rstrip().rfind(")")
    return t[:end] + extra + t[end:]


def prep(tmp_path, text, name="b"):
    src = tmp_path / name / "src" / "b.kicad_pcb"
    src.parent.mkdir(parents=True)
    src.write_text(text)
    entry = dict(id=name, repo="https://example.invalid/r", pcb_path="b.kicad_pcb")
    rec = prepare.prepare_board(entry, {"kicad_pcb": str(src), "pcb_sha256": "x"}, tmp_path / name / "tasks")
    return tmp_path / name / "tasks" / name, rec


def layers_of(board):
    return re.findall(r'\(\d+ "((?:F|B|In\d+)\.Cu)"', Path(board).read_text())


def add_tracks(board, dst, extra):
    t = Path(board).read_text()
    end = t.rstrip().rfind(")")
    Path(dst).write_text(t[:end] + extra + t[end:])


def test_complete_four_layer_design_on_two_layers_becomes_two_layers(tmp_path):
    tdir, rec = prep(tmp_path, inner_board(4))
    assert rec["layer_restriction"] == dict(declared=4, used=2, copper_layers=2, forbidden=[], reason="complete-human-copper")
    for b in ("reference", "route/input", "place/input"):
        assert layers_of(board_path(tdir / b)) == ["F.Cu", "B.Cu"]
    assert rec["qualified"] and rec["roundtrip"]["route"]["ok"]


def test_output_with_copper_on_a_removed_layer_is_invalid(tmp_path):
    tdir, rec = prep(tmp_path, inner_board(4))
    seg = '\t(segment (start 112 106) (end 115 106) (width 0.25) (layer "In1.Cu") (net 1) (uuid "66666666-6666-6666-6666-666666666666"))\n'
    out = tmp_path / "o"
    out.mkdir()
    add_tracks(board_path(tdir / "reference"), out / "board.kicad_pcb", seg)
    (tmp_path / "o" / "board.kicad_pro").write_text("{}")
    s = score.score_route_task(tdir, out / "board.kicad_pcb", tmp_path / "scored", rec, allow_copy=True)
    assert not s["valid"] and not s["integrity"]["layers"]


def test_four_to_three_keeps_the_stack_and_forbids_the_empty_layer(tmp_path):
    tdir, rec = prep(tmp_path, inner_board(4, VIA + ZONE))
    assert rec["layer_restriction"]["copper_layers"] == 4
    assert rec["layer_restriction"]["forbidden"] == ["In2.Cu"]
    for b in ("reference", "route/input"):
        assert len(layers_of(board_path(tdir / b))) == 4
        assert "kae_unused_layer" in board_path(tdir / b).read_text()
    assert rec["qualified"] and rec["roundtrip"]["route"]["ok"]

    def scored(layer, name):
        seg = (f'\t(segment (start 112 106) (end 115 106) (width 0.25) (layer "{layer}") (net 1) '
               '(uuid "66666666-6666-6666-6666-666666666666"))\n')
        d = tmp_path / name
        d.mkdir()
        add_tracks(board_path(tdir / "reference"), d / "board.kicad_pcb", seg)
        return score.score_route_task(tdir, d / "board.kicad_pcb", tmp_path / f"s-{name}", rec, allow_copy=True)

    bad = scored("In2.Cu", "forbidden")
    assert bad["errors_by_type"].get("items_not_allowed", 0) >= 1 and not bad["clean"]
    ok = scored("In1.Cu", "allowed")
    assert ok["errors_by_type"].get("items_not_allowed", 0) == 0


def test_eagle_default_sixteen_layers_without_copper_becomes_two(tmp_path):
    empty = re.sub(r'\t\(segment .*\n', "", inner_board(16))
    assert "(segment" not in empty
    tdir, rec = prep(tmp_path, empty)
    assert rec["layer_restriction"]["reason"] == "eagle-16-default"
    assert layers_of(board_path(tdir / "reference")) == ["F.Cu", "B.Cu"]


def test_empty_four_layer_board_keeps_its_layers(tmp_path):
    empty = re.sub(r'\t\(segment .*\n', "", inner_board(4))
    tdir, rec = prep(tmp_path, empty)
    assert "layer_restriction" not in rec and len(layers_of(board_path(tdir / "reference"))) == 4


def test_board_with_nothing_to_change_is_untouched(tmp_path):
    src = tmp_path / "b.kicad_pcb"
    shutil.copy2(FIXTURE, src)
    ref = tmp_path / "ref"
    ref.mkdir()
    tools.run_ops("convert", src, board_path(ref))
    before = {p.name: p.read_bytes() for p in ref.iterdir()}
    assert prepare.restrict_layers(ref, dict(unconnected=0)) is None
    assert {p.name: p.read_bytes() for p in ref.iterdir()} == before  # no plan file, nothing re-saved



def test_via_only_inner_layers_are_unused(tmp_path):
    src = tmp_path / "b.kicad_pcb"
    src.write_text(inner_board(4, VIA))
    use = tools.run_ops("layer-use", src)
    assert use["inner_used"] == [] and use["routing_items"] == 7
