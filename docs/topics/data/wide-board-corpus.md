# Wide board corpus (second sourcing pass, 2026-10-21)

**TL;DR**
- **14,318 new boards from 8,757 repos**, pinned by commit (or sha256 for downloads) with stats and KiCad 10.0.7 DRC, in [`bench/manifests/wide.jsonl`](../../../bench/manifests/wide.jsonl) (13,475) and [`wide-noncommercial.jsonl`](../../../bench/manifests/wide-noncommercial.jsonl) (843). With the 297 boards of [`candidates.jsonl`](../../../bench/manifests/candidates.jsonl) that is ~14,600 test boards [P, measured].
- **Mix:** 11,495 two-layer, 2,193 four-layer, 630 with 6+ layers (255 with 10+, max 18); median 38 footprints, 458 boards ≥ 300, 49 ≥ 1,000. 11,360 routed, 2,449 DRC-clean under their own rules [P, measured].
- **Every licence was read, not taken from GitHub's detector.** NC is accepted (separate file and tier), ND is not; where signals conflict the more restrictive one wins. 6,994 repos were rejected, mostly for no licence (2,849) or no board files (2,263) [P].
- **Near-duplicates are removed by content**, not by name: 1,637 revisions, forks and mirrors were dropped ([`wide-duplicates.jsonl`](../../../bench/manifests/wide-duplicates.jsonl) maps each to its representative) and ~600 near-empty boards excluded [P, measured].
- **Non-KiCad sources are converted at fetch time:** 2,472 Eagle, 419 Altium, 32 Allegro and 14 PADS boards go through `kicad-cli pcb import`; 1,473 rows are KiCad 4/5 files. All of them load in KiCad 10 [P, measured].

## Key facts

### Licence policy (user decisions, applied to every row)

| Signal | Decision | Tier |
|---|---|---|
| MIT, BSD, Apache, ISC, 0BSD, Unlicense, CC0, CC-BY, CERN-OHL-P, WTFPL, Solderpad; MIT-CBA/Fab licence; Lone Dynamics licence | accept | `permissive` |
| CERN-OHL-W, LGPL, MPL, EPL | accept | `weak-copyleft` |
| GPL (any version), AGPL | accept | `copyleft` |
| CERN-OHL-S, CERN-OHL-1.x, CC-BY-SA, TAPR-OHL; OSHWA-declared "CERN" with no version; org-wide statements (Sinara) | accept | `reciprocal-hardware` |
| CC-BY-NC(-SA), custom "non-commercial" or "private use only" terms, TAPR-NCL | accept, separate file | `noncommercial` |
| ND/NoDerivatives; terms granting use but not modification; "personal use" | reject | — |
| No licence; "all rights reserved"; vendor EULAs; source-available | reject | — |
| Clauses forbidding AI/ML use, automated processing or benchmarking | reject (none found) | — |
| Reverse-engineered copies of commercial boards | reject | — |

