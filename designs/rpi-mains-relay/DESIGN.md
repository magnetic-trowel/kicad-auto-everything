# rpi-mains-relay: 4-channel 120 VAC relay board for a Raspberry Pi, in a 4-11/16" box

Status: engineering design, encoded in [design.py](design.py) and [parts.py](parts.py). Not reviewed by a certification body.

`kaesynth build` result: 0 errors, 0 warnings, 25 waived findings (8 waiver rules, each with its reason
in [out/report.md](out/report.md)). KiCad ERC is clean and the netlist round trip is identical. Six
BLOCKING questions remain open, so the design is not ready for fabrication.

Encoding changed one value: the watchdog hold network went from R14 100 kΩ / C4 1 µF to
1 MΩ / 100 nF (see C-4).
The netlist is in [CONNECTIONS.md](CONNECTIONS.md). Evidence tags: [P] read in the primary
source, [S] secondary or snippet, [V] vendor claim, [I] our inference. Where a standard was not
readable (NEC, UL 508, UL 1059, IEC 60664-1, IEC 62368-1), values come through cited secondary
sources and are tagged so. Verify them against the adopted editions before fabrication.

**Design summary.**

- **Mounting.** A 106 × 80 mm two-layer board sits on nylon supports in a listed steel 4-11/16" box, 2-1/8" deep, with a 1-1/2" extension ring and a blank cover.
- **Switching.** Four G5RL-1A-E-TV8 relays (Omron, now Aratas) switch the line of four outputs. They are rated 16 A, TV-8 and 1/2 hp, with reinforced 8/8 mm coil-to-contact insulation.
- **Terminals.** WAGO 2606 lever terminals take the shared L/N input and an (L_SW, N) pair per output. Grounds are spliced in the box and never pass through the PCB.
- **Pi link.** The Pi stays outside the box. One Class 2 cable carries its 5 V, which powers the coils, plus 4 GPIO lines and a heartbeat.
- **Fail-safe.** A charge-pump watchdog in series with every coil keeps all outputs OFF unless the heartbeat toggles. The only parts crossing the barrier are the four certified relays.

## 1. Brief

"I want you to make a breakout board for a Raspberry Pi that has the ability to switch 120 volts. Maybe 4 or 6 of them. It should use stuff that is reliable. It should have terminals that make it really easy to access. Maybe all with shared inputs and then a whole bunch of outputs or something like that. Kind of like the outlets. It should probably be mounted into an outlet type box."

## 2. Requirements

| ID | Requirement | Value + units | Source | Verified by |
|---|---|---|---|---|
| REQ-1 | Supply | 120 VAC nominal (108–132 V), 60 Hz, 1-phase, L + N + EGC; single 2-wire branch, not a multiwire branch circuit | brief; ASM-1 | inspection, T-FUNC |
| REQ-2 | Branch overcurrent device (OCPD) | ≤ 15 A; Cu conductors 14 AWG minimum, 12 AWG allowed | derived; NEC 240.4(D) [I] | label, install check |
| REQ-3 | Channels | 4 independently controlled outputs | brief ("4 or 6"); box size (C-1) | T-FUNC |
| REQ-4 | What is switched | Line only. Neutral is not switched. The EGC never passes through the PCB | NEC 404.2(B) [I], 250.148(B) [S] | netlist review |
| REQ-5 | Rating per output | ≤ 15 A general use, ≤ 12 A continuous; motor ≤ 1/2 hp at 120 V (9.8 A FLA); tungsten ≤ TV-8; capacitive inrush ≤ 100 A peak | relay UL/VDE ratings [P] | T-LOAD, T-OL |
| REQ-6 | Total current | ≤ 15 A (sum of outputs; set by the branch OCPD) | derived | T-HEAT |
| REQ-7 | Enclosure | Listed steel 4-11/16" square box, 2-1/8" deep, + 1-1/2" extension ring + flat blank cover; surface-mounted indoors | brief ("outlet type box"); C-1, C-6 | inspection |
| REQ-8 | Box fill | Displaced volume + NEC allowances ≤ 71.5 in³ | NEC 314.16 [S/I] | C-1 |
| REQ-9 | Field terminals | Lever push-in, UL 1059 ≥ 300 V / ≥ 20 A, 14–12 AWG Cu solid or stranded; one (L, N) input and four (L_SW, N) outputs, all labelled | brief ("really easy to access", "shared inputs … outputs") | inspection |
| REQ-10 | Mains ↔ SELV insulation | Reinforced. PCB creepage ≥ 8.0 mm and clearance ≥ 8.0 mm; relay coil–contact reinforced | UL/IEC 62368-1, IEC 60664-1 (C-8) | T-CREEP, T-HIPOT |
| REQ-11 | Opposite-polarity mains spacing (L or L_SWk to N; L_SWj to L_SWk) | creepage ≥ 6.4 mm, clearance ≥ 3.2 mm | UL 1059 use group C [S] | T-CREEP |
| REQ-12 | Mains ↔ PE | ≥ 6.4 mm from mains copper to box metal (walls, bottom, ground screw); ≥ 2.0 mm from mains copper to any board edge (basic insulation against a stray bare EGC) | UL field-wiring practice [S]; 62368-1 basic [P/I] | T-CREEP, T-HIPOT |
| REQ-13 | Fail-safe OFF | All outputs OFF when the Pi is unplugged, unpowered, booting, rebooting or halted; when any CH line floats; and within ≤ 0.5 s of the heartbeat stopping | brief ("reliable"); task | T-BOOT, T-FLOAT, T-HB |
| REQ-14 | Two-fault rule | No single stuck GPIO and no single shorted driver energizes an output while the heartbeat is absent | derived | FMEA (§4), T-HB |
| REQ-15 | Load on the Pi | GPIO ≤ 0.6 mA DC per CH pin and ≤ 3.3 mA peak on HB; only default-pull-down GPIOs used; 5 V ≤ 0.40 A | Pi docs [P] | T-PWR |
| REQ-16 | Heartbeat (HB) | 3.3 V square wave, 100 Hz–2 kHz, 40–60 % duty, arms the outputs; DC or no signal disarms them | derived (C-4) | T-HB |
| REQ-17 | Coil voltage | ≥ 4.5 V at the relay pins in the worst case | must-operate voltage [P]; C-3 | T-COIL |
| REQ-18 | Leakage at an OFF output | ≤ 0.1 mA (no snubber or MOV across the contacts) | derived (C-12) | T-LEAK |
| REQ-19 | Thermal | Every part within its derated limit at 40 °C room temperature, box surface-mounted, 12 A continuous plus all 4 coils on | derived (C-6) | T-HEAT |
| REQ-20 | Fault withstand | PCB mains copper survives the let-through of a 15 A breaker at ≤ 2 kA prospective fault current | derived (C-7) | T-SC |
| REQ-21 | Indicators | LED per channel (coil energized), ARM LED, 5 V LED; all on the SELV side | task | T-FUNC |
| REQ-22 | Environment | Indoor, dry, PD2, OVC II, ≤ 2000 m, 0–40 °C room | ASM-2 | — |
| REQ-23 | Parts | Active and orderable; UL-recognized relays, terminals, PTC and PCB laminate | brief ("reliable") | BOM review |
| REQ-24 | Installation | Licensed electrician; approval by the authority having jurisdiction (AHJ) | NEC 110.2/110.3 [I] | Q-1 |
| REQ-25 | Markings | Ratings, conductor size and strip length, warnings, "Class 2 only" at the SELV terminal | UL practice [I] | inspection |
| REQ-26 | SELV link | 8-conductor Class 2 cable: 22 AWG up to 3 m, or 24 AWG up to 2 m. Enters through its own knockout; kept apart from mains by a barrier | NEC 725.136(B)/(D) [S]; C-3 | inspection |

