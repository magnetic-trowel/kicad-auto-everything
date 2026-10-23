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
