# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.joint.feedback: DRC items to spots, congestion history, windows."""
import numpy as np
from kae.joint.feedback import (
    CongestionHistory,
    PartGeom,
    Spot,
    error_spots,
    parse_item,
    physics_spots,
    plan_windows,
    unrouted_spots,
    window_for_spot,
)

DRC = {
    "unconnected_items": [
        {"items": [{"description": "Pad 1 [Net-(C3-Pad1)] of C3 on F.Cu", "pos": {"x": 10.0, "y": 10.0},
                    "uuid": "p1"},
                   {"description": "Pad 2 [Net-(C3-Pad1)] of R4 on F.Cu", "pos": {"x": 20.0, "y": 10.0},
                    "uuid": "p2"}],
         "severity": "error", "type": "unconnected_items"},
        {"items": [{"description": "Track [GND] on B.Cu, length 1.2000 mm", "pos": {"x": 5.0, "y": 5.0},
                    "uuid": "t1"},
                   {"description": "PTH pad 2 [GND] of J1", "pos": {"x": 6.0, "y": 8.0}, "uuid": "p3"}],
         "severity": "error", "type": "unconnected_items"},
    ],
    "violations": [
        {"severity": "error", "type": "clearance", "items": [
            {"description": "Via [SIG] on F.Cu - B.Cu", "pos": {"x": 1.0, "y": 1.0}, "uuid": "v1"},
            {"description": "Pad 1 [VCC] of U2 on F.Cu", "pos": {"x": 1.4, "y": 1.0}, "uuid": "p9"}]},
        {"severity": "warning", "type": "silk_overlap", "items": [
            {"description": "Footprint U2", "pos": {"x": 1.0, "y": 1.0}, "uuid": "f"}]},
        {"severity": "error", "type": "lib_footprint_mismatch", "items": [
            {"description": "Footprint U2", "pos": {"x": 1.0, "y": 1.0}, "uuid": "f"}]},
    ],
}


def test_parse_item_kinds_refs_nets():
    p = parse_item({"description": "Pad 1 [Net-(C3-Pad1)] of C3 on F.Cu", "pos": {"x": 1, "y": 2}, "uuid": "u"})
    assert (p["kind"], p["ref"], p["net"], p["pos"]) == ("pad", "C3", "Net-(C3-Pad1)", (1.0, 2.0))
    assert parse_item({"description": "PTH pad 2 [GND] of J1"})["ref"] == "J1"
    t = parse_item({"description": "Track [GND] on B.Cu, length 1.2 mm", "uuid": "t"})
    assert (t["kind"], t["ref"], t["net"]) == ("track", "", "GND")
    assert parse_item({"description": "Via [SIG] on F.Cu - B.Cu"})["kind"] == "via"
    assert parse_item({"description": "Zone [GND] on In1.Cu"})["kind"] == "zone"


def test_unrouted_and_error_spots():
    u = unrouted_spots(DRC)
    assert len(u) == 2
    assert u[0].refs == ("C3", "R4") and u[0].nets == ("Net-(C3-Pad1)",) and (u[0].x, u[0].y) == (15.0, 10.0)
    assert u[1].refs == ("J1",) and u[1].uuids == ("t1",)
    e = error_spots(DRC)
    assert len(e) == 1                       # warnings and library-environment checks are not errors
    assert e[0].why == "clearance" and e[0].refs == ("U2",) and e[0].uuids == ("v1",)
    assert e[0].kind == "error"              # a via is involved: the router's
    p = error_spots({"violations": [{"severity": "error", "type": "hole_clearance",
                                     "description": "Hole clearance violation (pad clearance 1.8500 mm; actual 1.2170 mm)",
                                     "items": [
        {"description": "PTH pad 1 [A] of MH4", "pos": {"x": 1, "y": 1}},
        {"description": "Pad 2 [B] of R5 on F.Cu", "pos": {"x": 2, "y": 1}}]}]})
    assert p[0].kind == "placement" and p[0].weight > u[0].weight and p[0].refs == ("MH4", "R5")
    assert abs(p[0].short_mm - 0.633) < 1e-9


def test_physics_spots_weight_by_rise():
    rc = dict(modules={"cell:U1": dict(u_stage=1.0, u_routed=1.5, flag=True),
                       "decap:U2": dict(u_stage=0.5, u_routed=0.5, cover_stage=1.0, cover_routed=0.7,
                                        flag=True, why="plane perforated")},
              retweak=["decap:U2", "cell:U1"])
    sp = physics_spots(rc, {"cell:U1": ["a", "b"], "decap:U2": ["c"]}, {"a": (0, 0), "b": (2, 0), "c": (5, 5)},
                       {"a": "U1", "b": "C1", "c": "C2"})
    assert [s.module for s in sp] == ["cell:U1", "decap:U2"]
    assert abs(sp[0].weight - 1.5) < 1e-9 and (sp[0].x, sp[0].y) == (1.0, 0.0)
    assert abs(sp[1].weight - 1.3) < 1e-9 and sp[1].why == "plane perforated"


def test_history_corridor_and_resample():
    h = CongestionHistory((0, 0, 20, 10), bin_mm=1.0)
    n = h.add_corridor((2, 5), (18, 5), width=1.0, amount=1.0)
    assert n > 0 and h.h[10, 5] == 1.0 and h.h[10, 0] == 0.0
    h.add_spot(Spot(kind="unrouted", x=10, y=5, points=((2, 5), (18, 5))), amount=1.0)
    assert h.h[10, 5] == 2.0
    # coarser grid: means; finer grid: nearest
    c = h.sample(0, 0, 2.0, 10, 5)
    assert c.shape == (10, 5) and c[5, 2] > 0 and c[5, 0] == 0
    f = h.sample(0, 0, 0.5, 40, 20)
    assert f[20, 10] == h.h[10, 5]
    assert np.isclose(CongestionHistory((0, 0, 5, 5)).sample(0, 0, 1, 5, 5).sum(), 0.0)


