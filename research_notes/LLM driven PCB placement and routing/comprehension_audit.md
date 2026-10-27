# Comprehension stage audit: weak labels, manual audit and suite table (kae.circuit, 2026-10-22; follow-up 2026-10-23)

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

First report (2026-10-22). The numbers after the follow-up fixes are in §7.2.

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

## 6. Suite table (final run of 2026-10-23, 112 boards) [C]

Structures per board, unknown parts, low-confidence parts (< 0.6) and structures (< 0.5), brief runtime (two
processes, shared host). Totals: 9,227 parts; 64 commutation cells on 32 boards; 26 power paths on 16 boards; 777
decap structures on 81 boards; 8 rail groups on 5 boards; 32 crystals and 8 oscillators; 42 antennas; 595 victims; 156
heat sources; 4 unknown parts on 4 boards; 172 low-confidence parts; 70 low-confidence structures. Brief median
0.08-0.10 s, max 1.5-3.6 s depending on host load (part classification dominates).

| board | parts | cells | paths | decap | rail groups | xtal | chains | victims | ant | heat | unknown | low-conf parts | low-conf structs | brief s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256foundation-emberone00-pcb-emberone | 395 | 2 | 0 | 90 | 0 | 1 | 12 | 8 | 1 | 26 | 0 | 0 | 0 | 0.676 |
| antmicro-ddr5-testbed-ddr5-testbed | 65 | 1 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0.31 |
| antmicro-myra-sip-interposer-myra-sip-interposer | 32 | 0 | 0 | 10 | 0 | 1 | 0 | 2 | 0 | 1 | 0 | 1 | 2 | 0.154 |
| azonenberg-dumptruck-emmc-interposer | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.02 |
| azonenberg-latentred-dual-sfp28 | 50 | 0 | 0 | 1 | 0 | 0 | 23 | 2 | 0 | 0 | 0 | 0 | 0 | 0.093 |
| azonenberg-latentred-linecard | 621 | 4 | 0 | 29 | 0 | 0 | 337 | 27 | 17 | 6 | 0 | 2 | 1 | 1.388 |
| azonenberg-latentred-pdu | 46 | 0 | 3 | 8 | 0 | 0 | 16 | 3 | 0 | 3 | 0 | 0 | 0 | 0.075 |
| berkeleylab-obsidian-obsidian | 521 | 7 | 1 | 42 | 0 | 2 | 146 | 19 | 1 | 9 | 0 | 0 | 5 | 3.579 |
| bluerobotics-ping-dev-kit-pingdevkit | 452 | 8 | 1 | 39 | 0 | 1 | 77 | 44 | 0 | 9 | 0 | 4 | 3 | 1.965 |
| chipsalliance-rocket-pcb-fmc-sdram | 73 | 0 | 0 | 20 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0.336 |
| chipsalliance-rocket-pcb-fmc-usb-gpio-spi-jtag | 146 | 1 | 0 | 25 | 2 | 0 | 59 | 2 | 0 | 1 | 0 | 0 | 1 | 0.315 |
| d3a-c-biscuit-crowbar | 13 | 0 | 0 | 0 | 0 | 0 | 2 | 1 | 0 | 0 | 0 | 1 | 0 | 0.008 |
| d3a-kitspace-12v5a-breakout | 18 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0.04 |
| d3a-kitspace-gas-sensor | 15 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 1 | 0 | 0.019 |
| d3a-kitspace-hum-temp-sensor | 12 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0.016 |
| d3a-kitspace-temp-breakout | 14 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0.088 |
| d3a-marlin-neopixel-bridge-attiny85-marneo | 8 | 0 | 0 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0.022 |
| d3a-pcb-serie-led-strip | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.007 |
| d3a-starsynctrackers-reset-switch | 9 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 1 | 0 | 0.012 |
| d3a-z2amiller-sensorboard-programmer | 8 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0.012 |
| dangerousprototypes-buspirate5-hardware-6-rev2b | 227 | 0 | 1 | 58 | 3 | 1 | 26 | 38 | 0 | 3 | 0 | 1 | 1 | 0.408 |
| electron271-tuxkeychain-tuxkeychain | 56 | 0 | 0 | 9 | 0 | 1 | 33 | 8 | 0 | 3 | 0 | 0 | 0 | 0.121 |
| git4dcc-rtb-c11-c11 | 163 | 2 | 2 | 15 | 0 | 0 | 57 | 15 | 0 | 4 | 0 | 7 | 0 | 0.517 |
| hackclub-reflow-badge | 68 | 1 | 0 | 9 | 0 | 1 | 10 | 1 | 0 | 1 | 0 | 0 | 2 | 0.162 |
| kicad-demos-complex-hierarchy-complex-hierarchy | 68 | 0 | 0 | 4 | 0 | 0 | 6 | 10 | 0 | 1 | 0 | 0 | 0 | 0.09 |
| kicad-demos-ecc83-ecc83-pp-v2 | 15 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0.041 |
| kicad-demos-kit-dev-coldfire-xilinx-5213-kit-dev | 160 | 0 | 0 | 11 | 0 | 1 | 173 | 11 | 0 | 1 | 0 | 7 | 0 | 0.301 |
| kicad-demos-pic-programmer-pic-programmer | 63 | 1 | 0 | 3 | 0 | 0 | 14 | 1 | 0 | 1 | 0 | 1 | 0 | 0.11 |
| kicad-demos-sonde-xilinx-sonde-xilinx | 25 | 0 | 0 | 1 | 0 | 0 | 17 | 4 | 0 | 0 | 0 | 0 | 0 | 0.093 |
| kicad-demos-stickhub-stickhub | 94 | 0 | 0 | 7 | 0 | 1 | 31 | 2 | 0 | 0 | 0 | 1 | 0 | 0.143 |
| kicad-demos-video-video | 189 | 0 | 0 | 12 | 0 | 3 | 19 | 14 | 4 | 6 | 0 | 6 | 2 | 0.577 |
| libresolar-bms-c1-bms-c1 | 210 | 1 | 1 | 6 | 0 | 0 | 42 | 27 | 1 | 9 | 0 | 0 | 0 | 0.173 |
| olimex-dcdc-50-5-12-dcdc-50-5-12-rev-a1 | 46 | 1 | 0 | 1 | 0 | 0 | 4 | 3 | 0 | 1 | 0 | 0 | 0 | 0.061 |
| olimex-mipi-hdmi-mipi-hdmi-rev-b | 70 | 1 | 0 | 6 | 0 | 1 | 12 | 1 | 0 | 2 | 0 | 0 | 0 | 0.094 |
| pcbcorpus-0rax-esphome-xiao-base-pcb | 10 | 0 | 0 | 0 | 0 | 0 | 13 | 1 | 1 | 0 | 0 | 0 | 0 | 0.014 |
| pcbcorpus-0xjmux-esp-prog-adapter-espprog-adapte | 11 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0.027 |
| pcbcorpus-angelnu-esphome-siedle-bus | 37 | 0 | 0 | 2 | 0 | 0 | 4 | 1 | 1 | 0 | 0 | 0 | 0 | 0.03 |
| pcbcorpus-atoomnetmarc-iot12-iot12-control-board | 73 | 0 | 0 | 6 | 0 | 0 | 21 | 13 | 0 | 0 | 0 | 0 | 0 | 0.175 |
| pcbcorpus-azoninc-doorman-doorman | 44 | 1 | 0 | 2 | 0 | 0 | 14 | 2 | 1 | 1 | 0 | 0 | 0 | 0.158 |
| pcbcorpus-badjeff-paw3222-pcb-paw3222 | 7 | 0 | 0 | 2 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0.012 |
| pcbcorpus-badjeff-paw3395-pcb-paw3395 | 18 | 0 | 0 | 5 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0.029 |
| pcbcorpus-badjeff-pmw3610-pcb-pmw3610-pcb | 15 | 0 | 0 | 6 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0.017 |
| pcbcorpus-bentwire-usb-c-fusb302-pi-usb-c-fusb30 | 64 | 1 | 0 | 8 | 0 | 1 | 43 | 6 | 0 | 1 | 0 | 0 | 0 | 0.089 |
| pcbcorpus-blueokiris-ch552g-dev-board-ch552g-dev | 9 | 0 | 0 | 2 | 0 | 0 | 18 | 1 | 0 | 0 | 0 | 0 | 0 | 0.018 |
| pcbcorpus-brenocq-bldc-motor-bldcm-power | 60 | 1 | 2 | 10 | 0 | 0 | 35 | 10 | 0 | 3 | 0 | 0 | 0 | 0.056 |
| pcbcorpus-brown-studios-minuet-minuet | 103 | 3 | 0 | 8 | 0 | 0 | 51 | 1 | 1 | 3 | 0 | 0 | 0 | 0.234 |
| pcbcorpus-brown-studios-minuet-minuet-086b34 | 88 | 3 | 0 | 6 | 0 | 0 | 46 | 3 | 1 | 3 | 0 | 0 | 0 | 0.144 |
| pcbcorpus-caffeinated-labs-caffeinated-aftonspar | 37 | 1 | 3 | 2 | 0 | 0 | 10 | 3 | 1 | 4 | 0 | 0 | 0 | 0.062 |
| pcbcorpus-circuitstate-mitayi-pico-d1-mitayi-pic | 75 | 0 | 0 | 5 | 0 | 1 | 57 | 1 | 0 | 1 | 0 | 0 | 1 | 0.112 |
| pcbcorpus-diysynthmnl-eurorack-multi-saturation- | 83 | 0 | 0 | 6 | 0 | 0 | 6 | 21 | 0 | 0 | 0 | 9 | 0 | 0.17 |
| pcbcorpus-electron271-tuxkeychain-expansion | 5 | 0 | 0 | 0 | 0 | 0 | 2 | 3 | 0 | 0 | 0 | 0 | 0 | 0.026 |
| pcbcorpus-envious-data-envopenpico-envopenpico-r | 58 | 0 | 0 | 7 | 0 | 1 | 43 | 8 | 0 | 0 | 0 | 0 | 1 | 0.085 |
| pcbcorpus-flypie-ace-2019-ace3nokb | 148 | 0 | 0 | 13 | 0 | 1 | 128 | 4 | 0 | 1 | 1 | 7 | 10 | 0.476 |
| pcbcorpus-funkeleinhorn-sc14cvmdect-devboard-aud | 34 | 0 | 0 | 0 | 0 | 0 | 10 | 1 | 0 | 0 | 0 | 0 | 0 | 0.048 |
| pcbcorpus-funkeleinhorn-sc14cvmdect-devboard-sc1 | 96 | 0 | 0 | 6 | 0 | 0 | 52 | 5 | 1 | 2 | 0 | 0 | 0 | 0.09 |
| pcbcorpus-fyralabs-suzyqboard-suzyqboard | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.045 |
| pcbcorpus-goga64-ulk-ulk | 124 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.155 |
| pcbcorpus-goga64-ulk-ulk-4ead33 | 124 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.1 |
| pcbcorpus-ikajdan-reflow-hot-plate-control-board | 125 | 1 | 1 | 8 | 0 | 1 | 35 | 8 | 0 | 3 | 0 | 0 | 0 | 0.306 |
| pcbcorpus-jana-marie-analog-toolkit-analog-toolk | 85 | 0 | 0 | 5 | 0 | 0 | 37 | 10 | 0 | 1 | 0 | 1 | 0 | 0.105 |
| pcbcorpus-jangtrinh-design-os-3d-blender-desktop | 24 | 0 | 0 | 0 | 0 | 0 | 15 | 2 | 1 | 0 | 0 | 0 | 0 | 0.026 |
| pcbcorpus-jkramarz-thetick-tick | 37 | 1 | 0 | 2 | 0 | 0 | 7 | 6 | 1 | 1 | 0 | 0 | 0 | 0.757 |
| pcbcorpus-justbuchanan-oasis-ledboard | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 0 | 0.013 |
| pcbcorpus-justbuchanan-oasis-pcb | 45 | 1 | 1 | 4 | 0 | 0 | 10 | 1 | 1 | 2 | 0 | 6 | 2 | 0.074 |
| pcbcorpus-jvedder-biploar-power-supply-kicad-bip | 37 | 0 | 0 | 2 | 0 | 0 | 3 | 2 | 0 | 0 | 0 | 0 | 0 | 0.07 |
| pcbcorpus-kabukiflux-duplicanator-scart-duplicat | 42 | 0 | 0 | 0 | 0 | 0 | 7 | 2 | 0 | 1 | 0 | 0 | 0 | 0.044 |
| pcbcorpus-kabukiflux-midi4mister-midi-4-mister | 40 | 0 | 0 | 3 | 0 | 0 | 14 | 0 | 0 | 1 | 0 | 0 | 0 | 0.136 |
| pcbcorpus-kabukiflux-pi-rgb-cable-sync-mixer-rgb | 9 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0.027 |
| pcbcorpus-kampi-beelight-beelight | 25 | 0 | 0 | 3 | 0 | 0 | 4 | 0 | 1 | 0 | 0 | 0 | 0 | 0.053 |
| pcbcorpus-kkckrnz-treble-treble | 141 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 43 | 0 | 0.128 |
| pcbcorpus-koron-yuiop-yuiop29re | 123 | 0 | 0 | 5 | 1 | 0 | 21 | 0 | 0 | 0 | 0 | 0 | 5 | 0.402 |
| pcbcorpus-lambdakb-trackball-lt6c-lt6c-pcb | 19 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0.058 |
| pcbcorpus-leomanangka-esp32-4-channel-relays-esp | 63 | 0 | 0 | 4 | 0 | 0 | 7 | 0 | 1 | 1 | 0 | 0 | 0 | 0.217 |
| pcbcorpus-m1geo-pi5-pcie-pi5-pcie | 54 | 0 | 0 | 3 | 0 | 0 | 17 | 0 | 0 | 0 | 0 | 0 | 0 | 0.152 |
| pcbcorpus-mecparts-retrowifimodem-retrowifimodem | 35 | 0 | 0 | 5 | 0 | 0 | 9 | 0 | 0 | 1 | 0 | 1 | 0 | 0.098 |
| pcbcorpus-mohamedboubaker-battery-powered-stm32- | 53 | 2 | 0 | 4 | 0 | 1 | 17 | 3 | 0 | 1 | 1 | 0 | 0 | 0.097 |
| pcbcorpus-murexrobotics-electrical-esc-carrier | 49 | 0 | 0 | 0 | 0 | 0 | 111 | 0 | 0 | 0 | 0 | 1 | 0 | 0.124 |
| pcbcorpus-ojg-thatmicpre-thatmicpre-v2 | 89 | 0 | 0 | 1 | 0 | 0 | 14 | 3 | 0 | 0 | 0 | 0 | 0 | 0.127 |
| pcbcorpus-pcbcupid-kicad-7-series-schematics | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0.025 |
| pcbcorpus-pcbcupid-kicad-7-series-schematics-d1e | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0.024 |
| pcbcorpus-protolux-electronics-trellis-core-trel | 89 | 2 | 0 | 10 | 0 | 2 | 9 | 4 | 0 | 2 | 0 | 0 | 0 | 0.262 |
| pcbcorpus-ravinrabbid-doncon2040-donconio | 106 | 0 | 0 | 16 | 0 | 0 | 8 | 16 | 0 | 0 | 0 | 0 | 0 | 0.278 |
| pcbcorpus-ravinrabbid-doncon2040-donconiomini | 96 | 1 | 0 | 11 | 0 | 0 | 3 | 16 | 0 | 1 | 0 | 0 | 0 | 0.194 |
| pcbcorpus-rniwase-sdtv2csi-sdtv2csi | 67 | 0 | 0 | 7 | 0 | 1 | 9 | 11 | 0 | 2 | 0 | 0 | 0 | 0.098 |
| pcbcorpus-rniwase-tsuraragb-tgb-main | 70 | 0 | 1 | 12 | 0 | 0 | 9 | 1 | 0 | 3 | 0 | 0 | 0 | 0.203 |
| pcbcorpus-siderakb-pmw3360-pcb-pmw3360-pcb-jst | 20 | 0 | 0 | 3 | 0 | 0 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0.061 |
| pcbcorpus-siderakb-pmw3610-pcb-pmw3610-pcb | 24 | 0 | 0 | 6 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0.048 |
| pcbcorpus-stack-chan-stack-chan-m5-pantilt | 39 | 0 | 0 | 1 | 0 | 0 | 21 | 1 | 0 | 0 | 0 | 0 | 0 | 0.127 |
| pcbcorpus-sufst-pcb-16ch-sensor-hub | 173 | 0 | 1 | 7 | 0 | 1 | 42 | 49 | 0 | 1 | 0 | 0 | 0 | 0.497 |
| pcbcorpus-sufst-pcb-8ch-sensor-hub | 114 | 0 | 1 | 7 | 0 | 1 | 26 | 33 | 0 | 1 | 0 | 0 | 0 | 0.341 |
| pcbcorpus-tcsullivan-noisecard-noisecard | 32 | 1 | 0 | 3 | 0 | 0 | 3 | 2 | 0 | 0 | 1 | 0 | 0 | 0.066 |
| pcbcorpus-tjko-brickpico-brickpico | 124 | 1 | 0 | 3 | 0 | 0 | 41 | 1 | 1 | 1 | 0 | 1 | 1 | 0.358 |
| pcbcorpus-tjko-fanpico-fanpico-31b08e | 216 | 0 | 0 | 9 | 0 | 0 | 50 | 8 | 1 | 0 | 0 | 1 | 1 | 0.42 |
| pcbcorpus-tmarhguy-alu-gate-xnor-2in | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.018 |
| pcbcorpus-tmarhguy-alu-gate-xor-2in | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.021 |
| pcbcorpus-tomtor-stm32-rfm95-pcb-avr-lora | 39 | 0 | 0 | 4 | 0 | 2 | 28 | 3 | 1 | 0 | 0 | 0 | 0 | 0.035 |
| pcbcorpus-tomtor-stm32-rfm95-pcb-avr-lora-805 | 39 | 0 | 0 | 4 | 0 | 2 | 28 | 3 | 1 | 0 | 0 | 0 | 0 | 0.038 |
| pcbcorpus-tzarc-keyboards-kobold | 104 | 0 | 1 | 20 | 1 | 0 | 16 | 3 | 0 | 2 | 0 | 0 | 16 | 0.189 |
| pcbcorpus-uzixls-pc-ega-composite-daughterboard- | 51 | 0 | 0 | 3 | 0 | 0 | 12 | 2 | 0 | 3 | 0 | 0 | 0 | 0.066 |
| pcbcorpus-uzixls-pc-ega-composite-daughterboard- | 48 | 0 | 0 | 4 | 0 | 0 | 11 | 2 | 0 | 3 | 0 | 0 | 0 | 0.092 |
| pcbcorpus-vaaarad07-pcb-designs-mvcu-f407 | 114 | 0 | 0 | 14 | 0 | 1 | 36 | 7 | 1 | 1 | 0 | 0 | 2 | 0.115 |
| pcbcorpus-waterloo-rocketry-canhw-processor | 80 | 1 | 0 | 8 | 0 | 0 | 21 | 4 | 0 | 1 | 0 | 3 | 0 | 0.127 |
| pcbcorpus-wibblyghost-southerly-split-keeb-south | 87 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 28 | 0 | 0.068 |
| pcbcorpus-zhiayang-mikoto-mikoto-flashbed | 48 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 21 | 0 | 0.052 |
| pcbcorpus-zswatch-watch-devkit-hw-zswatch-watch- | 132 | 3 | 0 | 19 | 0 | 0 | 81 | 4 | 1 | 0 | 0 | 0 | 0 | 0.951 |
| piotr-binkowski-kintex-pcie-board-kintex-pcie | 166 | 2 | 0 | 14 | 0 | 0 | 18 | 9 | 0 | 3 | 0 | 0 | 4 | 0.278 |
| rapidanalysis-xerxes-xerxes | 58 | 1 | 1 | 3 | 0 | 1 | 47 | 4 | 0 | 2 | 0 | 2 | 0 | 0.198 |
| reform-reform-reform2-protected-batterypack-pcb | 38 | 0 | 0 | 0 | 0 | 0 | 5 | 12 | 0 | 0 | 0 | 4 | 0 | 0.063 |
| sparkfun-sparkfun-xrp-controller-sparkfun-xrp-co | 387 | 4 | 5 | 10 | 0 | 1 | 110 | 9 | 0 | 7 | 0 | 1 | 0 | 0.601 |
| system76-launch-launch-heavy | 73 | 0 | 0 | 10 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 10 | 0.146 |
| wntrblm-helium-board | 67 | 0 | 0 | 8 | 0 | 0 | 19 | 22 | 0 | 0 | 0 | 0 | 0 | 0.207 |
| wntrblm-micronova-board | 55 | 3 | 0 | 2 | 0 | 0 | 21 | 1 | 0 | 3 | 0 | 5 | 0 | 0.077 |

