# Original ideas: verification, critics and anti-reward-hacking

Scope: V1–V5, making checks trustworthy before anything optimizes against them. Part of the [original-ideas catalog](README.md); shorthands as in [intent-and-why](intent-and-why.md). Baseline: three-tier critic stack (A: DRC, S: semantic geometry, J: LLM judge) and T0–T3 evaluation tiers ([critic-stack](../../topics/verification/critic-stack.md), [evaluation-stack](../../topics/verification/evaluation-stack.md)). Test status: [research/ideas](../../research/ideas.md#original-ideas-58).
Keys: V1 mutation-tested layout unit tests, mutation score, V2 red-team reward hacker gate, V3 judge licensing, seeded-fault exam, V4 proxy trust radius, V5 counterexample-guided rule refinement, CEGAR

## V1. Mutation-tested layout unit tests — *new*

Idea: compile every intent into executable tests over the board model; accept a test (including LLM-written checkers and LLM-written `.kicad_dru` rules) only if it kills generated near-miss mutants and still passes on compliant variants.
Mechanism:
- Test = function `(board, ir) → {pass, measured, limit}`.
- Mutation operators per primitive: move a part across a proximity threshold by ±ε; flip its side or swap its layer; insert a via before a TVS; delete a stitching via; shift one pair leg to create skew; narrow a power neck.
- Mutants generated from the current board, so each test is validated on the actual design.
- Acceptance: mutation score ≥ threshold and zero false positives on ≥ 10 compliant perturbations; DRU rules run through `kicad-cli` DRC on the mutants.
- Runs in CI (git hook) and after every agent step.
Evidence [I]: LLMs write detector code well; accepting code only when tests pass works ([block-recognition](../../topics/llm/block-recognition.md)); every primitive needs a checker with pass criteria ([constraint-ir](../../topics/architecture/constraint-ir.md)); DRU pitfalls silently disable rules: the last matching rule wins, a second `condition` overwrites the first ([drc-rule-language-reference](../../topics/kicad/drc-rule-language-reference.md)); muted checks are a top field failure ([field-failure-modes](../../topics/ux/field-failure-modes.md)).
Builds on: llm#174–175, llm#217, llm#297; prac#207, prac#235; eco#51 · Test: seed 100 faults from the 299-item checklist into 10 boards; escaped-defect rate for mutation-validated tests vs unvalidated LLM tests vs DRC alone · Effort/risk: S–M; operators designed per primitive: start with 8.

## V2. Red-team reward hacker as a gate — *new*

Idea: before any RL, evolution or autonomous loop optimizes a score, an adversarial agent tries to maximize that score while violating intent; every hack found becomes a regression test and a scorer fix.
Mechanism: sandboxed red-team agent with the scorer API and full tool surface; forbidden outcomes: shorts through planes, deleted nets, rule edits relaxing clearances, `ignore` severities, net-tie abuse, copper outside the board, edits to locked objects, geometry hidden on unused layers; reward = score gain × intent violation, confirmed by an independent auditor; gate: optimization starts only once the red team finds no new hack within its budget.
Evidence [I]: scoreboard gaming has been observed, so the harness must be immutable to agents ([trust-requirements](../../topics/workflow/trust-requirements.md)); a no-tools baseline passed DRC while routing through the GND plane ([kicad-ai-tools](../../topics/landscape/kicad-ai-tools-and-mcp-servers.md)); RL routers find reward loopholes ([imitation](../../topics/data/imitation-and-learned-scores.md)); legality must be part of the acceptance contract ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md)).
Builds on: prac#202; llm#64, llm#299; eco#201 · Test: hacks found per scorer version; hack incidence in later GRPO and evolution runs with vs without the gate · Effort/risk: S; limited by the red team's imagination: seed it with the field-failure list.

## V3. Judge licensing by seeded-fault exams — *sharpened*

