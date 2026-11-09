<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# kaeres: results store for routing and placement methods

`kaeres.py` keeps every routing and placement any method has produced, keyed by board. For
each result it records the exact code that produced it, linked to the commits on GitHub, so it
can be rerun. Its jobs run unattended through the [kaeq](../kaeq/README.md) queue. The store
lives in the home directory: `~/kae-baselines`, or `$KAE_RESULTS`.

## Schema

There are three kinds of record. Each is identified by a hash of what defines it.

| Record | Defined by (hashed) | Also stores |
|---|---|---|
| **method** | kind, runner (kaebench adapter + binary sha256, a `--command` template, or the human reference), parameters, KiCad version, code components (`repo` + `commit`) | a human-readable `name`, description, GitHub links, a copy of the binary, the build note, patches for uncommitted code |
| **run** | method id + board + attempt (+ task) | output board, logs, CPU and memory, the router's own report, the harness commit that ran it, the experiment that asked for it |
| **evaluation** | evaluator id: the content of the code that scores (git blob/tree ids of `score.py`, `tools.py`, `boardfiles.py`, `kicad_scripts/` for the DRC scorer; `kae/src` and `physics_board.py` for physics) + KiCad version | the score of one run |

Consequences:
- The same recipe always gets the same method id, under any name. Changing any commit, flag, timeout, binary or KiCad version gives a new id. Names may repeat across versions; the id tells them apart.
- A harness commit that does not touch scoring keeps the same DRC evaluator, so its scores stay comparable. A scoring change makes a new evaluator, and runs gain a new evaluation beside the old one. Runs are never redone for that.
- An **experiment** is a view: methods × boards, plus reports. A run that already exists for a method on a board is reused. Comparing a new router against the baseline only runs the new router.
- A task spec bump gives every board a new task id, but a run still counts on the new task when the task it ran on had the same content (see [Task aliases](#task-aliases)). Only boards whose prepared input changed are run again.
- Code must be pushed when it is registered, so every link works. `--allow-dirty` freezes uncommitted work as a local snapshot commit and saves its patch next to the method.

## Layout

```
~/kae-baselines/
  methods/<method-id>.json            name, recipe, code (repo, commit, link), binary copy, build note
  evaluators/<eval-id>.json           what scores: code ids, KiCad version, commits with links
  bins/<slug>-<sha8>/                 the exact router binaries methods run
  code/kicad-auto-everything@<sha12>/ frozen worktrees (+ .venv / .venv-kae) the jobs run
  boards/<board-id>/
    board.json                        corpus row
    tasks/<task-id>/task.json         prepared task (board sha256, task spec, KiCad); human DRC
    tasks/<task-id>/content.json      content hash of the prepared task, per harness commit that prepared it
    prepare-failures/<harness>.json   when a harness could not build the task
    runs/<slug>.<method-id8>.a<attempt>/
      run.json                        method, task, harness commit, timing, CPU, router outcome
      output.kicad_pcb.gz             the method's output board
      adapter.log.gz, router-report.json, board.ses.gz, artifacts/ (router input, kept when a bug was seen)
      restarts.json                   restart.py's per-attempt log; each route attempt's `fr` holds its Freerouting telemetry: `loops[i].unrouted` per pass, whole `fallback` attempts, `start_necked`, `pour_connected`, `pour_cut_off` (one entry per logged line), for the first routing and each repair round; top-level `fr_raw` says what fr-telemetry.tar holds and how much was dropped
      fr-telemetry.tar                every Freerouting run's whole log and result file, `<attempt>/<name>.gz`; attempts' telemetry together stay within 20 MB as stored per run on a board (restart.py, FR_RAW_LIMIT): past that the bulkiest raw parts go first, and `manifest.json` in the tar lists each one kept or dropped
      restart-report.json             the kept attempt's own report (a joint loop: iterations, windows, stop reason)
      restart-report-origin.json      when that board was resumed or had a final pass: the report of the fresh attempt it descends from
      evals/<eval-id>.json            score (DRC) or physics, per evaluator; <eval-id>.drc.json.gz
      bugs.json                       bug records of this run
  experiments/<name>/
    experiment.json, boards.txt       methods, harness and kae commits, evaluators
    REPORT.md, results.csv            per method: cp1, k, cpk, completion, not closed, DRC errors, timeouts, CPU, physics;
                                      paired tests against a baseline (below)
    bugs/BY-SIGNATURE.md, index.jsonl bugs grouped by signature: the work list for a fixing agent
  index.sqlite                        rebuildable cache over everything (kaeres index)
```

Run folders read as `fr-fork-master.3f9a1c2e.a0`: the method's name, then its id, then the attempt.

## Commands

```bash
K="python3 tools/kaeres/kaeres.py"
$K method add human --reference
$K method add "freerouting 2.5.0" --binary ~/.cache/kaebench/freerouting-2.5.0-linux-x64/bin/freerouting \
   --code router=https://github.com/freerouting/freerouting@v2.5.0 --build "release asset freerouting-2.5.0-linux-x64.zip"
$K method add "fr-fork master" --binary ~/.cache/kaebench/kae-freerouting-fork-06d2686/bin/freerouting \
   --code router=~/.cache/kaebench/src/freerouting --build "tools/research/routing/install_freerouting_fork.sh 06d2686"
$K method add "kae bridge" --command "{py:kae} -m kae.route.cli route {input} {output} --seed {attempt} --time {timeout}" \
   --code kae=.@origin/claude/vigilant-mayer-i91rrr        # place / joint: --kind joint; place adds --param probe=freerouting
$K method list
$K exp create NAME --method "freerouting 2.5.0" --method "fr-fork master" [--boards @ids.txt] --description "..."
$K exp submit NAME [--limit 20]       # one kaeq job per board that lacks a run; re-submitting resumes
$K exp status NAME; $K exp report NAME [--baseline METHOD]; $K exp install-timer NAME   # report + index hourly
$K board BOARD_ID                     # every method's run of this board, with its scores
$K rerun ~/kae-baselines/boards/ID/runs/RUN [--submit]   # the code, binary and command; queue a reproduction
$K index                              # then e.g. sqlite3 ~/kae-baselines/index.sqlite 'select ...'
```

A method runs with the harness commit recorded in it, and an experiment's jobs run the
experiment's frozen copy of `kaeres.py`. Code changes after `exp create` therefore change
nothing in that experiment.

## Running an experiment without wasting it

Lessons from experiments that ran and measured nothing (2026-11):
- **One harness for the experiment and its methods.** A method prepares its boards and runs its restart
  wrapper from its own `--harness`. Pin every method's `--harness` and the experiment's `--harness` to
  the same commit (or commits with the same `TASK_SPEC` and `restart.py`): a method pinned to a harness
  of another task spec runs every job and writes nothing, because its runs land on another task
  (`exp create` now refuses it); a wrapper from a harness without a flag the method uses (`--resume`)
  fails every run at once.
- **Run every arm at the same time.** On this shared host the same code, seeds and time budget left
  13.9 % more open connections a few days later (zone-keepout-ab2's fresh base against zone-ab's,
  47 boards, p < 0.001): more than any effect the recent A/Bs measured. A run reused from another
  experiment was made at another time, so `exp create` refuses methods that already have runs on the
  experiment's boards. Register a replicate instead (`method add` with the same recipe plus
  `--param replicate=<tag>`), so each board's job runs every arm side by side; `--reuse-runs` overrides,
  and the report then warns about boards whose arms ran more than 12 h apart.
- **Smoke first.** One or two boards, 1 attempt, `exp submit` on that experiment, then read the runs
  (status, scores, bug records) before submitting the full one.
- **`results.csv` holds attempt 0 only** (cp1's attempt). A multi-seed comparison reads every attempt from
  the run folders (`boards/<id>/runs/<slug>.<method8>.a<k>/`).
- **Timed jobs.** Runs budget on wall time, so their kaeq jobs must be class `timed` (never frozen).
  Before kaeq had classes, jobs frozen for memory ran shorter and worse, unevenly between arms;
  `kaeq`'s jobs table records `freezes` and `frozen_s` per job.
- **Big boards.** KiCad's DRC lists at most 499 unconnected items; the scorer, the restart judge and
  `kae.route.drc` count past it with pcbnew. Freerouting stops on its own time limit, so on big boards
  its result moves with host load; compare arms on the boards where a control did not move.

Lessons from the decide-ab campaign (2026-11, 17 experiments; plan and analysis scripts on branch
`decide-ab`, `experiments/decide-ab/`):
- **No `{` or `}` in a method's shell.** `--command` goes through `str.format`, so the shell's
  `${in%.kicad_pcb}` is read as a template field: every run of area-cost-ab failed with `KeyError: 'in%'`,
  and the report shows 0 / 0 / 0 rather than an error. Use `$(echo {input} | sed ...)` and smoke it.
- **Size the kaeq timeout for the hardest board, and retry time-outs before reading results.** A job
  runs every arm of one board in turn, so a time-out drops its later arms, mostly on the dense boards
  where arms differ most. 58 of 224 ladder jobs timed out at 2 h and an interim read was misleading.
  `kaeq retry --owner exp-<name> --timeout 6h`, then analyse only boards every arm finished.
- **Know the noise before claiming a difference.** The A/A (`aa-joint`: one joint-loop method under two
  names, 213 merit boards, k = 1) moved cp1 by 0.5 pp, 95 % CI −1.4 to +2.8 pp, with 5 boards flipped.
  With about 200 boards, effects under about 3 pp are not visible in cp1.
- **Test determinism before relying on k = 1.** area-cost-ab assumed kae-plain was deterministic, but
  only 22 of the ~53 boards that could not differ came out identical across arms: time-budgeted steps
  vary with host load.
- **Pick a metric close to the change.** Placement legality changes showed large effects in
  `legal_strict`, placement shorts per board and hazard counts, while cp1 did not move. Count boards
  with placement shorts per arm, not only totals; one board can dominate a total.
- **Reuse an arm only when its code path is unchanged.** A new arm at a later commit can be compared
  with older control runs only if the change cannot reach them (the ladder fix touched only the
  ladder path); otherwise rerun every arm at one commit.
- **kaeq's CPU column counts the job's own process.** A restart-wrapped job can show hours of wall
  time and seconds of CPU while its children work; check `ps` of the children before calling it hung.

## Per board job

1. **Preflight.** KiCad's Python must import pcbnew. If it can't, the job exits 75 and kaeq retries it; this is an infrastructure failure, not a board result.
2. **Prepare.** `kaebench prepare-dir` builds the route task once per harness commit. Its task id is the hash of the board file sha256, task spec and KiCad version. The job records the task's content hash, and that of the older tasks the methods' runs were made on (see [Task aliases](#task-aliases)).
3. **Run.** Every missing method runs in one `kaebench run` (built-in adapters, interleaved) or one run per `--command` method. The human layout (the `reference` method) is scored once per board. The kaebench score becomes the run's DRC evaluation.
4. **Physics.** `physics_board.py` runs kae's routed module physics on each new run's scored board. The brief is built from the task input, so module ids pair with the human run.
5. **Archive.** Run folders are written atomically, with bug records. If another experiment's job wrote the same run meanwhile, the first one is kept.

Settings for every job:
- KiCad runs with `MaximumThreads=2`.
- Freerouting gets `-Xmx` sized to the board (`java_heap=auto-v1`) and `-XX:ActiveProcessorCount=2`.
- The harness tree has a 40 GB address-space cap.

## Step cache (A/B arms that share early steps)

`$K exp create NAME --method A --method B --env KAE_STEP_CACHE=/var/tmp/$USER/step-cache ...` gives the
experiment's jobs kae's step cache (`kae/src/kae/route/stepcache.py`). The arms of one board run in one job,
one after the other, so arm B replays arm A's identical Freerouting runs and kicad-cli DRCs instead of
computing them again. The setting is in `experiment.json` (`env`), not in any method, so method ids do not
change; only result-neutral settings are accepted there. Methods need a harness commit whose sandbox binds
the cache directory (kaebench `Sandbox`) and whose `restart.py` charges cached time.

- Keys are content only (input bytes, tool, settings), never experiment or run paths, so any later A/B on the
  same input hits too. A Freerouting run that stopped by itself replays under any job timeout it fits in; one
  that stopped at its job timeout replays under that timeout. A DRC replays when it fits in its timeout. A
  hit costs its recorded duration: kae's clock and `restart.py`'s budgets, holds and kills count it as if
  the step had run.
- Fork points: each attempt's board after Freerouting's import (with the raw session), after repair and last
  mile, and at its end, keyed by input, seed, budget, options and the kae source (`stepcache.find_fork`).
- Size: at most `KAE_STEP_CACHE_MAX_GB` (default 50), gzip blobs deduplicated by content; past the cap the
  least recently used entries go, never one a job is reading. `python -m kae.route.stepcache stats|prune`.
- `run.json` → `work.step_cache` holds hits, misses, uncacheable steps, charged and saved seconds and the
  real wall time; `wall_s` is charged time.
- Put the cache on local disk, never the NFS home. Delete it any time; nothing else depends on it.

## Task aliases

Before task spec 10, prepare drew random uuids for objects that a board file stores no uuid for (KiCad 5/6 files, generated boards). Then one task id could stand for several different inputs, and a stored output re-scored against a new preparation came out invalid. From spec 10 on, prepare is deterministic: the same board bytes give byte-identical task files.

- **Content hash** (`task_content`, `v1:`). It covers the files of `reference/` and of the kind's input directory (`drc.json` reports, which are dated, are left out) and the parts of `task.json` that the scorer and runner read: reference stats, pads outside, the kind's task entry, split and project rules. Local paths, the task spec and the round trip are left out. Each job stores it in `tasks/<id>/content.json`, under the harness commit that prepared the task.
- **Alias.** `find_run` counts a run made on another task of the same board file, kind and KiCad when that task's content, as prepared by the run's own harness (`task_prepared_by`, else `harness_commit`), equals a content recorded for the wanted task. Inputs that differ never alias. A spec-9 preparation of a board without uuids is random, so it never equals the seeded one.
- **Old tasks.** Their content is computed lazily. The first job on a board at a newer spec re-prepares the board with each older harness commit whose runs it could reuse (`fill_old_contents`, one prepare per commit), if that harness's code is in `code/`. `kaeres job --content-only --harness H --board B --method M ...` does only this, so the queue can do it ahead of an experiment.
- **Older-spec methods.** From spec 10 on, a method pinned to a harness of an older task spec runs, with its own harness, on tasks prepared by the experiment's harness (`prep_harness`), and `exp create` accepts it. Its stored runs on unchanged boards are reused; on changed boards it runs again, on a deterministic task. Runs keep the DRC evaluation of the harness that scored them, as before.

## Bug records

Each record has `board`, `method` (a method name, `harness` or `physics`), `category`,
`signature` (the grouping key), `detail` and `evidence` (paths relative to the run folder).

| Category | Meaning |
|---|---|
| `prepare_error`, `prepare_timeout` | KiCad or kaebench could not build the task (in `prepare-failures/`) |
| `run_error`, `score_error`, `attempt_missing` | harness failures |
| `adapter_error`, `ses_import_error` | the round trip failed: DSN export, the router, or KiCad's SES import |
| `router_crash`, `no_output`, `ses_incomplete` | no usable session file |
| `no_output_at_deadline` | the router ignored its own job timeout and was killed with nothing written |
| `java_exception`, `java_oom` | exceptions in the router log (`exception`, `frame`, `count`), even when output was written |
| `unconnected_mismatch` | KiCad finds more unconnected items than the router reported incomplete: connections lost in translation |
| `integrity` | the output changed something a route result may not |
| `drc` | DRC errors of one type (`drc_type`, `count`) beyond the human layout's on the same board. `human_baseline` says what they were compared with: the experiment's own human score (signature `...:drc:<type>`), else the human's newest evaluation (`...:human-fallback`), else none (`...:no-human-baseline`, `count` is all of the run's errors). `exp report` recomputes these from the run's scores, without changing `bugs.json` |
| `over_time` | the attempt overran its timeout by more than 5 % |
| `physics_error` | kae's physics failed on a board or module |

Unrouted connections and timeouts are outcomes, not bugs: they are in `results.csv` and `REPORT.md`.

## Reading a report

- **cp1, k, cpk.** cp1 is attempt 0's clean rate. k is the most attempts any board has (the
  experiment's `--attempts`), and cpk is the share of boards with any clean attempt, so cpk = cp1
  when k = 1. A method named `… restarts` is wrapped by `restart.py`: one run is already the best
  of its internal seeds within one wall budget (the `restarts` column), so its cp1 is a best-of-N
  that a bare router's cp1 is not. Compare such methods with each other, or give the bare router
  the same CPU (the CPU column).
- **Paired against a baseline.** For each method against `--baseline` (default: the experiment's
  first method), on the boards both have run: exact McNemar for cp1 and cpk, a sign-flip test
  for completion and for cp1_mean (the clean share over all attempts, the primary), Holm over the
  secondaries, a 95 % bootstrap CI that resamples repositories, and the boards that flipped. A
  failed run counts as not clean. A board only one method has run yet is left out and counted
  ("not run by one"): finish both before concluding. Runs whose scorer failed (`score_error`)
  are left out too; rescore them. The code is `bench/src/kaebench/stats.py`, shared with
  `kaebench report`.
- **CPU.** The method's own report (`restart.py`'s `work.cpu_s`) when it has one, else kaebench's
  rusage. Before the kaebench launcher became a subreaper, rusage lost everything inside the
  bwrap sandbox (bwrap exits without reaping its pid 1), so every `--command` run made with an
  older harness reads ~0; those show as no value, or as the job step's cgroup CPU
  (`job_steps.run.cgroup_cpu_s`, recorded from now on, which also includes scoring).

To reproduce a router bug without KiCad, run Freerouting on `artifacts/board.dsn.gz` with the
flags in `run.json` → `adapter_meta.rule_args`.