## 7. Follow-up, 2026-10-23: pin pairing, power paths, rail groups, pin types [C][I]

Same 112 boards, same eval script (extended with rail-group and power-path measures). Baselines are the runs made
with the code just before each change; "first report" is §1.

### 7.1 Decap pin pairing (cases reported by the critical router)

The human distance was used only as the label; each case was traced to the rule that produced it.

| Case (human distance) | Rule error | Fix, fixture |
|---|---|---|
| canhw-processor U4: six VDD pins -> C5/C6/C7/C8/C11 at 11.4-21.9 mm | a group with several pins on one net paired its capacitors with pins round-robin in reference order; the netlist cannot say which of six VDD pins a capacitor serves | multi-pin groups name no pin (`pairing: 'nearest_pin'`); `test_multi_pin_group_pairs_by_distance_not_by_reference_order` |
| bms-c1 U1 pin 3 -> C19 (69.6 mm), U5 pin 3 -> C36 (57.6 mm) | the ESP32 module's `3V3` pin read as a regulator output (a 'bypass' group); the buck's output filter, an exclusive owner, took a 100 nF cap because its quota had room | a `3V3` pin is a load supply unless typed power_out; exclusive owners never take ineligible caps; `test_module_3v3_pin_is_a_load_and_exclusive_owners_take_only_eligible_caps` |
| bms-c1 U2 pin 8 -> C21 (11.2 mm); noisecard MK1 pin 5 -> C8/C9 (19-21 mm) | leftover capacitors all went to the first consumer in reference order | leftovers go to the near-best owner with the fewest capacitors per pin; a pin is named only for small ceramics within quota with p >= 0.5; `test_leftover_caps_spread_by_caps_per_pin` |

