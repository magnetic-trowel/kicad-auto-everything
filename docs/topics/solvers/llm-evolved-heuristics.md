# LLM-evolved heuristics and objectives (FunSearch, AlphaEvolve, EvoPlace, OrderPlace, CoEvoP&R)

**TL;DR**
- LLM-guided code evolution now works on physical design: OrderPlace (−34% HPWL vs WireMask-EA), CoEvoP&R (−16.9% routed WL, −36.7% congestion), EvoPlace (evolved initialization), AlphaEvolve (0.7% of Google fleet compute; TPU circuit simplification).
- **Restricted, gradient-checked interfaces beat free-form prompts** (CoEvoP&R): AST grammar → finite-value/autograd gate → cost-tiered evaluation → negative memory of failures.
- Budget realistically: EvoPlace's case-specific gains needed ~1,000 candidates per component and 1,000 trials per case on ~210 GPUs; **generalized gains were only 0.5–2.9%** — test cross-board generalization from day one.
- Evolve **constructor functions for symmetric structures** and **search algorithms for irregular problems** (AlphaEvolve).
- Better than letting the LLM place parts: evolve move operators, cost terms, orders and schedules against a sandboxed evaluator; never let it write whole CP models from scratch (Text2Zinc ≤25%).

## Key facts

| System | Mechanism | Result |
|---|---|---|
| **FunSearch** (Nature 2023, [P]) | Evolves a bin-packing priority function from best-fit; island program database | Beats first-fit and best-fit on all OR-Library sets; 0.03% off the lower bound on 100k-item Weibull; heuristic avoids leaving small unfillable gaps; OR1–4 excess bins 5.30/4.19/3.11/2.47% vs best-fit 5.81/6.06/5.37/4.94% [S] |
| **AlphaEvolve** (2025, [arXiv 2506.13131](https://arxiv.org/abs/2506.13131) [P]) | Parent + inspirations from MAP-Elites/island database → LLM diff → evaluate; **evaluation cascades**; **LLM-generated feedback** for hard-to-code properties; multiple criteria mixed in prompts; choose to evolve raw solution, constructor, or bespoke search | Vector bin packing heuristic recovers 0.7% of fleet resources; Verilog rewrite removing bits in a TPU circuit; new packing results; kissing number in 11-D 592 → 593. OpenEvolve reproduced n=26 circle packing 2.634 |
| EoH (ICML'24) / ReEvo (NeurIPS'24) / OPRO (ICLR'24) / ELM (2022) / LLM4AD | Evolve "thoughts" + code; LLM reflections as verbal gradients; meta-prompt of solution–score pairs; LLM as MAP-Elites mutation; unified platform | EoH beats FunSearch at low budget; ReEvo SOTA on 6 COPs [S/P] |
| **EvoPlace** (TCAD 2026, GPT-4o; [arXiv 2504.17801](https://arxiv.org/pdf/2504.17801) [P]) | Four-step generation (CoT analysis → idea → reference code → placer code); diversity-aware selection (normalized HPWL + code-embedding cosine distance); UCB evolution with self-reflection; extra inputs (sizes, pin offsets, net weights) | Initialization evolves best; **generalized gains 0.509% (MMS), 2.85% (ISPD2005)** vs DREAMPlace; ≥1,000 candidates per component, 1,000 trials per case on 60×2080Ti + 150×3090 |
| **OrderPlace** (ICML'26, Claude Sonnet 4.5; [arXiv 2606.08904](https://arxiv.org/pdf/2606.08904) [P]) | LLM writes macro ordering policies over exposed features; **three-stage proxy filter**: syntax → functional test on a subset → 50 parallel Monte-Carlo greedy probes (1,800 s); top-4 elites in prompt; temperature 0.7; final top-4 run with wire-mask greedy + EA | **−34.04% / −14.08% HPWL vs WireMask-EA / EGPlace** (ISPD2005 macro HPWL) |
| **CoEvoP&R** (gpt-5.4 default; [arXiv 2607.17398](https://arxiv.org/pdf/2607.17398) [P]) | LLM writes objectives through a **restricted interface** over differentiable observables (smooth WL, density; maps: density, RUDY, pin density, long-net pressure); AST grammar check + **finite-value + autograd gate**; tiers A (placement, all) → B (timing proxy, some) → C (real OpenROAD routing, 3 per 20 generations); MAP-Elites + islands + **negative memory of failure reasons**; logs sufficient to reconstruct lineage | 8 ChiPBench designs × 3 seeds: −16.9% rWL, −36.7% congestion, +0.70 ns WNS, TNS +912 ns; Superblue −5.4% / −23.2%; robust across gpt-5.4, gpt-4.1-mini, claude-opus-4-8, qwen3.7-max; **free-form prompt interface underperforms** |
| VeoPlace | In-context evolution of VLM region proposals with Top-Stratified history | See [LLM-guided placement](../placement/llm-guided-placement.md) |
| MAGE tournament | Go-With-The-Winners over agent variants | $220–509 per tournament |

**LLMs writing constraint models**: Text2Zinc ≤25.39% solution accuracy (GPT-4, MiniZinc); CP-Bench ~70% with docs + repeated sampling + self-verification, Python (CPMpy, CP-SAT) easier; per-global-constraint agent ensembles beat CoT [S].

**LLM-guided BO** (LLAMBO): [bayesian tuning](bayesian-tuning.md).

## Recommendations for our system
- Offline evolution loop [I]: targets = PathFinder `net_priority()`/`edge_cost()`, net/placement order heuristic (OrderPlace), PSDL repair neighbourhood, legalizer GLS weight schedule, placer loss over observables (HPWL, net crossing, RUDY, decap distance, loop area).
- **Evaluation cascade** [I]: (1) runs + courtyard legality on 3 toy boards → (2) HPWL + congestion proxy on 20 boards → (3) full Freerouting/PathFinder routing + KiCad DRC on held-out boards; negative memory of failure reasons; lineage logging.
- Restricted observable API with AST/autograd gates (CoEvoP&R), not free-form code [I].
- Constructor functions for symmetric blocks (LED matrices, memory buses, analog diff pairs); search algorithms for irregular boards [I].
- Add VLM "pros/cons" judgments as an LLM-scored criterion for hard-to-code aesthetics in the multi-criteria database, guarded by hard metrics [I].
- Provide a fixed, tested CP-SAT template; the LLM only adds typed constraints [I].

## Conflicts and open questions
- No LLM-evolved heuristic for PCB placement or routing has been published.
- EvoPlace's small generalized gains warn that case-specific evolution may not transfer across boards.

## Sources
- research notes: [cross_domain_ideas.md § Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md); [solver_toolbox.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [verification_papers.md § 1 rows 18–20; § 2.7; § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md); [placement_algorithms.md § Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md)

See also: [metaheuristics-and-qd](metaheuristics-and-qd.md) · [bayesian-tuning](bayesian-tuning.md) · [placement/ml-rl-placement](../placement/ml-rl-placement.md)
