# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.hotloop and the cell stage's options (R1-R5 of kae-hot-loops), on the synthetic
buck board of critical_fixtures, without KiCad."""
import math

import pytest
from shapely.geometry import Point, Polygon

import critical_fixtures as F
from kae.board.kicad_file import load
from kae.route import critical_modules as CM
from kae.route import critical_physics as P
from kae.route import hotloop


def _stage(tmp_path, **opts):
    p = F.write_board(tmp_path / "in")
    b = load(p)
    rep = hotloop.stage(p, F.synth_info(b), tmp_path / "w", opts, log=lambda *a: None)
    return p, rep


# ----------------------------------------------------------------------------- settings
def test_settings_default_off_and_vias_pours_imply_cells(monkeypatch):
    for k in hotloop.SETTINGS:
        monkeypatch.delenv("KAE_" + k.upper(), raising=False)
    st = hotloop.settings(None, {})
    assert not hotloop.active(st) and st["keepout_mm"] == 1.0
    assert hotloop.settings(None, {"hotloop_vias": 1})["cells"]
    assert hotloop.settings(None, {"hotloop_pours": "1"})["cells"]
    monkeypatch.setenv("KAE_HOTLOOP_KEEPOUT", "1")
    assert hotloop.settings(None, {})["keepout"]


def test_stage_is_none_when_off(tmp_path):
    p = F.write_board(tmp_path / "in")
    assert hotloop.stage(p, F.synth_info(load(p)), tmp_path / "w", {}, log=lambda *a: None) is None


# ----------------------------------------------------------------------------- R2: loop resistance and watts
def test_loop_resistance_counts_copper_plane_return_and_vias_not_bodies():
    lp = P.Loop()
    lp.strip((0, 0), (10, 0), 1.0, 0.2)
    L, R = lp.value_r()
    want = P.r_track(10, 1.0) + P.r_track(10, 1.0 + 2 * math.pi * 0.2)
    assert L > 0 and R == pytest.approx(want)
    lp.body((10, 0), (10, 2), 0.2, 0.5, 0.5)                 # a part's inside: no board resistance
    assert lp.value_r()[1] == pytest.approx(want)
    lp.vert(0, 0, 0.2, 0.0, 0.3, drill=0.3)
    assert lp.value_r()[1] == pytest.approx(want + P.r_via(0.2, 0.3))


def test_parallel_vias_share_resistance():
    def two(n):
        lp = P.Loop()
        lp.strip((0, 0), (5, 0), 0.5, 0.2)
        for i in range(n):
            e = f"v{i}"
            lp.vert(5, 0.6 * i, 0.2, 0.0, 0.3, e, drill=0.3)
            lp.kcl({e: 1.0}) if n == 1 else None
        if n > 1:
            lp.kcl({f"v{i}": 1.0 for i in range(n)})
        return lp.value_r()[1]
    assert two(2) < two(1)


def test_watts_quote_is_loss_loop_plus_loop_ac(tmp_path):
    s = F.session(tmp_path, kinds=("cell",), rails="none", cell_price="W", trim_tol=0.0, place_allocs=False)
    s.route()
    m = next(x for x in s.modules if x.kind == "cell")
    I, f, D, basis = CM.cell_operating(s.ctx, m)
    w = CM.quote(s.ctx, m, store=False)
    L, R = m.physics["value"], m.physics["R_mohm"] * 1e-3
    ph = m.physics
    assert w == pytest.approx(0.5 * L * 1e-9 * I * I * f + ph["W_loop_ac"] + ph["W_swnode"], rel=1e-3)
    # the AC term is the evaluator's I^2 D (1 - D) R plus skin and proximity at f_sw and its harmonics
    assert ph["W_loop_ac"] > ph["W_loop_ac_dc"] == pytest.approx(I * I * D * (1 - D) * R, rel=1e-3)
    assert ph["W_swnode"] >= 0       # the fixture's loop has no switch-node hop (SW runs U1 -> L1 outside it)
    assert 0 < D < 1 and basis


def test_ac_loss_reduces_to_rms_without_skin(monkeypatch):
    monkeypatch.setattr(P, "rac_ratio", lambda f, h=0.1: 1.0)
    for D in (0.2, 0.5, 0.66):
        assert P.ac_loss(2.0, D, 1e6, 0.01, t_r=0.0, n_max=20000) == pytest.approx(4 * D * (1 - D) * 0.01, rel=5e-3)


def test_rac_ratio_follows_the_solved_table():
    assert P.rac_ratio(1e6, 0.1) == pytest.approx(1.59)
    assert P.rac_ratio(1e7, 1.5) == pytest.approx(1.67)
    assert P.rac_ratio(1e3, 0.1) == 1.0 and P.rac_ratio(3e6, 0.1) > P.rac_ratio(1e6, 0.1)


def test_watts_trim_never_narrows_more_than_nh_trim(tmp_path):
    out = {}
    for price in ("L", "W"):
        s = F.session(tmp_path / price, kinds=("cell",), rails="none", cell_price=price, trim_tol=0.05,
                      place_allocs=False)
        s.route()
        m = next(x for x in s.modules if x.kind == "cell")
        out[price] = ({k: rt.width for k, rt in m.hops.items() if rt is not None}, m.physics["R_mohm"])
    for k, w in out["L"][0].items():
        assert out["W"][0].get(k, w) >= w - 1e-9
    assert out["W"][1] <= out["L"][1] + 1e-9


def test_intent_values_drive_the_price(tmp_path):
    s = F.session(tmp_path, kinds=("cell",), rails="none", cell_price="W", place_allocs=False,
                  intent={"cells": {"cell:buck:U1": {"I_A": [2.0, 2.0], "f_sw_Hz": [5e5, 5e5], "D": 0.3}}})
    s.route()
    m = next(x for x in s.modules if x.kind == "cell")
    I, f, D, _ = CM.cell_operating(s.ctx, m)
    assert (I, f, D) == (pytest.approx(2.0), pytest.approx(5e5), pytest.approx(0.3))


# ----------------------------------------------------------------------------- R4: via arrays
def test_via_array_meets_current_spreads_and_stays_out_of_the_strip(tmp_path):
    s = F.session(tmp_path, kinds=("cell",), rails="none", cell_price="W", cell_via_array=True, place_allocs=False,
                  intent={"cells": {"cell:buck:U1": {"I_A": [2.5, 2.5]}}})
    s.route()
    m = next(x for x in s.modules if x.kind == "cell")
    T = m.spec["_T"]
    k = CM._ground_hop(s.ctx, T)
    ta, tb = T[k], T[(k + 1) % len(T)]
    strip = ta.geom.union(tb.geom).convex_hull
    pitch = s.space.same_net_via_pitch("GND")
    allv = []
    for t in (ta, tb):
        vs = m.vias.get(f"via:{t.fp}:{t.pad}") or []
        need = P.vias_needed(2.5, s.space.via_size("GND")[1])
        assert len(vs) >= max(3, need) or any(h["code"] == "vias_below_current" for h in m.hazards)
        allv += vs
    arr = m.spec.get("_array_vias") or []
    assert arr
    for v in arr:                       # the array's own vias (the L-placed return vias may sit anywhere)
        assert v[2] <= 0 or not strip.contains(Point(v[0], v[1]))
    for i, a in enumerate(allv):
        for b in allv[i + 1:]:
            assert math.dist(a[:2], b[:2]) >= pitch - 1e-6
    # every array via is exactly legal against everything committed
    vias = [it for it in s.space.routed if it.kind == "via"]
    for it in vias:
        assert not s.space.via_violations(it.net, it.geom.x, it.geom.y, ignore=[it], first=True)


# ----------------------------------------------------------------------------- R5: keep-out
def test_keepout_covers_the_cell_on_the_return_plane(tmp_path):
    _, rep = _stage(tmp_path, hotloop_keepout=1)
    assert rep["board"] and rep["guards"]
    g = rep["guards"][0]
    assert g["net"] == "GND" and g["layer"] == "B.Cu" and g["name"].startswith(hotloop.GUARD_PREFIX)
    poly = Polygon(g["ring"])
    b = load(tmp_path / "in" / "board.kicad_pcb")
    from shapely.geometry import MultiPoint
    # the hot loop's footprint (its terminals: C1's pads, U1's VIN and GND pins) is mostly guarded; the
    # cell's own pins keep their escape corridors
    c1, u1 = (next(f for f in b.footprints if f.ref == r) for r in ("C1", "U1"))
    loop = MultiPoint([(c1.x, c1.y - 0.95), (c1.x, c1.y + 0.95), (u1.x - 1.31, u1.y + 0.95),
                       (u1.x + 1.31, u1.y + 0.95)]).convex_hull
    assert poly.intersection(loop).area >= 0.3 * loop.area
    assert "kae-crit:hotloop" in (tmp_path / "w" / "hotloop.kicad_pcb").read_text()


def test_keepout_margin_setting(tmp_path):
    _, a = _stage(tmp_path / "a", hotloop_keepout=1, hotloop_keepout_mm=0.5)
    _, b = _stage(tmp_path / "b", hotloop_keepout=1, hotloop_keepout_mm=2.0)
    assert a["keepout"]["cells"][0]["region_mm2"] < b["keepout"]["cells"][0]["region_mm2"]


def test_hard_zones_become_obstacles_in_the_plan(tmp_path):
    from kae.route import constraints
    p = F.write_board(tmp_path / "in")
    info = F.synth_info(load(p))
    ring = [[115, 108], [123, 108], [123, 112], [115, 112], [115, 108]]
    cz = [dict(name="kae-hl:cell:x:VIN", net="VIN", layers={"F.Cu": [[ring]]}, clearance=0.2)]
    assert hotloop.hard_zone("kae-hl:a") and hotloop.hard_zone("kae-crit:b") and not hotloop.hard_zone("GND")
    plan = constraints.plan(info, p, dict(crit_zones=cz))
    assert any(n == "VIN" and "kae-hl:" in why for n, _s, _c, why in plan.net_graphics)


def test_blocked_by_keepout_is_a_decision_and_skips_ground():
    ring = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]
    guards = [dict(net="GND", layer="B.Cu", ring=ring, name="kae-crit:hotloop:cell:buck:U1")]
    rep = dict(unconnected_items=[
        dict(items=[dict(description="Pad 1 [SIG] of R1", pos=dict(x=-1, y=2)),
                    dict(description="Pad 2 [SIG] of R2", pos=dict(x=5, y=2))]),
        dict(items=[dict(description="Pad 1 [GND] of R1", pos=dict(x=-1, y=2)),
                    dict(description="Pad 2 [GND] of R2", pos=dict(x=5, y=2))]),
        dict(items=[dict(description="Pad 1 [FAR] of R1", pos=dict(x=-1, y=9)),
                    dict(description="Pad 2 [FAR] of R2", pos=dict(x=5, y=9))])])
    hz = hotloop.blocked_by_keepout(rep, guards, gnd={"GND"})
    assert [h["objects"][0] for h in hz] == ["SIG"]
    assert hz[0]["code"] == "hotloop_keepout_blocks_route" and hz[0]["decision"]["setting"] == "hotloop_keepout"


# ----------------------------------------------------------------------------- R1 + R3: cells and pours
def test_cells_first_writes_locked_copper(tmp_path):
    from kae.route import critical_write as W
    _, rep = _stage(tmp_path, hotloop_cells=1)
    assert rep["cells"][0]["status"] == "routed" and rep["tracks"] > 0
    assert rep["cells"][0]["R_mohm"] > 0 and rep["cells"][0]["W_loop_ac"] > 0
    items = W.routing(tmp_path / "w" / "hotloop.kicad_pcb")
    assert items and all(r["locked"] for r in items)


def test_pours_never_on_the_switch_node_and_clear_other_pads(tmp_path):
    _, rep = _stage(tmp_path, hotloop_pours=1)
    nets = {r["net"] for r in rep["pours"] if r["area_mm2"] > 0}
    assert nets <= {"VIN", "GND"} and "VIN" in nets
    text = (tmp_path / "w" / "hotloop.kicad_pcb").read_text()
    assert "kae-hl:" in text and "Net-(U1-SW)\")\n\t\t(layer" not in text.split("kae-hl:")[0][-400:]
    # distinct priorities among the pours, above the board's own zones
    import re
    prios = [int(x) for x in re.findall(r'\(name "kae-hl:[^"]*"\)\n\t\t\(hatch edge 0\.5\)\n\t\t\(priority (\d+)\)', text)]
    assert prios and len(set(prios)) == len(prios) and min(prios) >= 1


def test_intent_current_sizes_the_cell_copper(tmp_path):
    """The intent's I_A (upper end) sizes the hops, not the brief's rating-based estimate."""
    lo = F.session(tmp_path / "lo", kinds=("cell",), rails="none", place_allocs=False,
                   intent={"cells": {"cell:buck:U1": {"I_A": [0.1, 0.2]}}})
    hi = F.session(tmp_path / "hi", kinds=("cell",), rails="none", place_allocs=False, trim_tol=0.0,
                   intent={"cells": {"cell:buck:U1": {"I_A": [2.0, 3.0]}}})
    assert CM._intent_current(lo.ctx, CM.Module(id="cell:buck:U1", kind="cell", spec={}, parts=[])) == 0.2
    hi.route()
    m = next(x for x in hi.modules if x.kind == "cell")
    floors = m.spec.get("_floor") or {}
    assert max(floors.values()) >= P.ipc2221_width(3.0) - 1e-6


def test_ground_hop_through_the_plane_is_no_unrouted_hazard():
    m = CM.Module(id="cell:x", kind="cell", spec={}, parts=[], status="partial")
    m.notes.append("hop 2 (GND): returns through the plane")
    assert hotloop.cell_hazards([m]) == []
    m.flags.append(dict(flag="ipc_floor_unroutable", hop=0, net="VIN"))
    assert [h["code"] for h in hotloop.cell_hazards([m])] == ["hotloop_cell_unrouted"]


def test_cell_pin_corridors_open_only_for_open_pins(tmp_path):
    from shapely.ops import unary_union
    p = F.write_board(tmp_path / "in")
    b = load(p)
    s = hotloop._session(p, F.synth_info(b), hotloop.settings(None, {"hotloop_keepout": 1}), {}, lambda *a: None)
    plan, rows, _ = hotloop.keepout_plan(s, hotloop._plan_cells(s), 1.0)
    esc = {x["pad"]: x for x in plan[0]["escapes"]}
    assert {"U1.1", "U1.2", "U1.3", "U1.5", "U1.6", "C1.1"} <= set(esc) and "U1.4" not in esc   # GND: the plane
    region = plan[0]["region"]
    for x in esc.values():                      # each corridor leaves the keep-out
        assert not region.buffer(-1e-3).contains(x["geom"])
    shut = unary_union([Polygon(z[2][0]) for z in hotloop.zones_for(s.board, plan)])
    opened = unary_union([Polygon(z[2][0]) for z in hotloop.zones_for(s.board, plan, {"U1.5"})])
    assert shut.area > opened.area > 0
    u1 = next(f for f in b.footprints if f.ref == "U1")
    from kae.board import transform
    sw = Point(transform.pad_xy(u1, next(q for q in u1.pads if q.number == "5")))
    assert shut.buffer(1e-6).contains(sw) and not opened.contains(sw)
    # exits are short and cheap: no corridor runs mostly under the loop
    assert all(x["cut_mm"] < x["length_mm"] for x in esc.values())
    rep = dict(unconnected_items=[dict(items=[dict(description="Pad 6 [Net-(U1-BST)] of U1 on F.Cu"),
                                              dict(description="Pad 1 [x] of R7 on F.Cu")])])
    assert hotloop.open_cell_pads(rep, plan) == {"U1.6"}


def test_keepout_covers_loop_net_pours_on_every_layer(tmp_path):
    """A pour of a loop net (here VIN on F.Cu) under the cell gets its own keep-out, as the return plane does."""
    from kae.route import critical_write as W
    src = F.write_board(tmp_path / "a")
    ring = [(114.0, 107.0), (124.0, 107.0), (124.0, 113.0), (114.0, 113.0), (114.0, 107.0)]
    p = tmp_path / "b" / "board.kicad_pcb"
    p.parent.mkdir()
    W.append_items(src, p, zones=[("VIN", "F.Cu", [ring], "vin-pour", 0)])
    (tmp_path / "b" / "board.kicad_pro").write_text((tmp_path / "a" / "board.kicad_pro").read_text())
    b = load(p)
    s = hotloop._session(p, F.synth_info(b), hotloop.settings(None, {"hotloop_keepout": 1}), {}, lambda *a: None)
    plan, rows, _ = hotloop.keepout_plan(s, hotloop._plan_cells(s), 1.0)
    assert {("GND", "B.Cu"), ("VIN", "F.Cu")} <= {(e["net"], e["layer"]) for e in plan}
    zs = hotloop.zones_for(s.board, plan)
    vin = [z for z in zs if z[0] == "VIN" and z[1] == "F.Cu"]
    assert vin and all(z[3].startswith(hotloop.GUARD_PREFIX) for z in vin)
    # inside the VIN pour only
    assert all(Polygon(ring).buffer(1e-6).contains(Polygon(z[2][0])) for z in vin)


def test_failed_cell_keeps_its_keepout(tmp_path):
    p = F.write_board(tmp_path / "in")
    s = hotloop._session(p, F.synth_info(load(p)), hotloop.settings(None, {"hotloop_keepout": 1}), {},
                         lambda *a: None)
    mods = hotloop._plan_cells(s)
    for m in mods:
        m.status = "failed"
    plan, _, _ = hotloop.keepout_plan(s, mods, 1.0)
    assert hotloop.zones_for(s.board, plan)


def test_widest_fit_routes_a_hop_with_no_room_at_its_ipc_width(tmp_path):
    big = {"cells": {"cell:buck:U1": {"I_A": [40.0, 40.0]}}}        # an 8 mm hop (rail_max_mm) asked by the current
    off = F.session(tmp_path / "off", kinds=("cell",), rails="none", place_allocs=False, intent=big, rail_max_mm=8.0)
    off.route()
    on = F.session(tmp_path / "on", kinds=("cell",), rails="none", place_allocs=False, intent=big, rail_max_mm=8.0,
                   cell_widest_fit=True)
    on.route()
    mo = next(x for x in off.modules if x.kind == "cell")
    mn = next(x for x in on.modules if x.kind == "cell")
    left = {f["hop"] for f in mo.flags if f["flag"] == "ipc_floor_unroutable"}
    fit = {f["hop"]: f for f in mn.flags if f["flag"] == "widest_fit"}
    assert left and left <= set(fit)
    for k, f in fit.items():
        assert f["width_mm"] < f["floor_mm"] and mn.hops[f"hop{k}"] is not None
    assert not [f for f in mn.flags if f["flag"] == "ipc_floor_unroutable"]


def test_guards_copy_the_planes_pad_connection_and_lift_locally(tmp_path):
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    p = F.write_board(tmp_path / "in")
    s = hotloop._session(p, F.synth_info(load(p)), hotloop.settings(None, {"hotloop_keepout": 1}), {},
                         lambda *a: None)
    plan, _, _ = hotloop.keepout_plan(s, hotloop._plan_cells(s), 1.0)
    full = hotloop.zones_for(s.board, plan)
    assert full and full[0][6].get("connect") == "thermal"     # the fixture's GND pour: thermal reliefs
    e = next(e for e in plan if e["plane"])
    seg = LineString([(e["region"].bounds[0] - 1, e["region"].centroid.y),
                      (e["region"].bounds[2] + 1, e["region"].centroid.y)])
    e["cuts"] = [seg.buffer(hotloop.CROSS_HALF_MM, cap_style=2)]
    crossed = unary_union([Polygon(z[2][0]) for z in hotloop.zones_for(s.board, plan)])
    assert not crossed.intersects(seg.buffer(0.1)) and crossed.area > 0
    e["lifted"] = True
    assert not [z for z in hotloop.zones_for(s.board, plan) if z[1] == e["layer"] and z[0] == e["net"]]


def test_open_pairs_and_lift_setting(monkeypatch):
    rep = dict(unconnected_items=[dict(items=[dict(description="Pad 1 [A] of R1", pos=dict(x=0, y=0)),
                                              dict(description="Pad 2 [A] of R2", pos=dict(x=3, y=4))])])
    (net, seg), = hotloop._open_pairs(rep)
    assert net == "A" and seg.length == pytest.approx(5.0)
    monkeypatch.delenv("KAE_HOTLOOP_LIFT", raising=False)
    assert hotloop.settings(None, {})["lift"] == "plane"
    assert hotloop.settings(None, {"hotloop_lift": "corridors"})["lift"] == "corridors"
    assert hotloop.settings(None, {"hotloop_lift": "bogus"})["lift"] == "plane"


def test_loopvias_leave_room_for_the_loops_own_vias_beside_their_pads(tmp_path):
    """hotloop_keepout_loopvias: the ground plane's keep-out gets via-sized holes beside the loop's VIN pads (C1.1,
    U1.3), so the loop's own vias can drop there; nothing else changes, and without the setting there are none."""
    from shapely.ops import unary_union
    p = F.write_board(tmp_path / "in")
    b = load(p)
    on = hotloop.settings(None, {"hotloop_keepout": 1, "hotloop_keepout_loopvias": 1})
    assert on["keepout_loopvias"] and not hotloop.settings(None, {"hotloop_keepout": 1})["keepout_loopvias"]
    s = hotloop._session(p, F.synth_info(b), on, {}, lambda *a: None)
    s.hotloop_loopvias_on = True
    plan, _, _ = hotloop.keepout_plan(s, hotloop._plan_cells(s), 1.0)
    gnd = next(e for e in plan if e["net"] == "GND" and e["plane"])
    assert len(gnd["holes"]) == 8                               # 4 sites at each of the two VIN terminals
    shut = unary_union([Polygon(z[2][0]) for z in hotloop.zones_for(s.board, [dict(gnd, holes=[])])])
    holed = unary_union([Polygon(z[2][0]) for z in hotloop.zones_for(s.board, [gnd])])
    assert 0 < holed.area < shut.area and shut.area - holed.area < 0.35 * shut.area
    from kae.board import transform
    c1 = next(f for f in b.footprints if f.ref == "C1")
    vin = Point(transform.pad_xy(c1, next(q for q in c1.pads if q.number == "1")))
    assert any(h.distance(vin) < 1.0 for h in gnd["holes"])
    s2 = hotloop._session(p, F.synth_info(b), hotloop.settings(None, {"hotloop_keepout": 1}), {}, lambda *a: None)
    plan2, _, _ = hotloop.keepout_plan(s2, hotloop._plan_cells(s2), 1.0)
    assert all(not e["holes"] for e in plan2)


