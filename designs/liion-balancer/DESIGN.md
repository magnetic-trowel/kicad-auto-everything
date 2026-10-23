# liion-balancer: active cell balancer for a 13–16S home Li-ion pack (≈ 10 kWh)

Status: engineering design, ready to encode in `kaesynth`. Not reviewed or certified. The netlist
is in [CONNECTIONS.md](CONNECTIONS.md).

Evidence tags: [P] read in the primary source, [S] secondary source or snippet, [V] vendor claim,
[I] our inference. IEC 60664-1, IEC 62368-1, IPC-2221B, UL 1973/9540 and IEC 62619 were not
readable here. Their values are tagged [S] and must be verified before fabrication.

## Summary

- **Topology.** Each cell has its own isolated flyback (ADI LT8584, 1:4 transformer). It takes
  ≈ 2.5 A out of a high cell and returns the energy to the whole stack. This is unidirectional
  top-balancing with no bleed resistors.
- **Fault containment.** This is the brief's "no pathways for voltage to jump."
  - Every power part of channel k sits between taps k−1 and k.
  - The stack return passes through two diodes in series (D1kk, then D1).
  - So no single shorted part connects non-adjacent taps.
  - A part that shorts one cell is cleared by that tap's board fuse in ≈ 5 ms.
- **Control.**
  - An ADI ADBMS1818 measures all cells directly (≤ ±4 mV). Its S pins enable the balancers.
  - An STM32G031 runs the algorithm. The ADBMS1818's 2 s watchdog stops balancing if the MCU stalls.
  - Each channel also has a second, independent enable: an opto string drives DCHRG.
- **Wiring.** 17 wires (N+1), 18 AWG, ≤ 1 m.
  - Battery end: an M6 ring and a 7 A ceramic fuse (10 kA at 125 VDC).
  - Board end: a 17-pole pluggable terminal block, then a replaceable 5 A fuse per tap.
  - 13–15S packs use insertion bridges in the plug.
- **Coexistence.** The board never switches the pack and is not a protection device. It draws
  ≤ 25 µA per cell (worst case) and ≤ 50 µA from the stack in sleep. It reports data over an
  isolated UART and a fault contact.
- **Part count.** 374 placed parts (368 electrical + 6 mounting holes):
  - 16 channels × 15 parts;
  - 17 tap entries × 3 parts;
  - ≈ 75 control parts;
  - plus the off-board harness.

## 1. Brief

The user's brief, verbatim:

"I want a battery balancer that can balance a string, series string of 12 volt lead acid batteries. I want another one that can balance a series string of lithium ion batteries. This would be in the 10 kilowatt hour range, so home packs. It should make sure that there's no pathways for voltage to jump from places. I don't know if you want to do a flying capacitor or inductor or some other elegant approach, but it needs to keep the charge balanced without bleed resistors. Ideally, it would be as efficient as possible, as robust as possible, and allow us to have little wires that go to the system ground and then all of the individual positive terminals."

**This document designs the lithium-ion balancer.** Another engineer designs the lead-acid one.

## 2. Requirements

