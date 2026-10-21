# Performance engineering and multi-fidelity evaluation

**TL;DR**
- Keep orchestration, CP-SAT models, Optuna, KiCad IPC I/O and the LLM tool layer in **Python**; put hot loops (incremental HPWL, overlap hash, RUDY, SA moves, A*/PathFinder, exact collision) in **Rust via PyO3/maturin** — KRT reports ~10× from moving A* to Rust; our Python SA manages only 9–12k moves/s (N=30–1000) and Python A*+PathFinder needs 33 s for 300 nets on a 77k-node grid.
- Parallelism: CP-SAT's worker portfolio, embarrassingly parallel cluster solves (hierarchical scheme), parallel Optuna trials. **GPU pays off only at Cypress scale (thousands of parts)** or huge routing lattices.
- Every published PCB placer ends its evaluation ladder at a **real router** (Freerouting) and/or KiCad DRC; we use a 5-level ladder L0 (µs) → L4 (final DRC + clean-pass).
- **No published correlation between RUDY/net-crossing proxies and PCB router completion exists** — calibrate proxies on held-out boards before trusting them inside tuners.

## Key facts

**Performance**
- maturin 1.15.0 ("MIT OR Apache-2.0") builds PyO3, cffi and uniffi crates ([PyPI](https://pypi.org/pypi/maturin/json) [P]).
- KRT: "Rust acceleration provides ~10x speedup vs pure Python" [P]; Rustuna several–several-hundred× faster than Optuna for cheap objectives [P].
- DREAMPlace GPU >30× on million-cell VLSI; Cypress small benchmarks 200–1,765 s on 4 V100s incl. MOTPE exploration [P].
- OrthoRoute parallelizes inside a single-net SSSP; nets stay sequential [P].
- jagua-rs: millions of collision queries per second [P].
- Measured Python ceilings [M] ([benchmarks](benchmarks.md)):
| Kernel | Measured |
|---|---|
| SA moves (Python + NumPy, 1 thread) | 9.0–11.7k moves/s, N=30–1000 |
| Per-move collision check | 12–30 µs ([geometry](geometry-libraries.md)) |
| PathFinder, Python heapq A* (76.8k nodes, 2 layers) | 2.2 s / 50 nets; 13.0 s / 150; 32.7 s / 300; 60.9 s / 300 on 4 layers (153.6k nodes); 15 iterations each |
| Same, SciPy C Dijkstra (full tree, CSR rebuilt per net) | 4.7 s / 50 nets — 2× *slower* than Python A*: search strategy beats language |
| CP-SAT model build | 0.01 s (N=30) → 0.2 s (N=1000) |
| LNS iteration via full-model clone at N=1000 | ~8.6 s for a 3 s solve (clone + presolve dominate) |
| Per-violation-cluster window sub-models at N=1000 | 41 windows legalized in 3.9 s total |
| Hierarchical cluster solves | 112 s for 87 clusters × 2 variants, embarrassingly parallel |

**Multi-fidelity ladder** ([solver_toolbox.md § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md))
| Level | Check | Cost |
|---|---|---|
| L0 | HPWL + hard-constraint check | µs |
| L1 | RUDY + net-crossing proxy (Cypress) | ms |
| L2 | Coarse PathFinder (capped iterations) | seconds |
| L3 | Freerouting headless / KRT / in-house router | seconds–minutes (Freerouting: "a few minutes to several hours" on big boards) |
| L4 | `kicad-cli pcb drc` + PCBWorld-style clean-pass (routability = 1 AND 0 DRC errors; 62 `DRCE_*` codes) | final |

**Evidence**
- Cypress: Freerouting v1.9.0, 2 layers, % routed pin pairs; MOTPE over WL/density/crossing then routes; net-crossing term cut crossings to 0.31× at 1.13× HPWL [P].
- NS-Place: FreeRouting routed WL/vias + KiCad DRVs [P]. PCBWorld: Freerouting 2.7–9.9 s per board on D2/D3 [P].
- DREAMPlace RUDY/RISA area adjustment (`adjust_rudy_area_flag`); SMAC multi-fidelity; Freerouting fidelity knobs `-mp`, `-mt 0`, `--router.optimizer.improvement_threshold` [P].
- Apollo: wirelength/density placers can score ~51% routability on its domain [S].
- Freerouting versions differ across papers, so results are not comparable ([freerouting](../routing/freerouting.md)).

## Recommendations for our system
- Rust core: incremental HPWL (per-net min/max with counts), grid-hash overlap, RUDY bins, SA moves, A*/PathFinder, optional jagua-rs exact collision; Python: CP-SAT, Optuna, IPC I/O, LLM tools [I].
- **Make Freerouting-on-2-layers (L3) the calibration target** for L1/L2 proxies on a held-out set (PCBWorld D3 + Cypress small suite); check rank correlation before using proxies in Optuna [I].
- Expose `evaluate(candidate, level)` to the LLM so L3/L4 are spent only on Pareto finalists [I].
- Parallelize cluster solves and Optuna trials; skip GPU unless boards reach thousands of parts [I].
- Never clone the full CP-SAT model per LNS/legalization step at ≥1000 parts: build small window sub-models (free parts as variables, neighbours fixed, external pins constant) [M].

## Conflicts and open questions
- No direct Rust-vs-Python measurement for placement kernels beyond KRT's routing claim (our numbers are Python-only ceilings); proxy-to-routed correlation unmeasured for PCBs.

## Sources
- research notes: [solver_toolbox.md § 7, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)
- Tags: [M] = measured in the notes' micro-benchmarks.

See also: [benchmarks](benchmarks.md) · [geometry-libraries](geometry-libraries.md) · [bayesian-tuning](bayesian-tuning.md) · [placement/benchmarks-and-metrics](../placement/benchmarks-and-metrics.md)
