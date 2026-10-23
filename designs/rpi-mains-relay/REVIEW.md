# rpi-mains-relay: independent design review

Independent review, 2026-10-23, of DESIGN.md, CONNECTIONS.md, parts.py, design.py and out/.
Datasheets read: Omron G5RL K132-E1-10, AOS AO3400A rev 3.1, Diodes DS11005 and DS30086, Vishay SMAJ,
TI SLVSBO7O, Bourns MF-MSMF, Kingbright APT1608SGC, and the raspberrypi.com GPIO specification. The watchdog was
simulated in the time domain (BAT54 model fitted to the DS11005 maximum V_F; V_OH = 3.2 V).

## Verdict

**Not ready, but no blocker in the wiring.** Every pinout matches its datasheet and KiCad footprint, and
the switching topology is as DESIGN.md says. The MAJOR issues are two watchdog defects the checks missed,
field-wiring and PE insulation in the box, an unsupported Class 2 assumption, brief fit, and placement
intent too weak for an auto-placer. **BLOCKER 0, MAJOR 6, MINOR 10.**

## MAJOR

### M1. With the heartbeat stopped HIGH, the outputs take about 1–1.6 s to disarm, not 0.15 s (REQ-13 violated). The C-4 value change caused it.

- **What.** C-4 and calc `disarm_time_s` model only the bleed of C4 through R14 (τ = 0.1 s). When HB stops
  *high*, HB_R stays at 3.3 V. D2 of D12 (pin 3 → pin 2) is then forward-biased into ARM_G, so
  C3 (1 µF) discharges in parallel with C4. The bleed sees R14·(C3 + C4) = 1 MΩ × 1.1 µF = **1.1 s**.
- **Evidence (simulation).**
  - HB stopped low: V_ARM < 0.65 V after **0.13 s**, which agrees with the design.
  - HB stopped high: V_ARM < 1.2 V after **0.95 s** and < 0.65 V after **1.57 s**, at both 100 Hz and 1 kHz.
  - The pre-encoding values (R14 100 kΩ, C4 1 µF) gave 0.28 s, so the C4/R14 change caused this.
  - A crashed process leaves BCM12 high half the time.
- **Consequence.**
  - REQ-13 (≤ 0.5 s) fails, and the "OFF ≤ 0.15 s" claim in DESIGN C-4 and in the arm block of report.md is wrong.
  - Q5 crosses its linear region slowly (up to ~0.4 W), ramping the coil voltage down over hundreds of ms,
    against the G5RL precaution "Do not decrease coil voltage after operation" (p.7, *Others*) while carrying up to 15 A.
- **Fix.** Either of these was simulated:
  - Add ~100 kΩ from PUMP to GND. HB stopped high then disarms in 0.15 s, and V_ARM(100 Hz) is 2.62 V.
  - Or make C3 = 100 nF: 0.28 s and 2.61 V.

  A watchdog or monostable IC driving Q5 from 5 V is more robust and also fixes m1. Add HB-stopped-high to the calcs.

### M2. Single faults in the watchdog go undetected and silently remove the second "key"

- **What.** H8 and REQ-14 argue that "the other path still blocks", which assumes the other path is healthy.
  Three single faults stay invisible in normal operation:
  - **Q5 drain-source short.**
  - **C3 short.** An MLCC flex crack is a common short. With C3 shorted, any DC-high HB holds ARM_G at ≈ 3 V indefinitely.
  - **R14 open.** C4 then holds ARM_G for seconds or longer, limited only by D2 and gate leakage.

  After any one of these, a hung app with a CH pin high leaves that output ON, which is exactly the H8 scenario.
- **Evidence.** The netlist has no path from ARM_G or COIL_RTN back to the Pi; all 8 positions of J6 are used.
  The H8 FMEA lists only Qk and Q5 shorts.
- **Fix.** Read ARM back (COIL_RTN, or ARM_G through a divider) on a spare pull-down GPIO (10-position J6); at
  boot and periodically, stop HB and confirm disarm within the limit, else refuse to run; add C3, C4, R14, D12
  and Q5 to the FMEA.

### M3. Field conductors and bare EGCs can rest on exposed mains copper, and LINE–PE spacing depends on installer behaviour

- **What.** MP1 covers only the SELV band; the 7.5 mm L, N and L_SW pours on F.Cu have only solder mask, which
  is not insulation. NM-B EGCs are bare, and cables entering the E/W walls (allowed by DESIGN §9) cross the board
  while the cover presses ~15 conductors onto it. The board is 4.95 mm from each E/W wall, so an NM connector or
  locknut (PE) in an E/W knockout sits inside REQ-12's 6.4 mm; the 6.95 mm figure ignores that hardware and the
  ±1 mm of a hand-drilled template with snap-in supports.
- **Consequence.** A bare grounded conductor can wear through the mask onto L, which is a ground fault arcing inside the box. The REQ-12 and H3 margins assume a tidy installation.
- **Fix.** Insulating cover over the mains area (terminal-entry cut-outs only) or the whole board; insulated or
  sleeved EGC pigtails; mains entries through the north wall and ring only; knockouts and connector hardware as
  PE obstacles in intent.yaml.

### M4. The Class 2 status of the Pi link is assumed, not shown

