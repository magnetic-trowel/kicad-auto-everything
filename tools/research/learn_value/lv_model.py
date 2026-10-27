# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Train and evaluate the restart value model from lv_gen.py data.

    python lv_model.py kae-work/learnv/data/phys.jsonl --obj phys --out kae-work/learnv/model
    python lv_model.py kae-work/learnv/data/lv.jsonl --obj lv --out kae-work/learnv/model

1. Pairs (running restart a at checkpoint c, other restart b of the same board) ->
   dy = log1p(final cost a) - log1p(final cost b); ridge and gradient boosting.
2. Leave-boards-out: 5 board folds; every number below uses a model that never saw the
   board (out-of-fold).
3. Predictive power: mean within-board Spearman between the score at checkpoint c and the
   restart's final cost, model vs single heuristics (current routed cost, conflicts, ...).
4. Use, simulated at equal CPU: replay each board's logged restarts in random orders under
   jc's restart rule and a budget of B CPU-s; a policy abandons a restart at a checkpoint
   when its dy vs the incumbent exceeds a margin (time spent so far is charged). Margins
   are picked on the other folds' boards (nested), then the result on held-out boards.
5. Exports fold models + margins (meta.json) for lv_jc.jc_value.
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")  # sklearn/OpenMP: one thread (CPU budget, shared machine)
import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lv_policy import CHECKS, PNAMES, VNAMES, pair_x, vec  # noqa: E402

NF = 5
MARGINS = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2]


def load(path, target="cost"):
    """target 'cost' = the restart score of the run's objective; 'route_cost' = routed cost
    only (the length + vias objective, re-targeted from physics-objective trajectories)."""
    boards, runs = {}, defaultdict(dict)
    for l in open(path):
        r = json.loads(l)
        key = r["board"]
        kd = r["kind"]
        if kd == "board":  # a (re)started board: drop rows of an interrupted earlier attempt
            boards[key] = r
            runs[key] = {}
        elif kd == "ck":
            runs[key].setdefault(r["k"], dict(ck={}))["ck"][r["it"]] = r
        elif kd == "end":
            d = runs[key].setdefault(r["k"], dict(ck={}))
            d.update(cost=r[target], T=r["t_run"] - r.get("t_probe", 0.0), its=r["its"],
                     overlap=r["overlap"], unrouted=r["unrouted"])
    out = {}
    for b, rs in runs.items():
        lst = [dict(k=k, **v) for k, v in sorted(rs.items()) if "cost" in v and v["ck"]]
        if len(lst) >= 3 and b in boards:
            for v in lst:
                v["y"] = math.log1p(v["cost"])
                v["last"] = max(v["ck"])
            out[b] = lst
    return boards, out


def folds_of(boards):
    bs = sorted(boards)
    random.Random(7).shuffle(bs)
    return {b: i % NF for i, b in enumerate(bs)}


def inc_feats(run, c):
    last = run["last"]
    cc = min(c, last)
    if cc not in run["ck"]:
        cc = max(x for x in run["ck"] if x <= cc)
    return run["ck"][cc], c > last


def pairs(board, runs, phys_w, rng, max_runs=120, nb=8):
    """Training pairs of one board; each checkpoint gets total weight 1."""
    rs = runs if len(runs) <= max_runs else rng.sample(runs, max_runs)
    X, Y, W = [], [], []
    for c in CHECKS:
        A = [r for r in rs if c in r["ck"]]
        if len(A) < 2:
            continue
        rows = []
        for a in A:
            others = [r for r in rs if r is not a]
            for b in rng.sample(others, min(nb, len(others))):
                fb, done = inc_feats(b, c)
                rows.append((pair_x(a["ck"][c], fb, done, c, board, phys_w), a["y"] - b["y"]))
        for x, y in rows:
            X.append(x)
            Y.append(y)
            W.append(1.0 / len(rows))
    return X, Y, W


def make_model(kind):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    if kind == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                         min_samples_leaf=40, l2_regularization=1.0, random_state=0)


def fit(boards, data, names, phys_w, kind, seed=0):
    rng = random.Random(seed)
    X, Y, W = [], [], []
    for b in names:
        x, y, w = pairs(boards[b], data[b], phys_w, rng)
        X += x
        Y += y
        W += w
    m = make_model(kind)
    X, Y, W = np.array(X), np.array(Y), np.array(W)
    if kind == "ridge":
        m.fit(X, Y, ridge__sample_weight=W)
    else:
        m.fit(X, Y, sample_weight=W)
    return m


def spearman(a, b):
    from scipy.stats import spearmanr
    if len(set(a)) < 2 or len(set(b)) < 2:
        return float("nan")
    return float(spearmanr(a, b).statistic)