| Measure | Before | After | Final (all changes) |
|---|---|---|---|
| Pin pairs stated (`pin_caps`) | 1,457 | 285 | 284 |
| Share with human distance > 10 mm | 33.2% | 11.6% | 11.6% (33 pairs on 20 boards) |
| Median pin-to-cap distance | 5.83 mm | 2.69 mm | 2.69 mm |
| Boards with any pairing > 10 mm | 55 | 20 | 20 |
| Ownership, all owners (n caps) | 73.2% (1,386) | 74.3% (1,369) | 74.7% (1,373) |
| Per-board mean | 68.8% | 69.4% | 70.5% |

The remaining far pairs are single-pin parts whose one capacitor the designer put elsewhere; three mouse-sensor
boards (PMW3610, PAW3395) hold 9 of the 33, the rest are one or two per board.

### 7.2 Final run against the first report

| Measure | First report | Final | No sheet names | Random tie order |
|---|---|---|---|---|
| Ownership, all owners | 73.1% (1,381) | **74.7%** (1,373; per board 70.5%) | 62.9% | 61.3% |
| Effective ownership (rail-group caps paired with the nearest group load) | | **76.0%** | 64.3% | 64.0% |
| Decap groups only | 74.7% (1,160) | 75.8% (1,155) | | |
| Pin pairs > 10 mm | 33.2% of 1,457 | 11.6% of 284 | 14.5% of 249 | 12.1% of 281 |
| Hot loops below the 5th percentile of random | 76.6% of 64 | **81.3%** (below 1st: 40.6%) | 73.4% | 71.9% |
| Power-path loops below the 5th percentile | | 52% of 21 (median percentile 0.035) | | |
| Crystal to IC | 4.71 mm | 4.71 mm | | |
| TVS nearer the connector | 60.2% of 266 | 59.5% of 269 | | |
| Brief runtime (2 processes, shared host) | median 0.06 s, max 1.6 s | median 0.08-0.10 s, max 1.5-3.6 s | | |