- **What.** REQ-26, H2 and Q-6 (CL2 cable in a mains box, NEC 725.136) all depend on the 5 V link being Class 2.
  NEC 725.121(A) (2020) accepts a listed Class 2 transformer or supply, listed equipment marked as a Class 2
  source, listed ITE limited-power circuits, or (Exception 2) circuits within Chapter 9 Table 11 limits [S, ECM
  summaries; verify the adopted edition]. The design shows no listing or Class 2 marking for the Pi header 5 V,
  and the Pi 5 PSU is 5 A with nothing limiting the header.
- **Consequence.** If the AHJ does not accept the link as Class 2, the cable and the separation scheme change: Class 1 wiring methods, or a listed Class 2 supply plus isolated I/O.
- **Fix.** Add a BLOCKING question; options are a listed Class 2 5 V coil supply with the Pi signals through an
  isolator or optocouplers, or documented compliance with Exception 2.

### M5. Brief fit: "Kind of like the outlets" is read as bare terminals, and the receptacle option was never considered

- **What.** The user asked for switching "kind of like the outlets" and "mounted into an outlet type box". The design delivers wire terminals behind a blank
  cover, and Q-10 ("receptacles or direct loads?") is non-blocking.
- **Missing alternative.** The trade study leaves out the most literal reading: a 2- or 3-gang box holding split-tab duplex receptacles, giving 4 individually switched outlets.
- **Why it matters.** It changes the enclosure, box fill, heat and labelling, and garage receptacles need GFCI under NEC 210.8(A)(2) [I] (ASM-2 puts the box in a garage).
- **Other departures.** The Pi outside the box is well argued (P1) but held as an assumption (ASM-4), not asked.
  The terminals are "easy to access" only with the breaker off and the cover removed.
- **Fix.** Make Q-10 blocking, add the receptacle architecture to §5, and ask about Pi placement explicitly.

### M6. intent.yaml lets a placer put parts in unsafe places; only a later DRC run would catch some of them, and others not at all

- **(a) Relay orientation.** Relays are constrained only by `orient: facing: south`, with the meaning carried in prose.
  - In `Relay_SPST_Omron_G2RL-1A-E` at rotation 0, A1/A2 sit at y = 0 and contacts at y = +20/+25, i.e. the coils face *north* on screen.
  - "Facing" is undefined, so a literal placer can put the contacts toward the SELV band.
  - The terminals have the same problem, with a footprint that does not exist yet.
- **(b) Barrier keepouts.** The barrier-band keepout and the K-relative board keepout are text strings (`obj: "barrier band: ..."`, `relative: "..."`), not geometry.
- **(c) SELV driver parts.** The SELV parts in the ch1–4 blocks (Qk, Dk, the LEDs, Rk) have no region. `group(ch_k, close)`, `align(D(k+4), Kk)` and `near(D(k+4), Kk, close)` all pull them toward the relay body, beside the L bus that runs under the relays. Only the 8 mm DRU rule would catch that, after routing.
- **(d) Edge and PE spacing.** The 2.0 mm mains-to-edge keepout and LINE–PE are not in `.kicad_dru`; there is no `edge_clearance` rule for the mains netclasses.
- **(e) MP1 holes.** The two MP1 snap holes are not in `board(holes=...)`.
- **(f) Track width.** The netclass track width is 6.3 mm, but C-7, the I²t margin of 1.4× and the waivers assume 7.5 mm on both layers.
- **Fix.** Use pin-relative constraints (K.A1 south of K.13) or explicit rotations; give each channel's SELV
  parts a region south of the coil-pin row; express keepouts as coordinates relative to the relay row; add
  DRU edge-clearance rules for the mains netclasses; add the MP1 holes; set the netclass width to 7.5 mm.

## MINOR

### m1. The gate-drive and ARM calculations use V_OH = 3.2–3.3 V

- **Evidence.** Pi documentation for BCM2711: V_OH ≥ 2.6 V at 4 mA, default drive 4 mA.
  - That gives V_G(Qk) = 2.6 × 4.7/5.7 = 2.14 V and V_ARM ≈ 2.6 − 0.48 = 2.1 V.
  - Both are below the 2.5 V at which R_DS(on) is specified (AO3400A p.2), so `gate_on_V` and `arm_gate_min_100Hz_V` fail on published minimums.
- **Risk.** It probably works: AO3400A Fig. 1/2 show amps at V_GS = 2 V. It is not guaranteed at V_th(max) 1.45 V and 55 °C.
- **Fix.** Use a FET whose R_DS(on) is specified at ≤ 1.8 V, or justify the margin from the curves at V_th(max).

### m2. The ERC status is misreported, and the custom footprint reference is broken

- report.md says ERC "0 warnings", then lists 5 `footprint_link_issues`.
- J1–J5 reference `custom:WAGO_2606-3102_020-000`. DESIGN and CONNECTIONS say `kae:`, and neither library is in `fp-lib-table`.
- Verified on the WAGO product page: 7.5 mm pitch, 2-pole, L = (n−1)·7.5 + 10.35 = 17.85 mm, top entry at 90°, strip length 11–13 mm, 24–8 AWG.
- Not verified: "W pinning" and the claimed pole-2 offset (+7.5, +12.5).
- Not verified: UL 1059 600 V/31 A. Distributors list 41 A (probably the IEC figure).

### m3. H14 and T-MISWIRE overstate how well the Pi is protected

- A red/black swap shorts the Pi's 5 V to GND through J6.2–J6.8, because there are two GND positions. F1 is not in that path.
- "12 V on +5V_IN" is also on the Pi's own 5 V pin (the same conductor), so the Pi cannot "survive" it.
- SMAJ7.0A (400 W, 10/1000 µs ≈ 0.4 J) absorbs tens of joules before F1 trips: about 0.3 s at 8 A (Bourns table).
- U1 clamps only above 6.5 V, so a 5 V conductor landed on a CH position damages the GPIO.
- U1 sits 3 m from the Pi pins, so T-ESD on the Pi-end conductors is unprotected.
- **Fix.** Correct the claims. Add series resistors at the Pi end (Q-8 adapter).

