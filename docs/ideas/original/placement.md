# Original ideas: placement

Scope: P1–P10, ideas that change what the baseline placement pipeline optimizes and what it is fed. Part of the [original-ideas catalog](README.md); shorthands (alg#, llm#, prac#, eco#, xd#, hs#, pwr) as in [intent-and-why](intent-and-why.md). Baseline: LLM intent → analytical global placement (Cypress-style) → CP-SAT legalization → SA/LNS ([recommended-stack](../../topics/solvers/recommended-stack.md)). Test status: [research/ideas](../../research/ideas.md#original-ideas-58).
Keys: P1 router-probe pseudo-gradients, P2 contracted floorplan cut check, P3 physics-slack templates, P4 side assignment graph cut, P5 motif distributions, P6 slot assignment Hungarian, P7 topological sketch objective, P8 connector-voltage EMI proxy V_ab, P9 pin-mux co-floorplanning, P10 variant-robust placement

## P1. Router-probe pseudo-gradients — *novel combination*

Idea: run a bounded fast router on placement snapshots, attribute each failure to the parts that caused it, and feed the attributions to the analytical placer as forces and penalties (placement learns from routing probes, not RUDY alone).
Mechanism:
1. Every k Nesterov steps (or per LNS window), legalize a snapshot.
2. Run KRT or a short Freerouting pass (5–10 s budget). PCBWorld measured KRT at ≈0.65 s per D3-A board (≤31 pads), 3.27 s at ≤100 pads: budget by board size.
3. Collect unrouted nets, KRT blocker attributions, SURF cut overflows, via hotspots.
4. Convert: blocked net → force on its blockers, perpendicular to the blocked corridor, scaled by overflow; overflowing cut → density inflation over its region (a measured RUDY); crossing-causing pin sides → rotation hints.
5. Forces decay over iterations. Probe results are archived to fit a per-board linear surrogate online; no pretrained model (keeps clear of the learned-routability patents).
Evidence [I]:
- Practitioners already use autorouters as placement probes and read the failure clusters ([autorouter-distrust](../../topics/workflow/autorouter-distrust.md), [llm-field-reports](../../topics/workflow/llm-field-reports.md)).
- Rule routers are fast enough for the loop on small boards ([evaluation-stack](../../topics/verification/evaluation-stack.md)), not on larger ones: kaebench split C, 22 of 79 Freerouting runs hit the 600 s timeout ([harness](../../topics/verification/harness.md)).
- Published proxy-to-completion correlations are few and weak (one unreviewed 64-board study, one patent dataset); none calibrates RUDY on PCBs ([performance-and-multifidelity](../../topics/solvers/performance-and-multifidelity.md), [imitation](../../topics/data/imitation-and-learned-scores.md), [patents](../../topics/landscape/patents-watchlist.md)).
Builds on: prac#72–73; alg#31, alg#161; eco#109, eco#129; avoids eco#133 ([patents](../../topics/landscape/patents-watchlist.md)) · Test: Cypress small suite + placement-stripped D3 boards, equal wall-clock, Cypress-style placer with RUDY vs RUDY + probe forces; metric Freerouting 2.5.0 completion, clean pass, vias; ablation attributed forces vs uniform inflation · Effort/risk: M; noisy probes can make the placer thrash: probe only legalized snapshots, decay forces.

## P2. Contracted soft-macro floorplan with cut-capacity check — *novel combination*

Idea: floorplan schematic sheets and recognized blocks as soft macros with port contracts; reject any floorplan whose block-to-block cuts cannot carry the bundled nets on the planned layers, before any part is placed.
Mechanism:
- Block = area estimate (Σ courtyard / utilization) + 2–3 aspect-ratio variants + port contract (edge each inter-block bundle leaves from; bundle width = net count × pitch per layer) + fixed anchors (connectors, holes).
- Floorplan solve: unequal-area facility layout, CP-SAT soft macros or a slicing GA.
- Cut check: block-adjacency graph; route bundles as multicommodity flow; SURF-style cut test demand(cut) vs capacity = cut length × layers / pitch.
- Feedback: each overflow to the LLM as one line ("MCU↔DDR: 64 demands, capacity 48 on 4 layers") with options: rotate a block, change a port edge, add a layer pair, pin-swap ([S3](system-loop.md#s3-infeasibility-to-priced-eco-menu--novel-combination)).
- Output: accepted floorplan → KiCad rule areas + global-placement regions.
Evidence [I]:
- SURF cut test names the bottleneck ([topological-routing](../../topics/routing/topological-routing.md)); exact only for a fixed single-layer sketch; for multi-layer bundle flow across blocks it is a necessary condition, so a passing floorplan can still fail to route (hence the Spearman test).
- Practitioners add a layer pair above 70% channel use ([board-size-layers-stackup](../../topics/workflow/board-size-layers-stackup.md)); hierarchy matters most ([llm-guided-placement](../../topics/placement/llm-guided-placement.md)).
- Monolithic exact placement competitive only to about 100 parts; no feasible solution at 300 ([cp-sat](../../topics/solvers/cp-sat-milp-smt.md), [measurements](../../topics/solvers/benchmarks.md)).
Builds on: alg#165, alg#286, alg#307; prac#88, prac#102; xd#29; eco#111 · Test: 20 multi-block boards: Spearman correlation of floorplan-stage maximum cut overflow vs final completion; then completion of floorplans passing the check vs unfiltered · Effort/risk: M; bundle widths estimated before escape routing are crude: refine after the escape solver runs.

## P3. Physics-slack deformable templates — *new*

Idea: reuse EVM, datasheet and verified prior layouts as templates that may deform only within the physics slack of their intents (e.g. CIN may drift until loop nH reaches its budget), so the global placer bends templates without breaking them.
Mechanism:
- Template = relative pose program (PSDL-style rows, rings, pin-anchored offsets) + per-part slack region.
- Slack: sample perturbations, evaluate spend models ([I1](intent-and-why.md#i1-physics-budget-ledger--novel-combination)); slack = every Δx, Δy, Δθ that keeps all budgets met.
- Pipeline: slack linearized to box or ellipse constraints for the analytical placer, hard bounds for the legalizer.
- Zero slack = rigid macro; generous slack packs tighter; slack shrinks as shared budgets are consumed.
Evidence [I]:
- Copying the EVM is the least-risk path, yet app notes are "wrong until proven right" ([layout-reuse](../../topics/workflow/layout-reuse.md)).
- Coarse hints barely help; fine relative geometry does ([layout-retrieval](../../topics/data/layout-retrieval-and-reuse.md)).
- 3-D scenes: PSDL programs with repair preferred 94.3% over Holodeck, 82.9% over a declarative DSL ([scene-layout-transplants](../../topics/placement/scene-layout-transplants.md)).
Builds on: xd#1, xd#19; alg#69, alg#76, alg#91; llm#198; prac#99–101; [N7](priority-agents-and-negotiation.md#n7-hot-loop-micro-placer-minimizing-estimated-nanohenries--new) · Test: 30 converter, USB and crystal blocks on dense boards, rigid template vs free placement vs slack template; metrics budget compliance, area, routability · Effort/risk: M; slack sampling is costly: templates ≤ 8 parts.

## P4. Side assignment as a graph cut with second-side activation cost — *sharpened*

Idea: exact top/bottom choice for every part by min-cut or QUBO, affinities from intents (same side for a hot loop, opposite under a BGA, bottom for heat-sinking), plus a global charge for populating the second side at all.
Mechanism: binary s_i per part.
- Unary: tall, heavy, through-hole, user-facing parts prefer top; heat-sinkable parts prefer bottom; assembly-side preference.
- Pairwise: must-same, heavily weighted (hot-loop members, chain members); prefer-opposite (decaps under a BGA pin field); aggressor/victim separation across a plane.
- Global: solve twice, all-top and with a bottom-activation cost A.
- Solvers: submodular part by s-t min-cut; remainder by CP-SAT. The LLM writes the affinities with a reason each and sees their prices ([I4](intent-and-why.md#i4-constraint-price-tags-and-precomputed-foils--new-for-pcb)).
Evidence [I]: no academic placer chooses sides; LLMs left alone put about 80% of parts on top ([sides-thermal-emc-reuse](../../topics/placement/sides-thermal-emc-reuse.md)); Cypress needs sides fixed upstream ([analytical](../../topics/solvers/analytical-differentiable.md)); single-sided SMT is the DFM preference ([dfm-fab-limits](../../topics/rules/dfm-fab-limits.md)).
Builds on: alg#55–56; xd#13; pwr: single-sided preference, bottom heat-sinking · Test: D3 4-layer and Cypress two-sided boards, LLM-only sides vs all-top vs graph cut; metrics area, routability, sides populated, PRC pass · Effort/risk: S, low risk.

## P5. Verified motif distributions from open boards — *sharpened*

Idea: mine recurring local arrangements (QFN + decap ring, USB-C + ESD, crystal + load caps, buck cell) as distributions over relative poses, only from licence-clean, DRC-clean, fully routed boards, used as mixture priors rather than single fragments.
Mechanism:
1. Canonicalize to the anchor IC's frame (pin 1, rotation); key each satellite by pin function and package.
2. Gaussian mixture per (anchor family, pin function, satellite package, layer count).
3. Keep only boards with `ref_open == 0` that pass their own DRC, weighted by trust tier.
4. Placer term: weak −log p(pose); weight set by sweep against a random-prior control (VeoPlace's λ_A = 0.01 multiplies a quadratic anchor in that benchmark's units and does not transfer). Datasheet hard constraints override.
5. Retrieval returns the motif, its density, and exemplar boards with licences.
Evidence [I]: learnable signal is relational and per-package ([measured-priors](../../topics/data/measured-priors.md)); coarse hints score 0.19–0.21 vs 0.63 for designers, so fine relative geometry is needed ([layout-retrieval](../../topics/data/layout-retrieval-and-reuse.md)); weak anchors help, strong ones over-constrain ([llm-guided-placement](../../topics/placement/llm-guided-placement.md)); only 33% of human boards pass their own DRC, so filtering matters ([corpora-and-yield](../../topics/data/corpora-and-yield.md)).
Builds on: llm#245, llm#257, llm#260–265; alg#124–125. **FTO:** near Cadence '060 (placement constraints learned from prior boards); keep it statistical, get counsel ([patents](../../topics/landscape/patents-watchlist.md)) · Test: placement-stripped D3 boards, no prior vs coarse hints vs motif prior vs designer placement; metric clean-route rate · Effort/risk: M; hobby bias (keyboards, ESP32 boards) requires stratifying the corpus.

## P6. Slot assignment stage — *sharpened*

Idea: once templates or motifs fix the slots, assign interchangeable parts (equal decaps, resistor arrays, pin-swappable connector pins, LED strings) by exact min-cost matching on crossings and length.
Mechanism:
- Interchange class: same footprint, same electrical role, net-equivalent or declared-swappable pins.
- Cost(part→slot) = HPWL + airwire crossings + budget spend.
- Hungarian algorithm per class, iterate across classes to a fixed point.
- Pin swaps emitted as back-annotation proposals for human approval.
Evidence [I]:
- Swapping interchangeable parts alone drops designer clean-route 0.56 → 0.31–0.39, so assignment within groups matters ([imitation](../../topics/data/imitation-and-learned-scores.md)). Caveats: one third-party, unreviewed 64-board study; the swaps also added 0.9–3.5 pre-route DRC errors on average, so the drop is not purely about assignment.
- Pin assignment with escape is polynomial-optimal ([escape-routing](../../topics/routing/escape-routing.md)).
Builds on: llm#291; alg#47–48, alg#190; eco#104 · Test: placement-stripped D3 boards, placer output with vs without the slot stage; metrics clean-route rate, crossings · Effort/risk: S, low risk; pin swaps always need human approval.

## P7. Live topological sketch as the placement objective — *novel combination*

Idea: keep an incremental rubber-band sketch (homotopy classes over a constrained Delaunay triangulation of pads and obstacles) alive during placement; optimize sketch length + cut overflow instead of HPWL or RUDY.
Mechanism:
1. Route all nets topologically on the current placement (toporouter-style, cheap).
2. Per move: update the triangulation locally; re-tighten affected bands, keeping their homotopy unless a better class is cheap; recompute SURF loads on affected cuts.
3. Objective = Σ octilinear-adjusted sketch length + λ·Σ cut overflow + critical-net crossings.
Use directly in SA/LNS detailed placement; in analytical global placement as a periodic correction, as in [P1](#p1-router-probe-pseudo-gradients--novel-combination).
Evidence [I]: for a fixed topology octilinear routing costs only about 5% more length, so topology decides quality; persisted topology makes the placement–routing loop cheap ([topological-routing](../../topics/routing/topological-routing.md)); HPWL is blind to intent ([quality-metrics](../../topics/verification/quality-metrics.md)).
Builds on: alg#29, alg#164–170; xd#14 · Test: (1) how well the sketch objective predicts final routed length and completion vs HPWL, RUDY, Cypress's crossing term; (2) detailed-placement quality on D3 · Effort/risk: L; no maintained open topological engine: start from Topola (Rust) or gEDA toporouter (GPLv2+).

## P8. Differentiable connector-voltage EMI proxy — *new*

Idea: turn LearnEMC's "no voltage between cable reference points" into a smooth placement penalty: estimated common-mode voltage between connector grounds, driven by fast return currents flowing between them.
Mechanism: for each pair of cabled connectors (a, b):

V_ab ≈ Σ_k I_k·2πf_k·L_plane·g(d_k)

- I_k: return current of fast net or loop k, from t_r and drive strength.
- L_plane: partial inductance of the plane region between a and b.
- g: smooth between-ness kernel; d_k = net k's distance from the a–b axis (pin segment, or its sketch from [P7](#p7-live-topological-sketch-as-the-placement-objective--novel-combination)).
- Penalty softplus(V_ab − V_budget), V_budget from the 1 mV Class B anchor; differentiable in positions, drops into a Cypress-style loss.
Evidence [I]: about 1 mV between cable reference points can fail Class B; MREMC is computable ([emc-placement](../../topics/rules/emc-placement.md)); no EMC-aware placer exists ([sides-thermal-emc-reuse](../../topics/placement/sides-thermal-emc-reuse.md)).
Builds on: hs#26–27, hs#98, hs#120, hs#138 · Test: (1) calibrate the V_ab ranking against openEMS or emcvisual on 10 synthetic two-connector boards; (2) placement A/B on 10 boards with ≥ 2 cabled connectors, metrics checker F findings, MREMC estimate, routability cost · Effort/risk: M; crude proxy: rank only within its trust radius ([V4](verification.md#v4-proxy-trust-radius--sharpened)).

## P9. Pin-mux co-floorplanning — *novel combination*

Idea: for MCUs and FPGAs with flexible pin functions, choose the peripheral-to-pin assignment jointly with block placement and IC orientation so each interface faces its connector, then propose the schematic change.
Mechanism:
- Deterministic pin-mux CSP from vendor tables: alternate functions, bank voltages, clock-capable pins.
- Geometry cost: angle between a pin's package side and the direction of its target block (from [P2](#p2-contracted-soft-macro-floorplan-with-cut-capacity-check--novel-combination)) + crossings.
- CP-SAT jointly with the IC's four rotations (small model).
- Output: ranked assignments with priced deltas; a human approves the back-annotation.
Evidence [I]: pin assignment with escape is polynomial-optimal ([escape-routing](../../topics/routing/escape-routing.md)); LLMs fail on multiplexed pins, so pin mux must be resolved deterministically ([net-role-classification](../../topics/llm/net-role-classification.md)); pin swaps are never delegated, so present options ([delegation](../../topics/workflow/delegation-and-expert-review.md)); fixing orientation upstream is the key solver lever ([cp-sat](../../topics/solvers/cp-sat-milp-smt.md)).
Builds on: llm#181; alg#180, alg#190; eco#104, eco#119 · Test: 15 STM32, RP2040 and ESP32 boards, crossings and completion with original vs co-optimized pin mux · Effort/risk: M; needs vendor pin tables: start with STM32 CubeMX exports.

## P10. Variant-robust placement — *new*

Idea: place for a set of alternate parts at once (second-source packages, KiCad 10 variants), so a supply-chain substitution needs no relayout.
Mechanism:
- Geometry: each substitutable slot uses the union of its alternates' courtyards, or compatible footprints with overlapping pads.
- Budgets: worst case across alternates (e.g. loop nH with the larger inductor).
- Engines: legalizer uses the union geometry; routing uses pad shapes compatible with every alternate, or per-variant DNP.
- Prices: each slot's area and routability cost of robustness reported ([I4](intent-and-why.md#i4-constraint-price-tags-and-precomputed-foils--new-for-pcb)); the user picks which slots to make robust.
Evidence [I]: KiCad 10 serves variants over IPC, DNP per variant ([built-in-automation-features](../../topics/kicad/built-in-automation-features.md)); footprint-variant mix-ups are among the costliest field failures ([field-failure-modes](../../topics/ux/field-failure-modes.md)); part-data APIs churn ([part-layout-card](../../topics/llm/part-layout-card.md)).
Builds on: eco#14; llm#358; prac#250 · Test: 10 boards with declared alternates; count re-layouts needed per approach, measure area overhead · Effort/risk: S–M; union courtyards waste area; price tags let the user choose.
