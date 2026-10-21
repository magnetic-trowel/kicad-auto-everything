# DRC JSON report and the violation-to-rule repair loop

**TL;DR**
- `kicad-cli pcb drc --format json` writes `drc.v1.json`. **It has no rule-name field.** The rule's name appears only inside the free-text `description` [P].
- **`type` keys are coarse:** for example, `physical_clearance` violations report as `clearance`/`hole_clearance`. Map violations back to IR constraints by giving rules unique names and parsing `description` [P/I].
- **Never drop `unconnected_items` or `schematic_parity`.** One MCP server reported 0 errors on a board with 17 violations and 14 unconnected items [P].
- **Freerouting writes the same drc.v1 format** (plus one extra key), so one parser serves both. Differences between the two reports reveal DSN translation losses [P/I].
- **On a live board, synchronize before running DRC** (exact target → save → snapshot compare → CLI DRC → source unchanged). File-only DRC can report deleted items [P].

## Key facts

### Schema (`drc.v1.json`, identical on 10.0 and master)
- **Top level:** `$schema`, `source`, `date`, `kicad_version`, `violations[]`, `unconnected_items[]`, `schematic_parity[]`, `coordinate_units` (mm|mils|in), `included_severities[]` (error|warning|exclusion), `ignored_checks[]` (`{key, description}`) [P] ([drc.v1.json @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/resources/schemas/drc.v1.json)).
- **Each violation:** `type` (the settings key), `description`, `severity` (error|warning), `items[]` (`{uuid, description, pos{x,y}}`), `excluded`, `comment`.
- **Invalid JSON schema:** the schema file has a **trailing comma in `required`**, which is invalid strict JSON (also on master).
- **`description`** = `GetErrorMessage()` = error title + detail, e.g. `"Clearance violation (<source> clearance 0.2000 mm; actual 0.1500 mm)"`. `<source>` is the rule or net-class name. Only the text `.rpt` adds `GetViolatingRuleDesc()` [P] ([rc_item.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/rc_item.cpp)).
- **Freerouting** writes drc.v1 via `-drc` and `GET /jobs/{id}/drc`, adding a `freerouting_version` key that the KiCad schema's `additionalProperties:false` would reject. `compact=true` "drops raw coordinate bloat by >70%". `/drc/summary` gives "spatial congestion hotspots and … auto-correction hints" [P] ([API_v1.md](https://github.com/freerouting/freerouting/blob/master/docs/API/API_v1.md)).

### All 67 `type` keys in 10.0
unconnected_items, shorting_items, items_not_allowed, text_on_edge_cuts, clearance, creepage, tracks_crossing, copper_edge_clearance, zones_intersect, isolated_copper, starved_thermal, via_dangling, track_dangling, hole_clearance, hole_to_hole, holes_co_located, connection_width, track_width, track_angle, track_segment_length, annular_width, drill_out_of_range, via_diameter, padstack, padstack_invalid, microvia_drill_out_of_range, courtyards_overlap, missing_courtyard, malformed_courtyard, pth_inside_courtyard, npth_inside_courtyard, item_on_disabled_layer, invalid_outline, duplicate_footprints, missing_footprint, extra_footprint, net_conflict, footprint_symbol_mismatch, footprint_filters_mismatch, footprint_symbol_field_mismatch, lib_footprint_issues, lib_footprint_mismatch, unresolved_variable, assertion_failure, generic_warning, generic_error, copper_sliver, solder_mask_bridge, silk_over_copper, silk_edge_clearance, silk_overlap, text_height, text_thickness, length_out_of_range, skew_out_of_range, too_many_vias, diff_pair_gap_out_of_range, diff_pair_uncoupled_length_too_long, footprint, footprint_type_mismatch, through_hole_pad_without_hole, mirrored_text_on_front_layer, nonmirrored_text_on_back_layer, missing_tuning_profile, tuning_profile_track_geometries, track_on_post_machined_layer, track_not_centered_on_via [P] ([drc_item.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_item.cpp)).

- **Master** adds footprint_scaled_with_pads, hole_aspect_ratio, malformed_microvia_stack_span, microvia_crosses_core, microvia_stack_depth, microvia_stack_not_filled, net_chain_return_path, net_chain_stub_length, net_chain_tuning_profiles and via_stitch_overlap, and **drops zones_intersect** [P] ([@master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/drc/drc_item.cpp)).

