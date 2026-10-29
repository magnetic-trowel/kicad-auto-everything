#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kaeq: a resource-aware job queue for a shared machine, built for LLM sessions.

One daemon (`kaeq daemon`, auto-started by `kaeq submit`) owns a SQLite queue in
~/.kaeq. Many sessions submit shell commands with a CPU/memory estimate; the daemon
starts them as the machine has room *beyond a reserve left for other users*, runs
them at SCHED_IDLE priority (they only get CPU nobody else wants) with the highest
OOM score (the kernel kills them first), and reports failures compactly to the
submitting session through `kaeq wait` / `kaeq inbox`.  Stdlib only, Python >= 3.10.
"""
import argparse
import fcntl
import json
import os
import re
import shlex
import signal
import socket
import sqlite3
import subprocess
import sys
import time

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
GB = 1 << 30
TICK = 2.0
ACTIVE = ("queued", "running")
PROBLEM = ("failed", "timeout", "oom", "lost")
ENV_KEEP = ("PATH", "VIRTUAL_ENV", "PYTHONPATH", "LD_LIBRARY_PATH", "HOME", "LANG")

DEFAULTS = {
    "threads": 0,            # 0 = os.cpu_count()
    "reserve_frac": 0.2,     # share of CPU threads and RAM kept free for other users (when the two below are -1)
    "reserve_cpu": -1,       # threads kept free for other users (-1: reserve_frac of threads)
    "mem_total_gb": 0,       # 0 = MemTotal
    "reserve_mem_gb": -1,    # MemAvailable kept free for other users (-1: reserve_frac of MemTotal)
    "emergency_frac": 0.75,  # free memory below this share of the reserve preempts the newest job
    "warmup_s": 300,         # a new job keeps its declared --mem reserved this long; then its observed peak * peak_margin
    "peak_margin": 1.25,
    # memory set aside for running jobs' peaks: "peak" = the sum of every job's peak (as if all peak at once);
    # "pooled" = statistical: jobs rarely peak together, so set aside mean + mem_pool_z std of their combined
    # growth, from how jobs of the same owner spent their lifetime (memory histograms of finished jobs)
    "mem_pool": "pooled",
    "mem_pool_z": 3.0,       # std deviations of headroom (3: ~0.1% of moments short if independent)
    "mem_pool_rho": 0.5,     # assumed correlation between jobs of one owner (0 = independent, 1 = in lockstep)
    "mem_pool_min_jobs": 5,  # finished jobs with a histogram an owner needs before its jobs are pooled
    "starts_per_tick": 1,    # ramp: at most this many job starts every 2 s, so new jobs show their memory before more start
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
 mem_hist TEXT);
CREATE INDEX IF NOT EXISTS jobs_state ON jobs(state);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY, ts REAL, owner TEXT, job INTEGER, kind TEXT, msg TEXT,
 delivered INTEGER DEFAULT 0);
"""


# ---------------------------------------------------------------- helpers
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
    for col, dflt in (("disk_mb", 1024), ("disk_peak_mb", 0)):  # upgrade a pre-scratch database
        if col not in have:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {col} INTEGER DEFAULT {dflt}")
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


def parse_cpus(spec):
    out = set()
    for part in str(spec).split(","):
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        elif part.strip():
            out.add(int(part))
    return out


def job_cpus(cfg):
    """CPUs jobs are pinned to (inherited by every child): a hard cap that leaves reserve_cpu free. None = no pinning."""
    spec = cfg["cpu_affinity"]
    if spec == "off" or not hasattr(os, "sched_getaffinity"):
        return None
    if spec == "auto":
        mine = sorted(os.sched_getaffinity(0))
        n = max(1, min(len(mine), cfg["threads"]) - cfg["reserve_cpu"])
        return set(mine[:n])
    return parse_cpus(spec)


def parse_size(s):
    m = re.fullmatch(r"([\d.]+)\s*([kmgt]?)b?", str(s).strip().lower())
    if not m:
        raise ValueError(f"bad size {s!r} (use e.g. 512M, 8G)")
    return float(m.group(1)) * {"": 1 << 20, "k": 1 << 10, "m": 1 << 20, "g": GB, "t": GB << 10}[m.group(2)]


def parse_dur(s):
    m = re.fullmatch(r"([\d.]+)\s*([smhd]?)", str(s).strip().lower())
    if not m:
        raise ValueError(f"bad duration {s!r} (use e.g. 90s, 15m, 2h)")
    return int(float(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)])


def fgb(mb):
    return f"{mb / 1024:.1f}G"


def fdur(s):
    s = int(s)
    return f"{s}s" if s < 120 else f"{s // 60}m" if s < 7200 else f"{s // 3600}h"


def git(root, *args, env=None):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, env=env)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "git failed")
    return r.stdout.strip()


def git_snapshot(cwd):
    """Freeze the working tree (tracked + untracked, not ignored) as a commit; None outside a git repo."""
    try:
        root = git(cwd, "rev-parse", "--show-toplevel")
        head = git(root, "rev-parse", "HEAD")
        branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
        idx = os.path.join(git(root, "rev-parse", "--absolute-git-dir"), f"kaeq-index-{os.getpid()}")
        env = dict(os.environ, GIT_INDEX_FILE=idx)
        try:
            git(root, "read-tree", "HEAD", env=env)
            git(root, "add", "-A", env=env)
            tree = git(root, "write-tree", env=env)
        finally:
            if os.path.exists(idx):
                os.unlink(idx)
        sha = git(root, "commit-tree", tree, "-p", head, "-m", "kaeq snapshot")
        git(root, "update-ref", f"refs/kaeq/{sha}", sha)  # keeps it from being gc'd
        return dict(root=root, branch=branch, sha=sha, rel=os.path.relpath(os.path.realpath(cwd), os.path.realpath(root)))
    except (RuntimeError, OSError):
        return None


def drop_worktree(j):
    if j["sha"] and j["root"]:
        src = os.path.join(jobdir(j["id"]), "src")
        subprocess.run(["git", "-C", j["root"], "worktree", "remove", "--force", src], capture_output=True)
        subprocess.run(["git", "-C", j["root"], "worktree", "prune"], capture_output=True)


def ref(j):
    return f"{os.path.basename(j['root'])}@{j['branch']}:{j['sha'][:7]}" if j["sha"] else "live"


def default_owner():
    if os.environ.get("KAEQ_OWNER"):
        return os.environ["KAEQ_OWNER"]
    try:
        root = git(os.getcwd(), "rev-parse", "--show-toplevel")
        return f"{os.path.basename(root)}@{git(root, 'rev-parse', '--abbrev-ref', 'HEAD')}"
    except (RuntimeError, OSError):
        return f"{os.environ.get('USER', 'u')}-{os.path.basename(os.getcwd())}"


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def meminfo():
    d = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            d[k] = int(v.split()[0]) // 1024  # MB
    return d


