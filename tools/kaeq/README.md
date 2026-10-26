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
| Other users' CPU | Jobs run `SCHED_IDLE` (inherited by children): they only get cycles no normal-priority task wants. Jobs are pinned to `threads - reserve_cpu` CPUs (`cpu_affinity=auto`), a hard cap that needs no cgroup `cpuset` (often not delegated to user slices). Admission also counts other users' measured load, so `reserve_cpu` threads stay free beyond it. |
| Other users' RAM | Admit a job only if `MemAvailable - unused part of running jobs' declared mem - job.mem >= reserve_mem_gb`. If free RAM drops below `emergency_frac` (75%) of the reserve, the newest job is killed and requeued (`preempted`). |
| Reserves | `reserve_cpu` and `reserve_mem_gb` default to `reserve_frac` (20%) of threads and RAM. |
| Wrong estimates | RSS (summed over the job's cgroup scope, else its session) polled every 2 s; > 1.5x declared (+1 GB) kills the job and requeues it once with `--mem` corrected from the observed peak. |
| Kernel OOM | `oom_score_adj=1000`: our jobs are the victims, not other users' processes. |
| Disk I/O | `ionice -c3`. |
| Scratch disk | Each job gets `$KAEQ_SCRATCH` (also `TMPDIR`) under `scratch_dir` (default `/var/tmp/$USER/kaeq-scratch`), deleted when the job ends, fails, is cancelled or preempted. Admission keeps measured scratch plus the unused part of declared `--disk` under `scratch_gb` (100). A job over 3x its `--disk` (+5 GB) is killed and requeued with a corrected estimate; over budget overall, the largest user is preempted. |
| Hard backstop | If `systemd-run --user` has the memory controller delegated (`kaeq doctor`), each job gets its own scope with `MemoryMax=2x`, inside `kaeq.slice` capped at `(1 - reserve_frac)` of RAM by `install-service`. Not required. |
| State on NFS | When `~/.kaeq` is on a network share, the SQLite database lives on local disk (`/var/tmp/$USER/kaeq/queue.db`), is backed up to `~/.kaeq/queue.db.bak` every 5 minutes, and is restored from there if the local copy is lost. Logs stay in `~/.kaeq/jobs/<id>/log`. |
| Fairness | Order: priority, then owners with the fewest running jobs, then age. A head-of-line job waiting > 10 min blocks backfill so big jobs don't starve. |

Tune with `kaeq config --set reserve_frac=0.25 --set scratch_gb=150` (read every tick).
Per-job resources in bulk: `kaeq submit --jobs FILE` (JSONL: `cmd`, `name`, `cpus`, `mem`, `disk`, `timeout`, `prio`).
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
