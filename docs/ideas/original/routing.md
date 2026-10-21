# Original ideas: routing

Part of the [original-ideas catalog](README.md). Shorthands as in [intent-and-why](intent-and-why.md). The baseline we assume is: escape by exact solvers, then pairs and buses via centerline A* and the PNS DP placer, then Freerouting/PathFinder bulk, then PNS repair, then DRC + SI ([recommended-stack](../../topics/solvers/recommended-stack.md)). The LLM decides topology, order and reservations. Engines realize geometry.

---

## R1. Homotopy menus for critical nets — *sharpened*

**Pitch.** Enumerate the k cheapest distinct homotopy classes for each critical net or bundle, and annotate each with its cost and cut impact. The LLM picks from this menu instead of writing free-form topology hints. SURF checks the joint choice, and PNS realizes it.

**Mechanism.**
1. Build a CDT per layer over pads, obstacles and keep-outs.
2. Find k ≈ 3–5 shortest non-homotopic rubber-band paths per net.
3. Annotate each option with:
   - length, vias and SURF cut loads;
   - reference continuity ([R2](#r2-shadow-return-nets--new));
   - a plain-words route summary, e.g. "left of U4, under the C12 cluster".
4. The LLM picks options (and optionally an order) for the top-N critical nets.
5. A joint SURF check returns any overflowing cuts, and the LLM re-picks.
6. Rubber-band waypoints feed PNS walkaround and shove.
7. The homotopy is persisted so it can be re-tightened later.

**Why it should work.**
- Spend LLM effort on homotopy, not angle ([topological-routing](../../topics/routing/topological-routing.md)).
- Bounded menus beat free-form generation (92.5% vs 6.6%) ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md)).
- PNS needs waypoints and an order supplied from outside ([kicad-pns-router](../../topics/routing/kicad-pns-router.md)).
- LLMs cannot emit copper ([llm-routing-evidence](../../topics/routing/llm-routing-evidence.md)).

**Builds on.** alg#176, alg#245, alg#251–252; xd#14; llm#52.

**How to test.** PCBWorld D3 plus the SI-constraint harness. Arms: Freerouting alone, LLM free-form hints, homotopy menu. Metrics: critical-net SI PRC pass, completion, tokens per board (target <50k).

**Effort/risk.** M. Building the homotopy engine is the cost; start with 2 layers.

---

## R2. Shadow return nets — *new*

**Pitch.** Route each fast signal together with a virtual "shadow" net on its reference plane that must stay continuous beneath it. Plane voids, splits and antipad slots become obstacles for the shadow. Every reference change needs a shadow via (a return via or a stitching cap) within budget.

