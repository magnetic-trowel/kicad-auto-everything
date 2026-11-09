#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The pre-registered analysis of the J1 chassis experiment (PLAN.md, Addendum 2).

    analyze.py [--batch EXP[:ATTEMPT] ...] [--arm LABEL=METHOD ...] [--pair ARM:CONTROL ...]
               [--store DIR] [--out FILE] [--selftest]

Each batch is an experiment (boards.txt) and the attempt to read, in order. Numbers come from the run
folders (run.json, evals/<experiment's evaluator>.json), so later attempts count too. Each --pair is
tested on physics and on opens; alpha 0.05 is split over all those tests (Bonferroni).

Physics: x = ln(sum_u_arm / sum_u_control) on boards both arms route fully (0 unconnected, 0 missing, 0
open modules, at least one module). Per batch, with S of n units above ln(theta), the e-value is
2^n B(S+1/2, n-S+1/2) / B(1/2, 1/2); units equal to ln(theta) are dropped; the evidence is the product
over batches, and theta is rejected at evidence >= 1/alpha.
Opens: d = (o_arm - o_control) / (o_arm + o_control + 1); a two-sided hedged-capital confidence sequence
for the mean of d (Waudby-Smith and Ramdas, JRSS B 2024), units in sha256(SEED, board) order within each batch.
"""
import argparse
import hashlib
import json
import math
import os
import random
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

SEED = "j1-chassis-2026-11-08"
S7 = "74fd46c"
ARMS = {"a": f"kae j1 staged {S7} (restarts)", "b": f"kae j1 modules {S7} (restarts)",
        "c": f"kae j1 modules finish {S7} (restarts)", "d": f"kae j1 joint {S7} (restarts)"}
PAIRS = [("b", "d"), ("c", "d")]
LADDER = [("b", "a"), ("c", "b"), ("d", "c"), ("d", "a")]   # descriptive: what each step adds
FLOORS = [(20, 1.12), (30, 1.08), (38, 1.06), (50, 1.05), (60, 1.04), (80, 1.04)]   # J21, excluding identical pairs
MARGIN_PHYS = 1.06
MARGIN_D = 0.03
MARGIN_TOTAL = 0.03
C = 0.75    # truncation of the bets (Waudby-Smith and Ramdas: 1/2 or 3/4)


def floor_for(n):
    """J21's bound for n units: the entry for the next smaller n; None under 20."""
    f = None
    for k, v in FLOORS:
        if n >= k:
            f = v
    return f


def log_e(S, n):
    """ln of the Beta(1/2, 1/2) mixture e-value of S successes in n fair-coin trials."""
    if n == 0:
        return 0.0
    lb = math.lgamma(S + .5) + math.lgamma(n - S + .5) - math.lgamma(n + 1)
    return n * math.log(2) + lb - (2 * math.lgamma(.5) - math.lgamma(1))


def log_evidence(batches, lt):
    """ln of the product over batches of the sign e-values at ln(theta) = lt."""
    tot = 0.0
    for xs in batches:
        kept = [x for x in xs if abs(x - lt) > 1e-12]
        tot += log_e(sum(x > lt for x in kept), len(kept))
    return tot


def physics_test(batches, alpha):
    """batches: lists of x. Returns the rejection flags, the median and the classification inputs."""
    xs = [x for b in batches for x in b]
    nz = [x for x in xs if abs(x) > 1e-9]
    thr = math.log(1 / alpha)
    e1 = log_evidence(batches, 0.0)
    out = dict(n=len(xs), n_nonidentical=len(nz), log_e_at_1=e1, reject_1=e1 >= thr,
               median=math.exp(st.median(xs)) if xs else None)
    m = math.log(MARGIN_PHYS)
    pts = sorted(set(xs))
    hi = [m] + [x for x in pts if x > m] + [(a + b) / 2 for a, b in zip(pts, pts[1:]) if a >= m]
    hi.append((pts[-1] if pts else m) + 1)
    lo = [-m] + [x for x in pts if x < -m] + [(a + b) / 2 for a, b in zip(pts, pts[1:]) if b <= -m]
    lo.append((pts[0] if pts else -m) - 1)
    out["equiv_reject_all"] = bool(xs) and all(log_evidence(batches, t) >= thr for t in hi + lo)
    f = floor_for(len(nz))
    out["floor"] = f
    med = out["median"]
    out["outside_floor"] = bool(f and med is not None and abs(med - 1) > f - 1)
    out["different"] = bool(out["reject_1"] and out["outside_floor"])
    out["equivalent"] = out["equiv_reject_all"]
    return out


def wsr_set(xs, alpha, step=0.0005):
    """Hedged-capital confidence set for the mean of xs in [0, 1] at level alpha, on a grid."""
    lam, sum_x, s2 = [], 0.0, 0.25
    for t, x in enumerate(xs, 1):
        lam.append(math.sqrt(2 * math.log(2 / alpha) / (max(s2 / t, 1e-9) * t * math.log(t + 1))))  # predictable: uses x_1..x_(t-1)
        sum_x += x
        s2 += (x - (0.5 + sum_x) / (t + 1)) ** 2
    keep = []
    for i in range(1, int(round(1 / step))):
        m = i * step
        kp = km = 0.0
        for x, l in zip(xs, lam):
            kp += math.log1p(min(l, C / m) * (x - m))
            km += math.log1p(-min(l, C / (1 - m)) * (x - m))
        if max(kp, km) < math.log(2 / alpha):
            keep.append(m)
    return keep


def opens_test(units, alpha):
    """units: (d, o_arm, o_control) in the pre-registered order."""
    if not units:
        return dict(n=0, different=False, equivalent=False)
    xs = [(d + 1) / 2 for d, _, _ in units]
    keep = wsr_set(xs, alpha)
    lo, hi = (2 * min(keep) - 1, 2 * max(keep) - 1) if keep else (None, None)
    ta, tc = sum(a for _, a, _ in units), sum(c for _, _, c in units)
    ratio = (ta / tc) if tc else None
    excl0 = lo is not None and (lo > 0 or hi < 0)
    within = lo is not None and lo >= -MARGIN_D and hi <= MARGIN_D
    total_ok = ratio is not None and abs(ratio - 1) <= MARGIN_TOTAL
    return dict(n=len(units), cs=(lo, hi), mean_d=st.mean(d for d, _, _ in units), total_arm=ta, total_control=tc, ratio=ratio,
                different=bool(excl0 and ratio is not None and abs(ratio - 1) > MARGIN_TOTAL),
                equivalent=bool(within and total_ok), empty=lo is None)


def signflip_p(xs, reps=20000, seed=0):
    """Two-sided Monte-Carlo sign-flip test of the median (descriptive only)."""
    if not xs:
        return None
    r = random.Random(seed)
    obs = abs(st.median(xs))
    hit = sum(abs(st.median([v if r.random() < .5 else -v for v in xs])) >= obs - 1e-12 for _ in range(reps))
    return (hit + 1) / (reps + 1)


class Store:
    def __init__(self, root):
        self.root = Path(root)

    def exp(self, name):
        d = self.root / "experiments" / name
        e = json.loads((d / "experiment.json").read_text())
        return e, (d / "boards.txt").read_text().split()

    def run(self, bid, mid, att, evs):
        rd = self.root / "boards" / bid / "runs"
        hits = [p for p in rd.glob(f"*.{mid[:8]}.a{att}") if p.is_dir()]
        if not hits:
            return None
        p = hits[0]
        j = json.loads((p / "run.json").read_text())
        ev = p / "evals"
        sc = json.loads((ev / f"{evs['drc']}.json").read_text()).get("score") if (ev / f"{evs['drc']}.json").exists() else None
        ph = json.loads((ev / f"{evs['physics']}.json").read_text()).get("physics") if (ev / f"{evs['physics']}.json").exists() else None
        ok = j.get("status") == "ok" and sc is not None and j.get("task_id") is not None
        task = self.root / "boards" / bid / "tasks" / str(j.get("task_id")) / "task.json"
        split = None
        if task.exists():
            split = (json.loads(task.read_text()).get("record") or {}).get("split")
        rep = None
        for n in ("restart-report-origin.json", "restart-report.json"):
            if (p / n).exists():
                try:
                    rep = json.loads((p / n).read_text())
                except ValueError:
                    pass
                break
        work = j.get("work") or {}
        return dict(board=bid, attempt=att, ok=ok, status=j.get("status"), error=j.get("error"), split=split, runtime=j.get("runtime_s"),
                    clean=bool(sc and sc.get("clean")), valid=bool(sc and sc.get("valid")), legal=sc.get("legal") if sc else None,
                    unconnected=sc.get("unconnected") if sc else None, errors=sc.get("errors") if sc else None,
                    by_type=(sc or {}).get("errors_by_type") or {}, completion=(sc or {}).get("completion") or 0.0,
                    start_open=(sc or {}).get("start_unconnected"), cpu=work.get("cpu_s"), attempts=work.get("attempts"),
                    phys=(ph or {}).get("physics_total"), n_mod=(ph or {}).get("n_modules"), n_miss=(ph or {}).get("n_missing"),
                    n_open=(ph or {}).get("n_open"), report=rep, run=p.name)


def both_routed(a, b):
    def good(r):
        return (r and r["ok"] and r["unconnected"] == 0 and r["n_mod"] and r["n_miss"] == 0 and r["n_open"] == 0 and r["phys"]
                and r["phys"] > 0)
    return good(a) and good(b)


def fmt(v, d=3):
    return "n/a" if v is None else (f"{v:.{d}f}" if isinstance(v, float) else str(v))


def arm_table(data, arms, boards, title):
    out = [f"### {title} ({len(boards)} boards)\n",
           "| arm | ok | no output/fail | cp1 | cpk | completion | opens total (scored) | opens common | DRC errors total | errors common | CPU h total | CPU median s | attempts median |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    common = [b for b in boards if all((data.get((lab, b)) or {}).get("ok") for lab in arms)]
    for lab in arms:
        rs = [data.get((lab, b)) for b in boards]
        ok = [r for r in rs if r and r["ok"]]
        n = len(boards)
        cp1 = sum(1 for r in rs if r and r["clean"]) / n if n else None
        comp = sum((r["completion"] if r and r["ok"] else 0.0) for r in rs) / n if n else None
        co = [data[(lab, b)] for b in common]
        out.append("| " + " | ".join([f"**{lab}**", str(len(ok)), str(n - len(ok)), fmt(cp1), fmt(cp1), fmt(comp),
                                      str(sum(r["unconnected"] or 0 for r in ok)), str(sum(r["unconnected"] or 0 for r in co)),
                                      str(sum(r["errors"] or 0 for r in ok)), str(sum(r["errors"] or 0 for r in co)),
                                      fmt(sum(r["cpu"] or 0 for r in ok) / 3600, 1),
                                      fmt(st.median([r["cpu"] for r in ok if r["cpu"] is not None]), 0) if ok else "n/a",
                                      fmt(st.median([r["attempts"] for r in ok if r["attempts"] is not None]), 0) if ok else "n/a"]) + " |")
    out.append(f"\nCommon boards (every arm scored): {len(common)}. cpk = cp1 at k = 1.\n")
    return out


def type_table(data, arms, boards):
    tot = {lab: Counter() for lab in arms}
    for lab in arms:
        for b in boards:
            r = data.get((lab, b))
            if r and r["ok"]:
                tot[lab].update(r["by_type"])
    types = sorted({t for c in tot.values() for t in c}, key=lambda t: -sum(c[t] for c in tot.values()))
    out = ["### Per-type DRC errors (scored runs, all batches)\n", "| type | " + " | ".join(arms) + " |", "|---" * (len(arms) + 1) + "|"]
    for t in types:
        out.append(f"| {t} | " + " | ".join(str(tot[l][t]) for l in arms) + " |")
    return out + [""]


def loop_table(data, arms, boards):
    out = ["### Joint loop reports (kept attempt, or its fresh origin; descriptive)\n",
           "| arm | reports | iterations median | window iterations median | boards with a window | stop reasons |", "|---|---|---|---|---|---|"]
    for lab in arms:
        reps = [(data.get((lab, b)) or {}).get("report") for b in boards]
        reps = [r for r in reps if r and r.get("iterations") is not None]
        its = [len(r["iterations"]) for r in reps]
        win = [sum(1 for row in r["iterations"] if row.get("iter", 0) > 0 and not row.get("finish")) for r in reps]
        stops = Counter(str(r.get("stop") or "none").split(" (")[0].split(":")[0][:30] for r in reps)
        out.append(f"| {lab} | {len(reps)} | {fmt(st.median(its), 0) if its else 'n/a'} | {fmt(st.median(win), 0) if win else 'n/a'} | "
                   f"{sum(1 for w in win if w > 0)} | {dict(stops)} |")
    return out + [""]


def pair_units(data, batches, arm, ctrl):
    phys, opens, miss = [], [], 0
    for bi, (_, boards) in enumerate(batches):
        p = []
        for b in sorted(boards, key=lambda b: hashlib.sha256((SEED + "\0" + b).encode()).hexdigest()):
            a, c = data.get((arm, b, bi)), data.get((ctrl, b, bi))
            if a and c and a["ok"] and c["ok"]:
                oa, oc = a["unconnected"] or 0, c["unconnected"] or 0
                opens.append(((oa - oc) / (oa + oc + 1), oa, oc))
            elif a or c:
                miss += 1
            if both_routed(a, c):
                p.append(math.log(a["phys"] / c["phys"]))
        phys.append(p)
    return phys, opens, miss


def classify(p, o, tests=()):
    return ("different" if p["different"] and not p["equivalent"] else "equivalent" if p["equivalent"] else "undecided",
            "different" if o["different"] else "equivalent" if o["equivalent"] else "undecided")


def pair_section(data, batches, pairs, alpha):
    lines, verdicts = ["### Pre-registered tests\n"], {}
    lines.append(f"Family alpha 0.05 over {len(pairs) * 2} tests: each at {alpha:.4f} (evidence threshold {1 / alpha:.0f}).\n")
    lines += ["| pair | metric | n (non-identical) | J21 floor | median ratio / CS on d | evidence at θ=1 / mean d | classification | detail |", "|---|---|---|---|---|---|---|---|"]
    for arm, ctrl in pairs:
        phys, opens, miss = pair_units(data, batches, arm, ctrl)
        p = physics_test(phys, alpha)
        o = opens_test(opens, alpha)
        cp, co = classify(p, o)
        verdicts[(arm, ctrl)] = (cp, co, p, o)
        lines.append(f"| {arm} vs {ctrl} | physics | {p['n']} ({p['n_nonidentical']}) | {p['floor']} | {fmt(p['median'])} | ln E = {p['log_e_at_1']:.2f} (thr {math.log(1 / alpha):.2f}) | **{cp}** | reject θ=1 {p['reject_1']}; outside floor {p['outside_floor']}; margin CS {p['equiv_reject_all']} |")
        lines.append(f"| {arm} vs {ctrl} | opens | {o['n']} (missing pair {miss}) | - | CS [{fmt(o.get('cs', (None, None))[0])}, {fmt(o.get('cs', (None, None))[1])}] | mean d {fmt(o.get('mean_d'))}; totals {o.get('total_arm')}/{o.get('total_control')} = {fmt(o.get('ratio'))} | **{co}** | |")
    return lines + [""], verdicts


def describe(data, batches, pairs):
    lines = ["### Paired descriptive (fixed-n sign-flip at the final n; not used for decisions)\n", "| pair | n physics | median ratio | sign-flip p (median) | opens pairs | totals arm/control | mean d |", "|---|---|---|---|---|---|---|"]
    for arm, ctrl in pairs:
        phys, opens, _ = pair_units(data, batches, arm, ctrl)
        xs = [x for b in phys for x in b]
        lines.append(f"| {arm} vs {ctrl} | {len(xs)} | {fmt(math.exp(st.median(xs)) if xs else None)} | {fmt(signflip_p(xs))} | {len(opens)} | "
                     f"{sum(a for _, a, _ in opens)}/{sum(c for _, _, c in opens)} | {fmt(st.mean(d for d, _, _ in opens) if opens else None)} |")
    return lines + [""]


def selftest():
    r = random.Random(0)
    # the e-value of 10 heads in 10 fair flips, closed form
    assert abs(log_e(10, 10) - (10 * math.log(2) + math.lgamma(10.5) + math.lgamma(.5) - math.lgamma(11) - 2 * math.lgamma(.5))) < 1e-9
    # sign e-process and hedged capital: under the null, crossing is rare at any of many looks
    false = 0
    for _ in range(400):
        xs = [r.gauss(0, 1) for _ in range(100)]
        if any(log_evidence([xs[:k]], 0.0) >= math.log(20) for k in range(5, 101, 5)):
            false += 1
    assert false / 400 < 0.05 + 0.03, false
    bad = 0
    for _ in range(100):
        ds = [r.uniform(-0.4, 0.4) for _ in range(60)]
        keep = wsr_set([(d + 1) / 2 for d in ds], 0.05, step=0.005)
        lo, hi = 2 * min(keep) - 1, 2 * max(keep) - 1
        bad += not (lo <= 0 <= hi)
    assert bad / 100 <= 0.05 + 0.05, bad
    # a clear effect is different, near-identical ones equivalent, 3 boards undecided
    big = physics_test([[math.log(0.6) + r.gauss(0, .1) for _ in range(40)]], .0125)
    assert big["different"] and not big["equivalent"], big
    eq = physics_test([[r.gauss(0, .005) for _ in range(120)]], .0125)
    assert eq["equivalent"], eq
    few = physics_test([[0.1, -0.2, 0.3]], .0125)
    assert not few["different"] and not few["equivalent"], few
    # opens: no difference anywhere, totals equal
    o = opens_test([(0.0, 3, 3)] * 500, .0125)
    assert o["equivalent"], o
    o2 = opens_test([(0.5, 3, 1)] * 200, .0125)
    assert o2["different"], o2
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", action="append", default=[])
    ap.add_argument("--arm", action="append", default=[])
    ap.add_argument("--pair", action="append", default=[])
    ap.add_argument("--store", default=os.environ.get("KAE_RESULTS") or str(Path.home() / "kae-baselines"))
    ap.add_argument("--out"), ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    arms = dict(kv.split("=", 1) for kv in a.arm) or dict(ARMS)
    pairs = [tuple(p.split(":")) for p in a.pair] or list(PAIRS)
    batches_arg = a.batch or ["j1-chassis:0"]
    s = Store(a.store)
    alpha = 0.05 / (2 * len(pairs))
    batches, data = [], {}
    lines = ["# J1 chassis: pre-registered analysis (PLAN.md Addendum 2)\n", f"Batches: {batches_arg}. Arms: {arms}. Tests: {pairs}.\n"]
    for bi, spec in enumerate(batches_arg):
        name, _, att = spec.partition(":")
        att = int(att or 0)
        e, boards = s.exp(name)
        ms = {m["name"]: m["id"] for m in e["methods"]}
        batches.append((spec, boards))
        for lab, mname in arms.items():
            for b in boards:
                r = s.run(b, ms[mname], att, e["evaluators"])
                if r:
                    data[(lab, b, bi)] = r
                    data[(lab, b)] = r  # latest batch, used by the per-arm tables
        done = sum(1 for b in boards if all((lab, b, bi) in data for lab in arms))
        lines.append(f"- **{spec}**: {len(boards)} boards, {done} with a run of every arm; evaluators {e['evaluators']}.")
    lines.append("")
    all_b = [b for _, bs in batches for b in bs]
    tests, verdicts = pair_section(data, batches, pairs, alpha)
    lines += arm_table(data, list(arms), all_b, "All boards")
    by_split = defaultdict(list)
    for b in all_b:
        split = next(((data.get((lab, b)) or {}).get("split") for lab in arms if data.get((lab, b))), None)
        by_split[split].append(b)
    for sp in sorted(k for k in by_split if k):
        lines += arm_table(data, list(arms), by_split[sp], f"Split {sp}")
    lines += type_table(data, list(arms), all_b) + loop_table(data, list(arms), all_b) + tests
    desc_pairs = pairs + [p for p in LADDER if p[0] in arms and p[1] in arms and p not in pairs]
    lines += describe(data, batches, desc_pairs)
    undecided = [f"{p[0]} vs {p[1]} {m}" for p, v in verdicts.items() for m, c in zip(("physics", "opens"), v[:2]) if c == "undecided"]
    lines.append(f"## Undecided tests: {undecided or 'none'}\n")
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
