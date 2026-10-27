<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Layer collapse: analogs with exact or analytic results

Checks the hypothesis table in [layer-collapse](../../docs/ideas/original/layer-collapse.md).
Tags: [P] read in a primary source, [S] abstract or secondary source only, [I] our
derivation, [U] not verified. Citations were checked by web search in October 2026.
References [n] are listed at the end.

**Main correction.** Topology alone never forces more than 2 layers. A via is a point
on every layer, so any crossing can be removed with a two-via jumper. Euler-type
thickness bounds give θ ≥ 1 on every real netlist (§C1). Layer counts are forced by
**capacity** (cuts, via area, SMD pads that sit on one layer) and by **via budgets**.
Exact via-free results exist only for special shapes: pins in two facing rows, or all
pins on one boundary.

## Table

| Piece | Analog | Verified result | Solves exactly / approximately | Hypothesis verdict |
|---|---|---|---|---|
| Layers, no vias | Graph thickness θ | θ ≥ ⌈m/(3n−6)⌉; bipartite ⌈m/(2n−4)⌉; θ(K_n)=⌊(n+7)/6⌋ except θ(K_9)=θ(K_10)=3 [1]; deciding θ ≤ 2 is NP-complete [2]; geometric thickness 2 is NP-hard [3] | Exact only with no vias; vacuous on pin graphs (§C1) | Formulas right, application wrong |
| Fixed pin positions | Pach–Wenger [4] | Any planar graph, any vertex-to-point map: a polyline drawing with O(n) bends per edge (24(n+2); 2.5n+1 in [5]); Ω(n) bends needed in the worst case [S] | Planarity does not depend on point positions; bends turn into length and capacity | **Overstated.** Pads are not points: a footprint fixes the cyclic order of its pins |
| Footprint pin order | Partially embedded planarity | Can a fixed drawing of a subgraph H be extended to a planar drawing of G? Linear time [6]; a simpler test in [7] [S] | Exact via-free test for one layer, with footprints as fixed walls | New |
| Pins on one boundary, fixed order | Circle-graph colouring / book embedding with fixed order | k-colouring NP-complete for k ≥ 4; k = 3 open (Unger's algorithm refuted) [8]; χ ≤ 2ω log₂ω + 2ω log₂log₂ω + 10ω, and Kostochka's lower bound is ½ω(ln ω − 2) [9]; max clique is polynomial [10]; maximum pagenumber-k subgraph with fixed order is NP-complete for k ≥ 2 [11] | Exact model for an escape region whose pins all lie on its boundary | New |
| Two facing pin rows | Permutation graph (perfect) | Minimum via-free layers = longest decreasing subsequence; the most nets routable via-free on L layers = λ₁+…+λ_L of the RSK shape (Greene [12]) | Exact, O(n log n) | New (§C2) |
| Vias as layer switches | Book embedding with spine crossings | Every graph embeds in 3 pages with O(log n) spine crossings per edge, and this order is tight for some graphs [13] [S] | Via-count order when pins are collinear | New |
| One-layer capacity | Cut conditions for homotopic routing | With homotopies fixed, a layer is routable iff every cut between features has flow ≤ capacity (Cole–Siegel; Leiserson–Maley) [14,15] [S]; disjoint homotopic paths in planar graphs, polynomial [16] | Exact for one layer with a fixed sketch; only necessary for L ≥ 2 | **Better than** Okamura–Seymour for PCBs |
| Same | Okamura–Seymour [17] | Planar graph, all terminals on one face: the cut condition is sufficient for **fractional** flow; integral **edge-disjoint** paths also need G+demands Eulerian [S] | Edge-disjoint graph model; PCBs need vertex-disjoint paths with widths | **Overstated** (Eulerian condition omitted; edge-disjoint) |
| Same, ordered | River routing | Non-crossing nets across a channel: separation and offset optimal in polynomial time (Leiserson–Pinter [18]) | Exact for planar bus routing | OK |
| Via minimization, 2 layers (CVM) | Planar max-cut / planar Ising ground state | Polynomial (planar max-cut via matching [19]) **only with junctions of degree ≤ 3** [20,21]; NP-complete with 4-way junctions [22,23]; topological (UVM) is NP-hard [24,25]; equivalent to the ground state of a planar Ising spin glass [26] [P: survey in 27] | Exact for a fixed sketch whose junctions are 3-way | **Overstated** (degree condition) |
| CVM, L ≥ 3 | Planar 3-colouring, k-partite induced subgraph | 3-layer CVM NP-hard [28]; k-layer heuristics [29]; exact ILP [30] [P: via 27] | Heuristic or ILP | New |
| Layer assignment as colouring | Antiferromagnetic Potts / Max-k-Cut | Frieze–Jerrum ratio α_k ≈ 1 − 1/k + 2 ln k/k² (α₃ ≥ 0.800, α₄ ≥ 0.850) [31]; **Min k-partition (residual conflicts) is not approximable within |V|^{2−ε} for k ≥ 3** [32] | Guarantees cut weight, not conflicts | **Overstated** |
| Conflict-graph structure | String / segment intersection graphs | Not χ-bounded: triangle-free segment graphs with unbounded χ [33] | The clique bound can be far below what is needed | New |
| Split planes | 2D minimal partitions | Arcs of constant curvature, three meeting at 120°, perpendicular to a free boundary (planar clusters [34]); planar double bubble [35]; planar triple bubble [36]; disk in 3 parts [37]; honeycomb [38] | Exact if the cost is clearance area ∝ boundary length; not if the cost is conductance | **Mis-cited:** Taylor 1976 [39] covers 2D surfaces in R³ |
| 0/45/90° copper | Crystalline / Wulff | The Wulff shape of the octilinear metric is the regular octagon with facets at 0/45/90/135° (§C6); crystalline variational problems [40] | Exact for single islands; partitions are non-unique | Confirmed, with numbers |
| Area allotment | Semi-discrete OT, power diagrams | For any sites and target areas, weights exist that make the power cells have those areas; they minimise squared transport cost [41]; damped Newton converges globally [42] | Exact areas, convex cells; a cell need not contain its pins | OK |
| Minimum-capacitance connection | Steiner tree over a plane; Chebotarev problem in free 2D | Over a near reference plane C ≈ C′·length, so the Steiner tree is optimal (Hanan grid [43]; RSMT ≥ ⅔·RMST [44]). In 2D log-capacity the minimiser is Grötzsch's set of analytic arcs (critical trajectories of a quadratic differential), **not** the Steiner tree [45] | Steiner tree is approximate (ignores fringing and junctions) | **Reasoning wrong:** monotonicity does not imply a Steiner tree |
| Pour capacitance | Plates | Disk C = 8εR (exact); among plates of given area the disk is minimal (Pólya–Szegő 1951) [S/U] | Free space only; over a plane C ≈ εA/h + fringe ∝ perimeter | New |
| Pour conductance | Sheet resistance, constructal design, SIMP | Two round contacts in an infinite sheet: R = (R_s/π)·arccosh(d/2a) [I, image method]; constructal trees [46]; SIMP [47] | Two terminals exact; many terminals numerical only | Refined |
| Signal cutting a pour | Planar topology | Number of pour fragments = E − V + C of (traces ∪ pour outline) (§C8) | Exact | Refined |
| Over/under | Knot diagrams | No transferable theorem: PCB layers impose no over/under consistency, so knot type is irrelevant. The real problem is CVM (graph bipartization [23]) | None | **Misleading analog** |
| Layer ordering | Origami flat-foldability | Deciding flat-foldability is NP-hard [48], with gadget errors corrected in [49] [S] | PCB layers have no ordering constraints | **Weak analog** |
| Multiphase algorithm | MBO threshold dynamics | Arbitrary surface tensions [50]; **volume constraints via auction dynamics** [51] | Algorithm, no closed form | Refined (volumes are in [51], not [50]) |
| Board-level demand | Thompson / Rent / layer estimation | Area ≥ Ω(bisection²) [52]; layer estimators surveyed in [53] [S]; BGA escape needs t+1 rows per layer for t traces per channel [54] | Necessary bounds | New (§C3, §C4) |
| Slicing (3D printing) | — | Found nothing that transfers | — | Drop |

## Notes per item

- **Thickness and Pach–Wenger.** For the via-free subproblem, positions of point
  vertices really do not matter ([4], [5]). They matter through footprints: a pin row
  with gap < w + 2s cannot be crossed, so the row acts as a wall. That fixes a rotation
  and turns the question into partially-embedded planarity [6]. The O(n)-bend worst
  case [4] is a capacity warning: a topologically legal route can wind a lot.
- **Cut conditions.** Leiserson–Maley/Cole–Siegel is the one-layer analog of
  max-flow/min-cut with widths, and it is exact once each net's homotopy is fixed
  [14,15,16]. With L ≥ 2 the cut condition is only necessary. Vias occupy every layer,
  and the multicommodity flow–cut gap is O(log k) in general graphs (Linial–London–
  Rabinovich 1995) [U for planar constants].
- **CVM.** Barahona–Grötschel–Jünger–Reinelt [26] map 2-layer CVM to planar max-cut,
  i.e. the ground state of a planar Ising spin glass. That is the exactly solvable stat-
  phys analog for **two** layers; the Potts model is the analog for L ≥ 3. Liers et al.
  [27] split each 4-way junction into a chain of 3-way junctions in an ε-region
  (heuristic) and solve planar max-cut for over 10⁶ nodes. Euclidean Steiner points have
  degree 3, so exactness is preserved (octilinear: [U]); rectilinear crosses are not.
- **Max-k-Cut.** The SDP guarantee is on cut weight. The quantity that matters (weight
  left uncut, i.e. same-layer conflicts) is inapproximable [32]. Treat SDP or annealing
  as heuristics and certify with the exact one-layer check.
- **Minimal partitions.** Split planes minimise lost copper = Σ c_ij·length(Γ_ij). With
  areas prescribed (or a concave value of area), the first variation gives the laws in
  §C5. Jean Taylor's 1976 theorem is the 3D statement (120° along triple curves,
  tetrahedral points). The planar laws are classical and proved for clusters by Morgan
  [34].
