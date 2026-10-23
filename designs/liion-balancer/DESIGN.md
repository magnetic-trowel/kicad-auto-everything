# liion-balancer: active cell balancer for a 13–16S home Li-ion pack (≈ 10 kWh)

Status: engineering design, encoded in [`design.py`](design.py) / [`parts.py`](parts.py) and built
with `kaesynth` (0 errors, 0 unwaived warnings, 24 waivers; KiCad ERC 0 errors; netlist round trip
identical). Independently reviewed (REVIEW.md: 0 blocker, 5 major, 8 minor — all addressed, see its
"Response to review"); not certified. Net table and naming rules: [CONNECTIONS.md](CONNECTIONS.md);
full pin list: `out/netlist.json`; checks, calculations and waivers: `out/report.md`.

Evidence tags: [P] primary source read, [S] secondary source, [V] vendor claim, [I] our inference.
IEC 60664-1, IEC 62368-1, IPC-2221B and UL 1973/9540 were not readable here; their values are [S].

## Summary

- **Topology.** One isolated flyback per cell (ADI LT8584, 1:4 transformer) moves ≈ 2.5 A out of a
  high cell into the whole stack. Unidirectional top-balancing, no bleed resistors.
- **Fault containment** ("no pathways for voltage to jump"). Every power part of channel k sits
  between taps k−1 and k; the stack return passes two diodes in series (D1kk, D1); a part that
  shorts one cell is cleared by that tap's board fuse in ≈ 5 ms.
- **Control.** ADBMS1818 measures every cell (≤ ±4 mV) and drives the LT8584 enables; an STM32G031
  runs the algorithm; a 2 s hardware watchdog and a second, independent enable path (opto string)
  stop a stuck channel. The pack BMS's OK signal is a third, MCU-independent enable, and two hardware
  trips stop every channel if an end tap (TAP0/TAP16) or the stack return opens.
- **Wiring.** N+1 = 17 wires, 18 AWG, ≤ 1 m: a 7 A 10 kA fuse at each ring, a pluggable 17-pole
  header, a replaceable 5 A fuse per tap on the board. 13–15S packs bridge the unused plug positions.
- **Coexistence.** Never switches the pack; ≤ 30 µA per cell worst case; isolated UART and a
  PhotoMOS fault contact for the BMS/host.
- **Size.** 407 electrical parts + 6 holes on one 270 × 130 mm 4-layer board; 35 harness items
  (17 rings, 17 inline fuses, 1 plug) modelled off-board.

## 1. Brief

Verbatim: "I want a battery balancer that can balance a string, series string of 12 volt lead acid
batteries. I want another one that can balance a series string of lithium ion batteries. This would
be in the 10 kilowatt hour range, so home packs. It should make sure that there's no pathways for
voltage to jump from places. I don't know if you want to do a flying capacitor or inductor or some
other elegant approach, but it needs to keep the charge balanced without bleed resistors. Ideally,
it would be as efficient as possible, as robust as possible, and allow us to have little wires that
go to the system ground and then all of the individual positive terminals."

This document designs the **lithium-ion** balancer; the lead-acid one is a separate design.

## 2. Requirements

| ID | Requirement | Value | Verified by |
|---|---|---|---|
| REQ-1 | One series string, 13–16 positions (a position may be a parallel group), ≈ 10 kWh | 13–16S | T-FUNC at 13S, 16S |
| REQ-2 | LFP 2.50–3.65 V or NMC 3.00–4.20 V per cell; stack in use ≤ 60.0 V (ES1 [S]); hardware rated to 67.2 V | ≤ 60 V | boot check (REQ-F7) |
| REQ-3 | No bleed resistors; energy returned to the stack | ≥ 72 % with 1 m harness, ≥ 78 % board | T-EFF |
| REQ-4 | Balancing current per discharged cell | ≥ 2.0 A (typ 2.5 A) | T-EFF |
| REQ-5 | Concurrency | ≤ 8 channels, NTC-derated | T-THERM |
| REQ-6 | Measurement with balancing muted | ≤ ±4 mV at 3.3 V | T-MEAS |
| REQ-7 | Wiring: B− cell terminal ("system ground") plus every cell positive | N+1 wires | inspection |
| REQ-8 | Tap fusing: battery end 7 A, ≥ 125 VDC, ≥ 10 kA; board 5 A very fast, 300 A at ≤ 32 VDC, replaceable | — | F-1…F-6 |
| REQ-9 | No single part fault joins non-adjacent taps with > 0.5 A; a one-cell short clears in ≤ 10 ms. T1kk interwinding insulation (1500 Vrms vs ≤ 67 V) is a safeguard; its residual is cleared by the inline fuses | ≤ 10 ms | FMEA §4, F-1…F-4 |
| REQ-10 | Every single-fault path has a fuse rated for its voltage and prospective current; multi-cell paths (double faults, T1kk insulation) are interrupted by the inline 3AB with the board fuse as series back-up | — | C-7, F-16 |
| REQ-11 | Spacing per §6.3 | B-1…B-6 | DRC, T-HIPOT |
| REQ-12 | Per-cell standing current, equal across cells | ≤ 30 µA worst case (sum of maxima), typ ≤ 3 µA; drift ≤ 0.15 %/yr | T-IQ |
| REQ-13 | Stack standing current | ≤ 50 µA sleep, ≤ 5 mA monitoring | T-IQ |
| REQ-14 | Swapped, reversed, offset or out-of-order taps: no fire, no cell damage; fuses open, self-test locks out | — | F-6, F-7 |
| REQ-15 | Open tap detected before each session; an open TAP0/TAP16 wire while balancing stops every channel in hardware | ≤ 1 ms | F-5 |
| REQ-16 | Stuck-on channel: two enables plus a hardware watchdog, plus the BMS-OK enable independent of the MCU | ≤ 2.2 s | F-8, F-17 |
| REQ-24 | Hardware inhibit without firmware: BMS OK dropped (BMS cell OV/UV), FLYBUS − TAP15 > ≈ 6 V, or TAP1 − TAP0 > ≈ 5.3 V | — | F-5, F-10, F-17 |
| REQ-17 | A cell at ≥ V_full − 20 mV is never net-charged by balancing | — | F-9 |
| REQ-18 | Coexist with the BMS: never switch the pack; expose data and a fault contact | — | review |
| REQ-19 | Isolated UART 115 200 8N1, host logic 2.25–5.5 V | — | T-FUNC |
| REQ-20 | Indoor, 0–45 °C, −20…60 °C storage, non-condensing, ≤ 2000 m, PD2 | — | T-THERM |
| REQ-21 | LT8584 T_J ≤ 105 °C; every part ≥ 20 °C below its rating at 45 °C with REQ-F3 derating | — | T-THERM |
| REQ-22 | Harness connector pluggable, polarized, ≥ 12 A, ≥ 300 V per pole | — | inspection |
| REQ-23 | Follow UL 1973 / UL 9540 / IEC 62619 BMS practice; no certification claim | — | review |

