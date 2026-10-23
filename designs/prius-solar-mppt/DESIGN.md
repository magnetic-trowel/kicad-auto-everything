<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Prius Prime solar MPPT charger: design

Status: engineering draft v0.2 (2026-10-23), encoded in [design.py](design.py) / [parts.py](parts.py) and checked by `kaesynth build` (0 errors, 0 warnings, 32 waivers with reasons; KiCad ERC 0 errors; netlist round trip identical for the system and both boards). **Not for fabrication**: BLOCKING questions Q-3, Q-4, Q-5, Q-6 and Q-10 are open and no qualified HV engineer has reviewed it. Netlist summary: [CONNECTIONS.md](CONNECTIONS.md); checks: [out/report.md](out/report.md).

Evidence tags: [P] read in the primary source, [S] secondary (distributor page, snippet, forum, press), [V] vendor claim, [I] our inference.

## 1. Brief

> "I want to put solar panels on my Prius. It should take a bunch of C60s in strings and mppt them. They should fit on the top roof so you can measure the size of the roof of a 2017 Prius and shrink it a little bit for margins. It should take that raw voltage, step it up, and dump it into the battery. It should make sure that the battery can't go over voltage. It should make sure that if the wires outside of the battery are shorted, that the battery can't dump, you know, the 200 or whatever volts into it. It should make sure it doesn't overheat, so it might need a fan depending on how much current it's pushing. Or maybe it just has a bit of an aluminum heatsink."

Follow-ups (2026-10-23): "on the prius it must work on or off. it will have to have some smarts, and to be weak enough that the batteries can't get themselves in trouble. so that means it would have to stop charging by 80%, have a voltage clamp, it would need temp compensation, etc. also i know on older prius the pack was electrically split in two while off. check to see if that's still the case. this is a complex board. that's the point" and "it's a prius prime with li-ion".

**Summary.** 56 C60 cells (two 28-cell strings, ≤ 23 V) feed two analog 4-switch buck-boost MPPT stages into a 26–36 V bus. A fixed-ratio, reinforced LLC "DC transformer" (1:22) lifts it to the Prime's 285–399 V pack. The charger taps the pack on the cell side of the system main relays, so it charges with the car on or off. Because the car's battery ECU sleeps while parked, the board carries its own supervision: isolated pack-voltage and charge-current sensing, coulomb counting with rest-OCV correction, four pack-case temperature sensors, a firmware stop at 75–80 % SOC, a firmware-free analog CV/CC clamp, an independent latching overvoltage/overcurrent trip, and a **hardware current cap of 0.30 A (C/83)**. At that cap, even with every firmware layer dead, two full sunny days pass before the pack goes from 80 % to 100 %. A battery-end board holds a fuse on each pole, a blocking diode and a 2-pole disconnect.

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
| REQ-7 | Weak by design: with all firmware failed, ≥ 2 sun-days from 80 % to 100 % SOC |
| REQ-8 | Stop by 80 % on its own SOC estimate (coulomb + rest OCV + CAN when awake); target 75 %; ≤ 3.95 V/cell average at rest |
| REQ-9 | Firmware-free clamp (L2 4.00 V/cell) and latch (L3 4.12 V/cell on HV_P) |
| REQ-10 | Own pack-case NTCs; charge 0–45 °C; temperature-compensated stop voltage; hardware OTP 50 °C |
| REQ-11/12 | Pack cannot feed our wiring: D901 + fuse per pole (≥ 500 VDC, ≥ 20 kA) + 2-pole disconnect, at the battery end |
| REQ-13/14 | Reinforced LV↔HV/PACK (10 mm creepage, 8 mm clearance, ≥ 4250 Vrms parts); ≥ 100 MΩ, no Y-caps |
| REQ-15/16 | No overheating; −40…+85 °C ambient |
| REQ-17 | Firmware faults contained by hardware (watchdog, analog CV/CC, PERMIT wired-AND, safe reset state) |
| REQ-18/19 | No 12 V battery drain; CAN read-only, transmitter physically off unless IG is on |
| REQ-20…25 | EMC CISPR 25 class 3; HV wiring practice (unfused tap leads ≤ 0.3 m); event log; reverse string; output bleed < 60 V in 10 s; AEC-Q parts |

## 3. Assumptions and open questions

Assumptions ASM-1…8 are in design.py. The important ones:

- **Roof** (ASM-1): Toyota covered about 0.8 m² of cells on this roof (180 W at ~22.5 % [S]) and left the curved edges bare. The 56-cell field (0.86 m² of cells) assumes a similar flat area. Q-3 (template) decides; strings of 28–40 cells work.
- **Cell window** (ASM-2/3): 3.00–4.20 V (NMC-class), giving 285–399 V for the pack. The car's own full charge is about 4.10 V/cell average [I]. OCV at 80 % SOC is 3.97–4.02 V [I]. Calibrated on the car through CAN (V-18).
- **Pack short circuit** ~3.3 kA (ASM-4, [I]).
- **Pack case** is chassis potential and isolated from the cells [P: DM], so NTCs bolted to it are LV parts (ASM-7).
- **Thermal**: pack ~70 kJ/K and ~10 W/K to the cabin with its fan off (ASM-8, [I]).

