# Constraint / intent IR (`pcb-intent/0.2` proposal)

Scope: our proposed geometric/electrical constraint file: schema sketch, design rules, compilation to KiCad 10, LLM extraction. Status: untested proposal [I]. Not here: other tools' constraint models -> [constraint-models-compared](constraint-models-compared.md); operating conditions (currents, bands) -> [intent-interchange](intent-interchange.md); optimizer objective -> [intent-driven-objectives](intent-driven-objectives.md); full KiCad rule reference -> [drc-rule-language-reference](../kicad/drc-rule-language-reference.md).
Keys: pcb-intent, IR, constraint capture, design intent, .kicad_dru compiler, PRC, physics rule check, proximity, via_to_plane, loop_area, layer_switch_count, symmetry, cluster_tight, edge_placement, match group, topology, specificity, last match wins, findings, waivers, IPC-2581 DFX, provenance, intent.yaml, CustomRule protobuf, tuning profile

Tags: [P] primary, [S] secondary, [V] vendor, [I] inference. VK = verification note ([verification_kicad_and_tools.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)).

## Definition

`pcb-intent` = typed, strict (unknown keys rejected, as KRT does), specificity-resolved constraint file; the single source of design intent [I]. Compile targets [I]:
1. strict KiCad `.kicad_dru` emitter + tuning profiles;
2. Python checkers (PRC-style: units, explicit pass criteria), authoritative;
3. optimizer penalties;
4. KiCad 11 `CustomRule` protobuf, when it ships.

Findings and waivers: one channel modelled on IPC-2581 DFX, shared by all critics ([critic-stack](../verification/critic-stack.md)) [I]. LLM role: propose high-level intents (bypass, switcher hot loop, DDR byte lane, USB pair) with detection evidence + provenance; deterministic code expands them to primitives; a human confirms; deterministic PRC-style checkers grade every candidate [I].

## Why an IR (evidence)

- Intent is the gap: "The killer isn't the algorithm — it's **constraint capture**" (KiCadRoutingTools placement doc) [P]. Practitioners' most repeated objection: intent "not captured in any file" ([autorouter-distrust](../workflow/autorouter-distrust.md)).
- No standard carries it: KiCad DRC cannot express pairwise pad distances between footprints, alignment, symmetry or loop area (VK) [P]; IPC-2581C carries impedance/loss specs, net-class categories and diff-pair links but no clearance, length/skew or placement rules, and KiCad's exporter writes no Impedance spec [P] ([IPC-2581C row](constraint-models-compared.md#systems-compared)).
- No precedent: no peer-reviewed formal design-intent language for PCB layout, and no LLM datasheet-to-layout-rule paper, found [S].
- Practical template: Quilter's auto-detection from schematic patterns → user-editable constraint list → named PRCs with units and pass criteria [V].

## IR sketch

Verbatim from the constraints note:

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

Corrections to the sketch:
- `skew` accepts `ps`, so emit the `ddr.byte0` fallback in time units; the "0.8mm … ~6.3 ps/mm illustrative" conversion is unnecessary [P, per VK].
- `ddr.byte0` selects the whole `DDR_DQ` class (every byte lane); its fallback `skew` without `(within_diff_pairs)` constrains skew across all matching nets and drops the `dqs0_p` target ([drc-rule-language-reference](../kicad/drc-rule-language-reference.md)). Scope the tag to one lane (its DQ/DM + its DQS) before compiling [I].
- `dec.U1.7.len` measures routed length on a `fromTo` path, not the pad-edge gap; KiCad creates a `fromTo` path only when uniquely determinable (VK). A decap reaching the pin only through vias + plane gets no path and the rule never fires: treat this compile as advisory; the Python checker is authoritative [P/I].

## Eight design rules

