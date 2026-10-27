# Physics-first ideas: SI, EMI and RF (FE1–FE56)

Each idea gives its mechanism, the physics behind it, why it beats the rule of thumb, and how to test it.
- **Tags:** **new** (not in the corpus), **combo** (a novel combination), **sharp** (an existing idea made buildable).
- **Effort:** S / M / L.

Evidence and numbers are in:
- [fields-si-emi](../../topics/physics/fields-si-emi.md): return path, crosstalk, cavities, pairs;
- [fields-emi-budget](../../topics/physics/fields-emi-budget.md): the EMI chain;
- [rf-geometry](../../topics/physics/rf-geometry.md): geometry thresholds and RF.

Scripts are `tools/research/physics/fe_*.py`. Everything here is [I] until tested.

**Try first:**
1. FE1 return-path EMF ledger;
2. FE3 transfer-inductance maps;
3. FE11 EMI margin as a placement loss;
4. FE26 cavity eigenvalue critic;
5. FE40 pad-void synthesis.

Each is small, rests on a model we already validated, and replaces several rules at once.

## A. The return path as one metric

**FE1 Return-path EMF ledger** (new, M).
- **Mechanism:** For each fast net, list every discontinuity on its path with a closed-form ΔZ_k(f):
  - slot: ΔL ≈ μ0·l/(2·ln(4l/g));
  - via pair: the Hankel radial term;
  - edge enhancement;
  - decap path plus cavity.
  
  Multiply by the net's current spectrum and post two projections as [I1](../original/intent-and-why.md) ledger rows: SI (mV at the receiver) and EMI (mV between cable points).
- **Why it beats the rules:** about a dozen plane rules become one number per net, with top spenders.
- **Test:** Use [pc_refplane](../../topics/physics/physics-critics.md)-style planted faults on 20 boards. Measure the rank correlation of ledger spend against PEEC/openEMS plane voltage, and confirm zero firings on benign twins.

**FE2 Slot price, not slot ban** (sharp, S).
- **Mechanism:** The router charges ω_knee·ΔL_slot·I for each void crossing, using ΔL ≈ μ0·l/(2 ln(4l/g)) (2.5 nH for 20 × 0.5 mm; not linear in l), instead of forbidding all crossings.
- **Why it beats the rules:** A 2 mm antipad gap is cheap; a 20 mm slot costs as much as 8 mm of extra trace inductance.
- **Test:** In the [R2](../original/routing.md) shadow-net router, compare price against forbid on 20 boards: completion and ledger spend.

**FE3 Transfer-inductance maps κ_ab(x, y, θ)** (new, M).
- **Mechanism:** For each pair of cable connectors, run one PEEC solve with current injected at a and extracted at b. By reciprocity, the plane-current density of that solve gives the a–b voltage produced by a unit return EMF at any position and direction.
- **Why it beats the rules:** One solve per connector pair, then O(1) EMI lookups for the placer and router. It replaces "nothing fast between connectors" with a field.
- **Test:** Map-based V_ab against full PEEC for 50 random trace placements; target ±3 dB.

