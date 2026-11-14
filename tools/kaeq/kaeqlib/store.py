# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where kaeq keeps its state: paths, config, the queue database, events, job directories, logs and traces."""
import json
import os
import re
import socket
import sqlite3
import sys
import time
from .host import meminfo


HOME = os.path.expanduser(os.environ.get("KAEQ_HOME", "~/.kaeq"))


USER = os.environ.get("USER") or str(os.getuid())


def _on_nfs(path):
    """True if path lives on a network filesystem (SQLite's WAL needs local shared memory)."""
    best, fs = "", ""
    try:
        with open("/proc/mounts") as f:
            for line in f:
                _, mnt, typ = line.split()[:3]
                if os.path.realpath(path).startswith(mnt.rstrip("/") + "/") and len(mnt) > len(best):
                    best, fs = mnt, typ
    except OSError:
        return False
    return fs.startswith(("nfs", "cifs", "smb", "fuse.sshfs", "lustre", "gpfs"))


CONF = os.path.join(HOME, "config.json")


def _pinned_db():
    try:
        with open(CONF) as f:
            return json.load(f).get("db")
    except (OSError, ValueError, AttributeError):
        return None


# The queue database lives on local disk when HOME is a network share (WAL over NFS is unsafe);
# it is then backed up into HOME every few minutes. The daemon pins its path in config.json, so
# every client uses the same file even where mounts look different (e.g. inside a sandbox).
AUTO_DB = (os.path.join("/var/tmp", USER, "kaeq", "queue.db")
           if _on_nfs(os.path.dirname(HOME.rstrip("/")) or "/") else os.path.join(HOME, "queue.db"))


DB = os.environ.get("KAEQ_DB") or _pinned_db() or AUTO_DB


# HOME may be shared by several machines (an NFS home): files the daemon writes there carry its host name
HOST = socket.gethostname().split(".")[0]


DB_BACKUP = os.path.join(HOME, f"queue.{HOST}.db.bak")


LOCK = os.path.join(HOME, "daemon.lock")


BEAT = os.path.join(HOME, f"daemon.{HOST}.json")


ACTIVE = ("queued", "running")


PROBLEM = ("failed", "timeout", "oom", "lost")


ENV_KEEP = ("PATH", "VIRTUAL_ENV", "PYTHONPATH", "LD_LIBRARY_PATH", "HOME", "LANG")


