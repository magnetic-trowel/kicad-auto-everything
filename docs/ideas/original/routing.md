# Original ideas: routing

Scope: R1–R8; the LLM decides topology, order and reservations, engines realize geometry. Part of the [original-ideas catalog](README.md); shorthands as in [intent-and-why](intent-and-why.md). Baseline: escape by exact solvers → pairs and buses via centerline A* and the PNS DP placer → Freerouting/PathFinder bulk → PNS repair → DRC + SI ([recommended-stack](../../topics/solvers/recommended-stack.md)). Test status: [research/ideas](../../research/ideas.md#original-ideas-58).
Keys: R1 homotopy menus, R2 shadow return nets, R3 joint signal/return via sites, R4 regret-driven priorities, R5 router-portfolio bandit, R6 verified routing macros, R7 plane-partition synthesis, R8 physics-scored PNS beam search

## R1. Homotopy menus for critical nets — *sharpened*

Idea: enumerate the k cheapest distinct homotopy classes per critical net or bundle, annotated with cost and cut impact; the LLM picks from this menu instead of writing free-form topology hints; SURF checks the joint choice; PNS realizes it.
Mechanism:
1. CDT per layer over pads, obstacles, keep-outs.
2. k ≈ 3–5 shortest non-homotopic rubber-band paths per net.
3. Annotate each: length, vias, SURF cut loads; reference continuity ([R2](#r2-shadow-return-nets--new)); plain-words summary ("left of U4, under the C12 cluster").
4. The LLM picks options (optionally an order) for the top-N critical nets.
5. Joint SURF check returns overflowing cuts; the LLM re-picks.
6. Rubber-band waypoints feed PNS walkaround and shove.
7. Homotopy persisted for later re-tightening.
Evidence [I]: spend LLM effort on homotopy, not angle ([topological-routing](../../topics/routing/topological-routing.md)); bounded menus beat free-form generation (DRC-Aid on IC layouts: 92.5% vs 6.6%) ([agent-loop-patterns](../../topics/llm/agent-loop-patterns.md)); PNS needs waypoints and an order supplied from outside ([kicad-pns-router](../../topics/routing/kicad-pns-router.md)); LLMs cannot emit copper ([llm-routing-evidence](../../topics/routing/llm-routing-evidence.md)).
Builds on: alg#176, alg#245, alg#251–252; xd#14; llm#52 · Test: PCBWorld D3 + the SI-constraint harness; arms Freerouting alone vs LLM free-form hints vs homotopy menu; metrics critical-net SI PRC pass, completion, tokens per board (target < 50k) · Effort/risk: M; the homotopy engine is the cost: start with 2 layers.

## R2. Shadow return nets — *new*

Idea: route each fast signal with a virtual "shadow" net on its reference plane that must stay continuous beneath it; voids, splits and antipad slots are obstacles for the shadow; every reference change needs a shadow via (return via or stitching cap) within budget.
Mechanism:
- Shadow of net n on layer L = projection onto reference plane P(L) (from the reference map, Checker A) within a ±3h corridor.
- Cost very high, or forbidden, where the projection hits a void or split.
- Layer change with P(L1) ≠ P(L2) needs a stitching via (same net) or stitching cap (different nets) within d_max(data rate) of the signal via; that site is reserved ([R3](#r3-joint-signal-and-return-via-site-planning-in-escape--new)).
- Differential pairs: one shadow per leg.
- Implementations: cost field in the in-house A*/PathFinder; scoring term in PNS beam search ([R8](#r8-physics-scored-beam-search-over-pns-checkpoints--sharpened)); the same rule as post-route Checker B.
Evidence [I]: return current flows directly under the trace (80% within ±3h for microstrip); differential pairs are not self-returning ([si-fundamentals](../../topics/rules/si-fundamentals.md), [diff-pairs](../../topics/rules/diff-pairs.md)); closing the loop constraints → routing → physics check is an unoccupied niche ([checkers-si-emi](../../topics/rules/checkers-si-emi.md)); an EMI-aware router is a stated practitioner wish ([trust-requirements](../../topics/workflow/trust-requirements.md)); a no-tools baseline passed DRC while routing through the GND plane ([kicad-ai-tools](../../topics/landscape/kicad-ai-tools-and-mcp-servers.md)).
Builds on: hs#2, hs#6–7, hs#12, hs#133–135; prac#78, prac#83, prac#183 · Test: 20 boards with HS nets over imperfect planes (splits, BGA antipad slots); default Freerouting/PNS route vs shadow-aware route; metrics Checker B/C violations, return-via compliance, vias, completion; openEMS on 3 nets · Effort/risk: M; Freerouting needs a fork to accept custom costs (GPL allows this).

## R3. Joint signal-and-return via-site planning in escape — *new*

Idea: return vias and power vias become part of the BGA/QFN escape problem, so every reference-changing signal via has a reserved return-via site within its distance budget by construction.
Mechanism:
- Flow/SAT escape model with typed via-site nodes: signal, ground-return, power.
- Each signal via whose layer change alters the reference plane (from the stackup) requires a ground via within d_max; return vias share site capacity with everything else.
- Each power pin gets its own via.
- Solve with MonoSAT (built with `-DGPL=OFF`) or CP-SAT on a site grid.
- UNSAT core → ECO menu of [S3](system-loop.md#s3-infeasibility-to-priced-eco-menu--novel-combination): via-in-pad, HDI, extra layer, pin swap.
Evidence [I]: escape is exactly solvable; MonoSAT has proved minimal layer counts ([escape-routing](../../topics/routing/escape-routing.md)); return-via distance rules scale with data rate ([si-fundamentals](../../topics/rules/si-fundamentals.md)); experts give every GND/VCC pin its own via ([sub-workflows](../../topics/workflow/sub-workflows-power-bga-ddr.md)).
Builds on: alg#181–186, alg#189; hs#7, hs#51; prac#69; eco#89 · Test: 10 open FPGA/SoC BGA boards, escape-then-stitch vs joint planning; metrics return-via compliance, via count, escape completion, layers needed · Effort/risk: M; large BGAs give large models: window by quadrant.

## R4. Regret-driven re-prioritization — *sharpened*

Idea: each critical net's regret = realized budget spend − solo-optimal spend on an otherwise empty board; the LLM bumps priorities, reservations or topologies only for high-regret, high-criticality nets.
Mechanism:
1. Solo-route each top-N net with placement and planes present, no other signals.
2. regret = spend_actual − spend_solo, in ledger units ([I1](intent-and-why.md#i1-physics-budget-ledger--novel-combination)).
3. Culprits = nets occupying the solo path.
4. Table {net, criticality, regret, culprits}.
5. Bounded actions: raise the net's tier; reserve its solo corridor; swap order with a culprit; choose another homotopy ([R1](#r1-homotopy-menus-for-critical-nets--sharpened)).
Deterministic, no sampled look-ahead.
Evidence [I]: order decides who gets the good resources; the LLM should see quantified conflicts ([net-ordering](../../topics/routing/net-ordering.md)); in PCBWorld the first net often decides success ([pcbworld](../../topics/routing/pcbworld.md)); InstaDeep's patents claim NN-guided SMC look-ahead over orders; deterministic regret avoids that ([patents](../../topics/landscape/patents-watchlist.md)).
Builds on: alg#222–226; eco#87; llm#118 · Test: D3-B + synthetic dense boards, fixed order with negotiation vs regret loop (≤ 3 rounds); metrics critical budget compliance, completion, tokens · Effort/risk: S; solo routes are optimistic, fine for ranking.

## R5. Router-portfolio bandit — *sharpened*

Idea: run several engines per net class or stage (Freerouting, KRT, PNS beam, in-house PathFinder) and learn across boards which engine wins in which context.
Mechanism: context = net class, pin count, local density, layer count, region type (BGA, connector, open), constraints present; arms = engine × preset; reward = lexicographic referee score (validity → PRC → vias and length); policy = Thompson sampling with LLM-set presets as prior and a per-board exploration budget; logs feed offline evolution ([L2](learning-and-data.md#l2-evolve-the-conductor--novel-combination)).
Evidence [I]: one engine per net class is recommended ([recommended-stack](../../topics/solvers/recommended-stack.md)); practitioners already run router tournaments ([llm-field-reports](../../topics/workflow/llm-field-reports.md)); Freerouting does not route pairs; KRT is the fastest ([freerouting](../../topics/routing/freerouting.md)).
Builds on: alg#334; eco#69, eco#88; prac#74 · Test: regret vs the best fixed engine per class over 100 D3 boards outside PCBWorld's 99 + 10 evaluation set, time split; record compute cost · Effort/risk: S–M; region-split routing creates boundary conflicts: start by dispatching per stage.

## R6. Verified routing macros attached to recipes — *novel combination*

Idea: small parametric copper generators for recurring structures, each verified by its PRCs and instanced before bulk routing (decap fanout, Kelvin sense pair, TVS-at-pad ESD entry, crystal guard, hot-loop polygon, AC-cap diff-pair breakout, thermal via array).
Mechanism: macro = precondition (recipe instance + geometry pattern) + parameters from stackup and budgets (via size and count, width from current) + deterministic generator emitting tracks, vias, zones in one IPC commit + postconditions (the layout unit tests of [V1](verification.md#v1-mutation-tested-layout-unit-tests--new)). Placed as locked or reserved copper. The LLM picks a macro per recipe instance from a menu, never draws copper.
Evidence [I]: a deterministic move library closed the last routing dead ends ([agent-tooling-reliability](../../topics/ux/agent-tooling-reliability-patterns.md)); fan-out rules are crisp ([placement-methodology](../../topics/rules/placement-methodology.md)); net ties force Kelvin connections ([current-sense-kelvin](../../topics/rules/power/current-sense-kelvin.md)); an LLM tool earns trust by doing delegable work perfectly first ([delegation](../../topics/workflow/delegation-and-expert-review.md)).
Builds on: pwr: fan-out generator, net ties, EP via arrays; llm#339; eco#91; hs#145 · Test: 200 instances, macros vs PNS vs Freerouting; metrics PRC pass, reviewer acceptance, time · Effort/risk: S per macro; cross-version maintenance risk: all transforms through one oracle-tested module.

## R7. Plane-partition synthesis coupled to the reference map — *new*

Idea: generate inner-layer power-plane partitions by optimization (which rail gets which region, where splits and necks go), meeting IR-drop and current-density limits and forbidding splits under the planned paths of fast nets.
Mechanism:
- Inputs: rails with loads and sources; fast-net corridors from [S1](system-loop.md#s1-corridor-contract-between-placement-and-routing--novel-combination) and [R1](#r1-homotopy-menus-for-critical-nets--sharpened); stackup.
- Variables: rail (or GND) per coarse grid cell per plane layer.
- Objective: IR drop and narrowest cross-section per rail (resistive network or padne); penalty where a fast-net corridor crosses a partition boundary on its reference layer; penalties for slivers and cavity resonance.
- Solve: graph-cut or CP-SAT, smooth to polygons, emit KiCad zones; re-check with Checkers A and B.
Evidence [I]: commercial tools have a pour-and-plane planning stage ([quilter](../../topics/landscape/quilter.md)); signals must not cross splits or reference power planes needlessly ([si-fundamentals](../../topics/rules/si-fundamentals.md)); a narrowest-cross-section check exists ([high-current](../../topics/rules/power/high-current.md)) but no open PDN tool ([decoupling-pdn](../../topics/rules/decoupling-pdn.md)).
Builds on: eco#91, eco#136; pwr: narrowest cross-section; hs#9; prac#81 · Test: 10 boards, 4–6 layers, multiple rails, vs designer's planes and a naive Voronoi split; metrics padne IR drop, split-crossing count · Effort/risk: M–L; plane shapes and routing depend on each other: iterate twice with routing.

## R8. Physics-scored beam search over PNS checkpoints — *sharpened*

Idea: beam-search PNS realizations of a chosen topology from PCBWorld-Engine checkpoints, scoring partial routes by budget spend (loss, skew, return continuity, via budget), beam width from criticality.
Mechanism: state = PNS checkpoint; actions = waypoint shifts along the homotopy, layer choice at allowed transitions, walkaround vs shove, via candidates; score = ledger spend + shadow feasibility ([R2](#r2-shadow-return-nets--new)) + disturbance to locked or reserved items; beam width from criticality ([I5](intent-and-why.md#i5-criticality-field-and-criticality-proportional-compute--novel-combination)); finish with PNS smoothing, then the meander engine inside the reserved area. Deterministic, no learned guidance (keeps clear of the InstaDeep claims).
Evidence [I]: PNS is a realizer that needs a planner; PCBWorld-Engine is checkpointable ([kicad-pns-router](../../topics/routing/kicad-pns-router.md)); beam search over PNS is already listed (alg#239) but without physics scoring.
Builds on: alg#239, alg#251–252; eco#79 · Test: critical nets of D3 and synthetic SerDes boards, single-shot PNS vs beam widths 1, 4, 16; metrics PRC pass, time · Effort/risk: M; porting PCBWorld-Engine to KiCad 10/11 has unknown maintenance cost.
