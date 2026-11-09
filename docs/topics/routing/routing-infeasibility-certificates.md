# Routing infeasibility certificates and computed relaxations

Scope: sound proofs that a region cannot be routed under the board's rules, the C0–C5 ladder, and relaxations as KiCad edits. Not here: theorems -> [dense-region math § 7](routing-cross-domain-and-math.md#7-math-and-topology); escape models -> [BGA survey](bga-routing-survey.md), [escape routing](escape-routing.md).
Keys: infeasibility certificate, relaxation, gap capacity, n(g), tile coupling, dog-bone legality, C0 ring cut, C1 LDS, circle-graph clique, C2 escape min cut, C3 multicommodity LP, λ*, weak duality, price vector, C4 fixed-topology cut, C5 CP-SAT/MaxSAT, assumption literals, MUS, MCS, IIS, Luo–Wong conflict clause, Japanese theorem, window soundness, rules variant, residual variant, kae.route.blocked

**Results**
1. A certificate is a proof only if every capacity it uses over-estimates the real one. Only "infeasible" is a proof; "feasible" proves nothing until an integral model or a routed board confirms it. Report "no obstruction found", never "feasible", from C0–C3 [I]. kae does this since the audit of 2026-11 ([below](#in-kae-the-ball-grid-certificate-kaerouteescapecertificate)).
2. Six-tier ladder, microseconds to hours: C0 ring/gap cuts → C1 fixed-order layer bounds → C2 escape max-flow min cut → C3 multicommodity LP with metric (price) dual → C4 fixed-topology cut test → C5 CP-SAT/MaxSAT with one assumption literal per rule (the only tier giving an exact minimal rule set).
3. Relaxations are computed: gap capacity is a step function of width, clearance, via size, so per-parameter thresholds come from a breakpoint search with a flow oracle; LP dual gives a necessary budget Σ d_e·Δc_e ≥ 1 − λ*; MaxSAT gives the cheapest relaxation set.
4. Negotiated routing yields a free certificate: by min-max resource sharing weak duality any price vector y (including PathFinder's history costs) is a lower bound; Σ_nets opt_c(y) > Σ_r y_r ⇒ no routing exists; one exact shortest path per net checks it.
5. No commercial PCB tool publishes such a certificate ([BGA survey § 6](bga-routing-survey.md#6-commercial-practice)); Luo–Wong (ASP-DAC'08) is the one paper mapping UNSAT conflicts to "add a track here".

### Capacity model from the board's own rules

Read from the board: net-class and `.kicad_dru` widths and clearances (incl. area rules under the BGA), via sizes, allowed via types, stackup, keepouts.
- Gap capacity: gap of free length g (copper edge to copper edge) holds n(g) = ⌊(g − 2·c_tp + c_tt)/(w + c_tt)⌋ tracks (c_tp track–pad, c_tt track–track clearance). An angled crossing uses more length, so n is an upper bound, safe for certificates [I, standard]. Example: 0.8 mm pitch, 0.4 mm pads: orthogonal g = 0.4 mm fits 1 track at w = c = 0.1, 2 at 0.075; diagonal √2·0.8 − 0.4 = 0.731 fits 3 at 0.1/0.1.
- Tile coupling: a tile's diagonal and two orthogonal gaps share space, so capacities do not add; use the Yan–Wong tile network (centre capacity D − 2⌊O/2⌋, [BGA survey § 1](bga-routing-survey.md#1-the-exact-single-layer-escape-network-yanwong)).
- Vias: via of diameter v in a gap leaves g − v − c each side. Dog-bone via at tile centre legal iff v + 2·c_via-pad ≤ √2·p − d; it then removes that tile's capacity on every layer it spans. Through vias couple all layers (why multi-layer escape is not a pure flow). Microvia or via-in-pad uses no channel.
- Pairs: merged diff pair uses 2w + gap, counts as one unit of that width.

### Tightness: where each bound is exact

| Setting | Exact? | Source |
|---|---|---|
| Single-layer unordered escape, Yan–Wong network | Yes: k balls escape iff max-flow ≥ k | thesis ch. 2 [P] |
| Multi-layer escape, via-in-pad or reserved via space | Yes, same argument | [P] |
| Multi-layer escape, through/blind vias placed freely | Not as flow (vias couple layers); exact as SAT (MonoSAT) | [P] |
| Fixed netlist (pairs fixed) | MCF LP is a relaxation; integrality gap exists (Hurkens–Schrijver–Tardos) | [P, survey] |
| Fixed topology, one layer | Yes: Cole–Siegel cut test, or Schrijver Thm 33 on any planar graph | [P] |
| Fixed boundary order, via-free layers | ω(crossing graph) ≤ layers; exact for two-sided order (LDS), a bound for one ring | [S] |
| Ring/gap counts with average channels (UG1099) | Loose: ignores inner rings passing through outer ones | [P] |

Flow-cut gap on planar graphs is small in theory; the practical gap is integrality (integer tracks, mutually exclusive vias, unsplittable nets). No published numeric gaps on detailed grid routing.

### Certificates in the literature and in tools

- Yan–Wong min cut [P]: maps to geometry (inter-tile edge = "between balls X and Y on layer L"; two shortcut edges + centre = "diagonal X–Z"); deficit = demand − cut; max-flow monotone in capacity, so what-ifs are re-runs.
- Wang–Shi–Cheng claim 4 [P]: closed-form minimum layer count; proved "2 layers impossible" for a 35×35 package.
- MonoSAT [P]: UNSAT proves "no escape in ≤ k layers under this via model" (12 of 23 parts); conflict clauses = min cuts over blocked and saturated edges.
- Luo–Wong ordered escape SAT ([ASP-DAC'08](https://www.cecs.uci.edu/~papers/aspdac08/pdf/p244_3A-4.pdf) [P]): final conflict clause read as node variables = "add a track in this tile", pin-edge variables = "add tracks around the pin in this direction", slot variables = "an ordering problem". 2 of 6 cases had no 1-track solution and routed after adding tracks where the conflict pointed; needs partitioning beyond ~10×10.
- BonnRoute weak duality ([slides](https://www.or.uni-bonn.de/home/vygen/files/rs-new.pdf) [P]): for any prices y ≥ 0, Σ_c opt_c(y)/Σ_r y_r ≤ λ*; ratio > 1 ⇒ infeasible even fractionally; multi-pin nets OK if opt_c is exact or a valid lower bound (e.g. MST/2).
- Japanese theorem (Onaga–Kakusho 1971; Iri 1971, [PDF](https://orsj.org/wp-content/or-archives50/pdf/e_mag/Vol.13_03_129.pdf) [S]): a multiflow exists iff Σ c_e·d_e ≥ Σ dem_i·dist_d(s_i, t_i) for every length function d ≥ 0; the dual of maximum concurrent flow returns the violating d.
- GRIP ([DAC'09](https://jlinderoth.github.io/papers/Wu-Davoodi-Linderoth-09.pdf) [P]): positive slack in the column-generation LP at convergence certifies fractional infeasibility.
- Solver support: HiGHS `feasibilityRelaxation` and IIS (light strategy); Gurobi `computeIIS`, `feasRelax` [S, docs]; CP-SAT `AddAssumptions` + `SufficientAssumptionsForInfeasibility()` returns a core not guaranteed minimal (minimize by deletion, [CPMpy](https://cpmpy.readthedocs.io/en/stable/unsat_core_extraction.html) [S]); pysat `musx`, `optux` (MUS), `lbx`, `mcsls`, `rc2` (MCS, MaxSAT). MCS = minimal relaxation, MUS = minimal explanation; hitting-set duals.
- Commercial ([BGA survey § 6](bga-routing-survey.md#6-commercial-practice)): Altium lists pads it could not fan out; Allegro X AI reports opens per net + pre-route audit; Cadence US 8,667,454 adds layers until bundles route; US 7,013,451 capacity check per congestion-graph edge; FPGA tools (Vivado, Quartus) show congestion per region and direction. None gives a proof.

## The ladder for a BGA region

Common model: gap graph of the window, one copy per signal layer; tiles as Yan–Wong nodes and via-site nodes with blocking sets; capacities from the rules, rounded up; every element named for people (e.g. "U3 gap B7–B8, In2.Cu"). Demand: every net with a pin inside the window and a pin or required exit outside.
Variants: rules variant (no routed copper: "impossible under the board's rules"); residual variant (current copper fixed: "impossible without rip-up"). Rules passes + residual fails ⇒ fix is rip-up, not rules.

| Tier | Test | Cost | Proves | Certificate shown to the LLM | Relaxation output |
|---|---|---|---|---|---|
| C0 | Ring and gap cuts: for each ring k and each half-plane row/column cut, nets inside that must leave ≤ Σ_layers Σ_gaps n(gap) − gap space taken by vias that must sit in the ring | µs | Infeasible under any routing | "Ring 3 of U3: 112 nets, 96 slots (4 layers × 24 gaps × 1)" | Closed form: largest w, smallest c, smallest via, or layer count at which slots ≥ demand |
| C1 | Fixed-order layer bound: LDS (two-sided) or circle-graph max clique (ring) | O(n log n) | Minimum via-free layers | "Byte lane DQ0–7 needs 3 via-free layers; 2 available" | "Allow vias in the region", "+1 layer", or a swap set that shortens the LDS (small ILP) |
| C2 | Escape max-flow on the Yan–Wong network (super-source on balls, sink on window border) | ms | Exact for single-layer unordered escape and via-in-pad; sound relaxation otherwise | Min-cut gap list with deficit | Per parameter, binary search over breakpoints (where n(g) steps), re-running max-flow: exact threshold for this model |
| C3 | Maximum concurrent multicommodity flow, LP or resource sharing with a Dijkstra oracle | s to min | λ* < 1: infeasible even fractionally | Lengths d_e (or prices y); top d_e·c_e arcs grouped into cut-like clusters | Elastic LP over relaxation classes; necessary Σ d_e·Δc_e ≥ 1 − λ*; confirm by re-solving |
| C4 | Fixed-topology cut test on the routed sketch, per layer | poly | This topology cannot be completed | Failing pad-pair cuts with overflow | "Re-topologize net set S" (rip-up, not a rule change) |
| C5 | CP-SAT or MaxSAT on the window: per-net flow conservation, cell and via exclusivity, MonoSAT-style via-type clauses, one assumption literal per rule instance | min to h; windows ≤ ~12×12 balls | UNSAT: exact proof these rules jointly forbid routing | Minimal core (MUS) over rule literals | Minimum-cost MCS, e.g. "via-in-pad on U3 C4, D5, plus w = 0.09 on L2" |

Window soundness: a proof on a window is a proof for the board only if the window border is left free (unconstrained exits, GRIP floating terminals). Fixing border crossings to Freerouting's gives only the residual answer.

### Relaxation classes, as KiCad edits

| Class | How it enters the model | How it is written back |
|---|---|---|
| Narrower track or smaller clearance in the BGA area | n(g) recomputed per gap | `.kicad_dru` rule scoped to the footprint's courtyard (neck-down) |
| Smaller via, or another via type (micro, blind, buried) | Via-site blocking sets and type clauses | Board setup via sizes, stackup via types |
| Via-in-pad | Pin edge straight to next layer, no channel use | Fab note (filled and capped); KiCad DRC allows a same-net via in a pad |
| One more signal layer, or more bottom-layer use | Extra layer copy | Stackup change, or layer preference only |
| Pin, bank or bit swap | Super-source per swap group | Schematic ECO (LLM decision) |
| Depopulated ball (package choice) | Δ resource node | Part change |

Report record per finding to the controlling LLM: tier (C0–C5); scope (rules, residual, topology); bottleneck (names, demand, capacity); relaxations per class with threshold and whether necessary (C0, C3) or verified sufficient in the model (C2, C5). Extends the "which rule blocks each open connection" report started in `kae.route.blocked` (branch `close-bga-escape`) [I].

## In kae: the ball-grid certificate (`kae.route.escape.certificate`)

The certificate is the LP bound of the escape planner's Yan–Wong network (C2 above, multi-layer, through vias as variables). What makes it a proof, what it reports, and what it still assumes:
- **Every capacity over-estimates the real one.** The bound uses the smallest ball, measured across the grid's axes, and the smallest ball-to-track requirement of any ball against any signal net class. Medians, which an earlier version used (robust to outlier pads, but not upper bounds), are kept only for the planner. It also uses the smallest legal width, the smallest track–track and track–via clearance between any two signal classes, and the smallest via the board setup's minimums allow. A net class's via is only the default size of new vias, not a DRC constraint. A gap between two empty via sites is credited at least the ⌊p/(w+c)⌋ + 1 tracks that can cross a pitch with nothing at its ends, so runs of empty sites of any length are over-estimated. The earlier one-pitch credit already over-estimated them wherever a track pitch is below the ball pitch.
- **Demand is per net, not per ball.** Each net with a pad off the package needs one escape. Its other balls may join it inside the ball field: a CSP's four adjacent supply balls, an eMMC's paired data balls. Counting each ball made the bound claim "can't escape" on human layouts that route those packages cleanly. A corpus scan found 5 such packages; the per-ball count caused at least 2 of them.
- **Rules are floored at the board's fab.** Nothing finer than the fab's finest class is credited ([fab classes](../rules/dfm-fab-limits.md)). A "can't escape" is therefore a proof under the board's rules *and* that fab's published capability. It is not a proof against a finer process.
- **Wording.** "k of n balls can't escape" is the proof. A relaxation that makes the bound reach the demand is reported as "no obstruction found with …", never "feasible": the bound is a relaxation, and only a routed board confirms it (recommendation 4).
- **Exact thresholds for this model.** Every tile capacity is fit(g) = ⌊(g − s₁ − s₂ + c)/(w + c)⌋, linear in each rule in both numerator and denominator. Its breakpoints in width, clearance, ball-to-track clearance and via diameter are therefore closed form. kae sorts them (rounded down to µm, plus each fab class's limit) and binary-searches them with the LP bound as the oracle. A via's legality at a dog-bone site comes from Space's exact checks and has no closed form, so via diameters also get a 5 µm grid. Fixed ladders (0.15/0.127/0.1/0.075 mm, 25 µm clearance steps down to 0.05 mm) over-relaxed by up to a rung and went below every fab.
- **Fab labels and hazards.** Each relaxation carries `fab`, `fab_class` (the cheapest class that builds it, or none) and the fab's cost wording. One beyond *standard* adds a `relaxation_beyond_standard_fab` hazard (warn, manufacturing) to the route report. The pad-ring check (`ring_certificate`) and `kae.route.blocked` label their suggestions the same way. Their thresholds are closed form (ring) or a binary search with the real grid router (blocked), floored at the fab.
- **Still assumed.** A uniform grid (rotated packages are handled, mixed pitches are not); at most one via per tile, at its dog-bone site or in the pad; the outer border open (window soundness above). Plane balls are left out of the demand. Where the field has a depopulated interior, a via can sit off the dog-bone sites. Three eMMC-153 packages routed by hand without rule violations have such vias: pinguz97 zynq-som U7, usbarmory U3 and satnogs-comms U102 are each "1 net short" in the model. The entry there carries `proof: false` and says "not a proof". Modelling a layer change at every free tile is the fix.
- **Measured** (2026-11-03): 576 corpus boards (the 213 merit boards, the `bga` tag, bga-next-ab), routing stripped, KiCad 10.0.7, fab JLCPCB. There were 633 ball grids on about 290 boards; 1 very large board (enzian) and 5 others were not reached. Results, old certificate → new:
  - flags: 216 → 184; 32 lose theirs, 20 weaken from "rule" to "only with via-in-pad", and none are new;
  - "rule" proofs on human layouts free of clearance, width, via, hole and edge violations: 6 → 3, the eMMCs above;
  - runtime: about 1.9× the old (mean 14 s per grid);
  - pad rings: 3,140, verdicts unchanged.

  Of the new relaxations that remove the obstruction, via diameters fall mostly in JLCPCB's advanced class (79 advanced, 15 HDI, 1 standard) and track widths mostly in the standard class (16 standard, 2 advanced, 4 HDI). 106 of the 184 entries carry a fab hazard.

## Build order

[I]
1. C0 and C2 first: one gap-graph builder from the board's rules feeds both; C0 is the instant message; C2 is the escape planner's own min cut ([BGA survey](bga-routing-survey.md#escape-pipeline-for-kae)); networkx or OR-Tools max-flow (BSD, Apache-2.0).
2. C3 for free from window negotiation: after each iteration compute exact per-net costs under current prices (GAMER-style sweeps in numba); weak-duality ratio > 1 ⇒ stop and report (a proof instead of "ran out of iterations").
3. C5 only on residual windows: CP-SAT with assumption literals, cores minimized by deletion, cheapest relaxation from an objective over relaxation literals.
4. Validate on our boards: any board whose human layout passes KiCad DRC must pass C0–C3 under the same rules; a failure is a capacity-model bug, not a proof.

## Open questions

- Tightness of C0 and C3 on real PCB windows unmeasured; no numeric flow-cut or integrality gaps for detailed routing in the literature.
- Off-grid KiCad geometry (rotated parts, rounded-rectangle pads, mixed pitches) breaks the uniform tile model; per-gap capacities from actual geometry keep the bound sound but lose Yan–Wong's exactness [I].
- CP-SAT core is not minimal; HiGHS IIS reportedly slow on large models ([MathOptIIS #20](https://github.com/jump-dev/MathOptIIS.jl/issues/20) [S]).

## Sources

- Primary sources linked inline. Related: [escape routing](escape-routing.md) · [topological](topological-routing.md) (SURF cut test)
