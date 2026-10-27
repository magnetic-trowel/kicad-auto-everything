# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.board.sexpr and kae.board.model: parsing, block stripping, JSON round trip."""
import json
from pathlib import Path

from kae.board import kicad_file, sexpr
from kae.board.model import Board

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def test_parse_nested_strings_and_escapes():
    t = sexpr.parse('(a (b "x y" 1.5) (c "q\\"uote" "back\\\\slash" "") d)')
    assert t == ["a", ["b", "x y", "1.5"], ["c", 'q"uote', "back\\slash", ""], "d"]
    assert sexpr.first(t, "b") == ["b", "x y", "1.5"]
    assert sexpr.value(t, "b") == "x y"
    assert sexpr.kids(t, "zz") == []


def test_parse_parens_inside_strings():
    t = sexpr.parse('(p "a(b)c" (q ")"))')
    assert t == ["p", "a(b)c", ["q", ")"]]


def test_flag_forms():
    assert sexpr.flag(["fp", "lib", "locked"], "locked")
    assert sexpr.flag(["fp", ["locked", "yes"]], "locked")
    assert sexpr.flag(["fp", ["locked"]], "locked")
    assert not sexpr.flag(["fp", ["locked", "no"]], "locked")
    assert not sexpr.flag(["fp", "lib"], "locked")


def test_strip_blocks_pretty_and_single_line():
    pretty = ('(kicad_pcb\n\t(zone\n\t\t(net "GND")\n\t\t(filled_polygon\n\t\t\t(layer "F.Cu")\n'
              '\t\t\t(pts\n\t\t\t\t(xy 0 0) (xy 1 0) (xy 1 1)\n\t\t\t)\n\t\t)\n\t\t(polygon (pts (xy 0 0)))\n'
              '\t)\n\t(embedded_files\n\t\t(file (name "a(b).ttf") (data |abc|))\n\t)\n)\n')
    t = sexpr.parse(sexpr.strip_blocks(pretty))
    z = sexpr.first(t, "zone")
    assert sexpr.first(z, "filled_polygon") is None and sexpr.first(z, "polygon") is not None
    assert sexpr.first(t, "embedded_files") is None
    one_line = '(kicad_pcb (zone (filled_polygon (layer "F.Cu") (pts (xy 0 0))) (polygon (pts (xy 1 1)))))'
    t = sexpr.parse(sexpr.strip_blocks(one_line))
    assert t == ["kicad_pcb", ["zone", ["polygon", ["pts", ["xy", "1", "1"]]]]]


def test_board_json_round_trip():
    b = kicad_file.load(FIXTURE)
    d = json.loads(json.dumps(b.to_dict()))
    b2 = Board.from_dict(d)
    assert b2 == b
    assert b2.footprints[0].pads[0] == b.footprints[0].pads[0]
    assert b2.outline[0].equals(b.outline[0]) and len(b2.outline[0].interiors) == len(b.outline[0].interiors)
    assert isinstance(b2.footprints[0].pads[0].size, tuple)
    # tolerant of fields from a newer writer
    d["footprints"][0]["new_field"] = 1
    d["new_board_field"] = 2
    assert Board.from_dict(d).footprints[0].ref == b.footprints[0].ref
