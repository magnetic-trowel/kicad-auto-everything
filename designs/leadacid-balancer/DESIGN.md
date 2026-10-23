# leadacid-balancer: MCU-free switched-capacitor equalizer for 2–4 series 12 V lead-acid batteries

Status: engineering design, ready to encode in `kaesynth`. Not built, reviewed or certified. The
netlist is in [CONNECTIONS.md](CONNECTIONS.md).

Evidence tags: [P] read in the primary source, [S] secondary source or snippet, [V] vendor claim,
[I] our inference. Several sites were unreachable from the design environment: analog.com,
littelfuse.com, phoenixcontact.com, eaton.com, schurter.com and the IEC/IPC standards. Values from
those sources are tagged [S] and must be checked before fabrication (Q-5, Q-6).

## Summary

- **Topology.** Three identical, independent channels. Each one is a 2:1 switched-capacitor (SC)
  "ratio cell" between two adjacent batteries: four N-MOSFETs, a fixed 100 kHz 50 % clock and a
  flying capacitor. The flying capacitor sits alternately across the upper and the lower battery,
  so charge flows from the higher battery to the lower one. Current is proportional to the voltage
  difference, so no current control loop is needed. There are no bleed resistors and no
  magnetics.
- **Why SC for lead-acid.** At rest, lead-acid voltage changes about 13.5 mV per % SOC [P]. Real
  imbalances are therefore 0.05–0.5 V, and an SC moves charge at an efficiency of
  1 − ΔV/V ≥ 97 %. Flat-OCV chemistries such as LFP need inductive balancers. Lead-acid does not.
- **Safety concept ("no pathways for voltage to jump").**
  - Every tap is fused twice: a 600 VDC, 50 kA midget fuse at the battery post, and a 400 VDC
    time-lag 5×20 fuse on the board.
  - No single component spans two or more batteries with a low-impedance path.
  - Each channel stops and lights a red LED when its battery ratio leaves ±8.7 % (a shorted cell,
    a dead battery or an open tap).
  - Board copper is ordered by potential, so only electrically adjacent domains are physically
    adjacent.
  - The alarm output is opto-isolated.
- **Efficiency.** Asleep: ≤ 35 µA per battery, with ≤ 26 µA difference between batteries. A
  channel wakes only while a charger holds its pair at ≥ 13.2 V per battery. Active overhead is
  0.22 W per channel, paid by the charger.
- **Part count:** 377 placed parts, plus the off-board harness: 122 per channel × 3, and 11 at
  board level. Fourteen distinct ICs and transistors, all with verified datasheets.

## 1. Brief

Verbatim:

> "I want a battery balancer that can balance a string, series string of 12 volt lead acid
> batteries. I want another one that can balance a series string of lithium ion batteries. This
> would be in the 10 kilowatt hour range, so home packs. It should make sure that there's no
> pathways for voltage to jump from places. I don't know if you want to do a flying capacitor or
> inductor or some other elegant approach, but it needs to keep the charge balanced without bleed
> resistors. Ideally, it would be as efficient as possible, as robust as possible, and allow us to
> have little wires that go to the system ground and then all of the individual positive
> terminals."

**This document covers only the lead-acid balancer.** The lithium-ion balancer is in
[../liion-balancer/](../liion-balancer/DESIGN.md).

## 2. Requirements

| ID | Requirement | Value + units | Source | How verified |
|---|---|---|---|---|
| REQ-1 | Balance a series string of N 12 V lead-acid batteries | N = 2, 3 or 4, set by jumper (24/36/48 V) | brief + derived (ASM-1, Q-1) | Test on 2-, 3- and 4-battery strings (V-1) |
| REQ-2 | Battery types | Flooded, AGM, gel; 100–400 Ah per 12 V battery | brief ("10 kWh") | Analysis §7.1 |
| REQ-3 | Per-battery voltage range: operate / survive | 10.5–17.6 V / 0–20 V | derived: Trojan 16.20 V equalize + 30 mV/K at −20 °C [P] | Analysis §7.1; test V-2 |
| REQ-4 | Maximum stack voltage | 70.2 V (4 × 17.55 V) | derived | Analysis |
| REQ-5 | No dissipative balancing | No bleed resistor or linear shunt in the balancing path | brief | Inspection |
| REQ-6 | Balancing current with ≤ 3 m 16 AWG harness | ≥ 0.10 A at ΔV = 0.1 V; ≥ 0.30 A at ΔV = 0.3 V | derived §7.2 | V-3 |
| REQ-7 | Charge-transfer efficiency | ≥ 97 % for ΔV ≤ 0.3 V | brief ("as efficient as possible") | V-4 |
| REQ-8 | Active overhead per channel | ≤ 0.25 W, only while a charger is present | derived | V-4 |
| REQ-9 | Sleep current per battery / mismatch between batteries | ≤ 50 µA / ≤ 40 µA | brief ("tiny and equal") | V-5 |
| REQ-10 | Wake threshold (pair voltage, rising / falling) | 26.4 ± 0.17 V / 26.1–26.4 V (13.2 / ≥ 13.05 V per battery) | derived §7.7 (Q-2) | V-6 |
| REQ-11 | Ratio lockout: stop, red LED and alarm when V_top/V_bot leaves the window | 0.907–1.088 (±1 %) | derived: a shorted cell is −16.7 % | V-7 |
| REQ-12 | Worst-case board dissipation / thermal cut-out | ≤ 3.1 W per channel / 92–99 °C | derived §7.6 | V-8 |
| REQ-13 | Fault containment | No single fault causes a sustained short or connects ≥ 2 batteries through < 100 kΩ. Every board fault current is interrupted by an on-board fuse. | brief ("no pathways") | FMEA §4; V-9…V-15 |
| REQ-14 | Tap fusing | At the battery end (≤ 150 mm from the post): ≥ 80 VDC rating, ≥ 10 kA DC interrupt. On board: ≥ 80 VDC, ≥ 1 kA. | brief + derived §7.10 | Inspection; V-9 |
| REQ-15 | Spacing | IPC-2221B functional as a minimum. Board rules in §6. ≥ 4 mm to the isolated alarm. | IPC-2221B; IEC 60664-1 [S] | KiCad DRC; inspection |
| REQ-16 | Hot-plug | Any mating order of the tap plug, any missing tap and any broken tap wire: no damage | derived | V-12 |
| REQ-17 | Mis-wiring (swapped taps, reversed battery) | No fire. On-board fuses clear. FETs may need replacement (stated limitation). | derived | V-13 |
| REQ-18 | Ambient | −20 to +50 °C, indoor, pollution degree 2, ≤ 2000 m | derived (Trojan −20…+45 °C [P]) | Analysis |
| REQ-19 | Control | No MCU and no firmware | decision §5 | Inspection |
| REQ-20 | Indication per channel | Green ACTIVE, red FAULT | brief ("robust", status) | V-6, V-7 |
| REQ-21 | Telemetry | One isolated alarm contact, closed on any fault: ≤ 30 V, ≤ 1 mA | derived | V-14 |
| REQ-22 | Harness | N + 1 wires: system negative plus every battery positive. 16 AWG, ≤ 3 m. Ring terminals. Fused. Pluggable at the board. | brief | Inspection |
| REQ-23 | Service | Board can be unplugged in one action to replace a battery | derived | Inspection |
| REQ-24 | Component derating | Semis ≤ 80 % V; caps ≤ 80 % V (DC bias counted); resistors ≤ 50 % P; fuses ≤ 75 % I in normal operation | task default | §8 table |

## 3. Assumptions and open questions

| ID | Assumption | Why |
|---|---|---|
| ASM-1 | Primary target N = 4, i.e. 48 V with 4 × 12 V × ~200 Ah ≈ 9.6 kWh. N = 2 (2 × 400 Ah) and N = 3 are also supported. | Home 10 kWh lead-acid banks are mostly 48 V. The board has three channels; jumpers disable unused ones. |
| ASM-2 | The batteries in a string are the same model and similar age | Normal practice. Mixed strings may trip the ratio lockout. |
| ASM-3 | The charger is a 3-stage temperature-compensated unit, with equalize for flooded batteries. There is no communication with it. | Typical inverter-charger |
| ASM-4 | Negative-ground system: T0 is the system ground | Brief: "wires that go to the system ground" |
| ASM-5 | One string per board. Parallel strings need one board per string. | Prospective fault current; balancing is per string |
| ASM-6 | Prospective short-circuit current at the battery posts ≤ 10 kA | One 200 Ah AGM gives 3.3 kA [P]; two strings give ≈ 7 kA |
| ASM-7 | FR-4 with CTI ≥ 175 V, i.e. material group IIIa | Standard FR-4 [I] |
| ASM-8 | The board lives in a ventilated IP54 enclosure outside the battery compartment | §9; hydrogen |
| ASM-9 | No certification for now. Spacing follows IEC 62368-1 and IEC 60664-1 principles from secondary values. | Standards not readable here |
| ASM-10 | Typical harness 1–3 m, minimum 0.3 m | Fault-current and balancing-current bounds in §7 |

