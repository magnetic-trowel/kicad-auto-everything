# leadacid-balancer: MCU-free switched-capacitor equalizer for 2–4 series 12 V lead-acid batteries

Status: engineering design, encoded in [design.py](design.py) and [parts.py](parts.py). `kaesynth
build` passes with 0 errors and 0 warnings (31 findings waived with reasons), KiCad ERC 0/0, netlist
round trip identical. Independently reviewed ([REVIEW.md](REVIEW.md), with the response at its end);
not built or certified; four blocking questions are open. Naming
rules and pin rationale are in [CONNECTIONS.md](CONNECTIONS.md).

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
  - Every tap is fused twice: a 10 A, 600 VDC, 10 kA DC midget fuse at the battery post, and a 6 A
    one of the same family (KLKD) on the board.
  - No single component spans two or more batteries with a low-impedance path.
  - Each channel stops and lights a red LED when its battery ratio leaves the 0.890–1.115 worst-case window (nominal 0.918/1.084;
    a shorted cell,
    a dead battery, or an open tap found by the periodic tap check).
  - Board copper is ordered by potential, so only electrically adjacent domains are physically
    adjacent.
  - The alarm output is opto-isolated and fail-safe (closed only while charging healthily).
- **Efficiency.** Asleep: ≤ 39 µA per battery, with ≤ 29 µA difference between batteries. A
  channel wakes only while a charger holds its pair at ≥ 13.2 V per battery. Active overhead is
  0.28 W per channel, paid by the charger.
- **Part count:** 465 placed parts (151 per channel × 3, and 12 at board level), plus 11 BOM-only
  board items (shunts, fuse holders) and the off-board harness. Eleven distinct semiconductors plus two LEDs. Datasheets were read for all of them except the SOT-323 BAS16W (its SOT-23 sibling was read).

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
| REQ-6 | Balancing current with the REQ-22 harness, worst case incl. finite tap capacitance and tap-check pauses | ≥ 0.09 A at ΔV = 0.1 V; ≥ 0.26 A at ΔV = 0.3 V (relaxed from 0.10/0.30 after review MINOR-1) | derived §7.2, §7.4 | V-3; calcs `i_bal_*` |
| REQ-7 | Charge-transfer efficiency | ≥ 97 % for ΔV ≤ 0.3 V | brief ("as efficient as possible") | V-4 |
| REQ-8 | Active overhead per channel | ≤ 0.30 W (0.25 W before the fail-safe alarm LED), only while a charger is present | derived | V-4 |
| REQ-9 | Sleep current per battery / mismatch between batteries | ≤ 50 µA / ≤ 40 µA | derived from "as efficient as possible" (no drain at rest) | V-5 |
| REQ-10 | Wake threshold (pair voltage) | rising 26.30–26.75 V worst case (26.45 V nominal, 13.23 V per battery); falling ≥ 26.15 V | derived §7.7 (Q-2) | V-6 |
| REQ-11 | Ratio lockout (stop, red LED, alarm open) and imbalance warning (alarm open, keeps running) | lockout 0.918 / 1.084, warning 0.960 / 1.044 nominal; ±1.5 % on V_pair/V_bot (§7.7) | derived: a shorted cell gives 0.833 / 1.20 | V-7; calcs `ratio_*`, `warn_*` |
| REQ-12 | Window-edge dissipation per channel (failing battery, worst tolerances) / thermal cut-out | ≤ 7.2 W at 50 °C ambient, ≤ 9.5 W at −20 °C / 91–101 °C | derived §7.6 | V-8 |
| REQ-13 | Fault containment | No single fault causes a sustained short or connects ≥ 2 batteries through < 100 kΩ. Every board fault current is interrupted by an on-board fuse. | brief ("no pathways") | FMEA §4; V-9…V-15 |
| REQ-14 | Tap fusing | At the battery end (≤ 150 mm from the post): ≥ 80 VDC rating, ≥ 10 kA DC interrupt. On board: ≥ 80 VDC, ≥ 1 kA. | brief + derived §7.10 | Inspection; V-9 |
| REQ-15 | Spacing | Adjacent battery domains 0.6/0.6 mm; non-adjacent 1.5/1.0 mm; ISO 4.0/4.0 mm (§6) | IPC-2221B; IEC 60664-1 [S] | KiCad DRC (`.kicad_dru`); inspection |
| REQ-16 | Hot-plug | Any mating order of the tap plug, any missing tap and any broken tap wire: no damage | derived | V-12 |
| REQ-17 | Mis-wiring (swapped taps, reversed battery) | No fire. On-board fuses clear. FETs and the affected channel's logic LDOs may need replacement. | derived | V-13 |
| REQ-18 | Ambient | −20 to +50 °C, indoor, pollution degree 2, ≤ 2000 m | derived (Trojan −20…+45 °C [P]) | Analysis |
| REQ-19 | Control | No MCU and no firmware | decision §5 | Inspection |
| REQ-20 | Indication per channel | Green ACTIVE, red FAULT (lockout or over-temperature) | brief ("robust", status) | V-6, V-7 |
| REQ-21 | Telemetry | One isolated fail-safe contact: closed only while every channel charges without fault or warning; opens on fault, warning, open tap or lost supply; open at rest. ≤ 30 V, ≤ 1 mA, reverse-protected. | derived; review M-4 | V-14; calcs `opto_*` |
| REQ-22 | Harness | N + 1 wires: system negative plus every battery positive. 14 AWG ≤ 3 m (16 AWG ≤ 1.5 m). Ring terminals. Fused. Pluggable at the board. Thinner wires are not possible because R_ext must stay small against R_SC ≈ 0.5 Ω. | brief; REQ-6 | Inspection |
| REQ-23 | Service | Board can be unplugged in one action to replace a battery | derived | Inspection |
| REQ-24 | Component derating | Normal operation: semis ≤ 80 % V; caps ≤ 80 % V (DC bias counted); resistors ≤ 50 % P; fuses ≤ 75 % I. Abnormal window edge (failing battery): ≤ 100 % of the temperature-derated rating | task default | kaesynth `rating.*`; waivers in the build report |
| REQ-25 | Battery-count configuration | Shunts on JP101…JP(N−1)01; a shunt on JPk02 for each unused channel (bridges its alarm opto); every unused plug position bridged to the highest used one. Default N = 4 (`N_BATT`). | REQ-1; H-12 | V-1; label at J1 |

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
| ASM-11 | The alarm circuit (ALM_E) stays within ±100 V of T0 | Sets the ISO barrier working voltage (§6) |

