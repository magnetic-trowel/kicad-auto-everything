# liion-balancer: connections (netlist)

Companion to [DESIGN.md](DESIGN.md). Every pin of every placed part is listed, plus the off-board
harness.

**Conventions**

- **Pin entries.** Each pin entry reads `pin number (datasheet name) → NET`. `NC` means intentionally unconnected (no net).
- **Pin evidence tags.**
  - [P]: pin numbering read in the datasheet at the cited page or figure.
  - [S]: from a secondary source, a KiCad library symbol or a common package convention.
  - [I]: inferred.
  - [unverified]: not confirmed.
- **Net names are global.** A net with the same name in two blocks is the same net.
- **Indexed parts and nets.** Channels repeat, so refdes and nets use indices:
  - k = 1…16 is the channel (cell) index. kk is k written as two digits (01…16).
  - t = 0…16 is the tap index. tt is t written as two digits (00…16).
  - Rules are given in §3.1 and §2.1.
- **Two-pin passives.** Pin 1 / pin 2 follow the KiCad symbol: `Device:R`, `Device:C`, `Device:L`, `Device:Fuse`, `Device:Thermistor_NTC` are non-polar. `Device:D`, `Device:D_Zener` and `Device:LED` have 1 = K and 2 = A.
- **Variant for N < 16 series cells.** The board netlist does not change. Positions N+1…17 of the harness plug are bridged (§11), so nets TAP(N)…TAP16 are one node.

## 1. Net table

| Net | Domain | Voltage range (to TAP0 unless noted) | Max current | Kind |
|---|---|---|---|---|
| TAPt_IN, t = 0…16 | t = 0: BAT0. t ≥ 1: top of CELLt | t·2.5 … t·4.2 V, ≤ 60 V (TAP0_IN = 0) | 2.6 A avg; 34–67 A fault until a fuse opens | power (tap, before the board fuse) |
| TAPt, t = 0…16 | as TAPt_IN | as TAPt_IN | 2.6 A avg | power (tap, after the fuse). TAP0 is also the stack − and flyback return; TAP16 is the stack + |
| CS_t, t = 0…16 | as TAPt | as TAPt (filtered) | ≤ 1 µA (100 µA during an open-wire test) | sense (ADBMS1818 C input) |
| S_k, k = 1…16 | CELLk | TAP(k−1) (low = enable) or TAPk (high) | 3 µA | signal (balance enable, active low) |
| MODE_k | CELLk | = TAPk through 10 kΩ | < 1 µA | config (LT8584 simple mode) |
| SW_k | CELLk (switching) | TAP(k−1)+0.2 V (on) … TAP(k−1)+38 V pk (leakage spike); flat top +19.6 V | 6.8 A pk; ≈ 3.2 A rms | switching node |
| SNB_k | CELLk | TAPk + 15…34 V | ≈ 0.05 A avg; 6.8 A pk | snubber clamp node |
| OUT_k | CELLk | TAPk − 0.6…1.4 V | < 1 mA | analog (LT8584 OUT compensation) |
| DCH_k | CELLk | TAP(k−1) (off) … TAPk − 0.1 V (on) | 130 µA | signal (second enable) |
| SEC_k | STACK (switching) | −4·V_IN … FLYBUS + 1 V | 1.7 A pk, 0.2 A avg | switching node (secondary) |
| LEDA_k, k = 1…16 | STACK | 30–57 V | 1.6 mA | bias (opto LED string node) |
| FLYBUS | STACK | 32.5–60.5 V; ≤ 90 V if the return opens (D2 clamp) | 1.6 A avg | power (flyback return bus) |
| STK_F | STACK | = TAP16 (32.5–60 V) | 10 mA (0.57 A fault, F1 clears) | power (fused stack supply) |
| VPLUS | STACK | STK_F − 0.14 V | 1.4 mA | power (ADBMS1818 V+) |
| BUCK_PRE | STACK | STK_F − 0.9 V | 10 mA | power |
| BUCK_IN | STACK | 31–60 V | 10 mA | power (buck input) |
| BUCK_EN | CTRL (to GND_B) | 0–3.6 V | 12 µA | signal (UVLO divider) |
| BUCK_RON | CTRL | ≈ 0–1 V | µA | analog |
| BUCK_FB | CTRL | 1.2 V | µA | analog (feedback) |
| BUCK_RAMP | CTRL | ≈ 5 V ± 40 mV ramp | µA | analog (ripple injection) |
| BUCK_SW | STACK (switching) | −0.7 … 60.5 V | 0.26 A pk | switching node |
| BUCK_BST | STACK | BUCK_SW + 5 V | mA | gate-drive bootstrap |
| 5V_SYS | CTRL | 4.9–5.1 V | 60 mA (35 mA pk ADBMS1818) | power |
| +3V3 | CTRL | 3.25–3.35 V | 25 mA | power |
| GND_B | CTRL/BAT0 | 0 V (joined to TAP0 at NT1) | 60 mA | ground (controller) |
| VREF1 | CTRL | ≈ 3.2 V [I]; no DC load | 0 | reference |
| VREF2 | CTRL | 3.000 V | 0.8 mA | reference (NTC bias) |
| NTC1, NTC2, NTC3 | CTRL | 0.3–2.5 V | 0.26 mA | sense |
| IBIAS | CTRL | 2.0 V when the port is active | 0.1 mA | bias (isoSPI port B) |
| IPB, IMB | CTRL | 0–5 V | 30 mA pk | isoSPI port B (terminated, unused) |
| SPI_CS, SPI_SCK, SPI_MOSI | CTRL | 0–3.3 V | 1 mA | signal (MCU → ADBMS1818) |
| SPI_MISO | CTRL | 0–3.3 V (open drain, 4.99 kΩ pull-up) | 0.7 mA | signal |
| ADBMS_WDT | CTRL | 0–3.3 V (open drain) | 3 µA | signal |
| PGOOD | CTRL | 0–3.3 V (open drain) | 33 µA | signal |
| FLY_SNS | CTRL | 0–2.9 V (≤ 4.3 V in a clamp fault, MCU-clamped) | 7 µA | sense |
| BAL_EN | CTRL | 0–3.3 V | 0.3 mA | signal (global enable) |
| Q1_B | CTRL | 0–0.7 V | 0.3 mA | bias |
| Q1_E | CTRL | 0–2.5 V | 1.6 mA | bias |
| STR_Q | STACK | 2.4–40 V | 1.6 mA (6.2 mA in a Q1-short fault) | bias (string bottom) |
| STR_D | STACK | STK_F − 0.9 V | 1.6 mA | bias (string top) |
| MCU_TX, MCU_RX | CTRL | 0–3.3 V | 1 mA | signal (UART) |
| ISO_VCC1 | CTRL | 3.1–3.3 V | 4 mA | power (isolator side 1, switched by GPIO) |
| FLT_DRV, FLT_LED | CTRL | 0–3.3 V | 5.3 mA | signal (PhotoMOS LED) |
| NRST, SWDIO, SWCLK | CTRL | 0–3.3 V | 1 mA | signal (debug) |
| LEDG, LEDG_A, LEDR, LEDR_A | CTRL | 0–3.3 V | 1.3 mA | signal (indicator) |
| GND_ISO | USER | 0 (floating to battery, ≤ 250 V rms assumed) | 5 mA | ground (user) |
| VIO_ISO | USER | 2.25–5.5 V vs GND_ISO (from host) | 4 mA | power (user, from host) |
| ISO_OUTB, TXD_ISO | USER | 0–V_IO | 1 mA | signal (board → host) |
| RXD_ISO, ISO_INA | USER | 0–V_IO | 1 mA | signal (host → board) |
| FLT_A, FLT_B | FAULT | ≤ 30 V DC user circuit (part rated 350 V) | ≤ 50 mA | dry contact (closes on fault) |