| ID | Question for a human | Blocking? |
|---|---|---|
| Q-1 | Confirm the supported N = 2–4. Is a > 4-battery (96 V) bank needed? Two boards can overlap by one battery, but a > 70 V stack is outside this design's safety analysis. | **BLOCKING** |
| Q-2 | Which battery model and charger set-points (float, absorb, equalize, temperature compensation)? The wake threshold is 13.2 V per battery. Float below 13.25 V, for example a hot room or a 13.2 V AGM float, will never wake the balancer. It is set by R120–R124. | **BLOCKING** |
| Q-3 | Are flooded batteries equalized at 16.2 V or more? Then the stack exceeds 60 VDC (ES2), which drives labelling and enclosure requirements. | no |
| Q-4 | MLCCs and an electrolytic sit directly across each battery. If one shorts, the on-board fuse clears and the battery is not shorted indefinitely. Is that acceptable, or must these caps be series-redundant pairs? Pairs add 16 caps per channel and an 8 mm larger board. | **BLOCKING** |
| Q-5 | The Littelfuse 477 DC interrupting rating (1.5 kA at 400 VDC) and cold resistance are only [S]. Verify before ordering, or substitute a fuse with a read DC rating ≥ 1 kA at ≥ 80 VDC. | **BLOCKING** |
| Q-6 | Phoenix MSTB/MSTBA ratings, Eaton HEB holder data and Nichicon UCZ data are [S]. Verify them. | no |
| Q-7 | Is the isolated alarm wanted, and what will it drive (voltage and polarity)? | no |
| Q-8 | Should the balancer also run during discharge or rest (an "always on" option)? This costs 0.66 W continuously. | no |
| Q-9 | Conformal coating (acrylic, IPC-CC-830)? Recommended for battery-room humidity and acid mist. | no |
| Q-10 | Re-evaluate the ADI LTC7820 integrated SC controller once its datasheet can be read (§5, option B2) | no |
| Q-11 | Is "board survives mis-wiring without FET damage" a requirement? If so, add per-channel reverse protection (§4 H-5). | no |
| Q-12 | Certification target (UL 1973 / IEC 62368-1)? If yes, the spacing must be re-derived from purchased standards. | **BLOCKING** if yes |

## 4. Hazards

| ID | Hazard | Cause | Mitigation (block / part) | Survives one more fault? |
|---|---|---|---|---|
| H-1 | Arc, fire or burns from a battery short through the harness. One 200 Ah AGM delivers 3.3 kA, and internal R ≤ 4 mΩ [P]. | Chafed or crushed tap wire; tool across terminals | KLKD010 fuse (600 VDC; DC 10 kA UL 248-19, 50 kA UL 248-14 [P]) in a sealed in-line holder ≤ 150 mm from each post (HARNESS). 600 V insulation. Loom and strain relief. | Yes for a wire fault. The ≤ 150 mm pigtail before the fuse is unprotected: double-insulate and clamp it. |
| H-2 | Fire on the board | Shorted FET, flying cap or bulk cap; contamination | On-board 4 A T, 400 VDC fuse per tap (INPUT, F1–F5). Bounded prospective current: 108–191 A for one battery, ≤ 676 A for the full stack (§7.10). | Yes: the harness fuse backs up the board fuse. |
| H-3 | Two or more batteries bridged ("voltage jumping") | Creepage failure; a component spanning taps | Potential-ordered layout (§9). Spacing rules (§6). No part spans ≥ 2 batteries except ≥ 4.99 MΩ divider strings, the 100 kΩ level shifter and certified isolation barriers (UCC21520, SFH617A). | Yes |
| H-4 | Balancer drains good batteries into a failed one | Shorted cell (−2.1 V) | Ratio lockout of ±8.7 % (SUPV, U108 B/C) stops the channel and raises the alarm | Lockout and thermal cut-out are independent comparators |
| H-5 | Mis-wiring: swapped taps or a reversed battery | Installer | Keyed single plug, numbered and colour-coded wires, and a pre-plug voltage check (V-13 procedure). Body diodes conduct, the 4 A T fuse clears in ≈ 10 ms at ≈ 70 A [I], and FET energy is ≈ 0.5 J. | No fire. A FET may fail short; the fuse still clears. |
| H-6 | Hydrogen ignition (LEL 4 %) | Flooded or overcharged cells vent H₂; plug spark (22 mJ per battery leg); fuse operation | Enclosure outside the battery box and not above vents. Plug only at the board, away from the batteries. Harness fuses are enclosed. No relays. | Yes |
| H-7 | Board overheating | ΔV at the window edge with short wires (3.1 W per channel); blocked vents | Thermal cut-out at 92–99 °C (NTC + U108 D). Power is bounded by the window (§7.6). | Yes: the window and the cut-out are independent. |
| H-8 | Shock | Stack up to 70.2 VDC (ES2 during cold equalize) | Enclosure; pluggable insulated connector; alarm opto with basic insulation (§6) | Yes |
| H-9 | Bank drained in storage | Balancer awake at rest | Wakes only at ≥ 13.2 V per battery. Sleep ≤ 35 µA. A stuck-awake fault costs 0.22 W per channel, and the green LED shows it. | Partial: needs a human to see the LED |
| H-10 | Battery opens internally under load | Broken strap | That position reverses. Body diodes carry string current until the tap fuses clear (ms). | Yes (fuses) |
| H-11 | Corrosion or leakage across divider nodes | Acid mist, humidity | Strings ≤ 10 MΩ. Conformal coat (Q-9). IP54 box. | Yes |

## 5. Architecture trade study

Criteria and weights:

- C1, fault containment (×3)
- C2, efficiency at ΔV ≤ 0.3 V including overhead (×2)
- C3, balancing effect at small ΔV (×2)
- C4, simplicity and robustness: MCU-free, no magnetics (×2)
- C5, idle draw and equality (×1)
- C6, scaling to N = 2–4 (×1)
- C7, parts verifiable now (×1)

Scores run from 1 to 5.

| Option | C1 | C2 | C3 | C4 | C5 | C6 | C7 | Score |
|---|---|---|---|---|---|---|---|---|
| A. Dissipative mid-point shunt (Victron Battery Balancer: on at 27.3 V, up to 0.7 A, alarm at 0.2 V deviation [S]) | 4 | 1 | 3 | 5 | 3 | 3 | 5 | 41: **excluded by the brief** |
| **B. SC 2:1 per adjacent pair, discrete (chosen)** | 4 | 5 | 3 | 4 | 4 | 5 | 4 | **49** |
| B2. Same, using the ADI LTC7820 fixed-ratio SC controller (72 V; prebalance, fault window, input OCP [S]) | 4 | 5 | 3 | 4 | 3 | 5 | 2 | 46 |
| C. Inductive buck-boost per pair: DCM energy packets, direction comparator (PowerPump style; HA01/HA02 likely belong here [I]) | 3 | 3 | 4 | 3 | 4 | 4 | 4 | 41 |
| D. Shuttle or auxiliary battery (ADI LTC3305: 4 × 12 V, stand-alone, sequenced FETs [S]) | 2 | 4 | 3 | 3 | 3 | 2 | 2 | 33 |
| E. Multi-winding forward or cell-to-stack transformer | 2 | 3 | 4 | 2 | 3 | 1 | 2 | 30 |

**Why the losers lose.**

- **A** is a bleed balancer, which the brief forbids. It turns the whole imbalance into heat.
- **C** keeps losing about 10–15 % of every amp it moves, whatever ΔV is.
  - Moving 1 Ah at 0.3 V imbalance costs ≈ 2 Wh in C against ≈ 0.3 Wh in B.
  - C adds a magnetic part, current sensing and a direction comparator.
  - A shorted switch shorts a battery through an inductor.
  - C only wins on current near balance. Lead-acid's steep OCV curve makes that advantage small.
  - The commercial HA02 claims "energy transfer, 0–10 A, starts at 10 mV" [V]. Its topology is
    not published and no teardown was found.
- **D** needs a fifth battery that cycles continuously and wears out.
  - Its FET matrix connects that battery to every position.
  - One shorted switch plus normal sequencing can put the auxiliary battery across non-adjacent
    taps. That violates the brief's "no pathways".
  - The LTC3305 is listed as recommended for new designs [S], but its datasheet was not readable
    here.
- **E** needs custom magnetics per N. Winding-to-winding insulation must hold the full stack, and a
  winding fault couples every tap.
- **B2** is the same physics as B with fewer parts, and would be preferred once verified.
  - Its datasheet could not be retrieved, so pin numbers and fault behaviour are unverified.
  - Its start-up prebalance sources ≈ 93 mA into VLOW [S]. Its window logic assumes a capacitor on
    VLOW, not a battery [I].
  - Its over-current sense is on the input current. Whether that works in reverse flow is
    unknown [I].
  - Revisit under Q-10.

**Decisions.**

- **MCU-free.** The functions are four comparisons: wake, two ratio limits and temperature. A CMOS
  gate and nanopower comparators do them with ≈ 5 µA and no firmware, brown-out or programming
  failure modes.
- **Three independent channels,** not a shared ladder.
  - No clock crosses between channels.
  - A channel only needs its own three taps.
  - N = 2–4 comes from disabling channels.
  - The cost is that middle batteries carry two channels' sleep current. §7.9 bounds this
    difference at ≤ 26 µA.

**Lead-acid specifics.**

