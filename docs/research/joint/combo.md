# combo: beam search, then blocker repair, then physics annealing

**Status:** worked.
**First published:** 2026-10-24, commit [2b7e6f9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/2b7e6f9d03edf76efd31c11fc8a02e60225810be) on branch `claude/keen-wright-mlkjv6` (`combo_lv`, `combo_full`: [46896fe](https://github.com/magnetic-trowel/kicad-auto-everything/commit/46896fe20d1b07b167e9091bdd220876571ded7d)).

Scope: the chain of the three single methods that each beat `seq`; also the canonical v7 baseline table (seq, seq_phys, combo_lv, combo). Not here: v7 physics of these arms -> [physics-objective.md](physics-objective.md#results); `combo_collapse` -> [layer-collapse-analysis.md](layer-collapse-analysis.md#collapse-quantities-as-placement-terms-collapse_cplace).
Keys: combo, combo_lv, combo_full, `full_w`, beam → repair_phys → anneal_phys, v7 baselines, `RoutedPhys`

## Idea and how it works

`methods_combo.py:combo(world, seed, budget, phys_w=2)`, budget split 45 / 25 / 30%:
1. **beam** with the physics term ([tree-search.md](tree-search.md)): B = 4, K = 6 per rotation.
2. **repair_phys** ([anneal-and-repair.md](anneal-and-repair.md)) from the beam's board: window 4, k = 5, accept on routed cost + `phys_w` · physics.
3. **anneal_phys** from that board and its routes for the rest of the clock.

Variants:
- `combo_lv`: `phys_w` = 0 (length + vias objective).
- `combo_full`: split 40 / 20 / 40; state score = routed cost + `full_w` · routed physics (`full_w` = 5) from kae's full recheck on the written board (`RoutedPhys`, ~1.5 s per call); a stage that scores worse is reverted; annealing in 4 slices, each slice end a checkpoint judged by the same score.

## What we tried

- v5: ab33, place tasks, 120 CPU-s, 3 seeds (`combo`, `seq`), 1 seed (`combo_lv`); physics on phys10.
- v7: ab33, joint tasks, engine v6.3, 120 CPU-s, 3 seeds, headline 28 boards; `combo` and `combo_lv` finished 99/99 attempts. Eras: [README](README.md#eras-and-caveats).

## Results

v5, ab33, 3 seeds, mean of per-seed values ([seeds-v5-ab33.md](../../../tools/research/pnr/results/seeds-v5-ab33.md)):

| run | legal | clean (seeds) | completion |
|---|---|---|---|
| seq | 0.788 (all seeds) | 0.555 (0.545 / 0.545 / 0.576) | 0.856 (0.863 / 0.850 / 0.854) |
| **combo** | **0.859** (0.848 / 0.848 / 0.879) | 0.596 (0.636 / 0.606 / 0.545) | **0.896** (0.897 / 0.893 / 0.899) |

Legal +0.07 and completion +0.04 hold on every seed; the clean gain (+0.04) is within seed noise (seed 0 matched the human placement through the same router, 0.636, but was lucky).

Seed 0: length 2687 vs 3117 mm (20 boards), vias 16 vs 40 ([drc-objectives-v5.md](../../../tools/research/pnr/results/drc-objectives-v5.md)); phys10 capped-u 0.97× human, routed 1.13× ([physics-objectives-v5.md](../../../tools/research/pnr/results/physics-objectives-v5.md)).

v7, 28 unchanged boards, 3 seeds (baselines partial, stopped 2026-10-25), mean ± half-range; length and vias summed over the 19 boards every arm completed on every seed ([v7-baselines.md](../../../tools/research/pnr/results/v7-baselines.md)):

| arm | legal | clean | completion | length mm | vias |
|---|---|---|---|---|---|
| seq | 0.893 ± 0.000 | 0.607 ± 0.036 | 0.904 ± 0.003 | 2715 ± 30 | 62.7 ± 11.0 |
| seq_phys | 0.893 ± 0.000 | 0.595 ± 0.036 | 0.903 ± 0.003 | 2719 ± 33 | 62.0 ± 11.5 |
| combo_lv | 0.917 ± 0.018 | 0.643 ± 0.036 | 0.933 ± 0.002 | 2362 ± 17 | 30.3 ± 1.0 |
| **combo** | 0.917 ± 0.018 | **0.667 ± 0.054** | **0.935 ± 0.003** | **2350 ± 2** | **29.0 ± 2.5** |

`combo_full`: no final numbers on the branch (scorecard: "still running").

## Verdict

**Worked.** On every seed in both eras: more legal, more connections completed, −13% copper, −54% vias (v7) vs place-then-route; clean rate higher but within seed noise. [jc](jc.md) later matched or beat it on legality and clean rate.
- Weak spot: v7 routed physics 1.27× human, worse than `seq_phys` (1.11×) despite good place physics; the annealing stage optimizes fast terms only. `combo_full` (stages judged by routed physics) was not finished; its `RoutedPhys` time is outside the CPU clock, so it would get more than 120 CPU-s of work.
- Merit arms: `combo`, `combo_full`; `combo_lv` is not ([merit list](README.md#merit-list)).

## Open questions

- Finish `combo_full`.

## Code

[`tools/research/pnr/methods_combo.py`](../../../tools/research/pnr/methods_combo.py): `combo`, `combo_lv`, `combo_full`, `repair_phys`. Needs `pnr_mcts` on the path (done in the module) and kae (`KAE_SRC`). Drivers: [`pnr/scripts/`](../../../tools/research/pnr/scripts/).

## Related

[tree-search.md](tree-search.md), [anneal-and-repair.md](anneal-and-repair.md), [physics-objective.md](physics-objective.md), [jc.md](jc.md).
