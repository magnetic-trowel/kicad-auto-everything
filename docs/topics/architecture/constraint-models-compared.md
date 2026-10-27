# Constraint models compared: KiCad, Altium, Allegro, JITX, tscircuit, atopile, Quilter, ALIGN, FloorSet, KRT, IPC-2581

**TL;DR**
- There are three families of constraint model:
  - **Rule-scoping languages**: KiCad `.kicad_dru` (last match wins), Altium query rules (explicit numeric priority), JITX tag/condition/effect (logical specificity).
  - **Object-centric constraint managers**: Allegro CSets, match groups, topology schedules.
  - **Placement-relation languages**: ALIGN typed JSON, tscircuit `calc()` and anchors, FloorSet hard constraints, KRT floorplan intent, Quilter physics constraints with PRCs.
- The tools resolve conflicting rules differently: KiCad by file order, Altium by priority (but all Matched Lengths rules apply), JITX by specificity, Allegro by CSet assignment. Our IR must define its own semantics.
- Timing belongs to pad-to-pad paths through series parts (Allegro pin pairs and Xnets, JITX topologies with pin models), not to nets.
- Exchange formats carry little intent. IPC-2581C carries impedance/loss specs, net-class category and diff-pair links, but no clearance, length or placement rules.
- A simple intent, "keep C5 within 2 mm of U1 pin 7 with a via to GND", is native in tscircuit, Quilter and KRT, only a post-route proxy in KiCad, and inexpressible in IPC-2581.

## Key facts

Tags: [P] primary; [S] snippet/secondary (Allegro facts come from a channel-partner note and a search summary of a login-gated guide); [V] vendor; [I] inference.

