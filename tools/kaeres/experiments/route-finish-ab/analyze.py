#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tables for the route-finish A/B (PLAN.md): one markdown report from the stored runs and measures.

    analyze.py --exp route-finish-ab [--out /var/tmp/$USER/rf-ab] [--section routing,geometry,physics,hazards,stages]
               [--offset-list FILE]

Arms: A, C, D, E are the experiment's kaeres methods (by name: "rf legacy", "rf finish", "... import-tails",
"... ground-vias"); B and A0r (A0 re-scored at this harness) come from OUT/<arm>/<board>/ (fork.sh); A0 is
merge3-ab's stored row (old scorer, cited only); human is the corpus board (physics only).

- routing: cp1, cpk (= cp1: one attempt per board, each a restart portfolio), clean_strict, completion, not
  closed, DRC errors per board and by type; paired tests of the pre-registered pairs (kaebench.stats).
- geometry: kae.route.taut stats of each kept board (OUT/measure/<board>/<arm>.stats.json).
- physics: per term against A and against the human layout, each difference judged against the raster
  noise floor; --offset-list writes the (board, arm) pairs that need offset-averaging (PLAN.md, noise).
- hazards: the kept board's hazards (RFAB_report in adapter.log; B: finish's report).
- stages: seconds per stage from restart.py's summary (RFAB_summary in adapter.log) and finish's report.
"""
import argparse
import csv
import gzip
import json
import math
import os
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

STORE = Path(os.path.expanduser(os.environ.get("KAE_RESULTS", "~/kae-baselines")))
CORPUS = Path(os.path.expanduser(os.environ.get("KAE_CORPUS", "~/kae-boards")))
A0_ID, A0_EXP = "286c2335844d", "merge3-ab"
PAIRS = (("A", "A2"), ("A", "B"), ("B", "C"), ("A", "C"), ("C", "D"), ("C", "E"), ("A0r", "A"))   # (control, treatment)
# raster noise floor of the fixed evaluator (relative, one side), measured at 4 window offsets (rf-raster);
# terms without a measured floor are reported with "floor ?" and never called a signal on their own
FLOOR = {"loss.copper": 0.005, "drop.rail": 0.02, "supply.peak": 0.04, "emission.cable_E": 0.05}
OFFSET_TAGS = ("0.0625,0.0625", "0.125,0.125", "0.1875,0.1875")


def jl(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def arm_of(name):
    n = name.lower()
    if n.startswith("rf legacy twin"):
        return "A2"
    if n.startswith("rf legacy"):
        return "A"
    if "import-tails" in n:
        return "D"
    if "ground-vias" in n:
        return "E"
    if n.startswith("rf finish"):
        return "C"
    return None


class Data:
    def __init__(self, exp, out, churn="exclude"):
        self.e = jl(STORE / "experiments" / exp / "experiment.json")
        if not self.e:
            sys.exit(f"no experiment {exp}")
        self.out = Path(out)
        self.boards = (STORE / "experiments" / exp / "boards.txt").read_text().split()
        self.ids = {arm_of(m["name"]): m["id"] for m in self.e["methods"] if arm_of(m["name"])}
        self.drc_eval = self.e["evaluators"]["drc"]
        self.arms = [a for a in ("A0", "A0r", "A", "A2", "B", "C", "D", "E") if a in ("A0", "A0r", "B") or a in self.ids]
        self._a0 = None
        self.src = defaultdict(lambda: defaultdict(set))   # arm -> source -> boards
        self.churn_mode = churn
        self.churn = {p.parent.name for p in self.out.glob("rescore-*/*/churn.json") if (jl(p) or {}).get("all_churn")}

    def run_dir(self, arm, b):
        if arm == "A0":
            mid = A0_ID
        elif arm in self.ids:
            mid = self.ids[arm]
        else:
            return None
        hits = sorted((STORE / "boards" / b / "runs").glob(f"*.{mid[:8]}.a0*"))
        return hits[0] if hits else None

    def fork_dir(self, arm, b):
        d = self.out / ("A0" if arm == "A0r" else arm) / b
        return d if (d / "attempt.json").exists() else None

    def score(self, arm, b):
        if arm == "A0":
            if self._a0 is None:
                f = STORE / "experiments" / A0_EXP / "results.csv"
                self._a0 = {r["board"]: r for r in csv.DictReader(open(f)) if r["method_id"] == A0_ID}
            r = self._a0.get(b)
            if not r:
                return None
            return dict(clean=r["clean"] == "True", completion=float(r["completion"] or 0), unconnected=int(r["unconnected"] or 0),
                        errors=int(r["errors"] or 0), errors_by_type=json.loads(r["errors_by_type"] or "{}"), clean_strict=None,
                        valid=r["valid"] == "True")
        # a re-score at the experiment's harness (fork.sh rescore:<id|B|A0>) wins over the stored score;
        # boards whose re-scores are only uuid churn (churn_check.py) have no consistent score at this scorer:
        # left out of every arm (--churn exclude), or given each run's own stored score (--churn stored)
        if b in self.churn and self.churn_mode == "exclude":
            self.src[arm]["left out (uuid churn)"].add(b)
            return None
        key = {"B": "B", "A0r": "A0"}.get(arm, (self.ids.get(arm) or "")[:12])
        r = jl(self.out / f"rescore-{key}" / b / "attempt.json") if key else None
        if r and r.get("status") == "ok" and b not in self.churn:
            self.src[arm]["rescore"].add(b)
            return r.get("score")
        if b in self.churn and arm == "A0r":   # no score of A0 against its own task at this scorer
            self.src[arm]["left out (uuid churn)"].add(b)
            return None
        if arm in ("B", "A0r"):
            d = self.fork_dir(arm, b)
            a = jl(d / "attempt.json") if d else None
            if a and a.get("status") == "ok":
                self.src[arm]["fork" + (" (uuid churn)" if b in self.churn else "")].add(b)
                return a.get("score")
            return None
        d = self.run_dir(arm, b)
        ev = jl(d / "evals" / f"{self.drc_eval}.json") if d else None
        if ev:
            self.src[arm]["stored" + (" (uuid churn)" if b in self.churn else "")].add(b)
        return (ev or {}).get("score")

    def log(self, arm, b):
        if arm in ("B", "A0r"):
            d = self.fork_dir(arm, b)
            p = d / "adapter.log" if d else None
            return p.read_text(errors="replace") if p and p.exists() else ""
        d = self.run_dir(arm, b)
        p = d / "adapter.log.gz" if d else None
        return gzip.open(p, "rt", errors="replace").read() if p and p.exists() else ""

    def run_json(self, arm, b):
        d = self.run_dir(arm, b)
        return jl(d / "run.json") if d else None

    def stats(self, arm, b):
        tag = self.ids.get(arm, arm)[:12] if arm in self.ids else ("A0" if arm in ("A0", "A0r") else arm)
        return jl(self.out / "measure" / b / f"{tag}.stats.json")

    def phys(self, arm, b, offset=None):
        tag = self.ids.get(arm, arm)[:12] if arm in self.ids else ("A0" if arm in ("A0", "A0r") else arm)
        return jl(self.out / "measure" / b / "phys" / f"{tag}{'@' + offset if offset else ''}.status.json")


def blocks(text, name):
    """JSON blocks the method command printed between RFAB_<name> and RFAB_end."""
    out = []
    for m in re.finditer(rf"^RFAB_{name}\n(.*?)\nRFAB_end$", text, re.S | re.M):
        try:
            out.append(json.loads(m.group(1)))
        except ValueError:
            pass
    return out


def last_json(text):
    for line in reversed(text.splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def table(head, rows):
    s = "| " + " | ".join(head) + " |\n|" + "---|" * len(head) + "\n"
    return s + "".join("| " + " | ".join("-" if v is None else str(v) for v in r) + " |\n" for r in rows)


def f3(x):
    return None if x is None else f"{x:.3f}"


def paired(D, metric, a, b, binary):
    sys.path.insert(0, str(STORE / "code" / f"kicad-auto-everything@{D.e['harness']['commit'][:12]}" / "bench" / "src"))
    from kaebench import stats as S
    va, vb = {}, {}
    for bd in D.boards:
        sa, sb = D.score(a, bd), D.score(b, bd)
        if sa is not None and sb is not None and metric(sa) is not None and metric(sb) is not None:
            va[bd], vb[bd] = metric(sa), metric(sb)
    if not va:
        return None
    clusters = {}
    rows = {}
    try:
        man = {json.loads(l)["id"]: json.loads(l).get("repo") for l in open(CORPUS / "manifest.jsonl") if l.strip()}
        clusters = {k: man.get(k, k) for k in va}
    except OSError:
        pass
    r = S.paired(va, vb, clusters=clusters, binary=binary)
    rows.update(r)
    return rows


# ------------------------------------------------------------------ sections
def sec_routing(D):
    out = ["## Routing (kaebench score; A0 under the old scorer, cited only)\n"]
    rows, types = [], defaultdict(Counter)
    for arm in D.arms:
        sc = {b: D.score(arm, b) for b in D.boards}
        got = {b: s for b, s in sc.items() if s}
        if not got:
            continue
        n = len(got)
        cp1 = sum(bool(s.get("clean")) for s in got.values()) / n
        strict = [s.get("clean_strict") for s in got.values() if s.get("clean_strict") is not None]
        comp = st.mean(float(s.get("completion") or 0) for s in got.values())
        nc = sum(1 for s in got.values() if (s.get("unconnected") or 0) > 0)
        err = st.mean(float(s.get("errors") or 0) for s in got.values())
        for s in got.values():
            types[arm].update(s.get("errors_by_type") or {})
        rows.append([arm, f"{n}/{len(D.boards)}", f3(cp1), f3(cp1), f3(sum(strict) / len(strict)) if strict else None,
                     f3(comp), nc, f"{err:.2f}", sum(int(s.get("unconnected") or 0) for s in got.values()),
                     sum(1 for s in got.values() if not s.get("valid", True))])
    out.append("Score sources (per arm, board-reads): " + "; ".join(
        f"{a} " + ", ".join(f"{k} {len(n)}" for k, n in sorted(c.items())) for a, c in D.src.items()) + "\n")
    if D.churn:
        out.append(f"Boards whose re-score is only uuid churn ({len(D.churn)}, --churn {D.churn_mode}): {' '.join(sorted(D.churn))}\n")
    out.append(table(["arm", "boards", "cp1", "cpk (k=1)", "clean_strict", "completion", "not closed", "errors / board",
                      "unconnected (sum)", "invalid"], rows))
    inv = []
    for arm in D.arms:
        for b in D.boards:
            sc = D.score(arm, b)
            if sc and not sc.get("valid", True):
                bad = [k for k, v in (sc.get("integrity") or {}).items() if v is False]
                fo = sc.get("foreign") or {}
                det = "; ".join(f"{x.get('kind')} {x.get('change')}" for x in (fo.get("items") or [])[:4])
                inv.append([arm, b[:40], ",".join(bad), fo.get("by_kind") or fo.get("counts") or fo.get("count"), det])
    if inv:
        out.append("\n### Invalid outputs (integrity checks that failed; foreign objects)\n")
        out.append(table(["arm", "board", "failed", "foreign", "first items"], inv))
    ks = sorted({k for c in types.values() for k in c}, key=lambda k: -sum(c[k] for c in types.values()))
    out.append("\n### DRC errors by type (sum over boards)\n")
    out.append(table(["type"] + list(types), [[k] + [types[a].get(k, 0) for a in types] for k in ks]))
    out.append("\n### Paired (treatment - control; McNemar for clean, sign-flip otherwise; 95 % CI resamples repositories)\n")
    prow = []
    for a, b in PAIRS:
        for name, met, binary in (("clean", lambda s: bool(s.get("clean")), True),
                                  ("clean_strict", lambda s: s.get("clean_strict"), True),
                                  ("completion", lambda s: float(s.get("completion") or 0), False),
                                  ("errors", lambda s: float(s.get("errors") or 0), False)):
            r = paired(D, met, a, b, binary)
            if r:
                prow.append([f"{b} vs {a}", name, r["n"], r["mean_a"], r["mean_b"], r["diff"],
                             "[" + ", ".join(f"{x:.3f}" for x in r["ci"]) + "]" if r.get("ci") else None, r["p"],
                             (f"+{len(r['gained'])}/-{len(r['lost'])}" if binary else None)])
    out.append(table(["pair", "metric", "n", "control", "treatment", "diff", "95 % CI", "p", "flips"], prow))
    return "\n".join(out)


GEO = ("perpendicular", "oblique", "acute_entries", "overhanging", "overhang_mm2", "length_mm", "corners", "acute", "arcs")


def geo(s):
    if not s:
        return None
    return dict(s, length_mm=sum((s.get("length") or {}).values()))


def sec_geometry(D):
    out = ["## Geometry (kae.route.taut stats of the kept boards)\n"]
    rows = []
    per = {}
    for arm in ["human"] + D.arms:
        g = {b: geo(D.stats(arm, b)) for b in D.boards}
        g = {b: v for b, v in g.items() if v}
        per[arm] = g
        if not g:
            continue
        ent = sum(v.get("entries", 0) for v in g.values())
        rows.append([arm, len(g)] + [round(sum(v.get(k, 0) for v in g.values()), 1) for k in GEO]
                    + [f3((sum(v.get("oblique", 0) + v.get("acute_entries", 0) for v in g.values())) / ent) if ent else None])
    out.append(table(["arm", "boards"] + [f"{k} (sum)" for k in GEO] + ["oblique+acute share"], rows))
    out.append("\n### Paired against A (boards both have): median per-board ratio, boards lower / higher\n")
    prow = []
    for arm in [a for a in D.arms if a != "A"] + ["human"]:
        for k in ("oblique", "acute_entries", "overhanging", "length_mm", "corners", "arcs"):
            common = [b for b in per.get(arm, {}) if b in per.get("A", {})]
            if not common:
                continue
            r = [per[arm][b].get(k, 0) / per["A"][b][k] for b in common if per["A"][b].get(k)]
            lo = sum(per[arm][b].get(k, 0) < per["A"][b].get(k, 0) for b in common)
            hi = sum(per[arm][b].get(k, 0) > per["A"][b].get(k, 0) for b in common)
            prow.append([f"{arm} / A", k, len(common), f3(st.median(r)) if r else None, lo, hi])
    out.append(table(["pair", "measure", "n", "median ratio", "lower", "higher"], prow))
    return "\n".join(out)


def terms(status):
    """{term id: (observable, contribution, raw value or None)}"""
    out = {}
    for t in (status or {}).get("terms") or []:
        if t.get("contribution") is None:
            continue
        m = re.match(r"\s*(-?[\d.]+(?:e-?\d+)?)", str(t.get("value") or ""))
        out[t["id"]] = (t["obs"], float(t["contribution"]), float(m.group(1)) if m else None)
    return out


def phys_terms(D, arm, b):
    """Terms at offset 0, and (when the shifted rasters exist) their mean and spread over the 4 offsets."""
    base = terms(D.phys(arm, b))
    if not base:
        return {}, False
    samples = [base] + [terms(D.phys(arm, b, o)) for o in OFFSET_TAGS]
    samples = [s for s in samples if s]
    if len(samples) < 4:
        return {k: (o, c, v, None) for k, (o, c, v) in base.items()}, False
    out = {}
    for k, (o, c, v) in base.items():
        vals = [(s[k][2] if s[k][2] is not None else s[k][1]) for s in samples if k in s]
        out[k] = (o, st.mean(s[k][1] for s in samples if k in s), st.mean(vals), st.pstdev(vals) if len(vals) > 1 else 0.0)
    return out, True


def sec_physics(D, offset_list=None):
    out = ["## Physics (fixed evaluator, per term)\n",
           "A term's difference is judged on its raw value (else its contribution): |ratio - 1| <= floor is "
           "noise; floor .. 2 x floor is ambiguous (offset-average it); > 2 x floor is a signal. With all four "
           "offsets measured, the means are compared and the difference must exceed 2 x the pooled offset SD.\n"]
    need = set()
    tot = defaultdict(dict)
    by_obs = defaultdict(lambda: defaultdict(list))   # (pair) -> obs -> [ratio]
    verdicts = defaultdict(lambda: defaultdict(Counter))
    for b in D.boards:
        P = {}
        for arm in ["human"] + D.arms:
            P[arm] = phys_terms(D, arm, b)
            if P[arm][0]:
                tot[arm][b] = sum(x[1] for x in P[arm][0].values())
        for ref in ("A", "human"):
            if not P.get(ref, ({},))[0]:
                continue
            for arm in D.arms:
                if arm == ref or not P[arm][0]:
                    continue
                for k, x in P[arm][0].items():
                    y = P[ref][0].get(k)
                    if not y:
                        continue
                    xv, yv = (x[2] if x[2] is not None else x[1]), (y[2] if y[2] is not None else y[1])
                    if not yv:
                        continue
                    r = xv / yv
                    by_obs[f"{arm} / {ref}"][x[0]].append(r)
                    fl = FLOOR.get(x[0])
                    if fl is None:
                        v = "floor ?"
                    elif P[arm][1] and P[ref][1] and len(x) > 3 and x[3] is not None and y[3] is not None:
                        sd = math.sqrt((x[3] ** 2 + y[3] ** 2) / 2)
                        v = "signal" if abs(xv - yv) > 2 * max(sd, 1e-12) else "noise (offsets)"
                    elif abs(r - 1) <= fl:
                        v = "noise"
                    elif abs(r - 1) <= 2 * fl:
                        v = "ambiguous"
                        need.update({(b, arm), (b, ref)})
                    else:
                        v = "signal"
                    verdicts[f"{arm} / {ref}"][x[0]][v + (" better" if v == "signal" and r < 1 else " worse" if v == "signal" else "")] += 1
    rows = []
    for arm in ["human"] + D.arms:
        if tot.get(arm):
            common = [b for b in tot[arm] if b in tot.get("A", {}) and tot["A"][b]]
            lr = [math.log(tot[arm][b] / tot["A"][b]) for b in common if tot[arm][b] > 0]
            rows.append([arm, len(tot[arm]), round(sum(tot[arm].values()), 1),
                         f3(math.exp(st.median(lr))) if lr else None])
    out.append(table(["arm", "boards", "total mW_eq (sum)", "median total / A"], rows))
    out.append("\n### Per observable: median ratio, and verdicts against the noise floor\n")
    prow = []
    for pair in sorted(by_obs):
        for o in sorted(by_obs[pair]):
            v = by_obs[pair][o]
            vc = verdicts[pair][o]
            prow.append([pair, o, FLOOR.get(o, "?"), len(v), f3(st.median(v)), f3(min(v)), f3(max(v)),
                         ", ".join(f"{k} {n}" for k, n in sorted(vc.items()))])
    out.append(table(["pair", "observable", "floor", "terms", "median ratio", "min", "max", "verdicts"], prow))
    if offset_list:
        Path(offset_list).write_text("".join(f"{b} {a}\n" for b, a in sorted(need)))
        out.append(f"\n{len(need)} (board, arm) pairs need offset-averaging: {offset_list}\n")
    return "\n".join(out)


def hazards_of(D, arm, b):
    txt = D.log(arm, b)
    rep = (blocks(txt, "report") or [None])[-1] if arm not in ("B", "A0r") else last_json(txt)
    hz = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "hazards" and isinstance(v, list):
                    hz.extend(h for h in v if isinstance(h, dict))
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(rep)
    seen, uniq = set(), []
    for h in hz:
        key = json.dumps(h, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            uniq.append(h)
    return uniq


def sec_hazards(D):
    out = ["## Hazards raised on the kept boards (by code, sum over boards; boards with any)\n"]
    cnt, boards = defaultdict(Counter), defaultdict(set)
    for arm in [a for a in D.arms if a not in ("A0", "A0r")]:
        for b in D.boards:
            for h in hazards_of(D, arm, b):
                code = h.get("code") or h.get("kind") or h.get("id") or "?"
                cnt[arm][code] += 1
                boards[arm].add(b)
    gv = []   # Q5's boards: E's kept attempt laid ground vias before routing (plane_escapes.ground_vias)
    if "E" in D.ids:
        for b in D.boards:
            rep = (blocks(D.log("E", b), "report") or [None])[-1] or {}
            if ((rep.get("plane_escapes") or {}).get("ground_vias")):
                gv.append(b)
    codes = sorted({c for x in cnt.values() for c in x}, key=lambda c: -sum(x[c] for x in cnt.values()))
    if "E" in D.ids:
        out.append(f"Boards where E laid ground vias before routing (Q5's set, {len(gv)}): {' '.join(gv) or '-'}\n")
    out.append(table(["code"] + list(cnt), [[c] + [cnt[a].get(c, 0) for a in cnt] for c in codes]
                     + [["boards with any"] + [len(boards[a]) for a in cnt]]))
    return "\n".join(out)


def stage_seconds(D, arm, b):
    """{stage: seconds} of one run: route attempts (sum of their wall), judge, final pass (last mile), finish
    and its parts, and the run's wall and CPU."""
    s = {}
    if arm == "B":
        rep = last_json(D.log(arm, b)) or {}
        for k, v in (rep.get("seconds") or {}).items():
            s[f"finish.{k}"] = v
        a = jl(D.fork_dir(arm, b) / "attempt.json") if D.fork_dir(arm, b) else {}
        s["wall"] = (a or {}).get("runtime_s")
        return s
    sm = (blocks(D.log(arm, b), "summary") or [None])[-1] or {}
    rj = D.run_json(arm, b) or {}
    for d in sm.get("attempt_log") or []:
        k = d.get("k")
        key = k if k in ("final", "finish") else "route attempts"
        s[key] = s.get(key, 0.0) + float(d.get("wall_s") or 0.0)
    fin = sm.get("finish") or {}
    for k, v in (fin.get("seconds") or {}).items():
        s[f"finish.{k}"] = v
    s["judge"] = sm.get("judge_wall_s")
    s["wall"] = rj.get("runtime_s")
    s["cpu"] = (rj.get("work") or {}).get("cpu_s")
    return s


