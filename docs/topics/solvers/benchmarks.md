# Solver micro-benchmarks (CP-SAT, hierarchical CP-SAT + LNS, SA, geometry)

Scope: our synthetic-instance measurements of placement solvers, geometry kernels and a PathFinder prototype; canonical home of these numbers. Not here: solver APIs and formulations -> [CP-SAT/MILP/SMT](cp-sat-milp-smt.md); geometry library choice -> [geometry libraries](geometry-libraries.md).
Keys: CP-SAT, NoOverlap2D, monolithic, hierarchical, soft macro, LNS, window sub-model, simulated annealing, SA, legalization, legalize_clusters.py, opt2, var encoding, fixed orientation, HPWL, lower bound, PathFinder, A*, Dijkstra, pcbgen.py, solver-bench

**Results** (single instances throughout; [C] = measured in-session by the solver-bench scripts)
1. Monolithic CP-SAT first feasible at 0.5 mm: 0.24 s (N=30) → 5.9 s (100) → 15 s (150) → 73 s (200) → none in 300 s (300, 1000; UNKNOWN, not an infeasibility proof).
2. Free 4-way rotation is the main difficulty: N=300 fixed-orientation feasible in 82.6 s; dropping decap constraints does not help; a dedicated packing subsolver gives 271 s.
3. Hierarchical CP-SAT + LNS beats monolithic by 22–55% HPWL at N=100 in similar wall time; feasible at 300 (2,461 mm, 124 s) and 1000 (22,596 mm, 294 s).
4. SA (wirelength) + CP-SAT (legality) beats monolithic at N=30–100 by 4–46% (median ≈20%); hierarchical wins at N=100 (480.5 vs 503.5 mm at 0.5 mm; 454.4 vs 465.9 mm at 0.1 mm); SA wins at N=300 (2,278 vs 2,461.5 mm, ~249 vs 124 s) and N=1000 (legal 13,774 vs 22,596 mm). CP-SAT HPWL lower bound = 2.5–25% of incumbent with rotation, 51% with fixed orientation.
5. Exact full re-check of a 1000-part board ≤5 ms; per-move Python checks 12–30 µs. Python A* PathFinder converges in 15 iterations for 50–300 nets (2.2–61 s); goal-directed A* beat SciPy's C Dijkstra 2×.

## Setup and instances

4 vCPU, 15 GB RAM, Python 3.13, OR-Tools 9.15.6755, Shapely 2.2.0, rtree 1.4.1, pyclipper 1.4.0, NumPy 2.5.4; CP-SAT `num_workers=4` [C].
Instances (`pcbgen.py`): R/C 0402/0603, SOT-23, SOIC-8, QFN-32, TQFP-64, 2×5 headers at courtyard size; board aspect 1.5, 45% utilization; 4 mounting-hole keep-outs (6×6 mm) + 1 edge keep-out; 2–4 decaps per IC with **hard decap-pin ↔ IC-VDD-pin L1 ≤ 3 mm**; 2–3-pin nets with cluster locality, no power/ground nets (decap GND pins left to an implied plane); 4-way rotation; exact pin-level HPWL.
Scripts (`pcbgen.py`, `cpsat_place.py`, `hier_place.py`, `sa_place.py`, `legalize_clusters.py`, `geom_bench.py`, `pathfinder_bench.py`, `results*.jsonl`): [`tools/research/solver-bench/`](../../../tools/research/solver-bench/), raw results in `results/`.

| N | Board (mm) | Nets | Decap constraints | CP-SAT vars |
|---|---|---|---|---|
| 30 | 32.7×20.7 | 43 | 5 | 322 |
| 100 | 51.9×32.9 | 109 | 25 | 1,080 |
| 300 | 98.1×62.3 | 323 | 65 | 3,248 |
| 1000 | 180×114 | 1,127 | 200 | 10,812 |

## A. Monolithic, time to first feasible

No objective. N=30: 0.24 s (0.5 mm) / 2.0 s (0.1 mm). N=100: 5.9 s / 72 s. N=300: none in 300 s at both. N=1000: none in 300/323 s. Utilization does not drive difficulty at N=100: 6.2 s at 55%, 5.0 s at 65%, 5.8 s at 75% [C].

## B. Monolithic, HPWL in 60 s

Cells: best HPWL mm @15/30/60 s [final lower bound]. "var" = variable-size interval rotation; "opt2" = two optional fixed-size intervals.

| N, grid | var | opt2 | no rotation |
|---|---|---|---|
| 30, 0.5 mm | 249 / 245 / 243.5 [55] | 233.5 / 225 / **218.5** [55] | – |
| 30, 0.1 mm | 255 / 226 / **222.8** [42] | 282 / 281 / 241.8 [11.8] | – |
| 100, 0.5 mm | 1300 / 784 / 643.5 [62.5] | 1172 / 771 / **616.5** [63] | 585.5 [299] |
| 100, 0.1 mm | 1009 (1st sol @45 s) [25] | **860** (1st @40 s) [22] | – |
| 300 / 1000 | no solution | no solution | no solution |

