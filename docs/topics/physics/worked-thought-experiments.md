# Worked thought experiments: physics-first vs rule-following on four boards

**TL;DR**
- In all four cases the physics-first answer differs from the rule-following one where it matters, and agrees elsewhere with a reason and a number attached. The difference usually comes from **asking which output binds** before drawing anything [I].
- **12 V buck + MCU + USB 2.0 + crystal:** choose a 0.1 mm prepreg and GND/GND inner layers; the hot loop leads (τ ≈ 1.7). USB skew is an EMI budget (1.27 mm → ~3 mV common-mode spikes), not a timing one. The crystal needs only ~2–3 mm from switch copper on this stackup [C].
- **48 V half-bridge:** with 15 ns edges, overshoot does not bind. What binds is common-mode current through the heatsink (~22 pF, ~71 mA pulses) and a shunt sitting inside the hot loop (1.3 V spikes on a 40 mV signal). Bond the heatsink to DC−, and move the HF capacitor return above the shunt [C, I].
- **24-bit ADC beside a buck:** the dominant couplings are DC plane gradients (µV/mm, hundreds of LSB) and thermal EMF along ∇T, not distance from the switcher. The fixes are measurement-loop topology and isotherm-aligned parts. Over a solid plane, magnetic coupling at 5 mm is already ~400× below the free-space value [C].
- **2.4 GHz chip antenna:** the ground plane is part of the antenna, and clock harmonics need 58–70 dB isolation. Slew-rate and frequency plans come before geometry; corners don't matter at 2.4 GHz over a 0.1 mm dielectric, though they do on a 1.5 mm two-layer board [C].

## Key facts

Numbers tagged [C] come from [dr_switch_cell_budget.py](../../../tools/research/physics/dr_switch_cell_budget.py), [dr_coupling_oracles.py](../../../tools/research/physics/dr_coupling_oracles.py) and [dr_noise_adjoint.py](../../../tools/research/physics/dr_noise_adjoint.py), under the conditions stated there. Each case ends with what the reasoning layer hands the joint optimizer ([joint-place-route](joint-place-route.md)), what comes back, and how the binding constraint is explained. Optimizer return values are illustrative [I]. The method is in [design-reasoning-architecture](design-reasoning-architecture.md) and [schematic-to-physics](schematic-to-physics.md).

### A. 12 V → 3.3 V buck, MCU with a USB 2.0 HS PHY, 24 MHz crystal, 4 layers, fixed USB-C

**Setup.** 50 × 35 mm board; USB-C fixed mid-right edge; a 2-pin 12 V input the optimizer may place; integrated 2 A synchronous buck at 0.3 A load.

**Rule-following answer.** Fab-default stackup (0.2 mm prepreg), SIG/GND/PWR/SIG; connectors on one edge; buck near its load; CIN < 2 mm; crystal ≤ 5 mm from the MCU, well away from the switcher; USB 90 Ω ±15 %, skew ≤ 1.27 mm, TVS near the connector ([usb2](../rules/interfaces/usb2.md), [buck](../rules/power/buck.md), [crystals-clocks](../rules/crystals-clocks.md)).