DEFAULTS = {
    "threads": 0,            # 0 = os.cpu_count()
    "reserve_frac": 0.2,     # share of CPU threads and RAM kept free for other users (when the two below are -1)
    "reserve_cpu": -1,       # threads kept free for other users (-1: reserve_frac of threads)
    "mem_total_gb": 0,       # 0 = MemTotal
    "reserve_mem_gb": -1,    # MemAvailable kept free for other users (-1: reserve_frac of MemTotal)
    "emergency_frac": 0.75,  # free memory below this share of the reserve preempts the newest job...
    "emergency_floor_gb": 28,  # ...or below this, if higher: above the host's earlyoom (SIGTERM at 10% of RAM)
    "warmup_s": 300,         # a new job keeps its declared --mem reserved this long; then its observed peak * peak_margin
    "peak_margin": 1.25,
    # memory for running jobs. "lease" (default where the cgroup memory controller is delegated): each job holds a
    # grant, enforced as its scope's memory.high; a job that reaches its grant is not killed but stalls in the kernel
    # until the queue grants more (lease_step_gb at a time, from what is free), and a grant far above what the job
    # uses is given back. Without a delegated memory controller "lease" falls back to "measured".
    # "peak" = the sum of every job's peak (as if all peak at once);
    # "pooled" = statistical: jobs rarely peak together, so set aside mean + mem_pool_z std of their combined
    # growth, from how jobs of the same owner spent their lifetime (memory histograms of finished jobs)
    "mem_pool": "lease",
    # "measured": set aside what the running jobs together have actually grown by: the largest rise of their
    # summed RSS within any mem_rise_window_s over the last mem_rise_history_s (new starts and finishes excluded),
    # x mem_rise_margin; at least the largest single job's headroom; plus warming-up jobs' needs. Falls back to
    # "pooled" until mem_rise_window_s of history exists
    "mem_rise_window_s": 3600,
    "mem_rise_history_s": 86400,
    "mem_rise_margin": 1.25,
    "mem_pool_z": 2.0,       # std deviations of headroom (2: ~2% of moments short if independent; the backstop
                             # preempts the newest job if free RAM really runs low)
    "mem_pool_margin": 1.1,  # pooled jobs may reach their observed peak x this (others: peak_margin)
    "mem_pool_rho": 0.5,     # prior correlation between jobs of one owner (0 = independent, 1 = in lockstep); the
                             # daemon measures it from concurrent jobs' RSS and uses the prior only as 2 pseudo-pairs
    "mem_pool_min_jobs": 3,  # finished jobs with a histogram an owner needs before its jobs are pooled
    # admission and warm-up on what jobs really use: once an owner has mem_learn_min_jobs finished jobs, a new job
    # of it needs its --mem x (p95 of the owner's peak/--mem) x mem_learn_margin, never more than --mem
    "mem_learn_min_jobs": 20,
    # what a RUNNING job is expected to grow into (expected_size): its owner's median peak/--mem once
    # forecast_min_jobs have finished; else, after forecast_trust_s, forecast_trust_margin x the most it has used;
    # else its --mem. (forecast_trust_s 1e9 and forecast_min_jobs 1e9: the declared --mem, as before.)
    "forecast_min_jobs": 3,
    "forecast_trust_s": 600,
    "forecast_trust_margin": 1.5,
    "mem_learn_margin": 1.1,
    # compress a frozen job's memory: let its scope swap (memory.swap.max) and reclaim it (memory.reclaim), into
    # zram swap only ("zram"), any swap ("any", e.g. for tests), or "off". Swap that is not zram is disk: slow
    "compress_frozen": "zram",
    # squeeze: when free memory beyond the reserve falls below the growth buffer (before any requeue, at half of
    # it), the biggest running timed job, preferring one not growing fast (at least squeeze_min_gb anon), has up to twice the
    # shortfall (at most half its memory) compressed into zram while it keeps running: the kernel's LRU takes its
    # oldest pages; it pays only when it touches them again. A job that pulls back (refaults) over a quarter of
    # what was squeezed out of it is hot and not squeezed again. One at a time, at most every squeeze_every_s.
    "squeeze": True,
    "squeeze_min_gb": 1.0,
    "squeeze_every_s": 5,
    # squeeze_credit: admission counts this share of timed jobs' memory (past warm-up, running, not hot)
    # as squeezable, x (1 - 1/zram_ratio) freed by compressing it, capped by zram room: the queue runs into
    # shortages on purpose and squeezes to cover them (requeues at half the buffer stay the backstop). 0 = off
    "squeeze_credit": 0.25,
    "zram_ratio": 1.4,
    "lease_step_gb": 1.0,    # lease: a grant grows by max(this, lease_step_frac of the grant) at a time
    "lease_step_frac": 0.25,
    "lease_margin_mb": 512,  # lease: a job within max(this, lease_margin_frac of its grant) of its grant gets more
    "lease_margin_frac": 0.15,
    "lease_backstop_frac": 0.1,  # memory.high sits max(1 GB, this x grant) above the grant: the kernel throttles only
                                 # a burst the daemon (every 2 s) has not seen yet; a job that must wait is frozen
    "lease_release_gb": 2.0, # lease: a grant more than max(this, lease_release_frac of use) above use for
    "lease_release_frac": 0.25,  # lease_release_after_s
    "lease_release_after_s": 120,  # is trimmed to use x 1.25 (at least use + 1 GB)
    "lease_press_pct": 10.0, # lease: a job whose own memory pressure (full avg10) is above this needs more, though its
                             # non-reclaimable use looks under its grant: memory.high counts its page cache too, and
                             # it is thrashing it (D state)
    "lease_freeze_mb": 256,  # lease: a job that gets no more is frozen only once within max(this, 2 ticks of its
                             # measured growth) of its grant; until then it runs on in the room it already has
    "lease_stall_s": 900,
    # job classes (kaeq submit --class): "timed" (default) for anything whose results or internal timeouts depend
    # on time: never frozen or throttled, its memory reserved (timed_hold_frac of its unused grant counts as taken),
    # at timed_nice, far above batch jobs (SCHED_IDLE), which only get the cycles timed jobs leave.
    # "batch" for throughput work with no time limits inside: elastic leases, may be frozen and overcommitted.
    # timed jobs are overcommitted too, but never paused: if memory runs short anyway, a job is requeued (it restarts
    # from scratch, its results unaffected). timed_hold_frac is the share of their unused grants set aside; with
    # timed_hold_auto it adapts every overcommit_every_s so that work lost to such requeues stays near
    # overcommit_loss_target of the timed work done over overcommit_window_s (up by 0.1 above it, down by 0.05
    # below half of it). A job requeued evict_protect_after times keeps its whole grant set aside.
    # health: the daemon watches for its own failure symptoms (each was found this way by hand once) and reports
    # them (log, kaeqtop, the job owner's `kaeq wait`, at most once an hour each): a job stalled on memory at a
    # limit kaeq set (full avg60 above health_mem_pct for health_after_s), frozen over health_frozen_s, running
    # without a readable cgroup, timed_wait held while no timed job runs, or no timed start for
    # health_timed_idle_s while timed jobs wait and CPUs are idle
    "health_mem_pct": 20.0,
    "health_after_s": 300,
    "health_frozen_s": 3600,
    "health_timed_idle_s": 1800,
    "default_class": "batch",  # class of a job submitted without --class: batch (packs tighter, may be paused)
    # expensive batch jobs are kept running (a frozen job holds its memory for nothing, and big ones most): a batch
    # job expected to reach keep_gb, or with keep_core_h of work in it, is never frozen for a grant and never
    # throttled, and gets memory before other batch jobs; when it is short, the newest batch job not kept is
    # frozen (and compressed) to make room, never requeued. keep_reserve_frac of its forecast growth is set aside
    # (0: none; 1 acts as a reservation and cost 20-30% of throughput in trace replays, tools/kaeq/sim_freeze.py).
    # A thawed job is not frozen again for max(thaw_min_run_s, thaw_min_frac x the time it was frozen) unless free
    # memory is below half the buffer: in replays the largest gain, at no throughput cost (600 s beat 300 s).
    "keep_gb": 8.0,
    "keep_core_h": 1.0,
    "keep_reserve_frac": 0.0,
    "thaw_min_run_s": 600,
    "thaw_min_frac": 0.25,
    # heavy_boost: jobs that hold the most memory get one step more CPU, so they wait less under contention and
    # free their memory sooner. Without privileges a priority can only be lowered, so a job starts one step up
    # when expected to be memory-heavy (its learned size, or --mem without history, at least keep_gb); the rest
    # start one step down, and a boosted job moves down after lease_warm_s if its learned size says it is light
    # (timed: timed_nice + 1; batch: SCHED_IDLE). Heavy timed > timed > heavy batch > batch.
    "heavy_boost": True,
    "timed_hold_frac": 1.0,  # (used only with timed_forecast off)
    "timed_hold_auto": False,
    # timed_forecast: set aside for timed jobs what they are forecast to grow into, not their unused grants: each
    # job may reach its expected size (need_mb, or the most it has used), and spends its life at each fraction of
    # that as its owner's finished jobs did (their memory histograms); jobs of one owner correlated as measured.
    # Mean + timed_z std of that growth, pooled over all timed jobs (pooled_headroom). timed_z adapts to the work
    # lost to requeues (overcommit_loss_target): +0.5 above it, -0.25 below half of it, within [0, 6].
    "timed_forecast": True,
    "timed_z": 2.0,
    "overcommit_loss_target": 0.02,
    "overcommit_window_s": 21600,
    "overcommit_every_s": 600,
    "evict_every_s": 10,
    "evict_protect_after": 2,
    "timed_nice": 10,        # timed jobs' nice: above SCHED_IDLE batch jobs by far, still below other users' work
    # CPU for timed jobs, measured, not reserved: a timed job starts only while the timed jobs' mean use plus their
    # bursts pooled as independent (sqrt of the summed squares of max-minus-mean over cpu_window_s), plus its own
    # (learned per owner from finished jobs, else --cpus), fit beside other users' load, and while timed jobs spent
    # under timed_wait_start of their time with all their runnable threads waiting for a CPU (cpu.pressure full).
    # Above timed_wait_freeze,
    # the newest batch job is frozen (one per cpu_freeze_every_s) until it falls below timed_wait_thaw.
    "cpu_window_s": 600,
    "timed_wait_start": 0.02,
    "timed_wait_freeze": 0.05,
    "timed_wait_thaw": 0.01,
    "cpu_freeze_every_s": 10,
    # a batch job (not kept running) starved of CPU (all its runnable threads waiting for a CPU, cpu.pressure
    # "full", at least starve_full of the time for starve_s) holds its memory while hardly progressing: it is frozen
    # and compressed into zram, which costs it almost nothing, and thawed once the run queue has room for its CPUs
    "starve_full": 0.5,
    # fillers: light batch jobs run at SCHED_IDLE (heavy_boost), so they only take CPU nothing else wants. One starts
    # whenever CPUs are spare right now (all threads ready to run below the CPUs jobs may use), memory permitting,
    # while their declared CPUs stay within filler_frac of those CPUs (a loose limit); starved ones are frozen and
    # compressed (starve_*); a waiting filler never holds room (no starvation hold). The run queue that gates
    # normal-priority starts leaves out idle-priority threads
    "filler_frac": 2.0,
    "starve_s": 180,
    "timed_preempt_s": 30,   # a timed job that needs memory nobody can give requeues the newest batch job, at most this often
    "lease_hold_frac": 0.1,  # lease: share (batch jobs; frozen and compressed cheaply when short) of a job's unused grant counted as taken (1: grants are reservations;
                             # 0: only real use counts, and jobs that collide take turns, frozen)
    "lease_warm_s": 120,     # lease: a job this young counts its whole unused grant (it is still growing into it)
    "lease_buffer_gb": 4.0,  # lease: free memory kept for growth between ticks: at least this, and
    "lease_buffer_ticks": 3.0,  # this many times the fleet's largest growth within one tick over the last 10 minutes    # lease: a job stalled this long for memory that nothing frees requeues the newest other job
    "mem_budget_gb": 0,      # cap on what all jobs together may use and hold (0: none beyond the reserve)
    "starts_per_tick": 1,
    # CPU admission of batch jobs: not the run queue of the moment but its runq_q quantile over the last
    # runq_window_s (a dip must last), plus jobs started in the last 60 s that have not ramped up yet. runq_q adapts
    # every runq_adapt_s: more than runq_over_target of the samples oversubscribed (more runnable threads than CPUs
    # jobs may use) -> +0.05; more than runq_idle_target of them with runq_idle_cpus free while jobs wait -> -0.05;
    # within [0.5, 0.95]
    "runq_window_s": 120,
    "runq_q": 0.8,
    "runq_adapt_s": 300,
    "runq_over_target": 0.10,
    "runq_idle_target": 0.20,
    "runq_idle_cpus": 4,    # ramp: at most this many job starts every 2 s, so new jobs show their memory before more start
    "cpu_affinity": "auto",  # auto: pin jobs to the first threads-reserve_cpu CPUs (a hard cap); off; or e.g. "0-101"
    "max_running": 256,
    "mem_overrun": 1.5,      # kill a job whose RSS exceeds declared * this (+1 GB)
    "starve_after_s": 600,   # a head-of-line job waiting this long blocks backfill, except short jobs:
    "backfill_short_s": 1800,  # an owner whose recent jobs (p90) end within this may still backfill; 0 = never
    "cgroup": "auto",        # auto|on|off: wrap jobs in `systemd-run --user --scope`
    "slice": "kaeq.slice",   # systemd user slice for job scopes (install-service caps its memory); "" = none
    "scratch_dir": "",       # per-job scratch dirs ($KAEQ_SCRATCH), deleted when the job ends; "" = /var/tmp/$USER/kaeq-scratch
    "scratch_gb": 100,       # scratch disk budget over all jobs
    "disk_overrun": 3.0,     # kill a job whose scratch exceeds declared * this (+5 GB)
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
 id INTEGER PRIMARY KEY, owner TEXT, name TEXT, tag TEXT, cmd TEXT, cwd TEXT, env TEXT,
 cpus REAL, mem_mb INTEGER, timeout_s INTEGER, prio INTEGER DEFAULT 0, state TEXT,
 attempt INTEGER DEFAULT 1, retries_left INTEGER DEFAULT 0, preempts INTEGER DEFAULT 0,
 submitted REAL, started REAL, finished REAL, not_before REAL DEFAULT 0, deadline REAL,
 pid INTEGER, rc INTEGER, peak_mb INTEGER DEFAULT 0, note TEXT,
 root TEXT, branch TEXT, sha TEXT, rel TEXT, links TEXT, disk_mb INTEGER DEFAULT 1024, disk_peak_mb INTEGER DEFAULT 0,
 mem_hist TEXT, grant_mb INTEGER DEFAULT 0,
 frozen_s REAL DEFAULT 0, frozen_since REAL DEFAULT 0, freezes INTEGER DEFAULT 0, cpu_s REAL DEFAULT 0,
 lost_run_s REAL DEFAULT 0, lost_cpu_s REAL DEFAULT 0, qos TEXT DEFAULT 'timed',
 cpu_wait_s REAL DEFAULT 0, cpu_stall_s REAL DEFAULT 0, cpu_peak REAL DEFAULT 0, squeezed_mb REAL DEFAULT 0);
