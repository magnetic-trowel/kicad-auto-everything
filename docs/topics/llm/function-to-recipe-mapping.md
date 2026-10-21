# Mapping recognized functions to layout recipes (constraints plus checks)

**TL;DR**
- **Recipes should be data:** a recognizer pattern, a constraint set, and a **check set**. Quilter's model, where every constraint has its own Physics Rule Checks, lets **one predicate drive both the placer objective and the acceptance test** [V].
- **Vendor numeric thresholds are scarce for regulators.** TI datasheets mostly say "as close as possible". App notes give a few numbers, and some **conflict**: 1 via per 200 mA (AN-1149) vs 1 via per ampere (SLYT614) [P].
- **MCU and SoC hardware design guides are numeric:** Microchip ≤ 6 mm decap trace through a via; Espressif crystal ≥ 2.0 mm from the clock pin [P].
- When a block matches exactly, prefer replaying a known-good sub-layout (KiCad 10 design blocks, atopile sub-PCBs, vendor exports); otherwise generate from constraints [I].
- The detailed rule packs live in the rules area. This doc covers the recipe mechanism and the numbers in our notes [I].

## Key facts

### Physics-constraint engine: Quilter [V] ([PRC overview](https://docs.quilter.ai/physics-rule-checks-prcs/overview); [Pin Distance](https://docs.quilter.ai/physics-rule-checks-prcs/pin-distance))

| Constraint | Physics Rule Checks |
|---|---|
| Bypass, crystal, switching converter | Pin Distance, Trace Path Length, Layer Switch Count, Ground Plane Overlap |
| Differential pairs | Ground Plane Overlap, Uncoupled Spacing, Length Mismatch |
| Power nets | Overheated Length |
| Single-ended impedance | Invalid Width Span, Ground Plane Overlap |

- **Pin Distance** = the distance between the closest pin edges. The example passes at "0.13 cm within acceptable range (0 cm to 1 cm)" and fails at 1.11 cm.
- **Constraint behaviour:**
  - converters: "tight ground return loops", with the three passives "as closely as possible";
  - bypass: "smaller capacitance values closer to power pins";
  - crystal: "near their drivers".
- Quilter frames its approach as "constraints at the physics level, not the rules level".

### Generators and modules
- **TI WEBENCH PCB Export (2014):** power-supply layout exported to Altium, Allegro, EAGLE, PADS and DesignSpark. **No KiCad export found** [V/S].
- **Ultra Librarian / TDK:** a reference design in 8 CAD formats including KiCad [S].
- **CELUS:** a floorplan at handover; a third party lists it as schematic and BOM only [S].
- **JITX:** buck constraints → TPS6293x parametric circuit [S].
- **atopile:** sub-PCB reuse by address [P].
- **Flux Modules:** reusable layout sections; "Auto Layout Gravity" 0–1 clustering knob [V].

### Rule checker: kicad-happy EMC [P] ([emc-precompliance.md](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md))
- SW-002/003: switch-node copper area and input-cap loop area.
- DC-001..003: decap distance (caps within 10 mm considered).
- ES-001: TVS distance to connector.
- ML-001: unshielded inductor within 15 mm of sensitive analog.
- Skew limits: USB HS 25 ps, PCIe 5 ps, Ethernet 50 ps, HDMI 20 ps.

### Vendor numbers [P]

