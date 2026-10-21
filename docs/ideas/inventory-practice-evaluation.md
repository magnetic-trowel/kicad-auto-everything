# Idea inventory: expert practice, trust, review, verification, constraint IR, benchmarks

This inventory lists every distinct approach, metric, checker, workflow idea and recommendation found in the practice/evaluation research cluster, one per line. Each line ends with links to the topic doc that holds the detail and evidence. Lines marked (I) are our inferences or synthesis, not source claims.

**Link keys**

| Key | Topic doc |
|---|---|
| SM | expert-state-machine |
| SW | sub-workflows-power-bga-ddr |
| BS | board-size-layers-stackup |
| LR | layout-reuse |
| GL | what-good-looks-like |
| DR | delegation-and-expert-review |
| AD | autorouter-distrust |
| LF | llm-field-reports |
| TR | trust-requirements |
| RC | review-checklist |
| CF1–CF5 | full checklist files: process/DFM/stackup; mechanical/placement/footprints; power/ground/HS/RF/EMC; thermal/routing/assembly/test; silk/HV/outputs/panel/flex |
| CK | checklist-sources |
| CS | critic-stack |
| RF | respin-and-fab-hold-data |
| LM | looks-right-metrics |
| ES | evaluation-stack |
| QM | quality-metrics |
| BM | benchmarks |
| BP | benchmark-plan |
| IR | constraint-ir |
| CM | constraint-models-compared |

## Workflow and process

1. Constraint-first expert order: mechanics/stackup/rules → PDN → fixed parts → floorplan → critical parts → decaps → rest → sanity check → fanout → critical routes → planes → bulk → tuning → stitching → DRC → outputs → [SM]
2. Backtracking state machine S0–S17 with critic-gated exits (I) → [SM]
3. Three review gates: constraint model, rough placement before routing, completion → [SM]
4. Git commit or PR per state; reviews tied to a commit; reviewee posts the checks performed → [SM]
5. Escalation ladder: local moves → re-floorplan → repackage/add layers/enlarge → drop or flag functions → ask a human → [SM]
6. Olney's ≥85% first test-route completion as the placement gate → [SM]
7. Autorouter near-completion as a layer-count adequacy test (VSE) → [BS]
8. Spend most search effort on placement, with a fast routability estimator as the inner objective (I) → [SM]
9. Staged reviews with distinct checklists: pre-layout, placement, critical routing, DFM → [SM]
10. Run DFM before quote, prototype and production, and whenever material, layers, density or assembly change → [SM]
11. Whole-assembly design review before assembly (NASA) → [SM]
12. Pre-routing setup: stackup into rules, PDN plan, via sizes per class, rule priority, router options → [SM]
13. Per-net highlight pass for nets longer than Manhattan or "spiral around the board" → [SM] [DR]
14. Separate per-IC layout review against datasheet guidance → [LR] [DR]
15. Effort anchors: 50 h simple, ~200 h CPU+memory (Feranec) → [SM]
16. Treat "90% placement" and "last 10% takes 90%" as folklore, not data → [SM]
17. Constraint definition is a dominant time sink, so make it cheap → [SM] [TR]
18. Grow the checklist after every escaped error (failure-log learning loop) → [RF] [CS]
19. Use Phil's Lab review order as a fixed LLM review script → [DR]
20. Floorplan of regions, anchors and pin-distance constraints confirmed by the user before any optimizer runs (I) → [SM]

## Placement practice

