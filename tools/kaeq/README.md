<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# kaeq: job queue for a shared machine

A single stdlib-Python file. Many Claude sessions submit shell commands; one daemon
starts them as room appears and tells the *submitting* session what broke.

## Setup (once, on the host)

```bash
tools/kaeq/install.sh          # symlinks ~/.local/bin/kaeq, prints `kaeq doctor`
kaeq install-service           # optional: systemd --user unit; then `loginctl enable-linger $USER`
```

The daemon auto-starts on the first `kaeq submit`, so the service is only for reboots.
Sessions on other machines: `export KAEQ_SSH=<host>`; every `kaeq ...` then runs over ssh
(paths are host paths, so the repo must be checked out on the host).
To stop permission prompts, allow one rule in each session's settings:
`"permissions": {"allow": ["Bash(kaeq:*)"]}`. Sessions load the usage text from
`~/.claude/skills/kaeq/` (installed by `install.sh`, so every repo gets it).

## How it shares the machine

| Concern | Mechanism (all unprivileged, Ubuntu 22.04) |
|---|---|
| Other users' CPU | Jobs run `SCHED_IDLE` (inherited by children): they only get cycles no normal-priority task wants, so we can fill the box without slowing anyone. Admission also keeps `reserve_cpu` (16) threads free. |
| Other users' RAM | Admit a job only if `MemAvailable - unused-part-of-running-jobs' declared mem - job.mem >= reserve_mem_gb` (40). If free RAM drops below half the reserve, the newest job is killed and requeued (`preempted`). |
| Wrong estimates | RSS polled every 2 s; > 1.5x declared (+1 GB) kills the job and requeues it once with `--mem` corrected from the observed peak. |
| Kernel OOM | `oom_score_adj=1000`: our jobs are the victims, not other users' processes. |
| Disk | `ionice -c3`. |
| Hard backstop | If `systemd-run --user` has the memory controller delegated (`kaeq doctor`), jobs also get `MemoryMax=2x`. Not required. |
| Fairness | Order: priority, then owners with the fewest running jobs, then age. A head-of-line job waiting > 10 min blocks backfill so big jobs don't starve. |

Tune with `kaeq config --set reserve_cpu=24 --set reserve_mem_gb=64` (read every tick).
Jobs get `KAEQ_CPUS`, `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `GOMAXPROCS` = `--cpus`, and the
submitter's `PATH`/`VIRTUAL_ENV`/`PYTHONPATH` (so the right venv is used).

## Many repos and branches

Each submit freezes the caller's tree (`git commit-tree` over HEAD + uncommitted + untracked,
kept alive by `refs/kaeq/<sha>`) and the daemon runs the job in a throwaway `git worktree` of the
submitter's repo, in the same subdirectory. Checkouts or edits after submit cannot change what
runs, and two branches of one repo can run side by side. The worktree is removed when the job
ends; the log stays. Git-ignored inputs are not in a snapshot: share them with `--link PATH`
(symlinked from the original repo). `--live` skips snapshots. Outside git, jobs run live.
The default owner is `repo@branch`; failure digests carry `repo@branch:sha`.
Old `refs/kaeq/*` can be deleted any time once no queued job needs them.

## Reporting loop

`kaeq wait` (run in the background) blocks until the owner has a problem event
(failed/timeout/oom/lost) or finished everything, prints one compact digest per failure
(command name, rc, runtime, peak/declared memory, earlier error lines, log tail, log path),
and exits 1/0 (2 = timeout, call again). Successes are never printed individually.
The session fixes the code and runs `kaeq retry [ids]`; it reuses the same command and cwd.
State lives in `~/.kaeq` (SQLite WAL, per-job `log`); the daemon can restart without
losing running jobs (they are re-adopted).

## Limits

- Jobs run as the daemon's user; submitters need access to the same `~/.kaeq` (same account or `KAEQ_HOME`).
- CPU weighting via cgroup `CPUWeight` would need a root-created systemd drop-in delegating `cpu`; `SCHED_IDLE` makes it unnecessary.
- RSS is summed per job session and over-counts shared pages (conservative).
