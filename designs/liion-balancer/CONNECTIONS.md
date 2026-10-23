# liion-balancer: connections (netlist)

Companion to [DESIGN.md](DESIGN.md). The source of truth is [`design.py`](design.py); the build
writes every pin of every part to `out/netlist.json` (and checks that the KiCad schematic reads back
pin-for-pin identical). This file keeps the net table, the naming rules for the 17 taps and 16
channels, the pinout of every non-repeated part, and the harness.

**Conventions**

- `pin (datasheet name) → NET`. NC = intentionally open, with the reason recorded in `design.py`.
- Pin evidence: [P] read in the datasheet (cited in `parts.py` `source=`), [S] secondary or KiCad
  symbol, [I] inferred.
- Net names are global except a channel's private nets and a few block-local ones, which KiCad shows
  as `/<block>/<net>` (e.g. `/ch3/SW_3`, `/psu/BUCK_SW`).
- k = 1…16 is the channel (cell), kk its two-digit form; t = 0…16 is the tap, tt its two-digit form.
- Two-pin parts: `Device:R/C/L/Fuse/Thermistor_NTC` non-polar; `Device:D`, `D_Zener`, `LED`: 1 = K, 2 = A.
- **N < 16:** the board netlist does not change; plug positions N+1…17 are bridged (§5), so
  TAP(N)…TAP16 are one node.

## 1. Net table

Voltages are worst-case normal operation relative to TAP0 unless noted (domain model: DESIGN.md §6.2).

| Net | Domain | Voltage | Current | Kind |
|---|---|---|---|---|
| CELLTERMt (off-board) | as TAPt | as TAPt | 2.6 A; kA fault | cell terminal, ring HTt |
| TAPt_IN, t = 0…16 | BAT0 / Ct | 0…t·4.2 V (≤ 67.2 V) | 2.6 A avg; 34–67 A until a fuse opens | power, harness wire through J1 |
| TAPt | BAT0 / Ct | as TAPt_IN | 2.6 A (1.5 mm track) | power after F1tt; TAP0 = stack −, TAP16 = stack + |
| CS_t | BAT0 / SNSt / STACK | TAPt ± 10 mV | ≤ 1 µA (100 µA open-wire test) | sense, ADBMS1818 C inputs |
| S_k / DIN_k | Ck | TAP(k−1)…TAPk | 3 µA | balance enable, active low; DIN_k is S_k behind R5kk 10 kΩ |
| MODE_k | SNSk / STACK | TAPk − 10 mV…TAPk | < 1 µA | LT8584 MODE via 10 kΩ |
| SW_k | SWk | TAP(k−1) − 0.7 V…+38.5 V; 21.4 V flat top | 3.2 A rms, 6.8 A pk | switching (0.6 mm to every other net) |
| SNB_k | SWk | TAPk + 15…34 V | 0.05 A avg, 6.8 A pk | RCD clamp node |
| OUT_k, DCH_k | Ck | within cell k | < 1 mA | LT8584 OUT; DCHRG (high = enable) |
| SEC_k | RET | −18…68.7 V | 0.4 A rms, 1.7 A pk | secondary switching node |
| FLYBUS | RET | stack + 0.5 V (≤ 67.7 V); ≤ 79 V if the return opens (U9 trip), 183 V if U9 also fails (LT8584 latch) | 1.6 A | flyback return bus |
| LEDA_k | STRk | ≤ 1.4 V above LEDA_(k−1) | 1.5 mA | opto LED string node |
| STR_Q / STR_D | RET / STACK | 2.4–67 V / STK_F − 1.3 V | 1.5 mA (6.2 mA Q1-short fault) | string bottom / top |
| STK_F | STACK | TAP16 − 0.05 V | 10 mA (0.66 A fault) | fused stack supply |
| VPLUS, BUCK_PRE, BUCK_IN | STACK | TAP16 − 0.3 / 1.3 / 2.5 V | 1.4 / 12 / 12 mA | ADBMS1818 V+, buck input |
| BUCK_SW / BUCK_BST | RET / BOOT | −0.7…67.2 V / SW + 5 V | 0.26 A pk | buck switch node, bootstrap |
| BUCK_EN, BUCK_RON, BUCK_FB, BUCK_RAMP | CTRL | ≤ 4.1, ≤ 5, 1.2, 5 V | µA | buck control |
| 5V_SYS / +3V3 | CTRL | 4.99 V (≤ 5.15) / 3.3 V (≤ 3.37) | 60 / 25 mA | power |
| GND_B | BAT0 | 0 (= TAP0 at NT1) | 60 mA | controller ground |
| VREF1, VREF2, NTC1–3, IBIAS, IPB, IMB | CTRL | ≤ 3.3 V; IPB/IMB ≤ 5.15 V | ≤ 2.5 mA | AFE analog |
| SPI_CS/SCK/MOSI/MISO, ADBMS_WDT, PGOOD, BAL_EN, MCU_TX/RX, FLT_DRV, NRST, SWDIO, SWCLK, LEDx | CTRL | 0–3.37 V | ≤ 5 mA | logic |
| ISO_VCC1 | CTRL | 3.3 V from PB0 | 4 mA | isolator side 1 supply |
| FLT_LED | CTRL | ≤ 1.5 V (LED-clamped) | 5.3 mA | PhotoMOS LED |
| FLY_SNS | CTRL | ≤ 3.10 V | 6.5 µA | FLYBUS × 470 k / 10.47 M to PA0 |
| Q1_B, EN_MCU | CTRL | ≤ 0.8 V / ≤ 3.37 V | 0.33 mA | string-sink base; BAL_EN through R21 before U8 |
| TRT1–3 | SNS15 | TAP15 + 0…12 V | ≤ 25 mA in a trip | top trip chain (FLYBUS → U9 → TAP15) |
| TRB1–3, Q2_B | CTRL / TRB | 0…4.4 V | ≤ 20 mA in a trip | bottom trip chain (TAP1 → U10 → Q2) |
| BMS_IN, BMS1, BMS2, BMS_N | BMS | ±30 V; BMS2 ≤ 1.5 V | ≤ 16 mA | BMS-OK input (J5) |
| GND_ISO, VIO_ISO, TXD_ISO, RXD_ISO, ISO_OUTB, ISO_INA | USER | 0–5.5 V (host) | ≤ 5 mA | isolated UART |
| FLT_A, FLT_B | FAULT | ±30 V user circuit | ≤ 50 mA | dry contact, closes on fault |

