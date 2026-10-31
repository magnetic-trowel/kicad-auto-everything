# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.board.kicad_file against pcbnew's view of the fixture (stored golden data, so no
KiCad is needed), plus the KiCad 6-9 dialect and loader conventions.

The fixture (data/board/) is our own 4-layer board: an asymmetric 3-pad part at 0, 90 and
30 degrees on the front and at 90 and 210 degrees on the back, a locked copy, an
off-board copy, a circle courtyard, a part with courtyards on both sides, a part without
a courtyard, a footprint with an Edge.Cuts slot, a footprint keepout, board keepouts,
a pour with a hole, tracks, an arc, through and blind vias, netclass patterns.
pcbnew 10.0.7 wrote it (poses through kae.board.pcbnew_io.write_poses) and produced
fixture.pcbnew.json (pcbnew_io.extract).
"""
import json
import math
import re
import shutil
from pathlib import Path

import pytest

from kae.board import kicad_file, pcbnew_io, transform

DATA = Path(__file__).parent / "data" / "board"
FIXTURE = DATA / "fixture.kicad_pcb"


@pytest.fixture(scope="module")
def board():
    return kicad_file.load(FIXTURE)


@pytest.fixture(scope="module")
def golden():
    return json.loads((DATA / "fixture.pcbnew.json").read_text())


def test_matches_pcbnew_golden(board, golden):
    rep = pcbnew_io.verify(FIXTURE, board=board, data=golden)
    assert rep["footprints"] == 12 and rep["pads"] == 28
    assert not rep["missing_fp"] and not rep["extra_fp"] and not rep["pad_count_mismatch"]
    assert rep["pose_err"] < 1e-9 and rep["rot_err"] < 1e-9
    assert not rep["side_mismatch"] and not rep["locked_mismatch"]
    assert rep["pad_err"] < 1e-6            # integer-nm rounding at 30/45/210 degrees
    assert rep["pad_err_loader"] < 1e-6 and rep["pad_err_vec"] < 1e-6
    assert rep["pad_angle_err"] < 1e-6
    assert rep["net_mismatch"] == rep["kind_mismatch"] == rep["layer_mismatch"] == 0
    cy = rep["courtyard"]
    assert cy["missing"] == cy["extra"] == 0
    assert cy["max_straight"] < 1e-5         # vs pcbnew's cache deflated by max_error
    assert cy["max_arcs"] < 0.006            # KiCad polygonizes arcs to 5 um
    assert rep["outline"]["ours"] == rep["outline"]["pcbnew"] == 1
    assert rep["outline"]["hausdorff"] < 0.006 and rep["outline"]["area_xor"] < 0.05
    assert rep["rules_diff"] == {} and rep["netclass_diff"] == {} and not rep["nets_missing"]
    assert rep["copper_diff"] is None and rep["thickness_diff"] < 1e-9


def test_footprints(board):
    f = {fp.ref: fp for fp in board.footprints}
    assert (f["U4"].side, f["U4"].rot) == ("B", 90.0) and (f["U5"].side, f["U5"].rot) == ("B", 210.0)
    assert f["U6"].locked and not f["U1"].locked
    assert not f["U7"].on_board and all(fp.on_board for r, fp in f.items() if r != "U7")
    assert f["U1"].fields["MPN"] == "KAE-ASYM-3" and f["U1"].value == "ASYM"
    assert f["U1"].attrs == ["through_hole"] and "board_only" in f["S1"].attrs
    assert f["U1"].path.startswith("/") and f["U1"].sheet == "/"
    # library frame: every copy of a part has the same local pads and courtyard
    for r in ("U2", "U3", "U4", "U5", "U6", "U7"):
        for p, q in zip(f[r].pads, f["U1"].pads):
            assert abs(p.lx - q.lx) < 2e-6 and abs(p.ly - q.ly) < 2e-6
            d = (p.lrot - q.lrot) % 360
            assert min(d, 360 - d) < 1e-6
        assert f[r].courtyard[0].equals_exact(f["U1"].courtyard[0], 2e-6) or \
            f[r].courtyard[0].normalize().equals_exact(f["U1"].courtyard[0].normalize(), 2e-6)
    p1 = f["U1"].pads
    assert [(p.number, p.lx, p.ly, p.lrot) for p in p1] == [("1", -1.5, -0.8, 0.0), ("2", 1.2, 0.0, 90.0),
                                                           ("3", 0.0, 1.3, 0.0)]
    assert p1[2].drill == 0.5 and p1[2].kind == "thru_hole" and p1[1].rratio == 0.25
    assert p1[2].layers[:4] == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    assert set(f["U4"].pads[0].layers) == {"B.Cu", "B.Paste", "B.Mask"}
    assert p1[0].pinfunction == "IN" and p1[0].pintype == "input" and p1[0].net == "SIG1"
    j = f["J1"].pads[1]
    assert j.slot == (0.8, 1.2) and j.drill == 0.8
    # courtyards: J1 has both sides; R1 and S1 fall back to a body box
    assert f["J1"].courtyard and f["J1"].courtyard_back and not f["U1"].courtyard_back
    assert not f["R1"].courtyard and f["R1"].body[0].bounds == pytest.approx((-1.2, -0.5, 1.2, 0.5))
    assert not f["S1"].courtyard and f["S1"].body and f["S1"].edge_cuts
    assert f["Y1"].courtyard[0].area == pytest.approx(3.14159 * 1.5 ** 2, rel=2e-3)  # 1 um chords


def test_board_level(board):
    b = board
    assert b.version == 20260206
    assert len(b.outline) == 1 and len(b.outline[0].interiors) == 2   # circle cut-out + S1's slot
    su = b.stackup
    assert su.copper == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"] and su.source == "file"
    assert su.cu_thickness == [0.035, 0.0175, 0.0175, 0.035]
    assert su.gaps == pytest.approx([0.2, 1.065, 0.2]) and su.er == pytest.approx([4.3, 4.6, 4.3])
    r = b.rules
    assert (r.clearance, r.track_min, r.via_min, r.edge_clearance, r.hole_clearance) == (0.15, 0.13, 0.45, 0.3, 0.25)
    assert r.track_widths == [0.25, 0.5] and r.via_sizes == [(0.6, 0.3)]
    assert b.nets["SIG3"].netclass == "Power,HS,Default"   # assignment + pattern, KiCad's naming
    assert b.nets["VCC_IO"].netclass == "Power,Default" and b.nets["GND"].netclass == "Default"
    assert r.netclasses["Power,HS,Default"].track_width == 0.5      # merged by priority
    assert r.netclasses["HS,Default"].via_diameter == 0.6
    assert [c["name"] for c in r.custom] == ["pwr_clearance", "hs_width"]
    assert r.custom[1]["constraints"][0] == dict(type="track_width", min=0.15, opt=0.2, max=0.254)
    assert ("U1", "1") in b.nets["SIG1"].pads
    ko = {k.name: k for k in b.keepouts}
    assert ko["no_tracks"].tracks and ko["no_tracks"].footprints and not ko["no_tracks"].pads
    assert ko["no_tracks"].layers == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    ant = ko["ant_keepout"]
    fp = {f.uuid: f for f in b.footprints}[ant.footprint]
    assert fp.ref == "AE1"     # footprint keepouts are stored in board coordinates
    assert ant.outline.bounds == pytest.approx((48, 19, 51, 23))
    z = b.zones[0]
    assert (z.name, z.net, z.layers, z.priority, z.clearance) == ("gnd_pour", "GND", ["B.Cu"], 1, 0.3)
    assert len(z.outline.interiors) == 1
    assert {(t.layer, t.mid is not None) for t in b.tracks} == {("F.Cu", False), ("In1.Cu", True)}
    v = {x.type: x for x in b.vias}
    assert v["through"].layers == su.copper and v["blind"].layers == ["F.Cu", "In1.Cu", "In2.Cu"]
    assert not b.warnings


def _to_kicad8(text):
    """The fixture in the KiCad 8 dialect: net table, numeric nets, `locked` atom."""
    names = []
    for m in re.finditer(r'\(net "([^"]*)"\)', text):
        if m.group(1) and m.group(1) not in names:
            names.append(m.group(1))
    code = {n: i + 1 for i, n in enumerate(names)}
    text = text.replace("(version 20260206)", "(version 20240108)").replace('"10.0"', '"8.0"')
    text = re.sub(r'\t\(zone\n\t\t\(net "([^"]*)"\)',
                  lambda m: f'\t(zone\n\t\t(net {code[m.group(1)]})\n\t\t(net_name "{m.group(1)}")', text)
    text = re.sub(r'\n\t\t\t\(net "([^"]*)"\)', lambda m: f'\n\t\t\t(net {code[m.group(1)]} "{m.group(1)}")', text)
    text = re.sub(r'\n\t\t\(net "([^"]*)"\)', lambda m: f"\n\t\t(net {code[m.group(1)]})", text)
    table = '\t(net 0 "")\n' + "".join(f'\t(net {c} "{n}")\n' for n, c in code.items())
    i = text.index("\n\t(footprint")
    text = text[:i + 1] + table + text[i + 1:]
    return re.sub(r'\t\(footprint ("[^"]*")\n\t\t\(locked yes\)', r"\t(footprint \1 locked", text)


def test_kicad8_dialect(tmp_path, board):
    p = tmp_path / "k8.kicad_pcb"
    p.write_text(_to_kicad8(FIXTURE.read_text()))
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(FIXTURE.with_suffix(ext), p.with_suffix(ext))
    b8 = kicad_file.load(p)
    assert b8.version == 20240108
    assert [f.ref for f in b8.footprints] == [f.ref for f in board.footprints]
    assert [f.locked for f in b8.footprints] == [f.locked for f in board.footprints]
    for f8, f in zip(b8.footprints, board.footprints):
        assert [(q.net, q.x, q.y) for q in f8.pads] == [(q.net, q.x, q.y) for q in f.pads]
    assert {n: x.netclass for n, x in b8.nets.items()} == {n: x.netclass for n, x in board.nets.items()}
    assert [t.net for t in b8.tracks] == [t.net for t in board.tracks]
    assert [z.net for z in b8.zones] == [z.net for z in board.zones]


def test_legacy_reference_and_tstamp(tmp_path):
    t = FIXTURE.read_text()
    m = re.search(r'\(footprint "[^"]*"\n\t\t\(layer "[^"]*"\)\n\t\t\(uuid "([^"]*)"\)', t)
    ref = re.search(r'\(property "Reference" "([^"]*)"', t[m.start():]).group(1)
    t = t.replace(f'(property "Reference" "{ref}"', f'(fp_text reference "{ref}"', 1)
    t = t.replace(f'(uuid "{m.group(1)}")', '(tstamp "56d0a5bf")', 1)   # KiCad 5 style
    p = tmp_path / "old.kicad_pcb"
    p.write_text(t)
    b = kicad_file.load(p, rules=False)
    f = b.footprints[0]
    assert f.ref == ref and f.uuid == "00000000-0000-0000-0000-000056d0a5bf"


def test_uuid_synthesis(tmp_path):
    t = FIXTURE.read_text()
    first_uuid = re.search(r'\(footprint "[^"]*"\n\t\t\(layer "[^"]*"\)\n\t\t\(uuid "([^"]*)"\)', t).group(1)
    t2 = t.replace(f'\t\t(uuid "{first_uuid}")\n', "", 1)       # first footprint: no uuid
    p = tmp_path / "nouuid.kicad_pcb"
    p.write_text(t2)
    b1, b2 = kicad_file.load(p, rules=False), kicad_file.load(p, rules=False)
    f = b1.footprints[0]
    assert "uuid_synthesized" in f.flags and f.uuid == b2.footprints[0].uuid   # stable
    assert f.uuid == kicad_file.synth_uuid(f.lib_id, f.x, f.y, f.rot, f.side, 0)
    # a repeated uuid: the later footprint gets a synthesized key
    second = re.findall(r'\(footprint "[^"]*"\n\t\t\(layer "[^"]*"\)\n\t\t\(uuid "([^"]*)"\)', t)[1]
    p.write_text(t.replace(second, first_uuid))
    b3 = kicad_file.load(p, rules=False)
    assert len({x.uuid for x in b3.footprints}) == len(b3.footprints)
    assert "uuid_duplicate" in b3.footprints[1].flags


def test_staging_detection_uses_outline(board):
    # U7 sits right of the board, like kaebench's place-task staging area
    u7 = next(f for f in board.footprints if f.ref == "U7")
    minx = min(c[0] for p in transform.courtyard(u7) for c in p.exterior.coords)
    assert minx > max(p.bounds[2] for p in board.outline)
    assert not u7.on_board


def test_rule_severities_come_from_the_project(tmp_path):
    """Rules.severities holds the .kicad_pro DRC severities, so consumers (placement legality,
    the router) judge a check the way the project's own DRC does."""
    p = tmp_path / "sev.kicad_pcb"
    shutil.copy(FIXTURE, p)
    pro = json.loads(FIXTURE.with_suffix(".kicad_pro").read_text())
    ds = pro.setdefault("board", {}).setdefault("design_settings", {})
    ds["rule_severities"] = {"courtyards_overlap": "warning", "pth_inside_courtyard": "ignore",
                             "solder_mask_bridge": "error", "bogus_check": "fatal"}
    p.with_suffix(".kicad_pro").write_text(json.dumps(pro))
    r = kicad_file.load(p).rules
    assert r.severity("courtyards_overlap") == "warning"
    assert r.severity("pth_inside_courtyard") == "ignore"
    assert r.severity("solder_mask_bridge") == "error"
    assert "bogus_check" not in r.severities              # only KiCad's three levels are kept
    assert r.severity("missing_in_project", default="warning") == "warning"
    assert type(r).from_dict(r.to_dict()).severities == r.severities


