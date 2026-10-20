# Infrastructure to evaluate, verify and constrain automated PCB layouts: constraint/intent IRs, open-source physics and verification tools, quality metrics, benchmarks and datasets (for an LLM-driven KiCad placer and router)

Research date: 2026-10-20. **Method and source caveats (read first):**
- This session's egress proxy blocked many primary hosts: docs.kicad.org, arxiv.org, antmicro.com, docs.atopile.io, docs.jitx.com, docs.tscircuit.com, docs.quilter.ai, iclr.cc, omnieda.com and forum.kicad.info. For KiCad I worked around the block by reading the **KiCad documentation sources on GitLab** (`kicad-doc` master branch, which documents KiCad 10 and current development) and the **KiCad source tree on GitLab**. For GitHub projects I read READMEs and docs directly. Facts about pages on blocked hosts come from search-engine result summaries, and each one is marked "(via search summary)". Treat those as secondary.
- The shared web-search budget ran out partway through. Topics I could not search afterwards are listed under Gaps: ISPD/ICCAD contests, Cypress, Elmer thermal flows in detail, Allegro and Altium syntax specifics, the IPC-2581 constraint schema, and academic "design intent" literature.
- GitHub star counts are point-in-time values from 2026-10-20 fetches. They differ between sources, which is noted where it happens.

---

## Q1. How can design constraints and intent be represented formally and fed to optimizers and LLMs? (KiCad rules language, net and component classes, rule areas, industry constraint managers, exchange formats, code-first EDA, analog constraint formats, IR design)

