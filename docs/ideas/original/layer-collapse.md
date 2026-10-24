# Original idea: layer collapse

Part of the [original-ideas catalog](README.md). Status tags as in
[joint-pnr](joint-pnr.md). Experiments: `tools/research/collapse_<tag>/`.

## The problem

Give every net its own layer, then collapse those N layers (50–100) into the board's
L copper layers (2, 4, 6, ...). On its own layer a net can take any shape. Power and
ground want as much copper as possible (low impedance, planes). Capacitance- and
coupling-sensitive nets want as little as possible. Look for the shapes that make the
collapse possible with the fewest conflicts, and find where it cannot go below L layers.

### Formal statement

- Board Ω ⊂ R², L layers. Nets i ∈ N, each with terminals T_i (pads; SMD pads on one
  layer, through-hole on all). Net classes:
  - **P (pours):** GND and rails. Weight w_p on conductance (or −resistance between
    source and sinks).
  - **S (sensitive):** weight c_s on capacitance to everything else, plus pairwise
    coupling weights k_ij.
  - **R (ordinary):** weight on length.
- **Lifted problem:** a connected S_i ⊂ Ω with T_i ⊂ S_i per net, on its own layer, with
  no interaction. Optima:
  - a pour takes S_p = Ω;
  - a sensitive or ordinary net takes a minimum-width Steiner tree of T_i.
- **Collapse:** an assignment Φ_i : S_i → {1..L} (a layer for every point of a net's
  copper) such that:
  - on each layer, different nets are disjoint with clearance c;
  - a net changes layer only through a via (cost v; it occupies all layers);
  - every net stays connected.

  Shapes may change during the collapse: pours shrink, others reroute.
- **Objective:**

  max Σ_P w_p·G_p(S_p) − Σ_S c_s·C_s(S_s) − Σ k_ij·M_ij − λ·#vias − μ·Σ_R length

- **Obstructions:** points or regions where no assignment with L layers exists. They are
  either local capacity (too many nets cross a cut) or local topology (the connections
  forced through a region form a graph that needs more than L planar layers).

## Analogous problems with exact or analytic results (hypotheses to verify)

| Piece of the problem | Analog | Known result |
|---|---|---|
| How many layers a netlist needs | Graph thickness θ(G) | Euler: θ ≥ ⌈E/(3V−6)⌉; bipartite θ ≥ ⌈E/(2V−4)⌉; θ(K_n) = ⌊(n+7)/6⌋ (n ≠ 9, 10). Pach–Wenger: a planar graph can be drawn with vertices at prescribed points (polyline edges), so fixed pin positions do not change per-layer topology, only capacity |
| Whether one layer has room | Multicommodity flow, cut condition | Okamura–Seymour: in planar graphs with all terminals on the outer face, the cut condition is sufficient; river routing (Leiserson–Pinter) is exact by cut density |
| Which side of each crossing goes to which layer (2 layers) | Constrained via minimization | Reduces to max-cut on a planar graph, polynomial (Hadlock 1975; Pinter 1983; Chen–Kajitani–Chan 1983) |
| Layer assignment for L > 2 | Antiferromagnetic Potts model / Max-k-Cut | Ground state = assignment; Frieze–Jerrum SDP ratio 1 − 1/k + O(log k/k²); mean-field (deterministic) annealing |
| Several pours sharing a layer (split planes) | Minimal partitions / soap films | Plateau / Jean Taylor (1976): boundaries are arcs of constant curvature (difference of the area multipliers) meeting at 120°, perpendicular to the free edge; double-bubble theorem; honeycomb (Hales) for many equal cells |
| Same, with 0/45/90° copper | Crystalline (anisotropic) variational problems | Wulff shapes: octagonal cells and facets, crystalline curvature |
| How much of a layer each pour gets, near its pins | Semi-discrete optimal transport | Power (Laguerre) diagrams with prescribed cell areas (Aurenhammer; Mérigot) |
| Minimum-capacitance connection | Isoperimetric inequalities for capacity (Pólya–Szegő) | Capacitance is monotone in the set, so the minimum connected set through T_i is a Steiner tree; Steiner points at 120°; rectilinear: Hanan grid, Hwang RSMT ≥ 2/3 RMST |
| Pour conductance with limited copper | Volume-to-point conduction, constructal design, topology optimization | Tree-like optimal conductors (Bejan); SIMP / level-set solutions |
| Signal crossing a pour layer | Planar topology, percolation | A curve splits a simply connected pour iff it meets the pour's boundary twice or closes a loop; on plane layers signals must be short jumpers, or the pour needs stitching |
| Over/under at crossings | Knot and link diagrams, braids | The crossing structure of the projected nets is a link diagram; via minimization chooses over/under at each crossing with minimum layer changes |
| An algorithm for multi-phase partitions with constraints | MBO threshold dynamics (Merriman–Bence–Osher; Esedoglu–Otto 2015) | Fast grid scheme for multi-phase minimal partitions with volume constraints and arbitrary surface tensions |

## How the pieces could compose

1. Lift: route every net alone (Steiner/A* on an empty board).
2. Obstructions: thickness and cut bounds give where and how many layers are needed.
3. Assign: crossings and overlaps of the lifted shapes become a conflict graph. Use planar
   max-cut for 2 layers, Potts annealing or Max-k-Cut SDP for L.
4. Grow pours into the remainder of each layer as a multi-phase minimal partition (MBO with
   area weights and Wulff anisotropy), cut only by short signal jumpers.
5. Realize with the pnr router, using the assignment as a layer prior, and score with KiCad
   DRC and kae.physics.

## Experiments

See [placement/joint-pnr-experiments](../../topics/placement/joint-pnr-experiments.md)
for the engine and scoring, and the results section added when the experiments finish.