| ID | Question for a human | Blocking? |
|---|---|---|
| Q-1 | Confirm the supported N = 2–4. Is a > 4-battery (96 V) bank needed? Two boards can overlap by one battery, but a > 70 V stack is outside this design's safety analysis. | **BLOCKING** |
| Q-2 | Which battery model and charger set-points (float, absorb, equalize, temperature compensation)? The wake threshold is 13.23 ± 0.09 V per battery. Float below ≈ 13.3 V, for example a hot room or a 13.2 V AGM float, may never wake the balancer. It is set by R120–R125. | **BLOCKING** |
| Q-3 | Are flooded batteries equalized at 16.2 V or more? Then the stack exceeds 60 VDC (ES2), which drives labelling and enclosure requirements. | no |
| Q-4 | MLCCs and an electrolytic sit directly across each battery. If one shorts, the on-board fuse clears and the battery is not shorted indefinitely. Is that acceptable, or must these caps be series-redundant pairs? Pairs add 16 caps per channel and an 8 mm larger board. | **BLOCKING** |
| Q-5 | Board fuse DC breaking capacity. **Closed (review B-1):** the 477 4 A T breaks only 500 A at 400 VDC; replaced by KLKD006.T (10 kA DC, datasheet read). | no |
| Q-6 | Phoenix MSTB/MSTBA ratings, Eaton HEB holder data and Nichicon UCZ data are [S]. Verify them. | no |
| Q-7 | Is the isolated alarm wanted, and what will it drive (voltage and polarity)? | no |
| Q-8 | Should the balancer also run during discharge or rest (0.84 W continuously)? A burst mode (switch only while \|ΔV\| > ~30 mV) could cut float overhead. | no |
| Q-9 | Conformal coating (acrylic, IPC-CC-830)? Recommended for battery-room humidity and acid mist. | no |
| Q-10 | Re-evaluate the ADI LTC7820 integrated SC controller once its datasheet can be read (§5, option B2) | no |
| Q-11 | Is "board survives mis-wiring without FET damage" a requirement? If so, add per-channel reverse protection (§4 H-5). | no |
| Q-12 | Certification target (UL 1973 / IEC 62368-1)? If yes, the spacing must be re-derived from purchased standards. | **BLOCKING** if yes |
| Q-13 | How many batteries will this unit serve? It sets `N_BATT`, the shunts and the plug bridges (REQ-25). Default N = 4. | no |
| Q-14 | Should the imbalance warning be delayed (e.g. sustained > 1 h) before it opens the alarm? Today it opens at once, also after a battery is replaced. | no |

## 4. Hazards

| ID | Hazard | Cause | Mitigation (block / part) | Survives one more fault? |
|---|---|---|---|---|
| H-1 | Arc, fire or burns from a battery short through the harness. One 200 Ah AGM delivers 3.3 kA, and internal R ≤ 4 mΩ [P]. | Chafed or crushed tap wire; tool across terminals | KLKD010 fuse (600 VDC; DC 10 kA UL 248-19, 50 kA UL 248-14 [P]) in a sealed in-line holder ≤ 150 mm from each post (HARNESS). 600 V insulation. Loom and strain relief. | Yes for a wire fault. The ≤ 150 mm pigtail before the fuse is unprotected: double-insulate and clamp it. |
| H-2 | Fire on the board | Shorted FET, flying cap or bulk cap; contamination | On-board KLKD006.T 6 A, 600 VDC, 10 kA DC fuse per tap (F1–F5). Prospective current 128–194 A for one battery, ≤ 670 A for the full stack (§7.10). | Yes: the harness fuse backs up the board fuse. |
| H-3 | Two or more batteries bridged ("voltage jumping") | Creepage failure; a component spanning taps | Potential-ordered layout (§9). Spacing rules (§6). No part spans ≥ 2 batteries except the divider strings (≥ 4.99 MΩ), the level shifter (2 × 49.9 kΩ in series, so ≥ 49.9 kΩ after any single short) and certified isolation barriers (UCC21520, SFH617A). Each string's top resistors are also split. | Yes |
| H-4 | Balancer drains good batteries into a failed one | Shorted cell (−2.1 V) | Ratio lockout ~±9 % (U108 B/C, 0.1 % strings) stops the channel and opens the alarm | Lockout and thermal cut-out are independent comparators |
| H-5 | Mis-wiring: swapped taps or a reversed battery | Installer | Keyed single plug, numbered and colour-coded wires, and a pre-plug voltage check (V-13 procedure). Body diodes conduct and the 6 A fast fuse clears in ms at ≈ 70 A [I]. | No fire. FETs and the logic LDOs of the affected channel may fail; the fuse still clears. |
| H-6 | Hydrogen ignition (LEL 4 %) | Flooded or overcharged cells vent H₂; plug spark (22 mJ per battery leg); fuse operation | Enclosure outside the battery box and not above vents. Plug only at the board, away from the batteries. Harness fuses are enclosed. No relays. | Yes |
| H-7 | Board overheating | Failing battery holding r at the window edge: up to 6.4 W per channel at 50 °C, 8.6 W at −20 °C (§7.6); blocked vents | Thermal cut-out at 91–101 °C (NTC + U108 D). R_CF doubled to stay within rating at the cut-out temperature. | Yes: the window and the cut-out are independent. |
| H-8 | Shock | Stack up to 70.2 VDC (ES2 during cold equalize) | Enclosure; pluggable insulated connector; alarm opto with basic insulation (§6) | Yes |
| H-9 | Bank drained in storage | Balancer awake at rest | Wakes only at ≥ 13.2 V per battery. Sleep ≤ 39 µA. A stuck-awake fault costs 0.28 W per channel, and the green LED shows it. | Partial: needs a human to see the LED |
| H-10 | Battery opens internally under load | Broken strap | That position reverses. Body diodes carry string current until the tap fuses clear (ms). | Yes (fuses) |
| H-11 | Corrosion or leakage across divider nodes | Acid mist, humidity | Strings ≤ 10 MΩ. Conformal coat (Q-9). IP54 box. | Yes |
| H-12 | Unused or broken top tap floats | N < 4 without plug bridges, or a broken T_H wire | The divider strings pull the floating tap ≈ 0.8 V below T_M through body diodes, at µA, which reverse-biases that channel's upper LDO and bulk cap. Mitigation: plug bridges (§9), and the ratio window lights FAULT on a broken wire. | No fire; LDO stress at µA only |
| H-13 | Failing battery absorbs amps during charge (internal heating, dry-out) | Soft short, high self-discharge | Imbalance warning ~±4 % (U111 B/C) opens the alarm while the channel keeps running; ≤ 2.4 A before it opens (review M-3) | No: needs someone to act on the alarm (Q-14) |
| H-14 | Broken tap wire goes unnoticed | T0, or a middle tap while charging: the SC cell holds the floating node at a plausible voltage | Tap check: U111 D pauses both drivers 1.5 s every 32.5 s; LDO loads slew a floating tap out of the window, a floating T0 collapses CH1's V5; the fail-safe series contact opens (review M-4) | Partial: at rest the contact is open by design |

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
- **C** loses 10–15 % of every amp it moves, whatever ΔV is. Moving 1 Ah at 0.3 V costs ≈ 2 Wh in C
  against ≈ 0.3 Wh in B. It adds a magnetic part, current sensing and a direction comparator, and a
  shorted switch shorts a battery through the inductor. Its only advantage, current near balance,
  is small for lead-acid's steep OCV. The HA02 claims "energy transfer, 0–10 A, starts at 10 mV"
  [V]; its topology is unpublished and no teardown was found.
- **D** needs a fifth, continuously cycling battery. Its FET matrix reaches every position, so one
  shorted switch plus normal sequencing can put the auxiliary battery across non-adjacent taps,
  which violates "no pathways". Its datasheet was not readable here; ADI lists it as recommended for new designs [S].
