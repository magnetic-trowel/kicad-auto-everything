# leadacid-balancer: connections (netlist)

Companion to [DESIGN.md](DESIGN.md). Every part instance, every pin by number and name, and every
net. The encoded design is [design.py](design.py) with part cards in [parts.py](parts.py); `kaesynth
build` writes the full pin-by-pin netlist to `out/netlist.json` (KiCad round trip: identical). If this
file and design.py disagree, design.py is the source and this file is wrong. Evidence tags: [P] pin numbers read in the primary datasheet, [S] secondary or the KiCad
library only.

## 0. Conventions

**Taps and channels.**

- Taps are TAP0 (system negative, T0) to TAP4 (positive of battery B4).
- Battery Bj sits between TAP(j−1) and TAPj.
- Channel k (k = 1, 2, 3) balances B_k (bottom) against B_{k+1} (top), using three taps:
  - T_L = TAP(k−1)
  - T_M = TAPk
  - T_H = TAP(k+1)

**Reference designators.**

- Board-level parts use numbers < 100: J1, J2, F1–F5, H1–H4.
- Channel parts are `<prefix><k><nn>`: Q101 is channel 1 part 01, Q201 is channel 2, Q301 is
  channel 3. The thermistor is RT101/RT201/RT301; the jumper is JP101/JP201/JP301.
- §3 defines channel 1 completely. §4 gives the substitution rule for k = 2, 3.

**Net names.**

- Board nets: `TAPj_IN` (connector side of fuse Fj+1), `TAPj` (fused bus), `ALM_C`, `ALM_E`.
- Channel nets: `CHk_<name>`.
- Channel-1 tables write the taps literally as TAP0/TAP1/TAP2. For channel k read TAP(k−1), TAPk,
  TAP(k+1).

**Pin numbers.**

- Pin numbers are datasheet pin numbers.
- Where the KiCad footprint merges pins, the pad mapping is given: the CSD18543Q3A drain pins 5–8
  plus the exposed pad are KiCad pad 5.
- Every pin is listed. `NC` means leave it unconnected.

**Domains** are defined in DESIGN.md §6 (the kaesynth voltage model):

- Bk (k = 1…4) is battery k's domain. It floats on TAP(k−1) and holds TAPk plus every net
  referenced to TAP(k−1). B1 is the root (TAP0). Channel k's "L" side is Bk, its "U" side B(k+1).
- CHk_HSU / CHk_HSL ride on the switch nodes CHk_X / CHk_Y (bootstrap, upper gate, C_FLY plates).
- CHk_LS rides on T_H (base of Qk07); CHk_QFB rides on CHk_V5 (base of Qk05); CHk_SPAN rides on
  T_L and holds the nets that swing across both batteries (PON_A, LSD, LSM).
- ISO is the alarm output (separate root, ref ALM_E).
- "Vb" is one battery voltage: 10.5–17.6 V operating, 0–20 V survive.

## 1. Nets

### 1.1 Board-level nets

| Net | Domain | V to own reference | V to T0 | Max current | Kind |
|---|---|---|---|---|---|
| TAP0_IN, TAP0 | B1 (root, = system ground) | 0 | 0 | ≤ 0.7 A normal; 4.4 A at the window edge (failing battery) | power / reference |
| TAP1_IN, TAP1 | B1 | Vb | 1 × Vb (10.5–17.6) | ≤ 2.0 A normal; 8.8 A at the edge (middle tap) | power |
| TAP2_IN, TAP2 | B2 | Vb above TAP1 | 2 × Vb (21–35.2) | as TAP1 | power |
| TAP3_IN, TAP3 | B3 | Vb above TAP2 | 3 × Vb (31.5–52.8) | as TAP1 | power |
| TAP4_IN, TAP4 | B4 | Vb above TAP3 | 4 × Vb (42–70.2) | as TAP0 | power |
| ALM_C | ISO | 0–30 V vs ALM_E (external supply) | floating; assumed ≤ ±100 V | 1 mA (3 opto collectors in parallel) | isolated signal |
| ALM_E | ISO | reference of the alarm contact | floating | 1 mA | isolated signal |

### 1.2 Channel-1 nets

For channel k, add (k−1) × Vb to the "V to T0" column.

