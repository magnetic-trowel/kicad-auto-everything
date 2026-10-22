# Physics-first ideas: thermodynamics, dissipation, noise and irreversibility (TH)

These ideas treat a layout as a dissipative system. Every unwanted joule needs a destination, and for rings above ~50 MHz copper is not one, so it must be designed. Every loss is also a noise source and a heat source. Every conductive heat path is also an electrical element. Damage accumulates where loss and stress concentrate.

The argument, derivations and numbers are in [lens-th](../../topics/physics/lens-th.md), which defines the principles cited below:

| Principle | Short name |
|---|---|
| TP1 | least dissipation |
| TP2 | passive reciprocal heat |
| TP3 | fluctuation–dissipation |
| TP4 | modal energy ledger |
| TP5 | Onsager thermoelectricity |
| TP6 | electro-thermal stability |
| TP7 | irreversible damage |
| TP8 | exchange rates and boundaries |

Scripts:
- [th_damping_ledger.py](../../../tools/research/physics/th_damping_ledger.py)
- [th_electrothermal.py](../../../tools/research/physics/th_electrothermal.py)
- [th_dissipation_noise.py](../../../tools/research/physics/th_dissipation_noise.py)

These ideas build on, and do not repeat:
- [thermal-hv-mfg](thermal-hv-mfg.md): TM2, TM6, TM13–TM17, TM21, TM24.
- [cross-domain](cross-domain.md): XD8, XD19, XD35, XD78, XD81, XD84, XD88.
- [si-emi-rf](si-emi-rf.md): FE26, FE31.
- [power](power.md): PW29, PW31.
- [reasoning](reasoning.md): DR3, DR27, DR28.
- [rule-replacements](rule-replacements.md): RG24.
- [optimization](optimization.md): OP1, OP11.

Tags: *new* (not in the corpus), *combo* (a new combination of known parts), *sharp* (a known idea made precise or given a number). Effort: S (days), M (weeks), L (months). Everything is untested [I] unless tagged [C].

**Build first:**
- **TH2 + TH1:** an undamped-mode alarm, then the full Q ledger.
- **TH29:** the electro-thermal margin, computed from the FV thermal matrix.
- **TH24 + TH25:** the thermoelectric loop critic.
- **TH14:** dielectric noise at high-impedance nodes.
- **TH19:** the Wiedemann–Franz dual solve.
- **TH3:** tuned snubbers, validated on one GaN board.

## A. Where every joule goes

**TH1. Modal Q ledger.** For each detected mode, record:
- frequency and Q;
- loss-channel shares: copper (Q = h/δ), dielectric (tanδ), devices and capacitors, designed dampers, radiation;
- excitation (ΔI, ΔV) and the predicted ring-band emission.

The budget row reads "designed share ≥ 50%" wherever excitation × Q exceeds the emission or overshoot budget. The modes are hot-loop rings, LC filters, PDN anti-resonances, plane cavities and cable common mode.

Principle TP4. Res carries frequencies today. Nothing records where a mode's energy goes, yet ring-band emission rises 19.9 dB per decade of Q until the edge spectrum takes over; damping Q 10–20 to ~1 buys 12–21 dB [C]. Test: on 5 converter EVMs, compare predicted ring-band levels and fix rankings with near-field scans. *new, M*

**TH2. Copper-only Q alarm.** Flag any mode whose only loss channels are copper and laminate as undamped. Q_cu = h/δ comes from the stackup and the frequency, at F1 cost; it holds for rings above ~50 MHz, while plane pairs below ~30 MHz on thin cores get Q 1–10 from copper alone [C, rt_sheet_return]. Principle TP4 (D1). It catches LC filters, hot loops and plane pairs with no designed loss, and retires the intuition "the copper will damp it": Q_cu is 8–720 for gaps of 0.05–1.5 mm at 0.1–1 GHz [C]. Test: in the mutation benchmark, delete snubbers and ESR parts; the alarm must fire at the planted site. *sharp, S*

