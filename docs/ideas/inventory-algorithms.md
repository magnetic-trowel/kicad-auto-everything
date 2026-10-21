# Idea inventory — algorithms cluster (placement, routing, solvers, cross-domain)

Every distinct algorithm, approach, transplant, formulation or recommendation found in the algorithms cluster notes, one line each. Source tags: **PA** placement_algorithms, **RA** routing_algorithms, **RC** routing_classics_supplement, **CD** cross_domain_ideas, **ST** solver_toolbox, **VP** verification_papers (wins conflicts). Links point to the topic doc holding detail. Notes live in `research_notes/LLM driven PCB placement and routing/` (e.g. [placement_algorithms.md](../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md)).

Link labels: `P-` placement, `R-` routing, `S-` solvers topic docs (definitions at the end). Ranked transplants: [cross-domain-transplants](cross-domain-transplants.md).

## A. Placement algorithm families
1. Four-class taxonomy of real PCB placers: greedy grid, SA/metaheuristic, analytical + legalizer, math programming. PA → [families][P-families]
2. Force-directed/quadratic spring placement (Quinn & Breuer 1979, first PCB FD placer). PA → [families][P-families]
3. GORDIAN quadratic WL with recursive-partition spreading. PA → [families][P-families]
4. Kraftwerk/Kraftwerk2 Bound2Bound force-directed placement. PA → [families][P-families]
5. FastPlace / SimPL lower-bound quadratic + look-ahead legalization. PA → [families][P-families]
6. ePlace electrostatic density (FFT/DCT potential) + Nesterov with Lipschitz steps. PA, ST → [analytical][S-analytical]
7. RePlAce routability-driven analytical placement. PA → [families][P-families]
8. DREAMPlace: placement as PyTorch training, GPU, fences, timing. PA, ST → [analytical][S-analytical]
9. Vanilla VLSI analytical placers fail on PCBs (NS-Place finding). PA → [families][P-families]
10. PCB analytical checklist: rotation variable, side-aware density, pad clearance/pad type, net-crossing term, exact geometry, discrete legalizer. PA → [placers][P-placers]
11. SA-PCB TimberWolf-style annealer with polygon overlap (Boost.Geometry). PA, ST → [families][P-families]
12. B*-tree Fast-SA (rotate/move/swap) as conventional PCB approach. PA → [families][P-families]
13. Tuned multithreaded / go-with-the-winners SA as strong baseline (TILOS). PA, VP → [ML/RL][P-ML]
14. Trace: LLM schematic analysis → floorplan variants → SA with 8 moves, HPWL+RUDY+compactness+thermal cost. PA → [families][P-families]
15. Hier-RTLMP SA over cluster tree with named weights. PA → [families][P-families]
16. GA/PSO/SOGA/ACO older PCB placers (toy-scale critique). PA → [families][P-families]
17. Hybrid distribution-EA orientation + conjugate-subgradient coordinates (PA-ICM). PA, ST → [placers][P-placers]
18. Capo multilevel min-cut placement; ROOSTER RSMT net model. PA → [families][P-families]
19. Partitioning surviving as clustering (hMETIS, DBSCAN). PA → [families][P-families]
20. Floorplan representations: sequence pair, BSG, O-tree, CBL, ECBL, twin binary trees, Polish expression. PA → [families][P-families]
21. Sequence-pair PCB placement with coordinate alignment / centralized blocks / relay-race. PA → [families][P-families]
22. KiCad autoplacer greedy 1 mm grid scan (no rotation since 7.0) — seed only. PA → [families][P-families]
23. kicad-tools force-directed/GA/hybrid/CMA-ES/Bayesian placement strategies. PA → [families][P-families]
24. SA as best cheap HPWL optimizer at small N; CP-SAT for legality. ST → [metaheuristics/QD][S-meta]

