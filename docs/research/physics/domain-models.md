# Physics domain models: power copper, SI/EMI/RF, thermal/HV/manufacturing, design reasoning, physics in the optimizer, cross-domain transplants

**Status:** partial (computed on synthetic cases, compared with closed forms and published anchors; little of it used in layout; nothing measured by us).
**First published:** 2026-10-22, commits [ba45def](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ba45defde956f7d73cf07929345b86e4793cd1aa) (scripts), [0538ab2](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0538ab23b72c16789ab0001095c32a089173047f) (power), [11fc505](https://github.com/magnetic-trowel/kicad-auto-everything/commit/11fc50536849f0419f46e2ef473be249798e0625) (SI/EMI/RF), [5d072c3](https://github.com/magnetic-trowel/kicad-auto-everything/commit/5d072c3150fdf0a3086ad7103f536ed02dcfa246) (thermal/HV/mfg docs), [a2750c8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/a2750c88a35e0cbd735f05098ef0a149951741a0) (design reasoning), [1bf5802](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1bf5802f66a35f9e3bf528a1c34071973b8d5799) (optimization) on branch `claude/vigilant-mayer-i91rrr`.

Scope: six workstreams that built small solvers for the physics behind layout rules and replaced rules by budgets; mechanisms, conclusions and verdict here; numbers and detail in the topic doc linked per section. Main overturns (loop L scales with length × h/w, not area; keep the plane under inductors; via spread beats via count) hold within the models. **All results model against model; the only external anchors are published vendor/literature numbers, not our measurements.**
Keys: waveform copper roles, a·L + b·C + g·R, w*, Z0*, squares N□, Peaceman well, filament PEEC, Dodd–Deeds, return-path EMF V_ret, meshed-plane PEEC, cavity model, EMI chain, CISPR 32, fin λ, K0 kernel, HV insulation, Paschen, etch min space, SPICE `.noise` adjoint, budget split, L_max edge budget, least-slack τ, LII, sheet operator, SIMP pour synthesis, power-tree law, XD1–XD125, Kelvin sizing

## Idea and how it works

### Power copper ([power-copper](../../topics/physics/power-copper.md), [pdn-and-commutation](../../topics/physics/pdn-and-commutation.md))
- Classify copper by waveform, not net name: nodes get dv/dt and swing, branches di/dt, I_rms, I_dc. Each piece minimises a·L + b·C + g·R, a = ½I_sw²f, b = ½V²f, g = I_rms².
- Width optimum over a plane (L = μ0hl/w, C = εwl/h, R = ρl/(wt)): w* = √((aμ0h + gρ/t)/(bε/h)); no R term: Z0* = √(b/a). Invariants L·C = (l/v)², R·Area = R_s·l²: only length lowers all three.
- One 2-D Laplace solve on the copper mask gives N□ (squares): R = R_s·N□ (DC), L = μ0·d·N□ (plane-pair spreading below the first resonance). Vias = Peaceman sub-cell wells adding (1/2π)·ln(0.198Δx/r) squares.
- Filament cross-section solver (skin, proximity); nodal filament PEEC over a PEC image (Grover/Ruehli partials, complex R + jωL) for commutation loops, via clusters, decap mounts, Kelvin error V = Δφ − jω∫A·dl; Dodd–Deeds eddy solution for inductors over copper.

### SI, EMI and RF ([fields-si-emi](../../topics/physics/fields-si-emi.md), [fields-emi-budget](../../topics/physics/fields-emi-budget.md), [rf-geometry](../../topics/physics/rf-geometry.md))
- One metric replaces ~12 plane rules: return-path EMF V_ret = I(f)·Σ_k ΔZ_k(f), ΔZ_k = jωΔL_k + R_cav,k, one term per slot, split, merged antipad, reference change, return-via distance, stitching cap, edge offset. Slot ΔL ≈ μ0·l/(2·ln(4l/g)); return via at a reference change from the radial waveguide Z = (ωμt/2)[H0(ka) − H0(ks)].
- Meshed-plane PEEC: plane current minimises magnetic energy under KCL, (NᵀLN)z = −Nᵀ(LI_p + m); node potentials give the plane voltage between cable points (transfer-inductance maps κ_ab).
- 2-D FD field solver (crosstalk K_L, K_C, NEXT_sat = (K_L + K_C)/4); Okoshi/Lei cavity model with stitching vias shorted by Schur complement, compared with the Belov wire-medium cut-off; EMI chain: trapezoid spectrum → drive current → V_cm = ωL_cm·I → current-driven cable antenna → CISPR 32 Class B.

### Thermal, HV, manufacturing ([thermal-physics](../../topics/physics/thermal-physics.md), [hv-and-manufacturing-physics](../../topics/physics/hv-and-manufacturing-physics.md))
- Board as 2-D fin: G_s∇²T = h_total·T − q; point response P/(2πG_s)·K0(r/λ), λ = √(G_s/h_total) (8 mm bare FR-4, 38 mm 2-layer 1 oz, 64 mm 6-layer). Below ~2λ the board is nearly isothermal: spacing hot parts is measured in λ. Checked by a 2.5-D finite-volume solver; placement uses kernel + adiabatic-edge image rings.
- HV insulation = three mechanisms: gas discharge (clearance), surface tracking (creepage), CAF (via spacing). Corner field E_max ∝ (g/r)^(1/3) by 2-D BEM; streamer inception ∫α_eff ds ≥ K; altitude factors = pressure ratio (Paschen similarity).
- Manufacturing: etch min space ≈ 47 µm + 1.65·t; throwing power 1/cosh(L/2Λ); tombstoning torque ratio; Monte Carlo impedance tolerance. Constraints encoded by origin: legal/fab-absolute hard, fab-recommended as yield cost, physics budgets soft.

### Design reasoning ([design-reasoning-architecture](../../topics/physics/design-reasoning-architecture.md), [schematic-to-physics](../../topics/physics/schematic-to-physics.md))
- Simulate the schematic (ngspice/Xyce) for per-net swing, dv/dt, di/dt, spectrum; susceptibility of every injection site by one adjoint solve: Yᵀλ = e, H_k = λᵀb_k (SPICE `.noise` is this method; fictitious noise resistors at candidate sites read |H_k|).
- Budget split: minimise Σ k_i/p_i s.t. Σ s_i·p_i = B → share ∝ √(k_i·s_i) ((k·s)^(1/3) under RSS). Edge budget for an erf-edged LC: overshoot ≈ exp(−(2πσ/T)²/2)·exp(−π/2Q), σ = t_sw/2.563, inverted to L_max ≈ σ²/(2C·ln(1/a′)) (implemented in `kae/src/kae/physics/priors.py hot_loop_budget()`).
- Least-slack ordering τ = budget / achievable floor; τ < 1 is an infeasibility certificate. Master objective: layout invisibility index LII = max over outputs |y(layout) − y(floor)|/B_y.

### Physics in the optimizer ([physics-in-the-loop-optimization](../../topics/physics/physics-in-the-loop-optimization.md), [copper-shape-synthesis](../../topics/physics/copper-shape-synthesis.md))
- One sheet operator for DC IR drop, inductive pour over a plane, heat spreading (coefficients 1/R_s, 1/(μ0·h_eff), k·t + 2h_c). Crossover f_c = R_s/(2π·μ0·h).
- Pour synthesis by SIMP: Q4 elements, p = 3, density filter r = 0.5 mm, Heaviside β 1→32, optimality-criteria update, 200 iterations, minimising loss at fixed area (self-adjoint). Non-self-adjoint objectives: one transposed solve; topological derivative by polarization tensor. Fab-legal output: marching squares, Minkowski close/open by gap_min/w_min, keep-out clip, source-connected islands, KiCad zone export.
- Power-tree law: at fixed area w ∝ I is optimal, P_min = R_s(Σ I·l)²/A.

### Cross-domain transplants ([cross-domain-lessons](../../topics/physics/cross-domain-lessons.md))
125 ideas (XD1–XD125), 12 worked lessons, e.g. stream-function coil design (slit cost (π/4)R_s(Δψ/I)²), Murray/Kelvin branched transport, transfer length L_T = p·√(R_via/(R_s1 + R_s2)) for via fields (rows across the flow at entry and exit), screening lengths K0(r/λ) for thermal, decap reach and via transfer, power-grid N-1 / LODF what-ifs, Tichelmann reverse return.

## Results

All [C], synthetic geometry. Headline numbers live in the topic docs; each row names the canonical section.

| Domain | Result | Numbers |
|---|---|---|
| Power | squares predict R and plane-pair L; corners add little steady-state R; via-cluster spread, not count, sets spreading L; lateral loop L over a close plane barely depends on gap; decap orientation matters; PEEC agrees with closed forms and Archambeault's 1-inch anchor, not his 10-inch one | [power-copper §3–§4](../../topics/physics/power-copper.md#3-trace-vs-pour-vs-plane), [pdn-and-commutation §1–§3](../../topics/physics/pdn-and-commutation.md#1-commutation-loop-geometry) |
| SI/EMI | microstrip loop L′ and slot ΔL reproduced by meshed-plane PEEC; a trace near the board edge multiplies plane voltage; stitching grids beat random patterns; EMI chain ranks slot > split > stitching cap for one case | [fields-si-emi §2, §5](../../topics/physics/fields-si-emi.md#2-discontinuities-as-extra-return-impedance), [fields-emi-budget §2](../../topics/physics/fields-emi-budget.md#2-worked-cases-fe_emi_budgetpy-c) |
| Thermal/HV/mfg | FV matches the K0 fin solution; cuts across heat flow cost 20–30× cuts along it; kernel + image rings ≈ FV; corner field follows the wedge law; tombstoning torque ratio scales as 1/L²; dielectric thickness dominates impedance variance | [thermal-physics](../../topics/physics/thermal-physics.md#the-board-as-a-fin), [hv-and-manufacturing-physics](../../topics/physics/hv-and-manufacturing-physics.md#field-enhancement-at-copper-corners-and-edges) |
| Reasoning | noise adjoint matches direct AC and ngspice `.noise`; 12 V buck hot-loop budget 1.05 nH exact vs 1.36 nH closed form; the 48 V bridge budget must come from EMI, not overshoot | [schematic-to-physics](../../topics/physics/schematic-to-physics.md) |
| Optimizer | topology-optimised pour −14.5% loss vs a human trunk-and-branch at equal area; adjoint gradients match finite differences; 9 ms–0.18 s per solve | [copper-shape-synthesis](../../topics/physics/copper-shape-synthesis.md#proof-of-concept) |
| Cross-domain | Kelvin sizing roughly halves loss vs equal width; IPC-2221 equal-ΔT sizing raises the worst drop; end via columns carry most of a via field's current | [cross-domain-lessons L2, L3](../../topics/physics/cross-domain-lessons.md#l2-murray-kelvin-branched-transport--widths-and-topology-of-power-trees) |

Red-team corrections ([redteam-corrections](redteam-corrections.md)):
- `pw_cells ring` Q values, `same_edge_db` (an input; board-vs-cable model 6–30 dB), `fe_field2d` resolution, grid-dependent floors: see the red-team page.
- EMI chain: "slot > cap > edge" holds for one case only; the 3 dB edge-rate figure omits the ring term (12–21 dB). Slot law is ℓ/ln(4ℓ/g), not linear.
- The −14.5% pour gain is "the size of fab and part tolerance", a rule-level effect, not a breakthrough.
- Thermal kernel vs FV is "method against the same fin model, not independent"; λ = 37.7 mm reproduces independently.
- Stitching pitch follows isolation distance plus f_p > f_max, not λ/20 (derivation audit D8).

## Verdict

- Coherent and internally checked, uncalibrated; honest magnitudes modest: a competent trunk is near its 1-D optimum, so pour synthesis pays only above ~3–5 A or at tight margins; absolute EMI levels are "ranking only".
- Reached the tools: PEEC loop model (re-implemented in `kae/src/kae/physics/exact.py`, tested equal to `pw_peec`); fin kernel with image rings (`kae/src/kae/physics/structures.py ThermalField`); H-J L′ with image partials (`kernels.py`); `priors.py` budgets; rail-width rules cited by `kae/src/kae/route/critical_rails.py`.
- Open: LCR measurement per inductor family (plane and cut-out); openEMS checks of slot ΔL and fences; IR-camera or Elmer thermal check; transient check of corners and reliefs; large-signal co-simulation where linearised budgets fail (slow-edged bridges).

## Code

`tools/research/physics/`, print-only, synthetic inputs (`op_topopt_pour.py --export` writes a KiCad zone; `dr_noise_adjoint.py` writes a temporary ngspice netlist); run `python tools/research/physics/<script>.py [section]`:
- power: `pw_sheet.py`, `pw_xsec.py`, `pw_peec.py`, `pw_eddy.py`, `pw_cells.py`;
- fields: `fe_peec_plane.py`, `fe_field2d.py`, `fe_cavity.py`, `fe_emi_budget.py`, `fe_geometry.py`;
- thermal/HV/mfg: `tm_board_thermal_fv.py`, `tm_thermal_analytic.py`, `tm_hv_field.py`, `tm_paschen_altitude.py`, `tm_mfg_physics.py`, `tm_solder_reflow.py`, `tm_impedance_tolerance.py`;
- reasoning: `dr_switch_cell_budget.py`, `dr_coupling_oracles.py`, `dr_noise_adjoint.py`;
- optimizer: `op_topopt_pour.py` (needs shapely ≥ 2, contourpy), `op_placement_kernels.py`;
- cross-domain: `xd_sheet.py`, `xd_power_tree.py`, `xd_lengths.py`, `xd_loop_coupling.py`.

Ideas: [power](../../ideas/physics-first/power.md), [si-emi-rf](../../ideas/physics-first/si-emi-rf.md), [thermal-hv-mfg](../../ideas/physics-first/thermal-hv-mfg.md), [reasoning](../../ideas/physics-first/reasoning.md), [optimization](../../ideas/physics-first/optimization.md), [cross-domain](../../ideas/physics-first/cross-domain.md). Related: [physics-ir-and-core](physics-ir-and-core.md), [first-principles-lenses](first-principles-lenses.md), [physics-critics-and-passports](physics-critics-and-passports.md), [validation-program](validation-program.md), [placement area](../placement/README.md) (place terms use these kernels).