| Net | Domain | V to own reference | V to T0 (k = 1) | Max current | Kind |
|---|---|---|---|---|---|
| CH1_X | B2 (upper switch node) | TAP1 − 0.7 … TAP2 + 0.7 | TAP1…TAP2 (10.5–35.2 V), square wave at 100 kHz | ≤ 1.4 A rms normal; 9.3 A rms at the edge | switching node |
| CH1_Y | B1 (lower switch node) | TAP0 − 0.7 … TAP1 + 0.7 | TAP0…TAP1 (0–17.6 V), square wave | as CH1_X | switching node |
| CH1_CFP | CH1_HSU | X ± 0.4 V (I · R101‖R152) | 10.5–35.2 V | as CH1_X | power (flying cap +) |
| CH1_CFN | CH1_HSL | Y ± 0.4 V | 0–17.6 V | as CH1_X | power (flying cap −) |
| CH1_GA | CH1_HSU | 0–12 V above X | ≤ 47.2 V | 4 A/6 A gate peak, ≈ 1 mA average | gate |
| CH1_GB | B2 | 0–12 V above TAP1 | ≤ 29.6 V | gate peak | gate |
| CH1_GC | CH1_HSL | 0–12 V above Y | ≤ 29.6 V | gate peak | gate |
| CH1_GD | B1 | 0–12 V above TAP0 | ≤ 12 V | gate peak | gate |
| CH1_OA_U | CH1_HSU | 0–12 V above X | ≤ 47.2 V | gate peak | gate (driver side of R105) |
| CH1_OB_U | B2 | 0–12 V above TAP1 | ≤ 29.6 V | gate peak | gate |
| CH1_OA_L | CH1_HSL | 0–12 V above Y | ≤ 29.6 V | gate peak | gate |
| CH1_OB_L | B1 | 0–12 V | ≤ 12 V | gate peak | gate |
| CH1_BSTU | CH1_HSU | 9–11.5 V above X | ≤ 46.7 V | 1.3 mA average, ≤ 1 A charge peak | bootstrap supply |
| CH1_BSTL | CH1_HSL | 9–11.5 V above Y | ≤ 29.1 V | 1.3 mA average | bootstrap supply |
| CH1_12VL | B1 | 10.4–12.04 V (0 when asleep) | ≤ 12.04 V | 15 mA | supply (gated) |
| CH1_12VU | B2 | 10.4–12.04 V above TAP1 (0 when asleep) | ≤ 29.6 V | 8 mA | supply (gated) |
| CH1_FBL | B1 | 1.193 V | 1.193 V | 12 µA | feedback |
| CH1_FBU | B2 | 1.193 V above TAP1 | ≤ 18.8 V | 12 µA | feedback |
| CH1_V5IN | B1 | = TAP1 when JP101 is fitted (10.5–17.6 V), else open | ≤ 17.6 V | ≤ 10 mA (fault LED) | supply input |
| CH1_V5 | B1 | 5.0 V ±1 % | 5.0 V | ≤ 10 mA (fault LED) | supply (always on) |
| CH1_V5EN | B1 | 0–6.5 V (internal pull-up) | — | 0.3 µA | logic (LDO enable) |
| CH1_VREF | B1 | 2.500 V | 2.5 V | < 1 µA | reference voltage |
| CH1_PON_A (CH1_SPAN), CH1_PON_B, CH1_PON_C | B1 | intermediate nodes of the wake string: 0.774 / 0.547 / 0.321 × V_pair | ≤ 27.3 V | 3 µA | sense (high-Z) |
| CH1_PON | B1 | V_pair × 0.0945 (0–3.3 V; ≤ 6.1 V single fault) | ≤ 3.3 V | 3 µA | sense (high-Z, 0.76 MΩ) |
| CH1_PLO_M | B1 | ≈ 0.52 × V_pair | ≤ 18.4 V | 2.5 µA | sense |
| CH1_PLO | B1 | V_pair × 0.04771 (≤ 1.68 V) | ≤ 1.68 V | 2.5 µA | sense (0.48 MΩ) |
| CH1_PHI_M | B1 | ≈ 0.53 × V_pair | ≤ 18.6 V | 2.5 µA | sense |
| CH1_PHI | B1 | V_pair × 0.05223 (≤ 1.84 V) | ≤ 1.84 V | 2.5 µA | sense (0.52 MΩ) |
| CH1_N_M | B1 | ≈ 0.55 × V_bot | ≤ 9.7 V | 2.6 µA | sense |
| CH1_N | B1 | V_bot × 0.0996 (≤ 1.75 V) | ≤ 1.75 V | 2.6 µA | sense (0.45 MΩ) |
| CH1_TH | B1 | 5 V × R_NTC/(R_NTC + 24.9 k): 4.75 V at 25 °C, 2.5 V at 95 °C | ≤ 5 V | 10 µA (≤ 0.1 mA hot) | sense (thermal) |
| CH1_NCHG | B1 | 0 / 5 V (high = not charging) | ≤ 5 V | 50 µA when low | logic (open drain + 100 k) |
| CH1_FLT_N | B1 | 0 / 5 V (low = fault) | ≤ 5 V | 50 µA + 42 µA base when low | logic (wired-AND open drain) |
| CH1_QFB | CH1_QFB | V5 − 0.7 … V5 | ≤ 5 V | 42 µA | bias (PNP base) |
| CH1_FLT | B1 | 0 / 4.9 V (high = fault) | ≤ 5 V | 4.2–9.1 mA | logic / LED drive |
| CH1_RUN | B1 | 0 / 5 V (high = run) | ≤ 5 V | 50 µA | logic |
| CH1_LSD | CH1_SPAN (rides on TAP0, spans B1–B2) | 0 V (on) … V_pair − 0.6 V (off) | ≤ 35.2 V | 0.35 mA | level shift |
| CH1_LSM | CH1_SPAN | midpoint of R147/R151: ≈ V_pair/2 when on, ≈ V_pair when off | ≤ 35.2 V | 0.35 mA | level shift |
| CH1_LSB | CH1_LS | TAP2 − 0.7 V (on) / TAP2 (off) | ≤ 35.2 V | 0.35 mA | level shift (PNP base) |
| CH1_LSC | B2 | TAP2 (on) / ≈ TAP1 (off) | ≤ 35.2 V | 90 µA | level shift |
| CH1_ENU | B2 | V_top/2 above TAP1 (on) / 0 (off) | ≤ 26.4 V | 90 µA | logic (LDO enable) |
| CH1_DTU, CH1_DTL | B1 | DT pin: ≈ 1 V (internal) | ≤ 1 V | µA | timing |
| CH1_PH1, CH1_PH2 | B1 | 0 / 12 V complementary, 100 kHz | ≤ 12 V | 1 mA | logic (clock) |
| CH1_OSCC, CH1_OSCR, CH1_OSCRC | B1 | 0–12 V RC timing | ≤ 12 V | 0.5 mA | timing |
| CH1_LEDR_A | B1 | ≈ 3.1 V | ≤ 4.3 V | 4.2–9.1 mA | LED drive |
| CH1_OPTO_A | B1 | ≈ 1.2 V | ≤ 1.65 V (opto V_F) | 4.2–9.1 mA | LED drive |
| CH1_LEDG_A | B1 | ≈ 2.0 V | ≤ 12 V | 1.0 mA | LED drive |

## 2. Board-level parts

