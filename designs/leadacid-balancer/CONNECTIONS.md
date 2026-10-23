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
| TAP0_IN, TAP0 | B1 (root, = system ground) | 0 | 0 | ≤ 0.7 A normal; 4.3 A at the window edge (failing battery) | power / reference |
| TAP1_IN, TAP1 | B1 | Vb | 1 × Vb (10.5–17.6) | ≤ 2.0 A normal; 8.5 A at the edge (middle tap) | power |
| TAP2_IN, TAP2 | B2 | Vb above TAP1 | 2 × Vb (21–35.2) | as TAP1 | power |
| TAP3_IN, TAP3 | B3 | Vb above TAP2 | 3 × Vb (31.5–52.8) | as TAP1 | power |
| TAP4_IN, TAP4 | B4 | Vb above TAP3 | 4 × Vb (42–70.2) | as TAP0 | power |
| ALM_C | ISO | 0–30 V vs ALM_E (external supply) | floating; assumed ≤ ±100 V | ≤ 1 mA | isolated signal (+ side) |
| ALM_S1, ALM_S2, ALM_S3 | ISO | 0–30 V | floating | ≤ 1 mA | series alarm chain: D1 → U110 C–E → U210 C–E → U310 C–E |
| ALM_E | ISO | reference of the alarm contact | floating | ≤ 1 mA | isolated signal (− side) |

### 1.2 Channel-1 nets

Generated from `out/netlist.json`. Voltage is relative to the domain's reference (DESIGN.md §6); for channel k add (k−1) × Vb to reach T0. Max current in A (window-edge values for the power nets).

| Net | Domain | V to own reference | Max current (A) | Kind |
|---|---|---|---|---|
| CH1_X | B2 | -1 … 21 V | 9.1 | switching |
| CH1_Y | B1 | -1 … 21 V | 9.1 | switching |
| CH1_CFP | CH1_HSU | -0.4 … 0.4 V | 9.1 | switching |
| CH1_CFN | CH1_HSL | -0.4 … 0.4 V | 9.1 | switching |
| CH1_GA | CH1_HSU | -2 … 12.5 V | — | switching |
| CH1_OA_U | CH1_HSU | -2 … 12.5 V | — | switching |
| CH1_BSTU | CH1_HSU | 0 … 12.5 V | 0.0013 | power |
| CH1_GB | B2 | -2 … 12.5 V | — | switching |
| CH1_OB_U | B2 | -2 … 12.5 V | — | switching |
| CH1_GC | CH1_HSL | -2 … 12.5 V | — | switching |
| CH1_OA_L | CH1_HSL | -2 … 12.5 V | — | switching |
| CH1_BSTL | CH1_HSL | 0 … 12.5 V | 0.0013 | power |
| CH1_GD | B1 | -2 … 12.5 V | — | switching |
| CH1_OB_L | B1 | -2 … 12.5 V | — | switching |
| CH1_12VL | B1 | 0 … 12.5 V | 0.015 | power |
| CH1_12VU | B2 | 0 … 12.5 V | 0.008 | power |
| CH1_FBL | B1 | 0 … 1.25 V | — | analog |
| CH1_FBU | B2 | 0 … 1.25 V | — | analog |
| CH1_V5IN | B1 | 0 … 20 V | 0.01 | power |
| CH1_V5 | B1 | 0 … 5.05 V | 0.01 | power |
| CH1_V5EN | B1 | 0 … 6.5 V | — | signal |
| CH1_VREF | B1 | 0 … 2.5 V | — | analog |
| CH1_PON_M1 | CH1_SPAN | 0 … 30.9 V | — | sense |
| CH1_PON_M2 | B1 | 0 … 21.9 V | — | sense |
| CH1_PON_M3 | B1 | 0 … 12.8 V | — | sense |
| CH1_PON | B1 | 0 … 3.78 V | — | sense |
| CH1_PLO_M1 | CH1_SPAN | 0 … 30.9 V | — | sense |
| CH1_PLO_M2 | B1 | 0 … 21.7 V | — | sense |
| CH1_PLO_M3 | B1 | 0 … 12.6 V | — | sense |
| CH1_PWH | B1 | 0 … 3.68 V | — | sense |
| CH1_PLO | B1 | 0 … 3.61 V | — | sense |
| CH1_PHI_M1 | CH1_SPAN | 0 … 31 V | — | sense |
| CH1_PHI_M2 | B1 | 0 … 22 V | — | sense |
| CH1_PHI_M3 | B1 | 0 … 12.9 V | — | sense |
| CH1_PHI | B1 | 0 … 3.92 V | — | sense |
| CH1_PWL | B1 | 0 … 3.83 V | — | sense |
| CH1_N_M1 | B1 | 0 … 11.9 V | — | sense |
| CH1_N | B1 | 0 … 3.76 V | — | sense |
| CH1_TH | B1 | 0 … 5.05 V | — | sense |
| CH1_NCHG | B1 | 0 … 5.05 V | — | signal |
| CH1_FLT_N | B1 | 0 … 5.05 V | — | signal |
| CH1_QFB | CH1_QFB | -0.8 … 0 V | — | signal |
| CH1_FLT | B1 | 0 … 5.05 V | — | signal |
| CH1_LEDQ | B1 | 0 … 5.05 V | 0.0045 | signal |
| CH1_OKA | B1 | 0 … 1.65 V | 0.0047 | signal |
| CH1_PAUSE | B1 | 0 … 5.05 V | — | signal |
| CH1_TPN | B1 | 0 … 5.05 V | — | analog |
| CH1_TCT | B1 | 0 … 5.05 V | — | analog |
| CH1_TSM | B1 | 0 … 5.05 V | — | analog |
| CH1_PDA | B1 | 0 … 5.05 V | — | analog |
| CH1_BSU_A | B2 | 0 … 12.5 V | 0.0013 | power |
| CH1_BSL_A | B1 | 0 … 12.5 V | 0.0013 | power |
| CH1_RUN | B1 | 0 … 5.05 V | — | signal |
| CH1_LSD | CH1_SPAN | 0 … 40 V | 0.0004 | signal |
| CH1_LSM | CH1_SPAN | 0 … 40 V | 0.0004 | signal |
| CH1_LSB | CH1_LS | -1 … 0 V | 0.0004 | signal |
| CH1_LSC | B2 | 0 … 20 V | — | signal |
| CH1_ENU | B2 | 0 … 10 V | — | signal |
| CH1_DTU | B1 | 0 … 1.2 V | — | analog |
| CH1_DTL | B1 | 0 … 1.2 V | — | analog |
| CH1_PH1 | B1 | 0 … 12.5 V | — | clock |
| CH1_PH2 | B1 | 0 … 12.5 V | — | clock |
| CH1_OSCC | B1 | -0.5 … 13 V | — | analog |
| CH1_OSCR | B1 | -0.5 … 13 V | — | analog |
| CH1_OSCRC | B1 | -0.5 … 13 V | — | analog |
| CH1_LEDR_A | B1 | 0 … 2.6 V | 0.0045 | signal |
| CH1_LEDG_A | B1 | 0 … 2.6 V | 0.0011 | signal |

