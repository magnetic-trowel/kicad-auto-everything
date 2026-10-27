<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Learned value of partial boards for joint collapse (tag `learnv`, idea 32)

**PARTIAL.** Work was closed out before the jc baselines finished. Everything below the harness section is complete. The harness comparison uses only the boards where every run has all 3 seeds.

Can a cheap learned predictor of a partial board's final outcome steer [jc](../collapse_joint/RESULTS.md) restarts better than its heuristics, at equal CPU? Code: [lv_jc.py](lv_jc.py) (probes, steered jc), [lv_gen.py](lv_gen.py) (data), [lv_model.py](lv_model.py) (training, evaluation, simulation), [lv_policy.py](lv_policy.py); models were written to `model/` (not published: pickled sklearn models execute code on load; `lv_model.py` re-trains them).

## Data

jc (frozen snapshot `kae-work/jc-snap/jc_v3.py`, physics objective, no polish, 300 CPU-s, seed 100, per-restart cap as at 120 s) with probes after the lift and after every β iteration of every restart. That gives **31 A/B boards, 1569 restarts, 28 433 checkpoints**. Each checkpoint has about 20 features that cost about 5 ms (≈2 % of CPU): HPWL, fast physics, routed length, vias, unrouted, routed cost, wire-history sum/density/max/p99, part history, part overlap, wire conflicts, bad nets, moved parts, bus forced vias, star crossings and overflow ([collapse_cplace/terms.py](../collapse_cplace/terms.py)), plus β and time. The outcome is the restart's score, which is what jc keeps the best by: routed cost + 2 × fast physics. The lv model is retargeted to routed cost alone, on the same trajectories. Lifted-conflict cost (`LiftedConflicts`) was left out: it needs copper ripped and a CP-SAT solve, which is not ms-cheap. Caveat: the data predates engine v6. The evaluation runs on v6.1.

## Model

The model is pairwise: (restart *a* at checkpoint *c*, another restart *b* of the same board at min(c, last of b)) → Δlog(1+cost). Pairing keeps board scale (5 to 3000) out of the model. We fit ridge and gradient boosting (sklearn) over **5 leave-boards-out folds**, so every number below is out-of-fold. At run time each board loads the model of the fold that held it out.

## Predictive power (mean within-board Spearman with the final restart cost)

| checkpoint | routed cost now | HPWL | conflicts | wire history | ridge | GBM |
|---|---|---|---|---|---|---|
| lift (c=0) | −0.09 | −0.09 | 0.04 | 0.01 | 0.00 | 0.12 |
| β-iter 2 | 0.09 | 0.23 | 0.00 | −0.01 | 0.14 | 0.20 |
| β-iter 5 | **0.45** | 0.40 | 0.06 | 0.22 | 0.32 | 0.36 |
| β-iter 12 | **0.58** | 0.51 | −0.02 | 0.16 | 0.42 | 0.55 |

Nothing measured at the lift predicts how a restart ends: the continuation's random orders decide it. From iteration 5 on, the plain current routed cost is the best predictor, and the learned model does not beat it (lv: same picture).

## Use, simulated at equal CPU

Each board's logged restarts were replayed in 60 bootstrap orders under jc's restart rule and budget (102 CPU-s phys, 120 lv). A policy abandons a restart at a checkpoint (lift and iterations 1–50) when its predicted Δ against the incumbent exceeds a margin. The time spent so far is charged, and at most 3 restarts can be abandoned in a row. Margins were chosen on the other folds' boards (nested). The table gives the ratio of the best restart cost to plain jc restarts (gmean over 31 boards) and the number of boards better / worse.

| policy | phys | lv |
|---|---|---|
| **oracle at lift** (true final cost known) | **0.967** (28/0) | **0.962** (28/0) |
| oracle at iteration 5 | 0.972 (23/0) | 0.973 (24/0) |
| learned, ridge (exported) | 0.996 (9/4) | 1.002 (8/5) |
| learned, GBM | 1.002 (8/4) | 1.008 (5/4) |
| learned, lift only | 1.013 (5/5) | 1.002 (2/3) |
| bound: routed cost now > best final | 0.997 (8/6) | 0.995 (9/6) |
| heuristic: Δ routed cost vs incumbent | 1.014 (3/4) | 1.023 (1/5) |

