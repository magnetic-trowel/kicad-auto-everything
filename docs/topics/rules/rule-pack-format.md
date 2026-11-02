# Rule-pack format, rule strength tiers and knowledge-base schema

Scope: canonical pack schema, precedence and resolution policy, fab/safety floors, rule strength tiers (cross-domain), vendor spread, knowledge-base record. Not here: datasheet-language translation and power/RF tier detail -> [datasheet-to-constraints.md](datasheet-to-constraints.md); contested rules -> [myths-and-contested.md](myths-and-contested.md); shared interface conventions -> [interfaces/common.md](interfaces/common.md); constraint IR -> [../architecture/constraint-ir.md](../architecture/constraint-ir.md).
Keys: rule pack, pack schema v0, precedence 20 30 40, vendor_profile, by_vendor, resolution policy, stricter, window intersection, ask, fab floor, safety floor, effective_min, Board Setup Constraints, drc_engine.cpp, rule strength tiers, hard, soft-strong, soft-weak, context switch, vendor spread, knowledge-base record, check_type K K11 G S
Tags: [P] primary, [S] snippet, [I] inference, [VR] verification_rules.md.

## Rule-pack requirements
1. Every rule carries: (1) a match pattern binding it to schematic objects; (2) typed, unit-carrying parameters, incl. formulas in UI, W, h or fractions of t_r; (3) provenance and precedence, conflicts **recorded, not silently resolved**; (4) a check backend `kicad_dru` | `geometric` | `simulation` | `bom`; (5) a placement intent separate from routing constraints. Required fields `source_scope`, `statement_strength`, `contested_by` let the LLM explain *why* a constraint is hard or soft.
2. Vendor profiles are mandatory: primary values for the same interface differ 5–25× (table below). Unknown vendor, current policy: tightest [P] value + `info` finding naming looser alternatives; two-sided windows take the intersection of [P] windows, empty → conflict (`ask`), never a synthesised composite. Policy under review: per-interface pack defaults differ (e.g. USB2 defaults to 50 mil skew, not SPRAAR7A's 2 mil).
3. Fab and safety minimums are floors, not precedence ranks (formula: [resolution policy](#resolution-policy) step 6); a pack asking for less raises a conflict ("needs a different fab class"). Also compile fab minimums into Board Setup → Constraints (`.kicad_pro`) and clamp every emitted rule to the floors: a matching custom rule escapes KiCad's board-minimum floor ([clearance resolution](../kicad/drc-rule-language-reference.md#clearance-resolution); [drc_engine.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp) [P]).
4. mm values that come only from blogs become rank or comparative objectives, never DRC errors.
5. Express budgets as physics, not lengths (dB budgets, per-material dB/in, per-via ≈2 in TI SLLU149E / ≈1 in Heck, ESD+CMC ≈1 in, UI formulas, cable IL input); compute L_max per stackup ([interfaces/common.md](interfaces/common.md#loss-budget-instead-of-length)). Delay packs (DDR, HDMI, D-PHY, RGMII, SD) emit ps rules directly, TI "<20% of limit" as `opt`, full limit as `max`.
6. Placement intents come from packs: chain order, distance windows and annuli, end-node termination, "AC cap within N mm of either endpoint". Keep packs as data so they can be calibrated against vendor evaluation boards.

## Pack schema v0
[IF] §11 proposal.
```yaml
pack:
  id: <interface-or-circuit id>        # usb2_hs, buck_sync, xtal_pierce
  version: 0.1
  precedence: 30                        # 20 interface < 30 vendor family < 40 datasheet; fab/safety packs are floors, not ranks
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

## Resolution policy
1. Use the highest precedence (design-intent values only).
2. Then use `by_vendor[vendor_profile]`.
3. Then apply the declared `resolution`. The default is "stricter", and it raises an `info` finding citing both sources. "Stricter" is defined for one-sided scalar bounds; two-sided windows take the intersection, and an empty intersection is a conflict (`ask`). Contested rules ([VR] §3) take a selector or `ask`, never "stricter".
4. [S] never overrides [P] at equal precedence.
5. [D]/[I] values are warnings until calibrated.
6. Finally apply the fab and safety floors: effective_min = max(resolved_min, fab_min, safety_min). A resolved value below a floor is a conflict, not an override.

## Worked pack examples
Full YAML in [IF] §11.
- `usb2_hs` -> [interfaces/usb2.md](interfaces/usb2.md#worked-pack-usb2_hs) (shield-termination conflict resolution `ask`).
- `buck_sync` -> [power/buck.md](power/buck.md#irp-buck_sync-rule-pack) (datasheet reference-layout override at precedence 40).
- `xtal_pierce` -> [crystals-clocks.md](crystals-clocks.md): annulus from vendor minimum to 12 mm; parasitic limits; hs_keepout 3 mm [I]; metal-can vendor switch; DRU disallows foreign tracks and vias in `XTAL_KEEPOUT`.
- Test the DRU token forms (`within_diff_pairs`, `insideArea`, `track_angle`) on the installed KiCad.

## Rule strength tiers
[VR] §3.
| Tier | Examples | Encoding |
|---|---|---|
| Hard: fab/assembly | Fab absolute minimums (router targets the recommended values); courtyard non-overlap; IPC-2221B floor; JLC silk 1.0 mm / 0.15 mm | Floors applied after resolution, not a precedence rank; Board setup + `.kicad_dru` ([dfm-fab-limits.md](dfm-fab-limits.md)) |
| Hard: topology (all primary sources agree) | No split or void crossing; ≥1.5W from voids on HS differential pairs (except voided SMD pads); crossings over the bridge; connector → TVS → IC with no stub, no via before the TVS, GND via at its pad; 0 TPs/stubs on SerDes; plus power/RF topology (CIN on the IC layer for integrated converters, with via count and plane coverage scored through the loop-inductance estimate and vertical loops allowed; FB from the COUT pad, "mandatory" AGND–PGND tie, shunt cap via the named VSS pin, antenna keep-out polygon, no digital under RF, AGND+DGND to the analog plane) | G-checker → reject the placement or route |
| Hard within declared scope | Pair skew, via count, 30/50 mil keep-outs, via stub min(15 mil, 0.3/Gbps in) on SerDes ≳3 Gb/s | Only when the interface pack and data rate are known; carries `source_scope` |
| Soft, strong | Return via ≤200 mil as a hard max, with "closer is better" as the objective; ≥90 mil from the plane edge / ≥2h from the board edge; connectors on one edge; I/O ≤2 cm, non-I/O ≥2 cm; plus power items (L2 ≤0.13 mm, 1 via/A, C_boot ≥10·Cg, bead ≤20% of rated I, EP vias 0.3 mm at 1.0–1.2 mm) | High-weight cost terms; warnings that quote the source |
| Soft, weak (heuristic) | TVS ≤5–10 mm; CMC ≤5 mm; crystal ≤5 mm; CIN ≤0.5–1 mm (MPS primary ≤2 mm); FB ≤2–3 mm; RF↔SMPS 20 mm; stitching λ/20, 3–5 mm or 2 mm near SerDes; **2W/3W/5W multipliers (compute crosstalk in h instead)**; 2 cm²/W | Rank-based objectives ("closer than any other part"); never DRC |
| Context switch | See [myths-and-contested.md](myths-and-contested.md) | Store both variants plus a selector; ask; log |
| Myth exceptions | 90° corners are a myth only for single-ended nets below about 2 Gb/s; keep corner/bend rules on ESD and RF nets, differential pairs and nets ≥10 Gb/s | Net-class scoped |

## Severity recalibrations
[VR].
- TL-5 (test points on SerDes) becomes hard.
- EMI-7: the millimetre distance becomes soft; the topology stays P0.
- EMI-6: the 10–15 mm stitch pitch is soft; the P0 is "no crossing without a bridge or stitch".
- RF-05 splits into a hard PCB keep-out plus an enclosure clearance for the mechanical checklist (15 mm for ESP32).

## Vendor spread
| Quantity | Tightest | Loosest | Ratio |
|---|---|---|---|
| USB3 intra-pair | 2 mil (TUSB1046) | 0.7 mm (Qualcomm) | ~14× |
| USB2 intra-pair | 2 mil (SPRAAR7A 2013) | 150 mil (TUSB9261) | 75× (historic) |
| DDR4 DQ↔DQS | 2 ps (TI) | 25 ps (PolarFire) | 12.5× |
| DDR4 ADDR↔CK | 4 ps (TI) | 100 ps (PolarFire) | 25× |
| Ethernet PHY↔magnetics | <1 in (Microchip) | ≥25 mm (Pulse) | opposite directions |
| PCIe AC cap (Gen3+) | 75–220 nF (TI) | 176–265 nF (Qualcomm) | 220 nF fits both; Gen1/2-only parts may cap at 200 nF ([interfaces/pcie.md](interfaces/pcie.md)) |

## Knowledge-base record
[HS] §12 + [VR].
- `rule_id, family, statement`
- `numeric{value, unit, basis: mm|ps|W|h|λ|fraction_of_tr}`
- `physics_why`
- `applies_if{interface, t_r<, data_rate>, layer_type, enclosure, emission_class}`
- `severity, check_type{K, K11, G, S}, kicad_dru_template, checker_fn`
- `source_url, source_author, source_type{physics, rule-of-thumb, vendor-req, spec-req, measured, satirical-inverse, myth}, provenance{P, S, …}, confidence`
- `conflicts_with[], source_scope, statement_strength{mandatory, must, should, as close as possible, good guideline}, contested_by[]`
- Negative (myth) rules are included.
- Precedence: spec and vendor requirements override rules of thumb, and physics drives the checkers.

## Open questions
- The schema is a proposal. The geometric backends exist only as function names.
- `statement_strength` has to be read from the source wording by hand (or by the LLM). No source supplies it as structured data.

## Sources
- [interface_rule_packs.md § 11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md); [rules_highspeed_emi.md § 10, 12](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md); [verification_rules.md § 1 Inferences, 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- See also [checkers-si-emi.md](checkers-si-emi.md).