Idea: the LLM/VLM judge may gate only checklist categories where it passed a seeded-fault exam with measured precision and recall; elsewhere it may annotate but not block or approve.
Mechanism: exam set = boards with seeded faults per checklist category + clean controls, refreshed regularly against contamination ([V1](#v1-mutation-tested-layout-unit-tests--new) mutants can supply the faults); judge scored per category for a given model and prompt; licence at recall ≥ R and precision ≥ P; re-exam on any model change; reports disclose unlicensed categories ("judge unlicensed for EMC stitching").
Evidence [I]: uncertain judge findings already go to a human ([critic-stack](../../topics/verification/critic-stack.md)); a seeded checklist track is already planned ([benchmark-plan](../../topics/verification/benchmark-plan.md)); explanations can raise overreliance ([explanations](../../topics/ux/explanations-and-alternatives.md)); a VLM pros/cons judge agreed with humans about 77% of the time, not uniformly across cases ([scene-layout-transplants](../../topics/placement/scene-layout-transplants.md)).
Builds on: prac#123, prac#346; llm#68; xd#4 · Test: exam test–retest reliability; escaped defects in licensed categories · Effort/risk: S; seeded sets take work: reuse the V1 mutants.

## V4. Proxy trust radius — *sharpened*

Idea: calibrate every cheap physics proxy against T3 simulation on synthetic families and record the feature-space region where it ranks candidates correctly; optimizers may not exploit a proxy outside that region and escalate fidelity instead.
Mechanism:
1. Proxy p: loop nH, crosstalk K, MREMC V_ab, thermal screener, or mounting L.
2. Parameter sweeps with T3 results (openEMS, FastHenry, Elmer).
3. Fit the validity region (rank correlation ≥ ρ, error ≤ e) as a box or hull in feature space.
4. At runtime flag every candidate scored by p as in or out of region.
5. Only in-region scores count toward the reward; out-of-region candidates get T2/T3 scheduled or are marked "unverified".
Evidence [I]: proxies must be calibrated before they are rewarded ([evaluation-stack](../../topics/verification/evaluation-stack.md)); published routing-proxy-to-completion correlations are few and weak (one unreviewed 64-board study, one patent dataset) ([performance-and-multifidelity](../../topics/solvers/performance-and-multifidelity.md), [imitation](../../topics/data/imitation-and-learned-scores.md), [patents](../../topics/landscape/patents-watchlist.md)); no figure of merit links scores to lab outcomes ([quality-metrics](../../topics/verification/quality-metrics.md)); optimizers find proxy errors (Goodhart's law).
Builds on: prac#323–324; alg#135, alg#330 · Test: optimizers with vs without the trust radius; metric fraction of "optimized" candidates whose T3 result is worse than the baseline's · Effort/risk: M; T3 compute is costly: start with loop nH and crosstalk (cheap).

## V5. Counterexample-guided rule refinement — *new*

Idea: when simulation or bench measurement exposes a failure every fast check passed, the LLM proposes a new or tightened fast check that would have caught it; accepted only if it flags the counterexample and stays silent on a corpus of passing designs.
Mechanism (CEGAR loop):
1. Input: counterexample = board + its T3 or measured failure (EMC pre-scan peaks, thermal-camera images, VNA traces).
2. Proposal: LLM-written check code over the board model, tied to a mechanism from [I3](intent-and-why.md#i3-mechanism-layer-intent-graph-why-graph--novel-combination).
3. Validation: fires on the counterexample; false-positive rate ≤ f on N passing boards; meets the [V1](#v1-mutation-tested-layout-unit-tests--new) mutation score.
4. Adoption: joins the rule pack as an [I] warning until calibrated, linked to its mechanism and provenance.
Evidence [I]: checklists should grow after every escaped error ([respin](../../topics/verification/respin-and-fab-hold-data.md), [critic-stack](../../topics/verification/critic-stack.md)); LLM-written analysis code validated against measurement already works in the field ([llm-field-reports](../../topics/workflow/llm-field-reports.md)); rule packs need calibration on EVMs ([rule-pack-format](../../topics/rules/rule-pack-format.md)).
Builds on: prac#18, prac#239; llm#68; hs#156 · Test: hold out 20 T3 failures; fraction with an accepted fast check found, its false-positive rate on held-out passing boards · Effort/risk: M; checks can overfit: mechanism link + held-out false-positive test limit this.