## 2. Block B2 TAPIN: harness header, tap fuses, monitor filters

### 2.1 Naming rule for tap t (t = 0…16, tt = 00…16)

| Part | Pins and nets |
|---|---|
| J1 pin (t+1) | net `TAPt_IN` |
| F1tt | 1 → TAPt_IN; 2 → TAPt |
| R3tt | 1 → TAPt, Kelvin at pad F1tt.2; 2 → CS_t |
| C7tt, t ≥ 1 | 1 → CS_t; 2 → CS_(t−1) |
| C700 | 1 → CS_0; 2 → GND_B |
| U1 C pin for tap t | pin (38 − 2t) ← CS_t |
| U1 S pin for channel k (k ≥ 1) | pin (39 − 2k) → S_k |

### J1: Phoenix Contact MSTBA 2,5/17-G-5,08 (1757394), 17-pos header, 5.08 mm, THT, right angle

- Symbol `Connector_Generic:Conn_01x17`.
- Footprint **custom**: the KiCad `Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_16-G-5,08_1x16_P5.08mm_Horizontal` extended by one position at the same pitch.
- Positions are numbered 1…17 along the header [S].

| Pin | Net | Harness wire (§11) |
|---|---|---|
| 1 | TAP0_IN | HW0, from B− (most negative cell terminal) |
| 2 | TAP1_IN | HW1, cell 1 + |
| 3 | TAP2_IN | HW2, cell 2 + |
| 4 | TAP3_IN | HW3, cell 3 + |
| 5 | TAP4_IN | HW4, cell 4 + |
| 6 | TAP5_IN | HW5, cell 5 + |
| 7 | TAP6_IN | HW6, cell 6 + |
| 8 | TAP7_IN | HW7, cell 7 + |
| 9 | TAP8_IN | HW8, cell 8 + |
| 10 | TAP9_IN | HW9, cell 9 + |
| 11 | TAP10_IN | HW10, cell 10 + |
| 12 | TAP11_IN | HW11, cell 11 + |
| 13 | TAP12_IN | HW12, cell 12 + |
| 14 | TAP13_IN | HW13, cell 13 + |
| 15 | TAP14_IN | HW14, cell 14 + |
| 16 | TAP15_IN | HW15, cell 15 + |
| 17 | TAP16_IN | HW16, cell 16 + (stack +) |

### F100–F116: Littelfuse 0154005.DR, OMNI-BLOK holder with Nano2 451 5 A very-fast fuse

- Symbol `Device:Fuse`.
- Footprint `Fuse:Fuseholder_Littelfuse_Nano2_154x`.
- Non-polar, 2 terminals [S].

| Refdes | Pin 1 | Pin 2 |
|---|---|---|
| F100 | TAP0_IN | TAP0 |
| F101 | TAP1_IN | TAP1 |
| F102 | TAP2_IN | TAP2 |
| F103 | TAP3_IN | TAP3 |
| F104 | TAP4_IN | TAP4 |
| F105 | TAP5_IN | TAP5 |
| F106 | TAP6_IN | TAP6 |
| F107 | TAP7_IN | TAP7 |
| F108 | TAP8_IN | TAP8 |
| F109 | TAP9_IN | TAP9 |
| F110 | TAP10_IN | TAP10 |
| F111 | TAP11_IN | TAP11 |
| F112 | TAP12_IN | TAP12 |
| F113 | TAP13_IN | TAP13 |
| F114 | TAP14_IN | TAP14 |
| F115 | TAP15_IN | TAP15 |
| F116 | TAP16_IN | TAP16 |

### R300–R316: Yageo RC0603FR-07100RL, 100 Ω 1 % 0.1 W, 0603

- Symbol `Device:R`; footprint `Resistor_SMD:R_0603_1608Metric`.
- The value is the ADI-recommended 100 Ω [P, LTC6813-1 p.73].
- Pin 1 connects to TAPt at the F1tt.2 pad (Kelvin).

| Refdes | Pin 1 | Pin 2 | → U1 pin |
|---|---|---|---|
| R300 | TAP0 | CS_0 | 38 (C0) |
| R301 | TAP1 | CS_1 | 36 (C1) |
| R302 | TAP2 | CS_2 | 34 (C2) |
| R303 | TAP3 | CS_3 | 32 (C3) |
| R304 | TAP4 | CS_4 | 30 (C4) |
| R305 | TAP5 | CS_5 | 28 (C5) |
| R306 | TAP6 | CS_6 | 26 (C6) |
| R307 | TAP7 | CS_7 | 24 (C7) |
| R308 | TAP8 | CS_8 | 22 (C8) |
| R309 | TAP9 | CS_9 | 20 (C9) |
| R310 | TAP10 | CS_10 | 18 (C10) |
| R311 | TAP11 | CS_11 | 16 (C11) |
| R312 | TAP12 | CS_12 | 14 (C12) |
| R313 | TAP13 | CS_13 | 12 (C13) |
| R314 | TAP14 | CS_14 | 10 (C14) |
| R315 | TAP15 | CS_15 | 8 (C15) |
| R316 | TAP16 | CS_16 | 6 (C16), and also 4 (C17) and 2 (C18) |

### C700–C716: Murata GRM188R71H103KA01D, 10 nF 50 V X7R, 0603

- Symbol `Device:C`; footprint `Capacitor_SMD:C_0603_1608Metric`.
- These form the differential filter [P, LTC6813-1 Fig. 35a].
- Stress: ≤ 4.2 V (8.4 V in a swap fault) of 50 V, i.e. ≤ 17 %.

| Refdes | Pin 1 | Pin 2 |
|---|---|---|
| C700 | CS_0 | GND_B |
| C701 | CS_1 | CS_0 |
| C702 | CS_2 | CS_1 |
| C703 | CS_3 | CS_2 |
| C704 | CS_4 | CS_3 |
| C705 | CS_5 | CS_4 |
| C706 | CS_6 | CS_5 |
| C707 | CS_7 | CS_6 |
| C708 | CS_8 | CS_7 |
| C709 | CS_9 | CS_8 |
| C710 | CS_10 | CS_9 |
| C711 | CS_11 | CS_10 |
| C712 | CS_12 | CS_11 |
| C713 | CS_13 | CS_12 |
| C714 | CS_14 | CS_13 |
| C715 | CS_15 | CS_14 |
| C716 | CS_16 | CS_15 |

### NT1: net tie, TAP0 ↔ GND_B

- Symbol `Device:NetTie_2`; footprint `NetTie:NetTie-2_SMD_Pad0.5mm`.
- Placed on pad F100.2.

| Pin | Net |
|---|---|
| 1 | TAP0 |
| 2 | GND_B |

## 3. Block B3 CH[k]: balancing channels (k = 1…16)

### 3.1 Naming rule for channel k

- **Refdes.** U1kk, T1kk, U2kk, D1kk, D2kk, D3kk, C1kk…C6kk, R1kk, R2kk, R4kk. Example for k = 7: U107, T107, U207, D107, D207, D307, C107…C607, R107, R207, R407.
- **Nets.**
  - The local positive is `TAPk` and the local reference (ground) is `TAP(k−1)`.
  - The channel's private nets are `SW_k`, `SNB_k`, `OUT_k`, `DCH_k`, `MODE_k`, `SEC_k`, `S_k`, `LEDA_k`.
  - Shared nets: `FLYBUS`, `TAP0` (secondary return), `LEDA_(k−1)` (next opto down the string).