**TH3. Tuned snubber synthesis.** Choose R_s, C_s and the snubber's own mounting inductance L_s together, aiming at L_s·C_s ≈ L·C_oss (Den Hartog's tuned absorber). L_s is realized through part size, via count and trace length, so snubber placement becomes a tuning variable for the joint optimizer. Accept a design only after a ±2× C_oss robustness check and an overshoot check. Principle TP4 (D3). It reaches the same Q at a third of the loss: n = 1 tuned gives Q 1.01 at 72 mW, against Q 0.96 at 216 mW for the textbook n = 3 [C]. The cost is robustness: Q rises to 2.7 when C_oss doubles. Builds on XD19, XD81 and PW29. Test: transient SPICE with vendor GaN and Si models, then one bench half-bridge with three snubber geometries. *combo, S*

**TH4. Damper placement by mode shape.** Compute each target mode's eigenvector (PEEC loop network, cavity model or cable-CM model).
- Put shunt dampers (RC, controlled-ESR caps, terminations) at voltage antinodes.
- Put series dampers (beads, R∥L damping links, gate resistors) at current antinodes.
- Weight candidate sites by the mode's energy participation.

Principle TP4. This replaces "ferrite at the connector" and "snubber close" with a computed location, and generalizes XD78 (cavities only) to every mode. Test: Q reduction per candidate damper site on three structures (cavity, LC filter, cable CM), from the model and on one board. *sharp, S*

**TH5. Damping price in watts and band.** Give each damping topology a ledger row with three entries:
- a shunt RC costs C·V²·f;
- a series R costs I_rms²·R;
- a frequency-selective damper (DC-blocked RC, R across a bead, lossy edge band) costs about the ring energy alone.

Pick the topology whose dissipation spectrum lies outside the circuit's working band. Principle TP4/TP1. This makes the EMI-versus-efficiency trade explicit: a 12 V, 10 A, 500 kHz buck pays 216 mW for a textbook snubber, against 25 + 36 mW of unavoidable turn-off energy [C]. Test: on 10 converters, compare ledger-predicted snubber loss with measured efficiency, with and without the snubber. *new, S*

**TH6. Ring term in the EMI chain.** Add a ring line to the [fields-emi-budget](../../topics/physics/fields-emi-budget.md) chain: amplitude ≈ ΔI·Z0 and spectral density ∝ Q_m/ω_r at f_r, carried through the common-mode path. Damping (Q) and ring steering (f_r) then become priced levers in dB and W, beside edge rate and topology. Principle TP4. The chain is trapezoid-only, but rings sit at 30–300 MHz, where cables resonate. Test: chain with and without the ring term against radiated or near-field scans of 5 EVMs. *sharp, S*

**TH7. Self-damping stackup term.** In stackup synthesis (DR30, PW28), score each PWR–GND pair by Z_pk ∝ d·Q(d), with Q = 1/(tanδ + δ/d). Flag a move to a low-loss laminate as a PDN risk: peaks rise 1.7× at d = 0.1 mm and 3.3× at 1.5 mm [C]. Principle TP4 (D4). Today "thin = more capacitance" is the only argument for thin cores; the damping half is missing. Test: cavity model against VNA on two coupons (FR-4 vs low-loss, same d). *new, S*

**TH8. Hybrid-loss stackups.** Let the stackup optimizer pick dielectric loss per layer pair. Lossy material (FR-4, or high-tanδ embedded capacitance) goes in power cores, and low-loss laminate in signal layers. Principle TP4. One material choice currently serves two opposite goals: SI wants low loss, while PDN damping wants loss. Test: SI loss budget and PDN peak impedance for three hybrid stackups vs uniform ones, plus fab cost from the cost oracle. *combo, M*

**TH9. Termination pitch from ESL.** Generate PWR–GND edge terminations at pitch p < η0·d/(√εr·ωL_esl), with R ≈ η0·d/(√εr·p). If the pitch is impractical, use a thinner core or a resistive edge band instead. Principle TP4 (D4). This makes FE31 buildable:
- a 0.1 mm core needs ~6 mm pitch at 1 GHz with 0.5 nH parts;
- at 10 mm pitch, ESL cuts the benefit from 5.5× to 2.8× [C].

Test: cavity model plus a coupon S21 with terminations at two pitches. *sharp, S*

**TH10. Absorptive I/O filtering.** At cell and cable boundaries, prefer filters whose Re Z dominates at the cable's common-mode resonance: lossy ferrites and RC networks. Check the modal Q of the filter plus cable, and reject lossless LC filters that ring with the cable. Principle TP4. A reactive filter reflects energy back into the board and peaks at Q = √(L/C)/R. Test: CM current spectra on a harness with reactive vs absorptive filters, simulated and on the bench. *new, S*

