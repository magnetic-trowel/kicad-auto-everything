# Learning PCB Placement and Routing from Data: Open-Source Layout Corpora, Layout Retrieval, Imitation and Synthetic Data, and Fine-Tuning LLMs for Layout

**Scope note for the report writer.** This file deliberately skips material already covered elsewhere and cross-references it instead:
- **`constraints_verification_benchmarks.md` Q4–Q5:** PCBWorld headline results, OmniLayout/OmniRouting, PCB-Bench, RL_PCB, tscircuit SRJ, the netlist SFT set, KiCad design blocks and multichannel.
- **`placement_algorithms.md` Q3:** PCBAgent and ModuPlace headline results, ChiPFormer, MaskPlace, chipdiffusion.
- **`cross_domain_ideas.md`:** CAD-Coder, Lara RLVR floorplans, TileGPT/QD synthesis.
- **`patents_and_industry.md` §3:** Zuken AIPR "Brain" learning from design libraries, and DeepPCB/Quilter training claims.

New in this file:
- **Measured corpus profiles:**
  - PCBench license, version and layer mix, which resolves the earlier "164 vs 679 boards" discrepancy;
  - the 5,856-entry kicad-happy repo catalog;
  - the 235-board circuit-skills licensed corpus;
  - a license spot-check.
- **A new data product:** decoupling-cap distance and trace-width priors measured on 128 permissively licensed boards.
- **Third-party experiments on learned versus hand-coded placement scores**, and on how much "hints extracted from the designer's placement" help.
- **Layout retrieval and migration** literature, analog and PCB.
- **Imitation-learning details:** GeniusRoute, DevFormer, ChiPFormer.
- **Fine-tuning recipes with exact reward formulas and data funnels:** GenLeaf, CodeV-R1, VeriReason, VeriPrefer, FOARL, SchGen, spatial RLVR.
- **Contamination and licence-text analysis**, including CERN-OHL-S §3.2.

**Provenance tags.**
- **[P]**: read from the primary source in this session (full PDF, dataset card, repo file, or arXiv abstract via the API; fetched with curl because WebFetch DNS failed).
- **[S]**: search-engine snippet or summary only.
- **[M]**: my own measurement on downloaded data, with the method stated.
- **[preprint]**: arXiv-only or not peer-reviewed, as far as I could tell.
- **[3P-unreviewed]**: a third-party engineering document in a GitHub repo, not peer-reviewed.

---

## Q1. Corpora: how much open PCB layout data exists (KiCad/Eagle/Altium, OSHWA, published ML datasets), under what licenses, and with what quality problems?

### Takeaway
Raw supply is in the tens of thousands of boards:
- open-schematics: 87,931 records / ~317 GB;
- kicad-happy catalog: 5,856 repos / 18,679 PCB files;
- PCBench: 1,183 boards;
- OSHWA: 3,452 certified projects;
- plus hundreds of professional Eagle boards (Adafruit, SparkFun).

**Usable, licensed, rule-clean supply is one to two orders of magnitude smaller:**
- **PCBench**, the source of PCBWorld D3: **62% of boards have no clear licence**, **89% are 2-layer**, and **only 23 of 1,183 are KiCad 6+ format**.
- **circuit-skills' licence-filtered collector** kept **235 boards from 423 candidate repos**. Only **33%** of those designers' boards pass their *own* KiCad DRC with zero errors.
- **kicad-tools' census of open-schematics PCBs** found only 36% usable as route-vs-human cases before a legacy-format parser fix (73% after).
- In a random sample of kicad-happy repos, **41% have no top-level licence file**.

Hobby boards dominate: 63% are 2-layer, keyboards and ESP32 boards are the largest named categories, and the median board has 65 parts.

### Cited Findings

