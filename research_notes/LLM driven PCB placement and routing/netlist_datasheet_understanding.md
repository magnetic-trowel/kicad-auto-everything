# Circuit Understanding for Layout Intent: Netlist + Schematic + Datasheet → Semantically Annotated Design

> **Scope.** The front end of an LLM-driven KiCad placement and routing system. It covers:
> - recognizing functional blocks;
> - classifying nets;
> - extracting layout constraints from datasheets and app notes;
> - capturing designer intent in KiCad.
>
> Per-interface rule packs (USB, Ethernet, DDR and so on) are covered by another researcher. They appear here only briefly.
>
> **Provenance tags (used on every finding).**
> - **[P-full]**: primary source, read in full or across the relevant sections this session (PDF or page text pulled and checked).
> - **[P-abs]**: primary source, but only the abstract or metadata was read (arXiv API record, publisher abstract).
> - **[P-doc]**: vendor or project documentation, read directly.
> - **[S]**: search-engine summary or aggregator. Not verified against the original.
>
> All arXiv items are **preprints** unless a venue is named. Dates are as of 2026-10-20.
>
> **Method.** There were two passes.
> - **Pass 1** was restricted: only raw.githubusercontent.com was reachable.
> - **Pass 2** had full internet access. arXiv, docs.kicad.org, ti.com, docs.quilter.ai, docs.flux.ai, celus.io, huggingface.co and PMC were all reachable.
> - In pass 2 the shared web-search quota ran out partway through. After that, only known URLs were fetched directly; no further searching was done.
> - Still unreachable in pass 2: IEEE Xplore (HTTP 418), dl.acm.org (403), analog.com, st.com and snapeda.com.

---

## 1. Subcircuit / structure recognition from netlists (graph matching, GNNs, rules, LLMs) and reported accuracy

### Takeaway
Recognition approaches split cleanly by reliability:
- **Exact template matching (VF2)** is near-perfect on known topologies.
- **GNNs** handle structural variants, but they need rule-based post-processing to reach 100%. GANA's GCN alone scored 79.8–98.2% node accuracy on its test sets. Post-processing lifted all 275 test cases to 100%.
- **Rule/heuristic detectors over pin names plus neighbour types** are what production board-level tools actually ship (Quilter, kicad-happy).
- **LLMs reading netlists directly are unreliable on relational/topological queries.** On NetlistBench, "terminal-neighbour incidence" ranges from 2% to 97% across models. GENIE-ASI's strict F1 falls from 0.97 to 0.31 as structures get more abstract.

LLMs do much better when they **write detector code** (GENIE-ASI), or when they are given a **compact JSON netlist with tool-based filtering** rather than raw KiCad files or PDFs (PCB-QA: 0.88 vs 0.55 vs 0.43 accuracy).

### Cited Findings

**Exact graph / template matching**