### Takeaway
KiCad 10's `.kicad_dru` language is a capable **checking** language. Its condition predicates over pairs of objects (A/B) cover area, courtyard, net class, component class, sheet, group, diff pair and `fromTo` path. Its constraints cover clearance, width, length, skew, diff-pair gap and uncoupled length, via count, and creepage, and arbitrary `assertion`s are allowed. What it lacks is a vocabulary for **placement relations** such as "within X mm of pin", "aligned", "symmetric", "ordered" or "edge-of-board", and for **physics objectives** such as loop area, IR drop and temperature. Those concepts exist elsewhere:
- analog layout formats (ALIGN's typed JSON constraints, split into hard and soft),
- code-first EDA (tscircuit `calc()`/anchors/`<constraint>`; JITX SI constraints over topologies),
- recent open-source intent files (the KiCadRoutingTools `floorplan-intent.json` with `proximity[]`, `decaps`, `edge_connectors`, `blocks/zones` and `keep_away`).

A good IR should combine these. It should **compile** down to `.kicad_dru` wherever possible and to custom checkers and optimizer penalties everywhere else.

### Cited Findings

**KiCad custom DRC rules (KiCad 10 / master docs)**
- Rules live in a separate `<project>.kicad_dru` file. The language is s-expression based, and the file must start with `(version 1)`, which is the version as of KiCad 10.0. Rules are evaluated in **reverse order**: the last matching rule wins, so specific rules belong at the end of the file. The rule form is `(rule <name> [(severity …)] [(layer …)] [(condition "<expr>")] (constraint <type> …))`. Text variables such as `${hv_clearance}` are substituted in a preprocessing step. — [KiCad docs source: pcbnew_advanced.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc)
- The `layer` clause accepts any layer name, `outer` or `inner`. Severity is `error`, `warning`, `ignore` or `exclusion`. A rule set to `ignore` is still evaluated and can still override earlier rules. Error, warning and excluded rules are all observed by the interactive router. — [pcbnew_advanced.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc)
- Conditions are boolean expressions over objects `A` and `B`; some functions use `AB`. Operators are `== != > >= < <= && || !`, all with equal precedence and evaluated left to right. Units are `mm`, `mil`/`th`, `in`, `deg` and `rad`, and simple math such as `1.0mm + 0.1mm` is allowed. Nullable properties are compared with `null`. — [pcbnew_advanced.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc)
- **Constraint types documented** in master: `annular_width`, `assertion` (an arbitrary boolean expression that must hold), `bridged_mask`, `clearance` (a negative min allows collision), `connection_width`, `courtyard_clearance`, `creepage`, `diff_pair_gap` (min/opt/max; opt is the router default), `diff_pair_uncoupled` (max), `disallow` (track, via, through_via, micro_via, blind_via, buried_via, pad, zone, text, graphic, hole, footprint), `edge_clearance`, `hole_clearance`, `hole_size`, `hole_to_hole`, `length` (min/opt/max; opt is the length-tuner target), `microvia_aspect_ratio`, `microvia_stack_depth`, `min_resolved_spokes`, `physical_clearance` (net-agnostic and "much slower"), `physical_hole_clearance`, `silk_clearance`, `skew` (min/opt/max, with optional `within_diff_pairs`), `solder_mask_expansion`, `solder_paste_abs_margin`, `solder_paste_rel_margin`, `text_height`, `text_thickness`, `thermal_relief_gap`, `thermal_spoke_width`, `track_angle`, `track_segment_length`, `track_width` (opt is the router default), `via_count` (min/max per net), `via_dangling`, `via_diameter`, and `zone_connection`. — [pcbnew_advanced.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc). (Some entries, for example `microvia_*`, `track_angle`, `track_segment_length` and `isStackedVia`, may be KiCad 10 or development-only. The master docs do not tag each one with a version.)
- **Expression functions**: `enclosedByArea`, `existsOnLayer`, `fromTo('x','y')` (copper path between pads, named `RefDes-PadNumber` such as `'U1-A5'`, or `RefDes` for all of a part's pads), `getField`, `hasComponentClass`, `hasExactNetclass`, `hasNetclass`, `inDiffPair`, `insideArea`, `insideCourtyard`, `intersectsArea`, `intersectsCourtyard`, `isBlindVia`, `isBuriedVia`, `isBlindBuriedVia`, `isCoupledDiffPair` (AB), `isMicroVia`, `isPlated`, `isStackedVia`, `memberOf`, `memberOfGroup`, `memberOfFootprint`, `memberOfSheet`, `memberOfSheetOrChildren`. Courtyard and area functions also accept `${Class:Name}` to mean "any footprint of component class Name". `fromTo()` is documented as most commonly used with `length`, `skew`, `track_width`, `clearance` and `diff_pair_gap`. — [pcbnew_advanced.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc)
- Object properties include `Layer`, `Locked`, `Parent`, `Position_X` and `Position_Y`. Positions are measured at the footprint origin, which may not be the courtyard center. Other properties are `NetClass` (a comma-joined multi-class string, matched if any class matches), `Component_Class`, `Reference` and `Do_not_populate`. — [pcbnew_advanced.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc)
- **Graphical rule editor (KiCad 10)**: Tools → Design Rule Editor writes the same `.kicad_dru` file as the text editor. Its categories are Electrical, Manufacturability, Highspeed (routing width, max via count, diff-pair skew, matched length with gap, absolute length) and Footprints (permitted layers, allowed orientation, vias under SMD). "Permitted layers" and "Allowed orientation" are implemented internally as `assertion` constraints, and their violations report as "Assertion violation". — [pcbnew_advanced.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc). KiCad 10.0 was released in March 2026 with the graphical rule editor, a track-tuning revamp and design variants. — [KiCad 10.0.0 release post](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/); [Tech Explorations review](https://techexplorations.com/kicad/kicad-10-review-new-features-high-speed-tuning-variants-and-more/) (via search summary)
- **Component classes** are named groups of components. They are assigned in the schematic or by Board Setup rules, and they apply to both symbols and footprints. One component can have several classes. Automatic assignment conditions are Reference (with wildcards), Footprint, Side, Rotation, Footprint Field Value, Sheet, and Custom Expression (any DRC condition, for example `A.intersectsArea('x')`). "Assign component class per sheet" creates one class per sheet automatically. — [pcbnew_create_board.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_create_board.adoc). A known pitfall is that `hasComponentClass` is true only for footprints and their children, so clearance rules need `insideCourtyard('${Class:X}')`-style workarounds. — [KiCad forum](https://forum.kicad.info/t/using-component-classes-for-custom-clearance-settings/57733) (via search summary)
- **Tuning profiles** (KiCad 10 Board Setup) define per-layer track width, diff-pair gap and **unit propagation delay**, plus via propagation delays with per-layer-pair overrides. Target impedance is optional. A profile is assigned to net classes, and the length tuner can tune in the **time domain**. DRC can optionally flag tracks that don't match their profile. — [pcbnew_create_board.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_create_board.adoc)
- **Rule areas** (formerly keepouts) are arbitrary polygons on selected layers with an optional name that DRC rules can reference. Their Keepouts tab can forbid tracks, vias, pads, zone fills and footprints. Their Placement tab defines **multichannel** channels, sourced from a sheet, a component class or a group. The Repeat Layout tool copies a manually placed and routed reference channel into the target rule areas. — [pcbnew_editing.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc); [pcbnew_multichannel.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc)

**Industry constraint managers and exchange formats**
- Altium decides where a rule applies by evaluating query-language expressions. For binary rules such as clearance, two queries run, one per object, and the default query is "All". Altium also offers an object-centric, spreadsheet-like Constraint Manager that is converted into the same rule format the PCB Rules and Constraints Editor uses. — [Altium: Scoping design rules](https://www.altium.com/jp/documentation/altium-designer/scoping-design-rules-ad); [Altium: Defining, scoping & managing design rules](https://www.altium.com/jp/documentation/altium-designer/pcb/defining-scoping-managing-design-rules) (via search summary). Altium "Rooms" are placement regions. — [Altium: Rooms](https://www.altium.com/documentation/altium-designer/pcb/rooms) (title only; details not verified)
- In the Cadence Allegro Constraint Manager (Constraint Compiler guide, 17.4-2019), DEFAULT Physical and Spacing Constraint Sets serve as starting points. A single rule specification containing width, line-to-line spacing and max length generates Physical, Spacing and Electrical CSets. — [Cadence PCB best practices / Constraint Compiler guide](https://resources.pcb.cadence.com/i/1180274/18) (via search summary)
- IPC-2581 Rev C, per secondary trade sources, can define impedance requirements at net, layer or stackup level, identify differential pairs, carry stackup thickness and tolerances, and includes a bidirectional DFX module for fabricator queries and responses. Some sources say the standard is being renamed IPC-DPMX. — [Sierra Circuits blog (Hemant Shah)](https://www.protoexpress.com/blog/ipc-2581-revision-c-facilitates-pcb-data-management-by-hemant-shah/); [PCD&F on the DFX module](https://pcdandf.com/pcdesign/index.php/editorial/menu-features/15219-new-dfx-module-for-ipc-2581-slices-design-manufacturing-time-errors) (via search summary)
- `kicad-cli` can export IPC-2581 (`pcb export ipc2581`, with BOM column mapping, version and units options) and ODB++ (`pcb export odb`). — [kicad-cli docs source](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/cli/cli.adoc)

**Code-first EDA constraint languages**
- **atopile**: `.ato` is "a declarative language for electronics: modules, interfaces, units, tolerances, and assertions". The compiler "solves constraints, picks parts, runs checks, and updates your KiCad layout". The project is MIT-licensed and has a `layout_reuse` example. — [atopile GitHub](https://github.com/atopile/atopile); [atopile examples tree](https://github.com/atopile/atopile/tree/main/examples). A third-party analysis describes interval arithmetic for tolerance propagation and hierarchical-address (`atopile_address`) matching to preserve layout across regenerations. — [kicad-tools atopile synthesis](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/atopile-research-synthesis.md)
- **JITX** layers three SI constraint kinds on top of net statements: timing, timing difference (skew) and insertion loss. **Routing structures** define per-layer width, spacing, velocity, loss, clearances and keepouts or via fences. `DiffPairConstraint` takes a skew window and a loss limit (a typical skew window is about 0 ±10 ps). Topologies are built with `>>`, for example `self += driver.out >> receiver.inp`. In the current runtime, each layer change is modelled as a fixed 20 ps and 0.15 dB. — [JITX SI constraints](https://docs.jitx.com/essentials/constraints.html); [jitx.si API](https://docs.jitx.com/en/4.0/api/jitx.si.html); [JITX topology](https://docs.jitx.com/essentials/topology.html) (via search summary)
- **tscircuit** props include `pcbX`, `pcbY`, `pcbRotation`, `pcbLeftEdgeX`/`RightEdgeX`/`TopEdgeY`/`BottomEdgeY`, `pcbOffsetX`/`Y`, `pcbPositionAnchor`, `pcbPositionMode` (`relative_to_group_anchor` | `auto` | `relative_to_board_anchor` | `relative_to_component_anchor`), `shouldBeOnEdgeOfBoard`, `pcbMargin*` and `pcbRelative`. Groups add CSS-like layout through `pcbGrid*`, `pcbFlex*`, `pcbPack` and `pcbLayout`, plus trace-level props `minTraceWidth` and `nominalTraceWidth`. — [tscircuit/props README](https://github.com/tscircuit/props). Relative placement also uses `calc()` expressions such as `pcbX="calc(R1.maxX + 2mm)"` and pad references such as `U1.pin1.x`. `<constraint />` elements set center-to-center or edge-to-edge distances and same-axis alignment. — [tscircuit relative positioning](https://docs.tscircuit.com/guides/tscircuit-essentials/relative-positioning); [tscircuit constraint element](https://docs.tscircuit.com/footprints/constraint); [constraint layout engine](https://docs.tscircuit.com/api-reference/layout-engines/constraint) (via search summary)
- **SKiDL** (MIT) describes circuits in Python and emits netlists, XML BOMs and editable KiCad 6–10 schematics, with its own `ERC()`. It has no layout-constraint language. — [SKiDL GitHub](https://github.com/devbisme/skidl)

**Analog layout constraint format (ALIGN)**
- ALIGN constraints are typed Pydantic models in `<hierarchy>.const.json` files. The base classes are `SoftConstraint`, `HardConstraint` and `UserConstraint`. A `HardConstraint` must implement `translate(solver)`, which yields math expressions for a solver backend. A `UserConstraint` expands into lower-level constraints, which separates user-facing constraints from place-and-route constraints. Types include `Order` (instances plus a direction such as `left_to_right`, with optional `abut`), `Align` (for example `line: v_center`), `Spread`, `AspectRatio`, `Boundary`, `AlignInOrder`, `Floorplan` (ordered regions), `PlaceSymmetric`, `CompactPlacement`, `SameTemplate`, `PlaceCloser`, `PlaceOnBoundary`, `PowerPorts`, `GroundPorts`, `ClockPorts`, `SymmetricBlocks` (pairs plus axis H or V), `BlockDistance`, `VerticalDistance`, `HorizontalDistance`, `GuardRing`, `GroupCaps`, `NetPriority`, `NetConst` (nets, shield net, criticality), `PortLocation`, `SymmetricNets`, `ChargeFlow`, `MultiConnection`, `DoNotRoute`, `Route` and `GroupBlocks`. An example is `{"constraint":"SymmetricBlocks","pairs":[["MN0","MN1"],["MN4"]],"direction":"V"}`. — [ALIGN constraint.py](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/master/align/schema/constraint.py); [ALIGN README](https://github.com/ALIGN-analoglayout/ALIGN-public)

**Open-source PCB "design intent" files (2026)**
- **KiCadRoutingTools `floorplan-intent.json`** (schema 1) uses these keys: `envelope` (read from the board, never authored), `blocks[]` (ref globs or sheet group, `zone` rect, `side`, `exclusive`, `rotation`, `rigid`), `keepouts[]` (rect or circle, sides, allow-list), `edge_connectors[]` (edge N/E/S/W, `overhang_mm` min/max, `center_on_edge` or `along_edge_band`), `decaps` (`max_distance_mm`, `max_pin_distance_mm`, `pin_functions`, `same_side`), `proximity[]` (`ref`, `near`, `max_mm`, `basis`: `pad_edge` or `body`, `pads`), `keep_away[]` (`AGGRESSOR:VICTIM:GAP`), `replicate[]`, `arrays[]`, `fixed_poses[]`, `must_lock`, `legality_budget` (overlap area, OoB count), `severity` (per rule) and `dispositions`. Unknown keys are **refused at load time** so that a typo can't silently drop a constraint. The intent has three roles: a construction source (`place_seed.py`), a **monotone hard per-move gate** inside the optimizer, and a rank gate. The docs give a measured example from the ulx3s board: an ungated quench "manufactures 4 `zone_containment` errors" and a gated one none. They warn that `--emit-intent` run on a damaged board records the damage as the requirement. — [KiCadRoutingTools floorplan-intent.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/floorplan-intent.md). The companion "design brief" records facts the board file can't contain, such as user-facing connectors and their edges, and compiles them into the intent. — [design-brief.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/design-brief.md)
- Quilter exposes "placement regions" as a user design parameter. — [Quilter docs: placement regions](https://docs.quilter.ai/design-parameters/placement-regions) (title only)

### Inferences
- **KiCad can already express part of "keep C5 within 2 mm of U1 pin 7 with via to GND plane" as a check.** `(rule "U1.7 decap" (condition "A.fromTo('U1-7','C5-1')") (constraint length (max 2mm)))` bounds the routed copper length on that pin-to-pad path. That is a routed-length proxy for proximity, and it is only meaningful after routing. An `assertion` on `Position_X`/`Position_Y` is single-object, so it cannot compare two footprints' positions, and footprint origins are not pad centers. There is no native "pad of A within d of pad of B" predicate and no "this pad has a via to plane P within d" predicate. Those need a custom checker. The IR should therefore compile each constraint into **(a)** a `.kicad_dru` rule where one exists, so the KiCad router and DRC enforce it, **(b)** a geometric checker for placement-time evaluation, and **(c)** a differentiable or penalty term for the optimizer.
- ALIGN's hard/soft split, plus `translate(solver)` and `UserConstraint` expansion, is a clean pattern. LLM-facing high-level intents such as "decouple U1" expand into low-level primitives (proximity, via-to-plane, loop area, same side), and each primitive knows how to emit solver terms and checker code.
- KiCadRoutingTools' strict-schema lesson matters for LLM-authored constraints. Reject unknown keys, track provenance (`source`, `context`, `dispositions`), and never auto-derive intent from a board under repair.
- Selectors should reuse KiCad's own vocabulary: refs and globs, `${Class:…}`, net class, sheet path, group, named rule area and `fromTo` pads. Then any IR selector can be rendered as a DRC `condition` string and checked with KiCad's evaluator.

### Gaps
- I could not read the IPC-2581 Rev C schema itself, so I could not confirm whether it carries generic layout constraints (clearance, length or skew rules) as opposed to stackup, impedance and DFX data. Only trade-press summaries were available. I also could not establish whether KiCad's IPC-2581 exporter emits impedance or diff-pair intent.
- Altium query function names (for example `InNetClass` and `WithinRoom`) and Allegro ECSet and topology syntax were not verified against primary docs.
- The academic literature on "design intent capture" for PCBs could not be searched after the budget ran out.
- I could not confirm exact atopile `assert … within …` syntax from primary docs, because docs.atopile.io was blocked and the example `.ato` paths returned 404.

---

## Q2. Which open-source or scriptable tools can score a layout beyond DRC (SI, PI, EMI, thermal, parasitics), which are fast enough for an optimization loop, and are there ML surrogates?

### Takeaway
There is a usable tiered stack:
1. **kicad-cli DRC** (JSON, exit codes, zone refill, schematic parity) for legality.
2. **Analytic and heuristic checkers**: decap distance, return-path and plane-split analysis, loop-area estimates, crosstalk proxies, and closed-form impedance (Transcalc models in KiCad's calculator). These are fast enough to run inside a loop.
3. **2.5D solvers** for DC IR drop (resistive-mesh plugins KiPIDA and KiPI) and 2D field solvers for Z0. These suit periodic checks.
4. **Full-wave and FEM** (openEMS via gerber2ems, PCB_SI_Toolkit or KiCad-Electrodynamic-Static-Studio, and SPIKE's extensions). These are for final verification only.

Most 2026 KiCad SI/PI/EMC plugins are alpha or community previews with little independent validation. ML surrogates for PCB SI exist mostly at the pre-layout or parameter level, not as layout-level EMI predictors.

### Cited Findings

**Legality and DRC**
- `kicad-cli pcb drc` takes `--format report|json`, `--severity-all|error|warning|exclusions`, `--schematic-parity`, `--all-track-errors`, `--units`, `--refill-zones` (with `--save-board`), `-D VAR=VALUE` and `--exit-code-violations` (exit 0 when clean, 5 when there are violations). — [kicad-cli docs source](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/cli/cli.adoc)
- The DRC JSON report schema (`drc.v1.json`) has these top-level fields: `source`, `date`, `kicad_version`, `violations[]`, `unconnected_items[]`, `schematic_parity[]`, `coordinate_units`, `included_severities`, `ignored_checks[]`. Each Violation has `type`, `description`, `severity`, `items[]` (each with `uuid`, `description`, `pos{x,y}`), `excluded` and `comment`. — [KiCad source: resources/schemas/drc.v1.json](https://gitlab.com/kicad/code/kicad/-/blob/master/resources/schemas/drc.v1.json)
- `kicad-cli pcb export stats --format json` reports board statistics. Other useful automation commands include `gerber diff --format json`, `pcb render` (images), `pcb export pos`, and STEP/GLB/VRML export. — [kicad-cli docs source](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/cli/cli.adoc)

**Impedance and transmission-line calculators**
- KiCad's PCB Calculator TransLine tool is "heavily based on Transcalc". It covers microstrip, CPW, grounded CPW, rectangular waveguide, coax, coupled microstrip, stripline and twisted pair, using frequency-dependent closed-form models (Atwater; Kirschning–Jansen). Via Size gives via electrical and thermal properties, and Track Width uses IPC-2221 for current versus temperature rise. — [pcb_calculator.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcb_calculator/pcb_calculator.adoc)
- KiCad 10 tuning profiles can calculate track geometry and unit delay from target impedance and stackup, and can drive time-domain length tuning. — [pcbnew_create_board.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_create_board.adoc)

**Full-wave EM (openEMS family)**
- openEMS is an open FDTD solver with graded 3D Cartesian and cylindrical meshes, multithreading and SIMD, Octave/Matlab and Python interfaces, dispersive materials, and vtk/hdf5 field dumps. — [openEMS-Project](https://github.com/thliebig/openEMS-Project)
- **gerber2ems** (Antmicro, Apache-2.0, 272★, 220 commits, copyright 2023–2026, no tagged releases) is a "Python interface to OpenEMS, for PCB trace simulation". It takes per-layer Gerbers, `stackup.json`, an Excellon PTH drill file, a `-pos.csv` with "SP"-prefixed port designators and a `simulation.json`, and outputs S-parameters and impedance CSVs, plots, and optional ParaView field exports. Its stated limits: capacitors are not simulated and must be modelled as shorts, terminated traces need ports or grounding, ports must be at least 8× the mesh cell, field exports can reach hundreds of GB, and it runs **one simulation per excited port**. — [gerber2ems](https://github.com/antmicro/gerber2ems)
- Antmicro's July 2025 update added trace propagation-delay estimation for checking intra-pair length matching, KiCad 9 support in the `kicad-si-simulation` wrapper (which defines a Region of Interest per simulation), adaptive grid generation, differential-pair simulation and `ems2paraview`. Antmicro says the flow now runs "mostly without manual tweaking". — [Antmicro blog 2025-07](https://antmicro.com/blog/2025/07/recent-improvements-to-antmicros-signal-integrity-simulation-flow) (via search summary). Earlier posts: [automated trace selection for SI (2024-07)](https://antmicro.com/blog/2024/07/automated-pcb-trace-selection-for-si-simulation); [open-source SI analysis (2023-11)](https://antmicro.com/blog/2023/11/open-source-signal-integrity-analysis) (titles via search)
- **pcbmodelgen** converts KiCad PCB files into Octave function files plus mesh lines for openEMS and CSXCAD. It is an older C++ tool. — [pcbmodelgen](https://github.com/jcyrax/pcbmodelgen)
- **KiCad Electrodynamic & Static Studio** (KiCad ≥10, uses the `kipy` IPC API) extracts tracks, vias, pads and zones, runs 2.5D and 3D openEMS FDTD for single-ended and mixed-mode S-parameters headlessly (`run_openems.py`), solves DC IR drop with a custom C++ MNA/Poisson solver, and post-processes with scikit-rf (Touchstone handling, vector fitting to SPICE). — [KiCad-Electrodynamic-Static-Studio](https://github.com/ravid1323/KiCad-Electrodynamic-Static-Studio)
- **scikit-rf** is a BSD-licensed Python RF/microwave package and the de facto Touchstone and network-analysis library. — [scikit-rf](https://github.com/scikit-rf/scikit-rf). **Qucs-S** is a GUI over ngspice (recommended), Xyce and SpiceOpus. — [Qucs-S](https://github.com/ra3xdh/qucs_s)
- **FastHenry** (inductance and resistance of 3D conductors) and **FastCap** (capacitance) are MIT-origin solvers, maintained with 64-bit Linux ports by FastFieldSolvers and described as "de-facto golden reference" solvers. — [FastHenry2](https://github.com/ediloren/FastHenry2); [FastCap2](https://github.com/ediloren/FastCap2)

**Combined SI/PI/EMC KiCad plugins (2026, mostly alpha)**
- **PCB_SI_Toolkit** (KiCad 10 plugin, installable through PCM) has these tabs:
  - Layout checks: measured-versus-limit rows for decap distance to IC supply pins and their ground vias, reference-plane changes without a ground via, plane edge (limit 3×h), HV isolation against IPC-2221, dead branches, width steps, tombstoning, and crystal routing.
  - Return Path: gap crossings plus an HF/DC return map.
  - DC Current: a resistive network with IPC-2221 limits.
  - Impedance: a 2D field solver from the real stackup.
  - Diff pairs: odd and even mode.
  - Crosstalk: estimated NEXT for parallel runs.
  - openEMS: 3D FDTD with S-parameters and TDR/TDT.
  It writes per-board JSON and HTML reports and ships a test board with one case per check. — [PCB_SI_Toolkit](https://github.com/ugo-silato/PCB_SI_Toolkit)
- **KiPI** (GPL-3.0, standalone or KiCad 9/10 IPC plugin, 0.9.1 alpha, has CI) has three modes. DC voltage drop takes VRMs, loads and series parts, gives PASS/FAIL for loads, VRMs, vias and temperature, and writes HTML/PDF reports. AC PDN impedance sweeps the network with decap RLC models against a target-impedance calculator. Coupled Noise treats a switcher as aggressor and checks named victim nets against logic-family noise margins. Setup is saved as `<board>.kipi-setup.yml`. — [KiPI](https://github.com/drewsum/KiPI)
- **Ki-PIDA** (KiCad 9+, IPC API) offers DC IR drop on a "hybrid 2.5D" resistive mesh with SciPy sparse solve, coupled electro-thermal analysis (temperature-dependent copper resistivity), power-tree and VRM efficiency modelling, voltage and current-density heatmaps, and config in `kipida_config.json`. Several forks exist (kbralten, Anercomp, Carter3DP, Gasman2014), and their maturity differs. — [KiPIDA (kbralten)](https://github.com/kbralten/KiPIDA); fork list via search: [Anercomp](https://github.com/Anercomp/KiPIDA), [Carter3DP](https://github.com/Carter3DP/KiPIDA)
- **SPIKE** (Apache-2.0, v0.3.10, an "early community preview" for Windows; Linux Flatpak experimental) is a PI/SI/thermal workbench. Its thermal mode covers object-node, 2D plate and layered steady/transient models with airflow presets. It has optional openEMS and EMerge EM extensions, ngspice circuits, a CLI with batch runs, and an optional MCP bridge. — [SPIKE](https://github.com/krishna-swaroop/SPIKE)
- **padne** is a finite-element DC power-delivery simulator for KiCad and a self-described side project. — [KiCad forum: padne](https://forum.kicad.info/t/presenting-padne-a-tool-for-dc-power-delivery-network-analysis/64966) (via search summary)

**EMI/EMC and return-path heuristics**
- **jasonarnoldarnie/kicad-tools `return_path`** (KiCad 10.0.1, bundled Python, read-only on `.kicad_pcb`, 0★, 4 commits, no license shown) picks each layer's reference plane by dielectric distance and refills zones in memory. It flags VOID (detour computed by A* on a 0.05 mm raster, failing when the detour exceeds `--max-detour`, default 1.0 mm), ISLAND, SPLIT (plane net changes, so the return must pass through a capacitor), TERMINAL, VIA (layer change without a stitching via or bridging cap) and EDGE. Per net it reports return length, return/trace ratio and a **loop-area estimate**, which it calls "for comparing nets, not a field solve". Net criticality is classed from net-name globs. Output can be text, HTML, JSON or `--fail` exit codes. It models plane copper only and identifies capacitors by refdes only. — [kicad-tools (return_path)](https://github.com/jasonarnoldarnie/kicad-tools)
- **emcvisual** runs in the browser and reads KiCad 6–10, IPC-2581, ODB++ and Eagle files. It computes a quasi-static magnetic near field (Biot–Savart with image currents in reference planes) and runs about 30 EMC rule checks covering interrupted return paths, reference changes at vias, missing stitching, regulator hot loops, cable common mode, filters and ESD at connectors, decoupling, and crystals near the edge. It gives a far-field estimate against CISPR 32/11/14-1 and FCC Part 15. The author reports that the fast far field agrees with openEMS "within 1 dB between 30 and 350 MHz" on a validation board, and that rules are documented with thresholds and test boards. — [emcvisual](https://github.com/tombueng/emcvisual)
- **kicad-happy** (MIT, about 1.3k★) is a set of AI-agent skills. Its EMC skill has "44 rule checks" (ground voids, decoupling, I/O filtering, switching harmonics, diff-pair skew, edge radiation, PDN impedance via ngspice, ESD paths, crosstalk) and outputs an "EMC risk score". The README reports regression testing over a corpus of more than 5,800 repos (3,498 PCB files, 6,853 EMC analyses). — [kicad-happy](https://github.com/aklofas/kicad-happy)
- **kicad-emi-guardian** (KiCad 10.0.5+ via `kicad-python`, MIT, 1 commit) checks GND antennas and islands, stubs, parallel coupling, sharp corners (default acute threshold 75°), electrically long nets, missing return vias, edge proximity and diff-pair mismatch, and estimates impedance, delay, quarter-wave resonance and a crosstalk proxy. It notes that KiCad 10's public IPC API does not expose stable custom DRC markers, and its author says it "is not an EMC compliance instrument". — [kicad-emi-guardian](https://github.com/hap231/kicad-emi-guardian)
- Other heuristic tools: Kicad_GND_return_path_identifier, a 0–100 heuristic score for a component's ground return that calls itself "a heuristic geometric proxy, not a field solver". — [repo](https://github.com/Kevin-Davees/Kicad_GND_return_path_identifier/tree/main) (via search summary)
- A KiCad forum thread exists on future built-in SI/PI functionality. — [KiCad forum](https://forum.kicad.info/t/future-plans-for-basic-signal-integrity-si-power-integrity-pi-funtionality/70585) (title only; content not readable here)

**Thermal**
- Ki-PIDA (electro-thermal), KiPI (optional board temperature in DC mode) and SPIKE (layered steady and transient board thermal) are the scriptable KiCad-native options found. — [KiPIDA](https://github.com/kbralten/KiPIDA); [KiPI](https://github.com/drewsum/KiPI); [SPIKE](https://github.com/krishna-swaroop/SPIKE)
- A 2024 write-up describes an open-source PCB thermal simulation workflow. — [jrainimo: Open-Source Thermal Simulation of PCBs](https://jrainimo.com/build/2024/11/oss-thermal-simulation-of-pcbs/) (title only; page blocked)
- KiCad StepUp (a FreeCAD workbench) is the KiCad↔FreeCAD mechanical/STEP bridge that such FEM flows rely on. — [kicadStepUpMod](https://github.com/easyw/kicadStepUpMod)

**Speed evidence and ML surrogates**
- An analytic, non-ML method for estimating total radiated power from PCB signal and PDN layout returns results "within 30s versus ~5 hours" for full-wave simulation on the authors' test board. — [Microelectronics Journal (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0026269221002445) (via search summary)
- ML SI surrogates: buffer-parameterized surrogates treat IC buffer characteristics as inputs alongside PCB parameters. In that work anisotropic GP regression was best with little data, NNs were best with large data, and validation used an interconnect with 44 parameters. — [arXiv 2605.18170](https://arxiv.org/pdf/2605.18170). Most ML SI work predicts eye height and width from PCB design parameters; differentiable surrogates have been used for amortized pre-layout design-space exploration. — [arXiv 2606.07463](https://arxiv.org/pdf/2606.07463) (via search summary)
- A vendor blog claims physics-informed neural operators are 100–1000× faster than FEM/FDTD at 2–5% accuracy loss. I found no peer-reviewed support. — [AtlasPCB blog](https://www.atlaspcb.com/blog/ai-accelerated-pcb-simulation-ml-si-pi-thermal/)

### Inferences
- **Loop-speed tiers.** These are inferred from method complexity and tool descriptions. Except for the 30 s vs 5 h comparison, these are not measured numbers.
  - (i) Microseconds to milliseconds per candidate, suitable for every optimizer step: HPWL and crossings, overlap and out-of-bounds, decap pad-to-pin distance, same-side checks, closed-form Z0 and delay (Transcalc), IPC-2221 width, parallel-run crosstalk proxies, and floorplan-intent grading.
  - (ii) Sub-second to seconds per candidate, suitable every N steps or per accepted move: `kicad-cli pcb drc --format json` (includes zone refill), raster return-path A* (0.05 mm grid), and Biot–Savart near-field estimates.
  - (iii) Seconds to minutes per board, for checkpoints and finalists: 2.5D resistive-mesh IR drop (Ki-PIDA, KiPI DC), PDN impedance sweeps, and 2D field-solver Z0 per cross-section.
  - (iv) Minutes to hours per net or port, final verification only: openEMS/gerber2ems 3D FDTD and FEM thermal.
- No tool provides a **standard machine-readable result schema** across SI, PI and EMC. Several emit JSON or HTML (return_path, PCB_SI_Toolkit, KiPI YAML setup plus reports). An LLM-driven system should wrap each tool behind a common `Finding{rule, severity, measured, limit, objects[uuid], location, evidence}` record that mirrors KiCad's DRC JSON (type, severity, items[uuid,pos]).
- Many plugins depend on a **running KiCad GUI with the IPC API** (KiPIDA, KiPI plugin mode, emi-guardian, Electrodynamic Studio). A headless loop should prefer file-based tools (return_path reads `.kicad_pcb`; emcvisual, gerber2ems and kicad-cli are headless) or run KiCad headless with the API. A third-party evaluation notes that `kipy` requires a running KiCad instance with no offline path. — [kicad-tools README (rjwalters)](https://github.com/rjwalters/kicad-tools)
- Validation is thin. Only emcvisual reports a quantitative agreement against openEMS (about 1 dB). The others warn "not compliance" or "alpha". A benchmark should therefore treat physics heuristics as **advisory soft scores** until each one has been calibrated against openEMS or measurements on a reference corpus.

### Gaps
- I found no published runtime figures for `kicad-cli pcb drc` on boards of various sizes, or for gerber2ems per-port runs, so tier boundaries are estimates.
- I found no open-source tool that predicts **radiated emissions from layout features with an ML surrogate**, and no peer-reviewed layout-level crosstalk or EMI surrogate dataset.
- Elmer FEM PCB thermal flows, atlc, Sonnet Lite, openEMS 2D and "KiCad openEMS" scripts other than those listed could not be researched after the search budget ran out. The Elmer GitHub README fetch also failed.
- Sparse validation data exists for KiPIDA, KiPI and SPIKE accuracy against commercial tools.

---

## Q3. Which layout quality metrics exist beyond DRC, and how do Quilter, DeepPCB and academic and open benchmarks report quality? Are there "human-like" or "expert-acceptable" metrics?

### Takeaway
The field has converged on a **gate-then-score** protocol:
- **Gate**: "Clean Pass" means fully connected **and** zero error-level DRC, under the board's own rules, re-checked by KiCad on saved files.
- **Routing secondaries**: routability (net-level and pad-pair level), DRV split by cause, wirelength, vias, layers, runtime, and parse-fail for LLMs.
- **Placement**: HPWL, overlap, out-of-bounds, crossings and net separation.

Vendor tools add "physics rule checks" for decoupling, switcher loops, diff pairs and current capacity. HPWL and crossings are explicitly not enough to separate sensible placements from scattered ones, so open tools now grade against **declared floorplan intent**. True "expert-acceptability" metrics barely exist yet. The closest are intent-conformance grading and comparison against human reference copper.

### Cited Findings
- **PCBWorld metrics.** Each board is routed 5 times, the rollout with the highest potential gain is kept (@5), and every board is re-opened and DRC-checked against its own project rules, so "a method never scores itself". The metrics are:
  - CP: fraction of boards fully connected with zero DRC errors.
  - Potential gain: Φ(routed) − Φ(bare).
  - Routability: the fraction of required connections routed.
  - DRV: error-level violations.
  - WL: total routed copper in mm.
  - Via.
  - Time: averaged over all rollouts.
  - Parse-fail: LLMs only.

  "Clean pass is the headline". WL and vias are "secondary", because shortening copper by leaving nets unrouted games them. — [PCBWorld METRICS.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/METRICS.md)
- PCBWorld's potential is Φ(s) = −unconnected − f_drv(DRC count, steepest near zero) − λ_w·wirelength − λ_v·vias + completion bonuses. The training potential also counts three promoted warnings (dangling track, dangling via, net conflict) that CP does not. — [PCBWorld ENVIRONMENT.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/ENVIRONMENT.md); [METRICS.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/METRICS.md). The DRC uses 35 stock error-level checks. — [PCBWorld arXiv HTML](https://arxiv.org/html/2607.05915v1) (via search summary)
- **OmniRouting/OmniLayout metric vocabulary**, as transcribed by a third party:
  - NRR: percentage of nets connected **and** DRC-clean.
  - PRR: percentage of DRC-clean pad-to-pad connections.
  - Open / PShort / NShort: net rates for opens, physical shorts and logical shorts.
  - Total / Clr. / Dist.: violation counts by cause.
  - Polygon: percentage of outputs with copper pours.
  - TWL, #Vias, #Layers.
  - PR: loadable-output rate.
  - RT: runtime.
  - Placement: OO (overlap), OoB, HPWL, NC (crossings), NS (net separation).

  The recon recommends adopting DRC-attributed NRR, pad-pair PRR and the violation-cause split. — [kicad-tools OmniLayout recon](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/omnilayout-recon.md)
- OmniRouting reports that current multimodal models show weak path planning, poor design-rule adherence and inconsistent preservation of electrical functionality. — [arXiv 2608.04434](https://arxiv.org/abs/2608.04434) (via search summary). A third-party summary gives under 13% clean net routability for models against about 94% for humans, which I could not verify in the paper. — [Pith summary](https://pith.science/paper/2607.03261) (via search summary)
- **RL_PCB** (DATE 2024) evaluates placement by HPWL, Euclidean wirelength, overlap, and **post-routing wirelength** after an A*-based router, against a simulated-annealing baseline. — [RL_PCB](https://github.com/LukeVassallo/RL_PCB)
- **Quilter** (vendor, self-reported) scores routing completion as the percentage of pins routed (goal 100%) plus manufacturability (fab-supported rules, zero DRC). It describes "Physics Rule Checks" for impedance targets, return-path continuity, bypass-cap placement, switching-converter layout, diff-pair integrity and trace width for current. It reports adding the Simbeor field solver for impedance profiles. Its "Project Speedrun" claims 98% routing completion with 38.5 h of human cleanup against a quoted 428 h of manual layout. Quilter's own blog concedes that routing metrics without first-pass yield or bring-up data don't show whether boards work. — [Quilter docs intro](https://docs.quilter.ai/using-quilter/introduction); [Quilter 2026 routing guide](https://www.quilter.ai/blog/a-2026-guide-to-automated-pcb-routing-traditional-autorouters-vs-ai-powered-layout); [Quilter vs DeepPCB vs Flux](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai) (via search summary)
- **DeepPCB** publishes per-board numbers. For example, on the open STRF RF board: 100% routed, 68 vias, under 3 min, 98 airwires. Its KiCad plugin is Apache-2.0, but routing runs in a closed, credit-metered cloud. — [kicad-tools external benchmark README (citing deeppcb.ai/benchmarks)](https://github.com/rjwalters/kicad-tools/blob/main/benchmarks/external/README.md); [deeppcb-kicad-plugin](https://github.com/instadeepai/deeppcb-kicad-plugin)
- **KiCadRoutingTools** states that "placement … is judged by `crossings` and `hpwl`. Both are indifferent between a sensible layout and a scattered one with the same wirelength". It adds `check_floorplan.py` with 15 settable rules (envelope, zone_containment, zone_side, assembly_side, zone_exclusive, keepout, edge_connector, decap_distance, decap_ungraded, decap_pin_distance, proximity, must_lock, legality, pins_to_edge, array_formation) plus plan-feasibility findings such as `plan_zone_overfull`. Exit code 4 means "violations found", kept distinct from a crash. — [floorplan-intent.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/floorplan-intent.md). Every change is A/B-tested on a corpus of open-source boards and graded for DRC violations and unconnected nets. — [KiCadRoutingTools](https://github.com/drandyhaas/KiCadRoutingTools)
- PCB_SI_Toolkit's "Layout checks" are framed as a "smart DRC that **measures** the layout instead of predicting physical quantities", with each row showing Measured next to Limit. Examples: decap distance to supply pins and ground vias, plane-edge distance (limit 3×h), width steps, dead branches, crystal routing. — [PCB_SI_Toolkit](https://github.com/ugo-silato/PCB_SI_Toolkit)
- Net-separation-oriented placement via margin maximization is an academic placement objective, relevant to NS. — [arXiv 2210.14259](https://arxiv.org/pdf/2210.14259) (title via search)

### Inferences
- **Proposed metric hierarchy.**
  - (1) Hard gates: loadable file, LVS/connectivity parity (`--schematic-parity`), CP (connected and zero error-level DRC under the board's own `.kicad_dru`), and zero hard-intent violations.
  - (2) Routing quality: NRR, PRR, DRV by cause, WL normalized by the human reference or by MST/Steiner lower bound, vias per net, layer-change count on critical nets, length and skew slack against `length`/`skew` constraints, and uncoupled diff-pair length.
  - (3) Placement quality: HPWL ratio to human, crossings, overlap and OoB (should be zero), intent conformance (floorplan-intent rules), decap pin distance distribution, and edge-connector compliance.
  - (4) Physics proxies: return-path violations by class, loop-area estimate for hot loops and critical nets, IR-drop margin, plane-split crossings, and crosstalk-proxy exposure.
  - (5) DFM and aesthetics: acute angles (`track_angle`), dangling segments, silk overlap, via-in-pad, and courtyard margins.
- "Human-like" acceptability can be operationalized as **distance to the human reference** on the same netlist and outline (WL, vias and HPWL ratios, plus intent conformance where the intent is authored, not emitted from a damaged board), together with **pairwise expert or LLM-judge preferences** calibrated on a held-out human-labelled set. No published calibrated "expert-acceptability" score was found.
- Selection effects matter. PCBWorld's best-of-5 by potential gain and its rule that Time is averaged over all rollouts are good conventions to copy so that stochastic LLM agents are compared fairly.

### Gaps
- I found no public, standardized "aesthetic" or "neatness" metric with human-rating validation.
- I could not obtain Quilter's or DeepPCB's exact scoring formulas, and their published numbers measure different things, as Quilter itself acknowledges.
- Thermal hot-spot metrics used in any public PCB layout benchmark were not found.

---

## Q4. What datasets and benchmarks exist for training or evaluating PCB placement and routing, and how could a benchmark be built from open-source KiCad repos?

### Takeaway
As of late 2026 the strongest routing benchmark is **PCBWorld/PCBWorld-Bench** (BSD-3). It provides KiCad-native boards, its own design rules per board, human reference copper, an engine-grounded DRC referee and published baselines. Its D3 split comes from the **PCBench** corpus.

Placement benchmarks are weaker:
- OmniLayout/OmniRouting have 1,681 Eagle-derived designs but no data license, and only 5 sample boards are public.
- RL_PCB is small.
- tscircuit's SRJ datasets are useful but lossy: they drop net classes, zones and keepouts.

LLM *knowledge* benchmarks (PCB-Bench, PCB-QA) measure what a model knows, not what it produces. A new benchmark can be built from open KiCad repos by stripping routing, or placement and routing, while keeping the outline, rules and fixed mechanical parts, then scoring against the human board. License tracking per board is essential.

### Cited Findings
- **PCBWorld** (LG AI Research, v1.1.0, BSD-3-Clause, engine GPLv3, KiCad 9.0.8 via submodule, Python 3.12+, Linux and macOS) wraps KiCad's push-and-shove router as a Gymnasium environment. It ships synthetic generators, real-board splits, a shared evaluation pipeline, and baselines: a decoder-only PPO/GRPO transformer, LLM tool-calling agents (Gemini, OpenAI, Anthropic, Together keys), FreeRouting and KRT. The state is exact geometry in mm (no grid or images), with a token wrapper for RL and an S-expression text wrapper for LLMs. The actions are `net_select`, `start_route`, `make_line`, `make_via`, `finish` and `net_end`. `tools/quickstart/prepare_pcbench.sh` builds D3 from PCBench. — [PCBWorld README](https://github.com/LGAI-Research/PCBWorld); [ENVIRONMENT.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/ENVIRONMENT.md)
- PCBWorld-Bench combines a grid-based (D1) and a gridless (D2) synthetic generator with **679 real open-source boards** (D3). Instances range from a few nets to hundreds of nets and more than 2,000 pads. The 679 boards are "taken from PCBench's corpus". An RL policy trained only on synthetic boards transferred zero-shot to real boards and approached rule-based routers. — [arXiv 2607.05915](https://arxiv.org/abs/2607.05915); [alphaXiv summary](https://www.alphaxiv.org/de/abs/2607.05915) (via search summary). A related source pool of 1,182 boards converted to KiCad 9 is mentioned, with the note that format conversion can itself trigger DRC violations. — [PCBWorld arXiv HTML v2](https://arxiv.org/html/2607.05915v2) (via search summary)
- Published Clean Pass on D3-A / D3-B (best-of-5): Freerouting 0.80 / 0.78, KiCadRoutingTools 0.74 / 0.20, as quoted by a third party from the paper. — [kicad-tools README ecosystem section](https://github.com/rjwalters/kicad-tools). OrthoRoute's own README reports 1% CP / 30% routability on D2 and 2% / 51% on D3-A (99 boards). It says Freerouting and KRT "performed dramatically better" and notes that OrthoRoute targets large backplanes. — [OrthoRoute](https://github.com/bbenchoff/OrthoRoute). A third party reports TraceMaker at about 0.99 / 1.00 / 0.90 clean on small / medium / large D3 splits, against about 0.7 / 0.7 / 0.2. This is self-reported and unreproduced. — [kicad-tools README](https://github.com/rjwalters/kicad-tools)
- **PCBench** describes itself as "a dataset for PCB routing" with **164 PCBs**. Each design folder contains `raw.kicad_pcb`, `processed.kicad_pcb`, `final.json` (PCB-RDL, a JSON routing-problem spec), `metadata.json` and `visual.png`. It also provides a net-subsampling augmentation script and a grid RL environment (`PCBRoutingEnv`). — [PCBench GitHub](https://github.com/PCBench/PCBench). **Conflict:** the README says 164 PCBs, while PCBWorld uses 679 PCBench boards. The README may be outdated or the corpus may have grown. I could not reconcile the two.
- **PCB-Bench** (ICLR 2026, DigAI Lab, no LICENSE file, 49★) contains about 1,800 expert free-form QA items plus matching single-choice versions (about 3,700 questions in total), about 500 image-and-text problems, and **174** OSHWHub (JLCPCB) real projects with schematics, placement and routing files, and screenshots for a screenshot-to-description task. Evaluation is zero-shot. — [PCB-Bench GitHub](https://github.com/digailab/PCB-Bench). The ICLR abstract summary says "over 170" projects. — [ICLR 2026 poster](https://iclr.cc/virtual/2026/poster/10009621) (via search summary). It tests model knowledge, not tool output.
- **OmniLayout** (arXiv 2607.03261, EMNLP Findings 2026) and **OmniRouting** (arXiv 2608.04434) draw on the same 1,681 designs: 2–8 layers, 109.9K components, 245.4K pads, 219.8K annotated nets, engineer reference routings, and 77.24K placement instances. A third-party audit (2026-08-15) found the records are JSON transcriptions of **Eagle 9.6.2** `.brd` files, not KiCad. Only 5 sample boards were public via Google Drive. The site's code, data and Hugging Face links were dead, there was **no data license**, and the papers are CC BY-NC-ND 4.0. — [kicad-tools OmniLayout recon](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/omnilayout-recon.md); [OmniRouting arXiv](https://arxiv.org/abs/2608.04434); [OmniLayout arXiv](https://arxiv.org/abs/2607.03261) (via search summary)
- **RL_PCB** (MIT, 71★): its parser reads `.kicad_pcb`, it trained on "a relatively small training dataset of 6 circuits", and it ships a `dataset` folder. — [RL_PCB](https://github.com/LukeVassallo/RL_PCB)
- **tscircuit autorouting datasets**:
  - `dataset-srj18` has 16 Simple Route JSON problems converted from KiCad boards: 5 Arduino and 11 Antmicro boards (for example DDR5_TESTBED and OCULINK_PCIE_ADAPTER). The pipeline is `kicad-to-circuit-json` then `getSimpleRouteJsonFromCircuitJson`. — [dataset-srj18](https://github.com/tscircuit/dataset-srj18)
  - The autorouter's main benchmark set is `dataset-srj33-drc-failures` (37 inputs, IDs 032–056 from bug reports), and results go to an external dashboard. — [tscircuit-autorouter](https://github.com/tscircuit/tscircuit-autorouter)
  - The docs explain how to contribute datasets and point to `dataset-srj19`. — [tscircuit docs: contributing autorouting datasets](https://docs.tscircuit.com/contributing/contributing-autorouting-dataset) (via search summary)
  - A community 45° obstacle dataset has 20 samples. — [dataset-srj11-45-degree](https://tscircuit.com/sangit/dataset-srj11-45-degree) (via search summary)
  - A third-party evaluation found that SRJ drops net-class width, clearance, zones and keepouts, so SRJ completion is not comparable to KiCad-native completion. — [kicad-tools README](https://github.com/rjwalters/kicad-tools)
- **Freerouting** (GPL-3.0) routes Specctra DSN to SES headlessly through a CLI, a beta REST API (self-hostable) and an MCP server. A third party calls the DSN round-trip a "lossy interchange boundary". fastroute, a Rust port, claims byte-identical parity on its 20 benchmark boards with roughly 4–5× less wall time (2102 s vs 510 s). — [freerouting](https://github.com/freerouting/freerouting); [kicad-tools README](https://github.com/rjwalters/kicad-tools)
- Other open corpora and datasets:
  - `bshada/open-schematics`: CC-BY-4.0, KiCad-native, versioned on Hugging Face, with each record pairing a schematic with a human-completed board, per a third party. — [kicad-tools OmniLayout recon](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/omnilayout-recon.md)
  - kicad-happy's test corpus: more than 5,800 repos, 3,498 PCB files analyzed. — [kicad-happy](https://github.com/aklofas/kicad-happy)
  - A KiCad netlist SFT dataset with 100,179 examples (netlists, not layouts). — [Hugging Face](https://huggingface.co/datasets/AbijahKaj/kicad-netlist-sft-dataset)
  - PCB-QA, a QA dataset built from KiCad files converted to JSON, where the best model scored about 93%. — [arXiv 2606.23704](https://arxiv.org/html/2606.23704) (via search summary)
  - Related schematic-side work: SchGen ([arXiv 2605.30345](https://arxiv.org/pdf/2605.30345)), pcbGPT ([arXiv 2606.01188](https://arxiv.org/html/2606.01188v1)), PCBSchemaGen v2 (227 tasks with a deterministic verifier, [GitHub](https://github.com/HZou9/PCBSchemaGen_v2)), and a GenAI-for-PCB survey ([arXiv 2606.17074](https://arxiv.org/pdf/2606.17074)) (via search summary).
- Practical benchmark-building precedent: a third-party harness fetches human-routed KiCad boards at **pinned commits** into a gitignored cache and never commits them, for license reasons. It upgrades legacy formats with `kicad-cli pcb upgrade`, captures "human baseline" routing stats, rips up tracks and vias while preserving placement, net assignments, net classes, zones and outline, and records upstream licenses in a manifest. — [kicad-tools benchmarks/external README](https://github.com/rjwalters/kicad-tools/blob/main/benchmarks/external/README.md). The same project integrates PCBWorld D3 CP@1/CP@5 aggregation. — [kicad-tools PR #6702](https://github.com/rjwalters/kicad-tools/pull/6702)

### Inferences
- **Benchmark construction recipe from open KiCad repos**, building on PCBWorld/PCBench practice:
  1. Harvest boards with a manifest pinning repo, SHA and license. Exclude NC/ND and unlicensed boards, or keep them evaluation-only and never redistribute them.
  2. Upgrade with `kicad-cli pcb upgrade` and run baseline DRC. Discard boards whose human copper fails their own rules, or record the baseline DRV, because conversion itself can introduce violations.
  3. Create task variants:
     - (R) route-only: strip tracks and vias, keep zones as outlines or strip them too.
     - (P) place-only: keep the outline, mounting holes, edge connectors and locked parts, randomize or pile the rest, and score with a fixed router (for example Freerouting or KRT) to get post-route metrics.
     - (P+R) both.
     - (I) intent-constrained: author or verify a floorplan intent and constraint IR per board, ideally human-reviewed rather than `--emit-intent` from the board.
  4. Score with the Q3 hierarchy and normalize against the human reference.
  5. Split by size and layers (PCBWorld's small, medium and large splits).
  6. Guard against contamination: popular open boards are likely in LLM pretraining data, so keep a private held-out set of recent or less-popular boards.
- Synthetic generators (PCBWorld D1/D2) are valuable for RL pretraining and for unit-testing specific constraint types such as diff pairs, length groups and decap proximity, where real boards are sparse.

### Gaps
- I found no ISPD or ICCAD contest problem specifically for PCB or package routing; I could not search for one after the budget ran out.
- The "Cypress" GPU PCB placement benchmark (ISPD 2025) could not be confirmed. A guessed repo URL returned 404.
- Freerouting's in-repo test designs and their count were not verified.
- The exact license mix of PCBench and PCBWorld D3 boards is unknown. PCBWorld ships a "recipe to rebuild D3" rather than the boards.
- The discrepancy between 164 and 679 PCBench boards is unresolved.

---

## Q5. How can datasheet reference layouts and existing open-source boards be reused as templates (layout retrieval)?

### Takeaway
KiCad now has native reuse primitives:
- **Design blocks**: schematic and/or layout fragments in `.kicad_blocks` libraries, where a saved layout can be applied to the footprints matching a schematic fragment.
- **Multichannel Repeat Layout**: copies a reference channel into target rule areas.

Code-first tools (atopile layout reuse) and agent toolkits (KiCadRoutingTools `replicate[]`) add hierarchical-address matching. I found no open dataset or retrieval system that mines datasheet reference layouts. Reference-layout reuse for an LLM system will have to be built from (a) design-block libraries, (b) subcircuit-matched fragments from open boards, and (c) datasheet-derived constraints rather than geometry.

### Cited Findings
- KiCad design blocks store a schematic fragment, a layout fragment or both, in `.kicad_blocks` library folders managed by global and project library tables. If a block has both fragments, "you can apply the saved layout to the footprints that correspond to the symbols in the schematic fragment". — [pcbnew_design_blocks.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_design_blocks.adoc)
- Multichannel layout requires channels to have equal symbol counts, matching refdes prefixes, the same footprints and equivalent connectivity. Placement and routing are copied from the reference rule area to target rule areas. — [pcbnew_multichannel.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc)
- atopile ships a `layout_reuse` example. A third-party analysis describes matching components by semantic module path (`atopile_address`, for example `power.ldo.package`) rather than refdes, so that layout survives regeneration. — [atopile examples](https://github.com/atopile/atopile/tree/main/examples); [kicad-tools atopile synthesis](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/atopile-research-synthesis.md)
- The KiCadRoutingTools intent has `replicate[]` (from one sheet instance to others, with an anchor and `allow_net_mismatch`) and `arrays[]` (ordered member lists serving a ref, with shared rotation). — [floorplan-intent.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/floorplan-intent.md)
- kicad-happy's datasheets skill extracts structured JSON from datasheet PDFs (pinouts, electrical characteristics, topology, SPICE coefficients), caches per MPN, and feeds its EMC, SPICE and thermal checks. — [kicad-happy](https://github.com/aklofas/kicad-happy)
- rjwalters/kicad-tools offers parametric circuit "blocks" (MCUBlock with bypass caps, CrystalOscillator, LDOBlock, USB connector with ESD, DecouplingCaps) as reusable templates. — [kicad-tools README](https://github.com/rjwalters/kicad-tools)

### Inferences
- Layout retrieval can be framed as **subgraph matching on the netlist**: find (IC MPN or footprint, connected passives, pin functions) in a corpus of human boards, then transfer *relative* poses (as in KiCad multichannel and design blocks) as a seed, and re-validate against the constraint IR. The corpus from Q4 can double as the retrieval index.
- Datasheet layout guidance (for example "place CIN within X mm of VIN/PGND, minimize the SW node") is better captured as **constraints** (proximity, loop-area, keep-away, same-side) extracted by an LLM into the IR than as copied geometry, because packages and stackups differ. Extracted constraints should carry provenance (datasheet page) and be human-confirmable.

### Gaps
- I found no published dataset of datasheet reference layouts and no evaluation of LLM extraction accuracy for datasheet layout guidelines.
- I found no open "layout retrieval" system or paper for PCBs; the search budget was exhausted before targeted searches.

---

## Q6. Implications for an LLM-driven KiCad placer/router: proposed constraint IR sketch, evaluation stack and benchmark plan

### Takeaway
Build a typed, strict-schema **constraint IR** that compiles to three back-ends: `.kicad_dru` rules for KiCad routing and DRC enforcement, fast Python checkers, and optimizer penalty terms. Each constraint carries hard/soft status, a weight, a measurement method and provenance. Evaluate in tiers: cheap geometric checks every step, kicad-cli DRC and return-path checks per accepted move, IR drop and PDN per checkpoint, openEMS only on finalists. Benchmark on PCBWorld D3 plus your own license-tracked, KiCad-native corpus with route-only, place-only and place+route tasks, gated by Clean Pass and scored against human reference copper and authored intent.

### Cited Findings
(Supporting facts, collected from above.)
- KiCad DRC already supports `fromTo` path selection, `length`, `skew`, `via_count`, `diff_pair_*`, `assertion` and area/courtyard/class predicates, and it outputs machine-readable JSON with object UUIDs and positions. — [pcbnew_advanced.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc); [drc.v1.json](https://gitlab.com/kicad/code/kicad/-/blob/master/resources/schemas/drc.v1.json)
- ALIGN's hard/soft and `translate(solver)` design and KiCadRoutingTools' strict-schema, monotone-gate intent are proven patterns. — [ALIGN constraint.py](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/master/align/schema/constraint.py); [floorplan-intent.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/floorplan-intent.md)
- PCBWorld provides an engine-grounded evaluation protocol (CP, Pot., Rout., DRV, WL, Via, Time, Parse-fail; @5 selection; DRC re-run on saved boards). — [PCBWorld METRICS.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/METRICS.md)

### Inferences

**A. Proposed constraint IR sketch (YAML/JSON, strict schema, unknown keys rejected)**

```yaml
schema: pcb-intent/0.1
units: mm
selectors:                     # reusable, all renderable to KiCad DRC condition strings
  U1_VDD7: {pad: "U1-7"}                       # KiCad fromTo pad syntax RefDes-Pad
  U1_GND:  {pads_of: U1, net: GND}
  C5_hot:  {pad: "C5-1"}
  C5_gnd:  {pad: "C5-2"}
  DDR_DQ0: {netclass: DDR_DQ, match: "/DDR/DQ[0-7]"}
  PWR_BLK: {component_class: "BUCK1"}          # -> ${Class:BUCK1}
constraints:
  - id: dec.U1.7.prox
    kind: proximity                 # placement-time
    a: C5_hot
    b: U1_VDD7
    max: 2.0
    basis: pad_edge                 # pad_edge | pad_center | courtyard
    hard: true
    provenance: {source: datasheet, doc: "U1 DS rev C", page: 23}
    compile:
      checker: geom.pad_distance
      optimizer: {penalty: hinge_sq, weight: 50}
      kicad_dru: |                  # post-route proxy only
        (rule "dec.U1.7.len" (condition "A.fromTo('U1-7','C5-1')") (constraint length (max 2mm)))
  - id: dec.U1.7.gndvia
    kind: via_to_plane
    pad: C5_gnd
    plane: {net: GND, layer: In1.Cu}
    max_via_distance: 0.5
    min_vias: 1
    hard: true
    compile: {checker: geom.pad_via_to_zone}   # no native KiCad DRC equivalent
  - id: dec.U1.7.loop
    kind: loop_area                 # physics proxy
    path: [U1_VDD7, C5_hot, C5_gnd, "via", "plane:GND", U1_GND]
    max_mm2: 4.0
    hard: false
    weight: 10
    compile: {checker: phys.loop_area_estimate}
  - id: ddr.dq.skew
    kind: skew
    group: DDR_DQ0
    max_ps: 5                       # time domain via KiCad tuning profile unit delay
    compile:                        # length fallback below assumes ~6.3 ps/mm (illustrative; derive from stackup)
      kicad_dru: |
        (rule "ddr.dq.skew" (condition "A.hasNetclass('DDR_DQ')") (constraint skew (max 0.8mm)))
  - id: buck.zone
    kind: region                    # like ALIGN Floorplan / KRT blocks.zone
    members: PWR_BLK
    rect: [2, 2, 40, 30]
    side: F
    exclusive: false
  - id: usb.edge
    kind: edge_placement            # like KRT edge_connectors
    ref: J1
    edge: north
    overhang: [0, 1.5]
  - id: sym.diffamp
    kind: symmetry                  # ALIGN SymmetricBlocks analogue
    pairs: [[R10, R11], [C20, C21]]
    axis: V
    hard: false
objectives:                         # soft, weighted; logged separately from gates
  - {metric: hpwl, weight: 1}
  - {metric: vias_on_critical, weight: 5}
  - {metric: return_path_violations, weight: 20}
```

Design rules for the IR:
- (1) Every constraint compiles to **at least one checker**. A `.kicad_dru` rule is added whenever one exists, so the KiCad interactive router and DRC see it.
- (2) Distinguish **placement-time vs post-route** measurability.
- (3) Keep **hard (gate) vs soft (objective)** separate, as in ALIGN.
- (4) Record **provenance and confidence** for LLM-extracted constraints, and require human confirmation for hard constraints extracted from datasheets.
- (5) Render selectors to KiCad syntax (`fromTo`, `${Class:}`, net class, sheet, rule area) so they can be validated with KiCad's own evaluator.
- (6) Be **monotone** inside optimizers: never accept a move that increases hard-violation count.
- (7) Never auto-derive intent from a board under repair.
- (8) The LLM's job is to *author and justify* IR entries and pick strategies. Numeric optimization and routing stay with deterministic engines.

**B. Recommended evaluation stack (fast to slow)**

| Tier | When | Checks | Tools |
|---|---|---|---|
| T0 (µs–ms) | every candidate move | overlap/OoB, intent rules (region, edge, proximity, decap distance, same-side, symmetry), HPWL, crossings, closed-form Z0 and delay, IPC-2221 widths | in-process Python/Rust geometry; KRT-style `check_floorplan` logic; Transcalc formulas |
| T1 (s) | per accepted placement or route batch | `kicad-cli pcb drc --format json --refill-zones --schematic-parity --exit-code-violations`; return-path VOID/SPLIT/VIA/EDGE and loop-area estimates; crosstalk proxies | kicad-cli; return_path-style raster A*; PCB_SI_Toolkit-style measured-vs-limit checks |
| T2 (s–min) | per checkpoint | DC IR drop and current density, PDN impedance vs target, switcher coupled noise, quasi-static near-field and far-field estimate | KiPI, Ki-PIDA, PCB_SI_Toolkit DC tab, emcvisual-style Biot–Savart |
| T3 (min–h) | finalists only | 3D FDTD S-parameters, TDR and delay on critical nets; FEM thermal | gerber2ems/openEMS + scikit-rf; SPIKE/Elmer thermal |

Normalize every tool's output into one `Finding` schema modelled on KiCad's DRC JSON, attributing each finding to nets and pads. Calibrate T0–T2 heuristics against T3 on a reference board set before trusting them as rewards. Treat T2/T3 as advisory unless they are validated.

**C. Proposed benchmark plan**
1. **External leaderboard**: run on PCBWorld D3 (route-only), reporting CP@1/@5, Pot., Rout., DRV, WL, Via, Time and Parse-fail per PCBWorld's protocol, against the published Freerouting and KRT baselines.
2. **Own KiCad-native corpus**: 300–1,000 license-clean boards from open repos and open-schematics-style datasets, pinned by SHA, with fetch-at-runtime manifests. Build tasks R (route-only), P (place-only with fixed mechanicals, scored by a fixed reference router), P+R and I (intent-constrained, with human-reviewed IR per board), split small, medium and large by nets, pads and layers.
3. **Metrics**: hard gates (loadable, LVS parity, CP, zero hard-intent violations); routing (NRR, PRR, DRV by cause, WL/human, vias/human, length and skew slack); placement (HPWL/human, crossings, intent conformance, decap distance distribution); physics proxies (return-path violations, loop area, IR-drop margin); and runtime and token cost.
4. **Human-likeness**: report ratios to human copper and pairwise preference from a small expert-labelled set, then use it to calibrate an LLM-judge.
5. **Synthetic unit suites** (PCBWorld D1/D2-style plus targeted generators) for each IR constraint kind: decap proximity, diff pair, length group, edge connector, symmetry, keep-away.
6. **Hygiene**: a private, recent held-out split to limit pretraining contamination; deterministic seeds; record KiCad version (conversion changes DRC results); never let a method score itself, so always re-open saved boards and re-run DRC.

### Gaps
- The IR sketch is an untested design proposal. The proximity and via-to-plane checkers and the loop-area estimator need implementation and validation.
- The tier latency figures are estimates. They should be measured on representative boards (small, medium, large) before fixing optimizer schedules.
- Suitability of PCBench/PCBWorld D3 board licenses for redistribution was not verified.
