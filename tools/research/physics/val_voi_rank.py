# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rank the physics-first claims by decision value, and the validation experiments by value per cost.

Used by docs/topics/physics/validation-program.md. Lens IN's framing: a claim is worth testing
in proportion to the decisions it would change. For each claim k, two actions compete: A acts
as if the claim holds, B acts as if it does not (usually today's rule or round 1's view).
With p = P(claim wrong in the way that matters), r_A = regret of A when the claim is wrong and
r_B = regret of B when it is right, the expected value of perfect information is
    EVPI_k = n_k * min(p r_A, (1 - p) r_B)
over n_k decision instances in the horizon (50 boards designed with the system). A test that
settles the claim with probability s recovers about s * EVPI_k. An experiment's value is the
sum over the claims it tests; experiments are ranked by value per cost.

All inputs are elicited judgements [I] in engineer-weeks (EW; one board respin ~ 4 EW), written
next to each claim with the reasoning. The conclusions drawn from this script are the RANKING and
its robustness, not the numbers: a Monte Carlo multiplies every input by a log-uniform factor in
[1/3, 3] (p on the odds scale) and reports each claim's median rank and P(top 3).

Run:  python tools/research/physics/val_voi_rank.py      (numpy, ~5 s)
"""
import math
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np  # noqa: E402

RESPIN = 4.0      # EW
BOARDS = 50       # horizon: boards designed with the system

# id: (claim, decisions [(p_wrong, r_A, r_B, n)], source)
CLAIMS = {
    "THESIS": ("physics-first layout beats competent rule-following on a board's binding budgets",
               [(0.30, 40.0, 0.3 * RESPIN * BOARDS / 1.0 * 0.25, 1)],       # build the core (A) or rules + critics (B)
               "README; user brief"),
    "CRITICS": ("physics critics are trustworthy enough to be optimizer rewards (recall, few false alarms)",
                [(0.30, 10.0, 8.0, 1)],                                     # reward on critics vs report only
                "physics-critics; IN D4 (Goodhart)"),
    "PROXY": ("smooth F1 proxies rank real contenders correctly; F2/F3 only on escalation",
              [(0.20, 0.05 * RESPIN * BOARDS, 15.0, 1)],
              "solver-ladder; IN E2"),
    "LMBAND": ("return spread follows l_m(f) = R_s/(pi mu0 f), not f_x(h): no transition solver; LF exclusion only by topology",
               [(0.15, 8 * 0.5 * RESPIN, 10.0, 1),                          # transition-band solver (12 EW) or closed forms
                (0.15, 0.5 * RESPIN, 0.3, 10)],                             # per precision board: peninsula or plane + distance
               "VP D5, SY, LS; research-gaps gap 2"),
    "DAMPING": ("every excited mode needs a designed loss channel; tuned snubbers; damping is a 15-27 dB ring lever",
                [(0.30, 4.0, 35 * 0.1 * RESPIN, 1),                         # build the modal Q ledger
                 (0.30, 0.05, 0.05 * RESPIN, 35)],                          # per converter: designed damping
                "TH D1, D3"),
    "QSADEQ": ("quasi-static PEEC, sheet and cavity models suffice for board budgets; full-wave only at sign-off",
               [(0.15, 0.05 * RESPIN * BOARDS, 20.0, 1)],
               "solver-ladder; LS"),
    "ROUTER": ("autorouters make DRC-clean boards with physics faults humans avoid",
               [(0.20, 6.0, 0.05 * RESPIN * BOARDS, 1)],
               "physics-critics router audit; user brief"),
    "WIRE": ("stitching pitch follows the wire-medium f_p (about 12 mm screens 2.45 GHz), not lambda/20",
             [(0.15, 0.1 * RESPIN, 0.1, 20)],
             "LS D-C; FE26"),
    "CMBOND": ("close displacement current locally (heatsink to DC-, GND to chassis at the source); chassis-only bonds radiate",
               [(0.20, 0.1 * RESPIN, 0.15 * RESPIN, 15)],
               "CT D2; DR28"),
    "WORLD": ("off-board conductors carry most EMI decision value: model the world node, ask for enclosure and cables",
              [(0.25, 0.1, 0.1 * RESPIN, 40)],
              "IN section 5; CT; SY"),
    "FLOORS": ("real pours carry enough avoidable loss to justify a pour synthesiser",
               [(0.50, 6.0, 2.0, 1)],
               "VP D1"),
    "SHORTSLOT": ("short voids (1-5 mm, merged antipads) under fast nets cost 0.15-0.7 nH, not ~0",
                  [(0.30, 0.1, 0.05 * RESPIN, 30)],
                  "IN section 5; round-1 slot models vs Ott fit"),
    "DUALITY": ("over a plane C_m barely depends on h and guards do not help over thin dielectric",
                [(0.15, 0.05 * RESPIN, 0.05, 30)],
                "SY D1"),
    "PDNLAYER": ("power pours over thin prepreg (GND/GND inner) beat a power plane across the core ~10x at 100 MHz",
                 [(0.20, 0.1, 0.05 * RESPIN, 40)],
                 "LS wire medium; VP D3; round-1 stackup advice"),
    "VIACAP": ("via-cluster inductance follows logarithmic capacity: outer size, not count",
               [(0.10, 0.02, 0.02, 50)],
               "VP D3"),
    "EDGETERM": ("edge RC terminations cut plane-cavity peaks 5-8x",
                 [(0.30, 0.05, 0.1, 5)],
                 "TH D4"),
    "HOTLOOPH": ("hot-loop L versus plane depth (anchored by AN-139, SNVA803, EPC)",
                 [(0.05, 0.05, 0.05, 35)],
                 "pdn-and-commutation"),
}

# experiment: (cost EW, {claim: s})
EXPERIMENTS = {
    "VAL-1 board, two arms + variants": (8.0, {"THESIS": 0.6, "PROXY": 0.3, "DAMPING": 0.6, "WORLD": 0.6, "CMBOND": 0.4,
                                               "PDNLAYER": 0.6, "LMBAND": 0.3, "DUALITY": 0.2, "ROUTER": 0.3}),
    "coupon LM (l_m band)": (0.6, {"LMBAND": 0.8}),
    "coupon FP (stitching f_p)": (0.5, {"WIRE": 0.8, "QSADEQ": 0.2}),
    "coupon CM (bond variants)": (0.6, {"CMBOND": 0.7, "WORLD": 0.2}),
    "coupon SS (short slots)": (0.5, {"SHORTSLOT": 0.8, "QSADEQ": 0.1}),
    "coupon NL (node vs loop, guard)": (0.5, {"DUALITY": 0.8}),
    "coupon VC (via clusters)": (0.2, {"VIACAP": 0.8}),
    "coupon ET (edge terminations)": (0.3, {"EDGETERM": 0.6}),
    "mutation benchmark": (2.0, {"CRITICS": 0.7, "ROUTER": 0.3}),
    "router audit on the harness": (1.0, {"ROUTER": 0.8, "CRITICS": 0.1}),
    "floor census (pilot -> suite)": (0.5, {"FLOORS": 0.7}),
    "cross-solver checks (openEMS, FastHenry)": (3.0, {"QSADEQ": 0.6, "PROXY": 0.4, "SHORTSLOT": 0.3, "WIRE": 0.2}),
}


def evpi(decisions, scale=None):
    tot = 0.0
    for i, (p, ra, rb, n) in enumerate(decisions):
        if scale is not None:
            fp, fa, fb, fn = scale[i]
            odds = p / (1 - p) * fp
            p = odds / (1 + odds)
            ra, rb, n = ra * fa, rb * fb, n * fn
        tot += n * min(p * ra, (1 - p) * rb)
    return tot


def main():
    names = list(CLAIMS)
    base = {k: evpi(CLAIMS[k][1]) for k in names}
    rng = np.random.default_rng(11)
    nmc = 4000
    ranks = {k: [] for k in names}
    for _ in range(nmc):
        vals = {}
        for k in names:
            sc = [tuple(math.exp(rng.uniform(math.log(1 / 3), math.log(3))) for _ in range(4)) for _ in CLAIMS[k][1]]
            vals[k] = evpi(CLAIMS[k][1], sc)
        order = sorted(names, key=lambda k: -vals[k])
        for r, k in enumerate(order):
            ranks[k].append(r + 1)
    print("== claims by decision value (EVPI over 50 boards, engineer-weeks; inputs x/3..x3 for the robustness columns)")
    print("   rank  claim       EVPI EW   median rank [10-90 %]   P(top 3)   claim")
    for i, k in enumerate(sorted(names, key=lambda k: -base[k])):
        rr = np.array(ranks[k])
        print(f"   {i+1:3d}   {k:10s} {base[k]:7.2f}      {np.median(rr):4.0f} [{np.percentile(rr,10):.0f}-{np.percentile(rr,90):.0f}]"
              f"          {np.mean(rr <= 3):5.2f}    {CLAIMS[k][0][:90]}")
    print("\n== experiments by value per cost (value = sum of s x EVPI over the claims each one settles)")
    rows = []
    for e, (cost, cov) in EXPERIMENTS.items():
        v = sum(s * base[k] for k, s in cov.items())
        rows.append((v / cost, v, cost, e, cov))
    for ratio, v, cost, e, cov in sorted(rows, reverse=True):
        top = ", ".join(f"{k} {s:.1f}" for k, s in sorted(cov.items(), key=lambda kv: -kv[1] * base[kv[0]])[:3])
        print(f"   {ratio:5.2f} per EW   value {v:5.2f}   cost {cost:4.1f} EW   {e:42s} ({top})")
    print("\n   reading: claims whose robust action is cheap (WORLD, VIACAP, EDGETERM) carry little value: act, do not test.")


if __name__ == "__main__":
    main()