**The headroom is small.** Even perfect knowledge of every restart's final cost, available right after its lift, buys only 3–4 % (4.5 % on the 12 boards with ≤4 restarts per budget). Restarts are cheap and their outcomes are close to i.i.d., so pruning them mostly buys more draws from the same distribution. The learned policies capture none of that 3–4 %.

## Harness (kae-v7, score v7, engine v6.3 c78c537, 120 CPU-s, 3 seeds, mean ± half-range)

The arms are `learnv-jcv-ab33-r3` (`jc_value`, physics objective) and `learnv-jcvlv-ab33-r3` (`jc_value_lv`, length + vias). Each ran all 99/99 attempts from a frozen worktree (`runj_wt.sh`), with about 12 of ~30 restarts per attempt abandoned. The baselines `v7-jc-r3` and `v7-jc_lv-r3` were stopped at 88 and 94 of 99. Fair rows: the **29 boards** that every run has on all 3 seeds (length and vias are summed over the 20 boards every run completed). Physics covers phys10 (jc baselines not yet scored).

| run | legal | clean | completion | length | vias | fast phys | routed phys |
|---|---|---|---|---|---|---|---|
| `jc` | 0.954 ± .017 | 0.655 ± .034 | 0.919 ± .009 | 3190 | 57.7 | — | — |
| **`jc_value`** | 0.943 ± .017 | 0.667 ± .017 | 0.915 ± .009 | 3189 | 53.7 | 0.96 ± .07 | 1.15 ± .04 |
| `combo` | 0.885 ± .017 | 0.644 ± .052 | 0.921 ± .005 | 3294 | 42.7 | 1.26 ± .12 | 1.27 ± .04 |
| `jc_lv` | 0.954 ± .017 | 0.678 ± .017 | 0.919 ± .003 | 3175 | 53.0 | — | — |
| **`jc_value_lv`** | 0.931 ± .000 | 0.667 ± .086 | 0.920 ± .001 | 3149 | 51.7 | 2.64 ± .35 | 1.24 ± .07 |
| `combo_lv` | 0.897 ± .034 | 0.609 ± .052 | 0.919 ± .002 | 3240 | 39.7 | 2.84 ± .50 | 1.26 ± .08 |

The requested 28-board row (`pnr/results/v63-v64-unchanged.txt`) and the 33-board row are in `kae-work/learnv/drc-tables.md`. Neither can be read yet: the missing baseline attempts count as zeros there (on 28 boards, `jc_value` shows legal 1.000 and clean 0.726 against 0.857 and 0.607 for `jc`, but `jc` has 73 of 84 attempts). Fast physics is the total ratio to human.

## Verdict (provisional)

**No merit.** The learned value predicts restart outcomes no better than the current routed cost. Restart pruning has a ceiling of only 3–4 % even with an oracle, and in the harness `jc_value` ties `jc` within the seed spread on every DRC metric (vias −7 %, within noise). The physics objective's own fast/routed physics stay ahead of combo, as jc's do.

## Next steps to finish

1. Let `v7-jc-r3` and `v7-jc_lv-r3` finish. Re-run `pnr/seeds.py` on the 28-board list, and run `kae-work/learnv/phys.sh v7-jc-r3 v7-jc_lv-r3` for the jc physics columns.
2. Optionally regenerate the training data on engine v6.3 (it predates v6), though the ceiling makes a different outcome unlikely.
3. If the idea is revisited, target what varies between restarts, the continuation's random orders, rather than the start state. For example, a value on whole-continuation summaries for choosing *which* restart to polish, not which to abandon.

Earlier harness attempts (`learnv-*-v7`, `-v7b` = mixed engine code; `-v7c` = v6.2) are set aside as `.MIXED`/`.v62` and not counted.
