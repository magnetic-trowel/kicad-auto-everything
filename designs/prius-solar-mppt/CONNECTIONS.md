<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Prius solar MPPT: connections (netlist)

Companion to [DESIGN.md](DESIGN.md). Every part instance, every pin by number and datasheet name, and the net it connects to. Generated from one structured list so the pin tables and the net table agree; the generator is not committed (it was a scratch tool), this file is the source of truth for encoding into `kaesynth`.

## Conventions

- **Boards.** `MB` = main converter board (cargo area). `BE` = battery-end board (next to the traction battery). Nets with the same name on both boards are the same conductor through a harness: `HV_P`, `HV_N` (orange HV cable J301<->J901) and `AUX12`, `K1_COIL_N`, `K2_COIL_N`, `NTC_PACK`, `GND` (LV harness J703<->J903). The array harness (roof) lands on J101/J201.
- **Pin numbers** are the datasheet numbers (cited per part type below) and equal the KiCad footprint pad numbers, except where a note says the footprint merges pins (PG-TDSON-8 drain pins 5-8 + tab = pad 5; TO-277A anodes = pads 1, 2, cathode tab = pad 3).
- **NC** = no connection (pad present, no copper attached). Exposed pads are listed as their own pin.
- **Domains.** `LV` = all circuits referenced to GND, which is bonded to the vehicle chassis at H701-H704 (PV string, VINT, AUX, logic; <= 60 V DC, ISO 6469-3 class A). `HV` = floating traction-battery domain referenced to HV_N (class B). The only LV<->HV crossings are T301, U401, U421 (reinforced) and the relay coils of K901/K902.
- **Variants.** `-N` (NiMH pack, Prius Two) and `-L` (Li-ion pack, other 2017 trims) differ only in R114, R214, R429, R431, R504 (marked VARIANT). Default values below are `-N`.
- **Evidence tags**: [P] read in the primary datasheet, [S] distributor/secondary or vendor page, [unverified] not read; [I] our inference.

## Part types and pin-number sources

| Refs | MPN | Mfr | KiCad symbol | KiCad footprint | Pin source |
|---|---|---|---|---|---|
| J101, J201, J702, J904 (4) | Phoenix 1757242 (MSTBA 2,5/2-G-5,08) + plug 1757019 (MSTB 2,5/2-ST-5,08) | Phoenix Contact | `Connector_Generic:Conn_01x02` | `Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal` | Phoenix MSTB 2,5 series [S]; item numbers [unverified] |
| D101, D201 (2) | TPSMB39A | Littelfuse | `Device:D_Zener (used as unidirectional TVS)` | `Diode_SMD:D_SMB` | Littelfuse TPSMB series DS [unverified]: VR 33.3 V, VBR 37.1 V min, VC 53.9 V; AEC-Q101 [S] |
| U101, U201 (2) | LM74700QDBVRQ1 | TI | `Power_Management:LM74700` | `Package_TO_SOT_SMD:SOT-23-6` | LM74700-Q1 DS SNOSD17G, Fig. 5-1 / Table 5-1 (DBV) [P] |
| Q101, Q103, Q104, Q105, Q106, Q201, Q203, Q204, Q205, Q206, Q301, Q302 (12) | IAUC100N10S5L040 | Infineon | `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)` | `Package_TO_SOT_SMD:TDSON-8-1` | IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S] |
| R101, R201 (2) | WSK2512R0050FEA | Vishay | `Device:R_Shunt` | `Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm` | Vishay WSK2512 DS doc 30108 (1 W, 5-200 mOhm, 4-terminal) [S]; pads per KiCad footprint |
| U102, U202 (2) | INA186A2QDBVRQ1 | TI | `custom (kae:INA186_DBV)` | `Package_TO_SOT_SMD:SOT-23-5` | INA186-Q1 DS SBOS386B, Fig. 5-2 / Table 5-1 (DBV) [P] |
| Q102, Q202, Q701 (3) | SMMBTA42LT1G | onsemi | `Transistor_BJT:MMBTA42` | `Package_TO_SOT_SMD:SOT-23` | onsemi MMBTA42 DS (300 V NPN, S-prefix AEC-Q101) [unverified]; KiCad Q_NPN_BEC |
| U103, U203 (2) | LM5176QPWPRQ1 | TI | `Regulator_Switching:LM5176PWP` | `Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.5mm_ThermalVias` | LM5176-Q1 DS SNVSB46B, Fig. 5-1 / Table 5-1 [P] |
| D102, D103, D104, D202, D203, D204, D501, D502, D503 (9) | BAT46WJ,115 | Nexperia | `Diode:BAT46` | `Diode_SMD:D_SOD-323F` | Nexperia BAT46WJ DS (SOD323F, 100 V, AEC-Q101) [unverified] |
| R116, R216 (2) | WSK2512R0100FEA | Vishay | `Device:R_Shunt` | `Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm` | Vishay WSK2512 DS doc 30108 [S] |
| L101, L201 (2) | XAL1510-223MEB | Coilcraft | `Device:L` | `Inductor_SMD:L_Coilcraft_XAL1510-223` | Coilcraft XAL1510 DS doc 947-1 (22 uH, Isat 18.7 A, Irms 10.5 A, DCR 16 mOhm max) [S] |
| NT101, NT201 (2) | (PCB feature) | - | `Device:NetTie_2` | `NetTie:NetTie-2_SMD_Pad0.5mm` | star-point tie, no BOM item |
| U104, U204, U402, U422 (4) | TLV9001QDBVRQ1 | TI | `Amplifier_Operational:TLV9061xDBV (pin-compatible)` | `Package_TO_SOT_SMD:SOT-23-5` | TLV900x-Q1 DS SBOS980G, Fig. 5-1 / Table 5-1 (DBV) [P] |
| U301 (1) | UCC27282QDRCRQ1 | TI | `custom (kae:UCC27282_DRC)` | `Package_SON:VSON-10-1EP_3x3mm_P0.5mm_EP1.65x2.4mm` | UCC27282-Q1 DS SLUSDN5D, Fig. 5-1 / Table 5-1 (DRC) [P] |
| T301 (1) | custom: TDK EPCOS ETD 39 core set N97, gapped for Lm=40 uH; 20-pin coil former; Np=6 (litz), Ns=66 (TIW) | magnetics vendor to spec | `custom (kae:T_ETD39_DCX)` | `custom (kae:ETD39_20pin_DCX; pad grid per TDK ETD 39 coil-former drawing; unused pins have no pad)` | design spec in DESIGN.md §7.3 [I]; pin assignment is ours (custom part) |
| D301, D302, D303, D304, D601, D602, D603, D901 (8) | VS-6ESH06HM3/86A | Vishay | `custom (kae:D_TO277A: 1=A,2=A,3=K)` | `Package_TO_SOT_SMD:TO-277A` | VS-6ESH06HM3 DS doc 94985 p1 [P]; pads per KiCad TO-277A |
| J301, J901, J902 (3) | Phoenix GMSTBA 2,5/2-G-7,62 + plug GMSTB 2,5/2-ST-7,62 (item nos. [unverified]) | Phoenix Contact | `Connector_Generic:Conn_01x02` | `Connector_Phoenix_GMSTB:PhoenixContact_GMSTBA_2,5_2-G-7,62_1x02_P7.62mm_Horizontal` | Phoenix GMSTB 2,5 (7.62 mm pitch, high-voltage series) [S] |
| RT301, RT302 (2) | NTCG163JF103FTDS | TDK | `Device:Thermistor_NTC` | `Resistor_SMD:R_0603_1608Metric` | TDK NTCG series (10 kOhm, B 3435 K, AEC-Q200) [unverified] |
| U401, U421 (2) | AMC3330QDWERQ1 | TI | `Isolator_Analog:AMC3330` | `Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm` | AMC3330-Q1 DS SBASA35B, Fig. 4-1 / Table 4-1 [P] |
| U501 (1) | LM4040QBIM3X2.5/NOPB | TI | `Reference_Voltage:LM4040DBZ-2.5` | `Package_TO_SOT_SMD:SOT-23` | LM4040-N-Q1 DS SNOS633N, Fig. 4-1 (DBZ) [P] |
| U502 (1) | LM2901BQDRQ1 | TI | `Comparator:LM2901` | `Package_SO:SOIC-14_3.9x8.7mm_P1.27mm` | LM2901B-Q1 DS SLCS142H, Fig. 4-1 (D package) [P] |
| U503 (1) | SN74LVC2G74QDCURQ1 | TI | `74xGxx:74LVC2G74` | `Package_SO:VSSOP-8_2.3x2mm_P0.5mm` | SN74LVC2G74-Q1 DS SCES563C, DCU pinout p1 [P] |
| U504 (1) | TPS3850G33QDRCRQ1 | TI | `custom (kae:TPS3850_DRC)` | `Package_SON:VSON-10-1EP_3x3mm_P0.5mm_EP1.65x2.4mm` | TPS3850-Q1 DS SBVS264B, Fig. 5-1 / Table 5-1 [P] |
| U505 (1) | TPL7407LAQPWRQ1 | TI | `Transistor_Array:TPL7407LAPW` | `Package_SO:TSSOP-16_4.4x5mm_P0.65mm` | TPL7407LA-Q1 DS SLRS074, PW pinout [P] |
| D504 (1) | any AEC-Q101 green 0603 LED (e.g. OSRAM LG L29K) [unverified] | - | `Device:LED` | `LED_SMD:LED_0603_1608Metric` | generic LED, K=1 A=2 per KiCad Device:LED |
| D505 (1) | any AEC-Q101 red 0603 LED (e.g. OSRAM LS L29K) [unverified] | - | `Device:LED` | `LED_SMD:LED_0603_1608Metric` | generic LED, K=1 A=2 per KiCad Device:LED |
| U601, U602 (2) | LM5164QDDARQ1 | TI | `Regulator_Switching:LM5164DDA` | `Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm_ThermalVias` | LM5164-Q1 DS SNVSB51C, Fig. 4-1 / Table 4-1 [P] |
| L601 (1) | MSS1210-104KED | Coilcraft | `Device:L` | `Inductor_SMD:L_Coilcraft_MSS1210-XXX` | Coilcraft MSS1210 DS (100 uH, Isat 3.1 A@10%, DCR 0.125 Ohm max, AEC-Q200 85C) [S] |
| L602 (1) | MSS1048-333MLB | Coilcraft | `Device:L` | `Inductor_SMD:L_Coilcraft_MSS1048-XXX` | Coilcraft MSS1048 DS (33 uH, Isat 1.66 A@10%, DCR 68 mOhm max) [S] |
| U701 (1) | DSPIC33CK64MP102-E/SS | Microchip | `custom (kae:dsPIC33CK64MP102_SSOP28)` | `Package_SO:SSOP-28_5.3x10.2mm_P0.65mm` | dsPIC33CK64MP105 family DS DS70005363E, Table 2 (28-pin SSOP) p4 [P] |
| J701 (1) | 2.54 mm 1x6 header (e.g. Wurth 61300611121) [unverified] | - | `Connector_Generic:Conn_01x06` | `Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical` | PICkit-style ICSP order |
| D701 (1) | SBAS21LT1G | onsemi | `Diode:BAS21` | `Package_TO_SOT_SMD:SOT-23` | onsemi BAS21 SOT-23 DS (250 V) [unverified]; pinout matches KiCad Diode:BAS21 |
| J703, J903 (2) | Phoenix 1757284 (MSTBA 2,5/6-G-5,08) + plug MSTB 2,5/6-ST-5,08 | Phoenix Contact | `Connector_Generic:Conn_01x06` | `Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_6-G-5,08_1x06_P5.08mm_Horizontal` | Phoenix MSTB 2,5 series [S]; item numbers [unverified] |
| J704 (1) | Molex 43650-0215 (Micro-Fit 3.0, 2-pin vertical) | Molex | `Connector_Generic:Conn_01x02` | `Connector_Molex:Molex_Micro-Fit_3.0_43650-0215_1x02_P3.00mm_Vertical` | Molex Micro-Fit 3.0 [S] |
| TP701, TP702, TP703, TP704, TP705 (5) | (PCB pad) | - | `Connector:TestPoint` | `TestPoint:TestPoint_Pad_D1.5mm` | test pad, no BOM item |
| H701, H702, H703, H704 (4) | (M3 plated hole) | - | `Mechanical:MountingHole_Pad` | `MountingHole:MountingHole_3.2mm_M3_Pad_Via` | chassis bond hole |
| H705, H706, H901, H902, H903, H904 (6) | (M3 non-plated hole) | - | `Mechanical:MountingHole` | `MountingHole:MountingHole_3.2mm_M3` | isolated hole, no net |
| F901, F902 (2) | EVM10-5-2P | Eaton Bussmann | `Device:Fuse (4-pad variant: custom kae:Fuse_2x2pin)` | `custom (kae:Eaton_EVM10_2P; 'PCB layout 2P' in Eaton ELX1304)` | Eaton ELX1304 (Jan 2026) [P] ratings; 2P = two PCB pins per end cap [unverified] |
| K901, K902 (2) | G9EJ-1-P-E-UVD DC12 | Omron | `custom (kae:Relay_SPST_NO_polar)` | `custom (kae:Omron_G9EJ-1-P-E; per Omron G9EJ-1-E datasheet 'PCB terminals' mounting-hole drawing)` | Omron G9EJ-1-E DS (2016) [P] for ratings and contact polarity; terminal numbering is ours [unverified vs drawing] |

Resistors: Panasonic ERJ-3EKF (0603, 1 %, 0.1 W, 75 V), ERJ-3RQF (0603 < 10 Ohm), ERJ-8ENF (1206, 1 %, 0.25 W, 200 V), ERA-3AEB (0603, 0.1 %, 25 ppm/K); all AEC-Q200; MPN = series + 4-character value code + `V` per Panasonic numbering [S]. Symbol `Device:R`, footprints `Resistor_SMD:R_0603_1608Metric` / `R_1206_3216Metric`. Capacitors: symbol `Device:C` (`Device:C_Polarized` for the hybrid electrolytics, pin 1 = +); MPNs per row.

## Nets