Calibration (final): p < 0.5 right 54.8% (n 529, mean p 0.24); 0.5-0.7 76.6% (239); 0.7-0.9 89.9% (197);
>= 0.9 91.8% (403). Cells: boosts 6/6, half-bridges 10/11, bucks 36/47 below the 5th percentile. The cell gain is
the capacitor donation rule (§7.6): trellis-core U2 (percentile 0.39 -> 0.03) and obsidian U10 (0.29 -> 0.03); one
regression, obsidian U11 (0.11 -> 0.53), where five bucks share six caps and nothing in the netlist says which.
Runtime is dominated by part classification (regex tables, about 70% of the slowest board); host load varied.

### 7.3 Power paths (no switching): 26 on 16 boards

| Board | Path | Class | Rails | I (basis) | P_W |
|---|---|---|---|---|---|
| latentred-pdu | U4, U5, U7 | load_switch | 12V0 -> shunt -> channel | 24 A (NCP45560 table) | 1.90 each |
| git4dcc rtb-c11 | IC6, IC8 | load_switch | Vsrc -> Vbst.0/.1 | 3 A (MAX17613 table) | 2.34 each |
| kobold | U3 (+ 50 mOhm shunt R3) | load_switch | VBUS -> RGB_PWR | 2.5 A (AP2552 table) | 0.44 |
| xerxes | U1 | load_switch | CM5_3V3 -> SD_PWR | 1.5 A (RT9742 table) | 0.16 |
| brenocq bldcm-power | U9:VIN_5V, U9:VBUS | power_mux, group U9 | -> 5V | 1.25 A (TPS2115A table) | 0.13 |
| libresolar bms-c1 | Q2-Q5 + Q6-Q9 | fet_bank, 2 stages x 4 | BAT+ -> PACK+ (gnd BAT-) | 120 A (HSOF class x 4) | 8.64 (1.08 per FET) |
| ping dev kit | Q101 | reverse_polarity | VIN -> VIN_PROTECTED | 5 A (SO-8 class) | 0.70 |
| sufst sensor hubs (2) | Q2 | reverse_polarity | +GLV -> +GLV_PROT | 0.27 A (500 mA fuse, capped by a 5 Ohm SOT-23) | 0.35 |
| sparkfun XRP | Q2, Q4 / Q6, Q8 | ideal_diode, groups or:VRAW / or:VSYS | VBATT, VUSB -> VRAW; VUSB, 5V -> VSYS | 2.5 / 0.75 / 0.75 / 2 A (fuses, connector) | 0.03-0.33 |
| sparkfun XRP | Q9 | fet_switch | VRAW -> VIN | 1 A | 0.05 |
| buspirate5 | Q402 | ideal_diode | VREG_OUT -> VREF_VOUT | 1 A | 0.05 |
| tsuraragb | Q1 | ideal_diode | VCC0 -> +5V | 1 A | 0.04 |
| obsidian | Q5 | fet_switch (U12) | VUSB -> VCC_USB | 5 A (SON class) | 0.33 |
| ikajdan reflow plate | Q2 (IRF1018E) | fet_switch, low side | heater pads J8/J9 -> GND | 24 A (TO-263, capped by 5 W) | 5.0 |
| caffeinated aftonsparv | Q1-Q3 | fet_switch, low side | LED-strip pins -> GND | 3 A (connector) | 0.27 each |
| justbuchanan oasis | Q1 | fet_switch, low side | -> GND | 2.1 A (capped) | 0.35 |

