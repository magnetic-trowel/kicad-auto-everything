# Hybrid architecture options for LLM-driven placement and routing

**TL;DR**
- There are four coherent end-to-end hybrids:
  - **A**, a staged intent-compiler spine;
  - **B**, a market of priority domain agents;
  - **C**, topology-first co-design;
  - **D**, search over LLM decisions.
- All four share one substrate. The LLM never emits copper or coordinates ([llm-routing-evidence](../routing/llm-routing-evidence.md)).
- **Recommendation: build A now, with B- and C-ready interfaces, then add B for contested resources, C for critical nets only, and D as an overnight explore mode.**
- A matches every working system: the LLM configures, engines construct, checkers judge, humans approve ([commercial-architecture-patterns](../landscape/commercial-architecture-patterns.md)). B and C add what A lacks: principled cross-domain arbitration, and topology-level coupling between placement and routing.
- The idea ids (I1, N7, R2, …) refer to the [original-ideas catalog](../../ideas/original/README.md). Every architecture here is untested [I].

## Common substrate (all options)

| Layer | Content | Evidence / ideas |
|---|---|---|
| Board I/O | KiCad 10 four-channel backend: IPC commits, `.kicad_dru` writes, `kicad-cli` DRC referee, SWIG DSN/SES helper. A `BoardSession` abstraction for KiCad 11 headless | [ipc-api-10-vs-11](../kicad/ipc-api-10-vs-11.md) |
| Intent | `pcb-intent` IR + budget ledger (I1) with dimensioned values (I2), criticality field (I5), why-graph (I3), stamps in the board file (I7) | [constraint-ir](constraint-ir.md), [intent-and-why](../../ideas/original/intent-and-why.md) |
| Knowledge | Rule packs with precedence and contested selectors; layout cards with provenance; recipes as data | [rule-pack-format](../rules/rule-pack-format.md), [part-layout-card](../llm/part-layout-card.md) |
| Verification | Critic stack A/S/J; mutation-tested layout unit tests (V1); proxy trust radius (V4); licensed judge (V3) | [critic-stack](../verification/critic-stack.md), [verification](../../ideas/original/verification.md) |
| Control | Decision DAG with replay (S2); propose → revision-bound apply; one undo per step; predictions before checks (S4) | [mcp-tool-surface-spec](../kicad/mcp-tool-surface-spec.md), [system-loop](../../ideas/original/system-loop.md) |

### Priority domains → specialist submodules

The same submodules appear in every option. What differs between options is how their conflicts get resolved.

| Priority domain | Specialist submodule (ideas) | Engine | Tier |
|---|---|---|---|
| Power conversion (hot loops, gate drive) | N7 nH micro-placer; R6 hot-loop and Kelvin macros; R7 plane partitions | CP-SAT/DFS; generators; graph cut | 1 |
| RF | N9 antenna→match→IC chain; R6 RF polygon macros | DP + CP-SAT; generators | 1 |
| High-speed, diff pairs | N9 I/O chains; R3 via sites; R1 homotopy menus; R2 shadow returns; R8 PNS beam | MCF/SAT escape; PNS DP placer + meanders | 2 |
| Adjacency-critical (crystal, FB divider, ESD, Kelvin) | P3 slack templates; N9; R6 | PSDL program + repair | 2 |
| Decoupling / PDN | N8 assignment; PDN screener | min-cost flow; lumped RLC | 2 |
| EMI/EMC | P8 connector-voltage proxy; P4 side cut; R2; Checker F | analytical penalty; router cost | spans tiers |
| Thermal | ΔT budgets (I1); P4 bottom heat-sinking | screener in the placement loop | spans tiers |
| DFM / mechanical | fab packs (precedence 10); P10 variants; locked anchors | legalizer constraints | hard |
| Bulk signals | R5 bandit over Freerouting / KRT / PathFinder | — | last |

Evidence for the specialists: hot loops rank first everywhere ([hot-loops](../rules/power/hot-loops.md)); mounting inductance governs decoupling ([decoupling-pdn](../rules/decoupling-pdn.md)); TVS order is comparative ([emc-placement](../rules/emc-placement.md)); return-path continuity is the shared SI/EMC physics ([si-fundamentals](../rules/si-fundamentals.md)).

---

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
   → slot assignment (P6) → SA/LNS            gate: probe completion ≥ 85%
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

**Data flow.** The IR is the only channel from the LLM to the engines. Engines return structured findings, prices and conflict lists, never geometry dumps. Each stage commits through one undoable step and is read back.

**Where the LLM sits.**
- Stage 1: adjudication.
- Stage 2: authoring intents and side affinities.
- Stage 6: repair, choosing from bounded menus.
- Throughout: narration generated from derivations and the why-graph.

