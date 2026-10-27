# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.pour: where a net's pours would fill, and the pieces they break into."""
from pathlib import Path

import shapely

from kae.board.kicad_file import load
from kae.place import pour

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def test_a_wall_of_other_copper_splits_the_pour_and_strands_pads():
    b = load(FIXTURE)
    whole = pour.fragmentation(b)["GND"]
    assert whole["components"] == 1 and whole["needed"] == 0 and whole["pads"] >= 2
    xs = sorted(g.centroid.x for ref, num, net, lays, g, lc in pour._pads(b) if net == "GND" and "B.Cu" in lays)
    cut = (xs[0] + xs[-1]) / 2
    wall = {"B.Cu": [("SIG1", shapely.LineString([(cut, -1), (cut, 41)]).buffer(0.5))]}
    split = pour.fragmentation(b, wires=wall)["GND"]
    assert split["components"] == 2 and split["needed"] == 1 and split["stranded"] >= 1
    assert split["main_area"] < whole["main_area"]


def test_mst_wires_lay_smd_edges_on_their_side():
    b = load(FIXTURE)
    w = pour.mst_wires(b)
    assert w and all(ly.endswith(".Cu") for ly in w)
    assert all(g.area > 0 for segs in w.values() for _, g in segs)
