# Infrastructure to evaluate, verify and constrain automated PCB layouts: constraint/intent IRs, open-source physics and verification tools, quality metrics, benchmarks and datasets (for an LLM-driven KiCad placer and router)

Research dates: first pass 2026-10-20; deep pass later the same day with full internet access. **Method and provenance (read first):**

**Provenance tags** (one or more per bullet):
- **[P]** — read directly from the primary source: official docs, source code/XSD, paper full text or abstract page, or project README/repo.
- **[3P]** — read in full from a credible secondary source, e.g. a vendor partner's technical note or a third-party project's evaluation document.
- **[S]** — search-engine snippet/summary only; not read at the source. Treat as unverified.

**Coverage notes**
- In the first pass, docs.kicad.org, arxiv.org, antmicro.com, docs.atopile.io, docs.jitx.com, docs.tscircuit.com, docs.quilter.ai and forum.kicad.info were unreachable. In the deep pass they were reachable via `curl` and were read directly.
- Still unreachable or refused:
  - community.cadence.com and www.cadence.com PDFs (403); the Cadence Constraint Manager user guide is behind support login.
  - dl.acm.org (bot wall).
  - Cornell csl.cornell.edu and artwork.com (TLS chain errors; TLS verification was not bypassed).
  - iclr.cc, the ElmerCSC GitHub README (fetch refused), and wiki.freecad.org (bot challenge).
- The shared web-search budget ran out twice. Thermal-ML and EMI-ML surrogate searches could not be completed in the deep pass (see Gaps).
- Out of scope here: a separate agent produces the verified KiCad DRC-rules reference and the IPC API coverage matrix. KiCad DRC content below is kept at the level needed for IR design.
- GitHub star counts are point-in-time values from 2026-10-20 and differ between sources.

---

## Q1. How can design constraints and intent be represented formally and fed to optimizers and LLMs? (KiCad rules language, net and component classes, rule areas, industry constraint managers, exchange formats, code-first EDA, analog constraint formats, IR design)

### Takeaway
There are three families of constraint model.
- **Rule-scoping languages:** KiCad `.kicad_dru` (last matching rule wins), Altium query-scoped rules (explicit numeric priority), and JITX tag/condition/effect constraints (priority chosen by logical *specificity*). All three attach checkable limits to object sets selected by a boolean query over classes, areas, layers and pad-to-pad paths.
- **Object-centric constraint managers:** Allegro CSets assigned to nets, classes, regions and pin pairs; match groups; topology schedules; Altium's Constraint Manager.
- **Placement-relation languages:** ALIGN's typed JSON (hard vs soft, compiled to solver terms), tscircuit `calc()`, anchors and `<constraint>`, FloorSet hard constraints, KiCadRoutingTools floorplan intent, and Quilter "physics constraints" checked by named PRCs.

Exchange formats carry little of this. IPC-2581C transports impedance and loss specs, net class *categories* and diff-pair links, and DFX queries. It does not carry clearance, length, skew or placement rules. KiCad's IPC-2581 exporter writes stackup material, finish and backdrill specs but no impedance specs.

A good IR should therefore be a superset that compiles *down* to `.kicad_dru`, to geometric checkers and to optimizer penalties. Its rule-resolution semantics must be explicit, because KiCad, Altium and JITX resolve conflicting rules differently.

### Cited Findings

