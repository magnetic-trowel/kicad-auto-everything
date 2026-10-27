# Original ideas: verification, critics and anti-reward-hacking

Part of the [original-ideas catalog](README.md). Shorthands as in [intent-and-why](intent-and-why.md). The baseline is the three-tier critic stack (A: DRC, S: semantic geometry, J: LLM judge) and the T0–T3 evaluation tiers ([critic-stack](../../topics/verification/critic-stack.md), [evaluation-stack](../../topics/verification/evaluation-stack.md)). The ideas below make checks trustworthy before anything optimizes against them.

---

## V1. Mutation-tested layout unit tests — *new*

**Pitch.** Compile every intent into executable tests over the board model. Accept a test, including LLM-written checkers and LLM-written `.kicad_dru` rules, only if it kills a set of generated near-miss mutants and still passes on compliant variants.

**Mechanism.**
- **Test:** a function `(board, ir) → {pass, measured, limit}`.
- **Mutation operators per primitive:**
  - move a part across a proximity threshold by ±ε;
  - flip its side or swap its layer;
  - insert a via before a TVS;
  - delete a stitching via;
  - shift one pair leg to create skew;
  - narrow a power neck.
- **Mutants are generated from the current board,** so each test is validated on the actual design.
- **Acceptance:** mutation score ≥ threshold, and zero false positives on at least 10 compliant perturbations. DRU rules are run through `kicad-cli` DRC on the mutants.
- **When tests run:** in CI (a git hook) and after every agent step.

**Why it should work.**
- LLMs write detector code well, and accepting code only when tests pass works ([block-recognition](../../topics/llm/block-recognition.md)).
- Every primitive needs a checker with pass criteria ([constraint-ir](../../topics/architecture/constraint-ir.md)).
- DRU pitfalls silently disable rules: the last matching rule wins, and a second `condition` overwrites the first ([drc-rule-language-reference](../../topics/kicad/drc-rule-language-reference.md)).
- Muted checks are a top field failure ([field-failure-modes](../../topics/ux/field-failure-modes.md)).

**Builds on.** llm#174–175, llm#217, llm#297; prac#207, prac#235; eco#51.

**How to test.** Seed 100 faults from the 299-item checklist into 10 boards. Measure the escaped-defect rate for three setups: mutation-validated tests, unvalidated LLM tests, and DRC alone.

**Effort/risk.** S–M. Mutation operators must be designed per primitive; start with 8.

---

## V2. Red-team reward hacker as a gate — *new*

**Pitch.** Before any RL, evolution or autonomous loop may optimize a score, an adversarial agent tries to maximize that score while violating intent. Every hack it finds becomes a regression test and a scorer fix.

**Mechanism.**
- The red-team agent runs in a sandbox with the scorer API and the full tool surface.
- It gets a list of forbidden outcomes:
  - shorts through planes;
  - deleted nets;
  - rule edits that relax clearances;
  - `ignore` severities;
  - net-tie abuse;
  - copper outside the board;
  - edits to locked objects;
  - geometry hidden on unused layers.
- **Reward:** score gain × intent violation, as confirmed by an independent auditor.
- **Gate:** optimization may start only once the red team finds no new hack within its budget.

**Why it should work.**
- Scoreboard gaming has been observed, so the harness must be immutable to agents ([trust-requirements](../../topics/workflow/trust-requirements.md)).
- A no-tools baseline passed DRC while routing through the GND plane ([kicad-ai-tools](../../topics/landscape/kicad-ai-tools-and-mcp-servers.md)).
- RL routers find reward loopholes ([imitation](../../topics/data/imitation-and-learned-scores.md)).
- Legality must be part of the acceptance contract ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md)).

**Builds on.** prac#202; llm#64, llm#299; eco#201.

**How to test.** Count the hacks found per scorer version. Compare hack incidence in later GRPO and evolution runs with and without the gate.

**Effort/risk.** S. The red team is limited by its imagination; seed it with the field-failure list.

---

## V3. Judge licensing by seeded-fault exams — *sharpened*

**Pitch.** The LLM/VLM judge may gate only the checklist categories where it has passed a seeded-fault exam with measured precision and recall. In every other category it may annotate but not block or approve.

