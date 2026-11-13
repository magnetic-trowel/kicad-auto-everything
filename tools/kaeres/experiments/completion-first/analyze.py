#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""completion-first (PLAN.md): CF vs bestR (primary and physics), Freerouting optimizer time-outs per arm, and
the descriptive staged-only R (phase 1) vs module-clock2's M-clock and M.    python3 analyze.py"""
import collections, glob, json, math, random, statistics as st, sys
from pathlib import Path

BASE = Path.home() / "kae-baselines"
ARMS = {"bestR": "bestR", "CF": "CF"}


def sign_flip(xs, n=50000, seed=0):
    xs = [x for x in xs if x]
    if not xs:
        return 1.0
    rng = random.Random(seed)
    t = abs(sum(xs))
    return (1 + sum(abs(sum(x if rng.random() < 0.5 else -x for x in xs)) >= t - 1e-12 for _ in range(n))) / (n + 1)


def opt_stops(x, out):
    if isinstance(x, dict):
        s_ = x.get("stops")
        if isinstance(s_, dict) and s_.get("optimizer") is not None:
            out.append(str(s_["optimizer"]).lower())
        for v in x.values():
            opt_stops(v, out)
    elif isinstance(x, list):
        for v in x:
            opt_stops(v, out)
    return out


def load(exp, name_of):
    e = json.loads((BASE / "experiments" / exp / "experiment.json").read_text())
    ids = {m["id"][:8]: name_of(m["name"]) for m in e["methods"]}
    D = collections.defaultdict(dict)
    for b in (BASE / "experiments" / exp / "boards.txt").read_text().split():
        for rd in glob.glob(str(BASE / "boards" / b / "runs" / "*.a0")):
            rd = Path(rd)
            mid = rd.name.split(".")[-2]
            if mid not in ids:
                continue
            r = dict(cpu=(json.loads((rd / "run.json").read_text()).get("method_usage") or {}).get("cpu_s") or 0, opt=[])
            for f in rd.glob("evals/*.json"):
                d = json.loads(f.read_text())
                if (d.get("score") or {}).get("valid") is not None:
                    r["s"] = d["score"]
                if d.get("physics"):
                    r["mods"] = d["physics"].get("modules") or {}
            for fn in ("restart-report.json", "restart-report-origin.json"):
                if (rd / fn).exists():
                    opt_stops(json.loads((rd / fn).read_text()), r["opt"])
            if (rd / "restarts.json").exists():
                r["sum"] = json.loads((rd / "restarts.json").read_text())
            if "s" in r:
                D[b][ids[mid]] = r
    return D


def phys(X, Y):
    ok = lambda m: m and m.get("u") is not None and not (m.get("open_hops") or 0)  # noqa: E731
    if X["s"]["unconnected"] or Y["s"]["unconnected"]:
        return None
    c = [k for k in X.get("mods", {}) if ok(X["mods"][k]) and ok(Y.get("mods", {}).get(k))]
    a, b = sum(min(5.0, X["mods"][k]["u"]) for k in c), sum(min(5.0, Y["mods"][k]["u"]) for k in c)
    return math.log(a / b) if c and a > 0 and b > 0 else None


def main(exp="completion-first"):
    D = load(exp, lambda n: n.split()[2])
    B = sorted(b for b in D if "CF" in D[b] and "bestR" in D[b])
    oc = [D[b]["CF"]["s"]["unconnected"] for b in B]
    orr = [D[b]["bestR"]["s"]["unconnected"] for b in B]
    d = [(x - y) / (x + y + 1) for x, y in zip(oc, orr)]
    cc = [bool(D[b]["CF"]["s"].get("clean")) for b in B]
    cr = [bool(D[b]["bestR"]["s"].get("clean")) for b in B]
    print(f"CF vs bestR, {len(B)} boards: opens {sum(oc)} vs {sum(orr)} ({100 * (sum(oc) / max(1, sum(orr)) - 1):+.1f} %), "
          f"mean d {st.mean(d) if d else 0:+.3f}, p {sign_flip(d):.4f}; clean {sum(cc)} vs {sum(cr)} (CF-only {sum(a and not b for a, b in zip(cc, cr))}, "
          f"bestR-only {sum(b and not a for a, b in zip(cc, cr))}); errors {sum(D[b]['CF']['s'].get('errors') or 0 for b in B)} vs "
          f"{sum(D[b]['bestR']['s'].get('errors') or 0 for b in B)}; CPU {sum(D[b]['CF']['cpu'] for b in B) / 3600:.1f} vs "
          f"{sum(D[b]['bestR']['cpu'] for b in B) / 3600:.1f} h")
    xs = [x for x in (phys(D[b]["CF"], D[b]["bestR"]) for b in B) if x is not None and abs(x) > 1e-12]
    if xs:
        print(f"physics CF/bestR: n {len(xs)}, median {math.exp(st.median(xs)):.3f}, p {sign_flip(xs):.4f}")
    for a in ("bestR", "CF"):
        rows = [D[b][a] for b in B]
        print(f"{a}: optimizer timed_out in {sum(any('timed_out' in x for x in r['opt']) for r in rows)} runs; "
              f"second phase {collections.Counter(str((r.get('sum') or {}).get('second')) for r in rows)}")
    # descriptive: staged-only R (phase 1) vs module-clock2's M-clock and M, same allowance and build of R
    M = load("module-clock2", lambda n: {"M": "M", "Mclock": "M-clock"}.get(n.split()[2], "other"))
    p1 = {}
    for b in B:
        ph = ((D[b]["bestR"].get("sum") or {}).get("phases") or [{}])[0].get("rank")
        if ph is not None:
            p1[b] = ph[2] if isinstance(ph, list) and len(ph) > 2 else None   # rank: (illegal, not clean, opens, new errors, outside)
    for arm in ("M-clock", "M"):
        S = [b for b in p1 if p1[b] is not None and arm in M.get(b, {})]
        om = [M[b][arm]["s"]["unconnected"] for b in S]
        orr = [p1[b] for b in S]
        print(f"staged R (phase 1) vs module-clock2 {arm}: {len(S)} boards, opens {sum(orr)} vs {sum(om)} "
              f"({100 * (sum(om) / max(1, sum(orr)) - 1):+.1f} % for {arm}), {arm} fewer/more {sum(x < y for x, y in zip(om, orr))}/"
              f"{sum(x > y for x, y in zip(om, orr))}")


if __name__ == "__main__":
    main(*sys.argv[1:])
