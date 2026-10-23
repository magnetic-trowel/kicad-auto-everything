# rpi-mains-relay: connections (netlist)

Companion to [DESIGN.md](DESIGN.md). Every pin of every placed part is listed, plus the
off-board objects (Raspberry Pi header, Class 2 cable, field wiring).

The encoded design is [design.py](design.py) with part cards in [parts.py](parts.py). `kaesynth build`
writes the authoritative pin list to [out/netlist.json](out/netlist.json). Section 8 below was checked
against that file node by node: all 32 nets are identical. If the two ever disagree, netlist.json wins.

**Conventions**

- Pin entries read `pin number (datasheet name) → NET`.
- The KiCad pad name is given where it differs from the datasheet number.
- `NC` means intentionally unconnected.
- Evidence tags: [P] pin numbering read in the datasheet at the cited page or figure; [I] inferred; [unverified] not confirmed in the primary source.
- Net names are global. A net with the same name in two blocks is the same net.
- In KiCad, the per-channel nets (CHk_G, COILk, LEDk_A) and the watchdog and input-local nets (HB_R, PUMP, ARM_G, LED_ARM_A, +5V_IN, LED_PWR_A) are sheet-local. They appear with a sheet prefix, e.g. `/ch1/COIL1`, `/arm/ARM_G`, `/selv_in/+5V_IN`.
- Domain names match design.py:
  - LINE (root, reference L_IN), NEUTRAL, OUT1–OUT4 (these float on L_IN), SELV (root, reference GND) and PE (off-board).
  - Taking L as the mains reference makes the voltage across an open relay contact exact (±187 V peak).
- Refdes and net names for channels follow the rule in section 3.

## 1. Net table

| Net | Domain | Voltage range | Max current | Kind |
|---|---|---|---|---|
| L_IN | LINE (root, 0 V) | 0–132 V rms vs N (±187 V pk); ≤ 1.5 kV pk transient (OVC II) | 15 A rms | mains, power |
| N | NEUTRAL | ±187 V pk vs L_IN; ≈ 0–5 V rms vs PE (treat as hazardous) | 15 A rms | mains, power (return) |
| L_SW1 … L_SW4 | OUT1 … OUT4 | equals L_IN when the relay is closed; floating or ≈ N when open (±187 V pk vs L_IN) | 15 A rms each (sum ≤ 15 A) | mains, switched power |
| PE | PE (off-board) | 0 V (earth) | fault current | protective earth: box, ring, cover, EGCs; no PCB copper |
| +5V_IN | SELV | 4.75–5.25 V (transient clamped ≤ 12 V after F1) | 0.39 A (F1 trips ≥ 2.2 A) | power (from the Pi) |
| +5V | SELV | 4.5–5.25 V | 0.39 A | power (coil and LED rail) |
| GND | SELV | 0 V (reference; may be earthed through the Pi) | 0.39 A | ground |
| CH1_IN … CH4_IN | SELV | 0–3.3 V (clamped by U1 above ≈ 6.5 V) | 0.6 mA | signal, from the Pi GPIO |
| CH1_G … CH4_G | SELV | 0–3.0 V | 0.6 mA | signal (MOSFET gate) |
| COIL1 … COIL4 | SELV | 0 V (ON) to 5.25 V (OFF); ≤ 6.1 V during flyback | 93 mA | power (coil low side) |
| LED1_A … LED4_A | SELV | 0–5.25 V | 2.3 mA | signal (LED anode) |
| COIL_RTN | SELV | 0–0.03 V when armed; floats ≤ 3.5 V when disarmed | 0.39 A | power (common coil return) |
| HB_IN | SELV | 0–3.3 V square wave, 100 Hz–2 kHz | 3.3 mA peak | signal (heartbeat) |
| HB_R | SELV | 0–3.3 V | 3.3 mA peak | signal (after series R) |
| PUMP | SELV | −0.3…+3.0 V | 3.3 mA peak | signal (pump node) |
| ARM_G | SELV | 0–2.75 V | 3 µA (bleed through R14) | signal (Q5 gate / hold) |
| LED_ARM_A | SELV | 0–5.25 V | 2.3 mA | signal |
| LED_PWR_A | SELV | 0–5.25 V | 2.3 mA | signal |

