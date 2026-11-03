# Offline LLM evolution of placer and router code and objectives

Scope: LLM-driven evolution of classical engine code and objectives (placement, global routing, FPGA routing, flow tuning) and our offline track. Not here: full EvoPlace / OrderPlace / CoEvoP&R / FunSearch / AlphaEvolve mechanisms -> [solvers/llm-evolved-heuristics](../solvers/llm-evolved-heuristics.md); online agent loops -> [agent-loop-patterns](agent-loop-patterns.md).
Keys: code evolution, objective evolution, EvoPlace, OrderPlace, CoEvoP&R, restricted interface, autograd gate, MAP-Elites, negative memory, GR-Evolve, VPR-Evolve, FABO, GoalEvolve, AlphaRoute, Prim–Dijkstra, AlphaEvolve, OPRO, EoH, ReEvo, TILOS, generalization, lineage

## Systems

| System | What the LLM evolves | Mechanism | Results | Source |
|---|---|---|---|---|
| **EvoPlace** (IEEE TCAD 2026, GPT-4o) | Placer optimizer code | -> [solvers](../solvers/llm-evolved-heuristics.md#systems) | Generalized gains 0.509% (MMS), 2.85% (ISPD2005) vs DREAMPlace. **Conflict:** the EDA note's "HPWL −5–8%" is case-specific | [2504.17801](https://arxiv.org/pdf/2504.17801); [DOI](https://doi.org/10.1109/TCAD.2026.3652945) [P] |
| **OrderPlace** (ICML 2026, Claude Sonnet 4.5) | Macro ordering policies | -> [solvers](../solvers/llm-evolved-heuristics.md#systems) | Macro HPWL −34.04% / −14.08% (ISPD2005) | [2606.08904](https://arxiv.org/pdf/2606.08904) [P] |
| **CoEvoP&R** (default gpt-5.4) | Differentiable placement objectives | Restricted interface + autograd gate; details -> [solvers](../solvers/llm-evolved-heuristics.md#systems) | 8 ChiPBench designs × 3 seeds: −16.9% rWL, −36.7% congestion; free-form interface underperforms | [2607.17398](https://arxiv.org/pdf/2607.17398); [repo](https://github.com/FCHXWH823/CoEvoP-R) [P] |
| **GR-Evolve** (ASU) | OpenROAD global-router source | QoR feedback; persistent knowledge of open-source routers | Up to −8.72% post-detailed-route WL (7 designs, 3 nodes) | [2604.22234](https://arxiv.org/abs/2604.22234) [P] |
| **VPR-Evolve** (ASP-DAC 2027) | FPGA VPR source, per design | Shared memory of earlier outcomes | vs stock: composite +2.7%, delay −9.8%, WL −18.1%, runtime −79.3%; vs hyperparameter tuning: delay −6.0%, WL −2.2%, runtime −7.8% | [2607.24998](https://arxiv.org/abs/2607.24998) [P] |
| **FABO** (HKUST/Synopsys) | Steiner-tree algorithm (SALT) | Agent-guided search found a structural limit; joint breakpoint optimization | 1.29M ICCAD15 nets: −0.83% overall, −2.66% for nets with 30+ pins | [2608.30268](https://arxiv.org/abs/2608.30268) [P] |
| **GoalEvolve** | OpenROAD algorithms | Teacher LLM converts unmet QoR targets into normalized gaps attributed to a stage; parallel Students implement via full-flow runs; mechanism memory | 8 ASAP7 designs: TNS +30.67%, leakage −21.18%, dynamic power −9.42%; beats Codex goal mode by 26.46% TNS | [2608.16733](https://arxiv.org/abs/2608.16733) [P] |
| **AlphaRoute** | Rip-up/reroute penalty parameters | LLM as "semantic policy optimizer" bounded by a knowledge graph | Claims −98.6% overflow (MEMPOOL), 29.8× lower overflow (ARIANE); single group, treat with caution | [2607.19768](https://arxiv.org/abs/2607.19768) [P] |
| **Prim–Dijkstra revisited** (Fudan) | Theory + solver | LLM-assisted proof of weak NP-completeness | HP-RCRST Pareto-dominates published methods on 23 of 28 instances | [2607.17005](https://arxiv.org/abs/2607.17005) [P] |
| **AlphaEvolve** | TPU Verilog, kernels | Evolutionary coding agent | TPU arithmetic change caught by downstream synthesis; 23% kernel speedup (≈1% Gemini training time); Verilog diffs "foster trust" | [2506.13131](https://arxiv.org/abs/2506.13131) [P] |

Evidence quality: coverage spans placement, global routing, FPGA routing, flow tuning; gains from a few percent to tens of percent; mostly self-reported single-group preprints, no independent replication, no PCB-specific study. Generalized gains are small (EvoPlace ≈3–10× below case-specific); gains over tuned baselines are much smaller than over stock tools (VPR-Evolve). A restricted, gradient-checked interface beats free-form prompting (CoEvoP&R) [P].

Method background: OPRO ([2309.03409](https://arxiv.org/abs/2309.03409)), EoH ([2401.02051](https://arxiv.org/abs/2401.02051)), ReEvo ([2402.01145](https://arxiv.org/abs/2402.01145)) [P]. Strong baselines matter: TILOS SA (320 parallel go-with-the-winners workers, 12.5 h) beat RL macro placement -> [pcb-llm-benchmarks](pcb-llm-benchmarks.md#hygiene-rules) [P].

## Offline track for our system

[I] Evolve the KiCad-side realizer (placer loss, legalizer heuristics, router costs) over a board corpus with full-flow scoring:
1. Placer loss over a restricted observable API via CoEvoP&R's pipeline; targets and evaluation cascade -> [solvers offline loop](../solvers/llm-evolved-heuristics.md#offline-evolution-loop-for-kae).
2. Freerouting cost functions or a custom router's heuristics with full-flow scoring and GR-Evolve/GoalEvolve-style stage attribution (placement vs routing vs DRC).
3. Hold out boards from day one; compare against tuned hyperparameters, not stock settings.
4. Log lineage (config, program, prompt, response, metrics) so every evolved artifact is reproducible and reviewable as a diff.
5. Evolved code is GPL-3.0-or-later; evolving GPL-3.0 Freerouting in-process is compatible; check [licensing/reuse-matrix](../licensing/reuse-matrix.md) before importing other engines.

## Sources
- [verification_papers.md § 1 rows 18–20, 43; § 2.7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
- [llm_for_eda.md § 1 IC, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
