# Original ideas: placement

Part of the [original-ideas catalog](README.md). Shorthands as in [intent-and-why](intent-and-why.md). Baseline assumed: LLM intent → analytical global placement (Cypress-style) → CP-SAT legalization → SA/LNS ([recommended-stack](../../topics/solvers/recommended-stack.md)). These ideas change what that pipeline optimizes and what it is fed.

---

## P1. Router-probe pseudo-gradients — *novel combination*

**Pitch.** Run a bounded fast router on placement snapshots and attribute each failure to the parts that caused it. Feed the attributions back into the analytical placer as forces and penalties, so placement learns from routing probes rather than from RUDY.

**Mechanism.**
1. Every k Nesterov steps (or per LNS window), legalize a snapshot.
2. Run KRT (≈0.65 s) or a short Freerouting pass (5–10 s budget).
3. Collect unrouted nets, KRT blocker attributions, SURF cut overflows and via hotspots.
4. Convert them:
   - each blocked net becomes a force on its blockers, perpendicular to the blocked corridor, scaled by overflow;
   - each overflowing cut becomes a density inflation over its region (a measured RUDY);
   - pin sides that cause crossings become rotation hints.
5. Forces decay over iterations.

Probe results are archived to fit a per-board linear surrogate online. There is no pretrained model, which keeps clear of the learned-routability patents.

**Why it should work.**
- Practitioners already use autorouters as placement probes and read the failure clusters ([autorouter-distrust](../../topics/workflow/autorouter-distrust.md), [llm-field-reports](../../topics/workflow/llm-field-reports.md)).
- Rule routers are fast enough for the loop ([evaluation-stack](../../topics/verification/evaluation-stack.md)).
- No published correlation links RUDY to completion ([performance-and-multifidelity](../../topics/solvers/performance-and-multifidelity.md)).

**Builds on.** prac#72–73; alg#31, alg#161; eco#109, eco#129. Avoids eco#133 ([patents](../../topics/landscape/patents-watchlist.md)).

**How to test.** On the Cypress small suite and placement-stripped D3 boards, at equal wall-clock, compare a Cypress-style placer with RUDY against the same placer with probe forces. Metric: Freerouting 2.5 completion, clean pass and vias. Ablation: attributed forces vs uniform inflation.

**Effort/risk.** M. Noisy probes can make the placer thrash; probe only legalized snapshots and decay the forces.

---

## P2. Contracted soft-macro floorplan with cut-capacity check — *novel combination*

**Pitch.** Floorplan schematic sheets and recognized blocks as soft macros with port contracts. Reject any floorplan whose block-to-block cuts cannot carry the bundled nets on the planned layers, before a single part is placed.

**Mechanism.**
- **Each block** has:
  - an area estimate (Σ courtyard / utilization);
  - 2–3 aspect-ratio variants;
  - a port contract: the edge each inter-block bundle should leave from, and the bundle width (net count × pitch per layer);
  - fixed anchors (connectors, holes).
