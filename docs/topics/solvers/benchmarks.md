# Solver micro-benchmarks (CP-SAT, hierarchical CP-SAT + LNS, SA, geometry)

**TL;DR**
- Monolithic CP-SAT placement (4-way rotation, keep-outs, hard decap distance, exact pin HPWL) finds a first feasible solution in **0.24 s (N=30) → 5.9 s (100) → 15 s (150) → 73 s (200) → none in 300 s (300, 1000)** at 0.5 mm.
- **Free rotation is the main difficulty**: N=300 with fixed orientations is feasible in 82.6 s; without decap constraints still infeasible; a dedicated packing subsolver made N=300 feasible in 271 s.
- **Hierarchical CP-SAT + LNS** beats monolithic by 25–55% HPWL at N=100 in similar wall time and stays feasible at 300 (2,461 mm, 124 s) and 1000 (22,596 mm, 294 s).
- **SA beats CP-SAT on HPWL at small N** (202–223 mm in 4–5 s vs 218.5–243.5 mm after 60 s at N=30); CP-SAT's HPWL lower bound stays at 5–25% of the incumbent.
- Geometry: full exact re-check of a 1000-part board ≤5 ms; per-move Python checks 12–30 µs.

## Key facts

**Setup** [M]: 4 vCPU, 15 GB RAM, Python 3.13, OR-Tools 9.15.6755, Shapely 2.2.0, rtree 1.4.1, pyclipper 1.4.0, NumPy 2.5.4; CP-SAT `num_workers=4`. Synthetic instances from `pcbgen.py`: R/C 0402/0603, SOT-23, SOIC-8, QFN-32, TQFP-64, 2×5 headers at courtyard size; board aspect 1.5 at 45% utilization; 4 mounting-hole keep-outs (6×6 mm) + one edge keep-out; 2–4 decaps per IC with **hard decap-pin ↔ IC-VDD-pin L1 ≤ 3 mm**; 2–4-pin nets with cluster locality; 4-way rotation; pin-level exact HPWL. Scripts (`pcbgen.py`, `cpsat_place.py`, `hier_place.py`, `sa_place.py`, `geom_bench.py`, `pathfinder_bench.py`, `results*.jsonl`) were in the session scratchpad listed in [solver_toolbox.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md).

| N | Board (mm) | Nets | Decap constraints | CP-SAT vars |
|---|---|---|---|---|
| 30 | 32.7×20.7 | 43 | 5 | 322 |
| 100 | 51.9×32.9 | 109 | 25 | 1,080 |
| 300 | 98.1×62.3 | 323 | 65 | 3,248 |
| 1000 | 180×114 | 1,127 | 200 | 10,812 |

**A. Monolithic, time to first feasible** (no objective): N=30 0.24 s (0.5 mm) / 2.0 s (0.1 mm); N=100 5.9 s / 72 s; N=300 none in 300 s at both; N=1000 none in 300/323 s. Utilization did not drive difficulty at N=100 (6.2 s at 55%, 5.0 s at 65%, 5.8 s at 75%).

**B. Monolithic, HPWL in 60 s** (best @15/30/60 s [final lower bound]; "var" = variable-size interval rotation, "opt2" = two optional fixed-size intervals)
| N, grid | var | opt2 | no rotation |
|---|---|---|---|
| 30, 0.5 mm | 249 / 245 / 243.5 [55] | 233.5 / 225 / **218.5** [55] | – |
| 30, 0.1 mm | 255 / 226 / **222.8** [42] | 282 / 281 / 241.8 [11.8] | – |
| 100, 0.5 mm | 1300 / 784 / 643.5 [62.5] | 1172 / 771 / **616.5** [63] | 585.5 [299] |
| 100, 0.1 mm | 1009 (1st sol @45 s) [25] | **860** (1st @40 s) [22] | – |
| 300 / 1000 | no solution | no solution | no solution |
Two-sided N=100 (side literal, two NoOverlap2D): first solution 11.2 s, 396 mm after 60 s [bound 92]; N=300 two-sided none in 60 s.