- **Scope:** a licence explicitly scoped to firmware or libraries does not cover the boards; an unscoped conflict (e.g. LICENSE MIT, README "hardware CC-BY-SA") takes the more restrictive licence. Ambiguous "some boards are NC" (Mutable Shruthi filters) is filed NC [P].
- **Top licences:** MIT 3,223; GPL-3.0 1,988; CC-BY-SA-4.0 1,975; CERN-OHL-S 1,156; CC-BY-SA-3.0 999; CERN-OHL-1.2 794; Apache 668; CC-BY-NC-SA-4.0 568 [P, measured].
- **What testing each tier allows** is in [licensing-tiers-and-contamination.md](licensing-tiers-and-contamination.md#what-testing-each-tier-allows).

### Sources

| Dataset tag | Rows | Where from |
|---|---|---|
| `kicad-happy` | 4,433 | [kicad-happy catalog](https://github.com/aklofas/kicad-happy-testharness/blob/8bae5a0c5a74d2d41366f0a9ee4f9cfa12b2a043/reference/repo_catalog.json): all 5,856 repos licence-audited at the catalog's pinned hash; 317 conflicting repos reviewed by agents |
| `direct-keyboard-synth2`, `direct-audio-keyboard` | 2,215 | split-keyboard lists, keebio/ai03/salicylic-acid3, Mutable Instruments, Befaco, Music Thing, eurorack |
| `direct-community2`, `direct-discovery` | 3,414 | OSHWA certification directory (3,453 projects), Codeberg/GitLab search, GitHub topic pages, awesome-lists, Made with KiCad, Hackaday.io |
| `direct-adafruit2`, `direct-vendors-a` | 944 | Adafruit `*-PCB` repos (Eagle, CC-BY-SA-3.0), Arduino CAD zips (CC-BY-SA-4.0), Electronic Cats, Particle, Watterott, Seeed, BeagleBoard, Espressif |
| `direct-sparkfun2`, `direct-vendors-b` | 929 | SparkFun and sparkfunX (CC-BY-SA), Olimex (README hardware licence), Kitspace, badges, Crowd Supply |
| `direct-complex`, `direct-complex2` | 603 | Antmicro, OHWR, Sinara, MNT, Luxonis, azonenberg, Machdyne, LimeSDR, FPGA/SoC boards |
| `direct-breakouts` | 498 | Soldered, MLAB, Freetronics, Protocentral, Unexpected Maker and other module makers |
| `direct-datasets2` | 481 | PCBench folders traced to their upstream repos (licence checked upstream) |
| `direct-hosts-misc` | 282 | GitLab, Codeberg, Zenodo/HardwareX records, CERN GitLab |
| `pcb-corpus` | 122 | [punkfab/pcb-corpus](https://github.com/punkfab/pcb-corpus/tree/1e999b4eefd5fdfcc90dc376d2882390245a8e0d) boards not in `candidates.jsonl`, licences re-audited |
| `direct-robotics-power-science`, `direct-ham-rf`, `direct-demo-eval`, `direct-fabacademy-mirror` | 397 | motor control, 3D printers, CubeSats, lab instruments; HF/VHF radios, SDRs, LoRa; KiCad demos of older versions, vendor reference boards; 16 curated Fab Academy boards |

Candidate lists, rejects with reasons, and scripts: [tools/research/board-sourcing/](../../../tools/research/board-sourcing/README.md).

### Pipeline

1. **Find and verify** (agents): each row is checked at a pinned commit with `probe.py`/`atcommit.py`; licence evidence is quoted.
2. **Fingerprint and de-duplicate** (`sig.py`): fetch every board; fingerprint = footprint library ids and values (as multisets) plus net names; MinHash/LSH candidate pairs, Jaccard ≥ 0.75 → same cluster; exact sha256 always. One representative per cluster, preferring curated sources, then newer file format, then more copper. Imported formats are compared by sha256 only.
3. **Enrich** (`enrich.py`, mostly on a 50-core host): fetch, import, pcbnew stats, `kicad-cli pcb drc` as saved under the board's own `.kicad_pro`/`.kicad_dru`, plus a zone-refill pass when connections are missing.
4. **Merge** (`merge.py`): results matched by (repo, commit, path), manual licence decisions applied, final sha256 de-duplication against mirrors and `candidates.jsonl`, NC split off, every row validated by `kaebench.manifest`.

### Harness changes this pass needed

- `pcb_path` may name an Eagle/Allegro `.brd`, Altium `.PcbDoc`, PADS `.asc` or CADSTAR `.cpa`; fetch converts it and keeps `pcb_sha256` as the upstream hash.
- Rows with `archive_sha256` and no commit fetch a zip/tar or single file (Arduino, Raspberry Pi, Zenodo); `file_urls` adds pinned project files.
- Import repairs for boards KiCad 10 refuses to load: items on layer `UNDEFINED`/`Rescue`, unquoted numeric net names, Eagle silkscreen art imported as tens of thousands of zones, stacked micro-arcs. Each changes only the boards that failed; see [local-board-corpus.md](local-board-corpus.md#fidelity-what-differs-from-upstream).
- Raw-file fetch for GitLab hosts and Codeberg, git fallback, polite retries on HTTP 429.

### Hosts and robots.txt

- **gitlab.fabcloud.org** disallows raw files for all agents and everything for AI crawlers: nothing is fetched from it; 16 Fab Academy boards come from fabacademy.org copies instead [P].
- **778 rows** are on hosts whose robots.txt disallows raw-file and/or git paths (gitlab.com, codeberg.org, gitlab.cern.ch, source.mnt.re, openbeagle.org, source.puri.sm and smaller ones). They carry the tag `host-robots-restricted`; drop them with a tag filter if fetches must honour robots.txt [P].

## Recommendations for our system

1. **Use `wide.jsonl` for breadth, `candidates.jsonl` for the scored benchmark.** Most wide rows are not DRC-clean; score them against the reference's own error count, as for `candidates` [I].
2. **Filter on tags:** `drc-clean` (2,449) for routing completion tests; `6plus`/`bga`/`ddr`/`pcie` for stress; `unrouted` (716) only for placement; exclude `imported-*` when import artefacts would confound a result [I].
3. **Keep `noncommercial` opt-in** and out of anything redistributed or used commercially [I].
4. **Re-run the licence and robots checks at each refresh**; hosts and licences change [I].

## Conflicts and open questions

- **Licence classification depth varies:** sector rows were read by agents, kicad-happy rows by script with agent review of conflicts. Errors lean restrictive (e.g. a repo with MIT hardware tagged NC because of a sub-folder licence), but spot checks are worth repeating.
- **Interface and category tags are heuristic.** `rf` fires on any MCU with a radio module; agent categories (`other`, `misc`) are coarse.
- **Revisions:** the representative of a revision cluster is usually, not always, the latest revision.
- **Unloadable boards** (binary pre-6 Eagle such as 11 Mutable Instruments designs, ASCII Altium, merge-conflicted files) are listed with reasons in `found/unloadable.rejected.jsonl`.

## Sources
- manifests: [wide.jsonl](../../../bench/manifests/wide.jsonl), [wide-noncommercial.jsonl](../../../bench/manifests/wide-noncommercial.jsonl), [wide-duplicates.jsonl](../../../bench/manifests/wide-duplicates.jsonl)
- scripts, candidate lists and rejects: [tools/research/board-sourcing/](../../../tools/research/board-sourcing/README.md)
- [OSHWA certification directory](https://certification.oshwa.org/list.html), [kicad-happy catalog @8bae5a0](https://github.com/aklofas/kicad-happy-testharness/blob/8bae5a0c5a74d2d41366f0a9ee4f9cfa12b2a043/reference/repo_catalog.json), [PCBench @dec3be75](https://github.com/PCBench/PCBench/tree/dec3be75cbdef74787625f9043c7391cd473bb64)

See also: [open-board-sources.md](open-board-sources.md), [local-board-corpus.md](local-board-corpus.md), [licensing-tiers-and-contamination.md](licensing-tiers-and-contamination.md)
