# SPDX-FileCopyrightText: 2026 HaslamPCB contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Score stored haslamres runs with the class-independent width metric (haslam.route.width_human).

    width_human_corpus.py --experiment control-w48 [--methods 288a499c,85993b60] --out DIR [-j N]
    width_human_corpus.py --boards FILE --methods M1,M2 --out DIR      # any boards with stored runs

Writes DIR/rows.jsonl: one line per (board, method or "human", attempt, option set) with pooled shares per net subset
and the per-net rows (numerators and denominators, so any pooling can be redone). The human reference is the corpus
board (`<corpus>/boards/<id>/board.kicad_pcb`); the human floor is the same board measured against itself.
Run in the haslam venv with PYTHONPATH=<repo>/haslam/src; pure Python, no KiCad.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

RES = Path(os.environ.get("HASLAM_RESULTS", Path.home() / "haslam-baselines"))
CORPUS = Path(os.environ.get("HASLAM_CORPUS", Path.home() / "haslam-boards"))
# option sets: the default, a looser tolerance, a shorter pad-entry reach, no pour credit
OPTS = {"d": dict(tol=0.05, reach=1.0), "tol15": dict(tol=0.15, reach=1.0), "reach05": dict(tol=0.05, reach=0.5),
        "nopour": dict(tol=0.05, reach=1.0, pour=False)}


def _strip(res):
    rows = {n: dict(r) for n, r in res["rows"].items()}
    return dict(w_sig=res["w_sig"], n_ref=len(res["ref"]), pooled=res["pooled"], rows=rows,
                ref={n: {k: v for k, v in f.items()} for n, f in res["ref"].items()})


def one_board(board, methods, attempts):
    from haslam.route import width_human as W
    out = []
    human_path = CORPUS / "boards" / board / "board.kicad_pcb"
    if not human_path.exists():
        return [dict(board=board, error="no corpus board")]
    try:
        human = W._load(human_path, rules=True)      # net classes for share_neck
        ref0 = W.reference(human)
    except Exception as e:
        return [dict(board=board, error=f"human: {type(e).__name__}: {e}")]
    runs = RES / "boards" / board / "runs"
    jobs = [("human", 0, human_path)]
    for m in methods:
        for a in attempts:
            hits = sorted(runs.glob(f"*.{m[:8]}.a{a}/output.kicad_pcb.gz"))
            if hits:
                jobs.append((m, a, hits[0]))
            else:
                out.append(dict(board=board, method=m, attempt=a, error="no output"))
    for who, a, path in jobs:
        for oname, o in OPTS.items():
            t = time.time()
            try:
                res = W.measure(path, human_path, o, human=human, ref=ref0)
                out.append(dict(board=board, method=who, attempt=a, opts=oname, secs=round(time.time() - t, 2),
                                run=str(path.parent.name) if who != "human" else "human", **_strip(res)))
            except Exception as e:
                out.append(dict(board=board, method=who, attempt=a, opts=oname,
                                error=f"{type(e).__name__}: {e}", tb=traceback.format_exc()[-800:]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--experiment")
    ap.add_argument("--boards")
    ap.add_argument("--methods", default="288a499c,85993b60")
    ap.add_argument("--attempts", default="0,1")
    ap.add_argument("--out", required=True)
    ap.add_argument("-j", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args(argv)
    if a.experiment:
        boards = (RES / "experiments" / a.experiment / "boards.txt").read_text().split()
    else:
        boards = [b for b in Path(a.boards).read_text().split() if not b.startswith("#")]
    methods = a.methods.split(",")
    attempts = [int(x) for x in a.attempts.split(",")]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out / "rows.jsonl", "w") as f, ProcessPoolExecutor(a.j) as ex:
        futs = {ex.submit(one_board, b, methods, attempts): b for b in boards}
        for fu in as_completed(futs):
            try:
                rows = fu.result()
            except Exception as e:
                rows = [dict(board=futs[fu], error=f"worker: {type(e).__name__}: {e}")]
            for r in rows:
                f.write(json.dumps(r) + "\n")
            f.flush()
            n += 1
            print(f"{n}/{len(boards)} {futs[fu]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
