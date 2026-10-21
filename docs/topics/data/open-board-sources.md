# Open board sources for the benchmark harness

**TL;DR**
- **We ship a pointer manifest, not boards.** [`bench/manifests/candidates.jsonl`](../../../bench/manifests/candidates.jsonl) lists **297 vetted boards**: each row has repo, pinned commit, path, sha256, licence and the licence file at that commit, plus our KiCad 10.0.7 stats and DRC result. Unlicensed, NC and ND boards are excluded [P, measured].
- **Mix:**
  - by licence: permissive 159, copyleft 72, reciprocal-hardware 54, weak-copyleft 12;
  - by layers: 2-layer 139, 4-layer 102, 6+ layers 56;
  - DRC: 105 boards are fully connected *and* error-free under their own rules in KiCad 10.0.7 [P, measured].
- **Existing datasets, best first:**
  - **punkfab/pcb-corpus**: 235 pinned KiCad 6–9 boards with their own rules and a CC0 manifest;
  - **PCBWorld D3**: rebuilt from PCBench @ `dec3be75` by PCBWorld's own script; not redistributed, and not pinned to upstream commits;
  - **Freerouting fixtures**: PCBench boards with KiCad 10.0.2 DRC labels, but judged by default rules only;
  - **Cypress**: Apache-2.0 placement boards with no outline;
  - **KiCad demos**: CC BY-SA 4.0 [P].
- **Don't trust GitHub's licence detector.** It mislabels:
  - SparkFun hardware: CC BY-SA, reported as MIT;
  - Olimex: the hardware licence is only in the README;
  - KiCad demos: CC BY-SA, reported as GPL;
  - HackRF: a per-directory licence.

  PCBench and pcb-corpus record GitHub-detected licences, so they inherit these errors; kicad-happy records no licence at all [P].
- **The best complex permissive boards are Antmicro's** (Apache-2.0): Jetson/Kria carriers and DDR4/DDR5/LPDDR4 testers with 8–12 layers. **Diversity at the top tier needs reciprocal licences**: MNT, Olimex, Marble, ButterStick, OrangeCrab [P].

## Key facts

### Existing datasets: what is public and how to get it