| Refdes | Part | Footprint | Pin | Name | Net |
|---|---|---|---|---|---|
| J1 | Phoenix MSTBA 2,5/5-G-5,08 (1757271), 5-pos header [S] | Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_5-G-5,08_1x05_P5.08mm_Horizontal | 1 | pos 1 | TAP0_IN |
| | | | 2 | pos 2 | TAP1_IN |
| | | | 3 | pos 3 | TAP2_IN |
| | | | 4 | pos 4 | TAP3_IN |
| | | | 5 | pos 5 | TAP4_IN |
| F1 | Littelfuse 0477004.MXP 4 A T in 2 × 01000056Z clips | Fuse:Fuseholder_Clip-5x20mm_Littelfuse_100_Inline_P20.50x4.60mm_D1.30mm_Horizontal (pads "1"×2, "2"×2) | 1 | end 1 | TAP0_IN |
| | | | 2 | end 2 | TAP0 |
| F2 | same | same | 1 / 2 | ends | TAP1_IN / TAP1 |
| F3 | same | same | 1 / 2 | ends | TAP2_IN / TAP2 |
| F4 | same | same | 1 / 2 | ends | TAP3_IN / TAP3 |
| F5 | same | same | 1 / 2 | ends | TAP4_IN / TAP4 |
| J2 | Phoenix MSTBA 2,5/2-G-5,08 (1757242) [S] | Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal | 1 | pos 1 | ALM_C |
| | | | 2 | pos 2 | ALM_E |
| H1–H4 | M3 mounting hole, non-plated, no net | MountingHole:MountingHole_3.2mm_M3 | — | — | — |

**Channel use of the tap buses.**

| Bus | Channels |
|---|---|
| TAP0 | CH1 T_L |
| TAP1 | CH1 T_M, CH2 T_L |
| TAP2 | CH1 T_H, CH2 T_M, CH3 T_L |
| TAP3 | CH2 T_H, CH3 T_M |
| TAP4 | CH3 T_H |

## 3. Channel 1 (T_L = TAP0, T_M = TAP1, T_H = TAP2)

### 3.1 PWR_1: switched-capacitor cell

CSD18543Q3A pinout per TI SLPS633 p. 1 "Top View" [P]:

- Pins 1, 2, 3 = S
- Pin 4 = G
- Pins 5, 6, 7, 8 = D, plus the exposed pad = D

In KiCad (Transistor_FET:CSD18543Q3A with footprint
Package_SON:VSON-8_3.3x3.3mm_P0.65mm_NexFET), pads 1–3 = S, 4 = G, and pad 5 = D covers pins 5–8 and
the pad.

| Refdes | Role | Value / MPN | Pins → net |
|---|---|---|---|
| Q101 | Q_A: T_H → X (on in phase 1) | CSD18543Q3A | 1 S → CH1_X; 2 S → CH1_X; 3 S → CH1_X; 4 G → CH1_GA; 5–8 D + pad → TAP2 |
| Q102 | Q_B: X → T_M (on in phase 2) | CSD18543Q3A | 1–3 S → TAP1; 4 G → CH1_GB; 5–8 D + pad → CH1_X |
| Q103 | Q_C: T_M → Y (on in phase 1) | CSD18543Q3A | 1–3 S → CH1_Y; 4 G → CH1_GC; 5–8 D + pad → TAP1 |
| Q104 | Q_D: Y → T_L (on in phase 2) | CSD18543Q3A | 1–3 S → TAP0; 4 G → CH1_GD; 5–8 D + pad → CH1_Y |
| R101 | R_CFX 1/2, flying-path resistor | 0.086 Ω 1 % 2 W, WSL2816R0860FEH | 1 → CH1_X; 2 → CH1_CFP |
| R152 | R_CFX 2/2, in parallel with R101 (R_CFX = 0.043 Ω, 4 W) | 0.086 Ω 2 W, WSL2816R0860FEH | 1 → CH1_X; 2 → CH1_CFP |
| R102 | R_CFY 1/2 | 0.086 Ω 2 W, WSL2816R0860FEH | 1 → CH1_CFN; 2 → CH1_Y |
| R153 | R_CFY 2/2, in parallel with R102 | 0.086 Ω 2 W, WSL2816R0860FEH | 1 → CH1_CFN; 2 → CH1_Y |
| C101 | C_FLY 1/8 | 10 µF 50 V X7S 1210, GCJ32EC71H106KA01L | 1 → CH1_CFP; 2 → CH1_CFN |
| C102 | C_FLY 2/8 | same | 1 → CH1_CFP; 2 → CH1_CFN |
| C103 | C_FLY 3/8 | same | 1 → CH1_CFP; 2 → CH1_CFN |
| C104 | C_FLY 4/8 | same | 1 → CH1_CFP; 2 → CH1_CFN |
| C105 | C_FLY 5/8 | same | 1 → CH1_CFP; 2 → CH1_CFN |
| C106 | C_FLY 6/8 | same | 1 → CH1_CFP; 2 → CH1_CFN |
| C107 | C_FLY 7/8 | same | 1 → CH1_CFP; 2 → CH1_CFN |
| C108 | C_FLY 8/8 | same | 1 → CH1_CFP; 2 → CH1_CFN |
| C109 | C_TOP 1/4 (across B_{k+1}) | same | 1 → TAP2; 2 → TAP1 |
| C110 | C_TOP 2/4 | same | 1 → TAP2; 2 → TAP1 |
| C111 | C_TOP 3/4 | same | 1 → TAP2; 2 → TAP1 |
| C112 | C_TOP 4/4 | same | 1 → TAP2; 2 → TAP1 |
| C113 | C_BOT 1/4 (across B_k) | same | 1 → TAP1; 2 → TAP0 |
| C114 | C_BOT 2/4 | same | 1 → TAP1; 2 → TAP0 |
| C115 | C_BOT 3/4 | same | 1 → TAP1; 2 → TAP0 |
| C116 | C_BOT 4/4 | same | 1 → TAP1; 2 → TAP0 |
| C117 | C_TOP_E, bulk damping | 100 µF 35 V, UCZ1V101MCL1GS (Capacitor_SMD:CP_Elec_8x10, pad 1 = +) [S] | 1 (+) → TAP2; 2 (−) → TAP1 |
| C118 | C_BOT_E, bulk damping | same | 1 (+) → TAP1; 2 (−) → TAP0 |
| R103 | R_PX, flying-cap precharge (holds X at T_H at rest) | 100 kΩ 1 % 0603 | 1 → CH1_X; 2 → TAP2 |
| R104 | R_PY, precharge (holds Y at T_M at rest) | 100 kΩ 1 % 0603 | 1 → CH1_Y; 2 → TAP1 |

