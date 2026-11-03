# LLM write interface: relations, not coordinates

Scope: what the LLM is allowed to write (relation bundles with ordinal magnitudes) and the evidence (RAC, scene-layout precedents). Not here: what the LLM reads -> [read-representations](read-representations.md); scene-layout mechanisms in full -> [placement/scene-layout-transplants](../placement/scene-layout-transplants.md); routing evidence -> [routing/llm-routing-evidence](../routing/llm-routing-evidence.md).
Keys: RAC, Relational Agent Contract, relation bundle, ordinal magnitude, tight/close/loose, joint realization, coordinates, clean-pass, re-solve, intent artifact, Holodeck, LayoutVLM, PSDL, self-consistency, SchGen, CCG, PCB-Migrator, NS-Place, admissible relaxation

## Write-interface rule

- The LLM commits **named relations over named objects** with **ordinal magnitudes** (tight/close/loose); it never writes a coordinate or a metric distance. Coordinates may be observable (read state), never writable [I].
- Submit the whole bundle at once for joint realization [P].
- Infeasibility feedback names the conflicting constraints and the admissible relaxations, so the LLM revises commitments, not geometry [I].
- Store the bundle as the intent artifact; it re-solves after board/footprint changes [P].
- Convergence: Holodeck/LayoutVLM/PSDL + RAC + ModuPlace all land on "LLM output is a relation set, never coordinates" [I] (verification note).

## RAC (Relational Agent Contract)