## 3. Assumptions and open questions

| ID | Assumption | Why |
|---|---|---|
| ASM-1 | North-American dwelling or light commercial; one 120 V branch from a ≤ 15 A breaker; prospective fault current at the box ≤ 2 kA | Typical; ≥ 10 m of 14 AWG limits faults to < 1 kA (C-7) |
| ASM-2 | Indoor dry location, PD2, OVC II, altitude ≤ 2000 m, room 0–40 °C; box surface-mounted (garage or utility wall) | The spacing tables and the thermal budget depend on these |
| ASM-3 | Loads are plug-in appliances, LED or tungsten lighting, small motors. None of them is hazardous if left on (a welded relay is a credible failure) | Section 4, H7 |
| ASM-4 | Raspberry Pi 4 or 5 on its official 5.1 V supply, in its own case outside the box, ≤ 3 m away | Pi outside the box (section 5) |
| ASM-5 | PCB laminate CTI ≥ 100 V (material group IIIb), so the tables are applied at their most conservative | FR-4 is usually IIIa [S] |
| ASM-6 | Control software toggles HB at ≥ 100 Hz from its main loop while any output should be on | Watchdog semantics (C-4) |
| ASM-7 | Outputs drop to OFF on every Pi reboot; no state is retained | Required by REQ-13 |

| ID | Question for a human | Blocking? |
|---|---|---|
| Q-1 | Certification path. Permanent building installation of this unlisted assembly needs AHJ approval, probably a field evaluation. Who evaluates it and who installs it (licensed electrician)? If neither is acceptable, buy listed products (alternative A5). | **BLOCKING** |
| Q-2 | Confirm 4 channels. 6 channels do not fit a 4-11/16" box (C-1) and would need a 6 × 6 × 4 in screw-cover enclosure. | **BLOCKING** |
| Q-3 | Confirm the branch is ≤ 15 A. A 20 A branch needs per-channel fuses or 20 A relays (a different design). | **BLOCKING** |
| Q-4 | Load list. Are any loads heaters, pumps, compressors or life-safety equipment, i.e. loads that are unsafe if a contact welds? Motors cycled more than about 5 times a day should drive a contactor (C-10). | **BLOCKING** |
| Q-5 | Surface mounting is required (C-6). Flush mounting in an insulated wall overheats the box and is excluded. Confirm. | **BLOCKING** |
| Q-6 | Insulating cover over the SELV zone (MP1): confirm the material and the method of fixing, and that the AHJ accepts it as the barrier under NEC 725.136(B). | **BLOCKING** |
| Q-7 | Watchdog semantics. The default (software heartbeat) turns outputs OFF when the control app hangs. A hardware-PWM heartbeat would keep outputs ON through app hangs. Which does the user want? | no |
| Q-8 | Pi-side termination of the cable: GPIO screw-terminal HAT or crimped 2.54 mm housings. | no |
| Q-9 | Surge protection: a Type 2 SPD at the panel is recommended instead of an MOV in the box (C-11). | no |
| Q-10 | Do the outputs feed downstream boxes with receptacles ("like outlets"), or loads wired directly? | no |
| Q-11 | Relay supply: Digi-Key now lists the G5RL under "Aratas, formerly Omron Components" [S], with a 26-week lead time. Qualify the second source. | no |

## 4. Hazards

| ID | Hazard | Mitigation | Implemented by | Survives a single fault? |
|---|---|---|---|---|
| H1 | Shock from live parts with the cover off | Listed steel box, ring and screw cover (tool needed); "disconnect before opening" label; electrician installs | box, ring, cover, labels | n/a (service condition): de-energize at the breaker |
| H2 | Mains reaches SELV and the Pi | Reinforced insulation: relay 8/8 mm, 6 kVAC, 10 kV impulse [P]; PCB 8/8 mm band; MP1 cover keeps field conductors off SELV parts; SELV cable on its own knockout | K1–K4, layout, MP1 | **Yes** (reinforced = double) |
| H3 | Metal box becomes live | All EGCs spliced with a listed connector, pigtail to the box ground screw; ring and cover bonded by their screws | installer | **Yes** (needs insulation failure plus loss of EGC) |
| H4 | Overload heats conductors, PCB, terminals or relays | One protective device (branch OCPD ≤ 15 A); every downstream element rated ≥ 15 A at temperature (C-7, C-9) | breaker, layout | **Yes** (breaker); 15–20 A overloads tested in T-OL |
| H5 | Short circuit on an output | Breaker clears it; copper I²t margin 1.4× at 2 kA (C-7); the steel box contains any arc | breaker, layout | **Yes** up to 2 kA |
| H6 | Loose or partially inserted conductor heats up | Spring clamps (no torque relaxation); strip length printed; pull test at commissioning | J1–J5, labels | **No**: inspection is the barrier |
| H7 | Fail-ON from a welded contact | Inrush-rated relay (TV-8, 100 A peak); load limits (REQ-5); no snubber; warning that the outputs are not for loads that are hazardous if left on | K1–K4, documentation | **No**: residual risk, disclosed (Q-4) |
| H8 | Fail-ON from control: software bug, hung or crashed Pi, stuck GPIO, shorted MOSFET | Coil current needs both Q_k (GPIO) and Q5 (heartbeat pump); 4.7 kΩ pull-downs; coils powered from the Pi | Q1–Q5, D12, C3, C4, R5–R8 | Hung or crashed software, stuck GPIO, shorted Q5: **yes** (the other path still blocks). Shorted Q_k while the heartbeat runs: **no**. Channel k follows ARM; its LED shows it; stopping the heartbeat turns it OFF |
| H9 | Glitch to ON at boot or reset | Default-pull-down pins plus 4.7 kΩ pull-downs; arming needs ≥ 100 Hz toggling | R5–R8, ARM block | **Yes** |
| H10 | Remote energization while a load is being serviced | Label: relays are not a disconnecting means; lock out at the breaker | labels | **No** (procedural) |
| H11 | Shock from an "OFF" output | No snubbers or MOVs across the contacts (C-12); line-only switching; polarity checked at commissioning (L/N swapped would switch the neutral) | design, T-MISWIRE | Leakage: yes. Miswire: **no** (procedural) |
| H12 | Overtemperature in the closed box | 4 W budget; surface mounting required; 12 A continuous limit (C-6) | REQ-7/19 | **Yes** with margin |
| H13 | Surge flashover or arc tracking | OVC II coordinated spacing; relay 10 kV impulse; no unprotected MOV in the box; panel SPD recommended | layout, Q-9 | **Yes** |
| H14 | Pi damaged by wiring errors | PTC F1, TVS D11, ESD array U1, two GND conductors, no back-power path from the GPIOs (U1 has no supply pin) | F1, D11, U1 | **Yes** |
| H15 | Motor stall | The motor's own overload protection (NEC 430); 1/2 hp relay rating; contactor recommended for larger motors | user | n/a |

## 5. Architecture trade study