def cpu_ticks():
    """(busy, total) jiffies over all CPUs."""
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v[:8]) - idle, sum(v[:8])


def proc_by_session():
    """({sid: (rss_mb, cpu_ticks)}, {pid: (rss_mb, cpu_ticks)}) over every process we can read."""
    out, per_pid = {}, {}
    page_mb = os.sysconf("SC_PAGE_SIZE") / (1 << 20)
    for ent in os.listdir("/proc"):
        if not ent.isdigit():
            continue
        try:
            with open(f"/proc/{ent}/stat") as f:
                s = f.read()
            fld = s[s.rindex(")") + 2:].split()
            sid, ut, st, rss = int(fld[3]), int(fld[11]), int(fld[12]), int(fld[21])
        except (OSError, ValueError, IndexError):
            continue
        per_pid[int(ent)] = (rss * page_mb, ut + st)
        r, t = out.get(sid, (0.0, 0))
        out[sid] = (r + rss * page_mb, t + ut + st)
    return out, per_pid


def job_cgroup(pid):
    """The job's own systemd scope (cgroup v2 path), or None when it runs without one."""
    try:
        with open(f"/proc/{pid}/cgroup") as f:
            for line in f:
                if line.startswith("0::") and line.rstrip().endswith(".scope") and "/run-" in line:
                    return "/sys/fs/cgroup" + line[3:].strip()
    except OSError:
        pass
    return None


def kill_tree(pid, cg=None, sig=signal.SIGKILL):
    """Kill a job: its process group, and every process in its scope (children that started
    their own session would otherwise outlive the job, e.g. in a deleted scratch dir).
    cg: the scope recorded while the job ran (never looked up from a pid that may be reused)."""
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError, TypeError):
        pass
    if not cg:
        return
    if sig == signal.SIGKILL and os.path.exists(os.path.join(cg, "cgroup.kill")):
        try:
            with open(os.path.join(cg, "cgroup.kill"), "w") as f:
                f.write("1")
            return
        except OSError:
            pass
    try:
        with open(os.path.join(cg, "cgroup.procs")) as f:
            for q in f.read().split():
                try:
                    os.kill(int(q), sig)
                except (ProcessLookupError, PermissionError, ValueError):
                    pass
    except OSError:
        pass


MEM_BINS = 20


def mem_hist(samples, peak):
    """How a job spent its life: counts of RSS samples in MEM_BINS equal slices of its peak."""
    h = [0] * MEM_BINS
    for r in samples:
        h[min(MEM_BINS - 1, int(r / peak * MEM_BINS))] += 1
    return h


def pooled_headroom(jobs, z, rho):
    """Memory to set aside for running jobs' growth when they rarely peak together.
    jobs: [(owner, expect_mb, rss_mb, profile or None)]: expect = the most it may reach (its peak x
    margin, or its declared --mem while it warms up); profile = share of lifetime its owner's jobs
    spend at each slice of their peak (MEM_BINS weights). A job without a profile counts its whole
    headroom (expect - rss). A profiled job's RSS at a random moment is expect x (slice upper edge),
    so its growth is max(0, that - rss): mean + z std over all of them, jobs of one owner correlated
    by rho, owners independent; never less than the largest single headroom, never more than the sum.
    Returns (set aside, sum of headrooms)."""
    full = worst = 0.0
    biggest = 0.0
    mu = 0.0
    var = 0.0
    by_owner = {}
    for owner, expect, rss, prof in jobs:
        room = max(0.0, expect - rss)
        worst += room
        if prof is None:
            full += room
            continue
        biggest = max(biggest, room)
        g = [max(0.0, expect * (k + 1) / MEM_BINS - rss) for k in range(MEM_BINS)]  # growth if at slice k
        m = sum(w * x for w, x in zip(prof, g))
        m2 = sum(w * x * x for w, x in zip(prof, g))
        sd = max(0.0, m2 - m * m) ** 0.5
        mu += m
        o = by_owner.setdefault(owner, [0.0, 0.0])
        o[0] += sd
        o[1] += sd * sd
    for lin, sq in by_owner.values():
        var += (1 - rho) * sq + rho * lin * lin
    pooled = max(biggest, mu + z * var ** 0.5)
    return min(worst, full + pooled), worst


def job_usage(j, sessions, per_pid, cgroups):
    """(rss_mb, cpu_ticks) of a job: every process in its scope (children that start their own
    session stay in it), else every process in its session."""
    cg = cgroups.get(j["id"]) or job_cgroup(j["pid"])
    if cg:
        cgroups[j["id"]] = cg
        try:
            with open(os.path.join(cg, "cgroup.procs")) as f:
                pids = [int(x) for x in f.read().split()]
            rss = ticks = 0
            for q in pids:
                r, t = per_pid.get(q, (0.0, 0))
                rss += r
                ticks += t
            return rss, ticks
        except (OSError, ValueError):
            pass
    return sessions.get(j["pid"], (0.0, 0))


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


# ---------------------------------------------------------------- digest of a finished job
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