### 3.2 DRV_1: gate drivers

UCC21520ADWR pin functions per TI SLUSCJ9F Table 5-1 [P]: 1 INA, 2 INB, 3 VCCI, 4 GND, 5 DISABLE,
6 DT, 7 NC, 8 VCCI, 9 VSSB, 10 OUTB, 11 VDDB, 12 NC, 13 NC, 14 VSSA, 15 OUTA, 16 VDDA. The KiCad
symbol Driver_FET:UCC21520ADW has the same numbering.

| Refdes | Role | Value / MPN | Pins → net |
|---|---|---|---|
| U101 | Upper half-bridge driver (A → Q_A, B → Q_B) | UCC21520ADWR | 1 INA → CH1_PH1; 2 INB → CH1_PH2; 3 VCCI → CH1_12VL; 4 GND → TAP0; 5 DISABLE → TAP0; 6 DT → CH1_DTU; 7 NC → NC; 8 VCCI → CH1_12VL; 9 VSSB → TAP1; 10 OUTB → CH1_OB_U; 11 VDDB → CH1_12VU; 12 NC → NC; 13 NC → NC; 14 VSSA → CH1_X; 15 OUTA → CH1_OA_U; 16 VDDA → CH1_BSTU |
| U102 | Lower half-bridge driver (A → Q_C, B → Q_D) | UCC21520ADWR | 1 INA → CH1_PH1; 2 INB → CH1_PH2; 3 VCCI → CH1_12VL; 4 GND → TAP0; 5 DISABLE → TAP0; 6 DT → CH1_DTL; 7 NC → NC; 8 VCCI → CH1_12VL; 9 VSSB → TAP0; 10 OUTB → CH1_OB_L; 11 VDDB → CH1_12VL; 12 NC → NC; 13 NC → NC; 14 VSSA → CH1_Y; 15 OUTA → CH1_OA_L; 16 VDDA → CH1_BSTL |
| R105 | Gate resistor Q_A | 4.7 Ω 1 % 0603 | 1 → CH1_OA_U; 2 → CH1_GA |
| R106 | Gate resistor Q_B | 4.7 Ω | 1 → CH1_OB_U; 2 → CH1_GB |
| R107 | Gate resistor Q_C | 4.7 Ω | 1 → CH1_OA_L; 2 → CH1_GC |
| R108 | Gate resistor Q_D | 4.7 Ω | 1 → CH1_OB_L; 2 → CH1_GD |
| R109 | Gate–source pull-down Q_A (off when unpowered) | 10.0 kΩ 0603 | 1 → CH1_GA; 2 → CH1_X |
| R110 | G–S pull-down Q_B | 10.0 kΩ | 1 → CH1_GB; 2 → TAP1 |
| R111 | G–S pull-down Q_C | 10.0 kΩ | 1 → CH1_GC; 2 → CH1_Y |
| R112 | G–S pull-down Q_D | 10.0 kΩ | 1 → CH1_GD; 2 → TAP0 |
| R113 | Dead-time resistor U101: 200 ns (10 ns/kΩ) | 20.0 kΩ 1 % | 1 → CH1_DTU; 2 → TAP0 |
| C119 | DT noise cap U101 (≤ 1 nF per datasheet) | 470 pF C0G 50 V | 1 → CH1_DTU; 2 → TAP0 |
| R114 | Dead-time resistor U102 | 20.0 kΩ 1 % | 1 → CH1_DTL; 2 → TAP0 |
| C120 | DT noise cap U102 | 470 pF C0G | 1 → CH1_DTL; 2 → TAP0 |
| C121 | U101 VCCI bulk | 1 µF 25 V X7R 0603 | 1 → CH1_12VL; 2 → TAP0 |
| C122 | U101 VCCI HF | 100 nF 50 V 0603 | 1 → CH1_12VL; 2 → TAP0 |
| C123 | U102 VCCI bulk | 1 µF 25 V | 1 → CH1_12VL; 2 → TAP0 |
| C124 | U102 VCCI HF | 100 nF 50 V | 1 → CH1_12VL; 2 → TAP0 |
| C125 | U101 VDDB bulk | 1 µF 25 V | 1 → CH1_12VU; 2 → TAP1 |
| C126 | U101 VDDB HF | 100 nF 50 V | 1 → CH1_12VU; 2 → TAP1 |
| C127 | U102 VDDB bulk | 1 µF 25 V | 1 → CH1_12VL; 2 → TAP0 |
| C128 | U102 VDDB HF | 100 nF 50 V | 1 → CH1_12VL; 2 → TAP0 |
| C129 | Bootstrap cap U101 (VDDA–VSSA) | 1 µF 25 V | 1 → CH1_BSTU; 2 → CH1_X |
| C130 | Bootstrap cap U102 | 1 µF 25 V | 1 → CH1_BSTL; 2 → CH1_Y |
| D101 | Bootstrap diode U101 | BAS16W-7-F; SOT-323 pins 1 A, 2 NC, 3 K (KiCad Diode:BAS16W) [S] | 1 A → CH1_12VU; 2 NC → NC; 3 K → CH1_BSTU |
| D102 | Bootstrap diode U102 | BAS16W-7-F | 1 A → CH1_12VL; 2 NC → NC; 3 K → CH1_BSTL |

