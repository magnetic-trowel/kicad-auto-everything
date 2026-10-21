# Original ideas: representations that carry the "why"

Part of the [original-ideas catalog](README.md). Everything here is our proposal [I]; the evidence links point to topic docs. Inventory shorthands: `alg#` [algorithms](../inventory-algorithms.md), `llm#` [LLM/data/UX](../inventory-llm-data-ux.md), `prac#` [practice/evaluation](../inventory-practice-evaluation.md), `eco#` [ecosystem](../inventory-ecosystem.md), `hs#` [HS/EMI rules](../inventory-rules-hs-emi.md), `pwr:` [power rules](../inventory-rules-power.md) (by section), `xd#` [cross-domain rank](../cross-domain-transplants.md).

The common thread: the LLM is good at semantic choices and bad at geometry, so give it a semantic layer for *physics*, not only for topology.

---

## I1. Physics budget ledger — *novel combination*

**Pitch.** Replace millimetre rules with per-mechanism budgets in physical units (dB, ps, nH, mV, °C). Budgets are allocated across sub-elements, spent by board objects, and reported with per-object attribution.

**Mechanism.** Each high-level intent declares budgets:
- USB3/PCIe channel: insertion loss at Nyquist (dB), skew (ps), uncoupled length;
- hot loop: L_max = 0.2·V_DS,max / (di/dt) in nH;
- decoupling: mounting inductance derived from Z_t;
- victim net: crosstalk noise (mV) shared across aggressors via K = 1/(1+(D/H)²);
- hot part: ΔT.

Deterministic *spend models* charge each object. Examples: a trace segment costs dB/mm from the stackup; a via costs 25–50 mm equivalent; ESD+CMC costs ≈1 in; a loop polygon costs nH from area and plane depth; a parallel run costs mV.

The ledger row is {budget, limit, allocation per segment or sub-block, spent, top spenders}. The LLM's only write actions are `allocate(budget, {a: 40%, b: 60%})` and `transfer(from, to)`. Solvers consume allocations as penalties (placement) or costs (routing). Checkers recompute spend after realization. Where no spend model exists, fall back to a millimetre proxy tagged [I].

**Why it should work.**
- Loss budgets already beat stored lengths for SerDes ([pcie](../../topics/rules/interfaces/pcie.md)).
- Inductance anchors make "minimise the loop" numeric ([hot-loops](../../topics/rules/power/hot-loops.md)).
- Crosstalk spacing should come from a noise budget ([si-fundamentals](../../topics/rules/si-fundamentals.md)).
- Rule packs already want formulas in h, t_r and UI, not slogans ([rule-pack-format](../../topics/rules/rule-pack-format.md), [myths](../../topics/rules/myths-and-contested.md)).

Budgets are to physics what relation bundles are to placement: a compact semantic layer the LLM can reason over.

**Builds on.** hs#21, hs#46, hs#62–63, hs#67; pwr: loop-inductance anchors and overshoot calculator; prac#248, prac#270–274.

**How to test.** Port the USB2, USB3, PCIe and buck packs to budgets. On 20 PCBWorld D3 boards plus 10 synthetic boards, compare the mm packs with the ledger on three counts: false violations (flagged, but physics is fine per T2/T3), missed violations, and routability. Baseline: the packs as written.

