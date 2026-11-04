# Routing infeasibility certificates and computed relaxations

**TL;DR**
- A certificate is only a proof if every capacity it uses **over-estimates** the real one. When a check says "feasible", it proves nothing until an integral model or a routed board confirms it. Only "infeasible" is a proof.
- There is a ladder of six tiers, from microseconds to hours:
  1. ring and gap cuts;
  2. fixed-order layer bounds;
  3. escape max-flow min cut;
  4. a multicommodity LP with a metric (price) dual;
  5. a fixed-topology cut test;
  6. CP-SAT or MaxSAT with one assumption literal per rule. This tier is the only one that gives an exact *minimal* rule set.
- Relaxations are computed, not guessed. Gap capacity is a step function of width, clearance and via size, so the exact threshold per parameter comes from a breakpoint search with a flow oracle. The LP dual gives a necessary budget, Σ d_e·Δc_e ≥ 1 − λ*. MaxSAT gives the cheapest set of relaxations.
- Negotiated routing yields a free certificate. By min-max resource sharing weak duality, any price vector y is a valid lower bound, including PathFinder's own history costs: if Σ_nets opt_c(y) > Σ_r y_r, no routing exists. One exact shortest path per net checks it.
- No commercial PCB tool publishes such a certificate ([BGA survey](bga-routing-survey.md#6-commercial-practice)). Luo–Wong (ASP-DAC'08) is the one paper that maps UNSAT conflicts to "add a track here".

Theory statements are in [math and topology](routing-cross-domain-and-math.md#7-math-and-topology). The escape models are in [BGA survey](bga-routing-survey.md) and [escape-routing](escape-routing.md).

## Key facts

### Capacity model from the board's own rules

Read every quantity from the board: net-class and `.kicad_dru` widths and clearances (including area rules under the BGA), via sizes, allowed via types, the stackup and keepouts. Then:

**Gap capacity.** A gap of free length g (copper edge to copper edge) holds
- n(g) = ⌊(g − 2·c_tp + c_tt)/(w + c_tt)⌋ tracks,
- where c_tp is the track–pad clearance and c_tt the track–track clearance.

A track crossing the gap at an angle uses more of its length, so n is an upper bound and safe for certificates [I, standard]. Example: 0.8 mm pitch with 0.4 mm pads has g = 0.4 mm orthogonally, which fits 1 track at w = c = 0.1 and 2 at 0.075. The diagonal gap is √2·0.8 − 0.4 = 0.731, which fits 3 at 0.1/0.1.

**Tile coupling.** The diagonal and the two orthogonal gaps of a tile share space, so their capacities do not add. Use the Yan–Wong tile network, where the centre node has capacity D − 2⌊O/2⌋ ([BGA survey §1](bga-routing-survey.md#1-the-exact-single-layer-escape-network-yanwong)).

**Vias.**
- A via of diameter v in a gap leaves g − v − c on each side.
- A dog-bone via at the tile centre is legal iff v + 2·c_via-pad ≤ √2·p − d. It then removes that tile's capacity on every layer it spans.
- A through via couples all layers, which is why multi-layer escape is not a pure flow.
- A microvia or via-in-pad uses no channel.

**Pairs.** A merged diff pair uses 2w + gap and counts as one unit of that width.

### Tightness: where each bound is exact

| Setting | Exact? | Source |
|---|---|---|
| Single-layer unordered escape, Yan–Wong network | Yes: k balls escape iff max-flow ≥ k | thesis ch. 2 [P] |
| Multi-layer escape, via-in-pad or reserved via space | Yes, by the same argument | [P] |
| Multi-layer escape with through or blind vias placed freely | No as a flow (vias couple layers); exact as SAT (MonoSAT) | [P] |
| Fixed netlist (pairs fixed) | MCF LP is a relaxation; the integrality gap exists (Hurkens–Schrijver–Tardos) | [P, survey] |
| Fixed topology, one layer | Yes: Cole–Siegel cut test, or Schrijver Thm 33 on any planar graph | [P] |
| Fixed boundary order, via-free layers | ω(crossing graph) ≤ layers. Exact for two-sided order (LDS); a bound for one ring | [S] |
| Ring or gap counts with average channels (UG1099) | Loose. It ignores inner rings passing through outer ones | [P] |

The flow-cut gap on planar graphs is small in theory. **The practical gap is integrality**: tracks are integers, vias exclude each other and nets cannot split. Published numeric gaps on detailed grid routing were not found.

### Certificates in the literature and in tools

- **Yan–Wong min cut** [P]. It maps directly to geometry:
  - an inter-tile edge means "between balls X and Y on layer L";
  - two shortcut edges plus the centre node mean "diagonal X–Z".
  The deficit is demand minus the cut. Max-flow is monotone in capacity, so what-ifs are re-runs.
- **Wang–Shi–Cheng claim 4** [P]. A closed-form minimum layer count. It proved "2 layers impossible" for a 35×35 package.
- **MonoSAT** [P]. UNSAT proves "no escape in ≤ k layers under this via model" (12 of 23 parts). Its conflict clauses are min cuts over blocked and saturated edges.
- **Luo–Wong ordered escape SAT** ([ASP-DAC'08](https://www.cecs.uci.edu/~papers/aspdac08/pdf/p244_3A-4.pdf) [P]). The final conflict clause is read as:
  - node variables mean "add a track in this tile";
  - pin-edge variables mean "add tracks around the pin in this direction";
  - slot variables only mean "an ordering problem".
  2 of 6 cases had no 1-track solution and routed after tracks were added where the conflict pointed. It needs partitioning beyond about 10×10.
- **BonnRoute weak duality** ([slides](https://www.or.uni-bonn.de/home/vygen/files/rs-new.pdf) [P]). For any prices y ≥ 0: Σ_c opt_c(y)/Σ_r y_r ≤ λ*. If the ratio is above 1, the instance is infeasible even fractionally. It works with multi-pin nets if opt_c is exact or a valid lower bound, for example MST/2.
- **Japanese theorem** (Onaga–Kakusho 1971; Iri 1971, [PDF](https://orsj.org/wp-content/or-archives50/pdf/e_mag/Vol.13_03_129.pdf) [S]). A multiflow exists iff Σ c_e·d_e ≥ Σ dem_i·dist_d(s_i, t_i) for every length function d ≥ 0. The dual of maximum concurrent flow returns the violating d.
- **GRIP** ([DAC'09](https://jlinderoth.github.io/papers/Wu-Davoodi-Linderoth-09.pdf) [P]). Positive slack in the column-generation LP at convergence certifies fractional infeasibility.
- **Tool support:**
  - HiGHS `feasibilityRelaxation` and IIS (light strategy), and Gurobi `computeIIS` and `feasRelax` [S, docs].
  - CP-SAT `AddAssumptions` plus `SufficientAssumptionsForInfeasibility()` returns a core that is not guaranteed minimal; minimise it by deletion ([CPMpy](https://cpmpy.readthedocs.io/en/stable/unsat_core_extraction.html) [S]).
  - pysat `musx` and `optux` (MUS), and `lbx`, `mcsls` and `rc2` (MCS and MaxSAT).
  - An MCS is a minimal relaxation and a MUS is a minimal explanation. They are hitting-set duals.
- **Commercial tools** ([BGA survey §6](bga-routing-survey.md#6-commercial-practice)):
  - Altium lists the pads it could not fan out.
  - Allegro X AI reports opens per net plus a pre-route audit.
  - Cadence US 8,667,454 adds layers until the bundles route.
  - US 7,013,451 is a capacity check per congestion-graph edge.
  - FPGA tools (Vivado, Quartus) show congestion per region and direction.
  - None gives a proof.

## The ladder for a BGA region

**Common model.** A gap graph of the window, one copy per signal layer:
- tiles as Yan–Wong nodes and via-site nodes with blocking sets;
- capacities from the rules above, rounded *up*;
- every element named for people, for example "U3 gap B7–B8, In2.Cu".

**Demand.** Every net with a pin inside the window and a pin or required exit outside.

**Two variants.**
- *Rules variant*: no routed copper, which answers "impossible under the board's rules".
- *Residual variant*: the current routed copper fixed, which answers "impossible without rip-up".

If the rules variant passes and the residual variant fails, the fix is rip-up, not rules.

| Tier | Test | Cost | Proves | Certificate shown to the LLM | Relaxation output |
|---|---|---|---|---|---|
| C0 | Ring and gap cuts: for each ring k, and each half-plane row or column cut, nets inside that must leave ≤ Σ_layers Σ_gaps n(gap) − gap space taken by vias that must sit in the ring | µs | Infeasible under any routing | "Ring 3 of U3: 112 nets, 96 slots (4 layers × 24 gaps × 1)" | Closed form: the largest w, the smallest c, the smallest via, or the layer count at which slots ≥ demand |
| C1 | Fixed-order layer bound: LDS (two-sided) or circle-graph max clique (ring) | O(n log n) | Minimum via-free layers | "Byte lane DQ0–7 needs 3 via-free layers; 2 available" | "Allow vias in the region", "+1 layer", or a swap set that shortens the LDS (a small ILP) |
| C2 | Escape max-flow on the Yan–Wong network (super-source on balls, sink on the window border) | ms | Exact for single-layer unordered escape and via-in-pad; a sound relaxation otherwise | Min-cut gap list with deficit | Per parameter, binary search over its breakpoints (where n(g) steps), re-running max-flow: an exact threshold *for this model* |
| C3 | Maximum concurrent multicommodity flow, LP or resource sharing with a Dijkstra oracle | s to min | λ* < 1: infeasible even fractionally | Lengths d_e (or prices y); top d_e·c_e arcs grouped into cut-like clusters | Elastic LP over relaxation classes. Necessary: Σ d_e·Δc_e ≥ 1 − λ*. Confirm by re-solving |
| C4 | Fixed-topology cut test on the routed sketch, per layer | poly | This topology cannot be completed | Failing pad-pair cuts with overflow | "Re-topologise net set S", which is rip-up, not a rule change |
| C5 | CP-SAT or MaxSAT on the window: per-net flow conservation, cell and via exclusivity, via-type clauses as in MonoSAT, one assumption literal per rule instance | min to h; windows ≤ about 12×12 balls | UNSAT: exact proof that these rules jointly forbid routing | Minimal core (MUS) over rule literals | Minimum-cost MCS: for example "via-in-pad on U3 C4, D5, plus w = 0.09 on L2" |

**Window soundness.** If the window border is left free, a proof on the window is a proof for the board. That means exits are unconstrained: GRIP's floating terminals. Fixing border crossings to Freerouting's gives only the residual answer.

### Relaxation classes, as KiCad edits

| Class | How it enters the model | How it is written back |
|---|---|---|
| Narrower track or smaller clearance in the BGA area | n(g) recomputed per gap | A `.kicad_dru` rule scoped to the footprint's courtyard (neck-down) |
| Smaller via, or another via type (micro, blind, buried) | Via-site blocking sets and type clauses | Board setup via sizes, stackup via types |
| Via-in-pad | Pin edge straight to the next layer, no channel use | Fab note (filled and capped). KiCad DRC allows a same-net via in a pad |
| One more signal layer, or using the bottom layer more | Extra layer copy | Stackup change, or layer preference only |
| Pin, bank or bit swap | A super-source per swap group | Schematic ECO (LLM decision) |
| Depopulated ball (package choice) | Δ resource node | Part change |

Each finding goes to the controlling LLM as one record:
- **tier**: C0–C5;
- **scope**: rules, residual, or topology;
- **bottleneck**: names, demand and capacity;
- **relaxations**: per class, the threshold and whether it is *necessary* (C0, C3) or *verified sufficient in the model* (C2, C5).

This extends the "which rule blocks each open connection" report already started in `kae.route.blocked` (branch `close-bga-escape`) [I].

## Recommendations for our system

1. **Build C0 and C2 first.** One gap-graph builder from the board's rules feeds both. C0 is the instant message. C2 is the escape planner's own min cut ([BGA survey](bga-routing-survey.md#recommendations-for-our-system)). Use networkx or OR-Tools max-flow (BSD, Apache-2.0) [I].
2. **Get C3 for free from the window negotiation.** After each iteration, compute exact per-net costs under the current prices; GAMER-style sweeps in numba suit this. Test the weak-duality ratio. If it exceeds 1, stop the window negotiation and report. That replaces "ran out of iterations" with a proof [I].
3. **C5 only on residual windows.** Use CP-SAT with assumption literals, minimise cores by deletion, and get the cheapest relaxation from an objective over the relaxation literals [I].
4. **Never claim "feasible" from C0–C3.** Report "no obstruction found" instead [I]. kae does this since the audit of 2026-11 ([below](#in-kae-the-ball-grid-certificate-kaerouteescapecertificate)).
5. **Validate on our boards.** The human layouts give a free soundness test: any board whose human layout passes KiCad DRC must pass C0–C3 under the same rules. A failure there is a bug in our capacity model, not a proof [I].

## In kae: the ball-grid certificate (`kae.route.escape.certificate`)

The certificate is the LP bound of the escape planner's Yan–Wong network (C2 above, multi-layer, through vias as variables). What makes it a proof, what it reports, and what it still assumes:
- **Every capacity over-estimates the real one.** The bound uses the smallest ball, measured across the grid's axes, and the smallest ball-to-track requirement of any ball against any signal net class. Medians, which an earlier version used (robust to outlier pads, but not upper bounds), are kept only for the planner. It also uses the smallest legal width, the smallest track–track and track–via clearance between any two signal classes, and the smallest via the board setup's minimums allow. A net class's via is only the default size of new vias, not a DRC constraint. A gap between two empty via sites is credited at least the ⌊p/(w+c)⌋ + 1 tracks that can cross a pitch with nothing at its ends, so runs of empty sites of any length are over-estimated. The earlier one-pitch credit already over-estimated them wherever a track pitch is below the ball pitch.
- **Demand is per net, not per ball.** Each net with a pad off the package needs one escape. Its other balls may join it inside the ball field: a CSP's four adjacent supply balls, an eMMC's paired data balls. Counting each ball made the bound claim "can't escape" on human layouts that route those packages cleanly. A corpus scan found 5 such packages; the per-ball count caused at least 2 of them.
- **Rules are floored at the board's fab.** Nothing finer than the fab's finest class is credited ([fab classes](../rules/dfm-fab-limits.md)). A "can't escape" is therefore a proof under the board's rules *and* that fab's published capability. It is not a proof against a finer process.
- **Wording.** "k of n balls can't escape" is the proof. A relaxation that makes the bound reach the demand is reported as "no obstruction found with …", never "feasible": the bound is a relaxation, and only a routed board confirms it (recommendation 4).
- **Exact thresholds for this model.** Every tile capacity is fit(g) = ⌊(g − s₁ − s₂ + c)/(w + c)⌋, linear in each rule in both numerator and denominator. Its breakpoints in width, clearance, ball-to-track clearance and via diameter are therefore closed form. kae sorts them (rounded down to µm, plus each fab class's limit) and binary-searches them with the LP bound as the oracle. A via's legality at a dog-bone site comes from Space's exact checks and has no closed form, so via diameters also get a 5 µm grid. Fixed ladders (0.15/0.127/0.1/0.075 mm, 25 µm clearance steps down to 0.05 mm) over-relaxed by up to a rung and went below every fab.
- **Fab labels and hazards.** Each relaxation carries `fab`, `fab_class` (the cheapest class that builds it, or none) and the fab's cost wording. One beyond *standard* adds a `relaxation_beyond_standard_fab` hazard (warn, manufacturing) to the route report. The pad-ring check (`ring_certificate`) and `kae.route.blocked` label their suggestions the same way. Their thresholds are closed form (ring) or a binary search with the real grid router (blocked), floored at the fab.
- **Still assumed.** A uniform grid (rotated packages are handled, mixed pitches are not); at most one via per tile, at its dog-bone site or in the pad; the outer border open (window soundness above). Plane balls are left out of the demand.

## Conflicts and open questions
- How tight C0 and C3 are on real PCB windows is unmeasured. The literature has no numeric flow-cut or integrality gaps for detailed routing.
- Off-grid KiCad geometry (rotated parts, rounded-rectangle pads, mixed pitches) breaks the uniform tile model. Per-gap capacities from actual geometry keep the bound sound but lose Yan–Wong's exactness [I].
- The CP-SAT core is not minimal. HiGHS IIS is reportedly slow on large models ([MathOptIIS #20](https://github.com/jump-dev/MathOptIIS.jl/issues/20) [S]).

## Sources
- Primary sources are linked inline. See also [escape-routing](escape-routing.md) · [topological-routing](topological-routing.md) (SURF cut test) · [routing-cross-domain-and-math](routing-cross-domain-and-math.md) · [bga-routing-survey](bga-routing-survey.md)
