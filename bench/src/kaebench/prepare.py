# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn fetched boards into benchmark tasks.

Recipe (after PCBWorld): convert to the installed KiCad version, keep each board's own
rules, qualify boards whose human layout is fully connected and free of error-level
DRC violations, keep the human copper as the reference, split by pad count. A board also
qualifies only if its human layout passes the benchmark's own scoring as if it were a
method's output (the round trip), so every qualified task is solvable under the rules
methods are held to.

Task kinds:
  route  placement kept, all tracks/vias removed (locked copper optionally kept)
  place  all copper removed and unlocked footprints moved to a staging area off-board;
         locked footprints stay where the designer put them
"""
import json
import shutil
from pathlib import Path

from . import score, tools
from .boardfiles import STEM, board_path, install_rules

TASK_KINDS = ("route", "place")
# 2: place tasks keep locked footprints in place (1 moved them off-board, so boards with
#    locked parts could not be placed legally and the human placement scored invalid)
# 3: teardrops are stripped with the routing (left behind they were stray copper and marked
#    the human pad positions in place tasks); footprints sharing a uuid get unique ones; the
#    record lists the pads each footprint has outside the outline in the human placement
# 4: qualification also requires the round trip (the human layout scored like a method's
#    output); it drops boards whose routing relies on what tasks strip, e.g. teardrops that
#    carry a connection or DRC rules keyed to the human copper's groups
# 5: footprints carrying Edge.Cuts graphics stay in place in place tasks and may not be moved,
#    like locked ones (staged off-board they broke the board outline)
TASK_SPEC = 5
# Oldest spec each task kind is still valid under (spec 5 changed only place tasks).
MIN_TASK_SPEC = {"route": 4, "place": 5}


def split_of(pads):
    if pads <= 31:
        return "A"
    if pads <= 100:
        return "B"
    return "C"


POSE_KEYS = ("uuid", "x", "y", "rot", "back")


def pose(row):
    return {k: row[k] for k in POSE_KEYS}


def _strip_stats(st):
    out = {k: v for k, v in st.items() if k not in ("placement", "path", "ok")}
    out["locked_placement"] = [pose(r) for r in st["placement"] if r["locked"]]
    return out


def prepare_board(entry, fetched, tasks_dir, kinds=TASK_KINDS, keep_locked=False, force=False):
    """Create tasks_dir/<id>/{reference,route,place}/ and task.json. Returns the task record."""
    tdir = Path(tasks_dir) / entry["id"]
    task_json = tdir / "task.json"
    if task_json.exists() and not force:
        return json.loads(task_json.read_text())
    if tdir.exists():
        shutil.rmtree(tdir)
    ref = tdir / "reference"
    ref.mkdir(parents=True)
    for key, ext in (("kicad_pro", ".kicad_pro"), ("kicad_dru", ".kicad_dru")):
        if fetched.get(key):
            shutil.copy2(fetched[key], ref / f"{STEM}{ext}")
    # Converting writes the current KiCad format; rules stay in the project files.
    conv = tools.run_ops("convert", fetched["kicad_pcb"], board_path(ref))
    ref_stats = tools.run_ops("stats", board_path(ref))
    ref_drc = tools.summarize_drc(tools.run_drc(board_path(ref), ref / "drc.json"))
    human_clean = ref_drc["unconnected"] == 0 and ref_drc["errors"] == 0
    record = dict(
        id=entry["id"], license=entry.get("license"), license_tier=entry.get("license_tier"),
        repo=entry["repo"], commit=entry["commit"], pcb_path=entry["pcb_path"],
        pcb_sha256=fetched.get("pcb_sha256"), tags=entry.get("tags") or [],
        split=split_of(ref_stats["pads"]), qualified=human_clean, human_clean=human_clean, task_spec=TASK_SPEC,
        footprint_uuids_reassigned=conv.get("footprint_uuids_reassigned", 0),
        has_project_rules=(ref / f"{STEM}.kicad_pro").exists(),
        reference=dict(stats=_strip_stats(ref_stats), drc=ref_drc,
                       pads_outside={r["uuid"]: r["pads_outside"] for r in ref_stats["placement"]
                                     if r.get("pads_outside")}),
        tasks={},
    )
    for kind in kinds:
        kdir = tdir / kind / "input"
        kdir.mkdir(parents=True)
        install_rules(ref, kdir)
        if kind == "route":
            tools.run_ops("strip-routing", board_path(ref), board_path(kdir),
                          *(["--keep-locked"] if keep_locked else []))
        else:
            tools.run_ops("strip-placement", board_path(ref), board_path(kdir))
        st = tools.run_ops("stats", board_path(kdir))
        drc = tools.summarize_drc(tools.run_drc(board_path(kdir), kdir / "drc.json"))
        record["tasks"][kind] = dict(input_stats=_strip_stats(st), input_drc=drc,
                                     keep_locked=keep_locked if kind == "route" else "footprints")
    if human_clean:
        record["roundtrip"] = _roundtrip(tdir, record)
        record["qualified"] = all(v["ok"] for v in record["roundtrip"].values())
    task_json.write_text(json.dumps(record, indent=1))
    return record


def _verdict(s, ok):
    return dict(ok=bool(s.get("valid") and ok),
                integrity=[k for k, v in (s.get("integrity") or {}).items() if not v],
                foreign=(s.get("foreign") or {}).get("by_kind"), errors_by_type=s.get("errors_by_type"),
                unconnected=s.get("unconnected"), outside=s.get("outside"),
                placement_errors=s.get("placement_errors"))


def _roundtrip(tdir, record):
    """Score the human layout of each task kind as if a method had produced it."""
    rt = tdir / "roundtrip"
    out = {}
    try:
        if "route" in record["tasks"]:
            s = score.score_route_task(tdir, board_path(tdir / "reference"), rt / "route", record,
                                       allow_copy=True)
            out["route"] = _verdict(s, s.get("clean"))
        if "place" in record["tasks"]:
            human = rt / "human-placement"
            human.mkdir(parents=True, exist_ok=True)
            tools.run_ops("strip-routing", board_path(tdir / "reference"), board_path(human))
            s, _ = score.score_place_task(tdir, board_path(human), rt / "place", record, allow_copy=True)
            out["place"] = _verdict(s, s.get("legal"))
    finally:
        shutil.rmtree(rt, ignore_errors=True)
    return out


def load_tasks(tasks_dir, only=None, qualified_only=True, splits=None):
    recs = []
    for tj in sorted(Path(tasks_dir).glob("*/task.json")):
        r = json.loads(tj.read_text())
        if only and r["id"] not in only:
            continue
        if qualified_only and not r["qualified"]:
            continue
        if splits and r["split"] not in splits:
            continue
        recs.append(r)
    return recs