**Firmware-enforced** (the hardware relies on them; each has a firmware test in §10):
REQ-F1 kick the ADBMS1818 watchdog every ≤ 0.5 s; REQ-F2 active-set rule (H-5); REQ-F3 thermal
derating (8 channels < 60 °C, 4 < 70 °C, 0 ≥ 80 °C); REQ-F4 measure only with balancing muted, plus a
sum-of-cells plausibility check; REQ-F5 FLYBUS supervision by an ADC analog-watchdog window on PA0
(last stack + 4 V / − 5 V), a second layer behind the hardware trip; REQ-F6 pulse test and
proof of both enable paths before each session; REQ-F7 series count N checked at boot (cells N+1…16
< 50 mV, cells 1…N 2.5–4.2 V, else lock out); REQ-F8 discharge floor 3.0 V LFP / 3.4 V NMC, deep
sleep below 2.8 V; REQ-F9 PA2 low or high-Z while U5 side 1 is unpowered; REQ-F10 convert cells 1
and 16 unmuted every ≤ 50 ms while balancing and latch off after a hardware trip; REQ-F11 log time in
the balancing window.

## 3. Assumptions and open questions

**Assumptions.** ASM-1 reference pack 16S LFP 3.2 V 200 Ah (51.2 V, 10.24 kWh) [S]; 15S LFP and
13–14S NMC also exist, so N is configurable. ASM-2 the pack keeps its own BMS. ASM-3 M6 studs,
harness ≤ 1 m. ASM-4 a parallel group is one cell. ASM-5 the inverter may be transformerless, so the
battery may sit at mains potential: the user port is reinforced for 250 Vrms. ASM-6 UL 94 V-0 plastic
enclosure, PD2, natural convection. ASM-7 drift ≤ 0.25 %/day worst, ≈ 0.04 %/day typical [I].
ASM-8 pack-bus transients are absorbed by the cells [I]. ASM-9 firmware implements REQ-F1…F8.

**Questions** (the build reports the design as not ready for fabrication while blocking ones are open):

- **Q-1 (BLOCKING)** Confirm 13–16S at ≤ 60 V. Above 60 V leaves ES1; below 13S the 30 V transformer
  minimum is not met (NA6252-AL needed [P]). Default: as stated; hardware checked to 67.2 V.
- **Q-2 (BLOCKING)** Disable the BMS's own bleed balancing? Is CAN/RS-485 needed? Default: BMS untouched, UART only.
- **Q-3 (BLOCKING)** Is the battery isolated from mains by the inverter? If so the user barrier can
  be functional. Default: reinforced (safe either way).
- **Q-4 (BLOCKING)** Accept 18 AWG ≤ 1 m, M6 rings and an axial fuse sealed in heat-shrink? Who builds
  the harness? Default: CONNECTIONS.md §5.
- Q-5 window: LFP top-balance only (default). Q-6 fault contact closes on fault (default; zero
  standing current). Q-7 UART enough? Q-8 enclosure/coating owner. Q-9 add-on may affect a UL listing
  (owner/AHJ). Q-10 bidirectional LTC3300-1 version? (no). Q-11 qualify the pin-identical LTC6813-1
  against the ADBMS1818's 52-week lead time (yes).
- **Q-12 (BLOCKING)** Which pack-BMS signal drives the BMS-OK input J5? It must drop on any cell OV/UV
  or BMS fault. Default: the BMS's charge-enable dry contact switching the user's 12 V.
- Q-13 Does the charger reach ≥ 3.45 V/cell often enough? (many LFP floats sit at 3.35–3.375 V).
- **Q-14 (BLOCKING)** Multi-cell faults put 320–560 A through two board Nano2 fuses (50 A at 125 V);
  the inline 3AB (10 kA at 125 VDC) is the rated interrupter. Accept series back-up qualified by F-16,
  or fund a board fuse with a verified ≥ 80 VDC / ≥ 600 A rating? (Littelfuse 415 lists 1500 A at
  125 VDC but is time-lag and its datasheet could not be read.)

## 4. Hazards

"1F" = the mitigation still holds after one more independent fault. Parts are listed in `design.py`.