### 3.3 OSC_1: 100 kHz complementary clock

CD4047B pinout and "free running" connections per TI SCHS044C p. 1 terminal diagram and p. 2
"Functional terminal connections" [P]:

- Pins 4, 5, 6, 14 → VDD
- Pins 7, 8, 9, 12 → VSS
- R between pins 2 and 3; C between pins 1 and 3
- Outputs Q and /Q on pins 10 and 11, with t_A = 4.40 RC

| Refdes | Role | Value / MPN | Pins → net |
|---|---|---|---|
| U103 | Astable multivibrator | CD4047BM96 (KiCad 4xxx:4047, Package_SO:SOIC-14_3.9x8.7mm_P1.27mm) | 1 C → CH1_OSCC; 2 R → CH1_OSCR; 3 RC COMMON → CH1_OSCRC; 4 /ASTABLE → CH1_12VL; 5 ASTABLE → CH1_12VL; 6 −TRIGGER → CH1_12VL; 7 VSS → TAP0; 8 +TRIGGER → TAP0; 9 EXTERNAL RESET → TAP0; 10 Q → CH1_PH1; 11 /Q → CH1_PH2; 12 RETRIGGER → TAP0; 13 OSC OUT → NC; 14 VDD → CH1_12VL |
| R115 | Timing R | 22.1 kΩ 1 % 0603 | 1 → CH1_OSCR; 2 → CH1_OSCRC |
| C131 | Timing C | 100 pF C0G 5 % 50 V | 1 → CH1_OSCC; 2 → CH1_OSCRC |
| C132 | VDD decoupling | 100 nF 50 V | 1 → CH1_12VL; 2 → TAP0 |

### 3.4 SUP_1: supplies, enable level shifter, channel jumper

**TPS7A1601DGNR** pins per TI SBVS171F "Pin Functions" [P]: 1 OUT, 2 FB, 3 PG, 4 GND, 5 EN, 6 NC,
7 DELAY, 8 IN, plus the PowerPAD (pad 9 in the footprint).

- EN must satisfy EN ≤ IN + 0.3 V; enabled ≥ 1.2 V; disabled ≤ 0.3 V.
- Custom symbol. Footprint: Package_SO:Texas_DGN0008D_VSSOP-8-1EP_3x3mm_P0.65mm_EP2x2.94mm_Mask1.57x1.89mm.

**TPS70950DBVR** pins per TI SBVS186H Table 5-1, DBV TPS709 column [P]: 1 IN, 2 GND, 3 EN, 4 NC,
5 OUT.

- EN has an internal 300 nA pull-up, a 6.5 V clamp, and must not be tied to IN.
- Custom symbol. Footprint: Package_TO_SOT_SMD:SOT-23-5.

| Refdes | Role | Value / MPN | Pins → net |
|---|---|---|---|
| U104 | 12V_L gated LDO (domain B1, powered from B_k) | TPS7A1601DGNR | 1 OUT → CH1_12VL; 2 FB → CH1_FBL; 3 PG → NC; 4 GND → TAP0; 5 EN → CH1_RUN; 6 NC → NC; 7 DELAY → NC; 8 IN → TAP1; 9 PowerPAD → TAP0 |
| R116 | FB top: 12.04 V = 1.193 × (1 + 909/100) | 909 kΩ 1 % | 1 → CH1_12VL; 2 → CH1_FBL |
| R117 | FB bottom | 100 kΩ 1 % | 1 → CH1_FBL; 2 → TAP0 |
| C133 | U104 input | 1 µF 50 V X7R 0805 | 1 → TAP1; 2 → TAP0 |
| C134 | U104 output | 10 µF 25 V X7R 1206 | 1 → CH1_12VL; 2 → TAP0 |
| U105 | 12V_U gated LDO (domain B2, powered from B_{k+1}) | TPS7A1601DGNR | 1 OUT → CH1_12VU; 2 FB → CH1_FBU; 3 PG → NC; 4 GND → TAP1; 5 EN → CH1_ENU; 6 NC → NC; 7 DELAY → NC; 8 IN → TAP2; 9 PowerPAD → TAP1 |
| R118 | FB top | 909 kΩ 1 % | 1 → CH1_12VU; 2 → CH1_FBU |
| R119 | FB bottom | 100 kΩ 1 % | 1 → CH1_FBU; 2 → TAP1 |
| C135 | U105 input | 1 µF 50 V 0805 | 1 → TAP2; 2 → TAP1 |
| C136 | U105 output | 10 µF 25 V 1206 | 1 → CH1_12VU; 2 → TAP1 |
| U106 | V5 always-on LDO (domain B1) | TPS70950DBVR | 1 IN → CH1_V5IN; 2 GND → TAP0; 3 EN → CH1_V5EN; 4 NC → NC; 5 OUT → CH1_V5 |
| C137 | U106 input | 1 µF 50 V 0805 | 1 → CH1_V5IN; 2 → TAP0 |
| C138 | U106 output (≥ 2.2 µF) | 2.2 µF 16 V X7R 0603 | 1 → CH1_V5; 2 → TAP0 |
| C139 | EN noise filter (internal pull-up enables it in ≈ 30 ms) | 10 nF 50 V | 1 → CH1_V5EN; 2 → TAP0 |
| JP101 | Channel enable: fit for N ≥ 2 (CH1), N ≥ 3 (CH2), N = 4 (CH3) | 2-pin header + shunt (Würth 61300211121 / 60900213421) [S]; KiCad Jumper:Jumper_2_Open, Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical | 1 → TAP1; 2 → CH1_V5IN |
| Q106 | Level-shift NMOS (RUN → domain U) | 2N7002-7-F; SOT-23: 1 G, 2 S, 3 D per DS11303 p. 1 [P] | 1 G → CH1_RUN; 2 S → TAP0; 3 D → CH1_LSD |
| R147 | Q106 drain → Q107 base, half 1 of 2. Two in series so one shorted resistor still leaves ≥ 49.9 kΩ between TAP2 and TAP0. | 49.9 kΩ 1 % 0603 | 1 → CH1_LSD; 2 → CH1_LSM |
| R151 | Q106 drain → Q107 base, half 2 of 2 | 49.9 kΩ 1 % 0603 | 1 → CH1_LSM; 2 → CH1_LSB |
| Q107 | Level-shift PNP | MMBT3906-7-F; SOT-23: 1 B, 2 E, 3 C per DS30059 p. 1 [P] | 1 B → CH1_LSB; 2 E → TAP2; 3 C → CH1_LSC |
| R148 | Q107 base–emitter | 100 kΩ | 1 → CH1_LSB; 2 → TAP2 |
| R149 | Q107 collector → EN divider | 100 kΩ | 1 → CH1_LSC; 2 → CH1_ENU |
| R150 | EN divider bottom | 100 kΩ | 1 → CH1_ENU; 2 → TAP1 |
| C150 | EN filter | 10 nF 50 V | 1 → CH1_ENU; 2 → TAP1 |

