# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Data generator for the learned value model: runs lv_jc.jc_log (jc with probes, no
steering) on place-task boards and appends checkpoint/outcome rows to JSONL.

    python lv_gen.py --suite kae-work/ab33.txt --budget 300 --phys-w 2 --seed 100 \
        --out kae-work/learnv/data/phys.jsonl -j 2

Extractions are cached in kae-work/learnv/extract/. No board is written (data only).
"""
import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path("/home/user/kicad-auto-everything")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools/research/pnr"))
sys.path.insert(0, str(HERE))


def extract(tid):
    out = ROOT / "kae-work/learnv/extract" / f"{tid}.json"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        import run as RUN
        RUN.kicad("extract", ROOT / "kae-work/tasks" / tid / "place/input/board.kicad_pcb", out)
    return out


def one(args):
    tid, budget, phys_w, seed, out, logdir = args
    import lv_jc
    from world import World
    data = json.loads(extract(tid).read_text())
    w = World(data, g=0.1)
    lf = open(Path(logdir) / f"{tid}-{phys_w}-{seed}.log", "w")
    lv_jc.jc_log(w, seed=seed, budget=budget, log=lambda m: (lf.write(m + "\n"), lf.flush()),
                 phys_w=phys_w, log_path=out, tag="gen")
    return tid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True)
    ap.add_argument("--budget", type=float, default=300)
    ap.add_argument("--phys-w", type=float, default=2.0)
    ap.add_argument("--seed", type=int, default=100)
    ap.add_argument("--out", required=True)
    ap.add_argument("-j", type=int, default=1)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    ids = [l.strip() for l in open(a.suite) if l.strip() and not l.startswith("#")]
    if a.only:
        ids = [i for i in ids if i in a.only.split(",")]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for l in open(out):
            r = json.loads(l)
            if r.get("kind") == "done" and r["seed"] == a.seed:
                done.add(r["board"])
    ids = [i for i in ids if i not in done]
    for i in ids:  # extract serially (KiCad python)
        extract(i)
    logdir = out.parent / "logs"
    logdir.mkdir(exist_ok=True)
    jobs = [(i, a.budget, a.phys_w, a.seed, str(out), str(logdir)) for i in ids]
    # largest boards first so the pool ends evenly
    jobs.sort(key=lambda j: -(ROOT / "kae-work/learnv/extract" / f"{j[0]}.json").stat().st_size)
    with ProcessPoolExecutor(a.j) as ex:
        for tid in ex.map(one, jobs):
            print("done", tid, flush=True)


if __name__ == "__main__":
    main()