def ranking(boards, data, models, folds, phys_w, rng, cs=(0, 2, 5, 12, 30)):
    """Mean within-board Spearman (score vs final cost) at checkpoints cs."""
    heur = ["cur_cost", "conf", "hpwl", "phys", "hist_sum", "overlap", "fv", "ovf"]
    res = {c: defaultdict(list) for c in cs}
    for b, runs in data.items():
        rs = runs if len(runs) <= 150 else rng.sample(runs, 150)
        for c in cs:
            A = [r for r in rs if c in r["ck"]]
            if len(A) < 5:
                continue
            y = [r["y"] for r in A]
            V = np.array([vec(r["ck"][c], phys_w) for r in A])
            for h in heur:
                res[c][h].append(spearman(V[:, VNAMES.index(h)], y))
            for kind, M in models.items():
                m = M[folds[b]]
                refs = rng.sample(rs, min(10, len(rs)))
                X = []
                for a in A:
                    for r in refs:
                        fb, done = inc_feats(r, c)
                        X.append(pair_x(a["ck"][c], fb, done, c, boards[b], phys_w))
                p = m.predict(np.array(X)).reshape(len(A), len(refs)).mean(1)
                res[c]["model_" + kind].append(spearman(p, y))
    return {c: {h: (float(np.nanmean(v)), int(np.sum(~np.isnan(v)))) for h, v in d.items()} for c, d in res.items()}


# ------------------------------------------------------------------ simulation
class Board:
    """Precomputed dy for every (running a, incumbent b, checkpoint c) of a board pool."""

    def __init__(self, board, runs, phys_w, model, rng, max_runs=200):
        self.runs = runs if len(runs) <= max_runs else rng.sample(runs, max_runs)
        self.phys_w = phys_w
        n = len(self.runs)
        self.y = np.array([r["y"] for r in self.runs])
        self.cost = np.array([r["cost"] for r in self.runs])
        self.T = np.array([r["T"] for r in self.runs])
        self.dy = {}
        self.heur = {}
        hi = [VNAMES.index("cur_cost"), VNAMES.index("conf")]
        for c in CHECKS:
            A = [i for i, r in enumerate(self.runs) if c in r["ck"]]
            if not A:
                continue
            X, H = [], []
            for i in A:
                va = vec(self.runs[i]["ck"][c], phys_w)
                for j in range(n):
                    fb, done = inc_feats(self.runs[j], c)
                    X.append(pair_x(self.runs[i]["ck"][c], fb, done, c, board, phys_w))
                    H.append(va[hi] - vec(fb, phys_w)[hi])
            P = model.predict(np.array(X)).reshape(len(A), n) if model is not None else None
            H = np.array(H).reshape(len(A), n, len(hi))
            for t, i in enumerate(A):
                self.dy[(c, i)] = P[t] if P is not None else None
                self.heur[(c, i)] = H[t]
        self.tck = [{c: r["ck"][c]["t_run"] for c in r["ck"]} for r in self.runs]

    def simulate(self, order, B, rule, margin, checks=CHECKS, max_consec=3):
        consec = 0
        t = 0.0
        best = None
        t_full = None
        n_ab = 0
        nrun = 0
        for i in order:
            if best is not None and B - t < 1.1 * t_full:
                break
            nrun += 1
            ab = False
            if best is not None and rule != "none" and consec < max_consec:
                for c in checks:
                    if (c, i) not in self.dy:
                        continue
                    if rule == "model":
                        d = self.dy[(c, i)][best]
                    elif rule == "lift_model":
                        if c != 0:
                            continue
                        d = self.dy[(c, i)][best]
                    elif rule == "heur_cost":
                        d = self.heur[(c, i)][best][0]
                    elif rule == "heur_conf":
                        d = self.heur[(c, i)][best][1]
                    elif rule == "bound":  # current routed cost already above the best final
                        f = self.runs[i]["ck"][c]
                        d = math.log1p(f["route_cost"] + self.phys_w * f["phys"]) - self.y[best]
                    elif rule.startswith("oracle"):  # perfect value at checkpoint c0 (headroom)
                        if c != int(rule[6:] or 0):
                            continue
                        d = self.y[i] - self.y[best]
                    if d > margin:
                        t += self.tck[i][c]
                        ab = True
                        n_ab += 1
                        break
            if ab:
                consec += 1
                continue
            consec = 0
            t += self.T[i]
            t_full = self.T[i]
            if best is None or self.cost[i] < self.cost[best]:
                best = i
        return self.cost[best], nrun, n_ab


