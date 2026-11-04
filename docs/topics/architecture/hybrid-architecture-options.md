# Hybrid architecture options for LLM-driven placement and routing

Scope: four end-to-end hybrid architectures (A staged intent-compiler spine, B market of priority domain agents, C topology-first co-design, D search over LLM decisions), their shared substrate, comparison and phased recommendation. All untested [I]. Idea ids (I1, N7, R2, …) refer to the [original-ideas catalog](../../ideas/original/README.md). Not here: the chosen architecture -> [system-design](system-design.md).
Keys: Option A–D, staged spine, intent compiler, domain market, priority domains, specialist submodules, reservations, topology-first, homotopy, decision search, ε-lexicographic, A-core, B-lite

## Common substrate (all options)

In every option the LLM never emits copper or coordinates ([llm-routing-evidence](../routing/llm-routing-evidence.md)).

| Layer | Content | Evidence / ideas |
|---|---|---|
| Board I/O | KiCad 10 four-channel backend: IPC commits, `.kicad_dru` writes, `kicad-cli` DRC referee, SWIG DSN/SES helper; `BoardSession` abstraction for KiCad 11 headless | [ipc-api-10-vs-11](../kicad/ipc-api-10-vs-11.md) |
| Intent | `pcb-intent` IR + budget ledger (I1) with dimensioned values (I2), criticality field (I5), why-graph (I3), stamps in the board file (I7) | [constraint-ir](constraint-ir.md), [intent-and-why](../../ideas/original/intent-and-why.md) |
| Knowledge | rule packs with precedence and contested selectors; layout cards with provenance; recipes as data | [rule-pack-format](../rules/rule-pack-format.md), [part-layout-card](../llm/part-layout-card.md) |
| Verification | critic stack A/S/J; mutation-tested layout unit tests (V1); proxy trust radius (V4); licensed judge (V3) | [critic-stack](../verification/critic-stack.md), [verification](../../ideas/original/verification.md) |
| Control | decision DAG with replay (S2); propose → revision-bound apply; one undo per step; predictions before checks (S4) | [mcp-tool-surface-spec](../kicad/mcp-tool-surface-spec.md), [system-loop](../../ideas/original/system-loop.md) |

### Priority domains → specialist submodules

Same submodules in every option; options differ in how their conflicts get resolved.

| Priority domain | Specialist submodule (ideas) | Engine | Tier |
|---|---|---|---|
| Power conversion (hot loops, gate drive) | N7 nH micro-placer; R6 hot-loop and Kelvin macros; R7 plane partitions | CP-SAT/DFS; generators; graph cut | 1 |
| RF | N9 antenna→match→IC chain; R6 RF polygon macros | DP + CP-SAT; generators | 1 |
| High-speed, diff pairs | N9 I/O chains; R3 via sites; R1 homotopy menus; R2 shadow returns; R8 PNS beam | MCF/SAT escape; PNS DP placer + meanders | 2 |
| Adjacency-critical (crystal, FB divider, ESD, Kelvin) | P3 slack templates; N9; R6 | PSDL program + repair | 2 |
| Decoupling / PDN | N8 assignment; PDN screener | min-cost flow; lumped RLC | 2 |
| EMI/EMC | P8 connector-voltage proxy; P4 side cut; R2; Checker F | analytical penalty; router cost | spans tiers |
| Thermal | ΔT budgets (I1); P4 bottom heat-sinking | screener in the placement loop | spans tiers |
| DFM / mechanical | fab packs (floors applied after rule resolution and compiled into Board Setup, not a precedence rank); P10 variants; locked anchors | legalizer constraints | hard |
| Bulk signals | R5 bandit over Freerouting / KRT / PathFinder | — | last |

Evidence: hot loops rank first everywhere ([hot-loops](../rules/power/hot-loops.md)); mounting inductance governs decoupling ([decoupling-pdn](../rules/decoupling-pdn.md)); TVS order is comparative ([emc-placement](../rules/emc-placement.md)); return-path continuity is the shared SI/EMC physics ([si-fundamentals](../rules/si-fundamentals.md)).

## Option A — Intent compiler on a staged engine pipeline