CREATE INDEX IF NOT EXISTS jobs_state ON jobs(state);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY, ts REAL, owner TEXT, job INTEGER, kind TEXT, msg TEXT,
 delivered INTEGER DEFAULT 0);
"""


def pinned_host():
    try:
        with open(CONF) as f:
            return json.load(f).get("host")
    except (OSError, ValueError, AttributeError):
        return None


def db(restore=False):
    """The queue database. Only the daemon (holding the lock) may restore it from the backup;
    a client on another machine, or one that cannot see it, stops instead of starting a second,
    diverging queue."""
    os.makedirs(HOME, exist_ok=True)
    host = pinned_host()
    if not restore and host and host != HOST:
        sys.exit(f"kaeq: the queue's daemon runs on {host}, this is {HOST} (they share {HOME}). "
                 f"Run kaeq there: export KAEQ_SSH={host}")
    if not os.path.exists(DB):
        if os.path.exists(DB_BACKUP) and not restore:
            sys.exit(f"kaeq: the queue database {DB} is not visible here, but {DB_BACKUP} exists: this process sees a "
                     "different filesystem than the daemon (a sandbox or container?). Run kaeq where the daemon runs.")
        os.makedirs(os.path.dirname(DB), exist_ok=True)
        if os.path.exists(DB_BACKUP):  # local disk wiped: start from the last backup
            import shutil
            shutil.copy2(DB_BACKUP, DB)
            dlog(f"restored {DB} from {DB_BACKUP}")
    c = sqlite3.connect(DB, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    have = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
    for col in ("root", "branch", "sha", "rel", "links", "mem_hist"):  # upgrade an older database
        if col not in have:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")
    if "qos" not in have:
        c.execute("ALTER TABLE jobs ADD COLUMN qos TEXT DEFAULT 'timed'")
    for col, dflt in (("disk_mb", 1024), ("disk_peak_mb", 0), ("grant_mb", 0), ("freezes", 0)):  # upgrade an older database
        if col not in have:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {col} INTEGER DEFAULT {dflt}")
    for col in ("frozen_s", "frozen_since", "cpu_s", "lost_run_s", "lost_cpu_s", "cpu_wait_s", "cpu_stall_s", "cpu_peak", "squeezed_mb"):
        if col not in have:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {col} REAL DEFAULT 0")
    return c


def backup_db(c):
    """Copy the live database into HOME (atomically), so a lost local disk loses at most minutes."""
    tmp = DB_BACKUP + ".tmp"
    dst = sqlite3.connect(tmp)
    try:
        c.backup(dst)
    finally:
        dst.close()
    os.replace(tmp, DB_BACKUP)


def config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONF) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    cfg["threads"] = cfg["threads"] or os.cpu_count() or 1
    if cfg["reserve_cpu"] < 0:
        cfg["reserve_cpu"] = int(round(cfg["threads"] * cfg["reserve_frac"]))
    if cfg["reserve_mem_gb"] < 0:
        total = cfg["mem_total_gb"] or meminfo()["MemTotal"] / 1024
        cfg["reserve_mem_gb"] = round(total * cfg["reserve_frac"], 1)
    cfg["scratch_dir"] = cfg["scratch_dir"] or os.path.join("/var/tmp", USER, "kaeq-scratch")
    return cfg


RISE_HIST = os.path.join(HOME, f"memrise.{HOST}.json")


OVERCOMMIT = os.path.join(HOME, f"overcommit.{HOST}.json")


def load_overcommit():
    try:
        with open(OVERCOMMIT) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_rise_hist():
    try:
        with open(RISE_HIST) as f:
            return [tuple(x) for x in json.load(f)]
    except (OSError, ValueError, TypeError):
        return []


TRACES = os.path.join(os.path.dirname(DB), "traces")


def trace_path(j):
    return os.path.join(TRACES, f"{j['id']}.{j['attempt']}.{j['preempts']}.tsv")


def write_trace(j, now, **v):
    """Append one 10-s sample to a job attempt's trace (local disk, gzipped when the attempt ends): t, rss and
    non-reclaimable use (MB), cores used, share of time some / all threads waited for a CPU, frozen, grant (MB).
    The first line is a JSON header with what the queue knew at the start."""
    path = trace_path(j)
    try:
        new = not os.path.exists(path)
        if new:
            os.makedirs(TRACES, exist_ok=True)
        with open(path, "a") as f:
            if new:
                f.write(json.dumps(dict(id=j["id"], owner=j["owner"], name=j["name"], cpus=j["cpus"], mem_mb=j["mem_mb"],
                                        qos=j["qos"], started=j["started"], timeout_s=j["timeout_s"],
                                        prio=j["prio"])) + "\n")
            f.write(f"{now:.0f}\t{v['rss']:.0f}\t{v['use']:.0f}\t{v['cores']:.2f}\t{v['wait']:.3f}\t{v['stall']:.3f}\t"
                    f"{int(v['frozen'])}\t{v['grant']:.0f}\n")
    except OSError:
        pass


def close_trace(j, state):
    """An attempt ended: append how (`# end <state> <t>`) and gzip its trace."""
    path = trace_path(j)
    if not os.path.exists(path):
        return
    try:
        import gzip
        import shutil as sh
        with open(path, "a") as f:
            f.write(f"# end {state} {time.time():.0f}\n")
        with open(path, "rb") as src, gzip.open(path + ".gz", "wb") as dst:
            sh.copyfileobj(src, dst)
        os.unlink(path)
    except OSError:
        pass


DEPLOYED = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "DEPLOYED.json")  # beside kaeq.py


def deployed():
    """What install.sh recorded about this copy of kaeq (commit, branch, in main or not), or {}."""
    try:
        with open(DEPLOYED) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def dlog(msg):
    """One line per scheduling decision in the daemon's log (journal under systemd)."""
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{os.getpid()}] {msg}", flush=True)


