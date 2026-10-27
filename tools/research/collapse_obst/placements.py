# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Obstruction measures on our placements vs the human placement.

    python placements.py extract            # kicad_io extract of attempt-0 outputs (serial)
    python placements.py analyze            # -> kae-work/collapse_obst/placements.json
    python placements.py report             # markdown tables
    python placements.py heat id [id...]    # human vs pnr-seq-v5 vs pnr-combo-v5 maps
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import obst  # noqa: E402
import placecost as pc  # noqa: E402
import run_all  # noqa: E402

ROOT = run_all.ROOT
RUNS = ("pnr-seq-v5", "pnr-combo-v5")
EXTR = os.path.join(run_all.WORK, "ext_runs")
OUTJ = os.path.join(run_all.WORK, "placements.json")


def attempts(run):
    out = {}
    for a in glob.glob(os.path.join(ROOT, "kae-work/results", run, "*/place/*/attempt-0")):
        out[a.rstrip("/").split("/")[-2]] = a
    return out


def board_of(run, tid):
    task = json.load(open(os.path.join(run_all.TASKS, tid, "task.json")))
    st = task["reference"]["stats"]
    if run == "human":
        d = json.load(open(os.path.join(run_all.EXT, tid + ".json")))
        return obst.Board(d, os.path.join(run_all.TASKS, tid, "reference/board.kicad_pcb"), st)
    d = json.load(open(os.path.join(EXTR, run, tid + ".json")))
    # same design rules as the reference: take the min routed width from the reference board
    return obst.Board(d, os.path.join(run_all.TASKS, tid, "reference/board.kicad_pcb"), st)


def capacity(B, L):
    return {key: pc.capacity_board(B, L, circles=True, key=key) for key in ("all", "nopour")}


def buses(B, pairs):
    res = []
    for fa, fb, n in pairs:
        bo = pc.best_orientations(B, fa, fb, mirror=False)
        if bo is None:
            continue
        cur, best, table = bo
        _, bestm, _ = pc.best_orientations(B, fa, fb, mirror=True)
        worst = max(table, key=lambda t: (t[1], t[2]))
        res.append(dict(a=B.fps[fa]["ref"], b=B.fps[fb]["ref"], nets=n, lds=cur["lds"],
                        forced=cur["forced_2layer"], best_lds=best[1], best_forced=best[2],
                        best_lds_mirror=bestm[1], worst_lds=worst[1],
                        rot=(B.fps[fa]["rot"], B.fps[fb]["rot"])))
    return res


def analyze():
    ids = [l.strip() for l in open(os.path.join(ROOT, "kae-work/ab33.txt")) if l.strip()]
    atts = {r: attempts(r) for r in RUNS}
    out = {}
    for tid in ids:
        task = json.load(open(os.path.join(run_all.TASKS, tid, "task.json")))
        L = task["reference"]["stats"]["copper_layers"]
        Bh = board_of("human", tid)
        pairs = pc.pairs_board(Bh, 4)
        rec = dict(L=L, split=task["split"], human=dict(cap=capacity(Bh, L), buses=buses(Bh, pairs)))
        for run in RUNS:
            if tid not in atts[run] or not os.path.exists(os.path.join(EXTR, run, tid + ".json")):
                continue
            a = json.load(open(os.path.join(atts[run][tid], "attempt.json")))
            pr = (a.get("probe") or {}).get("score") or {}
            B = board_of(run, tid)
            assert [f["ref"] for f in B.fps] == [f["ref"] for f in Bh.fps]
            rec[run] = dict(cap=capacity(B, L), buses=buses(B, pairs),
                            legal=a["score"].get("legal"), unconnected=pr.get("unconnected"),
                            completion=pr.get("completion"), errors=pr.get("errors"),
                            hpwl_ratio=a["score"].get("hpwl_ratio"))
        out[tid] = rec
        print(tid, flush=True)
    json.dump(out, open(OUTJ, "w"), default=float)


