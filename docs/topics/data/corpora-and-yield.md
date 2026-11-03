# Open PCB layout corpora: supply, quality, expected yield

Scope: how many public PCB layouts exist, their licence/format/layer/DRC quality, and the expected usable yield. Not here: the boards we vetted -> [open-board-sources](open-board-sources.md), [wide-board-corpus](wide-board-corpus.md); tier rules -> [licensing-tiers-and-contamination](licensing-tiers-and-contamination.md).
Keys: PCBench census, circuit-skills, ref_drv, bare_drv, kicad-happy catalog, open-schematics, kicad-tools census, yield funnel, hobby bias, unlicensed share

## Supply vs usable yield

- Raw supply: tens of thousands of boards (open-schematics, kicad-happy, PCBench, OSHWA, below); usable supply 1–2 orders of magnitude smaller [P].
- Only **33%** of licensed, fully routed human boards pass their *own* DRC [P, measured] (circuit-skills, below).
- Expect **low thousands** of licence-clean, fully routed boards; **a few hundred** also DRC-clean or 4+ layers [I]. Measured result of our own pass: [wide-board-corpus](wide-board-corpus.md).
- Use open-schematics and kicad-happy as discovery indexes; re-fetch at pinned SHAs with own licence detection and DRC qualification [I].
- Hobby bias: keyboards and ESP32 boards dominate; median board ≈ 60 parts [P, measured].

## PCBench (source pool of PCBWorld D3)