| Net | Domain | Voltage range | Max current | Kind | Pins | Note |
|---|---|---|---|---|---|---|
| `BAT_F_N` | HV | pack - | 2 A | hv power | F902.3, F902.4, K902.3 | after F902 |
| `BAT_F_P` | HV | 150..262 V | 2 A | hv power | F901.3, F901.4, K901.4 | after F901 |
| `BAT_TAP_N` | HV | pack - | as above | hv power | J902.2, F902.1, F902.2 | traction battery - tap |
| `BAT_TAP_P` | HV | 150..262 V to BAT_TAP_N; pack short-circuit source | pack Isc (~0.5..2 kA) until F901 clears; 2 A normal | hv power | J902.1, F901.1, F901.2 | traction battery + tap |
| `BE_DK` | HV | 0..262 V | 2 A | hv power | K901.3, D901.3 | D901 cathode to K901 |
| `HVS1_D1` | HV | 219 V max to HV_N | <50 uA | hv sense | R401.2, R402.1 | divider string tap |
| `HVS1_D2` | HV | 176 V max to HV_N | <50 uA | hv sense | R402.2, R403.1 | divider string tap |
| `HVS1_D3` | HV | 132 V max to HV_N | <50 uA | hv sense | R403.2, R404.1 | divider string tap |
| `HVS1_D4` | HV | 88 V max to HV_N | <50 uA | hv sense | R404.2, R405.1 | divider string tap |
| `HVS1_D5` | HV | 45 V max to HV_N | <50 uA | hv sense | R405.2, R406.1 | divider string tap |
| `HVS1_DCDC` | HV | ~4 V to HV_N | <30 mA | bias, hv | U401.1, U401.3, C402.1, C403.1, C404.1 | isolated DC/DC out |
| `HVS1_HLDO` | HV | ~3.3 V to HV_N | <10 mA | bias, hv | U401.5, C405.1, C406.1 | high-side LDO |
| `HVS1_INP` | HV | 0..0.9 V to HV_N | <50 uA | hv sense | R406.2, R407.1, C401.1, U401.6 | AMC3330 input |
| `HVS2_D1` | HV | 219 V max to HV_N | <50 uA | hv sense | R421.2, R422.1 | divider string tap |
| `HVS2_D2` | HV | 176 V max to HV_N | <50 uA | hv sense | R422.2, R423.1 | divider string tap |
| `HVS2_D3` | HV | 132 V max to HV_N | <50 uA | hv sense | R423.2, R424.1 | divider string tap |
| `HVS2_D4` | HV | 88 V max to HV_N | <50 uA | hv sense | R424.2, R425.1 | divider string tap |
| `HVS2_D5` | HV | 45 V max to HV_N | <50 uA | hv sense | R425.2, R426.1 | divider string tap |
| `HVS2_DCDC` | HV | ~4 V to HV_N | <30 mA | bias, hv | U421.1, U421.3, C422.1, C423.1, C424.1 | isolated DC/DC out |
| `HVS2_HLDO` | HV | ~3.3 V to HV_N | <10 mA | bias, hv | U421.5, C425.1, C426.1 | high-side LDO |
| `HVS2_INP` | HV | 0..0.9 V to HV_N | <50 uA | hv sense | R426.2, R427.1, C421.1, U421.6 | AMC3330 input |
| `HV_N` | HV | reference of HV domain | 2 A | hv power / hv ground | D303.1, D303.2, D304.1, D304.2, C350.2, C351.2, C352.2, C353.2, C354.2, C355.2, J301.2, R407.2, C401.2, U401.2, U401.7, U401.8, C402.2, C403.2, C404.2, C405.2, C406.2, R427.2, C421.2, U421.2, U421.7, U421.8, C422.2, C423.2, C424.2, C425.2, C426.2, J901.2, K902.4 | converter output -, via cable to K902 |
| `HV_P` | HV | 0..262 V to HV_N; floating to chassis (|V| <= 262 V single fault) | 2 A | hv power | D301.3, D302.3, C350.1, C351.1, C352.1, C353.1, C354.1, C355.1, J301.1, R401.1, R421.1, J901.1, D901.1, D901.2 | converter output +, via cable to battery-end D901 |
| `T1_S1` | HV | +-262 V square (to HV_N: 0..262 V) | 2 A rms | switching node, hv | T301.11, D301.1, D301.2, D303.3, R305.1 | T1 secondary |
| `T1_S2` | HV | +-262 V square | 2 A rms | switching node, hv | T301.20, D302.1, D302.2, D304.3, C349.2 | T1 secondary |
| `T1_SNB` | HV | 0..262 V | <0.1 A | hv | R305.2, C349.1 | snubber (DNP) |
| `+3V3` | LV | 3.29 V | 0.25 A | power | U102.3, C103.1, U104.5, C126.1, R130.1, U202.3, C203.1, U204.5, C226.1, R230.1, R309.1, U401.12, C408.1, C409.1, U402.5, C410.1, U421.12, C428.1, C429.1, U422.5, C430.1, R514.1, U503.8, C507.1, U504.1, U504.10, C508.1, R515.1, R516.1, L602.2, C611.1, C612.1, R610.1, C613.2, U701.7, U701.20, R701.1, C703.1, C704.1, C705.1, R702.1, J701.2, R706.1, TP703.1 | logic, AMC3330 low sides, op-amps |
| `+3V3A` | LV | 3.29 V | <20 mA | power | U701.5, R701.2, C701.1, C702.1 | MCU AVDD (ADC reference) |
| `AGND_A` | LV | 0 V | <10 mA | ground | U103.10, U103.29, R108.2, C109.2, R111.2, C110.2, R112.2, C111.2, C112.2, C113.2, C114.2, R115.2, NT101.1 | LM5176 A analog ground, tied to GND only at NT101 |
| `AGND_B` | LV | 0 V | <10 mA | ground | U203.10, U203.29, R208.2, C209.2, R211.2, C210.2, R212.2, C211.2, C212.2, C213.2, C214.2, R215.2, NT201.1 | LM5176 B analog ground, tied to GND only at NT201 |
| `AUX12` | LV | 12.1 V | 0.6 A | power | R121.1, R221.1, U301.1, C311.1, C312.1, R501.1, U502.3, C503.1, U505.9, C510.1, R521.1, R522.1, L601.2, C604.1, C605.1, R604.1, C606.2, C608.1, C609.1, U602.2, R607.1, J703.1, J704.1, TP702.1, J903.1, K901.1, K902.1 | gate drive, relays, fan, comparators, reference |
| `AUX12_BST` | LV | SW + 5 V | <0.1 A | bias | U601.7, C603.1 |  |
| `AUX12_FB` | LV | 0..5 V | <1 mA | analog | U601.5, R604.2, R605.1, C607.2 |  |
| `AUX12_RA` | LV | 0..5 V | <1 mA | analog | R606.2, C606.1, C607.1 |  |
| `AUX12_RON` | LV | 0..5 V | <1 mA | analog | U601.4, R603.1 |  |
| `AUX12_SW` | LV | -1..48 V | 1 A pk | switching node | U601.8, C603.2, L601.1, R606.1 |  |
| `AUX_EN` | LV | 0..4.8 V | <0.1 mA | signal | U601.3, R601.2, R602.1 |  |
| `AUX_IN` | LV | 0..48 V | 0.6 A | power | D601.3, D602.3, D603.3, C601.1, C602.1, U601.2, R601.1 | OR of PV_A, PV_B, VINT |
| `DCX_HB` | LV | HB_SW + 11 V | 3 A pk | bias | U301.3, C314.1 | bootstrap |
| `DCX_HI` | LV | 0/3.3 V | <1 mA | digital | R303.1, U701.25 | MCU PWM1H/L, 95-100 kHz, 50% with dead time |
| `DCX_HI_F` | LV | 0/3.3 V | <1 mA | digital | U301.7, R303.2, C315.1 | MCU PWM1H/L, 95-100 kHz, 50% with dead time |
| `DCX_HO` | LV | node + 0..12 V | 3 A pk | gate | U301.4, R301.1 |  |
| `DCX_HO_G` | LV | node + 0..12 V | 3 A pk | gate | Q301.4, R301.2 |  |
| `DCX_LI` | LV | 0/3.3 V | <1 mA | digital | R304.1, U701.26 | MCU PWM1H/L, 95-100 kHz, 50% with dead time |
| `DCX_LI_F` | LV | 0/3.3 V | <1 mA | digital | U301.8, R304.2, C316.1 | MCU PWM1H/L, 95-100 kHz, 50% with dead time |
| `DCX_LO` | LV | node + 0..12 V | 3 A pk | gate | U301.10, R302.1 |  |
| `DCX_LO_G` | LV | node + 0..12 V | 3 A pk | gate | Q302.4, R302.2 |  |
| `DCX_MID` | LV | -2..50 V | 22 A rms | switching node | C317.2, C318.2, C319.2, C320.2, C321.2, C322.2, C323.2, C324.2, C325.2, C326.2, C327.2, C328.2, C329.2, C330.2, C331.2, C332.2, C333.1, C334.1, C335.1, C336.1, C337.1, C338.1, C339.1, C340.1, C341.1, C342.1, C343.1, C344.1, C345.1, C346.1, C347.1, C348.1, T301.3, T301.4 | split/resonant midpoint, -2..34 V |
| `FAN_N` | LV | 0..12 V | 0.3 A | power (inductive) | U505.14, J704.2 | fan low side |
| `FAN_PWM` | LV | 0/3.3 V | <1 mA | digital | U505.3, U701.23 |  |
| `GND` | LV | 0 V (reference; bonded to chassis at H701-H704) | 8 A per string return | ground | J101.2, D101.2, U101.2, C102.2, U102.1, C103.2, C104.2, R105.2, C106.2, C107.2, C108.2, U103.22, R116.4, C117.2, C118.2, C120.2, C121.2, C122.2, C123.2, NT101.2, R125.2, C124.2, U104.2, C126.2, C127.2, C128.2, J201.2, D201.2, U201.2, C202.2, U202.1, C203.2, C204.2, R205.2, C206.2, C207.2, C208.2, U203.22, R216.4, C217.2, C218.2, C220.2, C221.2, C222.2, C223.2, NT201.2, R225.2, C224.2, U204.2, C226.2, C227.2, C228.2, C301.2, C302.2, C303.2, C304.2, C305.2, C306.2, C307.2, C308.2, C309.2, C310.2, Q302.1, Q302.2, Q302.3, U301.9, U301.11, C311.2, C312.2, C313.2, C315.2, C316.2, C333.2, C334.2, C335.2, C336.2, C337.2, C338.2, C339.2, C340.2, C341.2, C342.2, C343.2, C344.2, C345.2, C346.2, C347.2, C348.2, R308.2, C356.2, RT301.2, C357.2, RT302.2, C358.2, U401.9, U401.15, C407.2, C408.2, C409.2, U402.2, R409.2, C410.2, C411.2, U421.9, U421.15, C427.2, C428.2, C429.2, U422.2, R429.2, C430.2, C431.2, U501.2, C501.2, R503.2, C502.2, U502.12, C503.2, R505.2, C504.2, R507.2, R510.2, C505.2, C506.2, U503.1, U503.2, U503.4, C507.2, U504.3, U504.5, U504.6, U504.11, C508.2, R519.2, C509.2, U505.6, U505.7, U505.8, C510.2, C601.2, C602.2, U601.1, U601.9, R602.2, R603.2, C604.2, C605.2, R605.2, C608.2, C609.2, U602.1, U602.9, R608.2, R609.2, C611.2, C612.2, R611.2, U701.6, U701.8, U701.19, C701.2, C702.2, C703.2, C704.2, C705.2, J701.3, J702.2, R705.2, Q701.2, C707.2, J703.5, J703.6, TP705.1, H701.1, H702.1, H703.1, H704.1, J903.5, J903.6, J904.2 | PV-, PGND, signal ground |
| `HB_SW` | LV | -2..50 V | 22 A rms | switching node | Q301.1, Q301.2, Q301.3, Q302.5, U301.5, C314.2, T301.1, T301.2 | half-bridge switch node 0..VINT |
| `HVS1_DA_N` | LV | 0..3.3 V | <1 mA | analog | U402.4, R410.2, R411.1 |  |
| `HVS1_DA_OUT` | LV | 0..3.3 V | <1 mA | analog | U402.1, R411.2, R412.1 |  |
| `HVS1_DA_P` | LV | 0..3.3 V | <1 mA | analog | U402.3, R408.2, R409.1 |  |
| `HVS1_LDO` | LV | ~3 V | <40 mA | bias | U401.13, U401.16, C407.1 | low-side LDO -> DCDC_IN |
| `HVS1_OUTN` | LV | 0..3.3 V | <1 mA | analog | U401.10, R410.1 |  |
| `HVS1_OUTP` | LV | 0..3.3 V | <1 mA | analog | U401.11, R408.1 |  |
| `HVS2_DA_N` | LV | 0..3.3 V | <1 mA | analog | U422.4, R430.2, R431.1 |  |
| `HVS2_DA_OUT` | LV | 0..3.3 V | <1 mA | analog | U422.1, R431.2, R432.1 |  |
| `HVS2_DA_P` | LV | 0..3.3 V | <1 mA | analog | U422.3, R428.2, R429.1 |  |
| `HVS2_LDO` | LV | ~3 V | <40 mA | bias | U421.13, U421.16, C427.1 | low-side LDO -> DCDC_IN |
| `HVS2_OUTN` | LV | 0..3.3 V | <1 mA | analog | U421.10, R430.1 |  |
| `HVS2_OUTP` | LV | 0..3.3 V | <1 mA | analog | U421.11, R428.1 |  |
| `HV_V_ADC` | LV | 0..2.0 V (0..300 V) | <1 mA | analog | R412.2, C411.1, U701.28 | HV voltage to MCU |
| `HV_V_OVP` | LV | 0..2.3 V | <1 mA | analog | R432.2, C431.1, U502.6 | HV voltage to OVP comparator (trip 2.000 V) |
| `IGN_D` | LV | 0..112 V | <10 mA | signal | D701.3, R704.1 |  |
| `IGN_IN` | LV | -150..+112 V transients; 9..16 V normal | <10 mA | signal (vehicle) | J702.1, D701.1 | from car IG2/READY fused circuit |
| `K1_COIL_N` | LV | 0..12 V (clamped to AUX12+0.7) | 0.12 A | power (inductive) | U505.16, J703.2, J903.2, K901.2 | relay K901 coil low side (via harness) |
| `K2_COIL_N` | LV | 0..12 V | 0.12 A | power (inductive) | U505.15, J703.3, J903.3, K902.2 | relay K902 coil low side (via harness) |
| `K_IN` | LV | 0/3.3 V | <1 mA | digital, safety | R520.2, D503.2, U505.1, U505.2 | RELAY_REQ AND PERMIT |
| `LATCH_Q` | LV | 0/3.3 V | <1 mA | digital, safety | U503.5, U505.5, U701.12 | OVP latched (to MCU and red LED) |
| `LATCH_QN` | LV | 0/3.3 V | <1 mA | digital, safety | U503.3, D501.1 |  |
| `LED_FLT_A` | LV | 0..12 V | 6 mA | signal | D505.2, R522.2 |  |
| `LED_FLT_K` | LV | 0..12 V | 6 mA | signal | U505.12, D505.1 |  |
| `LED_OK_A` | LV | 0..12 V | 6 mA | signal | D504.2, R521.2 |  |
| `LED_OK_K` | LV | 0..12 V | 6 mA | signal | U505.13, D504.1 |  |
| `MCLR_N` | LV | 0/3.3 V | <1 mA | digital | R517.2, D502.2, U701.27, R702.2, J701.1 | MCU reset |
| `MCU_RUN` | LV | 0/3.3 V | <1 mA | digital, safety | R518.1, R519.1, U701.24 |  |
| `MPPT_A_PWM` | LV | 0/3.3 V PWM | <1 mA | digital | R128.1, R130.2, U701.21 | MCU setpoint PWM, default high |
| `MPPT_B_PWM` | LV | 0/3.3 V PWM | <1 mA | digital | R228.1, R230.2, U701.22 | MCU setpoint PWM, default high |
| `NTC_HS` | LV | 0..3.3 V | <1 mA | analog | RT301.1, R309.2, C357.1, U701.10 | heatsink NTC to MCU |
| `NTC_PACK` | LV | 0..2.5 V | <1 mA | analog | U502.11, R511.2, R512.2, C505.1, U701.11, J703.4, J903.4, J904.1 | pack NTC (off-board via harness) to MCU and comparator ch4 |
| `NTC_T1` | LV | 0..2.5 V | <1 mA | analog | RT302.1, R310.2, C358.1, U502.9, R508.2 | T1 NTC to comparator ch3 |
| `OVP_TRIP_N` | LV | 0/3.3 V | <4 mA | digital, safety | U502.1, U502.2, R514.2, C506.1, U503.7 | open-collector OR of comparator ch1/ch2 -> latch ~PRE |
| `PERMIT` | LV | 0..3.3 V (wired-AND) | <1 mA | digital, safety | D102.1, D202.1, U301.6, C313.1, U401.14, U421.14, U502.13, U502.14, R508.1, R511.1, D501.2, R518.2, C509.1, D503.1, U505.4, TP704.1 | run permission: sourced by MCU_RUN via 10k; pulled low by WDT reset, DIAG1/2, OVP latch, OTP comparators |
| `PGC` | LV | 0/3.3 V | <5 mA | digital | U701.18, J701.5 |  |
| `PGD` | LV | 0/3.3 V | <5 mA | digital | U701.17, J701.4 |  |
| `PVA_BIAS` | LV | 0..12 V | <40 mA | bias | U103.24, R121.2, C118.1 |  |
| `PVA_BT1` | LV | SW1 + 7 V | 2 A pk | bias | U103.26, C119.1, D104.1 | bootstrap |
| `PVA_BT2` | LV | SW2 + 7 V | 2 A pk | bias | U103.20, C116.1, D103.1 | bootstrap |
| `PVA_COMP` | LV | 0..3.3 V | <1 mA | analog | U103.9, R113.1, C114.1 |  |
| `PVA_COMP_RC` | LV | 0..3.3 V | <1 mA | analog | R113.2, C113.1 |  |
| `PVA_CS` | LV | 0..3.3 V | <1 mA | sense | U103.16, R117.2, C115.1 |  |
| `PVA_CSG` | LV | 0..3.3 V | <1 mA | sense | U103.15, R118.2, C115.2 |  |
| `PVA_CSG_K` | LV | 0..3.3 V | <1 mA | sense | R116.3, R118.1 |  |
| `PVA_CS_K` | LV | 0..3.3 V | <1 mA | sense | R116.2, R117.1 |  |
| `PVA_DITH` | LV | 0..3.3 V | <1 mA | analog | U103.5, C110.1 |  |
| `PVA_EN` | LV | 0..3.2 V | <0.2 mA | signal | U103.1, R107.2, R108.1, D102.2 | LM5176 EN/UVLO |
| `PVA_FB` | LV | 0..3.3 V | <1 mA | analog | U103.11, R114.2, R115.1 |  |
| `PVA_HD1` | LV | node + 0..7.5 V | 2 A pk | gate | U103.27, R123.1 |  |
| `PVA_HD1_G` | LV | node + 0..7.5 V | 2 A pk | gate | R123.2, Q103.4 |  |
| `PVA_HD2` | LV | node + 0..7.5 V | 2 A pk | gate | U103.19, R119.1 |  |
| `PVA_HD2_G` | LV | node + 0..7.5 V | 2 A pk | gate | R119.2, Q105.4 |  |
| `PVA_IDG` | LV | PV + 0..14 V | gate | gate | U101.5, Q101.4 | ideal-diode gate |
| `PVA_IN` | LV | 0..33 V (TVS clamp 54 V) | 8 A | power | J101.1, D101.1, C101.2, U101.3, U101.6, Q101.1, Q101.2, Q101.3 | string A + at connector |
| `PVA_INA_N` | LV | 0..33 V | <5 mA fault | sense | U102.4, R132.2 | INA186 IN- behind 10k |
| `PVA_INA_P` | LV | 0..33 V | <5 mA fault | sense | U102.5, R131.2 | INA186 IN+ behind 10k |
| `PVA_INT_N` | LV | 0..3.3 V | <1 mA | analog | U104.4, R126.2, C125.1 |  |
| `PVA_ISK_N` | LV | 0..33 V | <1 mA | sense | R101.3, R132.1, R104.1 | Kelvin - of shunt |
| `PVA_ISK_P` | LV | 0..33 V | <1 mA | sense | R101.2, R131.1, R103.1 | Kelvin + of shunt |
| `PVA_ISNS_N` | LV | 0..33 V | <0.1 mA | sense | R104.2, C105.2, U103.13 | LM5176 ISNS(-) |
| `PVA_ISNS_P` | LV | 0..33 V | <0.2 mA | sense | R103.2, C105.1, Q102.3, U103.14 | LM5176 ISNS(+) after R_iso |
| `PVA_I_ADC` | LV | 0..3.3 V | <1 mA | analog | R102.2, C104.1, U701.2 | PV current to MCU (0.25 V/A) |
| `PVA_I_RAW` | LV | 0..3.3 V | <1 mA | signal | U102.2, R102.1 | INA186 out |
| `PVA_LD1` | LV | node + 0..7.5 V | 2 A pk | gate | U103.25, R122.1 |  |
| `PVA_LD1_G` | LV | node + 0..7.5 V | 2 A pk | gate | R122.2, Q104.4 |  |
| `PVA_LD2` | LV | node + 0..7.5 V | 2 A pk | gate | U103.21, R120.1 |  |
| `PVA_LD2_G` | LV | node + 0..7.5 V | 2 A pk | gate | R120.2, Q106.4 |  |
| `PVA_MODE` | LV | 0..3.3 V | <1 mA | analog | U103.4, R111.1 |  |
| `PVA_MPPT_OUT` | LV | 0..3.3 V | <1 mA | signal | R106.1, U104.1, R127.2 | PV-voltage regulator output |
| `PVA_P` | LV | 0..33 V | 8 A | power | U101.4, Q101.5, C102.1, R101.1, D601.1, D601.2 | string A + after ideal diode |
| `PVA_PI` | LV | 0..3.3 V | <1 mA | analog | C125.2, R127.1 |  |
| `PVA_RT` | LV | 0..3.3 V | <1 mA | analog | U103.6, R112.1 |  |
| `PVA_SINK_B` | LV | 0..3.3 V | <0.3 mA | signal | Q102.1, R106.2 |  |
| `PVA_SINK_E` | LV | 0..2.6 V | <0.15 mA | signal | Q102.2, R105.1 |  |
| `PVA_SLOPE` | LV | 0..3.3 V | <1 mA | analog | U103.7, C111.1 |  |
| `PVA_SRC` | LV | 0..0.15 V | 12 A pk | power | R116.1, Q104.1, Q104.2, Q104.3, Q106.1, Q106.2, Q106.3 | low-side FET sources (top of RSENSE) |
| `PVA_SS` | LV | 0..3.3 V | <1 mA | analog | U103.8, C112.1 |  |
| `PVA_SW1` | LV | -1..33 V | 12 A pk | switching node | U103.28, C119.2, Q103.1, Q103.2, Q103.3, Q104.5, L101.1 | buck-side switch node |
| `PVA_SW2` | LV | -1..49 V | 12 A pk | switching node | U103.18, C116.2, Q105.1, Q105.2, Q105.3, Q106.5, L101.2 | boost-side switch node |
| `PVA_VCAP` | LV | PV + 0..14 V | <1 mA | bias | C101.1, U101.1 | LM74700 charge pump |
| `PVA_VCC` | LV | 7.35 V | <65 mA | bias | U103.23, D103.2, C117.1, D104.2 | LM5176 VCC |
| `PVA_VDIV` | LV | 0..3.3 V | <1 mA | analog | R124.2, R125.1, C124.1, R126.1, U701.1 |  |
| `PVA_VINF` | LV | 0..33 V | <10 mA | bias | U103.2, R109.2, C109.1 | LM5176 VIN pin |
| `PVA_VISNS` | LV | 0..33 V | <1 mA | sense | U103.3, R110.2 |  |
| `PVA_VSET` | LV | 0..3.3 V | <1 mA | analog | U104.3, R129.2, C128.1 |  |
| `PVA_VSET1` | LV | 0..3.3 V | <1 mA | analog | R128.2, C127.1, R129.1 |  |
| `PVB_BIAS` | LV | 0..12 V | <40 mA | bias | U203.24, R221.2, C218.1 |  |
| `PVB_BT1` | LV | SW1 + 7 V | 2 A pk | bias | U203.26, C219.1, D204.1 | bootstrap |
| `PVB_BT2` | LV | SW2 + 7 V | 2 A pk | bias | U203.20, C216.1, D203.1 | bootstrap |
| `PVB_COMP` | LV | 0..3.3 V | <1 mA | analog | U203.9, R213.1, C214.1 |  |
| `PVB_COMP_RC` | LV | 0..3.3 V | <1 mA | analog | R213.2, C213.1 |  |
| `PVB_CS` | LV | 0..3.3 V | <1 mA | sense | U203.16, R217.2, C215.1 |  |
| `PVB_CSG` | LV | 0..3.3 V | <1 mA | sense | U203.15, R218.2, C215.2 |  |
| `PVB_CSG_K` | LV | 0..3.3 V | <1 mA | sense | R216.3, R218.1 |  |
| `PVB_CS_K` | LV | 0..3.3 V | <1 mA | sense | R216.2, R217.1 |  |
| `PVB_DITH` | LV | 0..3.3 V | <1 mA | analog | U203.5, C210.1 |  |
| `PVB_EN` | LV | 0..3.2 V | <0.2 mA | signal | U203.1, R207.2, R208.1, D202.2 | LM5176 EN/UVLO |
| `PVB_FB` | LV | 0..3.3 V | <1 mA | analog | U203.11, R214.2, R215.1 |  |
| `PVB_HD1` | LV | node + 0..7.5 V | 2 A pk | gate | U203.27, R223.1 |  |
| `PVB_HD1_G` | LV | node + 0..7.5 V | 2 A pk | gate | R223.2, Q203.4 |  |
| `PVB_HD2` | LV | node + 0..7.5 V | 2 A pk | gate | U203.19, R219.1 |  |
| `PVB_HD2_G` | LV | node + 0..7.5 V | 2 A pk | gate | R219.2, Q205.4 |  |
| `PVB_IDG` | LV | PV + 0..14 V | gate | gate | U201.5, Q201.4 | ideal-diode gate |
| `PVB_IN` | LV | 0..33 V (TVS clamp 54 V) | 8 A | power | J201.1, D201.1, C201.2, U201.3, U201.6, Q201.1, Q201.2, Q201.3 | string B + at connector |
| `PVB_INA_N` | LV | 0..33 V | <5 mA fault | sense | U202.4, R232.2 | INA186 IN- behind 10k |
| `PVB_INA_P` | LV | 0..33 V | <5 mA fault | sense | U202.5, R231.2 | INA186 IN+ behind 10k |
| `PVB_INT_N` | LV | 0..3.3 V | <1 mA | analog | U204.4, R226.2, C225.1 |  |
| `PVB_ISK_N` | LV | 0..33 V | <1 mA | sense | R201.3, R232.1, R204.1 | Kelvin - of shunt |
| `PVB_ISK_P` | LV | 0..33 V | <1 mA | sense | R201.2, R231.1, R203.1 | Kelvin + of shunt |
| `PVB_ISNS_N` | LV | 0..33 V | <0.1 mA | sense | R204.2, C205.2, U203.13 | LM5176 ISNS(-) |
| `PVB_ISNS_P` | LV | 0..33 V | <0.2 mA | sense | R203.2, C205.1, Q202.3, U203.14 | LM5176 ISNS(+) after R_iso |
| `PVB_I_ADC` | LV | 0..3.3 V | <1 mA | analog | R202.2, C204.1, U701.4 | PV current to MCU (0.25 V/A) |
| `PVB_I_RAW` | LV | 0..3.3 V | <1 mA | signal | U202.2, R202.1 | INA186 out |
| `PVB_LD1` | LV | node + 0..7.5 V | 2 A pk | gate | U203.25, R222.1 |  |
| `PVB_LD1_G` | LV | node + 0..7.5 V | 2 A pk | gate | R222.2, Q204.4 |  |
| `PVB_LD2` | LV | node + 0..7.5 V | 2 A pk | gate | U203.21, R220.1 |  |
| `PVB_LD2_G` | LV | node + 0..7.5 V | 2 A pk | gate | R220.2, Q206.4 |  |
| `PVB_MODE` | LV | 0..3.3 V | <1 mA | analog | U203.4, R211.1 |  |
| `PVB_MPPT_OUT` | LV | 0..3.3 V | <1 mA | signal | R206.1, U204.1, R227.2 | PV-voltage regulator output |
| `PVB_P` | LV | 0..33 V | 8 A | power | U201.4, Q201.5, C202.1, R201.1, D602.1, D602.2 | string B + after ideal diode |
| `PVB_PI` | LV | 0..3.3 V | <1 mA | analog | C225.2, R227.1 |  |
| `PVB_RT` | LV | 0..3.3 V | <1 mA | analog | U203.6, R212.1 |  |
| `PVB_SINK_B` | LV | 0..3.3 V | <0.3 mA | signal | Q202.1, R206.2 |  |
| `PVB_SINK_E` | LV | 0..2.6 V | <0.15 mA | signal | Q202.2, R205.1 |  |
| `PVB_SLOPE` | LV | 0..3.3 V | <1 mA | analog | U203.7, C211.1 |  |
| `PVB_SRC` | LV | 0..0.15 V | 12 A pk | power | R216.1, Q204.1, Q204.2, Q204.3, Q206.1, Q206.2, Q206.3 | low-side FET sources (top of RSENSE) |
| `PVB_SS` | LV | 0..3.3 V | <1 mA | analog | U203.8, C212.1 |  |
| `PVB_SW1` | LV | -1..33 V | 12 A pk | switching node | U203.28, C219.2, Q203.1, Q203.2, Q203.3, Q204.5, L201.1 | buck-side switch node |
| `PVB_SW2` | LV | -1..49 V | 12 A pk | switching node | U203.18, C216.2, Q205.1, Q205.2, Q205.3, Q206.5, L201.2 | boost-side switch node |
| `PVB_VCAP` | LV | PV + 0..14 V | <1 mA | bias | C201.1, U201.1 | LM74700 charge pump |
| `PVB_VCC` | LV | 7.35 V | <65 mA | bias | U203.23, D203.2, C217.1, D204.2 | LM5176 VCC |
| `PVB_VDIV` | LV | 0..3.3 V | <1 mA | analog | R224.2, R225.1, C224.1, R226.1, U701.3 |  |
| `PVB_VINF` | LV | 0..33 V | <10 mA | bias | U203.2, R209.2, C209.1 | LM5176 VIN pin |
| `PVB_VISNS` | LV | 0..33 V | <1 mA | sense | U203.3, R210.2 |  |
| `PVB_VSET` | LV | 0..3.3 V | <1 mA | analog | U204.3, R229.2, C228.1 |  |
| `PVB_VSET1` | LV | 0..3.3 V | <1 mA | analog | R228.2, C227.1, R229.1 |  |
| `READY_B` | LV | 0..0.8 V | <1 mA | signal | R704.2, R705.1, Q701.1 |  |
| `READY_N` | LV | 0/3.3 V | <1 mA | digital | U701.13, Q701.3, R706.2, C707.1 | low = car IG/READY on |
| `RELAY_REQ` | LV | 0/3.3 V (PWM economiser after pull-in) | <1 mA | digital | R520.1, U701.16 |  |
| `RESET_N` | LV | 0/3.3 V | <1 mA | digital, safety | U503.6, U504.9, R516.2, D502.1 | supervisor reset; clears OVP latch only at power-up/brown-out |
| `TPS_CWD` | LV | 3.3 V | <1 mA | bias | U504.2, R515.2 |  |
| `UART_TX` | LV | 0/3.3 V | <5 mA | digital | U701.14, J701.6 |  |
| `V33_BST` | LV | SW + 5 V | <0.1 A | bias | U602.7, C610.1 |  |
| `V33_EN` | LV | 0..5 V | <1 mA | analog | U602.3, R607.2, R608.1 |  |
| `V33_FB` | LV | 0..5 V | <1 mA | analog | U602.5, R610.2, R611.1, C614.2 |  |
| `V33_RA` | LV | 0..5 V | <1 mA | analog | R612.2, C613.1, C614.1 |  |
| `V33_RON` | LV | 0..5 V | <1 mA | analog | U602.4, R609.1 |  |
| `V33_SW` | LV | -1..12 V | 1 A pk | switching node | U602.8, C610.2, L602.1, R612.1 |  |
| `VA_IN` | LV | 0..33 V | 8 A dc + ripple | power | R101.4, C106.1, C107.1, C108.1, R107.1, R109.1, R110.1, Q103.5, R124.1 | channel A power-stage input (after shunt) |
| `VB_IN` | LV | 0..33 V | 8 A dc + ripple | power | R201.4, C206.1, C207.1, C208.1, R207.1, R209.1, R210.1, Q203.5, R224.1 | channel B power-stage input (after shunt) |
| `VINT` | LV | 0..49.4 V (NiMH) / 0..44 V (Li); normal 30..46 V | 10 A dc, 22 A rms in DCX caps | power | U103.12, R114.1, Q105.5, C120.1, C121.1, C122.1, C123.1, U203.12, R214.1, Q205.5, C220.1, C221.1, C222.1, C223.1, C301.1, C302.1, C303.1, C304.1, C305.1, C306.1, C307.1, C308.1, C309.1, C310.1, Q301.5, C317.1, C318.1, C319.1, C320.1, C321.1, C322.1, C323.1, C324.1, C325.1, C326.1, C327.1, C328.1, C329.1, C330.1, C331.1, C332.1, R307.1, R504.1, D603.1, D603.2, TP701.1 | intermediate bus |
| `VINT_DIV` | LV | 0..2.5 V | <1 mA | analog | R307.2, R308.1, C356.1, U701.9 | VINT/20.1 to MCU |
| `VINT_OVP` | LV | 0..2.2 V | <0.3 mA | analog | U502.4, R504.2, R505.1, C504.1 | independent VINT divider |
| `VREF2V5` | LV | 2.500 V | <1.5 mA | reference | R310.1, R501.2, U501.1, C501.1, R502.1, R506.1, R509.1, R512.1 |  |
| `VTH2V0` | LV | OVP threshold 2.000 V | <0.3 mA | reference | R502.2, R503.1, C502.1, U502.5, U502.7 |  |
| `VTH_OT1` | LV | T1 OTP threshold 0.716 V | <0.3 mA | reference | U502.8, R506.2, R507.1 |  |
| `VTH_OTP` | LV | pack OTP threshold 0.729 V | <0.3 mA | reference | U502.10, R509.2, R510.1 |  |
| `WDI` | LV | 0/3.3 V | <1 mA | digital | U504.7, U701.15 | watchdog kick |
| `WDO_N` | LV | 0/3.3 V | <1 mA | digital, safety | U504.8, R517.1 |  |

