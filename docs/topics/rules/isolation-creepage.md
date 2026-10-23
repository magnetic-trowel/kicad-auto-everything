# Isolation, creepage and clearance, high-voltage and mains safety

**TL;DR**
- **Safety spacing is a lookup chain, not one DRC number.**
  - Insulation grade comes from the end-product standard.
  - Creepage = f(working V_RMS, pollution degree, material group/CTI), ×2 for reinforced.
  - Clearance = f(impulse voltage from mains V × overvoltage category, PD, altitude).
- **IPC-2221B and IPC-9592B cover functional spacing only,** not user safety. Apply the stricter of IPC and the safety standard.
- **Slots add creepage, not clearance,** and count only if wide enough (≥1.0 mm at PD2). Keep everything off every layer under isolators and transformers.
- **Corrected IPC-2221B >500 V B4 rate: 0.00305 mm/V** (not 0.005).
- **The LLM may only propose net voltage classes and insulation grades.** A human confirms them; a deterministic engine computes the spacing.

## Key facts

**Method** (TI SLUP419, rev. Mar 2024, [PDF](https://www.ti.com/lit/pdf/slup419)) [P]:
- *Creepage:* working voltage + material group + pollution degree. Basic vs reinforced per IEC 60950-1 Fig. 2H; double the value for reinforced.
- *Tables by equipment:* IEC 60664-1 Table F.4 (general); IEC 62368-1 Table 17 (AV/ICT); IEC 61800-5-1 Table 10 (motor drives); IEC 62109-1 Table 14 (solar).
- *Clearance:* impulse voltage from F.1 (mains × OVC), then F.2 (or IEC 62368-1 Table 10, which gives basic and reinforced). Reinforced under other standards means one impulse step up.
- *Altitude:* above 2000 m multiply by the IEC 60664-1 Table A.2 factor.
- *Scope:* IPC-2221B and the stricter IPC-9592B "address proper or functional operation only and do not address user safety".
- *Coating* can lower PD (IEC 62109-1 via IEC 60664-3), or IEC 62368-1 Table G.13 can be used for coated boards.

**Lookup subsets** (from SLUP419) [P]:
- **Material group by CTI:** I ≥600 V; II 400–600; IIIa 175–400; IIIb 100–175. TI isolators are group I; typical FR-4 is III/IIIa.
- **Pollution degree:**
  - PD1: none, or dry non-conductive (coated);
  - PD2: occasional condensation (labs, offices, server/telecom enclosures);
  - PD3: conductive, or non-conductive made conductive by condensation (industrial);
  - PD4: continuously conductive (outdoor).
- **Overvoltage category:** I (protected circuits) through IV (origin of installation).
- **F.4 creepage (mm):**

  | V_RMS | PD1, any group | PD2 group I | PD2 group II | PD2 group III |
  |---|---|---|---|---|
  | 63 | 0.2 | 0.63 | 0.9 | 1.25 |
  | 400 | 1.0 | 2.0 | 2.8 | 4.0 |
  | 800 | 2.4 | 4.0 | 5.6 | 8.0 |
  | 1000 | 3.2 | 5.0 | 7.1 | 10.0 |

- **F.1 rated impulse (V_peak) by line-to-neutral voltage, OVC I / II / III / IV:**

  | Line-to-neutral | I | II | III | IV |
  |---|---|---|---|---|
  | ≤50 V | 330 | 500 | 800 | 1500 |
  | ≤150 V (US 120 V) | 800 | 1500 | 2500 | 4000 |
  | ≤300 V (EU/China 230 V) | 1500 | 2500 | 4000 | 6000 |
  | ≤600 V | 2500 | 4000 | 6000 | 8000 |

- **F.2 clearance** (IEC 62368-1 Table 10 values in parentheses):
  - 0.5 kV: 0.04 (PD1) / 0.2 (PD2) / 0.8 mm (PD3);
  - 1.5 kV: 0.5 (0.76) mm at PD1–2, 0.8 mm at PD3;
  - 2.5 kV: 1.5 (1.8) mm;
  - 4.0 kV: 3.0 (3.8) mm;
  - 6.0 kV: 5.5 (7.9) mm.
- **Worked example** (telecom AC/DC, 265 V, OVC II, PD2, 5000 m, reinforced): creepage 4 / 5.6 / 8 mm (MG I / II / III), i.e. 2/2.8/4 × 2 per 62368-1 Table 17. Clearance 3.6 mm × 1.48 = **5.33 mm**.

**When spacing cannot be met** (SLUP419) [P]:
- A slot increases creepage, not clearance. Minimum slot width: 0.25 mm (PD1), **1.0 mm (PD2)**, 1.5 mm (PD3).
- Conformal coating helps when clearance cannot be met.
- For functional isolation only, a routine hi-pot can substitute, typically at 2 × V_working + 1000 V (265 VAC → 1530 V, hence the common 1.5 kV test).
- **Common trap:** a group-I IC package (4 mm creepage) on a group-IIIa PCB (8 mm needed). The usual fix is a slot.

**TI SLLA284G** (digital isolator design guide, [PDF](https://www.ti.com/lit/pdf/slla284)) [P]:
- ≥4 layers for low EMI, stacked HS signal / GND / power / LS signal.
- On all layers, the space under the isolator is free of traces, vias and pads.
- A groove >1 mm wide counts if creepage + groove width + 2 × depth ≥ required, without weakening the board.
- Higher package CTI allows a smaller package for the same voltage.

**PI AN-72** (offline; [PDF](https://www.power.com/sites/default/files/documents/an-72_innoswitch3_family_design_guide_20251107.pdf)) [P]:
- >8 mm primary↔secondary, especially under the InSOP package and transformer. No traces under the IC; no spark gaps near or across it.
- Spark gaps from the secondary output terminals to one AC input after the fuse: 6.4 mm (5.5 acceptable) in the layout section vs "at least 5.4 mm" in the ESD section, which is inconsistent. Also one across the CM choke.
- A heat spreader crossing the barrier needs a 0.4 mm mylar pad (reinforced).

**Other sources.**
- TI BQ76952: PCB spark gaps as copper (E prefix), no part installed [P].
- [smps.us calculator](https://pcbdesign.smps.us/creepage.html) [S]: coated boards may use 62368-1 Table G.13; reinforced creepage is double basic.

**IPC-2221B Table 6-1** (functional floor; [EMA reproduction](https://www.ema-eda.com/ema-resources/blog/pcb-clearance-and-creepage-distance-table/)) [S], VR rows VERIFIED, **B4 rate CORRECTED**:

| Voltage | B1 internal | B2 external uncoated (≤3050 m) | B3 | B4 external, permanent polymer coat |
|---|---|---|---|---|
| 31–50 V | 0.1 mm | 0.6 mm | 0.6 mm | 0.13 mm |
| 301–500 V | 0.25 mm | 2.5 mm | 12.5 mm | 0.8 mm |
| >500 V, per V | 0.0025 | 0.005 | 0.025 | **0.00305** mm/V |

- Solder mask is **not** a B4 coating. Altitude derating applies.
- JLCPCB's blog table disagrees with these and is treated as an outlier.

**Rules** (RPA §9, §6) [I]:

| ID | Rule | Numeric | Check | Sev |
|---|---|---|---|---|
| ISO-01 | Every net gets a voltage class; every net pair an insulation grade (functional/basic/reinforced): mains, primary bulk, secondary SELV, earthed chassis | Store V_RMS, V_peak, OVC, PD, MG, altitude | Missing classification = error | S1 |
| ISO-02 | Creepage per pair = table(V_RMS, PD, MG) × (2 if reinforced) | e.g. 400 V, PD2, MG III: 4.0 basic / 8.0 reinforced. RPA's "250 V ≈ 2.5 mm MG III" is from memory, so verify it | Surface-path distance, routed around slots narrower than the PD minimum | S1 |
| ISO-03 | Clearance = F.2 / 62368 Table 10 at the impulse voltage × altitude. Reinforced: one impulse step up under 60664-1; the Table 10 reinforced column under 62368-1 | 230 V OVC II → 2.5 kV → 1.5 mm (1.8); reinforced: 4 kV → 3.0 mm (60664-1), 3.6 mm (62368-1, worked example above; not the 4 kV basic 3.8) | 3-D straight-line, including across slots and bodies | S1 |
| ISO-04 | Barrier keep-out: no copper, vias or pads on any layer under isolators, optos, transformer primary–secondary span; slot centreline under the barrier | Width ≥ required creepage | All-layer rule area per isolating footprint | S1 |
| ISO-05 | Slots valid only above the PD minimum | ≥1.0 mm at PD2 | Edge.Cuts slot width | S1 |
| ISO-06 | Spark gaps as copper features: secondary output → AC after the fuse, and across the CM choke | ~5.4–6.4 mm (PI, device-specific) | Footprint present + gap measured | S2 |
| ISO-07 | Y-cap from primary bulk+ (or AC after the fuse) to secondary rail/return, never via controller ground | — | Y-cap pin connectivity | S2 |
| ISO-08 | Fuse is the first series element from the AC connector; spacing upstream of the fuse also meets the table | — | Topology | S1 (general practice, not primary-read) |
| DFM-10 | HV net class clearance per IPC-2221B (B2/B4) or the safety standard | 301–500 V: 2.5 mm B2 | KiCad custom rules | S1 |

## Recommendations for our system
- **Safety-spacing engine:** deterministic lookup (V_RMS, V_impulse from OVC, PD, MG/CTI, altitude, grade) → (creepage, clearance).
- **Checkers:** KiCad 10.0's native `creepage` constraint for the surface path where it suffices, a custom 2-D surface-geodesic check that counts only slots ≥ the PD minimum where it does not, and a 3-D clearance checker. See [checkers-power.md](checkers-power.md).
- **Classification workflow:** the LLM proposes voltage classes and grades from the schematic and product context, and **a human must confirm** (safety-critical). BMS stacks derive classes from cell index × cell voltage ([power/chargers-bms.md](power/chargers-bms.md)).
- **Trap detector:** package CTI group vs PCB material group; suggest a slot.
- **Escalation rule:** suggest hi-pot substitution only for functional isolation.

## Conflicts and open questions
- **Paywalled standards:** IEC 60664-1, 62368-1 and 61010-1 were not read. Other Table 17 voltages, Table G.13 coated values and ES1/ES2/ES3 boundaries need the standard.
- **Not researched:** mains input-filter layout (X/Y caps, CM choke, input/output separation) and MOV/fuse placement.
- **KiCad 10.0 parses a native `creepage` constraint** (minimum surface path between nets; DRC key `creepage`) [P] ([drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md)). Still to test: how it treats slots and the PD minimum slot width.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 6, § 9, § 10, § 20](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B (DFM-10)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [power/flyback-offline.md](power/flyback-offline.md), [checkers-power.md](checkers-power.md), [dfm-fab-limits.md](dfm-fab-limits.md)