- **Capacitance.** Monotonicity (A ⊂ B ⇒ C(A) ≤ C(B)) is true but says nothing about
  which connected set is minimal. Over a reference plane at height h much smaller than
  the net span, capacitance is additive in length, so the Steiner tree is right.
  Without a plane (2D log-capacity) the answer is the Chebotarev–Grötzsch continuum [45].
- **Fixed-geometry assignment conflicts** form string graphs, and colouring them gives
  no ω-based guarantee [33].

## Closed forms we can compute

**C1. The Euler bound is vacuous on netlists [I].** Model one layer. Footprints whose
pads cannot be passed between are holes (h of them) with P pins on their boundaries.
Model each multi-pin net as a star around one free Steiner vertex (s of them); a
two-pin net is one edge. The graph is the hole cycles plus net edges: V = P + s,
E = P + m. The h hole faces have total length P; every other face has length ≥ 3.
Euler's formula then gives m ≤ P + 3s + 3h − 6. Every net edge ends at a pin, and each
pin carries at most one net edge, so m ≤ P. The bound therefore always holds once
h + s ≥ 2. Pins away from walls only add slack. **Do not** use the clique expansion of
multi-pin nets (common in placement): it creates spurious dense graphs, because
Steiner points are free. Non-planarity in real boards comes from **order**
(crossings forced by fixed pin orders), which counting cannot see.