| ID | Hazard | Mitigation | 1F |
|---|---|---|---|
| H-1 | A part shorts one cell (LT8584 switch, cracked 1210 MLCC, TVS): ≈ 34 A | F1tt clears in 4.9 ms; inline fuse backs it up; 1210s ≥ 5 mm from edges/holes; MODE (pin 5, between GND pins 4 and 6) tied to VIN through R4kk 10 kΩ so a bridge draws 0.4 mA; 100 % AOI. A cracked C6kk or shorted D1kk collapses FLYBUS (≈ 5 W from the other channels); the REQ-F5 low window and the BMS-OK inhibit stop it, and a hung MCU at the same time is a double fault | yes |
| H-2 | Multi-cell short ("voltage jump") | By construction: D1kk short → D1 blocks; D1 short → every D1kk blocks; C6kk short → D1 blocks. Supplies via F1 125 mA + 100 Ω; LED string via R24 and a current sink; sense divider 10 MΩ; an ADBMS1818 internal short passes ≤ 0.3 A through two 100 Ω C filters or ≤ 6.7 mA through the 10 kΩ S-line resistors R5kk. **Residual:** T1kk interwinding breakdown joins TAPk to TAP0 (safeguard, sample hipot T-XFMR; up to 560 A, cleared by 10 kA inline fuses) | yes; double faults: inline 3AB with the board Nano2 as series back-up (Q-14) |
| H-3 | Harness short near the battery, ≤ 2.5 kA | 3AB 7 A fuse at the ring (10 kA at 125 VDC [P]); UL 1015 wire; bundled in tap order | yes |
| H-4 | Over-discharge by a stuck balancer (BMS cannot disconnect it) | Two enables (S_k → DIN; BAL_EN → opto → DCHRG), independent of hardware faults but not of firmware; watchdog clears DCC in ≤ 2.2 s; floors REQ-F8; **BMS OK (U8) in series with BAL_EN, so the BMS's own UV detection stops balancing**; LT8584 UVLO; proof tests each session; fault contact | yes; LT8584 internal logic fault is residual |
| H-5 | Returned energy overcharges a full cell (0.12–0.2 A per active channel into every cell) | REQ-F2: every cell ≥ V_full − 20 mV is discharged, so its net current −2.5 + n·0.15 A < 0 for n ≤ 8; the BMS's OV trip drops BMS OK and stops all channels in hardware | yes above the BMS OV threshold; firmware between V_full and it |
| H-6 | Wrong decisions from IR drop on single-wire taps | Muted measurement and plausibility (REQ-F4) | yes |
| H-7 | Hot-plug overvoltage | TVS D3kk per cell; 100 Ω / 10 nF filters and internal clamps; 2 × 100 µF per cell (C-10) | yes |
| H-8 | Swapped, reversed or offset taps | Pre-plug DMM check; TVS crowbar opens the board fuse; replaceable fuses; boot lockout | yes (no fire; repair) |
| H-9 | Open tap while balancing. Intermediate taps reach LT8584 UVLO first; an open TAP16/TAP0 wire leaves the 1.6 A return in D316/D301 (breakdown), lifting that cell to 6.4–7.1 V. The board nodes stay alive through the TVS, so the string alone does not stop anything | Pulse test (REQ-F6); hardware trips U9 (FLYBUS − TAP15 > ≈ 5.9 V) and U10 (TAP1 − TAP0 > ≈ 5.3 V) pull Q1_B low in < 100 µs; hiccup < 1 ms on / ≥ 20 ms off until firmware (REQ-F10) latches off or the 2.2 s watchdog stops a hung MCU (≤ 0.8 J in the TVS) | yes |
| H-15 | Open return (D1 lifted) with the MCU hung | U9 trips in hardware; D2 removed so nothing hides the LT8584's own open-output latch (≈ 183 V on FLYBUS, inside C6kk's 2.5× surge) as last layer | yes |
| H-10 | Shock through the user port (battery at mains potential) | ISO7721DWV and AQY210EH, reinforced 5 kVrms [P]; 8 mm (UART) / 5 mm (contact) board barrier; separate connectors | yes |
| H-11 | Overtemperature (8 × 1.5 W) | TH1–TH4, one per 4 channels (at U103, U107, U110, U114), and REQ-F3 | yes |
| H-12 | The balancer itself unbalances the pack | Controller loads hang on the whole stack; per-cell loads ≤ 30 µA | n/a |
| H-13 | Drains a pack the BMS has shut off | ≤ 50 µA sleep, buck UVLO 25 V, deep sleep < 2.8 V/cell | yes |
| H-14 | TAP0 landed on P− instead of B− | Label and procedure; cell 1 reads out of range → lockout; CH1 TVS and fuse limit damage | partial |

Standards context [S]: UL 1973 / IEC 62619 evaluate the battery's own BMS; UL 9540 the system;
NFPA 855 / IRC R328 the installation. This board is not a protective device.

## 5. Architecture trade study

Weights: fault containment 0.30, control on LFP 0.15, efficiency 0.10, robustness/diagnostics 0.15,
parts (active, boring) 0.15, complexity/cost 0.10, 13–16S on one BOM 0.05. Scores 1–5 [I].

| Option | Total |
|---|---|
| A. Adjacent-cell inductor buck-boost (MCU, 30 FETs) | 3.25 |
| B. Switched/flying capacitor | 2.45 |
| C. Multi-winding transformer | 2.20 |
| D. Switch matrix + one converter (EMB1428 + EMB1499Q) | 2.40 |
| E. ADI LTC3300-1 bidirectional flyback | 3.40 |
| **F. LT8584 per cell + ADBMS1818 + MCU** | **4.25** |
| G. AFE with bleed resistors | excluded by the brief |

- **B** moves current in proportion to ΔV, which is 1–5 mV across the LFP plateau, so almost nothing
  moves and hysteresis can move charge the wrong way; a cracked flying capacitor shorts a cell.
- **C** needs custom magnetics, fixes N and equalizes voltage (same LFP problem).
- **D**: one shorted matrix FET plus a normal selection joins non-adjacent taps at kA — the failure
  the brief forbids.
- **A**: 15 floating half-bridges; shoot-through shorts two cells; charge moves one hop at a time
  (15 hops at 93 % ≈ 34 %).
- **E** (runner-up, ≈ 90 % [V]): its synchronous secondary spans 12 cells, so one shorted FET puts
  ≈ 44 V across a winding with only a fuse to clear it, and a bidirectional path cannot use a
  blocking diode. Kept as the Q-10 fallback.

F costs: a low cell is fixed by discharging the other 15 (5 % low ≈ 8 h, ≈ 124 Wh once);
≈ 82 % converter / 75 % end-to-end efficiency; single-source LT8584; long ADBMS1818 lead time.

## 6. Blocks and domains

### 6.1 Blocks (one schematic sheet each)

| Block | Function |
|---|---|
| `harness` (off-board) | 17 × ring + 7 A inline fuse, plug HP1 |
| `tapin`, `tap0`…`tap16` | J1 header, net tie NT1; per tap: board fuse F1tt, 100 Ω / 10 nF C-pin filter |
| `ch1`…`ch16` | LT8584, T1kk, RCD clamp, TVS, CVCELL/CTRAN, output diode and cap, opto enable |
| `ret` | D1 stack-return diode, D2 FLYBUS clamp, FLYBUS divider to PA0 |
| `afe` | ADBMS1818 (SPI mode), VPLUS filter, NTCs |
| `psu` | F1 125 mA, D3, R9, LM5164 5 V buck, MCP1700 3.3 V |
| `mcu` | STM32G031K8, SWD pads, LEDs |
| `en` | BAL_EN current sink Q1 and the 16-LED opto string |
| `iso` | ISO7721DWV + ESD array → J2 (UART); AQY210EH + TVS → J4 (fault contact) |
| `mech` | 6 × M4 holes |

