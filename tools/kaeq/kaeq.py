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
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # kaeqlib sits next to this file
from kaeqlib.consts import GB, MEM_BINS, TICK  # noqa: E402
from kaeqlib.units import parse_cpus, parse_size, parse_dur, fgb, fdur, frozen_for, active_for, times  # noqa: E402
from kaeqlib.leases import expected_size, keep_flags, mem_hist, pooled_headroom, max_rise, pearson, owner_correlation, warm_headroom, lease_plan, adapt_z, adapt_hold  # noqa: E402
from kaeqlib.cpu import quantile, adapt_runq_q, burst_fits  # noqa: E402
from kaeqlib.forecast import size_model, given_so_far, board_of, runtime_model, expected_durations, forecast_queue  # noqa: E402
from kaeqlib.host import Host, TICK_HZ, at_high, cg_anon_refaults, cg_freeze, cg_frozen, cg_high_mb, cg_mem, cg_mem_pressure, cg_pressure, cg_set_high, cg_swap_mb, compress, compress_room_mb, cpu_ticks, job_cgroup, job_cpus, job_usage, kill_tree, meminfo, pid_alive, proc_by_session, runnable_threads, set_unit_prop, shutil_which, uncompress, user_pressure  # noqa: E402,F401
from kaeqlib.store import ACTIVE, AUTO_DB, BEAT, CONF, DB, DB_BACKUP, DEFAULTS, DEPLOYED, ENV_KEEP, ERR_RE, HOME, HOST, LOCK, OVERCOMMIT, PROBLEM, RISE_HIST, SCHEMA, TRACES, USER, _on_nfs, _pinned_db, backup_db, close_trace, config, db, deployed, digest, dlog, drop_scratch, du_mb, event, jobdir, load_overcommit, load_rise_hist, pinned_host, rc_path, scratchdir, trace_path, write_trace  # noqa: E402,F401
from kaeqlib.gitsnap import drop_worktree, git, git_snapshot, ref  # noqa: E402,F401
from kaeqlib.daemon import Daemon, daemon_status, run_daemon, take_lock  # noqa: E402,F401


# ---------------------------------------------------------------- helpers


def default_owner():
    if os.environ.get("KAEQ_OWNER"):
        return os.environ["KAEQ_OWNER"]
    try:
        root = git(os.getcwd(), "rev-parse", "--show-toplevel")
        return f"{os.path.basename(root)}@{git(root, 'rev-parse', '--abbrev-ref', 'HEAD')}"
    except (RuntimeError, OSError):
        return f"{os.environ.get('USER', 'u')}-{os.path.basename(os.getcwd())}"


# ---------------------------------------------------------------- digest of a finished job


# ---------------------------------------------------------------- daemon


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
def qos(name):
    name = name or config()["default_class"]
    if name not in ("timed", "batch"):
        sys.exit(f"kaeq: --class is timed or batch, not {name!r}")
    return name


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
            "INSERT INTO jobs(owner,name,tag,cmd,cwd,env,cpus,mem_mb,timeout_s,prio,state,retries_left,submitted,root,branch,sha,rel,links,disk_mb,qos)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,'queued',?,?,?,?,?,?,?,?,?)",
            (owner, o.get("name") or a.name, a.tag, o["cmd"], os.path.abspath(a.cwd or os.getcwd()),
             json.dumps(env), float(o.get("cpus", a.cpus)), int(parse_size(o.get("mem", a.mem)) / (1 << 20)),
             parse_dur(o.get("timeout", a.timeout)), int(o.get("prio", a.prio)), a.retries, now + i * 1e-6,
             snap["root"], snap["branch"], snap["sha"], snap["rel"], json.dumps(a.link or []),
             int(parse_size(o.get("disk", a.disk)) / (1 << 20)), qos(o.get("class", a.qos))))
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
        lease = f" grant {fgb(j['grant_mb'])}" if j["grant_mb"] else ""
        cls = "batch" if j["qos"] == "batch" else "timed"
        z = j["id"] in ((d or {}).get("sys", {}).get("lease") or {}).get("compressed", [])
        print(f"{('FRZ*' if z else 'FRZN') if j['frozen_since'] else 'RUN '} #{j['id']} {j['owner']} {cls} {times(j, now)} {fgb(j['peak_mb'])}/{fgb(j['mem_mb'])}"
              f"{lease} {j['cpus']:g}c {j['name'] or j['cmd'][:50]}")
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
    """Block until a problem or 'all done'. Exit 1 = problems, 0 = all done, 2 = timeout (call again),
    3 = only health warnings about running jobs (read them, then call again)."""
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
            # 1: problems; 3: only health warnings (jobs still run: look, then wait again); 0: all done
            sys.exit(1 if any(r["kind"] in PROBLEM for r in rows) else 3 if all(r["kind"] == "health" for r in rows) else 0)
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
        print(f"#{j['id']} {j['state'].upper()} rc={j['rc']} {times(j)} peak {fgb(j['peak_mb'])}/{fgb(j['mem_mb'])} {j['cpus']:g}c attempt {j['attempt']} owner={j['owner']} code={ref(j)}")
        print(f"  cmd: {j['cmd'][:300]}\n  cwd: {j['cwd']}" + (f"\n  note: {j['note']}" if j["note"] else ""))
        print("\n".join(digest(j["id"], tail=a.tail)) + f"\n  log: {os.path.join(jobdir(j['id']), 'log')}")


