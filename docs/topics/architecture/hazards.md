<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Hazards: what kae tells the commanding LLM about the board it hands back

**TL;DR**
- **Every JSON report the LLM reads ends with `hazards` and `hazard_summary`** (`kae place`, `kae.route.cli`, `kae.route.critical_cli`, `kae.joint.cli`, `kae brief`, `kae.excite.evaluate`, `kae.sim`). `hazard_summary.blocked` is true when the board would not work or cannot be built as drawn [M].
- **The project's own DRC severities can hide a short.** KiCad does not run a check set to `ignore` at all (nothing in `violations`, even with `--severity-all`; only a line in `ignored_checks`) [M]. kae therefore rechecks every board it writes with the safety checks forced on, on a scratch copy; the board, its project and the benchmark's scoring are untouched [M].
- **Static project hazards need no KiCad:** checks the project downgrades, custom rules that waive their own severity, a `.kicad_dru` KiCad drops, design minimums below every mainstream fab, and net classes whose clearance is below IPC-2221B for the net's inferred voltage [I].
- **Risk signals kae already wrote are gathered** (current-capped rails, BGA escape certificates, unchecked final cards, modules over their physics allocation) instead of staying buried in sub-reports [M].
- **Compact by contract:** at most 40 entries and 8 per code, objects capped at 12 per entry, with counts of what was cut; a block entry is never dropped for space ([agent-tooling-reliability-patterns.md](../ux/agent-tooling-reliability-patterns.md) item 8) [I].

## Key facts

### The entry and the summary (`kae/src/kae/hazards.py`)

```json
{"code": "drc_shorting_items", "severity": "block", "category": "electrical",
 "message": "2 x copper of two different nets touches (a short) (the project sets this check to ignore, ...).",
 "objects": ["R2", "N2", "N1"],
 "evidence": {"count": 2, "project_severity": "ignore", "hidden_by_project": true,
              "example": "Items shorting two nets", "at_mm": [[120.8, 105.0]]},
 "fix": "move or re-route the items so the nets are separated"}
```

- `severity`: `block` (the board would not work, or cannot be built as drawn), `warn` (buildable, a risk the caller must weigh), `info`.
- `category`: electrical, manufacturing, assembly, thermal, safety, data.
- `code` is stable snake case; `objects` are refs, nets, rules or check keys; `evidence` carries the numbers and the source of the limit; `fix` is the concrete action or relaxation.
- Optional: `source` (the sub-report path it came from), `sources` (when deduped from several), `objects_more` (objects cut).
- `hazard_summary`: `{block, warn, info, blocked, total, shown, omitted: {code: n}, objects_truncated, block_codes: {code: n}}`.
- Code that relaxes, skips, caps, assumes or ignores something appends a plain dict to the report it already writes (`rep.setdefault("hazards", []).append(...)` or `hazards.add`). `finalize` at the CLI hoists nested lists, derives flags, dedupes by (code, objects) keeping the most severe, sorts, caps and writes the summary as the last two keys.

### Which report emits what

| Command | Hazards from |
|---|---|
| `kae place` | static project hazards; recheck of OUTPUT (opens and dangling copper left out: a placement is not routed); `body_overlap`/`body_relaxed`; `connector_off_edge`; writer checks; `dru_rejected` |
| `kae.route.cli route`, `lastmile` | static; recheck of OUTPUT; BGA `escape_infeasible`; else the bridge's final DRC counts |
| `kae.route.critical_cli route` | static; recheck; `copper_below_ipc_width`, `rail_left_narrow`, `vias_below_current` (heat of the copper drawn, [critical-net-routing](../routing/critical-net-routing.md)); `class_max_below_ipc` module flags; `crystal_ground_no_plane` |
| `kae.route.critical_cli physics` | `physics_over_budget` (u > 1), `physics_unmeasured`; static |
| `kae.joint.cli run` | static; recheck; everything nested in iterations; `check_not_run` and `physics_over_budget` of the final card; KiCad's writer checks of every pose write, once per code (`kicad_format_upgraded`, ...) |
| `kae brief` | static project hazards with the brief's net voltages (route and joint reports have no brief at hand, so `hv_clearance_below_ipc` and `capacitor_over_voltage` come from `kae brief` and `kae place`) |
| `kae.excite.evaluate -o`, `kae.sim evaluate` | harms over their limit (`physics_over_budget`); failed or incomplete simulated requirements (`sim_fail`, `sim_incomplete`) |