### Failures seen in MCP servers
- **Konnect's parser discarded two thirds of the result.** It dropped `unconnected_items` and `schematic_parity`, "so an unrouted net … was invisible". On ecc83-pp with its 59 segments stripped, KiCad reported 17 violations and 14 unconnected items, while Konnect counted 0. It also read positions from a field "the schema has never had" and dropped the rule key, "the only part of a violation a caller can act on" [P] ([e7eeeac](https://github.com/mixelpixx/Konnect/commit/e7eeeac3dc013f4fdeb18598d77fed9e591f2930)).
- **KiCad 10 schema change:** courtyard violations needed a "schema-aware courtyard classifier" in PRO that stays compatible with legacy reports [P] ([03238cae](https://github.com/oaslananka/kicad-mcp-pro/commit/03238cae9a22b1cfb72df1c5fe4d552a54aaa90a)).
- **Live versus file DRC.** Konnect's `sync_live_board` runs: exact target → save → native-snapshot comparison → CLI DRC → check that the saved source did not change. A failed save gives `mutation_outcome_uncertain` and DRC stops.
  - Regression recipe: create and save a via, delete it without saving, show file-only DRC still reports the via's UUID, then show synchronized DRC drops it [P] ([DRC_SYNCHRONIZATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/DRC_SYNCHRONIZATION.md)).
- **GUI scraping.** KMS also has a GUI driver whose `kicad_run_drc` opens the dialog, clicks "Run DRC" and scrapes the grid, with a Linux AT-SPI backend [P].
- **PRO's focused DRC slices:** `get_courtyard_violations`, `get_unconnected_nets`, `get_silk_to_pad_violations`. Gates: `pcb_placement_quality_gate`, `pcb_transfer_quality_gate`, `project_full_validation_loop` (a bounded fix-and-rerun) [P].
- **A clean DRC only covers what is enabled.** GPT-6 Astra's "0 DRC" result had 5 DRC and 4 ERC categories ignored [P] ([JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad)). A no-tools Claude Code run passed DRC while routing signals through a GND plane layer [P] ([devbisme tests](https://github.com/devbisme/ai-circuit-design-tests)).

## Recommendations for our system
- **Rule-name protocol** [I, from VK]:
  - Prefix every generated rule with a stable IR ID, e.g. `(rule "IR:c42:decap_len" …)`.
  - Map each violation by regex on `description`, e.g. `\((rule '|)?([^ ]+)'? .*?; actual .*?\)`, or by parsing the `.rpt`.
  - Keep a sidecar map from rule name to IR constraint. Treat `type` only as a coarse class.
- **Lint pass:** after writing `.kicad_dru`, run DRC on a scratch copy; syntax errors block DRC entirely [I].
- **One tolerant parser** for KiCad and Freerouting drc.v1: accept the trailing comma and extra keys. Keep `unconnected_items`, `schematic_parity`, each item's position and the rule key. Report `null`, not `0`, for parity when it did not run [I].
- **Synchronize live state** (save, compare, refill) before trusting DRC on a live board [I].
- **Name every waived or ignored check** in the agent's review report. Never silently exclude categories [I, from PI].
- **Add layout-quality checks DRC misses:** signals on plane layers, plane splits under high-speed nets, decap distance, diff-pair skew, via counts. Rules live in the `rules/` area [I].

## Conflicts and open questions
- Does `solder_mask_sliver` emit a dedicated key? Not found.
- How stable is `description` wording across point releases? Untested, but the regex depends on it.

## Sources
- research notes:
  - [verification_kicad_and_tools.md § 2.9, § 2 Inferences, § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [kicad_mcp_codebases.md § 1, § 2D–E, § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
  - [patents_and_industry.md § 4 (Astra), § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md)
  - [existing_tools_and_apis.md § 2 (devbisme)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
- primary: [drc.v1.json](https://gitlab.com/kicad/code/kicad/-/blob/10.0/resources/schemas/drc.v1.json), [rc_item.h](https://gitlab.com/kicad/code/kicad/-/blob/10.0/include/rc_item.h), [drc_test_provider_copper_clearance.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_test_provider_copper_clearance.cpp)

See also: [drc-rule-language-reference.md](drc-rule-language-reference.md), [kicad-cli.md](kicad-cli.md), [specctra-freerouting-integration.md](specctra-freerouting-integration.md), [mcp-tool-surface-spec.md](mcp-tool-surface-spec.md)
