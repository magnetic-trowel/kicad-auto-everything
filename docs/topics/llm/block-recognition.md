# Recognizing functional blocks and reading netlists

Scope: recognizing functional blocks (buck, crystal, decoupling, analog primitives) by templates, GNNs, rules and LLMs; LLM netlist-reading accuracy. Not here: net roles -> [net-role-classification](net-role-classification.md); block -> recipe -> [function-to-recipe-mapping](function-to-recipe-mapping.md).
Keys: block recognition, subgraph isomorphism, VF2, ALIGN, GANA, PCBSchemaGen L3 Topology, motifs, key-component filter, GNN, R-SAGE, MCE-HGCN, BenchPCNP, hypergraph, Plettenberg, Quilter detectors, kicad-happy detectors, NetlistBench, GENIE-ASI, HL1/HL2/HL3, PCB-QA, HWE-Bench, AMSbench, structural LVS

## Recognition order

[I]
1. Rules and templates first: VF2 on **normalized pin-role edges** with PCBSchemaGen relaxations, plus Quilter/kicad-happy-style heuristics (near-perfect on known topologies [P]).
2. LLM-written detector for the long tail (GENIE-ASI pattern), unit-tested on 1–6 examples, accepted only if it explains all of the block's pins.
3. Port-semantics post-processing after any learned or LLM classifier: connector types, net names, part categories (GANA lesson).
4. Deterministic code builds the graph; the LLM queries it via `neighbors(pin)`, `nets_of(ref)`, `path(a, b)`; never traces connectivity in raw netlist text.
5. Stage-level groups come from sheet hierarchy and designer intent, never from the LLM (HL3 F1 0.31).
6. Hypergraph representation (nets as hyperedges) if a GNN is trained on board netlists (BenchPCNP).
7. Structural LVS (topology validity) is a stage separate from simulation and DRC.

## Exact and template matching

