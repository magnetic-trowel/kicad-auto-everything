# Routed-cost annealing, blocker-directed repair, and exact CP-SAT windows

**Status:** annealing worked; blocker repair worked as a stage; CP-SAT windows did not work.
**First published:** 2026-10-24, commit [44831ff](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44831ff3f802b1758b9c1299e0ae0b212d581f9a) on branch `claude/keen-wright-mlkjv6` (CP-SAT windows: [6e5c658](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6e5c658f0ea7c268fe8d44682160bf7a820b4d4b), results [95265a6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/95265a6ac80097d86dea3a42a5b933b2667012bf)).

Scope: three local searches that judge a placement change by the copper the router actually lays; anneal and repair became stages of [combo](combo.md). Not here: CP-SAT placement on synthetic instances -> `tools/research/solver-bench/`, [solver benchmarks](../../topics/solvers/benchmarks.md).
Keys: anneal, anneal_phys, simulated annealing on routed cost, repair, repair_phys, blockers, LNS, guided local search, cpsat, CP-SAT window, Numberlink, SP&R, `NoOverlap2D`, ideas 11 12 13 36

## Idea and how it works

### anneal / anneal_phys (idea 11; VPR, Nag–Rutenbar 1998)
Simulated annealing over part poses from the `seq` placement.
- Moves: jump to a random legal pose nearby (radius shrinks with temperature), rotate in place, swap two parts.
- Each move rips up and re-routes only the affected nets, incrementally, with snapshot/restore of route state.
- Cost = `Kit.total_cost()` ([engine](engine.md)); `anneal_phys` adds `phys_w` · physics with physics-part moves ([physics-objective.md](physics-objective.md)).

### repair (ideas 12, 13; LNS + guided local search)
Until the budget ends:
1. Pick an unrouted net (or the most detoured one).
2. Route it *soft* (foreign copper priced, not forbidden); **blockers** = parts whose footprint lies under cells where the soft route crosses foreign copper.
3. Rip up the blockers plus the net's own parts.
4. Re-place them one by one, candidates scored by real routing (the `grow` step).
5. Keep if the board improved (`repair_phys`: accept on routed cost + w · physics).

### cpsat (idea 36; SP&R, Numberlink SAT) as the repair window solver
From `seq_phys`: pick an unrouted or most-detoured net and a window ≤ 9 mm with 2–3 movable parts; rip up those parts and every net touching or crossing the window. Model on a 0.6 mm, 2-layer grid:
- Boolean pose choice per part over current pose + top-6 candidates; `NoOverlap2D` per plane; pad halos exclude other nets.
- Each MST connection a Numberlink path: degree 1 at endpoints, 0 or 2 elsewhere; cells exclusive per net; a via clears its 8 neighbours; border exits priced by distance to the pins outside.
- Objective: 3000 per missed connection + length + 2 mm/via + exit cost + 2 · physics delta.
- Two phases: route with poses fixed (as assumptions, gives a hint), then free the poses. 1 worker, LP off, presolve off, 3 deterministic seconds.
- Decode, re-route with PathFinder, accept on routed cost + 2 · physics.

## What we tried

v5, 120 CPU-s, place tasks, **1 seed**: ab33 for `anneal`, `anneal_phys`, `repair`; dev6 and phys10 for `cpsat` with a dev6 repair control. Head-to-head on 28 identical windows and states × 4 CP-SAT model variants (lattice, LP on, radius 3) = 112 runs. An earlier multi-commodity flow encoding was abandoned.

## Results

ab33, v5, seed 0 ([drc-v5-ab33.md](../../../tools/research/pnr/results/drc-v5-ab33.md); `seq` control row → [sequential-controls.md](sequential-controls.md#results)):

| run | legal | clean | completion | length mm (21 boards) | vias |
|---|---|---|---|---|---|
| **anneal** | **0.848** | **0.576** | 0.874 | 3048 (−8% vs seq) | 32 |
| anneal_phys | 0.818 | 0.576 | 0.876 | 3145 | 32 |
| repair | 0.818 | 0.545 | 0.873 | 3054 | 33 |

Routed physics (phys10): → [physics-objective.md](physics-objective.md#results). Olimex buck: `anneal_phys` place physics 5.83 vs human 7.39, DRC clean; the HPWL placement scores 51–1400 depending on the engine version.

dev6, v5, seed 0 ([pnr_cpsat/RESULTS.md](../../../tools/research/pnr_cpsat/RESULTS.md)):

| run | legal | clean | completion | length (4 boards) | wall s |
|---|---|---|---|---|---|
| seq | 0.667 | 0.667 | 0.904 | 682 | 45 |
| **repair** (control) | **0.833** | 0.500 | **0.921** | **594** | 214 |
| same loop, no CP-SAT | 0.667 | 0.667 | 0.908 | 681 | 257 |
| cpsat (3 s) | 0.667 | 0.667 | 0.908 | 680 | 353 |
| cpsat (10 s) | 0.667 | 0.667 | 0.908 | 685 | 205 |

- ~750 CP-SAT windows; none OPTIMAL (FEASIBLE, INFEASIBLE or UNKNOWN).
- Routing alone does not converge: a 5-connection window (8k variables) scored 672 at 1 s, 404 at 3 s, 292 at 10 s, unproven at 30 s. At 3 s ≥ 1 connection left unrouted in 40% of dev6 windows on boards the engine routes completely.
- Head-to-head: repair improved 14 of 28 windows; CP-SAT moved a part in 17 of 112 runs, improved the board in 6, **beat the heuristic in 0 of 112**.
- Flow encoding: a flow per net missed 9 of 16 terminals with parts fixed after 30 s on 4 workers.
- phys10: `cpsat` from `seq_phys`: completion 0.869 vs 0.859, place physics 1.67× vs 1.52×.

## Verdict

- **anneal: worked** (1 seed): more legal and clean boards, 8% less copper; best use is the finishing stage of `combo`.
- **repair: worked as a stage**: strong on completion (dev6 0.921), fastest fix for a specific unrouted net; on ab33 alone close to anneal.
- **cpsat: did not work.** The exact model cannot route the window in the time a heuristic routes the whole board; pose choices then follow search noise and grid artefacts. Proposed (not done): exact joint choice among a few candidate poses per part with pair costs measured by the engine's router (a small quadratic assignment).
- Caveats: single seed; v5-only numbers (v6 fixed DRC classes).
- Merit arms: `anneal`, `anneal_phys`, `repair`; `cpsat` is not ([merit list](README.md#merit-list)).

## Code

- [`tools/research/pnr/methods.py`](../../../tools/research/pnr/methods.py): `anneal`, `repair`, `blockers`; [`methods_phys.py`](../../../tools/research/pnr/methods_phys.py): `anneal_phys`; [`methods_combo.py`](../../../tools/research/pnr/methods_combo.py): `repair_phys`.
- [`tools/research/pnr_cpsat/cpsat_lns.py`](../../../tools/research/pnr_cpsat/cpsat_lns.py) (`cpsat`, options for window radius, time, lattice), `window_stats.py`. Needs `ortools`.

## Related

[combo.md](combo.md), [sequential-controls.md](sequential-controls.md).