| Source | What you get | Pinned to upstream? | Licence | How to fetch | Verdict |
|---|---|---|---|---|---|
| **PCBWorld D3** ([repo](https://github.com/LGAI-Research/PCBWorld)) | 677 (of 679) boards. D3-A 99, D3-B 286, D3-C 292 by pin count; eval sets 99 / 10 / 10 (2-layer) | No: `d3.json` lists PCBench folder names | Code BSD-3; boards keep their upstream licences: 356/677 none, 45 NOASSERTION | `tools/quickstart/prepare_pcbench.sh` clones PCBench @ `dec3be75` and converts it with KiCad 9.0.8 (~4 GB). A rebuild differs from the paper's files on 40 guide boards | Use PCBWorld's script for comparable numbers [P] |
| **PCBench** ([repo](https://github.com/PCBench/PCBench)) | 1,183 folders (`raw` / `processed.kicad_pcb`, `final.json`, `metadata.json`); README says 164; metadata says 1,194 | No: per-board `source` repo URL only | Collection MIT; per board: GitHub-API detection at retrieval (2023) | `git clone` (1.2 GB) | KiCad 4/5, default rules [P] |
| **Freerouting fixtures** ([dir](https://github.com/freerouting/freerouting/tree/c4755a8874719dea76110860096776c4a9210994/scripts/benchmark/fixtures)) | 1,143 PCBench boards (`unrouted.kicad_pcb`/`.dsn`, `reference-routed.dsn`, KiCad 10.0.2 DRC JSON) plus DAC2020 and KiCad-10 demo DSNs | No (PCBench names) | Repo GPL-3.0; boards: 743 of 1,142 have no licence | Partial clone | Useful DRC labels. **0 boards** have zero error-severity DRC under default rules [P, measured] |
| **punkfab/pcb-corpus** ([README](https://github.com/punkfab/pcb-corpus/blob/1e999b4eefd5fdfcc90dc376d2882390245a8e0d/README.md)) | 235 boards (178 2-layer, 57 4-layer) with `.kicad_pro`/`.kicad_dru`, an unrouted twin, `features.json`, groups and a TraceMaker baseline | **Yes**: repo, commit, path | Manifest CC0; boards keep GitHub-detected licences | Raw URLs at commit | Best modern seed. We re-checked 89 boards: 70 are DRC-clean in KiCad 10, and 2 licences needed fixing [P, measured] |
| **kicad-happy catalog** | 5,856 repos with pinned hashes, categories and max layers (117 with ≥6 layers on KiCad 6+) | Yes (repo hash) | **No licence field** | JSON | Discovery index only [P] |
| **open-schematics** (HF) | 87,931 rows of raw schematic and PCB text | No commit | CC-BY-4.0 wrapper, no per-row licence | HF | Discovery only [P] |
| **Cypress** ([artifacts](https://github.com/NVlabs/Cypress/tree/743b07c4e33dc52a00584d55d2e67f38f70957f5/artifacts/benchmarks)) | small-1..10 in KiCad 7 (kiutils) plus small-1..20 in Bookshelf; anonymised | Yes | Apache-2.0 | Partial clone | Placement only: **no Edge.Cuts outline**, no copper, stale net table [P, measured] |
| **ASP-DAC'21 bm1–bm11** | Routed/unrouted KiCad 5 boards and DSN | Yes | No repo licence; only bm1 and bm11 have a CC BY-SA licence.txt | Clone | Keep bm1 and bm11 only [P] |
| **KiCad demos** ([LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/b1d58a59a9a3da4d061ee3dc22ceba3d11812eb2/LICENSE.README)) | 19 boards at tag 10.0.7, including vme-wren (12 layers), cm5_minima, multichannel_mixer (+unrouted) | Yes (pin the **10.0.7 tag**, not master) | "CC BY-SA 4.0: All the demo files provided in demos/*" | GitLab partial clone | On master, `constraints.kicad_pcb` uses format 20260624 and won't open in 10.0.x [P, measured] |
| **Raspberry Pi minimal** | RP2040 and RP2350A KiCad 10 projects (both DRC-clean) | No git: zip only | MIT (LICENSE.txt in the zip) | `datasheets.raspberrypi.com/.../Minimal-KiCAD.zip` → versioned pip-assets file | Pin by sha256. Listed in `netlist_candidates.jsonl` because kaebench requires a 40-hex commit [P] |
| **OmniLayout / OmniRouting** | 1,681 Eagle-derived designs | — | No data licence | Not released ("will open-source") | Not usable yet [S] |
| **tscircuit dataset-srj18** | 16 boards as Simple Route JSON (5 Arduino + 11 Antmicro) | Upstream refs are `main`, not commits | **No licence file** | — | Use the upstream Antmicro repos instead [P] |
| **RL_PCB** | 9 tiny KiCad 5 boards (3–9 parts) | Yes | MIT | Clone | Netlist toy set [P] |
| **BenchPCNP** (Figshare) | 50 Protel netlists with per-module sub-netlists (54 labels) | Figshare | CC BY 4.0 | Zip | Module labels; no footprints [P] |

Sources and URLs: [research notes § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/open_board_sources.md).

### Direct open-hardware projects (verified at pinned commits)

| Group | Examples in the manifest | Licence (evidence) | Notes |
|---|---|---|---|
| Antmicro (29 boards) | jetson-orin/nano/agx-thor baseboards, kria-k26-devboard, sodimm-ddr5, rdimm-ddr4/ddr5 testers (12 layers), lpddr4 test boards, OSM-L BMC SoM, GMSL/OCuLink/MIPI adapters | Apache-2.0 (`LICENSE`) | Most complex permissive boards; KiCad 7–10 [P] |
| Great Scott Gadgets | Cynthion, HackRF One, HackRF Pro (praline), YARD Stick One, GreatFET, Tycho, LNA3030 | CERN-OHL-P-2.0 (HackRF and YARD Stick: per-directory LICENSE); GreatFET BSD-3 | RF, USB HS [P] |
| azonenberg | latentred switch boards, dumptruck, starshipraider maxwell-main | BSD-3-Clause | 8–10 layers, SERDES [P] |
| MNT Research (source.mnt.re) | Reform motherboard30, imx8mplus SoM, keyboard4; Pocket Reform motherboard | CERN-OHL-S-2.0 | Forgejo host, not GitHub [P] |
| Olimex (21 boards) | ESP32-PoE (Apache), GateMate/iMX8MP/ESP32-P4/RP2350 boards (CERN-OHL-S), LoRa-STM32WL and USB-GIGABIT (CERN-OHL-1.2) | **README** states the hardware licence; `LICENSE` is the software licence | Repos keep every revision; we pick the latest [P] |
| SparkFun (9 boards) | XRP controller (6 layers), GNSSDO, IoT RedBoard RP2350 | **CC-BY-SA-4.0** (hardware section of LICENSE.md) | GitHub says MIT [P] |
| Others, permissive | Glasgow (0BSD OR Apache-2.0), moteus (Apache), CHIPS Alliance rocket-pcb (Apache, 12 layers), Bus Pirate 5/6 (MIT), Winterbloom boards (CERN-OHL-P; faceplates NC-ND excluded), keyboards (Corne, Ferris, Lily58, Sweep, Redox), RP2040 design guide | as stated | [P] |
| Others, reciprocal/copyleft | Marble (CERN-OHL-1.2, README only), ButterStick, OrangeCrab (CERN-OHL-1.2), Bitaxe (CERN-OHL-S), Libre Solar BMS/MPPT (CERN-OHL-W), System76 Launch/Thelio Io (GPL-3.0), tigard (CC-BY-SA) | as stated | [P] |
| **Rejected** | Crazyflie (CC BY-NC-SA), endgame trackball (CC BY-NC), LimeSDR Mini v1/v2, ODrive, SimpleFOC shield (Altium/EasyEDA), OpenMV/Watchy/PocketPD/gamebub (no PCB in repo), many unlicensed high-layer catalog repos | — | [P] |

### Manifest composition [P, measured on 2026-10-21 with KiCad 10.0.7]

| Dataset | Rows | 2-layer / 4-layer / 6+ | DRC-clean | Notes |
|---|---|---|---|---|
| direct | 157 | 35 / 69 / 53 | 22 | median 151 footprints; 133 have a schematic |
| pcb-corpus | 86 | 56 / 30 / 0 | 67 | 74 clean-reference + 12 near-clean 4-layer (KiCad-demo copies dropped); licences re-audited |
| pcbworld-d3 | 29 | 29 / 0 / 0 | 9 | licensed eval boards (all 9 licensed D3-B/C + 20 D3-A ≥ 8 parts); PCBench `processed.kicad_pcb`, KiCad 4/5 |
| kicad-demos | 13 | 7 / 3 / 3 | 7 | tag 10.0.7 |
| cypress | 10 | 10 / 0 / 0 | 0 | unrouted placement inputs, no outline |
| aspdac21 | 2 | 2 / 0 / 0 | 0 | KiCad 5, CC BY-SA |
| **Total** | **297** | **139 / 102 / 56** | **105** | 273 routed, 14 partially routed, 10 unrouted. The 2 Raspberry Pi zip designs sit in `netlist_candidates.jsonl` |

**Coverage:**
- **Interface tags:** usb2 128, diff-pairs 119, rf 56, ethernet 44, pcie 44, bga 37, power 36, mipi 31, fpga 29, hdmi 27, usb3 27, usb-c 26, ddr 25.
- **KiCad generation:** KiCad 9 93, KiCad 7 64, KiCad 5 48, KiCad 8 43, KiCad 6 32, KiCad 10 11, KiCad 4 6.
- **Schematics and rules:** 229 rows have a root `.kicad_sch`; 235 ship their own `.kicad_pro`.

**Quality signals:**
- **Complex boards are rarely DRC-clean.** The direct set has a median of 8 errors and only 22/157 are clean; only 8 of the 56 boards with 6+ layers are clean.
- **Most common error types:** courtyards_overlap (58 boards), clearance (45), copper_edge_clearance (44), hole_clearance (42), starved_thermal (38).
- **KiCad 10 adds errors:** 7 of 77 boards that pcb-corpus measured clean in KiCad 9 gain errors in KiCad 10.

**Parser check:** our S-expression counts equal pcbnew's for footprints, track items, vias and zones on all 354 boards checked.

### Schema notes (how fields were computed)
- **Licences:**
  - `license` is an SPDX id or expression; `license_tier` is the most restrictive tier (for `OR`, the least restrictive).
  - A bare GPL `LICENSE` text is normalised to `-only`, because or-later was not verified.
- **Counts:**
  - `layers` = entries in the `(layers …)` block typed signal/power/mixed/jumper.
  - `nets` = distinct named nets referenced by pads. On normally saved boards this equals the top-level net table; Cypress files have stale tables.
  - `tracks` = top-level `segment` + `arc`.
  - `board_mm` = Edge.Cuts bounding box (top-level `gr_*` plus transformed footprint `fp_*`), null when there is no outline.
- **`routed`:** copper is present *and* zero unconnected items, either as saved or after `--refill-zones`.
- **Tags:**
  - `drc-clean` = routed and zero error-severity violations under the board's own `.kicad_pro`/`.kicad_dru`.
  - `no-project-rules` = no `.kicad_pro`, so DRC used KiCad defaults.
  - Interface tags come from net and footprint name heuristics plus curation; treat them as filters, not ground truth [I].
- **`notes`** carries the DRC summary (unconnected, errors, warnings, top error types) and any licence caveats.

### Fetch pitfalls [P unless marked]
- **Harness fetch check:** kaebench's `fetch` retrieved 31 sampled rows (GitHub, GitLab, the Forgejo host and PCBench) with sha256 verified [P, measured].
- **Partial clones:**
  - `git clone --filter=blob:none --no-checkout --depth 1` plus `git cat-file -p <commit>:<path>` fetches only the needed blobs.
  - `git ls-tree -l` on such a clone lazily downloads **every** blob, because it needs their sizes [P, observed].
- **Git LFS:** many repos carry `.gitattributes`, but no manifest board turned out to be an LFS pointer. The harness should still detect `version https://git-lfs` and fall back to `media.githubusercontent.com` [I].
- **Multi-revision folders** (Olimex, Glasgow revC0–revD1, moteus r1.x) and backups (`-backups/`, `_autosave`) need explicit path pins.
- **Submodules** usually hold libraries. Boards embed their footprints, so routing and DRC work without them, but expect `lib_footprint_issues` warnings.
- **Formats and tools:**
  - **Legacy formats:** 54 rows are KiCad 4/5; KiCad 10 opens them, and `kicad-cli pcb upgrade` rewrites them.
  - **KiCad master demos** may need 10.99.
  - **DRC report cap:** stock `kicad-cli` caps reports at 199 per type (499 for clearance).
- **Freerouting round trip:** DSN export needs `pcbnew.ExportSpecctraDSN` (there is no CLI subcommand in KiCad 10); headless SES import failed on 10.0.2.
- **Non-GitHub hosts:** source.mnt.re, gitlab.com and zip downloads need host-agnostic fetchers; zips can be pinned only by sha256.

## Recommendations for our system

1. **Use the manifest as-is for v0 of the harness.**
   - Verify `pcb_sha256` after fetching and store payloads in a git-ignored cache.
   - Default suites by tag:
     - `drc-clean` routing set: 105 boards;
     - placement set: all routed rows with a schematic, plus Cypress;
     - stress set: `6plus` (56).
   - Report results per tier and per dataset [I].
2. **Score relative to the reference.** For rows that are not `drc-clean`, score the router's DRC delta against the human reference's own count (in `notes`), not against zero. Always run DRC with the row's own `.kicad_pro`/`.kicad_dru` copied beside the board [I].
3. **Get PCBWorld comparability from PCBWorld's own chain.** Use `prepare_pcbench.sh` with KiCad 9.0.8 and `d3.json` splits; don't use our `pcbworld-d3` rows for that, since those are a licence-filtered pointer subset for general use [I].
4. **Normalise legacy rows before routing.** Run `kicad-cli pcb upgrade` on the 54 legacy rows and record the upgraded sha256 separately [I].
5. **Licence handling:**
   - Only `permissive` rows feed CDLA-Permissive data products.
   - `copyleft` and `reciprocal-hardware` rows are for evaluation only.
   - Re-run licence detection with README and per-directory checks at every manifest refresh. See [licensing-tiers-and-contamination.md](licensing-tiers-and-contamination.md) [I].
6. **Grow the 6+ layer tier next**, from:
   - Antmicro's remaining repos;
   - kicad-happy's ≥6-layer list (117 repos; licences must be checked);
   - MNT's other boards.

   Keep at most 2 boards per repo in scored suites to limit repo dominance (Antmicro is 13 of 56 6+ rows) [I].
7. **Contamination:** popular boards (HackRF, Glasgow, Corne, Antmicro carriers) are almost surely in LLM pretraining data. Keep a time-split subset: pin commits after the model cutoff [I].

## Conflicts and open questions
- **PCBench size:** README 164 vs metadata 1,194 vs 1,183 folders vs PCBWorld's 1,182 converted. D3 is 679 boards, of which 677 are in the splits.
- **pcb-corpus licences:** GitHub-detected; we found 1 wrong label among 89 audited boards (minuet: MIT → CERN-OHL-W hardware) and 3 KiCad-demo copies labelled GPL-3.0. The rest are unaudited.
- **Crkbd** ships both `LICENSE_MIT` and `LICENSE_CC` (CC-BY-4.0) without saying which covers the PCBs. We record "MIT AND CC-BY-4.0".
- **No upstream commit is known for any PCBench board.** Blob-hash matching against upstream history is feasible but was not done.
- **Interface tags are heuristic.** USB D+/D− counts as `diff-pairs`, and pcb-corpus's "wireless" group maps to `rf`.
- **DRC baseline:** DRC was run on the boards as saved. Refill changed connectivity on only 2 boards, but it changes clearance results on pour-heavy boards.

## Sources
- research notes: [open_board_sources.md § Q1–Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/open_board_sources.md)
- manifests: [candidates.jsonl](../../../bench/manifests/candidates.jsonl), [netlist_candidates.jsonl](../../../bench/manifests/netlist_candidates.jsonl)
- primary:
  - [PCBWorld pcbench_prep](https://github.com/LGAI-Research/PCBWorld/blob/1989a9325796b73cca793a0c8f222dd1509256e8/tools/datagen/pcbench_prep/README.md)
  - [PCBench](https://github.com/PCBench/PCBench/tree/dec3be75cbdef74787625f9043c7391cd473bb64)
  - [Freerouting PCBench integration](https://github.com/freerouting/freerouting/blob/c4755a8874719dea76110860096776c4a9210994/scripts/pcbench/README.md)
  - [pcb-corpus](https://github.com/punkfab/pcb-corpus/tree/1e999b4eefd5fdfcc90dc376d2882390245a8e0d)
  - [KiCad LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/b1d58a59a9a3da4d061ee3dc22ceba3d11812eb2/LICENSE.README)
  - [SparkFun LICENSE.md](https://github.com/sparkfun/SparkFun_XRP_Controller/blob/86c4cd7fbc40c49308ec9d28007809906f18eec3/LICENSE.md)
  - [Olimex README](https://github.com/OLIMEX/ESP32-P4-DevKit/blob/26705d36407a07324348927dfd30fbf4ffc1d94c/README.md)
  - [BenchPCNP](https://figshare.com/articles/dataset/BenchPCNP_Benchmark_Dataset_for_Printed_Circuit_Board_Netlist_Processing/30020125)
  - [Cypress](https://github.com/NVlabs/Cypress/tree/743b07c4e33dc52a00584d55d2e67f38f70957f5)

See also: [local-board-corpus.md](local-board-corpus.md) (all accepted boards as one local folder), [corpora-and-yield.md](corpora-and-yield.md), [licensing-tiers-and-contamination.md](licensing-tiers-and-contamination.md), [data-pipeline-plan.md](data-pipeline-plan.md), [../verification/benchmarks.md](../verification/benchmarks.md), [../routing/pcbworld.md](../routing/pcbworld.md), [../placement/benchmarks-and-metrics.md](../placement/benchmarks-and-metrics.md)
