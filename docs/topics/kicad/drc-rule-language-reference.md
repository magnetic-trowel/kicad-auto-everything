# KiCad 10 custom DRC rule language (.kicad_dru)

Scope: grammar, evaluation order, clearance resolution, constraints, functions, properties, diff-pair naming, tuning profiles, compiler rules for `.kicad_dru` on 10.0 (master noted). Not here: violation reports -> [drc-report-and-repair-loop.md](drc-report-and-repair-loop.md); KiCad 11 `CustomRule` proto -> [ipc-api-10-vs-11.md](ipc-api-10-vs-11.md#coverage-matrix).
Keys: kicad_dru, custom rules, constraint keywords, condition, severity, layer clause, operator precedence, clearance resolution, net tie, Clearance_Override, board minimum, units, time domain, ps, fs, physical_clearance, solder_mask_sliver, intersectsKeepout, fromTo, inDiffPair, diff-pair naming, XTAL false positive, tuning profile, graphical rule editor, hole_aspect_ratio, return_path, net chain, constraint compiler

**10.0 parses:** 35 constraint keywords (34 documented + undocumented `solder_mask_sliver`), 3 deprecated aliases, 23 current functions (incl. undocumented `intersectsKeepout`) + 5 deprecated, any registered item property, 4 severities + a `layer` clause [P]. Sources: [pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc) ([rendered](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom-design-rules)), [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp), [drc_rules.keywords @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/drc_rules.keywords) [P].

## Grammar and evaluation
- **File:** `<project>.kicad_dru`, starts `(version 1)` ("As of KiCad 10.0, the version is `1`"); `#` comments; `${var}` substituted before parsing (object-dependent `${LAYER}` → syntax error); top level allows only `version` and `rule`.
- **Rule:** `(rule <name> [(severity error|warning|ignore|exclusion)] [(layer <L>|outer|inner)] [(condition "<expr>")] (constraint <type> …)…)`.
- **Parser gotchas:**
  1. A second `condition` silently **overwrites** the first.
  2. A second `layer` clause is an error.
  3. A repeated constraint type raises "Rule already has a '%s' constraint" (one per type per rule).
- **Order:** rules are "evaluated in reverse order", first match wins → the **last** matching rule wins; put specific rules later. Exceptions in *Clearance resolution*.
- **Severity `ignore`:** still evaluated, "can still override previous rules". The interactive router does **not** observe `ignore`; it observes error, warning, exclusion.
- **Conditions:** `A` and `B` tested in both orders; `AB.` for pair functions. Booleans are bare (`A.Do_not_populate`); no `true`/`false` literals; `null` is comparable. Unitless value = nm (degrees for angles).
- **Precedence, lowest → highest:** `&&` < `||` < comparisons (`== != > >= < <=`, non-associative) < `!` < `+ -` < `* /`. So `a && b || c` = `a && (b || c)` (reverse of C) and `!x == y` = `(!x) == y`. The 10.0 user doc ("All the boolean operators have the same precedence and are evaluated in order from left to right") is wrong; always parenthesise (corrected) [P] ([grammar.lemon @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/libeval_compiler/grammar.lemon)).
- **Component classes:** separate parser `ParseComponentClassAssignmentRules` for `(assign_component_class <name> (condition …))` (Board Setup assignment).

## Units
- Accepted only `mm, mil, in, deg, ps, fs`; resolver error "must be mm, in, mil, deg, fs, or ps". The documented `th`, `"` and `rad` are rejected by the source (source reading only; nobody ran KiCad) [P].
- Time units only in `length` and `skew` (corrected, VK); elsewhere "Time based units not allowed for constraint type"; mixing → "Mixed units" [P] ([pcbexpr_evaluator.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcbexpr_evaluator.cpp)).

## Clearance resolution
`DRC_ENGINE::EvalRules` [P] ([drc_engine.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp)):
1. Footprint net tie → clearance 0 (source "net tie").
2. Pad/footprint overrides (`Clearance_Override`) beat every custom rule; floored at Board Setup minimum clearance (hole-clearance overrides at minimum hole clearance).
3. Else the last matching custom rule's value, **as is, no board-minimum floor** (a negative `min` still allows overlap).
4. No matching rule → net-class value maxed with local clearances (e.g. zones), floored at the board minimum; implicit diff-pair gaps floored the same. Source names the net class, the local item or "board minimum".

→ the violation `<source>` is a rule name only in case 3 ([report](drc-report-and-repair-loop.md#rule-name-protocol)).

## Constraints parsed in 10.0
"opt→router" = the interactive router or length tuner uses `opt`. Keys = DRC JSON `type` ([drc_item.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_item.cpp)) [P].

| Constraint | Args / units | Notes, DRC key(s) |
|---|---|---|
| `clearance` | min; negative allows overlap | Router honours; **different nets only**. `clearance`, `hole_clearance`, `shorting_items`, `tracks_crossing`, `zones_intersect` |
| `physical_clearance` | min | Net-agnostic; same layer only except Edge.Cuts (all layers); "much slower". **Reported as `clearance`/`hole_clearance`.** Router since 10.0.4 |
| `physical_hole_clearance` | min | Round holes only ("drilling tolerance"); router since 10.0.4; `hole_clearance` |
| `hole_clearance` | min | Drilled hole to copper of another net |
| `edge_clearance` | min; negative allowed | Edge = Edge.Cuts **and oval pad holes** ("milling tolerance"). `copper_edge_clearance`, `silk_edge_clearance` |
| `courtyard_clearance` | min; negative allowed | No courtyard → no error. `courtyards_overlap` (+ `missing_courtyard`, `malformed_courtyard`, `pth_`/`npth_inside_courtyard`) |
| `creepage` | min | Surface path between nets |
| `connection_width` | min | Narrowest copper incl. zone necks |
| `silk_clearance` | min; negative allowed | `silk_overlap`, `silk_over_copper` |
| `hole_size` | min/opt/max | opt→router default drill; oval: minor axis vs min, major vs max. `drill_out_of_range`, `microvia_drill_out_of_range` |
| `hole_to_hole` | min | Mechanical drills only (laser, milled not checked). `hole_to_hole`, `holes_co_located` |
| `annular_width` | min/max | Vias and pads |
| `via_diameter` | min/opt/max | opt→router default |
| `via_count` | min/max, unitless | Per net or per `fromTo` → `too_many_vias`; diff-pair and matched-length providers also emit it |
| `via_dangling` | none | Use with `severity` |
| `disallow` | `track via through_via blind_via buried_via micro_via pad zone text graphic hole footprint` | `via` = **all** via types. `items_not_allowed`, `text_on_edge_cuts` |
| `track_width` | min/opt/max | opt→router default width |
| `track_angle` | min/max deg | Angle between connected segments (in 10.0, corrected VK) |
| `track_segment_length` | min/max | Per segment or arc (in 10.0) |
| `diff_pair_gap` | min/opt/max | opt→router gap for new pairs; not tested on non-parallel fan-out. `diff_pair_gap_out_of_range` |
| `diff_pair_uncoupled` | max | Uncoupled = not parallel or outside gap range; tuning patterns excluded since 10.0.4. `diff_pair_uncoupled_length_too_long` |
| `length` | min/opt/max, **len or time** | opt→tuner target; per net or `fromTo`; time units force time-domain tuning. `length_out_of_range` |
| `skew` | min/opt/max + optional `(within_diff_pairs)`, **len or time** | Target opt, else min, else 0. Without option: across all matching nets (bus); with: within each pair. `skew_out_of_range` |
| `solder_mask_expansion` | opt | Pads, shapes, tracks |
| `solder_mask_sliver` | generic parser path (editor shows a minimum) | **Undocumented**; editor label "Minimum soldermask silver" [sic]; no dedicated key found |
| `solder_paste_abs_margin` / `solder_paste_rel_margin` | opt | Final = absolute + relative |
| `bridged_mask` | none | With severity → `solder_mask_bridge` |
| `text_height` / `text_thickness` | min/max | Includes text boxes |
| `zone_connection` | `solid`/`thermal_reliefs`/`none` | Pad-to-zone connection |
| `thermal_relief_gap` / `thermal_spoke_width` | min / opt | Fill geometry |
| `min_resolved_spokes` | bare integer 0–4 | `starved_thermal` |
| `assertion` | `"bool expr"` | `assertion_failure`; graphical "Permitted layers" and "Allowed orientation" compile to it |
| Deprecated aliases | `mechanical_clearance`→`physical_clearance`, `mechanical_hole_clearance`→`physical_hole_clearance`, `hole`→`hole_size` | Accepted with a warning |

`DIFF_PAIR_INTRA_SKEW_CONSTRAINT` exists in the enum, no keyword creates it ([drc_rule.h](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule.h)).

## Master-only constraints (KiCad 11 development)
| Constraint | Notes |
|---|---|
| `microvia_stack_depth` (max) | Keys `microvia_stack_depth`, `malformed_microvia_stack_span`, `microvia_crosses_core`, `microvia_stack_not_filled` |
| `hole_aspect_ratio` (max; proto stores thousandths) | Renamed 2026-10-12; every plated hole. Master docs still say `microvia_aspect_ratio`, which the parser rejects |
| `net_chain_length`, `stub_length` (min/opt/max; time OK) | Net chains; undocumented (only parser and proto read) |
| `return_path` | `(constraint return_path (layer "B.Cu") (net "GND"))` → `net_chain_return_path`; KiCad's first native reference-plane check. Re-target our return-path checks to it if it ships in 11.0 [I] |

Master-only functions: `customProperty`, `hasCustomProperty`, `hasNetChain`, `inNetChain`, `inNetChainClass`, `isStackedVia` [P] ([pcbexpr_functions.cpp @master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/pcbexpr_functions.cpp); [parser @master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/drc/drc_rule_parser.cpp)).

## Functions (10.0)
Source: [pcbexpr_functions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcbexpr_functions.cpp) [P].
| Group | Functions |
|---|---|
| Areas | `enclosedByArea('x')` (entire object; slower), `intersectsArea('x')` (any part; fill for filled zones), `intersectsKeepout('x')` (**undocumented**; same code with keepout flag) |
| Paths, layers | `existsOnLayer('L')`; `fromTo('U1-C5','U2-D3')` (`RefDes-Pad` or `RefDes`; `*`/`?` wildcards; case-insensitive; path must be uniquely determinable) |
| Fields, classes | `getField('x')` (footprints only); `hasComponentClass('x')` (object **or parent footprint**); `hasNetclass('x')`; `hasExactNetclass('x')`; `A.ComponentClass == '…'` and `Component_Class` both resolve (corrected, VK) |
| Diff pairs | `inDiffPair('base')` (valid pairs only; false if complement missing); `isCoupledDiffPair()` (AB) |
| Courtyards | `intersectsCourtyard`, `intersectsFrontCourtyard`, `intersectsBackCourtyard` (refdes wildcard, `lib:fp` wildcard or `${Class:Name}`) |
| Vias, holes | `isBlindVia`, `isBuriedVia`, `isBlindBuriedVia`, `isMicroVia`, `isPlated` |
| Membership | `memberOfGroup`, `memberOfFootprint`, `memberOfSheet` (exact path), `memberOfSheetOrChildren` |
| Deprecated (still registered) | `insideArea`, `insideCourtyard`, `insideFrontCourtyard`, `insideBackCourtyard`, `memberOf` |

## Properties
- **Rule:** any `PROPERTY` registered on a `BOARD_ITEM` subclass is readable, `_` for space, case-insensitive. Fast paths: `NetClass` (priority-ordered comma list; equality matches any member or the full list), `ComponentClass`, `NetName`, `Type` [P].
- **Documented:** common `Layer`, `Locked`, `Parent`, `Position_X/Y`, `Type`; footprint (inherited by children) `Reference`, `Value`, `Orientation`, `Component_Class`, `Do_not_Populate`, `Keywords`, `Library_Link`, `Clearance_Override`, `Exempt_From_Courtyard_Requirement`, …; pad `Pad_Number`, `Pad_Type`, `Pin_Name`, `Pin_Type` (`+no_connect`), `Size_X/Y`, `Hole_Size_X/Y`, `Pad_To_Die_Length`; track `Width`, `Start/End_X/Y`; via `Diameter`, `Hole`, `Layer_Top/Bottom`, `Via_Type`; tuning pattern `Target_Length`, `Target_Skew`; zone `Name`, `Priority` [P].
- **Undocumented in 10.0 source:** `Pad_To_Die_Delay`, backdrill and post-machining properties, `Hole_Shape`; via tenting, plugging, filling, capping; zone `Keep_Out_Tracks/Vias/Pads/Zone_Fills/Footprints`, `Source_Type`/`Source_Name` (multichannel source), `Remove_Islands`, `Minimum_Island_Area`; `Target_Skew_Delay` [P].

## Diff-pair naming rule (router and DRC share it)
- Scan from the end of the net name, **skip `[0-9_]`**, then require uppercase `+`, `-`, `P` or `N`; the complement swaps that character and keeps the skipped suffix.
- `LANE_P_0`↔`LANE_N_0`, `USB_DP`↔`USB_DN` pair; lowercase `p`/`n` not recognized.
- **`XTAL_P`/`XTAL_N` pairs too: false-positive hazard** (corrected, VK) [P] ([drc_engine.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp)). Never trust net names alone; confirm detected pairs [I].

## Graphical rule editor and tuning profiles (10.0)
- **Editor:** Tools → Design Rule Editor, writes the same `.kicad_dru`. Categories Electrical, Manufacturability, Highspeed, Footprints (permitted layers, allowed orientation 0/90/180/270, vias under SMD), Custom. Condition rows (Any, Net, Netclass, Within Area, Custom Query) combine left to right with AND, OR, AND NOT, OR NOT. 10.0.7 fixed it "breaking time domain rules" [P] ([10.0.7 notes](https://www.kicad.org/blog/2026/10/KiCad-10.0.7-Release/)).
- **Tuning profiles:** Single or Differential; per signal layer: track width, unit delay (e.g. ps/mm), diff gap; vias: global delay + per-layer-pair overrides; assigned per net class. Router uses the profile's width and gap; tuner uses its delays when "Enable time domain tuning" is set. DRC keys `missing_tuning_profile`, `tuning_profile_track_geometries`. A `length`/`skew` rule in ps "will force the length tuner into time-domain mode … regardless of the tuning profile setting". 10.0.5: profiles no longer always imply time domain; 10.0.7: length tolerance may equal the optimum [P] ([pcbnew_create_board.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_create_board.adoc); [10.0.4 notes](https://www.kicad.org/blog/2026/06/KiCad-10.0.4-Release/)).
- **Profiles on 10.x must exist in `.kicad_pro`:** 10.0 IPC has no call that creates them; the net class's `tuning_profile` field (settable via `SetNetClasses` since 10.0.0) only names one; kipy 0.8.x cannot call `SetNetClasses` [P] ([project_settings.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/types/project_settings.proto)).

## Verified syntax (10.0 doc examples + parser)
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

## Compiler rules
[I, from VK]
1. All predicates in one `condition` with explicit parentheses.
2. One constraint type per rule.
3. General rules first, specific last.
4. Emit only `mm`, `deg`, `ps`.
5. Stable `IR:<id>:<slug>` names ([feedback mapping](drc-report-and-repair-loop.md#rule-name-protocol)).
6. Write fab minimums into Board Setup (`.kicad_pro`) and clamp every emitted rule to the fab floor in the compiler (a matching custom rule bypasses the board minimum); audit `Clearance_Override` values, which beat compiled rules.
7. High-speed classes time-domain first: a tuning profile per net class in `.kicad_pro`, plus `length`/`skew` in ps with `(within_diff_pairs)`. DeepPCB and Quilter explicitly leave this space open [I].
8. Compile placement intent into native DRC where possible: courtyard spacing; `assertion` on `Layer`/`Orientation`; `enclosedByArea`/`intersectsArea` against named rule areas; component classes; edge and keepout rules.
9. **DRC cannot express** pairwise pad distance between two footprints, alignment, symmetry, loop area, and (on 10.x) return path → our own checker [P/I].
10. Keep a second emitter for the KiCad 11 `CustomRule` proto.

## Open questions
- `th`, `"`, `rad`: listed in docs, rejected by 10.0 and master resolvers (source reading only).
- How does `solder_mask_sliver` report? Unknown.
- Net-chain semantics on master undocumented.
- When does the GUI reload an externally edited `.kicad_dru`? Docs: the file "should not be edited with an external text editor".

## Sources
- [verification_kicad_and_tools.md § 1 (#14–18, #39–40), § 2.1–2.8, § 2.10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); corrects [constraints_verification_benchmarks.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md) and [netlist_datasheet_understanding.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)
