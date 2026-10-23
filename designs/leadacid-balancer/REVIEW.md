# leadacid-balancer: independent design review

Reviewer: Claude (independent pass, 2026-10-23). Scope: DESIGN.md, CONNECTIONS.md, parts.py,
design.py, out/netlist.json, out/report.md, out/intent.yaml, out/leadacid-balancer.kicad_dru and the
KiCad symbols and footprints. Datasheets were downloaded and read. Transient behaviour was checked with a
piecewise-linear periodic-steady-state model of one SC cell, written in numpy (scratch, not committed).

## Verdict

**Not ready for layout.** The topology is sound and every pinout checks out. The SC cell, the
bootstrap and the dead-time logic work as described. The safety and supervision layer has
problems, though:

- The on-board fuse's DC breaking capacity is a third of the claimed value and below the computed
  fault current.
- The ratio-lockout window is far less precise than claimed.
- The lockout logic depends on LED forward voltages.
- Two of the claimed "open tap → FAULT" cases never alarm.

Counts: **1 BLOCKER, 4 MAJOR, 10 MINOR.**

## BLOCKER

### B-1 Board fuse 0477004.MXP is rated 500 A DC, not 1.5 kA

- **What is wrong.** DESIGN.md §7.10, parts.py `FUSE_BOARD` (`breaking_a=1500`) and the calc
  `board_fault_max_A` (limit 1500) all assume 1.5 kA at 400 VDC.
- **Evidence.** The 477-series table row for 4 A is 100 A @ 500 VAC / **500 A @ 400 VDC**. The
  1.5 kA figure belongs to the low-current rows. Digi-Key's 0477004.MXP listing gives "Breaking
  Capacity 100A AC, 500A DC", melting I²t 52.48 A²s and cold resistance 17.2 mΩ (it links the
  Littelfuse 477 datasheet, Rev 07/04/23; littelfuse.com returned 403 to direct fetches).
- **Consequence.**
  - REQ-14 (≥ 1 kA on board) fails.
  - The design's own prospective board fault (TAP0↔TAP4) is 477–684 A, so it exceeds the
    rating. With a 3 m harness the margin is about zero; at 0.3 m it is 37 % over.
  - A 5×20 ceramic fuse interrupting beyond its rating can hold an arc or rupture. Clearing then
    falls to the KLKD010 in the harness. That is a coordination failure in the primary
    fault-containment path (H-2, H-3 "fails to a fuse").
- **Fix.**
  - Choose a board fuse whose datasheet DC breaking capacity is ≥ 1 kA at ≥ 80 VDC. Example: a
    10×38 mm DC-rated midget such as KLKD 5 (10 kA DC, UL 248-19) in PCB clips. Its melting I²t is
    34 A²s, which keeps selectivity against KLKD010 (278 A²s).
  - Correct `breaking_a` and close Q-5 with the read value.

## MAJOR

### M-1 Ratio-window tolerance is about ±5 %, not ±1.5 %: false lockout or a missed shorted cell

- **Evidence.**
  - The P_LO, P_HI and N strings are 1 % CRCW0603 parts (parts.py `_crcw`).
  - At linear worst case each divider ratio is ±1.8–1.9 %; for P_LO, (1−k)·2 % with k = 0.048.
  - The TLV7044 hysteresis is centred on the threshold (SLVSE13J §6.4.2, Fig. 6-1:
    V_TH + V_OS ± V_HYS/2). V_HYS is 3–25 mV on the quad (Electrical Characteristics), so the trip
    point moves outward by up to 12.5 mV. On N ≈ 1.34 V that is 0.9 %, plus V_OS ±8 mV (0.6 %).
    `numbers()` adds neither the V_HYS/2 term nor any resistor drift.
- **Result.**
  - Upper trip r = 1.00–1.20, against the claimed 1.056–1.119.
  - Lower trip r = 0.81–0.99, against the claimed 0.878–0.936.
- **Consequence.**
  - At the tight corner, a unit locks out at ~0–1.5 % imbalance and never balances.
  - At the loose corner, it can miss a shorted cell: r = 1.20 or 0.833 (REQ-11, H-4).
  - CRCW TCR (±100 ppm/K) and leakage on 5 MΩ strings in an uncoated battery-room board (H-11)
    widen this further.
