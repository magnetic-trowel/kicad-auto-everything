<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Prius Prime solar MPPT charger: design

Status: engineering draft v0.3 (2026-10-23), revised after the independent review in [REVIEW.md](REVIEW.md) (its "Response to review" lists every change). Encoded in [design.py](design.py) / [parts.py](parts.py) and checked by `kaesynth build` (0 errors, 0 warnings, 9 waivers covering 17 findings, each with a reason; KiCad ERC 0 errors; netlist round trip identical for the system and both boards). **Not for fabrication**: BLOCKING questions Q-3, Q-4, Q-5, Q-6, Q-10 and Q-13 are open, custom footprints are undrawn, and no qualified HV engineer has signed it off. Netlist summary: [CONNECTIONS.md](CONNECTIONS.md); checks: [out/report.md](out/report.md).

Evidence tags: [P] read in the primary source, [S] secondary (distributor page, snippet, forum, press), [V] vendor claim, [I] our inference.

## 1. Brief

> "I want to put solar panels on my Prius. It should take a bunch of C60s in strings and mppt them. They should fit on the top roof so you can measure the size of the roof of a 2017 Prius and shrink it a little bit for margins. It should take that raw voltage, step it up, and dump it into the battery. It should make sure that the battery can't go over voltage. It should make sure that if the wires outside of the battery are shorted, that the battery can't dump, you know, the 200 or whatever volts into it. It should make sure it doesn't overheat, so it might need a fan depending on how much current it's pushing. Or maybe it just has a bit of an aluminum heatsink."

Follow-ups (2026-10-23): "on the prius it must work on or off. it will have to have some smarts, and to be weak enough that the batteries can't get themselves in trouble. so that means it would have to stop charging by 80%, have a voltage clamp, it would need temp compensation, etc. also i know on older prius the pack was electrically split in two while off. check to see if that's still the case. this is a complex board. that's the point" and "it's a prius prime with li-ion".

**Summary.** 56 C60 cells (two 28-cell strings, ≤ 23 V) feed two analog 4-switch buck-boost MPPT stages into a 26–36 V bus. A fixed-ratio, reinforced LLC "DC transformer" (1:22) lifts it to the Prime's 285–399 V pack. The charger taps the pack on the cell side of the system main relays, so it charges with the car on or off. Because the car's battery ECU sleeps while parked, the board carries its own supervision: isolated pack-voltage and charge-current sensing, coulomb counting with rest-OCV correction, four pack-case temperature sensors, a firmware stop at 75–80 % SOC, a firmware-free analog CV/CC clamp, an independent latching overvoltage/overcurrent trip, its own insulation monitor, and a **hardware current cap of 0.30 A (C/83)**. Because the Prime's own top-of-charge cell voltage could not be sourced (Q-13), the hardware clamp and latch are set below the lowest credible value (4.00 V/cell) until it is measured on the car. At that cap, even with every firmware layer dead, two full sunny days pass before the pack goes from 80 % to 100 %. A battery-end board holds a fuse on each pole, a blocking diode and a 2-pole disconnect.

### 1.1 What the vehicle research found

- **Pack** [P: Toyota dismantling manual T-DM-017-D, 2017–2022 Prius Prime, p.10; Toyota PHV launch release]: Li-ion, 95 cells of 3.7 V in series, 351.5 V nominal, 25 Ah, 8.8 kWh, in the luggage area. Normally open relays on both output cables open when the car is shut off; a fuse sits inside the pack; removing the service plug grip (under the No. 4 shield panel) cuts the circuit. The manual also warns that cars with the solar charging system generate power in any light.
- **Is the pack split while off? No.** Toyota's documents for the Gen 1 (274 V, 38 modules), Gen 3 (201.6 V), first plug-in (ZVW35) and Prime all describe relays on the two pack cables only [P: Toyota ERG/dismantling manuals]. The split the user remembers is the **service plug**: it sits inside the string and divides the pack only when removed. On Gen 2 it splits the pack into halves [S: fewstreet.com]; on the 2010 car into 64.8 V and 136.8 V sections [S: VehicleServicePros]. I found no Toyota source for a relay that splits any Prius pack while off. Consequences: one tap pair on the cell side of the system main relays (SMRB +, SMRG/SMRP −) reaches the whole 95-cell string. Each tap pole has its own fuse (F901, F902). With the plug pulled, our pack reading falls below 280 V or goes open, and firmware refuses to charge (Q-11 asks where the plug sits in the string).
- **Toyota's own solar roof** (Japanese Prius PHV = Prime, 2017) [P: Miyoshi, J. JSAEM 25(4):379, 2017; Toyota release]: a 180 W panel. While driving it feeds the 12 V system. While parked it charges the traction battery by **"pump charging"**. A solar ECU with three DC/DCs first charges a small temporary battery without waking the car's BMS. Once that battery holds enough, the ECU wakes the BMS (battery ECU, HV ECU, relays), discharges the buffer into the traction battery, and covers the BMS's 12 V draw. Toyota's reason was efficiency: BMS wake-up power is comparable to the panel output. The result was up to 6.1 km and on average 2.9 km of EV range per day (Nagoya), about 0.58 kWh/day at the quoted 10.54 km/kWh. It was built as an add-on with minimal changes to the car's battery systems. The lesson: **Toyota let the traction battery accept charge only with its BMS awake.** We cannot wake the BMS or close its relays from outside (the interface is not public), so our board takes over the BMS duties that matter for slow charging (§7.4–7.6), and its current cap keeps the daily energy at the scale Toyota chose (§7.1).

## 2. Requirements

Full text, values and verification are in design.py `intent()` and [out/report.md](out/report.md). Summary:

