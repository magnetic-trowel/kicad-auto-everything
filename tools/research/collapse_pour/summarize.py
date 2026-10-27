# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tables for RESULTS.md (venv Python).

    python summarize.py [--place kae-work/pour/place.json]

Resistance is reported as R_eff = 1 / mean_pairs(1/R_ij), with a disconnected pad pair
counted as zero conductance, next to the number of pads cut off from the largest
group, so no result gains from dropped pads.
Placement study: correlations of the cheap term with the full Laplace R_eff and with the
kae physics cached by tools/research/pnr_phys/physics_score.py in kae-work/phys/
(fast = place terms, routed = recheck on copper, worst rail mOhm) and with routed length
and vias from the harness, all as method/human ratios.
"""
import glob
import json
import os
import sys

import numpy as np
from scipy.stats import spearmanr

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
WORK = os.path.join(ROOT, "kae-work", "pour")
PHYS = os.path.join(ROOT, "kae-work", "phys")


def short(b):
    return "-".join(b.replace("pcbcorpus-", "").split("-")[:2])


def fmt(v, p=2):
    return "inf" if v is None else f"{v:.{p}f}"


def boards_table(tags=("iso_area2", "fill2")):
    print("| board | mode | kernel | net | Cu human / MBO mm2 | R_eff human | R_eff MBO | ratio | cut-off pads h/m | DRC err h/m |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    ratios = {}
    for f in sorted(glob.glob(os.path.join(WORK, "*", "*", "results.json"))):
        tag = os.path.basename(os.path.dirname(f))
        if tag not in tags:
            continue
        r = json.load(open(f))
        hd = r.get("drc_human") or {}
        for k in [k for k in r if k.startswith("net_mbo_")]:
            kern = k[8:]
            md = r.get(f"drc_{kern}") or {}
            # DRC errors not present on the refilled human board (pre-existing excluded)
            extra = {t: md.get(t, 0) - hd.get(t, 0) for t in set(md) | set(hd)}
            extra = {t: v for t, v in extra.items() if v}
            for n, h in r["net_human"].items():
                m = r[k][n]
                ra = (m["R_eff"] / h["R_eff"]) if h.get("R_eff") and m.get("R_eff") else None
                ratios.setdefault((tag, kern), []).append(ra)
                print(f"| {short(r['board'])} | {tag} | {kern} | {n[:12]} | {h['copper_mm2']:.0f} / "
                      f"{m['copper_mm2']:.0f} | {fmt(h.get('R_eff'))} | {fmt(m.get('R_eff'))} | {fmt(ra)} | "
                      f"{h.get('disconnected_pads')}/{m.get('disconnected_pads')} | "
                      f"{sum(hd.values())}/{'+' + str(extra) if extra else 'same'} |")
    for (tag, kern), v in sorted(ratios.items()):
        v = [x for x in v if x]
        if v:
            print(f"\n{tag}/{kern}: geomean R_eff ratio MBO/human = {np.exp(np.mean(np.log(v))):.3f} "
                  f"over {len(v)} nets, better on {sum(x < 0.98 for x in v)}, worse on {sum(x > 1.02 for x in v)}")


def phys_rows():
    out = {}
    for run in ("pnr-seq-v5", "pnr-combo-v5"):
        p = os.path.join(PHYS, f"{run}.json")
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        for bid, v in d["boards"].items():
            if "skip" not in v:
                out[(bid, run)] = v
        for bid, v in d["human"].items():
            out.setdefault((bid, "human"), v)
    return out


def place_table(path):
    res = json.load(open(path))
    rows = []
    for key, row in res.items():
        if "error" in row:
            continue
        bid, who = key.split("|")
        for n, v in row.items():
            f = v["full"]
            rows.append(dict(board=bid, who=who, net=n, R=f.get("R_eff"), disc=f.get("disconnected_pads"),
                             pads=f["pads"], Rw=(v["world"] or {}).get("R_pred"),
                             Ri=(v["world"] or {}).get("R_ideal"), fw=(v["world"] or {}).get("free"),
                             Rr=(v["routed"] or {}).get("R_pred"),
                             spread=(v["world"] or {}).get("spread_mm")))
    ok = [r for r in rows if r["R"] and r["Rw"]]
    print(f"\nplacement study: {len(rows)} (board, placement, pour net) rows; {len(ok)} with a finite R_eff")
    print("| term | n | Spearman vs full R_eff (absolute) | Spearman of ratios to human |")
    print("|---|---|---|---|")
    hum = {(r["board"], r["net"]): r for r in ok if r["who"] == "human"}
    for name, key in (("ideal sheet (pad distances)", "Ri"), ("pour_score on World (pads block)", "Rw"),
                      ("same term on routed board", "Rr"), ("pad spread", "spread"), ("free fraction", "fw")):
        xs = [(r[key], r["R"]) for r in ok if r[key] is not None]
        rx = [(r[key] / hum[(r["board"], r["net"])][key], r["R"] / hum[(r["board"], r["net"])]["R"])
              for r in ok if r["who"] != "human" and (r["board"], r["net"]) in hum and r[key]
              and hum[(r["board"], r["net"])][key]]
        a = spearmanr(*zip(*xs))[0] if len(xs) > 3 else float("nan")
        b = spearmanr(*zip(*rx))[0] if len(rx) > 3 else float("nan")
        print(f"| {name} | {len(xs)}/{len(rx)} | {a:+.2f} | {b:+.2f} |")
    # board level: sum over pour nets, ratio to human, vs physics and length/vias
    ph = phys_rows()
    agg = {}
    for r in rows:
        a = agg.setdefault((r["board"], r["who"]), dict(R=0.0, Rw=0.0, ok=True))
        if r["R"] is None or r["Rw"] is None:
            a["ok"] = False
        else:
            a["R"] += r["R"]
            a["Rw"] += r["Rw"]
    pairs = []
    for (bid, who), a in agg.items():
        if who == "human" or not a["ok"] or (bid, "human") not in agg or not agg[(bid, "human")]["ok"]:
            continue
        h = agg[(bid, "human")]
        pm, phh = ph.get((bid, who)), ph.get((bid, "human"))
        row = dict(board=bid, who=who, R=a["R"] / h["R"], Rw=a["Rw"] / h["Rw"])
        if pm and phh:
            eps = 0.01
            row["fast"] = (pm["place"]["total"] + eps) / (phh["place"]["total"] + eps)
            row["routed"] = (pm["routed"]["total"] + eps) / (phh["routed"]["total"] + eps)
            wr_m, wr_h = pm["routed"].get("worst_rail_mohm"), phh["routed"].get("worst_rail_mohm")
            row["rail"] = (wr_m / wr_h) if wr_m and wr_h else None
            hv = pm.get("harness", {})
            row["length"] = hv.get("length_mm")
            row["vias"] = hv.get("vias")
        pairs.append(row)
    print(f"\nboard level ({len(pairs)} method boards, ratios to human; physics from kae-work/phys)")
    print("| target | n | Spearman with pour_score ratio | Spearman with full R_eff ratio |")
    print("|---|---|---|---|")
    for tgt in ("R", "fast", "routed", "rail", "length", "vias"):
        sel = [p for p in pairs if p.get(tgt) is not None]
        if len(sel) > 3:
            a = spearmanr([p["Rw"] for p in sel], [p[tgt] for p in sel])[0]
            b = spearmanr([p["R"] for p in sel], [p[tgt] for p in sel])[0]
            print(f"| {tgt} | {len(sel)} | {a:+.2f} | {b:+.2f} |")
    print("\n| board | who | sum R_eff / human | pour_score / human | worst rail / human | routed phys / human |")
    print("|---|---|---|---|---|---|")
    for p in sorted(pairs, key=lambda p: (p["board"], p["who"])):
        print(f"| {short(p['board'])} | {p['who']} | {p['R']:.2f} | {p['Rw']:.2f} | {fmt(p.get('rail'))} | {fmt(p.get('routed'))} |")
    for who in ("pnr-seq-v5", "pnr-combo-v5"):
        v = [p["R"] for p in pairs if p["who"] == who]
        if v:
            print(f"{who}: geomean pour R_eff vs human {np.exp(np.mean(np.log(v))):.3f} over {len(v)} boards, "
                  f"worse on {sum(x > 1.02 for x in v)}")
    dis = [r for r in rows if r["disc"]]
    print(f"rows with cut-off pads: {len(dis)} ({', '.join(sorted({short(r['board']) + ':' + r['who'] for r in dis}))})")


if __name__ == "__main__":
    tags = ("iso_area2", "fill2")
    boards_table(tags)
    p = sys.argv[sys.argv.index("--place") + 1] if "--place" in sys.argv else os.path.join(WORK, "place.json")
    if os.path.exists(p):
        place_table(p)