- **Edge cases.**
  - k = 1: TAP(k−1) = TAP0. U201 pin 2 goes to `STR_Q`, not `LEDA_0`.
  - k = 16: TAPk = TAP16. LEDA_16 is fed from R24.

### 3.2 Channel k, complete

#### U1kk: ADI LT8584EFE#PBF, monolithic active cell balancer, TSSOP-16 with exposed pad (FE)

- Symbol: **custom** (17 pins as below).
- Footprint: `Package_SO:TSSOP-16-1EP_4.4x5mm_P0.65mm`. The EP gets thermal vias to a ≥ 650 mm² TAP(k−1) plane [P, p.28 item 3]; ≥ 9 vias is our choice [I].
- Pin numbers come from the pin configuration (p.2) and pin functions (p.9) [P].
- Simple mode: MODE tied to V_IN; VSNS and VCELL shorted to V_IN; RTMR grounded [P, p.9, p.13, p.22–23].

| Pin | Name | Net | Note |
|---|---|---|---|
| 1 | GND | TAP(k−1) | |
| 2 | GND | TAP(k−1) | |
| 3 | GND | TAP(k−1) | |
| 4 | GND | TAP(k−1) | |
| 5 | MODE | MODE_k | tied to V_IN through R4kk = 10 kΩ, so a solder bridge to pin 4 or 6 cannot short the cell [I]. MODE − V_IN ≤ 0.2 V is held [P] |
| 6 | RTMR | TAP(k−1) | grounded in simple mode [P] |
| 7 | DIN | S_k | driven directly by the ADBMS1818 S pin [P]. Low = enable |
| 8 | OUT | OUT_k | needs C_OUT [P]. Outputs V_CELL − V_TEMP in simple mode; not measured |
| 9 | VIN | TAPk | |
| 10 | VCELL | TAPk | shorted to V_IN in simple mode [P] |
| 11 | VSNS | TAPk | shorted to V_IN in simple mode [P] |
| 12 | DCHRG | DCH_k | input in simple mode, high = enable [P]. Driven by opto U2kk |
| 13 | SW | SW_k | |
| 14 | SW | SW_k | |
| 15 | SW | SW_k | |
| 16 | SW | SW_k | |
| 17 | EP (GND) | TAP(k−1) | must be soldered [P] |

#### T1kk: Coilcraft NA5743-ALD, flyback transformer 1:4, 4 µH, SMD 8-pad

- Symbol: **custom** (8 pins).
- Footprint: **custom** per the Coilcraft Doc 1075 recommended land pattern. That is 2 rows × 4 pads, pad 2.03 × 1.27 mm, pitch 2.50 mm, rows 11.68 mm apart as dimensioned. Check on the drawing whether that dimension is inner edge or pad centre [P/I].
- Pin roles come from the Doc 1075 schematic [P]:
  - The primary is two windings, 1–2 to 3–4, to be paralleled on the PCB. Dots are at pins 1 and 2.
  - The secondary is 5–8, with the dot at pin 8.
  - Pins 6 and 7 do not appear in the schematic. They have pads only.

| Pin | Name | Net |
|---|---|---|
| 1 | PRI start (dot) | TAPk |
| 2 | PRI start (dot) | TAPk |
| 3 | PRI finish | SW_k |
| 4 | PRI finish | SW_k |
| 5 | SEC (no dot) | SEC_k |
| 6 | (no winding) | NC (pad only, no copper to other nets) |
| 7 | (no winding) | NC (pad only) |
| 8 | SEC (dot) | TAP0 |

Polarity check [I]:

- While the switch is on, the dotted ends are positive. Pin 5 is then negative relative to pin 8, so D1kk is reverse-biased.
- While the switch is off, pin 5 swings positive and D1kk conducts into FLYBUS.

This is the correct flyback phasing.

#### D1kk: Diodes Inc ES1G-13-F, 400 V 1 A super-fast rectifier, SMA (output diode)

- Symbol `Device:D`; footprint `Diode_SMD:D_SMA`.
- Cathode band = pin 1 [P, DS14001].

| Pin | Name | Net |
|---|---|---|
| 1 | K | FLYBUS |
| 2 | A | SEC_k |

#### D2kk: Diodes Inc ES1G-13-F, SMA (snubber diode)

| Pin | Name | Net |
|---|---|---|
| 1 | K | SNB_k |
| 2 | A | SW_k |

#### D3kk: ST SMA6T6V7AY, unidirectional TVS, 5 V standoff, SMA (cell input crowbar and clamp)

- Symbol `Device:D_Zener`; footprint `Diode_SMD:D_SMA`.
- Cathode band = pin 1 [S]. The ST datasheet was not readable here.

| Pin | Name | Net |
|---|---|---|
| 1 | K | TAPk |
| 2 | A | TAP(k−1) |

#### C1kk (CVCELL) and C2kk (CTRAN): Murata GRM32ER61A107ME20L, 100 µF 10 V X5R, 1210

- Symbol `Device:C`; footprint `Capacitor_SMD:C_1210_3225Metric`.
- C1kk sits at the channel's tap entry. C2kk sits at T1kk pin 1/2 and U1kk pin 17 [P, p.22].

| Refdes | Pin 1 | Pin 2 |
|---|---|---|
| C1kk | TAPk | TAP(k−1) |
| C2kk | TAPk | TAP(k−1) |

#### C3kk (CVIN): Murata GRM188R71A105KA61D, 1 µF 10 V X7R, 0603

| Pin | Net |
|---|---|
| 1 | TAPk (at U1kk pin 9) |
| 2 | TAP(k−1) |

#### C4kk (COUT): Murata GRM188R71H473KA61D, 47 nF 50 V X7R, 0603

The value is ADI's "most applications" 47 nF [P, p.23].

| Pin | Net |
|---|---|
| 1 | OUT_k |
| 2 | TAP(k−1) |

#### C5kk (snubber C): Murata GCM188R72A223KA37D, 22 nF 100 V X7R, 0603

| Pin | Net |
|---|---|
| 1 | SNB_k |
| 2 | TAPk |

#### C6kk (flyback output C): KEMET C1210C225K1RACTU, 2.2 µF 100 V X7R, 1210

Placed at D1kk pin 1 and T1kk pin 8.

| Pin | Net |
|---|---|
| 1 | FLYBUS |
| 2 | TAP0 |

#### R1kk (snubber R): Yageo RC2010FK-074K99L, 4.99 kΩ 1 % 0.5 W, 2010

Symbol `Device:R`; footprint `Resistor_SMD:R_2010_5025Metric`.

| Pin | Net |
|---|---|
| 1 | SNB_k |
| 2 | TAPk |

#### R2kk (DCHRG pull-down): Yageo RC0603FR-0733KL, 33 kΩ 1 %, 0603

| Pin | Net |
|---|---|
| 1 | DCH_k |
| 2 | TAP(k−1) |

#### R4kk (MODE pull-up): Yageo RC0603FR-0710KL, 10 kΩ 1 %, 0603

| Pin | Net |
|---|---|
| 1 | TAPk |
| 2 | MODE_k |

#### U2kk: Toshiba TLP293(GB-TPL,E, phototransistor optocoupler, SO4

- Symbol `Isolator:TLP293`; footprint `Package_SO:SOIC-4_4.55x2.6mm_P1.27mm`.
- Pins from datasheet §4, "Packaging and Pin Assignment" [P].