# ---------------------------------------------------------------- daemon
class Daemon:
    def __init__(self):
        self.c = db()
        self.popen = {}          # id -> Popen (to reap zombies)
        self.others_ema = 0.0
        self.prev = cpu_ticks()
        self.prev_ours = {}
        self.sys = {}
        self.cg = None
        self.cgroups = {}        # job id -> its scope's cgroup dir
        self.disk = {}           # job id -> scratch MB (refreshed by a background thread)
        self.disk_total = 0.0
        self.disk_ts = 0.0
        self.last_backup = 0.0
        self.trace = {}          # job id -> RSS samples (every ~10 s) for its memory histogram
        self.profiles, self.profiles_ts = {}, 0.0
        import threading
        threading.Thread(target=self.disk_loop, daemon=True).start()

    def disk_loop(self):
        """Measure every job's scratch dir (and strays) every ~20 s, off the scheduling thread."""
        while True:
            try:
                root = config()["scratch_dir"]
                sizes = {}
                if os.path.isdir(root):
                    for e in os.scandir(root):
                        sizes[e.name] = du_mb(e.path)
                self.disk = {int(k): v for k, v in sizes.items() if k.isdigit()}
                self.disk_total = sum(sizes.values())
                self.disk_ts = time.time()
            except Exception:  # noqa: BLE001 - never let the monitor die
                pass
            time.sleep(20)

    # -- capability probing
    def use_cgroup(self, cfg):
        if cfg["cgroup"] == "off":
            return False
        if self.cg is None:
            self.cg = False
            if shutil_which("systemd-run"):
                try:
                    r = subprocess.run(
                        ["systemd-run", "--user", "--scope", "--quiet", "-p", "MemoryMax=1G", "sh", "-c",
                         "cat /sys/fs/cgroup$(grep '^0::' /proc/self/cgroup | cut -d: -f3)/memory.max"],
                        capture_output=True, text=True, timeout=15)
                    self.cg = r.returncode == 0 and r.stdout.strip() == str(GB)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        return self.cg if cfg["cgroup"] == "auto" else True

    # -- one scheduling pass
    def tick(self):
        cfg = config()
        c = self.c
        sessions, per_pid = proc_by_session()
        now = time.time()
        running = c.execute("SELECT * FROM jobs WHERE state='running'").fetchall()
        ours_ticks, ours_rss, unrealized = 0, 0.0, 0.0
        usage = {j["id"]: job_usage(j, sessions, per_pid, self.cgroups) for j in running}
        for j in running:
            rss, ticks = usage[j["id"]]
            ours_rss += rss
            ours_ticks += max(0, ticks - self.prev_ours.get(j["id"], ticks))
            self.prev_ours[j["id"]] = ticks
            tr = self.trace.setdefault(j["id"], [0.0, [], now - (j["started"] or now) < 30])  # [last, samples, whole life]
            if now - tr[0] >= 10:
                tr[0] = now
                tr[1].append(rss)
            self.check(j, rss, now, cfg, self.disk.get(j["id"], 0.0))
        # system sample
        busy, total = cpu_ticks()
        dt = max(1, total - self.prev[1])
        sys_threads = (busy - self.prev[0]) / dt * cfg["threads"]
        ours_threads = ours_ticks / dt * cfg["threads"]
        self.others_ema = 0.7 * self.others_ema + 0.3 * max(0.0, sys_threads - ours_threads)
        self.prev = (busy, total)
        mi = meminfo()
        running = c.execute("SELECT * FROM jobs WHERE state='running'").fetchall()
        for jid in set(self.trace) - {j["id"] for j in running}:
            del self.trace[jid]
        profiles = self.owner_profiles(cfg, now, running)
        grow = []
        for j in running:
            # what a job may still grow into: its declared --mem while it warms up, then its observed peak
            # with a margin (a later phase may need more than the first); free memory is measured, not declared
            rss = usage.get(j["id"], (0.0, 0))[0]
            peak = max(j["peak_mb"] or 0, rss)
            warm = now - (j["started"] or now) < cfg["warmup_s"]
            expect = j["mem_mb"] if warm else peak * cfg["peak_margin"]
            grow.append((j["owner"], expect, rss, None if warm else profiles.get(j["owner"])))
        unrealized, unrealized_peak = pooled_headroom(grow, cfg["mem_pool_z"], cfg["mem_pool_rho"])
        if cfg["mem_pool"] != "pooled":
            unrealized = unrealized_peak
        disk_unrealized = sum(max(0.0, j["disk_mb"] - self.disk.get(j["id"], 0.0)) for j in running)
        declared = max(1.0, sum(j["cpus"] for j in running))
        # declared CPUs while a job warms up, then what the fleet really uses (floor: 25% of declared)
        cpu_commit = sum(j["cpus"] if now - j["started"] < 20 else max(j["cpus"] * 0.25, ours_threads * j["cpus"] / declared)
                         for j in running)
        avail = mi["MemAvailable"]
        reserve = cfg["reserve_mem_gb"] * 1024
        cap = cfg["scratch_gb"] * 1024
        pinned = job_cpus(cfg)
        self.sys = dict(threads=cfg["threads"], others=self.others_ema, ours_cpu=ours_threads, cpu_commit=cpu_commit,
                        mem_total=mi["MemTotal"], avail=avail, ours_rss=ours_rss, unrealized=unrealized,
                        unrealized_peak=unrealized_peak, pooled_owners=sorted(profiles),
                        reserve_cpu=cfg["reserve_cpu"], reserve_mem=reserve, running=len(running),
                        pinned=len(pinned) if pinned else None, disk=self.disk_total, disk_cap=cap,
                        disk_unrealized=disk_unrealized)
        # emergency: free memory below emergency_frac of the reserve -> preempt newest job
        floor = reserve * cfg["emergency_frac"]
        if avail < floor and running:
            v = max(running, key=lambda j: j["started"])
            self.preempt(v, now, f"preempted: free memory {fgb(avail)} < {fgb(floor)}")
            running = [j for j in running if j["id"] != v["id"]]
            avail += v["mem_mb"]
        # emergency: scratch over budget -> preempt the job with the most scratch
        if self.disk_total > cap and running and now - self.disk_ts < 60:
            v = max(running, key=lambda j: self.disk.get(j["id"], 0.0))
            used = self.disk.get(v["id"], 0.0)
            self.preempt(v, now, f"preempted: scratch {fgb(self.disk_total)} > budget {fgb(cap)} (job used {fgb(used)})",
                         disk_mb=max(v["disk_mb"], int(used * 1.3)))
            self.disk_total -= used
            running = [j for j in running if j["id"] != v["id"]]
        disk_room = cap - self.disk_total - disk_unrealized
        self.admit(cfg, now, avail - unrealized - reserve, cpu_commit, len(running), disk_room)
        self.idle_events(now)
        if now - self.last_backup > 300 and DB != os.path.join(HOME, "queue.db"):
            try:
                backup_db(c)
            except (OSError, sqlite3.Error):
                pass
            self.last_backup = now
        tmp = f"{BEAT}.tmp{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump({"pid": os.getpid(), "ts": now, "sys": self.sys}, f)
        os.replace(tmp, BEAT)

    def preempt(self, v, now, note, disk_mb=None):
        dlog(f"preempt #{v['id']}: {note}")
        self.kill(v)
        drop_scratch(config(), v["id"])
        self.c.execute("UPDATE jobs SET state='queued',pid=NULL,preempts=preempts+1,not_before=?,note=?,disk_mb=? WHERE id=?",
                       (now + 60, note, disk_mb or v["disk_mb"], v["id"]))

    def admit(self, cfg, now, mem_room, cpu_commit, n_running, disk_room=float("inf")):
        c = self.c
        cpu_room = cfg["threads"] - cfg["reserve_cpu"] - self.others_ema - cpu_commit
        queued = c.execute("SELECT * FROM jobs WHERE state='queued' AND not_before<=?", (now,)).fetchall()
        per_owner = {}
        for j in c.execute("SELECT owner, COUNT(*) n FROM jobs WHERE state='running' GROUP BY owner"):
            per_owner[j["owner"]] = j["n"]
        started = 0
        short = None
        while queued and started < cfg["starts_per_tick"] and n_running < cfg["max_running"]:
            queued.sort(key=lambda j: (-j["prio"], per_owner.get(j["owner"], 0), j["submitted"]))
            fits = lambda j: (j["mem_mb"] <= mem_room and j["disk_mb"] <= disk_room
                              and (j["cpus"] <= cpu_room or n_running == 0))
            fit = next((j for j in queued if fits(j)), None)
            head = queued[0]
            if fit is not None and fit is not head and now - head["submitted"] > cfg["starve_after_s"]:
                # head is starving: hold the room for it, but let jobs that end soon use it meanwhile,
                # so the head waits at most about backfill_short_s longer once its room frees
                short = self.short_owners(cfg) if short is None else short
                fit = next((j for j in queued if j["owner"] in short and fits(j)), None)
            if fit is None:
                break
            queued.remove(fit)
            if self.start(fit, cfg):
                mem_room -= fit["mem_mb"]
                cpu_room -= fit["cpus"]
                disk_room -= fit["disk_mb"]
                n_running += 1
                started += 1
                per_owner[fit["owner"]] = per_owner.get(fit["owner"], 0) + 1

    def short_owners(self, cfg):
        """Owners whose recent jobs (p90 of the last 50, at least 5) ran within backfill_short_s."""
        out = set()
        if cfg["backfill_short_s"] <= 0:
            return out
        for (owner,) in self.c.execute("SELECT DISTINCT owner FROM jobs WHERE state='queued'").fetchall():
            d = sorted(r[0] for r in self.c.execute(
                "SELECT finished-started FROM jobs WHERE owner=? AND state='ok' AND started IS NOT NULL "
                "ORDER BY finished DESC LIMIT 50", (owner,)))
            if len(d) >= 5 and d[int(0.9 * (len(d) - 1))] <= cfg["backfill_short_s"]:
                out.add(owner)
        return out

    def start(self, j, cfg):
        d = jobdir(j["id"])
        os.makedirs(d, exist_ok=True)
        rc = rc_path(j)
        if os.path.exists(rc):
            os.unlink(rc)
        env = dict(os.environ)
        env.update(json.loads(j["env"] or "{}"))
        n = str(max(1, int(round(j["cpus"]))))
        scratch = scratchdir(cfg, j["id"])
        drop_scratch(cfg, j["id"])  # left over from a preempted or lost run
        os.makedirs(scratch, exist_ok=True)
        env.update(KAEQ_JOB=str(j["id"]), KAEQ_CPUS=n, OMP_NUM_THREADS=n, MKL_NUM_THREADS=n,
                   OPENBLAS_NUM_THREADS=n, GOMAXPROCS=n, KAEQ_SCRATCH=scratch, TMPDIR=scratch)
        wrap = 'bash -c "$1"; echo $? > "$2"'
        argv = ["bash", "-c", wrap, "_", j["cmd"], rc]
        if shutil_which("ionice"):
            argv = ["ionice", "-c3"] + argv
        if self.use_cgroup(cfg):
            lim = int(j["mem_mb"] * cfg["mem_overrun"] * 2 + 1024)
            argv = ["systemd-run", "--user", "--scope", "--quiet", "--collect",
                    *([f"--slice={cfg['slice']}"] if cfg["slice"] else []),
                    "-p", f"MemoryMax={lim}M", "-p", "MemorySwapMax=0"] + argv
        pinned = job_cpus(cfg)

        def pre():
            os.setsid()
            if pinned:
                os.sched_setaffinity(0, pinned)
            try:
                os.sched_setscheduler(0, os.SCHED_IDLE, os.sched_param(0))
            except OSError:
                os.nice(19)
            try:
                with open("/proc/self/oom_score_adj", "w") as f:
                    f.write("1000")
            except OSError:
                pass

        cwd = j["cwd"]
        if j["sha"]:  # run a frozen copy of the submitter's tree, not whatever is checked out now
            src = os.path.join(d, "src")
            drop_worktree(j)
            try:
                git(j["root"], "worktree", "add", "--detach", "--force", src, j["sha"])
                for p in json.loads(j["links"] or "[]"):  # git-ignored inputs (data, venvs) shared by symlink
                    t = os.path.join(j["root"], p)
                    if os.path.exists(t) and not os.path.lexists(os.path.join(src, p)):
                        os.makedirs(os.path.dirname(os.path.join(src, p)), exist_ok=True)
                        os.symlink(t, os.path.join(src, p))
            except (RuntimeError, OSError) as e:
                self.finish_fail(j, "failed", f"snapshot checkout failed: {e}")
                return False
            cwd = os.path.normpath(os.path.join(src, j["rel"] or "."))
        if not os.path.isdir(cwd or ""):
            self.finish_fail(j, "failed", f"cwd missing on daemon host: {j['cwd']}")
            return False
        try:
            with open(os.path.join(d, "log"), "ab") as log:
                log.write(f"=== kaeq start job {j['id']} attempt {j['attempt']} by daemon {os.getpid()} at "
                          f"{time.strftime('%Y-%m-%d %H:%M:%S')} (db {DB}) ===\n".encode())
                log.flush()
                p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                     stderr=subprocess.STDOUT, preexec_fn=pre)
        except OSError as e:
            self.finish_fail(j, "failed", f"spawn error: {e}")
            return False
        self.popen[j["id"]] = p
        self.c.execute("UPDATE jobs SET state='running',pid=?,started=?,deadline=?,peak_mb=0,note=NULL WHERE id=?",
                       (p.pid, time.time(), time.time() + j["timeout_s"], j["id"]))
        dlog(f"start #{j['id']} attempt {j['attempt']} pid {p.pid} mem {fgb(j['mem_mb'])} {j['name'] or j['cmd'][:60]}")
        return True

    def kill(self, j, sig=signal.SIGTERM):
        cg = self.cgroups.get(j["id"]) or (job_cgroup(j["pid"]) if j["pid"] and pid_alive(j["pid"]) else None)
        kill_tree(j["pid"], cg, sig)
        if sig == signal.SIGTERM:  # a hard kill after a short grace
            time.sleep(0.2)
            kill_tree(j["pid"], cg, signal.SIGKILL)

    def check(self, j, rss, now, cfg, disk=0.0):
        c = self.c
        if disk > j["disk_peak_mb"]:
            c.execute("UPDATE jobs SET disk_peak_mb=? WHERE id=?", (int(disk), j["id"]))
        p = self.popen.get(j["id"])
        if p:
            p.poll()
        rcf = rc_path(j)
        legacy = os.path.join(jobdir(j["id"]), "rc")  # jobs started before rc files were named per start
        if not os.path.exists(rcf) and os.path.exists(legacy) and os.path.getmtime(legacy) >= (j["started"] or 0):
            rcf = legacy
        peak = max(j["peak_mb"], int(rss))
        if peak != j["peak_mb"]:
            c.execute("UPDATE jobs SET peak_mb=? WHERE id=?", (peak, j["id"]))
        if os.path.exists(rcf):
            try:
                rc = int(open(rcf).read().strip() or 1)
            except ValueError:
                rc = 1
            kill_tree(j["pid"], self.cgroups.get(j["id"]))  # stragglers, in their own sessions too
            self.popen.pop(j["id"], None)
            return self.finish(j, rc, peak)
        if not pid_alive(j["pid"]):
            self.popen.pop(j["id"], None)
            return self.finish(j, 137, peak, lost=True)
        if now > j["deadline"]:
            self.kill(j)
            return self.finish_fail(j, "timeout", f"exceeded --timeout {fdur(j['timeout_s'])}; raise --timeout or split the job", peak)
        if disk > j["disk_mb"] * cfg["disk_overrun"] + 5 * 1024:
            self.kill(j)
            drop_scratch(cfg, j["id"])
            new = int(disk * 1.3) + 1024
            if j["preempts"] < 2:
                c.execute("UPDATE jobs SET state='queued',pid=NULL,disk_mb=?,preempts=preempts+1,note=? WHERE id=?",
                          (new, f"killed at scratch {fgb(disk)} > declared {fgb(j['disk_mb'])}; auto-requeued with --disk {fgb(new)}", j["id"]))
            else:
                self.finish_fail(j, "failed", f"scratch {fgb(disk)} exceeded declared {fgb(j['disk_mb'])}; resubmit with --disk {fgb(new)}")
            return
        if rss > j["mem_mb"] * cfg["mem_overrun"] + 1024:
            self.kill(j)
            new = int(rss * 1.3) + 1024
            drop_scratch(cfg, j["id"])
            if j["preempts"] < 2:  # one automatic re-queue with a corrected estimate
                c.execute("UPDATE jobs SET state='queued',pid=NULL,mem_mb=?,preempts=preempts+1,note=? WHERE id=?",
                          (new, f"killed at {fgb(rss)} > declared {fgb(j['mem_mb'])}; auto-requeued with --mem {fgb(new)}", j["id"]))
            else:
                self.finish_fail(j, "oom", f"RSS {fgb(rss)} exceeded declared {fgb(j['mem_mb'])}; resubmit with --mem {fgb(new)}", peak)

    def owner_profiles(self, cfg, now, running):
        """{owner: MEM_BINS weights}: the average memory histogram of an owner's last 50 finished
        jobs, for owners with at least mem_pool_min_jobs of them (refreshed every minute)."""
        if now - self.profiles_ts < 60:
            return self.profiles
        out = {}
        for o in {j["owner"] for j in running}:
            hs = [json.loads(r[0]) for r in self.c.execute(
                "SELECT mem_hist FROM jobs WHERE owner=? AND mem_hist IS NOT NULL ORDER BY finished DESC LIMIT 50", (o,))]
            hs = [h for h in hs if sum(h)]
            if len(hs) >= cfg["mem_pool_min_jobs"]:
                out[o] = [sum(h[k] / sum(h) for h in hs) / len(hs) for k in range(MEM_BINS)]
        self.profiles, self.profiles_ts = out, now
        return out

    def finish(self, j, rc, peak, lost=False):
        dlog(f"finish #{j['id']} rc {rc}{' lost' if lost else ''} peak {fgb(peak)}")
        if rc == 0 and not lost:
            _, tr, whole = self.trace.pop(j["id"], [0, [], False])
            hist = json.dumps(mem_hist(tr, peak)) if whole and len(tr) >= 6 and peak > 0 else None  # >= 1 min, from its start
            self.c.execute("UPDATE jobs SET state='ok',rc=0,finished=?,pid=NULL,mem_hist=? WHERE id=?",
                           (time.time(), hist, j["id"]))
            drop_worktree(j)
            drop_scratch(config(), j["id"])
            return
        note = "daemon lost the job's process" if lost else f"rc={rc}" + (" (SIGKILL: likely memory-cgroup OOM, raise --mem)" if rc == 137 else "")
        self.finish_fail(j, "lost" if lost else "failed", note, peak, rc)

    def finish_fail(self, j, state, note, peak=None, rc=None):
        c = self.c
        peak = peak if peak is not None else j["peak_mb"]
        drop_scratch(config(), j["id"])
        if j["retries_left"] > 0 and state != "timeout":
            c.execute("UPDATE jobs SET state='queued',pid=NULL,attempt=attempt+1,retries_left=retries_left-1,note=? WHERE id=?",
                      (f"auto-retry after: {note}", j["id"]))
            return
        c.execute("UPDATE jobs SET state=?,rc=?,finished=?,pid=NULL,peak_mb=?,note=? WHERE id=?",
                  (state, rc if rc is not None else -1, time.time(), peak, note, j["id"]))
        drop_worktree(j)
        run = (time.time() - (j["started"] or time.time()))
        head = f"#{j['id']} {state.upper()} {note} | {j['name'] or j['cmd'][:60]} | {ref(j)} | {fdur(run)} peak {fgb(peak)}/{fgb(j['mem_mb'])} attempt {j['attempt']}"
        event(c, j, state, "\n".join([head] + digest(j["id"]) + [f"  log: {os.path.join(jobdir(j['id']), 'log')}  retry: kaeq retry {j['id']}"]))

    def idle_events(self, now):
        """One 'idle' event when an owner's last active job ends."""
        c = self.c
        for r in c.execute("""SELECT owner FROM jobs GROUP BY owner HAVING SUM(state IN ('queued','running'))=0
                              AND MAX(finished) > COALESCE((SELECT MAX(ts) FROM events e WHERE e.owner=jobs.owner AND e.kind='idle'),0)"""):
            o = r["owner"]
            cnt = dict(c.execute("SELECT state, COUNT(*) FROM jobs WHERE owner=? GROUP BY state", (o,)).fetchall())
            msg = "all jobs finished: " + ", ".join(f"{v} {k}" for k, v in sorted(cnt.items()))
            c.execute("INSERT INTO events(ts,owner,job,kind,msg) VALUES(?,?,0,'idle',?)", (now, o, msg))

    def run(self):
        os.makedirs(HOME, exist_ok=True)
        # running jobs from a previous daemon are adopted: check() handles alive / finished / lost
        signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
        while True:
            try:
                self.tick()
            except sqlite3.OperationalError:
                pass
            time.sleep(TICK)