def report():
    D = json.load(open(OUTJ))
    print(f"{len(D)} boards\n")
    print("| placement | boards | unrouted (probe unconnected>0) | median max demand | "
          "boards max demand > human | mean cuts d>=0.5 | median p99 demand |")
    print("|---|---|---|---|---|---|---|")
    hm = {t: r["human"]["cap"]["all"]["max_demand"] for t, r in D.items()}
    print(f"| human | {len(D)} | 0 (reference) | {np.median(list(hm.values())):.2f} | - | "
          f"{np.mean([r['human']['cap']['all']['cuts_d50'] for r in D.values()]):.1f} | "
          f"{np.median([r['human']['cap']['all']['p99_demand'] for r in D.values()]):.2f} |")
    for run in RUNS:
        rs = {t: r[run] for t, r in D.items() if run in r}
        unr = [t for t, r in rs.items() if (r["unconnected"] or 0) > 0]
        gt = sum(r["cap"]["all"]["max_demand"] > hm[t] + 1e-9 for t, r in rs.items())
        print(f"| {run} | {len(rs)} | {len(unr)} | "
              f"{np.median([r['cap']['all']['max_demand'] for r in rs.values()]):.2f} | {gt} | "
              f"{np.mean([r['cap']['all']['cuts_d50'] for r in rs.values()]):.1f} | "
              f"{np.median([r['cap']['all']['p99_demand'] for r in rs.values()]):.2f} |")
    # does extra demand go with routing failure?
    print("\n**Routing failure vs capacity (ours minus human, all nets)**\n")
    print("| run | group | n | median d_max ours/human | share with ours > human | "
          "median cuts d>=0.5 (ours - human) | any cut over L layers |")
    print("|---|---|---|---|---|---|---|")
    for run in RUNS:
        for name, cond in (("unrouted", lambda r: (r["unconnected"] or 0) > 0),
                           ("routed", lambda r: (r["unconnected"] or 0) == 0)):
            rows = [(t, r) for t, r in D.items() if run in r and cond(r[run])]
            if not rows:
                continue
            ratio = [r[run]["cap"]["all"]["max_demand"] / max(r["human"]["cap"]["all"]["max_demand"], 1e-9)
                     for t, r in rows]
            share = np.mean([x > 1 + 1e-9 for x in ratio])
            dc = [r[run]["cap"]["all"]["cuts_d50"] - r["human"]["cap"]["all"]["cuts_d50"] for t, r in rows]
            over = sum(r[run]["cap"]["all"]["cuts_over"] > 0 for t, r in rows)
            print(f"| {run} | {name} | {len(rows)} | {np.median(ratio):.2f} | {share:.2f} | "
                  f"{np.median(dc):.0f} | {over} |")
    # correlation of unconnected with demand ratio
    for run in RUNS:
        xs, ys = [], []
        for t, r in D.items():
            if run in r and r[run]["unconnected"] is not None:
                xs.append(r[run]["cap"]["all"]["max_demand"] / max(r["human"]["cap"]["all"]["max_demand"], 1e-9))
                ys.append(r[run]["unconnected"])
        from scipy.stats import spearmanr
        rho, p = spearmanr(xs, ys)
        print(f"\n{run}: Spearman(d_max ratio ours/human, unconnected) = {rho:.2f} (p={p:.2f}, n={len(xs)})")
    # per board table
    print("\n| board | L | human d_max | " + " | ".join(f"{r} d_max (unconn)" for r in RUNS) + " |")
    print("|---|---|---|" + "---|" * len(RUNS))
    for t, r in sorted(D.items(), key=lambda kv: -kv[1]["human"]["cap"]["all"]["max_demand"]):
        cells = []
        for run in RUNS:
            if run in r:
                cells.append(f"{r[run]['cap']['all']['max_demand']:.2f} ({r[run]['unconnected']})")
            else:
                cells.append("-")
        print(f"| {t[:40]} | {r['L']} | {r['human']['cap']['all']['max_demand']:.2f} | " + " | ".join(cells) + " |")
    # buses
    print("\n**Bus orientation (pairs of parts joined by >= 4 two-pin nets)**\n")
    print("| placement | buses | boards | LDS-optimal rotation pair | mean LDS | mean best LDS | "
          "mean worst LDS | forced jumpers on 2 layers (sum) | best possible (sum) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for who in ("human",) + RUNS:
        bs = [b for r in D.values() if who in r for b in r[who]["buses"]]
        nb = sum(1 for r in D.values() if who in r and r[who]["buses"])
        if not bs:
            continue
        opt = sum(b["lds"] <= b["best_lds"] for b in bs)
        print(f"| {who} | {len(bs)} | {nb} | {opt} ({opt / len(bs):.0%}) | {np.mean([b['lds'] for b in bs]):.2f} | "
              f"{np.mean([b['best_lds'] for b in bs]):.2f} | {np.mean([b['worst_lds'] for b in bs]):.2f} | "
              f"{sum(b['forced'] for b in bs)} | {sum(b['best_forced'] for b in bs)} |")
    print("\nbuses where ours is worse than human (LDS):")
    for run in RUNS:
        worse = better = same = 0
        for r in D.values():
            if run not in r:
                continue
            for bh, bo in zip(r["human"]["buses"], r[run]["buses"]):
                worse += bo["lds"] > bh["lds"]
                better += bo["lds"] < bh["lds"]
                same += bo["lds"] == bh["lds"]
        print(f"  {run}: worse {worse}, same {same}, better {better}")
    print("\nper bus (human / seq / combo LDS, best):")
    for t, r in D.items():
        for i, bh in enumerate(r["human"]["buses"]):
            ours = [r[run]["buses"][i]["lds"] if run in r else "-" for run in RUNS]
            print(f"  {t[:35]} {bh['a']}-{bh['b']} n={bh['nets']} human {bh['lds']} ours {ours} best {bh['best_lds']}"
                  f" worst {bh['worst_lds']}")


def buses_human(min_nets=4):
    """Bus orientation on the human placement of every prepared board."""
    bs, nb = [], 0
    for tid in run_all.task_ids():
        B = board_of("human", tid)
        pairs = pc.pairs_board(B, min_nets)
        if pairs:
            nb += 1
            for b in buses(B, pairs):
                b["id"] = tid
                bs.append(b)
    json.dump(bs, open(os.path.join(run_all.WORK, "buses_human.json"), "w"), default=float)
    opt = sum(b["lds"] <= b["best_lds"] for b in bs)
    optm = sum(b["lds"] <= b["best_lds_mirror"] for b in bs)
    print(f"{len(bs)} buses on {nb} boards; human rotation pair LDS-optimal: {opt} ({opt / len(bs):.0%}); "
          f"optimal incl. mirror: {optm} ({optm / len(bs):.0%})")
    print(f"mean LDS human {np.mean([b['lds'] for b in bs]):.2f}, best {np.mean([b['best_lds'] for b in bs]):.2f}, "
          f"worst {np.mean([b['worst_lds'] for b in bs]):.2f}; forced 2-layer jumpers human "
          f"{sum(b['forced'] for b in bs)} vs best {sum(b['best_forced'] for b in bs)}")
    worst_rank = sum(b["lds"] >= b["worst_lds"] and b["worst_lds"] > b["best_lds"] for b in bs)
    print(f"human at the worst rotation (where rotation matters): {worst_rank}")
    matters = [b for b in bs if b["worst_lds"] > b["best_lds"]]
    print(f"buses where rotation changes LDS: {len(matters)}; human optimal among those: "
          f"{sum(b['lds'] <= b['best_lds'] for b in matters)}")
    by_n = {}
    for b in bs:
        k = "4-7" if b["nets"] < 8 else ("8-15" if b["nets"] < 16 else "16+")
        by_n.setdefault(k, []).append(b["lds"] <= b["best_lds"])
    print("optimal share by bus width:", {k: f"{np.mean(v):.0%} of {len(v)}" for k, v in by_n.items()})


def heat(ids):
    for tid in ids:
        task = json.load(open(os.path.join(run_all.TASKS, tid, "task.json")))
        L = task["reference"]["stats"]["copper_layers"]
        panels = [(board_of("human", tid), "all", "human")]
        for run in RUNS:
            if os.path.exists(os.path.join(EXTR, run, tid + ".json")):
                panels.append((board_of(run, tid), "all", run))
        run_all.heat_panels(panels, f"{tid}  ({L} copper layers): local layer demand by placement",
                            os.path.join(HERE, "heatmaps", tid + "-placements.png"))


def main():
    op = sys.argv[1]
    if op == "extract":
        for run in RUNS:
            os.makedirs(os.path.join(EXTR, run), exist_ok=True)
            for tid, a in sorted(attempts(run).items()):
                out = os.path.join(EXTR, run, tid + ".json")
                src = os.path.join(a, "output/board.kicad_pcb")
                if os.path.exists(out) or not os.path.exists(src):
                    continue
                subprocess.run(["/usr/bin/python3", os.path.join(ROOT, "tools/research/pnr/kicad_io.py"),
                                "extract", src, out], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    elif op == "analyze":
        analyze()
    elif op == "report":
        report()
    elif op == "heat":
        heat(sys.argv[2:])
    elif op == "buses_human":
        buses_human()


if __name__ == "__main__":
    main()