- **E** needs custom magnetics per N. Winding insulation must hold the full stack, and one winding
  fault couples every tap.
- **B2** is B's physics with fewer parts and would be preferred once verified. Its datasheet could
  not be retrieved. Its prebalance sources ≈ 93 mA into VLOW and its fault window assumes a
  capacitor, not a battery, on VLOW [S/I]. Whether its input-current OCP works in reverse flow is
  unknown (Q-10).

**Decisions.**

- **MCU-free.** Wake, two ratio limits and temperature are four comparisons: a CMOS gate and
  nanopower comparators do them with ≈ 5 µA and no firmware, brown-out or programming failure modes.
- **Three independent channels,** not a shared ladder: no clock crosses between channels, a channel
  needs only its own three taps, and N = 2–4 comes from disabling channels. The cost is that middle
  batteries carry two channels' sleep current (≤ 26 µA difference, §7.9).

**Lead-acid specifics** (numbers in §7.1). OCV slope ≈ 13.5 mV per % SOC; float 13.2–13.8 V,
absorption 14.4–14.8 V, equalize 16.2 V (flooded only); −30 mV/K per battery (Trojan, AIMS [P]).
In a series string every battery carries the same current, but self-discharge (AGM 3 %/month,
flooded 5–15 %/month [P]), charge acceptance and temperature differ, while the charger controls only
the total voltage: the high battery is overcharged (gassing, dry-out), the low one undercharged
(sulfation). Equalizing voltage during charge and float is the right target, because float and
absorption limits are per-cell voltage limits. It does not repair capacity mismatch, does not
replace the periodic equalize charge of flooded batteries, and must not "rescue" a battery with a
shorted cell (hence the ratio lockout). The balancer therefore runs only while a charger holds the
pair above 13.2 V per battery, and stops on gross mismatch.

## 6. Blocks and domains

Tap numbering:

- T0 = system negative. Tk = positive of battery Bk (k = 1…4). The board nets are TAP0–TAP4.
- Channel k (k = 1…3) spans B_k (bottom) and B_{k+1} (top), with T_L = TAP(k−1), T_M = TAPk and
  T_H = TAP(k+1).

Blocks in [design.py](design.py) (one schematic sheet each):

| Block | Function | Ports (domain, voltage, current) |
|---|---|---|
| `input` | J1 tap header; fuses F1–F5 | TAPj_IN → TAPj: 0–70.2 V; ≤ 2.0 A normal, 8.8 A at the window edge |
| `ch1`–`ch3` | One channel each, five functions (placement clusters `chk.pwr`, `.drv`, `.osc`, `.sup`, `.supv`): PWR SC cell (Q_A–Q_D, R_CF, C_FLY, C_TOP/C_BOT); DRV two isolated half-bridge drivers, bootstrap, dead time; OSC CD4047 at 100 kHz; SUP 12V_L/12V_U/V5 LDOs, enable level shifter, jumper; SUPV reference, quad comparator, dividers, NTC, NOR, LEDs, opto | T_L, T_M, T_H; ALM_C/ALM_E (ISO, ≤ 30 V, ≤ 1 mA) |
| `alarm` | J2, reverse diode D1 and the series alarm chain | ALM_C → D1 → ALM_S1…S3 → ALM_E |
| `mech` | Mounting holes | — |
| `harness` (`board="off"`) | N + 1 fused tap wires, ring lugs, plug P1, bridges, alarm plug P2 | POSTj → TAPj_IN |

**Domains (the kaesynth voltage model).** Every net belongs to one domain and has a voltage range
relative to the domain's reference. A floating domain sits on a net of another domain, so the checker
sums ranges along the chain and stacked batteries come out exact.

| Domain | Reference | Members | Range to its reference |
|---|---|---|---|
| B1 (root) | TAP0 | TAP0, TAP1 and every net referenced to TAP0: CH1 "L" side (V5, 12V_L, comparators, OSC, driver inputs, lower driver output B, Y) | TAP1: 0–20 V (one battery); 12 V rails 0–12.5 V |
| Bk (k = 2…4) | TAP(k−1) | TAPk and every net referenced to TAP(k−1): CH(k−1) "U" side (12V_U, upper driver output B, X) and CHk "L" side | as B1 |
| CHk_HSU | CHk_X | BSTU, OA_U, GA, C_FLY + | 0–12.5 V (−2 V for ≤ 200 ns on the gate) |
| CHk_HSL | CHk_Y | BSTL, OA_L, GC, C_FLY − | as HSU |
| CHk_LS | T_H | base of Qk07 | −1…0 V |
| CHk_QFB | CHk_V5 | base of Qk05 | −0.8…0 V |
| CHk_SPAN | T_L | nets that swing across both batteries of the pair: PON_A, LSD, LSM | 0–40 V |
| ISO (root) | ALM_E | ALM_C | 0–30 V; ALM_E within ±100 V of T0 (ASM-11) |

The "bands" of the potential-ordered layout are these battery domains; CHk_SPAN keeps the three
nets that straddle two batteries out of them, so every band stays within 30 V inside (0.2 mm
in-domain clearance for fine-pitch parts). A domain must hold its top tap
(its reference lives in the domain below), so adjacent battery domains can be up to 2 Vb + 14.5 V
apart (TAP(k+1) + bootstrap against TAP(k−1)). The rule for adjacent bands is therefore the 31–50 V
row, not the 0–30 V row of the first draft.

**Barriers.** Pollution degree 2, material group IIIa, ≤ 2000 m. The `.kicad_dru` carries each pair;
floating domains inherit their parent's rules.

| Pair | Grade | Working V (DC) | Standard and table | Required creepage / clearance | Board rule (creepage / clearance) |
|---|---|---|---|---|---|
| Adjacent battery domains (B1/B2, B2/B3, B3/B4) | Functional | ≤ 49.7 (2 × 17.6 + 14.5) | IPC-2221B Table 6-1, B2 31–50 V [S] | 0.6 / 0.6 mm | **0.6 / 0.6 mm**. Inside parts: per footprint. |
| Non-adjacent (B1/B3, B2/B4, B1/B4) | Functional | ≤ 84.9 | IPC-2221B B2 51–100 V: 0.6 mm [S]; IEC 60664-1 F.4 PD2 MG III: 63 V 1.25 mm [P via SLUP419 in repo], 80–100 V 1.3–1.4 mm [S] | 1.4 / 0.6 mm | **1.5 / 1.0 mm**: margin; fails to a fuse, not to shock |
| Any stack domain ↔ ISO (alarm) | Basic (ES2 → ES1) | ≤ 185 (84.9 + 100, ASM-11) | IEC 62368-1; IEC 60664-1 F.4 PD2 MG IIIa at 200 V 2.0 mm [S]; F.2 1.5 kV impulse 0.5 mm [S] | 2.0 / 0.5 mm | **4.0 / 4.0 mm**, no copper under SFH617A (package ≥ 7 mm, CTI 175 [P]); hi-pot 1.5 kV DC |
| Copper ↔ board edge, holes and metal hardware | Basic | ≤ 84.9 | as above | 1.4 / 0.5 mm | 1.5 mm edge clearance (domain rule); 4.0 mm copper-free ring at holes; nylon standoffs |

