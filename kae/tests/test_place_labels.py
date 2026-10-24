# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.labels: board silk labels, the parts they name, and the annealer's label term."""
from pathlib import Path
from types import SimpleNamespace

import shapely

from kae.board.kicad_file import load
from kae.place import labels
from kae.place.anneal import Annealer, make_annealer
from kae.place.legalize import legalize
from kae.place.problem import Problem
from kae.place.state import State

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def test_tokens_normalize_kicad_markup_and_net_names():
    assert labels.tokens("~{RST}  +3V3|/sub/SDA, ON/OFF") == ["RST", "3V3", "SUB", "SDA", "ON", "OFF"]
    assert labels.norm("/power/VCC") == "VCC" and labels.norm("<40dB") == "40DB"


def _pad(net, pin=""):
    return SimpleNamespace(net=net, pinfunction=pin, number="1", x=0.0, y=0.0)


def _fp(ref, nets, uuid=None):
    return SimpleNamespace(ref=ref, uuid=uuid or ref, pads=[_pad(n) for n in nets])


def _label(text, x, y):
    g = shapely.box(x - 1, y - 0.5, x + 1, y + 0.5)
    return dict(text=text, tokens=labels.tokens(text), side=0, geom=g, xy=(x, y), at=(x, y))


def test_infer_names_connector_pins_switches_and_numbered_rows():
    fps = [_fp("J1", ["SDA", "SCL", "GND"]), _fp("SW1", ["EN", "VDC"]), _fp("R1", ["SDA", "X"])]
    fps += [_fp(f"D{k}", [f"LED{k}"]) for k in range(1, 4)]
    board = SimpleNamespace(footprints=fps)
    labs = [_label("SDA", 0, 0), _label("ON", 10, 0), _label("<40dB", 20, 9), _label("60dB", 20, 5),
            _label(">80dB", 20, 1), _label("1", 30, 0), _label("2", 30, 2), _label("3", 30, 4)]
    found = labels.infer(board, labs)
    by = {(a["label"], a["part"]) for a in found}
    assert (0, "J1") in by and (0, "R1") not in by            # pins of connectors only
    assert (1, "SW1") in by                                    # ON names the only switch
    rows = {a["label"]: a["part"] for a in found if a["how"].startswith("row")}
    assert rows == {2: "D1", 3: "D2", 4: "D3"}                 # numeric order, not position
    assert not any(a["label"] in (5, 6, 7) for a in found)     # the family took one row


def test_label_term_pulls_a_part_beside_its_label():
    """With w_label > 0 the annealer prices the L1 distance (beyond the dead zone) from a
    labelled part's target origin; both engines price it alike."""
    P = Problem.build(load(FIXTURE))
    st = State(P)
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    i = P.mov[0]
    p = P.parts[i]
    tx, ty = int(P.ncx * 0.8), int(P.ncy * 0.8)
    anchors = {i: ([(tx, ty)] * len(p.rots), 2, 1.0)}
    a0 = Annealer(P, st.copy(), terms=None, w_cong=0.0, labels=anchors, w_label=1.0)
    d0 = abs(a0.X[i] - tx) + abs(a0.Y[i] - ty)
    assert a0.terms_report()["labelled_parts"] == 1 and (a0.labels_off() == 1) == (d0 > 2)
    off = Annealer(P, st.copy(), terms=None, w_cong=0.0, labels=anchors, w_label=0.0)
    assert not off.labels and "label" not in off.terms_report()
    ann = make_annealer(P, st.copy(), terms=None, w_cong=0.0, labels=anchors, w_label=5.0, seed=0)
    c_fast = ann.cost(ann.lam1)
    ref = Annealer(P, st.copy(), terms=None, w_cong=0.0, labels=anchors, w_label=5.0, seed=0)
    assert abs(c_fast - ref.cost(ref.lam1)) < 1e-6
    ann.run(cpu_s=20.0, max_moves=40000)
    d1 = abs(int(ann.X[i]) - tx) + abs(int(ann.Y[i]) - ty)
    assert d1 < d0


def test_numbered_row_anchors_keep_the_row_order():
    """A numbered row's dead zone along the row is a third of its pitch (the parts keep the
    labels' order); across it, the label's half size plus d0. Only the default-on kinds when
    asked."""
    P = Problem.build(load(FIXTURE))
    p = P.parts[P.mov[0]]
    row = dict(label=0, how="row", part=p.uuid, pads=None, xy=(10.0, 10.0), half=2.0, along=1, pitch=4.0)
    pin = dict(label=1, how="pin", part=P.parts[P.mov[1]].uuid, pads=[0], xy=(20.0, 10.0), half=1.0)
    a = labels.anchors(P, [row, pin], d0=1.5)
    (tg, r, w) = a[p.i]
    assert len(tg) == len(p.rots) and r == (int(3.5 / P.g + 0.999), int(4.0 / 3.0 / P.g))
    assert set(labels.anchors(P, [row, pin], kinds=labels.DEFAULT_KINDS)) == {p.i}