### 6.2 Voltage domains (as encoded)

Every net has a range relative to its domain's reference; the checker sums ranges down the chain, so
the stack is exact rather than interval-blown.

| Domain | Reference | Nets | Range |
|---|---|---|---|
| BAT0 (root) | TAP0 = B− | TAP0, TAP0_IN, GND_B (joined at NT1), CS_0 | 0 |
| C1…C16 | TAP(k−1) | TAPk, TAPk_IN, S_k, OUT_k, DCH_k | 0–4.2 V (0 for bridged positions) |
| SW1…SW16 | TAP(k−1) | SW_k, SNB_k (LT8584 switch and clamp nodes) | −0.7…38.5 V |
| SNS1…SNS15 | TAPk | CS_k, MODE_k (tap potential through ≥ 100 Ω) | ±10 mV |
| STACK | TAP16 | STK_F, VPLUS, BUCK_PRE/IN, STR_D, CS_16, MODE_16 | −2.5…0 V |
| RET | TAP0 | FLYBUS, SEC_k, BUCK_SW, STR_Q | FLYBUS 0–67.7 V; SEC −18…68.7 V |
| BOOT | BUCK_SW | BUCK_BST | 0–5 V |
| STR1…STR16 | LEDA_(k−1) / STR_Q | LEDA_k (opto string node) | 0–1.4 V |
| CTRL | GND_B | 5 V / 3.3 V logic | 0–5.15 V |
| USER (root) | GND_ISO | UART port | 0–5.5 V; floating, ≤ 250 Vrms to battery |
| FAULT (root) | FLT_B | fault contact | ±30 V |
| BMS (root) | BMS_N | BMS-OK input (J5) | ±30 V |
| CHASSIS (root) | — | screws, enclosure (no copper) | earth |

Net ranges are normal-operation worst cases at the 67.2 V hardware envelope (each position 0–4.2 V).
Single-fault stresses are calculations with limits (§7).

### 6.3 Barriers

FR-4 CTI ≥ 175 (material group IIIa), PD2. Creepage / clearance in mm.

| # | Pair | Grade | Working V | Spacing | Source |
|---|---|---|---|---|---|
| B-1 | adjacent positions (BAT0–C1 … C16–STACK) | functional | 4.2 (8.4 swap) | 0.2 / 0.2 | IPC-2221B B2 0–15 V: 0.1 [S] |
| B-1a | SW_k, SNB_k (domains SWk) to every other net | functional | 38.5 | 0.6 | B2 31–50 V: 0.6 [S] (barrier BAT0–SWk, inherited by all) |
| B-2 | every other pair inside the battery (positions ≥ 2 apart, CTRL, STACK) | functional | exact pair voltage | 0.2 up to 30 V, **0.6 above**; 1.0 preferred on open board | B2 [S]; emitted by kaesynth from the exact worst voltage of each domain pair |
| B-3 | T1kk primary ↔ secondary (RET ↔ cells); FLYBUS/SEC/BUCK_SW ↔ BAT0 | functional; part 1500 Vrms [P] | ≤ 106 pk | 0.6 (footprint gives 11.7) | B2 31–150 V [S] |
| B-4u | battery ↔ USER | **reinforced** | 250 Vrms | required 5.0 / 3.8; **design 8.0 / 8.0** | IEC 60664-1 F.4/F.2, IEC 62368-1 Table 10 via TI SLUP419 [S]; ISO7721DWV pads 8.85 apart |
| B-4f | battery ↔ FAULT | **reinforced** | 250 Vrms | **5.0 / 3.8** (required) | as B-4u; the AQY210EH SMDIP-4 pads are only 5.6 mm apart |
| B-5 | battery ↔ CHASSIS screws | basic | 250 Vrms | 3.0 ring (placement keepout); 3.0 to the board edge (DRC rule) | 2.5 / 1.5 [S] |
| B-4b | battery ↔ BMS | **reinforced** | 250 Vrms | 5.0 / 3.8 (required) | as B-4f; U8 AQY210EH pads 5.6 mm apart |
| B-6 | USER ↔ FAULT ↔ BMS | functional | ≤ 36 | 0.6 | B2 31–50 V [S]; separate connectors J2, J4, J5 |

Pads of one part that bridges two of these domains (LT8584, ADBMS1818, filters) are exempt from
each other in the DRC rules: the package sets that spacing, and package creepage is checked against
the barrier (ISO7721DWV 8.5 mm, AQY210EH pad gap 5.6 mm [I]). The rules were audited net pair by net
pair against IPC-2221B B2 for the exact worst voltage: none is below it.

## 7. Calculations

All values are recorded as `d.calc` in `design.py` with their limits; `out/report.md` lists them.

**C-1/C-3 Pack and envelope.** 16 × 3.2 V × 200 Ah = 10.24 kWh. Stack 32.5 V (13S LFP empty) to
67.2 V (16S NMC): inside the transformer's 30–80 V output range [P] and the ADBMS1818's V+ range; V+ −
C12 ≤ 16.8 V (≤ 40 V). One 200 Ah cell short-circuited ≈ 13 kA [S]. For N < 16, plug positions
N+1…17 are bridged; unused C inputs are "shorted to the highest connected cell" [P].

**C-2 Balancing current.** V_IN 3.15 V, I_pk 6.3 A, L_pri 4 µH, L_sec 64 µH: t_on 8.0 µs,
t_off 1.71 µs, f ≈ 97 kHz, I_in = ½·I_pk·t_on·f = 2.45 A (Fig. G32: 2.4–2.6 A [P]); I_pri,rms 3.2 A.
Capacity 2 h/day × 2.5 A = 2.5 %/day of 200 Ah, 10× typical drift.