## Block MPPT_A (board MB)

MPPT channel A: string A input, protection, PV current/voltage sense, LM5176 4-switch buck-boost to VINT, analog PV-voltage regulator

### Two-terminal parts

| Ref | MPN | Value / rating | Footprint | Pin 1 | Pin 2 | Note |
|---|---|---|---|---|---|---|
| C101 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_VCAP` | 2 (2): `PVA_IN` | LM74700 charge-pump cap (VCAP-ANODE) |
| C102 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_P` | 2 (2): `GND` | LM74700 CATHODE cap |
| R131 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_ISK_P` | 2 (2): `PVA_INA_P` | limits INA186 input current to <5 mA during 54 V TVS clamp (DS note 3); 3 nA IB -> 30 uV |
| R132 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_ISK_N` | 2 (2): `PVA_INA_N` | as above, matched |
| C103 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | U2 VS decoupling |
| R102 | Panasonic ERJ-3EKF1001V | 1 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_I_RAW` | 2 (2): `PVA_I_ADC` | ADC anti-alias |
| C104 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_I_ADC` | 2 (2): `GND` | ADC anti-alias |
| R103 | Panasonic ERJ-3EKF1001V | 1 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_ISK_P` | 2 (2): `PVA_ISNS_P` | R_iso: lets Q2 offset the CC-loop sense voltage |
| R104 | Panasonic ERJ-3EKF1000V | 100 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_ISK_N` | 2 (2): `PVA_ISNS_N` | CC-loop sense filter |
| C105 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_ISNS_P` | 2 (2): `PVA_ISNS_N` | CC-loop sense filter (differential) |
| R105 | Panasonic ERJ-3EKF2002V | 20 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_SINK_E` | 2 (2): `GND` | sink emitter resistor |
| R106 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_MPPT_OUT` | 2 (2): `PVA_SINK_B` | sink base resistor |
| C106 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VA_IN` | 2 (2): `GND` | buck-side hot-loop input cap (next to QH1/QL1) |
| C107 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VA_IN` | 2 (2): `GND` | buck-side hot-loop input cap |
| C108 | Panasonic EEH-ZA1J101P | 100 uF 63 V polymer-hybrid Al | `CP_Elec_10x10` | 1 (+): `VA_IN` | 2 (-): `GND` | input bulk |
| R107 | Panasonic ERJ-3EKF2003V | 200 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VA_IN` | 2 (2): `PVA_EN` | UVLO top: on 10.5 V, hyst 0.63 V |
| R108 | Panasonic ERJ-3EKF2742V | 27.4 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_EN` | 2 (2): `AGND_A` | UVLO bottom |
| R109 | Panasonic ERJ-3EKF10R0V | 10 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VA_IN` | 2 (2): `PVA_VINF` | VIN filter |
| C109 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_VINF` | 2 (2): `AGND_A` | VIN filter |
| R110 | Panasonic ERJ-3EKF2001V | 2 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VA_IN` | 2 (2): `PVA_VISNS` | VISNS series R (TI: required >40 V) |
| R111 | Panasonic ERJ-3EKF9312V | 93.1 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_MODE` | 2 (2): `AGND_A` | CCM, hiccup enabled |
| C110 | Murata GCM188R71H473KA55D | 47 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_DITH` | 2 (2): `AGND_A` | dither ~0.9 kHz modulation |
| R112 | Panasonic ERJ-3EKF4122V | 41.2 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_RT` | 2 (2): `AGND_A` | fsw 201 kHz |
| C111 | Murata GCM1885C1H681JA16D | 680 pF 50 V C0G | `C_0603_1608Metric` | 1 (1): `PVA_SLOPE` | 2 (2): `AGND_A` | slope comp |
| C112 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_SS` | 2 (2): `AGND_A` | soft start 16 ms; CC loop acts on this node |
| R113 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_COMP` | 2 (2): `PVA_COMP_RC` | Rc1 (initial; tune by sim) |
| C113 | Murata GCM188R71H473KA55D | 47 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_COMP_RC` | 2 (2): `AGND_A` | Cc1 (initial) |
| C114 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `PVA_COMP` | 2 (2): `AGND_A` | Cc2 (initial) |
| R114 | Panasonic ERJ-3EKF5623V | 562 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VINT` | 2 (2): `PVA_FB` | FB top, VARIANT: 562k (NiMH ceiling 251.7 V) / 499k (Li ceiling 224.0 V) |
| R115 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `PVA_FB` | 2 (2): `AGND_A` | FB bottom |
| R117 | Panasonic ERJ-3EKF1000V | 100 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_CS_K` | 2 (2): `PVA_CS` | CS filter |
| R118 | Panasonic ERJ-3EKF1000V | 100 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_CSG_K` | 2 (2): `PVA_CSG` | CSG filter |
| C115 | Murata GCM1885C1H470JA16D | 47 pF 50 V C0G | `C_0603_1608Metric` | 1 (1): `PVA_CS` | 2 (2): `PVA_CSG` | CS filter |
| R119 | Panasonic ERJ-3RQF2R2V | 2.2 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_HD2` | 2 (2): `PVA_HD2_G` | gate R QH2 |
| C116 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_BT2` | 2 (2): `PVA_SW2` | bootstrap 2 |
| R120 | Panasonic ERJ-3RQF2R2V | 2.2 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_LD2` | 2 (2): `PVA_LD2_G` | gate R QL2 |
| C117 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_VCC` | 2 (2): `GND` | VCC bypass |
| R121 | Panasonic ERJ-3EKF10R0V | 10 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `PVA_BIAS` | BIAS from AUX12 (VCC from BIAS when >8 V) |
| C118 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_BIAS` | 2 (2): `GND` | BIAS bypass |
| R122 | Panasonic ERJ-3RQF2R2V | 2.2 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_LD1` | 2 (2): `PVA_LD1_G` | gate R QL1 |
| C119 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_BT1` | 2 (2): `PVA_SW1` | bootstrap 1 |
| R123 | Panasonic ERJ-3RQF2R2V | 2.2 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_HD1` | 2 (2): `PVA_HD1_G` | gate R QH1 |
| L101 | XAL1510-223MEB | 22 uH | `L_Coilcraft_XAL1510-223` | 1 (1): `PVA_SW1` | 2 (2): `PVA_SW2` | buck-boost inductor |
| C120 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | boost-side hot-loop output cap (next to QH2/QL2) |
| C121 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | boost-side hot-loop output cap (next to QH2/QL2) |
| C122 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | boost-side hot-loop output cap (next to QH2/QL2) |
| C123 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | boost-side hot-loop output cap (next to QH2/QL2) |
| NT101 | (PCB feature) |  | `NetTie-2_SMD_Pad0.5mm` | 1 (1): `AGND_A` | 2 (2): `GND` | single AGND-PGND tie under U3 PowerPAD |
| R124 | Panasonic ERJ-3EKF1103V | 110 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VA_IN` | 2 (2): `PVA_VDIV` | PV voltage divider (1/12) |
| R125 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `PVA_VDIV` | 2 (2): `GND` | PV voltage divider bottom |
| C124 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_VDIV` | 2 (2): `GND` | ADC/op-amp filter |
| R126 | Panasonic ERJ-3EKF1003V | 100 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_VDIV` | 2 (2): `PVA_INT_N` | integrator input R |
| C125 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_INT_N` | 2 (2): `PVA_PI` | integrator C (initial) |
| R127 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_PI` | 2 (2): `PVA_MPPT_OUT` | PI zero R (initial) |
| C126 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | op-amp decoupling |
| R128 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `MPPT_A_PWM` | 2 (2): `PVA_VSET1` | setpoint PWM filter stage 1 |
| C127 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_VSET1` | 2 (2): `GND` | setpoint filter |
| R129 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVA_VSET1` | 2 (2): `PVA_VSET` | setpoint PWM filter stage 2 |
| C128 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `PVA_VSET` | 2 (2): `GND` | setpoint filter |
| R130 | Panasonic ERJ-3EKF1003V | 100 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `MPPT_A_PWM` | default high = setpoint above Voc = zero current |

