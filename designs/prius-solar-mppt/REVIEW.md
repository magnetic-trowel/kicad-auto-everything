<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Prius Prime solar MPPT charger: independent design review

Reviewer: independent HV/automotive review (LLM), 2026-10-23. Scope: design v0.2 as committed (`DESIGN.md`, `CONNECTIONS.md`, `parts.py`, `design.py`, `out/`). Datasheets were re-read from TI/Microchip PDFs. Citations give the datasheet revision and table.

## Verdict

**Not ready for layout, and not to be connected to a car.** The pinouts I checked are correct, the numbers in the arithmetic chain (L1/L2/L3, UVLO, ISNS sink direction, PERMIT levels) are correct, and the battery-end topology does what the brief asks. Two things block the design:

- The HV-to-chassis insulation was never designed. The board bottom and HV parts are pressed onto a chassis-bonded thermal pad, and no rule checks that path.
- The hardware overvoltage thresholds are fixed resistor values derived from an *inferred* cell window.

Seven major findings follow. The most important: the LM5176 is CCM-only, so it can run power backwards. The CAN node is clocked from a ±2 % RC oscillator. Nothing monitors insulation while the car sleeps. The hardware pack over-temperature trip is blind to an open sensor. Several "single-fault safe: yes" claims in the hazard table do not hold.

Counts: **2 BLOCKER, 7 MAJOR, 9 MINOR.**

## BLOCKER

### B1. HV-to-chassis insulation is not designed. The placement intent puts HV copper on a chassis-bonded pad.

