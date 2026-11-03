# Physics place terms in the placement objective, and the physics scorer

**Status:** worked (objective); the scorer is a working measurement tool.
**First published:** 2026-10-24, commit [2a1c9c1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/2a1c9c1f6213e7e289bea7e014c0e9b5c90b6328) on branch `claude/keen-wright-mlkjv6` (engine v5; scorer [6e5c658](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6e5c658f0ea7c268fe8d44682160bf7a820b4d4b)).

Scope: kae's fast physics terms added to every pnr placement objective (idea 43 of the [catalog](../../ideas/original/joint-pnr.md)), and the scorer that measures place and routed physics against the human layout. Not here: exact maps instead of `Terms.delta` sampling -> [jc-extensions.md](jc-extensions.md#exact-physics-maps-t2).
Keys: physics place terms, `phys_w`, φ(u), capped-u, `Terms.delta`, `Phys`, `RoutedPhys`, `descent_phys`, `coarse_map`, seq_phys, anneal_phys, physics scorer, `physics_score.py`, routed physics, phys10, idea 43

## Idea and how it works

### Physics in the objective (`pnr/physics.py`, `pnr/methods_phys.py`)

Problem: HPWL placements are electrically worse than human ones (decaps far from the pin they serve, feedback nodes next to switch nodes).
- `Phys` builds a netlist-only "brief" (decap loop, hot loop, crystal, cable entry, ESD path, coupled victim) and kae's `Terms` once per board; poses keyed by footprint uuid.
- Move price: `Terms.delta(...)` in 30–60 µs. Terms = φ(u) per structure, u = metric / budget: decap loop inductance (nH), hot-loop inductance (nH), coupling (mV), crystal (ppm), thermal rise (K), cable common-mode, ESD path.
- Objective = routability cost + `phys_w` · Δphysics, `phys_w` = 2 mm of copper per unit of φ.
- `descent_phys`: best-response descent; physics parts use a coarse physics map over their legal origins (`coarse_map`), others the HPWL map.
- `seq_phys` = HPWL placement (as `seq`) → `descent_phys` → route.
- `anneal_phys` = annealing on routed cost + `phys_w` · physics; half the moves pick a physics part, a third of those jump to the part's best HPWL + physics spot.
- `RoutedPhys`: full routed recheck (~1.5 s, KiCad subprocess) for stage gates in `combo_full` and `jc_full`; runs outside the CPU clock.
- kae found via `KAE_SRC` (default `~/.cache/kaebench/kae-phys/src`, else `kae/src`).

### Physics scorer (`pnr_phys/physics_score.py`)

`physics_score.py RUN_DIR...` (kae venv). Per board, once (cached): the brief (identical from reference board or task input) and `Terms(board, brief)`; then score the human reference and each attempt:
- **place:** `Terms.total` (confidence × φ(u), barrier above budget) and robust **capped-u** Σ min(u, 5);
- **routed:** kae's `critical_recheck.board_physics` on the real copper, zones refilled by KiCad; unrouted hops priced as straight strips (optimistic), so a "no open hop" column is reported too.
- Ratio = geometric mean over boards of (method + 0.01) / (human + 0.01).
- `xf_common/physics_score_xf.py` supersedes it for the xf rounds.

## What we tried

