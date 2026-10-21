# Rule-pack format, rule strength tiers and knowledge-base schema

*Tags: [P] primary, [S] snippet, [I] inference. VR = verification_rules.md.*

**TL;DR**
- **Every rule must carry five things:**
  1. a match pattern that binds it to schematic objects;
  2. typed, unit-carrying parameters, including formulas in UI, W, h or fractions of t_r;
  3. provenance and precedence, with conflicts **recorded rather than silently resolved**;
  4. a check backend: `kicad_dru`, `geometric`, `simulation` or `bom`;
  5. a placement intent, kept separate from the routing constraints.
- **Vendor profiles are mandatory.** Primary values for the same interface differ 5–25×. When the vendor is unknown, use the tightest [P] value and add an `info` finding that names the looser alternatives.
- **Precedence and resolution:**
  - Precedence order: fab 10 < interface default 20 < vendor family 30 < device datasheet 40.
  - A snippet-sourced [S] value never overrides a primary [P] value at equal precedence.
  - Our heuristics [I] default to `warning` until calibrated against vendor evaluation-board layouts.
  - Fab packs set only `min`; interface packs set `opt` and `max`, and may never relax a fab minimum.
- **Rule strength tiers** ([VR] §3):
  - hard fab limits;
  - hard topology;
  - hard within a declared scope;
  - soft-strong;
  - soft-weak (heuristic);
  - context switch;
  - exceptions to myths.
  
  Millimetre values that come only from blogs become rank or comparative objectives, never DRC errors.
- **Required fields:** `source_scope`, `statement_strength` and `contested_by`. Then the LLM can explain *why* a constraint is hard or soft and surface any disagreement.

## Key facts

### Pack schema v0 ([IF] §11 proposal)
```yaml
pack:
  id: <interface-or-circuit id>        # usb2_hs, buck_sync, xtal_pierce
  version: 0.1
  precedence: 30                        # 10 fab < 20 interface < 30 vendor family < 40 datasheet
  vendor_profile: <ti|microchip|qualcomm|...|unknown>
  applies_when:
    parts: [ {role: <name>, match: {lib_regex, pin_functions, value_regex, class, nets}, optional} ]
    nets:  [ {role: <name>, match: {pin: "<role>.<pin_function>"}} ]
  parameters:
    <name>: {value: <number|formula>, unit: mm|mil|ps|ohm|nF|pF|dB|pct|UI|W|H, tol_pct,
             tag: P|S|D, source: <url>, rev: <doc rev>, by_vendor: {<vendor>: <value>}}
  conflicts:
    - {parameter, values: [{value, source}], resolution: stricter|vendor_profile|window|ask}
  placement:   # anchor|adjacent|order_along_path|distance_window|same_side|keepout_ring|orientation|max_loop_area|priority_order
  routing: {netclasses: [...], diff_pairs: [...]}
  checks:
    - {id, backend: kicad_dru|geometric|simulation|bom, severity: error|warning|info, emit: <template|function>}
  overrides: {datasheet_reference_layout: {precedence: 40}}
```

**Resolution policy:**
1. Use the highest precedence.
2. Then use `by_vendor[vendor_profile]`.
3. Then apply the declared `resolution`. The default is "stricter", and it raises an `info` finding citing both sources.
4. [S] never overrides [P] at equal precedence.
5. [D]/[I] values are warnings until calibrated.

### Worked examples (full YAML in [IF] §11)
- **usb2_hs.** See [interfaces/usb2.md](interfaces/usb2.md).
  - Roles and parameters:
    - roles conn, phy, esd, cmc;
    - zdiff 90 ±15% with by_vendor {qualcomm 75–105, microchip 90 +5/−10};
    - intra-skew 1.27 mm {qualcomm 2.0, ti_usb_controllers 3.81};
    - length warn 150 mm, max 250 mm {ti 304.8};
    - ≤4 vias;
    - gaps 0.762 mm (others) and 1.27 mm (clocks);
    - GND overhang 5× pair gap;
    - esd_conn_max 5 mm [I].
  - Shield-termination conflict: resolution `ask`.
  - Placement: anchor the connector on the board edge, then order conn → esd → cmc → phy.
  - Checks:
    - DRU: `skew … within_diff_pairs`, `via_count (max 4)`, `length` with `fromTo`, USB2-vs-others clearance;
    - geometric: no T-junctions or test points; GND covers the offset polygon; ESD path order with a GND via ≤1 mm;
    - BOM: no series caps.
- **buck_sync.** Owned by the power cluster: [power/buck.md](power/buck.md).
  - Parameters: Cin ≤2 mm (MPS); bulk ≤20 mm (Rohm); loop area 2/10/20 mm²; 5 A/ns; L1–L2 ≤0.127 mm; 1 via/A; 1 mm/A; SW ≤2.54 mm; FB ≤3 mm [I].
  - Datasheet reference-layout override at precedence 40.
- **xtal_pierce.** See [crystals-clocks.md](crystals-clocks.md).
  - Placement: annulus from a vendor-specific minimum distance to 12 mm.
  - Parameters: parasitic limits; hs_keepout 3 mm [I]; metal-can vendor switch.
  - DRU: disallow foreign tracks and vias in `XTAL_KEEPOUT`.
- The DRU token forms (`within_diff_pairs`, `insideArea`, `track_angle`) must be tested on the installed KiCad.