def sim_all(sb, rule, margin, B, n_perm=60, seed=0):
    """Per board: mean over random restart orders of log(best_policy / best_jc)."""
    out = {}
    for b, S in sb.items():
        rng = random.Random(seed)
        d, ab, nr = [], [], []
        for _ in range(n_perm):
            order = [rng.randrange(len(S.runs)) for _ in range(3000)]  # bootstrap: pools can be short
            c0, _, _ = S.simulate(order, B, "none", 0)
            c1, n1, a1 = S.simulate(order, B, rule, margin)
            d.append(math.log1p(c1) - math.log1p(c0))
            ab.append(a1)
            nr.append(n1)
        out[b] = (float(np.mean(d)), float(np.mean(nr)), float(np.mean(ab)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--obj", required=True, choices=["phys", "lv"])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "model"))
    ap.add_argument("--budget", type=float, default=None, help="restart CPU-s (jc: 102 phys, 120 lv)")
    ap.add_argument("--perm", type=int, default=60)
    ap.add_argument("--retarget", action="store_true", help="lv from physics data: target = routed cost")
    a = ap.parse_args()
    phys_w = 2.0 if a.obj == "phys" else 0.0
    B = a.budget or (102.0 if a.obj == "phys" else 120.0)
    boards, data = load(a.data, "cost" if a.obj == "phys" or not a.retarget else "route_cost")
    names = sorted(data)
    folds = folds_of(names)
    print(f"{a.obj}: {len(names)} boards, {sum(len(v) for v in data.values())} restarts, "
          f"{sum(len(r['ck']) for v in data.values() for r in v)} checkpoints")
    rng = random.Random(1)
    models = {}
    for kind in ("ridge", "gbm"):
        models[kind] = {f: fit(boards, data, [b for b in names if folds[b] != f], phys_w, kind) for f in range(NF)}
    rk = ranking(boards, data, models, folds, phys_w, rng)
    print("\nwithin-board Spearman (score vs final restart cost), mean over boards [n boards]:")
    keys = list(next(iter(rk.values())).keys())
    print("c   " + " ".join(f"{k[:12]:>13s}" for k in keys))
    for c, d in rk.items():
        print(f"{c:<3d} " + " ".join(f"{d[k][0]:9.3f}[{d[k][1]:2d}]" if k in d else " " * 13 for k in keys))

    # simulation with OOF gbm and ridge
    report = dict(obj=a.obj, B=B, ranking={str(c): d for c, d in rk.items()}, sim={})
    best_kind = None
    for kind in ("gbm", "ridge"):
        sb = {b: Board(boards[b], data[b], phys_w, models[kind][folds[b]], random.Random(3)) for b in names}
        rules = ["model", "lift_model"] + (["heur_cost", "heur_conf", "bound", "oracle0", "oracle5"]
                                           if kind == "gbm" else [])
        for rule in rules:
            tab = {m: sim_all(sb, rule, m, B, a.perm) for m in MARGINS}
            # nested margin choice: for fold f, the margin best on the other folds
            chosen, held = {}, {}
            for f in range(NF):
                tr = [b for b in names if folds[b] != f]
                m_best = min(MARGINS, key=lambda m: np.mean([tab[m][b][0] for b in tr]))
                chosen[f] = m_best
                for b in names:
                    if folds[b] == f:
                        held[b] = tab[m_best][b]
            d = np.array([held[b][0] for b in names])
            name = f"{rule}/{kind}" if rule in ("model", "lift_model") else rule
            report["sim"][name] = dict(gmean_ratio=float(np.exp(d.mean())), better=int((d < -0.005).sum()),
                                       worse=int((d > 0.005).sum()), margins=chosen,
                                       runs=float(np.mean([held[b][1] for b in names])),
                                       aborted=float(np.mean([held[b][2] for b in names])),
                                       per_margin={str(m): float(np.exp(np.mean([tab[m][b][0] for b in names])))
                                                   for m in MARGINS},
                                       per_board={b: held[b] for b in names})
            r = report["sim"][name]
            print(f"sim {name:18s} gmean best-cost ratio vs jc restarts {r['gmean_ratio']:.4f}  "
                  f"better {r['better']} worse {r['worse']}  runs {r['runs']:.1f} aborted {r['aborted']:.1f} "
                  f"margins {chosen}  per-margin {r['per_margin']}")
            if rule == "model" and (best_kind is None or r["gmean_ratio"] < report["sim"][f"model/{best_kind}"]["gmean_ratio"]):
                best_kind = kind
    # export
    out = Path(a.out)
    (out / a.obj).mkdir(parents=True, exist_ok=True)
    import joblib
    for f in range(NF):
        joblib.dump(models[best_kind][f], out / a.obj / f"fold{f}.pkl")
    joblib.dump(fit(boards, data, names, phys_w, best_kind), out / a.obj / "foldall.pkl")
    mp = out / "meta.json"
    meta = json.loads(mp.read_text()) if mp.exists() else {}
    meta[a.obj] = dict(kind=best_kind, folds=folds, margin={str(k): v for k, v in
                                                            report["sim"][f"model/{best_kind}"]["margins"].items()},
                       features=PNAMES)
    meta[a.obj]["margin"]["all"] = float(np.median(list(meta[a.obj]["margin"].values())))
    mp.write_text(json.dumps(meta, indent=1))
    (out / f"report-{a.obj}.json").write_text(json.dumps(report, indent=1))
    # ridge coefficients (standardized) for interpretation
    try:
        rm = fit(boards, data, names, phys_w, "ridge")
        coef = rm[-1].coef_
        top = sorted(zip(PNAMES, coef), key=lambda t: -abs(t[1]))[:10]
        print("ridge top standardized coefficients:", ", ".join(f"{n}={c:+.3f}" for n, c in top))
    except Exception as e:  # pragma: no cover
        print("coef:", e)


if __name__ == "__main__":
    main()
