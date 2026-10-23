<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Prius solar MPPT charger: design

Status: engineering draft v0.1 (2026-10-23). Not for fabrication: the BLOCKING questions in §3 are open, and a qualified HV engineer has not reviewed the design. The netlist is in [CONNECTIONS.md](CONNECTIONS.md).

Evidence tags: [P] read in the primary source, [S] secondary, snippet or distributor page, [V] vendor claim, [I] our inference.

## 1. Brief

> "I want to put solar panels on my Prius. It should take a bunch of C60s in strings and mppt them. They should fit on the top roof so you can measure the size of the roof of a 2017 Prius and shrink it a little bit for margins. It should take that raw voltage, step it up, and dump it into the battery. It should make sure that the battery can't go over voltage. It should make sure that if the wires outside of the battery are shorted, that the battery can't dump, you know, the 200 or whatever volts into it. It should make sure it doesn't overheat, so it might need a fan depending on how much current it's pushing. Or maybe it just has a bit of an aluminum heatsink."

**Summary.** Two 32-cell C60 strings (≤ 33 V) feed two analog 4-switch buck-boost MPPT stages. These drive a 30–48 V bus, which a fixed-ratio, reinforced LLC "DC transformer" (1:11) lifts to pack voltage. A battery-end board holds a fuse on each pole, a blocking diode and a 2-pole disconnect. By default the charger runs only while the car is READY and taps the car side of the system main relays, so the car's battery ECU keeps control of SOC. Parked charging uses the same hardware but is a BLOCKING decision (Q-1).

## 2. Requirements

| ID | Requirement | Value | Source | Verified by |
|---|---|---|---|---|
| REQ-1 | Array fits the 2017 Prius (XW50) roof, no structural change, margin to edges | baseline cell field 1016 × 1016 mm; ≥ 40 mm to drip mouldings, antenna and glass | brief | V-1 template fit |
| REQ-2 | Cells | SunPower/Maxeon C60, 125 mm; baseline 64 cells; electronics accept 24–40 cells/string | brief | BOM |
| REQ-3 | MPPT per string | 2 independent channels, static tracking ≥ 98 % | brief | V-3 |
| REQ-4 | String voltage | Voc ≤ 33 V at −40 °C (≤ 60 V DC, ISO 6469-3 class A) | derived/standard | §7.1, V-2 |
| REQ-5 | Output | 150–262 V into the traction battery, ≤ 2.0 A, rated 300 W input | brief/derived | V-4 |
| REQ-6 | PV/LV ↔ HV isolation | reinforced; ≥ 8.0 mm creepage and clearance | IEC 60664-1 via TI SLUP419 | V-5 |
| REQ-7 | Added HV insulation to chassis | ≥ 10 MΩ at 500 V (target ≥ 100 MΩ); no Y-capacitors HV→chassis | Toyota repair manual values | V-6 |
| REQ-8 | No overvoltage | ≥ 2 independent layers, one is a firmware-free latch; thresholds in §7.4 | brief | V-7 |
| REQ-9 | Battery cannot feed a fault in our wiring | blocking diode + fuse on each pole + 2-pole disconnect, all at the battery end | brief | V-8 |
| REQ-10 | Battery-end fuses | ≥ 500 V DC, breaking capacity ≥ 20 kA, 5 A | derived (§7.6) | datasheet |
| REQ-11 | No overheating | firmware derating + firmware-free OTP; all semiconductors ≤ 80 % Tj,max at worst case | brief | V-9 |
| REQ-12 | Ambient | −40…+85 °C (cargo area); full power to 60 °C | ISO 16750-4 class (passenger compartment) [I] | V-10 |
| REQ-13 | Firmware failures contained by hardware | watchdog reset; analog CV/CC limits; PERMIT wired-AND; reset state = off | derived | V-11 |
| REQ-14 | No 12 V battery drain | powered from PV only; IG sense draws < 1 mA only while IG is on | derived | V-12 |
| REQ-15 | IG input robust | ISO 7637-2 pulses 1, 2a, 3a/3b; ISO 16750-2 reverse voltage and suppressed load dump | standard | V-13 |
| REQ-16 | EMC | CISPR 25 class 3 target (radio in the same car) | standard | V-14 |
| REQ-17 | Efficiency (PV in → battery) | ≥ 92 % at 180 W, ≥ 90 % at 300 W | derived | V-3 |
| REQ-18 | HV wiring | orange, screened, ≥ 600 V class, non-separable connections inside IP67 boxes with strain relief | ISO 6469-3 practice | inspection |
| REQ-19 | Vibration/shock | ISO 16750-3, passenger car, sprung mass | standard | V-15 |
| REQ-20 | Enclosure | IP67, conformal coat; creepage designed for PD2 without the coat | derived | V-16 |
| REQ-21 | Operating modes | Mode R (default): charge only with the car READY, tap on the car side of the SMRs. Mode P: only after Q-1 is approved | derived | V-17 |
| REQ-22 | Mode P limits (if approved) | pack NTC ≤ 45 °C; Li ≤ 3.90 V/cell average (218 V); NiMH ≤ 240 V under charge; charge-Ah budget per parked period | derived | V-18 |
| REQ-23 | Reverse-connected string | −33 V indefinitely, no damage | derived | V-19 |
| REQ-24 | Output discharge after stop | < 60 V within 10 s | derived | V-20 |
| REQ-25 | Parts | AEC-Q where available, active lifecycle | task | §8 |

## 3. Assumptions and open questions

| ID | Assumption | Why |
|---|---|---|
| ASM-1 | The flat-enough roof area is about 1.20–1.30 m (fore–aft) × 1.05–1.15 m. A 1016 × 1016 mm cell field fits with ≥ 40 mm margins. [I] | No published dimensions were found. Two reference points: Toyota fitted about 56 cells, 180 W, into the Prius PHV roof [S], and the 3rd-gen roof option carried 36 cells above the rear seats [P] |
| ASM-2 | Pack: NiMH 168 × 1.2 V = 201.6 V, 6.5 Ah (Prius Two); Li-ion 56 cells = 207.2 V, 3.6 Ah (other trims). System bus up to 600 V, but only after the car's own boost converter [P: 2016 product information]. Trim mapping [S] | Sets the 150–262 V output range and the variant |
| ASM-3 | Terminal-voltage range 150–262 V (NiMH 1.0–1.56 V/cell; Li 3.0–4.15 V/cell) [I] | No Toyota limit found |
| ASM-4 | Pack short-circuit current 0.5–2 kA [I] (internal resistance 0.1–0.5 Ω) | Sets the fuse breaking capacity |
| ASM-5 | The converter box sits in the cargo area and the battery-end box under the rear seat next to the pack [S: the pack is under the rear seat] | Ambient and cable length |
| ASM-6 | LV ground (PV−, PGND) is bonded to the chassis at the main box | EMC and simplicity. Conflicts with the C60 "positive ground" note (Q-7) |
| ASM-7 | The car's insulation monitor trips at a few hundred kΩ [P: P0AA6 manual says "several hundred kiloohms" points to a fault]; component standards are 1–100 MΩ at 500 V [P] | REQ-7 |
| ASM-8 | Isc temperature coefficient +0.05 %/K (not in the C60 sheet) [I] | Current limit margin |
| ASM-9 | ISO 16750-2/7637-2 apply only to the IG input, because the board takes no power from the 12 V system | REQ-14/15 |

| ID | Question for a human | BLOCKING? |
|---|---|---|
| Q-1 | **Mode R or Mode P?** Mode R taps the car side of the SMRs and charges only while READY. The car's current sensor and ECU see every amp; harvest is ~0.15 kWh/day. Mode P taps the pack side and charges while parked, ~0.5–1 kWh/day in sun. In Mode P, SOC drifts and no cell or insulation monitoring is awake, so only our pack voltage, Ah budget and one NTC guard against overcharge. That is **not single-fault tolerant** (HZ-4/5). Safer options: Mode R, 12 V-only (A4), or a buffer battery (A5). | **BLOCKING** |
| Q-2 | Which pack does the car have (VIN/model code: ZVW50 NiMH vs ZVW51 Li [S])? This selects the -N or -L resistor variant. | **BLOCKING** |
| Q-3 | Measure the roof (template), and check for the moonroof (Advanced Technology Package on Three/Four [P]). This sets the cell count, 24–40 per string. | **BLOCKING** |
| Q-4 | Get the 2016–2018 ZVW5x repair-manual pages for the battery junction block: where are the current sensor and the SMRs, and where are the tap terminals? Mode R needs our current to pass through the car's current sensor. | **BLOCKING** |
| Q-5 | Who installs and inspects the HV tap (trained HV technician, service-plug procedure, 10-minute wait [P]), and is the modification legal and insurable where the car is registered? | **BLOCKING** |
| Q-6 | How is the array fixed to the roof (bonded flexible laminate vs rails)? Detachment at speed is HZ-9. | **BLOCKING** |
| Q-7 | C60 sheet: "systems ... must be configured as positive ground systems" [P]. Our string is negative-ground at ≤ 33 V. Accept with a 4-week polarization test (V-22), or float the LV domain? | no |
| Q-8 | Hot climate: fit the optional fan? | no |
| Q-9 | Custom magnetics vendor for T301, and Hi-pot/PD test ownership | no |
| Q-10 | Future: read hybrid SOC over CAN (diagnostic PIDs) to gate charging | no |