### 3.5 SUPV_1: wake, ratio lockout, thermal, indication, alarm

**REF35250QDBVR** pins per TI SNAS809C Table 5-1 [P]: 1 GND, 2 GND, 3 EN, 4 VIN, 5 NR, 6 VREF. KiCad
Reference_Voltage:REF35250QDBVR has the same numbering.

**TLV7044PWR** pins per TI SLVSE13J Table 4-3, TSSOP column [P]: 1 OUT A, 2 −IN A, 3 +IN A, 4 VCC,
5 +IN B, 6 −IN B, 7 OUT B, 8 OUT C, 9 −IN C, 10 +IN C, 11 VEE, 12 +IN D, 13 −IN D, 14 OUT D.

- Outputs are open drain.
- Custom symbol; the pinout is identical to Amplifier_Operational:LM324.
- Footprint: Package_SO:TSSOP-14_4.4x5mm_P0.65mm.

**SN74LVC1G02DBVR** pins per TI SCES213Y §4, DBV [P]: 1 A, 2 B, 3 GND, 4 Y, 5 VCC. KiCad
74xGxx:74LVC1G02 matches.

**SFH617A-3X017T** pins per Vishay 83740 p. 1 [P]: 1 anode, 2 cathode, 3 emitter, 4 collector.
KiCad Isolator:SFH617A-3X017T matches.

**LEDs.** Device:LED, pin 1 = K, 2 = A; LED_SMD:LED_0603_1608Metric. The Rohm cathode mark was
not cross-checked [S].

