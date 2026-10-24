# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics score of joint place-and-route runs, against the human board.

    KAE_KICAD_PYTHON=/usr/bin/python3 <kae-venv>/bin/python physics_score.py \\
        kae-work/results/RUN1 [kae-work/results/RUN2 ...] [--suite kae-work/ab33.txt] \\
        [--out kae-work/phys] [--md FILE] [--no-routed] [--timeout 600]

Needs the `kae` package (branch claude/vigilant-mayer-i91rrr, `pip install -e 'kae[fast]'`)
in the interpreter that runs this script; KiCad's Python (pcbnew) for zone refills.

Per board, once: the circuit brief of the human reference board (kae.circuit.brief.build,
cached in kae-work/phys-cache/<id>/brief.json) and the place terms built on it
(kae.physics.place_terms.Terms). Every board (the human reference and each run's
attempt-0 output) is then scored with that same brief and those same allocations:

- place: Terms.total(poses) (sum over structures of confidence * phi(u), phi with its
  over-budget barrier), Terms.total_by_kind, and a robust variant, the sum of utilizations
  capped at 5 (as the Scorecard caps routed u), overall and per kind;
- routed: kae.route.critical_recheck.board_physics on the board's real copper (zones
  refilled by KiCad), summarized as the Scorecard's physics_total (per module u capped at
  5, a module without a value at 3) plus the number of open hops (an unrouted connection
  inside a module is priced as a straight strip, so missing copper looks optimistic).

Results per (run, board) are cached by the output board's md5. Per run: a JSON with every
board's numbers in --out, and a markdown summary (geometric mean of method/human ratios,
boards worse than human, per-kind ratios and which kind carries the excess, coverage with
the reason for every board not scored).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import signal
import sys
import tempfile
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("KAE_KICAD_PYTHON", "/usr/bin/python3")

ROOT = Path("/home/user/kicad-auto-everything")
WORK = ROOT / "kae-work"
VERSION = "phys-1"           # harness numbers are re-read every time           # bump when the scoring here changes (invalidates the caches)
U_CAP = 5.0
EPS = 0.01                   # ratio floor: (m + EPS) / (h + EPS)
TOL = 1e-3                   # relative change below which a board counts as a tie


