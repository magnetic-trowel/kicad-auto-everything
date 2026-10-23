# liion-balancer: independent design review

Reviewer: independent LLM review, October 2026. Scope: `DESIGN.md`, `CONNECTIONS.md`, `parts.py`,
`design.py`, `footprints/custom.pretty/`, `out/` (netlist, report, DRU, intent). Datasheets were read
as primary sources: LT8584 Rev B (8584fb), ADBMS1818 Rev A, LTC6813-1 Rev B, Coilcraft Doc 1075,
STM32G031 DS12992, LM5164 SNVSAU4D, TLP293 (2019-11-29) and Littelfuse 314/324 (07/31/15).

## Verdict

**Not ready for fabrication. I found no BLOCKER.** Every pinout I checked is correct, including
both hand-drawn footprints, and the channel follows ADI's own application circuit almost part for
part. The weak points are the fault cases at the ends of the stack and the protection functions
that depend on firmware:

- An open TAP0 or TAP16 wire while balancing is not caught by the FLYBUS watchdog. The design's
  "≤ 1 ms" claim for that case is wrong.
- The D2 clamp hides an open output from the LT8584's own over-voltage latch, so that protection
  becomes firmware-only.
- The ADBMS1818 S lines have no current limit.
- The board fuses are relied on outside their interrupting rating.
- Both enables share one MCU, and nothing in hardware stops over-charge.

All five can be fixed cheaply. Fix them before layout.

Counts: **0 BLOCKER, 5 MAJOR, 8 MINOR.**

## MAJOR

### M-1 An open TAP0 or TAP16 wire while balancing is not detected; D301/D316 take the returned power for seconds

**What is wrong.** The returned current (≈ 1.0–1.6 A) flows FLYBUS → D1 → TAP16 node → harness →
cells → TAP0 harness → TAP0 node → secondaries.

- If wire 16 opens, the TAP16 node is held only by D316 in breakdown.
- If wire 0 opens, the TAP0 node is held by D301 in breakdown.

The node moves by V_BR − V_cell: SMA6T6V7AY V_BR is 6.4–7.07 V at 1 mA (LT8584 Table 5), minus a
3.45 V cell, so ≈ 3.0–3.6 V. FLYBUS measured against GND_B then rises by about the same amount:

- ≈ 3.2 V typical above its normal stack + 0.57 V.
- REQ-F5 trips only at "last stack + 4 V".
- The 2 MΩ/100 kΩ 1 % divider alone adds ±2 % (±1.1 V at 55 V).

So the analog watchdog does not trip reliably. Detection waits for the next muted measurement, up
to 5 s (C-11).

Intermediate taps are benign: the affected channel reaches LT8584 UVLO (2.1–2.45 V, p.3) before a
TVS conducts. Only taps 0 and 16, which carry the return current, are exposed.

**Consequence.**
- D316 or D301 dissipates ≈ 1.6 A × 6.7 V ≈ 7–11 W for up to 5 s, which is beyond an SMA TVS's
  multi-second capability.
- C116/C216 (or C101/C201), rated 6.3 V, sit at 6.7–7.1 V.
- C-10 says "for ≤ 1 ms", which is not true. REQ-15 ("within 1 s while balancing") is not met.
- H-9's statement that "the BAL_EN string spans TAP16…TAP0, so losing either end disables every
  channel" is false for a harness break, because the on-board nodes stay alive through the TVS.

**Fix.**
- While balancing, convert cells 1 and 16 unmuted every ≤ 50 ms; the ADBMS1818 can measure two
  cells in < 1 ms. Stop if either reads > 4.4 V.
- Also, or instead, compare FLYBUS with the live sum of cells using 0.1 % divider resistors and a
  ≤ +2 V threshold.
- Rate C1kk/C2kk at 10 V, at least for channels 1 and 16.
- Correct C-10 and H-9.

### M-2 D2 clamps FLYBUS below the LT8584's own open-output detection, so the open-return protection depends on firmware

**What is wrong.** On its own, the LT8584 detects an open secondary by its 45–50 V SW clamp and
latches off after the 80–360 ns blanking time (p.3; "Overvoltage Protection", p.13). With 1:4 that
happens at FLYBUS ≈ 4 × (50 − 4.2) ≈ 183 V.

D2 (SMBJ70A) clamps FLYBUS at 78–94 V. That reflects to only (94 + 1)/4 + 4.2 ≈ 28 V on SW, so the
LT8584 never sees a fault and keeps delivering ≈ 1.6 A × 94 V ≈ 150 W into D2. Only REQ-F5, a
firmware ISR, stops it.