**Physics-first reasoning.**
1. **Ports and energy flow.** Two cables are the efficient antennas below ~100 MHz. About 1 mV of common-mode voltage between their references can fail Class B ([emc-placement](../rules/emc-placement.md)) [S]. So no HF current may cross the plane between the two connector grounds. Put the 12 V input on the USB edge (agreeing with the rule) and the buck *at the 12 V input*, not at the load. Carrying 0.3 A of 3.3 V across the board costs 4.4 mV (30 squares of 1 oz copper) against a 99 mV (3 %) budget. A hot loop near the USB reference costs EMI margin [C].
2. **Stackup from budgets.** For wide strips the lateral loop inductance scales with h. A 0.1 mm instead of 0.2 mm prepreg halves the hot loop's lateral part, cuts the crosstalk factor at 1 mm spacing from 0.038 to 0.0099, and narrows the 90 Ω pair (check the fab minimum) [C]. Ask for it if the fab offers it at no premium [I].
3. **Plane roles.** Use GND on L2 and L3 and a 3.3 V pour on L4. The 1.1 mm core gives a plane pair of only 3.5 pF/cm² (~60 pF), irrelevant to decoupling, while GND/GND lets every via return through a ground via [C].
4. **τ ranking.**
   - Hot loop: budget 1.05 nH (17 V peak at 13.2 V in) [C]; floor ≈ 0.6 nH (package ~0.3 nH plus a 0402 C_IN over 0.1 mm) [I]. τ ≈ 1.7, so it is tier 1 with an N7 seed.
   - TVS ground: at 30 A/ns (IEC 61000-4-2, 8 kV contact: 30 A, 0.8 ns) a via to L2 0.1 mm down (~0.03 nH) adds 0.8 V; a via through to L4 (~1.3 nH) adds 39 V [C]. Tier 1, cheap.
   - USB: 25 mm is ~150 ps against a 300–500 ps edge, so impedance tolerance hardly moves the eye [C]. Skew does matter for EMI: 1.27 mm (7.6 ps) gives ~3 mV common-mode spikes, 0.25 mm gives 0.6 mV [C]. Tighten skew, relax impedance.
   - Crystal: 1 pF of stray pulls about 45 ppm (ST, [crystals-clocks](../rules/crystals-clocks.md)) against USB HS's ±500 ppm, so pull does not bind. SW-node injection does: a 3 mm exposure at 1 mm gap gives 2.1 mV on XIN; a 3 mm gap gives 0.24 mV. On a 2-layer board the same numbers are 69 mV and, at 6 mm, 5.8 mV [C]. With a 1 mV budget the gap is ≥ 1.5 mm, so τ is large and the crystal follows the MCU pins.

**Hand-off.**

| To the joint optimizer | Back (illustrative) |
|---|---|
| ports: USB-C fixed; 12 V connector on an edge; CM proxy between connector references ≤ budget | hot loop 0.82 nH (78 % spent, binding) |
| hot loop ≤ 1.05 nH, tier 1, seed template; no plane voids under it | crystal coupling 0.3 mV (30 %) |
| TVS ground via ≤ 0.1 nH, TVS between connector and PHY | USB skew 0.2 mm (80 %) |
| USB skew ≤ 1.5 ps, ±15 % impedance soft | price: 0.1 nH of hot loop ≈ 2 mm² near U3 |
| crystal C_m ≤ 1.7 fF to SW copper (1 mV); GND/GND, 0.1 mm prepreg fixed upstream | |

Explanation: "C_IN is 0.4 mm from U3 because the 1.05 nH hot-loop budget binds. Moving the crystal 1 mm closer to the MCU would cost 0.04 nH, which we have."

### B. 48 V half-bridge motor driver with a heatsink and a low-side shunt

**Setup.** One leg of a 3-phase inverter: 54 V maximum, 20 A phase, 100 V FETs in TO-220 on a heatsink fixed along one edge, 2 mΩ low-side shunt, 20 kHz PWM, 15 ns edges.

**Rule-following answer.** FETs on the sink, ceramics plus bulk at the FETs, shunt from LS source to GND with Kelvin net ties, gate traces ≥ 20 mil, switch node short and wide, smallest possible loop, heatsink to chassis ([motor-drivers](../rules/power/motor-drivers.md), [current-sense-kelvin](../rules/power/current-sense-kelvin.md)).