## B. PCB placers 2022–2026 and their features
25. NS-Place net-separation term (SVM margin between pin convex hulls, alternating minimization). PA → [placers][P-placers]
26. Laplacian-eigenvector (spectral) seeding with enumerated relative orientations. PA → [placers][P-placers]
27. MILP legalization minimizing ΣHPWL + (max−min HPWL) wirelength-variance term. PA → [legalization][P-legal]
28. Cypress two-sided electrostatic density with sides fixed upstream. PA, ST, VP → [analytical][S-analytical]
29. Cypress differentiable net crossing (Bézier t,u through bell functions). PA, ST, VP → [analytical][S-analytical]
30. Gumbel-Softmax orientation logits optimized bi-level with positions. PA, ST, VP → [analytical][S-analytical]
31. RUDY-guided area adjustment and RMST wirelength op. PA → [analytical][S-analytical]
32. BOHB/MOTPE hyperparameter tuning scored by Freerouting routability. PA, ST, VP → [tuning][S-tuning]
33. Chen DAC'25 wire-area model separating power vs signal routing demand. PA, VP → [placers][P-placers]
34. Pad-to-pad clearance model in global placement. PA → [placers][P-placers]
35. Two-sided pad-type-aware (THT vs SMD) density. PA → [sides/thermal/EMC][P-sides]
36. QP legalizer for heterogeneous shapes. PA → [legalization][P-legal]
37. NTU power-circuit-flow anchor points guiding force-directed placement. PA → [placers][P-placers]
38. SA-based pad alignment to reduce wire crossings. PA → [placers][P-placers]
39. Separating-Axis-Theorem collision on exact contours and board shapes. PA → [placers][P-placers]
40. Multi-stage force-directed with adaptive attraction/repulsion; scanline/window legalization. PA → [legalization][P-legal]
41. Joint rotation + position gradient descent with Hanan-grid legalization and insensitive-component fine-tuning (Zhao 2025). PA → [placers][P-placers]
42. MARS-Place multi-stage alignment-refined placement + routing. PA, VP → [placers][P-placers]
43. PA-ICM objective α·HPWL + β·√overlap + γ·out-of-contour; DBSCAN bottom-side IC-pin clusters. PA → [placers][P-placers]
44. PA-ICM legalization chain (push-apart, spacing table, maximal empty rectangles, close-to-pin resampling). PA → [legalization][P-legal]
45. HiePlace priority classes (first priority = outermost-pin parts). PA → [placers][P-placers]
46. Slicing irregular/stacked parts into sub-rectangles with cohesion constraints. PA → [legalization][P-legal]
47. Pattern grouping of same-size connected passives (1×4, 2×2). PA → [placers][P-placers]
48. Unrolled chip boundary + pairwise-swap crossing-minimizing reorder. PA → [placers][P-placers]
49. DP 0/1-knapsack selection of the first ring around a chip. PA → [LLM-guided][P-LLM]
50. Module relaxation to circles R = α√area solved with SLSQP. PA → [placers][P-placers]
51. Cardinal-relation MP legalization eliminating Booleans; backtracking by relaxing groups. PA → [legalization][P-legal]
52. Greedy alignment fine-tuning with misalignment-count metric. PA → [placers][P-placers]
53. DRLPlace PPO + per-step reward prediction + pre-trained ResNet policy-value + chip-centric clustering + push-and-reflection legalization. PA → [ML/RL][P-ML]
54. Commercial references: Quilter (RL + physics checks), DeepPCB placement, Allegro X AI; Cadence NN routability fitness patent. PA → [ML/RL][P-ML]

## C. Sides, thermal, EMC, reuse
55. LLM decides component sides (no academic placer does). PA → [sides/thermal/EMC][P-sides]
56. Bottom-side passives under the IC outline clustered by IC pins (PA-ICM). PA → [sides/thermal/EMC][P-sides]
57. Two interconnected planes with interlayer via costs (HiePlace future work). PA → [sides/thermal/EMC][P-sides]
58. TRouter differentiable thermal surrogate (backprop gradients steer layout). PA, RA → [sides/thermal/EMC][P-sides]
59. HSL-TFP DNN temperature-field surrogate; RBF-surrogate SA for thermal placement. PA → [sides/thermal/EMC][P-sides]
60. Thermal spreading penalty Σ PᵢPⱼ/(d²+ε). ST → [analytical][S-analytical]
61. Pareto SA wire length vs heat (control cabinets). CD → [sides/thermal/EMC][P-sides]
62. Power-converter layout automation: GA + Q3D parasitics, Pareto loop inductance vs mismatch, PowerSynth, hierarchical RL loop shrinking. PA → [sides/thermal/EMC][P-sides]
63. Hot-loop area / loop_compact terms; gate and power loops as critical loops. PA, ST → [sides/thermal/EMC][P-sides]
64. Aggressor/victim away_from constraints; Qplacer frequency repulsion. PA, CD → [sides/thermal/EMC][P-sides]
65. Post-route EM evaluation (ADS insertion loss, crosstalk) as placement metric (ModuPlace). PA → [sides/thermal/EMC][P-sides]
66. Lock mechanical anchors (connectors, holes, switches, LEDs) before placement. PA → [sides/thermal/EMC][P-sides]
67. D2BS subgraph-matching reference placement for reuse. PA → [sides/thermal/EMC][P-sides]
68. PCB-Migrator offset constraint graph + routing-path graph matching. PA, VP → [sides/thermal/EMC][P-sides]
69. Library of proven sub-layouts (datasheet references, past boards) reused via subgraph matching. PA → [LLM-guided][P-LLM]

## D. Legalization
70. Relative-position pruning of MILP from global placement (NS-Place). PA, ST → [legalization][P-legal]
71. NTU constraint-graph MILP legalization on sliced rectangles, double-sided, any orientation. PA → [legalization][P-legal]
72. Graph-based legalization with adaptive packing (Chen & Deng). PA → [legalization][P-legal]
73. Tetris + Abacus per-side legalization (Cypress). PA, ST → [legalization][P-legal]
74. CP-SAT min-displacement legalizer with hard decap/keep-out/edge/fixed constraints. ST → [CP-SAT][S-CPSAT]
75. Report infeasible constraint subsets with admissible relaxations to the LLM. PA, VP → [legalization][P-legal]
76. Compile each soft LLM constraint twice: smooth penalty in GP, exact constraint in legalization. PA → [analog][P-analog]