- **ALIGN** [P] ([README](https://github.com/ALIGN-analoglayout/ALIGN-public); [graph.py](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/master/align/schema/graph.py)): annotation via `basic_template.sp` + `user_template.sp`; NetworkX `GraphMatcher.subgraph_isomorphisms_iter()`, nodes matched by device class, edges **by pin label**; sorted matches; overlaps skipped; kept only if `check_constraint_satisfiability` passes.
- **GANA** VF2 for primitives ≈ O(n), since library subgraphs have O(1) diameter and degree ([DATE 2020](https://www.date-conference.com/proceedings-archive/2020/pdf/0921.pdf)) [P].
- **PCBSchemaGen v2 "L3 Topology"** [P] ([2602.00510v2](https://arxiv.org/abs/2602.00510); [repo, MIT](https://github.com/HZou9/PCBSchemaGen_v2)): VF2 against **5 board motifs** (half-bridge, synchronous buck, three-phase inverter, Pierce oscillator, Pi filter); relaxations: **key-component filter** (only IC, MOSFET, inductor pins must match), **boolean prefiltering**, **passive grouping**; motif eligibility from the task's IC list.
- HiLSD: symmetry search only inside matched instances [S]. ICCAD 2020 multi-axis symmetry extraction [S].
- Classical ground truth: Abel/Neuner/Graeb functional block decomposition (Integration 85, 2022); sizing-rules method (TCAD 2008) [P, as cited].

## GNNs

| Model | Data | Result | Source |
|---|---|---|---|
| GANA GCN (DATE 2020) | OTA bias 624 circuits; RF 608; 18 node features; textbook SPICE | GCN alone: OTA 90.5%, SC filter 98.2%, RF 83.64%, phased array 79.8%. Postprocessing I/II (antenna at the LNA port, oscillation at the oscillator port) -> **100% on 275 cases**, but "may require new rules as new classes… are added". Per-class constraints: OTA symmetric about the diff-pair axis; LNA close to the antenna; guard rings for LNA and mixers; oscillators symmetric | [PDF](https://www.date-conference.com/proceedings-archive/2020/pdf/0921.pdf) [P] |
| R-SAGE (ISQED 2024) | 14 circuits, 219 transistors, 120 pairs | Macro F1 0.864 vs VF2 0.841; 80.3 ms vs 594 ms; no device sizes, so technology-independent | [session](https://isqed.org/English/Archives/2024/Technical_Sessions/144.html) [P] |
| MCE-HGCN (2025) | heterogeneous multigraph | Matching-constraint F1 0.917 | [PMC12195540](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12195540/) [P] |
| GAT (ACCV'24 workshop) | analog classes | 90.9% accuracy, 91.6% precision | [CVF](https://openaccess.thecvf.com/content/ACCV2024W/MLCSA2024/html/Li_The_Application_of_Graph_Attention_Mechanism_in_the_Automation_of_ACCVW_2024_paper.html) [S] |
| GNN region prediction (ICCAD 2025) | large netlists | Predicts regions, not node matches, for scale | [2507.19518](https://arxiv.org/abs/2507.19518) [P] |
| **BenchPCNP** (Sci. Data 2026) | **50** production circuits, 5 designers, IPC-2612, **54 module labels**, CC BY 4.0; only labelled board dataset | HyperResGCN 79.07 / F1 70.77; HyperJKNet 78.34 / 72.32; GraphSAGE 67.94 / 54.60; GAT 66.59 / 53.49. Large power/ground nets create redundant pairwise edges | [PMC13046837](https://pmc.ncbi.nlm.nih.gov/articles/PMC13046837/) [P] |
| Plettenberg (ECML-PKDD 2025) | bipartite net–symbol graph, LM-embedded names; proprietary 2,396 / 849 / 944 | Edge-attributed GNNs beat MLPs; for decoupling **names alone carry most of the signal**; parallel-cap count within ±1 in ≈70% | [2506.10577](https://arxiv.org/abs/2506.10577) [P] |

## Production rules (board level)

- **Quilter** [V] ([crystal](https://docs.quilter.ai/physics-constraints/crystal-oscillators), [converter](https://docs.quilter.ai/physics-constraints/switching-converters), [bypass](https://docs.quilter.ai/physics-constraints/bypass-capacitors)): crystal = refdes X/Y with both pins on the same parent (no load-limiting resistors); switching converter = U whose output connects to an L, ≥ 2 external caps, with several caps it "somewhat arbitrarily select[s] one"; bypass-cap parent pin by explicit wire -> voltage-named pin -> equal split.
- **kicad-happy** (MIT) [P] ([how-it-works](https://github.com/aklofas/kicad-happy/blob/main/how-it-works.md)): union-find nets, then **60+ deterministic detectors** in dependency order (LDO = FB + ≥ 2 power pins, no SW/BOOT; switcher = SW+BOOT or SW+inductor; motor-driver false-positive guard); harness ≈5,800 projects; "Detection accuracy is harder to quantify".

## LLM netlist-reading benchmarks

| Benchmark | Key numbers | Source |
|---|---|---|
| **NetlistBench** (MLCAD 2026; 2,342 analog CMOS cases, 24 families) | Recognition: Claude Sonnet 4.6 98%, GPT-4.1 74%, Gemini 2.5 Flash 75%, DeepSeek-V4-Flash 74%, Qwen3.6-Flash 62%, Qwen3-30B 55%. Relational: node incidence 15–98%, terminal connectivity 6–99%, **terminal-neighbour 2–97%**, structural equivalence 49–90%. Explicit attributes ≈99–100%. Dependent edits: Claude 80% -> 26% (3 -> 15 edits), GPT-4.1 71% -> 34%. Reasoning mode +30–40 pts for weaker models. Analog CMOS only; transfer to RF, power, digital or board netlists unverified | [2608.12197](https://arxiv.org/abs/2608.12197) [P] |
| **GENIE-ASI** (MLCAD 2025, TUM + Sony; **transistor-level op-amps, not PCB**, corrected) | 300 netlists from ≈47k. GPT-4.1 + GENIE F1strict 0.70; zero-shot 0.49–0.64. HL1 **0.97**, HL2 **0.81**, HL3 **0.31** (all models 0.05–0.31). AnyGraph GNN 0.12–0.30. In direct analysis "LLMs often skipped" elements; detector code beats direct reading. Discrepancy: EDA and verification notes give F1 1.0 / 0.81 / 0.31 (simple, moderate, complex); netlist note HL1 0.97 | [2508.19393](https://arxiv.org/pdf/2508.19393) [P] |
| PCB-QA | JSON + tools 0.88 vs native 0.55 vs PDF 0.43 -> [read-representations](read-representations.md#pcb-qa-input-formats) | [2606.23704](https://arxiv.org/abs/2606.23704) [P] |
| HWE-Bench (board) | Conventional pin names "extremely high" accuracy; multiplexed/redundant pins -> omissions, hallucinations; "context cognition overload" at hundreds to thousands of pins | [2603.18102](https://arxiv.org/abs/2603.18102) [P] |
| CIRCUIT | GPT-4o 48.04% final answers, 27.45% unit tests | [2502.07980](https://arxiv.org/abs/2502.07980) [P] |
| AMSbench | Gemini 2.5 Pro: element 0.94, connection judgment 0.85, connection F1 0.88, netlist NED 0.91 (GPT-4o 1.40, Claude 3.7 1.65) | [2505.24138](https://arxiv.org/abs/2505.24138) [P] |
| CircuitSense | > 85% perception; < 19% symbolic derivation | [2509.22339](https://arxiv.org/abs/2509.22339) [P] |
| Image2Net | 80.77% success, NED 0.116 | [2508.13157](https://arxiv.org/abs/2508.13157) [P] |
| SPICED | 93.32% Trojan coverage, 93.4% TPR | [2408.16018](https://arxiv.org/abs/2408.16018) [P] |
| Validation vs simulation (150 gpt-4o-mini circuits) | 10.7% rejected by the validator yet silent in ngspice; 4.7% passed validation but failed in ngspice | [2609.26830](https://arxiv.org/abs/2609.26830) [P] |
| Masala-CHAI / AnalogRetriever | ≈7,500 schematics, +46% Pass@1; original compile rate 22%, repaired to 100% | [2411.14299](https://arxiv.org/abs/2411.14299), [2604.23195](https://arxiv.org/abs/2604.23195) [P] |

## Open questions

- No published precision/recall for board-level recognition of layout-relevant blocks (buck, crystal, USB) on KiCad designs.
- GANA's TCAD 2023 tables not retrieved.

## Sources
- [netlist_datasheet_understanding.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)
- [verification_papers.md § 1 row 32](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
- [llm_for_eda.md § 1 analog](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
