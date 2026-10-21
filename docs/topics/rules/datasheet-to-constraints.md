# Datasheet layout language → typed constraints, and hard vs soft vs context-switch rules

**TL;DR**
- **Datasheet layout sections mix five kinds of statement:** qualitative proximity, relative priority, pin/point-specific connectivity, explicit numbers, and ordered procedures (plus reference figures and designs). Each maps to a constraint type.
- **Prefer comparative constraints** (rank orders, distance ratios) over invented millimetres. They are more faithful to the source and still checkable.
- **Every rule carries:** a match pattern, typed units, `source_scope`, `statement_strength`, `contested_by` and provenance/precedence. Conflicts are recorded, never silently resolved.
- **Hard:** fab limits and topology facts that all primary sources state the same way. **Soft:** millimetre "closeness" numbers and spacing multipliers. **Context switch:** rules primary experts dispute.
- **VR's meta-finding:** catalog numbers were mostly right, but lost their applicability conditions. Scope fields matter more than the numbers.

## Key facts

**Statement types** (RPA §8) [P examples]:

| Type | Example | Source |
|---|---|---|
| Qualitative proximity | "The LDO input capacitor should be placed as close as possible to the LDOIN and PGND pins" | [Renesas AN-PM-179](https://www.renesas.com/en/document/apn/da9080-pcb-layout-recommendations) |
| Relative priority | "Place inductor close to IC, no need to be as close as input capacitor" | [Rohm](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf) |
| Pin/point connectivity | "connect the VOS pin in the shortest way to VOUT at the output capacitor"; AGND/PGND to EP "mandatory" | [TI TPS62130](https://www.ti.com/lit/ds/symlink/tps62130.pdf) |
| Pin-specific grounding | "shunt capacitor closest to the radio should be grounded via the VSS pin closest to the ANT pin" | [Nordic DevZone](https://devzone.nordicsemi.com/guides/hardware-design-test-and-measuring/b/nrf5x/posts/general-pcb-design-guidelines-for-nrf52-series) |
| Explicit numeric | MPS CIN <2 mm; Microchip crystal ≤12 mm; Espressif crystal ≥2.7 mm; ~1 via per A (SLVA773) | various |
| Ordered procedure | SLYT614's five steps; BQ25895 "according to this specific order is essential" | [SLYT614](https://www.ti.com/lit/an/slyt614/slyt614.pdf); [BQ25895](https://www.ti.com/lit/ds/symlink/bq25895.pdf) |
| Reference design deference | Nordic: use the reference design, because matching differs QFN vs WLCSP | Nordic |

**Translation table** [I] (defaults are heuristics to calibrate):

| Phrase pattern | Constraint type | Default quantification | Notes |
|---|---|---|---|
| "C as close as possible to pin(s)" (power stage) | `proximity(part, pins, max_gap)` + `same_layer` + `max_vias=0` + priority 1 | 0.5 mm (0402/0603), 1.0 mm (0805+); primary MPS ≤2 mm | Also emit `loop_area` for scoring |
| "close to IC" / "near" (secondary) | lower-priority `proximity` | 3–5 mm | Rohm: inductor less tight than CIN |
| "Connect X to Y at Z" | `connect_at(net, pad)` + `separate_from(net, power_net)` | Sense leaves from the Z pad; no shared copper before Z | TPS62130 VOS |
| "Shortest path" / "short and wide" | `max_length` + `min_width` | ≤5 mm; width from IPC | — |
| "Keep away from SW / inductor / noisy" | `keepout(class, aggressor, d, layers=all)` | 1–2 mm; no overlap with the aggressor courtyard | — |
| "Do not route under X" | Rule area on the X courtyard, disallowing tracks/vias | — | KiCad rule areas |
| "Ground via near pad" / "via fence" | `via_near(pad, GND, d)` / `via_fence(net, pitch, offset)` | 0.5 mm / λ_g/20 | u-blox 2 mm NOT FOUND |
| "Mandatory" / "must" | Hard (S1) | — | "should" / "recommended" → S2–S3 |
| Numeric keep-out / clearance | DRC rule as written | Store units, layer, condition | — |
| Layout example figure | `relative_placement_template` | Vision extraction, normalised to pin-1 orientation | Initial placement seed |
| Ordered steps | `placement_priority` | — | Place and route in that order |

**Comparative constraints** (VR §3) [I]:
- Examples: "Place the protected IC much further from the TVS than the TVS is to the connector" becomes a distance ratio. "Inductor close, but not as close as CIN" becomes a rank order.
- These are more faithful than blog millimetres and machine-checkable.

**Rule record fields** (VR) [I]:
- `applies_if` and `source_scope` (device family / data rate / power level / enclosure vs PCB);
- `statement_strength` (mandatory / must / should / as close as possible / good guideline);
- `contested_by` (rule IDs + sources).

**Rule-pack contract, precedence (10 fab < 20 interface < 30 vendor family < 40 device datasheet), resolution policy ("stricter" + info finding; [S] never overrides [P]; [I] stays a warning until calibrated) and mandatory vendor profiles** (values differ 5–25×) are specified once in [rule-pack-format.md](rule-pack-format.md). Worked packs: [power/buck.md](power/buck.md) (`buck_sync`) and [crystals-clocks.md](crystals-clocks.md).

**Hard vs soft classification** (VR §3, power/RF/analog/DFM scope; cross-domain tiers in [rule-pack-format.md](rule-pack-format.md), myth handling in [myths-and-contested.md](myths-and-contested.md)):

| Class | Rules | Encoding |
|---|---|---|
| **Hard: DRC** | DFM-01 fab absolute limits (router at recommended); DFM-02 courtyards; DFM-10 IPC-2221B floor (raised by the safety standard); DFM-11 JLC silk ≥1.0 / 0.15 mm | Board setup + `.kicad_dru` |
| **Hard: topology** | No split/void crossing; single bridge if split; PWR-01 topology (CIN on the IC layer, 0 hot-loop vias); PWR-06 FB/VOS from the COUT pad; PWR-07 single AGND–PGND tie where "mandatory"; RF-03 shunt via the named VSS pin; RF-05 PCB keep-out polygon from the module datasheet; RF-07 no digital under RF; AMS-02. Cross-domain: connector→TVS→IC with no stub or via; 0 test points on SerDes | Geometric checker; reject |
| **Hard within scope** | Vendor numbers tied to a family, interface or data rate | Activate only when the scope matches |
| **Soft, strong** | PWR-02 next-layer GND ≤0.13 mm; PWR-10 ≥1 via/A; PWR-12 C_boot ≥10·C_g, C_VDD ≥10·C_boot; PDN-06 bead ≤20% rated; PWR-15 EP vias 0.3 mm at 1.0–1.2 mm | High-weight cost terms; warnings quoting the source |
| **Soft, weak** | CIN ≤0.5–1 mm (primary MPS 2 mm); crystal ≤5 mm; FB divider ≤2–3 mm; RF↔SMPS 20 mm; λ/20 or 3–5 mm stitching; 2W/3W/5W (express in h, compute crosstalk); 2 cm²/W; thermal spacing; V-score MLCC 3–5 mm | Rank objectives; never DRC errors |
| **Context switch** (not emitted by default) | Copper under the inductor (Rohm vs TI); PWR-08 CIN/COUT ground (Rohm vs MPS/TI); thermal-via tenting (SLOA122 vs SLUA271/TB389); "smallest cap closest" (MT-101 vs Bogatin/Archambeault); perimeter stitching (Ott vs Hubing); PMIC ground cuts (DA9080); 20-H (Montrose "fact, not fiction" for high-density multilayer vs Shim/Hubing measurements; LearnEMC "debunked"); crystal can/VSSOSC grounding | Both variants + a selector (power level, layer count, fab process, datasheet mandate); ask; log the choice |
| **Scoped myth exceptions** | 90° corners harmless below multi-GHz, but ≤45° or curved on ESD paths (SLVA680A: arcing below ~2.6 mm radius at 8 kV) and arcs/135° on RF | Corner rule only on `ESD_UNPROTECTED` and `RF50` |

**Severity recalibrations** (VR):
- Remove PWR-08 as a default.
- Split RF-05 into a hard PCB polygon plus an enclosure clearance on the mechanical checklist.
- Keep AMS-02 at S1, with the escape only for scheme-specified multi-converter parts.
- Datasheet "mandatory" maps to hard.

**Why vendors disagree:** they optimise different objectives. Rohm targets conducted HF noise and inductor Q; TI and MPS target loop area and shielding. Store both, with the condition that selects between them.

**Anti-folklore.**
- Hubing: boards laid out "by people trying to adhere to a long list of EMC guidelines are worse than boards laid out by people with no EMC guidance at all"; "Blindly adhering" heads his error list ([slides](https://r6.ieee.org/scv-emcs/wp-content/uploads/sites/111/022019ToddHubing.pdf)) [P].
- LearnEMC calls even its own good guidelines "not necessarily the best advice in every situation".

## Recommendations for our system
- **Parse datasheet "Layout Guidelines" and "Layout Example" sections** into typed constraints with strength and scope. Extract figures as relative templates. Datasheet constraints override generic defaults.
- **The LLM's value-add** is turning relative language into comparative constraints and explaining *why* a rule is hard or soft. Disagreements are surfaced, not hidden.
- **Keep provenance on every constraint** (URL + tag). Authority order: [P] > [S] > [V] > [I].
- **Build a taxonomy and test corpus of datasheet layout language.** None exists in the literature; this is novel work.

## Conflicts and open questions
- **No published taxonomy of datasheet layout language exists;** the table above is a synthesis.
- **KiCad DRU syntax** (`insideArea`, `within_diff_pairs`, ...) must be verified on the installed KiCad.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 8, § 20](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1 Inferences, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [interface_rule_packs.md § 11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)

See also: [rule-pack-format.md](rule-pack-format.md), [myths-and-contested.md](myths-and-contested.md), [checkers-power.md](checkers-power.md), [power/buck.md](power/buck.md), [placement-methodology.md](placement-methodology.md), [crystals-clocks.md](crystals-clocks.md)
