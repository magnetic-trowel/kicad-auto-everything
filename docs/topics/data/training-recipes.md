# Synthetic data and fine-tuning recipes for layout LLMs

**TL;DR**
- **Representation first.** Relative-offset, pin-name code gives **82% valid circuits vs 32.5%** for raw KiCad files from the same model [P].
- **Then SFT on verified pairs, then group RL (GRPO/DAPO)** with shaped executable rewards and difficulty filtering; **DPO** where reward hacking appears [P].
- **Manufacture verified supervision:**
  - round-trip plus equivalence filters (CodeV-R1: 150K → 87K → 3.1K);
  - BO reverse-engineering of expert layouts (GenLeaf);
  - solver distillation plus feasibility RL (FOARL);
  - calibrated jitter and part swaps for hard negatives [P].
- **Scale:** hundreds (426 CCGs) to thousands (2,105 schematics) of expert examples suffice for a 7–20B LoRA *when the representation is right*; a few thousand hard RL prompts (3.1K) suffice [P].
- For PCBs, the highest-value generator is **round-trip constraint extraction** from human boards, accepted only when re-solving reproduces the human result [I].

## Key facts

### Representation results

| Work | Finding | Source |
|---|---|---|
| SchGen | Code-L1 (relative and semantic) 82.0% valid vs 32.5% raw KiCad (same model); without CoT 53.4%; vanilla 11.0%; GPT-5.2 67.9% (code) vs 10.5% (raw) | [2605.30345](https://arxiv.org/abs/2605.30345) [P] |
| LaMAGIC | Output formulation matters; the adjacency-matrix form reaches up to 96% success at 0.01 tolerance | [2407.18269](https://arxiv.org/abs/2407.18269) [P] |
| R³L | Multi-hop relative relations accumulate frame errors; fix with invariant decomposition, imagine-and-revise, global-to-local re-parameterization | [2605.06758](https://arxiv.org/abs/2605.06758) [P] |
| ACDC | Fine-tuned LLMs placing analog devices directly show "sensitivity to data format, instability… limited generalization" | [2512.09199](https://arxiv.org/abs/2512.09199) [P] |

### Synthetic-data pipelines

| Pipeline | Recipe | Numbers | Source |
|---|---|---|---|
| **CodeV-R1** (NeurIPS'25) | Code → NL (DeepSeek-V3) → NL → thought + code (R1); keep cases where baseline Qwen-Coder fails; require equivalence plus Yosys; drop Rouge-L > 0.5 to eval sets; RL set = drop prompts solved 5/5; adaptive DAPO | 150K → **87K** SFT → **3.1K** RL; rule testbench gives 96.1% fewer false negatives and catches 62.5% more injected errors than LLM testbenches; 7B: 68.6% VerilogEval v2, 72.9% RTLLM | [2505.24183](https://arxiv.org/abs/2505.24183) [P] |
| **GenLeaf** (ICML'26) | "BO-Generated Golden Scripts": BO searches script parameters until the layout matches the expert's metrics and embedding, then SFT + GRPO on Qwen3-14B (groups of 5 from 20) | 14 industrial cases vs experts: 0.52× tracks, 0.96× WL, 1.01× vias | [PDF](https://yhhan.com/PDFs/GenLeaf_paper.pdf) [P] |
| **FOARL** (NeurIPS'25) | SFT on solver outputs as text-attributed instances (KD-tree top-2 neighbours); feasibility reward R_f = ω0·ζ + Σωᵢcᵢ (TSP ω 0.2/0.5/0.3); optimality R_o = α/(1+M_o); GRPO; **Best-of-N** at inference | "SFT alone leads to over-greedy behavior"; GPT-4o and Claude-3.5 about 50% feasible on CO problems with <30 nodes | [2509.16865](https://arxiv.org/abs/2509.16865) [P] |
| **OptiScene** | 3D-SynthPlace, about 17K scenes ("GPT synthesize, human inspect"); SFT then multi-turn DPO with injected-violation negatives | — | [2506.07570](https://arxiv.org/abs/2506.07570) [P] |
| **GeoSVG-RL** | Synthetic SFT warm start → GRPO vs a rendered verifier with 6 reward terms | — | [2605.25447](https://arxiv.org/abs/2605.25447) [P] |
| **kicad-tools perturbation corpus** | Per board: Gaussian xy jitter σ 1.0–4.0 mm plus ±90° rotation with p 0.05–0.30; connectors, holes and test points fixed; σ hand-calibrated to a **20–60% pass rate** (flat σ 6 mm → 0%); label = routes in 45 s with 0 DRC; 20 placement features; GroupKFold by board; negative controls (edge violation, overlap pile, σ 20 mm) | Out-of-fold AUC **0.919** on 131 samples (32 positive); precision at p > 0.8 only 0.67 (n = 6) | [doc](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/learned_fom_phase0.md) [P, third-party] |
| **circuit-skills swaps** | Swap 25% or 100% of same-footprint interchangeable parts in human placements: legal but worse wiring, so hard negatives | clean 0.56 → 0.39 / 0.31 | [score_study.py](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/score_study.py) [P, third-party] |
| Simulator-Refined Diffusion (RF PCB) | Differentiable surrogate plus full-wave simulator during sampling | up to 21.2% closer to targets | [2609.38363](https://arxiv.org/abs/2609.38363) [P] |

### Layout fine-tuning and reward design

| Work | Recipe | Source |
|---|---|---|
| **ModuPlace** | Qwen-2.5-7B; SFT on 426 expert CCGs; GRPO with 36 CCGs per input in groups of 4; **GNN ranker trained on pairwise expert rankings** ("manual scoring… may lead to instability"); CCG equivalence test. Without SFT WL +35.1%; without GRPO +25.4% | [PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf) [P] |
| **VeriReason** | R = 2.0 if the testbench passes; 0.1 + AST score if it only parses; 0 otherwise. Keep prompts with group mean in [0.3, 1.8] and variance ≥ 0.1. 83.1% VerilogEval-Machine; 2.8× first-attempt correctness | [2505.11849](https://arxiv.org/abs/2505.11849) [P] |
| **VeriPrefer** | DPO; "the code that passes more testcases is… preferred"; chosen because "reward-based RL is prone to reward hacking" | [2504.15804](https://arxiv.org/abs/2504.15804) [P] |
| **3D-Layout-R1** | GRPO with scene-graph reasoning and dense IoU, centre and collision rewards: +15% IoU, −25% centre error vs CoT-SFT and vanilla GRPO | [2603.22279](https://arxiv.org/abs/2603.22279) [P] |
| **SR-ReaL** | Cold-start SFT → RL with accuracy, format and center-detection rewards; "blended cold-start data is crucial" | [2606.17539](https://arxiv.org/abs/2606.17539) [P] |
| **AesthetiQ** | DPO with MLLM-judge pairs plus filtering; +17% / +16% (Crello / WebUI) | [2503.00591](https://arxiv.org/abs/2503.00591) [P] |

## Recommendations for our system

### Synthetic generators, in order of value [I]
1. **Round-trip constraint extraction** (GenLeaf/CodeV-R1 analogue):
   - from a human board, extract a constraint graph (relative offsets, rotations, sides, groups, edges);
   - re-solve with our placer, then route;
   - keep the pair if completion, DRC and HPWL ratio match or beat the human; otherwise BO over weights and tolerances;
   - decontaminate by footprint-set and WL-hash similarity.
2. **Hard negatives:** part swaps plus σ-calibrated jitter (20–60% pass), labelled by an actual routing outcome, giving DPO and ranker pairs.
3. **Difficulty filtering** (CodeV-R1, VeriReason).
4. **Solver distillation plus a feasibility RL stage** (FOARL), with Best-of-N against a DRC/router verifier at inference.
5. **Procedural constraint boards** (PCBWorld D1/D2-style) for reward unit tests.

### Reward template (VeriReason/FOARL style)
- R = 0 if the output fails to parse or apply.
- R = 0.1 + 0.4·legality if it parses (fraction of hard indicators met: overlap, outline, keepouts, error DRC).
- R = 1.0 + completion + optimality if legal (routed fraction under a bounded Freerouting/KRT budget; α/(1+HPWL ratio)).
- Optional + β·ranker (a pairwise GNN on human-vs-perturbed and expert pairs).
- Filter prompts by group mean and variance; switch to **DPO** if hacking appears.

### Training order
DevFormer-style pose/assignment model → **SFT** (7–20B LoRA, distilled CoT, anchor-relative DSL) → **GRPO/DAPO** (groups of 4–5 out of 16–36 samples) → expert A/B rankings for a ranker or DPO.

**Open data:** mine relative-offset graphs from the 679 KiCad-9 PCBWorld D3 boards (each keeps its source licence; tier rules apply) as an open CCG equivalent. See [data-pipeline-plan.md](data-pipeline-plan.md).

## Conflicts and open questions

- No PCB paper implements round-trip constraint extraction, and the equivalence tolerance is uncalibrated (e.g. "routes clean, HPWL ≤ 1.1× designer").
- No GRPO study exists on LLM *routing* output for PCBs.
- ModuPlace's weights, data and ranking-set size are unpublished.
- How much expert preference data a PCB ranker needs is unknown.

## Sources
- research notes:
  - [learning_from_layout_data.md § Q4, § Q5, § Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md)
  - [verification_papers.md § 2.2, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [imitation-and-learned-scores.md](imitation-and-learned-scores.md), [data-pipeline-plan.md](data-pipeline-plan.md), [../llm/read-representations.md](../llm/read-representations.md), [../llm/llm-guided-placement-systems.md](../llm/llm-guided-placement-systems.md)
