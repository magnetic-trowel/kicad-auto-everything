# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.em.mesh: a thin track whose raster cells a fine-pitch neighbour of another net already owns stays
connected (bridge_gaps), with its resistance."""
from kae.em import solve as ES
from kae.em.mesh import Layer, Mesh


def test_a_thin_track_squeezed_by_a_neighbour_stays_connected():
    m = Mesh.over(0, -2, 6, 2, 0.25, [Layer("T", 0.0, 0.035, 1)])
    m.paint_line(0, "A", [(0.2, 0.05), (5.8, 0.05)], 0.15)          # painted first: owns row 0
    # B detours through A's row (0.15 mm away, the same raster cells) between two points above it
    m.paint_line(0, "B", [(1.0, 1.0), (1.0, 0.2), (5.0, 0.2), (5.0, 1.0)], 0.15)
    assert m.bridge_gaps() >= 1
    m.terminal("a0", 0, xy=(0.2, 0.05), net="A")
    m.terminal("a1", 0, xy=(5.8, 0.05), net="A")
    m.terminal("b0", 0, xy=(1.0, 1.0), net="B")
    m.terminal("b1", 0, xy=(5.0, 1.0), net="B")
    net = ES.Network(m)
    c = {t: int(net.comp[net.term_node[t]]) for t in ("a0", "a1", "b0", "b1")}
    assert c["a0"] == c["a1"] and c["b0"] == c["b1"] and c["a0"] != c["b0"]