PE (box, ring, cover, EGCs, ground screw) is **not** a PCB net. It appears only in section 6.

## 2. Block B5 SELV_IN: link terminal and protection

### J6: WAGO 2601-3108, 8-pole lever terminal, 3.5 mm pitch, THT

Footprint `TerminalBlock_WAGO:TerminalBlock_WAGO_2601-3108_1x08_P3.50mm_Vertical`. Each
position has **two** solder pins with the same pad number. Both pins carry the same net.
The pin count and arrangement come from the WAGO data sheet, "Number of solder pins per potential 2" [P]. Positions are numbered 1–8 left to right as marked on the housing [I].

| Pos | Signal | Net | Pi side (via W1) |
|---|---|---|---|
| 1 | +5 V from Pi | +5V_IN | PI1 pin 2 (5V) |
| 2 | Ground | GND | PI1 pin 6 (GND) |
| 3 | Channel 1 command | CH1_IN | PI1 pin 11 (BCM17) |
| 4 | Channel 2 command | CH2_IN | PI1 pin 13 (BCM27) |
| 5 | Channel 3 command | CH3_IN | PI1 pin 15 (BCM22) |
| 6 | Channel 4 command | CH4_IN | PI1 pin 16 (BCM23) |
| 7 | Heartbeat | HB_IN | PI1 pin 32 (BCM12, PWM0-capable) |
| 8 | Ground | GND | PI1 pin 34 (GND) |

### F1: Bourns MF-MSMF110/16X-2, PTC 1.1 A hold, 1812

Symbol `Device:Polyfuse`; footprint `Fuse:Fuse_1812_4532Metric`. Non-polar [P].

- 1 → +5V_IN
- 2 → +5V

### D11: Vishay SMAJ7.0A-E3/61, unidirectional TVS, SMA (DO-214AC)

The band marks the cathode (datasheet p.1, "Polarity") [P]. Symbol `Diode:SMAJ5.0A` (Value
overridden to SMAJ7.0A). Its pin 1 is the cathode: the bar is drawn at pin 1 in the KiCad
symbol [I, read from the symbol graphics]. Footprint `Diode_SMD:D_SMA`, pad 1 = cathode.

- 1 (K, cathode) → +5V
- 2 (A, anode) → GND

### C1: Murata GRM21BR61C106KE15L, 10 µF 16 V X5R, 0805

- 1 → +5V
- 2 → GND

### C2: Yageo CC0603KRX7R9BB104, 100 nF 50 V X7R, 0603

- 1 → +5V
- 2 → GND

### U1: TI TPD6E05U06RVZR, 6-channel ESD, USON-14 (RVZ)

Pin functions from Table 4-3, datasheet SLVSBO7O p.5 [P]. Symbol `Power_Protection:TPD6E05U06RVZ`.
Footprint `Package_SON:Texas_R-PUSON-N14`, 14 pads, no exposed pad.

| Pin | Name | Net |
|---|---|---|
| 1 | NC | NC |
| 2 | NC | NC |
| 3 | NC | NC |
| 4 | NC | NC |
| 5 | GND | GND |
| 6 | NC | NC |
| 7 | NC | NC |
| 8 | D3− | NC (spare channel; unused protected I/O left open [I]) |
| 9 | D3+ | HB_IN |
| 10 | GND | GND |
| 11 | D2− | CH4_IN |
| 12 | D2+ | CH3_IN |
| 13 | D1− | CH2_IN |
| 14 | D1+ | CH1_IN |

### D10: Kingbright APT1608SGC, green LED, 0603 (5 V present)

The datasheet p.1 package drawing shows pin 1 as the cathode, pin 2 as the anode, and a
polarity mark on the bottom [P]. KiCad `Device:LED` uses the same numbering (1 = K, 2 = A).
Footprint `LED_SMD:LED_0603_1608Metric`, pad 1 = cathode. D5–D9 follow the same rule.