def test_footprint_copper_and_mask_graphics(tmp_path):
    """Footprint.graphics holds copper and mask graphics (with stroke widths) per library layer,
    so placement legality can see logos and mask apertures that KiCad's DRC sees."""
    txt = FIXTURE.read_text()
    anchor = '(uuid "00000000-0000-4000-8000-000000000011")\n\t\t(at 10 10)'
    assert txt.count(anchor) == 1
    extra = ('\n\t\t(fp_rect (start -0.5 -1) (end 0.5 1) (stroke (width 0.1) (type solid)) (fill solid) (layer "F.Mask"))'
             '\n\t\t(fp_line (start 2 0) (end 5 0) (stroke (width 0.2) (type solid)) (layer "F.Cu"))'
             '\n\t\t(fp_circle (center 0 4) (end 1 4) (stroke (width 0.2) (type solid)) (fill none) (layer "F.Cu"))')
    p = tmp_path / "gfx.kicad_pcb"
    p.write_text(txt.replace(anchor, anchor + extra))
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(FIXTURE.with_suffix(ext), p.with_suffix(ext))
    u1 = next(f for f in kicad_file.load(p).footprints if f.ref == "U1")
    mask = u1.graphics["F.Mask"]
    assert len(mask) == 1 and abs(mask[0].area - (1.1 * 2.1 - 0.05 ** 2 * (4 - math.pi))) < 1e-3
    cu = sorted(u1.graphics["F.Cu"], key=lambda g: g.area)
    assert len(cu) == 2
    assert abs(cu[0].area - (3 * 0.2 + math.pi * 0.1 ** 2)) < 2e-3          # stroked line, round caps
    assert abs(cu[1].area - math.pi * ((1.1 ** 2) - (0.9 ** 2))) < 5e-3      # unfilled circle: a ring
    assert "B.Cu" not in u1.graphics
    rt = type(u1).from_dict(u1.to_dict())
    assert abs(rt.graphics["F.Mask"][0].area - mask[0].area) < 1e-9