## 2. Board-level parts

| Refdes | Part | Footprint | Pin | Name | Net |
|---|---|---|---|---|---|
| J1 | Phoenix MSTBA 2,5/5-G-5,08 (1757271), 5-pos header [S] | Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_5-G-5,08_1x05_P5.08mm_Horizontal | 1 | pos 1 | TAP0_IN |
| | | | 2 | pos 2 | TAP1_IN |
| | | | 3 | pos 3 | TAP2_IN |
| | | | 4 | pos 4 | TAP3_IN |
| | | | 5 | pos 5 | TAP4_IN |
| F1 | Littelfuse KLKD006.T 6 A fast, 600 VDC, 10 kA DC [P], in a Keystone 3576 holder (XH1) | custom:Fuseholder_Keystone_3576_10x38mm (drawn from Keystone catalog p.45) | 1 / 2 | ends | TAP0_IN / TAP0 |
| F2–F5 | same (XH2–XH5) | same | 1 / 2 | ends | TAPj_IN / TAPj (j = 1…4) |
| J2 | Phoenix MSTBA 2,5/2-G-5,08 (1757242) [S] | Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal | 1 | pos 1 | ALM_C |
| | | | 2 | pos 2 | ALM_E |
| D1 | BAS16W-7-F, alarm-loop reverse blocking | Package_TO_SOT_SMD:SOT-323_SC-70 | 1 / 3 | A / K | ALM_C / ALM_S1 |
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

Generated from `out/netlist.json` (the KiCad round trip is identical to it). Pin numbers are footprint pads; datasheet pin functions and their sources are in §6 and parts.py. CSD18543Q3A pad 5 = drain pins 5–8 + pad; TPS7A1601 pad 9 = PowerPAD.