**FE4 Antipad web synthesis** (new, S).
- **Mechanism:** Detect antipad clusters that merge into slots under fast nets. Then shrink, stagger or split them to leave copper webs at least ~h wide.
- **Physics:** Separate holes add < 0.3·h nH each; a merged cluster is a slot (Ott's 15-hole experiment).
- **Test:** BGA breakouts on open boards: ΔL before and after, DRC clean, no loss of routability.

**FE5 Return via sized by cavity launch** (sharp, S).
- **Mechanism:** Put the return via at s ≤ 0.63/k(f_N) ≈ λ_d/10, where the via pair launches 10 dB less power into the plane pair than an unpaired via (1 − J0(ks)). Use two symmetric vias when the budget is tighter.
- **Why it beats the rules:** It reproduces TI's 200 mil and 50 mil, and extends them to any stackup and rate.
- **Test:** openEMS via transitions at three data rates against the Hankel closed form.

**FE6 Smooth edge cost** (sharp, S).
- **Mechanism:** Replace the 2h / 3h / 90 mil edge rules with two terms:
  - an EMI term: the MREMC/PEEC edge enhancement (~1/√d) in dB of V_cm per connector pair;
  - an SI term that is zero beyond ~3h.
- **Why it beats the rules:** Edges with no cable nearby are not penalised, and the steep part of the curve is priced correctly.
- **Test:** Decisions on 20 boards against the slogan rules, scored by PEEC V_ab.

**FE7 Stitching-cap optimizer** (new, S).
- **Mechanism:** When a split crossing is forced, choose the cap value (put its SRF at the dominant harmonic), the count and the position along the slot to minimise |Z_slot ∥ Z_cap| over the net's spectrum.
- **Physics:** One cap buys 8–11 dB and two buy 15 dB in our case. "≤ 1 µF" is not the operative parameter.
- **Test:** fe_emi_budget sweep against openEMS on one slotted board.

**FE8 Priced reference changes** (sharp, S).
- **Mechanism:** Every via of a fast net gets a transition type (Ott 1–4) and a ΔZ price: via pair, or decap path plus cavity. The router then weighs a layer change against the detour it saves.
- **Test:** Count of P↔G changes and ledger spend against a Freerouting baseline.

**FE9 Return-current picture for the LLM** (new, S).
- **Mechanism:** Render the PEEC plane current under each critical net as a heat map, with detours outlined and labelled in nH. The LLM then argues from the physics picture instead of reciting rules.
- **Test:** LLM fix quality on 20 planted faults, with and without the map.

**FE10 Current-aware plane partitioning** (combo with [R7](../original/routing.md), M).
- **Mechanism:** Score power-plane splits by Σ ΔL_n·I_n over fast nets, and draw boundaries where the PEEC return-current density of all fast nets is below a threshold.
- **Test:** The R7 benchmark with this objective added.

## B. EMI budget, cables and connectors

**FE11 EMI margin as a placement loss** (combo, M).
- **Mechanism:** The [fe_emi_budget](../../topics/physics/fields-emi-budget.md) chain plus FE3 maps gives a margin per (net, harmonic, connector pair). The placement loss is softplus(E − limit + guard).
- **Why it beats the rules:** It subsumes "cabled connectors on one edge" (6–48 dB by orientation, counting the board-vs-cable mode) and "no fast circuitry between connectors".
- **Test:** A [P8](../original/placement.md) A/B on 10 boards with two or more cabled connectors, scored by PEEC/MREMC margin.

**FE12 Fix ranking by sensitivity** (new, S).
- **Mechanism:** Compute ∂margin/∂parameter for each fix: cable side, slot, edge distance, caps, t_r, series R. Offer the cheapest fix with its dB gain.
- **Physics:** In one worked case the gains were 6–48 (by orientation) / 24 / 15 / 10 / 3 / 2.5 dB. Topology beat tweaks there; the ranking is case-specific, so compute it.
- **Test:** Agreement with EMC engineers' fix rankings on 10 cases.

**FE13 Clock plan against resonances** (new, S).
- **Mechanism:** Put every clock and switching harmonic line on the same axis as cable half-wave resonances, board dipole modes, plane cavity modes and slot resonances. Propose frequency, spread or layout changes that keep strong lines off peaks.
- **Test:** Synthetic sweeps; the emission estimate as lines move.

**FE14 Chassis-bond planner** (new, M).
- **Mechanism:** Choose k bond points (screws or caps) that minimise the maximum V_ab over connector pairs, with bonds modelled as shorts in PEEC.
- **Physics:** A bond shorts the antenna feed where the voltage is generated.
- **Test:** Against "bond at every connector" in PEEC and on one enclosure.

**FE15 Spectrum-defined net classes** (sharp, S).
- **Mechanism:** Derive each net's I(f) envelope from IBIS or the part family. Nets with negligible energy from 30 MHz to 1 GHz drop out of EMI checks; the rest are ranked by in-band energy.
- **Why it beats the rules:** It replaces "fast net" name regexes.
- **Test:** Precision and recall against expert labels.

**FE16 Skew as a common-mode budget for cables** (sharp, S).
- **Mechanism:** For pairs that leave the board on a cable, allocate skew from the common-mode budget through sin(πfΔt)/2, shared with the CMC and magnetics rejection.
- **Physics:** 50 ps of skew leaves ~30 dB for the magnetics to cover.
- **Test:** Allocations against vendor skew rules on Ethernet and USB boards.

**FE17 Voltage-driven source critic** (combo, M).
- **Mechanism:**
  - Estimate the free-space capacitance of heatsinks, tall magnetics, switch-node copper and long edge traces with a quick BEM, and take V_cm ≈ V·C_part/C_board.
  - Flag heatsinks over fast dies near λ/4, and suggest grounding points.
- **Test:** openEMS on three heatsink cases.

**FE18 I/O-coupling budget** (sharp, S).
- **Mechanism:** Crosstalk onto nets that leave on cables is budgeted against the cable antenna, at about 100 µV, not against receiver noise margin.
- **Test:** Flagged pairs against HyperLynx-style I/O-coupling rules.

**FE19 Bring-up probe plan** (combo, S).
- **Mechanism:** From the ledger, emit near-field probe points and expected spectra for the first scan, so the measurement calibrates κ and the MREMC offset (see FE56).
- **Test:** One real board.

## C. Crosstalk

**FE20 Per-layer crosstalk kernels** (sharp, S).
- **Mechanism:** Field-solve K_L and K_C against D/h for each layer once per stackup with [fe_field2d.py](../../../tools/research/physics/fe_field2d.py).
- **Physics:** Microstrip is algebraic, with FEXT growing with coupled length. Stripline is exponential (about −11 dB per extra h) with zero FEXT.
- **Test:** Against a commercial 2-D BEM on three stackups.

**FE21 Per-victim noise budget in mV** (sharp, S).
- **Mechanism:** Each victim gets a budget: its noise margin share, an LSB-based limit for ADC inputs, or 100 µV for I/O. Aggressors share it, and spacing becomes a solved output.
- **Physics:** 3W gives 1.3% NEXT in microstrip and 0.02% in stripline, so one slogan cannot serve both.
- **Test:** Area saved against 3W at equal simulated noise on 10 boards.

**FE22 Timing-window crosstalk** (new, M).
- **Mechanism:** Aggressor edges that never coincide with a victim's sampling window do not count; STA windows mask the coupling matrix.
- **Test:** DDR byte lanes: the spacing reduction at equal eye.

**FE23 FEXT-driven layer choice** (new, S).
- **Mechanism:** When coupled length × (K_L − K_C)/2 / t_r exceeds the budget, move the bus to stripline, where FEXT vanishes, instead of spreading it.
- **Test:** Long parallel buses on 4- and 6-layer boards.

**FE24 Broadside coupling map** (sharp, S).
- **Mechanism:** Replace "route adjacent layers at 90°" with overlap-weighted broadside coupling from the 2-D solve, so parallel runs are allowed where vertical separation is large.
- **Test:** Dual-stripline 6-layer boards.

**FE25 Guard-trace gate** (sharp, S).
- **Mechanism:** Allow a guard trace only when the 2-D solve shows spacing alone cannot meet the budget in the available channel, and only as an end-shorted stripline guard.
- **Test:** Guard proposals against expert review.

## D. Cavities, stitching, fences, shields

**FE26 Cavity eigenvalue critic** (new, S).
- **Mechanism:** Compute the first resonance of each plane pair with stitching vias as shorted ports ([fe_cavity.py](../../../tools/research/physics/fe_cavity.py), seconds). Compare it with the highest frequency at which reference-changing vias still inject energy.
- **Why it beats the rules:** The largest-empty-circle proxy is right only ±30% and biased by pattern.
- **Test:** First-mode error against openEMS on five boards.

**FE27 Lattice stitching synthesis** (new, S).
- **Mechanism:** Generate stitching as a square or hex lattice with pitch from the Belov cut-off f_p > f_target, or as blue noise around obstacles.
- **Physics:** At 48 vias, a grid's first mode is 7.45 GHz against 3.35–5.0 GHz for random placement.
- **Test:** First mode per via budget: grid, Poisson and the designer's layout.

**FE28 Eigenvalue-gradient via placement** (new, M).
- **Mechanism:** Add vias greedily where the first mode's |E_z|² is largest. That is where a short raises the eigenvalue most (first-order perturbation).
- **Test:** First mode against via count, compared with FE27.

**FE29 Source-weighted stitching** (new, M).
- **Mechanism:** Weight each cavity mode by how strongly the board's reference-changing vias and IC ground pins excite it (modal overlap), and suppress only excited modes.
- **Test:** Transfer impedance between aggressor and victim vias at equal via count.

**FE30 Fence from an isolation target** (sharp, S).
- **Mechanism:**
  - Pitch from |T| = 2/√(4 + B²).
  - Row count from the dB target.
  - Channel width from the TE10 cut-off.
  - Then verify with the cavity model, because in finite boards the realised isolation differed from the closed form by −24 to +19 dB.
- **Test:** openEMS on RF compartments.

**FE31 Lossy edge termination for PWR–GND cavities** (combo, M).
- **Mechanism:** Lower cavity Q with R–C edge terminations or a lossy edge band instead of adding decaps, priced by the reduction in peak |Z|.
- **Test:** Cavity model with resistive edge ports, then one fabricated board.

**FE32 Shield-can resonance check** (sharp, S).
- **Mechanism:** A can is a cavity, with TE110 at 6.25 GHz for 40 × 30 mm. Check its modes against the radio's bands and propose absorber or a partition wall.
- **Test:** Against vendor can designs.

**FE33 Perimeter-vs-distributed resolver** (combo, S).
- **Mechanism:** Compute both outputs: interior first mode (Hubing's concern) and edge-fringe voltage (Ott's). Then split the via budget between perimeter and interior to meet both.
- **Why it beats the rules:** The contested rule becomes two terms of one objective.
- **Test:** fe_cavity plus openEMS edge radiation.

## E. Differential pairs

**FE34 Coupling chosen by loss and density** (sharp, S).
- **Mechanism:** Choose the gap from Zdiff, loss budget and channel width. Loose coupling gives ~30% less conductor loss at 100 Ω. EMI enters only if k·s > ε (s* ≈ 0.5 mm at 1 GHz).
- **Test:** 2-D loss per inch and routed density.

**FE35 Mode-conversion critic along the route** (new, M).
- **Mechanism:** Slice the pair into cross-sections. In each, compute imbalance from asymmetric neighbours, plane edges, vias and weave with the 2-D solver, and accumulate the conversion.
- **Why it beats the rules:** It catches asymmetry that length-skew checks miss.
- **Test:** Three asymmetric cases against 3-D simulation.

**FE36 Turn-balanced pair placement** (combo, S).
- **Mechanism:** A placer cost on signed turn imbalance (skew ≈ pitch × Σθ), so left and right turns cancel by topology and tuning only fixes the residual.
- **Test:** Total serpentine length on 10 boards.

**FE37 Spectrally weighted running skew** (sharp, S).
- **Mechanism:** The running-skew budget uses sin(πfΔt) at the frequencies that matter for common mode, and places compensation near each mismatch.
- **Test:** Common mode at the connector against end-only matching.

**FE38 Loose-pair escape mode** (new, S).
- **Mechanism:** Let pairs decouple through BGA pin fields when each leg keeps solid reference. Budget the uncoupled length by the Zdiff change it causes, not by a fixed 45 mil.
- **Test:** Escape completion and eye in 2-D/3-D.

## F. Geometry, pads, vias, weave

**FE39 Geometry relevance gate** (sharp, S).
- **Mechanism:** Per net, compute |Γ| for each feature from t_r. Enforce corner, arc and teardrop constraints only where they exceed the budget; elsewhere free the geometry for length, density and DFM.
- **Test:** Constraints removed with no simulated eye change.

**FE40 Pad-void synthesis** (new, S).
- **Mechanism:** Per stackup and pad, solve the void extent and depth that gives Z_pad = Z0, and emit it as a zone.
- **Physics:** In our stackup the answer is the pad width + 0.1 mm, where 60% leaves 32 Ω.
- **Test:** TDR or 3-D simulation of AC caps on three stackups against the 60% and 100% rules.

**FE41 Stub price in the router** (sharp, S).
- **Mechanism:** Via-stub cost is |S11| ≈ (Z0/2Z_s)·tan(βL) at Nyquist, which reproduces 0.3/Gbps. The router then trades layers, backdrill and microvias by price.
- **Test:** Stub-budget compliance and layer use on Gen4 boards.

**FE42 Fibre-weave angle planner** (new, M).
- **Mechanism:** An any-angle segment constraint θ ≥ max(asin(3P/L), Bragg bound) for long SerDes, or panel rotation chosen by fab cost.
- **Test:** Statistical skew simulation with a weave model, plus routed-length overhead.

**FE43 Antipad shaping for via impedance** (sharp, S).
- **Mechanism:** Choose antipad size and shape (oval for pairs) so the via's Z matches Z0, while checking that the cut-outs do not form slots for neighbours (FE4).
- **Test:** 3-D simulation at 16 GHz.

**FE44 ESD field-enhancement corners** (sharp, S).
- **Mechanism:** Apply a corner-radius rule only on nets exposed to ESD or HV. Compute it from field enhancement at a corner against surface breakdown, not from a 45° slogan.
- **Test:** The number of constrained nets, and a review of TI's 2.6 mm example.

**FE45 Teardrops as DFM only** (sharp, S).
- **Mechanism:** A teardrop costs about one corner's worth of SI. Allow it on all nets with edges slower than ~30 ps; on RF use computed impedance tapers.
- **Test:** The table check in [rf-geometry](../../topics/physics/rf-geometry.md).

## G. RF

**FE46 Chu-sphere keep-out volume** (new, S).
- **Mechanism:** Derive a 3-D keep-out from band and bandwidth: ka from Q ≤ 1/(√2·B), giving 7.5 mm at 2.4 GHz BLE. Merge it with the vendor polygon and check enclosure parts, batteries and connectors in 3-D.
- **Test:** Against vendor keep-outs and measured detuning.

**FE47 Pin-Q matching budget** (new, S).
- **Mechanism:** l_max for the first match element follows from pin Q and the mismatch allowance. Two millimetres costs 0.03 dB at Q 0.3 and 3 dB at Q 4. Otherwise, re-synthesise the match including the line.
- **Test:** scikit-rf on vendor reference designs.

**FE48 RF reference-integrity critic** (sharp, S).
- **Mechanism:** Price holes, antipads and slots within ±3h of an RF line as jωΔL against Z0 at the carrier.
- **Why it beats the rules:** It replaces "only GND under RF on all layers" when L2 is intact, since one plane absorbs 146 dB at 1 GHz.
- **Test:** Flags on open RF boards against openEMS.

**FE49 openEMS RF-path auto-check** (combo, L).
- **Mechanism:** Crop the RF path (pin → match → feed) with its reference from KiCad. Simulate S11/S21 automatically in openEMS (GPL-3.0) and compare with the budget.
- **Test:** Five open RF boards.

**FE50 Harmonic-to-channel frequency plan** (new, S).
- **Mechanism:** Find clock and SMPS harmonics that land in receive channels (26 MHz × 92 = 2.392 GHz). Apply layout separation and shielding only to those nets.
- **Test:** Synthetic BLE and Wi-Fi boards.

**FE51 Ground plane as the antenna's other arm** (sharp, S).
- **Mechanism:** Size the board ground in the λ/4–λ/2 range for the band, and keep its chassis-mode current path free of slots.
- **Physics:** This is the reason behind u-blox's 24 × 30 mm minimum.
- **Test:** openEMS on module-plus-board variants.

**FE52 RF↔SMPS coupling budget** (new, M).
- **Mechanism:** Replace "20 mm from SMPS" with a near-field estimate in dB below receiver sensitivity:
  - the inductor's magnetic dipole moment, from ripple current and footprint;
  - the switch node's electric coupling, from area and dV/dt.
- **Test:** A dev board or openEMS.

## H. Solvers and validation

**FE53 PEEC as a library** (sharp, M).
- **Mechanism:** Turn fe_peec_plane into a fast, hierarchical (later GPU) solver, so ΔL and κ for a whole board take under a second.
- **Test:** Speed, and agreement with FastHenry.

**FE54 Rule → metric oracle tests** (new, S).
- **Mechanism:** Each classic rule becomes a pair of layouts, compliant and not, and the metric must rank them correctly.
- **Why it is useful:** It catches metric bugs and documents each decompression.
- **Test:** 30 pairs: full agreement, or a documented regime where the rule is wrong.

**FE55 Adjoint sensitivities for placement** (new, M).
- **Mechanism:** Get ∂V_ab/∂position and ∂f_res/∂via from the PEEC and cavity models by the adjoint method, so the placer has gradients.
- **Test:** Gradient check against finite differences.

**FE56 Calibration ledger** (combo, S).
- **Mechanism:** Every closed form carries a trust range (± dB) learned from openEMS or measurement. The agent escalates to full-wave only when a margin is inside that range ([solver-ladder](../../topics/physics/solver-ladder.md)).
- **Test:** The number of escalations against the number of decisions they changed.
