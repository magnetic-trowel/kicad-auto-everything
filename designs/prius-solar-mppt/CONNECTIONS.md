<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Prius Prime solar MPPT: connections

Companion to [DESIGN.md](DESIGN.md). The source of truth is [design.py](design.py) (parts in [parts.py](parts.py)); `kaesynth build designs/prius-solar-mppt/design.py` checks it and writes the KiCad projects. **Every pin of every part, with its net, is in [out/netlist.json](out/netlist.json)** (KiCad round trip: identical, system and per board). This file keeps the human-facing parts: naming rules, part types with pin sources, connector pinouts, IC pin maps and the net table.

Counts: 644 part instances (main 591, batt_end 18, off-board 35), 136 distinct parts, 329 nets.

## Naming rules

- **Boards.** `main` = converter board in the cargo area; `batt_end` = battery-end board next to the HV battery; `off` = roof array and harness items (cables, tap fuse, pack-case NTCs). A net on two boards passes through a connector on each (J101/J201 roof, J301-J901 HV, J703-J903 coils and HVIL, J705/J904 lid switches, J702 IG, J706/J708 NTC pairs, J707 CAN, J902 pack tap; HV terminals are CAGE CLAMP blocks, not plugs).
- **Global nets** (no slash) cross sheets: `PVA_IN`, `VINT`, `HV_P`, `PERMIT`, ... **Local nets** are `/SHEET/NAME` in KiCad and netlist.json (`SHEET/NAME` in design.py), e.g. `/MPPT_A/SW1`, `/HVSENSE/H2_OUTP`; the same local name in `MPPT_A` and `MPPT_B` is two nets.
- **Prefixes.** `PVA_`/`PVB_` string A/B; `H1_` pack-voltage path (U401), `H2_` L3 output-voltage path (U421), `H3_` charge-current path (U441), `H4_` insulation monitor (U461), `IP*`/`IN*` IMD chain nodes; `_N` suffix = active low (`RESET_N`, `OVP_TRIP_N`) except `HV_N`, `BAT_TAP_N`, `BAT_F_N` (negative pole); `_ADC` goes to an MCU analog pin; `_LIM` to the analog limiter; `_OVP`/`_OCP` to a latching comparator.
- **Refdes blocks.** 1xx MPPT A, 2xx MPPT B, 3xx DCX, 4xx HV sense, 5xx safety, 6xx aux supplies, 7xx MCU/IO, 8xx analog limiter, 9xx battery end (461-499 IMD); `SCx0k` array columns, `D161-D164`/`D261-D264` bypass diodes, `W1-W11` cables, `S701`/`S901` lid switches, `TH1-TH4` pack-case NTCs, `F701`/`X701` IG tap.
- **Domains** (voltages in the net table are relative to the domain's 0 V): `LV` 0 V = `GND`; `CHASSIS` (boxes, screws, plated holes) at GND via NT701; `HV` 0 V = `HV_N` (floating); `PACK` floats on `HV_N` (`BAT_TAP_N` = pack -; K902 joins them). Gate and bootstrap supplies ride on their switch node (`BSTA1` on `MPPT_A/SW1`, `DCXBST` on `DCX/HB_SW`, ...); the HVIL loop `KSUP` rides on `AUX12`, relay coil low sides on `K_SUP` (`K1C`, `K2C`), the fan on `AUX12` (`FANC`); the LM74700 charge pumps ride on the string input (`IDA`, `IDB`). Under one insulation fault any `HV` or `PACK` net can be 0-420 V from chassis.
- **Pin numbers** are datasheet numbers = KiCad pad numbers. Generated symbols (LM5176, INA186, UCC27282, AMC3330, AMC3302, TPS3850, dsPIC, T301, G9KB, VS-6ESH06) carry datasheet pin names; library symbols with unnamed pins get names through `pin_names` (TLV9001, TLV9062, LM2901B, WSK2512 shunts).

## Part types and pin sources

| Refs | MPN | Maker | Symbol | Footprint | Pins / ratings source |
|---|---|---|---|---|---|
| J101, J201, J702, J705, J904 | 1757242 | Phoenix Contact | `Connector_Generic:Conn_01x02` | `Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal` | Phoenix MSTBA 2,5 header family page [S]: 12 A, 320 V (IEC, III/2), UL 300 V |
| D101, D201 | TPSMB39A | Littelfuse | `Device:D_Zener` | `Diode_SMD:D_SMB` | D_SMB pad 1 = cathode band; Device:D_Zener K = 1 |
| U101, U201 | LM74700QDBVRQ1 | Texas Instruments | `Power_Management:LM74700` | `Package_TO_SOT_SMD:SOT-23-6` | LM74700-Q1 DS SNOSD17G p.3 Fig. 5-1/Table 5-1 (DBV): 1 VCAP, 2 GND, 3 EN, 4 CATHODE, 5 GATE, 6 ANODE; matches KiCad Power_Management:LM74700 |
| Q101, Q103, Q104, Q105, Q106, Q201, ... (12) | IAUC100N10S5L040 | Infineon | `Transistor_FET:BSC040N10NS5` | `Package_TO_SOT_SMD:TDSON-8-1` | IAUC100N10S5L040 DS rev 1.0 p.1 PG-TDSON-8: S 1-3, G 4, D 5-8 + tab; KiCad BSC040N10NS5 (same package and pinout) numbers S 1,2,3, G 4, D 5 = TDSON-8-1 pads |
| D107, D207 | TPSMB43A | Littelfuse | `Device:D_Zener` | `Diode_SMD:D_SMB` | D_SMB pad 1 = cathode band; Device:D_Zener K = 1 |
| D102, D103, D104, D105, D106, D108, ... (24) | BAT46WJ,115 | Nexperia | `Diode:BAT46` | `Diode_SMD:D_SOD-323F` | KiCad Diode:BAT46 K = 1, A = 2; SOD-323F pad 1 = cathode band |
| U102, U202 | INA186A2QDBVRQ1 | Texas Instruments | `generated` | `Package_TO_SOT_SMD:SOT-23-5` | INA186-Q1 DS SBOS386B p.3 Fig. 5-2/Table 5-1 (DBV): 1 GND, 2 OUT, 3 VS, 4 IN-, 5 IN+ |
| Q102, Q202, Q701, Q702, Q703 | SMMBTA42LT1G | onsemi | `Transistor_BJT:MMBTA42` | `Package_TO_SOT_SMD:SOT-23` | KiCad Transistor_BJT:MMBTA42: 1 B, 2 E, 3 C (SOT-23) |
| U103, U203 | LM5176QPWPRQ1 | Texas Instruments | `generated` | `Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.5mm_ThermalVias` | LM5176-Q1 DS SNVSB46B p.3 Fig. 5-1 and Table 5-1 (PWP); KiCad's LM5176PWP symbol types VOSNS as an output, so this card generates its own symbol with the datasheet pin directions |
| L101, L201 | XAL1510-223MEB | Coilcraft | `Device:L` | `Inductor_SMD:L_Coilcraft_XAL1510-223` | Coilcraft XAL1510 document 947-1 [S]: 22 uH, Isat 18.7 A (30 % drop), Irms 10.5 A (40 K rise), DCR 16 mOhm max, AEC-Q200 grade 1 |
| NT101, NT201, NT701 | NetTie | - | `Device:NetTie_2` | `NetTie:NetTie-2_SMD_Pad0.5mm` |  |
| U104, U204, U402, U422, U442, U462 | TLV9001QDBVRQ1 | Texas Instruments | `Amplifier_Operational:TLV9061xDBV` | `Package_TO_SOT_SMD:SOT-23-5` | TLV900x-Q1 DS SBOS980G p.3 Fig. 5-1/Table 5-1 (DBV): 1 OUT, 2 V-, 3 IN+, 4 IN-, 5 V+; same pinout as the KiCad TLV9061xDBV symbol |
| L301 | XAL7070-561MEB | Coilcraft | `Device:L` | `Inductor_SMD:L_Coilcraft_XAL7070-XXX` | Coilcraft XAL7070 family [unverified: values to be read from document 1074 before layout]: 0.56 uH +/-20 %, Isat ~30 A, Irms ~20 A, AEC-Q200 grade 1 |
| U301 | UCC27282QDRCRQ1 | Texas Instruments | `generated` | `Package_SON:VSON-10-1EP_3x3mm_P0.5mm_EP1.65x2.4mm` | UCC27282-Q1 DS SLUSDN5D p.3 Fig. 5-1/Table 5-1 (DRC): 1 VDD, 2 NC, 3 HB, 4 HO, 5 HS, 6 EN, 7 HI, 8 LI, 9 VSS, 10 LO, thermal pad to VSS |
| T301 | T301-ETD39-DCX22 (custom) | magnetics vendor to specification (DESIGN.md 7.3) | `generated` | `custom:ETD39_20pin_DCX` | our pin assignment on the TDK ETD 39 20-pin coil former: 1/2 primary start, 3/4 primary end, 11 secondary start, 20 secondary end; unused positions have no pad [I] |
| D301, D302, D303, D304, D601, D602, ... (10) | VS-6ESH06HM3/86A | Vishay | `generated` | `Package_TO_SOT_SMD:TO-277A` | VS-6ESH06HM3 DS doc 94985 p.1 package drawing: two anode leads, cathode = heatsink tab; pads per KiCad TO-277A (1, 2 leads, 3 tab) |
| J301, J901 | 236-303 | WAGO | `Connector_Generic:Conn_01x03` | `TerminalBlock_WAGO:TerminalBlock_WAGO_236-303_1x03_P10.00mm_45Degree` | WAGO 236 series PCB terminal block, 10/10.16 mm pitch, CAGE CLAMP (opened with an operating tool), 0.08-2.5 mm2, 24 A [S: Buerklin/RS listings]; rated voltage (IEC, III/2) 630 V [unverified: WAGO data sheet to be read before layout, V-5] |
| RT301, RT302 | NTCG163JF103FTDS | TDK | `Device:Thermistor_NTC` | `Resistor_SMD:R_0603_1608Metric` | TDK NTCG series [unverified]: 10 kOhm 1 %, B25/85 3435 K, AEC-Q200 |
| U401, U421, U461 | AMC3330QDWERQ1 | Texas Instruments | `generated` | `Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm` | AMC3330-Q1 DS SBASA35B p.3 Fig. 4-1/Table 4-1: 1 DCDC_OUT, 2 DCDC_HGND, 3 HLDO_IN, 4 NC, 5 HLDO_OUT, 6 INP, 7 INN, 8 HGND, 9 GND, 10 OUTN, 11 OUTP, 12 VDD, 13 LDO_OUT, 14 DIAG (open drain), 15 DCDC_GND, 16 DCDC_IN. KiCad's AMC3330 symbol types DIAG as push-pul |
| U441 | AMC3302QDWERQ1 | Texas Instruments | `generated` | `Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm` | AMC3302-Q1 DS SBASA84A p.3 Fig. 5-1/Table 5-1: same 16-pin assignment as AMC3330-Q1 (DIAG open drain) |
| Q461 | BSS123Q-7 | Diodes Incorporated | `Transistor_FET:BSS123` | `Package_TO_SOT_SMD:SOT-23` | DS43455 p.1 SOT23 top view: G 1, S 2, D 3; KiCad Transistor_FET:BSS123 G 1, S 2, D 3 |
| U501, U801 | LM4040QBIM3X2.5/NOPB | Texas Instruments | `Reference_Voltage:LM4040DBZ-2.5` | `Package_TO_SOT_SMD:SOT-23` | LM4040-N-Q1 DS SNOS633N p.3 Fig. 4-1 (DBZ): 1 +, 2 -, 3 NC (* = no connect or tie to pin 2) |
| U802, U803 | TLV9062QDRQ1 | Texas Instruments | `Amplifier_Operational:TLV9062xD` | `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` | TLV906x-Q1 DS SBOS966H Pin Configuration (D, SOIC-8): 1 OUT A, 2 IN A-, 3 IN A+, 4 V-, 5 IN B+, 6 IN B-, 7 OUT B, 8 V+; matches KiCad TLV9062xD |
| U502, U506, U507, U508 | LM2901BQDRQ1 | Texas Instruments | `Comparator:LM2901` | `Package_SO:SOIC-14_3.9x8.7mm_P1.27mm` | LM2901B-Q1 DS SLCS142H p.3 Fig. 4-1 (D): 1 1OUT, 2 2OUT, 3 VCC, 4 2IN-, 5 2IN+, 6 1IN-, 7 1IN+, 8 3IN-, 9 3IN+, 10 4IN-, 11 4IN+, 12 GND, 13 4OUT, 14 3OUT |
| U503 | SN74LVC2G74QDCURQ1 | Texas Instruments | `74xGxx:74LVC2G74` | `Package_SO:VSSOP-8_2.3x2mm_P0.5mm` | SN74LVC2G74-Q1 DS SCES563C p.1 DCU pinout: 1 CLK, 2 D, 3 ~Q, 4 GND, 5 Q, 6 ~CLR, 7 ~PRE, 8 VCC |
| U504 | TPS3850G33QDRCRQ1 | Texas Instruments | `generated` | `Package_SON:VSON-10-1EP_3x3mm_P0.5mm_EP1.65x2.4mm` | TPS3850-Q1 DS SBVS264B p.3 Fig. 5-1/Table 5-1 (DRC): 1 VDD, 2 CWD, 3 SET0, 4 CRST, 5 GND, 6 SET1, 7 WDI, 8 WDO, 9 RESET, 10 SENSE, pad GND |
| U505 | TPL7407LAQPWRQ1 | Texas Instruments | `Transistor_Array:TPL7407LAPW` | `Package_SO:TSSOP-16_4.4x5mm_P0.65mm` | TPL7407LA-Q1 DS SLRS074 p.3 PW pinout: 1-7 IN1-IN7, 8 GND, 9 COM, 10-16 OUT7-OUT1; matches KiCad Transistor_Array:TPL7407LAPW |
| D504 | APT1608SGC | Kingbright | `Device:LED` | `LED_SMD:LED_0603_1608Metric` | APT1608SGC DS p.1: pin 1 cathode |
| D505 | APT1608SURCK | Kingbright | `Device:LED` | `LED_SMD:LED_0603_1608Metric` | pin 1 cathode [S] |
| U601, U602 | LM5164QDDARQ1 | Texas Instruments | `Regulator_Switching:LM5164DDA` | `Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm_ThermalVias` | LM5164-Q1 DS SNVSB51C p.3 Fig. 4-1/Table 4-1: 1 GND, 2 VIN, 3 EN/UVLO, 4 RON, 5 FB, 6 PGOOD, 7 BST, 8 SW, 9 EP; matches KiCad LM5164DDA |
| L601 | MSS1210-104KED | Coilcraft | `Device:L` | `Inductor_SMD:L_Coilcraft_MSS1210-XXX` | Coilcraft MSS1210 data sheet [S]: 100 uH, Isat 3.1 A (10 % drop), Irms 2.4 A, DCR 0.125 Ohm max |
| L602 | MSS1048-333MLB | Coilcraft | `Device:L` | `Inductor_SMD:L_Coilcraft_MSS1048-XXX` | Coilcraft MSS1048 data sheet [S]: 33 uH, Isat 1.66 A (10 % drop), DCR 68 mOhm max |
| U701 | DSPIC33CK256MP505-E/PT | Microchip | `generated` | `Package_QFP:TQFP-48_7x7mm_P0.5mm` | dsPIC33CK256MP508 family DS70005349K p.8 Table 6 (48-pin TQFP): pin names abbreviated to the port and the function used (21 OSCI/CLKI/AN5/RP32/RB0, 22 OSCO/CLKO/AN6/RP33/RB1, 26 PGD2/OA2IN-/AN8/RP35/RB3, 33 PGD3/RP37/SDA2/RB5, 34 PGC3/RP38/RB6, 35 TDO/AN2/RP39 |
| Y701 | NX3225GA 20.000000MHz STD-CRA-1 | NDK | `Device:Crystal_GND24` | `Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm` | same sheet, terminal land connections (top view): #1 and #3 crystal, #2 and #4 not connected ('better to connect with a GND'); KiCad Crystal_GND24 1/3 crystal, 2/4 G; Crystal_SMD_3225-4Pin pads numbered the same way round [S] |
| J701 | 61300611121 | Wurth Elektronik | `Connector_Generic:Conn_01x06` | `Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical` | Wurth WR-PHD 2.54 mm header [S]: 3 A |
| J703, J706, J707, J708, J903 | 1757255 | Phoenix Contact | `Connector_Generic:Conn_01x03` | `Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_3-G-5,08_1x03_P5.08mm_Horizontal` | Phoenix MSTBA 2,5 header family page [S]: 12 A, 320 V (IEC, III/2), UL 300 V |
| D701 | SBAS21LT1G | onsemi | `Diode:BAS21` | `Package_TO_SOT_SMD:SOT-23` | KiCad Diode:BAS21: 1 A, 2 NC, 3 K (SOT-23 single diode) |
| U702 | SN65HVD230QDRQ1 | Texas Instruments | `Interface_CAN_LIN:SN65HVD230` | `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` | SN65HVD230Q-Q1 DS SGLS398A p.1 D package: 1 D, 2 GND, 3 VCC, 4 R, 5 Vref, 6 CANL, 7 CANH, 8 RS |
| U703 | 25LC256-E/SN | Microchip | `Memory_EEPROM:25LCxxx` | `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` | Microchip DS20005715A pin function table: CS, SO, WP, VSS, SI, SCK, HOLD, VCC in the standard SPI-EEPROM order 1-8 (KiCad 25LCxxx) [S: the read copy shows the MF package of the same die] |
| J704 | 43650-0215 | Molex | `Connector_Generic:Conn_01x02` | `Connector_Molex:Molex_Micro-Fit_3.0_43650-0215_1x02_P3.00mm_Vertical` | Molex Micro-Fit 3.0 series [S]: 5 A, 250 V |
| TP701, TP702, TP703, TP704, TP705, TP706 | TP | - | `Connector:TestPoint` | `TestPoint:TestPoint_Pad_D1.5mm` |  |
| H701, H702, H703, H704 | MountingHole | - | `Mechanical:MountingHole_Pad` | `MountingHole:MountingHole_3.2mm_M3_Pad_Via` |  |
| H705, H706, H901, H902, H903, H904 | MountingHole | - | `Mechanical:MountingHole` | `MountingHole:MountingHole_3.2mm_M3` |  |
| J902 | 236-302 | WAGO | `Connector_Generic:Conn_01x02` | `TerminalBlock_WAGO:TerminalBlock_WAGO_236-302_1x02_P10.00mm_45Degree` | WAGO 236 series PCB terminal block, 10/10.16 mm pitch, CAGE CLAMP (opened with an operating tool), 0.08-2.5 mm2, 24 A [S: Buerklin/RS listings]; rated voltage (IEC, III/2) 630 V [unverified: WAGO data sheet to be read before layout, V-5] |
| F901, F902 | EVM10-5-2P | Eaton Bussmann | `Device:Fuse` | `custom:Eaton_EVM10-2P` | ELX1304 p.2 '2P: 2 pin PCB terminal' drawing; one symbol pin per end cap, two pads each (custom footprint) |
| K901, K902 | G9KB-1A DC12 | Omron | `generated` | `custom:Omron_G9KB-1A` | Omron G9KB Cat. No. K340-E1-06 p.3 'Terminal Arrangement/Internal Connections (BOTTOM VIEW)': coil 1-2 (no coil polarity), contact 3-4 (double break, bidirectional) |
| SC101, SC102, SC103, SC104, SC201, SC202, SC203, SC204 | C60 bin H (Gen II) | Maxeon (SunPower) | `Device:Solar_Cells` | `(off-board)` | SunPower C60 solar cell data sheet (bins G-J) [P]: 125 x 125 mm, Pmp 3.34-3.42 W, Vmp 0.574-0.582 V, Imp 5.83-5.93 A, Voc 0.682-0.687 V, Isc 6.24-6.28 A, -1.8 mV/K, -0.32 %/K; 'positive ground' note |
| D161, D162, D163, D164, D261, D262, D263, D264 | V10P45-M3/86A | Vishay | `Device:D_Schottky` | `(off-board)` | Device:D_Schottky K = 1, A = 2 |
| W1, W2 | 2-core 2.5 mm2 FLRY-B, 4 m | - | `Connector_Generic:Conn_02x02_Odd_Even` | `(off-board)` | harness convention of this design: odd pin = conductor at the board end, even pin = the same conductor at the far end |
| W3 | 3-core screened HV cable 2 x 2.5 mm2 + 1 x 0.75 mm2, orange, >= 600 V, 2 m | - | `Connector_Generic:Conn_02x03_Odd_Even` | `(off-board)` | harness convention of this design: odd pin = conductor at the board end, even pin = the same conductor at the far end |
| W4 | 3-core 0.75 mm2 FLRY-B, 2 m | - | `Connector_Generic:Conn_02x03_Odd_Even` | `(off-board)` | harness convention of this design: odd pin = conductor at the board end, even pin = the same conductor at the far end |
| W5, W11 | screened 3-core 0.35 mm2 (2 NTC + ground) | - | `Connector_Generic:Conn_02x03_Odd_Even` | `(off-board)` | harness convention of this design: odd pin = conductor at the board end, even pin = the same conductor at the far end |
| W9, W10 | 2-core 0.5 mm2 FLRY-B, 0.3 m | - | `Connector_Generic:Conn_02x02_Odd_Even` | `(off-board)` | harness convention of this design: odd pin = conductor at the board end, even pin = the same conductor at the far end |
| S701, S901 | lid interlock | - | `Switch:SW_SPST` | `(off-board)` | Switch:SW_SPST A/B, no polarity |
| W6 | OBD-II Y cable, CAN-H/CAN-L twisted pair + signal ground, 0.35 mm2 | - | `Connector_Generic:Conn_02x03_Odd_Even` | `(off-board)` | harness convention of this design: odd pin = conductor at the board end, even pin = the same conductor at the far end |
| W7 | 2-core 0.5 mm2 FLRY-B | - | `Connector_Generic:Conn_02x02_Odd_Even` | `(off-board)` | harness convention of this design: odd pin = conductor at the board end, even pin = the same conductor at the far end |
| W8 | 2 x 2.5 mm2 double-insulated HV leads >= 600 V with M6 ring terminals, <= 0.3 m | - | `Connector_Generic:Conn_02x02_Odd_Even` | `(off-board)` | harness convention of this design: odd pin = conductor at the board end, even pin = the same conductor at the far end |
| F701 | 0287001.PXCN | Littelfuse | `Device:Fuse` | `(off-board)` | Littelfuse ATO 287 series [S]: 1 A, 32 VDC, 1000 A interrupting |
| X701 | add-a-fuse (ATO) | - | `Connector_Generic:Conn_01x01` | `(off-board)` | single blade contact into the car's fuse socket |
| TH1, TH2, TH3, TH4 | 10k | - | `Device:Thermistor_NTC` | `(off-board)` | generic lug-mount NTC (e.g. Vishay NTCALUG series) [unverified] |

Resistors: Panasonic ERJ-3EKF (0603 1 % 0.1 W 75 V), ERJ-3RQF (< 10 Ohm), ERJ-8ENF (1206 1 % 0.25 W 200 V); precision Vishay TNPW0603/TNPW1206 ...BEEA (0.1 %, 25 ppm/K, 100/200 V). Capacitors: Murata GCM / TDK CGA AEC-Q200 MLCC, Panasonic EEH-ZA hybrid polymer. Values and MPNs per instance: [out/bom.csv](out/bom.csv).

## Connectors and harness interfaces

- **J101** (main, 1757242): 1 = PVA_IN, 2 = GND
- **J201** (main, 1757242): 1 = PVB_IN, 2 = GND
- **J301** (main, 236-303): 1 = HV_P, 2 = HV_N, 3 = PACK_SNS
- **J701** (main, 61300611121): 1 = MCLR_N, 2 = +3V3, 3 = GND, 4 = PGD, 5 = PGC, 6 = NC
- **J702** (main, 1757242): 1 = IGN_IN, 2 = GND
- **J703** (main, 1757255): 1 = HVIL_A, 2 = K1_COIL_N, 3 = K2_COIL_N
- **J704** (main, 43650-0215): 1 = AUX12, 2 = FAN_N
- **J705** (main, 1757242): 1 = AUX12, 2 = HVIL_A
- **J706** (main, 1757255): 1 = NTC_P1, 2 = NTC_P2, 3 = GND
- **J707** (main, 1757255): 1 = CAN_H, 2 = CAN_L, 3 = GND
- **J708** (main, 1757255): 1 = NTC_P3, 2 = NTC_P4, 3 = GND
- **J901** (batt_end, 236-303): 1 = HV_P, 2 = HV_N, 3 = PACK_SNS
- **J902** (batt_end, 236-302): 1 = BAT_TAP_P, 2 = BAT_TAP_N
- **J903** (batt_end, 1757255): 1 = HVIL_A, 2 = K1_COIL_N, 3 = K2_COIL_N
- **J904** (batt_end, 1757242): 1 = HVIL_A, 2 = K_SUP

Cables (off-board, odd pin = board end, even pin = far end of the same core): W1/W2 PV strings (2 x 2.5 mm2), W3 HV (HV_P, HV_N, PACK_SNS; screened, >= 600 V), W4 coils (HVIL_A, K1_COIL_N, K2_COIL_N), W5 hardware NTC pair (TH1/TH2), W11 firmware NTC pair (TH3/TH4), W9/W10 lid-switch leads (S701: AUX12-HVIL_A; S901: HVIL_A-K_SUP), W6 OBD-II CAN (CAN_H pin 6, CAN_L pin 14, signal ground pin 5), W7 IG (IGN_IN, GND), W8 pack tap leads (BAT_TAP_P/N, <= 0.3 m).

## IC and relay pin maps

**U103** LM5176QPWPRQ1 - MPPT A controller (U203 identical with MPPT_B nets)

| Pin | Name | Net |
|---|---|---|
| 1 | EN/UVLO | /MPPT_A/EN |
| 2 | VIN | /MPPT_A/VINF |
| 3 | VISNS | /MPPT_A/VISNS |
| 4 | MODE | /MPPT_A/MODE |
| 5 | DITH | /MPPT_A/DITH |
| 6 | RT/SYNC | /MPPT_A/RT |
| 7 | SLOPE | /MPPT_A/SLOPE |
| 8 | SS | /MPPT_A/SS |
| 9 | COMP | /MPPT_A/COMP |
| 10 | AGND | /MPPT_A/AGND |
| 11 | FB | /MPPT_A/FB |
| 12 | VOSNS | VINT |
| 13 | ISNS- | /MPPT_A/ISNS_N |
| 14 | ISNS+ | /MPPT_A/ISNS_P |
| 15 | CSG | /MPPT_A/CSG |
| 16 | CS | /MPPT_A/CS |
| 17 | PGOOD | NC |
| 18 | SW2 | /MPPT_A/SW2 |
| 19 | HDRV2 | /MPPT_A/HD2 |
| 20 | BOOT2 | /MPPT_A/BT2 |
| 21 | LDRV2 | /MPPT_A/LD2 |
| 22 | PGND | GND |
| 23 | VCC | /MPPT_A/VCC |
| 24 | BIAS | /MPPT_A/BIAS |
| 25 | LDRV1 | /MPPT_A/LD1 |
| 26 | BOOT1 | /MPPT_A/BT1 |
| 27 | HDRV1 | /MPPT_A/HD1 |
| 28 | SW1 | /MPPT_A/SW1 |
| 29 | PAD | /MPPT_A/AGND |

**U101** LM74700-Q1 - ideal diode A

| Pin | Name | Net |
|---|---|---|
| 1 | VCAP | /MPPT_A/VCAP |
| 2 | GND | GND |
| 3 | EN | PVA_IN |
| 4 | CATHODE | PVA_P |
| 5 | GATE | /MPPT_A/IDG |
| 6 | ANODE | PVA_IN |

**U301** UCC27282QDRCRQ1 - half-bridge driver

| Pin | Name | Net |
|---|---|---|
| 1 | VDD | AUX12 |
| 2 | NC | NC |
| 3 | HB | /DCX/DCX_HB |
| 4 | HO | /DCX/HO |
| 5 | HS | /DCX/HB_SW |
| 6 | EN | PERMIT |
| 7 | HI | /DCX/HI_F |
| 8 | LI | /DCX/LI_F |
| 9 | VSS | GND |
| 10 | LO | /DCX/LO |
| 11 | PAD | GND |

**T301** T301-ETD39-DCX22 (custom) - DCX transformer

| Pin | Name | Net |
|---|---|---|
| 1 | P_START | /DCX/HB_LR |
| 2 | P_START | /DCX/HB_LR |
| 3 | P_END | /DCX/MID |
| 4 | P_END | /DCX/MID |
| 11 | S_START | /DCX/T1_S1 |
| 20 | S_END | /DCX/T1_S2 |

**U401** AMC3330QDWERQ1 - pack-voltage isolated amp

| Pin | Name | Net |
|---|---|---|
| 1 | DCDC_OUT | /HVSENSE/H1_DCDC |
| 2 | DCDC_HGND | HV_N |
| 3 | HLDO_IN | /HVSENSE/H1_DCDC |
| 4 | NC | NC |
| 5 | HLDO_OUT | /HVSENSE/H1_HLDO |
| 6 | INP | /HVSENSE/HVS1_INP |
| 7 | INN | HV_N |
| 8 | HGND | HV_N |
| 9 | GND | GND |
| 10 | OUTN | /HVSENSE/H1_OUTN |
| 11 | OUTP | /HVSENSE/H1_OUTP |
| 12 | VDD | +3V3 |
| 13 | LDO_OUT | /HVSENSE/H1_LDO |
| 14 | DIAG | PERMIT |
| 15 | DCDC_GND | GND |
| 16 | DCDC_IN | /HVSENSE/H1_LDO |

**U421** AMC3330QDWERQ1 - L3 output-voltage isolated amp

| Pin | Name | Net |
|---|---|---|
| 1 | DCDC_OUT | /HVSENSE/H2_DCDC |
| 2 | DCDC_HGND | HV_N |
| 3 | HLDO_IN | /HVSENSE/H2_DCDC |
| 4 | NC | NC |
| 5 | HLDO_OUT | /HVSENSE/H2_HLDO |
| 6 | INP | /HVSENSE/HVS2_INP |
| 7 | INN | HV_N |
| 8 | HGND | HV_N |
| 9 | GND | GND |
| 10 | OUTN | /HVSENSE/H2_OUTN |
| 11 | OUTP | /HVSENSE/H2_OUTP |
| 12 | VDD | +3V3 |
| 13 | LDO_OUT | /HVSENSE/H2_LDO |
| 14 | DIAG | PERMIT |
| 15 | DCDC_GND | GND |
| 16 | DCDC_IN | /HVSENSE/H2_LDO |

**U441** AMC3302QDWERQ1 - charge-current isolated amp

| Pin | Name | Net |
|---|---|---|
| 1 | DCDC_OUT | /HVSENSE/H3_DCDC |
| 2 | DCDC_HGND | HV_RTN |
| 3 | HLDO_IN | /HVSENSE/H3_DCDC |
| 4 | NC | NC |
| 5 | HLDO_OUT | /HVSENSE/H3_HLDO |
| 6 | INP | /HVSENSE/H3_INP |
| 7 | INN | /HVSENSE/H3_INN |
| 8 | HGND | HV_RTN |
| 9 | GND | GND |
| 10 | OUTN | /HVSENSE/H3_OUTN |
| 11 | OUTP | /HVSENSE/H3_OUTP |
| 12 | VDD | +3V3 |
| 13 | LDO_OUT | /HVSENSE/H3_LDO |
| 14 | DIAG | PERMIT |
| 15 | DCDC_GND | GND |
| 16 | DCDC_IN | /HVSENSE/H3_LDO |

**U802** TLV9062-Q1 - CV/CC limiter

| Pin | Name | Net |
|---|---|---|
| 1 | OUTA | /LIMIT/CV_OUT |
| 2 | INA- | /LIMIT/CV_N |
| 3 | INA+ | HV_V_LIM |
| 4 | V- | GND |
| 5 | INB+ | I_HV_LIM |
| 6 | INB- | /LIMIT/CC_N |
| 7 | OUTB | /LIMIT/CC_OUT |
| 8 | V+ | +3V3 |

**U502** LM2901B-Q1 - comparators: L3, L3b, T301 OTP, pack OTP 1

| Pin | Name | Net |
|---|---|---|
| 1 | 1OUT | OVP_TRIP_N |
| 2 | 2OUT | OVP_TRIP_N |
| 3 | VCC | AUX12 |
| 4 | 2IN- | /SAFETY/VINT_OVP |
| 5 | 2IN+ | VTH2V0 |
| 6 | 1IN- | HV_V_OVP |
| 7 | 1IN+ | VTH2V0 |
| 8 | 3IN- | /SAFETY/VTH_OT1 |
| 9 | 3IN+ | NTC_T1 |
| 10 | 4IN- | VTH_OTP |
| 11 | 4IN+ | NTC_P1 |
| 12 | GND | GND |
| 13 | 4OUT | PERMIT |
| 14 | 3OUT | PERMIT |

**U506** LM2901B-Q1 - comparators: OC latch, pack OTP 2

| Pin | Name | Net |
|---|---|---|
| 1 | 1OUT | OVP_TRIP_N |
| 2 | 2OUT | PERMIT |
| 3 | VCC | AUX12 |
| 4 | 2IN- | VTH_OTP |
| 5 | 2IN+ | NTC_P2 |
| 6 | 1IN- | I_HV_OCP |
| 7 | 1IN+ | VTH_OC |
| 8 | 3IN- | ONT_H |
| 9 | 3IN+ | VTH_ONT |
| 10 | 4IN- | ONT_L |
| 11 | 4IN+ | VTH_ONT |
| 12 | GND | GND |
| 13 | 4OUT | OVP_TRIP_N |
| 14 | 3OUT | OVP_TRIP_N |

**U503** SN74LVC2G74-Q1 - trip latch

| Pin | Name | Net |
|---|---|---|
| 1 | C | GND |
| 2 | D | GND |
| 3 | ~{Q} | LATCH_QN |
| 4 | GND | GND |
| 5 | Q | LATCH_Q |
| 6 | ~{CLR} | /SAFETY/CLR_N |
| 7 | ~{PRE} | OVP_TRIP_N |
| 8 | VCC | LATCH_VCC |

**U504** TPS3850G33QDRCRQ1 - supervisor/watchdog

| Pin | Name | Net |
|---|---|---|
| 1 | VDD | +3V3 |
| 2 | CWD | /SAFETY/TPS_CWD |
| 3 | SET0 | GND |
| 4 | CRST | NC |
| 5 | GND | GND |
| 6 | SET1 | GND |
| 7 | WDI | WDI |
| 8 | WDO | /SAFETY/WDO_N |
| 9 | RESET | RESET_N |
| 10 | SENSE | +3V3 |
| 11 | PAD | GND |

**U505** TPL7407LA-Q1 - low-side drivers

| Pin | Name | Net |
|---|---|---|
| 1 | IN1 | K_IN |
| 2 | IN2 | K_IN |
| 3 | IN3 | FAN_PWM |
| 4 | IN4 | PERMIT |
| 5 | IN5 | LATCH_Q |
| 6 | IN6 | GND |
| 7 | IN7 | GND |
| 8 | GND | GND |
| 9 | COM | AUX12 |
| 10 | OUT7 | NC |
| 11 | OUT6 | NC |
| 12 | OUT5 | /SAFETY/LED_FLT_K |
| 13 | OUT4 | /SAFETY/LED_OK_K |
| 14 | OUT3 | FAN_N |
| 15 | OUT2 | K2_COIL_N |
| 16 | OUT1 | K1_COIL_N |

**U601** LM5164-Q1 - AUX12 buck

| Pin | Name | Net |
|---|---|---|
| 1 | GND | GND |
| 2 | VIN | AUX_IN |
| 3 | EN/UVLO | /AUX/AUX_EN |
| 4 | RON | /AUX/AUX12_RON |
| 5 | FB | /AUX/AUX12_FB |
| 6 | PGOOD | NC |
| 7 | BST | /AUX/AUX12_BST |
| 8 | SW | /AUX/AUX12_SW |
| 9 | EP | GND |

**U602** LM5164-Q1 - +3V3 buck

| Pin | Name | Net |
|---|---|---|
| 1 | GND | GND |
| 2 | VIN | AUX12 |
| 3 | EN/UVLO | /AUX/V33_EN |
| 4 | RON | /AUX/V33_RON |
| 5 | FB | /AUX/V33_FB |
| 6 | PGOOD | NC |
| 7 | BST | /AUX/V33_BST |
| 8 | SW | /AUX/V33_SW |
| 9 | EP | GND |

**U701** DSPIC33CK256MP505-E/PT - MCU

| Pin | Name | Net |
|---|---|---|
| 1 | RB14/PWM1H | DCX_HI |
| 2 | RB15/PWM1L | DCX_LI |
| 3 | RC12/PWM8H | MPPT_A_PWM |
| 4 | RC13/PWM8L | MPPT_B_PWM |
| 5 | MCLR | MCLR_N |
| 6 | RD13/RP77 | FAN_PWM |
| 7 | RC0/AN12 | NTC_P1 |
| 8 | RA0/AN0 | HV_V_ADC |
| 9 | RA1/ANA1 | HV_V2_ADC |
| 10 | RA2/AN9 | I_HV_ADC |
| 11 | RA3/AN3 | PVA_VDIV |
| 12 | RA4/AN4 | PVA_I_ADC |
| 13 | AVDD | +3V3A |
| 14 | AVSS | GND |
| 15 | RC1/AN13 | PVB_VDIV |
| 16 | RC2/AN14 | PVB_I_ADC |
| 17 | RC6/AN17 | NTC_P2 |
| 18 | VDD | +3V3 |
| 19 | VSS | GND |
| 20 | RC3/AN15 | VINT_DIV |
| 21 | OSCI/RB0 | /MCU/XTAL_I |
| 22 | OSCO/RB1 | /MCU/XTAL_O |
| 23 | RD10/AN18 | NTC_P4 |
| 24 | RC7/AN16 | AUX12_DIV |
| 25 | RB2/AN1 | LIM_ADC |
| 26 | RB3/AN8 | NTC_HS |
| 27 | RB4/PGC2 | READY_N |
| 28 | RC8/SCK2 | EE_SCK |
| 29 | RC9/SDI2 | EE_SO |
| 30 | RD8/SDO2 | EE_SI |
| 31 | VSS | GND |
| 32 | VDD | +3V3 |
| 33 | RB5/PGD3 | PGD |
| 34 | RB6/PGC3 | PGC |
| 35 | RB7/AN2 | NTC_P3 |
| 36 | RB8/AN10 | IMD_ADC |
| 37 | RB9/RP41 | EE_CS_N |
| 38 | RC4/RP52 | CAN_TX |
| 39 | RC5/RP53 | CAN_RX |
| 40 | RC10/PWM7H | RELAY_REQ |
| 41 | RC11/PWM7L | CAN_EN |
| 42 | VSS | GND |
| 43 | VDD | +3V3 |
| 44 | RD1/RP65 | MCU_RUN |
| 45 | RB10/RP42 | WDI |
| 46 | RB11/RP43 | LATCH_SNS |
| 47 | RB12/RP44 | PERMIT_SNS |
| 48 | RB13/RP45 | IMD_SW |

**U702** SN65HVD230Q-Q1 - CAN transceiver

| Pin | Name | Net |
|---|---|---|
| 1 | D | CAN_TX |
| 2 | GND | GND |
| 3 | VCC | +3V3 |
| 4 | R | CAN_RX |
| 5 | Vref | NC |
| 6 | CANL | CAN_L |
| 7 | CANH | CAN_H |
| 8 | Rs | /MCU/CAN_RS |

**U703** 25LC256 - log EEPROM

| Pin | Name | Net |
|---|---|---|
| 1 | ~{CS} | EE_CS_N |
| 2 | MISO | EE_SO |
| 3 | ~{WP} | +3V3 |
| 4 | GND | GND |
| 5 | MOSI | EE_SI |
| 6 | SCK | EE_SCK |
| 7 | ~{HOLD} | +3V3 |
| 8 | VCC | +3V3 |

**K901** G9KB-1A DC12 - + pole relay

| Pin | Name | Net |
|---|---|---|
| 1 | COIL_1 | K_SUP |
| 2 | COIL_2 | K1_COIL_N |
| 3 | C3 | /BATEND/BAT_F_P |
| 4 | C4 | /BATEND/BE_DK |

**K902** G9KB-1A DC12 - - pole relay

| Pin | Name | Net |
|---|---|---|
| 1 | COIL_1 | K_SUP |
| 2 | COIL_2 | K2_COIL_N |
| 3 | C3 | /BATEND/BAT_F_N |
| 4 | C4 | HV_N |

**D901** VS-6ESH06HM3/86A - blocking diode

| Pin | Name | Net |
|---|---|---|
| 1 | A | HV_P |
| 2 | A | HV_P |
| 3 | K | /BATEND/BE_DK |

**F901** 5A - pack + fuse

| Pin | Name | Net |
|---|---|---|
| 1 | - | BAT_TAP_P |
| 2 | - | /BATEND/BAT_F_P |

**F902** 5A - pack - fuse

| Pin | Name | Net |
|---|---|---|
| 1 | - | BAT_TAP_N |
| 2 | - | /BATEND/BAT_F_N |

## Net table

V range is relative to the domain's 0 V (see naming rules); I max is the design envelope used by the current checks. Pins = number of pins on the net (list in out/netlist.json).

| Net | Domain | V range (V) | I max (A) | Kind | Boards | Pins | Note |
|---|---|---|---|---|---|---|---|
| `+3V3` | LV | 0..3.4 | 0.35 | power | main | 66 |  |
| `+3V3A` | LV | 0..3.4 | 0.02 | power | main | 7 | MCU AVDD |
| `/ARRAY/PVA_C1` | LV | 0..33 | 7.5 | power | off | 4 |  |
| `/ARRAY/PVA_C2` | LV | 0..33 | 7.5 | power | off | 4 |  |
| `/ARRAY/PVA_C3` | LV | 0..33 | 7.5 | power | off | 4 |  |
| `/ARRAY/PVB_C1` | LV | 0..33 | 7.5 | power | off | 4 |  |
| `/ARRAY/PVB_C2` | LV | 0..33 | 7.5 | power | off | 4 |  |
| `/ARRAY/PVB_C3` | LV | 0..33 | 7.5 | power | off | 4 |  |
| `/AUX/AUX12_BST` | AUXBST | 0..5 | - | signal | main | 2 |  |
| `/AUX/AUX12_FB` | LV | 0..1.5 | - | analog | main | 4 |  |
| `/AUX/AUX12_RA` | LV | 0..12.5 | - | analog | main | 3 |  |
| `/AUX/AUX12_RON` | LV | 0..3 | - | analog | main | 2 |  |
| `/AUX/AUX12_SW` | LV | -1.5..38 | 1.0 | switching | main | 4 |  |
| `/AUX/AUX_EN` | LV | 0..3.5 | - | signal | main | 3 |  |
| `/AUX/V33_BST` | V33BST | 0..5 | - | signal | main | 2 |  |
| `/AUX/V33_EN` | LV | 0..2.5 | - | signal | main | 3 |  |
| `/AUX/V33_FB` | LV | 0..1.5 | - | analog | main | 4 |  |
| `/AUX/V33_RA` | LV | 0..3.4 | - | analog | main | 3 |  |
| `/AUX/V33_RON` | LV | 0..3 | - | analog | main | 2 |  |
| `/AUX/V33_SW` | LV | -1.5..12.5 | 0.5 | switching | main | 4 |  |
| `/BATEND/BAT_F_N` | PACK | 0 | 0.85 | hv | batt_end | 2 |  |
| `/BATEND/BAT_F_P` | PACK | 0..399 | 0.85 | hv | batt_end | 2 |  |
| `/BATEND/BE_DK` | HV | 0..420 | 0.85 | hv | batt_end | 3 |  |
| `/BATEND/SNS_A` | HV | 0..420 | - | hv | batt_end | 2 |  |
| `/BATEND/SNS_B` | HV | 0..420 | - | hv | batt_end | 2 |  |
| `/DCX/DCX_CSK` | LV | -0.1..0.1 | - | sense | main | 2 |  |
| `/DCX/DCX_HB` | DCXBST | 0..12.5 | - | signal | main | 2 |  |
| `/DCX/DCX_RS` | LV | -0.1..0.1 | 8 | power | main | 4 |  |
| `/DCX/HB_LR` | LV | -6..44 | 10 | switching | main | 3 |  |
| `/DCX/HB_SW` | LV | -1..38 | 8 | switching | main | 7 |  |
| `/DCX/HI_F` | LV | 0..3.4 | - | signal | main | 5 |  |
| `/DCX/HO` | DCXBST | 0..12.5 | - | signal | main | 2 |  |
| `/DCX/HO_G` | DCXBST | 0..12.5 | - | signal | main | 2 |  |
| `/DCX/LI_F` | LV | 0..3.4 | - | signal | main | 5 |  |
| `/DCX/LO` | LV | 0..12.5 | - | signal | main | 2 |  |
| `/DCX/LO_G` | LV | 0..12.5 | - | signal | main | 2 |  |
| `/DCX/MID` | LV | -2..40 | 8 | switching | main | 34 |  |
| `/DCX/T1_S1` | HV | -1.5..421.5 | 0.85 | switching | main | 5 |  |
| `/DCX/T1_S2` | HV | -1.5..421.5 | 0.85 | switching | main | 5 |  |
| `/DCX/T1_SNB` | HV | 0..420 | - | hv | main | 2 |  |
| `/HVSENSE/H1_DA_N` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/HVSENSE/H1_DA_OUT` | LV | 0..3.3 | - | analog | main | 4 |  |
| `/HVSENSE/H1_DA_P` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/HVSENSE/H1_DCDC` | HV | 0..4.5 | - | power | main | 5 |  |
| `/HVSENSE/H1_HLDO` | HV | 0..3.6 | - | power | main | 3 |  |
| `/HVSENSE/H1_LDO` | LV | 0..3.6 | - | power | main | 3 |  |
| `/HVSENSE/H1_OUTN` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/HVSENSE/H1_OUTP` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/HVSENSE/H2_DA_N` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/HVSENSE/H2_DA_OUT` | LV | 0..3.3 | - | analog | main | 5 |  |
| `/HVSENSE/H2_DA_P` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/HVSENSE/H2_DCDC` | HV | 0..4.5 | - | power | main | 5 |  |
| `/HVSENSE/H2_HLDO` | HV | 0..3.6 | - | power | main | 3 |  |
| `/HVSENSE/H2_LDO` | LV | 0..3.6 | - | power | main | 3 |  |
| `/HVSENSE/H2_OUTN` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/HVSENSE/H2_OUTP` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/HVSENSE/H3_DA_N` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/HVSENSE/H3_DA_OUT` | LV | 0..3.3 | - | analog | main | 5 |  |
| `/HVSENSE/H3_DA_P` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/HVSENSE/H3_DCDC` | HV | 0..4.5 | - | power | main | 5 |  |
| `/HVSENSE/H3_HLDO` | HV | 0..3.6 | - | power | main | 3 |  |
| `/HVSENSE/H3_INN` | HV | -0.1..0.1 | - | sense | main | 3 |  |
| `/HVSENSE/H3_INP` | HV | -0.1..0.1 | - | sense | main | 3 |  |
| `/HVSENSE/H3_LDO` | LV | 0..3.6 | - | power | main | 3 |  |
| `/HVSENSE/H3_OUTN` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/HVSENSE/H3_OUTP` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/HVSENSE/HVS1_INP` | HV | 0..1 | - | analog | main | 4 |  |
| `/HVSENSE/HVS2_INP` | HV | 0..1 | - | analog | main | 4 |  |
| `/HVSENSE/I_SN` | HV | -0.1..0.1 | - | sense | main | 2 |  |
| `/HVSENSE/I_SP` | HV | -0.1..0.1 | - | sense | main | 2 |  |
| `/HVSENSE/S1A` | HV | 0..420 | - | hv | main | 2 |  |
| `/HVSENSE/S1B` | HV | 0..420 | - | hv | main | 2 |  |
| `/HVSENSE/S2A` | HV | 0..420 | - | hv | main | 2 |  |
| `/HVSENSE/S2B` | HV | 0..420 | - | hv | main | 2 |  |
| `/HVSENSE/S2C` | HV | 0..420 | - | hv | main | 2 |  |
| `/HVSENSE/S2D` | HV | 0..420 | - | hv | main | 2 |  |
| `/HVSENSE/S2E` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/H4_DA_N` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/IMD/H4_DA_OUT` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/IMD/H4_DA_P` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/IMD/H4_DCDC` | HV | 0..4.5 | - | power | main | 5 |  |
| `/IMD/H4_HLDO` | HV | 0..3.6 | - | power | main | 3 |  |
| `/IMD/H4_LDO` | LV | 0..3.6 | - | power | main | 3 |  |
| `/IMD/H4_OUTN` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/IMD/H4_OUTP` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/IMD/IMD_G` | LV | 0..3.4 | - | signal | main | 3 |  |
| `/IMD/IMD_REF` | LV | 0..2.6 | - | analog | main | 4 |  |
| `/IMD/IN1` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IN2` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IN3` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IN4` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IN5` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IN6` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IN7` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IN8` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IN9` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IN10` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IP1` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IP2` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IP3` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IP4` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IP5` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IP6` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IP7` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IP8` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/IP9` | HV | 0..420 | - | hv | main | 2 |  |
| `/IMD/NTAP` | HV | -1..1 | - | analog | main | 4 |  |
| `/IMD/PSW` | CHASSIS | 0..40 | - | pe | main | 3 |  |
| `/LIMIT/CC_N` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/LIMIT/CC_OUT` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/LIMIT/CC_RZ` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/LIMIT/CV2_N` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/LIMIT/CV2_OUT` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/LIMIT/CV2_RZ` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/LIMIT/CV_N` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/LIMIT/CV_OUT` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/LIMIT/CV_RZ` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/LIMIT/U803B_FB` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/LIMIT/VREF_CC` | LV | 0..2.6 | - | analog | main | 4 |  |
| `/LIMIT/VREF_CV` | LV | 0..2.6 | - | analog | main | 5 |  |
| `/LIMIT/VREF_CV2` | LV | 0..2.6 | - | analog | main | 4 |  |
| `/LIMIT/VREF_LIM` | LV | 0..2.6 | - | analog | main | 8 |  |
| `/MCU/CAN_EN_B` | LV | 0..0.8 | - | signal | main | 2 |  |
| `/MCU/CAN_GE` | LV | 0..3.4 | - | signal | main | 2 |  |
| `/MCU/CAN_RS` | LV | 0..3.4 | - | signal | main | 3 |  |
| `/MCU/IGN_D` | LV | 0..112 | - | signal | main | 3 |  |
| `/MCU/IG_GB` | LV | 0..0.8 | - | signal | main | 3 |  |
| `/MCU/READY_B` | LV | 0..0.8 | - | signal | main | 3 |  |
| `/MCU/XTAL_I` | LV | 0..3.4 | - | clock | main | 3 |  |
| `/MCU/XTAL_O` | LV | 0..3.4 | - | clock | main | 3 |  |
| `/MPPT_A/AGND` | LV | 0 | - | ground | main | 14 |  |
| `/MPPT_A/BIAS` | LV | 0..12.5 | 0.04 | power | main | 3 |  |
| `/MPPT_A/BT1` | BSTA1 | 0..7.6 | - | signal | main | 3 |  |
| `/MPPT_A/BT2` | BSTA2 | 0..7.6 | - | signal | main | 3 |  |
| `/MPPT_A/COMP` | LV | 0..3 | - | analog | main | 3 |  |
| `/MPPT_A/COMP_RC` | LV | 0..3 | - | analog | main | 2 |  |
| `/MPPT_A/CS` | LV | -0.2..0.2 | - | sense | main | 3 |  |
| `/MPPT_A/CSG` | LV | -0.2..0.2 | - | sense | main | 3 |  |
| `/MPPT_A/CSG_K` | LV | -0.2..0.2 | - | sense | main | 2 |  |
| `/MPPT_A/CS_K` | LV | -0.2..0.2 | - | sense | main | 2 |  |
| `/MPPT_A/DITH` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_A/EN` | LV | 0..3.5 | - | signal | main | 7 |  |
| `/MPPT_A/FB` | LV | 0..1 | - | analog | main | 3 |  |
| `/MPPT_A/HD1` | BSTA1 | 0..7.6 | - | signal | main | 2 |  |
| `/MPPT_A/HD1_G` | BSTA1 | 0..7.6 | - | signal | main | 2 |  |
| `/MPPT_A/HD2` | BSTA2 | 0..7.6 | - | signal | main | 2 |  |
| `/MPPT_A/HD2_G` | BSTA2 | 0..7.6 | - | signal | main | 2 |  |
| `/MPPT_A/IDG` | IDA | 0..13.9 | - | signal | main | 2 |  |
| `/MPPT_A/INA_N` | LV | 0..35 | - | sense | main | 2 |  |
| `/MPPT_A/INA_P` | LV | 0..35 | - | sense | main | 2 |  |
| `/MPPT_A/INT_N` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/MPPT_A/ISK_N` | LV | 0..35 | - | sense | main | 3 |  |
| `/MPPT_A/ISK_P` | LV | 0..35 | - | sense | main | 3 |  |
| `/MPPT_A/ISNS_N` | LV | 0..35 | - | sense | main | 4 |  |
| `/MPPT_A/ISNS_P` | LV | 0..35 | - | sense | main | 3 |  |
| `/MPPT_A/I_RAW` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_A/LD1` | LV | 0..8 | - | signal | main | 2 |  |
| `/MPPT_A/LD1_G` | LV | 0..8 | - | signal | main | 2 |  |
| `/MPPT_A/LD2` | LV | 0..8 | - | signal | main | 2 |  |
| `/MPPT_A/LD2_G` | LV | 0..8 | - | signal | main | 2 |  |
| `/MPPT_A/MODE` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_A/MPPT_OUT` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/MPPT_A/PI` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_A/RT` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_A/SINK_B` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_A/SINK_E` | LV | 0..2.7 | - | analog | main | 2 |  |
| `/MPPT_A/SLOPE` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_A/SRC` | LV | -0.1..0.2 | 7.5 | power | main | 7 |  |
| `/MPPT_A/SS` | LV | 0..1.25 | - | analog | main | 2 |  |
| `/MPPT_A/SW1` | LV | -1..35 | 7.5 | switching | main | 7 |  |
| `/MPPT_A/SW2` | LV | -1..38 | 7.5 | switching | main | 7 |  |
| `/MPPT_A/VCAP` | IDA | 0..13.9 | - | signal | main | 2 |  |
| `/MPPT_A/VCC` | LV | 0..7.6 | 0.065 | power | main | 4 |  |
| `/MPPT_A/VIN` | LV | 0..35 | 7.5 | power | main | 9 |  |
| `/MPPT_A/VINF` | LV | 0..35 | 0.07 | power | main | 3 |  |
| `/MPPT_A/VISNS` | LV | 0..35 | - | sense | main | 2 |  |
| `/MPPT_A/VSET` | LV | 0..3.3 | - | analog | main | 4 |  |
| `/MPPT_A/VSET1` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/MPPT_B/AGND` | LV | 0 | - | ground | main | 14 |  |
| `/MPPT_B/BIAS` | LV | 0..12.5 | 0.04 | power | main | 3 |  |
| `/MPPT_B/BT1` | BSTB1 | 0..7.6 | - | signal | main | 3 |  |
| `/MPPT_B/BT2` | BSTB2 | 0..7.6 | - | signal | main | 3 |  |
| `/MPPT_B/COMP` | LV | 0..3 | - | analog | main | 3 |  |
| `/MPPT_B/COMP_RC` | LV | 0..3 | - | analog | main | 2 |  |
| `/MPPT_B/CS` | LV | -0.2..0.2 | - | sense | main | 3 |  |
| `/MPPT_B/CSG` | LV | -0.2..0.2 | - | sense | main | 3 |  |
| `/MPPT_B/CSG_K` | LV | -0.2..0.2 | - | sense | main | 2 |  |
| `/MPPT_B/CS_K` | LV | -0.2..0.2 | - | sense | main | 2 |  |
| `/MPPT_B/DITH` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_B/EN` | LV | 0..3.5 | - | signal | main | 7 |  |
| `/MPPT_B/FB` | LV | 0..1 | - | analog | main | 3 |  |
| `/MPPT_B/HD1` | BSTB1 | 0..7.6 | - | signal | main | 2 |  |
| `/MPPT_B/HD1_G` | BSTB1 | 0..7.6 | - | signal | main | 2 |  |
| `/MPPT_B/HD2` | BSTB2 | 0..7.6 | - | signal | main | 2 |  |
| `/MPPT_B/HD2_G` | BSTB2 | 0..7.6 | - | signal | main | 2 |  |
| `/MPPT_B/IDG` | IDB | 0..13.9 | - | signal | main | 2 |  |
| `/MPPT_B/INA_N` | LV | 0..35 | - | sense | main | 2 |  |
| `/MPPT_B/INA_P` | LV | 0..35 | - | sense | main | 2 |  |
| `/MPPT_B/INT_N` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/MPPT_B/ISK_N` | LV | 0..35 | - | sense | main | 3 |  |
| `/MPPT_B/ISK_P` | LV | 0..35 | - | sense | main | 3 |  |
| `/MPPT_B/ISNS_N` | LV | 0..35 | - | sense | main | 4 |  |
| `/MPPT_B/ISNS_P` | LV | 0..35 | - | sense | main | 3 |  |
| `/MPPT_B/I_RAW` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_B/LD1` | LV | 0..8 | - | signal | main | 2 |  |
| `/MPPT_B/LD1_G` | LV | 0..8 | - | signal | main | 2 |  |
| `/MPPT_B/LD2` | LV | 0..8 | - | signal | main | 2 |  |
| `/MPPT_B/LD2_G` | LV | 0..8 | - | signal | main | 2 |  |
| `/MPPT_B/MODE` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_B/MPPT_OUT` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/MPPT_B/PI` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_B/RT` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_B/SINK_B` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_B/SINK_E` | LV | 0..2.7 | - | analog | main | 2 |  |
| `/MPPT_B/SLOPE` | LV | 0..3.3 | - | analog | main | 2 |  |
| `/MPPT_B/SRC` | LV | -0.1..0.2 | 7.5 | power | main | 7 |  |
| `/MPPT_B/SS` | LV | 0..1.25 | - | analog | main | 2 |  |
| `/MPPT_B/SW1` | LV | -1..35 | 7.5 | switching | main | 7 |  |
| `/MPPT_B/SW2` | LV | -1..38 | 7.5 | switching | main | 7 |  |
| `/MPPT_B/VCAP` | IDB | 0..13.9 | - | signal | main | 2 |  |
| `/MPPT_B/VCC` | LV | 0..7.6 | 0.065 | power | main | 4 |  |
| `/MPPT_B/VIN` | LV | 0..35 | 7.5 | power | main | 9 |  |
| `/MPPT_B/VINF` | LV | 0..35 | 0.07 | power | main | 3 |  |
| `/MPPT_B/VISNS` | LV | 0..35 | - | sense | main | 2 |  |
| `/MPPT_B/VSET` | LV | 0..3.3 | - | analog | main | 4 |  |
| `/MPPT_B/VSET1` | LV | 0..3.3 | - | analog | main | 3 |  |
| `/SAFETY/CLR_N` | LV | 0..3.4 | - | signal | main | 4 |  |
| `/SAFETY/LED_FLT_A` | LV | 0..12.5 | - | signal | main | 2 |  |
| `/SAFETY/LED_FLT_K` | LV | 0..12.5 | - | signal | main | 2 |  |
| `/SAFETY/LED_OK_A` | LV | 0..12.5 | - | signal | main | 2 |  |
| `/SAFETY/LED_OK_K` | LV | 0..12.5 | - | signal | main | 2 |  |
| `/SAFETY/TPS_CWD` | LV | 0..3.4 | - | signal | main | 2 |  |
| `/SAFETY/VINT_OVP` | LV | 0..2.2 | - | analog | main | 4 |  |
| `/SAFETY/VTH_OT1` | LV | 0..2.5 | - | analog | main | 3 |  |
| `/SAFETY/WDO_N` | LV | 0..3.4 | - | signal | main | 2 |  |
| `AUX12` | LV | 0..12.5 | 0.6 | power | main, off | 38 | gate drive, relays, comparators, references |
| `AUX12_DIV` | LV | 0..3.3 | - | analog | main | 4 |  |
| `AUX_IN` | LV | 0..38 | 0.6 | power | main | 8 | OR of PV A, PV B and VINT |
| `AUX_PG` | LV | 0..3.4 | - | signal | main | 4 |  |
| `AUX_PGS` | LV | 0..3.3 | - | analog | main | 5 |  |
| `BAT_TAP_N` | PACK | 0 | 0.85 | hv | batt_end, off | 4 | Prime pack - (cell side of SMRG) |
| `BAT_TAP_P` | PACK | 0..399 | 0.85 | hv | batt_end, off | 4 | pack + (cell side of SMRB) |
| `BURST_N` | LV | 0..12.5 | - | signal | main | 4 | low = limiter at full cut: both LM5176 disabled |
| `CAN_EN` | LV | 0..3.4 | - | signal | main | 2 |  |
| `CAN_H` | LV | -2..7 | - | diff | main, off | 4 | OBD-II pin 6 (no termination here) |
| `CAN_L` | LV | -2..7 | - | diff | main, off | 4 | OBD-II pin 14 |
| `CAN_RX` | LV | 0..3.4 | - | signal | main | 2 |  |
| `CAN_TX` | LV | 0..3.4 | - | signal | main | 2 |  |
| `CHASSIS` | CHASSIS | 0 | 16 | pe | main | 8 | enclosures, screws, plated holes H701-H704, thermal pedestal |
| `DCX_CS` | LV | 0..3.3 | - | analog | main | 3 |  |
| `DCX_HI` | LV | 0..3.4 | - | signal | main | 2 |  |
| `DCX_LI` | LV | 0..3.4 | - | signal | main | 2 |  |
| `EE_CS_N` | LV | 0..3.4 | - | signal | main | 3 |  |
| `EE_SCK` | LV | 0..3.4 | - | signal | main | 2 |  |
| `EE_SI` | LV | 0..3.4 | - | signal | main | 2 |  |
| `EE_SO` | LV | 0..3.4 | - | signal | main | 2 |  |
| `FAN_N` | FANC | -12.5..0.7 | 0.3 | power | main | 2 |  |
| `FAN_PWM` | LV | 0..3.4 | - | signal | main | 2 |  |
| `GND` | LV | 0 | 16 | ground | main, off | 282 | PV-, PGND, signal ground; bonded to CHASSIS by NT701 at the main box |
| `HVIL_A` | KSUP | -12.5..0 | 0.5 | power | batt_end, main, off | 12 | AUX12 after the main-box lid switch S701 |
| `HV_N` | HV | 0 | 0.85 | hv | batt_end, main, off | 36 | converter output -, cable core 2, to K902 |
| `HV_P` | HV | 0..420 | 0.85 | hv | batt_end, main, off | 18 | converter output +, cable core 1 |
| `HV_RTN` | HV | -0.07..0.07 | 0.85 | hv | main | 20 | rectifier return; HV_N - I x 0.1 Ohm |
| `HV_V2_ADC` | LV | 0..3.3 | - | analog | main | 3 |  |
| `HV_V2_LIM` | LV | 0..3.3 | - | analog | main | 3 |  |
| `HV_V_ADC` | LV | 0..3.3 | - | analog | main | 3 |  |
| `HV_V_LIM` | LV | 0..3.3 | - | analog | main | 3 |  |
| `HV_V_OVP` | LV | 0..3.3 | - | analog | main | 3 |  |
| `IGN_CAR` | LV | -150..112 | 0.01 | signal | off | 2 | car IG2-switched fuse socket |
| `IGN_IN` | LV | -150..112 | 0.01 | signal | main, off | 5 | IG feed after the 1 A tap fuse |
| `IMD_ADC` | LV | 0..3.3 | - | analog | main | 3 |  |
| `IMD_SW` | LV | 0..3.4 | - | signal | main | 2 |  |
| `I_HV_ADC` | LV | 0..3.3 | - | analog | main | 3 |  |
| `I_HV_LIM` | LV | 0..3.3 | - | analog | main | 3 |  |
| `I_HV_OCP` | LV | 0..3.3 | - | analog | main | 3 |  |
| `K1_COIL_N` | K1C | -12.5..0.7 | 0.3 | power | batt_end, main, off | 8 |  |
| `K2_COIL_N` | K2C | -12.5..0.7 | 0.3 | power | batt_end, main, off | 8 |  |
| `K_IN` | LV | 0..3.4 | - | signal | main | 6 |  |
| `K_SUP` | KSUP | -12.5..0 | 0.5 | power | batt_end, off | 8 | relay-coil supply after both lid switches (HVIL) |
| `LATCH_Q` | LV | 0..3.4 | - | signal | main | 3 |  |
| `LATCH_QN` | LV | 0..3.4 | - | signal | main | 3 |  |
| `LATCH_SNS` | LV | 0..3.4 | - | signal | main | 2 |  |
| `LATCH_VCC` | LV | 0..3.4 | 0.01 | power | main | 8 | trip-latch supply held up by supercap C521 |
| `LIM` | LV | 0..3.3 | - | analog | main | 9 |  |
| `LIM_ADC` | LV | 0..3.3 | - | analog | main | 3 |  |
| `MCLR_N` | LV | 0..3.4 | - | signal | main | 5 |  |
| `MCU_RUN` | LV | 0..3.4 | - | signal | main | 3 |  |
| `MPPT_A_PWM` | LV | 0..3.3 | - | signal | main | 3 | MCU setpoint PWM; default high = zero power |
| `MPPT_B_PWM` | LV | 0..3.3 | - | signal | main | 3 | MCU setpoint PWM; default high = zero power |
| `NTC_HS` | LV | 0..3.3 | - | analog | main | 4 |  |
| `NTC_P1` | LV | 0..3.3 | - | analog | main, off | 10 | hardware-OTP pack-case NTC via J706 |
| `NTC_P2` | LV | 0..3.3 | - | analog | main, off | 10 | hardware-OTP pack-case NTC via J706 |
| `NTC_P3` | LV | 0..3.3 | - | analog | main, off | 7 |  |
| `NTC_P4` | LV | 0..3.3 | - | analog | main, off | 7 |  |
| `NTC_T1` | LV | 0..3.3 | - | analog | main | 5 |  |
| `ONT_H` | LV | 0..3.3 | - | analog | main | 4 |  |
| `ONT_L` | LV | 0..3.3 | - | analog | main | 4 |  |
| `OVP_TRIP_N` | LV | 0..3.4 | - | signal | main | 9 |  |
| `PACK_SNS` | HV | 0..420 | 0.001 | hv | batt_end, main, off | 6 | pack + through 3 MOhm at the battery end; cable core 3 |
| `PERMIT` | LV | 0..3.4 | - | signal | main | 23 |  |
| `PERMIT_SNS` | LV | 0..3.4 | - | signal | main | 2 |  |
| `PGC` | LV | 0..3.4 | - | signal | main | 2 |  |
| `PGD` | LV | 0..3.4 | - | signal | main | 2 |  |
| `PVA_IN` | LV | -33..33 | 7.5 | power | main, off | 12 | string A + at J101 |
| `PVA_I_ADC` | LV | 0..3.3 | - | analog | main | 3 | PV current 0.25 V/A |
| `PVA_OVS` | LV | 0..3.3 | - | analog | main | 4 | PV node / 17 to the back-feed comparator |
| `PVA_OV_N` | LV | 0..12.5 | - | signal | main | 3 | low = PV node above 34 V: stage disabled |
| `PVA_P` | LV | 0..35 | 7.5 | power | main | 8 | string A after the ideal diode; back-feed bounded at 34 V by U507 (M1), TVS above 40.9 V |
| `PVA_VDIV` | LV | 0..3.3 | - | analog | main | 5 | PV voltage / 12 to MCU and the PV loop |
| `PVB_IN` | LV | -33..33 | 7.5 | power | main, off | 12 | string B + at J201 |
| `PVB_I_ADC` | LV | 0..3.3 | - | analog | main | 3 | PV current 0.25 V/A |
| `PVB_OVS` | LV | 0..3.3 | - | analog | main | 4 | PV node / 17 to the back-feed comparator |
| `PVB_OV_N` | LV | 0..12.5 | - | signal | main | 3 | low = PV node above 34 V: stage disabled |
| `PVB_P` | LV | 0..35 | 7.5 | power | main | 8 | string B after the ideal diode; back-feed bounded at 34 V by U507 (M1), TVS above 40.9 V |
| `PVB_VDIV` | LV | 0..3.3 | - | analog | main | 5 | PV voltage / 12 to MCU and the PV loop |
| `READY_N` | LV | 0..3.4 | - | signal | main | 4 |  |
| `RELAY_REQ` | LV | 0..3.4 | - | signal | main | 2 |  |
| `RESET_N` | LV | 0..3.4 | - | signal | main | 3 |  |
| `VINT` | LV | 0..38 | 8 | power | main | 46 | intermediate bus 26-36 V running; LM5176 ceiling 35.4 V |
| `VINT_DIV` | LV | 0..3.3 | - | analog | main | 4 |  |
| `VREF2V5` | LV | 0..3.3 | - | analog | main | 15 |  |
| `VTH2V0` | LV | 0..3.3 | - | analog | main | 9 |  |
| `VTH_BURST` | LV | 0..3.3 | - | analog | main | 4 |  |
| `VTH_DOC` | LV | 0..3.3 | - | analog | main | 4 |  |
| `VTH_OC` | LV | 0..3.3 | - | analog | main | 4 |  |
| `VTH_ONT` | LV | 0..3.3 | - | analog | main | 5 |  |
| `VTH_OPEN` | LV | 0..3.3 | - | analog | main | 6 |  |
| `VTH_OTP` | LV | 0..3.3 | - | analog | main | 4 |  |
| `WDI` | LV | 0..3.4 | - | signal | main | 2 |  |

