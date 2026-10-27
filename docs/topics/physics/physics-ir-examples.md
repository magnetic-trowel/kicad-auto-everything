# Physics IR worked examples: buck, USB3, crystal, 24-bit ADC, 2.4 GHz feed, 48 V half-bridge

**TL;DR**
- Six circuits in the `physics:` grammar of [physics-ir.md](physics-ir.md). Every YAML block passes `tools/research/physics/vo_ir_check.py` with 0 errors; its warnings flag references to entities defined elsewhere on the board [C].
- In each case the binding budget differs from what the rule of thumb names: switch-node C and FB pickup (buck), dB spend (USB3), pF of uncertainty (crystal), 15 µΩ of common impedance (ADC), the plane as half the antenna (2.4 GHz), common-source and mutual inductance (motor drive).
- Design points are illustrative assumptions [I]; numbers marked [C] come from `tools/research/physics/vo_numbers.py`.
- Code drafts most entities; the LLM writes requirement links, allocations and `ops`. `src` fields are omitted.

## Key facts

| Example | Dominant primitives | Binding budget [C] | Rule of thumb it replaces |
|---|---|---|---|
| Buck 12→3.3 V | loop, node, coupling, sense port | FB edge pickup ≤ 30 mV ⇒ ≥ 2 mm from SW when fully parallel; SW C ≤ 10 pF | "FB away from SW", "small loop" |
| USB3 Gen1 | channel, port pair, discontinuity, antenna | IL ≥ −5.5 dB at 2.5 GHz ⇒ about 200 mm of trace after fixed spends | "≤ N inches", "match 5 mil" |
| 32 MHz crystal | node (victim), loop, shield | ±0.61 pF stray uncertainty ⇒ about 3 mm of trace per 0.3 pF | "≤ 5 mm from MCU" |
| 24-bit ADC | sense port, exclusion, coupling (thermal, leakage, common impedance) | R_shared ≤ 15 µΩ ⇒ geometric current exclusion | "split AGND/DGND", "far from SMPS" |
| 2.4 GHz feed | channel, designed antenna, shield, exclusion | S11 ≤ −10 dB; fence pitch ≤ λ_g/20 = 3.4 mm | "15 mm keep-out", "no 90° bends" |
| 48 V half-bridge | cell, gate loop, sense port, coupling to chassis | L_cs ≤ 1 nH; M(hot, sense) ≤ 0.05 nH; tab C·dv/dt | "short wide switch node" |

### 1. Synchronous buck, 12 V → 3.3 V, 3 A, 1 MHz, integrated FETs

```yaml
bands:
  sw: ["f_sw(buck1)", "1/(pi*tr(buck1.sw))"]
  edge: [159 MHz, 1 GHz]
physics:
  - {id: buck1, kind: cell, template: buck, parts: {ic: U3, cin_hf: C10, l: L1, cout: [C12, C13], fb: [R5, R6]}}
  - id: buck1.hot
    kind: loop
    class: commutation
    path: [C10.1, U3.VIN, U3.SW, U3.PGND, via:GND, C10.2]
    return: [ref.l2]
    excite: {wave: trapezoid, I: 3 A, f0: 1 MHz, duty: 27.5 %, tr: 2 ns}
    budget: {V_pk: "<= 0.85*V_abs(U3.VIN)", alloc: {c10_esl_pads: 30 %, vias: 20 %, lateral: 50 %}, band: edge}
    why: [req.vin_abs_max]
  - {id: buck1.sw, kind: node, net: SW, excite: {wave: trapezoid, V: 13.2 V, f0: 1 MHz, tr: 2 ns}, budget: {C: "<= 10 pF"}}
  - {id: buck1.fb, kind: node, net: FB, z_src: 2.4 kohm, sense: {threshold: "0.01*V_ref(U3)", band: sw}}
  - {id: cpl.sw_fb, kind: coupling, aggr: buck1.sw, victim: buck1.fb, mech: capacitive, band: edge, budget: {V_pk: "<= 30 mV"}}
  - {id: buck1.vsense, kind: port, use: sense, sig: [C12.1], ref: [C12.2], budget: {I_through: "== 0 A"}}
  - {id: buck1.out, kind: feed, from: L1.2, to: J2.1, I: 3 A, budget: {R: "<= 5 mOhm"}}
  - {id: hp.u3, kind: heat_path, source: U3, P: 0.8 W, sink: ambient, via: [U3.EP, ref.l2], budget: {Tj: "<= 105 degC"}}
ops:
  - {op: fold_loop_vertical, target: buck1.hot, args: {return_layer: In1.Cu}}
  - {op: shrink_node, target: buck1.sw}
  - {op: kelvin_tap, target: buck1.vsense}
```

