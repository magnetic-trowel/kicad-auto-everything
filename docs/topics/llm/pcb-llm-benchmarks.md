# PCB and EDA benchmarks for LLM layout work

Scope: numbers from LLM layout and understanding benchmarks, vendor/field numbers, and comparison hygiene. Not here: OmniRouting in routing context -> [routing/llm-routing-evidence](../routing/llm-routing-evidence.md); OmniLayout data -> [placement/benchmarks-and-metrics](../placement/benchmarks-and-metrics.md); PCBWorld -> [routing/pcbworld](../routing/pcbworld.md); our evaluation stack -> [verification/benchmarks](../verification/benchmarks.md).
Keys: OmniRouting, NRR, PRR, OmniLayout, RR, routability, pad overlap, PCBWorld, clean-pass, D3-A, D3-B, PCB-Bench, PCB-QA, HWE-Bench, PCBInnoBench, PCBSchemaGen, PDAgent-Bench, EEBench, CUABench-KiCad, @k, seeds, relaxed D3 rules, TILOS, TEWL, Cherry Blossom, Project Speedrun, DeepPCB vs Quilter

## Results

1. LLM routing is far from usable: agentic best NRR ≈ half an open-source router's, under a third of humans' ([OmniRouting](#omnirouting)) [P].
2. LLM placement is connectivity-aware but geometrically illegal: frontier RR beats academic placers, yet most outputs have pad overlaps (verification correction); not like-for-like with legal-by-construction placers ([OmniLayout](#omnilayout)) [I].
3. Understanding benchmarks (PCB-Bench, PCB-QA, HWE-Bench, NetlistBench) reward netlist and document reading, not layout quality; no independent multi-board benchmark of LLM placement quality on real boards exists [P].
4. Cross-paper numbers are rarely comparable (router versions/settings, @k, seeds, harness, potential functions); report them [P].

## OmniRouting

[P] ([2608.04434](https://arxiv.org/pdf/2608.04434)); dataset, NRR/PRR table, DRC/shorts, preroute and step ablations -> [routing/llm-routing-evidence](../routing/llm-routing-evidence.md#omnirouting); tool ablations -> [vision-feedback](vision-feedback.md#evidence). NRR = share of nets connected and DRC-clean; PRR = pad-to-pad equivalent. Extra facts kept here:
- Best zero-shot = Claude Opus 4.8 (12.60% / 15.41% NRR/PRR); GPT-5.5 zero-shot 9.13% / 12.26%; best agentic = GPT-5.5 with all tools (27.98% / 30.34%). Dataset also counts 494K wire segments.
- GPT-5.5 all tools: DRC totals 48.06 -> 9.35, shorts 39.5% -> 9.1%. GPT-5.5 tools and steps changed together: not a clean step-budget test [I].
- Few-shot examples "can reduce violations by routing less".
- Verification #29: the "<13% vs ~94%" figure had been wrongly sourced to OmniLayout.

## OmniLayout

[P] ([2607.03261 v3](https://arxiv.org/pdf/2607.03261)); task, metrics, full RR table (GPT-5.5 0.95 few-shot, Chen DAC'25 0.62, Quilter 0.84), 79.82% pad-overlap / 72.89% out-of-bounds, AUC effects -> [placement/benchmarks-and-metrics](../placement/benchmarks-and-metrics.md#methods-and-results). Extra facts kept here:
- Gemini 3.1 Pro 0.34 zero-shot rises to 0.91–0.92 with schematic netlist or image. Per-model legality and RR-on-legal-only are not in our notes: RR is not like-for-like with legal-by-construction placers [I].
- Licence conflict: ethics statement CC-BY-4.0 code and data; third-party recon (2026-08-15) found no licence and 5 boards public. EMNLP venue unconfirmed.

## PCBWorld and RAC

- PCBWorld [P] ([2607.05915 v4](https://arxiv.org/pdf/2607.05915)): clean-pass, engine engagement (0.65 / 0.19 / 0.02), speed, tokens, seed protocol, router settings, relaxed D3 rules -> [routing/pcbworld](../routing/pcbworld.md#results-table-21-5). On D2, GPT-5.4 is 219× slower than PPO and 35× slower than Freerouting (94.04 s vs 0.43 s / 2.69 s).
- RAC [P]: 98 tasks; coordinates 23.2% vs relations 90.9% -> [interfaces-relations-vs-coordinates](interfaces-relations-vs-coordinates.md#rac-relational-agent-contract).

## Understanding benchmarks

| Benchmark | Content | Headline | Source |
|---|---|---|---|
| PCB-Bench (ICLR 2026) | ≈3,700 text QAs, 500 image QAs, 174 OSHWHub boards | Gemini-2.5-Pro 100%, GPT-5 90.9% on Basic Wiring Error Identification; **that subset has ≈11 items, so the gap is one question** (verification #24). Open-source models 45–55%. Claude-Opus-4.1 93.3% on Placement Macro-level CQ | [ICLR PDF](https://proceedings.iclr.cc/paper_files/paper/2026/file/051f3997af1dd65da8e14397b6a72f8e-Paper-Conference.pdf) [P] |
| PCB-QA (MLCAD 2026) | 480 yes/no questions, 8 KiCad projects | JSON 0.88 vs native 0.55 vs PDF 0.43 -> [read-representations](read-representations.md#pcb-qa-input-formats) | [2606.23704](https://arxiv.org/abs/2606.23704) [P] |
| HWE-Bench | 300 spec->schematic tasks, 2,914 datasheets; model selects parts | Best fully correct 8.15% -> [synthesis](../synthesis/schematic-generation-landscape.md#papers-and-benchmarks-20242026) | [2603.18102](https://arxiv.org/pdf/2603.18102) [P] |
| PCBInnoBench (NeurIPS 2026, SJTU + Huawei) | 372 tasks | 22.0% vs 7.3% Pass@1 with vs without an expert trajectory | [poster](https://neurips.cc/virtual/2026/poster/139034) [P] |
| PCBSchemaGen / PCBBench | v2: 227 tasks, 22 domains, 480 real ICs (MIT) | Pass@1 per model -> [synthesis](../synthesis/schematic-generation-landscape.md#papers-and-benchmarks-20242026). "~300 tokens per IC" is from v2; the 16k baseline and topology-aware retrieval from v1. Slide numbers 86.3/84.0/61.0% are not in the paper | [v2](https://arxiv.org/abs/2602.00510v2) [P] |
| NetlistBench, GENIE-ASI | analog netlist reading | -> [block-recognition](block-recognition.md#llm-netlist-reading-benchmarks) | [P] |
| PDAgent-Bench | 353 physical-design problems, 11 models | GPT-5.5 73.3% on root cause; weak on long-horizon tool use | [2606.17253](https://arxiv.org/abs/2606.17253) [P] |
| EEBench (atopile) | circuit design in atopile; **layout excluded** | Score = 0.65 × technical + 0.35 × cost-efficiency, deterministic grading. 1 Sept 2026: Claude Opus 5 61.6%, Grok 4.6 57.1%, Fable 5.1 56.4%. GPT-6 Astra 69.3 ±10.7 (**conflict:** another source says no Astra result existed; provisional). Later mirror: Opus 5.5 75.0% [S] | [EEBench](https://eebench.org/methodology.html) [V] |
| CUABench-KiCad | 25 schematic GUI tasks | Persistent memory: 0.267 -> 0.440 reward | [2610.22686](https://arxiv.org/abs/2610.22686) [P] |

## Vendor and field numbers

| Claim | Number | Source |
|---|---|---|
| Cherry Blossom, 40 boards (GPT-6 Astra + real part data + verification gate) | First-pass fab yield 94% -> 97%; design time −54%; "Forty boards is our own sample" | [blog](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design) [V] |
| Quilter Project Speedrun (8-layer i.MX 8M Mini) | 428 h manual quote vs 27 h automated + 38.5 h cleanup | [blog](https://www.quilter.ai/blog/cleaning-up-an-ai-designed-computer) [V] |
| DeepPCB vs Quilter (3 boards: 98/290/414 airwires) | Completion 97.3% vs 87.7%; Quilter +44% vias; first result 1–2 min vs 15–20 min; a "414-net" figure elsewhere is derivative | [blog](https://deeppcb.ai/deeppcb-vs-quilter-open-source-routing-compared-2026/) [V] |
| Altium Academy video | **168 DRC violations (AI tool) vs 0 (human)**; not the GPT-6 Astra demo or the StationX build, contrary to the EDA note | [video](https://www.youtube.com/watch?v=qX29OWSYTmI) [S] |
| Li et al. DAC 2026 | -> [llm-guided-placement-systems](llm-guided-placement-systems.md#llm-roles-across-systems) | [S, via survey] |

## Hygiene rules

- @k: report @1 and @5; @1 vs @5 drops (GPT-5.4-mini, PPO-terminal) -> [pcbworld](../routing/pcbworld.md#results-table-21-5) [P].
- Seeds: report seed means for stochastic routers; PCBWorld protocol -> [pcbworld datasets](../routing/pcbworld.md#datasets) [P].
- Router settings: Freerouting is the de facto oracle (NS-Place, Cypress v1.9.0, ModuPlace with PcbRouter, OmniLayout); PCBWorld's 2.1.0 config -> [pcbworld](../routing/pcbworld.md#results-table-21-5); OrthoRoute ran without board design rules; so cross-paper numbers are not comparable [P].
- Potential function: PCBWorld's repository default differs from the paper's -> [pcbworld reward](../routing/pcbworld.md#reward-and-metrics) [P].
- Relaxed D3 rules: every D3 clean-pass is under PCBWorld's relaxed `.kicad_pro` rule set ([pcbworld datasets](../routing/pcbworld.md#datasets)); state the rule set when comparing ([open_board_sources.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/open_board_sources.md); verification #7) [P].
- Strong baselines: TILOS SA beat AlphaChip-style CT on proxy cost 17/17 and HPWL 16/17; "Using weak or outdated baselines may lead to misleading conclusions" ([2302.11014](https://arxiv.org/abs/2302.11014)) [P].
- Harness effects: ARC-AGI-3 62.7% vs 99.9% depending on two undisclosed API settings ([zerowithdot](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/)) [S]; gains incomparable across unmatched models, budgets, backends (handoff survey, [2606.19795](https://arxiv.org/abs/2606.19795)) [P].
- Metric choice: TEWL ignores overlaps, so "RL beats human" can be an artifact (Lim 2026); proxy cost correlates weakly with post-route PPA (TILOS) [P].
- Per-board vs average: ModuPlace beats baselines on average only [P].
- Few-shot effects conflict: few-shot lifted GPT-5.5 RR to its best, barely moved grouping AUC, and in routing "can reduce violations by routing less".
- Paper errors to discount: OmniRouting's agentic-framework text describes refining "component positions" (apparently copied from OmniLayout); HiePlace wrongly calls Quilter "a widely used open-source tool".

## Ladders for our system

[I]
1. Placement: OmniLayout-style RR/PRWL + pad-overlap and out-of-bounds rates; targets to beat Chen DAC'25 (0.62) and Quilter (0.84); academic placers are a low bar.
2. Routing: PCBWorld D3-A/B with matched @k and seed protocol, pinned router versions and settings.
3. Own scorecard vs human reference boards: unrouted count; DRC by severity incl. disabled categories; parity; footprint–datasheet consistency; loop area, decap distance, ampacity, via count and area; tokens, cost, latency per verified board -> [verification/benchmarks](../verification/benchmarks.md).
4. Legality always in acceptance (blocks metric gaming); random-relation or random-region controls show the LLM's semantic content is what helps (VeoPlace).

## Open questions

- No independent replication of any LLM-PCB result.
- No joint place-and-route comparison of an LLM-steered KiCad flow vs Freerouting baselines on real boards.
- EEBench Astra score disputed; OmniLayout licence and data availability disputed.

## Sources
- [verification_papers.md § 1, § 2.1, § 2.9, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
- [llm_for_eda.md § 1, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
- [field_reports_and_ux.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)