- OCV runs from 12.73 V at 100 % to 11.51 V at 10 % SOC (Trojan [P]), about 13.5 mV per % SOC.
- Float is 13.50 V for Trojan flooded and 13.2–13.8 V for AIMS AGM standby.
- Absorption is 14.82 V for Trojan and 14.4–14.7 V for AIMS.
- Equalize is 16.20 V for Trojan flooded only.
- Temperature compensation is −30 mV/K per battery (Trojan 5 mV/K/cell; AIMS −30 mV/K for cycle
  use) [P].

In a series string every battery carries the same current, but self-discharge (AGM 3 %/month,
flooded 5–15 %/month [P]), charge acceptance and temperature differ. The charger controls only the
total voltage. The high battery is overcharged (gassing, dry-out) and the low one undercharged
(sulfation).

Equalizing *voltage during charge and float* is exactly the right control target, because float and
absorption limits are per-cell voltage limits. It is **not enough** for three things:

- It does not repair capacity mismatch. Equal voltage does not mean equal Ah.
- It does not replace the periodic equalize charge that removes stratification in flooded
  batteries.
- It must not "rescue" a battery with a shorted cell. That is why the ratio lockout exists.

The balancer therefore runs only while a charger holds the pair above 13.2 V per battery, and it
stops on gross mismatch.

## 6. Blocks and domains

Tap numbering:

- T0 = system negative. Tk = positive of battery Bk (k = 1…4). In CONNECTIONS.md the board nets
  are TAP0–TAP4.
- Channel k (k = 1…3) spans B_k (bottom) and B_{k+1} (top).
- Its local names are T_L = TAP(k−1), T_M = TAPk and T_H = TAP(k+1).

Blocks. The `_k` blocks repeat for k = 1, 2, 3.

| Block | Function | Ports (direction, domain, voltage, max current) |
|---|---|---|
| HARNESS (off-board) | N + 1 fused tap wires, ring terminals, plug | P0–P4: bidirectional, TAPj, 0–70.2 V, 4.5 A normal-worst / 10 A fuse |
| INPUT | J1 tap header; fuses F1–F5 | TAPj_IN → TAPj: bidirectional, 0–70.2 V, ≤ 4.5 A |
| ALARM | J2 and the isolated bus | ALM_C, ALM_E: output, ISO, ≤ 30 V, ≤ 1 mA |
| PWR_k | SC cell: Q_A–Q_D, R_CF, C_FLY, C_TOP/C_BOT | T_H, T_M, T_L: bidirectional power, ≤ 2.3 A (T_M ≤ 4.6 A); gates in from DRV_k |
| DRV_k | Two isolated half-bridge drivers, bootstrap, dead time | PH1/PH2: in, band k−1, 0–12 V. Gates: out, local, 0–12 V, 4 A/6 A peak. 12V_L/12V_U: in, ≤ 15 mA. |
| OSC_k | CD4047 astable, 100 kHz, complementary outputs | PH1/PH2: out, band k−1, 0–12 V |
| SUP_k | 12V_L LDO (band k−1), 12V_U LDO (band k), V5 always-on LDO, enable level shifter, jumper | RUN: in, 0–5 V. 12V_L: out, ≤ 15 mA. 12V_U: out, ≤ 8 mA. V5: out, ≤ 5 mA. |
| SUPV_k | Reference, quad comparator, ratio and wake dividers, NTC, NOR gate, LEDs, alarm opto | Divider inputs from T_H/T_M: sense, ≤ 3 µA. RUN: out. ALM: out (ISO). |

**Domains.** Each reference potential is a domain. Bands group everything referenced to one tap.

| Domain | Reference | Members | V to own reference | V to T0 |
|---|---|---|---|---|
| TAPj (j = 0…4) | T0 | Tap buses | — | j × (10.5…17.6) V, ≤ 70.2 V |
| BANDj (j = 0…3) | TAPj | CH(j+1) "L" circuits: V5, 12V_L, comparators, OSC, driver inputs, lower driver output B. CHj "U" circuits: 12V_U, upper driver output B. | 0…17.6 V (12 V rails) | j × Vb … (j+1) × Vb + 12 V |
| CHk_X | node X_k | Upper switch node, BSTU, GA | X ∈ [TAPk, TAP(k+1)]; BSTU = X + 12 V | ≤ 70.2 + 12 V (k = 3) |
| CHk_Y | node Y_k | Lower switch node, BSTL, GC | Y ∈ [TAP(k−1), TAPk]; BSTL = Y + 12 V | ≤ 52.8 + 12 V |
| ISO | floating | ALM_C, ALM_E | ≤ 30 V across the contact | Assumed ≤ ±100 V to T0 |

CHk_U and CH(k+1)_L share a reference (TAPk), so they sit side by side with no barrier. This is
the basis of the potential-ordered layout.

**Barriers.** Pollution degree 2, material group IIIa, ≤ 2000 m. Every pair not listed falls into
the nearest row by voltage.

| Pair | Grade | Working V (DC) | Standard and table | Required creepage / clearance | Board rule (creepage / clearance) |
|---|---|---|---|---|---|
| Adjacent bands, or within a band to its X/Y nodes | Functional | ≤ 29.6 (17.6 + 12) | IPC-2221B Table 6-1, B2 0–30 V [S] | 0.1 / 0.1 mm | 0.2 / 0.2 mm (fab minimum). Inside parts: per footprint. |
| Bands two apart (e.g. TAP0↔TAP2, Y↔BSTU) | Functional | ≤ 47.2 | IPC-2221B B2 31–50 V: 0.6 mm; B1 internal 0.1 mm [S] | 0.6 / 0.6 mm | 0.6 mm outer, 0.3 mm inner |
| Bands three or more apart (TAP0/1 ↔ TAP3/4) | Functional | ≤ 70.2 | IPC-2221B B2 51–100 V: 0.6 mm [S]; IEC 60664-1 F.4 PD2 MG III: 63 V 1.25 mm [P via SLUP419 in repo], 80 V ≈ 1.3 mm [S] | 1.3 / 0.6 mm | **1.5 / 1.0 mm**: environment margin; fails to a fuse, not to shock |
| Any channel domain ↔ ISO (alarm) | Basic (ES2 → ES1) | ≤ 100 (assumed) | IEC 62368-1 / IEC 60664-1 F.4 PD2 MG IIIa at 100 V ≈ 1.4 mm [S]; F.2 1.5 kV impulse → 0.5 mm [S] | 1.4 / 0.5 mm | **4.0 / 4.0 mm**, no copper under SFH617A (package ≥ 7 mm, CTI 175 [P]) |
| Copper ↔ mounting holes and metal hardware | Basic | ≤ 70.2 | as above | 1.4 / 0.5 mm | 4.0 mm copper-free ring, or nylon standoffs |

Spacing details are in [docs/topics/rules/isolation-creepage.md](../../docs/topics/rules/isolation-creepage.md).
No slots are needed, because every rule is met with flat spacing.

## 7. Calculations

The calculation scripts are not committed. Every value below can be reproduced from the equations
shown.

### 7.1 Voltages and fault current

- **Per-battery maximum.** 16.20 V equalize at 25 °C + 0.030 V/K × 45 K at −20 °C = 17.55 V. The
  design value is 17.6 V; the stack is 70.2 V.
  - Float is 13.5 V, so the stack floats at 54 V.
  - The operating minimum is 10.5 V (1.75 V/cell discharge limit [P]).
- **Short circuit.** AIMS 12 V 200 Ah AGM: R_int ≤ 4.0 mΩ, I_sc 3300 A [P].
- **OCV slope.** (12.73 − 11.51) V / 90 % = 13.6 mV per % SOC [P]. So ΔV = 0.1 V at rest is about 7 %
  SOC.

### 7.2 How much balancing current is needed

- **Self-discharge mismatch.** 200 Ah × 3 %/month = 6 Ah/month, or 8 mA. A 30 % spread between
  batteries gives ≈ 3 mA [I]. Flooded, 150 Ah at 10 %/month: 21 mA, with a spread of ≈ 6 mA.
- **Float-current mismatch.** ≈ 0.05–0.1 A for a 200 Ah AGM with batteries a few kelvin apart [I].
- **Cycling.** A 1–2 % charge-efficiency spread on 100 Ah/day throughput is ≤ 2 Ah/day. Recovering
  it in ≈ 6 h of absorption and float needs 0.33 A.
- **Requirement.** ≥ 0.1 A at 0.1 V and ≥ 0.3 A at 0.3 V (REQ-6).
  - A 20 Ah (10 % SOC) step, for example a new battery, then recovers in ≈ 60 h of charger time.

### 7.3 Switched-capacitor equivalent resistance

Each phase lasts t_p = T/2 − t_DT, and the loop time constant is τ = R_loop · C. Steady-state charge
per cycle is q = C · ΔV · tanh(t_p/2τ), which gives

R_SC = 1 / (C · f · tanh(t_p / 2τ)).

The limits are 1/(Cf) (slow switching) and 4 · R_loop (fast switching).

Inputs:

