# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rebuild runs' scored boards without scoring them: what kaebench scored, for evaluators added later.

Runs in a harness venv (kaebench importable), the one whose commit ran the runs, so the rebuild is
the scorer's own. From a corpus board folder it rebuilds the route task's reference and input the
way `prepare` does (convert, rules, strip-routing; no DRC), then each run's output is transplanted
onto the input with the reference rules (kaebench.score._rebuild, as score_route_task does). A run
named with --joint placed the parts too: its poses go onto the input first, then its copper onto that
placement (as score_joint_task does; the place input differs from the route input only in which parts
are locked and where unplaced parts wait, and every part takes the output's pose).

The tool is newer than some venvs it runs in: a harness from before score v10 has no `_rebuild(flags=...)`,
and its scorer transplanted without `--zones`, so that is how those runs are rebuilt too. If no run
could be rebuilt the tool exits 2, so a job cannot read an empty manifest as "nothing to do".

  python rebuild_boards.py --board-dir CORPUS/boards/<id> --work DIR --run NAME=OUTPUT.kicad_pcb[.gz] ... [--joint NAME ...]
                           --out MANIFEST.json
Writes MANIFEST: {"input": path, "reference": path, "board_sha256": ..., "task_spec": N,
"runs": {NAME: {"board": path} | {"error": ...}}}.
"""
import argparse
import gzip
import inspect
import json
import shutil
import sys
import traceback
from pathlib import Path


def rebuild_call(score, *args):
    """score._rebuild as this harness's scorer called it: harnesses from before score v10 take no
    flags (their scorer did not pass --zones either)."""
    if "flags" in inspect.signature(score._rebuild).parameters:
        return score._rebuild(*args, flags=("--zones",))
    return score._rebuild(*args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--run", action="append", default=[], metavar="NAME=OUTPUT")
    ap.add_argument("--joint", action="append", default=[], metavar="NAME", help="a run of a joint task")
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
    if hasattr(prepare, "restrict_layers"):  # as prepare_board, from task spec 11 on (older harnesses run this too)
        prepare.restrict_layers(ref)
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
            onto = board_path(inp)
            if name in a.joint:
                onto, tp = rebuild_call(score, "transplant-placement", src, board_path(inp), ref, work / "placed" / name,
                                        board_path(ref))
                if not tp.get("loadable"):
                    man["runs"][name] = dict(error="placement not loadable")
                    continue
            staged, tr = rebuild_call(score, "transplant-routing", src, onto, ref, work / "scored" / name,
                                      board_path(ref))
            man["runs"][name] = dict(board=str(staged)) if tr.get("loadable") else dict(error="output not loadable")
        except Exception as e:  # noqa: BLE001
            man["runs"][name] = dict(error=f"{type(e).__name__}: {e}"[:500], traceback=traceback.format_exc()[-2000:])
    Path(a.out).write_text(json.dumps(man, indent=1))
    if a.run and not any(r.get("board") for r in man["runs"].values()):
        for name, r in man["runs"].items():
            print(f"{name}: {r.get('error')}", file=sys.stderr)
        print(f"rebuild_boards: none of {len(a.run)} runs could be rebuilt", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
