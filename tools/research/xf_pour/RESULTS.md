<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# xf_pour: T4 pour-damage maps in jc (experiment C), rounds 2–3

Plan: [transformations.md §T4, §5.3](../../../research_notes/transformations/transformations.md).
All results below use the fixed pnr engine (commit 4c4330a). They are compared with the
`xf3-base-` baselines: joint tasks, ab33, budget 120, 3 seeds.

## What was built
- **`pourmap.py` (`PourMaps`)** computes Dirichlet/Thomson pour-damage maps.
  - E is the first-order relative increase of a net's pour R_eff per removed 0.1 mm cell.
  - The solve runs on a 0.4 mm coarse grid. The region is the zone ∩ board, minus foreign
    halos.
  - Pads are equipotential terminals, and R_eff = 1/mean(1/R_ij), as in netcond.
- **New: layer coupling** (`coupled=True`, `solve_stack`).
  - One sparse solve per net covers all its pour layers. A plated pad is one terminal on
    all its layers.
  - The net's routed vias link consecutive pour layers with netcond's conductance,
    `VIA_G`·(L−1)/gap.
  - E is the net-level relative change, with no per-layer weights. This matches the
    scoring metric (`collapse_pour/netcond.py` is 3-D with via links).
  - It covers B.Cu pours that are fed only through vias. Round 1's per-layer model could
    not handle them.
- **`pjc.py`** subclasses jc and does not edit `collapse_joint/`.
  - The pour map enters part best responses (pour_w) and router costs (route_w). It is
    refreshed at every jc iteration.
  - Plug-ins: `pjc` / `pjc_lv_nopol` use per-layer maps, as in round 1. `pjc2` /
    `pjc2_lv_nopol` use coupled maps.
- **Scoring and scripts:**
  - `gate.py` checks both models on the same cut-outs.
  - `pour_score.py` scores pour R with netcond on the KiCad-refilled output. It stubs
    matplotlib and contourpy.
  - `sweep_table.py`, `sweep.sh` (dev6 weight sweep) and `runs.sh PREFIX` (the 4 ab33 arms).

## Validation gate: passed, and coupling helps
- Setup: 6 phys10 boards, human placement routed by the pnr router.
- 40 random cut-outs per pour (640 in all), each a real part's foreign-pad halo, compared
  with an exact re-solve.
- The gate gave identical numbers on v6.1 and on the fixed engine; the fix touches none of
  these boards.
- Columns are Spearman ρ:
  - u: per-layer map vs per-layer exact.
  - c: coupled map vs coupled exact.
  - u→c: per-layer map vs coupled exact.

| board | pooled u | pooled c | pooled u→c | worst pour u / c / u→c |
|---|---|---|---|---|
| olimex dcdc | 0.991 | 0.991 | 0.955 | GND F 0.978 / 0.974 / 0.973 |
| paw3395 | 0.959 | **0.989** | 0.415 | GND B 0.745 / **0.983** / 0.043 |
| lt6c | 0.968 | 0.974 | 0.913 | GND F 0.960 / 0.961 / 0.957 |
| pmw3360 | 0.925 | **0.963** | 0.934 | GND B 0.488 / **0.794** / 0.612 |
| pmw3610 | 0.991 | 0.979 | 0.982 | GND B – / 0.970 / – |
| noisecard | 0.978 | **0.999** | 0.993 | GND F 0.991 / 0.988 / 0.856 |

- **Coupled maps:** pooled ρ ≥ 0.963 on every board, and 15/16 pours ≥ 0.9.
- **Per-layer maps:** 12/14 pours ≥ 0.9, and they have no map at all for 2 via-fed B.Cu
  pours.
- **Under the coupled truth, the per-layer map misranks via-fed layers**: ρ 0.04 on
  paw3395 B.Cu.
- Maps are lower bounds: median exact/predicted is 2.1–3.6×.
- A coupled refresh costs 0.02–0.3 s.

## Weight
- K = pour_w = route_w = 100 mm of wire per 100 % increase in pour R.
- **K was fixed before any ab33 run**, by a dev6 sweep over K ∈ {30, 100, 300} with the
  coupled maps, 3 seeds, on the old engine (v6.1). Runs: `xf2C-sw-*-dev6`.
- Selection rule: the lowest pour R among the K that keep completion, ties to 100.
- K = 100 won on both objectives: pour R 0.86× and 0.91× on dev6.
  - K = 30 gave 1.24× and 0.98×.
  - K = 300 cost 0.14 completion on the length objective.
- I kept K = 100 on the fixed engine and did not re-tune it.
- dev6 has only 3 (board, net) pour pairs.

## Results (ab33, budget 120, 3 seeds, fixed engine)
- Legal, clean and completion are mean ± sd over seeds.
- Length and vias are summed over the 25 boards that every run and seed completed.
- Physics is phys10, method/human gmean, mean ± sd over 3 seeds.
- Pour R is netcond over the 23 (board, net) pairs with pours. Each pair is a gmean over
  seeds, and the table gives the gmean ratio to the baseline.