**TH11. Damped heatsink and shield bonds.** A heatsink or shield can is a capacitance (~22 pF class) in series with its bond inductance. Compute that resonance and its Q. Add a damping path with R ≈ √(L_bond/C), in parallel with the low-inductance bond, so the bond stays effective above resonance. Principle TP4. DR28 chooses the bond node, but nobody checks the bond's own ring. Test: openEMS of a heatsink and bond with and without R, then a near-field scan. *new, S*

**TH12. Layout-born dissipators as ECOs.** The synthesizer may propose parts the schematic lacks: edge terminations, damping links, tuned snubber geometry and controlled-ESR capacitors. Each proposal carries a price in watts, area and dB, and the human confirms it. Principle TP4. Minimizing parasitics alone cannot damp a mode, so designed dissipation has to be a sanctioned action class, not an afterthought. Test: on 10 boards, count binding EMI or PDN budgets that are met only with layout-born parts. *new, S*

## B. Every loss is a noise source

**TH13. Fluctuation–dissipation back-annotation.** In the LII loop, extract lossy parasitics as noisy passive elements:
- R_ac(f) as Foster ladders;
- dielectric conductance ωC·tanδ;
- ferrite Re Z(f);
- leakage conductance.

Run the real `.noise` analysis and include noise outputs in LII. Principle TP3. DR3 already runs `.noise` for transfer functions, so the layout's own noise comes for free. Passivity enforcement (SIM33) becomes a correctness requirement for noise too. Test: fA TIA and LNA front ends, predicted vs measured noise floors. *new, M*

**TH14. Dielectric-noise critic for high-impedance nodes.** For nodes above ~1 GΩ (electrometers, photodiode TIAs, charge amplifiers, ion sensors), sum C·tanδ of the board dielectric each node touches: pads, trace, guard gap. Compare 4kT·ωC·tanδ with the amplifier's noise and the feedback resistor's noise. The remedies are smaller pads, slots or air gaps, PTFE inserts and lifting the node; a guard ring is not one. Principle TP3. One pF of FR-4 out-noises a 1 TΩ resistor above 8 Hz [C]. A guard removes the signal current through the dielectric but not its thermal noise current. Test: noise of two TIA layouts on a bench, an FR-4 guard ring against a slot or PTFE island. *new, S*

**TH15. Front-end loss ledger in kelvin.** Charge every element between the antenna or sensor and the first gain stage to the noise-figure budget as T_add = (L − 1)·T_phys. That includes matching-component Q, ESD-diode loss and FR-4 line loss. The antenna itself adds (1 − η)·T_phys. Principle TP3. This turns "LNA close to the antenna" into a budget. A GNSS antenna of efficiency 0.5 adds 2.7 dB of noise on top of its 3 dB gain loss [C]. Test: predicted vs measured C/N0 on two GNSS boards with different antenna and LNA placements. *sharp, S*

**TH16. Lossy-material participation near antennas.** Compute the participation of lossy regions (FR-4, batteries, ferrites, displays) in the antenna mode, as in XD84. Charge each one both as efficiency and as noise temperature, and move lossy parts out of high-participation regions. Principle TP3/TP4. Antenna keep-outs are binary today, but loss there costs twice: once in gain and again in noise. Test: EPR-predicted efficiency change vs chamber measurement for three battery positions. *combo, M*

**TH17. Copper Johnson-noise keep-out for magnetometers.** Near optically pumped or SQUID-class sensors, budget δB = μ0√(kTσt)/(√(8π)·a) per copper layer. One 1 oz plane gives 72 fT/√Hz at 10 mm and 361 at 2 mm [C]. Slot or remove pours, use thinner copper, or move the sensor; fluxgate and Hall sensors are exempt. Principle TP3. Near such sensors, "pour everything" adds magnetic noise above their 10–20 fT/√Hz floors. Test: magnetometer noise spectra with and without nearby pours. *new, S*

**TH18. Thermal-EMF fluctuation budget.** For nV-class DC front ends, model the differential temperature fluctuation spectrum at each junction pair: air turbulence filtered by the local thermal RC, times ΔS. Three levers reduce it:
- covers;
- thermal mass on both junctions;
- shared copper islands that make the fluctuations common-mode.

Principle TP5/TP3. TM13 and DR27 treat thermal EMF as a static offset. At a 7 nV rms ADC floor, millikelvin fluctuations times µV/K coefficients matter. Test: 0.01–1 Hz noise of a covered vs uncovered input stage. *new, M*