- f = 100 kHz (CD4047: t = 4.40 · R · C [P], with R = 22.1 kΩ and C = 100 pF → 103 kHz)
- t_DT = 0.2 µs (UCC21520: DT = 10 ns/kΩ × 20 kΩ [P])
- C_FLY = 8 × 10 µF X7S 50 V, effective 30–50 µF after DC bias at 13–17 V [I]
- R_loop = 2 · R_on (8.1–13.9 mΩ [P], hot ×1.4 [I]) + 2 × 0.043 Ω (R101, R102) + 5 mΩ ESR and
  copper = 0.107–0.118 Ω

Result: **R_SC = 0.48–0.57 Ω, nominal 0.52 Ω.** It is insensitive to C because the cell runs mostly
in fast-switching mode. The flying current is near-square, with I_rms = 2.13 · I_bal, and the FET
current is I_rms = 1.51 · I_bal.

### 7.4 Balancing current and wiring

Per tap: R_tap = KLKD010 (≈ 12 mΩ [I]) + 16 AWG at 13.2 mΩ/m × L + 3 mΩ (lugs and plug) +
4 A T fuse (≈ 25 mΩ [I]).

Per channel: R_ext = R_H + 4 · R_M + R_L + 2 · R_int = 6 · R_tap + 8 mΩ. The middle tap carries
2 · I. This gives 0.27 Ω at 0.3 m and 0.49 Ω at 3 m.

| ΔV at the posts | I_bal (0.3 m / 3 m) | Board loss I²·R_SC | Transfer efficiency 1 − ΔV/13.5 V |
|---|---|---|---|
| 0.05 V | 0.063 / 0.050 A | 2 / 1 mW | 99.6 % |
| 0.10 V | 0.126 / 0.099 A | 8 / 5 mW | 99.3 % |
| 0.20 V | 0.25 / 0.20 A | 33 / 21 mW | 98.5 % |
| 0.30 V | 0.38 / 0.30 A | 75 / 46 mW | 97.8 % |
| 1.00 V | 1.26 / 0.99 A | 0.83 / 0.51 W | 92.6 % |

REQ-6 and REQ-7 are met.

The steady float deviation for a 0.1 A float-current mismatch is ΔV ≈ 0.1 A × 0.8–1.0 Ω ≈ 0.09 V
per pair, or ±45 mV per battery around the mean.

Sharing tap wires between channels changes per-wire current, not R_SC. Under the worst
alternating pattern a tap carries I_{k−1} + 2I_k + I_{k+1} ≤ 4 · I_edge = 9.1 A, which would open
a 4 A T fuse after minutes. That pattern only occurs with failed batteries.

### 7.5 Overhead while active (per channel, typical)

- **Gate charge:** 4 × 13 nC × 100 kHz × 12 V = 62 mW.
- **Coss charging:** 4 × ½ × 15 nC × 13.5 V × 100 kHz = 41 mW.
- **UCC21520 quiescent:** 2 × (1.4 mA VCCI + 2 × 1.0 mA VDD) at 12 V [P].
- **CD4047:** ≈ 0.3 mA.
- **Green LED:** 1 mA.

So 12V_L draws 8.7 mA and 12V_U draws 4.6 mA, which is **0.18 W from the batteries + 0.04 W Coss
= 0.22 W**, or 0.66 W for three channels while a charger is active.

LDO dissipation at 17.6 V input: U104 (17.6 − 12) × 8.7 mA = 49 mW; U105 26 mW. Both are fine for
HVSSOP.

Including overhead, end-to-end efficiency is 92 % at ΔV = 0.2 V and 74 % at 0.05 V. The overhead
stops when the charger stops (Q-8).

### 7.6 Ratio lockout, edge power and thermal

- **The window** measures ΔV at the board: lockout when V_top/V_bot > 1.088 or < 0.907 (§7.7).
  - While running, the board ΔV is ΔV_posts · R_SC/(R_SC + R_ext). Running therefore moves the
    measured ratio toward 1, which is natural hysteresis.
  - At rest it equals ΔV at the posts. A shorted cell gives 0.83 or 1.20, so the channel never
    starts.
- **Edge case.** The ratio drifts to the window while the channel is running. At V_bot = 13.5 V,
  ΔV_board = 1.18 V and I = 2.27 A.
  - P_board = 2.69 W; at V_bot = 14.4 V, 3.06 W.
  - Reaching this needs ΔV_posts ≥ 1.8–2.3 V, which is a failing battery.
  - Component power at the edge:
    - R101 and R102: (2.13 × 2.27)² × 0.043 = 1.00 W each, which is 50 % of the 2 W WSL2816 rating
      at 70 °C and 68 % at 97 °C (Vishay linear derating from 70 °C [P]). This is accepted for an
      edge state limited by the thermal cut-out.
    - Each FET: (1.51 × 2.27)² × 13.9 mΩ = 0.16 W, giving Tj ≈ 50 + 0.16 × 55 = 59 °C
      (R_θJA 55 °C/W [P]).
    - Bulk capacitor ripple at the edge: C117/C118 see ≈ 0.7 A rms against a 0.27 A rating [S].
      This is accepted because the edge is transient (normal ≤ 0.13 A). Alternative: a hybrid
      polymer capacitor.
- **Thermal cut-out.** NTC NCP15WM474 (470 kΩ ±3 %, B25/85 4582 K ±3 % [P]) under 24.9 kΩ from V5,
  compared with VREF = 2.5 V. The trip is 95.5 °C nominal and 92–99 °C across tolerances, with
  0.1–0.6 °C internal hysteresis. Thermal mass makes the resulting on/off cycle slow, seconds to
  minutes. The thermal fault also lights FAULT.

### 7.7 Thresholds

- **Comparator.** TLV7044: offset ±8 mV, built-in hysteresis 3–25 mV, input bias 2 pA,
  0.335 µA/channel [P].
- **Reference.** REF35250: 2.500 V ±0.05 %, 12 ppm/K, 0.65 µA [P].
- **Wake (CMP A).**
  - Divider: P_ON = V_pair · 0.945 MΩ / (9.03 + 0.945) MΩ, built from 3 × 3.01 MΩ and
    2 × 1.89 MΩ 0.1 %.
  - Rising threshold: 2.5 × 9.975/0.945 = **26.39 V (13.19 V per battery)**.
  - Falling threshold: 26.12–26.36 V, set by the 3–25 mV hysteresis.
  - Tolerance (0.05 % + 0.07 % drift + 0.32 % offset + 2 × 0.1 %): ±0.64 %, or ±0.085 V per
    battery.
  - Fully charged AGM rests at ≈ 12.8–12.95 V [I], which is below even the worst-case falling
    threshold of 12.98 V.
- **Ratio window (CMP B, C).** N = V_bot · 0.0996 (2 × 2.26 MΩ over 2 × 1.00 MΩ).
  - P_LO = V_pair · 0.04771 (2 × 4.99 MΩ over 2 × 1.00 MΩ).
  - P_HI = V_pair · 0.05223 (2 × 4.99 MΩ over 2 × 1.10 MΩ).
  - Trip when P_LO > N, i.e. r > 0.0996/0.04771 − 1 = **1.088**; or when N > P_HI, i.e.
    r < **0.907**. At V_bot = 13.5 V that is ΔV = +1.18 V or −1.26 V.
  - Hysteresis is 10 mV typ, or Δr ≈ 0.8 %. 1 % resistors plus offset give a window tolerance of
    ±1.5 %.
- **Robustness.** Each divider top is two resistors in series and each bottom two in parallel. One
  open or shorted resistor at most doubles the node voltage, to ≤ 6.1 V, which is under the 7 V
  input absolute maximum [P]. The fault shows up as a lockout or a missed wake; it never damages
  the comparator.
- **Filters.** All four nodes have time constants of 0.21–0.45 s (470 nF), matched within 15 % for
  the ratio nodes. A common-mode step therefore causes < 6 mV transient error against ≥ 100 mV
  margin.

### 7.8 Gate drive, timing, start-up

- **Gate drive.** U104 and U105 give 12.04 V (1.193 V × (1 + 909 k/100 k) [P]); at low battery the
  rail falls to ≈ 10.4 V. V_GS is 12 V against ±20 V, which is 60 %.
- **Bootstrap.** C = 1 µF ≥ 70 × Qg/ΔV, giving ΔV = 13 mV. The BAS16W sees ≤ 17.6 V reverse against
  75 V. Refresh happens every low-side phase (50 %).
- **Dead time against skew.** DT = 160–240 ns [P]. The skew between the upper and lower drivers is
  ≤ 19 ns (t_PD 26–45 ns [P]) plus the gate fall time (~20 ns). The rule is DT_min > skew + t_off,
  and 160 ns > 39 ns. This break-before-make holds across *both* half-bridges, which an SC needs:
  overlap would short the flying cap or put two batteries across it.
- **Start-up.** R103/R104 (100 kΩ) hold X = T_H and Y = T_M at rest. C_FLY is therefore pre-charged
  to V_top and the first commutation draws only ΔV-proportional current.
  - The bootstrap capacitors are empty, so high sides stay in UVLO for the first half-cycle. The
    first low-side phase charges them.
  - If the upper driver powers up later, its half-bridge stays off. Body diodes then run a
    harmless diode-rectified SC.
