# Tree search over place-one-route-it: beam search and MCTS

**Status:** beam search worked (moderate); MCTS did not work at this budget.
**First published:** 2026-10-24, commit [6e5c658](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6e5c658f0ea7c268fe8d44682160bf7a820b4d4b) on branch `claude/keen-wright-mlkjv6` (results [5dd4957](https://github.com/magnetic-trowel/kicad-auto-everything/commit/5dd495783727e28e0113365507388659f9842df2)).

Scope: place parts one at a time, routing each before the next, keeping several partial boards alive (ideas 7, 8 of the [catalog](../../ideas/original/joint-pnr.md)). Not here: the greedy step `grow` -> [sequential-controls.md](sequential-controls.md); beam as combo's first stage -> [combo.md](combo.md).
Keys: beam search, beam, MCTS, UCT, rolling horizon, progressive widening, grow_wide, fastcand, node switching by diffing, partial board, ideas 7 8

## Idea and how it works

**Tree.** Level k = k-th part in growth order (most-connected first); branch = candidate pose of that part (K = 6 per rotation); node = partial board (poses of placed parts + their routes).

**Node switching by diffing.** A node keeps poses + a shallow copy of routes; path arrays are immutable, so nodes share them. `switch(a, b)` diffs two states and moves or re-stamps only what changed: 0.1–0.5 ms, vs 2–90 ms per expansion (place a part + 4 PathFinder iterations), so replay from the root would cost 2–3 orders of magnitude more.

**fastcand.** Same candidates as `Kit.candidates`, 4–6× faster: skip the FFT legal map, take cells in HPWL order, test legality one by one in numba.

**beam** (B = 4). Child score = routed cost + look-ahead (greedy HPWL of the next 2 parts × 1.3, penalty when a part has no legal spot) + `phys_w` · physics, unplaced parts parked at the board centre. Keep the best B children per level; the 2 best final boards get a full PathFinder; parts left unplaced go through the engine's ripple legalizer.

**mcts.** Rolling-horizon UCT on the same tree: each part gets an equal CPU slice, then the root commits to a child. Progressive widening ⌈1.5 · N^0.5⌉ children, fading prior from each child's routed cost. Rollout = greedy HPWL placement of the remaining parts + 3 PathFinder iterations.

**grow_wide.** Greedy ablation: same score, K = 24, no beam.

## What we tried

v5, place tasks, 120 CPU-s, **seed 0 only**: ab33 with `phys_w` = 2 (zero on the 23 boards without physics structures), dev6 with `phys_w` = 0, phys10 for physics. Host loaded (9–14 on 4 cores): wall time ≈ 2–3× CPU.

## Results

ab33, v5, seed 0; length over the 21 boards every run completed ([pnr_mcts/RESULTS.md](../../../tools/research/pnr_mcts/RESULTS.md)):

| run | legal | clean | completion | length mm | vias | wall s |
|---|---|---|---|---|---|---|
| seq | 0.788 | 0.545 | 0.863 | 3327 | 54 | 58 |
| grow | 0.788 | 0.545 | 0.861 | 3274 | 35 | 74 |
| grow_wide (K = 24) | 0.788 | 0.515 | 0.868 | 3278 | 42 | 83 |
| **beam** | **0.818** | 0.545 | **0.891** | **3012** | **32** | 192 |

- Beam vs grow_wide per board: completion better on 5, worse on 2; shorter on 16 of 22.
- dev6 (`phys_w` = 0), completion / length over 3 boards: seq 0.904 / 624, grow_wide 0.953 / 631, beam 0.954 / 554, **mcts 0.963 / 541**; clean 0.667 for all.
- phys10, × human, place φ / capped-u / routed: grow_wide 2.45 / 1.32 / 1.22; **beam 0.98 / 1.01 / 1.14**; mcts 1.74 / 1.17 / 1.18 (seq, seq_phys → [physics-objective.md](physics-objective.md#results)).

## Verdict

- **beam: worked (moderate).** Equal CPU, same objective: completion +2.3 points, 8% less wire, fewer vias, legal +3 points; with the physics term the best place physics of any v5 run (0.98× human). K = 24 greedy = K = 6 greedy, so the gain is from keeping alternatives *across* steps, not more candidates per step.
- No clean-rate gain: failures there come from engine gaps (pad clearance, thermal spokes, silkscreen); beam's denser boards add `silk_overlap` (52 vs 28).
- **mcts: did not work at this budget.** Best dev6 completion, but dense boards allow only 8–10 rollouts per part; the first version (committing on rollout value) lost to greedy on paw3395. Trails beam on legality and physics at ~1.6× the wall time.
- Not done: beam over 3 seeds vs grow_phys / anneal_phys; branching on which part goes next.
- Merit arm: `beam --opt phys_w=2`; `mcts` is not ([merit list](README.md#merit-list)).

## Code

[`tools/research/pnr_mcts/`](../../../tools/research/pnr_mcts/): `mcts.py` (`beam`, `mcts`, `grow_wide`), `fastcand.py`, `dev.py` (in-process dev runner), `rundev6.sh`, `merge_runs.sh`. Run: `run.py tools/research/pnr_mcts/mcts.py:beam IN OUT --budget 120 --opt phys_w=2`.

## Related

[sequential-controls.md](sequential-controls.md), [combo.md](combo.md), [engine.md](engine.md).
