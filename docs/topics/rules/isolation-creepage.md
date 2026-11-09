# Isolation, creepage and clearance, high-voltage and mains safety

Scope: canonical home for safety spacing: creepage/clearance lookup chain (IEC 60664-1, 62368-1), IPC-2221B functional floor, slots, isolator keep-outs, ISO rule IDs. Not here: flyback layout and spark-gap placement -> [power/flyback-offline.md](power/flyback-offline.md); engine design -> [checkers-power.md](checkers-power.md#safety-spacing-engine).
Keys: creepage, clearance, isolation, reinforced, basic, functional, pollution degree, PD2, material group, CTI, overvoltage category, OVC, impulse voltage, altitude, IEC 60664-1, IEC 62368-1, SLUP419, SLLA284G, IPC-2221B Table 6-1, B4 0.00305 mm/V, slot, hi-pot, Y-cap, spark gap, ISO-01, ISO-08

## Safety spacing rules
1. Safety spacing is a lookup chain, not one DRC number: insulation grade from the end-product standard; creepage = f(working V_RMS, PD, material group/CTI), ×2 reinforced; clearance = f(impulse voltage from mains V × OVC, PD, altitude).
2. IPC-2221B and IPC-9592B cover functional spacing only, not user safety: apply the stricter of IPC and the safety standard.
3. Slots add creepage, not clearance, and count only above the PD minimum width (≥1.0 mm at PD2). Nothing on any layer under isolators and transformers.
4. The LLM only proposes net voltage classes and insulation grades from schematic and product context; **a human confirms** (safety-critical); a deterministic engine computes spacing. BMS stacks derive classes from cell index × cell voltage ([power/chargers-bms.md](power/chargers-bms.md)).
5. Checkers: KiCad 10.0 native `creepage` for the surface path where it suffices; else custom 2-D surface-geodesic check counting only slots ≥ PD minimum; 3-D clearance checker. Trap detector: package CTI group vs PCB material group → suggest a slot. Suggest hi-pot substitution only for functional isolation.
6. Corrected: IPC-2221B >500 V B4 rate 0.00305 mm/V (not 0.005).

## Spacing method
TI SLUP419 ( rev. Mar 2024, [PDF](https://www.ti.com/lit/pdf/slup419)) [P]:
- *Creepage:* working voltage + material group + pollution degree. Basic vs reinforced per IEC 60950-1 Fig. 2H; double the value for reinforced.
- *Tables by equipment:* IEC 60664-1 Table F.4 (general); IEC 62368-1 Table 17 (AV/ICT); IEC 61800-5-1 Table 10 (motor drives); IEC 62109-1 Table 14 (solar).
- *Clearance:* impulse voltage from F.1 (mains × OVC), then F.2 (or IEC 62368-1 Table 10, which gives basic and reinforced). Reinforced under other standards means one impulse step up.
- *Altitude:* above 2000 m multiply by the IEC 60664-1 Table A.2 factor.
- *Scope:* IPC-2221B and the stricter IPC-9592B "address proper or functional operation only and do not address user safety".
- *Coating* can lower PD (IEC 62109-1 via IEC 60664-3), or IEC 62368-1 Table G.13 can be used for coated boards.

## Lookup tables
From SLUP419 [P].
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
- **Altitude factor on clearance** (IEC, as commonly reproduced; 5000 m confirmed in SLUP419 [P]): 5 km 1.48, 10 km 3.02, 15 km 6.67, 20 km 14.50. Pressure ratios and Paschen physics -> [hv-and-manufacturing-physics](../physics/hv-and-manufacturing-physics.md#altitude-and-paschen).
- **Worked example** (telecom AC/DC, 265 V, OVC II, PD2, 5000 m, reinforced): creepage 4 / 5.6 / 8 mm (MG I / II / III), i.e. 2/2.8/4 × 2 per 62368-1 Table 17. Clearance 3.6 mm × 1.48 = **5.33 mm**.

## When spacing cannot be met
SLUP419 [P].
- A slot increases creepage, not clearance. Minimum slot width: 0.25 mm (PD1), **1.0 mm (PD2)**, 1.5 mm (PD3).
- Conformal coating helps when clearance cannot be met.
- For functional isolation only, a routine hi-pot can substitute, typically at 2 × V_working + 1000 V (265 VAC → 1530 V, hence the common 1.5 kV test).
- **Common trap:** a group-I IC package (4 mm creepage) on a group-IIIa PCB (8 mm needed). The usual fix is a slot.

## Digital isolator layout
TI SLLA284G (digital isolator design guide, [PDF](https://www.ti.com/lit/pdf/slla284)) [P]:
- ≥4 layers for low EMI, stacked HS signal / GND / power / LS signal.
- On all layers, the space under the isolator is free of traces, vias and pads.
- A groove >1 mm wide counts if creepage + groove width + 2 × depth ≥ required, without weakening the board.
- Higher package CTI allows a smaller package for the same voltage.

## Other isolation sources
- PI AN-72 ([PDF](https://www.power.com/sites/default/files/documents/an-72_innoswitch3_family_design_guide_20251107.pdf)) [P]: >8 mm primary↔secondary, spark gaps 6.4 mm (5.5 acceptable) vs "at least 5.4 mm" (inconsistent), 0.4 mm mylar pad for a barrier-crossing heat spreader -> [power/flyback-offline.md](power/flyback-offline.md#pi-an-72-flyback-layout-rules).
- TI BQ76952: PCB spark gaps as copper (E prefix), no part installed [P].
- [smps.us calculator](https://pcbdesign.smps.us/creepage.html) [S]: coated boards may use 62368-1 Table G.13; reinforced creepage is double basic.

## IPC-2221B Table 6-1
(Functional floor; [EMA reproduction](https://www.ema-eda.com/ema-resources/blog/pcb-clearance-and-creepage-distance-table/)) [S], VR rows VERIFIED, **B4 rate CORRECTED**:

| Voltage | B1 internal | B2 external uncoated (≤3050 m) | B3 | B4 external, permanent polymer coat |
|---|---|---|---|---|
| 31–50 V | 0.1 mm | 0.6 mm | 0.6 mm | 0.13 mm |
| 301–500 V | 0.25 mm | 2.5 mm | 12.5 mm | 0.8 mm |
| >500 V, per V | 0.0025 | 0.005 | 0.025 | **0.00305** mm/V |

- Solder mask is **not** a B4 coating. Altitude derating applies.
- JLCPCB's blog table disagrees with these and is treated as an outlier.

## Isolation rule IDs
RPA §9, §6 [I].

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

## Open questions
- **Paywalled standards:** IEC 60664-1, 62368-1 and 61010-1 were not read. Other Table 17 voltages, Table G.13 coated values and ES1/ES2/ES3 boundaries need the standard.
- **Not researched:** mains input-filter layout (X/Y caps, CM choke, input/output separation) and MOV/fuse placement.
- **KiCad 10.0 parses a native `creepage` constraint** (minimum surface path between nets; DRC key `creepage`) [P] ([drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md)). Still to test: how it treats slots and the PD minimum slot width.
- **What kae does today (register RC10, kept):** no voltage-dependent clearance of its own; the board's rules win and the router uses only them. Every report warns (`hv_clearance_below_ipc`, [hazards.md](../architecture/hazards.md)) when a net kae.circuit puts above 30 V sits in a class whose clearance is below the IPC-2221B B2 row for its voltage. Inferred voltages are not a safety classification (ISO-01 needs a human), so this stays a warning, not a rule kae applies [I].

## Sources
- [rules_power_rf_analog_dfm.md § 6, § 9, § 10, § 20](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B (DFM-10)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [power/flyback-offline.md](power/flyback-offline.md), [checkers-power.md](checkers-power.md), [dfm-fab-limits.md](dfm-fab-limits.md)