**Effort/risk.** M. Spend models are approximate; bound their use with [V4](verification.md#v4-proxy-trust-radius--sharpened).

---

## I2. Dimensioned constraint types with derivation traces — *new*

**Pitch.** Give every IR number a physical dimension and a symbolic origin (3h, t_r/6, λ_g/20, 0.1·UI). Type-check it, resolve it lazily against stackup and net facts, and keep the derivation as the explanation.

**Mechanism.** The value grammar is `Quantity(expr, dim)`. `expr` may reference:
- stackup symbols: h(L1→In1), Dk, w_50Ω;
- net facts: t_r from IBIS `[Ramp]`, data rate, I_max;
- part facts: pitch, pad size.

A small checker (pint-style dimensions plus UI and fraction-of-t_r) refuses `spacing: 3W` without a W binding and `skew: 5` without a unit.

Compilation resolves each value to mm or ps and attaches a derivation, for example `["3·h", "h(L1→In1)=0.11 mm (stackup rev B)", "=0.33 mm"]`. A stackup change re-resolves every derived number and lists which rules moved. The LLM writes expressions and never writes resolved numbers.

**Why it should work.**
- KiCad accepts only mm/mil/in/deg/ps/fs, and silently mishandles some documented units ([drc-rule-language-reference](../../topics/kicad/drc-rule-language-reference.md)).
- Rules belong in units of h and t_r ([si-fundamentals](../../topics/rules/si-fundamentals.md)).
- "Never invent millimetres" ([datasheet-extraction](../../topics/llm/datasheet-extraction.md)).
- LLM-drafted rationale has about 0.27 precision ([design-rationale](../../topics/ux/design-rationale-and-intent-record.md)), so numbers should explain themselves.

**Builds on.** hs#80, hs#153, hs#155; llm#13, llm#219; eco#45.

**How to test.** Seed 50 unit and dimension errors into LLM-authored constraint sets; measure the catch rate. Change the stackup on 5 boards and compare the re-derived values with hand calculations.

**Effort/risk.** S. Keep the expression language to arithmetic over named symbols.

---

## I3. Mechanism-layer intent graph ("why-graph") — *novel combination*

**Pitch.** Insert an explicit physics-mechanism layer between requirements and rules. Then any board object answers "why here?" by a graph walk, and any edit answers "what breaks?" by forward impact.

**Mechanism.** A typed DAG with these node kinds:
- **Requirement** (spec, datasheet or user, with provenance);
- **Mechanism**, from a closed catalog of about 40 (return current under the trace, loop-inductance overshoot, skew→common mode, antenna voltage between connectors, mounting inductance, thermal spreading, creepage, and so on);
- **Constraint** (IR primitive), **Budget** ([I1](#i1-physics-budget-ledger--novel-combination)), **Object** (footprint, net, zone, via), **Check** (PRC or DRC rule id).

Edges: `requires`, `explained-by`, `enforced-by`, `realized-by`, `verified-by`. Each mechanism card holds the formula, units, check, a canonical counterexample and links to related myths.

The LLM authors only Requirement→Mechanism edges. That is the tacit part, Pease's criticality. The compiler generates the rest.

Two queries:
- `why(object)` returns the paths to Requirements, with verdicts and margins.
- `impact(edit)` returns the forward closure, which is the list of checks to re-run. It doubles as an incremental-verification scheduler.

**Why it should work.**
- Classic rationale capture failed on effort and retrieval; captured rationale answered only 41% of designers' questions ([design-rationale](../../topics/ux/design-rationale-and-intent-record.md)).
- Myths need a physics replacement ([myths](../../topics/rules/myths-and-contested.md)).
- Explanations help only when they cut verification cost ([explanations](../../topics/ux/explanations-and-alternatives.md)).

**Builds on.** llm#407, llm#425–426, llm#430; prac#277; hs#1, hs#148.

**How to test.** Pose 100 designer-style why/what-if questions over 5 boards. Compare graph-walk answers with post-hoc LLM rationale. Metrics: claim precision and recall against an expert key, and time to verify. Also time `impact()` against a full re-check.

**Effort/risk.** M. The risk is catalog completeness. Start with the roughly 15 mechanisms behind the 41 Critical checklist items ([review-checklist](../../topics/verification/review-checklist.md)).

---

## I4. Constraint price tags and precomputed foils — *new for PCB*

**Pitch.** After every solve, attach to each constraint its measured cost in wirelength, vias, area and routability, plus the best "foil" solution with that constraint dropped or flipped. Negotiation and explanation then run on numbers.

**Mechanism.** Prices come from three sources:
1. LP duals from the legalizer's relaxation, and the analytical placer's penalty multipliers at convergence (cheap, local).
2. Leave-one-out re-solves for the top-k binding constraints, warm-started window LNS in background workers (exact, seconds each).
3. For routing, a bounded re-route with the constraint's keep-out or reservation removed.

The output is `prices.json` {constraint, binding, Δhpwl, Δvias, Δarea, Δcompletion, foil_id}. The LLM receives a ranked table of at most 20 rows. The UI shows lines such as "the 2 mm decap rule on C7 costs 4 vias; foil available".

**Why it should work.**
- About 90% of users' questions are contrastive, and compiling them into a re-solve answered 89.8% ([explanations](../../topics/ux/explanations-and-alternatives.md)).
- Feedback naming admissible relaxations helps LLMs revise commitments ([interfaces](../../topics/llm/interfaces-relations-vs-coordinates.md)).
- Window LNS makes local re-solves cheap ([cp-sat](../../topics/solvers/cp-sat-milp-smt.md)).

**Builds on.** llm#5, llm#398, llm#400, llm#432; alg#75.

**How to test.** On over-constrained synthetic boards, compare an LLM relaxation loop given conflict lists alone with one given conflict lists plus prices. Metrics: iterations to feasibility, budget overspend of the chosen relaxations, and tokens.

**Effort/risk.** S–M. Prices are not additive, so report pairwise prices for the top conflicts only.

---

## I5. Criticality field and criticality-proportional compute — *novel combination*

**Pitch.** Compile roles, edge rates, currents and consequence classes into one human-confirmed criticality score per net, loop or part, and rasterize it over the board. The field then sets solver time, routing order, verification fidelity and which questions get asked.

**Mechanism.**

score = consequence (safety > compliance > function > cosmetic) × physics risk × uncertainty

Physics risk uses the t_r-relative electrical length (IBIS ramp × estimated length), di/dt for loops, impedance level for high-Z analog nodes, and RF band. The deterministic score comes first; the LLM adjusts it with a written reason, and a human confirms the top N.

Consumers:
- LNS window selection probability ∝ field;
- beam width per net ([R8](routing.md#r8-physics-scored-beam-search-over-pns-checkpoints--sharpened));
- routing tiers;
- the T2/T3 simulation budget for the top-k;
- question order in the brief ([U3](workflow-ux.md#u3-expected-loss-ordered-intent-brief--sharpened)).

**Why it should work.**
- Knowing what is critical is tacit expertise and the LLM's core contribution ([checkers-power](../../topics/rules/checkers-power.md)).
- Placement effort pays back where routing payoff is large ([deeppcb](../../topics/landscape/deeppcb.md)).
- IBIS answers "is this net fast?" ([net-role-classification](../../topics/llm/net-role-classification.md)).
- T3 simulation is too expensive to run everywhere ([evaluation-stack](../../topics/verification/evaluation-stack.md)).

**Builds on.** pwr: criticality map; eco#122; llm#179, llm#182, llm#195; prac#125.

**How to test.** On 30 boards with equal wall-clock, compare uniform allocation with criticality-weighted allocation. Metrics: PRC pass rate on the top-decile critical constraints, overall clean pass, and T3 failures found per CPU-hour.

**Effort/risk.** S–M. A mis-scored net could be starved; keep a floor allocation and show the field in the brief.

---

## I6. Intent diff across revisions — *new*

**Pitch.** Diff two revisions at the level of intents, budgets and verdicts, not geometry. The report then reads "rev C dropped near(C12, U3.VDD, tight) and overspent the USB loss budget by 0.4 dB".

**Mechanism.** For each revision, re-run the deterministic part of comprehension and load the persisted IR into an intent graph. Diff the node and edge sets on stable IR ids and hierarchical addresses, then add verdict deltas (pass→fail, or margin shrink above X%).

Categories:
- intent added, removed or modified;
- intent kept but verdict regressed;
- geometry moved with no intent change (benign);
- rule changed with geometry unchanged.

It runs as a git pre-commit hook and as a PR comment, including on edits made only by humans.

**Why it should work.**
- Relations survive geometry change (re-solve passes 89.5%), so they make a stable key ([interfaces](../../topics/llm/interfaces-relations-vs-coordinates.md)).
- Reviewable diffs build trust ([design-rationale](../../topics/ux/design-rationale-and-intent-record.md)).
- Respins run about 2.9 per project ([respin](../../topics/verification/respin-and-fab-hold-data.md)).

**Builds on.** llm#6, llm#207, llm#330; eco#135; prac#4.

**How to test.** Seed 40 intent regressions into revision pairs from open repos. Compare detection rate and false alarms with a geometric diff plus a DRC diff.

**Effort/risk.** S once the IR exists. Key ids on hierarchical paths plus UUIDs so they survive re-annotation.

---

## I7. Intent that travels inside the `.kicad_pcb` — *sharpened*

**Pitch.** Stamp intent ids and one-line rationales into KiCad-native objects. The "why" then survives other tools, plain-KiCad edits and a lost sidecar.

**Mechanism.** The compiler writes:
- a footprint field `Intent` listing IR ids;
- a component class per block and role;
- rule areas named `IR:buck1.region`;
- groups named after their recipe instance;
- DRU rules named `IR:<id>`, each with a comment giving its mechanism and source;
- a hash of the sidecar on a user layer.

On load, reconciliation runs. A missing sidecar is partly rebuilt from the stamps. Stamps a human has edited are treated as intent edits.

**Why it should work.**
- Component classes, rule areas and design blocks are native levers ([built-in-automation-features](../../topics/kicad/built-in-automation-features.md)).
- DRC JSON has no rule-name field, so IR-named rules are needed for attribution ([drc-report-and-repair-loop](../../topics/kicad/drc-report-and-repair-loop.md)).
- Intent emitted as KiCad artifacts is inspectable and checkable ([constraint-ir](../../topics/architecture/constraint-ir.md)).

**Builds on.** eco#49, eco#57; llm#190–192; prac#311.

**How to test.** Delete the sidecar and measure how much IR is reconstructed. Edit the board in plain KiCad 9.0 and 10.0 and check that the stamps survive save and load.

**Effort/risk.** S. Keep stamps short to avoid clutter.
