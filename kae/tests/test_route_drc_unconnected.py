# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.drc.canonical_unconnected: unconnected pairs named the same whichever of the copper at an
anchor KiCad's DRC happened to name (it varies from run to run on one file)."""
import copy

from kae.route import drc

# two GND tracks meeting at (2, 0); a connector's front and back GND pads at one position (5, 5); a GND pad
# elsewhere (9, 9) that is not joined to either
ITEMS = [
    dict(uuid="t1", kind="track", net="GND", description="Track [GND] on F.Cu, length 1.0000 mm",
         pos=[1_000_000, 0], anchors=[[1_000_000, 0], [2_000_000, 0]]),
    dict(uuid="t2", kind="track", net="GND", description="Track [GND] on F.Cu, length 3.0000 mm",
         pos=[2_000_000, 0], anchors=[[2_000_000, 0], [5_000_000, 0]]),
    dict(uuid="p2", kind="pad", net="GND", description="Pad 2 [GND] of P1 on F.Cu", pos=[5_000_000, 5_000_000],
         anchors=[[5_000_000, 5_000_000]]),
    dict(uuid="p4", kind="pad", net="GND", description="Pad 4 [GND] of P1 on B.Cu", pos=[5_000_000, 5_000_000],
         anchors=[[5_000_000, 5_000_000]]),
    dict(uuid="q1", kind="pad", net="GND", description="Pad 1 [GND] of C1 on F.Cu", pos=[2_100_000, 1_000_000],
         anchors=[[2_100_000, 1_000_000]]),
    dict(uuid="v1", kind="via", net="SIG", description="Via [SIG] on F.Cu - B.Cu", pos=[2_000_000, 0],
         anchors=[[2_000_000, 0]]),
]
BY = {it["uuid"]: it for it in ITEMS}


def _it(u, pos=None):
    it = BY[u]
    p = pos or it["pos"]
    return dict(description=it["description"], pos=dict(x=p[0] / 1e6, y=p[1] / 1e6), uuid=u)


def _rep(*pairs):
    return dict(violations=[], unconnected_items=[dict(type="unconnected_items", severity="error",
                                                         description="Missing connection between items",
                                                         items=[_it(a), _it(b)]) for a, b in pairs])


def test_the_same_pairs_whichever_item_kicad_named():
    # run 1 named t1 and p2, run 2 t2 and p4, in the other order: the same connections
    a = drc.canonical_unconnected(_rep(("t1", "q1"), ("p2", "q1")), ITEMS)
    b = drc.canonical_unconnected(_rep(("q1", "t2"), ("q1", "p4")), ITEMS)
    assert a == b
    named = [[i["uuid"] for i in u["items"]] for u in a["unconnected_items"]]
    assert sorted(map(sorted, named)) == [["p2", "q1"], ["q1", "t1"]]


def test_other_nets_at_the_anchor_are_not_candidates():
    rep = drc.canonical_unconnected(_rep(("t2", "q1")), ITEMS)
    assert {i["uuid"] for i in rep["unconnected_items"][0]["items"]} == {"t1", "q1"}   # never the SIG via


def test_items_it_does_not_know_as_kicad_names_them_are_left_alone():
    rep = _rep(("t2", "q1"))
    rep["unconnected_items"][0]["items"][0]["description"] = "Track [GND] on Top, length 3.0000 mm"
    rep["unconnected_items"].append(dict(type="unconnected_items", items=[
        dict(description="Zone [GND] on F.Cu", pos=dict(x=0.0, y=0.0), uuid="z1"), _it("q1")]))
    want = copy.deepcopy(rep)
    for u in want["unconnected_items"]:                       # only put in order
        u["items"].sort(key=lambda r: (r["description"], str(r["pos"]), r["uuid"]))
    want["unconnected_items"].sort(key=drc._content_key)
    assert drc.canonical_unconnected(rep, ITEMS) == want
    assert drc.canonical_unconnected(copy.deepcopy(want), None) == want