| System | Model | Key mechanics | Tag |
|---|---|---|---|
| **KiCad 10** `.kicad_dru` | Rule scoping | `(version 1)`; `(rule name [(severity)] [(layer)] [(condition "expr")] (constraint …))`; last match wins. For clearance, a net tie forces 0, pad/footprint clearance overrides beat every custom rule, and the result is floored at the Board Setup minimum ([drc_engine.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp)). 35 constraint keywords (VK); selectors `fromTo('U1-7','C5-1')`, `intersectsArea`, `enclosedByArea`, `intersectsCourtyard('${Class:X}')`, `hasNetclass`, `hasComponentClass`, `memberOfSheet`, `memberOfGroup`, `inDiffPair`. Component classes; tuning profiles (per-layer width/gap/unit delay, via delays); rule areas; Repeat Layout. Details: [../kicad/drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md) | [P] |
| **Altium** | Rule scoping | Query-scoped unary/binary rules, e.g. `InNet('VBAT') And OnLayer('Bottom Layer')`. Every rule has a priority (lower number = higher priority; new rules get 1), within a rule type. **Exception: multiple Matched Lengths rules all apply**. Keywords include `InNetClass`, `InComponentClass`, `InDifferentialPair`, `InFromTo('NET (C13-2 : U1-8)')`, `InxSignal` (paths through series parts), `InPadClass`, `InRegion`, `WithinRoom` (fully inside; pads/vias by centre) and `TouchesRoom`. **Rooms** are Room Definition constraints (kept inside or outside), a "confinement" constraint in the Placement category; components move with their room; rooms can scope other rules ([scoping](https://www.altium.com/documentation/altium-designer/scoping-design-rules-ad), [rooms](https://www.altium.com/documentation/altium-designer/pcb/rooms)) | [P] |
| **Allegro/OrCAD CM** | Object-centric | Electrical, Physical, Spacing and Same Net Spacing domains. Physical/Spacing CSets hold per-layer values and are assigned to Net, Class and Region objects, each domain with an undeletable DEFAULT. Electrical CSets come from SigXplorer topology templates. Modes: stub length/net schedule; max via count and match via count; max exposed length; propagation delay per pin pair (delay, length or %); relative propagation delay (match groups); max parallel (up to 4 length:gap entries); impedance (abs or %); total etch; layer sets; max xtalk / max peak xtalk; Return Path DRC. Placement: package-to-package overlap, keepin/keepout, package-to-room. **Match groups** are nets/Xnets/pin pairs resolved to pin pairs (All Drivers/All Receivers, Longest Driver/Receiver, Longest Pin Pair), with Scope, Delta, Tolerance and Target; "Match" = tolerance only, "Relative" = delta + tolerance against a target ([Parallel Systems notes](https://www.parallel-systems.co.uk/wp-content/uploads/2020/02/Constraint_modes.pdf)) | [S] |
| **JITX** | Rule scoping by specificity + SI topologies | **Tags**: Python classes with inheritance; implicit `IsCopper` ⊃ `IsTrace`/`IsPour`/`IsVia`/`IsPad`, plus `IsBoardEdge`, `IsHole`, `OnLayer(i)`. Tags are currently assignable only to nets, only in code. **Conditions**: `& \| ~`. **Effects**: `trace_width`, `clearance` (auto-symmetrized), `thermal_relief`, `stitch_via`, `fence_via`. **Selection**: effect type → condition satisfied (else default) → highest explicit `priority` → **global logical specificity** → local specificity (object types, then user tags, then layers) → tie-break. The docs recommend specificity over priority. **SI**: ordered acyclic `>>` pad trees; `BridgingPinModel` for pass-through parts and `TerminatingPinModel(delay, loss)`; `RoutingStructure`/`DifferentialRoutingStructure` (impedance, per-layer width, spacing, velocity, insertion loss, NeckDown, uncoupled region); `TimingConstraint` (e.g. 1.0 ns ±10 ps), `TimingDifferenceConstraint`, `InsertionLossConstraint`; Signal Tuning regions; reports "Unsatisfied Signal Constraints". Placement is a kinematic tree of relative transforms, not constraints. Circuit-port forwarding lets reusable sub-circuits carry constraints ([constraints](https://docs.jitx.com/en/latest/essentials/physical_design/design-constraints.html), [SI](https://docs.jitx.com/en/latest/essentials/SI/constraints.html)) | [P] |
| **tscircuit** | Constructive placement + routing props | `pcbX/pcbY/pcbRotation`; edge anchors (`pcbLeftEdgeX`…); `pcbPositionMode` (relative to group/board/component anchor, or auto); `shouldBeOnEdgeOfBoard`; `pcbMargin*`; group layouts `pcbGrid*`/`pcbFlex*`/`pcbPack` (beta). `calc()` references pad bounds: `pcbX="calc(R1.pin1.minX - 2mm)"`. `<constraint xDist="6.35mm" centerToCenter …/>`. `<bus … maxLengthSkew="0.5mm">` (no electrical connection); `<differentialpair … maxLengthSkew>`; `<breakout>` regions own fanout (DDR: controller fanout / global channel / memory fanout). `<drccheck checkFn>` adds design-local DRC functions ([props](https://github.com/tscircuit/props), [DDR guide](https://docs.tscircuit.com/guides/routing-ddr)) | [P] |
| **atopile** | Parametric electrical assertions | `assert v_out is v_in * ratio`; `assert … within 3.3V +/- 10%`; `assert max_current within 10uA to 100uA`; `r.resistance = 1kohm +/- 20%`; `~>` bridge-connect (experimental). Layout reuse: sub-module build target plus KiCad "pull group". No geometric/placement vocabulary; newer pre-release syntax shows the language is in flux ([examples](https://github.com/atopile/atopile/blob/main/examples/equations/equations.ato)) | [P] |
| **Quilter** | Physics constraints graded by PRCs | **7 constraint types**: Bypass Capacitors (parent pins assigned by explicit wire, then voltage-named pins; a cap on several same-name pins is split equally), Switching Converters (refdes `U`, output inductor `L`, ≥2 external caps placed "as closely as possible"), Crystal Oscillators, Power Nets, Timing-sensitive Signals ("coming soon"), Differential Pairs, Single-ended Impedance. Unconstrained nets are generic low-speed. **8 PRCs**: Pin Distance (closest pin edges in cm, e.g. 0–1 cm), Layer Switch Count, Ground Plane Overlap (under both traces at all points except the last 2×clearance), Trace Path Length, Length Mismatch, Uncoupled Spacing, Invalid Width Span, Overheated Length (% of a high-current net with analytic rise >20 °C, e.g. 0–10%). 2026: reads net-class/layer/pair clearances from inputs; adds a "restricted component … parent component … target pin … maximum allowed distance" placement constraint (May) and a Floorplan page (Jun) ([PRCs](https://docs.quilter.ai/physics-rule-checks-prcs/overview)) | [V, per VK] |
| **ALIGN** (analog VLSI) | Typed placement relations | Pydantic constraints in `<hier>.const.json`. A `HardConstraint` must implement `translate(solver)`; a `UserConstraint` expands into low-level ones. Types: Order, Align, Spread, AspectRatio, Boundary, Floorplan, SymmetricBlocks, BlockDistance, Horizontal/VerticalDistance, GuardRing, GroupCaps, NetPriority, NetConst (shield, criticality), SymmetricNets, PortLocation, MultiConnection, Route, GroupBlocks ([constraint.py](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/master/align/schema/constraint.py)) | [P] |
| **FloorSet** (Intel; ICCAD 2026 C) | Hard floorplan constraints | Fixed outline, shape (aspect-ratio range), boundary (edge or corner), grouping, multi-instantiation (partitions sharing one shape), pre-placement; Bookshelf `.blocks` extension plus net weights; 1M training + 100 test per variant ([arXiv 2405.05480](https://arxiv.org/abs/2405.05480)) | [P] |
| **KRT `floorplan-intent.json`** | Strict placement intent | Keys: blocks/zones, keepouts, edge_connectors, decaps, `proximity[]` (ref, near, max_mm, basis), keep_away, replicate, arrays, fixed_poses, must_lock, legality_budget, severity. Unknown keys are refused at load. Intent acts as a monotone per-move gate in the optimizer ([doc](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/floorplan-intent.md)) | [P] |
| **IPC-2581C** (XSD 2020-07-31) | Exchange format | `Spec` with `Impedance` (value, `tolPlus`/`tolMinus`/`tolPercent`; `SingleEnded`/`EdgeCoupled`/`BroadsideCoupled`/`CoplanarWaveguide`, each with LineWidth, Spacing/Pitch, `RefPlane`, structure enums like `STRIPLINE_SYMMETRIC`, `MICROSTRIP_MASK_COVERED`), `Loss`, `Backdrill`, `SurfaceFinish`, etc. `LogicalNet` has `netClass` (CLK, FIXED, GROUND, SIGNAL, POWER, UNUSED), `netPair`, `SpecRef`. `Dfx` (COMPONENT/BOARDFAB/ASSEMBLY/STACKUP/TESTING/DATAQUALITY) has `Criteria` and `DfxQuery` with responses YES/NO/APPROVED/CONDITIONALLY_APPROVED/REJECTED/WAIVED. **No clearance, length/skew or placement rules.** KiCad's exporter writes stackup material specs, Rev-C surface finish, backdrill and `Dfx`, but **no Impedance spec**. The consortium validator checks schema only ([XSD](https://webstds.ipc.org/2581/IPC-2581C.xsd), [KiCad exporter](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/pcb_io/ipc2581/pcb_io_ipc2581.cpp)) | [P] |

### One intent, many systems

How each system expresses "keep C5 within 2 mm of U1 pin 7 with a via to the GND plane":

| System | Expression |
|---|---|
| tscircuit | Constructively, as an equality: `pcbX="calc(U1.pin7.x + …)"` |
| Quilter | A Bypass Capacitor constraint checked by the Pin Distance, Layer Switch Count, Ground Plane Overlap and Trace Path Length PRCs |
| KiCadRoutingTools | `proximity[]` or `decaps.max_pin_distance_mm` |
| KiCad | Only as a post-route `fromTo('U1-7','C5-1')` + `length (max 2mm)` proxy, which needs a uniquely determinable copper path (none exists when the decap reaches the pin only through vias and a plane) |
| IPC-2581 | Not at all |

### Commercial input contract (VK synthesis)

Commercial tools converge on one input contract [P/I]:
- a fixed outline;
- pre-placed connectors;
- locked critical copper;
- net classes and named planes (Quilter detects planes by layer names "ground"/"gnd" and "power"/"pwr");
- auto-detected "physics constraints" that a human confirms.

## Recommendations for our system

- **Resolution**: adopt JITX-style specificity, which frees authors from ordering rules. Compile to KiCad in general → specific order ([constraint-ir.md](constraint-ir.md)) [I].
- **Timing**: model it with Allegro-style pin pairs and match groups and JITX topologies with pin models. KiCad's `fromTo()` + `length`/`skew` covers part of this; tscircuit's `maxLengthSkew` is a simpler subset [I].
- **Placement relations**: borrow from ALIGN (hard vs soft, user constraints expanding into solver terms), FloorSet (boundary, grouping, multi-instantiation) and KRT (strict keys, monotone gate) [I].
- **Physics checks**: copy Quilter's pattern of auto-detection → confirmation → named PRCs with units [I].
- **IPC-2581C**: use it as an *input* for impedance and stackup intent, and as the model for the findings/waivers channel. It is not a carrier of placement or routing rules [I].

## Conflicts and open questions

- Primary Cadence documentation is login-gated; Allegro facts are second-hand [S].
- The IPC-2581C standard text (paid) was not read, only the XSD.
- The atopile language is in flux; any binding to it should wait [I].

## Sources

- research notes: [constraints_verification_benchmarks.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md)
- corrections: [verification_kicad_and_tools.md § 2, § 4 Quilter](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)

See also: [constraint-ir.md](constraint-ir.md), [../workflow/layout-reuse.md](../workflow/layout-reuse.md), [../landscape/quilter.md](../landscape/quilter.md)