Two-sided N=100 (side literal, two NoOverlap2D): first solution 11.2 s, 396 mm at 60 s [bound 92]; N=300 two-sided: none in 60 s [C]. 0.1 mm grid makes first-feasible 12× slower at N=100.

## C. Hierarchical CP-SAT + LNS

`hier_place.py`: per-IC-cluster CP-SAT (1 s) for 2 aspect variants (1:1, 2:1) → soft macros (connectors stay top-level) → top-level floorplan, one-hot (variant × 4 rotations), keep-outs, inter-cluster pin HPWL → flatten → windowed LNS (40 nearest parts free, 2 s/iteration). Rigid square macros: **INFEASIBLE at N=30** (macros do not fit between corner keep-outs), so soft macros with aspect variants are required. All results: 0 overlaps, 0 decap violations, 0 out-of-board, 0 keep-out intrusions [C].

| N, grid | Hierarchy only | + LNS | Wall time | Monolithic (60 s) |
|---|---|---|---|---|
| 100, 0.5 mm | 599.0 (31 s) | **480.5** | 71 s | 616.5–643.5 |
| 100, 0.1 mm | 584.1 (34 s) | **454.4** | 75 s | 860–1009 |
| 300, 0.5 mm | 2,826 (63 s; 26 clusters) | **2,461.5** | 124 s | none |
| 300, 0.1 mm | 2,793.8 (70 s) | **2,473.2** | 131 s | none |
| 1000, 0.5 mm | 22,963 (172 s; 87 clusters) | 22,595.5 (1/14 LNS moves accepted) | 294 s | none in 300 s |
| 1000, 0.1 mm | top-level floorplan of 87 macros: none in 60 s | – | 193 s | none |

N=1000: each LNS iteration costs ~8.6 s for a 3 s solve (full-model cloning/presolve dominates). Cluster solves: 112 s for 87 clusters × 2 variants, embarrassingly parallel.

## D. Ablation: what makes N ≥ 300 hard

First feasible, 0.5 mm, 300 s budget.

| Variant | Result |
|---|---|
| N=150 / N=200 full model | 15.0 s / 72.7 s |
| N=300 full model | none |
| N=300 without decap constraints | none (decap distance not the bottleneck) |
| N=300 **fixed orientation** | **82.6 s** |
| N=300 "opt2" encoding | none |
| N=300 at 35% utilization | 173.7 s |
| N=300 + dedicated packing subsolver (area-energetic + energetic + timetabling NoOverlap2D reasoning, 5,000 pairwise pairs; 9.15 API fix) | **271 s** |
| N=100 seeds 0–3 | first feasible 4.0–5.9 s; 60 s HPWL 643.5–1,176.5 mm ("var"; 616.5 is "opt2" on seed 0) |

`cpsat_place.py --seed` also seeds the instance generator (`make_instance`): seeds 0–3 are four boards (95–124 nets, 21–25 decaps), so the ~2× spread is instance variance, not solver noise. Separate instance seeds from solver seeds before averaging.

## E. Simulated annealing + CP-SAT legalization/polish

`sa_place.py`: pure Python + NumPy, single thread; cost = HPWL + λ(t)·(overlap + keep-out + out-of-board area + 3·decap excess); λ ramp 0.5→200, geometric cooling; moves shift/rotate/swap; 9.0–11.7k moves/s for N=30–1000. HPWL mm, legal unless noted; CP-SAT 4 workers; seed = instance seed [C].

| N, grid (seed) | SA alone | → CP-SAT legalize | → + CP-SAT LNS | Hier. + LNS | Monolithic 60 s |
|---|---|---|---|---|---|
| 30, 0.5 (0) | 195.5 (10 s) | – | **182.0** (+20 s) | – | 218.5–243.5 |
| 30, 0.1 (0) | 241.5, 1 decap viol. | 243.9 (3.8 s) | **214.6** (+20 s) | – | 222.8–241.8 |
| 100, 0.5 (0) | 521.5 (60 s) | – | 503.5 (+60 s) | **480.5** (71 s) | 616.5–643.5 |
| 100, 0.1 (0) | 490.1 (60 s) | – | 465.9 (+60 s) | **454.4** (75 s) | 860–1,009 |
| 100, 0.5 (1) | 691, 1 overlap | 699 (3.8 s) | **664** (+30 s) | – | 858.5 |
| 100, 0.5 (2) | 525.5 | – | **517.5** (+30 s) | – | 681.0 |
| 300, 0.5 (0) | 2,316, 1 decap viol. (120 s) | 2,316 (6.9 s) | **2,278** (+122 s) | 2,461.5 | none |
| 300, 0.1 (0) | 2,467.1 (120 s) | – | **2,399.2** (+120 s) | 2,473.2 | none |
| 1000, 0.5 (0) | 13,552.5, 16 overlaps + 2 decap (240 s) | full-board: none in 120 s; **cluster-wise: legal 13,773.5 in 3.9 s** | – | 22,595.5 | none |

