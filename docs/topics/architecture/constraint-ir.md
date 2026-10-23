# Constraint / intent IR (`pcb-intent/0.2` proposal)

**TL;DR**
- The IR is a typed, strict, specificity-resolved constraint file that is the single source of design intent.
  - It compiles down to KiCad `.kicad_dru` rules and tuning profiles, to Python checkers (PRC-style, with units and pass criteria), and to optimizer penalties.
  - It records findings and waivers in a channel modelled on IPC-2581 DFX.
- The LLM authors high-level intents (bypass, switcher hot loop, DDR byte lane, USB pair), with detection evidence and provenance. Deterministic code expands them into primitives, and a human confirms.
- Native primitives are needed for what KiCad DRC cannot express: `proximity(pad, pad, max, basis)`, `via_to_plane`, `loop_area`, `layer_switch_count`, `symmetry`, `cluster_tight`, `edge_placement`.
- Rule resolution must be explicit. Use JITX-style specificity, emitted to KiCad general-to-specific so that KiCad's "last match wins" agrees.
- Timing constraints belong to pad-to-pad topologies and match groups, not to nets. On KiCad 10, emit time-domain `length`/`skew` in `ps` plus tuning profiles.

## Key facts

Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference. The IR itself is an untested proposal [I]. Other systems' constraint models are compared in [constraint-models-compared.md](constraint-models-compared.md).

### Why an IR (evidence)

- **Intent is the gap.** "The killer isn't the algorithm — it's **constraint capture**" (KiCadRoutingTools placement doc) [P]. Practitioners' most repeated objection is that design intent is "not captured in any file" ([../workflow/autorouter-distrust.md](../workflow/autorouter-distrust.md)).
- **No standard carries it.**
  - KiCad DRC cannot express pairwise pad distances between footprints, alignment, symmetry or loop area (VK) [P].
  - IPC-2581C carries impedance and loss specs, net-class categories and diff-pair links, but **no** clearance, length/skew or placement rules. KiCad's IPC-2581 exporter writes **no Impedance spec** [P].
- **No precedent for PCB.** No peer-reviewed formal design-intent language for PCB layout, and no LLM datasheet-to-layout-rule paper, was found [S].
- **Quilter's workflow is a practical template**: automatic detection from schematic patterns → user-editable constraint list → named PRCs with explicit pass criteria and units [V].

### IR sketch (verbatim from the constraints note)

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

### Eight design rules

1. **Hard/soft split** (ALIGN), with a monotone optimizer gate on hard constraints (KRT floorplan intent).
2. **High-level intents expand to primitives** (ALIGN `UserConstraint`). These intents are what the LLM authors.
3. **Every primitive has a checker** with explicit pass criteria and units (Quilter PRCs), plus a KiCad compilation wherever one exists.
4. **Specificity-based resolution** (JITX), emitted to KiCad general-to-specific so that KiCad's last-match semantics agree.
5. **Topologies and match groups** for timing (Allegro, JITX, tscircuit), not net-level length.
6. **Provenance and confirmation** for every LLM-extracted constraint: source, document, page, confidence, `confirmed_by`.
7. **IPC-2581 import/export mapping** for impedance and loss specs. Import them when present, e.g. from Altium/Allegro exports.
8. **A findings/waivers channel** modelled on IPC-2581 DFX (Criteria / Measurement / Query / Response: APPROVED, WAIVED, REJECTED) that mirrors KiCad DRC exclusions.

### Compiling to KiCad 10 (verification-note corrections apply)

