# DRC JSON report and the violation-to-rule repair loop

Scope: `drc.v1.json` schema, the 67 `type` keys, mapping violations back to IR rules, parser failures seen in MCP servers. Not here: rule syntax -> [drc-rule-language-reference.md](drc-rule-language-reference.md); CLI flags -> [kicad-cli.md](kicad-cli.md).
Keys: drc.v1.json, violation type keys, description, rule name, unconnected_items, schematic_parity, GetErrorMessage, GetViolatingRuleDesc, live vs file DRC, sync_live_board, mutation_outcome_uncertain, rule-name protocol, IR prefix, Freerouting drc

## Schema (drc.v1.json, identical on 10.0 and master)
- **Top level:** `$schema`, `source`, `date`, `kicad_version`, `violations[]`, `unconnected_items[]`, `schematic_parity[]`, `coordinate_units` (mm|mils|in), `included_severities[]` (error|warning|exclusion), `ignored_checks[]` (`{key, description}`) [P] ([drc.v1.json @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/resources/schemas/drc.v1.json)).
- **Violation:** `type` (settings key), `description`, `severity` (error|warning), `items[]` (`{uuid, description, pos{x,y}}`), `excluded`, `comment`.
- **No rule-name field.** The winning rule's name appears only inside `description`.
- **Schema bug:** trailing comma in `required` (invalid strict JSON; also on master).
- **`description`** = `GetErrorMessage()` = title + detail, e.g. `"Clearance violation (<source> clearance 0.2000 mm; actual 0.1500 mm)"`. `<source>` = winning rule name, or for non-rule sources "board minimum", "net tie", the net class, or a pad/footprint override ([clearance resolution](drc-rule-language-reference.md#clearance-resolution)). Only the text `.rpt` adds `GetViolatingRuleDesc()` [P] ([rc_item.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/rc_item.cpp)).
- **`type` is coarse:** e.g. `physical_clearance` violations report as `clearance`/`hole_clearance` [P].
- **Freerouting** writes drc.v1 via `-drc` and `GET /jobs/{id}/drc`, plus a `freerouting_version` key that the schema's `additionalProperties:false` would reject. `compact=true` "drops raw coordinate bloat by >70%"; `/drc/summary` gives "spatial congestion hotspots and … auto-correction hints" [P] ([API_v1.md](https://github.com/freerouting/freerouting/blob/master/docs/API/API_v1.md)). One parser serves both; differences between the two reports reveal DSN translation losses [I].

## All 67 type keys in 10.0
unconnected_items, shorting_items, items_not_allowed, text_on_edge_cuts, clearance, creepage, tracks_crossing, copper_edge_clearance, zones_intersect, isolated_copper, starved_thermal, via_dangling, track_dangling, hole_clearance, hole_to_hole, holes_co_located, connection_width, track_width, track_angle, track_segment_length, annular_width, drill_out_of_range, via_diameter, padstack, padstack_invalid, microvia_drill_out_of_range, courtyards_overlap, missing_courtyard, malformed_courtyard, pth_inside_courtyard, npth_inside_courtyard, item_on_disabled_layer, invalid_outline, duplicate_footprints, missing_footprint, extra_footprint, net_conflict, footprint_symbol_mismatch, footprint_filters_mismatch, footprint_symbol_field_mismatch, lib_footprint_issues, lib_footprint_mismatch, unresolved_variable, assertion_failure, generic_warning, generic_error, copper_sliver, solder_mask_bridge, silk_over_copper, silk_edge_clearance, silk_overlap, text_height, text_thickness, length_out_of_range, skew_out_of_range, too_many_vias, diff_pair_gap_out_of_range, diff_pair_uncoupled_length_too_long, footprint, footprint_type_mismatch, through_hole_pad_without_hole, mirrored_text_on_front_layer, nonmirrored_text_on_back_layer, missing_tuning_profile, tuning_profile_track_geometries, track_on_post_machined_layer, track_not_centered_on_via [P] ([drc_item.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_item.cpp)).

**Master** adds footprint_scaled_with_pads, hole_aspect_ratio, malformed_microvia_stack_span, microvia_crosses_core, microvia_stack_depth, microvia_stack_not_filled, net_chain_return_path, net_chain_stub_length, net_chain_tuning_profiles, via_stitch_overlap, and **drops zones_intersect** [P] ([@master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/drc/drc_item.cpp)).

## Failures seen in MCP servers
| Failure | Detail |
|---|---|
| Konnect parser discarded 2/3 of the result | Dropped `unconnected_items` and `schematic_parity` ("so an unrouted net … was invisible"). ecc83-pp with its 59 segments stripped: KiCad 17 violations + 14 unconnected, Konnect counted 0. Read positions from a field "the schema has never had"; dropped the rule key, "the only part of a violation a caller can act on" [P] ([e7eeeac](https://github.com/mixelpixx/Konnect/commit/e7eeeac3dc013f4fdeb18598d77fed9e591f2930)) |
| KiCad 10 courtyard change | PRO needed a "schema-aware courtyard classifier" compatible with legacy reports [P] ([03238cae](https://github.com/oaslananka/kicad-mcp-pro/commit/03238cae9a22b1cfb72df1c5fe4d552a54aaa90a)) |
| File-only DRC on a live board reports deleted items | Konnect `sync_live_board`: exact target → save → native-snapshot compare → CLI DRC → check saved source unchanged; failed save → `mutation_outcome_uncertain`, DRC stops [P] |
| GUI scraping | KMS GUI driver `kicad_run_drc` opens the dialog, clicks "Run DRC", scrapes the grid (Linux AT-SPI backend) [P] |
| Clean DRC covers only enabled checks | GPT-6 Astra "0 DRC" had 5 DRC and 4 ERC categories ignored [P] ([JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad)). A no-tools Claude Code run passed DRC while routing signals through a GND plane layer [P] ([devbisme tests](https://github.com/devbisme/ai-circuit-design-tests); table in [../landscape/kicad-ai-tools-and-mcp-servers.md](../landscape/kicad-ai-tools-and-mcp-servers.md#independent-hands-on-test-devbisme)) |

**Live-DRC regression recipe** (Konnect) [P] ([DRC_SYNCHRONIZATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/DRC_SYNCHRONIZATION.md)): (1) create and save a via; (2) delete it without saving; (3) file-only DRC still reports the via's UUID; (4) synchronized DRC (refill, save) drops it.

**PRO focused DRC slices:** `get_courtyard_violations`, `get_unconnected_nets`, `get_silk_to_pad_violations`; gates `pcb_placement_quality_gate`, `pcb_transfer_quality_gate`, `project_full_validation_loop` (bounded fix-and-rerun) [P].

## Rule-name protocol
[I, from VK]
1. Prefix every generated rule with a stable IR ID: `(rule "IR:c42:decap_len" …)`.
2. Map each violation by regex on `description`, e.g. `\((rule '|)?([^ ]+)'? .*?; actual .*?\)`, or parse the `.rpt`.
3. Keep a sidecar map rule name → IR constraint; treat `type` only as a coarse class.
4. A `<source>` without `IR:` ("board minimum", "net tie", net class, override) is its own class: no compiled rule won there.

## Parser and loop requirements
[I]
- One tolerant parser for KiCad and Freerouting drc.v1: accept the trailing comma and extra keys; keep `unconnected_items`, `schematic_parity`, each item's position, the rule key. Parity not run → `null`, not `0`.
- Referee: the command in [kicad-cli.md](kicad-cli.md#referee-command), on a saved copy; lint `.kicad_dru` on a scratch copy first.
- On a live board, synchronize (save, compare, refill) before trusting DRC.
- Name every waived or ignored check in the review report; never silently exclude categories [I, from PI].
- Add checks DRC misses (signals on plane layers, plane splits under high-speed nets, decap distance, diff-pair skew, via counts) in the `rules/` area.

## Open questions
- Does `solder_mask_sliver` emit a dedicated key? Not found.
- How stable is `description` wording across point releases? Untested; the regex depends on it.

## Sources
- [verification_kicad_and_tools.md § 2.9, § 2 Inferences, § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); [kicad_mcp_codebases.md § 1, § 2D–E, § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md); [patents_and_industry.md § 4 (Astra), § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md); [existing_tools_and_apis.md § 2 (devbisme)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
- [drc.v1.json](https://gitlab.com/kicad/code/kicad/-/blob/10.0/resources/schemas/drc.v1.json), [rc_item.h](https://gitlab.com/kicad/code/kicad/-/blob/10.0/include/rc_item.h), [drc_test_provider_copper_clearance.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_test_provider_copper_clearance.cpp)
