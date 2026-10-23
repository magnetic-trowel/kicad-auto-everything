# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route repair geometry and DSN ordering (no KiCad needed)."""
import copy
from types import SimpleNamespace

from shapely.geometry import Point, box

from kae.route import repair, specctra as S, translate

DSN = '''(pcb x
  (placement
    (component R0603 (place R1 0 0 front 0) (place R2 1000 0 front 0) (place R3 2000 0 front 0))
    (component C0402 (place C1 0 1000 front 0) (place C2 1000 1000 front 0))
    (component SOT23 (place Q1 0 2000 front 0))
  )
  (network
    (net A (pins R1-1 C1-1))
    (net B (pins R1-2 R2-1))
    (net C (pins R2-2 R3-1))
    (net D (pins R3-2 Q1-1))
    (class kae_Default A B C D)
  )
)
'''


def _order(tree):
    pl = S.find(tree, "placement")
    comps = [(c[1], [p[1] for p in S.findall(c, "place")]) for c in S.findall(pl, "component")]
    nets = [n[1] for n in S.findall(S.find(tree, "network"), "net")]
    return comps, nets


def test_permute_is_reproducible_and_keeps_everything():
    t0 = S.parse(DSN)
    t = copy.deepcopy(t0)
    assert not translate.permute(t, 0) and t == t0          # seed 0: KiCad's order
    a, b = copy.deepcopy(t0), copy.deepcopy(t0)
    assert translate.permute(a, 3) and translate.permute(b, 3)
    assert a == b                                            # same seed, same order
    (ca, na), (c0, n0) = _order(a), _order(t0)
    assert sorted(na) == sorted(n0) and sorted(x for _, p in ca for x in p) == sorted(x for _, p in c0 for x in p)
    assert S.find(S.find(a, "network"), "class") == S.find(S.find(t0, "network"), "class")
    orders = set()
    for seed in range(1, 8):
        t = copy.deepcopy(t0)
        translate.permute(t, seed)
        orders.add(repr(_order(t)))
    assert len(orders) > 1
    assert repair.round_seed(0, 1) != 0 and repair.round_seed(5, 1) != repair.round_seed(5, 2)


def _sq(x, y, h):
    return [[[x - h, y - h], [x + h, y - h], [x + h, y + h], [x - h, y + h], [x - h, y - h]]]


def _pad(uuid, net, x, y, h=0.5, layers=("F.Cu",)):
    return dict(uuid=uuid, net=net, pos=[x, y], layers=list(layers), comp="U1", pin=uuid, ref="U1",
                number=uuid, poly_by_layer={l: [_sq(x, y, h)] for l in layers}, thermal_gap=0.5, spoke_angle=0.0)


def _ring(polygon):
    return [[list(c) for c in polygon.exterior.coords]] + [[list(c) for c in h.coords] for h in polygon.interiors]


def test_net_clusters_follow_overlapping_copper_and_join_layers():
    cu = ["F.Cu", "B.Cu"]
    pads = [_pad("p1", "N", 0, 0), _pad("p2", "N", 10, 0), _pad("p3", "N", 20, 0),
            _pad("p4", "N", 30, 0, layers=("B.Cu",)), _pad("m1", "M", 5, 5)]
    info = dict(pads=pads)
    piece_a = box(-1, -2, 11, 2)                 # touches p1 and p2
    piece_b = box(28, 3, 32, 6)                  # holds the via below, not p4
    fills = [dict(uuid="z", net="N", layers={"F.Cu": [_ring(piece_a), _ring(piece_b)]})]
    copper = {"v1": dict(kind="via", net="N", pos=[30, 4], size=0.6),
              "t1": dict(kind="track", net="N", layer="B.Cu", a=[30, 0], b=[30, 4], width=0.2)}
    parts = repair.net_clusters("N", info, copper, fills, cu)
    assert sorted(sorted(c["pads"]) for c in parts) == [["p1", "p2"], ["p3"], ["p4"]]
    main = parts[0]
    assert main["pads"] == {"p1", "p2"} and len(main["pieces"]) == 1
    p4 = next(c for c in parts if "p4" in c["pads"])
    assert p4["routed"] == {"v1", "t1"} and len(p4["pieces"]) == 1   # track -> via -> F.Cu piece


def test_spoke_tracks_land_in_fill_and_keep_clear_of_other_nets():
    pad = _pad("p1", "N", 0, 0)
    foreign = _pad("m1", "M", 2.0, 0)            # blocks the 0 degree direction
    info = dict(pads=[pad, foreign], graphics=[])
    fill = box(-6, -6, 6, 6).difference(box(-1.2, -1.2, 1.2, 1.2)).difference(Point(2.0, 0).buffer(0.9))
    zone = dict(uuid="z", net="N", layers={"F.Cu": [_ring(fill)]})
    plan = SimpleNamespace(net_class={"N": "kae_A", "M": "kae_A"},
                           classes={"kae_A": SimpleNamespace(widths={"F.Cu": 0.2})},
                           matrix={("kae_A", "kae_A", "F.Cu"): (0.2, 0.2, 0.2)},
                           pin_class={}, obstacle_classes={}, obstacles=[])
    space = repair._Space({}, info, plan)
    got = repair.spoke_tracks(pad, zone, "F.Cu", 2, plan, space)
    assert len(got) == 2
    core = fill.buffer(-(0.1 + 0.01))
    m = box(1.5, -0.5, 2.5, 0.5)
    from shapely.geometry import LineString
    for s in got:
        assert s["net"] == "N" and s["layer"] == "F.Cu" and s["width"] == 0.2
        assert tuple(s["a"]) == (0.0, 0.0)                           # from the pad's centre
        assert core.buffer(1e-6).contains(Point(s["b"]))           # KiCad: the end lies in the fill
        assert LineString([s["a"], s["b"]]).buffer(0.1).distance(m) >= 0.2 - 1e-6


def test_pad_cut_off_from_its_zone_gets_a_spoke_into_the_rest_of_the_net():
    """A pad in its own island of fill is joined to the net's other piece, not to its island
    (a spoke into its own island joins nothing)."""
    pad, other = _pad("p1", "N", 0, 0), _pad("q1", "N", 5, 0)
    info = dict(pads=[pad, other], graphics=[], copper=["F.Cu", "B.Cu"])
    island = box(-2, -2, 2, 2).difference(box(-0.9, -0.9, 0.9, 0.9)).union(box(0.4, -0.1, 0.95, 0.1))
    main = box(3, -3, 8, 3)
    zone = dict(uuid="z", net="N", layers={"F.Cu": [_ring(island), _ring(main)]})
    plan = SimpleNamespace(net_class={"N": "kae_A"}, classes={"kae_A": SimpleNamespace(widths={"F.Cu": 0.2})},
                           matrix={}, pin_class={}, obstacle_classes={}, obstacles=[], copper=["F.Cu", "B.Cu"])
    report = dict(violations=[], unconnected_items=[dict(items=[
        dict(description="Pad 1 [N] of U1 on F.Cu", uuid="p1", pos=dict(x=0, y=0)),
        dict(description="Zone [N] on F.Cu, priority 0", uuid="z", pos=dict(x=3, y=-3))])])
    a = repair.analyse(report, {}, info, plan, fills=[zone], layer_map={}, copper={})
    assert len(a["spokes"]) == 1 and not a["thermal"]
    end = Point(a["spokes"][0]["b"])
    assert main.contains(end) and not island.buffer(0.05).contains(end)
