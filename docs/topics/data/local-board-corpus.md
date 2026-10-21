# Local board corpus (`kae-boards`)

**TL;DR**
- **One folder holds every accepted board:** ~13,749 open-hardware PCBs. Each board is in `boards/<id>/` as `board.kicad_pcb`, plus its own `.kicad_pro`/`.kicad_dru`, a KiCad 10.0.7 DRC report and its manifest row. `manifest.jsonl` sits at the top.
- **It is built locally and never committed** (third-party licences). Git holds only the manifests that pin each board by commit or sha256. To build it, run `bench/scripts/setup.sh --no-freerouting`, then `bench/scripts/build-corpus.sh`.
- **The default location is `~/kae-boards`.** A host that keeps it elsewhere says so in its git-ignored `CLAUDE.local.md`.
- **Treat the folder as read-only.** Copy a board to a scratch dir before changing it, and filter on `license_tier` before anything leaves the machine.
- **Every board opens in KiCad 10.** Converted and repaired boards are flagged by tags and notes.

## Getting the corpus

| Step | Command | Notes |
|---|---|---|
| Install KiCad 10.0.7 and the venv | `bench/scripts/setup.sh --no-freerouting` | Needs no sudo: rootless Apptainer and the official KiCad image. `kaebench doctor` must pass. |
| Build | `bench/scripts/build-corpus.sh [OUT_DIR] [WORKDIR]` | Defaults are `~/kae-boards` and `~/kae-boards-work`. Set `J=8` for parallel jobs. The build is resumable: rerun the same command. |
| Check | `wc -l ~/kae-boards/manifest.jsonl` | Expect 13,749 rows. |