- 1 (K) → GND
- 2 (A) → LED_PWR_A

### R16: Yageo RC0603FR-071K5L, 1.5 kΩ, 0603

- 1 → +5V
- 2 → LED_PWR_A

### TP1, TP2: test pads (`Connector:TestPoint`, `TestPoint:TestPoint_Pad_D1.5mm`)

- TP1.1 → +5V
- TP2.1 → GND

## 3. Channels: B3 DRV_k and B2 SW_k

### 3.1 Naming rule for channel k (k = 1, 2, 3, 4)

| Item | Refdes or net for channel k | k = 1 | k = 2 | k = 3 | k = 4 |
|---|---|---|---|---|---|
| Relay | K{k} | K1 | K2 | K3 | K4 |
| Driver MOSFET | Q{k} | Q1 | Q2 | Q3 | Q4 |
| Flyback diode | D{k} | D1 | D2 | D3 | D4 |
| Channel LED | D{k+4} | D5 | D6 | D7 | D8 |
| Gate series R (1 kΩ) | R{k} | R1 | R2 | R3 | R4 |
| Gate pull-down R (4.7 kΩ) | R{k+4} | R5 | R6 | R7 | R8 |
| LED R (1.5 kΩ) | R{k+8} | R9 | R10 | R11 | R12 |
| Output terminal | J{k+1} | J2 | J3 | J4 | J5 |
| Command net | CH{k}_IN | CH1_IN | CH2_IN | CH3_IN | CH4_IN |
| Gate net | CH{k}_G | CH1_G | CH2_G | CH3_G | CH4_G |
| Coil low-side net | COIL{k} | COIL1 | COIL2 | COIL3 | COIL4 |
| LED anode net | LED{k}_A | LED1_A | LED2_A | LED3_A | LED4_A |
| Switched line net | L_SW{k} | L_SW1 | L_SW2 | L_SW3 | L_SW4 |
| J6 position | k + 2 | 3 | 4 | 5 | 6 |
| U1 pin | 14, 13, 12, 11 | 14 | 13 | 12 | 11 |
| Pi pin (BCM) | — | 11 (17) | 13 (27) | 15 (22) | 16 (23) |

Shared by all channels: +5V, GND, COIL_RTN, L_IN, N.

### 3.2 Channel 1, complete. Channels 2–4 are identical under the rule above.

**R1: Yageo RC0603FR-071KL, 1 kΩ, 0603** (`Device:R`, `Resistor_SMD:R_0603_1608Metric`)

- 1 → CH1_IN
- 2 → CH1_G

**R5: Yageo RC0603FR-074K7L, 4.7 kΩ, 0603**

- 1 → CH1_G
- 2 → GND

**Q1: AOS AO3400A, N-MOSFET, SOT-23**

Pinout from the AO3400A datasheet rev 3.1 p.1, "SOT23 Top View": G, S, D [P]. KiCad
`Transistor_FET:AO3400A` (extends `Q_NMOS_GSD`); footprint `Package_TO_SOT_SMD:SOT-23`.

- 1 (G) → CH1_G
- 2 (S) → COIL_RTN
- 3 (D) → COIL1

**D1: Diodes 1N4148W-7-F, SOD-123**

The band is the cathode (DS30086, "Polarity: Cathode Band") [P]. KiCad `Diode:1N4148W` (pin 1 = K, pin 2 = A); `Diode_SMD:D_SOD-123`, pad 1 = cathode.

- 1 (K) → +5V
- 2 (A) → COIL1

**D5: Kingbright APT1608SGC, LED, 0603**

- 1 (K) → COIL1
- 2 (A) → LED1_A

**R9: Yageo RC0603FR-071K5L, 1.5 kΩ, 0603**

- 1 → +5V
- 2 → LED1_A

**K1: Omron/Aratas G5RL-1A-E-TV8 DC5, SPST-NO, 16 A, THT, 6 pins**

