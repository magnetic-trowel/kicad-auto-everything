# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route against live KiCad (and Freerouting for the end-to-end test); skipped when
they are missing."""
import json
import shutil
from pathlib import Path

import pytest

from kae.board import pcbnew_io, sexpr
from kae.route import bridge, constraints, drc, effective, freerouting, specctra, translate

DATA = Path(__file__).parent / "data" / "board"
FIXTURE = DATA / "fixture.kicad_pcb"

pytestmark = [pytest.mark.kicad,
              pytest.mark.skipif(not pcbnew_io.available(), reason="no Python with pcbnew")]

# error types a translation loss produces (as opposed to routing failures)
TRANSLATION = ("track_width", "clearance", "copper_edge_clearance", "hole_clearance", "hole_to_hole",
               "shorting_items", "via_diameter", "annular_width", "solder_mask_bridge", "items_not_allowed")


def _unrouted_copy(tmp_path):
    """The fixture with its tracks, arcs and vias removed, project files beside it."""
    text = FIXTURE.read_text()
    out, pos = [], 0
    i = 0
    while True:
        cands = [text.find(h, i) for h in ("\n\t(segment", "\n\t(via", "\n\t(arc")]
        cands = [c for c in cands if c >= 0]
        if not cands:
            break
        a = min(cands) + 1
        b = sexpr.block_end(text, a)
        out.append(text[pos:a])
        pos = b
        i = b
    out.append(text[pos:])
    p = tmp_path / "board.kicad_pcb"
    p.write_text("".join(out))
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(FIXTURE.with_suffix(ext), p.with_suffix(ext))
    return p


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    d = tmp_path_factory.mktemp("export")
    board = _unrouted_copy(d)
    info = pcbnew_io.export_dsn(board, d / "kicad.dsn")
    return board, info, d / "kicad.dsn"


def test_rule_port_agrees_with_kicads_engine(exported):
    board, info, _ = exported
    v = constraints.validate(info, board)
    assert v["checked"] > 100
    assert v["mismatched"] == 0, v["examples"]
    assert not v["unsupported"] and not v["rule_errors"]


def test_export_carries_what_the_dsn_leaves_out(exported):
    board, info, dsn = exported
    assert info["tracks"] == 0
    assert {n["netclass"] for n in info["nets"].values()} <= set(info["netclasses"])
    assert any("Power" in nc.split(",") for nc in info["netclasses"])
    # every component the DSN places is known to the export, with KiCad's component ids
    comps = {p["comp"] for p in info["pads"]}
    tree = specctra.read(dsn)
    placed = {str(pl[1]) for comp in specctra.findall(specctra.find(tree, "placement"), "component")
              for pl in specctra.findall(comp, "place")}
    assert comps <= placed
    probe = next(iter(info["probes"].values()))
    assert set(probe["track"]) == set(info["copper"]) and probe["via"]["diameter"][0] is not None


def test_plan_and_translation(exported, tmp_path):
    board, info, dsn = exported
    p = constraints.plan(info, board)
    # every net is in a routing class; every pin with copper has a clearance class
    assert set(p.net_class) == set(info["nets"])
    assert all((pd["comp"], pd["pin"]) in p.pin_class for pd in info["pads"] if pd["pin"] and pd["layers"])
    # widths: never below the KiCad minimum on any layer, never above a rule's maximum
    for rc in p.classes.values():
        for l, w in rc.widths.items():
            lim = info["probes"][rc.rep]["track"][l]["width"]
            assert w >= lim[0] - 1e-9 and (lim[2] is None or w <= lim[2] + 1e-9)
        D, d = rc.via
        assert D >= max(info["settings"]["min_via"], d + 2 * info["settings"]["min_annular"]) - 1e-9
    # the Power class keeps its 0.3 mm custom clearance against everything
    pw = p.net_class.get("VCC")
    if pw:
        for (a, b, l), v in p.matrix.items():
            if pw in (a, b):
                assert min(v) >= 0.3 - 1e-9
    tree = specctra.read(dsn)
    summary = translate.apply(tree, p, info)
    out = tmp_path / "board.dsn"
    specctra.write(tree, out)
    text = out.read_text()
    assert "class_class" in text and "kae_obstacles" in text and "(clearance_class kae_pin" in text
    assert summary["pins_classed"] == len(p.pin_class)



def test_pin_shapes_outside_contain_kicads_pad_copper(exported, tmp_path):
    """With pad_shapes "outside", every polygon pin of KiCad's DSN contains its pad's copper
    on its layer (KiCad's own roundrect chords lie inside it), at most max_error + 1 um
    beyond it; with the default, the DSN keeps KiCad's shapes."""
    from shapely.geometry import Polygon
    board, info, dsn = exported
    p = constraints.plan(info, board)
    tree = specctra.read(dsn)
    assert "pin_shapes" not in translate.apply(tree, p, info)
    p.pad_shapes = "outside"
    tree = specctra.read(dsn)
    summary = translate.apply(tree, p, info)["pin_shapes"]
    assert summary["pin_shapes_circumscribed"] >= 1 and summary["pin_shapes_kept"] == 0
    lib = specctra.find(tree, "library")
    stacks = {str(ps[1]): ps for ps in specctra.findall(lib, "padstack")}
    dsn_l = [str(l[1]) for l in specctra.findall(specctra.find(tree, "structure"), "layer")]
    pads = {(pd["comp"], pd["pin"]): pd for pd in info["pads"]}
    checked = 0
    for ref, num, psn, side, m in translate.dsn_pins(tree):
        if (ref, num) not in pads or psn not in stacks:
            continue
        for sh in specctra.findall(stacks[psn], "shape"):
            node = sh[1]
            if node[0] != "polygon":
                continue
            v = [float(x) for x in node[3:]]
            g = translate._apply_affine(Polygon(list(zip(v[0::2], v[1::2]))), m)
            i = dsn_l.index(str(node[1]))
            layer = info["copper"][len(dsn_l) - 1 - i if side == "back" else i]
            real = translate._pad_copper(pads[(ref, num)], layer)
            assert g.buffer(1e-6).contains(real), (ref, num, psn)
            assert g.hausdorff_distance(real) <= info["settings"]["max_error"] + 0.001
            checked += 1
    assert checked >= 9

def test_mask_openings_keep_other_copper_out(exported):
    """A solder-mask opening drawn as a graphic exposes the copper under it: unless it covers
    a pad, it is a keepout on its outer copper layer (another net there would bridge)."""
    import copy
    from shapely.geometry import box
    board, info, _ = exported
    info = copy.deepcopy(info)
    pad = next(pd for pd in info["pads"] if "F.Cu" in pd["layers"])
    x, y = pad["pos"]
    free = next(b for b in (box(x + dx, y + dy, x + dx + 1, y + dy + 1) for dx in range(-30, 31, 3)
                            for dy in range(-30, 31, 3))
                if all(g.distance(b) > 0.5 for pd in info["pads"]
                       for g in constraints._pad_shapes(pd)[1].values() if g is not None))
    ring = lambda g: [[list(c) for c in g.exterior.coords]]
    info["mask_openings"] = [dict(layer="B.Mask", owner="", cls="PCB_SHAPE", polys=[ring(free)]),
                             dict(layer="F.Mask", owner="", cls="PCB_SHAPE", polys=[ring(box(x - .1, y - .1, x + .1, y + .1))])]
    p = constraints.plan(info, board)
    ko = [o for o in p.obstacles if o.why.startswith("mask opening")]
    assert len(ko) == 1 and ko[0].kind == "keepout" and ko[0].layer == info["copper"][-1]
    assert ko[0].geom.equals(free)
    p2 = constraints.plan(info, board, dict(severities={"solder_mask_bridge": "ignore"}))
    assert not [o for o in p2.obstacles if o.why.startswith("mask opening")]


def test_mask_openings_over_pads(exported):
    """An opening that exposes a netted pad stays a keepout beyond the room the pad's net needs
    (a hole as large as the pad's clearance); one that shuts the pad in raises the pad's
    clearance over its share of the opening instead; no-net copper does not count."""
    import copy
    from shapely.geometry import box
    board, info, _ = exported
    info = copy.deepcopy(info)
    pads = [pd for pd in info["pads"] if "F.Cu" in pd["layers"] and pd.get("net") and pd.get("pin")]
    pad = pads[0]
    g = constraints._pad_shapes(pad)[1]["F.Cu"]
    x0, y0, x1, y1 = g.bounds
    ring = lambda b: [[list(c) for c in b.exterior.coords]]
    # a strip from the pad's left edge 3 mm out: a keepout minus the hole round the pad
    strip = box(x0 - 3, (y0 + y1) / 2 - 0.1, (x0 + x1) / 2, (y0 + y1) / 2 + 0.1)
    info["mask_openings"] = [dict(layer="F.Mask", owner="", cls="PCB_SHAPE", polys=[ring(strip)])]
    p0 = constraints.plan(info, board)
    base_cls = p0.pin_class[(pad["comp"], pad["pin"])]
    ko = [o for o in p0.obstacles if o.why.startswith("mask opening")]
    assert len(ko) == 1 and ko[0].layer == "F.Cu" and not ko[0].geom.intersects(g)
    assert ko[0].geom.area < strip.area and ko[0].geom.bounds[0] == pytest.approx(x0 - 3)
    # a box 1 mm round the pad on every side: shut in, so no keepout near it, a wider clearance
    big = g.buffer(1.0).envelope
    others = [pd for pd in info["pads"] if pd is not pad
              and any(h is not None and h.intersects(big.buffer(0.5)) for h in constraints._pad_shapes(pd)[1].values())]
    if not others:
        info["mask_openings"] = [dict(layer="F.Mask", owner="", cls="PCB_SHAPE", polys=[ring(big)])]
        p1 = constraints.plan(info, board)
        assert not [o for o in p1.obstacles if o.why.startswith("mask opening")]
        c0 = p0.obstacle_classes[base_cls].values
        c1 = p1.obstacle_classes[p1.pin_class[(pad["comp"], pad["pin"])]].values
        assert all(c1[k][0] >= 1.0 > c0[k][0] for k in c1 if k[1] == "F.Cu")
    # the same strip over a pad with no net: a keepout of the whole strip
    info["pads"] = [dict(pd, net="") if pd is pad else pd for pd in info["pads"]]
    info["mask_openings"] = [dict(layer="F.Mask", owner="", cls="PCB_SHAPE", polys=[ring(strip)])]
    p2 = constraints.plan(info, board)
    ko = [o for o in p2.obstacles if o.why.startswith("mask opening")]
    assert len(ko) == 1 and ko[0].geom.equals(strip)


def test_effective_rules_are_the_plans(exported):
    board, info, _ = exported
    p = constraints.plan(info, board)
    r = effective.Rules(info, board, plan=p)
    assert r.layers == info["copper"] and set(r.nets) == {n for n in info["nets"] if n}
    for net in r.nets:
        rc = p.classes[p.net_class[net]]
        assert r.via(net) == effective.Via(*rc.via)
        for l in r.layers:
            w = r.track_width(net, l)
            lim = info["probes"][net]["track"][l]["width"]
            assert w.min >= (lim[0] or 0.0) - 1e-9
            assert w.opt == rc.widths[l] and w.min <= w.opt and (w.max is None or w.opt <= w.max)
            e = r.edge_clearance(net, l)
            assert (e.track, e.via) == p.obstacle_classes["kae_edge"].values[(rc.name, l)]
    vcc = "VCC" if "VCC" in r.nets else None
    if vcc:  # the fixture's Power class keeps its 0.3 mm custom clearance against everything
        c = r.clearance(vcc, None, "F.Cu")
        assert min(c.track_track, c.track_via, c.via_track, c.via_via) >= 0.3 - 1e-9
    a, b = r.nets[0], r.nets[1]
    ab, ba = r.clearance(a, b, "F.Cu"), r.clearance(b, a, "F.Cu")
    assert (ab.track_track, ab.track_via, ab.via_track, ab.via_via) == \
        (ba.track_track, ba.via_track, ba.track_via, ba.via_via)
    pad = next(pd for pd in info["pads"] if pd.get("net") and pd["net"] != a and "F.Cu" in pd["layers"])
    pc = r.pad_clearance(a, "F.Cu", pad["ref"], pad["number"])
    assert pc.track > 0 and pc.via > 0
    with pytest.raises(KeyError):
        r.track_width("no such net", "F.Cu")


def _have_freerouting():
    try:
        freerouting.command()
        drc.kicad_cli()
        return True
    except Exception:
        return False


needs_router = pytest.mark.skipif(not _have_freerouting(), reason="no Freerouting or kicad-cli")


@pytest.fixture(scope="module")
def routed(tmp_path_factory):
    d = tmp_path_factory.mktemp("routed")
    board = _unrouted_copy(d)
    out = d / "out" / "board.kicad_pcb"
    rep = bridge.route(board, out, time_s=150, workdir=d / "wd", opts=dict(rounds=1))
    return board, out, rep, d


def _blocks(text):
    """{uuid: s-expression text} of every track, arc and via of a .kicad_pcb."""
    out, i = {}, 0
    while True:
        cands = [c for c in (text.find(h, i) for h in ("\n\t(segment", "\n\t(via", "\n\t(arc")) if c >= 0]
        if not cands:
            return out
        a = min(cands) + 1
        b = sexpr.block_end(text, a)
        block = text[a:b]
        u = block.split('(uuid "', 1)[1].split('"', 1)[0]
        out[u] = block
        i = b


@needs_router
def test_route_end_to_end_has_no_translation_errors(routed, tmp_path):
    board, out, rep, _ = routed
    assert rep["status"] == "routed" and out.exists()
    staged = drc.stage_board(out, board, tmp_path / "drc")
    report = drc.run(staged, tmp_path / "drc" / "drc.json")
    # the fixture places U7 outside the board: copper reaching it must cross the edge
    from kae.board import kicad_file
    b = kicad_file.load(board)
    off = {p.net for fp in b.footprints if not fp.on_board for p in fp.pads if p.net}
    bad = [v for v in drc.errors(report) if v["type"] in TRANSLATION and
           not any(f"[{n}]" in it.get("description", "") for n in off for it in v.get("items", []))]
    assert not bad, json.dumps(bad[:5], indent=1)


@needs_router
def test_locked_preroutes_come_back_unchanged(routed, tmp_path):
    """Locked tracks and vias in the input (what kae.route.critical emits) are fixed wiring:
    byte-identical in the output, with the rest of the board routed around them."""
    board, out, _, _ = routed
    routing = pcbnew_io.edit_routing(out, tmp_path / "listing.kicad_pcb")["routing"]
    # lock a net whose first routing is clean (the fixture's U7 sits off the board)
    report = drc.run(drc.stage_board(out, board, tmp_path / "drc1"), tmp_path / "drc1" / "drc.json")
    dirty = {n for v in drc.errors(report) for it in v.get("items", [])
             for n in [it.get("description", "").partition("[")[2].partition("]")[0]] if n}
    by_net = {}
    for r in routing:
        if r["net"] not in dirty:
            by_net.setdefault(r["net"], []).append(r)
    assert by_net, "no net routed cleanly to lock"
    net = max(by_net, key=lambda n: (any(r["kind"] == "via" for r in by_net[n]), len(by_net[n])))
    keep = {r["uuid"] for r in by_net[net]}
    pre = tmp_path / "pre" / "board.kicad_pcb"
    pre.parent.mkdir()
    pcbnew_io.edit_routing(out, pre, delete=[r["uuid"] for r in routing if r["uuid"] not in keep], lock_all=True)
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(board.with_suffix(ext), pre.with_suffix(ext))
    before = {u: b for u, b in _blocks(pre.read_text()).items()}
    assert set(before) == keep and all("(locked yes)" in b for b in before.values())

    out2 = tmp_path / "out2" / "board.kicad_pcb"
    rep = bridge.route(pre, out2, time_s=120, workdir=tmp_path / "wd2", opts=dict(rounds=1, plane_escapes=False))
    assert rep["status"] == "routed" and rep["fixed_items"] == len(keep)
    after = _blocks(out2.read_text())
    for u, b in before.items():
        assert after.get(u) == b, f"pre-route {u} changed"
    assert len(after) > len(before)                       # the rest was routed
    others = [b for u, b in after.items() if u not in before]
    assert all("(locked yes)" not in b for b in others)
    staged = drc.stage_board(out2, pre, tmp_path / "drc2")
    report = drc.run(staged, tmp_path / "drc2" / "drc.json")
    touching = [v for v in drc.errors(report)
                if any(it.get("uuid") in keep for it in v.get("items", [])) and v["type"] in TRANSLATION]
    assert not touching, json.dumps(touching[:3], indent=1)


CRIT_ZONE = """	(zone
		(net "{net}")
		(layer "{layer}")
		(uuid "00000000-0000-4000-8000-00000000c417")
		(name "kae-crit:test")
		(hatch edge 0.5)
		(connect_pads
			(clearance 0.2)
		)
		(min_thickness 0.2)
		(fill
			(thermal_gap 0.5)
			(thermal_bridge_width 0.5)
			(island_removal_mode 1)
		)
		(polygon
			(pts
				(xy {x0} {y0}) (xy {x1} {y0}) (xy {x1} {y1}) (xy {x0} {y1})
			)
		)
	)
"""


@needs_router
def test_critical_zones_are_obstacles_for_other_nets(routed, exported, tmp_path):
    """A zone named "kae-crit:..." (a pour kae.route.critical emitted) keeps every other net
    out: routed again, its refilled copper is intact and no other net comes within the
    zone's clearance of it."""
    from shapely.geometry import LineString, Point, box
    from shapely.ops import unary_union
    board, out, _, _ = routed
    _, info, _ = exported
    pads = unary_union([g for pd in info["pads"] for g in constraints._pad_shapes(pd)[1].values() if g is not None])
    routing = pcbnew_io.edit_routing(out, tmp_path / "listing.kicad_pcb")["routing"]
    tracks = sorted((r for r in routing if r["kind"] == "track"),
                    key=lambda r: -LineString([r["a"], r["b"]]).length)
    pick = None
    for r in tracks:   # a square on a stretch the first routing used, clear of every pad
        m = LineString([r["a"], r["b"]]).interpolate(0.5, normalized=True)
        sq = box(m.x - 0.8, m.y - 0.8, m.x + 0.8, m.y + 0.8)
        if sq.distance(pads) > 0.5:
            pick = (r, sq)
            break
    assert pick, "no stretch of routing clear of pads"
    r, sq = pick
    net = next(n for n in sorted(info["nets"]) if n and n != r["net"])
    x0, y0, x1, y1 = sq.bounds
    text = board.read_text()
    end = text.rstrip().rfind(")")
    crit = tmp_path / "crit" / "board.kicad_pcb"
    crit.parent.mkdir()
    crit.write_text(text[:end] + CRIT_ZONE.format(net=net, layer=r["layer"], x0=x0, y0=y0, x1=x1, y1=y1)
                    + text[end:])
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(board.with_suffix(ext), crit.with_suffix(ext))

    def fill(path):
        z = next(z for z in pcbnew_io.zone_fills(path)["zones"] if z["name"] == "kae-crit:test")
        return unary_union([constraints._poly(rings) for rings in z["layers"].get(r["layer"], [])])

    before = fill(crit)
    assert before.area > 1.0
    out3 = tmp_path / "out3" / "board.kicad_pcb"
    rep = bridge.route(crit, out3, time_s=120, workdir=tmp_path / "wd3", opts=dict(rounds=1))
    assert rep["status"] == "routed" and rep["plan"]["net_graphics"] >= 1
    assert fill(drc.stage_board(out3, crit, tmp_path / "staged3")).area >= before.area - 1e-3
    for x in pcbnew_io.edit_routing(out3, tmp_path / "listing3.kicad_pcb")["routing"]:
        if x["net"] == net or (x["kind"] != "via" and x["layer"] != r["layer"]):
            continue
        g = Point(x["pos"]).buffer(x["size"] / 2) if x["kind"] == "via" else \
            LineString([x["a"], x["b"]]).buffer(x["width"] / 2)
        assert g.distance(before) >= 0.2 - 1e-3, x


FAKE_ROUTER = """#!/usr/bin/env python3
# A Freerouting that ignores its job timeout (the caller must kill it), except that a
# one-pass run (-mp 1) writes the canned session CANNED, if it exists.
import os, shutil, sys, time
a = sys.argv[1:]
if "-mp" in a and os.path.exists({canned!r}):
    shutil.copy({canned!r}, a[a.index("-do") + 1])
    sys.exit(0)
time.sleep(3600)
"""


@needs_router
def test_router_killed_at_its_deadline_still_yields_a_board(exported, tmp_path, monkeypatch):
    """Freerouting killed before writing a session: one quick pass gives a partial board; if
    that writes nothing either, the output is the unrouted input. A board in every case."""
    _, info, _ = exported
    board = _unrouted_copy(tmp_path)
    by_net = {}
    for pd in info["pads"]:
        if pd.get("net") and "F.Cu" in pd["layers"] and pd["attr"] == "smd":
            by_net.setdefault(pd["net"], []).append(pd)
    net, (a, b) = next((n, ps[:2]) for n, ps in sorted(by_net.items()) if len(ps) >= 2)
    xy = lambda p_: f"{round(p_['pos'][0] * 10000)} {round(-p_['pos'][1] * 10000)}"
    canned = tmp_path / "canned.ses"
    canned.write_text(f"""(session board
  (base_design board)
  (routes
    (resolution um 10)
    (parser (host_cad "KiCad's Pcbnew") (host_version "10"))
    (library_out)
    (network_out
      (net "{net}"
        (wire (path F.Cu 2000 {xy(a)} {xy(b)}))
      )
    )
  )
)
""")
    fake = tmp_path / "fake-freerouting"
    fake.write_text(FAKE_ROUTER.format(canned=str(canned)))
    fake.chmod(0o755)
    monkeypatch.setenv("KAE_BRIDGE_FREEROUTING", str(fake))
    # the fake needs no memory: its own slots, so it never waits for a host-wide Freerouting
    # slot (kae.route.freerouting._Slot) held by real routers, which would spend the deadline
    monkeypatch.setenv("KAE_FR_LOCKDIR", str(tmp_path / "fr-slots"))
    fast = dict(repair=False, router_share_alone=0.25, router_grace=2, plane_escapes=False)

    out = tmp_path / "out" / "board.kicad_pcb"
    rep = bridge.route(board, out, time_s=50, workdir=tmp_path / "wd", opts=fast)
    assert rep["router"]["timed_out"] and rep["router_quick"]["rc"] == 0
    assert rep["status"] == "routed" and out.exists()
    routing = pcbnew_io.edit_routing(out, tmp_path / "l.kicad_pcb")["routing"]
    assert [r["net"] for r in routing] == [net]

    canned.unlink()   # now the quick pass writes nothing either
    out2 = tmp_path / "out2" / "board.kicad_pcb"
    rep2 = bridge.route(board, out2, time_s=30, workdir=tmp_path / "wd2", opts=fast)
    assert rep2["status"] == "no_session" and rep2["router"]["timed_out"]
    assert out2.read_bytes() == board.read_bytes()


@needs_router
def test_repair_round_without_a_session_is_a_failed_round(routed, exported, tmp_path, monkeypatch):
    """A repair round whose router run is killed before writing anything counts as a failed
    round: the loop goes on (up to its failure limit) and the best board stays."""
    from kae.route import repair
    board, out, _, _ = routed
    _, info, _ = exported
    cur = tmp_path / "board.kicad_pcb"
    shutil.copy(out, cur)
    before = cur.read_bytes()
    calls = []

    def killed(*a, **k):
        calls.append(k.get("budget_s"))
        return freerouting.Run(rc=-9, ses=None, log="", seconds=0.1, timed_out=True)

    monkeypatch.setattr(repair.freerouting, "route", killed)
    p = constraints.plan(info, board)
    rep = repair.loop(board, cur, tmp_path / "wd", p, info, dict(rounds=4, severities={}),
                      deadline=__import__("time").monotonic() + 600)
    rounds = [r for r in rep["rounds"] if r.get("round", 0) > 0]
    if not rounds:
        pytest.skip("the routed fixture needed no repair")
    assert len(calls) == repair.FAILS and rounds[-1].get("stopped") == "no improvement"
    assert all(r.get("kept") is False for r in rounds)
    assert cur.read_bytes() == before


@needs_router
def test_a_locked_stub_on_a_rounded_pad_centre_routes_connected(tmp_path):
    """At x >= 100 mm KiCad's DSN export rounds a pad centre such as 133.2125 mm to whole
    micrometres, and Freerouting joins wiring to a pin only at its exact centre: a locked
    stub R10.1 -> R11.1 read as floating, and the net's other pin was left open. With the
    wiring snapped onto the pin centres (translate.snap_wiring) Freerouting sees the stub
    joined: R12.1 routes to it, no SIG connection is open, and the stub comes back
    byte-identical."""
    import critical_fixtures as F
    from kae.route import critical_write as W
    r = "Resistor_SMD:R_0805_2012Metric"
    pads = lambda: [("1", "SIG", -1.0375, 0.0, 1.0, 1.4, "smd", 0.0, "", "passive"),     # noqa: E731
                    ("2", "SIG2", 1.0375, 0.0, 1.0, 1.4, "smd", 0.0, "", "passive")]
    extra = [("R10", "1k", r, 134.25, 126.0, 0.0, pads(), (1.8, 1.0)),
             ("R11", "1k", r, 134.25, 128.5, 0.0, pads(), (1.8, 1.0)),
             ("R12", "1k", r, 104.25, 127.0, 0.0, pads(), (1.8, 1.0))]
    src = F.write_board(tmp_path / "in", extra=extra)
    shutil.copy(FIXTURE.with_suffix(".kicad_dru"), src.with_suffix(".kicad_dru"))
    board = tmp_path / "in" / "stub.kicad_pcb"
    uid = "5e0b5e0b-0000-4000-8000-000000000001"
    W.append_items(src, board, tracks=[("SIG", "F.Cu", 0.25, (133.2125, 126.0), (133.2125, 128.5), uid)])
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(src.with_suffix(ext), board.with_suffix(ext))
    before = _blocks(board.read_text())[uid]
    out = tmp_path / "out" / "board.kicad_pcb"
    rep = bridge.route(board, out, time_s=150, workdir=tmp_path / "wd", opts=dict(rounds=1))
    assert rep["status"] == "routed" and rep["translate"]["wiring_snapped"]["to_pins"] == 2
    assert "133212.5" in (tmp_path / "wd" / "board.dsn").read_text()
    assert _blocks(out.read_text())[uid] == before
    report = drc.run(drc.stage_board(out, board, tmp_path / "drc"), tmp_path / "drc" / "drc.json")
    open_sig = [u for u in report.get("unconnected_items") or []
                if any("[SIG" in it.get("description", "") for it in u.get("items", []))]
    assert not open_sig, json.dumps(open_sig[:3], indent=1)
    log = (tmp_path / "wd" / "freerouting.log").read_text()
    assert "R10-1" not in log and "R11-1" not in log          # never an "unrouted connection"
    # unsnapped, Freerouting joined the "floating" stub to the pins with 0.5 um slivers
    from kae.board import kicad_file
    import math
    slivers = [t for t in kicad_file.load(out).tracks if not t.locked and math.dist(t.start, t.end) < 0.002]
    assert not slivers, slivers


@needs_router
def test_last_mile_rejoins_a_net_cut_open(routed, exported, tmp_path):
    """Cut a routed signal net open (all its tracks removed): kae.route.lastmile joins its
    pads again with the grid router, and KiCad's DRC on the re-opened board agrees."""
    from kae.board.kicad_file import load
    from kae.route import critical_write as W
    from kae.route import lastmile
    board, out, rep, d = routed
    _, info, _ = exported
    b = load(out)
    zone_nets = {z.net for z in b.zones}
    pads = {}
    for f in b.footprints:
        for p in f.pads:
            pads[p.net] = pads.get(p.net, 0) + 1
    nets = sorted({t.net for t in b.tracks if t.net and t.net not in zone_nets and pads.get(t.net, 0) >= 2},
                  key=lambda n: (pads[n], n))
    assert nets
    net = nets[0]
    cut = tmp_path / "cut.kicad_pcb"
    W.edit(out, cut, remove=[t.uuid for t in b.tracks if t.net == net] + [v.uuid for v in b.vias if v.net == net])
    staged = drc.stage_board(cut, board, tmp_path / "cut")
    before = drc.run(staged, tmp_path / "cut" / "drc.json")
    assert net in lastmile.open_nets(before)
    p = constraints.plan(info, board)
    fills = pcbnew_io.zone_fills(staged)["zones"]
    cand = tmp_path / "cand.kicad_pcb"
    r = lastmile.close(staged, info, p, fills, cand, nets=lastmile.open_nets(before), log=lambda *a: None)
    assert r["joined"] >= 1
    after = drc.run(drc.stage_board(cand, board, tmp_path / "cand"), tmp_path / "cand" / "drc.json")
    assert net not in lastmile.open_nets(after)
    assert drc.summary(after)["errors"] <= drc.summary(before)["errors"]


@needs_router
def test_router_copper_named_by_errors_is_taken_out_for_the_last_mile(routed, tmp_path):
    """Routed (unlocked) copper that DRC errors name is taken out by repair._rip_errors,
    leaving a board without errors for the last mile to join exactly; with an error that
    names no router copper, nothing is taken out."""
    from kae.route import critical_write as W
    from kae.route import repair
    board, out, rep, d = routed
    r_base = drc.run(drc.stage_board(out, board, tmp_path / "base"), tmp_path / "base" / "drc.json")
    base = drc.summary(r_base)["errors"]
    lst = pcbnew_io.edit_routing(out, tmp_path / "l.kicad_pcb")["routing"]
    t = max((r for r in lst if r["kind"] == "track" and not r.get("locked") and r.get("layer") == "F.Cu"),
            key=lambda r: ((r["b"][0] - r["a"][0]) ** 2 + (r["b"][1] - r["a"][1]) ** 2))
    bad = tmp_path / "bad.kicad_pcb"
    pcbnew_io.edit_routing(out, bad, widths={t["uuid"]: 3.0})        # far too wide: clearances break
    r0 = drc.run(drc.stage_board(bad, board, tmp_path / "bad"), tmp_path / "bad" / "drc.json")
    assert drc.summary(r0)["errors"] > base
    got = repair._rip_errors(board, bad, r0, tmp_path / "rip", set(), lambda: 600)
    assert got is not None
    cand, r1, s1 = got
    assert s1["errors"] == 0 and t["uuid"] not in {r["uuid"] for r in W.routing(cand)}
    # the same track fixed (a pre-route): not the router's to take out
    assert repair._rip_errors(board, bad, r0, tmp_path / "rip2", {t["uuid"]}, lambda: 600) is None
