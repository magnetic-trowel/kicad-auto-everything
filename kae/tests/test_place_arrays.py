# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.arrays: LED matrices and series buses from the netlist; rigid macros in the annealer."""
from types import SimpleNamespace as NS

from kae.place import arrays as A


def pad(number, net):
    return NS(number=number, net=net, drill=0.0)


def led(ref, row, col, lib="LED:RGB"):
    return NS(uuid=ref, ref=ref, lib_id=lib, pads=[pad("1", f"ROW{row}"), pad("2", f"COLR{col}"), pad("3", f"COLG{col}"), pad("4", f"COLB{col}")])


def test_matrix_found_with_rows_and_columns():
    fps = [led(f"D{(r * 12) + c + 1}", r, c) for r in range(10) for c in range(12)]
    kinds = {}
    groups = A.matrices(fps, kinds)
    assert len(groups) == 1
    g = groups[0]
    assert {g.rows, g.cols} == {10, 12} and len(g.cells) == 120
    assert set(g.cells.values()) == {(r, c) for r in range(g.rows) for c in range(g.cols)}


def test_matrix_needs_a_product_of_signal_nets():
    # a shared power rail on one pin: the other pin alone is not a matrix
    fps = [NS(uuid=f"R{i}", ref=f"R{i}", lib_id="R:0402", pads=[pad("1", "VCC"), pad("2", f"N{i}")]) for i in range(20)]
    assert A.matrices(fps, {"VCC": "power"}) == []


def test_sparse_grid_below_fill_is_rejected():
    fps = [led(f"D{i}", i, i) for i in range(20)]   # a diagonal: 20 rows x 20 cols, fill 0.05
    assert A.matrices(fps, {}) == []


def series(i, a="U1", b="U2", lib="R:0402"):
    n1, n2 = f"A{i}", f"B{i}"
    return NS(uuid=f"R{i}", ref=f"R{i}", lib_id=lib, pads=[pad("1", n1), pad("2", n2)]), n1, n2


def test_bus_found_between_two_parts():
    parts = [series(i) for i in range(8)]
    fps = [p[0] for p in parts] + [
        NS(uuid="U1", ref="U1", lib_id="BGA", pads=[pad(str(i + 1), parts[i][1]) for i in range(8)]),
        NS(uuid="U2", ref="U2", lib_id="BGA2", pads=[pad(str(i + 1), parts[i][2]) for i in range(8)])]
    groups = A.buses(fps, {})
    assert len(groups) == 1 and groups[0].cols == 8 and groups[0].rows == 1


def test_bus_excludes_parts_with_a_third_connection():
    parts = [series(i) for i in range(8)]
    fps = [p[0] for p in parts] + [
        NS(uuid="U1", ref="U1", lib_id="BGA", pads=[pad(str(i + 1), parts[i][1]) for i in range(8)]),
        NS(uuid="U2", ref="U2", lib_id="BGA2", pads=[pad(str(i + 1), parts[i][2]) for i in range(8)]),
        NS(uuid="TP1", ref="TP1", lib_id="TP", pads=[pad("1", parts[0][1])])]   # a third pad on one net: that one drops out
    groups = A.buses(fps, {})
    assert len(groups) == 1 and groups[0].cols == 7


def test_bus_to_a_fixed_part_found_when_all_parts_give_pins():
    # the far end (a connector) is fixed: members are the movable parts, ends come from every part
    parts = [series(i) for i in range(8)]
    u1 = NS(uuid="U1", ref="U1", lib_id="BGA", pads=[pad(str(i + 1), parts[i][1]) for i in range(8)])
    j1 = NS(uuid="J1", ref="J1", lib_id="CONN", pads=[pad(str(i + 1), parts[i][2]) for i in range(8)])
    movable = [p[0] for p in parts] + [u1]
    assert A.buses(movable, {}) == []
    groups = A.buses(movable, {}, pin_fps=movable + [j1])
    assert len(groups) == 1 and groups[0].cols == 8 and set(groups[0].cells) == {f"R{i}" for i in range(8)}
