# Local board corpus (`kae-boards`)

Scope: building, laying out and using the local folder of every accepted board (~14,600 open-hardware PCBs; 13,837 in a fresh build). Not here: how boards were found and vetted -> [open-board-sources](open-board-sources.md), [wide-board-corpus](wide-board-corpus.md); method and load-fix mechanism -> [research/data/board-corpus](../../research/data/board-corpus.md).
Keys: kae-boards, build-corpus.sh, `manifest.jsonl`, `boards/<id>/`, `board.kicad_pcb`, drc.json, copy_board, KAE_KICAD_WRAP, --no-fetch-tag, license_tier, fidelity

## Getting the corpus

Facts: never committed (third-party licences); git holds only manifests pinning each board by commit or sha256. Default location `~/kae-boards`; a host keeping it elsewhere says so in its git-ignored `CLAUDE.local.md`. Every board opens in KiCad 10; converted and repaired boards are flagged by tags and notes.

| Step | Command | Notes |
|---|---|---|
| Install KiCad 10.0.7 and the venv | `bench/scripts/setup.sh --no-freerouting` | No sudo: rootless Apptainer + official KiCad image. `kaebench doctor` must pass |
| Build | `bench/scripts/build-corpus.sh [OUT_DIR] [WORKDIR]` | Defaults `~/kae-boards`, `~/kae-boards-work`. `J=8` for parallel jobs. Resumable: rerun the same command |
| Check | `wc -l ~/kae-boards/manifest.jsonl` | 13,837 rows on a fresh host; more if the cache already held robots-restricted boards |