| Source | Statement |
|---|---|
| TI AN-1149 ([SNVA021C](https://www.ti.com/lit/pdf/snva021c)) | Power traces "an absolute minimum of 15 mils (0.381 mm) per Ampere"; "one standard via per 200 mA"; FB trace far from the inductor and noisy traces, possibly on the opposite side over ground; IC/Cin/Cout/diode grounds together; loops "curl in the same direction" |
| TI SLYT614 ([PDF](https://www.ti.com/lit/pdf/slyt614)) | Input cap "should be the first component placed… after the IC"; SW node small; "one via per amp"; vias outside the Cin–IC path |
| TI SNVA803 ([PDF](https://www.ti.com/lit/pdf/snva803)) | Lateral switching loop about 20 mm² (>1 nH) vs a vertical loop over a layer-2 return of about 2 mm² (flux cancellation) |
| TI regulator datasheets (9 checked: TPS62933, LMR33630, TPS54202, TPS563200, TPS62130, LM5146-Q1, TPS61023, LMR51430, TPS7A20) | Qualitative. Exceptions: TPS62933 ">10-mil" FB trace and a separate VOUT sense trace; TPS54202/TPS563200 Kelvin FB ground; TPS7A20 no thermal via directly under the DQN pad |
| Microchip MCU ([docs](https://onlinedocs.microchip.com/oxy/GUID-469A9E6E-3954-4CBA-A0EA-20BD77D40B54-en-US-4/GUID-F15B709B-5112-4669-BAE9-9DBAC5DA209C.html)) | Caps "as close to the pins as possible"; through a via, pin-to-cap trace ≤ ¼ in (6 mm) |
| Espressif ESP32-S3 ([guide](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html)) | 3.3 V trace ≥ 25 mil, VDD3P3 ≥ 20 mil; 10 µF at power entry; crystal ≥ 2.0 mm from the clock pin; 50 Ω RF, 0201 matching in a zigzag, 15 mil stub; ≥ 15 mm antenna clearance; SDIO ±50 mil, 50 Ω ±10%, ≲ 2000 mil; touch traces ≤ 300 mm, ≤ 0.18 mm |
| Community skill | Buck/boost loop "tight (< 15 mm² loop area)": a skill author's number, not a vendor's [S] |

Field example: the JLCPCB build fixed an FB trace beside the SW node with a 1.2 mm analog keepout ([JLCPCB](https://jlcpcb.com/blog/kicad-mcp-how-to-design-a-pcb-with-claude-code)) [P, anecdote].

### Draft recipe table [I]

"Hard" = compiled to DRC or physics checks; "soft" = placer weight. `null` means qualitative only.

| Block (recognizer) | Hard | Soft / defaults |
|---|---|---|
| **Buck** (U with SW/FB(/BOOT) + L on SW) | width from current (≥ 15 mil/A floor; IPC-2152 better); vias by current (1 per 200 mA conservative vs 1 per A); Kelvin FB where the datasheet says | Cin_HF first, same layer, adjacent to VIN/PGND (max weight); loop ≲ 2–20 mm² by stack-up with a vertical return over solid L2 GND; minimal SW copper; FB divider at the pin with separate VOUT sense, away from SW/L; Pin Distance check (0–1 cm example); sensitive parts ≥ 15 mm from an unshielded L |
| **Boost** | as buck | Cout_HF is the critical loop cap |
| **LDO** | no thermal via under a DQN pad if the datasheet says so | Cin/Cout adjacent; thermal copper |
| **Decoupling** (cap rail–GND sharing a net with an IC power pin; parent by wire → voltage-named pin → split) | ≤ 6 mm trace through a via (Microchip) | smallest cap closest; ground via at the cap pad (Espressif) |
| **Crystal** (X/Y with both pins on the same IC) | none universal | near the driver; nothing routed underneath; ground isolation; ≥ 2.0 mm (chip-specific); no magnetics nearby |
| **USB / diff pairs** | Zdiff and skew from the protocol pack; KiCad diff-pair class | ESD at the connector |
| **RF** | 50 Ω (±10% invalid width) | matching at the pin; antenna keepout; 15 mm housing clearance |
| **Power nets** | width for max current, ΔT ≤ 20 °C | pour on request; 200/500 mA defaults need confirmation |

## Recommendations for our system

1. Recipes are **data files** (CC0 rule-pack licence): a recognizer (pin roles plus refdes, as in Quilter's rules), constraints with strength, checks with thresholds, and citations [I].
2. The **same predicate** feeds the placer objective (soft weight) and the post-route check (hard or soft threshold).
3. **Conflicting vendor numbers:** use the conservative value, attach both citations, and surface the discrepancy to the user.
4. **Qualitative strength:** "as close as possible" becomes `weight=high, bound=null`; corpus percentiles supply soft targets (see [../data/measured-priors.md](../data/measured-priors.md)).
5. **Exact-match replay first:** KiCad 10 design blocks, atopile sub-PCBs, vendor EVM exports. Otherwise generate from constraints.
6. **Datasheet layout statements** map to the same closed vocabulary as the LLM relation API, e.g. `near(C_in, U1.VIN, tight)`, `min_loop({U1.SW, L1, C_out})`, `kelvin(R_sense)` (see [interfaces-relations-vs-coordinates.md](interfaces-relations-vs-coordinates.md)).

## Conflicts and open questions

- Via-per-current rules conflict (200 mA vs 1 A per via).
- Vendors publish no loop-area *targets* in mm² beyond SNVA803's worked examples.
- ADI, ST and NXP app notes were unreachable. The current WEBENCH export formats (KiCad?) are unknown.

## Sources
- research notes: [netlist_datasheet_understanding.md § 3 (vendor content), § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)

See also: [../rules/decoupling-pdn.md](../rules/decoupling-pdn.md), [../rules/datasheet-to-constraints.md](../rules/datasheet-to-constraints.md), [design-understanding-pipeline.md](design-understanding-pipeline.md), [datasheet-extraction.md](datasheet-extraction.md)
