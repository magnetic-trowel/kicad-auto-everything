# Open PCB layout corpora: supply, quality, expected yield

**TL;DR**
- **Raw supply is in the tens of thousands of boards:**
  - open-schematics: 87,931 records;
  - kicad-happy catalog: 5,856 repos with 18,679 PCB files;
  - PCBench: 1,183 boards;
  - OSHWA: 3,452 projects [P].
- **Usable supply is one to two orders of magnitude smaller.**
  - PCBench is **62% unlicensed**, **89% 2-layer**, and has **only 23 KiCad 6+ boards**.
  - Only **33%** of licensed, fully routed human boards pass their *own* DRC [P, measured].
- Expect **low thousands** of licence-clean, fully routed boards, and **a few hundred** that are also DRC-clean or have 4+ layers [I].
- Use open-schematics and kicad-happy as **discovery indexes**, not training sets. Re-fetch at pinned SHAs with your own licence detection and DRC qualification [I].
- **Hobby bias:** keyboards and ESP32 boards dominate; the median board has about 60 parts [P, measured].

## Key facts

### PCBench (source pool of PCBWorld D3) [P, measured by note author]

Census of all 1,183 `PCBs/*/metadata.json` files ([repo](https://github.com/PCBench/PCBench)):
- **Size history:** 164 boards retrieved in 2023-04 plus 1,018 in 2023-08, from 842 repos and 561 authors. This **resolves the "164 vs 679" discrepancy**: the README's 164 is the first batch, and PCBWorld kept 679 of about 1,182 after conversion.
- **Licences:**
  - none or unclear: **735 (62.1%)**;
  - permissive: 221 (18.7%), of which MIT 128, Apache 28, CC-BY 11;
  - reciprocal: 213 (18.0%), of which GPL-3.0 105, GPL-2.0 about 20, CC-BY-SA-4.0 17;
  - unspecified CC: 14.
- **CAD versions:** KiCad 4: 651; KiCad 5: 377; KiCad 3: 88; other pre-6: 43; **KiCad 6+: 23**.
- **Layers:** 2-layer 1,052 (89%), 4-layer 126, 6-layer 3, 8-layer 1.
- The boards are "KiCad 5 files with no project file, so their rules are KiCad's defaults" ([circuit-skills collect.py](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/collect.py); that repo has no licence, so facts only) [P].
- **Minor conflict:** 1,183 in this census vs PCBWorld's "1,182".

### circuit-skills licensed corpus (most rigorous public collector) [P, third-party, unreviewed]

**Pipeline:**
- search with queries such as `topic:kicad stars:>=10`, `topic:oshw stars:>=10`, `language:"KiCad Layout" stars:>=5`, against a licence allow-list (MIT, Apache-2.0, BSD-3, CC0, CC-BY-4.0, CC-BY-SA-4.0, CERN-OHL-P/W/S-2.0, GPL-3.0);
- pick `.kicad_pcb` files that have a `.kicad_pro`, at most 2 per repo, deduplicated by blob hash, skipping lib/template/panel/backup/test/example paths;
- fetch at a pinned commit into a cache, "never into the repo";
- qualify: opens, 1–4 copper layers, ≥10 segments, rejected on **any** unconnected item;
- record `ref_drv` (designer board) and `bare_drv` (stripped board);
- bucket by connections: easy <40, medium <150, hard otherwise.

**Manifest at commit `34e3841`** [P, measured] ([manifest](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/manifest.json)):
- **235 boards from 170 repos**, out of 423 candidates;
- licences: MIT 75, GPL-3.0 67, CERN-OHL-S 25, CERN-OHL-P 25, Apache 19, CC-BY-SA 10, CERN-OHL-W 5, CC-BY 4, BSD-3 3, CC0 2;
- 2-layer 178, 4-layer 57;
- parts: median 59, max 558; connections: median 119;
- **`ref_drv` median 4, max 938; only 77 of 235 (33%) at zero**;
- `bare_drv` is zero for only 73 of 235, so most human placements already carry courtyard or silk errors.

### kicad-happy test corpus [P]

**History and caveats:**
- It started at 1,052 curated repos. 87 were purged (18 Eagle-only, 14 tool/library, 22 PCB-only, 33 with <3 components).
- It was expanded in April 2026 to **5,822 repos** across GitHub, GitLab and Codeberg, all pinned.
- **Author's bias statement:** "ESP32 dev boards and mechanical keyboards… simple power supplies". RF, precision analog, complex power and mixed-signal are under-represented ([methodology](https://github.com/aklofas/kicad-happy-testharness/blob/main/methodology.md)).
- The analyzer cannot associate a regulator on one sheet with decaps on another.
- **Totals:** 6,845 schematics, 3,498 PCB files analyzed, 312,956 components, 531,418 nets, KiCad 5–10.

**Catalog profile** [P, measured] (5,856 entries, [repo_catalog.json](https://github.com/aklofas/kicad-happy-testharness/blob/main/reference/repo_catalog.json)):
- 5,707 repos with PCBs, **18,679 PCB files** (including revisions and backups);
- KiCad generation: mixed 3,824, k7 713, k6 630, k5 619, **k9 29, k10 21**;
- max layers: 2-layer 3,619 (63%), 4-layer 1,028, 6-layer 100, 8-layer 22, ≥10 layers 10, unparsed 621;
- components: median 65, p90 488, p99 2,284;
- categories: Misc 1,810, Keyboards 449, Synths 324, Motor 315, LED 304, ESP32 294, Arduino 294, RF/SDR 254, IoT 250, Retro 235, USB 214, Power 207, RP2040 192, STM32 179, CubeSat 39, SBC 33;
- detectors fired: decoupling 3,848, regulators 2,979, crystals 1,852, USB 809;
- median documentation score 0; `has_gerbers` on 2,213 repos.

**Licence spot-check** of 54 random repos: no licence file 41%, permissive 37%, reciprocal 22% (±13 pp).

### open-schematics (Hugging Face) [P] ([card](https://huggingface.co/datasets/bshada/open-schematics))
- **87,931 rows, 316.8 GB**, with a CC-BY-4.0 tag but "comply with the original licenses", and no per-row licence.
- PCBs over 10 MB dropped; JSON for about 85% of rows; PCB images missing for about 55%.
- 11,966 downloads; at least 12 re-uploads.
- **kicad-tools census** of 22 pinned boards ([doc](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/corpus-benchmark-feasibility.md)) [P, third-party]:
  - only 10/22 featurizable and **8/22 usable** before a parser fix (9 used legacy `(module …)`); **18/22 and 16/22 (72.7%)** after;
  - residual blockers: no net with 2+ pads, no copper, no outline, legacy arc outlines;
  - **lessons:** "a pour counts as copper" (a trace-only test misgrades 7 of 8); adopt each board's `(setup …)` rules; on a dense board (11.4 pads/cm²) their router reached 20% vs the human's 100%.

### Other datasets
- **SchGen:** 2,105 KiCad schematics (1,390 unique) rebuilt from SparkFun designs under CC BY-SA 4.0, ×4 to 8,420 samples; out-of-distribution set of 988 from 20 GitHub projects ([2605.30345](https://arxiv.org/abs/2605.30345)) [P].
- **CELUS/Kassel GNN sets:** pull-ups 2,396, RC filters 849, decaps 944; 100–124 nodes on average ([2506.10577](https://arxiv.org/abs/2506.10577); only example graphs are public) [P].
- **KiCad 9+ corpora:** 98 permissive / 209 copyleft, split after a legal audit ([permissive](https://huggingface.co/datasets/electron-rare/kicad9plus-permissive), [copyleft](https://huggingface.co/datasets/electron-rare/kicad9plus-copyleft)) [P].
- **Ohmatic human-verified-schematics-v1:** 1,000 schematics in trust tiers (685 grandfathered + 315 with ≥2 independent evidence families) [P].
- **mascarade-kicad-dataset:** 2,645 Q&A, **79.7% LLM-generated**; a heuristic detector overcounted human content 5.6× [P].
- **R3SET:** 338 requirements → 92 blocks from 8 OSH projects, plus 100 distractors; hybrid retrieval 71% Hit@1, 92% Hit@5 ([DOI](https://doi.org/10.1115/1.4071107)) [S].
- **BenchPCNP:** 50 boards with module labels (see [../llm/block-recognition.md](../llm/block-recognition.md)) [P].
- **OSHWA:** 3,452 certified projects (2026-10-20); earlier 2,972 (Feb 2025) and 3,107 (Jul 2025) [P/S].
- **GitHub topic `kicad`:** 4,559 repos [S].
- **Adafruit and SparkFun:** Eagle files under CC-BY-SA [S].
- **OSH documentation:** of 242 products, about a third were adequately documented [S].
- **Not useful:** PCB-Layout (668 photo/layout pairs) for placement. OmniSch (1,854 schematics) is an upstream netlist benchmark [P].
- **Survey:** 227 papers screened, 80 included; "domain-specific data scarcity" is a key challenge ([2606.17074](https://arxiv.org/abs/2606.17074)) [P].

### Expected yield funnel [I]
1. Discovery: about 10⁴ repos.
2. Licence-clean: about 40–60% (PCBench 38% clear; kicad-happy 59% with a licence file).
3. Parseable and modern: legacy formats are 41% of one open-schematics sample and 97% of PCBench.
4. Fully routed: 235 boards from 423 candidate repos in circuit-skills.
5. DRC-clean under the board's own rules: about 33%.

## Recommendations for our system

1. Build a **pinned, licence-tiered corpus** with circuit-skills-style qualification. Store pointers plus SHA-256 in the repo and payloads in a git-ignored cache. See [data-pipeline-plan.md](data-pipeline-plan.md) [I].
2. **Treat human geometry as relational structure, not ground truth.** DRC-clean human boards are the exception; legality comes from our solver.
3. **Refuse rather than half-parse** legacy constructs; run `kicad-cli pcb upgrade`; count pours as copper; adopt each board's own rules.
4. Weight professional and DRC-clean boards, and stratify by layer count to counter hobby bias.

## Conflicts and open questions

- There is no authoritative count of `.kicad_pcb` files on GitHub or GitLab; code search was blocked.
- OSHWHub, Kitspace, Hackaday.io and CERN OHR counts are missing.
- open-schematics' KiCad/Eagle/Altium split and routed fraction were not measured.
- No Altium layout ML dataset was found.

## Sources
- research notes: [learning_from_layout_data.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md)
- related correction: [verification_papers.md § 1 row 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [licensing-tiers-and-contamination.md](licensing-tiers-and-contamination.md), [measured-priors.md](measured-priors.md), [data-pipeline-plan.md](data-pipeline-plan.md)