Spacing details are in [docs/topics/rules/isolation-creepage.md](../../../../../docs/topics/rules/isolation-creepage.md).
No slots are needed.

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
- R_loop = 2 · R_on (8.1–13.9 mΩ [P], hot ×1.4 [I]) + 2 × 0.043 Ω (R_CF: R101‖R152 and
  R102‖R153, 2 × 0.086 Ω each) + 5 mΩ ESR and copper = 0.107–0.119 Ω

Result: **R_SC = 0.476–0.567 Ω, nominal 0.51 Ω** (calcs `r_sc_*`). It is insensitive to C because the cell runs mostly
in fast-switching mode. The flying current is near-square, with I_rms = 2.13 · I_bal, and the FET
current is I_rms = 1.51 · I_bal.

### 7.4 Balancing current and wiring

Per tap: R_tap = KLKD010 (12.8 mΩ [P]) + wire × L + 3 mΩ (lugs and plug) + KLKD006 board fuse (26.1 mΩ [P]).
14 AWG is 8.28 mΩ/m, 16 AWG 13.2 mΩ/m [S].

Per channel: R_ext = R_H + 4 · R_M + R_L + 2 · R_int = 6 · R_tap + 8 mΩ. The middle tap carries
2 · I. This gives 0.27 Ω at 0.3 m and 0.41 Ω at 3 m of 14 AWG.

**The encoding check changed the harness.** With 16 AWG at 3 m (R_ext 0.49 Ω) and the worst R_SC
(0.567 Ω), 0.1 V drives only 0.095 A. The review's periodic-steady-state model (finite C_TOP/C_BOT)
gives a further ×0.92, and the tap-check pauses ×0.955. REQ-6 is therefore ≥ 0.09 A at 0.1 V and
≥ 0.26 A at 0.3 V (worst case 0.090 / 0.270 A with 14 AWG ≤ 3 m or 16 AWG ≤ 1.5 m, calcs `i_bal_*`);
a 0.1 A float mismatch still settles at ≤ 0.11 V per pair. The table below is nominal formula values.

| ΔV at the posts | I_bal, nominal R_SC (0.3 m / 3 m 14 AWG) | Board loss I²·R_SC | Transfer efficiency 1 − ΔV/13.5 V |
|---|---|---|---|
| 0.05 V | 0.064 / 0.055 A | 2 / 2 mW | 99.6 % |
| 0.10 V | 0.128 / 0.109 A | 8 / 6 mW | 99.3 % |
| 0.20 V | 0.26 / 0.22 A | 34 / 25 mW | 98.5 % |
| 0.30 V | 0.38 / 0.33 A | 76 / 55 mW | 97.8 % |
| 1.00 V | 1.28 / 1.09 A | 0.84 / 0.61 W | 92.6 % |

REQ-7 is met (worst case: 13.2 V wake voltage gives 97.7 %). A 0.1 A float-current
mismatch leaves ΔV ≈ 0.08–0.09 V per pair, or about ±45 mV per battery around the mean.

Sharing tap wires between channels changes per-wire current, not R_SC. Under the worst alternating
pattern (two failing batteries) a tap carries I_{k−1} + 2I_k + I_{k+1}; the 6 A board fuse then opens.

### 7.5 Overhead while active (per channel, typical)

- **Gate charge:** 4 × 13 nC × 100 kHz × 12 V = 62 mW.
- **Coss charging:** 4 × ½ × 15 nC × 13.5 V × 100 kHz = 41 mW.
- **UCC21520 quiescent:** 2 × (1.4 mA VCCI + 2 × 1.0 mA VDD) at 12 V [P].
- **CD4047:** ≈ 0.3 mA.
- **Green LED:** 1 mA.

So 12V_L draws 8.7 mA and 12V_U draws 4.6 mA, which is 0.18 W from the batteries + 0.04 W Coss.
The fail-safe alarm LED adds ≤ 5 mA from V5 (0.06 W): **0.28 W per channel** (REQ-8 ≤ 0.30 W), or
0.84 W for three channels while a charger is active.

LDO dissipation at 17.6 V input: U104 (17.6 − 12) × 8.7 mA = 49 mW; U105 26 mW. Both are fine for
HVSSOP.

Including overhead, end-to-end efficiency is 92 % at ΔV = 0.2 V and 74 % at 0.05 V. The overhead
stops when the charger stops (Q-8).

### 7.6 Ratio lockout, edge power and thermal

- **Window.** The lockout uses ΔV at the board (r = V_top/V_bot outside 0.918–1.084 nominal, §7.7).
  While running, ΔV_board = ΔV_posts · R_SC/(R_SC + R_ext), so running pulls r toward 1 (natural
  hysteresis). At rest ΔV_board = ΔV_posts, so a shorted cell (r = 0.83 or 1.20) never starts.
- **Edge.** A failing battery can hold r just inside the window while the channel runs. With the
  lockout's worst upper trip (r = 1.115, §7.7) and R_SC min (calcs `edge_*`):

| Case | V_bot | R_SC | I_edge | Board power | Each R_CF resistor | Middle tap |
|---|---|---|---|---|---|---|
| Hot: 50 °C ambient, board at the cut-out, equalize at 45 °C | 15.6 V | 0.505 Ω (hot R_on) | 3.55 A | 6.4 W | 1.24 W of 1.42 W rating at 99 °C | 7.1 A |
| Cold: −20 °C | 17.55 V | 0.476 Ω | 4.25 A | 8.6 W | 1.76 W of 2 W (board ≤ 70 °C) | 8.5 A |

- Each flying-path resistor position is two WSL2816R0860FEH (0.086 Ω, 2 W) in parallel
  (R101‖R152, R102‖R153); a single 0.043 Ω 2 W part would exceed its rating at 99 °C.
- Each FET: (1.51 · I)² × 13.9 mΩ = 0.40 W hot, Tj ≈ 104 °C (calc `edge_fet_tj_C`).
- The 6 A middle-tap fuse carries up to 1.4 × I_n at the cold edge and may open: a safe end state
  (the tap check then trips the window). Normal operation (ΔV ≤ 0.5 V) is ≤ 2.0 A (33 %).
  These edge stresses are recorded as waivers in the build report (REQ-24 abnormal-condition rule).
- C117/C118 ripple at the edge exceeds the 0.27 A rating [S]; transient only (normal ≤ 0.15 A).
  Alternative: a hybrid polymer capacitor (Q-6).
- **Thermal cut-out.** NCP15WM474 (470 kΩ ±3 %, B 4582 K ±3 % [P]) under 24.9 kΩ from V5, against
  VREF. Trip is 95.5 °C nominal, 91–101 °C over V5, R138, R25, B and comparator offset (calcs
  `ntc_trip_*`; 91–101 °C with offset and V_HYS/2), ≥ 15 K under the 125 °C rating of the hot-zone parts. Hysteresis 0.1–0.6 °C; the
  thermal mass makes the on/off cycle seconds to minutes. It also lights FAULT.
- **Board heat.** Overhead 0.28 W plus I²·R_SC: ≤ 0.35 W per channel normally. About 45 cm² of
  2 oz copper per channel spreads it [I], using ≥ 15.3 cm²/W from
  [thermal.md](../../../../../docs/topics/rules/thermal.md); at the edge the cut-out governs.