Pin numbering is the datasheet bottom view, "G5RL-1A-E-LN / -E-HR / -E-TV8, Terminal
Arrangement/Internal Connections", p.5 [P]:

- Coil pins 1 and 8. No coil polarity.
- Pins 3 and 6 are joined internally (moving contact).
- Pins 4 and 5 are joined internally (fixed contact).
- Both pins of each contact must be used (p.7, "Wiring of High-capacity Models (-E)") [P].

KiCad symbol `Relay:G2RL-1A-E` (pins A1, A2, 13, 14). Footprint
`Relay_THT:Relay_SPST_Omron_G2RL-1A-E`:

- Pads A1 (0,0) and A2 (7.5,0).
- Pad "13" at (0,20) and (7.5,20).
- Pad "14" at (0,25) and (7.5,25).

This matches the G5RL hole pattern of 7.5 / 20 / 5 mm with Ø1.3 mm holes [P].

| Datasheet pin | Function | KiCad pad | Net |
|---|---|---|---|
| 1 | coil | A1 | +5V |
| 8 | coil | A2 | COIL1 |
| 3 | contact (moving), joined to 6 | 13 | L_IN |
| 6 | contact (moving), joined to 3 | 13 | L_IN |
| 4 | contact (fixed), joined to 5 | 14 | L_SW1 |
| 5 | contact (fixed), joined to 4 | 14 | L_SW1 |

The coil is non-polar, so the assignment of datasheet pin 1 to A1 and pin 8 to A2 is arbitrary [I].
Pins 3/6 sit 20 mm from the coil pins and 4/5 sit 25 mm away [P]. The always-live L_IN therefore
lands on the column nearer the coil, and the L bus enters from the coil side under the relay
body, ≥ 8 mm from the coil pads. L_SW1 leaves northwards from 4/5 (see DESIGN.md §9).

**J2: WAGO 2606-3102/020-000, 2-pole lever terminal, 7.5 mm, THT**

Pole numbering follows the WAGO data sheet drawing p.1, "Dimensions in mm" [P]:

- One solder pin per pole.
- Poles are staggered: pole 2's pin is offset 7.5 mm along the strip and 12.5 mm across it from pole 1's pin.

KiCad symbol `Connector_Generic:Conn_01x02`. Footprint: **custom**
`kae:WAGO_2606-3102_020-000`. Pad 1 = pole 1, pad 2 = pole 2. Geometry:

- Drill Ø2.1 mm finished (datasheet: Ø2.0 +0.1); pad Ø3.5 mm.
- Pad 2 at (+7.5, +12.5) mm from pad 1.
- Body 17.85 × 24.0 mm. Pole 1's pin is 5.5 mm from its end face and 7.7 mm from the long face it is nearer to.
- Lever side: [unverified] check against WAGO CAD before freezing layout.

| Pole | Function | Net |
|---|---|---|
| 1 | Output 1, switched line | L_SW1 |
| 2 | Output 1, neutral | N |

### 3.3 Channels 2–4: expanded pin lists (for checking)

| Part | Pin → net (k = 2) | Pin → net (k = 3) | Pin → net (k = 4) |
|---|---|---|---|
| R{k} 1 kΩ | R2: 1→CH2_IN, 2→CH2_G | R3: 1→CH3_IN, 2→CH3_G | R4: 1→CH4_IN, 2→CH4_G |
| R{k+4} 4.7 kΩ | R6: 1→CH2_G, 2→GND | R7: 1→CH3_G, 2→GND | R8: 1→CH4_G, 2→GND |
| Q{k} AO3400A | Q2: 1(G)→CH2_G, 2(S)→COIL_RTN, 3(D)→COIL2 | Q3: 1→CH3_G, 2→COIL_RTN, 3→COIL3 | Q4: 1→CH4_G, 2→COIL_RTN, 3→COIL4 |
| D{k} 1N4148W | D2: 1(K)→+5V, 2(A)→COIL2 | D3: 1→+5V, 2→COIL3 | D4: 1→+5V, 2→COIL4 |
| D{k+4} LED | D6: 1(K)→COIL2, 2(A)→LED2_A | D7: 1→COIL3, 2→LED3_A | D8: 1→COIL4, 2→LED4_A |
| R{k+8} 1.5 kΩ | R10: 1→+5V, 2→LED2_A | R11: 1→+5V, 2→LED3_A | R12: 1→+5V, 2→LED4_A |
| K{k} G5RL | K2: 1(A1)→+5V, 8(A2)→COIL2, 3&6(13)→L_IN, 4&5(14)→L_SW2 | K3: …→COIL3 …→L_SW3 | K4: …→COIL4 …→L_SW4 |
| J{k+1} WAGO 2606 | J3: 1→L_SW2, 2→N | J4: 1→L_SW3, 2→N | J5: 1→L_SW4, 2→N |

