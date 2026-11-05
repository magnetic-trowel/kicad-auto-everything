# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Red-team tests: cheating methods must come out invalid, be blocked, or gain nothing.

Every cheat runs as an ordinary `--command` method (bench/tests/redteam_cheats.py) on the
tasks built from fixtures/redteam.kicad_pcb: two resistors, a locked mounting hole, a
keepout that the human routing respects, and a mechanical interface (connector J1, button SW1,
mounting hole H2) that place-fixed tasks keep at the human pose. Add a case here for every new way to cheat.
"""
import hashlib
import shutil
import subprocess
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
    assert all(v["ok"] for v in rec["roundtrip"].values()), rec["roundtrip"]
    assert set(rec["roundtrip"]) == {"route", "place", "place-fixed"}
    return root, rec


def _run(root, ad, kind, name):
    run_dir = runner.run(root / "tasks", root / "results", ad, kinds=(kind,), name=name,
                         progress=lambda *_: None)
    rows = report.load_rows(run_dir)
    assert len(rows) == 1
    return rows[0], run_dir


def cheat(root, mode, kind="route", path="", sandbox=True, ro=()):
    sb = adapters.Sandbox(enabled=sandbox, ro=[HERE, *ro])
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
    # a footprint carrying Edge.Cuts is part of the outline: it stays where the designer put it
    place = board_path(root / "tasks" / "redteam" / "place" / "input").read_text()
    assert '(uuid "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1")\n\t\t(at 125 114)' in place


def test_reference_is_valid(rt):
    root, _ = rt
    for kind in ("route", "place", "place-fixed", "joint-fixed"):
        row, _ = _run(root, adapters.Reference(), kind, f"ref-{kind}")
        s = row["score"]
        assert s["valid"] and s["foreign"]["count"] == 0, s
        assert s["legal"] if kind.startswith("place") else s["clean"], s


def test_place_fixed_keeps_the_mechanical_interface(rt):
    """The classifier fixes the connector, the button and the unlocked mounting hole (the locked
    one is fixed anyway); the test points and resistors stay movable."""
    root, rec = rt
    t = rec["tasks"]["place-fixed"]
    fixed = {r["ref"]: r["class"] for r in t["fixed_mech"]}
    assert fixed == {"J1": "connector", "SW1": "user", "H1": "mounting", "H2": "mounting"}, t["fixed_mech"]
    assert rec["tasks"]["place"]["movable"] == 7 and t["movable"] == 4
    locked = {r["uuid"] for r in t["input_stats"]["locked_placement"]}
    assert {r["uuid"] for r in t["fixed_mech"]} <= locked
    text = board_path(root / "tasks" / "redteam" / "place-fixed" / "input").read_text()
    assert '(uuid "cccccccc-cccc-cccc-cccc-ccccccccccc1")\n\t\t(at 130 103)' in text


def test_noop_place_fixed_is_valid_but_not_legal(rt):
    root, _ = rt
    s = _run(root, adapters.Noop(), "place-fixed", "noop-place-fixed")[0]["score"]
    assert s["valid"] and not s["legal"] and s["outside"] > 0, s


def test_honest_methods_pass(rt):
    root, _ = rt
    s = cheat(root, "honest")[0]["score"]
    assert s["valid"] and s["clean"], s
    s = cheat(root, "place_honest", kind="place")[0]["score"]
    assert s["valid"] and s["legal"], s
    s = cheat(root, "place_honest", kind="place-fixed")[0]["score"]
    assert s["valid"] and s["legal"], s
    s = cheat(root, "joint_honest", kind="joint-fixed")[0]["score"]
    assert s["valid"] and s["legal"] and s["clean"], s


def test_moving_a_fixed_connector(rt):
    """Moving the connector is fine in a place task and caught in a place-fixed task, also when
    the method unlocks it first."""
    root, _ = rt
    s = cheat(root, "move_connector", kind="place")[0]["score"]
    assert s["valid"] and s["legal"], s
    s = cheat(root, "move_connector", kind="place-fixed")[0]["score"]
    assert not s["valid"] and not s["legal"] and s["integrity"]["locked"] is False, s
    assert s["locked_moved"] == ["J1"], s
    s = cheat(root, "unlock_connector", kind="place-fixed")[0]["score"]
    assert not s["valid"] and s["locked_moved"] == ["J1"] and s["integrity"]["untouched"] is False, s
    s = cheat(root, "move_connector", kind="joint-fixed")[0]["score"]
    assert not s["valid"] and not s["clean"] and s["integrity"]["place_locked"] is False, s


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
])
def test_route_tampering_is_invalid(rt, mode, broken):
    root, _ = rt
    row, _ = cheat(root, mode)
    s = row["score"]
    assert row["status"] == "ok", row
    assert not s["valid"] and not s["clean"], s
    if broken:
        assert s["integrity"][broken] is False, s["integrity"]


def test_copper_on_an_invented_net_gains_nothing(rt):
    """KiCad gives a track with an unknown net name the net of the copper it touches, so an
    invented name buys nothing a method could not get by naming the right net; floating
    copper keeps its new net, is counted, and connects nothing. The result scores like the
    honest routing it was added to."""
    root, _ = rt
    s = cheat(root, "bogus_net")[0]["score"]
    assert s["valid"] and s["clean"] and s["new_net_items"] == 1, s


def test_copper_graphic_net_is_not_a_change(rt):
    """KiCad assigns nets to copper graphics that imported tracks touch; the rebuilt board
    keeps the input's graphic, so the net is ignored when comparing."""
    root, _ = rt
    s = cheat(root, "graphic_net")[0]["score"]
    assert s["valid"] and s["clean"], s