Criteria, weight (score 1–5): **S** safety and failure mode (30), **T** heat in a closed box (20),
**L** load compatibility (15), **O** OFF-state isolation (10), **C** UL parts and certification path (10),
**X** complexity and cost (10), **B** fit to the brief (5).

| Alternative | S | T | L | O | C | X | B | Weighted /5 |
|---|---|---|---|---|---|---|---|---|
| **A1 PCB relays with reinforced insulation (G5RL TV-8), MOSFET drivers, heartbeat watchdog** | 4 | 5 | 4 | 5 | 4 | 4 | 5 | **4.35** |
| A2 Zero-cross triac SSRs | 2 | 1 | 3 | 1 | 4 | 3 | 3 | 2.20 |
| A3 MOSFET AC SSRs (photovoltaic driver) | 2 | 2 | 3 | 3 | 2 | 2 | 3 | 2.30 |
| A4 Hybrid (relay with a triac across it) | 3 | 4 | 5 | 2 | 2 | 1 | 4 | 3.15 |
| A5 Listed products (4 × Functional Devices RIB relays plus driver, or a Digital Loggers IoT Relay) | 5 | 4 | 4 | 5 | 5 | 2 | 2 | 4.20 |

Why the alternatives lose:

| Alt | Reason |
|---|---|
| A2 | 1–1.5 V drop: 15–20 W per channel, impossible in a closed box (C-6). Fails shorted (fail-ON). mA-level off-state leakage |
| A3 | 5–9 W per channel. Fails shorted. Few UL-recognized 15 A PCB parts |
| A4 | The triac adds a fail-ON path, leakage and a second barrier crossing, for life gains that outlet duty does not need |
| A5 | The *safest* path; offer it to the user (Q-1). It loses only on fit to the brief and on cost. It is not a Pi breakout; RIB relays need 24 V plus a driver; the IoT Relay has one shared control input |

Relays win: the OFF state is an air gap, a coil dissipates 0.4 W, the insulation is certified
inside the part, and listed motor, tungsten and inrush ratings exist.

**Packaging: the Pi stays outside the box (P1).**

- **Rejected, P2: Pi plus an AC/DC module (e.g. Mean Well IRM) in a larger box.** Steel blocks Wi-Fi. The Pi adds 3–7 W of heat. The SD card would sit behind a mains cover. It does not fit a 4-11/16" box.
- **Rejected, P3: relay HAT on the Pi.** It puts mains over unlisted consumer electronics.
- **Chosen, P1.** One Class 2 cable enters through its own knockout. The Pi's PSU powers the coils, so the box has no converter, fuse or extra heat. No Pi means no coil power.

**Options decided:**

| Option | Decision | Reason |
|---|---|---|
| Discrete MOSFET drivers | in (AO3400A) | A ULN2803 drops up to 1.1 V and would leave the coil at about 69 % of rated, below must-operate (C-3) |
| Flyback diodes | in | Coil spikes otherwise exceed MOSFET ratings |
| Status LEDs | in (SELV side) | Commissioning with mains OFF |
| Watchdog (heartbeat charge pump) | in | Covers hung or crashed control software (H8) |
| HAT ID EEPROM | out | Not a HAT: the board is on a cable, and the ID pins are left free |
| Per-channel current sensing | out | Would add four more barrier crossings and mains-side dissipation |
| Manual override switches | out | Hidden in a closed box, and an override bypasses the fail-safe |
| Contact-state readback | out | Detecting a weld would not remove it (it needs a series contact); disclosed as H7 |
| Input fuse / per-output fuses | out | The branch OCPD ≤ 15 A protects every element (C-9); a fuse inside a box is not user-serviceable |
| MOV / snubbers | out | C-11, C-12 |
| AC/DC module (IRM) | out | Coils are powered from the Pi (P1) |

**Channel count: 4.** Four channels fill a 106 × 80 mm board. Six relays plus seven terminals
need ≥ 145 mm, but the box interior is about 116 mm. Six channels also exceed the box-fill limit (C-1).

## 6. Blocks and domains

| Block | Function | Parts | Ports (dir, domain, V range, I max) |
|---|---|---|---|
| B1 MAINS_IN | Shared input, L and N buses | J1, PCB buses | L_IN (in, LINE, 0–132 VAC, 1.5 kV transient, 15 A); N (bidir, NEUTRAL, 15 A) |
| B2 SW_k (k = 1…4) | Switch one output | K_k contacts, J_(k+1) | L_IN (in, 15 A); L_SWk (out, OUTk, 0–132 VAC, 15 A); N (pass, 15 A) |
| B3 DRV_k | Coil drive and indication | K_k coil, Q_k, D_k, D_(k+4), R_k, R_(k+4), R_(k+8) | CHk_IN (in, SELV, 0–3.3 V, 0.6 mA); +5V (in, SELV, 4.5–5.25 V, 93 mA); COIL_RTN (out, SELV, 93 mA) |
| B4 ARM | Heartbeat charge-pump watchdog, low-side enable for all coils | R13, C3, D12, C4, R14, Q5, D9, R15, TP3, TP4 | HB_IN (in, SELV, 0–3.3 V, 3.3 mA peak); COIL_RTN (in, 0.39 A); GND |
| B5 SELV_IN | Link terminal and protection | J6, F1, D11, C1, C2, U1, D10, R16, TP1, TP2 | +5V_IN (in, 4.75–5.25 V, 0.39 A); GND; CH1–4_IN, HB_IN (in, 0–3.3 V); +5V (out, 0.39 A) |
| B6 MECH | Mounting and barrier | H1–H4, MP1, supports, box, ring, cover | — |
| B7 PI (off-board) | Controller | Raspberry Pi 40-pin header | 5 V, GND, BCM17/27/22/23/12 |
| B8 FIELD (off-board) | Building wiring | input and output cables, EGC splice | — |

| Domain | Nets | Reference | Voltage range | Notes |
|---|---|---|---|---|
| LINE (root) | L_IN | L_IN itself (0 V) | 0 V by definition; 0–132 V rms (187 V pk) to N; transient ≤ 1.5 kV pk (OVC II) | hazardous live. L is the mains reference so that the voltage across an open contact is exact |
| NEUTRAL | N | L_IN | ±187 V pk; ≈ 0–5 V rms to PE in normal use; treated as hazardous | not switched |
| OUT1…OUT4 | L_SW1…L_SW4 | L_IN | 0 V when closed; ±187 V pk when open (pulled to N by the load) | state-dependent |
| PE | (off-board) box, ring, cover, EGC, ground screw | earth | 0 V | not on the PCB |
| SELV | +5V_IN, +5V, GND, CHk_IN, CHk_G, COILk, LEDk_A, COIL_RTN, HB_IN, HB_R, PUMP, ARM_G, LED_ARM_A, LED_PWR_A | GND (may be earthed through the Pi) | 0–5.25 V; transients clamped to ≤ 12 V (D11) | Class 2 / ES1 |

Barrier table. Uw = working voltage. Creepage/clearance in mm. PD2, OVC II and MG IIIb unless noted.
Values marked [I] for IEC 60664-1 Table F.4 rows other than 63 V and 400 V are recalled and must be verified.