| Refdes | Role | Value / MPN | Pins → net |
|---|---|---|---|
| U107 | 2.5 V reference | REF35250QDBVR | 1 GND → TAP0; 2 GND → TAP0; 3 EN → CH1_V5; 4 VIN → CH1_V5; 5 NR → NC; 6 VREF → CH1_VREF |
| C140 | U107 input | 100 nF 50 V | 1 → CH1_V5; 2 → TAP0 |
| C141 | U107 output (0.1–10 µF allowed) | 1 µF 25 V 0603 | 1 → CH1_VREF; 2 → TAP0 |
| U108 | Quad comparator: A wake, B top-high, C top-low, D over-temperature | TLV7044PWR | 1 OUT A → CH1_NCHG; 2 −IN A → CH1_PON; 3 +IN A → CH1_VREF; 4 VCC → CH1_V5; 5 +IN B → CH1_N; 6 −IN B → CH1_PLO; 7 OUT B → CH1_FLT_N; 8 OUT C → CH1_FLT_N; 9 −IN C → CH1_N; 10 +IN C → CH1_PHI; 11 VEE → TAP0; 12 +IN D → CH1_TH; 13 −IN D → CH1_VREF; 14 OUT D → CH1_FLT_N |
| C142 | U108 decoupling | 100 nF 50 V | 1 → CH1_V5; 2 → TAP0 |
| R120 | Wake string top 1/4 | 2.00 MΩ 0.1 % 25 ppm 1206, TNPW12062M00BEEA | 1 → TAP2; 2 → CH1_PON_A |
| R121 | Wake string top 2/4 | same | 1 → CH1_PON_A; 2 → CH1_PON_B |
| R122 | Wake string top 3/4 | same | 1 → CH1_PON_B; 2 → CH1_PON_C |
| R123 | Wake string top 4/4 | same | 1 → CH1_PON_C; 2 → CH1_PON |
| R124 | Wake string bottom 1/2 (parallel) | 1.67 MΩ 0.1 % 1206, TNPW12061M67BEEA | 1 → CH1_PON; 2 → TAP0 |
| R125 | Wake string bottom 2/2 | same | 1 → CH1_PON; 2 → TAP0 |
| C143 | Wake filter (τ 0.36 s) | 470 nF 25 V 0603 | 1 → CH1_PON; 2 → TAP0 |
| R126 | P_LO top 1/2 | 4.99 MΩ 1 % 0603 | 1 → TAP2; 2 → CH1_PLO_M |
| R127 | P_LO top 2/2 | 4.99 MΩ | 1 → CH1_PLO_M; 2 → CH1_PLO |
| R128 | P_LO bottom 1/2 | 1.00 MΩ 1 % | 1 → CH1_PLO; 2 → TAP0 |
| R129 | P_LO bottom 2/2 | 1.00 MΩ | 1 → CH1_PLO; 2 → TAP0 |
| C144 | P_LO filter (τ 0.22 s) | 470 nF 25 V | 1 → CH1_PLO; 2 → TAP0 |
| R130 | P_HI top 1/2 | 4.99 MΩ 1 % | 1 → TAP2; 2 → CH1_PHI_M |
| R131 | P_HI top 2/2 | 4.99 MΩ | 1 → CH1_PHI_M; 2 → CH1_PHI |
| R132 | P_HI bottom 1/2 | 1.10 MΩ 1 % | 1 → CH1_PHI; 2 → TAP0 |
| R133 | P_HI bottom 2/2 | 1.10 MΩ | 1 → CH1_PHI; 2 → TAP0 |
| C145 | P_HI filter (τ 0.25 s) | 470 nF 25 V | 1 → CH1_PHI; 2 → TAP0 |
| R134 | N top 1/2 (from T_M) | 2.26 MΩ 1 % | 1 → TAP1; 2 → CH1_N_M |
| R135 | N top 2/2 | 2.26 MΩ | 1 → CH1_N_M; 2 → CH1_N |
| R136 | N bottom 1/2 | 1.00 MΩ 1 % | 1 → CH1_N; 2 → TAP0 |
| R137 | N bottom 2/2 | 1.00 MΩ | 1 → CH1_N; 2 → TAP0 |
| C146 | N filter (τ 0.21 s) | 470 nF 25 V | 1 → CH1_N; 2 → TAP0 |
| R138 | NTC bias | 24.9 kΩ 1 % | 1 → CH1_V5; 2 → CH1_TH |
| RT101 | Board thermistor, placed at R101/R152/Q101 | 470 kΩ NTC, NCP15WM474E03RC (Device:Thermistor_NTC, R_0402_1005Metric) | 1 → CH1_TH; 2 → TAP0 |
| C147 | TH filter (τ ≈ 12 ms) | 1 µF 25 V 0603 | 1 → CH1_TH; 2 → TAP0 |
| R139 | FLT_N pull-up | 100 kΩ 1 % | 1 → CH1_V5; 2 → CH1_FLT_N |
| R140 | NCHG pull-up | 100 kΩ 1 % | 1 → CH1_V5; 2 → CH1_NCHG |
| U109 | RUN = NOR(NCHG, FLT) | SN74LVC1G02DBVR (Package_TO_SOT_SMD:SOT-23-5) | 1 A → CH1_NCHG; 2 B → CH1_FLT; 3 GND → TAP0; 4 Y → CH1_RUN; 5 VCC → CH1_V5 |
| C148 | U109 decoupling | 100 nF 50 V | 1 → CH1_V5; 2 → TAP0 |
| R141 | RUN pull-down (keeps LDOs off if V5 is absent) | 100 kΩ 1 % | 1 → CH1_RUN; 2 → TAP0 |
| C149 | RUN filter | 10 nF 50 V | 1 → CH1_RUN; 2 → TAP0 |
| Q105 | Fault driver PNP | MMBT3906-7-F | 1 B → CH1_QFB; 2 E → CH1_V5; 3 C → CH1_FLT |
| R142 | Q105 base | 100 kΩ 1 % | 1 → CH1_FLT_N; 2 → CH1_QFB |
| R143 | Q105 base–emitter | 100 kΩ | 1 → CH1_QFB; 2 → CH1_V5 |
| R144 | FLT pull-down (clean logic low) | 100 kΩ | 1 → CH1_FLT; 2 → TAP0 |
| R145 | Fault LED + opto current: (4.85 − 2.4 − 1.4)/251 ≥ 4.2 mA, ≤ 9.1 mA (calc opto_*) | 249 Ω 1 % | 1 → CH1_FLT; 2 → CH1_LEDR_A |
| D103 | FAULT LED (red) | SML-D12V1WT86 | 1 K → CH1_OPTO_A; 2 A → CH1_LEDR_A |
| U110 | Alarm opto (series with D103) | SFH617A-3X017T (Package_DIP:SMDIP-4_W9.53mm_Clearance8mm) | 1 A → CH1_OPTO_A; 2 K → TAP0; 3 E → ALM_E; 4 C → ALM_C |
| R146 | ACTIVE LED current, (12 − 2.0)/10 k = 1.0 mA | 10.0 kΩ 1 % | 1 → CH1_12VL; 2 → CH1_LEDG_A |
| D104 | ACTIVE LED (green) | SML-D12M1WT86 | 1 K → TAP0; 2 A → CH1_LEDG_A |

### 3.6 Net membership

The net-by-net member lists are generated: `out/netlist.json` (`nets`) after `kaesynth build`. The
KiCad round trip checks that the schematic matches it pin for pin. NC pins per channel:
U101.7, .12, .13; U102.7, .12, .13; U103.13; U104.3, .6, .7; U105.3, .6, .7; U106.4; U107.5; D101.2;
D102.2.

Per-channel part totals:

- Q101–Q107 (7), U101–U110 (10), D101–D104 (4)
- R101–R153 (53), C101–C150 (50), RT101, JP101

That is **126 placed parts per channel**, 378 for three channels. Adding J1, J2, F1–F5 and H1–H4
gives **389 placed parts**. BOM-only items: shunts JS101/JS201/JS301 (fitted per §4), fuse clips
XC1–XC10 (two per fuse, pads in the F footprint) and the harness (§5).

## 4. Channels 2 and 3: substitution rule

Copy §3 with these substitutions, applied to every row:

| Item | Channel 1 | Channel k |
|---|---|---|
| Refdes | Xnnn with hundreds digit 1 (Q101, R151, RT101, JP101) | hundreds digit k (Q201…, Q301…) |
| Channel nets | CH1_<name> | CHk_<name> |
| T_L | TAP0 | TAP(k−1): CH2 → TAP1, CH3 → TAP2 |
| T_M | TAP1 | TAPk: CH2 → TAP2, CH3 → TAP3 |
| T_H | TAP2 | TAP(k+1): CH2 → TAP3, CH3 → TAP4 |
| ALM_C, ALM_E | shared | shared; all three optos in parallel |
| Silkscreen | "CH1 ACT / FLT / EN(N≥2)" | "CH2 … EN(N≥3)", "CH3 … EN(N=4)" |