By reading, all 26 are real power paths; the class is uncertain for buspirate Q402 and tsuraragb Q1. Loop
percentiles by class (21 loops with three or more terminals): load switch 0.01, power mux 0.00, reverse polarity
0.01, FET bank 0.02, low-side and ideal-diode paths 0.14-0.15. The poor ones close on a rail capacitor the designer
placed at the rail's source (XRP Q8, kobold U3) or run through a cable connector (the LED-strip switches).
Currents are upper bounds: the belief interval is [I/3, I].

### 7.4 Rail groups: 8 on 5 boards (108 loads, 62 capacitors)

| Board | Group | Loads / caps | Allocation right | Nearest group load right |
|---|---|---|---|---|
| chipsalliance fmc-usb-gpio | rg:3P3V, rg:VADJ (TXS02612 x 8 each) | 16 / 16 | 9 | 16 |
| buspirate5 | rg:+3V3, rg:VREF_VOUT (74LVC1T45 x 8), rg:+VUSB (SK6812 x 10) | 26 / 26 | 26 | 26 |
| yuiop29re | rg:5V0 (WS2812C x 29) | 29 / 5 | 1 | 3 |
| kobold | rg:RGB_PWR (16 RGB LEDs, two footprint variants) | 16 / 5 | 2 | 4 |
| system76 launch heavy | rg:+3V6 (SK6805 x 21) | 21 / 10 | 0 | 7 |