- **Wake latency.** Divider τ ≈ 0.45 s, then LDO start ≤ 1 ms, then driver UVLO ≤ 50 µs [P].
- **Fault reaction.** Divider τ 0.2–0.45 s, then 74LVC1G02 → LDO EN (≈ µs), and switching stops when
  VDD falls (ms). This is fine because power at the edge is bounded (§7.6).

### 7.9 Sleep current (per channel, typical, 25 °C, 12.8 V per battery)

- **From B_bot:**
  - TPS70950: 1.4 µA [P]
  - REF35: 0.65 µA
  - TLV7044: 1.34 µA
  - NOR gate: ~0.1 µA
  - NTC string: 5 V/(24.9 k + 470 k) = 10.1 µA
  - N string: 2.55 µA
  - U104 shutdown: 0.59 µA [P]
- **From both batteries (pair strings):** P_ON 2.57 + P_LO 2.44 + P_HI 2.43 = 7.4 µA. U105
  shutdown adds 0.59 µA on B_top.
- **Electrolytic leakage:** ~1 µA each [I].
- **Totals:** B_bot 25 µA, B_top 9 µA.

Per battery with N = 4: B1 = 25, B2 = 34, B3 = 34, B4 = 9 µA. The maximum mismatch is
**25 µA**, or 0.11 Ah in 6 months, which is 0.06 % of 200 Ah. That is < 1 % of the natural
self-discharge spread, so REQ-9 is met.

Perfect equality is impossible with overlapping channels, because middle batteries serve two
channels. A dummy load to equalize would itself be a bleed resistor.

### 7.10 Fuses, wire, fault currents

- **Harness fuse KLKD010.** Fast-acting, 600 VDC, 10 kA (UL 248-19) or 50 kA (UL 248-14) [P].
  - It protects 16 AWG wire, whose ampacity is ≥ 10 A (fuse ≤ wire).
  - Prospective current at the holder: up to 3.3 kA for one battery and 2.3 kA for a stack fault
    through the pigtail. Both are ≤ 10 kA.
  - Normal current ≤ 1 A; at the edge 4.5 A = 45 %.
- **Board fuse.** Littelfuse 477, 4 A, IEC 60127-2/5 time-lag, 400 VDC, 1.5 kA DC [S].
  - Prospective current at the board: 108–191 A for a one-battery short and 401–676 A for TAP0–TAP4
    (2 · R_tap + R_batts, L = 3 m … 0.3 m). Both are ≤ 1.5 kA.
  - Normal ≤ 1 A, which is 25 % (≤ 75 % rule ✓).
  - At the edge the middle tap carries 4.5 A = 113 %. That is accepted: it holds ≥ 1 h below 1.5 ×
    I_n and the thermal cut-out intervenes first.
  - Selectivity: the board 4 A T melting I²t is ≈ 30–60 A²s [I], against KLKD010 melting I²t of
    ≈ 150 A²s [I], interpolated from KLKD 6 A 63 A²s and 20 A 462 A²s [P]. Board faults should clear
    on board. Verify this in V-9.
- **Mis-wiring.** Through two body diodes the current is ≈ 11 V/0.15 Ω ≈ 70 A. The 4 A T fuse clears
  in ~5–20 ms [I], so FET energy is 0.9 V × 70 A × 10 ms ≈ 0.6 J. That is likely survivable but not
  guaranteed (Q-11).
- **Hot-plug inrush.** About 140 µF per battery leg charges from 0 V: peak ≤ 200 A,
  τ ≈ 14 µs, I²t ≈ 0.3 A²s, which is ≪ fuse I²t. Spark energy is ½CV² = 22 mJ per leg.
- **Wire drop at 4 A, 3 m:** 0.16 V.

### 7.11 Thermal summary

Per channel, the dissipation is 0.22 W overhead + I²R_SC. That is ≤ 0.3 W in normal operation
(ΔV ≤ 0.3 V) and ≤ 3.1 W at the edge.

With 2 oz outer copper and a ≈ 45 cm² column per channel, the edge case gives a board rise of
≈ 35–45 °C [I], using ≥ 15.3 cm²/W from
[docs/topics/rules/thermal.md](../../docs/topics/rules/thermal.md). The cut-out covers blocked
vents.

## 8. Parts

The lifecycle column comes from the TI and Vishay orderable addenda read on 2026-10-23, unless it
is tagged.

