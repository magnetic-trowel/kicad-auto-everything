# Wide board corpus (second sourcing pass, 2026-10-21)

Scope: the `wide.jsonl` / `wide-noncommercial.jsonl` manifests: licence policy, source sectors, harness changes, tag filters. Not here: pipeline mechanism, dedup parameters, load fixes and headline counts -> [research/data/board-corpus](../../research/data/board-corpus.md); the local folder build -> [local-board-corpus](local-board-corpus.md); the 297-board benchmark set -> [open-board-sources](open-board-sources.md).
Keys: `bench/manifests/wide.jsonl`, wide-noncommercial.jsonl, licence policy, noncommercial, direct-* dataset tags, host-robots-restricted, archive_sha256

## Corpus at a glance

- **14,318 boards from 8,757 repos**: [`wide.jsonl`](../../../bench/manifests/wide.jsonl) 13,475 + [`wide-noncommercial.jsonl`](../../../bench/manifests/wide-noncommercial.jsonl) 843; pinned by commit (or sha256 for downloads), with stats and KiCad 10.0.7 DRC. With the 297 of [`candidates.jsonl`](../../../bench/manifests/candidates.jsonl): ≈14,600 test boards [P, measured].
- Layer mix, size, routed and DRC-clean counts, rejects, conversions, near-duplicates -> [board-corpus#results](../../research/data/board-corpus.md#results).
- Near-duplicate map: [`wide-duplicates.jsonl`](../../../bench/manifests/wide-duplicates.jsonl).

## Licence policy (user decisions, applied to every row)

Every licence was read, not taken from GitHub's detector [P].

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

- Scope rule: a licence explicitly scoped to firmware or libraries does not cover the boards; an unscoped conflict (e.g. LICENSE MIT, README "hardware CC-BY-SA") takes the more restrictive licence. Ambiguous "some boards are NC" (Mutable Shruthi filters) is filed NC [P].
- Why each tier may be tested: [licensing-tiers-and-contamination](licensing-tiers-and-contamination.md#what-testing-each-tier-allows).
- Top licences: [board-corpus#results](../../research/data/board-corpus.md#results).

## Sources

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

Candidate lists, rejects with reasons, scripts: [tools/research/board-sourcing/](../../../tools/research/board-sourcing/README.md).

## Pipeline

Find and verify (agents, `probe.py`/`atcommit.py`, quoted licence evidence) → fingerprint and de-duplicate (`sig.py`) → enrich (`enrich.py`, mostly on a 50-core host) → merge (`merge.py`, validated by `kaebench.manifest`). Mechanism and parameters -> [board-corpus#idea-and-how-it-works](../../research/data/board-corpus.md#idea-and-how-it-works).

## Harness changes this pass needed

- `pcb_path` may name an Eagle/Allegro `.brd`, Altium `.PcbDoc`, PADS `.asc` or CADSTAR `.cpa`; fetch converts it (`kicad-cli pcb import`) and keeps `pcb_sha256` as the upstream hash.
- Rows with `archive_sha256` and no commit fetch a zip/tar or single file (Arduino, Raspberry Pi, Zenodo); `file_urls` adds pinned project files.
- Import repairs for boards KiCad 10 refuses to load -> [board-corpus#import-and-load-fixes](../../research/data/board-corpus.md#import-and-load-fixes).
- Raw-file fetch for GitLab hosts and Codeberg, git fallback, polite retries on HTTP 429.

## Hosts and robots.txt

- gitlab.fabcloud.org disallows raw files for all agents and everything for AI crawlers: nothing fetched; its 16 Fab Academy boards come from fabacademy.org copies [P].
- **778 rows** on hosts whose robots.txt disallows raw-file and/or git paths (gitlab.com, codeberg.org, gitlab.cern.ch, source.mnt.re, openbeagle.org, source.puri.sm, smaller ones) carry tag `host-robots-restricted`; drop them with a tag filter if fetches must honour robots.txt. Per-host counts -> [local-board-corpus#hosts-and-robotstxt](local-board-corpus.md#hosts-and-robotstxt) [P].

## Using the wide manifests [I]

1. `wide.jsonl` for breadth, `candidates.jsonl` for the scored benchmark. Most wide rows are not DRC-clean: score against the reference's own error count, as for `candidates`.
2. Tag filters: `drc-clean` (2,449) for routing-completion tests; `6plus`/`bga`/`ddr`/`pcie` for stress; `unrouted` (716) only for placement; exclude `imported-*` when import artefacts would confound a result.
3. Keep `noncommercial` opt-in and out of anything redistributed or used commercially.
4. Re-run licence and robots checks at each refresh; hosts and licences change.

## Open questions

- Licence-classification depth, heuristic tags, revision representatives: known limits -> [board-corpus#verdict](../../research/data/board-corpus.md#verdict). Example of restrictive lean: a repo with MIT hardware tagged NC because of a sub-folder licence; agent categories (`other`, `misc`) are coarse.
- Unloadable boards (binary pre-6 Eagle such as 11 Mutable Instruments designs, ASCII Altium, merge-conflicted files) are listed with reasons in `found/unloadable.rejected.jsonl`.

## Sources

- manifests: [wide.jsonl](../../../bench/manifests/wide.jsonl), [wide-noncommercial.jsonl](../../../bench/manifests/wide-noncommercial.jsonl), [wide-duplicates.jsonl](../../../bench/manifests/wide-duplicates.jsonl)
- scripts, candidate lists, rejects: [tools/research/board-sourcing/](../../../tools/research/board-sourcing/README.md)
- [OSHWA certification directory](https://certification.oshwa.org/list.html), [kicad-happy catalog @8bae5a0](https://github.com/aklofas/kicad-happy-testharness/blob/8bae5a0c5a74d2d41366f0a9ee4f9cfa12b2a043/reference/repo_catalog.json), [PCBench @dec3be75](https://github.com/PCBench/PCBench/tree/dec3be75cbdef74787625f9043c7391cd473bb64)
