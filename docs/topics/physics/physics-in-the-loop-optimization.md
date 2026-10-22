# Physics in the loop: objectives, adjoints, search at scale and legalization

**TL;DR**
- **Physics enters the optimizer as spend models with gradients, evaluated on the joint placement-and-routing state** (poses, route topologies, copper fields), not as after-the-fact checks. The key terms are closed-form kernels (µs to sub-ms, batchable, differentiable) or one sparse 2-D solve plus an adjoint back-substitution (about 10 ms at 0.4 mm and 0.2 s at 0.1 mm per layer) [C]. The joint loop is owned by [joint-place-route](joint-place-route.md).
- **Common proxies fail in known regimes, and the kernels show where.**
  - Loop area: with a solid plane 0.1 mm below, equal-area hot loops differ 1.7× in inductance, which tracks perimeter to within 3%. Without a plane, area ranks loops roughly (equal-area loops still differ by 18%) [C].
  - Thermal spacing: the spreading length is about 5 mm on bare FR-4 and 37–64 mm with copper planes [C].
  - Corners: an unmitred corner reflects about −50 to −56 dB at 1 GHz [C].
- **Adjoints answer "where should copper go or move?"** One extra solve gives the sensitivity of loss, IR drop, loop L or ΔT to every cell, pad or via. In the POC, adjoint-guided copper growth beat uniform widening (1.53 vs 1.67 mΩ for +25% area), and the gradients match finite differences to 3.5 × 10⁻⁷ [C]. The same sensitivities are the budget shadow prices the design-reasoning layer reports.
- **Routing splits by physics.** Power nets are shapes: at fixed area, loss is minimal with width ∝ current on a Steiner topology minimizing Σ I·l. Signals stay paths whose edge costs are physics fields (reference continuity, impedance, coupling potential). One copper price field per layer arbitrates; PathFinder history costs, area multipliers and resource-sharing duals are the same kind of variable [C/I].
- **Use compute on binding budgets, and keep fab rules hard.** Use continuation in physics, a multi-fidelity ladder gated by trust radius, quality-diversity over physics descriptors and adversarial excitations. Legalize by projection, Minkowski morphology and CP-SAT, re-check physics, and end with `kicad-cli` DRC. Never trade a DRC rule against a physics score.

## Key facts

### Where physics sits in the joint state

| State element (see [joint-place-route](joint-place-route.md)) | Physics terms that read it | Evaluator |
|---|---|---|
| Part poses (x, y, θ, side) | hot-loop L, decap mounting L, ΔT superposition, aggressor–victim coupling, connector common-mode voltage (P8) | closed-form kernels; batched |
| Route topologies (homotopy, layer, via sites) | path length × L′(w, h_eff), reference crossings, parallel-run coupling, via-transition loop L | kernels on sketches |
| Copper density and price fields per layer | IR drop, HF pour L, heat spreading, plane partitions | 2-D sheet solve + adjoint ([copper-shape-synthesis](copper-shape-synthesis.md)) |
| Stackup and reference map h_eff(x, y) | every L′, f_c, return-path term | precomputed per layer pair |
| Budgets, from [physics-ir](physics-ir.md) | penalties or constraints; multipliers become shadow prices | ledger |

### Physics terms: model, cost, gradient, regime