def shutil_which(x):
    import shutil
    return shutil.which(x)


def take_lock():
    """The single-daemon lock (a POSIX lock: NFS enforces it across hosts and namespaces, where
    pids are not comparable). Returns the open file holding it, or None if another daemon has it."""
    os.makedirs(HOME, exist_ok=True)
    f = open(LOCK, "a+")
    try:
        fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def daemon_status():
    """The daemon's heartbeat if it is alive: a fresh beat, or the lock held (never a pid check alone:
    a process in another pid namespace cannot see the daemon's pid)."""
    b = None
    try:
        with open(os.path.join(HOME, f"daemon.{pinned_host() or HOST}.json")) as f:
            b = json.load(f)
    except (OSError, ValueError):
        pass
    if b and time.time() - b.get("ts", 0) < 15:
        return b
    lk = take_lock()
    if lk is None:  # held: a daemon runs (perhaps busy, or beating where we cannot see)
        return b or {"pid": None, "ts": 0, "sys": {}}
    lk.close()
    return None


def run_daemon(a):
    lk = take_lock()
    if lk is None:
        print(f"kaeq: another daemon holds {LOCK}; not starting a second one", flush=True)
        return
    cfg = {}
    try:
        cfg = json.load(open(CONF))
    except (OSError, ValueError):
        pass
    if (not os.environ.get("KAEQ_DB") and cfg.get("db") != DB) or cfg.get("host") != HOST:
        cfg["db"] = DB  # pin the database path and host for every client
        cfg["host"] = HOST
        os.makedirs(HOME, exist_ok=True)
        json.dump(cfg, open(CONF, "w"), indent=1)
    db(restore=True).close()
    dlog(f"daemon {os.getpid()} up: db {DB}")
    Daemon().run()


