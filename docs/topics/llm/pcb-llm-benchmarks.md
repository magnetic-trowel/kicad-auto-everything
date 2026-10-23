# PCB and EDA benchmarks for LLM layout work: numbers and hygiene

**TL;DR**
- **Routing by LLM is far from usable.** OmniRouting's best zero-shot model connects 12.6% of nets DRC-clean (agentic best 28.0%), against 56.2% for an open-source router and 93.6% for humans [P].
- **LLM placement is connectivity-aware but geometrically illegal.** On FreeRouting routability, frontier LMMs (GPT-5.5: 0.90 zero-shot, 0.95 few-shot) beat the academic placers (0.23–0.62), but about 80% of outputs have pad overlaps (corrected per the verification note) [P]. Our notes don't say whether RR was gated on legality, and the overlap rates are pooled across models, so this is not like-for-like with legal-by-construction placers [I].
- **Understanding benchmarks** (PCB-Bench, PCB-QA, HWE-Bench, NetlistBench) reward the netlist and documents, not layout quality. No independent multi-board benchmark of LLM placement quality on real boards exists [P].
- **Cross-paper numbers are rarely comparable.** Router versions and settings, @k, seeds, harness and potential functions all differ. Report them [P].

## Key facts

### Layout benchmarks

**OmniRouting** [P] ([2608.04434](https://arxiv.org/pdf/2608.04434)). Penn State–led; 1,681 EAGLE-derived open-hardware designs: 494K wire segments, 84.6K vias, 4.3K pours, 2–8 layers. NRR is the share of nets connected and DRC-clean; PRR is the pad-to-pad equivalent.

| Router | NRR | PRR |
|---|---|---|
| Best LMM zero-shot (Claude Opus 4.8) | 12.60% | 15.41% |
| GPT-5.5 zero-shot | 9.13% | 12.26% |
| Best agentic (GPT-5.5, all tools) | 27.98% | 30.34% |
| PcbRouter (open source) | 56.20% | 71.37% |
| GPCB learned router | 0.69% | — |
| Human | 93.58% | 95.91% |

Further results:
- For GPT-5.5 with all tools, DRC totals fell from 48.06 to 9.35 and shorts from 39.5% to 9.1%.
- "More steps do not guarantee improvement": GPT-5.5 went 16.97 → 20.78 steps with NRR 21.71% → 27.98%, GPT-5-mini 18.38 → 23.65 steps with NRR 9.86% → 6.82%. For GPT-5.5 this compares the no-tool agentic baseline with all tools, so tools and step counts changed together; it is not a clean test of step budget [I].
- Few-shot examples "can reduce violations by routing less".
- **(Verification #29):** the "<13% vs ~94%" figure had been wrongly sourced to the OmniLayout paper.

**OmniLayout** [P] ([2607.03261 v3](https://arxiv.org/pdf/2607.03261)). Led by Penn State with one MSR co-author; the original note's "MSR et al." is corrected. 9 LMMs and 6 PnR tools.
- **Data:** 77.24K placements, 168.82K pads, 55.83K netlist graphs, and 139.4K nets with layout and schematic spatial weights.
- **Output:** x, y, side and orientation (including MR0–MR270).

FreeRouting routability (RR):

| Group | RR |
|---|---|
| GPT-5.5 | 0.90 zero-shot; **0.95** few-shot |
| GPT-5-mini | 0.84 |
| Claude Sonnet 4.6 | 0.76 |
| Gemini 3.1 Pro | 0.34 zero-shot; 0.91–0.92 with schematic netlist or image |
| Qwen | 0.31 |
| SA-PCB / NS-Place / Cypress / PCBAgent / Chen DAC'25 | 0.25 / 0.23 / 0.33 / 0.42 / 0.62 |
| Quilter | 0.84 |
| Human | 1.00 |

Legality and other findings:
- 79.82% of outputs had at least one pad overlap; 72.89% had a part out of bounds; 80% of parts were placed on top. These rates are pooled; per-model legality is not in our notes, nor whether RR was computed on legal outputs only.
- Reference similarity was below 60%; the best end-to-end pass rate was 62.6% (GPT-5.5 few-shot).
- Schematic context raised grouping AUC in all 15 comparisons (+0.079 to +0.091); few-shot examples −0.006.
- **Licence conflict:** the ethics statement says code and data are CC-BY-4.0; third-party recon (2026-08-15) found no licence and only 5 boards public. The EMNLP venue was not confirmed.

**PCBWorld** [P] ([2607.05915 v4](https://arxiv.org/pdf/2607.05915)). Full detail is in [../routing/pcbworld.md](../routing/pcbworld.md).
- **Clean-pass:** GPT-5.4 0.65 on D3-A (99 boards, ≤31 pads), against 0.80 for Freerouting and 0.86 for PPO. Every LLM scores 0 on the 10-board, 2-layer D3-B set.
- **Engine engagement:** interactive 0.65 vs plan-and-execute 0.19 vs engine-free 0.02.
- **Speed (corrected):** GPT-5.4 is 219× slower than PPO but 35× slower than Freerouting on D2; on D3-A, 126× / 33× / 356× slower than PPO / Freerouting / KRT.
- **Tokens:** about 107k (D2), 425k (D3-A) and 1.92M (D3-B) per episode.
- **Corrected:** the prompt had no reward and no DRC list, so LLM numbers are a lower bound.
- **Seed protocol:** routers and RL are 4-seed means; LLMs are a single best-of-5 run.

**RAC** [P]: 98 tasks; coordinates 23.2% vs relations 90.9%. See [interfaces-relations-vs-coordinates.md](interfaces-relations-vs-coordinates.md).

### Understanding benchmarks

| Benchmark | Content | Headline | Source |
|---|---|---|---|
| PCB-Bench (ICLR 2026) | about 3,700 text QAs, 500 image QAs, 174 OSHWHub boards | Gemini-2.5-Pro 100% and GPT-5 90.9% on Basic Wiring Error Identification. **That subset has about 11 items, so the gap is one question** (verification #24). Open-source models 45–55%. Claude-Opus-4.1 93.3% on Placement Macro-level CQ | [ICLR PDF](https://proceedings.iclr.cc/paper_files/paper/2026/file/051f3997af1dd65da8e14397b6a72f8e-Paper-Conference.pdf) [P] |
| PCB-QA (MLCAD 2026) | 480 yes/no questions, 8 KiCad projects | JSON 0.88 vs native 0.55 vs PDF 0.43 | [2606.23704](https://arxiv.org/abs/2606.23704) [P] |
| HWE-Bench | 300 spec→schematic tasks, 2,914 datasheets | Best Claude Sonnet 4.5 **8.15%**, GPT-5.2 6.58%, others 4–5% | [2603.18102](https://arxiv.org/pdf/2603.18102) [P] |
| PCBInnoBench (NeurIPS 2026, SJTU + Huawei) | 372 tasks | 22.0% vs 7.3% Pass@1 with vs without an expert trajectory | [poster](https://neurips.cc/virtual/2026/poster/139034) [P] |
| PCBSchemaGen / PCBBench | v2: 227 tasks, 22 domains, 480 real ICs (MIT) | Gemma-4-31B passes 81.3%. The "~300 tokens per IC" figure is from v2; the 16k baseline and topology-aware retrieval are from v1. Slide numbers 86.3/84.0/61.0% are not in the paper | [v2](https://arxiv.org/abs/2602.00510v2) [P] |
| NetlistBench, GENIE-ASI | analog netlist reading | see [block-recognition.md](block-recognition.md) | [P] |
| PDAgent-Bench | 353 physical-design problems, 11 models | GPT-5.5 73.3% on root cause; weak on long-horizon tool use | [2606.17253](https://arxiv.org/abs/2606.17253) [P] |
| EEBench (atopile) | circuit design in atopile; **layout excluded** | Score = 0.65 × technical + 0.35 × cost-efficiency, deterministic grading. 1 Sept 2026: Claude Opus 5 61.6%, Grok 4.6 57.1%, Fable 5.1 56.4%. GPT-6 Astra 69.3 ±10.7 (**conflict:** another source says no Astra result existed; provisional). A later mirror shows Opus 5.5 at 75.0% [S] | [EEBench](https://eebench.org/methodology.html) [V] |
| CUABench-KiCad | 25 schematic GUI tasks | Persistent memory: 0.267 → 0.440 reward | [2610.22686](https://arxiv.org/abs/2610.22686) [P] |

### Vendor and field numbers

| Claim | Number | Source |
|---|---|---|
| Cherry Blossom, 40 boards (GPT-6 Astra plus real part data plus a verification gate) | First-pass fab yield 94% → 97%; design time −54%; "Forty boards is our own sample" | [blog](https://www.trycherryblossom.com/blog/gpt-6-astra-pcb-design) [V] |
| Quilter Project Speedrun (8-layer i.MX 8M Mini) | 428 h manual quote vs 27 h automated + 38.5 h cleanup | [blog](https://www.quilter.ai/blog/cleaning-up-an-ai-designed-computer) [V] |
| DeepPCB vs Quilter (3 boards: 98/290/414 airwires) | Completion 97.3% vs 87.7%; Quilter +44% vias; first result in 1–2 min vs 15–20 min. A "414-net" figure seen elsewhere is derivative | [blog](https://deeppcb.ai/deeppcb-vs-quilter-open-source-routing-compared-2026/) [V] |
| Altium Academy video | **168 DRC violations (AI tool) vs 0 (human)**. This is *not* the GPT-6 Astra demo or the StationX build, contrary to the EDA note | [video](https://www.youtube.com/watch?v=qX29OWSYTmI) [S] |
| Li et al. DAC 2026 (LLM-guided PCB placement) | −55%/−73% WL/vias vs a commercial placer, −34%/−26% vs NS-Place, −15%/−13% vs Quilter (6 boards) | [2606.19795](https://arxiv.org/pdf/2606.19795) [S, via survey] |

### Hygiene rules
- **@k:** report both @1 and @5. GPT-5.4-mini falls from 0.58 to 0.20 CP on D2 under @1; PPO-terminal from 0.92 to 0.61 [P].
- **Seeds:** report seed means for stochastic routers. PCBWorld used 4 seeds for routers and RL but a single best-of-5 run for LLMs [P].
- **Router settings:**
  - Freerouting is the de facto oracle (NS-Place, Cypress v1.9.0, ModuPlace with PcbRouter, OmniLayout).
  - PCBWorld ran 2.1.0 with `-mp 10` and a 4 GiB heap; OrthoRoute ran without board design rules.
  - So cross-paper numbers are not comparable [P].
- **Potential function:** PCBWorld's repository default potential differs from the paper's [P].
- **Relaxed D3 rules:** PCBWorld's rebuild chain set some DRC severities to ignore and some rule floors to 0 in `.kicad_pro`, and D3 is the 679 boards that then passed DRC. Every D3 clean-pass number is measured under that relaxed rule set; state the rule set when comparing ([open_board_sources.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/open_board_sources.md); verification #7) [P].
- **Strong baselines:** TILOS found SA beat AlphaChip-style CT on proxy cost 17/17 and on HPWL 16/17. "Using weak or outdated baselines may lead to misleading conclusions" ([2302.11014](https://arxiv.org/abs/2302.11014)) [P].
- **Harness effects:**
  - ARC-AGI-3 scored 62.7% vs 99.9% depending on two undisclosed API settings ([zerowithdot](https://zerowithdot.com/blog/gpt-6-astra-impact-on-cad/)) [S].
  - The handoff survey warns gains are incomparable across unmatched models, budgets and backends ([2606.19795](https://arxiv.org/abs/2606.19795)) [P].
- **Metric choice:** TEWL ignores overlaps, so "RL beats human" can be an artifact (Lim 2026). Proxy cost correlates weakly with post-route PPA (TILOS) [P].
- **Per-board vs average:** ModuPlace beats all baselines on average, but baselines win individual boards [P].

## Recommendations for our system

1. **Placement ladder:** OmniLayout-style RR/PRWL plus pad-overlap and out-of-bounds rates. Targets to beat are **Chen DAC'25 (0.62) and Quilter (0.84)**; academic placers are a low bar [I].
2. **Routing ladder:** PCBWorld D3-A/B with a matched @k and seed protocol, and pinned router versions and settings.
3. **Own layout scorecard** against human reference boards:
   - unrouted count;
   - DRC by severity, **including disabled categories**;
   - parity;
   - footprint–datasheet consistency;
   - loop area, decap distance, ampacity, via count and area;
   - tokens, cost and latency per verified board.

   See [../verification/benchmarks.md](../verification/benchmarks.md).
4. Legality is always part of acceptance, to block metric gaming.
5. Include random-relation or random-region controls to show that the LLM's semantic content is what helps (VeoPlace).

## Conflicts and open questions

- No independent replication of any LLM-PCB result exists.
- No joint place-and-route comparison exists of an LLM-steered KiCad flow against Freerouting baselines on real boards.
- The EEBench Astra score is disputed; OmniLayout's licence and data availability are disputed.
- **Few-shot effects conflict:** few-shot lifted GPT-5.5 placement RR to 0.95, barely moved grouping AUC (−0.006), and in routing "can reduce violations by routing less".
- **Paper errors to discount:** OmniRouting's agentic-framework text describes refining "component positions", apparently copied from OmniLayout. HiePlace wrongly calls Quilter "a widely used open-source tool".

## Sources
- research notes:
  - [verification_papers.md § 1, § 2.1, § 2.9, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
  - [llm_for_eda.md § 1, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
  - [field_reports_and_ux.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)

See also: [../routing/pcbworld.md](../routing/pcbworld.md), [spatial-reasoning-limits.md](spatial-reasoning-limits.md), [../data/imitation-and-learned-scores.md](../data/imitation-and-learned-scores.md)