Over the 62 capacitors: allocation 61.3%, nearest-load pairing 90.3%. Where the allocation was already right
(buspirate) the group costs nothing.

### 7.5 Pin types that contradict names

Perturbation test, [`cm_pin_type_robustness.py`](../../tools/research/physics/cm_pin_type_robustness.py) (agreement with
the unperturbed brief; 112 boards):

| Perturbation | Version | Net roles | Rails (Jaccard) | Cells | Decap groups |
|---|---|---|---|---|---|
| blank: every pin type removed | before the name-first rules | 0.993 | 0.918 | 1.0 | 0.899 |
| | final | 0.9945 | 0.927 | 1.0 | 0.931 |
| flip: supply names typed input, logic names and VIN+/IN- typed power_in | before | 0.9946 | 0.955 | 1.0 | 0.946 |
| | final | 0.9998 | 0.998 | 1.0 | 0.997 |

Flip is partly circular (it perturbs the pins whose names the rules trust); blank is the honest one. What blank
still loses: internal-regulator nodes recognized only by `power_out` (BQ76952 REG1 without a capacitor), names the
rules do not parse (`VBUS-In`), and charger pins whose direction only the type gives (VBAT, VSYS).

Held-out audit 2: three boards never opened before (selected by contradicting IC pin types, then part count), code
frozen, errors recorded before fixes.