- **Floorplan solve:** unequal-area facility layout with CP-SAT soft macros or a slicing GA.
- **Cut check:** build the block-adjacency graph, route bundles as multicommodity flow, and run SURF-style cut tests: demand(cut) vs capacity = cut length × layers / pitch.
- **Feedback:** each overflow goes to the LLM as one line ("MCU↔DDR: 64 demands, capacity 48 on 4 layers"), with options to rotate a block, change a port edge, add a layer pair, or pin-swap ([S3](system-loop.md#s3-infeasibility-to-priced-eco-menu--novel-combination)).
- **Output:** the accepted floorplan becomes KiCad rule areas and global-placement regions.

**Why it should work.**
- The SURF cut test is exact and names the bottleneck ([topological-routing](../../topics/routing/topological-routing.md)).
- Practitioners add a layer pair above 70% channel use ([board-size-layers-stackup](../../topics/workflow/board-size-layers-stackup.md)).
- Hierarchy matters most ([llm-guided-placement](../../topics/placement/llm-guided-placement.md)).
- Monolithic exact placement fails beyond about 100 parts ([cp-sat](../../topics/solvers/cp-sat-milp-smt.md)).

**Builds on.** alg#165, alg#286, alg#307; prac#88, prac#102; xd#29; eco#111.

**How to test.** On 20 multi-block boards, measure the Spearman correlation between floorplan-stage maximum cut overflow and final completion. Then compare completion for floorplans that pass the check against unfiltered floorplans.

**Effort/risk.** M. Bundle widths estimated before escape routing are crude; refine them after the escape solver runs.

---

## P3. Physics-slack deformable templates — *new*

**Pitch.** Reuse EVM, datasheet and verified prior layouts as templates that may deform only within the physics slack of their intents. For example, CIN may drift until loop nH reaches its budget. The global placer can then bend templates without breaking them.

**Mechanism.**
- **Template** = a relative pose program (PSDL-style rows, rings and pin-anchored offsets) plus a per-part slack region.
- **Slack** is found by sampling perturbations and evaluating spend models ([I1](intent-and-why.md#i1-physics-budget-ledger--novel-combination)): every Δx, Δy, Δθ that keeps all budgets met.
- **Use in the pipeline:** slack is linearized to box or ellipse constraints for the analytical placer and to hard bounds for the legalizer.
- **Behaviour:** a zero-slack template is a rigid macro; generous slack lets the placer pack tighter. Slack shrinks as shared budgets are consumed.

**Why it should work.**
- Copying the EVM is the least-risk path, yet app notes are "wrong until proven right" ([layout-reuse](../../topics/workflow/layout-reuse.md)).
- Coarse hints barely help; fine relative geometry does ([layout-retrieval](../../topics/data/layout-retrieval-and-reuse.md)).
- PSDL programs with repair were preferred 94.3% ([scene-layout-transplants](../../topics/placement/scene-layout-transplants.md)).

**Builds on.** xd#1, xd#19; alg#69, alg#76, alg#91; llm#198; prac#99–101; [N7](priority-agents-and-negotiation.md#n7-hot-loop-micro-placer-minimizing-estimated-nanohenries--new).

**How to test.** Place 30 converter, USB and crystal blocks on dense boards in three ways: rigid template, free placement, and slack template. Metrics: budget compliance, area, routability.

**Effort/risk.** M. Sampling slack is costly, so limit templates to 8 parts or fewer.

---

## P4. Side assignment as a graph cut with second-side activation cost — *sharpened*

**Pitch.** Decide top or bottom for every part with an exact min-cut or QUBO. Intents supply the affinities: same side for a hot loop, opposite sides under a BGA, bottom for heat-sinking. A global term charges for populating the second side at all.

**Mechanism.** Each part has a binary variable s_i.
- **Unary terms:** tall, heavy, through-hole and user-facing parts prefer top; heat-sinkable parts prefer bottom; plus the assembly-side preference.
- **Pairwise terms:**
  - must-same, heavily weighted (hot-loop members, chain members);
  - prefer-opposite (decaps under a BGA pin field);
  - aggressor/victim separation across a plane.
- **Global term:** solve twice, once all-top and once with a bottom-activation cost A.
- **Solvers:** the submodular part by s-t min-cut; the remainder by CP-SAT.

The LLM writes the affinities with a reason for each and sees their prices ([I4](intent-and-why.md#i4-constraint-price-tags-and-precomputed-foils--new-for-pcb)).

**Why it should work.**
- No academic placer chooses sides, and LLMs left alone put about 80% of parts on top ([sides-thermal-emc-reuse](../../topics/placement/sides-thermal-emc-reuse.md)).
- Cypress needs sides fixed upstream ([analytical](../../topics/solvers/analytical-differentiable.md)).
- Single-sided SMT is the DFM preference ([dfm-fab-limits](../../topics/rules/dfm-fab-limits.md)).

**Builds on.** alg#55–56; xd#13; pwr: single-sided preference, bottom heat-sinking.

**How to test.** On D3 4-layer and Cypress two-sided boards, compare LLM-only sides, all-top, and the graph cut. Metrics: area, routability, sides populated, PRC pass.

**Effort/risk.** S, low risk.

---

## P5. Verified motif distributions from open boards — *sharpened*

**Pitch.** Mine recurring local arrangements (QFN + decap ring, USB-C + ESD, crystal + load caps, buck cell) as distributions over relative poses. Take them only from licence-clean, DRC-clean, fully routed boards, and use them as mixture priors rather than single fragments.

**Mechanism.**
1. Canonicalize to the anchor IC's frame (pin 1, rotation). Key each satellite by pin function and package.
2. Fit a Gaussian mixture per (anchor family, pin function, satellite package, layer count).
3. Keep only boards with `ref_open == 0` that pass their own DRC, weighted by trust tier.
4. Placer term: a weak −log p(pose), at VeoPlace-like strength (λ ≈ 0.01). Datasheet hard constraints override it.
5. Retrieval returns the motif, its density, and exemplar boards with their licences.

**Why it should work.**
- The learnable signal is relational and per-package ([measured-priors](../../topics/data/measured-priors.md)).
- Coarse hints score 0.19–0.21 against 0.63 for designers, so fine relative geometry is needed ([layout-retrieval](../../topics/data/layout-retrieval-and-reuse.md)).
- Weak anchors help, while strong ones over-constrain ([llm-guided-placement](../../topics/placement/llm-guided-placement.md)).
- Only 33% of human boards pass their own DRC, so filtering matters ([corpora-and-yield](../../topics/data/corpora-and-yield.md)).

**Builds on.** llm#245, llm#257, llm#260–265; alg#124–125. **FTO:** this is near Cadence '060 (placement constraints learned from prior boards). Keep it statistical and get counsel ([patents](../../topics/landscape/patents-watchlist.md)).

**How to test.** On placement-stripped D3 boards, compare no prior, coarse hints, motif prior and the designer placement. Metric: clean-route rate.

**Effort/risk.** M. Hobby bias (keyboards, ESP32 boards) requires stratifying the corpus.

---

## P6. Slot assignment stage — *sharpened*

**Pitch.** Once templates or motifs fix the slots, assign interchangeable parts to them by exact min-cost matching on crossings and length. Interchangeable parts include equal decaps, resistor arrays, pin-swappable connector pins and LED strings.

**Mechanism.**
- **Interchange classes:** same footprint, same electrical role, and net-equivalent or declared-swappable pins.
- **Cost of part→slot:** HPWL + airwire crossings + budget spend.
- **Solve:** the Hungarian algorithm per class, iterating across classes to a fixed point.
- **Pin swaps** are emitted as back-annotation proposals for a human to approve.

**Why it should work.**
- Swapping interchangeable parts alone drops designer clean-route from 0.56 to 0.31–0.39, so assignment within groups matters ([imitation](../../topics/data/imitation-and-learned-scores.md)).
- Pin assignment with escape is polynomial-optimal ([escape-routing](../../topics/routing/escape-routing.md)).

**Builds on.** llm#291; alg#47–48, alg#190; eco#104.

**How to test.** On placement-stripped D3 boards, run placer output with and without the slot stage. Metrics: clean-route rate, crossings.

**Effort/risk.** S, low risk. Pin swaps always need human approval.

---

## P7. Live topological sketch as the placement objective — *novel combination*

**Pitch.** Keep an incremental rubber-band sketch (homotopy classes over a constrained Delaunay triangulation of pads and obstacles) alive during placement. Optimize sketch length plus cut overflow instead of HPWL or RUDY.

**Mechanism.**
1. Route all nets topologically on the current placement (toporouter-style, cheap).
2. On each move:
   - update the triangulation locally;
   - re-tighten the affected bands, keeping their homotopy unless a better class is cheap;
   - recompute SURF loads on the affected cuts.
3. Objective = Σ octilinear-adjusted sketch length + λ·Σ cut overflow + critical-net crossings.

Use this directly in SA/LNS detailed placement. In analytical global placement, apply it as a periodic correction, as in [P1](#p1-router-probe-pseudo-gradients--novel-combination).

**Why it should work.**
- For a fixed topology, octilinear routing costs only about 5% more length, so topology decides quality.
- Persisted topology makes the placement–routing loop cheap ([topological-routing](../../topics/routing/topological-routing.md)).
- HPWL is blind to intent ([quality-metrics](../../topics/verification/quality-metrics.md)).

**Builds on.** alg#29, alg#164–170; xd#14.

**How to test.**
1. Measure how well the sketch objective predicts final routed length and completion, against HPWL, RUDY and Cypress's crossing term.
2. Compare detailed-placement quality on D3.

**Effort/risk.** L. No maintained open topological engine exists. Start from Topola (Rust) or gEDA toporouter (GPLv2+).

---

## P8. Differentiable connector-voltage EMI proxy — *new*

**Pitch.** Turn LearnEMC's "no voltage between cable reference points" into a smooth placement penalty: the estimated common-mode voltage between connector grounds, driven by fast return currents flowing between them.

**Mechanism.** For each pair of cabled connectors (a, b), estimate the voltage across the plane between them:

V_ab ≈ Σ_k I_k·2πf_k·L_plane·g(d_k)

- I_k is the return current of fast net or loop k, from t_r and drive strength.
- L_plane is the partial inductance of the plane region between a and b.
- g is a smooth between-ness kernel. d_k is net k's distance from the a–b axis, using its pin segment or its sketch from [P7](#p7-live-topological-sketch-as-the-placement-objective--novel-combination).

The penalty is softplus(V_ab − V_budget), with V_budget from the 1 mV Class B anchor. It is differentiable in positions, so it drops straight into a Cypress-style loss.

**Why it should work.**
- About 1 mV between cable reference points can fail Class B; MREMC is computable ([emc-placement](../../topics/rules/emc-placement.md)).
- No EMC-aware placer exists ([sides-thermal-emc-reuse](../../topics/placement/sides-thermal-emc-reuse.md)).

**Builds on.** hs#26–27, hs#98, hs#120, hs#138.

**How to test.**
1. Calibrate the V_ab ranking against openEMS or emcvisual on 10 synthetic two-connector boards.
2. Run a placement A/B on 10 boards with two or more cabled connectors. Metrics: checker F findings, MREMC estimate, routability cost.

**Effort/risk.** M. The proxy is crude, so use it only for ranking within its trust radius ([V4](verification.md#v4-proxy-trust-radius--sharpened)).

---

## P9. Pin-mux co-floorplanning — *novel combination*

**Pitch.** For MCUs and FPGAs with flexible pin functions, choose the peripheral-to-pin assignment jointly with block placement and IC orientation, so each interface faces its connector. Then propose the schematic change.

**Mechanism.**
- A deterministic pin-mux CSP is built from vendor tables: alternate functions, bank voltages, clock-capable pins.
- The geometry cost is the angle between a pin's side on the package and the direction of its target block (from [P2](#p2-contracted-soft-macro-floorplan-with-cut-capacity-check--novel-combination)), plus crossings.
- CP-SAT solves this jointly with the IC's four rotations; the model is small.
- Output: ranked assignments with priced deltas. A human approves the back-annotation.

**Why it should work.**
- Pin assignment with escape is polynomial-optimal ([escape-routing](../../topics/routing/escape-routing.md)).
- LLMs fail on multiplexed pins, so pin mux must be resolved deterministically ([net-role-classification](../../topics/llm/net-role-classification.md)).
- Pin swaps are never delegated, so the tool should present options ([delegation](../../topics/workflow/delegation-and-expert-review.md)).
- Fixing orientation upstream is the key solver lever ([cp-sat](../../topics/solvers/cp-sat-milp-smt.md)).

**Builds on.** llm#181; alg#180, alg#190; eco#104, eco#119.

**How to test.** On 15 STM32, RP2040 and ESP32 boards, compare crossings and completion between the original pin mux and the co-optimized one.

**Effort/risk.** M. It needs vendor pin tables; start with STM32 CubeMX exports.

---

## P10. Variant-robust placement — *new*

**Pitch.** Place for a set of alternate parts at once (second-source packages, KiCad 10 variants), so a supply-chain substitution needs no relayout.

**Mechanism.**
- **Geometry:** each substitutable slot uses the union of its alternates' courtyards, or compatible footprints with overlapping pads.
- **Budgets:** evaluated at the worst case across alternates (for example, loop nH with the larger inductor).
- **Engines:** the legalizer uses the union geometry; routing uses pad shapes compatible with every alternate, or per-variant DNP.
- **Prices:** each slot's area and routability cost of robustness is reported ([I4](intent-and-why.md#i4-constraint-price-tags-and-precomputed-foils--new-for-pcb)), so the user picks which slots to make robust.

**Why it should work.**
- KiCad 10 serves variants over IPC, with DNP per variant ([built-in-automation-features](../../topics/kicad/built-in-automation-features.md)).
- Footprint-variant mix-ups are among the costliest field failures ([field-failure-modes](../../topics/ux/field-failure-modes.md)).
- Part-data APIs churn ([part-layout-card](../../topics/llm/part-layout-card.md)).

**Builds on.** eco#14; llm#358; prac#250.

**How to test.** On 10 boards with declared alternates, count the re-layouts each approach needs and measure area overhead.

**Effort/risk.** S–M. Union courtyards waste area; the price tags let the user choose.