| Pair | Grade | Uw | Governing standard | Required creepage / clearance (source) | Design creepage / clearance | Slot |
|---|---|---|---|---|---|---|
| SELV ↔ LINE (covers NEUTRAL and OUT1–4, which float on LINE) | reinforced | 120 V rms (designed for 250 V) | UL/IEC 62368-1 Tables 10 and 17; IEC 60664-1 F.1/F.2/F.4 | At 120 V: creepage 2 × 1.5 = **3.0** (F.4, 125 V row, MG III [I]); impulse 1.5 kV (F.1 [P, via SLUP419]); clearance 1.5 (F.2, one step up to 2.5 kV [P]) or 2 × 0.76 ≈ 1.5 (62368-1 T10 [P/I]). At 240 V: creepage **5.0**, clearance **3.6** (62368-1 T10, 2.5 kV reinforced [P via SLUP419]) | **8.0 / 8.0**, matching the relay's own 8/8 mm [P] | no |
| LINE or OUTk ↔ NEUTRAL | functional (operational) | 120 | UL 1059 use group C, 51–150 V [S]; functional under 62368-1 | 6.4 / 3.2 | 6.4 / 3.2 | no |
| OUTj ↔ OUTk | functional | 120 (one on, one off) | as above | 6.4 / 3.2 | 6.4 / 3.2 | no |
| LINE ↔ OUTk (same channel, open contact) | functional | 120 | IPC-2221B B2, 151–170 V peak [S] | 1.25 / 1.25 | 2.5 / 1.5 outside the relay footprint; inside it the relay's pin pitch (5.0 mm) governs | no |
| LINE (all mains) ↔ PE (box metal; bare EGC near a board edge) | basic | 120 | 62368-1 basic: clearance 0.76 [P/I], creepage 1.5 [I]; UL field wiring to dead metal 6.4 [S] | 6.4 to box metal; 1.5 / 0.76 to a board edge | 6.4 to box metal (placement, nylon supports); 2.0 / 2.0 copper-to-edge | — |
| SELV ↔ PE | none | — | — | — | — | — |
| SELV cable ↔ mains field conductors inside the box | Class 2 separation | — | NEC 725.136(B), (D)(1) [S] | barrier, or ≥ 6 mm | MP1 cover plus its own knockout | — |

**240 V variant.** The SELV barrier (8/8 mm) and the relays (rated insulation voltage 250 V, OVC III
[P]) are unchanged. The opposite-polarity mains spacings would rise to the UL 151–300 V class [S]
and must be re-checked.

## 7. Calculations

**C-1 Box, fill, channel count.**

- **Volume.** RACO 257: outside 119.1 × 118.3 mm, inside depth 54 mm, 42.0 in³ [P]. The inside is about 115.9 mm square (wall ≈ 1.6 mm [I]). The RACO 250 ring adds 29.5 in³ [P], giving V_box = 71.5 in³.
- **Allowances at 12 AWG** (2.25 in³ each, Table 314.16(B) [I]):
  - 10 insulated conductors: 22.50 in³.
  - 5 EGCs = 1 + ¼ allowance (314.16(B)(5), 2020+ [S]): 2.81 in³.
  - Class 2 cable, counted conservatively: 2.0 in³ [I].
  - Clamps: 2.25 in³.
  - Total **29.6 in³**.
- **Displaced volume** (bounding boxes):
  - Board plus supports, 106 × 80 × 14.3 mm: 121 cm³.
  - Terminals: 58 cm³.
  - Relays: 23 cm³.
  - MP1 cover: 57 cm³.
  - Total 259 cm³ = **15.8 in³**.
- **Result.** 71.5 − 15.8 = 55.7 ≥ 29.6 in³ (53 % filled). Without the ring, 26.2 < 29.6, so **the ring is required**. Six channels need 39.7 in³ and a board ≥ 145 mm wide (the box gives about 116 mm), so they do not fit.

**C-2 5 V budget.**

- Coils: 4 × 5.0/62.5 = 320 mA nominal. Worst case 4 × 5.25/56.25 Ω (−10 % resistance) = 373 mA [P coil data].
- LEDs: 6 × (5.25 − 1.9)/1.485 k = 13.5 mA.
- Pull-downs and pump: < 1 mA.
- **I_5V ≤ 0.39 A.**
- **Pi 4 headroom.** 3.0 A PSU − 1.2 A USB maximum − 1.25 A stress maximum = 0.55 A [P], so 71 % is used. A Pi 5 on its 5 A PSU has ≥ 0.9 A spare [I].
- **GPIO load.** Each CH pin draws 3.3/5.7 k = 0.58 mA. HB draws ≤ 3.3 mA peak and about 25 µA average. The total, ≤ 5.6 mA, is well inside the Pi's limits of 50 mA combined and 16 mA per pin [P].

**C-3 Coil voltage and must-operate.**

- **Supply equation.** V_relay = V_hdr − I(R_cable + R_PTC + R_Q5) − I_k·R_Qk.
  - R_cable for 3 m of 22 AWG (+5V on one conductor, GND on two): 0.238 Ω.
  - R_PTC ≤ 0.20 Ω [P]; R_DS(on) ≤ 48 mΩ [P].
  - I = 0.388 A, I_k = 0.093 A.
- **Drop and result.** The drop is **0.193 V**. That leaves 4.71 V (94 %) at V_hdr = 4.90 V on the official PSU, or 4.56 V (91 %) at 4.75 V.
- **Must-operate threshold.** 70 % × (234.5 + T_c)/257.5 [P, scaled by copper resistance]:
  - Cold start in a 55 °C box: 76 % (margin ≥ 15 points).
  - Hot restart with the coil at 90 °C (55 + 35 K rise [I]): 88.2 % (margin 3–6 points, measured in T-COIL).
- **Driver choice.** A ULN2803 would drop up to 1.1 V [I], leaving 3.46 V (69 %), which fails. The maximum coil voltage is 105 % (limit 130 % [P]).

**C-4 Heartbeat pump (R13 = 1 kΩ, C3 = 1 µF, BAT54S, C4 = 100 nF, R14 = 1 MΩ).**

- **Why the values changed.** The first values (C4 = 1 µF, R14 = 100 kΩ) gave V_ARM ≈ 2.45 V at 100 Hz. That is below the 2.5 V at which the AO3400A's R_DS(on) is specified, and the encoded calc limit exposed it. The fix keeps τ = 0.1 s and cuts the bleed current tenfold.
- **Steady state.** V_pk = V_OH − 2V_F = 3.2 − 2 × 0.24 = 2.72 V, using V_F ≤ 0.24 V at 0.1 mA [P]. The bleed is I = 2.7 µA. The minimum at 100 Hz is V_pk − I/(f·C3) − I·5 ms/C4 = **2.56 V ≥ 2.5 V**.
- **Q5 drop.** Q5 conducts 0.39 A at ≤ 48 mΩ (≤ 19 mV).
- **Arming.** C3 ≫ C4, so V_ARM is above 2.4 V after 1–2 cycles.
- **Disarm.** τ = R14·C4 = 0.1 s. V_GS falls below V_th(min) 0.65 V in 0.1·ln(2.72/0.65) = 0.14 s; adding the relay release (≤ 5 ms [P]) gives **0.15 s**, against 0.5 s required.
- **DC on HB**, high or low: C3 blocks it, so the outputs disarm.
- **Low frequencies.** Between about 5 and 20 Hz, C4 droops 20–60 % each half cycle and the outputs may chatter, so below 100 Hz is not allowed (REQ-16).

**C-5 Gate drive and floating inputs.**