## E. Analog constraint placement (vocabulary)
77. MAGICAL GP with symmetry/overlap/boundary penalties and rising weights. PA → [analog][P-analog]
78. MAGICAL constraint-graph LP compaction with exact symmetry; LP detailed placement. PA → [analog][P-analog]
79. Signal-flow-graph traversal from seed differential pairs to extract symmetry. PA → [analog][P-analog]
80. ALIGN SA over sequence pairs with order/symmetry-preserving perturbations. PA → [analog][P-analog]
81. ALIGN ILP evaluation of each sequence pair (coordinates + flips). PA → [analog][P-analog]
82. Enumerate all order-consistent sequence pairs for small blocks. PA → [analog][P-analog]
83. ALIGN electrostatic EA placer with symmetric force matrix and common centroid. PA → [analog][P-analog]
84. ALIGN typed Hard/User/Soft constraint JSON schema as PCB vocabulary base. PA → [analog][P-analog]
85. Symmetry islands / ASF-B*-trees / HB*-trees. PA → [analog][P-analog]
86. Mixed constraint graphs for interactive editing (too imprecise for PCB). PA → [analog][P-analog]
87. GNN/GAT symmetry extraction; GNN performance-guided placement. PA → [analog][P-analog]
88. LayoutCopilot multi-agent intent → 11 layout commands (93.75% correctness). PA, CD, VP → [analog][P-analog]
89. LLANA LLM-enhanced BO for constraint generation. PA, CD → [analog][P-analog]
90. Multi-level MARL for asymmetric analog placement; ACDC synthetic symmetry benchmark. CD → [analog][P-analog]
91. IPRAIL structural template extraction and retargeting. CD → [analog][P-analog]

## F. ML/RL placement
92. Circuit Training/AlphaChip RL macro placement and its proxy cost. PA → [ML/RL][P-ML]
93. Reproduction critique: SA beats CT; proxy weakly correlates; weak baselines mislead. PA, VP → [ML/RL][P-ML]
94. MaskPlace position/wire/view masks; ChiPFormer offline decision transformer. PA → [ML/RL][P-ML]
95. WireMask-BBO greedy decoder + BO/EA; MaskRegulate RL refinement of DREAMPlace. PA → [ML/RL][P-ML]
96. EfficientPlace global tree search + local RL. PA, CD → [ML/RL][P-ML]
97. RL_PCB per-component multi-agent TD3/SAC (avg 17%/21% better than SA). PA, VP → [ML/RL][P-ML]
98. Lim 2026 discrete border-slot RL with Top-K proximity reward and TEWL metric. PA → [ML/RL][P-ML]
99. Crocker curriculum-reward RL placement. PA → [ML/RL][P-ML]
100. Kaphle MCTS self-generated datasets for offline RL. CD → [ML/RL][P-ML]
101. Use ML to order/partition/mask/prioritize, keep geometry classical. PA → [ML/RL][P-ML]
102. Position/boundary/spacing masks per rotation as feasibility rasters. PA, VP → [ML/RL][P-ML]

## G. LLM-guided placement and interfaces
103. PCBAgent decision transformer with legality masks for 4 rotations + chip-centred clockwise order. PA, VP → [LLM-guided][P-LLM]
104. Surface Layer Wire metric and NSLW objective. PA, VP → [LLM-guided][P-LLM]
105. LLM reweights RL score/replay weights and re-optimizes only violating parts. PA, VP → [LLM-guided][P-LLM]
106. ModuPlace LLM Hierarchical Modular Tree with confidence-based recursive splitting and RAG. PA, VP → [LLM-guided][P-LLM]
107. Netlist heterogeneous graph + sub-circuit matching to simplify netlists for LLMs. VP → [LLM-guided][P-LLM]
108. Comprehensive Constraint Graph (x̂, ŷ, θ̂, w) consumed by a hierarchical placer. PA, VP → [LLM-guided][P-LLM]
109. SFT on expert CCGs + GRPO with GNN pairwise-ranking reward + CCG equivalence test. PA, VP → [LLM-guided][P-LLM]
110. Li DAC'26 LLM grouping agents + topology-enriched retrieval + group-aware GP + CG/MILP legalization. VP → [LLM-guided][P-LLM]
111. LLM conflict prioritization from feature vectors (severity, congestion, category, type). PA → [LLM-guided][P-LLM]
112. Hierarchy-first recipe: core IC → satellite ring → module packing → module placement → exact legalization. PA → [LLM-guided][P-LLM]
113. Typed relation bundle with ordinal magnitudes as the LLM's only write API. PA, VP → [LLM-guided][P-LLM]
114. PCB constraint DSL (fixed, on_edge, keepout, side, rot_allowed, inside, clearance; near, ring, align, order, symmetric, group, spread, away_from, loop_compact). PA → [LLM-guided][P-LLM]
115. Persist relations as re-solvable design intent for ECOs/resizes. VP → [LLM-guided][P-LLM]
116. VeoPlace VLM regions as weak anchors (λ_A 0.01) or action masks. PA, CD, VP → [LLM-guided][P-LLM]
117. VeoPlace HISTORY SUMMARY → STRATEGY → REGIONS output contract. VP → [LLM-guided][P-LLM]
118. Top-Stratified context selection (K-means + rank-softmax). CD, VP → [LLM-guided][P-LLM]
119. Random-region control in every VLM-guidance evaluation. CD → [LLM-guided][P-LLM]
120. MAGE families of structurally similar groups → reference placement → transform-and-merge. VP → [LLM-guided][P-LLM]
121. Mandatory render visual gate + stateless independent auditor agent. VP → [LLM-guided][P-LLM]
122. Go-With-The-Winners tournament over agent variants. VP → [LLM-guided][P-LLM]
123. Images optional: text conflict lists beat image-based overlap inference. VP → [LLM-guided][P-LLM]
124. Calibrate tight/close/loose mm per component class from human boards. VP → [LLM-guided][P-LLM]
125. Mine CCG-like relative-offset graphs from PCBWorld D3 human boards for fine-tuning. VP → [LLM-guided][P-LLM]
126. Steerable IR menu: weighted costs, constraints, relative graphs, anchors/fences, orders/seeds, masks, conflict lists. PA → [LLM-guided][P-LLM]
127. Run DRC after every API-driven placement pass. PA → [LLM-guided][P-LLM]
128. Apply results as one undo step via IPC, respecting locked footprints. PA → [LLM-guided][P-LLM]
129. Deterministic, logged runs with per-module "why" listing binding constraints. PA → [LLM-guided][P-LLM]