def ensure_daemon():
    if daemon_status():
        return
    os.makedirs(HOME, exist_ok=True)
    with open(os.path.join(HOME, "daemon.log"), "ab") as log:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "daemon"], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)
    for _ in range(40):
        time.sleep(0.25)
        if daemon_status():
            return
    print("warning: daemon did not start; see ~/.kaeq/daemon.log", file=sys.stderr)


# ---------------------------------------------------------------- client commands
def cmd_submit(a):
    cmds = []
    if a.jobs:  # JSONL, one job per line: {"cmd": ..., optional "name","cpus","mem","disk","timeout","prio"}
        src = sys.stdin if a.jobs == "-" else open(a.jobs)
        cmds = [json.loads(l) for l in src if l.strip() and not l.startswith("#")]
    elif a.batch:
        src = sys.stdin if a.batch == "-" else open(a.batch)
        cmds = [l.strip() for l in src if l.strip() and not l.startswith("#")]
    else:
        if not a.command:
            sys.exit("usage: kaeq submit [opts] -- <command...>   (or --batch FILE)")
        cmds = [shlex.join(a.command) if len(a.command) > 1 else a.command[0]]
    env = {k: os.environ[k] for k in ENV_KEEP if k in os.environ}
    for kv in a.env or []:
        k, _, v = kv.partition("=")
        env[k] = v
    owner = a.owner or default_owner()
    snap = None if a.live else git_snapshot(a.cwd or os.getcwd())
    if snap is None:
        snap = dict(root=None, branch=None, sha=None, rel=None)
    ensure_daemon()
    c = db()
    ids = []
    now = time.time()
    c.execute("BEGIN")
    for i, cmd in enumerate(cmds):
        o = cmd if isinstance(cmd, dict) else {"cmd": cmd}
        cur = c.execute(
            "INSERT INTO jobs(owner,name,tag,cmd,cwd,env,cpus,mem_mb,timeout_s,prio,state,retries_left,submitted,root,branch,sha,rel,links,disk_mb)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,'queued',?,?,?,?,?,?,?,?)",
            (owner, o.get("name") or a.name, a.tag, o["cmd"], os.path.abspath(a.cwd or os.getcwd()),
             json.dumps(env), float(o.get("cpus", a.cpus)), int(parse_size(o.get("mem", a.mem)) / (1 << 20)),
             parse_dur(o.get("timeout", a.timeout)), int(o.get("prio", a.prio)), a.retries, now + i * 1e-6,
             snap["root"], snap["branch"], snap["sha"], snap["rel"], json.dumps(a.link or []),
             int(parse_size(o.get("disk", a.disk)) / (1 << 20))))
        ids.append(cur.lastrowid)
    c.execute("COMMIT")
    c.commit()
    ahead = c.execute("SELECT COUNT(*) FROM jobs WHERE state='queued' AND id<?", (ids[0],)).fetchone()[0]
    rng = f"#{ids[0]}" if len(ids) == 1 else f"#{ids[0]}..#{ids[-1]} ({len(ids)} jobs)"
    where = f"code={snap['root'] and os.path.basename(snap['root'])}@{snap['branch']}:{snap['sha'][:7]} (frozen now)" if snap["sha"] else "code=live dir"
    print(f"queued {rng} owner={owner} {where} ({ahead} ahead). Get failures pushed to you: kaeq wait --owner {owner}")