**Physics-first reasoning.**
1. **Which output binds?** At 10–20 nH (typical for TO-220 leads plus capacitors) the switch-node peak is 71–73 V against 80 V allowed, and overshoot does not bind anywhere up to the model's 40 nH limit [C]. Loop inductance still matters through its ring at 45–63 MHz [C], inside the 30–100 MHz band where cables resonate. Its budget must come from the EMI output, not from voltage stress.
2. **Heatsink as a capacitor.** The LS FET's tab is the switch node. Over a 0.2 mm pad it has ~22 pF to the sink, and 48 V in 15 ns drives ~71 mA pulses through it [C]. Bonded to chassis, those pulses return through the motor and supply cables. Physics-first bonds the sink to DC− at the bridge with a short, wide strap, or uses an insulator with a shield layer tied to DC−, so that the displacement current closes inside the power cell. Any chassis tie then goes through a defined capacitor, if the product standard needs one [I]. The rule says "ground the heatsink"; physics says which node.
3. **Shunt inside the hot loop.** A 1 nH shunt ESL at 1.33 A/ns puts 1.33 V spikes on a 40 mV signal (20 A × 2 mΩ) [C]. If the gate driver returns below the shunt, the same 1.3 V subtracts from a 10–12 V gate drive as common-source inductance [C]. Proposal [I]: return the HF ceramic to the LS source node *above* the shunt and Kelvin the driver return at the FET source pin. The commutation current then circulates without crossing the shunt, which carries the phase current at the slower rate set by the ceramic–bulk loop. Trade-off: the ceramic's recharge current passes through the shunt, so sample mid-PWM after it settles. Test both arrangements in SPICE: sense error at the sample point, overshoot, shunt di/dt.
4. **Thermal.** The shunt dissipates 0.8 W. A 1 % accuracy budget is 400 µV, so thermal EMF (µV) does not bind here, but TCR and self-heating do. Give the shunt a copper heat path; its symmetry is a minor term. Contrast case C.

**Hand-off.** Devices constrained to the heatsink line. Discrete choices: capacitor return node (above or below the shunt) and heatsink bond node. Budgets: common-mode current through the sink and the ring amplitude at 45–63 MHz (EMI proxy), sense spike ≤ blanking window, gate common-source inductance ≤ 0.3 nH. Tier 1: sense integrity and heatsink bond; loop inductance is tier 2.
**Back (illustrative):** with a chassis bond the CM budget is infeasible (certificate: heatsink capacitance × dv/dt alone exceeds it). With a DC− bond it passes at 40 % spent; loop inductance 12 nH.
**Explanation:** "The heatsink is bonded to DC− because the chassis option cannot meet the CM budget at any geometry. The loop is 12 nH, not smaller, because overshoot never binds; the area went to the gate loop."

### C. 24-bit ADC next to a switching supply

