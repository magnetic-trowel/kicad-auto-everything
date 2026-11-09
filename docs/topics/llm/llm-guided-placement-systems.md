# LLM roles in placement systems

Scope: what the LLM does inside placement systems (role view), plus systems the placement doc omits. Not here: full PCBAgent, ModuPlace, Li DAC'26, VeoPlace, MAGE mechanisms and numbers -> [placement/llm-guided-placement](../placement/llm-guided-placement.md); non-LLM placers -> [placement/pcb-placers-2022-2026](../placement/pcb-placers-2022-2026.md).
Keys: LLM role, grouping, hierarchy, constraint graph, CCG, HMT, weak anchor, λ_A, region proposal, hyperparameter explanation, HyperPlace, CHIP-MAP, LLANA, LayoutCopilot, Ho & Ren, PDAgent-Bench, SFT vs zero-shot

## Geometry stays in a solver

Every PCB result where an LLM-involved system beats classical or commercial tools with legal or DRC-clean output keeps geometry in a solver [I]:
- Li et al. DAC'26: LLM grouping + MILP legalization [S, via survey].
- ModuPlace: LLM constraint graph + hierarchical placer [P].
- PCBAgent: RL with legality masks; the LLM only reweights [P].

Use: the LLM produces hierarchy, grouping, sides and a relation graph; our solver (MILP/CP-SAT) places and legalizes; the LLM never emits final coordinates -> [interfaces-relations-vs-coordinates](interfaces-relations-vs-coordinates.md) [I].

## LLM roles across systems

| Role | System | Key numbers | Source |
|---|---|---|---|
| Request/defect -> RL reweighting; re-tune only violating parts | PCBAgent (ASP-DAC'25) | LLM unnamed, never trains weights; numbers -> [placement/llm-guided-placement](../placement/llm-guided-placement.md#methods-and-results) | [PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf) [P] |
| Hierarchical Modular Tree + Comprehensive Constraint Graph (x̂, ŷ, θ̂, w) -> placer | ModuPlace (DAC'26) | Fine-tuned 7B beats zero-shot GPT-4o and Claude-3.5 by ≈26% WL, 43% vias: fine-tuning beats zero-shot for constraint generation; numbers -> [placement/llm-guided-placement](../placement/llm-guided-placement.md#methods-and-results) | [PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf) [P] |
| Two grouping agents + topology-enriched retrieval -> MILP legalization | Li et al. (DAC'26; separate paper, not ModuPlace) | Beats commercial placer, NS-Place, Quilter (6 boards) -> [placement/llm-guided-placement](../placement/llm-guided-placement.md#methods-and-results) | [2606.19795](https://arxiv.org/pdf/2606.19795) [S, via survey] |
| VLM region proposals -> weak quadratic anchors / −∞ masks | VeoPlace (Harvard/Kempner + Google DeepMind, not MSR; NeurIPS 2026) | λ_A, gains, image ablation -> [placement/llm-guided-placement](../placement/llm-guided-placement.md#methods-and-results) | [2603.28733](https://arxiv.org/pdf/2603.28733) [P] |
| Families of repeated groups -> place one, transform-and-merge; flyline visual gate; stateless auditor | MAGE (UCSD, Opus 4.6) | Numbers -> [placement/llm-guided-placement](../placement/llm-guided-placement.md#methods-and-results); vision ablation -> [vision-feedback](vision-feedback.md#evidence) | [2607.18536](https://arxiv.org/pdf/2607.18536) [P] |
| **Propose and explain** hyperparameters for DREAMPlace/Xplace | HyperPlace (TODAES 2025) | Up to 1.66% HPWL on ISPD2005; under fences +22.24% vs DREAMPlace 3.0, +19.28% vs Xplace 2.0 | [2606.19795](https://arxiv.org/abs/2606.19795) [S, via survey] |
| Analysis / grouping / floorplan / verification agents exchange **structured JSON** | CHIP-MAP (DATE 2026) | Up to 1.5% area; repairs 61.6% of TNS | [S, via survey] |
| Few-shot LLM **net-weight constraints** for Bayesian optimization | LLANA (analog) | — | [2406.05250](https://arxiv.org/abs/2406.05250) [S] |
| Multi-agent with instructions -> 11 commands | LayoutCopilot (TCAD) | 93.75% vs 79.98% single-agent -> [agent-loop-patterns](agent-loop-patterns.md#multi-agent-consensus-memory-infrastructure) | [2406.18873](https://arxiv.org/pdf/2406.18873) [P] |
| LLM cluster constraints for a cell-layout engine | Ho & Ren (LAD 2024) | Up to 19.4% smaller cells, 100% LVS/DRC-clean -> [agent-loop-patterns](agent-loop-patterns.md#bounded-action-space-deterministic-realization-independent-check) | [2406.06549](https://arxiv.org/abs/2406.06549) [P] |
| Human-skill-enhanced VLM macro placement | PDAgent-Bench | With human instructions, beat analytical and RL baselines | [2606.17253](https://arxiv.org/abs/2606.17253) [P] |
| LLM writes layout-generator code; LLM-only routing coordinates | You et al. 2024; Zhang et al. 2025 (MDPI, unread) | — | [2606.17074](https://arxiv.org/abs/2606.17074) [S] |

Successful LLM roles: hierarchy and grouping, constraint/relation graphs, hyperparameters with explanations, region proposals as weak anchors (λ_A = 0.01), command menus [P].

## Reuse in our system

Mechanism details (VeoPlace prompt contract and Top-Stratified context selection, ModuPlace SFT/GRPO training, MAGE tournament) -> [placement/llm-guided-placement](../placement/llm-guided-placement.md); training recipe -> [data/training-recipes](../data/training-recipes.md).

1. Weak anchors only, relative to the wirelength and density terms, validated against a random-region control. VeoPlace's λ_A = 0.01 (0.1–1.0 over-constrained) is an absolute coefficient in its benchmark's units, not a 1% share: calibrate ours by a sweep [I].
2. VeoPlace prompt-contract port and MAGE-style channel replication (KiCad multichannel / Repeat Layout, then global legalization) -> [placement/llm-guided-placement](../placement/llm-guided-placement.md#use-in-kae) [I].
3. The LLM explains every parameter or weight it proposes (HyperPlace pattern), stored in the intent record -> [ux/design-rationale-and-intent-record](../ux/design-rationale-and-intent-record.md) [I].
4. Plan a fine-tuned constraint-graph model: open CCG dataset mined from PCBWorld D3 tier-A boards only, evaluation boards excluded -> [data/training-recipes](../data/training-recipes.md) [I].

## Open questions

- Li et al. primary text unread.
- ModuPlace and PCBAgent release no code or prompts; CCG text schema unknown.

## Sources
- [llm_for_eda.md § 1, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
- [verification_papers.md § 1 rows 12–17, 21–23, 44; § 2.2, § 2.3, § 2.6, § 2.8, § 2.11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
