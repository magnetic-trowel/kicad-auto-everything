# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.critical without KiCad: physics of routed loops, the Space's rules (the
bridge's effective rules), the grid router's exact legality, module routing, the writer,
the recheck's copper graph and the joint optimizer, on a synthetic board
(critical_fixtures). KiCad's own verdict is in test_route_critical_kicad.py."""
import math

import pytest
from shapely.geometry import LineString

import critical_fixtures as F
from kae.physics import fastloop as FL
from kae.route import critical_write as W
from kae.route.critical_grid import Anchor
from kae.route.critical_physics import Loop, drop_width, ipc2221_width, r_track


# ----------------------------------------------------------------------------- physics
def test_ipc2221_and_drop_widths():
    assert ipc2221_width(1.0) == pytest.approx(0.30, abs=0.01)       # high-current.md: 1 A, 10 K, 1 oz
    assert ipc2221_width(5.0) == pytest.approx(2.77, abs=0.05)
    w = drop_width(1.0, 50.0, 0.033)
    assert r_track(50.0, w) * 1.0 == pytest.approx(0.033, rel=1e-9)  # the width meets the budget exactly


def test_loop_series_equals_fastloop():
    H = [(0, 0, 4, 0, 1.0, 0.2), (4, 0, 4, 2, 1.0, 0.2), (4, 2, 0, 2, 1.0, 0.2), (0, 2, 0, 0, 1.0, 0.2)]
    lp = Loop()
    for x0, y0, x1, y1, w, h in H:
        lp.strip((x0, y0), (x1, y1), w, h)
    assert lp.value() == pytest.approx(FL.loop_fast(H, []), rel=1e-12)


def _via_loop(n_pairs, h=0.2, w=0.5):
    lp = Loop()
    lp.strip((0, 0), (4, 0), w, h)
    ka, kb = {}, {}
    for i in range(n_pairs):
        a, b = f"a{i}", f"b{i}"
        lp.strip((4, 0), (4, 0.7 * i), w, h, a)
        lp.vert(4, 0.7 * i, h, 0.0, 0.15, a)
        lp.vert(0, 0.7 * i, 0.0, h, 0.15, b)
        lp.strip((0, 0.7 * i), (0, 0), w, h, b)
        ka[a] = kb[b] = 1.0
    lp.kcl(ka)
    lp.kcl(kb)
    return lp


def test_parallel_return_vias_lower_the_loop_and_obey_kcl():
    l1 = _via_loop(1).value()
    l2, sh = _via_loop(2).value(shares=True)
    assert 0 < l2 < l1
    assert sh["a0"] + sh["a1"] == pytest.approx(1.0) and sh["b0"] + sh["b1"] == pytest.approx(1.0)
    assert sh["a0"] > sh["a1"]                    # the nearer via carries more


def test_loop_falls_with_width_and_plane_height():
    def rect(w, h):
        lp = Loop()
        lp.path([(0, 0), (5, 0), (5, 3), (0, 3), (0, 0)], w, h)
        return lp.value()
    assert rect(1.0, 0.2) < rect(0.3, 0.2)
    assert rect(0.5, 0.1) < rect(0.5, 0.4) < rect(0.5, 1.5) < rect(0.5, math.inf)


# ----------------------------------------------------------------------------- the space
@pytest.fixture(scope="module")
def routed(tmp_path_factory):
    s = F.session(tmp_path_factory.mktemp("crit"))
    s.route()
    return s