### The recheck (`kae/src/kae/board_hazards.py`)

- **Why it is needed.** Of 2,454 qualified boards, 184 downgrade `courtyards_overlap`, 96 `copper_edge_clearance`, 49 `clearance` and 7 `shorting_items` (divergence register B1). Over the 7,226 project files of the whole corpus, `ignore` / `warning`: `shorting_items` 11 / 6, `clearance` 72 / 58, `copper_edge_clearance` 169 / 69, `hole_clearance` 96 / 66, `annular_width` 53 / 25, `courtyards_overlap` 318 / 202, `unconnected_items` 7 / 5 [M]. kae's DRC loops and the scorer take severities from the board's project, so on those boards a short, an edge violation or a clearance violation counts as clean [M].
- **What KiCad 10.0.7 emits** (measured on a two-resistor board, `kae/tests/test_board_hazards.py`): a check set to `ignore` reports none of its violations under `--severity-all`; it is listed in `ignored_checks`. A check set to `warning` reports at warning severity. With `shorting_items` ignored, the short shows up as two `clearance` violations of 0.0 mm; with `clearance` ignored too, it is invisible [M].
- **What it finds.** On the Freerouting 2.5.0 outputs of 12 corpus boards whose projects ignore `shorting_items`, `clearance` or `copper_edge_clearance`, the recheck found violations the project hid on 9: rt08-programboard 199 shorts and 236 clearance violations, perci-detonator-trigger 12 shorts and 34 clearance, gmwm-analysis-board 16 shorts, gy-pcm5102a 16 copper-to-edge, roza-reflow-master (0 errors by its own severities) 10 clearance and 28 hole clearance. Recheck 1.5–5.6 s per board, the same as the plain DRC [M].
- **Mechanism** (KiCad 10.0 `drc_engine.cpp` `RunTests`): an ignored check gets an error limit of 0, and `ReportViolation` drops every violation past its limit; other checks stop at `ERROR_LIMIT` (clearance and opens at the extended limit), so a count can be a floor [P].
- **How.** One `kicad-cli pcb drc` (kae's wrapper `kae.route.drc.run`, as the scorer runs it: zones refilled, all severities, uncapped opens) on a scratch copy whose `.kicad_pro` has each check below raised to at least its required severity. Every violation of those checks becomes one hazard per check type, with count, objects (refs and nets parsed from the item descriptions), up to 3 locations, and `hidden_by_project` when the project's severity would have hidden it [M].
- **When.** `--recheck auto` (default) runs it if kicad-cli is found and at least 20 s of the command's `--time` is left; it never takes routing time. If skipped, `recheck_skipped` says so: `warn` when the project downgrades a safety check, `info` otherwise (kae's own final DRC then ran at the right severities, and its counts become hazards). `--recheck on` runs it regardless of time; `off` never. `kae place --drc off` implies off [I].
- **Cost.** One extra DRC of the output, the same as kae's own DRC of it: 1.7, 2.7 and 28.7 s against 2.2, 2.7 and 26.6 s for the plain DRC, on Freerouting outputs at the median, 90th and 99th percentile of the scorer's time per board (8.9, 16.5 and 81 s over 14,541 boards; the slowest board took 1,091 s to score) [M]. Within `--time` this fits on most boards; on the biggest ones `auto` usually skips it, so ordering a big board calls for `--recheck on`.

### The check classes (`DRC_CHECKS`)