| Rule | Reason | Tag |
|---|---|---|
| Emit `(version 1)`; one `condition` per rule, with all predicates combined in explicit parentheses | A second `condition` silently overwrites the first. Operator precedence, lowest to highest: `&&`, `\|\|`, `^`, comparisons (non-associative), `!`, `+ -`, `* /`. So `&&` binds looser than `\|\|`, the reverse of C: always parenthesise ([grammar.lemon @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/libeval_compiler/grammar.lemon)) | [P] |
| At most one constraint of each type per rule | Parser error "Rule already has a '%s' constraint" | [P] |
| Order rules general → specific | Rules are evaluated in reverse, so the last matching rule wins. For clearance, a net tie forces 0, pad/footprint clearance overrides beat every custom rule, and the result is floored at the Board Setup minimum (violation source "board minimum"); diff-pair gap is floored the same way ([drc_engine.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp)) | [P] |
| Units only `mm`, `deg`, `ps` (also accepted: `mil`, `in`, `fs`) | `th`, `"` and `rad` are documented but rejected. Time units are only valid in `length`/`skew`, and they force time-domain tuning | [P] |
| Prefix rule names `IR:<id>`; keep a sidecar map rule name → IR ID; parse JSON `description` (regex `\((rule '|)?([^ ]+)'? .*?; actual .*?\)`) | DRC JSON has no rule-name field; `physical_clearance` violations report as `clearance`/`hole_clearance` | [P] |
| Use `intersectsArea`/`enclosedByArea`, `intersectsCourtyard*`, `memberOfFootprint` | `insideArea`, `insideCourtyard*` and `memberOf` are deprecated | [P] |
| Don't use `microvia_*` on 10.x | Master-only; the master keyword is `hole_aspect_ratio` | [P] |
| Don't rely on `ignore` severity to steer routing | `ignore` rules are evaluated and can override, but the interactive router ignores them | [P] |
| Compile fab and safety minimums into Board Setup → Constraints (`.kicad_pro`), not only into `.kicad_dru` rules. They are floors applied after resolution, effective_min = max(resolved_min, fab_min, safety_min); a [rule pack](../rules/rule-pack-format.md) that asks for less raises a conflict ("needs a different fab class") instead of winning | KiCad clamps every resolved clearance and diff-pair gap to the board minimum ([drc_engine.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp)) | [P/I] |
| Lint by running `kicad-cli pcb drc` on a scratch copy | "Any errors in the custom rules will prevent the design rule checker from running" | [P] |
| High-speed classes: write a tuning profile per net class (width, gap, unit delay per layer, via delays) via `SetNetClasses`; emit `length`/`skew` in `ps`, with `(within_diff_pairs)` for intra-pair skew | `tuning_profile` is available on net classes since 10.0.0 over IPC | [P] |
| Use component classes as role carriers (decap-of, hot-loop, crystal) queried by `hasComponentClass()` | KiCad 9+ | [P] |
| Track KiCad 11: the structured `CustomRule` protobuf (a second compile target); `return_path (layer, net)`, `net_chain_length`, `stub_length` | First native reference-plane check, which could replace part of a custom via-to-plane checker | [P] |

**Corrections to the sketch:**
- Since `skew` accepts `ps`, the `ddr.byte0` fallback can be emitted directly in time units. The "0.8mm … ~6.3 ps/mm illustrative" conversion is unnecessary [P, per VK].
- `ddr.byte0` selects the whole `DDR_DQ` class, i.e. every byte lane, and its fallback `skew` without `(within_diff_pairs)` constrains skew across all matching nets and drops the `dqs0_p` target ([../kicad/drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md)). Scope the tag to one lane (its DQ/DM plus its DQS) before compiling [I].
- The `dec.U1.7.len` proxy measures routed length on a `fromTo` path, not the pad-edge gap, and KiCad creates a `fromTo` path only when it is uniquely determinable (VK). A decap that reaches the pin only through vias and a plane then gets no path and the rule never fires, so treat this compile as advisory; the Python checker is authoritative [P/I].

**What KiCad 10 can and cannot enforce from the IR:**
- **Native**: courtyard spacing; side and orientation (`assertion` on `Layer`/`Orientation`); containment in named rule areas (`intersectsArea`/`enclosedByArea`); edge and keepout distances; length/skew on `fromTo` paths; diff-pair gap and uncoupled length; via count.
- **Custom checkers needed**: proximity between footprints' pads (KiCad has only a post-route `fromTo`+`length` proxy), via-to-plane, loop area, alignment, symmetry, layer-switch count.

The full verified rule reference is in [../kicad/drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md).

### Practitioner version: `intent.yaml` fields

From the practitioner note's recommendations [I]:
- net classes with current and edge rate;
- SMPS hot-loop member sets;
- decoupling targets per pin group;
- terminator ends;
- star point and order;
- keep-outs ("no power under IMU");
- connector edges and orientation from the enclosure;
- locked "stake-in-the-ground" regions;
- reference-layout copies;
- a per-company style profile.

