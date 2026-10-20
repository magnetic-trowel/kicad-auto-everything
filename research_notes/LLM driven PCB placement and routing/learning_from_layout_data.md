# Learning PCB Placement and Routing from Data: Open-Source Layout Corpora, Layout Retrieval, Imitation and Synthetic Data, and Fine-Tuning LLMs for Layout

**Scope note for the report writer.** This file deliberately skips material already covered elsewhere and cross-references it instead:
- PCBWorld/PCBench, OmniLayout/OmniRouting, PCB-Bench, RL_PCB, tscircuit SRJ datasets, the netlist SFT set and KiCad design blocks/multichannel: see `constraints_verification_benchmarks.md` Q4–Q5.
- PCBAgent and ModuPlace headline results, ChiPFormer/MaskPlace/chipdiffusion: see `placement_algorithms.md` Q3.
- CAD-Coder, Lara RLVR floorplans and TileGPT/QD data synthesis: see `cross_domain_ideas.md`.

What is new here:
- a measured profile of the largest public KiCad repo list (5,856 entries), plus a license spot-check;
- new Hugging Face corpora;
- layout retrieval and migration (graph hashing, GNN matching, analog layout reuse, PCB-Migrator);
- imitation learning from human layouts (GeniusRoute, DevFormer, ChiPFormer data framing);
- GenLeaf (ICML 2026), whose BO-based "reverse-engineer expert layouts into programs" recipe is the most transferable new idea;
- Verilog RLVR/DPO recipes (CodeV-R1, VeriReason, VeriPrefer);
- solver distillation (FOARL);
- layout DPO (AesthetiQ, OptiScene);
- contamination and licensing evidence.

**Provenance tags.**
- **[P]**: read from the primary source in this session (paper PDF or abstract via the arXiv API, dataset card, repo file).
- **[S]**: search-engine snippet or summary only.
- **[M]**: my own measurement on downloaded data, with the method stated.
- **[preprint]**: arXiv-only or not yet peer-reviewed, as far as I could tell.

---

## Q1. Corpora: how much open PCB layout data exists (KiCad/Eagle/Altium, OSHWA, published ML datasets), under what licenses, and with what quality problems?

### Takeaway
The raw supply is large but messy:
- One public, pinned-commit KiCad repo list has **5,856 entries / 18,679 PCB files**.
- A Hugging Face scrape (`open-schematics`) has **87,931 schematic records (~317 GB)** with attached PCB files.
- OSHWA lists **3,452 certified projects**.
- Adafruit and SparkFun publish hundreds of Eagle boards, mostly under CC-BY-SA.

The usable supply for layout learning is much smaller:
- Boards are dominated by 2-layer hobby designs (keyboards are the largest named category).
- KiCad versions are mixed.
- In a random sample, about 40% of repos have no top-level license file. Copyleft licenses (GPL, CERN-OHL-S, CC-BY-SA) are common among those that do.
- No published ML dataset (beyond the already-covered PCBWorld/OmniLayout) yet pairs netlists with human placements *and* clean license metadata for training.

### Cited Findings