def event(c, job, kind, msg):
    c.execute("INSERT INTO events(ts,owner,job,kind,msg) VALUES(?,?,?,?,?)", (time.time(), job["owner"], job["id"], kind, msg))


def jobdir(jid):
    return os.path.join(HOME, "jobs", str(jid))


def rc_path(j):
    """Exit-code file of one start of a job: named per host and start (a requeue bumps attempt or
    preempts), so nothing else writing into a shared HOME can end a job here."""
    return os.path.join(jobdir(j["id"]), f"rc.{HOST}.{j['attempt']}.{j['preempts']}")


def scratchdir(cfg, jid):
    return os.path.join(cfg["scratch_dir"], str(jid))


def drop_scratch(cfg, jid):
    import shutil
    shutil.rmtree(scratchdir(cfg, jid), ignore_errors=True)


def du_mb(path):
    """Disk usage of a tree in MB (allocated blocks, hard links once); 0 if missing."""
    total, seen, stack = 0, set(), [path]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                elif (st.st_dev, st.st_ino) not in seen:
                    seen.add((st.st_dev, st.st_ino))
                    total += st.st_blocks * 512
    return total / (1 << 20)


ERR_RE = re.compile(r"Traceback|Error|error:|FAILED|Exception|assert|Killed|panic|fatal|No such file", re.I)


def digest(jid, tail=12, errs=6):
    try:
        with open(os.path.join(jobdir(jid), "log"), "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 65536))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return ["  (no log)"]
    lines = [l.rstrip()[:200] for l in lines if l.strip()]
    marks = [i for i, l in enumerate(lines) if l.startswith(("=== kaeq retry", "=== kaeq start"))]
    if marks:
        lines = lines[marks[-1] + 1:]  # only the latest attempt
    tl = lines[-tail:]
    seen, el = set(), []
    for l in reversed(lines[:-tail] if len(lines) > tail else []):
        if ERR_RE.search(l) and l not in seen:
            seen.add(l)
            el.append(l)
        if len(el) >= errs:
            break
    out = [f"  earlier-err: {l}" for l in reversed(el)]
    out += [f"  | {l}" for l in tl]
    return out