**C-4 LFP policy.** In the plateau (slope 0.5–1 mV/%, 20–30 mV hysteresis [S]) cells are
unobservable, so no balancing. Above ≈ 95 % SOC the slope is ≥ 20 mV/%. Start at V_max ≥ 3.45 V and
ΔV ≥ 20 mV; discharge cells ≥ V_min + 10 mV, at most 8; stop at ΔV ≤ 5 mV or V_max < 3.40 V. NMC: at
rest, V ≥ 3.9 V, ΔV ≥ 15 mV.

**C-5 LT8584 stresses** (V_IN ≤ 4.2 V, FLYBUS ≤ 67.7 V). SW flat top 4.2 + 68.7/4 = 21.4 V (≤ 40 VDC
rule [P]); leakage spike clamped at 38.5 V vs 50 V abs max (77 %). I_pk 6.8 A vs transformer 7.0 A
(97 %): ADI's own pairing [P], accepted and checked for saturation in T-EFF.

**C-6 RCD clamp.** ½ × 0.116 µH × 6.3² × 97 kHz = 0.22 W; V_c = √(0.22 × 4.99 kΩ) = 33 V above V_IN
(> 17.2 V reflected). R1kk 0.22 W of 0.5 W used (46 %).

**C-7 Fuses.** Per-tap path ≈ 60 mΩ (wire 22.6, 0324007 18.7 [P], 0451005 12.5 [P], contacts 6).

| Fault | Prospective | Clears | Rating |
|---|---|---|---|
| One cell on board | 4.2 / 0.125 = 34 A | F1tt I²t 5.566 → 4.9 ms; inline 71 A²s, so selective (12.8×) | Nano2 300 A at 32 VDC [P] |
| Two cells (swap) | 67 A | 1.2 ms | ok |
| Stack (two faults or T1kk insulation) | 67.2 / 0.12 = 560 A | Nano2 melts first (5.6 vs 71 A²s), 3AB interrupts | 3AB 10 kA at 125 VDC [P]; Nano2 only 50 A at 125 V: **series back-up, F-16, Q-14** |
| Reversed harness / ring 0 on B+ (two installer errors: landing + skipped pre-plug check) | ≈ 320–390 A (via secondaries + D1kk + D1, or D301) | as above | as above |
| Wire to wire / chassis at the battery | 1.35–2.5 kA | inline | ok |

Tap current ≤ 2.6 A: board fuse 2.6 / (5 × 0.75 × 0.9) = 77 %; inline 50 %. F1 (125 mA) sees a buck or
V+ short at 0.66 A (5.3×) and opens in milliseconds; R9 absorbs ≈ 0.3 J.

**C-8 Efficiency** (1 m, 120 mΩ loop, 2.5 A, 3.45 V cell). Harness 0.75 W; (8.63 − 0.75) × 0.82 =
6.46 W out: **75 % end to end**, 82 % board only.

**C-9 Standing currents.** Per cell: LT8584 1 + SW leakage 4 + C pin 0.25 + TVS 20 (rated at 5 V)
+ opto 0.08 = **25.3 µA worst case** (typ ≈ 2 µA): 0.11 %/yr of 200 Ah. Stack in sleep: LM5164 25 +
UVLO 6.3 + V+ 9 + reflected 1.4 + D1 reverse leakage into the FLYBUS divider (≤ 67.2 V/10.47 MΩ =
6.4 µA) = 48.1 µA max (≈ 27 µA typ). The V8P10's leakage (14.5 µA typ, 70 µA max at 100 V) through the
old 2.1 MΩ divider could have reached 32 µA, so both dividers were raised to ≈ 10 MΩ. The bottom trip
chain is switched off with BAL_EN; the top one adds ≤ 1 µA [I] to cell 16.

**C-10 Hot plug.** L ≈ 2 µH, R 0.12 Ω, ≈ 80 µF effective (X6S 6.3 V at 4.2 V [I]): ζ = 0.38,
peak 5.4 V — below the 6.3 V capacitor rating and the 9 V LT8584 limit; D3kk clamps above ≈ 7 V.
An open TAP16 (TAP0) wire while balancing pushes the returned current through D316 (D301): the cell
reads ≤ 7.1 V (VBR max 7.07 V at 1 mA, 9.1 V at 68 A [P]) until U9 (U10) trips, < 100 µs per hiccup.

**C-10a Hardware trips.** Top chain FLYBUS → ES1G → BZX84-B3V9 → 220 Ω → TLP293 LED (10 kΩ shunt) →
TAP15; onset 5.4–6.4 V with tolerances, against 4.75 V normal maximum (cell 4.2 + D1 0.45 + wire 0.1)
and ≥ 6.8 V in the fault (D316 6.46 V at 1.6 A + D1 0.35). Bottom chain TAP1 → BZX84-B3V9 → 220 Ω →
LED → Q2 (on only with BAL_EN) → GND_B; onset 4.9–5.8 V against 4.4 V normal and ≥ 6.46 V fault. Each
opto sinks ≥ 0.33 mA (R21) at 1.1 mA LED current (CTR(sat) 30 %), pulling Q1_B low. Open return: FLYBUS
peaks ≤ TAP15 + 16 V (≤ 79 V) before the channels stop; if U9 failed, each LT8584 latches off at
FLYBUS ≈ 4 × (50 − 4.2) = 183 V, inside C6kk's 2.5× surge.

**C-11 Timing.** DTEN = V−: the watchdog clears DCC after 1.8–2.2 s [P]; the MCU talks every ≤ 0.5 s.
Measurement: MUTE → ADCV → UNMUTE every 5 s. Open wire: ADOW's 100 µA sources only work up to
10 nF [P] and each node carries ≈ 200 µF, so each session starts with a 5 ms pulse per channel (healthy
tap drops 0.3 V; an open one collapses at 6 V/ms), which also proves both enables. Open end taps and
an open return are stopped in hardware (C-10a); REQ-F5/F10 are the firmware layer.