**Largest pinned KiCad repo list (kicad-happy-testharness).**
- The harness validates kicad-happy analyzers against "a corpus of 5,822 real-world open-source KiCad projects" organized as `owner/repo`. `repos.md` is the master list, and "All repos must have a pinned 40-char commit hash". `reference/repo_catalog.json` is a "searchable metadata catalog (KiCad versions, complexity, quality scores, design domains, tags)". Clones are shallow and git-ignored, around 290k directories. **[P]** — [kicad-happy-testharness README](https://github.com/aklofas/kicad-happy-testharness)
- kicad-happy reports the analyzed corpus as:
  - 5,800+ repos, 6,845 schematic files, **3,498 PCB files**, 1,050 Gerber directories;
  - 312,956 components and 531,418 nets;
  - KiCad 5 through 10, 2- to 6-layer;
  - hobby boards through "production hardware".
  **[P]** — [kicad-happy README](https://github.com/aklofas/kicad-happy)
- **[M] Profile of `repo_catalog.json`** (downloaded 2026-10-20, 12.5 MB, **5,856 entries**). Note the mismatch with the README's 5,822.
  - **5,707 repos have at least one PCB file**, with **18,679 PCB files** in total. This is far more than the 3,498 "analyzed". The count probably includes backups and old revisions; I did not verify.
  - **KiCad generation:** "mixed" 3,824, kicad7 713, kicad6 630, kicad5 619, kicad9 29, kicad10 21, kicad8 6, unknown 14.
  - **Max copper layers (PCB repos):** 0 layers 621 (likely empty or unparsed), 1 layer 229, **2 layers 3,619 (63%)**, 3 layers 50, **4 layers 1,028**, 5 layers 26, 6 layers 100, 8 layers 22, 10 or more layers 10.
  - **Components per repo:** p10 11, p25 24, **median 65**, p75 201, p90 488, p99 2,284. Nets: median 102, p90 708. 2,374 repos have 100 or more components; 1,030 have 300 or more.
  - **Board area (mm²):** median 3,833, p75 9,600, p90 20,459. Median SMD ratio is 0.72.
  - **Categories:**
    - Miscellaneous 1,810, **Keyboards 449**, Synthesizers/audio 324, Motor/robotics 315, LED/display 304;
    - ESP32 294, Arduino recreations 294, Networking/radio/SDR 254, Sensor/IoT 250, Retro computing 235;
    - USB/interface 214, Power/battery 207, RP2040 192, STM32 179, ADC/DAC 110, RISC-V/FPGA 90;
    - CubeSat/aerospace 39, SBCs/carrier boards 33.
  - **Subcircuit detectors that fired:** decoupling detected in **3,848 repos**, power regulators in 2,979, crystal circuits in 1,852, USB-bus validation in 809, opamp circuits in 741, memory interfaces in 435, motor drivers in 274, battery chargers in 273.
  - **Quality and other tags:** catalog "documentation" quality median **0**, "completeness" median 70; `has_gerbers` on 2,213 repos. The catalog's "routing" quality score is 100 for 4,575 of 5,707 PCB repos. I did not find documented semantics for this score.

  Source: [repo_catalog.json](https://github.com/aklofas/kicad-happy-testharness/blob/main/reference/repo_catalog.json)
- **[M] License spot-check.** Method: 55 repos sampled at random (seed 42) from catalog entries with PCB files. For each, I fetched `LICENSE`, `LICENSE.md`, `LICENSE.txt`, `COPYING` or `LICENCE` at the **pinned commit** via raw.githubusercontent.com and classified the text by keyword. 54 results were usable.
  - **No top-level license file: 22 (41%).** Some may declare a license in the README or a subfolder.
  - **Permissive: 20 (37%)**: MIT 11, Apache-2.0 4, BSD 3, Unlicense 1, CC0 1.
  - **Reciprocal/copyleft: 12 (22%)**: GPL-3 3, CERN-OHL-S 3, CC-BY-SA 3, LGPL 2, TAPR-OHL 1.
  - This is a small, heuristic sample with a ±13 pp 95% CI on the 41% figure. The GitHub REST license API was blocked from this environment. Sources: [kicad-happy-testharness](https://github.com/aklofas/kicad-happy-testharness); raw.githubusercontent.com fetches.

**Hugging Face corpora (new since the other notes).**
- **`bshada/open-schematics`:** **87,931 rows**, 316.8 GB parquet (dataset-server size API), license tag CC-BY-4.0, 11,966 downloads and 199 likes, last modified 2026-06-30.
  - Card self-description: "The largest dataset of electronic schematics and PCB layouts on the internet… a self-growing, autonomous dataset that continuously scans the web".
  - Each record: raw schematic (`.kicad_sch`, legacy `.sch`, or Altium `.SchDoc`), `pcb_files` (raw `.kicad_pcb`/`.pcb` from the same project), rendered images, kiutils JSON/YAML, `name` (= `owner/repo`).
  - Filters: PCBs over 10 MB dropped; projects with more than 20 PCB files keep the 20 with the largest render.
  - Card-stated limitations: JSON only for `.kicad_sch` (about 85% of rows), **PCB images missing for about 55% of PCB entries**, and "Quality and complexity of designs vary significantly".
  - License caveat: "Please ensure you comply with the original licenses of the source projects". The card gives no per-row license field.
  - **[P]** — [dataset card](https://huggingface.co/datasets/bshada/open-schematics); [size API](https://datasets-server.huggingface.co/size?dataset=bshada/open-schematics). At least 12 re-uploads named `*/open-schematics` exist on the Hub. — **[P]** [HF dataset search API](https://huggingface.co/api/datasets?search=schematic)
- **`electron-rare/kicad9plus-{permissive,copyleft}`** (mirrored as `Ailiance-fr/...`, May 2026): KiCad 9+ *schematic* corpora.
  - **Permissive:** 98 samples (Apache-2.0 74, MIT 20, CC0 3, CERN-OHL-P 1).
  - **Copyleft:** 209 samples (GPL-3.0 169, CERN-OHL-S-2.0 36, EUPL-1.2 4).
  - **Pipeline:** discovery via `gh search code "(kicad_sch (version 202X)" extension:kicad_sch`, an SPDX license whitelist, per-file sidecar metadata (`source_url`, `commit_sha`, `license_spdx`, `kicad_version`), SHA-256 dedup, truncation at 8 KB, and validation with `kicad-cli sch erc` (99.6% pass).
  - **License history:** the original combined set was split "after legal audit revealed CC-BY-SA-4.0 incompatibility with GPL-3 / CERN-OHL-S inputs". The copyleft subset was relicensed GPL-3.0-or-later, with a claim that trained models "must comply with GPL-3.0-or-later obligations". This is the dataset author's legal interpretation, not settled law.
  - Cards follow the EU AI Act training-data template (July 2025).
  - **[P]** — [kicad9plus-permissive](https://huggingface.co/datasets/electron-rare/kicad9plus-permissive); [kicad9plus-copyleft](https://huggingface.co/datasets/electron-rare/kicad9plus-copyleft); [scripts](https://github.com/ailiance/ailiance-bench)
- **`Ohmatic/human-verified-schematics-v1`** (compiled 2026-08-15, CC-BY-4.0): **1,000** native KiCad (legacy and S-expression) and Eagle XML schematics "with high confidence of human review and real-world use". They come in trust tiers: 685 "grandfathered" plus 315 "verified" with at least 2 independent evidence families. **[P]** — [dataset card](https://huggingface.co/datasets/Ohmatic/human-verified-schematics-v1). A trust-tier model of this kind is directly reusable for PCB layout curation.
- **`Ailiance-fr/mascarade-kicad-dataset`** (CC-BY-SA-4.0): 2,645 KiCad Q&A pairs, of which **79.7% are synthetic LLM-generated**. An attribution audit found the original heuristic estimate of Stack Exchange content ("~30%") was "over-counted by ~5.6×". The actual SE share is 5.52%. **[P]** — [dataset card](https://huggingface.co/datasets/Ailiance-fr/mascarade-kicad-dataset)
- **`Warren-wzw/PCB-Layout`:** 668 manually aligned pairs of PCB *photographs* and layout images, for cross-modal registration. It is not useful for placement learning. **[P]** — [dataset card](https://huggingface.co/datasets/Warren-wzw/PCB-Layout); [arXiv 2610.03167](https://arxiv.org/abs/2610.03167) [preprint]
- Hub searches for "pcb", "pcb layout", "gerber", "routing" and "placement" surfaced mostly defect-detection image sets. Apart from the above, I found no netlist-plus-placement dataset. **[P]** — [HF search API](https://huggingface.co/api/datasets?search=pcb)

**Other corpus sources.**
- **OSHWA:** the homepage counter read "**3452** Certified Open Source Hardware Projects" on 2026-10-20 **[P]** — [oshwa.org](https://oshwa.org/). Earlier counts were over 2,972 (Feb 2025) and over 3,107 (Jul 2025, with 43 added that month) **[S]** — [Hackster Feb 2025](https://www.hackster.io/news/february-2025-open-source-hardware-certification-roundup-2a5302419b7d); [Hackster Jul 2025](https://www.hackster.io/news/july-2025-open-source-hardware-certification-roundup-dcf069506dee). Certification covers all hardware types (mechanical, textiles and so on), not only PCBs.
- **GitHub topic `kicad`:** 4,559 public repositories tagged **[S]** (date of snapshot unknown) — [github.com/topics/kicad](https://github.com/topics/kicad). Topic tags heavily undercount: most KiCad repos are untagged. GitHub code search for `extension:kicad_pcb` was not accessible from this environment.
- **Open-hardware repository mining:** of 242 OSH products, 105 used GitHub for hardware data. A related paper notes that "only a third of products provided enough publicly accessible supporting documentation". **[S]** — [Design Science, "How participative is open source hardware?"](https://www.cambridge.org/core/journals/design-science/article/how-participative-is-open-source-hardware-insights-from-online-repository-mining/D1341B4E550B8F42032585694B6DB8D8)
- **Adafruit:** "provides the design files for all Adafruit designed printed circuit boards… as Eagle CAD files and hosted on GitHub". An example repo is under CC-BY-SA. **[S]** — [Adafruit Learn guide](https://learn.adafruit.com/accessing-and-using-adafruit-pcb-design-files)
- **SparkFun:** product hardware repos state CC BY-SA 4.0 (for example RedBot Line Sensor), and the Eagle libraries are CC BY-SA 4.0. **[S]** — [RedBot_Line_Sensor](https://github.com/sparkfun/RedBot_Line_Sensor); [SparkFun-Eagle-Libraries](https://github.com/sparkfun/SparkFun-Eagle-Libraries). These are professionally designed, fabricated and sold boards, a higher-quality stratum than average GitHub hobby boards. Both are Eagle, which needs KiCad's Eagle importer.
- **`dataset-srj24`:** a further tscircuit-format set of "production-oriented" boards converted to Simple Route JSON. The repo title says "Ten production-oriented KiCad boards". A search summary says 26 KiCad and Altium boards. **Conflict unresolved.** **[S]** — [techmannih/dataset-srj24](https://github.com/techmannih/dataset-srj24)
- **OmniSch:** 1,854 real-world schematic *diagrams*, 109.9K grounded instances and 423.4K labels, for schematic-to-netlist-graph reasoning. This is useful upstream (netlist extraction from PDFs), not for layout. **[P]** — [arXiv 2604.00270](https://arxiv.org/abs/2604.00270) [preprint]
- The 2026 GenAI-for-PCB survey names "domain-specific data scarcity and limited support for integration with existing PCB tools" as key challenges. **[P]** — [arXiv 2606.17074](https://arxiv.org/abs/2606.17074) [preprint]

### Inferences
- **Order-of-magnitude supply:** about 5–20k distinct real KiCad boards with routing are reachable from GitHub. Sources are the kicad-happy list, the `name` field of open-schematics as a discovery index, and gh code search. Add a few hundred professional Eagle boards (Adafruit/SparkFun) and about 3.4k OSHWA entries, partially overlapping.
- After deduplication (keyboard and Arduino-clone families, forks), license filtering and quality filtering, I would expect **low thousands** of training-grade boards and **a few hundred** 4+-layer boards. That is enough for retrieval, statistical priors and LLM SFT on *constraint* outputs (ModuPlace used 426 constraint graphs). It is not enough for end-to-end learned placers from scratch.
- The distribution skew is large: 63% 2-layer, median 65 parts, keyboards and synths over-represented. Any learned prior must be **conditioned** on board class, layer count and part type, or it will encode hobbyist habits.
- open-schematics is the easiest bulk source but has no per-row license. Treat it as a **discovery index** (owner/repo), then re-fetch at pinned commits with your own license detection, rather than as a training set.

### Gaps
- No authoritative count of `.kicad_pcb` files on GitHub or GitLab. Code search was blocked here; a one-off `gh search code extension:kicad_pcb` count with a date stamp is needed.
- No count found for OSHWHub (JLC) public projects, Kitspace, Hackaday.io or CERN OHR.
- License distribution measured only on n=54 and not via SPDX tooling (for example scancode). README-declared licenses were not parsed.
- The semantics of kicad-happy catalog "routing" and "quality" scores were not verified, nor how many PCBs are fully routed and DRC-clean against their own rules. PCBWorld notes that format conversion itself can trigger DRC violations (see `constraints_verification_benchmarks.md`).
- I found no published Altium layout dataset for ML.

---

## Q2. Layout retrieval and pattern mining: graph similarity over subcircuits, frequent-motif mining, and VLSI/analog layout reuse and migration analogues

### Takeaway
No published PCB layout-retrieval system was found. All the building blocks exist, though:
- **WL hashing plus motif vectors** for fast structural retrieval (used in NEMESIS for OTAs);
- **GNN region prediction** for subcircuit matching in large netlists;
- **GCN-based hierarchical annotation** of analog netlists (GANA/ALIGN), which also emits symmetry and matching constraints;
- **gSpan-style mining** for frequent subcircuits (CellE).

Analog IC design has a 15-year literature on **template- and knowledge-based layout reuse and migration** (IPRAIL, Wu et al. TCAD'15, Lin et al. ICCAD'20, ISPD'18 regularity extraction, commercial ML migration). PCB has one direct analogue: **PCB-Migrator (DATE'26)**, which encodes expert layouts as offset constraint graphs and migrates them to changed boards. The consistent lesson is that retrieval should return **relational constraints (offsets, symmetry, ordering)**, not raw coordinates.

### Cited Findings

**Structural retrieval over netlists.**
- **NEMESIS** (OTA design, 65 nm) retrieves equations "from the prior invocations of NEMESIS to structurally similar OTAs" before falling back to LLM derivation **[P]** — [arXiv 2607.05657](https://arxiv.org/abs/2607.05657) [preprint]. Per a search summary of the PDF:
  - the netlist is a bipartite net/device graph;
  - the structural signature is a motif vector plus a **2-iteration Weisfeiler-Lehman hash**;
  - similarity = weighted sum of WL-hash Jaccard (weight 0.6) and motif cosine.
  **[S]** — [NEMESIS PDF](https://arxiv.org/pdf/2607.05657)
- **GNN region prediction for subcircuit matching:**
  - Rule-based matching "cannot generalize to arbitrary target circuits", and node-to-node matching is inefficient.
  - The method trains a GNN with constructed negative samples to predict high-probability regions.
  - It extracts subgraph embeddings directly from the whole-circuit embedding, rather than running a GNN per candidate.
  - It "significantly outperforms existing methods in time efficiency and target region prediction".
  **[P]** — [arXiv 2507.19518](https://arxiv.org/abs/2507.19518) [preprint]
- **Classical baselines:**
  - SubGemini, subgraph isomorphism extending Gemini, reports near-linear runtime in device count for CMOS **[S]** — [SubGemini paper](https://lamarr.ece.uw.edu/research/ssrl/download/FROSTY/design/data/subgemini.pdf).
  - NetworkX ships WL graph hashing, where isomorphic graphs get identical hashes (exact, not partial, similarity) **[S]** — [NetworkX graph hashing](https://networkx.org/documentation/latest/reference/algorithms/graph_hashing.html).
  - A Technion thesis proposes self-supervised subgraph localization with graph-similarity kernels **[S]** — [Technion event page](https://www.cs.technion.ac.il/events/view-event.php?evid=10634).
- **GANA** (DATE 2020; Kunal, Sapatnekar et al.):
  - A trained GCN labels netlist elements for upper-level blocks, while lower-level structures are identified by graph algorithms.
  - The motivation is that traditional graph methods "cannot easily identify the large number of structural variants".
  - It also detects symmetry and matching constraints.
  - It feeds the ALIGN flow; per ALIGN, the GCN training set is 1,390 OTA circuits.
  **[S]** — [IEEE Xplore](https://ieeexplore.ieee.org/document/9116329); [ALIGN arXiv 2008.10682](https://arxiv.org/pdf/2008.10682). The data repo reads SPICE OTA netlists into adjacency, feature and label matrices for the GNN. **[P]** — [GANA_circuit_data](https://github.com/kkunal1408/GANA_circuit_data)
- A 2023 GCN analog-circuit classification study reports large accuracy gains from augmentation. Feature-matrix augmentation took accuracy from 48.2% to 76.6%; dataset augmentation by flipping took it from 72% to 92%. **[S]** — [Sensors 2023 via Crossref](https://api.crossref.org/works/10.3390%2FS23062989)

**Frequent-motif mining.**
- **CellE** (2026) applies equality saturation to post-mapping netlists. It clusters functionally equivalent implementations in an e-graph and then runs "an efficient pattern mining algorithm" to pick new standard cells, giving 15.41% average area reduction (up to 23.64%) and 8.00% delay reduction. **[P]** — [arXiv 2603.12797](https://arxiv.org/abs/2603.12797) [preprint]. A search summary says it adapts gSpan because e-graphs contain cycles. **[S]**
- gSpan mines frequent connected subgraphs via canonical minimum DFS codes without candidate generation **[S]** — [gSpan](https://sites.cs.ucsb.edu/~xyan/papers/gSpan-short.pdf). SPMiner is a neural alternative for larger motifs. **[S]** (same search)
- A patent describes representing a netlist as a graph, finding isomorphic fragments and substituting matched fragments with higher-level functional blocks. **[S]** — [US 8701058](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8701058)

**Analog/VLSI layout reuse, retargeting and migration (closest analogue to "reuse how others laid out a buck").**
- **IPRAIL** (U. Washington): extracts a structural template from an already-tuned analog layout and imposes new device sizes and new process rules. It was demonstrated retargeting two op-amps from TSMC 0.25 µm to 0.18 µm. **[S]** — [IPRAIL paper](https://lamarr.ece.uw.edu/research/ssrl/workspace/iprail/web_IPRAIL/JOURNAL_ELSEVIER.pdf)
- **Xu, Basaran, Su, Pan (ISPD 2018):** extracts **regularity constraints (symmetry, matching)** from an existing analog placement so that migration preserves them, with a 7.6% average placement-area reduction. **[S]** — [NSF PAR](https://par.nsf.gov/servlets/purl/10121012)
- **Wu, Lin, Chen, Yeh, Li, Ho (IEEE TCAD 34(2), 2015), "knowledge-based analog physical synthesis":**
  - analyzes legacy circuits, layouts and constraints;
  - **finds matching sub-circuits between legacy and new designs**;
  - generates multiple candidate layouts that reuse legacy layout "as much as possible", with a high reuse rate that preserves designer preferences.
  It criticizes earlier flows that assumed identical netlist topology or template. **[S]** — [TCAD 2015 PDF](https://users.ece.cmu.edu/~xinli/papers/2015_TCAD_pd.pdf); [NYCU record](https://ir.lib.nycu.edu.tw/handle/11536/124196)
- **Lin et al. (ICCAD 2020, invited), "Achieving Analog Layout Integrity through Learning and Migration":** "different companies and designers follow different guidelines and preferences", and migration is preferred over starting from scratch when a similar design exists. Keywords: circuit classification and identification, layout templates, ML, migration. **[S]** — [NYCU scholar](https://scholar.nycu.edu.tw/en/publications/achieving-analog-layout-integrity-through-learning-and-migration-/)
- **Commercial:** Synopsys showed ML-based analog migration of a 14 nm bandgap to 5 nm, "resembles the original" while meeting 5 nm rules (vendor claim). **[S]** — [Synopsys blog](https://www.synopsys.com/blogs/chip-design/ai-analog-design-migration-samsung-safe-forum-2023.html). Patents exist for a "knowledge-based analog layout generator" using a design repository and pattern matching. **[S]** — [US 9256706](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9256706)
- **PCB-Migrator: Automated PCB PnR Migration** (Han, Li, Fu, Ye, Lu, Liu, Yu, Ho, Chen; CUHK / CUHK-SZ / Index Tech; DATE 2026, Verona, Apr 20–22).
  - Motivation: "when design requirements change, such as adjustments to board dimensions or the addition of new obstacles, experts must often recreate similar layouts from scratch".
  - Method: uses an **offset constraint graph to capture positional relationships among components** of the expert layout, so that migration "gives the tool foresight in the early stage".
  **[S]** for content (DATE PDF snippet); **[P]** for the bibliographic entry — [yhhan.com publications](https://yhhan.com/publications); [Tinghuan Chen CV](https://mypage.cuhk.edu.cn/academics/chentinghuan/CV/TinghuanCV.pdf). The proceedings PDF URL found by search ([DATE archive](https://past.date-conference.com/proceedings-archive/2026/DATA/21.pdf)) returned a 404 page when fetched.
- **GenLeaf's layout embedding** (see Q5) is a supervised, performance-aware layout representation: a GraphSAGE model over a placement graph whose cell/net vertices carry size, pin-coordinate, rotation, net-degree and span features, fused with a multi-layer routing image. On a layout-quality prediction task it reduced MSE by 34.0% and 35.9% versus Circuit GNN and DeepLayout. It doubles as a **layout similarity metric** for both data preparation and the GRPO reward. **[P]** — [GenLeaf PDF](https://yhhan.com/PDFs/GenLeaf_paper.pdf)

### Inferences
- **Two-stage PCB subcircuit retrieval** is directly buildable:
  1. Label the netlist graph: component nodes carry footprint and package class, MPN family and pin function (VIN/SW/FB/GND/VBUS/CC/D±); net nodes carry net class.
  2. Key the anchor IC by `(MPN family | pin-function multiset)` and take a k-hop neighbourhood (k=2 catches CIN/COUT/L/FB divider/boot cap).
  3. Coarse filter by WL hash at 1–2 iterations (NEMESIS-style), plus a motif histogram (number of caps per pin function, inductor present, and so on).
  4. Rank by graph-kernel or GNN embedding similarity.
  5. Return the human fragment as a **relative offset/rotation constraint graph anchored on IC pins** (PCB-Migrator/ModuPlace style), never as absolute XY.
- "How others laid out a TPS62xxx buck" is a query for the matched human fragments' **distribution** of (CIN-to-VIN-pad distance, inductor orientation relative to the SW pin, FB divider side, via count in the GND return). The retrieval layer should return the top-k fragments and their summary statistics. The LLM picks or adapts, and the solver legalizes.
- The analog lesson (Wu 2015; Lin 2020) is that exact-topology templates fail when netlists differ slightly. Approximate matching (GCN/WL) plus partial reuse is needed. GANA's split (learned recognition for variable high-level blocks, exact graph rules for low-level primitives) maps onto PCB as rule-based detectors for standard motifs (decoupling, dividers, crystals: kicad-happy already has more than 40) with learned embeddings for "the rest".
- **Frequent-subgraph mining over the corpus** (gSpan on labelled netlist neighbourhoods, then joined with the geometry of each occurrence) would produce a *motif library with empirical layout statistics*. That is a data product nobody has published.

### Gaps
- PCB-Migrator's full method, benchmarks and numbers were not retrievable (DATE PDF unavailable). Whether it learns from multiple prior boards or migrates one, and how routing is migrated, is unknown.
- No study measures how often the same IC's support circuitry is laid out "the same way" across open boards (layout variance per motif).
- No PCB-specific graph-kernel or GNN retrieval benchmark exists. NEMESIS's 0.6/0.4 weighting comes from an OTA context and is snippet-only.

---

## Q3. Imitation learning / behavior cloning from human layouts: what has been tried for placement, routing order/topology and relative offsets, and how well did it work?

### Takeaway
Pure imitation of human layouts has a mixed record:
- **GeniusRoute** (analog routing guidance learned from manual layouts via VAE) reached "competitive" quality with manual layouts. Successors criticize it for data scarcity, manual labelling and performance-blind, biased guidance.
- **ChiPFormer** shows offline (decision-transformer) learning from *placement data* transfers and fine-tunes 10× faster, but the data are optimizer outputs, not human layouts.
- **DevFormer** shows that **strong inductive biases** (relative positions, permutation symmetry) make offline learning work for **decap placement with limited data**.
- For PCB, no paper does behavior cloning from human boards. PCBAgent uses online fine-tuning only. Lim 2026 hard-codes "passives near their IC pins / voltage source" priors into the reward.
- No imitation-learned net ordering was found; net-ordering learning is RL.

The evidence favours learning **relational priors** (offsets, orderings, constraint graphs) from human data and leaving geometry to optimizers.

### Cited Findings
- **GeniusRoute** (Zhu, Liu, Pan et al., ICCAD 2019) "leverages machine learning to provide routing guidance, mimicking the sophisticated manual layout approaches". It uses VAEs to extract latent layout strategies from human expertise and trains a generative model to guide routing. It reports results "competitive… to manual layouts" and generalization across circuit functions. **[S]** — [NSF PAR](https://par.nsf.gov/servlets/purl/10192510); [AI-for-EDA survey](https://arxiv.org/pdf/2204.09579)
- **Critique by PARoute/AnalogFold** (Xu, Chen, Zhu, Chen, Ho, Yu; DAC 2024, "Performance-driven Analog Routing via Heterogeneous 3DGNN and Potential Relaxation"):
  - "Machine learning methods summarize the experience from existing routing solutions, but suffering from scarcity of manual data."
  - "The training process relies on manual labeling data and limits the model's capability. Moreover, the existing methods do not explicitly consider performance optimization and lead to biased routing guidance."
  - Its alternative generates guidance optimized for post-layout performance.
  **[P]** — [PARoute PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C223-DAC2024-PARoute.pdf). Its slides add that GeniusRoute struggles with designs of different sizes or aspect ratios. **[S]** — [slides](https://www.cse.cuhk.edu.hk/~byu/papers/C223-DAC2024-PARoute-slides.pdf)
- **ChiPFormer** (ICML 2023) "cast[s] the chip placement as an offline RL formulation… learning a transferable placement policy from fixed offline data". It exploits offline placements in a multi-task setting, fine-tunes on unseen circuits ("from hours to minutes"), and on 32 circuits gives better quality with a 10× runtime reduction. **[P]** — [arXiv 2306.14744](https://arxiv.org/abs/2306.14744). Later work found EfficientPlace beats it on HPWL (see `placement_algorithms.md`).
- **DevFormer** (KAIST, ICML 2023) targets hardware design optimization limited by "the scarcity of offline data". It introduces "strong inductive biases such as relative positional embeddings and action-permutation symmetricity… enabl[ing] efficient design optimization with limited offline data". It is applied to **decoupling-capacitor placement**, beating prior methods "in both simulated and real hardware… while reducing the number of components by more than 30%". **[P]** — [arXiv 2205.13225](https://arxiv.org/abs/2205.13225). It is the closest published "learn decap placement from offline data" result, though it targets PDN impedance on a grid, not human-layout imitation.
- **Lim et al. 2026, "Component Centric Placement Using Deep RL"** [preprint]:
  - fixes the main component at the centre and places passives "in proximity to the pins of the main component";
  - discretizes free space around it;
  - "leverage[s] prior knowledge that each passive's position has to be near to its corresponding voltage source" in the reward.
  It compares DQN, Actor-Critic and SA on "over nine real-world PCBs", with the best "approach[ing] near human-like placements". **[P]** — [arXiv 2602.23540](https://arxiv.org/abs/2602.23540). The prior is hand-coded, not learned.
- **Net ordering:**
  - An IJCAI 2025 transformer-RL framework learns net-order policies for detailed routing "rather than relying on expert-written heuristics", reporting fewer DRVs. **[S]** — [IJCAI 2025](https://www.ijcai.org/proceedings/2025/1055)
  - DATE 2021 notes net orders "are mostly determined by simple heuristic rules tuned for specific benchmarks". **[S]** — [DATE 2021](https://past.date-conference.com/proceedings-archive/2021/pdf/1334.pdf)
  - A 2022 survey covers attention-based REINFORCE ordering followed by a pattern router. **[S]** — [arXiv 2202.13564](https://arxiv.org/pdf/2202.13564)
  - I found no work cloning net order from human boards. Human routing order is not recorded in final layout files.
- A Cadence-assigned PCB-design patent describes using "one or more completed designs as examples for a design agent to imitate" (no detail on ordering). **[S]** — [US 12223248](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12223248)
- **DeepPCB** (InstaDeep) blog, April 2026: training "happens in simulation… sometimes synthetic boards generated programmatically, sometimes real designs from a training corpus". After "millions of routing attempts across thousands of board configurations" the agent develops strategies that transfer. Learned preferences include escape direction, dog-bone vs via-in-pad, and "how to sequence net routing to avoid blocking later connections". **[P]** — [DeepPCB blog](https://deeppcb.ai/reinforcement-learning-pcb-routing-explained/). ModuPlace attributes DeepPCB's relatively good results to "extensive historical designs to train the reward model". **[P]** — [ModuPlace PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
- PCBAgent's decision transformer is ChiPFormer-style but trained **online only** (see `placement_algorithms.md`). No PCB paper pre-trains on human placements.

### Inferences
- **What can be imitated from final layouts:**
  - (a) Relative pose of each passive to its anchor-IC pin: distance, angle, side, rotation. These are the "decap offset distributions per package".
  - (b) Module partition and module adjacency: which functional blocks sit together and near which board edge.
  - (c) Per-net-class routing style: width, layer, via count, whether a plane is used, diff-pair spacing.
  - (d) Placement *ordering* only weakly, since history is absent. Git history of the layout file could partially recover ordering and is an untried idea.
- **What cannot be imitated:** routing order and rip-up history (not stored), and the designer's rationale.
- Use the corpus for **relational statistics plus a conditional model** (DevFormer-style relative-position transformer) that predicts offsets and rotations of satellites given the anchor IC footprint and pin functions. Evaluate it against the hand-coded rule "nearest edge of nearest power pin, < X mm".
- The GeniusRoute → PARoute history warns that **imitation targets must be paired with physics or performance checks**. Otherwise the model copies hobbyist mistakes (for example a decap at 8 mm with a long via chain) as faithfully as good practice. Filter training fragments by quality (fabricated boards, professional sources, DRC-clean) and/or reweight by an independent physics score (loop area, inductance proxy).

### Gaps
- No published distribution of decap-to-pin distances, buck-loop areas or similar per package from real boards was found. This is a data product to build.
- I found no PCB behavior-cloning paper and no PCB result where a human-imitation prior was A/B-tested against rules.
- DeepPCB's training corpus, size and licensing are undisclosed.

---

## Q4. Synthetic data generation and self-improvement loops for layout learning (procedural boards, round-trip synthesis, solver-generated labels)

### Takeaway
Every successful recent EDA fine-tuning pipeline manufactures its supervision rather than relying on raw human data:
- **CodeV-R1** round-trips open Verilog through NL and back, then filters with equivalence checking.
- **GenLeaf** uses **Bayesian optimization to reverse-engineer expert layouts into generator scripts** ("expert layouts exist but no corresponding scripts").
- **FOARL** distils solver outputs into an LLM and then uses RL to fix constraint violations.
- **OptiScene** builds 17K scenes by "GPT synthesize, Human inspect" and constructs hard negatives by injecting violations.
- **PCBWorld** (covered elsewhere) shows procedurally generated boards transfer zero-shot to real boards for routing RL.

For PCB, the most valuable synthetic data is likely to be **(human board → extracted constraint graph → solver re-placement → verified equivalence)** round-trips, plus **perturb-and-repair** episodes generated from human boards.

### Cited Findings
- **CodeV-R1 / QiMeng-CodeV-R1** (NeurIPS 2025): a rule-based testbench generator for equivalence checking against golden references, plus a **round-trip data synthesis** that pairs open-source Verilog with LLM-generated NL descriptions. It "verifies code-NL-code consistency via the generated testbench, and filters out inequivalent examples". Training is "distill-then-RL" (adaptive DAPO). **[P]** — [arXiv 2505.24183](https://arxiv.org/abs/2505.24183). The first stage starts from about 150K NL–code samples. **[S]** — [NeurIPS page](https://neurips.cc/virtual/2025/poster/116244)
- **GenLeaf** (Han et al., ICML 2026):
  - "Since there have been many expert-designed leaf cell layouts but no corresponding scripts, they cannot be used directly to train the LLM… we propose a Bayesian Optimization (BO) based dataset preparation method to align layouts and scripts".
  - BO searches script parameters so that the produced layout matches the expert layout's metrics (tracks, wirelength, vias) and embedding similarity.
  - The result is "BO-Generated Golden Scripts" for SFT, followed by GRPO.
  **[P]** — [GenLeaf PDF](https://yhhan.com/PDFs/GenLeaf_paper.pdf)
- **"LLMs as End-to-end Combinatorial Optimization Solvers"** (NeurIPS 2025):
  - SFT "imparts LLMs with solution generation patterns from domain-specific solvers".
  - A feasibility-and-optimality-aware RL (FOARL) stage "explicitly mitigates constraint violations".
  - A 7B LoRA model reaches a 1.03–8.20% average optimality gap on seven NP-hard problems, "surpassing… GPT-4o… DeepSeek-R1, and domain-specific heuristics".
  **[P]** — [arXiv 2509.16865](https://arxiv.org/abs/2509.16865). SFT alone produced "over-greedy behavior… where LLMs violate constraints in pursuit of improved objectives". **[S]** — [NeurIPS poster page](https://neurips.cc/virtual/2025/poster/115835)
- **OptiScene** (NeurIPS 2025): the **3D-SynthPlace** dataset has "nearly 17,000 scenes" from a "'GPT synthesize, Human inspect' pipeline". Training is SFT (first generate high-level spatial descriptions, then concrete placements), followed by **multi-turn DPO** to "align the generated layouts with human design preferences". **[P]** — [arXiv 2506.07570](https://arxiv.org/abs/2506.07570). Stage-2 hard negatives inject out-of-boundary and overlap violations into good layouts. **[S]** (search summary of the same paper)
- **GeoSVG-RL** (2026): a "supervised warm-start phase on synthetic data", then GRPO against a browser-rendered verifier with six reward dimensions: rendering validity, canvas fitting, anchor placement, text containment, graph consistency and code cleanliness. It yields large gains in "arrow-anchor accuracy and text-in-box rates". **[P]** — [arXiv 2605.25447](https://arxiv.org/abs/2605.25447) [preprint]. This is a close structural analogue to "LLM emits layout code, a geometric verifier scores it".
- **DeepPCB:** trains on "synthetic boards generated programmatically" and real designs, and warns that "if the simulation allows routing patterns that would fail DRC in your actual EDA tool, the agent will happily learn those patterns". It also notes that "novel" strategies may be reward loopholes. **[P]** — [DeepPCB blog](https://deeppcb.ai/reinforcement-learning-pcb-routing-explained/)
- **Mascarade** shows the downside of unlabeled synthetic data. 79.7% of a KiCad QA set is LLM-generated, and a heuristic estimate of human-sourced content was off by 5.6×. **[P]** — [dataset card](https://huggingface.co/datasets/Ailiance-fr/mascarade-kicad-dataset)
- **Simulator-Refined Diffusion** (2026) for RF PCB inverse design generates layouts conditioned on target S-parameters. It combines a differentiable surrogate (gradient direction) with a non-differentiable full-wave simulator (search) during sampling, getting up to 21.2% closer to targets in-distribution and 19.8% out-of-distribution. **[P]** — [arXiv 2609.38363](https://arxiv.org/abs/2609.38363) [preprint]. This is a pattern for physics-in-the-loop generation where training data comes from simulation.
- Already covered elsewhere: PCBWorld D1/D2 generators and synthetic-to-real transfer; chipdiffusion's synthetic netlists; and TileGPT/QD in `cross_domain_ideas.md`.

### Inferences
- **Highest-value synthetic tasks for a KiCad LLM:**
  - (a) **Round-trip constraint extraction.** Take a human board, extract a constraint graph (relative offsets, alignment, edge and side, grouping), re-solve with the project's placer, and keep only pairs where the re-solved layout matches the human one within tolerance on HPWL, routed completion and embedding similarity. This is the PCB analogue of CodeV-R1's equivalence filter and GenLeaf's BO alignment, and it produces verified (netlist → constraints) SFT pairs.
  - (b) **Perturb-and-repair.** Displace or rotate k parts of a human board, or rip up a net group. The target is the human configuration. This gives unlimited supervised "fix this placement" examples with ground truth.
  - (c) **Procedural constraint tasks** (decap within X mm, diff-pair symmetry, keep-outs) on PCBWorld-style generated boards, for unit-testing reward functions.
  - (d) **Solver distillation.** Run CP-SAT/analytical placement with good settings on many corpus netlists and SFT the LLM on the *constraint and priority choices*, not raw coordinates. Then add FOARL-style RL to penalize infeasibility.
- **Self-improvement loop:** sample N candidate constraint graphs, solve, verify (DRC + router + metrics), keep the best as new SFT data or as DPO pairs, and iterate. This is expert iteration and has the same structure as ModuPlace's GRPO grouping and GenLeaf's 20-sample groups.

### Gaps
- No PCB paper implements round-trip constraint extraction or perturb-and-repair data generation. These are proposals.
- I did not verify tscircuit's or RL_PCB's procedural generators beyond what other notes cover.

---

## Q5. Fine-tuning LLMs for EDA layout: SFT recipes, RL with verifiable rewards (GRPO/DAPO), preference learning, reward design, solver distillation

### Takeaway
There is now a consistent recipe, validated on Verilog, leaf-cell layout and PCB constraint graphs:
1. **SFT on verified pairs**, usually synthesized and filtered.
2. **Group-based RL (GRPO/DAPO)** with **executable verifiers** (testbench, DRC, metric computation), optionally augmented by a **learned pairwise ranker trained on expert preferences** where "quality" is not fully computable.

Reported scale: 7–14B open models (Qwen2.5-7B, Qwen3-14B) beat GPT-4o and Claude-class zero-shot on narrow EDA tasks:
- **ModuPlace:** 426 SFT graphs; 36 samples per input in groups of 4.
- **GenLeaf:** Qwen3-14B; 20 scripts per input in groups of 5; beats expert golden layouts on track count.
- **CodeV-R1-7B:** 68.6% VerilogEval v2.
- **VeriReason:** 83.1% VerilogEval-Machine.

DPO with verifier- or judge-derived pairs is a cheaper alternative (VeriPrefer, AesthetiQ, OptiScene).

### Cited Findings

**PCB / layout-specific fine-tuning.**
- **ModuPlace** (DAC'26) details beyond those in `placement_algorithms.md`:
  - "We utilize **426 CCGs corresponding to expert-level placements** as training data" for SFT on **Qwen-2.5 (7B)**.
  - "In the GRPO stage, the LLM agent generates **36 CCGs for each input**, and each group for GRPO consists of **4 CCGs**."
  - "Manual scoring of placements may lead to instability, including inconsistent standards and difficulty in quantification", so in-group rankings come from "a **graph neural network, trained on ranking data from human expert feedback**. Its inputs are two distinct CCGs, and the output is the ranking". The advantage combines "actual physical metrics and the ranking".
  - Benchmarks come from OpenROAD and industrial boards. Hardware: 4×A100-80GB.
  **[P]** — [ModuPlace PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
- **GenLeaf** ("Expert-level Leaf Cell Layout Generation via Preference-Optimized LLM", ICML 2026):
  - **Setup:** base model **Qwen3 (14B)** for SFT and GRPO. The LLM writes PnR *scripts* calling custom APIs, not coordinates. Cadence Virtuoso runs DRC/LVS. "Our script-based generation ensures construction-correctness for most rules, and a lightweight post-processing step" handles the rest.
  - **GRPO:** 20 scripts per input, groups of 5. The advantage is "based on both the actual physical metrics [track count t, wirelength w, via count v] and the similarity to the golden layouts" via the learned embedding.
  - **Results** on 14 industrial cases, versus expert "Golden Design": average ratios of **0.52× tracks, 0.96× wirelength, 1.01× vias**, described as "48% fewer tracks… 4% reduction in wirelength with only a 1% increase in via count".
  - **Baselines:** Qwen2.5-7B, Qwen3-14B, Qwen3-Coder-30B, DeepSeek-R1-14B, GPT-4o and Claude Sonnet 4.
  **[P]** — [GenLeaf PDF](https://yhhan.com/PDFs/GenLeaf_paper.pdf); [publications list](https://yhhan.com/publications)
- **ACDC** fine-tunes T5, GPT-2, Mistral-7B and GPT-oss-20B for analog placement. It reports "sensitivity to data format, instability in generated designs, and limited generalization to unseen circuit configurations". **[P]** — [arXiv 2512.09199](https://arxiv.org/abs/2512.09199) [preprint]
- **LLANA** uses LLM few-shot ability to make Bayesian optimization of analog layout constraints more sample-efficient, with performance "comparable to SOTA BO methods". **[P]** — [arXiv 2406.05250](https://arxiv.org/abs/2406.05250)
- **PANDA** (2026): LLM-enhanced intent → topology → sizing → "constraint-driven layout generation", with turnaround "from days or weeks to hours". **[P]** abstract only — [arXiv 2606.15052](https://arxiv.org/abs/2606.15052) [preprint]

**RL with verifiable rewards in HDL (closest mature analogue).**
- **CodeV-R1-7B:** 68.6% / 72.9% pass@1 on VerilogEval v2 / RTLLM v1.1, "surpassing prior state-of-the-art by 12~20%, while even exceeding… 671B DeepSeek-R1 on RTLLM". The three stated challenges are "lack of automated and accurate verification environments, the scarcity of high-quality NL-code pairs, and the prohibitive computation cost of RLVR". Adaptive DAPO adjusts the sampling rate to cut cost. Model, code and data were released. **[P]** — [arXiv 2505.24183](https://arxiv.org/abs/2505.24183)
- **VeriReason** (GLSVLSI 2026): SFT + GRPO. The reward "combines testbench evaluations with structural heuristics" plus self-checking. It reaches **83.1%** on VerilogEval-Machine and "up to a 2.8X increase in first-attempt functional correctness", "outperforming… GPT-4 Turbo". **[P]** — [arXiv 2505.11849](https://arxiv.org/abs/2505.11849); [code](https://github.com/NellyW8/VeriReason)
- **VeriPrefer** ("Insights from Verification"): an automatic testbench pipeline using VCS feedback. **DPO** preference pairs come from testbench outcomes, and the method outperforms baselines on VerilogEval and RTLLM variants. **[P]** — [arXiv 2504.15804](https://arxiv.org/abs/2504.15804) [preprint]

**Preference learning for layouts (non-EDA).**
- **AesthetiQ** (CVPR 2025): DPO over graphic layouts using an MLLM's aesthetic preferences, with "a data filtering protocol utilizing our layout-quality heuristics". The metric is an MLLM-judged win rate versus ground truth. It reports +17% / +16% on Crello / WebUI across 1B–8B models. **[P]** — [arXiv 2503.00591](https://arxiv.org/abs/2503.00591)
- **OptiScene:** SFT followed by multi-turn DPO (see Q4). **[P]** — [arXiv 2506.07570](https://arxiv.org/abs/2506.07570)

**Solver distillation.**
- FOARL (see Q4): SFT on solver outputs, then RL for feasibility and optimality; a 7B LoRA beats domain heuristics on seven CO problems. **[P]** — [arXiv 2509.16865](https://arxiv.org/abs/2509.16865)

### Inferences
- **Reward design for a KiCad placer/router LLM**, using a verifier stack the project will already have (see `constraints_verification_benchmarks.md`):
  - **Hard gates (r = 0 or a large negative if failed):** parse and apply success, no courtyard overlap, inside the outline, and `kicad-cli pcb drc` error count for placement-only checks.
  - **Dense terms:** HPWL ratio vs human, net crossings (ModuPlace), routed completion with Freerouting or KRT within a time budget, via count, decap-pin distance compliance, and loop-area proxies.
  - **Learned term:** a pairwise GNN ranker trained on a few hundred expert A/B judgments (ModuPlace) and/or embedding similarity to the human reference (GenLeaf).
  - **Group size:** GRPO groups of 4–5 out of 20–36 samples per input are the published operating points.
- **What the LLM should output:** published wins come from LLMs emitting **programs or constraint graphs** (GenLeaf scripts, ModuPlace CCGs, CodeV Verilog) that deterministic engines realize. They do not come from raw coordinates (ACDC reports instability). For KiCad this means a constraint IR or a placement DSL, not `(at x y)` S-expressions.
- **Order of investment:** (1) SFT on round-trip-verified constraint graphs from the corpus; (2) GRPO with executable rewards; (3) only then preference data, because expert ranking is the scarcest resource.
- **Distillation target:** the LLM learns to predict constraint sets for which the solver yields good layouts ("solver-quality constraints"). Labels are cheap to generate by searching over constraint parameters with BO (GenLeaf) on corpus boards.

### Gaps
- No public weights or data for ModuPlace's CCG model, its 426 CCGs or its expert ranking set. ModuPlace and GenLeaf data are industrial.
- No study of GRPO on *routing* LLM outputs for PCBs. PCBWorld's GRPO baseline is a small transformer policy, not an LLM (see other notes).
- No measurement of how many expert preference pairs are needed for a usable ranker. ModuPlace does not state the size of its ranking dataset in the text I extracted.

---

## Q6. Evaluation of learned priors vs hand-coded rules: what evidence exists for PCB (and close analogues)?

### Takeaway
No head-to-head study "learned prior vs hand-written rules, same solver, real PCBs" exists. The indirect evidence points to a **hybrid**:
- Learned components help most when they produce **constraints or guidance** for an optimizer (ModuPlace: removing SFT +35.1% wirelength, removing GRPO +25.4%; GenLeaf beats expert layouts on tracks).
- Hand-coded priors remain competitive or necessary for feasibility. Lim 2026 builds priors into the reward. On PCBWorld, Freerouting still has the best clean-pass rate on real boards. GANA uses rules for low-level primitives.
- Pure imitation (GeniusRoute) is criticized as data-starved and performance-blind.
- DeepPCB itself says learned policies "learn behaviors, not rules" and cannot respect unencoded constraints.

### Cited Findings
- **ModuPlace ablations and zero-shot comparison** (fine-tuned 7B versus GPT-4o/Claude-3.5): see `placement_algorithms.md`. The new detail here is that the reward ranker is learned from expert rankings because "manual scoring… may lead to instability". **[P]** — [ModuPlace PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
- **GenLeaf** exceeds human golden layouts on track count (0.52×) at roughly equal wirelength and vias. A learned generator plus metric-driven RL beats expert data, which suggests imitation is a floor rather than a ceiling when a verifier exists. **[P]** — [GenLeaf PDF](https://yhhan.com/PDFs/GenLeaf_paper.pdf)
- **PARoute/AnalogFold** argues human-imitation guidance is "biased" and does not "guarantee performance improvement"; it replaces imitation with performance-driven guidance. **[P]** — [PARoute PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C223-DAC2024-PARoute.pdf)
- **DevFormer** reaches better decap solutions with >30% fewer components than prior methods. Hand-designed **inductive biases**, not more data, made offline learning work. **[P]** — [arXiv 2205.13225](https://arxiv.org/abs/2205.13225)
- **Lim 2026** builds domain priors into the RL reward and search space, and SA is among the compared methods. The abstract does not say which method won outright. **[P]** — [arXiv 2602.23540](https://arxiv.org/abs/2602.23540)
- **DeepPCB on limitations:**
  - "If you haven't explicitly specified a constraint, the model won't respect it."
  - "The model's confidence doesn't correlate reliably with correctness."
  - "The training distribution defines the boundaries of competence."
  **[P]** — [DeepPCB blog](https://deeppcb.ai/reinforcement-learning-pcb-routing-explained/)
- **GANA:** learned GCN recognition for variable high-level blocks, exact graph rules for constrained low-level primitives. **[S]** — [IEEE Xplore](https://ieeexplore.ieee.org/document/9116329)
- **ACDC:** fine-tuned LLMs placing analog devices directly show "instability" and "limited generalization to unseen circuit configurations". **[P]** — [arXiv 2512.09199](https://arxiv.org/abs/2512.09199)
- On PCBWorld, rule-based routers (Freerouting) remain strongest on real boards; synthetic-trained RL only "approached" them (see `constraints_verification_benchmarks.md` Q4).

### Inferences
- **Design for measurability.** Implement every prior twice: as a hand-coded rule (for example "decap ≤ 2 mm from pin, same side, via to GND within 0.5 mm") and as a learned or corpus-derived distribution. Feed both into the same solver as soft constraints and compare on held-out human boards and on physics proxies. This produces the missing evidence.
- Learned priors should win where rules are under-specified or context-dependent: module adjacency, connector-edge assignment, orientation conventions, aesthetic alignment. Rules should win on safety-critical, well-understood physics: clearances, creepage, decap proximity, loop area. Use rules as hard constraints and learned priors as soft objectives or tie-breakers.

### Gaps
- No PCB-specific A/B evidence exists, and no human blind-ranking study compares learned and rule-based placements on open boards.
- DeepPCB, Quilter and Cadence learned-prior claims remain vendor-reported.

---

## Q7. Risks: dataset contamination, license compliance (GPL / CC-BY-SA / CERN-OHL), and bias toward hobbyist practice

### Takeaway
- **Contamination is demonstrated for hardware-code benchmarks** (VeriContaminated) and is near-certain for popular open boards, which sit in GitHub crawls. Evaluation needs time-split or private boards.
- **Licensing is unresolved but actively policed by practitioners:**
  - About 40% of sampled KiCad repos lack a top-level license file.
  - Copyleft hardware licenses (GPL, CERN-OHL-S, CC-BY-SA) are common.
  - One HF dataset already split and relicensed after a legal audit.
  - CERN-OHL v2 explicitly covers PCB layouts, but no source addresses ML training.
  - Code-LLM practice (The Stack) shows permissive-only data plus opt-out is viable.
- **Hobbyist bias is structural:** 63% of boards are 2-layer, keyboards are the largest named category, and median documentation quality is 0. Learned priors must be filtered and conditioned.

### Cited Findings

**Contamination.**
- **VeriContaminated** (NYU) applies CCD and Min-K% Prob to VerilogEval and RTLLM across CodeGen2.5, LLaMA 1–3.1, GPT-2/3.5/4o, DeepSeek-Coder, CodeQwen 1.5, RTLCoder and VeriGen. "Our study confirms that data contamination is a critical concern." **[P]** — [arXiv 2503.13572](https://arxiv.org/abs/2503.13572). A 2026 survey characterizes the result as near-100% contamination of VerilogEval for most commercial models. This is unverified against the original. **[S]** — [arXiv 2605.10807](https://arxiv.org/pdf/2605.10807)
- **LiveVerilogEval** (DATE 2026) proposes a contamination-free, automatically scalable benchmark. **[S]** — [DATE 2026 PDF](https://past.date-conference.com/proceedings-archive/2026/DATA/167.pdf)

**Licensing.**
- **The Stack** (BigCode): 3.1 TB of permissively licensed code. "Near-deduplicating the data significantly boosts performance", and "it is possible to match previously reported HumanEval and MBPP performance using only permissively licensed data". It provides "Am I in The Stack" and a removal process. **[P]** — [arXiv 2211.15533](https://arxiv.org/abs/2211.15533)
- **CERN-OHL v2** comes in S (strongly reciprocal), W (weakly reciprocal) and P (permissive) variants and is OSI-approved. Covered material includes schematics, **"circuit or PCB layouts"** and mechanical drawings. **[S]** — [AB Open](https://abopen.com/news/cern-launches-open-hardware-licence-2-0-in-reciprocal-and-permissive-variants/); [OSH Park blog](https://blog.oshpark.com/2021/01/29/cern-open-hardware-license-approved-by-osi/). No source found on whether model training is a "use" or "modification" under CERN-OHL.
- **KiCad 9+ corpus legal split** (see Q1): CC-BY-SA-4.0 is "one-way compatible *to* GPLv3 only, never the reverse". The copyleft subset was relicensed GPL-3.0-or-later, with the claim that trained models carry GPL obligations. **[P]** — [kicad9plus-copyleft](https://huggingface.co/datasets/electron-rare/kicad9plus-copyleft)
- **open-schematics** is CC-BY-4.0 at the dataset level over mixed-license sources, while telling users to "comply with the original licenses". This is a license-laundering risk if used directly. **[P]** — [dataset card](https://huggingface.co/datasets/bshada/open-schematics). OmniLayout has no data license (see `constraints_verification_benchmarks.md`).
- **[M] License sample:** 41% no top-level license file, 37% permissive, 22% reciprocal (n=54; see Q1).
- **Copyrightability of PCB layouts:**
  - Taiwan's IPO treats a circuit *concept* as unprotectable, but once drawn as a PCB layout it is a protectable graphical work. **[S]** — [Lee and Li newsletter](https://www.leeandli.com/EN/Newsletters/3149.htm)
  - Singapore litigated PCB layout/artwork infringement in *Real Electronics v Nimrod*; the outcome was not retrieved. **[S]** — [vLex](https://sg.vlex.com/vid/real-electronics-industries-singapore-842804218)
  - A Polish law review treats PCB copyright as "multi-aspect". **[S]** — [Acta Iuris Stetinensis](https://wnus.usz.edu.pl/ais/en/issue/592/article/9103/)
  - The US mask-work regime (SCPA 1984) covers chips, not boards. **[S]** — same search
- **Attribution audits:** heuristic source detection overestimated Stack Exchange content by 5.6×. Provenance must be verified per sample, not inferred from style. **[P]** — [mascarade card](https://huggingface.co/datasets/Ailiance-fr/mascarade-kicad-dataset)

**Hobbyist bias and quality.**
- **[M]** kicad-happy catalog:
  - 2-layer boards are 3,619 of 5,707 PCB repos (63%), and median part count is 65.
  - Keyboards (449), synths (324), Arduino recreations (294) and ESP32 (294) dominate the named categories.
  - Median "documentation" score is 0.
  - Only 1,188 repos have a 4+-layer board, and only 39 CubeSat/aerospace and 33 SBC repos exist.
  Source: [repo_catalog.json](https://github.com/aklofas/kicad-happy-testharness/blob/main/reference/repo_catalog.json)
- open-schematics' own card warns "Quality and complexity of designs vary significantly". **[P]** — [card](https://huggingface.co/datasets/bshada/open-schematics). Only about a third of OSH products have adequate documentation. **[S]** — [Design Science](https://www.cambridge.org/core/journals/design-science/article/how-participative-is-open-source-hardware-insights-from-online-repository-mining/D1341B4E550B8F42032585694B6DB8D8)
- GeniusRoute's imitation learning was criticized for "biased routing guidance". **[P]** — [PARoute PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C223-DAC2024-PARoute.pdf)

### Inferences
- **License tiers for a project:**
  - **Tier A** (MIT, Apache, BSD, CC0, CERN-OHL-P, CC-BY): train and redistribute derived data with attribution.
  - **Tier B** (GPL, CERN-OHL-S/W, CC-BY-SA, TAPR): use for evaluation and retrieval-at-inference (showing the user a fragment with attribution and license). Exclude from released weights unless counsel approves.
  - **Tier C** (no license, NC, ND): evaluation-only, never redistributed. Fetch at pinned SHA into a git-ignored cache (the kicad-tools/PCBWorld practice already noted in other files).
  - Keep an opt-out list, as in The Stack.
- **Retrieval sidesteps much of the training-license risk.** Showing a CC-BY-SA buck layout to a user with attribution is ordinary reuse under that license. Baking it into weights is the contested case. This favours a **retrieval-heavy, train-light** architecture early on.
- **Contamination control:**
  - Hold out boards first committed after the base model's training cutoff.
  - Hold out private boards contributed by testers.
  - Hold out whole near-duplicate clusters (forks, kit families) by WL-hash or footprint-set similarity, so a fork does not leak across splits.
  - Report results on "popular" and "obscure" splits separately.
- **Bias control:** condition priors on (layer count, board class, part package, voltage/current class). Upweight professional sources (Adafruit, SparkFun, Antmicro, OSHWA-certified, boards with Gerbers or release tags). Never train "what is good" solely on corpus frequency; pair it with physics proxies.

### Gaps
- No legal analysis was found of ML training on CERN-OHL/GPL/CC-BY-SA *hardware* designs, or of whether weights are derivative works. This needs counsel.
- No contamination study exists for PCB layout benchmarks (PCBWorld, PCB-Bench). I also did not test whether frontier LLMs can regurgitate specific open `.kicad_pcb` files.
- No quantitative study compares hobbyist vs professional layout practice, for example decap distances or ground-return quality.

---

## Q8. Implications for an LLM-driven KiCad placer/router: a concrete data strategy (what to scrape, how to clean and label, what to train first, how to evaluate)

### Takeaway
Build a **license-tiered, pinned-commit corpus of a few thousand KiCad boards**. Mine it first for **retrieval and statistical priors**; no training is required for this step. Then generate **verified (netlist → constraint graph) pairs by round-trip re-solving**, and fine-tune a 7–14B open model with SFT followed by GRPO against executable DRC and router rewards. This is the ModuPlace/GenLeaf/CodeV-R1 recipe. Add a small expert-preference ranker last. Evaluate on time-split, de-duplicated, private held-out boards against both human references and a rules-only baseline.

### Cited Findings (evidence underpinning the plan)
- **Seed lists exist with pinned commits:**
  - kicad-happy-testharness: 5,822–5,856 repos, with per-repo layer count, complexity and detected subcircuits. **[P]** — [README](https://github.com/aklofas/kicad-happy-testharness); [catalog](https://github.com/aklofas/kicad-happy-testharness/blob/main/reference/repo_catalog.json)
  - open-schematics: 87,931 rows with `owner/repo`. **[P]** — [card](https://huggingface.co/datasets/bshada/open-schematics)
  - Code search by S-expression version header is already used by others. **[P]** — [kicad9plus card](https://huggingface.co/datasets/electron-rare/kicad9plus-permissive)
- **Published recipes and scales:**
  - ModuPlace: SFT on 426 graphs, GRPO 36 samples in groups of 4, GNN ranker from expert rankings. **[P]** — [ModuPlace](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
  - GenLeaf: BO reverse-engineering of expert layouts into scripts, Qwen3-14B, groups of 5 out of 20. **[P]** — [GenLeaf](https://yhhan.com/PDFs/GenLeaf_paper.pdf)
  - CodeV-R1: round-trip synthesis plus equivalence filter, distill-then-RL. **[P]** — [arXiv 2505.24183](https://arxiv.org/abs/2505.24183)
  - FOARL: SFT on solver outputs, then a feasibility RL stage. **[P]** — [arXiv 2509.16865](https://arxiv.org/abs/2509.16865)
- **Hazards:**
  - Learned policies don't respect unencoded constraints. **[P]** — [DeepPCB](https://deeppcb.ai/reinforcement-learning-pcb-routing-explained/)
  - Imitation is biased without performance checks. **[P]** — [PARoute](https://www.cse.cuhk.edu.hk/~byu/papers/C223-DAC2024-PARoute.pdf)
  - Contamination. **[P]** — [VeriContaminated](https://arxiv.org/abs/2503.13572)
  - Near-dedup matters. **[P]** — [The Stack](https://arxiv.org/abs/2211.15533)

### Inferences (concrete plan; my synthesis, not sourced claims)

**1. What to scrape (target: about 3–8k clean boards, of which about 500–1,200 are 4+-layer).**
- Start from the kicad-happy `repos.md` (pinned SHAs) and PCBWorld's D3 recipe.
- Expand via open-schematics `name` and a dated `gh search code` for `(kicad_pcb (version 202`.
- Add professional strata: Adafruit and SparkFun Eagle boards imported via KiCad's Eagle importer (track conversion DRC separately), Antmicro open hardware, OSHWA-certified projects that link KiCad sources, and boards with Gerbers or release tags.
- Store raw files only in a git-ignored cache at pinned SHA. Store derived features in the project's dataset with provenance.

**2. Manifest and license tiers per board.**
- **Manifest fields:** `repo, sha, path, kicad_file_version, spdx (LICENSE + README + scancode), tier A/B/C, layers, n_parts, n_nets, board_area, has_gerbers, stars, last_commit_date, category`.
- **Tier A** goes into training. **Tier B** goes into retrieval-with-attribution and evaluation. **Tier C** is evaluation-only and private. Keep an opt-out mechanism.

**3. Cleaning pipeline.**
- (a) `kicad-cli pcb upgrade`.
- (b) `kicad-cli pcb drc --format json` against the board's own rules. Record errors, unconnected items and courtyard overlaps. Drop boards with unrouted nets from routing-imitation sets, and drop boards with courtyard overlaps from placement sets.
- (c) Schematic↔PCB parity check, to drop stale PCBs.
- (d) **Near-dedup:** cluster by footprint-multiset Jaccard plus a netlist WL hash. Keep one representative per cluster for training and put whole clusters on one side of any split. Keyboard and devboard clones are the main duplicates.
- (e) Quality score: professional source, fabricated (Gerbers or release), DRC-clean, layer count. Use it for sampling weights, not as a hard filter.

**4. Automatic labelling (the data products).**
- **(i) Subcircuit instances** from rule detectors (kicad-happy-style: decoupling, regulators, crystals, USB, ESD, dividers) plus WL-hash motif mining (gSpan on labelled 2-hop neighbourhoods).
- **(ii) Fragment geometry relative to the anchor IC:** per-satellite (Δx, Δy, Δθ, side) in the IC frame, distance to the specific pin pad, via count and length to the plane, and loop-area proxies for buck input/output loops.
- **(iii) Empirical prior tables:** for example decap-to-power-pin distance percentiles per package and per cap value, crystal-to-pin distance, ESD-to-connector distance. These are conditioned on layer count and source tier.
- **(iv) Module partition** from sheet hierarchy and clustering, and module-to-edge and module adjacency graphs.
- **(v) Routing-style labels:** width, clearance and layer per inferred net function, plane usage, diff-pair geometry.
- **(vi) ModuPlace-style constraint graphs** (relative offsets, rotation offsets, weights) per board, **verified by round-trip**: re-solve with the project's placer from the constraints alone and keep the pair only if the result is within tolerance of the human board (HPWL ratio, routed completion, embedding similarity). Where it fails, run BO over constraint weights (the GenLeaf trick) to find the constraint set that reproduces the human layout.

**5. What to train first (in order of return on effort).**
- **Step 0, no training:** a retrieval service (WL hash filter + graph-kernel or GNN rerank) returns top-k human fragments plus prior tables. The LLM agent cites them as soft constraints. This ships first and is license-friendly with attribution.
- **Step 1, small specialist models:**
  - A DevFormer-style relative-position transformer predicting satellite offsets given anchor footprint and pin functions, trained on (ii).
  - A pairwise layout ranker (GNN) trained on cheap synthetic preferences (human board vs perturbed board) before any expert labels.
- **Step 2, LLM SFT** (Qwen-class 7–14B, LoRA): netlist + board context in, constraint graph or placement-DSL out, trained on verified pairs from (vi) plus perturb-and-repair examples.
- **Step 3, GRPO/DAPO** with executable rewards. Hard gates: parse, overlap, outline, DRC. Dense terms: HPWL ratio, net crossings, Freerouting/KRT completion and vias, prior-table compliance, embedding similarity to the human board when one exists. Group size about 4–5 out of 16–36 samples, as published.
- **Step 4, preferences:** collect a few hundred expert A/B rankings on tier-A boards to train the ModuPlace-style ranker, or use DPO pairs. Add AesthetiQ-style MLLM-judge pairs only as a weak supplement.
- **Defer end-to-end coordinate generation** (diffusion or RL placers) until the constraint route plateaus. Evidence (ACDC, PCBWorld, TILOS) says direct geometry learning is the least data-efficient path.

**6. How to evaluate.**
- **Splits:** (a) time-split: boards first committed after the base model's cutoff; (b) cluster-split: no near-duplicate across train and test; (c) private boards from users; (d) strata by layers (2 / 4 / 6+) and source tier.
- **Tasks:** place-only (fixed router scoring), route-only (PCBWorld-compatible CP@k), place+route, and subcircuit-level ("place this buck/USB-C/ESD block").
- **Metrics:** DRC errors, routed completion, HPWL and via ratio vs human, prior-table compliance (for example share of decaps within the human p50 distance), physics proxies (loop area, return-path continuity), and blind expert preference on a subset.
- **Mandatory ablations:**
  - rules-only constraints vs corpus-learned priors vs both, with the same solver (this fills the evidence gap in Q6);
  - retrieval on vs off;
  - SFT-only vs +GRPO.
- **Contamination probes:** test whether the base LLM can reproduce test boards' footprint coordinates from a partial prompt (Min-K%-style). Report popular and obscure splits separately.

### Gaps
- All volumes above (3–8k clean boards; 500–1,200 4+-layer) are extrapolations from one catalog. A real pipeline run is needed to measure DRC-clean, license-tier-A yields.
- The tolerance for "round-trip equivalence" of placements (how close to the human board counts as reproducing it) has no published precedent for PCBs. It must be calibrated empirically.
- It is unknown how much expert preference data a PCB ranker needs; ModuPlace's ranking-set size was not found.
