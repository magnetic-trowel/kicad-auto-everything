# Licensing for datasets, benchmark boards, rule packs and model weights

Scope: licences of third-party board datasets, of our own data/docs/rule packs, and of model weights and their base models. Not here: which board licence allows which data use (tiers A/B/C, contamination) -> [../data/licensing-tiers-and-contamination.md](../data/licensing-tiers-and-contamination.md); code reuse -> [reuse-matrix](reuse-matrix.md).
Keys: master_metadata.json, run-time fetch, tier R/SA/E, CDLA-Permissive-2.0, ODC-By, ODbL, CC0, facts vs expression, Feist, TI datasheet notice, rule records, base-model licences, OSAID, CC AI-training guidance, footprint corpora

Project licences for our data (CDLA-Permissive-2.0), rule packs (CC0-1.0) and weights (Apache-2.0): [LICENSING.md](../../../LICENSING.md#what-applies-to-what). Below: the evidence and what is not there.

## Board datasets

- **PCBench per-board licences** (tally of `master_metadata.json`: 1,194 designs, 846 repos, retrieved 2023-08) [P] ([metadata](https://github.com/PCBench/PCBench/blob/HEAD/PCBs/master_metadata.json)):
  - none/not found 648 (54.3%), MIT 147 (12.3%), GPL-3.0 106 (8.9%), "Other" 96 (8.0%); Apache-2.0 38, GPL unspecified 33, GPL-2.0 20, CC-BY-SA 18, CERN-OHL 18, BSD 16, CC unspecified 15, CC-BY 11; LGPL 6, WTFPL 5, CC0 5, Unlicense 5, AGPL 4, MPL-2.0 2, TAPR 1 (≈14% copyleft).
  - By repo: 449/846 (53.1%) no licence.
  - kicad-tools: "MIT repository, mixed per-board licenses — boards are cache-only". A repo-level MIT licence cannot relicense the boards: ship manifests, fetch at run time [P].
  - Other tallies of the same pool -> [../data/corpora-and-yield.md](../data/corpora-and-yield.md#pcbench-source-pool-of-pcbworld-d3).
- **Run-time fetch precedents** [P]: PCBWorld rebuilds D3 at run time (`prepare_pcbench.sh`); Freerouting's PCBench integration expects a local clone, converted DSNs gitignored; kicad-tools fetches "at run time into a gitignored cache" from a `boards.toml` manifest (pinned URL + SHA, path, upstream licence); kicad-happy-testharness requires pinned 40-character hashes.
- **bshada/open-schematics** (HF): `license: cc-by-4.0` card, data "collected from publicly available data from the web", no per-record licence. Seth Hillbrand: "Yet another 'open' dataset that merely strips the license and origin of thousands of people's projects". kicad-tools disagrees [P].
- Other datasets [P]: OmniLayout/OmniRouting "no licence grant of any kind", papers CC BY-NC-ND 4.0; PCBSchemaGen-Benchmarks (MIT card) and kicad-netlist-sft-dataset (Apache-2.0 card), provenance not audited; commaai/PCBGolf: no licence = all rights reserved.
- **Unlicensed code:** "all copyrightable works are copyrighted by default"; GitHub's ToS grants only use, display and fork "through the Service"; choosealicense: "Ask the maintainers nicely to add a license" [P].
- **Open-hardware licences on boards** [P]: CERN-OHL v2 S/W/P. S: "Including Covered Source in a larger work is modifying"; "Product" covers anything "arising from the use, application or processing of Covered Source"; express patent licence §7 (clause list -> [../data/licensing-tiers-and-contamination.md](../data/licensing-tiers-and-contamination.md#licence-texts-and-precedents)). W: "External Material" via documented interfaces. FSF recommends GPLv3+ for circuit designs; "copyright does not cover making physical hardware from a drawing" in many situations.

### Tiers for board bundles

[I]. Scheme for redistributed bundles (compare the data-use tiers A/B/C in [licensing-tiers-and-contamination](../data/licensing-tiers-and-contamination.md#licence-tiers-i); conflict noted there):

| Tier | Licences | Handling |
|---|---|---|
| R | permissive, CC-BY, CC0, CERN-OHL-P | redistributable with a generated NOTICE |
| SA | GPL, CC-BY-SA, CERN-OHL-S/W | separate bundles under their own licences only |
| E | unlicensed or "Other" | fetch-only local evaluation |
| — | NC/ND | excluded |

Never mix GPL or CC-BY-SA boards into a CDLA bundle [P].

- Manifest schema: `repo_url`, `commit_sha`, `path`, `spdx_license`, `license_evidence_url`, `attribution`, `retrieved_at`, `tier`; fetch into a gitignored cache.
- Never re-host PCBench, open-schematics, OmniLayout or PCBGolf content.
- Footprint corpora: any extracted footprint or 3D-model corpus is CC-BY-SA-4.0 WITH KiCad-libraries-exception, kept separate. Boards that merely embed library footprints carry no obligation ([library exception](kicad-and-gpl-ecosystem-notes.md#kicad-libraries-and-outputs)).
- Test fixtures: KiCad demos are CC BY-SA 4.0: read them from the user's install (POA's `kicad_corpus` pattern) or annotate them in `REUSE.toml`. Antmicro Apache-2.0 boards work as routed ground truth.
- Provide a takedown and contact process and a data card for every dataset.

## Licenses for our own data, docs and rules

- **CDLA-Permissive-2.0:** share "so long as the Data Recipient makes available the text"; "does not impose any restriction or obligations with respect to the use, modification, or sharing of Results" (Results include ML models) [P] ([CDLA](https://cdla.dev/permissive-2-0/)).
- Alternatives considered [P]: ODC-By 1.0 requires attribution of public use; CC BY 4.0 has a sui generis database section, FSF calls it GPL-compatible but "should not be used on software"; ODbL is GPL-incompatible.
- **CC0:** FSF recommends it for non-software, but it "does not grant you any patent licenses" [P].
- **Facts vs expression** [P]: 17 U.S.C. §102(b): no copyright in "any idea, procedure, process, system, method of operation, concept, principle, or discovery"; *Feist*: "facts are not copyrightable … the copyright in a factual compilation is thin"; Circular 33: "no copyrightable authorship in a mere listing of ingredients".
- **TI datasheet notice** (contractual reproduction restriction): "TI grants you permission to use these resources only for development of an application that uses the TI products … Other reproduction and display of these resources is prohibited". Enforceability against non-customers: question for counsel [P] ([TPS62130](https://www.ti.com/lit/ds/symlink/tps62130.pdf)).
- Commercial physics definitions: Quilter's PRCs and comprehension heuristics are facts and methods: restate, don't copy the text ([../landscape/quilter.md](../landscape/quilter.md)) [I].
- **Rule records** [I]: no verbatim text, tables, figures or PDFs; facts restated in our own words with structured citations: vendor, document ID, revision, section or page, URL, access date + paraphrased condition, value, rationale, under CC0-1.0. Executable checks and `.kicad_dru` generators are code (GPL-3.0-or-later).

## Model weights

| Base family | License | Fit for Apache-2.0 weights |
|---|---|---|
| Qwen3 (8B/32B/235B-A22B), Qwen3.5 (0.8B–35B-A3B), Qwen3.6 (27B, 35B-A3B), Qwen3-Coder; Qwen2.5-7B/VL-7B/Coder-32B | Apache-2.0 | Yes |
| Mistral-7B-Instruct-v0.3, OLMo-2, gpt-oss-20b/120b | Apache-2.0 | Yes |
| Phi-4, DeepSeek-R1 | MIT | Yes (DeepSeek-V3's card lists no license) |
| Qwen2.5-72B / VL-72B | "qwen" (100M MAU cap; "Built with Qwen") | No |
| Llama 3/3.1/3.3 | llama licence ("Built with Llama"; names must start with "Llama"; AUP; 700M MAU). FSF: "not a free software license" | No |
| Gemma 3 | Gemma terms (restrictions flow down even via synthetic-data distillation) | No |
| OpenRAIL family | Use restrictions flow down; FSF: nonfree | No |

- Qwen3.5-397B's licence not checked [P].
- **OSAID 1.0** requires data information, code and parameters under OSI-approved terms, incl. "the complete description of all data used for training" [P].
- **Anthropic Commercial Terms:** customers may not use the services "to build a competing product or service, including to train competing AI models". A narrow layout model probably does not count; get it reviewed [P/I].
- **CC guidance on AI training (2025):** conservatively, "When training data is subject to the ShareAlike condition, model outputs and the model itself, if shared publicly, should be made available under the same CC license"; ND works "should not be used as training data". Following it "will almost certainly lead to overcompliance". Attribution is triggered if a model memorizes substantially similar expression [P].
- Rule [I]: Apache/MIT bases only (training on copyleft/share-alike boards is legally unresolved); check AI-provider terms before training on generated outputs; train on tier-R + synthetic and solver- or DRC-generated supervision; record which models generated any synthetic data; ship an OSAID-style model card.

## Open questions

- No case law on whether trained weights are adaptations of copyleft or share-alike training data. CERN-OHL-S "Product" might reach a model (untested reading).
- EU sui generis database rights not researched. Analog Devices, ST, NXP and Microchip document terms not retrieved; OpenAI's terms page did not render.
- No official KiCad statement on ML training with KiCad library data.
- The PCBench tally reflects GitHub's 2023 repo-level detection, which may describe the software licence rather than the hardware.

## Sources

- research notes: [licensing.md § 1G–H, § 3, § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md); [kicad_mcp_codebases.md § 4 (fixtures)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
- primary: [CC AI-training guidance (PDF)](https://creativecommons.org/wp-content/uploads/2025/05/Using-CC-licensed-Works-for-AI-Training.pdf), [OSAID 1.0](https://opensource.org/ai/open-source-ai-definition), [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms), [kicad-tools benchmarks/external](https://github.com/rjwalters/kicad-tools/blob/HEAD/benchmarks/external/README.md)
- related: [compliance-checklist](compliance-checklist.md), [../landscape/measured-tool-comparisons.md](../landscape/measured-tool-comparisons.md)