| Severity | Checks | Why |
|---|---|---|
| block, electrical | `shorting_items`, `tracks_crossing`, `unconnected_items`, `clearance` | a short or an open is a different circuit. A clearance violation is below the designer's own rule, which encodes both the fab's capability and voltage isolation; kae cannot tell which, so it blocks [I] |
| block, safety | `creepage` | KiCad 10's native creepage constraint only exists when the designer wrote one ([isolation-creepage.md](../rules/isolation-creepage.md)) |
| block, manufacturing | `copper_edge_clearance`, `hole_clearance`, `annular_width`, `drill_out_of_range`, `microvia_drill_out_of_range`, `via_diameter`, `track_width`, `invalid_outline` | below the board's own minimums or uncuttable: fabs need copper 0.2–0.4 mm from routed edges, annular rings of 0.1–0.25 mm ([dfm-fab-limits.md](../rules/dfm-fab-limits.md)) |
| warn | `hole_to_hole`, `holes_co_located`, `connection_width`, `zones_intersect`, `items_not_allowed`, `starved_thermal`, `solder_mask_bridge`, `courtyards_overlap`, `copper_sliver`, length/skew/diff-pair rules, `too_many_vias`, `assertion_failure`, `track_on_post_machined_layer`, `silk_over_copper`, `silk_edge_clearance` | buildable, but assembly, yield or signal risk. KiCad itself ships hole-to-hole, connection width and the silk checks as warnings |
| info | `isolated_copper`, `via_dangling`, `track_dangling`, `silk_overlap`, `text_height`, `text_thickness`, `pth_inside_courtyard`, `npth_inside_courtyard` | cosmetic or harmless; the two courtyard-hole checks are ignored by 6,519 of the corpus's 7,226 projects (KiCad 6–9's default), and a part-to-part conflict also shows as `courtyards_overlap` |