| Role | Mfr | MPN | Key ratings | Stress in design (margin) | Package | KiCad symbol / footprint | Datasheet | Lifecycle | 2nd source |
|---|---|---|---|---|---|---|---|---|---|
| SC switches Q_A–Q_D | TI | CSD18543Q3A | 60 V, ±20 V_GS, 8.1/9.9 mΩ at 10 V, Qg 11.1 nC, I_D 12 A (1 in² Cu), I_DM 156 A | V_DS ≤ 17.6 V (29 %); V_GS 12 V (60 %); 3.4 A rms edge (28 %); 0.16 W | VSON-CLIP 3.3×3.3 | Transistor_FET:CSD18543Q3A / Package_SON:VSON-8_3.3x3.3mm_P0.65mm_NexFET | https://www.ti.com/lit/ds/symlink/csd18543q3a.pdf | Active [P] | Infineon BSZ099N06LS5 [I] |
| Isolated dual gate driver | TI | UCC21520ADWR | VCCI 3–18 V; VDD 6.5–25 V (5 V UVLO); 4 A/6 A; 5.7 kVrms; DT 10 ns/kΩ | VCCI 12 V (67 % of 18 V); VDD 12 V (48 %); barrier ≤ 35 V | SOIC-16W | Driver_FET:UCC21520ADW / Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm | https://www.ti.com/lit/ds/symlink/ucc21520.pdf | Active (ADWR; ADW tube obsolete) [P] | Si8233 [I] |
| Oscillator | TI | CD4047BM96 | 3–18 V rec., 20 V abs. | 12 V (67 %) | SOIC-14 | 4xxx:4047 / Package_SO:SOIC-14_3.9x8.7mm_P1.27mm | https://www.ti.com/lit/ds/symlink/cd4047b.pdf | Active [P] | Nexperia HEF4047B [I] |
| 12 V gated LDO | TI | TPS7A1601DGNR | 60 V in (62 abs); 100 mA; I_SHDN 0.59 µA; EN ≥ 1.2 V | V_IN ≤ 17.6 V (29 %); 9 mA; 49 mW | HVSSOP-8 PowerPAD | custom symbol (pins §CONN) / Package_SO:Texas_DGN0008D_VSSOP-8-1EP_3x3mm_P0.65mm_EP2x2.94mm_Mask1.57x1.89mm (closest to TI DGN0008C: pad 1.6×1.92 mm mask [P]) | https://www.ti.com/lit/ds/symlink/tps7a16.pdf | Active [P] | ADI LT3014 [I] |
| 5 V always-on LDO | TI | TPS70950DBVR | 30 V in (32 abs); I_GND 1.4 µA; ±1 % | V_IN ≤ 17.6 V (55 % of abs.); 33 mW in fault | SOT-23-5 | custom symbol / Package_TO_SOT_SMD:SOT-23-5 | https://www.ti.com/lit/ds/symlink/tps709.pdf | Active [P] | TPS7A1650DGNR (Iq 5 µA) [P] |
| Reference 2.5 V | TI | REF35250QDBVR | V_IN ≤ 6 V rec., 6.5 V abs.; ±0.05 %; 0.65 µA; C_L 0.1–10 µF | 5.05 V (78 % of abs.) | SOT-23-6 | Reference_Voltage:REF35250QDBVR / Package_TO_SOT_SMD:SOT-23-6 | https://www.ti.com/lit/ds/symlink/ref35.pdf | Active [P] | REF3325 [I] |
| Quad comparator, open drain | TI | TLV7044PWR | 1.6–6.5 V; 7 V abs.; inputs 7 V abs.; hysteresis 3–25 mV | 5.05 V (72 %); inputs ≤ 3.3 V (≤ 6.1 V single fault) | TSSOP-14 | custom (pinout = Amplifier_Operational:LM324) / Package_SO:TSSOP-14_4.4x5mm_P0.65mm | https://www.ti.com/lit/ds/symlink/tlv7042.pdf | Active [P] | TLV3404IDR + external hysteresis [P] |
| NOR gate | TI | SN74LVC1G02DBVR | 1.65–5.5 V; 6.5 V abs.; I_CC ≤ 10 µA | 5.05 V (78 %) | SOT-23-5 | 74xGxx:74LVC1G02 / Package_TO_SOT_SMD:SOT-23-5 | https://www.ti.com/lit/ds/symlink/sn74lvc1g02.pdf | Active [P] | Nexperia 74LVC1G02 [I] |
| Alarm opto | Vishay | SFH617A-3X017T | V_CEO 70 V; I_F 60 mA; 5300 Vrms; creepage ≥ 7 mm; CTR 34 % min at 1 mA | I_F 2.6 mA (4 %); V_CE ≤ 30 V (43 %) | SMD-4 option 7 | Isolator:SFH617A-3X017T / Package_DIP:SMDIP-4_W9.53mm_Clearance8mm | https://www.vishay.com/docs/83740/sfh617a.pdf | Active (Rev 2.5, 2025) [P] | Everlight EL817 [I] |
| Level-shift N-FET | Diodes | 2N7002-7-F | 60 V; 115 mA | V_DS ≤ 35.2 V (59 %); 0.35 mA | SOT-23 | Transistor_FET:2N7002 / Package_TO_SOT_SMD:SOT-23 | https://www.diodes.com/assets/Datasheets/2N7002.pdf | Active (2024) [P] | Nexperia 2N7002 [I] |
| PNP (fault driver, enable shifter) | Diodes | MMBT3906-7-F | 40 V; 200 mA; hFE ≥ 100 | V_CE ≤ 17.6 V (44 %); ≤ 2.7 mA | SOT-23 | Transistor_BJT:MMBT3906 / Package_TO_SOT_SMD:SOT-23 | https://www.diodes.com/assets/Datasheets/MMBT3906.pdf | Active (2025) [P] | onsemi MMBT3906 [I] |
| Bootstrap diode | Diodes | BAS16W-7-F | 75 V; 150 mA | V_R ≤ 17.6 V (23 %); 1.3 mA average | SOT-323 | Diode:BAS16W / Package_TO_SOT_SMD:SOT-323_SC-70 | https://www.diodes.com/assets/Datasheets/BAS16.pdf (SOT-23 version read [P]; BAS16W sheet not retrieved [S]) | Active [S] | Nexperia BAS16W [S] |
| Red LED | Rohm | SML-D12V1WT86 | I_F 20 mA; V_F 2.2 V; Topr −40…85 °C | 2.6 mA (13 %) | 0603 | Device:LED / LED_SMD:LED_0603_1608Metric | https://fscdn.rohm.com/en/products/databook/datasheet/opto/led/chip_mono/sml-d12x1-e.pdf | Active [S] | Vishay VLMS1300 [S] |
| Green LED | Rohm | SML-D12M1WT86 | as above, 572 nm | 1.0 mA (5 %) | 0603 | Device:LED / LED_SMD:LED_0603_1608Metric | same | Active [S] | Vishay VLMG1300 [S] |
| NTC | Murata | NCP15WM474E03RC | 470 kΩ ±3 %, B25/85 4582 K, −40…125 °C | 10 µA (self-heating ≪ 0.1 K) | 0402 | Device:Thermistor_NTC / Resistor_SMD:R_0402_1005Metric | https://pim.murata.com/asset/pim4/ntcForTemperatureSensor/SPEC_NCP15_PDF_NTCFORTEMPERATURESENSOR | Active [P] | TDK B57230V2474 [I] |
| Flying-path resistor 0.043 Ω | Vishay | WSL2816R0430FEH | 2 W at 70 °C, 0.002–0.1 Ω, 1 % | 1.0 W edge (50 % at 70 °C; 68 % at 97 °C); 0.03 W normal | 2816 | Device:R / Resistor_SMD:R_2816_7142Metric | https://www.vishay.com/docs/30100/wsl.pdf | Active [P] | Bourns CRA2512 [I] |
| C_FLY, C_TOP, C_BOT | Murata | GCJ32EC71H106KA01L | 10 µF 50 V X7S, soft termination | ≤ 17.6 V (35 %); effective ~5–6 µF [I]; 0.6 A rms per cap at edge | 1210 | Device:C / Capacitor_SMD:C_1210_3225Metric | https://pim.murata.com/en-us/pim/details/?partNum=GCJ32EC71H106KA01%23 (mirror read [P]) | In production [P] | TDK CGA6P3X7S1H106K [I] |
| Bulk damping cap | Nichicon | UCZ1V101MCL1GS | 100 µF 35 V, 125 °C 3000 h, ESR 0.2 Ω, 270 mA at 100 kHz | 17.6 V (50 %); ripple ≤ 0.13 A normal (48 %), 0.7 A edge (exceeds rating, transient) | 8×10 mm SMD | Device:C_Polarized / Capacitor_SMD:CP_Elec_8x10 | https://www.nichicon.co.jp (UCZ series) [S] | Active [S] | Panasonic EEE-FK1V101P [S] |
| 1 µF 50 V (LDO inputs) | Murata | GRM21BR71H105KA12L | 50 V X7R | ≤ 17.6 V (35 %) | 0805 | Device:C / Capacitor_SMD:C_0805_2012Metric | Murata | Active [S] | Samsung CL21B105KBFNNNE [S] |
| 1 µF 25 V (driver VCCI, VDD, bootstrap; REF output) | Murata | GRM188R71E105KA12D | 25 V X7R | 12 V (48 %) | 0603 | Device:C / Capacitor_SMD:C_0603_1608Metric | Murata | Active [S] | Samsung CL10B105KA8NNNC [S] |
| 10 µF 25 V (LDO outputs) | Murata | GRM31CR71E106KA12L | 25 V X7R | 12 V (48 %) | 1206 | Device:C / Capacitor_SMD:C_1206_3216Metric | Murata | Active [S] | Samsung CL31B106KAHNNNE [S] |
| 2.2 µF 16 V (V5 output) | Murata | GRM188R71C225KE11D | 16 V X7R | 5 V (31 %) | 0603 | Device:C / Capacitor_SMD:C_0603_1608Metric | Murata | Active [S] | — |
| 100 nF 50 V (decoupling) | Murata | GRM188R71H104KA93D | 50 V X7R | ≤ 12 V (24 %) | 0603 | Device:C / Capacitor_SMD:C_0603_1608Metric | Murata | Active [S] | Samsung CL10B104KB8NNNC [S] |
| 470 nF 25 V (divider filters) | Murata | GRM188R71E474KA12D | 25 V X7R | ≤ 3.3 V | 0603 | Device:C / Capacitor_SMD:C_0603_1608Metric | Murata | Active [S] | — |
| 10 nF 50 V | Murata | GRM188R71H103KA01D | 50 V X7R | ≤ 9 V | 0603 | Device:C / Capacitor_SMD:C_0603_1608Metric | Murata | Active [S] | — |
| 470 pF 50 V C0G (DT pin) | Murata | GRM1885C1H471JA01D | 50 V C0G | ~0 V | 0603 | Device:C / Capacitor_SMD:C_0603_1608Metric | Murata | Active [S] | — |
| 100 pF 50 V C0G (timing) | Murata | GRM1885C1H101JA01D | 50 V C0G, ±5 % | 12 V | 0603 | Device:C / Capacitor_SMD:C_0603_1608Metric | Murata | Active [S] | — |
| 3.01 MΩ 0.1 % (wake divider) | Vishay | TNPW12103M01BEEA | 1210 thin film, ≤ 3.01 MΩ range, 0.1 % | ≤ 11.7 V each; µW | 1210 | Device:R / Resistor_SMD:R_1210_3225Metric | https://www.vishay.com/docs/28758/tnpw_e3.pdf | Active [P] | Panasonic ERA [I] |
| 1.89 MΩ 0.1 % | Vishay | TNPW12061M89BEEA | 1206 thin film, ≤ 2 MΩ | ≤ 3.3 V | 1206 | Device:R / Resistor_SMD:R_1206_3216Metric | same | Active [P] | — |
| Thick-film 1 % 0603: 4.7 Ω, 750 Ω, 10.0 k, 20.0 k, 22.1 k, 24.9 k, 100 k, 909 k, 1.00 M, 1.10 M, 2.26 M, 4.99 M (one MPN per value, CRCW0603xxxxFKEA) | Vishay | CRCW0603…FKEA | 0.1 W, 75 V, 1 Ω–10 MΩ, 1 % | Worst: R146 100 k at 35 V gives 12 mW (12 %); divider tops ≤ 17.6 V (23 % of 75 V) | 0603 | Device:R / Resistor_SMD:R_0603_1608Metric | https://www.vishay.com/docs/20035/dcrcwe3.pdf | Active [P] | Yageo RC0603FR [I] |
| Board tap fuse | Littelfuse | 0477004.MXP | 4 A T, 500 VAC/400 VDC, 1.5 kA DC [S] | 1 A normal (25 %); 4.5 A edge | 5×20 | Device:Fuse / Fuse:Fuseholder_Clip-5x20mm_Littelfuse_100_Inline_P20.50x4.60mm_D1.30mm_Horizontal | https://www.littelfuse.com (477 series) [S] | Active [S] | Schurter SPT 5x20 [S] |
| Fuse clips (2 per fuse) | Littelfuse | 01000056Z | 5×20, 10 A, 250 V | 4.5 A (45 %) | THT | (in fuse footprint) | [S] | Active [S] | Keystone 3517 [S] |
| Tap header, 5-pin | Phoenix | MSTBA 2,5/5-G-5,08 (1757271) | 12 A, 320 V (III/2) [S] | 4.5 A (38 %), 70 V | THT, 5.08 mm | Connector_Generic:Conn_01x05 / Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_5-G-5,08_1x05_P5.08mm_Horizontal | phoenixcontact.com [S] | Active [S] | Würth 691313710005 [S] |
| Tap plug, 5-pin | Phoenix | MSTB 2,5/5-ST-5,08 (1757048) | 12 A, 320 V, 0.2–2.5 mm² | 16 AWG with ferrule | — | (cable side) | [S] | Active [S] | Würth 691304100005 [S] |
| Alarm header / plug | Phoenix | 1757242 / 1757019 | 12 A, 320 V [S] | 1 mA | THT, 5.08 mm | Connector_Generic:Conn_01x02 / Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal | [S] | Active [S] | — |
| Channel enable jumper | Würth | 61300211121 + shunt 60900213421 | 2.54 mm, 3 A | ≤ 50 µA | THT | Jumper:Jumper_2_Open / Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical | we-online.com [S] | Active [S] | any 2.54 mm header |
| Mounting hole | — | M3, non-plated | — | — | — | Mechanical:MountingHole / MountingHole:MountingHole_3.2mm_M3 | — | — | — |
| Harness fuse (×5) | Littelfuse | KLKD010.T | 10 A fast, 600 VAC/VDC, DC 10 kA / 50 kA | ≤ 4.5 A (45 %); ≤ 70 V | 10×38 | off-board | https://www.farnell.com/datasheets/2603270.pdf | Active [P] | Bussmann KTK-R-10 [S] |
| In-line holder (×5) | Eaton Bussmann | HEB-AW-RLC-A | 30 A, 600 V, 13/32 × 1-1/2 in, crimp 16–8 AWG | 10 A fuse, 16 AWG | in-line | off-board | [S] | Active [S] | Littelfuse LEY [S] |
| Wire | Alpha Wire (example) | 3075 (UL1015 16 AWG, 600 V, 105 °C) | 13.2 mΩ/m | ≤ 4.5 A | — | off-board | [S] | Active [S] | any UL1015 / TXL 16 AWG |
| Ring terminal | Panduit | PV14-516R-L | 16–14 AWG, 5/16 in stud, vinyl insulated | — | — | off-board | [S] | Active [S] | TE PIDG |
| Ferrule (plug side) | Phoenix | AI 1,5-8 RD (3200030) | 1.5 mm² | — | — | off-board | [S] | Active [S] | Weidmüller H1.5 |