def sel_jobs(c, a, states=None):
    q, p = "SELECT * FROM jobs WHERE 1=1", []
    if getattr(a, "ids", None):
        q += f" AND id IN ({','.join('?' * len(a.ids))})"
        p += [int(x.lstrip('#')) for x in a.ids]
    if getattr(a, "owner", None):
        q += " AND owner=?"
        p.append(a.owner)
    if getattr(a, "tag", None):
        q += " AND tag=?"
        p.append(a.tag)
    if states:
        q += f" AND state IN ({','.join('?' * len(states))})"
        p += list(states)
    return c.execute(q + " ORDER BY id", p).fetchall()


def cmd_status(a):
    c = db()
    d = daemon_status()
    if not d:
        print("daemon: NOT RUNNING (any `kaeq submit` starts it; or `kaeq daemon &`)")
    else:
        s = d["sys"]
        print(f"cpu {s['others'] + s['cpu_commit']:.0f}/{s['threads']} thr (others {s['others']:.0f}, ours {s['cpu_commit']:.0f}, reserve {s['reserve_cpu']}) | "
              f"mem avail {s['avail'] / 1024:.0f}/{s['mem_total'] / 1024:.0f}G (ours {s['ours_rss'] / 1024:.0f}G rss +{s['unrealized'] / 1024:.0f}G reserved, keep-free {s['reserve_mem'] / 1024:.0f}G)"
              + (f" | scratch {s['disk'] / 1024:.1f}/{s['disk_cap'] / 1024:.0f}G" if "disk" in s else "")
              + (f" | jobs pinned to {s['pinned']} cpus" if s.get("pinned") else ""))
    counts = {}
    for r in c.execute("SELECT owner,state,COUNT(*) n FROM jobs GROUP BY owner,state"):
        counts.setdefault(r["owner"], {})[r["state"]] = r["n"]
    if a.owner:
        counts = {a.owner: counts.get(a.owner, {})}
    for o, st in sorted(counts.items()):
        print(f"{o}: " + " ".join(f"{k}={v}" for k, v in sorted(st.items())))
    now = time.time()
    run = sel_jobs(c, a, ["running"])
    for j in run[: a.limit]:
        print(f"RUN  #{j['id']} {j['owner']} {fdur(now - j['started'])} {fgb(j['peak_mb'])}/{fgb(j['mem_mb'])} {j['cpus']:g}c {j['name'] or j['cmd'][:50]}")
    if len(run) > a.limit:
        print(f"  (+{len(run) - a.limit} more running)")
    bad = sel_jobs(c, a, PROBLEM)
    for j in bad[-a.limit:]:
        print(f"{j['state'].upper():4} #{j['id']} {j['owner']} {j['note']} | {j['name'] or j['cmd'][:50]}")
    if len(bad) > a.limit:
        print(f"  (+{len(bad) - a.limit} older problems; `kaeq result ID`)")
    waits = [j for j in sel_jobs(c, a, ["queued"]) if j["note"]]
    for j in waits[:5]:
        print(f"QUEUED #{j['id']} {j['note']}")