def test_pad_clearance_override(tmp_path):
    """Pad.clearance is the pad's own (clearance …), else its footprint's, else 0: DRC uses the
    larger of it and the netclass clearance, so legality must see it."""
    txt = FIXTURE.read_text()
    anchor = '(uuid "00000000-0000-4000-8000-000000000011")\n\t\t(at 10 10)'
    pad1 = '\t\t(pad "1" smd rect\n'
    i = txt.index(anchor)
    j = txt.index(pad1, i)
    txt = txt[:j] + pad1 + '\t\t\t(clearance 0.5)\n' + txt[j + len(pad1):]
    txt = txt.replace(anchor, anchor + '\n\t\t(clearance 0.3)')
    p = tmp_path / "clr.kicad_pcb"
    p.write_text(txt)
    b = kicad_file.load(p, rules=False)
    u1 = next(f for f in b.footprints if f.ref == "U1")
    by = {q.number: q.clearance for q in u1.pads}
    assert by["1"] == 0.5 and by["2"] == 0.3 and by["3"] == 0.3
    others = [q.clearance for f in b.footprints if f.ref != "U1" for q in f.pads]
    assert others and set(others) == {0.0}
    assert type(u1).from_dict(u1.to_dict()).pads[0].clearance == 0.5


def test_board_copper_and_mask_graphics(tmp_path):
    """Board.graphics holds board-level copper, mask and silkscreen graphics (gr_* with stroke
    widths, gr_text as its box; silk text apart as '<layer>:text') per layer, board frame;
    Edge.Cuts stays out."""
    txt = FIXTURE.read_text().rstrip()
    assert txt.endswith(")")
    extra = ('\t(gr_line (start 1 1) (end 4 1) (stroke (width 0.2) (type solid)) (layer "F.Cu"))\n'
             '\t(gr_poly (pts (xy 0 0) (xy 1 0) (xy 1 1) (xy 0 1)) (stroke (width 0) (type solid)) (layer "B.Mask"))\n'
             '\t(gr_text "AB" (at 20 20 90) (layer "B.Cu") (effects (font (size 1 0.8) (thickness 0.1)) (justify mirror)))\n'
             '\t(gr_line (start 1 1) (end 4 1) (stroke (width 0.2) (type solid)) (layer "F.SilkS"))\n')
    p = tmp_path / "bgfx.kicad_pcb"
    p.write_text(txt[:-1] + extra + ")\n")
    g = kicad_file.load(p, rules=False).graphics
    assert set(g) == {"F.Cu", "B.Mask", "B.Cu", "F.SilkS"}
    assert abs(g["F.SilkS"][0].area - g["F.Cu"][0].area) < 1e-9          # the same line on silk
    assert abs(g["F.Cu"][0].area - (3 * 0.2 + math.pi * 0.1 ** 2)) < 2e-3
    assert abs(g["B.Mask"][0].area - 1.0) < 1e-9                       # gr_poly fills by default
    x0, y0, x1, y1 = g["B.Cu"][0].bounds                               # 2 chars × 0.8 wide, rotated 90°
    assert abs((x1 - x0) - 1.1) < 1e-6 and abs((y1 - y0) - 1.7) < 1e-6
    assert abs((x0 + x1) / 2 - 20) < 1e-6 and abs((y0 + y1) / 2 - 20) < 1e-6
    from kae.board.model import Board
    b = kicad_file.load(p, rules=False)
    assert abs(Board.from_dict(b.to_dict()).graphics["B.Cu"][0].area - g["B.Cu"][0].area) < 1e-9