So for channel 2:

- Q201.5-8 → TAP3 and Q204.1-3 → TAP1.
- U201.9 → TAP2, U202.4/.5/.9 → TAP1, JP201.1 → TAP2, R220.1 → TAP3, R234.1 → TAP2.
- U210.2 → TAP1.

Voltage ratings are identical for every channel because each channel sees only its own two
batteries. Only the "V to T0" column rises by (k−1) × Vb, which matters for the spacing rules in
DESIGN.md §6.

**Jumper setting by battery count.**

| N | JP101 | JP201 | JP301 | Harness positions wired (others bridged in the plug, §5) |
|---|---|---|---|---|
| 2 | fit | open | open | 1–3 |
| 3 | fit | fit | open | 1–4 |
| 4 | fit | fit | fit | 1–5 |

## 5. Off-board harness (block `harness`, `board="off"`: in the BOM and system schematic, not on the PCB)

Nets: POSTj is battery terminal Tj; TAPj_IN runs from the harness fuse through plug P1 to J1.

| Refdes | Qty | MPN / spec | Connection |
|---|---|---|---|
| W0–W4 | N + 1 | 14 AWG UL1015 600 V 105 °C, tinned (Alpha Wire 14 AWG UL1015 [I]); W0 black, W1–W4 red with number sleeves; ≤ 3 m. 16 AWG is allowed up to 2 m (REQ-6, calc i_bal_*). | Wj: post Tj → FHj → P1 position j+1 |
| LG0–LG4 | N + 1 | Panduit PV14-516R-L (16–14 AWG, 5/16 in stud) [S]; match the battery stud (M6/M8) | pin 1 → POSTj; stacked on top of the main cable lug |
| FH0–FH4 | N + 1 | Littelfuse KLKD010.T, 10 A, 600 VDC, 10/50 kA DC [P] | 1 → POSTj; 2 → TAPj_IN |
| XF0–XF4 | N + 1 | Eaton Bussmann HEB-AW-RLC-A in-line holder (crimp 16–8 AWG) [S] | holds FHj, ≤ 150 mm from the ring lug |
| FE0–FE4 | N + 1 | Phoenix AI 2,5-8 BU (3200522) ferrule for 2.5 mm² / 14 AWG [S] | wire ends in P1 |
| P1 | 1 | Phoenix MSTB 2,5/5-ST-5,08 (1757048) [S] | position j+1 → TAPj_IN, mates J1 |
| BRj | per unused position | 14 AWG link inside P1 | 1 → TAPj_IN; 2 → TAP(N)_IN (N < 4 only) |
| P2 | 1 | Phoenix MSTB 2,5/2-ST-5,08 (1757019) [S] | 1 = ALM_C (to the external pull-up, ≤ 30 V); 2 = ALM_E (external return) |

**Mapping of plug positions to battery terminals.** The pre-plug check (DESIGN V-13) is that each
used position reads about j × 12.7 V relative to position 1, increasing monotonically.

Unused positions are bridged with a short 14 AWG link (BRj) inside the plug to the highest used position,
so they read the stack voltage. This keeps the unused channel's T_H from floating below its T_M
(DESIGN §9).

| Plug pos | Wire | Battery terminal (N = 4) | N = 3 | N = 2 |
|---|---|---|---|---|
| 1 | W0 | B1 − (system negative) | B1 − | B1 − |
| 2 | W1 | B1 + / B2 − | B1 + | B1 + |
| 3 | W2 | B2 + / B3 − | B2 + | B2 + (stack +) |
| 4 | W3 | B3 + / B4 − | B3 + (stack +) | bridge to pos 3 (no wire) |
| 5 | W4 | B4 + (stack +) | bridge to pos 4 (no wire) | bridge to pos 3 (no wire) |

## 6. Pin-number sources

| Part | Source of pin numbers |
|---|---|
| CSD18543Q3A | TI SLPS633 (Dec 2016) p. 1 top-view pinout [P] |
| UCC21520ADWR | TI SLUSCJ9F (Nov 2024) Table 5-1 [P] |
| CD4047BM96 | TI SCHS044C p. 1 terminal diagram; p. 2 functional terminal connections table [P] |
| TPS7A1601DGNR | TI SBVS171F (Oct 2015) Pin Functions table [P] |
| TPS70950DBVR | TI SBVS186H (Jul 2021) Table 5-1, DBV TPS709 column [P] |
| REF35250QDBVR | TI SNAS809C (Sep 2024) Table 5-1 [P] |
| TLV7044PWR | TI SLVSE13J (Nov 2024) Table 4-3 [P] |
| SN74LVC1G02DBVR | TI SCES213Y (Aug 2026) §4 [P] |
| SFH617A-3X017T | Vishay 83740 Rev 2.5 p. 1 [P] |
| 2N7002-7-F | Diodes DS11303 Rev 40-2 p. 1 [P] |
| MMBT3906-7-F | Diodes DS30059 Rev 23-2 p. 1 [P] |
| BAS16W-7-F | KiCad Diode:BAS16W (1 A, 2 NC, 3 K) [S]; SOT-23 BAS16 (Zetex) read [P] |
| Two-terminal parts (R, C, NTC, fuse) | non-polar; C_Polarized pad 1 = + (KiCad CP_Elec) [S]; LED pin 1 = K (KiCad Device:LED) [S] |
| Phoenix MSTB/MSTBA | positions numbered 1…n along the header; datasheet not reachable [S] |