**C. Hierarchical CP-SAT + LNS** (`hier_place.py`): per-IC-cluster CP-SAT (1 s) for 2 aspect variants (1:1, 2:1) → soft macros (connectors stay top-level) → top-level floorplan with one-hot (variant × 4 rotations), keep-outs, inter-cluster pin HPWL → flatten → windowed LNS (free 40 nearest parts, 2 s/iteration). First version with rigid square macros was **INFEASIBLE at N=30** (macros could not fit between corner keep-outs) → soft macros with aspect variants are necessary. All results 0 overlaps / 0 decap violations / 0 out-of-board / 0 keep-out intrusions.
| N, grid | Hierarchy only | + LNS | Wall time | Monolithic (60 s) |
|---|---|---|---|---|
| 100, 0.5 mm | 599.0 (31 s) | **480.5** | 71 s | 616.5–643.5 |
| 100, 0.1 mm | 584.1 (34 s) | **454.4** | 75 s | 860–1009 |
| 300, 0.5 mm | 2,826 (63 s; 26 clusters) | **2,461.5** | 124 s | none |
| 300, 0.1 mm | 2,793.8 (70 s) | **2,473.2** | 131 s | none |
| 1000, 0.5 mm | 22,963 (172 s; 87 clusters) | 22,595.5 (1/14 LNS moves accepted) | 294 s | none in 300 s |
| 1000, 0.1 mm | top-level floorplan of 87 macros: none in 60 s | – | 193 s | none |
At N=1000 each LNS iteration cost ~8.6 s for a 3 s solve (full-model cloning/presolve dominates).

**D. Ablation — what makes N ≥ 300 hard?** (first feasible, 0.5 mm, 300 s)
| Variant | Result |
|---|---|
| N=150 / N=200 full model | 15.0 s / 72.7 s |
| N=300 full model | none |
| N=300 without decap constraints | none (decap distance is **not** the bottleneck) |
| N=300 **fixed orientation** | **82.6 s** |
| N=300 "opt2" encoding | none |
| N=300 at 35% utilization | 173.7 s |
| N=300 + dedicated packing subsolver (area-energetic + energetic + timetabling NoOverlap2D reasoning, 5,000 pairwise pairs; 9.15 API fix) | **271 s** |
| N=100 seeds 0–3 | first feasible 4.0–5.9 s; 60 s HPWL 616–1,177 mm (~2× spread) |

**E. Simulated annealing** (`sa_place.py`): ~10–11k moves/s at N=30; legal 202–223 mm in 4–5 s; one run left 2 overlaps; CP-SAT LNS (3×2 s) could not improve a 202 mm SA result. The extended `{{SA}}` results section in the notes is **pending** at time of writing.

**F. Geometry** (`geom_bench.py`): see table in [geometry libraries](geometry-libraries.md) — NumPy AABB 11–23 µs/move, grid hash 13–16 µs, static STRtree ~24–27 µs, exact octagons 27–32 µs; full exact check 0.49 ms (100) → 4.95 ms (1000) → 15.7 ms (3000); pyclipper offset 12.7–14.6 µs.

**G. PathFinder prototype** (`pathfinder_bench.py`): formulation in [PathFinder](../routing/pathfinder-negotiated-congestion.md); results section `{{PF}}` **pending** in the notes.

## Recommendations for our system
- Monolithic CP-SAT only up to ~100 parts at 0.5 mm; hierarchical soft-macro floorplan + window sub-model LNS beyond; fix orientations upstream at scale; add one packing-subsolver worker; "opt2" encoding at N ≥ 100; average over seeds (2× HPWL spread) [M/I].
- Use SA (Rust) for HPWL quality and CP-SAT for legality; run the ≤5 ms exact check after each accepted move batch [M/I].
- Validate on real boards next (PCBWorld D3, Cypress small suite): synthetic instances bound scale, not quality [I].

## Conflicts and open questions
- Synthetic instances lack irregular outlines, many fixed parts, height/thermal/EMI rules.
- SA extended results, PathFinder results and an extra performance note are still placeholders in the source notes; re-check [solver_toolbox.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md) § 3, § 5, § 7.

## Sources
- research notes: [solver_toolbox.md § 1, § 3, § 6, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)
- Tags: [M] = measured by the notes' author in-session.

See also: [cp-sat-milp-smt](cp-sat-milp-smt.md) · [metaheuristics-and-qd](metaheuristics-and-qd.md) · [geometry-libraries](geometry-libraries.md)