| ID | Question | Status |
|---|---|---|
| Q-1 | Charge only while READY, or also parked? | **Answered**: both (user, 2026-10-23) |
| Q-2 | Which pack? | **Answered**: 2017 Prius Prime Li-ion (user); NiMH variant removed |
| Q-3 | Roof template: confirm the 8 × 7 field | **BLOCKING** |
| Q-4 | Prime repair-manual pages for the HV junction block: SMRB/SMRP/SMRG, CHRB/CHRG, current-sensor position and cell-side studs. Our − tap should be on the relay side of the car's current sensor so the battery ECU counts our current when awake | **BLOCKING** |
| Q-5 | Who installs the pack-side tap (HV-trained, service-plug procedure, 10-min wait [P]); insurer/registration/warranty | **BLOCKING** |
| Q-6 | Array fixing (bonded laminate vs rails) | **BLOCKING** |
| Q-7 | C60 sheet asks for positive ground [P]; we bond PV− to chassis (test V-22) | open |
| Q-8 | Optional fan | default no |
| Q-9 | T301 vendor; hipot/PD test ownership | open |
| Q-10 | How the Prime battery ECU re-estimates SOC after charge added while it slept, and whether it sets DTCs (V-23). Parked charging ships disabled until V-23 passes | **BLOCKING** |
| Q-11 | Where the service plug sits in the string | open (firmware handles < 280 V / open) |
| Q-12 | Toyota OBD PIDs for SOC, min/max cell voltage and DTC status on the Prime (community lists exist [unverified]); without them firmware stops at 3.90 V/cell | open |

**What happens to the car's SOC estimate** (Q-10, [I]): no Toyota document on this was found. While the car sleeps, its battery ECU counts nothing, so after a sunny day its stored SOC is low by our added charge (≤ 2.4 Ah ≈ 10 %). Li-ion ECUs normally correct SOC from rested open-circuit voltage at wake-up. The Prime should therefore see a jump toward the true value, and its plug-in and hybrid limits are voltage-based per cell, so they still protect the cells. The DTC risk (a "SOC/voltage inconsistency" or capacity code) cannot be argued from documents, so it is a test: V-23 runs three park-charge-wake cycles with Techstream logging before parked charging is enabled by default, and the per-parking budget (≤ 10 % SOC) bounds the jump. Toyota's own design avoided this question by keeping the BMS awake (§1.1).

## 4. Hazards

The full table, with implementing parts and single-fault flags, is in design.py and [out/report.md](out/report.md). Interlock chains:

| ID | Hazard | Mitigation (implemented by) | 1-fault safe |
|---|---|---|---|
| HZ-1 | Shock: 285–420 V on our cable/boards; any HV/PACK net up to 420 V to chassis under one insulation fault | Reinforced barriers (T301, U401/U421/U441, K901/K902 coil–contact), 10/8 mm PCB, screened cable, metal IP67 boxes, both poles open when idle, bleed < 60 V/10 s | yes |
| HZ-2 | Short in our cable/board lets the pack dump kA | D901 blocks pack→cable; F901/F902 (20 kA) first from each pole; K901/K902 open | yes |
| HZ-3 | Pack overvoltage while the BMS sleeps | L1 firmware → L2 analog CV (U802A on own reference U801) → L3 latch (U421→U422→U502 ch1→U503→PERMIT) → L3b VINT latch → L2b LM5176 ceiling; cap 0.30 A | yes |
| HZ-4 | Cell imbalance pushes one cell high | Common series current; stop below the car's own full charge; CAN min/max cell check (§7.5) | yes |
| HZ-5 | Our SOC drifts | Conservative capacity, dawn OCV reset, CAN cross-check; L2/L3 bound it | yes |
| HZ-6 | Car SOC/DTC disturbed | Per-parking budget, V-23 gate, tap position (Q-4) | **no** (until V-23) |
| HZ-7 | Hidden insulation fault or false P0AA6 | ≥ 100 MΩ, no Y-caps, < 1 nF to chassis; the car's monitor sees our circuit whenever both are on | yes |
| HZ-8 | Roof arc/hot spot | ≤ 33 V, bypass per 7-cell column, 1 string per input, ideal diode | yes |
| HZ-9 | Array detaches | mechanical (Q-6) | open |
| HZ-10 | Converter overheats | RT301 firmware derate; RT302→U502 ch3 OTP; LM5176 TSD | yes |
| HZ-11 | Firmware hang/wild PWM | TPS3850 window WDT → MCU reset → MCU_RUN pulled down (R519) → PERMIT low | yes |
| HZ-12 | Sensor masks OV | Each isolated amp's DIAG pulls PERMIT low; L3 has its own divider, amp and reference; L2b needs none | yes |
| HZ-13 | Pack disconnects under load | DCX output ≤ 11 × VINT ≤ L2b; L3 latch; 70 mJ in output caps | yes |
| HZ-14 | String reversed | LM74700 + FET | yes |
| HZ-15 | Pack too hot/cold | Firmware window 0–45 °C on 4 NTCs; hardware OTP 50 °C on two (U502 ch4, U506 ch2) | yes |
| HZ-16 | Vehicle transients on IG/CAN | BAS21 + 22.1 kΩ 1206; transceiver −7…16 V bus | yes |
| HZ-17 | Service: our tap is live on the cell side and could bridge an open service plug through 6 MΩ | Relays open when idle; labels; unplug J902 first (install guide) | **procedural** |
| HZ-18 | Crash crushes the HV cable | Routing; D901 and fuses at the battery end | yes |
| HZ-19 | Our CAN node disturbs the car | Transmitter off in hardware unless IG on (Q703 AND Q702 hold RS low only then); unpowered transceiver passive [P] | yes |
| HZ-20 | Relay coil left at 100 % | PWM economiser after 100 ms; watchdog; class F coil | no (thermal only) |

