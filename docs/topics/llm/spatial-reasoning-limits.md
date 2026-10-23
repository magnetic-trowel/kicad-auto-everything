# LLM spatial and geometric reasoning limits

**TL;DR**
- Frontier models fail at **constructing globally consistent geometry**. Difficulty scales with the **number of coupled relations**, not the number of objects: PlanarBench solve rates fall to **1.0–1.6% at 11–12 edges** on graphs of at most 7 vertices [P].
- **Tools fix arithmetic, not planning or global constraints.** A code interpreter adds 30–40 pp on distance and angle tasks but little on planning; on PCB tasks, Python *lowered* coordinate clean-pass from 23.2% to 21.0% [P].
- "The bottleneck lies in **extracting constraints from spatial representations**, not in reasoning over them". Authoritative tool-computed state helps (TopoBench: 40% → 50%) [P].
- On PCBs, the same pattern shows as pad overlaps, out-of-bounds parts, shorts and wrong rotations. LLMs remain useful for **noticing** (e.g. "unrouted nets cluster in one region") [P, anecdote].

## Key facts

### General benchmarks

| Benchmark | Key numbers and findings | Source |
|---|---|---|
| **PlanarBench** (91 models; crossing-free ASCII drawings of planar graphs) | Edges drive difficulty: r = −0.85, vs −0.47 for vertices (−0.80 partialled). Mean score 46.4% at 5 edges → 16.3% at 8 → 5.1% at 10 → 1.0–1.6% at 11–12. Best GPT-5.2-pro 159.5/199. Extended thinking: Sonnet 3.7 39.5 → 95.5. Cliff around 30B params. Failures: missing edges at high-degree nodes; "relational load", with early placements constraining later routes | [2606.02010](https://arxiv.org/abs/2606.02010) [P] |
| **TopoBench** | Fewer than 1/4 of hard puzzles solved. "Premature commitment" and "constraint forgetting" are causal; repeated reasoning is benign. Structured engine state: hard Bridges 40% → 46% (state) → 50% (full suite with legal moves and components); ASCII render tool 42% | [2603.12133](https://arxiv.org/abs/2603.12133) [P] |
| **FloorplanQA** (ICML 2026; 2,000 JSON/XML layouts; 15 models) | Distances and angles are fine. Failures: constraint satisfaction; area summed instead of unioned; centroids of non-axis-aligned polygons; shortest paths in clutter; multi-step planning. Code interpreter +30–40 pp on distance and angle only. Advice: external geometric solvers (unions, shoelace centroid, clearance buffering, oriented rectangle search, A*) | [2507.07644](https://arxiv.org/abs/2507.07644) [P] |
| **SpatialEval** (NeurIPS 2024) | Competitive models can fall below random | [2406.14852](https://arxiv.org/abs/2406.14852) [P] |
| **Grid Spatial Understanding** | Egocentric frames and 3D-from-coordinates are weak; fine-tuned small models approach frontier models | [2603.17333](https://arxiv.org/abs/2603.17333) [P] |
| **PPNL** | Promising with reason/act, but "fails to perform long-term temporal reasoning"; fine-tunes don't generalize to larger or cluttered grids | [2310.03249](https://arxiv.org/abs/2310.03249) [P] |
| **GPSBench** / **Text2CAD-Bench** | Geometry computations are weaker than geographic facts; performance degrades on complex topology | [2602.16105](https://arxiv.org/abs/2602.16105), [2605.18430](https://arxiv.org/abs/2605.18430) [P] |
| **MMCircuitEval** (3,614 QA) | Gaps in back-end design and computation | [2507.19525](https://arxiv.org/abs/2507.19525) [P] |
| **OPT-Engine** | Tools "help with local calculations [but] still fail to adhere to global optimization constraints" | [2601.19924](https://arxiv.org/abs/2601.19924) [P] |

### PCB-specific evidence

| Evidence | Numbers | Source |
|---|---|---|
| OmniRouting, LMM traces | Best zero-shot NRR 12.60% (humans 93.58%). 69.8–431.3 DRC violations, 20.5–78.3% nets shorted. Fails multi-net path planning, layer and via assignment, congestion. GND routed as traces, not pours | [2608.04434](https://arxiv.org/abs/2608.04434) [P] |
| OmniLayout, LMM placement | 79.82% of outputs had at least one pad overlap; 72.89% had a part out of bounds; 80% of parts on top; reference similarity below 60%. Routability scores are high, though our notes don't say whether they were gated on legality (see [pcb-llm-benchmarks.md](pcb-llm-benchmarks.md)) | [2607.03261](https://arxiv.org/pdf/2607.03261) [P] |
| RAC, coordinate interface | 23.2%; with Python 21.0% | [2610.20935](https://arxiv.org/pdf/2610.20935) [P] |
| Holodeck | GPT-4 absolute coordinates MRR 0.364, about equal to random (0.369) | [2312.09067](https://arxiv.org/abs/2312.09067) [P] |
| PCB-Bench (ICLR 2026) | Models "struggle significantly with the spatial logic and strict constraints" | [Lacuna summary](https://lacuna.tiptreesystems.com/work/pcb-bench-benchmarking-llms-for-printed-circuit-board-placement-and-routing/wrk_3aa259abb5e3e453177ad0f77da09471) [S] |
| StationX agent log | Via 0.0285 mm from an LED pad: "I had verified the clearance against one pad and forgotten its neighbour"; "I have no spatial intuition, only arithmetic" | [StationX](https://app.stationx.net/articles/ai-pcb-design) [P, anecdote] |
| A6M-Zero (Claude Opus 4.8) | "no idea about the orientation of the components, it did not do any proper routing" | [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/) [P, anecdote] |
| Autocuro | Distances, overlaps, clearances and trace widths "failed completely" from images | [Autocuro](https://autocuro.com/blog/can-llms-verify-pcb-designs) [V] |
| MCP builders | LLMs got inverse rotations wrong for labels (Copperhead PR #398) | [S] |

### Where LLMs add value instead
- **Noticing.** "The unrouted nets all terminated in the same congested region" led to staggering U6–U10, and **314/314 nets** routed. "It pointed at a geometric problem I hadn't recognized as a problem" ([tinycomputers](https://tinycomputers.io/posts/what-routing-314-nets-taught-me-about-ai-assisted-pcb-design.html)) [P, anecdote].
- **Long horizons need recent models.** Multi-hour tool-driving sessions are reliable only with frontier models released since early to mid-2026 ([2608.31006](https://arxiv.org/abs/2608.31006)) [P].
- **Surveys:**
  - "No LLM-driven autonomous agent has yet demonstrated a complete, human-free tape-out" ([2512.23189](https://arxiv.org/abs/2512.23189)) [P].
  - The "syntax trap": plausible code rather than physically correct hardware ([2608.27184](https://arxiv.org/abs/2608.27184)) [P].
  - "No GenAI tools independently validate PCB layouts – they instead work as EDA design assistants" ([2606.17074](https://arxiv.org/abs/2606.17074), 80 papers) [P].

## Recommendations for our system

1. Never ask the LLM for coordinates, distances or overlap judgments. Compute them in tools and hand back facts [I].
2. **Decompose by functional group** so each LLM decision involves few coupled relations (PlanarBench).
3. Give the LLM authoritative structured state (legal moves, clusters, overlaps, unrouted connections), not renders (TopoBench).
4. Delegate unions, centroids, clearances and paths to geometry libraries (FloorplanQA's list).
5. Enable reasoning or extended thinking modes for planning steps (PlanarBench, NetlistBench).
6. Turn the LLM's "noticing" ability into tools that report congestion and failure attribution (see [../ux/agent-tooling-reliability-patterns.md](../ux/agent-tooling-reliability-patterns.md)).

## Conflicts and open questions

- Would fine-tuned small models close the gap on PCB spatial tasks, as GSU and CoDeLayout suggest for other domains? Untested.
- How many coupled relations per decision is safe for PCB groups? Unmeasured.
- **Apparent conflict on code tools:** writing code helps *analysis* (GENIE-ASI detector code; FloorplanQA distance/angle +30–40 pp) but not geometric *construction* or planning (RAC coordinates + Python 21.0%; FloorplanQA planning). Use code for measurement and detection, solvers for construction [I].

## Sources
- research notes:
  - [llm_for_eda.md § 1 surveys, § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
  - [verification_papers.md § 1 row 26](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
  - [field_reports_and_ux.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)

See also: [interfaces-relations-vs-coordinates.md](interfaces-relations-vs-coordinates.md), [vision-feedback.md](vision-feedback.md), [pcb-llm-benchmarks.md](pcb-llm-benchmarks.md), [block-recognition.md](block-recognition.md)
