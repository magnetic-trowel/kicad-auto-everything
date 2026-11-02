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
| Other users' CPU | Jobs run at nice 19 and `SCHED_IDLE` (inherited by children; the daemon itself runs at nice 10, above its jobs and below normal work): they only get cycles no normal-priority task wants. Jobs are pinned to `threads - reserve_cpu` CPUs (`cpu_affinity=auto`), a hard cap that needs no cgroup `cpuset` (often not delegated to user slices). Admission also counts other users' measured load, so `reserve_cpu` threads stay free beyond it. A job's CPU use is read from its scope's `cpu.stat` (which includes children that already exited), and no job starts while the machine's ready-to-run threads (`procs_running`, smoothed) plus its `--cpus` exceed `threads - reserve_cpu`: past that point more work only slows every running job. |
| Memory leases (default, `mem_pool=lease`) | Each running job holds a grant, enforced as its scope's `memory.high`; it starts at its `--mem` (scaled by its owner's learned peak/`--mem`). A job that reaches its grant is not killed: the kernel holds it (it sleeps in the allocation) until the daemon grants more, `max(lease_step_gb, lease_step_frac × grant)` (1 GB, 25%) at a time, as soon as its non-reclaimable memory (anon + shmem + kernel, from `memory.stat`; page cache is reclaimed at the grant) comes within `lease_margin_mb` (512) of it. Grants come from what is free beyond the reserve (and `mem_budget_gb`, if set) minus every grant's unused part, by priority, then oldest job first. While any job waits at its grant, no new job starts. A grant more than `max(lease_release_gb, lease_release_frac × use)` (2 GB, 25%) above use for `lease_release_after_s` (2 min) is trimmed to use × 1.25 (at least use + 1 GB), so another job can have it. If a job has waited `lease_stall_s` (15 min) and nothing frees, one job of no higher priority is requeued with `--mem` raised to what it used: the one furthest past `mem_overrun` (1.5) × its declared `--mem` (a runaway, even the waiting job itself), else the newest other job; a job within its declaration that only waits for other users' memory keeps waiting. `kaeq status` shows each job's grant; `kaeqtop` shows the grants and who waits. The `--mem` overrun kill does not apply to leased jobs. Needs the cgroup memory controller (`kaeq doctor`); without it the queue falls back to `measured` below. |
| Other users' RAM | Without leases, admission is measured: a job starts only if `MemAvailable - reserve_mem_gb - what running jobs may still grow into >= its --mem`. A job younger than `warmup_s` (300 s) may grow into its declared `--mem`; after that, into its observed peak × `peak_margin` (1.25), so a later, heavier phase is still covered. With `mem_pool=measured` (the fallback) the queue does not add up worst cases at all: it measures how much its running jobs together have actually grown (their summed RSS once past warm-up, with starts and finishes excluded) and sets aside the largest rise within any hour of the last 24 h × `mem_rise_margin` (1.25), at least the largest single job's headroom, plus what jobs still warming up may need (pooled too: each one's peak drawn from its owner's finished jobs' spread of peak/`--mem`, mean + 2 std over all of them). A new job needs its `--mem` scaled by its owner's learned p95 peak/`--mem` (× 1.2, from 20 finished jobs). The history survives restarts (`~/.kaeq/memrise.<host>.json`); with under an hour of it, the model below is used. With `mem_pool=pooled`, jobs' growth is pooled statistically (`peak` sums every job's worst case): each finished job observed for at least half its run leaves a histogram of how its RSS spent its life relative to its peak, and once an owner has `mem_pool_min_jobs` (5) of them, its running jobs count as random variables. The queue sets aside the mean plus `mem_pool_z` (3) standard deviations of their combined growth, with jobs of one owner correlated as measured (mean Pearson r of concurrent jobs' last 15 min of RSS, shrunk towards the prior `mem_pool_rho`, 0.5) and different owners independent; never less than the largest single job's headroom, never more than the sum. Jobs still warming up, and owners without enough history, count in full. Jobs start one per tick (`starts_per_tick`, every 2 s): each new job shows its memory before more start. If free RAM drops below `emergency_frac` (75%) of the reserve, the newest job is killed and requeued (`preempted`); this backstop applies with leases too. |
| Reserves | `reserve_cpu` and `reserve_mem_gb` default to `reserve_frac` (20%) of threads and RAM. |
| Wrong estimates (without leases) | RSS (summed over the job's cgroup scope, else its session) polled every 2 s; > 1.5x declared (+1 GB) kills the job and requeues it once with `--mem` corrected from the observed peak. |
| Kernel OOM | `oom_score_adj=1000`: our jobs are the victims, not other users' processes. |
| Disk I/O | `ionice -c3`. |
| Scratch disk | Each job gets `$KAEQ_SCRATCH` (also `TMPDIR`) under `scratch_dir` (default `/var/tmp/$USER/kaeq-scratch`), deleted when the job ends, fails, is cancelled or preempted. Admission keeps measured scratch plus the unused part of declared `--disk` under `scratch_gb` (100). A job over 3x its `--disk` (+5 GB) is killed and requeued with a corrected estimate; over budget overall, the largest user is preempted. |
| Hard backstop | If `systemd-run --user` has the memory controller delegated (`kaeq doctor`), each job gets its own scope (with leases: `MemoryHigh` = its grant; without: `MemoryMax=2x`), inside `kaeq.slice` capped at `(1 - reserve_frac)` of RAM by `install-service`. Not required. |
| State on NFS | When `~/.kaeq` is on a network share, the SQLite database lives on local disk (`/var/tmp/$USER/kaeq/queue.db`), is backed up to `~/.kaeq/queue.db.bak` every 5 minutes, and is restored from there if the local copy is lost. Logs stay in `~/.kaeq/jobs/<id>/log`. |
| Fairness | Order: priority, then owners with the fewest running jobs, then age. A head-of-line job waiting > 10 min blocks backfill so big jobs don't starve, except by owners whose recent jobs end quickly (p90 of the last 50 ≤ `backfill_short_s`, 30 min): those still fill the held room, so a big job waits at most about that much longer once its room frees. |

Tune with `kaeq config --set reserve_frac=0.25 --set scratch_gb=150` (read every tick).
Per-job resources in bulk: `kaeq submit --jobs FILE` (JSONL: `cmd`, `name`, `cpus`, `mem`, `disk`, `timeout`, `prio`).
Change the priority of queued jobs: `kaeq prio N [ids] [--owner O] [--tag T]` (higher runs first).
Watch the queue live: `kaeqtop` (text only, fine over SSH): machine CPU/RAM as the scheduler sees them, what the next job waits for, and per owner priority, running jobs, CPU, RAM, memory set aside, progress, rate and ETA.
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

## One daemon, one machine

A POSIX lock on `~/.kaeq/daemon.lock` admits one daemon, even across machines that share an NFS
home: pids are not comparable across hosts or namespaces, but NFS locks are. The daemon pins its
host and database path in `~/.kaeq/config.json`. A client on another machine stops and points
at `KAEQ_SSH=<host>` instead of starting a second queue. Heartbeat (`daemon.<host>.json`), backup
(`queue.<host>.db.bak`) and exit-code files (`jobs/<id>/rc.<host>.<attempt>.<preempts>`) are per
host and per start, so nothing else writing into a shared home can end a job.

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
