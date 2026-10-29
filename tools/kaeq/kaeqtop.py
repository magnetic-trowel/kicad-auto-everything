#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kaeqtop: a live, text-only view of the kaeq queue for a terminal (works over SSH).

Shows the machine's CPU and memory as the scheduler sees them, what the next job is waiting for,
and per owner (experiment/session): priority, running jobs, CPU and RAM in use, memory set aside,
queued and finished counts, progress, throughput and an ETA if the current rate holds.

  kaeqtop                 refresh every 5 s (Ctrl-C quits)
  kaeqtop -n 2 --jobs 30  faster, and list more running jobs
  kaeqtop --once          print one frame and exit
  kaeqtop --all           also owners with nothing queued or finished lately
Read-only: it never changes the queue. Run it on the machine the daemon runs on.
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import kaeq  # noqa: E402  (same folder: paths, config and the scheduler's own accounting)

DONE = ("ok", "failed", "timeout", "oom", "lost")
BAD = ("failed", "timeout", "oom", "lost")
TICK_HZ = os.sysconf("SC_CLK_TCK")


def bar(frac, width):
    frac = max(0.0, min(1.0, frac))
    n = int(round(frac * width))
    return "[" + "#" * n + "." * (width - n) + "]"


def gb(mb):
    return f"{mb / 1024:.1f}G" if mb < 100 * 1024 else f"{mb / 1024:.0f}G"


def dur(s):
    if s is None:
        return "-"
    s = int(s)
    if s < 120:
        return f"{s}s"
    if s < 2 * 3600:
        return f"{s // 60}m"
    if s < 2 * 86400:
        return f"{s // 3600}h{(s % 3600) // 60:02d}m"
    return f"{s // 86400}d{(s % 86400) // 3600}h"


def eta_clock(secs, now):
    t = time.localtime(now + secs)
    same_day = time.localtime(now)[:3] == t[:3]
    return time.strftime("%H:%M" if same_day else "%a %H:%M", t)


class Sampler:
    """CPU use per job from the change in its processes' CPU ticks between frames."""

    def __init__(self):
        self.prev = {}
        self.cgroups = {}

    def sample(self, running):
        sessions, per_pid = kaeq.proc_by_session()
        now = time.time()
        out = {}
        for j in running:
            rss, ticks = kaeq.job_usage(j, sessions, per_pid, self.cgroups)
            pt, pticks = self.prev.get(j["id"], (None, None))
            cores = None
            if pt is not None and now > pt:
                cores = max(0.0, (ticks - pticks) / TICK_HZ / (now - pt))
            self.prev[j["id"]] = (now, ticks)
            out[j["id"]] = (rss, cores)
        return out


