# Synthetic data and fine-tuning recipes for layout LLMs

Scope: output representations, synthetic-supervision pipelines, SFT/RL/DPO recipes and reward design for layout LLMs. Not here: imitation precedents and learned scores -> [imitation-and-learned-scores](imitation-and-learned-scores.md); the full pipeline plan -> [data-pipeline-plan](data-pipeline-plan.md); LLM read formats -> [../llm/read-representations.md](../llm/read-representations.md); LLM placement systems -> [../llm/llm-guided-placement-systems.md](../llm/llm-guided-placement-systems.md).
Keys: SchGen, CodeV-R1, GenLeaf, FOARL, ModuPlace, VeriReason, VeriPrefer, kicad-tools perturbation corpus, GRPO, DAPO, DPO, Best-of-N, round-trip constraint extraction, reward template, CCG

Scale [I]: hundreds (426 CCGs) to thousands (2,105 schematics) of expert examples suffice for a 7–20B LoRA *when the representation is right*, at least in distribution; out of distribution SchGen's fine-tuned model scored 65.6% valid vs GPT-5.2's 77.0% ([read-representations](../llm/read-representations.md#schgen-relative-code-vs-raw-kicad)). 3.1K hard RL prompts sufficed for CodeV-R1 [P]. Order: representation, SFT on verified pairs, group RL, DPO where reward hacking appears ([training order](#training-order)).

## Representation results

| Work | Finding | Source |
|---|---|---|
| SchGen | Code-L1 (relative and semantic) 82.0% valid vs 32.5% raw KiCad, same model; table -> [read-representations](../llm/read-representations.md#schgen-relative-code-vs-raw-kicad) | [2605.30345](https://arxiv.org/abs/2605.30345) [P] |
| LaMAGIC | Output formulation matters; adjacency-matrix form up to 96% success at 0.01 tolerance | [2407.18269](https://arxiv.org/abs/2407.18269) [P] |
| R³L | Multi-hop relative relations accumulate frame errors; fix: invariant decomposition, imagine-and-revise, global-to-local re-parameterization | [2605.06758](https://arxiv.org/abs/2605.06758) [P] |
| ACDC | Fine-tuned LLMs placing analog devices directly show "sensitivity to data format, instability… limited generalization" | [2512.09199](https://arxiv.org/abs/2512.09199) [P] |

## Synthetic-data pipelines

| Pipeline | Recipe | Numbers | Source |
|---|---|---|---|
| **CodeV-R1** (NeurIPS'25) | Code → NL (DeepSeek-V3) → NL → thought + code (R1); keep cases where baseline Qwen-Coder fails; require equivalence + Yosys; drop Rouge-L > 0.5 to eval sets; RL set = drop prompts solved 5/5; adaptive DAPO | 150K → **87K** SFT → **3.1K** RL; rule testbench 96.1% fewer false negatives, catches 62.5% more injected errors than LLM testbenches; 7B: 68.6% VerilogEval v2, 72.9% RTLLM | [2505.24183](https://arxiv.org/abs/2505.24183) [P] |
| **GenLeaf** (ICML'26) | "BO-Generated Golden Scripts": BO searches script parameters until the layout matches the expert's metrics and embedding, then SFT + GRPO on Qwen3-14B (groups of 5 from 20) | 14 industrial cases vs experts: 0.52× tracks, 0.96× WL, 1.01× vias | [PDF](https://yhhan.com/PDFs/GenLeaf_paper.pdf) [P] |
| **FOARL** (NeurIPS'25) | SFT on solver outputs as text-attributed instances (KD-tree top-2 neighbours); feasibility reward R_f = ω0·ζ + Σωᵢcᵢ (TSP ω 0.2/0.5/0.3); optimality R_o = α/(1+M_o); GRPO; **Best-of-N** at inference | "SFT alone leads to over-greedy behavior"; GPT-4o and Claude-3.5 ≈50% feasible on CO problems with <30 nodes | [2509.16865](https://arxiv.org/abs/2509.16865) [P] |
| **OptiScene** | 3D-SynthPlace, ≈17K scenes ("GPT synthesize, human inspect"); SFT then multi-turn DPO with injected-violation negatives | — | [2506.07570](https://arxiv.org/abs/2506.07570) [P] |
| **GeoSVG-RL** | Synthetic SFT warm start → GRPO vs a rendered verifier, 6 reward terms | — | [2605.25447](https://arxiv.org/abs/2605.25447) [P] |
| **kicad-tools perturbation corpus** | Per board: Gaussian xy jitter σ 1.0–4.0 mm + ±90° rotation with p 0.05–0.30; connectors, holes, test points fixed; σ hand-calibrated to a **20–60% pass rate** (flat σ 6 mm → 0%); label = routes in 45 s with 0 DRC; 20 placement features; GroupKFold by board; negative controls (edge violation, overlap pile, σ 20 mm) | Out-of-fold AUC **0.919** on 131 samples (32 positive); precision at p > 0.8 only 0.67 (n = 6) | [doc](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/learned_fom_phase0.md) [P, third-party] |
| **circuit-skills swaps** | Swap 25% or 100% of same-footprint interchangeable parts in human placements: legal but worse wiring → hard negatives | clean 0.56 → 0.39 / 0.31 ([table](imitation-and-learned-scores.md#which-placement-measures-predict-a-clean-route)) | [score_study.py](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/score_study.py) [P, third-party] |
| Simulator-Refined Diffusion (RF PCB) | Differentiable surrogate + full-wave simulator during sampling | up to 21.2% closer to targets | [2609.38363](https://arxiv.org/abs/2609.38363) [P] |

## Layout fine-tuning and reward design

| Work | Recipe | Source |
|---|---|---|
| **ModuPlace** | Qwen-2.5-7B; SFT on 426 expert CCGs → GRPO with a GNN reward trained on pairwise expert rankings ("manual scoring… may lead to instability"). Without SFT WL +35.1%; without GRPO +25.4%. Mechanism -> [placement/llm-guided-placement](../placement/llm-guided-placement.md#methods-and-results) | [PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf) [P] |
| **VeriReason** | R = 2.0 if testbench passes; 0.1 + AST score if it only parses; 0 otherwise. Keep prompts with group mean in [0.3, 1.8] and variance ≥ 0.1. 83.1% VerilogEval-Machine; 2.8× first-attempt correctness | [2505.11849](https://arxiv.org/abs/2505.11849) [P] |
| **VeriPrefer** | DPO; "the code that passes more testcases is… preferred"; chosen because "reward-based RL is prone to reward hacking" | [2504.15804](https://arxiv.org/abs/2504.15804) [P] |
| **3D-Layout-R1** | GRPO with scene-graph reasoning and dense IoU, centre and collision rewards: +15% IoU, −25% centre error vs CoT-SFT and vanilla GRPO | [2603.22279](https://arxiv.org/abs/2603.22279) [P] |
| **SR-ReaL** | Cold-start SFT → RL with accuracy, format and center-detection rewards; "blended cold-start data is crucial" | [2606.17539](https://arxiv.org/abs/2606.17539) [P] |
| **AesthetiQ** | DPO with MLLM-judge pairs + filtering; +17% / +16% (Crello / WebUI) | [2503.00591](https://arxiv.org/abs/2503.00591) [P] |

## Synthetic generators, in order of value [I]

1. **Round-trip constraint extraction** (GenLeaf/CodeV-R1 analogue): extract a constraint graph (relative offsets, rotations, sides, groups, edges) from a human board → re-solve with our placer → route → keep the pair if completion, DRC and HPWL ratio match or beat the human, else BO over weights and tolerances; decontaminate by footprint-set and WL-hash similarity.
2. **Hard negatives:** part swaps + σ-calibrated jitter (20–60% pass), labelled by an actual routing outcome → DPO and ranker pairs.
3. **Difficulty filtering** (CodeV-R1, VeriReason).
4. **Solver distillation + feasibility RL stage** (FOARL), Best-of-N against a DRC/router verifier at inference.
5. **Procedural constraint boards** (PCBWorld D1/D2-style) for reward unit tests.

## Reward template (VeriReason/FOARL style)

```
R = 0                                   output fails to parse or apply
R = 0.1 + 0.4·legality                  parses; legality = fraction of hard indicators met
                                        (overlap, outline, keepouts, error DRC)
R = 1.0 + completion + optimality       legal; completion = routed fraction under a bounded
                                        Freerouting/KRT budget; optimality = α/(1+HPWL ratio)
  (+ β·ranker, optional: pairwise GNN on human-vs-perturbed and expert pairs)
```

Filter prompts by group mean and variance; switch to DPO if hacking appears.

## Training order

DevFormer-style pose/assignment model → **SFT** (7–20B LoRA, distilled CoT, anchor-relative DSL) → **GRPO/DAPO** (groups of 4–5 out of 16–36 samples) → expert A/B rankings for a ranker or DPO. Per-step detail: [data-pipeline-plan#5](data-pipeline-plan.md#5-train-in-order).

- Before distilling CoT: check the base-model licence and the teacher model's terms for training on its outputs and releasing the weights; record the teacher in the data card ([LICENSING.md](../../../LICENSING.md), [base-model table](../licensing/data-rulepacks-weights.md#model-weights)).
- Open data: mine relative-offset graphs (open CCG equivalent) only from PCBWorld D3's tier-A boards, ≈100 of the 677 in `d3.json` after a README/licence audit (356 no licence, 45 NOASSERTION; [open-board-sources](open-board-sources.md#existing-datasets-what-is-public-and-how-to-get-it)). Never mine the 119 evaluation boards in `d3.json` (99 D3-A + 10 D3-B + 10 D3-C): D3-A/B is our routing benchmark.

## Open questions

- No PCB paper implements round-trip constraint extraction; equivalence tolerance uncalibrated (e.g. "routes clean, HPWL ≤ 1.1× designer").
- No GRPO study on LLM *routing* output for PCBs.
- ModuPlace's weights, data and ranking-set size unpublished.
- How much expert preference data a PCB ranker needs is unknown.

## Sources

- research notes: [learning_from_layout_data.md § Q4, § Q5, § Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md); [verification_papers.md § 2.2, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