- Driven high: V_G = 3.3 × 4.7/5.7 = 2.72 V ≥ 2.5 V, where R_DS(on) is specified [P].
- Open or floating: 0 V.
- Worst case, a miswire onto a GPIO with a default 33 kΩ pull-up [P]: V_G = 3.3 × 4.7/(4.7 + 1 + 33) = 0.40 V < V_th(min) 0.65 V. **This survives miswiring.**
- **Chosen pins.** BCM17/27/22/23 (CH) and BCM12 (HB) default to pull-low on BCM2711 [P]. On the Pi 5 (RP1) the reset pull "varies" but outputs are disabled at reset [P], so safety does not rely on internal pulls.
- **Avoided pins.** BCM0–8 (pull-high), 2/3 (fixed pull-ups), 0/1 (EEPROM probe at boot), 14/15 (boot UART [I]), 18–21 (PCM).

**C-6 Thermal (closed box).**

- **Losses, one channel at 15 A with all coils on:**
  - Coils: 1.60 W.
  - Relay contact path: 15² × 5 mΩ [I] = 1.13 W.
  - PCB copper: 0.79 W (C-7).
  - Terminals (4 × 0.5 mΩ [I]): 0.45 W.
  - LEDs: 0.06 W.
  - Total **4.0 W**; **3.2 W** at 12 A continuous.
- **Surface-mounted box.** Exposed area is 0.0589 m² and h ≈ 6.5 W/m²K [I], so ΔT = 8.4 K at the wall plus about 5 K to the internal air [I]. The inside reaches **≈ 55 °C** at a 40 °C room.
- **Against ratings:**
  - Relay: 85 °C max, 16 A at 85 °C (VDE) [P].
  - Terminals: 105 °C, about 28 A at 70 °C [P].
  - LEDs: 85 °C [P].
- **Flush mounting** in an insulated wall leaves only the cover (0.0142 m²) to shed heat: ΔT ≈ 35 K, inside ≈ 80 °C. **Excluded** (Q-5).

**C-7 Mains copper.** 2 oz copper, 7.5 mm wide on *both* layers: 1.05 mm² (2072 cmil).

- **Heating.** IPC-2221 external, I = 0.048·ΔT^0.44·A^0.725, with 7.5 A in 813 mil² per layer: **ΔT ≈ 1.6 K** [I]. For comparison, one layer at ΔT = 10 K would need 6.3 mm.
- **Resistance.** 0.019 mΩ/mm at 60 °C. The longest L + N path is ≈ 185 mm, giving 3.5 mΩ and 0.79 W.
- **Fault withstand.** Onderdonk melt I²t = A_cmil²·log₁₀(1 + 1058/259)/33 = **92 kA²s**.
  - A 15 A breaker clearing 2 kA within one cycle lets through ≤ 67 kA²s: margin 1.4×. At 1 kA the margin is 5.5×.
  - 10 m of 14 AWG limits the fault current to ≈ 0.6 kA.
- **Layer stitching.** ≥ 4 vias of Ø0.6 mm every 10 mm along each bus [I].

**C-8 Creepage and clearance** (derivation in §6).

- **Margins.** 8.0/8.0 mm is ≥ 2.6× the 120 V reinforced creepage, ≥ 1.6× the 240 V value, and ≥ 2.2× the 240 V clearance. It also meets PD3 at 250 V (2 × 4.0 [I]), so no slot is needed.
- **Under the relay.** Coil pads to contact pads are **18 mm** edge to edge (20 mm pitch, Ø2.0 mm pads [P]), so no slot is needed there either. Instead, the band from the coil-pad edge (+1.0 mm) to +9.25 mm is copper-free on all layers.

**C-9 Protection coordination, wire, PTC.**

- The branch OCPD (≤ 15 A) is the only protective device. Everything downstream is rated at or above it:
  - 14 AWG conductors, 15 A at 60 °C [I].
  - Terminals: 31 A, i.e. 48 % used.
  - Relays: 16 A general use (94 % at 15 A; 75 % at the 12 A continuous limit).
  - PCB copper: ΔT ≈ 1.6 K.
- Continuous loads ≤ 80 % of 15 A = 12 A (NEC 210.19/210.20 [I]).
- PTC F1:
  - I_hold 1.1 A = 2.8 × 0.39 A. At 55 °C the hold current derates to ≈ 0.85 A [I].
  - I_trip 2.2 A ≤ Pi PSU 3 A.
  - V_max 16 V ≥ a 12 V wiring mistake [P].
- TVS D11: V_WM 7.0 V ≥ 5.25 V (75 %); clamps 12.0 V at 33 A [P]. C1 (16 V) sees ≤ 75 %.

**C-10 Relay ratings vs loads and life [P, UL file E41643].**

| Rating | Operations | Use |
|---|---|---|
| 16 A, 277 VAC general use | 50,000 | sets the 15 A per-channel maximum |
| TV-8 at 120 VAC | 25,000 | tungsten ≤ 8 A |
| 1/2 hp at 120 VAC | 6,000 | 9.8 A FLA (NEC Table 430.248 [I]) |
| A300 pilot duty | 30,000 | contactor coils |
| VDE 240 V, 100 A peak inrush / 10 A steady | 50,000 | LED-driver inrush budget per channel |

At 20 operations a day the motor rating lasts about 10 months. Frequently cycled motors therefore
drive a contactor coil (A300 rating). Lighting at 4 operations a day lasts more than 17 years.

**C-11 Surge and MOV energy (why there is no MOV).** IEEE C62.41.2 [I]:

- **Category B** (6 kV / 3 kA) into a 14 mm 140 VAC MOV clamping at about 450 V: E ≈ 450 × 3000 × 22 µs ≈ **30 J**. That is about 55 % of its roughly 55 J rating [S].
- **Category A** (200 A ring wave): ≈ 0.4 J.

The MOV would age, and an aging MOV is a fire source in a closed, unlisted box. The insulation is
already coordinated for OVC II. Use a listed Type 2 SPD at the panel instead (Q-9).

**C-12 OFF-state leakage.** A 0.1 µF snubber across the contacts would leak
2π·60·0.1 µF·120 V = **4.5 mA**: perceptible, and enough to light LED lamps. So there are no snubbers.
Open contacts measure ≥ 1000 MΩ at 500 VDC [P], so leakage is < 0.2 µA. Any suppression for
inductive loads goes at the load.

## 8. Parts

Datasheets were read for every on-board part except where marked. Lifecycle comes from Digi-Key
(October 2026) [S] unless noted. "Stress" is the worst case in this design.

