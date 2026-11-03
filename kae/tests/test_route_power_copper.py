# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The pure rules of kae.route.power_copper: width choice, spacing, runs, via candidates, net classes."""
import math

import numpy as np

import pytest
from shapely.geometry import Point, box
from shapely.ops import unary_union

from kae.route import power_copper as pc


def test_ipc_width_monotone_and_known_point():
    # IPC-2221, 1 A, 10 K, 1 oz external: about 0.30 mm (12 mil)
    assert 0.27 < pc.ipc_width(1.0) < 0.33
    assert pc.ipc_width(2.0) > pc.ipc_width(1.0)
    assert pc.ipc_width(1.0, external=False) > pc.ipc_width(1.0)
    assert pc.ipc_width(0.0) == 0.0


def test_width_ladder_never_narrows():
    assert pc.width_ladder(0.25, 1.0) == [1.0, 0.8, 0.6, 0.5, 0.4, 0.3]
    assert pc.width_ladder(0.5, 1.0) == [1.0, 0.8, 0.6]
    assert pc.width_ladder(0.25, 0.55) == [0.5, 0.4, 0.3]
    assert pc.width_ladder(1.2, 1.0) == []          # already wider than the cap: left alone
    assert pc.width_ladder(1.0, 1.0) == []


def test_victim_gap_from_crosstalk_budget():
    # K = 1/(1+(D/h)^2): K 5% at h 0.2 mm -> D = 0.2*sqrt(19) = 0.87 mm
    assert pc.victim_gap(0.2, 0.05, 0.0, 10.0) == pytest.approx(0.2 * math.sqrt(19))
    k = 1.0 / (1.0 + (pc.victim_gap(0.3, 0.02, 0, 10) / 0.3) ** 2)
    assert k == pytest.approx(0.02)
    assert pc.victim_gap(1.5, 0.05, 0.5, 2.0) == 2.0       # 2-layer board: the cap
    assert pc.victim_gap(0.01, 0.05, 0.5, 2.0) == 0.5      # never below the floor


def test_signal_gap_beyond_clearance():
    assert pc.signal_gap(0.2, 0.0) == pytest.approx(0.4)    # pads: twice the clearance
    assert pc.signal_gap(0.15, 0.25) == pytest.approx(0.5)  # 3W centre to centre: 2x the signal's width
    assert pc.signal_gap(0.3, 0.1, clr_mult=1.0, w_mult=0.0) == pytest.approx(0.3)


def test_runs_take_minimum_and_merge_short():
    xs = [i * 0.1 for i in range(31)]                       # 3 mm track
    w = [1.0] * 31
    assert pc.runs(w, xs, 0.25, 1.0) == [(0.0, pytest.approx(3.0), 1.0)]
    # a 0.3 mm pinch in the middle: three runs, the pinch at the original width... widened
    # neighbours are 1.4 mm long, so they stay; the pinch is kept narrow
    w2 = [1.0] * 14 + [0.25] * 3 + [1.0] * 14
    r = pc.runs(w2, xs, 0.25, 1.0)
    assert [x[2] for x in r] == [1.0, 0.25, 1.0]
    assert r[0][0] == 0.0 and r[-1][1] == pytest.approx(3.0)
    for (a0, a1, _), (b0, b1, _) in zip(r, r[1:]):
        assert a1 == pytest.approx(b0)                      # pieces join end to end
    # a short wide run between narrow ones is lowered, never kept wider than its samples
    w3 = [0.25] * 10 + [0.8] * 3 + [0.25] * 18
    r3 = pc.runs(w3, xs, 0.25, 1.0)
    assert all(x[2] == 0.25 for x in r3)
    # every run is at most the minimum width of the samples it covers
    w4 = [0.6] * 12 + [0.4] * 12 + [1.0] * 7
    for x0, x1, wr in pc.runs(w4, xs, 0.25, 1.0):
        cov = [wi for xi, wi in zip(xs, w4) if x0 - 1e-9 <= xi <= x1 + 1e-9]
        assert wr <= min(cov) + 1e-9