- Forced severity: error for the block class; KiCad's shipped default for the rest (`warning` where KiCad ships `warning` or `ignore`). KiCad's defaults are from `BOARD_DESIGN_SETTINGS` (`pcbnew/board_design_settings.cpp` @10.0) [P].
- Left out: library checks (environment-dependent, as the scorer), schematic parity (not run without `--schematic-parity`), `missing_courtyard` (KiCad ignores it by default; the placer's relaxed parts are reported instead).

### Static project hazards

| Code | Severity | Trigger |
|---|---|---|
| `drc_check_downgraded` | warn (block class), info (warn class) | the project runs a check of the table below its required severity |
| `dru_rule_downgraded` | warn | a custom rule with `(severity ignore|warning|exclusion)` |
| `dru_rejected` | warn | `kae.board.dru_check.rejection` (`kae dru-check`): KiCad drops the whole file on any error |
| `below_fab_floor` | warn | board minimum, net-class or custom-rule clearance/width/drill/annular/edge/hole-to-hole below the smallest absolute limit of JLCPCB, PCBWay and OSH Park: 0.09 mm space and width, 0.15 mm drill, 0.10 mm annular, 0.2 mm edge, 0.127 mm hole-to-hole ([dfm-fab-limits.md](../rules/dfm-fab-limits.md)) |
| `hv_clearance_below_ipc` | warn, safety | a net kae.circuit puts above 30 V whose class clearance is below IPC-2221B Table 6-1 B2 (external, uncoated) for its voltage to the lowest net; a custom clearance rule naming the net or class at that value clears it (register RC10) |
| `capacitor_over_voltage` | block (warn when the rail voltage is only inferred), electrical | the brief's `summary.caps_over_rating`: a capacitor from a rail to ground whose stated rating (`Voltage` field, else the value) is below the rail's nominal voltage; evidence: rated V, rail V and its source. 64 such MLCCs in the corpus ([component-priors](../../research/physics/component-priors.md)) |

- IPC-2221B B2: 0.1 mm to 30 V, 0.6 mm to 100 V, 1.25 mm to 300 V, 2.5 mm to 500 V, then 0.005 mm/V ([isolation-creepage.md](../rules/isolation-creepage.md); EMA reproduction of Table 6-1) [S]. It is functional spacing only; mains and touchable circuits need the safety standard's creepage and clearance, which the message says.
- Net voltages are inferred (`kae.circuit` brief `volts`), so the hazard is a warning, never a block, and its evidence names the source.

### Flags gathered from existing reports (`hazards.derive`)

| Code | Severity | From |
|---|---|---|
| `copper_below_ipc_width`, `rail_left_narrow` | block / warn / info, thermal | copper narrower than its IPC width (the `rail_max_mm` cap, or a hop left to the bridge at the class width): block past 130 °C from 50 °C at the expected current, info within 1.2× |
| `class_max_below_ipc` | warn, thermal | net class maximum below the IPC-2221 width for the current |
| `escape_infeasible` | block, electrical | `escape.certificate`: balls no routing can escape under the rules, with the relaxations that suffice ([bga-routing-ranked-ideas.md](../routing/bga-routing-ranked-ideas.md)) |
| `body_overlap` / `body_relaxed` | block / info, assembly | `Problem.relaxed_body_hazards`, per part `relax_bodies` freed (off by default; `escalate`, `auto`), on the final poses: block when its body overlaps another part ([kae-exact-legality](../../research/placement/kae-exact-legality.md)) |
| `check_not_run` | warn, data | the joint loop's final card `checked` has `false` (values reported `null`) |
| `physics_over_budget` | warn | a module's routed u > 1 (the critical recheck flags u crossing 1, [critical-net-routing.md](../routing/critical-net-routing.md)) |
| `outline_incomplete` | block, manufacturing | `kae place`: staged footprints carry Edge.Cuts, the outline is open |
| `placement_illegal` | block, assembly | `kae place` `legal: false` (exit 3): overlaps or outline violations remain |
| `rules_not_modelled`, `rule_errors` | warn, data | the bridge's plan: custom-rule functions the router does not model, rules it could not evaluate |

## Recommendations for our system
- Treat `hazard_summary.blocked` as the gate: a blocked board is not a deliverable, whatever `status` says. The `fix` field is the next command or relaxation to try.
- New relaxations anywhere in kae add a hazard where they happen; `finalize` does the rest. Keep codes stable; add rows to the tables above.
- Run with `--recheck on` when the board will be ordered; `auto` keeps benchmark timing unchanged.

## Conflicts and open questions
- **Errors the input already had** (a fixed via below the board's drill minimum, say) come back as hazards too; the report does not yet say which findings the input board already carried (that needs a DRC of the input).
- **Clearance as block** follows the user's rule (never hand back a board that might not work). A designer who lowered `clearance` to warning on purpose (e.g. a known footprint conflict) will see a block; the evidence says `hidden_by_project`, so the LLM can confirm with them.
- **The scorer is unchanged.** A fixed-severity scoring profile (register B1, [dev-eval-plan.md](../verification/dev-eval-plan.md) H12) is a separate scoring decision; the recheck only reports.
- **Exclusions** (`excluded: true` violations the designer waived in KiCad) are not reported as hazards.
- **Placement.** The placer still drops constraints that a project downgrades (register P2); the place recheck reports what that let through.

## Sources
- KiCad 10.0 `pcbnew/board_design_settings.cpp` (default severities) [P]; `pcbnew/drc/drc_item.cpp` (check keys, via [drc-report-and-repair-loop.md](../kicad/drc-report-and-repair-loop.md)) [P].
- Measured: `kae/tests/test_board_hazards.py::test_ignored_short_is_a_block_hazard` on KiCad 10.0.7 [M].
- IPC-2221B Table 6-1 via [EMA](https://www.ema-eda.com/ema-resources/blog/pcb-clearance-and-creepage-distance-table/) [S]; fab limits from [dfm-fab-limits.md](../rules/dfm-fab-limits.md) [P].
- research notes: [verification_kicad_and_tools.md § 2.9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md) (DRC report schema, "name every waived or ignored check").

See also: [drc-report-and-repair-loop.md](../kicad/drc-report-and-repair-loop.md), [mcp-tool-surface-spec.md](../kicad/mcp-tool-surface-spec.md), [joint-loop.md](joint-loop.md), [kae-place.md](../placement/kae-place.md), [isolation-creepage.md](../rules/isolation-creepage.md)