21. Place by cross-probing one part at a time, by function and importance → [SM] [LR]
22. Group each IC's private parts first, minimizing crossings between groups → [SM]
23. Order functional blocks by signal flow; separate power/analog/digital/RF → [SM]
24. Place all components before routing (Feranec Tip 095) → [SM]
25. Use autoplace only as a fit check → [BS]
26. Feranec order: defined parts → CPU+memory → other ICs → power → small parts → [SW]
27. BGA: trial placement, clear, then fan out and place from the centre, together → [SW]
28. Leave routing channels between memories and dense ICs → [SW]
29. Keep the power-stage transistor, inductor and caps tight → [SW]
30. Decap staging: nF at pins → µF near → bulk on the source path → [SW]
31. Place and route the converter input cap first → [SW]
32. Shorten power loops before widening traces → [SW]
33. SLVAFJ3 8-step converter order, including Kelvin sense through net ties → [SW]
34. Follow ordered datasheet layout-priority lists (bq25886) → [SW] [TR]
35. Crystal: nothing unrelated within 1 inch; ground guard; check routing near it → [RC] [CF2]
36. ESD and filters at connectors; series R at the source; terminators at the load → [CF2]
37. ADC anti-alias filter at the ADC input → [CF2]
38. Align bottom-side lands with top-side lands to open via channels → [CF2]
39. 80 mil rework clearance; inspection angle ⇒ spacing = tallest neighbour's height → [CF4]
40. Like parts in one orientation, pin-1s aligned, memories in a matrix → [LM]
41. Placement grids (100/25 mil; 0.05"; 0.1" headers; 5 mil origin) → [LM]
42. MLCCs away from V-scores, tabs and holes, aligned against flex → [CF2] [TR]
43. Space and orient nearby inductors against magnetic coupling (unsourced) → [CF2]
44. Heat sources near airflow/edge; small parts ≥1 mm from tall or hot parts → [CF2]
45. Switching converters away from sensitive analog → [CF2]
46. Group circuits that share supply/ground domains → [CF2]
47. Don't over-constrain board size; needed space is underestimated → [BS]
48. Rough place → swap-autoplace with "unmovable" parts → autoroute → star-ground fix → pours → [SM]
49. Group parts by ratsnest length and crossing count for initial placement → [SM]
50. Cluster by fewest unique nets → [SM]
51. Weighted total-ratsnest-length metric → [SM]
52. Paper sketch of functional "nuggets"; Pack and Move per block; group and move groups → [SM]
53. Reference-designator ranges per block (x3nn power, x5nn MCU) → [SM]
54. Agree fixed part positions with the mechanical engineer via STEP → [SM] [DR]
55. Sequential optimal packing as a seed, then an LLM feedback loop that "hardens" constraints → [SM]
56. CSS-grid-style placement constraints beat flexbox/cassowary → [SM]
57. Area-minimizing packing yields unroutable boards; force-directed placement is unpredictable → [SM]
58. Hierarchical decomposition to avoid "UNFEASIBLE" placements → [SM]
59. Frame placement as bin-packing → [SM]
60. Refine from a seed rather than place from scratch; constraint capture is the bottleneck (KRT) → [SM] [IR]
61. Lock connectors and fixed parts before any optimizer runs → [SM] [TR]
62. Treat placement and routing as coupled; expect pin, package and case changes during routing → [SM] [DR]

## Routing practice

63. Route matched, diff and critical nets first, by hand, then lock them → [SW]
64. TI ladder: power/ground and susceptible → clocked data → only <50 kHz to the autorouter → [SW]
65. Routing order power → high-speed → MCU → [SW]
66. Bartels flow: pre-route power vias, decaps and critical nets; autoroute; check net by net → [SW]
67. Escape-and-reserve channels for a whole bus before completing any member → [SW]
68. Same topology per signal group; stitching vias at reference changes → [SW]
69. Own via per GND/VCC pin and per decap; 10–20 mil power fanout → [SW]
70. Finish interactively to >90%, then autoroute the remainder → [AD]
71. Autoroute regular buses in cleared areas → [DR]
72. Autorouter as placement probe, then rip up → [AD]
73. Use router via counts and failure clusters as placement diagnostics → [AD] [LF]
74. Tournament of routers or routes; lock the best → [LF]
75. Pin key traces via the Python API, Freerouting for the rest → [LF]
76. The router must rip up its own earlier routes → [AD]
77. Feed routers quantitative info: keepouts, vias by ground pins, layer penalties → [TR]
78. EMI-aware autorouter as a long-term goal → [TR]
79. Topological, any-angle and 8-direction routing are underexplored → [AD]
80. Avoid any-angle routes and micro-wiggles for human editability → [GL] [LM]
81. Width only where current flows; polygons for power distribution → [GL]
82. Keep margin from rule minima → [GL]
83. Change layers across the same plane; transfer via very near; never cross split pairs → [GL]
84. No noisy traces on board edges; edge stitching → [CF3]
85. Route adjacent signal layers orthogonally → [CF3]
86. Penalize neat long parallel runs (crosstalk) → [GL] [LM]

