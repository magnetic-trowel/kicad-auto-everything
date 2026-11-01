# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.critical without KiCad: physics of routed loops, the Space's rules (the
bridge's effective rules), the grid router's exact legality, module routing, the writer,
the recheck's copper graph and the joint optimizer, on a synthetic board
(critical_fixtures). KiCad's own verdict is in test_route_critical_kicad.py."""
import math
from pathlib import Path

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
    assert all(m["value"] is None or m["value"] > 0 for m in rep["modules"])   # never chases a negative L
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
    mine = [x for x in g if x[3].startswith(W.GUARD_PREFIX + cell.id)]     # merged guards keep the first name
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


# ----------------------------------------------------------------------------- regressions
def test_decap_on_the_far_side_routes_through_a_via(tmp_path):
    s = F.session(tmp_path, back=("C3",))           # IC on top, its decap on the bottom
    s.route()
    m = next(x for x in s.modules if x.id == "decap:U2:+3V3")
    rt = next(v for k, v in m.hops.items() if k.startswith("rail:"))
    assert m.status == "routed" and rt is not None and len(rt.vias) == 1
    assert {l for l, _, _ in rt.segs} == {"F.Cu", "B.Cu"}
    sp = s.space
    # the IC's ground pin reaches the pour the capacitor sits in
    gv = [it for it in m.copper if it.kind == "via" and it.net == "GND"]
    tG = sp.terminal(next(f.uuid for f in s.board.footprints if f.ref == "U2"), ["4"])
    assert gv and min(it.geom.distance(tG.geom) for it in gv) < 1.5
    for it in m.copper:
        others = [x for x in sp.routed if x is not it]
        if it.kind == "track":
            l = next(iter(it.layers))
            assert not sp.track_violations(it.net, l, it.width, it.geom.coords[0], it.geom.coords[-1], ignore=others)
        else:
            assert not sp.via_violations(it.net, it.geom.x, it.geom.y, ignore=others + [it])


def test_move_margin_keeps_grid_moves_legal_and_small():
    import random
    from kae.route.critical_grid import _margin
    rnd = random.Random(1)
    res = 0.05
    for _ in range(4000):
        R = rnd.uniform(0.05, 1.0)
        m = _margin(R, res)
        a = (rnd.uniform(-1, 1), rnd.uniform(-1, 1))
        dx, dy = rnd.choice([(1, 0), (0, 1), (1, 1), (1, -1)])
        b = (a[0] + dx * res, a[1] + dy * res)
        p = (rnd.uniform(-1.5, 1.5), rnd.uniform(-1.5, 1.5))
        if math.dist(a, p) >= R + m and math.dist(b, p) >= R + m:      # both cells free
            assert LineString([a, b]).distance(__import__("shapely").geometry.Point(p)) >= R - 1e-12
    assert _margin(0.3, res) < 0.005            # a flat 0.71 cell (35 um) closes 0.5 mm-pitch gaps


def test_far_decaps_are_skipped_not_failed(tmp_path):
    s = F.session(tmp_path, decap_max_mm=0.5)
    s.route()
    for m in s.modules:
        if m.kind == "decap":
            assert m.status == "skipped" and not m.copper


def test_mixed_plane_heights_give_a_finite_loop():
    def loop(h_last):
        lp = Loop()
        for (a, b), h in zip((((0, 0), (4, 0)), ((4, 0), (4, 2)), ((4, 2), (0, 2)), ((0, 2), (0, 0))),
                             (0.2, 0.2, 0.2, h_last)):
            lp.strip(a, b, 0.5, h)
        return lp.value()
    v = loop(math.inf)                        # one strip over no plane
    assert math.isfinite(v) and v > loop(0.2)


def test_recheck_survives_degenerate_decap_loops(routed, tmp_path, monkeypatch):
    from kae.route import critical_recheck as RC
    out = tmp_path / "out.kicad_pcb"
    routed.write(out)
    monkeypatch.setattr(RC.Loop, "value", lambda self, shares=False: 0.0)
    ph = RC.board_physics(out, brief=routed.brief, fills=None)
    for k, v in ph.items():
        if k.startswith("decap:"):
            assert "error" not in v and v.get("value") is None


def test_quote_rejects_nonphysical_values(routed, monkeypatch):
    from kae.route import critical_modules as CM
    cell = next(m for m in routed.modules if m.kind == "cell")
    monkeypatch.setattr(CM, "_cell_value", lambda ctx, m: (-1.0, {}))
    assert CM.quote(routed.ctx, cell, store=False) is None
    assert any("rejected" in n for n in cell.notes)


def test_guard_zones_avoid_other_nets_and_outrank_planes():
    from types import SimpleNamespace as NS
    from shapely.geometry import Polygon, box
    from kae.route.critical_recheck import guard_zones
    gnd = NS(net="GND", layers=["B.Cu"], outline=box(0, 0, 20, 20), name="", priority=0)
    vcc = NS(net="+3V3", layers=["B.Cu"], outline=box(8, 8, 12, 12), name="", priority=1)
    top = NS(net="VIN", layers=["F.Cu"], outline=box(0, 0, 20, 20), name="", priority=3)
    g = guard_zones(NS(zones=[gnd, vcc, top]), box(5, 5, 15, 15), "GND", "B.Cu", "kae-crit:x")
    assert g and all(z[0] == "GND" and z[1] == "B.Cu" and z[4] == 2 for z in g)   # above both B.Cu zones
    for z in g:
        poly = Polygon(z[2][0])
        assert poly.intersection(vcc.outline).area == 0 and poly.within(gnd.outline.buffer(1e-9))


