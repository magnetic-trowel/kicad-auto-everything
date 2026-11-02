# Original ideas: learning, self-improvement and data

Scope: L1–L6. Part of the [original-ideas catalog](README.md); shorthands as in [intent-and-why](intent-and-why.md). Test status: [research/ideas](../../research/ideas.md#original-ideas-58).
Keys: L1 planted-solution boards, L2 evolve the conductor, orchestration DSL, L3 inverse optimization from edits, house style, L4 EVM extraction oracle, L5 git-history repair pairs, L6 fab-query memory, EQ

Constraints throughout: usable real data is in the low thousands of boards ([corpora-and-yield](../../topics/data/corpora-and-yield.md)); learned routability predictors and RL placement policies carry patent risk ([patents](../../topics/landscape/patents-watchlist.md)); so learning targets configuration, orchestration and checks, with solver- or DRC-generated supervision.

## L1. Planted-solution synthetic boards — *new*

Idea: training and benchmark boards whose known-good layout is planted by construction, giving a gap to a planted reference (a known feasible layout, not a proven optimum) for rewards, curricula and regression tests.
Mechanism:
1. Compose boards from recipe blocks with verified sub-layouts (outputs of N7, N9, R6) in a floorplan.
2. Route fully with our engines, verify with every critic: the planted solution.
3. Strip copper and/or placement, then perturb.
4. Difficulty knobs: density, layer count, number of competing domains, contested-rule selectors, budget tightness.
5. Reward = gap to the planted solution on lexicographic metrics. The planted solution bounds the achievable score but is not claimed unique; a better solution found replaces it.
Evidence [I]: Quilter trains only on synthetic, physics-scored problems ([quilter](../../topics/landscape/quilter.md)); procedural boards are already recommended for reward unit tests, jitter calibrated to a 20–60% pass rate ([training-recipes](../../topics/data/training-recipes.md)); real data is scarce ([corpora-and-yield](../../topics/data/corpora-and-yield.md)).
Builds on: llm#292, llm#297; eco#232; prac#336; xd#10 · Test: D3 with a time split; planners or heuristics trained/evolved on planted boards vs on D3 alone; never train on PCBWorld's 99 D3-A + 10 D3-B evaluation boards · Effort/risk: M; synthetic-to-real gap: mix in real boards.

## L2. Evolve the conductor — *novel combination*

Idea: AlphaEvolve-style evolution of the orchestration policy (stage order, per-stage compute budgets, escalation thresholds, engine dispatch, when to call the LLM) written in a small DSL, rather than of low-level heuristics.
Mechanism: DSL of stages with guards and budgets (`if cut_overflow > 0: P2.rebalance(budget=30s)`), engine choices, LLM call points; LLM-proposed mutations within a restricted grammar, checked at the AST level; evaluation cascade synthetic L1 boards → D3 boards of increasing size, time split, excluding PCBWorld's 99 + 10 evaluation boards; negative memory of failed variants, MAP-Elites over (speed, quality), generalization tests from the first run.
Evidence [I]: restricted interfaces beat free-form ones; evolving low-level heuristics generalizes only 0.5–2.9% ([llm-evolved-heuristics](../../topics/solvers/llm-evolved-heuristics.md)); execution infrastructure decides long-horizon reliability, up to 141× differences in token ROI ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md)): the orchestration layer is where large wins remain.
Builds on: xd#8; alg#318–322; llm#95–107 · Test: evolved policy vs hand-written pipeline on held-out boards; metrics quality per CPU-hour, generalization gap · Effort/risk: M, mostly compute; overfitting the benchmark: use time and cluster splits.

## L3. Inverse optimization from expert edits — *sharpened*

Idea: when a designer edits an AI result, infer the smallest change to objective weights or constraints that makes the human version optimal, apply it to the project's house profile, and tell the designer.
Mechanism:
1. Classify the edit: move, rotate, swap, reroute, width change.
2. Inverse problem in a local window re-solve: smallest Δw such that the human result beats the AI result by a margin; or detect an implied missing constraint (consistent alignment → `align` relation).
3. Present: "You moved C3 0.8 mm closer; I now weight decap distance 1.6× in this project. Keep?"
4. Store (before, after) as a DPO pair.
Evidence [I]: learning house style from cleanup edits is recommended; low-variance figure-of-merit terms transfer ([imitation](../../topics/data/imitation-and-learned-scores.md), [explanations](../../topics/ux/explanations-and-alternatives.md)); designers ask for house style ([designer-demand](../../topics/ux/designer-demand-and-trust.md)).
Builds on: llm#282, llm#299, llm#409; prac#184. **FTO:** close to Cadence '060 and Zuken's learned "brain": keep it per-project, visible and opt-in ([patents](../../topics/landscape/patents-watchlist.md)) · Test: (1) simulated designers with hidden weights: weight-recovery error after k edits; (2) real users: acceptance rate of inferred updates · Effort/risk: M; single edits are noisy: require confirmation before applying.