| run | legal | clean | clean best-of-3 | completion | length mm | vias | fast phys | routed phys | pour R / base (better/worse) |
|---|---|---|---|---|---|---|---|---|---|
| xf3-base-jc | 1.000 ± 0 | 0.687 ± 0.017 | 0.758 | 0.935 ± 0.002 | 3559 | 57 | 0.96 ± 0.08 | 1.18 ± 0.08 | 1 |
| xf3C-pjc (per-layer) | 1.000 ± 0 | 0.697 ± 0.030 | 0.727 | 0.937 ± 0.003 | 3562 | 56 | 0.90 ± 0.12 | 1.12 ± 0.07 | 0.939 (11/9) |
| **xf3C-pjc2 (coupled)** | 1.000 ± 0 | **0.707 ± 0.046** | 0.758 | 0.936 ± 0.006 | 3555 | 54 | **0.88 ± 0.05** | **1.05 ± 0.05** | **0.839** (14/6) |
| xf3-base-jc_lv_nopol | 0.990 ± 0.017 | 0.677 ± 0.035 | 0.727 | 0.942 ± 0.003 | 3465 | 61 | 1.92 ± 0.50 | 1.26 ± 0.05 | 1 |
| xf3C-pjc_lv_nopol | 0.990 ± 0.017 | 0.707 ± 0.017 | 0.758 | 0.940 ± 0.007 | 3505 | 67 | 2.02 ± 0.55 | 1.15 ± 0.06 | 1.123 (10/9) |
| xf3C-pjc2_lv_nopol | 1.000 ± 0 | **0.727 ± 0.000** | 0.758 | 0.939 ± 0.004 | 3491 | 61 | 2.46 ± 0.30 | 1.15 ± 0.13 | 0.985 (10/10) |

Per seed (0 / 1 / 2):

| run | pour R / base | routed phys | base routed phys |
|---|---|---|---|
| pjc | 0.99 / 0.82 / 1.02 | 1.09 / 1.20 / 1.06 | 1.09 / 1.21 / 1.23 |
| pjc2 | 0.89 / 0.89 / 0.74 | 1.08 / 1.00 / 1.07 | 1.09 / 1.21 / 1.23 |
| pjc_lv_nopol | 1.15 / 1.05 / 1.17 | 1.21 / 1.09 / 1.16 | 1.26 / 1.20 / 1.31 |
| pjc2_lv_nopol | 1.01 / 1.06 / 0.90 | 1.28 / 1.01 / 1.16 | 1.26 / 1.20 / 1.31 |

- Against human, pour R is 1.43× for base jc and 1.20× for pjc2.
- DRC error types match the baselines' (`solder_mask_bridge`, `starved_thermal`,
  `silk_overlap`). All 396 attempts were ok.
- Tables are in `kae-work2/score/xf3C-pjc{,_lv}.md`, and pour R in
  `kae-work2/xf_pour/pour-xf3.json`.

## Verdict: merit for the coupled maps on the physics objective; no merit elsewhere
The success criterion: pour R ≤ 0.9× the baseline, lower routed physics, and completion
held.

- **pjc2 (coupled, physics objective) meets all three.**
  - Pour R is 0.839×, and below 0.9 on every seed.
  - Routed physics is 1.05 ± 0.05 against 1.18 ± 0.08, and it is no worse on any seed.
  - Completion is 0.936 against 0.935. Clean, length and vias are equal or slightly
    better, and fast physics also improves.
  - Caveat: the routed-physics gap is about 1.6 pooled sd, on 10 boards and 3 seeds.
- **pjc2_lv_nopol (length + vias) fails the pour criterion** at 0.985×. Routed physics is
  lower (1.15 against 1.26), and clean is up (0.727 against 0.677), but the cause is not
  the pours.
- **The per-layer maps (round 1's method) fail**: 0.939× and 1.123×.
  - This is consistent with the gate. Without coupling the map misranks via-fed layers,
    so it steers parts and tracks with partly wrong damage.
  - Round 1's 0.857× on the length objective does not reproduce.
- **Overall: merit**, limited to the coupled variant under the physics objective. Next
  steps: confirm on a larger pour suite and with more seeds, and tune K on the fixed
  engine.

## Scorecard row
| T4 | Pour-damage maps (layer-coupled Dirichlet/Thomson sensitivity of pour R_eff) in jc best responses and router costs | variational principles, topological derivative | `pjc2` (xf_pour) | **Merit** (physics objective) | Gate ρ ≥ 0.96 per board, coupled; pour R 0.84× jc, routed physics 1.05 ± 0.05 vs 1.18 ± 0.08, completion held (3 seeds, xf3); no merit on jc_lv_nopol (pour R 0.99×) or for per-layer maps |

## Earlier rounds (not comparable)
- **Round 1** (place tasks with probe, old engine): pour R 0.857× on jc_lv_nopol and 1.00×
  on jc, routed physics worse. Verdict: no merit.
- **Round 2** (engine v6.1): the ab33 runs `xf2C-*-ab33` were stopped part-way when the
  engine fix was announced. They are scratch.
