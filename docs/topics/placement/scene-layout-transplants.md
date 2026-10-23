# LLM layout generation in other fields (scenes, UI, floorplans, CAD) → PCB placement

**TL;DR**
- Three generations: (1) LLM emits absolute coordinates (collisions); (2) LLM emits relational constraints, a solver places (Holodeck: MRR 0.706 vs 0.364 for coordinates); (3) **LLM writes structured relative-placement code/relations and an LLM-free numeric repair stays close to that intent** (Brown PSDL: preferred 82.9% over a declarative DSL and 94.3% over Holodeck; LayoutVLM +40.8 PSA).
- **Top PCB transplant: a "PCB-PSDL" imperative placement language** with pin handles, local frames and shared variables (`row`, `ring`), repaired by greedy local search over constant and direction rewrites, minimizing loss + an edit distance to the LLM's program (d_edit, which keeps its intent) + an area-weighted transport term (VP-corrected).
- **Self-consistency filter** (LayoutVLM): keep only LLM relations already satisfied by its own rough poses (removing it cost 12.4 PSA).
- Avoid long chains of relative references (R3L drift) and global crossing-free geometry (PlanarBench) — anchor relations to a parent IC's pins or the board frame.
- A VLM asked to list **pros and cons before choosing** between two layouts agreed with humans ~77% — a cheap ranking judge.

## Key facts