**Mechanism.**
- For net n on layer L, the shadow is n's projection onto the reference plane P(L), taken from the reference map (Checker A), within a ±3h corridor.
- **Cost:** very high, or forbidden, wherever the projection hits a void or split.
- **Layer changes:** if P(L1) ≠ P(L2), the move needs a stitching via (same net) or a stitching cap (different nets) within d_max(data rate) of the signal via. That site is reserved ([R3](#r3-joint-signal-and-return-via-site-planning-in-escape--new)).
- **Differential pairs:** one shadow per leg.
- **Three implementations:**
  - a cost field in the in-house A*/PathFinder;
  - a scoring term in PNS beam search ([R8](#r8-physics-scored-beam-search-over-pns-checkpoints--sharpened));
  - the same rule as a post-route Checker B.

**Why it should work.**
- Return current flows directly under the trace (80% within ±3h for microstrip).
- Differential pairs are not self-returning ([si-fundamentals](../../topics/rules/si-fundamentals.md), [diff-pairs](../../topics/rules/diff-pairs.md)).
- Closing the loop from constraints through routing to physics checks is an unoccupied niche ([checkers-si-emi](../../topics/rules/checkers-si-emi.md)).
- An EMI-aware router is a stated practitioner wish ([trust-requirements](../../topics/workflow/trust-requirements.md)).
- A no-tools baseline passed DRC while routing through the GND plane ([kicad-ai-tools](../../topics/landscape/kicad-ai-tools-and-mcp-servers.md)).

**Builds on.** hs#2, hs#6–7, hs#12, hs#133–135; prac#78, prac#83, prac#183.

**How to test.** Use 20 boards with HS nets over imperfect planes (splits, BGA antipad slots). Compare the default Freerouting/PNS route with a shadow-aware route. Metrics: Checker B/C violations, return-via compliance, vias, completion. Run openEMS on 3 nets.

**Effort/risk.** M. Freerouting needs a fork to accept custom costs; GPL allows this.

---

## R3. Joint signal-and-return via-site planning in escape — *new*

**Pitch.** Make return vias and power vias part of the BGA/QFN escape problem, so that every reference-changing signal via has a reserved return-via site within its distance budget by construction.

**Mechanism.**
- Extend the flow/SAT escape model with typed via-site nodes: signal, ground-return, power.
- For each signal via whose layer change alters the reference plane (known from the stackup), require a ground via within d_max. Return vias share site capacity with everything else.
- Give each power pin its own via.
- Solve with MonoSAT (built with `-DGPL=OFF`) or CP-SAT on a site grid.
- An UNSAT core becomes the ECO menu in [S3](system-loop.md#s3-infeasibility-to-priced-eco-menu--novel-combination): via-in-pad, HDI, an extra layer, or a pin swap.

**Why it should work.**
- Escape is exactly solvable; MonoSAT has proved minimal layer counts ([escape-routing](../../topics/routing/escape-routing.md)).
- Return-via distance rules scale with data rate ([si-fundamentals](../../topics/rules/si-fundamentals.md)).
- Experts give every GND/VCC pin its own via ([sub-workflows](../../topics/workflow/sub-workflows-power-bga-ddr.md)).

**Builds on.** alg#181–186, alg#189; hs#7, hs#51; prac#69; eco#89.

**How to test.** On 10 open FPGA/SoC BGA boards, compare escape-then-stitch with joint planning. Metrics: return-via compliance, via count, escape completion, layers needed.

**Effort/risk.** M. Large BGAs give large models; window by quadrant.

---

## R4. Regret-driven re-prioritization — *sharpened*

**Pitch.** Compute each critical net's regret: its realized budget spend minus its solo-optimal spend on an otherwise empty board. The LLM then bumps priorities, reservations or topologies only for nets with high regret and high criticality.

**Mechanism.**
1. Solo-route each top-N net with placement and planes present but no other signals.
2. regret = spend_actual − spend_solo, in ledger units ([I1](intent-and-why.md#i1-physics-budget-ledger--novel-combination)).
3. Culprits = the nets occupying the solo path.
4. Show the table {net, criticality, regret, culprits}.
5. Bounded actions:
   - raise the net's tier;
   - reserve its solo corridor;
   - swap its order with a culprit;
   - choose another homotopy ([R1](#r1-homotopy-menus-for-critical-nets--sharpened)).

The procedure is deterministic, with no sampled look-ahead.

**Why it should work.**
- Order decides who gets the good resources, and the LLM should see quantified conflicts ([net-ordering](../../topics/routing/net-ordering.md)).
- In PCBWorld the first net often decides success ([pcbworld](../../topics/routing/pcbworld.md)).
- InstaDeep's patents claim NN-guided SMC look-ahead over orders; deterministic regret avoids that ([patents](../../topics/landscape/patents-watchlist.md)).

**Builds on.** alg#222–226; eco#87; llm#118.

**How to test.** On D3-B and synthetic dense boards, compare a fixed order with negotiation against the regret loop (≤3 rounds). Metrics: critical budget compliance, completion, tokens.

**Effort/risk.** S. Solo routes are optimistic, but that is fine for ranking.

---

## R5. Router-portfolio bandit — *sharpened*

**Pitch.** Run several engines per net class or stage (Freerouting, KRT, PNS beam, in-house PathFinder), and learn across boards which engine wins in which context. Dispatch improves with use.

**Mechanism.**
- **Context:** net class, pin count, local density, layer count, region type (BGA, connector, open) and the constraints present.
- **Arms:** engine × preset.
- **Reward:** a lexicographic referee score (validity → PRC → vias and length).
- **Policy:** Thompson sampling, with LLM-set presets as the prior and an exploration budget per board.
- **Logs** feed offline evolution ([L2](learning-and-data.md#l2-evolve-the-conductor--novel-combination)).

**Why it should work.**
- One engine per net class is recommended ([recommended-stack](../../topics/solvers/recommended-stack.md)).
- Practitioners already run tournaments of routers ([llm-field-reports](../../topics/workflow/llm-field-reports.md)).
- Freerouting does not route pairs; KRT is the fastest ([freerouting](../../topics/routing/freerouting.md)).

**Builds on.** alg#334; eco#69, eco#88; prac#74.

**How to test.** Measure regret against the best fixed engine per class over 100 D3 boards, using a time split, and record compute cost.

**Effort/risk.** S–M. Region-split routing creates boundary conflicts, so start by dispatching per stage.

---

## R6. Verified routing macros attached to recipes — *novel combination*

**Pitch.** Ship small parametric copper generators for recurring structures, each verified by its PRCs and instanced before bulk routing. Examples: decap fanout, a Kelvin sense pair, a TVS-at-pad ESD entry, a crystal guard, a hot-loop polygon, an AC-cap diff-pair breakout, a thermal via array.

**Mechanism.** Each macro has four parts:
- a precondition (a recipe instance plus a geometry pattern);
- parameters derived from the stackup and budgets (via size and count, width from current);
- a deterministic generator that emits tracks, vias and zones in one IPC commit;
- postconditions, which are the layout unit tests of [V1](verification.md#v1-mutation-tested-layout-unit-tests--new).

The result is placed as locked or reserved copper. The LLM picks a macro per recipe instance from a menu; it never draws copper itself.

**Why it should work.**
- A deterministic move library closed the last routing dead ends ([agent-tooling-reliability](../../topics/ux/agent-tooling-reliability-patterns.md)).
- Fan-out rules are crisp and well defined ([placement-methodology](../../topics/rules/placement-methodology.md)).
- Net ties force Kelvin connections ([current-sense-kelvin](../../topics/rules/power/current-sense-kelvin.md)).
- An LLM tool earns trust by doing the delegable work perfectly first ([delegation](../../topics/workflow/delegation-and-expert-review.md)).

**Builds on.** pwr: fan-out generator, net ties, EP via arrays; llm#339; eco#91; hs#145.

**How to test.** On 200 instances, compare macros with PNS and with Freerouting. Metrics: PRC pass, reviewer acceptance, time.

**Effort/risk.** S per macro. Cross-version maintenance is a risk, so all transforms go through one oracle-tested module.

---

## R7. Plane-partition synthesis coupled to the reference map — *new*

**Pitch.** Generate the inner-layer power-plane partitions by optimization: which rail gets which region, where splits and necks go. The result must meet IR-drop and current-density limits while forbidding splits under the planned paths of fast nets.

**Mechanism.**
- **Inputs:** rails with their loads and sources; fast-net corridors from [S1](system-loop.md#s1-corridor-contract-between-placement-and-routing--novel-combination) and [R1](#r1-homotopy-menus-for-critical-nets--sharpened); the stackup.
- **Variables:** the rail (or GND) assigned to each coarse grid cell on each plane layer.
- **Objective terms:**
  - IR drop and narrowest cross-section per rail, from a resistive network or padne;
  - a penalty wherever a fast-net corridor crosses a partition boundary on its reference layer;
  - penalties for slivers and cavity resonance.
- **Solve:** graph-cut or CP-SAT, then smooth to polygons and emit KiCad zones.
- **Re-check** with Checkers A and B.

**Why it should work.**
- Commercial tools have a pour-and-plane planning stage ([quilter](../../topics/landscape/quilter.md)).
- Signals must not cross splits or reference power planes needlessly ([si-fundamentals](../../topics/rules/si-fundamentals.md)).
- There is a narrowest-cross-section check ([high-current](../../topics/rules/power/high-current.md)), but no open PDN tool ([decoupling-pdn](../../topics/rules/decoupling-pdn.md)).

**Builds on.** eco#91, eco#136; pwr: narrowest cross-section; hs#9; prac#81.

**How to test.** On 10 boards with 4–6 layers and multiple rails, compare against the designer's planes and a naive Voronoi split. Metrics: padne IR drop, split-crossing count.

**Effort/risk.** M–L. Plane shapes and routing depend on each other, so iterate twice with routing.

---

## R8. Physics-scored beam search over PNS checkpoints — *sharpened*

**Pitch.** Use PCBWorld-Engine checkpoints to beam-search PNS realizations of a chosen topology. Score partial routes by budget spend (loss, skew, return continuity, via budget), and set the beam width from criticality.

**Mechanism.**
- **State:** a PNS checkpoint.
- **Actions:** waypoint shifts along the homotopy; layer choice at allowed transitions; walkaround vs shove mode; via candidates.
- **Score:** ledger spend plus shadow feasibility ([R2](#r2-shadow-return-nets--new)) plus disturbance to locked or reserved items.
- **Beam width:** set by criticality ([I5](intent-and-why.md#i5-criticality-field-and-criticality-proportional-compute--novel-combination)).
- **Finish:** PNS smoothing, then the meander engine inside the reserved area.

The search is deterministic, with no learned guidance, which keeps clear of the InstaDeep claims.

**Why it should work.**
- PNS is a realizer that needs a planner.
- PCBWorld-Engine is checkpointable ([kicad-pns-router](../../topics/routing/kicad-pns-router.md)).
- Beam search over PNS is already listed (alg#239), but without physics scoring.

**Builds on.** alg#239, alg#251–252; eco#79.

**How to test.** On critical nets of D3 and synthetic SerDes boards, compare single-shot PNS with beam widths 1, 4 and 16. Metrics: PRC pass, time.

**Effort/risk.** M. Porting PCBWorld-Engine to KiCad 10/11 has unknown maintenance cost.