Estimated token use is around 50–200k per board, far below the 0.4–1.9M tokens of per-step routing agents ([pcbworld](../routing/pcbworld.md)) [I].

**Priorities.** Tier order is set by stage order plus the ε-lexicographic compiler (N6). Critical copper becomes reservations (N5), not frozen copper, because KiCad 10 SES import deletes unlocked copper ([specctra-freerouting-integration](../kicad/specctra-freerouting-integration.md)).

**Engines.** CP-SAT, a Cypress-style JAX placer, Rust SA/LNS, MonoSAT or CP-SAT escape, the PNS DP placer and meander engine, Freerouting 2.6.x, and KRT ([recommended-stack](../solvers/recommended-stack.md)).

**Strengths.**
- It mirrors the commercial pattern and the field-proven loop ([field-reports](../ux/field-reports.md)).
- Every stage can be benchmarked on its own (PCBWorld D3, Cypress protocol).
- It ships value early: review, setup and recipe solvers.

**Risks.**
- The fixed stage order handles contested regions crudely.
- Placement and routing couple only through probes and gates.
- Cross-domain trade-offs hide inside ε choices.

---

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

**Data flow.**
1. Agents value resource bundles with their own critics, in their own budget units.
2. Criticality weights convert the values into credits.
3. The market raises prices on over-subscribed resources until bids clear, which is PathFinder's mechanism lifted to domains ([pathfinder](../routing/pathfinder-negotiated-congestion.md)).
4. Allocations become reservations.
5. The remainder goes to the generic engines.

**Where the LLM sits.** It acts as treasury and court: setting budgets, breaking deadlocks with iso-physics trades, and writing arbitration summaries. Domain agents are code, and LLM opinions cannot veto (N3).

**Priorities.** Priority is explicit. A domain's influence equals its funded criticality, and the clearing prices are directly what it paid.

**Strengths.**
- It directly implements the request for submodules with different priorities.
- Trade-offs are visible and priced.
- New domains plug in as agents.
- It fits contested regions such as a buck beside an ADC beside USB3.

**Risks.**
- Market convergence and oscillation.
- Calibrating a common currency across nH, dB and °C.
- Harder to debug and benchmark early.
- Unproven anywhere for PCBs. The closest evidence is stakeholder critics, which lacked a resolution mechanism ([analog-constraint-placement](../placement/analog-constraint-placement.md)).

---

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

**Data flow.** The persistent artifact is the topology: homotopy classes plus corridor assignments. Geometry is derived from it late and can be regenerated. Placement optimizes sketch length and cut overflow instead of HPWL.

**Where the LLM sits.** At topology. It groups bundles, picks homotopy options from bounded menus, and orders critical nets. This is where the evidence says LLM effort pays: octilinear routing costs only about 5% more length than any-angle for a fixed topology, and humans plan top-down ([topological-routing](../routing/topological-routing.md), [autorouter-skepticism](../routing/autorouter-skepticism.md)).

**Priorities.** Critical nets get menu choices and corridors first. Return-path continuity (R2) and EMI (P8) are built into the objective rather than checked afterwards.

**Strengths.**
- Tight placement–routing coupling.
- Cheap ECOs.
- Physics-aware routing for HS, RF and EMC.
- Precedent: Situs builds a topological map and then pushes and shoves.

**Risks.**
- No maintained open multi-layer topological engine exists. Topola and gEDA toporouter are only starting points.
- Building it is a large engineering effort.
- Gains claimed by TopoR are vendor claims.

---

## Option D — Search over decisions (explore mode)

```
 Decision DAG root = confirmed IR (S2)
     │
 MCTS / beam over macro decisions:
   sides, block regions, big-IC orientation, homotopy choices, engine presets
   prior: LLM proposals (+ VLM regions, λ≈0.01)
   rollout: Option A pipeline at low fidelity
     │
 Successive halving across fidelity rungs (S6); QD archive keyed by budget spend
     │
 2–4 alternatives (U4) with price tags (I4); bisect on regressions (S2)
     │
 Offline: evolve orchestration (L2), bandit dispatch (R5),
          planted-solution curricula (L1), all gated by V2 and V4
```

**Data flow.** The LLM proposes macro decisions, and search evaluates them by running the A pipeline cheaply. Survivors climb the fidelity ladder ([performance-and-multifidelity](../solvers/performance-and-multifidelity.md)).

**Where the LLM sits.** It supplies the prior and the narration. Compute replaces tokens.

**Strengths.**
- Robust alternatives, which designers want ([explanations-and-alternatives](../ux/explanations-and-alternatives.md)).
- It exploits the Quilter-style placement × router matrix ([quilter](../landscape/quilter.md)).
- It produces logs for learning.

