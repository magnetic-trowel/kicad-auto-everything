# Comprehension stage audit: weak labels, manual audit and suite table (kae.circuit, 2026-10-22)

> **Method note.** `kae.circuit` reads a `.kicad_pcb` (names, values, footprints, lib ids, pin functions and types,
> fields, net classes, zone nets, sheet names) and writes the physics brief; positions are never read. This note is
> the raw evidence behind [comprehension](../../docs/topics/physics/comprehension.md).
> - **Weak labels.** [`tools/research/physics/cm_comprehension_eval.py`](../../tools/research/physics/cm_comprehension_eval.py)
>   builds the brief for the 112 reference boards in `kae-work/tasks` (KiCad 10.0.7 suite), then reads the human
>   placement to score it against random baselines. Run: `-j 2`, `OMP_NUM_THREADS=1`, about 40 s per pass.
> - **Manual audit.** 10 dev boards were read part by part against the brief; rules were fixed where an error
>   generalised (F), and residual errors kept (R). 3 held-out boards were audited after the code froze, errors
>   recorded before any fix, then fixed. Dev numbers are therefore training-set numbers; held-out numbers are honest.
> - Tags: [C] computed by the scripts named; [I] our reading of the board.

## 1. Weak labels on 112 boards [C]

| Metric | Final | No sheet names | Random tie order | Baseline |
|---|---|---|---|---|
| Capacitor ownership, all owners (caps on rails with >= 2 owners) | **73.1%** (n=1381, 74 boards; per-board mean 68.0%) | 60.9% | 60.8% | 37.8% |
| Decap ownership, decap groups only | 74.7% (n=1160, 64 boards) | 61.9% | 59.6% | 38.2% |
| Group kNN3: cap among the 3 nearest caps to one of its IC's power pins | 74.9% (n=1722) | 66.6% | 66.5% | |
| Pin kNN1, same rail (suggested pin pairing) | 33.2% (n=1457) | 31.0% | 23.5% | 16.8% |
| Pin kNN3, same rail | 49.0% | 46.6% | 43.8% | 34.8% |
| Commutation cells: human loop below the 5th percentile of random placement | 76.6% of 64 (below 1st: 40.6%; median loop 13.45 mm) | 70.3% | 71.9% | 5% |
| Crystals: crystal to its IC's oscillator pins | median 4.71 mm, 87.1% within 12 mm (n=31); load caps median 2.835 mm from the crystal | | | |
| Protection order: TVS nearer the connector than the protected IC | 60.2% of 266 chains | | | 50% |
| Brief runtime | median 0.045 s, max 1.157 s (two processes on four shared cores) | | | |