def pending(c, owner, mark=True, kinds=None):
    q = "SELECT * FROM events WHERE delivered=0 AND owner=?"
    rows = c.execute(q, (owner,)).fetchall()
    if kinds:
        rows = [r for r in rows if r["kind"] in kinds]
    if mark and rows:
        c.execute(f"UPDATE events SET delivered=1 WHERE id IN ({','.join(str(r['id']) for r in rows)})")
        c.commit()
    return rows


def print_events(rows, cap=8):
    for r in rows[:cap]:
        print(r["msg"])
    if len(rows) > cap:
        print(f"(+{len(rows) - cap} more problem events; `kaeq status --owner ...` / `kaeq inbox`)")


def cmd_inbox(a):
    c = db()
    rows = pending(c, a.owner or default_owner())
    print_events(rows) if rows else print("inbox empty")


def cmd_wait(a):
    """Block until a problem or 'all done'. Exit 1 = problems, 0 = all done, 2 = timeout (call again)."""
    owner = a.owner or default_owner()
    t_end = time.time() + parse_dur(a.timeout)
    while True:
        c = db()
        rows = pending(c, owner)
        if rows:
            print_events(rows)
            ns = c.execute("SELECT COUNT(*) FROM jobs WHERE owner=? AND state IN ('queued','running')", (owner,)).fetchone()[0]
            if ns:
                print(f"({ns} still active; run `kaeq wait --owner {owner}` again to keep listening)")
            sys.exit(1 if any(r["kind"] in PROBLEM for r in rows) else 0)
        if not c.execute("SELECT 1 FROM jobs WHERE owner=? AND state IN ('queued','running') LIMIT 1", (owner,)).fetchone():
            print(f"nothing active for owner {owner}")
            sys.exit(0)
        if time.time() > t_end:
            cmd_status(argparse.Namespace(owner=owner, tag=None, ids=None, limit=5))
            print("no problems yet; call `kaeq wait` again")
            sys.exit(2)
        c.close()
        time.sleep(2)


def cmd_result(a):
    c = db()
    for j in sel_jobs(c, a):
        run = ((j["finished"] or time.time()) - j["started"]) if j["started"] else 0
        print(f"#{j['id']} {j['state'].upper()} rc={j['rc']} {fdur(run)} peak {fgb(j['peak_mb'])}/{fgb(j['mem_mb'])} {j['cpus']:g}c attempt {j['attempt']} owner={j['owner']} code={ref(j)}")
        print(f"  cmd: {j['cmd'][:300]}\n  cwd: {j['cwd']}" + (f"\n  note: {j['note']}" if j["note"] else ""))
        print("\n".join(digest(j["id"], tail=a.tail)) + f"\n  log: {os.path.join(jobdir(j['id']), 'log')}")


def cmd_retry(a):
    c = db()
    if not a.ids:
        a.owner = a.owner or default_owner()  # never retry other sessions' failures by default
    rows = sel_jobs(c, a, None if a.ids else PROBLEM)
    for j in rows:
        if j["state"] in ACTIVE:
            continue
        mem = int(parse_size(a.mem) / (1 << 20)) if a.mem else max(j["mem_mb"], int(j["peak_mb"] * 1.3)) if j["state"] == "oom" else j["mem_mb"]
        snap = None if not j["sha"] or not os.path.isdir(j["cwd"] or "") else git_snapshot(j["cwd"])  # pick up the fixes
        if snap:
            c.execute("UPDATE jobs SET root=?,branch=?,sha=?,rel=? WHERE id=?", (snap["root"], snap["branch"], snap["sha"], snap["rel"], j["id"]))
        disk = int(parse_size(a.disk) / (1 << 20)) if getattr(a, "disk", None) else j["disk_mb"]
        c.execute("UPDATE jobs SET state='queued',attempt=attempt+1,preempts=0,mem_mb=?,timeout_s=?,cpus=?,pid=NULL,rc=NULL,"
                  "started=NULL,finished=NULL,note=NULL,submitted=?,retries_left=?,disk_mb=? WHERE id=?",
                  (mem, parse_dur(a.timeout) if a.timeout else j["timeout_s"], a.cpus or j["cpus"], time.time(), a.retries,
                   disk, j["id"]))
        if os.path.isdir(jobdir(j["id"])):
            with open(os.path.join(jobdir(j["id"]), "log"), "ab") as f:
                f.write(f"\n=== kaeq retry (attempt {j['attempt'] + 1}) ===\n".encode())
    c.commit()
    ensure_daemon()
    print(f"requeued {len([j for j in rows if j['state'] not in ACTIVE])} job(s): " + " ".join(f"#{j['id']}" for j in rows if j["state"] not in ACTIVE))


def cmd_cancel(a):
    c = db()
    rows = sel_jobs(c, a, ACTIVE)
    if not (a.ids or a.owner or a.tag):
        sys.exit("give job ids, --owner or --tag")
    for j in rows:
        c.execute("UPDATE jobs SET state='cancelled',finished=?,note='cancelled' WHERE id=?", (time.time(), j["id"]))
        drop_worktree(j)
        if j["state"] == "running":
            kill_tree(j["pid"], job_cgroup(j["pid"]) if j["pid"] and pid_alive(j["pid"]) else None)
            drop_scratch(config(), j["id"])
    c.commit()
    print(f"cancelled {len(rows)} job(s)")


def cmd_prio(a):
    c = db()
    if not (a.ids or a.owner or a.tag):
        sys.exit("give job ids, --owner or --tag")
    n = 0
    for j in sel_jobs(c, a, ("queued",)):
        n += c.execute("UPDATE jobs SET prio=? WHERE id=? AND state='queued'", (a.prio, j["id"])).rowcount
    c.commit()
    print(f"set priority {a.prio} on {n} queued job(s)")


def cmd_config(a):
    cfg = {}
    try:
        cfg = json.load(open(CONF))
    except (OSError, ValueError):
        pass
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        if k not in DEFAULTS:
            sys.exit(f"unknown key {k}; keys: {', '.join(DEFAULTS)}")
        cfg[k] = type(DEFAULTS[k])(v) if not isinstance(DEFAULTS[k], str) else v
    if a.set:
        os.makedirs(HOME, exist_ok=True)
        json.dump(cfg, open(CONF, "w"), indent=1)
    print(json.dumps({**DEFAULTS, **cfg}, indent=1))


def cmd_doctor(a):
    d = Daemon()
    cfg = config()
    ok = lambda b: "ok " if b else "NO "
    try:
        os.sched_setscheduler(0, os.SCHED_IDLE, os.sched_param(0))
        sched = True
    except OSError:
        sched = False
    print(f"{ok(sched)}SCHED_IDLE (jobs only use CPU nobody else wants)")
    try:
        open("/proc/self/oom_score_adj", "w").write("1000")
        oom = True
    except OSError:
        oom = False
    print(f"{ok(oom)}oom_score_adj=1000 (kernel kills our jobs before other users')")
    print(f"{ok(d.use_cgroup(cfg))}systemd --user memory cgroup (hard MemoryMax backstop; optional: RSS polling enforces otherwise)")
    print(f"{ok(bool(shutil_which('ionice')))}ionice")
    print(f"{ok(daemon_status() is not None)}daemon running (auto-starts on submit)")
    pinned = job_cpus(cfg)
    print(f"{ok(bool(pinned))}CPU affinity: jobs pinned to {len(pinned) if pinned else 'all'} of {os.cpu_count()} cpus (hard cap)")
    print(f"ok  scratch: {cfg['scratch_dir']} budget {cfg['scratch_gb']}G | database: {DB}" + (f" (backed up to {DB_BACKUP})" if DB != os.path.join(HOME, "queue.db") else ""))
    print(f"threads={cfg['threads']} reserve_cpu={cfg['reserve_cpu']} | mem {meminfo()['MemTotal'] // 1024}G reserve {cfg['reserve_mem_gb']}G")


