# System design: physics-first, LLM-assisted placement and routing

**TL;DR**
- **Four product surfaces share one evaluator:** a copper doctor (review), a joint placement, routing and copper optimizer, an LLM physicist (brief, explanations) and the benchmark harness. All read one physics core and one critic suite, so each surface built early becomes part of the later ones.
- **The copper doctor ships first.** It works on any existing board and changes nothing without approval. It needs only kernels and critics that already run on real boards, and its findings show where optimization can pay.
- **Packages depend one way:** units → board → intent → circuit, physics → critics → optimize → agent → MCP and plugin. The harness depends on none of them. The contracts are files: `intent.yaml` (required), `ledger.json` (observed, written by code only), passports, Beliefs, findings in KiCad's `drc.v1` shape, and a decision DAG.
- **Process model:** a library, plus one session server per board for live and optimizer use. The server owns the single KiCad connection, the DAG and a physics service that keeps factorizations warm. A `BoardSession` hides KiCad 10's four channels and KiCad 11's headless server.
- **The LLM is a physicist on a bounded contract.** It adjudicates detections, proposes budgets and hypotheses, chooses from priced menus and explains by citing Beliefs. It never writes coordinates or numbers. Estimated cost: 60–170k tokens per designed board, 15–50k per review [I].

Tags: [P] primary, [C] computed by the named scripts, [I] inference; the design is untested [I]. Engine internals: [physics-engine-design](physics-engine-design.md). Milestones: [system-design-build-plan](system-design-build-plan.md).

## 1. Purpose and product surfaces

The system takes a schematic and fixed constraints: outline, holes, connectors, antenna region, heatsink, keep-outs, fab profile, stackup options, and the enclosure and cables where known. It returns a DRC-clean layout in which every part of the unintended physics is invisible, known or designed within budgets ([foundations](../physics/foundations.md)). Every piece of copper carries a passport that says what it does ([lens-cd](../physics/lens-cd.md)).

| Surface | Takes | Returns | Its claims are |
|---|---|---|---|
| (a) Copper doctor | any `.kicad_pcb` (human, router or ours); schematic and intent optional | scorecard, findings, passports, priced repair menu; each approved fix applied as one undo step | E0 topology, E1 counterfactuals, E2 floors; budgets E3–E5 until calibrated |
| (b) Joint optimizer | schematic, fixed parts as boundary conditions, confirmed brief | 2–4 DRC-clean alternatives with scorecards and shadow prices | refined on exact quotes; legality judged by `kicad-cli` |
| (c) LLM physicist | netlist, datasheets, simulations, ledgers | brief (outputs, budgets, world model, questions), hypotheses, menu choices, explanations | E5 until code or a human checks them |
| (d) Harness | manifests, runs | cp1/cpk, completion, errors; a separate physics scorecard; mutation and validation results | `kicad-cli` on re-opened boards |

**The doctor ships first,** for three reasons.
- **Value without trust.** It helps on boards people already have, and practitioners ask for a reviewer before a router ([trust-requirements](../workflow/trust-requirements.md)). On a real open board its prototype found what DRC cannot: an exposed pad without vias, a capacitor island carrying 86% of the switching current, and the best of 511 via sites ([real-board-passports](../physics/real-board-passports.md)) [C].
- **Lowest risk.** It reads and proposes, and its parts are prototyped: core identities hold to 4×10⁻¹¹, passports for a 111k-node board take 48 s, and critics take 1.4–2.7 s per board and found 31/31 planted faults ([physics-core-v2](../physics/physics-core-v2.md), [physics-critics](../physics/physics-critics.md)) [C].
- **It teaches the optimizer.** The optimizer's objective is the doctor's critics, and its inner loop is the doctor's quote → apply. The floor census and router audit show where geometry search can pay ([validation-program](../physics/validation-program.md), [suite results](../physics/suite-physics-results.md)).

The brief builder follows, then the optimizer as a refiner, then design from schematic.

## 2. Components and boundaries

### Packages