[arXiv 2610.20935](https://arxiv.org/pdf/2610.20935), Univ. of Washington, 14 Oct 2026, preprint [P].

Setup: 98 PCB tasks (42 routing, 31 placement, 17 combined, 8 repair) over decoupling, board-edge association, keepouts, grouping, symmetry, alignment, routing relations; 6 seeds; ≤ 5 model calls; 9 models (incl. Claude Opus 4.8 and 5, GPT-5.6, Gemini 3.8 Flash).

| Interface (harness fixed) | Mean clean-pass |
|---|---|
| Direct coordinates | 23.2% |
| Coordinates + Python sandbox | **21.0%** (code does not rescue coordinates) |
| PCBWorld-style candidate selection | 37.4% |
| Sequential single relations | 62.4% |
| Requirements-only delegation | 74.0% |
| **RAC** (bundled relations) | **90.9%** (77.6–95.9% by model) |

The interface swing exceeds any model difference [P]:
- 8 of 9 models reached 89.8–95.9%; newer was not reliably better (Opus 4.8 > Opus 5; GPT-5.6 Luna > Sol).
- Tokens 22.9–48.5% fewer than candidate selection; lowest latency for 7 of 9 models.
- Harness robustness: native function calling, Codex, Claude Code, OpenCode: coordinates 22.7–32.7%, RAC 91.8–95.9%. Coding-agent harnesses cost **2.2–5.4×** the tokens of native calls: prefer native function calling.
- Geometry change (20% board shrink, 20% expansion, 25% footprint shrink), same relations re-solved: 89.5% (411/459) vs 65.6% for the best coordinate-reuse control (frozen, affine, or fresh solve without relations). Board shrink hardest: 77.1% vs 47.7%.

Contract: agent observes exact authoritative state incl. coordinates; acts only through relations (proximity, alignment, symmetry, edge association, keepouts, matched routing, layer preference, via limits); magnitudes are small ordered classes with metric values fixed solver-side; independent DRC + relation-specific geometric oracles verify. Example actions: `board_edge(J1, left)`, `place_relative(C1, U1.R1, near, tight)`, `route_matched([N2, N3], 5%)` [P].

Caveats (verification note) [P]: tasks appear small and synthetic (≈5–10 parts); backend placer and router not identified; preferences not writable as checkable predicates fall outside the contract.

## Convergent precedents from scene layout

Holodeck (relations + solver MRR 0.706 vs coordinates 0.364), LayoutVLM (self-consistent decoding), Brown PSDL (imperative programs + LLM-free repair) all output relations, never coordinates; mechanisms and numbers -> [placement/scene-layout-transplants](../placement/scene-layout-transplants.md#methods-and-results) [P].

Imperative vs bundled: PSDL's sequential programs beat declarative solvers on scenes; on PCB tasks RAC's sequential relations (62.4%) lost to one jointly realized bundle (90.9%). Coupled PCB constraints appear to need joint realization [I].

## PCB and EDA precedents for relational output

- SchGen: relative-offset, pin-name schematic code 82.0% valid vs 32.5% raw KiCad files, same model -> [read-representations](read-representations.md#schgen-relative-code-vs-raw-kicad) [P].
- ModuPlace CCG: LLM emits a constraint graph with relative offset (x̂, ŷ), rotation θ̂ and weight per edge, consumed by a placer as soft penalties -> [llm-guided-placement-systems](llm-guided-placement-systems.md) [P].
- PCB-Migrator (DATE 2026): offset constraint graph moves expert layouts onto resized or obstructed boards; same use case as RAC re-solve [S].
- NS-Place: MILP legalization with relative-position constraints preserving global structure [P].
- Li et al. DAC 2026: LLM grouping + constraint-graph/MILP legalization beats a commercial placer and Quilter [S, via survey].

## Relation vocabulary

Typed relation bundle = the only LLM write API [I]. Verification note's vocabulary:
- `group`, `region(group, rule_area)`, `side(part, top|bottom)`;
- `near(part, part.pin, tight|close|loose)`, `align(parts, axis)`, `symmetric(a, b, axis)`;
- `board_edge(part, side)`, `orient_toward(part, part.pin)`, `keepout(region, layers)`;
- `route_matched(nets, tol_class)`, `layer_pref(net, layer)`, `via_limit(net, n)`, `net_order(rank)`.

EDA note adds `same_side`, `route_priority`, `min_loop(nets)`, `plane(net, layer, region)`, `kelvin(R_sense)`.

Placement-side additions (RAC/VP synthesis, [placement/llm-guided-placement](../placement/llm-guided-placement.md#use-in-kae)): `ring(ic, refs, priority)`, `order`, `spread(heat)`, `away_from`, `loop_compact(nets)`; hard `fixed`, `on_edge`, `inside`, `clearance`, `rot_allowed`.

## Realization and feedback

1. Magnitude classes resolve to mm solver-side from net class, stackup, datasheet facts and per-class corpus priors (corpus median 0402 decap ≈2.5 mm pad centre to pad centre -> [data/measured-priors](../data/measured-priors.md)); the LLM never chooses mm [I].
2. Joint realization by analytical placer + legalizer + router; verification by independent KiCad DRC + per-relation oracles, never the solver's own satisfaction flag [I].
3. Feedback per relation: realized/violated, margin, conflict sets, admissible relaxations [I].
4. Optional self-consistency filter: drop a relation the LLM's own coarse sketch violates (LayoutVLM: −12.4 points without it) [I].
5. Numeric repair keeps relations: edit constants and orientations only; weight movement by footprint area so connectors and ICs move less than passives (PSDL) [I].
6. Persist the bundle as the design-intent sidecar so ECOs and resizes re-solve without LLM calls -> [ux/design-rationale-and-intent-record](../ux/design-rationale-and-intent-record.md), [architecture/constraint-ir](../architecture/constraint-ir.md) [I].

## Open questions

- Does RAC hold on full real boards at PCBWorld D3 scale (dozens of interacting relations, KiCad backend)?
- Calibration of tight/close/loose per component class is unpublished [I].
- Expressiveness gap: non-checkable preferences (aesthetics, house style) need another channel.
- PSDL imperative-sequential vs RAC bundled: winner depends on constraint coupling.

## Sources
- [verification_papers.md § 2.4 RAC, § 2.10 scene precedents, § 3 implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
- [llm_for_eda.md § 1, § 2, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
- Primary: [RAC 2610.20935](https://arxiv.org/pdf/2610.20935), [Holodeck 2312.09067](https://arxiv.org/abs/2312.09067), [LayoutVLM 2412.02193](https://arxiv.org/abs/2412.02193), [PSDL 2504.05482](https://arxiv.org/abs/2504.05482) / [2510.16147](https://arxiv.org/abs/2510.16147), [SchGen 2605.30345](https://arxiv.org/abs/2605.30345), [PCB-Migrator DOI](https://doi.org/10.23919/DATE69613.2026.11539307)