def test_clear_regions_and_foreign_copper(tmp_path):
    """design D: the cell's region, its clear layers and the nets that are never foreign."""
    p = F.write_board(tmp_path / "in")
    s = hotloop._session(p, F.synth_info(load(p)), hotloop.settings(None, {"hotloop_clear": 1}), {},
                         lambda *a: None)
    regs = hotloop.clear_regions(s, hotloop._plan_cells(s), 1.0)
    assert len(regs) == 1
    r = regs[0]
    assert r["layers"].get("B.Cu") == "GND"
    assert {"VIN", "GND"} <= r["own"] and "Net-(U1-BST)" in r["pins"] and "Net-(U1-BST)" not in r["own"]
    c = r["region"].centroid
    routing = [
        dict(kind="segment", uuid="a", net="Net-(U2-XTAL1)", layer="B.Cu", a=[c.x - 5, c.y], b=[c.x + 5, c.y],
             width=0.2, locked=False),
        dict(kind="segment", uuid="b", net="Net-(U2-XTAL1)", layer="F.Cu", a=[c.x - 5, c.y], b=[c.x + 5, c.y],
             width=0.2, locked=False),                      # not a clear layer here
        dict(kind="segment", uuid="c", net="VIN", layer="B.Cu", a=[c.x - 5, c.y], b=[c.x + 5, c.y], width=0.2,
             locked=False),                                 # the loop's own copper: never touched
        dict(kind="via", uuid="d", net="+3V3", pos=[c.x, c.y], size=0.6, locked=False),
        dict(kind="via", uuid="e", net="Net-(U2-XTAL2)", pos=[c.x, c.y], size=0.6, locked=True),   # locked: kept
    ]
    routing.append(dict(kind="segment", uuid="f", net="Net-(U1-BST)", layer="B.Cu", a=[c.x - 5, c.y],
                        b=[c.x + 5, c.y], width=0.2, locked=False))      # a cell pin's net on the return: ripped
    if r["side"] in r["layers"]:
        routing.append(dict(kind="segment", uuid="g", net="Net-(U1-BST)", layer=r["side"], a=[c.x - 5, c.y],
                            b=[c.x + 5, c.y], width=0.2, locked=False))  # its fan-out on the parts' layer: kept
    got = {x["uuid"] for x, _ in hotloop._foreign(routing, r)}
    assert "a" in got and "b" not in got and "c" not in got and "e" not in got and "f" in got and "g" not in got
    assert ("d" in got) == ("+3V3" not in r["own"])