def test_deleted_keepout_still_applies(rt):
    """The scored board is rebuilt from the task input, so the keepout is still there."""
    root, _ = rt
    row, run_dir = cheat(root, "delete_keepout")
    assert row["score"]["foreign"]["by_kind"] == {"zone": 1}
    rebuilt = next(run_dir.glob("*/route/*/attempt-0/score")) / "board.kicad_pcb"
    assert "KEEPOUT" in rebuilt.read_text()


# --- added zones (score v10): a route method may pour copper, within the rules ---

def test_added_pour_connects_and_scores_valid(rt):
    """An N1 pour over both N1 pads replaces N1's tracks: valid, clean, and its refilled copper
    counts in connectivity (the same routing without it leaves N1 open). Its fill is not taken
    from the output; the rebuilt board carries the zone unfilled and DRC refills it."""
    root, _ = rt
    s = cheat(root, "n2_only")[0]["score"]
    assert s["valid"] and not s["clean"] and s["unconnected"] == 1 and s["zones_added"] == 0, s
    row, run_dir = cheat(root, "zone_gnd")
    s = row["score"]
    assert s["valid"] and s["clean"] and s["unconnected"] == 0 and s["completion"] == 1.0, s
    assert s["zones_added"] == 1 and s["zone_problems"] == [] and s["integrity"]["zones"], s
    assert not s["suspect_copy"] and s["copy"]["zones"] == dict(matched=0, total=1, suspect=False), s
    rebuilt = (next(run_dir.glob("*/route/*/attempt-0/score")) / "board.kicad_pcb").read_text()
    assert rebuilt.count("abababab-abab-abab-abab-") == 1 and "filled_polygon" not in rebuilt


def test_pad_zone_connection_is_a_route_edit(rt):
    """A pad's own zone connection (solid on a heat pad) may be set: transplanted, not foreign."""
    root, _ = rt
    row, run_dir = cheat(root, "zone_solid_pad")
    s = row["score"]
    assert s["valid"] and s["clean"] and s["pad_zone_connections"] == 1 and s["foreign"]["count"] == 0, s
    rebuilt = (next(run_dir.glob("*/route/*/attempt-0/score")) / "board.kicad_pcb").read_text()
    assert rebuilt.count("(zone_connect 2)") == 1


def test_overlapping_zone_needs_its_own_priority(rt):
    """Over the task's N2 zone, an N1 zone at the same priority is refused (KiCad 10.0.7's filler
    deadlocks on such ties when uuids tie too); at a higher priority it is legal."""
    root, _ = rt
    s = cheat(root, "zone_overlap_tie")[0]["score"]
    assert not s["valid"] and s["integrity"]["zones"] is False, s
    assert "equal priority" in s["zone_problems"][0]["reasons"][0], s
    s = cheat(root, "zone_overlap_priority")[0]["score"]
    assert s["valid"] and s["clean"] and s["zones_added"] == 1, s


def test_copied_human_pour_is_suspect(rt):
    root, _ = rt
    s = cheat(root, "zone_copy")[0]["score"]
    assert s["copy"]["zones"]["matched"] == 1 and s["suspect_copy"], s


@pytest.mark.parametrize("mode,broken,reason", [
    ("zone_edit", "untouched", None),
    ("zone_delete", "untouched", None),
    ("zone_dup_uuid", "zones", "duplicate uuid"),
    ("zone_unknown_net", "zones", "not in the task"),
    ("zone_no_net", "zones", "no net"),
    ("zone_non_copper", "zones", "copper layers"),
    ("zone_outside", "zones", "outside the board outline"),
    ("zone_in_keepout", "zones", "keepout"),
    ("zone_rule_area", "zones", "rule area"),
])
def test_illegal_zones_are_invalid(rt, mode, broken, reason):
    root, _ = rt
    row, _ = cheat(root, mode)
    s = row["score"]
    assert row["status"] == "ok", row
    assert not s["valid"] and not s["clean"] and s["integrity"][broken] is False, s
    if reason:
        assert any(reason in r for z in s["zone_problems"] for r in z["reasons"]), s["zone_problems"]


