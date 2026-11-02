# Build plan: from copper doctor to design from schematic

Scope: twelve-month plan for the [system-design](system-design.md) architecture: seven milestones (M0–M6) with acceptance tests, kill criteria, dependencies, staffing, weeks 1–6, risks. Thresholds are proposals [I] unless a doc is cited. Not here: the architecture -> [system-design](system-design.md); the first-month plan that replaced M1–M6 for month 1 -> [month-plan](month-plan.md).
Keys: M0–M6, milestones, acceptance tests, kill criterion, critic gate, sign test, VAL-1, LM coupon, N7, N8, `kae review`, `kae refine`, mutation benchmark v1, router audit, critical path, KiCad 11, staffing

## Plan summary

- 7 milestones, 12 months, ≈ 4.5 people. Order: substrate (M0) → copper doctor (M1, M2) → brief builder (M2) → refiner (M3) → joint search (M4) → design from schematic (M6); validation readout (M5) runs beside them. Each milestone reuses the previous one's evaluators.
- Weeks 1–6 deliver a batch copper doctor on the 112-board suite (exact passports, ten critics, priced DRC-checked fixes, ≥ 400 mutants, router audit); none of it touches cp1/cpk.
- Three pre-registered decisions steer the year: critics as optimizer terms (M1, week 6); physics beats competent rules on VAL-1 (M5, ≈ week 22); joint search beats an equal-CPU portfolio on 20 real boards (M4, ≈ week 34).

## Assumptions

| Item | Assumption |
|---|---|
| Team | P physics numerics; K KiCad and infrastructure; O optimization and routing; L evaluation and LLM; H hardware validation (half time) |
| Pins | KiCad 10.0.7 container, Freerouting 2.5.0, kipy 0.8.x, OR-Tools 9.15; new pins only with re-run baselines (CLAUDE.md) |
| Compute | one 32-core bench host; long runs detached in `tmux`; one GPU from M4 |
| Data | the 112-board qualified suite, PCBWorld D3, `netlist_candidates.jsonl` for schematics; boards never committed |
| Hardware money | ≈ $1.5–2.5k of instruments and < $1k of VAL-1 fabrication and assembly ([validation-program](../physics/validation-program.md)); one contracted engineer, blind to the predictions, lays out the rules arm |
| Reference results | the research run of passports and critics on the suite ([suite-physics-results](../physics/suite-physics-results.md)); the product must reproduce it or explain each difference |

## Milestones