| Package | Responsibility |
|---|---|
| `kae.units` | quantities, dimension checks, `Belief`, `Exactness` |
| `kae.board` | `BoardSession` (file, live IPC 10, headless 11); immutable snapshots with `board_rev`; CST splice; `kicad-cli` and DSN/SES helpers |
| `kae.store` | revisions, decision DAG, content-addressed cache, run manifests |
| `kae.intent` | `pcb-intent` 0.4 schema and validator; rule packs; compiler to `.kicad_dru`, classes, rule areas, optimizer terms |
| `kae.circuit` | netlist import, MNA adjoints, ngspice and Xyce drivers, net passports, budget allocation |
| `kae.physics` | pieces, world conductors, kernels K1–K8, the `PhysicsCore` facade ([API](../physics/physics-core-v2-api.md)) |
| `kae.critics` | board physics model views, critic registry, scorecard, mutation operators |
| `kae.engines` | Freerouting, KiCad PNS (PCBWorld-Engine), KRT, CP-SAT, openEMS, Palace, FasterCap |
| `kae.optimize` | joint state (P, T, C), seeders, legalizer, realizers, copper synthesis, search loops |
| `kae.agent` | deterministic orchestrator, LLM contracts, brief builder, VOI questions, explanation renderer |
| `kae.mcp`, `plugin/` | MCP server; KiCad IPC plugin with a local web view |
| `kae.eval` | physics report over kaebench runs, mutation benchmark, validation registry |

Imports run only down the table, and an import linter enforces this in CI. `kaebench` imports nothing from `kae`: it judges methods, so it stays stdlib-only and outside every write scope (CLAUDE.md). One practitioner's agent rewrote its own scoreboard ([trust-requirements](../workflow/trust-requirements.md)). `kae.eval` reads kaebench attempt directories as files and writes only to `attempt-N/physics/`.

### Data contracts

| Artifact | Writer → readers | Content |
|---|---|---|
| `intent.yaml` (`pcb-intent/0.4`) | detectors, LLM, human (provenance per entity) → compiler, physics, critics, optimizer | what is required: roles, cells, ports with named returns, loop-named budgets with criticality, world conductors and open asks, hypotheses, waivers ([physics-ir](../physics/physics-ir.md)) |
| `ledger.json` + passport blobs | code only → critics, agent, UI | what is observed per `board_rev` and epoch: Beliefs, spend, floors with τ, quotes, events, modes, VOI. Passports are sparse in JSON (binding budgets, jobs above threshold), dense per band in `.npz` |
| `Belief` | every kernel → everyone | value, unit, exactness E0–E5, `relative_to`, interval, spread, validity, lineage; the only number type that crosses a package boundary |
| Finding | critics → agent, plugin, reports | `drc.v1` shape plus `measured`, `limit`, `budget_id`, critic id and version, rung, trust, fix quote ids; severity from budget utilization |
| `Quote`, `Candidate` | physics, optimizer → agent, human | edit, per-budget deltas, radius r, events, cost; a candidate applies only at its `base_rev` |
| `dag.jsonl` | orchestrator → replay, bisect | nodes (input, detect, adjudicate, confirm, budget, world fact, hypothesis, choice, engine run, apply, waiver) with actor, inputs hash, seeds, tool versions |

Required and observed live in different files, so critics diff them and no computed number is ever written into intent.

### Process model

