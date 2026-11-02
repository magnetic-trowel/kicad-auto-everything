# Crystals and clocks

Scope: crystal placement window, parasitic budget, guard/keep-out, vendor conflicts; clock driver placement, clock vias, differential clock buffers, spread spectrum. Not here: slow multi-drop clock topology -> [interfaces/i2c-spi-qspi.md](interfaces/i2c-spi-qspi.md#slow-multi-drop-clock-topology-limits); EMC zoning -> [emc-placement.md](emc-placement.md).
Keys: crystal, oscillator, Pierce, XIN, XOUT, load capacitance, C_L, stray capacitance, pullability, guard ring, metal can, AN2867, AVR186, SLAA322D, Espressif, clock buffer, REFCLK, spread spectrum, SSC, xtal_pierce, XTAL-DMAX
Tags: [P] primary, [S] snippet, [I] inference, [VR] verification_rules.md.

## Crystal placement and scoring rules
1. Placement is an annulus: `distance_window` [dist_min (vendor: ESP32 ≥2.7 mm, ESP32-S3 ≥2.0 mm), 12 mm (Microchip)] as objective (minimise inside the window); `same_side`; caps on both sides of the crystal, CL1 (XIN cap) first, series R at the chip side. "≤5 mm" is a heuristic [VR].
2. Score parasitic capacitance (trace length × C′ from the stackup) against XIN–GND 1 pF / XOUT–GND 2 pF / XIN–XOUT 0.5 pF (total stray 2–5 pF); each 0.1 pF matters (0.175 pF × 45 ppm/pF ≈ 7.8 ppm, ST).
3. Keep-out: rule area `disallow track via` for foreign nets on F.Cu and the adjacent layer; HS traces and magnetics radius 3 mm [I] (uncalibrated warning); zero test points on oscillator nets; XIN/XOUT separation `D ≥ H·√(1/K − 1)` ([si-fundamentals.md](si-fundamentals.md)) [I], not a bare "3W".
4. GND guard ring around the circuit, no foreign nets inside or under it; tie scheme, can grounding and copper-under are switched by the MCU vendor profile (single tie to MCU GND/AVSS per ST AN2867, TI SLAA322D vs stitched into main ground with dense GND vias per Espressif).

## Crystal rule table
Source: [IF] §7.

| ID | Value | Source |
|---|---|---|
| XTAL-DMAX | ≤12 mm (½ in) from the oscillator pins; same side; load caps adjacent and on the same side; grounded pour around the circuit routed directly to MCU ground, with no signal or power traces inside; on 2-sided boards, no traces under the crystal; tie broken guard sections to a mirrored ground layer | [Microchip dsPIC33AK](https://onlinedocs.microchip.com/oxy/GUID-E48B4A26-F201-4F0A-BCBA-16461582816A-en-US-4/GUID-AA04B64F-3C38-4E1C-8B51-49DE3CFE2419.html) [P] |
| XTAL-DMIN (vendor-specific) | "Placed far from the clock pin to avoid interference on the chip": ≥2.7 mm (ESP32), ≥2.0 mm (ESP32-S3). Dense GND vias around the clock trace; **no vias on the clock input/output traces** [VR]; series parts near the chip; load caps on both sides of the crystal, not directly connected to the series parts; no signal traces under the crystal; power-trace vias kept away from the clock; "no magnetic components nearby"; top-layer keep-out if top ground suffices; complete GND under the RF section, crystal and chip | [Espressif ESP32](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html); [ESP32-S3](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html) [P] |
| XTAL-PAR | XIN–GND 1 pF, XOUT–GND 2 pF, XIN–XOUT 0.5 pF (AVR186 typicals); stray 2–5 pF (AN826); C_SHUNT 4.5 pF with 20 pF load (TUSB9261); AN-1469 implies ~3.5 pF (C_L1 ≈ 2·C_L − 7 pF; start at 33 pF if unknown); 2–3 pF internal + 7 pF external → C_L 9 pF (SWRA495L) | [AVR186](https://www.insidegadgets.com/wp-content/uploads/2013/02/Best-Practices-for-the-PCB-layout-of-oscillators.pdf); [AN826](https://ww1.microchip.com/downloads/en/AppNotes/00826a.pdf); [TUSB9261](https://www.ti.com/lit/ds/symlink/tusb9261.pdf); [SNLA079D](https://www.ti.com/lit/pdf/snla079); [SWRA495L](https://www.ti.com/lit/pdf/swra495) [P] |
| XTAL-SENS | 0.175 pF × 45 ppm/pF ≈ 7.8 ppm; LSE C_L ≥6 pF (7 pF compromise); oscillator gain margin >5; PC13 toggling can shift the LSE; Cs = pin + PCB parasitic (used in the C_L calculation); 802.15.4 needs ±40 ppm (SWRA495L) | [ST AN2867](https://ecsxtal.com/store/pdf/stm32-microcontroller-application-note.pdf) [P; VERIFIED, no mm values] |
| XTAL-GUARD | AN2867: guard ring "essential"; dedicated oscillator ground plane connected to the nearest MCU ground. SLAA322D: clean guard tied to AVSS only; on 2-layer boards, no digital lines under the crystal and fill with clean ground. AVR186: guard ring on single-layer boards | AN2867; [SLAA322D](https://www.ti.com/lit/pdf/slaa322); AVR186 [P] |
| XTAL-CAP | Place the XIN cap first and closest; NPO/C0G; short symmetric crystal → CL1 → CL2 loop with cap grounds close together; never route the ground between the caps or around the crystal; keep cap grounds clear of USB, RS-232, LIN, PWM and power return currents; include trace capacitance in C_L | AVR186; SLAA322D [P] |
| XTAL-SEP | Route XIN and XOUT apart | AVR186; SLAA322D |
| XTAL-TP | Avoid test points ("too many test points" is a listed fault); avoid asymmetry; conformal coating "highly recommended" for LSE in humid environments | AN2867 [VERIFIED] |
| XTAL-MAG / HS | No magnetics nearby (Espressif). No HS traces under or near crystals, oscillators, clock generators, switching regulators, mounting holes or magnetics (TI). Fast digital signals away from the crystal (Nordic) | Espressif; [SPRAAR7J p.9](https://www.ti.com/lit/pdf/spraar7); Nordic [P] |
| XTAL-EDGE | Crystal ≥5 mm from the board edge and ≥10 mm from cable connectors; foreign lines under the package with no plane in between are flagged (emcvisual, citing Infineon AP24026 and ST AN2867) | [emcvisual](https://github.com/tombueng/emcvisual/blob/main/docs/RULES.md) [P] |
| **XTAL-CAN** | **Conflict:** ST: "do not connect [a metal can] to the oscillator ground". TI SLAA322D/AVR186: housing to ground. TUSB9261: VSSOSC must not connect to the PCB ground plane | Vendor switch |
| **Copper under crystal** | **Conflict:** solid or clean ground (Microchip, AVR186, SLAA322D, SWRA495L, Espressif, Nordic) vs "cut ground and power planes" (TI CDCE925 [S]). Resolution: ground for an MCU Pierce; cut only when the device datasheet asks | — |

## Clock routing rules
- **Clock driver placement.** Place the clock driver next to its oscillator. Any part that talks exclusively to one other part goes next to it ([LearnEMC](https://learnemc.com/other-good-emc-design-guidelines) [P]).
- **Clock vias.** Clock vias should be "completely surrounded": use a C-shaped ring of GND vias at every clock and RF transition ([Qualcomm CXO](https://docs.qualcomm.com/doc/80-PV086-5P/topic/CXO-and-SLEEP_CLK-routing.html) [P]).
- **Slow multi-drop clocks (SLEEP_CLK):** star branches within 30 mm, daisy stubs <7 mm (Qualcomm) -> [interfaces/i2c-spi-qspi.md](interfaces/i2c-spi-qspi.md#slow-multi-drop-clock-topology-limits).
- **Differential clock buffers (Renesas, PCIe)** ([Renesas](https://www.renesas.com/en/document/apn/pcie-buffer-mux-layout-recommendations?r=1565126) [P]): nothing between the two lines; 0402/0201 parts; same layer and via count; "1 mm ⇒ 6 ps"; GND via at each layer change; ≥3W spacing (5W optimal); one GND via per decap.
- **Spread-spectrum clocking** lowers peak readings only when the new spectral lines are >100 kHz apart. Never use it as a reference for Ethernet, Fibre Channel or SONET transceivers, PLL-based CPUs, or RF ([Johnson](https://www.sigcon.com/Pubs/edn/clockmod.htm) [P]). Prefer slower edges and differential or low-swing clocks.
- **Edge rate.** Clock rise/fall below 10% of the period is an Ott red flag.
- **Placement order.** Clocks go next to their consumer, away from the I/O zone and the edges ([emc-placement.md](emc-placement.md)).

## Open questions
- No primary numeric distance from crystal nets to switch nodes, inductors or HS traces; 3 mm and 5 mm are heuristics.
- Silicon Labs AN0016 and Abracon notes not retrievable.

## Sources
- [interface_rule_packs.md § 7, 11 (xtal_pierce)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md); [verification_rules.md § 1A crystal row, 1B AMS-08, 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [rules_highspeed_emi.md § 4, 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
- See also [rule-pack-format.md](rule-pack-format.md), [interfaces/pcie.md](interfaces/pcie.md).