## H. Placement benchmarks and metrics
130. Evaluate after routing with a pinned FreeRouting; report RR, routed length, vias, DRVs. PA → [metrics][P-metrics]
131. OmniLayout benchmark (1,681 designs; RR, PRWL, overlap, OoB, relation distance, S_ref). PA, VP → [metrics][P-metrics]
132. Cypress KiCad/Bookshelf suite and PCBWorld D3 as open placement benchmarks. PA → [metrics][P-metrics]
133. Four-tier placement metric stack (legality, proxies, domain rules, periodic ground truth). PA → [metrics][P-metrics]
134. Beat Chen DAC'25 (RR 0.62) and Quilter (0.84), not just academic placers. VP → [metrics][P-metrics]
135. Validate proxy-to-routed correlation before trusting proxies. PA, ST → [perf/fidelity][S-perf]

## I. Classical routing families
136. Lee maze routing; Soukup line-search + Lee-bubble hybrid. RA, RC → [families][R-families]
137. Admissible multi-layer A* heuristic (per-layer min trace + via costs). RA → [Freerouting][R-Freerouting]
138. Octilinear grid A* in Rust (KRT); grid A* with 1/√2 diagonal scaling (PcbRouter). RA → [families][R-families]
139. Hightower / Mikami–Tabuchi line probes; line-probe "Straighten" cleanup pass. RC → [families][R-families]
140. Channel routers (left-edge, dogleg, net merging, greedy), switchbox, gridless contour. RC → [families][R-families]
141. Single-row and monotonic BGA routing conditions for structured regions. RC → [families][R-families]
142. LLM dispatches pattern/channel routers to memory rows, connector buses, BGA perimeters. RC → [families][R-families]
143. Corner stitching and tile-expansion routing. RC → [families][R-families]
144. Finch gridless PCB routing; gEDA rectangle-expansion router with conflict pricing. RC → [families][R-families]
145. Specctra shape-based routing (conflict-tolerant first pass + push-and-shove). RC → [families][R-families]
146. Implicit connection graphs; DUNE gridless variable-width routing. RC → [families][R-families]
147. Freerouting A* over convex free-space rooms and doors. RA → [Freerouting][R-Freerouting]
148. tscircuit successive approximation over hypergraph capacity mesh. RA, ST → [families][R-families]
149. RRT-PCB continuous refinement of grid routes. CD → [families][R-families]
150. Security-aware routing: sequence-first prioritization + multilayer A* + RL test points. RC → [families][R-families]
151. OpenROAD PcbRouter as BSD-3 KiCad-native second baseline. RC → [families][R-families]

## J. Negotiation and rip-up
152. PathFinder (b+h)·p negotiated congestion with VPR defaults. RA, ST, CD → [PathFinder][R-PathFinder]
153. Formulation C: windowed multi-layer PathFinder grid router rerouting only offenders. ST → [PathFinder][R-PathFinder]
154. Negotiation inside detailed routers (FanoutNet MCR multi-term 3-D A* cost). RA → [PathFinder][R-PathFinder]
155. Situs "Globally Optimised Main" conflict-cost escalation. RC → [PathFinder][R-PathFinder]
156. PcbRouter escalating obstacle costs per fixed-order iteration, keep best. RA, RC → [PathFinder][R-PathFinder]
157. Expose the conflict-penalty schedule as typed knobs with LLM presets per board class. RC → [PathFinder][R-PathFinder]
158. Learn the schedule offline (CQL, history-aware LSTM). RA, RC → [PathFinder][R-PathFinder]
159. Conflict-tolerant "route everything" first pass as a feasibility probe. RC → [PathFinder][R-PathFinder]
160. Freerouting rip-up cost model with randomization and linear escalation. RA → [Freerouting][R-Freerouting]
161. KRT blocker attribution and count/near-target/bidir/mincut rip-up modes. RA → [families][R-families]
162. Rip/restore diff pairs as a unit. RA → [diff pairs][R-DP]
163. gEDA "easiest nets first on next pass" schedule. RC → [families][R-families]

## K. Topological routing
164. Homotopy-class (rubber-band sketch over CDT) as route representation. RC → [topological][R-topo]
165. SURF cut-capacity routability test that names the bottleneck. RC → [topological][R-topo]
166. O(n log n + m) rubber-band → octilinear/rectilinear conversion. RC → [topological][R-topo]
167. Spend LLM effort on topology, not angle (~5% octilinear penalty). RC → [topological][R-topo]
168. Persist routes as topology; re-tighten after placement nudges. RC → [topological][R-topo]
169. Simultaneous hierarchical global routing to avoid order dependence. RC → [topological][R-topo]
170. gEDA toporouter CDT + capacity/flow + A* over triangulation + ROAR passes. RC → [topological][R-topo]
171. TopoR route-all-with-violations then multicriteria optimization; topology-preserving moves. RC → [topological][R-topo]
172. Situs topological map → push-and-shove realization pattern. RC → [topological][R-topo]
173. Homotopic routing theory (Kaufmann–Mehlhorn linear-time, Hershberger–Snoeyink shortest paths). RC → [topological][R-topo]
174. Circular-Frame non-crossing chord routing for substrates. RC → [topological][R-topo]
175. JITX topo-routes; Topola Rust topological router. CD, ST → [topological][R-topo]
176. LLM homotopy hints verified topologically before geometry. CD → [topological][R-topo]