**Setup.** ADS1262-class ADC with a bridge sensor at gain 32: ±78 mV full scale, 9.3 nV LSB, datasheet noise 7 nV rms at 2.5 SPS ([TI](https://www.ti.com/product/ADS1262/datasheet)) [S]. A 500 kHz buck losing 0.4 W, 0.3 A of digital return, 60 × 40 mm, 4 layers.

**Rule-following answer.** Split or partitioned AGND/DGND, ADC ≥ 20 mm from the switcher (no primary source, per [rf](../rules/rf.md)), star ground, guard rings, filter at the ADC ([analog-mixed-signal](../rules/analog-mixed-signal.md), [precision-sensing](../rules/precision-sensing.md)).

**Physics-first ranking.**
1. **DC plane gradient.** 0.3 A across a solid 1 oz plane gives 0.7–4.6 µV/mm everywhere on this board [C]. A measurement that references the plane at two points 3 mm apart sees 2–14 µV, i.e. 230–1,500 LSB. Distance cannot fix that; topology can. Make the measurement fully differential and ratiometric (AINP/AINN and REFP/REFN Kelvin-routed to the bridge), so the plane drop is common mode and the ADC's CMRR rejects it. Optionally add a current-free peninsula with the ADC at its neck: the interior gradient falls from 2.0 to 0.017 µV/mm (~120×). The neck must be narrow, because a 4 mm neck still admits circulating current [C]. This is ADI's "≥14 bits: isolated region tied under the converter", decompressed.
2. **Thermal EMF.** The buck's 0.4 W makes an in-plane gradient of 0.21 K/mm at 10 mm and 0.09 K/mm at 20 mm (fin model, two 1 oz planes) [C]. An 0603 aligned with the gradient at 10 mm spans 0.34 K: 0.3–1 µV at 1–3 µV/K for copper–solder ([Keithley handbook](https://docs.ampnuts.ru/eevblog.docs/Keithley/Ch3_LowLevMsHandbk.pdf)) [S]. That is 37–110 LSB per resistor before P/N cancellation. The new constraint: orient input-path resistors perpendicular to ∇T, and mirror P and N about an axis parallel to ∇T so both legs sit on the same isotherms [I].
3. **Magnetic coupling at f_sw.** The budget is M ≤ 1.7 pH at the 500 kHz fundamental, before the digital filter [C]. Between a 6 × 3 mm lateral hot loop and a 10 × 1 mm input loop at a 5 mm gap, M is 13 pH in free space but 0.03 pH with a plane 0.1 mm under both [C]. Over a solid plane 5 mm suffices; on 2 layers or over a void you need > 20 mm (0.9 pH free space). The digital filter rejects f_sw strongly except near multiples of the modulator rate, so frequency-plan or synchronize the buck so no harmonic lands in an alias band [I].
4. **Electric coupling.** C_m ≤ 0.23 fF at the ADC pins and 2.9 fF on the sensor side (before digital filtering) [C]. A 3 mm gap with 3 mm exposure on 0.1 mm prepreg gives 0.4 fF [C], so keep switch copper ≥ 5 mm from ADC-side nodes, or count on the alias argument.

The ranking, DC gradient ≫ thermal > magnetic ≈ electric (only in alias bands), puts the effort into measurement-loop topology and isotherms. The ADC may sit about 10 mm from the buck over a solid plane, where the 20 mm rule would forbid it.

**Hand-off.** Kelvin and differential topology as hard structures; peninsula yes/no and f_sw plan as discrete alternatives; orientation constraints relative to the ∇T field, re-solved each round by the thermal estimator; M and C_m budgets per path.
**Back (illustrative):** isotherm alignment binds against short routing (price: 3 mm extra on AINN). Peninsula chosen.
**Explanation:** "R12/R13 are rotated 90° from the obvious route because the buck's gradient (0.2 K/mm here) would put 0.3 µV across each."

### D. 2.4 GHz radio with a chip antenna fixed at one corner

**Setup.** BLE SoC with an on-chip DC-DC, chip antenna fixed at a corner of a 50 × 30 mm 4-layer board, SPI flash clocked at 48 MHz, 3.3 V logic.

**Rule-following answer.** Follow the antenna and SoC reference layouts: keep-out, 50 Ω CPWG, match at the pin, via fence, arcs on RF corners, switcher "20 mm away" ([rf](../rules/rf.md)).

**Physics-first reasoning.**
1. **The board is the antenna.** A chip antenna excites the ground plane, and the plane's dimension near λ/4 (~31 mm at 2.45 GHz) is part of the radiator. Vendor efficiencies depend on the test board: Taoglas PCS.25.A gives 52 % with clearance and 31 % without on 50 × 50 mm; Abracon gives 69 % off-ground and 57 % on-ground. Taoglas recommends the long-side mid-point, while others choose corners ([Taoglas](https://www.taoglas.com/datasheets/PCS.25.A.pdf), [WLA.04](https://www.taoglas.com/datasheets/WLA.04.pdf)) [S]. With the corner fixed, the variable is the plane: keep the edge strip running away from the feed continuous (no slots, connectors or tall metal), and keep the plane length close to the reference board's.
2. **Lines and corners.** λ_g ≈ 68 mm on outer-layer microstrip (ε_eff ≈ 3.2), so λ_g/20 ≈ 3.4 mm [C]. A 2–3 mm feed is nearly lumped. With L2 0.1 mm below, a bend matters only above ~14 GHz; on a 1.5 mm two-layer board it reaches −20 dB near 2–2.6 GHz, so the arc rule is real there ([rule-genealogy-si-emi-rf](rule-genealogy-si-emi-rf.md)) [C]. Curves buy nothing on this board.
3. **Desense.** The 51st harmonic (2.448 GHz) of a 3.3 V, 48 MHz clock is about −35 dBm-equivalent with 1 ns edges and −47.5 dBm with 4 ns edges [C]. Holding the antenna port at −105 dBm, 10 dB under a ~−95 dBm BLE sensitivity [I], needs 58–70 dB of isolation. USB HS would add 5 × 480 MHz = 2.400 GHz at the band edge. So the first levers are firmware and schematic: GPIO slew (−12 dB for 4× slower edges) and the clock plan. Then geometry: the flash clock short, on L1 over solid L2, away from the antenna-side plane edge.
4. **Reference designs are measured physics.** For the SoC's DC-DC inductor and RF pins, copy the vendor layout and verify it; don't re-derive it ([layout-reuse](../workflow/layout-reuse.md)).

**Hand-off.** The antenna as a radiator object with its keep-out and a protected plane-edge strip (hard); the plane length as a soft target; spur budgets in dB per clock net, converted by a coupling oracle into distance and layer limits; slew setting as a discrete alternative.
**Back (illustrative):** flash-clock isolation binds at 4 dB margin with 1 ns edges and passes at 16 dB with slow slew.
**Explanation:** "We set the SPI GPIO to slow slew. It buys 12 dB of desense margin and frees the flash to sit 6 mm closer to the SoC."

### Where the answers diverge

| Case | Rule answer | Physics-first answer | Why it is better |
|---|---|---|---|
| A | fab-default prepreg, PWR plane | 0.1 mm prepreg, GND/GND | halves the hot loop, 4× less crosstalk, free |
| A | skew 1.27 mm, Z ±15 % strict | skew 0.25 mm, Z soft | skew drives cable CM; impedance barely matters at 25 mm |
| B | heatsink to chassis | heatsink to DC− at the bridge | closes the 71 mA displacement current locally |
| B | shunt in the loop as drawn | HF cap return above the shunt | removes 1.3 V spikes and common-source inductance |
| C | ≥ 20 mm and split ground | differential/Kelvin topology, isotherm alignment, ~10 mm | fixes the actual dominant errors |
| D | geometry first | slew and frequency plan first | 12 dB from one register bit |

## Recommendations for our system

1. Turn the four cases into synthetic benchmark boards with the reasoning layer's expected hand-off as a golden file; score whether the system finds the binding output ([benchmark-plan](../verification/benchmark-plan.md)) [I].
2. Ship oracles for plane DC flow, loop mutual inductance with images, K-factor capacitance, trapezoid envelopes and fin-model gradients as T0 spend models [C demo].
3. Make discrete non-geometric levers (prepreg, plane roles, bond node, capacitor return node, slew, f_sw) first-class decision variables in the hand-off [I].

## Conflicts and open questions

- Case B's capacitor-above-shunt proposal is untested and may conflict with single-shunt or three-shunt reconstruction schemes; it needs a SPICE and bench comparison.
- Case C's isotherm rule assumes resistor thermal EMF of the copper–solder order; foil and thin-film parts differ. The fin model ignores components and airflow.
- The ~1 mV cable common-mode threshold is a LearnEMC sinusoidal heuristic; applying it to 500 ps skew spikes is our inference.
- Optimizer return values are illustrative until [joint-place-route](joint-place-route.md) exists.

## Sources

- research notes: [rules_power_rf_analog_dfm.md § 7, § 19](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)
- IEC 61000-4-2 waveform ([Wikipedia](https://en.wikipedia.org/wiki/IEC_61000-4-2)) [S]; USB 2.0 HS rise time ([USB-IF compliance spec](https://www.usb.org/sites/default/files/USB2%20Electrical%20Compliance%20Specification%20v1.08.pdf), [TI TUSB1210](https://www.ti.com.cn/document-viewer/cn/lit/html/ZHCSKM0J/GUID-1003578D-34E0-47DB-BF8D-514B4C9072EC)) [S]
- heatsink common-mode coupling ([Altium](https://resources.altium.com/p/emi-heatsinks-and-what-you-can-do-about-it)) [S]

See also: [design-reasoning-architecture](design-reasoning-architecture.md), [schematic-to-physics](schematic-to-physics.md), [reasoning ideas](../../ideas/physics-first/reasoning.md), [hot-loops](../rules/power/hot-loops.md), [emc-placement](../rules/emc-placement.md)