| Term | Model | Cost per evaluation | Gradient | Valid when | Replaces |
|---|---|---|---|---|---|
| Hot-loop / commutation L | filament PEEC, Grover parallel-filament mutuals, plane as image ([op_placement_kernels.py](../../../tools/research/physics/op_placement_kernels.py)) | 0.35 ms per 4-segment loop (numpy, 1 core); ~µs batched on GPU [I] | autodiff or finite differences | edges well above f_c; plane continuous under the loop | "minimize loop area" |
| Path inductance near a plane | Σ L′(w, h_eff)·l | µs | analytic | h_eff ≲ w | length or area |
| Pour IR drop / loss | sheet Laplace, 1/R_s | 9 ms (0.4 mm) – 0.18 s (0.1 mm) per 24×14 mm layer | adjoint (same LU) | f < f_c | width-per-amp tables |
| Pour HF inductance | sheet Laplace, 1/(μ0·h_eff) | same | adjoint | f ≫ f_c, w ≳ h | "keep under plane" |
| ΔT between parts | K0(r/λ)/(2π·k·t), λ = √(k·t/2h_c), edge images | µs per pair; FFT on a grid | analytic | steady state, convection-cooled | "keep hot parts apart" |
| Crosstalk | K = 1/(1 + (D/H)²) per parallel length; filament M for loops | µs | analytic | edge-coupled lines over a plane | 3W |
| Connector common-mode voltage | P8 plane-voltage proxy ([placement ideas](../../ideas/original/placement.md#p8-differentiable-connector-voltage-emi-proxy--new)) | µs | analytic | ranking only | "keep fast nets away from connectors" |

Kernel checks [C]:
- 10×4 mm loop of 0.25 mm-radius wire: 13.47 nH, against 13.28 nH from Grover's rectangle formula.
- Strip L′ over a plane: 0.317 vs 0.319 nH/mm (w 0.3, h 0.17 mm) and 0.062 vs 0.069 nH/mm (w 1.5, h 0.1 mm), against the air-microstrip Z0/c.

Lateral hot loop, 1.5 mm strips, 1 oz, inductance vs depth of a solid plane below [C]:

| Loop | No plane | h = 1.5 mm | 0.4 | 0.2 | 0.1 mm |
|---|---|---|---|---|---|
| 8×3 mm (24 mm², perimeter 22) | 8.02 nH | 7.00 | 3.95 | 2.35 | 1.20 |
| 4.9×4.9 mm (24 mm², 19.6) | 7.61 | 6.48 | 3.53 | 2.09 | 1.07 |
| 12×2 mm (24 mm², 28) | 8.72 | 7.92 | 4.83 | 2.94 | 1.52 |
| 16×1.5 mm (24 mm², 35) | 8.97 | 8.32 | 5.44 | 3.43 | 1.82 |
| 6×2 mm (12 mm², 16) | 4.67 | 4.30 | 2.67 | 1.64 | 0.85 |

- At h = 0.1 mm, L/perimeter is 0.052–0.055 nH/mm for all five shapes. With no plane, L/area spans 0.32–0.39 nH/mm².
- Moving the input-capacitor side of the 8×3 loop changes L by 0.86 nH/mm with no plane and by 0.22 nH/mm with a plane at 0.2 mm.
- Consequence: the loop term changes form with h_eff/b (b = forward-to-return spacing), and a plane 0.1–0.2 mm under the loop is worth more than squeezing the loop [C]. Power-specific extraction: [pdn-and-commutation](pdn-and-commutation.md).

Thermal Green's function in still air (h_c = 10 W/m²K per side) [C]:

| Stackup | k·t | λ | θ_mutual at 5 / 10 / 20 / 40 mm |
|---|---|---|---|
| 2L 1.6 mm, no pours | 0.48 mW/K | 4.9 mm | 136 / 36 / 3.4 / 0.0 K/W |
| 2L 1.6 mm, two 1 oz pours | 27.8 mW/K | 37 mm | 12.3 / 8.5 / 5.0 / 2.2 K/W |
| 4L, 1 oz outer + 2×0.5 oz planes | 41.4 mW/K | 46 mm | 9.0 / 6.4 / 4.0 / 1.9 K/W |
| 4L, 2 oz outer + 2×1 oz planes | 82.4 mW/K | 64 mm | 5.2 / 3.9 / 2.6 / 1.4 K/W |

- On copper-heavy boards, thermal coupling barely decays across the board, so "spread the heat sources" buys little; copper area and the convection path matter more [C]. Thermal detail: [thermal-physics](thermal-physics.md).

### Adjoint sensitivities

- **Mechanics.** For K(p)·u = f and J = lᵀu, solve Kᵀλ = l once; then dJ/dp = −λᵀ(∂K/∂p)u for every parameter p at once. For loss or compliance (J = fᵀu), λ = u: no extra solve. For a non-self-adjoint J (drop at one load, temperature at one part, coupling into one victim), the extra solve reuses the LU factors; the back-substitution costs 2–5% of the factorization [C].
- **Shape derivative.** Moving a copper edge outward by δn changes loss by about −σ|∇V|²·δn per unit length, i.e. by the square of the tangential current density at the edge. That is the physics behind teardrops, inside-corner fillets and flared pad entries: copper pays where current crowds [I].
- **Topological derivative.** The same quantities rank where to punch a small hole (antipad, slot) or add a small conductor (stitching via).
- **EM.** Frequency-domain adjoints cost one extra solve per objective (Nikolova, Bandler, Bakr, IEEE MTT 2004) [S]. FDTD gets gradients by time reversal: FDTDX (JAX, MIT) and ceviche (MIT) [P: licence files]; Meep is GPL-2.0-or-later, so usable [S].
- **POC on the human layout** ([op_topopt_pour.py](../../../tools/research/physics/op_topopt_pour.py)) [C]:

| Action, +26 mm² copper (or −14 mm²) | R_loss |
|---|---|
| Baseline trunk and branches | 2.092 mΩ |
| Add copper by adjoint ranking (boundary cells, 10 batches) | 1.531 mΩ |
| Uniform widening, same area | 1.666 mΩ |
| Full re-optimization at the new total area | 1.370 mΩ |
| Remove the 20% least-loaded copper | 2.525 mΩ (+21%) |

- **What this answers for any layout:** the copper that buys the most mΩ (or K, or nH) per mm²; necks (largest ∂R/∂width); dead copper; the pad or via whose move changes a budget most. These are the shadow prices [design-reasoning-architecture](design-reasoning-architecture.md) asks the optimizer to return.

### Placement with physics fields

- **ePlace gives the template:** an electrostatic potential from cell density, solved by FFT/DCT every Nesterov step. Cypress adds net crossing and orientation ([analytical-differentiable](../solvers/analytical-differentiable.md)).
- **Add physical fields alongside density:**
  - a **noise potential**: aggressor near-fields such as dv/dt node area and hot-loop dipole moments, convolved with a coupling kernel; victims descend it;
  - a **thermal potential**: the K0 superposition, or an FFT fin solve;
  - **loop terms** from the filament kernel, attached to the loop's members.
- Each costs about one FFT per step or O(members²) kernels. Add them by continuation: wirelength, density and DC/thermal first, HF loop and coupling terms as parts settle ([OP43](../../ideas/physics-first/optimization.md)) [I].
- **Throughput.** At ~0.35 ms per loop in numpy, one core does about 10⁷ loop evaluations per hour; a GPU batch should reach 10⁵–10⁶ candidate poses per second [C/I], enough to reject physically bad placements before any router runs.

### Routing as current flow

**Power nets are shapes.**
- For a tree of strips with fixed area A, loss Σ I²·R_s·l/w is minimized by w ∝ I (constant current density). The minimum is P = R_s·(Σ I·l)²/A [C].
- So the topology to minimize is the Steiner tree weighted by current, Σ I·l (a Gilbert network), and widths then follow current.
- The POC baseline already sits on this law: every branch is about 0.67 mm/A, and its 1-D loss is within 0.2% of the optimum for its topology. Topology optimization's extra 14.5% comes from topology and 2-D spreading at pads and junctions [C].
- IPC-2221 widths answer a thermal question (w ∝ I^1.38 at fixed ΔT), not a loss question. Use the larger of the two widths.

**Signals are paths with physics-priced edges.**

| Cost term | Physics | Data |
|---|---|---|
| Reference continuity | return detours around slots, raising loop L and common-mode voltage | h_eff map, split and void polygons |
| Impedance deviation | reflection from width or reference change | per-layer w(Z0) |
| Coupling potential | crosstalk and EMI to declared victims | aggressor field from placement |
| Via transition | loop L of the return via, stub resonance | filament kernel, via model |
| Congestion history | shared copper resource | PathFinder (VPR defaults, [PathFinder](../routing/pathfinder-negotiated-congestion.md)) |

- FanoutNet already weights reference-layer shielding ([PathFinder](../routing/pathfinder-negotiated-congestion.md)); we would make each weight a physical spend from the ledger.

**One price field.**
- Negotiated congestion, multicommodity-flow relaxations and min-max resource sharing are the same Lagrangian idea. BonnRoute's resource sharing solves chip global routing near-optimally on industrial chips (Müller, Radke, Vygen, *Math. Prog. Comp.* 2011) [S].
- Our topology optimization's area multiplier is also a price. Pours and signals should negotiate per-cell, per-layer copper prices (POC: a 4× corridor price halved corridor copper for +24% loss) [C].

**Angles and curves.**
- For a fixed topology, octilinear wiring is ~5% longer than any-angle; rectilinear is 23–31% longer ([topological-routing](../routing/topological-routing.md)) [P].
- An unmitred 90° corner with 10–20 fF excess C reflects |Γ| ≈ 0.002–0.003 at 1 GHz, 0.016–0.031 at 10 GHz and 0.05–0.09 at 30 GHz [C].
- Arcs therefore matter for mm-wave lines, flex bends and minimum gaps in dense escapes (TopoR claims ~30% larger gaps than 45° [V]). Photonic Euler (clothoid) bends help because dielectric waveguides are curvature-sensitive; PCB quasi-TEM lines are not, below tens of GHz [S/I].
- **Elastic bands** (Quinlan–Khatib) relax a fixed-homotopy path under tension plus potentials; with coupling and reference fields as the potentials they tidy critical routes without changing topology [S/I].

**Pairs and length matching.** A diff pair is one ribbon with fixed internal geometry; a length-match group is an equality constraint whose multiplier prices meander area ([diff-pair-routing](../routing/diff-pair-routing.md), [length-matching](../routing/length-matching-and-buses.md)) [I].

### Search at scale

| Method | Use it for | Physics angle |
|---|---|---|
| Gradient + continuation | global placement and shape synthesis | smooth physics first, field terms later |
| Multi-fidelity ladder (kernel → sheet → PEEC/FastHenry → openEMS) | verifying finalists | escalate only when the margin is inside the cheaper model's error (V4 trust radius) |
| Bayesian optimization (MOTPE, multi-fidelity) | 5–20 knobs: weights, stackup choice, grid | objective = budget margins, not HPWL ([bayesian-tuning](../solvers/bayesian-tuning.md)) |
| MAP-Elites / CMA-MAE | portfolios | descriptors in physical units: nH, K, mV, dB ([QD](../solvers/metaheuristics-and-qd.md)) |
| Evolution / LLM-evolved heuristics | cost schedules and move sets | fitness from full-solver budgets on held-out boards |
| RL with a red team | adversarial excitations, reward hacking | adversary maximizes victim noise or IR drop over switching phases and load steps (V2 extended) |
| Surrogates (CNN, neural operator) | screening, warm starts | trained on synthetic boards labelled by the exact solver; accepted designs re-solved |

- **Compute arithmetic** [C/I]: sheet solves at 0.1 mm take ~0.2 s per layer (about 7 × 10⁴ per hour on 4 cores). Greedy ESO-style pour screening needs ~14 solves per shape against ~200 for SIMP, and reached 1.88 vs 1.79 mΩ: screen greedy, finish with SIMP. "Near-infinite compute" buys breadth (seeds, portfolios, adversaries), not finer grids: R converged to 0.5% at 0.1 mm.

### Legalization: from continuous to DRC-legal

| Continuous result | Operation | Tool | Hard rule enforced |
|---|---|---|---|
| Density field | filter radius / robust projection during optimization | own (numpy, JAX) | minimum width/space, etch tolerance |
| Thresholded field | marching-squares contour at ρ = 0.5 | contourpy (BSD-3) | — |
| Polygon | close by gap_min, then open by w_min (round joins), clip keep-outs, keep source-connected parts, simplify | Shapely / pyclipper | sliver, acid trap, clearance, islands |
| Smooth outline | biarc fit with minimum radius | own | curvature (optional) |
| Discrete leftovers | via sites and counts, relief style, layer choice | CP-SAT | integrality, via-to-via spacing |
| Placement | min-displacement legalization with physics-weighted displacement | CP-SAT ([legalization](../placement/legalization.md)) | courtyard, keep-out |
| Everything | physics re-solve, then `kicad-cli pcb drc` on the re-opened board | own + KiCad | budgets within margin; DRC = 0 |

- **POC** [C]: legalization cost 0.0% R at a 0.5 mm minimum on the equal-area design and +2.8% on a thin low-area design.
- Opening at 1.0 mm cut a 0.70 mm neck and disconnected a load. The minimum width must set the filter radius, and the legalizer must re-check source-to-every-load connectivity.
- Photonics has the same pipeline: foundry rules inside topology optimization (Hammond et al. 2021) and minimum-distortion legalization (OptiClear, 2026) [S/P].

## Recommendations for our system

- **Kernels first.** Implement the loop, K0 thermal and crosstalk kernels as pure JAX or PyTorch functions, so the Cypress-style placer can differentiate through them. Validate each against the F2/F3 references (PEECN, FasterCap, the finite-volume thermal solver) before using it in a loss ([solver-ladder](solver-ladder.md), [physics-critics](physics-critics.md)) [I].
- **Use the loop kernel, not a proxy.** If a proxy is unavoidable, choose it by h_eff relative to the loop's narrow dimension b: L ∝ perimeter within ±8% at h ≤ b/4 and ±3% at h ≤ b/15, with a constant of about 0.85·L′(w, h) (corner overlap). Area is wrong whenever a plane is that close [C].
- **One sheet solver with adjoint per layer** for IR, HF pour L and heat. Expose `sensitivity(objective)` as a tool, so the agent and humans can ask where copper should go ([copper-shape-synthesis](copper-shape-synthesis.md)) [C/I].
- **Power nets:** Gilbert-tree topology with width ∝ current, then shape synthesis where amps or margins justify it. **Signals:** PathFinder with physics-priced edges. **Both** share a per-layer price field inside the joint loop ([joint-place-route](joint-place-route.md)) [I].
- **Spend compute by criticality:** continuation, trust-radius-gated fidelity escalation, QD portfolios in physical descriptors, adversarial excitations for budgets with small margins [I].
- **Hard rules stay hard:** fab and DRC rules are constraints or projections, never penalties traded against physics; every candidate ends with a physics re-solve and KiCad DRC.

## Conflicts and open questions

- **Loop-area proxy vs perimeter.** N7 ([priority-agents](../../ideas/original/priority-agents-and-negotiation.md#n7-hot-loop-micro-placer-minimizing-estimated-nanohenries--new)) and the joint-loop doc's "hot-loop area" term assume area. Our kernel says that near a plane, perimeter × depth dominates. Reconcile with the power workstream's PEEC ([power-copper](power-copper.md)) and a FastHenry check [C].
- **Our kernel assumes uniform current across the width and an infinite ideal plane.** Workstream 3's PEECN solves the HF current split and matches FastHenry within 1.3% ([open-solvers](open-solvers.md), [sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py)); use it as the reference and ours for batched gradients. Below ~1 MHz the return spreads and image PEEC underestimates L. Slotted planes are untested [C].
- **Shadow prices are local.** Multipliers of a non-convex problem hold only near the current design; explanations need a "valid within" margin [I].
- **No PCB benchmark exists for physics-aware routing costs.** The first test is reference-crossing count and crosstalk at equal completion vs plain PathFinder ([OP31](../../ideas/physics-first/optimization.md)) [I].
- **Timings are CPU time on a shared, loaded 4-core VM**; GPU numbers are estimates [C/I].

## Sources

- Scripts: [op_placement_kernels.py](../../../tools/research/physics/op_placement_kernels.py), [op_topopt_pour.py](../../../tools/research/physics/op_topopt_pour.py)
- Research notes: [solver_toolbox.md § 2, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [routing_classics_supplement.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md)
- Müller, Radke, Vygen, "Faster min–max resource sharing in theory and practice", *Math. Prog. Comp.* 2011: https://link.springer.com/doi/10.1007/s12532-011-0023-y [S]
- Hammond et al., *Opt. Express* 2021: https://dspace.mit.edu/handle/1721.1/131097 [S]; OptiClear: https://arxiv.org/abs/2607.03632 [P]
- FDTDX (MIT): https://github.com/ymahlau/fdtdx [P: LICENSE]; ceviche (MIT): https://github.com/fancompute/ceviche [P: LICENSE]
- Euler bends (photonics): https://kb.flexcompute.com/tidy3d/examples/WaveguideBend.html [S]
- TopoR arcs and isotropic routing (vendor): https://pcdandf.com/pcdesign/index.php/2009-archive-articles/5203-advantages-of-isotropic-pcb-routing [V]
- Grover, *Inductance Calculations* (rectangle and parallel-filament formulas) [S]; Nikolova, Bandler, Bakr, IEEE MTT 52(1), 2004 (adjoint EM sensitivities) [S]; Quinlan & Khatib, ICRA 1993 (elastic bands) [S]

See also: [joint-place-route](joint-place-route.md) · [copper-shape-synthesis](copper-shape-synthesis.md) · [design-reasoning-architecture](design-reasoning-architecture.md) · [physics-ir](physics-ir.md) · [solver-ladder](solver-ladder.md) · [solvers/analytical-differentiable](../solvers/analytical-differentiable.md) · [routing/topological-routing](../routing/topological-routing.md) · [ideas: optimization](../../ideas/physics-first/optimization.md)