### 7.7 Thresholds (revised after review M-1, M-3, MINOR-2)

- **Comparators.** Two TLV7044 per channel: offset ±8 mV, hysteresis 3–25 mV centred on the
  threshold (SLVSE13J §6.4.2), so a trip moves outward by up to V_OS + V_HYS/2 = 20.5 mV [P].
- **Reference.** REF35250: 2.500 V ±0.05 %, 12 ppm/K [P].
- **Strings.** All supervisor dividers are TNPW1206 0.1 %, 25 ppm/K, ≤ 2 MΩ per segment
  (`STRINGS` in design.py). Tops are series chains, lower elements parallel pairs, so one open or
  shorted resistor at most doubles a node, to ≤ 6.2 V < 7 V (calc `comparator_input_fault_V`).
  Node voltages were raised to ~2.4 V at the lowest running voltage so offset and hysteresis are
  0.88 % of the measured ratio; resistors and TCR add 0.58 % (RSS). Window tolerance ±1.34 % on
  V_pair/V_bot, budgeted at ±1.5 % (calc `window_tol`). The first draft used 1 % strings and
  ignored V_HYS/2: about ±5 % in reality.

| Function | Node | Ratio | Threshold, nominal (worst) |
|---|---|---|---|
| Wake (U108 A, vs VREF) | PON = V_pair · 0.0945 (4 × 2.00 MΩ / 2 × 1.67 MΩ) | — | rising 26.45 V (26.30–26.75), falling ≥ 26.15 V |
| Bottom battery | N = V_bot · 0.1878 (2 × 2.00 MΩ / 2 × 1.85 MΩ) | — | — |
| Lockout, top high (U108 B) | PLO, lower tap of 3 × 2.00 + 1.96 MΩ / 2 × 30.9 kΩ / 2 × 1.58 MΩ | r > 1.084 | 1.053–1.115 |
| Lockout, top low (U108 C) | PHI, upper tap of 4 × 2.00 MΩ / 2 × 36.5 kΩ / 2 × 1.70 MΩ | r < 0.918 | 0.890–0.947 |
| Warning, top high (U111 B) | PWH, upper tap of the PLO string | r > 1.044 | 1.013–1.075 |
| Warning, top low (U111 C) | PWL, lower tap of the PHI string | r < 0.960 | 0.930–0.989 |

- The lockout catches a shorted cell (1.20 / 0.833) and never trips at 0.5 V imbalance at 13.5 V; the
  warning never fires in a balanced string (calcs `ratio_*`, `warn_*`).
- The wake rising worst case is 26.75 V (13.38 V per battery); a float below that may never wake
  the balancer (Q-2).
- **Filters.** 470 nF on every node; node impedances 0.72–0.78 MΩ, so τ = 0.34–0.37 s, matched
  within 8 %.

### 7.7a Supervisor logic, alarm and tap check (review M-2, M-4)

- **RUN.** U109 is a dual NOR: gate 1 makes FLT = NOT FLT_N, gate 2 RUN = NOR(NCHG, FLT). Both
  inputs are open-drain nodes with 100 kΩ pull-ups or a gate output, so the lockout no longer
  depends on LED voltages. Q105 (base 10 kΩ, forced β ≈ 20) only drives the red LED.
- **Fail-safe alarm.** The alarm opto LED is fed from RUN through R172 (3.9–5.0 mA), and the
  warning comparators shunt it. The three opto outputs are in series with a reverse diode D1, so the
  contact is closed only while every channel charges without fault or warning. It opens on any fault,
  warning, lost supply or open tap. At rest it is open by design: read it while charging. With CTR
  ≥ 34 % and 0.8 for ageing it sinks ≥ 1.06 mA. Unused channels need a shunt on JPk02.
- **Tap check.** U111 D is a relaxation oscillator (C51 4.7 µF; R176 + R177 charge, R178 + R179
  discharge). It drives DIS on both drivers high for 1.5 s every 32.5 s. During the pause the LDOs
  keep drawing current: a floating middle tap slews at ~17 V/s out of the window (calc
  `open_tap_detect_s` [I]), and a floating T0 collapses CH1's V5. Both open the alarm within one
  period. The pauses cost 4.5 % of the balancing time.
- **Current into a failing battery** before the alarm opens is ≤ 2.4 A (calc `silent_current_max_A`;
  4.4 A before the warning existed). It is not limited, only reported (H-13, Q-14).

### 7.8 Gate drive, timing, start-up

- **Gate drive.** U104/U105 give 1.193 V × (1 + 909 k/100 k) = 12.04 V [P], falling to ≈ 10.4 V at
  low battery. V_GS 12 V against ±20 V is 60 %.
- **Bootstrap.** C_boot = 1 µF ≈ 900 × the gate charge ratio 13 nC/12 V (≈ 370× after DC bias), above the ≥ 10×
  rule in [gate-drive-bootstrap.md](../../../../../docs/topics/rules/power/gate-drive-bootstrap.md). Droop
  is 13 mV per cycle. BAS16W reverse voltage ≤ 17.6 V against 75 V. Refresh every low-side phase.
  R158/R159 (10 Ω, review MINOR-4, SLUSCJ9F §9.2.2.2: 1–20 Ω) limit the first charge at every wake
  to 1.2 A, under the BAS16W I_FSM of 2 A at 1 µs (calc `bootstrap_inrush_A`). τ = 10 µs, so a full
  first charge takes ~5 refresh phases; steady-state droop recovery leaves < 40 mV deficit [I].
- **Dead time against skew.** DT = 160–240 ns [P]. Skew between the two drivers is ≤ 19 ns (t_PD
  26–45 ns [P]) plus ~20 ns gate fall, so DT_min 160 ns > 39 ns. An SC needs break-before-make
  across *both* half-bridges: any overlap shorts the flying cap or puts two batteries across it.
- **Start-up.** R103/R104 (100 kΩ) hold X = T_H and Y = T_M at rest, so C_FLY is pre-charged to
  V_top and later commutations draw only ΔV-proportional current. The precharge τ is ≈ 8 s, so at
  the very first wake after plug-in (≈ 1 s at absorption) C_FLY can be nearly empty and the first
  commutation draws up to ≈ 120 A for a few µs (review MINOR-5). That is accepted: it is below the
  CSD18543 I_DM of 156 A [P], the energy is ½CV² ≈ 3.4 mJ, and C_TOP dips briefly, at worst
  tripping the upper driver's UVLO for one cycle. A shorter τ would cost ≈ 25 mW per channel
  while running. S-1 now checks the peak rather than "≤ 2 × steady". Empty bootstrap caps keep
  the high sides in UVLO for the first half-cycle; the first low-side phase charges them. If the
  upper driver powers up later, body diodes run a harmless diode-rectified SC.
- **Latency.** Wake: divider τ ≈ 0.36 s, LDO start ≤ 1 ms, driver UVLO ≤ 50 µs [P]. Fault: divider
  τ 0.2–0.36 s, then gate → LDO EN in µs, and switching stops as VDD decays (ms). Edge power is
  bounded (§7.6), so this is fast enough.

### 7.9 Sleep current (per channel, typical, 25 °C, 12.8 V per battery)