**PERMIT chain** (the hardware interlock): PERMIT is sourced only by MCU_RUN through R518 (2.2 kΩ). Any of these pull it low: U401/U421/U441 DIAG, latch Q̄ via D501, U502 ch3/ch4, U506 ch2, or a watchdog reset (MCU pins tri-state, R519 pulls MCU_RUN down). PERMIT gates U103/U203 EN (via D102/D202), U301 EN, and the relay drive (D503 AND with RELAY_REQ). Worst-case back-feed into a low PERMIT is 108 µA (EN dividers 44 µA, hysteresis resistors 34 µA, R520/D503 30 µA), giving ≤ 0.35 V against the 0.7 V U301 and 0.9 V TPL7407 off thresholds. R520 was raised from 10 kΩ to 100 kΩ for this (§7.9).

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
| DCX | main | VINT bulk, UCC27282 + 2 FETs half-bridge at 95 kHz, split resonant caps, T301 (4:88), VS-6ESH06 bridge, 8 × 100 nF 630 V, J301, temperature sensors |
| HVSENSE | main | Path 1: pack voltage via the battery-end string and cable sense core (U401, G = 1.5). Path 2: HV_P for L3 (U421, G = 1.21). Current: 0.1 Ω return shunt + AMC3302 U441 (G = 1, 4.1 V/A) |
| LIMIT | main | L2: CV and CC integrators (U802) on their own LM4040 (U801); output LIM lifts both PV setpoints |
| SAFETY | main | LM4040 U501, comparators U502/U506, trip latch U503, TPS3850 WDT, PERMIT, TPL7407 coil/fan/LED drivers |
| AUX | main | PV/VINT OR → LM5164 AUX12 (12.1 V) → LM5164 +3V3 |
| MCU | main | dsPIC33CK256MP505, EEPROM log U703, IG sense (Q701), CAN (SN65HVD230Q) with IG-AND-enable transmit gate (Q702/Q703), connectors J701–J707 |
| BATEND | batt_end | J901 (HV in), J902 (pack tap), J903 (coils), F901/F902 EVM10-5, K901/K902 G9KB-1A, D901, sense string R902–R904 |
| ARRAY, HARNESS | off | 8 columns × 7 C60 + 8 bypass diodes; cables W1–W8, IG tap fuse F701/X701, pack-case NTCs TH1–TH4 |

| Domain | 0 V reference | Range | To chassis |
|---|---|---|---|
| LV (PV, VINT, AUX, logic, IG, CAN, pack-case NTCs) | GND, bonded to chassis at H701–H704 | 0–38 V (PV TVS clamp 54 V; IG −150…+112 V pulses) | same |
| HV (T301 secondary, sense high sides, cable, D901/K901/K902 side) | HV_N | 0–420 V | floating: 0–420 V under one insulation fault |
| PACK (cell-side tap, F901/F902) | BAT_TAP_N | 0–399 V | floating with the car's IT system |
| Floating sub-domains | BSTA1/2, BSTB1/2 on the LM5176 switch nodes; DCXBST on HB_SW; AUXBST/V33BST; K1C/K2C/FANC on AUX12; IDA/IDB on the string inputs | | |

| Barrier | Grade | Working V | Creepage / clearance | Basis |
|---|---|---|---|---|
| LV ↔ HV, LV ↔ PACK | reinforced | 420 V / 399 V DC | **10.0 / 8.0 mm**, routed slot ≥ 2 mm under T301, U401, U421, U441 | IEC 60664-1 F.4 PD2 MG III: 400 V row 4.0 mm basic [P via TI SLUP419]; 500 V row 5.0 mm [S] → ×2. F.1 ≤ 600 V OVC II 4 kV, reinforced 6 kV → F.2 5.5 mm; design 8 mm = G9KB requirement. Test 4.25 kVrms |
| HV ↔ PACK | functional | 399 V (relays open only with the converter stopped) | 5.0 / 5.0 mm | IPC-2221B B2 (301–500 V 2.5 mm; +0.005 mm/V above 500 V covers the 820 V fault case: 4.1 mm) |
| HV_P ↔ HV_N | functional | 420 V | 2.5 mm | IPC-2221B B2 |