```
 schematic + netlist + datasheets + fab profile + user brief
                          │
 1 Comprehension: detectors (VF2/rules), IBIS, layout cards
   LLM: adjudicates, writes detector code, extracts predicates
                          │
 2 Brief (U3) ── human confirms ──► IR + budgets (I1,I2) + criticality (I5)
                          │ compile (I7)
      ┌───────────────┬───┴──────────┬────────────────┐
  .kicad_dru     placer terms    router presets    unit tests (V1)
                          │
 3 Placement: sides (P4) → floorplan + cut check (P2) → recipe solvers
   (N7, N8, N9, P3) → analytical GP (+ P1 probe forces) → CP-SAT legalize
   → slot assignment (P6) → SA/LNS     gate: probe completion (profile, default 85%)
                          │
 4 Routing: escape + via sites (R3) → macros (R6) → critical nets
   (PNS DP placer, meanders in reserved slack) → bulk (Freerouting/KRT)
   → PNS repair → tuning
                          │
 5 Critics: DRC + V1 + tier-S checkers + licensed judge (V3)
                          │ findings + price tags (I4)
 6 LLM repair of commitments: relax / substitute (N2) / priced ECO (S3)
   → back to 3 or 4; a human approves every apply
```

- **Data flow:** the IR is the only channel from the LLM to the engines; engines return structured findings, prices and conflict lists, never geometry dumps; each stage commits as one undoable step and is read back.
- **LLM:** stage 1 adjudication; stage 2 authoring intents and side affinities; stage 6 repair from bounded menus; narration throughout, generated from derivations and the why-graph. Tokens ≈ 50–200k per board (estimate, not derived or measured) vs 0.4–1.9M for PCBWorld's per-step routing agents on 2-layer boards of ≤ 31 and ≤ 100 pads ([pcbworld](../routing/pcbworld.md)) [I].
- **Priorities:** tier order = stage order + ε-lexicographic compiler (N6). Critical copper becomes reservations (N5), not frozen copper, so upper tiers can be re-realized after ECOs. Lock any critical copper present at a Freerouting hand-off: KiCad 10 SES import deletes unlocked tracks and vias and re-adds locked ones ([specctra-freerouting-integration](../kicad/specctra-freerouting-integration.md)).
- **Engines:** CP-SAT, a Cypress-style JAX placer, Rust SA/LNS, MonoSAT or CP-SAT escape, PNS DP placer and meander engine, Freerouting v2.5.0 (pinned until 2.6.0 is released; 2.6.x exists only as RCs; `-mt 1` for final runs), KRT ([recommended-stack](../solvers/recommended-stack.md)).
- **Strengths:** mirrors the commercial pattern (LLM configures, engines construct, checkers judge, humans approve, [commercial-architecture-patterns](../landscape/commercial-architecture-patterns.md)) and the field-proven loop ([field-reports](../ux/field-reports.md)); every stage benchmarkable alone (PCBWorld D3, Cypress protocol); ships value early (review, setup, recipe solvers).
- **Risks:** fixed stage order handles contested regions crudely; placement and routing couple only through probes and gates; cross-domain trade-offs hide inside ε choices.

## Option B — Market of priority domain agents

```
                 ┌──────────── LLM arbiter ────────────┐
                 │ funds agents from criticality (I5); │
                 │ proposes substitutions (N2);        │
                 │ briefs contested rules (N4)         │
                 └───────┬─────────────────────▲───────┘
            credits      │                     │ prices, deadlocks
   ┌────────┬────────┬───▼────┬────────┬───────┴┬─────────┐
   Power    SI/HS    RF       EMC      Thermal  DFM/Mech     each agent = recipe pack
   N7 N8 R7 N9 R1-3  N9 R6    P8 R2    ΔT       fab packs    + critic + specialist
   └────────┴──── bids in budget units ─┴────────┘
                         ▼
      Resource market (N1): cells near anchor pins, board edge, SURF cuts,
      plane adjacency, via sites → clearing prices = explanations
                         ▼
      Reservation store (N5) → generic placer and routers fill the rest
                         ▼
      Critics; objections only with proof (N3); ε-lexicographic tie-break (N6)
```