| Board | Errors found | Pin-type related |
|---|---|---|
| sc14cvmdect devboard (DECT module breakout) | module VDDPA and VDDE wired straight to header pins were 'signal' (a 2-pin-net penalty); minor: audio outputs plain signal | VDDE is typed bidirectional, but VDDPA (typed correctly) failed the same way: topology, not type |
| sdtv2csi (ADV7280A-M, every pin typed passive) | MVDD not a supply name, so MVDD_1V8's three caps had no group; XTALP/XTALN as a diff pair; MIPI lanes without interface | MVDD: a missing type plus an unparsed name |
| trellis-core (T113-S3, two bucks) | the first buck took both VBUS caps, the second borrowed one; crystal xin/xout swapped | none (AGND typed input handled) |

Contradicting IC/module pin types on all six held-out boards (thatmicpre, bms-c1, zswatch, and the three above):
4 pins (bms-c1 SRP/SRN typed input, trellis AGND typed input, sc14 VDDE typed bidirectional); 3 handled before the
name-first rules and after; VDDE handled after the connector-fed rule. Untyped supply pins on sdtv2csi: 4 of 5
handled before, 5 of 5 after. Contradicting types are rare on held-out boards; missing types and unparsed names
(`MVDD`, `V_{DD}` markup) are the commoner failure.