Parts across barriers: T301 (5.0 kVrms type test, ≥ 10 mm), AMC3330/AMC3302 (4250 Vrms, VIOWM 1700 VDC, CPG ≥ 8 mm, CTI ≥ 600), G9KB coil–contact (5000 VAC, reinforced 600 V, 12.6/8.0 mm) and its open contact (2500 VAC, 600 V).

## 7. Calculations

Numbers below are computed in design.py `calcs()` (limits enforced by the build) or by hand where noted.

### 7.1 Array and the "weak by design" cap

- C60 [P]: 125 mm, Pmp 3.34–3.42 W, Vmp 0.574–0.582 V, Imp 5.83–5.93 A, Voc 0.682–0.687 V, Isc 6.24–6.28 A, −1.8 mV/K, −0.32 %/K.
- **Layout**: 8 columns × 7 rows at 127 mm pitch, field 1016 × 889 mm (laminate 1066 × 939 mm). String A is columns 1–4 (left), string B columns 5–8. Each column is 7 cells with one V10P45 bypass diode. Left/right strings see the same fore–aft curvature.
- String (28 cells): Voc 22.5 V at −40 °C (limit 33 V; 40 cells give 32.2 V), Vmp 16.1 V at 25 °C and 13.8 V at 70 °C. One column bypassed while hot gives 9.9 V, which stays 3.0 V above UVLO-off (`uvlo_off_vs_shaded_vmp`).
- Array 191.5 W at STC, ~150 W at a hot noon. The worst corner is 1.2 suns cold at the lowest pack voltage: 0.81 A (`phys_max_current_a`, envelope 0.85 A).
- **Cap derivation.** Li-ion has no safe overcharge rate, so the cap is set by time to damage, not by heat:
  - At 0.30 A a generous clear day of 8 cap-hours adds at most 2.4 Ah = 9.6 % SOC.
  - From the 80 % stop to 100 % takes ≥ 2.08 sun-days; to 110 %, the onset of plating and cathode damage [I], ≥ 3.1 days (`days_80_to_*`). Those figures assume every firmware layer failed, while L2 and L3 stop it at ≤ 4.12 V/cell first.
  - Daily energy at the cap (~0.7 kWh) matches Toyota's own maximum of 0.58 kWh/day.
  - The cap costs some energy on the best days (array 150 W vs 113 W). The cap wins.
- **Pack temperature.** Joule heat at 0.3 A is I²R ≈ 0.014 W. Even if all 113 W became heat (gross overcharge), the pack would rise ≤ 5.8 K/h adiabatic and 11.3 K steady with its fan off (`pack_rise_*`). Our case NTCs catch that before the 50 °C hardware OTP.

### 7.2 MPPT stage (each channel; LM5176-Q1 equations [P])

- fsw 201 kHz (RT 41.2 kΩ). Boost operation (VINT 26–36 V > Vmp). Ripple at 16 V → 30 V: ΔI = 16·0.47/(22 µH·201 kHz) = 1.7 A.
- XAL1510-223: 7.5 A rms against 10.5 A (71 %); peak 8.4 A against 18.7 A Isat.
- Current sense 10 mΩ: boost peak limit 12 A. In boost mode the shunt carries D·I_L, so 7.5²·0.6·10 mΩ = 0.33 W.
- PV shunt 5 mΩ: 0.28 W. ISNS average-current limit (50 mV − 3 µA·1 kΩ)/5 mΩ = 9.4 A.
- **UVLO (corrected)**: datasheet Eq. 1 is VIN(UV) = VEN(OP)·(1 + R2/R1) − R2·IEN(STBY), with a minus sign [P, p.16]. v0.1 used a plus and was wrong (its real off threshold was below 0 V). Now 1.5 MΩ/137 kΩ: on 11.6 V, off = on − 3.15 µA·1.5 MΩ = 6.9 V.
- PV loop: TLV9001 integrates (VSET − PV/12). Q102 sinks current from ISNS(−) through R_iso (1 kΩ, R103), so I_PV = (50 mV − I_sink·1 kΩ)/5 mΩ, zero at 50 µA (MPPT_OUT 1.65 V). **v0.1 put R_iso and the sink on ISNS(+)**, which raises the current instead; found while re-deriving the loop during encoding. VSET defaults above Voc (PWM pin pulled high), so the stage gives zero power without firmware. D105 lets the limiter raise VSET above the MCU's value. Compensation is initial and tuned in V-21.
- **L2b, VINT ceiling**: FB 442 kΩ/10 kΩ (0.1 %) gives VINT 36.16 V, about 396 V at no load (4.17 V/cell; 390–418 V across the tolerance corners). It is the backstop if both AMC paths fail.

### 7.3 LLC-DCX and T301 (fixed ratio, open loop)