def frame(c, cfg, sampler, args, width):
    now = time.time()
    L = []
    try:
        with open(kaeq.BEAT) as f:
            beat = json.load(f)
        bsys, bage = beat.get("sys", {}), now - beat.get("ts", 0)
        dstate = f"daemon pid {beat.get('pid')}, last tick {dur(bage)} ago" + ("  << NOT TICKING" if bage > 30 else "")
    except (OSError, ValueError):
        bsys, dstate = {}, "daemon heartbeat missing  << is kaeq running?"
    running = c.execute("SELECT * FROM jobs WHERE state='running'").fetchall()
    use = sampler.sample(running)

    L.append(f"kaeqtop  {kaeq.HOST}  {time.strftime('%Y-%m-%d %H:%M:%S')}   {dstate}")
    L.append("")
    # machine, as the scheduler sees it
    threads = bsys.get("threads") or cfg["threads"]
    ours_cpu, others = bsys.get("ours_cpu", 0.0), bsys.get("others", 0.0)
    pinned, rcpu = bsys.get("pinned") or threads, bsys.get("reserve_cpu", cfg["reserve_cpu"])
    bw = max(10, min(40, width - 90))
    L.append(f"CPU  {bar((ours_cpu + others) / threads, bw)} {ours_cpu + others:5.1f}/{threads} threads busy: "
             f"queue jobs {ours_cpu:.1f}, everything else {others:.1f} | jobs may use {pinned} CPUs, {rcpu} kept free")
    mi = kaeq.meminfo()
    total, avail = mi["MemTotal"], bsys.get("avail", mi["MemAvailable"])
    ours_rss, unreal = bsys.get("ours_rss", 0.0), bsys.get("unrealized", 0.0)
    rmem = bsys.get("reserve_mem", cfg["reserve_mem_gb"] * 1024)
    room = avail - unreal - rmem
    upeak = bsys.get("unrealized_peak", unreal)
    L.append(f"RAM  {bar((total - avail) / total, bw)} {gb(total - avail)}/{gb(total)} used: queue jobs {gb(ours_rss)} now, "
             f"{gb(unreal)} more set aside for their peaks | {gb(avail)} free, {gb(rmem)} kept free")
    if upeak > unreal + 512:
        L.append(f"     set aside {gb(unreal)} instead of {gb(upeak)} (all peaks at once): jobs rarely peak together"
                 f" (pooled owners marked *)")
    L.append(f"     room for new jobs: {gb(max(0, room))}  (free - set aside - kept free)"
             + ("   << memory is the limit" if room < 4096 else ""))
    if bsys.get("disk_cap"):
        L.append(f"Disk scratch {gb(bsys.get('disk', 0))}/{gb(bsys['disk_cap'])}"
                 f" (+{gb(bsys.get('disk_unrealized', 0))} declared, not used yet)")
    # what the next start waits for (the daemon's own order: priority, fewest running per owner, age)
    queued = c.execute("SELECT * FROM jobs WHERE state='queued' AND not_before<=?", (now,)).fetchall()
    per_owner = {}
    for j in running:
        per_owner[j["owner"]] = per_owner.get(j["owner"], 0) + 1
    if queued:
        queued.sort(key=lambda j: (-j["prio"], per_owner.get(j["owner"], 0), j["submitted"]))
        h = queued[0]
        cpu_room = threads - rcpu - others - bsys.get("cpu_commit", ours_cpu)
        why = []
        if h["mem_mb"] > room:
            why.append(f"needs {gb(h['mem_mb'])} RAM, {gb(max(0, room))} free for jobs")
        if h["cpus"] > cpu_room:
            why.append(f"needs {h['cpus']:g} CPUs, {max(0, cpu_room):.0f} free")
        starving = now - h["submitted"] > cfg["starve_after_s"]
        L.append(f"Next: #{h['id']} {h['owner']} prio {h['prio']} ({h['name'] or h['cmd'][:40]})")
        L.append("      " + ("; ".join(why) + (" -> room is held for it; only short jobs may backfill" if starving else "")
                             if why else "fits now: starts within a tick or two"))
    L.append("")

    # per owner
    since = now - 24 * 3600
    rows = {}
    for o, st, n in c.execute("SELECT owner,state,COUNT(*) FROM jobs GROUP BY owner,state"):
        rows.setdefault(o, {})[st] = n
    rate = {}
    for hrs in (1, 3, 24):
        for o, n in c.execute(f"SELECT owner,COUNT(*) FROM jobs WHERE state IN ({','.join('?' * len(DONE))}) "
                              "AND finished>? GROUP BY owner", (*DONE, now - hrs * 3600)):
            rate.setdefault(o, {})[hrs] = n
    prios = {}
    for o, p in c.execute("SELECT DISTINCT owner,prio FROM jobs WHERE state IN ('queued','running')"):
        prios.setdefault(o, set()).add(p)
    aside = {}
    for j in running:
        rss = use.get(j["id"], (0.0, None))[0]
        peak = max(j["peak_mb"] or 0, rss)
        expect = j["mem_mb"] if now - (j["started"] or now) < cfg["warmup_s"] else peak * cfg["peak_margin"]
        aside[j["owner"]] = aside.get(j["owner"], 0.0) + max(0.0, expect - rss)
    owners = [o for o, s in rows.items()
              if args.all or s.get("queued") or s.get("running") or rate.get(o, {}).get(3)]
    owners.sort(key=lambda o: (-max(prios.get(o, {-99})), -(rows[o].get("running", 0)), o))
    pooled = set(bsys.get("pooled_owners") or [])
    pw = max(10, min(20, width - 120))
    ow = max(12, min(26, max([len(o) for o in owners] + [5])))
    L.append(f"{'OWNER':<{ow}} PRIO RUN  CPU   RAM  ASIDE  QUEUED   DONE  FAIL  {'PROGRESS':<{pw + 7}} DONE/h 1h  3h   ETA (at 3h rate)")
    tot_run = tot_q = 0
    for o in owners:
        s = rows[o]
        run, q = s.get("running", 0), s.get("queued", 0)
        done, bad = sum(s.get(k, 0) for k in DONE), sum(s.get(k, 0) for k in BAD)
        tot_run, tot_q = tot_run + run, tot_q + q
        cpu = sum((use.get(j["id"], (0, 0))[1] or 0) for j in running if j["owner"] == o)
        ram = sum(use.get(j["id"], (0, 0))[0] for j in running if j["owner"] == o)
        frac = done / (done + run + q) if done + run + q else 1.0
        r1, r3 = rate.get(o, {}).get(1, 0), rate.get(o, {}).get(3, 0)
        left = run + q
        if not left:
            eta = "finished"
        elif r3:
            secs = left / (r3 / 3) * 3600
            eta = f"{dur(secs)}  ({eta_clock(secs, now)})"
        else:
            eta = "stalled" if run == 0 else "no finishes in 3h"
        pr = ",".join(str(p) for p in sorted(prios.get(o, []), reverse=True)) or "-"
        name = (o[:ow - 1] + "*") if o in pooled else o[:ow]
        L.append(f"{name:<{ow}} {pr:>4} {run:>3} {cpu:5.1f} {gb(ram):>5} {gb(aside.get(o, 0)):>5} {q:>7} {done:>6} {bad:>5}  "
                 f"{bar(frac, pw)} {frac * 100:3.0f}%  {r1:>5} {r3 / 3:5.0f}   {eta}")
    L.append(f"{'total':<{ow}}      {tot_run:>3} {sum((u[1] or 0) for u in use.values()):5.1f} "
             f"{gb(sum(u[0] for u in use.values())):>5} {gb(sum(aside.values())):>5} {tot_q:>7}")
    L.append("  RUN/CPU/RAM: jobs running now and what they use.  ASIDE: their worst case (every job at its peak);"
             " * = pooled: the queue sets aside less, from how its jobs' memory rises and falls")
    L.append("  DONE/FAIL: finished (FAIL = failed, timeout, oom or lost).  DONE/h: finishes in the last hour, and per hour over 3 h.")

    # problems in the last 24 h
    probs = c.execute(f"SELECT owner,state,COUNT(*) n FROM jobs WHERE state IN ({','.join('?' * len(BAD))}) AND finished>? "
                      "GROUP BY owner,state ORDER BY n DESC", (*BAD, since)).fetchall()
    if probs:
        L.append("")
        L.append("Problems in the last 24 h: " + ", ".join(f"{o} {n} {st}" for o, st, n in probs)
                 + "   (details: kaeq result --owner OWNER)")

    # running jobs
    if args.jobs and running:
        L.append("")
        L.append(f"RUNNING JOBS (top {min(args.jobs, len(running))} of {len(running)} by CPU)")
        L.append(f"  {'ID':>6} {'OWNER':<{ow}} {'CPU':>5} {'RAM':>6}/{'DECL':<6} {'TIME':>7} {'LIMIT':>7}  NAME")
        order = sorted(running, key=lambda j: -(use.get(j["id"], (0, 0))[1] or 0))
        for j in order[:args.jobs]:
            rss, cores = use.get(j["id"], (0.0, None))
            el = now - (j["started"] or now)
            cpu = "  -  " if cores is None else f"{cores:5.1f}"
            L.append(f"  {j['id']:>6} {j['owner'][:ow]:<{ow}} {cpu} {gb(rss):>6}/{gb(j['mem_mb']):<6} {dur(el):>7} "
                     f"{dur(j['timeout_s']):>7}  {j['name'] or j['cmd'][:60]}")
    return [line[:width] for line in L]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-n", "--interval", type=float, default=5.0, help="seconds between refreshes (default 5)")
    ap.add_argument("--jobs", type=int, default=15, help="running jobs to list (0 = none)")
    ap.add_argument("--all", action="store_true", help="also owners with nothing active or finished in 3 h")
    ap.add_argument("--once", action="store_true", help="print one frame and exit")
    args = ap.parse_args()
    if not os.path.exists(kaeq.DB):
        sys.exit(f"no queue database at {kaeq.DB}: run this on the machine the kaeq daemon runs on")
    c = sqlite3.connect(f"file:{kaeq.DB}?mode=ro", uri=True, timeout=10)
    c.row_factory = sqlite3.Row
    sampler = Sampler()
    sampler.sample(c.execute("SELECT * FROM jobs WHERE state='running'").fetchall())
    time.sleep(1.0)  # a first CPU sample, so the first frame already has rates
    try:
        while True:
            cfg = kaeq.config()
            width = shutil.get_terminal_size((160, 50)).columns or 160
            try:
                lines = frame(c, cfg, sampler, args, width)
            except sqlite3.OperationalError as e:  # the daemon briefly holds a write lock
                lines = [f"kaeqtop: database busy ({e}); retrying"]
            if args.once:
                print("\n".join(lines))
                return
            sys.stdout.write("\033[H" + "".join(line + "\033[K\n" for line in lines) + "\033[J")
            sys.stdout.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
