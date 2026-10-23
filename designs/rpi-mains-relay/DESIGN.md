# rpi-mains-relay: six switched 120 VAC receptacles run by an on-board Raspberry Pi Zero 2 W

Status: engineering design, encoded in [design.py](design.py) and [parts.py](parts.py), with custom
footprints from [footprints/make_footprints.py](footprints/make_footprints.py). Not reviewed by a
certification body. This is revision 4 (re-review fixes N1–N3, m1–m8, on the revision-3 single enclosure): revision 2 answered the review in [REVIEW.md](REVIEW.md) and the user
decisions Q-2 to Q-5; revision 3 applies the user's Q-8 decision (one enclosure, receptacles in
its cover).

`kaesynth build` result: 0 errors, 0 warnings, 31 waived findings (6 waiver rules, each with its reason
in [out/report.md](out/report.md)). KiCad ERC is clean and the netlist round trip is identical. Four
BLOCKING questions remain open (Q-1, Q-6, Q-7, Q-17), so the design is not ready for fabrication.

The netlist is in [CONNECTIONS.md](CONNECTIONS.md). Evidence tags: [P] read in the primary source,
[S] secondary source or distributor listing, [V] vendor claim, [I] our inference. Where a standard was
not readable (NEC, UL 508, UL 1059, IEC 60664-1, IEC 62368-1), values come through cited secondary
sources and are tagged so. Verify them against the adopted editions before fabrication.

**Design summary.**

- **Assembly (one listed nonmetallic enclosure, Q-8).** E1 is an ABB/Carlon Circuit Safe NS14126
  polycarbonate enclosure, 14 × 12 × 6 in, UL 50 Type 4X/12/13. It holds the unchanged 200 × 150 mm
  board (relays, supply, Pi) on its PVC back panel. Three Pass & Seymour TR5252 tamper-resistant 15 A
  duplex receptacles, line tabs broken off, sit in a 3-gang opening in the upper half of its cover on a
  polycarbonate subplate (MP4), giving six individually switched outlets. 14 AWG leads with a service
  loop join each receptacle to its terminal block (J2–J4). Mounting devices in a cut cover is not a
  listed method, so Q-17 asks how the AHJ will accept it.
- **Switching.** Six G5RL-1A-E-TV8 relays switch line to the six outlets. They are rated 16 A, TV-8 and 1/2 hp, with reinforced 8/8 mm coil-to-contact insulation.
- **Supply.** A Mean Well IRM-20-5 encapsulated AC/DC module makes 5 V from the shared L/N input behind its own 1 A time-lag fuse (10 kA at 125 VAC). The module is Class II, 4.2 kVAC, certified to UL/IEC 62368-1, and its output is a limited power source (LPS).
- **Pi.** A Raspberry Pi Zero 2 W plugs component side up onto a 2×20 socket (J5) and is back-fed through header pins 2 and 4 behind a 2 A PTC. Its PCB antenna sits on the south board edge over a copper-free zone, inside an RF-transparent enclosure.
- **Fail-safe.** Every coil current needs two keys: its channel GPIO (Q1–Q6) and Q7, held on by a 74LVC1G123 retriggerable monostable. The monostable only stays on while the heartbeat (HB) has rising edges, so if HB stops at either level the outlets go OFF within 0.36 s, while stalls up to 150 ms ride through (simulated in [wdsim.py](wdsim.py)). Q7's drain is read back on BCM16 for a boot-time and periodic self-test.
- **Finger safety.** With the cover off, only the SELV/Pi zone is touchable: a clear IP2X shield (MP16) covers F1, the relay contacts, the PS1 AC end and the line copper; the receptacle backs are shrouded; the field terminals are finger-safe.
- **Separation.** Three barriers keep the field wiring away from the low-voltage side:
  - A polycarbonate partition (MP1) cuts E1 into a field-wiring/receptacle compartment (north) and a PCB/Pi compartment (south).
  - An 8 mm copper-free band on the board separates every SELV part from mains copper.
  - The only parts that cross the barrier are certified ones: the six relays and the supply module.

## 1. Brief and user decisions

"I want you to make a breakout board for a Raspberry Pi that has the ability to switch 120 volts. Maybe 4 or 6 of them. It should use stuff that is reliable. It should have terminals that make it really easy to access. Maybe all with shared inputs and then a whole bunch of outputs or something like that. Kind of like the outlets. It should probably be mounted into an outlet type box."

The user's decisions after the first review are recorded as answered questions in design.py and in section 3:

