# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route against live KiCad (and Freerouting for the end-to-end test); skipped when
they are missing."""
import json
import shutil
from pathlib import Path

import pytest

from kae.board import pcbnew_io, sexpr
from kae.route import bridge, constraints, drc, freerouting, specctra, translate

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
    assert v["checked"] > 500
    assert v["mismatched"] == 0, v["examples"]
    assert not v["unsupported"] and not v["rule_errors"]


def test_export_carries_what_the_dsn_leaves_out(exported):
    board, info, dsn = exported
    assert info["tracks"] == 0
    assert set(info["netclasses"]) >= {"Default", "Power"}
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


def _have_freerouting():
    try:
        freerouting.command()
        drc.kicad_cli()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _have_freerouting(), reason="no Freerouting or kicad-cli")
def test_route_end_to_end_has_no_translation_errors(tmp_path):
    board = _unrouted_copy(tmp_path)
    out = tmp_path / "out" / "board.kicad_pcb"
    out.parent.mkdir()
    rep = bridge.route(board, out, time_s=240, workdir=tmp_path / "wd", opts=dict(rounds=2))
    assert rep["status"] == "routed" and out.exists()
    staged = drc.stage_board(out, board, tmp_path / "drc")
    report = drc.run(staged, tmp_path / "drc" / "drc.json")
    bad = [v for v in drc.errors(report) if v["type"] in TRANSLATION]
    assert not bad, json.dumps(bad[:5], indent=1)
