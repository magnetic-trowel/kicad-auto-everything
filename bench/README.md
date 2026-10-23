# kaebench

Benchmark harness for automated and LLM-driven KiCad placement and routing. It
fetches real boards from a manifest, turns them into route and place tasks, runs a
method (an "adapter") on each task k times, and scores every attempt by re-opening
the saved board with `kicad-cli` under the board's own rules. Design rationale:
[docs/topics/verification/harness.md](../docs/topics/verification/harness.md).

## Setup (Ubuntu 22.04/24.04)

```bash
git clone https://github.com/magnetic-trowel/kicad-auto-everything
cd kicad-auto-everything
bench/scripts/setup.sh          # KiCad 10 (PPA, no recommends), Freerouting 2.5.0, bench/.venv
source bench/.venv/bin/activate
kaebench doctor
```

**Without sudo** the same script still works:
- KiCad runs from the official `kicad/kicad:10.0.7` image, unpacked into `~/.cache/kaebench` (~2.5 GB). It needs no root and no `/dev/fuse`.
- It uses an installed Apptainer or Singularity. Without one, it installs Apptainer 1.5.4 rootless into `~/.cache/kaebench/apptainer` (~160 MB) with Apptainer's own `install-unprivileged.sh`, which unpacks EL8 RPMs. Python stand-ins replace `rpm2cpio` and `cpio` if they are missing.
- The rootless install needs x86_64 and unprivileged user namespaces. Check with `unshare -Ur true && echo ok`. Ubuntu 22.04 allows them by default; 24.04 blocks them unless an admin relaxes `kernel.apparmor_restrict_unprivileged_userns`.
- If `python3-venv` is missing, the venv comes from `uv`.
- Freerouting, the venv and `env.sh` all live in your home directory. Set `KAE_HOME` to put the large files on another disk.
- `source bench/.venv/bin/activate` picks up the KiCad wrapper. Force this route with `--kicad container`.
- The container sees `$HOME`, `/tmp` and the current directory. For a `--workdir` elsewhere, export `APPTAINER_BIND=/that/path`.
- `--command` methods run sandboxed under bubblewrap, which the script does not install (`apt-get install bubblewrap`; it also needs unprivileged user namespaces). `kaebench doctor` reports whether it works; built-in adapters don't need it.

Other OSes or setups: point `KAE_KICAD_CLI` / `KAE_KICAD_PYTHON` at KiCad 10. Both accept a command with a wrapper, e.g. `flatpak run --command=kicad-cli org.kicad.KiCad`, or use `KAE_KICAD_WRAP` as a prefix for both. The Python must be able to `import pcbnew`. Set `KAE_FREEROUTING` to a Freerouting binary or JAR; the JAR needs Java 25. Run `pytest bench/tests` to check the install.

## Usage

```bash
M=bench/manifests/candidates.jsonl
kaebench fetch   -m $M -j 8                 # download boards at pinned commits (verifies sha256)
kaebench prepare -m $M -j 8                 # convert to KiCad 10, qualify, build route/place tasks
kaebench run --adapter reference --kinds route,place --probe freerouting -j 8 --name human
kaebench run --adapter freerouting -k 5 --timeout 900 -j 8 --name fr-2.5.0
kaebench report kae-work/results/human kae-work/results/fr-2.5.0
```

`report` keeps runs apart: when two runs use the same adapter name, their rows are labelled `adapter@run`, and it warns when the runs were scored by different score versions.

Everything lives under `--workdir` (default `./kae-work`): `cache/` (fetched files),
`tasks/<id>/{reference,route,place}/` and `results/<run>/<adapter>/<kind>/<id>/attempt-N/`.
Runs resume: re-running with the same `--name` skips finished attempts.

Useful filters on `fetch`/`prepare`: `--tiers permissive`, `--tags rf,ddr`, `--only id1,id2`,
`--limit N`. On `run`: `--splits A,B` (A ≤ 31 pads, B ≤ 100, C larger), `--all` to include
boards whose human layout is not clean.