| # | Rule | Borrowed from |
|---|---|---|
| 1 | Hard/soft split; monotone optimizer gate on hard constraints | ALIGN; KRT floorplan intent |
| 2 | High-level intents (what the LLM authors) expand to primitives / solver terms | ALIGN `UserConstraint` |
| 3 | Every primitive has a checker with pass criteria + units, plus a KiCad compilation where one exists | Quilter PRCs |
| 4 | Specificity-based resolution (frees authors from rule order), emitted to KiCad general → specific so KiCad's last-match semantics agree | JITX |
| 5 | Timing on topologies (pin pairs, pad paths through series parts with pin models) and match groups, not net-level length; KiCad `fromTo()` + `length`/`skew` covers part; tscircuit `maxLengthSkew` is a simpler subset | Allegro, JITX, tscircuit |
| 6 | Provenance + confirmation per LLM-extracted constraint: source, document, page, confidence, `confirmed_by` | — |
| 7 | IPC-2581 import/export mapping for impedance and loss specs; import when present (e.g. Altium/Allegro exports); IPC-2581 is not a carrier of placement or routing rules | IPC-2581C |
| 8 | Findings/waivers channel (Criteria / Measurement / Query / Response: APPROVED, WAIVED, REJECTED) mirroring KiCad DRC exclusions | IPC-2581 DFX |

Placement relations also borrow FloorSet boundary, grouping and multi-instantiation [I].

Build first: `proximity`, `via_to_plane`, `loop_area`, `layer_switch_count` checkers; they cover decoupling and hot loops ([hot-loops](../rules/power/hot-loops.md)) [I].

Treat high-speed classes time-domain first: commercial tools leave them open. DeepPCB is "Not for … DDR nets, length matching, advanced impedance control, and RF"; Quilter's timing-sensitive signals are "coming soon" (VK) [I].

## Compiling to KiCad 10

