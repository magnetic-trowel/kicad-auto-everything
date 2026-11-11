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
import random
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
    def __init__(self, exp, out, churn="exclude", only_arms=None, twin=None, drop=None):
        self.e = jl(STORE / "experiments" / exp / "experiment.json")
        if not self.e:
            sys.exit(f"no experiment {exp}")
        self.out = Path(out)
        self.boards = (STORE / "experiments" / exp / "boards.txt").read_text().split()
        self.ids = {arm_of(m["name"]): m["id"] for m in self.e["methods"] if arm_of(m["name"])}
        self.drc_eval = self.e["evaluators"]["drc"]
        self.arms = [a for a in ("A0", "A0r", "A", "A2", "B", "C", "D", "E") if a in ("A0", "A0r", "B") or a in self.ids]
        self._a0 = None
        if only_arms:
            self.arms = [a for a in self.arms if a in only_arms]
        self.drop = defaultdict(set)
        for x in drop or []:
            a_, _, b_ = x.partition(":")
            self.drop[a_].add(b_)
        self.src = defaultdict(lambda: defaultdict(set))   # arm -> source -> boards
        self.churn_mode = churn
        self.churn = {p.parent.name for p in self.out.glob("rescore-*/*/churn.json") if p.parent.parent.name != "rescore-A0"
                      and (jl(p) or {}).get("all_churn")}
        # stored outputs of the old code carry the random uuids of their own prepare: only A0r is affected at spec 10
        self.a0_churn = {p.parent.name for p in self.out.glob("rescore-A0/*/churn.json") if (jl(p) or {}).get("all_churn")}
        if twin:
            e = jl(STORE / "experiments" / twin / "experiment.json") or {}
            self.ids.update({arm_of(m["name"]): m["id"] for m in e.get("methods", []) if arm_of(m["name"])})
            self.arms = [a for a in ("A0", "A0r", "A", "A2", "B", "C", "D", "E") if a in ("A0", "A0r", "B") or a in self.ids]

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
        if b in self.drop.get(arm, ()):     # --drop ARM:BOARD (a known artefact, reported)
            self.src[arm]["dropped"].add(b)
            return None
        if b in self.churn and self.churn_mode == "exclude":
            self.src[arm]["left out (uuid churn)"].add(b)
            return None
        if arm == "A0r" and b in self.a0_churn:   # A0's outputs against a task of different random uuids
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


SCALE = {"V": 1.0, "mV": 1e-3, "µV": 1e-6, "uV": 1e-6, "nV": 1e-9, "W": 1.0, "mW": 1e-3, "µW": 1e-6, "uW": 1e-6, "nW": 1e-9,
         "pW": 1e-12, "A": 1.0, "mA": 1e-3, "µA": 1e-6, "uA": 1e-6, "K": 1.0, "C": 1.0, "ohm": 1.0, "mohm": 1e-3}


def raw_value(v):
    """A term's displayed value in base units ('980 mV' and '1.1 V' are comparable), dB as a linear amplitude;
    None when it has no number or an unknown unit (the contribution is judged instead)."""
    m = re.match(r"\s*(-?[\d.]+(?:e[-+]?\d+)?)\s*(\S*)", str(v or ""))
    if not m:
        return None
    x, u = float(m.group(1)), m.group(2)
    if u.startswith("dB"):
        return 10 ** (x / 20.0)
    return x * SCALE[u] if u in SCALE else None


def terms(status):
    """{term id: (observable, contribution, raw value or None)}"""
    out = {}
    for t in (status or {}).get("terms") or []:
        if t.get("contribution") is None:
            continue
        out[t["id"]] = (t["obs"], float(t["contribution"]), raw_value(t.get("value")))
    return out


def _cmp(x, y):
    """The two numbers a term is judged on: raw values when both arms have one, else both contributions."""
    return (x[2], y[2]) if x[2] is not None and y[2] is not None else (x[1], y[1])


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
                    xv, yv = _cmp(x, y)
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


NOTCH_DEPTH = "0.05"     # m: the gated column of notch_stats, at gaps below 80 degrees (PLAN.md section 9)


def _tag(D, arm):
    return D.ids[arm][:12] if arm in D.ids else arm


def overhang(D, arm, b):
    """{kind: (entries, mm2)} of a kept board (overhang_diag), None without a measure."""
    j = jl(D.out / "measure" / b / f"{_tag(D, arm)}.overhang_diag.json")
    if j is None:
        return None
    out = defaultdict(lambda: [0, 0.0])
    for e in j.get("entries") or []:
        out[e["kind"]][0] += 1
        out[e["kind"]][1] += float(e["mm2"])
    return out


