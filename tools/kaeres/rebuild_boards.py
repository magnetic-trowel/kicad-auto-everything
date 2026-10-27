# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rebuild runs' scored boards without scoring them: what kaebench scored, for evaluators added later.

Runs in a harness venv (kaebench importable), the one whose commit ran the runs, so the rebuild is
the scorer's own. From a corpus board folder it rebuilds the route task's reference and input the
way `prepare` does (convert, rules, strip-routing; no DRC), then each run's output is transplanted
onto the input with the reference rules (kaebench.score._rebuild, as score_route_task does).

  python rebuild_boards.py --board-dir CORPUS/boards/<id> --work DIR --run NAME=OUTPUT.kicad_pcb[.gz] ... --out MANIFEST.json
Writes MANIFEST: {"input": path, "reference": path, "board_sha256": ..., "task_spec": N,
"runs": {NAME: {"board": path} | {"error": ...}}}.
"""
import argparse
import gzip
import json
import shutil
import sys
import traceback
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--run", action="append", default=[], metavar="NAME=OUTPUT")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    from kaebench import prepare, score, tools
    from kaebench.boardfiles import STEM, board_path, install_rules
    from kaebench.cli import _local_boards
    bd = Path(a.board_dir)
    work = Path(a.work)
    (entry, fetched), = _local_boards(bd.parent, "board.kicad_pcb", [bd.name])
    ref = work / "reference"
    inp = work / "route" / "input"
    ref.mkdir(parents=True)
    inp.mkdir(parents=True)
    for key, ext in (("kicad_pro", ".kicad_pro"), ("kicad_dru", ".kicad_dru")):  # as prepare_board
        if fetched.get(key):
            shutil.copy2(fetched[key], ref / f"{STEM}{ext}")
    tools.run_ops("convert", fetched["kicad_pcb"], board_path(ref))
    install_rules(ref, inp)
    tools.run_ops("strip-routing", board_path(ref), board_path(inp))
    man = dict(input=str(board_path(inp)), reference=str(board_path(ref)), board_sha256=fetched.get("pcb_sha256"),
               task_spec=prepare.TASK_SPEC, runs={})
    for spec in a.run:
        name, _, out = spec.partition("=")
        try:
            src = work / "outputs" / name / "board.kicad_pcb"
            src.parent.mkdir(parents=True)
            if out.endswith(".gz"):
                with gzip.open(out, "rb") as fi, open(src, "wb") as fo:
                    shutil.copyfileobj(fi, fo)
            else:
                shutil.copy2(out, src)
            staged, tr = score._rebuild("transplant-routing", src, board_path(inp), ref, work / "scored" / name,
                                        board_path(ref))
            man["runs"][name] = dict(board=str(staged)) if tr.get("loadable") else dict(error="output not loadable")
        except Exception as e:  # noqa: BLE001
            man["runs"][name] = dict(error=f"{type(e).__name__}: {e}"[:500], traceback=traceback.format_exc()[-2000:])
    Path(a.out).write_text(json.dumps(man, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