- **From B_bot:** TPS70950 1.4, REF35 0.65, two TLV7044 2.7, NOR 0.1, NTC string 10.1, N string 2.6,
  pause-oscillator divider 0.5, U104 shutdown 0.59 µA [P/I].
- **From both batteries (pair strings):** P_ON 2.9 + P_LO/P_WH 2.9 + P_HI/P_WL 2.9 µA. U105 shutdown
  adds 0.59 µA on B_top. Electrolytic leakage ~1 µA each [I]. The alarm LED and the pause pull-up
  are fed from RUN, so they draw nothing asleep.
- **Per battery (N = 4):** middle batteries 38.6 µA, B4 10.3 µA; mismatch 28.3 µA (calcs `sleep_*`).
  REQ-9 is met.

### 7.10 Fuses, wire, fault currents (board fuse changed after review B-1)

- **Harness fuse KLKD010.** Fast, 600 VDC, DC 10 kA (UL 248-19) / 50 kA (UL 248-14); 12.8 mΩ;
  melting I²t 278 A²s [P].
- **Board fuse KLKD006.T** (same datasheet, [P]): 6 A fast, 600 VDC, 10 kA DC; 26.1 mΩ; melting
  I²t 63 A²s, clearing I²t 96.8 A²s at 20 kA. It sits in a Keystone 3576 PCB holder (UL 30 A
  500 VAC; custom footprint from the catalog drawing). The previous Littelfuse 477 4 A T breaks only
  500 A at 400 VDC, below the 670 A worst board fault.
- **Fault currents** (2 · R_tap + R_batteries, L = 3 m … 0.3 m): 128–194 A for one battery and
  477–670 A for TAP0↔TAP4, ≪ 10 kA (calcs `board_fault_*`).
- **Selectivity.** KLKD006 clearing I²t 96.8 A²s against KLKD010 melting 278 A²s: ratio 0.35
  (calc `fuse_selectivity_ratio`, both [P]).
- **Load.** Normal ≤ 2.0 A on a middle tap (33 %). At the cold window edge 8.5 A (142 %): the fuse
  opens within minutes, a safe end state (waived with reason).
- **Hot-plug.** ≈ 140 µF per leg, ≤ 200 A peak, I²t ≈ 0.3 A²s ≪ 63 A²s.
- **Mis-wiring.** Body diodes conduct ≈ 70 A until the fuse clears in milliseconds. FETs and the
  affected channel's TPS7A16/TPS709 (reversed IN–GND) may fail (review MINOR-8, Q-11).
- **Wire drop** at 4 A over 3 m of 14 AWG is 0.10 V.

## 8. Parts

Part cards with symbols, footprints, datasheet links, pin provenance, lifecycle and second sources
are in [parts.py](parts.py); the build writes `out/bom.csv`. Lifecycle comes from the TI, Vishay and
Diodes orderable addenda read on 2026-10-23 unless tagged.