## 4. Block B4 ARM: heartbeat watchdog

**R13: Yageo RC0603FR-071KL, 1 kΩ, 0603**

- 1 → HB_IN
- 2 → HB_R

**C3: Yageo CC0603KRX7R7BB105, 1 µF 16 V X7R, 0603** (pump capacitor)

- 1 → HB_R
- 2 → PUMP

**D12: Diodes BAT54S-7-F, dual series Schottky, SOT-23**

From DS11005 p.1, "BAT54S" diagram, top view [P]:

- Pin 1 is the anode of diode 1.
- Pin 2 is the cathode of diode 2.
- Pin 3 is common (cathode of diode 1 and anode of diode 2).

KiCad `Diode:BAT54S` uses 1 = A, 2 = K, 3 = COM.

- 1 (A) → GND (clamps PUMP at −V_F on the low half-cycle)
- 2 (K) → ARM_G (charges the hold capacitor on the high half-cycle)
- 3 (COM) → PUMP

**C4: Yageo CC0603KRX7R9BB104, 100 nF 50 V X7R, 0603** (hold capacitor)

Changed from 1 µF during encoding, together with R14 (100 kΩ → 1 MΩ). The time constant stays at
τ = 0.1 s, but the bleed current falls tenfold, so V_ARM at 100 Hz rises from 2.45 V to ≥ 2.56 V.
That is above the 2.5 V at which the AO3400A's R_DS(on) is specified (calc `arm_gate_min_100Hz_V`).

- 1 → ARM_G
- 2 → GND

**R14: Yageo RC0603FR-071ML, 1 MΩ, 0603** (bleed, τ = R14·C4 = 0.1 s)

- 1 → ARM_G
- 2 → GND

**Q5: AOS AO3400A, SOT-23** (common low-side enable)

- 1 (G) → ARM_G
- 2 (S) → GND
- 3 (D) → COIL_RTN

**D9: Kingbright APT1608SGC, LED, 0603** (ARM indicator: lit when Q5 is on)

- 1 (K) → COIL_RTN
- 2 (A) → LED_ARM_A

**R15: Yageo RC0603FR-071K5L, 1.5 kΩ, 0603**

- 1 → +5V
- 2 → LED_ARM_A

**TP3, TP4: test pads**

- TP3.1 → ARM_G
- TP4.1 → COIL_RTN

## 5. Block B1 MAINS_IN

**J1: WAGO 2606-3102/020-000, 2-pole** (same footprint and pole rule as J2)

| Pole | Function | Net |
|---|---|---|
| 1 | Line in (from the branch circuit, black) | L_IN |
| 2 | Neutral in (white) | N |

## 6. Mechanical parts (no electrical pins)

| Ref | Part | Connection |
|---|---|---|
| H1–H4 | `MountingHole:MountingHole_4mm` (Ø4.0 NPTH), Essentra LCBS-8-19 nylon supports | none. Insulated from the box (PE) by nylon. No copper within Ø8 mm |
| MP1 | Insulating cover over the SELV zone (custom, UL 94 V-0) | none |

## 7. Off-board objects

### PI1: Raspberry Pi 4 Model B or 5, 40-pin header J8 (not on our PCB)