| Refdes | Role | Value (MPN) | Pins → net |
|---|---|---|---|
| C101 | C_FLY 1/8 | 10u (GCJ32EC71H106KA01L) | 1 → CH1_CFP; 2 → CH1_CFN |
| C102 | C_FLY 2/8 | 10u (GCJ32EC71H106KA01L) | 1 → CH1_CFP; 2 → CH1_CFN |
| C103 | C_FLY 3/8 | 10u (GCJ32EC71H106KA01L) | 1 → CH1_CFP; 2 → CH1_CFN |
| C104 | C_FLY 4/8 | 10u (GCJ32EC71H106KA01L) | 1 → CH1_CFP; 2 → CH1_CFN |
| C105 | C_FLY 5/8 | 10u (GCJ32EC71H106KA01L) | 1 → CH1_CFP; 2 → CH1_CFN |
| C106 | C_FLY 6/8 | 10u (GCJ32EC71H106KA01L) | 1 → CH1_CFP; 2 → CH1_CFN |
| C107 | C_FLY 7/8 | 10u (GCJ32EC71H106KA01L) | 1 → CH1_CFP; 2 → CH1_CFN |
| C108 | C_FLY 8/8 | 10u (GCJ32EC71H106KA01L) | 1 → CH1_CFP; 2 → CH1_CFN |
| C109 | C_TOP (across B_top) | 10u (GCJ32EC71H106KA01L) | 1 → TAP2; 2 → TAP1 |
| C110 | C_TOP (across B_top) | 10u (GCJ32EC71H106KA01L) | 1 → TAP2; 2 → TAP1 |
| C111 | C_TOP (across B_top) | 10u (GCJ32EC71H106KA01L) | 1 → TAP2; 2 → TAP1 |
| C112 | C_TOP (across B_top) | 10u (GCJ32EC71H106KA01L) | 1 → TAP2; 2 → TAP1 |
| C113 | C_BOT (across B_bot) | 10u (GCJ32EC71H106KA01L) | 1 → TAP1; 2 → TAP0 |
| C114 | C_BOT (across B_bot) | 10u (GCJ32EC71H106KA01L) | 1 → TAP1; 2 → TAP0 |
| C115 | C_BOT (across B_bot) | 10u (GCJ32EC71H106KA01L) | 1 → TAP1; 2 → TAP0 |
| C116 | C_BOT (across B_bot) | 10u (GCJ32EC71H106KA01L) | 1 → TAP1; 2 → TAP0 |
| C117 | C_TOP bulk | 100u (UCZ1V101MCL1GS) | 1 → TAP2; 2 → TAP1 |
| C118 | C_BOT bulk | 100u (UCZ1V101MCL1GS) | 1 → TAP1; 2 → TAP0 |
| C119 | DT filter U101 | 470p (GRM1885C1H471JA01D) | 1 → CH1_DTU; 2 → TAP0 |
| C120 | DT filter U102 | 470p (GRM1885C1H471JA01D) | 1 → CH1_DTL; 2 → TAP0 |
| C121 |  | 1u (GRM188R71E105KA12D) | 1 → CH1_12VL; 2 → TAP0 |
| C122 |  | 100n (GRM188R71H104KA93D) | 1 → CH1_12VL; 2 → TAP0 |
| C123 |  | 1u (GRM188R71E105KA12D) | 1 → CH1_12VL; 2 → TAP0 |
| C124 |  | 100n (GRM188R71H104KA93D) | 1 → CH1_12VL; 2 → TAP0 |
| C125 |  | 1u (GRM188R71E105KA12D) | 1 → CH1_12VU; 2 → TAP1 |
| C126 |  | 100n (GRM188R71H104KA93D) | 1 → CH1_12VU; 2 → TAP1 |
| C127 |  | 1u (GRM188R71E105KA12D) | 1 → CH1_12VL; 2 → TAP0 |
| C128 |  | 100n (GRM188R71H104KA93D) | 1 → CH1_12VL; 2 → TAP0 |
| C129 | bootstrap U101 | 1u (GRM188R71E105KA12D) | 1 → CH1_BSTU; 2 → CH1_X |
| C130 | bootstrap U102 | 1u (GRM188R71E105KA12D) | 1 → CH1_BSTL; 2 → CH1_Y |
| C131 | timing C | 100p (GRM1885C1H101JA01D) | 1 → CH1_OSCC; 2 → CH1_OSCRC |
| C132 |  | 100n (GRM188R71H104KA93D) | 1 → CH1_12VL; 2 → TAP0 |
| C133 |  | 1u (GRM21BR71H105KA12L) | 1 → TAP1; 2 → TAP0 |
| C134 |  | 10u (GRM31CR71E106KA12L) | 1 → CH1_12VL; 2 → TAP0 |
| C135 |  | 1u (GRM21BR71H105KA12L) | 1 → TAP2; 2 → TAP1 |
| C136 |  | 10u (GRM31CR71E106KA12L) | 1 → CH1_12VU; 2 → TAP1 |
| C137 |  | 1u (GRM21BR71H105KA12L) | 1 → CH1_V5IN; 2 → TAP0 |
| C138 |  | 4.7u (GRM21BR71E475KA73L) | 1 → CH1_V5; 2 → TAP0 |
| C139 |  | 10n (GRM188R71H103KA01D) | 1 → CH1_V5EN; 2 → TAP0 |
| C140 |  | 100n (GRM188R71H104KA93D) | 1 → CH1_V5; 2 → TAP0 |
| C141 |  | 1u (GRM188R71E105KA12D) | 1 → CH1_VREF; 2 → TAP0 |
| C142 |  | 100n (GRM188R71H104KA93D) | 1 → CH1_V5; 2 → TAP0 |
| C143 | PON filter | 470n (GRM188R71E474KA12D) | 1 → CH1_PON; 2 → TAP0 |
| C144 | PLO filter | 470n (GRM188R71E474KA12D) | 1 → CH1_PLO; 2 → TAP0 |
| C145 | PHI filter | 470n (GRM188R71E474KA12D) | 1 → CH1_PHI; 2 → TAP0 |
| C146 | N filter | 470n (GRM188R71E474KA12D) | 1 → CH1_N; 2 → TAP0 |
| C147 | TH filter | 1u (GRM188R71E105KA12D) | 1 → CH1_TH; 2 → TAP0 |
| C148 |  | 100n (GRM188R71H104KA93D) | 1 → CH1_V5; 2 → TAP0 |
| C149 | RUN filter | 10n (GRM188R71H103KA01D) | 1 → CH1_RUN; 2 → TAP0 |
| C150 |  | 10n (GRM188R71H103KA01D) | 1 → CH1_ENU; 2 → TAP1 |
| C151 | pause timing C | 4.7u (GRM21BR71E475KA73L) | 1 → CH1_TCT; 2 → TAP0 |
| C152 |  | 100n (GRM188R71H104KA93D) | 1 → CH1_V5; 2 → TAP0 |
| C153 | PWH filter | 470n (GRM188R71E474KA12D) | 1 → CH1_PWH; 2 → TAP0 |
| C154 | PWL filter | 470n (GRM188R71E474KA12D) | 1 → CH1_PWL; 2 → TAP0 |
| D101 | bootstrap diode U101 | BAS16W (BAS16W-7-F) | 1 A → CH1_BSU_A; 2 NC → NC; 3 K → CH1_BSTU |
| D102 | bootstrap diode U102 | BAS16W (BAS16W-7-F) | 1 A → CH1_BSL_A; 2 NC → NC; 3 K → CH1_BSTL |
| D103 | FAULT LED (red) | red (SML-D12V1WT86) | 1 K → TAP0; 2 A → CH1_LEDR_A |
| D104 | ACTIVE LED (green) | green (SML-D12M1WT86) | 1 K → TAP0; 2 A → CH1_LEDG_A |
| D105 | pause charge diode | BAS16W (BAS16W-7-F) | 1 A → CH1_PAUSE; 2 NC → NC; 3 K → CH1_PDA |
| JP101 | channel enable jumper | EN (61300211121) | 1 A → TAP1; 2 B → CH1_V5IN |
| JP102 | alarm-opto bypass (fit if channel unused) | EN (61300211121) | 1 A → ALM_S1; 2 B → ALM_S2 |
| JS101 |  | 60900213421 | BOM only |
| JS102 |  | 60900213421 | BOM only |
| Q101 | Q_A: T_H -> X (phase 1) | CSD18543Q3A | 1 S → CH1_X; 2 S → CH1_X; 3 S → CH1_X; 4 G → CH1_GA; 5 D → TAP2 |
| Q102 | Q_B: X -> T_M (phase 2) | CSD18543Q3A | 1 S → TAP1; 2 S → TAP1; 3 S → TAP1; 4 G → CH1_GB; 5 D → CH1_X |
| Q103 | Q_C: T_M -> Y (phase 1) | CSD18543Q3A | 1 S → CH1_Y; 2 S → CH1_Y; 3 S → CH1_Y; 4 G → CH1_GC; 5 D → TAP1 |
| Q104 | Q_D: Y -> T_L (phase 2) | CSD18543Q3A | 1 S → TAP0; 2 S → TAP0; 3 S → TAP0; 4 G → CH1_GD; 5 D → CH1_Y |
| Q105 | red LED driver | MMBT3906 (MMBT3906-7-F) | 1 B → CH1_QFB; 2 E → CH1_V5; 3 C → CH1_LEDQ |
| Q106 | level-shift NMOS | 2N7002 (2N7002-7-F) | 1 G → CH1_RUN; 2 S → TAP0; 3 D → CH1_LSD |
| Q107 | level-shift PNP | MMBT3906 (MMBT3906-7-F) | 1 B → CH1_LSB; 2 E → TAP2; 3 C → CH1_LSC |
| R101 | R_CFX 1/2 | 0.086 (WSL2816R0860FEH) | 1 → CH1_X; 2 → CH1_CFP |
| R102 | R_CFY 1/2 | 0.086 (WSL2816R0860FEH) | 1 → CH1_CFN; 2 → CH1_Y |
| R103 | X precharge | 100k (CRCW0603100KFKEA) | 1 → CH1_X; 2 → TAP2 |
| R104 | Y precharge | 100k (CRCW0603100KFKEA) | 1 → CH1_Y; 2 → TAP1 |
| R105 | gate R Q_A | 4.7 (CRCW06034R70FKEA) | 1 → CH1_OA_U; 2 → CH1_GA |
| R106 | gate R Q_B | 4.7 (CRCW06034R70FKEA) | 1 → CH1_OB_U; 2 → CH1_GB |
| R107 | gate R Q_C | 4.7 (CRCW06034R70FKEA) | 1 → CH1_OA_L; 2 → CH1_GC |
| R108 | gate R Q_D | 4.7 (CRCW06034R70FKEA) | 1 → CH1_OB_L; 2 → CH1_GD |
| R109 | G-S pull-down Q_A | 10k (CRCW060310K0FKEA) | 1 → CH1_GA; 2 → CH1_X |
| R110 | G-S pull-down Q_B | 10k (CRCW060310K0FKEA) | 1 → CH1_GB; 2 → TAP1 |
| R111 | G-S pull-down Q_C | 10k (CRCW060310K0FKEA) | 1 → CH1_GC; 2 → CH1_Y |
| R112 | G-S pull-down Q_D | 10k (CRCW060310K0FKEA) | 1 → CH1_GD; 2 → TAP0 |
| R113 | dead time U101 | 20k (CRCW060320K0FKEA) | 1 → CH1_DTU; 2 → TAP0 |
| R114 | dead time U102 | 20k (CRCW060320K0FKEA) | 1 → CH1_DTL; 2 → TAP0 |
| R115 | timing R | 22.1k (CRCW060322K1FKEA) | 1 → CH1_OSCR; 2 → CH1_OSCRC |
| R116 |  | 909k (CRCW0603909KFKEA) | 1 → CH1_12VL; 2 → CH1_FBL |
| R117 |  | 100k (CRCW0603100KFKEA) | 1 → CH1_FBL; 2 → TAP0 |
| R118 |  | 909k (CRCW0603909KFKEA) | 1 → CH1_12VU; 2 → CH1_FBU |
| R119 |  | 100k (CRCW0603100KFKEA) | 1 → CH1_FBU; 2 → TAP1 |
| R120 | wake string top | 2M (TNPW12062M00BEEA) | 1 → TAP2; 2 → CH1_PON_M1 |
| R121 | wake string top | 2M (TNPW12062M00BEEA) | 1 → CH1_PON_M1; 2 → CH1_PON_M2 |
| R122 | wake string top | 2M (TNPW12062M00BEEA) | 1 → CH1_PON_M2; 2 → CH1_PON_M3 |
| R123 | wake string top | 2M (TNPW12062M00BEEA) | 1 → CH1_PON_M3; 2 → CH1_PON |
| R124 | wake string bottom (pair) | 1.67M (TNPW12061M67BEEA) | 1 → CH1_PON; 2 → TAP0 |
| R125 | wake string bottom (pair) | 1.67M (TNPW12061M67BEEA) | 1 → CH1_PON; 2 → TAP0 |
| R126 | P_LO/P_WH string top | 2M (TNPW12062M00BEEA) | 1 → TAP2; 2 → CH1_PLO_M1 |
| R127 | P_LO/P_WH string top | 2M (TNPW12062M00BEEA) | 1 → CH1_PLO_M1; 2 → CH1_PLO_M2 |
| R128 | P_LO bottom (pair) | 1.58M (TNPW12061M58BEEA) | 1 → CH1_PLO; 2 → TAP0 |
| R129 | P_LO bottom (pair) | 1.58M (TNPW12061M58BEEA) | 1 → CH1_PLO; 2 → TAP0 |
| R130 | P_HI/P_WL string top | 2M (TNPW12062M00BEEA) | 1 → TAP2; 2 → CH1_PHI_M1 |
| R131 | P_HI/P_WL string top | 2M (TNPW12062M00BEEA) | 1 → CH1_PHI_M1; 2 → CH1_PHI_M2 |
| R132 | P_WL bottom (pair) | 1.7M (TNPW12061M70BEEA) | 1 → CH1_PWL; 2 → TAP0 |
| R133 | P_WL bottom (pair) | 1.7M (TNPW12061M70BEEA) | 1 → CH1_PWL; 2 → TAP0 |
| R134 | N string top | 2M (TNPW12062M00BEEA) | 1 → TAP1; 2 → CH1_N_M1 |
| R135 | N string top | 2M (TNPW12062M00BEEA) | 1 → CH1_N_M1; 2 → CH1_N |
| R136 | N bottom (pair) | 1.85M (TNPW12061M85BEEA) | 1 → CH1_N; 2 → TAP0 |
| R137 | N bottom (pair) | 1.85M (TNPW12061M85BEEA) | 1 → CH1_N; 2 → TAP0 |
| R138 | NTC bias | 24.9k (CRCW060324K9FKEA) | 1 → CH1_V5; 2 → CH1_TH |
| R139 | FLT_N pull-up | 100k (CRCW0603100KFKEA) | 1 → CH1_V5; 2 → CH1_FLT_N |
| R140 | NCHG pull-up | 100k (CRCW0603100KFKEA) | 1 → CH1_V5; 2 → CH1_NCHG |
| R141 | RUN pull-down | 100k (CRCW0603100KFKEA) | 1 → CH1_RUN; 2 → TAP0 |
| R142 | Q105 base (10 k) | 10k (CRCW060310K0FKEA) | 1 → CH1_FLT_N; 2 → CH1_QFB |
| R143 | Q105 B-E | 100k (CRCW0603100KFKEA) | 1 → CH1_QFB; 2 → CH1_V5 |
| R144 | LED drive pull-down | 100k (CRCW0603100KFKEA) | 1 → CH1_LEDQ; 2 → TAP0 |
| R145 | red LED current | 750 (CRCW0603750RFKEA) | 1 → CH1_LEDQ; 2 → CH1_LEDR_A |
| R146 | green LED current | 10k (CRCW060310K0FKEA) | 1 → CH1_12VL; 2 → CH1_LEDG_A |
| R147 | level shift 1/2 | 49.9k (CRCW060349K9FKEA) | 1 → CH1_LSD; 2 → CH1_LSM |
| R148 |  | 100k (CRCW0603100KFKEA) | 1 → CH1_LSB; 2 → TAP2 |
| R149 |  | 100k (CRCW0603100KFKEA) | 1 → CH1_LSC; 2 → CH1_ENU |
| R150 |  | 100k (CRCW0603100KFKEA) | 1 → CH1_ENU; 2 → TAP1 |
| R151 | level shift 2/2 | 49.9k (CRCW060349K9FKEA) | 1 → CH1_LSM; 2 → CH1_LSB |
| R152 | R_CFX 2/2 (parallel) | 0.086 (WSL2816R0860FEH) | 1 → CH1_X; 2 → CH1_CFP |
| R153 | R_CFY 2/2 (parallel) | 0.086 (WSL2816R0860FEH) | 1 → CH1_CFN; 2 → CH1_Y |
| R154 | P_LO/P_WH string top | 2M (TNPW12062M00BEEA) | 1 → CH1_PLO_M2; 2 → CH1_PLO_M3 |
| R155 | P_LO/P_WH string top | 1.96M (TNPW12061M96BEEA) | 1 → CH1_PLO_M3; 2 → CH1_PWH |
| R156 | P_HI/P_WL string top | 2M (TNPW12062M00BEEA) | 1 → CH1_PHI_M2; 2 → CH1_PHI_M3 |
| R157 | P_HI/P_WL string top | 2M (TNPW12062M00BEEA) | 1 → CH1_PHI_M3; 2 → CH1_PHI |
| R158 | R_BOOT U101 | 4.7 (CRCW06034R70FKEA) | 1 → CH1_12VU; 2 → CH1_BSU_A |
| R159 | R_BOOT U102 | 4.7 (CRCW06034R70FKEA) | 1 → CH1_12VL; 2 → CH1_BSL_A |
| R160 | PWH/PLO tap 1/2 | 30.9k (CRCW060330K9FKEA) | 1 → CH1_PWH; 2 → CH1_PLO |
| R161 | PWH/PLO tap 2/2 | 30.9k (CRCW060330K9FKEA) | 1 → CH1_PWH; 2 → CH1_PLO |
| R162 | PHI/PWL tap 1/2 | 36.5k (CRCW060336K5FKEA) | 1 → CH1_PHI; 2 → CH1_PWL |
| R163 | PHI/PWL tap 2/2 | 36.5k (CRCW060336K5FKEA) | 1 → CH1_PHI; 2 → CH1_PWL |
| R172 | alarm-opto LED current | 825 (CRCW0603825RFKEA) | 1 → CH1_RUN; 2 → CH1_OKA |
| R173 | oscillator threshold top | 4.99M (CRCW06034M99FKEA) | 1 → CH1_V5; 2 → CH1_TPN |
| R174 | oscillator threshold bottom | 4.99M (CRCW06034M99FKEA) | 1 → CH1_TPN; 2 → TAP0 |
| R175 | oscillator hysteresis | 4.99M (CRCW06034M99FKEA) | 1 → CH1_PAUSE; 2 → CH1_TPN |
| R176 | pause pull-up (from RUN) | 100k (CRCW0603100KFKEA) | 1 → CH1_RUN; 2 → CH1_PAUSE |
| R177 | pause charge (fast) | 249k (CRCW0603249KFKEA) | 1 → CH1_PDA; 2 → CH1_TCT |
| R178 | pause discharge 1/2 | 4.99M (CRCW06034M99FKEA) | 1 → CH1_PAUSE; 2 → CH1_TSM |
| R179 | pause discharge 2/2 | 4.99M (CRCW06034M99FKEA) | 1 → CH1_TSM; 2 → CH1_TCT |
| RT101 | board NTC at R101/Q101 | 470k NTC (NCP15WM474E03RC) | 1 → CH1_TH; 2 → TAP0 |
| U101 | upper half-bridge driver | UCC21520ADWR | 1 INA → CH1_PH1; 2 INB → CH1_PH2; 3 VCCI → CH1_12VL; 4 GND → TAP0; 5 DIS → CH1_PAUSE; 6 DT → CH1_DTU; 7 NC → NC; 8 VCCI → CH1_12VL; 9 VSSB → TAP1; 10 OUTB → CH1_OB_U; 11 VDDB → CH1_12VU; 12 NC → NC; 13 NC → NC; 14 VSSA → CH1_X; 15 OUTA → CH1_OA_U; 16 VDDA → CH1_BSTU |
| U102 | lower half-bridge driver | UCC21520ADWR | 1 INA → CH1_PH1; 2 INB → CH1_PH2; 3 VCCI → CH1_12VL; 4 GND → TAP0; 5 DIS → CH1_PAUSE; 6 DT → CH1_DTL; 7 NC → NC; 8 VCCI → CH1_12VL; 9 VSSB → TAP0; 10 OUTB → CH1_OB_L; 11 VDDB → CH1_12VL; 12 NC → NC; 13 NC → NC; 14 VSSA → CH1_Y; 15 OUTA → CH1_OA_L; 16 VDDA → CH1_BSTL |
| U103 | 100 kHz astable | CD4047BM96 | 1 C → CH1_OSCC; 2 R → CH1_OSCR; 3 RC_COMMON → CH1_OSCRC; 4 ~{ASTABLE} → CH1_12VL; 5 ASTABLE → CH1_12VL; 6 -TRIGGER → CH1_12VL; 7 VSS → TAP0; 8 +TRIGGER → TAP0; 9 EXT_RESET → TAP0; 10 Q → CH1_PH1; 11 ~{Q} → CH1_PH2; 12 RETRIGGER → TAP0; 13 OSC_OUT → NC; 14 VDD → CH1_12VL |
| U104 | 12V_L gated LDO | TPS7A1601DGNR | 1 OUT → CH1_12VL; 2 FB → CH1_FBL; 3 PG → NC; 4 GND → TAP0; 5 EN → CH1_RUN; 6 NC → NC; 7 DELAY → NC; 8 IN → TAP1; 9 PAD → TAP0 |
| U105 | 12V_U gated LDO | TPS7A1601DGNR | 1 OUT → CH1_12VU; 2 FB → CH1_FBU; 3 PG → NC; 4 GND → TAP1; 5 EN → CH1_ENU; 6 NC → NC; 7 DELAY → NC; 8 IN → TAP2; 9 PAD → TAP1 |
| U106 | V5 always-on LDO | TPS70950DBVR | 1 IN → CH1_V5IN; 2 GND → TAP0; 3 EN → CH1_V5EN; 4 NC → NC; 5 OUT → CH1_V5 |
| U107 | 2.5 V reference | REF35250 (REF35250QDBVR) | 1 GND → TAP0; 2 GND → TAP0; 3 EN → CH1_V5; 4 VIN → CH1_V5; 5 NR → NC; 6 VREF → CH1_VREF |
| U108 | comparators: A wake, B/C lockout, D thermal | TLV7044PWR | 1 OUTA → CH1_NCHG; 2 INA- → CH1_PON; 3 INA+ → CH1_VREF; 4 VCC → CH1_V5; 5 INB+ → CH1_N; 6 INB- → CH1_PLO; 7 OUTB → CH1_FLT_N; 8 OUTC → CH1_FLT_N; 9 INC- → CH1_N; 10 INC+ → CH1_PHI; 11 VEE → TAP0; 12 IND+ → CH1_TH; 13 IND- → CH1_VREF; 14 OUTD → CH1_FLT_N |
| U109 | dual NOR: FLT = !FLT_N; RUN = NOR(NCHG, FLT) | 74LVC2G02 (SN74LVC2G02DCTR) | 1 1A → CH1_FLT_N; 2 1B → CH1_FLT_N; 3 2Y → CH1_RUN; 4 GND → TAP0; 5 2A → CH1_NCHG; 6 2B → CH1_FLT; 7 1Y → CH1_FLT; 8 VCC → CH1_V5 |
| U110 | alarm opto (series chain, LED on = healthy) | SFH617A-3 (SFH617A-3X017T) | 1 A → CH1_OKA; 2 K → TAP0; 3 E → ALM_S2; 4 C → ALM_S1 |
| U111 | comparators: B/C imbalance warning, D tap-check pause oscillator, A spare | TLV7044PWR | 1 OUTA → NC; 2 INA- → CH1_VREF; 3 INA+ → TAP0; 4 VCC → CH1_V5; 5 INB+ → CH1_N; 6 INB- → CH1_PWH; 7 OUTB → CH1_OKA; 8 OUTC → CH1_OKA; 9 INC- → CH1_N; 10 INC+ → CH1_PWL; 11 VEE → TAP0; 12 IND+ → CH1_TPN; 13 IND- → CH1_TCT; 14 OUTD → CH1_PAUSE |