def test_space_uses_the_bridges_effective_rules(tmp_path):
    s = F.session(tmp_path)
    sp, eff = s.space, s.space.eff
    for net in ("VIN", "GND", "+3V3"):
        w = eff.track_width(net, "F.Cu")
        assert sp.width_limits(net, "F.Cu") == (w.min, max(w.opt, w.min), w.max)
        v = eff.via(net)
        assert sp.via_size(net) == (v.diameter, v.drill)
        assert sp.same_net_via_pitch(net) == eff.same_net_via_pitch(net)
    # a pad's requirement is its clearance class, as effective.Rules.pad_clearance reads it
    pad = next(it for it in sp.pads if it.owner == ("U2", "8"))
    c = eff.pad_clearance("GND", "F.Cu", "U2", "8")
    assert sp.need(pad, "GND", "track", "F.Cu") == c.track
    assert sp.need(pad, "GND", "via", "F.Cu") == c.via
    assert sp.need(pad, "+3V3", "track", "F.Cu") is None          # same net: no clearance


def test_grid_route_is_exactly_legal(tmp_path):
    s = F.session(tmp_path)
    sp, gr = s.space, s.router
    a = sp.terminal(_uuid(s, "C3"), ["1"])
    b = sp.terminal(_uuid(s, "U2"), ["8"])
    rt = gr.connect("+3V3", [Anchor(a.geom, a.layers, (a.x, a.y))], [Anchor(b.geom, b.layers, (b.x, b.y))], 0.3,
                    ["F.Cu"], via=False)
    assert rt is not None and rt.segs
    for l, p, q in rt.segs:
        assert not sp.track_violations("+3V3", l, rt.width, p, q)
    # ends on the pads
    assert a.geom.distance(LineString([rt.segs[0][1], rt.segs[0][2]])) < 1e-6
    # a width that cannot pass between the IC's pins on the way out is refused or detours legally
    rt2 = gr.connect("+3V3", [Anchor(a.geom, a.layers, (a.x, a.y))], [Anchor(b.geom, b.layers, (b.x, b.y))], 2.5,
                     ["F.Cu"], via=False)
    if rt2 is not None:
        for l, p, q in rt2.segs:
            assert not sp.track_violations("+3V3", l, rt2.width, p, q)


def _uuid(s, ref):
    return next(f.uuid for f in s.board.footprints if f.ref == ref)


def test_session_routes_every_module_legally(routed):
    s = routed
    status = {m.kind: m.status for m in s.modules}
    assert status == {"cell": "routed", "decap": "routed", "crystal": "routed", "chain": "routed"}
    sp = s.space
    for it in sp.routed:
        others = [x for x in sp.routed if x is not it]
        l = next(iter(it.layers))
        if it.kind == "track":
            a, b = it.geom.coords[0], it.geom.coords[-1]
            assert not sp.track_violations(it.net, l, it.width, a, b, ignore=others), it.owner
        else:
            assert not sp.via_violations(it.net, it.geom.x, it.geom.y, ignore=others + [it]), it.owner
    cell = next(m for m in s.modules if m.kind == "cell")
    assert cell.physics["unit"] == "nH" and 0 < cell.physics["value"] < 50
    # the hot loop's VIN hop is as wide as its terminals allow, never narrower than the class
    vin = next(rt for k, rt in cell.hops.items() if rt is not None and rt.net == "VIN")
    assert vin.width >= sp.width_limits("VIN", "F.Cu")[1]


def test_protection_order_connector_protector_ic(routed):
    s = routed
    ch = next(m for m in s.modules if m.kind == "chain")
    T = ch.spec["_T"]
    refs = [s.ctx.fp[t.fp].ref for t in T]
    assert refs.index("J1") < refs.index("D1") < refs.index("U1")
    assert ch.hops.get("hop0") is not None              # connector -> TVS is a routed hop


def test_crystal_and_decap_vias_reach_the_ground_pour(routed):
    s = routed
    for kind in ("crystal", "decap"):
        ms = [m for m in s.modules if m.kind == kind]
        vias = [it for m in ms for it in m.copper if it.kind == "via"]
        assert vias, kind
        for v in vias:
            assert s.space.zone_covers(v.net, "B.Cu", v.geom.x, v.geom.y)