**C-12 Thermal.** Per channel ≈ 1.5 W (LT8584 0.55, transformer 0.5, D1kk 0.13, fuses 0.08) plus
D1 0.7 W. LT8584 T_J = 70 + 0.55 × 38 = 91 °C (650 mm² copper [P]). D1 T_J = 70 + 0.72 × 60 = 113 °C
(≤ 130). Eight channels ≈ 12 W → ≈ 72 °C board at 45 °C ambient uncontrolled, hence REQ-F3. Margins
under REQ-F3: CTRAN/CVCELL 105 °C X6S at ≤ 85 °C local = 20 °C; ADBMS1818 (85 °C) ≤ 65 °C = 20 °C;
AQY210EH and STM32 (85 °C) ≤ 60 °C = 25 °C (east zone, away from channels 8/9).

**C-13 Buck (LM5164).** R12 49.9 kΩ → 250 kHz; t_on at 67.2 V = 298 ns (> 50 ns). L1 47 µH: ripple
0.39 A, peak 0.26 A vs I_sat 1.44 A. C11 22 µF (≈ 14 µF at 5 V [I]). R13/R14 316 k/100 k → 4.99 V.
Type-3 ripple injection R15 470 kΩ, C12 1 nF, C13 220 pF. UVLO R10/R11 10 M/620 k → on at 25.7 V.
BST cap 2.2 nF 50 V X7R as required [P]. VPLUS drop 0.14 V (≥ −0.3 V limit [P]). MCP1700 43 mW.

**C-14 BAL_EN string.** Q1 sink (3.3 − 0.65 − 0.2)/1.6 kΩ = 1.5 mA; compliance at 32.5 V stack:
32.5 − 0.9 − 7.2 − 16 × 1.15 − 0.3 − 2.4 = 3.3 V. TLP293 CTR ≥ 30 % gives 0.46 mA vs 0.13 mA needed
(3.6×). Off: dark current 5 µA × 33 kΩ = 0.17 V < 0.5 V threshold. Q1 C–E short: 6.2 mA; R24
0.18 W (36 %).

**C-15 FLYBUS.** C6kk 2.2 µF 100 V (≈ 1 µF each at 60 V [I]) × 16 ≥ 1.5 µF needed [P]. Normal 68 % of
rating. D1kk sees 67.7 + 16.8 + 1 = 85 V of 400 V; D1 67 V of 100 V. The former SMBJ70A clamp (D2) is
removed: it clamped FLYBUS at
86 + 27 × 1.6/5.3 = **94 V** (C6kk and D1 still < 100 V). At 1.6 A that is 150 W: **a 10 ms software
loop would put 1.5 J into an SMBJ rated ≈ 0.87 J (600 W, 10/1000 µs)**, so REQ-F5 uses the analog
watchdog — and it hid the LT8584's own latch, so a hung MCU left ≈ 300 J for D2 (review M-2). FLY_SNS =
67.7 V × 470 k/10.47 MΩ = 3.10 V worst case (≤ VDD).

**C-17 New interfaces.** S-line resistors R5kk 10 kΩ: a monitor fault is limited to 67.2 V/10 kΩ =
6.7 mA; DIN's ≤ 6 µA pull-up drops ≤ 60 mV. BMS-OK input: (9 − 0.9 − 1.5)/1.8 kΩ − 0.15 mA = 3.5 mA ≥
AQY210EH IFon max 3.0 mA at 9 V; 15.5 mA and 0.43 W in R34 (2512, 1 W) at 30 V; reversed input blocked
by D11, transients by D12 (SMBJ40CA).

**C-16 NTCs.** 10 kΩ B 3434 K [P] with 10.0 kΩ 0.1 % from VREF2 = 3.000 V: 1.50 V at 25 °C, 0.54 V
at 70 °C, 0.38 V at 85 °C.

## 8. Parts

Stress is the worst case in this design; ratings, sources and lifecycle are in `parts.py`.