### 3.6 Net membership

The net-by-net member lists are generated: `out/netlist.json` (`nets`) after `kaesynth build`. The
KiCad round trip checks that the schematic matches it pin for pin. NC pins per channel:
U101.7, .12, .13; U102.7, .12, .13; U103.13; U104.3, .6, .7; U105.3, .6, .7; U106.4; U107.5; U111.1 (spare
comparator A); D101.2; D102.2; D105.2.

Per-channel part totals: 151 placed (Q 7, U 11, D 5, R 71, C 54, RT 1, JP 2) plus 2 shunts (JSk01, JSk02).
Three channels give 453; adding J1, J2, D1, F1–F5 and H1–H4 gives **465 placed parts**. BOM-only items:
6 shunts, 5 fuse holders XH1–XH5 (pads in the F footprint) and the harness (§5).

## 4. Channels 2 and 3: substitution rule

Copy §3 with these substitutions, applied to every row:

| Item | Channel 1 | Channel k |
|---|---|---|
| Refdes | Xnnn with hundreds digit 1 (Q101, R151, RT101, JP101) | hundreds digit k (Q201…, Q301…) |
| Channel nets | CH1_<name> | CHk_<name> |
| T_L | TAP0 | TAP(k−1): CH2 → TAP1, CH3 → TAP2 |
| T_M | TAP1 | TAPk: CH2 → TAP2, CH3 → TAP3 |
| T_H | TAP2 | TAP(k+1): CH2 → TAP3, CH3 → TAP4 |
| Alarm chain | U110 C → ALM_S1, E → ALM_S2 | U210: ALM_S2 → ALM_S3; U310: ALM_S3 → ALM_E (outputs in series) |
| Silkscreen | "CH1 ACT / FLT / EN(N≥2)" | "CH2 … EN(N≥3)", "CH3 … EN(N=4)" |

