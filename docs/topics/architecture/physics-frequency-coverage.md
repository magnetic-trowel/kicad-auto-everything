<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Covering the whole frequency range: one reduced model, not a list of bands

**TL;DR**
- **The board is one linear system across frequency.** Its copper and passive parts have
  matrices R, L (and, once added, P) that do not depend on frequency. The response at every
  frequency, and in time, lies in a small subspace spanned by solutions at a few frequencies.
- **Recommendation:** build a passive reduced-order model by projecting the full field system onto
  the solutions of every source *and* every observer pattern at a few adaptively chosen
  frequencies. Evaluate every harm on it at any frequency, at every harmonic, and as a waveform.
- **Bands are the special case without an error estimate.** A band list combines results by
  interpolation; the projection combines them by the physics (Galerkin), so resonances between
  samples come out right.
- **Measured on the boost board:** six snapshot frequencies (DC to 300 MHz, under 100 basis
  vectors) reproduce the nine observers at test frequencies that are not snapshots, 2 kHz to
  220 MHz. The worst relative error is 6e-5 to 9e-4 up to 25 MHz and 3.7e-3 at 110–220 MHz (§3).
- **What it cannot cover:** capacitive coupling until the electrostatic operator P joins the
  system, and electrically long nets (retardation). Those get §5's treatment.

## 1. What the range has to cover

| Range | Physics that sets it | Harm it decides | Now |
|---|---|---|---|
| DC | resistance | copper loss, rail drop, heating | DC band ([dc](../../../kae/src/kae/excite/dc.py)) |
| ~1 kHz – 1 MHz | R–L transition: return current moves from least resistance to least inductance | ground currents through analog and audio returns; regulator loop ripple | not covered |
| f_sw and harmonics, ~0.1–10 MHz | capacitor ESR/ESL and C split the current; PDN anti-resonance | input and output ripple, supply bounce | the fundamental, one point |
| 10–300 MHz | loop inductance, switch-node ring with C_sw, capacitor self-resonance | overshoot, ringing, CM emissions (CISPR 30–230 MHz), victim pickup | one 10 MHz solve, extrapolated as a constant L |
| any, dV/dt-driven | electric field (partial capacitance) | capacitive crosstalk into high-Z nodes, switch-node CM via capacitance | not modelled |
| above the quasi-static limit | retardation: θ = ωℓ/v ≳ 0.3 | transmission-line nets (DDR, USB), radiation above ~300 MHz | not modelled |

Two bands per aggressor ([kae.excite.evaluate](../../../kae/src/kae/excite/evaluate.py)) sample this
at two points. The peak formula then joins them with an assumed shape: |Z_f| c₁ I + |L_e| I/t_i.
That shape is wrong exactly where it matters:

- near a resonance (the ring, a PDN anti-resonance), where |H(f)| peaks by Q;
- in the R–L transition, where the return path itself changes;
- for capacitive coupling, which grows as f, not as a constant L.

## 2. The options

1. **Many bands, combined.** Solve each pattern at F log-spaced frequencies; interpolate |H(f)|;
   sum over the source spectrum.
   - Simple; each sample is exact.
   - Resonances with Q ≈ 10–50 need ~Q points per decade near the peak, or they are missed silently.
   - No error estimate between samples. Cost is S solves per frequency, F ≈ 15–30.
2. **Rational fitting of samples** (vector fitting). Needs the same many samples, and passivity
   has to be enforced afterwards. Nothing beyond option 1 except smooth interpolation.
3. **Time-domain field solve** with the real waveforms. Every frequency at once, but thousands of
   full solves per waveform. It is the job of sign-off, not of the inner loop.
4. **Projection-based model order reduction** (PRIMA, Odabasioglu et al. 1998; reduced-basis
   methods).
   - The PEEC saddle system [Z(s) −D; −Dᵀ 0] with Z(s) = R + sL + lumped(s) is projected by
     congruence onto V = span of snapshot solutions.
   - R and L are symmetric positive semidefinite, so the reduced model stays passive by
     construction: no fitting, no passivity repair.
   - The reduced system has order m ≈ 50–100. It is evaluated at thousands of frequencies, or
     time-stepped, at negligible cost.
   - Snapshots are chosen greedily where the estimated output error is largest.
