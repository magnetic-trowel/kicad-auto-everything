# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI placement sweep over a split, with legality, runtime, physics and order rules vs the
human placement aggregated into one JSON and one Markdown file.

    python tools/research/place/csweep.py run --snap SNAP --tasks kae-work-v2/tasks --split C \\
        --time 600 -j 24 --workers 2 --out kae-work-v2/csweep/v7 [--ids a,b] [-- extra kae args]
    python tools/research/place/csweep.py summary --snap SNAP --tasks kae-work-v2/tasks --out kae-work-v2/csweep/v7

`run` places every qualified board of the split with `python -m kae.cli place` from the frozen
snapshot SNAP (PYTHONPATH=SNAP, NUMBA_CACHE_DIR=SNAP/.numba_cache, KAE_WORKERS=--workers),
`-j` boards at a time, and then writes the summary. Warm the numba cache once before (outside
any sandbox, at the snapshot's final path):

    env PYTHONPATH=$SNAP NUMBA_CACHE_DIR=$SNAP/.numba_cache $PY -m kae.cli place \\
        kae/tests/data/board/fixture.kicad_pcb /tmp/warm.kicad_pcb --time 40

Per board it keeps OUT/<id>.json (kae's report, the last stdout line), OUT/<id>.log (stderr),
OUT/<id>.time (wall seconds) and OUT/<id>/board.kicad_pcb (git-ignored work area: never
commit boards). The summary (OUT/summary.json, OUT/summary.md) counts boards whose staged
footprints carry Edge.Cuts (outline_incomplete) and boards with no movable part separately
(any task with at least one movable part counts) and lists for every illegal board
why: the exact check's findings by type, grid violators left after escalation, the closed
loop's diagnosis (no room / side full / crowded), KiCad's last DRC verdict, timeouts and
errors. Physics and order rules are compared with the human placement (reference poses) under
the snapshot's own brief and place terms. The tool imports kae only from the snapshot.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def board_ids(tasks, split, ids=None):
    out = []
    for p in sorted(Path(tasks).glob("*/task.json")):
        t = json.loads(p.read_text())
        if t.get("split") == split and t.get("qualified", True):
            out.append(t["id"])
    if ids:
        want = set(ids)
        out = [i for i in out if i in want]
    return out


def run_one(args, tid, extra):
    out = Path(args.out)
    (out / tid).mkdir(parents=True, exist_ok=True)
    snap = str(Path(args.snap).resolve())
    env = dict(os.environ, PYTHONPATH=snap, NUMBA_CACHE_DIR=str(Path(snap) / ".numba_cache"),
               KAE_WORKERS=str(args.workers))
    cmd = [args.python, "-m", "kae.cli", "place", str(Path(args.tasks) / tid / "place" / "input" / "board.kicad_pcb"),
           str(out / tid / "board.kicad_pcb"), "--time", str(args.time), "--writer", "sexpr",
           "--workers", str(args.workers)] + list(extra)
    t0 = time.monotonic()
    with open(out / f"{tid}.json", "w") as fo, open(out / f"{tid}.log", "w") as fe:
        try:
            rc = subprocess.run(cmd, stdout=fo, stderr=fe, env=env, timeout=args.time * 1.5 + 120).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    (out / f"{tid}.time").write_text(f"{time.monotonic() - t0:.1f}\n")
    return tid, rc


def warm(args):
    """Compile (or load) every numba kernel into SNAP/.numba_cache once, before the sweep:
    the place-term kernels and a fixture placement (annealing engine, greedy legalizer)."""
    snap = str(Path(args.snap).resolve())
    env = dict(os.environ, PYTHONPATH=snap, NUMBA_CACHE_DIR=str(Path(snap) / ".numba_cache"), KAE_WORKERS="1")
    fixture = Path(__file__).resolve().parents[3] / "kae" / "tests" / "data" / "board" / "fixture.kicad_pcb"
    out = Path(args.out) / "_warm"
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    subprocess.run([args.python, "-c", "from kae.physics import jit; jit.warm(jit.nb())"], env=env, check=False)
    subprocess.run([args.python, "-m", "kae.cli", "place", str(fixture), str(out / "board.kicad_pcb"), "--time", "40",
                    "--writer", "sexpr"], env=env, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"numba warm-up {time.monotonic() - t0:.1f}s", flush=True)


def cmd_run(args, extra):
    if not args.no_warm:
        warm(args)
    ids = board_ids(args.tasks, args.split, args.ids.split(",") if args.ids else None)
    print(f"{len(ids)} boards of split {args.split}, {args.j} at a time, {args.time} s each", flush=True)
    rcs = {}
    with ThreadPoolExecutor(max_workers=args.j) as ex:
        for tid, rc in ex.map(lambda t: run_one(args, t, extra), ids):
            rcs[tid] = rc
            print(f"{tid} rc={rc}", flush=True)
    (Path(args.out) / "rc.json").write_text(json.dumps(rcs, indent=1))
    cmd_summary(args)


def _report(out, tid):
    p = Path(out) / f"{tid}.json"
    if not p.exists():
        return None
    for ln in reversed(p.read_text(errors="replace").splitlines()):
        if ln.startswith("{"):
            try:
                return json.loads(ln)
            except ValueError:
                return None
    return None


def _human(snap, tasks, tid):
    """Human placement under the snapshot's brief and terms: physics scorecard and order
    rules broken (None when the snapshot cannot score it)."""
    sys.path.insert(0, str(Path(snap).resolve()))
    from kae.board.kicad_file import load
    from kae.place import clusters
    from kae.place.anneal import Annealer
    from kae.place.pipeline import _net_kinds, physics_summary
    from kae.place.problem import Problem
    from kae.place.state import State
    from kae.place.stubs import make_brief, make_terms
    base = load(Path(tasks) / tid / "place" / "input" / "board.kicad_pcb")
    ref = load(Path(tasks) / tid / "reference" / "board.kicad_pcb")
    brief, _ = make_brief(base)
    bu = ref.by_uuid()
    poses = {f.uuid: (bu.get(f.uuid, f).x, bu.get(f.uuid, f).y, bu.get(f.uuid, f).rot, bu.get(f.uuid, f).side)
             for f in base.footprints}
    out = {}
    if brief.get("structures"):
        terms, _ = make_terms(base, brief, barrier=0.0)
        sc = physics_summary(terms, poses, breakdown=False)
        out["scorecard"] = sc
    P = Problem.build(base, net_kinds=_net_kinds(brief))
    rules = clusters.protection_order(P, brief)
    if rules:
        st = State(P)
        for q in P.parts:
            if q.movable:
                f = bu.get(q.uuid)
                if f is None:
                    continue
                X, Y = P.grid_of(f.x, f.y)
                rots = [r.rot for r in q.rots]
                k = min(range(len(rots)), key=lambda kk: min(abs(rots[kk] - f.rot) % 360, 360 - abs(rots[kk] - f.rot) % 360))
                st.X[q.i], st.Y[q.i], st.K[q.i] = X, Y, k
        out["order"] = dict(rules=len(rules), violated=Annealer(P, st, terms=None, w_cong=0.0, order=rules).order_violations())
    return out


def cmd_summary(args):
    out = Path(args.out)
    ids = sorted(p.stem for p in out.glob("*.json") if p.stem not in ("summary", "rc") and not p.stem.startswith("_"))
    rcs = json.loads((out / "rc.json").read_text()) if (out / "rc.json").exists() else {}
    rows = []
    for tid in ids:
        r = _report(out, tid)
        wall = float((out / f"{tid}.time").read_text()) if (out / f"{tid}.time").exists() else None
        row = dict(id=tid, rc=rcs.get(tid), wall_s=wall)
        if r is None:
            tail = (out / f"{tid}.log").read_text(errors="replace").splitlines()[-3:] if (out / f"{tid}.log").exists() else []
            row.update(legal=False, reason="no report (crash or timeout)", log_tail=tail)
            rows.append(row)
            continue
        a = r.get("anneal") or {}
        sc = r.get("scorecard") or {}
        esc = (r.get("legalize_seed_escalation") or []) + (r.get("legalize_escalation") or [])
        exact = collections.Counter(e.get("type") for e in r.get("exact") or [])
        row.update(legal=bool(r.get("legal")), kicad_verified=r.get("kicad_verified"),
                   legal_grid=r.get("legal_grid"), exact=dict(exact),
                   outline_incomplete=r.get("outline_incomplete"), parts=(r.get("problem") or {}).get("movable"),
                   seconds=r.get("seconds"), budget_s=r.get("budget_s"), stages=r.get("stages"),
                   moves=a.get("moves"), planned=a.get("planned_moves"), moves_per_s=a.get("moves_per_s"),
                   engine=a.get("engine"), schedule=a.get("schedule"), hpwl=r.get("hpwl"),
                   hpwl_seed=(r.get("seed") or {}).get("hpwl"),
                   physics=dict(total_linear=sc.get("total_linear"), over_budget=sc.get("over_budget"),
                                structures=sc.get("structures")),
                   order=r.get("protection_order"), escalation=[(e.get("step"), e.get("end_violators")) for e in esc],
                   violations=(r.get("legalize_final") or r.get("legalize") or {}).get("violations"))
        if not row["legal"]:
            why = []
            if r.get("outline_incomplete"):
                why.append(f"outline_incomplete {r['outline_incomplete']}")
            if not r.get("legal_grid"):
                why.append(f"grid violators left {list((row['violations'] or {}).items())[:4]}")
            if exact:
                why.append(f"exact {dict(exact)}")
            diag = (r.get("closed_loop") or {}).get("diagnosis") or {}
            if diag:
                why.append("diagnosis " + "; ".join(d.get("detail", "") for d in list(diag.values())[:4]))
            kd = [d for d in (r.get("kicad_drc") or []) if isinstance(d, dict) and "errors" in d]
            if kd and kd[-1]["errors"]:
                why.append(f"KiCad DRC {kd[-1].get('by_type')}")
            row["reason"] = "; ".join(why) or "unknown"
        if not args.no_human:
            try:
                row["human"] = _human(args.snap, args.tasks, tid)
            except Exception as e:      # the comparison is extra; never lose the sweep over it
                row["human"] = dict(error=f"{type(e).__name__}: {e}")
        rows.append(row)
    # a task with nothing to move is not a placement problem (all footprints locked): held out
    counted = [x for x in rows if not x.get("outline_incomplete") and x.get("parts") != 0]
    legal = [x for x in counted if x.get("legal")]
    walls = sorted(x["wall_s"] for x in rows if x.get("wall_s") is not None)
    phys = [(x["physics"]["total_linear"], x["human"]["scorecard"]["total_linear"],
             x["physics"]["over_budget"], x["human"]["scorecard"]["over_budget"])
            for x in counted if (x.get("physics") or {}).get("total_linear") is not None
            and ((x.get("human") or {}).get("scorecard") or {}).get("total_linear") is not None]
    orders = [((x.get("order") or {}).get("violated") or 0, (x["human"].get("order") or {}).get("violated") or 0,
               (x.get("order") or {}).get("rules") or 0)
              for x in counted if (x.get("order") or {}).get("rules") and isinstance(x.get("human"), dict)]
    summ = dict(
        boards=len(rows), counted=len(counted), outline_incomplete=[x["id"] for x in rows if x.get("outline_incomplete")],
        no_movable=[x["id"] for x in rows if x.get("parts") == 0 and not x.get("outline_incomplete")],
        legal=len(legal), legal_rate=round(len(legal) / max(1, len(counted)), 4),
        legal_unverified=[x["id"] for x in legal if x.get("kicad_verified") is False],
        illegal=[dict(id=x["id"], reason=x.get("reason")) for x in counted if not x.get("legal")],
        wall_s=dict(median=statistics.median(walls) if walls else None, max=walls[-1] if walls else None,
                    over_budget=[x["id"] for x in rows if x.get("wall_s") and x["wall_s"] > args.time]),
        anneal_full_schedule=sum(1 for x in rows if x.get("moves") and x.get("planned") and x["moves"] >= x["planned"]),
        anneal_cooled_on_budget=sum(1 for x in rows if x.get("schedule") == "budget"),
        physics=dict(boards=len(phys), ours_linear=round(sum(p[0] for p in phys), 2),
                     human_linear=round(sum(p[1] for p in phys), 2), ours_over=sum(p[2] for p in phys),
                     human_over=sum(p[3] for p in phys), ours_better=sum(1 for p in phys if p[0] < p[1] - 1e-9),
                     human_better=sum(1 for p in phys if p[1] < p[0] - 1e-9)),
        order=dict(boards=len(orders), rules=sum(o[2] for o in orders), ours_violated=sum(o[0] for o in orders),
                   human_violated=sum(o[1] for o in orders)),
    )
    (out / "summary.json").write_text(json.dumps(dict(summary=summ, boards=rows), indent=1, default=str))
    md = [f"# Placement sweep: {out.name}", "",
          f"- boards {summ['boards']}, counted {summ['counted']} (held out: outline_incomplete "
          f"{len(summ['outline_incomplete'])}, no movable parts {len(summ['no_movable'])})",
          f"- **legal {summ['legal']}/{summ['counted']} = {summ['legal_rate']:.1%}**"
          + (f" ({len(summ['legal_unverified'])} without a KiCad verdict: {', '.join(summ['legal_unverified'])})"
             if summ['legal_unverified'] else ""),
          f"- wall median {summ['wall_s']['median']} s, max {summ['wall_s']['max']} s, over {args.time} s: "
          f"{len(summ['wall_s']['over_budget'])}",
          f"- annealer: all planned moves on {summ['anneal_full_schedule']} boards, cooled on its time budget on "
          f"{summ['anneal_cooled_on_budget']} (planned moves grow when the engine is fast)",
          f"- physics (linear sum, {summ['physics']['boards']} boards with place terms): ours {summ['physics']['ours_linear']} "
          f"vs human {summ['physics']['human_linear']}; over budget {summ['physics']['ours_over']} vs "
          f"{summ['physics']['human_over']}; ours better on {summ['physics']['ours_better']}, human on "
          f"{summ['physics']['human_better']}",
          f"- protection order ({summ['order']['boards']} boards, {summ['order']['rules']} rules): broken ours "
          f"{summ['order']['ours_violated']} vs human {summ['order']['human_violated']}", "",
          "## Illegal boards", ""]
    md += [f"- {x['id']}: {x['reason']}" for x in summ["illegal"]] or ["- none"]
    md += ["", "## Boards", "", "| board | parts | legal | wall s | moves/planned | HPWL seed -> final | physics ours/human | order ours/human |",
           "|---|---|---|---|---|---|---|---|"]
    for x in rows:
        h = x.get("human") or {}
        hs = (h.get("scorecard") or {}) if isinstance(h, dict) else {}
        md.append(f"| {x['id'][:48]} | {x.get('parts')} | {'yes' if x.get('legal') else 'NO'} | {x.get('wall_s')} | "
                  f"{x.get('moves')}/{x.get('planned')} | {x.get('hpwl_seed')} -> {x.get('hpwl')} | "
                  f"{(x.get('physics') or {}).get('total_linear')}/{hs.get('total_linear')} | "
                  f"{(x.get('order') or {}).get('violated')}/{(h.get('order') or {}).get('violated') if isinstance(h, dict) else None} |")
    (out / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:12]))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        k = argv.index("--")
        argv, extra = argv[:k], argv[k + 1:]
    ap = argparse.ArgumentParser(prog="csweep")
    ap.add_argument("mode", choices=("run", "summary"))
    ap.add_argument("--snap", required=True)
    ap.add_argument("--tasks", default="kae-work-v2/tasks")
    ap.add_argument("--split", default="C")
    ap.add_argument("--ids")
    ap.add_argument("--time", type=float, default=600.0)
    ap.add_argument("-j", type=int, default=8)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out", required=True)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--no-human", action="store_true")
    ap.add_argument("--no-warm", action="store_true")
    args = ap.parse_args(argv)
    if args.mode == "run":
        cmd_run(args, extra)
    else:
        cmd_summary(args)


if __name__ == "__main__":
    main()
