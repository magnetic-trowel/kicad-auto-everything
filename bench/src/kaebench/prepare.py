# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn fetched boards into benchmark tasks.

Recipe (after PCBWorld): convert to the installed KiCad version, keep each board's own
rules, qualify boards whose human layout is fully connected and free of error-level
DRC violations, keep the human copper as the reference, split by pad count.

Task kinds:
  route  placement kept, all tracks/vias removed (locked copper optionally kept)
  place  tracks removed and unlocked footprints moved to a staging area off-board
"""
import json
import shutil
from pathlib import Path

from . import tools
from .boardfiles import STEM, board_path, install_rules

TASK_KINDS = ("route", "place")


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
    tools.run_ops("convert", fetched["kicad_pcb"], board_path(ref))
    ref_stats = tools.run_ops("stats", board_path(ref))
    ref_drc = tools.summarize_drc(tools.run_drc(board_path(ref), ref / "drc.json"))
    qualified = ref_drc["unconnected"] == 0 and ref_drc["errors"] == 0
    record = dict(
        id=entry["id"], license=entry.get("license"), license_tier=entry.get("license_tier"),
        repo=entry["repo"], commit=entry.get("commit"), pcb_path=entry["pcb_path"],
        pcb_sha256=fetched.get("pcb_sha256"), tags=entry.get("tags") or [],
        split=split_of(ref_stats["pads"]), qualified=qualified,
        has_project_rules=(ref / f"{STEM}.kicad_pro").exists(),
        reference=dict(stats=_strip_stats(ref_stats), drc=ref_drc),
        tasks={},
    )
    for kind in kinds:
        kdir = tdir / kind / "input"
        kdir.mkdir(parents=True)
        install_rules(ref, kdir)
        op = "strip-routing" if kind == "route" else "strip-placement"
        args = ["--keep-locked"] if keep_locked else []
        tools.run_ops(op, board_path(ref), board_path(kdir), *args)
        st = tools.run_ops("stats", board_path(kdir))
        drc = tools.summarize_drc(tools.run_drc(board_path(kdir), kdir / "drc.json"))
        record["tasks"][kind] = dict(input_stats=_strip_stats(st), input_drc=drc,
                                     keep_locked=keep_locked)
    task_json.write_text(json.dumps(record, indent=1))
    return record


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
