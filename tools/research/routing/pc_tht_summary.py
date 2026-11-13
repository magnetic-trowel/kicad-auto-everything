# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize the THT-neck A/B: finish (kae.route.cli finish) on route-finish-ab stage 2's arm A boards with
the base code and with power copper's THT neck, measured per board.

    python3 tools/research/routing/pc_tht_summary.py OUTDIR [--arms base,tht]

OUTDIR/<board>/<arm>.finish.json (finish report), <arm>.ovd.json (overhang_diag), <arm>.stats.json (taut
stats), phys/<arm>.status.json (kae.intent status). Prints a per-board table and totals: THT and SMD overhang
mm^2, DRC errors/unconnected and the types that differ, entries kept/planned, loss.copper, the worst
drop.rail, the hottest temp.junction, heat.track, and the THT hazards."""
import json
import re
import statistics
import sys
from pathlib import Path


def _j(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def _num(v):
    m = re.match(r"\s*(-?[\d.]+(?:e-?\d+)?)\s*(\S*)", str(v or ""))
    if not m:
        return None
    x, u = float(m.group(1)), m.group(2)
    return x * {"V": 1e3, "uV": 1e-3, "W": 1e3, "uW": 1e-3}.get(u, 1.0)     # mV, mW


def phys(st):
    if not st:
        return {}
    t = st.get("terms") or []

    def vals(obs, prefix=None):
        return [v for x in t if x["obs"] == obs and (prefix is None or x["id"].startswith(prefix))
                for v in [_num(x.get("value"))] if v is not None]
    out = {}
    for k, obs, f, pre in (("loss_mW", "loss.copper", max, None), ("drop_mV", "drop.rail", max, None),
                           ("drop_sum_mV", "drop.rail", sum, None), ("tj_C", "temp.junction", max, "T"),
                           ("heat_K", "heat.track", max, None)):
        v = vals(obs, pre)
        if v:
            out[k] = f(v)
    return out


def row(d, arm):
    rep = _j(d / f"{arm}.finish.json") or {}
    ovd = (_j(d / f"{arm}.ovd.json") or {}).get("entries") or []
    st = _j(d / f"{arm}.stats.json") or {}
    o = dict(tht=sum(e["mm2"] for e in ovd if e["kind"] == "tht"),
             smd=sum(e["mm2"] for e in ovd if e["kind"] != "tht"),
             drc=rep.get("drc_out") or {}, drc_in=rep.get("drc_in") or {}, kept=rep.get("kept"), entries=rep.get("entries"),
             obl=(st.get("oblique") or 0) + (st.get("acute_entries") or 0),
             hz={}, secs=(rep.get("seconds") or {}).get("power"))
    for h in rep.get("hazards") or []:
        if str(h.get("code", "")).startswith("tht_"):
            o["hz"][h["code"]] = o["hz"].get(h["code"], 0) + 1
    o.update(phys(_j(d / "phys" / f"{arm}.status.json")))
    return o


def main(argv):
    root = Path(argv[0])
    arms = (argv[argv.index("--arms") + 1] if "--arms" in argv else "base,tht").split(",")
    a, b = arms
    rows = {d.name: {x: row(d, x) for x in arms} for d in sorted(root.iterdir()) if d.is_dir()}
    print(f"| board | THT mm² {a} → {b} | SMD mm² | DRC err/unc {a} → {b} | types differing | kept/entries | "
          f"loss.copper mW | worst drop.rail mV | hottest Tj °C | heat.track K | THT hazards ({b}) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    tot = {x: dict(tht=0.0, smd=0.0, err=0, unc=0) for x in arms}
    ratios = {k: [] for k in ("loss_mW", "drop_mV", "tj_C", "heat_K")}
    for name, r in rows.items():
        x, y = r[a], r[b]
        for arm in arms:
            tot[arm]["tht"] += r[arm]["tht"]
            tot[arm]["smd"] += r[arm]["smd"]
            tot[arm]["err"] += r[arm]["drc"].get("errors") or 0
            tot[arm]["unc"] += r[arm]["drc"].get("unconnected") or 0
        bt_x, bt_y = x["drc"].get("by_type") or {}, y["drc"].get("by_type") or {}
        diff = ", ".join(f"{k} {bt_x.get(k, 0)}→{bt_y.get(k, 0)}" for k in sorted(set(bt_x) | set(bt_y))
                         if bt_x.get(k, 0) != bt_y.get(k, 0)) or "="

        def pv(k, f="{:.1f}"):
            if k not in x or k not in y:
                return "-"
            if x[k] and k in ratios:
                ratios[k].append(y[k] / x[k])
            return f"{f.format(x[k])} → {f.format(y[k])}"
        print(f"| {name[:40]} | {x['tht']:.1f} → {y['tht']:.1f} | {x['smd']:.1f} → {y['smd']:.1f} | "
              f"{x['drc'].get('errors')}/{x['drc'].get('unconnected')} → {y['drc'].get('errors')}/{y['drc'].get('unconnected')} | "
              f"{diff} | {x['kept']}/{x['entries']} → {y['kept']}/{y['entries']} | {pv('loss_mW')} | {pv('drop_mV', '{:.2f}')} | "
              f"{pv('tj_C', '{:.2f}')} | {pv('heat_K', '{:.2f}')} | {y['hz'] or '-'} |")
    print()
    for arm in arms:
        print(f"{arm}: THT {tot[arm]['tht']:.1f} mm², SMD {tot[arm]['smd']:.1f} mm², DRC {tot[arm]['err']}/{tot[arm]['unc']}")
    for k, v in ratios.items():
        if v:
            print(f"{k}: median {b}/{a} {statistics.median(v):.3f} over {len(v)} boards, worse on "
                  f"{sum(1 for q in v if q > 1.001)}, better on {sum(1 for q in v if q < 0.999)}")


if __name__ == "__main__":
    main(sys.argv[1:])