**C2. Via-free layers for ordered pins.** For nets between two facing walls (connector
to connector, bus fanout), number the pins by position on each row. Net i crosses net j
iff their orders are inverted. Then:
- L_min = LDS(σ), the longest decreasing subsequence (Dilworth/Mirsky).
- The most nets routable via-free on L layers is λ₁+…+λ_L, where λ is the RSK shape of σ
  [12]. The remaining n − Σλ_i nets need at least one via each.
For pins on one closed boundary (escape region): ω(circle graph) ≤ L_min ≤
2ω log₂ω + 2ω log₂log₂ω + 10ω [9], and ω is computable in polynomial time [10].

**C3. Cut-capacity bound [I, from 14–15].** For a cut segment γ, let N(γ) be the number
of nets with pins on both sides, and ℓ_free(l) the length of γ on layer l minus every
pad, via, or keep-out crossing it (each counted with its clearance). Through-vias count
on every layer. Then

  Σ_l ⌊(ℓ_free(l) + s)/(w + s)⌋ ≥ N(γ),  so  L ≥ N(γ)(w+s)/ℓ_free.

Run it on Delaunay edges between pads to get a per-region obstruction map. For one layer
with a fixed sketch, checking cuts between all feature pairs is also sufficient.

**C4. BGA escape [I + S].** Traces per channel: t = ⌊(p_b − D − s)/(w + s)⌋, with ball
pitch p_b and land D (pad on the top layer, via land on inner layers). Pins of rings
2..r of an n×n array must leave through the 4(n−1) channels of ring 1:
Σ_{k=2..r} 4(n−2k+1) ≤ 4t(n−1). For n ≫ r this gives r ≤ t+1 rows per layer, matching
AMD UG1099 [54] (t = 1 → 2 rows). Signal layers ≈ ⌈R_sig/(t+1)⌉, slightly fewer
because inner rings are shorter.