def test_equally_near_pairs_of_two_clusters_are_one_choice():
    """Copper laid out symmetrically: two parallel tracks, each from a pad, 1 mm apart; the two clusters are as
    near at the pads as at the tracks' far ends, and KiCad names either pair."""
    items = [
        dict(uuid="a", kind="pad", net="N", description="Pad 1 [N] of R1 on F.Cu", pos=[0, 0], anchors=[[0, 0]], cluster=1),
        dict(uuid="ta", kind="track", net="N", description="Track [N] on F.Cu, length 2.0000 mm", pos=[0, 0],
             anchors=[[0, 0], [2_000_000, 0]], cluster=1),
        dict(uuid="b", kind="pad", net="N", description="Pad 1 [N] of R2 on F.Cu", pos=[0, 1_000_000],
             anchors=[[0, 1_000_000]], cluster=2),
        dict(uuid="tb", kind="track", net="N", description="Track [N] on F.Cu, length 2.0000 mm", pos=[0, 1_000_000],
             anchors=[[0, 1_000_000], [2_000_000, 1_000_000]], cluster=2),
    ]
    by = {it["uuid"]: it for it in items}

    def rep(x, y):
        return dict(unconnected_items=[dict(type="unconnected_items", items=[
            dict(description=by[u]["description"], pos=dict(x=by[u]["pos"][0] / 1e6, y=by[u]["pos"][1] / 1e6), uuid=u)
            for u in (x, y)])])
    a = drc.canonical_unconnected(rep("ta", "tb"), items)      # the far ends
    b = drc.canonical_unconnected(rep("b", "a"), items)        # the pads
    assert a == b
    assert {i["uuid"] for i in a["unconnected_items"][0]["items"]} == {"a", "b"}      # at (0, 0), the first


def test_nearest_pair_of_large_sets_is_the_exact_first():
    import random
    rnd = random.Random(3)
    a = [(rnd.randrange(0, 10_000), rnd.randrange(0, 10_000)) for _ in range(300)]
    b = [(rnd.randrange(20_000, 30_000), rnd.randrange(0, 10_000)) for _ in range(300)]
    b.append((a[0][0] + 13_000, a[0][1]))
    want = min(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2, p, q) for p in a for q in b)[1:]
    assert drc._nearest(a, b) == want and drc._nearest(b, a) == want[::-1]


def _entry(by, x, y):
    return dict(type="unconnected_items", severity="error", description="Missing connection between items",
                items=[dict(description=by[u]["description"], pos=dict(x=by[u]["pos"][0] / 1e6, y=by[u]["pos"][1] / 1e6),
                            uuid=u) for u in (x, y)])


def test_ties_between_clusters_are_one_spanning_tree():
    """A connector's front and back GND pads at one position are two clusters (0 apart), and a capacitor's
    pad is as near to either: KiCad joins it to whichever it sorted first. Three clusters with two equally
    short connections and a longer one: KiCad names the short ones in either order and either way round."""
    p, s = 1_000_000, 866_025
    items = [
        dict(uuid="f", kind="pad", net="GND", description="Pad 3 [GND] of P1 on F.Cu", pos=[0, 0], anchors=[[0, 0]], cluster=1),
        dict(uuid="b", kind="pad", net="GND", description="Pad 5 [GND] of P1 on B.Cu", pos=[0, 0], anchors=[[0, 0]], cluster=2),
        dict(uuid="c", kind="pad", net="GND", description="Pad 1 [GND] of C25 on F.Cu", pos=[0, p], anchors=[[0, p]], cluster=3),
        dict(uuid="x", kind="pad", net="S", description="Pad 1 [S] of U1 on F.Cu", pos=[0, 0], anchors=[[0, 0]], cluster=4),
        dict(uuid="y", kind="pad", net="S", description="Pad 2 [S] of U1 on F.Cu", pos=[2 * p, 0], anchors=[[2 * p, 0]], cluster=5),
        dict(uuid="z", kind="pad", net="S", description="Pad 3 [S] of U1 on F.Cu", pos=[p, 2 * s], anchors=[[p, 2 * s]], cluster=6),
    ]
    by = {it["uuid"]: it for it in items}
    a = dict(unconnected_items=[_entry(by, "f", "b"), _entry(by, "c", "f"), _entry(by, "x", "y"), _entry(by, "y", "z")])
    b = dict(unconnected_items=[_entry(by, "c", "b"), _entry(by, "b", "f"), _entry(by, "z", "x"), _entry(by, "x", "y")])
    a, b = drc.canonical_unconnected(a, items), drc.canonical_unconnected(b, items)
    assert a == b
    pairs = sorted(tuple(sorted(i["uuid"] for i in u["items"])) for u in a["unconnected_items"])
    assert pairs == [("b", "f"), ("c", "f"), ("x", "z"), ("y", "z")]      # x-y is the longest side