- **ALIGN** (DARPA IDEA; UMN, Texas A&M and Intel) starts with a *circuit annotation* step that "creates a multilevel hierarchical representation of the input netlist". Hierarchies are identified using a template library (`basic_template.sp`) plus `user_template.sp`. Optional constraint JSON files are per hierarchy. **[P-doc]** — [ALIGN-public README](https://github.com/ALIGN-analoglayout/ALIGN-public)
  - Its matcher is NetworkX `GraphMatcher(...).subgraph_isomorphisms_iter()`.
  - Node matching is by device model class; edge matching is by **pin label**.
  - Matches are sorted to remove non-determinism, overlapping matches are skipped, and a match is kept only if `check_constraint_satisfiability` passes.
  - **[P-full]** — [align/schema/graph.py](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/master/align/schema/graph.py)
- **GANA uses VF2** for primitives (current mirrors, differential pairs). Because library subgraphs have "O(1) diameter and O(1) degree", the authors estimate VF2's complexity at O(n) for their problem. **[P-full]** — [GANA, DATE 2020 PDF](https://www.date-conference.com/proceedings-archive/2020/pdf/0921.pdf)
- **PCBSchemaGen v2** (board level) runs a verifier layer "L3 Topology".
  - It does VF2 subgraph isomorphism against **five motifs**: half-bridge, synchronous buck, three-phase inverter, Pierce oscillator and Pi filter.
  - It uses three relaxations:
    - a *key-component filter*: only IC, MOSFET and inductor pins must match exactly;
    - *boolean prefiltering*: a cheap signature gate before VF2;
    - *passive-element grouping*: passive terminals on a shared net collapse to one class.
  - Per-task motif eligibility is decided by the IC list.
  - **[P-full]** — [arXiv 2602.00510v2, App. A.3](https://arxiv.org/abs/2602.00510); [PCBSchemaGen_v2 repo](https://github.com/HZou9/PCBSchemaGen_v2)
- **HiLSD** (ASP-DAC 2004) pattern-matches subcircuits first and then searches for symmetry only inside those instances. **[S]** — [HiLSD PDF](https://labs.ece.uw.edu/ssrl/workspace/iprail/web_IPRAIL/ASPDAC04_2.pdf)
- **ICCAD 2020 hierarchical symmetry extraction** (UMN) uses graph-based methods to find multiple symmetry axes. **[S]** — [arXiv 2010.00051](https://ar5iv.labs.arxiv.org/html/2010.00051)
- **Classical rule-based recognition** still serves as ground truth in recent work. GENIE-ASI's labels come from the rule-based functional block decomposition of Abel, Neuner and Graeb (*Integration* 85, 2022) inside the ACST tool. The "sizing rules method" (Massier et al., TCAD 2008) is the classic library-based approach. **[P-full]** (as cited in GENIE-ASI) — [arXiv 2508.19393](https://arxiv.org/pdf/2508.19393)

**GNN-based recognition (analog IC level) — accuracy**

- **GANA** (Kunal et al., DATE 2020, pp. 55–60). **[P-full]** — [DATE 2020 PDF](https://www.date-conference.com/proceedings-archive/2020/pdf/0921.pdf)
  - **Training data:**
    - OTA bias set: 624 circuits, 32,152 nodes, 2 labels.
    - RF set: 608 circuits, 21,886 nodes, 3 labels (LNA, mixer, oscillator).
    - 18 node features (element type, whether a value is low, medium or high, etc.).
    - 80:20 train/validation split. Training circuits come from textbooks and papers in SPICE format.
  - **Test results (GCN alone):**

    | Test set | Circuits | Nodes | GCN accuracy |
    |---|---|---|---|
    | OTA bias | 168 | 9,296 | 90.5% |
    | Switched-capacitor filter | 1 | 57 | 98.2% (56/57) |
    | RF | 105 | 17,640 | 83.64% |
    | Phased-array system | 1 | 902 | 79.8% |

  - **After post-processing:**
    - OTA bias goes from 90.5% to 100% after "Postprocessing I".
    - RF goes from 83.64% to 89.24% after Postprocessing I, then to 100% after "Postprocessing II". Postprocessing II uses the antenna at the LNA port and the oscillating signal at the oscillator port.
    - The paper's conclusion: "postprocessing provides 100% accuracy in all 275 test cases evaluated here".
    - Postprocessing II "requires domain-specific annotation, and may require new rules as new classes of subcircuits are added".
  - **Constraints per recognized class:**
    - OTA: symmetric about the differential-pair axis.
    - LNA: "placed close to the antenna".
    - LNAs and mixers: guard rings.
    - Oscillators and BPFs: symmetric about the cross-coupled pair.
    - Wireless blocks: minimize wire length.
- **GANA journal version**, "GNN-Based Hierarchical Annotation for Analog Circuits" (IEEE TCAD 2023, vol. 42, no. 9, pp. 2801–2814): the abstract reports a "high degree of accuracy". Its results tables were *not* retrieved because IEEE Xplore was blocked. **[S]** — [UMN page](https://neurospin.umn.edu/gnn-based-hierarchical-annotation-analog-circuits); [DBLP](https://dblp.uni-trier.de/pid/241/4371.html)
- **R-SAGE (relational GraphSAGE)** (ISQED 2024) frames recognition as multi-class link prediction of "analog functional pairs".
  - Dataset: 14 circuits, 219 transistors, 120 functional pairs across 7 primitive categories.
  - **Macro F1 0.864 vs VF2 0.841**; test time 80.3 ms vs 594 ms.
  - Device sizes are deliberately not used as features, so the model stays technology-independent.
  - **[P-abs]** — [ISQED 2024 session page](https://isqed.org/English/Archives/2024/Technical_Sessions/144.html)
- **MCE-HGCN** (*Micromachines*, June 2025) uses a heterogeneous attribute multigraph, mixed-domain attention and an SVM classifier to extract **matching constraints**. Mean **F1 0.917** across processes and circuit types. **[P-abs]** — [PMC12195540](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12195540/)
- **GCN classification with data augmentation** for analog circuit classes (*Sensors*, March 2023) is motivated by the small number of available schematics. **[P-abs]** — [PMC10054122](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10054122/)
- **GNN region prediction for target-circuit matching** in large netlists (ICCAD 2025) predicts high-probability regions instead of doing node-to-node matching, for scalability. **[P-abs]** — [arXiv 2507.19518](https://arxiv.org/abs/2507.19518)
- A GAT model for analog circuit design automation (ACCV 2024 workshop) reports 90.9% accuracy, 91.6% precision and 91.9% mAP versus GraphSAGE and other baselines. **[S]** — [CVF open access](https://openaccess.thecvf.com/content/ACCV2024W/MLCSA2024/html/Li_The_Application_of_Graph_Attention_Mechanism_in_the_Automation_of_ACCVW_2024_paper.html)

**GNNs at PCB / board level**

- **BenchPCNP** (*Scientific Data*, 25 Feb 2026; DOI 10.1038/s41597-026-06818-y) is the **only public board-level dataset with functional-module labels** found.
  - **50** production-verified circuits, partitioned by **5 designers** following IPC-2612, into **54 module labels** (power supply, filter, LED, connector, voltage regulator, transceiver and others). The label distribution is long-tailed.
  - Protel-2 netlists, released on figshare under **CC BY 4.0**. The designs were bought from a Taobao PCB design shop, with a copyright transfer.
  - **Best baselines (node-classification accuracy / F1):**
    - Hypergraph models: HyperResGCN 79.07 / 70.77; HyperJKNet 78.34 / 72.32.
    - Plain-graph models are weaker: GraphSAGE 67.94 / 54.60; GAT 66.59 / 53.49.
    - The authors attribute the gap to large power and ground nets creating redundant pairwise edges.
  - **[P-full]** — [PMC13046837](https://pmc.ncbi.nlm.nih.gov/articles/PMC13046837/)
- **Plettenberg et al., "GNNs for Automatic Addition of Optimizing Components in PCB Schematics"** (ECML-PKDD 2025, per HWE-Bench's citation).
  - **Representation:** a bipartite graph of nets and symbols, with pins as edges. Node names are embedded with a pre-trained language model.
  - **Task:** node-pair prediction.
  - **Three expert-labelled proprietary datasets:**
    - pull-ups/pull-downs: 2,396 graphs;
    - RC filters: 849 graphs;
    - decoupling caps: 944 graphs.
    - Graphs range from 6 to 702 nodes; on average only 1.4–2.8 nodes are added per graph.
  - **Findings:**
    - GNNs with edge attributes beat MLPs.
    - For decoupling, **node names alone carry most of the signal**, because "supply and ground nets... mostly have well-defined names".
    - The predicted *count* of parallel decoupling caps is within ±1 in about 70% of cases.
  - Only example graphs are public (github.com/pasplett/pcb-node-pair-gnn).
  - **[P-full]** — [arXiv 2506.10577](https://arxiv.org/abs/2506.10577)

**Rule-based recognition in board-level tools (production)**

- **Quilter "Circuit Comprehension"** reads the schematic and board file, automatically detects physics constraints, and has the user validate them before layout. **[P-doc]** — [Quilter: Define physics comprehensions](https://docs.quilter.ai/using-quilter/define-physics-comprehensions)
  - **Crystal:** reference designator starts with X or Y, and **both pins connect directly to the same parent component**. Crystals with load-limiting resistors are not supported. **[P-doc]** — [Quilter: Crystal Oscillators](https://docs.quilter.ai/physics-constraints/crystal-oscillators)
  - **Switching converter:** reference designator starts with U, and **its output connects to an inductor whose reference designator starts with L**. It supports only configurations with ≥2 external capacitors plus an output inductor. With multiple input or output caps, it "somewhat arbitrarily select[s] one". **[P-doc]** — [Quilter: Switching Converters](https://docs.quilter.ai/physics-constraints/switching-converters)
  - **Bypass capacitor:** a cap between a component and ground. It is assigned to a parent pin with this priority:
    1. an explicit wire in the schematic;
    2. parent pins with voltage-type names (e.g., Vin);
    3. an equal split when connected to several same-named pins.

    **[P-doc]** — [Quilter: Bypass Capacitors](https://docs.quilter.ai/physics-constraints/bypass-capacitors)
- **kicad-happy** (MIT) does union-find net building on pin coordinates, then runs **60+ deterministic detectors** in dependency order. Examples:
  - LDO = FB plus ≥2 power pins and no SW/BOOT;
  - switching regulator = SW+BOOT, or SW plus an inductor;
  - false-positive guard against motor drivers.

  It is tested on a harness of 5,829 KiCad projects. "Detection accuracy is harder to quantify." **[P-full]** — [how-it-works](https://github.com/aklofas/kicad-happy/blob/main/how-it-works.md); [methodology_schematic.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_schematic.md)

**LLM-based netlist understanding — benchmarks (read in full where marked)**

- **GENIE-ASI** (MLCAD 2025; Sony AI collaborators). **[P-full]** — [arXiv 2508.19393](https://arxiv.org/pdf/2508.19393)
  - **Benchmark:** 300 synthetic op-amp netlists, curated from about 47,000 generated by ACST/FUBOCO. Device names are anonymized.
  - **Hierarchy levels:**
    - HL1: device level (MosfetDiode, load/compensation caps).
    - HL2: structure level (DiffPair, current mirror, inverter).
    - HL3: stage level (first/second stage, feedback, load and bias parts).
  - **Method:** the LLM writes instructions, then Python code with test assertions, with a code-repair loop.
  - **Overall results:** GPT-4.1 with GENIE-ASI has **F1strict 0.70** overall. **Zero-shot direct prompting reaches F1strict only 0.49–0.64** across frontier models.
  - **Per level (GPT-4.1 with GENIE-ASI, F1strict):** HL1 **0.97**, HL2 **0.81**, HL3 **0.31**. For HL3, every model scores between 0.05 and 0.31.
  - **GNN baseline:** the AnyGraph graph foundation model, given the same 6 demonstration netlists, reaches only F1 0.26–0.30 (HL1) and 0.12–0.15 (HL2/HL3).
  - **Authors' observations:**
    - Direct LLM analysis "proved unreliable in practice: LLMs often skipped" elements.
    - LLMs "perform better when executing tasks via generated Python code rather than reasoning directly over netlists".
    - With one-shot direct code generation, Claude 3.7 Sonnet and Gemini 2.5 did best.
- **NetlistBench** (MLCAD 2026). **[P-full]** — [arXiv 2608.12197](https://arxiv.org/abs/2608.12197); [repo](https://github.com/WoshiMayou/NetlistBench)
  - **Benchmark:** 2,342 analog CMOS SPICE cases in 24 task families, graded by a deterministic canonical-structure oracle.
  - **Recognition subtotal:**

    | Model | Recognition subtotal |
    |---|---|
    | Claude Sonnet 4.6 | **98%** |
    | GPT-4.1 | 74% |
    | Gemini 2.5 Flash | 75% |
    | DeepSeek-V4-Flash | 74% |
    | Qwen3.6-Flash | 62% |
    | Qwen3-30B | 55% |

  - **Relational queries vary enormously across models:**
    - node incidence: 15–98%;
    - semantic terminal connectivity: 6–99%;
    - **terminal-neighbour incidence: 2–97%**;
    - structural equivalence: 49–90%.
  - **Explicit attributes are easy:** parameters, ordered terminals and subcircuit ports score about 99–100%.
  - **Long-horizon edits fall off sharply:** Claude drops from 80% at 3 dependent edits to 26% at 15; GPT-4.1 drops from 71% to 34%.
  - **Reasoning mode** adds 30–40 points for weaker models (DeepSeek-V4-Flash: 52% to 81%).
  - **Limitation stated by the authors:** results "should not be assumed to transfer unchanged to RF, power, digital, or mixed-signal netlists".
- **PCB-QA** (MLCAD 2026). **[P-full]** — [arXiv 2606.23704](https://arxiv.org/abs/2606.23704)
  - **Benchmark:** 480 yes/no questions over 8 open-source **KiCad** projects. Categories: theory/layout connectivity, component datasheet, SPICE behaviour.
  - **Input format strongly matters** (GPT-5.4 Nano, 25% split):

    | Input format | Accuracy | F1 |
    |---|---|---|
    | KiCad-exported **PDF** | 0.43 | 0.28 |
    | **Native KiCad `.net` + `.cir`** | 0.55 | 0.45 |
    | **Proposed JSON** (hierarchical components and nets) | **0.88** | **0.90** |

  - **Full dataset:** Gemini 3 Flash reaches **93%** with JSON.
  - Inputs reach about 100k tokens on complex projects, so Python helper tools filter the relevant subcircuits and nets.
  - Datasheet questions use a MiniLM-embedding retrieval with 500-character chunks. These are the weakest and most variable category.
- **CIRCUIT** (510 analog QA pairs): GPT-4o reaches 48.04% on final answers, but **only 27.45% of grouped "unit tests"**. Topology is the hardest part. **[P-abs]** — [arXiv 2502.07980](https://arxiv.org/abs/2502.07980)
- **AMSbench** (about 8,000 questions). **[P-full]** — [arXiv 2505.24138](https://arxiv.org/abs/2505.24138)
  - On schematic-image perception, the best model (Gemini 2.5 Pro) scores:
    - element classification: 0.94;
    - connection judgment: 0.85;
    - connection identification: F1 0.88;
    - **full-netlist normalized edit distance (NED): 0.91**, where lower is better (GPT-4o 1.40, Claude 3.7 Sonnet 1.65).
  - The authors: even Gemini's netlists "require substantial modifications to align with the ground truth".
- **CircuitSense** (8,006+ problems): closed models score above 85% on component and topology perception but **below 19% on symbolic derivation**. **[P-abs]** — [arXiv 2509.22339](https://arxiv.org/abs/2509.22339)
- **Image2Net** reaches an 80.77% success rate and mean NED 0.116 converting analog diagrams to netlists. **[P-abs]** — [arXiv 2508.13157](https://arxiv.org/abs/2508.13157)
- **MMCircuitEval** (ICCAD 2025) has 3,614 QA pairs, drawn partly from datasheets. It shows gaps on back-end design and computation. **[P-abs]** — [arXiv 2507.19525](https://arxiv.org/abs/2507.19525)
- **SPICED** (PAINE 2024): LLM chain-of-thought plus few-shot detection of syntactic bugs and analog Trojans in netlists. 93.32% average Trojan coverage and 93.4% TPR. **[P-abs]** — [arXiv 2408.16018](https://arxiv.org/abs/2408.16018)
- **"Validation and Simulation Catch Different Errors"** (2026, preprint), on 150 LLM-generated circuits from gpt-4o-mini:
  - 10.7% were rejected by a topology validator **yet ran in ngspice with no warning** (e.g., a dangling resistor gave 5.00 V instead of 2.50 V);
  - 4.7% passed validation but failed in ngspice.
  - **[P-abs]** — [arXiv 2609.26830](https://arxiv.org/abs/2609.26830)
- **Masala-CHAI** extracts SPICE from schematic images: about 7,500 schematics, giving +46% Pass@1 in AnalogCoder. **[P-abs]** — [arXiv 2411.14299](https://arxiv.org/abs/2411.14299)
  - An audit by AnalogRetriever found the original netlist **compile rate was 22%**, repaired to 100%. **[P-abs]** — [arXiv 2604.23195](https://arxiv.org/abs/2604.23195)
- **AnalogCoder** (AAAI 2025) solved 20 of 24 tasks. **[P-doc]** — [repo](https://github.com/laiyao1/AnalogCoder)
- **PCB-Bench** (ICLR 2026): about 3,700 text QAs and about 500 image QAs, including functional-block recognition, plus 174 OSHWHub boards for screenshot-to-description. **[P-doc]** — [project page](https://digailab.github.io/PCB-Bench/)

### Inferences
- **For a KiCad tool, the evidence favours rules plus templates over GNNs.**
  - At board level, the transistor-level variants that motivated GANA live inside ICs.
  - Production tools (Quilter, kicad-happy) recognize crystals, converters and bypass caps from *reference-designator prefixes, pin names and one-hop neighbours*.
  - The only board-level labelled benchmark (BenchPCNP) tops out at about 79% node accuracy with hypergraph GNNs, on just 50 circuits.
- PCBSchemaGen's motif VF2 with relaxations (key-component filter, passive grouping) is the right shape for a board-level template matcher. Edges should be labelled with **normalized pin roles**.
- **LLMs should not be asked to trace connectivity from raw netlist text.**
  - NetlistBench shows only the best model reliably answers "what is connected to this terminal".
  - PCB-QA shows a compact hierarchical JSON with query tools beats native KiCad exports by 33 points.
  - So: deterministic code builds the graph, and the LLM queries it through tools such as `neighbors(pin)`, `nets_of(ref)` and `path(a, b)`.
- **Use GENIE-ASI's pattern for the long tail.** The LLM writes detector code from 1–6 examples. The code is unit-tested against the examples and then executed deterministically. Expect near-perfect results on low-level structures and poor results on large "stage-level" groupings.
- **GANA's post-processing lesson transfers directly.** *Port semantics* resolved the remaining misclassifications: the antenna at the LNA port, the oscillating signal at the oscillator port. On PCBs the analogues are connector types, net names and part categories. Wire them in as post-processing rules after any learned or LLM classifier.

### Gaps
- GANA's TCAD 2023 results tables (IEEE blocked).
- No published precision/recall for *board-level* recognition of specific blocks (buck, crystal, USB) on KiCad designs. Quilter and kicad-happy publish detection *rules* but no accuracy. BenchPCNP measures module partitioning, not typed recognition of layout-relevant blocks.
- The LLM4-IC8K / LMM4-IC4K footprint-geometry results were not read in full (see §3).

---

## 2. Net classification: diff pairs, power, clocks, high-speed — from names, pin metadata, part data and IBIS

### Takeaway
Net roles in practice come from four signals:
1. **Power symbols and power-net names**;
2. **net-name suffix/keyword rules**;
3. **pin names and roles on the connected IC pins**;
4. **designer-assigned net classes** (both Quilter and Flux key off native net classes first).

KiCad's diff-pair router is strictly name-based: `+`/`-` or `P`/`N` suffixes, which cannot be mixed. Quilter's detector is broader and also accepts A/B, P/M and t/c.

**IBIS models** hold machine-readable facts that no other source has: explicit differential pairing (`[Diff Pin]`), pin→buffer-model mapping with `POWER`/`GND`/`NC` reserved names, buffer type (`Model_type`), and 20–80% edge rates (`[Ramp]`). KiCad's simulator already loads IBIS. Even so, no tool was found that uses IBIS to classify nets for layout. That is an open opportunity.

### Cited Findings
- **KiCad (official manual):**
  - "Differential pairs in KiCad are defined as nets with a common base name and a positive and negative suffix. KiCad supports using + and -, or P and N as the suffix… The suffix styles cannot be mixed: the nets USB+ and USB_N do not form a differential pair."
  - The differential gap comes from the net class settings.
  - **[P-doc]** — [KiCad 9 PCB Editor manual](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html)
- **KiCad net-class patterns (official):**
  - Patterns use wildcards (`*`, `?`) **and regular expressions**. Assignments are dynamic: new matching nets join automatically.
  - A net matching several patterns gets all of the classes. Values come from the highest-priority class that has the field set, with Default as the fallback.
  - Net names include the full sheet path (e.g., `/` prefix for root-sheet local labels).
  - **[P-doc]** — [KiCad 9 Schematic Editor manual](https://docs.kicad.org/9.0/en/eeschema/eeschema.html)
- **KiCad diff-pair hazards (community):**
  - The suffix must be the last character.
  - Symbol pin names (e.g., `Pin_P`) do not create pairable nets.
  - `XTAL_P`/`XTAL_N` names make the router apply diff-pair rules even to single-ended traces.
  - **[S]** (forum) — [suffix thread](https://forum.kicad.info/t/differential-pair-doesnt-work-with-any-of-the-suffixes/26166); [pin-name thread](https://forum.kicad.info/t/differential-pair-defined-with-pin-names-in-symbol/41801); [XTAL thread](https://forum.kicad.info/t/kicad6-pcbnew-picks-wrong-trace-width-and-clearance-from-netclass/34007)
- **Quilter diff-pair detection:**
  - Nets "must be in differentialpair or synonymous net class (75ohm etc)", **and** names must end in a supported paired suffix:

    | Suffix | Example |
    |---|---|
    | `+`/`–` | TX+, TX- |
    | `A`/`B` | SSTXA, SSTXB |
    | `P`/`M`, last character | RFoutP, RFoutM |
    | `P`/`M`, second-to-last character | USB_DPX, USB_DMX |
    | `P`/`N` | DP, DN |
    | `t`/`c` | ddr0_dqs_t, ddr0_dqs_c |

  - Names starting with **V** are never treated as pairs, to avoid power nets.
  - Pairs with series R/C show up as two pairs but are merged at compile.
  - For each pair the user supplies differential impedance, the associated single-ended impedance and the carrier frequency (GHz).
  - Limitations: no multi-drop or fly-by pairs; none on 2-layer stack-ups; microstrip only, no coplanar waveguide.
  - **[P-doc]** — [Quilter: Differential Pairs](https://docs.quilter.ai/physics-constraints/differential-pairs)
- **Quilter power nets:**
  - Detected if the name "matches our various patterns for being a voltage or power net" **or** the net is in a "Power" net class. A motor net can be forced in this way.
  - Default max current: **200 mA for nets detected below 3 V, 500 mA above 3 V**. The user overrides it per net.
  - Width comes from IPC calculations per stack-up.
  - PRC "Overheated Length" flags segments with **>20 °C** estimated rise.
  - Single-ended impedance nets (50 or 75 Ω) are **manual only**: width within 5%, invalid-width tolerance 10%.
  - Signals not captured "are treated as generic, low-speed digital signals".
  - **[P-doc]** — [Quilter: Power Nets](https://docs.quilter.ai/physics-constraints/power-nets); [Single-ended Impedance](https://docs.quilter.ai/physics-constraints/single-ended-impedance-control); [Define physics comprehensions](https://docs.quilter.ai/using-quilter/define-physics-comprehensions)
- **Flux "Net Type"**:
  - Seven priority buckets: **High Speed, Analog, Power, Medium Speed, Low Speed, Uncertain, Ground**.
  - "Flux will infer the Net Type of each net"; the user can change it. Auto-Layout routes the buckets in that order.
  - Users are told to mark diff pairs and high-speed nets in the schematic, and to add "Max Current" or "Thermal Rise" to power nets.
  - **[P-doc]** (Flux blog, July 2025) — [AI Auto-Layout Just Got Smarter](https://www.flux.ai/p/blog/ai-auto-layout-just-got-smarter)
- **kicad-happy keyword classes:**
  - Classes: ground, power, clock (SCL/SCK/CLK/XTAL), data, high_speed (USB/CAN/LVDS/ETH), analog (ADC/AIN/VREF), control, chip_select, interrupt, debug, config.
  - Power rails are identified from `#PWR`/`#FLG` symbols plus name heuristics.
  - IO-domain mapping uses VDDIO, VCCA/VCCB.
  - **[P-full]** — [methodology_schematic.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_schematic.md)
- **LLM pin-semantics evidence (HWE-Bench, 300 board-level tasks):**
  - With conventional pin names such as "USBD, USBP, CLK, SDA, TXD, RXD, RST", "the connection accuracy of all models is extremely high".
  - With "Multiplexed Pins" or "Redundant Pins" (parallel grounds), models "often produce serious omissions or connection hallucinations".
  - Hundreds to thousands of pins cause "context cognition overload".
  - **[P-full]** — [arXiv 2603.18102](https://arxiv.org/abs/2603.18102)
- **PCBSchemaGen's 32-role pin ontology** spans 7 groups:
  - power supply (supply/primary/secondary vdd and gnd);
  - signal I/O (sense ±, out, out ±);
  - logic in/out;
  - MOSFET (gate, drain, source, **kelvin source**);
  - **buck regulator (vin, gnd, sw, fb, en, boot)**;
  - half-bridge (hb, hs, ho, lo);
  - transformer and passive (terminal, anode, cathode).

  It has four predicate templates: supply-pair, must-be-connected, driving-pair, diff-pair-distinct. **[P-full]** — [arXiv 2602.00510v2, Tables 8–9](https://arxiv.org/abs/2602.00510)
- **KiCad pin electrical types:** Input, Output, Bidirectional, Tri-state, Passive, Unspecified, Power input, Power output, Open collector, Open emitter, Not connected. **[P-doc]** (kicad-doc GitHub mirror, possibly stale) — [eeschema_library_editor.adoc](https://github.com/KiCad/kicad-doc/blob/master/src/eeschema/eeschema_library_editor.adoc)

**IBIS as a net-classification source** (specification read directly) — all from [IBIS Version 7.2 spec (PDF)](https://ibis.org/ver7.2/ver7_2.pdf), **[P-full]**:

- **`[Pin]`** (required) associates each pin with a data-book `signal_name` and a `model_name`. The reserved model names **POWER, GND, NC** (and CIRCUITCALL) directly label supply, ground and unconnected pins. Optional per-pin R/L/C package parasitics are included.
- **`[Diff Pin]`** "associates differential pins": a non-inverting pin, its `inv_pin`, the receiver threshold `vdiff`, and launch-delay skews `tdelay_typ/min/max`. This is **authoritative differential pairing, independent of net names**.
- **`Model_type`** values:
  - Input, Output, I/O, 3-state, Open_drain, I/O_open_drain, Open_sink, Open_source, the *_ECL variants, Terminator, Series, Series_switch;
  - true-differential types: Input_diff, Output_diff, I/O_diff, 3-state_diff.
  - Inputs carry Vinl/Vinh thresholds.
- **`[Ramp]`** gives the rise and fall times of a buffer as dV/dt "from 20% to 80% of the final value", into a default 50 Ω load, with typ/min/max corners. Example given: 2.20 V / 1.06 ns typical.
- **`[Model Selector]`** offers alternative drive strengths for the same pin.

Related:
- A practitioner constraint guide calls IBIS `[Ramp]` "the best place to get rise and fall times" for setting high-speed constraints. **[S]** — [PCEA High-Speed Constraint Values (Pfeil)](https://pcea.net/wp-content/uploads/2022/04/High-Speed-Constraint-Values-v2-Pfeil.pdf)
- **KiCad already ingests IBIS** for simulation. The symbol fields are `Sim.Library`, `Sim.Ibis.Pin` and `Sim.Ibis.Model`; KiCad ships IBIS_DEVICE, IBIS_DEVICE_DIFF and IBIS_DRIVER helper symbols. "KiCad does not ship with IBIS models for symbols." **[P-doc]** — [KiCad 9 Schematic Editor manual, simulator section](https://docs.kicad.org/9.0/en/eeschema/eeschema.html)

### Inferences
- **Use a layered net classifier, in this order:**
  1. **Explicit designer intent**: net classes, directive labels, Flux/Quilter-style "Power" or "differentialpair" classes.
  2. **Authoritative part data**: IBIS `[Pin]`/`[Diff Pin]`/`Model_type`/`[Ramp]` when an `.ibs` file exists; otherwise datasheet pin roles mapped to a role ontology.
  3. **Topology**: SW pin plus inductor gives a switch node; FB pin plus divider gives feedback; XIN/XOUT plus a crystal gives a crystal net.
  4. **Names**: suffix and keyword rules.
  5. **LLM adjudication** for what is left, citing the pins.

  Each layer records its evidence, and higher layers override lower ones.
- **Edge rate from IBIS turns "is this net fast?" into a computation.** Use t_r(20–80%) together with estimated route length (critical length roughly ∝ t_r × propagation velocity) rather than keyword guesses. Data-rate and impedance tables per protocol stay deterministic, and come from the other researcher's rule packs.
- **Mismatches between detectors are warning signs.** Quilter's suffix set is broader than KiCad's. If the front end detects an A/B or t/c pair, KiCad's router will not pair it until the nets are renamed to `+`/`-` or `_P`/`_N`. The front end should *propose renames* and never silently rely on non-KiCad conventions.
- HWE-Bench's multiplexed-pin failures argue for resolving MCU pin-mux (the role of each pin in *this* design) deterministically. Sources for that are the MCU vendor's pin-config exports or an explicit table in the schematic, rather than LLM inference.

### Gaps
- **No tool or paper found that classifies nets for layout from IBIS data.** The search quota ran out before vendor constraint managers (Allegro, Xpedition) could be checked for IBIS-driven classification.
- Availability of IBIS files per MPN (what fraction of KiCad BOM parts have an `.ibs`) is not quantified.
- No measured accuracy for net-role classification on PCB netlists.

---

## 3. Datasheet / app-note mining: extracting layout guidelines, tables and figures — tools and reliability

### Takeaway
Extracting **electrical facts** from datasheets is now measurably reliable *when it is staged and grounded*:
- 98.8% property faithfulness for a chunked, provenance-preserving pipeline, against 76.1% one-shot;
- D2S-FLOW reaches exact match 0.86, F1 0.92;
- datasheet-aware compatibility checking reaches 97.5% using deterministic scripts for the numbers.

Naive "upload the PDF and ask" is not reliable:
- the best model passes only 30.7% of professional-PDF questions in GDP.pdf;
- on PCB-QA, PDF input scores 0.43 accuracy;
- one model **fabricated source text without ever opening the datasheet**.

**Layout-guideline extraction remains unbenchmarked.** There is also an asymmetry in vendor content:
- regulator datasheets are almost entirely qualitative ("as close as possible");
- MCU/SoC hardware design guides (Espressif, Microchip) give **numeric** rules.

**Tooling.** MinerU2.5-Pro leads open table parsing (TEDS 93.4 on OmniDocBench v1.6). Marker trails badly on tables (65.8).

### Cited Findings

**Extraction pipelines and their reliability**

- **Hierarchical hardware knowledge-graph construction** (chunked property extraction, hierarchical routing, iterative refinement, source provenance, deterministic graph updates):
  - **98.8% property faithfulness vs 76.1% for one-shot**, evaluated on 20 datasheets.
  - It fully covers 83.6% of the baseline's faithful properties; the baseline covers only 10.5% of its properties.
  - "Naïve one-shot processing omits relevant specifications even when the document fits within the model's context window."
  - **[P-abs]** — [arXiv 2610.12762](https://arxiv.org/abs/2610.12762)
- **"Fidelity Is Not Enough"** (EMNLP 2026 Industry):
  - "One model passed our fidelity check without ever opening the datasheet". A structured-output constraint had silently disabled tool use, and the model answered "with fabricated source text".
  - Logging every tool call ("dispatch-level instrumentation") caught all 50 planted faults that withheld the checked tools, with no false flags on 207 clean runs.
  - Physical measurement could verify only 2 of 37 datasheet claims.
  - **[P-abs]** — [arXiv 2608.28439](https://arxiv.org/abs/2608.28439)
- **Datasheet-aware compatibility verification:**
  - Builds a design graph, retrieves only the properties needed by explicit verification criteria, and **generates deterministic scripts** ("avoids reliance on LLMs for numerical computation").
  - **97.5% accuracy** on 7 designs with 34 datasheets, and **8.6× less context** than upload-and-query.
  - **[P-abs]** — [arXiv 2608.25217](https://arxiv.org/abs/2608.25217)
- **D2S-FLOW** (datasheet → SPICE parameters): document focusing, hierarchy-aware retrieval and entity normalization give EM 0.86 / F1 0.92 / exact correctness 0.96, with 38% fewer tokens. **[P-abs]** — [arXiv 2502.16540](https://arxiv.org/abs/2502.16540)
- **GDP.pdf** (CVPR 2026 workshop): professional-PDF questions, datasheets included, that at least two frontier models had failed.
  - **The best of 17 models passes 30.7%.**
  - Recurring errors: "misaligned tables, misread charts, skipped footnotes and exclusions… amendments that supersede earlier text".
  - **[P-abs]** — [arXiv 2607.11192](https://arxiv.org/abs/2607.11192)
- **ElecSafety:** using datasheet and manual rules improves LLM safety judgments, but results stay "unreliable on near-boundary and missing-information scenarios", and "a correct label often rests on the inaccurate constraints". **[P-abs]** — [arXiv 2610.06905](https://arxiv.org/abs/2610.06905)
- **DRCY** (deployed on AllSpice Hub) runs a production multi-agent schematic review against datasheets. **[P-full]** — [arXiv 2603.15672](https://arxiv.org/abs/2603.15672)
  - A Critic Agent scores each datasheet extraction out of 10: feature completeness 25%, **pin-function coverage 40%**, application info 20%, typical application circuits 15%.
  - It retries alternative sources up to 5 times and keeps the best.
  - Extractions are cached for 7 days, keyed by part number and source URL.
  - **k parallel review runs** are reconciled by a consensus agent.
  - It uses a "strong" model for review and a "weak" model for extraction.
  - **The paper gives no accuracy numbers.**
- **HWE-Bench preprocessing:** PDFs → Markdown via **MinerU**; an LLM then extracts descriptions and pin definitions into JSON, which "greatly mitigat[es] misunderstandings caused by document formatting". **[P-full]** — [arXiv 2603.18102](https://arxiv.org/abs/2603.18102)
- **kicad-happy datasheets skill** (community, read in pass 1):
  - Page selection: TOC → keyword density → fallback, 8–15 pages.
  - Category prompts, then a typed `SpecValue{min, typ, max, unit, condition, evidence{page, confidence}}`.
  - Quality-score trust gates, PDF-hash staleness, and "null, never guess".
  - It **explicitly skips app-note and "recommended for X" prose**.
  - **[P-full]** — [datasheet-extraction.md](https://github.com/aklofas/kicad-happy/blob/main/datasheet-extraction.md)
- **DocEDA**: a datasheet-specific layout-analysis model plus chain-of-thought LLM parameter extraction, and YOLO-based circuit-diagram parsing. **[P-abs]** — [arXiv 2412.05301](https://arxiv.org/abs/2412.05301)

**Footprint and figure geometry**

- **LLM4-IC8K / ICGeo8K** (arXiv 2508.03725; an ICML 2026 listing titled "LMM4-IC4K" appears to be a related version):
  - Finding: current large multimodal models "severely suffer from inaccurate geometric perception" on IC mechanical drawings.
  - Approach: split the task into pin count, pin centres and pin dimensions; train on synthetic drawings, then fine-tune on real ones.
  - Dataset: 8,608 labelled samples.
  - **[P-abs]** (via search summary) — [arXiv 2508.03725](https://arxiv.org/html/2508.03725v1); [ICML 2026 poster](https://icml.cc/virtual/2026/poster/65113)
- **ICLabagent**, a multi-agent LMM framework for IC footprint-geometry labelling, is cited by HWE-Bench. **[S]** — [OpenReview d6tTnuWmTb](https://openreview.net/forum?id=d6tTnuWmTb)

**PDF parsing tools (OmniDocBench v1.6, official leaderboard)** — all from the [OmniDocBench README](https://github.com/opendatalab/OmniDocBench), **[P-doc]**:

| Parser | Table TEDS | Notes |
|---|---|---|
| MinerU2.5-Pro (1.2B) | **93.42** | overall 95.75 |
| MinerU-2.5 | 87.88 | |
| Gemini 3 Pro | 89.15 | |
| Gemini 3 Flash | 89.29 | |
| dots.ocr | 87.18 | |
| olmOCR (7B) | 83.00 | |
| GPT-5.2 | 82.95 | |
| MinerU pipeline | 81.88 | |
| Mistral OCR | 76.78 | |
| **Marker** | **65.77** | |

- The current overall leaders are TeleOCR 96.91, OvisOCR2 96.47 and PaddleOCR-VL-1.6 96.34.
- Docling does not appear in the current table; an older snapshot showed it weak.
- **Benchmark caveat:** OmniDocBench covers 10 general document types, not datasheets specifically.

**Vendor layout content: numeric or not** (read directly)

- **TI regulator datasheets** (all 9 checked; Layout Guidelines sections read): TPS62933, LMR33630, TPS54202, TPS563200, TPS62130, LM5146-Q1, TPS61023, LMR51430, TPS7A20. **[P-full]** — e.g., [TPS62933](https://www.ti.com/lit/ds/symlink/tps62933.pdf), [TPS54202](https://www.ti.com/lit/ds/symlink/tps54202.pdf), [LM5146-Q1](https://www.ti.com/lit/ds/symlink/lm5146-q1.pdf), [TPS7A20](https://www.ti.com/lit/ds/symlink/tps7a20.pdf)
  - They use qualitative wording: "as close as possible", "loop area as small as possible", "sufficient vias".
  - Rare numbers or hard rules:
    - TPS62933: "A > 10-mil width trace" for the feedback divider, and a "separate VOUT trace to the upper feedback resistor".
    - TPS54202 / TPS563200: "Kelvin connection to the GND pin for the feedback path".
    - TPS7A20: do not place a thermal via directly under the DQN thermal pad.
- **Microchip MCU decoupling:** caps "as close to the pins as possible". If a cap sits on another layer through a via, keep "the trace length from the pin to the capacitor… within one-quarter inch (6 mm)". **[P-doc]** — [Microchip online docs, 2.2 Decoupling Capacitors](https://onlinedocs.microchip.com/oxy/GUID-469A9E6E-3954-4CBA-A0EA-20BD77D40B54-en-US-4/GUID-F15B709B-5112-4669-BAE9-9DBAC5DA209C.html)
- **Espressif ESP32-S3 hardware design guide** — many numeric rules. **[P-doc]** — [ESP32-S3 PCB Layout Design](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html)
  - Main 3.3 V power trace ≥ 25 mil; VDD3P3 traces ≥ 20 mil.
  - A 10 µF cap where power enters the chip.
  - Crystal "far from the clock pin… The gap should be at least 2.0 mm".
  - RF traces 50 Ω; 0201 matching parts placed in a zigzag; a 15 mil harmonic stub.
  - ≥ 15 mm antenna clearance in the housing.
  - SDIO lengths within ±50 mil of CLK, 50 Ω ±10%, total ≲ 2000 mil.
  - Touch traces ≤ 300 mm long and ≤ 0.18 mm wide.

### Inferences
- **Two extraction targets need two schemas:**
  1. **Electrical tables** (pinout, absolute max, recommended externals, θJA). These are well served by staged extraction with provenance (kicad-happy, the hardware KG, D2S-FLOW).
  2. **Layout guidance**: prose bullets plus one figure. This must be converted to typed predicates and keep qualitative strength levels ("as close as possible" → `weight=high, bound=null`). Never invent millimetres.

  For MCUs and SoCs, look in the **hardware design guide** first. That is where numeric bounds live, not the datasheet.
- **Reliability controls to implement**, each backed by a cited failure mode:
  - Page or sentence evidence on every value (GDP.pdf: skipped footnotes, superseding amendments).
  - **Tool-call audit**: refuse any extraction whose trace shows the PDF was never read ("Fidelity Is Not Enough").
  - Chunked multi-pass extraction (76.1% → 98.8%).
  - Deterministic computation of all derived numbers (2608.25217).
  - Multi-run consensus for safety-critical checks (DRCY).
  - PDF-hash plus revision pinning (kicad-happy).
- **Parser choice:** run MinerU2.5-Pro (or a VLM like Gemini 3 Flash) for tables, and keep pdftotext `-layout` as a cheap fallback for prose. Treat figures (recommended layouts) as **low-confidence topology hints** only, because LMM geometric perception is poor (LLM4-IC8K).

### Gaps
- Still **no paper or tool that extracts PCB *layout* guidelines** (placement and routing rules) from datasheets or app notes and measures accuracy.
- No datasheet-specific benchmark of PDF parsers. OmniDocBench is general-purpose.
- Not checked: ADI, ST and NXP app notes (analog.com and st.com unreachable); whether any vendor publishes machine-readable layout constraints.
- DRCY publishes no accuracy numbers.

---

## 4. Component knowledge bases and assembling a per-part "layout card"

### Takeaway
Distributor and part APIs give identity, package, datasheet URL and loosely typed parametrics:
- Nexar: `specs { attribute { name id shortname } displayValue }`;
- DigiKey v4: `Parameters[]`;
- LCSC: `attributes` as a JSON string.

Exchange standards (**JEDEC JEP30 PartModel**, supported by Flux, including AI generation from datasheets) and **application-level block models** (CELUS "CUBOs": description, specs, BOM with lifecycle, app-note-based schematic, typed ports, resources) come closest to a "part + its application circuit" card.

None of these sources carries layout constraints. Those must come from datasheet extraction and recipes (§3, §6).

### Cited Findings
- **Nexar / Octopart GraphQL:**
  - `supSearchMpn(q, filters: {case_package: ["SSOP"]}, limit)` returns `hits` and `results { part { mpn specs { attribute { name id shortname } displayValue } } }`.
  - "Not every component will have every attribute"; results can be filtered on attribute shortnames.
  - Each returned part counts against the organization's part limit; the default is 10 parts.
  - **[P-doc]** — [Nexar Playground query examples](https://support.nexar.com/support/solutions/articles/101000494582-nexar-playground-graphql-query-examples)
- **DigiKey Product Information API v4:**
  - `POST /products/v4/search/keyword` with `SearchOptions` (`HasDatasheet`, `Has3DModel`, `HasCadModel`) returns `DatasheetUrl` and `Parameters[] {ParameterText, ValueText}`.
  - `GET …/productdetails`, `/substitutions` and `/recommendedproducts` provide more; rate limits return HTTP 429.
  - **[P-full, secondary documentation]** — [kicad-happy digikey SKILL.md](https://github.com/aklofas/kicad-happy/blob/main/skills/digikey/SKILL.md). The official developer portal is a JavaScript app and was not readable.
- **LCSC / JLCPCB:**
  - The community `jlcsearch` API stopped returning the `extra` block (manufacturer, datasheet, attributes) in general search **as of 2026-09**.
  - LCSC's product-detail endpoint gives `productModel`, `brandNameEn`, `pdfUrl` and `encapStandard`.
  - **[P-full, secondary]** — [kicad-happy lcsc SKILL.md](https://github.com/aklofas/kicad-happy/blob/main/skills/lcsc/SKILL.md)
- **JEDEC JEP30 PartModel** — "guidelines established by JEDEC… to facilitate the exchange of part data between manufacturers and their customers".
  - Flux imports and exports JEP30 XML, and "can also generate JEP30 files from a datasheet using AI".
  - **[P-doc]** — [Flux: JEP30 PartModel Import/Export](https://docs.flux.ai/reference/jep30-partmodel-reference.md)
  - The JEDEC page itself did not render.
- **CELUS CUBO data model** (each is "the smallest reusable functional block… a complete implementation of a function, structured as a digital, application-ready datasheet"). **[P-doc]** — [CELUS: What is a CUBO](https://www.celus.io/knowledge/what-is-a-cubo); [Functionality structure](https://www.celus.io/knowledge/functionality-structure-for-cubos-their-specs)
  - Contents:
    1. description;
    2. structured specs;
    3. BOM with lifecycle status;
    4. schematic reflecting "decoupling capacitors, pull-up or pull-down resistors… based directly on manufacturer application notes";
    5. **ports** with "signal types, electrical constraints, and connection requirements";
    6. links to app notes and code.
  - Functions sit in a **four-level hierarchy**: L1 parent (e.g., "Power Supply") → L2–L4 children (e.g., "Step-Down Converter"). A functional block appears only if a matching CUBO exists.
  - Component data comes from Accuris. CELUS also offers an MCP server for Claude. **[S]** — [CELUS news](https://www.celus.io/news/define-design-develop)
- **SnapMagic (SnapEDA):**
  - Footprints follow IPC-7351B; symbols follow IEEE-315 plus internal standards.
  - 3D models use nominal dimensions without internal features.
  - An HTTP API exists, but no public field reference was found.
  - **[S]** — [SnapMagic standards](https://support.snapmagic.com/en/articles/2702511-what-standards-does-snapmagic-follow); [apis.io listing](https://apis.io/providers/snapmagic/)
- **Flux Knowledge Base** is persistent memory of preferences (preferred manufacturers, naming conventions, derating and testing protocols, "layout guidelines"). Each entry has a trigger and a scope (user or project), and is suggested automatically from chat ("We prefix signal nets with SIG_"). **[P-doc]** — [Flux Knowledge Base](https://docs.flux.ai/reference/knowledge-base.md)
- **kicad-happy `DatasheetFacts`**: a typed per-MPN cache with evidence, confidence trust gates and staleness checks. It already covers regulator, diode, transistor, op-amp, MCU and crystal categories. **[P-full]** — [datasheet-extraction.md](https://github.com/aklofas/kicad-happy/blob/main/datasheet-extraction.md)
- **PCBSchemaGen's schema-induced KG** holds per-IC pin roles plus constraint predicates; the KG files are in the repo (`kg.json`, `kg_component.json`). **[P-full]** — [PCBSchemaGen_v2](https://github.com/HZou9/PCBSchemaGen_v2)

### Inferences
- **The layout card should be a superset of a CUBO "ports" model plus the PCBSchemaGen pin-role KG.** Fields:
  - identity: MPN, footprint, PDF hash;
  - pin→role map;
  - IBIS-derived pin facts where available (§2);
  - required externals with roles;
  - typed layout predicates with evidence;
  - thermal and creepage data;
  - provenance per field.

  Keep it exportable to JEP30 for interchange where that makes sense.
- **Distributor APIs are best used for identity resolution and coarse parametrics**: package, current rating, f_sw. Expect schema churn, such as the jlcsearch change in 2026-09.
- **Copy Flux's "knowledge entry with trigger" pattern for team-specific recipe overrides**, e.g., "our bucks always get a 0402 HF cap on the same layer". These are user-scoped constraint templates that the recipe engine merges in.

### Gaps
- Not obtained: official DigiKey v4 field documentation (JavaScript portal); SnapMagic API fields; the JEP30 schema contents.
- No public, structured source of θJA or layout data across vendors was found.

---

## 5. Design-intent capture in KiCad schematics, and LLM-proposed annotations and clarifying questions

### Takeaway
KiCad 9/10 provide official, round-tripping carriers for every annotation an LLM front end needs:
- net classes via **patterns (wildcards and regex), directive labels, net-label fields and rule areas**, with multiple prioritized classes per net and *implicit* classes usable only in DRC;
- **component classes** via a `Component Class` symbol field or directive labels on rule areas;
- **placement rule areas** generated per hierarchical sheet or component class, plus Repeat Layout;
- design blocks (schematic in 9, PCB in 10);
- time-domain tuning profiles and a graphical rule editor (10).

Commercial precedents (Quilter, Flux) confirm the workflow: **detect automatically → present to the user for validation → treat everything else as generic**.

### Cited Findings
- **KiCad official net-class assignment** (all from the [KiCad 9 Schematic Editor manual](https://docs.kicad.org/9.0/en/eeschema/eeschema.html), **[P-doc]**):
  - **Directive labels** "behave like labels, except that they cannot be used to name a net". The attached net gets the directive's Net Class field.
  - "You can also type in a net class that isn't explicitly listed… Such implicit net classes can't be assigned any design settings… but they can still be used in DRC rule queries."
  - Several Net Class fields mean all listed classes are assigned. A directive on a bus applies to all of its members.
  - **Net labels** can carry a Net Class field.
  - **Rule areas**: "Any wire, bus, label, or symbol pin which crosses or is inside the rule area will be assigned the net class of a net class directive attached to the rule area border."
- **KiCad official component classes:**
  - "Named groupings of components: they are assigned to symbols… and also apply to the corresponding footprints". They are used for multichannel channels and "to group footprints in custom DRC rules".
  - Assignment: a symbol field named **`Component Class`**, or a directive label with a Component Class field on a rule area. Multiple classes are allowed.
  - **[P-doc]** — [KiCad 9 Schematic Editor manual](https://docs.kicad.org/9.0/en/eeschema/eeschema.html)
- **KiCad DRC functions** (KiCad 9): `A.hasNetclass('x')`, `A.hasComponentClass('X')`, `A.memberOfFootprint('${Class:X}')`, `A.ComponentClass == 'A,B'`. **[P-doc]** — [KiCad 9.0.0 release notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)
  - Caveat from users: `hasComponentClass` matches footprints only. **[S]** — [forum](https://forum.kicad.info/t/using-component-classes-for-custom-clearance-settings/57733)
- **KiCad placement rule areas:**
  - Tools → Multi-Channel → **Generate Placement Rule Areas** "can draw basic placement rule areas for any of the hierarchical sheets or component classes… even if it is not intended to represent a channel".
  - Each generated area is "the minimum size rectangle that encloses their constituent footprints". It can optionally be grouped with its footprints.
  - **Repeat Layout** copies a reference channel's placement and routing when the topologies match.
  - **[P-doc]** — [KiCad 9 PCB Editor manual](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html)
- **KiCad 10 additions:**
  - PCB design blocks ("libraries of board layouts");
  - time-domain tuning with Tuning Profiles (per-layer parameters);
  - a graphical DRC rule editor compatible with the custom-rule language;
  - variants, jumpers, schematic grouping, unconstrained pin/gate swap.
  - **[P-doc]** — [KiCad 10.0.0 release notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)
- **Quilter schematic guidance:**
  - "Use native object classes whenever possible… to help identify important signals such as power nets, differential pairs, and important net classes".
  - Supported CAD inputs: Altium, **KiCad**, Cadence Allegro, Siemens Xpedition.
  - It parses hierarchical schematics but has no symmetric multichannel layout.
  - **[P-doc]** — [Quilter: Design your schematic](https://docs.quilter.ai/using-quilter/design-your-schematic)
  - Quilter "tries to automatically detect as many constraints as possible… However, some constraints need to be manually defined". Undetected signals are treated as "generic, low-speed digital". **[P-doc]** — [Quilter: Define physics comprehensions](https://docs.quilter.ai/using-quilter/define-physics-comprehensions)
- **Flux**:
  - The Net Type property is inferred and editable (§2).
  - Copilot "understands your circuit's structure and connections", reads datasheets, and changes the schematic "with your approval".
  - The Knowledge Base suggests persistent rules from conversation.
  - **[P-doc]** — [Flux Copilot reference](https://docs.flux.ai/reference/copilot.md); [Knowledge Base](https://docs.flux.ai/reference/knowledge-base.md)
- **kicad-happy design-intent detection** emits a `design_intent` object (product class, IPC class, target market, `confidence`, `detection_signals`, per-field `source`). It **asks the user when confidence < 0.5**. **[P-full]** — [design-intent.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/references/design-intent.md)
- **copperhead**: "Nothing starts without a spec"; edit tools stay unavailable until a validated change proposal exists, and a constraints registry is kept. **[P-doc]** — [copperhead README](https://github.com/copperheadhq/copperhead)
- **atopile** keeps layouts across regeneration by matching hierarchical addresses (`atopile_address`, e.g., `usb_c.esd_protection.package`) and sub-PCB templates. **[P-full, secondary analysis]** — [kicad-tools atopile-layout-reuse.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/atopile-layout-reuse.md)

### Inferences
- **Mapping from front-end annotations to KiCad carriers:**
  - Net roles → net classes. Prefer **implicit classes** (DRC-queryable, no settings) for pure semantic tags like `ROLE_SW_NODE`. Use real classes for width, clearance and diff-pair gap.
  - Block membership → a `Component Class` field (e.g., `BLK_BUCK1`), plus per-role classes such as `ROLE_CIN_HF`.
  - Block placement regions → **generated placement rule areas per component class**. KiCad already sizes these from footprints and can group them, which gives the placer native region seeds.
  - Block-scoped rules → `.kicad_dru` using `memberOfFootprint('${Class:…}')` or courtyard conditions, because `hasComponentClass` only applies to footprints.
- **Validation UX should mirror Quilter's:**
  - each detected constraint is shown with its evidence and editable fields;
  - accept or reject is recorded;
  - undetected nets default to "generic low-speed", stated explicitly.

  Flux's "suggested knowledge" pattern can turn repeated user edits into reusable rules.
- **Generate clarifying questions only for high-impact, low-confidence fields.** Typical examples: interface speed (USB FS vs HS), max current on unnamed power nets (Quilter's 200/500 mA defaults show why), whether the ground strategy should be split or single. kicad-happy's 0.5-confidence threshold is a working precedent.

### Gaps
- Exact `.kicad_dru` syntax examples for component-class conditions in KiCad 10 were not re-verified.

---

## 6. Mapping recognized function → layout recipe (existing codifications and vendor numbers)

### Takeaway
Function-to-layout recipes exist in three forms:
1. **Physics-constraint engines with checks.** Quilter is the clearest. Bypass caps, crystals and switching converters are placement constraints, validated after layout by **Pin Distance** (an example acceptable range of 0–1 cm), Trace Path Length, Layer Switch Count and Ground Plane Overlap.
2. **Generators and modules**: JITX parametric circuits, atopile sub-PCB reuse, CELUS CUBOs (with a floorplan handover), KiCad 10 PCB design blocks, Flux modules, TI WEBENCH PCB Export.
3. **Prose rules** in app notes and agent skills.

**Vendor numeric thresholds are scarce for regulators.** TI datasheets give "as close as possible". TI app notes give a few numbers:
- traces ≥ 15 mil per ampere;
- 1 via per 200 mA (AN-1149) vs 1 via per ampere (SLYT614) — these **conflict**;
- a lateral hot loop of about 20 mm² (>1 nH) vs a vertical loop of about 2 mm² (SNVA803).

MCU guides are more numeric: Microchip ≤ 6 mm decap trace when going through a via; Espressif crystal ≥ 2.0 mm from the clock pin.

### Cited Findings

**Physics-constraint engine: Quilter.** **[P-doc]** — [Quilter: PRC overview](https://docs.quilter.ai/physics-rule-checks-prcs/overview); [Pin Distance](https://docs.quilter.ai/physics-rule-checks-prcs/pin-distance); [Switching Converters](https://docs.quilter.ai/physics-constraints/switching-converters); [Bypass Capacitors](https://docs.quilter.ai/physics-constraints/bypass-capacitors); [Crystal Oscillators](https://docs.quilter.ai/physics-constraints/crystal-oscillators)

- **Switching converter:** "ensures tight ground return loops for input and output paths"; "requires the three passive components to be positioned as closely as possible to the converter package".
- **Bypass:** "places capacitors with smaller capacitance values closer to power pins". One cap may bypass several pins on the same IC.
- **Crystal:** "position oscillators near their drivers".
- **Checks per constraint:**

  | Constraint | Physics Rule Checks |
  |---|---|
  | Bypass, crystal, switching converter | Pin Distance, Trace Path Length, Layer Switch Count, Ground Plane Overlap |
  | Differential pairs | Ground Plane Overlap, Uncoupled Spacing, Length Mismatch |
  | Power nets | Overheated Length |
  | Single-ended impedance | Invalid Width Span, Ground Plane Overlap |

- **Pin Distance** is the Euclidean distance between the closest edges of two pins. The documented example passes at "0.13cm within acceptable range (0cm to 1cm)" and fails at 1.11 cm.
- Quilter frames its whole approach as "constraints at the physics level, not the rules level", computing geometric rules per stack-up. **[P-doc]** — [How does Quilter work?](https://docs.quilter.ai/about-quilter/how-does-quilter-work)

**Generators and modules**

- **TI WEBENCH PCB Export** (June 2014):
  - Creates a power-supply PCB layout "using the sound layout principles provided by WEBENCH Power Designer", with footprints included.
  - Exports to **Altium Designer, Cadence Allegro, CadSoft EAGLE, Mentor Graphics PADS and DesignSpark PCB**.
  - **[P-doc]** — [TI press release (PRNewswire)](https://www.prnewswire.com/news-releases/create-a-power-supply-board-layout-in-minutes-with-tis-webench-pcb-export-262360801.html)
  - TI's current WEBENCH Circuit Designer page still lists "Export your design into your favorite CAD tool", without a format list. **[P-doc]** — [TI WEBENCH page](https://www.ti.com/design-resources/design-tools-simulation/webench-power-designer.html)
  - **No evidence of KiCad export was found.** **[S]**
- **Ultra Librarian / TDK** published a multi-power-module reference design in 8 CAD formats including KiCad, so vendor reference layouts can arrive as native files. **[S]** — [ElectronicsForU press release](https://www.electronicsforu.com/press-releases/multi-power-module-reference-design-in-8-different-cad-formats)
- **CELUS** generates schematics and BOMs from functional blocks. Its handover "involves generating a floorplan that simplifies the transition from schematic design to PCB layout". A third-party roundup lists CELUS as schematic and BOM, not layout. **[S]** — [CELUS news](https://www.celus.io/news/define-design-develop); [JLCPCB AI tools blog](https://jlcpcb.com/blog/ai-tools-for-pcb-design)
- **JITX**: a buck is defined by a constraints object, then a TI TPS6293x parametric circuit is instantiated. Placement and routing can be in code. **[S]** — [JITX power layout tutorial](https://docs.jitx.com/getting-started/quickstart-power-layout.html) (the page did not render in pass 2)
- **atopile**: package registry plus sub-PCB layout reuse matched by hierarchical address. **[P-doc / P-full secondary]** — [atopile README](https://github.com/atopile/atopile); [kicad-tools analysis](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/atopile-layout-reuse.md)
- **Flux** has "Modules… reusing layout sections". **[P-doc, index only]** — [Flux docs index (llms.txt)](https://docs.flux.ai/llms.txt)
  - Its layout rules include "Auto Layout Gravity", a 0–1 setting for how tightly parts are initially clustered. **[P-doc]** — [Flux Layout Rules List](https://docs.flux.ai/reference/layout-rules-types.md)

**Rule checkers: kicad-happy.** EMC rules include:
- SW-002/003: switch-node copper area, input-cap loop area;
- DC-001..003: decap distance (caps within 10 mm considered);
- ES-001: TVS distance to connector;
- ML-001: unshielded inductor within 15 mm of sensitive analog;
- skew limits: USB HS 25 ps, PCIe 5 ps, Ethernet 50 ps, HDMI 20 ps.

**[P-full]** — [emc-precompliance.md](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md); [methodology_pcb.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_pcb.md)

**Vendor numbers** (all **[P-full]**)

- **TI AN-1149 (SNVA021C):**
  - Run the feedback trace "as far from the inductor and noisy power traces as possible", "direct… somewhat thick", and possibly on the opposite side with a ground plane between.
  - Power traces "an absolute minimum of 15 mils (0.381mm) per Ampere".
  - "One standard via per 200 mA of current".
  - Grounds of the IC, Cin, Cout and the diode connect close together to the ground plane.
  - Switching current loops should "curl in the same direction".
  - Source: [TI SNVA021C](https://www.ti.com/lit/pdf/snva021c)
- **TI SLYT614** ("Five steps to a great PCB layout for a step-down converter"):
  - The input cap "should be the first component placed in the layout after the IC. Route the capacitor to the IC immediately".
  - Keep the SW node small.
  - "A good rule of thumb for the number of vias necessary is to use one via per amp of current".
  - Place vias outside the Cin–IC path.
  - Source: [TI SLYT614](https://www.ti.com/lit/pdf/slyt614)
- **TI SNVA803** (Hegarty, LM5146-Q1 power stage):
  - Laterally oriented switching loop: "almost 20 mm²", loop inductance ">1 nH".
  - Vertical loop with a layer-2 return path: "loop area of 2 mm²", with flux cancellation.
  - Source: [TI SNVA803](https://www.ti.com/lit/pdf/snva803)
- **TI datasheets:** see §3. They are qualitative apart from TPS62933's ">10-mil" FB trace and the Kelvin FB-ground rule on TPS54202/TPS563200.
- **MCU guides:** Microchip ≤ 6 mm (¼ in) pin-to-cap trace when the cap is through a via. Espressif: crystal ≥ 2.0 mm from the clock pin, power trace widths, 15 mm antenna clearance. See §3. [Microchip](https://onlinedocs.microchip.com/oxy/GUID-469A9E6E-3954-4CBA-A0EA-20BD77D40B54-en-US-4/GUID-F15B709B-5112-4669-BAE9-9DBAC5DA209C.html); [Espressif](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html)
- **Community rule:** "tight (< 15 mm² loop area)" for buck/boost loops (Cin → FET → L → Cout). This is a skill author's number, not a vendor's. **[P-doc]** — [IxTechCrypto kicad-rf-lowpower SKILL](https://github.com/IxTechCrypto/kicad-skills/blob/main/skills/kicad-rf-lowpower/SKILL.md)

### Inferences
**Draft recipe table.** "Hard" means compiled to DRC or PRC checks. "Soft" means a placer objective weight. Numbers are cited where available, otherwise left as `null` with a qualitative weight.

| Block (recognizer) | Critical roles | Hard constraints | Soft constraints / defaults |
|---|---|---|---|
| **Buck** (U with SW/FB(/BOOT) + L on SW: the Quilter and kicad-happy rule) | Cin_HF, IC VIN/PGND, L, Cout, Cboot, FB divider | Power trace width from current (≥ 15 mil/A floor, AN-1149; IPC-2152 better); vias by current (1 per 200 mA conservative vs 1 per A, a noted conflict); Kelvin FB ground where the datasheet says so | Cin_HF placed first, same layer, adjacent to VIN/PGND (weight max); loop area target ≲ 2–20 mm² depending on stack-up (SNVA803 range) with a vertical return over a solid layer-2 GND; SW copper minimal; FB divider at the FB pin with a separate VOUT sense trace, away from SW/L (opposite side over GND); Pin Distance check (example 0–1 cm, Quilter); sensitive parts ≥ 15 mm from unshielded L (kicad-happy ML-001) |
| **Boost** | Cout, switch/diode, PGND | as buck | Cout_HF is the critical loop cap |
| **LDO** | Cin, Cout | no thermal via directly under a DQN pad if the datasheet says so (TPS7A20) | Cin/Cout adjacent; thermal copper |
| **Decoupling** (cap between rail and GND sharing a net with an IC power pin; Quilter priority: wire, then voltage-named pin, then split) | cap ↔ pin | ≤ 6 mm trace if through a via (Microchip) | smallest cap closest (Quilter); ground via at the cap pad (Espressif) |
| **Crystal** (X/Y with both pins on the same IC: Quilter) | XIN/XOUT | none universal | crystal near the driver; no signals underneath; ground isolation or keep-out; ≥ 2.0 mm from the clock pin (Espressif, chip-specific); no magnetics nearby |
| **USB / diff pairs** (pin-role pair + KiCad suffix) | D± | Zdiff and skew from the protocol pack (other researcher); KiCad diff-pair net class | ESD at the connector |
| **RF** (antenna / RF pin + matching network) | 50 Ω line | 50 Ω (±10% invalid-width tolerance, Quilter) | matching parts at the pin; antenna keep-out; clearance (15 mm housing, Espressif) |
| **Power nets** (name or "Power" class: Quilter) | rail | width for max current, ΔT ≤ 20 °C (Quilter) | pour if the user requests it; defaults 200 mA (<3 V) / 500 mA (>3 V) need confirmation |

- **Recipes should be data.** Each has a recognizer pattern (pin roles plus refdes, as in Quilter's rules), a constraint set and a **check set**. Quilter's design of "every constraint has its own PRCs" is the model to copy: the same predicate drives the placer objective and the post-route acceptance test.
- **Where vendor numbers conflict** (via-per-current rules), use the conservative value and attach both citations, so the user sees the discrepancy.
- **Replaying a known-good sub-layout** (KiCad 10 PCB design blocks, atopile sub-PCBs, WEBENCH or vendor EVM exports) should be preferred when the block matches exactly. Generate from constraints otherwise.

### Gaps
- Not obtained: the current WEBENCH export format list, or whether KiCad is supported; CELUS floorplan details; ADI/ST/NXP layout app-note numbers (hosts unreachable).
- No published loop-area *targets* from vendors in mm² beyond SNVA803's worked examples.

---

## 7. Implications for an LLM-driven KiCad placer/router — proposed "design understanding" pipeline and data schema

### Takeaway
Build the front end as:
1. **deterministic extraction**;
2. **template/rule recognition** (pin-role-labelled VF2 motifs plus Quilter/kicad-happy-style heuristics);
3. **LLM work through tools** on a compact JSON graph: adjudication, detector-writing, and staged datasheet extraction with evidence;
4. **user validation** of detected constraints;
5. **compilation to KiCad-native intent** (net classes, component classes, placement rule areas, `.kicad_dru`) plus a placer objective file;
6. **constraint-specific post-layout checks**.

The evidence for this split:
- LLMs are strong on names, documents and code generation (HWE-Bench, PCB-QA, GENIE-ASI HL1/HL2, staged datasheet extraction at 98.8%);
- LLMs are weak on raw-text connectivity (NetlistBench), stage-level grouping (GENIE-ASI HL3: 0.31), geometry (LLM4-IC8K) and multi-step edits (NetlistBench: 80% → 26%).

### Cited Findings
- **Representation matters:** PCB-QA has JSON + tools at 0.88 vs native KiCad exports at 0.55 vs PDF at 0.43. **[P-full]** — [arXiv 2606.23704](https://arxiv.org/abs/2606.23704)
- **Code-writing beats direct reading** for subcircuit identification, but stage-level grouping stays poor (F1strict 0.31). **[P-full]** — [arXiv 2508.19393](https://arxiv.org/pdf/2508.19393)
- **Connectivity queries from raw netlists are model-dependent** (2–97%), and long edit chains collapse. **[P-full]** — [arXiv 2608.12197](https://arxiv.org/abs/2608.12197)
- **Production precedent for detect → validate → check:** Quilter's Circuit Comprehension plus PRCs. **[P-doc]** — [Quilter docs](https://docs.quilter.ai/using-quilter/define-physics-comprehensions)
- **Staged, provenance-preserving datasheet extraction** (98.8% vs 76.1%) and **tool-call auditing** against fabricated extractions. **[P-abs]** — [arXiv 2610.12762](https://arxiv.org/abs/2610.12762); [arXiv 2608.28439](https://arxiv.org/abs/2608.28439)
- **A deterministic verifier makes LLM output checkable:** PCBSchemaGen's 5-layer verifier (ERC, role, template, VF2 topology, power invariants). With it, Gemma-4-31B passes 81.3% of PCBBench tasks. **[P-full]** — [arXiv 2602.00510](https://arxiv.org/abs/2602.00510)
- **Topological validity ≠ simulates OK:** structural validation must be its own stage. **[P-abs]** — [arXiv 2609.26830](https://arxiv.org/abs/2609.26830)
- **KiCad-native carriers exist** for every annotation type, including generated placement rule areas per component class. **[P-doc]** — [KiCad 9 manuals](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html)

**Evaluation datasets available**

| Dataset | What it contains | License / access |
|---|---|---|
| BenchPCNP | 50 boards, 54 module labels | CC BY 4.0 |
| open-schematics | 87.9k schematic/PCB records, KiCad v5+ / legacy / Altium, kiutils JSON, no labels | CC-BY-4.0 overall; source licences vary |
| Ohmatic human-verified-v1 | 1,000 native KiCad/Eagle schematics, no labels | CC-BY-4.0 |
| PCBSchemaGen benchmarks | 227 tasks, 480 real ICs | MIT |
| PCB-QA | 480 QA over 8 KiCad projects | — |
| PCB-Bench | 174 OSHWHub boards with descriptions | — |
| HWE-Bench | 300 tasks, 2,914 datasheets | — |
| OmniLayout / OmniRouting | 1,681 schematic-coupled designs claimed | no licence; only 5 boards public as of 2026-08-15 (third-party recon) |

Sources:
- BenchPCNP **[P-full]** — [PMC13046837](https://pmc.ncbi.nlm.nih.gov/articles/PMC13046837/)
- open-schematics **[P-doc]** — [HF bshada/open-schematics](https://huggingface.co/datasets/bshada/open-schematics)
- Ohmatic **[P-doc]** — [HF Ohmatic/human-verified-schematics-v1](https://huggingface.co/datasets/Ohmatic/human-verified-schematics-v1)
- PCBSchemaGen benchmarks **[P-doc]** — [HF Hzou9/PCBSchemaGen-Benchmarks](https://huggingface.co/datasets/Hzou9/PCBSchemaGen-Benchmarks). Note: the difficulty split for the 165 Open-Schematics tasks differs between the HF card (67/63/35) and the GitHub README (40/48/77).
- PCB-QA **[P-full]** — [arXiv 2606.23704](https://arxiv.org/abs/2606.23704)
- PCB-Bench **[P-doc]** — [project page](https://digailab.github.io/PCB-Bench/)
- HWE-Bench **[P-full]** — [arXiv 2603.18102](https://arxiv.org/abs/2603.18102)
- OmniLayout/OmniRouting **[P-abs]** — [arXiv 2607.03261](https://arxiv.org/abs/2607.03261); [arXiv 2608.04434](https://arxiv.org/abs/2608.04434). Licence recon: kicad-tools issue #4830, **[S]**, as summarized in the [kicad-tools README](https://github.com/rjwalters/kicad-tools)

### Inferences

**Pipeline.** Each stage is labelled D = deterministic code, L = LLM, U = user.

1. **Ingest (D).**
   - Parse `.kicad_sch` / `.kicad_pro`; build the part–net–pin graph and expand hierarchy.
   - Capture existing intent: net classes and patterns, directive labels, `Component Class` fields, sheet names, power symbols.
   - Export a **compact hierarchical JSON** in the PCB-QA style, plus query tools: `neighbors`, `nets_of`, `path`, `pins_by_role`.
2. **Part resolution (D, with L for gaps).**
   - MPN → Nexar/DigiKey/LCSC → datasheet PDF (hashed) and, where available, an IBIS file.
   - When the MPN is missing, the LLM proposes candidates, marked `proposed`.
3. **Layout card (L staged; D validation).**
   - MinerU-class parse.
   - Chunked extraction of the pin-role map, externals, thermal data, and layout-guideline predicates, each with page and sentence evidence.
   - Every LLM tool call is logged, and the run is rejected if the source was not read.
   - Validators check units, pin existence against the KiCad symbol, and agreement between datasheet and symbol pin names.
   - Use the HW design guide for MCUs and SoCs.
4. **Net roles (D layered classifier, §2; L for leftovers with cited pins).**
   - Priority: explicit intent → IBIS/datasheet roles → topology → names → LLM.
5. **Blocks (D templates; L adjudication and detector-writing).**
   - VF2 motifs over pin-role-labelled edges, with PCBSchemaGen relaxations, plus Quilter/kicad-happy heuristics.
   - Uncovered parts: the LLM writes a detector (GENIE-ASI pattern). It is accepted only if unit tests pass and all of the block's pins are explained.
   - Never ask the LLM to form stage-level groupings directly (HL3 F1 0.31). Use sheet hierarchy and designer intent for those.
6. **Recipes → constraints + checks (D; L fills parameters from cards).**
   - Each constraint carries its own check (Quilter PRC model): pin distance, trace length, layer switches, ground overlap, loop area, overheated length.
7. **Validate (U).**
   - Quilter-style review screen. Undetected nets are explicitly "generic low-speed".
   - Ask questions only for high-impact, low-confidence fields.
8. **Compile (D).**
   - Real and implicit net classes; `Component Class` fields; generated **placement rule areas per block**; `.kicad_dru`; tuning profiles.
   - Soft objectives go to a placer JSON.
9. **Verify (D).**
   - DRC, constraint-specific checks, and structural LVS (topological validity as a separate stage, per 2609.26830).
   - Violations feed back to the placer and router.

**Schema additions to the pass-1 sketch:**
- each `constraints[]` item carries a `checks` list (e.g., `{"type": "pin_distance", "a": "C12.1", "b": "U3.VIN", "max_mm": 10, "source": "Quilter example range"}`);
- each `nets.*` entry carries `ibis` facts (`model_type`, `diff_pin`, `ramp_20_80_ps`) when available;
- each `parts.*.layout_card` has `extraction_audit` (tool-call trace hash, evidence pages, consensus count).

**LLMs are good at (use them for):**
- normalizing pin names to roles;
- interpreting designer naming and sheet names;
- staged datasheet table/prose extraction with evidence;
- turning qualitative guidelines into typed predicates;
- writing detector code;
- generating targeted questions and explanations.

**Needs deterministic code:**
- parsing and connectivity;
- every graph query;
- VF2 matching;
- numeric derivation (widths, impedance, Vout, loop area);
- IBIS parsing;
- unit normalization;
- KiCad file writing;
- all checks;
- staleness and audit logging;
- geometry (no LLM coordinates or millimetres without a cited source).

### Gaps
- No public dataset combines block labels, net roles **and** layout constraints on KiCad boards. Candidate path: mine net classes, component classes and DRU rules from open-schematics or kicad-happy-corpus projects, plus BenchPCNP-style relabelling. Whether enough designers use these features to make that worthwhile is unmeasured.
- Undisclosed by vendors: the internal accuracy of Quilter's or Flux's automatic detection, and how Cadence Allegro X AI / Siemens tools derive constraints from schematics (not found; search quota exhausted).
