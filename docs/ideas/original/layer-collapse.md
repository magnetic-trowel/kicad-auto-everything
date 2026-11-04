# Original idea: layer collapse

Scope: every net on its own layer, collapsed into the board's L copper layers; formal statement, verified analogs, the joint continuation method, experiments. Part of the [original-ideas catalog](README.md); status tags as in [joint-pnr](joint-pnr.md); verdict index in [scorecard](scorecard.md#layer-collapse-pieces). Experiments: `tools/research/collapse_<tag>/`.
Keys: layer collapse, lifted problem, obstruction, graph thickness, cut condition, Cole–Siegel, Okamura–Seymour, via minimization, planar max-cut, Greene/RSK, LDS, minimal partition, double bubble, Wulff shape, MBO, power diagram, Steiner tree, joint collapse by continuation, jc, coupling β

## The problem

Give every net its own layer (N = 50–100), then collapse those N layers into the board's L copper layers (2, 4, 6, ...). On its own layer a net can take any shape. Power and ground want as much copper as possible (low impedance, planes); capacitance- and coupling-sensitive nets want as little as possible. Find the shapes that make the collapse possible with the fewest conflicts, and where it cannot go below L layers.

### Formal statement

- Board Ω ⊂ R², L layers. Nets i ∈ N with terminals T_i (pads; SMD on one layer, through-hole on all). Classes:
  - **P (pours):** GND and rails; weight w_p on conductance (or −resistance source→sinks).
  - **S (sensitive):** weight c_s on capacitance to everything else + pairwise coupling weights k_ij.
  - **R (ordinary):** weight on length.
