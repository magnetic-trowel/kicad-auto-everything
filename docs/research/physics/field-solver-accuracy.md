<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Field-solver accuracy: skin effect vs nsub, mesh bias, hot copper (2026-11-03)

**Status:** partial. Three audit items were decided and built. Everything here is model against model (closed forms, finer solves, the evaluator on corpus boards); nothing was measured on physical hardware.
**First published:** 2026-11-03 on branch `decide-em` (off `audit-fixes-2611`).

The 2026-11 audit raised three accuracy questions about `kae.em` and the two evaluators (`kae.excite.evaluate`, the fast one, and `kae.excite.wideband`):
- **E5.** How much skin effect do two filaments through the copper miss?
- **E7.** How large is the raster's inductance bias, and when does it matter?
- **E4.** What does copper's temperature coefficient do to heat and drop?

A fourth problem turned up while answering E5: a bug in narrow bars.

Scripts:
- [em_skin_nsub_check.py](../../../tools/research/physics/em_skin_nsub_check.py): the 1-D slab, the canonical solves (decap loop, buck hot loop, plane pair, coplanar pair) at nsub 1–8 and 1–200 MHz, and `--pitch` refinement.
- Code: [kae.em.skin](../../../kae/src/kae/em/skin.py), `Reduced.skin_correction` in [reduce](../../../kae/src/kae/em/reduce.py), `mesh_report` and `bias_hazards` in [evaluate](../../../kae/src/kae/excite/evaluate.py), `tcr_solve` in [heat](../../../kae/src/kae/excite/heat.py).

## 1. Narrow bars lost part of their inductance correction at nsub ≥ 2 (fixed)

**The bug.** A bar narrower than its cell (a partly covered edge cell, or a sub-cell track) gets a self-inductance correction: the self L at its true width minus that of the p-wide bar the FFT operator holds. With `nsub` filaments, the correction was applied only to each filament's self term, at the filament's own thickness. A uniform current through the stack therefore saw about 1/nsub of it.

**Evidence.** A 0.3 mm trace over a plane at 0.25 mm pitch (the cells are partly covered) at 1 kHz:

| nsub | Before | After |
|---|---|---|
| 1 | 2.879 nH | 2.879 nH |
| 2 | 2.788 nH (−3.2%) | 2.879 nH |
| 8 | 2.712 nH (−5.8%) | 2.879 nH |

A 0.5 mm trace (full cells) was nsub-independent before the fix too.

**The fix.** The full-thickness correction now couples every pair of filaments in the stack (`Network.Lc_off`). The router's nsub = 1 path is unchanged. At the default nsub = 2, every narrow copper's loop inductance rises by about half its narrow-bar correction. Physics results computed before commit `83e2bd7` are therefore not comparable with later ones.

**On a real board.** The fast evaluator was run on metro-m7 (Adafruit Metro M7) at nsub = 2, before and after the fix, and compared with nsub = 4 after it.
- Before the fix, two crystal-pickup harms (IC2.37 and IC2.38 from their clock) read u = 0.835, a pass. With the fix, and at nsub = 3 and 4, they read 1.064, a fail. **The bug produced a false pass.**
- After the fix, nsub = 2 has no pass/fail change against nsub = 4. Of the field harms above their bound, all are within −2.5% to +4.2%.

## 2. Skin effect vs nsub (E5)

**The slab.** Take 35 µm copper with its field on one side, as a conductor facing its return across a dielectric has. Its exact ratio is R/R_dc = Re[(1+j)D coth((1+j)D)], with D = t/δ. This is Dowell's single-layer factor; δ is 66 µm at 1 MHz and 6.6 µm at 100 MHz. The same slab cut into n uniform-current filaments (kae.em's Chebyshev slices) reaches only F_n:

| f | δ | exact | n = 2 | 3 | 4 | 8 |
|---|---|---|---|---|---|---|
| 10 MHz | 20.9 µm | 1.54 | 1.40 | 1.48 | 1.50 | 1.53 |
| 30 MHz | 12.1 µm | 2.91 | 2.49 | 2.92 | 2.90 | 2.90 |
| 100 MHz | 6.6 µm | 5.30 | 3.15 | 4.72 | 5.39 | 5.28 |
| 200 MHz | 4.7 µm | 7.49 | 3.22 | 5.40 | 7.33 | 7.47 |

