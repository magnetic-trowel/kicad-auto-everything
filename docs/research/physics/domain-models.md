# Physics domain models: power copper, SI/EMI/RF, thermal/HV/manufacturing, design reasoning, physics in the optimizer, cross-domain transplants

**Status:** partial (computed on synthetic cases, compared with closed forms and published anchors; little of it used in layout; nothing measured by us).
**First published:** 2026-10-22, commits [ba45def](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ba45defde956f7d73cf07929345b86e4793cd1aa) (scripts), [0538ab2](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0538ab23b72c16789ab0001095c32a089173047f) (power), [11fc505](https://github.com/magnetic-trowel/kicad-auto-everything/commit/11fc50536849f0419f46e2ef473be249798e0625) (SI/EMI/RF), [5d072c3](https://github.com/magnetic-trowel/kicad-auto-everything/commit/5d072c3150fdf0a3086ad7103f536ed02dcfa246) (thermal/HV/mfg docs), [a2750c8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/a2750c88a35e0cbd735f05098ef0a149951741a0) (design reasoning), [1bf5802](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1bf5802f66a35f9e3bf528a1c34071973b8d5799) (optimization) on branch `claude/vigilant-mayer-i91rrr`.

Six workstreams built small solvers for the physics behind layout rules and used them to replace rules by budgets. The main overturns (loop L scales with length × h/w, not area; keep the plane under inductors; via spread beats via count) hold within the models. **All results are model against model; the only external anchors are published vendor/literature numbers, not our measurements.** The detail lives in the topic docs linked per section; this page gives the mechanisms and headline numbers.

## Idea and how it works

### Power copper ([power-copper](../../topics/physics/power-copper.md), [pdn-and-commutation](../../topics/physics/pdn-and-commutation.md))
- Classify copper by waveform, not net name: nodes get dv/dt and swing, branches di/dt, I_rms, I_dc. Each piece minimises a·L + b·C + g·R with a = ½I_sw²f, b = ½V²f, g = I_rms².
- Width optimum over a plane (L = μ0hl/w, C = εwl/h, R = ρl/(wt)): w* = √((aμ0h + gρ/t)/(bε/h)); with no R term Z0* = √(b/a). Invariants L·C = (l/v)² and R·Area = R_s·l², so only length lowers all three.
- One 2-D Laplace solve on the copper mask gives N□ (squares): R = R_s·N□ for DC, L = μ0·d·N□ for plane-pair spreading below the first resonance. Vias are Peaceman sub-cell wells adding (1/2π)·ln(0.198Δx/r) squares.
- Filament cross-section solver (skin, proximity); nodal filament PEEC over a PEC image (Grover/Ruehli partials, complex R + jωL) for commutation loops, via clusters, decap mounts, Kelvin error V = Δφ − jω∫A·dl; Dodd–Deeds eddy solution for inductors over copper.

### SI, EMI and RF ([fields-si-emi](../../topics/physics/fields-si-emi.md), [fields-emi-budget](../../topics/physics/fields-emi-budget.md), [rf-geometry](../../topics/physics/rf-geometry.md))
- One metric replaces about a dozen plane rules: return-path EMF V_ret = I(f)·Σ_k ΔZ_k(f), ΔZ_k = jωΔL_k + R_cav,k, one term per slot, split, merged antipad, reference change, return-via distance, stitching cap, edge offset. Slot ΔL ≈ μ0·l/(2·ln(4l/g)); return via at a reference change from the radial waveguide Z = (ωμt/2)[H0(ka) − H0(ks)].
- Meshed-plane PEEC: plane current minimises magnetic energy under KCL, (NᵀLN)z = −Nᵀ(LI_p + m); node potentials give the plane voltage between cable points (transfer-inductance maps κ_ab).
- 2-D FD field solver (crosstalk K_L, K_C, NEXT_sat = (K_L + K_C)/4); Okoshi/Lei cavity model with stitching vias shorted by Schur complement, compared with the Belov wire-medium cut-off; an EMI chain trapezoid spectrum → drive current → V_cm = ωL_cm·I → current-driven cable antenna → CISPR 32 Class B.

### Thermal, HV, manufacturing ([thermal-physics](../../topics/physics/thermal-physics.md), [hv-and-manufacturing-physics](../../topics/physics/hv-and-manufacturing-physics.md))
- Board as a 2-D fin: G_s∇²T = h_total·T − q, point response P/(2πG_s)·K0(r/λ), λ = √(G_s/h_total) (8 mm bare FR-4, 38 mm 2-layer 1 oz, 64 mm 6-layer). Below ~2λ the board is nearly isothermal, so spacing hot parts is measured in λ. A 2.5-D finite-volume solver checks it; placement uses kernel + adiabatic-edge image rings.
- HV insulation as three mechanisms: gas discharge (clearance), surface tracking (creepage), CAF (via spacing). Corner field E_max ∝ (g/r)^(1/3) by 2-D BEM; streamer inception ∫α_eff ds ≥ K; altitude factors equal the pressure ratio (Paschen similarity).
- Manufacturing: etch min space ≈ 47 µm + 1.65·t; throwing power 1/cosh(L/2Λ); tombstoning torque ratio; Monte Carlo impedance tolerance. Constraints are encoded by origin: legal/fab-absolute hard, fab-recommended as yield cost, physics budgets soft.

### Design reasoning ([design-reasoning-architecture](../../topics/physics/design-reasoning-architecture.md), [schematic-to-physics](../../topics/physics/schematic-to-physics.md))
- Simulate the schematic (ngspice/Xyce) for per-net swing, dv/dt, di/dt and spectrum; then susceptibility of every injection site by one adjoint solve: Yᵀλ = e, H_k = λᵀb_k (SPICE `.noise` is this method; fictitious noise resistors at candidate sites read |H_k|).
- Budget split: minimise Σ k_i/p_i s.t. Σ s_i·p_i = B gives a share ∝ √(k_i·s_i) ((k·s)^(1/3) under RSS). Edge budget for an erf-edged LC: overshoot ≈ exp(−(2πσ/T)²/2)·exp(−π/2Q), σ = t_sw/2.563, inverted to L_max ≈ σ²/(2C·ln(1/a′)) (implemented in `kae/src/kae/physics/priors.py hot_loop_budget()`).
- Least-slack ordering τ = budget / achievable floor; τ < 1 is an infeasibility certificate. Master objective: layout invisibility index LII = max over outputs |y(layout) − y(floor)|/B_y.

### Physics in the optimizer ([physics-in-the-loop-optimization](../../topics/physics/physics-in-the-loop-optimization.md), [copper-shape-synthesis](../../topics/physics/copper-shape-synthesis.md))
- One sheet operator for DC IR drop, inductive pour over a plane, and heat spreading (coefficients 1/R_s, 1/(μ0·h_eff), k·t + 2h_c). Crossover f_c = R_s/(2π·μ0·h).
- Pour synthesis by SIMP: Q4 elements, p = 3, density filter r = 0.5 mm, Heaviside β 1→32, optimality-criteria update, 200 iterations, minimising loss at fixed area (self-adjoint). Non-self-adjoint objectives use one transposed solve; topological derivative by polarization tensor. Fab-legal output: marching squares, Minkowski close/open by gap_min/w_min, keep-out clip, source-connected islands, KiCad zone export.
- Power-tree law: at fixed area w ∝ I is optimal and P_min = R_s(Σ I·l)²/A.

### Cross-domain transplants ([cross-domain-lessons](../../topics/physics/cross-domain-lessons.md))
125 ideas (XD1–XD125), 12 worked lessons, e.g. stream-function coil design (slit cost (π/4)R_s(Δψ/I)²), Murray/Kelvin branched transport, transfer length L_T = p·√(R_via/(R_s1 + R_s2)) for via fields (rows across the flow at entry and exit), screening lengths K0(r/λ) for thermal, decap reach and via transfer, power-grid N-1 / LODF what-ifs, Tichelmann reverse return.

## Results

All [C], synthetic geometry, from the linked topic docs.

| Domain | Result |
|---|---|
| Power | 30 mm pad-to-pad: 2 mm trace 14.1 □, 8 mm pour 3.7 □, full 44×30 mm region 1.47 □; a sharp corner adds 0.55 □ and no steady hot spot; 4-via cluster at 0.6 mm pitch = 0.71× one via's spreading L (not 0.25); lateral 4×2 mm loop 0.93 nH at h 0.1 mm, gap 0.2→4 mm moves L only 0.89→1.35 nH; alternating decap orientation −16–39%; PEEC within 1–7% of closed forms, Archambeault 1-inch anchor reproduced (157 vs 154 pH) but not 10-inch (276 vs 545 pH) |
| SI/EMI | microstrip loop L′ 0.302 vs 0.298 nH/mm; slot 20×0.4 mm at h 0.2 mm 2.34 nH; trace 3h from an edge raises plane voltage ×2.7–6.9; cavity 40×30 mm: open 1.80 GHz, 5 mm stitch grid 7.45 GHz, random 48-via patterns 3.35–5.0 GHz; EMI chain at 50 MHz: slot −24 dB, split −38 dB, stitching cap +10 dB |
| Thermal/HV/mfg | FV matches K0 within 4% at 5–40 mm; cut across heat flow costs 20–30× one along it; kernel + image rings within ~2% of FV; corner field 4.94× at r = 0.02g; tombstoning ratio 2 (1206) to 110 (01005); σ_Z 2.2–2.9%, h carries 46–80% of the variance |
| Reasoning | noise adjoint matches direct AC to 6e-13 and ngspice 42 `.noise` to four digits; 12 V buck hot-loop budget 1.05 nH exact, 1.36 closed form; 48 V bridge budget must come from EMI, not overshoot |
| Optimizer | topology-optimised pour 1.789 vs 2.092 mΩ for a human trunk-and-branch at equal area (−14.5%); adjoint vs finite-difference gradients agree to 3.5×10⁻⁷; 9 ms–0.18 s per solve |
| Cross-domain | Kelvin sizing (w ∝ I) 52% loss vs equal width; IPC-2221 equal-ΔT sizing 58% loss but 135% worst drop; end via columns carry 59% of a 10×4 via field |

**Red-team corrections that touch this page** ([redteam-corrections](redteam-corrections.md)):
- `pw_cells ring` Q values (31–173) belong to no single geometry (R fixed, L free).
- EMI chain: the same-edge cable benefit was an input (`same_edge_db`), not a result; a board-vs-cable model gives 6–30 dB. "slot > cap > edge" holds for one case only; the 3 dB edge-rate figure omits the ring term (12–21 dB).
- Slot law is ℓ/ln(4ℓ/g), not linear; `fe_field2d` is under-resolved by 1.3–1.9 points.
- Convex copper floors move 2.2–12.8% between grids; the −14.5% pour gain is "the size of fab and part tolerance", a rule-level effect, not a breakthrough.
- Thermal kernel vs FV is "method against the same fin model, not independent"; λ = 37.7 mm reproduces independently.
- Stitching pitch follows isolation distance plus f_p > f_max, not λ/20 (derivation audit D8).

## Verdict

Coherent and internally checked, but uncalibrated, and the honest magnitudes are modest: a competent trunk is near its 1-D optimum, so pour synthesis pays only above ~3–5 A or at tight margins; absolute EMI levels are "ranking only". What reached the tools: the PEEC loop model (re-implemented in `kae/src/kae/physics/exact.py`, tested equal to `pw_peec`), the fin kernel with image rings (`kae/src/kae/physics/structures.py ThermalField`), H-J L′ with image partials (`kernels.py`), `priors.py` budgets, and rail-width rules cited by `kae/src/kae/route/critical_rails.py`. Open: an LCR measurement per inductor family (plane and cut-out), openEMS checks of slot ΔL and fences, an IR-camera or Elmer thermal check, a transient check of corners and reliefs, large-signal co-simulation where linearised budgets fail (slow-edged bridges).

## Code

`tools/research/physics/`, all print-only with synthetic inputs (`op_topopt_pour.py --export` writes a KiCad zone; `dr_noise_adjoint.py` writes a temporary ngspice netlist):
- power: `pw_sheet.py`, `pw_xsec.py`, `pw_peec.py`, `pw_eddy.py`, `pw_cells.py`;
- fields: `fe_peec_plane.py`, `fe_field2d.py`, `fe_cavity.py`, `fe_emi_budget.py`, `fe_geometry.py`;
- thermal/HV/mfg: `tm_board_thermal_fv.py`, `tm_thermal_analytic.py`, `tm_hv_field.py`, `tm_paschen_altitude.py`, `tm_mfg_physics.py`, `tm_solder_reflow.py`, `tm_impedance_tolerance.py`;
- reasoning: `dr_switch_cell_budget.py`, `dr_coupling_oracles.py`, `dr_noise_adjoint.py`;
- optimizer: `op_topopt_pour.py` (needs shapely ≥ 2, contourpy), `op_placement_kernels.py`;
- cross-domain: `xd_sheet.py`, `xd_power_tree.py`, `xd_lengths.py`, `xd_loop_coupling.py`.

Run `python tools/research/physics/<script>.py [section]`. Ideas: [power](../../ideas/physics-first/power.md), [si-emi-rf](../../ideas/physics-first/si-emi-rf.md), [thermal-hv-mfg](../../ideas/physics-first/thermal-hv-mfg.md), [reasoning](../../ideas/physics-first/reasoning.md), [optimization](../../ideas/physics-first/optimization.md), [cross-domain](../../ideas/physics-first/cross-domain.md).

## Related

[physics-ir-and-core](physics-ir-and-core.md), [first-principles-lenses](first-principles-lenses.md), [physics-critics-and-passports](physics-critics-and-passports.md), [validation-program](validation-program.md), [placement area](../placement/README.md) (where the place terms use these kernels).
