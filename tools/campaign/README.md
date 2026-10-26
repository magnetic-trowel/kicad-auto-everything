<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Campaigns: corpus-wide router baselines

`campaign.py` runs a fixed set of routers over every board of the local corpus
(`~/kae-boards`, see `docs/topics/data/local-board-corpus.md`). It queues one
[kaeq](../kaeq/README.md) job per board, so the run is unattended, resumable and capped for a
shared host. Results are kept in the home directory, so later methods can be compared
against them.

## Per board

Each job does the following, in a private scratch directory that kaeq deletes afterwards:

1. **Prepare.** `kaebench prepare-dir` builds the route task: convert to KiCad 10, DRC the human layout under the board's own rules, strip the copper.
2. **Route and score.** `kaebench run` runs, interleaved and with k = 1:
   - `human`: the reference adapter, i.e. the original copper scored the same way;
   - each router through the `freerouting` adapter, with the campaign's timeout.

   Each attempt is scored by kaebench (score v7): clean, completion, unconnected, DRC errors by type, `wl_ratio` and `via_delta` against the human layout, the router's CPU time and peak RSS, and the scoring cost.
3. **Physics.** `physics_board.py` runs kae's routed module physics (the measure of `tools/research/joint/joint_physics.py`) on the human board and on every router's scored board. The brief comes from the human placement, so module ids pair across boards. It records Σu, its ratio to the human board, the median per-module value ratio, worst rail mΩ, and modules that are missing or have open hops.
4. **Bugs.** Each problem becomes one record in `bugs.json` (schema below).
5. **Archive.** Results go to `~/kae-baselines/<campaign>/boards/<id>/`, written atomically. `record.json` marks the board as done.

Settings for every job:
- KiCad runs with `MaximumThreads=2` (in the campaign's own `kicad-config`).
- Freerouting gets `-Xmx` sized to the board and `-XX:ActiveProcessorCount=2`.
- The harness process tree has an address-space cap of 40 GB.

## Commands

```bash
C=tools/campaign/campaign.py
python3 $C init NAME --router fr-2.5.0=$HOME/.cache/kaebench/freerouting-2.5.0-linux-x64/bin/freerouting \
                     --router fr-fork-06d2686=$HOME/.cache/kaebench/kae-freerouting-fork-06d2686/bin/freerouting
python3 $C submit NAME [--limit 20 | --only id,id | --only @FILE]   # skips boards already done
python3 $C status NAME
python3 $C summarize NAME           # REPORT.md, results.csv, bugs/index.jsonl, bugs/BY-SIGNATURE.md
python3 $C install-timer NAME       # summarize hourly while it runs
kaeq status --owner campaign-NAME   # queue view; kaeq result ID for a failed job
```

`init` freezes the harness at a commit (a worktree in `NAME/code`, its own venv) and kae at
another (`NAME/kae-src`, `NAME/venv-kae`). A campaign's code never changes once started. Use a
new campaign name after changing a method or the scorer. Re-submitting a campaign resumes it.

## Layout of `~/kae-baselines/NAME/`

| Path | Contents |
|---|---|
| `campaign.json` | routers (path, version, jar sha256), code and kae commits, timeout, corpus manifest hash |
| `REPORT.md` | per arm, for all boards, human-clean boards, splits A/B/C and layer counts: cp1, completion, boards not closed, DRC errors per board, timeouts, no output, errors, CPU time, physics. Also DRC types, router final states, top bug signatures |
| `results.csv` | one row per board × arm, every metric above plus the router's own incomplete count, introduced violations and heap |
| `boards/<id>/record.json` | the board's summary: corpus metadata, task (split, pads, human DRC), each arm's full `attempt.json`, physics summary, step times |
| `boards/<id>/arms/<arm>/` | `attempt.json`, `drc.json` (scored board), `adapter.log.gz`, `result.json` (Freerouting's report), `board.ses.gz` (router output) |
| `boards/<id>/physics.json` | per-module physics of every board |
| `boards/<id>/bugs.json` | the board's bug records, with tracebacks and log tails |
| `bugs/BY-SIGNATURE.md` | bugs grouped by signature, most boards first: the fixing agent's work list |
| `bugs/index.jsonl` | all bug records |

To re-create a routed board, apply `board.ses.gz` to the route task. Rebuild the task with
`kaebench prepare-dir` from the corpus folder. For arms with a non-DRC bug, the router's exact
input is also kept: `arms/<arm>/artifacts/board.dsn.gz` and its SES. Freerouting bugs can then
be reproduced without KiCad, e.g. `freerouting -de board.dsn -do out.ses -mp 10 -mt 1`, plus the
flags in `attempt.json` → `adapter_meta.rule_args`.

## Bug records

Each record has `campaign`, `board`, `arm`, `category`, `signature` (the grouping key),
`detail` and `evidence` (paths under `boards/<board>/`). Some categories add fields.

| Category | Meaning |
|---|---|
| `prepare_error`, `prepare_timeout` | KiCad or kaebench could not build the route task (arm `harness`) |
| `run_error`, `score_error`, `attempt_missing` | harness failures |
| `adapter_error`, `ses_import_error` | the round trip failed: DSN export, the router, or KiCad's SES import |
| `router_crash`, `no_output`, `ses_incomplete` | the router wrote no usable session file |
| `no_output_at_deadline` | the router ignored its own job timeout and was killed with nothing written |
| `java_exception`, `java_oom` | exceptions in the router log (`exception`, `frame`, `count`), even when output was written |
| `unconnected_mismatch` | KiCad finds more unconnected items on the imported board than the router reported incomplete: connections lost in translation |
| `integrity` | the output changed something a route result may not |
| `drc` | DRC errors of one type (`drc_type`, `count`) beyond what the human layout has on the same board |
| `over_time` | the attempt overran its timeout by more than 5 % |
| `physics_error` | kae's physics failed on a board or module (arm `physics`) |

Unrouted connections and router timeouts are outcomes, not bugs: they are in `results.csv`
and `REPORT.md`.