## Board size, layers and stackup

87. Size estimate = Σ courtyard / utilization + edge keepouts, then a packer fit test (I) → [BS]
88. Layer count by generate-and-test: +2 layers at >70% channel use or <85–100% completion → [BS]
89. Stackup from the fab catalog with the impedance-width sanity check (craftyjon) → [BS]
90. Fab approves HDI/rigid-flex stackup before rules are set → [BS]
91. Evaluate interdependent fab parameters jointly → [BS]
92. Fab capability tiers; don't push fab limits; write fab notes in process order → [BS]
93. Hi-rel mode: IPC-2221 Class 3, sectional standard, coupons → [BS]
94. Hartley's stackups to use and avoid; signals one dielectric from a plane → [BS] [GL]
95. Rise time sets bandwidth: F(GHz) = 0.5/Tr(ns) → [GL]
96. Prefer ICs with paired power/ground pins and the lowest adequate Vcc → [GL]
97. Two-layer rules: power over ground, length:width ≤3:1, pour under HS traces → [BS]
98. Panel efficiency and board thickness as explicit decisions → [BS]

## Reuse

99. Copy the EVM/datasheet layout as the least-risk path → [LR] [SW]
100. EVM-layout design-block library keyed by MPN and topology (I) → [LR]
101. Save agent-learned blocks only after they pass critics (I) → [LR]
102. Hierarchical sheets → per-sheet rule areas as floorplan cells → [LR]
103. Detect channels by isomorphism and copy with Repeat Layout; prefer sheet-based channels → [LR]
104. Version-gate reuse (≥9 multichannel/classes; ≥10 design blocks) → [LR]
105. Compare the schematic with a known-working reference board → [LR]
106. Treat app notes and EVMs as wrong until proven right; run critics on them → [LR] [GL]
107. Don't copy popular open-source layouts (Arduino Uno counterexample) → [LR]
108. Retrieval index keyed by (footprint/MPN, passives, pin functions) that supplies relative-pose seeds (I) → [LR]
109. Compile datasheet guidance into IR constraints, not copied geometry (I) → [LR] [IR]
110. Quilter-style schematic-pattern detection as the first-pass intent extractor → [IR] [LR]
111. Circuit-port forwarding so reusable blocks carry their constraints (JITX) → [LR] [CM]
112. atopile sub-build plus "pull group" layout reuse → [LR]
113. Rooms that move their components, generated from component classes (Altium) → [LR] [CM]
114. Multichannel as a placement multiplier after one channel is done → [LR]

## Review, checklists and critics

