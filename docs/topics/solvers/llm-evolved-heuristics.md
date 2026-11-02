# LLM-evolved heuristics and objectives (FunSearch, AlphaEvolve, EvoPlace, OrderPlace, CoEvoP&R)

Scope: LLM-guided program evolution for placement/routing heuristics and objectives. Not here: LLM-guided BO -> [Bayesian tuning](bayesian-tuning.md); LLM as placer -> [LLM-guided placement](../placement/llm-guided-placement.md).
Keys: FunSearch, AlphaEvolve, OpenEvolve, EoH, ReEvo, OPRO, ELM, LLM4AD, EvoPlace, OrderPlace, CoEvoP&R, evaluation cascade, negative memory, restricted interface, autograd gate, AST grammar, constructor function, MAGE, Go-With-The-Winners, Text2Zinc

## Systems

| System | Mechanism | Result |
|---|---|---|
| **FunSearch** (Nature 2023, [P]) | Evolves a bin-packing priority function from best-fit; island program database | Beats first-fit and best-fit on all OR-Library sets; 0.03% off the lower bound on 100k-item Weibull; avoids small unfillable gaps; OR1–4 excess bins 5.30/4.19/3.11/2.47% vs best-fit 5.81/6.06/5.37/4.94% [S] |
| **AlphaEvolve** (2025, [arXiv 2506.13131](https://arxiv.org/abs/2506.13131) [P]) | Parent + inspirations from MAP-Elites/island database → LLM diff → evaluate; evaluation cascades; LLM-generated feedback for hard-to-code properties; multiple criteria in prompts; evolve raw solution, constructor, or bespoke search | Vector bin-packing heuristic recovers 0.7% of fleet resources; Verilog rewrite removing bits in a TPU circuit; new packing results; kissing number in 11-D 592 → 593. OpenEvolve reproduced n=26 circle packing 2.634 |
| EoH (ICML'24) / ReEvo (NeurIPS'24) / OPRO (ICLR'24) / ELM (2022) / LLM4AD | Evolve "thoughts" + code; LLM reflections as verbal gradients; meta-prompt of solution–score pairs; LLM as MAP-Elites mutation; unified platform | EoH beats FunSearch at low budget; ReEvo SOTA on 6 COPs [S/P] |
| **EvoPlace** (TCAD 2026, GPT-4o; [arXiv 2504.17801](https://arxiv.org/pdf/2504.17801) [P]) | Four-step generation (CoT analysis → idea → reference code → placer code); diversity-aware selection (normalized HPWL + code-embedding cosine distance); UCB evolution with self-reflection; extra inputs (sizes, pin offsets, net weights) | Initialization evolves best; generalized gains 0.509% (MMS), 2.85% (ISPD2005) vs DREAMPlace; ≥1,000 candidates per component, 1,000 trials per case on 60×2080Ti + 150×3090 |
| **OrderPlace** (ICML'26, Claude Sonnet 4.5; [arXiv 2606.08904](https://arxiv.org/pdf/2606.08904) [P]) | LLM writes macro ordering policies over exposed features; three-stage proxy filter: syntax → functional test on a subset → 50 parallel Monte-Carlo greedy probes (1,800 s); top-4 elites in prompt; temperature 0.7; final top-4 run with wire-mask greedy + EA | −34.04% / −14.08% HPWL vs WireMask-EA / EGPlace (ISPD2005 macro HPWL) |
| **CoEvoP&R** (gpt-5.4 default; [arXiv 2607.17398](https://arxiv.org/pdf/2607.17398) [P]) | LLM writes objectives through a restricted interface over differentiable observables (smooth WL, density; maps: density, RUDY, pin density, long-net pressure); AST grammar check + finite-value + autograd gate; tiers A (placement, all) → B (timing proxy, some) → C (real OpenROAD routing, 3 per 20 generations); MAP-Elites + islands + negative memory of failure reasons; logs reconstruct lineage | 8 ChiPBench designs × 3 seeds: −16.9% rWL, −36.7% congestion, +0.70 ns WNS, TNS +912 ns; Superblue −5.4% / −23.2%; robust across gpt-5.4, gpt-4.1-mini, claude-opus-4-8, qwen3.7-max; free-form prompt interface underperforms |
| VeoPlace | In-context evolution of VLM region proposals with Top-Stratified history | → [LLM-guided placement](../placement/llm-guided-placement.md) |
| MAGE tournament | Go-With-The-Winners over agent variants | $220–509 per tournament |

LLMs writing constraint models (Text2Zinc ≤25.39%, CP-Bench ~70%) → [CP-SAT](cp-sat-milp-smt.md#llms-writing-constraint-models): give a tested CP-SAT template; the LLM only adds typed constraints [I].

## Offline evolution loop for kae

[I]
- Targets: PathFinder `net_priority()`/`edge_cost()`; net/placement order heuristic (OrderPlace); PSDL repair neighbourhood; legalizer GLS weight schedule; placer loss over observables (HPWL, net crossing, RUDY, decap distance, loop area).
- Evaluation cascade: (1) runs + courtyard legality on 3 toy boards → (2) HPWL + congestion proxy on 20 boards → (3) full Freerouting/PathFinder routing + KiCad DRC on held-out boards; negative memory of failure reasons; lineage logging.
- Interface: restricted observable API with AST/autograd gates (CoEvoP&R), not free-form code.
- Test cross-board generalization from day one: EvoPlace's case-specific gains needed ~1,000 candidates per component and 1,000 trials per case on ~210 GPUs, generalized gains only 0.5–2.9%.
- Constructor functions for symmetric blocks (LED matrices, memory buses, analog diff pairs); search algorithms for irregular boards.
- VLM "pros/cons" judgments as one LLM-scored criterion for hard-to-code aesthetics, guarded by hard metrics.

## Open questions

- No LLM-evolved heuristic for PCB placement or routing is published.

## Sources

- [cross_domain_ideas.md § Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md); [solver_toolbox.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [verification_papers.md § 1 rows 18–20; § 2.7; § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md); [placement_algorithms.md § Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md)
