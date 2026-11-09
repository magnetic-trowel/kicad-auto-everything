<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Covering the whole frequency range: one reduced model, not a list of bands

Scope: one passive reduced-order model (Galerkin/PRIMA projection of the PEEC system) covering DC to the quasi-static limit for evaluation, router prices and sign-off; evidence on boost; stages R1–R7. Not here: the formal problem and tiers -> [physics-driven-design](physics-driven-design.md); field solver and capacitive prices -> [physics-driven-build](physics-driven-build.md); hop ports -> [physics-hop-ports](physics-hop-ports.md); later results (chaac R2, evaluator speed) -> [field-solver-routing-and-intent](../../research/physics/field-solver-routing-and-intent.md).
Keys: model order reduction, MOR, reduced basis, PRIMA, Galerkin projection, two-sided basis, snapshots, greedy, dual-weighted residual, DC moments, AWE, `kae.em.spectral`, `--spectral`, R1–R7 gates, basis recycling, R–L transition, θ = ωℓ/v, quasi-TEM, wideband

Copper and passive parts have frequency-independent R, L (and P once added), so the response at every frequency and in time lies in a small subspace spanned by solutions at a few frequencies. Skin effect does not break this: it emerges from the filaments through the thickness, and what `nsub` filaments cannot hold is a per-layer surface-impedance factor applied at evaluation ([field-solver-accuracy](../../research/physics/field-solver-accuracy.md)). A band list combines samples by interpolation, with no error estimate; projection combines them by the physics (Galerkin), so resonances between samples come out right.

## 1. What the range has to cover

| Range | Physics that sets it | Harm it decides | Now |
|---|---|---|---|
| DC | resistance | copper loss, rail drop, heating | DC band ([dc](../../../kae/src/kae/excite/dc.py)) |
| ~1 kHz – 1 MHz | R–L transition: return current moves from least resistance to least inductance | ground currents through analog/audio returns; regulator loop ripple | not covered |
| f_sw and harmonics, ~0.1–10 MHz | capacitor ESR/ESL and C split the current; PDN anti-resonance | input/output ripple, supply bounce | fundamental, one point |
| 10–300 MHz | loop L, switch-node ring with C_sw, capacitor self-resonance | overshoot, ringing, CM emissions (CISPR 30–230 MHz), victim pickup | one 10 MHz solve, extrapolated as constant L |
| any, dV/dt-driven | electric field (partial capacitance) | capacitive crosstalk into high-Z nodes, switch-node CM via capacitance | not modelled |
| above the quasi-static limit | retardation, θ = ωℓ/v ≳ 0.3 | transmission-line nets (DDR, USB), radiation (above ~150 MHz on a 5 cm board) | not modelled |

Two bands per aggressor ([kae.excite.evaluate](../../../kae/src/kae/excite/evaluate.py)) joined by the assumed peak shape |Z_f| c₁ I + |L_e| I/t_i fail near resonances (ring, PDN anti-resonance: |H(f)| peaks by Q), in the R–L transition (return path changes), and for capacitive coupling (∝ f, not constant L).

## 2. The options

| # | Option | Pros | Cons |
|---|---|---|---|
| 1 | **Many bands**: S patterns at F ≈ 15–30 log-spaced frequencies, interpolate \|H(f)\|, sum over source spectrum | simple; each sample exact | Q ≈ 10–50 resonances need ~Q points per decade near the peak or are missed silently; no error estimate between samples; S solves per frequency |
| 2 | **Rational fitting** (vector fitting) | smooth interpolation | same many samples; passivity enforced afterwards |
| 3 | **Time-domain field solve** with real waveforms | every frequency at once | thousands of full solves per waveform; a sign-off job, not inner loop |
| 4 | **Projection MOR** (PRIMA, Odabasioglu et al. 1998; reduced-basis methods) | see below | — |
| 5 | **DC moment matching** (AWE/PRIMA at s₀ = 0) | each moment = one exact DC solve + one L apply | convergence radius stops at the first pole; use as extra basis vectors, not alone |