| Pin | Name | Net |
|---|---|---|
| 1 | Anode | LEDA_k |
| 2 | Cathode | LEDA_(k−1); for k = 1: STR_Q |
| 3 | Emitter | DCH_k |
| 4 | Collector | TAPk |

### 3.3 Channels 1–16, expanded (for checking)

Every channel has the pins of §3.2 with these substitutions. U1kk pin 7 is S_k, which comes from
ADBMS1818 pin 39 − 2k.

| k | U1kk | Local + (TAPk) | Local ref (TAP(k−1)) | DIN net (U1 pin) | U2kk pin 1 | U2kk pin 2 |
|---|---|---|---|---|---|---|
| 1 | U101 | TAP1 | TAP0 | S_1 (37) | LEDA_1 | STR_Q |
| 2 | U102 | TAP2 | TAP1 | S_2 (35) | LEDA_2 | LEDA_1 |
| 3 | U103 | TAP3 | TAP2 | S_3 (33) | LEDA_3 | LEDA_2 |
| 4 | U104 | TAP4 | TAP3 | S_4 (31) | LEDA_4 | LEDA_3 |
| 5 | U105 | TAP5 | TAP4 | S_5 (29) | LEDA_5 | LEDA_4 |
| 6 | U106 | TAP6 | TAP5 | S_6 (27) | LEDA_6 | LEDA_5 |
| 7 | U107 | TAP7 | TAP6 | S_7 (25) | LEDA_7 | LEDA_6 |
| 8 | U108 | TAP8 | TAP7 | S_8 (23) | LEDA_8 | LEDA_7 |
| 9 | U109 | TAP9 | TAP8 | S_9 (21) | LEDA_9 | LEDA_8 |
| 10 | U110 | TAP10 | TAP9 | S_10 (19) | LEDA_10 | LEDA_9 |
| 11 | U111 | TAP11 | TAP10 | S_11 (17) | LEDA_11 | LEDA_10 |
| 12 | U112 | TAP12 | TAP11 | S_12 (15) | LEDA_12 | LEDA_11 |
| 13 | U113 | TAP13 | TAP12 | S_13 (13) | LEDA_13 | LEDA_12 |
| 14 | U114 | TAP14 | TAP13 | S_14 (11) | LEDA_14 | LEDA_13 |
| 15 | U115 | TAP15 | TAP14 | S_15 (9) | LEDA_15 | LEDA_14 |
| 16 | U116 | TAP16 | TAP15 | S_16 (7) | LEDA_16 | LEDA_15 |

The following are the same for every k: T1kk pin 8 → TAP0; D1kk pin 1 → FLYBUS; C6kk → FLYBUS / TAP0.

## 4. Block B4 RET: stack return, clamp, sense

### D1: Vishay V8P10-M3/86A, 100 V 8 A TMBS Schottky, TO-277A (SMPC)

- Symbol `Device:D_Schottky_AAK`; footprint `Package_TO_SOT_SMD:TO-277A`.
- Anodes are pins 1 and 2; the cathode is the tab [P, doc 89005 p.1]. KiCad pad 3 is the tab.
- Place at F116. Put ≥ 400 mm² of copper on the tab (TAP16).

| Pin | Name | Net |
|---|---|---|
| 1 | A | FLYBUS |
| 2 | A | FLYBUS |
| 3 | K (tab) | TAP16 |

### D2: Littelfuse SMBJ70A, 600 W unidirectional TVS, V_R 70 V, SMB

- Symbol `Device:D_Zener`; footprint `Diode_SMD:D_SMB`.
- Cathode band = pin 1 [P, SMBJ series datasheet, "Cathode / Anode" marking].

| Pin | Name | Net |
|---|---|---|
| 1 | K | FLYBUS |
| 2 | A | TAP0 |

### R19: Yageo RC1206FR-072ML, 2.0 MΩ 1 % 0.25 W 200 V, 1206

Stress: ≤ 90 V of 200 V.

| Pin | Net |
|---|---|
| 1 | FLYBUS |
| 2 | FLY_SNS |

### R20: Yageo RC0603FR-07100KL, 100 kΩ 1 %, 0603

| Pin | Net |
|---|---|
| 1 | FLY_SNS |
| 2 | GND_B |

### C19: Murata GRM188R71H103KA01D, 10 nF 50 V X7R, 0603

| Pin | Net |
|---|---|
| 1 | FLY_SNS |
| 2 | GND_B |

## 5. Block B5 AFE: ADBMS1818 cell monitor

### U1: ADI ADBMS1818ASWZ, 18-cell battery monitor, 64-lead LQFP with exposed pad (05-08-1982)

- Symbol: **custom**.
- Footprint: **custom**, based on `Package_QFP:LQFP-64-1EP_10x10mm_P0.5mm_EP5x5mm_ThermalVias` with the EP land set to 5.74 × 5.74 mm [P, Fig. 113].
- Pin numbers from Rev A, Fig. 3 and Table 14 [P]. They are identical to LTC6813-1 Rev B p.3 [P].
- For fewer than 18 cells, unused C pins are shorted to the highest connected cell and unused S pins are left open [P, LTC6813-1 p.85; ADBMS1818 "Using … with fewer than 18 cells"].
- Single device in SPI mode [P, LTC6813-1 p.45]: ICMP is tied to IBIAS, IBIAS has 2–20 kΩ to V−, and IPB/IMB are terminated in 100 Ω.

| Pin | Name | Net | Note |
|---|---|---|---|
| 1 | V+ | VPLUS | via R1 100 Ω from STK_F; C1 100 nF to V− |
| 2 | C18 | CS_16 | unused input tied to the top cell |
| 3 | S18 | NC | |
| 4 | C17 | CS_16 | unused input tied to the top cell |
| 5 | S17 | NC | |
| 6 | C16 | CS_16 | |
| 7 | S16 | S_16 | → U116.7 |
| 8 | C15 | CS_15 | |
| 9 | S15 | S_15 | → U115.7 |
| 10 | C14 | CS_14 | |
| 11 | S14 | S_14 | → U114.7 |
| 12 | C13 | CS_13 | |
| 13 | S13 | S_13 | → U113.7 |
| 14 | C12 | CS_12 | |
| 15 | S12 | S_12 | → U112.7 |
| 16 | C11 | CS_11 | |
| 17 | S11 | S_11 | → U111.7 |
| 18 | C10 | CS_10 | |
| 19 | S10 | S_10 | → U110.7 |
| 20 | C9 | CS_9 | |
| 21 | S9 | S_9 | → U109.7 |
| 22 | C8 | CS_8 | |
| 23 | S8 | S_8 | → U108.7 |
| 24 | C7 | CS_7 | |
| 25 | S7 | S_7 | → U107.7 |
| 26 | C6 | CS_6 | |
| 27 | S6 | S_6 | → U106.7 |
| 28 | C5 | CS_5 | |
| 29 | S5 | S_5 | → U105.7 |
| 30 | C4 | CS_4 | |
| 31 | S4 | S_4 | → U104.7 |
| 32 | C3 | CS_3 | |
| 33 | S3 | S_3 | → U103.7 |
| 34 | C2 | CS_2 | |
| 35 | S2 | S_2 | → U102.7 |
| 36 | C1 | CS_1 | |
| 37 | S1 | S_1 | → U101.7 |
| 38 | C0 | CS_0 | |
| 39 | GPIO1 | NTC1 | thermistor TH1 |
| 40 | GPIO2 | NTC2 | thermistor TH2 |
| 41 | GPIO3 | NTC3 | thermistor TH3 |
| 42 | GPIO4 | GND_B | unused; tied low [I] |
| 43 | GPIO5 | GND_B | unused [I] |
| 44 | GPIO6 | GND_B | unused [I] |
| 45 | GPIO7 | GND_B | unused [I] |
| 46 | GPIO8 | GND_B | unused [I] |
| 47 | GPIO9 | GND_B | unused [I] |
| 48 | VREG | 5V_SYS | supplied by the buck (allowed [P]); C2 1 µF |
| 49 | DRIVE | NC | no NPN regulator; output left open [I] |
| 50 | VREF2 | VREF2 | C4 1 µF; NTC pull-ups |
| 51 | VREF1 | VREF1 | C3 1 µF; no DC load [P] |
| 52 | DTEN | GND_B | discharge timer disabled, so the 2 s watchdog clears DCC [P] |
| 53 | SDI | SPI_MOSI | ISOMD = V− → 4-wire SPI [P] |
| 54 | SDO | SPI_MISO | open drain; 4.99 kΩ pull-up (R4) [P] |
| 55 | ISOMD | GND_B | SPI mode |
| 56 | WDT | ADBMS_WDT | open drain; R5 1 MΩ to +3V3 [P] |
| 57 | IBIAS | IBIAS | R2 20 kΩ to V− |
| 58 | ICMP | IBIAS | tied to IBIAS [P] |
| 59 | V− | GND_B | must be tied to pin 60 [P] |
| 60 | V− | GND_B | |
| 61 | CSB (IMA) | SPI_CS | |
| 62 | SCK (IPA) | SPI_SCK | |
| 63 | IMB | IMB | R3 100 Ω to IPB |
| 64 | IPB | IPB | |
| 65 | EP (V−) | GND_B | must be soldered [P] |

