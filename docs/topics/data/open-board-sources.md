# Open board sources for the benchmark harness

Scope: public PCB datasets and open-hardware projects vetted for the 297-board benchmark manifest `candidates.jsonl` (first sourcing pass); its schema and fetch pitfalls. Not here: the 14,318-board second pass -> [wide-board-corpus](wide-board-corpus.md); raw supply and yield -> [corpora-and-yield](corpora-and-yield.md); tier rules -> [licensing-tiers-and-contamination](licensing-tiers-and-contamination.md).
Keys: candidates.jsonl, pointer manifest, PCBWorld D3, PCBench, Freerouting fixtures, pcb-corpus, Cypress, KiCad demos, Antmicro, licence detector errors, drc-clean, partial clone, Git LFS

## Pointer manifest

- Ship pointers, not boards: [`bench/manifests/candidates.jsonl`](../../../bench/manifests/candidates.jsonl) = **297 vetted boards**; row = repo, pinned commit, path, sha256, licence + licence file at that commit, KiCad 10.0.7 stats and DRC result. Unlicensed, NC and ND boards excluded [P, measured].
- By licence: permissive 159, copyleft 72, reciprocal-hardware 54, weak-copyleft 12 [P, measured].
- Best complex permissive boards: Antmicro (Apache-2.0), 8–12 layers. Diversity at the top tier needs reciprocal licences: MNT, Olimex, Marble, ButterStick, OrangeCrab [P].
- Second pass (2026-10-21) adds 14,318 boards (NC in its own tier, ND excluded) -> [wide-board-corpus](wide-board-corpus.md).
- Qualification on KiCad 10.0.7 (112 of 297) -> [../verification/harness.md](../verification/harness.md).

## GitHub licence detector errors

Don't trust GitHub's detector [P]:

| Project | Real licence | Detector / issue |
|---|---|---|
| SparkFun hardware | CC-BY-SA-4.0 (hardware section of LICENSE.md) | reported MIT |
| Olimex | hardware licence only in README; `LICENSE` = software | wrong file |
| KiCad demos | CC BY-SA 4.0 | reported GPL |
| HackRF, YARD Stick One | per-directory LICENSE | missed |

PCBench and pcb-corpus record GitHub-detected licences and inherit these errors; kicad-happy records no licence [P].

## Existing datasets: what is public and how to get it

Best first: pcb-corpus > PCBWorld D3 > Freerouting fixtures > Cypress > KiCad demos.

