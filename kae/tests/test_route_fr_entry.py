# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.fr_entry: the rule D entry table and rail classes written into the DSN for kae's
Freerouting fork (no KiCad needed)."""
import math
from types import SimpleNamespace

from shapely import affinity
from shapely.geometry import LineString, Point, box

from kae.route import fr_entry as FE
from kae.route import freerouting as FR
from kae.route import pad_entry as PE
from kae.route import specctra as S
from kae.route.constraints import RoutingClass

DSN = '''(pcb "/tmp/x.dsn"
  (resolution um 10)
  (unit um)
  (structure (layer F.Cu (type signal)) (layer B.Cu (type signal)))
  (placement
    (component R0603 (place R1 100000 -50000 front 30))
    (component TP (place TP1 110000 -50000 front 0))
  )
  (library
    (image R0603 (pin RECT 1 -800 0) (pin RECT 2 800 0))
    (image TP (pin ROUND 1 0 0))
    (padstack RECT (shape (rect F.Cu -500 -300 500 300)) (attach off))
    (padstack ROUND (shape (circle F.Cu 800)) (attach off))
  )
  (network
    (class kae_Default VCC SIG (circuit (use_via "Via[0-1]_600:300_um")) (rule (width 250) (clearance 200)))
    (class_class (classes kae_Default kae_obs0) (rule (clearance 150)))
    (net VCC (pins R1-1 TP1-1))
    (net SIG (pins R1-2))
  )
)
'''


def _board():
    """The DSN's pads as KiCad's export would describe them (board mm, y down)."""
    a = math.radians(30)
    pads = []
    for pin, px in (("1", -0.8), ("2", 0.8)):
        x, y = 100.0 + px * math.cos(a), 50.0 - px * math.sin(a)
        g = affinity.translate(affinity.rotate(box(-0.5, -0.3, 0.5, 0.3), -30, origin=(0, 0)), x, y)
        pads.append(dict(comp="R1", ref="R1", pin=pin, net="VCC" if pin == "1" else "SIG", attr="smd",
                         layers=["F.Cu"], pos=[x, y], poly=[[list(g.exterior.coords)]]))
    rnd = Point(110.0, 50.0).buffer(0.4, quad_segs=32)
    pads.append(dict(comp="TP1", ref="TP1", pin="1", net="VCC", attr="smd", layers=["F.Cu"], pos=[110.0, 50.0],
                     poly=[[list(rnd.exterior.coords)]]))
    info = dict(copper=["F.Cu", "B.Cu"], pads=pads, nets={"VCC": {}, "SIG": {}})
    rc = RoutingClass(name="kae_Default", nets=["VCC", "SIG"], netclass="Default",
                      widths={"F.Cu": 0.25, "B.Cu": 0.25}, via=(0.6, 0.3))
    plan = SimpleNamespace(copper=["F.Cu", "B.Cu"], classes={"kae_Default": rc},
                           net_class={"VCC": "kae_Default", "SIG": "kae_Default"}, min_width=0.1)
    return info, plan


def test_land_entries_follow_rule_d_and_reach_the_centre():
    """Every entry of a 1.0 x 0.6 land (rotated 30 deg) is one of pad_entry's rule D targets: the
    approach point outside the land, the last piece square to the outline, the end on the long
    centre line, and the run from the end to the pin centre inside the land."""
    g = affinity.rotate(box(-0.5, -0.3, 0.5, 0.3), 30, origin=(0, 0))
    es = FE.land_entries(g, (0.0, 0.0), 0.25)
    kinds = {e["kind"] for e in es}
    assert {"long", "axial"} <= kinds
    a0, b0 = PE.centreline(g)
    for e in es:
        assert not g.contains(Point(e["a"]))
        assert PE.entry_angle(g, e["a"], e["end"]) <= 10.0 + 1e-6
        assert LineString([a0, b0]).distance(Point(e["end"])) < 1e-6
        assert FE._runs_inside(g, e["end"], (0.0, 0.0), 0.25)
        assert not PE.overhangs(g, e["a"], e["end"], 0.25)
    # both long edges and both short ends are offered, each at least once
    sides = {round(math.degrees(math.atan2(e["a"][1] - e["end"][1], e["a"][0] - e["end"][0]))) % 360 for e in es}
    assert len(sides) >= 4
    assert es == FE.land_entries(g, (0.0, 0.0), 0.25)          # deterministic


def test_wide_track_is_necked_and_round_lands_are_radial():
    g = box(-0.3, -0.3, 0.3, 0.3)
    es = FE.land_entries(g, (0.0, 0.0), 0.8, need=0.0, min_w=0.1)
    assert es and all(e["neck"] is not None and e["neck"] <= 0.6 + 1e-9 for e in es)
    assert FE.is_round(Point(0, 0).buffer(0.4, quad_segs=32)) and not FE.is_round(g)


def test_table_round_trip_in_dsn_units():
    """translate writes the table at the end of the pcb scope; read back, every point is the
    entry's board-mm point in DSN units (um, y up), the frame carries the land's axis and size,
    and the round test point is marked radial."""
    info, plan = _board()
    tree = S.parse(DSN)
    sm = FE.apply(tree, plan, info, lambda l: l, entries=True, rails=False)
    assert sm["pins"] == 3 and sm["entries"] > 0
    assert tree[-1][0] == FE.SCOPE
    back = S.parse(S.dumps(tree))
    pins, floors = FE.read_scope(back)
    assert set(pins) == {("R1", "1", "F.Cu"), ("R1", "2", "F.Cu"), ("TP1", "1", "F.Cu")} and not floors
    assert pins[("TP1", "1", "F.Cu")]["radial"] and not pins[("R1", "1", "F.Cu")]["radial"]
    table = FE.pin_entries(S.parse(DSN), plan, info)
    centre, per = table[("R1", "1")]
    g, es = per["F.Cu"]
    rec = pins[("R1", "1", "F.Cu")]
    assert math.dist(rec["centre"], (centre[0] * 1000, -centre[1] * 1000)) < 1e-3
    ux, uy, w, h, cx, cy = rec["frame"]
    assert abs(w - 1000) < 1 and abs(h - 600) < 1
    assert abs(math.degrees(math.atan2(uy, ux)) % 180 - 30) < 0.1      # 30 deg, y up
    assert len(rec["entries"]) == len(es)
    for e, r in zip(es, rec["entries"]):
        assert r["kind"] == e["kind"] and abs(r["width"] - 250) < 1e-6
        assert math.dist(r["approach"], (e["a"][0] * 1000, -e["a"][1] * 1000)) < 1e-3
        assert math.dist(r["end"], (e["end"][0] * 1000, -e["end"][1] * 1000)) < 1e-3
    # written in (ref, pin) order, the same twice
    assert S.dumps(tree) == S.dumps(_applied())


def _applied():
    info, plan = _board()
    t = S.parse(DSN)
    FE.apply(t, plan, info, lambda l: l, entries=True, rails=False)
    return t


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("KAE_FR_PIN_ENTRIES", raising=False)
    monkeypatch.delenv("KAE_FR_RAILS", raising=False)
    info, plan = _board()
    tree = S.parse(DSN)
    assert FE.apply(tree, plan, info, lambda l: l) == {}
    assert S.find(tree, FE.SCOPE) is None


def test_rail_gets_its_own_class_and_floor(monkeypatch):
    """A rail whose current needs 0.6 mm moves into a copy of its class at that width, with the
    class's class_class rules copied, a rule against its old class, and a class floor."""
    info, plan = _board()
    plan.rail_need = {"VCC": 0.6}
    tree = S.parse(DSN)
    sm = FE.apply(tree, plan, info, lambda l: l, entries=False, rails=True)
    assert sm["rail_classes"] == [dict(net="VCC", cls="kae_Default__rail0", need_mm=0.6)]
    net = S.find(tree, "network")
    cls = {str(c[1]): c for c in S.findall(net, "class")}
    assert "VCC" not in [str(x) for x in cls["kae_Default"][2:] if not isinstance(x, list)]
    rail = cls["kae_Default__rail0"]
    assert [str(x) for x in rail[2:] if not isinstance(x, list)] == ["VCC"]
    assert S.find(S.find(rail, "rule"), "width")[1] == "600"
    assert S.find(S.find(rail, "rule"), "clearance")[1] == "200"
    pairs = [[str(x) for x in S.find(c, "classes")[1:]] for c in S.findall(net, "class_class")]
    assert ["kae_Default__rail0", "kae_obs0"] in pairs and ["kae_Default", "kae_Default__rail0"] in pairs
    _pins, floors = FE.read_scope(S.parse(S.dumps(tree)))
    assert S.find(floors["kae_Default__rail0"], "width")[1] == "600"


def test_freerouting_asks_the_fork_for_the_table(tmp_path):
    p = tmp_path / "b.dsn"
    p.write_text(S.dumps(_applied()))
    assert FR.fork_settings(p, {"a": "1"}) == {"a": "1", "kae_pin_entries": "true"}
    q = tmp_path / "c.dsn"
    q.write_text(DSN)
    assert FR.fork_settings(q, None) == {}
    log = "x\n[main] INFO kae_pin_entries: pin_layers=3 tails=2 raw=1 inserted=4\n"
    assert FR.pin_entry_stats(log) == dict(pin_layers=3, tails=2, raw=1, inserted=4)
