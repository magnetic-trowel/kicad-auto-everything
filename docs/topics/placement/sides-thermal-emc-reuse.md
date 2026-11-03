# Double-sided, thermal, EMC/power-loop and reuse-aware placement

Scope: double-sided, thermal-, EMC/power-loop- and reuse-aware placement. Not here: kae's own physics terms -> [physics terms](../../research/placement/kae-physics-terms.md).
Keys: side assignment, double-sided, thermal-aware placement, TRouter, thermal surrogate, EMC, loop inductance, power-loop anchors, power module layout, Pareto GA, parasitic extraction, reuse, D2BS, subgraph matching, PCB-Migrator, offset constraint graph

## Methods and results

**Double-sided** [P unless noted]. No academic placer optimizes component sides (all take them as input); side assignment is a natural LLM decision [I].
| Source | Handling |
|---|---|
| Cypress | Separate top/bottom electrostatic density and per-side legalization; side fixed by input orientation ("F" prefix) ([repo](https://github.com/NVlabs/Cypress)) |
| NTU DAC'25 | Two-sided **pad-type-aware** density (THT pads matter on both sides); double-sided MILP constraint-graph legalizer ([DOI](https://doi.org/10.1109/dac63849.2025.11133056) [S]) |
| PA-ICM | Top: IC + accessories; bottom: pin-oriented placement **within the IC outline** (decaps under the IC), DBSCAN on IC pins, "close-to-pin" priority ([arXiv](https://arxiv.org/pdf/2502.14012)) |
| HiePlace | Future work: "two interconnected planes … interlayer connection costs … minimizing vias" |
| Lim 2026 | Forced a double-sided board to single-sided |
| OmniLayout | LMMs left alone place ~80% of parts on top → [metrics](benchmarks-and-metrics.md#methods-and-results) |
| KiCad autoplacer | Keeps sides; checks the opposite side only for THT |
| Patent US 5481474 | Two-sided raw-then-refined placement [S] |

**Thermal**
- Older PCB metaheuristics: GA + thermal-resistance network (IEICE ELEX 2020), CLPSO with 3-D model, NN junction-temperature surrogate (skips overlapping states), ACO, SOGA ([J-STAGE](https://www.jstage.jst.go.jp/article/elex/17/3/17_17.20190737/_article) [S]).
- **TRouter** (TCAD'23): criss-cross-attention network predicts the board thermal map from pads, vias, parts and wires; **backprop gradients per grid cell steer detours and via punching** ([PDF](https://www.cse.cuhk.edu.hk/~byu/papers/J94-TCAD2023-TRouter.pdf) [P]).
- HSL-TFP: DNN surrogate benchmark for temperature fields from heat-source layouts ([arXiv 2103.11177](https://arxiv.org/pdf/2103.11177) [P]).
- RBF-surrogate SA for thermal chiplet placement (WHUT, JETCAS'25) ([arXiv 2504.03808](https://arxiv.org/pdf/2504.03808) [P]).
- Control-cabinet Pareto SA (wire length vs heat): ~2× better wire length, 1.6× better heat, evaluating ~4.7% of configurations ([arXiv 1906.04825](https://ar5iv.labs.arxiv.org/html/1906.04825) [S]).

**EMC / SI / power loops.** The only automated loop-inductance work is power-converter/power-module layout (GA/Pareto with parasitic extraction).
- **ModuPlace** is the only placement paper measuring post-route EM (Keysight ADS insertion loss, crosstalk), crediting grouping by frequency and power domain ([PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf) [P]).
- Power-electronics automation [S]: GA DC-DC layout with ANSYS Q3D parasitics in the loop ([RG](https://www.researchgate.net/publication/355865177)); graph-model generative SiC module layout, GA Pareto of loop inductance vs branch mismatch, validated at 1200 V/240 A; PowerSynth (inductance vs junction temperature); hierarchical-RL thesis keeping current loops small; GaN gate loop and power loop as the two critical loops ([DTU](https://backend.orbit.dtu.dk/ws/portalfiles/portal/236953218/IAS_accepted_PCB_for_GaN_2020.pdf)).
- **NTU TCAD'25 power-flow anchor points** keep power paths compact structurally [S].
- Guidelines only: partition by function/EM, crystals next to loads, connectors at the edge (Altium) [S]; Quilter checks bypass-cap distance, via-in-loop, coil proximity, crystal placement [V].
- Qplacer (quantum chips): frequency-aware electrostatic repulsion — transplant for aggressor/victim separation ([arXiv 2401.17450](https://www.arxiv.org/abs/2401.17450v3) [S]).

**Mechanical, fixed parts, reuse.** Reuse is solved academically: D2BS finds placed templates, PCB-Migrator moves a reference layout to a changed board.
- KiCad workflow: lock connectors and critical parts before autoplacing [P]. Benchmarks contain fixed parts (NS-Place up to 947, ModuPlace 1–6, HiePlace preplaced/obstacles).
- **D2BS** subgraph-matching reference placement (Su et al., DAC'22; J. Supercomput. 2024): 100% accuracy on PCB instances, faster than VF3 ([DOI](https://doi.org/10.1145/3489517.3530670) [S]).
- **PCB-Migrator** (Han et al., DATE'26): offset constraint graph + routing-path graph matching ([DOI](https://doi.org/10.23919/DATE69613.2026.11539307) [S]); closely related to RAC relation re-solve (89.5% pass after resizes) ([LLM routing evidence](../routing/llm-routing-evidence.md)).
- MAGE (VLSI): place one reference per family of identical groups, then transform-and-merge ([LLM-guided](llm-guided-placement.md)).

## Use in kae
- **LLM assigns sides explicitly**: decaps/small passives under BGAs/QFNs on bottom; tall, THT and user-facing parts on top; then two-sided density + PA-ICM-style "bottom pins under the IC" clustering [I].
- Thermal: fast surrogate (RBF/CNN) as differentiable penalty or SA cost, or Σ PᵢPⱼ/(d²+ε) spreading term; offer a Pareto (wire length vs thermal spread) view [I].
- Power converters: hot-loop area term (input cap, switch, diode/inductor) + anchors; `away_from` constraints between aggressors and victims ([analytical](../solvers/analytical-differentiable.md)) [I].
- Pre-place mechanical anchors (connectors, holes, switches, LEDs) as fixed/edge constraints [I].
- Reuse: subgraph-match a library of proven sub-layouts (datasheet references, past boards) and re-solve stored relations/offset graphs on ECOs [I].

## Open questions
- Thermal- and EMC-aware placement have no maintained open tool; most transferable: a differentiable thermal surrogate (TRouter-style) as a penalty, and power-loop anchors / loop-area terms [I].
- No general EMC-aware placer with a coupling or loop-area objective exists for mixed-signal boards.
- Recent (2024–26) thermal-aware PCB placement literature was not searched (budget ran out).
- Qplacer area savings conflict between sources (2.14× vs ~22–26%).

## Sources
- [placement_algorithms.md § Q4, Q5, Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [cross_domain_ideas.md § Q8, Q10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)