- **Library first.** Batch review, bench adapters and tests call everything in-process.
- **One session server per board** (`kae serve`) serves live and optimizer use. It owns the only KiCad IPC connection, because KiCad answers on one UI thread and clients "should not open multiple connections" ([ipc-api-10-vs-11](../kicad/ipc-api-10-vs-11.md)). It also owns the store, the orchestrator and one writer lock. Requests carry `board_rev`; stale writes are refused.
- **Its physics service keeps factorizations warm.** Workers own the factorizations for some (operator, band, epoch) keys and answer solves, quotes and passports as actors. A factorization costs about 10–25 s at 1M cells [I]; a quote inside a cached hot window costs 0.2 ms [C]. Optimizer workers receive hot-window Green blocks and quote locally ([physics-core-v2](../physics/physics-core-v2.md)).
- **Helpers run as subprocesses** for crash isolation, not licences ([reuse-matrix](../licensing/reuse-matrix.md)): SWIG DSN/SES, Freerouting (`-mt 1`, hash-pinned), PNS, ngspice, openEMS.
- **KiCad 10 uses four channels:**
  - IPC CRUD in commit groups (≤ 32 creates, one undo entry);
  - direct `.kicad_dru` writes;
  - `kicad-cli pcb drc --refill-zones` on a saved copy, the only legal referee;
  - SWIG DSN/SES.
  
  Live snapshots come from `SaveDocumentToString`. File mode writes by byte-preserving splice, never `SaveBoard`, and is refused once a board has been seen live ([file-format-and-version-hazards](../kicad/file-format-and-version-hazards.md)).
- **KiCad 11** adds a `HeadlessSession` on `kicad-cli api-server`, with DSN/SES and structured `CustomRule` over IPC. DRC stays with `kicad-cli`, which 11 still cannot run over IPC. Baselines are re-run per KiCad version.
- **Concurrency.** One IPC queue with request IDs; refills polled through `AS_BUSY`; single-threaded worker processes. Parallel results merge in candidate-id order and search budgets count moves, so runs replay exactly.
- **Caching.** Pure kernels are content-addressed by geometry window, stackup, band and kernel version; engine runs by decision-prefix hash, seeds and tool versions ([S2](../../ideas/original/system-loop.md)). Snapshot diffs invalidate within an interaction cutoff; topological events bump the epoch and refactor in the background.
- **Persistence and provenance.** A sidecar `<board>.kae/` holds `intent.yaml`, `stackup.yaml` and `dag.jsonl`, committed with the project, plus git-ignored revisions, ledgers and caches. Every artifact records schema, code and tool versions, inputs hash and seeds, so any revision regenerates from its DAG prefix. LLM outputs live in DAG nodes, so replay never calls the LLM.

## 3. The main loops

**(i) Review an existing board.**
1. `board` snapshots the board, refilling zones on a private copy.
2. `intent` drafts roles and cells with deterministic detectors; the LLM adjudicates ambiguous ones; a human confirms the few items ranked highest by expected loss ([U3](../../ideas/original/workflow-ux.md)). Without a brief, budgets are labelled rule-pack priors or "unbudgeted".
3. `physics` factors once per band and computes passports lazily, binding budgets first.
4. `critics` emit findings and the scorecard.
5. For each binding finding, `physics` quotes candidate edits exactly (via sites, decap vias, plane order, bridges, tap moves, pour reshaping). `kicad-cli` checks each on a scratch copy before it is offered.
6. `agent` explains; the human approves; `board` applies the change at `expected_rev` as one undo step. The doctor re-runs and compares observed with quoted changes; a gap beyond the quote's stated error becomes a finding.

**(ii) Design from schematic and constraints.** The orchestrator is a deterministic state machine that calls the LLM at fixed points. Bounded menus beat free generation (92.5% vs 6.6% in DRC-Aid, [agent-loop-patterns](../llm/agent-loop-patterns.md)), and a deterministic loop can be replayed and bisected.