- **Spectra** [C]: di/dt = 1.5 A/ns, dv/dt = 6 V/ns; knee 1/(π·t_r) = 159 MHz, which defines the `edge` band.
- **The hot loop budget is a peak voltage, not an area.** Code chooses the spend model by regime. When the edge is shorter than the ring period, an LC step model applies instead of L·di/dt; [dr_switch_cell_budget.py](../../../tools/research/physics/dr_switch_cell_budget.py) shows that the two can disagree by an order of magnitude [C]. The `alloc` splits the budget across the cap's ESL and pads, the vias and the lateral path, so the ledger can attribute spend.
- **The switch node is the second aggressor and has the opposite sign.** A 20 mm² SW pour over a plane 0.1 mm down is 7.6 pF and injects C·dv/dt = 46 mA of displacement current each edge [C]. `widen_to_pour` would help the feed and hurt this node, which is why node and loop are separate primitives.
- **FB coupling.** Johnson's K = 1/(1+(D/H)²) as a capacitive-divider bound: at H = 0.1 mm a fully parallel FB trace picks up 462 mV at D = 0.5 mm, 119 mV at 1 mm and 30 mV at 2 mm [C, rough]. The compiler emits `clearance (min 2mm)` between SW and FB as a proxy; the checker integrates the actual parallel length.
- **Feed.** 3 A over 20 mm of 1 mm, 1 oz track is 9.8 mΩ (29 mV, 88 mW); a 5 mm pour is 2 mΩ [C]. That is why `R ≤ 5 mOhm` triggers `widen_to_pour` on VOUT but not on SW.

### 2. USB 3.x Gen1 SuperSpeed TX through a Type-C receptacle

```yaml
bands:
  nyq: [2.5 GHz, 2.5 GHz]
  cm: [30 MHz, 1 GHz]
physics:
  - {id: J1.sstx, kind: port, use: signal, sig: [J1.A2, J1.A3], ref: [J1.A1, J1.A12, J1.S1], fixed: {edge: north}, external: cable, z: 90 ohm}
  - {id: U5.tx, kind: port, use: signal, sig: [U5.TXP, U5.TXN], ref: [U5.GND]}
  - id: usb.sstx
    kind: channel
    from: U5.tx
    to: J1.sstx
    through: [C21, C22, D3]
    z: 90 ohm
    ref: [ref.l2]
    transitions: 2
    budget: {IL: ">= -5.5 dB", skew: "<= 1 ps", V_cm: "<= 5 mV", band: nyq}
    why: [req.usb3_gen1]
  - {id: usb.sstx.t_conn, kind: discontinuity, in: ref.l2, type: ref_change, bridge: gnd_vias}
  - {id: ant.usb_dc, kind: antenna, halves: [J1.S1, J4.S1], drive: [current, voltage], band: cm, budget: {V_cm: "<= 1 mV", I_cm: "<= 5 uA"}}
ops:
  - {op: stitch, target: usb.sstx.t_conn, args: {dist: "<= 1 mm"}}
  - {op: relocate_port, target: J4, args: {edge: north}}
```