"All owners" counts decap groups (their power pins), commutation cells (the IC's loop pins), a connector-fed rail's
entry (the source part's pins) and a buck's output filter (the inductor's far pad); entry and converter-output owners
are candidates even in runs that do not name them, so variants are compared on the same truth.

**Ownership probability calibration** (all owners, per capacitor, final run):

| reported p | n | mean p | observed |
|---|---|---|---|
| 0.0-0.5 | 543 | 0.24 | 51.7% |
| 0.5-0.7 | 245 | 0.59 | 78.8% |
| 0.7-0.9 | 228 | 0.81 | 89.5% |
| 0.9-1.0 | 365 | 0.96 | 90.7% |

Monotone, underconfident below 0.7: the softmax spreads mass that the quota-constrained assignment does not lose.

**Cells by class** (percentile of the human loop among 400 random placements):

| class | n | median percentile | below 5th |
|---|---|---|---|
| boost | 6 | 0.0037 | 100.0% |
| buck | 47 | 0.0200 | 70.2% |
| half_bridge | 11 | 0.0100 | 90.9% |

**Member spread** (mean distance to the members' centroid against random placement; kinds with n >= 5):

| kind | n | median percentile | below 5th |
|---|---|---|---|
| antenna | 14 | 0.154 | 28.6% |
| commutation_cell:boost | 6 | 0.000 | 83.3% |
| commutation_cell:buck | 45 | 0.003 | 86.7% |
| commutation_cell:half_bridge | 11 | 0.000 | 81.8% |
| connector_chain | 2712 | 0.220 | 15.7% |
| crystal | 32 | 0.000 | 96.9% |
| decap | 771 | 0.013 | 72.4% |
| oscillator | 5 | 0.095 | 40.0% |
| victim:analog | 117 | 0.048 | 52.1% |
| victim:crystal | 31 | 0.090 | 22.6% |
| victim:feedback | 41 | 0.000 | 95.1% |
| victim:sense | 23 | 0.013 | 73.9% |

Plain connector chains (a cable pin to the first IC pin) are not compact and carry no placement claim; protected
chains, decaps, cells and crystals are.

## 2. Allocation variants (ownership, all owners, 74 boards) [C]

Scratch study (`own_study.py`, same truth as §1). Each line changes one rule from the version before it.

| Variant | Pooled | Per board | Kept |
|---|---|---|---|
| Base (cells prefer ceramics <= 1 uF, regulator output groups separate) | 72.97% | 64.1% | |
| Converter's own output group merged into its cell | 72.97% | 64.1% | yes (no change, removes double counting) |
| 'count': cells take small ceramics only when the loads' pins leave some spare | 73.21% | 64.8% | yes |
| Cell's second capacitor scored -3 / -1 below its first | 73.21% / 73.44% | 63.5% / 63.9% | no (per-board worse) |
| Quotas scaled in proportion under a shortage | 70.86% | 65.3% | no |
| Polarized >= 10 uF caps of a connector-fed rail owned by the entry | 73.19% (vs 73.01%) | 66.6% (vs 66.4%) | yes |
| Buck output / boost input caps >= 10 uF owned by the inductor | 73.01% (vs 72.81%) | 67.5% (vs 67.0%) | yes |
| ICs and modules before LEDs on ties | 72.94% (vs 73.01%) | 68.1% (vs 67.9%) | no (neutral) |
| Cells avoid small ceramics entirely under scarcity | 73.01% (vs 73.01%) | 67.9% | yes (fixes a fixture, neutral) |

The rank-order term (RANK_W) was measured earlier at 0 (best). Differences under 0.5 pp are within noise
(1,380 caps); rules were kept only when principled and not worse.

## 3. Manual audit: dev boards (10) [I]

#### 1 brenocq BLDC power (TMC6300 3-phase driver, 3x INA240 on in-line phase shunts, LDOs, TPS2115A mux, CAN, USB-C)
- F TMC6300 '1.8VOUT' internal regulator not a rail (INT_OUT_PIN)
- F VOLT.U/V/W/SRC 20k/10k dividers not reported (divider victims)
- F VBUS source unknown (rail sources ran before connector typing)
- ok half-bridge cell C10 -> U3 VS -> U3 GND; three in-line shunts R2/R4/R12 with INA240 Kelvin loops; CAN pair with 120 ohm R11; USB ESD D3
- R C2 (TMC6300 VCP charge-pump cap) only 'series_or_coupling'
- R VIN has no voltage (no name, no rating): the cell's excite.V is null
- R BAT54S ADC clamps (U7, U10-U12) carry the generic 'schottky' role; R16-R18 100k bleeders read as pull-downs
- R J1 (Molex 501920 board-to-board) typed wire_to_board

#### 2 azoninc doorman (ESP32-S3-WROOM, AP63203 buck from a 24 V bus via OR-ing Schottkys, MB6S bridge, PhotoMOS SSR)
- F '+24V Bus' (space in the name) not a rail
- F VCC terminal feed through D5 not counted as supply evidence
- F OR-ing Schottkys D1/D5 called connector protection
- F AP63203 switching frequency 500 kHz -> 1.1 MHz (table)
- F U3 GAQY252G3S PhotoMOS SSR typed ic (0.62) -> optocoupler
- F Net-(D1-K) (OR-ed node) derived from VCC (no voltage) -> from +5V through D1 (4.6 V)
- F '+24V Bus' source unknown -> bridge rectifier D2
- R C2 (100 nF, 1.7 mm from the module's 3V3 pin) given to the WS2812 D3 by reference order; U1 (the module) left uncovered. An 'ICs before LEDs' tie rule measured neutral on the suite and was not kept

#### 3 stm32 battery orbit (TPS63802 buck-boost, STM32F030, CP2102, MCP73031)
- F I2C1_SCLK read as SPI/high_speed (SCLK regex before I2C)
- F PC14 and USER_Button read as clocks (STM32 GPIO names PC14/PC15 in XTAL_PIN)
- F +BATT not a rail (VIN/VBAT pins typed input)
- F Net-(U22-VDD) not a rail (CP2102 VDD typed bidirectional); now source internal
- F BOOT0 'BOOT0_SW' unknown -> switch
- R PWR1 (K3-1270L slide switch, value 'PWR') was LED, now unknown (0.39)
- F boost cell took the MCU's 100 nF caps (C3, C4); now C13 22 uF + C2 (human: C13 at U15 VOUT, C2 at the MCU)
- R buck loop closed on C7 (4.7 uF, 14 mm away in the human layout) rather than C14 (10 uF, 1.8 mm)
- R Net-(U1-PROG) charger PROG pin reported as an analog victim (0.5)
- R U17 EEPROM VCC uncovered (designer shares the MCU's caps)

#### 4 eurorack saturation (4x NE5532, +-12 V, two boards in one file)
- F the four op-amps' V+ to V- capacitors (C4-C7) not used as decoupling -> split_supply decaps, all 4 match the human layout
- F C8/C9 22 uF electrolytics given to U1 -> entry bulk at D7 (human: 4.5 mm from D7)
- F -12V source direction (series diode on a negative rail)
- F panel-hole footprints (one NPTH pad) typed potentiometer/connector/switch -> mechanical
- R D4_+/D4_- (LED drive through a header) kept as an analog diff pair (0.96)
- R D7/D8 '4001' without the rectifier subtype

#### 5 latentred-pdu (3x NCP45560 load switch, 3x INA230, 4-terminal shunts)
- F Kelvin lines 12V0_LCx_N/_P (6 nets) read as rails (INA230 VIN+/- typed power_in)
- F 12V0_OUT_EN read as a rail (rail-like name with _EN)
- F load-switch outputs without a voltage -> inherit 12 V from VIN
- F 12V0_LCx sourced from the connector -> derived through the 4-terminal shunt
- R no power-path or heat structure for the load switches and shunts (unknown current)

#### 6 yuiop29re keyboard (RP2040 breakout module, 29 WS2812C, USB-C, TRRS link)
- F /5V0 sourced from the TRRS jack J3 -> derived from USB_VBUS through DS1 and F1 (middle net followed)
- F /3V3 sourced from the OLED header J2 -> the RP2040 breakout module's 3V3 output
- F U1 'RP2040_breakout' module at 0.41 -> 0.93
- R 29 WS2812 loads share 5 caps: given to LED1-LED5 by reference order (confidence 0.19-0.32), 24 LEDs uncovered

#### 7 sparkfun XRP controller (RP2350B with internal SMPS, AP63357 buck, 2x DRV8411, RT9080 LDO, PMOS power path)
- F RP2350 IOVDD pins (10) had no decap group: the internal-SMPS cell swallowed all of U1's pins on 3.3V; now only the loop pins
- F the cell took 5 caps (C1, C2, C15, C19, C20) as leftovers
- F U1 (RP2350B) role 'switching_regulator' -> mcu (structure role only for regulator ICs)
- F GPIO0/DIST_TRIG and RADIO_GPIO0/LED read as boot straps (GPIO0 is a strap only on ESP parts)
- F GPIO10/MOTOR_4_IN1 etc. read as analog: DRV8411 AIN1/AIN2 are logic inputs
- F GPIO40/CURRENT_ML: ADC alternate pin 'ADC0/GPIO40' now weak evidence (0.67)
- F Net-(JP3-A) and Net-(D5-VCC) derived from the downstream rail through the fuse; now the barrel jack / USB VBUS pin
- F Net-(D5-VCC) subrole 'regulated' from the ESD array's power_out-typed VCC pin
- R VSYS, VRAW and VIN sourced from header pins: the PMOS ideal-diode / switch power path is not followed
- R C19/C20 (U2 flash, U3 PSRAM) given to U1 (10 pins, quota fills in reference order); U2/U3 uncovered
- R U9 'RM2' radio module typed ic/None (0.59)
- R J16-J19 motor connectors typed 'header' (they carry bridge outputs)

#### 8 tomtor AVR128DB28 + RFM95 LoRa (MCP1700 LDO, two crystals, SMA antenna)
- F VCC (battery) derived from 3V3 through JP5, a normally-open solder jumper ('Close when no MCP1700'), and given 3.3 V
- ok antenna J3 -> U2.ANA at 915 MHz; crystals Y1 24 MHz and Y2 32.768 kHz with their load caps; battery divider R4/R5
- R 3V3 decaps: U3 gets C8, C9, C10 (right) but U2 gets C7, C11 (human: next to U3) and U1's output gets C2, C12 (human: C2 next to U2, C12 next to U3): 3 of 7
- R solder jumpers JP1-JP4 hang off the crystal nets (stubs) and are not flagged

#### 9 bentwire USB-C FUSB302 Pi HAT (LMR36006 buck from PD VBUS, RP2040, flash)
- F C7/C8 22 uF buck output caps given to the FUSB302 (U1) -> converter_output at L1 (human: 4.5 mm from L1)
- F Net-(U2-BOOT) (converter bootstrap) read as a boot strap -> signal/bootstrap
- F FUSB302 typed 'phy' with a 0.4 W heat source -> usb_pd, no heat
- F RP2040 VREG_VOUT rail at 3.94 V (capacitor-rating estimate) -> 1.1 V (core-regulator table)
- F LMR36006 VCC (internal bias LDO) decap labelled regulator_input -> bypass
- ok buck cell on VBUS closes on C2 (human nearest, 1.1 mm); U1 gets C18-C20, U302 gets C303-C308, C311 (all right)
- R C301 given to the flash U301 (human: next to the RP2040)
- R C12-C16 sit at the USB-C VBUS pins (entry ceramics); entry ownership covers only polarized bulk, so they go to the cell and U1
- R decap U1:VBUS on the FUSB302's VBUS sense pin (a detection input, not a supply)

#### 10 olimex DCDC 8-50 V -> 5/12 V (TX4138 non-synchronous buck, pins without function names)
- ok buck cell C2 -> U1 VIN -> SW -> D2 (K, A) -> C2 in loop order; C1 100 uF bulk; L1 output caps C6/C7 (converter_output)
- F feedback divider R7/R5 (+ C5 feed-forward) reported as a generic divider: the IC's pins have no names; the net '/Vfb' now counts
- F output-connector chains walked through L1 into SW and called the freewheel diode D2 and the LED zener D3 protection
- R the TX4138 switch current enters through the 30 mOhm input shunts R1/R2 (VIN -> ILIM/EP); the loop lists the VIN pin and omits them
- R C4 (bootstrap through R3 4.7 ohm) only 'bootstrap_or_snubber'; C3/R4 (NA) SW snubber read as a filter
- R Vout reported 12 V from the connector name; the divider implies 5 V default, 12 V with the jumper (TX4138 Vref not in the table)

## 4. Manual audit: held-out boards (3) [I]

#### H1 ojg THAT mic preamp v2 (THAT1512, 48 V phantom, through-hole, unnamed nets; 89 parts)
- E U1 (THAT1512) inputs Net-(D5-Pad1)/Net-(D6-Pad1): 'signal', not analog (subtype unknown, so '+'/'-' pins were not read as amplifier inputs) -- the board's most sensitive nets
- E RG1/RG2 gain network (C13, SW3 ladder) not marked analog
- E D15-D17 '16V' zeners: subtype missing (diode/None)
- E VIN source unknown (barrel jack -> F1 -> L3; the middle net also carries C9 and D7)
- E V48P/V35P/V18P voltages from capacitor ratings (39 V) instead of the names' 48/35/18 V
- gap phantom-power matched pair R5/R6 (6k8 0.1 %) not modelled
- ok U1 decap (C6, C11 on V35P); rails VIN/V35P/V48P; V18P reference victim; no false cells; connectors typed (XLR audio, barrel power)

#### H2 libresolar BMS C1 (BQ76952 16S AFE, 8x IPT012N08N5 high-side FETs, 300 uOhm 4-terminal shunt, LMR3801x buck, ESP32-C3, CAN; 210 parts)
- E R45 '300µ' 4-terminal Kelvin shunt not recognized (value unparsed, lib 'R_Shunt_..._Kelvin' unused): no sense structure for the pack current; SHUNT_P/N and SRP/SRN only weak analog
- E BQ76952 subtype unknown: VC0-VC16 cell-sense nets (17) and their C1+..C16+ cable side are 'signal'
- E /LED_GREEN, /LED_RED read as clocks (ESP32-C3 XTAL_32K_P/N pins double as GPIO0/1)
- gap FET bank Q2-Q9 on the pack path: no heat or power-path structure (current unknown)
- ok buck cell U3 (C40, catch diode D9) in loop order; converter output caps; feedback R28/R31 (Vref 1.0 V table); CAN pair + D8; USB + D3/D4; REG18/REG1 internal rails; BAT+ -> D1 -> VIN; TEMP1/2 analog; integrated antenna

#### H3 ZSWatch devkit (nPM1300 PMIC with two bucks, nRF5340 module, 4 sensors, haptic driver, display FPC; 230-line brief)
- E both nPM1300 buck cells take +1V8 (buck 1's own output via a 0 ohm link, pin V_IO) as the input rail instead of VSYS (pin V_DD): wrong input loop on 2 cells
- E X608 display FPC 'ER-CON0.4-24P' typed oscillator (0.37)
- E VIB-EN (DRV2603 EN) and Net-(IC506-EN) (PCA9306 EN) read as reset lines
- E TOUCH-EN 100k/100k bias pair reported as an analog divider victim
- ok USB pairs (2) with USBLC6; QSPI bus; I2S/mic clocks; haptic driver half-bridge cell (IC505, C510); integrated antenna (M601); +1V8/+3V0 derived through 0 ohm from the PMIC outputs; 19 decap groups on sensor VDD nets (per-IC current-measurement headers as sources)

After the held-out audit these were fixed and covered by tests: amplifier inputs on ICs known only by '+'/'-' pins,
zeners valued in volts, input jack -> fuse -> filter sources, '300µ' shunts and 'R_Shunt_*_Kelvin' footprints,
battery-monitor cell-sense inputs (BQ769xx/LTC68xx), XTAL-named GPIOs, EN pins outside MCUs, a converter's own output
as its fallback input, logic straps as dividers, 'CON0.4' connectors.

## 5. Precision and recall per structure type [I]

Structure-level: a structure is correct when its class, rail(s) and core members are right; member-level slips
(a loop closed on the second-nearest capacitor) are listed in §3 but not counted. Capacitor ownership is §1.

| Structure | Dev (10 boards, after fixes): emitted / correct / missed | P | R | Held-out (3 boards, before fixes): emitted / correct / missed | P | R |
|---|---|---|---|---|---|---|
| Commutation cell | 10 / 10 / 0 (2 member slips) | 100% | 100% | 4 / 2 / 0 (2 nPM1300 bucks on the wrong input rail) | 50% | 50% |
| Crystal circuit | 5 / 5 / 0 | 100% | 100% | 0 / 0 / 0 | | |
| Feedback divider | 4 / 4 / 0 | 100% | 100% | 1 / 1 / 0 | 100% | 100% |
| Measurement divider | 9 / 9 / 0 | 100% | 100% | 1 / 0 / 0 (a logic strap) | 0% | |
| Shunt with Kelvin sense loop | 8 / 8 / 0 | 100% | 100% | 0 / 0 / 1 (BMS 300 uOhm shunt) | | 0% |
| Protected connector chain | 14 / 12 / 0 (2 through an ESD array's VBUS pin) | 86% | 100% | 18 / 18 / ? | 100% | |
| Antenna | 2 / 2 / 0 | 100% | 100% | 2 / 2 / 0 | 100% | 100% |
| Split-supply, entry and converter-output decaps | 10 / 10 / 0 | 100% | 100% | 2 / 2 / 0 | 100% | 100% |
| Decap groups (IC, rail) | 48 / 47 / 3 (1 on a VBUS sense pin; 3 ICs left uncovered) | 98% | 94% | 25 / 25 / ? | 100% | |
| Rails | 50 / 50 / 0; 3 voltages and 3 sources wrong | 100% | 100% | 27 / 27 / 0; 3 voltages, 3 sources wrong | 100% | 100% |
| Sensitive nets (analog, sense, cell-sense) | (not counted per net) | | | 15 / 13 / 20 (false: a PDM data line, a logic strap; missed: THAT1512 inputs and gain node, 17 BMS cell taps) | 87% | 39% |
| False clock/reset roles | 0 after fixes | | | 4 (2 LED nets as clocks, 2 enables as resets) | | |
| Differential pairs | 19 / 15 / 0 (4 LED-drive lines on one board) | 79% | 100% | 7 / 7 / 0 | 100% | |
| Part kinds | 945 parts: 1 unknown, 1 debatable (RM2 module as IC) | 99.8% | | 431 parts: 1 wrong (display FPC as oscillator), 4 subtypes missing | 99.8% | |

## 6. Suite table (final run, 112 boards) [C]

Structures per board, unknown parts, low-confidence parts (< 0.6) and structures (< 0.5), brief runtime (two
processes). Totals: 9,227 parts; 64 commutation cells on 32 boards; 790 decap structures on 81 boards; 32 crystals and
8 oscillators; 42 antennas; 597 victims; 127 heat sources; 4 unknown parts on 4 boards; 172 low-confidence parts;
66 low-confidence structures. Brief median 0.06 s, p90 0.25 s, max 1.6 s; the largest board (621 parts) takes 0.6 s.

| board | parts | cells | decap | xtal | chains | victims | ant | heat | unknown | low-conf parts | low-conf structs | brief s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256foundation-emberone00-pcb-emberone | 395 | 2 | 90 | 1 | 12 | 8 | 1 | 26 | 0 | 0 | 0 | 0.497 |
| antmicro-ddr5-testbed-ddr5-testbed | 65 | 1 | 5 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0.192 |
| antmicro-myra-sip-interposer-myra-sip-interposer | 32 | 0 | 10 | 1 | 0 | 2 | 0 | 1 | 0 | 1 | 0 | 0.072 |
| azonenberg-dumptruck-emmc-interposer | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.006 |
| azonenberg-latentred-dual-sfp28 | 50 | 0 | 1 | 0 | 23 | 2 | 0 | 0 | 0 | 0 | 0 | 0.033 |
| azonenberg-latentred-linecard | 621 | 4 | 33 | 0 | 337 | 27 | 17 | 6 | 0 | 2 | 1 | 0.641 |
| azonenberg-latentred-pdu | 46 | 0 | 8 | 0 | 16 | 3 | 0 | 0 | 0 | 0 | 0 | 0.054 |
| berkeleylab-obsidian-obsidian | 521 | 7 | 43 | 2 | 146 | 19 | 1 | 8 | 0 | 0 | 5 | 1.157 |
| bluerobotics-ping-dev-kit-pingdevkit | 452 | 8 | 38 | 1 | 77 | 44 | 0 | 8 | 0 | 4 | 1 | 0.517 |
| chipsalliance-rocket-pcb-fmc-sdram | 73 | 0 | 20 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0.066 |
| chipsalliance-rocket-pcb-fmc-usb-gpio-spi-jtag | 146 | 1 | 25 | 0 | 59 | 2 | 0 | 1 | 0 | 0 | 1 | 0.103 |
| d3a-c-biscuit-crowbar | 13 | 0 | 0 | 0 | 2 | 1 | 0 | 0 | 0 | 1 | 0 | 0.006 |
| d3a-kitspace-12v5a-breakout | 18 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.01 |
| d3a-kitspace-gas-sensor | 15 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 1 | 0 | 0.008 |
| d3a-kitspace-hum-temp-sensor | 12 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0.007 |
| d3a-kitspace-temp-breakout | 14 | 0 | 0 | 0 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0.01 |
| d3a-marlin-neopixel-bridge-attiny85-marneo | 8 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0.006 |
| d3a-pcb-serie-led-strip | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.006 |
| d3a-starsynctrackers-reset-switch | 9 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 1 | 0 | 0.006 |
| d3a-z2amiller-sensorboard-programmer | 8 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0.005 |
| dangerousprototypes-buspirate5-hardware-6-rev2b | 227 | 0 | 58 | 1 | 26 | 38 | 0 | 2 | 0 | 1 | 1 | 0.158 |
| electron271-tuxkeychain-tuxkeychain | 56 | 0 | 9 | 1 | 33 | 8 | 0 | 3 | 0 | 0 | 0 | 0.052 |
| git4dcc-rtb-c11-c11 | 163 | 2 | 15 | 0 | 57 | 15 | 0 | 2 | 0 | 7 | 0 | 0.248 |
| hackclub-reflow-badge | 68 | 1 | 10 | 1 | 10 | 1 | 0 | 1 | 0 | 0 | 2 | 0.057 |
| kicad-demos-complex-hierarchy-complex-hierarchy | 68 | 0 | 4 | 0 | 6 | 10 | 0 | 1 | 0 | 0 | 0 | 0.04 |
| kicad-demos-ecc83-ecc83-pp-v2 | 15 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0.008 |
| kicad-demos-kit-dev-coldfire-xilinx-5213-kit-dev | 160 | 0 | 19 | 1 | 173 | 11 | 0 | 1 | 0 | 7 | 0 | 0.104 |
| kicad-demos-pic-programmer-pic-programmer | 63 | 1 | 4 | 0 | 14 | 1 | 0 | 1 | 0 | 1 | 0 | 0.036 |
| kicad-demos-sonde-xilinx-sonde-xilinx | 25 | 0 | 1 | 0 | 17 | 4 | 0 | 0 | 0 | 0 | 0 | 0.018 |
| kicad-demos-stickhub-stickhub | 94 | 0 | 7 | 1 | 31 | 2 | 0 | 0 | 0 | 1 | 0 | 0.079 |
| kicad-demos-video-video | 189 | 0 | 12 | 3 | 19 | 14 | 4 | 6 | 0 | 6 | 1 | 0.229 |
| libresolar-bms-c1-bms-c1 | 210 | 1 | 5 | 0 | 44 | 27 | 1 | 1 | 0 | 0 | 0 | 0.1 |
| olimex-dcdc-50-5-12-dcdc-50-5-12-rev-a1 | 46 | 1 | 1 | 0 | 4 | 3 | 0 | 1 | 0 | 0 | 0 | 0.028 |
| olimex-mipi-hdmi-mipi-hdmi-rev-b | 70 | 1 | 6 | 1 | 12 | 1 | 0 | 2 | 0 | 0 | 0 | 0.05 |
| pcbcorpus-0rax-esphome-xiao-base-pcb | 10 | 0 | 0 | 0 | 13 | 1 | 1 | 0 | 0 | 0 | 0 | 0.012 |
| pcbcorpus-0xjmux-esp-prog-adapter-espprog-adapte | 11 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0.015 |
| pcbcorpus-angelnu-esphome-siedle-bus | 37 | 0 | 3 | 0 | 4 | 1 | 1 | 0 | 0 | 0 | 0 | 0.025 |
| pcbcorpus-atoomnetmarc-iot12-iot12-control-board | 73 | 0 | 6 | 0 | 21 | 13 | 0 | 0 | 0 | 0 | 0 | 0.077 |
| pcbcorpus-azoninc-doorman-doorman | 44 | 1 | 2 | 0 | 14 | 2 | 1 | 1 | 0 | 0 | 0 | 0.072 |
| pcbcorpus-badjeff-paw3222-pcb-paw3222 | 7 | 0 | 2 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0.01 |
| pcbcorpus-badjeff-paw3395-pcb-paw3395 | 18 | 0 | 5 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0.014 |
| pcbcorpus-badjeff-pmw3610-pcb-pmw3610-pcb | 15 | 0 | 6 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0.012 |
| pcbcorpus-bentwire-usb-c-fusb302-pi-usb-c-fusb30 | 64 | 1 | 8 | 1 | 43 | 6 | 0 | 1 | 0 | 0 | 0 | 0.062 |
| pcbcorpus-blueokiris-ch552g-dev-board-ch552g-dev | 9 | 0 | 2 | 0 | 18 | 1 | 0 | 0 | 0 | 0 | 0 | 0.009 |
| pcbcorpus-brenocq-bldc-motor-bldcm-power | 60 | 1 | 10 | 0 | 35 | 10 | 0 | 2 | 0 | 0 | 0 | 0.066 |
| pcbcorpus-brown-studios-minuet-minuet | 103 | 3 | 8 | 0 | 51 | 1 | 1 | 3 | 0 | 0 | 0 | 0.105 |
| pcbcorpus-brown-studios-minuet-minuet-086b34 | 88 | 3 | 6 | 0 | 46 | 3 | 1 | 3 | 0 | 0 | 0 | 0.085 |
| pcbcorpus-caffeinated-labs-caffeinated-aftonspar | 37 | 1 | 2 | 0 | 10 | 3 | 1 | 1 | 0 | 0 | 0 | 0.031 |
| pcbcorpus-circuitstate-mitayi-pico-d1-mitayi-pic | 75 | 0 | 5 | 1 | 57 | 1 | 0 | 1 | 0 | 0 | 1 | 0.056 |
| pcbcorpus-diysynthmnl-eurorack-multi-saturation- | 83 | 0 | 6 | 0 | 6 | 21 | 0 | 0 | 0 | 9 | 0 | 0.07 |
| pcbcorpus-electron271-tuxkeychain-expansion | 5 | 0 | 0 | 0 | 2 | 3 | 0 | 0 | 0 | 0 | 0 | 0.012 |
| pcbcorpus-envious-data-envopenpico-envopenpico-r | 58 | 0 | 7 | 1 | 43 | 8 | 0 | 0 | 0 | 0 | 1 | 0.042 |
| pcbcorpus-flypie-ace-2019-ace3nokb | 148 | 0 | 13 | 1 | 128 | 4 | 0 | 1 | 1 | 7 | 10 | 0.209 |
| pcbcorpus-funkeleinhorn-sc14cvmdect-devboard-aud | 34 | 0 | 0 | 0 | 10 | 1 | 0 | 0 | 0 | 0 | 0 | 0.024 |
| pcbcorpus-funkeleinhorn-sc14cvmdect-devboard-sc1 | 96 | 0 | 6 | 0 | 52 | 5 | 1 | 2 | 0 | 0 | 0 | 0.065 |
| pcbcorpus-fyralabs-suzyqboard-suzyqboard | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.007 |
| pcbcorpus-goga64-ulk-ulk | 124 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.047 |
| pcbcorpus-goga64-ulk-ulk-4ead33 | 124 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.048 |
| pcbcorpus-ikajdan-reflow-hot-plate-control-board | 125 | 1 | 8 | 1 | 35 | 8 | 0 | 2 | 0 | 0 | 0 | 0.109 |
| pcbcorpus-jana-marie-analog-toolkit-analog-toolk | 85 | 0 | 5 | 0 | 37 | 10 | 0 | 1 | 0 | 1 | 0 | 0.052 |
| pcbcorpus-jangtrinh-design-os-3d-blender-desktop | 24 | 0 | 0 | 0 | 15 | 2 | 1 | 0 | 0 | 0 | 0 | 0.013 |
| pcbcorpus-jkramarz-thetick-tick | 37 | 1 | 2 | 0 | 7 | 6 | 1 | 1 | 0 | 0 | 0 | 0.042 |
| pcbcorpus-justbuchanan-oasis-ledboard | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 0 | 0.013 |
| pcbcorpus-justbuchanan-oasis-pcb | 45 | 1 | 4 | 0 | 10 | 1 | 1 | 1 | 0 | 6 | 2 | 0.036 |
| pcbcorpus-jvedder-biploar-power-supply-kicad-bip | 37 | 0 | 2 | 0 | 3 | 2 | 0 | 0 | 0 | 0 | 0 | 0.027 |
| pcbcorpus-kabukiflux-duplicanator-scart-duplicat | 42 | 0 | 0 | 0 | 7 | 2 | 0 | 1 | 0 | 0 | 0 | 0.046 |
| pcbcorpus-kabukiflux-midi4mister-midi-4-mister | 40 | 0 | 3 | 0 | 14 | 0 | 0 | 1 | 0 | 0 | 0 | 0.032 |
| pcbcorpus-kabukiflux-pi-rgb-cable-sync-mixer-rgb | 9 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0.015 |
| pcbcorpus-kampi-beelight-beelight | 25 | 0 | 3 | 0 | 4 | 0 | 1 | 0 | 0 | 0 | 0 | 0.024 |
| pcbcorpus-kkckrnz-treble-treble | 141 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 43 | 0 | 0.054 |
| pcbcorpus-koron-yuiop-yuiop29re | 123 | 0 | 5 | 0 | 21 | 0 | 0 | 0 | 0 | 0 | 5 | 0.125 |
| pcbcorpus-lambdakb-trackball-lt6c-lt6c-pcb | 19 | 0 | 3 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0.022 |
| pcbcorpus-leomanangka-esp32-4-channel-relays-esp | 63 | 0 | 4 | 0 | 7 | 0 | 1 | 1 | 0 | 0 | 0 | 0.068 |
| pcbcorpus-m1geo-pi5-pcie-pi5-pcie | 54 | 0 | 3 | 0 | 17 | 0 | 0 | 0 | 0 | 0 | 0 | 0.049 |
| pcbcorpus-mecparts-retrowifimodem-retrowifimodem | 35 | 0 | 4 | 0 | 9 | 0 | 0 | 1 | 0 | 1 | 0 | 0.025 |
| pcbcorpus-mohamedboubaker-battery-powered-stm32- | 53 | 2 | 4 | 1 | 17 | 3 | 0 | 1 | 1 | 0 | 0 | 0.044 |
| pcbcorpus-murexrobotics-electrical-esc-carrier | 49 | 0 | 0 | 0 | 111 | 0 | 0 | 0 | 0 | 1 | 0 | 0.04 |
| pcbcorpus-ojg-thatmicpre-thatmicpre-v2 | 89 | 0 | 1 | 0 | 14 | 3 | 0 | 0 | 0 | 0 | 0 | 0.084 |
| pcbcorpus-pcbcupid-kicad-7-series-schematics | 14 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0.012 |
| pcbcorpus-pcbcupid-kicad-7-series-schematics-d1e | 14 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0.011 |
| pcbcorpus-protolux-electronics-trellis-core-trel | 89 | 2 | 10 | 2 | 9 | 4 | 0 | 2 | 0 | 0 | 0 | 0.119 |
| pcbcorpus-ravinrabbid-doncon2040-donconio | 106 | 0 | 16 | 0 | 8 | 16 | 0 | 0 | 0 | 0 | 0 | 0.094 |
| pcbcorpus-ravinrabbid-doncon2040-donconiomini | 96 | 1 | 11 | 0 | 3 | 16 | 0 | 1 | 0 | 0 | 0 | 0.092 |
| pcbcorpus-rniwase-sdtv2csi-sdtv2csi | 67 | 0 | 6 | 1 | 9 | 11 | 0 | 2 | 0 | 0 | 0 | 0.095 |
| pcbcorpus-rniwase-tsuraragb-tgb-main | 70 | 0 | 12 | 0 | 9 | 1 | 0 | 3 | 0 | 0 | 0 | 0.083 |
| pcbcorpus-siderakb-pmw3360-pcb-pmw3360-pcb-jst | 20 | 0 | 3 | 0 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0.02 |
| pcbcorpus-siderakb-pmw3610-pcb-pmw3610-pcb | 24 | 0 | 6 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0.038 |
| pcbcorpus-stack-chan-stack-chan-m5-pantilt | 39 | 0 | 1 | 0 | 21 | 1 | 0 | 0 | 0 | 0 | 0 | 0.042 |
| pcbcorpus-sufst-pcb-16ch-sensor-hub | 173 | 0 | 7 | 1 | 42 | 49 | 0 | 0 | 0 | 0 | 0 | 0.247 |
| pcbcorpus-sufst-pcb-8ch-sensor-hub | 114 | 0 | 7 | 1 | 26 | 33 | 0 | 0 | 0 | 0 | 0 | 0.122 |
| pcbcorpus-tcsullivan-noisecard-noisecard | 32 | 1 | 3 | 0 | 3 | 2 | 0 | 0 | 1 | 0 | 0 | 0.03 |
| pcbcorpus-tjko-brickpico-brickpico | 124 | 1 | 3 | 0 | 41 | 1 | 1 | 1 | 0 | 1 | 1 | 0.197 |
| pcbcorpus-tjko-fanpico-fanpico-31b08e | 216 | 0 | 9 | 0 | 50 | 8 | 1 | 0 | 0 | 1 | 1 | 0.349 |
| pcbcorpus-tmarhguy-alu-gate-xnor-2in | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.016 |
| pcbcorpus-tmarhguy-alu-gate-xor-2in | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.016 |
| pcbcorpus-tomtor-stm32-rfm95-pcb-avr-lora | 39 | 0 | 4 | 2 | 28 | 3 | 1 | 0 | 0 | 0 | 0 | 0.038 |
| pcbcorpus-tomtor-stm32-rfm95-pcb-avr-lora-805 | 39 | 0 | 4 | 2 | 28 | 3 | 1 | 0 | 0 | 0 | 0 | 0.033 |
| pcbcorpus-tzarc-keyboards-kobold | 104 | 0 | 20 | 0 | 16 | 3 | 0 | 1 | 0 | 0 | 16 | 0.105 |
| pcbcorpus-uzixls-pc-ega-composite-daughterboard- | 51 | 0 | 3 | 0 | 12 | 2 | 0 | 3 | 0 | 0 | 0 | 0.048 |
| pcbcorpus-uzixls-pc-ega-composite-daughterboard- | 48 | 0 | 3 | 0 | 11 | 2 | 0 | 3 | 0 | 0 | 0 | 0.043 |
| pcbcorpus-vaaarad07-pcb-designs-mvcu-f407 | 114 | 0 | 14 | 1 | 36 | 7 | 1 | 1 | 0 | 0 | 2 | 0.078 |
| pcbcorpus-waterloo-rocketry-canhw-processor | 80 | 1 | 9 | 0 | 21 | 4 | 0 | 1 | 0 | 3 | 1 | 0.069 |
| pcbcorpus-wibblyghost-southerly-split-keeb-south | 87 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 28 | 0 | 0.039 |
| pcbcorpus-zhiayang-mikoto-mikoto-flashbed | 48 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 21 | 0 | 0.028 |
| pcbcorpus-zswatch-watch-devkit-hw-zswatch-watch- | 132 | 3 | 19 | 0 | 81 | 4 | 1 | 0 | 0 | 0 | 0 | 0.138 |
| piotr-binkowski-kintex-pcie-board-kintex-pcie | 166 | 2 | 14 | 0 | 18 | 9 | 0 | 3 | 0 | 0 | 4 | 0.106 |
| rapidanalysis-xerxes-xerxes | 58 | 1 | 3 | 1 | 47 | 4 | 0 | 1 | 0 | 2 | 0 | 0.095 |
| reform-reform-reform2-protected-batterypack-pcb | 38 | 0 | 0 | 0 | 5 | 12 | 0 | 0 | 0 | 4 | 0 | 0.024 |
| sparkfun-sparkfun-xrp-controller-sparkfun-xrp-co | 387 | 4 | 10 | 1 | 110 | 11 | 0 | 4 | 0 | 1 | 0 | 0.233 |
| system76-launch-launch-heavy | 73 | 0 | 10 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 10 | 0.04 |
| wntrblm-helium-board | 67 | 0 | 8 | 0 | 19 | 22 | 0 | 0 | 0 | 0 | 0 | 0.087 |
| wntrblm-micronova-board | 55 | 3 | 3 | 0 | 21 | 1 | 0 | 3 | 0 | 5 | 0 | 0.025 |