### J101 — Phoenix 1757242 (MSTBA 2,5/2-G-5,08) + plug 1757019 (MSTB 2,5/2-ST-5,08)

PV string input; plug side to roof harness. Symbol `Connector_Generic:Conn_01x02`, footprint `Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal`. Pins: Phoenix MSTB 2,5 series [S]; item numbers [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `PVA_IN` |
| 2 | 2 | `GND` |

### D101 — TPSMB39A

string surge/ESD clamp. Symbol `Device:D_Zener (used as unidirectional TVS)`, footprint `Diode_SMD:D_SMB`. Pins: Littelfuse TPSMB series DS [unverified]: VR 33.3 V, VBR 37.1 V min, VC 53.9 V; AEC-Q101 [S].

| Pin | Name | Net |
|---|---|---|
| 1 | K | `PVA_IN` |
| 2 | A | `GND` |

### U101 — LM74700QDBVRQ1

reverse-polarity ideal diode controller. Symbol `Power_Management:LM74700`, footprint `Package_TO_SOT_SMD:SOT-23-6`. Pins: LM74700-Q1 DS SNOSD17G, Fig. 5-1 / Table 5-1 (DBV) [P].

| Pin | Name | Net |
|---|---|---|
| 1 | VCAP | `PVA_VCAP` |
| 2 | GND | `GND` |
| 3 | EN | `PVA_IN` |
| 4 | CATHODE | `PVA_P` |
| 5 | GATE | `PVA_IDG` |
| 6 | ANODE | `PVA_IN` |

### Q101 — IAUC100N10S5L040

ideal-diode FET: S=input, D=output. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `PVA_IN` |
| 2 | S | `PVA_IN` |
| 3 | S | `PVA_IN` |
| 4 | G | `PVA_IDG` |
| 5 | D (pins 5-8 + tab) | `PVA_P` |

### R101 — WSK2512R0050FEA — 5 mOhm 1% 1 W 4-terminal

PV current shunt; Kelvin pins 2/3 feed U2 and the LM5176 CC loop. Symbol `Device:R_Shunt`, footprint `Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm`. Pins: Vishay WSK2512 DS doc 30108 (1 W, 5-200 mOhm, 4-terminal) [S]; pads per KiCad footprint.

| Pin | Name | Net |
|---|---|---|
| 1 | I+ (force) | `PVA_P` |
| 2 | S+ (sense) | `PVA_ISK_P` |
| 3 | S- (sense) | `PVA_ISK_N` |
| 4 | I- (force) | `VA_IN` |

### U102 — INA186A2QDBVRQ1

PV current amp, 50 V/V. Symbol `custom (kae:INA186_DBV)`, footprint `Package_TO_SOT_SMD:SOT-23-5`. Pins: INA186-Q1 DS SBOS386B, Fig. 5-2 / Table 5-1 (DBV) [P].

| Pin | Name | Net |
|---|---|---|
| 1 | GND | `GND` |
| 2 | OUT | `PVA_I_RAW` |
| 3 | VS | `+3V3` |
| 4 | IN- | `PVA_INA_N` |
| 5 | IN+ | `PVA_INA_P` |

### Q102 — SMMBTA42LT1G

MPPT current-setpoint sink (offsets ISNS). Symbol `Transistor_BJT:MMBTA42`, footprint `Package_TO_SOT_SMD:SOT-23`. Pins: onsemi MMBTA42 DS (300 V NPN, S-prefix AEC-Q101) [unverified]; KiCad Q_NPN_BEC.

| Pin | Name | Net |
|---|---|---|
| 1 | B | `PVA_SINK_B` |
| 2 | E | `PVA_SINK_E` |
| 3 | C | `PVA_ISNS_P` |

### U103 — LM5176QPWPRQ1

4-switch buck-boost, PV -> VINT; PGOOD unused (NC). Symbol `Regulator_Switching:LM5176PWP`, footprint `Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.5mm_ThermalVias`. Pins: LM5176-Q1 DS SNVSB46B, Fig. 5-1 / Table 5-1 [P].

| Pin | Name | Net |
|---|---|---|
| 1 | EN/UVLO | `PVA_EN` |
| 2 | VIN | `PVA_VINF` |
| 3 | VISNS | `PVA_VISNS` |
| 4 | MODE | `PVA_MODE` |
| 5 | DITH | `PVA_DITH` |
| 6 | RT/SYNC | `PVA_RT` |
| 7 | SLOPE | `PVA_SLOPE` |
| 8 | SS | `PVA_SS` |
| 9 | COMP | `PVA_COMP` |
| 10 | AGND | `AGND_A` |
| 11 | FB | `PVA_FB` |
| 12 | VOSNS | `VINT` |
| 13 | ISNS(-) | `PVA_ISNS_N` |
| 14 | ISNS(+) | `PVA_ISNS_P` |
| 15 | CSG | `PVA_CSG` |
| 16 | CS | `PVA_CS` |
| 17 | PGOOD | NC |
| 18 | SW2 | `PVA_SW2` |
| 19 | HDRV2 | `PVA_HD2` |
| 20 | BOOT2 | `PVA_BT2` |
| 21 | LDRV2 | `PVA_LD2` |
| 22 | PGND | `GND` |
| 23 | VCC | `PVA_VCC` |
| 24 | BIAS | `PVA_BIAS` |
| 25 | LDRV1 | `PVA_LD1` |
| 26 | BOOT1 | `PVA_BT1` |
| 27 | HDRV1 | `PVA_HD1` |
| 28 | SW1 | `PVA_SW1` |
| 29 | PowerPAD | `AGND_A` |

### D102 — BAT46WJ,115

PERMIT low pulls EN/UVLO below 1.17 V. Symbol `Diode:BAT46`, footprint `Diode_SMD:D_SOD-323F`. Pins: Nexperia BAT46WJ DS (SOD323F, 100 V, AEC-Q101) [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | K | `PERMIT` |
| 2 | A | `PVA_EN` |

### R116 — WSK2512R0100FEA — 10 mOhm 1% 1 W 4-terminal

PWM current sense in low-side source path. Symbol `Device:R_Shunt`, footprint `Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm`. Pins: Vishay WSK2512 DS doc 30108 [S].

| Pin | Name | Net |
|---|---|---|
| 1 | I+ (force) | `PVA_SRC` |
| 2 | S+ (sense) | `PVA_CS_K` |
| 3 | S- (sense) | `PVA_CSG_K` |
| 4 | I- (force) | `GND` |

### D103 — BAT46WJ,115

bootstrap diode 2. Symbol `Diode:BAT46`, footprint `Diode_SMD:D_SOD-323F`. Pins: Nexperia BAT46WJ DS (SOD323F, 100 V, AEC-Q101) [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | K | `PVA_BT2` |
| 2 | A | `PVA_VCC` |

### D104 — BAT46WJ,115

bootstrap diode 1. Symbol `Diode:BAT46`, footprint `Diode_SMD:D_SOD-323F`. Pins: Nexperia BAT46WJ DS (SOD323F, 100 V, AEC-Q101) [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | K | `PVA_BT1` |
| 2 | A | `PVA_VCC` |

### Q103 — IAUC100N10S5L040

QH1 buck high side. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `PVA_SW1` |
| 2 | S | `PVA_SW1` |
| 3 | S | `PVA_SW1` |
| 4 | G | `PVA_HD1_G` |
| 5 | D (pins 5-8 + tab) | `VA_IN` |

### Q104 — IAUC100N10S5L040

QL1 buck low side. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `PVA_SRC` |
| 2 | S | `PVA_SRC` |
| 3 | S | `PVA_SRC` |
| 4 | G | `PVA_LD1_G` |
| 5 | D (pins 5-8 + tab) | `PVA_SW1` |

### Q105 — IAUC100N10S5L040

QH2 boost sync rectifier. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `PVA_SW2` |
| 2 | S | `PVA_SW2` |
| 3 | S | `PVA_SW2` |
| 4 | G | `PVA_HD2_G` |
| 5 | D (pins 5-8 + tab) | `VINT` |

### Q106 — IAUC100N10S5L040

QL2 boost switch. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `PVA_SRC` |
| 2 | S | `PVA_SRC` |
| 3 | S | `PVA_SRC` |
| 4 | G | `PVA_LD2_G` |
| 5 | D (pins 5-8 + tab) | `PVA_SW2` |

### U104 — TLV9001QDBVRQ1

PV-voltage regulator (PI). Symbol `Amplifier_Operational:TLV9061xDBV (pin-compatible)`, footprint `Package_TO_SOT_SMD:SOT-23-5`. Pins: TLV900x-Q1 DS SBOS980G, Fig. 5-1 / Table 5-1 (DBV) [P].

| Pin | Name | Net |
|---|---|---|
| 1 | OUT | `PVA_MPPT_OUT` |
| 2 | V- | `GND` |
| 3 | IN+ | `PVA_VSET` |
| 4 | IN- | `PVA_INT_N` |
| 5 | V+ | `+3V3` |

## Block MPPT_B (board MB)

MPPT channel B: identical to channel A (refdes +100, nets PVA_->PVB_, VA_IN->VB_IN, AGND_A->AGND_B, MPPT_A_PWM->MPPT_B_PWM)

### Two-terminal parts

| Ref | MPN | Value / rating | Footprint | Pin 1 | Pin 2 | Note |
|---|---|---|---|---|---|---|
| C201 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_VCAP` | 2 (2): `PVB_IN` | LM74700 charge-pump cap (VCAP-ANODE) |
| C202 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_P` | 2 (2): `GND` | LM74700 CATHODE cap |
| R231 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_ISK_P` | 2 (2): `PVB_INA_P` | limits INA186 input current to <5 mA during 54 V TVS clamp (DS note 3); 3 nA IB -> 30 uV |
| R232 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_ISK_N` | 2 (2): `PVB_INA_N` | as above, matched |
| C203 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | U2 VS decoupling |
| R202 | Panasonic ERJ-3EKF1001V | 1 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_I_RAW` | 2 (2): `PVB_I_ADC` | ADC anti-alias |
| C204 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_I_ADC` | 2 (2): `GND` | ADC anti-alias |
| R203 | Panasonic ERJ-3EKF1001V | 1 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_ISK_P` | 2 (2): `PVB_ISNS_P` | R_iso: lets Q2 offset the CC-loop sense voltage |
| R204 | Panasonic ERJ-3EKF1000V | 100 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_ISK_N` | 2 (2): `PVB_ISNS_N` | CC-loop sense filter |
| C205 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_ISNS_P` | 2 (2): `PVB_ISNS_N` | CC-loop sense filter (differential) |
| R205 | Panasonic ERJ-3EKF2002V | 20 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_SINK_E` | 2 (2): `GND` | sink emitter resistor |
| R206 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_MPPT_OUT` | 2 (2): `PVB_SINK_B` | sink base resistor |
| C206 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VB_IN` | 2 (2): `GND` | buck-side hot-loop input cap (next to QH1/QL1) |
| C207 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VB_IN` | 2 (2): `GND` | buck-side hot-loop input cap |
| C208 | Panasonic EEH-ZA1J101P | 100 uF 63 V polymer-hybrid Al | `CP_Elec_10x10` | 1 (+): `VB_IN` | 2 (-): `GND` | input bulk |
| R207 | Panasonic ERJ-3EKF2003V | 200 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VB_IN` | 2 (2): `PVB_EN` | UVLO top: on 10.5 V, hyst 0.63 V |
| R208 | Panasonic ERJ-3EKF2742V | 27.4 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_EN` | 2 (2): `AGND_B` | UVLO bottom |
| R209 | Panasonic ERJ-3EKF10R0V | 10 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VB_IN` | 2 (2): `PVB_VINF` | VIN filter |
| C209 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_VINF` | 2 (2): `AGND_B` | VIN filter |
| R210 | Panasonic ERJ-3EKF2001V | 2 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VB_IN` | 2 (2): `PVB_VISNS` | VISNS series R (TI: required >40 V) |
| R211 | Panasonic ERJ-3EKF9312V | 93.1 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_MODE` | 2 (2): `AGND_B` | CCM, hiccup enabled |
| C210 | Murata GCM188R71H473KA55D | 47 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_DITH` | 2 (2): `AGND_B` | dither ~0.9 kHz modulation |
| R212 | Panasonic ERJ-3EKF4122V | 41.2 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_RT` | 2 (2): `AGND_B` | fsw 201 kHz |
| C211 | Murata GCM1885C1H681JA16D | 680 pF 50 V C0G | `C_0603_1608Metric` | 1 (1): `PVB_SLOPE` | 2 (2): `AGND_B` | slope comp |
| C212 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_SS` | 2 (2): `AGND_B` | soft start 16 ms; CC loop acts on this node |
| R213 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_COMP` | 2 (2): `PVB_COMP_RC` | Rc1 (initial; tune by sim) |
| C213 | Murata GCM188R71H473KA55D | 47 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_COMP_RC` | 2 (2): `AGND_B` | Cc1 (initial) |
| C214 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `PVB_COMP` | 2 (2): `AGND_B` | Cc2 (initial) |
| R214 | Panasonic ERJ-3EKF5623V | 562 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VINT` | 2 (2): `PVB_FB` | FB top, VARIANT: 562k (NiMH) / 499k (Li) |
| R215 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `PVB_FB` | 2 (2): `AGND_B` | FB bottom |
| R217 | Panasonic ERJ-3EKF1000V | 100 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_CS_K` | 2 (2): `PVB_CS` | CS filter |
| R218 | Panasonic ERJ-3EKF1000V | 100 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_CSG_K` | 2 (2): `PVB_CSG` | CSG filter |
| C215 | Murata GCM1885C1H470JA16D | 47 pF 50 V C0G | `C_0603_1608Metric` | 1 (1): `PVB_CS` | 2 (2): `PVB_CSG` | CS filter |
| R219 | Panasonic ERJ-3RQF2R2V | 2.2 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_HD2` | 2 (2): `PVB_HD2_G` | gate R QH2 |
| C216 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_BT2` | 2 (2): `PVB_SW2` | bootstrap 2 |
| R220 | Panasonic ERJ-3RQF2R2V | 2.2 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_LD2` | 2 (2): `PVB_LD2_G` | gate R QL2 |
| C217 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_VCC` | 2 (2): `GND` | VCC bypass |
| R221 | Panasonic ERJ-3EKF10R0V | 10 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `PVB_BIAS` | BIAS from AUX12 (VCC from BIAS when >8 V) |
| C218 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_BIAS` | 2 (2): `GND` | BIAS bypass |
| R222 | Panasonic ERJ-3RQF2R2V | 2.2 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_LD1` | 2 (2): `PVB_LD1_G` | gate R QL1 |
| C219 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_BT1` | 2 (2): `PVB_SW1` | bootstrap 1 |
| R223 | Panasonic ERJ-3RQF2R2V | 2.2 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_HD1` | 2 (2): `PVB_HD1_G` | gate R QH1 |
| L201 | XAL1510-223MEB | 22 uH | `L_Coilcraft_XAL1510-223` | 1 (1): `PVB_SW1` | 2 (2): `PVB_SW2` | buck-boost inductor |
| C220 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | boost-side hot-loop output cap (next to QH2/QL2) |
| C221 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | boost-side hot-loop output cap (next to QH2/QL2) |
| C222 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | boost-side hot-loop output cap (next to QH2/QL2) |
| C223 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | boost-side hot-loop output cap (next to QH2/QL2) |
| NT201 | (PCB feature) |  | `NetTie-2_SMD_Pad0.5mm` | 1 (1): `AGND_B` | 2 (2): `GND` | single AGND-PGND tie under U3 PowerPAD |
| R224 | Panasonic ERJ-3EKF1103V | 110 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VB_IN` | 2 (2): `PVB_VDIV` | PV voltage divider (1/12) |
| R225 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `PVB_VDIV` | 2 (2): `GND` | PV voltage divider bottom |
| C224 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_VDIV` | 2 (2): `GND` | ADC/op-amp filter |
| R226 | Panasonic ERJ-3EKF1003V | 100 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_VDIV` | 2 (2): `PVB_INT_N` | integrator input R |
| C225 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_INT_N` | 2 (2): `PVB_PI` | integrator C (initial) |
| R227 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_PI` | 2 (2): `PVB_MPPT_OUT` | PI zero R (initial) |
| C226 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | op-amp decoupling |
| R228 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `MPPT_B_PWM` | 2 (2): `PVB_VSET1` | setpoint PWM filter stage 1 |
| C227 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_VSET1` | 2 (2): `GND` | setpoint filter |
| R229 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PVB_VSET1` | 2 (2): `PVB_VSET` | setpoint PWM filter stage 2 |
| C228 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `PVB_VSET` | 2 (2): `GND` | setpoint filter |
| R230 | Panasonic ERJ-3EKF1003V | 100 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `MPPT_B_PWM` | default high = setpoint above Voc = zero current |

### J201 — Phoenix 1757242 (MSTBA 2,5/2-G-5,08) + plug 1757019 (MSTB 2,5/2-ST-5,08)

PV string input; plug side to roof harness. Symbol `Connector_Generic:Conn_01x02`, footprint `Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal`. Pins: Phoenix MSTB 2,5 series [S]; item numbers [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `PVB_IN` |
| 2 | 2 | `GND` |

### D201 — TPSMB39A

string surge/ESD clamp. Symbol `Device:D_Zener (used as unidirectional TVS)`, footprint `Diode_SMD:D_SMB`. Pins: Littelfuse TPSMB series DS [unverified]: VR 33.3 V, VBR 37.1 V min, VC 53.9 V; AEC-Q101 [S].

| Pin | Name | Net |
|---|---|---|
| 1 | K | `PVB_IN` |
| 2 | A | `GND` |

### U201 — LM74700QDBVRQ1

reverse-polarity ideal diode controller. Symbol `Power_Management:LM74700`, footprint `Package_TO_SOT_SMD:SOT-23-6`. Pins: LM74700-Q1 DS SNOSD17G, Fig. 5-1 / Table 5-1 (DBV) [P].

| Pin | Name | Net |
|---|---|---|
| 1 | VCAP | `PVB_VCAP` |
| 2 | GND | `GND` |
| 3 | EN | `PVB_IN` |
| 4 | CATHODE | `PVB_P` |
| 5 | GATE | `PVB_IDG` |
| 6 | ANODE | `PVB_IN` |

### Q201 — IAUC100N10S5L040

ideal-diode FET: S=input, D=output. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `PVB_IN` |
| 2 | S | `PVB_IN` |
| 3 | S | `PVB_IN` |
| 4 | G | `PVB_IDG` |
| 5 | D (pins 5-8 + tab) | `PVB_P` |

### R201 — WSK2512R0050FEA — 5 mOhm 1% 1 W 4-terminal

PV current shunt; Kelvin pins 2/3 feed U2 and the LM5176 CC loop. Symbol `Device:R_Shunt`, footprint `Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm`. Pins: Vishay WSK2512 DS doc 30108 (1 W, 5-200 mOhm, 4-terminal) [S]; pads per KiCad footprint.

| Pin | Name | Net |
|---|---|---|
| 1 | I+ (force) | `PVB_P` |
| 2 | S+ (sense) | `PVB_ISK_P` |
| 3 | S- (sense) | `PVB_ISK_N` |
| 4 | I- (force) | `VB_IN` |

### U202 — INA186A2QDBVRQ1

PV current amp, 50 V/V. Symbol `custom (kae:INA186_DBV)`, footprint `Package_TO_SOT_SMD:SOT-23-5`. Pins: INA186-Q1 DS SBOS386B, Fig. 5-2 / Table 5-1 (DBV) [P].

| Pin | Name | Net |
|---|---|---|
| 1 | GND | `GND` |
| 2 | OUT | `PVB_I_RAW` |
| 3 | VS | `+3V3` |
| 4 | IN- | `PVB_INA_N` |
| 5 | IN+ | `PVB_INA_P` |

### Q202 — SMMBTA42LT1G

MPPT current-setpoint sink (offsets ISNS). Symbol `Transistor_BJT:MMBTA42`, footprint `Package_TO_SOT_SMD:SOT-23`. Pins: onsemi MMBTA42 DS (300 V NPN, S-prefix AEC-Q101) [unverified]; KiCad Q_NPN_BEC.

| Pin | Name | Net |
|---|---|---|
| 1 | B | `PVB_SINK_B` |
| 2 | E | `PVB_SINK_E` |
| 3 | C | `PVB_ISNS_P` |

### U203 — LM5176QPWPRQ1

4-switch buck-boost, PV -> VINT; PGOOD unused (NC). Symbol `Regulator_Switching:LM5176PWP`, footprint `Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.5mm_ThermalVias`. Pins: LM5176-Q1 DS SNVSB46B, Fig. 5-1 / Table 5-1 [P].

| Pin | Name | Net |
|---|---|---|
| 1 | EN/UVLO | `PVB_EN` |
| 2 | VIN | `PVB_VINF` |
| 3 | VISNS | `PVB_VISNS` |
| 4 | MODE | `PVB_MODE` |
| 5 | DITH | `PVB_DITH` |
| 6 | RT/SYNC | `PVB_RT` |
| 7 | SLOPE | `PVB_SLOPE` |
| 8 | SS | `PVB_SS` |
| 9 | COMP | `PVB_COMP` |
| 10 | AGND | `AGND_B` |
| 11 | FB | `PVB_FB` |
| 12 | VOSNS | `VINT` |
| 13 | ISNS(-) | `PVB_ISNS_N` |
| 14 | ISNS(+) | `PVB_ISNS_P` |
| 15 | CSG | `PVB_CSG` |
| 16 | CS | `PVB_CS` |
| 17 | PGOOD | NC |
| 18 | SW2 | `PVB_SW2` |
| 19 | HDRV2 | `PVB_HD2` |
| 20 | BOOT2 | `PVB_BT2` |
| 21 | LDRV2 | `PVB_LD2` |
| 22 | PGND | `GND` |
| 23 | VCC | `PVB_VCC` |
| 24 | BIAS | `PVB_BIAS` |
| 25 | LDRV1 | `PVB_LD1` |
| 26 | BOOT1 | `PVB_BT1` |
| 27 | HDRV1 | `PVB_HD1` |
| 28 | SW1 | `PVB_SW1` |
| 29 | PowerPAD | `AGND_B` |

### D202 — BAT46WJ,115

PERMIT low pulls EN/UVLO below 1.17 V. Symbol `Diode:BAT46`, footprint `Diode_SMD:D_SOD-323F`. Pins: Nexperia BAT46WJ DS (SOD323F, 100 V, AEC-Q101) [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | K | `PERMIT` |
| 2 | A | `PVB_EN` |

### R216 — WSK2512R0100FEA — 10 mOhm 1% 1 W 4-terminal

PWM current sense in low-side source path. Symbol `Device:R_Shunt`, footprint `Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm`. Pins: Vishay WSK2512 DS doc 30108 [S].

| Pin | Name | Net |
|---|---|---|
| 1 | I+ (force) | `PVB_SRC` |
| 2 | S+ (sense) | `PVB_CS_K` |
| 3 | S- (sense) | `PVB_CSG_K` |
| 4 | I- (force) | `GND` |

### D203 — BAT46WJ,115

bootstrap diode 2. Symbol `Diode:BAT46`, footprint `Diode_SMD:D_SOD-323F`. Pins: Nexperia BAT46WJ DS (SOD323F, 100 V, AEC-Q101) [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | K | `PVB_BT2` |
| 2 | A | `PVB_VCC` |

### D204 — BAT46WJ,115

bootstrap diode 1. Symbol `Diode:BAT46`, footprint `Diode_SMD:D_SOD-323F`. Pins: Nexperia BAT46WJ DS (SOD323F, 100 V, AEC-Q101) [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | K | `PVB_BT1` |
| 2 | A | `PVB_VCC` |

### Q203 — IAUC100N10S5L040

QH1 buck high side. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `PVB_SW1` |
| 2 | S | `PVB_SW1` |
| 3 | S | `PVB_SW1` |
| 4 | G | `PVB_HD1_G` |
| 5 | D (pins 5-8 + tab) | `VB_IN` |

### Q204 — IAUC100N10S5L040

QL1 buck low side. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `PVB_SRC` |
| 2 | S | `PVB_SRC` |
| 3 | S | `PVB_SRC` |
| 4 | G | `PVB_LD1_G` |
| 5 | D (pins 5-8 + tab) | `PVB_SW1` |

### Q205 — IAUC100N10S5L040

QH2 boost sync rectifier. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `PVB_SW2` |
| 2 | S | `PVB_SW2` |
| 3 | S | `PVB_SW2` |
| 4 | G | `PVB_HD2_G` |
| 5 | D (pins 5-8 + tab) | `VINT` |

### Q206 — IAUC100N10S5L040

QL2 boost switch. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `PVB_SRC` |
| 2 | S | `PVB_SRC` |
| 3 | S | `PVB_SRC` |
| 4 | G | `PVB_LD2_G` |
| 5 | D (pins 5-8 + tab) | `PVB_SW2` |

### U204 — TLV9001QDBVRQ1

PV-voltage regulator (PI). Symbol `Amplifier_Operational:TLV9061xDBV (pin-compatible)`, footprint `Package_TO_SOT_SMD:SOT-23-5`. Pins: TLV900x-Q1 DS SBOS980G, Fig. 5-1 / Table 5-1 (DBV) [P].

| Pin | Name | Net |
|---|---|---|
| 1 | OUT | `PVB_MPPT_OUT` |
| 2 | V- | `GND` |
| 3 | IN+ | `PVB_VSET` |
| 4 | IN- | `PVB_INT_N` |
| 5 | V+ | `+3V3` |

## Block DCX (board MB)

VINT bus, half-bridge LLC-DCX (fixed ratio, open loop), T301 reinforced barrier, HV rectifier, HV output, temperature sensors

### Two-terminal parts

| Ref | MPN | Value / rating | Footprint | Pin 1 | Pin 2 | Note |
|---|---|---|---|---|---|---|
| C301 | Panasonic EEH-ZA1J101P | 100 uF 63 V polymer-hybrid Al | `CP_Elec_10x10` | 1 (+): `VINT` | 2 (-): `GND` | VINT bulk |
| C302 | Panasonic EEH-ZA1J101P | 100 uF 63 V polymer-hybrid Al | `CP_Elec_10x10` | 1 (+): `VINT` | 2 (-): `GND` | VINT bulk |
| C303 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | half-bridge DC-link MLCC (hot loop with Q301/Q302) |
| C304 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | half-bridge DC-link MLCC (hot loop with Q301/Q302) |
| C305 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | half-bridge DC-link MLCC (hot loop with Q301/Q302) |
| C306 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | half-bridge DC-link MLCC (hot loop with Q301/Q302) |
| C307 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | half-bridge DC-link MLCC (hot loop with Q301/Q302) |
| C308 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | half-bridge DC-link MLCC (hot loop with Q301/Q302) |
| C309 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | half-bridge DC-link MLCC (hot loop with Q301/Q302) |
| C310 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `VINT` | 2 (2): `GND` | half-bridge DC-link MLCC (hot loop with Q301/Q302) |
| C311 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `GND` | U301 VDD bulk |
| C312 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `GND` | U301 VDD HF |
| C313 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `PERMIT` | 2 (2): `GND` | EN filter (TI: 1 nF) |
| C314 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `DCX_HB` | 2 (2): `HB_SW` | bootstrap HB-HS |
| R301 | Panasonic ERJ-3RQF2R2V | 2.2 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `DCX_HO` | 2 (2): `DCX_HO_G` | gate R high side |
| R302 | Panasonic ERJ-3RQF2R2V | 2.2 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `DCX_LO` | 2 (2): `DCX_LO_G` | gate R low side |
| R303 | Panasonic ERJ-3EKF1000V | 100 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `DCX_HI` | 2 (2): `DCX_HI_F` | input filter |
| C315 | Murata GCM1885C1H101JA16D | 100 pF 50 V C0G | `C_0603_1608Metric` | 1 (1): `DCX_HI_F` | 2 (2): `GND` | input filter |
| R304 | Panasonic ERJ-3EKF1000V | 100 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `DCX_LI` | 2 (2): `DCX_LI_F` | input filter |
| C316 | Murata GCM1885C1H101JA16D | 100 pF 50 V C0G | `C_0603_1608Metric` | 1 (1): `DCX_LI_F` | 2 (2): `GND` | input filter |
| C317 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C318 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C319 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C320 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C321 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C322 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C323 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C324 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C325 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C326 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C327 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C328 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C329 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C330 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C331 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C332 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `VINT` | 2 (2): `DCX_MID` | resonant/split cap, upper leg (16 x 100 nF = 1.6 uF) |
| C333 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C334 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C335 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C336 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C337 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C338 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C339 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C340 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C341 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C342 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C343 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C344 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C345 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C346 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C347 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| C348 | TDK CGA5L1C0G2A104J160AC | 100 nF 100 V C0G (resonant) | `C_1206_3216Metric` | 1 (1): `DCX_MID` | 2 (2): `GND` | resonant/split cap, lower leg (16 x 100 nF = 1.6 uF) |
| R305 | Panasonic ERJ-8ENF1000V | 100 Ohm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `T1_S1` | 2 (2): `T1_SNB` | secondary RC snubber, DNP by default; value set at bench |
| C349 | TDK CGA5H4C0G2J221J115AA [unverified] | 220 pF 630 V C0G (snubber, DNP) | `C_1206_3216Metric` | 1 (1): `T1_SNB` | 2 (2): `T1_S2` | secondary RC snubber, DNP by default |
| C350 | TDK CGA6M4X7T2W224K200AE | 220 nF 450 V X7T | `C_1210_3225Metric` | 1 (1): `HV_P` | 2 (2): `HV_N` | HV output cap (6 x 220 nF) |
| C351 | TDK CGA6M4X7T2W224K200AE | 220 nF 450 V X7T | `C_1210_3225Metric` | 1 (1): `HV_P` | 2 (2): `HV_N` | HV output cap (6 x 220 nF) |
| C352 | TDK CGA6M4X7T2W224K200AE | 220 nF 450 V X7T | `C_1210_3225Metric` | 1 (1): `HV_P` | 2 (2): `HV_N` | HV output cap (6 x 220 nF) |
| C353 | TDK CGA6M4X7T2W224K200AE | 220 nF 450 V X7T | `C_1210_3225Metric` | 1 (1): `HV_P` | 2 (2): `HV_N` | HV output cap (6 x 220 nF) |
| C354 | TDK CGA6M4X7T2W224K200AE | 220 nF 450 V X7T | `C_1210_3225Metric` | 1 (1): `HV_P` | 2 (2): `HV_N` | HV output cap (6 x 220 nF) |
| C355 | TDK CGA6M4X7T2W224K200AE | 220 nF 450 V X7T | `C_1210_3225Metric` | 1 (1): `HV_P` | 2 (2): `HV_N` | HV output cap (6 x 220 nF) |
| R307 | Panasonic ERJ-3EKF1913V | 191 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VINT` | 2 (2): `VINT_DIV` | VINT ADC divider (1/20.1) |
| R308 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `VINT_DIV` | 2 (2): `GND` | VINT ADC divider |
| C356 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `VINT_DIV` | 2 (2): `GND` | ADC filter |
| RT301 | NTCG163JF103FTDS | 10 kOhm B3435 | `R_0603_1608Metric` | 1 (1): `NTC_HS` | 2 (2): `GND` | FW temperature sensor at Q301/Q302 thermal pad |
| R309 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `NTC_HS` | NTC pull-up (ratiometric to AVDD) |
| C357 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `NTC_HS` | 2 (2): `GND` | filter |
| RT302 | NTCG163JF103FTDS | 10 kOhm B3435 | `R_0603_1608Metric` | 1 (1): `NTC_T1` | 2 (2): `GND` | HW OTP sensor between T301 and Q301 (independent of RT301) |
| R310 | Panasonic ERA-3AEB2201V | 2.2 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `VREF2V5` | 2 (2): `NTC_T1` | NTC pull-up from 2.5 V reference |
| C358 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `NTC_T1` | 2 (2): `GND` | filter |

### Q301 — IAUC100N10S5L040

half-bridge high side. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `HB_SW` |
| 2 | S | `HB_SW` |
| 3 | S | `HB_SW` |
| 4 | G | `DCX_HO_G` |
| 5 | D (pins 5-8 + tab) | `VINT` |

### Q302 — IAUC100N10S5L040

half-bridge low side. Symbol `Transistor_FET:BSC040N10NS5 (same PG-TDSON-8 pinout)`, footprint `Package_TO_SOT_SMD:TDSON-8-1`. Pins: IAUC100N10S5L040 DS rev1.0 p1 (PG-TDSON-8); pin numbers per KiCad TDSON-8-1 pads [S].

| Pin | Name | Net |
|---|---|---|
| 1 | S | `GND` |
| 2 | S | `GND` |
| 3 | S | `GND` |
| 4 | G | `DCX_LO_G` |
| 5 | D (pins 5-8 + tab) | `HB_SW` |

### U301 — UCC27282QDRCRQ1

half-bridge driver; EN = PERMIT. Symbol `custom (kae:UCC27282_DRC)`, footprint `Package_SON:VSON-10-1EP_3x3mm_P0.5mm_EP1.65x2.4mm`. Pins: UCC27282-Q1 DS SLUSDN5D, Fig. 5-1 / Table 5-1 (DRC) [P].

| Pin | Name | Net |
|---|---|---|
| 1 | VDD | `AUX12` |
| 2 | NC | NC |
| 3 | HB | `DCX_HB` |
| 4 | HO | `DCX_HO` |
| 5 | HS | `HB_SW` |
| 6 | EN | `PERMIT` |
| 7 | HI | `DCX_HI_F` |
| 8 | LI | `DCX_LI_F` |
| 9 | VSS | `GND` |
| 10 | LO | `DCX_LO` |
| 11 | PAD (VSS only) | `GND` |

### T301 — custom: TDK EPCOS ETD 39 core set N97, gapped for Lm=40 uH; 20-pin coil former; Np=6 (litz), Ns=66 (TIW)

reinforced LV/HV barrier; n = Ns/Np = 11; pins 5-10 and 12-19 have no pad. Symbol `custom (kae:T_ETD39_DCX)`, footprint `custom (kae:ETD39_20pin_DCX; pad grid per TDK ETD 39 coil-former drawing; unused pins have no pad)`. Pins: design spec in DESIGN.md §7.3 [I]; pin assignment is ours (custom part).

| Pin | Name | Net |
|---|---|---|
| 1 | P_START | `HB_SW` |
| 2 | P_START | `HB_SW` |
| 3 | P_END | `DCX_MID` |
| 4 | P_END | `DCX_MID` |
| 11 | S_START | `T1_S1` |
| 20 | S_END | `T1_S2` |

### D301 — VS-6ESH06HM3/86A

bridge, upper. Symbol `custom (kae:D_TO277A: 1=A,2=A,3=K)`, footprint `Package_TO_SOT_SMD:TO-277A`. Pins: VS-6ESH06HM3 DS doc 94985 p1 [P]; pads per KiCad TO-277A.

| Pin | Name | Net |
|---|---|---|
| 1 | A (anode 1) | `T1_S1` |
| 2 | A (anode 2) | `T1_S1` |
| 3 | K (cathode, tab) | `HV_P` |

### D302 — VS-6ESH06HM3/86A

bridge, upper. Symbol `custom (kae:D_TO277A: 1=A,2=A,3=K)`, footprint `Package_TO_SOT_SMD:TO-277A`. Pins: VS-6ESH06HM3 DS doc 94985 p1 [P]; pads per KiCad TO-277A.

| Pin | Name | Net |
|---|---|---|
| 1 | A (anode 1) | `T1_S2` |
| 2 | A (anode 2) | `T1_S2` |
| 3 | K (cathode, tab) | `HV_P` |

### D303 — VS-6ESH06HM3/86A

bridge, lower. Symbol `custom (kae:D_TO277A: 1=A,2=A,3=K)`, footprint `Package_TO_SOT_SMD:TO-277A`. Pins: VS-6ESH06HM3 DS doc 94985 p1 [P]; pads per KiCad TO-277A.

| Pin | Name | Net |
|---|---|---|
| 1 | A (anode 1) | `HV_N` |
| 2 | A (anode 2) | `HV_N` |
| 3 | K (cathode, tab) | `T1_S1` |

### D304 — VS-6ESH06HM3/86A

bridge, lower. Symbol `custom (kae:D_TO277A: 1=A,2=A,3=K)`, footprint `Package_TO_SOT_SMD:TO-277A`. Pins: VS-6ESH06HM3 DS doc 94985 p1 [P]; pads per KiCad TO-277A.

| Pin | Name | Net |
|---|---|---|
| 1 | A (anode 1) | `HV_N` |
| 2 | A (anode 2) | `HV_N` |
| 3 | K (cathode, tab) | `T1_S2` |

### J301 — Phoenix GMSTBA 2,5/2-G-7,62 + plug GMSTB 2,5/2-ST-7,62 (item nos. [unverified])

HV output to orange cable -> battery-end unit J901. Symbol `Connector_Generic:Conn_01x02`, footprint `Connector_Phoenix_GMSTB:PhoenixContact_GMSTBA_2,5_2-G-7,62_1x02_P7.62mm_Horizontal`. Pins: Phoenix GMSTB 2,5 (7.62 mm pitch, high-voltage series) [S].

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `HV_P` |
| 2 | 2 | `HV_N` |

## Block HVSENSE (board MB)

Two independent reinforced isolated HV voltage sense paths (control, OVP)

### Two-terminal parts

| Ref | MPN | Value / rating | Footprint | Pin 1 | Pin 2 | Note |
|---|---|---|---|---|---|---|
| R401 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HV_P` | 2 (2): `HVS1_D1` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R402 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HVS1_D1` | 2 (2): `HVS1_D2` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R403 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HVS1_D2` | 2 (2): `HVS1_D3` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R404 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HVS1_D3` | 2 (2): `HVS1_D4` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R405 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HVS1_D4` | 2 (2): `HVS1_D5` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R406 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HVS1_D5` | 2 (2): `HVS1_INP` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R407 | Panasonic ERA-3AEB2002V | 20 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `HVS1_INP` | 2 (2): `HV_N` | HV divider bottom: ratio 301 |
| C401 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `HVS1_INP` | 2 (2): `HV_N` | input filter |
| C402 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `HVS1_DCDC` | 2 (2): `HV_N` | DCDC_OUT bulk (TI C2) |
| C403 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `HVS1_DCDC` | 2 (2): `HV_N` | DCDC_OUT HF (TI C3) |
| C404 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `HVS1_DCDC` | 2 (2): `HV_N` | HLDO_IN (TI C1) |
| C405 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `HVS1_HLDO` | 2 (2): `HV_N` | HLDO_OUT (TI C5) |
| C406 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `HVS1_HLDO` | 2 (2): `HV_N` | HLDO_OUT HF (TI C6) |
| C407 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `HVS1_LDO` | 2 (2): `GND` | DCDC_IN (TI C4) |
| C408 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | VDD HF (TI C8) |
| C409 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | VDD bulk (TI C9) |
| R408 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `HVS1_OUTP` | 2 (2): `HVS1_DA_P` | diff amp |
| R409 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `HVS1_DA_P` | 2 (2): `GND` | gain-setting, G = 1.00 |
| R410 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `HVS1_OUTN` | 2 (2): `HVS1_DA_N` | diff amp |
| R411 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `HVS1_DA_N` | 2 (2): `HVS1_DA_OUT` | gain-setting, G = 1.00 |
| C410 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | op-amp decoupling |
| R412 | Panasonic ERJ-3EKF1001V | 1 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `HVS1_DA_OUT` | 2 (2): `HV_V_ADC` | ADC filter |
| C411 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `HV_V_ADC` | 2 (2): `GND` | ADC filter |
| R421 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HV_P` | 2 (2): `HVS2_D1` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R422 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HVS2_D1` | 2 (2): `HVS2_D2` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R423 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HVS2_D2` | 2 (2): `HVS2_D3` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R424 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HVS2_D3` | 2 (2): `HVS2_D4` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R425 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HVS2_D4` | 2 (2): `HVS2_D5` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R426 | Panasonic ERJ-8ENF1004V | 1 MOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `HVS2_D5` | 2 (2): `HVS2_INP` | HV divider top string (6 x 1 MOhm, 44 V each) |
| R427 | Panasonic ERA-3AEB2002V | 20 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `HVS2_INP` | 2 (2): `HV_N` | HV divider bottom: ratio 301 |
| C421 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `HVS2_INP` | 2 (2): `HV_N` | input filter |
| C422 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `HVS2_DCDC` | 2 (2): `HV_N` | DCDC_OUT bulk (TI C2) |
| C423 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `HVS2_DCDC` | 2 (2): `HV_N` | DCDC_OUT HF (TI C3) |
| C424 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `HVS2_DCDC` | 2 (2): `HV_N` | HLDO_IN (TI C1) |
| C425 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `HVS2_HLDO` | 2 (2): `HV_N` | HLDO_OUT (TI C5) |
| C426 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `HVS2_HLDO` | 2 (2): `HV_N` | HLDO_OUT HF (TI C6) |
| C427 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `HVS2_LDO` | 2 (2): `GND` | DCDC_IN (TI C4) |
| C428 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | VDD HF (TI C8) |
| C429 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | VDD bulk (TI C9) |
| R428 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `HVS2_OUTP` | 2 (2): `HVS2_DA_P` | diff amp |
| R429 | Panasonic ERA-3AEB1152V | 11.5 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `HVS2_DA_P` | 2 (2): `GND` | VARIANT gain: 11.5k (G=1.15, trip 261.7 V NiMH) / 13.0k (G=1.30, trip 231.5 V Li) |
| R430 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `HVS2_OUTN` | 2 (2): `HVS2_DA_N` | diff amp |
| R431 | Panasonic ERA-3AEB1152V | 11.5 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `HVS2_DA_N` | 2 (2): `HVS2_DA_OUT` | VARIANT gain: 11.5k (G=1.15, trip 261.7 V NiMH) / 13.0k (G=1.30, trip 231.5 V Li) |
| C430 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | op-amp decoupling |
| R432 | Panasonic ERJ-3EKF1001V | 1 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `HVS2_DA_OUT` | 2 (2): `HV_V_OVP` | comparator input filter |
| C431 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `HV_V_OVP` | 2 (2): `GND` | comparator input filter |

### U401 — AMC3330QDWERQ1

control/telemetry path; DIAG (open drain) -> PERMIT. Symbol `Isolator_Analog:AMC3330`, footprint `Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm`. Pins: AMC3330-Q1 DS SBASA35B, Fig. 4-1 / Table 4-1 [P].

| Pin | Name | Net |
|---|---|---|
| 1 | DCDC_OUT | `HVS1_DCDC` |
| 2 | DCDC_HGND | `HV_N` |
| 3 | HLDO_IN | `HVS1_DCDC` |
| 4 | NC | NC |
| 5 | HLDO_OUT | `HVS1_HLDO` |
| 6 | INP | `HVS1_INP` |
| 7 | INN | `HV_N` |
| 8 | HGND | `HV_N` |
| 9 | GND | `GND` |
| 10 | OUTN | `HVS1_OUTN` |
| 11 | OUTP | `HVS1_OUTP` |
| 12 | VDD | `+3V3` |
| 13 | LDO_OUT | `HVS1_LDO` |
| 14 | DIAG | `PERMIT` |
| 15 | DCDC_GND | `GND` |
| 16 | DCDC_IN | `HVS1_LDO` |

### U402 — TLV9001QDBVRQ1

difference amp, output = G*(OUTP-OUTN). Symbol `Amplifier_Operational:TLV9061xDBV (pin-compatible)`, footprint `Package_TO_SOT_SMD:SOT-23-5`. Pins: TLV900x-Q1 DS SBOS980G, Fig. 5-1 / Table 5-1 (DBV) [P].

| Pin | Name | Net |
|---|---|---|
| 1 | OUT | `HVS1_DA_OUT` |
| 2 | V- | `GND` |
| 3 | IN+ | `HVS1_DA_P` |
| 4 | IN- | `HVS1_DA_N` |
| 5 | V+ | `+3V3` |

### U421 — AMC3330QDWERQ1

independent OVP path; DIAG (open drain) -> PERMIT. Symbol `Isolator_Analog:AMC3330`, footprint `Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm`. Pins: AMC3330-Q1 DS SBASA35B, Fig. 4-1 / Table 4-1 [P].

| Pin | Name | Net |
|---|---|---|
| 1 | DCDC_OUT | `HVS2_DCDC` |
| 2 | DCDC_HGND | `HV_N` |
| 3 | HLDO_IN | `HVS2_DCDC` |
| 4 | NC | NC |
| 5 | HLDO_OUT | `HVS2_HLDO` |
| 6 | INP | `HVS2_INP` |
| 7 | INN | `HV_N` |
| 8 | HGND | `HV_N` |
| 9 | GND | `GND` |
| 10 | OUTN | `HVS2_OUTN` |
| 11 | OUTP | `HVS2_OUTP` |
| 12 | VDD | `+3V3` |
| 13 | LDO_OUT | `HVS2_LDO` |
| 14 | DIAG | `PERMIT` |
| 15 | DCDC_GND | `GND` |
| 16 | DCDC_IN | `HVS2_LDO` |

### U422 — TLV9001QDBVRQ1

difference amp, output = G*(OUTP-OUTN). Symbol `Amplifier_Operational:TLV9061xDBV (pin-compatible)`, footprint `Package_TO_SOT_SMD:SOT-23-5`. Pins: TLV900x-Q1 DS SBOS980G, Fig. 5-1 / Table 5-1 (DBV) [P].

| Pin | Name | Net |
|---|---|---|
| 1 | OUT | `HVS2_DA_OUT` |
| 2 | V- | `GND` |
| 3 | IN+ | `HVS2_DA_P` |
| 4 | IN- | `HVS2_DA_N` |
| 5 | V+ | `+3V3` |

## Block SAFETY (board MB)

Threshold reference, comparators (OVP/OTP), OVP latch, supervisor/watchdog, PERMIT wired-AND, relay/fan/LED drivers

### Two-terminal parts

| Ref | MPN | Value / rating | Footprint | Pin 1 | Pin 2 | Note |
|---|---|---|---|---|---|---|
| R501 | Panasonic ERJ-3EKF6801V | 6.8 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `VREF2V5` | reference bias ~1.4 mA |
| C501 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `VREF2V5` | 2 (2): `GND` | reference bypass |
| R502 | Panasonic ERA-3AEB2491V | 2.49 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `VREF2V5` | 2 (2): `VTH2V0` | 2.000 V threshold |
| R503 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `VTH2V0` | 2 (2): `GND` | 2.000 V threshold |
| C502 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `VTH2V0` | 2 (2): `GND` | threshold filter |
| C503 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `GND` | comparator decoupling |
| R504 | Panasonic ERJ-3EKF2373V | 237 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `VINT` | 2 (2): `VINT_OVP` | VARIANT: 237k (trip 49.4 V NiMH) / 210k (trip 44.0 V Li) |
| R505 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `VINT_OVP` | 2 (2): `GND` | VINT OVP divider bottom |
| C504 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `VINT_OVP` | 2 (2): `GND` | filter |
| R506 | Panasonic ERA-3AEB2492V | 24.9 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `VREF2V5` | 2 (2): `VTH_OT1` | T1 OTP threshold 0.716 V (~105 C) |
| R507 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `VTH_OT1` | 2 (2): `GND` | T1 OTP threshold |
| R508 | Panasonic ERJ-3EKF1003V | 100 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PERMIT` | 2 (2): `NTC_T1` | T1 OTP hysteresis (~3 K) |
| R509 | Panasonic ERA-3AEB2432V | 24.3 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `VREF2V5` | 2 (2): `VTH_OTP` | pack OTP threshold 0.729 V (~50 C) |
| R510 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `VTH_OTP` | 2 (2): `GND` | pack OTP threshold |
| R511 | Panasonic ERJ-3EKF3303V | 330 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `PERMIT` | 2 (2): `NTC_PACK` | pack OTP hysteresis (~1.5 K) |
| R512 | Panasonic ERA-3AEB1002V | 10 kOhm 0.1% 0603 (0.1 W, 75 V, 25 ppm/K) | `R_0603_1608Metric` | 1 (1): `VREF2V5` | 2 (2): `NTC_PACK` | pack NTC pull-up |
| C505 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `NTC_PACK` | 2 (2): `GND` | harness filter |
| R514 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `OVP_TRIP_N` | OVP trip pull-up |
| C506 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `OVP_TRIP_N` | 2 (2): `GND` | 10 us glitch filter |
| C507 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | latch decoupling |
| C508 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | supervisor decoupling |
| R515 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `TPS_CWD` | CWD = 10k to VDD (window 9/109 ms with SET1=SET0=0) |
| R516 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `RESET_N` | RESET pull-up |
| R517 | Panasonic ERJ-3EKF1001V | 1 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `WDO_N` | 2 (2): `MCLR_N` | watchdog resets MCU; 1k lets ICSP override |
| R518 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `MCU_RUN` | 2 (2): `PERMIT` | PERMIT is sourced only by MCU_RUN |
| R519 | Panasonic ERJ-3EKF1003V | 100 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `MCU_RUN` | 2 (2): `GND` | MCU in reset -> MCU_RUN low -> PERMIT low |
| C509 | Murata GCM1885C1H102JA16D | 1 nF 50 V C0G | `C_0603_1608Metric` | 1 (1): `PERMIT` | 2 (2): `GND` | PERMIT noise filter |
| R520 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `RELAY_REQ` | 2 (2): `K_IN` | relay drive = RELAY_REQ AND PERMIT |
| C510 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `GND` | COM decoupling |
| R521 | Panasonic ERJ-3EKF2001V | 2 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `LED_OK_A` | LED current ~5 mA |
| R522 | Panasonic ERJ-3EKF2001V | 2 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `LED_FLT_A` | LED current ~5 mA |

### U501 — LM4040QBIM3X2.5/NOPB — 2.500 V 0.2%

threshold reference, fed from AUX12 (not +3V3). Symbol `Reference_Voltage:LM4040DBZ-2.5`, footprint `Package_TO_SOT_SMD:SOT-23`. Pins: LM4040-N-Q1 DS SNOS633N, Fig. 4-1 (DBZ) [P].

| Pin | Name | Net |
|---|---|---|
| 1 | + (K) | `VREF2V5` |
| 2 | - (A) | `GND` |
| 3 | * (NC; float or tie to 2) | NC |

### U502 — LM2901BQDRQ1

ch1 HV OVP, ch2 VINT OVP (both latch); ch3 T1 OTP, ch4 pack OTP (both non-latching -> PERMIT). Symbol `Comparator:LM2901`, footprint `Package_SO:SOIC-14_3.9x8.7mm_P1.27mm`. Pins: LM2901B-Q1 DS SLCS142H, Fig. 4-1 (D package) [P].

| Pin | Name | Net |
|---|---|---|
| 1 | 1OUT | `OVP_TRIP_N` |
| 2 | 2OUT | `OVP_TRIP_N` |
| 3 | VCC | `AUX12` |
| 4 | 2IN- | `VINT_OVP` |
| 5 | 2IN+ | `VTH2V0` |
| 6 | 1IN- | `HV_V_OVP` |
| 7 | 1IN+ | `VTH2V0` |
| 8 | 3IN- | `VTH_OT1` |
| 9 | 3IN+ | `NTC_T1` |
| 10 | 4IN- | `VTH_OTP` |
| 11 | 4IN+ | `NTC_PACK` |
| 12 | GND | `GND` |
| 13 | 4OUT | `PERMIT` |
| 14 | 3OUT | `PERMIT` |

### U503 — SN74LVC2G74QDCURQ1

OVP latch: set by ~PRE, cleared only by power-on RESET_N. Symbol `74xGxx:74LVC2G74`, footprint `Package_SO:VSSOP-8_2.3x2mm_P0.5mm`. Pins: SN74LVC2G74-Q1 DS SCES563C, DCU pinout p1 [P].

| Pin | Name | Net |
|---|---|---|
| 1 | CLK | `GND` |
| 2 | D | `GND` |
| 3 | ~Q | `LATCH_QN` |
| 4 | GND | `GND` |
| 5 | Q | `LATCH_Q` |
| 6 | ~CLR | `RESET_N` |
| 7 | ~PRE | `OVP_TRIP_N` |
| 8 | VCC | `+3V3` |

### D501 — BAT46WJ,115

latched OVP pulls PERMIT low (wired-AND). Symbol `Diode:BAT46`, footprint `Diode_SMD:D_SOD-323F`. Pins: Nexperia BAT46WJ DS (SOD323F, 100 V, AEC-Q101) [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | K | `LATCH_QN` |
| 2 | A | `PERMIT` |

### U504 — TPS3850G33QDRCRQ1

3.3 V supervisor + window watchdog 9-109 ms; CRST NC = 200 ms. Symbol `custom (kae:TPS3850_DRC)`, footprint `Package_SON:VSON-10-1EP_3x3mm_P0.5mm_EP1.65x2.4mm`. Pins: TPS3850-Q1 DS SBVS264B, Fig. 5-1 / Table 5-1 [P].

| Pin | Name | Net |
|---|---|---|
| 1 | VDD | `+3V3` |
| 2 | CWD | `TPS_CWD` |
| 3 | SET0 | `GND` |
| 4 | CRST | NC |
| 5 | GND | `GND` |
| 6 | SET1 | `GND` |
| 7 | WDI | `WDI` |
| 8 | WDO | `WDO_N` |
| 9 | RESET | `RESET_N` |
| 10 | SENSE | `+3V3` |
| 11 | PAD | `GND` |

### D502 — BAT46WJ,115

supervisor RESET also resets MCU (latch CLR stays separate). Symbol `Diode:BAT46`, footprint `Diode_SMD:D_SOD-323F`. Pins: Nexperia BAT46WJ DS (SOD323F, 100 V, AEC-Q101) [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | K | `RESET_N` |
| 2 | A | `MCLR_N` |

### D503 — BAT46WJ,115

relay AND gate. Symbol `Diode:BAT46`, footprint `Diode_SMD:D_SOD-323F`. Pins: Nexperia BAT46WJ DS (SOD323F, 100 V, AEC-Q101) [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | K | `PERMIT` |
| 2 | A | `K_IN` |

### U505 — TPL7407LAQPWRQ1

low-side drivers with internal flyback clamps to COM. Symbol `Transistor_Array:TPL7407LAPW`, footprint `Package_SO:TSSOP-16_4.4x5mm_P0.65mm`. Pins: TPL7407LA-Q1 DS SLRS074, PW pinout [P].

| Pin | Name | Net |
|---|---|---|
| 1 | IN1 | `K_IN` |
| 2 | IN2 | `K_IN` |
| 3 | IN3 | `FAN_PWM` |
| 4 | IN4 | `PERMIT` |
| 5 | IN5 | `LATCH_Q` |
| 6 | IN6 | `GND` |
| 7 | IN7 | `GND` |
| 8 | GND | `GND` |
| 9 | COM | `AUX12` |
| 10 | OUT7 | NC |
| 11 | OUT6 | NC |
| 12 | OUT5 | `LED_FLT_K` |
| 13 | OUT4 | `LED_OK_K` |
| 14 | OUT3 | `FAN_N` |
| 15 | OUT2 | `K2_COIL_N` |
| 16 | OUT1 | `K1_COIL_N` |

### D504 — any AEC-Q101 green 0603 LED (e.g. OSRAM LG L29K) [unverified]

green: PERMIT high. Symbol `Device:LED`, footprint `LED_SMD:LED_0603_1608Metric`. Pins: generic LED, K=1 A=2 per KiCad Device:LED.

| Pin | Name | Net |
|---|---|---|
| 1 | K | `LED_OK_K` |
| 2 | A | `LED_OK_A` |

### D505 — any AEC-Q101 red 0603 LED (e.g. OSRAM LS L29K) [unverified]

red: OVP latched. Symbol `Device:LED`, footprint `LED_SMD:LED_0603_1608Metric`. Pins: generic LED, K=1 A=2 per KiCad Device:LED.

| Pin | Name | Net |
|---|---|---|
| 1 | K | `LED_FLT_K` |
| 2 | A | `LED_FLT_A` |

## Block AUX (board MB)

PV-powered auxiliary supplies AUX12 and +3V3

### Two-terminal parts

| Ref | MPN | Value / rating | Footprint | Pin 1 | Pin 2 | Note |
|---|---|---|---|---|---|---|
| C601 | TDK CGA6P3X7S2A475K250AB | 4.7 uF 100 V X7S | `C_1210_3225Metric` | 1 (1): `AUX_IN` | 2 (2): `GND` | U601 input bulk |
| C602 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `AUX_IN` | 2 (2): `GND` | U601 input HF |
| R601 | Panasonic ERJ-3EKF9092V | 90.9 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX_IN` | 2 (2): `AUX_EN` | EN/UVLO: start ~15 V |
| R602 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX_EN` | 2 (2): `GND` | EN/UVLO |
| R603 | Panasonic ERJ-3EKF1003V | 100 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX12_RON` | 2 (2): `GND` | fsw = 12*2500/100 = 300 kHz |
| C603 | Murata GCM188R71H222KA37D | 2.2 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `AUX12_BST` | 2 (2): `AUX12_SW` | BST cap (TI: 2.2 nF 50 V X7R) |
| L601 | MSS1210-104KED | 100 uH | `L_Coilcraft_MSS1210-XXX` | 1 (1): `AUX12_SW` | 2 (2): `AUX12` | AUX12 inductor |
| C604 | Murata GCM32ER71E106KA57L | 10 uF 25 V X7R | `C_1210_3225Metric` | 1 (1): `AUX12` | 2 (2): `GND` | AUX12 output |
| C605 | Murata GCM32ER71E106KA57L | 10 uF 25 V X7R | `C_1210_3225Metric` | 1 (1): `AUX12` | 2 (2): `GND` | AUX12 output |
| R604 | Panasonic ERJ-3EKF9092V | 90.9 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `AUX12_FB` | FB top: 12.1 V |
| R605 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX12_FB` | 2 (2): `GND` | FB bottom |
| R606 | Panasonic ERJ-3EKF1503V | 150 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX12_SW` | 2 (2): `AUX12_RA` | type-3 ripple RA |
| C606 | Murata GCM188R71H222KA37D | 2.2 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `AUX12_RA` | 2 (2): `AUX12` | type-3 ripple CA |
| C607 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `AUX12_RA` | 2 (2): `AUX12_FB` | type-3 ripple CB |
| C608 | Murata GCM32ER71E106KA57L | 10 uF 25 V X7R | `C_1210_3225Metric` | 1 (1): `AUX12` | 2 (2): `GND` | U602 input |
| C609 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `GND` | U602 input HF |
| R607 | Panasonic ERJ-3EKF4992V | 49.9 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `AUX12` | 2 (2): `V33_EN` | EN/UVLO: start ~9 V |
| R608 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `V33_EN` | 2 (2): `GND` | EN/UVLO |
| R609 | Panasonic ERJ-3EKF2742V | 27.4 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `V33_RON` | 2 (2): `GND` | fsw = 3.3*2500/27.4 = 301 kHz |
| C610 | Murata GCM188R71H222KA37D | 2.2 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `V33_BST` | 2 (2): `V33_SW` | BST cap |
| L602 | MSS1048-333MLB | 33 uH | `L_Coilcraft_MSS1048-XXX` | 1 (1): `V33_SW` | 2 (2): `+3V3` | +3V3 inductor |
| C611 | Murata GCM32ER71E106KA57L | 10 uF 25 V X7R | `C_1210_3225Metric` | 1 (1): `+3V3` | 2 (2): `GND` | +3V3 output |
| C612 | Murata GCM32ER71E106KA57L | 10 uF 25 V X7R | `C_1210_3225Metric` | 1 (1): `+3V3` | 2 (2): `GND` | +3V3 output |
| R610 | Panasonic ERJ-3EKF1742V | 17.4 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `V33_FB` | FB top: 3.29 V |
| R611 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `V33_FB` | 2 (2): `GND` | FB bottom |
| R612 | Panasonic ERJ-3EKF1503V | 150 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `V33_SW` | 2 (2): `V33_RA` | type-3 ripple RA |
| C613 | Murata GCM188R71H222KA37D | 2.2 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `V33_RA` | 2 (2): `+3V3` | type-3 ripple CA |
| C614 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `V33_RA` | 2 (2): `V33_FB` | type-3 ripple CB |

### D601 — VS-6ESH06HM3/86A

aux OR-ing from string A. Symbol `custom (kae:D_TO277A: 1=A,2=A,3=K)`, footprint `Package_TO_SOT_SMD:TO-277A`. Pins: VS-6ESH06HM3 DS doc 94985 p1 [P]; pads per KiCad TO-277A.

| Pin | Name | Net |
|---|---|---|
| 1 | A (anode 1) | `PVA_P` |
| 2 | A (anode 2) | `PVA_P` |
| 3 | K (cathode, tab) | `AUX_IN` |

### D602 — VS-6ESH06HM3/86A

aux OR-ing from string B. Symbol `custom (kae:D_TO277A: 1=A,2=A,3=K)`, footprint `Package_TO_SOT_SMD:TO-277A`. Pins: VS-6ESH06HM3 DS doc 94985 p1 [P]; pads per KiCad TO-277A.

| Pin | Name | Net |
|---|---|---|
| 1 | A (anode 1) | `PVB_P` |
| 2 | A (anode 2) | `PVB_P` |
| 3 | K (cathode, tab) | `AUX_IN` |

### D603 — VS-6ESH06HM3/86A

aux OR-ing from VINT. Symbol `custom (kae:D_TO277A: 1=A,2=A,3=K)`, footprint `Package_TO_SOT_SMD:TO-277A`. Pins: VS-6ESH06HM3 DS doc 94985 p1 [P]; pads per KiCad TO-277A.

| Pin | Name | Net |
|---|---|---|
| 1 | A (anode 1) | `VINT` |
| 2 | A (anode 2) | `VINT` |
| 3 | K (cathode, tab) | `AUX_IN` |

### U601 — LM5164QDDARQ1

AUX12 buck; PGOOD unused (NC). Symbol `Regulator_Switching:LM5164DDA`, footprint `Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm_ThermalVias`. Pins: LM5164-Q1 DS SNVSB51C, Fig. 4-1 / Table 4-1 [P].

| Pin | Name | Net |
|---|---|---|
| 1 | GND | `GND` |
| 2 | VIN | `AUX_IN` |
| 3 | EN/UVLO | `AUX_EN` |
| 4 | RON | `AUX12_RON` |
| 5 | FB | `AUX12_FB` |
| 6 | PGOOD | NC |
| 7 | BST | `AUX12_BST` |
| 8 | SW | `AUX12_SW` |
| 9 | EP | `GND` |

### U602 — LM5164QDDARQ1

+3V3 buck; PGOOD unused (NC). Symbol `Regulator_Switching:LM5164DDA`, footprint `Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm_ThermalVias`. Pins: LM5164-Q1 DS SNVSB51C, Fig. 4-1 / Table 4-1 [P].

| Pin | Name | Net |
|---|---|---|
| 1 | GND | `GND` |
| 2 | VIN | `AUX12` |
| 3 | EN/UVLO | `V33_EN` |
| 4 | RON | `V33_RON` |
| 5 | FB | `V33_FB` |
| 6 | PGOOD | NC |
| 7 | BST | `V33_BST` |
| 8 | SW | `V33_SW` |
| 9 | EP | `GND` |

## Block MCU (board MB)

dsPIC33CK MCU, ICSP/log header, car IG/READY input, harness and fan connectors, mounting

### Two-terminal parts

| Ref | MPN | Value / rating | Footprint | Pin 1 | Pin 2 | Note |
|---|---|---|---|---|---|---|
| R701 | Panasonic ERJ-3EKF10R0V | 10 Ohm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `+3V3A` | AVDD filter |
| C701 | Murata GCM188R71E105KA64D | 1 uF 25 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3A` | 2 (2): `GND` | AVDD bulk |
| C702 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3A` | 2 (2): `GND` | AVDD HF |
| C703 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | VDD pin 7 |
| C704 | Murata GCM188R72A104KA64D | 100 nF 100 V X7R | `C_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `GND` | VDD pin 20 |
| C705 | Murata GCM32ER71E106KA57L | 10 uF 25 V X7R | `C_1210_3225Metric` | 1 (1): `+3V3` | 2 (2): `GND` | MCU bulk |
| R702 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `MCLR_N` | MCLR pull-up |
| R704 | Panasonic ERJ-8ENF2212V | 22.1 kOhm 1% 1206 (0.25 W, 200 V) | `R_1206_3216Metric` | 1 (1): `IGN_D` | 2 (2): `READY_B` | pulse-rated series R |
| R705 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `READY_B` | 2 (2): `GND` | base pull-down; threshold ~2.2 V on IGN |
| R706 | Panasonic ERJ-3EKF1002V | 10 kOhm 1% 0603 (0.1 W, 75 V) | `R_0603_1608Metric` | 1 (1): `+3V3` | 2 (2): `READY_N` | pull-up |
| C707 | Murata GCM188R71H103KA37D | 10 nF 50 V X7R | `C_0603_1608Metric` | 1 (1): `READY_N` | 2 (2): `GND` | filter |

### U701 — DSPIC33CK64MP102-E/SS

pin functions: AN on 1-4,9-11,28; PPS/SCCP outputs on 21-23; PWM1H/L on 25/26; PGD1/PGC1 on 17/18. Symbol `custom (kae:dsPIC33CK64MP102_SSOP28)`, footprint `Package_SO:SSOP-28_5.3x10.2mm_P0.65mm`. Pins: dsPIC33CK64MP105 family DS DS70005363E, Table 2 (28-pin SSOP) p4 [P].

| Pin | Name | Net |
|---|---|---|
| 1 | OA1IN-/ANA1/RA1 | `PVA_VDIV` |
| 2 | OA1IN+/AN9/RA2 | `PVA_I_ADC` |
| 3 | DACOUT/AN3/CMP1C/RA3 | `PVB_VDIV` |
| 4 | AN4/CMP3B/IBIAS3/RA4 | `PVB_I_ADC` |
| 5 | AVDD | `+3V3A` |
| 6 | AVSS | `GND` |
| 7 | VDD | `+3V3` |
| 8 | VSS | `GND` |
| 9 | OSCI/CLKI/AN5/RP32/RB0 | `VINT_DIV` |
| 10 | OSCO/CLKO/AN6/RP33/RB1 | `NTC_HS` |
| 11 | OA2OUT/AN1/AN7/ANA0/CMP1D/CMP2A/CMP3D/RP34/INT0/RB2 | `NTC_PACK` |
| 12 | PGD2/OA2IN-/AN8/RP35/RB3 | `LATCH_Q` |
| 13 | PGC2/OA2IN+/RP36/RB4 | `READY_N` |
| 14 | PGD3/RP37/SDA2/RB5 | `UART_TX` |
| 15 | PGC3/RP38/SCL2/RB6 | `WDI` |
| 16 | TDO/AN2/CMP3A/RP39/RB7 | `RELAY_REQ` |
| 17 | PGD1/AN10/RP40/SCL1/RB8 | `PGD` |
| 18 | PGC1/AN11/RP41/SDA1/RB9 | `PGC` |
| 19 | VSS | `GND` |
| 20 | VDD | `+3V3` |
| 21 | TMS/RP42/PWM3H/RB10 | `MPPT_A_PWM` |
| 22 | TCK/RP43/PWM3L/RB11 | `MPPT_B_PWM` |
| 23 | TDI/RP44/PWM2H/RB12 | `FAN_PWM` |
| 24 | RP45/PWM2L/RB13 | `MCU_RUN` |
| 25 | RP46/PWM1H/RB14 | `DCX_HI` |
| 26 | RP47/PWM1L/RB15 | `DCX_LI` |
| 27 | MCLR | `MCLR_N` |
| 28 | OA1OUT/AN0/CMP1A/IBIAS0/RA0 | `HV_V_ADC` |

### J701 — 2.54 mm 1x6 header (e.g. Wurth 61300611121) [unverified]

ICSP (1-5) + log UART TX (6). Symbol `Connector_Generic:Conn_01x06`, footprint `Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical`. Pins: PICkit-style ICSP order.

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `MCLR_N` |
| 2 | 2 | `+3V3` |
| 3 | 3 | `GND` |
| 4 | 4 | `PGD` |
| 5 | 5 | `PGC` |
| 6 | 6 | `UART_TX` |

### J702 — Phoenix 1757242 (MSTBA 2,5/2-G-5,08) + plug 1757019 (MSTB 2,5/2-ST-5,08)

car IG/READY 12 V sense (informational). Symbol `Connector_Generic:Conn_01x02`, footprint `Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal`. Pins: Phoenix MSTB 2,5 series [S]; item numbers [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `IGN_IN` |
| 2 | 2 | `GND` |

### D701 — SBAS21LT1G

blocks ISO 7637 negative pulses (250 V). Symbol `Diode:BAS21`, footprint `Package_TO_SOT_SMD:SOT-23`. Pins: onsemi BAS21 SOT-23 DS (250 V) [unverified]; pinout matches KiCad Diode:BAS21.

| Pin | Name | Net |
|---|---|---|
| 1 | A | `IGN_IN` |
| 2 | NC | NC |
| 3 | K | `IGN_D` |

### Q701 — SMMBTA42LT1G

level shifter, READY_N low = ignition on. Symbol `Transistor_BJT:MMBTA42`, footprint `Package_TO_SOT_SMD:SOT-23`. Pins: onsemi MMBTA42 DS (300 V NPN, S-prefix AEC-Q101) [unverified]; KiCad Q_NPN_BEC.

| Pin | Name | Net |
|---|---|---|
| 1 | B | `READY_B` |
| 2 | E | `GND` |
| 3 | C | `READY_N` |

### J703 — Phoenix 1757284 (MSTBA 2,5/6-G-5,08) + plug MSTB 2,5/6-ST-5,08

LV harness to battery-end unit J903. Symbol `Connector_Generic:Conn_01x06`, footprint `Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_6-G-5,08_1x06_P5.08mm_Horizontal`. Pins: Phoenix MSTB 2,5 series [S]; item numbers [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `AUX12` |
| 2 | 2 | `K1_COIL_N` |
| 3 | 3 | `K2_COIL_N` |
| 4 | 4 | `NTC_PACK` |
| 5 | 5 | `GND` |
| 6 | 6 | `GND` |

### J704 — Molex 43650-0215 (Micro-Fit 3.0, 2-pin vertical)

optional 12 V fan (DNP fan by default). Symbol `Connector_Generic:Conn_01x02`, footprint `Connector_Molex:Molex_Micro-Fit_3.0_43650-0215_1x02_P3.00mm_Vertical`. Pins: Molex Micro-Fit 3.0 [S].

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `AUX12` |
| 2 | 2 | `FAN_N` |

### TP701 — (PCB pad)

test pad. Symbol `Connector:TestPoint`, footprint `TestPoint:TestPoint_Pad_D1.5mm`. Pins: test pad, no BOM item.

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `VINT` |

### TP702 — (PCB pad)

test pad. Symbol `Connector:TestPoint`, footprint `TestPoint:TestPoint_Pad_D1.5mm`. Pins: test pad, no BOM item.

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `AUX12` |

### TP703 — (PCB pad)

test pad. Symbol `Connector:TestPoint`, footprint `TestPoint:TestPoint_Pad_D1.5mm`. Pins: test pad, no BOM item.

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `+3V3` |

### TP704 — (PCB pad)

test pad. Symbol `Connector:TestPoint`, footprint `TestPoint:TestPoint_Pad_D1.5mm`. Pins: test pad, no BOM item.

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `PERMIT` |

### TP705 — (PCB pad)

test pad. Symbol `Connector:TestPoint`, footprint `TestPoint:TestPoint_Pad_D1.5mm`. Pins: test pad, no BOM item.

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `GND` |

### H701 — (M3 plated hole)

LV-side mount; bonds GND to enclosure/chassis. Symbol `Mechanical:MountingHole_Pad`, footprint `MountingHole:MountingHole_3.2mm_M3_Pad_Via`. Pins: chassis bond hole.

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `GND` |

### H702 — (M3 plated hole)

LV-side mount; bonds GND to enclosure/chassis. Symbol `Mechanical:MountingHole_Pad`, footprint `MountingHole:MountingHole_3.2mm_M3_Pad_Via`. Pins: chassis bond hole.

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `GND` |

### H703 — (M3 plated hole)

LV-side mount; bonds GND to enclosure/chassis. Symbol `Mechanical:MountingHole_Pad`, footprint `MountingHole:MountingHole_3.2mm_M3_Pad_Via`. Pins: chassis bond hole.

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `GND` |

### H704 — (M3 plated hole)

LV-side mount; bonds GND to enclosure/chassis. Symbol `Mechanical:MountingHole_Pad`, footprint `MountingHole:MountingHole_3.2mm_M3_Pad_Via`. Pins: chassis bond hole.

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `GND` |

### H705 — (M3 non-plated hole)

HV-side mount, non-plated, >= 8 mm from LV copper. Symbol `Mechanical:MountingHole`, footprint `MountingHole:MountingHole_3.2mm_M3`. Pins: isolated hole, no net.

No electrical pins.

### H706 — (M3 non-plated hole)

HV-side mount, non-plated, >= 8 mm from LV copper. Symbol `Mechanical:MountingHole`, footprint `MountingHole:MountingHole_3.2mm_M3`. Pins: isolated hole, no net.

No electrical pins.

## Block BATEND (board BE)

Battery-end unit (separate PCB at the battery tap): fuses, blocking diode, double-pole disconnect

### J901 — Phoenix GMSTBA 2,5/2-G-7,62 + plug GMSTB 2,5/2-ST-7,62 (item nos. [unverified])

HV from main board J301. Symbol `Connector_Generic:Conn_01x02`, footprint `Connector_Phoenix_GMSTB:PhoenixContact_GMSTBA_2,5_2-G-7,62_1x02_P7.62mm_Horizontal`. Pins: Phoenix GMSTB 2,5 (7.62 mm pitch, high-voltage series) [S].

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `HV_P` |
| 2 | 2 | `HV_N` |

### J902 — Phoenix GMSTBA 2,5/2-G-7,62 + plug GMSTB 2,5/2-ST-7,62 (item nos. [unverified])

HV to traction-battery tap (Mode R: car side of SMRs). Symbol `Connector_Generic:Conn_01x02`, footprint `Connector_Phoenix_GMSTB:PhoenixContact_GMSTBA_2,5_2-G-7,62_1x02_P7.62mm_Horizontal`. Pins: Phoenix GMSTB 2,5 (7.62 mm pitch, high-voltage series) [S].

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `BAT_TAP_P` |
| 2 | 2 | `BAT_TAP_N` |

### J903 — Phoenix 1757284 (MSTBA 2,5/6-G-5,08) + plug MSTB 2,5/6-ST-5,08

LV harness from main board J703. Symbol `Connector_Generic:Conn_01x06`, footprint `Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_6-G-5,08_1x06_P5.08mm_Horizontal`. Pins: Phoenix MSTB 2,5 series [S]; item numbers [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `AUX12` |
| 2 | 2 | `K1_COIL_N` |
| 3 | 3 | `K2_COIL_N` |
| 4 | 4 | `NTC_PACK` |
| 5 | 5 | `GND` |
| 6 | 6 | `GND` |

### J904 — Phoenix 1757242 (MSTBA 2,5/2-G-5,08) + plug 1757019 (MSTB 2,5/2-ST-5,08)

pack NTC (Mode P only; reinforced-insulated probe). Symbol `Connector_Generic:Conn_01x02`, footprint `Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal`. Pins: Phoenix MSTB 2,5 series [S]; item numbers [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | 1 | `NTC_PACK` |
| 2 | 2 | `GND` |

### F901 — EVM10-5-2P — 5 A 500 VDC 20 kA

first element from battery +. Symbol `Device:Fuse (4-pad variant: custom kae:Fuse_2x2pin)`, footprint `custom (kae:Eaton_EVM10_2P; 'PCB layout 2P' in Eaton ELX1304)`. Pins: Eaton ELX1304 (Jan 2026) [P] ratings; 2P = two PCB pins per end cap [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | END_A | `BAT_TAP_P` |
| 2 | END_A | `BAT_TAP_P` |
| 3 | END_B | `BAT_F_P` |
| 4 | END_B | `BAT_F_P` |

### F902 — EVM10-5-2P — 5 A 500 VDC 20 kA

first element from battery -. Symbol `Device:Fuse (4-pad variant: custom kae:Fuse_2x2pin)`, footprint `custom (kae:Eaton_EVM10_2P; 'PCB layout 2P' in Eaton ELX1304)`. Pins: Eaton ELX1304 (Jan 2026) [P] ratings; 2P = two PCB pins per end cap [unverified].

| Pin | Name | Net |
|---|---|---|
| 1 | END_A | `BAT_TAP_N` |
| 2 | END_A | `BAT_TAP_N` |
| 3 | END_B | `BAT_F_N` |
| 4 | END_B | `BAT_F_N` |

### K901 — G9EJ-1-P-E-UVD DC12

+ pole disconnect; charge current flows 3 -> 4. Symbol `custom (kae:Relay_SPST_NO_polar)`, footprint `custom (kae:Omron_G9EJ-1-P-E; per Omron G9EJ-1-E datasheet 'PCB terminals' mounting-hole drawing)`. Pins: Omron G9EJ-1-E DS (2016) [P] for ratings and contact polarity; terminal numbering is ours [unverified vs drawing].

| Pin | Name | Net |
|---|---|---|
| 1 | COIL+ | `AUX12` |
| 2 | COIL- | `K1_COIL_N` |
| 3 | CONTACT(+) (current in) | `BE_DK` |
| 4 | CONTACT(-) (current out) | `BAT_F_P` |

### K902 — G9EJ-1-P-E-UVD DC12

- pole disconnect; return current flows 3 -> 4. Symbol `custom (kae:Relay_SPST_NO_polar)`, footprint `custom (kae:Omron_G9EJ-1-P-E; per Omron G9EJ-1-E datasheet 'PCB terminals' mounting-hole drawing)`. Pins: Omron G9EJ-1-E DS (2016) [P] for ratings and contact polarity; terminal numbering is ours [unverified vs drawing].

| Pin | Name | Net |
|---|---|---|
| 1 | COIL+ | `AUX12` |
| 2 | COIL- | `K2_COIL_N` |
| 3 | CONTACT(+) (current in) | `BAT_F_N` |
| 4 | CONTACT(-) (current out) | `HV_N` |

### D901 — VS-6ESH06HM3/86A

blocking diode: battery cannot feed the cable. Symbol `custom (kae:D_TO277A: 1=A,2=A,3=K)`, footprint `Package_TO_SOT_SMD:TO-277A`. Pins: VS-6ESH06HM3 DS doc 94985 p1 [P]; pads per KiCad TO-277A.

| Pin | Name | Net |
|---|---|---|
| 1 | A (anode 1) | `HV_P` |
| 2 | A (anode 2) | `HV_P` |
| 3 | K (cathode, tab) | `BE_DK` |

### H901 — (M3 non-plated hole)

non-plated mount. Symbol `Mechanical:MountingHole`, footprint `MountingHole:MountingHole_3.2mm_M3`. Pins: isolated hole, no net.

No electrical pins.

### H902 — (M3 non-plated hole)

non-plated mount. Symbol `Mechanical:MountingHole`, footprint `MountingHole:MountingHole_3.2mm_M3`. Pins: isolated hole, no net.

No electrical pins.

### H903 — (M3 non-plated hole)

non-plated mount. Symbol `Mechanical:MountingHole`, footprint `MountingHole:MountingHole_3.2mm_M3`. Pins: isolated hole, no net.

No electrical pins.

### H904 — (M3 non-plated hole)

non-plated mount. Symbol `Mechanical:MountingHole`, footprint `MountingHole:MountingHole_3.2mm_M3`. Pins: isolated hole, no net.

No electrical pins.

## Off-board wiring (array and harnesses)

Not part of either PCB netlist; listed so the harness can be built from this file. Cell and diode details are in DESIGN.md §7.1.

| Item | From | To | Conductor |
|---|---|---|---|
| String A (front 4 rows x 8 cells, series) | row-1 + ribbon | J101.1 `PVA_IN` | FLRY-B 2.5 mm2, 60 V, twisted with return |
| String A return | row-4 - ribbon | J101.2 `GND` | FLRY-B 2.5 mm2 |
| String B (rear 4 rows x 8 cells, series) | row-5 + ribbon | J201.1 `PVB_IN` | FLRY-B 2.5 mm2 |
| String B return | row-8 - ribbon | J201.2 `GND` | FLRY-B 2.5 mm2 |
| Bypass diodes DB1..DB8 (Vishay V10P45-M3/86A, one per 8-cell row, anode to row -, cathode to row +) | laminate junction pads | - | in laminate edge |
| HV link | J301.1/.2 `HV_P`/`HV_N` | J901.1/.2 | orange screened 2 x 2.5 mm2, 600 V AC / 900 V DC class (ISO 19642-5 type), screen to enclosures both ends |
| Battery tap | J902.1/.2 `BAT_TAP_P`/`BAT_TAP_N` | traction battery tap (Mode R: car side of SMRs) | orange 2 x 2.5 mm2 as above, <= 0.5 m |
| LV harness | J703.1-6 | J903.1-6 | 6 x 0.5 mm2 FLRY-B, screened, screen = pin 6 |
| Pack NTC (Mode P only) | J904.1/.2 | NTC probe on module case | 2 x 0.35 mm2; probe insulation reinforced for 300 V |
| IG/READY sense | car IG2 fused circuit, via 1 A fuse tap | J702.1 `IGN_IN`; J702.2 to body ground near J702 | 0.5 mm2 |