## 2. Taps (blocks `tapin`, `tap0`…`tap16`)

| Part | Rule |
|---|---|
| J1 Phoenix MSTBA 2,5/17-G-5,08 (custom 17-pos footprint) | pin t+1 → TAPt_IN; pin 1 = B− cell terminal (never P−), pin 17 = B+ |
| F1tt 0154005.DR (OMNI-BLOK, Nano2 5 A) | 1 → TAPt_IN; 2 → TAPt |
| R3tt 100 Ω 0603 | 1 → TAPt (Kelvin at pad F1tt.2); 2 → CS_t |
| C7tt 10 nF 50 V | 1 → CS_t; 2 → CS_(t−1); for t = 0: 2 → GND_B |
| NT1 `Device:NetTie_2` on pad F100.2 | 1 → TAP0; 2 → GND_B |
| U1 C pin for tap t | pin 38 − 2t ← CS_t; C17 (pin 4) and C18 (pin 2) ← CS_16 |
| U1 S pin for channel k | pin 39 − 2k → S_k; S17 (5), S18 (3) NC |

## 3. Channel k (blocks `ch1`…`ch16`)

Refdes U1kk, T1kk, U2kk, D1kk, D2kk, D3kk, C1kk…C6kk, R1kk, R2kk, R4kk, R5kk (e.g. k = 7: U107, T107, …).
Local positive TAPk, local reference TAP(k−1). k = 1: U201.2 → STR_Q. k = 16: LEDA_16 is fed by R24.

