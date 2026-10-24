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
import json
import os
import re
import shlex
import signal
import sqlite3
import subprocess
import sys
import time

HOME = os.path.expanduser(os.environ.get("KAEQ_HOME", "~/.kaeq"))
DB = os.path.join(HOME, "queue.db")
CONF = os.path.join(HOME, "config.json")
BEAT = os.path.join(HOME, "daemon.json")
GB = 1 << 30
TICK = 2.0
ACTIVE = ("queued", "running")
PROBLEM = ("failed", "timeout", "oom", "lost")
ENV_KEEP = ("PATH", "VIRTUAL_ENV", "PYTHONPATH", "LD_LIBRARY_PATH", "HOME", "LANG")

DEFAULTS = {
    "threads": 0,            # 0 = os.cpu_count()
    "reserve_cpu": 16,       # threads kept free for other users
    "mem_total_gb": 0,       # 0 = MemTotal
    "reserve_mem_gb": 40,    # MemAvailable kept free for other users
    "max_running": 256,
    "mem_overrun": 1.5,      # kill a job whose RSS exceeds declared * this (+1 GB)
    "starve_after_s": 600,   # a head-of-line job waiting this long blocks backfill
    "cgroup": "auto",        # auto|on|off: wrap jobs in `systemd-run --user --scope`
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
 id INTEGER PRIMARY KEY, owner TEXT, name TEXT, tag TEXT, cmd TEXT, cwd TEXT, env TEXT,
 cpus REAL, mem_mb INTEGER, timeout_s INTEGER, prio INTEGER DEFAULT 0, state TEXT,
 attempt INTEGER DEFAULT 1, retries_left INTEGER DEFAULT 0, preempts INTEGER DEFAULT 0,
 submitted REAL, started REAL, finished REAL, not_before REAL DEFAULT 0, deadline REAL,
 pid INTEGER, rc INTEGER, peak_mb INTEGER DEFAULT 0, note TEXT,
 root TEXT, branch TEXT, sha TEXT, rel TEXT, links TEXT);
CREATE INDEX IF NOT EXISTS jobs_state ON jobs(state);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY, ts REAL, owner TEXT, job INTEGER, kind TEXT, msg TEXT,
 delivered INTEGER DEFAULT 0);
