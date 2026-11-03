# Original ideas: priority submodules, arbitration and specialist solvers

Scope: N1–N9, submodules with different priorities (power conversion, high-speed and differential pairs, RF, EMI, parts that must sit together). Part of the [original-ideas catalog](README.md); shorthands as in [intent-and-why](intent-and-why.md). Test status: [research/ideas](../../research/ideas.md#original-ideas-58).
Keys: N1 resource market, auction, N2 iso-physics substitution, N3 veto-with-proof, objection budget, N4 contested-rule court, precedent, N5 reservation tokens, N6 ε-lexicographic compiler, N7 hot-loop nH micro-placer, L_est, N8 decap-to-pin assignment, L_mount, N9 ordered-chain embedder

Design stance: a domain submodule is deterministic code (recipe pack + critic + specialist realizer); the LLM funds, arbitrates and explains, never does the geometry.

## N1. Domain agents in a resource market — *new*

Idea: power, SI, RF, EMC, thermal, DFM and mechanical submodules buy contested board resources with criticality-funded credits; an ascending-price auction clears the bids. Generalizes PathFinder negotiated congestion from nets to domains and from routing to placement.
Mechanism:
- Resources: placement cells near anchor pins (the 3 mm ring around U1's VDD pins); board-edge segments; SURF cut capacity between blocks; adjacency to the solid GND plane; via sites under BGAs; top-side area.
- Valuation: each agent computes the marginal value of a resource bundle in its own budget units ([I1](intent-and-why.md#i1-physics-budget-ledger--novel-combination)); criticality weights convert to one currency ([I5](intent-and-why.md#i5-criticality-field-and-criticality-proportional-compute--novel-combination)).
- Clearing: prices rise on over-subscribed resources (history cost like PathFinder's h_n); agents re-bid their best bundles until nothing is over-subscribed or N rounds pass.
- The LLM sets agent budgets, breaks deadlocks by proposing substitutions ([N2](#n2-iso-physics-substitution-trades--new)), writes the arbitration summary ("SI outbid power for the In1 reference under DDR; power took In2 and paid with 3 extra vias").
- Output: allocations become reservations ([N5](#n5-reservation-tokens-with-confidence-hardening--new)) for placer and routers.
Evidence [I]: every production router resolves conflicts by negotiated prices ([pathfinder](../../topics/routing/pathfinder-negotiated-congestion.md)); stakeholder critic agents help but have no resolution mechanism ([analog-constraint-placement](../../topics/placement/analog-constraint-placement.md)); weighted sums hide trade-offs, clearing prices double as explanations ([I4](intent-and-why.md#i4-constraint-price-tags-and-precomputed-foils--new-for-pcb)).
Builds on: alg#152, alg#295; xd#15, xd#18; pwr: criticality map; eco#169 · Test: 20 synthetic boards with deliberate cross-domain conflict (buck beside a 16-bit ADC beside a USB3 connector beside a crystal) + 10 D3 boards; arbiters market vs weighted sum vs LLM-only vs ε-lexicographic ([N6](#n6-ε-lexicographic-objective-compiler--sharpened)); metrics per-domain PRC pass, hypervolume over domain budgets, rounds to converge · Effort/risk: M–L; currency calibration is hard and prices can oscillate: damp with PathFinder-style monotone history.

## N2. Iso-physics substitution trades — *new*

Idea: when constraints collide, trade one geometric parameter for another that keeps the protected physical quantity constant, instead of relaxing the requirement.
Mechanism: per-mechanism substitution library from the spend models:
- loop inductance: distance ↔ number of parallel vias ↔ plane depth ↔ vertical vs lateral loop;
- skew: length ↔ via-count balance ↔ per-layer delay;
- crosstalk: spacing ↔ parallel length ↔ dielectric height h;
- mounting inductance: distance ↔ via-in-pad ↔ package (0402→0201);
- return path: stitching-via distance ↔ stitching cap.
Each substitution is a typed move with a computed iso-curve, e.g. CIN may move 1.5 mm → 3 mm if a second via pair is added and L1–L2 ≤ 0.1 mm, keeping L_loop ≤ 1.2 nH. The LLM or the market searches substitutions; the checker verifies the budget invariant before acceptance.
Evidence [I]: loop inductance depends on plane distance as well as area (AN-139: 187 nH vs 13 nH for a 10 × 10 cm test loop at 27 MHz; real hot loops are 2–20 mm², SNVA803: 2 mm² < 0.5 nH) ([hot-loops](../../topics/rules/power/hot-loops.md)); mounting inductance, not capacitance value, governs decoupling ([decoupling-pdn](../../topics/rules/decoupling-pdn.md)); reduce h before adding spacing ([si-fundamentals](../../topics/rules/si-fundamentals.md)); admissible-relaxation feedback helps LLMs ([interfaces](../../topics/llm/interfaces-relations-vs-coordinates.md)).
Builds on: llm#5; alg#75; hs#22; pwr: vertical loops; [I1](intent-and-why.md#i1-physics-budget-ledger--novel-combination) · Test: boards where CP-SAT is infeasible; fraction of conflicts resolved without budget overspend by substitutions vs plain relaxation vs a human expert; also area and vias · Effort/risk: M; substitutions inherit proxy error: allow only calibrated mechanisms.

## N3. Veto-with-proof and objection budgets — *novel combination*

Idea: a domain agent (code or LLM) may block a candidate only by attaching a failing deterministic check; opinions become non-blocking annotations; a capped number of objections per round prevents deadlock.
Mechanism: objection schema {agent, check_id, measured, limit, objects, proposed_fix}; accepted only if the referee re-runs `check_id` and reproduces the failure; LLM concerns without a check go to the human brief or to [V5](verification.md#v5-counterexample-guided-rule-refinement--new) to become a new check; k objections per agent per round, upheld objections refunded, repeatedly rejected concerns lower the agent's weight.
Evidence [I]: "a model can make a repair fail but cannot make a layout pass checks it fails" ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md)); critics can be jointly wrong; field agents loop and game scores ([field-failure-modes](../../topics/ux/field-failure-modes.md)); uncertain judge findings go to a human ([critic-stack](../../topics/verification/critic-stack.md)).
Builds on: llm#53, llm#91, llm#128; prac#123, prac#132 · Test: multi-agent loop on 20 boards with vs without veto-with-proof; metrics iterations, spurious rejections (expert-labelled), final PRC pass, tokens · Effort/risk: S; real issues lacking a check could be ignored: concern routing mitigates.

## N4. Contested-rule court with precedent — *novel combination*

Idea: contested rules (20-H, copper under inductors, CIN/COUT ground separation, stitching style) become a short brief evaluating both variants on this board; a human rules; the ruling is stored as precedent and reused when the context matches.
Mechanism:
- Trigger: a recipe hits a `contested_by` field.
- Brief (≤ 1 page): both variants with sources and scope; context features (layer count, f_sw, ADC bits, enclosure); cheap T0/T1 metrics and budget spend per variant; LLM recommendation citing the selector conditions (e.g. Montrose's conditions for 20-H).
- Ruling stored as {rule family, context vector, decision, rationale, signer}.
- Reuse: on the next board the nearest precedent within a threshold applies automatically with a citation; otherwise a new brief.
Evidence [I]: contested rules must never be defaults; they need a selector plus a user choice ([myths](../../topics/rules/myths-and-contested.md), [datasheet-to-constraints](../../topics/rules/datasheet-to-constraints.md)); designers want house style and auditability ([designer-demand](../../topics/ux/designer-demand-and-trust.md)); ask only when necessary ([explanations](../../topics/ux/explanations-and-alternatives.md)).
Builds on: hs#128–129; llm#188; eco#174; prac#184 · Test: 10 consecutive boards from one team; repeated-question rate, ruling consistency, time to decision vs ad-hoc questioning · Effort/risk: S; precedents may over-generalize: the brief always lists the precedents applied.

## N5. Reservation tokens with confidence hardening — *new*

Idea: higher-priority submodules publish reservations (area, channel capacity, layer claims, meander slack, via sites) instead of frozen copper; lower tiers plan around them; upper tiers can be re-realized without losing intent.
Mechanism:
- Reservation = {owner intent, resource polygon, capacity in cut units or layer span, hardness soft/firm/locked, confidence}.
- Tier order (per recipe): hot loops → RF → SerDes and differential pairs → clocks and crystals → DDR byte lanes → analog sense → power distribution → bulk.
- Each tier runs its specialist realizer and emits reservations with slack (e.g. meander area = expected length deficit × pitch).
- Hardening: confidence rises when a reservation survives k downstream iterations or passes a T1 probe; lock only at a review gate.
- Disputes: a lower tier requests a shrink through [N1](#n1-domain-agents-in-a-resource-market--new) or [N2](#n2-iso-physics-substitution-trades--new).
Evidence [I]: experts route critical nets first and lock them ([expert-state-machine](../../topics/workflow/expert-state-machine.md), [sub-workflows](../../topics/workflow/sub-workflows-power-bga-ddr.md)); meander area should be reserved early ([length-matching](../../topics/routing/length-matching-and-buses.md)); KiCad 10 SES import deletes unlocked tracks and vias but re-adds locked ones, so critical copper existing at a Freerouting hand-off must be locked ([specctra-freerouting-integration](../../topics/kicad/specctra-freerouting-integration.md)).
Builds on: alg#200, alg#247; prac#63, prac#67; llm#346 · Test: freeze-copper flow vs reservation flow on 15 boards with DDR, USB3 and a buck; metrics completion, critical PRC pass, critical re-routes, runtime · Effort/risk: M; over-reservation kills density: tune slack with MOTPE.

## N6. ε-lexicographic objective compiler — *sharpened*

Idea: compile priority tiers into an ε-lexicographic objective for every solver: optimize tier 1, constrain later tiers to stay within ε of that optimum, optimize tier 2, ...; ε from budgets, not hand-tuned weights.
Mechanism: tiers from criticality ([I5](intent-and-why.md#i5-criticality-field-and-criticality-proportional-compute--novel-combination)) and rule strength. Per solver: CP-SAT legalizer = sequential solves with objective bounds and solution hints; analytical placer = staged penalties with barriers on earlier-tier losses; routers = per-class cost ordering. ε rule e.g. tier-1 loop L may grow until 90% of its budget. "Price of tier k" reported as in [I4](intent-and-why.md#i4-constraint-price-tags-and-precomputed-foils--new-for-pcb).
Evidence [I]: Quilter ranks candidates lexicographically ([quilter](../../topics/landscape/quilter.md)); rule tiers already exist ([rule-pack-format](../../topics/rules/rule-pack-format.md)); weighted sums need per-board tuning.
Builds on: eco#169; hs#122; prac#125 · Test: vs weighted sum with MOTPE-tuned weights on 30 boards; metrics tier-1 PRC pass, routability, tuning time · Effort/risk: S–M; too-tight ε starves later tiers; deriving ε from budgets limits this.

## N7. Hot-loop micro-placer minimizing estimated nanohenries — *new*

Idea: a specialist exact placer per recognized switching cell (buck, boost, half-bridge, flyback primary) placing IC, CIN_HF, L/SW, COUT and their vias to minimize *estimated loop inductance* (vertical-loop options included), not distance.
Mechanism:
1. Detect the cell and its hot-loop members from the topology table.
2. Enumerate discrete poses for 3–6 parts: 4 rotations, side fixed to the IC's side, 0.25 mm grid inside a 15 mm window; CP-SAT or DFS with pruning.
3. Objective L_est from loop-polygon area, depth to the first plane (stackup), via count and position; SNVA803 and EPC anchors + via-inductance formula. AN-139's 187/13 nH are for a 10 × 10 cm test loop at 27 MHz, about 10³ times a 2–20 mm² hot loop: use only qualitatively.
4. Constraints: CIN on the IC layer (integrated converters), via count and plane coverage scored through L_est, vertical loops (vias to the first inner plane) allowed; SW copper-area cap; FB parts outside the SW/L half-plane (angular-sector test); room for thermal vias.
5. Emit a template with physics slack ([P3](placement.md#p3-physics-slack-deformable-templates--new)) and an nH ledger entry.
Evidence [I]: every source ranks the hot loop first; membership derivable from topology; score nH, not mm ([hot-loops](../../topics/rules/power/hot-loops.md), [buck](../../topics/rules/power/buck.md)); no published system extracts hot loops from netlists ([checkers-power](../../topics/rules/checkers-power.md)); prior loop automation exists only for power modules with Q3D in the loop ([sides-thermal-emc-reuse](../../topics/placement/sides-thermal-emc-reuse.md)).
Builds on: pwr: topology table, inductance anchors, angular-sector test; alg#62–63; prac#31; xd#20 · Test: 30 converter instances from EVMs and open boards; L_est vs the EVM layout and a generic placer with a `loop_area` term; 5 of them vs FastHenry or openEMS extraction; metrics nH, area, overshoot estimate · Effort/risk: S–M; calibrate L_est for vertical loops on the 5 extracted cases.

## N8. Decap-to-pin assignment over mounting inductance — *new*

Idea: decoupling as min-cost assignment of capacitors to power pins and mounting sites, weighted by each pin's transient-current share and each site's mounting inductance, replacing "smallest cap closest".
Mechanism:
- Inputs: power pins with rail and estimated transient share (datasheet or labelled default); capacitors with package ESL class and DC-bias-derated value; candidate sites per pin (ring slots, bottom-side slots under a BGA, via-in-pad where allowed), each with mounting L from a pad + via + plane-depth model.
- Solve: min-cost bipartite matching or flow minimizing Σ w_pin·L_mount; small MILP when the PDN target must be met jointly.
- Check: lumped PDN screener verifies Z(f) ≤ Z_t with peaks ≤ 1.57×Z_t.
- Output: reservations for the placer + one-line reason per capacitor.
Evidence [I]: mounting inductance governs; 0.1 µF and 47 µF in the same package have equal ESL; "smallest closest" is contested ([decoupling-pdn](../../topics/rules/decoupling-pdn.md)); human decap placement is loose, only 17% within 2 mm ([measured-priors](../../topics/data/measured-priors.md)); slot assignment matters ([imitation](../../topics/data/imitation-and-learned-scores.md)).
Builds on: pwr: mounting-inductance ranking, PDN screener; prac#30; eco#115; alg#49 · Test: 20 MCU/FPGA boards vs "smallest closest" and vs the designer; metrics weighted L_mount, screener peak/Z_t, area; validate the L model on 3 boards with KiPI (AC PDN impedance; 0.9.1 alpha, unvalidated); padne is a DC solver and cannot measure inductance · Effort/risk: S; transient shares are guesses, labelled as estimates.

## N9. Ordered-chain embedder for I/O protection and RF chains — *novel combination*

Idea: chains defined by their order (connector → TVS → CMC → AC cap → PHY; antenna → match → RF IC) are placed and pre-routed as a 1-D embedding along the pair's path, with comparative constraints instead of millimetres.
Mechanism:
1. Centerline from the connector pins toward the IC (from the corridor plan, [S1](system-loop.md#s1-corridor-contract-between-placement-and-routing--novel-combination)).
2. Chain parts as ordered stations along it, in-line and symmetric with the pair.
3. Constraints: no via or stub before the TVS; GND via at the TVS pad; AC cap near one endpoint, never mid-line; match at the pin; only GND under RF.
4. Solve: DP over discrete stations, CP-SAT for spacing; realize with the PNS DP placer.
5. Output: chain macro + reservation.
Evidence [I]: TI gives TVS topology without millimetres; comparative constraints recommended ([emc-placement](../../topics/rules/emc-placement.md)); USB chain order is fixed ([usb3-usb4-typec](../../topics/rules/interfaces/usb3-usb4-typec.md)); RF geometry is fixed by module data ([rf](../../topics/rules/rf.md)); pairs route best as centerline then offset ([diff-pair-routing](../../topics/routing/diff-pair-routing.md)).
Builds on: hs#60, hs#68, hs#102–104; pwr: RF match at pin; alg#215; llm#216 · Test: 25 USB, Ethernet and RF front ends vs generic placer + Freerouting; metrics PRC pass (order, no stub before TVS, uncoupled ≤ 45 mil), time · Effort/risk: S–M; each chain is narrow, but chains recur on most boards.
