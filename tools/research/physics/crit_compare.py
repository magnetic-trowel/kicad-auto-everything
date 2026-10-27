# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Module physics of routed boards side by side: the human reference and router arms
(e.g. bridge alone, critical routing then bridge) on the same route tasks, measured with
critical-net routing's routed-copper estimator (kae.route.critical_recheck.board_physics).

For each task: the brief is built once from the task input, so module ids pair across
boards; each board is refilled by KiCad's zone filler and read as a copper graph; per
module the routed value (commutation-cell and decoupling loop L in nH, crystal trace
capacitance x pulling in ppm, surge-path L ahead of the protector in nH) with its
allocation u, and per rail the copper resistance from the source to each load (mOhm).
A module whose loop has an open hop (unrouted copper) is measured on straight hops and
left out of the paired ratios. The DC passports and rb HF loop (suite_physics.py
--compare-to) are the independent check; this tool is the per-module view.

Writes <out>/<id>.json and <out>/summary.json, <out>/summary.md (median arm/human and
arm/arm ratios per module kind, wins and losses, rail resistance ratios). Never touches
scores or results directories.

Usage:
  python tools/research/physics/crit_compare.py --tasks kae-work-v2/tasks --out DIR \\
      --arm bridge=kae-work-v2/results/<run>/kae-fr --arm crit=kae-work-v2/results/<run>/kae-crit \\
      [--only id1,id2 | --suite FILE] [--attempt 0] [-j 4]
  python tools/research/physics/crit_compare.py --out DIR --aggregate-only
  python tools/research/physics/crit_compare.py --out DIR --retweak kae-work-v2/results/<run>/kae-crit