5. **Moment matching at DC** (AWE/PRIMA at s₀ = 0). Each moment costs one exact DC solve plus one L
   apply: cheap. But its radius of convergence stops at the first pole. Useful as extra basis
   vectors, not alone.

**Option 4, with option 5's cheap DC moments as extra vectors**, is the elegant one. It also has
the lowest bug risk:

- One code path covers every frequency, and the pieces it reuses are already validated: the
  solver, the patterns and the observers.
- Every reduced output can carry its own error estimate.
- The same reduced model is the SPICE sign-off's parasitic network (§4).

## 3. Evidence: the boost board

Setup:
- Script: [`tools/research/physics/em_reduced_basis_check.py`](../../../tools/research/physics/em_reduced_basis_check.py).
- Copper with its 33 two-pad parts lumped in; the cell's edge-band injection held fixed over frequency.
- Galerkin projection of the full saddle system. The basis is the real span of [Re X, Im X].

One-sided basis (the source's solutions only):
- 3 frequencies: the driving point is right to 1e-4 at 3 MHz, 2e-4 at 30 MHz, 7e-3 at 150 MHz,
  but 2% at 30 kHz (no snapshot in the R–L transition).
- **Transfers are not.** With 7 frequencies the observers err by 5–30% of the largest observer.
  Only a quantity whose own solution is in the basis is variational.

Two-sided basis (source plus the nine observer patterns at each snapshot frequency):
- Greedy snapshots: DC, 10 MHz, 0.55 MHz, 1.7 MHz, 98 kHz, 300 MHz (the last chosen at 78 vectors).
- Under 100 vectors, 1134 s at 4 threads for the six snapshot solves of ten right-hand sides.

| Test frequency | Worst relative error over 9 observers | Worst error / largest observer |
|---|---|---|
| 2 kHz | 5.8e-4 | 8e-8 |
| 50 kHz | 8.7e-4 | 9e-6 |
| 0.7 MHz | 6.8e-5 | 9e-7 |
| 4.4 MHz | 9.2e-5 | 2e-6 |
| 25 MHz | 6.1e-4 | 2e-6 |
| 110 MHz | 3.1e-3 | 2e-5 |
| 220 MHz | 3.7e-3 | 1e-4 |

**The full-system residual is no error estimate here.** It stayed at 10¹–10⁵, scaled like the
iterative solver's, while the outputs were right to 1e-4. The residual is dominated by components
no observer sees. The estimator has to be output-based: the dual-weighted residual rᵀz with the
observer's reduced adjoint z. The two-sided basis carries z already.

## 4. The design

**The system becomes LTI with fixed inputs.**
- Two-pad parts are already lumped into the copper. IC pin models (package R, L to an internal
  die node, die C) join them as lumped elements on internal nodes.
- What stays outside are ideal sources: the switch's current, core currents, clocks. Each has a
  fixed spatial injection b_s and a spectrum from the ledger (trapezoid of I, D, t_i, f_sw).
- Observers are fixed functionals c_k. Then H_ks(s) = c_kᵀ x_s(s) for all s. This removes the
  current approximation of per-band patterns computed with ideal copper.

**Basis.**
1. The DC solution of every pattern, plus 2–4 DC moments each. These are cheap: the preconditioner
   is exact at f = 0.
2. Greedy snapshots of every pattern where the estimated error of the harm is largest. The error
   is weighted by each source's spectrum and each observer's limit curve. Frequencies are chosen
   because a harm depends on them, not from a fixed list.
3. Stop when the estimated harm error is below its tolerance (1e-3 of the bound).

**Harms from the reduced model.**
- Peak quantities (overshoot, supply bounce, victim pickup): synthesize the waveform from the
  harmonics, H_ks(jnω_sw)·c_n, n up to the edge knee, by one inverse FFT. Take its peak.
  - Ringing then emerges from the resonance instead of being estimated from L and C_sw.
  - The edge-share and |Z_f| c₁ terms disappear.
- Emissions: per harmonic against the CISPR line. Ripple at f_sw and its harmonics against the
  rail tolerance.
- Low-frequency ground currents: per audio or analog victim, over its own band.
- All of this is evaluated at the same corners of the ledger as now. A corner changes the source
  spectra and nothing in the reduced model, so the corners cost nothing extra.

**Router.**
- Price fields are linear in the currents, and the flux of every basis vector is L·V_I. The
  projection computes L·V_I anyway.
- So prices weighted over the whole spectrum, Π = Σ_f w(f) Π(f), are a combination of fixed fields
  with weights from the reduced model. Resonant pairs get their Q-amplified weight automatically.
- Between refreshes the basis was to be recycled: the old basis plus the new copper's local
  currents. Measured (R4 below), it is not accurate enough. What is recycled is the snapshot
  frequencies: a refresh re-solves them concurrently and adds one only where the calibrated
  error estimate says so.
- Built as [`kae.em.spectral`](../../../kae/src/kae/em/spectral.py), `kae.em.pnr --spectral`. Two
  points the design above missed:
  - A hop's current per pattern comes from the model's own part currents at each frequency. The
    ring and the copper's own current split are in it; the ideal-copper flow has neither.
  - The projection's potentials are multipliers of the projected KCL. They are right at the ports
    and at the snapshots, but off by up to 40× between them. Crossing prices recover potentials
    from the reduced currents through the branch equation D φ = (R + jωL) I instead.

**Sign-off.** The reduced model is a passive RLC-like state space. It exports as a SPICE
subcircuit with the switch and rectifier replaced by device models, which is step 6 of the build
plan.

## 5. What projection does not cover, and what does

- **Capacitive coupling and plane cavity modes need P**, the potential coefficients of layered
  electrostatics. They come on the same raster with FFT Toeplitz kernels, as L does.
  - With P the system is (L, P)-PEEC: still symmetric, still passive under congruence. The same
    reduction applies unchanged.
  - Reference for validation: FastCap, FastHenry's sibling.
- **Electrically long nets.** Quasi-static PEEC holds while θ = ωℓ/v ≲ 0.3: to ~300 MHz on a 5 cm
  board, ~100 MHz on 15 cm.
  - Nets whose knee frequency exceeds that are screened by θ and treated as quasi-TEM lines.
  - Their per-length L and C come from the same operators on the cross-section. They become
    routing constraints (impedance by layer, length match, spacing for crosstalk), not field prices.
  - Radiated emission above the limit is reported as not computed, never extrapolated.

## 6. Build stages and their gates

| Stage | What | Gate |
|---|---|---|
| R1 | IC pin models into the copper as lumped parts on internal nodes; fixed-source patterns | the two current bands' harms reproduced within 1% |
| R2 | Two-sided reduced basis, DC moments, greedy by the dual-weighted output estimate | reduced vs direct at 10 random frequencies, 1 kHz – 300 MHz, ≤ 1e-3 relative on every observer, on boost and a 4-layer board; the reduced model passive |

**R2 on boost: passed.** 7 snapshots (DC, 46 kHz, 0.24, 0.72, 10, 19, 300 MHz), order 111, 30 min at 4 threads. At 10 seeded random frequencies from 1.2 kHz to 132 MHz the worst relative error of any observer's layout share was 2.7e-4; the model's port matrix had no negative eigenvalue beyond rounding (−8e-14 against 3e4). The 4-layer case is still to run.

| R3 | Harms from the reduced model: waveform peaks, harmonics vs limit lines, low-frequency bands | boost ring frequency and overshoot against a direct transient of the full system at one corner |
| R4 | Router prices weighted over the spectrum; basis recycling between refreshes | predicted vs actual dL per pair within the current 0.93–1.06 band |

**R4: built. The gate holds on the check geometry, and on boost where a hop carries the pair's current.**

What `kae.em.spectral` does:
- Every refresh reduces the copper as it stands, with the whole circuit inside it.
- The weights are the derivatives of the evaluator's own harms: the waveform peak at every corner,
  through the robust objective. That makes one complex weight per harmonic.
- A hop's price is one real combination of the basis vectors' price fields.

Check geometry ([em_r4_check](../../../tools/research/physics/em_r4_check.py), 0.2 mm): an aggressor
loop with C_sw that rings at 130–170 MHz, and a victim hop replacing a field-free short. The table
gives price / exact, from 1 to 300 MHz:

| | basis fields | one 10 MHz field, constant L |
|---|---|---|
| solid plane: coupling | 1.01–1.07 | 0.09–4.3, sign flips above the ring |
| solid plane: detour minus straight | 1.01–1.05 | 0.09–4.3 |
| slot under both: coupling | 0.99–1.01 | 0.24–5.9 |
| slot under both: detour minus straight | 0.97–1.00 | 0.24–5.8 |

Below 0.3 MHz both fail (0.3–0.7 at 0.1 MHz). There the hop's return does not run under it, which
is the R–L transition (§1).

The price counts the hop's whole coupling. The field-free short it replaces already returned through
the plane, and that coupling was in Z before the hop (a third of it here). It is the same for every
path, so it does not move a route, but it does keep an absolute "actual dL" from matching.

Recycling:
- The old basis carried onto the new copper (by position, plus the hop's own current) misses the
  post-hop Z_vs by 13–46%.
- Fresh snapshots at the old frequencies hold it to 1e-6–1e-3. So the frequencies are what gets
  recycled, not the vectors.

Cost per refresh on boost, 0.25 mm, 8 threads
([em_r4_cost](../../../tools/research/physics/em_r4_cost.py)):

| Refresh | Time |
|---|---|
| 10 MHz solve of 9 patterns | 143 s |
| spectral, first (greedy build of 7 snapshots) | 1825 s |
| spectral, recycled, frequencies one after another | 878 s |
| spectral, recycled, 2 at once | 437 s |
| spectral, recycled, 4 at once | did not run: SuperLU and OpenMP ran out of address space under the 40 GB `ulimit -v` |

The greedy build's cost is mostly its error grid: 24 factorizations per step.

Boost, `--verify`: each net is routed twice from one state, and the two candidates' difference is
compared per pair ([em_r4_trace](../../../tools/research/physics/em_r4_trace.py)). The route took 8656 s
for 7 nets, against 2635 s for the 10 MHz router.

Where the hop carries the pair's pattern current, the change is first order and the prices hold:
- On the switch node, Net-(D3-A), the cell's overshoot changed by +0.796 nH at 10 MHz. The
  prediction was +0.797 (1.00); for supply:IC1 it was 0.96.
- On the whole-spectrum harm u, the ratios are 0.73 (overshoot) and 1.15 (supply:IC1).
- On the FB net, the feedback victim's ratio is 1.09.

Where the hop carries none of it, the prediction is ~0, and the actual changes are 0.001–0.03 nH:
- Rails with capacitors become new return copper, which is second order in the coupling.
- Every pair's |dZ| peaks at 70–95 MHz, at the resonance under the board's 95 MHz limit, which
  routing shifts.
- One prediction was spurious: −0.71 nH on supply:U2 for a /VBAT route, against +0.03 actual. The
  search sought it out.

Boost A/B: the six priced nets re-routed with the human placement. Scores are from
`kae.excite.wideband` (robust objective) and `kae.excite.evaluate` (two bands):

| Router | wideband robust | two-band robust | DRC |
|---|---|---|---|
| plain | 4176 | 367 | 1 starved thermal, 1 unconnected (the human board's own) |
| physics, 10 MHz, `--verify` | 1316 | 221 | the same |
| physics, whole spectrum, `--verify` | 806 | 170 | the same |

One board and one run. The physics candidate won on 2 of the 7 nets, /VBAT and +5V. Part of the gain
is that `--verify` now chooses by the evaluator's own whole-spectrum harm.

| R5 | P operator (EQS) and capacitive prices | microstrip C per length vs closed form; two-trace mutual C vs FastCap |

**R5 capacitive prices: built** ([physics-driven-build](physics-driven-build.md) §3b).
- A hop's predicted change of mutual capacitance holds within 0.91–0.99 of a fresh static solve beside an aggressor strip.
- On the boost feedback net's hops it holds within 1.02 in sum.
- In a smoke route of boost it kept the switch node out of the plane under the feedback divider: C_m 6.3 fF against 57.5 fF without it, and 17.9 fF for the human layout.
- The FastCap comparison is still to run.

| R6 | θ screen and quasi-TEM constraints for long nets | Z₀ vs closed form per layer of the stackup |
| R7 | SPICE export of the reduced model; nonlinear sign-off | waveform vs the reduced model's own linear transient at small signal |

**Cost.** Two-sided snapshots solve (sources + observers) right-hand sides per frequency, about 6
frequencies. On boost that is 60 solves, against 2 for the present evaluator. The router already
solves every pattern at each refresh, so for it the factor is the number of frequencies. That
factor shrinks with:
- recycling between refreshes;
- the cheap low-frequency solves (DC needs no iterations, 2 kHz 6);
- the coarse-grid preconditioner that would cut the 80–100 iterations at high frequency for every
  solve.