### AFE support parts

| Refdes | Part | Pin 1 | Pin 2 | Note |
|---|---|---|---|---|
| R1 | Yageo RC0805FR-07100RL, 100 Ω 1 % 0.125 W, 0805 | STK_F | VPLUS | ADI recommendation [P]. A V+ short gives 0.57 A until F1 opens |
| C1 | Murata GRM188R72A104KA35D, 100 nF 100 V X7R, 0603 | VPLUS | GND_B | 58 % |
| C2 | Murata GRM188R71A105KA61D, 1 µF 10 V, 0603 | 5V_SYS | GND_B | at U1 pin 48 [P] |
| C3 | same 1 µF | VREF1 | GND_B | at U1 pin 51 [P] |
| C4 | same 1 µF | VREF2 | GND_B | at U1 pin 50 [P] |
| R2 | Yageo RC0603FR-0720KL, 20 kΩ, 0603 | IBIAS | GND_B | 2–20 kΩ allowed [P] |
| R3 | Yageo RC0603FR-07100RL, 100 Ω, 0603 | IPB | IMB | port B termination [P] |
| R4 | Yageo RC0603FR-074K99L, 4.99 kΩ, 0603 | SPI_MISO | +3V3 | SDO pull-up [P] |
| R5 | Yageo RC0603FR-071ML, 1 MΩ, 0603 | ADBMS_WDT | +3V3 | [P] |
| R6, R7, R8 | Yageo RT0603BRD0710KL, 10.0 kΩ 0.1 %, 0603 | VREF2 | NTC1 / NTC2 / NTC3 | |
| TH1, TH2, TH3 | Murata NCP18XH103F03RB, 10 kΩ NTC, 0603 (`Device:Thermistor_NTC`, `Resistor_SMD:R_0603_1608Metric`) | NTC1 / NTC2 / NTC3 | GND_B | located at U103, U106, U112. These sit in other domains' areas, so keep 1.0 mm (B-2) |
| C5, C6, C7 | Murata GRM188R71H104KA93D, 100 nF 50 V X7R, 0603 | NTC1 / NTC2 / NTC3 | GND_B | at U1 GPIO pins |

## 6. Block B6 PSU: fused stack supply, 5 V buck, 3.3 V LDO

### F1: Littelfuse 0451.125MRL, Nano2 125 mA very fast, 2410

- Symbol `Device:Fuse`; footprint `Fuse:Fuse_Littelfuse-NANO2-451_453`.
- Pin 1 connects to TAP16 at pad F116.2 (Kelvin-style branch).

| Pin | Net |
|---|---|
| 1 | TAP16 |
| 2 | STK_F |

### D3: Diodes Inc ES1G-13-F, SMA (reverse-polarity block for the buck)

| Pin | Name | Net |
|---|---|---|
| 1 | K | BUCK_PRE |
| 2 | A | STK_F |

### R9: Yageo RC2512FK-07100RL, 100 Ω 1 % 1 W, 2512 (inrush and fault limiter)

| Pin | Net |
|---|---|
| 1 | BUCK_PRE |
| 2 | BUCK_IN |

### U3: TI LM5164DDAR, 100 V 1 A synchronous buck, SO-8 PowerPAD (DDA)

- Symbol `Regulator_Switching:LM5164DDA`.
- Footprint `Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm_ThermalVias`.
- Pins from Table 4-1 [P].

| Pin | Name | Net |
|---|---|---|
| 1 | GND | GND_B |
| 2 | VIN | BUCK_IN |
| 3 | EN/UVLO | BUCK_EN |
| 4 | RON | BUCK_RON |
| 5 | FB | BUCK_FB |
| 6 | PGOOD | PGOOD |
| 7 | BST | BUCK_BST |
| 8 | SW | BUCK_SW |
| 9 | EP | GND_B |

### Buck passives

| Refdes | Part | Pin 1 | Pin 2 | Role |
|---|---|---|---|---|
| C8 | KEMET C1210C225K1RACTU, 2.2 µF 100 V X7R, 1210 | BUCK_IN | GND_B | C_IN at U3 pin 2 |
| C9 | Murata GRM188R72A104KA35D, 100 nF 100 V, 0603 | BUCK_IN | GND_B | HF bypass |
| R10 | Yageo RC1206FR-074M7L, 4.7 MΩ 1 %, 1206 (200 V) | BUCK_IN | BUCK_EN | UVLO top |
| R11 | Yageo RC0603FR-07300KL, 300 kΩ 1 %, 0603 | BUCK_EN | GND_B | UVLO bottom |
| R12 | Yageo RC0603FR-0749K9L, 49.9 kΩ 1 %, 0603 | BUCK_RON | GND_B | R_RON → 250 kHz |
| C10 | Murata GRM188R71H222KA01D, 2.2 nF 50 V X7R, 0603 | BUCK_BST | BUCK_SW | bootstrap, 2.2 nF as specified [P] |
| L1 | Coilcraft MSS1048-473MLB, 47 µH (`Device:L`, `Inductor_SMD:L_Coilcraft_MSS1048-XXX`) | BUCK_SW | 5V_SYS | |
| C11 | Murata GRM32ER71A226KE20L, 22 µF 10 V X7R, 1210 | 5V_SYS | GND_B | C_OUT (50 %) |
| R13 | Yageo RC0603FR-07316KL, 316 kΩ 1 %, 0603 | 5V_SYS | BUCK_FB | R_FB1 |
| R14 | Yageo RC0603FR-07100KL, 100 kΩ 1 %, 0603 | BUCK_FB | GND_B | R_FB2 |
| R15 | Yageo RC1206FR-07470KL, 470 kΩ 1 %, 1206 | BUCK_SW | BUCK_RAMP | R_A (Type 3) |
| C12 | Murata GRM1885C1H102JA01D, 1 nF 50 V C0G, 0603 | BUCK_RAMP | 5V_SYS | C_A |
| C13 | Murata GRM1885C1H221JA01D, 220 pF 50 V C0G, 0603 | BUCK_RAMP | BUCK_FB | C_B |
| R16 | Yageo RC0603FR-07100KL, 100 kΩ, 0603 | PGOOD | +3V3 | PGOOD pull-up (≤ 14 V allowed [P]) |