## 9. Placement and mechanical constraints

**Mechanical.**

- **Board.** 160 × 110 mm, 4 layers, 1.6 mm FR-4 with CTI ≥ 175. 2 oz outer and 1 oz inner copper.
  All parts on the top side.
- **Mounting.** Four M3 holes, 5 mm from the corners, on nylon standoffs.
- **Enclosure.** IP54 polycarbonate wall box, about 200 × 150 × 75 mm. M20 gland for the harness at
  the bottom and M12 for the alarm. LEDs behind a clear lid or light pipes.
- **Location.** Mount the box on the wall beside the battery rack: outside any battery box, not
  above vent caps, and below the battery top level if possible (hydrogen rises). Allow ≥ 0.5 m
  horizontal distance from flooded-battery vents [I]. Trojan forbids charging in sealed or
  non-ventilated compartments [P].
- **Harness.**
  - Five wires: T0 black; T1–T4 red with number sleeves.
  - Each ends at the battery in an insulated ring lug *stacked on top of* the main cable lug, never
    between the lug and the post.
  - The fuse holder sits within 150 mm of the lug.
  - Wires run in split loom to the plug, using ferrules.
  - For N < 4, leave the unused plug positions empty and remove JP for unused channels.
- **Heatsinking.** No heatsink. Power copper is poured on L1/L4 per net (X, Y, TAPs), with thermal
  vias under Q_A–Q_D and R101/R102.

**Board floor plan.**

- **Ordered by potential (key rule).** The three channel columns sit west → east as CH1, CH2, CH3.
  Inside each column, the "L" side (band k−1: logic, lower half-bridge, Y) is west and the "U" side
  (band k: upper driver, X) is east. Bands therefore increase monotonically west → east:
  B0 | B1 B1 | B2 B2 | B3.
- **South edge.** J1 is centred on the south edge, with fuses F1–F5 north of it in tap order west →
  east.
- **North edge.** An 8 mm ISO strip runs along the north edge, carrying J2 at the north-west corner
  and the ALM bus. The optos straddle it. LEDs and jumpers sit just south of the strip.

Relations follow. Names: channel 1 refdes shown; the same applies to k = 2, 3 with 1nn → knn.
"PWR_1" means the group of block PWR for channel 1.

```
# --- board level
edge(J1, south); edge(J2, north); near(J2, U110, loose)
array([F1,F2,F3,F4,F5], x, pitch: equal)          # tap order T0..T4 west->east
near(J1, F1, close); near(J1, F5, close)
order(x, [BAND0, BAND1, BAND2, BAND3])             # NEW: potential-monotonic order
array([CH1, CH2, CH3], x, pitch: equal)            # NEW: array of groups (channel columns)
strip(north, 8mm, ISO)                             # NEW: reserved edge strip for a domain
separate(ISO, BAND*, 4.0, 4.0, slot: no)
separate(BAND0, BAND3, 1.5, 1.0, slot: no); separate(BAND0, TAP4, 1.5, 1.0, slot: no)
separate(BAND1, TAP4, 1.5, 1.0, slot: no)
separate(BAND_j, BAND_j+2, 0.6, 0.6, slot: no)     # for j = 0,1 (and X/Y/boot nets per §6)
keepout(H1..H4, copper, all, radius 4.0mm)
side(all, top)

# --- PWR_1 (SC cell), 2x2 FET quad around C_FLY
group(PWR_1)
array([Q103, Q101], x, pitch: equal); array([Q104, Q102], x, pitch: equal)  # Y column west, X column east
align([Q103, Q104], x); align([Q101, Q102], x)
array([C101..C108], y, pitch: equal)               # C_FLY bank between the columns
symmetric([Q103,Q104], [Q101,Q102], axis: C_FLY centre line)
near(R101, Q101.1, tight); near(R101, C101, tight) # X side
near(R102, Q103.1, tight); near(R102, C108, tight) # Y side
near([C109..C112], Q101.5, tight); near([C109..C112], Q103.5, tight)  # C_TOP across top row
near([C113..C116], Q102.1, tight); near([C113..C116], Q104.1, tight)  # C_BOT across bottom row
hot_loop([C109.1, Q101.5, Q101.1, R101.1, R101.2, C101.1, C101.2, R102.1, R102.2, Q103.1, Q103.5, C109.2],
         "phase-1 commutation: C_TOP -> Q_A -> R_CFX -> C_FLY -> R_CFY -> Q_C -> C_TOP")
hot_loop([C113.1, Q102.1, Q102.5, R101.1, R101.2, C101.1, C101.2, R102.1, R102.2, Q104.5, Q104.1, C113.2],
         "phase-2 commutation: C_BOT(TAP1) -> Q_B -> X -> C_FLY -> Y -> Q_D -> TAP0")
near(C117, [C109..C112], close); near(C118, [C113..C116], close)
near(R103, Q101, close); near(R104, Q103, close)
thermal(R101, 1.0W, copper); thermal(R102, 1.0W, copper)
thermal([Q101,Q102,Q103,Q104], 0.16W each, copper + vias)
far(RT101, [C117, C118])                           # NTC senses R_CF/FETs, not bulk caps
near(RT101, R101, close); near(RT101, Q101, close)
pour(TAP0, TAP1, TAP2, CH1_X, CH1_Y: L1+L4, min_width 3mm)   # NEW: copper pours per power net

# --- DRV_1
group(DRV_1)
near(U101, Q101, close); near(U101, Q102, close)   # east side
near(U102, Q103, close); near(U102, Q104, close)   # west side
near(R105, Q101.4, tight); near(R106, Q102.4, tight); near(R107, Q103.4, tight); near(R108, Q104.4, tight)
hot_loop([U101.15, R105.1, R105.2, Q101.4, Q101.1, U101.14], "upper high-side gate loop")
hot_loop([U101.10, R106.1, R106.2, Q102.4, Q102.1, U101.9], "upper low-side gate loop")
hot_loop([U102.15, R107.1, R107.2, Q103.4, Q103.1, U102.14], "lower high-side gate loop")
hot_loop([U102.10, R108.1, R108.2, Q104.4, Q104.1, U102.9], "lower low-side gate loop")
near(C129, U101.16, tight); near(D101, U101.16, close); near(C130, U102.16, tight); near(D102, U102.16, close)
near(C121, U101.3, tight); near(C123, U102.3, tight); near(C125, U101.11, tight); near(C127, U102.11, tight)
near(R113, U101.6, tight); near(R114, U102.6, tight)
keepout(U101 body between pin rows 1-8 and 9-16, copper, all)   # barrier under isolator
keepout(U102 body between pin rows, copper, all)
orient(U101, input_side: west); orient(U102, input_side: west)  # NEW: barrier faces potential gradient

# --- OSC_1
near(U103, U101.1, close); near(U103, U102.1, close)
matched([CH1_PH1, CH1_PH2] to U101 and U102, length_tolerance: loose)  # NEW
near(R115, U103.2, tight); near(C131, U103.1, tight)
far(U103, [CH1_X, CH1_Y])

# --- SUP_1 / SUPV_1 (quiet BAND0 corner, west of PWR_1)
group(SUPV_1); group(SUP_1)
far(SUPV_1, PWR_1)                                  # divider nodes are 0.2-1 Mohm
near(U104, U102, close); near(U105, U101, close)
near(U108, U107, close); near([C143,C144,C145,C146,C147], U108, tight)
connect_at(TAP2 -> R120, R125, R129, at: C109.1)    # NEW: sense taps at C_TOP pads (channel side of fuses)
connect_at(TAP1 -> R133, at: C113.1)
connect_at(TAP0 -> R123,R124,R127,R128,R131,R132,R135,R136, at: C113.2)
guard(CH1_PON, CH1_PLO, CH1_PHI, CH1_N, ring: TAP0)  # NEW: guard ring for high-Z nodes
near(Q106, Q107, loose); near(Q107, U105, close)
edge([D103, D104, JP101], north); align([D103, D104, JP101], x)
near(U110, [D103], close); straddle(U110, BAND0 | ISO)  # NEW: part spans a barrier
```

