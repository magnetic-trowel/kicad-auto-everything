# Physics in the loop: objectives, adjoints, search at scale and legalization

Scope: physics terms as spend models with gradients inside the joint optimizer (models, cost, validity), adjoint sensitivities, placement with physics fields, routing as current flow, search methods, legalization to DRC. Not here: the joint loop itself -> [joint-place-route](joint-place-route.md); pour synthesis POC numbers -> [copper-shape-synthesis](copper-shape-synthesis.md); rungs -> [solver-ladder](solver-ladder.md).
Keys: physics terms, spend model, hot-loop kernel, filament PEEC, L vs perimeter, h_eff, thermal Green's function K0, λ spreading length, adjoint, shape derivative, topological derivative, ePlace, noise potential, Gilbert network, width ∝ current, physics-priced edges, price field, BonnRoute resource sharing, elastic bands, octilinear, corner reflection, continuation, MAP-Elites, legalization, op_placement_kernels.py, P8, N7, OP31, OP43

**Results** [C]:
- Physics enters the optimizer as spend models with gradients on the joint state (poses, route topologies, copper fields), not after-the-fact checks: closed-form kernels (µs to sub-ms, batchable, differentiable) or one sparse 2-D solve + adjoint back-substitution (~10 ms at 0.4 mm, 0.2 s at 0.1 mm per layer).
- Proxies fail in known regimes: with a solid plane 0.1 mm below, equal-area hot loops differ 1.7× in L and track perimeter; without a plane area ranks roughly. Thermal spreading length is mm on bare FR-4, tens of mm with copper planes. Unmitred corners reflect ~−50 to −56 dB at 1 GHz.
- Adjoints answer "where should copper go?": one extra solve gives sensitivity to every cell, pad or via, and adjoint-guided growth beat uniform widening ([copper-shape-synthesis](copper-shape-synthesis.md#proof-of-concept)). They are the shadow prices design reasoning reports.
- Routing splits by physics: power nets are shapes (width ∝ current on a Steiner topology minimizing Σ I·l); signals are paths with physics-priced edges; one copper price field per layer arbitrates; PathFinder history costs, area multipliers and resource-sharing duals are one kind of variable [C/I].
- Spend compute on binding budgets; fab and DRC rules are constraints or projections, never penalties; every candidate ends with a physics re-solve and `kicad-cli` DRC.

## Where physics sits in the joint state

| State element ([joint-place-route](joint-place-route.md#4-the-joint-state)) | Physics terms that read it | Evaluator |
|---|---|---|
| Part poses (x, y, θ, side) | hot-loop L, decap mounting L, ΔT superposition, aggressor–victim coupling, connector CM voltage (P8) | closed-form kernels; batched |
| Route topologies (homotopy, layer, via sites) | path length × L′(w, h_eff), reference crossings, parallel-run coupling, via-transition loop L | kernels on sketches |
| Copper density and price fields per layer | IR drop, HF pour L, heat spreading, plane partitions | 2-D sheet solve + adjoint ([copper-shape-synthesis](copper-shape-synthesis.md)) |
| Stackup and reference map h_eff(x, y) | every L′, f_c, return-path term | precomputed per layer pair |
| Budgets ([physics-ir](physics-ir.md)) | penalties or constraints; multipliers → shadow prices | ledger |

## Physics terms: model, cost, gradient, regime

Write the loop, K0 thermal and crosstalk kernels as pure JAX or PyTorch functions the Cypress-style placer can differentiate; validate each against F2/F3 references (PEECN, FasterCap, FV thermal) first ([solver-ladder](solver-ladder.md), [physics-critics](physics-critics.md)) [I].

| Term | Model | Cost per evaluation | Gradient | Valid when | Replaces |
|---|---|---|---|---|---|
| Hot-loop / commutation L | filament PEEC, Grover parallel-filament mutuals, plane as image ([op_placement_kernels.py](../../../tools/research/physics/op_placement_kernels.py)) | 0.35 ms per 4-segment loop (numpy, 1 core); ~µs batched on GPU [I] | autodiff or finite differences | edges well above f_c; plane continuous under the loop | "minimize loop area" |
| Path inductance near a plane | Σ L′(w, h_eff)·l | µs | analytic | h_eff ≲ w | length or area |
| Pour IR drop / loss | sheet Laplace, 1/R_s | 9 ms (0.4 mm) – 0.18 s (0.1 mm) per 24×14 mm layer | adjoint (same LU) | f < f_c | width-per-amp tables |
| Pour HF inductance | sheet Laplace, 1/(μ0·h_eff) | same | adjoint | f ≫ f_c, w ≳ h | "keep under plane" |
| ΔT between parts | K0(r/λ)/(2π·k·t), λ = √(k·t/2h_c), edge images | µs per pair; FFT on a grid | analytic | steady state, convection-cooled | "keep hot parts apart" |
| Crosstalk | K = 1/(1 + (D/H)²) per parallel length; filament M for loops | µs | analytic | edge-coupled lines over a plane | 3W |
| Connector CM voltage | P8 plane-voltage proxy ([placement ideas](../../ideas/original/placement.md#p8-differentiable-connector-voltage-emi-proxy--new)) | µs | analytic | ranking only | "keep fast nets away from connectors" |

Kernel checks [C]: 10×4 mm loop of 0.25 mm-radius wire 13.47 nH vs 13.28 nH (Grover's rectangle); strip L′ over a plane 0.317 vs 0.319 nH/mm (w 0.3, h 0.17 mm) and 0.062 vs 0.069 nH/mm (w 1.5, h 0.1 mm) vs air-microstrip Z0/c.

**Lateral hot loop vs plane depth** (1.5 mm strips, 1 oz, solid plane below) [C]:

| Loop | No plane | h = 1.5 mm | 0.4 | 0.2 | 0.1 mm |
|---|---|---|---|---|---|
| 8×3 mm (24 mm², perimeter 22) | 8.02 nH | 7.00 | 3.95 | 2.35 | 1.20 |
| 4.9×4.9 mm (24 mm², 19.6) | 7.61 | 6.48 | 3.53 | 2.09 | 1.07 |
| 12×2 mm (24 mm², 28) | 8.72 | 7.92 | 4.83 | 2.94 | 1.52 |
| 16×1.5 mm (24 mm², 35) | 8.97 | 8.32 | 5.44 | 3.43 | 1.82 |
| 6×2 mm (12 mm², 16) | 4.67 | 4.30 | 2.67 | 1.64 | 0.85 |

- h = 0.1 mm: L/perimeter 0.052–0.055 nH/mm for all five shapes; no plane: L/area 0.32–0.39 nH/mm².
- Moving the input-cap side of the 8×3 loop: 0.86 nH/mm without a plane, 0.22 nH/mm with one at 0.2 mm.
- The loop term changes form with h_eff/b (b = forward-to-return spacing); a plane 0.1–0.2 mm under the loop beats squeezing it. Use the kernel, not a proxy; if a proxy is unavoidable choose it by h_eff vs b: L ∝ perimeter within ±8% at h ≤ b/4, ±3% at h ≤ b/15, constant ≈ 0.85·L′(w, h) (corner overlap); area is wrong whenever a plane is that close [C]. Power-specific extraction: [pdn-and-commutation](pdn-and-commutation.md).

**Thermal Green's function, still air** (h_c = 10 W/m²K per side) [C]:

| Stackup | k·t | λ | θ_mutual at 5 / 10 / 20 / 40 mm |
|---|---|---|---|
| 2L 1.6 mm, no pours | 0.48 mW/K | 4.9 mm | 136 / 36 / 3.4 / 0.0 K/W |
| 2L 1.6 mm, two 1 oz pours | 27.8 mW/K | 37 mm | 12.3 / 8.5 / 5.0 / 2.2 K/W |
| 4L, 1 oz outer + 2×0.5 oz planes | 41.4 mW/K | 46 mm | 9.0 / 6.4 / 4.0 / 1.9 K/W |
| 4L, 2 oz outer + 2×1 oz planes | 82.4 mW/K | 64 mm | 5.2 / 3.9 / 2.6 / 1.4 K/W |

These λ use the sheet k·t listed; the fin model in [thermal-physics](thermal-physics.md#the-board-as-a-fin) (FR-4 k_xy 0.8) gives 8 and 38 mm for the first two rows and is canonical. On copper-heavy boards coupling barely decays: spreading sources lowers the mean rise little (still moves a neighbour's peak 10–20%); copper area and convection path matter more ([thermal-physics](thermal-physics.md)) [C].

## Adjoint sensitivities

- **Mechanics:** K(p)·u = f, J = lᵀu: solve Kᵀλ = l once; dJ/dp = −λᵀ(∂K/∂p)u for every p. Loss or compliance (J = fᵀu): λ = u, no extra solve. Non-self-adjoint J (drop at one load, T at one part, coupling into one victim): extra solve reuses the LU; back-substitution 2–6% of the factorization [C].
- **Shape derivative:** moving a copper edge outward by δn changes loss by ≈ −σ|∇V|²·δn per unit length (square of tangential current density at the edge): teardrops, inside-corner fillets, flared pad entries; copper pays where current crowds [I].
- **Topological derivative:** forward and adjoint fields × the edit's polarization tensor rank small holes and added conductors; for slits the tensor is the crack law; the plain area-weighted adjoint underestimates a 6 mm slot 30×. Finite edits need exact Woodbury updates ([solver-ladder](solver-ladder.md#6-caching-and-incremental-re-extraction), [lens-cd](lens-cd.md)).
- **EM:** frequency-domain adjoints cost one extra solve per objective (Nikolova, Bandler, Bakr, IEEE MTT 2004) [S]; FDTD gradients by time reversal: FDTDX (JAX, MIT), ceviche (MIT) [P: licence files]; Meep GPL-2.0-or-later, usable [S].
- **POC** ([op_topopt_pour.py](../../../tools/research/physics/op_topopt_pour.py), human layout 2.092 mΩ): adjoint-ranked +26 mm² (boundary cells, 10 batches) 1.531 mΩ; uniform widening 1.666; full re-optimization at that area 1.370; removing the 20% least-loaded copper (−14 mm²) 2.525 mΩ (+21%) [C].
- **Answers for any layout:** copper that buys most mΩ (or K, nH) per mm²; necks (largest ∂R/∂width); dead copper; the pad or via whose move changes a budget most. Expose `sensitivity(objective)` as a tool for agents and humans, with one sheet solver + adjoint per layer for IR, HF pour L and heat [C/I].

## Placement with physics fields

- **Template ePlace:** electrostatic potential from cell density, FFT/DCT-solved each Nesterov step; Cypress adds net crossing and orientation ([analytical-differentiable](../solvers/analytical-differentiable.md)).
- **Extra fields:** a noise potential (aggressor near fields such as dv/dt node area and hot-loop dipole moments, convolved with a coupling kernel; victims descend it); a thermal potential (K0 superposition or FFT fin solve); loop terms from the filament kernel attached to loop members. Each ≈ one FFT per step or O(members²) kernels. Add by continuation: wirelength, density and DC/thermal first, HF loop and coupling as parts settle ([OP43](../../ideas/physics-first/optimization.md)) [I].
- **Throughput:** ~0.35 ms per loop in numpy → ~10⁷ loop evaluations per core-hour; GPU batch 10⁵–10⁶ poses/s [C/I], enough to reject bad placements before any router runs.

## Routing as current flow

**Power nets are shapes.**
- Strip tree with fixed area A: loss Σ I²·R_s·l/w is minimized by w ∝ I (constant current density), P_min = R_s·(Σ I·l)²/A [C]. Minimize the current-weighted Steiner tree Σ I·l (Gilbert network); widths follow current; shape synthesis only where amps or margins justify it.
- POC baseline already on this law: every branch ~0.67 mm/A, within 0.2% of its topology's 1-D optimum; topology optimization's extra 14.5% (0.1 mm raster) comes from topology and 2-D spreading at pads and junctions [C].
- IPC-2221 widths answer a thermal question (w ∝ I^1.38 at fixed ΔT), not a loss question; use the larger width.

**Signals are paths with physics-priced edges** (PathFinder with physics-priced edges; FanoutNet already weights reference-layer shielding; here each weight is a physical spend from the ledger):

| Cost term | Physics | Data |
|---|---|---|
| Reference continuity | return detours around slots, raising loop L and CM voltage | h_eff map, split and void polygons |
| Impedance deviation | reflection from width or reference change | per-layer w(Z0) |
| Coupling potential | crosstalk and EMI to declared victims | aggressor field from placement |
| Via transition | loop L of the return via, stub resonance | filament kernel, via model |
| Congestion history | shared copper resource | PathFinder (VPR defaults, [PathFinder](../routing/pathfinder-negotiated-congestion.md)) |

**One price field.** Negotiated congestion, multicommodity-flow relaxations and min-max resource sharing are one Lagrangian idea; BonnRoute's resource sharing solves chip global routing near-optimally (Müller, Radke, Vygen, *Math. Prog. Comp.* 2011) [S]. Topology optimization's area multiplier is also a price; pours and signals negotiate per-cell, per-layer copper prices inside the joint loop (POC: 4× corridor price halved corridor copper for +24% loss) [C].

**Angles and curves.**
- Fixed topology: octilinear ~5% longer than any-angle; rectilinear 23–31% longer ([topological-routing](../routing/topological-routing.md)) [P].
- Unmitred 90° corner with 10–20 fF excess C: |Γ| ≈ 0.002–0.003 at 1 GHz, 0.016–0.031 at 10 GHz, 0.05–0.09 at 30 GHz [C].
- Arcs matter for mm-wave lines, flex bends and minimum gaps in dense escapes (TopoR claims ~30% larger gaps than 45° [V]). Euler (clothoid) bends help curvature-sensitive photonic waveguides; PCB quasi-TEM lines are not curvature-sensitive below tens of GHz [S/I].
- Elastic bands (Quinlan–Khatib) relax a fixed-homotopy path under tension plus potentials (coupling, reference fields), tidying critical routes without changing topology [S/I].

**Pairs and length matching:** a diff pair is one ribbon with fixed internal geometry; a length-match group is an equality constraint whose multiplier prices meander area ([diff-pair-routing](../routing/diff-pair-routing.md), [length-matching](../routing/length-matching-and-buses.md)) [I].

## Search at scale

| Method | Use it for | Physics angle |
|---|---|---|
| Gradient + continuation | global placement, shape synthesis | smooth physics first, field terms later |
| Multi-fidelity ladder (kernel → sheet → PEEC/FastHenry → openEMS) | verifying finalists | escalate only when the margin is inside the cheaper model's error (V4 trust radius) |
| Bayesian optimization (MOTPE, multi-fidelity) | 5–20 knobs: weights, stackup, grid | objective = budget margins, not HPWL ([bayesian-tuning](../solvers/bayesian-tuning.md)) |
| MAP-Elites / CMA-MAE | portfolios | descriptors in physical units: nH, K, mV, dB ([QD](../solvers/metaheuristics-and-qd.md)) |
| Evolution / LLM-evolved heuristics | cost schedules, move sets | fitness from full-solver budgets on held-out boards |
| RL with a red team | adversarial excitations, reward hacking | adversary maximizes victim noise or IR drop over switching phases and load steps (V2 extended) |
| Surrogates (CNN, neural operator) | screening, warm starts | trained on synthetic boards labelled by the exact solver; accepted designs re-solved |

Compute arithmetic [C/I]: sheet solves at 0.1 mm ~0.2 s per layer (~7 × 10⁴ per hour on 4 cores). Greedy ESO-style pour screening ~14 solves per shape vs ~200 for SIMP, reaching 1.88 vs 1.79 mΩ: screen greedy, finish with SIMP. "Near-infinite compute" buys breadth (seeds, portfolios, adversaries), not finer grids: R converged to 0.5% at 0.1 mm.

## Legalization: from continuous to DRC-legal

| Continuous result | Operation | Tool | Hard rule enforced |
|---|---|---|---|
| Density field | filter radius / robust projection during optimization | own (numpy, JAX) | min width/space, etch tolerance |
| Thresholded field | marching-squares contour at ρ = 0.5 | contourpy (BSD-3) | — |
| Polygon | close by gap_min, open by w_min (round joins), clip keep-outs, keep source-connected parts, simplify | Shapely / pyclipper | sliver, acid trap, clearance, islands |
| Smooth outline | biarc fit with minimum radius | own | curvature (optional) |
| Discrete leftovers | via sites and counts, relief style, layer choice | CP-SAT | integrality, via-to-via spacing |
| Placement | physics-weighted min-displacement legalization | CP-SAT ([legalization](../placement/legalization.md)) | courtyard, keep-out |
| Everything | physics re-solve, then `kicad-cli pcb drc` on the re-opened board | own + KiCad | budgets within margin; DRC = 0 |

POC legalization results (0.0% R at 0.5 mm minimum; +2.8% thin design; 1.0 mm opening disconnected a load, so min width must set the filter radius and the legalizer must re-check source-to-load connectivity): [copper-shape-synthesis](copper-shape-synthesis.md#proof-of-concept) [C]. Photonics runs the same pipeline: foundry rules inside topology optimization (Hammond et al. 2021), minimum-distortion legalization (OptiClear, 2026) [S/P].

## Open questions

- **Loop-area proxy vs perimeter:** N7 ([priority-agents](../../ideas/original/priority-agents-and-negotiation.md#n7-hot-loop-micro-placer-minimizing-estimated-nanohenries--new)) estimates L from loop-polygon area; near a plane perimeter × depth dominates (MS2). Reconcile N7 with the PEEC in [power-copper](power-copper.md) [C].
- **Kernel assumes uniform current across width and an infinite ideal plane.** PEECN solves the HF current split and is the reference (graded filaments for w/h > 10; [verification-and-limits](verification-and-limits.md#1-claims-verified-by-an-independent-method)); ours serves batched gradients. Below ~1 MHz the return spreads and image PEEC underestimates L. Slotted planes untested [C].
- **Shadow prices are local:** multipliers of a non-convex problem hold only near the current design; explanations need a "valid within" margin [I].
- **No PCB benchmark for physics-aware routing costs.** First test: reference crossings and crosstalk at equal completion vs plain PathFinder ([OP31](../../ideas/physics-first/optimization.md)) [I].
- Timings are CPU time on a loaded 4-core VM; GPU numbers are estimates [C/I].

## Sources

- Scripts: [op_placement_kernels.py](../../../tools/research/physics/op_placement_kernels.py), [op_topopt_pour.py](../../../tools/research/physics/op_topopt_pour.py).
- Research notes: [solver_toolbox.md § 2, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [routing_classics_supplement.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md).
- Müller, Radke, Vygen, *Math. Prog. Comp.* 2011: https://link.springer.com/doi/10.1007/s12532-011-0023-y [S]
- Hammond et al., *Opt. Express* 2021: https://dspace.mit.edu/handle/1721.1/131097 [S]; OptiClear: https://arxiv.org/abs/2607.03632 [P]
- FDTDX (MIT): https://github.com/ymahlau/fdtdx [P: LICENSE]; ceviche (MIT): https://github.com/fancompute/ceviche [P: LICENSE]
- Euler bends: https://kb.flexcompute.com/tidy3d/examples/WaveguideBend.html [S]
- TopoR isotropic routing (vendor): https://pcdandf.com/pcdesign/index.php/2009-archive-articles/5203-advantages-of-isotropic-pcb-routing [V]
- Grover, *Inductance Calculations* [S]; Nikolova, Bandler, Bakr, IEEE MTT 52(1), 2004 [S]; Quinlan & Khatib, ICRA 1993 [S]
- Related: [ideas: optimization](../../ideas/physics-first/optimization.md).
