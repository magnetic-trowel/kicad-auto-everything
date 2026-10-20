# Circuit Understanding for Layout Intent: Netlist + Schematic + Datasheet → Semantically Annotated Design

> Scope: front end of an LLM-driven KiCad placement+routing system — recognizing functional blocks, classifying nets, extracting layout constraints from datasheets/app notes, and capturing designer intent in KiCad.
>
> **Method note (read first).** In this session, the shared web-search budget ran out after about 20 queries. Direct page fetches were also blocked by the egress proxy for almost every host: arXiv, IEEE, ACM, docs.kicad.org, ti.com, flux.ai, quilter.ai, celus.io, digikey.com, nexar.com and huggingface.co all failed. **Only raw.githubusercontent.com was reachable.** As a result:
> (a) primary GitHub sources (READMEs, docs and source code) were read in full;
> (b) paper findings come from search-engine summaries of the arXiv/IEEE pages and were **not** read in full;
> (c) where only an aggregator was found, it is flagged.
> All arXiv items are **preprints** unless a venue is named. Dates are as of 2026-10-20.

---

## 1. Subcircuit / structure recognition from netlists (graph matching, GNNs, rules, LLMs) and reported accuracy

### Takeaway
There are four recognition approaches, and they have different strengths:
- **Template subgraph matching (VF2)** is exact and fast on known topologies.
- **GNNs** handle structural variants (GANA/ALIGN, analog IC level).
- **Rule/heuristic detectors** over pin names plus neighbour types are the most mature approach at *board level* (kicad-happy: 60+ detectors tested on ~5,800 KiCad projects).
- **Pure LLM netlist reading** is unreliable on topology. GENIE-ASI reaches F1 1.0 on simple structures but only 0.31 on complex subcircuits, and on the CIRCUIT benchmark the best model scores 48%.

The strongest pattern so far is "the LLM writes detector code, and that code executes deterministically" (GENIE-ASI), or "deterministic detectors, with the LLM reasoning on top of them" (kicad-happy).

### Cited Findings