## C. Heat paths are electrical elements

**TH19. Wiedemann–Franz dual solve.** Reuse the DC (IR-drop) factorization of the copper as the copper part of the thermal network, with G_th = L·T·G_el. Only the dielectric and convection terms are added. Principle TP8. OP1 kept separate coefficient sets, but for metal one universal constant links them: a via's 1.74 mΩ is its 260 K/W [C]. Test: WF-derived copper thermal resistance vs tm_board_thermal_fv on 10 copper shapes. *new, S*

**TH20. Electrical twin of every heat path.** Tag each thermal element with its electrical shadow and send it to the EMI and isolation ledgers. Metal elements become Ω via Wiedemann–Franz; dielectric elements become pF via k/ε. The elements include via arrays, TIM pads, thermal prepreg, standoffs and heatsink contacts. For example, 1 K/W through FR-4 costs 127 pF [C]. Principle TP8. This unifies heatsink capacitance, standoff bonds and switch-node heat spreading (S4), and blocks thermal fixes that create antennas or breach isolation. Test: on 10 boards, count thermal edits that change a Vcm or isolation verdict. *combo, S*

**TH21. Radiative boundary as a design input.** When convection is weak (altitude, vacuum, sealed enclosures), switch the thermal model to radiation-dominant. Per-region emissivity (mask vs bare finishes) and solar absorptance then become layout variables, and conduction into the structure through standoffs comes first. Principle TP8. At 20 km radiation carries ~52% of the cooling, and in sunlight black and white mask differ by ~64 K at radiative equilibrium [C, rough]. Extends TM6 and TM21. Test: thermal-vacuum test of two mask finishes on one design. *sharp, S*

**TH22. Warm-zone placement for leakage-critical nodes.** Local warming lowers surface relative humidity by 6.3%/K [C]. Which way to place depends on the binding physics:
- When humidity or condensation binds, put HV creepage regions and GΩ nodes in warm regions, or add a small heater.
- When drift binds, keep them in cool, isothermal regions.

Principle TP2/TP7. "Keep sensitive parts cool" is wrong when leakage binds. Test: dew-cycling leakage tests with warm vs cold placement. *new, S*

**TH23. Plume-aware thermal kernel.** For vertical boards in natural convection, add an upwind (advective) term to the thermal kernel. The "upstream" rule then becomes a computed, non-reciprocal coupling θ_ij ≠ θ_ji. Principle TP2. The TM2 and OP23 kernels are reciprocal, while rules TH-06 and TH-07 encode advection. Test: IR camera on a vertical board with a heater below vs above a sensor. *new, M*

## D. Thermoelectric precision

**TH24. Thermoelectric loop-integral critic.** Compute EMF = Σ_k ΔS_k·(T_k,in − T_k,out) along each precision loop.
- ΔS comes from a material table keyed by the bill of materials: solder, nickel barrier, tin plating, Kovar or Alloy-42 leads, resistor elements, connector and relay contacts.
- T comes from the FV field.

Report µV and the top three segments. Principle TP5. TM13 orients single parts; this sums the whole loop and catches connectors, relays and leaded parts. Test: bench offset vs prediction on a board with a controllable heater. *sharp, S*

**TH25. Differential congruence check.** The two legs' non-copper segment chains must be congruent by translation along the isotherms, or by reflection across the gradient direction. The residual is ≈ ΔS·ℓ·s·∂²T for leg separation s, and the placer receives the check as a constraint. Principle TP5. A P/N layout mirrored across the gradient doubles the EMF instead of cancelling it; DR27 states only the good case. Test: FV plus the loop integral for mirrored vs translated layouts. *sharp, S*

**TH26. Thermal-dipole susceptibility map.** By reciprocity, one thermal solve gives µV per watt for every possible heat-source location. Place unit sources of opposite sign at the two ends of each non-copper segment, weighted by its ΔS. The placer reads the result as a lookup. Principle TP2/TP5. One solve per precision loop replaces a re-solve per move. It complements XD35 (electromagnetic) and TM2 (forward kernel). Test: map-predicted vs direct FV EMF for 50 source positions. *new, S*

