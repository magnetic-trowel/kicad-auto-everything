# kaebench

Benchmark harness for automated and LLM-driven KiCad placement and routing. It
fetches real boards from a manifest, turns them into route and place tasks, runs a
method (an "adapter") on each task k times, and scores every attempt by re-opening
the saved board with `kicad-cli` under the board's own rules. Design rationale:
[docs/topics/verification/harness.md](../docs/topics/verification/harness.md).

## Setup (Ubuntu 22.04/24.04, e.g. sk-tibia)

```bash
git clone -b claude/gallant-newton-lt98do https://github.com/magnetic-trowel/kicad-auto-everything
cd kicad-auto-everything
bench/scripts/setup.sh          # KiCad 10 (PPA, no recommends), Freerouting 2.5.0, bench/.venv
source bench/.venv/bin/activate
kaebench doctor
```

Other OSes: install KiCad 10 and point `KAE_KICAD_CLI` / `KAE_KICAD_PYTHON` (an
interpreter that can `import pcbnew`) at it; set `KAE_FREEROUTING` to a Freerouting
binary or JAR (the JAR needs Java 25). Run `pytest bench/tests` to check the install.

## Usage

```bash
M=bench/manifests/candidates.jsonl
kaebench fetch   -m $M -j 8                 # download boards at pinned commits (verifies sha256)
kaebench prepare -m $M -j 8                 # convert to KiCad 10, qualify, build route/place tasks
kaebench run --adapter reference --kinds route,place --probe freerouting -j 8 --name human
kaebench run --adapter freerouting -k 5 --timeout 900 -j 8 --name fr-2.5.0
kaebench report kae-work/results/human kae-work/results/fr-2.5.0
```

Everything lives under `--workdir` (default `./kae-work`): `cache/` (fetched files),
`tasks/<id>/{reference,route,place}/` and `results/<run>/<adapter>/<kind>/<id>/attempt-N/`.
Runs resume: re-running with the same `--name` skips finished attempts.

Useful filters on `fetch`/`prepare`: `--tiers permissive`, `--tags rf,ddr`, `--only id1,id2`,
`--limit N`. On `run`: `--splits A,B` (A ≤ 31 pads, B ≤ 100, C larger), `--all` to include
boards whose human layout is not clean.

## Suites

`bench/suites/*.txt` are board-id lists for `--only @FILE`:
- `kaebench tasks --write-suite FILE` writes the boards that qualified on your KiCad version.
- `qualified-kicad-10.0.7.txt`: the 112 manifest boards that qualified on KiCad 10.0.7.
- `pcbworld-d3{a,b,c}-test.txt` are PCBWorld's D3 eval splits (99 / 10 / 10).

### Reproducing PCBWorld's routing baseline

PCBWorld's D3 boards are PCBench boards run through PCBWorld's own chain: KiCad 5→9.0.8 conversion, DRC repair, guide generation. Build them with that chain, then import them:

```bash
# in a PCBWorld checkout (https://github.com/LGAI-Research/PCBWorld); builds its KiCad engine
export PCBWORLD_DATA_ROOT=$PWD/var/datasets
bash tools/quickstart/prepare_pcbench.sh --workers 16
# back in this repo
kaebench --workdir kae-d3 prepare-dir --dir $PCBWORLD_DATA_ROOT/pcbench/exacad_sorted \
  --board-glob processed_v9_guide_v3.kicad_pcb --only @bench/suites/pcbworld-d3a-test.txt --kinds route -j 16
kaebench --workdir kae-d3 run --adapter freerouting --passes 10 -k 5 -j 16 --name fr-2.5.0-mp10
```

PCBWorld published Freerouting 2.1.0 `-mp 10` at 0.80 (D3-A) and 0.78 (D3-B) clean-pass @5. Our scoring re-saves boards with KiCad 10 and uses each board's own severities. Expect close but not identical numbers; report both.

## Adapters

| Adapter | What it does |
|---|---|
| `reference` | The human layout: original copper (route) or original placement (place) |
| `noop` | Returns the task input unchanged (lower bound) |
| `freerouting` | Specctra DSN → Freerouting (`-mt 1`, analytics off, per-attempt pass schedule) → SES with placement block stripped → import |
| any name + `--command` | External tool; template placeholders `{input} {output} {workdir} {kind} {attempt} {timeout}` |

Example external router: `kaebench run --adapter myrouter --command "python my_router.py {input} {output}"`.
The tool reads `{input}` (a `.kicad_pcb` with its project files beside it) and writes `{output}`.

## Scoring

- **Fresh process, reference rules.** The output board is copied into a scoring
  directory with the reference `.kicad_pro`/`.kicad_dru`, zones are refilled, and
  `kicad-cli pcb drc` runs. Methods never score themselves and cannot change rules.
- **Integrity.**
  - Route results must keep placement, pad nets and the board `setup` block.
  - Place results must keep pad nets, locked footprints and `setup`.
  - Anything else is invalid.
- **Route metrics.**
  - `clean`: valid, 0 unconnected, 0 error-level DRC violations. Severities come from the board's own project; library-environment checks are excluded.
  - `completion`: share of start-of-task unconnected items now routed.
  - `wl_ratio`: track length relative to the human layout.
  - `via_delta`: via count minus the human layout's.
- **Place metrics.**
  - `legal`: no courtyard/clearance errors, every pad inside the board outline.
  - `hpwl_ratio` relative to the human placement.
  - With `--probe freerouting`, the placement is routed by a fixed router and scored like a route result, Cypress-style.
- **Best-of-k** picks the attempt by clean, then completion, errors, track length (PCBWorld's best-potential @k). The report shows `cp1` (attempt 0) and `cpk`.

## Manifests

`bench/manifests/*.jsonl`, one board per line: `id`, `repo`, `commit` (40-hex),
`pcb_path`, `license` (required), plus `pcb_sha256`, `license_tier`, stats and
`tags`. Boards are never redistributed; only manifests are committed
(CDLA-Permissive-2.0).

## Known limitations

- KiCad 10 SES import deletes unlocked copper and applies placement. The adapter strips the SES placement block, and route tasks start without copper.
- Freerouting necks tracks down below the board's minimum width near fine-pitch pads. KiCad DRC flags this as `track_width`.
- Freerouting has no seed flag, so best-of-k varies the pass count (`-mp` 10, 20, 30, ...).
- `inside` uses pad centres against the board outline. Courtyard-vs-edge overhang is not checked.