**Graph/template matching (deterministic)**
- ALIGN (an open-source analog layout generator from DARPA IDEA, built by UMN, Texas A&M and Intel) starts with a *circuit annotation* step. This step "creates a multilevel hierarchical representation of the input netlist", using a built-in template library (`basic_template.sp`) plus a user-extensible `user_template.sp` to "identify hierarchies in the design". Optional per-hierarchy constraint files are JSON (`<hierarchy>.const.json`). — [ALIGN-public README](https://github.com/ALIGN-analoglayout/ALIGN-public)
- ALIGN's subgraph matcher is NetworkX `GraphMatcher(...).subgraph_isomorphisms_iter()`. Node matching is by device model class (a library model must be in the instance's model-class bases), and edge matching is by **pin label** (`x.get('pin') == y.get('pin')`). Matches are sorted to remove non-determinism, overlapping matches are skipped, and a match is kept only if `check_constraint_satisfiability` passes. — [ALIGN align/schema/graph.py](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/master/align/schema/graph.py)
- NetworkX's `GraphMatcher` is its VF2 implementation. — [NetworkX VF2 docs](https://networkx.org/documentation/stable/reference/algorithms/isomorphism.vf2.html) (standard library fact; page not fetched this session)
- ALIGN constraint files use typed JSON records such as `{"constraint": "PowerPorts", "ports": ["VDD"]}` and `{"constraint": "GroundPorts", "ports": ["0"]}`. — [ALIGN telescopic_ota.const.json](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/master/examples/telescopic_ota/telescopic_ota.const.json)
- Hierarchical symmetry-constraint extraction (UMN, ICCAD 2020): a graph-based, hierarchical method that extracts multiple symmetry axes. Prior approaches handled only simple symmetries. — [arXiv 2010.00051 (ar5iv)](https://ar5iv.labs.arxiv.org/html/2010.00051)
- HiLSD (ASP-DAC 2004) pattern-matches subcircuits first and then looks for symmetry only inside those instances. This "significantly curtails the search-space and ignores all unintended axes of symmetry". — [HiLSD ASP-DAC'04](https://labs.ece.uw.edu/ssrl/workspace/iprail/web_IPRAIL/ASPDAC04_2.pdf)

**GNN-based recognition**
- GANA (Kunal et al., DATE 2020, pp. 55–60):
  - A trained GCN identifies netlist elements for blocks at the upper levels of the hierarchy. Lower-level structures are identified with graph-based algorithms.
  - It is motivated by the observation that "traditional graph-based methods cannot easily identify the large number of structural variants".
  - Recognition "organically detects layout constraints such as symmetry and matching".
  - It recognizes OTAs, LNAs, mixers, oscillators and band-pass filters.
  - Sources: [DATE 2020 proceedings](https://past.date-conference.com/proceedings-archive/2020/html/0921.html); [IEEE 9116329](https://ieeexplore.ieee.org/document/9116329)
- GANA's input format is an N×N adjacency matrix, an N×D node-feature matrix and an N×E binary label matrix. The released data covers OTA circuits converted from SPICE (`read_netlist.py`, then `preprocess_data.py`). — [GANA_circuit_data repo](https://github.com/kkunal1408/GANA_circuit_data)
- Journal extension: "GNN-Based Hierarchical Annotation for Analog Circuits", IEEE TCAD 2023, vol. 42, no. 9, pp. 2801–2814, covering "a variety of GNN strategies". — [DBLP entry](https://dblp.uni-trier.de/pid/241/4371.html); [UMN page](https://neurospin.umn.edu/gnn-based-hierarchical-annotation-analog-circuits)
- PCB-level graph learning:
  - A benchmark dataset frames **PCB netlist partitioning as graph node classification**: components are nodes, electrical connections are edges, and the stated use is tasks like functional recognition. — [PMC article](https://pmc.ncbi.nlm.nih.gov/articles/PMC13046837/)
  - Separately, arXiv 2506.10577 models PCB schematics as **bipartite graphs** (net nodes plus symbol nodes, with pins as edges) and uses GNNs to predict automatic addition of components. Preprint. — [arXiv 2506.10577](https://arxiv.org/pdf/2506.10577)

**Rule-based recognition at board level (most directly reusable)**
- kicad-happy (MIT, Python) works as follows:
  - It parses `.kicad_sch` S-expressions for KiCad 5–10 and walks hierarchical and multi-instance sheets.
  - It builds nets by **union-find on pin coordinates** (0.01 mm merge tolerance).
  - It then runs "60+ signal, domain, validation, and audit detectors", each "a pure function that looks for specific circuit patterns in the connectivity graph". Detectors include voltage dividers, RC/LC filters, regulators, transistor circuits, op-amp configurations, current sense, TVS/ESD mapped to the interfaces they protect, crystals with load caps, H-bridges, I2C/SPI/UART/CAN/RS-485, RF chains, Ethernet, HDMI, memory, BMS and more.
  - Detectors run in dependency order: dividers are found first, then regulators reference them.
  - Source: [kicad-happy how-it-works](https://github.com/aklofas/kicad-happy/blob/main/how-it-works.md)
- kicad-happy regulator recognition:
  - It scans IC pin names (normalized, with trailing digits stripped) for FB/ADJ/COMP, SW/BOOT/BST, VIN/VOUT, EN/SHDN, PG and SS.
  - Classification rules: **LDO** = FB plus ≥2 power pins and no SW/BOOT; **Switching** = SW+BOOT, or SW plus an inductor on the output net; **Charge pump** = BOOST and no FB.
  - False-positive guard: "An IC with SW but no inductor on the switch net and no regulator keywords… is NOT classified as a switching regulator" (to avoid motor drivers).
  - Vout = Vref×(1+Rtop/Rbot), using a 150+ entry Vref table, with a fallback to the voltage encoded in the net name (e.g., `+3V3`).
  - Source: [methodology_schematic.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_schematic.md)
- Other kicad-happy detector rules:
  - **Crystal**: a crystal's two non-power nets, each with a capacitor to ground.
  - **Decoupling**: capacitors directly between a power rail and ground, grouped per rail with capacitance summed.
  - **RC filter**: an R–C pair sharing exactly one non-power net; the type depends on which element goes to ground.
  - **Divider**: two resistors sharing a mid-node, with power at one end and ground or power at the other. It is rejected if the mid-node is a named rail with more than 4 pins.
  - Source: [methodology_schematic.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_schematic.md)
- kicad-happy design stance: "bugs produce *missing data*, not *wrong data*… it's better to miss a voltage divider than to report one that doesn't exist".
  - It is tested on a harness of **5,829 open-source KiCad projects** (KiCad 5–10) with baselines, assertions, and LLM review whose confirmed findings are promoted to assertions.
  - "Detection accuracy is harder to quantify — you can't count what you didn't catch."
  - Source: [kicad-happy how-it-works](https://github.com/aklofas/kicad-happy/blob/main/how-it-works.md)
  - Note that the detector count is inconsistent across docs: the README says "40 detectors total" in the domain row, while how-it-works says "60+". — [kicad-happy README](https://github.com/aklofas/kicad-happy)

**LLM-based netlist understanding and benchmarks**
- **GENIE-ASI** (MLCAD 2025; arXiv 2508.19393, with Sony AI involvement):
  - A training-free LLM method. First it derives natural-language instructions from a few examples, then it turns them into **Python code that identifies subcircuits in unseen SPICE netlists**.
  - It introduces a benchmark built from op-amp netlists.
  - Reported F1: **1.0 on simple structures** ("matching rule-based methods"), **0.81 on moderate abstractions** and **0.31 on complex subcircuits**.
  - Sources: [arXiv 2508.19393](https://arxiv.org/pdf/2508.19393); [Sony AI publication page](https://ai.sony/publications/genie-asi-generative-instruction-and-executable-code-for-analog-subcircuit-identification); [Sony MLCAD 2025 blog](https://ai.sony/blog/advancing-analog-design-with-ai-sony-ais-contributions-at-mlcad-2025)
  - The same Sony blog describes **Schemato**, a fine-tuned LLM that converts netlists into LTspice schematics. — [Sony blog](https://ai.sony/blog/advancing-analog-design-with-ai-sony-ais-contributions-at-mlcad-2025)
- **CIRCUIT** (arXiv 2502.07980, Feb 2025; preprint): 510 QA pairs on analog circuit interpretation. The best model, GPT-4o, reached **48.04%**, and models "struggled most with circuit topology understanding". — [arXiv 2502.07980](https://www.arxiv.org/pdf/2502.07980)
- **AMSbench** (arXiv 2505.24138; preprint): evaluates multimodal LLMs on analog/mixed-signal schematics, netlists and QA. Models do fairly well on textbook knowledge but poorly on industry-style performance trade-offs. — [arXiv 2505.24138](https://arxiv.org/pdf/2505.24138)
- **AITEE** (arXiv 2505.21582; preprint): evaluates circuit description from 24 hand-made netlists, scored 0–4 with GPT-4 as judge. — [arXiv 2505.21582](https://arxiv.org/pdf/2505.21582)
- **NetlistBench** (listed as arXiv 2608.12197): 2,342 cases across 24 task families (connectivity recognition, edits, equivalence judgment). Simple local edits score high, while device addition and equivalence judgment score noticeably lower. — **Aggregator only**: [tldr.takara.ai summary](https://tldr.takara.ai/p/2608.12197); primary paper not verified.
- **Masala-CHAI** (NYU; arXiv 2411.14299; preprint):
  - An LLM plus custom DNN pipeline (YOLO component detection and a Hough-transform model) that extracts SPICE netlists from schematic images. It covers about 7,500 schematics from 10 textbooks.
  - Fine-tuned models used inside AnalogCoder give a "46% improvement in Pass@1".
  - A May 2026 V2 adds a multi-agent pipeline: a component-validation agent, a connectivity/netlist agent that runs ngspice, and a judge allowed up to 2 revisions.
  - Sources: [Masala-CHAI repo README](https://github.com/jitendra-bhandari/Masala-CHAI); [arXiv 2411.14299](https://arxiv.org/abs/2411.14299v5)
- A data-quality audit by AnalogRetriever (arXiv 2604.23195; preprint) found that of Masala-CHAI's 6,371 schematic images, only 6,069 have paired netlists and captions, and the netlists needed LLM-based repair. — [arXiv 2604.23195](https://arxiv.org/pdf/2604.23195)
- **AnalogCoder** (AAAI 2025 oral): a training-free LLM agent that frames analog design as Python code generation and keeps a "circuit skill library" of reusable subcircuits.
  - It solved **20 of 24** benchmark tasks.
  - The README's leaderboard shows small open models with near-zero Pass@1 (e.g., Llama2-7B 0.0, Llama3-8B 0.1).
  - Source: [AnalogCoder repo](https://github.com/laiyao1/AnalogCoder); extended version AnalogCoder-Pro [arXiv 2508.02518](https://arxiv.org/abs/2508.02518)
- **PCB-Bench** (ICLR 2026):
  - About 3,700 text questions on placement and routing.
  - About 500 image+text problems, including "functional block recognition" and "differential-pair continuity analysis".
  - 174 real OSHWHub projects, where models describe board function from an EDA screenshot alone. Metrics are BERTScore/SBERT and P/R/F1.
  - Sources: [PCB-Bench project page](https://digailab.github.io/PCB-Bench/); [OpenReview](https://openreview.net/forum?id=Q5QLu7XTWx)
- Netlist→schematic and schematic→netlist conversion tools are related but separate problems: Netlistify (schematic image to netlist, validated by simulation) — [ResearchGate](https://www.researchgate.net/publication/396395178_Netlistify_Transforming_Circuit_Schematics_into_Netlists_with_Deep_Learning); Weave (verified netlist-to-schematic via layered graph layout; arXiv 2607.03835, preprint) — [arXiv 2607.03835](https://arxiv.org/pdf/2607.03835); AMSnet-KG (a netlist dataset with knowledge-graph RAG) — [ACM DL](https://dl.acm.org/doi/10.1145/3736166).

### Inferences
- **Board-level recognition is mostly a pin-name + neighbour-type problem, not a deep-topology problem.** A buck converter on a PCB is "IC with SW/BOOT/FB pins + inductor on SW + caps on VIN/VOUT + divider on FB". That is easy for rules, and the hard IC-level variants that motivated GANA mostly do not exist at board level, where the transistors sit inside the IC. GNNs are therefore a lower priority for a KiCad tool than (a) good part metadata and (b) a rule and template library.
- ALIGN's VF2 approach, which labels edges by pin role, carries over to PCBs if edges are labelled with **normalized pin roles** (SW, FB, VIN, PGND, XIN/XOUT, D+/D−) rather than pin numbers. A template like "buck_async = IC{SW,FB,VIN,GND} + L(SW,Vout) + D(SW,GND) + Cin(VIN,GND) + Cout(Vout,GND) + Rdiv(Vout,FB,GND)" becomes a small labelled-subgraph query.
- GENIE-ASI's F1 collapse (1.0 → 0.31) argues against letting an LLM free-read a whole netlist to decide block membership. It is better to have the LLM (i) write or extend detector templates, (ii) label ICs from MPN, datasheet and pin names, and (iii) adjudicate the leftovers that deterministic passes could not explain.
- Masala-CHAI V2 and kicad-happy share one pattern: an LLM proposes, a deterministic checker (ngspice, or the JSON netlist) verifies, and a judge loops. Block recognition should copy this. Every proposed block must explain all of its pins, and its members must be consistent with the graph.

### Gaps
- I found no published *quantitative* accuracy for board-level (PCB) functional-block recognition: no precision/recall for "buck detected", "crystal detected" and so on. kicad-happy explicitly declines to give one.
- I could not retrieve GANA's per-class accuracy numbers (the search budget ran out).
- I could not locate the specific papers the brief named as "CircuitBench" or "SPICED". They may exist under other names; this is not verified.
- The NetlistBench primary paper was not verified (aggregator only).

---

## 2. Net classification: diff pairs, power, clocks, high-speed — from names, pin metadata, and part data

### Takeaway
In practice (kicad-happy, KiCad itself), net roles come from three cheap signals: **power symbols and power-net naming**, **net-name keyword and suffix rules** (`+`/`-`, `_P`/`_N`, CLK, SDA…), and **pin names and types on the connected IC pins**.

KiCad's own diff-pair router depends on net-name suffixes, which must be the last character, so the naming convention is load-bearing. Data rate and impedance are *not* in KiCad metadata. They must be inferred from the IC's interface (via datasheet or LLM) and written back as net classes.

### Cited Findings
- **Power rails in kicad-happy** come from two methods:
  - Method 1, authoritative: any net with a pin from a `#PWR`/`#FLG` symbol.
  - Method 2, heuristic: exact names (VCC, VDD, AVDD, VBUS, VBAT, VIN, VOUT…), names starting with `+` (`+3V3`), `V`+digits (`V1V8`), and prefixes like `VDD_*`.
  - Ground = GND/VSS/AGND/DGND/PGND… or names starting or ending with GND.
  - Source: [methodology_schematic.md §7](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_schematic.md)
- **kicad-happy name-based net classes**, from a keyword table:

  | Class | Keywords |
  |---|---|
  | ground | GND/VSS |
  | power | VCC/VDD/+3V3/VBUS |
  | clock | SCL, SCK, CLK, MCLK, XTAL, OSC |
  | data | SDA, MOSI, MISO, UART, TX, RX |
  | high_speed | USB, CAN, LVDS, ETH |
  | analog | ADC, AIN, VREF, VSENSE |
  | control | RESET, NRST, EN |
  | chip_select | CS, SS, NSS, CE |
  | interrupt | INT, IRQ, ALERT, DRDY |
  | debug | SWD, JTAG, TCK |
  | config | BOOT, TEST |
  | signal | everything else |

  Diff-pair analysis covers USB D+/D-, CAN H/L and LVDS, with termination checks. Power-domain mapping separates IO rails (VDDIO, VIO, VCCA/VCCB) from core rails for cross-domain detection. — [methodology_schematic.md §10.2](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_schematic.md)
- **KiCad diff-pair recognition** is by net-name suffix: `+`/`-` (D+/D−) or `_P`/`_N` (or `P`/`N`).
  - The suffix must be the last character. A net whose name ends in a parenthesis was not paired.
  - Symbol *pin* names like `Pin_P` do not propagate, because auto-generated nets look like `Net-(J1-Pin_P)`, so explicit labels are needed.
  - Vector buses such as `DACD_P[0..15]` did not work with the pair router in an older thread.
  - Sources: [KiCad forum: suffixes](https://forum.kicad.info/t/differential-pair-doesnt-work-with-any-of-the-suffixes/26166); [KiCad forum: pin names](https://forum.kicad.info/t/differential-pair-defined-with-pin-names-in-symbol/41801); [KiCad forum: bus naming](https://forum.kicad.info/t/differential-bus-naming-and-pair-router/770); [DigiKey Maker USB diff-pair tutorial](https://www.digikey.com/en/maker/projects/how-to-route-differential-pairs-in-kicad-for-usb/45b99011f5d34879ae1831dce1f13e93)
- **False-positive hazard:** names like `XTAL_P`/`XTAL_N` make the interactive router apply diff-pair width and gap even to single-ended routing. Forum replies say this is by design and advise not using those suffixes on non-differential nets. — [KiCad forum thread](https://forum.kicad.info/t/kicad6-pcbnew-picks-wrong-trace-width-and-clearance-from-netclass/34007) (forum, not official docs)
- **KiCad pin electrical types** available as metadata: Bidirectional, Tri-state, Passive, Unspecified, Power input, Power output ("used for regulator outputs"), Open emitter, Open collector, Not connected. Plain Input and Output also exist. — [kicad-doc GitHub mirror, library editor chapter](https://github.com/KiCad/kicad-doc/blob/master/src/eeschema/eeschema_library_editor.adoc) (the mirror may be stale relative to the current GitLab docs)
- **Signal-integrity parameters that should follow from net role** (one community rule set): USB HS skew 25 ps, PCIe 5 ps, Ethernet 50 ps, HDMI 20 ps. V_CM = V_diff×skew/(2·T_rise), so a 4 mm USB-HS mismatch gives about 8.8 mV of common-mode voltage. — [kicad-happy EMC guide](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md)
- Regime triggers in another community skill set:
  - **High-speed**: clocks or signals above 25 MHz, t_r < 2 ns, USB, Ethernet RMII/RGMII, SPI > 40 MHz, HDMI/MIPI.
  - **High-current**: any rail above 3 A, or a converter above 15 W.
  - **RF**: sub-GHz or 2.4 GHz, or sleep current < 50 µA.
  - Inconsistency: the README's diagram says ">5A", while the SKILL file says ">3.0 A".
  - Impedance targets: USB 2.0 90 Ω and Ethernet 100 Ω differential; RF 50 Ω CPWG.
  - Sources: [IxTechCrypto/kicad-skills kicad-core SKILL](https://github.com/IxTechCrypto/kicad-skills/blob/main/skills/kicad-core/SKILL.md); [kicad-highspeed SKILL](https://github.com/IxTechCrypto/kicad-skills/blob/main/skills/kicad-highspeed/SKILL.md); [kicad-rf-lowpower SKILL](https://github.com/IxTechCrypto/kicad-skills/blob/main/skills/kicad-rf-lowpower/SKILL.md)
- **PCBSchemaGen (v2)** uses a **32-role pin ontology** with four constraint-predicate templates extracted automatically per IC. This is a ready-made vocabulary for normalizing pin roles beyond KiCad's ERC types. Preprint. — [alphaXiv v2 summary of arXiv 2602.00510](https://www.alphaxiv.org/abs/2602.00510.md); [arXiv 2602.00510 v1](https://arxiv.org/html/2602.00510v1)

### Inferences
- **Use a pin-role-first, name-second classifier.** KiCad ERC pin types are too coarse: there is no "SW node", "FB" or "XIN" type, and many library symbols use Passive or Unspecified everywhere. The useful signal is the **pin name**, normalized to a role ontology (PCBSchemaGen-style), plus the connected component types.
- A *net's role is a function of the pins on it*:
  - SW pin + inductor → **switch node** (minimize copper area).
  - FB pin + divider → **feedback** (high-Z, keep away from SW).
  - XIN/XOUT + crystal → **crystal net** (short, guarded, no vias).
  - USB_DP/DM on MCU + connector D+/D− → **90 Ω diff pair**.
  - Antenna/RF pin + matching network → **50 Ω RF**.
  - Connector power pin + fuse + high-current part → **high-current**.
- Diff-pair detection should combine (a) KiCad's own suffix rule (so the router will actually pair the nets), (b) the pin-role pair on both endpoints, and (c) a check that rejects false pairs (`XTAL_P`/`XTAL_N`). When an LLM proposes a pair that KiCad will not recognize by name, the pipeline should **propose a label rename** (e.g., `USB_D_P`/`USB_D_N`) as a schematic edit for the user to confirm.
- Data rate is the missing link. The interface standard (USB 2.0 HS vs FS, RGMII, PCIe Gen) usually has to come from the IC's datasheet or an LLM's knowledge of the MPN, and then map to impedance, skew and length rules through a static protocol table that deterministic code owns.

### Gaps
- **IBIS models.** I could not research whether IBIS model data (`[Model] Model_type`, edge rates, `[Diff Pin]`) is used anywhere to infer interface type or edge rate for PCB layout tools. Search budget was exhausted and ibis.org was unreachable. This is a promising source of rise times for the "fast edge" classification and deserves follow-up.
- I found no paper that measures net-role classification accuracy on PCB netlists.

---

## 3. Datasheet / app-note mining: extracting layout guidelines and recommended layouts

### Takeaway
Structured extraction of **electrical** facts from datasheets (pinouts, ratings, recommended external parts) works now. Production-minded tools page-anchor every value, score its quality and gate on trust.

**Layout-guideline** extraction is largely unsolved and unbenchmarked. Even the best community pipeline (kicad-happy) deliberately *skips* application-note prose. Academic work extracts parameters or footprints, not placement and routing rules. Board-level reasoning from datasheets is weak: HWE-Bench's best model passes only 8.15% of board-level schematic tasks.

### Cited Findings
- **kicad-happy datasheet pipeline**:
  - Distributor skills download PDFs ("96% success rate across 240+ manufacturers", each PDF verified against the expected MPN).
  - A **page selector** picks 8–15 pages using a TOC → keyword-density → fallback cascade. It targets "Pin Configuration", "Absolute Maximum Ratings", "Electrical Characteristics" and "Typical Application", and always includes page 1 and the last page.
  - Category extractor prompts cover base, pinout, regulator, diode, transistor, op-amp, MCU and crystal.
  - Merge and validation follow, then invariant cross-checks and a quality scorer.
  - The output is per-MPN JSON with `SpecValue{min, typ, max, unit, condition, evidence{page, section, confidence, method}}`.
  - Source: [kicad-happy datasheet-extraction.md](https://github.com/aklofas/kicad-happy/blob/main/datasheet-extraction.md); [README](https://github.com/aklofas/kicad-happy)
- **Reliability controls in the same pipeline**:
  - Trust gates (`best(spec, min_confidence="medium")`).
  - Tri-state nullability: "not extracted" vs "extracted but below the gate" vs "trusted".
  - A PDF SHA-256 staleness check.
  - Per-project caches, because "a verified extraction for revision A should not quietly get used for revision B".
  - A legacy scorer with `MIN_SCORE = 6.0/10` and up to 3 retries, keeping the best result ("easier to refuse an extraction than to mislead an analyzer").
  - "It doesn't guess": missing parameters are recorded as `null`, never copied from sister parts.
  - **"It doesn't interpret marketing claims. Application notes, reference designs, and 'recommended for X' prose are skipped."**
  - Source: [kicad-happy datasheet-extraction.md](https://github.com/aklofas/kicad-happy/blob/main/datasheet-extraction.md)
  - Internal inconsistency: the v1.4 score is 0–100 with 3 dimensions, while the legacy rubric is 0–10 with 5 dimensions.
- Example legacy extraction (TPS61023):
  - Pins carry `function` (e.g., "Switch node"), `type` (power/ground/analog/digital) and voltage limits.
  - `features.topology` = boost; `switching_freq_hz` = 1.2 MHz.
  - `application_circuits` = recommended Cin/Cout/L.
  - `thermal.rtheta_ja_cw` = 175.
  - Source: [kicad-happy datasheet-extraction.md](https://github.com/aklofas/kicad-happy/blob/main/datasheet-extraction.md)
- kicad-happy v2.0 "Deep Review" does a per-IC LLM comparison of actual usage against the datasheet. Findings carry evidence links and are written to `analysis/deep_review.json`, kept separate from the deterministic findings ("stripping `llm_*` fields recovers the deterministic baseline"). — [how-it-works](https://github.com/aklofas/kicad-happy/blob/main/how-it-works.md); [deep-review.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/references/deep-review.md)
- Multimodal reading of PDF reference designs: render pages, read 2–4 pages at a time, follow off-page connectors, and match net labels across pages. — [kicad-happy pdf-schematic-extraction.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/references/pdf-schematic-extraction.md)
- **HWE-Bench** (arXiv 2603.18102; preprint):
  - 300 board-level schematic tasks and **2,914 IC datasheets**.
  - The best model passed **8.15%**.
  - The authors say models show "usable documentation understanding but lack physical intuition".
  - The paper also cites prior work on extracting **footprint geometry from datasheet diagrams** for placement, which I could not locate.
  - Source: [arXiv 2603.18102](https://arxiv.org/pdf/2603.18102)
- **PCBSchemaGen** (arXiv 2602.00510; preprint):
  - v1 uses a knowledge graph derived from real IC datasheets plus **subgraph isomorphism** to check pin-role semantics and topological constraints.
  - v2 adds a schema-induced KG (a 32-role pin ontology and 4 predicate templates per IC), a 5-layer reward oracle (electrical, role, template, topology, power) and Thompson-sampling refinement. It emits SKiDL, which compiles to KiCad.
  - Benchmarks are on Hugging Face: 227 tasks across `pcbbench` and `open_schematics`, with `pcbbench` holding 62 tasks on 41 real ICs, all scored by a deterministic verifier.
  - An author slide deck reports 86.3% / 84.0% / 61.0% (easy/medium/hard). These numbers are self-reported and were not verified against the paper.
  - A NeurIPS 2026 poster page appears in search results.
  - Sources: [arXiv v1](https://arxiv.org/html/2602.00510v1); [HF benchmarks](https://huggingface.co/datasets/Hzou9/PCBSchemaGen-Benchmarks); [Sandia DOE review slides](https://doepeerreview.sandia.gov/app/uploads/sites/82/2026/07/Han_Peng_20260727_DOE_Review_AIPE.pdf); [NeurIPS 2026 poster](https://neurips.cc/virtual/2026/poster/149018)
- **DocEDA** (arXiv 2412.05301; preprint): computer vision plus an LLM with chain-of-thought to extract electrical parameters from circuit datasheets, aimed at analog design rather than layout. — [arXiv 2412.05301](https://arxiv.org/abs/2412.05301)
- **DATE 2026 paper 1187**: multi-agent LLM generation of PCB **component libraries (symbols and footprints) from datasheets**, with preprocessing and error-repair stages. — [DATE 2026 PDF](https://past.date-conference.com/proceedings-archive/2026/DATA/1187.pdf)
- **DS2SC-Agent** (arXiv 2603.21190; preprint): a multi-agent datasheet-to-model pipeline for chiplets. — [arXiv 2603.21190](https://arxiv.org/pdf/2603.21190)
- Practitioner reports: Altium's article on building a local-LLM datasheet extractor (for IC driver development) — [Altium Resources](https://resources.altium.com/p/building-local-llm-datasheet-extractor-ic-driver-development); JITX's blog testing generative AI for board design — [JITX blog](https://blog.jitx.com/jitx-corporate-blog/testing-generative-ai-for-circuit-board-design).
- Datasheet-to-footprint is also appearing in agent skills: IxTechCrypto `kicad-newpart` (parametric IPC-7351B synthesis with paste-gridding) — [kicad-skills README](https://github.com/IxTechCrypto/kicad-skills); kicad-harness (datasheet-to-footprint generation; AGPL) — as listed in [kicad-tools README](https://github.com/rjwalters/kicad-tools).
- kicad-tools offers `kct datasheet convert` (PDF → markdown), `extract-images` and `extract-tables`. These are building blocks for locating "Layout Guidelines" sections and example-layout figures. — [kicad-tools README](https://github.com/rjwalters/kicad-tools)

### Inferences
- **The layout section is a different extraction target from the electrical tables**, and it needs its own schema. Most regulator, PHY and RF datasheets have a "Layout Guidelines" / "Layout Example" section: numbered prose rules plus one figure. A dedicated extractor should:
  1. Locate the section (TOC/keyword, the same as kicad-happy's page selector).
  2. Convert each rule into a **typed predicate**, e.g., `near(pin=VIN, part_role=Cin, max_mm=?, layer=same)`, `minimize_area(net=SW)`, `route_away(net=FB, from=SW/L)`, `kelvin(net=FB, at=Cout)`, `thermal_vias(pad=EP, count≥n)`, `no_copper_under(part=L|antenna, layers=…)`, `ground_return(PGND→AGND single point)`.
  3. Keep the page and sentence as evidence.
  4. Leave numbers `null` when the text is qualitative ("as close as possible"). The constraint solver then turns "as close as possible" into an objective weight instead of a hard bound.
- Example layout **images** are best used as *topology hints* (relative placement order such as Cin–IC–L–Cout, and which side the FB divider sits on), interpreted by a VLM with low confidence. Their scale is unreliable. Recommended land patterns are a footprint concern and are already handled by KiCad libraries.
- Key reliability issues to design for:
  1. **Units and conditions**: values are only meaningful with their test conditions, as in `SpecValue.condition`.
  2. **Variant confusion**: fixed vs ADJ versions, and package-specific θJA.
  3. **Datasheet revision drift**: hash the PDF.
  4. **Qualitative rules mis-quantified by the LLM**: never invent a millimetre value.
  5. **Sister-part leakage**: the LLM "remembers" a similar part's guideline.

  kicad-happy's controls (evidence page, confidence, null-not-guess, trust gates) are a good template for all five.

### Gaps
- I found **no tool or paper that specifically extracts PCB layout guidelines** (placement and routing rules) from datasheets or app notes and evaluates the result. This is a genuine gap in the literature, and possibly an opportunity.
- I could not verify the named products "DatasheetGPT" or "PDF datasheet extraction for EDA".
- I could not check TI WEBENCH's layout-export capability, or whether TI, ADI or ST publish machine-readable layout data (all hosts blocked).
- I found no quantitative hallucination or unit-error rates for LLM datasheet extraction.

---

## 4. Component knowledge bases and assembling a per-part "layout card"

### Takeaway
Distributor APIs provide identity, package, a datasheet URL and loosely structured parametric key/value pairs:
- **DigiKey v4**: `Parameters[]`, `DatasheetUrl`, plus filters like `Has3DModel`/`HasCadModel`.
- **Nexar/Octopart GraphQL**: `specs { attribute, value }`.
- **LCSC/JLC**: `attributes`, `encapStandard`, `pdfUrl`, and basic vs extended status.

None of them provide *layout* semantics: pin roles, hot-loop membership, keepouts or placement rules. A layout card must therefore be assembled from (i) the KiCad symbol and footprint, (ii) distributor parametrics, and (iii) datasheet extraction with evidence, plus (iv) the role-specific recipe.

### Cited Findings
- **Nexar (Octopart) API**:
  - A single GraphQL endpoint (`https://api.nexar.com/graphql`) with OAuth2 client-credentials auth.
  - `supSearchMpn(q, limit)` returns `hits` and `results { part { mpn manufacturer { name } … } }`. Parts expose `specs { attribute { name shortname id } value }`.
  - Each returned part counts against the organization's part quota, and partial matches are allowed.
  - Sources: [Nexar Playground query examples](https://support.nexar.com/support/solutions/articles/101000494582-nexar-playground-graphql-query-examples); [Altium Octopart API docs](https://www.altium.com/documentation/altium-developer-center/octopart/api?version=5); [Altium quick-start (JP)](https://www.altium.com/jp/documentation/altium-developer-center/quick-starts/octopart-api)
- **DigiKey Product Information API v4**:
  - OAuth2 client credentials.
  - `POST /products/v4/search/keyword`, with `SearchOptions` including `HasDatasheet`, `Has3DModel`, `HasCadModel`.
  - The response includes `DatasheetUrl` and `Parameters[] {ParameterText, ValueText}` (e.g., Capacitance 100nF, Voltage Rated 16V, Temperature Coefficient X7R, Package / Case 0402).
  - `GET /products/v4/search/{pn}/productdetails` returns full details, with `manufacturerId` to disambiguate.
  - Other endpoints: `/media`, `/substitutions`, `/recommendedproducts`.
  - Rate limits return HTTP 429 with `Retry-After`.
  - Source (secondary; it documents the API): [kicad-happy digikey SKILL.md](https://github.com/aklofas/kicad-happy/blob/main/skills/digikey/SKILL.md)
- **LCSC / JLCPCB**:
  - The free community `jlcsearch` API (`https://jlcsearch.tscircuit.com`, no auth) returns `is_basic`/`is_preferred`, stock and price.
  - "As of 2026-09" its general search no longer returns the `extra` block (manufacturer, datasheet, attributes). Category endpoints return `attributes` as a JSON **string** (e.g., `{"Resistance":"10kΩ","Power(Watts)":"100mW"}`).
  - LCSC's own product-detail endpoint gives `productModel` (MPN), `brandNameEn`, `pdfUrl`, `encapStandard` (package) and price ladders.
  - Source: [kicad-happy lcsc SKILL.md](https://github.com/aklofas/kicad-happy/blob/main/skills/lcsc/SKILL.md)
  - Another skill set ships a local search over "630,000+ components in the JLCPCB/LCSC catalog". — [IxTechCrypto/kicad-skills](https://github.com/IxTechCrypto/kicad-skills)
- **Datasheet-derived per-part facts** with evidence (pinout with `power_domain` and `alt_functions[]`, absolute max, thermal θJA, regulator topology, enable and PG pins) are already modelled as `DatasheetFacts`, with six categories in v1.4 (regulator, diode, transistor, op-amp, MCU catalog tier, crystal). — [kicad-happy datasheet-extraction.md](https://github.com/aklofas/kicad-happy/blob/main/datasheet-extraction.md)
- kicad-happy uses **package θJA lookup** with a thermal-via correction for junction-temperature estimates. It also keeps a per-part op-amp behavioral table (~100 parts: GBW, slew rate, output swing from distributor APIs or a built-in table). — [kicad-happy README](https://github.com/aklofas/kicad-happy)
- KiCad 9 can **embed datasheets, 3D models and fonts** in schematic, PCB, symbol and footprint files, which makes self-contained projects possible. A layout card's datasheet can therefore travel with the design. — [KiCad 9.0 release notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)
- **PCBSchemaGen's per-IC KG** (pin roles plus constraint predicates, extracted automatically per IC) is the closest published analogue to a machine-checkable "part card", though it targets schematic correctness rather than layout. — [arXiv 2602.00510](https://arxiv.org/html/2602.00510v1); [alphaXiv v2](https://www.alphaxiv.org/abs/2602.00510.md)
- CELUS models "CUBOs" as "digital datasets that serve as digital twins of component applications", meaning a part plus its application circuit, behind each functional block. — [CELUS: What are Functional Blocks](https://www.celus.io/knowledge/what-are-functional-blocks); [CELUS: Explore CUBOs](https://www.celus.io/knowledge/explore-cubos)

### Inferences
- A **layout card** per part (MPN + footprint) should contain:
  - **Identity**: MPN, manufacturer, KiCad lib_id, footprint, package, datasheet hash.
  - **Pin-role map**: pin number → role from the ontology (VIN, SW, BOOT, FB, PGND, AGND, EP, XIN…) + KiCad electrical type + power domain.
  - **Electrical parametrics** relevant to layout: f_sw, max currents per pin, edge rate or interface standard, θJA/θJC, Tj_max, and voltage class (for creepage).
  - **Required externals with roles**: Cin (which pins, value, "as close as possible"), Cboot, Cout, L, FB divider, crystal load caps.
  - **Layout rules**: typed predicates with evidence (page, sentence) and confidence.
  - **Thermal**: EP via count/pitch suggestion and copper area.
  - **Keepouts**: e.g., no copper under an inductor or antenna.
  - **Provenance** per field: kicad_lib / distributor / datasheet:p12 / llm_prior / user.
- The distributor APIs are best used for **identity resolution, package, datasheet URL and coarse parametrics** (current rating, f_sw, package). They should not be the source of layout rules. Expect schema churn (the jlcsearch change in 2026-09 is an example) and design adapters accordingly.
- Passive parts (R, C, L, ferrites) can get layout cards from parametrics alone (size, voltage rating, DC-bias derating, an L shielded-or-not flag for magnetic-leakage rules). ICs need datasheet extraction.

### Gaps
- I could not verify the SnapMagic (SnapEDA) API's metadata fields, Octopart's 3D-model and CAD fields, or whether any API exposes θJA or "recommended layout" data in structured form (hosts blocked, search exhausted).
- I found no public "part knowledge graph" for board-level layout rules.

---

## 5. Design-intent capture in KiCad schematics, and LLM-proposed annotations and clarifying questions

### Takeaway
KiCad 9/10 now give a schematic-side vocabulary for intent that round-trips to the PCB and to DRC:
- **net-class directive labels**, net-class **rule areas** and multiple prioritized net classes per net;
- **component classes** (set on symbols, on rule-area directives, or by rules), queryable in DRC;
- **hierarchical sheets** and multichannel repeat;
- **design blocks** (schematic in 9, PCB in 10);
- **time-domain tuning profiles**, a **graphical DRC rule editor**, variants, jumpers and schematic groups (KiCad 10).

An LLM front end can emit *all* of its annotations through these native mechanisms, as proposals for the user to accept, rather than in a side file.

### Cited Findings
- **Component classes (KiCad 9)**:
  - "Component classes are set on symbol in the schematic editor and then apply to the footprints associated with those symbols."
  - "Directive labels attached to a rule area can now take a 'Component Class' field. Symbols within the rule area will be assigned that component class."
  - Symbols can have multiple classes.
  - New DRC expressions: `A.ComponentClass == 'CLASS_1,CLASS_2'`, `A.hasComponentClass('CLASS_1')` and `A.memberOfFootprint('${Class:CLASS_1}')`.
  - Source: [KiCad 9.0.0 release notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)
- Component-class caveats from users:
  - `hasComponentClass` matches only footprints, so a clearance rule on pads or tracks will not fire.
  - The workaround is a spatial condition such as `intersectsCourtyard('${Class:fine_pitch}')`.
  - Classes can also be assigned by condition-based rules.
  - Community use cases: the multichannel tool, and writing custom rules.
  - Sources: [KiCad forum: component classes for clearance](https://forum.kicad.info/t/using-component-classes-for-custom-clearance-settings/57733); [KiCad forum: component classes and directive labels](https://forum.kicad.info/t/component-classes-and-directive-labels-how-can-they-be-used/55950)
- **Net classes (KiCad 9)**:
  - A net can now have **multiple net classes**, ordered by priority. The effective class is built from non-null fields in priority order, with the default class as fallback.
  - New DRC function `A.hasNetclass('x')`.
  - **Net-class rule areas** let users "draw a shape to which net class directives can be attached to all nets defined by the shape".
  - Source: [KiCad 9.0.0 release notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)
  - Assignment methods: a netclass directive label on a net, right-click → "Assign netclass", or **patterns** that group nets automatically. — [KiCad forum: netclasses](https://forum.kicad.info/t/netclasses/60014)
- **Creepage DRC (KiCad 9)**: e.g., `(rule HV_HV (constraint creepage (min 20mm)) (condition "A.hasNetclass('A') && B.hasNetclass('B')"))`. — [KiCad 9.0.0 release notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)
  - kicad-tools exports voltage-domain netclasses plus pairwise HV clearance rules so that `kicad-cli` DRC enforces creepage. — [kicad-tools README](https://github.com/rjwalters/kicad-tools)
- **Design blocks and multichannel**:
  - KiCad 9 adds schematic design blocks ("libraries of reusable schematic blocks") and multichannel design support that repeats PCB layout across channels.
  - KiCad 10 extends design blocks to the PCB ("libraries of board layouts").
  - Sources: [KiCad 9.0.0 release notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/); [KiCad 10.0.0 release notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/) (release dated 2026-03-20; URL inferred from KiCad's blog slug pattern)
- **KiCad 10 additions relevant to intent**:
  - Time-domain tuning: constraints in delay rather than only length, plus Tuning Profiles for per-layer routing parameters.
  - A graphical DRC rule editor compatible with the custom-rules language.
  - Variants.
  - Jumpers: pin sets that are internally connected.
  - Schematic grouping.
  - Unconstrained pin/gate swap with forward and back annotation.
  - Source: [KiCad 10.0.0 release notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)
- **Example of LLM intent detection with clarifying questions (kicad-happy)**:
  - The analyzers emit a `design_intent` object: `product_class` (prototype/production), `ipc_class` (1–3), `target_market` (hobby/consumer/industrial/medical/automotive/aerospace), `confidence`, `detection_signals` and per-field `source` (config / pcb_fab_notes / schematic_title / auto).
  - **When confidence < 0.5 the agent must ask the user to confirm** before applying stricter criteria. At ≥0.5 it applies the detected intent and states it.
  - Extra LLM refinement signals: AEC-Q MPNs → automotive; isolation barriers → medical or industrial; TMR → safety-critical.
  - Source: [kicad-happy design-intent.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/references/design-intent.md)
- **Structured design interviews**: IxTechCrypto's `grill-me` skill runs a "relentless, round-based design tree interview" to stress-test PDN budgets and layout decisions before any copper is committed, optionally syncing to `CONTEXT.md`. — [IxTechCrypto/kicad-skills](https://github.com/IxTechCrypto/kicad-skills)
- **Spec-gated edits**: copperhead lets "nothing start without a spec". Edit tools stay unavailable until a validated change proposal exists, and it keeps markdown design docs as memory plus a constraints registry. — [copperhead README](https://github.com/copperheadhq/copperhead)
- **Hierarchy as identity**: atopile tags each footprint with an `atopile_address` (e.g., `usb_c.esd_protection.package`) taken from the module hierarchy, and uses it to keep and replay layouts across regenerations. — [kicad-tools analysis of atopile layout reuse](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/atopile-layout-reuse.md)

### Inferences
- **Mapping from annotation types to KiCad carriers**:
  - Net role and class → net-class directive labels (or `.kicad_pro` net-class patterns), using multiple classes per net, e.g., `PWR_HICURRENT` + `SWITCH_NODE`.
  - Block membership → **component class** per block instance, e.g., `BLK_BUCK1`. Each class can also carry a *role* class such as `ROLE_CIN_HOT`.
  - Block-scoped rules → custom DRC rules in `.kicad_dru` keyed on `memberOfFootprint('${Class:BLK_BUCK1}')` or `hasNetclass`, plus courtyard or area conditions.
  - Repeated channels → hierarchical sheets plus the multichannel tool.
  - Approved block layouts → PCB design blocks (KiCad 10).
- **Hierarchical sheet names are the cheapest high-precision intent signal.** Sheets named "Power", "USB" or "RF" give block boundaries a prior. Local labels inside a sheet give net roles. An LLM can be asked to propose a sheet split for flat schematics.
- **Clarifying-question policy**: ask only where (a) a constraint is expensive to get wrong and (b) confidence is low or sources conflict. Examples:
  - "Is J3 USB 2.0 HS or FS only?" (decides the 90 Ω rule).
  - "Is +12V_MOTOR up to 5 A continuous?" (decides copper width).
  - "Is net `SENSE` high-impedance analog?"
  - "Should Y1 nets get guard rings?"

  Each question should be generated from a specific unresolved field in the annotation schema, never asked open-ended. kicad-happy's confidence threshold is a working precedent.
- Write-back should be **diff-style and reversible**: proposed labels, component-class fields and `.kicad_dru` rules are shown as a patch and accepted per item. This also gives training data (accept or reject) for later fine-tuning.

### Gaps
- I could not read the current official KiCad 9/10 manuals (docs.kicad.org was blocked). Details such as the exact field names for component classes in rule-area directives, and the netclass *pattern* syntax in `.kicad_pro`, should be checked against the official docs.
- I could not check Flux's or Quilter's intent-capture UIs (hosts blocked, search exhausted).

---

## 6. Mapping recognized function → layout recipe (existing codifications)

### Takeaway
Recipes exist today in three forms:
1. **Generator and module libraries** that bundle a circuit with its layout: JITX parametric circuits, atopile modules with sub-PCB layout reuse, CELUS functional blocks/CUBOs that produce a "prototype-grade PCB layout", KiCad 10 PCB design blocks, and kicad-tools circuit blocks.
2. **Rule checkers** that encode the recipe as post-hoc checks: kicad-happy's EMC and PCB rules, such as input-cap loop area, SW copper area, decoupling distance, and TVS-to-connector distance.
3. **Prose agent skills**: IxTechCrypto, kicad-happy deep-review heuristics.

None of them publishes a general, machine-readable "function → placement/routing constraints" table. That table is the gap a new system has to fill.

### Cited Findings
- **JITX**:
  - In the power-layout tutorial, a buck regulator (24 V → 5.5 V) is defined by a constraints object (input range, output setpoint, ripple, output current, switching frequency, inductor sizing method), and a **TI TPS6293x parametric circuit** is instantiated from a TI-vreg library. A TPS6208 stage (5.5 V → 3.3 V) follows the same pattern.
  - Placement and routing can be specified in code for repeatability, or adjusted interactively.
  - Sources: [JITX power layout tutorial](https://docs.jitx.com/getting-started/quickstart-power-layout.html); [JITX physical design docs](https://docs.jitx.com/en/4.0/essentials/physical_design/index.html)
  - A JITX skills plugin describes Python-based workflows for pours, wiring and SI constraints. — [Claude Plugin Hub listing](https://www.claudepluginhub.com/plugins/jitx-inc-jitx-skills)
  - I did not find a JITX page that spells out buck hot-loop rules.
- **atopile**:
  - A declarative `.ato` language with modules, interfaces, units, tolerances and assertions. The compiler "solves constraints, picks parts, runs checks, and updates your KiCad layout".
  - It emphasizes "reusable modules" and a package registry at packages.atopile.io.
  - Source: [atopile README](https://github.com/atopile/atopile)
  - Layout reuse: each module can have a sub-PCB with pre-laid-out footprints and routes. On regeneration, footprints are matched by hierarchical address. For new groups, the layout is pulled from the template with an anchor-footprint offset, and nets are remapped by matching pads. — [kicad-tools analysis of atopile layout reuse](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/atopile-layout-reuse.md)
- **CELUS**:
  - Functional blocks are "questions" that CUBOs "answer".
  - From a canvas of blocks, "AI-powered software generates the corresponding schematics file, a Bill of Material and a prototype-grade PCB layout file in the EDA format of your choice".
  - The vendor claims up to 90% time reduction (marketing claim, not independently measured).
  - Sources: [CELUS functional blocks](https://www.celus.io/knowledge/what-are-functional-blocks); [CELUS blog](https://celus.io/blog/define-design-develop); [CELUS FAQ](https://www.celus.io/faq)
- **kicad-tools** has reusable schematic blocks: `MCUBlock` (MCU with bypass capacitors), `LDOBlock` (regulator with input and output capacitors), USB, debug header, I2C and reset. It also has an A* autorouter "with net class awareness". — [kicad-tools README](https://github.com/rjwalters/kicad-tools)
- **kicad-happy rule checks that encode recipes**:
  - SW-001..003: harmonic overlap with test bands, **switching-node copper area**, **input-capacitor loop area**.
  - DC-001..003: cap too far from IC, IC with no decoupling, cap too far from via.
  - ES-001/002: **TVS too far from connector**, TVS with too few ground vias.
  - CK-001..004: clock on an outer layer, long clock trace, clock near a connector, stubs.
  - DP-001..004: skew, reference-plane change, outer-layer routing.
  - ML-001: **unshielded switching inductor within 15 mm** of ADCs, op-amps, crystals or RF.
  - VS-001: stitching spacing > 2×λ/20.
  - RP-001: a layer-change via without a nearby ground via.
  - Physics: E ∝ f²·A·I, so doubling loop area adds +6 dB and doubling frequency adds +12 dB. "A 500 kHz buck converter has its 60th–176th harmonics in the FCC 30–88 MHz test band. Minimizing the switching loop area is the primary mitigation."
  - Source: [kicad-happy EMC pre-compliance guide](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md)
  - The PCB analyzer's decoupling check considers caps within 10 mm of each IC and reports the closest cap that shares a net. — [kicad-happy methodology_pcb.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_pcb.md)
- **kicad-happy Deep Review per-class heuristics** (these become layout-relevant facts):
  - **Regulators**: required externals vs datasheet minimums (inductance floor, Cin/Cout *after DC-bias derating*, bootstrap cap), plus thermal check P_diss×θJA + T_amb vs Tj_max.
  - **MCUs**: per-domain decoupling vs datasheet placement requirements; crystal CL = C1·C2/(C1+C2) + Cstray; USB series resistors.
  - **Interfaces**: termination and fail-safe biasing.
  - **TVS**: working voltage and clamping vs abs-max.
  - Source: [kicad-happy deep-review.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/references/deep-review.md)
- **Community prose recipes (IxTechCrypto/kicad-skills)**:
  - "Keep the high-frequency buck/boost switching loop (C_IN → FET → L → C_OUT) tight (< 15 mm² loop area)." — [kicad-rf-lowpower SKILL](https://github.com/IxTechCrypto/kicad-skills/blob/main/skills/kicad-rf-lowpower/SKILL.md)
  - "Never sense buck regulator feedback at the output inductor. Route a dedicated differential Kelvin pair directly from the core bypass capacitor of the furthest critical ASIC back to the buck controller sense pins." Also: design one point-of-load decoupling and thermal pattern and clone it across N identical chip sites. — [kicad-highcurrent SKILL](https://github.com/IxTechCrypto/kicad-skills/blob/main/skills/kicad-highcurrent/SKILL.md)
  - Clock lines: guard with ground copper or keep 3W spacing; critical clock or ADC lines get 5W or a coplanar ground guard with stitching vias every 5 mm. USB 2.0 is 90 Ω and Ethernet 100 Ω. — [kicad-highspeed SKILL](https://github.com/IxTechCrypto/kicad-skills/blob/main/skills/kicad-highspeed/SKILL.md)
  - RF: a "sacred" antenna keepout on all layers, a 50 Ω CPWG feed and a via fence. — [kicad-rf-lowpower SKILL](https://github.com/IxTechCrypto/kicad-skills/blob/main/skills/kicad-rf-lowpower/SKILL.md)
  - These are community rules of thumb, not vendor specifications.
- A "spec-to-layout automation flow for buck converters" exists at IC level (NYCU), showing that recipe-driven buck layout has been automated in the IC domain (title only seen). — [NYCU scholar page](https://scholar.nycu.edu.tw/zh/publications/spec-to-layout-automation-flow-for-buck-converters-with-current-m/)

### Inferences
- **A draft recipe table** follows. The rules are *standard engineering practice*, partly backed by the community and tool sources above, and should be confirmed against vendor app notes. Pointers that were **not verified this session**: TI AN-1149 / SNVA021 "Layout Guidelines for Switching Power Supplies"; TI SPRAAR7 "USB 2.0 Board Design and Layout Guidelines"; ST AN2867 "Oscillator design guide for STM8/STM32"; ADI MT-101 "Decoupling Techniques".

  | Block (recognizer) | Critical sub-structure (roles) | Hard/soft constraints to emit |
  |---|---|---|
  | **Buck** (IC with SW+FB±BOOT, L on SW) | Hot loop = Cin(HF) ↔ VIN pin ↔ high-side FET ↔ low-side FET/diode ↔ PGND, plus Cboot SW↔BOOT | Cin(HF) on the same layer, adjacent to VIN/PGND (minimize loop area; numeric bounds only from the datasheet); SW copper minimal and no SW under the FB network; FB divider near the FB pin, with its top tap Kelvin-sensed at Cout (or at the load); L right next to SW; Cout returns to PGND near Cin's return; PGND/AGND join at one point if the datasheet says so; EP thermal vias; keep sensitive nets ≥ X mm from L (ML-001 uses 15 mm) |
  | **Boost** | Hot loop = Cout ↔ switch/diode ↔ PGND | Mirror of buck, with Cout as the critical loop cap |
  | **LDO** | Cin, Cout at pins | Cout within the ESR/distance spec; thermal copper on the tab or EP |
  | **Decoupling network** (cap between rail and GND, sharing a net with an IC power pin) | Cap ↔ specific power pin | Smallest cap closest to its pin; via to plane at the cap pad; one cap per pin group (kicad-happy DC-001..003) |
  | **Crystal** (crystal + 2 load caps to GND on XIN/XOUT) | XIN/XOUT nets | Very short, symmetric, no vias, ground guard or keepout of other signals, load caps between the crystal and ground near the IC, no fast signals nearby |
  | **USB 2.0** (MCU USB_DP/DM ↔ connector D+/D−, optional ESD, series R) | Diff pair | 90 Ω differential, skew ≤ ~25 ps (kicad-happy), ESD as close to the connector as possible (ES-001), continuous reference plane, minimal vias and stubs |
  | **RF front end** (antenna/RF pin + matching network) | 50 Ω line | 50 Ω CPWG, matching parts in line with no stubs, antenna keepout, via fence |
  | **Op-amp / ADC front end** (op-amp with feedback R/C; ADC input RC) | High-Z input nodes, feedback loop | Short high-Z nodes, guard rings where leakage matters, feedback parts close to the inverting pin, ADC RC close to the ADC pin, away from SW/L/clock |
  | **ESD protection** (TVS mapped to a connector) | Connector pin → TVS → GND | TVS immediately at the connector, short low-inductance ground with multiple vias |
  | **High-current path** (net with a high-current part/rating) | Power path | Width from IPC-2152 on current; via arrays (one community source gives 1.5–2 A/via); copper pours |

- **Recipes should be data, not prompts.** Each row should be a parameterized template: a role pattern for recognition, plus a constraint set with default weights. Numbers are filled in from the part's layout card where the datasheet gives them, and stay qualitative or objective-weighted otherwise. This makes recipes testable against kicad-happy-style checkers, which already exist for several rows.
- KiCad 10 PCB design blocks and atopile-style address matching suggest a second recipe channel: **"replay a known-good sub-layout"** (e.g., a vendor EVM layout for the same IC) when the block matches exactly. Generate from constraints when it does not.

### Gaps
- I could not verify TI WEBENCH's layout export (formats, KiCad support) or Flux's template and AI-layout recipe system (hosts blocked, search exhausted).
- I found no published, machine-readable cross-vendor recipe database.
- I could not confirm which numeric thresholds (mm, mm²) vendors actually specify for Cin distance or loop area. Most vendor guidance is believed to be qualitative ("as close as possible"), but that is unverified.

---

## 7. Implications for an LLM-driven KiCad placer/router — proposed "design understanding" pipeline and data schema

### Takeaway
Build the front end as **deterministic extraction → template/rule recognition → LLM adjudication and datasheet-rule extraction (evidence-gated) → user confirmation → compilation into native KiCad intent** (net classes, component classes, `.kicad_dru` rules, groups and design blocks), plus a soft-constraint objective for the placer.

The evidence favours keeping topology and graph facts deterministic. GENIE-ASI's F1 drops from 1.0 to 0.31, CIRCUIT tops out at 48%, and HWE-Bench at 8.15%. LLMs should be used where they are measurably useful: reading datasheets, labelling parts and pins, recognizing intent from names and context, writing new detector templates, and asking targeted questions. kicad-happy's architecture (deterministic JSON plus LLM reasoning with confidence and evidence labels) is the closest working precedent.

### Cited Findings
- Deterministic-first architecture precedent: "The analysis scripts are data extraction tools, not AI… The AI part is the *reasoning about* the data." "Hallucination risk is bounded by the data… it can't invent components that aren't in your schematic." Every finding carries a `deterministic` / `heuristic` / `datasheet-backed` confidence label. — [kicad-happy how-it-works](https://github.com/aklofas/kicad-happy/blob/main/how-it-works.md)
- "LLM writes executable code" beats "LLM answers directly" on subcircuit identification for simple and moderate structures (F1 1.0 / 0.81), but still fails on complex ones (0.31). — [GENIE-ASI arXiv 2508.19393](https://arxiv.org/pdf/2508.19393)
- LLM topology comprehension is weak: CIRCUIT's best is 48.04%, with topology the hardest part. — [arXiv 2502.07980](https://www.arxiv.org/pdf/2502.07980)
- Board-level datasheet-driven design is far from solved: HWE-Bench's best is 8.15%, with "usable documentation understanding but lack physical intuition". — [arXiv 2603.18102](https://arxiv.org/pdf/2603.18102)
- A KG plus a deterministic verifier makes LLM output checkable at pin and topology level (PCBSchemaGen). — [arXiv 2602.00510](https://arxiv.org/html/2602.00510v1)
- An intent-confidence threshold that triggers user confirmation (<0.5) is in production use. — [kicad-happy design-intent.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/references/design-intent.md)
- KiCad-native carriers for every annotation exist as of v9/v10: component classes, multiple net classes, rule areas, DRC functions, design blocks, tuning profiles and the graphical rule editor. — [KiCad 9.0.0 notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/); [KiCad 10.0.0 notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)

### Inferences

**Proposed pipeline.** Each stage is labelled D = deterministic code, L = LLM, U = user.

1. **Ingest (D).**
   - Parse `.kicad_sch` and `.kicad_pro` with the KiCad netlist export or an S-expression parser. Build the bipartite part–net–pin graph and expand hierarchy and multichannel instances.
   - Capture existing intent: sheet names, net classes and patterns, directive labels, component classes, fields (MPN, Datasheet), power symbols.
2. **Part resolution (D+L).**
   - Resolve MPN → distributor record (DigiKey/Nexar/LCSC) → datasheet PDF, hashed (D).
   - When the MPN is missing, the LLM proposes candidates from value, footprint and description, marked `proposed` (L).
3. **Layout-card build (L, evidence-gated; D validation).**
   - Page-select the PDF (D).
   - The LLM extracts the pin-role map, required externals, f_sw, interface standards, thermal data, and **the layout-guidelines section as typed predicates**, each with a page/quote and confidence (L).
   - Validators check units, conditions, pin-number existence against the KiCad symbol, and agreement between symbol pin names and datasheet pin names (D).
   - Cache per MPN and PDF hash.
4. **Net-role pass (D, then L for leftovers).**
   - Deterministic rules: power symbols and names, ground, diff-pair suffixes, pin-role pairs, protocol buses (kicad-happy-style tables).
   - The LLM labels only unexplained or ambiguous nets, using pin roles and names (e.g., `SENSE_A` → high-Z analog?), and must cite which pins justify the label.
5. **Block recognition (D templates, then L adjudication).**
   - VF2/rule templates over pin-role-labelled edges (ALIGN-style matcher, kicad-happy-style detectors) find bucks, LDOs, crystals, decoupling, USB, ESD, op-amp stages, RF chains and so on.
   - Uncovered ICs and passives go to the LLM, which either assigns them to an existing block or **writes a new detector template** (GENIE-ASI pattern). The template is executed and must explain every member pin before it is accepted (D check).
6. **Criticality and constraint synthesis (D recipe engine + L parameter fill).**
   - Each recognized block instantiates its recipe (Section 6 table). Numeric parameters come from layout cards (L-extracted, trust-gated) or from defaults. Protocol tables (USB/PCIe/Ethernet impedance and skew) are D.
   - Criticality score = f(edge rate or f_sw, current, impedance requirement, block type). Its main use is ordering placement and routing.
7. **Clarify (L → U).**
   - Generate questions only for low-confidence, high-impact fields (e.g., USB speed, motor current, which ground strategy) and present them as a short checklist. U answers update the schema with `source: user`.
8. **Compile to KiCad (D).**
   - Net classes (with patterns and multiple classes), component classes per block and role, `.kicad_dru` custom rules (diff pair, width, clearance, creepage, `memberOfFootprint`/`hasNetclass` conditions), rule areas or keepouts, groups, and time-domain tuning profiles.
   - Soft constraints (proximity, loop area, keep-away) go to the placer objective as a JSON side file, because KiCad DRC cannot express "minimize area".
   - All edits are proposed as a reviewable diff.
9. **Verify (D).**
   - After placement and routing, run DRC plus recipe checkers (loop area, SW copper area, decoupling distance, TVS distance, skew). These are the kicad-happy-style EMC and PCB rules, re-used as acceptance tests. Feed violations back to the placer and router.

**Proposed data schema** (annotated block graph, JSON). The field layout is a sketch:

```json
{
  "design": {"project": "...", "kicad_version": "10.0", "intent": {"product_class": "prototype", "ipc_class": 2, "source": "user|auto", "confidence": 0.8}},
  "parts": {
    "U3": {"mpn": "TPS62933DRLR", "footprint": "...", "layout_card": "cards/TPS62933DRLR@<pdfsha>.json",
           "pins": {"1": {"name": "SW", "role": "SW", "net": "/PWR/SW1", "erc_type": "power_out"}},
           "provenance": {"mpn": "schematic_field", "pin_roles": "datasheet:p3 (conf=high)"}}
  },
  "nets": {
    "/PWR/SW1": {"roles": ["switch_node"], "classes": ["SWITCH_NODE", "PWR_2A"], "criticality": 0.9,
                 "electrical": {"f_sw_hz": 1.2e6, "i_max_a": 3.0},
                 "evidence": [{"kind": "rule", "id": "sw_pin+inductor"}], "status": "confirmed"},
    "USB_D_P": {"roles": ["diff_p"], "pair": "USB_D_N", "protocol": "USB2_HS", "z_diff_ohm": 90, "skew_ps_max": 25,
                "evidence": [{"kind": "suffix"}, {"kind": "pin_role", "pins": ["U1.USB_DP", "J1.D+"]}], "status": "proposed"}
  },
  "blocks": [
    {"id": "BUCK1", "type": "buck_sync", "detector": "tmpl:buck_sync@v3", "confidence": 0.97,
     "members": {"controller": "U3", "cin_hf": ["C12"], "cin_bulk": ["C11"], "cboot": ["C13"], "inductor": "L2",
                 "cout": ["C14", "C15"], "fb_top": "R8", "fb_bot": "R9"},
     "nets": {"vin": "+12V", "sw": "/PWR/SW1", "vout": "+5V", "fb": "/PWR/FB1", "pgnd": "GND"},
     "kicad": {"component_class": "BLK_BUCK1", "sheet": "/Power/"}}
  ],
  "constraints": [
    {"id": "c1", "type": "loop_area_min", "block": "BUCK1", "path": ["C12", "U3.VIN", "U3.PGND", "C12"], "hard": false, "weight": 10,
     "bound_mm2": null, "source": "recipe:buck + datasheet:p28 'place input cap as close as possible'"},
    {"id": "c2", "type": "keep_away", "a": {"net": "/PWR/FB1"}, "b": {"net": "/PWR/SW1"}, "min_mm": 1.0, "hard": false, "source": "recipe default"},
    {"id": "c3", "type": "diff_pair", "nets": ["USB_D_P", "USB_D_N"], "z_diff_ohm": 90, "skew_ps": 25, "hard": true, "compile_to": "kicad_dru"}
  ],
  "questions": [{"field": "nets.USB_D_P.protocol", "ask": "Is J1 used at USB 2.0 High-Speed (480 Mb/s)?", "options": ["HS", "FS-only"], "impact": "90Ω controlled impedance"}]
}
```

**LLMs do well (use them for):**
- Reading datasheet prose and tables into typed facts *with page evidence*.
- Recognizing part function from MPN, description and pin names.
- Normalizing pin names to roles.
- Interpreting designer naming conventions and sheet names.
- Proposing block boundaries for unusual circuits.
- **Writing new detector templates** that are then executed.
- Converting qualitative guidelines into constraint types and weights.
- Generating targeted clarifying questions.
- Explaining rationale to the user.

**Needs deterministic code:**
- Parsing and connectivity (union-find, hierarchy expansion).
- Exact subgraph matching (VF2) and the check that every pin is explained.
- Numeric work: Vout from dividers, crystal CL, DC-bias derating, IPC-2152 widths, impedance from stackup.
- Unit and condition normalization.
- Protocol tables (impedance, skew).
- KiCad file writing (net classes, `.kicad_dru`, component classes).
- DRC and recipe verification (loop area, distances, skew).
- Caching and staleness (PDF hash).
- Never let an LLM emit coordinates or millimetre bounds that do not come from a source.

**Highest-leverage near-term build order:**
1. Pin-role ontology plus deterministic net-role and block detectors (port kicad-happy-style rules).
2. A datasheet layout-guideline extractor that produces typed predicates with evidence. This is novel; nothing comparable was found.
3. A recipe engine plus compilation to KiCad 9/10 native intent.
4. Re-use of recipe checkers as post-route acceptance tests.
5. LLM-written templates for the long tail.

### Gaps
- There is no public dataset of KiCad boards labelled with block types, net roles *and* layout constraints for evaluating this front end. A plausible evaluation source is mining existing net-class and component-class assignments and DRC rules from open KiCad projects; the 5,829-project kicad-happy harness corpus and PCB-Bench's 174 OSHWHub projects are candidates. I did not verify whether these contain enough intent annotations.
- I could not verify whether commercial tools (Quilter, Flux, Cadence Allegro X AI, Siemens) publish how their "circuit comprehension" front ends classify nets and blocks (search budget exhausted, hosts blocked).