@pytest.mark.parametrize("kind", ["joint", "joint-fixed"])
def test_joint_tasks_may_add_zones(rt, kind):
    """Joint tasks take added zones and pads' zone connection under the route rules: the
    placement half ignores them (legality judged on the placement alone), the routing half
    transplants and checks them."""
    root, _ = rt
    s = cheat(root, "joint+n2_only", kind=kind)[0]["score"]
    assert s["valid"] and s["legal"] and not s["clean"] and s["unconnected"] == 1, s
    for mode in ("joint+zone_gnd", "joint+zone_solid_pad", "joint+zone_overlap_priority"):
        s = cheat(root, mode, kind=kind)[0]["score"]
        assert s["valid"] and s["legal"] and s["clean"] and s["unconnected"] == 0, (mode, s)
        assert s["integrity"]["route_zones"] and s["place_foreign"]["count"] == 0 and s["zones_added"] == 1, (mode, s)
    assert s["pad_zone_connections"] == 0
    row, run_dir = cheat(root, "joint+zone_solid_pad", kind=kind)
    assert row["score"]["pad_zone_connections"] == 1, row["score"]
    sdir = next(run_dir.glob(f"*/{kind}/*/attempt-0/score"))
    placed_text = (sdir / "placement" / "board.kicad_pcb").read_text()  # what placement legality judged
    assert "abababab-abab-abab-abab-" not in placed_text and "(zone_connect 2)" not in placed_text
    routed_text = (sdir / "routing" / "board.kicad_pcb").read_text()
    assert routed_text.count("abababab-abab-abab-abab-") == 1 and routed_text.count("(zone_connect 2)") == 1
    s = cheat(root, "joint+zone_copy", kind=kind)[0]["score"]
    assert s["copy"]["zones"]["matched"] == 1 and s["suspect_copy"], s


@pytest.mark.parametrize("kind", ["joint", "joint-fixed"])
@pytest.mark.parametrize("mode,broken,reason", [
    ("zone_edit", "untouched", None),
    ("zone_delete", "untouched", None),
    ("zone_dup_uuid", "zones", "duplicate uuid"),
    ("zone_unknown_net", "zones", "not in the task"),
    ("zone_no_net", "zones", "no net"),
    ("zone_non_copper", "zones", "copper layers"),
    ("zone_outside", "zones", "outside the board outline"),
    ("zone_in_keepout", "zones", "keepout"),
    ("zone_rule_area", "zones", "rule area"),
    ("zone_overlap_tie", "zones", "equal priority"),
])
def test_illegal_zones_are_invalid_in_joint_tasks(rt, kind, mode, broken, reason):
    root, _ = rt
    row, _ = cheat(root, f"joint+{mode}", kind=kind)
    s = row["score"]
    assert row["status"] == "ok", row
    assert not s["valid"] and not s["clean"] and s["integrity"][f"route_{broken}"] is False, s
    if broken == "untouched":  # a task zone edited or deleted: the placement half sees it too
        assert s["integrity"]["place_untouched"] is False, s
    else:  # an added zone is the routing half's to judge; the placement stays legal
        assert s["integrity"]["place_untouched"] is True, s
    if reason:
        assert any(reason in r for z in s["zone_problems"] for r in z["reasons"]), s["zone_problems"]


@pytest.mark.parametrize("mode,broken", [
    ("move_locked", "locked"),
    ("move_edge_cut", "locked"),
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


def test_joint_tasks_score_placement_and_routing_together(rt):
    root, _ = rt
    s = cheat(root, "joint_honest", kind="joint")[0]["score"]
    assert s["valid"] and s["legal"] and s["clean"], s
    s = cheat(root, "joint_move_locked", kind="joint")[0]["score"]
    assert not s["valid"] and not s["clean"] and s["integrity"]["place_locked"] is False, s


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


def test_sandbox_hides_the_whole_work_dir(rt):
    """Even when the work dir is readable (bound by --sandbox-ro, or the checkout holding the
    method's code), everything in it but the attempt's own dir stays hidden: here the source
    board in src/, standing in for the board cache."""
    root, _ = rt
    row, _ = cheat(root, "read_file", path=root / "src" / "redteam.kicad_pcb", ro=[root])
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


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bubblewrap not installed")
def test_sandbox_keeps_the_harness_python(tmp_path):
    """The harness's own interpreter (and its venv packages) works inside the sandbox, even
    when it lives under the hidden home directory; otherwise `python` silently changes."""
    argv = adapters.Sandbox().wrap([sys.executable, "-c", "import sys, pytest; print(sys.prefix)"], tmp_path)
    r = subprocess.run(argv, capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0 and r.stdout.strip() == sys.prefix, r.stderr