N=1000 SA residue: four runs (240–300 s) ended at 12,093–13,552 mm with 8–25 overlaps ([solver_toolbox.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)). Committed in `results/`: 12,267.5 mm / 25 overlaps (240 s, `results_sa1000w.jsonl`); 12,843 mm / 16 overlaps + 2 out-of-board (300 s, `results_sa.jsonl`); 13,552.5 mm legalizer input (`results_sa1000_legal.jsonl`, no record of its SA run). The 12,093 mm / 8-overlap run is not committed.

Legalizer at N=1000:
- Full-model clone freeing k=30 neighbours of *every* violator in one model: did not finish in a 10-min budget.
- `legalize_clusters.py`: one small model per violation cluster; 12 nearest parts free inside window bbox +3 mm; overlapping parts and decap partners fixed; min L1 displacement; 3 s/window; k ×1.6 on failure. Result: 41 windows in 3.9 s.
- Rule: legalize full-board up to ~300 parts, per violation cluster beyond; never clone the full model per window (window sub-model: free parts as variables, neighbours fixed, external pins constant) [C].

This SA lacks clustering and legalization-aware moves: a lower bar for SA.

## F. Geometry kernels

`geom_bench.py`; table in [geometry libraries](geometry-libraries.md#measured-collision-check-cost). NumPy AABB 11–23 µs/move, grid hash 13–16 µs, static STRtree ~24–27 µs, exact octagons 27–32 µs; full exact check 0.49 ms (100) → 4.95 ms (1000) → 15.7 ms (3000); pyclipper offset 12.7–14.6 µs. CP-SAT model build 0.01 s (N=30) → 0.2 s (N=1000) [C].

## G. PathFinder prototype

`pathfinder_bench.py`; formulation in [PathFinder](../routing/pathfinder-negotiated-congestion.md). Grid 60×40 mm, 0.25 mm pitch (76,800 nodes / 382,400 edges for 2 layers); random 2-pin nets (pins unique, ≥2 cells apart); pad-blob obstacles on top; via cost 8; VPR schedule (pres_fac 0→0.5→×1.3, acc_fac 1); reroute overused nets only.

| Nets, layers | Engine | Route time | Iterations to 0 overuse | Vias |
|---|---|---|---|---|
| 50, 2 | Python heapq A* | **2.2 s** | 15 | 10 |
| 50, 2 | SciPy C Dijkstra (full tree, CSR rebuilt per net) | 4.7 s | 14 | 4 |
| 150, 2 | Python A* | 13.0 s | 15 | 88 |
| 300, 2 | Python A* | 32.7 s | 15 | 332 |
| 300, 4 | Python A* | 60.9 s | 15 | 342 |

- Goal-directed search beats raw C speed; convergence in 14–15 iterations (VPR default cap 50) [C].
- 2→4 layers (153.6k nodes) doubles runtime, barely changes results (2-via hop cost 16 > early congestion penalties).
- A generator allowing shared/abutting pin nodes never converged at 150/300 nets (5 and 13 overused nodes after 50 iterations): reserve pins and pad escapes per net before negotiation.
- 2-pin nets, no rule geometry: bounds algorithmic cost, not routing quality.

## Rules drawn from these runs

- Monolithic CP-SAT only up to ~100 parts at 0.5 mm; hierarchical soft-macro floorplan + window sub-model LNS beyond; fix orientations upstream at scale; add one packing-subsolver worker [C/I].
- "opt2" encoding at N ≥ 100 rests on one instance; every hierarchical/LNS/legalization run used "var".
- SA (Rust) for HPWL, CP-SAT for legality; ≤5 ms exact check after each accepted move batch [C/I].
- Router core: goal-directed A* with bounding windows + PathFinder (VPR schedule) in Rust [C/I].
- Validate on real boards next (PCBWorld D3; Cypress small suite after synthesizing outlines: its KiCad files have no Edge.Cuts outline, no copper and a stale net table, see [open board sources](../data/open-board-sources.md)): synthetic instances bound scale, not quality [I].

## Open questions

- Synthetic instances lack irregular outlines, many fixed parts, height/thermal/EMI rules, and high-fanout power/ground nets (all nets 2–3 pins).
- Hierarchical vs SA ordering flips with N (hierarchical better at 100, SA from 300) on single seeds; repeat on real boards before fixing the default pipeline. Small differences (454 vs 466 mm at N=100) need repeated solver seeds on one instance.

## Sources

- [solver_toolbox.md § 1, § 3, § 5, § 6, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)