| ID | Requirement | Value + units | Source | Verified by |
|---|---|---|---|---|
| REQ-1 | Pack | one series string, 13–16 positions (a position may be a parallel group), ≈ 10 kWh | brief; ASM-1 | T-FUNC at 13S, 16S |
| REQ-2 | Chemistry | LFP 2.50–3.65 V/cell, NMC/NCA 3.00–4.20 V/cell; stack ≤ 60.0 V | IEC 62368-1 ES1 ≤ 60 V DC [S]; C-3 | config check |
| REQ-3 | No bleed resistors | energy returned to the stack. Efficiency ≥ 72 % including a 1 m harness, ≥ 78 % board only (3.3 V cell, 51 V stack) | brief | T-EFF |
| REQ-4 | Balancing current | ≥ 2.0 A average per discharged cell (typical 2.5 A) | C-2 | T-EFF |
| REQ-5 | Concurrency | ≤ 8 channels at once; NTC derating | C-12 | T-THERM |
| REQ-6 | Measurement | ≤ ±4 mV at 3.3 V over temperature, with balancing muted | ADBMS1818 [P]; C-4 | T-MEAS |
| REQ-7 | Wiring | N+1 wires: the B− cell terminal (the user's "system ground") plus every cell positive | brief | inspection |
| REQ-8 | Tap fusing | battery end: 7 A, ≥ 125 VDC, ≥ 10 kA DC. Board: 5 A very fast, 300 A at ≤ 32 VDC, replaceable | brief; C-7 | F-1…F-6 |
| REQ-9 | No voltage jumps | No single part fault creates a path between non-adjacent taps able to carry > 0.5 A. A one-cell short clears in ≤ 10 ms. Exception: T1kk interwinding insulation (1500 V rms vs ≤ 60 V working, 25×) is treated as a safeguard; its residual risk is cleared by the battery-end fuses | brief | FMEA §4; F-1…F-4 |
| REQ-10 | Bounded fault energy | every fault path has a fuse rated for its voltage and prospective current | derived | C-7 |
| REQ-11 | Spacing | §6.3 (functional per IPC-2221B; user port reinforced) | standards [S] | DRC, T-HIPOT |
| REQ-12 | Per-cell standing current | ≤ 25 µA worst case, typically ≤ 3 µA; mismatch drift ≤ 0.15 %/yr of 200 Ah | brief ("equal"); C-9 | T-IQ |
| REQ-13 | Stack standing current | ≤ 50 µA in sleep, ≤ 5 mA while monitoring | C-9 | T-IQ |
| REQ-14 | Mis-wiring | Swapped, reversed, offset or out-of-order taps cause no fire and no cell damage. Fuses open and the self-test locks out | brief ("robust") | F-6, F-7 |
| REQ-15 | Open tap | detected before each session, and within 1 s while balancing | C-11 | F-5 |
| REQ-16 | Stuck-on channel | two independent enables per channel plus a ≤ 2.2 s hardware watchdog | H-4 | F-8 |
| REQ-17 | No overcharge | a cell at ≥ V_full − 20 mV is never net-charged by balancing | H-5 | F-9 |
| REQ-18 | Coexist with BMS | does not switch the pack or replace protection; measures every cell; exposes data and a fault contact | task; Q-2 | review |
| REQ-19 | Telemetry | isolated UART, 115 200 8N1, host logic 2.25–5.5 V; firmware update over it | Q-7 | T-FUNC |
| REQ-20 | Environment | indoor (garage or utility room); 0–45 °C operating, −20…60 °C storage; non-condensing; ≤ 2000 m; pollution degree 2 | task | T-THERM |
| REQ-21 | Temperatures | LT8584 T_J ≤ 105 °C; all parts ≥ 20 °C below rating at 45 °C ambient with 8 channels on | derived | T-THERM |
| REQ-22 | Harness connector | pluggable, polarized, ≥ 12 A and ≥ 300 V per pole | derived | inspection |
| REQ-23 | Standards | follow UL 1973 / UL 9540 / IEC 62619 BMS practice; no certification claim | task | review |

## 3. Assumptions and open questions

**Assumptions**

- **ASM-1 Pack.** Reference pack: 16S LFP, 3.2 V, 200 Ah = 51.2 V, 10.24 kWh. This is the common home format [S]. 15S LFP (48 V rack modules) and 13–14S NMC also exist, so the series count is configurable (13–16S), not fixed.
- **ASM-2 Existing BMS.** The pack keeps its own BMS for protection.
- **ASM-3 Terminals.** M6 studs or busbar holes; harness ≤ 1.0 m.
- **ASM-4 Parallel groups.** A parallel group counts as one cell. Balancing time scales with its capacity.
- **ASM-5 Inverter.** It may be transformerless, so the battery may sit at mains potential. The user port is therefore reinforced for 250 V rms.
- **ASM-6 Enclosure.** UL 94 V-0 plastic, pollution degree 2, natural convection.
- **ASM-7 Drift.** ≤ 0.25 %/day worst case, ≈ 0.04 %/day typical (self-discharge spread plus coulombic-efficiency spread) [I].
- **ASM-8 Transients.** Pack-bus transients are absorbed by the mΩ cells, so the taps see the cell voltage plus ≤ tens of mV [I].
- **ASM-9 Firmware.** Implements C-4 and C-11. Not in this step.

**Open questions**

- **Q-1 (BLOCKING) Pack range.** Confirm 13–16S at ≤ 60 V.
  - The hardware is rated to 67.2 V (16S NMC). Going above 60 V leaves ES1/SELV and changes the insulation analysis.
  - Below 13S the stack falls under the 30 V transformer range; NA6252-AL (10–35 V) would be needed [P].
- **Q-2 (BLOCKING) BMS interaction.**
  - Should the pack BMS's bleed balancing be disabled? Both act on high cells, but the brief rejects bleed.
  - Is a BMS or inverter data link (CAN or RS-485) required?
- **Q-3 (BLOCKING) Inverter isolation.** Is the battery isolated from mains by the inverter? If so, the user barrier can drop from reinforced to functional. The current design is safe either way.
- **Q-4 (BLOCKING) Harness.** Accept 18 AWG, ≤ 1 m, M6/¼" rings, and an axial fuse sealed in heat-shrink? The alternative is a replaceable 6.3 × 32 mm in-line holder. Who builds the harness?
- **Q-5 Balancing window.** LFP top-balance only (default), or also near empty?
- **Q-6 Fault contact.** Close on fault (default: zero standing current), or open on fault (fail-safe, but draws 5 mA continuously)?
- **Q-7 Telemetry.** Is UART enough?
- **Q-8 Enclosure and mounting.** Who provides them? Conformal coating?
- **Q-9 Listing.** Wiring an add-on to a listed UL 1973/9540 battery may void the listing [I]. Is that acceptable to the owner and the AHJ?
- **Q-10 Bidirectional option.** Is a bidirectional version (LTC3300-1, §5) wanted, which can recharge a low cell directly but has weaker fault containment?
- **Q-11 Supply.** The ADBMS1818 is Active but has a 52-week lead time [P]. Should the pin-identical LTC6813-1 be qualified as a second source?

## 4. Hazards

The last column says whether the mitigation still holds after one further independent fault ("1F").

| ID | Hazard | Cause | Mitigation (where) | 1F? |
|---|---|---|---|---|
| H-1 | Fire or burns at the board | A part shorts one cell: LT8584 switch, a cracked 1210 MLCC, or the TVS. ≈ 34 A, limited by the harness | Board fuse F1tt clears in ≈ 5 ms. The 7 A battery-end fuse is the backup (C-7). 1210 MLCCs kept ≥ 5 mm from edges and holes. LT8584 MODE (pin 5, between GND pins 4 and 6) is tied to V_IN through R4kk = 10 kΩ, so a solder bridge there draws 0.4 mA instead of shorting the cell; 100 % AOI | yes |
| H-2 | Multi-cell short ("voltage jump"), kA | A part spanning non-adjacent taps fails short | **By construction.** Only stack-spanning parts cross taps, and each is blocked or limited. Flyback return: D1kk in series with D1, so D1kk short → D1 blocks; D1 short → every D1kk blocks; C6kk or D2 short → D1 blocks. Supplies go through F1 (125 mA) + 100 Ω. The LED string has R24 and a current sink. The sense divider is 2 MΩ. An ADBMS1818 internal pin-to-pin short passes ≤ 0.3 A through two 100 Ω filter resistors, which act as fusible links. **Residual:** a breakdown of T1kk's interwinding insulation (rated 1500 V rms [P], 25× the working voltage) joins TAPk to TAP0. It is treated as a safeguard, not a part fault. If it does occur (up to ≈ 490 A), the 10 kA battery-end fuses clear it in < 1 ms | yes. A double fault (D1 + D1kk) is cleared by F116/F100 and the battery-end fuses |
| H-3 | Harness short near the battery: ≤ 2.5 kA, arc | Insulation damage | 3AB fuse at the ring (10 kA at 125 VDC [P]). UL 1015 wire; bundle in tap order; strain relief | yes |
| H-4 | **Over-discharge by a stuck balancer.** The BMS cannot disconnect this load. Copper dissolution leads to an internal short and runaway on recharge | S pin stuck; DIN bridged to the adjacent pin 6 (GND); firmware | Two independent enables: S_k→DIN and BAL_EN→opto→DCHRG. The ADBMS1818 watchdog clears DCC in 2 s. Firmware floor 3.0 V (LFP) / 3.4 V (NMC). LT8584 UVLO 2.1–2.45 V [P] as last resort. Both paths proof-tested before each session. FAULT contact | yes. An LT8584 internal logic fault is residual |
| H-5 | Overcharge of a full cell by the returned energy | Discharging others returns 0.12–0.2 A per active channel to every cell | Firmware: every cell ≥ V_full − 20 mV must be in the active set, so its net current is −2.5 + n·0.15 A < 0 for n ≤ 8. If more than 8 cells qualify, do not balance | partial (firmware, reviewed and tested) |
| H-6 | Bad decisions from IR drop on single-wire taps | Balancing current | MUTE (or DCP = 0) during conversions [P]; plausibility check (sum of cells vs the SC measurement) | yes |
| H-7 | Hot-plug overvoltage | Random mating order | TVS D3kk per channel. 100 Ω/10 nF C-pin filters plus the ADBMS1818's internal 8 V clamps [P]. 2 × 100 µF per channel damps overshoot (C-10) | yes |
| H-8 | Swapped, reversed or offset taps | Installer error | Pre-plug DMM check (§9). TVS crowbars open the fuses. OMNI-BLOK fuses are replaceable. Self-test lockout | yes (no fire); board may need repair |
| H-9 | Open tap (including TAP0 or TAP16) | Broken crimp | Pulse test (C-11); 10 ms FLYBUS check; D2 clamp. The BAL_EN string is fed from TAP16 to TAP0, so losing either disables all channels | yes |
| H-10 | Shock through the user port | Battery at mains potential (ASM-5) | ISO7721DWV and AQY210EH, both reinforced 5 kV rms [P]; 8 mm board barrier | yes |
| H-11 | Overtemperature | 8 × 1.5 W | 3 NTCs. Max channels: 8 below 60 °C, 4 below 70 °C, 0 at ≥ 80 °C | yes |
| H-12 | Balancer causes imbalance | Unequal standing loads | Controller loads hang on the full stack. Per-cell loads ≤ 25 µA (C-9) | n/a |
| H-13 | Drains a pack the BMS has shut off | Upstream of the BMS switch | ≤ 50 µA sleep. Buck UVLO at 25 V. Deep sleep below 2.8 V/cell | yes |
| H-14 | TAP0 landed on P− instead of B− | Installer | Label and procedure. With a low-side-FET BMS open, cell 1 reads out of range, so the board locks out; the CH1 TVS and fuse limit damage | partial |

Standards context [S]:

- UL 1973 and IEC 62619 evaluate the battery's own BMS functions and their functional safety.
- UL 9540 covers the system; UL 9540A is the propagation test.
- NFPA 855 and IRC R328 govern residential installation.
- This board is not a protective device.

## 5. Architecture trade study

Weights:

- C1 fault containment: 0.30
- C2 control on LFP: 0.15
- C3 efficiency: 0.10
- C4 robustness and diagnostics: 0.15
- C5 parts (active, orderable, boring): 0.15
- C6 complexity and cost: 0.10
- C7 13–16S on one BOM: 0.05

Scores run 1–5 [I].

| Option | C1 | C2 | C3 | C4 | C5 | C6 | C7 | Total |
|---|---|---|---|---|---|---|---|---|
| A. Adjacent-cell inductor buck-boost (MCU, 30 FETs) | 4 | 4 | 3 | 2 | 3 | 2 | 4 | 3.25 |
| B. Switched/flying capacitor | 2 | 1 | 2 | 3 | 3 | 4 | 4 | 2.45 |
| C. Multi-winding transformer | 3 | 1 | 3 | 3 | 1 | 2 | 1 | 2.20 |
| D. Switch matrix + one converter (TI EMB1428 + EMB1499Q) | 1 | 4 | 4 | 2 | 2 | 3 | 4 | 2.40 |
| E. ADI LTC3300-1 bidirectional flyback + monitor | 2 | 5 | 5 | 4 | 4 | 2 | 3 | 3.40 |
| **F. ADI LT8584 per cell + ADBMS1818 + MCU** | **5** | **4** | **3** | **5** | **3** | **4** | **5** | **4.25** |
| G. AFE with bleed resistors (e.g. TI BQ76952) | excluded | | | | | | | the brief forbids bleed |

**Decision: F.**

Why each alternative loses:

- **B, switched capacitor.**
  - Current is proportional to ΔV. In the LFP plateau ΔV is 1–5 mV even at 10 % SOC difference, so nearly nothing moves, and IR drop or hysteresis can move charge the wrong way.
  - A cracked flying capacitor shorts a cell.
  - It switches all the time.
- **C, multi-winding transformer.**
  - Custom magnetics, not orderable; series count fixed.
  - Equalizes voltage, so it has the same LFP problem as B.
- **D, switch matrix.**
  - One shorted matrix FET plus one normal selection joins two non-adjacent taps, up to the full stack at kA. That is the exact failure the brief forbids.
  - Break-before-make depends on firmware.
  - EMB1428 status unknown (EMB1499Q is Active [P]).
- **A, adjacent-cell inductor.**
  - 15 floating half-bridges with level-shifted drivers.
  - Shoot-through shorts 2 cells.
  - Charge moves one hop at a time: 15 hops at 93 % ≈ 34 % [I].
  - No proven dedicated IC.
- **E, LTC3300-1** (runner-up: bidirectional, ≈ 90 % efficient [V], Active at $20.20 [P]).
  - Its synchronous secondary spans 12 cells. One shorted secondary FET puts ≈ 44 V across a winding, and only a fuse clears it.
  - Because it is bidirectional, it cannot use a series blocking diode.
  - 32 FETs and 32 sense resistors.
  - Kept as the fallback for Q-10.

What F costs:

- Unidirectional: a single low cell is fixed by discharging the other 15 cells. For 5 % that takes ≈ 8 h and costs ≈ 124 Wh once (C-2).
- ≈ 82 % converter efficiency, ≈ 75 % with a 1 m harness.
- The LT8584 is single-source.
- The ADBMS1818 has a long lead time (Q-11).

## 6. Blocks and domains

### 6.1 Blocks

Voltages are relative to TAP0. Currents are average maxima.

| Block | Function | Ports (dir · domain · V · I) |
|---|---|---|
| B1 HARNESS (off-board) | 17 wires, fuses, rings, plug P1 | TAPt_W in · CELL/STACK · 0–60 V · 2.6 A → J1 |
| B2 TAPIN | J1, fuses F100–F116, C-pin filters, net tie NT1 | TAPt_IN in, TAPt out (2.6 A); CS_t out (sense, ≤ 1 µA); GND_B |
| B3 CH[k], k = 1…16 | LT8584 flyback, T1kk, snubber, TVS, opto enable | TAPk, TAP(k−1) in · CELLk · 2.5–4.2 V · 2.6 A (6.8 A pk inside the CTRAN loop); S_k in · CELLk · 3 µA; LEDA_k, LEDA_k−1 · STACK · 1.6 mA; SEC_k→FLYBUS out · STACK · 0.2 A (1.7 A pk); TAP0 return |
| B4 RET | D1 stack return, D2 clamp, FLYBUS sense | FLYBUS in (≤ 60 V, ≤ 90 V clamp, 1.6 A); TAP16 out; FLY_SNS out (CTRL) |
| B5 AFE | ADBMS1818 + 3 NTCs | CS_0…16 in; S_1…16 out; SPI; VPLUS (1.4 mA); 5V_SYS (35 mA pk) |
| B6 PSU | F1, D3, R9, LM5164 (5 V), MCP1700 (3.3 V) | TAP16 in (≤ 10 mA); 5V_SYS (≤ 60 mA); +3V3 (≤ 25 mA) |
| B7 MCU | STM32G031K8, SWD, LEDs | SPI, UART, BAL_EN, FLY_SNS, PGOOD, ADBMS_WDT |
| B8 EN | BAL_EN current sink, 16-LED string | BAL_EN in; string TAP16→TAP0 (STACK, 1.6 mA) |
| B9 ISO | ISO7721DWV, AQY210EH, J2 | MCU_TX/RX (CTRL); TXD/RXD/VIO/GND_ISO (USER, 2.25–5.5 V, 5 mA); FLT_A/B (FAULT, ≤ 30 V, 50 mA) |

### 6.2 Domains

| Domain | Reference | Range to reference | Range to TAP0 (system ground) |
|---|---|---|---|
| BAT0: TAP0 (= stack −), GND_B via NT1 | — | 0 | 0 |
| CELLk, k = 1…16: TAPk, SW_k, SNB_k, OUT_k, DCH_k, S_k, CS_k | TAP(k−1) | 0–4.2 V; SW_k ≤ 38 V pk; ≤ 8.4 V in a swap fault | (k−1)·2.5 … k·4.2 V, capped at 60 V. For 16S LFP: CELL1 0–3.65, CELL8 17.5–29.2, CELL16 37.5–58.4 V |
| STACK: TAP16, STK_F, VPLUS, BUCK_IN, FLYBUS, SEC_k, LEDA_k, STR_Q | TAP0 | 32.5–60 V. FLYBUS ≤ 90 V in a clamp fault. LED nodes 30–57 V | same |
| CTRL: 5V_SYS, +3V3, logic | GND_B | 0–5.5 V | 0–5.5 V |
| USER: GND_ISO, VIO_ISO, TXD_ISO, RXD_ISO | GND_ISO | 0–5.5 V | floating; up to 250 V rms assumed |
| FAULT: FLT_A, FLT_B | floating | ≤ 30 V DC, 50 mA | floating |
| CHASSIS: screws, enclosure | earth | — | 0–60 V DC typical; 250 V rms worst case |

### 6.3 Barriers

FR-4 CTI ≥ 175 (material group IIIa), pollution degree 2. Values are creepage / clearance in mm.

| # | Pair | Grade | Working V | Rule source | Creepage / clearance |
|---|---|---|---|---|---|
| B-1 | CELLk ↔ CELLk±1 | functional | ≤ 4.2 V (8.4 V swap fault) | IPC-2221B Table 6-1, B2 0–15 V: 0.10 [S] | **0.20 / 0.20** |
| B-2 | CELLj ↔ CELLk (\|j−k\| ≥ 2); CELL ↔ STACK/BAT0/CTRL | functional | ≤ 60 V DC; FLYBUS ≤ 113 V transient | B2 31–150 V: 0.6 external; B1 0.1–0.2 internal [S] | **1.0 / 1.0 external, 0.3 internal** |
| B-3 | T1kk primary pads ↔ secondary pads | functional (part rated 1500 V rms [P]) | ≤ 60 V + 35 V pk | as B-2 | ≥ 1.0 (footprint gives ≈ 10) |
| B-4 | battery side (BAT0, CELL, STACK, CTRL) ↔ USER and FAULT | **reinforced** | 250 V rms (Q-3); OVC II → 2.5 kV impulse, one step up → 4 kV | IEC 60664-1 creepage at 250 V, PD2, MG III: 2.5 basic → 5.0. Clearance table F.2 at 4 kV: 3.0 (62368-1 Table 10: 3.8) [S] | need 5.0 / 3.8; **design 8.0 / 8.0** (ISO7721DWV 8.5 [P]). No slot. Still meets PD3 (6.4) |
| B-5 | battery side ↔ CHASSIS (H1–H6) | basic | 250 V rms worst case | 2.5 creepage / 1.5 clearance (2.5 kV) [S] | **3.0** copper-free ring around each screw head, all layers |
| B-6 | USER ↔ FAULT | functional | ≤ 30 V | B2 ≤ 30 V: 0.1 [S] | 0.5 |

## 7. Calculations

**C-1 Pack.**

- 16 × 3.2 V × 200 Ah = 10.24 kWh.
- 16S LFP stack: 40.0–58.4 V. 13S minimum: 32.5 V.
- One 200 Ah LFP cell short-circuited: ≈ 3.2 V / 0.25 mΩ ≈ 13 kA [S].

**C-2 Balancing current and time.**

- Datasheet: LT8584 + NA5743-AL at 50–60 V gives 2.4–2.6 A average discharge, 80–84 % efficient [P, Figs. G32/G33].
- Boundary-mode check at V_IN = 3.15 V, I_pk = 6.3 A, L_pri = 4 µH, L_sec = 64 µH:
  - t_on = L·I_pk/V_IN = 8.0 µs
  - t_off = 64 µH × 1.58 A / 59 V = 1.71 µs
  - f ≈ 98 kHz
  - I_in = ½·I_pk·t_on/T = 2.47 A ✓
  - I_pri,rms = 6.3·√(0.78/3) = 3.2 A
- Daily capacity: 2 h/day in the LFP top window × 2.5 A = 5 Ah = 2.5 %/day. That is 10× typical drift and 2× worst case (ASM-7).
- One cell 5 % (10 Ah) high: 4 h.
- One cell 5 % low: the other 15 are discharged in two batches at a relative 2.5 A, ≈ 8 h. Loss ≈ 15 × 10 Ah × 3.3 V × 0.25 ≈ 124 Wh.

**C-3 Series-count envelope.**

- Transformer output range 30–80 V [P] covers 13S LFP (32.5 V) and 16S NMC (67.2 V).
- ADBMS1818 limits are met [P]: V+ 16–90 V; V+ − C12 ≤ 40 V (16.8 V here).
- For N < 16, J1 pins N+1…17 are bridged in the plug. The datasheet allows unused C inputs to be "shorted to the highest connected cell" [P].

**C-4 LFP observability and policy.**

- **Plateau** (≈ 20–90 % SOC): slope 0.5–1 mV/% and 20–30 mV hysteresis [S]. A ±4 mV error is ±4–8 % SOC, so cells are unobservable and there is no balancing.
- **Above ≈ 95 % SOC** (3.40–3.65 V): slope ≥ 20 mV/% [S], so 4 mV ≤ 0.2 % SOC.
- **LFP policy.**
  - Start when V_max ≥ 3.45 V and ΔV ≥ 20 mV (1 min average, 26 Hz filtered mode).
  - Discharge cells with V ≥ V_min + 10 mV, highest first, at most 8.
  - Stop when ΔV ≤ 5 mV or V_max < 3.40 V.
- **NMC policy.** At rest (|dV/dt| < 1 mV/min), V ≥ 3.9 V, ΔV ≥ 15 mV.
- SOC-based balancing needs pack current or capacity data, which the board does not have (Q-2).

**C-5 LT8584 stresses** (V_IN ≤ 4.2 V, FLYBUS ≤ 60.5 V).

- SW flat-top = 4.2 + (60.5 + 1)/4 = 19.6 V. Rule "≤ 40 VDC" [P]: 49 %.
- Leakage spike, clamped by C-6: ≈ 38 V vs 50 V abs max (76 %).
- In a 90 V clamp fault: 27 V.
- V_IN 4.2 V vs 5.3 V recommended (79 %) and 9 V max.
- I_pk 6.0–6.8 A [P] vs transformer rating 7.0 A [P] (97 %). This is ADI's own pairing (Table 3); accepted, but checked for saturation in T-EFF.

**C-6 RCD snubber.**

- Leakage energy ½ × 0.116 µH (max [P]) × 6.3² = 2.3 µJ; at 98 kHz that is 0.23 W.
- Clamp voltage V_c = √(0.23 × 4.99 kΩ) = 34 V above V_IN, which is above the reflected 15.4 V ✓.
- R1kk: 2010 size, 0.5 W → 46 %. C5kk: 100 V → 34 %. D2kk reverse 38/400 V → 10 %.

**C-7 Fuses and fault currents.**

Per-tap path R_p ≈ 60 mΩ:

| Element | Resistance |
|---|---|
| 18 AWG wire, 1 m at 40 °C | 22.6 mΩ [S] |
| 0324007 | 18.7 mΩ [P] |
| 0451005 | 12.5 mΩ [P] |
| Connector, crimps, PCB | ≈ 6 mΩ [I] |

| Fault | Prospective current | Clears | Rating |
|---|---|---|---|
| One cell, on board | 4.2 / 0.125 = 34 A | F1tt: I²t 5.57 A²s → 4.8 ms. Inline: 71 A²s → 61 ms, so selective | Nano2 300 A at 32 VDC [P] ✓ |
| Two cells (swap) | 67 A | 1.2 ms | ✓ |
| Stack, on board (needs 2 faults) | 58.4 / 0.12 = 487 A | beyond Nano2's 50 A at 125 V. The inline 3AB clears in 0.3 ms | 10 kA at 125 VDC [P] ✓ |
| Wire-wire at battery end | 58.4 / 43 mΩ = 1.35 kA | inline | ✓ |
| Wire to earthed chassis | 58.4 / 24 mΩ = 2.5 kA | inline | ✓ |

- 18 AWG at 7 A matches NEC 240.4(D) [S].
- Tap current ≤ 2.6 A (TAPk carries \|I_k − I_k+1\|; TAP0 and TAP16 also carry the opposing flyback return).
  - Board fuse: 2.6 A vs 5 × 0.75 (UL 248-14) × 0.9 (≈ 60 °C [I]) = 3.4 A → 77 %.
  - Inline fuse: 2.6 / (7 × 0.75) → 50 %.
- F1 (125 mA) carries ≈ 10 mA. A buck or V+ short draws 0.57 A, 4.6× rating, and clears in milliseconds [I]. R9 (2512) absorbs ≈ 0.3 J.

**C-8 Harness loss and efficiency** (1 m, R_loop 120 mΩ, 2.5 A, cell 3.45 V).

- Harness loss 2.5² × 0.12 = 0.75 W (8.7 %), so V_IN = 3.15 V.
- η_conv 82 % [P] → P_out = (8.63 − 0.75) × 0.82 = 6.46 W.
- **End-to-end 75 %**; board only 82 %.
- I_out = 0.116 A at 55.5 V (≈ 0.2 A at 32.5 V).
- A 0.5 m harness gives 77 %. More than half of the loss is in the two fuses.

**C-9 Standing currents.**

Per cell, with balancing off:

| Load | Current |
|---|---|
| LT8584 shutdown | ≤ 1 µA [P] |
| SW leakage | ≤ 4 µA [P] |
| ADBMS1818 C pin | ≤ 0.25 µA [P] |
| TVS | ≤ 20 µA at 5 V [P, ADI Table 5]; far lower at 3.3–4.2 V [I] |
| TLP293 dark current | ≤ 0.08 µA [P] |
| **Worst case** | **≈ 25 µA** (typically ≈ 2 µA) |

- Worst-case mismatch: 0.22 Ah/yr, which is 0.11 % of 200 Ah and about 5 minutes of balancing.
- While BAL_EN is on, R2kk adds 3.3 V / 33 kΩ = 100 µA per cell, equal to ±1 %.

Stack, in sleep:

| Load | Current |
|---|---|
| LM5164 | 10.5 µA typ / 25 µA max [P] |
| UVLO divider | 11.7 µA |
| ADBMS1818 V+ | 3 µA typ / 9 µA max [P] |
| 5 V-side loads, reflected (VREG 3.1, LDO 1.6, MCU Stop1 with RTC 3.7 µA [P]) | ≈ 1.4 µA |
| **Total** | **≈ 27 µA typ, ≤ 50 µA** (0.24–0.44 Ah/yr) |

**C-10 Hot plug.**

- L ≈ 2 µH, R 0.12 Ω, C ≈ 110 µF (DC-biased) → ζ = 0.06 × √(110/2) = 0.44 → overshoot ≈ 21 % (4.2 → 5.1 V, against 9 V max).
- A floating node between connected taps reaches ≤ 1.25 × V_cell = 5.25 V with ±20 % capacitors.
- D3kk (V_BR 6.4–7.07 V [S]) clamps anything higher.

**C-11 Timing and self-tests.**

- **Watchdog.** DTEN is tied to V−, so 1.8–2.2 s without a command resets DCC [P]. The MCU sends a command every ≤ 0.5 s.
- **Fault loop.** FLY_SNS is checked every 10 ms. If FLYBUS − SC > 4 V, the MCU drops BAL_EN and clears DCC within 1 ms.
- **Measurement.** MUTE → ADCV filtered → UNMUTE, every 5 s.
- **Open-wire test.** ADOW's 100 µA sources only work up to 10 nF per node [P]; each node here has 200 µF. So each session starts with a 5 ms single-channel pulse test:
  - A healthy tap drops 2.5 A × R_loop ≈ 0.3 V.
  - An open tap collapses at 6 V/ms until UVLO.
  - The same pulse measures harness resistance and proves both enable paths (BAL_EN off → no step; DCC off → no step).

**C-12 Thermal.**

Board loss per channel ≈ 1.5 W:

| Part | Loss | Result |
|---|---|---|
| LT8584 | 0.55 W × 38 °C/W (650 mm² [P]) | T_J 91 °C at 70 °C local |
| Transformer | 0.5 W | |
| D1kk | 0.13 W | |
| Fuses | 0.08 W | |
| D1 (common) | 0.7 W | |

- Eight channels ≈ 12 W.
- Board 0.07 m² (both sides) at h ≈ 10 W/m²K gives ΔT ≈ 17 K, plus ≈ 10 K for the enclosure → 72 °C at 45 °C ambient. Hence the H-11 derating.

**C-13 Buck (LM5164)** (equations from the TI datasheet [P]).

| Item | Value |
|---|---|
| R12 (R_RON) | 49.9 kΩ → f = 5 × 2500/49.9 = 250 kHz. t_on(60 V) = 0.33 µs > 50 ns |
| L1 | 47 µH: ΔI = 0.39 A at 60 V; peak 0.26 A. I_sat 1.44 A (10 %) / 2.2 A (30 %) [P] vs 1.75 A current limit [P], so saturation only in a fault |
| C11 | 22 µF, ≈ 14 µF at 5 V [I] → 14 mV ripple |
| R13/R14 | 316 k / 100 k → 4.99 V |
| Ripple injection (Type 3) | C12 (C_A) ≥ 10/(f·(R13‖R14)) = 0.53 nF → 1 nF. R15 (R_A) 470 kΩ: ramp ≈ 36–39 mV over 32–60 V; R_A·C_A = 470 µs ≤ 901 µs ✓. C13 (C_B) ≥ 100 µs/(3·R13) → 220 pF |
| UVLO | R10/R11 = 4.7 M/300 k → on 25.0 V, off 23.3 V |
| C8 | 2.2 µF 100 V (≈ 1 µF at 58 V [I]) → 19 mV |

- VPLUS goes through 100 Ω. At 1.35 mA, V+ − C18 = −0.14 V, inside the ≥ −0.3 V limit [P].
- VREG is fed by the buck, which the datasheet allows [P]; DRIVE is left open [I].
- MCP1700: (5 − 3.3) × 25 mA = 43 mW.

**C-14 BAL_EN string.**

- Q1 sink: (3.3 − 0.65 − 0.2)/1.6 kΩ ≈ 1.5 mA (h_FE ≥ 80 [P]).
- Compliance at 32.5 V: 32.5 − 0.9 − 7.05 − 16 × 1.15 − 0.3 − 2.4 = 3.5 V ✓.
- TLP293 GB gives ≥ 30 % CTR at 1 mA, V_CE 0.4 V [P], so ≥ 0.45 mA available against 0.13 mA needed.
- DCHRG high ≈ V_IN − 0.1 V vs a 0.5–1.1 V threshold [P].
- Off state: dark current ≤ 5 µA (hot, [I]) × 33 kΩ = 0.17 V < 0.5 V.
- Q1 dissipates 45 mW at 30 V; V_CE ≤ 58 V of 160 V (36 %).
- Q1 C–E short: 6.2 mA. R24 (2010) 0.18 W (36 %); R23 (0805) 0.06 W (49 %).

**C-15 FLYBUS.**

- C6kk 2.2 µF 100 V. Needed ≥ 400·L/V² = 1.5 µF at 32.5 V [P]. Each gives ≈ 1.0–1.5 µF derated, ×16 in parallel.
- Surge ≥ 50·N = 200 V; a 100 V MLCC has 2.5× surge [P].
- Normal 61 %; 90 % only in a clamp fault.
- D1kk ES1G: 60.5 + 4 × 4.2 = 77 V (19 %).
- D1 V8P10: 58.4 V (58 %) with a D1kk shorted; ≤ 1.6 A of 8 A.
- D2 SMBJ70A: V_R 70 V ≥ 60.5 V; clamps ≈ 86–90 V at ≤ 1.6 A [P].
- FLY_SNS divider: 2 MΩ/100 kΩ maps 60 V to 2.86 V; at 90 V it injects 7 µA into the MCU clamp.

**C-16 NTCs.**

- 10 kΩ, B25/85 3434 K [P], with a 10.0 kΩ 0.1 % pull-up from VREF2 = 3.000 V [P].
- 1.50 V at 25 °C; 0.543 V at 70 °C (−9 mV/K); 0.380 V at 85 °C.
- Self-heating 0.14 K.

## 8. Parts

One row per distinct part. Stress is the worst case in this design. Lifecycle was checked at
Digi-Key in Oct 2026 unless noted. KiCad ids were checked against the KiCad 10.0.7 libraries.

| Role (refdes) | Mfr / MPN | Ratings | Stress (margin) | Package; KiCad symbol / footprint | Datasheet | Lifecycle | 2nd source |
|---|---|---|---|---|---|---|---|
| Balancer U101–U116 | ADI LT8584EFE#PBF | V_IN 2.5–5.3 V (9 V max); SW ≤ 40 VDC, 50 V spikes; 6 A | V_IN 47 %; SW 76 %; T_J 91 °C | TSSOP-16 EP. **custom symbol** / `Package_SO:TSSOP-16-1EP_4.4x5mm_P0.65mm` (LT FE16; EP 2.94 × 3.58 mm [P/I]) | Rev B [P] | Active, $9.58 [P] | none |
| Transformer T101–T116 | Coilcraft NA5743-ALD | 4 µH, 1:4, 7 A pk, DCR 12 mΩ / 0.5 Ω, L_lk ≤ 0.116 µH, 1500 V rms | 6.8 A (97 %, C-5); 8.6 W in, rated 7–12 W | SMD 15.2 × 12.7 × 11.4 mm. **custom symbol + footprint** per Doc 1075 land pattern (2 × 4 pads 2.03 × 1.27 mm, 2.50 mm pitch, 11.68 mm span) [P] | Doc 1075 [P] | listed; Farnell stock [S] | Würth 750314018 (ADI Table 3 [P], availability unverified) |
| Diodes D101–D116, D201–D216, D3, D4 | Diodes Inc ES1G-13-F | 400 V, 1 A, 25 ns, I_R 5 µA | ≤ 107 V (27 %) | SMA. `Device:D` / `Diode_SMD:D_SMA` | DS14001 [P] | Active [S] | Vishay ES1G |
| TVS D301–D316 | ST SMA6T6V7AY | V_RM 5 V, V_BR ≥ 6.4 V, 600 W | 4.2 V (within standoff) | SMA. `Device:D_Zener` / `Diode_SMD:D_SMA` | ADI Table 5 [P]; ST sheet not readable | Active [P] | Littelfuse SMAJ6.0A |
| 100 µF C101–C116, C201–C216 | Murata GRM32ER61A107ME20L | 10 V X5R | 42 % | 1210. `Device:C` / `Capacitor_SMD:C_1210_3225Metric` | [P] | Active (17 wk) [P] | TDK C3225X5R1A107M |
| 1 µF C301–C316, C14, C15, C17* | Murata GRM188R71A105KA61D | 10 V X7R | ≤ 50 % | 0603 / `C_0603_1608Metric` | [S] | Active [S] | Samsung CL10B105KP8NNNC |
| 47 nF C401–C416 | Murata GRM188R71H473KA61D | 50 V X7R | 8 % | 0603 | [S] | Active [S] | any |
| 22 nF C501–C516 | Murata GCM188R72A223KA37D | 100 V X7R | 34 % | 0603 | [S] | Active [S] | TDK CGA3E2X7R2A223K |
| 2.2 µF C601–C616, C8 | KEMET C1210C225K1RACTU | 100 V X7R | 61 % (90 % in fault) | 1210 | [P] | Active [P] | Taiyo Yuden HMK325B7225KN-T |
| 4.99 kΩ R101–R116 | Yageo RC2010FK-074K99L | 0.5 W | 46 % | 2010 / `R_2010_5025Metric` | [S] | Active [S] | Vishay CRCW2010 |
| 33 kΩ R201–R216; 10 kΩ R401–R416 | Yageo RC0603FR-0733KL; RC0603FR-0710KL | 0.1 W | < 2 % | 0603 | [S] | Active | any 1 % |
| Opto U201–U216 | Toshiba TLP293(GB-TPL,E | 80 V, CTR 100–600 %, 3750 V rms, 5.0 mm creepage | V_CE ≤ 4.2 V | SO4. `Isolator:TLP293` / `Package_SO:SOIC-4_4.55x2.6mm_P1.27mm` | 2019-11-29 [P] | Active [P] | Lite-On LTV-357T |
| Battery-end fuse HF0–HF16 | Littelfuse 0324007.HXP | 7 A, 125 VDC, 10 kA, I²t 71 A²s | 50 % | 3AB axial; off-board | rev 07/31/15 [P] | listed, $3.03 [P] | 0314007.MXP in a holder |
| Board fuse F100–F116 | Littelfuse 0154005.DR (OMNI-BLOK + Nano2 451 5 A) | 125 V; 50 A at 125 V, 300 A at 32 VDC; 12.5 mΩ | 77 % derated | `Device:Fuse` / `Fuse:Fuseholder_Littelfuse_Nano2_154x` | fuse [P]; holder [S] | Active [S] | 0451005.MRL soldered |
| Supply fuse F1 | Littelfuse 0451.125MRL | 125 mA, 125 V, 1.7 Ω | 8 % | 2410. `Fuse:Fuse_Littelfuse-NANO2-451_453` | [P] | Active [S] | Bel 0685P0125 |
| Monitor U1 | ADI ADBMS1818ASWZ | 18 cells; V+ ≤ 90 V (112.5 V abs max); TME ±3–4.8 mV; −40…85 °C | 52 % | LQFP-64 EP. **custom symbol**; footprint `Package_QFP:LQFP-64-1EP_10x10mm_P0.5mm_EP5x5mm_ThermalVias` with the EP land changed to 5.74 mm (ADI Fig. 113 [P]) | Rev A [P] | Active, **52 wk** [P] | LTC6813-1 (same pinout [P]) |
| MCU U2 | ST STM32G031K8T6 | 1.7–3.6 V | — | `MCU_ST_STM32G0:STM32G031K8Tx` / `Package_QFP:LQFP-32_7x7mm_P0.8mm` | DS12992 [P] | Active [S] | STM32G031K6T6 |
| Buck U3 | TI LM5164DDAR | 100 V, 1 A, I_Q 10.5 µA | 61 % | `Regulator_Switching:LM5164DDA` / `Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm_ThermalVias` | SNVSAU4D [P] | Active [S] | LM5163 |
| L1 | Coilcraft MSS1048-473MLB | 47 µH, I_sat 1.44/2.2 A | 0.26 A pk | `Device:L` / `Inductor_SMD:L_Coilcraft_MSS1048-XXX` | Doc 462 [P] | Active [S] | Bourns SRR1050A-470M |
| LDO U4 | Microchip MCP1700T-3302E/TT | 6.0 V operating, 6.5 V abs max | 5 V (77 % of abs max) | `Regulator_Linear:MCP1700x-330xxTT` / `Package_TO_SOT_SMD:SOT-23` | [P] | Active [S] | TI TPS7A0233 |
| Isolator U5 | TI ISO7721DWVR | reinforced 5 kV rms; 8.5 mm; CTI > 600 | logic | `Isolator:ISO7721DWV` / `Package_SO:SOIC-8_7.5x5.85mm_P1.27mm` | SLLSEP3G [P] | Active [S] | ADuM1201BRWZ |
| Fault contact U6 | Panasonic AQY210EHAX | reinforced 5 kV; 350 V, 130 mA | 30 V/50 mA (37 %) | `Relay_SolidState:AQY280EH` (same pinout) / `Package_DIP:SMDIP-4_W7.62mm` | [P] | Active [P] | AQY214EHAX |
| D1 stack return | Vishay V8P10-M3/86A | 100 V, 8 A | 58 %, 1.6 A | `Device:D_Schottky_AAK` / `Package_TO_SOT_SMD:TO-277A` (1, 2 = A; 3 = K) | 89005 [P] | Active [S] | V8PM10 |
| D2 FLYBUS clamp | Littelfuse SMBJ70A | V_R 70, V_BR 77.8–86 V | ≤ V_R | `Device:D_Zener` / `Diode_SMD:D_SMB` | [P] | Active [S] | Vishay SMBJ70A |
| Q1 | onsemi MMBT5551LT1G | 160 V, 600 mA | 36 % | `Transistor_BJT:MMBT5551L` / `SOT-23` | Rev 12 [P] | Active [S] | Nexperia PMBT5551 |
| TH1–TH3 | Murata NCP18XH103F03RB | 10 k 1 %, B 3380 K | 0.14 mW | `Device:Thermistor_NTC` / `R_0603_1608Metric` | [P] | Active [S] | TDK NTCG163JF103FT1 |
| J1 | Phoenix MSTBA 2,5/17-G-5,08 (1757394) | 12 A, 320 V | 2.6 A, 60 V | `Connector_Generic:Conn_01x17` / **custom**: KiCad `PhoenixContact_MSTBA_2,5_16-G-5,08…` plus one position | [S] | Active [S] | Würth 5.08 mm header |
| P1 (off-board) | Phoenix MSTB 2,5/17-ST-5,08 (1757161); EBP 2-5 bridges (1733169) for N < 16 | 12 A, 320 V | as J1 | — | [S] | Active [S] | — |
| J2 | Phoenix MC 1,5/6-G-3,81 (header number 1803316 inferred [I]); plug MC 1,5/6-ST-3,81 (1803617) | 8 A, 160 V | 5 mA | `Connector_Generic:Conn_01x06` / `Connector_Phoenix_MC:PhoenixContact_MC_1,5_6-G-3.81_1x06_P3.81mm_Horizontal` | [S] | Active [S] | — |
| Rings HT0–HT16 | Panduit PV18-14R-MY | 22–18 AWG, ¼" (M6) | — | off-board | [S] | Active [S] | TE PIDG ¼" |
| Wire HW0–HW16 | UL 1015 18 AWG Cu, 600 V, 105 °C | 22.6 mΩ/m | 2.6 A | off-board | [S] | — | SAE GXL 18 AWG |
| Misc. passives, LEDs, test pads, holes | Yageo RC 1 %; Murata X7R; Lite-On LTST-C191KGKT / KRKT; Tag-Connect TC2030-NL; M4 holes | per CONNECTIONS.md | R ≤ 50 % P; C ≤ 61 % V | standard `Device:*` | [S] | Active [S] | equivalents |

*C17 is 4.7 µF (MCU bulk); see CONNECTIONS.md.

## 9. Placement and mechanical constraints

**Board.**

- 270 × 130 mm, 4 layers, 1.6 mm FR-4 (CTI ≥ 175).
  - L1 and L4: 2 oz.
  - L2: per-channel reference islands.
  - L3: 2 oz, tap corridors and spine.
- Top-side assembly only. Tallest part: T1kk at 11.4 mm.
- Six M4 non-plated holes, each with a 3.0 mm copper keepout (B-5). Nylon standoffs onto a panel or DIN carrier.
- The board sits in a V-0 plastic enclosure inside the battery cabinet, next to the cells, so the harness stays ≤ 1 m.

**Zones.**

- **West (x 0–40 mm).** J1 on the edge, the fuse column, C-pin filters, U1.
- **South row (y 5–55 mm).** CH01 to CH08, running west to east.
- **North row (y 75–125 mm).** CH16 to CH09, running west to east.
- **Spine (y 55–75 mm).** FLYBUS and TAP0 power buses, the LED string, D1 and D2 at the west end, the NTCs.
- **East (x 235–270 mm).** PSU, MCU and ISO, with J2 on the east edge.

The U-shape keeps neighbouring channels one cell apart. CH08 and CH09 meet on TAP8 at the east end.

```
group(TAPIN: J1, F100..F116, R300..R316, C700..C716, NT1)
group(AFE: U1, R1..R8, C1..C7)
group(CH[k]: U1kk, T1kk, D1kk, D2kk, D3kk, C1kk..C6kk, R1kk, R2kk, R4kk, U2kk)   # kk = 01..16
group(RET: D1, D2, R19, R20, C19)
group(PSU: F1, D3, R9, C8..C15, U3, U4, L1, R10..R16)
group(MCU: U2, C16..C18, J3, D5, D6, R17, R18, TP1..TP6)
group(EN: Q1, R21..R24, D4)
group(ISO: U5, U6, C20, C21, R25..R28, J2)

edge(J1, west); pin_order(J1, axis=y, pin1=south)
edge(J2, east); side(*, top)
array(F100..F116, y, pitch: equal); align(F1tt, J1.(tt+1)); near(F1tt, J1.(tt+1), tight)
kelvin(R3tt.1, F1tt.2)
near(R3tt, U1, close); near(C7tt, U1, close)              # filters at the IC [P]
net_tie(NT1: TAP0 ↔ GND_B, at F100.2)
near(U1, F100..F116, close); far(U1, T1kk)

array(CH01..CH08, x, pitch: equal); array(CH16..CH09, x, pitch: equal)
symmetric(CH[k], CH[17-k], axis: spine)
near(CH01, J1.1, close); near(CH16, J1.17, close)
orient(T1kk, pins 1-4 → own cell edge, pins 5,8 → spine)
hot_loop([C2kk.1, T1kk.1, T1kk.2, T1kk.3, T1kk.4, U1kk.13..16, U1kk.17, C2kk.2], "primary, ≤ 15 mm perimeter")
hot_loop([T1kk.5, D1kk.2, D1kk.1, C6kk.1, C6kk.2, T1kk.8], "secondary")
hot_loop([U1kk.13, D2kk.2, D2kk.1, C5kk.1, C5kk.2, U1kk.9], "RCD clamp")
near(C3kk, U1kk.9, tight); near(C2kk, T1kk.1, tight); near(C2kk, U1kk.17, tight)
near(C1kk, D3kk, tight); near(C4kk, U1kk.8, tight); near(R2kk, U1kk.12, tight); near(R4kk, U1kk.5, tight)
near(U2kk, U1kk.12, close); near(C6kk, D1kk.1, tight)
thermal(U1kk, 0.6, copper ≥ 650 mm² on TAP(k-1), L1+L2+L4, ≥ 9 vias under EP)
thermal(T1kk, 0.5, natural convection)
near(D1, F116, close); near(D2, D1, close); thermal(D1, 0.7, ≥ 400 mm² on the TAP16 tab)
near(TH1, U103, close); near(TH2, U106, close); near(TH3, U112, close)

separate(CELLk, CELLk±1, 0.2, 0.2, slot: no)
separate(CELLj, CELLk, 1.0, 1.0, slot: no)                # |j-k| ≥ 2; 0.3 on inner layers
separate(CELLk, STACK|BAT0|CTRL, 1.0, 1.0, slot: no)
separate(BATTERY, USER|FAULT, 8.0, 8.0, slot: no)         # BATTERY = BAT0 ∪ CELL* ∪ STACK ∪ CTRL
separate(BATTERY, CHASSIS, 3.0, 3.0, slot: no)            # around H1..H6
keepout(gap under U5 and U6, copper and vias, all layers)
keepout(T1kk primary–secondary pad gap, foreign-domain copper, all layers)
keepout(1210 MLCCs, ≥ 5 mm from edges and holes, top)

hot_loop([C8.1, U3.2, U3.8, L1, C11, U3.1, C8.2], "buck input/output")
near(C8, U3.2, tight); near(C10, U3.7, tight); near(R12, U3.4, tight); near(R13, U3.5, close)
near(C1, U1.1, tight); near(C2, U1.48, tight); near(C3, U1.51, tight); near(C4, U1.50, tight)
far(U3, U1); near(C16, U2.4, tight); near(C18, U2.6, tight)
straddle(U5, BATTERY|USER); straddle(U6, BATTERY|FAULT); far(J2, J1)

island(TAP(k-1), L2, under CH[k])                        # per-channel reference plane
corridor([TAP0..TAP8, S_1..S_8], south edge, L3, ordered by index)
corridor([TAP16..TAP8, S_16..S_9], north edge, L3, ordered by index)
current(TAPt, 2.6 A); current(FLYBUS, 1.6 A); current(TAP0, 2.6 A)   # ≥ 1.5 mm on 2 oz, ΔT ≤ 10 K [S, IPC-2152]
```

**Extensions to the vocabulary.**

- `pin_order(ref, axis, pin1=side)`: taps must enter in physical order.
- `kelvin(a, b)`: the sense trace leaves pad b on its own, not along the power path.
- `net_tie(id: A ↔ B, at pad)`: joins the power return to the controller ground at one point.
- `orient(ref, pins → direction)`: the transformer's barrier faces the spine.
- `straddle(ref, domA|domB)`: the part's body sits across a barrier.
- `island(net, layers, under group)`: a reference-plane island per domain. Each channel needs its own plane, at its own potential.
- `corridor(nets, edge, layer, ordered)`: an ordered bus. Taps must run in potential order, so neighbouring traces differ by one cell.
- `current(net, A)`: sets the trace width.

**Installation.**

- J1 pin p carries TAP(p−1). Pin 1 is the B− **cell** terminal, never P−. Pin 17 is the top cell +.
- For N < 16, bridge plug positions N+1…17 and set N in the firmware; the firmware checks it at boot.
- Harness: wires in tap order with no crossings, laced every 100 mm, labelled 0…16 (0 black, 16 red).
- Procedure:
  1. Idle the pack.
  2. Mount the board with the plug off.
  3. Land the rings from B− upward.
  4. At the plug, check with a DMM that every adjacent pair reads 2.5–4.2 V with pin p+1 > pin p, and that the sum equals the stack voltage.
  5. Plug in.

## 10. Verification plan

**Simulation**

- **S-1.** KiCad ERC. DRC with custom rules from §6.3, using net classes CELLk (indexed), STACK, USER and CHASSIS.
- **S-2.** LTspice, one channel, using the ADI LT8584 model.
  - Sweep V_IN 2.5–4.2 V and FLYBUS 32.5–67 V, with the harness R and L included.
  - Check I_in against Fig. G32, SW ≤ 40 V, and the R1kk, D1kk and C6kk stresses.
  - Run the faults: open FLYBUS, shorted D1kk, shorted C6kk.
- **S-3.** Buck stability with the Type-3 network, 25–60 V input, 0–60 mA load steps.

**Bench tests**

| Test | Method | Pass |
|---|---|---|
| T-FUNC | 16S and 13S packs of 20–100 Ah LFP; configuration, telemetry, fault contact | all functions work |
| T-EFF | ring-side power vs stack return; 0.5 m and 1 m harness; 25 and 45 °C; SW current probe | REQ-3/4; no saturation knee |
| T-MEAS | balancing on vs muted, against a 6½-digit DMM | ≤ ±4 mV muted |
| T-BAL | 16S, 200 Ah: one cell +5 %, one cell −5 %, random ±2 % | ≤ 6 h, 10 h, 4 h of top-window time |
| T-IQ | µA meter in every tap; sleep and active; 25 and 45 °C | REQ-12, REQ-13 |
| T-THERM | 8 channels in an enclosure in a 45 °C chamber; IR camera | REQ-21; derating steps work |
| T-HIPOT | J2 vs the battery side: reinforced test for 250 V rms (≈ 3 kV rms, 60 s [S]). Battery side vs chassis: 1.5 kV | no breakdown |
| T-EMC | harness conducted emissions; ESD ±8 kV contact on J2, ±4 kV on J1 | no reset or damage |
| T-XFMR | incoming sample hipot of T1kk primary ↔ secondary at 1.5 kV rms, 60 s (the H-2 safeguard) | no breakdown |
| T-AOI | 100 % AOI/X-ray of U1kk pins 4–7 and the EP (cell-short and stuck-enable bridges, H-1/H-4) | no bridges |

**Fault injection**

One test per hazard, in a fire-safe box, with a Rogowski probe on the current.

| Test | Injection | Pass |
|---|---|---|
| F-1 (H-1) | short C1kk, U1kk SW–GND, D3kk (k = 1, 8, 16) | fuse clears ≤ 10 ms; no flame; I²t as C-7 |
| F-2 (H-2) | short D1kk | LT8584 latches its switch error [P]; no TAP16→TAP0 current |
| F-3 (H-2) | short D1; then D1 + D1kk | single: no effect; double: fuses clear (record) |
| F-4 (H-2) | short C6kk; short D2 | D1 blocks; channels stop |
| F-5 (H-9) | open TAP0/1/8/15/16, idle and with 8 channels on | detected before start; stop ≤ 1 s; FLYBUS ≤ 90 V |
| F-6 (H-8) | swap k/k+1; swap k/k+2; reverse the harness; offset the plug one pin | no fire; fuses open; lockout; damage logged |
| F-7 (H-7) | 200 rocked plug cycles; scope every V_IN and C pair | ≤ 9 V (LT8584), ≤ 8 V (pair) |
| F-8 (H-4) | S_k low with BAL_EN off; Q1 shorted with DCC off; MCU halted; LED string open; DIN bridged to pin 6 | no discharge; stop ≤ 2.2 s; BAL_EN stops the bridged channel |
| F-9 (H-5) | one cell held at V_full while others balance | its net current < 0 throughout |
| F-10 (H-9) | lift D1 while balancing | FLYBUS ≤ 90 V; stop ≤ 50 ms |
| F-11 (H-2) | short U3 V_IN; short ADBMS1818 V+ | F1 clears; nothing else damaged |
| F-12 (H-6) | 2.5 A balancing, MUTE off vs on | error quantified |
| F-13 (H-11) | NTC open and short; airflow blocked | AXOW flags it; derating works |
| F-14 (H-14) | TAP0 on P− of a low-side-FET BMS, then BMS opens | lockout; worst case one fuse |
| F-15 (H-12) | 30 days idle on 16S, rest voltages logged | no drift beyond C-9 |

## 11. Sources

**Primary (read)**

- ADI LT8584 Rev B, via an [rlocman mirror](https://www.rlocman.ru/i/File/2017/10/23/8584fb.pdf): pins p.9; Tables 3–8; Figs. 2, 3, 12, 14; G32/G33.
- ADI LTC6813-1 Rev B, via [LCSC C2758259](https://www.lcsc.com/product-detail/C2758259.html): pp. 3, 15, 32–35, 45, 70–75, 85.
- ADI ADBMS1818 Rev A, via [LCSC C2971928](https://www.lcsc.com/product-detail/C2971928.html): Table 14, Fig. 113.
- Coilcraft [NA5743 Doc 1075](https://www.coilcraft.com/pdfs/na5743.pdf) and [MSS1048 Doc 462](https://www.coilcraft.com/pdfs/mss1048.pdf).
- TI [LM5164](https://www.ti.com/lit/ds/symlink/lm5164.pdf) and [ISO7721](https://www.ti.com/lit/ds/symlink/iso7721.pdf); TI [EMB1499Q](https://www.ti.com/product/EMB1499Q) product page.
- ST STM32G031 DS12992, via [LCSC C432203](https://www.lcsc.com/product-detail/C432203.html).
- Microchip [MCP1700](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP1700-Low-Quiescent-Current-LDO-20001826E.pdf).
- Vishay [V8P10](https://www.vishay.com/docs/89005/v8p10.pdf).
- Littelfuse 314/324 ([chipdip](https://static.chipdip.ru/lib/536/DOC021536932.pdf)).
- Via LCSC: Littelfuse 451/453 (C48467), SMBJ (C224025); Toshiba TLP293 (C77656); Diodes ES1x (C674398); onsemi MMBT5551 (C150072); Panasonic AQY21xEH (C24728); Murata NTC (C77131), GRM32ER61A107ME20 (C84455).
- Digi-Key, Oct 2026: [LT8584](https://www.digikey.com/en/products/result?keywords=LT8584EFE%23PBF), [LTC3300-1](https://www.digikey.com/en/products/detail/analog-devices-inc/LTC3300ILXE-1-PBF/3913110), [ADBMS1818](https://www.digikey.com/en/products/detail/analog-devices-inc/ADBMS1818ASWZ/13978974), TLP293, AQY210EHAX, SMA6T6V7AY, GRM32ER61A107ME20L, and GRM32ER72A225KA35L (NRND, so KEMET C1210C225K1RACTU is used instead).

**Secondary**

- IPC-2221B Table 6-1, from [EMA](https://www.ema-eda.com/ema-resources/blog/pcb-clearance-and-creepage-distance-table/).
- IEC 60664-1/62368-1 values, from [isolation-creepage](../../docs/topics/rules/isolation-creepage.md) (TI SLUP419).
- [chargers-bms](../../docs/topics/rules/power/chargers-bms.md).
- Phoenix part numbers from RS, Shortec and Automa listings.
- OMNI-BLOK, from a Farnell listing.
- Panduit, from a Digi-Key listing.
- LTC3300-1 efficiency, from [Electronic Specifier](https://www.electronicspecifier.com/industries/automotive/high-efficiency-bidirectional-multicell-active-balancer-maximizes/) [V].
- LFP OCV slope and cell resistance: typical cell data [S].
- NEC 240.4(D).
