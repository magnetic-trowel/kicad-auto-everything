# Performance engineering and multi-fidelity evaluation

Scope: Python/Rust split, parallelism, measured Python ceilings, the L0–L4 evaluation ladder. Not here: full benchmark tables -> [solver benchmarks](benchmarks.md); proxy-score learning -> [learned scores](../data/imitation-and-learned-scores.md).
Keys: Rust, PyO3, maturin, cffi, uniffi, GPU, parallelism, multi-fidelity, evaluation ladder, L0, L1, L2, L3, L4, proxy correlation, clean-pass, OrthoRoute, KRT, Rustuna

## Python/Rust split

- Python: orchestration, CP-SAT models, Optuna, KiCad IPC I/O, LLM tool layer. Rust via PyO3/maturin: incremental HPWL (per-net min/max with counts), grid-hash overlap, RUDY bins, SA moves, A*/PathFinder, optional jagua-rs exact collision [I].
- maturin 1.15.0 ("MIT OR Apache-2.0") builds PyO3, cffi and uniffi crates ([PyPI](https://pypi.org/pypi/maturin/json) [P]).
- KRT: "Rust acceleration provides ~10x speedup vs pure Python" [P]; Rustuna several–several-hundred× faster than Optuna for cheap objectives [P]; jagua-rs: millions of collision queries per second [P].
- No direct Rust-vs-Python measurement for placement kernels beyond KRT's routing claim; our numbers are Python-only ceilings.

## Measured Python ceilings

[C]; sources → [benchmarks](benchmarks.md), [geometry](geometry-libraries.md#measured-collision-check-cost).

| Kernel | Measured |
|---|---|
| SA moves (Python + NumPy, 1 thread) | 9.0–11.7k moves/s, N=30–1000 |
| Per-move collision check | 12–30 µs |
| PathFinder, Python heapq A* (76.8k nodes, 2 layers) | 2.2 s / 50 nets; 13.0 s / 150; 32.7 s / 300; 60.9 s / 300 on 4 layers (153.6k nodes); 15 iterations each |
| Same, SciPy C Dijkstra (full tree, CSR rebuilt per net) | 4.7 s / 50 nets: 2× *slower* than Python A* (search strategy beats language) |
| CP-SAT model build | 0.01 s (N=30) → 0.2 s (N=1000) |
| LNS iteration via full-model clone at N=1000 | ~8.6 s for a 3 s solve (clone + presolve dominate) |
| Per-violation-cluster window sub-models at N=1000 | 41 windows legalized in 3.9 s total |
| Hierarchical cluster solves | 112 s for 87 clusters × 2 variants, embarrassingly parallel |

- Never clone the full CP-SAT model per LNS/legalization step at ≥1000 parts: build window sub-models (free parts as variables, neighbours fixed, external pins constant) [C].

## Parallelism and GPU

- Parallel units: CP-SAT worker portfolio; cluster solves (hierarchical scheme); Optuna trials [I].
- GPU pays off only at Cypress scale (thousands of parts) or huge routing lattices: DREAMPlace GPU >30× on million-cell VLSI; Cypress small benchmarks 200–1,765 s on 4 V100s incl. MOTPE exploration [P].
- OrthoRoute parallelizes inside a single-net SSSP; nets stay sequential [P].

## Multi-fidelity evaluation ladder

Every published PCB placer ends its ladder at a real router (Freerouting) and/or KiCad DRC ([solver_toolbox.md § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)).

| Level | Check | Cost |
|---|---|---|
| L0 | HPWL + hard-constraint check | µs |
| L1 | RUDY + net-crossing proxy (Cypress) | ms |
| L2 | Coarse PathFinder (capped iterations) | seconds |
| L3 | Freerouting headless / KRT / in-house router | seconds–minutes (Freerouting: "a few minutes to several hours" on big boards) |
| L4 | `kicad-cli pcb drc` + PCBWorld-style clean-pass (routability = 1 AND 0 DRC errors; 62 `DRCE_*` codes) | final |

Evidence:
- Cypress: Freerouting v1.9.0, 2 layers, % routed pin pairs; MOTPE objectives Freerouting routability + track length (VP-corrected), so a real router runs inside each tuning trial; net crossing cut crossings to 0.31× at 1.13× HPWL [P].
- NS-Place: FreeRouting routed WL/vias + KiCad DRVs [P]. PCBWorld: Freerouting 2.7–9.9 s per board on D2/D3 [P].
- DREAMPlace RUDY/RISA area adjustment (`adjust_rudy_area_flag`); SMAC multi-fidelity; Freerouting fidelity knobs `-mp`, `-mt 0`, `--router.optimizer.improvement_threshold` [P]; final runs `-mt 1` (multi-threaded optimization is known to create clearance violations).
- Apollo: wirelength/density placers can score ~51% routability on its domain [S].
- Freerouting versions differ across papers, so their results are not comparable → [freerouting](../routing/freerouting.md).
- Published correlation between routing proxies and PCB router completion is scarce and weak: one unreviewed third-party 64-board study, one Cadence patent dataset of one board → [learned scores](../data/imitation-and-learned-scores.md).

Rules [I]:
- Calibrate L1/L2 proxies against Freerouting-on-2-layers (L3) on a held-out set: PCBWorld D3 boards outside the 99 D3-A + 10 D3-B evaluation boards (never calibrate on those); Cypress small suite once outlines are synthesized (its KiCad files have none). Check rank correlation before using proxies in Optuna.
- Expose `evaluate(candidate, level)` to the LLM so L3/L4 are spent only on Pareto finalists.

## Sources

- [solver_toolbox.md § 7, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)