| Role (refdes) | Part | Key rating | Stress | Notes |
|---|---|---|---|---|
| Balancer U101–U116 | ADI LT8584EFE#PBF | V_IN 9 V abs; SW 50 V (40 VDC) | 47 %; 77 % | generated symbol; TSSOP-16 EP; single source |
| Transformer T101–T116 | Coilcraft NA5743-ALD | 1:4, I_pk 7 A, 1500 Vrms | 97 % (waived, ADI pairing) | footprint drawn from Doc 1075 (`footprints/custom.pretty`) |
| Diodes D1kk, D2kk, D3, D4 | Diodes ES1G-13-F | 400 V, 1 A | ≤ 22 % | |
| Cell TVS D301–D316 | ST SMA6T6V7AY | V_RM 5 V | 84 % (stand-off is a working rating) | ADI Table 5 [P] |
| CVCELL/CTRAN C1kk, C2kk | **Murata GRM32EC80J107ME20L**, 100 µF 6.3 V **X6S** | 105 °C | 67 % | was 10 V X5R (85 °C): failed the REQ-21 margin |
| C3kk / C4kk / C5kk | 1 µF 10 V / 47 nF 50 V / 22 nF 100 V X7R | | ≤ 42 % | |
| C6kk, C8 | KEMET C1210C225K1RACTU 2.2 µF 100 V | | 68 % | GRM32ER72A225KA35L is NRND |
| R1kk / R2kk / R4kk | 4.99 k 2010 / 33 k / 10 k | 0.5 W used | 46 % | |
| Opto U201–U216 | Toshiba TLP293(GB-TPL,E | 80 V, 3750 Vrms, VR 5 V | ≤ 60 % | |
| Board fuse F100–F116 | Littelfuse 0154005.DR (OMNI-BLOK + 451 5 A) | 300 A at 32 VDC | 77 % derated | replaceable |
| Inline fuse HF0–HF16 | Littelfuse 0324007.HXP 3AB 7 A | 10 kA at 125 VDC | 50 % | off-board, in heat-shrink |
| Supply fuse F1 | Littelfuse 0451.125MRL | 125 mA | 8 % | |
| Monitor U1 | ADI ADBMS1818ASWZ | V+ 112.5 V abs; Cn−Cn−1 8 V | 60 %; 53 % | 2-unit generated symbol; LTC6813-1 second source |
| MCU U2 | ST STM32G031K8T6 | VDD 4.0 V abs, 3.6 V operating | 3.37 V, within operating | |
| Buck U3 / L1 | TI LM5164DDAR / Coilcraft MSS1048-473 | 100 V / I_sat 1.44 A | 67 % / 18 % | |
| LDO U4 | Microchip MCP1700T-3302E/TT | 6.5 V abs | 79 % | |
| Isolator U5 | TI ISO7721DWVR | reinforced 5 kVrms, 8.5 mm, V_IOWM 1500 Vrms | logic | |
| ESD U7 (new) | TI TPD4E05U06DQAR | ±12 kV contact, V_RWM 5.5 V | 5.5 V = V_RWM | on VIO/TXD/RXD at J2 |
| Fault contact U6 | Panasonic AQY210EHAX | reinforced 5 kVrms; 350 V; LED VR 3 V | 9 %; 50 % | |
| Contact TVS D7 (new) | Littelfuse SMBJ40CA | V_R 40 V | 75 % | across J4 |
| Return D1 | Vishay V8P10 | 100 V 8 A | 68 % | D2 (SMBJ70A clamp) removed (review M-2) |
| S-line resistors R501–R516 (new) | 10 kΩ 0603 | | < 1 % | at the U1 S pins (review M-3) |
| BMS-OK U8, J5, R34, D11, D12, R35 (new) | AQY210EHAX, MC 1,5/2, 1.8 kΩ 2512, ES1G, SMBJ40CA, 10 kΩ | reinforced 5 kVrms | 43 % (R34) | enable independent of the MCU (review M-5) |
| Trips U9, U10, D8, D9, D10, Q2, R30–R33, R36, R37 (new) | TLP293, ES1G, Nexperia BZX84-B3V9, MMBT5551 | | ≤ 60 % | hardware open-tap / open-return stop (review M-1/M-2) |
| TH4, R29, C22 (new) | as TH1–TH3 | | | fourth NTC (review minor 6) |
| Q1 | onsemi MMBT5551LT1G | 160 V | 42 % | |
| R25, R26 | **1 kΩ** (was 100 Ω) | 0.1 W | 30 % | a host driving TXD back put 0.3 W in 100 Ω |
| C2, C14 | **1 µF 16 V** GRM188R71C105KA12D (was 10 V) | | 32 % | 5 V rail, DC bias |
| J1 / HP1 | Phoenix MSTBA 2,5/17-G-5,08 (1757394) / MSTB 2,5/17-ST (1757161) | 12 A, 320 V | 21 % | 17-pos footprint drawn from KiCad's 16-pos |
| J2 / J4 (split) | Phoenix MC 1,5/4-G-3,81 / MC 1,5/2-G-3,81 [I numbers] | 8 A, 160 V | | UART and contact on separate plugs |
| Rings HT0–HT16 | Panduit PV18-14R-MY | ¼" stud | | off-board |
| Passives, LEDs, test pads | Yageo RC 1 %, Murata X7R/C0G, Lite-On LTST-C191 | | R ≤ 50 % P | |

## 9. Placement and mechanical constraints

Board 270 × 130 mm, 4 layers, 1.6 mm FR-4 (CTI ≥ 175): L1/L4 2 oz; L2 per-channel reference islands;
L3 2 oz tap corridors (taps drawn 1.5 mm). Top-side assembly, tallest part T1kk 11.4 mm. Six M4
NPTH on nylon standoffs with a 3.0 mm copper keepout (B-5). V-0 enclosure next to the cells.

**Floorplan.** West: J1 on the edge, the fuse column in tap order, C-pin filters, U1 (kept away from
the transformers). South row CH01→CH08 and north row CH16→CH09, both west to east, mirrored about a
central spine that carries FLYBUS, TAP0, the LED string, D1 (at F116) and the NTCs. The U-shape keeps
neighbouring channels one cell apart; CH08/CH09 meet on TAP8 in the east. East: PSU, MCU and ISO
(J2, J4 on the east edge), kept away from channels 8/9 for the 85 °C parts.

All 541 relations are in `placement()` of `design.py` (and `out/intent.yaml`): groups and regions per
block; arrays and mirror symmetry of the channels; `pins_toward` for each transformer (primary to the
cell's own copper, secondary to the spine); three hot loops per channel (primary, secondary, RCD) and
the buck loop; tight decoupling; thermal relations for U1kk (≥ 650 mm² TAP(k−1), ≥ 9 vias) and D1
(≥ 400 mm² tab); keepouts in the transformer and isolator pad gaps; one `separate` per barrier.
Relations outside the vocabulary are `custom`:

- `pin_order(J1, y, pin1 south)`: taps enter in potential order.
- `kelvin(R3tt.1 at F1tt.2)`: sense trace leaves the fuse pad on its own.
- `net_tie(NT1, TAP0–GND_B at F100.2)`: the only battery-return/controller-ground joint.
- `island(TAP(k−1), In1, under ch k)`: a reference plane per channel at its own potential.
- `corridor([TAP0…8, S_1…8], south, In2, by index)` and the north equivalent: neighbours differ by one cell.
- `current(TAPt 2.6 A, FLYBUS 1.6 A)`; `straddle(U5 CTRL|USER)`, `straddle(U6 CTRL|FAULT)`;
  `keepout_mlcc` (1210s ≥ 5 mm from edges and holes); labels.

**Installation.** J1 pin p carries TAP(p−1); pin 1 is the B− cell terminal, never P−. For N < 16
bridge plug positions N+1…17 and set N in firmware. Mount with the plug off, land rings from B−
upward, check every adjacent pair at the plug (2.5–4.2 V, rising) and the sum, then plug in.

## 10. Verification plan

**Build checks** (`kaesynth build`): voltage/current/power ratings at the 67.2 V envelope, isolation
and barrier grades, provenance, protection, calculations, KiCad ERC, netlist round trip, DRU lint.
IC rail pins carry their datasheet recommended operating maximum (`v_rec`). Waived findings, each
with its reason in `design.py`: transformer peak current 6.8 of 7.0 A (16), LM5164 BST–SW set by its
internal 5 V regulator (1), the host-powered VIO_ISO without a fuse (1), and ERC pin-to-pin on the
PWR_FLAGs the emitter adds to GND_B and ISO_VCC1 (6).

**Simulation.** S-1 DRC with the generated rules. S-2 LTspice LT8584 channel: V_IN 2.5–4.2 V,
FLYBUS 32.5–67.7 V with harness R/L; faults open FLYBUS, shorted D1kk, shorted C6kk. S-3 buck
stability 25–67 V input, 0–60 mA steps.

| Test | Method | Pass |
|---|---|---|
| T-FUNC | 16S and 13S LFP packs; configuration, telemetry, fault contact | all functions |
| T-EFF | ring-side power vs return; 0.5/1 m harness; 25/45 °C; SW current probe | REQ-3/4; no saturation knee |
| T-MEAS | balancing on vs muted against a 6½-digit DMM | ≤ ±4 mV muted |
| T-BAL | 16S 200 Ah: one cell +5 %, one −5 %, random ±2 % | ≤ 6 h / 10 h / 4 h of top-window time |
| T-IQ | µA meter in every tap; sleep/active; 25/45 °C | REQ-12/13 |
| T-THERM | 8 channels in a 45 °C chamber; IR camera | REQ-21; derating steps |
| T-HIPOT | J2/J4 vs battery side ≈ 3 kVrms 60 s [S]; battery vs chassis 1.5 kV | no breakdown |
| T-EMC | conducted emissions on the harness; ESD ±8 kV contact on J2/J4, ±4 kV on J1 | no reset or damage |
| T-XFMR | incoming sample hipot of T1kk at 1.5 kVrms, 60 s | no breakdown |
| T-AOI | 100 % AOI/X-ray of U1kk pins 4–7 and EP | no bridges |

**Fault injection** (fire-safe box, Rogowski probe): F-1 short C1kk / U1kk SW–GND / D3kk (k = 1, 8,
16): fuse ≤ 10 ms, no flame. F-2 short D1kk: switch-error latch, no TAP16→TAP0 current. F-3 short
D1, then D1 + D1kk: none / fuses clear. F-4 short C6kk: D1 blocks; low-side window trips. F-5 open
TAP0/1/8/15/16 idle and balancing: detected before start; U9/U10 stop TAP0/TAP16 in < 1 ms; TVS energy
≤ 1 J with the MCU halted. F-6 swap k/k+1, k/k+2, reversed harness, plug offset
one pin: no fire, lockout. F-7 200 rocked plug cycles: ≤ 9 V per LT8584, ≤ 8 V per C pair. F-8 S_k low
with BAL_EN off; Q1 shorted with DCC off; MCU halted; string open; DIN bridged to pin 6: no discharge
or stop ≤ 2.2 s. F-9 a full cell during balancing: net current < 0. **F-10 lift D1 while balancing, with the MCU halted:
U9 stops all channels, FLYBUS ≤ 80 V.** F-11 short U3 V_IN and ADBMS1818 V+: F1 clears. F-12
muting quantified. F-13 NTC open/short, blocked airflow. F-14 TAP0 on P− then BMS opens: lockout.
F-15 30 days idle on 16S: no drift beyond C-9.
**F-16 series back-up:** 560 A at 67 V through a Nano2 0451005 in OMNI-BLOK in series with a 0324007,
then the reversed-harness and ring-0-on-B+ cases: no rupture or sustained arc (Q-14). **F-17** BMS-OK
input dropped while balancing with the MCU still commanding: all channels stop. F-7 also mates pin 1
last (buck inrush returns through D301, ≈ −0.9 V on U101 VIN for 0.2 ms; review minor 3). T-EFF is
repeated with the transformer core at ≥ 100 °C (minor 7).

## 11. Sources

**Primary (read).** ADI LT8584 Rev B (pins p.2/p.9, abs max p.2, Tables 3 and 5, Figs. 2–3,
G32/G33, layout p.28) via an [rlocman mirror](https://www.rlocman.ru/i/File/2017/10/23/8584fb.pdf);
ADI ADBMS1818 Rev A (Table 11 abs max p.11, Fig. 3 / Table 14 pp.12–13, Fig. 113) via
[LCSC C2971928](https://www.lcsc.com/product-detail/C2971928.html); LTC6813-1 Rev B (pp. 3, 7, 45,
70–75, 85) via [LCSC C2758259](https://www.lcsc.com/product-detail/C2758259.html); Coilcraft
[NA5743 Doc 1075](https://www.coilcraft.com/pdfs/na5743.pdf) and
[MSS1048 Doc 462](https://www.coilcraft.com/pdfs/mss1048.pdf); TI
[LM5164 SNVSAU4D](https://www.ti.com/lit/ds/symlink/lm5164.pdf),
[ISO7721 SLLSEP3G](https://www.ti.com/lit/ds/symlink/iso7721.pdf),
[TPD4E05U06 SLVSBO7O](https://www.ti.com/lit/ds/symlink/tpd4e05u06.pdf); ST STM32G031 DS12992 via
[LCSC C432203](https://www.lcsc.com/product-detail/C432203.html); Microchip
[MCP1700](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP1700-Low-Quiescent-Current-LDO-20001826E.pdf);
Vishay [V8P10](https://www.vishay.com/docs/89005/v8p10.pdf); Littelfuse 314/324
([chipdip copy](https://static.chipdip.ru/lib/536/DOC021536932.pdf)), 451/453, SMBJ; Toshiba TLP293;
Diodes ES1x; onsemi MMBT5551; Panasonic AQY21xEH; Murata NTC (all via LCSC product pages);
Digi-Key lifecycle searches, Oct 2026.

**Secondary.** IPC-2221B Table 6-1 via [EMA](https://www.ema-eda.com/ema-resources/blog/pcb-clearance-and-creepage-distance-table/);
IEC 60664-1 / 62368-1 values via [isolation-creepage](../../docs/topics/rules/isolation-creepage.md)
(TI SLUP419); [chargers-bms](../../docs/topics/rules/power/chargers-bms.md); Phoenix, Panduit and
OMNI-BLOK data from distributor listings (phoenixcontact.com returned 403); Murata
GRM32EC80J107ME20L from a Future Electronics listing; LTC3300-1 efficiency from
[Electronic Specifier](https://www.electronicspecifier.com/industries/automotive/high-efficiency-bidirectional-multicell-active-balancer-maximizes/) [V];
LFP OCV slope and cell resistance: typical cell data [S]; NEC 240.4(D).
