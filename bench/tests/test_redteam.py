# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Red-team tests: cheating methods must come out invalid, be blocked, or gain nothing.

Every cheat runs as an ordinary `--command` method (bench/tests/redteam_cheats.py) on the
tasks built from fixtures/redteam.kicad_pcb: two resistors, a locked mounting hole and a
keepout that the human routing respects. Add a case here for every new way to cheat.
"""
import hashlib
import shutil
import sys
from pathlib import Path

import pytest

from kaebench import adapters, prepare, report, runner, tools
from kaebench.boardfiles import board_path

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "redteam.kicad_pcb"
# A project with a text variable: KiCad turns it into a board property on load.
PROJECT = HERE / "fixtures" / "redteam.kicad_pro"
CHEATS = HERE / "redteam_cheats.py"


def _have(fn):
    try:
        fn()
        return True
    except tools.ToolError:
        return False


pytestmark = [
    pytest.mark.kicad,
    pytest.mark.skipif(not (_have(tools.kicad_cli) and _have(tools.kicad_python)),
                       reason="KiCad 10 not installed"),
    pytest.mark.skipif(not shutil.which("bwrap"), reason="bubblewrap not installed"),
]


@pytest.fixture(scope="module")
def rt(tmp_path_factory):
    root = tmp_path_factory.mktemp("redteam")
    src = root / "src"
    src.mkdir()
    shutil.copy2(FIXTURE, src / "redteam.kicad_pcb")
    shutil.copy2(PROJECT, src / "redteam.kicad_pro")
    entry = dict(id="redteam", repo="https://example.invalid/r", commit="0" * 40,
                 pcb_path="redteam.kicad_pcb", license="GPL-3.0-or-later", tags=["2layer"])
    rec = prepare.prepare_board(entry, {"kicad_pcb": str(src / "redteam.kicad_pcb"), "pcb_sha256": "x",
                                        "kicad_pro": str(src / "redteam.kicad_pro")}, root / "tasks")
    assert rec["qualified"], rec["reference"]["drc"]
    assert rec["footprint_uuids_reassigned"] == 1
    return root, rec


def _run(root, ad, kind, name):
    run_dir = runner.run(root / "tasks", root / "results", ad, kinds=(kind,), name=name,
                         progress=lambda *_: None)
    rows = report.load_rows(run_dir)
    assert len(rows) == 1
    return rows[0], run_dir


def cheat(root, mode, kind="route", path="", sandbox=True):
    sb = adapters.Sandbox(enabled=sandbox, ro=[HERE])
    ad = adapters.Command(f"{sys.executable if not sandbox else 'python3'} {CHEATS} {mode} "
                          f"{{input}} {{output}} {path}", name=f"cheat-{mode}", kinds=(kind,), sandbox=sb)
    return _run(root, ad, kind, f"{kind}-{mode}-{'sb' if sandbox else 'nosb'}")


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# --- the honest baselines must pass, so the cheat failures below mean something ---

def test_tasks_carry_no_routing_leftovers(rt):
    """Teardrops belong to the routing: stripped from both inputs (in a place task they
    would also mark where the human put the pads)."""
    root, _ = rt
    assert "(teardrop" in FIXTURE.read_text()
    for kind in ("route", "place"):
        assert "(teardrop" not in board_path(root / "tasks" / "redteam" / kind / "input").read_text()


def test_reference_is_valid(rt):
    root, _ = rt
    for kind in ("route", "place"):
        row, _ = _run(root, adapters.Reference(), kind, f"ref-{kind}")
        s = row["score"]
        assert s["valid"] and s["foreign"]["count"] == 0, s
        assert s["clean"] if kind == "route" else s["legal"], s


def test_honest_methods_pass(rt):
    root, _ = rt
    s = cheat(root, "honest")[0]["score"]
    assert s["valid"] and s["clean"], s
    s = cheat(root, "place_honest", kind="place")[0]["score"]
    assert s["valid"] and s["legal"], s


# --- tampering with anything but the allowed changes makes the result invalid ---

@pytest.mark.parametrize("mode,broken", [
    ("move_part", "placement"),
    ("delete_keepout", "untouched"),
    ("grow_outline", "untouched"),
    ("edit_setup", "untouched"),
    ("shrink_pad", "untouched"),
    ("pad_clearance", "untouched"),
    ("swap_net", "pad_nets"),
    ("add_layer", None),  # either unloadable or flagged; both are invalid
    ("bogus_net", "nets"),
])
def test_route_tampering_is_invalid(rt, mode, broken):
    root, _ = rt
    row, _ = cheat(root, mode)
    s = row["score"]
    assert row["status"] == "ok", row
    assert not s["valid"] and not s["clean"], s
    if broken:
        assert s["integrity"][broken] is False, s["integrity"]


def test_deleted_keepout_still_applies(rt):
    """The scored board is rebuilt from the task input, so the keepout is still there."""
    root, _ = rt
    row, run_dir = cheat(root, "delete_keepout")
    assert row["score"]["foreign"]["by_kind"] == {"zone": 1}
    rebuilt = next(run_dir.glob("*/route/*/attempt-0/score")) / "board.kicad_pcb"
    assert "KEEPOUT" in rebuilt.read_text()


@pytest.mark.parametrize("mode,broken", [
    ("move_locked", "locked"),
    ("delete_footprint", "footprints"),
    ("shrink_courtyard", "untouched"),
    ("add_copper", "no_copper"),
    ("place_grow_outline", "untouched"),
])
def test_place_tampering_is_invalid(rt, mode, broken):
    root, _ = rt
    row, _ = cheat(root, mode, kind="place")
    s = row["score"]
    assert row["status"] == "ok", row
    assert not s["valid"] and not s["legal"] and s["integrity"][broken] is False, s


def test_own_rules_are_ignored(rt):
    """Rules shipped next to the output never reach the scorer."""
    root, _ = rt
    s = cheat(root, "permissive_rules")[0]["score"]
    assert s["valid"] and not s["clean"] and s["unconnected"] == 2, s


# --- the sandbox keeps the answers out of reach ---

def test_sandbox_hides_reference(rt):
    root, _ = rt
    ref = board_path(root / "tasks" / "redteam" / "reference")
    row, _ = cheat(root, "read_file", path=ref)
    assert row["status"] == "no_output", row
    row, _ = cheat(root, "read_file", kind="place", path=board_path(root / "tasks" / "redteam" / "route" / "input"))
    assert row["status"] == "no_output", row


def test_sandbox_blocks_writes_outside_attempt(rt):
    root, _ = rt
    ref = board_path(root / "tasks" / "redteam" / "reference")
    before = _sha(ref)
    cheat(root, "write_file", path=ref)
    assert _sha(ref) == before


def test_sandbox_blocks_network(rt):
    root, _ = rt
    row, _ = cheat(root, "network")
    assert row["status"] == "no_output", row


def test_unsandboxed_copy_is_flagged(rt):
    """Without the sandbox a method can copy the human layout; the copy metric and the
    report's unsandboxed warning show it."""
    root, _ = rt
    row, run_dir = cheat(root, "read_file", path=board_path(root / "tasks" / "redteam" / "reference"),
                         sandbox=False)
    s = row["score"]
    assert s["copy"]["frac"] == 1.0 and row["adapter_meta"]["sandboxed"] is False
    summary, _ = report.report([run_dir])
    assert "Unsandboxed" in report.to_markdown(summary)