The LLM should ask about never-delegate items rather than guess them ([../workflow/delegation-and-expert-review.md](../workflow/delegation-and-expert-review.md)).

**Evidence on extraction quality.**
- CadMust's author (self-measured, 161-component board): LLM-generated placement constraints scored "about 70% quality against a hand-written baseline" from the schematic alone, and "roughly 95%" after adding datasheet extraction for two key ICs ([Reddit](https://www.reddit.com/r/KiCad/comments/1se0r2u/comment/oeo4fy4/)) [P, anecdote].
- Critique: "at that point your AI replaced the act of dragging the select box across the components in the sch and clicking 'Add Room'" [P, community].
- seveibar (tscircuit) says requirements must be captured as statements like "The USB port must be 2mm from the left edge" or "Copy the placement from the datasheet EXACTLY for this subcircuit". He argues LLM loops can "harden" constraints as flaws appear ([blog](https://blog.autorouting.com/p/sequential-optimal-packing-for-pcb)) [V].
- **Detection heuristics**: Quilter's rules are a reasonable first-pass intent extractor for bypass caps and switchers:
  - a cap wired to a pin;
  - voltage-named pins;
  - refdes `U` for the converter and `L` for its inductor, with ≥2 caps.

### Related academic work

- Graph-attention extraction of analog symmetry constraints ([arXiv 2312.14405](https://arxiv.org/abs/2312.14405)) [P].
- LLANA: LLM few-shot priors for Bayesian optimization of analog layout constraint parameters ([arXiv 2406.05250](https://arxiv.org/abs/2406.05250)) [P].
- PCBSchemaGen: per-IC domain knowledge graph from datasheets plus a deterministic 5-layer verifier with pin-level error localization; 81.3% pass on PCBBench schematic tasks with Gemma-4-31B ([arXiv 2602.00510](https://arxiv.org/abs/2602.00510)) [P].
- An ontology for constraints in custom IC design (Protégé) [S].

## Recommendations for our system

- **Single source of truth.** Make `pcb-intent` the one place intent lives. Reject unknown keys, as KRT does [I].
- **LLM role.** The LLM proposes constraints with detection evidence and provenance; a human confirms; deterministic PRC-style checkers grade every candidate [I].
- **Three compile targets**: a strict `.kicad_dru` emitter, Python checkers, and optimizer penalties. Add KiCad 11's `CustomRule` protobuf as a fourth when it ships [I].
- **Native placement primitives.** Implement `proximity`, `via_to_plane`, `loop_area` and `layer_switch_count` checkers first; they cover decoupling and hot loops ([../rules/power/hot-loops.md](../rules/power/hot-loops.md)) [I].
- **Shared findings format.** Use the findings schema across critics and waivers ([../verification/critic-stack.md](../verification/critic-stack.md)) [I].
- **Time-domain first for high-speed classes.** This targets the space commercial tools leave open: DeepPCB is "Not for … DDR nets, length matching, advanced impedance control, and RF", and Quilter's timing-sensitive signals are "coming soon" (VK) [I].

## Conflicts and open questions

- The IR is untested. Its pad-distance, via-to-plane, loop-area and layer-switch checkers need implementation and validation against Quilter-style PRC definitions and openEMS.
- How IPC-2581C binds `SpecRef` on `LogicalNet` vs `Set` is inferred from the XSD; the paid standard text was not read.
- Thresholds (e.g. `max_mm2` for loop area) need datasheet extraction or calibration [I].

## Sources

- research notes: [constraints_verification_benchmarks.md § Q1, Q5, Q6A](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md)
- corrections: [verification_kicad_and_tools.md § 2 (DRC language), § 5 (rule-name protocol, time domain)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- research notes: [practitioner_discussions.md § Q5 Inferences](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)

See also: [constraint-models-compared.md](constraint-models-compared.md), [../verification/critic-stack.md](../verification/critic-stack.md), [../workflow/layout-reuse.md](../workflow/layout-reuse.md), [../kicad/drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md), [../kicad/drc-report-and-repair-loop.md](../kicad/drc-report-and-repair-loop.md)