**C5. Split-plane geometry [I; standard first variation].** Line tension
σ_ij = c_ij·v (clearance × copper value per area). λ_i is the area multiplier, i.e. the
marginal value of copper area for pour i.
- Boundary curvature: κ_ij = (λ_i − λ_j)/σ_ij (constant along each arc).
- Triple junctions (Neumann triangle): the opening angle of pour k is θ_k = π − α_k,
  where cos α_k = (σ_ki² + σ_kj² − σ_ij²)/(2σ_ki σ_kj). With equal clearances, θ = 120°
  and κ₁₂ + κ₂₃ + κ₃₁ = 0. A high-voltage pour with clearance 2c to both others gets
  θ_HV = 151.0° and the other two 104.5°.
- At the board edge: 90°, since the edge pull-back is the same for every pour.
- Two pours in a w×h board (w ≤ h), smaller area A. The candidates are a quarter disk
  at a corner (boundary √(πA)), a half disk on a side (√(2πA), never better), and a
  straight cut (w). **Use the quarter disk iff A < w²/π.** This agrees with the
  quarter-plane bound √(πA) of [55]. Octilinear corner: a quarter octagon, length
  √(8(√2−1)A) ≈ 1.820√A. Manhattan: a square, 2√A.

**C6. Wulff shapes [I].** The octilinear length of a step (dx, dy), 0 ≤ dy ≤ dx, is
dx + (√2−1)dy, so γ(n) = max|n_i| + (√2−1)·min|n_i|. Its unit ball is the regular
octagon with vertices on the axes and diagonals. The Wulff shape is the polar of that
ball: a regular octagon whose **facets** lie along 0/45/90/135°. The anisotropic
isoperimetric inequality P_γ ≥ 2√(|W|A) gives these minimum boundary lengths:

| Metric | Wulff shape | Minimum boundary length |
|---|---|---|
| Euclidean | disk | 3.545√A |
| Octilinear | octagon, \|W\| = 8(√2−1) | 3.641√A (+2.7%) |
| Manhattan | square | 4√A (+12.8%) |

**C7. Capacitance and resistance scaling.**
- Trace over a plane: C ≈ C′ℓ, with C′ = √ε_eff/(c₀Z₀) ≈ 1.2 pF/cm for 50 Ω on FR-4
  (ε_eff ≈ 3.3).
- A net with p terminals spread over area A_net has Steiner length ≈ β√(p·A_net)
  (BHH-type asymptotics, Steele 1981) [S; constant U].
- Pour: C ≈ ε₀ε_r A/h·(1 + O(h/√A)); about 19 pF/cm² at h = 0.2 mm, ε_r = 4.3. So
  C_pour/C_net ~ (ε/C′h)·√A/(β√p), and a pour carries roughly √A/(h√p) times more
  capacitance.
- Free space: disk 8εR; thin wire ≈ 2πεℓ/ln(ℓ/a) (Jackson 2000) [S].
- Coupling between traces at spacing D, height H: ≈ 1/(1+(D/H)²) (Johnson–Graham 1993)
  [S]. For coupling ≤ k you need D ≥ H√(1/k − 1).
- Resistance: plane R = (R_s/π)·arccosh(d/2a) against trace R_s·d/w; 1 oz copper has
  R_s ≈ 0.49 mΩ/□. Example with d = 50 mm, a = 0.5 mm: plane 0.72 mΩ, 1 mm trace
  24.5 mΩ. The break-even width is w* = πd/arccosh(d/2a) ≈ 34 mm.