| M | Weeks | Scope and deliverables | Acceptance tests | Kill or redirect | Needs |
|---|---|---|---|---|---|
| **M0 Substrate** | 1–2 | `kae/` layout, CI (unit, KiCad container, import linter, REUSE, licence gate); schemas v0; snapshot reader; skeleton promoted to `units`, K1, K4 | identities on 1,000 random edits within 10⁻¹⁰ of refactoring on the skeleton and c·ε·κ on real boards ([physics-engine-design](physics-engine-design.md)); DC bounds never fail; λ = 1 exactly at disconnects ([physics-core-v2](../physics/physics-core-v2.md) §9); pad centres match `kicad-cli` drill and Gerber flash positions on 112/112 boards ([transform-math-pitfalls](../kicad/transform-math-pitfalls.md)); validator catches the 12 seeded errors of `vo_ir_check` plus 12 new 0.4 ones and passes the 46 worked entities | identity failure stops all physics work until fixed | — |
| **M1 Doctor alpha** (batch) | 3–6 | DC sheet (CHOLMOD), passports, floors, Schur and HF windows; 6 catalog critics + 4 exact ones from [real-board-passports](../physics/real-board-passports.md); fix menus; `kae review`; `kae eval physics`; mutation benchmark v1 (≥ 8 operators on ≥ 50 boards); router audit | removal quotes match brute force to ≤ 10⁻⁹ on 3 real boards; scorecard on ≥ 106/112 boards, median ≤ 2 and p90 ≤ 10 CPU-min each; per critic: recall at site ≥ 90%, false alarms on twins ≤ 5%, Spearman with oracle ≥ 0.7; priced DRC-legal fix for ≥ 80% of binding findings on 4-layer boards with a switching cell; engineer review of 20 `why_here` answers and 20 findings: ≥ 16 correct, ≥ 12 useful | critic recall < 70% or false alarms > 10%: report-only ([validation-program](../physics/validation-program.md) §5); engineer precision < 50%: stop adding critics, fix roles and budgets, delay M3 | M0 |
| **M2 Brief and live doctor** | 7–14 | schematic import; ngspice and MNA adjoints; net passports; √(k·s) budgets; floors τ; world model and VOI questions; 0.4 compiler; merged PEEC (K3); session server; KiCad plugin; MCP server; LLM contracts | adjoint = direct AC to ≤ 10⁻⁹ and ngspice `.noise` to 4 digits; buck loop budget of [dr_switch_cell_budget](../../../tools/research/physics/dr_switch_cell_budget.py) within 2%; on 10 labelled schematics roles and cells recall and precision ≥ 90%, ≤ 10 questions, ≤ 15% of confirmed items corrected, ≤ 90k tokens; K3 within 3.5% of `ls_thin_sheet` and 1.3% of PEECN; generated `.kicad_dru` pass `kicad-cli` lint 100%; 50 scripted applies = 50 single undo entries, read back; `what_if` ≤ 50 ms p95 in a cached window, refresh ≤ 2 s p95 within an epoch (Schur windows, compiled factor); MCP tool-selection evals ≥ 90% expected tools, no forbidden writes | > 20 questions per board or > 30% corrections: ship review with manual intent; brief work moves to detectors | M1 |
| **M3 Refiner** | 13–22 | harness `joint` task kind (separate commit, baselines re-run); copper moves (vias, stitching, pours, reliefs, decap vias); N7 hot-loop and N8 decap micro-solvers with local re-route; legality inside the loop; `kae-refine` adapter | on ≥ 20 pre-registered boards with a switching cell or ≥ 10 decaps: median binding-budget spend −20% on Freerouting outputs, −10% on human boards; no board loses clean status; error-level DRC never rises; ≥ 95% of accepted moves agree with an F2 re-solve within the quote's stated error; N7 beats a generic placer on ≥ 20/30 converters; N8 beats smallest-closest on ≥ 14/20 boards | N7 or N8 worse than its baseline, or its estimate off extraction: kill that solver (report experiments 3–4); < 10% median gain on human boards: refine router outputs only | M1 gate, M2 budgets |
| **M4 Joint search** | 21–34 | Rust crate: grid router (PathFinder, LPA* repair), SA and LNS moves; delayed acceptance; CP-SAT channel-width legalizer; successive halving over diverse starts; physics quotes as terms | pre-registered on 20 boards (splits A and B, D3): joint beats the equal-CPU sequential portfolio on ≥ 15/20 (one-sided sign test p ≈ 0.02), no fewer clean boards, no worse physics margin; ≥ 5,000 routed moves per CPU-second (10× the Python prototype) | < 15/20: portfolio plus refiner is the optimizer; topological-state work stops ([verification-and-limits](../physics/verification-and-limits.md) §4) | M3 |
| **M5 Validation readout** | 4–30 | LM coupon ordered week 4; VAL-1 both arms laid out weeks 5–10, the physics arm by a person using the doctor; predictions recomputed from the frozen copper ([val_board](../../../tools/research/physics/val_board.py) + M1 evaluators) and hashed week 10; blinded measurement weeks 15–19; readout by week 22; assimilation into a posterior registry by week 30 | registered rules: ≥ 80% of values inside their 90% intervals; differential sign right ≥ 90% where the predicted difference exceeds 2× repeatability; magnitude within 2×; interval score better than the rule baseline | kill table of [validation-program](../physics/validation-program.md): physics arm beats rules arm by less than scatter on every binding budget → product becomes rules plus critics, physics kept for diagnosis | M1, M2 |
| **M6 Design from schematic** | 30–52 | loop (ii) end to end on 2–4-layer boards ≤ 150 parts; fixed connectors, holes, antenna, heatsink; 2–4 alternatives; KiCad 11 `HeadlessSession` if released | on 10 held-out boards (schematic, outline, fixed parts kept; human layout hidden): ≥ 7/10 DRC-clean by `kicad-cli`; hard physics budgets pass ≥ 7/10; minimum margin ≥ the human board's on ≥ 5/10; ≤ 2 h on 16 cores; ≤ 200k tokens and ≤ 10 questions per board; blind engineer review rates ours better or equal on ≥ 5/10 | < 4/10 clean: ship the doctor and the refiner of human placements; revisit after KiCad 11 | M4 or its fallback, M5 |

Thresholds from evidence: the mutation gates sit above the validation program's kill line (recall 70%, false alarms 10%). The M4 test is the falsification test of [verification-and-limits](../physics/verification-and-limits.md); on toy boards joint search tied that portfolio 5/10 ([joint-place-route-experiment](../physics/joint-place-route-experiment.md)) [C].

## Releases and staffing