Emitter checklist (verification-note corrections applied; facts [P], canonical in the linked KiCad docs):
1. `(version 1)`; one `condition` per rule (a second one silently overwrites the first), predicates in explicit parentheses: `&&` binds looser than `||`, the reverse of C → [grammar](../kicad/drc-rule-language-reference.md#grammar-and-evaluation).
2. ≤ 1 constraint of each type per rule → [grammar](../kicad/drc-rule-language-reference.md#grammar-and-evaluation).
3. Order rules general → specific: rules are evaluated in reverse, so the last match wins. Pad/footprint clearance overrides beat every custom rule; a net tie forces 0 → [clearance resolution](../kicad/drc-rule-language-reference.md#clearance-resolution).
4. Emit only `mm`, `deg`, `ps` (KiCad also accepts `mil`, `in`, `fs`; `th`, `"`, `rad` are documented but rejected; time units only in `length`/`skew`, forcing time-domain tuning) → [units](../kicad/drc-rule-language-reference.md#units).
5. Rule names `IR:<id>` + sidecar map rule name → IR id; DRC JSON has no rule-name field, so map violations by regex on `description` → [rule-name protocol](../kicad/drc-report-and-repair-loop.md#rule-name-protocol).
6. Use `intersectsArea`/`enclosedByArea`, `intersectsCourtyard*`, `memberOfFootprint` (`insideArea`, `insideCourtyard*`, `memberOf` deprecated); no `microvia_*` on 10.x (master-only; master keyword `hole_aspect_ratio`) → [functions](../kicad/drc-rule-language-reference.md#functions-100).
7. Never steer routing with `ignore` severity (the interactive router does not observe it) → [grammar](../kicad/drc-rule-language-reference.md#grammar-and-evaluation).
8. Fab and safety minimums: write into Board Setup → Constraints (`.kicad_pro`) and clamp every emitted rule, since a matching custom rule bypasses KiCad's board-minimum floor; effective_min = max(resolved_min, fab_min, safety_min), and a [rule pack](../rules/rule-pack-format.md) asking for less raises a conflict ("needs a different fab class") [P/I].
9. Check every emitted file with `kae dru-check`: kicad-cli 10.0.7 drops a bad `.kicad_dru` silently and exits 0, so a DRC run on a scratch copy proves nothing → [kicad-cli](../kicad/kicad-cli.md#pcb-drc-flags-100-docs-byte-identical-on-master) [M].
10. High-speed classes: tuning profile per net class (width, gap, unit delay per layer, via delays; net-class `tuning_profile` via `SetNetClasses` since 10.0.0 over IPC) + `length`/`skew` in `ps`, `(within_diff_pairs)` for intra-pair skew → [tuning profiles](../kicad/drc-rule-language-reference.md#graphical-rule-editor-and-tuning-profiles-100).
11. Component classes (KiCad 9+) carry roles (decap-of, hot-loop, crystal), queried by `hasComponentClass()` → [functions](../kicad/drc-rule-language-reference.md#functions-100).
12. KiCad 11: second emitter for the structured `CustomRule` protobuf; `return_path (layer, net)` (first native reference-plane check; could replace part of our via-to-plane checker), `net_chain_length`, `stub_length` → [master-only constraints](../kicad/drc-rule-language-reference.md#master-only-constraints-kicad-11-development).

| KiCad 10 enforces natively | Needs our checker |
|---|---|
| courtyard spacing; side and orientation (`assertion` on `Layer`/`Orientation`); containment in named rule areas (`intersectsArea`/`enclosedByArea`); edge and keepout distances; length/skew on `fromTo` paths; diff-pair gap and uncoupled length; via count | pad proximity between footprints (KiCad: only the post-route `fromTo` + `length` proxy); via-to-plane; loop area; alignment; symmetry; layer-switch count |

## Practitioner fields and extraction quality

`intent.yaml` fields from the practitioner note [I]: net classes with current and edge rate; SMPS hot-loop member sets; decoupling targets per pin group; terminator ends; star point and order; keep-outs ("no power under IMU"); connector edges and orientation from the enclosure; locked "stake-in-the-ground" regions; reference-layout copies; a per-company style profile. Ask about never-delegate items instead of guessing them ([delegation-and-expert-review](../workflow/delegation-and-expert-review.md)).

| Evidence on extraction quality | Tag |
|---|---|
| CadMust author, self-measured, 161-component board: LLM placement constraints "about 70% quality against a hand-written baseline" from the schematic alone, "roughly 95%" with datasheet extraction for two key ICs ([Reddit](https://www.reddit.com/r/KiCad/comments/1se0r2u/comment/oeo4fy4/)) | [P, anecdote] |
| Critique: "at that point your AI replaced the act of dragging the select box across the components in the sch and clicking 'Add Room'" | [P, community] |
| seveibar (tscircuit): capture requirements as statements ("The USB port must be 2mm from the left edge", "Copy the placement from the datasheet EXACTLY for this subcircuit"); LLM loops can "harden" constraints as flaws appear ([blog](https://blog.autorouting.com/p/sequential-optimal-packing-for-pcb)) | [V] |

Use Quilter's detection rules as the first-pass extractor for bypass caps and switchers: cap wired to a pin; voltage-named pins; refdes `U` converter + `L` inductor with ≥ 2 caps ([Quilter row](constraint-models-compared.md#systems-compared)) [I].

Related academic work:
- graph-attention extraction of analog symmetry constraints ([arXiv 2312.14405](https://arxiv.org/abs/2312.14405)) [P];
- LLANA: LLM few-shot priors for Bayesian optimization of analog layout constraint parameters ([arXiv 2406.05250](https://arxiv.org/abs/2406.05250)) [P];
- PCBSchemaGen: per-IC domain knowledge graph from datasheets + deterministic 5-layer verifier with pin-level error localization; 81.3% pass on PCBBench schematic tasks with Gemma-4-31B ([arXiv 2602.00510](https://arxiv.org/abs/2602.00510)) [P];
- ontology for constraints in custom IC design (Protégé) [S].

## Open questions

- Pad-distance, via-to-plane, loop-area and layer-switch checkers need implementation and validation against Quilter-style PRC definitions and openEMS.
- IPC-2581C `SpecRef` binding on `LogicalNet` vs `Set` is inferred from the XSD; the paid standard text was not read.
- Thresholds (e.g. `max_mm2` for loop area) need datasheet extraction or calibration [I].

## Sources

- [constraints_verification_benchmarks.md § Q1, Q5, Q6A](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md)
- corrections: [verification_kicad_and_tools.md § 2 (DRC language), § 5 (rule-name protocol, time domain)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- [practitioner_discussions.md § Q5 Inferences](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- See also: [layout-reuse](../workflow/layout-reuse.md), [drc-report-and-repair-loop](../kicad/drc-report-and-repair-loop.md)