- **Fix.**
  - Use 0.1 % thin film for all three strings. TNPW tops out at 2 MΩ, so use more segments.
  - Alternatively, derive N, P_LO and P_HI from one tapped string so that resistor errors become
    ratiometric.
  - Recompute with V_OS + V_HYS/2 and add a Monte-Carlo (S-2) that includes TCR.

### M-2 Lockout logic depends on LED forward voltage: Q105 is under-driven

- **Evidence.**
  - Q105 (MMBT3906) gets I_B = (5 − 0.72)/100 k − 0.72/100 k ≈ 36 µA through R142/R143.
  - DS30059 Rev 23-2 gives h_FE min 100 at 10 mA and 80 at 1 mA. So I_C ≤ 3.6 mA at 25 °C and
    about 2.7 mA cold, against the 4.2–9.1 mA the design claims (forced β would be 255).
  - Q105 is therefore not saturated. FLT, the NOR input B, sits at V_F(red) + V_F(opto) + I·249 Ω
    ≈ 3.6–3.9 V.
  - SN74LVC1G02 needs V_IH = 0.7·V_CC = 3.54 V (SCES213Y, Recommended Operating Conditions).
- **Consequence.**
  - The margin is about 0.1–0.3 V. In the 1.5–3.5 V band the NOR output is undefined and the gate
    draws ΔI_CC.
  - If D103 fails short, FLT falls to about 2–2.9 V. RUN can then stay high with a ratio or thermal
    fault present. A single indicator fault defeats the lockout.
- **Fix.**
  - Drive the run logic from clean open-drain levels. Swap comparator A's inputs to get CHG and
    use RUN = AND(CHG, FLT_N), for example 74LVC1G08. Keep Q105 for the LEDs only.
  - At minimum, set R142 to 10 kΩ (forced β ≈ 20).

### M-3 The window lets a failing battery absorb amps silently

- **What is wrong.** Nothing alarms until |r − 1| > 8.7 % (±1.2 V at the board, about 2 V at the
  posts).
- **Evidence.** Just inside the window the channel pushes ΔV/R_SC = 1.19 V/0.514 Ω ≈ 2.3 A
  nominal, and up to 4.4 A at the design's worst case, into the low battery.
- **Consequence.**
  - A battery with a soft short or high self-discharge then takes 30–57 W of extra internal
    heating, continuously during charge. That is a dry-out and thermal-runaway driver for VRLA.
  - The FMEA covers only a dead shorted cell (H-4) and board heat (H-7). The board sits at
    3–9 W, cycling on the NTC, and nobody is told.
  - The brief asks for "robust". A balancer that quietly feeds a dying battery is the opposite.
- **Fix.**
  - Add an imbalance alarm, separate from the lockout, at about ±2–3 % running deviation sustained
    for more than 1 h.
  - Or limit the transfer current, for example by a hiccup when I > ~1 A.
  - Add a hazard row for battery-side heating.

### M-4 "Open tap → FAULT" is false for T0, and for middle taps while running

- **T0 wire broken (system ground).**
  - While charging, CH1's SC drives the floating T_L to 2·T_M − T_H. CH1 keeps running, powered
    through its own cell from B2, and sees r = 1. No fault.
  - At rest, the CH1 B_bot loads and the pair strings feed current into the floating T_L. It rises
    to T_M + 1.4 V through the Q_D/Q_C body diodes. V5 collapses, the comparators lose power and
    nothing alarms, ever.
  - B1 is then never balanced.
- **Middle tap broken while running.** CH(k) holds its floating T_M at the midpoint of T_L…T_H
  through R_SC ≈ 0.5 Ω. Its ratio reads exactly 1 and the neighbours see averaged batteries. The
  fault shows only after the charger stops and the node drifts.
- **Consequence.** V-12's pass criterion and the DESIGN.md summary claim ("a dead battery or an open
  tap") cannot be met. The alarm is also closed-on-fault: a channel or board that loses its supply
  reports "OK".