**KiCad (constraint vocabulary relevant to IR design; full rule reference is another agent's deliverable)**
- `.kicad_dru` rules: `(version 1)` header as of KiCad 10.0; rules are evaluated in reverse order with the last match winning; form is `(rule name [(severity)] [(layer)] [(condition "expr")] (constraint type …))`. — [P] [kicad-doc pcbnew_advanced.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc)
- Constraint types include:
  - `clearance`, `physical_clearance`, `creepage`, `edge_clearance`, `courtyard_clearance`
  - `track_width` (min/opt/max), `length` (opt is the tuner target), `skew` (with `within_diff_pairs`), `diff_pair_gap`, `diff_pair_uncoupled`
  - `via_count`, `disallow`, `assertion`, `track_angle`, `track_segment_length`, `microvia_*`
  - zone and thermal relief constraints

  Selectors are `A.`/`B.`/`AB.` functions, including `fromTo('U1-7','C5-1')`, `insideArea`, `intersectsArea`, `enclosedByArea`, `insideCourtyard('${Class:X}')`, `hasNetclass`, `hasComponentClass`, `memberOfSheet`, `memberOfGroup` and `inDiffPair`. — [P] [pcbnew_advanced.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc)
- Other primitives:
  - **Component classes**: assigned by Reference, Footprint, Side, Rotation, Field, Sheet or custom expression, with automatic per-sheet classes.
  - **Tuning profiles** (KiCad 10): per-layer width, gap and unit delay plus via delays; time-domain tuning.
  - **Rule areas**: keepouts, and placement areas for multichannel layout.
  - **Repeat Layout**.

  — [P] [pcbnew_create_board.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_create_board.adoc); [P] [pcbnew_editing.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_editing.adoc); [P] [pcbnew_multichannel.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc)

**Altium Designer — query-scoped rules**
- Rules are scoped by query expressions, for example `InNet('VBAT') And OnLayer('Bottom Layer')`. **Unary** rules take one scope; **binary** rules take two scopes, one for each object.
- **Every rule has a priority.** A lower number means higher priority, and a new rule gets priority 1 while existing ones shift down. Priorities apply only within a rule type, across all rule sets.
- The documented exception: **multiple Matched Lengths rules all apply** to the objects they target.
- Invalid queries flag the rule as invalid.

— [P] [Altium: Scoping design rules](https://www.altium.com/documentation/altium-designer/scoping-design-rules-ad)
- Membership-check keywords include:
  - `InNet`, `InNetClass`, `InComponent`, `InComponentClass`
  - `InDifferentialPair(Class)`, `InFromTo('NET (C13-2 : U1-8)')`, `InFromToClass`
  - `InxSignal(Class)` (xSignals are signal paths through series components)
  - `InPadClass`, `InPolygonClass`, `InRegion`/`Absolute`/`Relative`, `InLayerClass`, `InStructureClass`, `OnLayer`, `ExistsOnLayer`
  - `WithinRoom` (object totally inside the room; pads and vias by center point) and `TouchesRoom` (totally or partially inside)

  Class names are single-quoted, and functions return Boolean. — [P] [Altium: query membership checks](https://www.altium.com/documentation/altium-designer/query-lang-pcbfunctions-membershipchecks-incomponentclassincomponentclass-ad)
- **Rooms**: each room is automatically a named **Room Definition** constraint that says which objects it applies to and whether they are **kept inside or outside**. Rooms can also scope other rules, for example width under a BGA. Components assigned to a room move with it. In Altium's Constraint Manager, Room Definition sits in the Placement category, and Altium describes it as a "confinement" constraint. — [P] [Altium: Rooms](https://www.altium.com/documentation/altium-designer/pcb/rooms)

**Cadence Allegro / OrCAD Constraint Manager — object-centric CSets**
- Constraint Manager groups rules into Electrical, Physical, Spacing and Same Net Spacing domains. Physical and Spacing CSets hold per-layer values and are assigned to Net, Class and Region objects. Each non-Electrical domain has an undeletable DEFAULT CSet. Electrical CSets can be derived from SigXplorer topology templates. — [S] [Allegro CM User Guide 16.3 (Cadence community PDF)](https://community.cadence.com/cfs-file/__key/telligent-evolution-components-attachments/00-27-01-00-00-96-42-32/cmug.pdf) (403 when fetched; summary only)
- Electrical constraint modes:

  | Constraint | What it specifies |
  |---|---|
  | **Stub length / Net schedule** | Daisy-chain stub length and the Verify-schedule check |
  | **Max via count**, **Match via count** | Via limits on a net; via-count matching across a group |
  | **Max exposed length** | Maximum copper length on outer layers |
  | **Propagation delay** | Min/max per pin pair, as delay, length or %length |
  | **Relative propagation delay** | Match groups |
  | **Max parallel** | A matrix of up to 4 length:gap entries |
  | **Impedance** | Target with absolute or % tolerance |
  | **Total etch length** | For a net or Xnet |
  | **Layer sets** | Permitted routing layer sets; fanout etch is ignored |
  | **Max xtalk**, **Max peak xtalk** | High-Speed option |
  | **Return Path DRC** | High-Speed option |

  Placement-related modes include Package-to-package overlap, Package to place keepin/keepout and **Package to room**. — [3P] [Parallel Systems (Cadence channel partner) technical note: Constraint Mode Options](https://www.parallel-systems.co.uk/wp-content/uploads/2020/02/Constraint_modes.pdf)
- A **Match Group** is a set of nets, Xnets or pin pairs that must match in time or length, or be relative to a target.
  - Groups resolve to **pin pairs**, which can be generated as All Drivers/All Receivers, Longest Driver/Receiver or Longest Pin Pair.
  - Each group has Scope, Delta, Tolerance and Target.
  - "Match" = Tolerance only; "Relative" = Delta + Tolerance against a Target.

  — [3P] [Parallel Systems: Matched Groups](https://www.parallel-systems.co.uk/wp-content/uploads/2020/02/Match_groups.pdf)

**JITX — tag/condition/effect constraints with specificity-based resolution**
- The model has four parts:
  - **Tag**: user tags are Python classes with inheritance; implicit tags include `IsCopper` ⊃ `IsTrace`/`IsPour`/`IsVia`/`IsPad`, `IsBoardEdge`, `IsHole`, `IsThroughHole`, `IsNeckdown` and `OnLayer(i)`.
  - **Condition**: a boolean expression over tags using `& | ~`.
  - **Effect**: `trace_width`, `clearance` (auto-symmetrized), `thermal_relief`, `stitch_via`, `fence_via`.
  - **Constraint**: `design_constraint(cond[, cond2]).effect(v)`; unary or binary.

  Tags can currently be assigned only to nets, and only in code. — [P] [JITX docs: Design Constraints](https://docs.jitx.com/en/latest/essentials/physical_design/design-constraints.html)
- **Selection algorithm.** JITX picks one rule per query, filtering in this order:
  1. Match the effect type.
  2. Drop rules whose condition isn't satisfied; if none remain, fall back to a default.
  3. Keep the highest explicit `priority`.
  4. Global logical specificity: a stronger condition, as a set of tag assignments respecting inheritance, wins.
  5. Local specificity by canonical tag order: object types, then user tags, then layers.
  6. Tie-breaks.

  The docs recommend specificity over explicit priority, because using a priority stops specificity from resolving rules at that priority level. — [P] [JITX docs: Design Constraints](https://docs.jitx.com/en/latest/essentials/physical_design/design-constraints.html)
- **SI constraints** are layered on **topologies**:
  - Topologies are ordered, acyclic trees of pad-to-pad "topo-nets" built with `>>`.
  - Each node must be a physical pad. Pass-through parts need a `BridgingPinModel`, and endpoints may have a `TerminatingPinModel(delay, loss)` from IBIS or datasheet data.
  - **Medium** constraints are `RoutingStructure` and `DifferentialRoutingStructure`: impedance, per-layer width, spacing, clearance, velocity, insertion loss, a `NeckDown`, and an uncoupled region.
  - **Medium-dependent** constraints are `TimingConstraint` (for example 1.0 ns ±10 ps between elements), `TimingDifferenceConstraint` (skew, intra- or inter-pair) and `InsertionLossConstraint`.
  - They are applied through `Constrain(Topology(a, b)).timing(...)`.
  - The router tunes delay in "Signal Tuning" regions and reports "Unsatisfied Signal Constraints".

  — [P] [JITX SI constraints](https://docs.jitx.com/en/latest/essentials/SI/constraints.html); [P] [JITX topology](https://docs.jitx.com/en/latest/essentials/SI/topology.html)
- **JITX placement** is a kinematic tree of relative transforms (`Placement(translate, rotate, on=Side)`, `Positionable.at(x, y, on, rotate)`), not a constraint system. — [P] [jitx.placement API](https://docs.jitx.com/en/latest/api/jitx.placement.html)

**tscircuit — constructive placement and routing properties**
- Placement props:
  - Position: `pcbX`, `pcbY`, `pcbRotation`.
  - Edge anchors: `pcbLeftEdgeX`, `pcbRightEdgeX`, `pcbTopEdgeY`, `pcbBottomEdgeY`.
  - Offsets and modes: `pcbOffsetX/Y`, `pcbPositionAnchor`, `pcbPositionMode` (`relative_to_group_anchor | auto | relative_to_board_anchor | relative_to_component_anchor`), `pcbRelative`.
  - Edge and margins: `shouldBeOnEdgeOfBoard`, `pcbMargin*`.
  - Group layouts: `pcbGrid*`, `pcbFlex*`, `pcbPack`, `pcbLayout`.
  - Trace widths: `minTraceWidth`, `nominalTraceWidth`.

  — [P] [tscircuit/props README](https://github.com/tscircuit/props)
- `calc()` expressions can reference component bounds (`R1.maxX`), **pin/pad bounds** (`U1.pin1.x`, `R1.pin2.maxX`) and board bounds. For example, `pcbX="calc(R1.pin1.minX - 2mm)"` places a part relative to a specific pad. — [P] [tscircuit: Relative Positioning](https://docs.tscircuit.com/guides/tscircuit-essentials/relative-positioning)
- `<constraint xDist="6.35mm" centerToCenter left=".H1" right=".H2" />` and `edgeToEdge` express footprint-internal geometry. — [P] [tscircuit: constraint](https://docs.tscircuit.com/footprints/constraint)
- Groups: `<group>` gives relative positioning, plus packing "to minimize trace distance", for example an MCU with its decoupling capacitors. Automatic layout via `pcbFlex`, `pcbGrid` and `pcbPack` is marked **beta**. — [P] [tscircuit: groups for PCB layout](https://docs.tscircuit.com/guides/tscircuit-essentials/using-groups-for-pcb-layout); [P] [tscircuit: Automatic PCB Layout](https://docs.tscircuit.com/guides/tscircuit-essentials/automatic-pcb-layout)
- Routing constraints:
  - `<bus name connections preferredLayers maxLengthSkew="0.5mm">` (a bus does not connect its members electrically).
  - `<differentialpair positiveConnection negativeConnection maxLengthSkew>`.
  - `<breakout>` regions own package fanout. The DDR guide splits a channel into a controller fanout, a global channel and a memory fanout.

  — [P] [tscircuit: Routing DDR](https://docs.tscircuit.com/guides/routing-ddr)
- `<drccheck checkFn>` adds custom, design-local DRC functions that return circuit-json error objects, for example to detect an I²C address conflict. — [P] [tscircuit: drccheck](https://docs.tscircuit.com/elements/drccheck)

**atopile — parametric assertions; layout delegated to KiCad**
- Primary example syntax:
  - `assert v_out is v_in * ratio` (equations for the solver)
  - `assert my_vdiv.power.voltage is 10V +/- 1%`
  - `assert ….voltage within 3.3V +/- 10%`
  - `assert max_current within 10uA to 100uA`
  - `r.resistance = 1kohm +/- 20%`, `capacitor.package = "C0402"`
  - Connections: `~` and the bridge-connect operator `~>`, behind `#pragma experiment("BRIDGE_CONNECT")`.

  — [P] [atopile examples/equations](https://github.com/atopile/atopile/blob/main/examples/equations/equations.ato); [P] [examples/auto-picking](https://github.com/atopile/atopile/blob/main/examples/auto-picking/auto-picking.ato)
- **Layout reuse** works by building a sub-module as its own build target (`builds: sub: entry: layout_reuse.ato:Sub`), laying it out by hand in KiCad, then using the KiCad "atopile pull group" button to replicate it into the top layout. — [P] [examples/layout_reuse](https://github.com/atopile/atopile/blob/main/examples/layout_reuse/layout_reuse.ato)
- docs.atopile.io now says the docs "live in the editor". It is marked pre-release, and it shows a newer syntax: `.ELEC: @STD::Import {…}`, `.Blinky: @type {…}`, `@trait(_): ELEC::is_pcb`, `.resistance &= 330ohm +/- 5%`. The language is therefore in flux. — [P] [docs.atopile.io](https://docs.atopile.io/)
- I found no geometric or placement constraint vocabulary in atopile. Placement and routing remain KiCad's job. — [P] (inference from examples and README) [atopile README](https://github.com/atopile/atopile)

**Quilter — "physics constraints" with explicit pass/fail PRCs** (primary docs, vendor-defined)
- Quilter's Circuit Comprehension detects physics constraints automatically, and users can enter them manually. The types are:
  - **Bypass Capacitors**: capacitor ref plus the component being bypassed. Parent pins are assigned by priority: explicit schematic wire, then voltage-named pins; a cap on several same-name pins is split equally.
  - **Switching Converters**: refdes must start with `U`, the output inductor with `L`, with ≥2 external capacitors. All three passives are placed "as closely as possible" to the package.
  - **Crystal Oscillators**, **Power Nets**, **Timing-sensitive Signals**, **Differential Pairs**, **Single-ended Impedance Control**.

  Unconstrained nets are treated as generic low-speed signals. — [P] [Quilter: physics constraints overview](https://docs.quilter.ai/physics-constraints/overview); [P] [bypass capacitors](https://docs.quilter.ai/physics-constraints/bypass-capacitors); [P] [switching converters](https://docs.quilter.ai/physics-constraints/switching-converters)
- **Physics Rule Checks (PRCs)** validate each constraint per candidate:

  | PRC | What it measures | Pass criterion |
  |---|---|---|
  | Pin Distance | Euclidean distance between closest pin edges, in cm | Within a tolerance, e.g. 0–1 cm |
  | Layer Switch Count | Layer switches on the path | — |
  | Ground Plane Overlap | Ground plane under both diff-pair traces at all points | All points except the last 2×clearance at the ends |
  | Trace Path Length | Pin-to-pin trace length | — |
  | Length Mismatch | — | — |
  | Uncoupled Spacing | — | — |
  | Invalid Width Span | — | — |
  | Overheated Length | % of a high-current net whose analytic temperature rise exceeds 20 °C | Below a tolerance, e.g. 0–10% |

  — [P] [Quilter PRCs overview](https://docs.quilter.ai/physics-rule-checks-prcs/overview); [P] [Pin Distance](https://docs.quilter.ai/physics-rule-checks-prcs/pin-distance); [P] [Ground Plane Overlap](https://docs.quilter.ai/physics-rule-checks-prcs/ground-plane-overlap); [P] [Overheated Length](https://docs.quilter.ai/physics-rule-checks-prcs/overheated-length)
- Quilter's design parameters include placement regions, keepouts, pre-placed components, pre-routed traces, preserved pours, single-sided placement, net widths by layer, stackups and fabricators. — [P] [docs.quilter.ai navigation](https://docs.quilter.ai/using-quilter/introduction)

**Exchange format: IPC-2581C (schema read directly)**
- The official XSDs (IPC-2581A, B, B1 and C) are published at webstds.ipc.org/2581/; the C version is dated 2020-07-31. — [P] [webstds.ipc.org/2581](https://webstds.ipc.org/2581/)
- **Specs.** A `Spec` (attribute `name`, plus optional Xform, Location and Outline) holds abstract `SpecificationType` members:
  - `Backdrill`, `Dielectric`, `Conductor`, `Compliance`, `Technology`, `General`, `Temperature`, `V_Cut`, `Tool`
  - **`Impedance`**: `value` plus `tolPlus`/`tolMinus`/`tolPercent`, and a `TransmissionType` of `SingleEnded`, `EdgeCoupled`, `BroadsideCoupled` or `CoplanarWaveguide`. Each transmission type has `LineWidth`, `Spacing`/`Pitch`, `RefPlane layerOrGroupRef` and a structure enum such as `STRIPLINE_SYMMETRIC` or `MICROSTRIP_MASK_COVERED`.
  - `Thieving`, `EdgeChamfer`, `EdgePlating`, `SecondaryDrill`, `SurfaceFinish`, `Flex`
  - **`Loss`** (types ATTENUATION, IMPEDANCE, INSERTION, POWER, SIGNAL, VOLTAGE)

  `LengthPropertyType` carries `constraintType` = MIN, MAX or NONE. — [P] [IPC-2581C.xsd](https://webstds.ipc.org/2581/IPC-2581C.xsd)
- **Nets.** `LogicalNet` has `name`, **`netClass`** (enum CLK, FIXED, GROUND, SIGNAL, POWER, UNUSED), **`netPair`** (diff-pair partner), `PinRef` and `SpecRef`. Copper `Set` elements carry `net`, `netPair` and `SpecRef`, so specs can be bound to nets and features. — [P] [IPC-2581C.xsd](https://webstds.ipc.org/2581/IPC-2581C.xsd)
- **DFX.** `Dfx` (category COMPONENT, BOARDFAB, ASSEMBLY, STACKUP, TESTING or DATAQUALITY) contains `Criteria` (with a measurementMode such as DISTANCE, IMPEDANCE, CURRENT or VOLTAGE_DC) and `DfxQuery`. Responses are YES, NO, APPROVED, CONDITIONALLY_APPROVED, REJECTED, WAIVED, etc. — [P] [IPC-2581C.xsd](https://webstds.ipc.org/2581/IPC-2581C.xsd)
- **No** element types named for clearance rules, length/skew rules or placement rules were found in the C schema. The name grep found only generic length properties and the MIN/MAX enum. — [P] (my schema inspection) [IPC-2581C.xsd](https://webstds.ipc.org/2581/IPC-2581C.xsd)
- **KiCad's IPC-2581 exporter** writes:
  - `Spec` nodes for each stackup layer: material, plus copper conductivity 5.959E7 S/m and dielectric properties.
  - `SURFACE_FINISH` (Rev C only).
  - Backdrill and secondary-drill specs.
  - `LogicalNet`, `PhyNetGroup`, BOM/AVL and `Dfx` section handling.

  The source contains **no `Impedance` spec output**. — [P] [KiCad source: pcb_io_ipc2581.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/pcb_io/ipc2581/pcb_io_ipc2581.cpp)
- Trade-press descriptions of Rev C: impedance at net, layer or stackup level, and a bidirectional DFX module. — [S] [Sierra Circuits](https://www.protoexpress.com/blog/ipc-2581-revision-c-facilitates-pcb-data-management-by-hemant-shah/). The IPC-2581 Consortium's validator checks schema compliance only, not design correctness. — [S] [IPC-2581 File Validation Tool](https://www.ipc2581.com/?p=2506)

**Analog / VLSI constraint formats (placement-relation inspiration)**
- **ALIGN**: typed Pydantic constraints in `<hier>.const.json`. A `HardConstraint` must implement `translate(solver)`, and a `UserConstraint` expands into low-level constraints. Types include Order, Align, Spread, AspectRatio, Boundary, Floorplan, SymmetricBlocks, BlockDistance, Horizontal/VerticalDistance, GuardRing, GroupCaps, NetPriority, NetConst (shield, criticality), SymmetricNets, PortLocation, MultiConnection, Route and GroupBlocks. — [P] [ALIGN constraint.py](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/master/align/schema/constraint.py)
- **FloorSet** (Intel Labs, ICCAD 2026 Problem C base) is a set of synthetic floorplans with 1M training and 100 test samples per variant (Prime: rectilinear; Lite: rectangular). Its hard constraints are fixed-outline, shape (aspect ratio range), boundary (edge or corner), grouping, **multi-instantiation** (partitions that must share one shape) and pre-placement. They are encoded by extending Bookshelf `.blocks` with per-component placement constraints and adding net weights in `.nets`. — [P] [FloorSet arXiv 2405.05480](https://arxiv.org/abs/2405.05480); [P] [ICCAD 2026 contest problems](https://www.iccad-contest.org/2026/Problems.html)
- **KiCadRoutingTools `floorplan-intent.json`** uses strict keys: blocks/zones, keepouts, edge_connectors, decaps, `proximity[]` (ref, near, max_mm, basis), keep_away, replicate, arrays, fixed_poses, must_lock, legality_budget and severity. Unknown keys are refused at load. The intent acts as a monotone per-move gate in the optimizer. — [P] [floorplan-intent.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/floorplan-intent.md)

**Academic "design intent" / constraint-capture work**
- Graph-attention extraction of analog **symmetry constraints** from netlists reports higher accuracy and F1 than earlier symmetry detectors. — [P] [arXiv 2312.14405 abstract](https://arxiv.org/abs/2312.14405)
- **LLANA** uses LLM few-shot priors to speed up Bayesian optimization of analog layout constraint parameters. — [P] [arXiv 2406.05250 abstract](https://arxiv.org/abs/2406.05250)
- **PCBSchemaGen** induces a per-IC domain schema (knowledge graph) from datasheets to ground LLM decoding, pairs it with a deterministic 5-layer verifier with pin-level error localization, and reports 81.3% pass on its PCBBench schematic tasks with Gemma-4-31B. It works on schematics, not layout. — [P] [arXiv 2602.00510 abstract](https://arxiv.org/abs/2602.00510)
- An older ontology formalizes constraint types for custom IC design (prototyped in Protégé). — [S] [An ontology for constraints in custom IC design (ResearchGate)](https://www.researchgate.net/publication/220743841_An_ontology_for_constraints_in_custom_IC_design)
- I found no peer-reviewed paper that defines a formal design-intent language for **PCB layout**, or that uses an LLM to extract **layout** rules from datasheets. Searches returned only vendor and marketing pages. — [S] (negative result across several searches)

### Inferences
- **Rule resolution must be explicit in the IR.** KiCad uses file order (last match wins), Altium explicit numeric priority (and Matched Lengths rules accumulate), JITX logical specificity, and Allegro object-precedence with CSet assignment. An IR that compiles to KiCad must emit rules in a deterministic order that reproduces the IR's own resolution semantics. JITX's "more specific condition wins", ordered general-to-specific when compiled to KiCad, is the most LLM-friendly choice, because it is order-independent for the author.
- **Allegro's pin-pair / match-group / Xnet abstractions and JITX's topology + pin-model abstractions** are the right primitives for timing constraints. Length belongs to a pad-to-pad path through series parts, not to a net. KiCad covers part of this with `fromTo()` plus `length`/`skew`. tscircuit's `maxLengthSkew` on buses and pairs is a simpler subset.
- **"Keep C5 within 2 mm of U1 pin 7 with via to GND plane" in each system:**

  | System | How it expresses this |
  |---|---|
  | tscircuit | Constructively, as an equality: `pcbX="calc(U1.pin7.x + …)"` |
  | Quilter | As a Bypass Capacitor constraint checked by Pin Distance, Layer Switch Count, Ground Plane Overlap and Trace Path Length PRCs |
  | KiCadRoutingTools | As `proximity[]` or `decaps.max_pin_distance_mm` |
  | KiCad | Only as a post-route `fromTo('U1-7','C5-1')` + `length (max 2mm)` proxy |
  | IPC-2581 | Not at all |

  The IR needs a native `proximity(pad, pad, max, basis)` primitive and a `via_to_plane(pad, net, max_dist)` primitive, and must compile them to checkers.
- **IPC-2581C is useful as an *input* for impedance and stackup intent** (Impedance spec with transmission structure and RefPlane, Loss, netClass category, netPair) when importing from Altium or Allegro. It is not useful as a carrier of placement or routing rules. KiCad does not export impedance specs, so a KiCad-native IR must carry them itself, for example via KiCad 10 tuning profiles.
- **IPC-2581 DFX** (Criteria / DfxMeasurement / DfxQuery / DfxResponse with severity and waiver states) is a good model for the IR's *findings and waivers* channel. A finding is a measurement with a severity, and a response can be APPROVED, WAIVED or REJECTED with a comment. This mirrors KiCad DRC exclusions.
- Quilter's design (automatic detection from schematic patterns, then a user-editable constraint list, then named PRCs with explicit pass criteria and units) is a practical template for an LLM system. The LLM proposes constraints with detection evidence, a human confirms them, and deterministic PRC-style checkers grade every candidate.

### Gaps
- Primary Cadence documentation is login-gated. Allegro facts come from a channel-partner note [3P] and a search summary of the 16.3 user guide [S].
- The IPC-2581C standard text (paid) was not read; only the XSD was. Semantics of how `SpecRef` on `LogicalNet` versus `Set` is meant to bind impedance targets are inferred from the schema structure.
- I found no formal PCB-specific design-intent language in the academic literature, and no LLM datasheet-to-layout-rule extraction paper.

---

## Q2. Which open-source or scriptable tools can score a layout beyond DRC (SI, PI, EMI, thermal, parasitics), which are fast enough for an optimization loop, and are there ML surrogates?

### Takeaway
The open stack now spans every tier:
- **kicad-cli DRC** (JSON output, exit codes, refill, parity).
- **Heuristic and analytic checkers**: return-path/plane-split checks, decap distance, crosstalk proxies, Transcalc impedance, IPC-2221.
- **2.5D solvers**: DC IR drop and PDN impedance (padne, KiPI, Ki-PIDA).
- **Full-wave and FEM**: openEMS via gerber2ems and si-wrapper (CI-automatable, VNA-validated), and FreeCAD + gmsh + CalculiX thermal (Antmicro) or Salome + Elmer current-conduction flows. Palace is an emerging FEM backend with C/L matrix extraction.

For speed, KiCad-native rule routers run in seconds per board (PCBWorld: Freerouting about 7 s and KRT about 0.65 s per small real board). An example gerber2ems run processes about 294 Mcells/s, roughly 34 s per excitation for a 10k-step run. A trained PDN-impedance DNN answers in 0.1 s.

ML surrogates exist for PDN impedance (DNN over more than 1M BEM-labelled boards), decap selection (DevFormer DPP), eye metrics and pre-layout SI (buffer-parameterized and differentiable surrogates), and coupled-line crosstalk (MLP, LS-SVM). None is layout-generic or open and KiCad-integrated. I found no maintained layout-level EMI or thermal surrogate.

### Cited Findings

**Legality / DRC (KiCad)**
- `kicad-cli pcb drc` takes `--format json`, `--severity-*`, `--schematic-parity`, `--refill-zones` and `--exit-code-violations` (exit 5 on violations). — [P] [kicad-cli docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/cli/cli.adoc)
- The `drc.v1.json` report schema has `violations[]` (type, description, severity, items[uuid, description, pos], excluded, comment), `unconnected_items[]`, `schematic_parity[]` and `ignored_checks[]`. — [P] [drc.v1.json](https://gitlab.com/kicad/code/kicad/-/blob/master/resources/schemas/drc.v1.json)
- `kicad-cli` also exports XAO, BREP and STEP, which feed FEM meshing (see the thermal flows below), and `pcb export stats --format json`. — [P] [kicad-cli docs](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/cli/cli.adoc)

**Impedance calculators**
- KiCad PCB Calculator TransLine is based on Transcalc and covers microstrip, CPW, grounded CPW, coax, coupled microstrip, stripline and twisted pair. Its Track Width tool uses IPC-2221. — [P] [pcb_calculator.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcb_calculator/pcb_calculator.adoc)
- KiCad 10 tuning profiles compute geometry and unit delay from target impedance. — [P] [pcbnew_create_board.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_create_board.adoc)

**Full-wave EM: openEMS / gerber2ems / si-wrapper**
- openEMS is an EC-FDTD solver written in C++ with Python and Octave interfaces. The engine is **GPLv3+** and CSXCAD is **LGPLv3+**; it was started by Thorsten Liebig (Univ. Duisburg-Essen) in 2010. Most users build from source with `update_openEMS.sh`; ready-made packages exist for Windows, FreeBSD and macOS. — [P] [openEMS intro](https://docs.openems.de/en/latest/intro.html); [P] [openEMS install](https://docs.openems.de/en/latest/install/index.html); [P] [requirements](https://docs.openems.de/en/latest/install/requirements.html)
- **gerber2ems flow** (Apache-2.0):
  - **Inputs**: per-layer Gerbers named `*-<stackup-layer>.gbr`, `stackup.json`, an Excellon PTH drill file, a `-pos.csv` with `SP*` port designators, and `simulation.json`.
  - **`-g` geometry step**: gerbv converts Gerbers to PNG at `pixel_size` (default 5 µm; must be raised for large boards because of a libcairo limit). The PNGs are triangulated and stacked by stackup Z.
  - **`-s` simulate**: iterates over every excited port.
  - **`-p` postprocess**: FFT to S-parameters and impedance CSV plus plots.
  - **Grid defaults**: `optimal` 50 µm, `diagonal` 50 µm, `perpendicular` 200 µm, `max` 500 µm, 4 inter-layer lines, `margin` 1500 µm, and grid pitch must be ≤ λmin/10.
  - **Ports** must be at least 8× the mesh cell long. **Capacitors** are not simulated and are shorted with a trace.
  - **Runtime guidance**: the README's example log shows "Excitation signal length is: 3211 timesteps … Max. number of timesteps: 10000", and recommends at least 3× the pulse length. A sample engine line reads "Timestep: 4620 || Speed: 294.4 MC/s (3.372e-03 s/TS)".
  - Field exports "can easily take hundreds GB".

  — [P] [gerber2ems README](https://github.com/antmicro/gerber2ems)
- **kicad-si-simulation-wrapper** (`si-wrapper`) requires KiCad 9.0.x and was tested with 9.0.2 on Debian 12. It selects nets (for example from a "controlled impedance" net class), creates **slices**: the net or pair, neighbouring nets within a configurable distance and neighbour-point threshold, and all vias and planes in the area. It shorts 0 Ω resistors and large caps, terminates neighbours with nominal impedance (power and low-speed nets with 0 Ω), and auto-places ports as virtual footprints, prompting the user when the trace isn't two-point. It also writes `netinfo` (name, width, length, impedance, diff flag). — [P] [si-wrapper README](https://github.com/antmicro/kicad-si-simulation-wrapper); [P] [Antmicro blog 2024-07](https://antmicro.com/blog/2024/07/automated-pcb-trace-selection-for-si-simulation)
- **Antmicro's July 2025 update**:
  - An **adaptive grid**, dense around the trace of interest and sparse elsewhere, replaced equidistant grids.
  - Differential-pair simulation and **trace delay** estimation were added for intra-pair skew checks.
  - Slicing improved and `ems2paraview` was added.
  - The flow "operate[s] mostly without manual tweaking", so it can run in CI for regression tracking.
  - Results were **validated against VNA measurements** on the RDIMM DDR5 Tester clock pair; S-parameters "match pretty well in both character and order of magnitude". Antmicro's open 50 Ω VNA probe is used for low bands, and soldered coax for high bands.

  — [P] [Antmicro blog 2025-07](https://antmicro.com/blog/2025/07/recent-improvements-to-antmicros-signal-integrity-simulation-flow)
- The 2023 introduction used a reference SI test board for validation, with PyBERT eye diagrams from gerber2ems output. — [P] [Antmicro blog 2023-11](https://antmicro.com/blog/2023/11/open-source-signal-integrity-analysis)
- Other openEMS front-ends:
  - pcbmodelgen: KiCad to Octave models. — [P] [pcbmodelgen](https://github.com/jcyrax/pcbmodelgen)
  - KiCad Electrodynamic & Static Studio: `kipy` extraction, headless `run_openems.py`, a C++ MNA DC solver, scikit-rf vector fitting. — [P] [repo](https://github.com/ravid1323/KiCad-Electrodynamic-Static-Studio)
  - The PCB_SI_Toolkit openEMS tab: S-parameters and TDR/TDT. — [P] [repo](https://github.com/ugo-silato/PCB_SI_Toolkit)
  - SPIKE's openEMS and EMerge extensions. — [P] [repo](https://github.com/krishna-swaroop/SPIKE)
- **Palace** (AWS, Apache-2.0) is a parallel 3D FEM code built on MFEM and libCEED. It does eigenmode, frequency-domain driven (lumped and wave ports, adaptive fast sweep) and time-domain analysis, **lumped capacitance and inductance matrix extraction** (electrostatic and magnetostatic), and adaptive mesh refinement (AMR). — [P] [awslabs/palace README](https://github.com/awslabs/palace)
- **FastHenry/FastCap** are MIT-origin inductance and capacitance solvers with 64-bit ports. — [P] [FastHenry2](https://github.com/ediloren/FastHenry2); [P] [FastCap2](https://github.com/ediloren/FastCap2)
- **scikit-rf** (BSD) handles Touchstone and network analysis. — [P] [scikit-rf](https://github.com/scikit-rf/scikit-rf)

**DC IR drop / PDN**
- **padne** is a KiCad-native **2.5D FEM** Laplace solver. Sources and sinks are declared as schematic text directives, e.g. `!padne VOLTAGE v=3.3V p=U1.1 n=U1.4`. It has a Qt GUI and ParaView export, CI tests, a bundled about 200 MB Linux binary that includes KiCad, and more than 30 KiCad test projects. — [P] [padne README](https://github.com/atx/padne); [P] [KiCad forum: Presenting padne (2025-10)](https://forum.kicad.info/t/presenting-padne-a-tool-for-dc-power-delivery-network-analysis/64966)
  - The author says the FEM core is about 40 lines and "the vast majority of work developing these tools is ferrying data around". The **via model** (resistors stitching via-opening edges across layers) is uncertain except for "large and short" vias, and needs test-board validation. The author suggests awslabs/palace as a possible larger backend. A user reported macOS install failure (KiCad Python 3.9 vs padne's 3.10+ `match`). — [P] [same thread](https://forum.kicad.info/t/presenting-padne-a-tool-for-dc-power-delivery-network-analysis/64966)
- **KiPI** (GPL-3.0, 0.9.1 alpha) covers DC drop, an AC PDN impedance sweep against a target-impedance calculator, and switcher **coupled noise**, with YAML setup and HTML/PDF reports. — [P] [KiPI](https://github.com/drewsum/KiPI)
- **Ki-PIDA** (KiCad 9+, IPC API) is a hybrid 2.5D resistive mesh with electro-thermal coupling. — [P] [KiPIDA](https://github.com/kbralten/KiPIDA)
- **PCB_SI_Toolkit** (KiCad 10) has measured-vs-limit layout checks: decap distance, plane edge 3×h, reference changes without ground vias, a DC network, a 2D field solver for Z0, NEXT estimates, and an openEMS tab. — [P] [PCB_SI_Toolkit](https://github.com/ugo-silato/PCB_SI_Toolkit)
- The KiCad core team has made no commitment to built-in SI/PI. A July 2026 forum request for FEM-like SI/PI in KiCad got no developer response before auto-closing. — [P] [KiCad forum thread](https://forum.kicad.info/t/future-plans-for-basic-signal-integrity-si-power-integrity-pi-funtionality/70585). A GitLab issue (#8398) tracking FEM integration "has not seen much progress in the last 6 years", per a forum user. — [3P] [padne thread](https://forum.kicad.info/t/presenting-padne-a-tool-for-dc-power-delivery-network-analysis/64966)

**EMI / return path heuristics**
- `return_path` flags VOID, ISLAND, SPLIT, TERMINAL, VIA and EDGE on a 0.05 mm A* raster and gives a loop-area estimate. — [P] [kicad-tools](https://github.com/jasonarnoldarnie/kicad-tools)
- **emcvisual** uses Biot–Savart with image currents and about 30 rule checks. Its fast far field agrees with openEMS "within 1 dB between 30 and 350 MHz" on a validation board. — [P] [emcvisual](https://github.com/tombueng/emcvisual)
- kicad-happy's EMC skill has 44 rules. — [P] [kicad-happy](https://github.com/aklofas/kicad-happy)
- kicad-emi-guardian is described by its author as "not an EMC compliance instrument". — [P] [repo](https://github.com/hap231/kicad-emi-guardian)
- Allegro's commercial equivalents are the **Return Path DRC**, Max xtalk and Max parallel modes (High-Speed option). — [3P] [Parallel Systems note](https://www.parallel-systems.co.uk/wp-content/uploads/2020/02/Constraint_modes.pdf)

**Thermal (FEM) flows**
- **Antmicro thermal-simulation-scripts**:
  - Tools: FreeCAD 1.0.0 for geometry, surface constraints and meshing (gmsh or netgen); CalculiX 2.20 (`ccx`) as solver; `ccx2paraview`; ParaView 6.0.0; Blender via PCBooth.
  - CLI: `tpre parse-fcstd` → `.inp` plus `simulation.json`, then `ccx file.inp`, then `ccx2paraview file.frd vtk`, then `tpost csv/plot/preview/animation`. The output CSV holds max/min temperature over time.
  - Validation: an RPi5 enclosure at 2.5 W and 8 W, with film coefficients of 5.14 and 6.61 W/(m²K) and 100 min of simulated time to equilibrium, compared with thermocouple measurements; also vacuum-chamber tests with emissivity 0.77.
  - Antmicro describes the flow as "invoked from the command line" and suitable for CI.

  — [P] [thermal-simulation-scripts README](https://github.com/antmicro/thermal-simulation-scripts); [P] [Antmicro blog 2025-03](https://antmicro.com/blog/2025/03/open-source-thermal-simulation-analysis-and-visualization/)
- **KiCad + Salome + ElmerFEM current-conduction flow** (2024):
  1. KiCad 8.99/9 exports **XAO** with only the copper of interest (net filter, fused shapes).
  2. Salome defines input/output face groups and a 1D-2D-3D mesh (min/max of about 0.02–0.08 mm worked) and exports UNV.
  3. Elmer runs "static current conduction".
  4. Results are viewed in ParaView.

  The author calls it "a bit tedious" with "four different software packages". The post covers current and voltage (Joule-heating inputs) rather than full thermal analysis. — [P] [jrainimo: Open-Source Thermal Simulation of PCBs](https://jrainimo.com/build/2024/11/oss-thermal-simulation-of-pcbs/)
- Lighter-weight options: SPIKE's layered steady/transient board-thermal models, KiPI's optional board temperature and Ki-PIDA's electro-thermal coupling. — [P] [SPIKE](https://github.com/krishna-swaroop/SPIKE); [P] [KiPI](https://github.com/drewsum/KiPI); [P] [KiPIDA](https://github.com/kbralten/KiPIDA)
- Quilter's analytic "Overheated Length" PRC (trace segments with temperature rise above 20 °C) is a cheap thermal proxy. — [P] [Quilter PRC](https://docs.quilter.ai/physics-rule-checks-prcs/overheated-length)

**Speed evidence**
- **PCBWorld per-rollout wall time** (@5 protocol, seconds):

  | Router | D2 | D3-A (99 small real boards) | D3-B (10 medium) |
  |---|---|---|---|
  | Freerouting 2.1.0 | 2.69 | 7.09 | 9.94 |
  | KiCadRoutingTools | 0.82 | 0.65 | 3.27 |
  | PPO policy | 0.43 | 1.83 | — |
  | GPT-5.4 interactive agent | — | 231 | 866 |

  — [P] [PCBWorld paper Table 3](https://arxiv.org/html/2607.05915v2)
- In the gerber2ems sample log, 3.37 ms/timestep × 10,000 steps ≈ 34 s per excited port for that example's mesh. This is a derived figure: runtime scales with cell count, steps and number of ports. — [P] (derived from) [gerber2ems README](https://github.com/antmicro/gerber2ems)
- An analytic radiated-power method gives results in 30 s versus about 5 h for full-wave. — [S] [Microelectronics Journal](https://www.sciencedirect.com/science/article/abs/pii/S0026269221002445)

**ML surrogates**
- **PDN impedance DNN** (Zhang et al., Missouri S&T, 2021): BEM labels over more than **1M random boards** varying shape, stackup, IC location and decap placement. It generalizes to unseen configurations in **0.1 s**, over 100× faster than BEM and **5000× faster than full-wave**. — [P] [arXiv 2106.10693](https://arxiv.org/abs/2106.10693). A search snippet of the journal version says 10,000×. — [S] [Wiley IJNM](https://onlinelibrary.wiley.com/doi/10.1002/jnm.2956) (conflict between versions noted)
- **DevFormer / DPP benchmark** (KAIST, ICML 2023): a symmetric transformer for decap placement that reduces component count by more than 30% with improved performance in simulated and real hardware. The open **DPP benchmark** provides a simulator call `decap_sim(probe=23, solution=[1,5,7], keep_out=[2,3,10])`, is also available as RL4CO environments, and was used by ReEvo (NeurIPS 2024) for LLM-discovered heuristics. — [P] [arXiv 2205.13225](https://arxiv.org/abs/2205.13225); [P] [devformer README](https://github.com/kaist-silab/devformer)
- **SI eye-metric surrogates**: buffer-parameterized models compare tree, kernel, GPR and NN methods on a 44-parameter interconnect; NNs win with large data and anisotropic GPR with little data. — [P] [arXiv 2605.18170](https://arxiv.org/abs/2605.18170). Amortized neural optimization trains a policy through a differentiable surrogate: about 10% optimality loss for 10³–10⁴× speedups, and a 320,000-instance SerDes sweep in milliseconds. — [P] [arXiv 2606.07463](https://arxiv.org/abs/2606.07463)
- **Crosstalk surrogates**: MLP time-domain crosstalk for coupled lines, and an LS-SVM for worst-case crosstalk under tolerances. — [S] [Springer NCA](https://link.springer.com/article/10.1007/s00521-019-04252-3); [S] [Sci. Reports](https://www.nature.com/articles/s41598-023-42728-4)
- **EMI**: the only layout-to-emission neural work found is a 2003 IEICE paper that predicts far-field spectra from near-field spectra. — [S] [IEICE 2003](https://globals.ieice.org/en_transactions/communications/10.1587/e86-b_4_1364/_p)
- An unsupported vendor claim of 100–1000× neural-operator speedups. — [S] [AtlasPCB blog](https://www.atlaspcb.com/blog/ai-accelerated-pcb-simulation-ml-si-pi-thermal/)

### Inferences
- **Loop tiers.**
  - **T0 (µs–ms)**: geometry, intent and PRC-style checks; Transcalc Z0 and delay; IPC-2221; a PDN-impedance DNN if trained for the board class.
  - **T1 (sub-second to seconds)**: kicad-cli DRC; raster return-path; Biot–Savart near field. Rule routers at 0.65–10 s per small or medium board are fast enough as post-route evaluators inside a placement loop, which is how Cypress used Freerouting.
  - **T2 (seconds to minutes)**: 2.5D IR drop (padne, KiPI), PDN sweeps.
  - **T3 (minutes to hours)**: openEMS per critical net or pair via si-wrapper slices; FreeCAD/CalculiX or Elmer thermal.
- The **si-wrapper slice approach** is directly reusable for an automated loop: pick constrained net classes, slice, short passives, terminate neighbours, auto-place ports. Antmicro's claim of CI-ability and VNA validation makes it the most production-ready open SI verifier for KiCad, though only on KiCad 9.0.x so far.
- Thermal FEM needs geometry/mesh tooling (FreeCAD/Salome/gmsh) and is not yet a one-command KiCad flow. For an optimizer, use analytic proxies (Quilter-style overheated length, Ki-PIDA electro-thermal) and run FEM only for sign-off.
- The surrogate literature points to a **training-data strategy**. The PDN DNN was trained on more than 1M *synthetically generated* boards labelled by a fast physics solver (BEM). The same recipe applies here: use padne, KiPI, return_path or si-wrapper slices as fast labellers on synthetic KiCad boards to train layout-level surrogates. No ready-made open surrogate exists.

### Gaps
- Thermal-ML and EMI-ML surrogate searches could not be completed because the shared search budget was exhausted. Coverage there is thin.
- I found no published wall-clock numbers for kicad-cli DRC versus board size, padne/KiPI solve times, or a full gerber2ems DDR-net slice.
- The ElmerCSC README and FreeCAD FEM wiki were not readable (fetch refused or bot challenge). Elmer facts come from the jrainimo post only.
- The validation of KiPI, Ki-PIDA, padne and SPIKE against measurement or commercial tools is not documented beyond the authors' own caveats.

---

## Q3. Which layout quality metrics exist beyond DRC, and how do Quilter, DeepPCB and academic and open benchmarks report quality? Are there "human-like" or "expert-acceptable" metrics?

### Takeaway
Metrics have converged into three layers:
- **Absolute legality and connectivity**: Clean Pass / NRR / PRR, open, physical-short and logical-short rates, DRV by cause.
- **Efficiency**: wirelength, vias, layers, runtime.
- **Physics PRCs**: pin distance, layer switches, ground-plane overlap, length mismatch, uncoupled spacing, overheated length.

There is now one published **reference-relative "human-likeness" metric**, OmniRouting's Multi-Scale Graph Similarity (MGS). Human reference boards are not perfect: in OmniRouting they reach only 93.58% NRR under the published DRC. Placement-specific metrics include HPWL, overlap, out-of-bounds, net crossings, net separation, routability after a fixed router, and intent conformance.

### Cited Findings
- **PCBWorld** reports CP (fully connected and 0 error-level DRVs), Potential gain (Φ over unconnected, DRV, WL and vias), Routability, DRV, WL, Via, Time and Parse-fail. It uses @5 best-of-five selection by potential gain, with Time averaged over all rollouts, and DRC re-run on saved boards against each board's own rules. — [P] [PCBWorld METRICS.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/METRICS.md); [P] [paper §4.3](https://arxiv.org/html/2607.05915v2)
- **OmniRouting** definitions:
  - **PR**: load and schema success.
  - **NRR**: % of expected nets connected and DRC-clean.
  - **PRR**: % of the Σ(|Pₙ|−1) minimum pad connections routed and DRC-clean. Missing outputs stay in denominators.
  - **Open / PShort / NShort**: PShort counts only different-net wire–wire and via–wire contacts.
  - **Clr. / Dist.**: violation counts by cause.
  - **Polygon** (copper-pour usage), **TWL**, **#Vias**, **#Layers**, **RT**.
  - **MGS**: predicted and reference routings become pad-aware, layer-specific graphs at coarse (corridor/topology) and fine (geometry) resolution, with the coarse graph weighted more. MGS measures agreement with the expert reference, not correctness.

  — [P] [OmniRouting arXiv 2608.04434 (HTML)](https://arxiv.org/html/2608.04434v1)
- **OmniRouting results**:
  - The **human engineer reference** scores NRR 93.58%, PRR 95.91%, Open 4.38%, PShort 0.38%, Clr. 0.80.
  - The best zero-shot LMM gets NRR/PRR 12.60/15.41%; agentic refinement reaches only 27.98/30.34%.
  - The OpenROAD PcbRouter baseline gets 56.20% NRR and 71.37% PRR.
  - Base LMM outputs average 69.77–431.29 DRC violations.
  - "Feedback quality matters more than iteration count."

  — [P] [OmniRouting HTML](https://arxiv.org/html/2608.04434v1)
- **Quilter** candidate metadata: % of pins routed, DRC count (candidates with DRC errors are not surfaced), single- or double-sided, layer count, minimum trace width, clearance, via and drill used, and via count. PRCs carry explicit pass criteria and units, e.g. Pin Distance 0–1 cm and Overheated Length 0–10%. — [P] [Quilter: candidate details](https://docs.quilter.ai/candidate-review/candidate-details); [P] [PRCs](https://docs.quilter.ai/physics-rule-checks-prcs/overview)
- **Cypress** (ISPD 2025 Best Paper) measures placement quality as **routability = % of routed pin pairs using Freerouting v1.9.0 with two free copper layers at default settings**. It also reports routed track length and runtime. Claims: 1–5.9× higher routability, 1–19.7× shorter routed track length on fully routed designs, and up to 492.3× runtime speedup. Baselines are SA-PCB (OpenROAD) and NS-Place/NS-Place+ (ASP-DAC'22). — [P] [Cypress ISPD slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf); [S] [ISPD'25 TOC abstract](https://www.sigda.org/publications/ispd-25-toc/); [S] [Cornell news (award)](https://zhang.ece.cornell.edu/news/cypress_ispd_bpa.html) (title via search; the ISPD slides list it as a "Best Paper Nominee")
- **RL_PCB** uses HPWL, Euclidean WL, overlap and post-route WL against a simulated-annealing baseline. — [P] [RL_PCB](https://github.com/LukeVassallo/RL_PCB)
- **KiCadRoutingTools** argues that "crossings and hpwl … are indifferent between a sensible layout and a scattered one", which motivates floorplan-intent grading. — [P] [floorplan-intent.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/floorplan-intent.md)
- Quilter's own blog says routing metrics without first-pass yield or bring-up data do not prove boards work. — [S] [Quilter blog](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai)

### Inferences
- **Recommended metric set**, a union of PCBWorld, OmniRouting, Quilter and Cypress:
  - **Gates**: PR/loadable, LVS parity, CP.
  - **Routing**: NRR, PRR, Open/PShort/NShort, DRV by cause, TWL, vias, layers, RT.
  - **Placement**: HPWL, overlap, OoB, net crossings, net separation, Freerouting-based routability (Cypress protocol), intent conformance.
  - **Physics PRCs**: pin distance, layer-switch count, ground-plane overlap, length mismatch, uncoupled spacing, overheated length, return-path violations, IR-drop margin.
  - **Human-relative**: MGS-style graph similarity plus WL, via and HPWL ratios to the human board.
- Because human boards are themselves not DRC-clean under their declared rules (OmniRouting human NRR 93.58%; PCBWorld keeps only boards that were DRV-free after conversion), report human scores on the same metrics and normalize. Don't assume the human reference is 100%.
- MGS rewards imitation. Use it as a *diagnostic* of human-likeness, not as an objective, because valid alternative routes score low on it.

### Gaps
- The full Cypress paper (ACM, bot-walled; Cornell PDF has TLS errors) was not read. Per-design tables and the benchmark statistics table are unread.
- I found no human-rated aesthetic or "expert acceptability" dataset.

---

## Q4. What datasets and benchmarks exist for training or evaluating PCB placement and routing, and how could a benchmark be built from open-source KiCad repos?

### Takeaway
**There are no ISPD or ICCAD contest problems on PCB or package routing or placement.**
- ISPD contests from 2005 to 2027 are all IC or FPGA topics.
- ICCAD contest routing problems are IC-level (bus routing 2018, routing with cell movement 2020/2021).
- ICCAD 2026's problems are LLM netlist exploration, regression bucketing and FloorSet floorplanning.

The usable PCB benchmarks are:
- **PCBWorld-Bench** (routing; KiCad-native; 679 PCBench-derived real boards in D3-A/B/C plus synthetic D1/D2; human reference copper).
- **Cypress** (placement; NVlabs, Apache-2.0; small benchmarks synthesized from commercial designs plus 5 large commercial ones; Freerouting-routability protocol).
- **OmniLayout/OmniRouting** (1,681 Eagle-derived designs; strong metric protocol; data not openly licensed).
- **PCBench** (164-board routing corpus in its README).
- **RL_PCB** (small).
- **tscircuit SRJ datasets** (lossy).
- **DevFormer DPP** (decap placement sub-problem).
- **FloorSet** (VLSI floorplanning with constraints; a design analogue).

### Cited Findings
- **ICCAD CAD Contest history** lists no PCB or package problem. Routing problems are obstacle-aware on-track bus routing, routing with cell movement (and its advanced version), system-level FPGA routing with TDM, and LEF/DEF open-source global routing. Placement problems include 3D placement with D2D vertical connections, 3D placement with macros, and routability-driven placement. — [P] [ICCAD contest history](https://www.iccad-contest.org/2025/History.html)
- **ICCAD 2026** problems: A — LLM-Assisted Netlist Exploration and Transformation; B — Regression Failure Bucketing; C — The FloorSet Challenge: Data-Driven SoC Floorplanning. — [P] [ICCAD 2026 Problems](https://www.iccad-contest.org/2026/Problems.html)
- **ISPD contests 2005–2026**: placement, global routing, clock synthesis, gate sizing, detailed-routing-driven placement, FPGA placement, initial detailed routing, wafer-scale, security closure, GPU/ML global routing (2024), performance-driven global routing (2025), post-placement buffering and sizing (2026). ISPD 2027 is MCMM post-CTS buffering and sizing on ASAP7. — [P] [ISPD previous contests](https://ispd.cc/?page=contests); [P] [ISPD27-Contest README](https://github.com/ABKGroup/ISPD27-Contest)
- **PCBWorld-Bench** (v1.1.0, BSD-3; engine GPLv3; KiCad 9.0.8):
  - **D1** (grid): 10,000/128/128 boards, 5 nets, 1 layer.
  - **D2** (gridless): 10,000/128/128, 4–6 nets, 2 layers.
  - **D3-A** (small, 100 boards: 2–13 nets, 6–31 pads), **D3-B** (medium, 287: 5–42 nets, 31–100 pads), **D3-C** (large, 292: 6–451 nets, 101–2,103 pads). 2–4 layers.
  - **D3** is "679 boards derived from PCBench's open-source PCB corpus (He et al., 2024)". Boards were converted to KiCad 9 with their design rules kept, and only boards still fully connected and DRV-free after conversion were retained. Each keeps its original routing as the reference.
  - Zero-shot evaluation uses 99 D3-A and 10 D3-B boards. D3-C is reserved as a challenge split.

  — [P] [PCBWorld paper](https://arxiv.org/html/2607.05915v2); [P] [PCBWorld README](https://github.com/LGAI-Research/PCBWorld)
- **PCBWorld Table 3** (CP on D3-A / D3-B, @5):

  | Method | D3-A CP | D3-B CP |
  |---|---|---|
  | Freerouting | 0.80 | 0.78 |
  | KRT | 0.74 | 0.20 |
  | OrthoRoute | 0.02 | 0.00 |
  | PPO (synthetic-only training) | 0.86 | 0.45 |
  | PPO (w/o finish) | 0.94 | 0.42 |
  | GPT-5.4 interactive | 0.65 | 0.00 |

  "All LLM agents nonetheless obtain 0.00 CP on D3-B". On D3-A, GPT-5.4 scores CP **0.65 interactive vs 0.19 plan-and-execute vs 0.02 engine-free**, with DRV 1.31 vs 16.28 vs 34.58. "Leveraging the native API is essential for design-rule-clean routing." — [P] [PCBWorld paper Tables 3–4](https://arxiv.org/html/2607.05915v2)
- **PCBench** README: "a dataset for PCB routing" with **164 PCBs**. Each has raw and processed `.kicad_pcb`, `final.json` (PCB-RDL), metadata and a PNG; the repo adds net-subsampling augmentation and a grid RL environment. — [P] [PCBench](https://github.com/PCBench/PCBench). **Conflict**: PCBWorld derives 679 boards from "PCBench's corpus". The README count may be outdated, or PCBWorld may count design versions or a larger pool. This is unresolved.
- **Cypress benchmark**: the ISPD slides describe **10 small benchmarks** synthesized "based on functionality" (Ethernet controller, power controller, GPIO expander, CPLDs, …) with component shapes, side assignment, pin positions and nets, plus **5 commercial big benchmarks**. The NVlabs repo (Apache-2.0, 55★, built on DREAMPlace) has a `benchmarks/` folder listing at least `small-1`…`small-20`, so the count differs from the slides. The repo also has a `pcb-util/` folder. — [P] [Cypress slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf); [P] [NVlabs/Cypress](https://github.com/NVlabs/Cypress); [P] [benchmarks tree](https://github.com/NVlabs/Cypress/tree/main/benchmarks)
- Cypress's placement formulation: SMD non-critical components on a rectilinear two-sided board; pre-assigned sides; constraints of spacing, non-overlap, and fixed critical and mechanical components; an orientation-aware LogSumExp wirelength; a two-sided electrostatic density; and a net-crossing model. — [P] [Cypress slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf)
- **OmniLayout** (77.24K placement instances) and **OmniRouting** (2–8 layers, human reference routings, four tasks including tool-augmented agentic routing) draw on 1,681 designs collected from SparkFun, Arduino, Adafruit, GitHub and others. They promise to "open-source all benchmark data, evaluation code, and tool interfaces". — [P] [OmniRouting abstract and HTML](https://arxiv.org/abs/2608.04434); [P] [OmniLayout abstract](https://arxiv.org/abs/2607.03261). A third-party audit (2026-08-15) found Eagle-9.6.2-derived JSON, 5 public sample boards, no data license, and CC BY-NC-ND papers. — [3P] [kicad-tools OmniLayout recon](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/omnilayout-recon.md)
- **PCB-Bench** (ICLR 2026) is a knowledge benchmark: about 3,700 text QA/CQ, about 500 image-text items, and 174 OSHWHub designs for screenshot-to-description. — [P] [PCB-Bench README](https://github.com/digailab/PCB-Bench)
- **Other datasets**:
  - **RL_PCB**: 6 training circuits. — [P] [RL_PCB](https://github.com/LukeVassallo/RL_PCB)
  - **tscircuit `dataset-srj18`**: 16 boards from KiCad, 5 Arduino + 11 Antmicro. — [P] [dataset-srj18](https://github.com/tscircuit/dataset-srj18)
  - **SRJ format**: drops net-class widths, clearances, zones and keepouts. — [3P] [kicad-tools README](https://github.com/rjwalters/kicad-tools)
  - **DevFormer DPP**. — [P] [devformer](https://github.com/kaist-silab/devformer)
  - **FloorSet** (2×1M synthetic floorplans with hard constraints). — [P] [arXiv 2405.05480](https://arxiv.org/abs/2405.05480)
- **Older academic PCB routing work** (bus, escape and substrate routing) mostly used proprietary or industrial instances. An example is SAT-based multi-layer BGA escape routing on a 28×28 BGA with about 380 signals (ICCAD 2016). — [S] [MonoSAT BGA escape routing](https://www.cs.ubc.ca/labs/isd/Projects/monosat/monosat_bga_iccad2016.pdf); [S] [Substrate topological routing (TCAD 2008)](https://shenghua-liu.github.io/assets/pdf/papers/tcad2008_substraterouting.pdf)

### Inferences
- Since no contest benchmark exists, **PCBWorld D3 (routing) plus Cypress (placement) are the closest to "standard" open benchmarks**. Both are KiCad- or Freerouting-grounded. Use Cypress's protocol (Freerouting routability on two free layers) as a placement-quality evaluator, and PCBWorld's CP@5 protocol as the routing evaluator.
- **PCBWorld's construction recipe** answers how to build a benchmark from open KiCad repos: convert to the current KiCad version, keep each board's own rules, drop boards not fully connected and DRV-clean after conversion, keep human copper as reference, and split by pad count. Extend it with placement-stripped variants: keep the outline, mechanical parts, connectors and locked parts, and re-place everything else. Then score placement through a fixed router (Cypress protocol) and compare with the human placement routed by the same router.
- The PCBWorld finding that engine-free LLM agents get CP 0.02 against 0.65 for engine-interactive ones is a strong architectural signal. An LLM placer/router should act **through KiCad's router and DRC**, as tools with feedback, and never emit raw geometry.

### Gaps
- I could not confirm whether Taiwan's MOE domestic CAD contest (separate from the international ICCAD track) ever ran a PCB problem; nothing surfaced.
- The Cypress benchmark statistics table and large-benchmark availability (the commercial ones are likely not public) remain unread.
- PCBench's 164 vs 679 discrepancy and per-board licenses are unresolved.

---

## Q5. How can datasheet reference layouts and existing open-source boards be reused as templates (layout retrieval)?

### Takeaway
Reuse primitives exist across tools. Retrieval over a corpus, and extraction of datasheet layout guidance, remain unbuilt in open source and absent from the academic literature I found.
- **KiCad**: design blocks with schematic and layout fragments; multichannel Repeat Layout.
- **atopile**: sub-module build targets plus KiCad "pull group".
- **JITX**: circuit-port forwarding, so constraints written at a sub-circuit boundary apply in any parent.
- **tscircuit**: groups with relative or packed layout.
- **Altium**: rooms that move their components.
- **Quilter**: automatic detection of bypass caps and switchers from schematic patterns.

### Cited Findings
- KiCad design blocks can hold schematic and/or layout fragments in `.kicad_blocks` libraries. A saved layout can be applied to the footprints matching the schematic fragment. — [P] [pcbnew_design_blocks.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_design_blocks.adoc)
- Multichannel Repeat Layout requires equivalent channels: the same symbol count, refdes prefixes, footprints and connectivity. — [P] [pcbnew_multichannel.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_multichannel.adoc)
- atopile's layout reuse: build the `Sub` module as its own target, lay it out in KiCad, then use "atopile pull group" in the top layout. — [P] [examples/layout_reuse](https://github.com/atopile/atopile/blob/main/examples/layout_reuse/layout_reuse.ato)
- JITX circuit-port forwarding: a circuit port connected to exactly one component port "forwards" to it, so `Constrain(Topology(...))` can be written at the parent level, and reusable sub-circuits don't need routing structures passed in. — [P] [JITX topology](https://docs.jitx.com/en/latest/essentials/SI/topology.html)
- Altium components assigned to a room move with it, and rooms can be generated from component classes. — [P] [Altium Rooms](https://www.altium.com/documentation/altium-designer/pcb/rooms)
- Quilter's detection rules (cap wired to a pin, voltage-named pins, `U`/`L` refdes for converter and inductor) show heuristic template matching from schematic patterns. — [P] [Quilter bypass capacitors](https://docs.quilter.ai/physics-constraints/bypass-capacitors); [P] [switching converters](https://docs.quilter.ai/physics-constraints/switching-converters)
- PCBSchemaGen builds per-IC knowledge graphs from datasheets, for schematics only. — [P] [arXiv 2602.00510](https://arxiv.org/abs/2602.00510)
- kicad-happy's datasheets skill extracts structured JSON (pinouts, characteristics, topology) per MPN. — [P] [kicad-happy](https://github.com/aklofas/kicad-happy)

### Inferences
- A retrieval index over PCBWorld-D3-style corpora, keyed by (IC footprint/MPN, connected passives, pin functions), can supply *relative* poses as seeds. The KiCad design-block format is the natural storage target. Datasheet guidance should be compiled into IR constraints (proximity, loop area, keep-away, same side) rather than copied geometry. Quilter's detection heuristics are a reasonable first-pass "intent extractor" for bypass caps and switchers.

### Gaps
- I found no open dataset of datasheet reference layouts, no layout-retrieval paper for PCBs, and no evaluation of LLM extraction of layout guidelines.

---

## Q6. Implications for an LLM-driven KiCad placer/router: proposed constraint IR sketch, evaluation stack and benchmark plan

### Takeaway
1. **Act through the engine.** PCBWorld shows that engine-interactive LLM agents reach CP 0.65 versus 0.02 when engine-free. OmniRouting adds that feedback quality matters more than iteration count.
2. **Use a typed, strict, specificity-resolved constraint IR** that unifies KiCad selectors, JITX-style topologies and pin models, Allegro-style match groups, ALIGN/FloorSet/tscircuit placement relations and Quilter-style PRCs. It should compile to `.kicad_dru`, tuning profiles, Python checkers and optimizer penalties, and record findings and waivers in an IPC-2581-DFX-like channel.
3. **Evaluate in tiers**, from µs geometry checks up to openEMS and CalculiX sign-off.
4. **Benchmark** on PCBWorld D3 (routing) and the Cypress protocol (placement), plus our own license-tracked corpus with intent annotations. Report the union metric set, including MGS-style human similarity as a diagnostic.

### Cited Findings
(Key supporting facts; see Q1–Q5.)
- Engine-interactive vs plan-and-execute vs engine-free CP is 0.65 / 0.19 / 0.02 for GPT-5.4 on D3-A. — [P] [PCBWorld Table 4](https://arxiv.org/html/2607.05915v2)
- JITX specificity-based selection versus Altium numeric priority versus KiCad last-match ordering. — [P] [JITX](https://docs.jitx.com/en/latest/essentials/physical_design/design-constraints.html); [P] [Altium](https://www.altium.com/documentation/altium-designer/scoping-design-rules-ad); [P] [KiCad](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc)
- IPC-2581C Impedance/Loss/netClass/netPair/Dfx structures. — [P] [IPC-2581C.xsd](https://webstds.ipc.org/2581/IPC-2581C.xsd)
- Quilter PRC definitions with pass criteria. — [P] [Quilter PRCs](https://docs.quilter.ai/physics-rule-checks-prcs/overview)
- The si-wrapper/gerber2ems flow is CI-able and VNA-validated. — [P] [Antmicro 2025](https://antmicro.com/blog/2025/07/recent-improvements-to-antmicros-signal-integrity-simulation-flow)

### Inferences

**A. Constraint IR sketch (YAML/JSON; strict schema; unknown keys rejected)**

```yaml
schema: pcb-intent/0.2
units: mm
resolution: specificity        # specificity | explicit_priority ; compiled to KiCad in general->specific order
tags:                          # JITX-style user tags with inheritance, bound to KiCad selectors
  Power:     {netclass: PWR}
  Power3V3:  {inherits: Power, nets: ["+3V3"]}
  DDR_DQ:    {netclass: DDR_DQ}
selectors:                     # all renderable to KiCad DRC condition strings
  U1_VDD7: {pad: "U1-7"}                       # KiCad fromTo pad syntax RefDes-Pad
  C5_hot:  {pad: "C5-1"}
  C5_gnd:  {pad: "C5-2"}
  BUCK1:   {component_class: "BUCK1"}          # -> ${Class:BUCK1}
topologies:                    # JITX/Allegro: ordered pad paths through series parts
  dqs0_p: {path: ["U1-A3", "R12", "U7-B2"], bridging: {R12: series}, pin_models: {U1-A3: {delay_ps: 15}}}
constraints:
  - id: dec.U1.7
    kind: bypass                # high-level intent (Quilter-like); expands to the primitives below
    cap: C5
    pin: U1_VDD7
    expands_to: [dec.U1.7.prox, dec.U1.7.gndvia, dec.U1.7.loop, dec.U1.7.layersw]
    provenance: {source: datasheet, doc: "U1 DS rev C", page: 23, confidence: 0.8, confirmed_by: null}
  - id: dec.U1.7.prox
    kind: proximity             # Quilter "Pin Distance" PRC / KRT proximity[]
    a: C5_hot
    b: U1_VDD7
    max: 2.0
    basis: pad_edge
    hard: true
    compile:
      checker: geom.pad_distance
      optimizer: {penalty: hinge_sq, weight: 50}
      kicad_dru: '(rule "dec.U1.7.len" (condition "A.fromTo(''U1-7'',''C5-1'')") (constraint length (max 2mm)))'   # post-route proxy
  - id: dec.U1.7.gndvia
    kind: via_to_plane
    pad: C5_gnd
    plane: {net: GND, layer: In1.Cu}
    max_via_distance: 0.5
    min_vias: 1
    hard: true
    compile: {checker: geom.pad_via_to_zone}
  - id: dec.U1.7.layersw
    kind: layer_switch_count    # Quilter PRC
    path: [U1_VDD7, C5_hot]
    max: 0
    hard: false
    weight: 5
  - id: dec.U1.7.loop
    kind: loop_area
    path: [U1_VDD7, C5_hot, C5_gnd, "via", "plane:GND", "U1:GND"]
    max_mm2: 4.0
    hard: false
    weight: 10
    compile: {checker: phys.loop_area_estimate}
  - id: ddr.byte0
    kind: match_group           # Allegro match group / JITX TimingDifference / tscircuit bus maxLengthSkew
    members: {tag: DDR_DQ, plus: [dqs0_p]}
    mode: relative
    target: dqs0_p
    delta_ps: 0
    tol_ps: 5
    compile:
      kicad_tuning_profile: {time_domain: true}
      kicad_dru: '(rule "ddr.byte0" (condition "A.hasNetclass(''DDR_DQ'')") (constraint skew (max 0.8mm)))'  # fallback; ~6.3 ps/mm illustrative
  - id: z.usb
    kind: impedance             # maps to/from IPC-2581 <Impedance><EdgeCoupled .../></Impedance>
    nets: {diff_pair: USB_D}
    value_ohm: 90
    tol_pct: 10
    structure: EDGE_COUPLED
    ref_plane: In1.Cu
  - id: buck.region
    kind: region                # Altium Room / FloorSet grouping / KRT block zone
    members: BUCK1
    rect: [2, 2, 40, 30]
    side: F
    keep: inside
  - id: buck.hotloop
    kind: cluster_tight         # Quilter switching-converter constraint
    anchor: U3
    members: [L1, C10, C11]
    max_span: 6.0
  - id: usb.edge
    kind: edge_placement        # FloorSet boundary / KRT edge_connectors
    ref: J1
    edge: north
    overhang: [0, 1.5]
  - id: sym.diffamp
    kind: symmetry              # ALIGN SymmetricBlocks
    pairs: [[R10, R11], [C20, C21]]
    axis: V
    hard: false
  - id: pwr.overheat
    kind: overheated_length     # Quilter PRC; analytic IPC-2152/2221-style
    tag: Power
    max_rise_c: 20
    max_fraction: 0.10
findings_schema:               # IPC-2581 DFX-like; mirrors KiCad DRC JSON items[uuid,pos]
  fields: [constraint_id, measured, limit, unit, severity, objects, location, response]   # response: open|approved|waived|rejected
```

Design rules for the IR:
- (1) **Hard/soft split** (ALIGN), with a monotone optimizer gate on hard constraints (KRT).
- (2) **High-level intents expand to primitives**: bypass, switcher hot loop, DDR byte lane, USB pair. This is ALIGN's `UserConstraint` idea, and it is what the LLM authors.
- (3) Every primitive has a **checker with explicit pass criteria and units** (Quilter PRCs), and a KiCad compilation wherever one exists.
- (4) **Specificity-based resolution** (JITX), emitted to KiCad general-to-specific so that KiCad's last-match semantics agree.
- (5) **Topologies and match groups** for timing (Allegro, JITX, tscircuit), not net-level length.
- (6) **Provenance and confirmation** for LLM-extracted constraints.
- (7) **IPC-2581 import/export mapping** for impedance and loss specs.
- (8) **Findings/waivers channel** modelled on IPC-2581 DFX and KiCad exclusions.

**B. Evaluation stack**

| Tier | When | Checks | Tools |
|---|---|---|---|
| T0 (µs–ms) | every move | overlap/OoB, intent and PRC geometry (proximity, region, edge, symmetry, layer-switch count once routed), HPWL, net crossings, Transcalc Z0/delay, IPC-2221/2152 widths, overheated-length proxy | in-process geometry; KRT-style intent grader; optionally a trained PDN surrogate |
| T1 (s) | per accepted placement / route batch | `kicad-cli pcb drc --format json --refill-zones --schematic-parity --exit-code-violations`; return-path VOID/SPLIT/VIA; NRR/PRR/PShort; quick reference router (KRT ≈0.65 s, Freerouting ≈7 s per small board) for placement routability | kicad-cli; return_path; KRT/Freerouting |
| T2 (s–min) | checkpoints | DC IR drop and current density; PDN impedance vs target; switcher coupled noise; near-field estimate | padne, KiPI, Ki-PIDA, emcvisual |
| T3 (min–h) | finalists | openEMS S-params/TDR/delay per critical net or pair via si-wrapper slices; FEM thermal | gerber2ems + si-wrapper + scikit-rf; FreeCAD/gmsh/CalculiX (Antmicro scripts) or Salome/Elmer; Palace for C/L extraction |

Calibrate T0/T1 proxies against T3 on reference boards before using them as rewards. Antmicro's VNA-validated slices and emcvisual's 1 dB agreement are the precedents.

**C. Benchmark plan**
1. **Routing leaderboard**: PCBWorld D3-A/B (and later D3-C), using its @5 CP / Pot. / Rout. / DRV / WL / Via / Time / Parse-fail protocol, against the published Freerouting (0.80/0.78) and KRT (0.74/0.20) baselines.
2. **Placement leaderboard**: Cypress small benchmarks under its protocol (Freerouting routability, two layers), plus HPWL, overlap, OoB and crossings. Also PCBWorld D3 boards with placement stripped: keep outline, mechanical parts, connectors and locks; route with a fixed router; compare with the human placement routed by the same router.
3. **Intent track**: a subset of D3 and own boards annotated with IR constraints, human-confirmed. Score intent conformance (PRC pass rate by constraint kind) and hard-violation counts.
4. **Physics track**: decap PRCs, return-path violations, IR-drop margin (padne/KiPI), and for a few high-speed boards si-wrapper/openEMS impedance and delay.
5. **Human-relative diagnostics**: OmniRouting-style MGS, plus WL, via and HPWL ratios to the human board. Report human scores on every metric, since human boards are not 100% clean.
6. **Unit suites**: synthetic generators per IR kind, PCBWorld D1/D2-style; the DPP simulator for the decap sub-problem; FloorSet-style constraint mixes for region, edge, grouping and pre-placed constraints.
7. **Hygiene**: pinned KiCad version, a license manifest per board, a private recent held-out split against pretraining contamination, and methods never scoring themselves (re-open and re-run DRC on saved files).

### Gaps
- The IR is an untested proposal. Its pad-distance, via-to-plane, loop-area and layer-switch checkers need implementation and validation against Quilter-style PRC definitions and openEMS.
- Tier timings for DRC, padne and KiPI on representative boards still need to be measured.
- Licenses on PCBWorld D3, PCBench and the Cypress benchmarks need per-board verification before redistributing derived artifacts.
