# Joint vs sequential placement and routing: a proof of concept

**TL;DR**
- RESULT1
- RESULT2
- RESULT3
- RESULT4
- These are synthetic 2-layer grid boards with a Python router; they bound mechanisms and costs, not real-board quality.

## Key facts

### Setup [C]

Script: [`tools/research/physics/jpr_joint_vs_sequential.py`](../../../tools/research/physics/jpr_joint_vs_sequential.py) (GPL-3.0-or-later; Python 3.11+, NumPy, Shapely). Raw JSON lines are not committed; rerun with the commands below.

| Item | Value |
|---|---|
| Instances | `pcbgen.make_instance` from [solver-bench](../../../tools/research/solver-bench/) at N = 30, 50 (seeds 0–4) and 80 (seeds 0–1), utilization 0.6: R/C 0402/0603, SOT-23, SOIC-8, QFN-32, TQFP-64, 2×5 headers; 4 mounting-hole keep-outs (6×6 mm) and an antenna-style edge keep-out; decaps with an L1 ≤ 3 mm rule |
| Added physics | 1–2 **hot loops** per board: an IC VIN pin → C0603 → an adjacent IC GND pin, as two 2-pin nets |
| Boundary condition | One 2×5 header fixed at the bottom edge, centred; parts may not leave the outline (hard domain constraint) |
| Router | 2-layer grid at 0.5 mm pitch (track + clearance), node capacity 1; SMD pads block the top layer, THT pads both; via = 4 steps; bottom-layer steps cost 2× (the bottom is meant to stay a solid ground plane) |
| Referee | PathFinder (VPR-like: first pass free, then present factor 0.5 × 1.3 per pass, history +1 per overuse, ≤ 40 passes, reroute offenders only) routing each **final placement from scratch**, same for every arm |
| Legalizer | Greedy spiral repair of any part still overlapping a part or keep-out, applied to every arm's final placement |
| Routed objective J (mm-equivalent) | wirelength + 2·vias + 1·bottom-layer length + 4·hot-loop area (mm²) + 40·failed nets + 100·(overlaps + keep-out intrusions + decap violations) |
| Hot-loop area | Enclosed area of the routed VIN path + GND path (lobes add, Shapely `make_valid`) + 1.5 mm × loop length on the bottom layer |

**Arms.** Budgets are process CPU seconds (the machine was shared with other jobs, so wall time was not usable); TP = 10 s, TJ = 40 s, B = TP + TJ = 50 s.

| Arm | What it does | CPU |
|---|---|---|
| `seq` | SA on HPWL + straight-line hot-loop area proxy + penalties, then referee | TP |
| `seqx` | `seq` plus a net-crossing proxy (0.5 mm per crossing of star-decomposed nets; best of {0.5, 1.5, 3} on held-out seed 9) | TP |
| `seq_long` | `seq` SA for the whole budget | B |
| `seq_port` | `seq`, then restarts from new random placements (each SA + referee) until B is spent; keep the best J | B |
| `joint` | `seq`'s placement and its referee routes as the start; SA whose every move rips up and A*-reroutes the affected nets (nets on moved parts plus nets crossing their new pads) and is accepted on the routed objective (J terms + an overflow penalty ramping 2→40 mm per overused node + placement penalties); then the referee re-routes from scratch | TP + TJ = B |
| `joint_nophys` | as `joint`, but the optimizer ignores hot-loop area and bottom-layer length (router costs unchanged) | B |

Commands: `python jpr_joint_vs_sequential.py --n 30 --seed 0 --util 0.6 --tp 10 --tj 40` (all six arms by default).

### Results

RESULTS_TABLES

## Recommendations for our system

RECS

## Conflicts and open questions

OPEN

## Sources
- Script: [`tools/research/physics/jpr_joint_vs_sequential.py`](../../../tools/research/physics/jpr_joint_vs_sequential.py); instance generator and earlier PathFinder and SA measurements: [solver benchmarks](../solvers/benchmarks.md)
- Prior art for the method: Starfish (ICCAD'21) and PROXI (ICCAD'95), see [joint-place-route](joint-place-route.md)

See also: [joint-place-route](joint-place-route.md) · [ideas: joint placement and routing](../../ideas/physics-first/joint-place-route.md) · [pathfinder-negotiated-congestion](../routing/pathfinder-negotiated-congestion.md) · [metaheuristics-and-qd](../solvers/metaheuristics-and-qd.md) · [performance-and-multifidelity](../solvers/performance-and-multifidelity.md)