| System | Representation / solver | Result |
|---|---|---|
| LayoutGPT (NeurIPS'23) | CSS serialization, 256 px | +20–40% numeric/spatial correctness over T2I [S] |
| LayoutPrompter (NeurIPS'23) | In-context: serialization, dynamic exemplars, ranker over samples | Matches trained SOTA, low data [S] |
| LayoutNUWA (ICLR'24) | HTML with masked slots ("Code Instruct Tuning") | >50% gains on some sets [S] |
| **Holodeck** (CVPR'24, [arXiv 2312.09067](https://arxiv.org/abs/2312.09067) [P]) | 10 soft relation types in 5 groups (edge, middle; near, far; in front of, side of, above, on top of; center aligned; face to); hard collision/boundary; LLM picks **anchor object**, DFS on grid with 4 rotations for fixed 30 s maximizing satisfied constraints; MILP alternative (Gurobi, binary disjunctions; near/far in objective) | Human MRR: constraints 0.706, all-at-edge 0.645, LLM coordinates 0.364, random 0.369; preferred 64.4% vs ProcTHOR; Holodeck 2.0 types (type, relation, source, target) + backtracking DFS with topological ordering |
| **LayoutVLM** (CVPR'25, [arXiv 2412.02193](https://arxiv.org/abs/2412.02193) [P]) | Numeric initial poses + 5 frame-free differentiable relations (`distance(a,b,lo,hi)`, `on_top_of`, `align_with`, `point_towards`, `against_wall`); **self-consistent decoding** 𝟙[L(p̂) ≤ ε]·L(p); DIoU collision; projected gradient descent into room; renders with 2 m coordinate points and facing arrows; group-by-group placement with re-render | CF/IB/PSA 81.8/94.9/58.8 vs LayoutGPT 83.8/24.2/16.6, Holodeck 77.8/8.1/5.6; ablation PSA: w/o numeric init 41.0, w/o spatial constraints 6.7, w/o self-consistency 46.4, w/o image 48.2; LoRA on relation representation beats raw poses |
| **Open-universe DSL** (Brown 2024, [arXiv 2403.09675](https://arxiv.org/abs/2403.09675) [P]) | Python-embedded declarative relations (adjacent, aligned, facing, on, surround); gradient solver; **centroid-direction no-overlap gradient** (fixes flat "+"-shaped overlap loss); repel-then-no-repel schedule | Auto-repair: delete lines raising exceptions; 6 contradiction subgraph patterns (delete last-declared); unsat after 10 non-zero restarts → regenerate |
| **PSDL imperative programs** (Gumin … Ritchie; one work, [arXiv 2504.05482](https://arxiv.org/abs/2504.05482) / [2510.16147](https://arxiv.org/abs/2510.16147) [P], VP-corrected) | Objects expose `.min/.max/.center/.facing`; assignments like `chair.max.x = table.min.x - 0.1`; loops + **shared variables**; `set_coordinate_frame`; repair = greedy local search minimizing loss + d_edit(P, P₀) + **volume-weighted optimal-transport d_OT(L, L₀)**; constant edits ×(±4^Y), Y~U[−1,1], 10 samples per constant; 4 cardinal direction rewrites | **82.9% preferred over DeclBase, 94.3% over Holodeck** (95.2% at ≥40 objects); ~7.13 edits/scene; errors Claude 3.5 17.57 → 2.10, GPT-4o 17.80 → 3.34; repair ablation: gradient descent fixes 96% (61.4% pref), LLM self-repair 5.7 left in 106.7 s, flat local search 93.5%, PSDL 91% in 9.3 s but wins preference because relations survive; shared variables ~3× faster search; VLM pros/cons judge ~77% human agreement (VQAScore near chance); limits: 4 orientations, no identity/x-y swap fixes |
| **SceneCraft** (ICML'24, [arXiv 2403.01248](https://arxiv.org/abs/2403.01248) [P]) | Relation bipartite graph (relation nodes as hyperedges over asset subsets); LLM writes Blender code; GPT-V critiques renders; outer-loop **spatial skill library** | +45.1%/40.9% CLIP over BlenderGPT |
| R3L (2026) | Multi-hop relative relations accumulate frame errors; fix by invariant decomposition, imagine-and-revise, global-to-local reparameterization | [P-abstract] |
| HSM (2025) | Hierarchical support regions filled with motifs learned from few examples | [P-abstract] |
| RoomCraft, I-Design, LLplace, DiagrammerGPT (planner–auditor loop), Make It Home (SA + Metropolis–Hastings over ergonomic priors) | — | [S] |
| CAD code | Text-to-CadQuery 58.8 → 69.3% exact match; CAD-Coder GRPO with Chamfer reward (CD 6.54 vs 29.29) | [S] |

**Direct evidence on LLM spatial ability**: **PlanarBench** — crossing-free ASCII drawings of 2–7-vertex planar graphs; edge count predicts difficulty (r = −0.85) far better than vertex count; best 159.5/199; frontier failures remain ([arXiv 2606.02010](https://arxiv.org/abs/2606.02010) [P]). **Graph Drawing for LLMs**: layout style and readability of rendered graphs change GPT-4o/Claude 3.7 accuracy ([arXiv 2505.03678](https://arxiv.org/abs/2505.03678) [P]); an earlier EuroVis short paper found ChatGPT could apply graph layout algorithms "not perfect, but promising" [S]. LLMs writing constraint models: Text2Zinc ≤25.39% (MiniZinc); CP-Bench ~70% with docs, sampling and self-verification, Python (CPMpy, CP-SAT) easier ([solvers/llm-evolved-heuristics](../solvers/llm-evolved-heuristics.md)).

**Multi-agent critique precedents**: LLM participatory urban planning (planner + resident agents in a "fishbowl"; SOTA satisfaction on two Beijing regions) [S]; LayoutCopilot ([analog](analog-constraint-placement.md)).

## Recommendations for our system
- **PCB-PSDL** [I]: footprints expose `.min/.max/.center` (courtyard), `.facing` ∈ {0,90,180,270}, `.side`, pin handles (`U1.pin["VDD"]`); operators `set_frame(U1)`, `row(R1..R8, pitch=p)`, `ring(caps, around=U1, gap=g)` with shared variables; repair by greedy local search over constant rewrites (×(±4^Y)) and 90° direction rewrites, minimizing loss + d_edit(P, P₀) + d_OT; loss = courtyard overlap + outline protrusion + keep-out intrusion + hole/connector clearance + decap-to-pin + crystal loop; d_OT weighted by footprint area so ICs/connectors stay put; regenerate via LLM only on identity/semantic errors. PCBs are 4-orientation, matching PSDL's main limit.
- Hybrid: ask for rough (x, y, θ) **and** relations, keep self-consistent relations, DIoU courtyard loss, projected GD into the outline, group-by-group with re-render [I].
- Use frame-free or pin-anchored relations; detect PCB contradiction patterns (`edge(J1,W)` + `edge(J1,E)`, 12 caps "within 1 mm", part on both sides); declare unsat after k restarts; centroid no-overlap gradient + repel schedule in gradient placers [I].
- Holodeck-style anchor-first 30 s DFS (connectors/holes → MCU → rest) as a baseline for <50 parts; switch to gradient/PSDL repair above ~50–80 [I].
- Relation hypergraph + **skill library** of verified macros (QFN decap ring, buck hot loop, USB-C + ESD, crystal + load caps); HSM-style levels board → block regions (KiCad rooms) → IC neighbourhoods → pin slots [I].
- Board-plan planner–auditor loop (DiagrammerGPT); VLM pros/cons pairwise judge for best-of-N; treat render style as a hyperparameter; PCB subsystem critic agents (PI, SI, thermal, DFM, mechanical) [I].

## Conflicts and open questions
- No published system applies Holodeck/PSDL-style languages to PCBs; behaviour under pad clearance and via-in-pad rules is untested.
- VP replaced the repair neighbourhood details (×2/×0.5/±δ in CD notes) with ×(±4^Y) sampling and an extra d_edit term.

## Sources
- research notes: [cross_domain_ideas.md § Q1, Q8, Q10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md); [verification_papers.md § 1 rows 39–40, § 2.10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [llm-guided-placement](llm-guided-placement.md) · [packing-and-graph-drawing-transplants](packing-and-graph-drawing-transplants.md) · [../../ideas/cross-domain-transplants](../../ideas/cross-domain-transplants.md)
