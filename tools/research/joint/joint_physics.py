# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Routed physics and scores of kaebench `joint` runs, arm by arm, against the human layout.

For each task the brief is built once from the route task's input (the human placement), so
module ids pair across arms. Each arm's rebuilt routed board (attempt-N/score/routing/
board.kicad_pcb, what kaebench scored) is measured with the routed-copper estimator
(kae.route.critical_recheck.board_physics: module loop values and utilization u, rail
resistances) and the place terms (kae.physics.place_terms, straight-line, on the board's
poses). Per arm: cp1, legal, completion, unconnected, errors, time, the joint loop's
physics total (kae.joint.scorecard.physics_total: sum of min(u, 5), modules without a
value at 3) and the median per-module value ratio to the human board.

Usage:
  python tools/research/joint/joint_physics.py --tasks kae-work-v3/tasks --out DIR \\
      --arm human-fr=kae-work-v3/results/ab-human-fr/human-freerouting \\
      --arm joint=kae-work-v3/results/ab-joint-v2/kae-joint [--only id1,id2] [--attempt 0]
Writes DIR/<id>.json and DIR/summary.md. Never touches results directories.
"""
import argparse
import json
import os
import statistics
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")


def _arm(arm_dir, tid, attempt):
    """An arm's scored board: a joint run's rebuilt routing, else a route run's (e.g. the
    human placement routed by the bridge)."""
    a = Path(arm_dir) / "joint" / tid / f"attempt-{attempt}"
    if not a.exists():
        r = Path(arm_dir) / "route" / tid / f"attempt-{attempt}"
        aj = json.loads((r / "attempt.json").read_text()) if (r / "attempt.json").exists() else {}
        s = aj.get("score") or {}
        sc = dict(clean=s.get("clean"), legal=True, valid=s.get("valid"), completion=s.get("completion"),
                  unconnected=s.get("unconnected"), errors=s.get("errors"), errors_by_type=s.get("errors_by_type"),
                  runtime_s=aj.get("runtime_s"), wl_ratio=s.get("wl_ratio"))
        p = r / "score" / "board.kicad_pcb"
        return (str(p) if p.exists() else None), sc
    aj = json.loads((a / "attempt.json").read_text()) if (a / "attempt.json").exists() else {}
    s = aj.get("score") or {}
    sc = dict(clean=s.get("clean"), legal=s.get("legal"), valid=s.get("valid"), completion=s.get("completion"),
              unconnected=s.get("unconnected"), errors=s.get("errors"), errors_by_type=s.get("errors_by_type"),
              runtime_s=aj.get("runtime_s"), hpwl_ratio=s.get("hpwl_ratio"), wl_ratio=s.get("wl_ratio"))
    p = a / "score" / "routing" / "board.kicad_pcb"
    return (str(p) if p.exists() else None), sc


def measure(path, brief, terms):
    from kae.board.kicad_file import load
    from kae.joint.scorecard import physics_total
    from kae.route.critical_recheck import board_physics
    b = load(path)
    ph = board_physics(b, brief=brief, fills="kicad", terms=terms)
    mods = {k: v for k, v in ph.items() if not k.startswith("_") and isinstance(v, dict)}
    us = {k: v.get("u") for k, v in mods.items()}
    rails = [x for loads in (ph.get("_rails") or {}).values() if isinstance(loads, dict)
             for x in loads.values() if isinstance(x, (int, float))]
    pt = None
    if terms is not None:
        try:
            pt = float(terms.total({fp.uuid: (fp.x, fp.y, fp.rot, fp.side) for fp in b.footprints}))
        except Exception:  # noqa: BLE001
            pt = None
    return dict(physics_total=round(physics_total(us), 4), modules={k: dict(kind=v.get("kind"), value=v.get("value"),
                                                                             u=v.get("u")) for k, v in mods.items()},
                worst_rail_mohm=round(max(rails), 3) if rails else None, place_terms=pt)


def one(tid, tasks, arms, attempt, out):
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.place.stubs import make_terms
    t0 = time.time()
    ref_path = Path(tasks) / tid / "reference" / "board.kicad_pcb"
    inp = load(Path(tasks) / tid / "route" / "input" / "board.kicad_pcb")
    brief = build(inp)
    try:
        terms, _ = make_terms(inp, brief)
    except Exception:  # noqa: BLE001
        terms = None
    rec = dict(id=tid, arms={})
    boards = dict(human=(str(ref_path), dict(clean=True, legal=True, completion=1.0, unconnected=0, errors=0)))
    boards.update({n: _arm(d, tid, attempt) for n, d in arms.items()})
    for name, (path, sc) in boards.items():
        if path is None:
            rec["arms"][name] = dict(score=sc, missing=True)
            continue
        try:
            rec["arms"][name] = dict(score=sc, **measure(path, brief, terms))
        except Exception as e:  # noqa: BLE001
            rec["arms"][name] = dict(score=sc, error=f"{type(e).__name__}: {e}")
    rec["wall_s"] = round(time.time() - t0, 1)
    (Path(out) / f"{tid}.json").write_text(json.dumps(rec, indent=1, default=str))
    return rec


def summary(recs, names):
    rows = ["| arm | boards | cp1 | legal | completion | unconnected | errors | physics Σu | vs human (median module ratio) | worst rail mΩ (median) | place terms | time s |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in names:
        got = [r["arms"][n] for r in recs if n in r["arms"] and not r["arms"][n].get("missing")]
        if not got:
            continue
        sc = [g["score"] for g in got]

        def mean(xs):
            xs = [x for x in xs if x is not None]
            return round(sum(xs) / len(xs), 3) if xs else None
        ratios = []
        for r in recs:
            a, h = r["arms"].get(n) or {}, r["arms"].get("human") or {}
            for k, v in (a.get("modules") or {}).items():
                hv = ((h.get("modules") or {}).get(k) or {}).get("value")
                if v.get("value") and hv:
                    ratios.append(v["value"] / hv)
        rails = [g.get("worst_rail_mohm") for g in got if g.get("worst_rail_mohm") is not None]
        rows.append("| " + " | ".join(str(x) for x in (
            n, len(got), mean([1.0 if s.get("clean") else 0.0 for s in sc]), mean([1.0 if s.get("legal") else 0.0 for s in sc]),
            mean([s.get("completion") for s in sc]), sum(s.get("unconnected") or 0 for s in sc),
            sum(s.get("errors") or 0 for s in sc), mean([g.get("physics_total") for g in got]),
            round(statistics.median(ratios), 3) if ratios else None,
            round(statistics.median(rails), 2) if rails else None, mean([g.get("place_terms") for g in got]),
            mean([s.get("runtime_s") for s in sc]))) + " |")
    per = ["", "| task | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for r in recs:
        cells = []
        for n in names:
            a = r["arms"].get(n) or {}
            s = a.get("score") or {}
            cells.append("—" if a.get("missing") else
                         f"{'C' if s.get('clean') else ''}{'' if s.get('legal', True) else 'IL'} u{s.get('unconnected')} "
                         f"e{s.get('errors')} Σu {a.get('physics_total')}")
        per.append(f"| {r['id'][:40]} | " + " | ".join(cells) + " |")
    return "\n".join(rows + per) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--arm", action="append", default=[], help="NAME=RESULTS/<run>/<adapter>")
    ap.add_argument("--only")
    ap.add_argument("--attempt", type=int, default=0)
    a = ap.parse_args(argv)
    arms = dict(x.split("=", 1) for x in a.arm)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ids = a.only.split(",") if a.only else sorted({p.name for d in arms.values() for k in ("joint", "route")
                                                   if (Path(d) / k).exists() for p in (Path(d) / k).iterdir()})
    recs = [one(t, a.tasks, arms, a.attempt, out) for t in ids]
    md = summary(recs, ["human"] + list(arms))
    (out / "summary.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
