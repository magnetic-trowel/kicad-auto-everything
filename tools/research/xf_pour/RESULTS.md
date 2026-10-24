<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# xf_pour: T4 pour-damage maps in jc (experiment C)

Plan: [transformations.md §T4, §5.3](../../../research_notes/transformations/transformations.md).

## What was built
- `pourmap.py` (`PourMaps`): one solve per pour (zone net n, layer l) on the World grid.
  - Region: zone outline ∩ board ∩ no foreign halo (`DT - own occT == 0`), so parts and
    foreign tracks are holes in it.
  - Grid: coarsened to 0.4 mm. Cell conductivity is the free fraction, edges use the
    harmonic mean, pads of n are equipotential terminals, and the metric is netcond's
    R_eff = 1/mean(1/R_ij).
  - Solve: one `splu` per connected component, then one back-solve per terminal.
  - Map: Thomson gives dR_ij/dc_e = −(Δφ_e^ij)². From that, E is the exact first-order
    relative R_eff increase per removed 0.1 mm cell, weighted by the layer's share of the
    net's conductance.
  - Cost: 0.02–0.2 s per refresh, 2–4 % of the budget.
- `pjc.py`: subclasses jc's `Collapse` and `Router`; `collapse_joint/` is not edited.
  - Part best response: `+ pour_w/g · Σ corr(E_nl, the part's halo cells of pads not on net n, layer l)`,
    one FFTCorr kernel per pour.
  - Router: for net m, hist on layer l gets `+ route_w/g · corr(E_nl, track disc)/diameter`
    for every pour n ≠ m.
  - Maps are refreshed at every jc iteration, after the nets are re-routed.
  - Weights: K = pour_w = route_w = 100 mm of wire per 100 % pour-resistance increase,
    fixed before the full runs. In a 1-seed pilot (6 boards, K ∈ {0, 30, 100, 300}) the
    seed noise was larger than any trend, and K = 300 tripled the length on noisecard.
- `gate.py` checks the maps. `pour_score.py` scores pour resistance: netcond, all layers,
  0.1 mm, on the KiCad-refilled output. It stubs `matplotlib.path` with shapely, because
  matplotlib and contourpy are not in the venv.

## Validation gate: passed
- Setup:
  - 6 phys10 boards with pours, human placement routed by the pnr router.
  - 40 random cut-outs per pour, each a real part's foreign-pad halo at a random spot on
    the pour.
  - 560 cut-outs in total, each compared with an exact re-solve.

| board | pours | Spearman, pooled | per pour |
|---|---|---|---|
| olimex dcdc | 4 | 0.991 | 0.978–0.982 |
| paw3395 | 2 | 0.959 | 0.997, B.Cu 0.745 |
| lt6c | 2 | 0.984 | 0.992, 0.986 |
| pmw3360 | 2 | 0.935 | 0.995, B.Cu 0.674 |
| pmw3610 | 1 | 0.991 | 0.991 |
| noisecard | 3 | 0.999 | 0.992–0.999 |

- Pooled ρ is ≥ 0.935 on every board. The median per pour is 0.988, and 12 of 14 pours
  reach ≥ 0.9.
- The exact change is always above the prediction, which is a true lower bound: median
  exact/predicted 2.3–3.3×, range 1.07–28×. It fails on necky, high-resistance B.Cu
  layers that only a few pads reach.
- Limit: each layer is solved alone, so vias do not couple the layers. A B.Cu pour fed
  only through vias has no terminals (noisecard GND B.Cu).

## Results (ab33, budget 120, seeds 0–2)
- Clean and completion are the 3-seed mean ± sd. Legal, length and vias are seed 0
  (`compare.py`; length and vias are on the boards both runs completed).
- Physics is phys10, seed 0, method/human.
- Pour R is the gmean over the 21 (board, net) pairs with pours. Each pair is first
  averaged as a gmean over 3 seeds, then the run's value is divided by the baseline's.

| run | legal | clean mean±sd | clean best-of-3 | completion | length mm | vias | fast phys | routed phys | pour R vs base (better/worse) | pour R vs human |
|---|---|---|---|---|---|---|---|---|---|---|
| xf-base-jc-ab33 | 0.909 | 0.657±0.035 | **0.727** | 0.897 | **3111** | **76** | 1.08 | **0.88** | 1 | 1.23 |
| **xfC-pjc-ab33** | 0.909 | 0.636±0.030 | 0.667 | **0.903** | 3259 | 82 | **0.98** | 1.01 | **0.999** (12/7) | 1.23 |
| xf-base-jc_lv_nopol-ab33 | 0.879 | 0.616±0.046 | 0.697 | 0.900 | **3298** | **79** | **2.31** | **1.16** | 1 | 1.21 |
| **xfC-pjc_lv_nopol-ab33** | 0.879 | **0.657±0.035** | 0.697 | **0.905** | 3343 | 83 | 2.54 | 1.21 | **0.857** (14/6) | 1.04 |

- Pour R per seed, as a ratio to the baseline: pjc 1.07 / 0.83 / 1.11; pjc_lv 0.95 / 0.75 / 0.89.
- In the harness tables, cpk (best of 3) is 0.667 for pjc and 0.697 for pjc_lv.
  Completion is 0.906 and 0.907.
- DRC types are the same as the baselines'. pjc's `solder_mask_bridge` count on seed 0
  fell from 21 to 9.

Full tables are in `kae-work/score/xfC-pjc{,-phys}.md`, `kae-work/score/xfC-pjc_lv{,-phys}.md`
and `kae-work/xf_pour/pour.json`.

## Verdict: no merit (against the success criterion)
- **Physics objective.**
  - Pour resistance is unchanged (0.999×).
  - Routed physics is worse: 1.01 against 0.88.
  - Fast physics improves (0.98 against 1.08), but at +5 % length and +8 % vias.
  - Under phys_w = 2 the pour term gets outvoted. With the route term, the extra wire
    goes elsewhere rather than into better pours.
- **Length + vias objective.**
  - Pour resistance falls to 0.857× the baseline, which meets the ≤ 0.9 target. Every
    seed improves, and against human it goes from 1.21× to 1.04×.
  - Completion and clean hold or improve.
  - But routed physics gets worse (1.21 against 1.16), so better pours did not carry into
    kae's routed physics on phys10. The plan's kill condition holds: pours are not on the
    critical path of the routed recheck.
- **The map itself works.** It is cheap (≤ 4 % of the budget) and rank-accurate (ρ ≥ 0.93
  per board), and on the length objective it moves pour resistance by about 14 %.
  As a placement/routing term for routed physics it has no merit at K = 100.
- **Caveats.**
  - The routed-physics numbers are one seed on 10 boards, of which only 6 have pours.
  - K was not tuned.
  - Inside the jc loop the part's own halo blocks the map at its current position, a
    slight stay-put bias.
  - Via costs over-weight pour damage by about 2.5×, because the via cost multiplies hist.

## Scorecard row
| T4 | Pour-damage maps (Dirichlet/Thomson sensitivity of pour R_eff) in jc best responses and router costs | variational principles, topological derivative | `pjc`, `pjc_lv_nopol` (xf_pour) | **No merit** | Gate ρ ≥ 0.93 per board (exact re-solves); pour R 0.86× jc_lv but 1.00× jc; routed physics 1.01 vs 0.88 (jc), 1.21 vs 1.16 (jc_lv); completion held |
