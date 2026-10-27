# KiCad 10 custom DRC rule language (`.kicad_dru`): reference for a constraint compiler

**TL;DR**
- **10.0 parses:** 35 constraint keywords (34 documented plus the undocumented `solder_mask_sliver`), 3 deprecated aliases, 23 current functions (including the undocumented `intersectsKeepout`) plus 5 deprecated ones, any registered item property, and 4 severities plus a `layer` clause [P].
- **Units are only `mm, mil, in, deg, ps, fs`.** The documented `th`, `"` and `rad` are rejected by the source. Time units are allowed only in `length` and `skew` (corrected, VK) [P].
- **Parser gotchas:**
  - A second `condition` silently **overwrites** the first.
  - Each constraint type may appear only once per rule.
  - The **last** matching rule wins, but a footprint net tie forces clearance 0 and pad/footprint clearance overrides beat every rule (see *Clearance resolution*).
  - **`&&` binds looser than `||`** (the reverse of C), and comparisons bind tighter than both. The user doc's "same precedence, left to right" is wrong, so always parenthesise (corrected from the 10.0 grammar) [P].
- **`microvia_*` and `isStackedVia` are master-only**; the master keyword is `hole_aspect_ratio`. `track_angle` and `track_segment_length` *are* in 10.0 (corrected, VK) [P].
- **What DRC can and cannot express:**
  - Can: courtyard spacing, side or orientation (via `assertion`), rule-area containment, edge and keepout distances.
  - Cannot: pairwise pad distance between two footprints, alignment, symmetry, loop area. Those need our own checker [P/I].

## Key facts

### Grammar and evaluation (10.0)
Sources: [pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc) ([rendered](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom-design-rules)) and [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp) [P].
- **File:** `<project>.kicad_dru`, starting with `(version 1)` ("As of KiCad 10.0, the version is `1`").
  - `#` starts a comment.
  - `${var}` is substituted before parsing; object-dependent variables (`${LAYER}`) cause syntax errors.
  - Only `version` and `rule` are valid at top level.
- **Rule form:** `(rule <name> [(severity error|warning|ignore|exclusion)] [(layer <L>|outer|inner)] [(condition "<expr>")] (constraint <type> …)…)`.
  - A second `layer` clause is an error.
  - "Rule already has a '%s' constraint" is raised for a repeated constraint type.
- **Evaluation order:** rules are "evaluated in reverse order" and the first match wins, so put specific rules **later**.
- **Clearance resolution** (`DRC_ENGINE::EvalRules`) [P] ([drc_engine.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp)):
  1. A footprint net tie forces clearance 0 (source "net tie").
  2. Pad and footprint clearance overrides (`Clearance_Override`) beat every custom rule. They are floored at Board Setup's minimum clearance (hole-clearance overrides at its minimum hole clearance).
  3. Otherwise the last matching custom rule's value is used as is, with no board-minimum floor, so a negative `min` still allows overlap.
  4. With no matching custom rule, the net-class value is maxed with local clearances (e.g. zones) and floored at the board minimum; implicit diff-pair gaps are floored the same way. The source then names the net class, the local item or "board minimum".
  - So the violation `<source>` is a rule name only in case 3 ([drc-report-and-repair-loop.md](drc-report-and-repair-loop.md)).
- **Severity:** `ignore` rules are still evaluated and "can still override previous rules". The interactive router does **not** observe `ignore`; it observes error, warning and exclusion.
- **Conditions:**
  - Objects `A` and `B` are tested in both orders; `AB.` is used for pair functions.
  - Precedence, lowest to highest: `&&` < `||` < comparisons (`== != > >= < <=`, non-associative) < `!` < `+ -` < `* /`. So `a && b || c` parses as `a && (b || c)` and `!x == y` as `(!x) == y`. The 10.0 user doc says "All the boolean operators have the same precedence and are evaluated in order from left to right"; the grammar disagrees (corrected) [P] ([grammar.lemon @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/libeval_compiler/grammar.lemon)).
  - Booleans are bare (`A.Do_not_populate`); there are no `true`/`false` literals; `null` is comparable.
  - A unitless value is in nm, or degrees for angles.
