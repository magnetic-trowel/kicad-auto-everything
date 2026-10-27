# Research code

The code behind every research path: experiments, prototypes and measurement
scripts. It is research quality, not library code. Each path is written up in
[docs/research](../../docs/research/README.md): how it works, what we tried, the
numbers, and whether it worked. The production placer and router live in the
[`kae`](../../kae/) package; its research scripts are under `physics/`, `place/`,
`routing/` and `joint/` here.

| Directory | What it is | Write-up |
|---|---|---|
| `pnr/` | pnr joint place-and-route engine (grid world, PathFinder/A* router with the fast router, anytime output) and its base methods: seq, anneal, repair, negotiate, combo | [engine](../../docs/research/joint/engine.md), [sequential controls](../../docs/research/joint/sequential-controls.md), [anneal and repair](../../docs/research/joint/anneal-and-repair.md), [combo](../../docs/research/joint/combo.md) |
| `pnr_phys/` | physics terms in the pnr objective, physics scorer | [physics objective](../../docs/research/joint/physics-objective.md) |
| `pnr_mcts/` | beam search and MCTS over placements | [tree search](../../docs/research/joint/tree-search.md) |
| `pnr_cpsat/` | CP-SAT window re-placement | [anneal and repair](../../docs/research/joint/anneal-and-repair.md) |
| `pnr_grad/`, `pnr_slime/` | soft-route gradients; Physarum routing | [forces and fields](../../docs/research/joint/forces-and-fields.md) |
| `pnr_llm/` | LLM move proposer | [LLM proposer](../../docs/research/joint/llm-proposer.md) |
| `collapse_joint/` | jc / jc2: layer-collapsed joint place-and-route | [jc](../../docs/research/joint/jc.md) |
| `collapse_assign/`, `collapse_cplace/`, `collapse_obst/` | layer-count bounds, exact layer assignment, collapse terms in placement | [layer-collapse analysis](../../docs/research/joint/layer-collapse-analysis.md) |
| `collapse_pour/`, `xf_pour/` | minimal-partition pours; pour-damage maps (pjc2) | [pour models](../../docs/research/joint/pour-models.md) |
| `harmonic/`, `qd_archive/`, `learn_value/`, `xf_minplus/`, `xf_physmap/` | extensions of jc: harmonic fields, QD archive, learned value, min-plus maps, exact physics maps | [jc extensions](../../docs/research/joint/jc-extensions.md) |
| `xf_common/` | shared launcher and helpers for the pnr experiments | [engine](../../docs/research/joint/engine.md) |
| `physics/` | physics models, critics, derivation and validation scripts of the physics-first line | [physics](../../docs/research/physics/README.md) |
| `place/`, `routing/`, `joint/` | experiment drivers for kae's placer, router and joint loop | [placement](../../docs/research/placement/README.md), [routing](../../docs/research/routing/README.md), [kae joint loop](../../docs/research/joint/kae-joint-loop.md) |
| `autoplace/` | annealing placer with the router and DRC in the loop | [autoplace](../../docs/research/placement/autoplace.md), [with kae's router](../../docs/research/placement/autoplace-kae-router.md) |
| `llm-design/` | kaesynth: typed circuit description to checked KiCad schematic, plus four LLM-made designs | [kaesynth](../../docs/research/llm-design/kaesynth.md) |
| `board-sourcing/` | open-board corpus: licence audit, dedup, import | [board corpus](../../docs/research/data/board-corpus.md) |
| `solver-bench/`, `layout-data/` | survey micro-benchmarks and board measurements (below) | below |

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
Most results are single-seed. `--seed` in `cpsat_place.py` also seeds the instance
generator, so the ~2x spread of plain CP-SAT across seeds 0–3 compares four different
boards (instance variance), not solver noise on one board.

## `layout-data/`: measurements on open-source KiCad boards

| Script | What it does |
|---|---|
| `decap_stats.py` | Heuristic decap-to-IC-power-pin distance statistics from `.kicad_pcb` files (stdlib only) |

Results: [docs/topics/data/measured-priors.md](../../docs/topics/data/measured-priors.md).
Input boards are third-party and are not redistributed here; see
[docs/topics/data/licensing-tiers-and-contamination.md](../../docs/topics/data/licensing-tiers-and-contamination.md).

## Licensing

Scripts are GPL-3.0-or-later; `*/results/*.jsonl` are CDLA-Permissive-2.0; a
KiCad-library footprint and generated schematics under `llm-design/` carry
CC-BY-SA-4.0 with the KiCad libraries exception (see [LICENSING.md](../../LICENSING.md)
and `REUSE.toml`).