def sec_stages(D):
    out = ["## Seconds per stage (restart.py summary; sums over boards, and medians)\n",
           "Route attempts run 4 at a time, so their summed wall exceeds the run's wall.\n"]
    rows = []
    for arm in [a for a in D.arms if a not in ("A0", "A0r")]:
        acc = defaultdict(list)
        for b in D.boards:
            for k, v in stage_seconds(D, arm, b).items():
                if v is not None:
                    acc[k].append(float(v))
        for k in sorted(acc):
            rows.append([arm, k, len(acc[k]), round(sum(acc[k]) / 3600, 2), round(st.median(acc[k]), 1)])
    out.append(table(["arm", "stage", "boards", "hours (sum)", "median s"], rows))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--exp", required=True)
    ap.add_argument("--out", default=f"/var/tmp/{os.environ.get('USER', '')}/rf-ab")
    ap.add_argument("--section", default="routing,geometry,physics,hazards,stages")
    ap.add_argument("--churn", choices=("exclude", "stored"), default="exclude",
                    help="boards whose re-score is only uuid churn: left out of every arm, or each run's stored score")
    ap.add_argument("--offset-list", help="write the (board, arm) pairs whose physics needs offset-averaging")
    a = ap.parse_args()
    D = Data(a.exp, a.out, a.churn)
    print(f"# route-finish A/B: {a.exp}\n\nArms {', '.join(D.arms)}; methods "
          + ", ".join(f"{k} `{v}`" for k, v in D.ids.items()) + f"; DRC evaluator `{D.drc_eval}`; {len(D.boards)} boards.\n")
    fns = dict(routing=sec_routing, geometry=sec_geometry, physics=lambda d: sec_physics(d, a.offset_list),
               hazards=sec_hazards, stages=sec_stages)
    for s in a.section.split(","):
        print(fns[s](D) + "\n")


if __name__ == "__main__":
    main()