def notches(D, arm, b):
    """(notches below 80 deg and at least 50 um deep, metres of track) of a kept board, None without a measure."""
    j = jl(D.out / "measure" / b / f"{_tag(D, arm)}.notch_stats.json")
    return None if j is None else (j["notches"][NOTCH_DEPTH]["below80"], j["track_m"])


def _stats(D):
    sys.path.insert(0, str(STORE / "code" / f"kicad-auto-everything@{D.e['harness']['commit'][:12]}" / "bench" / "src"))
    from kaebench import stats as S
    return S


def _repos():
    try:
        rows = [json.loads(l) for l in open(CORPUS / "manifest.jsonl") if l.strip()]
    except OSError:
        return {}
    return {r["id"]: r.get("repo") for r in rows}


def smd_overhang(D, a, b):
    """{board: (n, mm2)} on SMD lands (smd2 + smd) over the boards both arms have."""
    out = {}
    for bd in D.boards:
        x, y = overhang(D, a, bd), overhang(D, b, bd)
        if x is not None and y is not None:
            out[bd] = tuple((sum(o[k][i] for k in ("smd2", "smd") if k in o)) for o in (x, y) for i in (0, 1))
    return out


def overhang_gate(D, ctrl="A", treat="C"):
    """C's SMD overhang against A's: per-board differences (entries; mm2), repository-resampled CI, sign-flip p.
    Fails when either difference is positive and its CI excludes 0."""
    S, cl = _stats(D), _repos()
    d = smd_overhang(D, ctrl, treat)
    res = {}
    for name, i in (("entries", 0), ("mm2", 1)):
        diffs = [v[2 + i] - v[i] for v in d.values()]
        if not diffs:
            continue
        ci = S.bootstrap_ci(diffs, [cl.get(b, b) for b in d])
        res[name] = dict(n=len(diffs), control=round(sum(v[i] for v in d.values()), 2),
                         treatment=round(sum(v[2 + i] for v in d.values()), 2), mean_diff=round(st.mean(diffs), 4),
                         ci=[round(x, 4) for x in ci], p=S.sign_flip(diffs), above=sum(x > 0 for x in diffs),
                         below=sum(x < 0 for x in diffs), fail=ci[0] > 0)
    return res


def notch_gate(D, treat="C", ref="human", n_boot=5000):
    """Pooled notches per metre, treatment against reference, boards both have; 95 % CI of the difference by
    resampling repositories. Fails when the CI's lower bound is above 0."""
    cl = _repos()
    rows = []
    for b in D.boards:
        x, y = notches(D, treat, b), notches(D, ref, b)
        if x and y:
            rows.append((cl.get(b, b), x, y))
    if not rows:
        return None
    rate = lambda rs, i: sum(r[i][0] for r in rs) / max(1e-9, sum(r[i][1] for r in rs))
    by = defaultdict(list)
    for r in rows:
        by[r[0]].append(r)
    keys, rng, boots = sorted(by), random.Random(0), []
    for _ in range(n_boot):
        rs = [r for k in rng.choices(keys, k=len(keys)) for r in by[k]]
        boots.append(rate(rs, 1) - rate(rs, 2))
    boots.sort()
    ci = (boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot)])
    return dict(n=len(rows), treat=round(rate(rows, 1), 2), ref=round(rate(rows, 2), 2), diff=round(rate(rows, 1) - rate(rows, 2), 2),
                ci=[round(x, 2) for x in ci], fail=ci[0] > 0)


def sec_dfm(D):
    out = ["## Overhang by land type and exposed acute notches\n"]
    rows = []
    for arm in ["human"] + [a for a in D.arms if a in ("A", "B", "C", "D", "E")]:
        tot = defaultdict(lambda: [0, 0.0])
        n = 0
        for b in D.boards:
            o = overhang(D, arm, b)
            if o is None:
                continue
            n += 1
            for k, v in o.items():
                tot[k][0] += v[0]
                tot[k][1] += v[1]
        if n:
            rows.append([arm, n, sum(v[0] for v in tot.values()), round(sum(v[1] for v in tot.values()), 1)]
                        + [f"{tot[k][0]} / {tot[k][1]:.1f}" for k in ("smd2", "smd", "tht")])
    out.append(table(["arm", "boards", "entries", "mm2", "SMD two-terminal n / mm2", "other SMD n / mm2", "THT n / mm2"], rows))
    out.append("\n| arm | boards | notches < 80 deg, >= 50 um | track m | per m |\n|---|---|---|---|---|")
    for arm in ["human"] + [a for a in D.arms if a in ("A", "B", "C", "D", "E")]:
        v = [x for x in (notches(D, arm, b) for b in D.boards) if x]
        if v:
            out.append(f"| {arm} | {len(v)} | {sum(x[0] for x in v)} | {sum(x[1] for x in v):.1f} | {sum(x[0] for x in v) / sum(x[1] for x in v):.2f} |")
    return "\n".join(out)