- **Lifted problem:** a connected S_i ⊂ Ω with T_i ⊂ S_i per net, on its own layer, no interaction. Optima: pour S_p = Ω; sensitive or ordinary net = minimum-width Steiner tree of T_i.
- **Collapse:** assignment Φ_i : S_i → {1..L} (a layer for every point of a net's copper) with: different nets disjoint with clearance c per layer; layer changes only through a via (cost v; occupies all layers); every net connected. Shapes may change during the collapse: pours shrink, others reroute.
- **Objective:** max Σ_P w_p·G_p(S_p) − Σ_S c_s·C_s(S_s) − Σ k_ij·M_ij − λ·#vias − μ·Σ_R length
- **Placement and routing are one problem.** Variables: poses of all parts, copper shape of every net, layer of every point of that copper, together. The obstruction is joint: a placement can make an impossible collapse possible, and the collapse decides which placement is good. The method below collapses parts and nets at the same time.
- **Placement as a variable.** Movable part k has pose (x_k, y_k, θ_k), side fixed; its pads move with it. Lifted shapes, cut demands, pin-order permutations between parts and pour regions are functions of the poses: min over poses of [min over collapse assignments of the objective]. Cheap placement terms:
  - **Forced vias of a bus:** LDS/RSK count of the pin permutation between two parts (depends on both rotations).
  - **Cut-capacity overflow** over gaps between pads: a function of XY pushing parts apart only where L layers cannot carry the demand.
  - **Pour fragmentation:** signals crossing between pads of a pour net.
  - **Lifted conflicts:** conflicts left after collapsing each net's lone route.
- **Obstructions:** points or regions where no assignment with L layers exists: local capacity (too many nets cross a cut) or local topology (connections forced through a region need more than L planar layers).

## Verified: what the analogs actually give

Literature check with citations and tags: [research_notes/layer-collapse/analogs.md](../../../research_notes/layer-collapse/analogs.md). It corrects the hypothesis table below:
1. **Topology never forces more than 2 layers.** A via is a point on every layer, so any crossing becomes a two-via jumper; the Euler thickness bound is ≥ 1 on real pin graphs. Layers are forced by **capacity** (cut density, via area, single-layer SMD pads) and by the via budget.
2. **Exact via-free results only for special pin orders:** two facing pin rows: minimum layers = longest decreasing subsequence of the pin permutation, and at most λ₁+…+λ_L nets fit via-free on L layers (Greene/RSK); all pins on one boundary: circle-graph clique is a lower bound; each footprint's pin order fixed: linear-time one-layer test (partially embedded planarity).
3. **One-layer capacity:** with each net's homotopy fixed, a layer is routable iff every cut passes the density test (Cole–Siegel, Leiserson–Maley; polynomial). Okamura–Seymour needs an Eulerian condition and gives only fractional flow.
4. **2-layer via minimization** is polynomial (planar max-cut) only if junctions have degree ≤ 3; NP-complete with 4-way junctions; NP-hard for ≥ 3 layers.
5. **Split planes:** 2D minimal partitions (Morgan; double/triple bubble); Taylor 1976 is the 3D case. Boundary curvature (λ_i − λ_j)/σ_ij; junction angles from clearance ratios (120° when all equal); boundaries meet the board edge at 90°. Boundary cost relative to a circle: octilinear Wulff octagon +2.7%, Manhattan +12.8%.
6. **Minimum-capacitance net:** Steiner tree is right over a ground plane (C ∝ length); in free 2D the optimum is curved (Chebotarev–Grötzsch), so "monotone capacity" was the wrong argument.
7. Knot diagrams and origami give nothing usable. Area-constrained MBO is auction dynamics (Jacobs–Merkurjev–Esedoglu 2018).

## Analogous problems (original hypotheses; see the corrections above)

| Piece of the problem | Analog | Known result |
|---|---|---|
| Layers a netlist needs | Graph thickness θ(G) | Euler: θ ≥ ⌈E/(3V−6)⌉; bipartite θ ≥ ⌈E/(2V−4)⌉; θ(K_n) = ⌊(n+7)/6⌋ (n ≠ 9, 10). Pach–Wenger: a planar graph can be drawn with vertices at prescribed points (polyline edges), so fixed pin positions change only capacity, not per-layer topology |
| Room on one layer | Multicommodity flow, cut condition | Okamura–Seymour: planar, all terminals on the outer face → cut condition sufficient; river routing (Leiserson–Pinter) exact by cut density |
| Which side of each crossing goes to which layer (2 layers) | Constrained via minimization | Max-cut on a planar graph, polynomial (Hadlock 1975; Pinter 1983; Chen–Kajitani–Chan 1983) |
| Layer assignment, L > 2 | Antiferromagnetic Potts / Max-k-Cut | Ground state = assignment; Frieze–Jerrum SDP ratio 1 − 1/k + O(log k/k²); mean-field (deterministic) annealing |
| Several pours sharing a layer (split planes) | Minimal partitions / soap films | Plateau / Jean Taylor (1976): constant-curvature arcs (difference of area multipliers) meeting at 120°, perpendicular to the free edge; double-bubble theorem; honeycomb (Hales) for many equal cells |
| Same, 0/45/90° copper | Crystalline (anisotropic) variational problems | Wulff shapes: octagonal cells and facets, crystalline curvature |
| Share of a layer per pour near its pins | Semi-discrete optimal transport | Power (Laguerre) diagrams with prescribed cell areas (Aurenhammer; Mérigot) |
| Minimum-capacitance connection | Capacity isoperimetric inequalities (Pólya–Szegő) | Capacitance monotone in the set → minimum connected set through T_i is a Steiner tree; Steiner points at 120°; rectilinear: Hanan grid, Hwang RSMT ≥ 2/3 RMST |
| Pour conductance with limited copper | Volume-to-point conduction, constructal design, topology optimization | Tree-like optimal conductors (Bejan); SIMP / level-set |
| Signal crossing a pour layer | Planar topology, percolation | A curve splits a simply connected pour iff it meets the pour boundary twice or closes a loop; on plane layers signals must be short jumpers, or the pour needs stitching |
| Over/under at crossings | Knot and link diagrams, braids | Projected nets' crossings form a link diagram; via minimization chooses over/under with minimum layer changes |
| Multi-phase partitions with constraints | MBO threshold dynamics (Merriman–Bence–Osher; Esedoglu–Otto 2015) | Fast grid scheme, volume constraints, arbitrary surface tensions |

## Joint collapse by continuation (parts and nets together)

1. **Lift.** Every net and part on its own layer, coupling β = 0: parts at their HPWL + physics optimum, overlaps allowed; each net its lone route (Steiner/A*) between its current pads; pours fill everything.
2. **Collapse.** Raise one coupling β from 0 to ∞. Every conflict costs β × its overlap, one currency: two nets in one physical-layer cell; two same-side parts overlapping; a pad on another net's copper; a signal cutting a pour.
3. **Best response at each β** to the same price field (PathFinder history, so recurring conflicts get dearer): nets re-route and choose layers (via where jumping costs less than sharing); parts translate and rotate, pulled by their nets' actual routes (pin tensions) and physics terms, pushed by priced conflicts under their footprint; pours take what is left of their layers.
4. **β → ∞: state is legal.** Cells whose price kept climbing are the obstructions (L layers too few for that placement); parts move to dissolve them.

A homotopy from the lifted state to the board, close to deterministic annealing. `negotiate` prices the same conflicts but never starts from the lifted state; `combo` builds the placement greedily before refining.

## How the pieces could compose

0. Place with collapse terms: part rotations by the LDS/RSK forced-via count of each bus; spread parts only where cut capacity overflows (XY); plus the [physics place terms](../../research/joint/physics-objective.md).
1. Lift: route every net alone (Steiner/A* on an empty board).
2. Obstructions: cut-capacity bounds over Delaunay edges and rings around dense parts give where and how many layers are needed (topology alone never needs more than 2).
3. Assign: crossings/overlaps of lifted shapes → conflict graph; planar max-cut for 2 layers (exact when junction degree ≤ 3), annealing or ILP for L.
4. Grow pours into each layer's remainder as a multi-phase minimal partition (MBO with area weights and Wulff anisotropy), cut only by short signal jumpers.
5. Realize with the pnr router using the assignment as a layer prior; score with KiCad DRC and kae.physics.

## Experiments (tools/research/collapse_*)

Mechanism, numbers and provenance on the research pages; verdicts in [scorecard](scorecard.md#layer-collapse-pieces).

| experiment | one-line result | verdict | page |
|---|---|---|---|
| obstruction bounds, 112 boards (`collapse_obst`) | bounds never force > 2 layers; layer counts = planes + BGA escape; bus rotation is the lever (jumpers 209 → 78) | bounds sound but loose | [bounds](../../research/joint/layer-collapse-analysis.md#layer-count-bounds-collapse_obst) |
| collapse as routing (`collapse_assign`) | optimal layer assignment no better than random | no merit as a router | [assign](../../research/joint/layer-collapse-analysis.md#exact-layer-assignment-as-a-router-lifted-cost-as-a-placement-measure-collapse_assign) |
| lifted cost as a placement measure (same) | ranks placements by routed cost at ρ 0.85 (HPWL 0.51) | positive signal | [assign](../../research/joint/layer-collapse-analysis.md#exact-layer-assignment-as-a-router-lifted-cost-as-a-placement-measure-collapse_assign) |
| minimal-partition pours (`collapse_pour`) | geometry matches theory; interleaved rails fail; shape must come from conductance to the pads | no merit as a pour objective | [pours](../../research/joint/pour-models.md#minimal-partition-and-wulff-pours) |
| collapse terms in the joint placer (`collapse_cplace`) | proxies drop, routed vias do not; use as tie-breakers or with routing out of the loop | no merit in the joint loop | [cplace](../../research/joint/layer-collapse-analysis.md#collapse-quantities-as-placement-terms-collapse_cplace) |
| joint collapse by continuation (`collapse_joint`) | best legal / clean / fast physics; joint vs frozen 0.52× copper | **merit** | [jc](../../research/joint/jc.md#jc) |