def log(msg):
    print(f"[phys {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def md5(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


class Timeout(Exception):
    pass


def _alarm(_sig, _frm):
    raise Timeout()


def stage(board, ref_dir, tmp):
    """Copy a board next to the reference's project files (rules for KiCad's refill)."""
    d = Path(tempfile.mkdtemp(dir=tmp))
    shutil.copy2(board, d / "board.kicad_pcb")
    for f in Path(ref_dir).glob("board.kicad_*"):
        if f.suffix != ".kicad_pcb":
            shutil.copy2(f, d / f.name)
    return d / "board.kicad_pcb"


# ----------------------------------------------------------------------------- per board
class BoardCtx:
    """Brief and place terms of one board, built once from the human reference."""

    def __init__(self, bid, cache):
        from kae.board.kicad_file import load
        from kae.physics.place_terms import Terms
        self.bid = bid
        self.ref_dir = WORK / "tasks" / bid / "reference"
        self.ref_path = self.ref_dir / "board.kicad_pcb"
        self.ref = load(self.ref_path)
        self.cache = cache / bid
        self.cache.mkdir(parents=True, exist_ok=True)
        bf = self.cache / "brief.json"
        h = md5(self.ref_path)
        meta = self.cache / "brief.meta.json"
        if bf.exists() and meta.exists() and json.loads(meta.read_text()).get("ref_md5") == h:
            self.brief = json.loads(bf.read_text())
        else:
            from kae.circuit.brief import build
            self.brief = json.loads(json.dumps(build(self.ref), default=str))
            bf.write_text(json.dumps(self.brief, indent=1))
            meta.write_text(json.dumps(dict(ref_md5=h, built=time.strftime("%F %T"))))
        self.terms = Terms(self.ref, self.brief)
        self.uuids = {fp.uuid for fp in self.ref.footprints}
        self.by_ref = {}
        for fp in self.ref.footprints:
            self.by_ref.setdefault(fp.ref, []).append(fp.uuid)
        self.ref_md5 = h

    def poses(self, board):
        """{reference uuid: pose} of a board (uuid, else unique reference designator)."""
        out, miss = {}, 0
        for fp in board.footprints:
            u = fp.uuid if fp.uuid in self.uuids else None
            if u is None:
                c = self.by_ref.get(fp.ref) or []
                u = c[0] if len(c) == 1 else None
            if u is None:
                miss += 1
                continue
            out[u] = (fp.x, fp.y, fp.rot, fp.side)
        return out, miss

    def place(self, board):
        from kae.board.kicad_file import load
        b = load(board)
        poses, miss = self.poses(b)
        T = self.terms
        total = float(T.total(poses))
        kinds = {k: float(v) for k, v in T.total_by_kind(poses).items()}
        capped, capped_kind, structs = 0.0, defaultdict(float), []
        for s in T.breakdown(poses):
            u = float(s["util"]) if s["util"] is not None and math.isfinite(s["util"]) else U_CAP
            cu = min(U_CAP, max(0.0, u))
            capped += cu
            capped_kind[s["kind"]] += cu
            structs.append(dict(id=s["id"], kind=s["kind"], value=round(float(s["value"]), 4), unit=s["unit"],
                                u=round(u, 4), cost=round(float(s["cost"]), 4), conf=round(float(s["confidence"]), 3)))
        return dict(total=round(total, 4), by_kind={k: round(v, 4) for k, v in kinds.items()},
                    capped=round(capped, 4), capped_by_kind={k: round(v, 4) for k, v in capped_kind.items()},
                    n_structs=len(structs), unmatched_parts=miss, structs=structs)

    def routed(self, board):
        from kae.joint.scorecard import physics_total
        from kae.route.critical_recheck import board_physics
        ph = board_physics(str(board), brief=self.brief, terms=self.terms)
        mods, opens, errs, per = {}, 0, {}, {}
        for k, v in ph.items():
            if k.startswith("_") or not isinstance(v, dict):
                continue
            mods[k] = v.get("u")
            opens += int(v.get("open_hops") or 0)
            if v.get("error"):
                errs[k] = v["error"][:160]
            per[k] = dict(kind=v.get("kind"), value=v.get("value"), unit=v.get("unit"), alloc=v.get("alloc"),
                          u=v.get("u"), open_hops=v.get("open_hops"),
                          **({"note": v["note"]} if v.get("note") else {}))
        rails = ph.get("_rails") or {}
        worst = [x for r in rails.values() if isinstance(r, dict) for x in r.values() if isinstance(x, (int, float))]
        return dict(total=round(physics_total(mods), 4), n_modules=len(mods),
                    missing=sum(1 for u in mods.values() if u is None), open_hops=opens, errors=errs,
                    worst_rail_mohm=round(max(worst), 3) if worst else None, modules=per)


def score_board(ctx, board, routed, tmp, timeout):
    """{place, routed} of one board file, each with its own error."""
    out = {}
    signal.signal(signal.SIGALRM, _alarm)
    for part in ("place", "routed"):
        if part == "routed" and not routed:
            continue
        t0 = time.monotonic()
        signal.alarm(int(timeout))
        try:
            if part == "place":
                out[part] = ctx.place(board)
            else:
                out[part] = ctx.routed(stage(board, ctx.ref_dir, tmp))
        except Timeout:
            out[part] = dict(error=f"timeout {timeout}s")
        except Exception as e:  # noqa: BLE001 - one board's failure must not stop the others
            out[part] = dict(error=f"{type(e).__name__}: {str(e)[:200]}",
                             trace=traceback.format_exc(limit=3)[-600:])
        finally:
            signal.alarm(0)
        out[part]["seconds"] = round(time.monotonic() - t0, 2)
    return out


def attempt_dir(run, bid, attempt=0):
    hits = sorted(Path(run).glob(f"*/*/{bid}/attempt-{attempt}"))  # place, route or joint tasks
    return hits[0] if hits else None


def harness_info(adir):
    try:
        r = json.loads((adir / "attempt.json").read_text())
    except (OSError, ValueError):
        return {}
    s = r.get("score") or {}
    p = (r.get("probe") or {}).get("score") or {}
    if r.get("kind") == "route":
        p = s
        s = dict(legal=True)
    elif r.get("kind") == "joint":  # harness score v7: placement and routing in one score
        p = s
    return dict(status=r.get("status"), legal=bool(s.get("legal")),
                clean=bool(s.get("legal")) and bool(p.get("clean")),
                completion=p.get("completion", 0.0) if s.get("valid", True) else 0.0,
                length_mm=p.get("track_length_mm"), vias=p.get("vias"))


# ----------------------------------------------------------------------------- summary
def gmean(xs):
    xs = [x for x in xs if x is not None and x > 0 and math.isfinite(x)]
    return math.exp(sum(math.log(x) for x in xs) / len(xs)) if xs else None


def ratio(m, h):
    return (m + EPS) / (h + EPS)


def worse(m, h):
    return m > h * (1 + TOL) + 1e-9


def better(m, h):
    return m < h * (1 - TOL) - 1e-9


def summarize(run, rows, human):
    """Aggregate of one run (rows: {bid: result}) against human ({bid: result})."""
    cov = Counter()
    reasons = {}
    pr, cr, rr = [], [], []
    pw = pb = cw = cb = rw = rb = 0
    nz = 0
    kind_r, kind_w, kind_n, kind_exc = defaultdict(list), Counter(), Counter(), defaultdict(float)
    opens_m, opens_h = [], []
    pl_both = rt_both = 0
    lr, lw, nl = [], 0, 0             # place, legal placements only
    xr, xw, nx = [], 0, 0             # routed, no open hop on either board
    hz = defaultdict(list)            # harness numbers: all boards with an attempt / physics boards
    for bid, r in sorted(rows.items()):
        h = human.get(bid) or {}
        hi = r.get("harness") or {}
        if hi or r.get("skip") != "no attempt":
            phb = bool((h.get("place") or {}).get("n_structs"))
            for scope in (("all", "phys") if phb else ("all",)):
                hz[scope + "_n"].append(1)
                hz[scope + "_legal"].append(int(bool(hi.get("legal"))))
                hz[scope + "_clean"].append(int(bool(hi.get("clean"))))
                hz[scope + "_compl"].append(float(hi.get("completion") or 0.0))
                if hi.get("length_mm") is not None:
                    hz[scope + "_len"].append(float(hi["length_mm"]))
        if r.get("skip"):
            cov[r["skip"]] += 1
            reasons[bid] = r["skip"]
            continue
        mp, hp = r.get("place") or {}, h.get("place") or {}
        if "total" not in mp or "total" not in hp:
            why = (mp.get("error") or hp.get("error") and f"human: {hp.get('error')}" or "place not scored")
            cov["place error"] += 1
            reasons[bid] = why
        elif mp["n_structs"] == 0:
            cov["no physics structures"] += 1
            nz += 1
        else:
            pl_both += 1
            pr.append(ratio(mp["total"], hp["total"]))
            cr.append(ratio(mp["capped"], hp["capped"]))
            pw += worse(mp["total"], hp["total"])
            pb += better(mp["total"], hp["total"])
            cw += worse(mp["capped"], hp["capped"])
            cb += better(mp["capped"], hp["capped"])
            if (r.get("harness") or {}).get("legal"):
                nl += 1
                lr.append(ratio(mp["capped"], hp["capped"]))
                lw += worse(mp["capped"], hp["capped"])
            for k in set(mp["capped_by_kind"]) | set(hp["capped_by_kind"]):
                a, b = mp["capped_by_kind"].get(k, 0.0), hp["capped_by_kind"].get(k, 0.0)
                kind_r[k].append(ratio(a, b))
                kind_n[k] += 1
                kind_w[k] += worse(a, b)
                kind_exc[k] += max(0.0, a - b)
        mr, hr = r.get("routed") or {}, h.get("routed") or {}
        if "total" in mr and "total" in hr and (mr["n_modules"] or hr["n_modules"]):
            rt_both += 1
            rr.append(ratio(mr["total"], hr["total"]))
            rw += worse(mr["total"], hr["total"])
            rb += better(mr["total"], hr["total"])
            opens_m.append(mr["open_hops"])
            opens_h.append(hr["open_hops"])
            if mr["open_hops"] == 0 and hr["open_hops"] == 0 and mr["missing"] <= hr["missing"]:
                nx += 1
                xr.append(ratio(mr["total"], hr["total"]))
                xw += worse(mr["total"], hr["total"])
        elif mr.get("error") or hr.get("error"):
            cov["routed error"] += 1
            reasons.setdefault(bid, f"routed: {mr.get('error') or 'human ' + str(hr.get('error'))}")
    exc = sum(kind_exc.values())
    kinds = {k: dict(n=kind_n[k], gmean_ratio=round(gmean(kind_r[k]) or 0, 3), worse=kind_w[k],
                     excess_share=round(kind_exc[k] / exc, 3) if exc > 0 else 0.0) for k in sorted(kind_n)}
    harness = {}
    for scope in ("all", "phys"):
        n = len(hz[scope + "_n"])
        harness[scope] = dict(n=n, legal=sum(hz[scope + "_legal"]), clean=sum(hz[scope + "_clean"]),
                              completion=round(sum(hz[scope + "_compl"]) / n, 4) if n else None,
                              length_mm=round(sum(hz[scope + "_len"]), 1))
    return dict(run=run, boards=len(rows), harness=harness, place_scored=pl_both, no_structures=nz,
                place_gmean_ratio=gmean(pr), place_worse=pw, place_better=pb,
                capped_gmean_ratio=gmean(cr), capped_worse=cw, capped_better=cb,
                legal_scored=nl, legal_capped_gmean_ratio=gmean(lr), legal_capped_worse=lw,
                closed_scored=nx, closed_routed_gmean_ratio=gmean(xr), closed_routed_worse=xw,
                routed_scored=rt_both, routed_gmean_ratio=gmean(rr), routed_worse=rw, routed_better=rb,
                open_hops_mean=(sum(opens_m) / len(opens_m)) if opens_m else None,
                open_hops_mean_human=(sum(opens_h) / len(opens_h)) if opens_h else None,
                kinds=kinds, coverage=dict(cov), reasons=reasons)


def fmt(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}"


def markdown(sums, n_human, human_cov):
    L = ["| run | legal / clean / completion, physics boards | clean / completion, all boards | place scored | phys total x human (gmean) | worse / better | capped-u x human | worse / better "
         "| legal only: n, capped-u x human, worse | routed scored | routed x human | worse / better "
         "| open hops (method / human) | no open hop: n, routed x human, worse |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in sums:
        hp, ha = s["harness"]["phys"], s["harness"]["all"]
        L.append(f"| {s['run']} | {hp['legal']} / {hp['clean']} of {hp['n']}, {fmt(hp['completion'])} | "
                 f"{ha['clean']} of {ha['n']}, {fmt(ha['completion'])} | {s['place_scored']} | {fmt(s['place_gmean_ratio'])} | {s['place_worse']} / "
                 f"{s['place_better']} | {fmt(s['capped_gmean_ratio'])} | {s['capped_worse']} / {s['capped_better']} | "
                 f"{s['legal_scored']}, {fmt(s['legal_capped_gmean_ratio'])}, {s['legal_capped_worse']} | "
                 f"{s['routed_scored']} | {fmt(s['routed_gmean_ratio'])} | {s['routed_worse']} / {s['routed_better']} | "
                 f"{fmt(s['open_hops_mean'], 1)} / {fmt(s['open_hops_mean_human'], 1)} | "
                 f"{s['closed_scored']}, {fmt(s['closed_routed_gmean_ratio'])}, {s['closed_routed_worse']} |")
    kinds = sorted({k for s in sums for k in s["kinds"]})
    L += ["", "Per kind (capped u, method x human gmean; boards worse; share of the run's capped-u excess):", "",
          "| run | " + " | ".join(kinds) + " |", "|---|" + "---|" * len(kinds)]
    for s in sums:
        cells = []
        for k in kinds:
            d = s["kinds"].get(k)
            cells.append("-" if not d else f"{d['gmean_ratio']:.2f} ({d['worse']}/{d['n']}, {100 * d['excess_share']:.0f}%)")
        L.append(f"| {s['run']} | " + " | ".join(cells) + " |")
    L += ["", f"Coverage: {n_human} boards; human reference: {json.dumps(human_cov)}."]
    for s in sums:
        L.append(f"- {s['run']}: {json.dumps(s['coverage'])}"
                 + (f"; " + "; ".join(f"{b}: {w}" for b, w in sorted(s['reasons'].items())) if s["reasons"] else ""))
    return "\n".join(L)


# ----------------------------------------------------------------------------- main
def main(argv=None):
    global WORK
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--suite", default=str(WORK / "ab33.txt"), help="board ids (default: the runs' union)")
    ap.add_argument("--all", action="store_true", help="every board found in the runs, ignore --suite")
    ap.add_argument("--out", default=str(WORK / "phys"))
    ap.add_argument("--cache", default=str(WORK / "phys-cache"))
    ap.add_argument("--md", default=None, help="also write the markdown summary here")
    ap.add_argument("--no-routed", action="store_true")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--only", default=None, help="comma-separated board ids")
    ap.add_argument("--workdir", default=str(WORK), help="kaebench workdir holding tasks/ (reference boards)")
    ap.add_argument("--attempt", type=int, default=0, help="which attempt (seed) of each task to score")
    a = ap.parse_args(argv)
    WORK = Path(a.workdir).resolve()
    runs = []
    for r in a.runs:
        if Path(r).is_dir():
            runs.append(Path(r).resolve())
        else:
            log(f"{r}: no such run directory, skipped")
    if not runs:
        return 1
    cache, out = Path(a.cache), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.only:
        ids = a.only.split(",")
    elif a.all or not Path(a.suite).exists():
        ids = sorted({p.parent.name for r in runs for p in r.glob(f"*/*/*/attempt-{a.attempt}")})
    else:
        ids = [x.strip() for x in Path(a.suite).read_text().split() if x.strip() and not x.startswith("#")]
    routed = not a.no_routed
    tmp = tempfile.mkdtemp(prefix="phys-")
    human, rows = {}, {r.name: {} for r in runs}
    t_all = time.monotonic()
    for n, bid in enumerate(ids):
        t0 = time.monotonic()
        try:
            ctx = BoardCtx(bid, cache)
        except Exception as e:  # noqa: BLE001
            why = f"brief/terms: {type(e).__name__}: {str(e)[:160]}"
            log(f"{bid}: {why}")
            human[bid] = dict(place=dict(error=why), routed=dict(error=why))
            for r in runs:
                rows[r.name][bid] = dict(skip="brief/terms failed")
            continue
        key = f"{VERSION}:{int(routed)}"
        hf = ctx.cache / "human.json"
        h = json.loads(hf.read_text()) if hf.exists() else None
        if not h or h.get("key") != key or h.get("md5") != ctx.ref_md5:
            h = dict(key=key, md5=ctx.ref_md5, **score_board(ctx, ctx.ref_path, routed, tmp, a.timeout))
            hf.write_text(json.dumps(h, indent=1))
        human[bid] = h
        for r in runs:
            ad = attempt_dir(r, bid, a.attempt)
            if ad is None:
                rows[r.name][bid] = dict(skip="no attempt")
                continue
            info = harness_info(ad)
            ob = ad / "output" / "board.kicad_pcb"
            if not ob.exists():
                rows[r.name][bid] = dict(skip=f"no output board (status {info.get('status')})", harness=info)
                continue
            rf = ctx.cache / "runs" / (f"{r.name}.json" if a.attempt == 0 else f"{r.name}.a{a.attempt}.json")
            m = md5(ob)
            res = json.loads(rf.read_text()) if rf.exists() else None
            if not res or res.get("key") != key or res.get("md5") != m:
                res = dict(key=key, md5=m, **score_board(ctx, ob, routed, tmp, a.timeout))
                rf.parent.mkdir(parents=True, exist_ok=True)
                rf.write_text(json.dumps(res, indent=1))
            res["harness"] = info
            rows[r.name][bid] = res
        hp = h.get("place", {})
        log(f"[{n + 1}/{len(ids)}] {bid}: human place {hp.get('total', hp.get('error'))} "
            f"routed {h.get('routed', {}).get('total', h.get('routed', {}).get('error'))} "
            f"({time.monotonic() - t0:.1f}s)")
    shutil.rmtree(tmp, ignore_errors=True)
    hcov = Counter()
    for bid, h in human.items():
        p = h.get("place") or {}
        hcov["place ok" if "total" in p else "place error"] += 1
        hcov["with physics structures"] += bool(p.get("n_structs"))
        if routed:
            hcov["routed ok" if "total" in (h.get("routed") or {}) else "routed error"] += 1
    sums = []
    for r in runs:
        s = summarize(r.name, rows[r.name], human)
        sums.append(s)
        (out / f"{r.name}.json").write_text(json.dumps(dict(summary=s, human=human, boards=rows[r.name]), indent=1))
    md = markdown(sums, len(ids), dict(hcov))
    print(md)
    if a.md:
        Path(a.md).write_text(md + "\n")
    log(f"done in {time.monotonic() - t_all:.0f}s; JSON in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
