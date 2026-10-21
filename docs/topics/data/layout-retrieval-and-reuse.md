# Layout retrieval, pattern mining and reuse

**TL;DR**
- No PCB layout-retrieval system is published, but the parts exist:
  - WL-hash plus motif retrieval (NEMESIS);
  - GNN subcircuit matching;
  - requirement → block retrieval (R3SET 71% Hit@1);
  - embedding retrieval of similar designs to seed tool settings (CROP);
  - max-weight-clique pattern selection with 73–100% device reuse (Wu TCAD'15) [P].
- **Warning from measurement:** coarse hints derived from the designer's placement barely help.
  - Clean-route rate: designer 0.63, no hints 0.15, coarse hints **0.19–0.21**.
  - Retrieval must transfer **fine-grained relative geometry** [P, third-party].
- **PCB-Migrator** (DATE'26) migrates expert layouts via offset constraint graphs, the same use case as re-solving relations after resizes [S].
- The database should **grow only through verified updates**, and the UI must surface fragment licences [I].

## Key facts

### Structural retrieval
- **NEMESIS (2026):** "a motif vector… and a two-iteration Weisfeiler-Lehman refinement hash".
  - Similarity s = λ·s_WL (Jaccard) + (1−λ)·s_motif (cosine), with **λ = 0.6**.
  - Accepted results are re-indexed, so "the database grows through verified updates" ([2607.05657](https://arxiv.org/abs/2607.05657)) [P].
- **GNN region prediction:** negative sampling plus subgraph embeddings from the whole-circuit embedding ([2507.19518](https://arxiv.org/abs/2507.19518)) [P].
- **Circuit-diagram retrieval:** GAM-YOLO recognition plus hierarchical graph similarity, for legacy consultation and plagiarism detection ([2503.11658](https://arxiv.org/abs/2503.11658)) [P].
- **CROP:** RTL embedding retrieval, then RAG-guided parameter search constrained by similar designs; −9.9% power. This is the pattern for "retrieve similar boards → reuse router and placer settings" ([2507.02128](https://arxiv.org/abs/2507.02128)) [P].
- **R3SET:** 71% Hit@1 / 92% Hit@5 (n = 271); an LLM final selector scored 60.1% vs 58.5% top-1 on the full set ([DOI](https://doi.org/10.1115/1.4071107)) [S].
- **GANA:** GCN plus graph algorithms detect symmetry and matching. ALIGN's training set has 1,390 OTAs [S] ([GANA data](https://github.com/kkunal1408/GANA_circuit_data)) [P].
- **Classic tools:** SubGemini subgraph isomorphism [S]; NetworkX WL hashing ([docs](https://networkx.org/documentation/latest/reference/algorithms/graph_hashing.html)) [S].
- **Patents:** a WIP PCB's connectivity matched against a company "design vault" ([US 11593437](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11593437)); analog template matching with pruning ([US 11354477](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11354477)) [S].
- **Frequent motifs:** CellE uses equality saturation plus pattern mining (−15.41% area, −8.00% delay) ([2603.12797](https://arxiv.org/abs/2603.12797)) [P]; gSpan is the canonical frequent-subgraph miner [S].

### Analog-IC reuse and migration
- **Wu et al. (IEEE TCAD 34(2), 2015)**, "the first knowledge-based physical synthesis methodology" ([PDF](https://users.ece.cmu.edu/~xinli/papers/2015_TCAD_pd.pdf)) [P]:
  - steps: build a legacy database as connection graphs → match common sub-circuits → reuse "quality-approved legacy layouts";
  - overlapping patterns are selected by **maximum-weight clique**;
  - two-stage Miller op-amp example: diff-amp only 73.33% devices / 39.29% nets; OTA only 86.67% / 50.00%; both 100% of devices;
  - earlier migration methods assumed identical topology.
- **Xu et al. ISPD'18:** sweep-line extraction of symmetry and alignment constraints from existing placements, preserved while cutting area 7.6% ([PDF](https://par.nsf.gov/servlets/purl/10121012)) [P].
- **Others** [S]:
  - Lin ICCAD'20: learning plus migration, because "different companies and designers follow different guidelines";
  - IPRAIL: 0.25 → 0.18 µm;
  - Synopsys 14 → 5 nm (vendor).
- **PCB-Migrator** (Han … Bei Yu, Ho, Chen; DATE 2026): when "board dimensions" change or "new obstacles" are added, an "offset constraint graph" carries the relationships; routing-path graphs plus matching guide re-routing ([DOI](https://doi.org/10.23919/DATE69613.2026.11539307)) [S].
- **GenLeaf layout embedding:** GraphSAGE over a placement graph plus a routing image; MSE 34.0% / 35.9% lower than Circuit GNN / DeepLayout; used as a similarity metric ([PDF](https://yhhan.com/PDFs/GenLeaf_paper.pdf)) [P].

### How much do coarse human-derived constraints transfer? [P, third-party, unreviewed]

circuit-skills hint study, 52 boards: parts placed from scratch by an annealer, routed by TraceMaker (20 s), judged by KiCad DRC ([hints_study.md](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/hints_study.md)).

| Placement | Clean route | Pre-route error DRC |
|---|---|---|
| Designer's own | **0.63** | 0.0 |
| No hints | 0.15 | 30.0 |
| L1: edge/region anchors | 0.19 | — |
| L2: + big-part relations | 0.21 | — |
| L3: + small parts near their big part | 0.19 | 30.2 |

Big parts moved from 26% to about 11–12% of the board diagonal away from the designer's positions, but clean routing barely improved.

## Recommendations for our system

### Retrieval design [I]
1. Key on the anchor IC (MPN family plus pin-function multiset) plus its 2-hop labelled neighbourhood.
2. Coarse filter by WL hash plus motif histogram; rerank with a GNN or graph kernel.
3. Return **top-k human fragments with full relative geometry**: per-pad offsets of passives in the IC frame, rotation, side, via and trace topology, plus summary stats.
4. The solver adapts and legalizes.

### Selection, growth and validation
- **Fragment selection:** Wu-2015 max-weight clique picks non-overlapping fragments that maximize reused parts.
- **Verified growth only:** index a fragment after it passes DRC and routes in its new context (NEMESIS).
- **Copy exact relative poses** where packages match. The likely carriers of routability are orientation, pin-escape-aware spacing and channel reservation, not anchors.
- **Validate extraction by round-trip re-solving** (see [training-recipes.md](training-recipes.md)).

### Licensing and settings
- **Licence-aware UI:** show each fragment's licence and attribution and offer a permissive-only filter. The LLM cites fragments and licences. Copying CERN-OHL-S or CC-BY-SA geometry plausibly makes the board a derivative (see [licensing-tiers-and-contamination.md](licensing-tiers-and-contamination.md)).
- **Settings reuse:** retrieve similar boards to seed placer and router parameters (CROP).

## Conflicts and open questions

- PCB-Migrator's full method and results are unavailable (DATE PDF 404).
- Cross-board layout variance per motif is unmeasured.
- R3SET numbers come from snippets.
- The hint study is small and unreviewed.

## Sources
- research notes: [learning_from_layout_data.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md)
- related: [verification_papers.md § 2.12 (PCB-Migrator)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [measured-priors.md](measured-priors.md), [imitation-and-learned-scores.md](imitation-and-learned-scores.md), [../llm/interfaces-relations-vs-coordinates.md](../llm/interfaces-relations-vs-coordinates.md)