### m4. Relay rating statements

- The VDE 16 A/250 VAC/85 °C rating is for **15,000** operations (p.6), not the 50k quoted in the waiver context.
- The UL ratings are at 40 °C, while the box reaches about 55 °C.
- C-6 assumes 5 mΩ contact resistance [I]. The datasheet maximum is 100 mΩ (at 1 A), so only T-HEAT can confirm the heat budget.
- The second source G5RL-1A-E-HR is rated TV-5, so REQ-5 must fall to TV-5 if it is substituted.

### m5. The hot-restart pick-up margin (2.9 points) is thin

- It rests on V_hdr ≥ 4.75 V and a 35 K coil rise [I].
- At the Pi under-voltage threshold of about 4.63 V the margin drops to about 0.5 points.
- Contact heating at 12–15 A raises the coil temperature further.
- **Fix.** Keep T-COIL, add a test at 4.63 V, and log the result.

### m6. The plain-diode flyback slows contact opening

- A plain diode slows contact opening (Omron's 5 ms release time is not stated as with-diode for the TV8 model), which means more arcing on inductive loads.
- **Fix.** Consider a diode plus a 12 V Zener: V_DS peak ≈ 17.3 V, which is below the 30 V rating [I].

### m7. The overvoltage category basis

- A box hard-wired into the fixed installation is arguably OVC III (2.5 kV at 150 V) under IEC 60664-1 [I].
- The margins still hold: the relay is rated OVC III, 8/8 mm is far above requirement, and the L–N clearance of 3.2 mm exceeds the 1.5 mm needed at 2.5 kV.
- **Fix.** State the category basis.

### m8. 15 A branch dependency

- The overcurrent waivers are true only if the branch is ≤ 15 A (Q-3).
- Garage branches are often 20 A [I], and nothing on the board enforces 15 A.
- **Fix.** Consider a UL 248 15 A fuse on L_IN, or keep Q-3 blocking and put the limit on the label as planned.

### m9. The schematic is labels only

Every pin is on a net label and there are no wires (e.g. sheets `arm` and `ch1`). The signal flow (pump, two-key coil path) cannot be seen, so a human cannot review it.

### m10. PTC hold current at 55 °C

The Bourns derating table gives about 0.81 A (0.85 A at 50 °C, 0.77 A at 60 °C), not 0.85 A. There is no consequence.

## Waivers in out/report.md

| Waiver | Reasoning true? |
|---|---|
| rating.current, K1–K4 at 15/16 A | Mostly. The 12 A continuous limit makes it acceptable, but correct the VDE life (15k) and the UL temperature (40 °C) (m4) |
| protect.threat surge (L_IN, N) | Yes. The spacings far exceed OVC III, and the MOV argument is reasonable |
| protect.threat and entry_fuse, overcurrent | Only if the branch is ≤ 15 A (Q-3). The "31 A" terminal rating is unverified. The I²t margin assumes 7.5 mm on both layers, while the netclass says 6.3 mm (M6f) |
| lib.footprint_custom | Yes, but the library nickname is wrong and the geometry is unverified (m2) |
| conn.empty_net PE | Yes |
| hazard.procedural H10, H15 | Yes |

## Verified correct (the next reviewer can skip these)

- **K1–K4 pinout.** G5RL bottom view, p.5:
  - coil on pins 1/8; 3 joined to 6 (moving contact); 4 joined to 5 (fixed contact);
  - holes 7.5/20/5 mm, Ø1.3.

  Against the KiCad footprint: A1 (0,0), A2 (7.5,0), "13" at y = 20 (pins 3/6), "14" at y = 25 (pins 4/5). L_IN is on 13 and L_SWk on 14, and both pads of each contact are used (p.7). Coil-to-contact pad edges are 18 mm apart; pad 13 to pad 14 is 3.0 mm.
- **K1–K4 ratings** (pp.2, 3, 6): coil 5 V / 80 mA / 62.5 Ω ±10 %, 70/10/130 %; 6 kVAC, 10 kV, 8/8 mm; UL 16 A 277 V GU, TV-8, ½ hp, A300; VDE reinforced, 250 V, PD3, OVC III.
- **AO3400A.** SOT-23 pins 1 G, 2 S, 3 D, matching KiCad. Limits: 30 V, ±12 V, V_th 0.65–1.45 V, 48 mΩ at 2.5 V.
- **D12 BAT54S.** Pin 1 A, pin 2 K, pin 3 COM. The pump polarity is correct (positive pump), and arming takes 1–2 cycles.
- **D1–D4 1N4148W.** Cathode (pin 1) on +5V and anode on COILk, the correct flyback orientation.
- **D11 SMAJ7.0A.** The KiCad symbol draws the bar at pin 1, pin 1 is on +5V, and pad 1 of D_SMA is the cathode. V_BR is 7.78–8.60 V and V_C is 12.0 V at 33.3 A.
- **U1.** Pins match Table 4-3. Leaving the NC pins and D3− open is allowed.
- **LEDs.** On APT1608SGC, pin 1 is the cathode (p.1 symbol). Ratings: 25 mA, 62.5 mW, 5 V reverse.
- **J6 to Pi header.** J6 → Pi pins 2, 6, 11, 13, 15, 16, 32, 34 = 5V, GND, BCM17, 27, 22, 23, 12, GND. +5V sits next to GND only.
- **Mains topology.** Line-only switching. N is never switched. There is no PE copper and no N–SELV or N–PE path, so a GFCI on the branch is not disturbed.
- **Two-key logic.**
  - With Q5 off, COIL_RTN floats until Qk turns off; there is no sneak path through D9 or the body diodes.
  - Power-up, boot (default pull-downs plus 4.7 kΩ), an unplugged Pi and a floating CH line all leave the outputs OFF.
  - HB stopped LOW disarms in 0.13 s.
- **Calculations recomputed:** C-2 (0.388 A, 0.58 mA/pin), C-3 (0.193 V drop, 88.2 % hot must-operate), C-7
  (IPC-2221 ΔT 1.6 K and 6.3 mm, Onderdonk 92 kA²s, 0.019 mΩ/mm), C-12 (4.5 mA), C-1 volume arithmetic, and the
  IEC 60664-1 creepage rows (125 V MG III PD2 1.5 mm; 250 V 2.5 mm; PD3 4.0 mm).
- **DRU.** SELV against every mains netclass gets 8/8 mm. The specific mains-pair rules follow the inherited ones, so the stricter value wins.
- **PTC F1.** MF-MSMF110/16X: 1.1/2.2 A, 16 V, 100 A, 0.06–0.20 Ω.

## Response to review (designer, revision 2)

Revision 2 also folds in four user decisions: switched receptacles, the Pi inside the box, 6 channels,
and a Pi Zero 2 W powered from the box's 120 VAC (DESIGN.md §1). Several findings were therefore
resolved by a new architecture, not by a patch.

Build (revision 3): 0 errors, 0 warnings, 31 waived (6 rules); ERC 0/0; netlist identical.

### Major findings

**M1 (slow disarm).**

- The charge pump is replaced by a TI SN74LVC1G123 retriggerable monostable (U1: R21 330 kΩ, C6 100 nF), which drives Q7.
- B is edge-triggered, so neither level can hold it on. tw is 25–46 ms over tolerance.
- Calcs `disarm_hb_stuck_high_s` and `disarm_hb_stuck_low_s` both give 61.4 ms against a 0.1 s limit (C-4).
- The gate now switches in ns, which meets the G5RL "no slow coil-voltage decrease" precaution.

**M2 (undetected watchdog faults).**

- Q7's drain is read back on BCM16 (ARM_FB) through 47 k/68 k, with a 10 k pull-up and BAT54S clamps.
- REQ-28 adds the boot and periodic self-test (disarmed → armed → disarmed, with timing).
- The new FMEA table (DESIGN.md §4, H18) covers U1, R21, C6, Q7, R22–R26 and D16. Every fault that removes the second key is detected; the rest fail safe.
- A shorted Qk remains visible only through its LED (Q-16).

**M3 (field conductors on mask-only copper).**

- E1 is split by partition MP1: a polycarbonate wall from the PCB to the lid at the south faces of J1–J4, plus a flat sheet die-cut around J1–J4.
- North of the wall, copper may lie only under a terminal body or the sheet, and none between the edge and the wire-entry faces (REQ-31, board keepouts).
- The enclosures are nonmetallic, so there is no box metal or knockout hardware.
- LINE `edge_clearance` = 6.4 mm is emitted to `.kicad_dru` for board edges and holes H1–H10 (the PE obstacles).
- EGC splice location and tie-down rules are in placement relations.

**M4 (Class 2 not shown).** Reshaped: no Class 2 wiring leaves E1 any more. DESIGN.md §5.3 states
the basis:

- the IRM-20-5's certified Class II, 4.2 kVAC insulation and its LPS output [P];
- reinforced relays;
- the 8/8 mm board band;
- MP1 as supplementary insulation.

The UL file number of the module is to be confirmed under Q-1.

**M5 (brief fit).** Answered by the user decisions: six individually switched TR receptacles, with
the Pi inside on J5 (Q-2 to Q-5 recorded as answered).

**Revision 3 (user decision Q-8, "One enclosure").** The two-box assembly is replaced by one Carlon
NS14126 polycarbonate UL 50 enclosure (14 × 12 × 6 in). The receptacles sit in a 3-gang opening in its
cover on a polycarbonate subplate; their leads, terminals and the field wiring stay north of MP1; the
board is unchanged. Cover-mounted devices are not a listed method, so Q-17 (AHJ or UL 508A) is a new
BLOCKING question. Heat: 15.5 W, 49 °C air.

**M6 (placement intent).**

| Item | Fix |
|---|---|
| (a) Orientation | `pins_toward` for K1–K6 (coil south), J1–J4 (wire entry north) and PS1 (AC north) |
| (b) Keepouts | Structured board keepouts (antenna rect, under-Pi rect), a J5 footprint rule area, and `keepout(J5, …)` relations. The barrier band and wire compartment stay relative text, because there is no pin-relative primitive yet |
| (c) SELV parts | `region([Qk, Dk, Rk, R(k+6), LED, R(k+12)], "south")` for every channel |
| (d) Edge clearance | Domain `edge_clearance_mm=6.4` with `edge_source` |
| (e) Holes | All 10 holes are in `board(holes=…)`. MP1 now uses no board holes |
| (f) Track width | `Net(width_mm=7.5)` on L_IN, N and L_SW1–6. Netclass track width is 7.5 mm |

### Minor findings

| Finding | Action |
|---|---|
| m1 (V_OH) | The Zero 2 W (RP3A0) specifies V_OH ≥ 3.0 V at 2 mA [P]. The gates are now 100 Ω + 4.7 kΩ, giving 2.94 V. Q7 is driven by U1 at ≥ 3.04 V. Both are calcs ≥ 2.5 V |
| m2 (ERC, footprints, WAGO) | ERC 0/0, with 0 violations in erc.json. Three custom footprints are drawn in `footprints/custom.pretty`, and all references use `custom:` consistently. The pole-2 offset (+7.5, +12.5) and UL 1059 31 A (IEC 41 A) are read from the WAGO data sheets [P] |
| m3 (Pi protection overstated) | Obsolete: no external SELV cable, J6, ESD array or Pi-end conductors remain. H14 now covers Pi mis-fitting |
| m4 (relay ratings) | The waiver and C-10 now quote VDE 16 A at 85 °C for 15k operations and UL at 40 °C. Contact resistance is taken as 10 mΩ [I] and measured in T-HEAT. The HR second source is limited to TV-5 (REQ-5) |
| m5 (hot-restart margin) | Margin is 4.82 V against 4.48 V (the coil supply no longer has a cable or PTC). T-COIL includes a 4.63 V case |
| m6 (diode plus Zener) | Not adopted. AC loads extinguish at current zero; 15 ms diode release is budgeted in C-4 and measured in T-HB (DESIGN.md §5.7) |
| m7 (OVC basis) | OVC III adopted. Margins: clearance 8.0/3.8 mm, creepage 8.0/3.0 mm (C-8) |
| m8 (15 A branch dependency) | Q-6 is blocking: a 15 A dual-function AFCI/GFCI breaker, and a 20 A circuit is re-breakered at 15 A. An on-board 15 A fuse was rejected: at 12 A continuous in a 52 °C box a 15 A fuse is past its continuous rating, and a 20 A fuse would not protect the 16 A relays (§5.6) |
| m9 (labels-only schematic) | Framework limitation, unchanged. Rendered and checked sheet by sheet; CONNECTIONS.md is cross-checked against netlist.json |
| m10 (PTC hold) | The 1.1 A PTC is gone. F2 (MF-MSMF200/16X) holds 1.43 A at 70 °C against a 1.0 A Pi allowance |

### Waivers

- **Removed:** `lib.footprint_custom` (footprints are now drawn) and `conn.empty_net PE` (the framework now exempts domain references).
- **Tightened:** the overcurrent and entry-fuse regexes, from `L_IN|…` to `L_SW1–6` and `N|L_SW1–6`.
- **Framework gap, since fixed:** L_IN was not flagged while F1 touched it. The framework now reports that the
  relays sit on the wire side of F1, so the overcurrent and entry-fuse waivers cover L_IN again (31 waived).
- **Framework update (123504b) applied:** all mains barriers are now `ac=True`; U1 limits carry the abs max (6.5 V) with `v_rec=5.5`; the relay isolation declares MG IIIa. The build reports no `waiver.unused`, so all six rules still match real findings.

## Re-review (revision 3)

Independent reviewer, 2026-10-23, against commit 1c49da0.

**Method.**

- **Datasheets read:** Mean Well IRM-20 SPEC (2025-11-21), TI SN74LVC1G123 SCES586E, Raspberry Pi Zero 2 W
  mechanical drawing, product brief and reduced schematic, and the Bourns MF-MSMF table.
- **Pads checked:** from the generated footprints (`footprints/custom.pretty`) and the KiCad libraries.
- **Watchdog:** an event simulation of the monostable, Q7 and relay timing.

### Verdict

**Not ready, and no wiring blocker found.** Revision 3 fixes the first-review defects it set out to fix.
Every new pinout checks out, including the J5 handedness. Three MAJOR issues remain:

- the watchdog window is so short that heartbeat jitter drops every outlet;
- live mains parts sit in the compartment the user opens to service the Pi;
- the cover-mounted receptacles. Q-17 is correctly BLOCKING, but its construction details are also unsafe as drawn.

**BLOCKER 0, MAJOR 3, MINOR 8.**

### Status of the first-review findings

| Finding | Status |
|---|---|
| M1 slow disarm | **Fixed.** U1 (74LVC1G123) is wired A = GND, CLR = +3V3, B = HB (Table 4-1, Function Table 7-1: Q is triggered only by B↑). Both stuck levels disarm ≤ tw + release: simulated 40–61 ms. Q7 switches in ns |
| M2 latent watchdog faults | **Fixed** for the ARM path. ARM_FB (Q7 drain, 47 k/68 k, R26 pull-up, D16 clamps) plus the REQ-28 self-test detect Q7 D–S short, U1 Q stuck, R21 open, and C6 open or short. Levels recomputed: disarmed 2.65 V, armed ≈ 0 V, RP3A0 V_IH 1.6 V. A shorted Qk is still only visible on its LED (Q-16); accepted and disclosed |
| M3 field conductors on mask-only copper | **Fixed** for field conductors: the MP1 wall plus sheet, DRU `edge_clearance` 6.4 mm, and `hole_clearance` 6.4 mm for H1–H10. The partition created a new problem: see N2 |
| M4 Class 2 | **Resolved by architecture.** No SELV wiring leaves E1. IRM-20: Class II, I/P–O/P 4.2 kVAC, LPS, UL/IEC 62368-1 [P, SPEC p.1–2]. Its UL file is still under Q-1 |
| M5 brief fit | **Resolved** by the user decisions (six switched TR outlets, Pi inside) |
| M6 placement intent | **Mostly fixed:** `pins_toward` on K/J/PS1, SELV regions per channel, edge and hole rules, all holes, 7.5 mm nets. Residuals in m6–m8 below |
| m1–m10 | m1, m4, m5, m7, m8 and m10 fixed. F2 is 1.48/1.43 A at 60/70 °C [Bourns derating table]. m2 fixed: ERC 0/0 and the footprints are drawn. m3 obsolete. m6 and m9 declined with reasons, which I accept |

### MAJOR

#### N1. Heartbeat gaps over ~35–50 ms drop every energized outlet, and 22–40 Hz makes them chatter

- **What.**
  - tw is 25–46 ms (C-4), and the HB is toggled by the userspace control loop (ASM-6).
  - Any gap between rising edges longer than tw turns Q7 off.
  - Simulation, assuming a 10 ms release with the diode and 15 ms operate:
    - tw_min part: a 40 ms gap opens the contacts for 20 ms, 50 ms for 30 ms, 80 ms for 60 ms. A 30 ms gap gives a 5 ms coil interruption that is shorter than the release time.
    - tw_max part: stalls up to 50 ms ride through.
  - HB periods between 1/tw_max and 1/tw_min (≈ 22–40 Hz) give repeated coil pulses.
- **Why it matters.** Stalls of tens of ms are routine for a Python or Linux loop on a Zero 2 W: GC, SD writeback, Wi-Fi driver, `stress`-level CPU load (T-HEAT runs `stress-ng`). The result is:
  - nuisance power-cycling of all loads, with repeated tungsten and motor inrush;
  - coil "pulse drive", against the G5RL precaution (p.7);
  - a contradiction of "reliable".
- **Test plan error.** T-HB's pass criterion "arms only at ≥ 100 Hz" is wrong: a 50 Hz HB (20 ms < tw_min) arms.
- **Cause.** REQ-13 was tightened from 0.5 s (revision 1) to 0.1 s without a source; nothing in the brief needs 0.1 s.
- **Fix.**
  - Restore a ≥ 0.25–0.5 s disarm requirement and set tw ≈ 150–250 ms. For example R21 1 MΩ with C6 220 nF; recompute K and leakage.
  - Generate HB from a high-priority thread, or a kernel timer that the app must pet.
  - Add stall and jitter cases to T-HB: 20–200 ms gaps under `stress-ng` with Wi-Fi traffic, plus the 22–40 Hz band.
  - If 0.1 s really is required, at least use tw ≈ 55–70 ms (R21 ≈ 470 kΩ: 36–66 ms, 81 ms with release) and a real-time HB.

#### N2. Bare live mains parts share the compartment the user opens to service the Pi

- **What.**
  - MP1 puts the field wiring north. South of the wall, in the "PCB/Pi compartment", it leaves:
    - F1 (3AB fuse in open clips, 01020071Z: bare metal at line potential);
    - the PS1 AC pins;
    - the relay contact pins;
    - the 7.5 mm L/L_SW pours on F.Cu (mask only).
  - The Pi's SD card and USB are in that same compartment (§5.4: "SD at the west end, reachable"), and the receptacles come off with the cover (H1).
- **Consequence.**
  - The one routine service action, re-imaging or swapping the SD card or debugging the Pi, puts fingers 20–100 mm from exposed 120 V.
  - "Disconnect before opening" is the only barrier, and a hobbyist debugging a Pi will often work live.
  - H1 rates this "n/a (service condition)". That does not hold, because the design itself makes the Pi a user-serviced part.
- **Fix.**
  - Use an enclosed or finger-safe fuse holder (covered 3AB holder, or a 5×20 or TR5 holder with cap; keep a ≥ 10 kA fuse), or move F1 north of MP1 under the sheet.
  - Add a clear PC shield over the whole mains area south of MP1 (IP2X), so only the SELV and Pi zone is exposed when the cover is off.
  - Put the shield in REQ-31 and in T-FILL.

#### N3. The cover-mounted receptacles (Q-17) also need construction fixes, not only AHJ acceptance

- **What.**
  - NEC 406.5 requires receptacles to be mounted in "boxes or assemblies designed for the purpose" [S].
  - A field-cut 3-gang opening also voids the NS14126's Type 4X/12/13 rating and possibly its listing marking [I].
  - Q-17 is correctly BLOCKING. As drawn:
    - The 6-32 device screws thread into tapped polycarbonate (MP4). Plug and unplug forces will strip them over time. Use brass inserts or captive nuts.
    - The nine leads plus three pigtails flex at every cover removal. The design does not say whether they are solid or stranded. Solid 14 AWG in a flexing 300 mm loop fatigues. Specify stranded THHN/MTW (both the TR5252 back-wire clamps and the WAGO 2606 accept it) and strain-relieve both ends.
    - With the cover off, the energized receptacle backs hang on those leads. That is inherent; it belongs in the AHJ package.
- **Fix.** Keep Q-17 blocking. Add the inserts and stranded leads to MP4 and MP15. Add a pull test (e.g. 20 N on each lead at the terminal) to T-FILL.

### MINOR

#### m1. PS1 OVP can exceed the Pi's PMIC rating

- IRM-20-5 OVP trips at 5.75–6.75 V ("shut off o/p voltage, clamping by zener diode") [SPEC p.2].
- The Zero 2 W's PAM2306 is rated −0.3 to 6.5 V abs max [S, Diodes DS36392].
- D15 (V_BR 7.78 V) does not conduct below that.
- H16 calls this single-fault safe. Outlets do go OFF, but the Pi can be destroyed.
- **Fix.** Add a ≤ 6.2 V clamp after F2 (Zener or TVS sized so F2 trips), or an eFuse with OVP on +5V_PI.

#### m2. F1 interrupting rating is stated only at 125 VAC

- F1's 10 kA rating is given at 125 VAC; at 250 VAC it is 100–400 A [S, distributor].
- REQ-1 allows 132 V.
- **Fix.** Confirm the 125 V rating covers the installation (ANSI C84.1 Range B tops out at 127 V), or choose a fuse rated 10 kA at ≥ 250 V. The 326-series datasheet is still unread (Q-15).

#### m3. TR5252 data is distributor-only

- The TR5252 TR, split-tab and back-wire features are [S] only. Get the P&S spec sheet.
- **Fix.** Add "GFCI Protected" and "Switched outlet N" labels to the cover.

#### m4. Pi supply below the published rating

- The product brief specifies 5 V DC, 2.5 A [P]. The design budgets 1.0 A from measurements [S], and F2 trips at 3.5 A. That is fine with REQ-26 (no peripherals).
- If the user also plugs in the Pi's micro-USB, the charger back-feeds the IRM through the Pi's 5 V rail; the Zero 2 W has no isolation diode [P, reduced schematic].
- **Fix.** Put "Do not connect micro-USB power" on the silkscreen and label, or add an ideal diode on +5V_PI.

#### m5. The T-HEAT pass criterion is likely to fail

- T-HEAT requires "SoC < 80 °C without throttling" under `stress-ng` at 56 °C local air with no heatsink.
- It is not a safety issue, but it will fail, and stress raises HB jitter (N1).
- **Fix.** Test at the application load, or add a heatsink.

#### m6. The antenna location is assumed, and the Wi-Fi distance is not machine-readable

- The antenna location is assumed (ASM-8 [V]), and the keepout covers only Pi x = 12–45 mm. Copper pours are still allowed elsewhere under the Pi.
- **Fix.** Make the whole Pi footprint pour-free, or confirm the antenna position.
- `far(J5, Kk, loose)` uses the 20 mm default, while REQ-30 needs ≥ 30 mm.
- **Fix.** Give the distance numerically.

#### m7. intent.yaml never declares its coordinate frame

- kaesynth's `BoardSpec` is y-up with the origin at the lower left (placement.py), while KiCad is y-down.
- The Pi holes H7–H10 (y 4.5/27.5), the antenna rect (y 0–13) and the J5 datum are only consistent in y-up.
- A placer that copies them into KiCad coordinates would put the Pi holes and the antenna keepout on the north edge, in the wire compartment.
- **Fix.** Emit `frame: {origin: lower-left, y: up}`.

#### m8. The array pitches are notes only

- The terminal pitch is `pitch: equal`, with "20 mm" and "J2 over K1/K2" in notes.
- L_SWk must pass the even (N) pole at 6.4 mm and stay 6.4 mm from the next terminal's L_SW. That needs a terminal pitch of ≥ 38 mm (the layout implies 40 mm).
- A packer that butts the terminals at 25.35 mm cannot be routed.
- The wire-entry stub into each odd pole is limited to ≤ 4.6 mm wide by the 6.4 mm edge rule (pad 6.95 mm from the edge). That is fine for 15 A over a few mm.
- **Fix.** Give both pitches numerically.

### Verified correct in revision 3

- **J5 Pi socket footprint.**
  - Pin 1 is the square pad on the inner row; pin 2 is at (0, −2.54) on the edge row, north. Pins run +x from the SD-card end.
  - This matches the Zero 2 W drawing (top view, square pin-1 pad on the inner row at the SD end) for a Pi fitted component side up.
  - It is the mirror of KiCad's `Raspberry_Pi_Zero_Socketed_THT_FaceDown` (pin 2 on the opposite side of the pin axis), as it should be.
  - The Pi holes sit 4.87 mm beyond pins 1 and 39 and 23 mm apart, matching both the drawing and KiCad's reference.
  - The board datum (pin 1 at 20.37, 26.23; H7–H10 at x 15.5/73.5, y 4.5/27.5) is consistent in y-up.
  - The Pi pin map checks: 1/17 = 3V3; 2/4 = 5V; GND on 6, 9, 14, 20, 25, 30, 34, 39; BCM17/27/22/23/24/25 on 11/13/15/16/18/22; BCM12 on 32; BCM16 on 36. All are default pull-down GPIOs.
- **PS1 IRM-20-5.** KiCad pad 1 AC/L (0,0), 2 AC/N (0,20.8), 3 −Vo (45,20.8), 4 +Vo (45,12.8). That is the SPEC p.3 bottom view mirrored into top view.
  - Derating: 5 V at 70 °C is 50 %, and 108 VAC gives 95.3 %, so 1.9 A against the 1.57 A budget.
  - Also confirmed: leakage < 0.25 mA at 277 V, inrush 20 A at 115 V, hold-up 8 ms, OVC III (61558) and OVC II (62368).
- **U1 SN74LVC1G123.** Pins 1 A, 2 B, 3 CLR, 4 GND, 5 Q, 6 Cext, 7 Rext/Cext, 8 VCC (Table 4-1, DCT). R21 runs to VCC and C6 sits between pins 7 and 6, as the datasheet requires. Rext ≥ 1 kΩ is met.
  - K = 1.0–1.1 is specified only at 10 kΩ / 0.1 µF.
  - The ±0.25 µA Rext/Cext leakage adds about 5 % at 330 kΩ (tw_max ≈ 48 ms). That is still ≤ 0.1 s; T-HB measures it.
  - With CLR tied to VCC, CLR↑ could trigger at power-up only if B were high. B is held low by R23 and the Pi's default pull.
- **Fail-safe states.** Power-up (PS1 1 s setup, R22, glitch-free reset), Pi reboot (GPIO12 reverts to pulled-down input), Pi absent, and 3V3 loss all leave Q7 off. Back-feed through D16 to +3V3 with the Pi absent is µA and cannot arm U1 without B edges.
- **Readback.** D16 BAT54S: A = GND, K = +3V3, COM = ARM_FB clamp. R26 pull-up gives no sneak path through Qk; Qk has V_GS < 0 while disarmed.
- **Protection parts.** D15 has its cathode on +5V, and its V_BR (7.78 V) sits above the IRM OVP, so they do not fight. F2 is MF-MSMF200/16X: 2.0/3.5 A, 0.07 Ω.
- **Receptacle feeds.** J2–J4 are wired pole 1 L_SW(2k−1), pole 2 N, pole 3 L_SW(2k), on a 14.6 mm stagger. One branch circuit with split line tabs is not a NEC 210.7 multi-circuit yoke.
- **Branch protection.** An upstream dual-function AFCI/GFCI breaker is the right answer, since no split-tab GFCI exists. Module leakage (≈ 0.12 mA) cannot trip a GFCI.
- **DRU.** The SELV↔mains 8/8 mm rules cover L_PSU (LINE_1A) and all W7p5 classes. The mains edge and hole rules are 6.4 mm. The same-footprint bridging rule (0 mm) affects only fixed package geometry.
- **Heat.** The area of 0.340 m² is checked; 15.5 W / (5 × 0.34) = 9.1 K.

## Response to the re-review (designer, revision 4)

Build: 0 errors, 0 warnings, 31 waived (6 rules); ERC 0/0; netlist identical (no topology change).

### MAJOR

- **N1 (watchdog window).**
  - REQ-13 is back to the revision-1 0.5 s turn-off. Its source is stated: neither the brief nor a standard asks for faster. It now also requires ride-through of HB stalls ≤ 150 ms.
  - R21 is now 1 MΩ and C6 220 nF (CC0603KRX7R9BB224), giving tw 150–340 ms including the ±0.25 µA leakage.
  - `wdsim.py` (event simulation, imported by design.py for the calcs) gives:
    - stuck high and stuck low: 165–356 ms to contact open;
    - largest gap ridden: 152 ms;
    - chatter band 2.9–6.7 Hz, with 10/20 Hz clean.
  - REQ-16 is now 20 Hz–10 kHz, generated by a high-priority thread that the loop pets.
  - T-HB now covers 20–300 ms gaps under `stress-ng` plus Wi-Fi, and the chatter band. The wrong "arms only at ≥ 100 Hz" claim is replaced. The self-test step 3 window is 150–345 ms.
- **N2 (live parts in the Pi service compartment).**
  - New MP16, a clear 1.0 mm polycarbonate IP2X shield over F1 and its clips, the relay contacts, the PS1 AC end and the line copper. It is flanged to the back panel, needs no board holes, and has 4 mm perforations for convection.
  - The receptacle backs are shrouded on MP4.
  - With the cover off only the SELV/Pi zone is touchable (H1, REQ-31, T-FILL probe test).
  - KiCad has no enclosed 6.3×32 holder, so F1 stays in clips under the shield.
- **N3 (cover-mounted receptacles).**
  - Brass heat-set 6-32 inserts replace the tapped polycarbonate.
  - The leads are now 14 AWG UL 1015 fine-stranded (Class K), with ferrules and strain relief at both ends, and a 20 N pull test in T-FILL.
  - The field cut ends the Type 4X/12/13 rating; the enclosure is used as Type 1, indoor dry only.
  - NEC 406.5 and the hanging receptacles are added to Q-17, which stays BLOCKING.

### MINOR

| Finding | Action |
|---|---|
| m1 (PS1 OVP above the Pi PMIC rating) | Answered: H16 now states that an OVP event can destroy the Pi (equipment damage); the outlets still go OFF. No clamp added: a ≤ 6.2 V clamp that trips F2 would need several amps below 6.5 V |
| m2 (F1 rating at 125 V) | Answered in §5.3. NEC 110.9 compares at the 120 V nominal [I]; the 326 datasheet check stays under Q-15 |
| m3 (TR5252 sources, labels) | Still [S]. "GFCI PROTECTED", "SWITCHED OUTLET" and OUT1–6 cover labels added (REQ-25, label relation) |
| m4 (micro-USB back-feed) | "DO NOT CONNECT MICRO-USB POWER" label at J5 (REQ-25) |
| m5 (T-HEAT criterion) | T-HEAT now allows throttling under `stress-ng`, requires no throttling at the application load, and requires no HB gap > 150 ms |
| m6 (antenna and Wi-Fi distance) | No pours under the whole Pi footprint (board keepout); `min_distance(J5, relays/PS1/F1, 30 mm)` relations |
| m7 (coordinate frame) | `frame` relation emitted: origin lower-left, y north. A first-class field in intent.yaml is a framework item |
| m8 (array pitches) | Numeric pitches: J2–J4 40 mm, K1–K6 20 mm |