- **Loss spend** [C]: FR-4 (Df 0.02), 5 mil traces: 0.21 dB/in dielectric (Bogatin-style 2.3·f·Df·√Dk) + 0.25 dB/in conductor ≈ 0.46 dB/in. Two vias (about 1 in each), ESD+CMC (about 1 in) and 0.5 dB for AC caps and receptacle [I] leave 3.6 dB, about 200 mm of trace. The conductor-loss constant is from memory, unverified [I].
- **Skew is a common-mode budget, not a length.** 5 mil is 0.77 ps at 6 ps/mm; with a 60 ps edge and 0.5 V leg swing, the CM spike is about 3 mV [C]. The vendor spread (2 mil to 0.7 mm, [usb3-usb4-typec](../rules/interfaces/usb3-usb4-typec.md)) collapses into one `V_cm` budget that each vendor profile can tighten.
- **The connector is a reference transition.** The discontinuity entity makes the return device explicit (GND vias within 1 mm), compiled as a via-site reservation (R3).
- **The antenna has two named halves:** J1's shell and the DC jack J4's shell. The budget is LearnEMC's 1 mV between antenna halves and Ott's 5 µA cable CM current for Class B ([emc-placement](../rules/emc-placement.md)) [P]. `relocate_port` (both connectors on one edge) is the cheapest fix, consistent with LearnEMC's connector zoning [P].

### 3. 32 MHz Pierce crystal for an 802.15.4 radio

```yaml
physics:
  - {id: xtal1, kind: cell, template: xtal_pierce, parts: {osc: U2, xtal: Y1, cl: [C30, C31]}}
  - id: xtal1.loop
    kind: loop
    class: signal
    path: [U2.XOUT, Y1.2, Y1.1, U2.XIN, C30.1, C30.2, C31.2, C31.1, U2.XOUT]
    return: [C30.2, C31.2, via:GND]
    excite: {wave: sine, f0: 32 MHz, V: 1 V}
  - id: xtal1.xin
    kind: node
    net: XIN
    z_src: 1 Mohm
    sense: {threshold: 17 ppm, band: [32 MHz, 32 MHz]}
    budget: {C: "[1.0 pF, 2.2 pF]", df: "<= 17 ppm", basis: "27.7 ppm/pF pullability"}
  - {id: xtal1.guard, kind: shield, protects: xtal1.loop, type: grounded}
  - {id: ex.xtal, kind: exclusion, region: "hull(xtal1)", of: [foreign], band: [1 MHz, 1 GHz], budget: {J_frac: "<= 1 %"}}
  - {id: cpl.sw_xin, kind: coupling, aggr: buck1.sw, victim: xtal1.xin, mech: capacitive, band: [32 MHz, 32 MHz], budget: {V_pk: "<= 1 mV"}}
```

- **The budget is in pF, derived from ppm** [C]. Pullability S = C1/(2(C0+CL)²) = 27.7 ppm/pF for C1 = 5 fF, C0 = 1.5 pF, CL = 8 pF. The ±40 ppm 802.15.4 budget minus 10 (tolerance), 10 (temperature) and 3 (aging) leaves ±17 ppm, so the stray-capacitance *uncertainty* must stay within ±0.61 pF. At 0.10 pF/mm (0.15 mm trace over 0.1 mm), 0.3 pF is 2.9 mm of trace. The "≤ 5 mm" rule is a lossy encoding of this.
- **Uncertainty, not value, is spent.** A known stray is absorbed by choosing CL; only the unknown part costs ppm.
- **XOUT is an aggressor** (peak 0.10 V/ns at 1 Vpp [C]) and XIN a high-impedance victim, so one cell carries both roles. ST's 0.175 pF × 45 ppm/pF ≈ 7.8 ppm example ([crystals-clocks](../rules/crystals-clocks.md)) is the same budget for a more pullable 32 kHz crystal [P].

### 4. 24-bit bridge ADC front end (ratiometric)

