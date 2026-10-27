# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Red-team sensitivity of lens IN's 'off-board unknowns carry 33-84% of VOI' (in_emi_voi.py).

Re-runs in_emi_voi.py's own decision model (imported unchanged) with alternative priors:
  base         as published: delta_real ~ U(0, 20) dB, same_edge ~ U(35, 60) dB
  narrow       delta_real ~ U(0, 10) dB (an enclosure class with one earlier scan)
  edge6-30     same_edge ~ U(6, 30) dB (rt_world_cm.py: the board-vs-cable mode remains)
  both         narrow + edge6-30
For the main scenario ('slot crossing') it prints the prior-optimal action, EVPI and the share of
EVPI carried by delta_real (the off-board offset).

Timing check: the published EVSI of a 'first-prototype pre-scan' lets the scan inform the layout
action. On the same board the scan arrives after fabrication. Under the model's own loss
(cost(a) + 100 x [fail]) a respin costs 100 whether it is triggered by the scan or by the formal
test, so a post-build scan of this board is worth ~0 to this decision; its value goes to later
boards in the same enclosure class. Printed as 'post-build EVSI'.

Run: OMP_NUM_THREADS=1 python tools/research/physics/rt_voi_sensitivity.py   (about 1 minute)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import in_emi_voi as iv  # noqa: E402  (lens IN model, unchanged)


def variant(th, rng, name):
    th = dict(th)
    n = len(th["t_r"])
    if name in ("narrow", "both"):
        th["delta_real"] = rng.uniform(0, 10, n)
    if name in ("edge6-30", "both"):
        th["same_edge"] = rng.uniform(6, 30, n)
    return th


def main():
    rng = np.random.default_rng(2026)
    th0 = iv.sample(rng)
    scen = "slot crossing, all actions"
    print(f"== scenario: {scen} (losses in % of one respin)")
    for name in ("base", "narrow", "edge6-30", "both"):
        th = variant(th0, np.random.default_rng(7), name)
        names, loss = iv.actions(th, scen)
        el = loss.mean(axis=0)
        best = int(np.argmin(el))
        evpi = el.min() - loss.min(axis=1).mean()
        share = iv.evppi(loss, th["delta_real"]) / evpi if evpi > 1e-9 else float("nan")
        top = sorted(((iv.evppi(loss, th[k]), k) for k in th), reverse=True)[:3]
        print(f"   {name:9s}: best {names[best]:24s} E[loss] {el[best]:5.1f}; EVPI {evpi:5.1f}; "
              f"delta_real share {share*100:5.1f}%; top EVPPI: " + ", ".join(f"{k} {v:.2f}" for v, k in top))
        # post-build value of a 3 dB pre-scan of THIS board: decide proceed (formal test) or respin now
        z = th["delta_real"] + np.random.default_rng(3).normal(0, 3.0, len(th["delta_real"]))
        fail = loss[:, best] - loss[:, best].min()          # 100 x fail indicator (cost(a*) removed)
        order = np.argsort(z)
        chunks = np.array_split(order, 40)
        # option A: proceed -> expected 100 * P(fail | z); option B: respin now with the best fix (>= 100)
        post = np.mean([min(fail[c].mean(), 100.0 + np.min(el - el.min())) for c in chunks])
        print(f"              post-build EVSI of a 3 dB pre-scan for this board: {fail.mean() - post:5.2f}"
              f" (pre-layout EVSI as published: {iv.evppi(loss, z):5.2f})")


if __name__ == "__main__":
    main()
