# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize the THT-neck fork of confirm-default-ab: arms A (legacy, stored), N (the default, stored), f0 (finish
with N's code on A's board) and f1 (finish with the short-neck rule on A's board), measured per board.

    python3 tools/research/routing/pc_tht_confirm.py OUTDIR [BASELINES_DIR]

OUTDIR/<board>/<arm>.ovd.json, phys/<arm>.status.json, <arm>.finish.json (f0, f1). DRC by type: the finish
reports' final DRC for f0/f1, the stored kaebench score (errors_by_type) for A and N."""
import glob
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pc_tht_summary import _j, phys  # noqa: E402

ARMS = ("A", "N", "f0", "f1")
RUN = {"A": "591ae9f6", "N": "361bb5d7"}


def drc(root, d, arm, base):
    if arm in RUN:
        for f in glob.glob(f"{base}/boards/{d.name}/runs/*.{RUN[arm]}*.a0/evals/*.json"):
            s = (_j(f) or {}).get("score")
            if s:
                return s.get("errors_by_type") or {}
        return None
    return ((_j(d / f"{arm}.finish.json") or {}).get("drc_out") or {}).get("by_type")


def main(argv):
    root = Path(argv[0])
    base = argv[1] if len(argv) > 1 else str(Path.home() / "kae-baselines")
    tot = {a: dict(tht=0.0, smd=0.0, n=0) for a in ARMS}
    ratios = {(x, k): [] for x in ("A", "N", "f0") for k in ("loss_mW", "drop_mV", "tj_C", "heat_K")}
    worse = {(x, k): [] for x in ("A", "N", "f0") for k in ("loss_mW", "drop_mV", "tj_C", "heat_K")}
    hz, drc_diff = {}, []
    print("| board | THT mm² A / N / f0 / f1 | SMD mm² A / N / f0 / f1 | loss.copper mW N / f1 | drop.rail mV N / f1 | "
          "Tj °C N / f1 | heat.track K N / f1 |")
    print("|---|---|---|---|---|---|---|")
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        r = {}
        for a in ARMS:
            e = (_j(d / f"{a}.ovd.json") or {}).get("entries")
            r[a] = dict(tht=sum(x["mm2"] for x in e if x["kind"] == "tht") if e is not None else None,
                        smd=sum(x["mm2"] for x in e if x["kind"] != "tht") if e is not None else None,
                        **phys(_j(d / "phys" / f"{a}.status.json")))
            if r[a]["tht"] is not None:
                tot[a]["tht"] += r[a]["tht"]
                tot[a]["smd"] += r[a]["smd"]
                tot[a]["n"] += 1
        for h in (_j(d / "f1.finish.json") or {}).get("hazards") or []:
            if str(h.get("code", "")).startswith("tht_"):
                hz[h["code"]] = hz.get(h["code"], 0) + 1
        bf0, bf1 = drc(root, d, "f0", base), drc(root, d, "f1", base)
        if bf0 is not None and bf1 is not None and bf0 != bf1:
            drc_diff.append((d.name, {k: (bf0.get(k, 0), bf1.get(k, 0)) for k in set(bf0) | set(bf1)
                                      if bf0.get(k, 0) != bf1.get(k, 0)}))
        for x in ("A", "N", "f0"):
            for k in ("loss_mW", "drop_mV", "tj_C", "heat_K"):
                if r[x].get(k) and r["f1"].get(k) is not None:
                    q = r["f1"][k] / r[x][k]
                    ratios[(x, k)].append(q)
                    if q > 1.001:
                        worse[(x, k)].append((d.name[:28], round(q, 4)))

        def f(v, n=1):
            return "-" if v is None else f"{v:.{n}f}"

        def pv(k, n=1):
            return f"{f(r['N'].get(k), n)} / {f(r['f1'].get(k), n)}"
        print(f"| {d.name[:40]} | {' / '.join(f(r[a]['tht']) for a in ARMS)} | {' / '.join(f(r[a]['smd']) for a in ARMS)} | "
              f"{pv('loss_mW')} | {pv('drop_mV', 2)} | {pv('tj_C', 2)} | {pv('heat_K', 2)} |")
    print()
    for a in ARMS:
        print(f"{a}: THT {tot[a]['tht']:.1f} mm², SMD {tot[a]['smd']:.1f} mm² over {tot[a]['n']} boards")
    for (x, k), v in ratios.items():
        if v:
            print(f"f1/{x} {k}: median {statistics.median(v):.4f} over {len(v)}, worse {worse[(x, k)]}")
    print("f1 THT hazards:", hz)
    print("DRC types differing f0 -> f1:", drc_diff or "none")


if __name__ == "__main__":
    main(sys.argv[1:])