- **Units:** resolver error text "must be mm, in, mil, deg, fs, or ps". Time units elsewhere raise "Time based units not allowed for constraint type"; mixing time and length raises "Mixed units" [P] ([pcbexpr_evaluator.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcbexpr_evaluator.cpp)).
- **Component classes:** a separate parser, `ParseComponentClassAssignmentRules`, handles `(assign_component_class <name> (condition …))` for Board Setup component-class assignment.

### Constraints parsed in 10.0
"opt→router" means the interactive router or length tuner uses the `opt` value. Keys are the DRC JSON `type` values ([drc_item.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_item.cpp)) [P].

| Constraint | Args / units | Notes, DRC key(s) |
|---|---|---|
| `clearance` | min; negative min allows overlap | Honoured by router; **different nets only**. Keys `clearance`, `hole_clearance`, `shorting_items`, `tracks_crossing`, `zones_intersect` |
| `physical_clearance` | min | Net-agnostic; same layer only, except Edge.Cuts counts on all layers; "much slower". **Reported as `clearance`/`hole_clearance`.** Router enforces it since 10.0.4 |
| `physical_hole_clearance` | min | Round holes only ("drilling tolerance"); router since 10.0.4; key `hole_clearance` |
| `hole_clearance` | min | Drilled hole to copper of another net |
| `edge_clearance` | min; negative allowed | Edge = Edge.Cuts **and oval pad holes** ("milling tolerance"). Keys `copper_edge_clearance`, `silk_edge_clearance` |
| `courtyard_clearance` | min; negative allowed | Footprints without a courtyard produce no error. Keys `courtyards_overlap` (+ `missing_courtyard`, `malformed_courtyard`, `pth_`/`npth_inside_courtyard`) |
| `creepage` | min | Surface path between nets |
| `connection_width` | min | Narrowest copper, including zone necks |
| `silk_clearance` | min; negative allowed | `silk_overlap`, `silk_over_copper` |
| `hole_size` | min/opt/max | opt→router default drill. Oval: minor axis vs min, major vs max. `drill_out_of_range`, `microvia_drill_out_of_range` |
| `hole_to_hole` | min | Mechanical drills only (laser and milled not checked). `hole_to_hole`, `holes_co_located` |
| `annular_width` | min/max | Vias and pads |
| `via_diameter` | min/opt/max | opt→router default |
| `via_count` | min/max, unitless | Per net or per `fromTo` path → `too_many_vias`. The diff-pair and matched-length providers also emit it |
| `via_dangling` | none | Use with `severity` |
| `disallow` | `track via through_via blind_via buried_via micro_via pad zone text graphic hole footprint` | `via` means **all** via types. `items_not_allowed`, `text_on_edge_cuts` |
| `track_width` | min/opt/max | opt→router default width |
| `track_angle` | min/max deg | Angle between connected segments |
| `track_segment_length` | min/max | Per segment or arc |
| `diff_pair_gap` | min/opt/max | opt→router gap for new pairs; not tested on non-parallel fan-out. `diff_pair_gap_out_of_range` |
| `diff_pair_uncoupled` | max | Uncoupled = not parallel or outside the gap range. Tuning patterns excluded since 10.0.4. `diff_pair_uncoupled_length_too_long` |
| `length` | min/opt/max, **len or time** | opt→tuner target; per net or per `fromTo`. Time units force time-domain tuning. `length_out_of_range` |
| `skew` | min/opt/max + optional `(within_diff_pairs)`, **len or time** | Target is opt, else min, else 0. Without the option: skew across all matching nets (bus). With it: within each pair. `skew_out_of_range` |
| `solder_mask_expansion` | opt | Pads, shapes, tracks |
| `solder_mask_sliver` | generic parser path (the editor shows a minimum) | **Undocumented**. Editor label "Minimum soldermask silver" [sic]. No dedicated key found |
| `solder_paste_abs_margin` / `solder_paste_rel_margin` | opt | Final value = absolute + relative |
| `bridged_mask` | none | With severity → `solder_mask_bridge` |
| `text_height` / `text_thickness` | min/max | Includes text boxes |
| `zone_connection` | `solid`/`thermal_reliefs`/`none` | Sets pad-to-zone connection |
| `thermal_relief_gap` / `thermal_spoke_width` | min / opt | Fill geometry |
| `min_resolved_spokes` | bare integer 0–4 | `starved_thermal` |
| `assertion` | `"bool expr"` | `assertion_failure`. The graphical "Permitted layers" and "Allowed orientation" compile to it |
| Deprecated aliases | `mechanical_clearance`→`physical_clearance`, `mechanical_hole_clearance`→`physical_hole_clearance`, `hole`→`hole_size` | Accepted with a warning |

