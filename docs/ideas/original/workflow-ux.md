# Original ideas: workflow and UX

Scope: U1–U7, turning the catalog's representations into interactions. Part of the [original-ideas catalog](README.md); shorthands as in [intent-and-why](intent-and-why.md). Test status: [research/ideas](../../research/ideas.md#original-ideas-58).
Keys: U1 physics HUD, U2 intent vs geometry locks, U3 expected-loss brief, U4 budget-slider Pareto explorer, U5 semantic ratsnest, U6 sketch-to-intent, U7 intent-level merge

Designers ask for: real-time error detection, auditability, house style, locks, small reversible steps, a tool cheaper than hand layout ([designer-demand](../../topics/ux/designer-demand-and-trust.md), [trust-requirements](../../topics/workflow/trust-requirements.md)).

## U1. Physics HUD — *sharpened*

Idea: a background KiCad plugin showing live budget deltas (loop nH, decap mounting L, skew, return-path breaks, creepage margin) next to the cursor and in a side panel while the human drags parts or routes: real-time error detection with physics, not only DRC.
Mechanism: IPC client polls selection and positions at about 5 Hz; recomputes T0 checks only for affected intents via `impact()` from [I3](intent-and-why.md#i3-mechanism-layer-intent-graph-why-graph--novel-combination); overlay in a separate panel (IPC cannot create persistent markers), click-to-select through IPC; fix-its from the [R6](routing.md#r6-verified-routing-macros-attached-to-recipes--novel-combination) and [S5](system-loop.md#s5-intent-preserving-refactoring-operators--new) operators as one-click proposals applied as one commit.
Evidence [I]: real-time error detection is the most-demanded feature ([designer-demand](../../topics/ux/designer-demand-and-trust.md)); KiCad 10 IPC is read/write CRUD with no marker API, so an overlay is required ([ipc-api](../../topics/kicad/ipc-api-10-vs-11.md), [checkers-si-emi](../../topics/rules/checkers-si-emi.md)); suggestions belong beside the canvas ([explanations](../../topics/ux/explanations-and-alternatives.md)).
Builds on: llm#414, llm#419; hs#143; eco#175 · Test: small user study with seeded problems; time to fix, violations remaining at commit, HUD latency · Effort/risk: M; polling could contend with KiCad's UI thread: throttle.

## U2. Intent locks versus geometry locks — *new*

Idea: two lock kinds: **geometry lock** (do not touch this copper or placement) and **intent lock** (geometry may change, but these relations and budgets must stay satisfied), so engines can re-tighten locked regions during an ECO while guaranteeing intent.
Mechanism: lock records in the IR {scope, kind: geometry or intent, intents[]}; engines treat geometry-locked items as fixed obstacles; intent-locked items stay movable with hard constraints (the listed intents + a budget margin no smaller than the current one); [V1](verification.md#v1-mutation-tested-layout-unit-tests--new) tests enforce both kinds; the UI colours each lock by kind.
Evidence [I]: known-good work must never be touched; designers ask for locks ([trust-requirements](../../topics/workflow/trust-requirements.md)); re-solving relations beats reusing coordinates, 89.5% vs 65.6% ([interfaces](../../topics/llm/interfaces-relations-vs-coordinates.md)).
Builds on: prac#199; llm#6, llm#346, llm#375 · Test: ECO scenarios (board resize, package swap), geometry locks alone vs intent locks; success, intent violations, designer preference · Effort/risk: S; users may confuse the two kinds: the UI must make them obvious.

## U3. Expected-loss-ordered intent brief — *sharpened*

Idea: present comprehension as a one-page brief ordered by expected loss (chance an inference is wrong × its consequence × cost of discovering it late); ask only the top few questions, default the rest with visible labels.
Mechanism: each inferred item has a confidence (from its evidence layers) and a consequence (criticality, [I5](intent-and-why.md#i5-criticality-field-and-criticality-proportional-compute--novel-combination)); expected loss = (1 − confidence) × consequence × rework cost (depends on the stage where the error would surface); ask the top 5–10; show every other item with its default ("assumed: generic low-speed (conf 0.7)"); edits enter the IR with `confirmed_by`.
Evidence [I]: asking only high-impact, low-confidence questions is already the plan ([design-understanding-pipeline](../../topics/llm/design-understanding-pipeline.md)); showing the agent's interpretation cut invalid outputs 4.8% → 0.9% (ProCAD) ([explanations](../../topics/ux/explanations-and-alternatives.md)); Quilter's comprehension step replaces the layout kickoff meeting ([quilter](../../topics/landscape/quilter.md)).
Builds on: llm#194–195, llm#393; eco#164 · Test: vs ordering by confidence alone; errors caught per question asked, time · Effort/risk: S, low risk.

## U4. Budget-slider Pareto explorer — *sharpened*

Idea: 2–4 distinct alternatives with budget-based scorecards; the user drags budget sliders (e.g. trade 0.3 dB of USB loss for 6 mm² less area) and warm-started background re-solves update the alternatives.
Mechanism: QD archive ([S6](system-loop.md#s6-successive-halving-over-the-placement--router-candidate-matrix--sharpened)) indexed by budget spend; a slider move selects the nearest archived alternative instantly, then a warm-started refinement runs in the background; scorecard = budget table + prices ([I4](intent-and-why.md#i4-constraint-price-tags-and-precomputed-foils--new-for-pcb)) + renders.
Evidence [I]: 2–4 alternatives with scorecards are the recommended presentation ([explanations](../../topics/ux/explanations-and-alternatives.md)); engineers think in physical budgets more readily than in abstract weights.
Builds on: llm#396, llm#401; alg#303; [I1](intent-and-why.md#i1-physics-budget-ledger--novel-combination) · Test: user study, sliders vs static alternatives; decision time, satisfaction · Effort/risk: M; archive coverage may be thin in places.

## U5. Semantic ratsnest — *sharpened*

Idea: replace shortest-airwire ratsnest renders with intent-encoding views for humans and the VLM judge: width by current, colour by criticality, arrows for signal flow, dashed return-path ghosts, chain-order markers.
Mechanism: styles generated per net from the IR; bus edges bundled; return ghosts drawn on the reference layer; the same renders feed the U4 scorecards and the [V3](verification.md#v3-judge-licensing-by-seeded-fault-exams--sharpened) judge exams, render style tuned as a hyperparameter against judge accuracy.
Evidence [I]: render style matters for VLM inputs ([scene-layout-transplants](../../topics/placement/scene-layout-transplants.md)); images are a gestalt channel; labelled renders should share ids with the text ([vision-feedback](../../topics/llm/vision-feedback.md)).
Builds on: xd#24; llm#32; alg#274 · Test: VLM judge accuracy on seeded faults, standard vs semantic renders · Effort/risk: S, low risk.

## U6. Sketch-to-intent — *novel combination*

Idea: the designer scribbles on a render (arrow = "route this bus here", circle = "keep these together", line = "split here"); a VLM translates the marks into typed relations for confirmation, never into geometry.
Mechanism: (1) render with id overlays, capture strokes; (2) VLM + stroke classifier propose relations: corridor, group, keepout, order, side; (3) object ids resolved by deterministic hit-testing, not the VLM; (4) user confirms, IR updated.
Evidence [I]: designers ask for sketch routing and visual constraint entry ([trust-requirements](../../topics/workflow/trust-requirements.md)); constraint entry is a dominant time sink ([expert-state-machine](../../topics/workflow/expert-state-machine.md)); LLMs handle semantics well and geometry badly ([spatial-reasoning-limits](../../topics/llm/spatial-reasoning-limits.md)).
Builds on: prac#209, prac#213; llm#32 · Test: time and accuracy for entering 20 constraints vs a form UI and vs chat · Effort/risk: M; VLMs may misread strokes; deterministic hit-testing limits the damage.

## U7. Intent-level merge for concurrent human and agent edits — *new*

Idea: a human and one or more agents edit different regions at once and merge at the intent level; a conflict is a contradictory relation or an overspent shared budget, not an overlapping coordinate.
Mechanism: each editor on its own branch of the [S2](system-loop.md#s2-decision-dag-with-deterministic-replay-and-decision-bisect--new) decision DAG; merge = union of intent graphs + conflict detection (contradictory relations, overspent shared budgets, overlapping reservations); geometry re-legalized at merge time; conflicts presented as [N4](priority-agents-and-negotiation.md#n4-contested-rule-court-with-precedent--novel-combination)-style briefs.
Evidence [I]: parallel authoring helps exploration ([explanations](../../topics/ux/explanations-and-alternatives.md)); work should come in bounded chunks with diffs ([trust-requirements](../../topics/workflow/trust-requirements.md)).
Builds on: llm#423; prac#197; [S2](system-loop.md#s2-decision-dag-with-deterministic-replay-and-decision-bisect--new) · Test: concurrent editing sessions; merge success, conflict-detection precision · Effort/risk: L; KiCad has no live collaborative editing, so this works on file branches.