def not_worse(D, ctrl, treat):
    """Rows of cp1, clean_strict, completion and DRC errors for a pair: (name, ok, detail)."""
    rows = []
    for name, met, binary, low in (("cp1", lambda s: bool(s.get("clean")), True, -0.02),
                                   ("clean_strict", lambda s: s.get("clean_strict"), True, -0.02),
                                   ("completion", lambda s: float(s.get("completion") or 0), False, -0.005),
                                   ("DRC errors / board", lambda s: float(s.get("errors") or 0), False, None)):
        r = paired(D, met, ctrl, treat, binary)
        if not r:
            rows.append((name, None, "no data"))
            continue
        if low is None:
            ok = r["p"] >= 0.05 or r["diff"] <= 0
        elif binary:
            ok = r["ci"][0] > low and (r["p"] >= 0.05 or r["diff"] > 0)
        else:
            ok = r["ci"][0] > low
        rows.append((name, ok, f"{ctrl} {r['mean_a']} {treat} {r['mean_b']} diff {r['diff']} CI {r['ci']} p {r['p']}"
                     + (f" +{len(r['gained'])}/-{len(r['lost'])}" if binary else "") + f" n {r['n']}"))
    return rows


def geometry_gate(D, ctrl, treat):
    S = _stats(D)
    ga, gc = {b: geo(D.stats(ctrl, b)) for b in D.boards}, {b: geo(D.stats(treat, b)) for b in D.boards}
    bs = [b for b in D.boards if ga[b] and gc[b]]
    if not bs:
        return (None, None, "no stats")
    oa = lambda g: g.get("oblique", 0) + g.get("acute_entries", 0)
    rat = [oa(gc[b]) / oa(ga[b]) for b in bs if oa(ga[b])]
    p = S.sign_flip([oa(gc[b]) - oa(ga[b]) for b in bs])
    med = st.median(rat) if rat else None
    return (med is not None and med < 0.9 and p < 0.05, med,
            f"sum {ctrl} {sum(oa(ga[b]) for b in bs)} {treat} {sum(oa(gc[b]) for b in bs)}, median ratio {f3(med)}, p {p:.4g}, n {len(bs)}")


def physics_rows(D, ctrl, treat):
    vd, by = physics_verdicts(D, treat, ctrl)
    rows = []
    for o in ("loss.copper", "drop.rail"):
        vals, c = by.get(o), vd.get(o)
        if vals:
            rows.append((f"{o}: median at most 1, more signal-better than signal-worse", st.median(vals) <= 1 and c["signal better"] > c["signal worse"],
                         f"median {st.median(vals):.3f}, " + ", ".join(f"{k} {n}" for k, n in sorted(c.items()))))
        else:
            rows.append((o, None, "no data"))
    bad = {o: (c["signal worse"], c["signal better"]) for o, c in vd.items() if c["signal worse"] - c["signal better"] > 2}
    rows.append(("no observable with signal-worse above signal-better by more than 2", not bad, str(bad or "none")))
    return rows


def overhang_rows(D, ctrl, treat):
    g = overhang_gate(D, ctrl, treat)
    if not g:
        return [("overhang on SMD lands", None, "no measures")]
    return [(f"overhang on SMD lands, {n}: no rise beyond noise", not x["fail"],
             f"{ctrl} {x['control']} {treat} {x['treatment']} mean diff {x['mean_diff']} CI {x['ci']} p {x['p']:.3g} boards up {x['above']} down {x['below']}")
            for n, x in g.items()]


def new_types(D, ctrl, treat):
    ta, tc = Counter(), Counter()
    for b in D.boards:
        sa, sc = D.score(ctrl, b), D.score(treat, b)
        if sa and sc:
            ta.update(sa.get("errors_by_type") or {})
            tc.update(sc.get("errors_by_type") or {})
    new = {k: n for k, n in tc.items() if n > 5 and not ta.get(k)}
    return ("no new error type with more than 5 occurrences", not new, str(new or "none"))