## L. Escape routing
177. Ozdal–Wong SER as longest path with forbidden pairs; max planar subset per layer. RC → [escape][R-escape]
178. Bus sequencing as longest common interval sequence (O(n log n)). RC → [escape][R-escape]
179. Minimum-layer and consecutive-layer bus escape. RC → [escape][R-escape]
180. Simultaneous pin assignment + escape (polynomial optimal). RC → [escape][R-escape]
181. SAT ordered escape. RC, ST → [escape][R-escape]
182. Correct diagonal-capacity network flow for 45° escape. RC → [escape][R-escape]
183. Staggered-array LP/ILP and flow escape. RC → [escape][R-escape]
184. Multi-commodity-flow ordered escape (MCMCF-Router 525 pins). RC, VP → [escape][R-escape]
185. LP network flow solving ordering + escape together. RC, ST → [escape][R-escape]
186. MonoSAT multi-layer escape with via types and proven minimal layer counts. RC → [escape][R-escape]
187. Negotiated escape (NCER), boundary escape (B-escape), multi-component SER. RC → [escape][R-escape]
188. Full-flow SER → refinement → gridless area routing with constraints each stage (Lin DAC'21). RC → [escape][R-escape]
189. Escape solver that can return "impossible" → stackup/HDI decision. RC → [escape][R-escape]
190. Pin/bank/bit swap as first-class LLM action with ECO back-annotation. RC → [escape][R-escape]
191. Learned dual warm starts for MCF escape; DQN escape (toy). RC → [escape][R-escape]
192. FanoutNet learned fanout locations and layers. RA → [ML/RL routing][R-ML]

## M. Length matching and buses
193. Lagrangian-relaxation length-resource allocation during routing. RC → [length/bus][R-length]
194. BSG-Route gridless area assignment for length matching. RC → [length/bus][R-length]
195. CAFE greedy target-length extension. RC → [length/bus][R-length]
196. Obstacle-aware, disordered-pin and multi-bus length-matched routing. RC → [length/bus][R-length]
197. LP → ILP → hierarchical-flow any-direction multilayer area assignment (topology-modifying). RC → [length/bus][R-length]
198. ACO with two-ant synchronized DP routing. RC → [length/bus][R-length]
199. Meander self-crosstalk speedup; ILP widening of meanders. RC → [length/bus][R-length]
200. Reserve meander area as extension budgets before routing. RC → [length/bus][R-length]
201. Explicit meander rules (pitch ≥3w, min corner radius, no tight meanders). RC → [length/bus][R-length]
202. Accordion / trombone / sawtooth / trapezoid-arc pattern generators. RC → [length/bus][R-length]
203. KiCad greedy fill-then-trim meander engine; chain-level tuning fields. RA, RC → [PNS][R-PNS]
204. Byte-lane auto-interactive delay tuning (Allegro AiDT). RC → [length/bus][R-length]
205. Single-detour bus untangling (DP; optimal O(n) one-sided; two-sided; internal detours). RC → [length/bus][R-length]
206. DAG-based topology-matching bus routing (IC contest follow-up). RC → [length/bus][R-length]
207. PACOR DME + MCF length-matched escape transplant. CD → [cross-domain][R-xdomain]

## N. Differential pairs
208. Median-point/centerline DP routing then offset. RC → [diff pairs][R-DP]
209. Median points + min-cost max-flow for simultaneous DP escape. RC → [diff pairs][R-DP]
210. Unified ILP with DP protection zones, matching, non-crossing, acute-angle limits. RC → [diff pairs][R-DP]
211. Chip-package-board LP/ILP co-design DP routing with variable reduction. RC → [diff pairs][R-DP]
212. KiCad PNS gateway enumeration (FitGateways) DP placer. RA, RC → [diff pairs][R-DP]
213. KRT pose-space (x, y, θ) centerline A* with Dubins heuristic. RA → [diff pairs][R-DP]
214. PcbRouter DP-first with median pseudo-pins. RA, RC → [diff pairs][R-DP]
215. Recommended DP pipeline: median points → centerline plan → PNS realization → skew tuning → return vias. RC → [diff pairs][R-DP]
216. Route and lock pairs before bulk autorouting. RC → [diff pairs][R-DP]

## O. Layer assignment and vias
217. Circle-graph via-free set + max-cut layer assignment (Hsu). RC → [layers/vias][R-vias]
218. Polynomial constrained via minimization for 2-layer boards; signed hypergraphs. RC → [layers/vias][R-vias]
219. Negotiation-based layer assignment reducing order sensitivity. RC → [layers/vias][R-vias]
220. K_v via-vs-length steepest-descent layer assignment. RC → [layers/vias][R-vias]
221. Via-cost knobs (Via Miser, via_costs) set per net class by LLM. RC → [layers/vias][R-vias]

## P. Net ordering
222. Order decides who gets good resources; negotiation protects completion. RC → [ordering][R-order]
223. Textbook heuristics (pins-in-bbox, length, criticality); junction-pin ordering. RC → [ordering][R-order]
224. KRT Maximum Planar Subset ordering (unrolled boundaries), inside-out, middle-out. RA → [ordering][R-order]
225. Toporouter pairwise-interaction scoring as a quantified conflict graph for the LLM. RC → [ordering][R-order]
226. LLM-set priority tiers and explicit first nets. RC, VP → [ordering][R-order]
227. Learned ordering (DreamerV3+FR, Ranking Cost, async RL, package ML, XRoute, IJCAI'25). RA, RC → [ordering][R-order]

## Q. ML/RL routing
228. DeepPCB actor/learner RL on a C++ simulator with Cooper setup agent. RA → [ML/RL routing][R-ML]
229. DeepPCB as optional cloud bulk router for non-SI nets. RA → [ML/RL routing][R-ML]
230. FanoutNet PPO fanout feeding a negotiated A*. RA → [ML/RL routing][R-ML]
231. DATE'23 polygon-partition MCTS router with dynamic re-partitioning invariant. CD → [ML/RL routing][R-ML]
232. MCTS + DNN rollout routing insensitive to order (He & Bao). RA, CD → [ML/RL routing][R-ML]
233. DreamerV3 world model choosing Freerouting net order. RA → [ML/RL routing][R-ML]
234. Ranking Cost ES-learned cost maps for A*. RA, RC → [ML/RL routing][R-ML]
235. Unet-Astar learned search-region masks. RC → [ML/RL routing][R-ML]
236. GPCB token-based routing (negative result 0.69% NRR). RA, VP → [ML/RL routing][R-ML]
237. VLSI generative routers (HubRouter, NeuralSteiner, DSBRouter, PRNet, DGR, GAT-Steiner) — low transfer. RA, RC → [ML/RL routing][R-ML]
238. Transferability ranking: control of classical routers > predictors as cost fields > generative drawing. RA, RC → [ML/RL routing][R-ML]
239. Beam search / MCTS over PNS waypoint, mode and layer choices with checkpoint/restore. RA → [PNS][R-PNS]

## R. LLM routing evidence and interfaces
240. Relations-not-coordinates rule (RAC 90.9% vs 23.2%; sandbox 21.0%). RA, VP → [LLM evidence][R-LLM]
241. Joint bundle realization over sequential relations. VP → [LLM evidence][R-LLM]
242. Engine-grounded interaction beats plan-and-execute and engine-free (PCBWorld). RA, VP → [PCBWorld][R-PCBWorld]
243. Three-layer router architecture: LLM relational planner, deterministic realizers, DRC/SI verifier. RA → [LLM evidence][R-LLM]
244. Routing relation vocabulary (route_class, pair, match_group, corridor, order, keepout, lock, return_vias, layer_pref, via_limit). RA, VP → [LLM evidence][R-LLM]
245. Topology sketch → capacity check → realization → DRC → per-predicate feedback. RA, RC → [LLM evidence][R-LLM]
246. KRT Claude skill generating replayable JSON routing plans. RA → [LLM evidence][R-LLM]
247. Pre-route and freeze critical nets before bulk autorouting. RA → [Freerouting][R-Freerouting]
248. Fix PCBWorld agent gaps (DRC echo, zones, netclass rules, delete actions, history, first-net planning, prefix cache) if building a step agent. VP → [PCBWorld][R-PCBWorld]
249. Rule out per-segment LLM routing on token cost. VP → [PCBWorld][R-PCBWorld]
250. Generate the sketch/flow plan from schematic semantics (fills the top-down planning gap). RC → [skepticism][R-skept]

## S. KiCad PNS and scripting
251. PNS as geometric realizer, repair and smoothing engine fed by a planner. RA → [PNS][R-PNS]
252. PCBWorld-Engine pybind11 bindings with deterministic, checkpointable PNS. RA, VP → [PNS][R-PNS]
253. IPC + KiCad 11 DSN export / SES import round trip for router integration. RA, ST → [PNS][R-PNS]
254. Headless PNS log replay (`qa/tools/pns`) for regression tests. RA → [PNS][R-PNS]

## T. Freerouting
255. Freerouting 2.6.x pinned as bulk router, fallback and routability judge, re-scored with KiCad DRC. RA, ST → [Freerouting][R-Freerouting]
256. Use Freerouting fidelity knobs (-mp, -mt 0, improvement threshold) inside loops. ST → [Freerouting][R-Freerouting]
257. Freerouting REST/MCP/CLI/Docker/Python-client integration paths. RA, ST → [Freerouting][R-Freerouting]
258. Improve Freerouting's fanout congestion and rip-up schedule (GPL-3 contribution). RA → [Freerouting][R-Freerouting]

## U. Routing evaluation
259. PCBWorld-Bench @1/@5, seed means, stated settings and potential function. RA, VP → [benchmarks][R-bench]
260. SI-constraint harness (coupling, skew, length spread, return vias). RA → [benchmarks][R-bench]
261. Practitioner metrics (via density, adjacent-layer overlap, min-clearance bottlenecks, plane-reference changes, bends). RC → [skepticism][R-skept]
262. Track LLM tokens and time per board. RA → [benchmarks][R-bench]

## V. Cross-domain transplants (see ranked list)
263. PCB-PSDL imperative placement language with shared variables. CD, VP → [scene][P-scene]
264. LLM-free coordinate-descent repair with area-weighted OT + edit-distance terms. CD, VP → [scene][P-scene]
265. LayoutVLM self-consistency relation filter. CD, VP → [scene][P-scene]
266. Frame-free / pin-anchored relations to avoid multi-hop drift (R3L). CD → [scene][P-scene]
267. Open-universe auto-repair (exception deletion, contradiction patterns, unsat restarts). CD → [scene][P-scene]
268. Centroid-direction no-overlap gradient + repel-then-no-repel schedule. CD → [scene][P-scene]
269. Holodeck anchor-first DFS baseline; MILP disjunction alternative. CD → [scene][P-scene]
270. SceneCraft relation hypergraph + spatial skill library of verified macros. CD → [scene][P-scene]
271. HSM hierarchical support regions + few-shot motifs. CD → [scene][P-scene]
272. DiagrammerGPT planner–auditor loop. CD → [scene][P-scene]
273. VLM pros/cons pairwise judge for ranking. CD → [scene][P-scene]
274. Render style as a tunable hyperparameter for VLM inputs. CD → [scene][P-scene]
275. LayoutGPT/LayoutPrompter/LayoutNUWA serialization, exemplars and rankers. CD → [scene][P-scene]
276. LLM stakeholder critic agents (urban fishbowl). CD → [scene][P-scene]
277. Synthetic-data inversion for a PCB diffusion placer. CD → [generative][P-gen]
278. Guided diffusion with legality dual ascent and DSL potentials. CD → [generative][P-gen]
279. Composable per-constraint energies (Diffusion-CCSP). CD → [generative][P-gen]
280. AlphaFold-style recycling with congestion/DRC features. CD → [generative][P-gen]
281. Motif-scaffolding inpainting around fixed mechanical parts. CD → [generative][P-gen]
282. Collision discriminator reranking (StructDiffusion). CD → [generative][P-gen]
283. jagua-rs hazards with typed filters for PCB keep-outs. CD, ST → [packing/graph][P-pack]
284. sparrow overlap-elimination GLS legalizer/compactor. CD, ST → [packing/graph][P-pack]
285. Sequence-pair completion of LLM relations. CD → [packing/graph][P-pack]
286. Block floorplanning as unequal-area facility layout. CD → [packing/graph][P-pack]
287. HOLA core/tree placement and aesthetic criteria score. CD → [packing/graph][P-pack]
288. IPSep-CoLa hard separation constraints for signal flow. CD → [packing/graph][P-pack]
289. Map-labeling SA/MaxSAT for silkscreen refdes. CD → [packing/graph][P-pack]
290. Metro-map MIP octilinear bus schematization. CD → [packing/graph][P-pack]
291. Sugiyama/ELK seeding; libavoid orthogonal previews; Cassowary constraint strengths. CD → [packing/graph][P-pack]
292. DEE pruning of rotation/side states + A*/ILP. CD → [packing/graph][P-pack]
293. ASP/WFC tiled-region generation; LLM→ASP contradiction checks. CD → [packing/graph][P-pack]
294. Rigid-flex panel assignment as constrained bin assignment. CD → [packing/graph][P-pack]
295. LLM as MAPF meta-controller (priorities, conflict choice, homotopy hints, costs). CD → [cross-domain][R-xdomain]
296. CBS / MC-CBS / UGPCB-CBS on Delaunay meshes. CD, VP → [cross-domain][R-xdomain]
297. PIBT/LaCAM fast first routing for dense fan-out with spread guidance. CD → [cross-domain][R-xdomain]
298. LLM as PUCT prior (LLM-MCTS, LLM-First Search, Scattered Forest Search). CD → [cross-domain][R-xdomain]
299. MCTS over coarse placement decisions with LLM prior. CD → [transplants](cross-domain-transplants.md)
300. Numberlink/Factorio SAT and ZDD window solving with LLM-chosen topology. CD → [cross-domain][R-xdomain]
301. Zachtronics post-solve metric histograms. CD → [cross-domain][R-xdomain]
302. Photonics curvy/bend-aware A*; harness bundling Pareto; package bump assignment; tensor-field directions. CD → [cross-domain][R-xdomain]
303. Warehouse QD pipeline (MAP-Elites + MILP repair + DSAGE surrogate) ported to placement. CD → [metaheuristics/QD][S-meta]
304. ELM LLM mutation emitters; QDAIF LLM quality/diversity judges; MarioGPT region resample + inpaint. CD → [metaheuristics/QD][S-meta]
305. Diverse (stratified) context for iterative LLM proposals. CD → [LLM-guided][P-LLM]

## W. Solvers and infrastructure
306. CP-SAT formulation A (rotation literals, opt2 intervals, keep-out boxes, L1 decap balls, exact HPWL, hints). ST → [CP-SAT][S-CPSAT]
307. Hierarchical CP-SAT: soft macros with aspect variants → top floorplan → windowed LNS. ST → [CP-SAT][S-CPSAT]
308. Window sub-model LNS (free parts as variables, neighbours fixed). ST → [CP-SAT][S-CPSAT]
309. Fix orientations upstream to make large CP-SAT models feasible. ST → [benchmarks][S-bench]
310. Dedicated packing subsolver worker (energetic/timetabling NoOverlap2D reasoning). ST → [CP-SAT][S-CPSAT]
311. 0.5 mm global grid, refine in windows; disconnected-region splitting; symmetry breaking. ST → [CP-SAT][S-CPSAT]
312. CDCL → CP-SAT warm-start hybrid. ST → [CP-SAT][S-CPSAT]
313. Fixed CP-SAT template + typed constraints instead of LLM-written models (Text2Zinc/CP-Bench). CD, ST → [CP-SAT][S-CPSAT]
314. Formulation B differentiable loss with decap, loop-area, SDF keep-out/outline, thermal, RUDY, net-crossing terms. ST → [analytical][S-analytical]
315. Lean JAX/PyTorch reimplementation of Cypress instead of DREAMPlace CUDA build. ST → [analytical][S-analytical]
316. SA/tabu in Rust with incremental HPWL/RUDY for detailed placement. ST → [metaheuristics/QD][S-meta]
317. pymoo / pyribs / cma / Nevergrad / DEAP for Pareto and diversity. ST → [metaheuristics/QD][S-meta]
318. LLM-evolved move operators and cost terms (ReEvo/EoH/AlphaEvolve/LLM4AD). ST, CD → [LLM-evolved][S-evolved]
319. CoEvoP&R restricted observable objective evolution with AST/autograd gates, cost tiers, negative memory. VP → [LLM-evolved][S-evolved]
320. OrderPlace three-stage proxy filter for evolved policies. VP → [LLM-evolved][S-evolved]
321. Evaluation cascade (toy legality → proxies → full routing + DRC). CD → [LLM-evolved][S-evolved]
322. Constructor functions for symmetric structures, search algorithms for irregular ones. CD → [LLM-evolved][S-evolved]
323. Optuna MOTPE/NSGA-II with LLAMBO warm start; LLM writes search space and picks from Pareto front. ST → [tuning][S-tuning]
324. AutoDMP-style multi-objective BO; SMAC multi-fidelity; BoTorch. ST → [tuning][S-tuning]
325. Shapely STRtree dwithin batch checks; full exact re-check ≤5 ms per accepted batch. ST → [geometry][S-geom]
326. pyclipper offsets and Minkowski NFPs (avoid pyclipr on Linux, avoid triangle). ST → [geometry][S-geom]
327. PythonCDT triangulation for channels/topology. ST → [geometry][S-geom]
328. Rust core via PyO3/maturin for hot loops; Python for orchestration. ST → [perf/fidelity][S-perf]
329. Five-level multi-fidelity ladder L0–L4 with `evaluate(candidate, level)` tool. ST → [perf/fidelity][S-perf]
330. Freerouting-on-2-layers as proxy calibration target. ST → [perf/fidelity][S-perf]

## X. Architecture-level recommendations
331. Hybrid constraint-centric pipeline: LLM intent → numeric placer → exact legalizer → metrics/conflicts → LLM. PA → [stack][S-stack]
332. Do not let the LLM emit coordinates or copper. PA, RA, RC, VP → [stack][S-stack]
333. Do not start with RL training. PA → [stack][S-stack]
334. Engine per net class (escape, pairs/impedance, length groups, bulk, repair). RA → [stack][S-stack]
335. GPL engines integrated freely under GPL-3.0-or-later; exclude Gurobi, OptiMathSAT, Triangle, GPL-2.0-only; MonoSAT with `-DGPL=OFF`. ST, RC → [stack][S-stack]
336. Benchmark-before-claiming: SA-PCB, NS-Place, Cypress, Chen DAC'25, Freerouting, KRT, PPO, DeepPCB baselines. PA, RA, VP → [stack][S-stack]
337. Key first experiments: relational planner vs routers on PCBWorld D3 with SI; topology plan + cut check ablation; VLM regions vs random. RA, RC, CD → [stack][S-stack]

[P-families]: ../topics/placement/algorithm-families.md
[P-placers]: ../topics/placement/pcb-placers-2022-2026.md
[P-sides]: ../topics/placement/sides-thermal-emc-reuse.md
[P-legal]: ../topics/placement/legalization.md
[P-analog]: ../topics/placement/analog-constraint-placement.md
[P-ML]: ../topics/placement/ml-rl-placement.md
[P-LLM]: ../topics/placement/llm-guided-placement.md
[P-metrics]: ../topics/placement/benchmarks-and-metrics.md
[P-gen]: ../topics/placement/generative-placement.md
[P-scene]: ../topics/placement/scene-layout-transplants.md
[P-pack]: ../topics/placement/packing-and-graph-drawing-transplants.md
[R-families]: ../topics/routing/algorithm-families.md
[R-PathFinder]: ../topics/routing/pathfinder-negotiated-congestion.md
[R-topo]: ../topics/routing/topological-routing.md
[R-escape]: ../topics/routing/escape-routing.md
[R-length]: ../topics/routing/length-matching-and-buses.md
[R-DP]: ../topics/routing/diff-pair-routing.md
[R-order]: ../topics/routing/net-ordering.md
[R-vias]: ../topics/routing/layer-assignment-and-vias.md
[R-ML]: ../topics/routing/ml-rl-routing.md
[R-PCBWorld]: ../topics/routing/pcbworld.md
[R-LLM]: ../topics/routing/llm-routing-evidence.md
[R-Freerouting]: ../topics/routing/freerouting.md
[R-PNS]: ../topics/routing/kicad-pns-router.md
[R-skept]: ../topics/routing/autorouter-skepticism.md
[R-bench]: ../topics/routing/benchmarks-and-datasets.md
[R-xdomain]: ../topics/routing/cross-domain-routing-transplants.md
[S-CPSAT]: ../topics/solvers/cp-sat-milp-smt.md
[S-analytical]: ../topics/solvers/analytical-differentiable.md
[S-meta]: ../topics/solvers/metaheuristics-and-qd.md
[S-evolved]: ../topics/solvers/llm-evolved-heuristics.md
[S-tuning]: ../topics/solvers/bayesian-tuning.md
[S-geom]: ../topics/solvers/geometry-libraries.md
[S-perf]: ../topics/solvers/performance-and-multifidelity.md
[S-bench]: ../topics/solvers/benchmarks.md
[S-stack]: ../topics/solvers/recommended-stack.md