## 4. Hazards

| ID | Hazard | Mitigation | Implemented by | Single fault? |
|---|---|---|---|---|
| HZ-1 | Electric shock from 150–262 V on our cable or boards | Reinforced LV/HV barrier (T301, U401, U421, 8 mm). Orange screened cable in glands. IP67 metal boxes bonded to chassis. K901/K902 open when idle (both poles). Bleeders < 60 V in 10 s. HV labels | DCX, HVSENSE, BATEND | yes: reinforced = two layers; two poles switched |
| HZ-2 | Short in our HV cable or main board lets the pack dump kA (fire) | D901 blocks reverse current at the battery end; its 10 MΩ sense bypass (R902/R903) passes ≤ 26 µA. F901/F902 (20 kA) are the first elements from each pole. K901/K902 open the circuit when not charging | BATEND | yes: D901 shorted → F901 clears; relay welded → D901 still blocks |
| HZ-3 | Battery overvoltage | L1 firmware termination; L2 analog CV ceiling (LM5176 FB on VINT, no firmware); L3 independent AMC3330 → comparator → latch → PERMIT; L4 car ECU (Mode R) | MPPT_x, HVSENSE, SAFETY | yes: three independent layers (§7.4) |
| HZ-4 | NiMH overcharge/thermal runaway when parked (CV charging of NiMH runs away as it heats) | Mode R by default. Mode P: Ah budget, 240 V limit, pack NTC firmware cut-off + comparator ch4 | SAFETY, MCU | **no in Mode P** (one NTC, pack-level only) → Q-1 |
| HZ-5 | Li cell overvoltage from imbalance while the BMS sleeps | Mode R by default. Mode P limits the pack average to 3.90 V/cell | MCU | **no in Mode P** → Q-1 |
| HZ-6 | Car SOC estimate corrupted → car mismanages the pack | Mode R tap so the car's sensor sees our current (Q-4) | install | yes in Mode R |
| HZ-7 | Insulation fault hidden, or false P0AA6 (car won't start) | ≥ 100 MΩ design; differential-only HV dividers; no Y-caps; T301 shield; megger at install | DCX, BATEND | yes (car monitor plus our design) |
| HZ-8 | Roof array arc, hot-spot or fire | ≤ 33 V class A; bypass diode per 8 cells; one string per input (no backfeed, no string fuse needed); ideal diode at the input; 2.5 mm² wire | ARRAY, MPPT_x | yes |
| HZ-9 | Array detaches at speed | Mechanical design out of scope → Q-6 | — | open |
| HZ-10 | Converter overheats inside the cabin | Firmware derating (RT301). Comparator ch3 OTP on its own NTC (RT302). LM5176 internal TSD. Metal box | DCX, SAFETY | yes |
| HZ-11 | Firmware hang or wild PWM | TPS3850 window watchdog resets the MCU. MCU_RUN has a 1 kΩ pull-down, so PERMIT drops. Analog CC/CV hold their limits. DCX is open loop and bounded | SAFETY | yes |
| HZ-12 | Sensor failure masks overvoltage | Both AMC3330 DIAG pins pull PERMIT low. Two separate dividers, AMC3330s and amplifiers. CV ceiling needs neither | HVSENSE | yes |
| HZ-13 | Battery disconnects under load (fuse, relay) | DCX output ≤ n·VINT/2 ≤ CV ceiling; OVP latch; output caps only 0.6 J | DCX | yes |
| HZ-14 | String reversed | LM74700 + FET block reverse current | MPPT_x | yes |
| HZ-15 | EMI into car radio or ECUs | LM5176 dither; resonant DCX; screened HV cable; T301 Faraday shield; CISPR 25 test | all | n/a |
| HZ-16 | Vehicle transients on the IG wire | BAS21 (250 V), 22.1 kΩ 1206, NPN shifter | MCU | yes |
| HZ-17 | Servicing: our tap stays live after the service plug is pulled | Mode R tap is dead when the SMRs are open; labels; procedure in the install guide | install | procedural |
| HZ-18 | Crash crushes the HV cable | Route along the floor tunnel away from crush zones; D901 and fuses at the battery end | install, BATEND | yes |
| HZ-19 | We energise the car's HV bus while its SMRs are open (Mode R, ignition on but not READY, or after READY-off). The car may flag a welded SMR or fail its discharge check, and a technician meets an unexpectedly live bus | Hardware IG interlock (Q702 + R709 pull PERMIT low when IG is off; relays drop via D503). Firmware starts only when the bus reads ≥ 150 V through R902/R903 before any power flows | MCU, SAFETY, BATEND | yes (hardware + firmware) |

## 5. Architecture trade study

Gates (must-meet): G1 = charges the traction battery (the brief). G2 = no HV on the roof and no non-isolated path from roof to HV. Scores 1–5; weights in brackets.

| Alt | Description | G1 | G2 | Safety and single fault (5) | Energy to pack (3) | Containment without firmware (3) | Simplicity (2) | Parts/AEC/magnetics (2) | Total |
|---|---|---|---|---|---|---|---|---|---|
| A1 | Non-isolated boost, roof string → HV pack | ✓ | ✗ | 1 | 5 | 2 | 5 | 4 | 44 |
| A2 | Isolated interleaved flyback (microinverter style), MCU digital control | ✓ | ✓ | 3 | 4 | 2 | 3 | 2 | 43 |
| **A3** | **2 × analog 4-switch buck-boost MPPT → LLC-DCX (fixed 1:11), battery-end protection** | ✓ | ✓ | 4 | 4 | 5 | 2 | 3 | **57** |
| A4 | 12 V auxiliary-battery MPPT charger only | ✗ | ✓ | 5 | 1 | 4 | 5 | 5 | 60 |
| A5 | Toyota-style: PV → buffer battery → isolated transfer to the pack when READY | ✓ | ✓ | 4 | 5 | 4 | 1 | 2 | 53 |

**Decision: A3.** By default it runs in Mode R; the same hardware can run Mode P.

- **A1 loses** on G2. A 200 V string needs ~350 cells, which will not fit, so a non-isolated boost of 10:1 or more would put the roof, its wiring and any laminate leakage inside the floating HV system. The car reads that leakage as an insulation fault (P0AA6 blocks READY [P]), and an exposed surface could carry pack voltage.
- **A2 loses** on containment. Flyback open-circuit output is unbounded, so CV needs isolated feedback in the loop, and the MCU sits in the inner loop. Peaks reach 25–30 A at 20 V in a custom coupled inductor. Credible (microinverters do it), but it fails harder.
- **A3 wins** because physics bounds the HV output: fixed DCX gain gives Vout ≈ n·VINT/2, and an analog FB divider caps VINT without firmware. MPPT and current limiting are analog loops that firmware only nudges.
- **A5 loses** only on complexity (a second battery, BMS and charger in the cabin). It best solves the parked-energy problem; listed as an upgrade path.
- **A4 fails G1** (the brief) but is the safest and cheapest; offered in Q-1.

## 6. Blocks and domains

| Block | Function | Ports (dir, domain, V range, I max) |
|---|---|---|
| ARRAY | 64 C60 cells, 2 strings × 4 rows × 8 cells, 8 bypass diodes (off-board) | PVA± out LV 0–33 V 8 A; PVB± out LV 0–33 V 8 A |
| MPPT_A / MPPT_B | input protection, PV I/V sense, LM5176 buck-boost, analog PV-voltage regulator | PVx_IN in LV 0–33 V 8 A; VINT out LV 30–49 V 6 A; MPPT_x_PWM in 3.3 V; PERMIT in; PVx_VDIV, PVx_I_ADC out (analog) |
| DCX | VINT bulk, half-bridge LLC-DCX at 95 kHz, T301, bridge rectifier | VINT in LV 30–49 V 10 A; HV_P/HV_N out HV 0–262 V 2 A; DCX_HI/LI in 3.3 V; PERMIT in |
| HVSENSE | two reinforced isolated voltage-sense paths | HV_P/HV_N in HV; HV_V_ADC, HV_V_OVP out LV 0–2.3 V; DIAG → PERMIT |
| SAFETY | 2.5 V reference, 4 comparators, OVP latch, supervisor/WDT, PERMIT, low-side drivers | HV_V_OVP, VINT, NTC_T1, NTC_PACK in; PERMIT, K1/K2_COIL_N, FAN_N, RESET_N out |
| AUX | PV-OR → AUX12 (12.1 V, 0.6 A) → +3V3 (0.25 A) | AUX_IN in LV 15–48 V; AUX12, +3V3 out |
| MCU | dsPIC33CK64MP102, ICSP/UART, IG input + hardware IG interlock, harness | 8 analog in, PWM out, IGN_IN in (vehicle 12 V class) |
| BATEND | F901/F902, D901 with 10 MΩ sense bypass, K901/K902 | HV_P/HV_N in; BAT_TAP_P/N to the pack; AUX12, K1/K2_COIL_N, NTC_PACK, GND via harness |

| Domain | Reference | Range to reference | Range to chassis |
|---|---|---|---|
| LV (includes the roof string, VINT, AUX, logic) | GND, bonded to chassis at H701–H704 | 0–49.4 V (TVS clamp 54 V on PV inputs) | same |
| VEH (IG wire, part of LV) | body ground | 9–16 V, ISO 7637 pulses −150…+112 V | same |
| HV (T301 secondary, HV sense high sides, cable, BATEND) | HV_N | 0–262 V | floating, ±262 V under one insulation fault |

| Barrier | Grade | Working V | Standard / table | PD | OVC | MG | Creepage | Clearance | Design rule |
|---|---|---|---|---|---|---|---|---|---|
| HV ↔ LV (main board, BE board, T301, AMC3330s, relay coil↔contacts) | reinforced | 300 V DC | IEC 60664-1, tables reproduced in TI SLUP419 ([repo](../../docs/topics/rules/isolation-creepage.md)) [P] | 2 (sealed IP67 box; coating not credited) | II (battery DC system, not mains) [I] | IIIa (FR-4, CTI ≥ 175) | F.4 400 V row (conservative for 300 V): 4.0 mm basic → **8.0 mm** reinforced (the 320 V row gives 6.4 mm [S]) | F.1 → 2.5 kV basic, one step up to 4.0 kV for reinforced → F.2: **3.0 mm** | **8.0 mm** on all layers, routed slot ≥ 2 mm under U401/U421/T301 |
| HV ↔ chassis (enclosure, mounting holes) | basic + protective bonding (ISO 6469-3 approach), designed as reinforced | 262 V | same | 2 | II | IIIa | 4.0 / design 8.0 mm | 1.5 / design 8.0 mm | non-plated holes ≥ 8 mm from HV copper |
| HV_P ↔ HV_N | functional | 262 V | IPC-2221B Table 6-1, B2 external uncoated [S] | — | — | — | 1.25 mm (151–300 V row) | same | **2.5 mm** (301–500 V row) |
| PV/VINT ↔ GND | functional | ≤ 54 V | IPC-2221B B2, 31–50/51–100 V | — | — | — | 0.6 mm | same | 0.6 mm |
| Logic | functional | ≤ 12 V | IPC-2221B | — | — | — | 0.1 mm | same | fab minimum |

## 7. Calculations

### 7.1 Array

C60 [P]: 125 × 125 mm (160 mm diameter, pseudo-square), bins G–J give Pmp 3.34–3.42 W, Vmp 0.574–0.582 V, Imp 5.83–5.93 A, Voc 0.682–0.687 V, Isc 6.24–6.28 A. Temperature coefficients: voltage −1.8 mV/K, power −0.32 %/K. Back-contact cells; the sheet asks for a positive-ground system.

**Layout.** Pitch 127 mm (2 mm gap), 8 columns × 8 rows. The cell field is 1016 × 1016 mm; with a 25 mm laminate border the panel is 1066 × 1066 mm. Front rows 1–4 form string A, rear rows 5–8 string B. Grouping by fore–aft position puts cells of similar tilt in the same string, because the XW50 roof's curvature is mostly fore–aft. Each row is an 8-cell substring with its own bypass diode.

```
 FRONT (windshield)                 + = string +, - = string -
 row1  [A][A][A][A][A][A][A][A]  DB1   string A (32 cells): rows 1-4 in series
 row2  [A][A][A][A][A][A][A][A]  DB2   serpentine: row1 L->R, row2 R->L, ...
 row3  [A][A][A][A][A][A][A][A]  DB3
 row4  [A][A][A][A][A][A][A][A]  DB4   -> J101
 row5  [B][B][B][B][B][B][B][B]  DB5   string B (32 cells): rows 5-8 in series
 row6  [B][B][B][B][B][B][B][B]  DB6
 row7  [B][B][B][B][B][B][B][B]  DB7
 row8  [B][B][B][B][B][B][B][B]  DB8   -> J201
 REAR (hatch)       cell field 1016 x 1016 mm, >= 40 mm to mouldings
```

| Per string (32 cells) | −40 °C | 25 °C | 70 °C |
|---|---|---|---|
| Voc = 32·(0.687 − 0.0018·(T−25)) | 25.7 V | 22.0 V | 19.4 V |
| Vmp = 32·(0.574 − 0.0018·(T−25)) | 22.1 V | 18.4 V | 15.8 V |
| Pmp = 32·3.42·(1 − 0.0032·(T−25)) | 132 W | 109 W | 94 W |

- Partial shade, one row bypassed, hot: Vmp = 24·0.493 − 0.45 = 11.4 V. The UVLO turn-off (7.8 V) must stay below this.
- Worst current at 1.2 suns, cold: Imp = 5.93·1.2·1.02 = 7.3 A. Worst power = 109·1.2·1.144 = 150 W per string.
- Electronics limit: a 40-cell string reaches Voc(−40 °C) = 32.2 V ≤ 33 V. That is REQ-4.
- Array totals: 216 W at STC. Typical noon on the roof ≈ 216·(1 − 0.0032·40)·0.95·0.95 = 170 W.
- Energy: about 1.0 kWh/day at best in summer when parked; about 0.15 kWh/day in Mode R, assuming 1 h of driving at 150 W [I].
- For comparison, Toyota claims an average of 2.9 km/day from its 180 W PHV roof [S].
- Bypass: one Vishay V10P45 (10 A, 45 V, TO-277A) per row. With a fully shaded cell, its reverse voltage is ≤ 7·0.6 + 0.45 = 4.7 V; a 24-cell diode group would reach 14 V.

### 7.2 MPPT stage (each channel; LM5176-Q1 equations from its datasheet [P])

**Switching frequency**

- RT = (1/fsw − 190 ns)/116 pF = 41.5 kΩ for 200 kHz. Use 41.2 kΩ, giving fsw = 201 kHz.

**Inductor (22 µH)**

- ΔI = Vin·D/(L·fsw). At Vin 20.8 V and VINT 46 V, ΔI = 2.6 A. At Vin 15.8 V, ΔI = 2.4 A (33 % of 7.3 A).
- Peak current = 7.5 + 1.3 = 8.8 A, against XAL1510-223: Isat 18.7 A, Irms 10.5 A [S]. That is 47 % and 70 %.

**Current-limit sense (RSENSE = 10 mΩ)**

- Boost peak limit 120 mV/10 mΩ = 12 A (10–14 A range); buck valley limit 8 A (6.6–9.4 A).
- Dissipation 0.29 W in a 1 W part (29 %).

**Slope compensation (CSLOPE)**

- Dead-beat value = 2 µS·L/(RSENSE·5) = 880 pF. Use 680 pF (more ramp).
- Datasheet Eq. 9 then gives VCOMP = 2.43 V at 11 V/79 W and 2.25 V at 20.8 V/150 W. Both are below the 3.0 V COMP limit, so regulation is possible.

**UVLO and soft start**

- UVLO: 1.22·(1 + 2 M/274k) + 2 M·2 µA = 14.1 V on; hysteresis 3.15 µA·2 M = 6.3 V, so it turns off at 7.8 V and rides through the 11.4 V shaded-row case.
- The divider is high impedance on purpose: at most 15 µA can back-feed PERMIT through D102.
- Soft start: 0.1 µF·0.8 V/5 µA = 16 ms.

**PV current loop (the CC loop on the input)**

- ISNS limit = (50 mV − 3 µA·1 kΩ)/5 mΩ = 9.4 A typical (8.0 A minimum). The 5 mΩ shunt dissipates 0.27 W at 7.3 A in a 1 W part.
- Q102 sinks I = (V_MPPT_OUT − 0.65)/20 kΩ out of ISNS(+) through R_iso = 1 kΩ, which lowers the sensed voltage. So the PV current setpoint is I_PV = (50 mV − I_sink·1 kΩ)/5 mΩ.
- Zero current needs V_MPPT_OUT = 1.65 V. The op-amp integrates (VSET − PV_VDIV), so the PV voltage is regulated to 12·VSET.
- When the MCU is absent, its PWM pin is pulled high, so VSET is above Voc. The loop then drives the PV current to zero.
- Initial compensation: 100 kΩ/100 nF integrator (100 s⁻¹), zero at 159 Hz. COMP: Rc1 10 kΩ, Cc1 47 nF, Cc2 1 nF. All to be tuned in simulation (V-21).

**VINT ceiling: the CV layer, firmware-free**

- VINT = 0.8·(1 + R_top/10 kΩ). The worst-case range uses VREF 0.788–0.812 V and 0.1 % resistors.
- -N variant (R_top 562 kΩ): VINT = 45.76 V, so Vout = 11·45.76/2 = 251.7 V (247.9–255.5 V).
- -L variant (R_top 499 kΩ): VINT = 40.72 V, so Vout = 224.0 V (220.6–227.3 V).

**Losses at 150 W** (Vin 20.8 V, VINT 46 V; Rds = 4 mΩ × 1.5 when hot)

| FETs (conduction, switching, dead time, Coss) | Shunts | Ideal diode | Inductor | Gate drive | Total |
|---|---|---|---|---|---|
| 1.31 W | 0.54 W | 0.27 W | 1.38 W | 0.13 W | **3.6 W per channel (97.6 %)** |

### 7.3 LLC-DCX and T301 (fixed ratio, open loop)

**Ratio and frequency**

- n = Ns/Np = 66/6 = 11. VINT = 2·(Vbat + 1.2 V)/n = 30.8 V at 168 V and 46.0 V at 252 V.
- fr = 100 kHz with Lr = 0.8 µH (T301 leakage plus trace, spec ±30 %). Cr = 1/((2π·fr)²·Lr) = 3.17 µF, built as two split legs of 16 × 100 nF C0G each.
- fsw = 95 kHz, slightly below fr. That gives ZCS on the rectifiers. Light-load gain stays ≈ 1.002 for Lm/Lr = 50 [I].
- Firmware trims fsw at first start to the primary-current minimum.

**Magnetizing current for ZVS**

- Lm = 40 µH (gapped). Im,pk = VINT·T/(8·Lm) = 1.0–1.5 A.
- ZVS needs ≥ 2·Qoss/t_dead = 70 nC/150 ns = 0.47 A, which is met.

| Operating point | Ipri pk / rms | Q | Cr swing (max V) | B pk | FET loss (2 FETs) | Bridge loss | T301 Cu + core |
|---|---|---|---|---|---|---|---|
| 300 W, 168 V | 30.9 / 21.8 A | 0.80 | ±15.5 V (30.9 V) | 54 mT | 3.05 W | 3.04 W | 1.7 + 0.2 W |
| 300 W, 252 V | 20.6 / 14.6 A | 0.35 | ±10.3 V (33.4 V) | 81 mT | 1.36 W | 2.02 W | ~1.0 + 0.4 W |
| 180 W, 210 V | 14.8 / 10.5 A | 0.31 | ±7.4 V (26.6 V) | 67 mT | 0.71 W | 1.46 W | 0.5 + 0.3 W |

- C0G stress: ≤ 33.4 V on 100 V parts (33 %); 0.68 A rms per capacitor.
- Output: rectifier diodes see ≤ 262 V against 600 V (44 %).
- Output capacitors: 6 × 220 nF 450 V X7T at 58 % bias, ~0.9 µF effective [I]; ripple ≈ 0.7 A/(2π·190 kHz·0.9 µF) ≈ 0.65 V.

**T301 specification (custom)**

- Core: ETD 39, N97, Ae 125 mm².
- Windings: Np 6 turns of litz, about 6 mm² total. Ns 66 turns of triple-insulated wire (each layer rated basic, so TIW = reinforced).
- Shield: a copper-foil Faraday shield between the windings, tied to GND.
- Clearances: ≥ 8 mm margin from primary pins to secondary pins across the former. Insulation class F.
- Tests: hi-pot 4.2 kV DC for 1 min (type) and 3.0 kV DC for 1 s (routine) [I]. Partial-discharge extinction > 1.2·√2·300 V.
- Targets: Lm 40 µH ±10 %, Lr 0.8 µH ±30 %, Cps < 150 pF.

### 7.4 Overvoltage layers (thresholds as battery-terminal voltage)

| Layer | Mechanism | -N (NiMH, 168 cells) | -L (Li, 56 cells) | Independent of |
|---|---|---|---|---|
| L1 | Firmware termination (AMC#1) | 240 V (1.43 V/cell); Mode P adds an Ah budget | 218 V (3.89 V/cell) | — |
| L2 | Analog CV ceiling, LM5176 FB on VINT | 251.7 V (247.9–255.5) | 224.0 V (220.6–227.3) | MCU, both AMC3330s |
| L3 | AMC#2 → U422 (G = 1.15/1.30) → comparator ch1 at 2.000 V → latch → PERMIT | 261.7 V ±0.7 % (259.9–263.5) | 231.5 V (229.9–233.1) | MCU, AMC#1, L2 |
| L3b | VINT comparator ch2 → same latch | VINT 49.4 V (→ 272 V no-load) | 44.0 V (→ 242 V) | AMC#2 |
| L4 | Car battery ECU (Mode R) | car limits | car limits | everything here |

- Ordering holds at the tolerance extremes for both variants: L1 < L2 max < L3 min.
- L3 tolerance budget: AMC3330 gain ±0.2 % [P], divider 0.1 %, difference-amplifier resistors 0.1 % (~±0.2 % gain), LM4040 B grade 0.2 % [P], threshold divider 0.1 %. Total ≈ ±0.7 %.
- Response time: comparator ~1 µs, plus 10 µs filter, latch, PERMIT (< 1 µs), UCC27282 disable [P] and LM5176 EN. Power transfer stops in < 30 µs.
- K901/K902 drop by hardware through D503 within 30 ms [P: release time]. The latch clears only at power-on reset, which happens at the next dawn.

### 7.5 HV sensing

- Divider: 6 × 1.00 MΩ (1206) over 20.0 kΩ, ratio 301. 300 V gives 0.997 V, inside the ±1 V input.
- Each resistor sees 44 V (22 % of 200 V) and 0.3 mW. AMC3330 input resistance ≥ 0.1 GΩ [P] adds < 0.02 % error.
- The two dividers bleed 87 µA, discharging the 1.3 µF output from 262 V to < 60 V in about 8 s (REQ-24).
- ADC path: 0–300 V maps to 0–2.0 V. Production calibration removes the ±1.6 % +3V3/AVDD tolerance; the remaining drift is about ±0.5 % (§10 V-7).

### 7.6 Battery-end protection, fuses, wire

- Fuses: Eaton EVM10-5, 5 A, 500 V DC, 20 kA, total I²t 105 A²s, min breaking 3·In [P].
  - Normal current ≤ 1.8 A is 36 % of rating; ≤ 50 % is our derating rule [I].
  - Voltage 262/500 = 52 %. Breaking 2 kA/20 kA = 10 % (ASM-4).
- Cable: 2.5 mm² screened HV cable (k ≈ 143 for XLPE [I]) withstands (143·2.5)² = 128 kA²s, 1200× the fuse I²t. Drop at 2 A over 2 × 2 m is 0.06 V.
- K901/K902 (G9EJ-1-P-E) [P]:
  - Contacts rated 15 A at 400 V DC resistive. Our 2 A at 262 V is 13 % of current and 66 % of voltage.
  - Interrupts 50 A at 400 V, so our 2 A fault case is covered.
  - Coil 12 V, 100 mA, 1.2 W; after pull-in, firmware PWMs it to about 0.3 W.
  - Coil–contact insulation 2.5 kV AC, impulse 4.5 kV.
  - Ambient max **70 °C**: Mode P must not run when the pack-area temperature is > 60 °C.
- D901 (VS-6ESH06HM3) [P]:
  - Reverse 262/600 V = 44 %. Current 1.8 A avg/6 A = 30 %.
  - Loss ≈ 0.85 V·1.8 A = 1.5 W worst case (1.1 W at the 216 W STC array). θJA ≈ 50 K/W on 4 cm² of 2 oz copper [I].
  - At 70 °C ambient: Tj = 125 °C at STC (71 % of 175 °C), 145 °C at the 300 W corner (83 %, accepted: the array cannot deliver 300 W when hot).
- D901 bypass R902/R903: 2 × 4.99 MΩ 1206. Each sees 131 V (66 % of 200 V) and 3.4 mW. Fault current into a shorted cable ≤ 262 V/10 MΩ = 26 µA.
- PV wiring: 2.5 mm² FLRY-B, 4 m. Drop = 7.3 A·8 m·7.6 mΩ/m = 0.44 V (2.4 %). MSTB 2,5 connectors rated 12 A [S]: 61 %.

### 7.7 Insulation and leakage (REQ-7)

- The only HV↔LV couplings are T301 (Cps < 150 pF), the two AMC3330 barriers (~2 pF each [I]) and the relay coils.
- The HV dividers are differential (HV_P–HV_N), so the car's insulation monitor does not see them.
- There are no Y-capacitors to chassis. Install acceptance: ≥ 100 MΩ at 500 V for the added cable, BE board and main-board HV section (V-6).

### 7.8 Auxiliary supplies (LM5164-Q1 equations from its datasheet [P])

**AUX12**

- fsw = 12·2500/100k = 300 kHz. FB = 1.2·(1 + 90.9k/10k) = 12.1 V. EN on at ~15 V.
- Ripple injection (type 3): RA 150 kΩ, CA 2.2 nF, CB 10 nF. Ramp = 24 mV at 15 V in and 92 mV at 50 V in (≥ 20 mV required).
- L601 100 µH: Isat 3.1 A against 1 A peak (32 %).

**+3V3**

- fsw = 301 kHz, Vout = 3.29 V, EN on at ~9 V.

**Load**

- AUX12 supplies relays (0.6 W economized), gate drivers (~0.5 W), comparator/reference/LEDs (0.2 W) and the +3V3 rail (0.5 W).
- The +3V3 rail feeds AMC3330 low sides (2 × 41 mA max [P]), the MCU and the op-amps.
- Total ≈ 1.9 W out, about 2.2 W from the PV.

### 7.9 Thermal and efficiency

| Loss (W) | 300 W, 168 V | 180 W, 210 V |
|---|---|---|
| MPPT A+B | 7.2 | 4.4 |
| DCX FETs | 3.1 | 0.7 |
| T301 | 1.9 | 0.8 |
| Bridge | 3.0 | 1.5 |
| Aux | 2.2 | 2.2 |
| **Main box total** | **17.4** | **9.6** |
| D901 (battery end) | 1.5 | 0.7 |
| **Efficiency** | **93.7 %** | **94.3 %** |

**Enclosure**

- Die-cast aluminium IP67 box with external fins. Natural convection plus radiation must give θsa ≤ 1.2 K/W (≥ 0.12 m² of surface) [I].
- Box rise: 17.4·1.2 = 21 K.

**Hot spots**

- Q301: Tj = Tcase + 1.5 W·(0.9 [P] + 6 (via array) + 1 (insulating TIM)) K/W = Tcase + 12 K.
- T301: hot spot ≈ Tcase + 2 W·15 K/W [I].

**Derating**

- Full power up to 60 °C ambient: case 81 °C, Q301 93 °C (53 % of 175 °C), T301 ≈ 111 °C (class F, 155 °C).
- Linear derating to 50 % at 85 °C: case 93 °C, T301 ≈ 105 °C.
- Firmware limit at RT301 > 95 °C. Firmware-free OTP when RT302 reaches 105 °C (comparator ch3, ~3 K hysteresis).

**Fan or heatsink?** A heatsink. 17 W of loss, at a power the array cannot reach on a hot day, needs no fan; the finned aluminium box suffices. The fan connector and driver are fitted, the fan is optional (Q-8). A fan would cut θsa to ~0.5 K/W, allowing full power to 80 °C.

### 7.10 Timing and control

- Bus sense before start: the relays close with PERMIT high but the converter idle (DCX PWM off, VSET at maximum, so the PV current setpoint is zero). R902/R903 (10 MΩ) and the two 6.02 MΩ HV dividers (3.01 MΩ together) form a divider of ratio 0.232. A live bus at 200 V reads 46 V on HV_V_ADC, without the converter injecting any power.
- Start: PERMIT goes high (MCU_RUN). The DCX starts PWM at 95 kHz with VINT ≈ 0. Then the LM5176 soft-starts over 16 ms. Current flows only once n·VINT/2 > Vbat + Vf, so there is no inrush. D901 also blocks inrush from the pack into our capacitors, so no precharge circuit is needed.
- MPPT: perturb-and-observe on VSET every 100 ms in 0.1 V steps, plus a global sweep every 10 min to escape partial-shade local maxima.
- PERMIT electrical budget:
  - High: MCU_RUN sources through R518 (2.2 kΩ), and every fault output sinks ≤ 1.5 mA (comparator, AMC3330 DIAG VOL ≤ 0.25 V at 4 mA [P], Q702 with ~97 µA base drive).
  - Low: ≈ 60 µA leaks back in (EN dividers via D102/D202, hysteresis resistors). R519 (1 kΩ) pulls MCU_RUN down even while the MCU is in reset with its pins tri-stated, so PERMIT stays ≤ 0.2 V (worst case: latch through D501 gives ≈ 0.35 V).
  - Every consumer then reads off: UCC27282 disable threshold ≥ 0.7 V [P]; LM5176 EN ≤ 0.5 V against 1.17 V; TPL7407 VIL 0.9 V [P].
- Watchdog: TPS3850 window 9–109 ms [P], kicked every 50 ms. A timeout resets the MCU through R517; MCU_RUN then drops, and PERMIT drops within < 1 ms.
- Mode R start condition (hardware IG interlock through R709, plus firmware): READY_N low, sensed bus ≥ 150 V (that is, the SMRs are closed), and PV ≥ 12 V. Firmware stops within 100 ms if the battery current reads zero while Vout is within 5 V of the ceiling.
- Mode P (if approved): also requires pack NTC < 45 °C, Vbat < L1, Ah since IG-off < budget (default 0.3·capacity), and relay ambient < 60 °C.

## 8. Parts

One row per distinct part. Every placed part, with its value, is in [CONNECTIONS.md](CONNECTIONS.md). That file lists 388 placed items: 377 on the main board (MB) and 11 on the battery-end board (BE), with 88 distinct MPNs. URLs are datasheets read unless tagged.

| Role | Mfr / MPN | Key ratings | Stress (margin) | Package | KiCad symbol / footprint | Datasheet | Life | 2nd source |
|---|---|---|---|---|---|---|---|---|
| MPPT controller ×2 | TI LM5176QPWPRQ1 | 55 V in/out, AEC-Q100 G1 | vs 60 V abs max: VIN ≤ 33 V (55 %), VOSNS 45.8 V normal (76 %), 49.4 V at the OVP trip (82 %, fault only) | HTSSOP-28 | Regulator_Switching:LM5176PWP / Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.5mm_ThermalVias | ti.com/lit/ds/symlink/lm5176-q1.pdf | active [P] | none pin-compatible; ADI LT8390A class (60 V) needs a new layout [unverified] |
| Power FET ×12 | Infineon IAUC100N10S5L040 | 100 V, 4.0 mΩ@10 V, 5.7 mΩ@4.5 V, AEC | ≤ 49 V + ringing ≈ 60 V (60 %); 15.4 A rms (Q301/Q302) | PG-TDSON-8 | Transistor_FET:BSC040N10NS5 (pin-compatible) / Package_TO_SOT_SMD:TDSON-8-1 | infineon.com …iauc100n10s5l040-datasheet-en.pdf | active & preferred [P] | Infineon BSC040N10NS5 (not AEC) |
| Ideal diode ctrl ×2 | TI LM74700QDBVRQ1 | 65 V, −65 V reverse | 33 V (51 %) | SOT-23-6 | Power_Management:LM74700 / SOT-23-6 | ti.com/lit/ds/symlink/lm74700-q1.pdf | active [P] | LM74701-Q1 |
| PV current amp ×2 | TI INA186A2QDBVRQ1 | CM −0.2…40 V (42 V abs; higher allowed if pin current ≤ 5 mA [P]), 50 V/V | CM 25.7 V (64 %) baseline, 33 V (83 %) at 40 cells; 54 V clamp → 1.2 mA via R131/R132 (24 % of 5 mA) | SOT-23-5 | custom / SOT-23-5 | ti.com/lit/ds/symlink/ina186-q1.pdf | active [P] | INA186A2-Q1 SC70 |
| Op-amp ×4 | TI TLV9001QDBVRQ1 | 5.5 V RRIO | 3.3 V (60 %) | SOT-23-5 | Amplifier_Operational:TLV9061xDBV / SOT-23-5 | ti.com/lit/ds/symlink/tlv9001-q1.pdf | active [P] | TLV9061-Q1 |
| HB driver | TI UCC27282QDRCRQ1 | 120 V HB, interlock, EN | HS ≤ 49 V (41 %) | VSON-10 | custom / Package_SON:VSON-10-1EP_3x3mm_P0.5mm_EP1.65x2.4mm | ti.com/lit/ds/symlink/ucc27282-q1.pdf | active [P] | UCC27284-Q1 [unverified] |
| Isolated amp ×2 | TI AMC3330QDWERQ1 | reinforced 6 kVpk, VIOWM 1700 V DC, CLR/CPG ≥ 8 mm, CTI ≥ 600 | 300 V (18 %) | SOIC-16W | Isolator_Analog:AMC3330 / Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm | ti.com/lit/ds/symlink/amc3330-q1.pdf | active [P] | none drop-in (AMC1350-Q1 + iso supply) |
| Comparator | TI LM2901BQDRQ1 | 36 V | 12 V (33 %) | SOIC-14 | Comparator:LM2901 / SOIC-14 | ti.com/lit/ds/symlink/lm2901b-q1.pdf | active [P] | onsemi NCV2901 |
| OVP latch | TI SN74LVC2G74QDCURQ1 | 5.5 V | 3.3 V | VSSOP-8 | 74xGxx:74LVC2G74 / Package_SO:VSSOP-8_2.3x2mm_P0.5mm | ti.com/lit/ds/symlink/sn74lvc2g74-q1.pdf | active [P] | Nexperia 74LVC1G74-Q100 [unverified] |
| Supervisor/WDT | TI TPS3850G33QDRCRQ1 | 3.3 V, window WDT | — | VSON-10 | custom / VSON-10 (EP 1.65x2.4 [I]) | ti.com/lit/ds/symlink/tps3850-q1.pdf | active [P] | TPS3851-Q1 [unverified] |
| Reference | TI LM4040QBIM3X2.5/NOPB | 2.5 V 0.2 %, G1 | 1.4 mA (9 % of 15 mA) | SOT-23 | Reference_Voltage:LM4040DBZ-2.5 / SOT-23 | ti.com/lit/ds/symlink/lm4040-n-q1.pdf | active [P] | Diodes LM4040-Q |
| LS driver | TI TPL7407LAQPWRQ1 | 30 V, 600 mA/ch | 12 V (40 %), 0.12 A (20 %) | TSSOP-16 | Transistor_Array:TPL7407LAPW / TSSOP-16 | ti.com/lit/ds/symlink/tpl7407la-q1.pdf | active [P] | ULN2003A-Q1 |
| Aux buck ×2 | TI LM5164QDDARQ1 | 100 V, 1 A | 48 V (48 %), 0.6 A (60 %) | SO-8 PowerPAD | Regulator_Switching:LM5164DDA / HSOP-8…ThermalVias | ti.com/lit/ds/symlink/lm5164-q1.pdf | active [P] | LM5163-Q1 (0.5 A) |
| MCU | Microchip DSPIC33CK64MP102-E/SS | 3.3 V, 100 MIPS, 12-bit ADC, 250 ps PWM; family AEC-Q100 G1/G0 [P] | — | SSOP-28 | custom / Package_SO:SSOP-28_5.3x10.2mm_P0.65mm | ww1.microchip.com …DS70005363E.pdf | active [unverified] | dsPIC33CK256MP502 (28-pin) |
| Rectifier/OR/blocking ×8 | Vishay VS-6ESH06HM3/86A | 600 V, 6 A, 175 °C, AEC-Q101 | 262 V (44 %), 1.8 A (30 %) | SMPC TO-277A | custom 3-pin / Package_TO_SOT_SMD:TO-277A | vishay.com/docs/94985 | active [S] | Vishay VS-6EWH06FN (DPAK) |
| PV TVS ×2 | Littelfuse TPSMB39A | VR 33.3 V, Vc 53.9 V, 600 W | 25.7 V (77 % of VR) baseline; 32.2 V (97 %) at the 40-cell, −40 °C corner | SMB | Device:D_Zener / Diode_SMD:D_SMB | [unverified] | active [S] | Vishay SMBJ39A |
| Schottky ×9 | Nexperia BAT46WJ | 100 V, 250 mA | ≤ 49 V boot (49 %) | SOD323F | Diode:BAT46 / Diode_SMD:D_SOD-323F | [unverified] | active [S] | onsemi BAT46 |
| IG diode | onsemi SBAS21LT1G | 250 V | −150 V pulse (60 %) | SOT-23 | Diode:BAS21 / SOT-23 | [unverified] | active [S] | Nexperia BAS21 |
| NPN ×4 | onsemi SMMBTA42LT1G | 300 V | 33 V (11 %) | SOT-23 | Transistor_BJT:MMBTA42 / SOT-23 | [unverified] | active [S] | Nexperia MMBTA42 |
| Buck-boost L ×2 | Coilcraft XAL1510-223MEB | 22 µH, Isat 18.7 A, Irms 10.5 A, AEC-Q200 | 8.8 A pk (47 %), 7.3 A rms (70 %) | 15×15 mm | Device:L / Inductor_SMD:L_Coilcraft_XAL1510-223 | coilcraft.com/…/xal1510 | active [S] | Würth WE-XHMA |
| AUX12 L | Coilcraft MSS1210-104KED | 100 µH, Isat 3.1 A, AEC-Q200 85 °C | 1 A (32 %) | 12×12 mm | Device:L / L_Coilcraft_MSS1210-XXX | coilcraft.com/pdfs/mss1210.pdf | active [S] | XGL family |
| 3V3 L | Coilcraft MSS1048-333MLB | 33 µH, Isat 1.66 A | 0.4 A (24 %) | 10×10 mm | Device:L / L_Coilcraft_MSS1048-XXX | coilcraft …MSS1048 | active [S] | — |
| Shunts | Vishay WSK2512R0050FEA / R0100FEA | 1 W, 4-terminal | 0.27 W / 0.29 W (27–29 %) | 2512 | Device:R_Shunt / R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm | vishay.com/docs/30108 | active [S] | Bourns CSS4J |
| DC-link bulk ×4 | Panasonic EEH-ZA1J101P | 63 V 100 µF hybrid, AEC-Q200 | 49 V (78 %) | 10×10.2 | Device:C_Polarized / CP_Elec_10x10 | [unverified] | active [S] | Nichicon GYA |
| MLCC 4.7 µF | TDK CGA6P3X7S2A475K250AB | 100 V X7S | 49 V (49 %, ~−40 % C at bias [I]) | 1210 | Device:C / C_1210_3225Metric | [unverified] | [S] | Murata GCM32 |
| Resonant C0G ×32 | TDK CGA5L1C0G2A104J160AC | 100 V C0G AEC-Q200 | 33.4 V (33 %), 0.68 A rms | 1206 | Device:C / C_1206_3216Metric | [S] | active [S] | Murata GCM31C |
| HV out ×6 | TDK CGA6M4X7T2W224K200AE | 450 V X7T AEC-Q200 | 262 V (58 %) | 1210 | Device:C / C_1210_3225Metric | [S] | active [S] | Murata GCJ/KC |
| Small MLCC (10 values) | Murata GCM188/GCM32 series | AEC-Q200 | ≤ 50 % V | 0603/1210 | Device:C | MPNs in CONNECTIONS [S] | active [S] | TDK CGA |
| Resistors | Panasonic ERJ-3EKF/ERJ-3RQF/ERJ-8ENF/ERA-3AEB | 1 %/0.1 %, AEC-Q200 | ≤ 50 % P (max 35 % in gate resistors R301/R302; LED resistors 21 %); R704 1206 for ISO 7637 pulse energy | 0603/1206 | Device:R | [S] | active [S] | Vishay CRCW-HP |
| NTC ×2 | TDK NTCG163JF103FTDS | 10 kΩ, B 3435 K | <1 mW | 0603 | Device:Thermistor_NTC / R_0603 | [unverified] | [S] | Murata NCU18 (B 3380: re-compute) |
| Transformer | custom (ETD 39 N97) | §7.3 | §7.3 | ETD39 20-pin | custom / custom | — | build-to-spec | 2 vendors (Q-9) |
| Fuse ×2 (BE) | Eaton Bussmann EVM10-5-2P | 5 A 500 V DC 20 kA, ISO 8820-8 design | 1.8 A (36 %), 262 V (52 %) | 10×38 PCB | custom / custom (ELX1304) | farnell.com/datasheets/4810345.pdf | active (2026 DS) [P] | Mersen/Littelfuse EV 10×38 [unverified] |
| Disconnect ×2 (BE) | Omron G9EJ-1-P-E-UVD DC12 | 15 A 400 V DC, polarized contacts | 2 A (13 %), 262 V (66 %) | PCB relay | custom / custom | omronfs.omron.com/en_US/ecb/products/pdf/en-g9ej-1-e.pdf | in production [S] | Panasonic AEV110122 is NRND [S]; TE/Gigavac (larger) |
| Conn. PV/IG/harness | Phoenix MSTBA 2,5/x-G-5,08 | 12 A, 320 V [S] | 8 A (67 %) | THT | Connector_Generic / Connector_Phoenix_MSTB:… | [unverified] | active [S] | Würth 691 series |
| Conn. HV ×3 | Phoenix GMSTBA 2,5/2-G-7,62 | 12 A, ≥ 630 V [S] | 2 A, 262 V | THT | Connector_Phoenix_GMSTB:PhoenixContact_GMSTBA_2,5_2-G-7,62… | [unverified] | active [S] | Würth 691 HV |
| Fan conn. | Molex 43650-0215 | 5 A | 0.3 A | THT | Connector_Molex:Molex_Micro-Fit_3.0_43650-0215… | [S] | active [S] | — |
| LEDs ×2 | AEC-Q101 0603 green/red | — | 2 mA | 0603 | Device:LED / LED_0603_1608Metric | [unverified] | — | any |
| Bypass (array) ×8 | Vishay V10P45-M3/86A | 10 A 45 V | 7.3 A (73 %) | TO-277A | off-board | [unverified] | [S] | — |

Note 1: the PV TVS clamps at 54 V, above the INA186 42 V absolute input rating. R131/R132 (10 kΩ) limit the pin current to 1.2 mA, within the datasheet's 5 mA allowance [P]. The 3 nA maximum bias current through 10 kΩ adds 30 µV, a 6 mA error. All other parts on PVx_IN/Vx_IN are rated ≥ 60 V.

## 9. Placement and mechanical constraints

**Main board (MB).**

- Enclosure: 4-layer, 2 oz outer copper, 200 × 120 mm, in a die-cast finned IP67 box (internal ≥ 210 × 130 × 55 mm).
- West edge: J101, J201, J702, J703, J704 (LV field wiring, M20 glands). East edge: J301 (HV, EMC gland with 360° screen clamp to the box).
- The board splits north–south into LV (x < 125 mm) and HV (x > 133 mm). The LV/HV barrier is a ≥ 8 mm void on all layers with a 2 mm routed slot under T301, U401 and U421.
- Mounting: H701–H704 (plated, bonded to the box) in LV; H705–H706 (non-plated) in HV, ≥ 8 mm from copper.
- Heat path: Q101, Q103–Q106, Q201, Q203–Q206, Q301, Q302 and the LM5176 pads sit over via arrays to a bottom copper pad. That pad is pressed onto a 0.25 mm insulating TIM on a box boss.
- Height: T301 is 40 mm max. Components above 15 mm are allowed only in LV-centre and over the T301 zone.

**Battery-end board (BE).** 100 × 80 mm, 2-layer 2 oz, in a small IP67 box. J901 and J903 are on the west edge; J902 and J904 on the east edge. LV (J903/J904, coil pins) is separated from HV by 8 mm.

```text
# ---- groups ----
group(MPPT_A) group(MPPT_B) group(DCX) group(HVSENSE) group(SAFETY) group(AUX) group(MCU) group(BATEND)
# ---- domains / barriers ----
separate(HV, LV, creepage_mm=8.0, clearance_mm=8.0, slot: yes)          # MB and BE
separate(HV_P, HV_N, creepage_mm=2.5, clearance_mm=2.5, slot: no)
straddle(T301, LV, HV) straddle(U401, LV, HV) straddle(U421, LV, HV)   # NEW: part body spans the barrier
keepout(region under T301/U401/U421 between pin rows, copper+vias, all layers)
keepout(H705, H706, copper, all layers, radius_mm=8)
# ---- edges ----
edge(J101, west) edge(J201, west) edge(J702, west) edge(J703, west) edge(J704, west) edge(J301, east)
edge(J901, west) edge(J903, west) edge(J902, east) edge(J904, east)
# ---- hot loops (minimise area; place on top layer, no vias in loop) ----
hot_loop([C106.1, Q103.5, Q103.1, Q104.5, Q104.1, R116.1, R116.4, C106.2], "ch A buck-side input loop")
hot_loop([C120.1, Q105.5, Q105.1, Q106.5, Q106.1, R116.1, R116.4, C120.2], "ch A boost-side output loop")
hot_loop([C206.1, Q203.5, Q203.1, Q204.5, Q204.1, R216.1, R216.4, C206.2], "ch B buck-side")
hot_loop([C220.1, Q205.5, Q205.1, Q206.5, Q206.1, R216.1, R216.4, C220.2], "ch B boost-side")
hot_loop([C303.1, Q301.5, Q301.1, Q302.5, Q302.1, C303.2], "half-bridge commutation loop")
hot_loop([Q301.1, T301.1, T301.3, C317.2, C333.1, C333.2, Q302.1], "resonant loop (22 A rms)")
hot_loop([T301.11, D301.1, D301.3, C350.1, C350.2, D304.1, D304.3, T301.20], "secondary rectifier loop (and mirror via D302/D303)")
# ---- tight placements ----
near(U103, Q103, close) near(U103, Q106, close) near(U103.29, NT101, tight)
near(R117, U103.16, tight) near(R118, U103.15, tight) near(C115, U103.16, tight)
near(C116, U103.20, tight) near(C119, U103.26, tight) near(D103, U103.23, close) near(D104, U103.23, close)
near(C117, U103.23, tight) near(C109, U103.2, tight) near(C111, U103.7, tight) near(R112, U103.6, tight)
near(R119, Q105.4, tight) near(R120, Q106.4, tight) near(R122, Q104.4, tight) near(R123, Q103.4, tight)
near(U102, R101, tight) near(R103, R101.2, close) near(R104, R101.3, close)
near(U101, Q101, tight) near(C101, U101.1, tight) near(D101, J101, close)
near(U104, Q102, close) near(R126, U104.4, tight) near(C124, R125, tight) near(R131, U102.5, tight) near(R132, U102.4, tight)
# channel B: same relations with refdes +100
near(U301, Q302, tight) near(C314, U301.3, tight) near(C311, U301.1, tight) near(R301, Q301.4, tight) near(R302, Q302.4, tight)
near(C317..C332, Q301.5, close) near(C333..C348, Q302.1, close)
near(D301..D304, T301.11, close) near(C350..C355, D301.3, close)
near(R407, U401.6, tight) near(C401, U401.6, tight) near(C402, U401.1, tight) near(C403, U401.1, tight) near(C405, U401.5, tight)
near(C406, U401.5, tight) near(C407, U401.16, tight) near(C408, U401.12, tight) near(U402, U401.11, close)
near(R427, U421.6, tight)   # and every other U401/U402 rule repeated for U421/U422 (refdes +20)
near(RT301, Q301, tight) near(RT302, T301, close) near(Q702, Q701, close) near(R709, Q702, tight) near(R902, D901, close) near(R903, D901, close)
near(U502, U503, close) near(U504, U701, close) near(C703, U701.7, tight) near(C704, U701.20, tight) near(C702, U701.5, tight)
near(U601, L601, tight) near(C602, U601.2, tight) near(C603, U601.7, tight) near(U602, L602, tight) near(C609, U602.2, tight)
# ---- kelvin / sense routing (NEW verb) ----
kelvin(R101.2 -> R131, R103) kelvin(R101.3 -> R132, R104)   # pads 2/3 are the sense pads; R131/R132 route as a pair
kelvin(R116.2 -> R117) kelvin(R116.3 -> R118)
kelvin(R407.2 = U401.7 = U401.8, single point)                 # HGND at divider bottom
diff_pair(HVS1_OUTP, HVS1_OUTN, matched) diff_pair(HVS2_OUTP, HVS2_OUTN, matched)
# ---- thermal ----
thermal(Q101,Q201, 0.3, copper) thermal(Q103..Q106, 0.4 each, heatsink) thermal(Q203..Q206, 0.4 each, heatsink)
thermal(Q301, 1.5, heatsink) thermal(Q302, 1.5, heatsink) thermal(T301, 2.0, airflow)
thermal(L101, 1.4, copper+airflow) thermal(L201, 1.4, copper+airflow)
thermal(D301..D304, 0.8 each, copper 4 cm2 each, HV side)   # no heatsink across the barrier
thermal(R116, R216, R101, R201, 0.3 each, copper) thermal(U601, 0.4, copper) thermal(D901, 1.5, copper 4 cm2)
# ---- arrays / symmetry ----
array([C317..C332], x, pitch: equal) array([C333..C348], x, pitch: equal)
symmetric(MPPT_A, MPPT_B, axis: y)        # channels mirror each other
array([C350..C355], y, pitch: equal) array([R401..R406], x, pitch: equal) array([R421..R426], x, pitch: equal)
# ---- separation for noise/heat ----
far(MPPT_A.SW1/SW2, U701, loose) far(HB_SW, HVSENSE.analog, close) far(L101, L201, close)
far(DCX_MID, U402/U422, close) far(T301, RT301, loose)
# ---- sides ----
side(all, top)   # single-sided assembly; bottom copper is the heat-spreader pad
# ---- mechanical (NEW) ----
height(T301, 40) height(C301, C302, C108, C208, 11) cable_entry(J301, gland: EMC, edge: east)
variant(R114, R214: 562k|499k; R429, R431: 11.5k|13.0k; R504: 237k|210k)   # NiMH|Li
variant(R709: fit|DNP)                                                       # Mode R|Mode P
```

Vocabulary I needed beyond the given list:

- `straddle` (a part body crossing a barrier, so the barrier keepout must leave room for it).
- `kelvin` (sense connection that starts at a named pad; a 4-terminal footprint makes this explicit).
- `diff_pair` for low-speed analog pairs.
- `height`, `cable_entry` and `variant`.
- Ranges such as `C317..C332`.


## 10. Verification plan

| ID | Test | Pass criterion | Covers |
|---|---|---|---|
| V-1 | Cardboard/foam template of the panel on the actual car; moonroof check | ≥ 40 mm margins, no overhang, antenna clear | REQ-1, Q-3 |
| V-2 | String Voc at −20 °C (climate chamber, cell sample) and extrapolate | ≤ 33 V at −40 °C | REQ-4 |
| V-3 | PV simulator (2 channels, mismatched curves, shaded-row profile), EN 50530-style dynamic MPPT | ≥ 98 % static, ≥ 95 % dynamic; efficiency ≥ 92 %/90 % | REQ-3/17 |
| V-4 | Bench HV battery emulator (bidirectional supply + 0.3 Ω) 150–262 V | regulated output, no oscillation | REQ-5 |
| V-5 | Hi-pot LV↔HV: 4.2 kV DC 60 s (type), 3.0 kV DC 1 s (routine); PD test on T301 | no breakdown, PD < 10 pC at 1.2× working | REQ-6 |
| V-6 | 500 V megger, HV↔chassis, each subassembly and installed | ≥ 100 MΩ | REQ-7, HZ-7 |
| V-7 | Fault injection: (a) firmware ignores termination; (b) FB top resistor of one LM5176 open; (c) AMC#1 high side unpowered; (d) AMC#2 unpowered; (e) U422 output stuck low; (f) battery emulator disconnected at full power | (a) L2 holds; (b) comp ch2/L3 latch; (c)(d) DIAG → PERMIT low; (e) L2 holds and FW plausibility stops; (f) Vout ≤ ceiling or latch | HZ-3/12/13 |
| V-8 | Short the HV cable at J901 with K901 closed and the converter off, fed from a 260 V 2 kA-capable source (lab) / then with D901 shorted | no current (D901); with D901 shorted F901 clears; cable intact | HZ-2 |
| V-9 | Thermal run at 300 W, 60 °C and 85 °C ambient, thermocouples on Q301, T301, D301, U103; fan unplugged | ≤ 80 % Tj,max; OTP trips at 105 °C ±5 K, recovers | HZ-10 |
| V-10 | Cold start −40 °C, hot soak 85 °C, 500 thermal cycles | functional | REQ-12 |
| V-11 | Watchdog: halt the MCU in the debugger while running; drive PWM pins stuck high/low | PERMIT low < 1 ms; no shoot-through (interlock) | HZ-11 |
| V-12 | Night drain on IG input with IG off | < 10 µA | REQ-14 |
| V-13 | ISO 7637-2 pulses 1, 2a, 3a/b and ISO 16750-2 reverse and load dump on J702 | no damage, READY_N correct after | REQ-15 |
| V-14 | CISPR 25 conducted and radiated, full load | class 3 | HZ-15 |
| V-15 | ISO 16750-3 random vibration on both boxes, relays energised and de-energised | no chatter, no damage | REQ-19 |
| V-16 | IP67 immersion, then V-5/V-6 | pass | REQ-20 |
| V-17 | In car, Mode R: car scan tool shows battery current includes our ~1 A; no DTCs after 2 weeks; READY off → output current stops, Vout bleeds | no P0AA6, SOC behaves | REQ-21, Q-4 |
| V-18 | Mode P only if approved: Ah-budget stop, NTC stop (heat probe), 218 V/240 V stop on emulator | stops at each limit | REQ-22 |
| V-19 | Reverse string at J101 for 1 h; TVS surge 8/20 µs on PVx_IN | no damage; check INA186 node (note 1) | HZ-14 |
| V-20 | Stop at 262 V, measure Vout decay | < 60 V in 10 s | REQ-24 |
| V-21 | Simulation: LM5176 PSpice model, CC loop on SS, MPPT PI, DCX stiff load (0.1–1 Ω battery); then bench Bode | phase margin ≥ 45° all corners | §7.2 |
| V-22 | Polarization: 4 weeks string at +33 V to a grounded aluminium plate vs. control | < 1 % Pmp loss | Q-7 |
| V-23 | Insulation/creepage review of the PCB in KiCad (8 mm rule, slots) and of T301 build | conforms | REQ-6 |

## 11. Sources

- SunPower C60 bin sheet (bins G–J, coefficients, positive-ground note) [P]: http://eshop.terms.eu/_data/s_3386/files/1379942540-sunpower_c60_bin_ghi.pdf
- Toyota 2016 Prius preliminary product information (battery types, voltages, capacities, moonroof) [P, PriusChat copy]: https://attachments.priuschat.com/attachment-files/2015/11/97312_2016_Prius_Liftback_Product_Information_1.pdf
- Trim/battery mapping [S]: https://www.autoguide.com/auto-news/2014/07/2016-toyota-prius-may-go-wheel-drive.html ; ZVW50/51 codes [S]: https://greenbeanbattery.com/blog-how-to-tell-if-your-prius-has-a-lithium-ion-or-nimh-hybrid-battery/
- Toyota ERG 2010–2015 Prius T-ERG-008-D (SMRs on both poles, pack fuse, ground-fault monitor, 10 min, roof solar 36 cells/22–27 V) [P]: https://techinfo.toyota.com/t3Portal/document/erg/T-ERG-008-D/pdf/T-ERG-008-D.pdf ; 2016–2022 quick guide T-ERG-028-D [P, figures only]
- Toyota repair manual P0AA6 (2010 Prius), insulation standards [P]: https://attachments.priuschat.com/attachment-files/2023/04/235371_P0AA6-526P0AA6-611P0AA6-612P0AA6-613P0AA6-614_Hybrid_Battery_Voltage_System_Isolation_Fault.pdf
- Prius PHV solar roof (180 W Panasonic HIT; solar battery + ECU + DC-DC; parked → drive battery, driving → 12 V; not offered in the US) [S]: https://monoist.itmedia.co.jp/mn/articles/1606/16/news033.html , https://response.jp/article/2017/03/01/291419.html , https://www.repairerdrivennews.com/2017/03/28/panasonic-photovoltaic-roof/ ; 56 cells [S]: https://response.jp/article/2016/08/27/280722.html
- Prius gen-4 battery under rear seat [S]: https://priuschat.com/wiki/zvw50-zvw51-2016-2022-gen-4/
- Isolation method and tables (IEC 60664-1 via TI SLUP419; IPC-2221B) [P via repo]: [docs/topics/rules/isolation-creepage.md](../../docs/topics/rules/isolation-creepage.md)
- Datasheets read [P]: TI LM5176-Q1 (SNVSB46B), LM74700-Q1 (SNOSD17G), INA186-Q1 (SBOS386B), TLV900x-Q1 (SBOS980G), UCC27282-Q1 (SLUSDN5D), AMC3330-Q1 (SBASA35B), LM2901B-Q1 (SLCS142H), SN74LVC2G74-Q1 (SCES563C), TPS3850-Q1 (SBVS264B), LM4040-N-Q1 (SNOS633N), TPL7407LA-Q1 (SLRS074), LM5164-Q1 (SNVSB51C) at https://www.ti.com/lit/ds/symlink/<part>.pdf ; Microchip DS70005363E; Infineon IAUC100N10S5L040 rev 1.0; Vishay VS-6ESH06HM3 (doc 94985); Omron G9EJ-1-E (2016) and G9EJ (2014); Eaton ELX1304 EVM10 (Jan 2026).
- Secondary [S]: Coilcraft, Panasonic (AEV110122 NRND), TDK and Murata product listings.