"""


# ---------------------------------------------------------------- helpers
def db():
    os.makedirs(HOME, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    have = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
    for col in ("root", "branch", "sha", "rel", "links"):  # upgrade a pre-snapshot database
        if col not in have:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")
    return c


def config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONF) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    cfg["threads"] = cfg["threads"] or os.cpu_count() or 1
    return cfg


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
    """{sid: (rss_mb, cpu_ticks)} over every process we can read."""
    out = {}
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
        r, t = out.get(sid, (0.0, 0))
        out[sid] = (r + rss * page_mb, t + ut + st)
    return out


def event(c, job, kind, msg):
    c.execute("INSERT INTO events(ts,owner,job,kind,msg) VALUES(?,?,?,?,?)", (time.time(), job["owner"], job["id"], kind, msg))


def jobdir(jid):
    return os.path.join(HOME, "jobs", str(jid))


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
    marks = [i for i, l in enumerate(lines) if l.startswith("=== kaeq retry")]
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
                         "cat /sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)/memory.max"],
                        capture_output=True, text=True, timeout=15)
                    self.cg = r.returncode == 0 and r.stdout.strip() == str(GB)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        return self.cg if cfg["cgroup"] == "auto" else True

    # -- one scheduling pass
    def tick(self):
        cfg = config()
        c = self.c
        sessions = proc_by_session()
        now = time.time()
        running = c.execute("SELECT * FROM jobs WHERE state='running'").fetchall()
        ours_ticks, ours_rss, unrealized = 0, 0.0, 0.0
        for j in running:
            rss, ticks = sessions.get(j["pid"], (0.0, 0))
            ours_rss += rss
            ours_ticks += max(0, ticks - self.prev_ours.get(j["id"], ticks))
            self.prev_ours[j["id"]] = ticks
            self.check(j, rss, now, cfg)
        # system sample
        busy, total = cpu_ticks()
        dt = max(1, total - self.prev[1])
        sys_threads = (busy - self.prev[0]) / dt * cfg["threads"]
        ours_threads = ours_ticks / dt * cfg["threads"]
        self.others_ema = 0.7 * self.others_ema + 0.3 * max(0.0, sys_threads - ours_threads)
        self.prev = (busy, total)
        mi = meminfo()
        running = c.execute("SELECT * FROM jobs WHERE state='running'").fetchall()
        for j in running:
            rss = sessions.get(j["pid"], (0.0, 0))[0]
            unrealized += max(0.0, j["mem_mb"] - rss)
        declared = max(1.0, sum(j["cpus"] for j in running))
        # declared CPUs while a job warms up, then what the fleet really uses (floor: 25% of declared)
        cpu_commit = sum(j["cpus"] if now - j["started"] < 20 else max(j["cpus"] * 0.25, ours_threads * j["cpus"] / declared)
                         for j in running)
        avail = mi["MemAvailable"]
        reserve = cfg["reserve_mem_gb"] * 1024
        self.sys = dict(threads=cfg["threads"], others=self.others_ema, ours_cpu=ours_threads, cpu_commit=cpu_commit,
                        mem_total=mi["MemTotal"], avail=avail, ours_rss=ours_rss, unrealized=unrealized,
                        reserve_cpu=cfg["reserve_cpu"], reserve_mem=reserve, running=len(running))
        # emergency: free memory below half the reserve -> preempt newest job
        if avail < reserve / 2 and running:
            v = max(running, key=lambda j: j["started"])
            self.kill(v)
            c.execute("UPDATE jobs SET state='queued',pid=NULL,preempts=preempts+1,not_before=?,note=? WHERE id=?",
                      (now + 60, f"preempted: free memory {fgb(avail)} < {fgb(reserve / 2)}", v["id"]))
            running = [j for j in running if j["id"] != v["id"]]
            avail += v["mem_mb"]
        self.admit(cfg, now, avail - unrealized - reserve, cpu_commit, len(running))
        self.idle_events(now)
        with open(BEAT + ".tmp", "w") as f:
            json.dump({"pid": os.getpid(), "ts": now, "sys": self.sys}, f)
        os.replace(BEAT + ".tmp", BEAT)

    def admit(self, cfg, now, mem_room, cpu_commit, n_running):
        c = self.c
        cpu_room = cfg["threads"] - cfg["reserve_cpu"] - self.others_ema - cpu_commit
        queued = c.execute("SELECT * FROM jobs WHERE state='queued' AND not_before<=?", (now,)).fetchall()
        per_owner = {}
        for j in c.execute("SELECT owner, COUNT(*) n FROM jobs WHERE state='running' GROUP BY owner"):
            per_owner[j["owner"]] = j["n"]
        started = 0
        while queued and started < 8 and n_running < cfg["max_running"]:
            queued.sort(key=lambda j: (-j["prio"], per_owner.get(j["owner"], 0), j["submitted"]))
            fit = next((j for j in queued if j["mem_mb"] <= mem_room and (j["cpus"] <= cpu_room or n_running == 0)), None)
            head = queued[0]
            if fit is None or (fit is not head and now - head["submitted"] > cfg["starve_after_s"]):
                break  # nothing fits, or head is starving: hold the room for it
            queued.remove(fit)
            if self.start(fit, cfg):
                mem_room -= fit["mem_mb"]
                cpu_room -= fit["cpus"]
                n_running += 1
                started += 1
                per_owner[fit["owner"]] = per_owner.get(fit["owner"], 0) + 1

    def start(self, j, cfg):
        d = jobdir(j["id"])
        os.makedirs(d, exist_ok=True)
        rc = os.path.join(d, "rc")
        if os.path.exists(rc):
            os.unlink(rc)
        env = dict(os.environ)
        env.update(json.loads(j["env"] or "{}"))
        n = str(max(1, int(round(j["cpus"]))))
        env.update(KAEQ_JOB=str(j["id"]), KAEQ_CPUS=n, OMP_NUM_THREADS=n, MKL_NUM_THREADS=n,
                   OPENBLAS_NUM_THREADS=n, GOMAXPROCS=n)
        wrap = 'bash -c "$1"; echo $? > "$2"'
        argv = ["bash", "-c", wrap, "_", j["cmd"], rc]
        if shutil_which("ionice"):
            argv = ["ionice", "-c3"] + argv
        if self.use_cgroup(cfg):
            lim = int(j["mem_mb"] * cfg["mem_overrun"] * 2 + 1024)
            argv = ["systemd-run", "--user", "--scope", "--quiet", "--collect",
                    "-p", f"MemoryMax={lim}M", "-p", "MemorySwapMax=0"] + argv

        def pre():
            os.setsid()
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
                p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                     stderr=subprocess.STDOUT, preexec_fn=pre)
        except OSError as e:
            self.finish_fail(j, "failed", f"spawn error: {e}")
            return False
        self.popen[j["id"]] = p
        self.c.execute("UPDATE jobs SET state='running',pid=?,started=?,deadline=?,peak_mb=0,note=NULL WHERE id=?",
                       (p.pid, time.time(), time.time() + j["timeout_s"], j["id"]))
        return True

    def kill(self, j, sig=signal.SIGTERM):
        try:
            os.killpg(j["pid"], sig)
        except (ProcessLookupError, PermissionError, TypeError):
            pass
        if sig == signal.SIGTERM:  # escalate later via check(); give a hard kill after grace
            time.sleep(0.2)
            try:
                os.killpg(j["pid"], signal.SIGKILL)
            except (ProcessLookupError, PermissionError, TypeError):
                pass

    def check(self, j, rss, now, cfg):
        c = self.c
        p = self.popen.get(j["id"])
        if p:
            p.poll()
        rcf = os.path.join(jobdir(j["id"]), "rc")
        peak = max(j["peak_mb"], int(rss))
        if peak != j["peak_mb"]:
            c.execute("UPDATE jobs SET peak_mb=? WHERE id=?", (peak, j["id"]))
        if os.path.exists(rcf):
            try:
                rc = int(open(rcf).read().strip() or 1)
            except ValueError:
                rc = 1
            try:
                os.killpg(j["pid"], signal.SIGKILL)  # stragglers
            except (ProcessLookupError, PermissionError):
                pass
            self.popen.pop(j["id"], None)
            return self.finish(j, rc, peak)
        if not pid_alive(j["pid"]):
            self.popen.pop(j["id"], None)
            return self.finish(j, 137, peak, lost=True)
        if now > j["deadline"]:
            self.kill(j)
            return self.finish_fail(j, "timeout", f"exceeded --timeout {fdur(j['timeout_s'])}; raise --timeout or split the job", peak)
        if rss > j["mem_mb"] * cfg["mem_overrun"] + 1024:
            self.kill(j)
            new = int(rss * 1.3) + 1024
            if j["preempts"] < 2:  # one automatic re-queue with a corrected estimate
                c.execute("UPDATE jobs SET state='queued',pid=NULL,mem_mb=?,preempts=preempts+1,note=? WHERE id=?",
                          (new, f"killed at {fgb(rss)} > declared {fgb(j['mem_mb'])}; auto-requeued with --mem {fgb(new)}", j["id"]))
            else:
                self.finish_fail(j, "oom", f"RSS {fgb(rss)} exceeded declared {fgb(j['mem_mb'])}; resubmit with --mem {fgb(new)}", peak)

    def finish(self, j, rc, peak, lost=False):
        if rc == 0 and not lost:
            self.c.execute("UPDATE jobs SET state='ok',rc=0,finished=?,pid=NULL WHERE id=?", (time.time(), j["id"]))
            drop_worktree(j)
            return
        note = "daemon lost the job's process" if lost else f"rc={rc}" + (" (SIGKILL: likely memory-cgroup OOM, raise --mem)" if rc == 137 else "")
        self.finish_fail(j, "lost" if lost else "failed", note, peak, rc)

    def finish_fail(self, j, state, note, peak=None, rc=None):
        c = self.c
        peak = peak if peak is not None else j["peak_mb"]
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


def daemon_status():
    try:
        with open(BEAT) as f:
            b = json.load(f)
        if time.time() - b["ts"] < 15 and pid_alive(b["pid"]):
            return b
    except (OSError, ValueError, KeyError):
        pass
    return None


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
    if a.batch:
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
    for i, cmd in enumerate(cmds):
        cur = c.execute(
            "INSERT INTO jobs(owner,name,tag,cmd,cwd,env,cpus,mem_mb,timeout_s,prio,state,retries_left,submitted,root,branch,sha,rel,links)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,'queued',?,?,?,?,?,?,?)",
            (owner, a.name or (None if len(cmds) > 1 else None), a.tag, cmd, os.path.abspath(a.cwd or os.getcwd()),
             json.dumps(env), a.cpus, int(parse_size(a.mem) / (1 << 20)), parse_dur(a.timeout), a.prio, a.retries, now,
             snap["root"], snap["branch"], snap["sha"], snap["rel"], json.dumps(a.link or [])))
        ids.append(cur.lastrowid)
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
              f"mem avail {s['avail'] / 1024:.0f}/{s['mem_total'] / 1024:.0f}G (ours {s['ours_rss'] / 1024:.0f}G rss +{s['unrealized'] / 1024:.0f}G reserved, keep-free {s['reserve_mem'] / 1024:.0f}G)")
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
        c.execute("UPDATE jobs SET state='queued',attempt=attempt+1,preempts=0,mem_mb=?,timeout_s=?,cpus=?,pid=NULL,rc=NULL,"
                  "started=NULL,finished=NULL,note=NULL,submitted=?,retries_left=? WHERE id=?",
                  (mem, parse_dur(a.timeout) if a.timeout else j["timeout_s"], a.cpus or j["cpus"], time.time(), a.retries, j["id"]))
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
            try:
                os.killpg(j["pid"], signal.SIGKILL)
            except (ProcessLookupError, PermissionError, TypeError):
                pass
    c.commit()
    print(f"cancelled {len(rows)} job(s)")


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
    print(f"threads={cfg['threads']} reserve_cpu={cfg['reserve_cpu']} | mem {meminfo()['MemTotal'] // 1024}G reserve {cfg['reserve_mem_gb']}G")


def cmd_install_service(a):
    d = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(d, exist_ok=True)
    unit = f"[Unit]\nDescription=kaeq job queue daemon\n\n[Service]\nExecStart={sys.executable} {os.path.abspath(__file__)} daemon\nRestart=always\nRestartSec=5\nKillMode=process\n\n[Install]\nWantedBy=default.target\n"
    open(os.path.join(d, "kaeq.service"), "w").write(unit)
    print("wrote kaeq.service. Run: systemctl --user daemon-reload && systemctl --user enable --now kaeq && loginctl enable-linger $USER")


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
    s.add_argument("--timeout", default="1h")
    s.add_argument("--prio", type=int, default=0, help="higher runs first")
    s.add_argument("--retries", type=int, default=0, help="auto-retry on failure (not for deterministic test failures)")
    s.add_argument("--name"), s.add_argument("--tag"), s.add_argument("--cwd")
    s.add_argument("--env", action="append", metavar="K=V")
    s.add_argument("--batch", metavar="FILE", help="'-' for stdin")
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
    s.add_argument("--mem"), s.add_argument("--cpus", type=float), s.add_argument("--timeout")
    s.add_argument("--retries", type=int, default=0)
    s.set_defaults(f=cmd_retry)

    s = sub.add_parser("cancel", help="cancel queued/running jobs by id, --owner or --tag")
    s.add_argument("ids", nargs="*"), owner_opt(s), s.add_argument("--tag")
    s.set_defaults(f=cmd_cancel)

    s = sub.add_parser("config", help="show / set limits: --set reserve_cpu=24 --set reserve_mem_gb=48")
    s.add_argument("--set", action="append")
    s.set_defaults(f=cmd_config)

    for name, f, h in (("doctor", cmd_doctor, "check isolation features"), ("down", cmd_down, "stop daemon"),
                       ("install-service", cmd_install_service, "write a systemd --user unit"),
                       ("daemon", lambda a: Daemon().run(), "run the scheduler in the foreground")):
        sub.add_parser(name, help=h).set_defaults(f=f)
    a = p.parse_args(argv)
    if getattr(a, "command", None) and a.command[:1] == ["--"]:
        a.command = a.command[1:]
    a.f(a)


if __name__ == "__main__":
    main()