- **Fix.**
  - Make the alarm fail-safe: contact closed when healthy, so loss of V5 opens it.
  - Add a tap-continuity check, for example a periodic stop-and-measure window in which the SC
    pauses for ~1 s before the ratio is compared.
  - Correct the claims.

## MINOR

1. **REQ-6 margin is negative.**
   - The R_SC formula assumes stiff sources at the taps, but C_TOP/C_BOT (4 × ~5 µF effective plus
     an electrolytic behind 0.2 Ω) are smaller than C_FLY (~40 µF).
   - The periodic-steady-state simulation gives these results at ΔV = 0.1 V:

     | Corner | Harness | Simulated | Design calc |
     |---|---|---|---|
     | Nominal | 3 m, 14 AWG | 0.100 A | 0.109 A |
     | Worst (30 µF, hot R_on) | 3 m, 14 AWG | 0.095 A | 0.103 A |
     | Worst | 2 m, 16 AWG | 0.094 A | 0.102 A |

   - So REQ-6 (≥ 0.10 A) fails at the stated corners.
   - The current factors (I_fly = 2.16·I, I_FET = 1.53·I) and the electrolytic ripple
     (0.063 A rms at 0.3 A) confirm the design.
   - Fix: add C_TOP/C_BOT capacitance (≥ C_FLY), or relax REQ-6.
2. **Wake threshold understated.** With the centred hysteresis (M-1), the rising worst case is
   2.5205 V → 26.76 V on the pair, i.e. 13.38 V per battery, not 13.31 V. That worsens Q-2: flooded
   floats (Trojan 13.2 V) and warm temperature-compensated AGM floats never wake the balancer.
   Consider ~12.9–13.0 V per battery.
3. **TPS709 output capacitor.** SBVS186H §8.1.1 requires ≥ 1.5 µF *effective*. C138
   (2.2 µF 16 V 0603 X7R) at 5 V DC bias, −10 % tolerance, is likely ~1.2–1.4 µF [I]. Use
   4.7 µF/16–25 V 0805.
4. **No bootstrap resistor.** TI recommends R_BOOT 1–20 Ω (SLUSCJ9F §9.2.2.2). The BAS16W
   non-repetitive I_FSM is 2 A @ 1 µs (Diodes DS30094 Rev 13-2), and the first charge of the 1 µF
   from a 10 µF rail exceeds it at every wake. Add 4.7 Ω in series with D101 and D102.
5. **No soft start; precharge too slow.**
   - The R103/R104 precharge has τ = 200 kΩ × 40 µF ≈ 8 s, but at absorption voltage wake occurs
     ~0.9 s after plug-in, with C_FLY at ~10 % of V_top.
   - The first commutation then draws ~100 A peak from C_TOP, which dips ~8 V. The S-1 criterion
     ("first cycle ≤ 2 × steady") will fail.
   - Fix: shorten τ (10 kΩ) or delay RUN by more than 3τ.
6. **Placement frames disagree.**
   - The board keepout `rect: [0, 102, 160, 110]` is labelled "north edge". In KiCad's y-down
     coordinates (holes at y = 5/105; the rpi-mains-relay design uses y = 0 as north) that strip is
     the south edge, where `edge(J1, south)` and F1–F5 must sit.
   - Also, `order`, `strip`, `guard`, `straddle` and `connect_at` are custom relations no placer
     checks. The potential-ordered floor plan that H-3 relies on is therefore unenforced; only the
     DRU spacing is.
   - Fix: state the axis convention, move the rect to y 0–8 (or make it relative) and give
     `order` a checker.
7. **In-domain 0.2 mm for bootstrap children.**
   - CHk_HSU/HSL have no custom rule against their parent band: they sit on the same side of the
     `.inherited` rules and both netclasses are 0.2 mm.
   - BSTx/Gx reach V_b + 13.5 V above the parent reference: 31 V at 17.6 V and 33.5 V at the 20 V
     survive value. IPC-2221B B2 needs 0.6 mm above 30 V.
   - Set the HSU/HSL netclass clearance to 0.6 mm. The SPAN netclasses already have 0.6.
8. **Mis-wiring damage is wider than "FETs".** With T1/T2 swapped, the next channel's
   TPS7A16/TPS709 see IN–GND reversed. The only clamp is two FET body diodes in series (≈2 V at
   tens of amps), in parallel with each LDO's single substrate diode. Expect the logic LDOs to
   fail too. State this in REQ-17/H-5, or add a per-channel reverse diode (Q-11).
