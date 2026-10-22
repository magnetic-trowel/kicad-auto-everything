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
@needs_fr
def test_probe_routes_the_rebuilt_placement(tasks):
    root, _ = tasks
    row = _run(root, adapters.Reference(), kinds=("place",), name="ref-probe", timeout=300,
               probe=adapters.Freerouting())[0]
    assert row["score"]["legal"], row["score"]
    p = row["probe"]["score"]
    assert p["valid"] and p["clean"], p


@needs_kicad
def test_rescore_rescores_saved_outputs(tasks):
    """A scoring fix is applied to a finished run without re-running the method."""
    import json
    from kaebench.score import SCORE_VERSION
    root, _ = tasks
    _run(root, adapters.Reference(), kinds=("route", "place"), name="ref-rescore")
    run_dir = root / "results" / "ref-rescore"
    for p in run_dir.glob("*/*/*/attempt-*/attempt.json"):  # as if scored by an older, wrong scorer
        row = json.loads(p.read_text())
        row["score"] = dict(valid=False, clean=False, legal=False)
        row["score_version"] = 0
        p.write_text(json.dumps(row))
    runner.rescore(run_dir)
    rows = {r["kind"]: r for r in report.load_rows(run_dir)}
    assert rows["route"]["score"]["clean"] and rows["place"]["score"]["legal"]
    assert all(r["score_version"] == SCORE_VERSION and r["rescored"][0]["from_version"] == 0
               for r in rows.values())
    assert json.loads((run_dir / "run.json").read_text())["rescored"][0]["attempts"] == 2
    runner.rescore(run_dir)  # already current: nothing is rescored again
    assert all(len(r["rescored"]) == 1 for r in report.load_rows(run_dir))