Build = fetch each board at its pinned commit (or sha256 for downloads) → convert Eagle, Altium, Allegro, PADS with `kicad-cli pcb import` → load fixes ([Fidelity](#fidelity-what-differs-from-upstream)) → DRC. Cost: several hours, ≈28 GB corpus + a similar amount in `WORKDIR` (fetch cache, deletable afterwards).

Host etiquette in the fetcher ([fetch.py](../../../bench/src/kaebench/fetch.py)):
- retries HTTP 429/5xx using Retry-After, holding off the whole host;
- `J` stays modest: do not raise it against GitHub or GitLab to go faster;
- rows tagged `host-robots-restricted` never fetched ([below](#hosts-and-robotstxt));
- nothing fetched from gitlab.fabcloud.org (robots.txt disallows raw files); its Fab Academy boards come from fabacademy.org.

Inputs = reviewed, committed manifests carrying final licence decisions and sha256 dedup; later rows win for the same id.

| Collection | Rows | File |
|---|---|---|
| `wide` | 13,475 | [bench/manifests/wide.jsonl](../../../bench/manifests/wide.jsonl) |
| `wide-noncommercial` | 843 | [bench/manifests/wide-noncommercial.jsonl](../../../bench/manifests/wide-noncommercial.jsonl) |
| `candidates` | 297 | [bench/manifests/candidates.jsonl](../../../bench/manifests/candidates.jsonl), the benchmark set |

Builder [corpus.py](../../../tools/research/board-sourcing/corpus.py): add a collection with `name=rows.jsonl@workdir` (any kaebench manifest or enrich results); `--prune` removes folders no longer in the inputs.

### Hosts and robots.txt

778 `wide` rows tagged `host-robots-restricted` (host's robots.txt disallows raw-file or git paths):

| Host | Rows |
|---|---|
| gitlab.com | 391 |
| codeberg.org | 258 |
| hub.allspice.io | 33 |
| gitlab.cba.mit.edu | 24 |
| openbeagle.org | 19 |
| source.mnt.re | 17 |
| gitlab.cern.ch | 16 |

- `build-corpus.sh` passes `--no-fetch-tag host-robots-restricted`: those boards are included only when the work dir's cache already holds them.
- Fresh build ≈ 13,837 boards. The original sourcing host fetched 760 before the tag existed and keeps them: 14,597.
- `raw.githubusercontent.com` has no robots.txt; GitHub rows fetch normally.

## Layout

```
kae-boards/
  manifest.jsonl              one JSON row per board (= boards/<id>/row.json)
  boards/<id>/
    board.kicad_pcb           opens in KiCad 10; converted and load-fixed if needed
    board.kicad_pro           project settings and design rules, when upstream has one (6,737)
    board.kicad_dru           custom DRC rules, when upstream has them (475)
    source.brd|.pcbdoc|.asc   original file, for converted boards (2,922)
    drc.json                  kicad-cli DRC report, as saved, under the board's own rules
    row.json                  manifest row
```

`board.*` names match the harness layout: `kaebench.boardfiles.copy_board(src_dir, dst_dir)` and `install_rules()` work on a corpus folder directly ([boardfiles.py](../../../bench/src/kaebench/boardfiles.py)).

### Manifest fields

| Field | Meaning |
|---|---|
| `id` | slug, also the folder name |
| `collection` | input it came from; `also_in` if another input had the same id |
| `repo`, `commit`, `pcb_path` | upstream location; download rows have `commit: null` and `archive_sha256` |
| `pcb_sha256` | hash of the **upstream** file, before conversion or fixes |
| `license`, `license_tier`, `license_evidence` | SPDX id, tier ([Licensing](#licensing)), quoted evidence |
| `layers`, `footprints`, `nets`, `tracks`, `vias`, `zones`, `board_mm` | pcbnew stats from the enrich step |
| `routed` | copper present and 0 unconnected after a zone refill |
| `tags` | e.g. `2layer`/`4layer`/`6plus`, `drc-clean`, `partially-routed`, `unrouted`, `imported-eagle`/`-altium`, `legacy-format`, `no-project-rules`, `no-schematic`, circuit hints (`usb2`, `ddr`, `fpga`, `rf`, ...) |
| `notes` | provenance and DRC summary in words |
| `file_urls` | download rows only: where `.kicad_pro`/`.kicad_dru` came from |

## Working with boards

- Pick boards from the manifest, not by walking folders:
  ```python
  import json
  rows = [json.loads(l) for l in open("/home/<you>/kae-boards/manifest.jsonl")]
  small_clean = [r for r in rows if r["layers"] == 2 and "drc-clean" in r["tags"] and r["footprints"] < 60]
  ```
- Treat the folder as read-only: copy first (`boardfiles.copy_board("~/kae-boards/boards/<id>", workdir)` or `cp -r`); filter on `license_tier` before anything leaves the machine.
- KiCad: with the venv active, `$KAE_KICAD_WRAP kicad-cli pcb drc ...` runs `kicad-cli`, `$KAE_KICAD_WRAP python3` runs pcbnew (the venv sources `KAE_KICAD_WRAP`). Stats and placement ops: `kaebench.tools.run_ops(...)`. Run KiCad under `ulimit -v 40000000` and a timeout: a few boards are heavy.
- Read DRC through [tools.summarize_drc](../../../bench/src/kaebench/tools.py): the benchmark's definition; ignores library-only checks. `drc.json` = board **as saved**, no zone refill. Many upstream boards carry DRC errors: compare before/after on the same board; 0 is not the expected state.
- Benchmark tasks: `kaebench prepare`/`run` on `candidates.jsonl` ([bench/README](../../../bench/README.md)); the corpus does not replace the harness's scoring.

## Licensing

| Tier | Boards | Use |
|---|---|---|
| permissive | 5,557 | anything, with attribution |
| weak-copyleft | 244 | anything, with attribution; modifications to the files stay under the same licence |
| copyleft, reciprocal-hardware | 7,953 | anything internal; derived boards or data products inherit the licence |
| noncommercial | 843 | private, non-commercial evaluation only; never feeds a redistributed product |

Counts: the sourcing host's 14,597 boards. Rules: [licensing-tiers-and-contamination](licensing-tiers-and-contamination.md). Never commit board files or post them elsewhere; commit ids and summaries.

## Fidelity: what differs from upstream

- Load fixes (connectivity-preserving, each tested in `bench/tests`) and import reproducibility (native boards byte-identical; converted boards get new UUIDs, so `clearance`/`shorting_items` may swap or duplicate) -> [board-corpus#import-and-load-fixes](../../research/data/board-corpus.md#import-and-load-fixes).
- 202 boards report 16 layers, mostly Eagle conversions declaring all 16 Eagle copper layers: count tracks per layer before trusting `layers`.
- Mirror and `.git`-URL duplicates removed by sha256 in the wide manifests ([wide-duplicates.jsonl](../../../bench/manifests/wide-duplicates.jsonl)); near-duplicates removed before enrichment (Jaccard ≥ 0.75 on footprints, values, nets); converted boards compared by exact hash only.
- Sourcing-host counts: 11,630 2-layer, 2,286 4-layer, 479 with 6+; 11,619 routed; 2,553 `drc-clean`; 2,937 converted (differ from manifest counts because candidates are included).
- Rejected boards with reasons: `tools/research/board-sourcing/found/*.rejected.jsonl` (unconvertible formats, corrupt upstream files, DRC that never finishes, no permitted source).

## Open questions

- [dev-eval-plan](../verification/dev-eval-plan.md#where-we-start) quotes an earlier snapshot (13,749 KiCad-10-loadable, 10,902 fully routed, 2,412 drc-clean, 1,663 repos); the sourcing-host counts above are later.

## Sources

- Builder and inputs: [board-sourcing README](../../../tools/research/board-sourcing/README.md), [corpus.py](../../../tools/research/board-sourcing/corpus.py), [build-corpus.sh](../../../bench/scripts/build-corpus.sh)
- Fetch and fixes: [fetch.py](../../../bench/src/kaebench/fetch.py), [boardfiles.py](../../../bench/src/kaebench/boardfiles.py)
- related: [corpora-and-yield](corpora-and-yield.md), [verification/harness](../verification/harness.md)