9. **Alarm output has no reverse protection.** The SFH617A V_ECO is 7 V (Vishay 83740 p. 2), so a
   reversed ≤ 30 V alarm loop breaks down all three optos. Add a series diode.
10. **Brief fit and wording.**
    - REQ-9 cites the brief for "tiny and equal", which the brief does not say.
    - 14 AWG with $100-class holders is not "little wires". It is forced because R_ext ≈ R_SC; say
      so in the brief response.
    - The always-awake float overhead (0.66 W, 74 % end-to-end at ΔV = 0.05 V) could drop with a
      burst/hysteretic mode (switch only when |ΔV| > ~30 mV).

## Waivers in out/report.md

| Waiver | Reasoning true? |
|---|---|
| TPS70950 EN 6.5 V | **Yes.** SBVS186H Table 5-1 and §7.4: a 300 nA pull-up, may float, 6.5 V Zener clamp, 7 V abs max. |
| NCP15 5.05 V | **Yes in substance.** It is a self-heating limit and the power is µW. |
| F2–F4 at 220 % / F1, F5 at 110 % | **Acceptable** as an abnormal-edge end state. The "selectivity" justification now rests on the wrong 477 rating (B-1). |
| FH 88 % | **Acceptable** (edge only). |
| R_CF 1.32 W | **Plausible.** WSL2816 is 2 W at 70 °C, 0.002–0.1 Ω at 1 %, derated to 170 °C (Vishay 30100), so 0.086 Ω is in range. |
| H-6 procedural | **Acceptable.** |

## Verified correct

- **Pinouts (datasheet = netlist = KiCad pads).**
  - CSD18543Q3A: 1–3 S, 4 G, 5–8 + pad D (SLPS633 p. 1); footprint pad 5 = drain.
  - UCC21520ADW: Table 5-1; A version = 5 V UVLO.
  - CD4047B: pin map and free-running connections 4, 5, 6, 14 → V_DD and 7, 8, 9, 12 → V_SS,
    t_A = 4.40 RC (SCHS044C pp. 1–2).
  - TPS7A1601 DGN: 1 OUT, 2 FB, 3 PG, 4 GND, 5 EN, 6 NC, 7 DELAY, 8 IN.
  - TPS70950DBVR uses the base TPS709 DBV column (1 IN, 2 GND, 3 EN, 4 NC, 5 OUT), not the A or B
    variant.
  - REF35 DBV: 1, 2 GND, 3 EN, 4 VIN, 5 NR, 6 VREF.
  - TLV7044 PW per Table 4-3.
  - SN74LVC1G02 DBV.
  - SFH617A: 1 A, 2 K, 3 E, 4 C; -3X017T exists.
  - 2N7002: G-S-D.
  - MMBT3906: B-E-C.
  - BAS16W: 1 A, 3 K, 2 NC (DS30094 internal schematic).
  - LED, C_Polarized and MSTBA pad orders.
- **SC cell.** Phase assignment (Q_A/Q_C on PH1, Q_B/Q_D on PH2), driver references (VSSA = X/Y,
  VSSB = T_M/T_L), bootstrap refresh paths and body-diode clamps are correct.
- **Dead time.** DT 160–240 ns at 20 kΩ against t_PD 26–45 ns gives ≥ 100 ns cross-driver margin.
  The DT capacitor ≤ 1 nF and DIS tied to GND match the datasheet.
- **Recomputed values.**
  - R_SC 0.476–0.567 Ω, by formula.
  - Edge powers.
  - NTC trip 91–100 °C.
  - Divider single-fault node voltages ≤ 6.1 V < 7 V. TLV704x inputs are fault-tolerant with
    V_CC = 0.
  - Sleep currents of 26/36/36/10 µA (typical; datasheet maxima push the mismatch to about 40 µA).
  - TPS7A16 EN ≤ IN and level-shifter stresses.
  - 12.04 V rail ±2 %.