- **What.** `boards()` says: *"thermal pad under the FETs, T301 and the bridge"*. `placement()` ends with `pl.side("all","top", note="… bottom flat on the thermal pad")`. The box is "bonded to chassis". The bridge diodes D301–D304 sit on that pad. Their TO-277A cathode tabs are HV_P / T1_S1 / T1_S2, up to 421 V. So do these through-hole parts, whose leads come through the bottom: T301 secondary pins 11/20, J301 (HV_P/HV_N/PACK_SNS) and every HV via. H705/H706 are M3 screws into the chassis-bonded box, placed *in the HV section* (x = 195 mm). The only spacing note is "≥ 10 mm from LV copper" (`mcu()`), which is the wrong reference.
- **Evidence.** `out/prius-solar-mppt.kicad_dru` has rules only between copper netclasses (LV/HV/PACK). Chassis is not a domain, and the enclosure, screws and thermal pad are not objects. The 8/10 mm LV↔HV rule therefore says nothing about HV copper → pad → box. The HV system floats (an IT system), so HV-to-chassis must carry at least basic insulation for 420 V working. That is 5.0 mm creepage (the design's own F.4 500 V row) plus an insulation-rated thermal interface.
- **Consequence.** One cut in the pad, or one THT lead tip piercing it, connects HV to chassis. That is the first insulation fault, and nothing detects it while parked (see M3). An auto-placer that follows this intent will put the bridge and T301 on the pad.
- **Fix.**
  - Add a CHASSIS domain and an HV↔CHASSIS (and PACK↔CHASSIS) barrier: basic, ≥ 5 mm creepage and clearance to enclosure, screws and pad.
  - Ban HV copper and vias on the bottom layer over the pad. Keep HV through-hole parts out of the pad footprint, or specify a rated insulating pad (thickness, kV, creepage at its edge).
  - Keep D301–D304 on copper only, as `pl.thermal(…,"copper")` already says. The enclosure note contradicts this.
  - Move H705/H706 out of the HV section, or use insulating standoffs. Re-run the build so the DRU carries the new rules.

### B2. The safety thresholds rest on an inferred cell window, and the resistors cannot be calibrated.

- **What.** L2 (380.0 V = 4.00 V/cell), L3 (391.6 V = 4.12 V/cell, max 4.159), L2b and the firmware stop all come from ASM-2/ASM-3, which are tagged [I]: NMC 3.00–4.20 V, car full charge "~4.10 V/cell". HZ-4 argues that "our stop is below the car's own full charge", so every cell ends below a normal plug-in charge. That argument holds only if the car really charges to about 4.10 V.
- **Evidence.** I found no Toyota or teardown source for the Prime's top-of-charge pack voltage or its maximum cell voltage. Argonne's teardown confirms only 95 cells (19 × 5), 351.5 V and 25 Ah (https://www.anl.gov/taps/d3-2017-toyota-prius-prime). The one Prime scanner anecdote I found is inconsistent with the design's numbers (PriusChat, unverified). Toyota PHEVs commonly use a narrow window. If the car's own maximum is about 4.0–4.05 V/cell, then:
  - L2 sits at or above it;
  - L3 (up to 4.159 V) sits above it;
  - the HZ-4 margin "≥ 150 mV below the car" becomes negative.
- **Consequence.** The firmware-independent layers would let a firmware fault park the pack above Toyota's own limit, every sunny day, without the BMS awake. V-18 calibrates only the firmware layer (L1). L2 and L3 are fixed by R802/R803, the U402 gain and R502/R503.
- **Fix.** Before any HV connection:
  - log the Prime at the end of a full plug-in charge with Techstream or OBD: pack voltage, max cell voltage, displayed SOC;
  - set L3 at or below the car's own measured maximum, and L2 one step lower;
  - put the measured numbers in the IR, with the [P] tag, and rebuild.
  - Consider a one-time-trim resistor position for VREF_CV and VTH2V0.

## MAJOR

### M1. The LM5176 is CCM-only. Its CC loop discharges SS, which makes it run backwards into a blocked input.

- **Evidence.** SNVSB46B Table 5-1: MODE selects only "CCM, hiccup enabled/disabled" (R11 = 93.1 kΩ). There is no DCM or diode-emulation option. The ISNS loop *"starts discharging the soft-start capacitor"* (pin 13/14 description), and SS is the error-amplifier reference (§7.2 block diagram).
- **What happens.** Whenever the setpoint asks for ≤ 0 A (I_sink ≥ 50 µA), SS is pulled toward 0 V. That covers the default "stop" (VSET high), the limiter cutting power (LIM → VSET), and MPPT perturbation near zero on a shaded string. VINT is still about 34 V, so the voltage loop commands minimum COMP, and a CCM 4-switch stage then drives negative inductor current. Energy goes from VINT (and from the other channel, if it is still sourcing) into PVx_P.
- **Why it matters.** PVx_P is behind the LM74700, so the energy cannot return to the string. PVx_P has no clamp: the TVS D101 is on PVx_IN. It rises until U104's PV loop (target 12 × VSET, up to 39.6 V) reverses the action.
- **Consequence.** Circulating power between the channels, PV-node overvoltage toward the LM74700 CATHODE and LM5176 VIN ratings, and limiter behaviour that differs from the model. The `rating.voltage` waiver for U101/U201 says "PVx_P is fed only by its string … no back-feed path from VINT". That is false while the stage is switching.
- **Fix.**
  - Clamp the current setpoint at ≥ 0: limit the Q102 sink to 50 µA minus margin, so the CC loop never asks for negative current.
  - Add a TVS or clamp on PVx_P.
  - Disable the channel (EN) rather than commanding zero current. For example, LIM above a threshold pulls EN.
  - Simulate the stop and limiter transients in V-21 before the PCB.

### M2. The CAN controller runs from the internal FRC (±1.5–2 %), which is outside CAN timing tolerance.

- **Evidence.** `mcu()` notes "FRC + PLL". The OSCI/OSCO pins RB0/RB1 (pins 21/22) carry NTC_HS and NTC_P3, so no crystal can be fitted. DS70005349K Table 33-23, F20a: FRC ±2 % (−40…−5 °C), ±1.5 % (−5…85 °C).
- **Requirement and risk.** A 500 kbit/s vehicle bus needs a clock tolerance well under 1 %. While IG is on, the transceiver is enabled. A mis-clocked node sends active error flags as a *receiver*, destroying other ECUs' frames until it goes error-passive. If the DLC is not gatewayed, that is the car's powertrain/diagnostic bus. HZ-19 ("cannot disturb the car") does not hold while IG is on.
- **Fix.** Fit a crystal or AEC-Q oscillator: move NTC_HS and NTC_P3 to spare analog pins (46–48 are free). Default the CAN FD module to Listen-Only mode, and enter Normal mode only for a request/response window.

### M3. Nothing monitors insulation on our HV cable and board while the car is asleep.

- **What.** HZ-7 relies on "the car's monitor sees our circuit when both are on". Our relays close only when we charge. Most of our charging happens with the car off, when the car's insulation monitor is not running. At night the relays are open, so the car never sees our cable at all.
- **Consequence.** A first insulation fault in W3, J301/J901 or the main board can sit undetected for weeks. Our own charging adds hours per day of HV on our cable with no monitoring. The second fault is a shock or arc hazard.
- **Fix.** Before closing K902/K901, measure HV_N and HV_P to chassis with the converter off. A switched high-value (≥ 2 × 5 MΩ) divider through an isolated amplifier, or a third AMC path, would do. Refuse to close below 500 Ω/V. Log the reading. Keep the measurement switched out the rest of the time so it does not load the car's insulation monitor.

### M4. The hardware pack over-temperature trip fails unsafe on an open sensor or a disconnected harness.

- **Evidence.** R512/R513 pull NTC_P1/P2 up to VREF2V5, with the NTC to GND through 2 m of harness (J706/W5). U502 ch4 and U506 ch2 trip when the node falls below VTH_OTP (0.729 V). An open NTC, cable or connector reads 2.5 V, which looks cold, so the trip can never fire.
- **Consequence.** The common harness fault disables both "hardware OTP 50 °C" sensors at once. HZ-15 is marked single-fault safe "yes", but only firmware catches an open sensor.
- **Fix.** Add a second comparator per channel (node > ~2.3 V = open) into PERMIT. Alternatively, put the NTCs on the high side so that an open sensor reads hot. Route the two hardware NTCs through separate connector pins and cable cores from the firmware ones.

### M5. Pack-live connections on pluggable PCB headers, with no HVIL.

- **What.** J902 (Phoenix GMSTBA 2,5, 1766343) carries BAT_TAP_P/N. These are the pack terminals, unswitched and behind only the 5 A fuses. J901 pin 2 is the pack negative whenever K902 is closed. The header rating used is "IEC 630 V (III/2); UL 300 V [unverified]". The install guide (HZ-17) has a person unplug J902 at full pack potential.
- **Missing.** There is no HV interlock loop. No connector is rated for automotive HV (IPXXB when unmated, a tool needed to open, vibration/IP67 retention).
- **Fix.** Use a proper automotive HV connector with HVIL, or a terminal block inside a tool-opened cover. Wire the HVIL in series with the relay coils, so that opening the box or unplugging drops K901/K902. Write the service procedure around the car's service plug, not ours.

### M6. The DCX is neither hardware-bounded nor well defined.

- **Firmware-only frequency.** The half-bridge frequency comes from MCU PWM1H/L, and there is no hardware primary current limit (the UCC27282 has none). HZ-11 says "DCX open loop and bounded". If corrupted firmware keeps feeding the watchdog but runs PWM1 at, say, 20 kHz, then Bpk = 0.095 T × 95/20 ≈ 0.45 T, which is above N97 saturation at temperature. The current is then limited only by the 3.2 µF of Cr and the FET resistance.
- **Lr is not credible as leakage.** §7.3 sets fr with Lr = 0.8 µH "T301 leakage plus trace (±30 %)". My estimate for 4 primary turns on ETD39 with a triple-insulated-wire secondary is about 0.15–0.3 µH. That gives fr ≈ 160 kHz, so fsw/fr ≈ 0.6 rather than 0.95, with higher peak and rms currents than §7.3/§7.10 assume.
- **Fix.**
  - Specify Lr as a discrete part, or as a controlled leakage in the T301 specification, with a tolerance.
  - Add a primary current sense (a CT or a shunt in the low-side source) into a comparator → OVP_TRIP_N.
  - Bound the frequency in hardware, for example with a fixed oscillator gated by PERMIT, or a frequency-window check.

### M7. The "latched until next dawn" trip actually clears on any +3V3 brownout, and dawn and dusk will cycle the relays.

- **Latch.** U503 ~CLR = RESET_N, from the TPS3850 sensing +3V3. +3V3 comes from PV only. A cloud, shading or dusk that drops AUX12 (from the PV OR, LM5164 EN off at about 11.1 V) clears the latch, and the system retries at the next upturn. §7.4 and HZ-3 describe a once-per-day latch.
- **Relays.** Relay pull-in is 2 × 2.8 W on AUX12, fed from one string at dawn irradiance. The OCV step closes K902 then K901 at dawn, which can collapse AUX, reset the MCU and repeat. That is daily relay cycling at 380 V (zero current, but G9KB life is 100 k operations) and an EEPROM log flood.
- **Fix.** Hold the latch with a supercap-backed supply, or store the trip in EEPROM and have firmware refuse to restart without a dawn-to-dawn gap. Add a hardware power-good: require string power (for example AUX_IN > 18 V under a dummy load) before RELAY_REQ can act. Also add a PV energy budget check in firmware.

## MINOR

1. **L2b is not a cell backstop.** The VINT ceiling of 396 V nominal spans 390–418 V across tolerance (§7.2), which is 4.11–4.40 V/cell. Don't list it as "the backstop if both AMC paths fail" (§7.2, §7.4 table). It limits the output with no pack connected, nothing more.
2. **The UVLO margin is nominal only.** With the SNVSB46B §6.5 spreads (VEN(OP) 1.17–1.29 V, IEN(STBY) 1–3 µA, ΔIHYS 2.15–4.25 µA), R107/R108 give an on-threshold up to 13.9 V and an off-threshold up to 10.7 V. That is above the 9.9 V shaded-hot Vmp, so `uvlo_off_vs_shaded_vmp = +3.05 V` becomes −0.8 V at the corner. Lower R107, or compute the check at the corners.
3. **Path 1 is a 9 MΩ node across 2 m of cable and two connectors.** Leakage from the PACK_SNS core to HV_N or the screen makes it read *low*, which is the unsafe direction for L2. L3 (path 2, on the main board) still bounds it, and the 5 V cross-check is firmware only. Consider guarding the PACK_SNS core and having the limiter use min(path 1, path 2).
4. **The hysteresis resistors shift the firmware readings.** R511/R523 (330 kΩ, from PERMIT to NTC_P1/P2) move the ADC reading by about 45 mV (~1 K) depending on PERMIT. Firmware must compensate, or the hysteresis should come from a separate node.
5. **Low-level margins at −40 °C.** In the latched state PERMIT = Vf(D501) ≈ 0.4–0.45 V. K_IN = PERMIT + Vf(D503) ≈ 0.65 V, against the TPL7407 VIL of 0.9 V (SLRS074 §6.5). U301 sees 0.45 V against VDIS min 0.7 V (SLUSDN5D §6.5). These pass, but the 108 µA budget in §7.9 covers only the R519 case, not the latch path. Recompute at cold.
6. **Temperature compensation and the meaning of "80 %".** Temperature compensation exists only in firmware: the hardware CV (4.00 V) is the same at 45 °C as at 10 °C. "80 %" is not defined (car display or true SOC). With firmware wrong but alive, L2 will hold the pack at 4.00 V/cell under CV indefinitely, which is likely above 80 % true SOC. State this plainly in REQ-7/8.
7. **Waiver text, U101/U201 V(CATHODE-ANODE).** The conclusion (≤ 33 V with the string reversed) holds, because the stage cannot start without VIN. The stated reason ("no back-feed path from VINT") is wrong; see M1.
8. **The vehicle facts are only partly re-verified.** ANL confirms 95 cells (19 × 5), 351.5 V and 25 Ah. The Toyota dismantling manual pages cited as [P] (relays on both cables, the solar warning) are behind a login, and I could not re-read them. The SMR, current-sensor and service-plug positions remain Q-4/Q-11. Also, a tap on the *cell side* of the SMRs means opening the sealed pack case and adding a penetration. Q-5 should say this explicitly.
9. **Fit to the brief: the roof was not measured.** The brief asked to "measure the size of the roof". The 1016 × 889 mm field is inferred from Toyota's 0.8 m² PHV panel (ASM-1, Q-3 blocking). The 0.30 A cap also discards about 25 % of the array's best-day output. That is the right trade-off, but the user should be told.

## Waivers in out/report.md

| Waiver | Verdict |
|---|---|
| LM74700 GATE/VCAP–ANODE 13.9 V | OK: internal charge pump (SNOSD17G 6.1/6.5) |
| LM74700 CATHODE–ANODE 66 V | Conclusion OK, reasoning wrong (MINOR 7) |
| LM5176 SS/COMP/VCC/BOOT | OK: pins driven by the IC itself |
| LM5164 BST–SW, dsPIC VDD | OK |
| AMC package creepage 8 < 10 mm | OK: CTI ≥ 600 V, material group I, CLR/CPG ≥ 8 mm (SBASA35B §5.7). This needs the slot to extend past the package ends. |
| Custom footprints (T301, EVM10-2P, G9KB) | Acceptable as a waiver, but **blocking for layout**: G9KB pin numbering is not verifiable from the catalogue I could reach |
| entry_fuse HV_P/HV_N/PACK_SNS | OK: fused at the battery end; D901 blocks |
| entry_fuse PV | OK: single string per input |
| HGND ERC | OK |

## Situations checked

- **Sunrise, car off:** works, but relays may chatter (M7). The OCV step is sound: the weld check logic works because BE_DK floats with K901 open.
- **Full pack:** L1 stops first if firmware is right. L2 and L3 are only as good as B2.
- **Sensor open or shorted:** AMC open input → reads 0 → L2 blind, L3 covers. Path-2 top resistor open → L3 blind, L2 covers. NTC open → hardware OTP blind (M4).
- **MCU hung:** the TPS3850 window watchdog (SET0 = SET1 = 0, CWD 10 kΩ → 9–109 ms, SBVS264B §6.6) resets the MCU through WDO → R517 → MCLR. R519 then pulls PERMIT low. Verified. A hang that keeps feeding the watchdog is covered by L2/L3, except for M6.
- **Harness short:** HV_P–HV_N is blocked by D901. With D901 shorted, F901 (EVM10-5, 20 kA) clears. A resistive 5–15 A fault with D901 shorted would not clear (a double fault).
- **Chassis contact on the HV side:** a single fault, undetected while parked (M3); B1 makes it more likely.
- **Car's charger running:** our L2 backs off at 380 V. L3 can nuisance-trip if the car charges above about 388 V while we run. That fails safe.

## Verified correct

- **Pinouts against datasheet and footprint pads:**
  - LM5176 PWP 1–28 (SNVSB46B Fig. 5-1)
  - LM74700 DBV (SNOSD17G Table 5-1)
  - UCC27282 DRC 1 VDD, 2 NC, 3 HB, 4 HO, 5 HS, 6 EN, 7 HI, 8 LI, 9 VSS, 10 LO (SLUSDN5D Fig. 5-1)
  - AMC3330 and AMC3302 DWE 1–16, including 13 LDO_OUT and 14 DIAG (SBASA35B Table 4-1; AMC3302 Fig. 5-1)
  - TPS3850 DRC (SBVS264B Table 5-1)
  - INA186 DBV 1 GND, 2 OUT, 3 VS, 4 IN−, 5 IN+
  - LM5164 DDA
  - TPL7407LA PW
  - SN74LVC2G74 DCU
  - LM2901 comparator pairing (pin 1 ↔ 6/7, pin 2 ↔ 4/5)
  - dsPIC33CK256MP505 48-TQFP: power, MCLR, AVDD/AVSS and every analog channel used (DS70005349K Table 6)
- **Datasheet behaviour:**
  - LM5176 UVLO equation with the minus sign, and the ISNS sink on ISNS(−) (correct sign; within the ±0.3 V differential abs max at 132 µA × 1 kΩ)
  - UCC27282 EN thresholds: enable ≤ 2.0 V, disable ≥ 0.7 V
  - AMC3330 input resistance ≥ 0.1 GΩ against the 12.7 kΩ divider leg
  - SN74LVC2G74 PRE/CLR truth table: power-up with both low gives Q = Q̄ = H, but the MCU is held in reset then, so this is safe
- **Arithmetic:**
  - L2 = 380.0 V, L3 = 391.6 V, OC 0.40 A, CC 0.301 A
  - AMC3330 full-scale range at 420 V
  - T301 Bpk 0.095 T at 95 kHz
  - Cap math: 2.08 days from 80 % to 100 % at 0.30 A for 8 h/day
  - Pack heating bound
  - HV bleed time
- **Battery-end board:**
  - EVM10-5: 5 A, 500 VDC, 20 kA, total I²t 105 A²s, minimum break 3 × In (Eaton ELX1304 via distributor listings)
  - G9KB: 600 VDC 1 A resistive, ≥ 3.6 mm gap, 12 V coil about 235 mA (Omron, via distributor)
  - No pre-charge is needed, because D901 blocks the pack from the output caps
  - The relays switch at zero current, within rating even under load
- **Isolators:** AMC3330/3302 are reinforced, VISO 4250 Vrms, VIOWM 1700 VDC, VIOTM 6000 Vpk, CTI ≥ 600 V.
- **PERMIT architecture:** sourced only by MCU_RUN, a wired-AND of DIAG, latch, OTP and watchdog. The CAN transmit gate requires IG AND CAN_EN. The MPPT default is zero power without firmware (100 kΩ pull-up on the PWM pins).
- **Vehicle:** Prime pack 95 cells, 351.5 V, 25 Ah (ANL). The "no split while off" conclusion is consistent with every source found.

## Response to review

Designer response, 2026-10-23, design v0.3. Build: `kaesynth build` 0 errors, 0 warnings, 9 waivers covering 17 findings (was 32), KiCad ERC 0 errors (4 waived HGND warnings), netlist round trip identical for the system and both boards. DESIGN.md §7.12–7.13 are new; §§2–10 are revised. Every item below is in design.py/parts.py, not only in prose.

### BLOCKERs

**B1, HV-to-chassis insulation: fixed.**
- New `CHASSIS` domain (floats on GND; the boxes, screws, pedestal and plated holes H701–H704, bonded once by NT701).
- Reinforced DC barriers HV↔CHASSIS (420 V) and PACK↔CHASSIS (399 V): 10 mm creepage, 8 mm clearance (IEC 60664-1 F.4 PD2 IIIa 500 V row ×2; F.2 for 6 kV). The DRU now has `IR:barrier.HV.CHASSIS`/`PACK.CHASSIS` rules.
- `Domain(edge_clearance_mm=10)` on HV and PACK emits edge and hole-clearance rules for every mounting hole on both boards.
- H705/H706 stay as east-edge supports, but with PA66 standoffs and nylon screws and a 13 mm `keepout_around` for HV/PACK copper. That stays compliant even if a metal screw is fitted. H901–H904 get the same keepout. Hole positions are `place.fixed` with the enclosure drawing as the source.
- No thermal interface under HV. A box-floor pedestal with an insulating gap pad sits under the LV power area only. Under the HV section there is a ≥ 10 mm pocket lined with polypropylene (not credited). D301–D304 sit on top copper only. T301's core goes to the lid through an insulating gap pad (core on the LV side of the TIW). HV THT leads are clipped to ≤ 1.5 mm.
- The contradictory `boards()` enclosure note and the `side()` note are rewritten.
- The battery-end board stands on standoffs with no thermal interface.
- PACK now floats on HV_N, per the README rule for relay-joined circuits: the connected case is modelled, with the functional barrier across the open contacts.

**B2, inferred cell window: answered and made BLOCKING.**
- No Toyota, Panasonic or teardown source for the Prime's top-of-charge was found. ANL D3 gives 95 cells (19 × 5), 351.5 V, 25 Ah only. One PriusChat log implies ~4.06 V/cell but is internally inconsistent [unverified].
- New **Q-13 (BLOCKING)**: log the car at the end of a full plug-in charge (pack V, max cell V, displayed vs true SOC).
- The hardware is now set below the lowest credible value, 4.00 V/cell:
  - L3 373.1 V = 3.927 V/cell, max 3.963 V with tolerance (U422 Rf 12.1k → 12.7k);
  - L2 364.4 V = 3.836 V/cell (R802 1.5k → 3.24k);
  - L1 firmware 3.79 V/cell; L3b 36.8 V.
- Ordering margins hold at the tolerance corners (`L1_below_L2min` 1.1 V, `L2max_below_L3min` 1.1 V).
- DNP trim positions R818 (‖R802) and R526 (‖R502) are in the netlist for re-setting after Q-13.
- HZ-4 is re-argued against 4.00 V. The cost is stated in REQ-8: the pack may stop near 55–65 % true SOC until Q-13 is answered.

### MAJORs

- **M1, reverse power: fixed four ways.**
  - Sink clamp: R105/R205 20k → 75k, so I_sink ≤ 39.1 µA < VSNS(min)/1 kΩ. The CC loop never asks for < 0.79 A.
  - Burst: LIM > 2.30 V (U801-derived VTH_BURST) → U507 ch2 → D106/D206 pull both EN low.
  - PV-node trip: PVx_P > 34.0 V → U507 ch3/ch4 → that EN low.
  - Clamp: TPSMB43A on PVx_P (D107/D207).
  - The scenario the review missed is also bounded: one channel's FB tolerance makes it sink while the other holds VINT unloaded. V-26 tests it.
- **M2, CAN clock: fixed.**
  - 20 MHz NDK NX3225GA AEC-Q200 crystal (±200 ppm worst case [P]) on OSCI/OSCO (pins 21/22).
  - Pin moves: NTC_HS → 26 (AN8), NTC_P3 → 35 (AN2), IMD_ADC → 36 (AN10), EE_CS_N → 37, WDI → 45, LATCH_SNS → 46, PERMIT_SNS → 47, IMD_SW → 48.
  - ICSP moves to PGC3/PGD3 (33/34). The log UART shares PGD3 at run time (J701 pin 6 now NC).
  - CAN FD starts in Listen-Only (REQ-19).
- **M3, insulation monitoring while parked: fixed (§7.12).**
  - Permanent 11 × 10 MΩ bridge per pole (≥ 108.9 MΩ, so REQ-14 still holds). U461 AMC3330 reads chassis-to-HV_N on a 220 kΩ tap, offset so negative readings survive. Q461 BSS123Q shorts one 10 MΩ of the P pole for the second point.
  - Measured with the relays open before every close and hourly. Refuse below 500 Ω/V. The same readings detect a welded K901 or K902.
  - Why not "switched out" as suggested: a chassis-end switch must block the full pole voltage. No small chassis-referenced switch can block the N pole's polarity, and an optocoupled PV-driver switch (ACPL-K30T, read) has only 8 mm creepage on a IIIa mould at 420 V. At 110 MΩ the permanent bridge already meets the 100 MΩ requirement and loads the car's monitor by < 0.5 %.
  - The chains are a protective impedance (≤ 4.2 µA with one resistor shorted). The framework's `domain.crossing` on R470/R481 is waived with that reasoning.
- **M4, open-sensor-safe OTP: fixed.**
  - U508 ch2/ch3 pull PERMIT low when NTC_P1/P2 > 2.199 V. An open sensor reads 2.50 V; a pack below −18 °C also trips, and charging needs ≥ 0 °C anyway. A short reads hot.
  - The hardware pair TH1/TH2 now has its own connector and cable (J706/W5); the firmware pair is on J708/W11.
- **M5, pluggable HV: fixed.**
  - J301/J901/J902 are WAGO 236 CAGE CLAMP blocks (tool-opened, wired once) under a tool-opened inner cover. The voltage rating is [unverified] until the WAGO sheet is read (V-5).
  - HVIL: the coil supply passes lid switches S701 and S901 in series (J705/J904, W9/W10), with flyback D902/D903 at the relays. Opening either lid drops both relays.
  - The service procedure is built on the car's service plug (HZ-17).
- **M6, DCX bounds: fixed.**
  - Discrete Lr L301 0.56 µH (XAL7070, ratings [unverified]); T301 leakage specified ≤ 0.30 µH. fr 90–115 kHz is computed at the corners.
  - Gate on-time limit on HI and LI (10k/1 nF integrators, U506 ch3/ch4): trip after 6.5–8.0 µs, f_min 62.5 kHz, Bpk 0.144 T.
  - Primary shunt R311 5 mΩ in the Q302 source → U507 ch1 at 17.6 A.
  - All three latch through OVP_TRIP_N.
- **M7, latch and dawn cycling: fixed.**
  - U503 now runs on LATCH_VCC: a 0.1 F supercap (Eaton KW, −40…85 °C, industrial grade) with τ 6.1 h. It holds 2.74 V after a 10-min brownout and clears overnight.
  - ~CLR comes from its own power-on RC, not RESET_N. The OVP_TRIP_N pull-up is on LATCH_VCC.
  - The relays need AUX_IN ≥ 18.1 V (U508 ch1, 1.4 V hysteresis).
  - Firmware keeps trips in EEPROM, requires a dawn-to-dawn gap and allows ≤ 3 relay cycles per day.
  - Both relays now switch together; v0.2's "sequenced" claim did not match its own hardware. The IMD replaces the per-relay weld check.

### MINORs

1. **L2b**: removed as a layer everywhere (§7.2, §7.4, HZ-3, HZ-12, HZ-13). The FB ceiling (now 432k, ≤ 393 V unloaded) is described as an output limit only.
2. **UVLO corners**: R108/R208 137k → 162k. At the SNVSB46B corners off is ≤ 8.51 V, below the 9.9 V shaded Vmp, and on is ≤ 11.73 V, below the 13.8 V hot Vmp. The build checks both (`uvlo_*`).
3. **Path-1 leakage**: added a second CV integrator on path 2 (U803A, 367.8 V on HV_P), diode-ORed into LIM. The clamp acts on whichever path reads higher. Its margin to L3 is calculated.
4. **Hysteresis shifting ADC readings**: kept. Firmware subtracts the known PERMIT-dependent shift using PERMIT_SNS (stated in R511/R523 and §7.5).
5. **Cold margins**: R518 2.2k → 4.7k, so PERMIT latched is ≤ 0.58 V at −40 °C against 0.7 V. D510 pulls K_IN straight to Q̄ (≤ 0.55 V against 0.9 V). Both are build calcs.
6. **Temperature compensation and "80 %"**: REQ-7/8 now say that the hardware CV is not temperature-compensated, that L2 holds 3.84 V/cell indefinitely with live-but-wrong firmware, and that "80 %" means true SOC.
7. **LM74700 waiver**: reasoning rewritten. The stage cannot start with the string reversed, because its VIN is the blocked PV node; it is no longer claimed that there is "no back-feed path".
8. **Vehicle facts and Q-5**: Q-5 now states that a cell-side tap means opening the sealed pack and adding a penetration. The login-only DM pages stay [P] as read earlier; ANL is added as an open source.
9. **Roof not measured, cap discards energy**: both are stated in §7.1 (`best_day_discard_pct` 30 %), and Q-3 stays BLOCKING.

### Waivers

- **Removed** (the framework now expresses them):
  - LM74700 GATE/VCAP, LM5176 SS/COMP/VCC/BOOT and LM5164 BST-SW: `VLimit(derate=False)`;
  - dsPIC VDD: `v_rec=3.6`;
  - AMC package creepage: `creepage_by_group={"I": 5.0}` with `material_group="I"` and `v_work_dc=1700` on the isolators.
- **Corrected**: LM74700 CATHODE–ANODE (MINOR 7).
- **Added**: `domain.crossing` for the IMD protective impedance.
- **Unchanged**: entry-fuse ×2, custom footprints ×3 (still blocking for layout, now stated in the waiver text), HZ-9, HGND ERC.

### Still open

- BLOCKING questions: Q-3 (roof), Q-4 (junction-block pages), Q-5 (installer, pack penetration), Q-6 (array fixing), Q-10 (ECU SOC re-estimation, V-23), Q-13 (car top-of-charge).
- Unverified part data to read before layout: WAGO 236 voltage rating, XAL7070 ratings, Eaton KW footprint pitch, G9KB pin numbering.
- Unpowered-comparator leakage on OVP_TRIP_N at 85 °C (V-11).
