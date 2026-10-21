# LLM roles in placement systems (complement to the placement area)

**Scope:** this doc covers the *LLM-role* view and the systems the placement-area doc does not. PCBAgent, ModuPlace, Li et al. DAC'26, VeoPlace and MAGE are covered in full in [../placement/llm-guided-placement.md](../placement/llm-guided-placement.md), and non-LLM PCB placers in [../placement/pcb-placers-2022-2026.md](../placement/pcb-placers-2022-2026.md).

**TL;DR**
- **Every PCB result in which an LLM-involved system beats classical or commercial tools keeps geometry in a solver** [I]:
  - Li et al. DAC'26: LLM grouping plus MILP legalization; −55%/−73% WL/vias vs a commercial placer, −15%/−13% vs Quilter [S, via survey];
  - ModuPlace: LLM constraint graph plus hierarchical placer [P];
  - PCBAgent: RL with legality masks; the LLM only reweights [P].
- **Successful LLM roles:** hierarchy and grouping, constraint or relation graphs, hyperparameters (with explanations), region proposals as **weak anchors** (λ_A = 0.01), and command menus [P].
- **Corrections:**
  - Li et al. is a separate paper, not ModuPlace.
  - VeoPlace is Harvard/Kempner + Google DeepMind (not MSR); NeurIPS 2026; DREAMPlace gain 0.5–4.4%.
  - MAGE's +29.7% WL is vs commercial placers; it is comparable to the human expert.
  - PCBAgent's LLM is unnamed and never trains weights.

  [P]
- **Fine-tuning beats zero-shot for constraint generation:** ModuPlace's 7B model trained on 426 expert graphs beats zero-shot GPT-4o and Claude-3.5 by about 26% WL and 43% vias [P].

## Key facts

### LLM roles across systems

| Role | System | Key numbers | Source |
|---|---|---|---|
| Request/defect → RL reweighting; re-tune only violating parts | PCBAgent (ASP-DAC'25) | HPWL 1.04×, NSLW 0.94× vs manual; +39.6% requested wire categories in 2–3 rounds; baselines' spacing legality 0 | [PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C247-ASPDAC2025-PCBAgent.pdf) [P] |
| Hierarchical Modular Tree + Comprehensive Constraint Graph (x̂, ŷ, θ̂, w) → placer | ModuPlace (DAC'26) | WL 1266.5 vs 1477–1529 for baselines; vias 48.6; without SFT WL +35.1%; GPT-4o zero-shot 1756.8 WL | [PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf) [P] |
| Two grouping agents + topology-enriched retrieval → MILP legalization | Li et al. (DAC'26) | −55%/−73% vs commercial, −34%/−26% vs NS-Place, −15%/−13% vs Quilter (6 boards) | [2606.19795](https://arxiv.org/pdf/2606.19795) [S, via survey] |
| VLM region proposals → weak quadratic anchors / −∞ masks | VeoPlace (NeurIPS 2026) | λ_A 0.01 best; image vs text <0.8%; about $7 per run; 125 VLM calls per 2,000 rollouts | [2603.28733](https://arxiv.org/pdf/2603.28733) [P] |
| Families of repeated groups → place one, transform-and-merge; flyline visual gate; stateless auditor | MAGE (UCSD, Opus 4.6) | $220–509 per tournament; vision ablation WNS +40.5% worse | [2607.18536](https://arxiv.org/pdf/2607.18536) [P] |
| **Propose and explain** hyperparameters for DREAMPlace/Xplace | HyperPlace (TODAES 2025) | Up to 1.66% HPWL on ISPD2005; under fences, +22.24% vs DREAMPlace 3.0 and +19.28% vs Xplace 2.0 | [2606.19795](https://arxiv.org/abs/2606.19795) [S, via survey] |
| Analysis / grouping / floorplan / verification agents exchange **structured JSON** | CHIP-MAP (DATE 2026) | Up to 1.5% area; repairs 61.6% of TNS | [S, via survey] |
| Few-shot LLM **net-weight constraints** for Bayesian optimization | LLANA (analog) | — | [2406.05250](https://arxiv.org/abs/2406.05250) [S] |
| Multi-agent with instructions; abstract suggestions to the designer, concrete ones compiled to 11 commands | LayoutCopilot (TCAD) | 93.75% command correctness vs 79.98% single-agent | [2406.18873](https://arxiv.org/pdf/2406.18873) [P] |
| LLM cluster constraints for a cell-layout engine | Ho & Ren (LAD 2024) | Up to 19.4% smaller cells, 100% LVS/DRC-clean | [2406.06549](https://arxiv.org/abs/2406.06549) [P] |
| Human-skill-enhanced VLM macro placement | PDAgent-Bench | With human instructions, beat analytical and RL baselines | [2606.17253](https://arxiv.org/abs/2606.17253) [P] |
| LLM writes layout-generator code; LLM-only routing coordinates | You et al. 2024; Zhang et al. 2025 (MDPI, unread) | — | [2606.17074](https://arxiv.org/abs/2606.17074) [S] |

### Reusable mechanisms (detail in the placement doc)
- **VeoPlace prompt contract:**
  - HISTORY SUMMARY: archetypes, ≥3 principles marked "hypothesis";
  - STRATEGY: exactly one change, marked "exploratory";
  - REGIONS: largest first.
- **VeoPlace context selection ("Top Stratified"):** K-means over placements, rank-softmax τ = 0.43 over clusters, top C from the chosen cluster.
- **ModuPlace training:** SFT on 426 CCGs; GRPO with 36 samples in groups of 4; a GNN reward from pairwise expert rankings; a CCG equivalence test (common edges ≥ τ, cosine ≥ ψ). See [../data/training-recipes.md](../data/training-recipes.md).
- **MAGE:** feasibility checks with recursive split; Go-With-The-Winners tournament (6 variants × 6 rounds).

## Recommendations for our system

1. The LLM produces hierarchy, grouping, sides and a relation graph; our solver places and legalizes (MILP/CP-SAT). The LLM never emits final coordinates. See [interfaces-relations-vs-coordinates.md](interfaces-relations-vs-coordinates.md) [I].
2. **Weak anchors only** (about 1% weight for LLM regions), validated against a random-region control.
3. Reuse VeoPlace's prompt contract and context selection for per-block rule-area proposals.
4. Detect repeated channels, place one and replicate (KiCad multichannel / Repeat Layout), then legalize globally.
5. Have the LLM **explain** any parameter or weight it proposes (HyperPlace pattern), stored in the intent record (see [../ux/design-rationale-and-intent-record.md](../ux/design-rationale-and-intent-record.md)).
6. Plan a fine-tuned constraint-graph model (an open CCG dataset mined from PCBWorld D3 boards).

## Conflicts and open questions

- The Li et al. primary text has not been read.
- ModuPlace and PCBAgent release no code or prompts; the CCG text schema is unknown.
- ModuPlace beats baselines only on average; baselines win several individual boards.

## Sources
- research notes:
  - [llm_for_eda.md § 1, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
  - [verification_papers.md § 1 rows 12–17, 21–23, 44; § 2.2, § 2.3, § 2.6, § 2.8, § 2.11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [../placement/llm-guided-placement.md](../placement/llm-guided-placement.md), [agent-loop-patterns.md](agent-loop-patterns.md), [code-and-objective-evolution.md](code-and-objective-evolution.md), [vision-feedback.md](vision-feedback.md)
