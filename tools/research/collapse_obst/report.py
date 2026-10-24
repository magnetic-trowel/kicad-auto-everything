# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tables for RESULTS.md from kae-work/collapse_obst/bounds/*.json."""
import collections
import glob
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "../../../kae-work/collapse_obst/bounds"))


def rows():
    rs = []
    for f in sorted(glob.glob(os.path.join(OUT, "*.json"))):
        r = json.load(open(f))
        if "error" in r:
            print("ERROR", r["id"], r["error"])
            continue
        rs.append(r)
    return rs


def parts(r, key, nominal=False):
    f = "Lnom" if nominal else "L"
    cut = max(r[f"cut_{k}_{key}"][f] for k in ("line", "circle", "ring"))
    t = r["topo"][key]
    return dict(side=r["side_L"], topo=1 if t["A_peel"] == 1 else 2, cut=int(min(cut, 99)),
                area=r["area"][key]["L"]), max([e[key]["L"] for e in r["escape"]], default=1)


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return float("nan")
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return gt / (len(pos) * len(neg))


def confusion(rs, pred_fn, title):
    acts = sorted({r["L"] for r in rs})
    preds = [pred_fn(r) for r in rs]
    cols = sorted(set(preds))
    print(f"\n**{title}** (rows: actual copper layers, columns: predicted minimum)\n")
    print("| actual \\ predicted | " + " | ".join(str(c) for c in cols) + " | n |")
    print("|---" * (len(cols) + 2) + "|")
    for a in acts:
        cnt = collections.Counter(p for r, p in zip(rs, preds) if r["L"] == a)
        print(f"| {a} | " + " | ".join(str(cnt.get(c, "")) for c in cols) + f" | {sum(cnt.values())} |")
    eq = sum(p == r["L"] for r, p in zip(rs, preds))
    lo = sum(p < r["L"] for r, p in zip(rs, preds))
    hi = sum(p > r["L"] for r, p in zip(rs, preds))
    print(f"\nequal {eq}, below {lo}, above {hi} (of {len(rs)})")
    return preds


def main():
    rs = rows()
    print(f"{len(rs)} boards")
    for key in ("all", "nopour"):
        print(f"\n### net set: {key}")
        confusion(rs, lambda r: max(parts(r, key)[0].values()),
                  f"Rigorous bounds ({key}): max(side, topo-with-vias, cut, area)")
        confusion(rs, lambda r: max(max(parts(r, key)[0].values()), parts(r, key)[1]),
                  f"Rigorous + BGA escape formula ({key})")
        # against signal layers: actual minus inner plane layers
        sigrs = [dict(r, L=r["L"] - r["planes"]) for r in rs]
        confusion(sigrs, lambda r: max(max(parts(r, key)[0].values()), parts(r, key)[1]),
                  f"Rigorous + BGA escape ({key}) vs signal layers (copper layers minus inner plane layers)")
        # binding bound
        bind = collections.Counter()
        for r in rs:
            p, esc = parts(r, key)
            p = dict(p, escape=esc)
            m = max(p.values())
            for k, v in p.items():
                if v == m:
                    bind[k] += 1
        print(f"\nbinding (ties counted for each): {dict(bind)}")
        # against signal layers (actual minus plane layers)
        sig = [r["L"] - r["planes"] for r in rs]
        pe = [max(max(parts(r, key)[0].values()), parts(r, key)[1]) for r in rs]
        print("vs signal layers (L - plane layers): equal %d below %d above %d" % (
            sum(a == b for a, b in zip(pe, sig)), sum(a < b for a, b in zip(pe, sig)),
            sum(a > b for a, b in zip(pe, sig))))
    # cut details
    print("\n### cut bounds by kind (all nets): boards where each kind reaches 2+ / 3+")
    for k in ("line", "circle", "ring"):
        v = [r[f"cut_{k}_all"]["L"] for r in rs]
        print(k, "2+:", sum(x >= 2 for x in v), "3+:", sum(x >= 3 for x in v), "max", max(v))
    # continuous demand per actual layer count
    print("\n### continuous indicators by actual layer count (median [min-max])\n")
    feats = {
        "cut demand d (all, lb pitch)": lambda r: max(r[f"cut_{k}_all"]["d"] for k in ("line", "circle", "ring")),
        "cut demand d (nopour)": lambda r: max(r[f"cut_{k}_nopour"]["d"] for k in ("line", "circle", "ring")),
        "cut demand (nominal pitch)": lambda r: max(r[f"cut_{k}_all"]["dnom"] for k in ("line", "circle", "ring")),
        "area util (layers of copper)": lambda r: r["area"]["all"]["util"],
        "human track area / board area": lambda r: (r["track_mm"] or 0) * r["p_lb"] / r["board_mm2"],
        "BGA escape L (formula)": lambda r: max([e["nopour"]["L"] for e in r["escape"]], default=0),
        "pads per cm2": lambda r: r["pads"] / r["board_mm2"] * 100,
        "inner plane layers (0 by definition on 2L)": lambda r: r["planes"],
        "via-free thickness peel (A, all)": lambda r: r["topo"]["all"]["A_peel"] or 99,
    }
    acts = sorted({r["L"] for r in rs})
    print("| indicator | " + " | ".join(f"L={a}" for a in acts) + " | AUC (4+ vs 2) |")
    print("|---" * (len(acts) + 2) + "|")
    for name, fn in feats.items():
        cells = []
        for a in acts:
            v = np.array([fn(r) for r in rs if r["L"] == a], float)
            cells.append(f"{np.median(v):.2f} [{v.min():.2f}-{v.max():.2f}]")
        A = auc([fn(r) for r in rs if r["L"] >= 4], [fn(r) for r in rs if r["L"] == 2])
        print(f"| {name} | " + " | ".join(cells) + f" | {A:.2f} |")
    # topology summary
    print("\n### topology (via-free)")
    for key in ("all", "nopour"):
        A = collections.Counter(str(r["topo"][key]["A_peel"]) for r in rs)
        W = collections.Counter(str(r["topo"][key]["W_peel"]) for r in rs)
        eu = collections.Counter((r["topo"][key]["A_euler"], r["topo"][key]["W_euler"]) for r in rs)
        print(key, "A_peel", dict(A), "W_peel", dict(W), "euler(A,W)", dict(eu))
    # escape parts
    print("\n### array packages found")
    for r in rs:
        for e in r["escape"]:
            print(r["id"][:45], "L", r["L"], "signal", r["L"] - r["planes"], e["ref"], e["grid"], e["pitch"],
                  "t", e["t_top"], e["t_in"],
                  "depth", e["nopour"]["depth"], "L", e["all"]["L"], e["nopour"]["L"])
    # top demand boards
    print("\n### highest cut demand boards")
    top = sorted(rs, key=lambda r: -max(r[f"cut_{k}_all"]["d"] for k in ("line", "circle", "ring")))[:12]
    for r in top:
        k = max(("line", "circle", "ring"), key=lambda k: r[f"cut_{k}_all"]["d"])
        print(r["id"][:45], "L", r["L"], "planes", r["planes"], "d %.2f" % r[f"cut_{k}_all"]["d"], k,
              r[f"cut_{k}_all"]["where"], "w", r["w_lb"], r["w_src"], "c", r["c_lb"])


if __name__ == "__main__":
    main()