**C8. Pour fragmentation.** Draw the signal traces on a pour layer together with the
pour outline as a plane graph. The number of pour pieces is E − V + C (bounded faces).
A piece without a pin of its net needs stitching vias or should be deleted.

## What composes into an algorithm

1. **Per-layer constraint graphs.** Make walls from footprint gaps < w+2s; lock SMD pads
   to their layer; through-hole pins exist on every layer.
2. **Capacity screen.** Run C3 on pad Delaunay edges and C4 per BGA to get L_min per
   region. This is the obstruction map, and it is mostly capacity.
3. **Lift and sketch.** Route each net alone, keep its homotopy, and build the
   forced-crossing graph.
4. **Via-free subsets.** Exact for channel regions (C2: LDS/Greene); use the
   circle-graph ω bound where all pins are on a boundary.
5. **Assign.** For L = 2, run CVM as planar max-cut after splitting 4-way junctions
   [27]; it is exact for the sketch. For L ≥ 3, use Potts annealing or the Max-k-Cut SDP
   for a start, and ILP [30] on small regions.
6. **Certify each layer.** Run the one-layer cut test [14–16] on the assigned
   homotopies. A violated cut is a concrete obstruction certificate; add vias or move
   the crossing net.
7. **Grow pours.** Start from a power diagram with target areas [41], then run auction
   MBO [51] with an octilinear kernel. Check curvature and junction angles against C5,
   fragments against C8, and conductance against C7.
8. **Realize** with the pnr router and score with KiCad DRC; the router log is not a
   score.

## Open problems / no analytic answer

- Exact multi-layer routability with vias that occupy every layer has no
  characterisation; cut conditions are only necessary.
- 3-colourability of circle graphs is open [8], so whether pins on one boundary fit on
  3 via-free layers has no known efficient test.
- No good approximation is known for CVM with L ≥ 3 or for 4-way junctions [U].
- Shapes that maximise conductance for many terminals under area and partition
  constraints have no closed form. SIMP and constructal methods are numerical.
- Crystalline minimal partitions with clearance classes are non-unique, and no explicit
  solutions are known beyond single Wulff islands.
- The capacitance-minimal connection in 3D at finite h comparable to pin spacing has no
  closed form (Chebotarev is 2D only).
- Thickness with fixed rotations at footprint vertices (partially-embedded thickness)
  has not been studied as such [U].

## References

