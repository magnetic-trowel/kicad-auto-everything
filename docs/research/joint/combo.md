# combo: beam search, then blocker repair, then physics annealing

**Status:** worked.
**First published:** 2026-10-24, commit [2b7e6f9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/2b7e6f9d03edf76efd31c11fc8a02e60225810be) on branch `claude/keen-wright-mlkjv6` (`combo_lv`, `combo_full`: [46896fe](https://github.com/magnetic-trowel/kicad-auto-everything/commit/46896fe20d1b07b167e9091bdd220876571ded7d)).

The pipeline the single-method experiments pointed to: chain the three methods that each beat `seq`.
Over 3 seeds it gives more legal placements, higher completion, 13% less copper and about half the
vias of place-then-route; the clean-rate gain is within seed noise.

## Idea and how it works

`methods_combo.py:combo(world, seed, budget, phys_w=2)`, budget split 45 / 25 / 30%:
1. **beam** with the physics term ([tree-search.md](tree-search.md)): B = 4 partial boards, K = 6
   candidates per rotation, child score = routed cost + look-ahead + `phys_w` · physics.
2. **repair_phys** ([anneal-and-repair.md](anneal-and-repair.md)): blocker-directed window repair from
   the beam's board (window 4, k = 5), accepting on routed cost + `phys_w` · physics.
3. **anneal_phys** continuing from that board and its routes, for the rest of the clock.

Variants:
- `combo_lv`: `phys_w` = 0, the length + vias objective.
- `combo_full`: split 40 / 20 / 40. A state's score is routed cost + `full_w` · routed physics
  (`full_w` = 5), where routed physics is kae's full recheck on the written board (`RoutedPhys`,
  ~1.5 s per call). A stage whose result scores worse is reverted. Annealing runs in 4 slices; each
  slice end is a checkpoint judged by the same score.

## What we tried

- **v5 era:** ab33, place tasks, engine v5, 120 CPU-s, 3 seeds (`combo`, `seq`), 1 seed for
  `combo_lv`; physics on phys10.
- **v7 era:** ab33, joint tasks, engine v6.3, 120 CPU-s, 3 seeds; headline = 28 boards that engine
  v6.4 leaves unchanged. `combo` and `combo_lv` finished 99/99 attempts.

The eras are not comparable ([engine.md](engine.md#what-we-tried)).

## Results

v5, ab33, 3 seeds, mean of per-seed values
([seeds-v5-ab33.md](../../../tools/research/pnr/results/seeds-v5-ab33.md)):

| run | legal | clean (seeds) | completion |
|---|---|---|---|
| seq | 0.788 | 0.555 (0.545 / 0.545 / 0.576) | 0.856 |
| **combo** | **0.859** | 0.596 (0.636 / 0.606 / 0.545) | **0.896** |

Seed 0 also: length 2687 vs 3117 mm (20 boards), vias 16 vs 40
([drc-objectives-v5.md](../../../tools/research/pnr/results/drc-objectives-v5.md)); phys10 capped-u
0.97× human, routed 1.13× ([physics-objectives-v5.md](../../../tools/research/pnr/results/physics-objectives-v5.md)).

v7, 28 unchanged boards, 3 seeds, mean ± half-range; length and vias summed over the 19 boards every
arm completed on every seed ([v7-baselines.md](../../../tools/research/pnr/results/v7-baselines.md)):

| arm | legal | clean | completion | length mm | vias |
|---|---|---|---|---|---|
| seq | 0.893 ± 0.000 | 0.607 ± 0.036 | 0.904 ± 0.003 | 2715 ± 30 | 62.7 ± 11.0 |
| seq_phys | 0.893 ± 0.000 | 0.595 ± 0.036 | 0.903 ± 0.003 | 2719 ± 33 | 62.0 ± 11.5 |
| combo_lv | 0.917 ± 0.018 | 0.643 ± 0.036 | 0.933 ± 0.002 | 2362 ± 17 | 30.3 ± 1.0 |
| **combo** | 0.917 ± 0.018 | **0.667 ± 0.054** | **0.935 ± 0.003** | **2350 ± 2** | **29.0 ± 2.5** |

v7 physics, phys10, × human: combo place terms 1.26, fast 1.06, routed **1.27 ± 0.03**, against
seq_phys routed 1.11 and the human placement through the same router 1.11.

`combo_full`: no final numbers on the branch (the scorecard lists it as "still running").

## Verdict

**Worked.** On every seed in both eras combo is more legal, completes more connections, and uses less
copper (−13%) and far fewer vias (−54% in v7) than place-then-route. Its clean rate is higher but
within seed noise. Later, joint layer collapse ([jc.md](jc.md)) matched or beat it on legality and
clean rate.

Weak spot: v7 routed physics 1.27× human, worse than `seq_phys` (1.11×), although its place physics is
good. The annealing stage optimizes fast terms only; `combo_full` was the attempt to judge stages by
routed physics and was not finished. `RoutedPhys` time is outside the CPU clock, so `combo_full`
would get more than 120 CPU-s of work.

`combo` and `combo_full` are arms of the merit list (`combo_lv` is not); the 500-board comparison
(`merit-500r3` / `merit-500r3k`) is running. Results on the 500-board comparison: pending.

## Code

[`tools/research/pnr/methods_combo.py`](../../../tools/research/pnr/methods_combo.py): `combo`,
`combo_lv`, `combo_full`, `repair_phys`. Needs `pnr_mcts` on the path (done in the module) and kae
(`KAE_SRC`). Drivers: [`pnr/scripts/`](../../../tools/research/pnr/scripts/).

## Related

[tree-search.md](tree-search.md), [anneal-and-repair.md](anneal-and-repair.md),
[physics-objective.md](physics-objective.md), [jc.md](jc.md),
[layer-collapse-analysis.md](layer-collapse-analysis.md) (`combo_collapse`).