| Role | Part | Key ratings | Stress in design (margin) |
|---|---|---|---|
| SC switches Q_A–Q_D | TI CSD18543Q3A | 60 V, ±20 V_GS, 8.1/9.9 mΩ at 10 V, Qg 11.1 nC, I_D 12 A (1 in² Cu), I_DM 156 A | V_DS ≤ 17.6 V (29 %); V_GS 12.5 V (63 %); ≤ 6.6 A rms at the cold edge (55 %); 0.43 W at the hot edge, Tj ≈ 104 °C |
| Isolated dual gate driver | TI UCC21520ADWR | VCCI 3–18 V; VDD 6.5–25 V (5 V UVLO); 4 A/6 A; 5.7 kVrms; DT 10 ns/kΩ | VCCI 12 V (67 % of 18 V); VDD 12 V (48 %); barrier ≤ 35 V |
| Oscillator | TI CD4047BM96 | 3–18 V rec., 20 V abs. | 12 V (67 %) |
| 12 V gated LDO | TI TPS7A1601DGNR | 60 V in (62 abs); 100 mA; I_SHDN 0.59 µA; EN ≥ 1.2 V | V_IN ≤ 17.6 V (29 %); 9 mA; 49 mW |
| 5 V always-on LDO | TI TPS70950DBVR | 30 V in (32 abs); I_GND 1.4 µA; ±1 % | V_IN ≤ 17.6 V (55 % of abs.); 33 mW in fault |
| Reference 2.5 V | TI REF35250QDBVR | V_IN ≤ 6 V rec., 6.5 V abs.; ±0.05 %; 0.65 µA; C_L 0.1–10 µF | 5.05 V (78 % of abs.) |
| Quad comparator, open drain (×2 per channel) | TI TLV7044PWR | 1.6–6.5 V; 7 V abs.; inputs 7 V abs.; V_OS ±8 mV; hysteresis 3–25 mV centred | 5.05 V (72 %); inputs ≤ 3.9 V (≤ 6.2 V single fault); output sink ≤ 5 mA (VOL ≤ 0.35 V at 3 mA) |
| Dual NOR gate | TI SN74LVC2G02DCTR | 1.65–5.5 V; 6.5 V abs.; V_IH 0.7 V_CC | 5.05 V (78 %); inputs from 100 kΩ open-drain pull-ups only |
| Alarm opto (series chain) | Vishay SFH617A-3X017T | V_CEO 70 V; I_F 60 mA; 4470 Vrms 1 min; creepage ≥ 7 mm; CTR ≥ 34 % at 1 mA | I_F 3.9–5.0 mA (8 %); V_CE ≤ 30 V (43 %); reverse loop blocked by D1 |
| Level-shift N-FET | Diodes 2N7002-7-F | 60 V; 115 mA | V_DS ≤ 35.2 V (59 %); 0.35 mA |
| PNP (fault driver, enable shifter) | Diodes MMBT3906-7-F | 40 V; 200 mA; hFE ≥ 100 | V_CE ≤ 17.6 V (44 %); ≤ 2.7 mA |
| Bootstrap, pause and alarm diode | Diodes BAS16W-7-F | 75 V; 150 mA; I_FSM 2 A at 1 µs | V_R ≤ 30 V (40 %); bootstrap inrush ≤ 1.2 A through 10 Ω (60 %) |
| Red LED | Rohm SML-D12V1WT86 | I_F 20 mA; V_F 2.2 V; Topr −40…85 °C | ≤ 4.1 mA (21 %) |
| Green LED | Rohm SML-D12M1WT86 | as above, 572 nm | 1.0 mA (5 %) |
| NTC | Murata NCP15WM474E03RC | 470 kΩ ±3 %, B25/85 4582 K, −40…125 °C | 10 µA (self-heating ≪ 0.1 K) |
| Flying-path resistor, 2 per position (0.043 Ω) | Vishay WSL2816R0860FEH | 2 W at 70 °C, derated linearly to 0 at 170 °C; 0.002–0.1 Ω, 1 % | Edge: 1.32 W hot (93 % of 1.42 W at 99 °C), 1.88 W cold (94 %); ≤ 0.05 W normal |
| C_FLY, C_TOP, C_BOT | Murata GCJ32EC71H106KA01L | 10 µF 50 V X7S, soft termination | ≤ 17.6 V (35 %); effective ~5–6 µF [I]; ≤ 1.2 A rms per cap at the edge |
| Bulk damping cap | Nichicon UCZ1V101MCL1GS | 100 µF 35 V, 125 °C 3000 h, ESR 0.2 Ω, 270 mA at 100 kHz | 17.6 V (50 %); ripple ≤ 0.13 A normal (48 %), > 1 A at the edge (exceeds rating, transient) |
| Small MLCCs, X7R/C0G (one MPN per value) | Murata 1 µF 50 V 0805 GRM21BR71H105KA12L (LDO inputs); 1 µF 25 V 0603 GRM188R71E105KA12D (driver VCCI/VDD, bootstrap, REF out, TH filter); 10 µF 25 V 1206 GRM31CR71E106KA12L (LDO outputs); 4.7 µF 25 V 0805 GRM21BR71E475KA73L (V5 out, ≥ 1.5 µF effective at 5 V per SBVS186H §8.1.1); 100 nF 50 V 0603 GRM188R71H104KA93D; 470 nF 25 V 0603 GRM188R71E474KA12D (divider filters); 10 nF 50 V 0603 GRM188R71H103KA01D; 470 pF 50 V C0G GRM1885C1H471JA01D (DT); 100 pF 50 V C0G ±5 % GRM1885C1H101JA01D (timing) | rated 16–50 V | ≤ 17.6 V on 50 V parts (35 %); ≤ 12 V on 25 V parts (48 %); 5 V on 25 V (20 %) |
| Supervisor strings, 0.1 % thin film: 2.00, 1.96, 1.85, 1.70, 1.67, 1.58 MΩ; 36.5, 30.9 kΩ | Vishay TNPW1206…BEEA | 1206, 0.1 %, 25 ppm/K, ≤ 2 MΩ, 200 V, 0.52 W | ≤ 9 V per segment; µW |
| Thick-film 1 % 0603: 4.7 Ω, 10 Ω, 750 Ω, 825 Ω, 10.0 k, 20.0 k, 22.1 k, 24.9 k, 49.9 k, 100 k, 249 k, 909 k, 4.99 M (one MPN per value, CRCW0603xxxxFKEA) | Vishay CRCW0603…FKEA | 0.1 W, 75 V, 1 %, ±100 ppm/K | Worst: R147/R151 49.9 k at ≤ 35 V after a single short: 25 mW (25 %) |
| Board tap fuse | Littelfuse KLKD006.T | 6 A fast, 600 VAC/VDC, DC 10 kA (UL 248-19), 26.1 mΩ, melting I²t 63 A²s [P] | ≤ 2.0 A normal (33 %); 8.5 A edge (opens: safe end state); fault ≤ 670 A ≪ 10 kA |
| Board fuse holder | Keystone 3576 | 10×38 (midget/SPF), UL 30 A 500 VAC, 38.1 mm pitch [P] | ≤ 2.0 A normal |
| Tap header, 5-pin | Phoenix MSTBA 2,5/5-G-5,08 (1757271) | 12 A, 320 V (III/2) [S] | 8.8 A edge (73 %), 70 V |
| Tap plug, 5-pin | Phoenix MSTB 2,5/5-ST-5,08 (1757048) | 12 A, 320 V, 0.2–2.5 mm² | 14 AWG with ferrule |
| Alarm header / plug | Phoenix 1757242 / 1757019 | 12 A, 320 V [S] | 1 mA |
| Channel enable and alarm-bypass jumpers (JPk01, JPk02) | Würth 61300211121 + shunt 60900213421 | 2.54 mm, 3 A | ≤ 10 mA |
| Mounting hole | M3, non-plated | — | — |
| Harness fuse (×5) | Littelfuse KLKD010.T | 10 A fast, 600 VAC/VDC, DC 10 kA / 50 kA | ≤ 2.0 A normal (20 %), 8.8 A edge; ≤ 70 V |
| In-line holder (×5) | Eaton Bussmann HEB-AW-RLC-A | 30 A, 600 V, 13/32 × 1-1/2 in, crimp 16–8 AWG | 10 A fuse, 14 AWG |
| Wire | Alpha Wire (example) UL1015 14 AWG, 600 V, 105 °C (16 AWG ≤ 2 m) | 8.28 mΩ/m | ≤ 8.8 A edge |
| Ring terminal | Panduit PV14-516R-L | 16–14 AWG, 5/16 in stud, vinyl insulated | — |
| Ferrule (plug side) | Phoenix AI 2,5-8 BU (3200522) | 2.5 mm² (14 AWG) | — |

## 9. Placement and mechanical constraints

**Mechanical.**

- **Board.** 180 × 130 mm (grown from 160 × 110 for five 43 × 18 mm 10×38 fuse holders), 4 layers, 1.6 mm FR-4 with CTI ≥ 175. 2 oz outer and 1 oz inner copper.
  All parts on the top side.
- **Mounting.** Four M3 holes, 5 mm from the corners, on nylon standoffs. Coordinates follow the kaesynth
  BoardSpec: origin at the lower-left corner, y north, so the ISO keep-out at y 122–130 is the north edge.
- **Enclosure.** IP54 polycarbonate wall box, about 250 × 200 × 90 mm. M20 gland for the harness at
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
  - Wires (14 AWG, or 16 AWG up to 2 m) run in split loom to the plug, using ferrules.
  - For N < 4, remove JP for unused channels and **bridge every unused plug position to the
    highest used position** with a short wire in the plug. A floating top tap is otherwise pulled
    ≈ 0.8 V below its neighbour: the divider strings draw µA through two body diodes. That
    reverse-biases U305/C317 beyond the −0.3 V absolute maximum of the LDO.
- **Heatsinking.** No heatsink. Power copper is poured on L1/L4 per net (X, Y, TAPs), with thermal
  vias under Q_A–Q_D and R_CF (R101/R152, R102/R153).

**Board floor plan.**

- **Ordered by potential (key rule).** The three channel columns sit west → east as CH1, CH2, CH3.
  Inside each column, the "L" side (domain Bk: logic, lower half-bridge, Y) is west and the "U" side
  (domain B(k+1): upper driver, X) is east, so battery domains increase monotonically west → east:
  B1 | B2 B2 | B3 B3 | B4.
- **South edge.** J1 is centred on the south edge, with fuses F1–F5 north of it in tap order west →
  east.
- **North edge.** An 8 mm ISO strip runs along the north edge, carrying J2 at the north-west corner
  and the ALM bus. The optos straddle it. LEDs and jumpers sit just south of the strip.

**Relations.** [design.py](design.py) (`placement`, `channel_placement`) holds the full set, and the
build writes them to `out/intent.yaml` (358 relations, plus inferred ones). Per channel:

- PWR: 2×2 FET quad around the C_FLY bank (Y column west, X column east, mirrored); R_CF and the
  C_TOP/C_BOT banks tight to the FET pins; both commutation loops and all four gate loops as
  `hot_loop`; `thermal` on R_CF and FETs; NTC near R101/Q101 and `far` from the bulk caps.
- DRV: drivers next to their FETs, gate resistors tight to the gates, decoupling and bootstrap parts
  tight to their pins, copper keep-out between the isolator pin rows, `pins_toward(U, inputs, west)`.
- OSC/SUP/SUPV: oscillator close to both drivers and away from X/Y; supervisor in the quiet corner
  of Bk, `far` from the FETs; divider filter caps tight to U108.