So for channel 2:

- Q201.5-8 → TAP3 and Q204.1-3 → TAP1.
- U201.9 → TAP2, U202.4/.9 → TAP1, JP201.1 → TAP2, R220.1 → TAP3, R234.1 → TAP2.
- U210.2 → TAP1.

Voltage ratings are identical for every channel because each channel sees only its own two
batteries. Only the "V to T0" column rises by (k−1) × Vb, which matters for the spacing rules in
DESIGN.md §6.

**Jumper setting by battery count.**

| N | JP101 | JP201 | JP301 | JP102 | JP202 | JP302 | Harness positions wired (others bridged in the plug, §5) |
|---|---|---|---|---|---|---|---|
| 2 | fit | open | open | open | fit | fit | 1–3 |
| 3 | fit | fit | open | open | open | fit | 1–4 |
| 4 | fit | fit | fit | open | open | open | 1–5 |

JPk01 enables channel k; JPk02 bridges the alarm opto of an unused channel so the series alarm chain can
close.

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
| SN74LVC2G02DCTR | TI SCES194N (May 2019) §5 Pin Functions [P] |
| Keystone 3576 holder (F footprint) | Keystone catalog M65 p.45 drawing [P] |
| SFH617A-3X017T | Vishay 83740 Rev 2.5 p. 1 [P] |
| 2N7002-7-F | Diodes DS11303 Rev 40-2 p. 1 [P] |
| MMBT3906-7-F | Diodes DS30059 Rev 23-2 p. 1 [P] |
| BAS16W-7-F | KiCad Diode:BAS16W (1 A, 2 NC, 3 K) [S]; SOT-23 BAS16 (Zetex) read [P] |
| Two-terminal parts (R, C, NTC, fuse) | non-polar; C_Polarized pad 1 = + (KiCad CP_Elec) [S]; LED pin 1 = K (KiCad Device:LED) [S] |
| Phoenix MSTB/MSTBA | positions numbered 1…n along the header; datasheet not reachable [S] |