**TH27. Shunt thermal symmetry and alloy rule.** Constrain the two shunt pads to equal thermal resistance (copper area, vias, distance to heat sources). Choose the alloy by the S²/L0 bound at the design current. Principle TP5 (D5). With 25 vs 80 K/W pads, Joule asymmetry gives 156 ppm at 10 A in manganin. Peltier gives up to 2.5% in constantan [C]. Test: DC vs pulsed resistance on symmetric and asymmetric pads. *new, S*

**TH28. Harman coupon for current sensing.** Measure R_DC/R_AC, or the slow tail after a current step, on the as-built shunt to calibrate the Peltier and asymmetry terms. Add it to the F4 coupon panel. Principle TP5. It is a cheap direct measurement of a thermoelectric error that the critic predicts. Test: a coupon with manganin and constantan shunts. *new, S*

## E. Electro-thermal stability

**TH29. Electro-thermal margin critic.** Compute g = ρ(D^½ΘD^½) from the FV thermal matrix Θ and datasheet slopes dP/dT: R_DS(on) TC, copper TCR, diode and BJT TC, and 0 for LDOs. Report the amplification 1/(1−g) and the board-floor bound Σα_iP_i/(h_tot·A), and flag g > 0.3. Principle TP6 (D6). It generalizes TM16 (one conductor) to all parts. On small boards the margin is board-level: the floor alone gives 0.25 of g = 0.32–0.36 in a 2 W example [C]. Test: FV fixed point vs bench on a four-FET board at three loads. *new, S*

**TH30. Mode-aware thermal relations for paralleled parts.** Classify paralleled devices by the sign of ∂I/∂T at fixed voltage.
- Negative-TC parts (BJTs, diodes, linear-mode and hot-swap FETs) get `thermal_couple`: minimize θ11 − θ12, share a pad or a die, and carry a ballast budget.
- Positive-TC parts get spacing only if g binds.

Principle TP6. A single "spread hot parts" rule is wrong for half the cases. Moving from 32 to 4 mm apart raised the hogging limit 1.7×, and a dual die raised it 15× [C]. Sharpens TM17. Test: current sharing of paralleled BJTs or diodes at two spacings. *sharp, S*

**TH31. Thermal back-annotation into SPICE.** Write a per-instance TEMP from the thermal field into the netlist, and iterate with the losses. LII then sees shifts in R_DS(on), V_f, reference drift, crystal ppm and MLCC C(T). Principle TP6. DR10's LII compares outputs at a single temperature. Test: predicted vs measured output drift of a reference-plus-ADC board with a heater. *new, M*

## F. Irreversible damage

**TH32. Two-kernel life map.** Compute Arrhenius damage from the DC kernel (mean temperature) and fatigue damage from the complex-screening AC kernel at the mission's power-cycle frequencies, then take the Miner sum per part. The swing is local (~2|Λ| = 18 mm at a 60 s period), while the mean is board-wide (~76 mm) [C]. Principle TP7. A single "keep away" radius cannot serve both mechanisms. Test: thermal-cycling coupons; transient FV vs AC kernel. *new, M*

**TH33. Fourier-number gate for corner rounding.** Round inside corners only where t_pulse < w²/α_Cu, or where fields or HV bind. The threshold is 0.8 ms at 0.3 mm, 9 ms at 1 mm and 80 ms at 3 mm. Principle TP7 (D7). It replaces the fixed "~1 ms" with a width-scaled predicate. Test: transient 2-D sheet solves at three widths. *sharp, S*

**TH34. Crowded-pin electromigration check.** For high-current fine-pitch pins (QFN power pins, BGA balls), compute the pad-entry current density, including crowding, from the sheet solve at the pin's temperature. Compare it with ~10⁴ A/cm² for Sn-based solder [S]. The lever is the feed geometry: a pour all around the pad vs a one-sided trace. Principle TP7. Electromigration is usually dismissed on PCBs because the copper is safe, but the solder joint is the weak point. Test: predicted crowding sites vs published EM failure sites, then EM coupons. *new, S*

**TH35. Damage-weighted copper shapes.** After a loss-optimal pour (p = 2), continue the objective toward a damage norm (p ≈ 4–8, Arrhenius-weighted by T), but only where the life budget binds. This rounds entries and corners exactly where life is at stake and nowhere else. Principle TP1/TP7. It separates shape changes that buy life from those that buy nothing. Extends XD8 and OP11. Test: life-weighted vs loss-optimal shapes on the OP2 test pour. *combo, M*