```yaml
physics:
  - {id: adc1.ain, kind: port, use: sense, sig: [U9.AIN0], ref: [U9.AIN1], budget: {I_through: "<= 1 nA"}}
  - {id: adc1.vref, kind: port, use: sense, sig: [J5.2], ref: [J5.5], budget: {I_through: "== 0 A"}}
  - id: adc1.in_loop
    kind: loop
    class: sense
    path: [J5.3, R20.1, R20.2, U9.AIN0, U9.AIN1, R21.2, R21.1, J5.4, J5.3]
    return: [R21, J5.4]
    budget: {area: "<= 10 mm2"}
  - {id: adc1.node, kind: node, net: AIN0, z_src: 10 kohm, sense: {threshold: "LSB(U9)", band: [0 Hz, 10 Hz]}}
  - {id: cpl.dig_ref, kind: coupling, aggr: dig.ret, victim: adc1.vref, mech: common_impedance, shared: ref.agnd, band: dc, budget: {V: "<= 0.3 uV"}}
  - {id: ex.agnd, kind: exclusion, body: ref.agnd, of: [dig.ret, buck1.out], band: [0 Hz, 10 kHz], budget: {J_frac: "<= 0.1 %"}}
  - {id: cpl.ldo_in, kind: coupling, aggr: hp.ldo, victim: adc1.ain, mech: thermal, band: dc, budget: {dT: "<= 0.1 K"}}
  - {id: cpl.5v_in, kind: coupling, aggr: n.5v, victim: adc1.node, mech: leakage, band: dc, budget: {V: "<= 0.1 uV"}}
  - {id: cpl.mains_in, kind: coupling, aggr: feed.heater, victim: adc1.in_loop, mech: inductive, band: [50 Hz, 60 Hz], budget: {V: "<= 0.1 uV"}}
  - {id: adc1.guard, kind: shield, protects: adc1.node, type: driven_guard}
```

