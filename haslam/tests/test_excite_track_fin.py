# SPDX-FileCopyrightText: 2026 HaslamPCB contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""haslam.excite.dc.fin_factor and track_runs: heat.track prices a track's run of thin copper as a fin held at its
ends, not as IPC-2221's infinitely long track (docs/topics/physics/thermal-physics.md, 'IPC-2221/2152 as a thermal
model')."""
import math
from types import SimpleNamespace as NS

import pytest
from shapely.geometry import Point, box

from haslam.excite import dc as DC

T = 0.035


def test_a_long_run_reads_ipc():
    ipc = DC.ipc_dT(2.0, 0.127, T)
    assert DC.fin_dT(2.0, 0.127, T, True, 1000.0) == pytest.approx(ipc, rel=1e-9)
    assert DC.fin_dT(2.0, 0.127, T, True, 5.0, anchored=0) == pytest.approx(ipc, rel=1e-12)


def test_a_pin_neck_reads_cool_and_an_8mm_run_does_not():
    """0.8 mm of 0.127 mm track at 2 A into a TSSOP pad: IPC 200 K, the fin < 1 K; 8 mm: ~56 K."""
    assert DC.ipc_dT(2.0, 0.127, T) == pytest.approx(199.6, abs=0.1)
    assert DC.fin_dT(2.0, 0.127, T, True, 0.8) < 1.0
    assert DC.fin_dT(2.0, 0.127, T, True, 8.0) == pytest.approx(54.9, abs=0.5)


def test_a_short_run_is_pure_conduction():
    """L << l: the rise is q' L^2 / (8 k_Cu w t), whatever the chart's line conductance."""
    I, w, L = 2.0, 0.127e-3, 0.3e-3
    q = I * I * DC.RHO_CU / (w * T * 1e-3)
    assert DC.fin_dT(I, 0.127, T, True, L * 1e3) == pytest.approx(q * L * L / (8 * DC.K_CU * w * T * 1e-3), rel=0.01)


def test_one_held_end_reads_as_a_run_twice_as_long():
    for L in (0.5, 3.0, 10.0):
        assert DC.fin_dT(2.0, 0.127, T, True, L, anchored=1) == pytest.approx(DC.fin_dT(2.0, 0.127, T, True, 2 * L))


def _tr(a, b, w=0.127, layer="F.Cu", net="A"):
    return NS(start=a, end=b, mid=None, width=w, layer=layer, net=net)


def _pad(x, y, layer="F.Cu", net="A"):
    return [(layer, box(x - 0.2, y - 0.5, x + 0.2, y + 0.5), NS(net=net))]


def _bm(pads=(), vias=(), fills=None):
    return NS(fills=fills or {}, pads={f"P{k}": p for k, p in enumerate(pads)}, b=NS(vias=list(vias)),
              span=lambda ls: list(ls))


def test_ten_segments_in_a_line_are_one_run():
    """KiCad splits a run into segments: ten 2 mm pieces between two pads read as one 20 mm run held at both ends."""
    trs = [_tr((2.0 * k, 0.0), (2.0 * (k + 1), 0.0)) for k in range(10)]
    runs = DC.track_runs(_bm([_pad(0, 0), _pad(20, 0)]), trs, trs)
    assert all(L == pytest.approx(20.0) and h == 2 for L, h in runs)


def test_a_t_junction_joins_the_run_and_other_nets_do_not():
    trs = [_tr((0, 0), (10, 0)), _tr((5, 0), (5, 3)), _tr((0, 1), (10, 1), net="B")]
    runs = DC.track_runs(_bm(), trs, trs)
    assert runs[0] == pytest.approx((13.0, 0)) and runs[1] == pytest.approx((13.0, 0))
    assert runs[2] == pytest.approx((10.0, 0))


def test_a_run_ends_at_wider_copper_and_the_wider_track_runs_through_it():
    """A 0.127 mm neck from a pad into a 1 mm track: the neck is held at both ends; the 1 mm track's own run takes
    the neck in (no wider than it)."""
    trs = [_tr((0, 0), (0.8, 0)), _tr((0.8, 0), (10, 0), w=1.0)]
    runs = DC.track_runs(_bm([_pad(0, 0)]), trs, trs)
    assert runs[0] == pytest.approx((0.8, 2))
    assert runs[1] == pytest.approx((10.0, 1))


def test_slightly_wider_is_still_the_same_run():
    trs = [_tr((0, 0), (5, 0), w=0.127), _tr((5, 0), (10, 0), w=0.13)]
    assert DC.track_runs(_bm(), trs, trs)[0] == pytest.approx((10.0, 0))


def test_a_via_into_more_thin_track_chains_the_run_and_one_into_a_pour_holds_it():
    trs = [_tr((0, 0), (5, 0)), _tr((5, 0), (12, 0), layer="B.Cu")]
    via = NS(x=5.0, y=0.0, size=0.6, net="A", layers=("F.Cu", "B.Cu"))
    pads = [_pad(0, 0)]
    run = DC.track_runs(_bm(pads, [via]), trs, trs)
    assert run[0] == pytest.approx((12.0, 1))          # held at the pad only: through the via it is 12 mm of thin
    pour = {"A": {"B.Cu": [Point(5.0, 0.0).buffer(3.0)]}}
    held = DC.track_runs(_bm(pads, [via], fills=pour), trs[:1], trs[:1])
    assert held[0] == pytest.approx((5.0, 2))
    wide = [trs[0], _tr((5, 0), (12, 0), w=1.0, layer="B.Cu")]
    assert DC.track_runs(_bm(pads, [via]), wide, wide)[0] == pytest.approx((5.0, 2))


def test_a_via_end_chained_reads_hotter_than_held():
    """The run through a via to more thin track reads as a longer, one-held run: hotter than the same piece held."""
    held = DC.fin_dT(2.0, 0.127, T, True, 5.0, anchored=2)
    chained = DC.fin_dT(2.0, 0.127, T, True, 12.0, anchored=1)
    assert chained > 3 * held and math.isfinite(chained)


def test_tracks_meeting_on_a_pad_are_separate_runs():
    """A pad holds both tracks that meet on it: the run does not pass through it."""
    trs = [_tr((0, 0), (3, 0)), _tr((3, 0), (5, 0))]
    runs = DC.track_runs(_bm([_pad(3, 0)]), trs, trs)
    assert runs == [pytest.approx((3.0, 1)), pytest.approx((2.0, 1))]