def cmd_usage(a):
    """Per owner, over jobs running or finished within --since: how long they ran (active: what --timeout counts),
    how long they waited frozen for memory and how often, the CPU they used (and as a share of the CPUs they
    declared while active), what thrown-away attempts (preempted, requeued, retried) had used, and how long some
    / all of their runnable threads waited for a CPU (cpu.pressure: time contention took from their budgets)."""
    c = db()
    now = time.time()
    since = now - parse_dur(a.since)
    q = "SELECT * FROM jobs WHERE started IS NOT NULL AND (state='running' OR finished>=?)"
    args = [since]
    if a.owner:
        q, args = q + " AND owner=?", args + [a.owner]
    if a.tag:
        q, args = q + " AND tag=?", args + [a.tag]
    rows = {}
    for j in c.execute(q, args):
        r = rows.setdefault(j["owner"], [0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        act = active_for(j, now)
        for k, v in enumerate((1, act, frozen_for(j, now), j["freezes"], j["cpu_s"], act * j["cpus"],
                               j["lost_run_s"], j["lost_cpu_s"], j["cpu_wait_s"], j["cpu_stall_s"], j["squeezed_mb"])):
            r[k] += v
    if not rows:
        print(f"no jobs ran within {a.since}")
        return
    rows["TOTAL"] = [sum(r[k] for r in rows.values()) for k in range(11)] if len(rows) > 1 else None
    w = max(len(o) for o in rows)
    h = lambda s: f"{s / 3600:.1f}"
    print(f"{'OWNER':<{w}} {'JOBS':>5} {'ACTIVE_H':>8} {'FROZEN_H':>8} {'FROZEN%':>7} {'FREEZES':>7} {'CPU_H':>7} "
          f"{'CPU/DECL':>8} {'LOST_H':>6} {'LOST_CPU_H':>10} {'CPU_WAIT_H':>10} {'CPU_STALL_H':>11} {'SQUEEZED_GB':>11}")
    for o, r in sorted(rows.items(), key=lambda kv: (kv[0] == "TOTAL", kv[0])):
        if r is None:
            continue
        n, act, fz, nf, cpu, decl, lr, lc, cw, cs, sq = r
        print(f"{o:<{w}} {n:>5} {h(act):>8} {h(fz):>8} {100 * fz / max(1.0, act + fz):>6.1f}% {nf:>7} {h(cpu):>7} "
              f"{100 * cpu / max(1.0, decl):>7.0f}% {h(lr):>6} {h(lc):>10} {h(cw):>10} {h(cs):>11} {sq / 1024:>11.1f}")


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
                  "lost_run_s=lost_run_s+?,lost_cpu_s=lost_cpu_s+cpu_s,cpu_s=0,frozen_s=0,frozen_since=0,freezes=0,"
                  "started=NULL,finished=NULL,note=NULL,submitted=?,retries_left=?,disk_mb=? WHERE id=?",
                  (mem, parse_dur(a.timeout) if a.timeout else j["timeout_s"], a.cpus or j["cpus"], active_for(j, time.time()),
                   time.time(), a.retries, disk, j["id"]))
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
        now = time.time()      # (an open freeze ends with the job: its time goes into frozen_s)
        c.execute("UPDATE jobs SET state='cancelled',finished=?,note='cancelled',frozen_s=frozen_s+"
                  "CASE WHEN frozen_since>0 THEN ?-frozen_since ELSE 0 END,frozen_since=0 WHERE id=?", (now, now, j["id"]))
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


def cmd_class(a):
    """Set the class (timed/batch) of queued jobs; running ones keep theirs until they restart."""
    c = db()
    if not (a.ids or a.owner or a.tag):
        sys.exit("give job ids, --owner or --tag")
    n = 0
    for j in sel_jobs(c, a, ("queued",)):
        n += c.execute("UPDATE jobs SET qos=? WHERE id=? AND state='queued'", (a.qos, j["id"])).rowcount
    c.commit()
    print(f"set class {a.qos} on {n} queued job(s)")


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
    dep = deployed()
    print(f"{ok(dep.get('in_main') and not dep.get('dirty'))} deployed: "
          + (f"{dep.get('sha', '?')[:7]} ({dep.get('branch')}{', local changes' if dep.get('dirty') else ''}"
             f"{', in main' if dep.get('in_main') else ', NOT in main'}), installed "
             f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(dep.get('installed_at', 0)))}" if dep
             else "unknown (installed before install.sh recorded it)"))
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
            "Restart=always\nRestartSec=5\nKillMode=process\nNice=10\n\n[Install]\nWantedBy=default.target\n")
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
    s.add_argument("--class", dest="qos", default=None, choices=("timed", "batch"),
                   help="batch (default, config default_class): packed tight, may be paused (frozen, compressed). "
                        "timed: never paused, CPU priority: for timing, benchmark, optimization and speed work, "
                        "whose results depend on the time it gets")
    s.add_argument("--retries", type=int, default=0, help="auto-retry on failure (not for deterministic test failures)")
    s.add_argument("--name"), s.add_argument("--tag"), s.add_argument("--cwd")
    s.add_argument("--env", action="append", metavar="K=V")
    s.add_argument("--batch", metavar="FILE", help="'-' for stdin")
    s.add_argument("--jobs", metavar="FILE", help="JSONL, one job per line: {cmd, name, cpus, mem, disk, timeout, prio, class}; '-' for stdin")
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

    s = sub.add_parser("class", help="set the class (timed|batch) of queued jobs by id, --owner or --tag")
    s.add_argument("qos", choices=("timed", "batch")), s.add_argument("ids", nargs="*"), owner_opt(s), s.add_argument("--tag")
    s.set_defaults(f=cmd_class)

    s = sub.add_parser("usage", help="per owner: time active, frozen waiting for memory, CPU used, lost to requeues")
    owner_opt(s), s.add_argument("--tag"), s.add_argument("--since", default="24h", help="jobs running or finished within this (default 24h)")
    s.set_defaults(f=cmd_usage)

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