def test_footprint_edges_close_an_open_outline(tmp_path):
    """Board-level Edge.Cuts left open, closed by a footprint's own Edge.Cuts (an RJ45 notch),
    with a small closed cut-out elsewhere: the outline is the whole board, not the cut-out
    (piecol cm5-minima: a 19 mm2 fragment left every part off the board)."""
    def ln(a, b, c, d, fp=False):
        k = "fp_line" if fp else "gr_line"
        return f'\t({k} (start {a} {b}) (end {c} {d}) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts"))\n'
    # 40 x 30 board; the top edge leaves a gap from x=10 to x=20 that the footprint closes
    body = (ln(0, 0, 10, 0) + ln(20, 0, 40, 0) + ln(40, 0, 40, 30) + ln(40, 30, 0, 30) + ln(0, 30, 0, 0)
            # a closed 2 x 2 cut-out inside
            + ln(30, 20, 32, 20) + ln(32, 20, 32, 22) + ln(32, 22, 30, 22) + ln(30, 22, 30, 20))
    fp = ('\t(footprint "notch" (layer "F.Cu") (uuid "00000000-0000-0000-0000-0000000000aa") (at 15 0)\n'
          '\t\t(property "Reference" "T1" (at 0 0) (layer "F.SilkS"))\n'
          + ln(-5, 0, -5, 5, True).replace("\t(", "\t\t(") + ln(-5, 5, 5, 5, True).replace("\t(", "\t\t(")
          + ln(5, 5, 5, 0, True).replace("\t(", "\t\t(") + '\t)\n')
    p = tmp_path / "notch.kicad_pcb"
    p.write_text('(kicad_pcb (version 20240108) (generator "test")\n' + body + fp + ")\n")
    b = kicad_file.load(p, rules=False)
    assert len(b.outline) == 1
    assert abs(b.outline[0].area - (40 * 30 - 10 * 5 - 4)) < 1e-6
    assert b.footprints[0].on_board