- v5 (place tasks, 1 seed): `seq` vs `seq_phys`, `anneal` vs `anneal_phys`, `grow`, on ab33; physics on phys10.
- v7 (joint tasks, engine v6.3, 3 seeds): `seq`, `seq_phys`, `combo_lv` (phys_w = 0), `combo`. Eras not comparable ([README](README.md#eras-and-caveats)).

## Results

v5, phys10, 1 seed, ratio to human ([pnr_phys/RESULTS.md](../../../tools/research/pnr_phys/RESULTS.md), [15e1899](https://github.com/magnetic-trowel/kicad-auto-everything/commit/15e189903b958c1a77e5ca1aaae21ac526b38a25)):

| run | clean / compl. (33 boards) | φ-total | capped-u (worse/better boards) | routed (worse/better) |
|---|---|---|---|---|
| human placement, pnr router | 21 / 0.92 | 1.00 | 1.00 | 1.09 (3/7) |
| seq | 18 / 0.86 | 4.05 | 1.45 (8/1) | 1.39 (7/3) |
| **seq_phys** | 18 / 0.86 | **1.52** | **1.20** (5/4) | **1.26** (7/3) |
| grow | 18 / 0.86 | 7.35 | 1.77 (8/1) | 1.37 (8/2) |
| anneal | 19 / 0.87 | 4.28 | 1.57 (7/2) | 1.54 (6/4) |
| **anneal_phys** | 19 / 0.88 | **1.68** | **1.29** (7/2) | **1.33** (7/3) |

- Sources of the HPWL excess: decap 50–70% of capped excess (HPWL pulls a capacitor toward its rail and ground nets, not the pin it serves); coupling ~25% (olimex buck: feedback node next to switch node, 405 mV vs a 10 mV budget); cable common-mode. ESD *better* than human (compaction shortens the connector-to-TVS hop).
- `seq_phys` vs `seq`: coupling 3.5× → 1.2×, decap 1.33× → 1.15×, thermal 1.39× → 0.94×; legal, clean, completion identical; routed length +1.7% on the physics boards.

v5, phys10, seed 0, DRC on the 10 boards ([physics-objectives-v5.md](../../../tools/research/pnr/results/physics-objectives-v5.md)); other methods' physics on their pages:

| run | legal / clean (of 10) | completion | φ-total | capped-u | routed |
|---|---|---|---|---|---|
| human placement, same router | 10 / 4 | 0.96 | 1.00 | 1.00 | 1.09 |
| seq | 7 / 3 | 0.86 | 4.05 | 1.45 | 1.39 |
| seq_phys | 7 / 3 | 0.86 | 1.52 | 1.20 | 1.26 |
| anneal_phys | 8 / 4 | 0.89 | 1.68 | 1.29 | 1.33 |
| beam (phys_w = 2) | 8 / 4 | 0.94 | 0.98 | 1.01 | 1.14 |
| combo | 9 / 5 | 0.96 | 1.03 | 0.97 | 1.13 |
| grad_phys post=phys | — | 0.84 | 1.37 | 1.08 | 1.00 |
| Physarum motion + physics, from seq_phys | 7 / 3 | 0.86 | 1.53 | — | 1.30 |

Objective comparison, v5, ab33, seed 0: length + vias objective (`phys_w` = 0) vs fast physics (`phys_w` = 2) in each pipeline; length summed over the 20 boards every run completed; physics × human on phys10 ([drc-objectives-v5.md](../../../tools/research/pnr/results/drc-objectives-v5.md)):

| pipeline | objective | legal | clean | completion | length mm | vias | capped-u | routed |
|---|---|---|---|---|---|---|---|---|
| seq | length + vias | 0.788 | 0.545 | 0.863 | 3117 | 40 | 1.45 | 1.39 |
| seq_phys | fast physics | 0.788 | 0.545 | 0.863 | 3152 | 44 | 1.20 | 1.26 |
| anneal | length + vias | 0.848 | 0.576 | 0.874 | 2852 | 22 | 1.57 | 1.54 |
| anneal_phys | fast physics | 0.818 | 0.576 | 0.876 | 2952 | 24 | 1.29 | 1.33 |
| combo_lv | length + vias | 0.818 | 0.545 | 0.900 | 2695 | 16 | 1.34 | 1.26 |
| combo | fast physics | 0.848 | 0.636 | 0.897 | 2687 | 16 | 0.97 | 1.13 |

- In every pipeline the physics objective improves fast and routed physics; completion, length and vias equal within noise. Keep the physics term on by default [M].
- 22-board length set (v5, seed 0; [collapse_joint/RESULTS.md](../../../tools/research/collapse_joint/RESULTS.md)): seq 3386 mm / 60 vias, seq_phys 3422 / 64, anneal_phys 3189 / 38, beam 3095 / 39, combo 2943 / 25.
- Three scores on every run (`kae-work/score_all.sh`): DRC (legal, clean, completion, length, vias), fast physics × human, full routed physics × human.

v7, phys10, 3 seeds, mean ± half-range ([v7-baselines.md](../../../tools/research/pnr/results/v7-baselines.md)):

| arm | place terms | fast (capped-u) | routed |
|---|---|---|---|
| human placement, same router (1 run) | 1.00 | 1.00 | 1.11 |
| seq | 2.52 ± 0.37 | 1.22 ± 0.10 | 1.22 ± 0.07 |
| **seq_phys** | 1.12 ± 0.07 | **1.01 ± 0.05** | **1.11 ± 0.09** |
| combo_lv | 2.84 ± 0.50 | 1.31 ± 0.04 | 1.26 ± 0.07 |
| combo | 1.26 ± 0.11 | 1.06 ± 0.06 | 1.27 ± 0.03 |

Scorer: only **10 of 33** boards have any physics structure (all terms 0 on the other 23); fast physics predicts routed physics weakly, mean within-board Spearman 0.55 (0.13–0.95 over 9 physics boards): a method tuned on fast physics needs the routed check ([scorecard.md](../../ideas/original/scorecard.md)).

## Verdict

**Worked.** Place-physics gap to human ~4× → ~1.5× (v5), capped-u at human level in v7, no loss in legality, clean rate or completion. Routed physics improves less (1.39 → 1.26 v5; 1.22 → 1.11 v7) and stays above human: copper the place terms do not see, plus the remaining decap and commutation terms.
- Caveats: n = 10 boards; priors unmeasured ("E5"); `*_phys` optimizes the terms that score it, so the routed column is the less circular check; `RoutedPhys` outside the CPU clock (affects `combo_full`, `jc_full`).
- Merit arms: `seq_phys`, `anneal_phys` ([merit list](README.md#merit-list)).

## Code

- [`tools/research/pnr/physics.py`](../../../tools/research/pnr/physics.py) (`Phys`, `RoutedPhys`), [`methods_phys.py`](../../../tools/research/pnr/methods_phys.py) (`seq_phys`, `anneal_phys`, `grow_phys`, `descent_phys`).
- Scorer: [`tools/research/pnr_phys/physics_score.py`](../../../tools/research/pnr_phys/physics_score.py), xf version [`xf_common/physics_score_xf.py`](../../../tools/research/xf_common/physics_score_xf.py). Needs kae (`KAE_SRC`).

## Related

[sequential-controls.md](sequential-controls.md), [anneal-and-repair.md](anneal-and-repair.md), [combo.md](combo.md), [jc.md](jc.md).