Option 4: PEEC saddle system [Z(s) −D; −Dᵀ 0], Z(s) = R + sL + lumped(s), projected by congruence onto V = span of snapshot solutions; R, L symmetric PSD -> passive by construction (no fitting or passivity repair); order m ≈ 50–100, evaluated at thousands of frequencies or time-stepped at negligible cost; snapshots greedy where estimated output error is largest.

**Use option 4 + option 5's DC moments as extra vectors** [I]: one code path for all frequencies on validated pieces (solver, patterns, observers), lowest bug risk; per-output error estimates; the same model is the SPICE sign-off's parasitic network (§4).

## 3. Evidence: the boost board

Script [`tools/research/physics/em_reduced_basis_check.py`](../../../tools/research/physics/em_reduced_basis_check.py): copper with its 33 two-pad parts lumped in; cell's edge-band injection fixed over frequency; Galerkin projection of the full saddle system; basis = real span of [Re X, Im X].

**One-sided basis** (source solutions only), 3 frequencies: driving point to 1e-4 at 3 MHz, 2e-4 at 30 MHz, 7e-3 at 150 MHz, 2% at 30 kHz (no snapshot in the R–L transition). Transfers fail: with 7 frequencies observers err 5–30% of the largest observer; only a quantity whose own solution is in the basis is variational.

**Two-sided basis** (source + nine observer patterns per snapshot): greedy snapshots DC, 10 MHz, 0.55 MHz, 1.7 MHz, 98 kHz, 300 MHz (last chosen at 78 vectors); under 100 vectors; 1134 s at 4 threads for six snapshot solves of ten right-hand sides. Test frequencies are not snapshots:

| Test frequency | Worst relative error over 9 observers | Worst error / largest observer |
|---|---|---|
| 2 kHz | 5.8e-4 | 8e-8 |
| 50 kHz | 8.7e-4 | 9e-6 |
| 0.7 MHz | 6.8e-5 | 9e-7 |
| 4.4 MHz | 9.2e-5 | 2e-6 |
| 25 MHz | 6.1e-4 | 2e-6 |
| 110 MHz | 3.1e-3 | 2e-5 |
| 220 MHz | 3.7e-3 | 1e-4 |

