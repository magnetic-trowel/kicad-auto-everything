# Bayesian optimization and LLM-guided tuning of placer/router knobs

**TL;DR**
- Multi-objective BO of placer knobs is **proven for PCBs**: Cypress tunes 8 parameters with MOTPE, scored by Freerouting-routed results; AutoDMP does MOBO for DREAMPlace (VLSI).
- **Optuna** (MIT) gives TPE/MOTPE, NSGA-II, CMA-ES, GP, AutoSampler (multi-objective + constrained); experimental Rustuna is several to several-hundred times faster for cheap objectives.
- **OptunaHub's LLAMBO sampler** makes LLM-guided BO a drop-in (~$0.05–0.10 per 30-trial run with GPT-4o-mini); its benefit is in the sparse early phase, on low-dimensional spaces, and small open backbones are unstable.
- Recipe: LLM writes the search space from intent → LLM/LLAMBO for the first ~10 trials → MOTPE/NSGA-II for the bulk with multi-fidelity pruning → LLM picks from the Pareto front.

## Key facts

| Tool | Facts |
|---|---|
| Cypress tuning | MOTPE in parallel across GPUs over 8 parameters (initial position, density weight, target density, net-crossing weight, LSE γ, learning rate, optimizer); objectives Freerouting routability + track length ([slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf) [P]); repo also ships BOHB via hpbandster ([analytical](analytical-differentiable.md)) |
| AutoDMP (NVlabs) | DREAMPlace + ABCDPlace with multi-objective hyperparameter BO; example 20 iterations × 2 workers ([README](https://raw.githubusercontent.com/NVlabs/AutoDMP/main/README.md) [P]) |
| Optuna 5.0.0 (MIT) | TPE/MOTPE, NSGA-II, CMA-ES, GP, AutoSampler "Full Support for Multi-Objective & Constrained Optimization"; Rustuna experimental TPE/MOTPE/NSGA-II/CMA-ES ([PyPI](https://pypi.org/pypi/optuna/json) [P]) |
| **LLAMBO** (Liu, Astorga, Seedat, van der Schaar; ICLR'24; [arXiv 2402.03921](https://arxiv.org/abs/2402.03921) [P]) | BO in natural language: zero-shot warm-start, LLM as discriminative/generative surrogate, candidate sampling; 74 Bayesmark/HPOBench tasks (GPT-3.5); authors: much larger compute footprint, low-dimensional HPT focus, use early or as one component |
| OptunaHub LLAMBO sampler ([hub](https://hub.optuna.org/samplers/llambo/) [P]) | `custom_task_description` beyond tabular ML; categorical params → random search; prompts forbid re-proposing observed points; GPT-4o-mini $0.05–0.10 per 30-trial run |
| LLAMBO reproducibility ([arXiv 2511.18891](https://arxiv.org/abs/2511.18891) [P]) | Llama 3.1 70B broadly confirms warm-start gains and sampler beating TPE/random; Gemma 27B, Llama 3.1 8B "unstable or invalid predictions" |
| BoTorch 0.18.1 (MIT), SMAC 2.4.1 (BSD-3, multi-objective + multi-fidelity facades) | [PyPI](https://pypi.org/pypi/smac/json) [P] |
| ChatEDA | LLM agent orchestrating RTL→GDSII tool flows ([arXiv 2308.10204](https://arxiv.org/abs/2308.10204) [P]) |
| PCBAgent | LLM reweights RL score terms from user language (+39.6% NSLW) ([LLM-guided](../placement/llm-guided-placement.md)) |

## Recommendations for our system
- Recipe [I]: (1) LLM writes the Optuna search space and constraints from design intent; (2) LLAMBO or the LLM's own zero-shot proposals for the first ~10 trials; (3) MOTPE/NSGA-II (Rustuna if objectives are cheap) for the bulk; (4) multi-fidelity pruning HPWL → RUDY → quick route → Freerouting ([multi-fidelity](performance-and-multifidelity.md)); (5) LLM chooses from the Pareto front and explains the trade-off.
- Keep the space small (~5–15 continuous knobs); use a strong backbone if the LLM acts as surrogate [I].
- Tune both placer weights and router negotiation schedules ([PathFinder](../routing/pathfinder-negotiated-congestion.md)) [I].

## Conflicts and open questions
- No published study applies LLAMBO or other LLM-BO to EDA/PCB parameters; original LLAMBO repo URL unverified (aggregator lists `tennisonliu/LLAMBO`, MIT).

## Sources
- research notes: [solver_toolbox.md § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)

See also: [analytical-differentiable](analytical-differentiable.md) · [metaheuristics-and-qd](metaheuristics-and-qd.md) · [performance-and-multifidelity](performance-and-multifidelity.md)
