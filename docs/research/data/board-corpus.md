# Wide open-board corpus

**Status:** worked (data infrastructure).
**First published:** 2026-10-21, commit [c03ad19](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c03ad199c26ea51932bd798bc05d00d068d9dfb0) on branch `claude/compassionate-ramanujan-lo56ee`.

We collected 14,318 open-hardware boards from 8,757 repositories. Each one is pinned by commit
or sha256, has had its licence read, has been de-duplicated by content, and loads in KiCad 10.0.7
with statistics and a DRC report. About 17% of them are DRC-clean, as committed, under their own
rules.

## Idea and how it works

The pipeline has four stages. Agents do the first; scripts do the rest
([tools/research/board-sourcing](../../../tools/research/board-sourcing/README.md)).

1. **Find and verify.** Candidates come from:
   - the [kicad-happy catalog](https://github.com/aklofas/kicad-happy-testharness/blob/8bae5a0c5a74d2d41366f0a9ee4f9cfa12b2a043/reference/repo_catalog.json), whose 5,856 repos were audited at the catalog's pinned hashes;
   - the OSHWA certification directory;
   - GitHub topics, Codeberg and GitLab search, and awesome-lists;
   - vendor organisations (Adafruit, SparkFun, Arduino, Olimex, Antmicro, OHWR, Sinara and others);
   - keyboard and eurorack lists;
   - [punkfab/pcb-corpus](https://github.com/punkfab/pcb-corpus/tree/1e999b4eefd5fdfcc90dc376d2882390245a8e0d), and [PCBench](https://github.com/PCBench/PCBench/tree/dec3be75cbdef74787625f9043c7391cd473bb64) folders traced back to their upstream repos.

   `probe.py` and `atcommit.py` list a repo's licence files and board files at a pinned commit.
   `classify.py` assigns a licence family from the licence and README text. Each accepted row
   quotes its licence evidence.
2. **Fingerprint and de-duplicate** (`sig.py`; see [below](#near-duplicate-removal)).
3. **Enrich** (`enrich.py`). For each board: fetch at the pinned commit, import non-KiCad formats,
   collect pcbnew statistics (layers, footprints, nets, tracks, vias, zones, size), then run
   `kicad-cli pcb drc` on the board as saved, under its own `.kicad_pro`/`.kicad_dru`. When
   connections are missing, a second DRC runs after a zone refill. Each board's DRC is read
   through the benchmark's own `tools.summarize_drc`. Heuristic tags are added (`2layer`/
   `4layer`/`6plus`, `drc-clean`, `unrouted`, `imported-eagle`, `bga`, `ddr`, `usb2`, `rf`, ...).
4. **Merge** (`merge.py`). Results are matched by (repo, commit, path). Manual licence decisions
   are applied, a final sha256 de-duplication runs against mirrors and the benchmark candidates,
   non-commercial rows are split off, and every row is validated against the `kaebench.manifest`
   schema.

`corpus.py` turns the manifests into one local folder with one directory per board, holding the
board, project rules, DRC report and manifest row. It is resumable, and `--prune` drops ids that
are no longer listed.

### Licence policy

Every licence was read by a person or agent; GitHub's licence detector was not trusted. Where
signals conflict, the more restrictive licence wins. A licence scoped to firmware or libraries
does not cover the boards.

| Signal | Decision | Tier |
|---|---|---|
| MIT, BSD, Apache, ISC, 0BSD, Unlicense, CC0, CC-BY, CERN-OHL-P, Solderpad | accept | permissive |
| CERN-OHL-W, LGPL, MPL, EPL | accept | weak-copyleft |
| GPL, AGPL | accept | copyleft |
| CERN-OHL-S, CERN-OHL-1.x, CC-BY-SA, TAPR-OHL | accept | reciprocal-hardware |
| CC-BY-NC(-SA), custom non-commercial terms, TAPR-NCL | accept into a separate file | noncommercial |
| ND, "use but not modify", no licence, all rights reserved, vendor EULA, AI/benchmark bans, reverse-engineered commercial boards | reject | — |

Robots.txt is honoured:
- Nothing is fetched from gitlab.fabcloud.org. Its 16 Fab Academy boards come from
  fabacademy.org copies, pinned by sha256.
- 778 rows on hosts whose robots.txt disallows raw-file or git paths are tagged
  `host-robots-restricted`, and a fresh build skips them.

### Near-duplicate removal

- **Fingerprint.** For each KiCad board, a feature set: the multiset of footprint library ids
  (`fp:<id>#<k>` for the k-th copy), the multiset of values (`v:<value>#<k>`) and the set of net
  names (`n:<name>`). Positions are ignored, so revisions, forks and re-spins with the same circuit
  match.
- **Candidates.** MinHash uses 96 permutations (`((h XOR seed) × 0x9E3779B97F4A7C15) mod 2^64`),
  and LSH uses 24 bands of 4 rows. Buckets with more than 400 members are skipped.
- **Decision.** The exact Jaccard similarity of the two feature sets must be at least 0.75. Pairs
  that pass are joined with union-find, and so are boards with equal file sha256.
- **Imported boards** (Eagle, Altium, ...) are compared by sha256 only, because importing every
  candidate just to fingerprint it was too slow.
- **Representative per cluster.** Rows already in the benchmark win. After that the order is: the
  curated source, the newer file-format version, more track segments, more features, then the path
  as a tie-break.
- Boards with fewer than 10 features (blank templates, panels, covers) are dropped as near-empty.

### Import and load fixes

Non-KiCad boards are converted at fetch time with `kicad-cli pcb import`. Some boards that KiCad 10
refuses to load are repaired. Each repair changes only the boards that failed to load, and none
changes connectivity:

| Fix | Applies to |
|---|---|
| Items on Eagle `UNDEFINED` or KiCad `Rescue` layers moved to `Cmts.User` | converted Eagle boards, a few native ones |
| Unquoted numeric net names quoted | KiCad 4/5 files |
| `(version)` moved ahead of SPDX comment lines; a 2017 dev-build `user_via` form normalised | a few native boards |
| Eagle silkscreen logos (imported as tens of thousands of zones) turned into graphic polygons | 252 Eagle boards |
| Piles of ≥ 1,000 sub-micron track arcs that same-net copper already covers dropped | 1 board |

A fresh build gives byte-identical native boards and DRC reports. Converted boards get new random
UUIDs on every import, so a few overlap violations can switch between `clearance` and
`shorting_items`. Statistics and unconnected counts do not change.

### Local corpus layout

```
<corpus>/manifest.jsonl                 one row per board (= boards/<id>/row.json)
<corpus>/boards/<id>/board.kicad_pcb    loads in KiCad 10; converted and load-fixed if needed
                    board.kicad_pro     when upstream has one (6,737 boards)
                    board.kicad_dru     when upstream has one (475)
                    source.brd|.pcbdoc  original file of converted boards (2,922)
                    drc.json            kicad-cli DRC, as saved, under the board's own rules
```

Manifest fields:
- `repo`, `commit` and `pcb_path`;
- `pcb_sha256`, the hash of the upstream file;
- `license`, `license_tier` and `license_evidence`;
- the pcbnew statistics;
- `routed`;
- `tags` and `notes`.

The `board.*` names match the benchmark harness's layout, so harness helpers work on a corpus
folder directly.

## What we tried

- **Sources.** Two sourcing passes. The first produced the 297-board benchmark candidate set
  ([open-board-sources](../../topics/data/open-board-sources.md)). The second, described here,
  searched source sectors one by one (keyboards and synths, vendors, complex FPGA/SoC boards,
  breakouts, RF, robotics and power, demo and evaluation boards, and others).
- **Licence review.** Agents read the licences in each sector. kicad-happy rows were classified by
  script, and agents reviewed the 317 repos where signals conflicted.
- **Compute.** Enrichment ran mostly on a shared 50-core host. A second host worked the same list
  from the other end, and results merged by id.

## Results

Source for all of these: the wide-corpus and local-corpus docs at
[c03ad19](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c03ad199c26ea51932bd798bc05d00d068d9dfb0)
and [a6b4dc9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/a6b4dc93623cb8a46c57f7aa783ee1b4a623f21a).
All figures are from KiCad 10.0.7.

| Quantity | Value |
|---|---|
| Accepted boards (repos) | 14,318 (8,757): 13,475 in `wide.jsonl`, 843 in `wide-noncommercial.jsonl` |
| Rejected repos | 6,994, mostly no licence (2,849) or no board files (2,263) |
| Layers | 11,495 two-layer, 2,193 four-layer, 630 with 6+ (255 with 10+, max 18) |
| Size | median 38 footprints; 458 boards ≥ 300, 49 ≥ 1,000 |
| Routed (copper present, 0 unconnected after zone refill) | 11,360 (79%) |
| DRC-clean as committed, own rules | 2,449 (17%) |
| Unrouted (placement only) | 716 |
| Converted at fetch | Eagle 2,472, Altium 419, Allegro 32, PADS 14; 1,473 KiCad 4/5 files |
| Near-duplicates removed | 1,637 (map in `wide-duplicates.jsonl`), plus ~600 near-empty |
| Top licences | MIT 3,223; GPL-3.0 1,988; CC-BY-SA-4.0 1,975; CERN-OHL-S 1,156; CC-BY-SA-3.0 999; CERN-OHL-1.2 794; Apache 668; CC-BY-NC-SA-4.0 568 |

A local build on the sourcing host held 14,597 boards: the wide rows plus the 297 candidates,
including 760 robots-restricted boards fetched before that tag existed. A fresh build gives about
13,837. By tier, the host's build had 5,557 permissive, 244 weak-copyleft, 7,953 copyleft or
reciprocal-hardware, and 843 noncommercial boards. Its counts differ slightly from the manifest
counts above (2,553 `drc-clean`, 11,619 routed) because the candidates are included.

## Verdict

As data infrastructure, the corpus worked: it is wide, legally clean and reproducible. Three
lessons carry over to other projects:
- **Most open boards are not DRC-clean under their own rules.** A benchmark should score a method
  against the reference board's own error count, not against zero.
- **Content fingerprints on footprints, values and nets** find revisions and forks that names and
  hashes miss. The threshold of 0.75 was set by inspection, not tuned.
- **Load failures cluster** in a handful of import constructs, and each needs only a small,
  connectivity-preserving repair.

Known limits:
- Licence classification is deeper for sector rows than for kicad-happy rows. Errors lean
  restrictive.
- Interface tags are heuristic; `rf`, for example, fires on any MCU with a radio module.
- The representative of a revision cluster is usually, but not always, the latest revision.
- 202 boards report 16 layers. They are mostly Eagle conversions that declare every Eagle layer.
- **Possible missed duplicates.** `sig.py` builds MinHash signatures with Python's salted `hash()`,
  and caches them in the work dir. Signatures cached by one process are not comparable with those
  made by a later process, so a resumed run can miss near-duplicate pairs. It cannot merge
  unrelated boards, because the exact Jaccard check decides. Set `PYTHONHASHSEED` or use a stable
  hash before re-running.

## Code

- **On main:** [tools/research/board-sourcing](../../../tools/research/board-sourcing/README.md).
  The scripts are `probe.py`, `atcommit.py`, `classify.py`, `kh_select.py`, `sig.py`, `enrich.py`,
  `merge.py` and `corpus.py`.
- **Not ported**, left on branch [`claude/compassionate-ramanujan-lo56ee`](https://github.com/magnetic-trowel/kicad-auto-everything/tree/claude/compassionate-ramanujan-lo56ee):
  - the manifests (`bench/manifests/wide*.jsonl`, 13 MB in all);
  - the candidate and reject lists;
  - the fetch-time import and load repairs in `bench/src/kaebench/{fetch,boardfiles,manifest}.py`,
    from commits [dfacba0](https://github.com/magnetic-trowel/kicad-auto-everything/commit/dfacba0be374f2effda2d70574022306e4a62153),
    [28f61e7](https://github.com/magnetic-trowel/kicad-auto-everything/commit/28f61e76d6be204e44a5a7031f15a9eda542a93b),
    [db6cd48](https://github.com/magnetic-trowel/kicad-auto-everything/commit/db6cd483f123121c1e5c9f3cb8657ee74fbd47cf),
    [390771e](https://github.com/magnetic-trowel/kicad-auto-everything/commit/390771e3d4240e8115f82135f762a72d25427527)
    and [bc33b73](https://github.com/magnetic-trowel/kicad-auto-everything/commit/bc33b73c36ec13e26c7fa01a55b4b981e2a57868);
  - `bench/scripts/build-corpus.sh`.

  The scripts need that branch's `kaebench`.
- **Run:** see the board-sourcing README. In outline: `sig.py` → `enrich.py` → `merge.py` →
  `corpus.py <out> --fetch-missing --drc --no-fetch-tag host-robots-restricted name=rows.jsonl@workdir ...`.

## Related

- [Data area map](README.md)
- [Licensing tiers and contamination](../../topics/data/licensing-tiers-and-contamination.md)
- [Open board sources](../../topics/data/open-board-sources.md)
- [Corpora and yield](../../topics/data/corpora-and-yield.md)
- Untested data ideas: [planted-solution boards and git-history repair pairs](../ideas.md#learning-and-data-l)