115. 299-item master checklist with severity and automation tags → [RC] [CF1]
116. A semantic annotation layer (roles, currents, voltages, frequencies) is the key automation enabler → [RC]
117. Three-tier critic stack: A (DRC), S (semantic geometry), J (LLM judge + simulation) → [CS]
118. Generate `.kicad_dru` from roles + fab profile and map violations to checklist IDs → [CS]
119. Audit severity overrides, exclusions and "ignore" before trusting DRC → [CS] [RC]
120. Group DRC violations by root cause → [CS]
121. Finding record: measured, threshold, threshold source, objects, evidence PNG, fix → [CS]
122. Tier-S priority list of 11 critics → [CS]
123. Tier-J structured packet; pass/fail/uncertain; uncertain goes to a human → [CS]
124. Hand HS-08/14, FLX-07 and PWR-01 EMI to simulators → [CS]
125. Critical items gate; Major items penalize; minor items and aesthetics are soft → [CS]
126. Threshold provenance: datasheet > fab profile > house default; label tool heuristics → [CS]
127. Fab/assembler profiles are mandatory because thresholds conflict → [RC] [CK]
128. Critic priority: documentation/spec → geometry → physics → [RF] [CS]
129. Output-package checks: RS-274X/X2, Excellon, 1:1, IPC-356, readme, no CAD files → [CF5]
130. Net-class coverage report for controlled-impedance nets (STK-09) → [RC]
131. Margin-to-limit DFM report → [RC] [CF1]
132. Verify each suspected issue against a primary source before reporting → [CS] [CF1]
133. "Never trust a clean ERC": walk each IC's power pins, mandatory passives, straps, VFB dividers → [CS] [RF]
134. Audit order "run the real checkers first" (Adom) → [CS]
135. Severity-ranked report with refs, pins, why and one concrete fix → [CS]
136. Footprint vs datasheet images side by side → [DR]
137. Adversarial datasheet-comparison review prompt → [DR]
138. Mandatory second deep-dive pinout pass → [DR]
139. Multiple DRC tools with fab DFM as source of truth; watch for checker false positives → [DR]
140. Same-LLM audit of its own changes catches introduced bugs → [DR]
141. Unit-test board generators → [DR]
142. Visual red-flag list: random decaps, thick traces, backwards connectors, needless BGAs, length matching → [DR]
143. Connector-orientation and supplier-footprint-orientation checks → [LF] [TR]
144. "Trace width closely matches reference design for chip" check → [LF]
145. "Opamp schematic layout conventional" check → [LF]
146. Readable schematic as a precondition for review → [DR]
147. Project web page with a chronological change log and visualizations → [DR]
148. Test-point distance L = 0.29·H + 0.7 mm → [CF4]
149. Copper balance of symmetric layer pairs within ~20% (15% for double reflow) → [CF1]
150. ≥1 ground return per 9 signals in cables (1 per 4 if >1 ft) → [CF3]
151. Termination threshold at trace length >λ/10 (FCC) or >λ/50 → [CF3]
152. Via-fence pitch ≤λ/8 → [CF3]
153. Simulate nets longer than 1/6 of rise time → [CF3]
154. HS traces ≥1.5W from voids and ≥90 mil from plane edges; stitching caps ≤1 µF → [RC] [CF3]
155. Via stubs <15 mil or backdrill; ~30 mil antipads; equal via counts; SMDs ≤0603; breakout within 0.25" → [RC] [CF3]
156. Tombstone copper-ratio checks (UWARG <2×; kicad-happy <0.3) → [RC] [CF4]
157. Assembler passive spacing table; part-to-hole ≥8 mil → [CF4]
158. Fiducial rules: 3 global, 2 local, 40–118 mil → [RC] [CF4]
159. Split grounds only for audio/precision <~100 kHz, joined at a single point → [CF3]
160. Respin framing: 2.8–2.9 respins/project; ~60% of designers at 1–5/year; <2–20% of designs with no TQs → [RF]
161. Fab-hold ranking (stackup 28%, impedance 22%, drill-to-copper 18%, notes 15%, BGA ring 12%) drives critic order → [RF]
162. Extract per-IC rules from datasheet "Layout Guidelines" sections at intake → [SM] [LR]
163. Keep source keys next to every threshold so conflicts stay visible (I) → [CK]

## "Looks right" and quality metrics