def _parts():
    g = {}
    for k, (x, y) in enumerate([(10, 10), (20, 10), (12, 12), (40, 30), (21, 11)]):
        u = f"u{k}"
        g[u] = PartGeom(uuid=u, ref=f"R{k}", bbox=(x - 1, y - 0.5, x + 1, y + 0.5))
    g["lk"] = PartGeom(uuid="lk", ref="J1", bbox=(14, 9, 16, 11), locked=True)
    return g


def test_window_for_spot_keeps_own_parts_and_skips_locked():
    parts = _parts()
    s = Spot(kind="unrouted", x=15, y=10, points=((10, 10), (20, 10)), refs=("R0", "R1"))
    w = window_for_spot(s, parts, (0, 0, 50, 40), margin=2.0, max_parts=3)
    assert set(w.parts) >= {"u0", "u1"} and "lk" not in w.parts and len(w.parts) == 3
    for u in w.parts:                      # the window contains every movable part's box
        b = parts[u].bbox
        assert w.rect[0] <= b[0] and w.rect[1] <= b[1] and w.rect[2] >= b[2] and w.rect[3] >= b[3]
    # a spot on locked parts only takes the movable parts around it
    s2 = Spot(kind="error", x=15, y=10, points=((15, 10),), refs=("J1",))
    w2 = window_for_spot(s2, parts, (0, 0, 50, 40), margin=1.0)
    assert w2 is None
    w3 = window_for_spot(s2, parts, (0, 0, 50, 40), margin=6.0)
    assert "lk" not in w3.parts and w3.parts


def test_plan_windows_merges_and_orders_deterministically():
    parts = _parts()
    spots = [Spot(kind="unrouted", x=15, y=10, points=((10, 10), (20, 10)), refs=("R0", "R1"), weight=3.0),
             Spot(kind="error", x=21, y=11, points=((21, 11),), refs=("R4",), weight=2.0),
             Spot(kind="physics", x=40, y=30, points=((40, 30),), refs=("R3",), weight=1.0, module="m")]
    w = plan_windows(spots, parts, (0, 0, 50, 40), margin=1.0, max_parts=4)
    assert len(w) == 2
    assert w[0].priority == 5.0 and set(w[0].parts) >= {"u0", "u1", "u4"}
    assert w[1].parts == ("u3",) and w[1].modules == ("m",)
    assert [x.parts for x in plan_windows(list(reversed(spots)), parts, (0, 0, 50, 40), 1.0, 4)] == \
        [x.parts for x in w]


def test_placement_errors_count_only_part_to_part_violations():
    from kae.joint.stages import placement_errors
    rep = {"violations": [
        {"severity": "error", "type": "courtyards_overlap", "items": [
            {"description": "Footprint U1"}, {"description": "Footprint U2"}]},
        {"severity": "error", "type": "clearance", "items": [
            {"description": "Pad 1 [A] of U1 on F.Cu"}, {"description": "Pad 2 [B] of U2 on F.Cu"}]},
        {"severity": "error", "type": "clearance", "items": [           # the router's
            {"description": "Track [A] on F.Cu, length 1 mm"}, {"description": "Pad 2 [B] of U2 on F.Cu"}]},
        {"severity": "warning", "type": "courtyards_overlap", "items": [{"description": "Footprint U3"}]},
        {"severity": "error", "type": "track_width", "items": [{"description": "Track [A] on F.Cu"}]},
    ]}
    assert placement_errors(rep) == 2


def test_big_parts_move_only_when_nothing_smaller_can():
    parts = _parts()
    parts["u1"].pins = 40                      # an IC at (20, 10)
    s = Spot(kind="unrouted", x=15, y=10, points=((10, 10), (20, 10)), refs=("R0", "R1"))
    w = plan_windows([s], parts, (0, 0, 50, 40), margin=2.0, max_parts=3, max_pins=12)
    assert "u1" not in w[0].parts and "u0" in w[0].parts
    s2 = Spot(kind="unrouted", x=20, y=10, points=((20, 10),), refs=("R1",))
    w2 = plan_windows([s2], parts, (0, 0, 50, 40), margin=0.5, max_parts=3, max_pins=12)
    assert "u1" in w2[0].parts                # nothing small within reach: the IC moves


def test_rudy_overflow_adds_history_only_near_failures():
    h = CongestionHistory((0, 0, 20, 10), bin_mm=1.0)
    util = np.full((10, 5), 0.9)                 # a 2 mm RUDY grid, crowded everywhere
    assert h.add_overflow(0, 0, 2.0, util) == 0.0     # no failure yet: RUDY alone marks nothing
    h.add_corridor((2, 5), (4, 5), width=1.0, amount=1.0)
    before = h.h.copy()
    added = h.add_overflow(0, 0, 2.0, util, target=0.5, scale=0.5, reach_mm=2.0)
    assert added > 0
    assert h.h[3, 5] > before[3, 5] and h.h[15, 5] == 0.0


def test_spot_without_movable_parts_becomes_a_reroute_window():
    parts = _parts()
    s = Spot(kind="unrouted", x=30, y=30, points=((29, 30), (31, 30)), nets=("VNEG",))   # two track ends
    w = plan_windows([s], parts, (0, 0, 50, 40), margin=1.0, max_parts=4)
    assert len(w) == 1 and w[0].parts == () and w[0].key[0] == "reroute"
    assert "re-route" in w[0].reasons[0]
