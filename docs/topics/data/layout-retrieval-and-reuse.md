# Layout retrieval, pattern mining and reuse

Scope: retrieving and reusing human layout fragments (structural retrieval, motif mining, analog-IC reuse and migration) and how much coarse human-derived hints transfer. Not here: relation DSL -> [../llm/interfaces-relations-vs-coordinates.md](../llm/interfaces-relations-vs-coordinates.md); fragment licensing -> [licensing-tiers-and-contamination](licensing-tiers-and-contamination.md); priors -> [measured-priors](measured-priors.md).
Keys: layout retrieval, NEMESIS, WL hash, motif, CROP, R3SET, gSpan, Wu TCAD'15, max-weight clique, PCB-Migrator, offset constraint graph, hint study, verified growth

No PCB layout-retrieval system is published; the parts exist (sections below) [P]. Coarse hints barely help ([hint study](#how-much-do-coarse-human-derived-constraints-transfer)), so retrieval must transfer **fine-grained relative geometry** [P, third-party]. Workflow-side KiCad primitives (Repeat Layout, multichannel) -> [../workflow/layout-reuse.md](../workflow/layout-reuse.md).

## Structural retrieval

- **NEMESIS (2026):** "a motif vector… and a two-iteration Weisfeiler-Lehman refinement hash". `s = λ·s_WL (Jaccard) + (1−λ)·s_motif (cosine)`, **λ = 0.6**. Accepted results are re-indexed: "the database grows through verified updates" ([2607.05657](https://arxiv.org/abs/2607.05657)) [P].
- **GNN region prediction:** negative sampling + subgraph embeddings from the whole-circuit embedding ([2507.19518](https://arxiv.org/abs/2507.19518)) [P].
- **Circuit-diagram retrieval:** GAM-YOLO recognition + hierarchical graph similarity, for legacy consultation and plagiarism detection ([2503.11658](https://arxiv.org/abs/2503.11658)) [P].
- **CROP:** RTL embedding retrieval → RAG-guided parameter search constrained by similar designs; −9.9% power. Pattern for "retrieve similar boards → reuse router and placer settings" ([2507.02128](https://arxiv.org/abs/2507.02128)) [P].
- **R3SET:** 71% Hit@1 / 92% Hit@5 (n = 271); an LLM final selector 60.1% vs 58.5% top-1 on the full set ([DOI](https://doi.org/10.1115/1.4071107)) [S]. Dataset -> [corpora-and-yield](corpora-and-yield.md#other-datasets).
- **GANA:** GCN + graph algorithms detect symmetry and matching; ALIGN's training set has 1,390 OTAs [S] ([GANA data](https://github.com/kkunal1408/GANA_circuit_data)) [P].
- Classic tools: SubGemini subgraph isomorphism [S]; NetworkX WL hashing ([docs](https://networkx.org/documentation/latest/reference/algorithms/graph_hashing.html)) [S].
- Patents: WIP PCB connectivity matched against a company "design vault" ([US 11593437](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11593437)); analog template matching with pruning ([US 11354477](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11354477)) [S].
- Frequent motifs: CellE, equality saturation + pattern mining (−15.41% area, −8.00% delay) ([2603.12797](https://arxiv.org/abs/2603.12797)) [P]; gSpan = canonical frequent-subgraph miner [S].

## Analog-IC reuse and migration

- **Wu et al. (IEEE TCAD 34(2), 2015)**, "the first knowledge-based physical synthesis methodology" ([PDF](https://users.ece.cmu.edu/~xinli/papers/2015_TCAD_pd.pdf)) [P]: legacy database as connection graphs → match common sub-circuits → reuse "quality-approved legacy layouts"; overlapping patterns selected by **maximum-weight clique**. Two-stage Miller op-amp: diff-amp only 73.33% devices / 39.29% nets; OTA only 86.67% / 50.00%; both 100% of devices. Earlier migration methods assumed identical topology.
- **Xu et al. ISPD'18:** sweep-line extraction of symmetry and alignment constraints from existing placements, preserved while cutting area 7.6% ([PDF](https://par.nsf.gov/servlets/purl/10121012)) [P].
- Others [S]: Lin ICCAD'20 learning + migration, because "different companies and designers follow different guidelines"; IPRAIL 0.25 → 0.18 µm; Synopsys 14 → 5 nm (vendor).
- **PCB-Migrator** (Han … Bei Yu, Ho, Chen; DATE 2026): when "board dimensions" change or "new obstacles" are added, an "offset constraint graph" carries the relationships; routing-path graphs + matching guide re-routing; same use case as re-solving relations after resizes ([DOI](https://doi.org/10.23919/DATE69613.2026.11539307)) [S].
- **GenLeaf layout embedding:** GraphSAGE over a placement graph + routing image; MSE 34.0% / 35.9% lower than Circuit GNN / DeepLayout; used as a similarity metric ([PDF](https://yhhan.com/PDFs/GenLeaf_paper.pdf)) [P].

## How much do coarse human-derived constraints transfer?

circuit-skills hint study [P, third-party, unreviewed], 52 boards: parts placed from scratch by an annealer, routed by TraceMaker (20 s), judged by KiCad DRC ([hints_study.md](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/hints_study.md)).

| Placement | Clean route | Pre-route error DRC |
|---|---|---|
| Designer's own | **0.63** | 0.0 |
| No hints | 0.15 | 30.0 |
| L1: edge/region anchors | 0.19 | — |
| L2: + big-part relations | 0.21 | — |
| L3: + small parts near their big part | 0.19 | 30.2 |

Big parts moved from 26% to ≈11–12% of the board diagonal away from the designer's positions; clean routing barely improved.

## Retrieval design [I]

1. Key: anchor IC (MPN family + pin-function multiset) + its 2-hop labelled neighbourhood.
2. Coarse filter by WL hash + motif histogram; rerank with a GNN or graph kernel.
3. Return top-k human fragments with full relative geometry: per-pad offsets of passives in the IC frame, rotation, side, via and trace topology, summary stats.
4. The solver adapts and legalizes.
5. Fragment selection: Wu-2015 max-weight clique picks non-overlapping fragments maximizing reused parts.
6. Verified growth only: index a fragment after it passes DRC and routes in its new context (NEMESIS).
7. Copy exact relative poses where packages match. Likely carriers of routability: orientation, pin-escape-aware spacing, channel reservation, not anchors.
8. Validate extraction by round-trip re-solving ([training-recipes](training-recipes.md#synthetic-generators-in-order-of-value-i)).
9. Licence-aware UI: show each fragment's licence and attribution, offer a permissive-only filter; the LLM cites fragments and licences. Copying CERN-OHL-S or CC-BY-SA geometry plausibly makes the board a derivative ([licensing-tiers-and-contamination](licensing-tiers-and-contamination.md#licence-texts-and-precedents)).
10. Settings reuse: retrieve similar boards to seed placer and router parameters (CROP).

## Open questions

- PCB-Migrator's full method and results unavailable (DATE PDF 404).
- Cross-board layout variance per motif unmeasured.
- R3SET numbers come from snippets.
- The hint study is small and unreviewed.

## Sources

- research notes: [learning_from_layout_data.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md); [verification_papers.md § 2.12 (PCB-Migrator)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
- related: [imitation-and-learned-scores](imitation-and-learned-scores.md)