Pin names come from the KiCad symbol `Connector:Raspberry_Pi_2_3`, which matches the
Raspberry Pi GPIO documentation [P]. Default pulls are from BCM2711 Table 94 [P] (Pi 4);
on the Pi 5 (RP1) the reset pull "varies" [P]. Only the pins marked "W1" are wired. All
others are NC as far as this design is concerned and remain free for other uses.

| Pin | Name | Default pull (BCM2711) | Connection |
|---|---|---|---|
| 1 | 3V3 | — | NC |
| 2 | 5V | — | **W1 → J6.1 (+5V_IN)** |
| 3 | GPIO2 / SDA1 | fixed 1.8 kΩ pull-up | NC |
| 4 | 5V | — | NC |
| 5 | GPIO3 / SCL1 | fixed 1.8 kΩ pull-up | NC |
| 6 | GND | — | **W1 → J6.2 (GND)** |
| 7 | GPIO4 / GPCLK0 | high | NC |
| 8 | GPIO14 / TXD0 | low | NC (UART console at boot) |
| 9 | GND | — | NC |
| 10 | GPIO15 / RXD0 | low | NC |
| 11 | GPIO17 | low | **W1 → J6.3 (CH1_IN)** |
| 12 | GPIO18 / PCM_CLK / PWM0 | low | NC |
| 13 | GPIO27 | low | **W1 → J6.4 (CH2_IN)** |
| 14 | GND | — | NC |
| 15 | GPIO22 | low | **W1 → J6.5 (CH3_IN)** |
| 16 | GPIO23 | low | **W1 → J6.6 (CH4_IN)** |
| 17 | 3V3 | — | NC |
| 18 | GPIO24 | low | NC |
| 19 | GPIO10 / MOSI0 | low | NC |
| 20 | GND | — | NC |
| 21 | GPIO9 / MISO0 | low | NC |
| 22 | GPIO25 | low | NC |
| 23 | GPIO11 / SCLK0 | low | NC |
| 24 | GPIO8 / CE0 | high | NC |
| 25 | GND | — | NC |
| 26 | GPIO7 / CE1 | high | NC |
| 27 | GPIO0 / ID_SD | high | NC (HAT EEPROM probe at boot) |
| 28 | GPIO1 / ID_SC | high | NC |
| 29 | GPIO5 / GPCLK1 | high | NC |
| 30 | GND | — | NC |
| 31 | GPIO6 / GPCLK2 | high | NC |
| 32 | GPIO12 / PWM0 | low | **W1 → J6.7 (HB_IN)** |
| 33 | GPIO13 / PWM1 | low | NC |
| 34 | GND | — | **W1 → J6.8 (GND)** |
| 35 | GPIO19 / PCM_FS | low | NC |
| 36 | GPIO16 | low | NC |
| 37 | GPIO26 | low | NC |
| 38 | GPIO20 / PCM_DIN | low | NC |
| 39 | GND | — | NC |
| 40 | GPIO21 / PCM_DOUT | low | NC |

Software contract (not hardware, but part of the safety case):

- CH pins are outputs, active high.
- Preload them low early in boot (config.txt `gpio=17,22,23,27=op,dl` [unverified syntax on the Pi 5]).
- The control process toggles BCM12 at 100 Hz–2 kHz only while it is healthy, and stops toggling on any fault.

### W1: Class 2 link cable (8 conductors, 22 AWG, ≤ 3 m; CL2, or a permitted substitute such as CL2R, CL3 or CM)

| Conductor (suggested colour) | J6 position | Net | PI1 pin |
|---|---|---|---|
| red | 1 | +5V_IN | 2 |
| black | 2 | GND | 6 |
| green | 3 | CH1_IN | 11 |
| yellow | 4 | CH2_IN | 13 |
| blue | 5 | CH3_IN | 15 |
| orange | 6 | CH4_IN | 16 |
| white | 7 | HB_IN | 32 |
| brown | 8 | GND | 34 |

If twisted pairs are used, pair red with black (supply) and white with brown (heartbeat).
At the Pi end, terminate on a GPIO screw-terminal HAT or crimped 2.54 mm housings (Q-8).

