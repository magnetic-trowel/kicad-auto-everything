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
    rep = bridge.route(pre, out2, time_s=120, workdir=tmp_path / "wd2", opts=dict(rounds=1))
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