**Consequence.** Take a lifted D1, and the MCU hung or the ISR broken:
- The ADBMS1818 watchdog clears DCC after 1.8–2.2 s (LTC6813-1 tSLEEP, Table 16).
- D2 absorbs ≈ 300 J against a ≈ 0.6–0.9 J rating.
- PA1 holds BAL_EN in its last state, so the opto path gives no help.

The result is an SMB package at hundreds of watts in a battery cabinet. C-15 itself shows that even
a 10 ms software loop is too slow. The 2.2 s hardware backstop is 2,000 times slower than needed.

**Fix.** Add a hardware trip: a comparator or shunt reference on FLY_SNS that pulls Q1_B low, or
breaks the string, with no firmware involved. Or let the LT8584 latch do the job: drop D2, use
C6kk ≥ 250 V surge (LT8584 p.22 asks for > 50·N = 200 V), and confirm D1 is not exposed.

### M-3 ADBMS1818 S pins drive LT8584 DIN with no series resistance

**What is wrong.** H-2 says "an ADBMS1818 pin short passes ≤ 0.3 A through two 100 Ω filters".
That is true for C pins only. Each S pin goes straight to DIN, and DIN is rated only ±10 V to its
own GND (LT8584 p.2).

An internal ADBMS1818 failure (for example after a hot-plug event) that joins S16 to V−, or one S
to a distant S or C, connects cell k's IC to TAP0 or another far tap. The only current limit is
the ESD structures of two ICs.

**Consequence.** There is a path between non-adjacent taps capable of well over 0.5 A, which
REQ-9 forbids. This is exactly the "pathway for voltage to jump" the brief asks to rule out.

**Fix.** Put a resistor in each S_k line. For example, 10 kΩ 0603 limits a 67 V short to 6.7 mA
and costs ≤ 60 mV at DIN's 1–6 µA pull-up current (p.3). Place it at the ADBMS pin.

### M-4 Board fuses carry multi-cell faults beyond their interrupting rating (REQ-10 not met)

**What is wrong.** The Nano2 451 5 A fuse interrupts 50 A at 125 V or 300 A at 32 VDC (Littelfuse
451/453). Because its I²t is 5.6 A²s against 71 A²s for the 3AB, it always melts first. Several
faults put far more than that through two board fuses:

| Fault | What happens | Current through two board fuses |
|---|---|---|
| T1kk interwinding breakdown (accepted residual) | TAPk joined to TAP0 | up to 67 V / 0.12 Ω = 560 A |
| Harness landed reversed (installer error, covered by REQ-14) | TAP0 → D2 (forward) → FLYBUS → D1 (forward) → TAP16 shorts the stack | ≈ (51 − 2)/0.12 ≈ 400 A |
| Ring 0 landed on B+ | D301 forward across 15 cells | ≈ 390 A at 48 V |

C-7 credits the 3AB with clearing these. In fact the Nano2, in its OMNI-BLOK holder, opens first,
outside its rating, and the 3AB only clears afterwards as series back-up.

