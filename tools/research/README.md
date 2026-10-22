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

## `physics/`: physics-first layout checks and prototypes

Results and interpretation: [docs/topics/physics/](../../docs/topics/physics/README.md); each topic doc tags the numbers these scripts produce as [C]. Prefix = workstream: `rg_` rule genealogy, `vo_` vocabulary/IR, `sl_` solver ladder, `pw_` power, `fe_` SI/EMI/RF, `op_` optimization, `tm_` thermal/HV/manufacturing, `dr_` design reasoning, `pc_` physics critics, `xd_` cross-domain, `jpr_` joint placement and routing. They need NumPy and SciPy (some also Shapely, pyamg or scikit-rf); quasi-static models, uncalibrated against measurement. Three PEEC solvers (`sl_loop_peec`, `pw_peec`, `fe_peec_plane`) and four sheet/thermal Laplace solvers (`pw_sheet`, `op_topopt_pour`, `xd_sheet`, `tm_board_thermal_fv`) overlap and should be merged (idea SIM46).

| Script | What it does |
|---|---|
| `rg_proxies.py`, `rg_corners.py`, `rg_fill_and_decaps.py` | Closed forms and 2-D solves that decompress rules (3W, corners, ground fill, decap distance) |
| `vo_return_spread.py`, `vo_numbers.py` | Return-current spread vs frequency; the vocabulary's closed-form numbers |
| `vo_ir_check.py` | Validator prototype for the `physics:` block of `pcb-intent/0.3` |
| `sl_loop_peec.py` | Hot-loop inductance: µs proxies (area, MS2) vs image-plane PEEC |
| `sl_tier_costs.py` | Cost and accuracy per fidelity tier |
| `pw_sheet.py`, `pw_xsec.py`, `pw_peec.py`, `pw_eddy.py`, `pw_cells.py` | 2-D current flow in copper masks; skin and proximity; filament PEEC; eddy currents under inductors; switching-cell width optimum |
| `fe_peec_plane.py`, `fe_field2d.py`, `fe_cavity.py`, `fe_emi_budget.py`, `fe_geometry.py` | Return current in a meshed plane with slots; 2-D cross-section fields; plane-pair cavity with stitching; EMI budget chain; geometry thresholds |
| `op_topopt_pour.py`, `op_placement_kernels.py` | Topology optimization of a power pour with adjoints and fab filters; differentiable placement kernels |
| `tm_board_thermal_fv.py`, `tm_thermal_analytic.py`, `tm_hv_field.py`, `tm_paschen_altitude.py`, `tm_mfg_physics.py`, `tm_solder_reflow.py`, `tm_impedance_tolerance.py` | Board thermal FV solver; thermal closed forms; HV corner fields; Paschen and altitude; DFM process physics; tombstoning; impedance tolerance |
| `dr_switch_cell_budget.py`, `dr_coupling_oracles.py`, `dr_noise_adjoint.py` | Sensitivity-derived hot-loop budgets; coupling oracles; adjoint susceptibility (optional ngspice cross-check via `NGSPICE`) |
| `pc_refplane.py`, `pc_budget_calcs.py` | Physics-critic prototype (return path and plane integrity from a `.kicad_pcb`, with an in-memory mutation self-test); critic numbers |
| `xd_sheet.py`, `xd_power_tree.py`, `xd_lengths.py`, `xd_loop_coupling.py` | Via-field transfer length and slot cost; branching power trees; screening lengths; loop coupling with plane images |
| `jpr_joint_vs_sequential.py` | Joint vs sequential placement and routing on synthetic boards (uses `solver-bench/pcbgen.py`) |

### First-principles lenses, foundations, verification and validation

Results: the `lens-*.md`, [foundations](../../docs/topics/physics/foundations.md), [derivation-audit](../../docs/topics/physics/derivation-audit.md), [verification-and-limits](../../docs/topics/physics/verification-and-limits.md), [physics-core-v2](../../docs/topics/physics/physics-core-v2.md), [validation-program](../../docs/topics/physics/validation-program.md) and [real-board-passports](../../docs/topics/physics/real-board-passports.md) docs. Run with `OMP_NUM_THREADS=1` on shared machines. The `rt_*` scripts re-derive key results by independent methods and serve as regression references. Third-party boards are read from a path you pass in and are never stored in the repo.

| Prefix | Scripts | What they compute |
|---|---|---|
| `vp_` | `vp_floors`, `vp_rl_band`, `vp_edit_pricing` | Certified floors and two-sided brackets; the R–L band as an eddy-mode spectrum; edit pricing by polarization tensor |
| `ct_` | `ct_cut_topology` | Exact cut law, neck leakage, board–world charge ledger, loop nesting |
| `sy_` | `sy_duality_balance`, `sy_images_symmetry` | Node vs loop coupling vs h, guards, image-exact slit and notch prices, mode conversion, scaling |
| `ls_` | `ls_thin_sheet`, `ls_post_lattice`, `ls_regime_map` | Complex images for planes, the wire medium (decaps + stitching), regime map of a reference board |
| `th_` | `th_damping_ledger`, `th_dissipation_noise`, `th_electrothermal` | Modal Q, tuned snubbers, cavity damping; dissipation and noise; electro-thermal stability and thermoelectric checks |
| `in_` | `in_decision_quality`, `in_emi_voi` | Proxy decision quality; value of information for an EMI decision |
| `cd_` | `cd_conductor_passport` | Conductor passports per piece and band, exact removal costs, job verbs (synthetic board) |
| `fd_` | `fd_gentleness`, `fd_impedance_level` | Radius of convergence of circuit + parasitics; the impedance-level theorem |
| `da_` | `da_derivations`, `da_inductor_cutout`, `da_coverage` | Checks behind the derivation audit; copper under inductors; coverage statistics |
| `rt_` | `rt_cut_law`, `rt_sheet_return`, `rt_damping`, `rt_impedance_match`, `rt_world_cm`, `rt_loop_proxy`, `rt_voi_sensitivity`, `rt_jpr_stats`, `rt_fill_z0` | Independent re-derivations of load-bearing claims |
| `pc2_` | `pc2_core_skeleton` | Physics core v2 skeleton: one factorization, exact edit quotes, brackets behind the proposed API |
| `val_` | `val_voi_rank`, `val_board`, `val_floor_census`, `val_*_coupon` | VOI ranking of claims; VAL-1 predictions; pilot floor census on real boards; registered coupon predictions |
| `rb_` | `rb_board_passports` | Conductor passports on a real `.kicad_pcb` passed on the command line |
| `suite_` | `suite_passports`, `suite_physics` | Roles, DC passports, ground topology and hot loops for any board; batch runner over a kaebench suite or router outputs, with aggregation and router-vs-human pairing ([suite-physics-results](../../docs/topics/physics/suite-physics-results.md)) |
