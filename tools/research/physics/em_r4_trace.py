# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate R4 on a routed board: the change of every (observer, source) pair that the hops' whole-spectrum
prices predicted, against the change the next refresh's reduced model measured (kae.em.spectral writes
both to WORK/spectral.jsonl).

Absolute changes carry a term no price can: a hop replaces a field-free short whose return already ran
through the planes, and that coupling leaves with it (tools/research/physics/em_r4_check.py). It is the
same for every path of the hop, so with --verify (each net routed twice from one state, physics and plain)
the difference between the two candidates is the comparison that decides a route.

    python em_r4_trace.py WORK/spectral.jsonl
"""
from __future__ import annotations

import json
import sys

import numpy as np


def main(argv=None):
    path = (argv or sys.argv[1:])[0]
    recs = [json.loads(x) for x in open(path)]
    print(f"{len(recs)} refreshes with a prediction")
    print("absolute (each refresh against the one before): pair, dL at 10 MHz actual / predicted (nH), "
          "du at the typical corner linearized actual / predicted")
    for r in recs:
        for p in r["pairs"]:
            if abs(p["dL"]) > 1e-12 or abs(p["dL_pred"]) > 1e-12:
                du = f"{p['du_lin']:+.3f} / {p['du_pred']:+.3f}" if p["du_lin"] is not None else ""
                print(f"  {p['pair'][0][:30]:30s} {p['dL'] * 1e9:+8.3f} / {p['dL_pred'] * 1e9:+8.3f}   {du}")
    # with connection ports (kae.em.hopport) the absolute change is predictable too
    ab10, abu = [], []
    for r in recs:
        mx = max((abs(p["dL"]) for p in r["pairs"]), default=0)
        for p in r["pairs"]:
            if mx and abs(p["dL"]) >= 0.1 * mx:
                ab10.append(p["dL_pred"] / p["dL"])
            if p["du_lin"] is not None and abs(p["du_lin"]) > 1e-3:
                abu.append(p["du_pred"] / p["du_lin"])
    for name, rs in (("absolute dL at 10 MHz (pairs >= 10% of the refresh's largest)", ab10),
                     ("absolute du, typical corner, linearized (|du| > 1e-3)", abu)):
        if rs:
            a_ = np.array(rs)
            print(f"{name}: {len(a_)} ratios, median {np.median(a_):.2f}, within 0.8-1.25: {np.mean((a_ > 0.8) & (a_ < 1.25)):.0%}, "
                  f"sign right: {np.mean(a_ > 0):.0%}")
    print("candidate differences (physics minus plain route of one net from one state):")
    rat10, ratu = [], []
    for a, b in zip(recs[:-1], recs[1:]):
        if a["H_was"] != b["H_was"]:
            continue
        for pa, pb in zip(a["pairs"], b["pairs"]):
            if pa["pair"] != pb["pair"]:
                continue
            act = np.array(pa["dZ_re"]) + 1j * np.array(pa["dZ_im"]) - np.array(pb["dZ_re"]) - 1j * np.array(pb["dZ_im"])
            pre = np.array(pa["pred_re"]) + 1j * np.array(pa["pred_im"]) - np.array(pb["pred_re"]) - 1j * np.array(pb["pred_im"])
            dl, pl = pa["dL"] - pb["dL"], pa["dL_pred"] - pb["dL_pred"]
            line = f"  {pa['pair'][0][:30]:30s} dL(10 MHz) {dl * 1e9:+8.4f} pred {pl * 1e9:+8.4f} nH"
            if abs(dl) > 1e-12:
                line += f" ratio {pl / dl:6.3f}"
                rat10.append((abs(dl), pl / dl, pa["pair"][0]))
            if pa["du_lin"] is not None:
                du, pu = pa["du_lin"] - pb["du_lin"], pa["du_pred"] - pb["du_pred"]
                line += f"; du {du:+.4f} pred {pu:+.4f}" + (f" ratio {pu / du:6.3f}" if abs(du) > 1e-9 else "")
                if abs(du) > 1e-9:
                    ratu.append((abs(du), pu / du, pa["pair"][0]))
            k = int(np.argmax(np.abs(act)))
            line += f"; |dZ| peak {abs(act[k]):.2e} at {a['pairs'][0]['f'][k] / 1e6:.1f} MHz, pred/actual there {abs(pre[k] / act[k]) if abs(act[k]) else 0:.3f}"
            print(line)
    for name, rs in (("dL at 10 MHz", rat10), ("du (whole spectrum, typical corner)", ratu)):
        if rs:
            big = [r for r in rs if r[0] >= 0.1 * max(x[0] for x in rs)]
            print(f"{name}: ratios of the {len(big)} largest differences (>= 10% of the largest): "
                  + ", ".join(f"{r[1]:.2f}" for r in sorted(big, key=lambda x: -x[0])))


if __name__ == "__main__":
    main()