| Source | What you get | Pinned to upstream? | Licence | How to fetch | Verdict |
|---|---|---|---|---|---|
| **PCBWorld D3** ([repo](https://github.com/LGAI-Research/PCBWorld)) | 677 (of 679) boards. D3-A 99, D3-B 286, D3-C 292 by pin count; eval sets 99 / 10 / 10 (2-layer) | No: `d3.json` lists PCBench folder names | Code BSD-3; boards keep upstream licences: 356/677 none, 45 NOASSERTION | `tools/quickstart/prepare_pcbench.sh` clones PCBench @ `dec3be75`, converts with KiCad 9.0.8 (~4 GB). A rebuild differs from the paper's files on 40 guide boards; not redistributed | Use PCBWorld's script for comparable numbers [P] |
| **PCBench** ([repo](https://github.com/PCBench/PCBench)) | 1,183 folders (`raw` / `processed.kicad_pcb`, `final.json`, `metadata.json`); README says 164; metadata says 1,194 | No: per-board `source` repo URL only | Collection MIT; per board: GitHub-API detection at retrieval (2023) | `git clone` (1.2 GB) | KiCad 4/5, default rules [P] |
| **Freerouting fixtures** ([dir](https://github.com/freerouting/freerouting/tree/c4755a8874719dea76110860096776c4a9210994/scripts/benchmark/fixtures)) | 1,143 PCBench boards (`unrouted.kicad_pcb`/`.dsn`, `reference-routed.dsn`, KiCad 10.0.2 DRC JSON) + DAC2020 and KiCad-10 demo DSNs | No (PCBench names) | Repo GPL-3.0; boards: 743 of 1,142 no licence | Partial clone | Useful DRC labels, but default rules only: **0 boards** have zero error-severity DRC [P, measured] |
| **punkfab/pcb-corpus** ([README](https://github.com/punkfab/pcb-corpus/blob/1e999b4eefd5fdfcc90dc376d2882390245a8e0d/README.md)) | 235 KiCad 6–9 boards (178 2-layer, 57 4-layer) with `.kicad_pro`/`.kicad_dru`, unrouted twin, `features.json`, groups, TraceMaker baseline | **Yes**: repo, commit, path | Manifest CC0; boards keep GitHub-detected licences | Raw URLs at commit | Best modern seed. Re-checked 89: 70 DRC-clean in KiCad 10; 2 licences needed fixing [P, measured] |
| **kicad-happy catalog** | 5,856 repos, pinned hashes, categories, max layers (117 with ≥6 layers on KiCad 6+) | Yes (repo hash) | **No licence field** | JSON | Discovery index only [P] |
| **open-schematics** (HF) | 87,931 rows of raw schematic and PCB text | No commit | CC-BY-4.0 wrapper, no per-row licence | HF | Discovery only [P] |
| **Cypress** ([artifacts](https://github.com/NVlabs/Cypress/tree/743b07c4e33dc52a00584d55d2e67f38f70957f5/artifacts/benchmarks)) | small-1..10 in KiCad 7 (kiutils) + small-1..20 in Bookshelf; anonymised | Yes | Apache-2.0 | Partial clone | Placement only: **no Edge.Cuts outline**, no copper, stale net table [P, measured] |
| **ASP-DAC'21 bm1–bm11** | Routed/unrouted KiCad 5 boards and DSN | Yes | No repo licence; only bm1, bm11 have a CC BY-SA licence.txt | Clone | Keep bm1 and bm11 only [P] |
| **KiCad demos** ([LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/b1d58a59a9a3da4d061ee3dc22ceba3d11812eb2/LICENSE.README)) | 19 boards at tag 10.0.7, incl. vme-wren (12 layers), cm5_minima, multichannel_mixer (+unrouted) | Yes (pin the **10.0.7 tag**, not master) | "CC BY-SA 4.0: All the demo files provided in demos/*" | GitLab partial clone | On master `constraints.kicad_pcb` uses format 20260624, won't open in 10.0.x; master demos may need 10.99 [P, measured] |
| **Raspberry Pi minimal** | RP2040 and RP2350A KiCad 10 projects (both DRC-clean) | No git: zip only | MIT (LICENSE.txt in zip) | `datasheets.raspberrypi.com/.../Minimal-KiCAD.zip` → versioned pip-assets file | Pin by sha256. In `netlist_candidates.jsonl` because kaebench requires a 40-hex commit [P] |
| **OmniLayout / OmniRouting** | 1,681 Eagle-derived designs | — | No data licence | Not released ("will open-source") | Not usable yet [S] |
| **tscircuit dataset-srj18** | 16 boards as Simple Route JSON (5 Arduino + 11 Antmicro) | Upstream refs `main`, not commits | **No licence file** | — | Use upstream Antmicro repos [P] |
| **RL_PCB** | 9 tiny KiCad 5 boards (3–9 parts) | Yes | MIT | Clone | Netlist toy set [P] |
| **BenchPCNP** (Figshare) | 50 Protel netlists, per-module sub-netlists (54 labels) | Figshare | CC BY 4.0 | Zip | Module labels; no footprints [P] |

PCBWorld D3 benchmark numbers -> [../routing/pcbworld.md](../routing/pcbworld.md). Sources and URLs: [research notes § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/open_board_sources.md).

## Direct open-hardware projects (verified at pinned commits)

| Group | Examples in the manifest | Licence (evidence) | Notes |
|---|---|---|---|
| Antmicro (29 boards) | jetson-orin/nano/agx-thor baseboards, kria-k26-devboard, sodimm-ddr5, rdimm-ddr4/ddr5 testers (12 layers), lpddr4 test boards, OSM-L BMC SoM, GMSL/OCuLink/MIPI adapters | Apache-2.0 (`LICENSE`) | Most complex permissive boards; KiCad 7–10 [P] |
| Great Scott Gadgets | Cynthion, HackRF One, HackRF Pro (praline), YARD Stick One, GreatFET, Tycho, LNA3030 | CERN-OHL-P-2.0 (HackRF, YARD Stick: per-directory LICENSE); GreatFET BSD-3 | RF, USB HS [P] |
| azonenberg | latentred switch boards, dumptruck, starshipraider maxwell-main | BSD-3-Clause | 8–10 layers, SERDES [P] |
| MNT Research (source.mnt.re) | Reform motherboard30, imx8mplus SoM, keyboard4; Pocket Reform motherboard | CERN-OHL-S-2.0 | Forgejo host, not GitHub [P] |
| Olimex (21 boards) | ESP32-PoE (Apache), GateMate/iMX8MP/ESP32-P4/RP2350 (CERN-OHL-S), LoRa-STM32WL, USB-GIGABIT (CERN-OHL-1.2) | README | Repos keep every revision; we pick the latest [P] |
| SparkFun (9 boards) | XRP controller (6 layers), GNSSDO, IoT RedBoard RP2350 | CC-BY-SA-4.0 | [P] |
| Others, permissive | Glasgow (0BSD OR Apache-2.0), moteus (Apache), CHIPS Alliance rocket-pcb (Apache, 12 layers), Bus Pirate 5/6 (MIT), Winterbloom (CERN-OHL-P; faceplates NC-ND excluded), keyboards (Corne, Ferris, Lily58, Sweep, Redox), RP2040 design guide | as stated | [P] |
| Others, reciprocal/copyleft | Marble (CERN-OHL-1.2, README only), ButterStick, OrangeCrab (CERN-OHL-1.2), Bitaxe (CERN-OHL-S), Libre Solar BMS/MPPT (CERN-OHL-W), System76 Launch/Thelio Io (GPL-3.0), tigard (CC-BY-SA) | as stated | [P] |
| **Rejected** | Crazyflie (CC BY-NC-SA), endgame trackball (CC BY-NC), LimeSDR Mini v1/v2, ODrive, SimpleFOC shield (Altium/EasyEDA), OpenMV/Watchy/PocketPD/gamebub (no PCB in repo), many unlicensed high-layer catalog repos | — | [P] |

## Manifest composition [P, measured on 2026-10-21 with KiCad 10.0.7]

| Dataset | Rows | 2-layer / 4-layer / 6+ | DRC-clean | Notes |
|---|---|---|---|---|
| direct | 157 | 35 / 69 / 53 | 22 | median 151 footprints; 133 have a schematic; median 8 DRC errors |
| pcb-corpus | 86 | 56 / 30 / 0 | 67 | 74 clean-reference + 12 near-clean 4-layer (KiCad-demo copies dropped); licences re-audited |
| pcbworld-d3 | 29 | 29 / 0 / 0 | 9 | licensed eval boards (all 9 licensed D3-B/C + 20 D3-A ≥ 8 parts); PCBench `processed.kicad_pcb`, KiCad 4/5 |
| kicad-demos | 13 | 7 / 3 / 3 | 7 | tag 10.0.7 |
| cypress | 10 | 10 / 0 / 0 | 0 | unrouted placement inputs, no outline |
| aspdac21 | 2 | 2 / 0 / 0 | 0 | KiCad 5, CC BY-SA |
| **Total** | **297** | **139 / 102 / 56** | **105** | 273 routed, 14 partially routed, 10 unrouted. The 2 Raspberry Pi zip designs sit in `netlist_candidates.jsonl` |

DRC-clean = fully connected *and* error-free under own rules in KiCad 10.0.7.

Coverage:
- Interface tags: usb2 128, diff-pairs 119, rf 56, ethernet 44, pcie 44, bga 37, power 36, mipi 31, fpga 29, hdmi 27, usb3 27, usb-c 26, ddr 25.
- KiCad generation: KiCad 9 93, KiCad 7 64, KiCad 5 48, KiCad 8 43, KiCad 6 32, KiCad 10 11, KiCad 4 6.
- 229 rows have a root `.kicad_sch`; 235 ship their own `.kicad_pro`.

Quality signals:
1. Complex boards are rarely DRC-clean: 22/157 direct; 8 of the 56 boards with 6+ layers.
2. Commonest error types (boards): courtyards_overlap 58, clearance 45, copper_edge_clearance 44, hole_clearance 42, starved_thermal 38.
3. KiCad 10 adds errors: 7 of 77 boards pcb-corpus measured clean in KiCad 9 gain errors in KiCad 10.
4. Parser check: our S-expression counts = pcbnew's for footprints, track items, vias, zones on all 354 boards checked.

## Schema notes (how fields were computed)

| Field | Definition |
|---|---|
| `license` | SPDX id or expression; bare GPL `LICENSE` text normalised to `-only` (or-later not verified) |
| `license_tier` | most restrictive tier of the expression (for `OR`, the least restrictive) |
| `layers` | entries in `(layers …)` typed signal/power/mixed/jumper |
| `nets` | distinct named nets referenced by pads (= top-level net table on normally saved boards; Cypress tables are stale) |
| `tracks` | top-level `segment` + `arc` |
| `board_mm` | Edge.Cuts bbox (top-level `gr_*` + transformed footprint `fp_*`); null without outline |
| `routed` | copper present *and* 0 unconnected, as saved or after `--refill-zones` |
| tag `drc-clean` | routed and 0 error-severity violations under the board's own `.kicad_pro`/`.kicad_dru` |
| tag `no-project-rules` | no `.kicad_pro`; DRC used KiCad defaults |
| interface tags | net/footprint name heuristics + curation; filters, not ground truth [I] |
| `notes` | DRC summary (unconnected, errors, warnings, top error types) + licence caveats |

## Fetch pitfalls [P unless marked]

- Harness check: kaebench's `fetch` retrieved 31 sampled rows (GitHub, GitLab, the Forgejo host, PCBench), sha256 verified [P, measured].
- Partial clone: `git clone --filter=blob:none --no-checkout --depth 1` + `git cat-file -p <commit>:<path>` fetches only needed blobs. `git ls-tree -l` on such a clone lazily downloads **every** blob (needs sizes) [P, observed].
- Git LFS: many repos carry `.gitattributes`; no manifest board was an LFS pointer. Detect `version https://git-lfs` and fall back to `media.githubusercontent.com` [I].
- Multi-revision folders (Olimex, Glasgow revC0–revD1, moteus r1.x) and backups (`-backups/`, `_autosave`) need explicit path pins.
- Submodules usually hold libraries; boards embed footprints, so routing and DRC work without them; expect `lib_footprint_issues` warnings.
- Legacy: 54 rows are KiCad 4/5; KiCad 10 opens them; `kicad-cli pcb upgrade` rewrites them. Run it before routing and record the upgraded sha256 separately [I].
- DRC report cap: stock `kicad-cli` caps reports at 199 per type (499 for clearance) -> [../kicad/kicad-cli.md](../kicad/kicad-cli.md).
- Freerouting round trip: DSN export needs `pcbnew.ExportSpecctraDSN` (no CLI subcommand in KiCad 10); headless SES import failed on 10.0.2 -> [../kicad/specctra-freerouting-integration.md](../kicad/specctra-freerouting-integration.md).
- Non-GitHub hosts (source.mnt.re, gitlab.com, zip downloads) need host-agnostic fetchers; zips pin only by sha256.

## Suite and scoring rules [I]

1. Verify `pcb_sha256` after fetch; payloads in a git-ignored cache.
2. Default suites by tag: `drc-clean` routing set 105; placement set = routed rows with a schematic + Cypress; stress set `6plus` 56. Report per tier and per dataset.
3. Score non-`drc-clean` rows by DRC delta against the human reference's own count (in `notes`), not zero. Always run DRC with the row's own `.kicad_pro`/`.kicad_dru` copied beside the board.
4. PCBWorld comparability: use `prepare_pcbench.sh` + KiCad 9.0.8 + `d3.json` splits, not our `pcbworld-d3` rows (a licence-filtered pointer subset for general use).
5. Licences: only `permissive` rows feed CDLA-Permissive data products; `copyleft`/`reciprocal-hardware` = evaluation only; re-run detection (README + per-directory) at every refresh -> [licensing-tiers-and-contamination](licensing-tiers-and-contamination.md).
6. Grow the 6+ tier from Antmicro's remaining repos, kicad-happy's ≥6-layer list (117 repos, licences unchecked), MNT's other boards. ≤2 boards per repo in scored suites (Antmicro is 13 of 56 6+ rows).
7. Contamination: popular boards (HackRF, Glasgow, Corne, Antmicro carriers) are almost surely in pretraining; time-split rules -> [licensing-tiers-and-contamination](licensing-tiers-and-contamination.md#contamination).

## Open questions

- PCBench size: README 164 vs metadata 1,194 vs 1,183 folders vs PCBWorld's 1,182 converted; D3 = 679 boards, 677 in the splits. 164 explained -> [corpora-and-yield](corpora-and-yield.md#pcbench-source-pool-of-pcbworld-d3).
- PCBench unlicensed share depends on the file counted; 743 empty + 91 NOASSERTION of the 1,142 parseable Freerouting fixture metadata files; not reconciled with the other tallies -> [corpora-and-yield](corpora-and-yield.md#pcbench-source-pool-of-pcbworld-d3).
- Freerouting fixtures and D3 both come from PCBench, so they likely share boards; overlap not measured [I].
- pcb-corpus licences: GitHub-detected; 1 wrong label among 89 audited (minuet: MIT → CERN-OHL-W hardware) + 3 KiCad-demo copies labelled GPL-3.0; rest unaudited.
- Crkbd ships `LICENSE_MIT` and `LICENSE_CC` (CC-BY-4.0) without saying which covers the PCBs; recorded "MIT AND CC-BY-4.0".
- No upstream commit known for any PCBench board; blob-hash matching against upstream history feasible, not done.
- Interface tags heuristic: USB D+/D− counts as `diff-pairs`; pcb-corpus "wireless" maps to `rf`.
- DRC ran on boards as saved. Refill changed connectivity on only 2 boards, but changes clearance results on pour-heavy boards.

## Sources

- research notes: [open_board_sources.md § Q1–Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/open_board_sources.md)
- manifests: [candidates.jsonl](../../../bench/manifests/candidates.jsonl), [netlist_candidates.jsonl](../../../bench/manifests/netlist_candidates.jsonl)
- primary: [PCBWorld pcbench_prep](https://github.com/LGAI-Research/PCBWorld/blob/1989a9325796b73cca793a0c8f222dd1509256e8/tools/datagen/pcbench_prep/README.md), [PCBench](https://github.com/PCBench/PCBench/tree/dec3be75cbdef74787625f9043c7391cd473bb64), [Freerouting PCBench integration](https://github.com/freerouting/freerouting/blob/c4755a8874719dea76110860096776c4a9210994/scripts/pcbench/README.md), [pcb-corpus](https://github.com/punkfab/pcb-corpus/tree/1e999b4eefd5fdfcc90dc376d2882390245a8e0d), [KiCad LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/b1d58a59a9a3da4d061ee3dc22ceba3d11812eb2/LICENSE.README), [SparkFun LICENSE.md](https://github.com/sparkfun/SparkFun_XRP_Controller/blob/86c4cd7fbc40c49308ec9d28007809906f18eec3/LICENSE.md), [Olimex README](https://github.com/OLIMEX/ESP32-P4-DevKit/blob/26705d36407a07324348927dfd30fbf4ffc1d94c/README.md), [BenchPCNP](https://figshare.com/articles/dataset/BenchPCNP_Benchmark_Dataset_for_Printed_Circuit_Board_Netlist_Processing/30020125), [Cypress](https://github.com/NVlabs/Cypress/tree/743b07c4e33dc52a00584d55d2e67f38f70957f5)
- related: [local-board-corpus](local-board-corpus.md), [data-pipeline-plan](data-pipeline-plan.md), [../verification/benchmarks.md](../verification/benchmarks.md), [../placement/benchmarks-and-metrics.md](../placement/benchmarks-and-metrics.md)