def cmd_install_service(a):
    """systemd --user unit for the daemon (restarted on failure; with linger it survives logout and reboot)
    and the slice job scopes run in, with a hard memory cap of (1 - reserve_frac) of RAM."""
    cfg = config()
    d = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(d, exist_ok=True)
    unit = (f"[Unit]\nDescription=kaeq job queue daemon\n\n[Service]\nExecStart={sys.executable} {os.path.realpath(__file__)} daemon\n"
            "Restart=always\nRestartSec=5\nKillMode=process\n\n[Install]\nWantedBy=default.target\n")
    open(os.path.join(d, "kaeq.service"), "w").write(unit)
    total_mb = meminfo()["MemTotal"]
    cap = int(total_mb - cfg["reserve_mem_gb"] * 1024)
    if cfg["slice"]:
        open(os.path.join(d, cfg["slice"]), "w").write(
            f"[Unit]\nDescription=kaeq jobs\n\n[Slice]\nMemoryMax={cap}M\nMemoryHigh={int(cap * 0.95)}M\nMemorySwapMax=0\n")
    print(f"wrote kaeq.service and {cfg['slice'] or '(no slice)'} (MemoryMax {fgb(cap)}). Run: systemctl --user daemon-reload && "
          "systemctl --user enable --now kaeq && loginctl enable-linger $USER")


def cmd_down(a):
    d = daemon_status()
    if d:
        os.kill(d["pid"], signal.SIGTERM)
        print("daemon stopped (running jobs keep running and are adopted on restart)")
    else:
        print("daemon not running")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    host = os.environ.get("KAEQ_SSH")
    if host and argv and argv[0] != "daemon":  # drive a remote queue from another machine
        os.execvp("ssh", ["ssh", host, "kaeq " + " ".join(shlex.quote(x) for x in argv)])
    p = argparse.ArgumentParser(prog="kaeq", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def owner_opt(sp):
        sp.add_argument("--owner", help="session label (default $KAEQ_OWNER or user-dirname)")

    s = sub.add_parser("submit", help="queue a command (or --batch file, one command per line)")
    owner_opt(s)
    s.add_argument("--cpus", type=float, default=1, help="threads it will use (also exported as OMP_NUM_THREADS/KAEQ_CPUS)")
    s.add_argument("--mem", default="4G", help="peak RSS estimate; exceeding 1.5x kills and requeues with a corrected value")
    s.add_argument("--disk", default="1G", help="peak scratch ($KAEQ_SCRATCH) estimate; admission keeps the total under scratch_gb")
    s.add_argument("--timeout", default="1h")
    s.add_argument("--prio", type=int, default=0, help="higher runs first")
    s.add_argument("--retries", type=int, default=0, help="auto-retry on failure (not for deterministic test failures)")
    s.add_argument("--name"), s.add_argument("--tag"), s.add_argument("--cwd")
    s.add_argument("--env", action="append", metavar="K=V")
    s.add_argument("--batch", metavar="FILE", help="'-' for stdin")
    s.add_argument("--jobs", metavar="FILE", help="JSONL, one job per line: {cmd, name, cpus, mem, disk, timeout, prio}; '-' for stdin")
    s.add_argument("--live", action="store_true", help="run in the directory as-is when the job starts (default: frozen git snapshot taken now)")
    s.add_argument("--link", action="append", metavar="PATH", help="git-ignored repo path to symlink into the snapshot (e.g. kae-work); repeatable")
    s.add_argument("command", nargs=argparse.REMAINDER)
    s.set_defaults(f=cmd_submit)

    s = sub.add_parser("status", help="resources, per-owner counts, running + problem jobs")
    owner_opt(s), s.add_argument("--tag"), s.add_argument("--limit", type=int, default=12)
    s.set_defaults(f=cmd_status, ids=None)

    s = sub.add_parser("wait", help="block until a problem or all done (run in background; exit 1 problems/0 done/2 timeout)")
    owner_opt(s), s.add_argument("--timeout", default="55m")
    s.set_defaults(f=cmd_wait)

    s = sub.add_parser("inbox", help="print undelivered events without blocking")
    owner_opt(s)
    s.set_defaults(f=cmd_inbox)

    s = sub.add_parser("result", help="digest of job(s): state, error lines, log tail")
    s.add_argument("ids", nargs="*"), owner_opt(s), s.add_argument("--tag"), s.add_argument("--tail", type=int, default=25)
    s.set_defaults(f=cmd_result)

    s = sub.add_parser("retry", help="requeue ids, or (no ids) all failed jobs of your --owner/--tag, optionally with new --mem/--cpus/--timeout")
    s.add_argument("ids", nargs="*"), owner_opt(s), s.add_argument("--tag")
    s.add_argument("--mem"), s.add_argument("--cpus", type=float), s.add_argument("--timeout"), s.add_argument("--disk")
    s.add_argument("--retries", type=int, default=0)
    s.set_defaults(f=cmd_retry)

    s = sub.add_parser("cancel", help="cancel queued/running jobs by id, --owner or --tag")
    s.add_argument("ids", nargs="*"), owner_opt(s), s.add_argument("--tag")
    s.set_defaults(f=cmd_cancel)

    s = sub.add_parser("prio", help="change the priority of queued jobs by id, --owner or --tag")
    s.add_argument("prio", type=int), s.add_argument("ids", nargs="*"), owner_opt(s), s.add_argument("--tag")
    s.set_defaults(f=cmd_prio)

    s = sub.add_parser("config", help="show / set limits: --set reserve_cpu=24 --set reserve_mem_gb=48")
    s.add_argument("--set", action="append")
    s.set_defaults(f=cmd_config)

    for name, f, h in (("doctor", cmd_doctor, "check isolation features"), ("down", cmd_down, "stop daemon"),
                       ("install-service", cmd_install_service, "write a systemd --user unit"),
                       ("daemon", run_daemon, "run the scheduler in the foreground")):
        sub.add_parser(name, help=h).set_defaults(f=f)
    a = p.parse_args(argv)
    if getattr(a, "command", None) and a.command[:1] == ["--"]:
        a.command = a.command[1:]
    a.f(a)


if __name__ == "__main__":
    main()