- **Data flow:** (1) agents value resource bundles with their own critics in their own budget units; (2) criticality weights convert values to credits; (3) the market raises prices on over-subscribed resources until bids clear (PathFinder's mechanism lifted to domains, [pathfinder](../routing/pathfinder-negotiated-congestion.md)); (4) allocations become reservations; (5) the remainder goes to the generic engines.
- **LLM:** treasury and court: sets budgets, breaks deadlocks with iso-physics trades, writes arbitration summaries. Domain agents are code; LLM opinions cannot veto (N3).
- **Priorities:** explicit: a domain's influence = its funded criticality; clearing prices = what it paid.
- **Strengths:** directly implements submodules with different priorities; trade-offs visible and priced; new domains plug in as agents; fits contested regions (a buck beside an ADC beside USB3).
- **Risks:** market convergence and oscillation; calibrating one currency across nH, dB and °C; harder to debug and benchmark early; unproven for PCBs (closest evidence: stakeholder critics, which lacked a resolution mechanism, [analog-constraint-placement](../placement/analog-constraint-placement.md)).

## Option C — Topology-first co-design

```
 IR + budgets
     │
 Floorplan soft macros + cut check (P2)
     │
 Corridor contract (S1) ◄── LLM picks homotopies from menus (R1) ──► SURF joint check
     │
 Placement on a live topological sketch (P7)
   + shadow-return feasibility (R2) + connector-voltage EMI proxy (P8)
     │        topology persisted; every move re-tightens the bands
 Plane partitions shaped around the corridors (R7)
     │
 Late geometry: PNS beam realization (R8) for critical nets,
 Freerouting for the rest, meanders in reserved slack
     │
 Critics → an ECO edits the topology and re-tightens; it does not re-route
```

- **Data flow:** the persistent artifact is the topology (homotopy classes + corridor assignments); geometry is derived late and regenerable; placement optimizes sketch length and cut overflow instead of HPWL.
- **LLM:** at topology: groups bundles, picks homotopy options from bounded menus, orders critical nets. Evidence that LLM effort pays there: octilinear routing costs only ≈ 5% more length than any-angle for a fixed topology, and humans plan top-down ([topological-routing](../routing/topological-routing.md), [autorouter-skepticism](../routing/autorouter-skepticism.md)).
- **Priorities:** critical nets get menu choices and corridors first; return-path continuity (R2) and EMI (P8) are in the objective, not checked afterwards.
- **Strengths:** tight placement–routing coupling; cheap ECOs; physics-aware routing for HS, RF, EMC; precedent: Situs builds a topological map, then pushes and shoves.
- **Risks:** no maintained open multi-layer topological engine (Topola and gEDA toporouter are only starting points); large engineering effort; TopoR's gains are vendor claims.

## Option D — Search over decisions (explore mode)

```
 Decision DAG root = confirmed IR (S2)
     │
 MCTS / beam over macro decisions:
   sides, block regions, big-IC orientation, homotopy choices, engine presets
   prior: LLM proposals (+ VLM regions as weak anchors)
   rollout: Option A pipeline at low fidelity
     │
 Successive halving across fidelity rungs (S6); QD archive keyed by budget spend
     │
 2–4 alternatives (U4) with price tags (I4); bisect on regressions (S2)
     │
 Offline: evolve orchestration (L2), bandit dispatch (R5),
          planted-solution curricula (L1), all gated by V2 and V4
```

- **Data flow:** the LLM proposes macro decisions; search evaluates them by running the A pipeline cheaply; survivors climb the fidelity ladder ([performance-and-multifidelity](../solvers/performance-and-multifidelity.md)).
- **LLM:** prior and narration; compute replaces tokens.
- **Strengths:** robust alternatives, which designers want ([explanations-and-alternatives](../ux/explanations-and-alternatives.md)); exploits the Quilter-style placement × router matrix ([quilter](../landscape/quilter.md)); produces logs for learning.
- **Risks:** compute cost; needs A fast and reliable first; patent proximity: avoid NN- or LLM-guided SMC look-ahead over net orders or sub-routes with posterior selection ([patents-watchlist](../landscape/patents-watchlist.md)); keep search over placement-level decisions with deterministic evaluation.

## Comparison

| | A Staged spine | B Domain market | C Topology-first | D Decision search |
|---|---|---|---|---|
| LLM role | configurator and repairer of commitments | treasury and court | topology planner | prior and narrator |
| Cross-domain trade-offs | stage order, ε | explicit prices | corridor and cut capacity | search over alternatives |
| Placement–routing coupling | probes (P1), probe-completion gate | reservations | strong (sketch) | rollouts |
| Build effort | M | L | L | M, after A |
| First useful result | weeks to months (review, recipes) | months | many months | after A |
| Main risk | rigid order | convergence, currency | no open topological engine | compute, FTO |
| Evidence base | every working system | PathFinder, critics (indirect) | SURF, Situs, TopoR (vendor) | warehouse QD, Quilter X.Y |

## Recommendation

Build A as the spine; design the substrate (budgets, reservations, decision DAG, mutation-tested critics from day one) so B and C plug in without rewrites. Then add B for contested resources, C for critical nets only, D as an overnight explore mode. B and C add what A lacks: principled cross-domain arbitration and topology-level placement–routing coupling.

| Phase | Scope | Exit / kill criterion | Why here |
|---|---|---|---|
| 1. A-core | substrate; top-10 ideas except R1 and R2 (Phase 3): P6, N8, N7, V2, V1, I4, I1+I2, P1; Freerouting/KRT bulk; review mode ships first ([trust-requirements](../workflow/trust-requirements.md)) | beats Freerouting 2.5+ alone on PCBWorld D3 clean pass with SI PRCs, and beats Cypress-protocol routability (Freerouting v1.9.0, two free layers, % of pin pairs routed) on placement-stripped boards | least evidential risk; produces the harness every option needs ([benchmark-plan](../verification/benchmark-plan.md)) |
| 2. B-lite | N3, N4, N5, N6 everywhere; N1 market only for named contested resources (anchor-pin rings, plane adjacency, BGA via sites) | drop N1 if it doesn't beat N6 ε-lexicographic on per-domain PRC pass for the conflict-board suite | addresses the priority-submodule goal exactly where weighted sums fail |
| 3. C for critical nets | R1 menus, R2 shadow returns, R3, R8 on HS/RF nets only; bulk stays on engines; P7 only if R1 shows topology gains | keep only if critical-net SI PRC pass and vias beat PNS+Freerouting at < 50k tokens/board | highest ceiling for HS/RF quality but costliest, so confined to nets that justify it |
| 4. D overnight | S6, QD alternatives (U4), R5, L2, gated by V2 and V4 | better best-of-portfolio than A at equal wall-clock; red team finds no new hacks | turns spare compute into alternatives and learning once the pipeline is trustworthy |

## Conflicts and open questions

- **KiCad limits.** KiCad 10 IPC has no DRC run or routing calls, so file-level work plus `kicad-cli` until KiCad 11 (~Q1 2027). The IPC API has no route or shove RPC, and the existing Python binding to PNS, PCBWorld-Engine, pins KiCad 9.0.8 ([kicad-pns-router](../routing/kicad-pns-router.md); "Blocked" in [routing/strategy-candidates](../routing/strategy-candidates.md)); its maintenance across 10/11 is unknown. Matters from Phase 1 (Option A's critical-net, repair and tuning stages use PNS) and again for R8 and Option C.
- **Patent exposure.** All four options have an LLM updating constraints in a loop, resembling pending NVIDIA US 2025/0315590; collect prior art regardless of option ([patents-watchlist](../landscape/patents-watchlist.md)).
- **Spend models.** Budget spend models (I1) and the EMI proxy (P8) are uncalibrated; B and C quality depends on them: calibrate per V4 first.
- **Market fallback.** Whether B converges on real boards is unknown; N6 is the fallback.
- **No benchmark** measures cross-domain arbitration: build a conflict-board suite (L1 planted boards).

## Sources

- Research notes: [solver_toolbox.md § 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md), [routing_algorithms.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md), [routing_classics_supplement.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md), [cross_domain_ideas.md § Q11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md), [patents_and_industry.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md), [field_reports_and_ux.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md).
- Synthesis: [original-ideas catalog](../../ideas/original/README.md), [cross-domain transplants](../../ideas/cross-domain-transplants.md).
- Related: [constraint-ir](constraint-ir.md), [constraint-models-compared](constraint-models-compared.md), [recommended-stack](../solvers/recommended-stack.md), [expert-state-machine](../workflow/expert-state-machine.md).
