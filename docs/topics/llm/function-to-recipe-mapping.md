# Mapping recognized functions to layout recipes

Scope: recipe mechanism (recognizer + constraints + checks) and the vendor numbers in our notes. Not here: full rule packs -> [rules/decoupling-pdn](../rules/decoupling-pdn.md), [rules/datasheet-to-constraints](../rules/datasheet-to-constraints.md); block recognizers -> [block-recognition](block-recognition.md).
Keys: recipe, layout recipe, Physics Rule Check, PRC, Pin Distance, Quilter, buck, boost, LDO, decoupling, crystal, via per current, AN-1149, SLYT614, SNVA803, loop area, kicad-happy EMC, SW-002, DC-001, ES-001, ML-001, skew limits, WEBENCH, design blocks, exact-match replay

## Recipe = recognizer + constraints + checks

- A recipe is a data file (CC0 rule-pack licence): recognizer (pin roles + refdes, as in Quilter), constraints with strength, checks with thresholds, citations [I].
- One predicate drives both the placer objective (soft weight) and the post-route acceptance test (hard/soft threshold), as in Quilter where each constraint has its own Physics Rule Checks [V].
- Qualitative strength: "as close as possible" -> `weight=high, bound=null`; corpus percentiles supply soft targets -> [data/measured-priors](../data/measured-priors.md) [I].
- Conflicting vendor numbers: use the conservative value, attach both citations, surface the discrepancy to the user [I].
- Exact match first: replay a known-good sub-layout (KiCad 10 design blocks, atopile sub-PCBs, vendor EVM exports); otherwise generate from constraints [I].
- Datasheet layout statements map to the closed vocabulary of the LLM relation API: `near(C_in, U1.VIN, tight)`, `min_loop({U1.SW, L1, C_out})`, `kelvin(R_sense)` -> [interfaces-relations-vs-coordinates](interfaces-relations-vs-coordinates.md#relation-vocabulary) [I].

## Quilter physics-constraint engine

[V] ([PRC overview](https://docs.quilter.ai/physics-rule-checks-prcs/overview); [Pin Distance](https://docs.quilter.ai/physics-rule-checks-prcs/pin-distance))

| Constraint | Physics Rule Checks |
|---|---|
| Bypass, crystal, switching converter | Pin Distance, Trace Path Length, Layer Switch Count, Ground Plane Overlap |
| Differential pairs | Ground Plane Overlap, Uncoupled Spacing, Length Mismatch |
| Power nets | Overheated Length |
| Single-ended impedance | Invalid Width Span, Ground Plane Overlap |

- Pin Distance = distance between closest pin edges; example passes at "0.13 cm within acceptable range (0 cm to 1 cm)", fails at 1.11 cm.
- Behaviour: converters "tight ground return loops", three passives "as closely as possible"; bypass "smaller capacitance values closer to power pins"; crystal "near their drivers".
- Framing: "constraints at the physics level, not the rules level".

## Generators and modules

| Source | Offer | Tag |
|---|---|---|
| TI WEBENCH PCB Export (2014) | Power-supply layout to Altium, Allegro, EAGLE, PADS, DesignSpark; **no KiCad export found** | [V/S] |
| Ultra Librarian / TDK | Reference design in 8 CAD formats incl. KiCad | [S] |
| CELUS | Floorplan at handover; a third party lists schematic and BOM only | [S] |
| JITX | Buck constraints -> TPS6293x parametric circuit | [S] |
| atopile | Sub-PCB reuse by address | [P] |
| Flux Modules | Reusable layout sections; "Auto Layout Gravity" 0–1 clustering knob | [V] |

## kicad-happy EMC rule checker

[P] ([emc-precompliance.md](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md)): SW-002/003 switch-node copper area and input-cap loop area; DC-001..003 decap distance (caps within 10 mm considered); ES-001 TVS distance to connector; ML-001 unshielded inductor within 15 mm of sensitive analog. Skew limits: USB HS 25 ps, PCIe 5 ps, Ethernet 50 ps, HDMI 20 ps.

## Vendor numbers

Regulator datasheets are mostly qualitative ("as close as possible"); MCU/SoC hardware design guides are numeric [P].

| Source | Statement |
|---|---|
| TI AN-1149 ([SNVA021C](https://www.ti.com/lit/pdf/snva021c)) | Power traces "an absolute minimum of 15 mils (0.381 mm) per Ampere"; "one standard via per 200 mA"; FB trace far from inductor and noisy traces, possibly opposite side over ground; IC/Cin/Cout/diode grounds together; loops "curl in the same direction" |
| TI SLYT614 ([PDF](https://www.ti.com/lit/pdf/slyt614)) | Input cap "should be the first component placed… after the IC"; SW node small; "one via per amp"; vias outside the Cin–IC path |
| TI SNVA803 ([PDF](https://www.ti.com/lit/pdf/snva803)) | Lateral switching loop ≈20 mm² (>1 nH) vs vertical loop over a layer-2 return ≈2 mm² (flux cancellation) |
| TI regulator datasheets (9: TPS62933, LMR33630, TPS54202, TPS563200, TPS62130, LM5146-Q1, TPS61023, LMR51430, TPS7A20) | Qualitative. Exceptions: TPS62933 ">10-mil" FB trace + separate VOUT sense trace; TPS54202/TPS563200 Kelvin FB ground; TPS7A20 no thermal via directly under the DQN pad |
| Microchip MCU ([docs](https://onlinedocs.microchip.com/oxy/GUID-469A9E6E-3954-4CBA-A0EA-20BD77D40B54-en-US-4/GUID-F15B709B-5112-4669-BAE9-9DBAC5DA209C.html)) | Caps "as close to the pins as possible"; through a via, pin-to-cap trace ≤ ¼ in (6 mm) |
| Espressif ESP32-S3 ([guide](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html)) | 3.3 V trace ≥ 25 mil, VDD3P3 ≥ 20 mil; 10 µF at power entry; crystal ≥ 2.0 mm from clock pin; 50 Ω RF, 0201 matching in a zigzag, 15 mil stub; ≥ 15 mm antenna clearance; SDIO ±50 mil, 50 Ω ±10%, ≲ 2000 mil; touch traces ≤ 300 mm, ≤ 0.18 mm |
| Community skill | Buck/boost loop "tight (< 15 mm² loop area)": a skill author's number, not a vendor's [S] |

Field example: the JLCPCB build fixed an FB trace beside the SW node with a 1.2 mm analog keepout ([JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code)) [P, anecdote].

## Draft recipe table

[I]. Hard = compiled to DRC or physics checks; soft = placer weight; `null` = qualitative only.

| Block (recognizer) | Hard | Soft / defaults |
|---|---|---|
| **Buck** (U with SW/FB(/BOOT) + L on SW) | CIN on the IC layer (integrated converters); width from current (≥ 15 mil/A floor; IPC-2152 better); vias by current (1 per 200 mA conservative vs 1 per A); Kelvin FB where the datasheet says | Cin_HF first, adjacent to VIN/PGND (max weight); loop ≲ 2–20 mm² by stack-up with vertical return over solid L2 GND; minimal SW copper; FB divider at the pin with separate VOUT sense, away from SW/L; Pin Distance check (0–1 cm example); sensitive parts ≥ 15 mm from an unshielded L |
| **Boost** | as buck | Cout_HF is the critical loop cap |
| **LDO** | no thermal via under a DQN pad if the datasheet says so | Cin/Cout adjacent; thermal copper |
| **Decoupling** (cap rail–GND sharing a net with an IC power pin; parent by wire -> voltage-named pin -> split) | none universal | lowest mounting inductance closest (value order only behind the contested-rule selector); ≤ 2–3 mm soft heuristic (PDN-01); vendor distance as an objective scoped to that part only where its guide gives one (Microchip MCUs: ≤ 6 mm pin-to-cap trace through a via); ground via at the cap pad (Espressif) -> [rules/decoupling-pdn](../rules/decoupling-pdn.md) |
| **Crystal** (X/Y with both pins on the same IC) | none universal | near the driver; nothing routed underneath; ground isolation; ≥ 2.0 mm (chip-specific); no magnetics nearby |
| **USB / diff pairs** | Zdiff and skew from the protocol pack; KiCad diff-pair class | ESD at the connector |
| **RF** | 50 Ω (±10% invalid width) | matching at the pin; antenna keepout; 15 mm housing clearance |
| **Power nets** | width for max current, ΔT ≤ 20 °C | pour on request; 200/500 mA defaults need confirmation |

## Open questions

- Via-per-current rules conflict: 1 per 200 mA (AN-1149) vs 1 per A (SLYT614).
- Vendors publish no loop-area targets in mm² beyond SNVA803's worked examples.
- ADI, ST, NXP app notes unreachable; current WEBENCH export formats (KiCad?) unknown.

## Sources
- [netlist_datasheet_understanding.md § 3 (vendor content), § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)