def test_retweak_watches_only_routed_modules():
    from types import SimpleNamespace as NS
    from kae.route.critical_recheck import routed_stage
    sess = NS(modules=[NS(id="a", status="routed"), NS(id="b", status="skipped"), NS(id="c", status="partial")])
    assert set(routed_stage({"a": 1.0, "b": 2.0, "c": 0.5, "d": 0.1}, sess)) == {"a", "c"}


def test_run_retries_the_bridge_when_it_returns_nothing(tmp_path, monkeypatch):
    import shutil
    from kae.board import pcbnew_io
    from kae.board.kicad_file import load
    from kae.route import bridge as BR
    from kae.route import critical
    src = F.write_board(tmp_path / "in")
    monkeypatch.setattr(pcbnew_io, "export_dsn", lambda path, dsn, *a, **k: F.synth_info(load(path)))
    calls = []

    def fake_route(inp, out, seed=0, time_s=0.0, workdir=None, opts=None, log=None):
        calls.append(time_s)
        if len(calls) == 1:
            return dict(status="no_session")      # Freerouting killed at its deadline
        assert W.GUARD_PREFIX in Path(inp).read_text()      # the bridge sees the guards
        shutil.copy(inp, out)
        return dict(status="routed")
    monkeypatch.setattr(BR, "route", fake_route)
    out = tmp_path / "out" / "board.kicad_pcb"
    rep = critical.run(src, out, time_s=300, log=lambda *a: None)
    assert len(calls) == 2 and calls[1] > 0.5 * calls[0] and rep["bridge"]["status"] == "routed"
    assert W.GUARD_PREFIX not in out.read_text() and len(W.routing(out)) == rep["critical"]["tracks"] + rep["critical"]["vias"]


def test_overlapping_guards_merge_into_one_layer_of_pours():
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    from kae.route.critical_recheck import merge_guards
    a = ("GND", "B.Cu", [list(box(0, 0, 4, 4).exterior.coords)], "kae-crit:cell:a", 1)
    b = ("GND", "B.Cu", [list(box(3, 3, 7, 7).exterior.coords)], "kae-crit:crystal:b", 1)
    c = ("GND", "In1.Cu", [list(box(0, 0, 2, 2).exterior.coords)], "kae-crit:cell:a", 3)
    g = merge_guards([a, b, c])
    bl = [Polygon(z[2][0]) for z in g if z[1] == "B.Cu"]
    for i, p in enumerate(bl):                       # no two pieces on one layer overlap
        for q in bl[i + 1:]:
            assert p.intersection(q).area < 1e-9
    assert unary_union(bl).area == pytest.approx(16 + 16 - 1)
    assert [z[4] for z in g if z[1] == "In1.Cu"] == [3]


def test_joint_never_moves_locked_parts(tmp_path):
    from kae.board.kicad_file import load
    from kae.route.critical import Session
    from kae.route.critical_joint import optimize_modules
    p = F.write_board(tmp_path)
    b = load(p)
    s = Session(p, info=F.synth_info(b), board=b, log=lambda *a: None)
    keep = {f.uuid for f in b.footprints if f.ref in ("C1", "U1", "C3", "Y1")}
    poses, copper, rep = optimize_modules(b, s.brief, terms=None, locked=keep, session=s, time_s=60)
    assert not set(poses) & keep


def test_corridor_failure_is_reported_not_hidden(tmp_path, monkeypatch):
    from kae.route import constraints as CN
    def boom(*a, **k):
        raise RuntimeError("no spokes today")
    monkeypatch.setattr(CN, "thermal_corridors", boom)
    s = F.session(tmp_path)
    assert any("thermal corridors unavailable" in n for n in s.report()["space_notes"])