- n = Ns/Np = 88/4 = 22. Half-bridge, so HV ≈ 11·VINT. VINT = 2·(Vpack + 1.6 V)/22 = 26.1 V at 285 V and 36.4 V at 399 V.
- fr = 1/(2π√(0.8 µH·3.2 µF)) = 99.5 kHz. Lr is T301 leakage plus trace (±30 %). Cr is two legs of 16 × 100 nF C0G. fsw is 95 kHz, slightly below fr, for rectifier ZCS.
- At 120 W/380 V: R_ac,pri = 0.811·1267 Ω/22² = 2.1 Ω, Z0 = 0.5 Ω, Q = 0.24. Primary 7.3 A rms (10.4 A peak); Cr ripple ±5.4 V on 100 V parts.
- Lm 18 µH (gapped): Im,pk = 18.1 V·2.63 µs/18 µH = 2.6 A. ZVS needs 0.47 A. Primary total 7.45 A rms.
- Flux: Bpk = 0.095 T on ETD39 (Ae 125 mm²), so N97 loss is ~1.0–1.2 W [I].
- **T301 specification**: ETD 39, N97, 20-pin former; Np 4 turns of litz (~6 mm²), Ns 88 turns of triple-insulated wire; Faraday shield to GND; ≥ 10 mm pin-to-pin creepage; class F. Hipot 5.0 kVrms 60 s type, 4.25 kVrms 1 s routine; partial-discharge extinction > 1.5 × 420 V; Cps < 150 pF. Pins: 1/2 primary start, 3/4 primary end, 11/20 secondary.
- Rectifier VS-6ESH06: ≤ 420 V against 600 V (70 %); ~0.15 W each. Output 8 × 100 nF 630 V X7T (420 V = 67 %).

### 7.4 Overvoltage and current layers (pack-terminal voltages)

| Layer | Mechanism | Threshold | Independent of |
|---|---|---|---|
| L1 | Firmware stop (§7.5): SOC ≥ 75 % target / 80 % max, or rest-equivalent ≥ 3.95 V/cell × temperature table | 375.2 V | — |
| L2 | Analog CV integrator U802A: HV_V_LIM (path 1) vs VREF_CV from U801 | 380.0 V (4.00 V/cell) ±0.9 % | MCU |
| L2-CC | Analog CC integrator U802B: I_HV vs VREF_CC | 0.301 A | MCU |
| L3 | U421 → U422 (G 1.21) → U502 ch1 vs 2.000 V (U501) → latch U503 → PERMIT | 391.6 V on HV_P (4.12 V/cell) ±0.9 % | MCU, path 1, U801, L2 |
| L3-OC | U441 → U442 → U506 ch1 vs 1.641 V → same latch | 0.400 A | MCU, U801 |
| L3b | VINT divider → U502 ch2 → latch | VINT 38.0 V | both AMC paths |
| L2b | LM5176 FB ceiling | 396 V no-load | everything above |
| L4 | Car BMS when awake | car limits | everything here |

Ordering at the tolerance extremes (worst-case sum 0.9 % each): L1 < L2 min by 1.3 V; L2 max < L3 min (minus the 0.9 V D901 drop) by 3.8 V; L3 max = 4.159 V/cell < 4.20 V. The latch clears only at power-on, which is the next dawn. Trip to power stop takes < 30 µs; the relays then open with the current already at zero, so they never break load current.

### 7.5 Smarts: SOC, temperature compensation, cell balance

