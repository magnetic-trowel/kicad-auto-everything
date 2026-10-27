# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Value of information for an EMI layout decision: what is worth measuring (lens IN).

Round 1 proposed a calibration-coupon panel with one coupon per basis quantity
(research-gaps.md gap 1). This script asks the decision-theoretic question instead:
for a concrete layout decision, which unknown is worth resolving, and how precisely?

Decision (fields-emi-budget.md, case B): a 50 MHz, 3.3 V clock runs 30 mm over L2 GND
(h = 0.2 mm) and crosses a 20 x 0.5 mm slot; the two cables leave from opposite edges of
an 80 mm board. Actions and their costs, in % of one EMC respin (a respin costs 100):
  a0 leave it                                  0
  a1 add a 10 nF stitching cap at the crossing 0.5
  a2 reroute around the slot (45 mm, no slot)  3
  a3 a2 + slow the edge (series R 33 -> 100 ohm) 4
  a4 move one cable connector to the same edge 25
Loss = cost(a) + 100 * [true margin < 0]. The margin comes from round 1's MREMC chain
(fe_emi_budget.py functions, reused), shifted by the unknown offset between that
worst-case model and the real product in its test setup.

Unknowns (priors are round 1's stated uncertainty ranges, not measurements):
  delta_real  real emission below MREMC worst case, U(0, 20) dB      (fields-emi-budget: 6-20 dB typical)
  kappa       share of the slot voltage between cable points, lognormal median 0.18, x2
  slot_model  error of the slot inductance formula, lognormal median 1, x1.5 (Ott l*ln l)
  L_path      stitching-cap path inductance, log-uniform 1-10 nH     (ours 1.2-3 vs Ott 5-10)
  t_r         actual edge, lognormal median 1 ns, x1.5 (IBIS corner spread)
  C_load      U(5, 15) pF
  same_edge   attenuation of moving a cable to the same edge, U(35, 60) dB (PEEC 43-63)

Prints the prior-optimal action, EVPI, EVPPI per unknown (binning estimator), EVSI of an
imperfect pre-scan, the decision-flip threshold on delta_real, and how the VOI changes
when rerouting is impossible, with a solid plane, with a 2 mm slot (merged antipads)
whose cost two models dispute (slot-line formula vs Ott-data fit) at two prices of the
robust fix, and with cables already on one edge.

Run:  python tools/research/physics/in_emi_voi.py     (~10 s, numpy)
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe_emi_budget as fe  # noqa: E402  (round-1 EMI chain, reused unchanged)

R_FAIL = 100.0
N = 200_000
H, LT, W = 0.2e-3, 30e-3, 80e-3
F0, A, DUTY = 50e6, 3.3, 0.5


def sample(rng, n=N):
    lu = lambda lo, hi: np.exp(rng.uniform(math.log(lo), math.log(hi), n))
    ln = lambda med, fac: med * np.exp(rng.normal(0, math.log(fac), n))
    # Short slots (l < 25 h) are outside the slot-line formula's validity range. Two models
    # disagree there: the formula (factor ~1) and the Ott-data fit dV ~ l ln(l / 2.3 mm),
    # which says a 2 mm slot costs almost nothing (factor ~0.05). Prior: 50/50.
    slotline = (rng.random(n) < 0.5).astype(float)
    return {
        "delta_real": rng.uniform(0, 20, n),
        "kappa": ln(0.18, 2.0),
        "slot_model": ln(1.0, 1.5),
        "L_path": lu(1e-9, 10e-9),
        "t_r": ln(1e-9, 1.5),
        "C_load": rng.uniform(5e-12, 15e-12, n),
        "same_edge": rng.uniform(35, 60, n),
        "short_slot_is_slotline": slotline,
        "short_slot_factor": np.where(slotline > 0, ln(1.0, 1.5), ln(0.05, 2.0)),
    }


def worst_margin(th, *, lt=LT, slot=True, cap=False, rs=33.0, tr_mult=1.0, same_edge=False, slot_len=20e-3,
                 factor_key="slot_model"):
    """Worst MREMC margin (dB) over harmonics 30 MHz-1 GHz, vectorized over samples."""
    n_h = np.arange(1, int(1e9 / F0) + 1)
    f = n_h * F0
    keep = f >= 30e6
    n_h, f = n_h[keep], f[keep]
    w = 2 * math.pi * f[None, :]
    tr = (th["t_r"] * tr_mult)[:, None]
    C = th["C_load"][:, None]
    Vn = 2 * A * DUTY * np.abs(np.sinc(n_h * DUTY))[None, :] * np.abs(np.sinc(n_h[None, :] * tr * F0))
    In = Vn * w * C / np.sqrt(1 + (w * rs * C) ** 2)
    Z = 1j * w * fe.mremc_lret(H, lt, W / 2, W / 2)
    if slot:
        Ls = fe.slot_inductance(slot_len, 0.5e-3) * th[factor_key][:, None]
        Zs = 1j * w * Ls
        if cap:
            Zc = 1j * w * th["L_path"][:, None] + 1 / (1j * w * 10e-9) + 0.03
            Zs = Zs * Zc / (Zs + Zc)
        Z = Z + th["kappa"][:, None] * Zs
    Vcm = np.abs(Z) * In
    if same_edge:
        Vcm = Vcm * 10 ** (-th["same_edge"][:, None] / 20)
    fac = np.array([fe.fmax_factor(x) * 0.55 * fe.cable_factor(x) for x in f])[None, :]
    lim = np.array([fe.cispr32_b_3m(x) for x in f])[None, :]
    E_db = 20 * np.log10(np.maximum(fac * Vcm, 1e-30) * 1e6)
    return np.min(lim - E_db, axis=1)


def actions(th, scenario):
    """Loss matrix (samples x actions) for a scenario."""
    if scenario == "cables on one edge already":
        acts = {"a0 leave it": (0.0, dict(slot=True, same_edge=True)),
                "a1 stitching cap": (0.5, dict(slot=True, cap=True, same_edge=True))}
    elif scenario == "solid plane (no slot)":
        acts = {"a0 leave it": (0.0, dict(slot=False)),
                "a3' slow the edge": (1.0, dict(slot=False, rs=100.0)),
                "a4 cables to one edge": (25.0, dict(slot=False, same_edge=True))}
    elif scenario.startswith("2 mm slot"):
        fix_cost = float(scenario.split("fix costs ")[1])
        sl = dict(slot=True, slot_len=2e-3, factor_key="short_slot_factor")
        acts = {"a0 leave it": (0.0, sl),
                "a3'' leave it, slow the edge": (1.0, {**sl, "rs": 100.0}),
                "a5 close the gap": (fix_cost, dict(slot=False)),
                "a4 cables to one edge": (25.0, {**sl, "same_edge": True})}
    else:
        acts = {"a0 leave it": (0.0, dict(slot=True)),
                "a1 stitching cap": (0.5, dict(slot=True, cap=True)),
                "a2 reroute around slot": (3.0, dict(slot=False, lt=45e-3)),
                "a3 reroute + slow edge": (4.0, dict(slot=False, lt=45e-3, rs=100.0)),
                "a4 cables to one edge": (25.0, dict(slot=True, same_edge=True))}
        if scenario == "no room to reroute":
            acts = {k: v for k, v in acts.items() if not k.startswith(("a2", "a3"))}
    names = list(acts)
    loss = np.empty((len(th["t_r"]), len(names)))
    for j, nm in enumerate(names):
        cost, kw = acts[nm]
        m = worst_margin(th, **kw) + th["delta_real"]
        loss[:, j] = cost + R_FAIL * (m < 0)
    return names, loss


def evppi(loss, x, bins=40):
    """E[min_a E[L | x]]-based EVPPI by quantile binning of one unknown (or a noisy reading of it)."""
    order = np.argsort(x)
    chunks = np.array_split(order, bins)
    with_info = np.mean([loss[c].mean(axis=0).min() for c in chunks])
    return loss.mean(axis=0).min() - with_info


def report(scenario, th, rng):
    names, loss = actions(th, scenario)
    el = loss.mean(axis=0)
    best = int(np.argmin(el))
    evpi = el.min() - loss.min(axis=1).mean()
    print(f"\n== {scenario}")
    print("  expected loss per action (respin = 100): " +
          ", ".join(f"{nm} {v:.1f}" for nm, v in zip(names, el)))
    print(f"  prior-optimal: {names[best]} ({el[best]:.1f}); EVPI {evpi:.1f}")
    rows = []
    for key in th:
        rows.append((evppi(loss, th[key]), key))
    rows.append((evppi(loss, th["kappa"] * th["slot_model"]), "kappa x slot_model (PEEC + slot coupon)"))
    for v, key in sorted(rows, reverse=True):
        print(f"    EVPPI {key:40s} {v:6.2f}")
    if "delta_real" in th:
        for noise in (3.0, 6.0):
            z = th["delta_real"] + rng.normal(0, noise, len(th["delta_real"]))
            print(f"    EVSI pre-scan of delta_real with {noise:.0f} dB rms error   {evppi(loss, z):6.2f}")
        # decision-flip threshold on delta_real: best action per delta_real bin
        edges = np.arange(0, 21, 2.0)
        seq = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            m = (th["delta_real"] >= lo) & (th["delta_real"] < hi)
            seq.append(f"{lo:.0f}-{hi:.0f} dB: {names[int(np.argmin(loss[m].mean(axis=0)))].split()[0]}")
        print("    best action by delta_real bin: " + "; ".join(seq))


def main():
    rng = np.random.default_rng(2026)
    th = sample(rng)
    for scenario in ("slot crossing, all actions", "no room to reroute", "solid plane (no slot)",
                     "2 mm slot (merged antipads), fix costs 2", "2 mm slot (merged antipads), fix costs 15",
                     "cables on one edge already"):
        report(scenario, th, rng)


if __name__ == "__main__":
    main()