def test_rails_size_from_current_and_skip_light_rails(routed):
    rails = {r["net"]: r for r in routed.rails if "design_A" in r}
    assert rails["+3V3"]["routed"] is False                  # 20 mA of ATtiny: the class width carries it
    assert rails["+3V3"]["design_A"] < rails["+3V3"]["rating_A"]   # loads with margin, capped by the source
    assert rails["VIN"]["design_A"] >= 1.0


# ----------------------------------------------------------------------------- writer
def test_writer_appends_locked_copper_and_transplants(routed, tmp_path):
    s = routed
    out = tmp_path / "out.kicad_pcb"
    nt, nv = s.write(out)
    items = W.routing(out)
    assert len(items) == nt + nv and all(r["locked"] for r in items)
    # transplant onto the input: input + routing, nothing else
    dst = tmp_path / "t.kicad_pcb"
    n = W.transplant(out, s.path, dst)
    assert n == nt + nv
    assert len(W.routing(dst)) == n                      # and the transplant reads back
    assert dst.read_text().replace("", "").count("(footprint") == s.path.read_text().count("(footprint")
    # unlock, remove
    W.edit(out, tmp_path / "u.kicad_pcb", unlock="all", remove=[items[0]["uuid"]])
    r2 = W.routing(tmp_path / "u.kicad_pcb")
    assert len(r2) == len(items) - 1 and not any(r["locked"] for r in r2)


def test_guard_zones_are_dropped(routed, tmp_path):
    s = routed
    a = tmp_path / "a.kicad_pcb"
    W.append_items(s.path, a, zones=[("GND", "B.Cu", [[(110, 110), (115, 110), (115, 115), (110, 115)]],
                                      W.GUARD_PREFIX + "cell")])
    assert W.GUARD_PREFIX in a.read_text()
    W.edit(a, tmp_path / "b.kicad_pcb", drop_guards=True)
    assert W.GUARD_PREFIX not in (tmp_path / "b.kicad_pcb").read_text()


# ----------------------------------------------------------------------------- recheck
def test_board_physics_reads_the_routed_copper(routed, tmp_path):
    from kae.route.critical_recheck import board_physics
    out = tmp_path / "out.kicad_pcb"
    routed.write(out)
    ph = board_physics(out, brief=routed.brief, fills=None)
    cell = next(v for k, v in ph.items() if k.startswith("cell:"))
    assert cell["open_hops"] == 0 and cell["value"] > 0
    # the unrouted input: every hop open, and its loop estimated on straight hops
    ph0 = board_physics(routed.path, brief=routed.brief, fills=None)
    cell0 = next(v for k, v in ph0.items() if k.startswith("cell:"))
    assert cell0["open_hops"] >= 1


# ----------------------------------------------------------------------------- joint
def test_joint_moves_are_legal_and_improve_the_routed_loop(tmp_path):
    from kae.board.kicad_file import load
    from kae.route.critical import Session
    from kae.route.critical_joint import Legality, optimize_modules
    p = F.write_board(tmp_path)
    b = load(p)
    s = Session(p, info=F.synth_info(b), board=b, log=lambda *a: None)
    poses, copper, rep = optimize_modules(b, s.brief, terms=None, locked=set(), session=s, time_s=120)
    cell = next(m for m in rep["modules"] if m["kind"] == "cell")
    assert cell["value"] <= cell["value0"]
    leg = Legality(s)        # the session's space now holds the final poses
    for u, pose in poses.items():
        assert pose[3] == next(f.side for f in b.footprints if f.uuid == u)
    assert copper


def test_heatsink_mount_keeps_right_angles(tmp_path):
    from kae.route.critical_joint import candidates, heatsink_mount
    s = F.session(tmp_path)
    f = next(fp for fp in s.board.footprints if fp.ref == "J1")
    f.lib_id = "Package_TO_SOT_THT:TO-220-3_Vertical"
    assert heatsink_mount(f)
    m = next(x for x in _mods(s) if x.kind == "chain")
    for c in candidates(s, m, f.uuid, (f.x, f.y, f.rot, f.side), right_angles=True):
        assert c[2] % 90.0 == pytest.approx(0.0, abs=1e-9) or c[2] % 90.0 == pytest.approx(90.0, abs=1e-9)