def test_clear_setting_parses(monkeypatch):
    monkeypatch.delenv("KAE_HOTLOOP_CLEAR", raising=False)
    st = hotloop.settings(None, {})
    assert not st["clear"] and not hotloop.active(st)
    st = hotloop.settings(None, {"hotloop_clear": 1})
    assert st["clear"] and not hotloop.active(st)          # D routes as N: no stage, no keep-outs


def test_clear_hook_defers_to_a_portfolio_that_clears_the_kept_board(tmp_path, monkeypatch):
    """KAE_CLEAR_KEPT=1 (tools/kaeres/restart.py --clear): an attempt or final pass does not clear its own board."""
    from kae.route import bridge
    board = tmp_path / "board.kicad_pcb"
    board.write_text("(kicad_pcb)\n")
    monkeypatch.setenv("KAE_HOTLOOP_CLEAR", "1")
    monkeypatch.setenv("KAE_CLEAR_KEPT", "1")
    rep = bridge.clear_hook(board, board, tmp_path / "wd", {}, deadline=None)
    assert rep == dict(cells=[], skipped="deferred: the restart portfolio clears the kept board")
    monkeypatch.delenv("KAE_HOTLOOP_CLEAR")
    assert bridge.clear_hook(board, board, tmp_path / "wd", {}, deadline=None) is None