**Consequence.** Series back-up will probably clear the fault, but the board fuse may rupture or
sustain an arc first. REQ-10 ("every fault path has a fuse rated for its voltage and prospective
current") is false as written.

**Fix.** Use a board fuse with a DC interrupting rating of ≥ 80 V at ≥ 600 A, or qualify the Nano2
+ 3AB series combination by test (extend F-3/F-6 to these cases) and document it as back-up
protection. Also add a series diode or reverse-polarity block so that a reversed harness cannot
forward-bias D2 and D1 together.

### M-5 Both enables share one MCU, and no hardware stops over-charge or over-discharge

**What is wrong.**
- S_k (DCC bits) and BAL_EN are both commanded by U2.
- The ADBMS1818 watchdog resets on any valid command (LTC6813-1 p.35). A firmware fault that keeps
  talking SPI therefore defeats both "independent" enables and the watchdog together.
- The only hardware floor is LT8584 UVLO at 2.1–2.45 V (p.3), which is below the LFP minimum.
- H-5 (returned energy over-charging full cells) is firmware-only, as the design itself admits
  (`single_fault_safe=False`).
- The pack BMS cannot open this load, because the balancer sits upstream of its switch.

**Consequence.** One firmware defect can over-discharge a cell to UVLO or push full cells above
3.65 V at n × 0.13 A, with nothing that can stop it.

**Fix.**
- Add a hardware interlock that is independent of U2. The cheapest is a "BMS OK" input (isolated,
  through the user port) in series with the opto string or Q1's base, driven by the pack BMS's
  charge-enable or fault output. That puts the BMS's independent OV/UV detection in charge of
  BAL_EN.
- Optionally add an external window watchdog (needs a toggling GPIO) in the same series path.
- Reword H-4 as "independent of hardware faults, not of firmware".

## MINOR

1. **No low-side FLYBUS supervision.** A cracked C6kk or a shorted D1kk collapses FLYBUS. The
   remaining channels then pump ≈ 0.6 W each into the short (demagnetising at ≈ 1 V), so about
   5 W goes into a cracked MLCC. **Fix:** make the PA0 analog watchdog a window, adding a trip at
   FLYBUS < stack − 5 V while balancing.
2. **Brief fit on LFP depends on the charger.** C-4 balances only above 3.45 V and stops below
   3.40 V. Many home inverters float LFP at 3.35–3.375 V/cell, and some charge only to 90 %. The
   "2 h/day" window (C-2) is assumed, not verified. **Fix:** add a question about the user's
   charge profile, and log time-in-window. The top-balance-in-the-knee method itself is sound.
3. **Hot-plug with pin 1 mating last.** Buck inrush (R9 limits it to 0.67 A) returns through D301
   in forward conduction. That puts U101 VIN and ADBMS C1−C0 at ≈ −0.9 V for ≈ 0.2 ms, against
   −0.3 V abs max (LT8584 p.2). **Fix:** use a staggered or longer pin 1, or a Schottky across
   cell 1 in addition to the TVS. Also add this case to F-7.
4. **ISO7721 side 1 powered from PB0.** With PB0 off and PA2 idling high, INB is back-powered
   (abs max VCC1 + 0.5 V). Host traffic is also lost while side 1 is off. **Fix:** set PA2 low or
   high-Z when PB0 is off, or power VCC1 from +3V3.
5. **The user-port working voltage (250 Vrms) is not derived.** If Q-3 turns out to be a
   non-isolated DC link, the battery-to-earth voltage could reach a few hundred volts DC plus
   ripple. The fault-contact barrier has no margin: 5.0 mm required against a 5.6 mm pad gap.
   **Fix:** derive the working voltage from the inverter topology when Q-3 is answered.
6. **Thermal sensing is sparse.** There are 3 NTCs for 16 channels, at U103, U106 and U112.
   Channels 8–9 (the hot east end) and 13–16 have no sensor, yet REQ-F3 is the only thermal
   protection. **Fix:** fit one NTC per 2–4 channels; the GPIOs are free.
7. **Transformer waiver (6.8 A against 7.0 A).** The reasoning is sound (ADI's Table 3 pairing),
   but Coilcraft specifies Ipk at 25 °C (Doc 1075 note 7) and ferrite B_sat falls when hot.
   **Fix:** run T-EFF and the saturation check at a hot core temperature (≥ 100 °C).
8. **Footprint detail.**
   - The LT8584 land (EP 2.94 × 3.58 mm, matching FE16 Variation BC, p.34) has no thermal vias, yet
     placement asks for ≥ 9 vias.
   - The ADBMS1818 EP land is 5 × 5 mm against ADI's 5.74 mm.
   - The J2/J4 order numbers are marked [I].

   Resolve these before layout.

## Waivers checked

| Waiver | Verdict |
|---|---|
| T1kk 97 % peak current | Valid, with the caveat in minor item 7. |
| LM5164 BST–SW 5 V | Valid: the internal regulator sets it, and the 2.2 nF BST capacitor is fitted. |
| VIO_ISO without a fuse | Valid: µA–mA of host logic supply, and a fuse could not act. |
| 7 PWR_FLAG ERC pin-to-pin warnings | Valid: emitter artefacts. GPIO4–9 tied to V− and PB0 sourcing ≤ 4 mA are legitimate. |

## Recomputed values

| Item | Result |
|---|---|
| Balancing current | 2.45 A at 3.15 V. Agrees with Fig. G32 (≈ 2.5 A at 50–55 V). |
| Efficiency | 82 % board (G33). (8.63 W − 0.75 W harness) × 0.82, less the D1 drop (0.8 %) and return-wire IR: **≈ 74 % end to end**. Matches C-8 within 1 %. |
| Thermal, 8 channels | ≈ 12 W total. LT8584 T_J ≈ 91 °C. Plausible; derating needed as stated. |
| Quiescent per cell | ≤ 25 µA worst case (1 µA shutdown + 4 µA SW leak + 20 µA TVS at 5 V). Controller loads hang on the whole stack, so they are balanced. Correct. |
| Inline fuse | 7 A, I²t ≤ 150 A²s against 18 AWG ≈ 8,900 A²s. The wire is protected. |
| Fault currents | One cell 34 A, clearing in ≈ 5 ms, within 300 A at 32 V. |
| Buck | UVLO 1.5 V × 5.0 M/300 k = 25 V. On-time 298 ns. Sleep IQ ≤ 25 µA (SNVSAU4D). |
| Opto string | GB-rank CTR(sat) ≥ 30 % at 1 mA. Drive margin ≈ 3.6×. |

## Verified correct

- **LT8584 pinout** (p.2): GND 1–4 and 17, MODE 5, RTMR 6, DIN 7, OUT 8, VIN 9, VCELL 10, VSNS 11,
  DCHRG 12, SW 13–16. The netlist for U107 matches.
- **LT8584 simple-mode wiring.** MODE tied to VIN; RTMR grounded (p.23); VCELL and VSNS tied to VIN
  (p.22). Enable = DIN low AND DCHRG high (p.13–14, Fig. 3), so the two-enable scheme is valid.
- **Channel components against ADI's simple-mode and stackable circuits** (p.32, p.36, Table 5,
  Table 3):
  - 2 × 100 µF CVCELL/CTRAN
  - 1 µF CVIN
  - 47 nF on OUT
  - 22 nF / 4.99 kΩ RCD snubber
  - SMA6T6V7AY cell TVS
  - 1 µF+ 100 V per-channel output capacitor
  - NA5743-AL
  - output diode ES1G (VRRM 400 V ≥ N·(50 + VIN) = 217 V, p.21)
  - V8P10 return diode = ADI's "D13" (Fig. 12, Table 8). ADI's 20 kΩ across it is omitted, which
    is acceptable.
- **SW stress.** 4.2 + 68.7/4 = 21.4 V < 40 VDC, and the clamp at 38.5 V is below the 42 V minimum
  internal clamp.
- **NA5743 transformer** (Doc 1075):
  - Windings 1–3 and 2–4 with dots at 1 and 2; secondary 5–8 with the dot at 8. Pins 6 and 7 have
    no winding.
  - The flyback polarity in the netlist is correct.
  - Custom footprint: 2.03 × 1.27 mm pads, 2.50 mm pitch, 11.68 mm inner-edge gap, so centres at
    ±6.855 mm. CCW top-view numbering. Matches the recommended land pattern.
- **ADBMS1818 pin map** (Table 14/15, LTC6813-1 p.3):
  - V+ 1; C(n) at 38 − 2n; S(n) at 39 − 2n; GPIO 39–47; VREG 48, DRIVE 49, VREF2 50, VREF1 51,
    DTEN 52, SDI 53, SDO 54, ISOMD 55, WDT 56, IBIAS 57, ICMP 58, V− 59/60/65, CSB 61, SCK 62,
    IMB 63, IPB 64.
  - Unused C17/C18 tied to C16, with S17/S18 open (LTC6813-1 p.85).
  - DTEN = V− means the watchdog clears DCC in 1.8–2.2 s.
  - V+ within 16–90 V; VIH(SPI) 2.3 V, compatible with 3.3 V logic; 5 kΩ SDO pull-up present.
- **STM32G031K8T6 LQFP32** (DS12992 Fig. 5): PA0–PA8, PB0–PB2, PB8/PB9, PA13/PA14 and PF2-NRST
  as listed. PA0 is FT_a.
- **Other pinouts.** ISO7721DWV pins 1–8; LM5164DDA (Table 4-1); MCP1700 SOT-23 (GND/VO/VI);
  TPD4E05U06DQA; TLP293 (1 A, 2 K, 3 E, 4 C); AQY210EH (1 A, 2 K, 3/4 out); MMBT5551L (B/E/C);
  V8P10 (pins 1, 2 anode, tab cathode).
- **J1 footprint.** 17 pads at 5.08 mm, 2.08 × 3.6 mm, 1.4 mm drill, pin 1 marked. The MSTBA and
  MSTB order numbers fit Phoenix's numbering sequence.
- **Fuses.** 0324007: 10 kA @ 125 VDC, cold resistance 18.7 mΩ, I²t 71 A²s. Board-to-inline
  selectivity holds for single-cell faults.
- **DRU rules.**
  - BAT0↔USER 8.0/8.0 mm and BAT0↔FAULT 5.0/3.8 mm are inherited by every battery-side netclass
    (C, SW, SNS, STR, STACK, RET, CTRL, BOOT).
  - The battery-side edge rule (3 mm) and hole rule (3 mm) cover the chassis barrier B-5.
  - USER↔FAULT 0.6 mm.
  - All match the DESIGN.md §6.3 table.
- **Placement intent.**
  - Tap corridors are ordered by potential, and J1's pin order runs south to north.
  - The mirrored rows put CH8 next to CH9 (one cell apart). The largest across-spine difference is
    CH1 against CH16 (≈ 63 V), which the generated rules cover.
  - Transformer secondaries face the spine, with keepouts in the pad gaps.
  - The 1210 MLCC edge keepout, the U5/U6 straddle and the hot loops are declared.
  - I found nothing in `intent.yaml` that would let a placer join non-adjacent channel copper
    without violating a rule.
