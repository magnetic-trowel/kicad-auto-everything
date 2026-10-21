# Offline LLM evolution of placer and router code and objectives

**TL;DR**
- LLM-driven evolution of classical engines now covers **placement, global routing, FPGA routing and flow tuning**, with gains from a few percent to tens of percent. Most results are self-reported preprints [P].
- **A restricted, gradient-checked interface beats free-form prompting** for evolving objectives (CoEvoP&R) [P].
- **Budget realistically, and test generalization.** EvoPlace's case-specific gains needed about 1,000 candidates per case on about 210 GPUs; its generalized gains were only **0.5–2.9%** [P].
- Gains over strong tuning baselines are much smaller than over stock tools: VPR-Evolve's WL gain is −18.1% vs stock VPR but −2.2% vs hyperparameter tuning [P].
- For us this is an offline track: evolve the KiCad-side realizer (placer loss, legalizer heuristics, router costs) over a board corpus with full-flow scoring [I].

## Key facts

| System | What the LLM evolves | Mechanism details | Results | Source |
|---|---|---|---|---|
| **EvoPlace** (IEEE TCAD 2026, GPT-4o) | Placer optimizer code | CoT analysis → idea → reference code → placer code; diversity-aware selection (HPWL plus code-embedding distance); UCB evolution with self-reflection; extra inputs such as node sizes and net weights | Compute: ≥1,000 candidates per component and 1,000 trials per case on 60×2080Ti + 150×3090. **Generalized** gains 0.509% (MMS) and 2.85% (ISPD2005) vs DREAMPlace. **Conflict:** the EDA note's "HPWL −5–8%" refers to case-specific gains | [2504.17801](https://arxiv.org/pdf/2504.17801); [DOI](https://doi.org/10.1109/TCAD.2026.3652945) [P] |
| **OrderPlace** (ICML 2026, Claude Sonnet 4.5) | Macro ordering policies | Features: macro size, area sharing nets, topology. 3-stage proxy filter: syntax → functional test on a subset → parallel Monte Carlo greedy probes (50 samples, 1,800 s). Top-4 elites in each prompt; final top-4 run with a wire-mask greedy placer plus EA; temperature 0.7 | Macro HPWL −34.04% / −14.08% on ISPD2005 | [2606.08904](https://arxiv.org/pdf/2606.08904) [P] |
| **CoEvoP&R** (default gpt-5.4) | Differentiable placement objectives | **Restricted interface** over scalars (smooth WL, density) and maps (density, **RUDY**, pin density, long-net pressure); AST grammar check plus a **finite-value and autograd gate**; Tier A placement on all, Tier B timing proxy on some, Tier C OpenROAD routing on 3 per 20 generations; MAP-Elites islands with **negative memory of failures**; full lineage logs | 8 ChiPBench designs × 3 seeds: −16.9% rWL, −36.7% congestion, +0.70 ns WNS, TNS +912 ns; Superblue −5.4% / −23.2%. **Free-form prompt interface underperforms.** Robust across gpt-5.4, gpt-4.1-mini, claude-opus-4-8, qwen3.7-max | [2607.17398](https://arxiv.org/pdf/2607.17398); [repo](https://github.com/FCHXWH823/CoEvoP-R) [P] |
| **GR-Evolve** (ASU) | OpenROAD global-router source | QoR feedback; persistent knowledge of open-source routers | Up to −8.72% post-detailed-route WL (7 designs, 3 nodes) | [2604.22234](https://arxiv.org/abs/2604.22234) [P] |
| **VPR-Evolve** (ASP-DAC 2027) | FPGA VPR source, per design | Shared memory of earlier outcomes | vs stock: composite +2.7%, delay −9.8%, WL −18.1%, runtime −79.3%. vs hyperparameter tuning: delay −6.0%, WL −2.2%, runtime −7.8% | [2607.24998](https://arxiv.org/abs/2607.24998) [P] |
| **FABO** (HKUST/Synopsys) | Steiner-tree algorithm (SALT) | Agent-guided search found a structural limit; joint breakpoint optimization | 1.29M ICCAD15 nets: −0.83% overall, −2.66% for nets with 30+ pins | [2608.30268](https://arxiv.org/abs/2608.30268) [P] |
| **GoalEvolve** | OpenROAD algorithms | A Teacher LLM converts unmet QoR targets into normalized gaps and attributes them to a stage; parallel Students implement via full-flow runs; mechanism memory | 8 ASAP7 designs: TNS +30.67%, leakage −21.18%, dynamic power −9.42%; beats Codex goal mode by 26.46% TNS | [2608.16733](https://arxiv.org/abs/2608.16733) [P] |
| **AlphaRoute** | Rip-up/reroute penalty parameters | LLM as "semantic policy optimizer" bounded by a knowledge graph | Claims −98.6% overflow (MEMPOOL), 29.8× lower overflow (ARIANE); single group, treat with caution | [2607.19768](https://arxiv.org/abs/2607.19768) [P] |
| **Prim–Dijkstra revisited** (Fudan) | Theory plus solver | LLM-assisted proof of weak NP-completeness | HP-RCRST Pareto-dominates published methods on 23 of 28 instances | [2607.17005](https://arxiv.org/abs/2607.17005) [P] |
| **AlphaEvolve** | TPU Verilog, kernels | Evolutionary coding agent | TPU arithmetic change caught by downstream synthesis; 23% kernel speedup (about 1% Gemini training time); diffs in Verilog "foster trust" | [2506.13131](https://arxiv.org/abs/2506.13131) [P] |

**Method background:** OPRO ([2309.03409](https://arxiv.org/abs/2309.03409)), EoH ([2401.02051](https://arxiv.org/abs/2401.02051)), ReEvo ([2402.01145](https://arxiv.org/abs/2402.01145)) [P].

**Ten-year context:** TILOS found strong SA baselines (320 parallel go-with-the-winners workers, 12.5 h) beat RL macro placement; "weak or outdated baselines may lead to misleading conclusions" ([2302.11014](https://arxiv.org/abs/2302.11014)) [P].

## Recommendations for our system

1. **Offline track:** evolve a KiCad placer loss over a restricted observable API (HPWL, net crossings, RUDY, decap distance, loop area, crossing count). Use CoEvoP&R's pipeline: AST grammar → finite/autograd gate → cost tiers (proxy → bounded Freerouting route → full DRC) → MAP-Elites with negative memory [I].
2. Evolve Freerouting cost functions or a custom router's heuristics with full-flow scoring, using GR-Evolve/GoalEvolve-style stage attribution (placement vs routing vs DRC).
3. **Hold out boards** to measure cross-board generalization from day one; compare against tuned hyperparameters, not stock settings.
4. **Log lineage** (config, program, prompt, response, metrics) so every evolved artifact can be reproduced and reviewed as a diff.
5. Keep evolved code under our GPL-3.0-or-later code licence. Evolving GPL-3.0 Freerouting in-process is compatible; check the [../licensing/reuse-matrix.md](../licensing/reuse-matrix.md) before importing other engines [I].

## Conflicts and open questions

- Most results are single-group preprints with no independent replication.
- No PCB-specific evolution study exists yet.
- EvoPlace's case-specific vs generalized gains differ by about 3–10×.

## Sources
- research notes:
  - [verification_papers.md § 1 rows 18–20, 43; § 2.7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
  - [llm_for_eda.md § 1 IC, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)

See also: [agent-loop-patterns.md](agent-loop-patterns.md), [llm-guided-placement-systems.md](llm-guided-placement-systems.md), [pcb-llm-benchmarks.md](pcb-llm-benchmarks.md)
