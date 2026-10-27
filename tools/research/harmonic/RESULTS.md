<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Harmonic-field routing in the joint loop (tag `harm`, idea 19) — PARTIAL

**Status: partial (work closed out on request).** Both v7 arms are complete: 3 seeds × 33 boards. The `v7-jc-r3` / `v7-jc_lv-r3` baselines were still running at close-out. The jc comparison below uses the 24 boards where jc had all 3 seeds. jc physics was not scored.

Idea 19 of [joint-pnr](../../../docs/ideas/original/joint-pnr.md), built on [jc](../collapse_joint/RESULTS.md). Code: [field.py](field.py), [stream.py](stream.py), [hjc.py](hjc.py); diagnostics [diag.py](diag.py), [congestion.py](congestion.py); tests [test_field.py](test_field.py).

## Method

- **Field.** A resistor network on a 0.4 mm grid per copper layer.
  - Via edges are scaled by 0.2.
  - Fine-cell conductance is 1/(1 + hist + β·foreign), the same prices as PathFinder. Coarse cells take the block mean; cells below 0.02 are removed (Neumann walls).
  - Per net: the pin nearest the centroid is held at φ = 1, the other pins at 0. Sparse LU solves the bounding box + 4 mm, at 60–80 ms per net. Warm-started SOR did not converge and was dropped.
- **Uses inside jc** (continuation, restarts, legalization and polish unchanged):
  - **(a) `stream`:** the steepest-ascent streamline tree is the route (search-free). Conflicts are priced as in jc.
  - **(b) `bias`:** a corridor around the tree biases A*.
  - **(c) `press`:** parts pay for other nets' expected occupancy |J|/I under their pads (Maxwell-stress analog). Its price is capped at β = 2.
- **Synthetic checks pass:** maximum principle, streamline termination, insulating walls, and |J|/I integrating to 1.6× the straight distance.

## Findings (v5, engine v5, kae-work)

- **(a) streamlines are not routes.** On 33 human placements, 974 of 980 sinks reached the source. But only 49.5 % of connections were clearance-legal at 0.1 mm, legal ones were 1.45× A* length, and CPU was 56× A*. Inside jc, (a) never converged: wire conflicts stayed in the hundreds. All-33 seed 0 gave clean 0.697 vs jc 0.667, but worse physics (fast 1.02× vs 0.82×; routed 1.19× vs 1.05×) and +8 % copper on all 3 seeds. Dropped.
- **(c) uncapped** (price ∝ β) made parts accept courtyard overlap. Capping it fixed this.
- **Route tasks** (`hroute`, (b) on human placements): cp1 0.667 vs 0.636 for the same engine, but 3 boards gained clean and 2 lost it, with +6 % copper. This is perturbation, not a systematic effect.
- **Congestion signal: modest but robust.** Summed |J|/I predicts the router's copper better than RUDY. Spearman 0.26 vs 0.18, better on 23/33 boards, and holding at 0.3 / 0.4 / 0.6 mm grids (23–24/33).

## Results (v7: harness score v7, `--kinds joint`, engine v6.3 c78c537, frozen worktree, 120 CPU-s, 3 seeds; mean ± spread)

**DRC, 28 boards unchanged by engine v6.4.** Length and vias are summed over the 19 boards every run completed on every seed.

| Run | Legal | Clean | Completion | Length (mm) | Vias |
|---|---|---|---|---|---|
| `v7-seq_phys-r3` | 0.893 ± 0.000 | 0.595 ± 0.036 | 0.903 | 2719 | 62 |
| `v7-combo-r3` | 0.917 ± 0.018 | 0.667 ± 0.054 | 0.935 | 2350 | 29 |
| **`hjc_press-r3`** | **0.988 ± 0.018** | **0.714 ± 0.036** | 0.935 | 2425 | 41 |
| `v7-combo_lv-r3` | 0.917 ± 0.018 | 0.643 ± 0.036 | 0.933 | 2362 | 30 |
| **`hjc_press_lv-r3`** | **1.000** | **0.738 ± 0.054** | 0.936 | 2388 | 45 |

**vs jc, 24 of the 28 boards** (jc had all 3 seeds there; 17 boards complete everywhere):

| Run | Legal | Clean | Completion | Length (mm) | Vias |
|---|---|---|---|---|---|
| `v7-jc-r3` | 0.986 | 0.694 ± 0.062 | 0.932 | 2583 | 46 |
| `hjc_press-r3` | 0.986 | 0.667 ± 0.042 | 0.925 | 2619 | 43 |
| `v7-jc_lv-r3` | 0.986 | 0.722 ± 0.021 | 0.928 | 2576 | 44 |
| `hjc_press_lv-r3` | 1.000 | 0.694 ± 0.062 | 0.925 | 2581 | 47 |

**Physics, phys10, per seed** (method/human gmean; jc not yet scored; output in `kae-v7/harm-phys/`):

| Run | Fast physics (φ-total) | Routed physics |
|---|---|---|
| `v7-combo-r3` | 1.37 / 1.28 / 1.14 | 1.29 / 1.23 / 1.30 |
| `hjc_press-r3` | **0.88 / 0.77 / 0.90** | **1.16 / 1.10 / 1.08** |
| `v7-combo_lv-r3` | 2.36 / 3.35 / 2.82 | 1.16 / 1.30 / 1.31 |
| `hjc_press_lv-r3` | 2.44 / 2.64 / 2.82 | 1.46 / 1.37 / 1.39 |

The physics rows cover the 10 phys10 boards, which may include boards that engine v6.4 changes. They have not yet been filtered to the 28.

## Provisional verdict

**No merit as a router. As a part-pressure term in jc it is a tie with jc, not a gain.**
- `hjc_press` clearly beats `combo` and `seq_phys` on legality, clean and physics.
- Against jc it is within seed spread: clean −0.03 (phys) and −0.03 (lv), +1 % copper, similar vias.
- The field is worth keeping only as an obstacle-aware congestion map, a small but consistent gain over RUDY.

## Next steps to finish

1. Re-run the jc comparison on all 28 boards once `v7-jc-r3` / `v7-jc_lv-r3` complete: `python tools/research/pnr/seeds.py kae-v7/results/{v7-jc-r3,harm-hjc_press-r3,v7-jc_lv-r3,harm-hjc_press_lv-r3} --suite tools/research/pnr/results/v63-v64-unchanged.txt`.
2. Score jc physics with `kae-v7/harm-phys/run.sh v7-jc-r3 v7-jc_lv-r3 ...`, and restrict physics to the unchanged boards.
3. If it stays a tie, close idea 19 as "no merit" and test |J|/I as a restart-ranking feature in jc.

**Operational notes:**
- Runs go through `runj_harm.sh` with `WT=<frozen worktree>` (a frozen worktree at 5987f57; engine identical to c78c537).
- `KAE_SRC` is the kae copy in `~/.cache/kaebench/kae-phys/src`. The sandbox hides /tmp; this was diagnosed here and the lead's fix followed.
- Earlier v7 runs `harm-*-v7`, `-v7r2` and smoke runs used a moving engine. They are discarded.
- `pyamg` was installed into `bench/.venv` for a solver test and is unused.