- **Thresholds** [C]: LSB over a 5 V span is 298 nV; with fewer than 24 noise-free bits, a 0.3 µV layout share is generous [I].
- **Common impedance decides the topology.** 20 mA of digital return through the analog reference must see ≤ 15 µΩ, that is 0.031 squares of 1 oz copper (0.49 mΩ/sq) [C]. No pour is that good, so the physics forces a sense port (ratiometric reference taken at the bridge, J5.2/J5.5) and a current exclusion zone. "Split the ground" is a lossy encoding of `exclusion` plus `sense`. Splitting without the exclusion check can make it worse ([si-fundamentals](../rules/si-fundamentals.md)).
- **The input pair is in the R regime.** At 10 Hz the return current spreads by resistance: the "return under the trace" regime starts only at f_x ≈ R_□/(2πµ0h), about 0.3 MHz at h = 0.2 mm [C, `vo_return_spread.py`]. Star-point thinking is correct here, and wrong for the buck.
- **Thermal EMF** [C]: Cu–Sn/Pb solder joints are 1–3 µV/°C and Cu–Kovar 40–75 µV/°C ([Keithley](https://xdevs.com/doc/Keithley/Appnotes/LV_LR_e-hnbook_91113.pdf) [P]). A 0.1 K difference between the two input joints is 0.1–0.3 µV, or 4 µV with Kovar leads. The thermal coupling (LDO heat path → input pair) is a budget in kelvin, realized by `symmetrize` and `isothermalize`.
- **Leakage and 50 Hz pickup** [C]: 5 V across 10 GΩ of surface leakage into a 10 kΩ node is 5 µV, hence the driven guard. A 1 A, 50 Hz conductor 10 mm away induces 0.63 µV in a 1 cm² input loop, so `area ≤ 10 mm²` is derived from the mains coupling, not chosen.
- **Honest magnitude.** Direct MHz magnetic coupling from a buck into a 10 SPS sigma-delta input is mostly removed by its digital filter. What matters is DC/LF common impedance, heat, leakage, and aliasing or rectification near the modulator frequency [I].

### 5. 2.4 GHz antenna feed (SoC → π match → chip antenna)

```yaml
bands:
  rf24: [2.4 GHz, 2.4835 GHz]
physics:
  - {id: rf.pin, kind: port, use: rf, sig: [U7.ANT], ref: [U7.VSS_RF]}
  - {id: ant1.port, kind: port, use: rf, sig: [E1.1], ref: [ref.l2_rf]}
  - id: rf.feed
    kind: channel
    from: rf.pin
    to: ant1.port
    through: [C50, L51, C52]
    z: 50 ohm
    ref: [ref.l2_rf]
    budget: {S11: "<= -10 dB", IL: ">= -0.5 dB", band: rf24}
  - {id: ant1, kind: antenna, intent: designed, halves: [E1, ref.l2_rf], drive: [current], band: rf24, budget: {S11: "<= -10 dB"}}
  - {id: ex.ant1, kind: exclusion, region: "keepout(E1)", of: [all_copper], band: rf24}
  - {id: rf.fence, kind: shield, protects: rf.feed, type: fence, pitch: "<= lambda_g(2.48 GHz, F.Cu)/20"}
  - {id: cpl.sw_rf, kind: coupling, aggr: buck1.hot, victim: rf.feed, mech: radiated, band: rf24, budget: {P: "<= -110 dBm"}}
```

- **Wavelengths** [C]: λ0 = 122 mm; on 0.35 mm over 0.2 mm FR-4 microstrip, ε_eff = 3.24, λ_g = 68 mm, λ_g/20 = 3.4 mm, λ_g/10 = 6.8 mm. The fence pitch is an expression, so a stackup change re-derives it.
- **Small parasitics are visible here** [C]: 1 nH is 15.4 Ω and 0.2 pF is 325 Ω at 2.45 GHz. An 0402 pad 0.1 mm over a plane is 0.11 pF (−j570 Ω), worth |S11| ≈ −27 dB by itself on a matched 50 Ω line. That is why RF reference designs sometimes void the plane under match pads: a designed `discontinuity`.
- **The ground plane is half the antenna.** `ant1.halves` names `ref.l2_rf`, so the same reference body is both a return (for `rf.feed`) and a radiator. Plane size and cuts near E1 become antenna parameters, not ground-quality issues. The keep-out is an `exclusion` of copper, sized per module ([rf](../rules/rf.md)).
- **Honest magnitude.** 90° corners do not matter at 2.45 GHz on a 0.35 mm line ([rf](../rules/rf.md)). A clean trapezoid (12 V, 1 MHz, 2 ns) is 90 dB below its low-frequency amplitude at 2.45 GHz [C], so desense comes mostly from SW-node *ringing* at hundreds of MHz and its harmonics. The aggressor spectrum therefore has to come from the layout-aware cell model, not from t_r alone.

### 6. 48 V half-bridge motor phase with low-side shunt

```yaml
bands:
  edge: [21 MHz, 300 MHz]
  ce: [150 kHz, 30 MHz]
physics:
  - {id: hb1, kind: cell, template: half_bridge, parts: {hs: Q1, ls: Q2, chf: C60, bulk: C61, shunt: R70, drv: U10, csa: U11, sink: HS1}}
  - id: hb1.hot
    kind: loop
    class: commutation
    path: [C60.1, Q1.D, Q1.S, Q2.D, Q2.S, R70.1, R70.2, via:PGND, C60.2]
    return: [ref.l2_pgnd]
    excite: {wave: trapezoid, I: 20 A, f0: 20 kHz, tr: 15 ns}
    budget: {V_pk: "<= 0.8*V_abs(Q1.D)", band: edge}
  - {id: hb1.gate_ls, kind: loop, class: gate, path: [U10.LO, Q2.G, Q2.S, U10.COM, U10.LO], return: [Q2.S], budget: {L_cs: "<= 1 nH"}}
  - {id: hb1.isense, kind: port, use: sense, sig: [R70.1], ref: [R70.2], budget: {I_through: "== 0 A", R: "<= 20 uOhm"}}
  - {id: hb1.sense_loop, kind: loop, class: sense, path: [R70.1, U11.INP, U11.INN, R70.2, R70.1], return: [R70.2]}
  - {id: cpl.hot_sense, kind: coupling, aggr: hb1.hot, victim: hb1.sense_loop, mech: inductive, band: edge, budget: {M: "<= 0.05 nH"}}
  - {id: hb1.sw, kind: node, net: PHASE, excite: {wave: trapezoid, V: 54 V, f0: 20 kHz, tr: 15 ns}}
  - {id: chassis, kind: port, use: chassis, sig: [HS1], ref: [MH1]}
  - {id: cpl.sw_tab, kind: coupling, aggr: hb1.sw, victim: chassis, mech: capacitive, band: ce, budget: {I: "<= 20 mA"}}
  - {id: hp.q2, kind: heat_path, source: Q2, P: 2 W, sink: HS1, budget: {Tj: "<= 125 degC"}}
ops:
  - {op: kelvin_tap, target: hb1.isense}
  - {op: orthogonalize, target: cpl.hot_sense}
```

- **Overshoot is not the binding nH budget here** [C]: di/dt = 1.33 A/ns, so 10 nH gives 13 V by L·di/dt against a 100 V part, and the ring sits at 60 MHz with 700 pF C_oss (85 MHz at 5 nH). The ring frequency lands in the CISPR radiated bands, so the band budget, not the voltage, drives loop size.
- **Common-source inductance is the gate's budget** [C]: 1 nH shared between hot loop and gate loop puts 1.33 V against the gate during the edge (the mechanism is described by [Microchip](https://developerhelp.microchip.com/xwiki/bin/view/products/power-management/sic-intro/packaging/) [S]). With a low-side shunt, the driver COM must return to Q2's source pin, *above* R70; otherwise the shunt's own drop and ESL enter the gate loop.
- **Shunt** [C]: 1 mΩ at 20 A is a 20 mV signal and 0.4 W. 0.1 mΩ of pad and solder in the sense path is a 10% error ([current-sense-kelvin](../rules/power/current-sense-kelvin.md)), hence the `R ≤ 20 uOhm` budget on the sense port. Shunt ESL of 0.3 nH adds a 400 mV spike, and 0.1 nH of mutual inductance between the hot loop and the sense loop adds 133 mV, so `M ≤ 0.05 nH` (67 mV, blanked or filtered) and `orthogonalize` follow.
- **The heatsink is a capacitor to chassis** [C]: a TO-220 tab (150 mm²) on a 0.23 mm pad (εr 4.5) is 26 pF; at 3.2 V/ns it drives 83 mA peaks into the chassis. That is a common-mode source the schematic never shows.
- **No barrier entity.** 48 V (54 V max) stays below the 60 V DC ES1/SELV limit [I], so creepage is a functional, not a safety, budget here.

## Recommendations for our system

- Use these six blocks as the regression set for the validator, compiler and critics; every budget must yield a ledger row with a model id and trust status [I].
- Implement in this order: buck (loop, node, coupling, sense), USB3 (channel, discontinuity, antenna), ADC (exclusion, common impedance, thermal). They exercise all compile targets except full-wave [I].
- Do not convert any of these budgets back to a millimetre DRU rule without tagging it as a proxy with its derivation (I2).

## Conflicts and open questions

- The undamped LC-step model of [dr_switch_cell_budget.py](../../../tools/research/physics/dr_switch_cell_budget.py) predicts near-100% overshoot almost independent of L for both power examples, so V_pk budgets need a damped, vendor-calibrated cell model before they gate anything.
- The Johnson K bound for FB pickup and the dB/in loss rule are rough; both need a 2D field-solver check ([solver-ladder](solver-ladder.md)).
- Desense budgets (`P ≤ −110 dBm` in channel) are placeholders; they need the radio's blocking and spur specs.

## Sources

- Research notes: [rules_power_rf_analog_dfm.md § 1, § 17](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [interface_rule_packs.md § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
- Keithley, *Making Precision Low Voltage and Low Resistance Measurements*, Table 1: https://xdevs.com/doc/Keithley/Appnotes/LV_LR_e-hnbook_91113.pdf [P]
- LearnEMC trapezoid harmonics: https://learnemc.com/ext/calculators/trapezoid_harmonics/index.html [S]
- Scripts: [vo_numbers.py](../../../tools/research/physics/vo_numbers.py), [vo_return_spread.py](../../../tools/research/physics/vo_return_spread.py), [vo_ir_check.py](../../../tools/research/physics/vo_ir_check.py)

See also: [physics-ir.md](physics-ir.md), [vocabulary.md](vocabulary.md), [worked-thought-experiments.md](worked-thought-experiments.md), [../rules/power/hot-loops.md](../rules/power/hot-loops.md), [../rules/precision-sensing.md](../rules/precision-sensing.md)