| ID | Requirement (value) |
|---|---|
| REQ-1/2 | 56 C60 cells, 2 × 28, field 1016 × 889 mm on the Prime roof, ≥ 40 mm margins; electronics accept 28–40 cells/string |
| REQ-3/4 | 2 analog MPPT channels; Voc ≤ 33 V at −40 °C (ISO 6469-3 class A) |
| REQ-5 | Output 285–399 V into the Prime pack, ≤ 0.30 A (hardware cap), ≤ 120 W |
| REQ-6 | Charge with the car ON and OFF (Q-1 answer) |
| REQ-7 | Weak by design: with all firmware failed, ≥ 2 sun-days from 80 % to 100 % SOC. With firmware wrong but alive, the hardware CV holds the pack at L2 (3.84 V/cell) indefinitely; the hardware clamp is not temperature-compensated |
| REQ-8 | Stop by 80 % **true** SOC (of the 25 Ah pack, not the car's narrower display) on its own estimate (coulomb + rest OCV + CAN when awake); target 75 %; until Q-13, never above 3.79 V/cell at rest, which may stop well below 80 % |
| REQ-9 | Firmware-free clamp (L2 3.84 V/cell on path 1, 3.87 on HV_P) and latch (L3 3.93 V/cell, max 3.96, on HV_P); trim positions for Q-13 |
| REQ-10 | Own pack-case NTCs, hardware pair and firmware pair in separate cables; charge 0–45 °C; temperature-compensated stop voltage; hardware OTP 50 °C and hardware open-sensor / below −18 °C cut |
| REQ-11/12 | Pack cannot feed our wiring: D901 + fuse per pole (≥ 500 VDC, ≥ 20 kA) + 2-pole disconnect, at the battery end |
| REQ-13/14 | Reinforced LV↔HV/PACK (10 mm creepage, 8 mm clearance, ≥ 4250 Vrms parts); ≥ 100 MΩ, no Y-caps |
| REQ-15/16 | No overheating; −40…+85 °C ambient |
| REQ-17 | Firmware faults contained by hardware (watchdog, analog CV/CC, PERMIT wired-AND, safe reset state) |
| REQ-18/19 | No 12 V battery drain; CAN read-only, transmitter physically off unless IG is on |
| REQ-20…25 | EMC CISPR 25 class 3; HV wiring practice (unfused tap leads ≤ 0.3 m); event log; reverse string; output bleed < 60 V in 10 s; AEC-Q parts |
| REQ-26 | HV/PACK-to-chassis insulation designed: reinforced, 10 mm creepage / 8 mm clearance to edges, holes, screws, enclosure; no thermal interface under HV |
| REQ-27 | Own insulation monitor: measure before every relay close and hourly; refuse below 500 Ω/V (210 kΩ) |
| REQ-28 | No pluggable pack-live connections; HVIL (lid switches in the relay-coil supply) |
| REQ-29 | DCX bounded in hardware: gate on-time and primary current latch the trip |

## 3. Assumptions and open questions

Assumptions ASM-1…8 are in design.py. The important ones:

- **Roof** (ASM-1): Toyota covered about 0.8 m² of cells on this roof (180 W at ~22.5 % [S]) and left the curved edges bare. The 56-cell field (0.86 m² of cells) assumes a similar flat area. Q-3 (template) decides; strings of 28–40 cells work.
- **Cell window** (ASM-2/3): 3.00–4.20 V (NMC-class), giving 285–399 V for the pack. **The car's own top-of-charge is not known** (Q-13). I found no Toyota, Panasonic or teardown figure: Argonne's D3 teardown gives only 95 cells (19 × 5), 351.5 V and 25 Ah [P]; Toyota's documents give nominal values only. The one Prime scanner log found (PriusChat [S, unverified]) implies about 4.06 V/cell but its cell count is inconsistent. Toyota PHEVs use a narrow window, so the hardware layers assume the car may stop as low as **4.00 V/cell** and sit below it (§7.4). OCV at 80 % true SOC is 3.97–4.02 V [I]; at the provisional 3.79 V stop the pack is nearer 55–65 % [I].
- **Pack short circuit** ~3.3 kA (ASM-4, [I]).
- **Pack case** is chassis potential and isolated from the cells [P: DM], so NTCs bolted to it are LV parts (ASM-7).
- **Thermal**: pack ~70 kJ/K and ~10 W/K to the cabin with its fan off (ASM-8, [I]).

| ID | Question | Status |
|---|---|---|
| Q-1 | Charge only while READY, or also parked? | **Answered**: both (user, 2026-10-23) |
| Q-2 | Which pack? | **Answered**: 2017 Prius Prime Li-ion (user); NiMH variant removed |
| Q-3 | Roof template: confirm the 8 × 7 field | **BLOCKING** |
| Q-4 | Prime repair-manual pages for the HV junction block: SMRB/SMRP/SMRG, CHRB/CHRG, current-sensor position and cell-side studs. Our − tap should be on the relay side of the car's current sensor so the battery ECU counts our current when awake | **BLOCKING** |
| Q-5 | Who installs the pack-side tap (HV-trained, service-plug procedure, 10-min wait [P])? A cell-side tap means opening the sealed pack case and adding a sealed penetration. Insurer/registration/warranty | **BLOCKING** |
| Q-6 | Array fixing (bonded laminate vs rails) | **BLOCKING** |
| Q-7 | C60 sheet asks for positive ground [P]; we bond PV− to chassis (test V-22) | open |
| Q-8 | Optional fan | default no |
| Q-9 | T301 vendor; hipot/PD test ownership | open |
| Q-10 | How the Prime battery ECU re-estimates SOC after charge added while it slept, and whether it sets DTCs (V-23). Parked charging ships disabled until V-23 passes | **BLOCKING** |
| Q-11 | Where the service plug sits in the string | open (firmware handles < 280 V / open) |
| Q-12 | Toyota OBD PIDs for SOC, min/max cell voltage and DTC status on the Prime (community lists exist [unverified]); without them firmware stops at 3.79 V/cell | open |
| Q-13 | The Prime's pack voltage and maximum cell voltage at the end of a full plug-in charge (Techstream/OBD log, warm and cold), and its displayed-vs-true SOC window. Then fit R818/R526 to put L2/L3 one step below the measured maximum and rebuild | **BLOCKING** |

**What happens to the car's SOC estimate** (Q-10, [I]): no Toyota document on this was found. While the car sleeps, its battery ECU counts nothing, so after a sunny day its stored SOC is low by our added charge (≤ 2.4 Ah ≈ 10 %). Li-ion ECUs normally correct SOC from rested open-circuit voltage at wake-up. The Prime should therefore see a jump toward the true value, and its plug-in and hybrid limits are voltage-based per cell, so they still protect the cells. The DTC risk (a "SOC/voltage inconsistency" or capacity code) cannot be argued from documents, so it is a test: V-23 runs three park-charge-wake cycles with Techstream logging before parked charging is enabled by default, and the per-parking budget (≤ 10 % SOC) bounds the jump. Toyota's own design avoided this question by keeping the BMS awake (§1.1).

## 4. Hazards

The full table, with implementing parts and single-fault flags, is in design.py and [out/report.md](out/report.md). Interlock chains:

| ID | Hazard | Mitigation (implemented by) | 1-fault safe |
|---|---|---|---|
| HZ-1 | Shock: 285–420 V on our cable/boards; any HV/PACK net up to 420 V to chassis under one insulation fault | Reinforced LV/HV, LV/PACK and HV/PACK↔CHASSIS barriers (T301, U401/U421/U441/U461, K901/K902 coil–contact), 10/8 mm PCB, 10 mm to edges and holes, no thermal path under HV (§7.12), own IMD, HVIL, screened cable, metal IP67 boxes, both poles open when idle, bleed < 60 V/10 s | yes |
| HZ-2 | Short in our cable/board lets the pack dump kA | D901 blocks pack→cable; F901/F902 (20 kA) first from each pole; K901/K902 open | yes |
| HZ-3 | Pack overvoltage while the BMS sleeps | L1 firmware → L2 analog CV on path 1 (U802A) and on HV_P (U803A), own reference U801 → L3 latch (U421→U422→U502 ch1→U503→PERMIT) → L3b VINT latch; cap 0.30 A. All below 4.00 V/cell (Q-13) | yes |
| HZ-4 | Cell imbalance pushes one cell high | Common series current; every hardware layer below the lowest credible car top-of-charge; CAN min/max cell check (§7.5) | yes |
| HZ-5 | Our SOC drifts | Conservative capacity, dawn OCV reset, CAN cross-check; L2/L3 bound it | yes |
| HZ-6 | Car SOC/DTC disturbed | Per-parking budget, V-23 gate, tap position (Q-4) | **no** (until V-23) |
| HZ-7 | Hidden insulation fault or false P0AA6 | Own IMD (U461, 110 MΩ/pole bridge, two-point, §7.12) before every close and hourly; ≥ 100 MΩ/pole added, no Y-caps, < 1 nF to chassis | yes |
| HZ-8 | Roof arc/hot spot | ≤ 33 V, bypass per 7-cell column, 1 string per input, ideal diode | yes |
| HZ-9 | Array detaches | mechanical (Q-6) | open |
| HZ-10 | Converter overheats | RT301 firmware derate; RT302→U502 ch3 OTP; LM5176 TSD | yes |
| HZ-11 | Firmware hang/wild PWM | TPS3850 window WDT → MCU reset → MCU_RUN pulled down (R519) → PERMIT low; DCX gate on-time limit (U506 ch3/ch4) and primary OC (R311, U507 ch1) latch | yes |
| HZ-12 | Sensor masks OV | Each isolated amp's DIAG pulls PERMIT low; L3 has its own divider, amp and reference; L2 acts on both paths | yes |
| HZ-13 | Pack disconnects under load | DCX output ≤ 11 × VINT (ceiling 393 V worst case); L3 latch; L3b; 70 mJ in output caps | yes |
| HZ-14 | String reversed | LM74700 + FET | yes |
| HZ-15 | Pack too hot/cold, sensor or harness open | Firmware window 0–45 °C on 4 NTCs; hardware OTP 50 °C (U502 ch4, U506 ch2) and open/below −18 °C cut (U508 ch2/ch3) on the hardware pair in its own cable; a short reads hot | yes |
| HZ-16 | Vehicle transients on IG/CAN | BAS21 + 22.1 kΩ 1206; transceiver −7…16 V bus | yes |
| HZ-17 | Service: our tap is live on the cell side and could bridge an open service plug through 6 MΩ | Relays open when idle; tap on a tool-opened CAGE CLAMP block under an inner cover; opening either lid drops both relays (HVIL); procedure built on the car's service plug (§7.13) | **procedural** |
| HZ-18 | Crash crushes the HV cable | Routing; D901 and fuses at the battery end | yes |
| HZ-19 | Our CAN node disturbs the car | Transmitter off in hardware unless IG on (Q703 AND Q702 hold RS low only then); unpowered transceiver passive [P] | yes |
| HZ-20 | Relay coil left at 100 % | PWM economiser after 100 ms; watchdog; class F coil | no (thermal only) |
| HZ-21 | LM5176 (CCM only) runs backwards into a blocked PV node | Sink clamp (setpoint ≥ 0.79 A), LIM burst disables both stages (U507 ch2), PV node > 34 V disables that stage (U507 ch3/4), TPSMB43A on PVx_P (§7.2) | yes |
| HZ-22 | Latch cleared by a brownout; relays cycling at dawn | Latch on its own supercap rail; relays need AUX_IN ≥ 18 V (U508 ch1); EEPROM trip memory, ≤ 3 relay cycles/day (§7.9) | yes |

**PERMIT chain** (the hardware interlock): PERMIT is sourced only by MCU_RUN through R518 (4.7 kΩ). Any of these pull it low: U401/U421/U441/U461 DIAG, latch Q̄ via D501, U502 ch3/ch4, U506 ch2, U508 ch2/ch3 (NTC open/cold), or a watchdog reset (MCU pins tri-state, R519 pulls MCU_RUN down). PERMIT gates U103/U203 EN (via D102/D202), U301 EN, and the relay drive. The relay input K_IN = RELAY_REQ AND PERMIT (D503) AND AUX_PG (D511) AND NOT latch (D510, directly from Q̄). The trip latch (OVP_TRIP_N) is set by L3, L3b, the charge-current OC, the DCX primary OC and the DCX gate on-time limit.

## 5. Architecture trade study

Gates: G1 charges the traction battery (brief). G2 no HV on the roof. G3 works with the car ON and OFF (Q-1). G4 buildable aftermarket.

| Alt | Description | G1 | G2 | G3 | G4 | Safety/containment (5) | Energy (3) | Car BMS in control (3) | Simplicity (2) | Score |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | Non-isolated boost, roof → pack | ✓ | ✗ | ✓ | ✓ | 1 | 5 | 1 | 5 | — |
| A2 | Isolated flyback, digital control | ✓ | ✓ | ✓ | ✓ | 3 | 4 | 1 | 3 | 36 |
| **A3** | **Analog MPPT → LLC-DCX → battery-end; own supervision, cell-side tap (direct injection)** | ✓ | ✓ | ✓ | ✓ | 4 | 4 | 2 | 2 | **42** |
| A4 | 12 V auxiliary charging only | ✗ | ✓ | ✓ | ✓ | 5 | 1 | 3 | 5 | — |
| A5 | Toyota pump charging: buffer battery, wake the BMS, transfer through the car's relays | ✓ | ✓ | ✓ | ✗ | 5 | 4 | 3 | 1 | — |
| A6 | Through the J1772 inlet: buffer battery + 1.5 kW inverter + EVSE pilot emulation, bursts | ✓ | ✓ | ✗ | ✓ | 5 | 2 | 3 | 1 | — |

- **A3 (chosen).** Physics bounds the output: fixed DCX gain, analog CV/CC loops, an independent latch, and an array too small to hurt the pack quickly. It meets every gate. Cost: our board must stand in for the sleeping BMS, so it needs isolated sensing, SOC estimation, temperature sensors and CAN. Hence the complexity the user asked for.
- **A5** is what Toyota built, and it is the best for the pack because the BMS supervises every transfer. Aftermarket it fails G4: waking the battery and HV ECUs and closing a charge relay needs Toyota's undocumented solar-ECU interface. It would also add a buffer battery and two more converters.
- **A6** keeps the car's charger and BMS fully in control and needs no HV tap. It fails G3, because a plugged-in car will not drive, so it charges only when parked. It costs a 1–2 kWh buffer (~15 kg), an inverter, a pilot emulator and the car's charging overhead (car awake, onboard-charger losses; round trip ~70 % [I]). If Q-5 or V-23 rules out a cell-side tap, it is the fallback.
- **Evidence on direct injection.** Nothing found says it is unsafe in itself. Toyota's choice says BMS supervision matters, so A3 adds its own supervision, a cap that limits the damage rate (§7.1), and a validation gate (V-23).

## 6. Blocks, domains and barriers

| Block (sheet) | Board | Function |
|---|---|---|
| MPPT_A / MPPT_B | main | J101/J201, TVS, LM74700 ideal diode, 5 mΩ shunt + INA186, LM5176 buck-boost (201 kHz) into VINT, PV-voltage PI loop (U104/U204), limiter override diode D105/D205 |
| DCX | main | VINT bulk, UCC27282 + 2 FETs half-bridge at 95 kHz, discrete Lr L301, split resonant caps, T301 (4:88), VS-6ESH06 bridge, 8 × 100 nF 630 V, J301 (CAGE CLAMP), primary shunt R311, gate on-time integrators, temperature sensors |
| HVSENSE | main | Path 1: pack voltage via the battery-end string and cable sense core (U401, G = 1.5). Path 2: HV_P for L3 and the second CV loop (U421, G = 1.27). Current: 0.1 Ω return shunt + AMC3302 U441 (G = 1, 4.1 V/A) |
| IMD | main | 11 × 10 MΩ per pole from HV_P and HV_N to CHASSIS; U461 (AMC3330) reads chassis-to-HV_N on a 220 kΩ tap; Q461 range switch for the second point |
| LIMIT | main | L2: CV (path 1, U802A), CV (path 2, U803A) and CC (U802B) integrators on their own LM4040 (U801); output LIM lifts both PV setpoints; burst threshold |
| SAFETY | main | LM4040 U501, comparators U502/U506/U507/U508, trip latch U503 on its supercap rail, TPS3850 WDT, PERMIT, relay AND gate, TPL7407 coil/fan/LED drivers |
| AUX | main | PV/VINT OR → LM5164 AUX12 (12.1 V) → LM5164 +3V3 |
| MCU | main | dsPIC33CK256MP505 with 20 MHz crystal, EEPROM log U703, IG sense (Q701), CAN (SN65HVD230Q) with IG-AND-enable transmit gate (Q702/Q703), connectors J701–J708, CHASSIS holes and bond NT701 |
| BATEND | batt_end | J901 (HV in), J902 (pack tap), both CAGE CLAMP; J903 (coils), J904 (lid switch); F901/F902 EVM10-5, K901/K902 G9KB-1A with flyback D902/D903, D901, sense string R902–R904 |
| ARRAY, HARNESS | off | 8 columns × 7 C60 + 8 bypass diodes; cables W1–W11, lid switches S701/S901, IG tap fuse F701/X701, pack-case NTCs TH1–TH4 |

| Domain | 0 V reference | Range | To chassis |
|---|---|---|---|
| LV (PV, VINT, AUX, logic, IG, CAN, pack-case NTCs) | GND, bonded to CHASSIS by NT701 | 0–38 V (PV TVS clamp 54 V; IG −150…+112 V pulses) | same |
| CHASSIS (boxes, screws, pedestal, plated holes H701–H704) | floats on GND at 0 V | 0 | is chassis |
| HV (T301 secondary, sense high sides, IMD HV ends, cable, D901/K901/K902 side) | HV_N (root) | 0–420 V | floating: 0–420 V under one insulation fault; 110 MΩ/pole IMD bridge |
| PACK (cell-side tap, F901/F902) | floats on HV_N (K902 joins them; README: model the connected case) | 0–399 V | floating with the car's IT system |
| Floating sub-domains | BSTA1/2, BSTB1/2 on the LM5176 switch nodes; DCXBST on HB_SW; AUXBST/V33BST; KSUP (HVIL loop) on AUX12, K1C/K2C on K_SUP, FANC on AUX12; IDA/IDB on the string inputs | | |

| Barrier | Grade | Working V | Creepage / clearance | Basis |
|---|---|---|---|---|
| LV ↔ HV, LV ↔ PACK | reinforced | 420 V / 399 V DC | **10.0 / 8.0 mm**, routed slot ≥ 2 mm under T301, U401, U421, U441, U461, extending ≥ 2 mm past each package end; package creepage by mould group: I 5.0 mm, II 7.2 mm, IIIa 10 mm | IEC 60664-1 F.4 PD2 MG III, DC working voltage = r.m.s. value: 400 V row 4.0 mm basic [P via TI SLUP419]; 500 V row 5.0 mm [S] → ×2. F.1 ≤ 600 V OVC II 4 kV, reinforced 6 kV → F.2 5.5 mm; design 8 mm = G9KB requirement. Test 4.25 kVrms |
| HV ↔ CHASSIS, PACK ↔ CHASSIS | reinforced | 420 V / 399 V DC | **10.0 / 8.0 mm**; HV/PACK `edge_clearance` 10 mm (board edge and every mounting hole), 13 mm keepout around screws | same tables; §7.12 |
| HV ↔ PACK | functional | 399 V (relays open only with the converter stopped) | 5.0 / 5.0 mm | IPC-2221B B2 (301–500 V 2.5 mm; +0.005 mm/V above 500 V covers the 820 V fault case: 4.1 mm) |
| HV_P ↔ HV_N | functional | 420 V | 2.5 mm | IPC-2221B B2 |

Parts across barriers: T301 (5.0 kVrms type test, ≥ 10 mm, 600 V DC working specified), AMC3330 ×3 / AMC3302 (4250 Vrms, VIOWM 1700 VDC, CPG ≥ 8 mm, CTI ≥ 600 = group I, which needs 5.0 mm), G9KB coil–contact (5000 VAC, reinforced 600 V, 12.6/8.0 mm) and its open contact (2500 VAC, 600 V). The IMD resistor chains are the only resistive path from HV to CHASSIS: a protective impedance of 110 MΩ per pole (waived with reasons, §7.12).

## 7. Calculations

Numbers below are computed in design.py `calcs()` (limits enforced by the build) or by hand where noted.

### 7.1 Array and the "weak by design" cap

- C60 [P]: 125 mm, Pmp 3.34–3.42 W, Vmp 0.574–0.582 V, Imp 5.83–5.93 A, Voc 0.682–0.687 V, Isc 6.24–6.28 A, −1.8 mV/K, −0.32 %/K.
- **Layout**: 8 columns × 7 rows at 127 mm pitch, field 1016 × 889 mm (laminate 1066 × 939 mm). String A is columns 1–4 (left), string B columns 5–8. Each column is 7 cells with one V10P45 bypass diode. Left/right strings see the same fore–aft curvature.
- String (28 cells): Voc 22.5 V at −40 °C (limit 33 V; 40 cells give 32.2 V), Vmp 16.1 V at 25 °C and 13.8 V at 70 °C. One column bypassed while hot gives 9.9 V; UVLO-off is ≤ 8.51 V even at the datasheet corner (`uvlo_off_max_v`, §7.2).
- Array 191.5 W at STC, ~150 W at a hot noon. The worst corner is 1.2 suns cold at the lowest pack voltage: 0.81 A (`phys_max_current_a`, envelope 0.85 A).
- **Cap derivation.** Li-ion has no safe overcharge rate, so the cap is set by time to damage, not by heat:
  - At 0.30 A a generous clear day of 8 cap-hours adds at most 2.4 Ah = 9.6 % SOC.
  - From the 80 % stop to 100 % takes ≥ 2.08 sun-days; to 110 %, the onset of plating and cathode damage [I], ≥ 3.1 days (`days_80_to_*`). Those figures assume every firmware layer failed, while L2 and L3 stop it at ≤ 3.96 V/cell first.
  - Daily energy at the cap (~0.7 kWh) matches Toyota's own maximum of 0.58 kWh/day.
  - **What the cap costs** (review MINOR 9): on a clear noon the array could deliver ~150 W, and the cap takes ~108 W, so about 30 % of the best-day peak is discarded (`best_day_discard_pct`). The user should know this; it is the price of "weak enough".
- **Pack temperature.** Joule heat at 0.3 A is I²R ≈ 0.014 W. Even if all 108 W became heat (gross overcharge), the pack would rise ≤ 5.6 K/h adiabatic and 10.8 K steady with its fan off (`pack_rise_*`). Our case NTCs catch that before the 50 °C hardware OTP.
- **The roof was not measured** (review MINOR 9). The brief asked for the 2017 roof to be measured; no published dimension was found, so the 1016 × 889 mm field is inferred from Toyota's 0.8 m² PHV panel (ASM-1). Q-3 (a template on the car) is BLOCKING.

### 7.2 MPPT stage (each channel; LM5176-Q1 equations [P])

- fsw 201 kHz (RT 41.2 kΩ). Boost operation (VINT 26–36 V > Vmp). Ripple at 16 V → 30 V: ΔI = 16·0.47/(22 µH·201 kHz) = 1.7 A.
- XAL1510-223: 7.5 A rms against 10.5 A (71 %); peak 8.4 A against 18.7 A Isat.
- Current sense 10 mΩ: boost peak limit 12 A. In boost mode the shunt carries D·I_L, so 7.5²·0.6·10 mΩ = 0.33 W.
- PV shunt 5 mΩ: 0.28 W. ISNS average-current limit (50 mV − 3 µA·1 kΩ)/5 mΩ = 9.4 A.
- **UVLO** (datasheet Eq. 1 with its minus sign [P, p.16]; corners per review MINOR 2): 1.5 MΩ/162 kΩ. Nominal on 9.5 V, off 4.8 V. At the SNVSB46B 6.5 corners (VEN(OP) 1.17–1.29 V, IEN(STBY) 1–3 µA, ΔIHYS 2.15–4.25 µA) on is 7.5–11.7 V and off ≤ 8.51 V, below the 9.9 V shaded hot Vmp (`uvlo_*`). EN reaches 3.41 V at a 35 V PV node.
- PV loop: TLV9001 integrates (VSET − PV/12). Q102 sinks current from ISNS(−) through R_iso (1 kΩ, R103), so I_PV = (VSNS − I_sink·1 kΩ)/5 mΩ. VSET defaults above Voc (PWM pin pulled high), so the stage gives zero power without firmware. D105 lets the limiter raise VSET above the MCU's value. Compensation is initial and tuned in V-21.
- **Reverse power (review M1).** The LM5176 is CCM-only (MODE offers only hiccup on/off) and its average-current loop acts by discharging SS. Asked for ≤ 0 A, or with VINT held above its own setpoint by the other channel, a CCM 4-switch stage drives negative inductor current into PVx_P, which the LM74700 isolates from the string. Four measures:
  - **Setpoint clamp**: R105/R205 75 kΩ limit the sink to (3.30 − 0.40 V)/74.25 kΩ = 39.1 µA, below VSNS(min)/1 kΩ = 43 µA, so the CC loop never asks for less than 0.79 A (`pv_sink_max_ua`, `pv_current_floor_a`).
  - **Burst instead of zero**: when LIM exceeds 2.30 V (VTH_BURST from U801; a PV setpoint ≥ 23.4 V, above any 28-cell Voc), U507 ch2 pulls BURST_N low and D106/D206 hold both EN/UVLO pins low. The stage stops instead of regulating to zero; the integrator sets the burst rate.
  - **PV-node trip**: U507 ch3/ch4 compare PVx_P/17 with VTH2V0 and pull that channel's EN low above 34.0 V (above the 40-cell cold Voc of 32.2 V).
  - **Clamp**: TPSMB43A on PVx_P (VWM 36.8 V, VBR ≥ 40.9 V) bounds a transient before the comparator acts; LM5176 VIN and LM74700 CATHODE stay below 60/75 V.
- **VINT ceiling**: FB 432 kΩ/10 kΩ gives 35.36 V (34.8–35.9 V over the 0.788–0.812 V reference). That limits the **unloaded** output to ≤ 393 V. It is not a cell backstop (review MINOR 1): with a pack connected the pack sets VINT. Charging at L2 needs 34.0 V (`vint_charging_at_L2_v`), inside the minimum ceiling.

### 7.3 LLC-DCX and T301 (fixed ratio, open loop)

- n = Ns/Np = 88/4 = 22. Half-bridge, so HV ≈ 11·VINT. VINT = 2·(Vpack + 1.6 V)/22 = 26.1 V at 285 V and 36.4 V at 399 V.
- **Lr is now a part** (review M6): L301 Coilcraft XAL7070-561 (0.56 µH ±20 % [unverified ratings]) plus T301 leakage specified ≤ 0.30 µH (an ETD39 with 4 primary turns and TIW secondary gives 0.15–0.3 µH). Total 0.60–0.97 µH with Cr 3.2 µF (two legs of 16 × 100 nF C0G): fr 90–115 kHz (`dcx_fr_khz_*`), fsw/fr 0.83–1.05 at 95 kHz. Below fr the rectifier gets ZCS; slightly above, ZVS is kept by the magnetising current. Peak and rms currents at fsw/fr 0.83 are ~10 % above the figures below; V-21 checks them.
- **Hardware bounds** (review M6): the half-bridge frequency comes from the MCU, so two things now latch the trip without firmware:
  - **gate on-time**: HI and LI each charge 10 kΩ/1 nF (C0G), reset by a BAT46 when the input falls; U506 ch3/ch4 trip at VTH_ONT 1.586 V, i.e. after 6.5–8.0 µs of continuous drive (VOH 3.0–3.3 V, RC ±6 %). The lowest frequency the hardware allows is 62.5 kHz, where Bpk = 0.144 T (`t301_bpk_at_fmin_t`, limit 0.2 T). A stuck-high pin trips the same way.
  - **primary current**: R311 (5 mΩ) in the Q302 source, filtered 1 kΩ/1 nF, against VTH_DOC 88 mV on U507 ch1: 17.6 A peak (normal peak 13–15 A at 114 W). This also catches saturation.
- At 120 W/380 V: R_ac,pri = 0.811·1267 Ω/22² = 2.1 Ω, Z0 = 0.5 Ω, Q = 0.24. Primary 7.3 A rms (10.4 A peak); Cr ripple ±5.4 V on 100 V parts.
- Lm 18 µH (gapped): Im,pk = 18.1 V·2.63 µs/18 µH = 2.6 A. ZVS needs 0.47 A. Primary total 7.45 A rms.
- Flux: Bpk = 0.095 T on ETD39 (Ae 125 mm²), so N97 loss is ~1.0–1.2 W [I].
- **T301 specification**: ETD 39, N97, 20-pin former; Np 4 turns of litz (~6 mm²), Ns 88 turns of triple-insulated wire; Faraday shield to GND; ≥ 10 mm pin-to-pin creepage; class F. Hipot 5.0 kVrms 60 s type, 4.25 kVrms 1 s routine; partial-discharge extinction > 1.5 × 420 V; Cps < 150 pF. Pins: 1/2 primary start, 3/4 primary end, 11/20 secondary.
- Rectifier VS-6ESH06: ≤ 420 V against 600 V (70 %); ~0.15 W each. Output 8 × 100 nF 630 V X7T (420 V = 67 %).

### 7.4 Overvoltage and current layers (pack-terminal voltages)

| Layer | Mechanism | Threshold | Independent of |
|---|---|---|---|
**Why these numbers (review B2).** The layers must sit below the car's own top-of-charge, which is not published (Q-13, §3). The lowest credible value is taken as 4.00 V/cell and L3 at its worst tolerance stays 37 mV below it. Every other layer is one step lower. When Q-13 is measured, DNP trims R818 (‖ R802) and R526 (‖ R502) move L2 and L3 up to one step below the measured maximum.

| Layer | Mechanism | Threshold | Independent of |
|---|---|---|---|
| L1 | Firmware stop (§7.5): SOC ≥ 75 % target / 80 % max, or rest-equivalent ≥ 3.79 V/cell × temperature table | 360.1 V (3.79 V/cell) | — |
| L2 | Analog CV integrator U802A: HV_V_LIM (path 1) vs VREF_CV (R802 3.24k/R803 39.2k from U801) | 364.4 V (3.836 V/cell) ±0.9 % | MCU |
| L2-p2 | Analog CV integrator U803A: HV_V2_LIM (path 2, HV_P) vs VREF_CV2 (R816 2.67k/R817 10k) | 367.8 V on HV_P | MCU, path 1 |
| L2-CC | Analog CC integrator U802B: I_HV vs VREF_CC | 0.301 A | MCU |
| L3 | U421 → U422 (G 1.27) → U502 ch1 vs 2.0016 V (U501) → latch U503 → PERMIT | 373.1 V on HV_P (3.927 V/cell; max 3.963) ±0.9 % | MCU, path 1, U801, L2 |
| L3-OC | U441 → U442 → U506 ch1 vs 1.641 V → same latch | 0.400 A | MCU, U801 |
| L3b | VINT divider (174k/10k) → U502 ch2 → latch | VINT 36.8 V | both AMC paths |
| — | LM5176 FB ceiling | unloaded output ≤ 393 V | not a cell layer (MINOR 1) |
| L4 | Car BMS when awake | car limits | everything here |

Ordering at the tolerance extremes (worst-case sum 0.9 % each): L1 < L2 min by 1.1 V; L2 max < L3 min (minus the 0.9 V D901 drop) by 1.1 V; the path-2 clamp is 1.6 V below the path-2 latch (shared divider, AMC and amplifier, so only references and dividers differ, ±0.5 %); L3 max = 3.963 V/cell < 4.00 V (`L*` calcs). **L2-p2 answers review MINOR 3**: path 1 is a 9 MΩ node through 2 m of cable, and leakage makes it read low, the unsafe direction for L2. The LIM diode-OR takes the larger correction of the two CV loops, so the clamp acts on whichever path reads higher. **Temperature** (MINOR 6): the hardware CV is not temperature-compensated. It is set for the coldest legitimate case, and the firmware table only lowers it. **Meaning of "80 %"**: true SOC of the 25 Ah pack. With firmware wrong but alive, L2 holds the pack at 3.84 V/cell indefinitely. That is below 80 % true SOC [I] and below the car's own top-of-charge. Until Q-13 is answered the pack may stop near 55–65 % true SOC; that cost is accepted. The latch is cleared only when its own hold-up rail powers up (§7.9), i.e. the next dawn. Trip to power stop takes < 30 µs; the relays then open with the current already at zero.

### 7.5 Smarts: SOC, temperature compensation, cell balance

- **Coulomb counting**: U441 has ±0.2 % gain and ±50 µV (0.5 mA) offset, recalibrated at zero current before each start. Capacity is taken as 0.85 × 25 Ah, so SOC is over-estimated and charging stops early.
- **Rest OCV**: at dawn, after ≥ 2 h with no IG and no charge, and after the IMD check (§7.12), close K901/K902 with the converter off. Path 1 then reads the pack through R902–R904 and the cable sense core. D901 blocks, so no current flows. Accuracy ±0.4 % (≈ ±16 mV/cell ≈ ±2 % SOC near 75 %). SOC is reset to the OCV value; 2 % is subtracted.
- **CAN (car awake only)**: read the car's SOC, min/max cell voltage and DTC status (Q-12). Each wake-up adds an (OCV, car-SOC) calibration pair. Charging is disabled on any HV-battery DTC or a cell spread > 50 mV, and the stop is lowered by the excess spread.
- **Temperature table** (max of TH1–TH4; TH4 sits in the battery's cooling-air inlet as the ambient reference):

| Pack case | Charge | Stop (rest V/cell) | Current |
|---|---|---|---|
| < 0 °C | no | — | 0 |
| 0–10 °C | yes | 3.79 V (until Q-13) | ≤ 0.15 A |
| 10–35 °C | yes | 3.79 V | ≤ 0.28 A |
| 35–45 °C | yes | 3.75 V | ≤ 0.28 A |
| > 45 °C | no (resume < 42 °C) | — | 0 |
| ≥ 50 °C | hardware OTP (U502 ch4 on TH1, U506 ch2 on TH2) | | |
| ≤ −18 °C or sensor/harness open | hardware cut (U508 ch2/ch3 on TH1/TH2) | | |

- **Open-sensor-safe hardware OTP** (review M4): an open NTC reads cold (2.50 V on a 10 kΩ pull-up), so the OTP comparators alone are blind to it. U508 ch2/ch3 pull PERMIT low when NTC_P1/P2 exceed VTH_OPEN 2.199 V, which an open sensor (2.50 V, 0.30 V margin) or a pack colder than −18 °C reaches. Charging is not allowed below 0 °C anyway, so the cold cut costs nothing. A short reads hot and trips the OTP. TH1/TH2 run in their own cable (W5, J706); the firmware pair TH3/TH4 in W11/J708. The hysteresis resistors R511/R523 shift the TH1/TH2 ADC readings by a known ~45 mV that depends on PERMIT; firmware subtracts it using PERMIT_SNS (review MINOR 4).

- **Anomaly terms** (the Li-ion counterpart of NiMH dT/dt and −dV): stop and log when the case–inlet temperature difference rises > 2 K/h while charging, when dV/dAh departs > 30 % from the learned curve, or when path 1 and path 2 disagree by > 5 V.
- **Budgets**: ≤ 2.4 Ah per day; ≤ 10 % SOC per parking period (HZ-6).
- **Why imbalance cannot push a cell into trouble.** Every cell in the series string gets the same ampere-hours, so our charge creates no imbalance. It only moves the whole string up. The car's own plug-in charge takes the same string to its own top-of-charge under per-cell supervision. That value is not published (Q-13), but every hardware layer here ends below the lowest credible value (4.00 V/cell): L3 max 3.963 V, L2 3.84 V, L1 3.79 V. A cell that is fine at the car's full charge is therefore fine at ours, as long as the spread is below the margin (~40 mV at L3, ~160 mV at L2). If the owner never plug-charges, the CAN min/max check covers it. When Q-13 gives the real number, the margin argument is redone with it before L2/L3 are raised.
- **Block-voltage taps** were considered and rejected: the Prime's cell-sense harness is inside the sealed pack and shared with the battery ECU, and tapping it adds load and failure points.

### 7.6 Battery end, fuses, wire

- EVM10-5 [P]: 500 VDC (399 V = 80 %), 20 kA (3.3 kA = 17 %), total I²t 105 A²s, minimum breaking 3 × In = 15 A. A 5–15 A fault could only come from the pack through the BE copper upstream of D901. That copper is inside the BE box, short and separated by 5 mm.
- The 2.5 mm² cable withstands (143·2.5)² = 128 kA²s, 1200 × the fuse I²t. Unfused tap leads ≤ 0.3 m, double insulated.
- **G9KB-1A** [P]: reinforced 600 V coil–contact, double break, 3.6 mm gap, 600 VDC 1 A make/break, −40…85 °C. Coil 12 V 235 mA (2.8 W pull-in), held at 45–60 % by PWM. The relays switch only at zero current: D901 blocks the pack and the converter stops first. The open contact sees ≤ 400 V in normal operation (our side unpowered), ≤ 820 V only if the converter runs with the relays open (fault), within the 2500 VAC rating. Both relays switch together (one K_IN). **Weld check** with both commanded open and the converter off: a welded K902 puts our HV_N on the car's pack negative, and the IMD then reads the car's chassis midpoint (~±175 V). A welded K901 pulls our side toward pack + through the 6 MΩ sense chain, and the IMD reads negative. Either one inhibits charging and is logged. The coil supply runs through the lid switches (HVIL, §7.13); D902/D903 carry the coil current when a lid opens.
- D901: 0.85 V × 0.3 A = 0.26 W. Sense string R902–R904: 3 × 1 MΩ TNPW1206 (≤ 70 V, 5 mW each); a shorted sense core draws ≤ 133 µA.

### 7.7 Sensing ranges

- HV dividers 6 × 1 MΩ / 12.7 kΩ (ratio 473.4, TNPW 0.1 %): 420 V gives 0.887 V into the ±1 V AMC3330 range. Path 2 bleeds the 0.8 µF output to < 60 V in 9.6 s.
- Current: 0.4 A × 0.1 Ω = 40 mV into the ±50 mV AMC3302 range. The −36 µA input bias through the matched 10 Ω filters cancels (10 nA mismatch → 0.1 µV).

### 7.8 Auxiliary supplies and power budget

- AUX12 (LM5164, 300 kHz, 12.1 V) starts from the string Voc (EN ~15 V; hot Voc 17 V), then runs from VINT through D603. +3V3 by a second LM5164.
- Load ≈ 3 W from PV: relays 1.15 W held, gate drive 0.5 W, three AMC low sides 0.4 W, MCU/CAN/EEPROM 0.2 W, references/comparators/LEDs 0.15 W.

### 7.9 PERMIT levels, latch hold-up and relay power-good

- High: R518 4.7 kΩ against ~40 µA of load (hysteresis resistors, TPL input, read-back) gives ≥ 3.1 V.
- Low, MCU in reset: ≤ 108 µA back-feed into R519 (1 kΩ) gives ≤ 0.2 V.
- **Low, latched with the MCU still driving MCU_RUN high** (review MINOR 5): 0.7 mA through R518 into D501 gives PERMIT ≤ 0.58 V at −40 °C (VOL 0.10 + Vf 0.48 [I]). That is under the 0.7 V UCC27282 EN-off minimum [P] and the 1.17 V LM5176 EN threshold (`permit_latched_cold_v`). R518 was raised from 2.2 kΩ to cut this current. The relays no longer depend on that level: D510 pulls K_IN directly to Q̄ (≤ 0.55 V cold vs TPL7407 VIL 0.9 V, `k_in_latched_cold_v`).
- R520 = 100 kΩ: K_IN reaches 3.0 V against the TPL7407's 1 MΩ input pull-down [P] (VIH 1.5 V).
- **Latch hold-up** (review M7): U503 runs on LATCH_VCC = +3V3 through D512 into a 0.1 F supercap C521 (Eaton KW, −40…85 °C, not AEC-Q). R530 220 kΩ bleeds it with τ = 6.1 h. A 10-minute cloud leaves 2.74 V (`latch_hold_10min_v`, minimum 1.65 V), so the trip survives brownouts. After 10 h of dark it is at 0.58 V, the flip-flop has forgotten, and the ~CLR RC (R531/C523, discharged through D513) clears it when LATCH_VCC returns: one trip per day, as intended. OVP_TRIP_N is pulled up on LATCH_VCC (100 kΩ), so PRE stays high while the comparators are unpowered at night. The unpowered-LM2901B output leakage at 85 °C is a test item (V-11). Firmware also stores every trip in EEPROM and refuses to restart without a dawn-to-dawn gap.
- **Relay power-good** (review M7): U508 ch1 holds K_IN low until AUX_IN ≥ 18.1 V (off at 16.7 V; 10 ms filter rides through pull-in). Firmware closes the relays only after the string has held up under the converter's own load, and allows at most 3 relay cycles per day.

### 7.10 Thermal and efficiency

- At 120 W out: MPPT 2 × 1.2 W, DCX FETs 0.35 W, T301 1.3 W, bridge 0.6 W, aux 2.5 W → 127.4 W in (94.2 %), plus D901 0.26 W at the battery end.
- Box rise ≈ 7.2 W × 1.2 K/W = 9 K. No fan needed; the connector and driver remain (Q-8).
- OTP: firmware derating at RT301 > 95 °C; comparator ch3 at RT302 ≈ 105 °C.

### 7.11 Sequencing (firmware, bounded by hardware)

1. Dawn: AUX up, then MCU, then self-test (references, both AMC paths agree at zero, latch clear).
2. Rest OCV (§7.5).
3. Decide (SOC, temperature, budgets, CAN if awake).
4. PERMIT high: DCX PWM at 95 kHz, LM5176 soft start, MPPT perturb-and-observe every 100 ms plus a global sweep every 10 min. The limiter acts by itself.
5. Stop: VSET high, then PWM off, then I_HV < 5 mA, then K901/K902 open.
6. Log every state change and trip to EEPROM (wear-levelled ring) and the UART.
7. Insulation check (§7.12) before step 2 and hourly while charging (relays open for ~1 s, converter running).

### 7.12 HV-to-chassis insulation and insulation monitoring (review B1, M3)

**The insulation is now designed.** v0.2 put HV copper and parts on a chassis-bonded thermal pad and HV-side screws, with no rule covering that path. In v0.3:

- **CHASSIS is a domain** (floats on GND at 0 V) with reinforced HV↔CHASSIS and PACK↔CHASSIS barriers at 420/399 V DC: 10 mm creepage, 8 mm clearance (IEC 60664-1 F.4 PD2 IIIa 500 V row, ×2; F.2 for 6 kV). The plated holes H701–H704 are CHASSIS, bonded to GND once by NT701.
- **Edges and holes**: HV and PACK carry `edge_clearance_mm = 10`, so the `.kicad_dru` has edge and hole rules from HV/PACK copper to the board edge and every mounting hole on both boards. H705/H706 (east-edge supports) and H901–H904 get a 13 mm keepout (10 mm plus the M3 head radius) and PA66 standoffs with nylon screws. They stay compliant even if someone fits a metal screw. Hole positions are `place.fixed` with the enclosure drawing as the source.
- **No thermal path under HV**: the box floor has a pedestal with an insulating gap pad only under the LV power area (MPPT FETs and inductors, Q301/Q302). Under the HV section (x > 145 mm) the floor is a pocket ≥ 10 mm deep, lined with polypropylene sheet (second layer, not credited). D301–D304 cool on top copper only. T301's core goes to the lid through an insulating gap pad; the core sits on the LV side of the reinforced TIW. HV THT leads are clipped to ≤ 1.5 mm. The battery-end board stands on 10 mm standoffs with no thermal interface; D901 dissipates 0.26 W.

**Insulation monitor (review M3).** Each pole has a permanent 11 × 10 MΩ chain to CHASSIS (110 MΩ; ≥ 108.9 MΩ with tolerance, meeting REQ-14's 100 MΩ per pole). This is a protective impedance: ≤ 4.2 µA even with one resistor shorted, ≤ 42 V per resistor. U461 (AMC3330, HGND = HV_N) reads chassis-to-HV_N on the 220 kΩ tap (0.84 V at 420 V), and U462 offsets the result to 1.67 V so negative readings are kept. Q461 (BSS123Q, ≤ 38 V) shorts one 10 MΩ of the P pole.

- **Measurement**: relays open, converter running unloaded. Firmware holds the output at 200–300 V through the MPPT setpoint, and the path-2 CV loop (367.8 V) bounds it below L3 without firmware. Read V_x with Q461 off and with it on, and V from path 2. Two readings and two known bridge values give both pole insulations. A symmetric fault shows as the missing 2.8 % shift between the two points.
- **Action**: refuse to close below 500 Ω/V (210 kΩ, ISO 6469-3 DC), warn below 1 MΩ, log every reading. Run it before every close and hourly while charging. The bridge loads the car's monitor by < 0.5 % when the relays are closed.
- **Why permanent rather than switched**: a switch at the chassis end must block the full pole voltage, and no small chassis-referenced switch can block the N pole's polarity. At 110 MΩ the permanent bridge already meets REQ-14, so only the 10 MΩ range step is switched. That switch sees ≤ 38 V.

### 7.13 HV terminals, interlock and service (review M5)

- J301, J901 and J902 are now WAGO 236 CAGE CLAMP PCB terminal blocks (10 mm pitch; voltage rating [unverified], V-5), wired once at installation and opened only with a tool. They sit under a tool-opened polycarbonate inner cover (IPXXB). No pluggable header carries pack potential.
- **HVIL**: the relay-coil supply runs AUX12 → S701 (main-box lid) → J703/W4 → S901 (battery-end lid) → K_SUP → coils. Opening either lid drops both relays within the coil release time, at ≤ 0.3 A, inside the G9KB's 1 A break rating. D902/D903 carry the coil current.
- **Service procedure** (install guide): READY off, remove the car's service plug (Toyota procedure), wait 10 min [P], measure < 60 V at J902, then open our battery-end box. The tap leads stay live from the cell side until the service plug is out. That is labelled on the battery cover. No step unplugs anything at pack potential.

## 8. Parts

One PartDef per distinct part is in [parts.py](parts.py): MPN, datasheet, pin and rating provenance, lifecycle, second source. Instances and values are in [out/bom.csv](out/bom.csv) (644 instances, 137 distinct). Key parts and stress:

| Role | Part | Rating | Worst stress |
|---|---|---|---|
| MPPT controller ×2 | TI LM5176QPWPRQ1 (symbol generated: KiCad types VOSNS as output) | 60 V abs | VIN ≤ 33 V, VOSNS ≤ 38 V (63 %) |
| FET ×12 | Infineon IAUC100N10S5L040 | 100 V, 4 mΩ | ≤ 38 V + ringing (≤ 50 %) |
| Ideal diode ×2 | TI LM74700QDBVRQ1 | 65 V | 33 V |
| HB driver | TI UCC27282QDRCRQ1 | HS 100 V | 38 V |
| Transformer | custom ETD39 4:88 | §7.3 | §7.3 |
| Rectifier/OR/blocking ×8 | Vishay VS-6ESH06HM3/86A | 600 V 6 A | 420 V (70 %) |
| Isolated amp ×4 | TI AMC3330QDWERQ1 ×3 (paths 1, 2, IMD), AMC3302QDWERQ1 | reinforced, VIOWM 1700 VDC | 420 V (25 %) |
| Comparator ×4, latch, WDT, refs ×2 | TI LM2901BQDRQ1, SN74LVC2G74QDCURQ1, TPS3850G33QDRCRQ1, LM4040QBIM3X2.5 | — | — |
| Limiter / amps | TI TLV9062QDRQ1 ×2, TLV9001QDBVRQ1 ×6 | 6 V | 3.3 V |
| MCU | Microchip dsPIC33CK256MP505-E/PT (CAN FD, 48-TQFP), NDK NX3225GA 20 MHz AEC-Q200 crystal (±200 ppm worst case) | 3.0–3.6 V | 3.29 V |
| Resonant inductor | Coilcraft XAL7070-561MEB [unverified ratings] | ~20 A rms | 7.5 A rms |
| PV-node clamp ×2 | Littelfuse TPSMB43A | VWM 36.8 V | 35 V |
| IMD | Vishay CRCW1206 10 MΩ ×22 [S], Diodes BSS123Q range switch | 200 V each / 100 V | 38 V each / 38 V |
| Latch hold-up | Eaton KW-5R5C104-R 0.1 F 5.5 V (−40…85 °C; industrial, no AEC-Q found) | 5.5 V | 3.0 V |
| CAN | TI SN65HVD230QDRQ1 | bus −7…16 V | 12 V car system |
| Log | Microchip 25LC256-E/SN | 1M cycles | wear-levelled |
| Aux bucks ×2 | TI LM5164QDDARQ1 | 100 V 1 A | 38 V, 0.25 A |
| Disconnect ×2 | Omron G9KB-1A DC12 (custom footprint) | 600 VDC, reinforced coil–contact | 399 V, 0.3 A (zero-current switching) |
| Fuse ×2 | Eaton EVM10-5-2P (custom footprint) | 500 VDC 20 kA | 399 V, 3.3 kA |
| HV out caps ×8 | TDK CGA6L1X7T2J104K160AC | 630 V | 420 V (67 %) |
| Precision R | Vishay TNPW 0.1 % 25 ppm | 100/200 V | ≤ 70 V per divider resistor |
| Shunts | Vishay WSK2512 5/10/100 mΩ | 1 W | 0.33 W |
| Connectors | Phoenix MSTBA 2,5 (LV); WAGO 236-302/-303 CAGE CLAMP 10 mm (HV, not pluggable; voltage rating [unverified]) | — | — |
| Lid switches ×2 | sealed snap-action NO, ≥ 1 A 30 V (part chosen with the enclosure) | — | 0.47 A pull-in |
| Array | Maxeon C60 ×56 (8 columns), Vishay V10P45 ×8 | — | 7.5 A, 5.7 V reverse |

Unverified MPN details (download blocked or not yet read) are tagged in parts.py: Littelfuse TPSMB39A/43A, Nexperia BAT46WJ, onsemi SBAS21/SMMBTA42, TDK NTCG and 220 pF 630 V, WAGO 236 voltage rating, Coilcraft XAL7070 ratings, Eaton KW footprint pitch, Kingbright red LED, generic pack NTCs. Datasheets read for v0.3 [P]: NDK NX3225GA (automotive sheet), Diodes BSS123Q DS43455, Broadcom ACPL-K30T and Infineon BSS127 / Diodes FMMT560 (considered for IMD switching, not used: §7.12).

## 9. Placement and mechanical constraints

Relations are in design.py `placement()` and compiled to [out/intent.yaml](out/intent.yaml) and per board in `out/board-*/intent.yaml` (143 relations plus inferred ones):

- **Main board** 200 × 140 mm, 4 layers, 2 oz, in a finned die-cast IP67 box. Floorplan: MPPT west, DCX centre, HV section east (x > 150 mm), safety/MCU south, aux north.
- **Edges and glands**: J101/J201 PV gland west; J301 EMC gland (360° screen) east; LV harness gland south.
- **Barrier band** 10 mm on all layers with a ≥ 2 mm slot under T301 and the three isolators (`straddle`, `keepout`). `separate()` is generated for every barrier and also written to the `.kicad_dru`.
- **Hot loops**: buck and boost loops per channel, the half-bridge loop and the rectifier loop, all on the top layer. Gate resistors and bootstrap caps `tight` to their pins. Kelvin routing for all shunts (custom `kelvin`). `diff_pair` for the AMC outputs and CAN.
- **Thermal and insulation** (§7.12): LV power parts on the pedestal (`thermal_pedestal`); T301 core to the lid; D301–D304 on top copper only; no HV copper on B.Cu near the pedestal. HV/PACK copper 10 mm from edges and holes (DRU `edge_clearance`/`hole_clearance`); `keepout_around` 13 mm at H705/H706/H901–H904; holes `fixed` from the enclosure drawing. RT302 between T301 and Q301. U401 and U421 kept apart (`far`) against common-cause damage.
- **IMD chains** (`protective_impedance`): straight chains across the barrier band, ≥ 4 resistors inside it and nothing else there.
- **HV terminals** under an inner cover (`hv_cover`); crystal `tight` to the MCU.
- **Heights**: T301 42 mm, bulk caps 11 mm, relays 51 mm.
- **Battery-end board** 140 × 100 mm, 2 layers, 2 oz. F901/F902 `tight` to J902; relays ≥ 20 mm apart (Omron); coil pins toward J903 with a 10 mm band; J901/J902 north, J903 south.
- Custom footprints (T301, G9KB, EVM10-2P) are to be drawn from the cited drawings (waived `lib.footprint_custom`).

## 10. Verification plan

| ID | Test | Pass |
|---|---|---|
| V-1 | Roof template on the actual Prime | field fits, ≥ 40 mm margins |
| V-2 | String IV cold/hot (cell samples) | Voc(−40 °C) ≤ 23 V for 28 cells |
| V-3 | PV simulator, two mismatched channels, shading | ≥ 98 % static MPPT; ≥ 92 % efficiency |
| V-4 | Battery emulator 285–399 V | cap 0.30 A ± 3 %; stable |
| V-5 | Hipot 4.25 kVrms LV↔HV/PACK and HV/PACK↔chassis (IMD chains lifted; type 60 s, routine 1 s); T301 PD; read WAGO 236 voltage rating | no breakdown; PD < 10 pC at 1.5 × 420 V |
| V-6 | 500 V megger HV↔chassis, installed (with the IMD bridge) | ≥ 100 MΩ per pole |
| V-7 | Fault injection: firmware ignores stop; path 1 open; FB top open; each AMC unpowered; U422 stuck low; emulator disconnected at full power; current limiter disabled | L2, L3, L3b, L3-OC and DIAG behave as in §7.4 |
| V-8 | Short the HV cable at J901 from a 400 V/≥ 3 kA source with K901 closed; repeat with D901 shorted | no current; then F901 clears |
| V-9 | Thermal at 60/85 °C; heat TH1/TH2 to 50 °C | Tj ≤ 80 %; OTP trips and recovers |
| V-10 | −40 °C start, 85 °C soak, 500 cycles | functional |
| V-11 | Halt the MCU; stuck PWM pins (DCX on-time trip); 20 kHz DCX PWM; brownout during a latched trip; unpowered-comparator leakage on OVP_TRIP_N at 85 °C; log integrity after power loss | PERMIT low < 1 ms; latch held through a 10-min brownout, cleared next dawn; log intact |
| V-12 | Night drain on the IG input | < 10 µA |
| V-13 | IG off: CAN analyser on the OBD port shows zero frames from us with firmware forced to transmit; ISO 7637-2 on J702 | silent; no damage |
| V-14 | CISPR 25 | class 3 |
| V-15/16 | ISO 16750-3 vibration; IP67 | pass |
| V-17 | In car, READY and parked: Techstream current includes ours (Q-4); no P0AA6 | pass |
| V-18 | Stop accuracy: our SOC vs CAN SOC over 10 cycles; temperature table on a heated pack mock-up | stop ≤ 80 % true SOC, never > 3.79 V/cell at rest until Q-13 |
| V-19 | Reverse string 1 h; 8/20 µs surge on PV inputs | no damage |
| V-20 | Output bleed | < 60 V in 10 s |
| V-21 | SIMPLIS/PSpice: PV loop, CV/CC limiter, DCX on a stiff pack; then bench Bode | ≥ 45° phase margin |
| V-22 | C60 polarization, 4 weeks at +23 V to grounded aluminium | < 1 % loss |
| V-23 | Three park-charge-wake cycles on the Prime with Techstream: SOC jump, DTCs | no DTC; car SOC converges; gate for enabling parked charging |
| V-24 | IMD: 200 kΩ, 1 MΩ and 10 MΩ from each pole and both poles to chassis; welded K901/K902 (jumpered) | each detected; 210 kΩ refused |
| V-25 | Open each lid while charging at the cap; unplug-attempt audit of J301/J901/J902 | relays drop; no tool-free access to pack potential |
| V-26 | Back-feed: one channel's FB tied 2 % low, DCX unloaded; limiter at full cut | PVx_P ≤ 34.5 V; no circulation > 50 mA |

## 11. Sources

- Toyota, *Dismantling Manual 2017–2022 Prius Prime* T-DM-017-D [P]: https://techinfo.toyota.com/techInfoPortal/resources/jsp/siviewer/index.jsp?href=dm/T-DM-017-D/xhtml/T-DM-017-D.html&locale=en&openSource=TechinfoPrelogin
- Toyota, *Prius PHV launch (Japan)*: 25 Ah 3.7 V cells, 8.8 kWh, solar charging 6.1/2.9 km/day [P]: https://global.toyota/en/detail/15055900
- T. Miyoshi, "Solar Charging System for Prius PHV", J. JSAEM 25(4):379–382, 2017, doi:10.14243/jsaem.25.379 (pump charging, 3 DC/DCs, 180 W) [P]
- Toyota patent US11628736B2 "Solar charging system and vehicle" (relay to the drive battery while parked) [P, summary]: https://patents.google.com/patent/US11628736B2/en
- Toyota dismantling manuals, Gen 1 / Gen 3 / ZVW35 PHV (relays on both cables, service plug) [P]: techinfo.toyota.com prelogin docs `1stprius.pdf`, `priusdisman3rd.pdf`, `priusphvdisman.pdf`
- Service-plug split [S]: https://www.vehicleservicepros.com/service-repair/battery-and-electrical/article/21197122/a-look-at-hybrid-and-ev-battery-service ; https://fewstreet.com/2023/06/14/replacing-gen-2-prius-battery-modules.html ; PHV junction-block training deck (SMRB/SMRP/SMRG, CHRB/CHRG) [S]: https://www.slideserve.com/gerda/prius-phv
- PHV solar cell efficiency and press coverage [S]: https://www.pv-magazine.com/2017/02/21/toyota-debuts-new-prius-with-rooftop-pv-option-in-japan/
- SunPower C60 bin sheet [P]: http://eshop.terms.eu/_data/s_3386/files/1379942540-sunpower_c60_bin_ghi.pdf
- Argonne National Laboratory, D3 2017 Toyota Prius Prime teardown (95 cells, 19 × 5, 351.5 V, 25 Ah) [P]: https://www.anl.gov/taps/d3-2017-toyota-prius-prime
- NDK NX3225GA automotive crystal sheet [P]: https://cdn.eicom.ru/media/PDF/1296309.pdf ; Diodes BSS123Q DS43455 [P]: https://www.diodes.com/assets/Datasheets/BSS123Q.pdf ; Broadcom ACPL-K30T AV02-4500EN [P]: https://docs.broadcom.com/doc/AV02-4500EN
- Isolation tables (IEC 60664-1 via TI SLUP419; IPC-2221B) [P via repo]: [docs/topics/rules/isolation-creepage.md](../../docs/topics/rules/isolation-creepage.md)
- Datasheets read [P] (revisions and pages in parts.py): TI LM5176-Q1 SNVSB46B, LM74700-Q1 SNOSD17G, INA186-Q1 SBOS386B, TLV900x-Q1 SBOS980G, TLV906x-Q1 SBOS966H, UCC27282-Q1 SLUSDN5D, AMC3330-Q1 SBASA35B, AMC3302-Q1 SBASA84A, LM2901B-Q1 SLCS142H, SN74LVC2G74-Q1 SCES563C, TPS3850-Q1 SBVS264B, LM4040-N-Q1 SNOS633N, TPL7407LA-Q1 SLRS074, LM5164-Q1, SN65HVD230Q-Q1 SGLS398A; Microchip DS70005349K (dsPIC33CK256MP508 family), DS20005715A (25LC256); Infineon IAUC100N10S5L040; Vishay VS-6ESH06HM3, TNPW e3 (28758), WSK2512 (30108); Omron G9KB K340-E1-06; Eaton EVM10 ELX1304.