## Suites

`bench/suites/*.txt` are board-id lists for `--only @FILE`:
- `kaebench tasks --write-suite FILE` writes the boards that qualified on your KiCad version.
- `qualified-kicad-10.0.7.txt`: the 112 manifest boards that qualified on KiCad 10.0.7 under task spec 1, before the round-trip (spec 4) and zone-uuid (spec 6) rules. Regenerate it with `prepare --force` and `tasks --write-suite` before relying on it.
- `pcbworld-d3{a,b,c}-test.txt` are the D3 test splits from PCBWorld's `d3.json` (99 / 10 / 10 boards). The paper reports results on the first two; D3-B itself has 287 boards.

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

PCBWorld published Freerouting 2.1.0 `-mp 10` at 0.80 (D3-A) and 0.78 (D3-B) clean-pass @5, and 0.75 / 0.64 @1 (4-seed means). Its @5 is the clean status of the best-potential (Φ) rollout of five, not "any clean attempt" (see Scoring). Our scoring re-saves boards with KiCad 10 and uses each board's own severities. Expect close but not identical numbers; report both.

With `--passes` fixed, every attempt runs the same command. If Freerouting's single-threaded runs are deterministic (it seeds its random choices with a constant; [dev-eval-plan](../docs/topics/verification/dev-eval-plan.md) H4), the five attempts are identical and `cpk` equals `cp1`, so compare with PCBWorld's @1 until that is checked (plan item 0.12).

## Adapters

| Adapter | What it does |
|---|---|
| `reference` | The human layout: original copper (route) or original placement (place) |
| `noop` | Returns the task input unchanged (lower bound) |
| `freerouting` | Specctra DSN → Freerouting (`-mt 1`, analytics off, per-attempt pass schedule, neck-down off, board edge/hole clearances passed, DSN widths clamped to the board minimum) → SES with placement block stripped → import |
| `freerouting-stock` | Same round trip with Freerouting's default settings |
| any name + `--command` | External tool; template placeholders `{input} {output} {workdir} {kind} {attempt} {timeout}` |

Example external router: `kaebench run --adapter myrouter --command "python my_router.py {input} {output}"`.
The tool reads `{input}` (a `.kicad_pcb` with its project files beside it) and writes `{output}`.

**Sandbox.** `--command` methods run under bubblewrap (`bwrap`):
- no network;
- a private `/tmp` and `/var/tmp`;
- a home directory that shows only the kaebench tool cache (`KAE_HOME`), the current directory and any `--sandbox-ro PATH`;
- the workdir's tasks and results hidden, plus anything in `KAE_SANDBOX_HIDE` (colon-separated);
- only the attempt's own work directory writable.

A method can't read the reference layout it is scored against, download it, or touch other attempts. The task input itself still carries some human decisions: route tasks keep the full human placement, and place tasks keep the human side assignment, zones and silkscreen. On timeout the whole sandbox is killed. `--sandbox-net` allows network access, for LLM methods. `--no-sandbox` turns the sandbox off; the report then marks those attempts as unsandboxed.

## Scoring

- **Rebuilt board, reference rules, fresh process.** The scorer never judges the file a method wrote. It rebuilds the board from the task input plus only the changes the task allows:
  - route: the tracks, arcs and vias, copied as KiCad's own re-save of them;
  - place: each unlocked footprint's position, rotation and side.

  The rebuilt board gets the reference `.kicad_pro`/`.kicad_dru`, zones are refilled, and `kicad-cli pcb drc` runs. Edits to rules, outline, keepouts, zones, pads, layers or nets can't change a score. Rules files a method writes are never read: the output is opened next to the task's own project files.
  - Teardrops, groups and tuning patterns are part of the routing. They are stripped from task inputs and are not transplanted or scored.