| Step | Who works | Result (exactness) |
|---|---|---|
| 1 Comprehend | detectors, layout cards, staged datasheet extraction; the LLM adjudicates | roles, cells, ports (E5 until confirmed) |
| 2 Simulate the schematic | `circuit`: operating point, cell transients, AC adjoints | net passports, susceptibilities (E1 relative to the models) |
| 3 Brief | `circuit`, floors, K8; the LLM proposes outputs, budgets, hypotheses, questions | budgets with τ; τ < 1 goes to an ECO menu. **Human gate 1** |
| 4 Compile | `intent` | `.kicad_dru` (linted by `kicad-cli`), classes, rule areas, optimizer terms |
| 5 Diverse starts | `optimize`: sides, floorplan, micro-solvers for τ < 2 (hot loop, decaps, RF chain), analytical placement, CP-SAT legalization | N legal starts |
| 6 Joint refinement | `optimize` on physics quotes; successive halving across starts | refined starts, legal throughout |
| 7 Realize | PNS and Freerouting with critical copper locked; morphology; zone fill | candidate boards |
| 8 Referee | `kicad-cli` DRC on re-opened files; physics re-solve on realized copper | legal verdict; F2 Beliefs |
| 9 Judge | critics; F3 slices where margin < z·σ | one scorecard per candidate |
| 10 Explain and choose | the LLM explains binding budgets and shadow prices and proposes priced operators | 2–4 alternatives. **Human gate 2**, then apply and sign-off |

Three results shape steps 5–8 [C]:
- **Joint search refines; it does not start.** On toy boards it improved its own start on 10/10 boards (−18%) but tied an equal-CPU restart portfolio 5/10 ([joint-place-route-experiment](../physics/joint-place-route-experiment.md)).
- **Legality stays inside the loop.** End-of-run legalization took one board's routed objective from 602.5 to 1163.5.
- **The optimizer's own route state is never the score.** Freerouting's log claimed "0 unrouted" on a board where KiCad found 2 unconnected items ([harness](../verification/harness.md)).

**(iii) Interactive editing.** The plugin bridges KiCad's selection to a side panel, since IPC cannot create persistent markers ([U1](../../ideas/original/workflow-ux.md)).
- **Updates.** KiCad sends no change notifications, so the session server polls item diffs, re-solves dirty regions by rank-k updates within the epoch, and refactors at topological events in the background.
- **Queries.** Selecting a piece answers `why_here`; a ghost drag answers `what_if` before the commit. "Why here, not there?" becomes a constraint and a re-solve, which answered 89.8% of user questions in a planning study ([explanations-and-alternatives](../ux/explanations-and-alternatives.md)).
- **Fills.** Until KiCad refills a zone, live physics uses its own provisional fill, tagged E3.

**Human approval points:** the brief (outputs, top budgets, world facts, contested choices); every ECO when τ < 1; every apply to the user's board; waivers; sign-off, with a residual-risk list of what was assumed or not checked.

## 4. The LLM's role and interface

| The LLM reads | It writes (schema-validated; refused otherwise) |
|---|---|
| detector outputs with evidence; layout cards; datasheet excerpts with page references | adjudications citing evidence ids |
| net passports and requirements | outputs and budget proposals; code checks dimensions and sums, a human approves |
| binding budgets with τ, margin, P(pass), class; job verbs and conflicts | mechanism hypotheses with registered predictions and falsifiers |
| priced menus (quotes with r, events, cost) | menu choices, allocations, symmetry declarations |
| VOI-ranked unknowns | question wording; world facts from answers, with provenance |
| scorecards, DRC summaries, infeasibility certificates | explanations as templates citing Belief ids |

It never writes coordinates, geometry, regimes, spend or classes. A renderer inserts each cited Belief's number, so the LLM cannot misquote one; OptiChat keeps numbers in solver calls for the same reason ([explanations-and-alternatives](../ux/explanations-and-alternatives.md)). Relations beat coordinates 90.9% to 23.2% ([interfaces-relations-vs-coordinates](../llm/interfaces-relations-vs-coordinates.md)); physics entities are relations in physical units.

**Tool surface.** About 22 MCP tools:
- the read, propose and apply groups of [mcp-tool-surface-spec](../kicad/mcp-tool-surface-spec.md);
- the physics facade: `why_here`, `what_if`, `where_add`, `explain`, `menu`, `binding`, `unknowns`, `regime`;
- `brief_get`, `brief_answer` and a restricted `kicad_cli`.

Twelve stay visible; the rest load as a toolset where the client honours `list_changed` ([mcp-server-lessons](../kicad/mcp-server-lessons.md)). Every response carries `{source, board_rev, kicad_version, outcome}`.

