# Licensing for datasets, benchmark boards, rule packs and model weights

**TL;DR**
- **Third-party boards keep their upstream licenses.** PCBench's repo is MIT, but **54.3% of its 1,194 designs have no license** and about 14% are copyleft. A repo-level MIT license cannot relicense the boards. Ship **manifests** and fetch at run time [P].
- **Our own datasets, manifests and labels are CDLA-Permissive-2.0**, which puts "no restriction" on Results, including ML models. Never mix GPL or CC-BY-SA boards into a CDLA bundle [P].
- **Rule packs are CC0-1.0:** facts and parameters restated in our own words, with structured citations. No verbatim text, tables, figures or PDFs. TI's datasheet notice adds a contractual reproduction restriction [P].
- **Weights are Apache-2.0**, fine-tuned only from Apache or MIT bases (Qwen3/3.5/3.6, Mistral-7B, OLMo-2, gpt-oss, Phi-4, DeepSeek-R1). Avoid Llama, Gemma, Qwen-license 72B and RAIL bases. Check AI-provider terms before training on generated outputs [P].
- **Training on copyleft or share-alike boards is legally unresolved.** For clean Apache weights, train on permissive boards plus synthetic and solver-generated data [I].

## Key facts

### Board datasets
- **PCBench per-board licences** (my tally of `master_metadata.json`, 1,194 designs from 846 repos, retrieved 2023-08):
  - none/not found 648 (54.3%), MIT 147 (12.3%), GPL-3.0 106 (8.9%), "Other" 96 (8.0%);
  - Apache-2.0 38, GPL unspecified 33, GPL-2.0 20, CC-BY-SA 18, CERN-OHL 18, BSD 16, CC unspecified 15, CC-BY 11;
  - LGPL 6, WTFPL 5, CC0 5, Unlicense 5, AGPL 4, MPL-2.0 2, TAPR 1.
  - By repo, 449/846 (53.1%) have no license.
  - kicad-tools records it as "MIT repository, mixed per-board licenses — boards are cache-only" [P] ([metadata](https://github.com/PCBench/PCBench/blob/HEAD/PCBs/master_metadata.json)).
- **Run-time fetch precedents:** PCBWorld rebuilds D3 at run time (`prepare_pcbench.sh`). Freerouting's PCBench integration expects a local clone, with converted DSNs gitignored. kicad-tools fetches "at run time into a gitignored cache" from a `boards.toml` manifest (pinned URL + SHA, path, upstream license). kicad-happy-testharness requires pinned 40-character hashes [P].
- **bshada/open-schematics** (HF): `license: cc-by-4.0` card, data "collected from publicly available data from the web", no per-record license. Seth Hillbrand: "Yet another 'open' dataset that merely strips the license and origin of thousands of people's projects". kicad-tools disagrees [P].
- **Other datasets:**
  - OmniLayout/OmniRouting: "no licence grant of any kind"; papers CC BY-NC-ND 4.0.
  - PCBSchemaGen-Benchmarks (MIT card) and kicad-netlist-sft-dataset (Apache-2.0 card): provenance not audited.
  - commaai/PCBGolf: no license, so all rights reserved [P].
- **Unlicensed code:** "all copyrightable works are copyrighted by default". GitHub's ToS grants only use, display and fork "through the Service". choosealicense: "Ask the maintainers nicely to add a license" [P].
- **Open-hardware licences seen on boards:**
  - CERN-OHL v2 S/W/P. S: "Including Covered Source in a larger work is modifying", and "Product" covers anything "arising from the use, application or processing of Covered Source"; express patent licence §7. W: "External Material" via documented interfaces.
  - FSF recommends GPLv3+ for circuit designs; "copyright does not cover making physical hardware from a drawing" in many situations [P].

### Licenses for our own data, docs and rules
- **CDLA-Permissive-2.0:** share "so long as the Data Recipient makes available the text"; "does not impose any restriction or obligations with respect to the use, modification, or sharing of Results" (Results include ML models) [P] ([CDLA](https://cdla.dev/permissive-2-0/)).
- **Alternatives considered:** ODC-By 1.0 requires attribution of public use. CC BY 4.0 has a sui generis database section; FSF says it is GPL-compatible but "should not be used on software". ODbL is GPL-incompatible [P].
- **CC0:** FSF recommends it for non-software, but it "does not grant you any patent licenses" [P].
- **Facts versus expression:**
  - 17 U.S.C. §102(b): no copyright in "any idea, procedure, process, system, method of operation, concept, principle, or discovery".
  - *Feist*: "facts are not copyrightable … the copyright in a factual compilation is thin".
  - Circular 33: "no copyrightable authorship in a mere listing of ingredients" [P].
- **TI datasheet notice:** "TI grants you permission to use these resources only for development of an application that uses the TI products … Other reproduction and display of these resources is prohibited". Its enforceability against non-customers is a question for counsel [P] ([TPS62130](https://www.ti.com/lit/ds/symlink/tps62130.pdf)).
- **Commercial physics definitions:** Quilter's PRCs and comprehension heuristics are facts and methods; restate them, don't copy the text ([../landscape/quilter.md](../landscape/quilter.md)) [I].

### Model weights
| Base family | License | Fit for Apache-2.0 weights |
|---|---|---|
| Qwen3 (8B/32B/235B-A22B), Qwen3.5 (0.8B–35B-A3B), Qwen3.6 (27B, 35B-A3B), Qwen3-Coder; Qwen2.5-7B/VL-7B/Coder-32B | Apache-2.0 | Yes |
| Mistral-7B-Instruct-v0.3, OLMo-2, gpt-oss-20b/120b | Apache-2.0 | Yes |
| Phi-4, DeepSeek-R1 | MIT | Yes (DeepSeek-V3's card lists no license) |
| Qwen2.5-72B / VL-72B | "qwen" (100M MAU cap; "Built with Qwen") | No |
| Llama 3/3.1/3.3 | llama licence ("Built with Llama"; names must start with "Llama"; AUP; 700M MAU). FSF: "not a free software license" | No |
| Gemma 3 | Gemma terms (restrictions flow down even via synthetic-data distillation) | No |
| OpenRAIL family | Use restrictions flow down; FSF: nonfree | No |

- Qwen3.5-397B's licence was not checked [P].
- **OSAID 1.0** requires data information, code and parameters under OSI-approved terms, including "the complete description of all data used for training" [P].
- **Anthropic Commercial Terms:** customers may not use the services "to build a competing product or service, including to train competing AI models". A narrow layout model probably does not count, but get that reviewed [P/I].
- **CC guidance on AI training (2025):** conservatively, "When training data is subject to the ShareAlike condition, model outputs and the model itself, if shared publicly, should be made available under the same CC license"; ND works "should not be used as training data". Following it "will almost certainly lead to overcompliance". Attribution is triggered if a model memorizes substantially similar expression [P].

## Recommendations for our system
- **Manifest schema:** `repo_url`, `commit_sha`, `path`, `spdx_license`, `license_evidence_url`, `attribution`, `retrieved_at`, `tier`. Fetch into a gitignored cache [I].
- **Tiers:**
  - **R:** permissive, CC-BY, CC0, CERN-OHL-P; redistributable with a generated NOTICE.
  - **SA:** GPL, CC-BY-SA, CERN-OHL-S/W; separate bundles under their own licences only.
  - **E:** unlicensed or "Other"; fetch-only local evaluation.
  - Exclude NC/ND. Never re-host PCBench, open-schematics, OmniLayout or PCBGolf content [I].
- **Footprint corpora:** any extracted footprint or 3D-model corpus is CC-BY-SA-4.0 WITH KiCad-libraries-exception, kept separate. Boards that merely embed library footprints carry no obligation [I].
- **Test fixtures:** KiCad demos are CC BY-SA 4.0; read them from the user's install (POA's `kicad_corpus` pattern) or annotate them in `REUSE.toml`. Antmicro Apache-2.0 boards work as routed ground truth [I].
- **Rule records** carry vendor, document ID, revision, section or page, URL and access date, plus a paraphrased condition, value and rationale, under CC0-1.0. Executable checks and `.kicad_dru` generators are code (GPL-3.0-or-later) [I].
- **Weights:** Apache/MIT bases only. Train on tier-R plus synthetic and solver- or DRC-generated supervision. Record which models generated any synthetic data. Ship an OSAID-style model card [I].
- **Provide a takedown and contact process and a data card** for every dataset [I].

## Conflicts and open questions
- No case law on whether trained weights are adaptations of copyleft or share-alike training data. CERN-OHL-S "Product" might reach a model (untested reading).
- EU sui generis database rights were not researched. Analog Devices, ST, NXP and Microchip document terms were not retrieved; OpenAI's terms page did not render.
- No official KiCad statement on ML training with KiCad library data.
- The PCBench tally reflects GitHub's 2023 repo-level detection, which may describe the software license rather than the hardware.

## Sources
- research notes:
  - [licensing.md § 1G–H, § 3, § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
  - [kicad_mcp_codebases.md § 4 (fixtures)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
- primary: [CC AI-training guidance (PDF)](https://creativecommons.org/wp-content/uploads/2025/05/Using-CC-licensed-Works-for-AI-Training.pdf), [OSAID 1.0](https://opensource.org/ai/open-source-ai-definition), [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms), [kicad-tools benchmarks/external](https://github.com/rjwalters/kicad-tools/blob/HEAD/benchmarks/external/README.md)

See also: [reuse-matrix.md](reuse-matrix.md), [compliance-checklist.md](compliance-checklist.md), [../landscape/measured-tool-comparisons.md](../landscape/measured-tool-comparisons.md)