def test_runs_short_track_widened_whole():
    xs = [0.0, 0.1, 0.2, 0.3]
    assert pc.runs([0.6] * 4, xs, 0.25, 1.0) == [(0.0, 0.3, 0.6)]


def test_ring_candidates_outside_pad_within_reach():
    pad = box(-0.5, -0.3, 0.5, 0.3)
    rv = 0.3
    c = pc.ring_candidates(pad, rv, 1.0)
    assert c, "no candidates"
    ds = [d for d, _, _ in c]
    assert ds == sorted(ds)                                  # nearest first
    for d, x, y in c:
        p = Point(x, y)
        assert p.distance(pad) >= rv - 1e-6                  # the via clears the pad
        assert p.distance(pad) <= 1.0 + rv + 1e-6            # within reach of the pad edge


def test_classify_switch_nodes_never_power():
    brief = dict(
        nets={"+3V3": dict(role="rail"), "GND": dict(role="ground"), "SW": dict(role="switch_node"),
              "XIN": dict(role="clock"), "FB": dict(role="signal"), "D0": dict(role="signal"),
              "VSW": dict(role="rail")},
        structures=[dict(kind="victim", nets=["FB"]), dict(kind="commutation_cell", sw="VSW")])
    power, ground, switch, victims = pc.classify(brief, ["+3V3", "GND", "SW", "XIN", "FB", "D0", "VSW"])
    assert power == {"+3V3"}
    assert ground == {"GND"}
    assert {"SW", "VSW"} <= switch
    assert victims == {"XIN", "FB"}


def test_net_currents_from_operating_facts():
    op = dict(parts={"U1": dict(I_A=[0.01, 0.2], I_sustained_A=0.05), "U2": dict(I_sustained_A=0.3),
                     "R1": dict(I_A=[0.0, 0.0])})
    nets = {"U1": {"+3V3", "GND", "SDA"}, "U2": {"+5V", "GND"}, "R1": {"+3V3", "X"}}
    cur = pc.net_currents(op, nets, {"+3V3", "+5V"}, {"GND"})
    assert cur["+3V3"] == pytest.approx(0.2)        # upper end of I_A
    assert cur["+5V"] == pytest.approx(0.3)         # I_sustained_A when no I_A
    assert cur["GND"] == pytest.approx(0.5)         # every powered part's return
    assert "SDA" not in cur


def test_width_cap_grows_with_current_only():
    assert pc.width_cap(1.0, 0.1) == 1.0            # small currents: the free-space default
    assert pc.width_cap(1.0, None) == 1.0
    w = pc.width_cap(1.0, 3.0)                      # 9 A design current: IPC asks for more
    assert w == pytest.approx(min(3.0, pc.ipc_width(9.0)))
    assert w > 1.0
    assert pc.width_cap(1.0, 100.0) == 3.0          # capped


def test_runs_short_pinch_between_wider_terminates():
    xs = [i * 0.1 for i in range(31)]
    w = [1.0] * 14 + [0.6] * 3 + [1.0] * 14             # a short 0.6 pinch, wider than the original
    r = pc.runs(w, xs, 0.25, 1.0)
    assert [x[2] for x in r] == [1.0, 0.6, 1.0]


def test_share_proportional_to_current():
    assert pc.share(1.0, 1.0) == pytest.approx(0.5)      # a supply and its return: equal
    assert pc.share(3.0, 1.0) == pytest.approx(0.75)     # the larger current takes more
    assert pc.share(None, 2.0) == pytest.approx(0.5)     # without both currents: equal
    # the share minimises I1^2/w1 + I2^2/w2 at w1 + w2 fixed
    i1, i2, room = 3.0, 1.0, 2.0
    best = min((i1 ** 2 / w + i2 ** 2 / (room - w), w) for w in [k * room / 1000 for k in range(1, 1000)])[1]
    assert best / room == pytest.approx(pc.share(i1, i2), abs=2e-3)


def test_process_of_assembly():
    assert pc.process_of({"process": "unknown"}) == "reflow"         # unknown: the common case
    assert pc.process_of(None) == "reflow"
    assert pc.process_of({"hand_solder_ok": True}) == "hand"
    assert pc.process_of({"process": "vapour phase"}) == "vapour_phase"
    assert pc.process_of({"process": "wave"}) == "wave"