### Rule strength tiers ([VR] §3)
| Tier | Examples | Encoding |
|---|---|---|
| Hard: fab/assembly | Fab absolute minimums (router targets the recommended values); courtyard non-overlap; IPC-2221B floor; JLC silk 1.0 mm / 0.15 mm | Board setup + `.kicad_dru` ([dfm-fab-limits.md](dfm-fab-limits.md)) |
| Hard: topology (all primary sources agree) | No split or void crossing; ≥1.5W from voids (except voided SMD pads); crossings over the bridge; connector → TVS → IC with no stub, no via before the TVS, GND via at its pad; 0 TPs/stubs on SerDes; plus power/RF topology (CIN on the IC layer, 0 hot-loop vias, FB from the COUT pad, "mandatory" AGND–PGND tie, shunt cap via the named VSS pin, antenna keep-out polygon, no digital under RF, AGND+DGND to the analog plane) | G-checker → reject the placement or route |
| Hard within declared scope | Pair skew, via count, 30/50 mil keep-outs, via stub min(15 mil, 0.3/Gbps) | Only when the interface pack and data rate are known; carries `source_scope` |
| Soft, strong | Return via ≤200 mil as a hard max, with "closer is better" as the objective; ≥90 mil from the plane edge / ≥2h from the board edge; connectors on one edge; I/O ≤2 cm, non-I/O ≥2 cm; plus power items (L2 ≤0.13 mm, 1 via/A, C_boot ≥10·Cg, bead ≤20% of rated I, EP vias 0.3 mm at 1.0–1.2 mm) | High-weight cost terms; warnings that quote the source |
| Soft, weak (heuristic) | TVS ≤5–10 mm; CMC ≤5 mm; crystal ≤5 mm; CIN ≤0.5–1 mm (MPS primary ≤2 mm); FB ≤2–3 mm; RF↔SMPS 20 mm; stitching λ/20, 3–5 mm or 2 mm near SerDes; **2W/3W/5W multipliers (compute crosstalk in h instead)**; 2 cm²/W | Rank-based objectives ("closer than any other part"); never DRC |
| Context switch | See [myths-and-contested.md](myths-and-contested.md) | Store both variants plus a selector; ask; log |
| Myth exceptions | 90° corners only on ESD and RF nets | Net-class scoped |

**Severity recalibrations ([VR]):**
- TL-5 (test points on SerDes) becomes hard.
- EMI-7: the millimetre distance becomes soft; the topology stays P0.
- EMI-6: the 10–15 mm stitch pitch is soft; the P0 is "no crossing without a bridge or stitch".
- RF-05 splits into a hard PCB keep-out plus an enclosure clearance for the mechanical checklist (15 mm for ESP32).

### Vendor spread (why vendor profiles are mandatory)
| Quantity | Tightest | Loosest | Ratio |
|---|---|---|---|
| USB3 intra-pair | 2 mil (TUSB1046) | 0.7 mm (Qualcomm) | ~14× |
| USB2 intra-pair | 2 mil (SPRAAR7A 2013) | 150 mil (TUSB9261) | 75× (historic) |
| DDR4 DQ↔DQS | 2 ps (TI) | 25 ps (PolarFire) | 12.5× |
| DDR4 ADDR↔CK | 4 ps (TI) | 100 ps (PolarFire) | 25× |
| Ethernet PHY↔magnetics | <1 in (Microchip) | ≥25 mm (Pulse) | opposite directions |
| PCIe AC cap | 75–220 nF (TI) | 176–265 nF (Qualcomm) | 220 nF fits both |

### Knowledge-base record ([HS] §12 + [VR])
- `rule_id, family, statement`
- `numeric{value, unit, basis: mm|ps|W|h|λ|fraction_of_tr}`
- `physics_why`
- `applies_if{interface, t_r<, data_rate>, layer_type, enclosure, emission_class}`
- `severity, check_type{K, K11, G, S}, kicad_dru_template, checker_fn`
- `source_url, source_author, source_type{physics, rule-of-thumb, vendor-req, spec-req, measured, satirical-inverse, myth}, provenance{P, S, …}, confidence`
- `conflicts_with[], source_scope, statement_strength{mandatory, must, should, as close as possible, good guideline}, contested_by[]`
- Negative (myth) rules are included.
- Precedence: spec and vendor requirements override rules of thumb, and physics drives the checkers.

## Recommendations for our system
- **Express budgets as physics, not lengths.** Store:
  - dB budgets and per-material dB/in tables;
  - per-via penalties (≈2 in, TI SLLU149E; ≈1 in, Heck);
  - per-component penalties (ESD+CMC ≈1 in);
  - UI formulas and the cable insertion-loss input.
  
  Compute L_max per stackup.
- **Delay packs** (DDR, HDMI, D-PHY, RGMII, SD) emit ps rules directly. Use TI's "<20% of limit" as `opt` and the full limit as `max`.
- **Placement intents** come from packs:
  - chain order;
  - distance windows and annuli;
  - end-node termination;
  - "AC cap within N mm of either endpoint".
- **Let the LLM turn relative source wording into comparative constraints**, e.g. "protected IC much further from the TVS than the TVS is to the connector" becomes a distance ratio. This is more faithful than inventing millimetre values.
- **Keep packs as data**, so they can be calibrated against vendor evaluation boards.

## Conflicts and open questions
- The schema is a proposal. The geometric backends exist only as function names.
- `statement_strength` has to be read from the source wording by hand (or by the LLM). No source supplies it as structured data.

## Sources
- Research notes:
  - [interface_rule_packs.md § 11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
  - [rules_highspeed_emi.md § 10, 12](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
  - [verification_rules.md § 1 Inferences, 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also:
- [myths-and-contested.md](myths-and-contested.md)
- [checkers-si-emi.md](checkers-si-emi.md)
- [interfaces/usb2.md](interfaces/usb2.md)
- [../architecture/constraint-ir.md](../architecture/constraint-ir.md)
