# Original ideas: learning, self-improvement and data

Part of the [original-ideas catalog](README.md). Shorthands as in [intent-and-why](intent-and-why.md). Constraints that apply throughout:
- Usable real data is in the low thousands of boards ([corpora-and-yield](../../topics/data/corpora-and-yield.md)).
- Learned routability predictors and RL placement policies carry patent risk ([patents](../../topics/landscape/patents-watchlist.md)).
- Learning should therefore target configuration, orchestration and checks, with solver- or DRC-generated supervision.

---

## L1. Planted-solution synthetic boards — *new*

**Pitch.** Generate training and benchmark boards whose known-good layout is planted by construction. That gives a gap to a planted reference (a known feasible layout, not a proven optimum) for rewards, curricula and regression tests.

**Mechanism.**
1. Compose boards from recipe blocks with verified sub-layouts (outputs of N7, N9 and R6) in a floorplan.
2. Route them fully with our engines and verify them with every critic. The result is the planted solution.
3. Strip the copper and/or the placement, then perturb.
4. Difficulty knobs: density, layer count, number of competing domains, contested-rule selectors, budget tightness.
5. Reward = gap to the planted solution on lexicographic metrics.

The planted solution bounds the achievable score but is not claimed unique. When a better solution is found, it replaces the planted one.

**Why it should work.**
- Quilter trains only on synthetic, physics-scored problems ([quilter](../../topics/landscape/quilter.md)).
- Procedural boards are already recommended for reward unit tests, with jitter calibrated to a 20–60% pass rate ([training-recipes](../../topics/data/training-recipes.md)).
- Real data is scarce ([corpora-and-yield](../../topics/data/corpora-and-yield.md)).

**Builds on.** llm#292, llm#297; eco#232; prac#336; xd#10.

**How to test.** Evaluate on D3 with a time split. Compare planners or heuristics trained/evolved on planted boards with ones trained on D3 alone. Never train on PCBWorld's 99 D3-A + 10 D3-B evaluation boards.

**Effort/risk.** M. There is a synthetic-to-real gap; mix in real boards.

---

## L2. Evolve the conductor — *novel combination*

**Pitch.** Apply AlphaEvolve-style evolution to the orchestration policy rather than to low-level heuristics. The policy covers stage order, per-stage compute budgets, escalation thresholds, engine dispatch and when to call the LLM, and it is written in a small DSL.

**Mechanism.**
- **DSL:** stages with guards and budgets (`if cut_overflow > 0: P2.rebalance(budget=30s)`), engine choices, and LLM call points.
- **Mutation:** an LLM proposes changes within a restricted grammar, checked at the AST level.
- **Evaluation cascade:** synthetic L1 boards → D3 boards of increasing size, with a time split, excluding PCBWorld's 99 + 10 evaluation boards.
- **Search bookkeeping:** negative memory of failed variants, MAP-Elites over (speed, quality), and generalization tests from the first run.

**Why it should work.**
- Restricted interfaces beat free-form ones, and evolving low-level heuristics generalizes only 0.5–2.9% ([llm-evolved-heuristics](../../topics/solvers/llm-evolved-heuristics.md)).
- Execution infrastructure decides long-horizon reliability, with up to 141× differences in token ROI ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md)). The orchestration layer is where large wins remain.

**Builds on.** xd#8; alg#318–322; llm#95–107.

**How to test.** Compare the evolved policy with the hand-written pipeline on held-out boards. Metrics: quality per CPU-hour, generalization gap.

**Effort/risk.** M, mostly compute. The policy can overfit the benchmark; use time and cluster splits.

---

## L3. Inverse optimization from expert edits — *sharpened*

**Pitch.** When a designer edits an AI result, infer the smallest change to objective weights or constraints that makes the human version optimal. Apply it to the project's house profile, and tell the designer.

**Mechanism.**
1. Classify the edit: move, rotate, swap, reroute or width change.
2. Solve the inverse problem in a local window re-solve: find the smallest Δw such that the human result scores better than the AI result by a margin. Alternatively, detect an implied missing constraint, e.g. consistent alignment implies an `align` relation.
3. Present the inference: "You moved C3 0.8 mm closer; I now weight decap distance 1.6× in this project. Keep?"
4. Store (before, after) as a DPO pair.

**Why it should work.**
- Learning house style from cleanup edits is recommended, and low-variance figure-of-merit terms transfer ([imitation](../../topics/data/imitation-and-learned-scores.md), [explanations](../../topics/ux/explanations-and-alternatives.md)).
- Designers ask for house style ([designer-demand](../../topics/ux/designer-demand-and-trust.md)).