- **Integrity (`valid`).** Anything else the method changed is still detected, by comparing KiCad re-saves of output and input with the allowed changes normalized away (`foreign` lists them). Such a result is invalid.
  - Route results must keep placement, pad nets and every other board object, and route only on the board's copper layers and nets.
  - Place results must keep pad nets and every non-pose property, leave anchored footprints where they are (locked ones, and ones carrying Edge.Cuts, which are part of the board outline), and not add or remove footprints or copper.
- **Copy check.** `copy` reports how much of the output reproduces the human layout exactly: tracks to 1 µm, or poses to 1 µm and 0.01°. `suspect_copy` flags at least 20 tracks and 60% matching, or at least 5 parts and 50%. It is report-only until calibrated on real methods. The sandbox is the enforcement.
- **Route metrics.**
  - `clean`: valid, 0 unconnected, 0 error-level DRC violations. Severities come from the board's own project; library-environment checks are excluded.
  - `completion`: share of start-of-task unconnected items now routed.
  - `wl_ratio`: track length relative to the human layout.
  - `via_delta`: via count minus the human layout's.
- **Place metrics.**
  - `legal`: valid, no courtyard, clearance, edge-clearance, hole or keepout errors, and no footprint with more pad centres outside the board outline than the same footprint has in the human placement. Edge connectors may overhang as far as the designer's do.
  - `hpwl_ratio` relative to the human placement.
  - With `--probe freerouting`, the rebuilt placement is routed by a fixed router and scored like a route result, Cypress-style. This is not the Cypress protocol itself, which routes with Freerouting v1.9.0 on two free layers and scores the share of pin pairs routed. An external router can be the probe: `--probe NAME --probe-command TEMPLATE` (or `probe=NAME,probe_command=TEMPLATE` in an `--arm`, without commas), run sandboxed as a route method.
- **Best-of-k** picks the attempt by clean, then completion, errors, track length, so `cpk` is any-clean@k: a board counts if any attempt is clean. PCBWorld's @k instead takes the best-potential (Φ) rollout and asks whether it is clean, so `cpk` can only be higher. The report shows `cp1` (attempt 0) and `cpk`.
- **Rescoring.** After a scoring fix, `kaebench rescore RUN_DIR -j N` scores a run's saved outputs (and saved probe routes) again with the current scorer, without re-running the method. Each attempt records the version it was rescored from.
- **Versions.** Every attempt records `score_version` (now 6). Tasks are at spec 6: locked footprints and footprints carrying Edge.Cuts stay in place, teardrops are stripped, repeated footprint and zone uuids are made unique, and the human layout must pass the round trip. Route tasks need spec 4 or later and place tasks spec 5 or later; re-run `prepare --force` on older task folders.
- **Red-team tests.** `bench/tests/test_redteam.py` runs cheating methods (move parts, delete a keepout, grow the outline, add a layer, shrink pads, swap nets, ship own rules, read or overwrite the reference, use the network) and requires each to be invalid, blocked or ineffective. Add a case for every new cheat found.

## Manifests

`bench/manifests/*.jsonl`, one board per line: `id`, `repo`, `commit` (40-hex),
`pcb_path`, `license` (required), plus `pcb_sha256`, `license_tier`, stats and
`tags`. Boards are never redistributed; only manifests are committed
(CDLA-Permissive-2.0).

## Known limitations

- KiCad 10 SES import deletes unlocked copper and applies placement. The adapter strips the SES placement block, and route tasks start without copper.
- Freerouting necks tracks down below the board's minimum width near fine-pitch pads and shrinks some to 75% to meet edge clearance; the `freerouting` adapter disables neck-down, but edge-driven shrinking remains (KiCad flags it as `track_width`).
- Freerouting has no seed flag, so best-of-k varies the pass count (`-mp` 10, 20, 30, 15, 25, 40, 50, 60). The attempts are nested runs of one seeded search, not independent samples ([dev-eval-plan](../docs/topics/verification/dev-eval-plan.md) H4).
- `inside` uses pad centres against the board outline. Courtyard-vs-edge overhang is not checked.
