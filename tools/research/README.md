# Research scripts

One-off measurement scripts from the survey. They are research quality, not
library code; results are written up in the docs linked below.

## `solver-bench/`: placement and routing solver micro-benchmarks

Results and interpretation: [docs/topics/solvers/benchmarks.md](../../docs/topics/solvers/benchmarks.md).

| Script | What it does |
|---|---|
| `pcbgen.py` | Synthetic PCB-like instances: footprint mix, mounting-hole and edge keep-outs, decaps tied to IC power pins, local nets |
| `cpsat_place.py` | Single-model CP-SAT placer: two rotation encodings, optional two-sided placement, keep-outs, hard decap distance, pin-level HPWL, optional packing subsolver (OR-Tools 9.15 API) |
| `hier_place.py` | Hierarchical CP-SAT (cluster macros with aspect variants, then top-level floorplan) plus windowed LNS; shared `check`, `violators`, `legalize`, `lns_polish` helpers |
| `legalize_clusters.py` | Per-violation-cluster CP-SAT legalizer for nearly legal placements (one small model per window) |
| `sa_place.py` | Simulated-annealing baseline with optional CP-SAT legalization/LNS polish and position dump |
| `geom_bench.py` | Incremental clearance-check timing (NumPy, grid hash, rtree, Shapely STRtree, exact polygons) and offsetting (pyclipper vs Shapely) |
| `pathfinder_bench.py` | Negotiated-congestion (PathFinder) grid router prototype: Python A* vs SciPy Dijkstra |
| `run_*.sh` | The experiment matrices behind the published numbers; outputs go to `results/` |

Requirements: Python 3.11+, `ortools` (tested 9.15), `numpy`, `scipy`,
`shapely` (2.x), `rtree`, optionally `pyclipper`. Run e.g.
`python3 cpsat_place.py 100 0.5 60` or `PY=/path/to/python ./run_sa.sh`.
Most results are single-seed; plain CP-SAT varied ~2x across seeds.

## `layout-data/`: measurements on open-source KiCad boards

| Script | What it does |
|---|---|
| `decap_stats.py` | Heuristic decap-to-IC-power-pin distance statistics from `.kicad_pcb` files (stdlib only) |

Results: [docs/topics/data/measured-priors.md](../../docs/topics/data/measured-priors.md).
Input boards are third-party and are not redistributed here; see
[docs/topics/data/licensing-tiers-and-contamination.md](../../docs/topics/data/licensing-tiers-and-contamination.md).

## Licensing

Scripts are GPL-3.0-or-later; `solver-bench/results/*.jsonl` are
CDLA-Permissive-2.0 (see [LICENSING.md](../../LICENSING.md)).