def test_pour_check_names_a_cell_for_every_pad_it_cut_and_reports_after_the_revert(tmp_path, monkeypatch):
    """giacobot: one cell's copper cut two LX pads off their pours. Reverting it for the first pad
    restores both, so neither hazard may say that no cell was reverted, and both say the pad touches
    its pour again."""
    from types import SimpleNamespace as NS
    from shapely.geometry import LineString
    from kae.route import critical_joint
    sq = lambda x0, y0, x1, y1: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    info = dict(pads=[dict(uuid="p7", ref="U2", number="7", net="LX2"),
                      dict(uuid="p9", ref="U2", number="9", net="LX1")],
                zones=[dict(net="LX2", layers=["F.Cu"], rings=[[sq(0, 0, 2, 2)]], clearance=0.2),
                       dict(net="LX1", layers=["F.Cu"], rings=[[sq(4, 0, 6, 2)]], clearance=0.2)])
    gnd = NS(net="GND", layers=("F.Cu",), width=0.3, geom=LineString([(1, 1), (5, 1)]))   # through both pours
    cell = NS(id="cell:buck:U2", copper=[gnd], status="routed", notes=[])
    other = NS(id="cell:boost:U2", copper=[NS(net="GND", layers=("F.Cu",), width=0.3,
                                             geom=LineString([(10, 10), (11, 10)]))], status="routed", notes=[])
    before = {("p7", "F.Cu"), ("p9", "F.Cu")}
    monkeypatch.setattr(hotloop, "_pad_fill_contacts",
                        lambda path, info: before if cell.status == "reverted" else set())
    monkeypatch.setattr(critical_joint, "_rip", lambda s, m: setattr(m, "copper", []))
    s = NS(write=lambda p: None)
    hz, gone = hotloop.pour_check(s, None, info, [cell, other], tmp_path, log=lambda *a: None, before=before)
    assert gone == [] and cell.status == "reverted" and other.status == "routed"
    assert [h["evidence"]["reverted"] for h in hz] == [["cell:buck:U2"], ["cell:buck:U2"]]
    assert all(h["evidence"]["restored"] and "touches its pour again" in h["message"] for h in hz)
    assert not any("none was reverted" in h["message"] for h in hz)