- **KLKD010.** 600 VDC, 10 kA DC (UL 248-19), 12.8 mΩ, melting I²t 278 A²s at 20 kA (Littelfuse
  Rev 061217 p. 3).
- **Existence and ratings.** HEB-AW-RLC-A exists (30 A, 600 V). SFH617A-3 CTR ≥ 34 % at 1 mA and
  ≥ 7 mm creepage.
- **DRU.** It matches DESIGN.md §6:
  - Adjacent bands 0.6/0.6 mm; non-adjacent 1.0/1.5 mm (clearance/creepage).
  - ISO 4/4 mm to every stack domain (via `.inherited`).
  - Explicit pair rules come last, so they win.
  - Bridging-part rules are limited to pad-to-pad within one footprint.
- **Approach.** Voltage equalization during charge and float is the right target for lead-acid,
  because float limits are per-cell voltage limits. It is how commercial midpoint balancers work, and
  no bleed path is used for balancing.

## Response to review

Designer's response, 2026-10-23. Every finding is listed with what changed. Calc names refer to
`calcs()` in design.py and appear in `out/report.md`. Rebuilt with the updated framework (fuse
branch rule, `waiver.unused`): 0 errors, ERC clean, netlist identical, no unused waivers.

### BLOCKER

| Finding | Action |
|---|---|
| B-1 board fuse 500 A DC | Replaced 0477004.MXP with **Littelfuse KLKD006.T**: 6 A, 600 VDC, **10 kA DC**, 26.1 mΩ, melting I²t 63 A²s (KLKD datasheet Rev 061217, Farnell 2603270 [P]). It sits in a Keystone 3576 PCB holder (catalog M65 p. 45: UL 30 A, 38.1 mm pitch), new footprint `custom:Fuseholder_Keystone_3576_10x38mm`, BOM items XH1–XH5; the 5×20 clips are gone. `breaking_a=10000`. Calc `board_fault_max_A` = 670 A against the 10 kA limit (`board_fault_min_A` 128 A). Selectivity: 63 / 278 A²s → ratio 0.35 (calc). The board is 180 × 130 mm to fit the holders. Q-5 closed. |

### MAJOR

| Finding | Action |
|---|---|
| M-1 window tolerance | All supervisor strings are TNPW1206 0.1 %, 25 ppm/K, ≤ 2 MΩ per segment (`STRINGS`). The lockout and warning thresholds share one tapped string per direction (PLO/PWH and PHI/PWL), so their errors are ratiometric. Nodes were raised to ~2.4 V, so V_OS + V_HYS/2 = 20.5 mV is 0.88 %. With resistors and TCR (RSS) the total is ±1.34 %, budgeted at `WIN_TOL` = ±1.5 % (calc `window_tol`). Worst-case trip points, both directions, are now in calcs: lockout high 1.053–1.115, lockout low 0.890–0.947, warning high 1.013–1.075, warning low 0.930–0.989. The lockout still catches 1.20 / 0.833 and never trips at 0.5 V imbalance. A Monte-Carlo with TCR stays in V-plan S-2. DESIGN.md §7.7. |
| M-2 Q105 base drive / LED-dependent lockout | U109 is now an SN74LVC2G02 dual NOR (SCES194N): gate 1 makes FLT = NOT FLT_N, gate 2 makes RUN = NOR(NCHG, FLT). Both inputs are clean open-drain or gate levels. Q105 (base 10 kΩ, forced β ≈ 20) drives only the red LED through R145 750 Ω. A shorted or open LED can no longer hold RUN high. NOR was kept (rather than AND) so NCHG idles low at rest with no pull-up current. DESIGN.md §7.7a. |
| M-3 silent current into a failing battery | Added an imbalance **warning** (U111 B/C) at nominal 1.044 / 0.960 (worst 1.013–1.075 / 0.930–0.989), tapped off the lockout strings. It opens the alarm while the channel keeps balancing. Calc `silent_current_max_A` = 2.44 A, down from 4.4 A. New hazard H-13 (battery-side heating). The current is reported, not limited. A warning delay is open as Q-14 (non-blocking). |
| M-4 T0 / middle-tap detection while charging | (1) The alarm is fail-safe: each opto LED is fed from RUN (R172 825 Ω, 3.9–5.0 mA), and the three outputs are in series, so the contact is closed only while every channel runs without fault or warning. Loss of V5 opens it. (2) Tap check: U111 D is a relaxation oscillator that pauses both drivers (DIS = PAUSE) for 1.54 s every 32.5 s. A floating middle tap leaves the window in 1.14 s (calc `open_tap_detect_s`). A floating T0 collapses CH1's V5. Either way the alarm opens. Claims are corrected, new hazard H-14 added, V-12 updated, and REQ-21 is the fail-safe contact. Cost: 4.5 % of balancing time (REQ-6 calc includes the duty). Unused channels need a JPk02 shunt (REQ-25). |

