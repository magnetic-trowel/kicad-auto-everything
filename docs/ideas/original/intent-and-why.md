# Original ideas: representations that carry the "why"

Scope: I1–I7, a semantic layer for *physics* (not only topology) for an LLM that is good at semantic choices and bad at geometry. Part of the [original-ideas catalog](README.md); all our proposals [I]; evidence links point to topic docs. Test status: [research/ideas](../../research/ideas.md#original-ideas-58).
Keys: I1 physics budget ledger, spend model, allocate, I2 dimensioned constraint types, Quantity(expr, dim), derivation trace, I3 why-graph, mechanism catalog, impact(), I4 constraint price tags, foil, prices.json, I5 criticality field, I6 intent diff, I7 intent in .kicad_pcb, IR stamps

Inventory shorthands (used by every theme file): `alg#` [algorithms](../inventory-algorithms.md), `llm#` [LLM/data/UX](../inventory-llm-data-ux.md), `prac#` [practice/evaluation](../inventory-practice-evaluation.md), `eco#` [ecosystem](../inventory-ecosystem.md), `hs#` [HS/EMI rules](../inventory-rules-hs-emi.md), `pwr:` [power rules](../inventory-rules-power.md) (by section), `xd#` [cross-domain rank](../cross-domain-transplants.md). Numbers are inventory line numbers.

## I1. Physics budget ledger — *novel combination*

Idea: replace millimetre rules with per-mechanism budgets in physical units (dB, ps, nH, mV, °C), allocated across sub-elements, spent by board objects, reported with per-object attribution.
Mechanism:
- Budgets per intent: USB3/PCIe channel: insertion loss at Nyquist (dB), skew (ps), uncoupled length; hot loop: L_max = 0.2·V_DS,max/(di/dt) (nH); decoupling: mounting inductance derived from Z_t; victim net: crosstalk noise (mV) shared across aggressors via K = 1/(1+(D/H)²); hot part: ΔT.
- Deterministic *spend models* charge each object: trace segment dB/mm from the stackup; via 25–50 mm equivalent; ESD+CMC ≈1 in; loop polygon nH from area and plane depth; parallel run mV.
- Ledger row {budget, limit, allocation per segment or sub-block, spent, top spenders}. The LLM's only writes: `allocate(budget, {a: 40%, b: 60%})`, `transfer(from, to)`.
- Solvers consume allocations as penalties (placement) or costs (routing); checkers recompute spend after realization; with no spend model, fall back to a millimetre proxy tagged [I].
Evidence [I]: loss budgets already beat stored lengths for SerDes ([pcie](../../topics/rules/interfaces/pcie.md)); inductance anchors make "minimise the loop" numeric ([hot-loops](../../topics/rules/power/hot-loops.md)); crosstalk spacing should come from a noise budget ([si-fundamentals](../../topics/rules/si-fundamentals.md)); rule packs want formulas in h, t_r and UI, not slogans ([rule-pack-format](../../topics/rules/rule-pack-format.md), [myths](../../topics/rules/myths-and-contested.md)). Budgets are to physics what relation bundles are to placement.
Builds on: hs#21, hs#46, hs#62–63, hs#67; pwr: loop-inductance anchors, overshoot calculator; prac#248, prac#270–274 · Test: port USB2, USB3, PCIe, buck packs to budgets; 20 PCBWorld D3 + 10 synthetic boards, mm packs (baseline, as written) vs ledger on false violations (flagged but physics fine per T2/T3), missed violations, routability · Effort/risk: M; spend models approximate: bound their use with [V4](verification.md#v4-proxy-trust-radius--sharpened).

## I2. Dimensioned constraint types with derivation traces — *new*

Idea: every IR number has a physical dimension and a symbolic origin (3h, t_r/6, λ_g/20, 0.1·UI), is type-checked, resolved lazily against stackup and net facts, and keeps its derivation as the explanation.
Mechanism:
- Value grammar `Quantity(expr, dim)`; `expr` references stackup symbols (h(L1→In1), Dk, w_50Ω), net facts (t_r from IBIS `[Ramp]`, data rate, I_max), part facts (pitch, pad size).
- Checker (pint-style dimensions + UI and fraction-of-t_r) refuses `spacing: 3W` without a W binding and `skew: 5` without a unit.
- Compilation resolves to mm or ps with a derivation, e.g. `["3·h", "h(L1→In1)=0.11 mm (stackup rev B)", "=0.33 mm"]`; a stackup change re-resolves every derived number and lists which rules moved. The LLM writes expressions, never resolved numbers.
Evidence [I]: KiCad accepts only mm/mil/in/deg/ps/fs and silently mishandles some documented units ([drc-rule-language-reference](../../topics/kicad/drc-rule-language-reference.md)); rules belong in units of h and t_r ([si-fundamentals](../../topics/rules/si-fundamentals.md)); "never invent millimetres" ([datasheet-extraction](../../topics/llm/datasheet-extraction.md)); LLM-drafted rationale has about 0.27 precision ([design-rationale](../../topics/ux/design-rationale-and-intent-record.md)), so numbers should explain themselves.
Builds on: hs#80, hs#153, hs#155; llm#13, llm#219; eco#45 · Test: seed 50 unit/dimension errors into LLM-authored constraint sets, measure catch rate; change the stackup on 5 boards, compare re-derived values with hand calculations · Effort/risk: S; keep the expression language to arithmetic over named symbols.

## I3. Mechanism-layer intent graph ("why-graph") — *novel combination*

Idea: an explicit physics-mechanism layer between requirements and rules, so any object answers "why here?" by a graph walk and any edit answers "what breaks?" by forward impact.
Mechanism:
- Typed DAG nodes: **Requirement** (spec, datasheet or user, with provenance); **Mechanism** from a closed catalog of about 40 (return current under the trace, loop-inductance overshoot, skew→common mode, antenna voltage between connectors, mounting inductance, thermal spreading, creepage, ...); **Constraint** (IR primitive); **Budget** ([I1](#i1-physics-budget-ledger--novel-combination)); **Object** (footprint, net, zone, via); **Check** (PRC or DRC rule id).
- Edges `requires`, `explained-by`, `enforced-by`, `realized-by`, `verified-by`. Mechanism card: formula, units, check, canonical counterexample, links to related myths.
- The LLM authors only Requirement→Mechanism edges (the tacit part, Pease's criticality); the compiler generates the rest.
- Queries: `why(object)` → paths to Requirements with verdicts and margins; `impact(edit)` → forward closure = checks to re-run (doubles as an incremental-verification scheduler).
Evidence [I]: classic rationale capture failed on effort and retrieval; captured rationale answered only 41% of designers' questions ([design-rationale](../../topics/ux/design-rationale-and-intent-record.md)); myths need a physics replacement ([myths](../../topics/rules/myths-and-contested.md)); explanations help only when they cut verification cost ([explanations](../../topics/ux/explanations-and-alternatives.md)).
Builds on: llm#407, llm#425–426, llm#430; prac#277; hs#1, hs#148 · Test: 100 designer-style why/what-if questions over 5 boards, graph-walk answers vs post-hoc LLM rationale; metrics claim precision/recall against an expert key, time to verify; time `impact()` vs full re-check · Effort/risk: M; risk = catalog completeness: start with the roughly 15 mechanisms behind the 41 Critical checklist items ([review-checklist](../../topics/verification/review-checklist.md)).

## I4. Constraint price tags and precomputed foils — *new for PCB*

Idea: after every solve, attach to each constraint its measured cost in wirelength, vias, area and routability, plus the best "foil" solution with that constraint dropped or flipped, so negotiation and explanation run on numbers.
Mechanism: prices from (1) LP duals of the legalizer's relaxation and the analytical placer's penalty multipliers at convergence (cheap, local); (2) leave-one-out re-solves for the top-k binding constraints, warm-started window LNS in background workers (exact, seconds each); (3) for routing, a bounded re-route with the constraint's keep-out or reservation removed. Output `prices.json` {constraint, binding, Δhpwl, Δvias, Δarea, Δcompletion, foil_id}; the LLM gets a ranked table of ≤ 20 rows; UI lines like "the 2 mm decap rule on C7 costs 4 vias; foil available".
Evidence [I]: about 90% of users' questions are contrastive; compiling them into a re-solve answered 89.8% ([explanations](../../topics/ux/explanations-and-alternatives.md)); feedback naming admissible relaxations helps LLMs revise commitments ([interfaces](../../topics/llm/interfaces-relations-vs-coordinates.md)); window LNS makes local re-solves cheap ([cp-sat](../../topics/solvers/cp-sat-milp-smt.md)).
Builds on: llm#5, llm#398, llm#400, llm#432; alg#75 · Test: over-constrained synthetic boards, LLM relaxation loop with conflict lists alone vs conflict lists + prices; metrics iterations to feasibility, budget overspend of chosen relaxations, tokens · Effort/risk: S–M; prices are not additive: report pairwise prices for the top conflicts only.

## I5. Criticality field and criticality-proportional compute — *novel combination*

Idea: compile roles, edge rates, currents and consequence classes into one human-confirmed criticality score per net, loop or part, rasterized over the board, setting solver time, routing order, verification fidelity and which questions get asked.
Mechanism:
- score = consequence (safety > compliance > function > cosmetic) × physics risk × uncertainty; physics risk from t_r-relative electrical length (IBIS ramp × estimated length), di/dt for loops, impedance level for high-Z analog nodes, RF band.
- Deterministic score first; the LLM adjusts with a written reason; a human confirms the top N.
- Consumers: LNS window selection probability ∝ field; beam width per net ([R8](routing.md#r8-physics-scored-beam-search-over-pns-checkpoints--sharpened)); routing tiers; T2/T3 simulation budget for the top-k; question order in the brief ([U3](workflow-ux.md#u3-expected-loss-ordered-intent-brief--sharpened)).
Evidence [I]: knowing what is critical is tacit expertise and the LLM's core contribution ([checkers-power](../../topics/rules/checkers-power.md)); placement effort pays back where routing payoff is large ([deeppcb](../../topics/landscape/deeppcb.md)); IBIS answers "is this net fast?" ([net-role-classification](../../topics/llm/net-role-classification.md)); T3 simulation is too expensive to run everywhere ([evaluation-stack](../../topics/verification/evaluation-stack.md)).
Builds on: pwr: criticality map; eco#122; llm#179, llm#182, llm#195; prac#125 · Test: 30 boards, equal wall-clock, uniform vs criticality-weighted allocation; metrics PRC pass rate on top-decile critical constraints, overall clean pass, T3 failures found per CPU-hour · Effort/risk: S–M; a mis-scored net could be starved: keep a floor allocation, show the field in the brief.

## I6. Intent diff across revisions — *new*

Idea: diff two revisions at the level of intents, budgets and verdicts, not geometry ("rev C dropped near(C12, U3.VDD, tight) and overspent the USB loss budget by 0.4 dB").
Mechanism: per revision, re-run the deterministic part of comprehension and load the persisted IR into an intent graph; diff node and edge sets on stable IR ids and hierarchical addresses; add verdict deltas (pass→fail, margin shrink above X%). Categories: intent added/removed/modified; intent kept but verdict regressed; geometry moved with no intent change (benign); rule changed with geometry unchanged. Runs as a git pre-commit hook and a PR comment, including on human-only edits.
Evidence [I]: relations survive geometry change (re-solve passes 89.5%), so they make a stable key ([interfaces](../../topics/llm/interfaces-relations-vs-coordinates.md)); reviewable diffs build trust ([design-rationale](../../topics/ux/design-rationale-and-intent-record.md)); respins run about 2.9 per project (Lifecycle Insights, cited only in vendor marketing; [respin](../../topics/verification/respin-and-fab-hold-data.md)).
Builds on: llm#6, llm#207, llm#330; eco#135; prac#4 · Test: seed 40 intent regressions into revision pairs from open repos; detection rate and false alarms vs geometric diff + DRC diff · Effort/risk: S once the IR exists; key ids on hierarchical paths + UUIDs so they survive re-annotation.

## I7. Intent that travels inside the `.kicad_pcb` — *sharpened*

Idea: stamp intent ids and one-line rationales into KiCad-native objects so the "why" survives other tools, plain-KiCad edits and a lost sidecar.
Mechanism: the compiler writes a footprint field `Intent` listing IR ids; a component class per block and role; rule areas named `IR:buck1.region`; groups named after their recipe instance; DRU rules named `IR:<id>`, each with a comment giving mechanism and source; a hash of the sidecar on a user layer. On load, reconcile: a missing sidecar is partly rebuilt from the stamps; stamps a human edited are treated as intent edits.
Evidence [I]: component classes, rule areas and design blocks are native levers ([built-in-automation-features](../../topics/kicad/built-in-automation-features.md)); DRC JSON has no rule-name field, so IR-named rules are needed for attribution ([drc-report-and-repair-loop](../../topics/kicad/drc-report-and-repair-loop.md)); intent emitted as KiCad artifacts is inspectable and checkable ([constraint-ir](../../topics/architecture/constraint-ir.md)).
Builds on: eco#49, eco#57; llm#190–192; prac#311 · Test: delete the sidecar, measure how much IR is reconstructed; edit the board in plain KiCad 9.0 and 10.0, check stamps survive save and load · Effort/risk: S; keep stamps short to avoid clutter.