| Part | Pins and nets |
|---|---|
| U1kk LT8584EFE#PBF (generated symbol; TSSOP-16 EP) [P p.2, p.9] | 1, 2, 3, 4 GND, 6 RTMR, 17 EP → TAP(k−1); 5 MODE → MODE_k; 7 DIN ← DIN_k; 8 OUT → OUT_k; 9 VIN, 10 VCELL, 11 VSNS → TAPk; 12 DCHRG → DCH_k; 13–16 SW → SW_k |
| T1kk Coilcraft NA5743-ALD (drawn footprint; pin 1 top left, 1–4 left, 8–5 right) [P] | 1, 2 (primary dots) → TAPk; 3, 4 → SW_k; 5 → SEC_k; 8 (secondary dot) → TAP0; 6, 7 NC (no winding) |
| D1kk ES1G | K → FLYBUS; A → SEC_k |
| D2kk ES1G | K → SNB_k; A → SW_k |
| D3kk SMA6T6V7AY (`D_Zener`) | K → TAPk; A → TAP(k−1) |
| C1kk, C2kk 100 µF 6.3 V X6S 1210 | TAPk ↔ TAP(k−1) (C1 at the tap entry, C2 at T1kk.1/2 and U1kk.17) |
| C3kk 1 µF / C4kk 47 nF | TAPk ↔ TAP(k−1) at U1kk.9 / OUT_k ↔ TAP(k−1) |
| C5kk 22 nF 100 V; R1kk 4.99 kΩ 2010 | SNB_k ↔ TAPk (both) |
| C6kk 2.2 µF 100 V 1210 | FLYBUS ↔ TAP0 (at D1kk.1 / T1kk.8) |
| R2kk 33 kΩ; R4kk 10 kΩ | DCH_k ↔ TAP(k−1); TAPk ↔ MODE_k |
| R5kk 10 kΩ 0603 (at U1's S pin) | 1 → S_k; 2 → DIN_k |
| U2kk TLP293 [P §4] | 1 A ← LEDA_k; 2 K → LEDA_(k−1) (STR_Q for k = 1); 3 E → DCH_k; 4 C ← TAPk |

## 4. Non-repeated parts

**U1 ADBMS1818ASWZ** (2-unit generated symbol; LQFP-64 EP) [P Rev A Fig. 3, Table 14]: 1 V+ →
VPLUS; C/S pins per §2; 39–42 GPIO1–4 → NTC1–4; 43–47 GPIO5–9 → GND_B (unused, held low [I]);
48 VREG → 5V_SYS; 49 DRIVE NC; 50 VREF2; 51 VREF1; 52 DTEN → GND_B (2 s watchdog); 53 SDI ← SPI_MOSI;
54 SDO → SPI_MISO; 55 ISOMD → GND_B (SPI mode); 56 WDT → ADBMS_WDT; 57 IBIAS and 58 ICMP → IBIAS;
59, 60, 65 V− → GND_B; 61 CSB ← SPI_CS; 62 SCK ← SPI_SCK; 63 IMB; 64 IPB.

| AFE | Part | Pin 1 | Pin 2 |
|---|---|---|---|
| R1 | 100 Ω 0805 | STK_F | VPLUS |
| C1 | 100 nF 100 V | VPLUS | GND_B |
| C2 | 1 µF 16 V | 5V_SYS (U1.48) | GND_B |
| C3, C4 | 1 µF 10 V | VREF1, VREF2 | GND_B |
| R2 / R3 | 20 kΩ / 100 Ω | IBIAS / IPB | GND_B / IMB |
| R4 / R5 | 4.99 kΩ / 1 MΩ | SPI_MISO / ADBMS_WDT | +3V3 |
| R6, R7, R8, R29 | 10.0 kΩ 0.1 % | VREF2 | NTC1–4 |
| TH1–TH4 | NCP18XH103F03RB (at U103, U107, U110, U114) | NTC1–4 | GND_B |
| C5, C6, C7, C22 | 100 nF | NTC1–4 | GND_B |

**Return (`ret`).** D1 V8P10 (`D_Schottky_AAK`): 1, 2 A ← FLYBUS; 3 K (tab) → TAP16. (D2, the former FLYBUS clamp, is
removed.) R19 10 MΩ 1206: FLYBUS–FLY_SNS. R20 470 kΩ and C19 10 nF: FLY_SNS–GND_B.
TP1 → FLYBUS.

**Supply (`psu`).** F1 0451.125MRL: TAP16 (at F116.2) → STK_F. D3 ES1G: A STK_F, K BUCK_PRE. R9
100 Ω 2512: BUCK_PRE–BUCK_IN. U3 LM5164DDA [P Table 4-1]: 1 GND, 9 EP → GND_B; 2 VIN ← BUCK_IN;
3 EN/UVLO; 4 RON; 5 FB; 6 PGOOD; 7 BST; 8 SW. C8 2.2 µF 100 V and C9 100 nF 100 V: BUCK_IN–GND_B.
R10 10 MΩ 1206 BUCK_IN–BUCK_EN; R11 620 kΩ BUCK_EN–GND_B; R12 49.9 kΩ RON–GND_B; C10 2.2 nF BST–SW;
L1 47 µH SW–5V_SYS; C11 22 µF 5V_SYS–GND_B; R13 316 kΩ 5V_SYS–FB; R14 100 kΩ FB–GND_B; R15 470 kΩ
SW–RAMP; C12 1 nF C0G RAMP–5V_SYS; C13 220 pF C0G RAMP–FB; R16 100 kΩ PGOOD–+3V3. U4 MCP1700 [P
Table 3-1]: 1 GND, 2 VO → +3V3, 3 VI ← 5V_SYS; C14 1 µF 16 V and C15 1 µF at its pins. TP6 → STK_F.

**MCU (`mcu`), U2 STM32G031K8T6** [P DS12992 Fig. 5, Tables 12/13]:

| Pin | Net | Pin | Net |
|---|---|---|---|
| 1 PB9 | LEDR | 13 PA6 SPI1_MISO | SPI_MISO |
| 4 VDD | +3V3 (C16 100 nF, C17 4.7 µF) | 14 PA7 SPI1_MOSI | SPI_MOSI |
| 5 VSS | GND_B | 15 PB0 | ISO_VCC1 |
| 6 PF2-NRST | NRST (C18 100 nF) | 16 PB1 | FLT_DRV |
| 7 PA0 ADC_IN0 | FLY_SNS (analog watchdog) | 17 PB2 | ADBMS_WDT |
| 8 PA1 | BAL_EN | 18 PA8 | PGOOD |
| 9 PA2 USART2_TX | MCU_TX | 24 PA13 | SWDIO |
| 10 PA3 USART2_RX | MCU_RX | 25 PA14 | SWCLK |
| 11 PA4 | SPI_CS | 32 PB8 | LEDG |
| 12 PA5 SPI1_SCK | SPI_SCK | 2, 3, 20, 22, 23, 26–31 | NC (analog mode); 19, 21 NC on G031 |

R17/R18 1 kΩ LEDG→LEDG_A / LEDR→LEDR_A; D5 green / D6 red: K → GND_B, A ← LEDx_A. J3 Tag-Connect
TC2030-NL pads: 1 +3V3, 2 SWDIO, 3 NRST, 4 SWCLK, 5 GND_B, 6 NC (no SWO on M0+); battery potential,
program only with an isolated debugger. TP2 5V_SYS, TP3 +3V3, TP4 GND_B.

**Enable string (`en`).** STK_F → D4 (ES1G, A STK_F, K STR_D) → R24 4.7 kΩ 2010 → LEDA_16 → U216 …
U201 → STR_Q → Q1 MMBT5551 (1 B ← Q1_B, 2 E → Q1_E, 3 C ← STR_Q) → R23 1.6 kΩ 0805 → GND_B.
R21 10 kΩ BAL_EN–EN_MCU; U8 (iso sheet) EN_MCU–Q1_B; R22 100 kΩ Q1_B–GND_B; TP5 → STR_Q.

**Hardware trips (`en`).** Top: FLYBUS → D8 ES1G (A FLYBUS, K TRT1) → D9 BZX84-B3V9 (3 K TRT1, 1 A TRT2;
pin 2 n.c.) → R30 220 Ω → TRT3 → U9 TLP293 (1 A TRT3, 2 K TAP15, 3 E GND_B, 4 C Q1_B); R36 10 kΩ TRT3–TAP15.
Bottom: TAP1 → D10 BZX84-B3V9 (K TAP1, A TRB1) → R31 220 Ω → TRB2 → U10 TLP293 (1 A TRB2, 2 K TRB3,
3 E GND_B, 4 C Q1_B); R37 10 kΩ TRB2–TRB3; Q2 MMBT5551 (1 B Q2_B, 2 E GND_B, 3 C TRB3); R32 10 kΩ
BAL_EN–Q2_B; R33 100 kΩ Q2_B–GND_B.

**Isolated port (`iso`).**

| Part | Pins |
|---|---|
| U5 ISO7721DWV [P Table 5-1] | 1 VCC1 ← ISO_VCC1; 2 OUTA → MCU_RX; 3 INB ← MCU_TX; 4 GND1 → GND_B; 5 GND2 → GND_ISO; 6 OUTB → ISO_OUTB; 7 INA ← ISO_INA; 8 VCC2 ← VIO_ISO |
| C20 / C21 100 nF | ISO_VCC1–GND_B / VIO_ISO–GND_ISO |
| R25 / R26 1 kΩ | ISO_OUTB–TXD_ISO / RXD_ISO–ISO_INA |
| R27 100 kΩ; R28 390 Ω | ISO_INA–VIO_ISO (idle high); FLT_DRV–FLT_LED |
| U7 TPD4E05U06DQA [P Table 4-2] | 1 D1+ → VIO_ISO; 2 D1− → TXD_ISO; 4 D2+ → RXD_ISO; 3, 8 GND → GND_ISO; 5 D2− NC (spare); 6, 7, 9, 10 NC |
| U6 AQY210EHAX (`Relay_SolidState:AQY280EH`, SMDIP-4) [P/S] | 1 LED A ← FLT_LED; 2 LED K → GND_B; 3 → FLT_A; 4 → FLT_B |
| D7 SMBJ40CA (`D_TVS`) | A1 FLT_A; A2 FLT_B |
| J2 Phoenix MC 1,5/4-G-3,81 | 1 GND_ISO, 2 VIO_ISO (host 2.25–5.5 V), 3 TXD_ISO (board → host), 4 RXD_ISO |
| J4 Phoenix MC 1,5/2-G-3,81 | 1 FLT_A, 2 FLT_B (closes on fault) |
| J5 Phoenix MC 1,5/2-G-3,81 | 1 BMS_IN (+, 9–30 V), 2 BMS_N |
| D12 SMBJ40CA; R34 1.8 kΩ 2512; D11 ES1G; R35 10 kΩ | D12 BMS_IN–BMS_N; R34 BMS_IN–BMS1; D11 A BMS1, K BMS2; R35 BMS2–BMS_N |
| U8 AQY210EHAX | 1 LED A ← BMS2; 2 LED K → BMS_N; 3 → EN_MCU; 4 → Q1_B (in series with the MCU's BAL_EN drive) |

**Mechanical.** H1–H6 M4 NPTH (`MountingHole_4.3mm_M4`), 3.0 mm copper-free ring.

## 5. Harness (block `harness`, off-board)

Per tap t = 0…16: ring HTt (Panduit PV18-14R-MY, ¼"/M6) on the cell terminal (net CELLTERMt: B− for
t = 0, cell t + otherwise) → 50 mm 18 AWG → inline fuse HFt (Littelfuse 0324007.HXP, 3AB 7 A,
butt-spliced, sealed in adhesive dual-wall heat-shrink): pin 1 CELLTERMt, pin 2 TAPt_IN → UL 1015
18 AWG ≤ 1 m → plug HP1 (MSTB 2,5/17-ST-5,08, 1757161) position t+1, which mates J1 pin t+1.
Wires in tap order, laced every 100 mm, labelled 0…16 (0 black, 16 red).

**N = 13…15:** build N+1 chains (wire N to position N+1) and bridge positions N+1…17 with Phoenix
EBP 2-5 (1733169) insertion bridges (16 − N bridges); set N in firmware (checked at boot).
**Before plugging in:** each adjacent pair reads 2.5–4.2 V rising, bridged positions 0 V, and
pos 17 − pos 1 equals the stack voltage.

## 6. Part count

| Group | Parts |
|---|---|
| Channels 16 × 16 | 256 |
| Taps 17 × 3 + J1 + NT1 | 53 |
| AFE (U1, R1–R8, R29, C1–C7, C22, TH1–TH4) | 22 |
| PSU (21 parts + TP6) | 22 |
| MCU (U2, C16–C18, R17, R18, D5, D6, J3, TP2–TP4) | 12 |
| RET (D1, R19, R20, C19, TP1) | 5 |
| EN (Q1, D4, R21–R24, TP5; trips D8–D10, Q2, R30–R33, R36, R37, U9, U10) | 19 |
| ISO (U5, U6, U7, D7, C20, C21, R25–R28, J2, J4; BMS-OK U8, J5, D11, D12, R34, R35) | 18 |
| Holes H1–H6 | 6 |
| **On the board** | **413** (407 electrical + 6 holes) |
| Harness: HT0–HT16, HF0–HF16, HP1 (+ wire, splices, heat-shrink, 0–3 bridges) | 35 |
