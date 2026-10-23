# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""KiCad DRC with kicad-cli, the way kaebench scores (zones refilled, all severities, mm).

kicad-cli is found as in kaebench: KAE_KICAD_CLI (a command, possibly with a wrapper),
KAE_KICAD_WRAP + kicad-cli (e.g. "apptainer exec ~/kicad.sif"), or kicad-cli on PATH.
The board must have its project files (.kicad_pro, .kicad_dru) beside it, since KiCad takes
rule severities and custom rules from them.
"""
import functools
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

# Violation types that depend on the local library setup, not on the board (as kaebench).
ENV_DEPENDENT = ("lib_footprint_issues", "lib_footprint_mismatch")


class DrcError(RuntimeError):
    pass


@functools.lru_cache(maxsize=None)
def kicad_cli():
    v = os.environ.get("KAE_KICAD_CLI")
    if v:
        return tuple(shlex.split(v))
    w = os.environ.get("KAE_KICAD_WRAP")
    if w:
        return (*shlex.split(w), "kicad-cli")
    p = shutil.which("kicad-cli")
    if not p:
        raise DrcError("kicad-cli not found; set KAE_KICAD_CLI or KAE_KICAD_WRAP")
    return (p,)


def run(board, out_json, timeout=900):
    """kicad-cli pcb drc on `board`; returns the parsed JSON report."""
    board, out_json = Path(board).resolve(), Path(out_json).resolve()
    if out_json.exists():
        out_json.unlink()
    cmd = [*kicad_cli(), "pcb", "drc", "--format", "json", "--refill-zones", "--severity-all",
           "--units", "mm", "-o", str(out_json), str(board)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=board.parent, errors="replace")
    except subprocess.TimeoutExpired:
        raise DrcError(f"DRC timed out after {timeout}s")
    if not out_json.exists():
        raise DrcError(f"DRC failed (rc={r.returncode}): {(r.stdout + r.stderr)[-600:]}")
    with open(out_json) as f:
        return json.load(f)


def errors(report, ignore=ENV_DEPENDENT):
    """Error-level violations (as kaebench counts them), unconnected items aside."""
    return [v for v in report.get("violations", []) if v.get("severity") == "error" and v.get("type") not in ignore]


def summary(report):
    errs = errors(report)
    by = {}
    for v in errs:
        by[v["type"]] = by.get(v["type"], 0) + 1
    return dict(errors=len(errs), unconnected=len(report.get("unconnected_items", [])), by_type=by)


def stage_board(src_board, project_board, dest_dir):
    """Copy `src_board` into `dest_dir` as board.kicad_pcb with the project files of
    `project_board` (its .kicad_pro and .kicad_dru) beside it; returns the staged path."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst = dest_dir / "board.kicad_pcb"
    shutil.copy2(src_board, dst)
    for ext in (".kicad_pro", ".kicad_dru"):
        src = Path(project_board).with_suffix(ext)
        tgt = dest_dir / f"board{ext}"
        if src.exists():
            shutil.copy2(src, tgt)
        elif tgt.exists():
            tgt.unlink()
    return dst