### U4: Microchip MCP1700T-3302E/TT, 3.3 V LDO, SOT-23

- Symbol `Regulator_Linear:MCP1700x-330xxTT`; footprint `Package_TO_SOT_SMD:SOT-23`.
- Pins from Table 3-1 [P].

| Pin | Name | Net |
|---|---|---|
| 1 | GND | GND_B |
| 2 | VOUT | +3V3 |
| 3 | VIN | 5V_SYS |

| Refdes | Part | Pin 1 | Pin 2 |
|---|---|---|---|
| C14 | Murata GRM188R71A105KA61D, 1 µF 10 V, 0603 | 5V_SYS | GND_B |
| C15 | same | +3V3 | GND_B |

## 7. Block B7 MCU

### U2: ST STM32G031K8T6, Cortex-M0+ 64 KB, LQFP-32

- Symbol `MCU_ST_STM32G0:STM32G031K8Tx`; footprint `Package_QFP:LQFP-32_7x7mm_P0.8mm`.
- Sources [P]: pin numbers from DS12992 Fig. 5; alternate functions from Table 13; ADC channels from Table 12.
- Unused pins are left unconnected and set to analog mode in firmware [I].

| Pin | Name | Net | Function |
|---|---|---|---|
| 1 | PB9 | LEDR | GPIO out, red LED |
| 2 | PC14-OSC32_IN | NC | |
| 3 | PC15-OSC32_OUT | NC | |
| 4 | VDD/VDDA | +3V3 | C16, C17 |
| 5 | VSS/VSSA | GND_B | |
| 6 | PF2-NRST | NRST | C18 |
| 7 | PA0 | FLY_SNS | ADC_IN0 [P] |
| 8 | PA1 | BAL_EN | GPIO out, global enable |
| 9 | PA2 | MCU_TX | USART2_TX, AF1 [P] |
| 10 | PA3 | MCU_RX | USART2_RX, AF1 [P] |
| 11 | PA4 | SPI_CS | GPIO out (chip select) |
| 12 | PA5 | SPI_SCK | SPI1_SCK, AF0 [P] |
| 13 | PA6 | SPI_MISO | SPI1_MISO, AF0 [P] |
| 14 | PA7 | SPI_MOSI | SPI1_MOSI, AF0 [P] |
| 15 | PB0 | ISO_VCC1 | GPIO out, supplies U5 side 1 (≤ 4 mA) |
| 16 | PB1 | FLT_DRV | GPIO out, PhotoMOS LED |
| 17 | PB2 | ADBMS_WDT | GPIO in |
| 18 | PA8 | PGOOD | GPIO in |
| 19 | PA9 | NC | |
| 20 | PC6 | NC | |
| 21 | PA10 | NC | |
| 22 | PA11 [PA9] | NC | |
| 23 | PA12 [PA10] | NC | |
| 24 | PA13 | SWDIO | SWD |
| 25 | PA14-BOOT0 | SWCLK | SWD. Boot is selected by option bytes [I] |
| 26 | PA15 | NC | |
| 27 | PB3 | NC | |
| 28 | PB4 | NC | |
| 29 | PB5 | NC | |
| 30 | PB6 | NC | |
| 31 | PB7 | NC | |
| 32 | PB8 | LEDG | GPIO out, green LED |

### MCU support

| Refdes | Part | Pin 1 | Pin 2 |
|---|---|---|---|
| C16 | Murata GRM188R71H104KA93D, 100 nF, 0603 | +3V3 | GND_B |
| C17 | Murata GRM188R61A475KE15D, 4.7 µF 10 V X5R, 0603 | +3V3 | GND_B |
| C18 | Murata GRM188R71H104KA93D, 100 nF, 0603 | NRST | GND_B |
| R17 | Yageo RC0603FR-071KL, 1 kΩ | LEDG | LEDG_A |
| R18 | Yageo RC0603FR-071KL, 1 kΩ | LEDR | LEDR_A |

### D5, D6: Lite-On LTST-C191KGKT (green) and LTST-C191KRKT (red), 0603 LEDs

- Symbol `Device:LED`; footprint `LED_SMD:LED_0603_1608Metric`.
- Pin 1 = K [S, Lite-On cathode mark].

| Refdes | Pin 1 (K) | Pin 2 (A) |
|---|---|---|
| D5 | GND_B | LEDG_A |
| D6 | GND_B | LEDR_A |

### J3: Tag-Connect TC2030-IDC-NL footprint (no part fitted), SWD, factory use only

- Symbol `Connector:Conn_ARM_SWD_TagConnect_TC2030-NL`.
- Footprint `Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical`.
- Pin names from the KiCad symbol [S].
- J3 is at battery potential. Program it only with an isolated debugger, or with the harness unplugged and the board on a bench supply.

| Pin | Name | Net |
|---|---|---|
| 1 | VCC | +3V3 |
| 2 | SWDIO | SWDIO |
| 3 | ~RESET | NRST |
| 4 | SWCLK | SWCLK |
| 5 | GND | GND_B |
| 6 | SWO | NC |

### TP1–TP6: test pads

Symbol `Connector:TestPoint`; footprint `TestPoint:TestPoint_Pad_D1.5mm`.

| Refdes | Net |
|---|---|
| TP1 | FLYBUS |
| TP2 | 5V_SYS |
| TP3 | +3V3 |
| TP4 | GND_B |
| TP5 | STR_Q |
| TP6 | STK_F |

## 8. Block B8 EN: global balance enable (opto LED string)

String order, from the top: STK_F → D4 → STR_D → R24 → LEDA_16 → U216 → LEDA_15 → U215 → … →
LEDA_1 → U201 → STR_Q → Q1 → Q1_E → R23 → GND_B.

### Q1: onsemi MMBT5551LT1G, NPN 160 V, SOT-23

- Symbol `Transistor_BJT:MMBT5551L`; footprint `Package_TO_SOT_SMD:SOT-23`.
- Pins: 1 = base, 2 = emitter, 3 = collector [P, MMBT5550L/5551L p.1].

| Pin | Name | Net |
|---|---|---|
| 1 | B | Q1_B |
| 2 | E | Q1_E |
| 3 | C | STR_Q |

### D4: Diodes Inc ES1G-13-F, SMA (reverse block for the string)

| Pin | Name | Net |
|---|---|---|
| 1 | K | STR_D |
| 2 | A | STK_F |

### Resistors

| Refdes | Part | Pin 1 | Pin 2 | Stress |
|---|---|---|---|---|
| R21 | Yageo RC0603FR-0710KL, 10 kΩ | BAL_EN | Q1_B | — |
| R22 | Yageo RC0603FR-07100KL, 100 kΩ | Q1_B | GND_B | — |
| R23 | Yageo RC0805FR-071K6L, 1.6 kΩ 0.125 W, 0805 | Q1_E | GND_B | 3.6 mW (60 mW, 49 %, in a Q1-short fault) |
| R24 | Yageo RC2010FK-074K7L, 4.7 kΩ 0.5 W, 2010 | STR_D | LEDA_16 | 11 mW (0.18 W, 36 %, in a fault) |