A release is tagged at every milestone exit with the `kae eval release` report ([system-design](system-design.md#evaluation-built-in)) attached.

| Week | Users get | Surface |
|---|---|---|
| 6 | `kae review` CLI and report; physics scorecards for kaebench runs | doctor alpha, batch |
| 14 | KiCad plugin side panel, MCP server, brief builder with questions | doctor beta, live; LLM physicist |
| 22 | `kae refine` as CLI and kaebench `--command` adapter | refiner |
| 34 | joint search, or the portfolio fallback | optimizer |
| 52 | design from schematic, alpha | full loop |

Staffing by milestone:
- P: core and passports (M0–M1); circuit adjoints and K3 (M2); physics terms and quotes for the optimizer (M3–M4); assimilation (M5).
- K: substrate, snapshot reader and splice (M0–M1); session server, plugin, MCP (M2); KiCad 11 backend (M4–M6).
- O: legalizer and edit generators (M1); refiner, N7, N8 (M3); Rust crate and joint search (M4); design loop (M6).
- L: schemas, evaluation and mutation benchmark (M0–M1); LLM contracts and brief (M2); release reports throughout.
- H: coupons and VAL-1 (M1–M5).

## Weeks 1–6 in detail

| Week | P physics | K KiCad and infra | O edits and legality | L evaluation and LLM | H validation | Exit check |
|---|---|---|---|---|---|---|
| 1 | promote [pc2_core_skeleton](../../../tools/research/physics/pc2_core_skeleton.py): Belief, types, operator, K4 removal and addition quotes, K1 events; skeleton checks as tests | `kae/` layout, CI, import linter, REUSE and licence gates; snapshot reader from the `KBoard` parser of [rb_board_passports](../../../tools/research/physics/rb_board_passports.py) | port legalization and LNS from `hier_place` as `optimize.legalize`, with tests | schemas v0 (Belief, finding, ledger, intent 0.4 subset); port [vo_ir_check](../../../tools/research/physics/vo_ir_check.py) | coupon geometries in KiCad ([validation-coupons](../physics/validation-coupons.md)) | identities ≤ 10⁻¹⁰; CI green |
| 2 | DC sheet builder from snapshots (per-net rasters, via barrels, terminals); brute-force checks on BLDCM-Power | transform oracle on 112 boards; refill contract (private copy, `--refill-zones --save-board`); port POA's byte-preserving splice | edit generators: via sites, decap-via moves, bridges, slot closures, as `Edit` objects | `kae eval physics` skeleton over kaebench runs; scorecard JSON; first suite pass with "unbudgeted" rows | coupon predictions registered with P | **M0 exit** |
| 3 | DC passports, exact and sketched leverage, Beckmann and convex floors from [vp_floors](../../../tools/research/physics/vp_floors.py) | board physics model views from [pc_refplane](../../../tools/research/physics/pc_refplane.py): reference map, plane polygons, via spans | morphology legalizer (K7) for copper edits; scratch-copy DRC service | role detectors (names, values, footprints, pin semantics); ten rule-pack priors from the [derivation-audit-table](../physics/derivation-audit-table.md) | VAL-1 schematic started | passports exact on 3 boards |
| 4 | HF window model for switching cells; plane-swap and via-site quotes | critics RET-COV, RET-VIA, PLANE-PERF, PWR-TRACE, DECAP-L, HOTLOOP-L | fix menus: quote, legalize, DRC-check, rank by value per cost | eight mutation operators and benign twins, written apart from the critics' authors; oracle labels | order the LM coupon panel | critics run on 112 boards |
| 5 | four exact critics: exposed pad without vias, decoupling island, single-via connector, foreign plane between a cell and its ground | findings as `drc.v1` markers; `kae review` report with renders from `kicad-cli` | reapply accepted fixes through the splice; compare observed and quoted changes | router audit (Freerouting vs reference); explanation v0 with Belief-cited templates; token ledger | VAL-1 layout brief for both arms | mutation results per critic |
| 6 | performance pass on split C: CHOLMOD backend, Schur windows, lazy passports, memory cap | packaging; `kae review` on 20 random suite boards without a crash | spec of the `joint` task kind and fixed-part integrity for M3 | engineer review (20 `why_here` answers, 20 findings, two boards); M1 readout; update [suite-physics-results](../physics/suite-physics-results.md) | physics-arm layout starts with the doctor | **M1 exit and critic gate** |

Week 6 deliverables: `kae review` CLI and report; `kae eval physics` scorecards for ≥ 106 suite boards, reference and Freerouting runs; mutation benchmark v1 with per-critic recall, false alarms and Spearman; router audit and engineer review; M1 readout with the critic gate decision (only critics passing calibration, mutation and red-team tests become optimizer terms, [physics-critics-validation](../physics/physics-critics-validation.md)).

## Dependencies and critical path

```
M0 ─► M1 ─┬─► M2 ─┬─► M3 ─► M4 ─┐
          │       └─► M5 (VAL-1 physics arm, predictions) ─┤
          └─ critic gate (week 6) ─► M3                     ├─► M6
                       KiCad 11 release ─► HeadlessSession ─┘
```

- **Critical path:** snapshot reader → K1, K2, K4 → critics and mutation gate → refiner → joint search → design from schematic. A slip in the snapshot reader or the critic gate moves everything.
- **Off the critical path** (parallel, join at M2 and M5): circuit simulation, plugin and MCP server, hardware track.
- **External:** KiCad 11 (expected ≈ Q1 2027 [I]) removes SWIG and adds the headless server, DSN/SES over IPC and `kicad-cli pcb export specctra`. A two-week spike within a month of release moves the SWIG helper to them, adds the headless session and `CustomRule` emission, and re-runs baselines ([kipy-and-swig-bindings](../kicad/kipy-and-swig-bindings.md)).

## How milestones are judged

- **Pre-registration:** board lists, thresholds and statistics committed (to `bench/suites/` or `validation/registry/`) before the run that tests them.
- **Benchmark discipline:** CLAUDE.md rules (same KiCad version, manifest, suite; cp1, cpk, completion, error counts and per-type `drc.json` errors together; new run name after a method change; scoring changes only in separate commits with re-run baselines). Physics apart from cp1/cpk and golden-test gating: [system-design](system-design.md#evaluation-built-in).
- **Process metrics:** tokens, CPU, questions per board and prediction calibration logged per run, so the [token estimates](system-design.md#llm-role-and-interface) become measurements.

## Risks and mitigations

| Risk | Early signal | Mitigation |
|---|---|---|
| Physics numbers wrong: none measured yet | coupon or VAL-1 coverage < 80%; models disagree | separate rankings from compliance; exactness classes on every number; coupons first, VAL-1 by week 22; F3 slices where the optimizer selects; regime-gated rules ([verification-and-limits](../physics/verification-and-limits.md)) |
| Critics gamed or circular | red team finds cheap wins; high recall but low engineer precision | mutants by a second author, seeded from real escapes; continuous metrics; frozen, human-confirmed roles; optimizer terms only after three tests |
| Joint search only ties | M4 sign test < 15/20 | refiner-first design; portfolio fallback; successive halving keeps both |
| KiCad API churn | KiCad 11 release; SWIG removal; PCBWorld-Engine lagging a KiCad release | `BoardSession` backends; file mode as default; pinned versions; baselines per version; Freerouting as fallback realizer |
| Missing inputs: encrypted models, stackup tolerances, world facts | stand-in validation fails; many E5 Beliefs | stand-ins tested against datasheet curves; datasheet envelopes; VOI questions; robust defaults |
| Compute on large boards | p90 > 10 CPU-min or > 4 GB per board | compiled factorization, Schur windows, lazy passports, binding budgets only |
| LLM comprehension errors | corrections > 15%; token overruns | detectors first; schema validation; human gates; mid-tier default; token ledger |
| Live and saved state diverge, data lost | read-back mismatches | one writer; read back after every apply; no file writes once live; byte-preserving splice |
| Scope exceeds the team | two consecutive slipped exits | kill criteria applied as written; scope cuts below |
| Patents | — | deterministic search over placement-level decisions; no pretrained routability fitness; prior-art file for LLM constraint loops ([patents-watchlist](../landscape/patents-watchlist.md)) |
| Licence drift | dependency gate fails | REUSE and licence gates in CI; FastHenry internal only; AGPL reference only |

## Not built in the first year

- BGA escape, DDR, boards above 6 layers in M6.
- RF matching synthesis beyond the antenna → match → IC chain order.
- Full-wave solvers inside the optimizer loop (finalists and calibration only).
- RL, learned surrogates before the M5 calibration, LLM-evolved heuristics.
- The domain market (Option B) and a multi-layer topological router; a two-layer topological state is a stretch goal only if M4 passes.
- A hosted service: everything runs locally.

## Conflicts and open questions

- **Staffing.** The plan assumes 4.5 people. With three, M2's plugin and MCP work moves after M3, and M6 becomes the refiner of human placements.
- **Suite results may move M1's thresholds:** if the research run shows few binding findings on human boards, M3's −10% target on human boards drops and router outputs become the main target.
- **VAL-1 physics arm** is laid out by a person using the tools, not by the optimizer: it tests the physics and the doctor, not the search.

## Sources

- [validation-program](../physics/validation-program.md), [physics-core-v2](../physics/physics-core-v2.md) §9, [physics-critics](../physics/physics-critics.md), [joint-place-route](../physics/joint-place-route.md), [report § 7](../../../reports/LLM%20driven%20PCB%20placement%20and%20routing.md).
- Harness: [bench/README](../../../bench/README.md), [CLAUDE.md](../../../CLAUDE.md). Related: [hybrid-architecture-options](hybrid-architecture-options.md), [benchmark-plan](../verification/benchmark-plan.md).