**Risks.**
- Compute cost.
- It needs A to be fast and reliable first.
- Patent proximity: avoid NN- or LLM-guided SMC look-ahead over net orders or sub-routes with posterior selection ([patents-watchlist](../landscape/patents-watchlist.md)). Search should stay over placement-level decisions, with deterministic evaluation.

---

## Comparison

| | A Staged spine | B Domain market | C Topology-first | D Decision search |
|---|---|---|---|---|
| LLM role | configurator and repairer of commitments | treasury and court | topology planner | prior and narrator |
| Cross-domain trade-offs | stage order, ε | explicit prices | corridor and cut capacity | search over alternatives |
| Placement–routing coupling | probes (P1), 85% gate | reservations | strong (sketch) | rollouts |
| Build effort | M | L | L | M, after A |
| First useful result | weeks to months (review, recipes) | months | many months | after A |
| Main risk | rigid order | convergence, currency | no open topological engine | compute, FTO |
| Evidence base | every working system | PathFinder, critics (indirect) | SURF, Situs, TopoR (vendor) | warehouse QD, Quilter X.Y |

## Recommendation

**Build A as the spine, but design the substrate so B and C plug in without rewrites.** That means budgets, reservations, the decision DAG and mutation-tested critics from day one.

| Phase | Scope | Exit / kill criterion |
|---|---|---|
| 1. A-core | Substrate. Top-10 ideas: P6, N8, N7, V2, V1, I4, I1+I2, P1. Freerouting/KRT bulk. Review mode ships first ([trust-requirements](../workflow/trust-requirements.md)) | Beats Freerouting 2.5+ alone on PCBWorld D3 clean pass with SI PRCs, and beats Cypress-protocol routability on placement-stripped boards |
| 2. B-lite | N3, N4, N5, N6 everywhere. N1 market only for named contested resources (anchor-pin rings, plane adjacency, BGA via sites) | Drop N1 if it doesn't beat N6 ε-lexicographic on per-domain PRC pass for the conflict-board suite |
| 3. C for critical nets | R1 menus, R2 shadow returns, R3, R8 on HS/RF nets only; bulk stays on engines. P7 only if R1 shows topology gains | Keep it only if critical-net SI PRC pass and vias beat PNS+Freerouting at <50k tokens/board |
| 4. D overnight | S6, QD alternatives (U4), R5, L2, gated by V2 and V4 | Better best-of-portfolio than A at equal wall-clock; red team finds no new hacks |

Why this order:
- A carries the least evidential risk and produces the harness every other option needs ([benchmark-plan](../verification/benchmark-plan.md)).
- B addresses the user's priority-submodule goal exactly where weighted sums fail.
- C is the highest-ceiling bet for HS/RF quality but the costliest, so it is confined to the nets that justify it.
- D turns spare compute into alternatives and learning once the pipeline is trustworthy.

## Conflicts and open questions
- **Physics-first update (2026-10-22):** the physics-first pass recommends one joint placement+routing optimizer on a topology-carrying state, with physics spend models as the shared objective, in place of the staged place → gate → route spine for critical structures. See [joint-place-route](../physics/joint-place-route.md) and [physics/README](../physics/README.md).
- **KiCad limits.**
  - KiCad 10 IPC has no DRC run or routing calls, so file-level work plus `kicad-cli` is required until KiCad 11 (~Q1 2027).
  - PCBWorld-Engine maintenance across 10/11 is unknown, which matters for R8 and Option C ([kicad-pns-router](../routing/kicad-pns-router.md)).
- **Patent exposure.** All four options have an LLM updating constraints in a loop, which resembles pending NVIDIA US 2025/0315590. Collecting prior art matters regardless of the option chosen ([patents-watchlist](../landscape/patents-watchlist.md)).
- **Spend models.** Budget spend models (I1) and the EMI proxy (P8) are uncalibrated, and the quality of Options B and C depends on them, so calibrate per V4 first.
- **Market fallback.** Whether a market (B) converges on real boards is unknown; N6 is the fallback.
- **No benchmark.** No benchmark measures cross-domain arbitration. A conflict-board suite (L1 planted boards) must be built.

## Sources
- Research notes:
  - [solver_toolbox.md § 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)
  - [routing_algorithms.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md)
  - [routing_classics_supplement.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md)
  - [cross_domain_ideas.md § Q11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)
  - [patents_and_industry.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md)
  - [field_reports_and_ux.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)
- Synthesis: [original-ideas catalog](../../ideas/original/README.md), [cross-domain transplants](../../ideas/cross-domain-transplants.md)

See also:
- [constraint-ir](constraint-ir.md)
- [constraint-models-compared](constraint-models-compared.md)
- [recommended-stack](../solvers/recommended-stack.md)
- [commercial-architecture-patterns](../landscape/commercial-architecture-patterns.md)
- [expert-state-machine](../workflow/expert-state-machine.md)