164. Orientation entropy per part class → [LM]
165. Pin-1 agreement fraction → [LM]
166. Grid-snap ratio → [LM]
167. Collinearity score → [LM]
168. HPWL/MST plus airwire crossing count → [LM]
169. Routed/Manhattan ratio outliers ("no scenic routes") → [LM]
170. Hot-loop polygon area and switch-node copper area → [LM]
171. Decap distance plus Spearman value-vs-distance order → [LM]
172. ≤2 text directions; mirrored bottom text → [LM]
173. Geographic designator rank correlation → [LM]
174. Pad-exit-style violations → [LM]
175. Coupled parallel-run length → [LM]
176. Channel congruence (RMS pose deviation after isomorphism) → [LM]
177. Signal-flow monotonicity → [LM]
178. Turn count/wiggle and any-angle fraction (I) → [LM]
179. Power-net width consistency vs declared current (I) → [LM]
180. Connector edge-facing and "which way is up" consistency (I) → [LM]
181. Pair every neatness term with a coupling penalty → [LM] [GL]
182. Taste = physics proxies + convention proxies + company style profile → [GL]
183. Field-containment check per critical net: plane adjacency, splits, transfer via, loop area → [GL]
184. Per-company style profile as configuration (I) → [LM] [GL]
185. PCBWorld CP, potential gain, @5 protocol → [QM]
186. OmniRouting PR/NRR/PRR/Open/PShort/NShort/Clr./Dist./Polygon/TWL/vias/layers/RT → [QM]
187. MGS human-similarity as a diagnostic only → [QM]
188. Normalize against human scores (human NRR 93.58%) → [QM]
189. Cypress routability protocol (Freerouting v1.9.0, two free layers) → [QM] [BM]
190. Quilter PRCs as physics metrics with units and pass criteria → [QM] [CM]
191. Intent conformance as PRC pass rate per constraint kind → [QM] [BP]
192. Freerouting `V2_CONTINUOUS` and `V2_LOWER_BOUND` scores → [QM]
193. Union metric set: gates, routing, placement, physics, human-relative → [QM]
194. Process metrics: out-of-scope edits, determinism, setup minutes, prediction accuracy (I) → [QM] [BP]
195. HPWL and crossings are blind to intent; add intent and convention metrics → [QM] [LM]

## Trust, UX and agent behaviour

