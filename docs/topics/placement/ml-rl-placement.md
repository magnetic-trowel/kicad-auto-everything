# ML/RL placement: the controversy and what ML is good for

**TL;DR**
- In VLSI, independent reproductions contradict claims that end-to-end RL macro placers beat tuned SA/analytical placers; credible recent ML is **guidance and refinement** (region hints, RL refiners, LLM-evolved code).
- Pure-RL PCB placers (RL_PCB, Lim 2026, DRLPlace, Crocker) use small/private sets and weak baselines; the strong PCB results are **hybrids** (PCBAgent, ModuPlace, Li DAC'26) — see [LLM-guided placement](llm-guided-placement.md).
- On PCBs, learned components help where they **order, partition, mask, group or prioritize**; exact geometry stays classical.
- Do not start with RL training; use ML for priorities, grouping, orders, region proposals, cost schedules and heuristic evolution ([LLM-evolved heuristics](../solvers/llm-evolved-heuristics.md)).

## Key facts

**Google RL macro placement and critiques (VLSI)**
- Circuit Training/AlphaChip: hMETIS-clustered macros; proxy = 1.0·WL + 1.0·density (top-10%×0.5) + 0.5·congestion (top-5%); claimed TPU-v5 tape-outs; checkpoint pre-trained on 20 TPU blocks ([repo](https://github.com/google-research/circuit_training) [S]; [TILOS ProxyCost](https://github.com/TILOS-AI-Institute/MacroPlacement/tree/main/Docs/ProxyCost) [S]).
- Cheng/Kahng et al. (ISPD'23; v3 "An Updated Assessment of RL for Macro Placement", TCAD, Mar 2026): SA beat CT 17/17 on proxy and 16/17 on HPWL (ICCAD04, v2); v3 adds CT-Ariane-X4 (532 macros) where SA wins; CT depends on initial placement; proxy "correlates weakly" with post-route PPA; "using weak or outdated baselines may lead to misleading conclusions" ([arXiv 2302.11014](https://arxiv.org/abs/2302.11014) [P], VP-verified).
- Markov CACM'24: Nature paper's integrity "substantially undermined" [S]; Goldie/Mirhoseini/Dean rebuttal ("That Chip Has Sailed") not peer reviewed [S].

**VLSI successors** [S]
| Method | Idea |
|---|---|
| MaskPlace (NeurIPS'22) | PPO with position, wire and view masks |
| ChiPFormer (ICML'23) | Offline decision transformer |
| WireMask-BBO (NeurIPS'23) | Greedy wire-mask decoder + RS/BO/EA |
| MaskRegulate (NeurIPS'24) | RL refining DREAMPlace output |
| EfficientPlace (ICML'24) | Global tree search + local RL policy |
| Chip diffusion (ICML'25) | See [generative placement](generative-placement.md) |
| PlaceReasoner-Beta, MacroAgent | Abstracts only |

adaptec1 HPWL (×10⁵): EfficientPlace 5.94, ChiPFormer 6.62, MaskPlace 7.62 ([arXiv 2609.34452](https://arxiv.org/html/2609.34452) [S]). LLM/VLM-driven VLSI work (VeoPlace, MAGE) is in [LLM-guided placement](llm-guided-placement.md); LLM code evolution (EvoPlace, OrderPlace, CoEvoP&R) in [LLM-evolved heuristics](../solvers/llm-evolved-heuristics.md).

**PCB-specific ML placers**
- **RL_PCB** (Vassallo & Bajada, DATE'24; MIT; parses KiCad): each component an agent (TD3/SAC); reward from HPWL, Euclidean WL and overlap; trained on 6 circuits; A* routing evaluation. **On unseen circuits, on average 17% (TD3) and 21% (SAC) lower post-routing WL than SA** (VP-corrected; [UM OAR](https://www.um.edu.mt/library/oar/handle/123456789/131782) [S]; [repo](https://github.com/LukeVassallo/RL_PCB)).
- **Lim 2026** (A*STAR, [arXiv 2602.23540](https://arxiv.org/abs/2602.23540) [P]): main IC fixed; passives choose among 20–48 border slots; state = one-hot passive ID + net ID; reward α·non-overlap + (1−α)·net proximity relaxed by Top-K slots near the right power pin; DQN/A2C/SA; TEWL metric. 9 in-house sub-circuits (8–24 passives). A2C best, but overlaps/conflicts remain (SA 14/22, DQN 12/13, A2C 4/16, DQNnet 6/16); no rotation, routing or two-sided.
- **DRLPlace** (ASP-DAC'26): PPO + per-step reward prediction, pre-trained ResNet policy-value over layout/net/density maps, chip-centric clustering init, boundary-aware push-and-reflection legalization; up to 16% lower HPWL than manual ([DOI](https://doi.org/10.1109/ASP-DAC66049.2026.11420655) [S]).
- **Crocker** (MIT MEng 2021): RL with no overlaps/crossings, routing metrics, curriculum reward [S].
- Kaphle (MIT 2022): MCTS self-generates PCB synthesis datasets for offline RL [S].
- Commercial [V]: DeepPCB RL placement (TPU 15–235× throughput), Quilter (RL + physics checks), Cadence Allegro X AI; Cadence patent US 12223248 uses a neural net as learned routability fitness [S].

**Explainability ranking.** End-to-end neural placers (CT, ChiPFormer, diffusion, DRLPlace) are the least explainable; weighted costs, declarative constraints, hierarchy/relative-position graphs, region anchors, orders/seeds, raster masks and feature-rich conflict lists are steerable ([LLM-guided](llm-guided-placement.md)).

## Recommendations for our system
- No RL training in v1. Learned pieces only where they feed a classical engine: ordering, grouping, region proposals, cost weights [I].
- Hold every ML claim to tuned-SA and analytical baselines on open boards (TILOS lesson) [I].
- Mask-based legality (PCBAgent position/boundary/spacing masks per rotation) is reusable as a feasibility raster even without RL [I].
- Keep a research track: fine-tuned relation generators (ModuPlace-style) and diffusion priors trained on synthetic data ([generative](generative-placement.md)) [I].

## Conflicts and open questions
- AlphaChip dispute unresolved (Google vs reproductions).
- RL_PCB, DRLPlace, EfficientPlace full texts not read.

## Sources
- research notes: [placement_algorithms.md § Q3, Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [verification_papers.md § 1 rows 42–43, § 2.11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md); [cross_domain_ideas.md § Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)

See also: [llm-guided-placement](llm-guided-placement.md) · [generative-placement](generative-placement.md) · [solvers/llm-evolved-heuristics](../solvers/llm-evolved-heuristics.md)