def _mods(s):
    from kae.route.critical_modules import modules_from_brief
    return modules_from_brief(s.brief)


# ----------------------------------------------------------------------------- guards, plane cover
def test_guards_cover_the_ground_plane_under_the_cell(routed):
    from shapely.geometry import Point, Polygon
    g = routed.guards()
    cell = next(m for m in routed.modules if m.kind == "cell")
    mine = [x for x in g if x[3] == W.GUARD_PREFIX + cell.id]
    assert mine and all(x[0] == "GND" and x[1] == "B.Cu" for x in mine)
    poly = Polygon(mine[0][2][0])
    for t in cell.spec["_T"]:                            # the hot loop's terminals are under it
        assert poly.contains(Point(t.x, t.y))
    assert poly.area < 0.25 * 40 * 30                    # the loop's hull, not the board


def test_recheck_flags_a_perforated_plane(routed, tmp_path):
    from shapely.geometry import box
    from kae.route.critical_recheck import board_physics, recheck
    out = tmp_path / "out.kicad_pcb"
    routed.write(out)
    gz = next(z for z in routed.board.zones if z.net == "GND" and "B.Cu" in z.layers)
    whole = {"GND": {"B.Cu": [gz.outline]}}
    ph = board_physics(out, brief=routed.brief, fills=whole)
    cid = next(k for k in ph if k.startswith("cell:"))
    assert ph[cid]["plane_cover"] == pytest.approx(1.0)
    # another net's track on B.Cu slices the plane under the hot loop
    T = next(m for m in routed.modules if m.kind == "cell").spec["_T"]
    cx = sum(t.x for t in T) / len(T)
    ys = [t.y for t in T]
    cut = gz.outline.difference(box(cx - 0.4, min(ys) - 5, cx + 0.4, max(ys) + 5))
    stage = {cid: dict(u=ph[cid]["u"], plane_cover=ph[cid]["plane_cover"])}
    rc = recheck(out, routed.brief, stage, fills={"GND": {"B.Cu": [cut]}})
    assert cid in rc["retweak"] and rc["modules"][cid]["cover_routed"] < 0.9
    assert rc["modules"][cid]["value"] >= ph[cid]["value"]       # and the loop does not get better
    assert recheck(out, routed.brief, stage, fills=whole)["retweak"] == []


def test_overlapping_alternatives_stay_physical():
    """Two return paths leaving one pad side by side (their closed-form mutual exceeds the
    self terms): the loop stays positive and no path carries reverse current."""
    lp = Loop()
    lp.path([(4, 0.5), (4, 3), (0, 3), (0, 0)], 1.0, 0.2)   # forward path, series
    lp.strip((0, 0), (0.5, 0.8), 0.6, 0.2, "va")           # surface stub to a via down
    lp.vert(0.5, 0.8, 0.2, 0.0, 0.15, "va")
    lp.strip((0, 0), (0.25, 0.35), 1.4, 0.2, "lat")         # wide surface return, nearly on top of it
    lp.strip((0.25, 0.35), (4, 0.5), 1.4, 0.2, "lat")
    lp.vert(3.5, 0.2, 0.0, 0.2, 0.15, "vb")                # via up at the far end
    lp.strip((3.5, 0.2), (4, 0.5), 0.6, 0.2, "vb")
    lp.kcl({"va": 1.0, "lat": 1.0})
    lp.kcl({"vb": 1.0, "lat": 1.0})
    val, sh = lp.value(shares=True)
    assert 0 < val < 50 and all(x > -1e-9 for x in sh.values())
    assert sh["va"] + sh["lat"] == pytest.approx(1.0) and sh["vb"] + sh["lat"] == pytest.approx(1.0)