## L4. EVM layouts as oracles for datasheet extraction — *novel combination*

Idea: check every extracted layout-card rule against the vendor's own evaluation-board layout; a rule the EVM violates is an extraction error or a vendor inconsistency, and both must be surfaced.
Mechanism: (1) import the EVM layout into KiCad (Gerber, KiCad or Altium export); (2) run the extracted predicates on it: proximity, order, via-free hot loop, Kelvin; (3) on disagreement, re-extract with the page evidence; (4) persistent disagreement → flag "vendor inconsistent", show both citations; agreement raises the rule's confidence.
Evidence [I]: no system extracts layout guidelines ([datasheet-extraction](../../topics/llm/datasheet-extraction.md)); heuristics should be calibrated on vendor EVMs ([rule-pack-format](../../topics/rules/rule-pack-format.md)); vendor documents contain errors ([power digest](../../digests/rules-power-rf-analog-dfm.md)); app notes are "wrong until proven right" ([layout-reuse](../../topics/workflow/layout-reuse.md)).
Builds on: llm#228, llm#238; hs#156; pwr: calibration on vendor eval layouts; prac#106 · Test: 50 parts with EVMs, extraction precision against an expert key before vs after the EVM check · Effort/risk: S–M; EVM import can be awkward; licences permit checking, not copying.

## L5. Git-history repair pairs from open hardware repos — *new*

Idea: mine commit histories of licence-clean KiCad repos for layout revisions that fixed problems ("rev B: fix USB routing", "move decaps"), giving (before, after, message) repair pairs with a natural-language rationale.
Mechanism: (1) semantic diff of consecutive `.kicad_pcb` versions with our parser; (2) classify changes: placement moves, reroutes, rule changes; (3) keep commits with fix-like messages or post-revision tags; (4) run our critics on before and after to label which checks changed; (5) store each pair with its commit message. Uses: DPO pairs; critic validation (did our checks flag the before-state?); [V5](verification.md#v5-counterexample-guided-rule-refinement--new) seeds; statistics on what humans actually fix.
Evidence [I]: practitioners want bad examples collected with their fixes ([llm-field-reports](../../topics/workflow/llm-field-reports.md)); respins are routine, so fix commits exist ([respin](../../topics/verification/respin-and-fab-hold-data.md)).
Builds on: llm#239–246, llm#290, llm#308; prac#253 · Test: yield in pairs per 1,000 repos; fraction of pairs whose before-state our critics flag; DPO value vs synthetic negatives · Effort/risk: M; many commits are noisy; licence tiers apply.

## L6. Fab-query memory — *new*

Idea: parse fab engineering queries (EQs/TQs) and DFM reports into structured findings that update fab profiles, house rules and the documentation checklist, so the same hold never happens twice.
Mechanism: the LLM extracts {issue type, objects, fab, resolution} with provenance (issue types: stackup ambiguity, undefined impedance, drill-to-copper, fab notes, BGA ring); each finding maps to an IR or fab-profile update (e.g. add the impedance spec to the fab notes, raise drill-to-copper min); a matching check joins the documentation critic; resolutions go into a precedent store as in [N4](priority-agents-and-negotiation.md#n4-contested-rule-court-with-precedent--novel-combination); everything stays local.
Evidence [I]: at one fab (AtlasPCB, vendor-reported) holds are dominated by stackup (28%), impedance (22%), drill-to-copper (18%), notes (15%); only 2–20% of designs pass with no technical queries ([respin-and-fab-hold-data](../../topics/verification/respin-and-fab-hold-data.md)); documentation should be checked first ([critic-stack](../../topics/verification/critic-stack.md)).
Builds on: prac#18, prac#92, prac#161; eco#238 · Test: replay a user's past EQ history, fraction the updated checks would have prevented; EQ rate on new orders · Effort/risk: S; needs the user's EQ data (privacy): runs locally only.