**Builds on.** llm#282, llm#299, llm#409; prac#184. **FTO:** close to Cadence '060 and Zuken's learned "brain". Keep it per-project, visible and opt-in ([patents](../../topics/landscape/patents-watchlist.md)).

**How to test.**
1. With simulated designers holding hidden weights, measure weight-recovery error after k edits.
2. With real users, measure how often they accept the inferred updates.

**Effort/risk.** M. Single edits are noisy, so require confirmation before applying.

---

## L4. EVM layouts as oracles for datasheet extraction — *novel combination*

**Pitch.** Check every extracted layout-card rule against the vendor's own evaluation-board layout. A rule the EVM violates is either an extraction error or a vendor inconsistency, and both must be surfaced.

**Mechanism.**
1. Import the EVM layout into KiCad (Gerber, KiCad or Altium export).
2. Run the extracted predicates on it: proximity, order, via-free hot loop, Kelvin.
3. On disagreement, re-extract with the page evidence.
4. If the disagreement persists, flag the rule "vendor inconsistent" and show both citations. Agreement raises the rule's confidence.

**Why it should work.**
- No system extracts layout guidelines ([datasheet-extraction](../../topics/llm/datasheet-extraction.md)).
- Heuristics should be calibrated on vendor EVMs ([rule-pack-format](../../topics/rules/rule-pack-format.md)).
- Vendor documents contain errors ([power digest](../../digests/rules-power-rf-analog-dfm.md)).
- App notes are "wrong until proven right" ([layout-reuse](../../topics/workflow/layout-reuse.md)).

**Builds on.** llm#228, llm#238; hs#156; pwr: calibration on vendor eval layouts; prac#106.

**How to test.** For 50 parts with EVMs, measure extraction precision against an expert key, before and after the EVM check.

**Effort/risk.** S–M. EVM import can be awkward, and licences permit checking but not copying.

---

## L5. Git-history repair pairs from open hardware repos — *new*

**Pitch.** Mine the commit histories of licence-clean KiCad repos for layout revisions that fixed problems ("rev B: fix USB routing", "move decaps"). The result is (before, after, message) repair pairs with a natural-language rationale.

**Mechanism.**
1. Semantically diff consecutive `.kicad_pcb` versions with our parser.
2. Classify the changes: placement moves, reroutes, rule changes.
3. Keep commits with fix-like messages or post-revision tags.
4. Run our critics on before and after to label which checks changed.
5. Store each pair with its commit message.

Uses:
- DPO pairs;
- critic validation (did our checks flag the before-state?);
- [V5](verification.md#v5-counterexample-guided-rule-refinement--new) seeds;
- statistics on what humans actually fix.

**Why it should work.**
- Practitioners want bad examples collected together with their fixes ([llm-field-reports](../../topics/workflow/llm-field-reports.md)).
- Respins are routine, so fix commits exist ([respin](../../topics/verification/respin-and-fab-hold-data.md)).

**Builds on.** llm#239–246, llm#290, llm#308; prac#253.

**How to test.** Measure:
- yield in pairs per 1,000 repos;
- the fraction of pairs whose before-state our critics flag;
- DPO value of the pairs compared with synthetic negatives.

**Effort/risk.** M. Many commits are noisy, and licence tiers apply.

---

## L6. Fab-query memory — *new*

**Pitch.** Parse fab engineering queries (EQs/TQs) and DFM reports into structured findings that update fab profiles, house rules and the documentation checklist. The same hold should never happen twice.

**Mechanism.**
- The LLM extracts {issue type, objects, fab, resolution} with provenance. Issue types include stackup ambiguity, undefined impedance, drill-to-copper, fab notes and BGA ring.
- Each finding maps to an IR or fab-profile update, e.g. add the impedance spec to the fab notes, or raise drill-to-copper min.
- A matching check is added to the documentation critic.
- Resolutions go into a precedent store, as in [N4](priority-agents-and-negotiation.md#n4-contested-rule-court-with-precedent--novel-combination).
- Everything stays local.

**Why it should work.**
- At one fab (AtlasPCB, vendor-reported), holds are dominated by stackup (28%), impedance (22%), drill-to-copper (18%) and notes (15%).
- Only 2–20% of designs pass with no technical queries ([respin-and-fab-hold-data](../../topics/verification/respin-and-fab-hold-data.md)).
- Documentation should be checked first ([critic-stack](../../topics/verification/critic-stack.md)).

**Builds on.** prac#18, prac#92, prac#161; eco#238.

**How to test.** Replay a user's past EQ history and measure the fraction the updated checks would have prevented. On new orders, track the EQ rate.

**Effort/risk.** S. It needs the user's EQ data, which raises privacy concerns, so it runs locally only.