def test_spanning_tree_of_a_large_net_matches_the_brute_force_one():
    import random
    rnd = random.Random(5)
    anchors = {c: [(rnd.randrange(0, 50) * 100_000, rnd.randrange(0, 50) * 100_000) for _ in range(rnd.randrange(1, 6))]
               for c in range(150)}
    big = drc._cluster_tree(anchors)
    assert len(big) == 149 and len({x for e in big for x in (e[0], e[2])}) == 150

    def length(t):
        return sum((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 for _, p, _, q in t)
    import itertools
    pts = sorted({p for v in anchors.values() for p in v})
    assert len(pts) > 400
    # the Delaunay tree is a minimum one: no shorter tree from all pairs (Kruskal over every pair)
    cand = sorted(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2, a, b) for a, b in itertools.combinations(anchors, 2)
                  for p in anchors[a] for q in anchors[b])
    parent = {c: c for c in anchors}

    def find(c):
        while parent[c] != c:
            c = parent[c]
        return c
    best = 0
    for d, a, b in cand:
        if find(a) != find(b):
            parent[find(b)] = find(a)
            best += d
    assert length(big) == best


def test_a_net_with_a_zone_pair_renames_its_other_pairs_one_by_one():
    rep = _rep(("t2", "q1"))
    rep["unconnected_items"].append(dict(type="unconnected_items", items=[
        dict(description="Zone [GND] on F.Cu", pos=dict(x=0.0, y=0.0), uuid="z1"), _it("p4")]))
    out = drc.canonical_unconnected(rep, ITEMS)
    named = sorted(sorted(i["uuid"] for i in u["items"]) for u in out["unconnected_items"])
    assert named == [["p4", "z1"], ["q1", "t1"]]      # the zone's pair as KiCad named it


def _sq(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


# a GND zone with two filled islands on F.Cu: A (0..4 mm) holds pad pA, B (10..14 mm) holds nothing; pad pC
# (20, 2) is on its own. Three parts, two missing connections.
ZD = "Zone [GND] on F.Cu, priority 0"
ZITEMS = [
    dict(uuid="pA", kind="pad", net="GND", description="Pad 1 [GND] of U1 on F.Cu", pos=[2_000_000, 2_000_000],
         anchors=[[2_000_000, 2_000_000]], cluster=0),
    dict(uuid="z", key="z/F.Cu/0", kind="zone", net="GND", description=ZD, pos=[0, 0],
         anchors=_sq(0, 0, 4_000_000, 4_000_000), ring=_sq(0, 0, 4_000_000, 4_000_000), cluster=0),
    dict(uuid="z", key="z/F.Cu/1", kind="zone", net="GND", description=ZD, pos=[10_000_000, 0],
         anchors=_sq(10_000_000, 0, 14_000_000, 4_000_000), ring=_sq(10_000_000, 0, 14_000_000, 4_000_000),
         cluster=1),
    dict(uuid="pC", kind="pad", net="GND", description="Pad 2 [GND] of U2 on F.Cu", pos=[20_000_000, 2_000_000],
         anchors=[[20_000_000, 2_000_000]], cluster=2),
]


def _zrep(*pairs):
    def one(x):
        u, p = x if isinstance(x, tuple) else (x, None)
        it = next(i for i in ZITEMS if i["uuid"] == u)
        q = p or it["pos"]
        return dict(description=it["description"], pos=dict(x=q[0] / 1e6, y=q[1] / 1e6), uuid=u)
    return dict(violations=[], unconnected_items=[dict(type="unconnected_items", severity="error",
                                                         description="Missing connection between items",
                                                         items=[one(a), one(b)]) for a, b in pairs])


def test_a_zone_nets_pairs_are_the_same_whichever_island_or_pad_kicad_named():
    # run 1 named the islands as the zone and pC's pair with pA; run 2 named island B with pA and pC with
    # island A; ch32v003's GND was named both ways by one board's DRCs
    a = drc.canonical_unconnected(_zrep((("z", [11_000_000, 1_000_000]), ("z", [3_000_000, 1_000_000])),
                                        ("pC", "pA")), ZITEMS)
    b = drc.canonical_unconnected(_zrep((("z", [12_000_000, 3_000_000]), "pA"),
                                        ("pC", ("z", [1_000_000, 3_000_000]))), ZITEMS)
    assert a == b
    sides = sorted(sorted((i["uuid"], i["pos"]["x"]) for i in u["items"]) for u in a["unconnected_items"])
    # the tree: island A to island B (4 mm to 10 mm), island B to pC (14 mm to 20 mm)
    assert sides == [[("pC", 20.0), ("z", 14.0)], [("z", 4.0), ("z", 10.0)]]


def test_a_zone_pair_maps_to_the_island_that_holds_its_position():
    isl = [i for i in ZITEMS if i.get("kind") == "zone"]
    assert drc._island_at(isl, (12_000_000, 2_000_000))["key"] == "z/F.Cu/1"
    assert drc._island_at(isl, (5_000_000, 2_000_000))["key"] == "z/F.Cu/0"      # outside both: the nearest