**PCBench (the source pool for PCBWorld D3): [M] full metadata census.**
- **Method:** I shallow-cloned [PCBench/PCBench](https://github.com/PCBench/PCBench) and downloaded all **1,183** `PCBs/*/metadata.json` files. Each records the source repo, author, retrieval time, the licence as reported by the GitHub API, layer count and CAD version.
- **Size history:** retrieval dates are 164 boards in **2023-04** and 1,018 in **2023-08**, from **842 source repos and 561 authors**. This resolves the discrepancy noted in `constraints_verification_benchmarks.md`: the README's "164 PCBs" is the April 2023 first batch, the repo now holds 1,183, and PCBWorld kept 679 after conversion and filtering. PCBWorld itself mentions a pool of about 1,182 boards converted to KiCad 9.
- **Licences (GitHub-detected):**
  - **no licence or unclear: 735 (62.1%)**, comprising "None" 606, NOASSERTION 93, and empty or "not found" about 36;
  - **permissive: 221 (18.7%)**, mostly MIT (128), then Apache-2.0 28, CC-BY 11, BSD, CC0, WTFPL;
  - **reciprocal: 213 (18.0%)**: GPL-3.0 105, GPL-2.0 about 20, CC-BY-SA-4.0 17, AGPL and LGPL, CERN;
  - unspecified "Creative Commons": 14.
- **CAD versions:** KiCad 4 651, KiCad 5 (`20171130`) 377, KiCad 3 88, other pre-6 dates 43, **KiCad 6+ formats only 23**.
- **Layers:** 2-layer 1,052 (89%), 4-layer 126, 6-layer 3, 8-layer 1.

Source: [PCBench repo](https://github.com/PCBench/PCBench)
- PCBench boards are "KiCad 5 files with no project file, so their rules are KiCad's defaults". **[P]** — [circuit-skills collect.py docstring](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/collect.py) (repo has no licence; facts cited only)

**circuit-skills licensed corpus (most rigorous public collector found).** **[P][3P-unreviewed]**
- **Pipeline** [collect.py](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/collect.py):
  - **Search:** GitHub search with queries such as `topic:kicad stars:>=10`, `topic:oshw stars:>=10` and `language:"KiCad Layout" stars:>=5`, restricted to a licence allow-list (MIT, Apache-2.0, BSD-3, CC0, CC-BY-4.0, CC-BY-SA-4.0, CERN-OHL-P/W/S-2.0, GPL-3.0).
  - **Pick:** `.kicad_pcb` files with a `.kicad_pro` beside them, at most 2 per repo, deduplicated by git blob hash. Path filters skip lib/template/panel/backup/test/example directories.
  - **Fetch:** at a pinned commit into a cache, "never into the repo".
  - **Qualify:** with stock KiCad. The board must open, have 1–4 copper layers, enough parts and at least 10 segments. It is rejected if `kicad-cli pcb drc` shows *any* unconnected item in the designer's routing.
  - **Record:** the manifest stores the error-level DRC violation count of the designer's board (`ref_drv`) and of the stripped board (`bare_drv`). Boards are bucketed into easy/medium/hard by connections (<40, <150, more).
- **[M] Manifest statistics** ([manifest.json](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/manifest.json), commit `34e3841`, 2026-10-05):
  - **235 boards from 170 repos**, out of 423 candidates in `candidates.json`;
  - **licences:** MIT 75, GPL-3.0 67, CERN-OHL-S-2.0 25, CERN-OHL-P-2.0 25, Apache-2.0 19, CC-BY-SA-4.0 10, CERN-OHL-W 5, CC-BY 4, BSD-3 3, CC0 2;
  - 2-layer 178, 4-layer 57;
  - parts: median 59, max 558; connections: median 119;
  - **designer `ref_drv` (error-severity DRC violations under the board's own rules): median 4, max 938, and only 77 of 235 (33%) at zero**;
  - stripped-board `bare_drv` is zero for only 73 of 235, so most human *placements* already carry error-level violations such as courtyard and silk issues.

**kicad-happy test corpus (largest pinned list).**
- **Selection history:** the corpus "started at 1,052 repos curated from publicly available GitHub repositories". 87 were purged: "18 Eagle-only, 14 tool/library repos, 22 PCB-only, 33 with fewer than 3 components". In April 2026 it was "expanded via automated discovery across GitHub, GitLab, and Codeberg… to the current 5,822 repos". Every repo is pinned to a commit hash.
- **The author's bias statement:** "biases it toward ESP32 dev boards and mechanical keyboards (the dominant categories in open-source KiCad), simple power supplies… Underrepresented domains include high-frequency RF, precision analog, power electronics with complex topologies… mixed-signal designs."
- **Analyzer limitation:** the schematic analyzer cannot associate a regulator on one sheet with decoupling caps on another sheet.

**[P]** — [methodology.md](https://github.com/aklofas/kicad-happy-testharness/blob/main/methodology.md); [README](https://github.com/aklofas/kicad-happy-testharness)
- Totals across the corpus: 6,845 schematic files, **3,498 PCB files analyzed**, 312,956 components, 531,418 nets, KiCad 5–10. **[P]** — [kicad-happy README](https://github.com/aklofas/kicad-happy)
- **[M] Profile of `repo_catalog.json`** (5,856 entries):
  - **5,707 repos have PCB files**, totalling **18,679 PCB files** (the count probably includes old revisions and backups).
  - **KiCad generation:** mixed 3,824, kicad7 713, kicad6 630, kicad5 619, kicad9 29, kicad10 21.
  - **Max layers:** 2-layer 3,619 (63%), 4-layer 1,028, 6-layer 100, 8-layer 22, 10 or more layers 10, "0 layers" 621 (unparsed or empty).
  - **Components per repo:** median 65, p90 488, p99 2,284. 2,374 repos have 100 or more parts.
  - **Categories:** Miscellaneous 1,810, **Keyboards 449**, Synths/audio 324, Motor/robotics 315, LED 304, ESP32 294, Arduino recreations 294, RF/SDR 254, IoT 250, Retro 235, USB 214, Power 207, RP2040 192, STM32 179, … CubeSat 39, SBC 33.
  - **Detectors that fired:** decoupling in 3,848 repos, regulators in 2,979, crystals in 1,852, USB in 809.
  - **Quality and other tags:** median "documentation" score 0; `has_gerbers` on 2,213 repos.

  Source: [repo_catalog.json](https://github.com/aklofas/kicad-happy-testharness/blob/main/reference/repo_catalog.json)
- **[M] Licence spot-check:** 54 random catalog repos, top-level LICENSE file read at the pinned SHA and keyword-classified. **No licence file 41%**, permissive 37% (MIT 11, Apache 4, BSD 3, Unlicense 1, CC0 1), reciprocal 22% (GPL-3 3, CERN-OHL-S 3, CC-BY-SA 3, LGPL 2, TAPR 1). The 95% CI is about ±13 pp. Sources: raw.githubusercontent.com at catalog SHAs.

**open-schematics (Hugging Face) and its measured usability.**
- **Size and licence:** **87,931 rows, 316.8 GB parquet**, CC-BY-4.0 dataset tag, described as "self-growing, autonomous… continuously scans the web".
- **Per row:** raw schematic (`.kicad_sch`/`.sch`/`.SchDoc`), `pcb_files` (raw `.kicad_pcb`/`.pcb`), renders and `name` = owner/repo.
- **Filters and gaps:** PCBs over 10 MB dropped; JSON only for about 85% of rows; PCB images missing for about 55%.
- **Licence caveat:** "comply with the original licenses of the source projects", with no per-row licence.
- **Downloads and copies:** 11,966 downloads; at least 12 re-uploads exist under other accounts.
**[P]** — [card](https://huggingface.co/datasets/bshada/open-schematics); [size API](https://datasets-server.huggingface.co/size?dataset=bshada/open-schematics); [HF search](https://huggingface.co/api/datasets?search=schematic)
- **kicad-tools census** of 22 revision-pinned open-schematics PCBs:
  - Before a parser fix, only **10/22 (45.5%) were featurizable** and **8/22 (36.4%) were usable as route-vs-human cases**. Nine boards (41%) used the pre-KiCad-6 `(module …)` spelling.
  - After adding legacy support: **18/22 featurizable, 16/22 (72.7%) usable**.
  - Residual blockers: no net with 2 or more pads (2), no reference copper (2), no outline (1), and legacy centre+angle `gr_arc` outlines (1).
  - **Method lessons:** "A pour counts as copper" (a trace-only completeness test misgrades 7 of 8 boards). A route-vs-human harness "must adopt each board's `(setup …)` clearance/track-width". On one dense board (11.4 pads/cm²) their router reached 20% against the human's 100%.
  - The README describes open-schematics as "~75k real `.kicad_sch` + paired `.kicad_pcb` files".
  **[P][3P-unreviewed]** — [corpus-benchmark-feasibility.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/corpus-benchmark-feasibility.md); [scripts/corpus/README.md](https://github.com/rjwalters/kicad-tools/blob/main/scripts/corpus/README.md)

**Other new corpora and datasets.**
- **SchGen** (Microsoft, 2026): **2,105 KiCad schematics (1,390 unique designs)** rebuilt from **SparkFun designs under CC BY-SA 4.0** by "a human–agent collaborative pipeline", ×4 to 8,420 samples via two prompt styles and two CoT sources. An out-of-distribution set has 988 samples from 20 GitHub KiCad projects. **[P]** — [arXiv 2605.30345](https://arxiv.org/abs/2605.30345) [preprint]; [code](https://github.com/microsoft/SchGen)
- **CELUS / U. Kassel schematic GNN datasets:** expert-labelled schematic graphs. **2,396** for pull-up/down insertion, **849** for reset RC filters, **944** for decoupling caps. Average 100–124 nodes; component names are embedded with `all-MiniLM-L6-v2`. **[P]** — [arXiv 2506.10577](https://arxiv.org/abs/2506.10577) [preprint]; [code](https://github.com/pasplett/pcb-node-pair-gnn)
- **KiCad 9+ schematic corpora** (98 permissive / 209 copyleft) were split after a legal audit (see Q7). **[P]** — [kicad9plus-permissive](https://huggingface.co/datasets/electron-rare/kicad9plus-permissive); [kicad9plus-copyleft](https://huggingface.co/datasets/electron-rare/kicad9plus-copyleft)
- **Ohmatic human-verified-schematics-v1:** 1,000 KiCad and Eagle schematics in trust tiers (685 grandfathered plus 315 with at least 2 independent evidence families). **[P]** — [card](https://huggingface.co/datasets/Ohmatic/human-verified-schematics-v1)
- **mascarade-kicad-dataset:** 2,645 Q&A pairs, **79.7% LLM-generated**. A heuristic "SE-style" detector overcounted human-sourced content by 5.6×. **[P]** — [card](https://huggingface.co/datasets/Ailiance-fr/mascarade-kicad-dataset)
- **R3SET** (J. Computing & Information Science in Engineering, 2026): 338 real requirements linked to 92 reusable circuit blocks from 8 OSH projects, plus 100 synthetic distractor blocks. A hybrid sparse + semantic + LLM retriever gets 71% Hit@1 and 92% Hit@5 on the one-to-one subset (n=271). **[S]** — [DOI 10.1115/1.4071107](https://doi.org/10.1115/1.4071107); [METU record](https://open.metu.edu.tr/handle/11511/119515)
- **OSHWA:** 3,452 certified projects on 2026-10-20 **[P]** — [oshwa.org](https://oshwa.org/). Earlier counts: 2,972 (Feb 2025) and 3,107 (Jul 2025) **[S]** — [Hackster](https://www.hackster.io/news/july-2025-open-source-hardware-certification-roundup-dcf069506dee). Certification spans all hardware types.
- **GitHub topic `kicad`:** 4,559 repos **[S]** (snapshot date unknown) — [topic page](https://github.com/topics/kicad).
- **Adafruit** publishes Eagle files for "all Adafruit designed printed circuit boards" on GitHub, with example repos under CC-BY-SA **[S]** — [Adafruit Learn](https://learn.adafruit.com/accessing-and-using-adafruit-pcb-design-files). **SparkFun** hardware repos are CC BY-SA 4.0 **[S]** — [RedBot_Line_Sensor](https://github.com/sparkfun/RedBot_Line_Sensor).
- **OSH documentation:** of 242 OSH products, 105 used GitHub, and about a third had adequate documentation. **[S]** — [Design Science](https://www.cambridge.org/core/journals/design-science/article/how-participative-is-open-source-hardware-insights-from-online-repository-mining/D1341B4E550B8F42032585694B6DB8D8)
- **PCB-Layout** (668 photo/layout image pairs) is not useful for placement. **[P]** — [card](https://huggingface.co/datasets/Warren-wzw/PCB-Layout). **OmniSch** (1,854 schematic diagrams) is an upstream netlist-extraction benchmark. **[P]** — [arXiv 2604.00270](https://arxiv.org/abs/2604.00270)
- A GenAI-for-PCB survey screened 227 papers and included 80 (as of 2025-08-08). It names "domain-specific data scarcity" as a key challenge. **[P]** — [arXiv 2606.17074](https://arxiv.org/abs/2606.17074) [preprint]

### Inferences
- **Expected yield funnel** for a KiCad training/eval set, combining the measurements above:
  1. **Discovery:** about 10⁴ candidate repos.
  2. **Licence-clean:** about 40–60% survive (PCBench 38% clear; kicad-happy sample 59% with a licence file).
  3. **Openable and modern enough to parse:** legacy formats are 41% of one open-schematics sample and 97% of PCBench.
  4. **Fully routed with no unconnected items:** this criterion alone left circuit-skills with 235 of 423 repos' boards.
  5. **DRC-clean under the board's own rules:** about 33%.

  Expect **low thousands** of licence-clean, fully routed boards. Expect **a few hundred** that are also DRC-clean, and a few hundred 4+-layer boards.
- **DRC-cleanliness of human boards is the exception.** Training targets should therefore be "human placement and routing *as relational structure*" (relative poses, layer and width choices), with legality enforced by the project's own solver. Raw human geometry should not be treated as ground truth.
- Use open-schematics and the kicad-happy list as **discovery indexes** (owner/repo), not as training sets. Re-fetch at pinned SHAs with your own licence detection and DRC qualification, as circuit-skills does.

### Gaps
- There is still no authoritative count of `.kicad_pcb` files on GitHub or GitLab. GitHub code search and repository search APIs were blocked from this environment, and Sourcegraph timed out.
- No counts were obtained for OSHWHub (JLC), whose host reset the connection, nor for Kitspace, Hackaday.io or CERN OHR.
- open-schematics' row-level split between KiCad, Eagle and Altium PCBs, and its fraction of routed boards, were not measured beyond the 22-board kicad-tools sample.
- No published Altium layout dataset for ML was found.

---

## Q2. Layout retrieval and pattern mining: graph similarity over subcircuits, frequent-motif mining, and VLSI/analog layout reuse and migration analogues

### Takeaway
No PCB layout-retrieval system has been published, but the parts exist:
- **Structural retrieval:** WL-hash plus motif-vector retrieval (NEMESIS, λ=0.6), GNN region prediction for subcircuit matching, GCN annotation of analog netlists (GANA/ALIGN).
- **Requirement-to-block retrieval** over open hardware (R3SET: 71% Hit@1) and **embedding retrieval of similar designs to seed tool parameters** (CROP).
- **Frequent-pattern mining** (CellE).
- **Analog-IC knowledge-based reuse**, the closest analogue, with numbers. Wu et al. (TCAD'15) match legacy subcircuits, choose patterns via max-weight clique, and report 73–100% device reuse. ISPD'18 extracts symmetry and regularity constraints from existing placements.
- **PCB-Migrator** (DATE'26) migrates expert PCB layouts via offset constraint graphs.

A sobering result comes from circuit-skills' hint study. Coarse constraints derived from the designer's placement (anchors, big-part relations, "small parts near their big part") barely improved clean-route rate: 0.19–0.21 vs 0.15 with no hints, against 0.63 for the designer's own placement. **Retrieval must transfer fine-grained relative geometry, or it will not capture what makes human placements route.**

### Cited Findings

**Structural retrieval.**
- **NEMESIS** (2026) gives each netlist "a compact structural signature consisting of a motif vector (capturing coarse block-level composition, e.g., shared-gate mirrors and device counts) and a two-iteration Weisfeiler-Lehman (WL) refinement hash". Similarity is "s(q,i) = λ·s_WL(q,i) + (1−λ)·s_motif(q,i)", where s_WL is the Jaccard similarity of WL hashes and s_motif the cosine of motif vectors, and "we choose λ = 0.6". After SPICE verification, "newly accepted equations are indexed via the same pipeline: thus, the database grows through verified updates". **[P]** — [arXiv 2607.05657](https://arxiv.org/abs/2607.05657) [preprint]
- **GNN region prediction for subcircuit matching:** constructs negative samples and extracts subgraph embeddings directly from the whole-circuit embedding, outperforming prior methods on time and region prediction. **[P]** — [arXiv 2507.19518](https://arxiv.org/abs/2507.19518) [preprint]
- **Circuit-diagram retrieval:** recognizes components and topology from images (GAM-YOLO), then runs hierarchical graph-similarity retrieval for "consultation of legacy designs and the detection of design plagiarism". **[P]** — [arXiv 2503.11658](https://arxiv.org/abs/2503.11658) [preprint]
- **CROP:** RTL→embedding retrieval of "semantically similar circuits", then RAG-guided LLM parameter search constrained by "prior knowledge from similar designs", reporting a 9.9% power reduction on industrial designs. **[P]** — [arXiv 2507.02128](https://arxiv.org/abs/2507.02128) [preprint]. This is the pattern for "retrieve similar boards → reuse their router/placer settings".
- **R3SET** requirement → block retrieval over open-hardware blocks: 71% Hit@1, 92% Hit@5. An LLM final selector slightly beat the hybrid retriever on the full set (60.1% vs 58.5% top-1). **[S]** — [DOI 10.1115/1.4071107](https://doi.org/10.1115/1.4071107)
- **GANA** (DATE'20): GCN labels upper-level analog blocks while graph algorithms find lower-level primitives, and it detects symmetry and matching constraints. ALIGN's GCN training set is 1,390 OTA circuits. **[S]** — [IEEE](https://ieeexplore.ieee.org/document/9116329); [ALIGN](https://arxiv.org/pdf/2008.10682). The data repo builds adjacency, feature and label matrices from SPICE OTAs. **[P]** — [GANA_circuit_data](https://github.com/kkunal1408/GANA_circuit_data)
- **Classic subgraph isomorphism:** SubGemini **[S]** — [paper](https://lamarr.ece.uw.edu/research/ssrl/download/FROSTY/design/data/subgemini.pdf). NetworkX WL hashing gives exact-isomorphism hashes. **[S]** — [docs](https://networkx.org/documentation/latest/reference/algorithms/graph_hashing.html)
- **Design-reuse patents:**
  - Pattern-matching a work-in-progress PCB's connectivity against a company "design vault" **[S]** — [US 11593437](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11593437).
  - Analog template matching with pruning **[S]** — [US 11354477](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11354477).

**Frequent-motif mining.**
- **CellE:** equality saturation over post-mapping netlists, then "an efficient pattern mining algorithm" selects new standard cells, giving 15.41% average area reduction and 8.00% delay reduction. **[P]** — [arXiv 2603.12797](https://arxiv.org/abs/2603.12797) [preprint]. gSpan is the canonical frequent-subgraph miner. **[S]** — [gSpan](https://sites.cs.ucsb.edu/~xyan/papers/gSpan-short.pdf)

**Analog layout reuse, retargeting and migration (read in full where marked).**
- **Wu, Lin, Chen, Yeh, Li, Ho (IEEE TCAD 34(2), 2015)**, "the first knowledge-based physical synthesis methodology", has three steps:
  1. design-knowledge database construction from legacy schematics, netlists and layouts, stored as connection graphs;
  2. matching and pattern extraction: common sub-circuits between the target and legacy designs under design constraints;
  3. layout generation reusing the "quality-approved legacy layouts as much as possible".

  Because extracted patterns overlap, pattern selection is solved as **maximum-weight clique** maximizing the reuse rate. **Worked example** (target: two-stage Miller op-amp):
  - with only a legacy diff-amp in the repository, 73.33% of devices and 39.29% of nets reuse legacy layout;
  - with only an OTA, 86.67% of devices and 50.00% of nets;
  - with both, 100% of devices.

  The paper notes that earlier migration and retargeting "assumes that the legacy design and the new design must have the same schematic/netlist topology". **[P]** — [TCAD 2015 PDF](https://users.ece.cmu.edu/~xinli/papers/2015_TCAD_pd.pdf)
- **Xu, Basaran, Su, Pan, "Analog Placement Constraint Extraction and Exploration with the Application to Layout Retargeting" (ISPD'18):** "Given the vast amount of previous high-quality analog layouts, it is desirable to explore the layout design constraints from them". Sweep-line algorithms extract symmetry and regularity (alignment) constraints from existing placements and preserve them while reducing placement area by 7.6% on average. It summarizes IPRAIL and MASH as template-extraction retargeting tools that keep the same topology. **[P]** — [ISPD'18 PDF](https://par.nsf.gov/servlets/purl/10121012)
- **Lin et al. (ICCAD'20, invited):** learning-plus-migration framework, motivated by "different companies and designers follow different guidelines and preferences". **[S]** — [NYCU](https://scholar.nycu.edu.tw/en/publications/achieving-analog-layout-integrity-through-learning-and-migration-/). **IPRAIL:** retargets op-amps from 0.25 to 0.18 µm. **[S]** — [paper](https://lamarr.ece.uw.edu/research/ssrl/workspace/iprail/web_IPRAIL/JOURNAL_ELSEVIER.pdf). **Synopsys** ML migration 14 nm → 5 nm (vendor claim). **[S]** — [blog](https://www.synopsys.com/blogs/chip-design/ai-analog-design-migration-samsung-safe-forum-2023.html)
- **PCB-Migrator** (Han … Bei Yu, Tsung-Yi Ho, Tinghuan Chen; DATE 2026): when "board dimensions" change or "new obstacles" are added, "experts must often recreate similar layouts from scratch". It uses "an offset constraint graph to capture positional relationships among components", and migrating from expert results "gives the tool foresight". **[S]** for content; **[P]** for the bibliographic entry — [yhhan.com](https://yhhan.com/publications). The DATE archive PDF URL returns 404 at three hostnames, and Semantic Scholar rate-limited queries.
- **GenLeaf's supervised layout embedding:** GraphSAGE over a placement graph plus a routing image. MSE is 34.0% and 35.9% lower than Circuit GNN and DeepLayout on a layout-quality prediction task, and the embedding is used as a similarity metric. **[P]** — [GenLeaf PDF](https://yhhan.com/PDFs/GenLeaf_paper.pdf)

**How much do coarse "learned-from-human" constraints transfer? (PCB, measured)**
- **circuit-skills "What do placement hints buy?"** (52 boards). Hints are derived from each designer's placement at three levels, then every part is placed from scratch by their annealer, routed by TraceMaker (20 s) and judged by KiCad DRC.

  | Placement | Clean route | Error-level DRC before routing |
  |---|---|---|
  | Designer's own placement | **0.63** | 0.0 |
  | No hints | 0.15 | 30.0 |
  | Level 1: edge/region anchors | 0.19 | — |
  | Level 2: plus big-part relations | 0.21 | — |
  | Level 3: plus small parts near their big part | 0.19 | 30.2 |

  Hints moved big parts much closer to the designer's positions (26% → about 11–12% of the board diagonal), but the clean-route rate barely moved. **[P][3P-unreviewed]** — [hints_study.md](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/hints_study.md)

### Inferences
- **Retrieval design:**
  1. Key on the anchor IC (MPN family plus pin-function multiset) plus a 2-hop labelled neighbourhood.
  2. Filter coarsely by WL hash and motif histogram (NEMESIS-style), then rerank with a GNN or graph kernel.
  3. Return the **top-k human fragments with full relative geometry**: per-pad offsets of passives in the IC frame, rotation, side, plus via and trace topology.
  4. Return summary statistics alongside.
  5. Let the solver adapt and legalize.
- Use the **Wu-2015 max-weight-clique formulation** to pick a non-overlapping set of retrieved fragments that maximizes reused parts on a new board.
- Make the database **grow only through verified updates** (NEMESIS): a fragment is indexed only after it passes DRC and routes in its new context.
- **The hint-study result is a warning.** What makes human placements route (0.63 vs 0.15) is not captured by anchors and coarse "near" relations. The likely carriers are fine-grained orientation, pin-escape-aware spacing and channel reservation. Fragment transfer should copy exact relative poses where packages match, and constraint extraction should be validated by **round-trip re-solving** (Q4), not assumed sufficient.
- **Licence interaction (see Q7):** copying a CERN-OHL-S or CC-BY-SA fragment's geometry into a user's board plausibly makes the user's board a derivative under that licence. Retrieval UIs must surface the licence and let users filter to permissive fragments.

### Gaps
- PCB-Migrator's full method and results (DATE PDF unavailable).
- No measurement of cross-board layout variance per motif (for example, how consistently the same buck regulator is laid out).
- R3SET's full text was unreachable (connection reset); its numbers are from search snippets.

---

## Q3. Imitation learning / behavior cloning from human layouts: what has been tried for placement, routing order/topology and relative offsets, and how well did it work?

### Takeaway
Imitation from human layouts works only in narrow, data-efficient forms, and none is end-to-end on PCBs:
- **GeniusRoute** learned *where* clock, differential and power nets should run from manual analog layouts. It used tiny labelled sets (168 / 128 / 256 augmented samples) plus 6,360 unlabelled samples, and reached quality "competitive" with manual layouts. Successors call it data-starved and performance-blind.
- **ChiPFormer's "expert" offline data is optimizer output** (500 MaskPlace placements × 12 circuits), not human layouts.
- **DevFormer** learned decap placement from **2,000 GA solutions**, and with only 100 it beat baselines trained on 2,000, thanks to symmetry inductive biases. It needed 26 decaps where GA needed 40.
- **On PCBs**, Lim 2026 uses human placements only as ground truth for comparison. Its RL agents beat human wirelength on simple subcircuits but produce overlaps that wirelength doesn't capture.

Measured PCB evidence (circuit-skills, 64 boards): **designer placements route clean 0.56 of the time, versus 0.12–0.16 for two automatic placers and 0.31–0.39 for designer placements with swapped interchangeable parts.** Human placements carry real, learnable signal; nobody has yet learned it end-to-end.

### Cited Findings
- **GeniusRoute** (ICCAD'19, UT Austin), read in full:
  - **Goal:** "imitate human intelligence from well-designed manual layouts". The motivating example is a comparator whose expert clock route "detours around the layout boundary", which is "counter-intuitive in the sense of minimum wirelength" but better for offset.
  - **Model:** small VAE-based encoder/decoders on 64×64 placement and routing images, with Gaussian blurring (17×17 for routing, 5×5 for placement) "to focus on the routing regions rather than the exact metal shapes".
  - **Training:** semi-supervised. After flip and rotate augmentation there are **168 clock, 128 differential and 256 power/ground** labelled samples and **6,360 unlabelled** samples.
  - **Evaluation:** on COMP1, COMP2 and OTA, it "achieves competitive performance compared with manual layouts".
  **[P]** — [GeniusRoute PDF](https://par.nsf.gov/servlets/purl/10192510)
- **PARoute/AnalogFold critique** (DAC'24): "Machine learning methods summarize the experience from existing routing solutions, but suffering from scarcity of manual data… The training process relies on manual labeling data… existing methods do not explicitly consider performance optimization and lead to biased routing guidance." **[P]** — [PARoute PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C223-DAC2024-PARoute.pdf)
- **ChiPFormer** (ICML'23), read in full: "we employ MaskPlace as the proxy method to learn 12 expert-level behavior (data-collecting) policies over 12 circuits (8 from ISPD05 and 4 from ICCAD04)… collect **500 expert-level placement results for each circuit**". The stochastic policy gives diversity. It pretrains on grouped circuits and fine-tunes on unseen ones with return-weighted regression and few-shot online rollouts (for example 300). It is evaluated on 32 circuits, including 6 industrial ones compared with human experts, with a 10× runtime reduction. **[P]** — [arXiv 2306.14744](https://arxiv.org/abs/2306.14744)
- **DevFormer** (ICML'23, KAIST), read in full:
  - **Task:** decap placement on a chip-package PDN modelled as a 10×10 grid, scored at 201 frequency points from 200 MHz to 20 GHz.
  - **Data:** "N expert data, collected by a genetic algorithm (GA)", with N = 2000 and M = 100 simulations each.
  - **Training:** imitation (teacher forcing) plus self-exploitation with action-permutation-symmetric augmentation.
  - **Data efficiency:** "DevFormer trained with N = 100 even outperformed the baselines trained with N = 2000."
  - **Generalization:** zero-shot to 15×15 PDNs and different decap counts.
  - **Case study:** noise reduced 94.2% with 26 decaps versus GA's 93.5% with 40.
  **[P]** — [arXiv 2205.13225](https://arxiv.org/abs/2205.13225)
- **Lim et al. 2026** [preprint], read in full:
  - The benchmark "PCBs" are **subcircuits extracted from larger PCBs**: a main IC plus 8–24 passives and 4–14 nets. Human placement is used as ground truth.
  - "Apart from the most complex cases (U20 and U26), all the MLs are able to surpass GT in terms of TEWL measure. However, TEWL does not take into account placements that have passives overlapping and routing conflicts."
  - A2C was best overall, and a net-aware DQN improved further.
  - It argues decision transformers "cannot learn from random or exploratory placements outside the dataset… and require large, diverse datasets".
  **[P]** — [arXiv 2602.23540](https://arxiv.org/abs/2602.23540)
- **circuit-skills "Which placement measures predict a clean route?":** 64 corpus boards and 320 placements, each routed by TraceMaker and judged by KiCad DRC.

  | Placement | Clean | Connections routed | Pre-route DRC errors |
  |---|---|---|---|
  | Designer | **0.56** | 0.96 | 0.0 |
  | swap25 (designer, a quarter of same-footprint interchangeable parts swapped) | 0.39 | 0.94 | 0.9 |
  | swap100 (all such parts swapped) | 0.31 | 0.90 | 3.5 |
  | Their annealer (pk) | 0.12 | 0.92 | 36.9 |
  | tracemaker-place (tm) | 0.16 | 0.78 | 200.3 |

  **[P][3P-unreviewed]** — [score_study.md](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/score_study.md); [score_study.py](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/score_study.py)
- **Net ordering:**
  - IJCAI'25 transformer RL learns detailed-routing net order. **[S]** — [IJCAI](https://www.ijcai.org/proceedings/2025/1055)
  - A third-party test of a hand-designed "crossing-aware" net order on KiCad boards found it "leaves completion unchanged and makes vias worse" on target boards (02: 37→38; 03: 46→52, stale) but helped a small board (vias 5→3). **[P][3P-unreviewed]** — [kct-route-net-order-experiment.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/kct-route-net-order-experiment.md)
  - No imitation-learned net order exists: human routing order is not stored in board files.
- **DeepPCB** trains "sometimes [on] synthetic boards… sometimes real designs from a training corpus", over "millions of routing attempts across thousands of board configurations". **[P]** — [DeepPCB blog](https://deeppcb.ai/reinforcement-learning-pcb-routing-explained/). Zuken AIPR's "Brain" learns from design libraries (see `patents_and_industry.md`).

**[M] Relative-offset priors measured from human boards (new data product).**
- **Method:**
  - **Boards:** all **128 permissively licensed boards** (MIT, Apache-2.0, BSD-3, CC0, CERN-OHL-P, CC-BY) in the circuit-skills manifest, fetched at pinned commits.
  - **Parser:** a minimal S-expression parser computes absolute pad positions (footprint `at` plus a rotated pad offset). The rotation convention was validated: rotated pads land on track endpoints 66.9% of the time with this convention versus 30.5% with the opposite sign.
  - **Decap selection:** a "decap" is a 2-pad `C*` part with one pad on a GND-like net and one on a power-like net (name heuristics).
  - **Distance:** from the cap's power-pad centre to the **nearest pad of any `U*`/`IC*` footprint on the same net**.
  - Script: [`decap_stats.py`](../../tools/research/layout-data/decap_stats.py); 110 boards had ICs.
- **1 nF–1 µF caps (n=809, 82 boards):** p10 1.55 mm, p25 2.21, **median 3.29**, p75 5.75, p90 15.1 mm. **17% within 2 mm, 44% within 3 mm, 70% within 5 mm.** 85% are on the same side as the IC. Exactly 100 nF (n=637): median 3.44 mm.
- **By package:**
  - **0402:** median **2.51 mm**, p90 4.93, 63% within 3 mm, 95% same side;
  - **0603:** median 3.10, with a long tail (p90 64.6, probably caps serving loads not named U);
  - **0805:** median 3.73, only 54% same side.
- **By layer count:** 4-layer boards median 3.12 mm, p90 **7.7**, 97% same side; 2-layer boards median 3.60, p90 **26.0**, 77% same side.
- **Per-board medians:** median of medians **2.82 mm**, IQR 2.22–4.75.
- **By designer DRC status:** boards whose designer routing is DRC-clean have a tighter tail (p90 7.7 mm vs 17.7 mm). GitHub stars barely matter (median 3.35 / 3.28 / 2.96 mm for <100 / 100–1k / >1k stars).
- **Bulk caps over 1 µF (n=398):** median 5.33 mm, p90 34 mm.
- **[M] Routing-style priors (same 128 boards):**
  - 114/128 (89%) have a GND zone;
  - median per-board signal track width 0.25 mm (IQR 0.20–0.25);
  - power-net width 0.40 mm (IQR 0.25–0.50);
  - per-board power/signal width ratio median **1.88**, with 69% of boards using more than 1.2×.

### Inferences
- The learnable, cheap signal from human boards is **relational and per-package**. Examples: a 0402 decap sits about 2.5 mm (pad-to-pad) from its IC power pin, on the same side, on 4-layer boards; power traces run about 1.9× signal width. These numbers can seed soft constraints immediately, with no ML model.
- **Corpus priors are looser than datasheet rules.** "Within 2 mm" is met by only 17% of hobby decaps. Use corpus percentiles conditioned on package and layer count as *soft* targets, and datasheet or rule distances as *hard* or tight targets. A prior learned from "all boards" would encode the 2-layer hobby tail: p90 26 mm.
- **The designer-vs-auto gap is the opportunity.** Designer placements route clean 0.56 against 0.12–0.16 for automatic placers on the same netlists. Swapping identical-footprint parts already drops this to 0.31–0.39, so assignment *within* groups (which cap goes to which pin) matters a lot. The best first target is a DevFormer-style relative-pose and assignment model for satellites around anchors, trained on corpus fragments with symmetry augmentation.

### Gaps
- The decap measurement is heuristic. It uses net-name rules and "nearest same-net IC pad" as a proxy for the intended pin, measures pad-centre to pad-centre, and covers 82 boards. It is not validated against human annotation.
- Nobody has measured whether learned relative-pose priors raise clean-route rates on held-out boards. The hint study suggests coarse versions do not.
- I found no imitation learning of routing topology on PCBs.

---

## Q4. Synthetic data generation and self-improvement loops for layout learning

### Takeaway
Successful EDA fine-tuning pipelines **manufacture verified supervision**:
- **CodeV-R1** funnels 150K round-trip NL↔Verilog samples to 87K equivalence-checked SFT samples, then to 3.1K "hard" RL samples, with a Rouge-L decontamination filter.
- **GenLeaf** **reverse-engineers expert layouts into generator scripts with Bayesian optimization**.
- **FOARL** distils solver outputs, then uses RL to fix constraint violations, with Best-of-N at inference.
- **OptiScene** generates about 17K layouts by "GPT synthesize, Human inspect" and builds DPO negatives by injecting violations.
- **kicad-tools** shows the PCB version of perturbation data: calibrate Gaussian jitter per board to a 20–60% route-pass rate, add negative controls, and use leave-one-board-out CV.

### Cited Findings
- **CodeV-R1** (NeurIPS'25), read in full:
  - **Round trip:**
    1. Code→NL with DeepSeek-V3 over GitHub Verilog, about **150K** samples.
    2. NL→thought+code with DeepSeek-R1.
    3. Keep only examples where baseline Qwen2.5-Coder-7B/32B fail.
    4. Require equivalence with the original by the auto testbench, plus Yosys synthesizability.
    5. Remove samples with Rouge-L > 0.5 to VerilogEval and RTLLM, which leaves **87K** SFT samples.
  - **RL set:** examples the distilled model solves 5/5 are dropped, leaving **3.1K** RL examples. Training uses adaptive DAPO with about 1.25× acceleration.
  - **Testbench quality:** the rule-based testbench has "96.1% fewer false negatives than the LLM-generated counterpart and detects 62.5% more injected errors".
  **[P]** — [arXiv 2505.24183](https://arxiv.org/abs/2505.24183)
- **GenLeaf** (ICML'26): "there have been many expert-designed leaf cell layouts but no corresponding scripts… we propose a Bayesian Optimization (BO) based dataset preparation method to align layouts and scripts". BO searches script parameters until the generated layout matches the expert's metrics and embedding. Its output, "BO-Generated Golden Scripts", feeds SFT. **[P]** — [GenLeaf PDF](https://yhhan.com/PDFs/GenLeaf_paper.pdf)
- **FOARL** (NeurIPS'25), read in full:
  - **SFT data:** solutions from domain solvers (LKH-3 for TSP and others) written as "text-attributed instances" that include KD-tree top-2 nearest neighbours.
  - **Feasibility reward:** `R_f = ω0·ζ + Σ ωi·c_i`, where ζ is format validity and c_i are per-constraint indicators (TSP: ω = 0.2 / 0.5 / 0.3).
  - **Optimality reward:** `R_o = α/(1+M_o)`. GRPO uses the group advantage, and **Best-of-N** sampling is used at inference.
  - **Findings:** "SFT alone leads to over-greedy behavior… where LLMs violate constraints". GPT-4o and Claude-3.5 reach "only around a 50% feasibility rate on CO problems with fewer than 30 nodes".
  **[P]** — [arXiv 2509.16865](https://arxiv.org/abs/2509.16865)
- **OptiScene:** 3D-SynthPlace, about 17,000 scenes; SFT then multi-turn DPO. **[P]** — [arXiv 2506.07570](https://arxiv.org/abs/2506.07570)
- **GeoSVG-RL:** synthetic SFT warm start, then GRPO against a rendered verifier with six reward terms. **[P]** — [arXiv 2605.25447](https://arxiv.org/abs/2605.25447) [preprint]
- **kicad-tools perturbation corpus** (learned figure-of-merit, phase 0):
  - **Perturbation:** per board, Gaussian (x, y) jitter with σ from 1.0 to 4.0 mm plus ±90° rotation with probability 0.05–0.30. Connectors, mounting holes and test points are left alone.
  - **Calibration:** σ is "hand-calibrated… to land each board near a 20–60% pass rate". A flat σ = 6 mm gave 0% pass everywhere.
  - **Labels:** route within 45 s with zero DRC errors.
  - **Features:** 20 placement-only features, including `decoupling_proximity_median`.
  - **Validation:** `GroupKFold` by board, which is "the only defensible CV strategy". Negative controls (edge violation, overlap pile, σ = 20 mm) "verify… the model is [not] learning 'committed-by-human != perturbed-by-script'".
  - **Result:** global out-of-fold AUC **0.919** on **131 samples (32 positive)**, but precision at p > 0.8 was only 0.67 (n=6).
  **[P][3P-unreviewed]** — [learned_fom_phase0.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/learned_fom_phase0.md); [metrics.json](https://github.com/rjwalters/kicad-tools/blob/main/data/research/fom_phase0/metrics.json)
- **circuit-skills synthetic negatives** come from *human* placements: swap 25% or 100% of same-footprint interchangeable parts. These stay legal but have worse wiring, so they make good hard negatives. **[P][3P-unreviewed]** — [score_study.py](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/score_study.py)
- **Simulator-Refined Diffusion** for RF PCB layouts mixes a differentiable surrogate with a full-wave simulator during sampling, getting up to 21.2% closer to targets. **[P]** — [arXiv 2609.38363](https://arxiv.org/abs/2609.38363) [preprint]
- **DeepPCB** warns that simulator-legal but EDA-illegal patterns get learned, and that "novel" strategies may be reward loopholes. **[P]** — [DeepPCB blog](https://deeppcb.ai/reinforcement-learning-pcb-routing-explained/)

### Inferences
**Recommended synthetic-data generators for a KiCad project, in order of value:**
1. **Round-trip constraint extraction (GenLeaf/CodeV-R1 analogue).**
   - Take a human board and extract a candidate constraint graph (relative offsets, rotations, sides, grouping, edges).
   - Re-solve with the project's placer, then route.
   - Keep the pair only if the outcome matches or beats the human board (completion, DRC, HPWL ratio).
   - If it fails, run BO over constraint weights and tolerances to find the set that reproduces the human result.
   - Decontaminate against evaluation boards by footprint-set or WL-hash similarity.
2. **Hard negatives from human boards:** interchangeable-part swaps (circuit-skills), plus σ-calibrated jitter with σ tuned to a 20–60% pass rate (kicad-tools). These yield DPO or ranker pairs labelled by actual routing outcome.
3. **Difficulty filtering** (CodeV-R1, VeriReason): drop tasks the current model always or never solves before RL.
4. **Solver distillation with a feasibility RL stage** (FOARL), plus Best-of-N with a DRC/router verifier at inference.
5. **Procedural constraint boards** (PCBWorld D1/D2-style) for reward-function unit tests.

### Gaps
- No PCB paper implements round-trip constraint extraction. The hint study (Q2) suggests the extracted constraints must be finer than anchors and "near" relations.
- The circuit-skills and kicad-tools results are small and non-peer-reviewed: 52–64 boards and 7 boards respectively.

---

## Q5. Fine-tuning LLMs for EDA layout: SFT recipes, RL with verifiable rewards, preference learning, reward design, solver distillation

### Takeaway
The validated recipe is **representation first, then SFT on verified pairs, then group RL (GRPO/DAPO) with shaped executable rewards and difficulty filtering, with DPO as a hacking-resistant alternative**.

- **Representation dominates.** In SchGen, a relative-offset, pin-name code representation reached **82% valid circuits versus 32% when the same model emits raw KiCad files**. GPT-5.2 emitting raw KiCad reached 10.5%.
- **Reward shaping is simple and tiered.** VeriReason: 2.0 if the testbench passes, 0.1 + AST similarity if the code parses, 0 otherwise. Prompts are kept only if their mean reward is in [0.3, 1.8] with variance ≥ 0.1.
- **Layout-specific results:**
  - ModuPlace (7B, 426 SFT graphs; GRPO 36 samples in groups of 4; GNN ranker trained on expert rankings);
  - GenLeaf (14B; groups of 5 from 20; beats expert golden layouts on tracks by 48%);
  - spatial RLVR with dense IoU, center-distance and collision rewards (3D-Layout-R1: +15% IoU and −25% center error vs CoT-SFT and vanilla GRPO).

### Cited Findings

**Representation.**
- **SchGen:** "our APIs use local coordinate systems with relative offsets from anchor components and connect wires by semantic pin names (e.g., VCC, TXD) rather than absolute coordinates". Setup: GPT-oss-20B + LoRA SFT with distilled CoT.

  | Configuration | Valid circuits | Functional correctness (expert check) | Netlist Jaccard |
  |---|---|---|---|
  | Code-L1 (relative/semantic) | **82.0%** | 60.5% | 49.1 |
  | Same model, raw KiCad files | **32.5%** | 3% | 9.1 |
  | Code-L1 without CoT | 53.4% | 14% | — |
  | Vanilla GPT-oss | 11.0% | — | — |
  | GPT-5.2, Code-L1 prompt | 67.9% | — | — |
  | GPT-5.2, raw KiCad text | 10.5% | — | 0.53 |

  On the unseen GitHub set: SchGen 65.6% valid vs GPT-5.2 77.0%, but fewer overlaps (7.46 vs 12.12) and equal Jaccard (40.65 vs 40.64). The authors also observed that large models "often use relative coordinates… even if the prompt example code does not adopt them". **[P]** — [arXiv 2605.30345](https://arxiv.org/abs/2605.30345) [preprint]
- **LaMAGIC** (analog topology LM, SFT) finds that output formulation matters. Its adjacency-matrix formulation reaches up to 96% success at tolerance 0.01. **[P]** — [arXiv 2407.18269](https://arxiv.org/abs/2407.18269)
- **R³L** (3D layouts) finds that multi-hop relative relations "require repeated reference-frame transformations, which accumulate errors". Its fix is invariant decomposition, imagine-and-revise self-consistency, and "global-to-local coordinate re-parameterization". **[P]** — [arXiv 2605.06758](https://arxiv.org/abs/2605.06758) [preprint]

**Layout fine-tuning.**
- **ModuPlace:** Qwen-2.5-7B; "426 CCGs corresponding to expert-level placements" for SFT. GRPO generates "36 CCGs for each input… each group… 4 CCGs". The ranking comes from "a graph neural network, trained on ranking data from human expert feedback… inputs are two distinct CCGs", because "manual scoring of placements may lead to instability". **[P]** — [ModuPlace PDF](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
- **GenLeaf:** Qwen3-14B with SFT and GRPO. The advantage combines tracks, wirelength and vias with embedding similarity to the golden layouts. Across 14 industrial cases the ratios are 0.52× tracks, 0.96× wirelength and 1.01× vias versus the experts. Baselines include GPT-4o and Claude Sonnet 4. **[P]** — [GenLeaf PDF](https://yhhan.com/PDFs/GenLeaf_paper.pdf)
- **ACDC:** fine-tuned LLMs placing analog devices directly show "sensitivity to data format, instability… limited generalization". **[P]** — [arXiv 2512.09199](https://arxiv.org/abs/2512.09199) [preprint]

**RL with verifiable rewards and preferences (HDL).**
- **VeriReason**, read in full:
  - **Reward:** `R = 2.0` if functionally correct; `R = 0.1 + 1.0·AST_score` if only syntactically correct; 0 otherwise.
  - **Sample filter:** keep prompts whose group mean reward lies in [α_min = 0.3, α_max = 1.8] and whose reward variance is ≥ 0.1. This excludes samples "either too difficult… or too trivial".
  - **Results:** 83.1% on VerilogEval-Machine and up to 2.8× better first-attempt correctness.
  **[P]** — [arXiv 2505.11849](https://arxiv.org/abs/2505.11849)
- **CodeV-R1-7B:** 68.6% on VerilogEval v2 and 72.9% on RTLLM v1.1 via distill-then-RL (funnel in Q4). **[P]** — [arXiv 2505.24183](https://arxiv.org/abs/2505.24183)
- **VeriPrefer:** "The code that passes more testcases is considered as preferred". DPO was chosen because "reward-based RL is prone to reward hacking". **[P]** — [arXiv 2504.15804](https://arxiv.org/abs/2504.15804) [preprint]
- **FOARL:** a feasibility reward as a weighted sum of per-constraint indicators, plus an optimality reward and Best-of-N (see Q4). **[P]** — [arXiv 2509.16865](https://arxiv.org/abs/2509.16865)

**Spatial and layout RLVR.**
- **3D-Layout-R1:** GRPO with structured scene-graph reasoning gives "an average 15% improvement in IoU and 25% reduction in center-distance error compared to CoT-SFT and vanilla GRPO baselines". **[P]** — [arXiv 2603.22279](https://arxiv.org/abs/2603.22279) [preprint]
- **SR-ReaL:** cold-start SFT, then RL with accuracy and format rewards plus a "discrete center-based detection reward". It finds that "high-quality, blended cold-start data is crucial for stable RL". **[P]** — [arXiv 2606.17539](https://arxiv.org/abs/2606.17539) [preprint]
- **AesthetiQ:** DPO with MLLM-judge preference pairs and heuristic data filtering, +17% / +16% on Crello / WebUI. **[P]** — [arXiv 2503.00591](https://arxiv.org/abs/2503.00591)

### Inferences
- **Output representation for a KiCad LLM:** a placement or constraint DSL in **anchor-relative coordinates with pin-name references**. Keep relation chains shallow, anchored directly to IC or module frames (R³L), and never use raw `.kicad_pcb` S-expressions (SchGen's 32% vs 82%).
- **Reward template** (VeriReason/FOARL style):
  - **R = 0** if the output fails to parse or apply.
  - **R = 0.1 + 0.4·legality** if it parses, where legality is the fraction of hard-constraint indicators satisfied (overlap, outline, keepouts, error-level DRC).
  - **R = 1.0 + completion + optimality** if legal, where completion is routed fraction under a bounded Freerouting/KRT budget and optimality is `α/(1+HPWL-ratio)` or similar.
  - **Optional + β·ranker** term from a pairwise GNN trained on human-vs-perturbed and expert pairs.
  - Filter prompts by group mean and variance.
  - Use **DPO** on (better-routing, worse-routing) pairs where reward hacking is a concern.
- **Scale guidance from the literature:** expert-level SFT sets of hundreds (426 CCGs) to thousands (2,105 schematics) are enough for a 7–20B LoRA when the representation is right. RL sets of a few thousand hard prompts (3.1K) are enough.

### Gaps
- No public weights or data exist for ModuPlace's CCG model or expert ranking set, and the ranking-set size was not found in the text.
- No study applies GRPO to LLM *routing* outputs for PCBs.

---

## Q6. Evaluation of learned priors vs hand-coded rules: what evidence exists for PCB?

### Takeaway
New third-party PCB evidence (small, non-peer-reviewed) agrees with the literature: **learned combinations rarely beat simple hand-coded signals on small corpora, and the ground truth that matters (does it route cleanly?) is best obtained by actually routing**.
- **kicad-tools:** a fitted pairwise ranker over 10 pre-route signals did **not** beat plain HPWL (0.743 vs 0.749 leave-one-board-out; 0.603 vs 0.698 once perturbation size is controlled). The project adopted a bounded real route as its acceptance gate.
- **circuit-skills:** a fitted combination reached **0.79 held-out pairwise accuracy** across 64 boards, versus ≤ 0.72 for any single measure. Decap distance and crossings carried weight, so learning helps once the corpus spans many boards and placement *styles*.
- **Published systems:** ModuPlace and GenLeaf show learned constraint generation beating zero-shot LLMs and even experts on some metrics. GeniusRoute-style imitation is judged biased. DevFormer wins through inductive bias rather than data volume.

### Cited Findings
- **kicad-tools placement-score calibration** (two corpora, read in full):
  - **Corpus A:** 2 usable boards, 915 pairs. The best single signal was optimizer cost at 0.672 pairwise; the fitted combination scored 0.586 leave-one-board-out.
  - **Corpus B:** 6 boards, 85 placements, 370 pairs. HPWL scored **0.749** (0.795 on completion-decided pairs, 0.698 on same-σ pairs). The fitted RankNet-style logistic over 10 signals scored **0.743**, falling to **0.603 on same-σ pairs**. RUDY congestion was "at or near chance" (0.46–0.57).
  - "The perturbation sigma alone ranks 0.739 of all pairs", so much apparent signal is shake size.
  - "A fitted combination never beats the best fixed signal of its own corpus, out of sample."
  - Decision: "do not adopt a calibrated pre-route score… Use a bounded real route instead."
  **[P][3P-unreviewed]** — [placement_score_calibration.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/placement_score_calibration.md)
- **kicad-tools soft-FOM weight calibration.** It treats the *committed* placement as preferred over 40 jittered alternatives (σ = 2.5 mm). Tuned weights reach holdout rank consistency **0.875** (diffpair 0.975, matchgroup 0.775) and beat uniform weights on 7/7 boards. Low-variance terms (crossing count) transfer across boards; high-variance terms (diff-pair margin, compactness) are board-specific. The committed boards are the project's own and partly agent-made. **[P][3P-unreviewed]** — [fom_calibration.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/fom_calibration.md)
- **circuit-skills score study** (64 boards, 440 informative pairs):
  - **Single measures:** congestion_max 0.72, placement_drv 0.70, over_capacity_pct 0.70, decap_mm 0.60 (0.75 on legal-only pairs), crossings 0.60 (0.85 legal-only), MST length 0.51 (0.84 legal-only).
  - **Combined logistic:** "Held-out pairwise accuracy, 5 folds split by board: **0.79**". Weights per log(1+measure): over_capacity_pct +2.41, crossings_per_net +1.29, **decap_mm +1.24**, congestion_max +0.73, off_board_pads +0.23.
  - kicad-tools quotes an earlier self-reported 0.89 from this project; the committed file at `34e3841` reports 0.79.
  **[P][3P-unreviewed]** — [score_study.md](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/score_study.md); [circuit-skills-evaluation.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/circuit-skills-evaluation.md)
- **Hint study:** coarse human-derived constraints give 0.19–0.21 clean vs 0.15 with none and 0.63 for the designer (see Q2). **[P][3P-unreviewed]** — [hints_study.md](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/hints_study.md)
- **ModuPlace** ablations (without SFT +35.1% wirelength; without GRPO +25.4%) and zero-shot GPT-4o/Claude-3.5 underperformance: see `placement_algorithms.md`. **GenLeaf** beats golden layouts on tracks. **[P]** — [ModuPlace](https://yhhan.com/PDFs/ModuPlace_paper.pdf); [GenLeaf](https://yhhan.com/PDFs/GenLeaf_paper.pdf)
- **Lim 2026:** RL beats human TEWL on simple subcircuits but TEWL misses overlaps and conflicts. Metric choice decides "learned beats human". **[P]** — [arXiv 2602.23540](https://arxiv.org/abs/2602.23540)
- **DeepPCB:** "If you haven't explicitly specified a constraint, the model won't respect it… confidence doesn't correlate reliably with correctness." **[P]** — [DeepPCB blog](https://deeppcb.ai/reinforcement-learning-pcb-routing-explained/)
- **DevFormer:** 100 samples with symmetry biases beat baselines trained on 2,000. **[P]** — [arXiv 2205.13225](https://arxiv.org/abs/2205.13225)

### Inferences
- **Practical rule.** Use hand-coded signals (HPWL, crossings, decap distance, congestion) as features, and the **router as the label oracle**. Fit learned rankers only when the corpus spans at least tens of boards *and* diverse placement styles (designer, swaps, several placers), with board-grouped CV and perturbation-size controls. Otherwise the fit learns shake size.
- **Report learned-vs-rules A/B on the same solver:** (a) rules-only soft constraints, (b) corpus-percentile priors, (c) learned relative-pose model, (d) LLM constraint graphs (SFT/GRPO), each scored by clean-route rate and HPWL versus the designer on held-out boards. The circuit-skills harness (designer, swap, auto placements; TraceMaker; KiCad DRC) is a ready template.

### Gaps
- No peer-reviewed PCB study of learned versus rule priors exists. The two third-party studies use 52–64 and 2–7 boards respectively.
- The 0.79 vs 0.89 circuit-skills discrepancy is attributed to the version history only by inference.

---

## Q7. Risks: dataset contamination, license compliance (GPL / CC-BY-SA / CERN-OHL), and bias toward hobbyist practice

### Takeaway
- **Contamination is demonstrated for hardware benchmarks:** about 100% for GPT-3.5 and GPT-4o on VerilogEval and RTLLM under CDD. Popular open boards are near-certainly in pretraining crawls.
- **Licensing is a first-order design constraint:**
  - PCBench is 62% unlicensed, and about 40% of sampled kicad-happy repos lack a licence file.
  - **CERN-OHL-S §3.2 says "Including Covered Source in a larger work is modifying the Covered Source, and the larger work becomes modified Covered Source"**, so copying a reciprocal fragment's layout into a user's board plausibly triggers reciprocity.
  - Whether model *training* is covered is unaddressed. §2.4 preserves fair use and fair dealing.
- **Hobbyist bias is quantifiable.** Corpus decap distances are looser than common guidance (17% within 2 mm), and 2-layer boards have a 26 mm p90 tail.

### Cited Findings

**Contamination.**
- **VeriContaminated:** "Our analysis of LLM data contamination across VerilogEval and RTLLM benchmarks shows **near 100% rates in GPT-3.5 and GPT-4o**, but lower in older models". CDD α = 0.05 and Min-K% threshold 0.55. "GPT-3.5 and GPT-4o exhibit nearly 100% contamination, which explains their superior performance." **[P]** — [arXiv 2503.13572](https://arxiv.org/abs/2503.13572)
- **CodeV-R1's decontamination practice:** drop training samples with Rouge-L > 0.5 to any evaluation benchmark. **[P]** — [arXiv 2505.24183](https://arxiv.org/abs/2505.24183). LiveVerilogEval (DATE'26) proposes a contamination-free benchmark. **[S]** — [PDF](https://past.date-conference.com/proceedings-archive/2026/DATA/167.pdf)

**Licensing.**
- **CERN-OHL-S v2 text:**
  - §1.5 "Product" means "any device, component, work or physical object… arising from the use, application or processing of Covered Source".
  - §2.4 "This Licence is not intended to restrict fair use, fair dealing, or any other similar right."
  - §3.2: "Including Covered Source in a larger work is modifying the Covered Source, and the larger work becomes modified Covered Source." Modified Covered Source must be made available "should You Convey a Product".
  - §4: conveying Products requires providing or pointing to the Complete Source.
  **[P]** — [CERN-OHL-S-2.0 (SPDX text)](https://raw.githubusercontent.com/spdx/license-list-data/main/text/CERN-OHL-S-2.0.txt)
- **KiCad 9+ corpus legal split:** CC-BY-SA-4.0 is "one-way compatible *to* GPLv3 only". The copyleft subset was relicensed GPL-3.0-or-later, with the dataset author asserting that trained models carry GPL obligations (their interpretation). **[P]** — [kicad9plus-copyleft](https://huggingface.co/datasets/electron-rare/kicad9plus-copyleft)
- **The Stack:** a permissive-only subset matched HumanEval and MBPP performance, "near-deduplicating the data significantly boosts performance", and it offers an opt-out tool. **[P]** — [arXiv 2211.15533](https://arxiv.org/abs/2211.15533)
- **Measured licence mixes [M]:**
  - PCBench: 62% unclear, 19% permissive, 18% reciprocal (Q1);
  - kicad-happy sample: 41% no licence file, 37% permissive, 22% reciprocal;
  - circuit-skills licensed corpus: 235 boards, 46% reciprocal (107: GPL-3 67, CERN-OHL-S 25, CC-BY-SA 10, CERN-OHL-W 5) and 54% permissive (128).
- **Practitioner precedent:** circuit-skills and kicad-tools both fetch boards at pinned SHAs into caches and "never into the repo", recording per-board licences. kicad-tools treats unlicensed repos as "ideas only" and re-states findings without copying code. **[P][3P-unreviewed]** — [collect.py](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/collect.py); [circuit-skills-evaluation.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/circuit-skills-evaluation.md)
- **PCB layout copyright:**
  - Taiwan treats a drawn PCB layout as a protectable graphical work **[S]** — [Lee and Li](https://www.leeandli.com/EN/Newsletters/3149.htm).
  - Singapore litigated PCB artwork in *Real Electronics v Nimrod* **[S]** — [vLex](https://sg.vlex.com/vid/real-electronics-industries-singapore-842804218).
  - The US SCPA mask-work regime covers chips, not boards. **[S]**
- open-schematics is CC-BY-4.0 at the dataset level over mixed-licence sources (licence-laundering risk). **[P]** — [card](https://huggingface.co/datasets/bshada/open-schematics)

**Hobbyist bias.**
- **kicad-happy author:** corpus biased toward "ESP32 dev boards and mechanical keyboards… simple power supplies"; RF, precision analog and complex power are under-represented. **[P]** — [methodology.md](https://github.com/aklofas/kicad-happy-testharness/blob/main/methodology.md)
- **[M]** 63% of kicad-happy PCB repos are 2-layer and 89% of PCBench boards are 2-layer. Decap distance p90 is 26 mm on 2-layer boards versus 7.7 mm on 4-layer boards. Only 33% of licensed, fully routed circuit-skills boards are DRC-clean at error level under their own rules.

### Inferences
**Licence tiers and uses:**

| Tier | Licences | Allowed uses |
|---|---|---|
| A | MIT, Apache, BSD, CC0, CERN-OHL-P, CC-BY | training, redistributed derived data (with attribution), retrieval that copies geometry |
| B | GPL, CERN-OHL-S/W, CC-BY-SA, TAPR | (i) evaluation; (ii) retrieval that shows the fragment with licence and attribution, where copying geometry into a user board is flagged as making the board a derivative; (iii) training only with counsel's sign-off, and never in redistributed weights by default |
| C | no licence, NC, ND | private evaluation only, fetched at pinned SHA, never redistributed |

- **Prefer "facts" over "expression" in training targets.** Aggregate statistics (decap percentiles per package, width ratios) and abstract constraint graphs are far less likely to carry copyright or reciprocal obligations than verbatim fragment geometry. This is my inference, not legal advice.
- **Contamination control:**
  - Time-split held-out boards committed after the base model's cutoff, plus private boards.
  - Cluster-split by footprint-set or WL-hash similarity.
  - Apply a CodeV-R1-style similarity filter between training fragments and evaluation boards.
  - Report results on popular and obscure splits separately.
- **Bias control:** condition all priors on layer count, package and board class, and weight professional sources and DRC-clean boards.

### Gaps
- No legal analysis was found of ML training on CERN-OHL, GPL or CC-BY-SA *hardware*, or of whether model weights are a CERN-OHL "Product". Counsel is needed.
- No contamination study exists for PCB layout benchmarks.

---

## Q8. Implications for an LLM-driven KiCad placer/router: a concrete data strategy (what to scrape, how to clean and label, what to train first, how to evaluate)

### Takeaway
1. **Build a pinned, licence-tiered corpus** using circuit-skills-style qualification: opens in KiCad, fully routed, own rules, DRC recorded.
2. **Ship corpus-derived priors and retrieval first** (no training).
3. **Then train in this order:**
   - a DevFormer-style relative-pose and assignment model;
   - a round-trip-verified constraint-graph SFT for a 7–20B LLM using an anchor-relative DSL;
   - GRPO with tiered, executable rewards, using DPO where hacking appears.
4. **Use the router as the label oracle throughout.**
5. **Evaluate** on time- and cluster-split held-out boards with designer, swap and auto baselines, and a rules-only versus learned A/B.

### Cited Findings (evidence underpinning the plan)
- **Qualification recipe and yields** (pinned SHA, licence allow-list, `.kicad_pro` present, no unconnected items, own-rule DRC recorded; 235 boards from 423 candidates; 33% DRC-clean). **[P][3P-unreviewed]** — [collect.py](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/collect.py); [manifest.json](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/manifest.json)
- **Legacy-format and rule-adoption pitfalls:** 41% legacy `(module …)` in one sample; pours count as copper; adopt each board's own rules. **[P][3P-unreviewed]** — [corpus-benchmark-feasibility.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/corpus-benchmark-feasibility.md)
- **Representation evidence:** SchGen relative/pin-name code 82% vs raw KiCad 32%. **[P]** — [arXiv 2605.30345](https://arxiv.org/abs/2605.30345)
- **Recipes:**
  - ModuPlace: 426 SFT; GRPO 36/4; expert-rank GNN. **[P]** — [ModuPlace](https://yhhan.com/PDFs/ModuPlace_paper.pdf)
  - GenLeaf: BO reverse-engineering. **[P]** — [GenLeaf](https://yhhan.com/PDFs/GenLeaf_paper.pdf)
  - CodeV-R1: 150K→87K→3.1K. **[P]** — [arXiv 2505.24183](https://arxiv.org/abs/2505.24183)
  - VeriReason: tiered reward and variance filter. **[P]** — [arXiv 2505.11849](https://arxiv.org/abs/2505.11849)
  - FOARL: feasibility RL and Best-of-N. **[P]** — [arXiv 2509.16865](https://arxiv.org/abs/2509.16865)
- **Evaluation evidence:**
  - Learned scores do not beat HPWL on small corpora, so use a bounded real route. **[P]** — [placement_score_calibration.md](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/placement_score_calibration.md)
  - Designer 0.56 vs auto 0.12–0.16 clean. **[P]** — [score_study.md](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/score_study.md)
- **Measured priors [M]:**
  - 0402 decap median 2.5 mm, 4-layer p90 7.7 mm;
  - power/signal width ratio 1.88;
  - 89% of boards have a GND zone.

### Inferences (concrete plan; my synthesis)

**1. Scrape (target: about 2–5k licence-clear, fully routed boards; about 500–1,000 DRC-clean; about 300–800 4+-layer).**
- **Discovery:** kicad-happy `repos.md` (5,822 pinned), open-schematics `name` field, circuit-skills-style GitHub queries (topics kicad, kicad-pcb, oshw, open-hardware; language "KiCad Layout"), PCBench sources (842 repos, but 62% unlicensed), OSHWA list, plus Adafruit and SparkFun Eagle via KiCad's importer (log conversion DRC separately).
- **Store:** pointers plus SHA-256 only in-repo; payloads in a git-ignored cache.

**2. Manifest and licence tiers.**
- **Fields:** `repo, sha, path, blob, spdx (LICENSE + README + scancode), tier, kicad_version, layers, parts, pads, connections, ref_drv (own rules, error severity), bare_drv, ref_open, has_pro/dru, stars, first_commit_date, category`.
- **Tier usage:** tier A for training, B for retrieval-with-attribution and eval, C for private eval only. Keep an opt-out list.

**3. Clean and qualify.**
- **Format:** `kicad-cli pcb upgrade`; refuse, rather than half-parse, legacy constructs your parser doesn't handle.
- **Routing:** require `ref_open == 0` for routing-imitation data. Keep `ref_drv` as a quality weight rather than a hard filter, or the corpus shrinks about 3×.
- **Dedup:** dedup by git blob and cluster by footprint-multiset Jaccard plus netlist WL hash. Keep at most 2 boards per repo (circuit-skills default).
- **Rules:** adopt each board's own `(setup …)` and `.kicad_dru` rules when scoring against the human.

**4. Label automatically (data products).**
- (i) **Subcircuit instances** from rule detectors plus WL/gSpan motif mining over the PCB netlist. Use the PCB, not per-sheet schematics, to avoid cross-sheet blind spots.
- (ii) **Relative pose tables** per (anchor package, pin function, satellite package): Δx, Δy, Δθ, side and pad-to-pad distance. Publish percentiles conditioned on layer count and tier (the decap measurement above is a prototype).
- (iii) **Routing-style tables:** width by net function, plane usage, via counts, diff-pair spacing.
- (iv) **Module partition and module-to-edge graphs.**
- (v) **Round-trip-verified constraint graphs** in an anchor-relative DSL (Q4 generator 1).
- (vi) **Outcome-labelled placement sets** per board: designer, swap25, swap100, σ-calibrated jitter and auto placers, each routed under a fixed budget and DRC-judged. These serve as ranker and DPO data and as a benchmark.

**5. Train, in order.**
- **Step 0, no training:** retrieval (WL filter, GNN rerank, max-weight-clique fragment selection) plus prior tables as soft constraints for the solver. The LLM cites the fragments and their licences.
- **Step 1, small models:**
  - a DevFormer-style relative-pose and **assignment** model for satellites around anchors (swap sensitivity shows assignment matters);
  - a pairwise ranker on (vi) with board-grouped CV and σ controls, used only as a tie-breaker or β-term, never as the acceptance gate.
- **Step 2, LLM SFT** (7–20B, LoRA, distilled CoT): netlist plus board context in, anchor-relative constraint DSL out (SchGen-style representation), trained on (v). Decontaminate against eval clusters.
- **Step 3, GRPO/DAPO:**
  - **Tiered reward:** parse → legality fraction → completion and optimality, with a +β ranker term.
  - **Prompt filter:** VeriReason mean and variance filter, CodeV-R1 difficulty filter.
  - **Group size:** 4–5 of 16–36 samples per input.
  - **Inference:** Best-of-N with the router/DRC verifier.
- **Step 4, preferences:** a few hundred expert A/B rankings to train a ModuPlace-style ranker or DPO. Switch to DPO if reward hacking appears (VeriPrefer).

**6. Evaluate.**
- **Splits:** time-split (first commit after the model cutoff), cluster-split, private boards, and strata by layers and tier.
- **Baselines:** designer placement, swap25/swap100, rules-only constraints with the same solver, existing auto placers, and frontier LLMs zero-shot.
- **Metrics:** clean-route rate and connections routed under a fixed router budget, error-level DRC, HPWL and via ratio vs designer, prior-table compliance, and a blind expert preference subset.
- **Ablations:** rules vs corpus priors vs learned pose model vs LLM constraint graphs; retrieval on/off; SFT vs +GRPO.
- **Contamination probes:** Min-K%-style tests on test-board fragments, and popular vs obscure splits.

### Gaps
- Yield estimates extrapolate from the PCBench, circuit-skills, kicad-happy and kicad-tools samples. A full pipeline run is needed.
- No precedent exists for the round-trip "equivalence" tolerance on PCB placements. It must be calibrated, for example "routes clean within budget and HPWL ≤ 1.1× designer".
- How much expert preference data a PCB ranker needs is unknown.
