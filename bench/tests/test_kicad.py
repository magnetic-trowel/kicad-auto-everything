# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end tests on a two-net fixture board. Need KiCad 10; Freerouting optional."""
import shutil
from pathlib import Path

import pytest

from kaebench import adapters, prepare, report, runner, tools

FIXTURE = Path(__file__).parent / "fixtures" / "two_pads.kicad_pcb"


def _have(fn):
    try:
        fn()
        return True
    except tools.ToolError:
        return False


needs_kicad = pytest.mark.skipif(not (_have(tools.kicad_cli) and _have(tools.kicad_python)),
                                 reason="KiCad 10 not installed")
needs_fr = pytest.mark.skipif(not _have(tools.freerouting_cmd), reason="Freerouting not installed")


@pytest.fixture(scope="module")
def tasks(tmp_path_factory):
    root = tmp_path_factory.mktemp("kae")
    src = root / "src"
    src.mkdir()
    shutil.copy2(FIXTURE, src / "two_pads.kicad_pcb")
    entry = dict(id="fixture", repo="https://example.invalid/r", commit="0" * 40,
                 pcb_path="two_pads.kicad_pcb", license="GPL-3.0-or-later", tags=["2layer"])
    fetched = {"kicad_pcb": str(src / "two_pads.kicad_pcb"), "pcb_sha256": "x"}
    rec = prepare.prepare_board(entry, fetched, root / "tasks")
    return root, rec


def _run(root, ad, **kw):
    run_dir = runner.run(root / "tasks", root / "results", ad, progress=lambda *_: None, **kw)
    return report.load_rows(run_dir)


@needs_kicad
def test_prepare(tasks):
    _, rec = tasks
    assert rec["qualified"] and rec["split"] == "A"
    assert rec["reference"]["stats"]["connections"] == 2
    assert rec["tasks"]["route"]["input_stats"]["tracks"] == 0
    assert rec["tasks"]["route"]["input_drc"]["unconnected"] == 2
    assert rec["tasks"]["route"]["input_stats"]["placement_hash"] == rec["reference"]["stats"]["placement_hash"]
    assert rec["tasks"]["place"]["input_stats"]["placement_hash"] != rec["reference"]["stats"]["placement_hash"]


@needs_kicad
def test_reference_and_noop(tasks):
    root, _ = tasks
    rows = {r["kind"]: r for r in _run(root, adapters.Reference(), kinds=("route", "place"), name="ref")}
    assert rows["route"]["score"]["clean"] and rows["route"]["score"]["wl_ratio"] == 1.0
    assert rows["place"]["score"]["legal"] and rows["place"]["score"]["hpwl_ratio"] == 1.0
    noop = _run(root, adapters.Noop(), name="noop")[0]["score"]
    assert noop["valid"] and not noop["clean"] and noop["completion"] == 0.0 and noop["unconnected"] == 2


@needs_kicad
def test_moving_parts_in_a_route_task_is_invalid(tasks):
    root, _ = tasks
    cheat = adapters.Command("sed 's/(at 120 105)/(at 121 105)/' {input} > {output}", name="cheat")
    s = _run(root, cheat, name="cheat")[0]["score"]
    assert not s["valid"] and not s["integrity"]["placement"] and not s["clean"]


@needs_kicad
def test_unplaced_board_is_not_legal(tasks):
    root, _ = tasks
    s = _run(root, adapters.Noop(), kinds=("place",), name="noop-place")[0]["score"]
    assert s["valid"] and not s["legal"] and s["outside"] == 2


@needs_kicad
@needs_fr
def test_freerouting_routes_fixture(tasks):
    root, _ = tasks
    s = _run(root, adapters.Freerouting(), name="fr", timeout=300)[0]["score"]
    assert s["valid"] and s["clean"], s


@needs_kicad
def test_covered_micro_arcs(tmp_path):
    def arc(x, y, uid):
        return (f'\t(arc (start {x} {y}) (mid {x + 0.0000003} {y + 0.0000004}) (end {x + 0.0000006} {y}) '
                f'(width 0.1) (layer "F.Cu") (net 1) (uuid "{uid}"))\n')
    text = FIXTURE.read_text()
    cut = text.rindex(")")
    covered = ["55555555-5555-5555-5555-555555555551", "55555555-5555-5555-5555-555555555552"]
    text = (text[:cut] + arc(109.2, 105, covered[0]) + arc(114, 107, covered[1])  # on R1 pad 1; on a track
            + arc(115, 108.5, "55555555-5555-5555-5555-555555555553")  # alone: it is copper
            + arc(109.6, 105, "55555555-5555-5555-5555-555555555554")  # half off the pad edge
            + text[cut:])
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text(text)
    res = tools.run_ops("covered-micro-arcs", pcb)
    assert res["candidates"] == 4 and sorted(res["covered"]) == covered