- `DIFF_PAIR_INTRA_SKEW_CONSTRAINT` exists in the enum, but no keyword creates it ([drc_rule.h](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule.h)).

### Master-only (KiCad 11 development)
| Constraint | Notes |
|---|---|
| `microvia_stack_depth` (max) | Keys `microvia_stack_depth`, `malformed_microvia_stack_span`, `microvia_crosses_core`, `microvia_stack_not_filled` |
| `hole_aspect_ratio` (max; proto stores thousandths) | Renamed 2026-10-12; applies to every plated hole. Master docs still say `microvia_aspect_ratio`, which the parser does not accept |
| `net_chain_length`, `stub_length` (min/opt/max; time units OK) | Net chains; undocumented |
| `return_path` | `(constraint return_path (layer "B.Cu") (net "GND"))` → `net_chain_return_path`. KiCad's first native reference-plane check |

Master-only functions: `customProperty`, `hasCustomProperty`, `hasNetChain`, `inNetChain`, `inNetChainClass`, `isStackedVia` [P] ([pcbexpr_functions.cpp @master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/pcbexpr_functions.cpp)).

### Functions (10.0)
Source: [pcbexpr_functions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcbexpr_functions.cpp) [P].
- **Areas:** `enclosedByArea('x')` (entire object; slower), `intersectsArea('x')` (any part; uses the fill for filled zones), `intersectsKeepout('x')` (**undocumented**; the same implementation with a keepout flag).
- **Paths and layers:** `existsOnLayer('L')`; `fromTo('U1-C5','U2-D3')` (`RefDes-Pad` or `RefDes`; `*`/`?` wildcards; case-insensitive; the path must be uniquely determinable).
- **Fields and classes:** `getField('x')` (footprints only); `hasComponentClass('x')` (the object **or its parent footprint**); `hasNetclass('x')`; `hasExactNetclass('x')`.
- **Diff pairs:** `inDiffPair('base')` (valid pairs only; false if the complement net is missing); `isCoupledDiffPair()` (AB).
- **Courtyards:** `intersectsCourtyard`, `intersectsFrontCourtyard`, `intersectsBackCourtyard` (refdes wildcard, `lib:fp` wildcard or `${Class:Name}`).
- **Vias and holes:** `isBlindVia`, `isBuriedVia`, `isBlindBuriedVia`, `isMicroVia`, `isPlated`.
- **Membership:** `memberOfGroup`, `memberOfFootprint`, `memberOfSheet` (exact path), `memberOfSheetOrChildren`.
- **Deprecated** (still registered): `insideArea`, `insideCourtyard`, `insideFrontCourtyard`, `insideBackCourtyard`, `memberOf`.
- **Component classes:** `A.ComponentClass == '…'` and `Component_Class` both resolve (corrected, VK) [P].