| Ref | Role | Mfr / MPN | Key ratings | Stress (margin) | Pkg | KiCad symbol / footprint | Datasheet | Life | 2nd source |
|---|---|---|---|---|---|---|---|---|---|
| K1–K4 | SPST-NO relay | Omron (Aratas) **G5RL-1A-E-TV8 DC5** | UL/CSA E41643: 16 A 277 VAC GU, TV-8, 1/2 hp 120 V, A300. VDE: 16 A at 85 °C, 100 A peak inrush. Coil 5 V / 80 mA / 62.5 Ω / 400 mW, operate ≤ 70 %, release ≥ 10 %, max 130 %. Coil–contact reinforced 8/8 mm, 6 kVAC, 10 kV impulse. −40…85 °C | 15/16 A = 94 % (12 A continuous = 75 %); coil 91–105 %; 55 °C vs 85 °C | THT 29 × 12.7 × 15.7 | `Relay:G2RL-1A-E` (pin-identical; Value overridden) / `Relay_THT:Relay_SPST_Omron_G2RL-1A-E` (hole pattern identical to G5RL [P]) | omronfs.omron.com/en_US/ecb/products/pdf/en-g5rl.pdf | Active [S] | G5RL-1A-E-HR DC5 (TV-5) [P]; G2RL-1A-E DC5 (GU only) [P] |
| J1–J5 | Mains field terminal, 2-pole | WAGO **2606-3102/020-000** | UL 1059 E45172, use groups B/C: 600 V 31 A; 24–8 AWG; lever; 7.5 mm pitch, staggered pins; PA66 V-0; −60…105 °C | 15/31 A = 48 %; 132/600 V | THT, Ø2.0 holes | `Connector_Generic:Conn_01x02` / **custom** `kae:WAGO_2606-3102_020-000` (geometry: WAGO datasheet p.1 drawing) | wago.com/2606-3102/020-000 | Active [S] | Phoenix lever 7.5 mm [unverified] |
| J6 | SELV link terminal, 8-pole | WAGO **2601-3108** | UL 1059 groups B/D: 300 V 10 A; 26–16 AWG; lever; 3.5 mm | 0.39/10 A = 4 % | THT | `Connector_Generic:Conn_01x08` / `TerminalBlock_WAGO:TerminalBlock_WAGO_2601-3108_1x08_P3.50mm_Vertical` | wago.com/2601-3108 | Active [S] | — |
| Q1–Q5 | N-MOSFET | AOS **AO3400A** | 30 V; 5.7 A; R_DS ≤ 48 mΩ at 2.5 V; V_th 0.65–1.45 V; V_GS ±12 V | V_DS 6.1/30 = 20 %; V_GS 3.3/12 = 28 %; I_D 0.39/4.7 A; ≤ 11 mW | SOT-23 | `Transistor_FET:AO3400A` / `Package_TO_SOT_SMD:SOT-23` | aosmd.com/res/datasheets/AO3400A.pdf (rev 3.1, Jul 2023) | Active [I] | Diodes DMN2041L [unverified] |
| D1–D4 | Coil flyback | Diodes **1N4148W-7-F** | 100 V; I_FM 300 mA; 2 A surge; 400 mW | V_R 5 %; I_F 93/300 mA pulse = 31 % | SOD-123 | `Diode:1N4148W` / `Diode_SMD:D_SOD-123` | diodes.com/assets/Datasheets/ds30086.pdf | Active [S] | Vishay 1N4148W [unverified] |
| D5–D10 | Indicator LED | Kingbright **APT1608SGC** | 25 mA; 62.5 mW; V_R 5 V; V_F 2.2 / 2.5 V; −40…85 °C | 2.3 mA = 9 %; 5 mW = 8 %; V_R 0.9/5 V | 0603 | `Device:LED` / `LED_SMD:LED_0603_1608Metric` | kingbrightusa.com/images/catalog/SPEC/APT1608SGC.pdf | Active [S] | Würth 150060VS75000 [S] |
| D11 | TVS on 5 V | Vishay **SMAJ7.0A-E3/61** | V_WM 7.0 V; V_BR 7.78–8.60 V; V_C 12.0 V at 33.3 A; 400 W; UL 497B | 5.25/7.0 = 75 % | SMA | `Diode:SMAJ5.0A` (Value SMAJ7.0A) / `Diode_SMD:D_SMA` | vishay.com/docs/88390/smaj50a.pdf | listed, status not shown [S] | Littelfuse SMAJ7.0A [unverified] |
| D12 | Pump diodes | Diodes **BAT54S-7-F** | 30 V; 200 mA; V_F ≤ 0.24 V at 0.1 mA | V_R 3.6/30 = 12 % | SOT-23 | `Diode:BAT54S` / `Package_TO_SOT_SMD:SOT-23` | diodes.com/assets/Datasheets/ds11005.pdf | listed [S] | Nexperia BAT54S [unverified] |
| U1 | 6-channel ESD array | TI **TPD6E05U06RVZR** | V_IO ≤ 5.5 V; V_BR ≥ 6.5 V; ±12 kV contact; 2.5 A 8/20 µs | 3.3/5.5 V = 60 % | USON-14 | `Power_Protection:TPD6E05U06RVZ` / `Package_SON:Texas_R-PUSON-N14` | ti.com/lit/ds/symlink/tpd6e05u06.pdf | Active [S] | 2 × TPD4E05U06 [P] |
| F1 | PTC on 5 V | Bourns **MF-MSMF110/16X-2** | I_hold 1.1 A; I_trip 2.2 A; 16 V; 100 A; 0.06–0.20 Ω; UL E174545 | 0.39/1.1 A = 35 % (46 % at 55 °C); 5.25/16 V | 1812 | `Device:Polyfuse` / `Fuse:Fuse_1812_4532Metric` | bourns.com/docs/Product-Datasheets/mfmsmf.pdf | Active [S] | MF-MSMF110/16-2 [S] |
| R1–R4, R13 | 1 kΩ 1 % 0.1 W 75 V | Yageo **RC0603FR-071KL** | 0.1 W; 75 V [S] | ≤ 11 mW (R13) = 11 % | 0603 | `Device:R` / `Resistor_SMD:R_0603_1608Metric` | yageogroup.com RC series | Active [S] | any 0603 1 % |
| R5–R8 | 4.7 kΩ gate pull-down | Yageo **RC0603FR-074K7L** | as above | 2.3 mW = 2 % | 0603 | as above | as above | Active [I] | any |
| R9–R12, R15, R16 | 1.5 kΩ LED | Yageo **RC0603FR-071K5L** | as above | 7.5 mW = 8 %; 3.4/75 V | 0603 | as above | as above | Active [S] | any |
| R14 | 1 MΩ bleed | Yageo **RC0603FR-071ML** | as above | 7 µW | 0603 | as above | as above | Active [S] | any |
| C1 | 10 µF 16 V X5R | Murata **GRM21BR61C106KE15L** | 16 V | 5.25 V = 33 % (12 V transient = 75 %) | 0805 | `Device:C` / `Capacitor_SMD:C_0805_2012Metric` | murata.com | Active, backordered [S] | Yageo CC0805KKX5R7BB106 [S] |
| C2, C4 | 100 nF 50 V X7R | Yageo **CC0603KRX7R9BB104** | 50 V | 11 % | 0603 | `Device:C` / `Capacitor_SMD:C_0603_1608Metric` | yageogroup.com | Active [S] | Murata GRM188R71H104KA93D [unverified] |
| C3 | 1 µF 16 V X7R | Yageo **CC0603KRX7R7BB105** | 16 V | 3.6/16 V = 23 % | 0603 | as C2 | yageogroup.com | Active [S] (replaces the obsolete Murata GRM188R71C105KA12D [S]) | Murata 1 µF 16 V X7R [unverified] |
| TP1–TP4 | Test pads | — | — | — | Ø1.5 mm pad | `Connector:TestPoint` / `TestPoint:TestPoint_Pad_D1.5mm` | — | — | — |
| H1–H4 | Mounting holes Ø4.0 mm NPTH | — | — | — | — | `Mechanical:MountingHole` / `MountingHole:MountingHole_4mm` | — | — | — |
| (off-board) | Box | Hubbell RACO **257** | 4-11/16" square × 2-1/8", welded steel, 42.0 in³, raised ground (#10-32), UL listed | — | — | — | hubbellcdn.com/specsheet/RACO-257-SPEC-EN.pdf | Active [P] | any listed 4-11/16 × 2-1/8 box |
| (off-board) | Extension ring | RACO **250** | 1-1/2", 29.5 in³, cULus | — | — | — | hubbellcdn.com/specsheet/RACO-250-SPEC-EN.pdf | Active [P] | — |
| (off-board) | Cover | RACO **832** | flat blank, cULus | — | — | — | hubbellcdn.com/specsheet/RACO-832-SPEC-EN.pdf | Active [P] | — |
| (off-board) ×4 | Board supports | Essentra **LCBS-8-19** | nylon 6/6, UL 94 V-0; 12.7 mm; PCB hole 4.0 mm; chassis hole 4.75 mm, 0.79–1.98 mm panel | — | — | — | Richco/Essentra LCBS drawing | listed [S] | LCBS-8-01 (V-2) [P] |
| MP1 | SELV-zone insulating cover | custom, 0.43 mm polypropylene, UL 94 V-0 (Formex GK-17 class) | — | — | — | — | — | [unverified] | polycarbonate, 0.8 mm |
| (off-board) | Field items | 8-conductor 22 AWG CL2 cable; listed NM cable connectors; listed EGC splice (UL 486C); a 1/2" bushing for the Class 2 cable | — | — | — | — | — | [I] | — |

Counts: 49 placed electrical parts (17 distinct MPNs), 4 test pads, 4 holes, and one custom footprint (J1–J5).

## 9. Placement and mechanical constraints

**Board and box.**

- **Board.** 106.0 × 80.0 mm, R2 corners, 2 layers, 1.6 mm FR-4, 2 oz both sides. UL 94 V-0, ZPMV2 laminate, CTI ≥ 175 V. All parts on the top side.
- **Mounting.** H1–H4 are Ø4.0 mm NPTH, 4 mm in from each corner, with an Ø8 mm copper keepout. They take LCBS-8-19 supports (12.7 mm). The installer drills 4 × Ø4.75 mm holes in the box bottom from a 1:1 template on the bench.
- **Position in the box.** The south edge sits against the south wall. That leaves a **free band of about 36 mm** along the north wall for the box ground screw, the EGC splice and conductor slack.
  - On the RACO 257 the screw tap is 30.2 mm from the outer edge [P], i.e. about 28.6 mm from the inner wall [I].
  - With other boxes, orient the box so the screw falls in the band, or use a listed ground clip.
- **Cable entries.** Field cables come in through the north, east and west walls and the ring. The Class 2 cable uses a west-wall knockout next to J6 with a bushing. The Pi is in its own case, ≤ 3 m away.
- **Clearance above.** The terminals top out at about 41 mm, leaving about 52 mm for conductors (box plus ring depth ≈ 93.7 mm [P]).

**Zones, south to north.**

1. SELV band.
2. Relay coil pins.
3. Barrier band: from the coil-pad edge (+1.0 mm) to +9.25 mm, copper-free on all layers.
4. Mains: the L bus under the relay bodies (+9.75 mm up to pads 13), the contact pads, the L_SW runs, the terminals, and the N bus along the north edge.

**Relations.**

```
group(SELV_IN: J6, F1, D11, C1, C2, U1, D10, R16, TP1, TP2)
group(ARM: Q5, D12, C3, C4, R13, R14, D9, R15, TP3, TP4)
group(DRV_k: Qk, Rk, R(k+4), R(k+8), Dk, D(k+4))          for k = 1..4
group(SW_k: Kk, J(k+1))                                   for k = 1..4
edge(J1, north) edge(J2, north) edge(J3, north) edge(J4, north) edge(J5, north)
edge(J6, south)   corner(J6, southwest)                   [ext: corner]
array([J1, J2, J3, J4, J5], x, pitch: equal)             butted blocks, 17.85 mm
array([K1, K2, K3, K4], x, pitch: equal)
align(Kk, J(k+1), x-centre)                               channel columns
align(Qk, Kk, x-centre)   align(D(k+4), Kk, x-centre)
orient(Kk, coil pins (A1, A2) south)                      [ext: orient]
orient(J1..J5, pole 1 row south, pole 2 row (N) north)    [ext: orient]
near(Dk, Kk.A1, tight)  near(Dk, Kk.A2, tight)
near(Qk, Kk.A2, close)  near(R(k+4), Qk.1, tight)  near(Rk, R(k+4), tight)
near(D(k+4), Kk, close) near(R(k+8), D(k+4), tight)
near(U1, J6, tight)  near(F1, J6.1, close)  near(D11, F1.2, tight)
near(C1, D11, close) near(C2, C1, tight)
near(R13, U1.9, close) near(C3, R13, tight) near(D12, C3, tight)
near(C4, D12.2, tight) near(R14, C4, tight) near(Q5, C4, close)
near(Q5, [Q1, Q2, Q3, Q4], close)                         short COIL_RTN
hot_loop([Dk.1, Kk.A1, Kk.A2, Dk.2], "coil flyback loop; keep spikes off SELV wiring")
hot_loop([C1.1, Kk.A1, Kk.A2, Qk.3, Qk.2, Q5.3, Q5.2, C1.2], "coil switching loop")
separate(SELV, LINE, 8.0, 8.0, slot: no)                 LINE subtree = LINE, NEUTRAL, OUT1..4
separate(LINE, NEUTRAL, 6.4, 3.2, slot: no)
separate(NEUTRAL, OUTk, 6.4, 3.2, slot: no)
separate(OUTj, OUTk, 6.4, 3.2, slot: no)                  j ≠ k
separate(LINE, OUTk, 2.5, 1.5, slot: no)                  functional; exempt inside Kk footprint
separate(LINE, PE, 6.4, 6.4)                              PE has no copper: met by placement
keepout(band from 1.0 to 9.25 mm north of the K1..K4 coil-pin row (coil-pad edge + 8.25 mm),
        full board width, copper and vias, all layers; only relay bodies may overhang it)
keepout(2.0 mm strip along every board edge, mains copper, all layers)
        -> E/W walls at 4.95 + 2.0 = 6.95 mm ≥ 6.4 mm
keepout(Ø8 mm around H1..H4, copper and parts, all layers)
keepout(volume above J1..J5 up to 45 mm, parts and MP1)   [ext: 3-D]
keepout(SELV band under MP1, parts taller than 18 mm)     [ext: 3-D]
thermal(Kk, 1.5 W, copper: L and L_SWk pours on both layers, no airflow)
thermal(J1, 0.3 W, copper)
current_path(L_IN, 15 A, ≥ 7.5 mm on F.Cu and B.Cu, 2 oz, ≥ 4 × Ø0.6 mm vias every 10 mm)  [ext]
current_path(N, 15 A, same)   current_path(L_SWk, 15 A, same)                               [ext]
side(all, top)
far(J6, J1..J5)
barrier_part(MP1, covers SELV band except J6 wire entry, height ≥ 20 mm,
             fixed by 2 NPTH snap holes in the SELV band)  [ext]
label(J1: "LINE IN / NEUTRAL IN"; J(k+1): "OUTk L / N"; J6: "+5V GND CH1 CH2 CH3 CH4 HB GND – CLASS 2 ONLY";
      board: "120 VAC 60 Hz, 15 A max branch; Cu 14–12 AWG, strip 11–13 mm;
      DANGER disconnect before opening; outputs are not a disconnecting means")  [ext]
```

**Routing intent.**

- L comes down the west side from J1.1, then runs E–W under the relay bodies into pads 13.
- L_SWk leaves pads 14 northwards to J(k+1).1.
- The N bus follows the north edge through every J.2. It must sit between the L_SW pad row + 6.4 mm and the 2.0 mm edge keepout. Place J1–J5 about 2 mm in from the north edge so this band is ≥ 7.5 mm.
- Installation note: dress bare EGCs along the north wall, ≥ 6 mm from the board edge.

**Vocabulary I needed beyond the given list:**

- `corner`
- `orient`
- `current_path` (width, layers, via stitching per net)
- `barrier_part` (an insulator that is part of the safety case)
- 3-D `keepout` (wire-bending volume, height under a cover)
- `label` (silkscreen safety text)
- Off-board objects as fixed PE obstacles: box walls, ground screw, knockouts and cable-entry directions

## 10. Verification plan

| Test | Hazard / REQ | Method | Pass |
|---|---|---|---|
| T-CREEP | H2, REQ-10–12 | Optical and caliper measurement on the bare and assembled PCB, plus KiCad DRC with the barrier rules | All pairs ≥ the design values in section 6 |
| T-HIPOT | H2, H3 | SELV nets tied together vs. all mains nets tied: 3.0 kVrms, 60 s (type), 1 s (production). Mains vs. box: 1.5 kVrms, 60 s. Insulation resistance at 500 VDC [S/I: 60950-1 Table 5B values] | No breakdown; IR > 100 MΩ |
| T-FUNC | REQ-3, REQ-21 | Each channel driven alone and all together; LEDs checked | Correct output; LED matches the coil |
| T-PWR | REQ-15 | 5 V current at 5.25 V with all on; GPIO currents | ≤ 0.40 A; ≤ 0.6 mA per pin |
| T-BOOT | H9, REQ-13 | Pi 4 and Pi 5: 100 cold boots, reboots, halts and unplugs, with outputs logged by a 4-channel isolated logger (1 ms) | No output energization |
| T-FLOAT | H8 | Open each CH conductor, then GND conductors one at a time, while HB runs | Affected channel OFF; nothing ON |
| T-HB | H8, REQ-14/16 | HB stopped high, stopped low, and at 5, 20, 50, 100, 500, 2000 Hz; measure ARM_G and release time. Inject a Q_k drain-source short | ON only for 100 Hz–2 kHz; OFF ≤ 0.5 s after stop; with Q_k shorted, OFF while HB is absent |
| T-COIL | REQ-17 | 3 m of 22 AWG; Pi 4 under stress plus 1.2 A USB load; 55 °C chamber; hot restart after 1 h ON | 100/100 pickups; V_relay ≥ 4.5 V |
| T-HEAT | H12, REQ-19 | Surface-mounted box, 12 A on one channel, 4 coils on, 4 h at 25 °C; thermocouples on relays, terminals, buses, inside air; extrapolate to 40 °C | Relay ambient ≤ 70 °C; terminals ≤ 90 °C; PCB ≤ 90 °C |
| T-OL | H4 | 20 A on one channel through a 15 A breaker until it trips | No part above its rating; no damage |
| T-SC | H5, REQ-20 | Bolted fault on an output at 1 kA and 2 kA prospective, 15 A breaker, relay closed (sample destroyed) | Breaker clears; copper intact; no flame out of the box; weld noted |
| T-WELD | H7 | Bridge K1's contacts on a test unit | Output stays ON as documented; no other hazard; label present |
| T-LOAD | REQ-5 | 1000 cycles each: 8 A tungsten, 1/2 hp motor (or 9.8 A FLA compressor), LED drivers at 100 A peak inrush | No weld; contact drop < 100 mV at 1 A |
| T-SURGE | H13 | IEC 61000-4-5: 2 kV line–line and 4 kV line–PE (box), with the Pi connected | No flashover; no reset; Pi undamaged |
| T-EFT | H8 | IEC 61000-4-4: ±2 kV on mains, ±1 kV clamp on the Class 2 cable | No uncommanded change of state |
| T-ESD | H14 | IEC 61000-4-2: ±8 kV contact on the Pi-end conductors | No damage; no uncommanded ON |
| T-LEAK | H11, REQ-18 | OFF output into 100 kΩ | ≤ 0.1 mA |
| T-MISWIRE | H11, H14 | Swapped L/N found with a receptacle tester at the outputs (commissioning procedure); 5 V/GND reversed at J6; 12 V on +5V_IN | Procedure catches the swap; F1 trips; board and Pi survive |
| T-BOND | H3 | Box, ring and cover to EGC at 30 A for 2 min | ≤ 0.1 Ω |
| T-FILL | REQ-8 | Wire a full box with 12 AWG | Cover closes without force; no conductor on MP1 |

## 11. Sources

- Omron G5RL datasheet, Cat. No. K132-E1-10 [P]: ratings, insulation, pinout, dimensions (pp. 1–2, 5–6). https://omronfs.omron.com/en_US/ecb/products/pdf/en-g5rl.pdf
- Omron G2RL datasheet [P]: identical footprint. https://omronfs.omron.com/en_US/ecb/products/pdf/en-g2rl.pdf
- WAGO data sheets 2606-3102/020-000 (28.02.2024), 2606-1102/020-000, 2601-3108 [P].
- AOS AO3400A rev 3.1 [P]. Diodes BAT54S DS11005 and 1N4148W DS30086 [P]. Vishay SMAJ5.0A–188CA [P]. TI TPD6E05U06 SLVSBO7O [P]. Bourns MF-MSMF [P]. Kingbright APT1608SGC [P]. Essentra/Richco LCBS drawing [P].
- Hubbell RACO 257 spec sheet and drawing, 250, 832 [P]. https://hubbellcdn.com/salesdrawings/RTB_257_CUSTDWG_EN.pdf
- Broadcom BCM2711 ARM Peripherals, Table 94: default GPIO pulls [P]. https://datasheets.raspberrypi.com/bcm2711/bcm2711-peripherals.pdf
- Raspberry Pi RP1 Peripherals, Tables 4 and 21 [P]. https://datasheets.raspberrypi.com/rp1/rp1-peripherals.pdf
- Raspberry Pi documentation, power-supplies and gpio sources [P]. https://github.com/raspberrypi/documentation
- TI SLUP419 "Demystifying clearance and creepage distance" (Mar 2024) [P]: IEC 60664-1 F.1/F.2/F.4 subsets, IEC 62368-1 Table 10 values. https://www.ti.com/lit/pdf/slup419
- Repo: [docs/topics/rules/isolation-creepage.md](../../docs/topics/rules/isolation-creepage.md).
- NEC (secondary, verify against the adopted edition):
  - 314.16(B)(5) EGC fill [S] (forums.mikeholt.com 2020 box-fill threads).
  - 725.136(D) [S] (Mike Holt forum quotes; ecmag.com).
  - 250.148(B) [S] (eepower.com, "NEC Basics: connections and continuity of EGCs").
  - 240.4(D), 404.2(B), 210.19/20, 310.16, Table 430.248 [I].
- UL 1059 spacings [S] (search snippet of the degson.com UL 1059 table). UL 508 Table 36.1 [S] (TDK-Lambda DRB UL reports).
- Distributor lifecycle and stock [S]: digikey.com searches (October 2026).