The build fetches each board at its pinned commit, or by sha256 for downloads. It then converts Eagle, Altium, Allegro and PADS boards with `kicad-cli pcb import`, applies the load fixes in [Fidelity](#fidelity-what-differs-from-upstream), and runs DRC. Expect several hours and about 26 GB for the corpus, plus a similar amount in `WORKDIR` (the fetch cache). That cache can be deleted afterwards.

Host etiquette is built into the fetcher ([fetch.py](../../../bench/src/kaebench/fetch.py)):
- it retries HTTP 429/5xx using Retry-After, holding off the whole host;
- `J` stays modest;
- nothing is fetched from gitlab.fabcloud.org, whose robots.txt disallows raw files. Its Fab Academy boards come from fabacademy.org instead.

Do not raise `J` against GitHub or GitLab to go faster.

Inputs, all committed (later rows win for the same id):

| Collection | Rows | File |
|---|---|---|
| `sourcing-batch1` | 5,815 | [results/wobbly-tibia.jsonl](../../../tools/research/board-sourcing/results/wobbly-tibia.jsonl) |
| `sourcing-batch2` | 7,621 | [results/wobbly-tibia-2.jsonl](../../../tools/research/board-sourcing/results/wobbly-tibia-2.jsonl) |
| `sourcing-fabacademy` | 16 | [results/wobbly-tibia-2-fabmirror.jsonl](../../../tools/research/board-sourcing/results/wobbly-tibia-2-fabmirror.jsonl) |
| `candidates` | 297 | [bench/manifests/candidates.jsonl](../../../bench/manifests/candidates.jsonl), the benchmark set |

The builder is [corpus.py](../../../tools/research/board-sourcing/corpus.py). To add a new collection, pass `name=rows.jsonl@workdir`. Rows can be enrich results or any kaebench manifest.

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

The `board.*` names match the harness's own layout. So `kaebench.boardfiles.copy_board(src_dir, dst_dir)` and `install_rules()` work on a corpus folder directly ([boardfiles.py](../../../bench/src/kaebench/boardfiles.py)).

### Manifest fields

| Field | Meaning |
|---|---|
| `id` | slug, also the folder name |
| `collection` | which input it came from; `also_in` if another input had the same id |
| `repo`, `commit`, `pcb_path` | upstream location; download rows have `commit: null` and `archive_sha256` |
| `pcb_sha256` | hash of the **upstream** file, before conversion or fixes |
| `license`, `license_tier`, `license_evidence` | SPDX id, tier (see below), quoted evidence |
| `layers`, `footprints`, `nets`, `tracks`, `vias`, `zones`, `board_mm` | pcbnew stats from the enrich step |
| `routed` | copper present and 0 unconnected after a zone refill |
| `tags` | e.g. `2layer`/`4layer`/`6plus`, `drc-clean`, `partially-routed`, `unrouted`, `imported-eagle`/`-altium`, `legacy-format`, `no-project-rules`, `no-schematic`, and circuit hints (`usb2`, `ddr`, `fpga`, `rf`, ...) |
| `notes` | provenance and the DRC summary in words |
| `file_urls` | download rows only: where the `.kicad_pro`/`.kicad_dru` came from |

## Working with boards

- **Pick boards from the manifest, not by walking folders:**
  ```python
  import json
  rows = [json.loads(l) for l in open("/home/<you>/kae-boards/manifest.jsonl")]
  small_clean = [r for r in rows if r["layers"] == 2 and "drc-clean" in r["tags"] and r["footprints"] < 60]
  ```
- **Never edit in place.** Copy first: `boardfiles.copy_board("~/kae-boards/boards/<id>", workdir)`, or `cp -r`.
- **KiCad commands:** with the venv active, `$KAE_KICAD_WRAP kicad-cli pcb drc ...` runs `kicad-cli`, and `$KAE_KICAD_WRAP python3` runs pcbnew (the venv sources `KAE_KICAD_WRAP`). For stats and placement operations use `kaebench.tools.run_ops(...)`. Run KiCad under `ulimit -v 40000000` and a timeout: a few boards are heavy.
- **Read DRC through [tools.summarize_drc](../../../bench/src/kaebench/tools.py).** It is the benchmark's definition, and it ignores library-only checks. `drc.json` is the board **as saved**, with no zone refill. Many upstream boards carry DRC errors, so compare before and after on the same board; don't treat 0 as the expected state.
- **For benchmark tasks,** use `kaebench prepare`/`run` on `candidates.jsonl` ([bench/README](../../../bench/README.md)). The corpus does not replace the harness's scoring.

## Licensing

| Tier | Boards | Use |
|---|---|---|
| permissive | 5,004 | anything, with attribution |
| weak-copyleft | 225 | anything, with attribution; keep modifications to the files under the same licence |
| copyleft, reciprocal-hardware | 7,687 | anything internal; derived boards or data products inherit the licence |
| noncommercial | 833 | private, non-commercial evaluation only; never feeds a redistributed product |

Rules: [licensing-tiers-and-contamination](licensing-tiers-and-contamination.md). Never commit board files or post them elsewhere. Commit IDs and summaries.

## Fidelity: what differs from upstream

Load fixes, all connectivity-preserving and each covered by a test in `bench/tests`:

| Fix | Applies to |
|---|---|
| Items on Eagle `UNDEFINED` or KiCad `Rescue` layers moved to `Cmts.User` | converted Eagle boards, a few native boards |
| Unquoted numeric net names quoted | KiCad 4/5 files |
| `(version)` moved ahead of SPDX lines | a few native boards |
| A 2017 dev-build `user_via` form normalised | 1 board |
| Silkscreen logo rectangles (imported as zones) made graphic polygons | 252 Eagle boards |
| Piles of ≥1,000 sub-micron track arcs already covered by same-net copper dropped | 1 board |

Reproducibility:
- A fresh build gives **byte-identical** native boards and DRC reports.
- **Converted boards** get new random UUIDs on every import. A few overlap violations can then switch between `clearance` and `shorting_items`, or appear twice. Stats and unconnected counts are unchanged.

Caveats:
- 203 boards report 16 layers. Most are Eagle conversions that declare all 16 Eagle copper layers; count tracks per layer before trusting `layers`.
- 14 boards were sourced from both GitHub and a Codeberg mirror. One row was kept for each.
- Near-duplicates were removed before enrichment (Jaccard ≥ 0.75 on footprints, values and nets). Converted boards were compared by exact hash only.
- Rejected boards and the reasons for each are in `tools/research/board-sourcing/found/*.rejected.jsonl`: unconvertible formats, corrupt upstream files, DRC that never finishes, and boards with no permitted source.

## Sources

- Builder and inputs: [board-sourcing README](../../../tools/research/board-sourcing/README.md), [corpus.py](../../../tools/research/board-sourcing/corpus.py), [build-corpus.sh](../../../bench/scripts/build-corpus.sh)
- Fetch and fixes: [fetch.py](../../../bench/src/kaebench/fetch.py), [boardfiles.py](../../../bench/src/kaebench/boardfiles.py)

See also: [open-board-sources](open-board-sources.md) (how boards were found and vetted), [licensing-tiers-and-contamination](licensing-tiers-and-contamination.md), [corpora-and-yield](corpora-and-yield.md), [verification/harness](../verification/harness.md).