def test_castellated_pad_anchors_keep_each_layers_copper(tmp_path):
    """A pad number with a through-hole pad and an SMD twin on F.Cu: a route may end on the
    twin only on F.Cu (a B.Cu end there was a dangling track in KiCad's DRC)."""
    from shapely.geometry import Point
    from kae.route.critical_modules import anchor
    s = F.session(tmp_path, twin=True)
    j1 = next(f for f in s.board.footprints if f.ref == "J1")
    t = s.space.terminal(j1.uuid, ["1"])
    assert set(t.layers) == {"F.Cu", "B.Cu"} and len(t.items) == 2
    twin = Point(j1.x + 1.9, j1.y - 1.0)                  # inside the SMD twin only
    a = anchor(t)
    assert a.geom_on("F.Cu").contains(twin) and not a.geom_on("B.Cu").contains(twin)
    for l in t.layers:                                     # a stub start lies on that layer's copper
        assert a.geom_on(l).distance(Point(a.centre_on(l))) < 1e-9
    gr = s.router
    grid = gr.window([a])
    cost = gr.cost_layer(grid, "VIN", "B.Cu", 0.25)[None]
    ks = gr._cells(grid, a, 0, cost, grid.nx * grid.ny, "B.Cu")
    xs = [grid.xy(int(k % grid.nx), int(k // grid.nx)) for k in ks]
    assert xs and all(not twin.buffer(0.3).contains(Point(p)) for p in xs)


def test_chain_tail_is_left_to_the_bridge(tmp_path):
    s = F.session(tmp_path)                            # default: no locked copper after the protector
    s.route()
    ch = next(m for m in s.modules if m.kind == "chain")
    T = ch.spec["_T"]
    refs = [s.ctx.fp[t.fp].ref for t in T]
    k = refs.index("D1")
    assert ch.hops.get("hop0") is not None                         # connector -> protector, routed
    assert all(f"hop{j}" not in ch.hops for j in range(k, len(T) - 1))   # nothing after the protector
    assert any("after the protector" in n for n in ch.notes)


def _rail_islands(tmp_path, reach):
    from shapely.ops import unary_union
    s = F.session(tmp_path, rails="all", rail_complete_mm=reach)
    s.route()
    sp = s.space
    out = []
    for r in s.rails:
        if not (r.get("routed") and r.get("items")):
            continue
        net = r["net"]
        f = next(f for f in s.board.footprints if f.ref == r["source"])
        st = sp.terminal(f.uuid, [p.number for p in f.pads if p.net == net])
        comp = sp.component(net, [(st.geom, st.layers)])
        ids = {id(x) for x in comp}
        geo = unary_union([x.geom.buffer(x.r) if x.r > 0 else x.geom for x in comp])
        out += [it.owner for it in sp.pads if it.net == net and it.kind == "pad" and id(it) not in ids
                and geo.distance(it.geom) <= 20.0]
    return out, s


def test_routed_rails_leave_no_nearby_islands(tmp_path):
    """A routed rail joins the rest of its net's pads within reach itself: Freerouting left
    such islands unrouted rather than join the middle of a fixed track (bipolar supply)."""
    left, _ = _rail_islands(tmp_path / "a", 0.0)
    assert left                                          # without it, the FB pin's island stays
    left, s = _rail_islands(tmp_path / "b", 20.0)
    assert not left
    sp = s.space
    for it in sp.routed:                                 # and the joins are exactly legal
        others = [x for x in sp.routed if x is not it]
        if it.kind == "track":
            l = next(iter(it.layers))
            assert not sp.track_violations(it.net, l, it.width, it.geom.coords[0], it.geom.coords[-1], ignore=others)


def test_critical_nets_join_their_nearby_pads(tmp_path):
    """A pad of a critical net next to its critical copper (a VIN pull-up beside the buck's
    input capacitor) is joined by the critical stage, not left as an island beside a fixed
    track."""
    def joined(reach, d):
        s = F.session(d, extra=[F.PULLUP], complete_mm=reach, rails="none")
        s.route()
        sp = s.space
        u1 = next(f.uuid for f in s.board.footprints if f.ref == "U1")
        vin = sp.terminal(u1, ["3"])
        r9 = sp.terminal(next(f.uuid for f in s.board.footprints if f.ref == "R9"), ["1"])
        comp = {id(x) for x in sp.component("VIN", [(vin.geom, vin.layers)])}
        return any(id(x) in comp for x in r9.items), s
    assert not joined(0.0, tmp_path / "a")[0]
    ok, s = joined(8.0, tmp_path / "b")
    assert ok and s.report()["completed"].get("VIN", 0) >= 1


def test_routes_that_wall_off_another_nets_pin_are_detected(tmp_path):
    """GridRouter.boxes_in: a route that encloses another net's unrouted pin is reported (the
    olimex converter's FB pin, walled in by a ground hop, was left unrouted by the bridge);
    one that passes at a distance is not."""
    from kae.route.critical_grid import Route
    s = F.session(tmp_path)                      # nothing routed: the XTAL2 pin is free
    sp, gr = s.space, s.router
    u2 = next(f.uuid for f in s.board.footprints if f.ref == "U2")
    pin = next(it for it in sp.pads_by_fp[u2] if it.owner[1] == "3")
    x0, y0, x1, y1 = pin.geom.bounds
    m = 0.45
    ring = [(x0 - m, y0 - m), (x1 + m, y0 - m), (x1 + m, y1 + m), (x0 - m, y1 + m), (x0 - m, y0 - m)]
    rt = Route(net="GND", width=0.2, segs=[("F.Cu", a, b) for a, b in zip(ring[:-1], ring[1:])], vias=[], length=0.0)
    assert any(it is pin for it, _ in gr.boxes_in(rt))
    far = Route(net="GND", width=0.2, segs=[("F.Cu", (x0 - 1.4, y0 - 3.0), (x0 - 1.4, y1 + 3.0))], vias=[], length=6.0)
    assert not any(it is pin for it, _ in gr.boxes_in(far))


def test_islands_of_a_critical_net_are_joined(tmp_path):
    """Two decaps of one rail are two islands of fixed copper; the bridge left such a pair
    unjoined (noisecard +1V8), so the critical stage joins islands within island_mm."""
    from kae.route.critical_rails import _islands
    s0 = F.session(tmp_path / "a", island_mm=0.0, complete_mm=0.0, rails="none")
    s0.route()
    assert len(_islands(s0.ctx, "+3V3")) >= 2
    s1 = F.session(tmp_path / "b", island_mm=20.0, complete_mm=0.0, rails="none")
    s1.route()
    assert len(_islands(s1.ctx, "+3V3")) == 1


# ----------------------------------------------------------------------------- brief fields
def _uuid_of(s, ref):
    return next(f.uuid for f in s.board.footprints if f.ref == ref)


def test_unowned_capacitors_are_not_paired(tmp_path):
    """caps_p < 0.5: the capacitor is not this IC's; the decap routes no pair to it."""
    s = F.session(tmp_path)
    d = next(x for x in s.brief["structures"] if x["kind"] == "decap" and x.get("ic") == _uuid_of(s, "U2"))
    c3 = _uuid_of(s, "C3")
    d["caps_p"] = {c3: 0.3}
    d["pin_caps"] = {}
    s.route()
    m = next(x for x in s.modules if x.id == d["id"])
    assert m.status == "skipped" and not m.copper


def test_power_path_routes_as_a_loop_sized_by_the_interval_bound(tmp_path):
    """A power_path module routes its loop like a cell, its widths from the upper bound of
    the excitation interval (capped by the terminals), and quotes it against the power-path
    budget."""
    s = F.session(tmp_path, kinds=("path",), rails="none")
    cell = next(x for x in s.brief["structures"] if x["kind"] == "commutation_cell")
    pp = dict(cell, id="path:test", kind="power_path", sw=None,
              excite={"V": 12.0, "I": 0.5, "I_belief": {"value": 0.5, "unit": "A", "interval": [0.2, 3.0]}})
    s.brief["structures"] = [pp]
    s.route()
    m = next(x for x in s.modules if x.id == "path:test")
    assert m.kind == "path" and m.status in ("routed", "partial") and m.copper
    assert m.physics.get("unit") == "nH" and m.physics.get("value", 0) > 0
    assert "load step" in m.physics.get("basis", "")
    vin = next(rt for rt in m.hops.values() if rt is not None and rt.net == "VIN")
    from kae.route.critical_physics import ipc2221_width
    assert vin.width >= min(ipc2221_width(3.0), 1.0) - 1e-6     # sized for 3 A, not the 0.5 A point value


def test_rail_group_capacitors_stub_to_their_nearest_load(tmp_path):
    s = F.session(tmp_path, kinds=("rgroup",), rails="none")
    s.brief["structures"] = [dict(id="rg:+3V3", kind="rail_group", rail="+3V3", ground="GND",
                                  loads=[_uuid_of(s, "U2")], caps=[_uuid_of(s, "C3")], pairing="nearest_load",
                                  members_ref={}, priority=48.0, confidence=0.9)]
    s.route()
    m = next(x for x in s.modules if x.id == "rg:+3V3")
    assert m.kind == "rgroup" and m.status == "routed"
    sp = s.space
    tp = sp.terminal(_uuid_of(s, "U2"), ["8"])
    tr = sp.terminal(_uuid_of(s, "C3"), ["1"])
    assert s.ctx.connected("+3V3", tr, tp)


def test_weak_ground_islands_get_stitching_vias(tmp_path):
    """A ground pour piece holding pads, cut off on its layer and tied by no via, gets vias
    into the ground fill of another layer (exactly legal); the layer's largest piece and a
    piece already tied are left alone."""
    from shapely.geometry import box
    s = F.session(tmp_path)
    s.route()
    sp = s.space
    c2 = next(f for f in s.board.footprints if f.ref == "C2")
    g = sp.terminal(c2.uuid, ["2"]).geom.buffer(1.6)                 # an F.Cu island around C2's ground pad
    fills = {"GND": {"F.Cu": [g, box(101, 125, 112, 129)], "B.Cu": [box(100.5, 100.5, 139.5, 129.5)]}}
    before = [it for it in sp.routed if it.kind == "via"]
    n = s.stitch_ground(fills)
    new = [it for it in sp.routed if it.kind == "via" and it not in before]
    assert n == len(new) >= 1 and all(g.contains(v.geom) for v in new)
    for v in new:
        assert not sp.via_violations("GND", v.geom.x, v.geom.y, ignore=[v])
    assert s.stitch_ground(fills) == 0 or len(new) < 3              # tied now: no more than `want` barrels



def test_wide_loop_hops_are_trimmed_within_the_tolerance(tmp_path):
    """Hops wider than the loop needs are narrowed to the narrowest width whose loop stays
    within trim_tol of the wide one, never below the class width or the current's floor, and
    the narrowed copper stays exactly legal."""
    wide = F.session(tmp_path / "a", trim_tol=0.0).route()
    trim = F.session(tmp_path / "b", trim_tol=0.25).route()
    v0 = {m.id: m.physics.get("value") for m in wide.modules if m.kind in ("cell", "decap")}
    w0 = {(m.id, k): r.width for m in wide.modules for k, r in m.hops.items() if r is not None}
    narrowed = 0
    sp = trim.space
    for m in trim.modules:
        if m.kind not in ("cell", "decap") or v0.get(m.id) is None:
            continue
        assert m.physics["value"] <= v0[m.id] * 1.25 + 1e-9
        for k, rt in m.hops.items():
            if rt is None or not rt.segs:
                continue
            lay = rt.segs[0][0]
            mn, opt, mx = sp.width_limits(rt.net, lay)
            assert rt.width >= min(opt, w0[(m.id, k)]) - 1e-9
            assert rt.width >= (m.spec.get("_floor") or {}).get(k, 0.0) - 1e-9 or rt.width == w0[(m.id, k)]
            narrowed += rt.width < w0[(m.id, k)] - 1e-6
            tracks = [it for it in m.copper if it.kind == "track" and it.owner == (m.id, k)]
            assert tracks and all(abs(it.width - rt.width) < 1e-9 for it in tracks)
    assert narrowed >= 1
    for it in sp.routed:
        if it.kind == "track":
            others = [x for x in sp.routed if x is not it]
            a, b = it.geom.coords[0], it.geom.coords[-1]
            assert not sp.track_violations(it.net, next(iter(it.layers)), it.width, a, b, ignore=others), it.owner


def test_rail_branches_that_fit_only_the_class_width_are_left_to_the_bridge(tmp_path):
    """A rail branch routed at the class width has no drop physics over the general router's
    track and is a locked wall (suzyqboard: a 17 mm VBUS track between the USB connectors cut
    D- and CC): it is ripped up; a wider one stays; rails="all" keeps both."""
    from kae.route.critical_modules import Module, anchor, route_hop
    from kae.route.critical_rails import _class_only
    for mode, keep_narrow in (("auto", False), ("all", True)):
        s = F.session(tmp_path / mode, rails=mode)
        ctx, sp = s.ctx, s.space
        a = sp.terminal(_uuid(s, "C3"), ["1"])
        b = sp.terminal(_uuid(s, "U2"), ["8"])
        mn, opt, mx = sp.width_limits("+3V3", "F.Cu")
        for w, kept in ((opt, keep_narrow), (1.6 * opt, True)):
            m = Module(id=f"rail:test{w}", kind="rail", spec={}, parts=[])
            rt = route_hop(ctx, m, "br:x", "+3V3", [anchor(a)], [anchor(b)], [w], ["F.Cu"])
            assert rt is not None and m.copper
            n0 = len(sp.routed)
            ripped = _class_only(ctx, m, "br:x", rt, opt)
            assert ripped == (not kept)
            assert bool(m.copper) == kept and (len(sp.routed) == n0) == kept
            sp.remove(list(m.copper))


def test_every_join_is_at_a_centre_or_a_corner(tmp_path):
    """Freerouting joins a wire to a pad or via only at its centre and to another wire only
    at a corner (lambdakb: a decap stub KiCad saw connected was an open connection for the
    bridge). A track ending on another track's body splits that body there; one ending off a
    pad's centre gets a neck to it; both exactly legal; the owners' copper lists follow."""
    s = F.session(tmp_path, corner_joins=False).route()
    sp = s.space
    body = max((it for it in sp.routed if it.kind == "track" and it.net != "GND"), key=lambda it: it.geom.length)
    layer = next(iter(body.layers))
    mid = body.geom.interpolate(0.5, normalized=True)
    t1 = sp.add_track(body.net, layer, body.width, (mid.x, mid.y), (mid.x, mid.y), owner=body.owner)
    pad = next(p for p in sp.pads if p.net == body.net and layer in p.layers and p.pos is not None)
    x0, y0, x1, y1 = pad.geom.bounds
    off = (pad.pos[0] + 0.25 * (x1 - x0) * 0.5, pad.pos[1])
    t2 = sp.add_track(body.net, layer, 0.1, off, off, owner=body.owner)
    m = next(x for x in s.modules + list(getattr(s.ctx, "rail_modules", [])) if x.id == body.owner[0])
    m.copper += [t1, t2]
    rep = s.join_at_corners()
    assert rep["splits"] >= 1 and rep["necks"] >= 1 and rep["left"] == 0
    assert body not in sp.routed and body not in m.copper
    corners = {tuple(round(c, 6) for c in pt) for it in sp.routed if it.kind == "track" and it.net == body.net
               for pt in (it.geom.coords[0], it.geom.coords[-1])}
    assert (round(mid.x, 6), round(mid.y, 6)) in corners
    assert tuple(round(c, 6) for c in pad.pos) in corners
    for it in m.copper:
        assert it in sp.routed
    for it in sp.routed:
        if it.kind == "track" and it not in (t1, t2):
            others = [x for x in sp.routed if x is not it]
            a, b = it.geom.coords[0], it.geom.coords[-1]
            assert not sp.track_violations(it.net, next(iter(it.layers)), it.width, a, b, ignore=others), it.owner


def test_a_light_branch_never_inherits_the_trunk_current(tmp_path, monkeypatch):
    """When the trunk (to the farthest load) is left to the router, the other branches carry
    their own loads' current, not the rail's design current (suzyqboard: a 0 A pull-up got a
    10 mm, 3 A-wide track after the VBUS trunk was ripped)."""
    from kae.route import critical_rails as CR
    calls = []
    real = CR._class_only

    def first_ripped(ctx, m, tag, rt, opt):
        calls.append(tag)
        if len(calls) == 1:
            return real(ctx, m, tag, rt, rt.width * 2.0)      # as if only the class width fitted
        return real(ctx, m, tag, rt, opt)
    monkeypatch.setattr(CR, "_class_only", first_ripped)
    s = F.session(tmp_path, rails="auto", extra=[F.PULLUP]).route()       # VIN: the buck and a pull-up
    checked = 0
    for r in s.rails:
        if not r.get("branches") or "design_A" not in r:
            continue
        loads = r["loads"]
        checked += len(r["branches"]) - 1
        for k, b in enumerate(r["branches"]):
            if k == 0 or "current_A" not in b:
                continue
            assert b["current_A"] <= max(loads[b["load"]], 0.05) + 1e-9, (r["net"], b)
    assert calls and checked >= 1


# ----------------------------------------------------------------------------- one objective with the placer
def test_modules_are_priced_against_the_place_terms(routed):
    """Every quoted module carries the allocation of the place terms' structure of its id
    (calibrated decap budgets, careful-layout clamps), so the module stage, the recheck and
    the placer optimize one objective."""
    by_id = {st.id: st for st in routed.terms.structs}
    n = 0
    for m in routed.modules:
        if m.physics.get("alloc") is None:
            continue
        sts = [st for i, st in by_id.items() if i == m.id or i.startswith(m.id + "#")]
        assert sts, m.id
        assert any(abs(m.physics["alloc"] - round(st.alloc.value, 4)) < 1e-6 for st in sts), m.id
        n += 1
    assert n >= 4


def test_decap_fallback_budget_is_per_pin_not_divided_again(tmp_path):
    """Without place terms, a decap's allocation is priors.decap_budget per power pin as the
    place terms read it; it was divided by the pin count a second time (canhw: u 13.9)."""
    from kae.physics import priors as PR
    from kae.route.critical_modules import allocation
    s = F.session(tmp_path, place_allocs=False)
    assert s.terms is None
    from kae.route.critical_modules import modules_from_brief
    m = next(x for x in modules_from_brief(s.brief) if x.kind == "decap")
    m.spec = dict(m.spec, power_pins=["1", "2", "3", "4"])
    a = allocation(s.ctx, m)
    b = PR.decap_budget(s.ctx.volts(m.spec.get("rail")) or 3.3, s.ctx.npins(m.spec.get("ic")), 4,
                        function=m.spec.get("function"))
    assert abs(a.value - b.value) < 1e-9


def test_decap_spend_prices_pin_clusters_and_nearest_pin_caps():
    """decap_spend: a pin cluster's capacitors in parallel (each at its mean loop to the
    cluster's pins), a nearest_pin structure its capacitor's best loop; the worst u wins."""
    from types import SimpleNamespace as NS
    from kae.physics import priors as PR
    from kae.route.critical_modules import decap_spend
    B = lambda v: PR.Belief(v, "nH", "t")                                   # noqa: E731
    pairs = [("1", "a", 2.0), ("2", "a", 4.0), ("1", "b", 6.0), ("5", "c", 3.0)]
    ref = {"a": "C1", "b": "C2", "c": "C3"}.get
    cl = NS(id="d#0", alloc=B(2.0), info=dict(pins=["1", "2"]), labels=["C1", "C2"])
    npin = NS(id="d#C3", alloc=B(6.0), info=dict(pairing="nearest_pin", pins=["5"]), labels=["C3"])
    v, a, ex = decap_spend(pairs, [cl, npin], ref, B(1.0))
    assert abs(v - 1.0 / (1 / 3.0 + 1 / 6.0)) < 1e-3 and a.value == 2.0        # cluster: (2+4)/2 || 6
    assert {c["id"] for c in ex["clusters"]} == {"d#0", "d#C3"}
    v2, a2, _ = decap_spend(pairs, [], ref, B(1.0))
    assert v2 == 4.0 and a2.value == 1.0                                        # worst pin: 2 || 6 = 1.5 vs 4 vs 3


def test_cell_loops_through_every_owned_input_cap_in_parallel(tmp_path):
    """The hot loop through a second owned input capacitor counts in parallel, as in the
    place terms (kae.physics.build._commutation); an unlikely capacitor does not."""
    from kae.route.critical_modules import _cell_value, cell_variants
    s = F.session(tmp_path).route()
    m = next(x for x in s.modules if x.kind == "cell")
    v1, _ = _cell_value(s.ctx, m)
    T = m.spec["_T"]
    other = next(f.uuid for f in s.board.footprints if f.ref == "C3")            # a stand-in second input cap

    def term_of(c, net):                                                         # at the first cap's pads
        return T[0] if net == T[0].net else T[-1]
    spec = dict(m.spec, caps=[T[0].fp, other], caps_p={T[0].fp: 0.9, other: 0.9})
    assert len(cell_variants(spec, T, term_of)) == 2
    assert len(cell_variants(dict(spec, caps_p={T[0].fp: 0.95, other: 0.01}), T, term_of)) == 1
    m.spec = dict(m.spec, caps=[T[0].fp, other], caps_p={T[0].fp: 0.9, other: 0.9})
    v2, ex = _cell_value(s.ctx, m)
    assert ex["variants"] >= 1 and v2 <= v1 + 1e-9


def test_crystal_pulling_is_a_quarter_of_the_trace_capacitance(routed):
    """Each crystal net's trace capacitance adds to one load capacitor; C_L moves by C / 4."""
    from kae.physics import priors as PR
    m = next(x for x in routed.modules if x.kind == "crystal")
    _, S = PR.crystal_budget(m.spec.get("f_Hz"))
    assert abs(m.physics["value"] - S * m.physics["c_trace_pf"] / 4.0) < 1e-3


def test_surge_via_runs_to_the_plane_under_the_protector(routed, tmp_path, monkeypatch):
    """The recheck's protector via is as long as the height of the plane under the protector
    (place terms' EsdComp), the board thickness only without a plane."""
    from kae.route import critical_recheck as R
    from kae.route.critical_modules import modules_from_brief
    dst = tmp_path / "b.kicad_pcb"
    routed.write(dst)
    from kae.board.kicad_file import load
    rb = R.RoutedBoard(load(dst), fills=None, brief=routed.brief)
    spec = next(x for x in modules_from_brief(routed.brief) if x.kind == "chain").spec
    monkeypatch.setattr(rb, "h_at", lambda *a, **k: 0.2)
    v_thin, _ = R.chain_value(rb, spec)
    monkeypatch.setattr(rb, "h_at", lambda *a, **k: R.INF)
    v_none, _ = R.chain_value(rb, spec)
    assert v_thin < v_none


def test_joint_and_recheck_are_window_scoped(tmp_path):
    """optimize_modules(window=...) works only on the modules with a member part in the
    window and moves only parts inside it (no rails); board_physics / recheck with a window
    report only those modules (the kae.joint loop re-places and re-routes locally)."""
    from shapely.geometry import box
    from kae.board.kicad_file import load
    from kae.route import critical_recheck as R
    from kae.route.critical import Session
    from kae.route.critical_joint import optimize_modules
    p = F.write_board(tmp_path)
    b = load(p)
    s = Session(p, info=F.synth_info(b), board=b, log=lambda *a: None)
    y1 = next(f for f in b.footprints if f.ref == "Y1")
    win = box(y1.x - 4, y1.y - 4, y1.x + 4, y1.y + 4)
    poses, copper, rep = optimize_modules(b, s.brief, locked=set(), session=s, time_s=60, window=win)
    ids = {m["id"] for m in rep["modules"]}
    assert ids and all(any(win.intersects(__import__("shapely").Point(f.x, f.y)) for f in b.footprints
                           if f.uuid in next(x for x in s.modules if x.id == i).parts) for i in ids)
    assert "cell:buck:U1" not in ids and "rails" not in rep
    for u in poses:
        f = next(f for f in b.footprints if f.uuid == u)
        assert win.intersects(__import__("shapely").Point(f.x, f.y))
    dst = tmp_path / "w.kicad_pcb"
    s.write(dst)
    ph = R.board_physics(dst, brief=s.brief, fills=None, window=win.bounds, rails=False)
    assert set(ph) <= ids | {"_rails"} and "_rails" not in ph


def test_decap_over_its_rail_plane_goes_into_the_plane(tmp_path, monkeypatch):
    """A decap whose rail is a plane under both the capacitor and the IC pin, more than
    decap_plane_mm away, gets a via into that plane instead of a surface track around the
    IC (canhw: 30+ locked stubs around an LQFP-100 took its signal escapes)."""
    from shapely.geometry import box
    from kae.route import critical_modules as CM
    s = F.session(tmp_path)
    sp = s.space
    sp.zones.append(("+3V3", "B.Cu", box(100.5, 100.5, 139.5, 129.5), 0))
    monkeypatch.setattr(CM, "_rail_plane", lambda ctx, rail, a, b: "B.Cu" if rail == "+3V3" else None)
    s.route()
    m = next(x for x in s.modules if x.id == "decap:U2:+3V3")
    assert any("into the B.Cu +3V3 plane" in n for n in m.notes)
    assert not any(k.startswith("rail:") and v is not None for k, v in m.hops.items())
    vias = [it for it in m.copper if it.kind == "via" and it.net == "+3V3"]
    c3 = sp.terminal(_uuid(s, "C3"), ["1"])
    assert vias and min(v.geom.distance(c3.geom) for v in vias) < 1.5
    for v in vias:
        assert not sp.via_violations("+3V3", v.geom.x, v.geom.y, ignore=[v])


def test_pad_requirement_reads_net_conditions_against_another_net(tmp_path):
    """A pad's clearance from a routing class is read against a track of another net of the
    class: with the class representative on the pad's own net, a custom rule "A.Net != B.Net"
    never matched and the pad got the net class clearance (oasis: C2's +18V pad 0.15 instead
    of 0.2 mm, Freerouting routed 30 um inside it)."""
    from kae.board.kicad_file import load
    from kae.route import constraints as CN
    p = F.write_board(tmp_path)
    p.with_suffix(".kicad_dru").write_text(
        '(version 1)\n(rule "track to pad"\n  (condition "A.Type == \'pad\' && B.Type == \'track\' && A.Net != B.Net")\n'
        '  (constraint clearance (min 0.33mm))\n)\n')
    b = load(p)
    info = F.synth_info(b)
    plan = CN.plan(info, p, {})
    rc = next(rc for rc in plan.classes.values() if rc.rep)
    pad = next(pd for pd in info["pads"] if pd["net"] == rc.rep and "F.Cu" in pd["layers"])
    cls = plan.pin_class[(pad["comp"], pad["pin"])]
    tw, vw = plan.obstacle_classes[cls].values[(rc.name, "F.Cu")]
    assert tw >= 0.33 - 1e-9


def test_dense_ic_signal_pins_keep_escape_corridors(tmp_path):
    """escape_mm builds, for each signal pad of a dense IC, the strip from its outer end
    outward along its long axis; critical vias of other nets stay out of them and critical
    tracks pay to enter them (canhw: crit 18-21 unconnected -> 15 with 1.5 mm corridors)."""
    import math as _m
    s = F.session(tmp_path, escape_mm=1.5, escape_pins=8)
    esc = s.router.escapes
    u2 = next(f for f in s.board.footprints if f.ref == "U2")
    nets = {n for _, _, n in esc}
    assert "Net-(U2-XTAL1)" in nets and "Net-(U2-XTAL2)" in nets
    assert not nets & {"GND", "+3V3"}                                      # ground and rails are not escapes
    for g, l, n in esc:
        pad = next(it for it in s.space.pads_by_fp[u2.uuid] if it.net == n)
        c = g.centroid
        assert _m.dist((c.x, c.y), (u2.x, u2.y)) > _m.dist(pad.pos, (u2.x, u2.y))   # outward
        assert not g.intersects(pad.geom.buffer(-1e-3))                    # beyond the pad
    s.route()
    for it in s.space.routed:
        if it.kind == "via":
            assert not s.router.escape_hit(it.net, it.geom, it.r), it.owner


def test_pads_the_placement_starves_get_their_spokes_first(tmp_path, monkeypatch):
    """KiCad's DRC on the bare board names a starved thermal (paw3395: C11's GND pad):
    Session.thermal_spokes lays the missing spoke as a legal track of the pad's net from
    inside the pad into the zone's fill, before any module, so module copper keeps clear."""
    from shapely.geometry import box
    from kae.board import pcbnew_io
    from kae.route import drc
    s = F.session(tmp_path)
    pad = next(p for p in s.info["pads"] if p["ref"] == "J1" and p["number"] == "2")      # GND, through hole
    zone_uuid = next(z.uuid for z in s.board.zones if z.net == "GND")
    monkeypatch.setattr(drc, "run", lambda *a, **k: {"violations": [dict(
        type="starved_thermal", severity="error",
        description="Thermal relief connection to zone incomplete (layer B.Cu; zone min spoke count 2; actual 1)",
        items=[dict(uuid=zone_uuid), dict(uuid=pad["uuid"])])], "unconnected_items": []})
    monkeypatch.setattr(pcbnew_io, "zone_fills", lambda *a, **k: {"zones": [dict(
        uuid=zone_uuid, net="GND", layers={"B.Cu": [[list(box(100.5, 100.5, 139.5, 129.5).exterior.coords)]]})]})
    mods = s.thermal_spokes()
    assert len(mods) == 1 and mods[0].copper
    for it in mods[0].copper:
        assert it.net == "GND" and set(it.layers) == {"B.Cu"}
        a, b = it.geom.coords[0], it.geom.coords[-1]
        assert not s.space.track_violations("GND", "B.Cu", it.width, a, b, ignore=[it])
    s.pre_modules = mods
    s.route()
    assert s.modules[0].id == "spokes"


def test_writer_edits_kicad6_files_with_spaces_and_tstamps(tmp_path):
    """KiCad 6/7 files indent by two spaces and id items by (tstamp ...): rip-up and lock must see them."""
    src = tmp_path / "k6.kicad_pcb"
    src.write_text('(kicad_pcb (version 20211014) (generator pcbnew)\n'
                   '  (net 0 "")\n  (net 1 "A")\n'
                   '  (gr_poly (pts (xy 0 0) (arc (start 1 1) (mid 2 2) (end 3 3))) (layer "Edge.Cuts") (width 0.1) (tstamp 00000000-0000-0000-0000-00000000000e))\n'
                   '  (segment (start 0 0) (end 1 0) (width 0.2) (layer "F.Cu") (net 1) (tstamp 11111111-1111-1111-1111-111111111111))\n'
                   '  (segment (start 1 0) (end 2 0) (width 0.2) (layer "F.Cu") (net 1) (tstamp 22222222-2222-2222-2222-222222222222))\n'
                   '  (via (at 2 0) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1) (tstamp 33333333-3333-3333-3333-333333333333))\n'
                   ')\n')
    items = W.routing(src)
    assert [(i["kind"], i["uuid"][:2]) for i in items] == [("segment", "11"), ("segment", "22"), ("via", "33")]
    dst = tmp_path / "out.kicad_pcb"
    W.edit(src, dst, remove=["11111111-1111-1111-1111-111111111111", "33333333-3333-3333-3333-333333333333"])
    text = dst.read_text()
    assert "1111" not in text and "3333" not in text and "2222" in text and "(arc (start 1 1)" in text