def test_neck_rule_by_class_process_and_current():
    assert pc.pkg_class(0.3) == "0201" and pc.pkg_class(0.6) == "0402"
    assert pc.pkg_class(0.95) == "0603-0805" and pc.pkg_class(1.6) == "1206+"
    assert pc.neck_rule(0.6, "reflow") == pytest.approx(0.25)        # 0402 land
    assert pc.neck_rule(0.3, "reflow") == pytest.approx(0.15)        # 0201
    assert pc.neck_rule(1.6, "reflow") is None                       # 1206 and up: no neck in reflow
    assert pc.neck_rule(1.6, "hand") == pytest.approx(0.5)
    assert pc.neck_rule(1.6, "vapour_phase") == pytest.approx(0.5)
    assert pc.neck_rule(0.6, "wave") is None
    # a series part in a rail keeps the width its current needs
    w = pc.neck_rule(0.95, "reflow", series_current_a=0.5)
    assert w == pytest.approx(max(0.3, pc.ipc_width(1.5)))
    assert pc.neck_rule(0.6, "reflow", series_current_a=5.0) is None  # needs more than the land: no neck


def test_neck_half_keeps_wide_copper_off_the_land():
    d = np.array([0.0, 0.3, 0.5, 1.0, 2.0])
    h = pc.neck_half(d, 0.25, 0.5)
    assert h[0] == pytest.approx(0.125) and h[2] == pytest.approx(0.125)
    assert h[3] == pytest.approx(0.5) and h[4] == pytest.approx(1.5)
    # copper of half-width h centred at d keeps d - h >= neck_len wherever it is wider than the neck
    assert all(di - hi >= 0.5 - 1e-9 for di, hi in zip(d, h) if hi > 0.125 + 1e-9)


def test_strips_cover_and_stay_inside():
    from shapely.geometry import LineString
    region = box(0, 0, 5, 2).union(box(0, 0, 1, 6))
    w = 0.5
    segs = pc.strips(region, w)
    cov = unary_union([LineString([a, b]).buffer(w / 2) for a, b in segs])
    assert cov.difference(region).area < 1e-3             # nothing outside the region
    assert cov.area > 0.95 * region.area                   # and it is (almost) covered


def test_share_room_splits_by_current():
    from shapely.geometry import LineString

    class Sp:
        max_need = 0.2

        def _pair(self, a, b, layer):
            return None

    obj = pc.PowerCopper.__new__(pc.PowerCopper)
    obj.sp = Sp()
    obj.o = dict(pc.DEFAULTS)
    obj.current = {"A": 3.0, "B": 1.0}
    free = box(-1, -10, 5, 10)
    cand = {"A": dict(seeds=LineString([(0, -10), (0, 10)]), free=free, cap=20.0),
            "B": dict(seeds=LineString([(4, -10), (4, 10)]), free=free, cap=20.0)}
    claim = obj._share_room(cand, "F.Cu", steps=60)
    xa = claim["A"].intersection(box(0, -1, 5, 1)).bounds[2]       # A's reach toward B
    xb = claim["B"].intersection(box(-1, -1, 4, 1)).bounds[0]
    assert xa == pytest.approx(0.75 * 4.0, abs=0.25)                # w ~ I: A takes 3/4 of the room
    assert xb - xa == pytest.approx(0.2 + pc.VTOL, abs=0.02)        # the clearance between them
    obj.current = {}
    claim = obj._share_room(cand, "F.Cu", steps=60)
    assert claim["A"].intersection(box(0, -1, 5, 1)).bounds[2] == pytest.approx(2.0, abs=0.25)   # equal
    obj.o = dict(pc.DEFAULTS, share=False)                          # first come: the larger current takes all
    obj.current = {"A": 3.0, "B": 1.0}
    claim = obj._share_room(cand, "F.Cu", steps=60)
    assert claim["A"].intersection(box(0, -1, 5, 1)).bounds[2] > 3.5