- Board: `separate` for every barrier (spacing from §6), keep-outs at the holes, all parts top side.

Relations outside the kaesynth vocabulary go through `d.place.custom` and are checked by people
until a checker exists: `order` (domains west → east), `strip` (north ISO strip), `cluster` (the five
functional groups inside a channel block), `pour`, `connect_at` (divider taps at the C_TOP/C_BOT pads,
channel side of the fuses), `guard` (T_L ring around the high-impedance nodes), `matched` (PH1/PH2 to
both drivers), `row` (LEDs and jumper) and `straddle` (opto across the ISO barrier). `array` takes
the three channel blocks as members.

## 10. Verification plan

Equipment:

- Four 12 V AGM batteries (or four 0–20 V, ≥ 5 A bipolar supplies, each with 10 mF across it)
- A 0–70 V charger emulator
- µA meters in every tap
- A thermal camera
- An oscilloscope with isolated probes

| ID | Test / simulation | Pass criterion |
|---|---|---|
| S-1 | SPICE of one SC cell (TI CSD18543 and UCC21520 models): sweep ΔV, C, R_on; start-up from empty C_FLY; DT and skew corners | R_SC 0.48–0.57 Ω; no overlap; first-commutation peak ≤ 140 A (< I_DM 156 A); REQ-6 currents with real C_TOP/C_BOT |
| S-2 | Monte Carlo of the wake, ratio and NTC thresholds (1 % / 0.1 % parts, offset, hysteresis) | Matches §7.7 bounds |
| V-1 | N = 2, 3, 4 with jumpers and plug bridges; unused channels dark | No false FAULT; correct channels ACTIVE; no unused T_H − T_M below −0.1 V |
| V-2 | Pair 21–35.2 V sweep (10.5–17.6 V per battery), −20 / +25 / +50 °C chamber | Stable operation; LDOs regulate |
| V-3 | Imposed ΔV 0.05–1.0 V; measure tap currents | ≥ REQ-6; within ±25 % of §7.4 |
| V-4 | Coulomb-count transfer between two batteries, 24 h; measure overhead power | Transfer efficiency ≥ 97 % at ΔV 0.3 V; overhead ≤ 0.25 W per channel |
| V-5 | Sleep current in each tap at 12.8 V per battery | ≤ 50 µA each; max difference ≤ 40 µA |
| V-6 | Ramp the pair voltage slowly | Wake 26.45 ± 0.17 V; sleep 26.0–26.4 V; green LED follows |
| V-7 | Ratio sweep at rest and running: replace one battery with a supply | Lockout at r = 1.088 / 0.907 ± 1.5 %; red LED and alarm |
| V-8 | Edge test: hold r at the upper trip (ΔV_board ≈ 1.9 V at 15.6 V), 0.3 m harness, blocked vents, 50 °C | Thermal trip 91–101 °C; R_CF and FETs within rating; middle-tap fuse may open (safe) |
| V-9 | Fault: board short TAP1–TAP2 behind the fuses with batteries; also TAP0–TAP4 | Board fuse clears; harness fuse intact; no smoke |
| V-10 | Fault: short Q101 drain–source (and Q104) before power-up, then charge | Fuses clear on the first phase-2; no fire; other channels OK |
| V-11 | Fault: short one C_FLY, one C_TOP MLCC; short C117 | Fuses clear; damage confined |
| V-12 | 100 random-order hot-plugs of J1; open each tap wire (T0 included) while charging and at rest | No damage; while charging the alarm opens within 35 s for every open tap; at rest at the next charge |
| V-13 | Mis-wiring with 2 A current-limited supplies first, then batteries: swap T1/T2, reverse B2, T0↔T4 | Fuses clear; no fire; record FET survival (Q-11). The installation procedure's pre-plug voltage check catches all cases. |
| V-14 | Alarm isolation hi-pot 1.5 kV DC, 60 s, all taps tied vs ALM_C/E; contact 30 V/1 mA; reversed loop | No breakdown; closed contact ≤ 2 V at 1 mA; open on loss of any channel supply; reversed loop blocked by D1 |
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
- sn74lvc1g02 (SCES213Y, superseded)
- sn74lvc2g02 (SCES194N): DCT pin map 1A 1, 1B 2, 2Y 3, GND 4, 2A 5, 2B 6, 1Y 7, VCC 8
- tlv3404 (SLCS135B, alternative)

**Other vendors [P].**

- Diodes: 2N7002 (DS11303), MMBT3906 (DS30059), BAS16 (Zetex 1996).
- Vishay: SFH617A (83740), WSL (30100), CRCW (20035), TNPW (28758).
- Murata: NCP15 spec; GCJ32EC71H106 product sheet via mirror
  https://extranet.mandieselturbo.com/electronics/datasheets/muRata/GCJxx_series/GCJ32EC71H106MA01.pdf
- Rohm: SML-D12x1.
- Littelfuse KLKD (POWR-GARD), Rev 061217: https://www.farnell.com/datasheets/2603270.pdf
  - KLKD006.T: 6 A, 600 VDC, 10 kA DC interrupting, 26.1 mΩ, melting I²t 63 A²s
- Keystone catalog M65 p. 45, 3576 PCB fuse holder for 10 × 38 mm: UL 30 A 500 VAC, 38.1 mm pitch,
  3.6 × 1.3 mm slots

**Secondary [S].**

- Littelfuse 477 series (rejected after review B-1: 500 A at 400 VDC is below the 670 A board fault): https://www.littelfuse.com/products/fuses/cartridge-fuses/5x20mm-fuses/477.aspx
- Littelfuse MINI 58V (1000 A at 58 VDC; rejected, below 70 V)
- Eaton HEB-AW-RLC-A:
  https://steinerelectric.com/Catalog/FusesFuse-Blocks-And-Fuse-Holders/Fuse-Holders/In-Line-Fuse-Holders-And-Insulators/Bussmann-HEB-AW-RLC-A-Tron-HEB-Fuse-Holder600-VAC30-A16-to-8-AWG-Wire1-Pole-5477
- Phoenix MSTB/MSTBA: https://automa.net/product/phoenix-contact/1757019-63a36f14ca04b4f2592acf7e
- Nichicon UCZ: https://ibselectronics.com/products/nichicon/ucz1v101mcl1gs
- Littelfuse 01000056Z: https://ie.farnell.com/littelfuse/01000056z/cartridge-fuse-clip-5x20mm-10a/dp/2762086

**Repository docs.**

- [isolation-creepage.md](../../../../../docs/topics/rules/isolation-creepage.md): IPC-2221B and
  IEC 60664-1 values via TI SLUP419
- [chargers-bms.md](../../../../../docs/topics/rules/power/chargers-bms.md)
- [hot-loops.md](../../../../../docs/topics/rules/power/hot-loops.md)
- [thermal.md](../../../../../docs/topics/rules/thermal.md)
- [gate-drive-bootstrap.md](../../../../../docs/topics/rules/power/gate-drive-bootstrap.md)
- Rohm SML-D12x1 [P]: https://fscdn.rohm.com/en/products/databook/datasheet/opto/led/chip_mono/sml-d12x1-e.pdf