**Full-system residual is no error estimate**: 10¹–10⁵ (scaled like the iterative solver's) while outputs were right to 1e-4, dominated by components no observer sees. Use the output-based dual-weighted residual rᵀz, z = observer's reduced adjoint (carried by the two-sided basis).

## 4. The design

**LTI system with fixed inputs.** Two-pad parts lumped into the copper; IC pin models (package R, L to an internal die node, die C) as lumped elements on internal nodes. Outside: ideal sources (switch current, core currents, clocks), each a fixed injection b_s with a ledger spectrum (trapezoid of I, D, t_i, f_sw). Observers = fixed functionals c_k: H_ks(s) = c_kᵀ x_s(s) for all s (removes today's per-band patterns computed with ideal copper).

**Basis.**
1. DC solution of every pattern + 2–4 DC moments each (cheap: preconditioner exact at f = 0).
2. Greedy snapshots of every pattern where estimated harm error (weighted by source spectrum and observer limit curve) is largest: frequencies chosen by the harms, not a fixed list.
3. Stop at estimated harm error < 1e-3 of the bound. A model stopped by the snapshot limit, or with a snapshot solve at its iteration limit, reports `converged: false` and marks the totals `uncertain`.

**Harms from the reduced model.**
- Peaks (overshoot, supply bounce, victim pickup): waveform from harmonics H_ks(jnω_sw)·c_n, n to the edge knee, one inverse FFT; ringing emerges from the resonance (no L, C_sw estimate; edge-share and |Z_f| c₁ terms gone).
- Emissions per harmonic vs CISPR line; ripple at f_sw and harmonics vs rail tolerance; low-frequency ground currents per audio/analog victim over its band.
- Same ledger corners; a corner changes only source spectra, so corners cost nothing extra.

**Router.**
- Price fields are linear in currents and each basis vector's flux L·V_I is computed by the projection anyway, so whole-spectrum prices Π = Σ_f w(f) Π(f) combine fixed fields with reduced-model weights; resonant pairs get Q-amplified weight automatically.
- Recycle snapshot frequencies, not basis vectors (vectors measured too inaccurate, §6 R4): a refresh re-solves them concurrently, adding one only where the calibrated error estimate says so.
- Built: [`kae.em.spectral`](../../../kae/src/kae/em/spectral.py), `kae.em.pnr --spectral`. Missed by the design: (a) a hop's per-pattern current must come from the model's own part currents per frequency (ring and copper current split included; ideal-copper flow has neither); (b) projected potentials are KCL multipliers, right at ports and snapshots but off up to 40× between, so crossing prices recover potentials from reduced currents via D φ = (R + jωL) I.

**Sign-off.** The reduced model is a passive RLC-like state space; export it as a SPICE subcircuit with switch and rectifier replaced by device models (= M6 of [physics-driven-design](physics-driven-design.md#8-the-build-with-gates-registered-in-advance)).

## 5. What projection does not cover, and what does

- **Capacitive coupling, plane cavity modes need P** (layered-electrostatics potential coefficients) on the same raster with FFT Toeplitz kernels. (L, P)-PEEC stays symmetric and passive under congruence: same reduction. Validate against FastCap (FastHenry's sibling).
- **Electrically long nets**: quasi-static PEEC holds while θ = ωℓ/v ≲ 0.3, with v = c/√ε_eff (ε_eff = 3.5, FR4 microstrip) and ℓ the board diagonal: f_qs = 0.3·c/(2π·ℓ·√3.5), 153 MHz at 5 cm, 51 MHz at 15 cm ([wideband.py](../../../kae/src/kae/excite/wideband.py) `THETA`, `EPS_EFF`; free-space v would give 286 and 95 MHz). Nets with knee above that: θ-screened, quasi-TEM lines with per-length L, C from the same operators on the cross-section -> routing constraints (impedance by layer, length match, crosstalk spacing), not field prices. Report radiated emission above the limit as not computed, never extrapolate.

## 6. Build stages and their gates

| Stage | What | Gate | Status |
|---|---|---|---|
| R1 | IC pin models into the copper as lumped parts on internal nodes; fixed-source patterns | the two current bands' harms reproduced within 1% | — |
| R2 | two-sided reduced basis, DC moments, greedy by dual-weighted output estimate | reduced vs direct at 10 random frequencies, 1 kHz – 300 MHz, ≤ 1e-3 relative on every observer, on boost and a 4-layer board; model passive | boost passed (below) |
| R3 | harms from the reduced model: waveform peaks, harmonics vs limit lines, low-frequency bands | boost ring frequency and overshoot vs a direct transient of the full system at one corner | — |
| R4 | router prices weighted over the spectrum; basis recycling between refreshes | predicted vs actual dL per pair within the current 0.93–1.06 band | built; holds on check geometry, and on boost where a hop carries the pair's current (below) |
| R4b | hops priced through the ports of the connections they replace | exact for coupling 1 kHz – 300 MHz | built: [physics-hop-ports](physics-hop-ports.md) |
| R5 | P operator (EQS) and capacitive prices | microstrip C per length vs closed form; two-trace mutual C vs FastCap | capacitive prices built, checks and smoke route in [physics-driven-build §3b](physics-driven-build.md#3b-capacitive-prices-stage-e3); FastCap comparison to run |
| R6 | θ screen and quasi-TEM constraints for long nets | Z₀ vs closed form per layer of the stackup | — |
| R7 | SPICE export of the reduced model; nonlinear sign-off | waveform vs the reduced model's own linear transient at small signal | — |

### R2 on boost: passed

7 snapshots (DC, 46 kHz, 0.24, 0.72, 10, 19, 300 MHz), order 111, 30 min at 4 threads. At 10 seeded random frequencies, 1.2 kHz – 132 MHz, worst relative error of any observer's layout share 2.7e-4. Port matrix had no negative eigenvalue beyond rounding (−8e-14 against 3e4). 4-layer case (chaac): [field-solver-routing-and-intent](../../research/physics/field-solver-routing-and-intent.md#what-worked).

### R4: spectral router prices

`kae.em.spectral`: each refresh reduces the current copper with the whole circuit inside; weights = derivatives of the evaluator's harms (waveform peak at every corner, through the robust objective), one complex weight per harmonic; hop price = one real combination of basis vectors' price fields.

Check geometry ([em_r4_check](../../../tools/research/physics/em_r4_check.py), 0.2 mm): aggressor loop with C_sw ringing at 130–170 MHz, victim hop replacing a field-free short; price / exact, 1–300 MHz:

| | Basis fields | One 10 MHz field, constant L |
|---|---|---|
| solid plane: coupling | 1.01–1.07 | 0.09–4.3, sign flips above the ring |
| solid plane: detour minus straight | 1.01–1.05 | 0.09–4.3 |
| slot under both: coupling | 0.99–1.01 | 0.24–5.9 |
| slot under both: detour minus straight | 0.97–1.00 | 0.24–5.8 |

- Below 0.3 MHz both fail (0.3–0.7 at 0.1 MHz): the hop's return does not run under it (R–L transition, §1); fixed by R4b.
- Price counts the hop's whole coupling, but the replaced short already returned through the plane (a third of it here, already in Z); path-independent, so routes don't move, but absolute "actual dL" doesn't match.
- Recycling: old basis carried onto new copper (by position + hop current) misses post-hop Z_vs by 13–46%; fresh snapshots at the old frequencies: 1e-6–1e-3.

Cost per refresh, boost, 0.25 mm, 8 threads ([em_r4_cost](../../../tools/research/physics/em_r4_cost.py)):

| Refresh | Time |
|---|---|
| 10 MHz solve of 9 patterns | 143 s |
| spectral, first (greedy build of 7 snapshots) | 1825 s |
| spectral, recycled, frequencies sequential | 878 s |
| spectral, recycled, 2 at once | 437 s |
| spectral, recycled, 4 at once | did not run: SuperLU + OpenMP out of address space under the 40 GB `ulimit -v` |

The greedy build's cost is mostly its error grid: 24 factorizations per step.

Boost `--verify` (each net routed twice from one state, candidates' difference compared per pair, [em_r4_trace](../../../tools/research/physics/em_r4_trace.py)): 8656 s for 7 nets vs 2635 s for the 10 MHz router.
- Hop carries the pair's pattern current (first order): switch node Net-(D3-A) overshoot +0.796 nH actual vs +0.797 predicted at 10 MHz (1.00); supply:IC1 0.96; whole-spectrum u 0.73 (overshoot), 1.15 (supply:IC1); FB net feedback victim 1.09.
- Hop carries none: prediction ~0, actual 0.001–0.03 nH (rails with capacitors become new return copper, second order; every pair's |dZ| peaks at 70–95 MHz, the resonance under the board's 95 MHz limit, which routing shifts). One spurious −0.71 nH on supply:U2 for a /VBAT route (+0.03 actual), which the search sought out.

Boost A/B, six priced nets re-routed with human placement; scores by `kae.excite.wideband` (robust) and `kae.excite.evaluate` (two bands):

| Router | Wideband robust | Two-band robust | DRC |
|---|---|---|---|
| plain | 4176 | 367 | 1 starved thermal, 1 unconnected (the human board's own) |
| physics, 10 MHz, `--verify` | 1316 | 221 | same |
| physics, whole spectrum, `--verify` | 806 | 170 | same |

One board, one run, inside the human layout; physics candidate won on 2 of 7 nets (/VBAT, +5V); part of the gain is `--verify` choosing by the evaluator's whole-spectrum harm.

### Cost of two-sided snapshots

(sources + observers) right-hand sides per frequency, about 6 frequencies: boost 60 solves vs 2 for the present evaluator. For the router (already solving every pattern per refresh) the factor = number of frequencies, cut by recycling, cheap low-frequency solves (DC 0 iterations, 2 kHz 6), and a coarse-grid preconditioner for the 80–100 iterations per high-frequency solve.