"""
import argparse
import json
import os
import statistics
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")


def arm_board(arm_dir, tid, attempt):
    a = Path(arm_dir) / "route" / tid / f"attempt-{attempt}"
    for p in (a / "score" / "board.kicad_pcb", a / "output" / "board.kicad_pcb"):
        if p.exists():
            sc = {}
            if (a / "attempt.json").exists():
                aj = json.loads((a / "attempt.json").read_text())
                s = aj.get("score") or {}
                sc = dict(status=aj.get("status"), completion=s.get("completion"), errors=s.get("errors"),
                          unconnected=s.get("unconnected"), valid=s.get("valid"))
            return str(p), sc
    return None, {}


def one(job):
    tid, tasks, arms, attempt, out = job
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.route.critical_recheck import board_physics
    rec = dict(id=tid, boards={})
    t0 = time.time()
    try:
        inp = load(Path(tasks) / tid / "route" / "input" / "board.kicad_pcb")
        brief = build(inp)
        boards = dict(human=(str(Path(tasks) / tid / "reference" / "board.kicad_pcb"), {}))
        for name, d in arms.items():
            boards[name] = arm_board(d, tid, attempt)
        for name, (path, sc) in boards.items():
            if path is None or not os.path.exists(path):
                rec["boards"][name] = dict(missing=True)
                continue
            t1 = time.time()
            try:
                ph = board_physics(path, brief=brief, fills="kicad")
                rec["boards"][name] = dict(path=path, score=sc, physics=ph, wall_s=round(time.time() - t1, 2))
            except Exception as e:  # noqa: BLE001
                rec["boards"][name] = dict(path=path, score=sc, error=f"{type(e).__name__}: {e}",
                                           trace=traceback.format_exc(limit=4))
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"
    rec["wall_s"] = round(time.time() - t0, 2)
    (Path(out) / f"{tid}.json").write_text(json.dumps(rec, indent=1))
    return rec


def _vals(b):
    """{module id: (kind, value, unit)} of closed modules on one board."""
    ph = (b or {}).get("physics") or {}
    out = {}
    for k, v in ph.items():
        if k.startswith("_") or v.get("value") is None or v.get("open_hops"):
            continue
        out[k] = (v["kind"], v["value"], v.get("unit"))
    return out


def _worst_rails(b):
    ph = (b or {}).get("physics") or {}
    out = {}
    for net, loads in (ph.get("_rails") or {}).items():
        vs = [x for x in loads.values() if x is not None]
        if vs and len(vs) == len(loads):
            out[net] = max(vs)
    return out


def _q(xs):
    if not xs:
        return None
    xs = sorted(xs)
    return dict(n=len(xs), median=round(statistics.median(xs), 3), p25=round(xs[len(xs) // 4], 3),
                p75=round(xs[(3 * len(xs)) // 4], 3), better=sum(x < 0.98 for x in xs), worse=sum(x > 1.02 for x in xs))


def aggregate(out):
    recs = [json.loads(p.read_text()) for p in sorted(Path(out).glob("*.json"))
            if p.name not in ("summary.json", "retweak.json")]
    recs = [r for r in recs if "boards" in r]
    names = []
    for r in recs:                     # arms in --arm order
        names += [n for n in r.get("boards", {}) if n != "human" and n not in names]
    pairs = [(n, "human") for n in names] + [(names[j], names[i]) for i in range(len(names))
                                             for j in range(i + 1, len(names))]
    S = dict(boards=len(recs), arms=names, pairs={})
    for a, b in pairs:
        by_kind, rails, boards = {}, [], 0
        for r in recs:
            A, B = r["boards"].get(a), r["boards"].get(b)
            if not A or not B or A.get("missing") or B.get("missing"):
                continue
            boards += 1
            va, vb = _vals(A), _vals(B)
            for k in set(va) & set(vb):
                kind, x, _ = va[k]
                y = vb[k][1]
                if y > 0:
                    by_kind.setdefault(kind, []).append(x / y)
            ra, rb_ = _worst_rails(A), _worst_rails(B)
            rails += [ra[n] / rb_[n] for n in set(ra) & set(rb_) if rb_[n] > 0]
        S["pairs"][f"{a}/{b}"] = dict(boards=boards, kinds={k: _q(v) for k, v in sorted(by_kind.items())},
                                      rail_r=_q(rails))
    comp = {}
    for n in names:
        cs = [((r["boards"].get(n) or {}).get("score") or {}).get("completion") for r in recs]
        cs = [c for c in cs if c is not None]
        comp[n] = dict(n=len(cs), mean_completion=round(sum(cs) / len(cs), 4) if cs else None,
                       complete=sum(c >= 1.0 for c in cs))
    S["completion"] = comp
    Path(out, "summary.json").write_text(json.dumps(S, indent=1))
    lines = [f"# Module physics: {', '.join(names)} vs human ({len(recs)} boards)", "",
             "Ratios of routed values (lower is better for every kind), per module present and closed on",
             "both boards; better/worse = ratio below 0.98 / above 1.02.", ""]
    for key, P in S["pairs"].items():
        lines += [f"## {key} ({P['boards']} boards)", "", "| kind | n | median | p25 | p75 | better | worse |",
                  "|---|---|---|---|---|---|---|"]
        for k, q in list(P["kinds"].items()) + [("rail R (worst load)", P["rail_r"])]:
            if q:
                lines.append(f"| {k} | {q['n']} | {q['median']} | {q['p25']} | {q['p75']} | {q['better']} | {q['worse']} |")
        lines.append("")
    lines += ["## Completion (from the scorer)", ""] + [f"- {n}: {c}" for n, c in comp.items()]
    Path(out, "summary.md").write_text("\n".join(lines) + "\n")
    return S


def retweak_summary(arm_dir, attempt=0):
    """The re-tweak rounds of a critical-routing run, from each attempt's report (the last
    JSON line of adapter.log): how often a module is flagged, how many rounds ran and were
    kept, and how much of the flagged modules' loss they recovered."""
    rows = []
    for log in sorted(Path(arm_dir).glob(f"route/*/attempt-{attempt}/adapter.log")):
        rep = None
        for ln in log.read_text(errors="replace").splitlines():
            if ln.startswith("{"):
                try:
                    rep = json.loads(ln)
                except ValueError:
                    pass
        rt = (rep or {}).get("retweak") or {}
        hist = rt.get("rounds") or []
        if not hist:
            rows.append(dict(id=log.parts[-3], ran=False, note=rt.get("error") or "no re-tweak report"))
            continue
        r0 = hist[0]
        flagged = r0.get("flagged") or []
        kept = [h for h in hist[1:] if h.get("kept")]
        last = kept[-1] if kept else r0
        rec = []
        for m in flagged:
            us, u0 = (r0.get("u") or {}).get(m, (None, None))
            u1 = (last.get("u") or {}).get(m, (None, None))[1]
            cs, c0 = (r0.get("cover") or {}).get(m, (None, None))
            c1 = (last.get("cover") or {}).get(m, (None, None))[1]
            frac = None
            if None not in (us, u0, u1) and u0 > us:
                frac = (u0 - u1) / (u0 - us)            # share of the u lost to the bridge won back
            elif None not in (cs, c0, c1) and cs > c0:
                frac = (c1 - c0) / (cs - c0)            # share of the plane cover won back
            rec.append(dict(module=m, u_stage=us, u_routed=u0, u_final=u1, cover_stage=cs, cover_routed=c0,
                            cover_final=c1, recovered=None if frac is None else round(frac, 3)))
        rows.append(dict(id=log.parts[-3], ran=True, flagged=len(flagged), rounds=len(hist) - 1, kept=len(kept),
                         errors0=r0.get("errors"), unconnected0=r0.get("unconnected"),
                         errors=(rt.get("final") or {}).get("errors"), unconnected=(rt.get("final") or {}).get("unconnected"),
                         modules=rec, history=[{k: h.get(k) for k in ("round", "ripped", "errors", "unconnected", "kept",
                                                                         "flagged", "note")} for h in hist]))
    ran = [r for r in rows if r["ran"]]
    rec = [m["recovered"] for r in ran for m in r["modules"] if m["recovered"] is not None]
    return dict(boards=len(rows), with_report=len(ran), flagged_boards=sum(r["flagged"] > 0 for r in ran),
                round1_ran=sum(r["rounds"] >= 1 for r in ran), round2_ran=sum(r["rounds"] >= 2 for r in ran),
                kept_any=sum(r["kept"] > 0 for r in ran),
                recovered=dict(n=len(rec), median=round(statistics.median(rec), 3) if rec else None,
                               full=sum(x >= 0.9 for x in rec), none=sum(x <= 0.0 for x in rec)),
                rows=rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tasks")
    ap.add_argument("--out", required=True)
    ap.add_argument("--arm", action="append", default=[], help="name=results/<run>/<adapter> (repeatable)")
    ap.add_argument("--only")
    ap.add_argument("--suite")
    ap.add_argument("--attempt", type=int, default=0)
    ap.add_argument("-j", type=int, default=1)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--aggregate-only", action="store_true")
    ap.add_argument("--retweak", metavar="RESULTS/<run>/<adapter>",
                    help="only summarize the re-tweak rounds of a critical-routing run into <out>/retweak.json")
    a = ap.parse_args(argv)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    if a.retweak:
        R = retweak_summary(a.retweak, a.attempt)
        Path(a.out, "retweak.json").write_text(json.dumps(R, indent=1))
        print(json.dumps({k: v for k, v in R.items() if k != "rows"}, indent=1))
        return 0
    if not a.aggregate_only:
        arms = dict(x.split("=", 1) for x in a.arm)
        if a.only:
            ids = [x for x in a.only.split(",") if x]
        elif a.suite:
            ids = [ln.strip() for ln in open(a.suite) if ln.strip() and not ln.startswith("#")]
        else:
            first = next(iter(arms.values()))
            ids = sorted(p.name for p in (Path(first) / "route").iterdir())
        jobs = [(t, a.tasks, arms, a.attempt, a.out) for t in ids
                if a.force or not (Path(a.out) / f"{t}.json").exists()]
        if a.j > 1:
            with ProcessPoolExecutor(a.j) as ex:
                for r in ex.map(one, jobs):
                    print(r["id"], r.get("error") or "ok", r["wall_s"], flush=True)
        else:
            for j in jobs:
                r = one(j)
                print(r["id"], r.get("error") or "ok", r["wall_s"], flush=True)
    S = aggregate(a.out)
    print(json.dumps(S["pairs"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