- **Coulomb counting**: U441 has ±0.2 % gain and ±50 µV (0.5 mA) offset, recalibrated at zero current before each start. Capacity is taken as 0.85 × 25 Ah, so SOC is over-estimated and charging stops early.
- **Rest OCV**: at dawn, after ≥ 2 h with no IG and no charge, close K902 then K901 with the converter off. Path 1 then reads the pack through R902–R904 and the cable sense core. D901 blocks, so no current flows. Accuracy ±0.4 % (≈ ±16 mV/cell ≈ ±2 % SOC near 75 %). SOC is reset to the OCV value; 2 % is subtracted.
- **CAN (car awake only)**: read the car's SOC, min/max cell voltage and DTC status (Q-12). Each wake-up adds an (OCV, car-SOC) calibration pair. Charging is disabled on any HV-battery DTC or a cell spread > 50 mV, and the stop is lowered by the excess spread.
- **Temperature table** (max of TH1–TH4; TH4 sits in the battery's cooling-air inlet as the ambient reference):

| Pack case | Charge | Stop (rest V/cell) | Current |
|---|---|---|---|
| < 0 °C | no | — | 0 |
| 0–10 °C | yes | 3.95 V | ≤ 0.15 A |
| 10–35 °C | yes | 3.95 V | ≤ 0.28 A |
| 35–45 °C | yes | 3.90 V | ≤ 0.28 A |
| > 45 °C | no (resume < 42 °C) | — | 0 |
| ≥ 50 °C | hardware OTP (U502 ch4 on TH1, U506 ch2 on TH2) | | |

- **Anomaly terms** (the Li-ion counterpart of NiMH dT/dt and −dV): stop and log when the case–inlet temperature difference rises > 2 K/h while charging, when dV/dAh departs > 30 % from the learned curve, or when path 1 and path 2 disagree by > 5 V.
- **Budgets**: ≤ 2.4 Ah per day; ≤ 10 % SOC per parking period (HZ-6).
- **Why imbalance cannot push a cell into trouble.** Every cell in the series string gets the same ampere-hours, so our charge creates no imbalance. It only moves the whole string up. The car's own plug-in charge takes the same string to a higher average (~4.10 V) under per-cell supervision. At our lower stop (3.95 V) every cell, including a weak or high one, is below where the car's own charger puts it daily. A cell that is fine at the car's full charge is fine at ours, with ≥ 150 mV of margin. If the owner never plug-charges, the CAN min/max check covers it.
- **Block-voltage taps** were considered and rejected: the Prime's cell-sense harness is inside the sealed pack and shared with the battery ECU, and tapping it adds load and failure points.

### 7.6 Battery end, fuses, wire

- EVM10-5 [P]: 500 VDC (399 V = 80 %), 20 kA (3.3 kA = 17 %), total I²t 105 A²s, minimum breaking 3 × In = 15 A. A 5–15 A fault could only come from the pack through the BE copper upstream of D901. That copper is inside the BE box, short and separated by 5 mm.
- The 2.5 mm² cable withstands (143·2.5)² = 128 kA²s, 1200 × the fuse I²t. Unfused tap leads ≤ 0.3 m, double insulated.
- **G9KB-1A** [P]: reinforced 600 V coil–contact, double break, 3.6 mm gap, 600 VDC 1 A make/break, −40…85 °C. Coil 12 V 235 mA (2.8 W pull-in), held at 45–60 % by PWM. The relays switch only at zero current: D901 blocks the pack and the converter stops first. The open contact sees ≤ 400 V in normal operation (our side unpowered), ≤ 820 V only if the converter runs with the relays open (fault), within the 2500 VAC rating. Weld check at each start: close K902 alone, then K901 alone; path 1 must read 0.
- D901: 0.85 V × 0.3 A = 0.26 W. Sense string R902–R904: 3 × 1 MΩ TNPW1206 (≤ 70 V, 5 mW each); a shorted sense core draws ≤ 133 µA.

### 7.7 Sensing ranges

- HV dividers 6 × 1 MΩ / 12.7 kΩ (ratio 473.4, TNPW 0.1 %): 420 V gives 0.887 V into the ±1 V AMC3330 range. Path 2 bleeds the 0.8 µF output to < 60 V in 9.6 s.
- Current: 0.4 A × 0.1 Ω = 40 mV into the ±50 mV AMC3302 range. The −36 µA input bias through the matched 10 Ω filters cancels (10 nA mismatch → 0.1 µV).

### 7.8 Auxiliary supplies and power budget

- AUX12 (LM5164, 300 kHz, 12.1 V) starts from the string Voc (EN ~15 V; hot Voc 17 V), then runs from VINT through D603. +3V3 by a second LM5164.
- Load ≈ 3 W from PV: relays 1.15 W held, gate drive 0.5 W, three AMC low sides 0.4 W, MCU/CAN/EEPROM 0.2 W, references/comparators/LEDs 0.15 W.

### 7.9 PERMIT levels

- High: R518 2.2 kΩ against ≤ 0.1 mA of load gives ≥ 3.1 V.
- Low: ≤ 108 µA back-feed into R518 + R519 (3.2 kΩ) gives ≤ 0.35 V. U301 EN off ≤ 0.7 V min [P]; TPL7407 VIL 0.9 V [P]; LM5176 EN ≤ 0.6 V, below the 1.17 V operating threshold (standby, not switching).
- R520 = 100 kΩ: K_IN reaches 3.0 V against the TPL7407's 1 MΩ input pull-down [P] (VIH 1.5 V).

### 7.10 Thermal and efficiency

- At 120 W out: MPPT 2 × 1.2 W, DCX FETs 0.35 W, T301 1.3 W, bridge 0.6 W, aux 2.5 W → 127.4 W in (94.2 %), plus D901 0.26 W at the battery end.
- Box rise ≈ 7.2 W × 1.2 K/W = 9 K. No fan needed; the connector and driver remain (Q-8).
- OTP: firmware derating at RT301 > 95 °C; comparator ch3 at RT302 ≈ 105 °C.

### 7.11 Sequencing (firmware, bounded by hardware)

1. Dawn: AUX up, then MCU, then self-test (references, both AMC paths agree at zero, latch clear).
2. Rest OCV (§7.5).
3. Decide (SOC, temperature, budgets, CAN if awake).
4. PERMIT high: DCX PWM at 95 kHz, LM5176 soft start, MPPT perturb-and-observe every 100 ms plus a global sweep every 10 min. The limiter acts by itself.
5. Stop: VSET high, then PWM off, then I_HV < 5 mA, then K901, then K902 open.
6. Log every state change and trip to EEPROM (wear-levelled ring) and the UART.

## 8. Parts

One PartDef per distinct part is in [parts.py](parts.py): MPN, datasheet, pin and rating provenance, lifecycle, second source. Instances and values are in [out/bom.csv](out/bom.csv) (515 instances, 114 distinct). Key parts and stress:

| Role | Part | Rating | Worst stress |
|---|---|---|---|
| MPPT controller ×2 | TI LM5176QPWPRQ1 (symbol generated: KiCad types VOSNS as output) | 60 V abs | VIN ≤ 33 V, VOSNS ≤ 38 V (63 %) |
| FET ×12 | Infineon IAUC100N10S5L040 | 100 V, 4 mΩ | ≤ 38 V + ringing (≤ 50 %) |
| Ideal diode ×2 | TI LM74700QDBVRQ1 | 65 V | 33 V |
| HB driver | TI UCC27282QDRCRQ1 | HS 100 V | 38 V |
| Transformer | custom ETD39 4:88 | §7.3 | §7.3 |
| Rectifier/OR/blocking ×8 | Vishay VS-6ESH06HM3/86A | 600 V 6 A | 420 V (70 %) |
| Isolated amp ×3 | TI AMC3330QDWERQ1 ×2, AMC3302QDWERQ1 | reinforced, VIOWM 1700 VDC | 420 V (25 %) |
| Comparator ×2, latch, WDT, refs ×2 | TI LM2901BQDRQ1, SN74LVC2G74QDCURQ1, TPS3850G33QDRCRQ1, LM4040QBIM3X2.5 | — | — |
| Limiter / amps | TI TLV9062QDRQ1, TLV9001QDBVRQ1 ×5 | 6 V | 3.3 V |
| MCU | Microchip dsPIC33CK256MP505-E/PT (CAN FD, 48-TQFP) | 3.0–3.6 V | 3.29 V |
| CAN | TI SN65HVD230QDRQ1 | bus −7…16 V | 12 V car system |
| Log | Microchip 25LC256-E/SN | 1M cycles | wear-levelled |
| Aux bucks ×2 | TI LM5164QDDARQ1 | 100 V 1 A | 38 V, 0.25 A |
| Disconnect ×2 | Omron G9KB-1A DC12 (custom footprint) | 600 VDC, reinforced coil–contact | 399 V, 0.3 A (zero-current switching) |
| Fuse ×2 | Eaton EVM10-5-2P (custom footprint) | 500 VDC 20 kA | 399 V, 3.3 kA |
| HV out caps ×8 | TDK CGA6L1X7T2J104K160AC | 630 V | 420 V (67 %) |
| Precision R | Vishay TNPW 0.1 % 25 ppm | 100/200 V | ≤ 70 V per divider resistor |
| Shunts | Vishay WSK2512 5/10/100 mΩ | 1 W | 0.33 W |
| Connectors | Phoenix MSTBA 2,5 (LV), GMSTBA 2,5 7.62 mm (HV, IEC 630 V; UL 300 V [unverified]) | — | — |
| Array | Maxeon C60 ×56 (8 columns), Vishay V10P45 ×8 | — | 7.5 A, 5.7 V reverse |

Unverified MPN details (download blocked) are tagged in parts.py: Littelfuse TPSMB39A, Nexperia BAT46WJ, onsemi SBAS21/SMMBTA42, TDK NTCG and 220 pF 630 V, Phoenix GMSTBA item numbers, Kingbright red LED, generic pack NTCs.

## 9. Placement and mechanical constraints

Relations are in design.py `placement()` and compiled to [out/intent.yaml](out/intent.yaml) and per board in `out/board-*/intent.yaml` (108 relations plus inferred ones):

- **Main board** 200 × 140 mm, 4 layers, 2 oz, in a finned die-cast IP67 box. Floorplan: MPPT west, DCX centre, HV section east (x > 150 mm), safety/MCU south, aux north.
- **Edges and glands**: J101/J201 PV gland west; J301 EMC gland (360° screen) east; LV harness gland south.
- **Barrier band** 10 mm on all layers with a ≥ 2 mm slot under T301 and the three isolators (`straddle`, `keepout`). `separate()` is generated for every barrier and also written to the `.kicad_dru`.
- **Hot loops**: buck and boost loops per channel, the half-bridge loop and the rectifier loop, all on the top layer. Gate resistors and bootstrap caps `tight` to their pins. Kelvin routing for all shunts (custom `kelvin`). `diff_pair` for the AMC outputs and CAN.
- **Thermal**: FETs, T301 and the bridge on the box wall through a pad. RT302 between T301 and Q301. U401 and U421 kept apart (`far`) against common-cause damage.
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
| V-5 | Hipot 4.25 kVrms LV↔HV/PACK (type 60 s, routine 1 s); T301 PD | no breakdown; PD < 10 pC at 1.5 × 420 V |
| V-6 | 500 V megger HV↔chassis, installed | ≥ 100 MΩ |
| V-7 | Fault injection: firmware ignores stop; path 1 open; FB top open; each AMC unpowered; U422 stuck low; emulator disconnected at full power; current limiter disabled | L2, L3, L3b, L3-OC and DIAG behave as in §7.4 |
| V-8 | Short the HV cable at J901 from a 400 V/≥ 3 kA source with K901 closed; repeat with D901 shorted | no current; then F901 clears |
| V-9 | Thermal at 60/85 °C; heat TH1/TH2 to 50 °C | Tj ≤ 80 %; OTP trips and recovers |
| V-10 | −40 °C start, 85 °C soak, 500 cycles | functional |
| V-11 | Halt the MCU; stuck PWM pins; log integrity after power loss | PERMIT low < 1 ms; log intact |
| V-12 | Night drain on the IG input | < 10 µA |
| V-13 | IG off: CAN analyser on the OBD port shows zero frames from us with firmware forced to transmit; ISO 7637-2 on J702 | silent; no damage |
| V-14 | CISPR 25 | class 3 |
| V-15/16 | ISO 16750-3 vibration; IP67 | pass |
| V-17 | In car, READY and parked: Techstream current includes ours (Q-4); no P0AA6 | pass |
| V-18 | Stop accuracy: our SOC vs CAN SOC over 10 cycles; temperature table on a heated pack mock-up | stop ≤ 80 % car SOC, never > 3.95 V/cell at rest |
| V-19 | Reverse string 1 h; 8/20 µs surge on PV inputs | no damage |
| V-20 | Output bleed | < 60 V in 10 s |
| V-21 | SIMPLIS/PSpice: PV loop, CV/CC limiter, DCX on a stiff pack; then bench Bode | ≥ 45° phase margin |
| V-22 | C60 polarization, 4 weeks at +23 V to grounded aluminium | < 1 % loss |
| V-23 | Three park-charge-wake cycles on the Prime with Techstream: SOC jump, DTCs | no DTC; car SOC converges; gate for enabling parked charging |

## 11. Sources

- Toyota, *Dismantling Manual 2017–2022 Prius Prime* T-DM-017-D [P]: https://techinfo.toyota.com/techInfoPortal/resources/jsp/siviewer/index.jsp?href=dm/T-DM-017-D/xhtml/T-DM-017-D.html&locale=en&openSource=TechinfoPrelogin
- Toyota, *Prius PHV launch (Japan)*: 25 Ah 3.7 V cells, 8.8 kWh, solar charging 6.1/2.9 km/day [P]: https://global.toyota/en/detail/15055900
- T. Miyoshi, "Solar Charging System for Prius PHV", J. JSAEM 25(4):379–382, 2017, doi:10.14243/jsaem.25.379 (pump charging, 3 DC/DCs, 180 W) [P]
- Toyota patent US11628736B2 "Solar charging system and vehicle" (relay to the drive battery while parked) [P, summary]: https://patents.google.com/patent/US11628736B2/en
- Toyota dismantling manuals, Gen 1 / Gen 3 / ZVW35 PHV (relays on both cables, service plug) [P]: techinfo.toyota.com prelogin docs `1stprius.pdf`, `priusdisman3rd.pdf`, `priusphvdisman.pdf`
- Service-plug split [S]: https://www.vehicleservicepros.com/service-repair/battery-and-electrical/article/21197122/a-look-at-hybrid-and-ev-battery-service ; https://fewstreet.com/2023/06/14/replacing-gen-2-prius-battery-modules.html ; PHV junction-block training deck (SMRB/SMRP/SMRG, CHRB/CHRG) [S]: https://www.slideserve.com/gerda/prius-phv
- PHV solar cell efficiency and press coverage [S]: https://www.pv-magazine.com/2017/02/21/toyota-debuts-new-prius-with-rooftop-pv-option-in-japan/
- SunPower C60 bin sheet [P]: http://eshop.terms.eu/_data/s_3386/files/1379942540-sunpower_c60_bin_ghi.pdf
- Isolation tables (IEC 60664-1 via TI SLUP419; IPC-2221B) [P via repo]: [docs/topics/rules/isolation-creepage.md](../../docs/topics/rules/isolation-creepage.md)
- Datasheets read [P] (revisions and pages in parts.py): TI LM5176-Q1 SNVSB46B, LM74700-Q1 SNOSD17G, INA186-Q1 SBOS386B, TLV900x-Q1 SBOS980G, TLV906x-Q1 SBOS966H, UCC27282-Q1 SLUSDN5D, AMC3330-Q1 SBASA35B, AMC3302-Q1 SBASA84A, LM2901B-Q1 SLCS142H, SN74LVC2G74-Q1 SCES563C, TPS3850-Q1 SBVS264B, LM4040-N-Q1 SNOS633N, TPL7407LA-Q1 SLRS074, LM5164-Q1, SN65HVD230Q-Q1 SGLS398A; Microchip DS70005349K (dsPIC33CK256MP508 family), DS20005715A (25LC256); Infineon IAUC100N10S5L040; Vishay VS-6ESH06HM3, TNPW e3 (28758), WSK2512 (30108); Omron G9KB K340-E1-06; Eaton EVM10 ELX1304.
