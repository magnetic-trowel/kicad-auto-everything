# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics under each board's intent for every layout of a kaeres experiment (and the human layout).

    python score_experiment.py queue EXPERIMENT --intents DIR --out DIR [--boards @FILE] > batch.txt
        one eval_intent.sh command per (board, layout) not yet evaluated, for `kaeq submit --batch`;
        each line carries its own --cpus/--mem (sized from the board's footprints)
    python score_experiment.py table EXPERIMENT --intents DIR --out DIR -o table.csv
        per board, each layout's key under its intent, on the terms every layout of that board computed

DIR/intents holds <board>.intent.json and <board>.operating.json (intent_from_spec.py). Layouts are the
runs' output boards (output.kicad_pcb.gz); the board's own .kicad_pro/.kicad_dru come from the corpus.
"""
import argparse
import csv
import glob
import gzip
import json
import os
import sys

STORE = os.path.expanduser("~/kae-baselines")
CORPUS = os.path.expanduser("~/kae-boards/boards")
HERE = os.path.dirname(os.path.abspath(__file__))


def runs(exp, boards=None):
    """(board, tag, board file, method name) for the human layout and every ok attempt-0 run of the
    experiment's methods on its boards, whichever experiment made the run (kaeres reuses runs)."""
    e = json.load(open(f"{STORE}/experiments/{exp}/experiment.json"))
    mids = {m["id"] for m in e["methods"]}
    eb = set(open(f"{STORE}/experiments/{exp}/boards.txt").read().split())
    want = (set(boards) & eb) if boards else eb
    seen = set()
    for p in sorted(glob.glob(f"{STORE}/boards/*/runs/*/run.json")):
        try:
            r = json.load(open(p))
        except (OSError, ValueError):
            continue
        b = r.get("board")
        if r.get("method_id") not in mids or b not in want or r.get("attempt", 0) != 0:
            continue
        out = os.path.join(os.path.dirname(p), "output.kicad_pcb.gz")
        if r.get("status") == "ok" and os.path.exists(out):
            yield b, r["run"], out, r.get("method_name")
        if b not in seen:
            seen.add(b)
            yield b, "human", f"{CORPUS}/{b}/board.kicad_pcb", "human"


def footprints(b):
    try:
        return json.load(open(f"{STORE}/boards/{b}/board.json")).get("footprints") or 50
    except (OSError, ValueError):
        return 50


def cmd_queue(a):
    py = a.py
    n = 0
    for b, tag, path, _ in runs(a.experiment, a.board_list):
        it, op = f"{a.intents}/{b}.intent.json", f"{a.intents}/{b}.operating.json"
        if not (os.path.exists(it) and os.path.exists(op)):
            continue
        od = f"{a.out}/{b}"
        if os.path.exists(f"{od}/{tag}.status.json"):
            continue
        fp = footprints(b)
        mem = min(60, int(3 + 0.16 * fp))
        hours = 1 if fp <= 80 else (3 if fp <= 250 else 6)
        print(json.dumps(dict(cmd=f"env KAE_PY={py} KAE_RULES_FROM={CORPUS}/{b}/board.kicad_pcb {HERE}/eval_intent.sh "
                                  f"{path} {op} {it} {od} {tag}",
                              name=f"phys:{b[:40]}:{tag[:24]}", cpus=4, mem=f"{mem}G", timeout=f"{hours}h")))
        n += 1
    print(f"{n} evaluations", file=sys.stderr)


def cmd_table(a):
    sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "kae", "src"))
    from kae.intent import objective as OB
    by = {}
    for b, tag, _, m in runs(a.experiment, a.board_list):
        p = f"{a.out}/{b}/{tag}.status.json"
        if os.path.exists(p):
            by.setdefault(b, []).append((tag, m, json.load(open(p))))
    rows = []
    for b, lst in sorted(by.items()):
        sts = [s for _, _, s in lst]
        common = OB.common_terms(sts)
        for tag, m, s in lst:
            k = OB.key(s, common)
            rows.append(dict(board=b, method=m, run=tag, hard=k[0], cost_mW_eq=round(k[1], 4),
                             terms_compared=len(common), terms_incomplete=len(s.get("incomplete_terms") or []),
                             not_computed=";".join(s.get("not_computed") or [])))
    with open(a.o, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["board"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows, {len(by)} boards -> {a.o}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("queue", "table"):
        s = sub.add_parser(name)
        s.add_argument("experiment"), s.add_argument("--intents", required=True), s.add_argument("--out", required=True)
        s.add_argument("--boards"), s.add_argument("--py", default=sys.executable), s.add_argument("-o")
    a = ap.parse_args(argv)
    a.board_list = (open(a.boards[1:]).read().split() if a.boards and a.boards.startswith("@")
                    else (a.boards.split(",") if a.boards else None))
    {"queue": cmd_queue, "table": cmd_table}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