def validity(D, *arms):
    inv = {a: [b for b in D.boards if (D.score(a, b) or {}).get("valid") is False] for a in arms}
    return ("check: no invalid outputs", not any(inv.values()), str({a: (len(x), x[:6]) for a, x in inv.items()}))


def _gtable(title, rows):
    return f"### {title}\n\n" + table(["criterion", "verdict", "detail"],
                                        [[n, {True: "PASS", False: "FAIL", None: "no data"}[ok], d] for n, ok, d in rows]) + "\n"


def q1_rows(D):
    S_rows = []
    more_un, more_err, got = [], [], 0
    for b in D.boards:
        sa, sb = D.score("A", b), D.score("B", b)
        if sa and sb:
            got += 1
            if int(sb.get("unconnected") or 0) > int(sa.get("unconnected") or 0):
                more_un.append(b)
            if int(sb.get("errors") or 0) > int(sa.get("errors") or 0):
                more_err.append(b)
    S_rows.append(("no board with more unconnected than A", not more_un if got else None, f"{len(more_un)} of {got}: {more_un[:5]}"))
    S_rows.append(("at most 2 boards with more DRC errors than A", len(more_err) <= 2 if got else None, f"{len(more_err)} of {got}: {more_err[:5]}"))
    r = paired(D, lambda s: bool(s.get("clean")), "A", "B", True)
    if r:
        S_rows.append(("B loses at most 1 clean board", len(r["lost"]) <= 1, f"+{len(r['gained'])}/-{len(r['lost'])}"))
    S_rows += not_worse(D, "A", "B")
    ok, _m, d = geometry_gate(D, "A", "B")
    S_rows.append(("oblique + acute entries fall", ok, d))
    S_rows += overhang_rows(D, "A", "B")
    S_rows += physics_rows(D, "A", "B")
    secs, skipped, n = [], 0, 0
    for b in D.boards:
        rep = last_json(D.log("B", b)) if D.fork_dir("B", b) else None
        if rep:
            n += 1
            skipped += bool((rep.get("parts") or {}).get("skipped"))
            if (rep.get("seconds") or {}).get("total") is not None and (rep.get("estimate_s") or {}).get("total"):
                secs.append(rep["seconds"]["total"] / max(1e-6, rep["estimate_s"]["total"]))
    S_rows.append(("finish median seconds within its estimate", st.median(secs) <= 1 if secs else None, f"median seconds/estimate {f3(st.median(secs)) if secs else '-'}"))
    S_rows.append(("under 5 % of boards with a part skipped for time", skipped / n < 0.05 if n else None, f"{skipped} of {n}"))
    return S_rows


def sec_gates(D):
    """The pre-registered verdicts of PLAN.md sections 4, 9 and 10, computed."""
    arms = set(D.arms)
    out = ["## Pre-registered gates\n"]
    if "A2" in arms:
        out.append(_gtable("Check: A/A twin of A (flips expected from noise alone)", not_worse(D, "A", "A2")))
    if "B" in arms:
        out.append(_gtable("Q1: finish alone (B against A)", q1_rows(D)))
    if {"A", "C"} <= arms:
        rows = not_worse(D, "A", "C") + [new_types(D, "A", "C"), validity(D, "A", "C")]
        ok, _m, d = geometry_gate(D, "A", "C")
        rows.append(("oblique + acute entries fall", ok, d))
        rows += overhang_rows(D, "A", "C")
        n = notch_gate(D)
        rows.append(("notches < 80 deg, >= 50 um, per m: C not above human beyond noise", (not n["fail"]) if n else None,
                     f"C {n['treat']} human {n['ref']} diff {n['diff']} CI {n['ci']} ({n['n']} boards)" if n else "no measures"))
        rows += physics_rows(D, "A", "C")
        out.append(_gtable("Q2: the redesign as the default (C against A)", rows))
    if {"B", "C"} <= arms:
        ok, _m, d = geometry_gate(D, "B", "C")
        out.append(_gtable("Q3: what born-right copper adds (C against B, descriptive)", not_worse(D, "B", "C") + [("entries fall against B", ok, d)]))
    if {"C", "D"} <= arms:
        nw = not_worse(D, "C", "D")
        ok, _m, d = geometry_gate(D, "C", "D")
        ph = physics_rows(D, "C", "D")
        adopt = all(x[1] for x in nw[:3]) and (bool(ok) or all(x[1] for x in ph))
        out.append(_gtable("Q4: import tails (D against C)", nw + [("entries a further 10 % down", ok, d)] + ph
                           + [("ADOPT import_tails (cp1, clean_strict, completion not worse; and entries or physics)", adopt, "")]))
    if {"C", "E"} <= arms:
        nw = not_worse(D, "C", "E")
        vd, _by = physics_verdicts(D, "E", "C", boards=ground_via_boards(D))
        better = [(o, vd[o]["signal better"], vd[o]["signal worse"]) for o in ("supply.peak", "loss.loop_ac") if o in vd]
        hit = any(b >= 2 * max(w, 1) for _o, b, w in better)
        out.append(_gtable("Q5: ground vias before routing (E against C, boards where E laid them)", nw + [
            ("supply.peak or loss.loop_ac: signal-better at least twice signal-worse", hit if better else None, str(better)),
            ("ADOPT escape_ground_vias", all(x[1] for x in nw[:3]) and hit if better else None, f"{len(ground_via_boards(D))} boards")]))
    return "\n".join(out)


