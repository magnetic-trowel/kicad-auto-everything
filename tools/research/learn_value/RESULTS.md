<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Learned value of partial boards for joint collapse (tag `learnv`, idea 32)

Can a cheap learned predictor of a partial board's final outcome steer [jc](../collapse_joint/RESULTS.md) restarts better than its heuristics, at equal CPU? Code: [lv_jc.py](lv_jc.py) (probes, steered jc), [lv_gen.py](lv_gen.py) (data), [lv_model.py](lv_model.py) (training, evaluation, simulation), [lv_policy.py](lv_policy.py); models in [model/](model/).

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

## Harness (kae-v7, score v7, engine v6.1, 33 A/B joint tasks, 120 CPU-s, 3 seeds)

PENDING

## Verdict

PENDING

## Next step

PENDING
