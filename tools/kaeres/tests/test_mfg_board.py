# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""mfg_board.py: geometry helpers on synthetic copper (needs numpy, shapely; no KiCad, no board files)."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

shapely = pytest.importorskip("shapely", minversion="2.0")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mfg_board as M  # noqa: E402


def test_read_fills_takes_layer_and_net_and_skips_keepouts():
    text = """(kicad_pcb
\t(net 3 "GND")
\t(zone
\t\t(net 3)
\t\t(net_name "GND")
\t\t(layer "F.Cu")
\t\t(filled_polygon
\t\t\t(layer "F.Cu")
\t\t\t(pts (xy 0 0) (xy 1 0) (xy 1 1))
\t\t)
\t)
\t(zone
\t\t(net 0)
\t\t(keepout (tracks not_allowed))
\t\t(filled_polygon (layer "B.Cu") (pts (xy 0 0) (xy 2 0) (xy 2 2)))
\t)
)"""
    assert M.read_fills(text) == [("F.Cu", "GND", [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])]


def _track(x0, y0, x1, y1, net="A", width=0.2, layer="F.Cu", mid=None):
    return NS(start=(x0, y0), end=(x1, y1), width=width, layer=layer, net=net, mid=mid)


def _board(tracks, vias=(), footprints=(), zones=()):
    return NS(tracks=list(tracks), vias=list(vias), footprints=list(footprints), zones=list(zones), outline=[], stackup=NS(copper=["F.Cu", "B.Cu"]),
              rules=NS(netclasses={}))


def test_spacing_counts_both_sides_and_only_other_nets():
    m = M.Model(_board([_track(0, 0, 10, 0, "A"), _track(0, 0.5, 10, 0.5, "B"), _track(0, -0.5, 10, -0.5, "A")]), [])
    ca, tt, tp = M.spacing(m, M._samples(m))
    assert tt == pytest.approx(0.3, abs=1e-6) and tp is None  # gap 0.5 minus half widths 0.2
    # A at y=0: B on one side at 0.3, A at y=-0.5 is the same net; B: A at 0.3 on one side; A at y=-0.5: B at 0.8.
    assert ca == pytest.approx(10 * M.X0 ** 2 * (2 / 0.3 + 1 / 0.8), rel=0.02)


def test_acute_junction_counts_only_sharp_same_net_corners():
    m = M.Model(_board([_track(0, 0, 10, 0, "A"), _track(10, 0, 0, 1, "A"), _track(0, 5, 10, 5, "A"), _track(10, 5, 20, 5, "A")]), [])
    n = M.acute_per_m(m, 10000.0)
    assert n == pytest.approx(0.1)      # one sharp junction per 10 m


def test_width_uses_the_boards_own_classes_only():
    assert M.Q(0) == pytest.approx(0.5)
    assert M.arc_pts((0, 0), (1, 1), (2, 0))[-1] == pytest.approx((2.0, 0.0), abs=1e-6)
