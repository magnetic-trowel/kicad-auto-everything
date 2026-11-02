# Wide open-board corpus

**Status:** worked (data infrastructure).
**First published:** 2026-10-21, commit [c03ad19](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c03ad199c26ea51932bd798bc05d00d068d9dfb0) on branch `claude/compassionate-ramanujan-lo56ee`.

Scope: method and results of the second sourcing pass: 14,318 open-hardware boards from 8,757 repos, each pinned by commit or sha256, licence read, de-duplicated by content, loaded in KiCad 10.0.7 with stats and DRC; ≈17% DRC-clean as committed under their own rules. Not here: licence policy table and source sectors -> [wide-board-corpus](../../topics/data/wide-board-corpus.md); building and using the local folder -> [local-board-corpus](../../topics/data/local-board-corpus.md).
Keys: board sourcing, sig.py, MinHash, LSH, Jaccard 0.75, union-find, near-duplicate, enrich.py, merge.py, load fixes, PYTHONHASHSEED

## Idea and how it works

Four stages; agents do stage 1, scripts the rest ([tools/research/board-sourcing](../../../tools/research/board-sourcing/README.md)).

1. **Find and verify.** Candidate sources:
   - [kicad-happy catalog](https://github.com/aklofas/kicad-happy-testharness/blob/8bae5a0c5a74d2d41366f0a9ee4f9cfa12b2a043/reference/repo_catalog.json): 5,856 repos audited at the catalog's pinned hashes;
   - OSHWA certification directory; GitHub topics, Codeberg and GitLab search, awesome-lists;
   - vendor organisations (Adafruit, SparkFun, Arduino, Olimex, Antmicro, OHWR, Sinara and others); keyboard and eurorack lists;
   - [punkfab/pcb-corpus](https://github.com/punkfab/pcb-corpus/tree/1e999b4eefd5fdfcc90dc376d2882390245a8e0d); [PCBench](https://github.com/PCBench/PCBench/tree/dec3be75cbdef74787625f9043c7391cd473bb64) folders traced to upstream repos.

   `probe.py`/`atcommit.py` list a repo's licence and board files at a pinned commit; `classify.py` assigns a licence family from licence + README text; each accepted row quotes its licence evidence.
2. **Fingerprint and de-duplicate** (`sig.py`; [below](#near-duplicate-removal)).
3. **Enrich** (`enrich.py`), per board: fetch at pinned commit; import non-KiCad formats; pcbnew stats (layers, footprints, nets, tracks, vias, zones, size); `kicad-cli pcb drc` as saved under its own `.kicad_pro`/`.kicad_dru`; if connections are missing, a second DRC after zone refill. DRC read through the benchmark's `tools.summarize_drc`. Heuristic tags (`2layer`/`4layer`/`6plus`, `drc-clean`, `unrouted`, `imported-eagle`, `bga`, `ddr`, `usb2`, `rf`, ...).
4. **Merge** (`merge.py`): match results by (repo, commit, path); apply manual licence decisions; final sha256 dedup against mirrors and benchmark candidates; split off non-commercial rows; validate every row against the `kaebench.manifest` schema.

`corpus.py` turns the manifests into one local folder, one directory per board (board, project rules, DRC report, manifest row); resumable; `--prune` drops ids no longer listed. Layout and manifest fields -> [local-board-corpus#layout](../../topics/data/local-board-corpus.md#layout); the `board.*` names match the harness layout, so harness helpers work on a corpus folder directly.

### Licence policy

Every licence read by a person or agent, not GitHub's detector; conflicting signals → more restrictive wins; a licence scoped to firmware or libraries does not cover boards. Signal → tier table (NC accepted into a separate file; ND, no licence, EULAs, AI/benchmark bans, reverse-engineered boards rejected): [wide-board-corpus#licence-policy](../../topics/data/wide-board-corpus.md#licence-policy-user-decisions-applied-to-every-row).

Robots.txt honoured: nothing fetched from gitlab.fabcloud.org (its 16 Fab Academy boards come from fabacademy.org copies, pinned by sha256); 778 rows on hosts disallowing raw-file or git paths tagged `host-robots-restricted`, skipped by a fresh build.

### Near-duplicate removal

| Step | Rule |
|---|---|
| Fingerprint | per KiCad board, feature set = multiset of footprint library ids (`fp:<id>#<k>` for the k-th copy) ∪ multiset of values (`v:<value>#<k>`) ∪ set of net names (`n:<name>`). Positions ignored, so revisions, forks, re-spins with the same circuit match |
| Candidates | MinHash, 96 permutations, `((h XOR seed) × 0x9E3779B97F4A7C15) mod 2^64`; LSH 24 bands × 4 rows; skip buckets > 400 members |
| Decision | exact Jaccard of the two feature sets ≥ 0.75; join passing pairs and equal-file-sha256 boards with union-find |
| Imported boards (Eagle, Altium, ...) | sha256 only (importing every candidate to fingerprint was too slow) |
| Representative | rows already in the benchmark win; then curated source, newer file-format version, more track segments, more features, path as tie-break |
| Near-empty | < 10 features (blank templates, panels, covers) dropped |

### Import and load fixes

Non-KiCad boards are converted at fetch time with `kicad-cli pcb import`. Boards KiCad 10 refuses to load are repaired; each repair touches only failing boards, none changes connectivity, each covered by a test in `bench/tests`:

| Fix | Applies to |
|---|---|
| Items on Eagle `UNDEFINED` or KiCad `Rescue` layers moved to `Cmts.User` | converted Eagle boards, a few native ones |
| Unquoted numeric net names quoted | KiCad 4/5 files |
| `(version)` moved ahead of SPDX comment lines | a few native boards |
| A 2017 dev-build `user_via` form normalised | 1 board |
| Eagle silkscreen logos (imported as tens of thousands of zones) turned into graphic polygons | 252 Eagle boards |
| Piles of ≥ 1,000 sub-micron track arcs already covered by same-net copper dropped | 1 board |

Reproducibility: a fresh build gives byte-identical native boards and DRC reports. Converted boards get new random UUIDs on every import, so a few overlap violations can switch between `clearance` and `shorting_items` (or appear twice); stats and unconnected counts do not change.

## What we tried

- Sources: two passes. Pass 1 → 297-board benchmark candidate set ([open-board-sources](../../topics/data/open-board-sources.md)). Pass 2 (here) searched sectors one by one: keyboards and synths, vendors, complex FPGA/SoC, breakouts, RF, robotics and power, demo and evaluation boards, others.
- Licence review: agents read licences per sector; kicad-happy rows classified by script, agents reviewed the 317 repos with conflicting signals.
- Compute: enrichment mostly on a shared 50-core host; a second host worked the same list from the other end; results merged by id.

## Results

Source: wide-corpus and local-corpus docs at [c03ad19](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c03ad199c26ea51932bd798bc05d00d068d9dfb0) and [a6b4dc9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/a6b4dc93623cb8a46c57f7aa783ee1b4a623f21a). KiCad 10.0.7.

| Quantity | Value |
|---|---|
| Accepted boards (repos) | 14,318 (8,757): 13,475 in `wide.jsonl`, 843 in `wide-noncommercial.jsonl` |
| Rejected repos | 6,994, mostly no licence (2,849) or no board files (2,263) |
| Layers | 11,495 two-layer, 2,193 four-layer, 630 with 6+ (255 with 10+, max 18) |
| Size | median 38 footprints; 458 boards ≥ 300, 49 ≥ 1,000 |
| Routed (copper present, 0 unconnected after zone refill) | 11,360 (79%) |
| DRC-clean as committed, own rules | 2,449 (17%) |
| Unrouted (placement only) | 716 |
| Converted at fetch | Eagle 2,472, Altium 419, Allegro 32, PADS 14; 1,473 KiCad 4/5 files; all load in KiCad 10 |
| Near-duplicates removed | 1,637 revisions, forks, mirrors (map in `wide-duplicates.jsonl`), plus ~600 near-empty |
| Top licences | MIT 3,223; GPL-3.0 1,988; CC-BY-SA-4.0 1,975; CERN-OHL-S 1,156; CC-BY-SA-3.0 999; CERN-OHL-1.2 794; Apache 668; CC-BY-NC-SA-4.0 568 |

Local-build counts (14,597 on the sourcing host incl. 297 candidates and 760 pre-tag robots-restricted boards; ≈13,837 fresh; per-tier counts) -> [local-board-corpus](../../topics/data/local-board-corpus.md#hosts-and-robotstxt).

## Verdict

Worked as data infrastructure: wide, legally clean, reproducible. Transferable lessons:
1. Most open boards are not DRC-clean under their own rules: score a method against the reference board's own error count, not zero.
2. Content fingerprints on footprints, values and nets find revisions and forks that names and hashes miss. Threshold 0.75 set by inspection, not tuned.
3. Load failures cluster in a handful of import constructs; each needs only a small, connectivity-preserving repair.

Known limits:
- Licence classification deeper for sector rows than for kicad-happy rows; errors lean restrictive.
- Interface tags heuristic; `rf` fires on any MCU with a radio module.
- Revision-cluster representative is usually, not always, the latest revision.
- 202 boards report 16 layers: mostly Eagle conversions declaring every Eagle layer.
- **Possible missed duplicates:** `sig.py` builds MinHash signatures with Python's salted `hash()` and caches them in the work dir; signatures from different processes are not comparable, so a resumed run can miss near-duplicate pairs. It cannot merge unrelated boards (the exact Jaccard check decides). Set `PYTHONHASHSEED` or use a stable hash before re-running.

## Code

- On main: [tools/research/board-sourcing](../../../tools/research/board-sourcing/README.md): `probe.py`, `atcommit.py`, `classify.py`, `kh_select.py`, `sig.py`, `enrich.py`, `merge.py`, `corpus.py`.
- Also on main (merged from `claude/compassionate-ramanujan-lo56ee` on 2026-11-01): manifests (`bench/manifests/wide*.jsonl`, 13 MB); candidate and reject lists; fetch-time import and load repairs in `bench/src/kaebench/{fetch,boardfiles,manifest}.py`, commits [dfacba0](https://github.com/magnetic-trowel/kicad-auto-everything/commit/dfacba0be374f2effda2d70574022306e4a62153), [28f61e7](https://github.com/magnetic-trowel/kicad-auto-everything/commit/28f61e76d6be204e44a5a7031f15a9eda542a93b), [db6cd48](https://github.com/magnetic-trowel/kicad-auto-everything/commit/db6cd483f123121c1e5c9f3cb8657ee74fbd47cf), [390771e](https://github.com/magnetic-trowel/kicad-auto-everything/commit/390771e3d4240e8115f82135f762a72d25427527), [bc33b73](https://github.com/magnetic-trowel/kicad-auto-everything/commit/bc33b73c36ec13e26c7fa01a55b4b981e2a57868); `bench/scripts/build-corpus.sh` ([local-board-corpus](../../topics/data/local-board-corpus.md)).
- Run (see board-sourcing README): `sig.py` → `enrich.py` → `merge.py` → `corpus.py <out> --fetch-missing --drc --no-fetch-tag host-robots-restricted name=rows.jsonl@workdir ...`.

## Related

- [Data area map](README.md); [licensing tiers and contamination](../../topics/data/licensing-tiers-and-contamination.md); [corpora and yield](../../topics/data/corpora-and-yield.md)
- Untested data ideas: [planted-solution boards and git-history repair pairs](../../ideas/original/learning-and-data.md)