### 7.6 Other bugs found and fixed (each with a regression test)

| Bug (board) | Fix |
|---|---|
| A pre-charge FET on the common-drain node split the BMS bank into two paths into that node (bms-c1) | banks whose ends are not both power nets are no chain stage |
| BAT- joined to GND by a net tie was a 'signal' net; the pack's 47 uF had no ground (bms-c1) | a negative power pole net-tied to a ground is a ground; Kelvin lines tied the same way are not |
| A flyback diode made +24 V 'derived' from the switched heater node; +24 V and VIN then named each other upstream through a fuse (ikajdan) | a diode from a low-side drain is a clamp, not a supply path; two-rail source cycles break at the connector side |
| A TO-263 low-side heater switch was dropped as a crowbar (ikajdan) | low-side switches on a connector or flyback load return are paths; the loop closes through the load's terminals and the supply cap |
| `500mA` fuse ratings unparsed; a grounded gate named the LDO on GND as controller (sufst) | mA ratings; no controller through a ground or rail gate |
| A load switch's QOD and a mux's D0 control pin tied to VIN/VOUT entered the path loop | IC paths use VIN/VOUT-named pins |
| A power mux emitted one heat source per input path (duplicate ids) | one heat source per pass element (the larger) |
| Two converters on one rail: the second borrowed the first's capacitor (trellis-core) | a converter left without a capacitor takes another converter's second one |
| `V_{DD}`, `VBUS_{OUT}` markup hid pin names (zswatch, 8 boards, 35 pins) | sub/superscript markup removed from pin functions |
| A PMIC's VSYS typed power_out became a buck input once its name was readable (nPM1300) | power_out pins on regulators, PMICs and chargers are outputs unless named VIN/IN |
| BQ76952 REG18/REG1 (internal LDO outputs) known only by type | `REGn`, `LDO`, `V*_OUT` names |
| Random tie-break ablation crashed on split-supply rails (tuple key) | fixed |