**Token budget per board** [I]:

| Stage | Tokens |
|---|---|
| Comprehension | 20–60k |
| Brief and questions | 10–30k |
| 3–5 refinement rounds of hypotheses and choices | 15–50k |
| Explanation | 10–30k |
| **Design total** | **60–170k**, capped at 250k, stop on stall |
| Review | 15–50k |

Per-step routing agents spent 0.4–1.9M ([pcbworld](../routing/pcbworld.md)). Input dominates spend (81% in "Who Plans"), so views are compact and the static board summary is prompt-cached. A mid-tier model is the default; a flagship planner is called only after a verified failure.

**Off-board unknowns.** Enclosure, cables, heatsink bonds, chassis and test setup enter as world conductors with E5 Beliefs from product-class priors ([lens-ct](../physics/lens-ct.md)).
- **Pricing.** For each decision they affect (connector edge, heatsink bond, filter population, stitching pitch), K8 ranks four actions by expected value per cost: ask, compute, measure, robustify ([lens-in](../physics/lens-in.md)).
- **When to ask.** Only when asking beats robustifying. A robust action caps VOI: cables on one edge cut total VOI 30× in the worked case, if co-location buys the assumed 35–60 dB [C].
- **How to ask.** Each question names the decision it changes and the default taken if unanswered; at most ten per board, ordered by expected loss.

## 5. Evaluation built in

- **Benchmark.** kaebench is unchanged: cp1, cpk, completion and per-type errors, same KiCad version, manifest and suite. A `joint` task kind (place-task input, route-task scoring, fixed-part integrity) enters as a separate harness commit, with baselines re-run.
- **Physics scorecard,** never inside cp1/cpk: coverage, hard budgets, minimum margin, counts by root cause, deltas against the human board. It compares lexicographically, with no blended number ([physics-critics](../physics/physics-critics.md)).
- **Mutation benchmark and red team.** DRC-equivalent planted faults with oracle deltas and benign twins; someone other than the critic's author writes the operators. A critic becomes an optimizer term only after calibration, mutation and red-team tests ([physics-critics-validation](../physics/physics-critics-validation.md)).
- **Regression references.** The `rt_*` scripts become golden tests and stay independent implementations that never import `kae`. Core identities, DC bounds and registered predictions are versioned golden values ([verification-and-limits](../physics/verification-and-limits.md)).
- **Pre-registered validation boards.** VAL-1 (rules arm vs physics arm) and the coupons. Predictions are hashed in `validation/registry/` before fabrication and scored on coverage, sharpness, differential sign and skill ([validation-program](../physics/validation-program.md)).
- **Release judgement.** `kae eval release` writes one report: tests; bench against the last release and Freerouting; scorecard against the human boards; critic validation status; registry scores; tokens, CPU and questions per board. A release is blocked by any of:
  - a failed golden test;
  - fewer cpk clean boards on any split;
  - more error-level DRC violations in aggregate;
  - an optimizer-term critic below its mutation gate;
  - registry coverage below 80% for a model class used for compliance.

## 6. Technology and licensing

| Concern | Choice | Reason |
|---|---|---|
| Core | Python 3.11+, numpy, scipy (SuperLU; CHOLMOD for symmetric operators), Shapely 2, pyclipper | the prototypes are numpy/scipy; 2-D factor and solve take ms to s ([solver-ladder](../physics/solver-ladder.md)) |
| Hot loops | Rust via PyO3 from the joint-search milestone: grid router, SA moves, kinetic topology, morphology | a routed move costs ~25× an HPWL move in Python; Rust gave ~10× in KRT ([performance-and-multifidelity](../solvers/performance-and-multifidelity.md)) |
| Differentiable kernels, GPU | JAX for placement kernels and batched F1/surrogates; GPU only for batches and Palace or openEMS finalists | 2-D solves gain little on GPU |
| Discrete solves | OR-Tools CP-SAT in windows | monolithic models fail beyond ~100 parts ([cp-sat-milp-smt](../solvers/cp-sat-milp-smt.md)) |
| Circuits | ngspice batch; Xyce from source for harmonic balance | `.noise` is the adjoint ([schematic-to-physics](../physics/schematic-to-physics.md)) |
| Routers | Freerouting 2.5.0; KiCad PNS via PCBWorld-Engine; KRT as a fast probe | bulk baseline; realizer and repair ([recommended-stack](../solvers/recommended-stack.md)) |
| LLM, MCP | official MCP Python SDK; native function calling | coding-agent harnesses cost 2.2–5.4× the tokens |
| Storage | YAML, JSON, JSONL, `.npz`, an SQLite index; no server | diffable and reproducible; boards are small |

