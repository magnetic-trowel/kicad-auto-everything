# Original ideas: priority submodules, arbitration and specialist solvers

Part of the [original-ideas catalog](README.md). These ideas answer the request for submodules with different priorities: power conversion, high-speed and differential pairs, RF, EMI, and parts that must sit next to each other. Shorthands as in [intent-and-why](intent-and-why.md): `alg#`, `llm#`, `prac#`, `eco#`, `hs#`, `pwr:`, `xd#`.

Design stance: a domain submodule is deterministic code, made of a recipe pack, a critic and a specialist realizer. The LLM funds, arbitrates and explains; it does not do the geometry.

---

## N1. Domain agents in a resource market — *new*

**Pitch.** Power, SI, RF, EMC, thermal, DFM and mechanical submodules buy contested board resources with credits funded by criticality. An ascending-price auction clears the bids. This generalizes PathFinder's negotiated congestion from nets to domains, and from routing to placement.

**Mechanism.**
- **Resources:**
  - placement cells near anchor pins (the 3 mm ring around U1's VDD pins);
  - board-edge segments;
  - SURF cut capacity between blocks;
  - adjacency to the solid GND plane;
  - via sites under BGAs;
  - top-side area.
- **Valuation:** each agent computes the marginal value of a resource bundle in its own budget units ([I1](intent-and-why.md#i1-physics-budget-ledger--novel-combination)). Criticality weights convert these to one currency ([I5](intent-and-why.md#i5-criticality-field-and-criticality-proportional-compute--novel-combination)).
- **Clearing:** prices rise on over-subscribed resources (a history cost like PathFinder's h_n). Agents re-bid their best bundles until nothing is over-subscribed or N rounds pass.
- **The LLM** sets agent budgets, breaks deadlocks by proposing substitutions ([N2](#n2-iso-physics-substitution-trades--new)), and writes the arbitration summary. Example: "SI outbid power for the In1 reference under DDR; power took In2 and paid with 3 extra vias."
- **Output:** allocations become reservations ([N5](#n5-reservation-tokens-with-confidence-hardening--new)) for the placer and routers.

**Why it should work.**
- Every production router resolves conflicts by negotiated prices ([pathfinder](../../topics/routing/pathfinder-negotiated-congestion.md)).
- Stakeholder critic agents help but have no resolution mechanism ([analog-constraint-placement](../../topics/placement/analog-constraint-placement.md)).
- Weighted sums hide trade-offs, whereas clearing prices double as explanations ([I4](intent-and-why.md#i4-constraint-price-tags-and-precomputed-foils--new-for-pcb)).

**Builds on.** alg#152, alg#295; xd#15, xd#18; pwr: criticality map; eco#169.

**How to test.** Build 20 synthetic boards with deliberate cross-domain conflict (buck beside a 16-bit ADC beside a USB3 connector beside a crystal), plus 10 D3 boards. Compare four arbiters: the market, a weighted sum, LLM-only arbitration, and ε-lexicographic ([N6](#n6-ε-lexicographic-objective-compiler--sharpened)). Metrics: per-domain PRC pass, hypervolume over domain budgets, and rounds to converge.

**Effort/risk.** M–L. Currency calibration is hard, and prices can oscillate; damp them with PathFinder-style monotone history.

---

## N2. Iso-physics substitution trades — *new*

**Pitch.** When constraints collide, trade one geometric parameter for another that keeps the protected physical quantity constant, rather than relaxing the requirement.

**Mechanism.** Each mechanism gets a substitution library derived from its spend models:
- **loop inductance:** distance ↔ number of parallel vias ↔ plane depth ↔ vertical vs lateral loop;
- **skew:** length ↔ via-count balance ↔ per-layer delay;
- **crosstalk:** spacing ↔ parallel length ↔ dielectric height h;
- **mounting inductance:** distance ↔ via-in-pad ↔ package (0402→0201);
- **return path:** stitching-via distance ↔ stitching cap.

Each substitution is a typed move with a computed iso-curve. Example: CIN may move from 1.5 mm to 3 mm if a second via pair is added and L1–L2 ≤ 0.1 mm, keeping L_loop ≤ 1.2 nH. The LLM or the market searches substitutions, and the checker verifies the budget invariant before acceptance.

**Why it should work.**
- Loop inductance depends on plane distance as well as area (187 nH vs 13 nH) ([hot-loops](../../topics/rules/power/hot-loops.md)).
- Mounting inductance, not capacitance value, governs decoupling ([decoupling-pdn](../../topics/rules/decoupling-pdn.md)).
- Reduce h before adding spacing ([si-fundamentals](../../topics/rules/si-fundamentals.md)).
- Admissible-relaxation feedback helps LLMs ([interfaces](../../topics/llm/interfaces-relations-vs-coordinates.md)).

**Builds on.** llm#5; alg#75; hs#22; pwr: vertical loops; [I1](intent-and-why.md#i1-physics-budget-ledger--novel-combination).

**How to test.** Take boards where CP-SAT is infeasible. Measure the fraction of conflicts each approach resolves without budget overspend: substitutions, plain relaxation, and a human expert. Also measure area and vias.

**Effort/risk.** M. Substitutions inherit proxy error, so allow only calibrated mechanisms.

---

## N3. Veto-with-proof and objection budgets — *novel combination*

**Pitch.** A domain agent, whether code or LLM, may block a candidate only by attaching a failing deterministic check. Opinions become non-blocking annotations. Each agent also has a capped number of objections per round, which prevents deadlock.

**Mechanism.**
- Objection schema: {agent, check_id, measured, limit, objects, proposed_fix}.
- An objection is accepted only if the referee re-runs `check_id` and reproduces the failure.
- LLM concerns without a check go to the human brief, or to [V5](verification.md#v5-counterexample-guided-rule-refinement--new) to become a new check.
- Each agent may raise k objections per round. Upheld objections are refunded. Repeatedly rejected concerns lower the agent's weight.

**Why it should work.**
- "A model can make a repair fail but cannot make a layout pass checks it fails" ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md)).
- Critics can be jointly wrong.
- Field agents loop and game scores ([field-failure-modes](../../topics/ux/field-failure-modes.md)).
- Uncertain judge findings go to a human ([critic-stack](../../topics/verification/critic-stack.md)).

**Builds on.** llm#53, llm#91, llm#128; prac#123, prac#132.

**How to test.** Run a multi-agent loop on 20 boards with and without veto-with-proof. Metrics: iterations, spurious rejections (expert-labelled), final PRC pass, and tokens.

**Effort/risk.** S. Real issues that lack a check could be ignored; concern routing mitigates this.

---

## N4. Contested-rule court with precedent — *novel combination*

**Pitch.** Contested rules (20-H, copper under inductors, CIN/COUT ground separation, stitching style) become a short brief. The brief evaluates both variants on this board, a human rules, and the ruling is stored as precedent and reused automatically when the context matches.

**Mechanism.**
- **Trigger:** a recipe hits a `contested_by` field.
- **The brief** (one page or less) contains:
  - both variants with their sources and scope;
  - context features (layer count, f_sw, ADC bits, enclosure);
  - cheap T0/T1 metrics and budget spend for each variant;
  - an LLM recommendation that cites the selector conditions (for example Montrose's conditions for 20-H).
- **Ruling** stored as {rule family, context vector, decision, rationale, signer}.
- **Reuse:** on the next board, the nearest precedent within a threshold applies automatically with a citation; otherwise a new brief is raised.

**Why it should work.**
- Contested rules must never be defaults and need a selector plus a user choice ([myths](../../topics/rules/myths-and-contested.md), [datasheet-to-constraints](../../topics/rules/datasheet-to-constraints.md)).
- Designers want house style and auditability ([designer-demand](../../topics/ux/designer-demand-and-trust.md)).
- Ask only when necessary ([explanations](../../topics/ux/explanations-and-alternatives.md)).

**Builds on.** hs#128–129; llm#188; eco#174; prac#184.

**How to test.** Over a sequence of 10 boards from one team, measure the repeated-question rate, consistency of rulings, and time to decision. Compare with ad-hoc questioning.

**Effort/risk.** S. Precedents may over-generalize, so the brief always lists which precedents were applied.

---

## N5. Reservation tokens with confidence hardening — *new*

**Pitch.** Higher-priority submodules publish reservations (area, channel capacity, layer claims, meander slack, via sites) instead of frozen copper. Lower tiers plan around them, and upper tiers can still be re-realized without losing intent.

**Mechanism.**
- **Reservation** = {owner intent, resource as polygon, capacity in cut units or layer span, hardness soft/firm/locked, confidence}.
- **Tier order, set per recipe:** hot loops → RF → SerDes and differential pairs → clocks and crystals → DDR byte lanes → analog sense → power distribution → bulk.
- **Each tier** runs its specialist realizer and emits reservations with slack (for example, meander area = expected length deficit × pitch).
- **Hardening:** confidence rises when a reservation survives k downstream iterations or passes a T1 probe. Reservations lock only at a review gate.
- **Disputes:** a lower tier can request a shrink through [N1](#n1-domain-agents-in-a-resource-market--new) or [N2](#n2-iso-physics-substitution-trades--new).

**Why it should work.**
- Experts route critical nets first and lock them ([expert-state-machine](../../topics/workflow/expert-state-machine.md), [sub-workflows](../../topics/workflow/sub-workflows-power-bga-ddr.md)).
- Meander area should be reserved early ([length-matching](../../topics/routing/length-matching-and-buses.md)).
- KiCad 10 SES import deletes unlocked copper, so frozen-copper flows are brittle ([specctra-freerouting-integration](../../topics/kicad/specctra-freerouting-integration.md)).

**Builds on.** alg#200, alg#247; prac#63, prac#67; llm#346.

**How to test.** Compare a freeze-copper flow with a reservation flow on 15 boards with DDR, USB3 and a buck converter. Metrics: completion, critical PRC pass, critical re-routes, runtime.

**Effort/risk.** M. Over-reservation kills density, so tune the slack with MOTPE.

---

## N6. ε-lexicographic objective compiler — *sharpened*

**Pitch.** Compile priority tiers into an ε-lexicographic objective for every solver. Optimize tier 1, constrain later tiers to stay within ε of that optimum, then optimize tier 2, and so on. ε comes from budgets rather than hand-tuned weights.

**Mechanism.**
- **Tiers** come from criticality ([I5](intent-and-why.md#i5-criticality-field-and-criticality-proportional-compute--novel-combination)) and rule strength.
- **Per solver:**
  - CP-SAT legalizer: sequential solves with objective bounds and solution hints;
  - analytical placer: staged penalties with barriers on earlier-tier losses;
  - routers: per-class cost ordering.
- **ε rule:** for example, let tier-1 loop L grow until it reaches 90% of its budget.
- **Price:** the "price of tier k" is reported as in [I4](intent-and-why.md#i4-constraint-price-tags-and-precomputed-foils--new-for-pcb).

**Why it should work.**
- Quilter ranks candidates lexicographically ([quilter](../../topics/landscape/quilter.md)).
- Rule tiers already exist ([rule-pack-format](../../topics/rules/rule-pack-format.md)).
- Weighted sums need per-board tuning.

**Builds on.** eco#169; hs#122; prac#125.

**How to test.** Compare against a weighted sum with MOTPE-tuned weights on 30 boards. Metrics: tier-1 PRC pass, routability, tuning time.

**Effort/risk.** S–M. An ε that is too tight starves later tiers; deriving ε from budgets limits this.

---

## N7. Hot-loop micro-placer minimizing estimated nanohenries — *new*

**Pitch.** A specialist exact placer for each recognized switching cell (buck, boost, half-bridge, flyback primary). It places the IC, CIN_HF, L/SW, COUT and their vias to minimize *estimated loop inductance*, including vertical-loop options, rather than distance.

**Mechanism.**
1. Detect the cell and its hot-loop members from the topology table.
2. Enumerate discrete poses for 3–6 parts: 4 rotations, side fixed to the IC's side, a 0.25 mm grid inside a 15 mm window. Use CP-SAT, or DFS with pruning.
3. Objective: L_est from loop-polygon area, depth to the first plane (from the stackup), and via count and position. Use the AN-139, SNVA803 and EPC anchors plus the via-inductance formula.
4. Constraints:
   - CIN on the IC layer, with no vias in the hot loop;
   - an SW copper-area cap;
   - FB parts outside the SW/L half-plane (angular-sector test);
   - room for thermal vias.
5. Emit a template with physics slack ([P3](placement.md#p3-physics-slack-deformable-templates--new)) and a nH ledger entry.

**Why it should work.**
- Every source ranks the hot loop first; membership is derivable from topology; score nH, not mm ([hot-loops](../../topics/rules/power/hot-loops.md), [buck](../../topics/rules/power/buck.md)).
- No published system extracts hot loops from netlists ([checkers-power](../../topics/rules/checkers-power.md)).
- Prior loop automation exists only for power modules with Q3D in the loop ([sides-thermal-emc-reuse](../../topics/placement/sides-thermal-emc-reuse.md)).

**Builds on.** pwr: topology table, inductance anchors, angular-sector test; alg#62–63; prac#31; xd#20.

**How to test.** Use 30 converter instances from EVMs and open boards. Compare L_est against the EVM layout and a generic placer with a `loop_area` term. For 5 of them, compare with FastHenry or openEMS extraction. Metrics: nH, area, overshoot estimate.

**Effort/risk.** S–M. Calibrate L_est for vertical loops on the 5 extracted cases.

---

## N8. Decap-to-pin assignment over mounting inductance — *new*

**Pitch.** Decoupling becomes a min-cost assignment of capacitors to power pins and mounting sites. It is weighted by each pin's transient-current share and each site's mounting inductance, replacing "smallest cap closest".

**Mechanism.**
- **Inputs:**
  - power pins with their rail and estimated transient share (from the datasheet or a labelled default);
  - capacitors with their package ESL class and DC-bias-derated value;
  - candidate sites per pin (ring slots, bottom-side slots under a BGA, via-in-pad where allowed), each with a mounting L from a pad + via + plane-depth model.
- **Solve:** min-cost bipartite matching or flow minimizing Σ w_pin·L_mount. Use a small MILP when the PDN target must be met jointly.
- **Check:** a lumped PDN screener verifies Z(f) ≤ Z_t with peaks ≤ 1.57×Z_t.
- **Output:** reservations for the placer and a one-line reason per capacitor.

**Why it should work.**
- Mounting inductance governs; 0.1 µF and 47 µF in the same package have equal ESL; "smallest closest" is contested ([decoupling-pdn](../../topics/rules/decoupling-pdn.md)).
- Human decap placement is loose: only 17% sit within 2 mm ([measured-priors](../../topics/data/measured-priors.md)).
- Slot assignment matters ([imitation](../../topics/data/imitation-and-learned-scores.md)).

**Builds on.** pwr: mounting-inductance ranking, PDN screener; prac#30; eco#115; alg#49.

**How to test.** On 20 MCU/FPGA boards, compare against "smallest closest" and against the designer. Metrics: weighted L_mount, screener peak/Z_t, area. Validate the L model on 3 boards with padne or KiPI.

**Effort/risk.** S. Transient shares are guesses and are labelled as estimates.

---

## N9. Ordered-chain embedder for I/O protection and RF chains — *novel combination*

**Pitch.** Some chains are defined by their order: connector → TVS → CMC → AC cap → PHY, or antenna → match → RF IC. Place and pre-route them as a 1-D embedding along the pair's path, with comparative constraints instead of millimetres.

**Mechanism.**
1. Choose a centerline from the connector pins toward the IC (from the corridor plan, [S1](system-loop.md#s1-corridor-contract-between-placement-and-routing--novel-combination)).
2. Place the chain parts as ordered stations along it, in-line and symmetric with the pair.
3. Constraints:
   - no via or stub before the TVS;
   - a GND via at the TVS pad;
   - the AC cap near one endpoint, never mid-line;
   - the match at the pin;
   - only GND under RF.
4. Solve with DP over discrete stations, CP-SAT for spacing, and realize with the PNS DP placer.
5. Output a chain macro plus a reservation.

**Why it should work.**
- TI gives TVS topology without millimetres; comparative constraints are recommended ([emc-placement](../../topics/rules/emc-placement.md)).
- USB chain order is fixed ([usb3-usb4-typec](../../topics/rules/interfaces/usb3-usb4-typec.md)).
- RF geometry is fixed by module data ([rf](../../topics/rules/rf.md)).
- Pairs route best as centerline then offset ([diff-pair-routing](../../topics/routing/diff-pair-routing.md)).

**Builds on.** hs#60, hs#68, hs#102–104; pwr: RF match at pin; alg#215; llm#216.

**How to test.** On 25 USB, Ethernet and RF front ends, compare against a generic placer plus Freerouting. Metrics: PRC pass (order, no stub before TVS, uncoupled ≤45 mil) and time.

**Effort/risk.** S–M. Each chain is narrow, but chains recur on most boards.
