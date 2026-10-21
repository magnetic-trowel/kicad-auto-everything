# RF layout: CPWG, matching, via fences, antenna keep-outs, module integration

**TL;DR**
- **RF geometry is fixed by the module or RF-IC datasheet and reference design.** That means a 50 Ω CPWG/microstrip over continuous ground, the matching network at the pin, and an antenna keep-out polygon from the module figure. Store this data **per part**.
- **Hard rules:** shunt match parts grounded through the *named* pin (Nordic VSS pin 31); only GND under RF traces on every layer; the PCB antenna keep-out polygon.
- **Corrected:** Espressif's 15 mm is **enclosure** clearance, not a PCB keep-out. The u-blox "≤0.5 mm / ≤2 mm" via-fence numbers were **NOT FOUND**. The RF↔SMPS "20 mm" has no primary source.
- **Use λ_g/20 at the highest harmonic** as a soft fence and stitching objective.
- **90° corners matter only at multi-GHz.** On RF nets use arcs or 135°.

## Key facts

**u-blox** ([NORA-B2 SIM](https://content.u-blox.com/sites/default/files/documents/NORA-B2-u-connectXpress_SIM_UBXDOC-465451970-3906.pdf); [MAX-M5Q HIM](https://content.u-blox.com/sites/default/files/MAX-M5Q_HardwareIntegrationManual_(UBX-13002460).pdf); [LEA-6 HIM](https://content.u-blox.com/sites/default/files/products/documents/LEA-NEO-MAX-6_HIM_(UBX-14054794)_1.pdf)) [P]:
- **Geometry:**
  - 50 Ω; coplanar microstrip most common; trace width ≥200 µm; trace-to-ground clearance ≥2× the trace width.
  - Route in arcs (preferred) or 45°.
  - If the same-layer GND gap ≤5× the track width, use the coplanar-waveguide model.
  - 50 Ω FR-4 microstrip width ≈ 2× the dielectric thickness.
  - In general routing, >3W from the ground-plane edge.
- **Module area:**
  - U.FL active pad: GND keep-out on at least the first inner layer.
  - Do not route RF under the receiver/module: ground there is only ~100 µm away, with tolerances up to 100%. "Ground cuts or separation are not allowed under the module."
  - "No digital routing is allowed in the GND reference plane area of RF traces … beneath all layers."
  - MAX-M5Q: cover the area under the receiver "entirely with solder mask. Vias should not be open."
- **Ground plane and enclosure:**
  - Ground ≥10 mm beyond the module on three non-edge sides: **NORA-B2x6 embedded-antenna variant only** (VR +CTX).
  - Ground plane ≥24 × 30 mm, but over 50 × 50 mm not recommended (embedded antenna).
  - Metal parts ≥10 mm from the antenna. Casing clearance ≥10 mm vs "minimum clearance of 5 mm" (internally inconsistent).
- **Routing:**
  - "As a first priority, minimize the length of the RF traces. Then, minimize bus length."
  - "All traces, including low speed or DC traces, must couple with a reference plane."
  - Route power through the bypass and bulk caps before the module pin.
  - Stitched ground ring at the PCB edge, power planes kept back from the edge.
  - "Add GND stitching vias around transmission lines" (no pitch number, VR).

**Nordic nRF52832** (PS v1.0, [mirror](https://cdn.sparkfun.com/datasheets/Wireless/Bluetooth/nRF52832_PS_v1.0.pdf)) [P]:
- The radio output is not 50 Ω, so a matching network is required; it also filters the 2nd/3rd harmonics.
- "C3 … is not directly connected to the ground plane, but grounded via VSS pin 31 … to create additional filtering of harmonic components."
- Keep-out on the inner layers directly below the matching circuit. ≥1 via per VSS pin.
- ≥2-layer PCB with a ground plane; with a topside RF ground, VSS connects directly to it.
- The chip supply is filtered and routed separately from digital supplies. Fast digital stays away from the crystal and supply lines.
- The reference layout has no bottom-side components.
- DevZone [S]: continuous ground under the centre pad and RF path; no plane under the antenna; use the reference design, because matching differs between QFN and WLCSP. The "4×4 via grid" was NOT RETRIEVABLE.

**Espressif ESP32** ([PCB layout guide](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html)) [P]:
- **Antenna placement:**
  - "At least 15 mm" clearance **inside the housing** (VR +CTX). The PCB keep-out is the module's "Keepout Zone" figure.
  - Antenna outside the board or feed at the edge; cut the board on both sides of and below the antenna; never mid-board with four-side cut-outs.
  - Keep the antenna away from crystals, DDR, HF clocks, USB and UART. Test throughput and range on the final product.
- **Stack and power:**
  - 4-layer: L1 signals and parts; L2 complete GND, no signals; L3 power + few signals, GND under RF and crystal; L4 few signals, no parts.
  - Power traces: main ≥25 mil; VDD3P3 ≥20 mil; others 12–15 mil. ≥2 vias when main power changes layer.
  - Chip ground pad ≥9 vias.
- **RF path:**
  - CLC match in 0201 "close to the pin in a zigzag".
  - 2nd-harmonic stub on the shunt-cap ground pad: 15 mil, 100 Ω ±10% (not needed for 0402 and up).
  - RF trace on the outer layer, no vias, constant width, no branches; 135° or arcs. Keep all layers clear under the IPEX connector. On 2-layer boards the RF trace is normally >20 mil.
- **Other numbers:**
  - SDIO ±50 mil to CLK, 50 Ω ±10%, ideally ≤2000 mil.
  - Touch traces ≤300 mm, width ≤0.18 mm, 0.5–1 mm gap to ground, electrodes 8–15 mm.
  - Supply ripple <80 mV (MCS7 at 11n) and <120 mV (11 MHz at 11b).

**Separation and shielding** (vendor knowledge base) [V]:
- ~20 mm SMPS↔RF start; LNA input far from SMPS (harmonic spurs).
- Shield-can footprint: continuous 0.5–1.0 mm ground ring with vias ≤1.0 mm pitch.
- Fence ≥3× substrate height from the trace edge; double staggered rows for TX/RX isolation; 30–70 dB shielding (rough) ([RF Essentials](https://rfessentials.com/rf-knowledge-base/how-do-i-design-a-shielded-compartment-on-a-pcb-to-isolate-sensitive-rf-stages/); [AtlasPCB](https://www.atlaspcb.com/blog/emc-shielding-pcb-via-fence-ground-plane/)).
- Primary sources are qualitative: route RF "far from any noise source, such as switching supplies" (u-blox).

**Via fences and stitching.**
- Pitch < λ_g/20 at f_max, so the fence looks solid; single-via self-resonance is a few hundred MHz to a few GHz ([Wikipedia](https://en.wikipedia.org/wiki/Via_fence)) [S].
- At 77 GHz, λ/20 ≈ 0.1 mm, which needs microvias ([AtlasPCB](https://www.atlaspcb.com/blog/gcpw-coplanar-waveguide-pcb-design-rf-mmwave/)) [V].
- Worked values [I] (εr 4.3, conservative for microstrip):

  | f | λ_g | λ_g/20 | λ_g/10 |
  |---|---|---|---|
  | 1 GHz | ~145 mm | ~7.2 mm | ~14 mm |
  | 2.4 GHz | ~60 mm | ~3.0 mm | ~6 mm |
  | 5.8 GHz | ~25 mm | ~1.25 mm | ~2.5 mm |

**Bends.**
- The myth traces to one figure in the 1971 MECL handbook. A 5-mil corner (8.5 fF) has no noticeable effect until well over 70 GHz (Bogatin data via [Altium](https://resources.altium.com/p/slaying-900-right-angle-bend-dragon)) [S].
- Johnson: fine to 2 Gbps, starting to matter at 10 Gbps [P].
- Mitering gave 20 dB at 77 GHz (simulation, [GaTech](https://tentzeris.ece.gatech.edu/ECTC09_Rida.pdf)) and may be worthwhile from ~5.8 GHz [S].
- The "50–60% optimal miter" is NOT FOUND. Johnson/Edwards: rounding removes 21% of the corner copper; neutralising needs 70–90% removed ([Johnson](https://www.sigcon.com/Pubs/edn/bigbadbend.htm)) [P].
- Acute angles are an acid-trap fab concern.

**Rules** (RPA §3 with VR status):

| ID | Rule | Numeric | Class |
|---|---|---|---|
| RF-01 | Z0 geometry from a field solver; continuous reference under the full line | u-blox ≥200 µm | Hard (S1) |
| RF-02 | Point-to-point; no stubs, test pads or T-branches except designed matching | stub ≪ λ/10 [I] | Hard (S1) |
| RF-03 | Match at the pin; shunt grounded at the named pin | first element ≤~1 mm [I] | Topology hard; distance soft |
| RF-04 | Via fence along CPWG and around the RF section | ≤ λ_g/20 (u-blox 2 mm NOT FOUND) | Soft |
| RF-05 | Antenna keep-out, all layers | Module polygon | **Split:** hard PCB polygon + enclosure clearance to the mechanical checklist |
| RF-06 | Separate from SMPS, clocks, HS digital; fence or shield if dense | ~20 mm [V] | Soft, ranked |
| RF-07 | Only GND under RF lines and match, every layer | — | Hard |
| RF-08 | Arcs/135° above a few GHz; acute angles banned | — | S4 below 1 GHz, S3 above 5 GHz |
| RF-09 | Pour stitching | ≤ λ/20 (λ/10 looser) | Soft |

## Recommendations for our system
- **Per-part RF records:** keep-out polygons (vision extraction from datasheet figures, human-reviewed), stacks, stub specs, power widths and supply-ripple limits. Never generalise across modules.
- **Antenna keep-out:** an all-layer KiCad rule area disallowing tracks, vias and zones. Enclosure clearance goes in a separate mechanical report.
- **Net class `RF50`:** width/gap from the stack-up solver; point-to-point topology check; arc corners; fence-gap scoring along the centreline; reference-plane integrity raster.
- **RF↔SMPS separation** is a ranked objective. Prefer fences or cans on dense boards.

## Conflicts and open questions
- **Perimeter stitching:** Hubing says perimeter-only stitching can create a resonant cavity and to distribute vias instead; Ott stitches the two grounds of a G/S/S/G board around the periphery. Context switch.
- **Not extracted:** Nordic/u-blox keep-out dimensions from figures (needed per module); a primary optimal-miter value.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 3, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B, § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [crystals-clocks.md](crystals-clocks.md), [datasheet-to-constraints.md](datasheet-to-constraints.md), [checkers-power.md](checkers-power.md)
