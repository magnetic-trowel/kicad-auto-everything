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
    assert w == pytest.approx(0.5 * L * 1e-9 * I * I * f + I * I * D * (1 - D) * R, rel=1e-3)
    assert 0 < D < 1 and basis


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
    for ref in ("C1", "U1"):            # the hot loop's input cap and IC sit over it
        fp = next(f for f in b.footprints if f.ref == ref)
        assert poly.contains(Point(fp.x, fp.y))
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