Census of all 1,183 `PCBs/*/metadata.json` files ([repo](https://github.com/PCBench/PCBench)) [P, measured by note author]:
- Batches: 164 boards retrieved 2023-04 + 1,018 in 2023-08, from 842 repos, 561 authors (dates, CAD versions and layer counts each sum to 1,182, one short of 1,183 files). Resolves "164 vs 679": README's 164 = first batch; PCBWorld kept 679 of ≈1,182 after conversion.
- Licences: none/unclear **735 (62.1%)**; permissive 221 (18.7%: MIT 128, Apache 28, CC-BY 11); reciprocal 213 (18.0%: GPL-3.0 105, GPL-2.0 ≈20, CC-BY-SA-4.0 17); unspecified CC 14.
- CAD: KiCad 4: 651; KiCad 5: 377; KiCad 3: 88; other pre-6: 43; **KiCad 6+: 23**.
- Layers: 2-layer 1,052 (89%), 4-layer 126, 6-layer 3, 8-layer 1.
- "KiCad 5 files with no project file, so their rules are KiCad's defaults" ([circuit-skills collect.py](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/collect.py); repo unlicensed, facts only) [P].

Unlicensed share by source file (not reconciled; canonical list):

| File counted | Unlicensed | Doc |
|---|---|---|
| per-board `metadata.json` (1,183) | 735 (62.1%) | this section |
| `master_metadata.json` (1,194) | 648 (54.3%) | [../licensing/data-rulepacks-weights.md](../licensing/data-rulepacks-weights.md#board-datasets) ([licensing.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)) |
| Freerouting fixture metadata (1,142) | 743 empty + 91 NOASSERTION | [open-board-sources](open-board-sources.md) |

Minor conflict: 1,183 here vs PCBWorld's "1,182".

## circuit-skills licensed corpus (most rigorous public collector)

[P, third-party, unreviewed]. Pipeline:
1. Search, e.g. `topic:kicad stars:>=10`, `topic:oshw stars:>=10`, `language:"KiCad Layout" stars:>=5`, against an allow-list (MIT, Apache-2.0, BSD-3, CC0, CC-BY-4.0, CC-BY-SA-4.0, CERN-OHL-P/W/S-2.0, GPL-3.0).
2. Pick `.kicad_pcb` with a `.kicad_pro`, ≤2 per repo, dedup by blob hash, skip lib/template/panel/backup/test/example paths.
3. Fetch at pinned commit into a cache, "never into the repo".
4. Qualify: opens, 1–4 copper layers, ≥10 segments, reject on **any** unconnected item.
5. Record `ref_drv` (designer board DRC) and `bare_drv` (stripped board DRC).
6. Bucket by connections: easy <40, medium <150, hard otherwise.

Manifest at commit `34e3841` ([manifest](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/manifest.json)) [P, measured]:
- **235 boards from 170 repos**, of 423 candidates; 2-layer 178, 4-layer 57 (= punkfab/pcb-corpus boards).
- Licences: MIT 75, GPL-3.0 67, CERN-OHL-S 25, CERN-OHL-P 25, Apache 19, CC-BY-SA 10, CERN-OHL-W 5, CC-BY 4, BSD-3 3, CC0 2.
- Parts median 59, max 558; connections median 119.
- **`ref_drv` median 4, max 938; only 77 of 235 (33%) at zero.**
- `bare_drv` = 0 for only 73 of 235: most human placements already carry courtyard or silk errors.

## kicad-happy test corpus

History [P]: 1,052 curated repos, 87 purged (18 Eagle-only, 14 tool/library, 22 PCB-only, 33 with <3 components); expanded April 2026 to **5,822 repos** (GitHub, GitLab, Codeberg), all pinned. Totals: 6,845 schematics, 3,498 PCB files analysed, 312,956 components, 531,418 nets, KiCad 5–10.
- Author's bias statement: "ESP32 dev boards and mechanical keyboards… simple power supplies"; RF, precision analog, complex power, mixed-signal under-represented ([methodology](https://github.com/aklofas/kicad-happy-testharness/blob/main/methodology.md)).
- Analyzer cannot associate a regulator on one sheet with decaps on another.

Catalog profile (5,856 entries, [repo_catalog.json](https://github.com/aklofas/kicad-happy-testharness/blob/main/reference/repo_catalog.json)) [P, measured]:

| Measure | Value |
|---|---|
| Repos with PCBs / PCB files | 5,707 / **18,679** (incl. revisions, backups) |
| KiCad generation | mixed 3,824, k7 713, k6 630, k5 619, **k9 29, k10 21** |
| Max layers | 2: 3,619 (63%), 4: 1,028, 6: 100, 8: 22, ≥10: 10, unparsed 621 |
| Components | median 65, p90 488, p99 2,284 |
| Categories | Misc 1,810, Keyboards 449, Synths 324, Motor 315, LED 304, ESP32 294, Arduino 294, RF/SDR 254, IoT 250, Retro 235, USB 214, Power 207, RP2040 192, STM32 179, CubeSat 39, SBC 33 |
| Detectors fired | decoupling 3,848, regulators 2,979, crystals 1,852, USB 809 |
| Docs | median documentation score 0; `has_gerbers` 2,213 repos |
| Licence spot-check (54 random repos) | no licence file 41%, permissive 37%, reciprocal 22% (±13 pp) |

## open-schematics (Hugging Face)

[P] ([card](https://huggingface.co/datasets/bshada/open-schematics)): **87,931 rows, 316.8 GB**; CC-BY-4.0 tag but "comply with the original licenses", no per-row licence; PCBs >10 MB dropped; JSON for ≈85% of rows; PCB images missing for ≈55%; 11,966 downloads; ≥12 re-uploads.

kicad-tools census of 22 pinned boards ([doc](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/corpus-benchmark-feasibility.md)) [P, third-party]:
- Before parser fix: 10/22 featurizable, **8/22 usable** (9 used legacy `(module …)`); after: **18/22 and 16/22 (72.7%)**.
- Residual blockers: no net with 2+ pads, no copper, no outline, legacy arc outlines.
- Lessons: "a pour counts as copper" (a trace-only test misgrades 7 of 8); adopt each board's `(setup …)` rules; on a dense board (11.4 pads/cm²) their router reached 20% vs the human's 100%.

## Other datasets

| Dataset | Facts | Tag |
|---|---|---|
| SchGen | 2,105 KiCad schematics (1,390 unique) rebuilt from SparkFun designs, CC BY-SA 4.0, ×4 → 8,420 samples; OOD set 988 from 20 GitHub projects ([2605.30345](https://arxiv.org/abs/2605.30345)) | [P] |
| CELUS/Kassel GNN sets | pull-ups 2,396, RC filters 849, decaps 944; 100–124 nodes avg ([2506.10577](https://arxiv.org/abs/2506.10577); only example graphs public) | [P] |
| KiCad 9+ corpora | 98 permissive / 209 copyleft, split after a legal audit ([permissive](https://huggingface.co/datasets/electron-rare/kicad9plus-permissive), [copyleft](https://huggingface.co/datasets/electron-rare/kicad9plus-copyleft)) | [P] |
| Ohmatic human-verified-schematics-v1 | 1,000 schematics in trust tiers (685 grandfathered + 315 with ≥2 independent evidence families) | [P] |
| mascarade-kicad-dataset | 2,645 Q&A, **79.7% LLM-generated**; a heuristic detector overcounted human content 5.6× | [P] |
| R3SET | 338 requirements → 92 blocks from 8 OSH projects + 100 distractors ([DOI](https://doi.org/10.1115/1.4071107)); retrieval results -> [layout-retrieval-and-reuse](layout-retrieval-and-reuse.md#structural-retrieval) | [S] |
| BenchPCNP | 50 boards with module labels -> [../llm/block-recognition.md](../llm/block-recognition.md) | [P] |
| OSHWA | 3,452 certified projects (2026-10-20); 2,972 (Feb 2025), 3,107 (Jul 2025) | [P/S] |
| GitHub topic `kicad` | 4,559 repos | [S] |
| Adafruit, SparkFun | Eagle files, CC-BY-SA | [S] |
| OSH documentation | of 242 products ≈ a third adequately documented | [S] |
| Not useful | PCB-Layout (668 photo/layout pairs) for placement; OmniSch (1,854 schematics) = upstream netlist benchmark | [P] |
| Survey | 227 papers screened, 80 included; "domain-specific data scarcity" a key challenge ([2606.17074](https://arxiv.org/abs/2606.17074)) | [P] |

## Expected yield funnel [I]

1. Discovery: ≈10⁴ repos.
2. Licence-clean: ≈40–60% (PCBench 38% clear; kicad-happy 59% with a licence file).
3. Parseable and modern: legacy formats = 41% of one open-schematics sample, 98% of PCBench.
4. Fully routed: 235 boards from 423 candidate repos (circuit-skills).
5. DRC-clean under own rules: ≈33%.

Corpus rules [I]:
- Build a pinned, licence-tiered corpus with circuit-skills-style qualification; pointers + SHA-256 in repo, payloads in a git-ignored cache -> [data-pipeline-plan](data-pipeline-plan.md).
- Treat human geometry as relational structure, not ground truth: DRC-clean human boards are the exception; legality comes from our solver.
- Refuse rather than half-parse legacy constructs; run `kicad-cli pcb upgrade`; count pours as copper; adopt each board's own rules.
- Weight professional and DRC-clean boards; stratify by layer count against hobby bias.

## Open questions

- No authoritative count of `.kicad_pcb` files on GitHub or GitLab (code search blocked).
- OSHWHub, Kitspace, Hackaday.io and CERN OHR counts missing.
- open-schematics' KiCad/Eagle/Altium split and routed fraction not measured.
- No Altium layout ML dataset found.

## Sources

- research notes: [learning_from_layout_data.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md); correction: [verification_papers.md § 1 row 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
- related: [measured-priors](measured-priors.md)