### Properties
- **Resolution rule:** any `PROPERTY` registered on a `BOARD_ITEM` subclass can be read, with `_` standing for a space (case-insensitive). `NetClass` (a priority-ordered comma list; equality matches any member or the full list), `ComponentClass`, `NetName` and `Type` have fast paths [P].
- **Documented:**
  - Common: `Layer`, `Locked`, `Parent`, `Position_X/Y`, `Type`.
  - Footprint (inherited by children): `Reference`, `Value`, `Orientation`, `Component_Class`, `Do_not_Populate`, `Keywords`, `Library_Link`, `Clearance_Override`, `Exempt_From_Courtyard_Requirement`, …
  - Pad: `Pad_Number`, `Pad_Type`, `Pin_Name`, `Pin_Type` (`+no_connect`), `Size_X/Y`, `Hole_Size_X/Y`, `Pad_To_Die_Length`.
  - Track: `Width`, `Start/End_X/Y`. Via: `Diameter`, `Hole`, `Layer_Top/Bottom`, `Via_Type`.
  - Tuning pattern: `Target_Length`, `Target_Skew`. Zone: `Name`, `Priority` [P].
- **Undocumented in 10.0 source:** `Pad_To_Die_Delay`, backdrill and post-machining properties, `Hole_Shape`; via tenting, plugging, filling and capping; zone `Keep_Out_Tracks/Vias/Pads/Zone_Fills/Footprints`, `Source_Type`/`Source_Name` (the multichannel source), `Remove_Islands`, `Minimum_Island_Area`; `Target_Skew_Delay` [P].

### Diff-pair naming rule (router and DRC share it)
- The matcher scans from the end of the net name, **skips `[0-9_]`**, then needs uppercase `+`, `-`, `P` or `N`. The complement swaps that character and keeps the skipped suffix.
- So `LANE_P_0`↔`LANE_N_0` and `USB_DP`↔`USB_DN` pair; lowercase `p`/`n` is not recognized.
- **`XTAL_P`/`XTAL_N` is paired too, a false-positive hazard** (corrected, VK) [P] ([drc_engine.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp)).

### Graphical rule editor and tuning profiles (10.0)
- **Graphical editor:** Tools → Design Rule Editor, writing the same `.kicad_dru` file.
  - Categories: Electrical, Manufacturability, Highspeed, Footprints (permitted layers, allowed orientation 0/90/180/270, vias under SMD) and Custom.
  - Condition rows (Any, Net, Netclass, Within Area, Custom Query) combine left to right with AND, OR, AND NOT or OR NOT.
  - 10.0.7 fixed it "breaking time domain rules" [P].
- **Tuning profiles:**
  - Single or Differential. Per signal layer: track width, unit delay (e.g. ps/mm) and diff gap. Vias: a global delay plus per-layer-pair overrides. Assigned per net class.
  - The router uses the profile's width and gap; the tuner uses its delays when "Enable time domain tuning" is set.
  - DRC keys `missing_tuning_profile`, `tuning_profile_track_geometries`.
  - A `length` or `skew` rule written in ps "will force the length tuner into time-domain mode … regardless of the tuning profile setting".
  - 10.0.5: profiles no longer always imply time domain. 10.0.7: a length tolerance may be as large as the optimum [P] ([pcbnew_create_board.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_create_board.adoc)).