def ground_via_boards(D):
    out = []
    for b in D.boards:
        rep = (blocks(D.log("E", b), "report") or [None])[-1] or {}
        if (rep.get("plane_escapes") or {}).get("ground_vias"):
            out.append(b)
    return out


def physics_verdicts(D, arm="C", ref="A", boards=None):
    """({observable: Counter of verdicts}, {observable: [ratios]}) of `arm` against `ref`, as sec_physics judges them."""
    vd, by = defaultdict(Counter), defaultdict(list)
    for b in (D.boards if boards is None else boards):
        x, y = phys_terms(D, arm, b), phys_terms(D, ref, b)
        if not x[0] or not y[0]:
            continue
        for k, xt in x[0].items():
            yt = y[0].get(k)
            if not yt:
                continue
            xv, yv = _cmp(xt, yt)
            if not yv:
                continue
            r = xv / yv
            by[xt[0]].append(r)
            fl = FLOOR.get(xt[0])
            if fl is None:
                vd[xt[0]]["floor ?"] += 1
            elif x[1] and y[1] and xt[3] is not None and yt[3] is not None:
                sd = math.sqrt((xt[3] ** 2 + yt[3] ** 2) / 2)
                if abs(xv - yv) > 2 * max(sd, 1e-12):
                    vd[xt[0]]["signal better" if xv < yv else "signal worse"] += 1
                else:
                    vd[xt[0]]["noise (offsets)"] += 1
            elif abs(r - 1) <= fl:
                vd[xt[0]]["noise"] += 1
            elif abs(r - 1) <= 2 * fl:
                vd[xt[0]]["ambiguous"] += 1
            else:
                vd[xt[0]]["signal better" if r < 1 else "signal worse"] += 1
    return vd, by


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
    ap.add_argument("--section", default="gates,routing,geometry,dfm,physics,hazards,stages")
    ap.add_argument("--churn", choices=("exclude", "stored"), default="exclude",
                    help="boards whose re-score is only uuid churn: left out of every arm, or each run's stored score")
    ap.add_argument("--drop", action="append", metavar="ARM:BOARD", help="leave one arm's score of a board out")
    ap.add_argument("--twin", help="experiment holding the A/A twin (arm A2)")
    ap.add_argument("--arms", help="comma list of arms to report (default: every arm with data)")
    ap.add_argument("--offset-list", help="write the (board, arm) pairs whose physics needs offset-averaging")
    a = ap.parse_args()
    D = Data(a.exp, a.out, a.churn, a.arms.split(",") if a.arms else None, a.twin, a.drop)
    print(f"# route-finish A/B: {a.exp}\n\nArms {', '.join(D.arms)}; methods "
          + ", ".join(f"{k} `{v}`" for k, v in D.ids.items()) + f"; DRC evaluator `{D.drc_eval}`; {len(D.boards)} boards.\n")
    fns = dict(routing=sec_routing, geometry=sec_geometry, physics=lambda d: sec_physics(d, a.offset_list),
               hazards=sec_hazards, stages=sec_stages, dfm=sec_dfm, gates=sec_gates)
    for s in a.section.split(","):
        print(fns[s](D) + "\n")


if __name__ == "__main__":
    main()