### MINOR

| # | Action |
|---|---|
| 1 | REQ-6 relaxed to ≥ 0.09 A at 0.1 V / ≥ 0.26 A at 0.3 V. The calc applies your simulation factor (0.92) and the pause duty: 0.090 / 0.27 A. Adding C_TOP/C_BOT ≥ C_FLY was rejected for board area. |
| 2 | The wake worst case uses centred hysteresis: rising 26.30–26.75 V (13.38 V per battery), falling ≥ 26.15 V. Lowering it to 12.9–13.0 V would wake on resting OCV after a charge and cost sleep current. It stays a user decision under Q-2, and DESIGN.md states the float consequence. |
| 3 | C138 is now 4.7 µF 25 V 0805 X7R (GRM21BR71E475KA73L). |
| 4 | Added R158/R159, 10 Ω (TI range 1–20 Ω) in series with the bootstrap diodes. Calc `bootstrap_inrush_A` = 1.21 A against the 2 A I_FSM limit. τ = 10 µs: the first charge takes ~5 refresh phases (50 µs, upper side in UVLO meanwhile), and steady refresh is unaffected. A first try at 4.7 Ω gave 2.4 A and was rejected rather than given a relaxed limit. |
| 5 | Answered rather than changed. The first commutation after plug-in is ≤ ~120 A for a few µs, below the CSD18543 I_DM of 156 A [P], with ½CV² ≈ 3.4 mJ. The worst case is one cycle of upper-driver UVLO. A 10 kΩ precharge would cost ~25 mW per channel continuously, against the REQ-8 overhead budget. S-1's criterion is now "first-commutation peak ≤ 140 A". |
| 6 | Axis convention: kaesynth `BoardSpec` uses a lower-left origin with y up, so y 122–130 is the north edge. The keepout is now `[0, 122, 180, 130]` for the 180 × 130 board, and DESIGN.md §9 says so. The custom relations (`order`, `strip`, `guard`, …) are unchecked by any placer. That is a framework gap, not a design change: H-3 relies on the DRU spacing as the enforced barrier, and floor-plan order is checked at layout review (V-plan). |
| 7 | Added barriers B{k+1}/CHk_HSU and B{k}/CHk_HSL at 0.6 mm (IPC-2221B B2, > 30 V). |
| 8 | REQ-17 and H-5 now state that a T1/T2 swap can also destroy the next channel's TPS7A16/TPS709. A per-channel reverse diode stays open under Q-11. |
| 9 | Added D1 (BAS16W) in series with the alarm chain, so a reversed loop blocks at the diode (75 V) instead of breaking down the optos (V_ECO 7 V). |
| 10 | REQ-9 now cites "balanced" and the brief response explains that 14/16 AWG and the holders are forced by R_ext ≈ R_SC (REQ-22: 16 AWG ≤ 1.5 m). Overhead is now 0.28 W. A burst/hysteretic mode is noted under Q-8 as a later option. |

### Waivers

- The F2–F4 / F1, F5 edge waivers now justify selectivity with the KLKD006/KLKD010 I²t (63 / 278 A²s), not the 477 rating.
- The fuse-branch rule now also flags the parallel BR bridge resistors in the N < 4 variants. Unused TAPj_IN nets are no longer marked external. In those variants the bridges carry conditional, reasoned waivers.
- A stale F1/F5 waiver that matched nothing (`waiver.unused`) was removed.
- R_CF is now 1.24 W at the hot edge (limit 1.42 W).
- The NTC, EN and H-6 waivers are unchanged.
- 31 waivers in total.
