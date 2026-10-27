# Routed-cost annealing, blocker-directed repair, and exact CP-SAT windows

**Status:** annealing worked; blocker repair worked as a stage; CP-SAT windows did not work.
**First published:** 2026-10-24, commit [44831ff](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44831ff3f802b1758b9c1299e0ae0b212d581f9a) on branch `claude/keen-wright-mlkjv6` (CP-SAT windows: [6e5c658](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6e5c658f0ea7c268fe8d44682160bf7a820b4d4b), results [95265a6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/95265a6ac80097d86dea3a42a5b933b2667012bf)).

Three local-search methods that judge a placement change by the copper the router actually lays.
Annealing on re-routed cost and blocker-directed repair both beat the `seq` control and became stages
of [combo](combo.md). Making the repair window exact with CP-SAT lost to the heuristic on every window.

## Idea and how it works

### anneal / anneal_phys (idea 11; VPR, Nag–Rutenbar)
Simulated annealing over part poses, starting from the `seq` placement.
- Moves: jump to a random legal pose nearby (the radius shrinks with temperature), rotate in place,
  swap two parts.
- Each move rips up and re-routes only the affected nets, incrementally, with snapshot/restore of the
  route state.
- Cost = `Kit.total_cost()` (routed mm + 2 mm/via + one board perimeter per unrouted connection).
- `anneal_phys`: cost + `phys_w` · physics; half the moves pick a physics part, and a third of those
  jump to the part's best HPWL + physics spot ([physics-objective.md](physics-objective.md)).

### repair (ideas 12, 13; LNS + guided local search)
Repeat until the budget ends:
1. Pick an unrouted net (or the most detoured one).
2. Route it *soft* (foreign copper priced, not forbidden). The **blockers** are the parts whose
   footprint lies under the cells where that soft route crosses foreign copper.
3. Rip up the blockers plus the net's own parts.
4. Re-place them one by one; each part's candidates are scored by real routing (the `grow` step).
5. Keep the result if the board improved (`repair_phys`: accept on routed cost + w · physics).

### cpsat (idea 36; SP&R, Numberlink SAT) as the repair window solver
From `seq_phys`, pick an unrouted or most-detoured net and a window ≤ 9 mm with 2–3 movable parts. Rip
up those parts and every net touching or crossing the window. Model on a 0.6 mm, 2-layer grid:
- Boolean pose choice per part over its current pose + its top-6 candidates; `NoOverlap2D` per plane;
  pad halos exclude other nets.
- Each MST connection is a Numberlink path: degree 1 at its endpoints, 0 or 2 elsewhere; cells
  exclusive per net; a via clears its 8 neighbours. Border exits are priced by distance to the pins
  outside.
- Objective: 3000 per missed connection + length + 2 mm/via + exit cost + 2 · physics delta.
- Solve in two phases: route with poses fixed (as assumptions, gives a hint), then free the poses.
  1 worker, LP off, presolve off, 3 deterministic seconds.
- Decode, re-route with PathFinder, accept on routed cost + 2 · physics.

## What we tried

v5 era, engine v5, 120 CPU-s, place tasks, **1 seed**: ab33 for `anneal`, `anneal_phys`, `repair`;
dev6 (6 development boards) and phys10 for `cpsat`, with a dev6 repair control. A head-to-head on 28
identical windows and states (4 CP-SAT model variants: lattice, LP on, radius 3; 112 runs). An earlier
multi-commodity flow encoding was abandoned.

## Results

ab33, v5, seed 0 ([drc-v5-ab33.md](../../../tools/research/pnr/results/drc-v5-ab33.md)):

| run | legal | clean | completion | length mm (21 boards) | vias |
|---|---|---|---|---|---|
| seq | 0.788 | 0.545 | 0.863 | 3327 | 54 |
| **anneal** | **0.848** | **0.576** | 0.874 | 3048 (−8%) | 32 |
| anneal_phys | 0.818 | 0.576 | 0.876 | 3145 | 32 |
| repair | 0.818 | 0.545 | 0.873 | 3054 | 33 |

- Routed physics (phys10): `anneal` 1.54×, `anneal_phys` 1.33× human
  ([physics-objective.md](physics-objective.md)). On the olimex buck board `anneal_phys` reached place
  physics 5.83 vs human 7.39, DRC clean.

dev6, v5, seed 0 ([pnr_cpsat/RESULTS.md](../../../tools/research/pnr_cpsat/RESULTS.md)):

| run | legal | clean | completion | length (4 boards) | wall s |
|---|---|---|---|---|---|
| seq | 0.667 | 0.667 | 0.904 | 682 | 45 |
| **repair** (control) | **0.833** | 0.500 | **0.921** | **594** | 214 |
| same loop, no CP-SAT | 0.667 | 0.667 | 0.908 | 681 | 257 |
| cpsat (3 s) | 0.667 | 0.667 | 0.908 | 680 | 353 |
| cpsat (10 s) | 0.667 | 0.667 | 0.908 | 685 | 205 |

- ~750 CP-SAT windows in all; none ended OPTIMAL (FEASIBLE, INFEASIBLE or UNKNOWN).
- Routing alone does not converge: a 5-connection window (8k variables) scored 672 at 1 s, 404 at 3 s,
  292 at 10 s, unproven at 30 s. At 3 s the model left ≥ 1 connection unrouted in 40% of dev6 windows on
  boards the engine routes completely.
- Head-to-head: repair improved 14 of 28 windows; CP-SAT moved a part in 17 of 112 runs, improved the
  board in 6 and **beat the heuristic in 0 of 112**.
- Flow encoding: a flow per net missed 9 of 16 terminals with parts fixed after 30 s on 4 workers.
- phys10: `cpsat` from `seq_phys` gave completion 0.869 vs 0.859, place physics 1.67× vs 1.52×.

## Verdict

- **anneal: worked** (1 seed): more legal and clean boards, 8% less copper. Its best use is as the
  finishing stage of `combo`.
- **repair: worked as a stage.** Strong on completion (dev6 0.921) and the fastest way to fix a
  specific unrouted net; on ab33 alone it is close to anneal.
- **cpsat: did not work.** Exactness does not pay when the exact model cannot even route the window
  in the time a heuristic routes the whole board; pose choices then follow search noise and grid
  artefacts. Proposed instead (not done): exact joint choice among a few candidate poses per part,
  with pair costs measured by the engine's router (a small quadratic assignment).
- Caveats: single seed; engine changed later (v6 fixed DRC classes), so these are v5-only numbers.

`anneal`, `anneal_phys` and `repair` are arms of the merit list; the 500-board comparison
(`merit-500r3` / `merit-500r3k`) is running. Results on the 500-board comparison: pending.
`cpsat` is not a merit arm.

## Code

- [`tools/research/pnr/methods.py`](../../../tools/research/pnr/methods.py): `anneal`, `repair`,
  `blockers`; [`methods_phys.py`](../../../tools/research/pnr/methods_phys.py): `anneal_phys`;
  [`methods_combo.py`](../../../tools/research/pnr/methods_combo.py): `repair_phys`.
- [`tools/research/pnr_cpsat/cpsat_lns.py`](../../../tools/research/pnr_cpsat/cpsat_lns.py) (`cpsat`,
  options for window radius, time, lattice), `window_stats.py`. Needs `ortools`.

## Related

[combo.md](combo.md), [sequential-controls.md](sequential-controls.md); CP-SAT placement on synthetic
instances: `tools/research/solver-bench/` and [solver benchmarks](../../topics/solvers/benchmarks.md).