## 9. Block B9 ISO: user port and fault contact (reinforced barrier)

### U5: TI ISO7721DWVR, reinforced dual-channel digital isolator (1 forward, 1 reverse), SOIC-8 wide (DWV)

- Symbol `Isolator:ISO7721DWV`; footprint `Package_SO:SOIC-8_7.5x5.85mm_P1.27mm`.
- Pins from Table 5-1, D/DWV column [P].
- Side 1 (pins 1–4) is the battery side; side 2 (pins 5–8) is the user side.

| Pin | Name | Net | Side |
|---|---|---|---|
| 1 | VCC1 | ISO_VCC1 | battery |
| 2 | OUTA | MCU_RX | battery |
| 3 | INB | MCU_TX | battery |
| 4 | GND1 | GND_B | battery |
| 5 | GND2 | GND_ISO | user |
| 6 | OUTB | ISO_OUTB | user |
| 7 | INA | ISO_INA | user |
| 8 | VCC2 | VIO_ISO | user |

### ISO support parts

| Refdes | Part | Pin 1 | Pin 2 | Side |
|---|---|---|---|---|
| C20 | Murata GRM188R71H104KA93D, 100 nF | ISO_VCC1 | GND_B | battery |
| C21 | same | VIO_ISO | GND_ISO | user |
| R25 | Yageo RC0603FR-07100RL, 100 Ω | ISO_OUTB | TXD_ISO | user |
| R26 | Yageo RC0603FR-07100RL, 100 Ω | RXD_ISO | ISO_INA | user |
| R27 | Yageo RC0603FR-07100KL, 100 kΩ | ISO_INA | VIO_ISO | user (idle-high pull-up [I]) |
| R28 | Yageo RC0603FR-07390RL, 390 Ω | FLT_DRV | FLT_LED | battery (I_F = (3.3 − 1.25)/390 = 5.3 mA) |

### U6: Panasonic AQY210EHAX, PhotoMOS 1 Form A, 350 V 130 mA, reinforced 5 kV, 4-SMD

- Symbol `Relay_SolidState:AQY280EH`, used for its identical 4-pin PhotoMOS pinout; value field AQY210EHAX.
- Footprint `Package_DIP:SMDIP-4_W7.62mm`.
- The pin positions 1–4 come from the GU-E package drawing [P]. The functions (1 LED +, 2 LED −, 3/4 output) follow the Panasonic convention; the catalog schematic page was not in the retrieved PDF [S].

| Pin | Name | Net | Side |
|---|---|---|---|
| 1 | LED anode | FLT_LED | battery |
| 2 | LED cathode | GND_B | battery |
| 3 | Output | FLT_A | fault (user) |
| 4 | Output | FLT_B | fault (user) |

### J2: Phoenix Contact MC 1,5/6-G-3,81 (header, number 1803316 [I]), with plug MC 1,5/6-ST-3,81 (1803617)

- Symbol `Connector_Generic:Conn_01x06`.
- Footprint `Connector_Phoenix_MC:PhoenixContact_MC_1,5_6-G-3.81_1x06_P3.81mm_Horizontal`.
- The whole connector is in the USER/FAULT domain.

| Pin | Net | Use |
|---|---|---|
| 1 | GND_ISO | host ground |
| 2 | VIO_ISO | host logic supply, 2.25–5.5 V |
| 3 | TXD_ISO | board → host |
| 4 | RXD_ISO | host → board |
| 5 | FLT_A | fault contact |
| 6 | FLT_B | fault contact |

## 10. Mechanical parts (no electrical pins)

### H1–H6: M4 mounting holes, non-plated

- Symbol `Mechanical:MountingHole`; footprint `MountingHole:MountingHole_4.3mm_M4`.
- No net. Keep a 3.0 mm copper-free ring on all layers (B-5).

## 11. Off-board objects: harness B1 (not on the PCB; put it on a separate schematic sheet, excluded from the board)

The harness is one assembly per pack. For each tap t = 0…16, the chain from the cell terminal is:

- **HTt.** Panduit PV18-14R-MY ring terminal, ¼" (M6) stud, crimped to 18 AWG.
- **Stub.** 50 mm of 18 AWG.
- **HFt.** Littelfuse 0324007.HXP, 3AB 7 A fast axial fuse. Both leads are crimped with butt splices (e.g. Panduit BSV18X [S]). The fuse body and splices are covered with adhesive-lined dual-wall heat-shrink.
- **HWt.** UL 1015 18 AWG wire, ≤ 1.0 m.
- **HP1 position t+1.** Phoenix MSTB 2,5/17-ST-5,08 (1757161), screw clamp.

Nets of the chain:

| Point | Net |
|---|---|
| Ring and stub | `CELLTERMt`: the B− terminal for t = 0, cell t + for t ≥ 1 |
| HFt pin 1 | CELLTERMt |
| HFt pin 2 and wire HWt | `TAPt_W` |
| HP1 position t+1 | TAPt_W |

When mated, HP1 position (t+1) meets J1 pin (t+1), so TAPt_W ≡ TAPt_IN.

| t | HT/HF/HW refdes | Lands on | HP1 position | Wire label / colour |
|---|---|---|---|---|
| 0 | HT0 / HF0 / HW0 | B− (cell 1 −). **Not** the BMS P− | 1 | 0, black |
| 1 | HT1 / HF1 / HW1 | cell 1 + | 2 | 1 |
| 2 | HT2 / HF2 / HW2 | cell 2 + | 3 | 2 |
| 3 | HT3 / HF3 / HW3 | cell 3 + | 4 | 3 |
| 4 | HT4 / HF4 / HW4 | cell 4 + | 5 | 4 |
| 5 | HT5 / HF5 / HW5 | cell 5 + | 6 | 5 |
| 6 | HT6 / HF6 / HW6 | cell 6 + | 7 | 6 |
| 7 | HT7 / HF7 / HW7 | cell 7 + | 8 | 7 |
| 8 | HT8 / HF8 / HW8 | cell 8 + | 9 | 8 |
| 9 | HT9 / HF9 / HW9 | cell 9 + | 10 | 9 |
| 10 | HT10 / HF10 / HW10 | cell 10 + | 11 | 10 |
| 11 | HT11 / HF11 / HW11 | cell 11 + | 12 | 11 |
| 12 | HT12 / HF12 / HW12 | cell 12 + | 13 | 12 |
| 13 | HT13 / HF13 / HW13 | cell 13 + | 14 | 13 |
| 14 | HT14 / HF14 / HW14 | cell 14 + | 15 | 14 |
| 15 | HT15 / HF15 / HW15 | cell 15 + | 16 | 15 |
| 16 | HT16 / HF16 / HW16 | cell 16 + (B+). **Not** the BMS P+ | 17 | 16, red |

**Fewer than 16 cells (N = 13, 14 or 15).**

- Build N+1 wire chains, t = 0…N. Wire N goes to position N+1.
- Insert Phoenix EBP 2-5 (1733169) insertion bridges [S] so that positions N+1, N+2, …, 17 are all connected. That takes 16 − N bridges between adjacent positions.
- The firmware parameter N must match. At boot the firmware checks that cells N+1…16 read < 50 mV.

**Mated-pair check before plugging in** (DESIGN §9):

- V(pos p+1) − V(pos p) must be within 2.5–4.2 V for p = 1…N.
- Bridged positions must read 0 V.
- V(pos 17) − V(pos 1) must equal the stack voltage.