### Field wiring (installed by an electrician; inside the box)

| Cable | Conductor | Lands on |
|---|---|---|
| Input (NM-B 14/2 or 12/2 with ground, from a ≤ 15 A branch) | black | J1.1 (L_IN) |
| | white | J1.2 (N) |
| | bare/green (EGC) | EGC splice |
| Output k (k = 1…4) | black | J{k+1}.1 (L_SW{k}) |
| | white | J{k+1}.2 (N) |
| | bare/green (EGC) | EGC splice |
| EGC splice (listed, e.g. lever-nut, UL 486C) | 5 EGCs + 1 pigtail | pigtail → box #10-32 ground screw (PE). The ring and cover are bonded by their screws |

## 8. Net-by-net node list (cross-check)

| Net | Nodes |
|---|---|
| L_IN | J1.1, K1.13 (pins 3, 6), K2.13, K3.13, K4.13 |
| N | J1.2, J2.2, J3.2, J4.2, J5.2 |
| L_SW1 | K1.14 (pins 4, 5), J2.1 |
| L_SW2 | K2.14, J3.1 |
| L_SW3 | K3.14, J4.1 |
| L_SW4 | K4.14, J5.1 |
| +5V_IN | J6.1, F1.1 |
| +5V | F1.2, D11.1, C1.1, C2.1, K1.A1, K2.A1, K3.A1, K4.A1, D1.1, D2.1, D3.1, D4.1, R9.1, R10.1, R11.1, R12.1, R15.1, R16.1, TP1.1 |
| GND | J6.2, J6.8, D11.2, C1.2, C2.2, U1.5, U1.10, R5.2, R6.2, R7.2, R8.2, D12.1, C4.2, R14.2, Q5.2, D10.1, TP2.1 |
| CH1_IN | J6.3, U1.14, R1.1 |
| CH2_IN | J6.4, U1.13, R2.1 |
| CH3_IN | J6.5, U1.12, R3.1 |
| CH4_IN | J6.6, U1.11, R4.1 |
| CH1_G | R1.2, R5.1, Q1.1 |
| CH2_G | R2.2, R6.1, Q2.1 |
| CH3_G | R3.2, R7.1, Q3.1 |
| CH4_G | R4.2, R8.1, Q4.1 |
| COIL1 | K1.A2, Q1.3, D1.2, D5.1 |
| COIL2 | K2.A2, Q2.3, D2.2, D6.1 |
| COIL3 | K3.A2, Q3.3, D3.2, D7.1 |
| COIL4 | K4.A2, Q4.3, D4.2, D8.1 |
| LED1_A | R9.2, D5.2 |
| LED2_A | R10.2, D6.2 |
| LED3_A | R11.2, D7.2 |
| LED4_A | R12.2, D8.2 |
| COIL_RTN | Q1.2, Q2.2, Q3.2, Q4.2, Q5.3, D9.1, TP4.1 |
| HB_IN | J6.7, U1.9, R13.1 |
| HB_R | R13.2, C3.1 |
| PUMP | C3.2, D12.3 |
| ARM_G | D12.2, C4.1, R14.1, Q5.1, TP3.1 |
| LED_ARM_A | R15.2, D9.2 |
| LED_PWR_A | R16.2, D10.2 |
| (NC) | U1.1, U1.2, U1.3, U1.4, U1.6, U1.7, U1.8 |

Pin count check:

| Part group | Pins |
|---|---|
| J1–J5 | 5 × 2 = 10 |
| J6 | 8 positions |
| K1–K4 | 4 × 6 = 24 datasheet pins (16 KiCad pads) |
| Q1–Q5 | 15 |
| D1–D11 | 22 |
| D12 | 3 |
| U1 | 14 |
| F1 | 2 |
| R1–R16 | 32 |
| C1–C4 | 8 |
| TP1–TP4 | 4 |
| **Total** | **142 datasheet pins (134 KiCad symbol pins)** |

Every pin listed above appears exactly once in this table.