| Q | Decision (user's words) |
|---|---|
| Q-2 Outputs | "Switched receptacles": actual receptacles in the box that loads plug into, each outlet individually switched (e.g. split-tab duplex receptacles, one relay per outlet). |
| Q-3 Pi location | "Inside, plugged on the board": a self-contained box; the Pi mounts on/plugs onto our board, powered from an on-board safety-certified AC/DC module fed from the shared input. |
| Q-4 Channels | "6 channels, bigger box": choose a larger listed box/enclosure that legally holds 3 duplex receptacles (6 outlets) plus the board, the Pi and the supply. |
| Q-5 Pi power and model | "also the pi should get its power from the 120Vac in the box, so it will need some power conversion stuff. design this for a zero 2W" |

## 2. Requirements

| ID | Requirement | Value + units | Source | Verified by |
|---|---|---|---|---|
| REQ-1 | Supply | 120 VAC (108–132 V), 60 Hz, 1-phase, L + N + EGC; single 2-wire branch, not a multiwire branch circuit | brief; ASM-1 | inspection, T-FUNC |
| REQ-2 | Branch protection | 15 A breaker. GFCI protection where NEC 210.8 requires it and AFCI where 210.12 requires it; the default is a 15 A dual-function AFCI/GFCI breaker. Cu 14 AWG minimum, 12 AWG allowed | NEC 210.8, 210.12, 240.4(D) [S]; relays 16 A (C-9) | label, install check (Q-6) |
| REQ-3 | Outlets | Six individually switched outlets: three split-tab duplex NEMA 5-15R receptacles, one relay per outlet | Q-2, Q-4 | T-FUNC |
| REQ-4 | What is switched | Line only. Neutral is not switched. The EGC never passes through the PCB | NEC 404.2(B) [I], 250.148(B) [S] | netlist review |
| REQ-5 | Rating per outlet | ≤ 15 A general use, ≤ 12 A continuous; motor ≤ 1/2 hp (9.8 A FLA); tungsten ≤ TV-8 (TV-5 with the HR second source); capacitive inrush ≤ 100 A peak | relay UL/VDE ratings [P] | T-LOAD, T-OL |
| REQ-6 | Total current, all outlets | ≤ 15 A, and ≤ 12 A for loads running ≥ 3 h | breaker; NEC 210.19/210.20 [S] | T-HEAT |
| REQ-7 | Enclosure | One listed nonmetallic UL 50 Type 4X/12 polycarbonate enclosure (E1) for board, Pi, supply and the three receptacles, which sit in a 3-gang opening in its cover on subplate MP4 with a nylon wallplate outside. Surface-mounted indoors, cover facing the room; no ventilation openings | Q-3, Q-4, Q-8; C-1, C-6, C-13 | inspection |
| REQ-8 | Box fill | E1 is over 100 in³, outside the NEC 314.16(A) table; conductor and device allowances are shown against its free volume | NEC 314.16 [S/I] | C-1 |
| REQ-9 | Field terminals in E1 | Lever push-in, UL 1059 ≥ 300 V / ≥ 20 A, 14–12 AWG Cu; one (L, N) input and three (OUTa, N, OUTb) receptacle feeds, all labelled | brief ("really easy to access", "shared inputs … outputs") | inspection |
| REQ-10 | Mains ↔ SELV | Reinforced everywhere. PCB creepage and clearance ≥ 8.0 mm; relay coil–contact reinforced; supply module Class II, 4.2 kVAC; field conductors kept out of the PCB/Pi compartment by MP1; hi-pot 3 kVrms for 60 s | UL/IEC 62368-1, IEC 60664-1 (C-8) | T-CREEP, T-HIPOT |
| REQ-11 | Opposite-polarity mains spacing (L or L_SWk to N; L_SWj to L_SWk) | creepage ≥ 6.4 mm, clearance ≥ 3.2 mm | UL 1059 use group C [S] | T-CREEP |
| REQ-12 | Mains copper to a board edge or mounting hole, where a bare EGC can lie | ≥ 6.4 mm (DRU `edge_clearance`, holes included) | UL field wiring 1/4 in to dead metal [S] | DRC |
| REQ-13 | Fail-safe OFF | All outlets OFF when the Pi is absent, unpowered, booting, rebooting, halted or hung; when its SD card fails; when the 5 V sags or fails; OFF ≤ 0.5 s after the last heartbeat edge, whether HB stops high or low; ON through heartbeat stalls ≤ 150 ms | revision-1 value restored (review N1): neither the brief nor a standard asks for faster, and 150 ms covers Linux GC, SD-writeback and Wi-Fi stalls [I] | T-BOOT, T-HB, T-BROWNOUT |
| REQ-14 | Two-key rule | No single stuck GPIO and no single shorted driver energizes an outlet while the heartbeat is absent | derived | FMEA (§4), T-HB |
| REQ-15 | Load on the Pi | ≤ 0.7 mA per CH pin; +3V3 ≤ 1 mA; only default-pull-down GPIOs | RPi docs GPIO pad table [P] | T-PWR |
| REQ-16 | Heartbeat | 3.3 V square wave 20 Hz–10 kHz, 20–80 % duty, from a high-priority thread that the control loop must pet (so a hung app still stops it) | C-4, wdsim.py | T-HB |
| REQ-17 | Coil voltage | ≥ 4.5 V at the relay pins in the worst case (also tested at 4.63 V) | must-operate [P]; C-3 | T-COIL |
| REQ-18 | Leakage at an OFF outlet | ≤ 0.1 mA (no snubber or MOV across the contacts) | C-12 | T-LEAK |
| REQ-19 | Thermal | E1 internal air ≤ 60 °C at a 40 °C room, with all coils on, 15 A through one outlet and the Pi at full load; Pi ambient ≤ 70 °C; IRM within its derating | C-6 | T-HEAT |
| REQ-20 | Fault withstand | Mains copper survives the breaker's let-through at ≤ 2 kA available; F1 can interrupt any fault at E1 | C-7, C-9 | T-SC |
| REQ-21 | Indicators | LED per channel (coil energized), ARM LED, 5 V LED; all SELV | task | T-FUNC |
| REQ-22 | Environment | Indoor dry, PD2, OVC III (conservative, review m7), ≤ 2000 m, room 0–40 °C | ASM-2 | — |
| REQ-23 | Parts | Active and orderable; relays, terminals, supply module, fuse, receptacles, enclosures and PCB laminate listed or recognized | brief ("reliable") | BOM review |
| REQ-24 | Installation | Licensed electrician; approval by the authority having jurisdiction (AHJ) | NEC 110.2/110.3 [I] | Q-1 |
| REQ-25 | Markings | Ratings, conductor size and strip length, terminal labels, "disconnect before opening", "outlets are not a disconnecting means", Pi orientation, "DO NOT CONNECT MICRO-USB POWER" at J5, and on the cover OUT1–OUT6 with "GFCI PROTECTED" and "SWITCHED OUTLET" | UL practice [I] | inspection |
| REQ-26 | Pi | Raspberry Pi Zero 2 W only, component side up on J5, with a 2×20 header soldered to its underside. No USB or HDMI peripherals. Powered only through J5 pins 2/4, never also from its micro-USB | Q-5 | inspection, T-PWR |
| REQ-27 | 5 V supply | Listed encapsulated AC/DC module fed from the shared L/N through its own fuse. The 5 V budget must fit its derated capacity | Q-5; C-2, C-9 | T-PWR, T-BROWNOUT |
| REQ-28 | Watchdog self-test | ARM_FB on BCM16. Software checks disarmed → armed → disarmed, with timing, at boot and whenever all outlets are off (at least daily). On failure it never arms, keeps every outlet off and raises an alarm | review M2 | T-SELFTEST |
| REQ-29 | Software | Read-only root filesystem (overlay); power-safe logging; all outlets OFF at boot; heartbeat from the control loop; documented power-restore policy (default OFF) | review M2; H17 | code review, T-BOOT |
| REQ-30 | Wi-Fi | PCB antenna inside a nonmetallic enclosure; antenna zone copper-free on all layers; ≥ 30 mm from relays, mains copper and the supply | C-13 | T-RF (RSSI ≥ −67 dBm at the install location) |
| REQ-31 | Compartments in E1 | Field wiring, receptacle leads and the receptacles themselves (north) are separated from the PCB/Pi by MP1, a vertical wall plus a flat sheet die-cut around J1–J4. North of the wall, PCB copper is allowed only under a terminal body or the MP1 sheet, and never between the board edge and the wire-entry faces. Conductors are tied down | review M3 | inspection |

## 3. Assumptions and open questions

| ID | Assumption | Why |
|---|---|---|
| ASM-1 | North-American dwelling or light commercial. One 120 V branch from a 15 A breaker. Available fault current at E1 ≤ 2 kA; ≥ 10 m of 14 AWG limits it to < 1 kA | Copper I²t (C-7); F1 has a 5× margin regardless (C-9) |
| ASM-2 | Indoor dry location, PD2, ≤ 2000 m, room 0–40 °C. E1 surface-mounted on a wall or backboard, not in an insulated cavity | Spacing tables and the heat budget |
| ASM-3 | Loads are plug-in appliances, LED or tungsten lighting, small motors. None is hazardous if left on, because a welded contact is a credible failure | H7 |
| ASM-4 | The Zero 2 W draws ≤ 0.6 A at full CPU load. Published measurements: 0.5 A (Geerling), 0.58 A (Tom's Hardware), "nearly 3 W" (Hackster) [S]. The budget allows 1.0 A | C-2 |
| ASM-5 | PCB laminate taken as material group IIIb (CTI ≥ 100 V) so the tables apply at their most conservative; FR-4 is usually IIIa [S] | C-8 |
| ASM-6 | A high-priority thread toggles HB at ≥ 20 Hz while the control loop pets it; whole-system stalls > 150 ms are rare enough that dropping the loads then is acceptable | C-4 |
| ASM-7 | The hardware keeps no output state: every Pi reboot or power cut leaves all outlets OFF | REQ-13 |
| ASM-8 | The Zero 2 W antenna is on the connector edge between the mini-HDMI and the USB socket. That is where the Zero W has it [S], and the Zero 2 W underside silkscreen ("uses antenna technology licensed from Proant AB") sits there [V, photo]. Not confirmed in a drawing | Antenna keepout (§5.2, §9) |

| ID | Question for a human | Blocking? | Default / answer |
|---|---|---|---|
| Q-1 | Certification path. This unlisted assembly is permanently installed, which needs AHJ approval (probably a field evaluation). Who evaluates it, and who installs it (licensed electrician)? If neither is acceptable, buy listed products. | **BLOCKING** | open |
| Q-2 | Outputs: field terminals, or receptacles in the box? | answered | user decision, section 1 |
| Q-3 | Where does the Pi live, and how is it powered? | answered | user decision, section 1 |
| Q-4 | How many channels, and in what box? | answered | user decision, section 1 |
| Q-5 | Which Pi, and what powers it? | answered | user decision, section 1 |
| Q-6 | Branch protection. Is a 15 A dual-function AFCI/GFCI breaker acceptable? GFCI is required in kitchens, baths, garages, basements, laundry and outdoors; AFCI in most dwelling rooms. A 20 A circuit must be re-breakered at 15 A (12 AWG is fine on 15 A). | **BLOCKING** | 15 A dual-function breaker |
| Q-7 | Load list. Are any loads heaters, pumps, compressors or life-safety equipment, i.e. unsafe if a contact welds? Motors cycled more than about 5 times a day should drive a contactor (C-10). | **BLOCKING** | general plug loads |
| Q-8 | One enclosure, or two boxes (electronics enclosure next to a receptacle box)? | answered | "One enclosure": a single larger listed non-metallic enclosure with the six switched receptacles (3 split-tab TR duplex) mounted in its lid/face and the relay board, Pi Zero 2 W and IRM-20-5 inside |
| Q-9 | Partition MP1: confirm 1.5 mm polycarbonate UL 94 V-0, the fixing, and AHJ acceptance. | no | as specified |
| Q-10 | Watchdog semantics: OFF when the control app hangs (software heartbeat), or ON through app hangs (hardware-PWM heartbeat)? | no | software heartbeat |
| Q-11 | Power-restore policy: outlets stay OFF after a power cut, or the app restores the last state after its self-test? | no | stay OFF |
| Q-12 | Surge protection: a listed Type 2 SPD at the panel instead of an MOV in the box (C-11)? | no | no MOV in the box |
| Q-13 | Relay supply (Omron → Aratas, long lead time): qualify the second source. | no | G5RL-1A-E-HR, TV-5 limit |
| Q-14 | Pi header: the user solders a 2×20 header to the Zero 2 W's underside. A Zero 2 WH (header on top) would have to sit face-down, which mirrors the pinout, so it is not supported. | no | solder on the underside |
| Q-15 | Generic hardware (nylon standoffs, NM connectors, wallplate, EGC splice, SD card) still needs MPNs. | no | specs in the BOM |
| Q-17 | Receptacles in the cover on a machined subplate (MP4) are not a listed device-mounting method. Accept through the AHJ field evaluation (Q-1), or have a UL 508A shop build and list the assembly as an industrial control panel? NEC 406.5 wants receptacles in boxes or assemblies designed for the purpose [S], and the field-cut opening ends the Type 4X/12/13 rating: the enclosure is then used as an indoor dry-location (Type 1) enclosure only [I] | **BLOCKING** | field evaluation with Q-1 |
| Q-16 | Add per-channel readback, which would detect a shorted channel MOSFET? It costs 6 GPIOs and 18 parts. | no | no; the channel LED shows it |

## 4. Hazards and failure modes

| ID | Hazard | Mitigation | Implemented by | Survives a single fault? |
|---|---|---|---|---|
| H1 | Shock with the cover open (the user opens it to service the Pi) | Screw cover (tool needed); "disconnect before opening" label. With the cover off only SELV/Pi parts are touchable: clear IP2X shield MP16 over F1, relay contacts, PS1 AC pins and line copper; receptacle backs shrouded on MP4; WAGO lever terminals finger-safe [I]; MP1 keeps field conductors away; stranded-lead service loop | MP1, MP2, MP4, MP16 | **Yes** for touch (IP2X guards); the guards are removed only with tools for mains work (review N2) |
| H2 | Mains reaches SELV, the Pi, or a person touching the Pi | Reinforced insulation everywhere it is needed: IRM Class II, 4.2 kVAC [P]; relays 8/8 mm, 6 kVAC, 10 kV [P]; PCB 8/8 mm band; MP1 adds supplementary insulation over the field conductors' basic insulation; no SELV wiring leaves E1 | K1–K6, PS1, layout, MP1 | **Yes** (reinforced = double) |
| H3 | A bare EGC or receptacle yoke touches live copper | Nonmetallic enclosures, so there is no box metal; EGCs spliced in the wire compartment with a listed connector; mains copper ≥ 6.4 mm from board edges and holes (DRU edge rule); copper north of MP1 lies under a terminal body or the MP1 sheet | J1–J4, MP1, MP15 | **Yes** |
| H4 | Overload heats conductors, PCB, terminals, relays or receptacles | One protective device, the 15 A breaker; every downstream element rated ≥ 15 A at temperature (C-7, C-9) | breaker, K1–K6, J1–J4, MP5–MP7 | **Yes**; 15–20 A overloads tested in T-OL |
| H5 | Short circuit on an outlet or in the module | The breaker clears outlet faults (copper I²t margin 1.4× at 2 kA). F1 (1 A T, 10 kA at 125 VAC) clears a module fault first. The UL 50 enclosure contains the arc | J1–J4, F1, MP2 | **Yes** |
| H6 | Loose or partially inserted conductor heats up | Spring clamps (no torque relaxation); strip length on the silkscreen; pull test at commissioning; receptacles back-wired under clamp plates, never push-in | J1–J4, MP5–MP7 | **No**: inspection is the barrier |
| H7 | Fail-ON from a welded contact | Inrush-rated relay (TV-8, 100 A peak); load limits (REQ-5); no snubber; warning that outlets are not for loads hazardous if left on | K1–K6 | **No**: residual risk, disclosed (Q-7) |
| H8 | Fail-ON from control: software bug, hung Pi, stuck GPIO, shorted MOSFET | Coil current needs both Qk (CH GPIO) and Q7 (U1 monostable); 4.7 kΩ pull-downs; HB is edge-triggered | Q1–Q7, U1, R21, C6, R22, R7–R12 | Hung software, stuck GPIO or shorted Q7: **yes** (the other key still blocks; a Q7 short is caught by the self-test). Shorted Qk while HB runs: **no**. Outlet k follows ARM; its LED shows it; stopping HB turns it OFF |
| H9 | Glitch to ON at boot, reset or power-up | Default-pull-down GPIOs plus 4.7 kΩ / 100 kΩ pull-downs; U1 has a glitch-free power-up reset [P]; arming needs rising edges on B; R22 holds Q7 off while U1 is unpowered (its output is high-Z under Ioff [P]) | U1, R22, R23, R7–R12 | **Yes** |
| H10 | Remote energization while a load is serviced | Label: outlets are not a disconnecting means; unplug the load or lock out the breaker | labels | **No** (procedural) |
| H11 | Shock from an "OFF" outlet | No snubber or MOV across the contacts (C-12); line-only switching; polarity check with a receptacle tester at commissioning | K1–K6, T-MISWIRE | Leakage: yes. L/N swapped: **no** (procedural) |
| H12 | Overtemperature in the closed enclosure | 15.5 W worst case into 0.34 m² of polycarbonate gives 49 °C air at a 40 °C room (C-6); surface mounting; 12 A continuous limit | MP2, PS1 | **Yes** with margin |
| H13 | Surge flashover or arc tracking | OVC III spacing; relays 10 kV impulse; IRM tested to 2 kV L–N [P]; no MOV in the box; panel SPD recommended | K1–K6, PS1 | **Yes** |
| H14 | Pi fitted wrongly (face-down Zero 2 WH, or offset a row), putting 5 V on GPIO pins | Zero 2 W only, header on its underside; J5 footprint uses the Pi's own top-view pin numbering; Pi outline, "components up" and pin-1 marks on the silkscreen; a face-down Pi does not line up with the standoffs | J5, MP9, MP10 | **No**: assembly error, caught by inspection before power-up |
| H15 | Motor stall on an outlet | The motor's own overload protection (NEC 430); 1/2 hp relay rating; contactor for larger motors | user | n/a |
| H16 | Supply module fails: output lost, output high, or input short | Output lost: the coils drop and the Pi stops, so all OFF. Output high: module OVP 5.75–6.75 V shuts it off [P], TVS D15 clamps, coil max 6.5 V. Input short: F1 opens. A Pi-side short: PTC F2 limits it | PS1, F1, F2, D15 | **Yes** for the outlets (all OFF). An OVP event (5.75–6.75 V) can exceed the Pi PMIC's 6.5 V abs max [S] and destroy the Pi: equipment damage, accepted (review m1) |
| H17 | Pi reboot, kernel hang or SD-card corruption leaves outlets in an unknown state | Any stop of HB disarms in ≤ 0.36 s (C-4). A Pi that cannot boot never arms. A read-only rootfs makes corruption unlikely (REQ-29). The self-test runs before arming (REQ-28) | U1, Q7, R24, R25, D16 | **Yes** |
| H18 | A watchdog part fails so the outlets arm without a heartbeat | ARM_FB readback and the self-test catch it (FMEA below) | U1, R21, C6, Q7, R22, R24–R26, D16 | **Yes** |
| H19 | Ground fault in a plugged-in load | GFCI protection of the branch (REQ-2, Q-6); EGC to every receptacle. Module leakage 0.12 mA ≪ the 4 mA no-trip level | MP5–MP7, breaker | **Yes** (GFCI is upstream) |

**Watchdog FMEA (review M2).** The self-test sequence (REQ-28), with all CH low:

1. Stop HB for ≥ 100 ms. Expect ARM_FB high ("disarmed").
2. Toggle HB at 50 Hz. Expect ARM_FB low within 20 ms ("armed").
3. Stop HB. Expect ARM_FB high again within 150–345 ms (tw window, C-4).

| Part | Failure | Effect | Detected by | Outcome |
|---|---|---|---|---|
| U1 | Q stuck high | Q7 always on: one key lost | Steps 1 and 3 read "armed" | Software never drives CH; outlets OFF; alarm |
| U1 | Q stuck low, or no VCC | Cannot arm | Step 2 fails | Safe (OFF) |
| R21 (1 MΩ) | Open | C6 never recharges, so Q stays high | Step 3 never disarms | Refuse; safe |
| R21 | Short (Rext/Cext tied to VCC, outside the datasheet) | Undefined timing | Step 2 or 3 fails | Refuse; safe |
| C6 (220 nF) | Open, or value collapsed | tw ≈ ns, so Q7 hardly conducts | Step 2 fails, or ARM_FB pulses | Safe (cannot hold coils) |
| C6 | Short | Timing never ends, so Q stays high | Step 3 | Refuse; safe |
| C6 | Value drifts high | Disarm too slow | Step 3 timing > 345 ms | Refuse |
| Q7 | Drain–source short | Always armed | Step 1 reads "armed" | Refuse; outlets OFF |
| Q7 | Open, or gate–source short | Cannot arm | Step 2 | Safe |
| R22 (100 kΩ) | Open | Q7 gate floats only while U1 is unpowered (Pi absent), and then every CH is pulled low | none (latent) | Single-fault safe: the CH key holds |
| R23 (100 kΩ) | Open | B floats only while the Pi is absent | none (latent) | Benign |
| R24 (47 kΩ) | Open | ARM_FB always low | Step 1 | Refuse; safe |
| R25 (68 kΩ) | Open | ARM_FB always high (clamped) | Step 2 | Refuse; safe |
| R26 (10 kΩ) | Open | Disarmed level set by the LED path only (~1.7–2.0 V) | May fail step 1 | Refuse, or no effect (R26 only sets a level) |
| D16 | Either diode shorts | ARM_FB stuck at GND or +3V3 | Steps 1 or 2 | Refuse; safe |
| Qk | Drain–source short | Outlet k follows ARM | LED k lit while CHk is low (visual only) | H8 residual; OFF when HB stops |
| Dk (flyback) | Open | Coil spike avalanches Qk, which may then short | none | As the Qk short |

## 5. Trade studies

### 5.1 Switching element (unchanged from revision 1)

Criteria (score 1–5) and weights: **S** safety and failure mode (30), **T** heat in a closed box (20),
**L** load compatibility (15), **O** OFF-state isolation (10), **C** UL parts and certification path
(10), **X** complexity and cost (10), **B** fit to the brief (5).

| Alternative | S | T | L | O | C | X | B | Weighted /5 |
|---|---|---|---|---|---|---|---|---|
| **A1 PCB relays with reinforced insulation (G5RL TV-8), MOSFET drivers, watchdog** | 4 | 5 | 4 | 5 | 4 | 4 | 5 | **4.35** |
| A2 Zero-cross triac SSRs | 2 | 1 | 3 | 1 | 4 | 3 | 3 | 2.20 |
| A3 MOSFET AC SSRs | 2 | 2 | 3 | 3 | 2 | 2 | 3 | 2.30 |
| A4 Hybrid relay plus triac | 3 | 4 | 5 | 2 | 2 | 1 | 4 | 3.15 |
| A5 Listed products (RIB relays, Digital Loggers IoT Relay) | 5 | 4 | 4 | 5 | 5 | 2 | 2 | 4.20 |

Why the others lose:

- **Triacs (A2):** 15–20 W per channel, they fail shorted, and they leak mA when OFF.
- **MOSFET SSRs (A3):** 5–9 W per channel, and they also fail shorted.
- **Hybrid (A4):** it adds a fail-ON path and a second barrier crossing.
- **Listed products (A5):** the safest path, offered under Q-1.

Six relays dissipate 2.8 W of coil power, which the heat budget absorbs (C-6).

### 5.2 Enclosure and Wi-Fi

The Pi's PCB antenna rules out a metal box. A steel box attenuates 2.4 GHz by more than 30 dB [I],
and an external antenna would mean cutting a trace on the Pi and fitting a U.FL connector
(a board modification outside its FCC grant 2ABCB-RPIZ2 [V, board silkscreen]). So the
electronics enclosure must be nonmetallic.

| Option | Holds 3 duplexes + board + Pi + supply? | Listed for this use | Wi-Fi | Heat | Verdict |
|---|---|---|---|---|---|
| Steel 4-11/16" box (revision 1) | No | yes | blocked | 4 W limit | out (Q-4) |
| 4-gang PVC device box (Carlon B468R, 71 in³ [S]) | No: the board does not fit beside three devices, and 314.16 fill is exceeded | for devices and NM cable | good | small area | out |
| Large PVC junction box (Carlon E989N-CAR 8 × 8 × 4 in, NEMA 6P [S]) | Only 8 × 8 in: the 3-gang block plus the board and the partition do not fit; screw cover too small for the opening | junction box | good | ok | out |
| Revision 2: NS1086 + separate 3-gang BH353A box | Yes, each box used as listed | yes | good | 52 °C | superseded by the user's Q-8 decision |
| Listed polycarbonate kits with duplex outlets on the inner plate (e.g. Transtector TEPC181610-100-UL [S]) | Receptacles are inside, reachable only with the lid open | yes | good | ok | out: loads must plug in with the box closed |
| **NS14126 (14 × 12 × 6 in, UL 50 Type 4X/12/13, back panel JP1412P 12.75 × 10.88 in [P catalog]); receptacles in a 3-gang opening of its cover** | Yes | enclosure yes; receptacle mounting in the cover **no** (Q-17) | < 1 dB [I] | 49 °C (C-6) | **chosen** |

No listed nonmetallic enclosure with device openings in its cover was found (searches of Carlon,
Fibox, Hammond, Allied Moulded and NEMA-kit makers [S]). The chosen construction is the usual
UL 508A control-panel practice: a listed enclosure, field-cut, carrying listed devices.

**How the receptacles mount.**

- **Cover opening.** A rectangular cut-out matching the opening of a standard 3-gang duplex wallplate, centred about 75 mm below the top wall.
- **Subplate MP4.** A 6.4 mm polycarbonate (UL 94 V-0) plate behind the cover, held by six nylon-insulated through-bolts. Brass heat-set 6-32 inserts sit at standard yoke spacing (3-9/32 in screw centres, 1-13/16 in gang pitch); no thread is cut in the plastic, so plug forces cannot strip it (review N3). The receptacle yokes screw to the inserts, and the nylon wallplate (MP8) clamps the cover from outside, as on a wall box. A 1.5 mm polycarbonate rear shroud closes over the receptacle backs, with the leads leaving through a strain-relief grommet, so the energized backs are finger-safe when the cover is off.
- **Enclosure rating.** The field-cut opening ends the NS14126's Type 4X/12/13 rating [I]; it is used as an indoor dry-location (Type 1) enclosure only, which ASM-2 already assumes. NEC 406.5 wants receptacles in "boxes or assemblies designed for the purpose" [S], so the AHJ or a UL 508A shop must accept the assembly (Q-17).
- **Grounding.** Nothing on the cover is metal except the yokes. Each yoke's green screw gets a 14 AWG green pigtail to the EGC splice (NEC 250.146 [S]; nonmetallic enclosure, so no box bonding).
- **Wiring.** Each receptacle gets black (top outlet), red (bottom outlet) and white leads, 14 AWG UL 1015 600 V 105 °C fine-stranded (Class K) copper, with ferrules at the WAGO end, to its 3-pole terminal (J2–J4). Solid wire would fatigue in the flexing loop (review N3). The nine leads plus three stranded green pigtails run in spiral wrap with a 300 mm service loop, strain-relieved at the shroud grommet and tied to the back panel north of MP1, so the cover can be removed and laid aside without stressing a terminal. With the cover off, the shrouded receptacles hang on these leads; that is part of the Q-17 package.
- **Separation.** The receptacle block (backs reach about 40 mm into the 152 mm depth) sits above the north (field-wiring) compartment. Its terminals, the leads and the field conductors all stay north of the MP1 wall, which runs from the PCB to the cover. The Pi is in the south-west corner, ≥ 150 mm from the nearest receptacle terminal.

**Arrangement (front view, cover removed; receptacles shown dashed where the cover carries them):**

```
   branch cable (14/2 or 12/2 NM-B) in through the top wall                     E1 NS14126, 14.4 x 12.4 x 6.5 in
   +------------------------------------------------------------------------------------------+
   |  EGC splice   lead bundle (spiral wrap, 300 mm loop)                                      |
   |              .- - - - - - - - - - - - - - - - - - .                                       |
   |              ' [TR5252 A]  [TR5252 B]  [TR5252 C] '  <- in the cover, 3-gang opening       |
   |              '  OUT1/OUT2   OUT3/OUT4   OUT5/OUT6 '     (subplate MP4, nylon wallplate)   |
   |              '- - - - - - - - - - - - - - - - - - '                                       |
   |        +---------------------------- board 200 x 150 ---------------------------+         |
   |        | [J2 OUT1|N|OUT2] [J3 OUT3|N|OUT4] [J4 OUT5|N|OUT6]      [J1 L|N]        |         |
   |   =====|======== MP1 partition wall + sheet (1.5 mm PC, PCB to cover) ===========|=====    |
   |        | L bus, F1          K1 K2 K3 K4 K5 K6               PS1 IRM-20-5          |         |
   |        | - - - - - 8 mm copper-free barrier band (under relays and PS1) - - - - - |         |
   |        | Q/D/LED per channel     U1 Q7 readback        C1-C3 D15 F2               |         |
   |        | [ Pi Zero 2 W on J5 ]  antenna zone at the south board edge             |         |
   |        +--------------------------------------------------------------------------+         |
   +------------------------------------------------------------------------------------------+
```

The board sits on 6 × M3 × 12 mm nylon standoffs on the PVC back panel. The Pi is 11 mm above the
board on nylon standoffs, so the cover faces its component side and antenna. Wi-Fi
range indoors is that of a bare Zero 2 W less about 1–3 dB [I]: typically 10–20 m through one or two
interior walls. REQ-30 sets the acceptance test (RSSI ≥ −67 dBm where it is installed). If that fails,
move the access point or add a mesh node. Do not modify the Pi.

### 5.3 Power conversion (the Zero 2 W powered from the box's 120 VAC)

| Option | Insulation and listing | 5 V at 70 °C, 108 VAC | Size | Heat at 5.8 W out | Effort and risk | Verdict |
|---|---|---|---|---|---|---|
| **M1 Mean Well IRM-20-5** | Class II, 4.2 kVAC I/P–O/P, UL/IEC 62368-1 (OVC II), IEC 61558-2-16 (OVC III), LPS [P] | 1.9 A (4 A × 50 % × 95 %) [P curves] | 52.4 × 27.2 × 24 mm | 1.8 W | Low: a potted, certified part; KiCad symbol and footprint exist | **chosen** |
| M2 IRM-10-5 | same family [P] | 0.95 A (2 A × 50 % × 95 %) | 45.7 × 25.4 × 21.5 | 1.9 W | Low | out: below the 1.57 A budget when hot |
| M3 IRM-15-5 | same family [P] | 1.42 A (3 A × 50 % × 95 %) | same case as IRM-20 | 1.8 W | Low | out: below the budget at 70 °C (fits at 60 °C) |
| M4 RECOM RAC20-05SK | similar class [unverified] | not evaluated | different footprint | — | Medium (no KiCad footprint) | second source to study |
| M5 Hi-Link HLK-10M05 class | listing not verifiable [I] | — | small | — | Low cost, unknown insulation | out (cannot show reinforced + listing) |
| M6 Discrete offline flyback (e.g. a TinySwitch/LinkSwitch with a triple-insulated-wire transformer) | We would have to prove reinforced insulation across the transformer, the optocoupler and the Y-cap, plus EMI and surge, by our own testing; no listing | as designed | larger | similar | High: about 25 parts and a certification test campaign | out (the default rule: a module unless a discrete design can be shown to meet reinforced insulation and listing; it cannot here) |
| M7 A listed USB wall adapter plugged into an internal receptacle | listed Class II | ok | bulky, plus a cord | similar | Medium; consumer part, uses an extra receptacle | out |

**The chosen supply branch, from the line terminal to the Pi:**

- **Input fuse F1.** Littelfuse 0326001.MXP: 1 A, 250 VAC, 3AB 6.3 × 32 mm ceramic time-lag, in two PCB clips. It interrupts 10 kA at 125 VAC [S, distributor listings; the Littelfuse datasheet could not be opened, see Q-15]. At 60 °C it runs at 67 % of rating (C-9). Its time lag rides through the module's 20 A typical cold-start inrush [P].
  - The IRM block diagram shows no internal fuse [P], so F1 is needed.
  - A 5×20 Littelfuse 215 (1500 A at 250 VAC [P]) was rejected: 1.5 kA is not a safe margin at a 120 V branch. KiCad has no enclosed 6.3 × 32 holder, so the open clips stay and the IP2X shield MP16 covers them (review N2); replacing F1 means removing the shield, which is mains work.
  - **Rating at 132 V (review m2).** The 10 kA rating is stated at 125 VAC [S]. NEC 110.9 compares interrupting ratings at the nominal circuit voltage, 120 V [I], and the fuse's voltage rating is 250 V; the Littelfuse 326 data sheet (Q-15) must confirm this before release.
- **Surge and EMI.** The module meets EN 55032 class B and EN 61000-4-5 level 4 (2 kV L–N) without external parts [P], so there is no MOV and no filter (C-11).
- **Hold-up and brown-out.**
  - Hold-up is 8 ms at full load and 115 VAC [P], or about 27 ms at our 5.8 W [I], so a one-cycle dropout rides through.
  - Below 115 VAC the output derates (80 % at 85 VAC [P]). Longer sags reset the Pi or collapse 5 V. In either case HB stops, Q7 opens within 0.36 s, and every outlet goes OFF.
  - A coil whose 5 V sags below hold voltage releases by itself.
  - Restart takes the module's 1 s setup [P] plus the Pi's boot. The outlets stay OFF until the software has passed its self-test (Q-11).
- **Output protection.**
  - The module's own protections: overload hiccup at 115–160 % [P] and OVP at 5.75–6.75 V (shut-off plus zener clamp) [P].
  - D15 (SMAJ7.0A) clamps transients on +5V.
  - F2 (MF-MSMF200/16X, 2 A hold, 1.48 A at 60 °C [P]) limits a Pi-side short. The Zero 2 W has no fuse of its own: its micro-USB VBUS goes straight to its 5 V rail, with 47 µF [P, reduced schematic].
- **5 V budget (C-2).**
  - Pi allowance 1.0 A. That is measured ≤ 0.6 A plus Wi-Fi bursts and margin; the RPi docs list 350 mA typical and recommend a 2 A PSU, which covers USB peripherals we do not use [P].
  - Six coils at 5.125 V on 56.25 Ω: 0.547 A.
  - Eight LEDs: 17 mA. U1 and the dividers: about 2 mA.
  - Total **1.57 A**, which is 82 % of the derated 1.9 A at 70 °C and 108 VAC, and 59 % at the expected 60 °C.
- **Back-feed.** J5 pins 2 and 4 carry +5V_PI into the Pi's 5 V rail, which bypasses nothing because the Zero 2 W has no input protection. At 1 A the Pi sees ≥ 4.775 V, above the ~4.63 V under-voltage threshold [S] (C-2). The Pi's micro-USB must stay unused (REQ-26).
- **What the M4 (Class 2) finding now rests on.** No Class 2 wiring leaves E1, so NEC 725 no longer applies. The safety of the SELV side rests on four things:
  1. PS1's certified reinforced (Class II) input–output insulation and its LPS output [P]. Its UL file number is to be confirmed in UL Product iQ as part of Q-1.
  2. The relays' reinforced coil–contact insulation [P].
  3. The PCB's 8/8 mm band (C-8).
  4. MP1 as supplementary insulation against field conductors.

  The SELV floats. Its touch current to earth through the module's Y-capacitance is ≤ 0.12 mA (C-12).

### 5.4 Mounting the Zero 2 W

All mechanical data comes from the Raspberry Pi Zero 2 W mechanical drawing and product brief [P]:

- The board is 65 × 30 mm.
- Four Ø2.75 mm holes sit 3.5 mm from each edge, at 58 × 23 mm centres.
- The 40-pin header is centred on the long edge (32.5 mm from the SD-card end), with its row centre 3.5 mm from that edge. Pin 1 is at (8.37, 4.77) mm in top view.
- The mini-HDMI, USB and PWR connectors are on the opposite long edge (centres at 12.4, 41.4 and 54 mm).
- The SD card is at the left end.
- Operating range is −20…+70 °C.

| Option | Pin mapping on our board | Heat | SD access | Antenna | User work | Verdict |
|---|---|---|---|---|---|---|
| **Pi component side up, header soldered to its underside, plugged into J5** | same as the Pi's top view (KiCad PinHeader handedness) | SoC faces the lid | SD at the west end, reachable | faces the lid, ≥ 11 mm above a copper-free zone | solder 40 joints (Q-14) | **chosen** |
| Zero 2 WH face-down onto a mirrored socket | mirrored | SoC traps heat against the board | removal needed | faces the board | none | out: a mirrored footprint invites a 5 V-on-GPIO error (H14) |
| Pi on a cable or off-board | — | — | — | — | — | out (Q-3 answer) |

**Mounting stack.**

| Item | Part | Height |
|---|---|---|
| Socket J5 on our board | Sullins PPPC202LFBN-RC, 2×20, 8.51 mm insulator, gold, 3 A per contact [S] | 8.51 mm |
| Header on the Pi's underside | 2×20 male, 2.54 mm insulator, e.g. Sullins PRPC020DAAN-RC [I] | 2.54 mm |
| Pi underside above our board | standoffs: 4 × M2.5 × 11 mm nylon in H7–H10 | **11.05 mm** |

The J5 footprint is custom (`custom:RPi_Zero2W_Socket_2x20_P2.54mm`). It uses the Pi's own top-view
numbering: pin 2 on the edge row, north of pin 1. This is the KiCad *PinHeader* handedness. KiCad's
*PinSocket* footprint assumes a board flipped face-down and would mirror the pins. The footprint draws
the Pi outline (also its courtyard, so nothing else sits under the Pi) and carries the antenna rule
area.

### 5.5 Watchdog (review M1, m1)

| Option | Disarm, HB stuck high | Disarm, HB stuck low | Gate drive at the 2.5 V spec point | Readback | Verdict |
|---|---|---|---|---|---|
| Rev 1 charge pump (R14 1 MΩ, C4 100 nF) | ≈ 1.6 s (reviewer's simulation): C3 discharges with C4 through R14 | 0.15 s | 2.56 V nominal, 2.1 V at V_OH 2.6 V (m1) | none | out |
| Pump + 100 kΩ PUMP→GND (reviewer fix 1) | 0.15 s | 0.15 s | 2.62 V | add-on | possible |
| Pump with C3 = 100 nF (reviewer fix 2) | 0.28 s | ≈ 0.15 s | 2.61 V | add-on | possible |
| Dedicated window watchdog (e.g. TPS3430) | set by the window | set by the window | needs an extra gate driver | add-on | out: more parts, open-drain output |
| 74LVC1G123, rev 2/3 values (330 kΩ, 100 nF, tw 25–46 ms) | ≤ 61 ms | ≤ 61 ms | push-pull | Q7 drain | out: heartbeat gaps of 30–50 ms drop every outlet, and 22–40 Hz chatters (review N1) |
| **74LVC1G123, R21 1 MΩ, C6 220 nF (tw 150–340 ms)** | **≤ 0.36 s** | **≤ 0.36 s** (edge-triggered: levels cannot hold it) | push-pull V_OH ≥ 3.0 V | Q7 drain on BCM16 | **chosen** |

**How the 74LVC1G123 is wired.**

- U1 runs from the Pi's 3.3 V (J5 pins 1/17). A is tied to GND and CLR to +3V3, so only a rising edge on B (HB) triggers it [P, Table 4-1].
- Q drives Q7's gate directly.
- tw = K·R21·C6, with K = 1.0–1.1 at 3.3 V [P, read at 10 kΩ / 0.1 µF] and R21 = 1 MΩ, C6 = 220 nF 50 V X7R (Yageo CC0603KRX7R9BB224). Over tolerance, temperature and the ±0.25 µA Rext/Cext leakage (±10 % at 1 MΩ [I]), tw is **150–340 ms** (C-4).
- HB comes from a high-priority thread (e.g. `SCHED_FIFO`) that the control loop must pet each cycle, so app hangs still stop it but scheduler noise does not.
- The power-up reset is glitch-free [P]. When U1 is unpowered its output goes high-Z [P, Ioff], so R22 (100 kΩ) holds Q7 off.
- Q7's drain is read back through a 47 k/68 k divider with a 10 kΩ pull-up (R26), clamped by a BAT54S to GND and +3V3.
- The Pi's own kernel watchdog (`dtparam=watchdog=on`, systemd `RuntimeWatchdogSec`) is recommended as well: it reboots a hung kernel. It is not part of the safety case, because a hung Pi already stops HB.

**Channel gates (m1).** The channel gate network is now 100 Ω in series with a 4.7 kΩ pull-down.
The Zero 2 W's GPIO gives V_OH ≥ 3.0 V at 2 mA [P, RP3A0 table]. That puts **2.94 V** on the gate when
driven, and 0.28 V if software enables the internal 50 kΩ pull-up by mistake.

### 5.6 Receptacles

- **Tamper-resistant (NEC 406.12).** The Pass & Seymour TR5252 is a TR, spec-grade NEMA 5-15R duplex with back and side wiring. Its line-side tab breaks off for split-circuit wiring [S].
  - Breaking the brass-side tab gives two individually switched outlets that share one neutral; each receptacle gets black, red and white 14 AWG leads from its terminal block.
  - Back-wire clamps are used, never push-in backstabs (H6).
- **GFCI (NEC 210.8).** No split-tab GFCI receptacle exists: a GFCI device protects both of its outlets as one, and its load terminals would sit downstream of the relays. GFCI protection is therefore upstream (REQ-2, Q-6).
  - The default is a 15 A dual-function AFCI/GFCI breaker. It also covers AFCI (210.12) for outlets in dwelling rooms.
  - A dead-front GFCI in its own box upstream is the alternative.
  - The module's leakage (≤ 0.12 mA at 132 V) and the relays (no snubbers) cannot trip a GFCI.
- **15 A vs 20 A (NEC 210.21(B)(3)).** 15 A receptacles on a 15 A branch are correct. On a 20 A branch, 15 A duplexes would be permitted, but the relays (16 A) and the PCB copper are designed for a 15 A breaker. A 20 A circuit must therefore be re-breakered at 15 A (Q-6).
- **Per-outlet fusing.** Not used. Every element downstream of the breaker is rated ≥ 15 A at temperature: 15 A receptacles, 16 A relays, 31 A terminals, and copper with a 1.4× I²t margin.
  - Six fuses would add about 1 W each at 12 A and would be unserviceable failure points behind a cover.
  - The sum of all six outlets is limited by the same 15 A breaker (REQ-6). The software can also cap concurrent loads, but that is not part of the safety case.
- **Grounding.** EGC pigtails go to each receptacle's green screw. The enclosure is nonmetallic, so there is no box bonding. The receptacle yokes are PE.

### 5.7 Options decided

| Option | Decision | Reason |
|---|---|---|
| Discrete MOSFET drivers | in (AO3400A) | A ULN2803 drops up to 1.1 V, leaving the coil below must-operate (C-3) |
| Flyback diode only, no Zener (m6) | diode only | AC loads extinguish their arc at current zero, so faster release gains little. Release with a diode is allowed 15 ms in the disarm budget, measured in T-HB |
| Status LEDs | in | Commissioning with mains OFF |
| HAT ID EEPROM | out | ID_SD/ID_SC left open, as the Pi docs require without an EEPROM |
| Per-channel readback | out (Q-16) | The LEDs show a shorted Qk; a weld cannot be removed by detecting it |
| MOV, snubbers | out | C-11, C-12 |
| Fuses per outlet | out | §5.6 |
| External SELV cable, ESD array, PTC on a cable | removed | No SELV wiring leaves E1 any more |

## 6. Blocks, domains and barriers

| Block (sheet) | Function | Parts | Ports |
|---|---|---|---|
| mains_in | Shared input, supply fuse, AC/DC module | J1, F1, PS1 | L_IN, N (15 A, external); L_PSU (0.6 A); +5V, GND out |
| power5 | 5 V rail | C1–C3, D15, D14, R20, F2, TP1, TP2 | +5V (1.6 A); +5V_PI (1.0 A) |
| pi | Pi socket | J5, C4, C5, TP6 | +5V_PI in; +3V3 out (≤ 1 mA); CH1–6, HB out; ARM_FB in |
| arm | Watchdog, arming switch, readback | U1, R21, C6, C7, R23, Q7, R22, D13, R19, R26, R24, R25, D16, TP3–TP5 | HB in; COIL_RTN (0.55 A); ARM_FB out |
| ch1…ch6 | Coil drive and indication | Kk, Qk, Dk, D(k+6), Rk, R(k+6), R(k+12) | CHk (0.7 mA); +5V (93 mA); COIL_RTN; L_IN in, L_SWk out (15 A) |
| outlets | Receptacle feeds | J2, J3, J4 | L_SW1–6, N (external) |
| mech | Holes; BOM-only items | H1–H10, MP1–MP16 | — |

| Domain | Nets | Reference | Range | Notes |
|---|---|---|---|---|
| LINE (root) | L_IN, L_PSU | L_IN (0 V) | 0 V by definition; 187 V pk to N; OVC III transient 2.5 kV | `edge_clearance` 6.4 mm (board edges and holes H1–H10) |
| NEUTRAL | N | L_IN | ±187 V pk | not switched |
| OUT1…OUT6 | L_SW1…L_SW6 | L_IN | 0 when closed; ±187 V pk when open | state-dependent |
| PE | (off-board) EGCs, receptacle yokes | earth | 0 V | no PCB copper |
| SELV (root) | +5V, +5V_PI, +3V3, GND, CHk, CHk_G, COILk, LEDk_A, COIL_RTN, HB, ARM_G, WD_RC, WD_CX, ARM_FB, LED_ARM_A, LED_PWR_A | GND | 0–5.25 V (COIL ≤ 6.1 V in flyback) | ES1, LPS, floating (Class II supply) |

L_PSU (after F1) equals L_IN while F1 conducts. With F1 open, PS1 pulls it somewhere between L and N.
It is modelled at L_IN's potential, so PS1 is checked against the true L–N voltage, and the open-fuse
voltage across F1 is a calc (`f1_open_voltage_ratio`).

Barrier table (PD2, MG IIIb, OVC III). Every barrier is declared `ac=True`: Uw is a 187 V peak, and the
checker scales the parts' Vrms working ratings by √2 before comparing (relays 250 Vrms, PS1 305 Vrms). The
relay's own mould is MG IIIa (PTI 250 [P]); the board is still taken as IIIb.

| Pair | Grade | Uw | Required creepage / clearance (source) | Design | Slot |
|---|---|---|---|---|---|
| SELV ↔ LINE (covers NEUTRAL and OUT1–6) | reinforced | 120 V rms | creepage 3.0 (2 × F.4 125 V MG III [I]); clearance 3.0 (60664-1 F.2, 4 kV) / 3.8 (62368-1 T10) [P via SLUP419] | **8.0 / 8.0** (relay's own 8/8 mm) | no |
| LINE or OUTk ↔ NEUTRAL | functional | 120 | UL 1059 group C: 6.4 / 3.2 [S] | 6.4 / 3.2 | no |
| OUTj ↔ OUTk | functional | 120 | as above | 6.4 / 3.2 | no |
| LINE ↔ OUTk (open contact) | functional | 120 | IPC-2221B B2 1.25 [S]; 2.5 kV clearance 1.5 / 1.8 | 2.5 / 1.5 outside the relay footprint; the relay pin pitch (5.0 mm) inside it | no |
| LINE (all mains) ↔ PE | basic | 120 | 62368-1 basic 1.5 / 1.8 [I]; UL field wiring to dead metal 6.4 [S] | 6.4 (edge and hole rule) | — |
| PS1 input ↔ output | reinforced (in the part) | 305 V rated | Class II, 4.2 kVAC [P] | 45 mm pin to pin outside the potting | — |

## 7. Calculations

All numbers below are evaluated in design.py (`d.calc`) and listed in out/report.md.

**C-1 Box fill.**

- **E1 (NS14126)**: inside ≈ 13.9 × 11.9 × 5.98 in = 989 in³ gross [I from the catalog dimensions]. It is over 100 in³, so the 314.16(A) table does not apply. As a check, at 12 AWG (2.25 in³):
  - branch L and N 2, receptacle leads 9, devices 3 × 2, EGCs 1: 18 allowances = 40.5 in³;
  - board assembly envelope (200 × 150 × 45 mm): 82 in³; receptacle block with subplate: 42 in³;
  - that leaves **825 in³ free**. Wire-bending space for 14–10 AWG is "not specified" in NEC 312.6(A) [S]; the terminals have ~140 mm above them.

**C-2 5 V budget.**

| Item | Calculation | Result |
|---|---|---|
| Total load | 1.0 + 0.547 + 0.017 + 0.002 A | **1.566 A** |
| IRM-20-5 capacity at 70 °C, 108 VAC | 4 A × 50 % × 95 % | 1.9 A (ratio **0.82**) |
| IRM-20-5 capacity at 60 °C | | ratio 0.59 |
| Pi voltage at J5 | 4.875 − 0.07 − 0.02 − 0.01 V | **4.775 V** ≥ 4.63 V |
| GPIO load per CH pin | 3.3 V / 4.8 kΩ | 0.69 mA |

**C-3 Coil voltage.**

- **Minimum.** V = 4.875 − (0.011 trace + 0.004 Qk + 0.026 Q7 + 0.011 return) = **4.82 V** ≥ 4.5 V.
- **Hot restart.** The coil is at 95 °C (60 °C air + 35 K rise [I]), so must-operate is 70 % × 329.5/257.5 = **89.6 %** = 4.48 V. The margin is 0.34 V (m5); T-COIL also runs at 4.63 V.
- **Maximum.** 105 % (limit 130 %). During an OVP event (≤ 6.75 V) the coil is briefly at 135 %, until the module shuts down.

**C-4 Watchdog timing (both stuck cases, review M1).**

- **Pulse width.** tw_min = 1.0 × 1 M × 220 n × 0.99 × 0.90 × 0.85 × 0.90 = **150 ms**; tw_max = 1.1 × 1 M × 220 n × 1.01 × 1.10 × 1.15 × 1.10 = **340 ms**. K is extrapolated from the 10 kΩ / 0.1 µF data [I], so T-HB measures it.
- **Event simulation ([wdsim.py](wdsim.py), review N1).** Relay operate 15 ms [P]; release 2 ms when asking whether a gap drops a load, 15 ms (with the diode [I]) when asking how late it turns off.

| Case | tw_min part (150 ms) | tw_max part (340 ms) |
|---|---|---|
| HB stuck high, last edge to contact open | 165 ms | **356 ms** ≤ 0.5 s |
| HB stuck low | 165 ms | **356 ms** (identical: B is edge-triggered) |
| Largest single HB gap that does not open a contact | **152 ms** ≥ 150 ms | 342 ms |
| HB 2 / 4 / 6 Hz (chatter band 2.9–6.7 Hz) | 6 / 12 / 18 openings in 3 s | — |
| HB 10 Hz and 20 Hz | 0 openings | 0 openings |

- **Heartbeat margin.** REQ-16's 20 Hz minimum retriggers every ≤ 50 ms: 3× inside tw_min, and 3× above the chatter band.
- **Clean turn-off.** Q7 turns off in ns, so the coil voltage is never "decreased gradually", which the G5RL precautions forbid (the M1 note).
- **Arm gate.** V_GS(Q7) ≥ 3.135 − 0.1 = **3.04 V** ≥ 2.5 V.

**C-5 Readback levels (RP3A0: V_IH ≥ 1.6 V, V_IL ≤ 0.9 V [P]).**

| Condition | Calculation | ARM_FB |
|---|---|---|
| Disarmed | COIL_RTN = 4.875 × 115/125 via R26 = 4.49 V; × 68/115 | **2.65 V** |
| Armed | 0.55 A × 48 mΩ × 68/115 | **0.016 V** |
| Disarmed with a CH on (worst steady state) | 5.25 × 68/115 | **3.10 V** ≤ 3.3 V |

Flyback transients up to 6.1 V on COIL_RTN are clamped by D16 to +3V3 + 0.24 V through ≥ 28 kΩ
(≤ 0.1 mA). With the Pi absent, the same clamp can back-feed U1 with a few µA. That is harmless: U1
cannot arm without edges.

**C-6 Heat budget (E1, closed, wall-mounted, receptacles included).**

| Source | W | Basis |
|---|---|---|
| 6 coils at 5.125 V, cold 56.25 Ω | 2.80 | [P] coil data |
| Relay contacts, 15 A through one relay at 10 mΩ | 2.25 | [I]: twice the rev 1 assumption (m4); measured in T-HEAT |
| PCB copper, ~300 mm of 7.5 mm × 2 layers × 2 oz (5.7 mΩ) | 1.28 | C-7 |
| Terminals, 4 clamping points × 1 mΩ | 0.90 | [I] |
| Conductors inside E1: branch 0.4 m + receptacle leads 0.9 m of 14 AWG (10.8 mΩ) | 2.43 | 8.3 mΩ/m [I] |
| Receptacle contacts, 2 × 2 mΩ at 15 A | 0.90 | [I] |
| PS1 loss at 5.8 W out, η 76 % | 1.84 | [P] efficiency ≈ 79 % at full load; derated [I] |
| Pi Zero 2 W at full CPU | 3.00 | [S] measurements |
| LEDs, PTC, FETs, U1 | 0.14 | |
| **Total** | **15.5** | |

- **Enclosure.** The NS14126 has 0.340 m² of exposed area (back excluded) and h ≈ 5.0 W/m²K for a sealed polycarbonate box [I]. ΔT = 15.5/(5.0 × 0.340) = 9.2 K, so the internal air reaches **49.2 °C** at a 40 °C room. One volume holds every source, so the Pi's 13.8 K margin already includes the receptacle and lead heat.
- **Ratings at 49 °C air (+7 K local):**
  - Pi: 70 °C max, **13.8 K margin**.
  - IRM-20-5: 70 % available at 60 °C.
  - Relays: 85 °C max. VDE rates 16 A at 85 °C [P].
  - Terminals: 105 °C [P]. Receptacles: rated for building use at normal wall-box temperatures [I]; measured in T-HEAT.
- **The budget closes** with no venting and no duty limit beyond REQ-6 (≤ 12 A continuous).
- **What would change it:** if T-HEAT finds more than 60 °C, the steps in order are (1) the 16 × 14 × 6 in NS16146, (2) limiting the sum of continuous outlet loads to 10 A in the label and software, and (3) moving PS1 to the top of the board.

**C-7 Mains copper (unchanged).**

- **Width.** 2 oz, 7.5 mm on both layers (`Net(width_mm=7.5)`), ΔT ≈ 1.6 K.
- **Fault withstand.** Onderdonk melt I²t = 92 kA²s against the 15 A breaker's 67 kA²s at 2 kA: **1.37×**.
- **Crossings.** Where N crosses an L or L_SW path, each runs on one layer for the crossing. One layer of 7.5 mm × 2 oz carries 15 A at a 10 K rise (IPC-2221 needs 6.3 mm) [I].

**C-8 Creepage and clearance (OVC III, review m7).**

- **Why OVC III.** Permanently connected equipment that is part of the fixed installation is arguably OVC III, so the design uses it conservatively.
- **SELV ↔ mains margins:** clearance 8.0/3.8 = **2.1×**, creepage 8.0/3.0 = **2.7×**.
- **Functional clearance margin:** 3.2/1.8 = **1.8×**.
- **Parts at OVC III:** the relays are rated OVC III (VDE) [P]; PS1 is OVC III under IEC 61558-2-16 [P].

**C-9 Protection coordination.**

| Item | Value | Note |
|---|---|---|
| Relay contact at the 15 A breaker ceiling | 15/16 = 0.94 | waived, with reason |
| Relay contact at 12 A continuous | 12/16 = **0.75** | |
| F1 load | 0.6 A full-load input / (1 A × 0.9 at 60 °C) = **0.67** | |
| F1 voltage with the fuse open | 187/354 = 0.53 | |
| F1 interrupting margin | 10 kA / 2 kA = **5×** | |
| F2 hold current at 70 °C | 1.43 A ≥ 1.0 A | m10 |
| D15 standoff ratio | 5.25/7.0 = 0.75 | |

The outlet paths on L_IN and L_SW1–6 have no fuse on the board; the 15 A breaker protects them.
F1 protects only the PS1 branch. kaesynth now reports exactly that (the relays sit on the wire side of F1),
and the overcurrent and entry-fuse waivers cover L_IN as well as L_SW1–6.

**C-10 Relay life.**

| Rating | Operations | Source |
|---|---|---|
| VDE, 16 A at 85 °C | 15,000 | reviewer m4 [P] |
| UL general use, 40 °C | 50,000 | [P] |
| TV-8 | 25,000 | [P] |
| 1/2 hp | 6,000 | [P] |

- At 10 operations a day at full current and 85 °C, the VDE figure gives **4.1 years**. Lighter loads and the 49 °C internal air last longer [I].
- Frequently cycled motors should drive a contactor.
- If the HR second source is used, tungsten loads drop to TV-5.

**C-11 Surge (unchanged reasoning).** An MOV would age and is a fire source in a closed box. The
insulation is coordinated for OVC III, and PS1 is tested at 2 kV L–N. A Type 2 SPD at the panel is
recommended (Q-12).

**C-12 Leakage and touch current.**

- **OFF outlet.** Open contacts are ≥ 1000 MΩ [P], so the leakage is 0.2 µA.
- **SELV to earth.** The module's leakage is < 0.25 mA at 277 VAC, about 0.12 mA at 132 V [P scaled]. That is below the ES1 0.5 mA limit [I] and 3 % of a GFCI's no-trip current.

**C-13 Wi-Fi.**

- **Enclosure loss.** 3.5 mm of polycarbonate costs < 1 dB at 2.4 GHz [I]. Carlon lists the Circuit Safe line for "applications where the ability to pass wireless signals is needed" [P].
- **Antenna placement.** The antenna zone is ≥ 30 mm (λ/4) from relays, mains copper and PS1; in this layout the gap is ≈ 60–110 mm.

## 8. Parts

Datasheets were read for every on-board part except where marked. "Stress" is the worst case in this design.

| Ref | Role | Mfr / MPN | Key ratings | Stress (margin) | KiCad symbol / footprint | Life | 2nd source |
|---|---|---|---|---|---|---|---|
| K1–K6 | SPST-NO relay | Omron (Aratas) **G5RL-1A-E-TV8 DC5** | UL E41643 16 A 277 VAC GU 40 °C, TV-8, 1/2 hp, A300; VDE 16 A 85 °C; coil 5 V 80 mA 62.5 Ω; reinforced 8/8 mm, 6 kVAC, 10 kV [P] | 15/16 A (12 A cont. = 75 %); coil 91–105 % | `Relay:G2RL-1A-E` / `Relay_THT:Relay_SPST_Omron_G2RL-1A-E` | Active [S] | G5RL-1A-E-HR (TV-5) |
| PS1 | AC/DC 5 V 4 A | Mean Well **IRM-20-5** | 85–305 VAC; Class II, 4.2 kVAC; UL/IEC 62368-1, 61558-2-16; LPS; OVP 5.75–6.75 V; hiccup 115–160 %; −30…85 °C with derating [P] | 1.57 A / 1.9 A derated (82 %) | `Converter_ACDC:IRM-20-5` / `Converter_ACDC_MeanWell_IRM-20-xx_THT` | spec 2025-11-21 [P] | IRM-15-5 (same footprint, hot derating short); RECOM RAC20-05SK [unverified] |
| F1 | Supply-branch fuse | Littelfuse **0326001.MXP** in 2 × 01020071Z clips | 1 A 250 VAC time-lag 3AB ceramic; 10 kA at 125 VAC [S] | 0.6/1.0 A (67 % at 60 °C) | `Device:Fuse` / `Fuseholder_Clip-6.3x32mm_Littelfuse_102071_…` | [S] | Bussmann MDA-1-R [unverified] |
| J1 | Line input, 2-pole | WAGO **2606-3102/020-000** | UL 1059 600 V 31 A; IEC 41 A [P] | 15/31 A = 48 % | `Conn_01x02` / **custom** `custom:WAGO_2606-3102_020-000` | Active [S] | — |
| J2–J4 | Receptacle feeds, 3-pole | WAGO **2606-3103/020-000** | as J1; L 25.35 mm [P] | 15/31 A | `Conn_01x03` / **custom** `custom:WAGO_2606-3103_020-000` | data sheet 22.10.2026 [P] | — |
| J5 | Pi socket 2×20 | Sullins **PPPC202LFBN-RC** | 8.51 mm, 3 A, 250 VDC, gold, V-0 [S] | 0.5 A per 5 V pin | `Conn_02x20_Odd_Even` / **custom** `custom:RPi_Zero2W_Socket_2x20_P2.54mm` | [S] | Samtec SSW-120-01-G-D [unverified] |
| U1 | Retriggerable monostable | TI **SN74LVC1G123DCTR** | 1.65–5.5 V; glitch-free power-up reset; Ioff; tw 1.0–1.1 ms at 10 k/0.1 µF [P] | VCC 3.47 V vs 5.5 V recommended (6.5 V abs max) | `74xGxx:74LVC1G123` / `Package_SO:SSOP-8_2.95x2.8mm_P0.65mm` | production data [P] | Nexperia 74LVC1G123 [unverified] |
| Q1–Q7 | N-MOSFET | AOS **AO3400A** | 30 V; R_DS ≤ 48 mΩ at 2.5 V; V_th 0.65–1.45 V [P] | V_DS 6.1/30 V; I_D 0.55/4.7 A (Q7) | `Transistor_FET:AO3400A` / SOT-23 | [I] | DMN2041L [unverified] |
| D1–D6 | Coil flyback | Diodes **1N4148W-7-F** | 100 V, 300 mA [P] | 93 mA | `Diode:1N4148W` / SOD-123 | [S] | Vishay 1N4148W |
| D7–D14 | LEDs (6 channel, ARM, PWR) | Kingbright **APT1608SGC** | 25 mA [P] | 2.3 mA | `Device:LED` / 0603 | [S] | Würth 150060VS75000 |
| D15 | TVS on +5V | Vishay **SMAJ7.0A-E3/61** | V_WM 7.0 V, V_C 12 V [P] | 5.25/7.0 = 75 % | `Diode:SMAJ5.0A` / D_SMA | [S] | Littelfuse SMAJ7.0A |
| D16 | ARM_FB clamp | Diodes **BAT54S-7-F** | 30 V, V_F ≤ 0.24 V at 0.1 mA [P] | ≤ 0.1 mA | `Diode:BAT54S` / SOT-23 | [S] | Nexperia BAT54S |
| F2 | Pi-branch PTC | Bourns **MF-MSMF200/16X-2** | I_hold 2.0 A (1.48 A at 60 °C, 1.43 A at 70 °C), I_trip 3.5 A, 16 V, R1max 0.07 Ω [P] | 1.0/1.43 A | `Device:Polyfuse` / 1812 | [I] | MF-MSMF260/16X-2 |
| R1–R6 | Gate series 100 Ω | Yageo RC0603FR-07100RL | 0.1 W, 75 V | 52 µW | `Device:R` / 0603 | [S] | any |
| R7–R12 | Gate pull-down 4.7 kΩ | Yageo RC0603FR-074K7L | | 2.3 mW | | | |
| R13–R20 | LED 1.5 kΩ | Yageo RC0603FR-071K5L | | 7.5 mW | | | |
| R21 | Rext 1 MΩ | Yageo RC0603FR-071ML | | µW | | | |
| R22, R23 | Pull-downs 100 kΩ | Yageo RC0603FR-07100KL | | µW | | | |
| R24 / R25 / R26 | Readback 47 k / 68 k / 10 k | Yageo RC0603FR-0747KL / -0768KL / -0710KL | | ≤ 2.6 mW | | | |
| C1, C2, C4 | 10 µF 16 V X5R | Murata GRM21BR61C106KE15L | | 5.25/16 V | `Device:C` / 0805 | backordered [S] | Yageo CC0805KKX5R7BB106 |
| C6 | 220 nF 50 V X7R (Cext) | Yageo CC0603KRX7R9BB224 | ±10 %, X7R ±15 % | 3.3/50 V | `Device:C` / 0603 | [S], 26–35 wk lead time | any 220 nF 50 V X7R |
| C3, C5, C7 | 100 nF 50 V X7R | Yageo CC0603KRX7R9BB104 | ±10 %, X7R ±15 % | ≤ 5.25/50 V | `Device:C` / 0603 | [S] | Murata GRM188R71H104KA93D |
| TP1–TP6 | Test pads | — | — | — | `TestPoint_Pad_D1.5mm` | — | — |
| H1–H6 | Board holes Ø3.2 NPTH | M3 × 12 mm nylon standoffs (MP12) | | | `MountingHole_3.2mm_M3` | | |
| H7–H10 | Pi holes Ø2.7 NPTH | M2.5 × 11 mm nylon standoffs (MP11) | | | `MountingHole_2.7mm_M2.5` | | |

**BOM-only items (not on the board).**

| Ref | Item | Source |
|---|---|---|
| MP1 | Partition: wall plus flat sheet, 1.5 mm polycarbonate UL 94 V-0, die-cut to a drawing (TBD) | [I] |
| MP2 | E1 enclosure: Carlon NS14126 | [P catalog] |
| MP3 | Back panel: Carlon JP1412P (PVC) | [P catalog] |
| MP4 | Receptacle subplate assembly: 6.4 mm polycarbonate, brass 6-32 inserts, rear shroud, grommet; machined to drawing (TBD) | [I], Q-17 |
| MP5–MP7 | Receptacles: P&S TR5252 | [S] |
| MP8 | 3-gang nylon duplex wallplate | generic |
| MP9 | Raspberry Pi Zero 2 W | [P] |
| MP10 | 2×20 male header for the Pi | [I] |
| MP11 | Pi standoff kit | generic |
| MP12 | Board standoff kit | generic |
| MP13 | Fuse clips | [S] |
| MP14 | Industrial microSD card | generic |
| MP15 | Field-wiring kit: NM-B connector, EGC lever splice, 9 receptacle leads (14 AWG UL 1015 fine-stranded, ferrules), 3 stranded green pigtails, spiral wrap, tie mounts | generic, Q-15 |
| MP16 | Mains-area shield: 1.0 mm clear polycarbonate UL 94 V-0 tray, 4 mm perforations (IP2X), flanges to the back panel | [I], review N2 |

Counts: 71 placed electrical parts (23 distinct MPNs), 6 test pads, 10 holes, 16 BOM-only items, and
three custom footprints drawn by [footprints/make_footprints.py](footprints/make_footprints.py).

## 9. Placement and mechanical constraints

**Board.**

- **Size and build.** 200 × 150 mm, 2 layers, 1.6 mm FR-4 (UL 94 V-0, ZPMV2, CTI ≥ 175 V preferred), 2 oz both sides. All parts on top.
- **Mounting.** Six Ø3.2 mm holes (H1–H6) at (4, 4), (196, 4), (4, 75), (196, 75), (4, 146) and (196, 146) mm. They take M3 × 12 mm nylon standoffs to the JP108P panel.
- **Pi holes H7–H10.** At (15.5, 4.5), (73.5, 4.5), (15.5, 27.5) and (73.5, 27.5) mm. They follow from the Zero 2 W drawing with the Pi's left edge at x = 12 and its connector edge at y = 1.
- **J5 position.** These holes fix J5: pin 1 at (20.37, 26.23) mm, rotation 0, pin 2 north.
- **Edge clearance.** The DRU applies the LINE `edge_clearance` (6.4 mm) to board edges and to holes H1–H10.

**Zones, north to south.**

1. **Wire compartment.** It runs from the north edge to the south faces of J1–J4. No copper may lie between the edge and the wire-entry faces. Other copper here must be under a terminal body or the MP1 sheet.
2. **MP1 wall.**
3. **Mains area.** L bus, F1 clips, relay contacts, and the AC end of PS1.
4. **8 mm copper-free barrier band.** It runs from the coil-pad edge + 1 mm to + 9 mm, full width, and also under the PS1 body.
5. **SELV.** Coil pins, drivers, LEDs, U1/Q7/readback, the 5 V parts, and J5 with the Pi.

**Relations (in intent.yaml).**

```
pins_toward(J1..J4, [pole 1 = wire-entry row], north)    edge(J1..J4, north)
pins_toward(K1..K6, [COIL_1, COIL_8], south)             array(K1..K6, x, pitch 20 mm)   array(J2, J3, J4, x, pitch 40 mm)
pins_toward(PS1, [AC/L, AC/N], north)                     region(PS1, east)  region(J1, corner-ne)
region([Qk, Dk, Rk, R(k+6), D(k+6), R(k+12)], south)      for k = 1..6
align([Kk, Qk, D(k+6)], y)   near(Dk, Kk.COIL_1/COIL_8, tight)   near(Kk.C_4_5, its terminal, close)
hot_loop([Dk.K, Kk.COIL_1, Kk.COIL_8, Dk.A])
region(J5, corner-sw)  edge(J5, south)  datum(J5, holes H7-H10)          [custom]
keepout(J5, antenna zone, all layers)   keepout(J5, parts under the Pi, top)
far(J5, K1..K6 / PS1 / F1, loose)  min_distance(J5, K1..K6 / PS1 / F1, 30 mm)        [custom]
frame(origin lower-left, y north)  barrier_part(MP16 IP2X shield)                          [custom]
group(arm) region(arm, south)  near(U1 pins, R21/C6/C7/R23)  near(R22, Q7.G)  near(D16/R25, J5.36)
separate(...) for every barrier;  Net(width_mm=7.5) on L_IN, N, L_SW1-6
barrier_part(MP1, wall at the J1-J4 south faces + sheet)  volume_keepout(wire compartment)   [custom]
current_path(L_IN, N, L_SW1-6: crossings single-layer)  enclosure_layout  ground_splice  label  [custom]
```

**Routing intent.**

- **L.** L runs from J1.1 south, then west under the relay bodies into pads 13 (C_3_6). It keeps 8 mm from the coil pads.
- **L_SWk.** Each L_SWk leaves pads 14 (C_4_5) going north. It enters its terminal pole from the side away from N (pole 1 from the west, pole 3 from the east), which keeps 6.4 mm to the N pad. It runs under the MP1 sheet.
- **N.** N runs on B.Cu along the south faces of J1–J4, through every pole 2 and to PS1 AC/N.
- **Crossings.** Where N crosses an L or L_SW path, each runs on one layer for the crossing, with the 1.6 mm laminate between them (functional insulation).
- **Stitching.** Use ≥ 4 vias of Ø0.6 mm every 10 mm on the two-layer stretches.
- **Supply side.** F1 goes between J1 and PS1 in the mains area. The SELV parts are C1–C3 and D15 near PS1 +Vo, F2 toward J5, and C4/C5 at J5.

**Field wiring (installer).**

- **Entries.** The branch cable enters the E1 top wall. The receptacle leads stay inside E1, north of MP1.
- **Grounding.** All EGCs are spliced in one listed lever connector in the middle of the wire compartment, ≥ 25 mm from any terminal. Green pigtails go to each receptacle.
- **Dressing.** Conductors are tied to the back panel within 50 mm of the terminals. The stripped length is 11–13 mm (WAGO).

**Vocabulary still missing from kaesynth:**

- An absolute datum (part position fixed by board holes).
- 3-D compartments and walls.
- Keepouts placed relative to part pins (the barrier band, the wire compartment).
- Single-layer segments of a wide net at crossings.

## 10. Verification plan

| Test | Hazard / REQ | Method | Pass |
|---|---|---|---|
| T-CREEP | H2, REQ-10–12 | Measurements on the bare and assembled PCB; KiCad DRC with the emitted rules | All pairs ≥ section 6 |
| T-HIPOT | H2 | All SELV tied vs all mains tied: 3.0 kVrms 60 s (type), 1 s (production). Pi removed for the type test | No breakdown; IR > 100 MΩ at 500 VDC |
| T-FUNC | REQ-3, 21 | Each outlet alone and all together, checked with a receptacle tester; LEDs | Correct outlet; LED matches the coil |
| T-PWR | REQ-15, 26, 27 | 5 V and J5 voltage with all coils on and the Pi under `stress-ng` with Wi-Fi traffic; GPIO currents | ≥ 4.75 V at J5; ≤ 0.7 mA per pin; no under-voltage flag |
| T-BOOT | H9, REQ-13, 29 | 100 cold boots, reboots, halts; Pi removed; SD removed; outlets logged at 1 ms by an isolated logger | No energization |
| T-HB | H8, H18, REQ-13, 16 | HB stopped high, stopped low; HB at 2, 4, 6, 10, 20, 50 Hz and 10 kHz; single gaps of 20–300 ms in 10 ms steps, with `stress-ng` and Wi-Fi traffic running; measure tw, disarm-to-contact-open and gaps ridden; inject a Qk short | Measured tw 150–340 ms; OFF ≤ 0.5 s after the last edge in both stuck cases; gaps ≤ 150 ms never open a contact; any HB period shorter than the measured tw arms (≥ 20 Hz always); with Qk shorted, OFF while HB is absent |
| T-SELFTEST | REQ-28, H18 | Inject each FMEA fault (Q7 D–S short, R21 open, C6 short/open, R24/R25 open, D16 short) | Software refuses to arm and alarms for each |
| T-BROWNOUT | H16, REQ-13 | Ramp mains 132 → 0 → 132 V at 1 V/s and with 0.5/1/5/30-cycle dropouts, outlets ON | Outlets either stay ON (ride-through) or go OFF cleanly; no chatter; after restore, OFF until commanded |
| T-COIL | REQ-17 | 60 °C chamber; hot restart after 1 h ON; repeat with the 5 V rail held at 4.63 V | 100/100 pickups |
| T-HEAT | H12, REQ-19 | E1 closed, surface-mounted, 12 A on one outlet (and 15 A for 1 h), 6 coils on, Pi stressed, 4 h at 25 °C; thermocouples on relays, PS1 case, Pi SoC, terminals, air; extrapolate to 40 °C | Air ≤ 60 °C; PS1 within its derating; terminals ≤ 90 °C; at the application load the Pi does not throttle; under `stress-ng` throttling is allowed but no HB gap > 150 ms (review m5) |
| T-OL | H4 | 20 A on one outlet through the 15 A breaker until it trips | No damage |
| T-SC | H5, REQ-20 | Bolted fault at an outlet at 1 and 2 kA (sample destroyed); PS1 input short at 2 kA | Breaker clears / F1 clears; no flame out of E1 |
| T-LOAD | REQ-5 | 1000 cycles: 8 A tungsten, 1/2 hp motor, LED drivers at 100 A peak inrush | No weld; contact drop < 100 mV at 1 A |
| T-SURGE | H13 | IEC 61000-4-5, 2 kV L–N and 4 kV L–PE | No flashover; no reset or uncommanded change |
| T-EFT | H8 | IEC 61000-4-4, ±2 kV on mains | No uncommanded change |
| T-LEAK | H11, REQ-18 | OFF outlet into 100 kΩ | ≤ 0.1 mA |
| T-MISWIRE | H11 | L/N swapped at J1, found with a receptacle tester (commissioning procedure) | Procedure catches it |
| T-RF | REQ-30 | RSSI and iperf at the installed location, lid closed; compare with the lid open | RSSI ≥ −67 dBm; < 3 dB lid penalty |
| T-FILL | REQ-8, Q-17 | Wire E1 fully, fit the cover with the receptacles, remove and refit it 20 times | Cover closes without force; 20 N pull on every lead at both ends holds; no lead pulled from a terminal; no conductor south of MP1; MP16 and the MP4 shroud in place (IP2X finger probe cannot touch a live part with the cover off) |

## 11. Sources

- Omron G5RL datasheet, Cat. No. K132-E1-10 [P]. https://omronfs.omron.com/en_US/ecb/products/pdf/en-g5rl.pdf
- Mean Well IRM-20, IRM-15 and IRM-10 SPEC (2025-11-21, 2025-08-08) [P]. https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF. Mean Well installation manual, PCB type [P]. https://www.meanwell.com/Upload/PDF/PCB_EN.pdf
- Raspberry Pi Zero 2 W:
  - Product brief (Apr 2024), mechanical drawing and reduced schematics [P]. https://datasheets.raspberrypi.com/rpizero2/
  - RPi documentation, power supplies and GPIO pad tables [P].
  - Power measurements [S]: jeffgeerling.com (2021), tomshardware.com Zero 2 W review, hackster.io review.
  - Antenna location [S]: magazine.raspberrypi.com, "Pi Zero W wireless antenna design"; briandorey.com, Zero 2 W external-antenna mod.
- TI SN74LVC1G123, SCES586E (Mar 2024) [P]. https://www.ti.com/lit/ds/symlink/sn74lvc1g123.pdf
- WAGO data sheets 2606-3102/020-000 (28.02.2024) and 2606-3103/020-000 (22.10.2026) [P].
- Littelfuse:
  - 215 series data sheet (chipdip copy) [P], considered and rejected.
  - 326 series 1 A, from distributor listings [S].
  - Fuse clip 102071, via the KiCad footprint description [S].
- Sullins PPPC202LFBN-RC [S] (Digi-Key, Future Electronics, Zenode listings).
- ABB/Carlon "E Enclosures" catalog: Circuit Safe NS14126, NS1086, JP1412P, JP108P, nonmetallic junction boxes [P]. https://tnb.ca.abb.com/en/pdf-catalogues/boxes-and-covers-meter-sockets/enclosures/E-Enclosures-E.pdf. BH353A, B468R, E989N-CAR [S] (distributor listings). Transtector/L-com UL-listed polycarbonate kits [S].
- Pass & Seymour TR5252 [S] (Crescent Electric, North Coast, Electrozad listings).
- Bourns MF-MSMF [P]. AOS AO3400A rev 3.1 [P]. Diodes BAT54S DS11005, 1N4148W DS30086 [P]. Vishay SMAJ [P]. Kingbright APT1608SGC [P].
- TI SLUP419 "Demystifying clearance and creepage distance" (Mar 2024) [P]: IEC 60664-1 F.1/F.2/F.4 subsets and IEC 62368-1 Table 10 values.
- NEC sections 210.8, 210.12, 210.19–21, 240.4(D), 240.22, 250.148(B), 314.16, 404.2(B), 406.12, 725 [S/I]: verify against the adopted edition.
- UL 1059 spacings [S]. Repo: [docs/topics/rules/isolation-creepage.md](../../docs/topics/rules/isolation-creepage.md).