## 12. Net-by-net node list (cross-check)

Indexed nets follow the rules. Non-indexed nets are listed in full.

| Net | Nodes |
|---|---|
| TAP0 | F100.2, R300.1, NT1.1, U101.1, U101.2, U101.3, U101.4, U101.6, U101.17, D301.2, C101.2, C201.2, C301.2, C401.2, R201.2, T1kk.8 (k = 1…16), C6kk.2 (k = 1…16), D2.2 |
| TAPk, 1 ≤ k ≤ 15 | F1kk.2, R3kk.1, and for channel k: U1kk.9, U1kk.10, U1kk.11, T1kk.1, T1kk.2, D3kk.1, C1kk.1, C2kk.1, C3kk.1, C5kk.2, R1kk.2, R4kk.1, U2kk.4. For channel k+1: U1(k+1).1–4, U1(k+1).6, U1(k+1).17, D3(k+1).2, C1(k+1).2, C2(k+1).2, C3(k+1).2, C4(k+1).2, R2(k+1).2 |
| TAP16 | F116.2, R316.1, F1.1, D1.3, U116.9, U116.10, U116.11, T116.1, T116.2, D316.1, C116.1, C216.1, C316.1, C516.2, R116.2, R416.1, U216.4 |
| TAPt_IN | J1.(t+1), F1tt.1 |
| CS_t, t ≤ 15 | R3tt.2, C7tt.1 (C700.1 for t = 0), C7(t+1).2, U1.(38 − 2t) |
| CS_16 | R316.2, C716.1, U1.6, U1.4, U1.2 |
| S_k | U1.(39 − 2k), U1kk.7 |
| SW_k | U1kk.13–16, T1kk.3, T1kk.4, D2kk.2 |
| SNB_k | D2kk.1, C5kk.1, R1kk.1 |
| OUT_k | U1kk.8, C4kk.1 |
| MODE_k | U1kk.5, R4kk.2 |
| DCH_k | U1kk.12, R2kk.1, U2kk.3 |
| SEC_k | T1kk.5, D1kk.2 |
| LEDA_k, 1 ≤ k ≤ 15 | U2kk.1, U2(k+1).2 |
| LEDA_16 | U216.1, R24.2 |
| STR_Q | U201.2, Q1.3, TP5 |
| STR_D | D4.1, R24.1 |
| FLYBUS | D1kk.1 (k = 1…16), C6kk.1 (k = 1…16), D1.1, D1.2, D2.1, R19.1, TP1 |
| STK_F | F1.2, R1.1, D3.2, D4.2, TP6 |
| VPLUS | R1.2, C1.1, U1.1 |
| BUCK_PRE | D3.1, R9.1 |
| BUCK_IN | R9.2, U3.2, C8.1, C9.1, R10.1 |
| BUCK_EN | U3.3, R10.2, R11.1 |
| BUCK_RON | U3.4, R12.1 |
| BUCK_FB | U3.5, R13.2, R14.1, C13.2 |
| BUCK_RAMP | R15.2, C12.1, C13.1 |
| BUCK_SW | U3.8, C10.2, L1.1, R15.1 |
| BUCK_BST | U3.7, C10.1 |
| 5V_SYS | L1.2, C11.1, R13.1, C12.2, U1.48, C2.1, U4.3, C14.1, TP2 |
| +3V3 | U4.2, C15.1, U2.4, C16.1, C17.1, R4.2, R5.2, R16.2, J3.1, TP3 |
| GND_B | NT1.2, C700.2, U1.42–47, U1.52, U1.55, U1.59, U1.60, U1.65, C1.2, C2.2, C3.2, C4.2, C5.2, C6.2, C7.2, R2.2, TH1.2, TH2.2, TH3.2, U3.1, U3.9, C8.2, C9.2, R11.2, R12.2, C11.2, R14.2, U4.1, C14.2, C15.2, U2.5, C16.2, C17.2, C18.2, D5.1, D6.1, J3.5, R20.2, C19.2, R22.2, R23.2, U5.4, C20.2, U6.2, TP4 |
| VREF1 | U1.51, C3.1 |
| VREF2 | U1.50, C4.1, R6.1, R7.1, R8.1 |
| NTC1 / NTC2 / NTC3 | U1.39 / U1.40 / U1.41; R6.2 / R7.2 / R8.2; TH1.1 / TH2.1 / TH3.1; C5.1 / C6.1 / C7.1 |
| IBIAS | U1.57, U1.58, R2.1 |
| IPB / IMB | U1.64, R3.1 / U1.63, R3.2 |
| SPI_CS | U2.11, U1.61 |
| SPI_SCK | U2.12, U1.62 |
| SPI_MOSI | U2.14, U1.53 |
| SPI_MISO | U2.13, U1.54, R4.1 |
| ADBMS_WDT | U1.56, R5.1, U2.17 |
| PGOOD | U3.6, R16.1, U2.18 |
| FLY_SNS | R19.2, R20.1, C19.1, U2.7 |
| BAL_EN | U2.8, R21.1 |
| Q1_B | R21.2, R22.1, Q1.1 |
| Q1_E | Q1.2, R23.1 |
| MCU_TX | U2.9, U5.3 |
| MCU_RX | U5.2, U2.10 |
| ISO_VCC1 | U2.15, U5.1, C20.1 |
| FLT_DRV | U2.16, R28.1 |
| FLT_LED | R28.2, U6.1 |
| NRST | U2.6, C18.1, J3.3 |
| SWDIO | U2.24, J3.2 |
| SWCLK | U2.25, J3.4 |
| LEDG / LEDG_A | U2.32, R17.1 / R17.2, D5.2 |
| LEDR / LEDR_A | U2.1, R18.1 / R18.2, D6.2 |
| GND_ISO | U5.5, C21.2, J2.1 |
| VIO_ISO | U5.8, C21.1, R27.2, J2.2 |
| ISO_OUTB | U5.6, R25.1 |
| TXD_ISO | R25.2, J2.3 |
| RXD_ISO | J2.4, R26.1 |
| ISO_INA | R26.2, R27.1, U5.7 |
| FLT_A | U6.3, J2.5 |
| FLT_B | U6.4, J2.6 |

**NC pins (intentional).**

- U1 pins 3, 5, 49.
- T1kk pins 6 and 7.
- U2 pins 2, 3, 19, 20, 21, 22, 23, 26, 27, 28, 29, 30, 31.
- J3 pin 6.

## 13. Part count

| Group | Count |
|---|---|
| Channels: 16 × 15 (U1kk, U2kk, T1kk, D1kk, D2kk, D3kk, C1kk–C6kk, R1kk, R2kk, R4kk) | 240 |
| Tap entries: 17 × 3 (F1tt, R3tt, C7tt) + J1 + NT1 | 53 |
| AFE: U1, R1–R8, C1–C7, TH1–TH3 | 19 |
| PSU: F1, D3, R9, U3, C8–C13, R10–R16, L1, U4, C14, C15 | 21 |
| MCU: U2, C16–C18, R17, R18, D5, D6, J3, TP1–TP6 | 15 |
| RET: D1, D2, R19, R20, C19 | 5 |
| EN: Q1, D4, R21–R24 | 6 |
| ISO: U5, U6, C20, C21, R25–R28, J2 | 9 |
| Mounting holes H1–H6 | 6 |
| **Placed total** | **374** (368 electrical, cross-checked by script, + 6 holes) |
| Off-board: HP1 + 17 × (HT, HF, HW) + up to 3 bridges | 52–55 |