196. Deterministic tools decide correctness; the LLM never self-judges → [TR]
197. Bounded, commanded chunks with review between them → [TR]
198. Predictable automation without settings; the human "plots a course" → [TR]
199. Never touch locked or known-good work; minimum change → [TR] [DR]
200. Before/after render with a physical rationale per step (I) → [TR]
201. 100% routed is never a terminal state → [TR]
202. Agent-immutable scoring harness (anti scoreboard gaming) → [TR] [BP]
203. State the expected result before running checks (Bogatin #9) → [TR] [GL]
204. Determinism across board revisions → [TR]
205. Cheaper than hand layout, setup included → [TR]
206. Data provenance and IP; no training on user data without consent → [TR]
207. Declarative constraints ("this trace carries 100 mA"), lockfiles, tests → [TR]
208. Progressive constraints "like CSS" → [TR]
209. Visual constraint entry (click net, "5A", "route shortest possible") → [TR]
210. Spreadsheet constraint entry (OrCAD-style) → [TR]
211. Per-zone and per-net-type rule sets with priorities → [TR]
212. Escape hatch from layout-as-code to the GUI → [TR]
213. Co-creation and conversational UI; cruise control, not chauffeur; sketch routing → [TR]
214. Guided commands ("Connect this 32 bit databus") with star-ground, shunt, HV and guard-ring awareness → [TR]
215. "Do DRC, fix whatever it tosses and show me what you did" → [TR]
216. Incremental-ECO mode (greenfield is hard, edits are easy) → [TR]
217. Undo, commits and project snapshots before mutating edits → [TR] [LF]
218. Ask explicit questions about never-delegate items → [DR] [TR]
219. Do the delegable work perfectly first → [DR] [TR]
220. Ship the reviewer/analyzer before the producer → [LF] [TR]
221. "Good but not perfect"; a "well-constrained one-step-up from autorouter" for simple boards → [TR]
222. Boilerplate prototypes are valuable even without analog/HS → [LF]
223. Leave routing to humans who enjoy it (optional per block) (I) → [TR]
224. Prove quality with evidence before claiming it → [TR]
225. Reliable tool round-trips and fixed-part marking → [AD]
226. AI silkscreen placement → [TR]
227. Tedious N-copy replication → [DR] [TR]
228. Pin planning, review against requirements, part suitability → [TR]
229. Parametric APIs (DigiKey) over model recall → [TR]
230. Standardized JSON/XML pin maps → [TR]
231. Accuracy bar: "60 percent of the tasks at a 50 percent accuracy rate is absolutely useless" → [TR]
232. Hard-case list (SMPS loop, decoupling impedance, return path, BGA escape, connector orientation, power width, pin swaps, greedy dead ends, …) → [TR]

## LLM roles and failure modes

233. The LLM works upstream of and around the solver: constraints, net priority, DRC config, floorplan fixes, judging → [LF]
234. LLM reads routing-failure clusters and proposes geometric fixes (stagger U6–U10) → [LF]
235. LLM authors DRC rules for classical routers → [LF]
236. LLM sorts nets into manual vs autorouted → [LF]
237. LLM as datasheet extractor → [LF]
238. LLM review as cheap insurance ($1–2 of tokens vs $70–80 boards) → [LF]
239. LLM-written analysis code validated against measurement (DC IR FEA, AC PDN vs DSO FRA) → [LF]
240. Parsers give the LLM "eyes"; post-processed data beats raw files → [LF]
241. "The parsers do the work, the LLM generates the narrative" → [DR] [CS]
242. Don't let the LLM write its own placer or router → [LF]
243. Guard the known failure modes: connectors, endless loops, huge schematics, BGA escape, micro-wiggles, unrequested edits, DRC slop, open nets at export, odd self-imposed rules → [LF]
244. LLMs don't reliably use only datasheet information → [LF]
245. Guard against LLM overconfidence → [LF]
246. Datasheet footnote traps (e.g. "3.3v max 80MHz") → [TR]
247. Datasheets are not ground truth (old, overkill, wrong, NDA) → [GL] [LR]
248. Decoupling as a loop/cross-impedance target; distance is only a proxy → [TR]
249. Layout is circuit design with unknown component values → [DR]
250. Pin, part and package swaps as layout moves with schematic back-annotation → [DR]
251. Schematic order communicates layout order → [SM]
252. Close the feedback-loop gap with a fast verification loop → [LF]
253. Training data is scarce; collect bad examples with their fixes → [LF] [BP]
254. An image-transformer router would need >10M boards → [LF]
255. Parallel seeded runs with ranked candidates (Quilter) → [LF]
256. LLM orchestrates router jobs with little token use → [LF]
257. Sub-second tool operations vs minutes of LLM thinking → [TR]
258. Code-first EDA (atopile) to avoid GUI context waste → [LF]
259. Deterministic scripts with AI only at judgment calls; per-module `board.yaml` hard-errors on unsafe pins → [DR]
260. `git describe` revision on the silkscreen → [DR]
261. AI teaching itself from layout plus simulation (Feranec) → [LF]
262. Harness with built-in EMC/EMI/SI/PI/thermal solvers → [AD]

## Constraint and intent IR

263. Three constraint-model families: rule scoping, object-centric managers, placement relations → [CM]
264. IR as a superset that compiles to `.kicad_dru`, checkers and penalties → [IR]
265. Explicit resolution semantics; specificity emitted general→specific to KiCad → [IR] [CM]
266. Tags with inheritance bound to KiCad selectors → [IR]
267. Topologies with bridging/terminating pin models for timing → [IR] [CM]
268. Match groups resolved to pin pairs (Match vs Relative) → [CM]
269. Allegro electrical modes as vocabulary (stub, exposed length, max parallel, return-path DRC) → [CM]
270. Native `proximity(pad, pad, max, basis)` primitive → [IR]
271. Native `via_to_plane` primitive → [IR]
272. `loop_area` and `layer_switch_count` primitives → [IR]
273. `region`, `cluster_tight`, `edge_placement` and `symmetry` primitives → [IR]
274. `overheated_length` primitive → [IR]
275. High-level intents (bypass, switcher, DDR lane, USB pair) expand into primitives → [IR]
276. Hard/soft split with a monotone optimizer gate on hard constraints → [IR]
277. Provenance, confidence and `confirmed_by` per constraint → [IR]
278. DFX-like findings and waivers channel → [IR] [CM]
279. IPC-2581 import/export for impedance and loss → [IR] [CM]
280. LLM proposes with evidence → human confirms → PRCs grade → [IR]
281. Strict schema; unknown keys refused (KRT) → [IR] [CM]
282. Practitioner `intent.yaml` field list → [IR]
283. tscircuit `calc()` pad-relative placement and `drccheck` custom checks as models → [CM]
284. atopile tolerance assertions as an electrical-intent model → [CM]
285. FloorSet multi-instantiation and boundary constraints → [CM]
286. ALIGN `UserConstraint` expansion into solver terms → [CM]
287. GNN symmetry extraction; LLM priors for Bayesian optimization (LLANA) → [IR]
288. PCBSchemaGen per-IC knowledge graph + 5-layer verifier with pin-level localization → [IR]
289. Extraction completeness (~70% schematic-only → ~95% with datasheets) as an evaluation target → [IR]
290. Copy the commercial input contract: fixed outline, pre-placed connectors, locked copper, named planes, confirmed constraints → [CM]
291. Target the high-speed constraint space DeepPCB and Quilter leave open → [IR]

## KiCad implementation (compile and backend)

292. Strict `.kicad_dru` emitter: one condition, one constraint type per rule, parenthesized, general→specific → [IR]
293. Canonical units mm/deg/ps; never `th`, `"` or `rad` → [IR]
294. Rule names prefixed `IR:<id>`; map violations by regex on `description` → [IR] [ES]
295. Lint generated rules by running `kicad-cli` on a scratch copy → [IR]
296. Avoid deprecated `insideArea`/`insideCourtyard`/`memberOf` → [IR]
297. Don't rely on `ignore` severity to constrain the router → [IR]
298. Time-domain first: tuning profiles via `SetNetClasses`, `ps` length/skew, `within_diff_pairs` → [IR]
299. Four-channel KiCad 10 backend: IPC CRUD, `.kicad_dru` writes, `kicad-cli` referee, SWIG DSN/SES helper → [ES]
300. Poll after the async `RefillZones` → [ES]
301. Lock copper before SES import; strip the SES placement section → [ES]
302. Diff KiCad vs Freerouting DRC JSON to expose DSN translation losses → [ES]
303. Single-call Freerouting tool that returns scores, not geometry → [ES]
304. Freerouting `/drc/summary` congestion hotspots as LLM input → [ES]
305. Library footprint placement via `ParseAndCreateItemsFromString` + `UpdateItems` net pass → [ES]
306. KiCad 11 `CustomRule` protobuf as a second compile target → [IR]
307. Adopt master `return_path`/net-chain rules when they ship → [IR]
308. Keep SWIG in a short-lived helper process; plan for its removal in KiCad 11 → [ES]
309. Check for diff-pair name false positives (XTAL_P/N) → [ES]
310. KiCad-enforceable intents (side, orientation, area, courtyard) vs custom-only (pad distance, alignment, symmetry, loop area) → [IR] [CS]
311. Component classes as role carriers queried with `hasComponentClass()` → [IR] [CS]

## Verification tools and tiers

312. T0–T3 tiered evaluation → [ES]
313. `kicad-cli` DRC JSON with parity, refill, exit code 5 → [ES]
314. Transcalc Z0 and IPC-2221 widths inside the loop → [ES]
315. `return_path` raster flags and loop-area estimate → [ES]
316. emcvisual Biot–Savart near/far field → [ES]
317. padne / KiPI / Ki-PIDA for IR drop, PDN impedance, coupled noise, electro-thermal → [ES]
318. PCB_SI_Toolkit measured-vs-limit checks → [ES]
319. si-wrapper slicing + gerber2ems/openEMS: CI-able and VNA-validated → [ES]
320. Palace C/L extraction; FastHenry/FastCap; scikit-rf → [ES]
321. Antmicro FreeCAD/CalculiX thermal; Salome/Elmer current conduction → [ES]
322. Analytic thermal proxies in the loop; FEM only at sign-off → [ES]
323. Calibrate proxies against T3 before using them as rewards → [ES]
324. Train surrogates on synthetic boards labelled by fast physics tools → [ES]
325. Surrogate precedents: PDN DNN, DevFormer DPP, SI eye, crosstalk → [ES]
326. Return compact summaries, not geometry, to the LLM → [ES]
327. Measure our own tier runtimes (none published) (I) → [ES]

## Benchmarks and data

328. PCBWorld D3 routing leaderboard under the @5 protocol → [BP] [BM]
329. Re-run Freerouting 2.5.0 baselines (published numbers are 2.1.0) → [BM] [BP]
330. Cypress-protocol placement leaderboard → [BP]
331. Placement-stripped PCBWorld variants routed by a fixed router → [BP]
332. PCBWorld construction recipe for our own corpus → [BP] [BM]
333. Intent track with human-confirmed annotations → [BP]
334. Physics track (decap PRCs, return path, IR drop, openEMS) → [BP]
335. Human-relative diagnostics (MGS, WL/via/HPWL ratios) → [BP]
336. Unit suites: synthetic per IR kind, DPP, FloorSet-style mixes → [BP]
337. Hygiene: pinned KiCad, licence manifest, private held-out split, re-run DRC on saved files → [BP]
338. Act through the engine (CP 0.65 interactive vs 0.19 plan-execute vs 0.02 engine-free) → [BM]
339. Feedback quality matters more than iteration count (OmniRouting) → [BM]
340. LLM-only routing is not competitive (0.65/0.00 vs Freerouting 0.80/0.78) → [BM] [LF]
341. Golden-task suites (18/18) and devbisme's AI-tool test repo → [BM]
342. EEBench-style deterministic grading (SPICE corners, BOM cost) → [BM]
343. Controlled human vs autorouter vs LLM comparison with measurements → [BP]
344. Corpus-scale regression harness (kicad-happy: 5,800+ repos) → [BM] [CS]
345. fastroute `--parity` as a determinism reference → [BM]
346. Checklist track seeded with known-bad boards and escaped-error cases (I) → [BP]
347. Blind expert review to calibrate convention metrics (I) → [BP] [LM]
348. Trust/process track: scope violations, determinism, setup time, prediction accuracy (I) → [BP]

[SM]: ../topics/workflow/expert-state-machine.md
[SW]: ../topics/workflow/sub-workflows-power-bga-ddr.md
[BS]: ../topics/workflow/board-size-layers-stackup.md
[LR]: ../topics/workflow/layout-reuse.md
[GL]: ../topics/workflow/what-good-looks-like.md
[DR]: ../topics/workflow/delegation-and-expert-review.md
[AD]: ../topics/workflow/autorouter-distrust.md
[LF]: ../topics/workflow/llm-field-reports.md
[TR]: ../topics/workflow/trust-requirements.md
[RC]: ../topics/verification/review-checklist.md
[CF1]: ../topics/verification/checklist-full-process-dfm-stackup.md
[CF2]: ../topics/verification/checklist-full-mechanical-placement-footprints.md
[CF3]: ../topics/verification/checklist-full-power-ground-hs-rf-emc.md
[CF4]: ../topics/verification/checklist-full-thermal-routing-assembly-test.md
[CF5]: ../topics/verification/checklist-full-silk-hv-outputs-panel-flex.md
[CK]: ../topics/verification/checklist-sources.md
[CS]: ../topics/verification/critic-stack.md
[RF]: ../topics/verification/respin-and-fab-hold-data.md
[LM]: ../topics/verification/looks-right-metrics.md
[ES]: ../topics/verification/evaluation-stack.md
[QM]: ../topics/verification/quality-metrics.md
[BM]: ../topics/verification/benchmarks.md
[BP]: ../topics/verification/benchmark-plan.md
[IR]: ../topics/architecture/constraint-ir.md
[CM]: ../topics/architecture/constraint-models-compared.md