Code is GPL-3.0-or-later; schemas and rule packs CC0; data CDLA-Permissive-2.0; docs CC-BY-4.0. A bundle that ships Freerouting is GPL-3.0 as a whole. FastHenry decks serve internal calibration only, and FastHenry is never shipped. Ki-PIDA and Konnect (AGPL) are reference only ([open-solvers](../physics/open-solvers.md), [reuse-matrix](../licensing/reuse-matrix.md)). CI runs REUSE lint and dependency licence gates.

## 7. Repository layout

```
kae/              pyproject.toml; src/kae/{units,board,store,intent,circuit,physics,critics,
                  engines,optimize,agent,mcp,eval}; tests/{unit,golden,kicad,mutation}
crates/kae-fast/  Rust extension (from the joint-search milestone)
plugin/           KiCad IPC plugin for the PCM
schemas/          JSON Schemas: intent, ledger, findings, passports, DAG (CC0)
rulepacks/        rule records with regime predicates (CC0)
validation/       registered predictions, coupon and VAL board definitions, measurements
bench/            kaebench, unchanged and independent
tools/research/   research scripts, frozen as the evidence behind [C] tags
```

Research scripts are rewritten into packages with tests, not moved, so doc citations stay valid. Promotion order:
1. `pc2_core_skeleton` → `units`, physics types, K1 and K4, with its checks as tests.
2. `rb_board_passports` → the snapshot reader, the DC sheet and the HF window model.
3. `pc_refplane` → the board physics model, the first critics and the mutation self-test.
4. `vo_ir_check` → the intent validator; `vp_floors` → K5; `cd_conductor_passport` → passports and jobs.
5. `dr_noise_adjoint`, `dr_switch_cell_budget` → `circuit`.
6. The three PEEC and four sheet scripts, merged into K3 and K2.
7. Legalization and LNS from `hier_place`, plus `pathfinder_bench` and `jpr_joint_vs_sequential` → `optimize` baselines.

## Conflicts and open questions

- **Joint state vs staged spine.** [hybrid-architecture-options](hybrid-architecture-options.md) builds a staged pipeline first. This design keeps its substrate but orders work by τ inside joint refinement, and falls back to a portfolio plus refiner if joint search fails its kill test.
- **Live physics on KiCad 10** relies on polled diffs and asynchronous whole-board refills; the provisional fill may disagree with KiCad's.
- **Piece ids under large edits** need an overlap matcher, or passport diffs misattribute.
- **Token figures** stay estimates until the per-role ledger measures them.

## Sources

- Research notes: [kicad_mcp_codebases.md § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md), [llm_for_eda.md § 1, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md), [verification_kicad_and_tools.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md).
- Harness: [bench/README](../../../bench/README.md), [CLAUDE.md](../../../CLAUDE.md). Scripts: [`tools/research/physics/`](../../../tools/research/physics/).

See also: [system-design-build-plan](system-design-build-plan.md) · [physics-engine-design](physics-engine-design.md) · [physics-core-v2](../physics/physics-core-v2.md) · [joint-place-route](../physics/joint-place-route.md) · [design-reasoning-architecture](../physics/design-reasoning-architecture.md) · [constraint-ir](constraint-ir.md)