### Verified syntax (10.0 doc examples plus parser)
```lisp
(version 1)
(rule "DDR_CLK len" (condition "A.fromTo('U1-C5','U2-D3')") (constraint length (min 20mm) (max 25mm)))
(rule "USB delay"   (condition "A.inDiffPair('/USB')") (constraint length (max 500ps)))
(rule "DQ skew"     (condition "A.fromTo('U1-A*','U2-B*')") (constraint skew (max 0.2mm)))
(rule "USB intra"   (condition "A.inDiffPair('/USB*')") (constraint skew (max 5ps) (within_diff_pairs)))
(rule "Clock gap"   (condition "A.inDiffPair('/CLK')") (constraint diff_pair_gap (min 0.12mm) (opt 0.15mm) (max 0.2mm)) (constraint diff_pair_uncoupled (max 3mm)))
(rule "DP clearance" (condition "A.inDiffPair('*') && !AB.isCoupledDiffPair()") (constraint clearance (min 1.5mm)))
(rule "HS vias"     (condition "A.hasNetclass('HS')") (constraint via_count (max 2)))
(rule front_courtyard_to_edge (layer "F.Courtyard") (condition "B.Layer == 'Edge.Cuts'") (constraint physical_clearance (min 3mm)))
(rule "TP spacing"  (condition "A.Reference == 'TP*' && B.Reference == 'TP*'") (constraint courtyard_clearance (min 1.5mm)))
```

## Recommendations for our system
- **Compiler rules** [I, from VK]:
  1. Put all predicates into one `condition` with explicit parentheses.
  2. Use one constraint type per rule.
  3. Emit general rules first, specific rules last.
  4. Emit only `mm`, `deg` and `ps`.
  5. Use stable `IR:<id>:<slug>` rule names. Feedback mapping is in [drc-report-and-repair-loop.md](drc-report-and-repair-loop.md).
  6. Write fab minimums into Board Setup (`.kicad_pro`) so net-class values and overrides are floored there, and clamp every emitted rule to the fab floor in the compiler, because a matching custom rule bypasses the board minimum. Audit pad and footprint `Clearance_Override` values, which beat compiled rules.
- **High-speed classes, time-domain first:** a tuning profile per net class (on 10.x the profiles must exist in `.kicad_pro`: 10.0 IPC has no call that creates them, and the net class's `tuning_profile` field, settable via `SetNetClasses` since 10.0.0, only names one; kipy 0.8.x cannot call `SetNetClasses`) [P] ([project_settings.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/types/project_settings.proto)), plus `length`/`skew` in ps with `(within_diff_pairs)`. DeepPCB and Quilter explicitly leave this space open [I].
- **Compile placement intent into native DRC** where possible: courtyard spacing; `assertion` on `Layer` and `Orientation`; `enclosedByArea`/`intersectsArea` against named rule areas; component classes; edge and keepout rules. Build our own checker only for pairwise distance, alignment, symmetry, loop area, and return path on 10.x [I].
- **Re-target return-path checks** to master's `return_path` if it ships in 11.0. Keep a second emitter for the KiCad 11 `CustomRule` proto ([ipc-api-10-vs-11.md](ipc-api-10-vs-11.md)) [I].
- **Never trust net names alone for diff pairs.** Confirm detected pairs, e.g. against XTAL false positives [I].

## Conflicts and open questions
- The docs list `th`, `"` and `rad`, but the 10.0 and master resolvers reject them. This comes from source reading only; nobody ran KiCad.
- How does `solder_mask_sliver` report? Unknown.
- Net-chain semantics on master are undocumented; only the parser and proto were read.
- When does the GUI reload an externally edited `.kicad_dru`? The docs say the file "should not be edited with an external text editor".

## Sources
- research notes:
  - [verification_kicad_and_tools.md § 1 (#14–18, #39–40), § 2.1–2.8, § 2.10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - this corrects [constraints_verification_benchmarks.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md) and [netlist_datasheet_understanding.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)
- primary: [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp), [@master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/drc/drc_rule_parser.cpp), [drc_rules.keywords @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/drc_rules.keywords), [10.0.4 notes](https://www.kicad.org/blog/2026/06/KiCad-10.0.4-Release/), [10.0.7 notes](https://www.kicad.org/blog/2026/10/KiCad-10.0.7-Release/)

See also: [drc-report-and-repair-loop.md](drc-report-and-repair-loop.md), [kicad-cli.md](kicad-cli.md), [built-in-automation-features.md](built-in-automation-features.md)