1. Beineke & Harary 1965, Canad. J. Math 17:850; completed by Alekseev–Gončakov and Vasak 1976; survey Mutzel–Odenthal–Scharbrodt 1998, Graphs Comb. 14:59.
2. Mansfield 1983, Math. Proc. Camb. Phil. Soc. 93:9.
3. Durocher, Gethner, Mondal 2016, Comput. Geom. 56 [S].
4. Pach & Wenger 2001, Graphs Comb. 17:717 [S].
5. Schaefer 2021, Electron. J. Comb. 28(4) P4.55, https://www.combinatorics.org/ojs/index.php/eljc/article/view/v28i4p55
6. Angelini et al. 2015, ACM TALG (SODA 2010).
7. Fink & Rutter 2024, https://arxiv.org/abs/2410.13536
8. Bachmann, Rutter, Stumpf 2023/24, JGAA 28, https://arxiv.org/abs/2309.02258 ; Garey–Johnson–Miller–Papadimitriou 1980, SIAM J. Alg. Disc. Meth. 1:216.
9. Davies 2022, Proc. AMS 150:5121, https://arxiv.org/abs/2107.03585
10. Gavril 1973, Networks 3:261.
11. Jonsson & Kuhlmann 2015, https://arxiv.org/abs/1504.05908
12. Greene 1974, Adv. Math. 14:254.
13. Enomoto & Miyauchi 1999, SIAM J. Discrete Math. 12:337, doi:10.1137/S0895480195280319
14. Cole & Siegel 1984, FOCS ("River routing every which way, but loose") [S].
15. Leiserson & Maley 1985, STOC; Maley, *Single-Layer Wire Routing and Compaction*, MIT Press 1990 [S].
16. Schrijver 1991, Discrete Comput. Geom. 6:527, doi:10.1007/BF02574704
17. Okamura & Seymour 1981, J. Comb. Theory B 31:75 [S].
18. Leiserson & Pinter 1983, SIAM J. Comput. 12:447.
19. Hadlock 1975, SIAM J. Comput. 4:221.
20. Pinter 1984, Adv. VLSI Comput. Syst. 1:123.
21. Chen, Kajitani, Chan 1983, IEEE TCAS 30:284, doi:10.1109/TCS.1983.1085357
22. Naclerio, Masuda, Nakajima 1989, IEEE Trans. Comput. 38:1604, doi:10.1109/12.42135
23. Choi, Nakajima, Rim 1989, SIAM J. Discrete Math. 2:38, doi:10.1137/0402004
24. Marek-Sadowska 1984, IEEE TCAD 3:184, doi:10.1109/TCAD.1984.1270074
25. Rim, Kashiwabara, Nakajima 1989, UMD TR (corrected NP-hardness proof) [S].
26. Barahona, Grötschel, Jünger, Reinelt 1988, Oper. Res. 36:493.
27. Liers, Nieberg, Pardella 2011, "Via minimization in VLSI chip design", https://kups.ub.uni-koeln.de/55018/1/zaik2011-630.pdf [P]
28. Chang & Du 1988, IEEE Trans. Comput. 37:625.
29. Chang & Cong 1997, DAC, doi:10.1109/DAC.1997.597216; Chou & Lin 1998, ICCAD.
30. Fouilhoux & Mahjoub 2010, Comput. Optim. Appl., doi:10.1007/s10589-010-9355-1
31. Frieze & Jerrum 1997, Algorithmica 18:67, doi:10.1007/BF02523688
32. Kann, Khanna, Lagergren, Panconesi 1997, Chicago J. Theor. Comput. Sci. [S].
33. Pawlik et al. 2014, J. Comb. Theory B 105:6.
34. Morgan 1994, Pacific J. Math. 165:347 [S].
35. Foisy et al. 1993, Pacific J. Math. 159:47.
36. Wichiramala 2004, J. reine angew. Math. 567:1.
37. Cañete & Ritoré 2004, Indiana Univ. Math. J. 53:883 [S].
38. Hales 2001, Discrete Comput. Geom. 25:1.
39. Taylor 1976, Ann. Math. 103:489.
40. Taylor 1978, Bull. AMS 84:568.
41. Aurenhammer, Hoffmann, Aronov 1998, Algorithmica 20:61, doi:10.1007/PL00009187
42. Kitagawa, Mérigot, Thibert 2019, JEMS 21:2603.
43. Hanan 1966, SIAM J. Appl. Math. 14:255.
44. Hwang 1976, SIAM J. Appl. Math. 30:104.
45. Ortega-Cerdà & Pridhnani, https://arxiv.org/abs/0809.2483 (Grötzsch 1930, Lavrentiev, Goluzin).
46. Bejan 1997, Int. J. Heat Mass Transfer 40:799.
47. Bendsøe 1989, Struct. Optim. 1:193; Bendsøe & Sigmund 2003, *Topology Optimization*.
48. Bern & Hayes 1996, SODA.
49. Akitaya et al. 2016, "Box pleating is hard", https://scripts.mit.edu/~jasonku/pdf/BOXPLEATINGHARD_LNCS2016.pdf
50. Esedoḡlu & Otto 2015, Comm. Pure Appl. Math. 68:808.
51. Jacobs, Merkurjev, Esedoḡlu 2018, J. Comput. Phys. 354:288, https://ww3.math.ucla.edu/camreport/cam17-23.pdf
52. Thompson 1979, STOC; Leighton 1983, *Complexity Issues in VLSI*.
53. Sandborn & Spletter 1996/1999, https://web.calce.umd.edu/articles/abstracts/1996/routing.htm [S]
54. AMD UG1099, https://docs.amd.com/r/en-US/ug1099-bga-device-design-rules/Layer-Count-Optimization [V]
55. Brezis & Bruckstein 2021, C. R. Math. 359:1191, https://www.numdam.org/articles/10.5802/crmath.243
