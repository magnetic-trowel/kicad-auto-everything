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
    prepare-failures/<harness>.json   when a harness could not build the task
    runs/<slug>.<method-id8>.a<attempt>/
      run.json                        method, task, harness commit, timing, CPU, router outcome
      output.kicad_pcb.gz             the method's output board
      adapter.log.gz, router-report.json, board.ses.gz, artifacts/ (router input, kept when a bug was seen)
      evals/<eval-id>.json            score (DRC) or physics, per evaluator; <eval-id>.drc.json.gz
      bugs.json                       bug records of this run
  experiments/<name>/
    experiment.json, boards.txt       methods, harness and kae commits, evaluators
    REPORT.md, results.csv            per method: cp1, completion, not closed, DRC errors, timeouts, CPU, physics
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
$K method list
$K exp create NAME --method "freerouting 2.5.0" --method "fr-fork master" [--boards @ids.txt] --description "..."
$K exp submit NAME [--limit 20]       # one kaeq job per board that lacks a run; re-submitting resumes
$K exp status NAME; $K exp report NAME; $K exp install-timer NAME   # report + index hourly
$K board BOARD_ID                     # every method's run of this board, with its scores
$K rerun ~/kae-baselines/boards/ID/runs/RUN [--submit]   # the code, binary and command; queue a reproduction
$K index                              # then e.g. sqlite3 ~/kae-baselines/index.sqlite 'select ...'
```

A method runs with the harness commit recorded in it, and an experiment's jobs run the
experiment's frozen copy of `kaeres.py`. Code changes after `exp create` therefore change
nothing in that experiment.

## Per board job

1. **Preflight.** KiCad's Python must import pcbnew. If it can't, the job exits 75 and kaeq retries it; this is an infrastructure failure, not a board result.
2. **Prepare.** `kaebench prepare-dir` builds the route task once per harness commit. Its task id is the hash of the board file sha256, task spec and KiCad version.
3. **Run.** Every missing method runs in one `kaebench run` (built-in adapters, interleaved) or one run per `--command` method. The human layout (the `reference` method) is scored once per board. The kaebench score becomes the run's DRC evaluation.
4. **Physics.** `physics_board.py` runs kae's routed module physics on each new run's scored board. The brief is built from the task input, so module ids pair with the human run.
5. **Archive.** Run folders are written atomically, with bug records. If another experiment's job wrote the same run meanwhile, the first one is kept.

Settings for every job:
- KiCad runs with `MaximumThreads=2`.
- Freerouting gets `-Xmx` sized to the board (`java_heap=auto-v1`) and `-XX:ActiveProcessorCount=2`.
- The harness tree has a 40 GB address-space cap.

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
| `drc` | DRC errors of one type (`drc_type`, `count`) beyond the human layout's on the same board |
| `over_time` | the attempt overran its timeout by more than 5 % |
| `physics_error` | kae's physics failed on a board or module |

Unrouted connections and timeouts are outcomes, not bugs: they are in `results.csv` and `REPORT.md`.

To reproduce a router bug without KiCad, run Freerouting on `artifacts/board.dsn.gz` with the
flags in `run.json` → `adapter_meta.rule_args`.