- With nsub = 2 there is no grading: the two slices are equal halves. Where the field is two-sided (the coplanar pair), symmetry gives both halves the same current, so nsub = 2 is no better than nsub = 1.
- Opposed eddy currents let two filaments exceed 2× R_dc, contrary to the audit's "at most 2×". They still fall to 0.60× of the exact ratio at 100 MHz and 0.43× at 200 MHz.
- FastHenry's rule of thumb is a smallest filament of about one skin depth (see Sources). The nsub = 4 outer slices are 5.1 µm thick.

**Solver, nsub 1–8 against nsub = 8** (after the fix of §1; worst over each case's variants):

| Case | nsub 2: R at 10 / 100 / 200 MHz | nsub 2: \|ΔL\| | nsub 4: R at 100 / 200 MHz | Rank flips (R at 100 MHz, L at 10 MHz) |
|---|---|---|---|---|
| decap loop (6 variants) | 0.96 / 0.58 / 0.42 | ≤ 2.5% | 1.00 / 1.01 | none |
| buck hot loop (6 variants) | 0.95 / 0.56 / 0.40 | ≤ 2.4% | 1.00 / 0.99 | none |
| plane pair (4 variants) | 0.93 / 0.55 / 0.39 | ≤ 5.1% | 1.02 / 0.98 | none |
| coplanar pair, no plane (4) | 0.97 / 0.42 / 0.30 | ≤ 0.8% | 0.98 / 1.01 | none |

- **nsub = 4 is converged** to about 1% in R and 0.2% in L, up to 200 MHz.
- **Cost of a solve** relative to nsub = 2: about 1.7× at nsub 3, 2.4× at nsub 4 and 7× at nsub 8. The iteration counts do not change; the sublayer-pair products grow.
- **Independent check.** The plane pair's copper-only Q at nsub = 8 and 100 MHz is 17.2, 16.9, 33.6 and 33.0. Lens TH's closed form h/δ + 1 gives 16.1 and 31.3 ([lens-th](../../topics/physics/lens-th.md) D1), within 7%. At nsub = 2 the same Q is about 2× too high.

**Rings.** Each hot loop is closed by C_oss = 1 or 4 nF, plus the cell stand-in's 0.05 Ω, which rings at 57–175 MHz.
- At nsub = 2, Q reads 5–25% high, so the ring-band peak (∝ Q) is +0.4 to +1.9 dB. The copper-only Q is 1.5–2.3× high.
- 1 of 15 Q orderings flips at nsub = 2; none flip at nsub ≥ 3.
- The model's damping is part copper and part the stand-in's 0.05 Ω. Measured buck converters damp mainly through the low-side FET (Kam et al. 2011), so on a real board copper's share, and with it this error, is likely smaller.

**What the evaluators use.**
- **Fast evaluator and router: keep nsub = 2, no correction.**
  - The fast evaluator solves each aggressor at two bands: the edge, capped at 10 MHz (`observe.gentle_f`), and the switching fundamental. That fundamental is a cell's f_sw (≤ 3 MHz), but a clock's frequency (25–100 MHz on the thermal problem boards).
  - Its harms use the edge band's inductance and the fundamental's |Z_f| ≈ ωL. At nsub = 2, L is within 0.2% at 10 MHz and within 1.6% (plane pair 3.6%, reading high) at 100 MHz, with no rank flips.
  - Its only resistive output, `loss.loop_ac` (Re Z_f at a cell's f_sw), is within 1–2%.
  - On metro-m7 (205 field harms), nsub = 2 is within −2.5% to +4.2% of nsub = 4 for every harm above its bound, with no pass/fail change. One harm reads 33% low (cable common mode, u = 0.20 against 0.29), but it is tiny: its inductance is a few pH.
  - A whole evaluation costs 1.35–1.6× at nsub = 3 and 1.7–2.4× at nsub = 4 (Ubertooth 44 → 59 → 73 s, metro-m7 106 → 168 → 250 s).
  - So raising nsub would change no decision on the evidence so far.
- **Wideband evaluator: nsub = 2 plus a surface-impedance correction**, on by default (`--no-skin-correction` turns it off).
  - Each layer's reduced resistance block is scaled by k = F/F_2 at every harmonic.
  - The basis is built without it, so the model's error estimate still compares like with like.
  - Accuracy against nsub = 8, 1–200 MHz: decap 0.97–1.07, hot loop 0.92–1.07, plane pair 0.92–1.03, coplanar pair (two-sided) 0.70–1.09.
  - **Validity:** one-sided crowding, which covers traces and pours over planes and plane pairs. Where the field is two-sided (go and return side by side with no plane, striplines), the correction under-corrects: R stays low and Q stays high. That is the conservative direction for the ring and emission harms.
  - It costs nothing measurable. An evaluation of the reduced model is a few m × m adds per harmonic.
- **Not yet measured on a board.** The smallest corpus board with a converter cell and a wideband model (moto:bit, 2 sources, 35 observers) still had not converged its reduced model after 45 minutes and 21 GB per run, so the arms (correction on, off, and nsub = 4 as the reference) were stopped. That run is a follow-up for a heavier job slot.

## 3. Mesh bias at 0.25 mm (E7)

**Refinement of the canonical loops at nsub = 2.** Loop L at 10 MHz is compared with the finest solve (0.0625 mm); in brackets, against the extrapolation from 0.125 and 0.0625 mm where the convergence is monotone:

| Case | 0.5 | 0.25 | 0.125 | 0.0625 mm | 0.25 mm vs finest |
|---|---|---|---|---|---|
| hot loop h 0.1, w 1.5 | 1.021 | 0.866 | 0.850 | 0.811 nH | +6.7% (+12% vs extrapolated) |
| hot loop h 0.4, w 0.6 | 2.458 | 1.936 | 1.911 | 1.848 | +4.8% (+8.5%) |
| decap lt 6, h 0.2 | 2.037 | 2.292 | 2.730 | 2.367 | −3.2% |
| decap lt 1, h 0.1 | 0.559 | 0.583 | 0.606 | 0.578 | +0.8% |
| plane pair h 0.1, d 6 | — | 0.156 | 0.147 | 0.141 | +11.0% (+16%) |
| plane pair h 0.2, d 14 | — | 0.395 | 0.381 | 0.371 | +6.4% (+9.7%) |

- **Hot loops and plane pairs converge from above, at first order.** The boost hot loop's +15% ([physics-driven-build](../../topics/architecture/physics-driven-build.md) §2) is of this kind.
- **Small decap loops do not converge monotonically.** Their pads, via landings and 0.3 mm trace snap to the cells differently at each pitch: R_dc moves by ±10% (2.74, 2.89, 2.46 mΩ), and L can read low (−3%) as well as high.
- **Richardson extrapolation is therefore not safe in production.** Against the 0.0625 mm solve, extrapolating from (0.5, 0.25) mm errs by −23% to +8% (worse than the plain 0.25 mm value, −3% to +11%). From (0.25, 0.125) mm it is within 6% on hot loops and plane pairs but up to +37% on the decap loops. A second solve at half the pitch costs about 4× the cells.
- **Decision: keep the 0.25 mm pitch and document the bias; no correction.** The evaluators now report it:
  - `mesh` in their output: pitch, nsub, `Mesh.check` warnings per layer, the priced nets with ≥ 25% of their copper under 3 cells, and the bias statement;
  - notes;
  - hazard `field_harm_within_mesh_error`. A field harm (overshoot, supply, victim, cm, radiated) that passes by less than 5%, scaled with the pitch, is **warn**: it may fail on a finer mesh. One that fails by less than 16% is **info**: it may pass.
- `Mesh.check` used to open all nets' copper together, so a thin track beside another net's pour passed. It now opens each net separately (`Mesh.thin_cells`).

## 4. Copper's temperature coefficient (E4)

**Mechanism.**
- The heat band's copper I²R was evaluated at 20 °C. It is now scaled per cell by 1 + α(T_amb + ΔT − 20 °C), with α = 0.00393/K (IEC 60028).
- The board's own conduction network is iterated to the fixed point (Picard, at the thermal factorization's cost per step). Its increments shrink by the loop gain g, the spectral radius of α Θ diag(Q_cu).
- With g ≥ 1 there is no steady state: the block hazard `thermal_runaway_copper`. Its single-conductor limit is thermal-physics.md's ΔT = ΔT₀/(1 − αΔT₀), which the tests reproduce to 1e-3.
- The DC band's copper loss and rail drops take the heat band's factor at the same corner. For a drop, that is the larger of its rail's and the grounds' factor. The heat band runs at sustained currents, the DC band at peaks, and copper temperature follows the sustained heat.
- **Left out:** the DC current's shift toward cooler parallel copper (stabilizing, second order) and parts' own temperature coefficients.

**Effect on the 14 thermal problem boards.** Human layouts, intents compiled at 6329e71; base bd67f8e against TCR 505fd9d, fast evaluator.

| Measure | Range over the 14 boards |
|---|---|
| Hard temperature violations | 2 → 2 (FONA's SIM800 at 129 °C, CM5 module at 116 °C) |
| Junction temperatures | +0.00 to +0.06 K, except one resistor on hdmi2rgb at +1.96 K |
| Loop gain g | ≤ 0.002: runaway is far off on real boards |
| Copper loss at the typical corner | +0.3% to +14% (FONA +14%, Ubertooth +11%, CM5 +8%) |
| Worst rail drop | +1% to +26% (FONA 18.3 → 23.0 mV, cm4-carrier 229 → 249 mV) |
| Heat band time, 0.01 K stop | 1.1–2.2× |

- **Temperatures barely move.** The copper's own heat is small next to the parts' on these boards.
- **Drop and loss move more**, because the whole board sits at T_amb plus its rise instead of at 20 °C.
- **Cold-ambient fix.** Two boards whose intents state a 0–40 °C ambient showed a lower worst drop (melexinvn 64.0 → 60.5 mV): a cold corner had been paired with a peak current. The factor on DC values is now never below 1 (commit 1c08265).
- **Speed fix.** The stop is now 0.1 K, so one step usually suffices; powerboost's heat band went from 1.5 s to 2.5 s.

## Sources

- FastHenry User Guide (Kamon, Smith, White), §2.4. Smallest filament about one skin depth; geometric grading toward the surface (rh = 2 by default). <https://www.fastfieldsolvers.com/Download/FastHenry_User_Guide.pdf>
- Altair Flux PEEC meshing help. Element size comparable to the skin depth. <https://help.altair.com/flux/Flux/Help/english/UserGuide/English/topics/ModeConducteurTubeMaillage.htm>
- Coperich, Ruehli, Cangellaris, "Enhanced skin effect for PEEC models", IEEE T-MTT 2000. Volume filaments get costly at high frequency; surface-impedance PEEC is the alternative used here. <https://experts.illinois.edu/en/publications/enhanced-skin-effect-for-partial-element-equivalent-circuit-peec->
- Dowell's single-layer (m = 1) factor D(sinh 2D + sin 2D)/(cosh 2D − cos 2D). It is the slab formula of §2, checked to 1e-9 in `test_em_skin.py`. <https://journals.pan.pl//Content/86445/PDF/31-paper.pdf>
- Wheeler's incremental-inductance rule. Skin resistance equals ωL_int (Q = h/δ for plates). <https://en.wikipedia.org/wiki/Wheeler_incremental_inductance_rule>
- Kam et al., "Quantification of self-damping of power MOSFET in a synchronous buck converter", IEEE T-EMC 2011. The low-side FET dominates the ring's decay. <https://scholarsmine.mst.edu/ele_comeng_facwork/2578>
- IS 8130:1984 (after IEC 60028). ρ20 = 1/58 Ω·mm²/m and α20 = 0.00393/K for annealed copper. <https://infralens.in/code/IS-8130-1984>
- Feldman, Richardson extrapolation notes. (2^k A(h/2) − A(h))/(2^k − 1); it assumes the asymptotic order, which the decap loops violate. <https://personal.math.ubc.ca/~feldman/m121/richard.pdf>
- Antonini and Orlandi 2006. Geometric meshing is a main PEEC error source; projection meshing beats Manhattan meshing at equal unknowns. <https://ricerca.univaq.it/handle/11697/10907>
- In-repo: [lens-th](../../topics/physics/lens-th.md) D1 (Q = h/δ), [thermal-physics](../../topics/physics/thermal-physics.md) "TCR feedback", [physics-driven-build](../../topics/architecture/physics-driven-build.md) §2, and [redteam-corrections](redteam-corrections.md) (convergence studies required).
