# Original ideas: workflow and UX

Part of the [original-ideas catalog](README.md). Shorthands as in [intent-and-why](intent-and-why.md).

What designers ask for: real-time error detection, auditability, house style, locks, small reversible steps, and a tool cheaper than hand layout ([designer-demand](../../topics/ux/designer-demand-and-trust.md), [trust-requirements](../../topics/workflow/trust-requirements.md)). Each idea below turns the representations in this catalog into an interaction.

---

## U1. Physics HUD — *sharpened*

**Pitch.** A background KiCad plugin that shows live budget deltas while the human drags parts or routes. The deltas cover loop nH, decap mounting L, skew, return-path breaks and creepage margin. They appear next to the cursor and in a side panel: real-time error detection with physics, not only DRC.

**Mechanism.**
- An IPC client polls the selection and positions at about 5 Hz.
- It recomputes T0 checks only for the affected intents, using `impact()` from [I3](intent-and-why.md#i3-mechanism-layer-intent-graph-why-graph--novel-combination).
- It draws an overlay in a separate panel, because IPC cannot create persistent markers. Click-to-select works through IPC.
- Fix-its come from the [R6](routing.md#r6-verified-routing-macros-attached-to-recipes--novel-combination) and [S5](system-loop.md#s5-intent-preserving-refactoring-operators--new) operators, offered as one-click proposals that apply as one commit.

**Why it should work.**
- Real-time error detection is the most-demanded feature ([designer-demand](../../topics/ux/designer-demand-and-trust.md)).
- KiCad 10 IPC is read/write CRUD with no marker API, so an overlay is required ([ipc-api](../../topics/kicad/ipc-api-10-vs-11.md), [checkers-si-emi](../../topics/rules/checkers-si-emi.md)).
- Suggestions belong beside the canvas ([explanations](../../topics/ux/explanations-and-alternatives.md)).

**Builds on.** llm#414, llm#419; hs#143; eco#175.

**How to test.** A small user study with seeded problems. Measure time to fix, violations remaining at commit, and HUD latency.

**Effort/risk.** M. Polling could contend with KiCad's UI thread, so throttle it.

---

## U2. Intent locks versus geometry locks — *new*

**Pitch.** Offer two kinds of lock:
- a **geometry lock**: do not touch this copper or placement;
- an **intent lock**: geometry may change, but these relations and budgets must stay satisfied.

With intent locks, engines can re-tighten locked regions during an ECO while still guaranteeing the intent.

**Mechanism.**
- Lock records live in the IR: {scope, kind: geometry or intent, intents[]}.
- Engines treat geometry-locked items as fixed obstacles.
- Intent-locked items stay movable, with hard constraints: the listed intents, plus a budget margin no smaller than the current one.
- The [V1](verification.md#v1-mutation-tested-layout-unit-tests--new) tests enforce both kinds.
- The UI colours each lock by kind.

**Why it should work.**
- Known-good work must never be touched, and designers ask for locks ([trust-requirements](../../topics/workflow/trust-requirements.md)).
- Re-solving relations beats reusing coordinates, 89.5% vs 65.6% ([interfaces](../../topics/llm/interfaces-relations-vs-coordinates.md)).

**Builds on.** prac#199; llm#6, llm#346, llm#375.

**How to test.** ECO scenarios such as a board resize or a package swap. Compare geometry locks alone with intent locks. Measure success, intent violations and designer preference.

**Effort/risk.** S. Users may confuse the two kinds; the UI must make them obvious.

---

## U3. Expected-loss-ordered intent brief — *sharpened*

**Pitch.** Present comprehension as a one-page brief ordered by expected loss: the chance an inference is wrong × its consequence × the cost of discovering it late. Ask only the top few questions, and default the rest with visible labels.

**Mechanism.**
- Each inferred item has a confidence, from its evidence layers, and a consequence, from criticality ([I5](intent-and-why.md#i5-criticality-field-and-criticality-proportional-compute--novel-combination)).
- Expected loss = (1 − confidence) × consequence × rework cost, where rework cost depends on the stage at which the error would surface.
- Ask the top 5–10 items.
- Show every other item with its default, e.g. "assumed: generic low-speed (conf 0.7)".
- Edits enter the IR with `confirmed_by`.

**Why it should work.**
- Asking only high-impact, low-confidence questions is already the plan ([design-understanding-pipeline](../../topics/llm/design-understanding-pipeline.md)).
- Showing the agent's interpretation cut invalid outputs from 4.8% to 0.9% (ProCAD) ([explanations](../../topics/ux/explanations-and-alternatives.md)).
- Quilter's comprehension step replaces the layout kickoff meeting ([quilter](../../topics/landscape/quilter.md)).

**Builds on.** llm#194–195, llm#393; eco#164.

**How to test.** Compare with ordering by confidence alone. Metrics: errors caught per question asked, and time.

**Effort/risk.** S, low risk.

---

## U4. Budget-slider Pareto explorer — *sharpened*

**Pitch.** Show 2–4 distinct alternatives with budget-based scorecards. The user drags budget sliders, for example to trade 0.3 dB of USB loss for 6 mm² less area, and warm-started background re-solves update the alternatives.

**Mechanism.**
- A QD archive ([S6](system-loop.md#s6-successive-halving-over-the-placement--router-candidate-matrix--sharpened)) is indexed by budget spend.
- A slider move selects the nearest archived alternative instantly, then a warm-started refinement runs in the background.
- Each scorecard shows the budget table, prices ([I4](intent-and-why.md#i4-constraint-price-tags-and-precomputed-foils--new-for-pcb)) and renders.

**Why it should work.**
- 2–4 alternatives with scorecards are the recommended presentation ([explanations](../../topics/ux/explanations-and-alternatives.md)).
- Engineers think in physical budgets more readily than in abstract weights.

**Builds on.** llm#396, llm#401; alg#303; [I1](intent-and-why.md#i1-physics-budget-ledger--novel-combination).

**How to test.** A user study comparing sliders with static alternatives. Metrics: decision time and satisfaction.

**Effort/risk.** M. Archive coverage may be thin in places.

---

## U5. Semantic ratsnest — *sharpened*

**Pitch.** Replace shortest-airwire ratsnest renders with views that encode intent, for both humans and the VLM judge:
- width by current;
- colour by criticality;
- arrows for signal flow;
- dashed return-path ghosts;
- chain-order markers.

**Mechanism.**
- Styles are generated from the IR, per net.
- Bus edges are bundled.
- Return ghosts are drawn on the reference layer.
- The same renders feed the U4 scorecards and the [V3](verification.md#v3-judge-licensing-by-seeded-fault-exams--sharpened) judge exams, with render style tuned as a hyperparameter against judge accuracy.

**Why it should work.**
- Render style matters for VLM inputs ([scene-layout-transplants](../../topics/placement/scene-layout-transplants.md)).
- Images are a gestalt channel, and labelled renders should share ids with the text ([vision-feedback](../../topics/llm/vision-feedback.md)).

**Builds on.** xd#24; llm#32; alg#274.

**How to test.** Measure VLM judge accuracy on seeded faults with standard renders and with semantic renders.

**Effort/risk.** S, low risk.

---

## U6. Sketch-to-intent — *novel combination*

**Pitch.** The designer scribbles on a render: an arrow for "route this bus here", a circle for "keep these together", a line for "split here". A VLM translates the marks into typed relations for confirmation, never into geometry.

**Mechanism.**
1. Render the board with id overlays and capture the user's strokes.
2. A VLM plus a stroke classifier proposes relations: corridor, group, keepout, order, side.
3. Object ids are resolved by deterministic hit-testing, not by the VLM.
4. The user confirms, and the IR is updated.

**Why it should work.**
- Designers ask for sketch routing and visual constraint entry ([trust-requirements](../../topics/workflow/trust-requirements.md)).
- Constraint entry is a dominant time sink ([expert-state-machine](../../topics/workflow/expert-state-machine.md)).
- LLMs handle semantics well and geometry badly ([spatial-reasoning-limits](../../topics/llm/spatial-reasoning-limits.md)).

**Builds on.** prac#209, prac#213; llm#32.

**How to test.** Time and accuracy for entering 20 constraints, compared with a form UI and with chat.

**Effort/risk.** M. VLMs may misread strokes; deterministic hit-testing limits the damage.

---

## U7. Intent-level merge for concurrent human and agent edits — *new*

**Pitch.** A human and one or more agents edit different regions at once and merge at the intent level. A conflict is a contradictory relation or an overspent shared budget, not an overlapping coordinate.

**Mechanism.**
- Each editor works on its own branch of the [S2](system-loop.md#s2-decision-dag-with-deterministic-replay-and-decision-bisect--new) decision DAG.
- A merge takes the union of the intent graphs and detects conflicts: contradictory relations, overspent shared budgets, overlapping reservations.
- Geometry is re-legalized at merge time.
- Conflicts are presented as [N4](priority-agents-and-negotiation.md#n4-contested-rule-court-with-precedent--novel-combination)-style briefs.

**Why it should work.**
- Parallel authoring helps exploration ([explanations](../../topics/ux/explanations-and-alternatives.md)).
- Work should come in bounded chunks with diffs ([trust-requirements](../../topics/workflow/trust-requirements.md)).

**Builds on.** llm#423; prac#197; [S2](system-loop.md#s2-decision-dag-with-deterministic-replay-and-decision-bisect--new).

**How to test.** Concurrent editing sessions. Metrics: merge success, conflict-detection precision.

**Effort/risk.** L. KiCad has no live collaborative editing, so this works on file branches.