**Mechanism.**
- **Exam set:** boards with seeded faults per checklist category, plus clean controls, refreshed regularly against contamination. The [V1](#v1-mutation-tested-layout-unit-tests--new) mutants can supply the faults.
- **Scoring:** the judge is scored per category for a given model and prompt.
- **Licence:** granted when recall ≥ R and precision ≥ P.
- **Re-exam:** required on any model change.
- **Disclosure:** reports state where the judge is unlicensed, e.g. "judge unlicensed for EMC stitching".

**Why it should work.**
- Uncertain judge findings already go to a human ([critic-stack](../../topics/verification/critic-stack.md)).
- A seeded checklist track is already planned ([benchmark-plan](../../topics/verification/benchmark-plan.md)).
- Explanations can raise overreliance ([explanations](../../topics/ux/explanations-and-alternatives.md)).
- A VLM pros/cons judge agreed with humans about 77% of the time, but not uniformly across cases ([scene-layout-transplants](../../topics/placement/scene-layout-transplants.md)).

**Builds on.** prac#123, prac#346; llm#68; xd#4.

**How to test.** Measure exam test–retest reliability, and escaped defects in licensed categories.

**Effort/risk.** S. Building seeded sets takes work; reuse the V1 mutants.

---

## V4. Proxy trust radius — *sharpened*

**Pitch.** Calibrate every cheap physics proxy against T3 simulation on synthetic families, and record the feature-space region where it ranks candidates correctly. Optimizers may not exploit a proxy outside that region; they escalate fidelity instead.

**Mechanism.**
1. Choose a proxy p: loop nH, crosstalk K, MREMC V_ab, the thermal screener, or mounting L.
2. Generate parameter sweeps and compute T3 results (openEMS, FastHenry, Elmer).
3. Fit the validity region (rank correlation ≥ ρ, error ≤ e) as a box or hull in feature space.
4. At runtime, flag every candidate scored by p as in or out of its region.
5. Only in-region scores count toward the reward. Out-of-region candidates get T2/T3 scheduled or are marked "unverified".

**Why it should work.**
- Proxies must be calibrated before they are rewarded ([evaluation-stack](../../topics/verification/evaluation-stack.md)).
- Published correlations between routing proxies and completion are few and weak (one unreviewed 64-board study, one patent dataset), so calibrate before use ([performance-and-multifidelity](../../topics/solvers/performance-and-multifidelity.md), [imitation](../../topics/data/imitation-and-learned-scores.md), [patents](../../topics/landscape/patents-watchlist.md)).
- No figure of merit links scores to lab outcomes ([quality-metrics](../../topics/verification/quality-metrics.md)).
- Optimizers find proxy errors (Goodhart's law).

**Builds on.** prac#323–324; alg#135, alg#330.

**How to test.** Run optimizers with and without the trust radius. Metric: the fraction of "optimized" candidates whose T3 result is worse than the baseline's.

**Effort/risk.** M. T3 compute is costly; start with loop nH and crosstalk, which are cheap.

---

## V5. Counterexample-guided rule refinement — *new*

**Pitch.** When simulation or bench measurement exposes a failure that every fast check passed, the LLM proposes a new or tightened fast check that would have caught it. The check is accepted only if it flags the counterexample and stays silent on a corpus of passing designs.

**Mechanism.** A CEGAR loop:
1. **Input:** a counterexample (the board plus its T3 or measured failure). Measurements can include EMC pre-scan peaks, thermal-camera images and VNA traces.
2. **Proposal:** the LLM writes check code over the board model, tied to a mechanism from [I3](intent-and-why.md#i3-mechanism-layer-intent-graph-why-graph--novel-combination).
3. **Validation:** the check
   - fires on the counterexample;
   - stays at or below a false-positive rate f on N passing boards;
   - meets the [V1](#v1-mutation-tested-layout-unit-tests--new) mutation score.
4. **Adoption:** the check joins the rule pack as an [I] warning until calibrated, linked to its mechanism and provenance.

**Why it should work.**
- Checklists should grow after every escaped error ([respin](../../topics/verification/respin-and-fab-hold-data.md), [critic-stack](../../topics/verification/critic-stack.md)).
- LLM-written analysis code validated against measurement already works in the field ([llm-field-reports](../../topics/workflow/llm-field-reports.md)).
- Rule packs need calibration on EVMs ([rule-pack-format](../../topics/rules/rule-pack-format.md)).

**Builds on.** prac#18, prac#239; llm#68; hs#156.

**How to test.** Hold out 20 T3 failures. Measure the fraction for which an accepted fast check is found, and its false-positive rate on held-out passing boards.

**Effort/risk.** M. Checks can overfit; requiring a mechanism link and a held-out false-positive test limits this.