**Vocabulary added beyond the given list.**

- `order(axis, domains)`: monotonic potential order, so physical neighbours are electrical
  neighbours.
- `array` / `align` / `symmetric` applied to *groups*: the three channel columns.
- `strip(edge, depth, domain)`: reserves an edge band for one domain.
- `pour(net, layers, width)`: copper for power and thermal.
- `orient(refdes, side → direction)`: which pin row of an isolator faces which domain.
- `connect_at(net → pins, at: pad)`: sense/Kelvin take-off point.
- `guard(nets, ring)`: guard ring for high-impedance nodes.
- `matched(nets)`: equal delay to two drivers.
- `straddle(refdes, A|B)`: a part that intentionally bridges a barrier.

The block/domain model was also missing two things:

- **Bands of shared reference**, which are not the same as domains.
- **Nets that ride on a switching node plus an offset** (BSTU = X + 12 V). Their worst-case
  potential to T0 must be derived, not declared.

## 10. Verification plan

Equipment:

- Four 12 V AGM batteries (or four 0–20 V, ≥ 5 A bipolar supplies, each with 10 mF across it)
- A 0–70 V charger emulator
- µA meters in every tap
- A thermal camera
- An oscilloscope with isolated probes

| ID | Test / simulation | Pass criterion |
|---|---|---|
| S-1 | SPICE of one SC cell (TI CSD18543 and UCC21520 models): sweep ΔV, C, R_on; start-up from precharge; DT and skew corners | R_SC 0.48–0.57 Ω; no overlap; first-cycle current ≤ 2 × steady |
| S-2 | Monte Carlo of the wake, ratio and NTC thresholds (1 % / 0.1 % parts, offset, hysteresis) | Matches §7.7 bounds |
| V-1 | N = 2, 3, 4 with jumpers; unused channels dark | No false FAULT; correct channels ACTIVE |
| V-2 | Pair 21–35.2 V sweep (10.5–17.6 V per battery), −20 / +25 / +50 °C chamber | Stable operation; LDOs regulate |
| V-3 | Imposed ΔV 0.05–1.0 V; measure tap currents | ≥ REQ-6; within ±25 % of §7.4 |
| V-4 | Coulomb-count transfer between two batteries, 24 h; measure overhead power | Transfer efficiency ≥ 97 % at ΔV 0.3 V; overhead ≤ 0.25 W per channel |
| V-5 | Sleep current in each tap at 12.8 V per battery | ≤ 50 µA each; max difference ≤ 40 µA |
| V-6 | Ramp the pair voltage slowly | Wake 26.39 ± 0.17 V; sleep ≥ 26.12 V; green LED follows |
| V-7 | Ratio sweep at rest and running: replace one battery with a supply | Lockout at r = 1.088 / 0.907 ± 1.5 %; red LED and alarm |
| V-8 | Edge test: ΔV_board ≈ 1.15 V, 0.3 m harness, blocked vents | Thermal trip 92–99 °C; no part above its rating |
| V-9 | Fault: board short TAP1–TAP2 behind the fuses with batteries; also TAP0–TAP4 | Board fuse clears; harness fuse intact; no smoke |
| V-10 | Fault: short Q101 drain–source (and Q104) before power-up, then charge | Fuses clear on the first phase-2; no fire; other channels OK |
| V-11 | Fault: short one C_FLY, one C_TOP MLCC; short C117 | Fuses clear; damage confined |
| V-12 | 100 random-order hot-plugs of J1; pull each tap fuse in turn while running and at rest | No damage; open tap → FAULT on affected channels |
| V-13 | Mis-wiring with 2 A current-limited supplies first, then batteries: swap T1/T2, reverse B2, T0↔T4 | Fuses clear; no fire; record FET survival (Q-11). The installation procedure's pre-plug voltage check catches all cases. |
| V-14 | Alarm isolation hi-pot 1.5 kV DC, 60 s, all taps tied vs ALM_C/E; contact rating 30 V/1 mA | No breakdown; V_CE(sat) ≤ 0.4 V |
| V-15 | Open battery under 50 A inverter load: open a link in the string | Tap fuses clear; board otherwise intact |
| V-16 | 30-day float with two deliberately mismatched batteries (−0.3 V start) | ΔV converges to ≤ 0.1 V per pair |
| V-17 | Inspection: KiCad DRC with the §6 band rules as custom rules; creepage check on J1, fuses, opto | Zero violations |

## 11. Sources

**Batteries.**

- Trojan T-1275 datasheet (2016), [P]: https://cdn.autosolar.es/pdf/TROJAN-T1275.pdf
  - Charger settings and temperature compensation
  - OCV vs SOC
  - Self-discharge 5–15 %/month
  - Operating −20…45 °C
- AIMS Power AGM12V200A, [P]: https://trek.systems/wp-content/uploads/2025/07/AGM12V200A.pdf
  - ≤ 4 mΩ, 3300 A short circuit
  - 3 %/month self-discharge
  - Cycle 2.40–2.45 V/cell, standby 2.20–2.30 V/cell, −30/−20 mV/K

**Commercial balancers and ICs.**

- HA02 equalizer brochure, [V]: https://www.aussiebatteries.com.au/assets/brochures/EQHA02.pdf.
  HA01 listing: https://scccltd.com/products/ha01-24v-battery-equalizer-2x-12v-balancer.
  Forum reports: https://powerforum.co.za/topic/1252-ha-02-balancers/ [S].
- Victron Battery Balancer specifications, [S]:
  https://backwoodssolar.com/product/victron-energy-battery-balancer/
- ADI LTC3305, [S]: https://www.analog.com/en/products/ltc3305.html;
  https://www.electronicdesign.com/technologies/power/power-supply/pmics/article/21198015/battery-balancing-ic-works-with-up-to-four-12-v-batteries-in-series
- ADI LTC7820, [S]: https://www.analog.com/en/products/ltc7820.html;
  https://www.analog.com/en/resources/design-notes/high-efficiency-high-density-switched-capacitor-converter-for-high-power-applications.html
  The datasheet https://www.analog.com/media/en/technical-documentation/data-sheets/7820fc.pdf
  was not retrievable.

**TI datasheets [P]**, each at https://www.ti.com/lit/ds/symlink/<part>.pdf:

- ucc21520 (SLUSCJ9F)
- csd18543q3a (SLPS633)
- cd4047b (SCHS044C)
- tps7a16 (SBVS171F)
- tps709 (SBVS186H)
- ref35 (SNAS809C)
- tlv7042 (SLVSE13J, covers TLV7044)
- sn74lvc1g02 (SCES213Y)
- tlv3404 (SLCS135B, alternative)

**Other vendors [P].**

- Diodes: 2N7002 (DS11303), MMBT3906 (DS30059), BAS16 (Zetex 1996).
- Vishay: SFH617A (83740), WSL (30100), CRCW (20035), TNPW (28758).
- Murata: NCP15 spec; GCJ32EC71H106 product sheet via mirror
  https://extranet.mandieselturbo.com/electronics/datasheets/muRata/GCJxx_series/GCJ32EC71H106MA01.pdf
- Rohm: SML-D12x1.
- Littelfuse KLKD (POWR-GARD): https://www.farnell.com/datasheets/2603270.pdf

**Secondary [S].**

- Littelfuse 477 series: https://www.littelfuse.com/products/fuses/cartridge-fuses/5x20mm-fuses/477.aspx
- Littelfuse MINI 58V (1000 A at 58 VDC; rejected, below 70 V)
- Eaton HEB-AW-RLC-A:
  https://steinerelectric.com/Catalog/FusesFuse-Blocks-And-Fuse-Holders/Fuse-Holders/In-Line-Fuse-Holders-And-Insulators/Bussmann-HEB-AW-RLC-A-Tron-HEB-Fuse-Holder600-VAC30-A16-to-8-AWG-Wire1-Pole-5477
- Phoenix MSTB/MSTBA: https://automa.net/product/phoenix-contact/1757019-63a36f14ca04b4f2592acf7e
- Nichicon UCZ: https://ibselectronics.com/products/nichicon/ucz1v101mcl1gs
- Littelfuse 01000056Z: https://ie.farnell.com/littelfuse/01000056z/cartridge-fuse-clip-5x20mm-10a/dp/2762086

**Repository docs.**

- [isolation-creepage.md](../../docs/topics/rules/isolation-creepage.md): IPC-2221B and
  IEC 60664-1 values via TI SLUP419
- [chargers-bms.md](../../docs/topics/rules/power/chargers-bms.md)
- [hot-loops.md](../../docs/topics/rules/power/hot-loops.md)
- [thermal.md](../../docs/topics/rules/thermal.md)
