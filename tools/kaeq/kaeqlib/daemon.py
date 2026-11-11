# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The scheduler daemon: one tick every TICK seconds admits, leases, freezes, measures and reports; the policy itself is in leases, cpu and forecast."""
import fcntl
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from .consts import GB, MEM_BINS, TICK
from .cpu import adapt_runq_q, burst_fits, quantile
from .gitsnap import drop_worktree, git, ref
from .host import Host, TICK_HZ, at_high, cg_anon_refaults, cg_freeze, cg_frozen, cg_high_mb, cg_mem, cg_mem_pressure, cg_pressure, cg_set_high, cg_swap_mb, compress, compress_room_mb, job_cgroup, job_cpus, job_usage, kill_tree, pid_alive, shutil_which, uncompress
from .leases import keep_flags, adapt_hold, adapt_z, lease_plan, max_rise, mem_hist, owner_correlation, pooled_headroom, warm_headroom
from .store import BEAT, CONF, DB, HOME, HOST, LOCK, OVERCOMMIT, RISE_HIST, backup_db, close_trace, config, db, deployed, digest, dlog, drop_scratch, du_mb, event, jobdir, load_overcommit, load_rise_hist, pinned_host, rc_path, scratchdir, write_trace
from .units import active_for, fdur, fgb, frozen_for, times


class Daemon:
    def __init__(self, host=None):
        self.host = host or Host()
        self.c = db()
        self.popen = {}          # id -> Popen (to reap zombies)
        self.others_ema = 0.0
        self.runq_ema = 0.0
        self.runq_hist, self.runq_q, self.runq_q_ts, self.runq_stats = [], None, time.time(), (0.0, 0.0)
        self.cpu_waiting = False     # a queued job waited for CPUs at the last admission
        self.prev = self.host.cpu_ticks()
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
        self.rho, self.rho_ts = {}, 0.0  # owner -> (measured correlation, pairs)
        self.ratios, self.ratios_ts = {}, 0.0  # owner -> p95 of peak / --mem
        self.ratio_samples = {}  # owner -> its jobs' peak / --mem, sorted
        self.organic = 0.0       # cumulative growth of running jobs' RSS (starts and finishes excluded)
        self.last_rss = {}
        self.rise_hist = load_rise_hist()  # [(t, organic)] every ~10 s
        if self.rise_hist:
            self.organic = self.rise_hist[-1][1]
        self.rise, self.rise_ts = None, 0.0
        # a job that ended while frozen (before cancel closed its freeze) still had frozen_since: close it now
        self.c.execute("UPDATE jobs SET frozen_s=frozen_s+MAX(0,COALESCE(finished,?)-frozen_since),frozen_since=0 "
                       "WHERE state!='running' AND frozen_since>0", (time.time(),))
        self.lease_st = {}       # job id -> {slack_since, stall_since, set, frozen_since, last, rate}: memory leases
        self.cpu_s, self.cpu_ts = {}, 0.0
        self.cpuj = {}           # job id -> CPU samples every 10 s: {t, cpu, some, full, rates: [(t, cores)], ...}
        self.timed_wait = 0.0    # share of time timed jobs had a thread waiting for a CPU (smoothed, ~30 s)
        self.cpu_freeze_ts, self.calm_since = 0.0, 0.0
        self.runq_class, self.runq_class_ts = {}, 0.0
        self.cpu_learn, self.cpu_learn_ts = {}, 0.0
        self.growth = []
        self.timed_preempt_ts = 0.0
        self.mem_stalled = set()     # jobs the last lease pass left waiting (frozen) for memory
        self.health_ts, self.health_first, self.health_said = 0.0, {}, {}   # health(): issues and when first seen
        self.started_at, self.last_timed_start = time.time(), time.time()
        self.squeezing, self.squeeze_ts, self.squeezed_add = None, 0.0, {}   # squeeze in flight; MB per job to record
        self.demoted, self.demote_ts = set(), 0.0   # jobs moved one CPU step down (heavy_boost)
        self.oc = load_overcommit()  # {hold, hist: [(t, done core-s, lost core-s)]}: the adaptive overcommit
        self.oc_t, self.oc_done, self.oc_lost, self.evict_ts = 0.0, 0.0, 0.0, 0.0
        if self.oc.get("hist"):
            _, self.oc_done, self.oc_lost = self.oc["hist"][-1]         # [(t, MB)]: how much running jobs together grew in each tick (last 10 minutes)  # job id -> CPU seconds of its current attempt (stored every minute)
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
        lease_on = cfg["mem_pool"] == "lease" and self.use_cgroup(cfg)
        sessions, per_pid = self.host.proc_by_session()
        now = time.time()
        running = c.execute("SELECT * FROM jobs WHERE state='running'").fetchall()
        ours_ticks, ours_rss, unrealized = 0, 0.0, 0.0
        usage = {j["id"]: job_usage(j, sessions, per_pid, self.cgroups) for j in running}
        for j in running:
            rss, ticks = usage[j["id"]]
            self.cpu_s[j["id"]] = max(self.cpu_s.get(j["id"], 0.0), ticks / TICK_HZ)
            ours_rss += rss
            ours_ticks += max(0, ticks - self.prev_ours.get(j["id"], ticks))
            self.prev_ours[j["id"]] = ticks
            tr = self.trace.setdefault(j["id"], [0.0, [], now])  # [last sample, samples, first sample]
            if now - tr[0] >= 10:
                tr[0] = now
                tr[1].append(rss)
            self.check(j, rss, now, cfg, self.disk.get(j["id"], 0.0), lease=lease_on and j["id"] in self.cgroups)
        self.sample_cpu(cfg, now, running, usage)
        for jid, mb in list(self.squeezed_add.items()):
            c.execute("UPDATE jobs SET squeezed_mb=squeezed_mb+? WHERE id=?", (mb, jid))
            del self.squeezed_add[jid]
        if now - self.cpu_ts >= 60:
            c.executemany("UPDATE jobs SET cpu_s=? WHERE id=? AND state='running'",
                          [(v, k) for k, v in self.cpu_s.items()])
            self.flush_cpu()
            self.cpu_ts = now
        # system sample
        busy, total = self.host.cpu_ticks()
        dt = max(1, total - self.prev[1])
        sys_threads = (busy - self.prev[0]) / dt * cfg["threads"]
        ours_threads = ours_ticks / dt * cfg["threads"]
        self.others_ema = 0.7 * self.others_ema + 0.3 * max(0.0, sys_threads - ours_threads)
        self.prev = (busy, total)
        # demand, not just use: when CPUs are saturated, use stops at capacity but threads keep queueing
        rq = self.host.runnable_threads()
        self.runq_ema = 0.8 * self.runq_ema + 0.2 * rq
        rq = max(0.0, rq - self.runq_class.get("idle", 0))      # idle-priority threads take only spare CPUs
        self.runq_hist.append((now, rq, self.cpu_waiting))     # the window behind batch CPU admission
        while self.runq_hist and self.runq_hist[0][0] < now - max(cfg["runq_window_s"], cfg["runq_adapt_s"]):
            self.runq_hist.pop(0)
        if now - self.runq_q_ts >= cfg["runq_adapt_s"]:
            pool = len(job_cpus(cfg) or ()) or cfg["threads"] - cfg["reserve_cpu"]
            new, over, idle = adapt_runq_q(self.runq_q or cfg["runq_q"], [(r, w) for _, r, w in self.runq_hist], pool, cfg)
            if self.runq_q and new != self.runq_q:
                dlog(f"cpu: admission quantile {self.runq_q:.2f} -> {new:.2f} (oversubscribed {over:.0%}, "
                     f"CPUs idle while jobs wait {idle:.0%})")
            self.runq_q, self.runq_q_ts, self.runq_stats = new, now, (over, idle)
        mi = self.host.meminfo()
        running = c.execute("SELECT * FROM jobs WHERE state='running'").fetchall()
        for jid in set(self.trace) - {j["id"] for j in running}:
            del self.trace[jid]
        profiles = self.owner_profiles(cfg, now, running)
        self.learn_ratios(cfg, now)
        if now - self.rho_ts >= 60:
            by = {}
            for j in running:
                if j["id"] in self.trace:
                    by.setdefault(j["owner"], []).append(self.trace[j["id"]][1])
            self.rho = {o: owner_correlation(v, cfg["mem_pool_rho"]) for o, v in by.items() if o in profiles}
            self.rho_ts = now
        # organic growth: RSS change of jobs past warm-up running both last tick and now (a warming-up job's
        # growth is covered by its own need, below; counting it here too would count it twice)
        cur = {j["id"]: usage[j["id"]][0] for j in running
               if j["id"] in usage and now - (j["started"] or now) >= cfg["warmup_s"]}
        self.organic += sum(r - self.last_rss[i] for i, r in cur.items() if i in self.last_rss)
        self.last_rss = cur
        if not self.rise_hist or now - self.rise_hist[-1][0] >= 10:
            self.rise_hist.append((now, self.organic))
            cut = now - cfg["mem_rise_history_s"]
            while self.rise_hist and self.rise_hist[0][0] < cut:
                self.rise_hist.pop(0)
        if now - self.rise_ts >= 60:
            span = self.rise_hist[-1][0] - self.rise_hist[0][0] if self.rise_hist else 0
            self.rise = max_rise(self.rise_hist, cfg["mem_rise_window_s"]) if span >= cfg["mem_rise_window_s"] else None
            self.rise_ts = now
        grow, warm_jobs, single = [], [], 0.0
        for j in running:
            # what a job may still grow into: its declared --mem while it warms up, then its observed peak
            # with a margin (a later phase may need more than the first); free memory is measured, not declared
            rss = usage.get(j["id"], (0.0, 0))[0]
            peak = max(j["peak_mb"] or 0, rss)
            warm = now - (j["started"] or now) < cfg["warmup_s"]
            prof = None if warm else profiles.get(j["owner"])
            expect = (self.need_mb(j, cfg) if warm else
                      peak * (cfg["mem_pool_margin"] if prof and cfg["mem_pool"] == "pooled" else cfg["peak_margin"]))
            grow.append((j["owner"], expect, rss, prof))
            if warm:
                warm_jobs.append((j, rss, max(0.0, expect - rss)))
            else:
                single = max(single, expect - rss)
        warm_need = warm_headroom([(rss, room, j["mem_mb"], self.ratio_samples.get(j["owner"]))
                                   for j, rss, room in warm_jobs], cfg["mem_pool_z"])
        unrealized, unrealized_peak = pooled_headroom(grow, cfg["mem_pool_z"], cfg["mem_pool_rho"],
                                                      {o: r for o, (r, _) in self.rho.items()})
        mode = cfg["mem_pool"]
        if mode == "lease" and not lease_on:
            mode = "measured (lease needs the cgroup memory controller)"
        if mode.startswith("measured") and self.rise is not None:
            unrealized = min(unrealized_peak, warm_need + max(single, self.rise * cfg["mem_rise_margin"]))
        elif mode.startswith("measured"):
            mode = "pooled (measuring: under 1 h of history)"
        elif mode not in ("pooled", "lease"):
            unrealized = unrealized_peak
        disk_unrealized = sum(max(0.0, j["disk_mb"] - self.disk.get(j["id"], 0.0)) for j in running)
        declared = max(1.0, sum(j["cpus"] for j in running))
        # declared CPUs while a job warms up, then what the fleet really uses (floor: 25% of declared)
        cpu_commit = sum(j["cpus"] if now - j["started"] < 20 else max(j["cpus"] * 0.25, ours_threads * j["cpus"] / declared)
                         for j in running)
        avail = mi["MemAvailable"]
        reserve = cfg["reserve_mem_gb"] * 1024
        lease = None
        if mode == "lease":
            lease = self.lease(cfg, now, running, usage, avail, reserve)
            unrealized = lease["held"]
            running = c.execute("SELECT * FROM jobs WHERE state='running'").fetchall()
            self.cpu_freeze(cfg, now, running)
        cap = cfg["scratch_gb"] * 1024
        pinned = job_cpus(cfg)
        self.sys = dict(threads=cfg["threads"], others=self.others_ema, ours_cpu=ours_threads, cpu_commit=cpu_commit,
                        mem_total=mi["MemTotal"], avail=avail, ours_rss=ours_rss, unrealized=unrealized,
                        unrealized_peak=unrealized_peak, pooled_owners=sorted(profiles),
                        runnable=self.runq_ema, runq_q=self.runq_q or cfg["runq_q"],
                        runq_qv=quantile([r for t, r, _ in self.runq_hist if t >= now - cfg["runq_window_s"]],
                                         self.runq_q or cfg["runq_q"]),
                        runq_over=self.runq_stats[0], runq_idle=self.runq_stats[1], runq_class=self.runq_class,
                        pool_rho={o: [round(r, 2), n] for o, (r, n) in self.rho.items()},
                        mem_ratio={o: round(q, 3) for o, q in self.ratios.items()},
                        mem_mode=mode, mem_rise=self.rise, mem_single=single, mem_warm=warm_need,
                        mem_hist_s=(self.rise_hist[-1][0] - self.rise_hist[0][0]) if self.rise_hist else 0,
                        reserve_cpu=cfg["reserve_cpu"], reserve_mem=reserve, running=len(running),
                        pinned=len(pinned) if pinned else None, disk=self.disk_total, disk_cap=cap,
                        disk_unrealized=disk_unrealized,
                        lease={k: v for k, v in (lease or {}).items() if k != "room"} or None)
        # emergency: free memory below emergency_frac of the reserve -> preempt newest job
        floor = max(reserve * cfg["emergency_frac"], cfg["emergency_floor_gb"] * 1024)
        if avail < floor and running:   # the newest batch job, else the newest
            v = max(running, key=lambda j: ((j["qos"] or "timed") != "timed", j["started"]))
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
        mem_room = avail - unrealized - reserve
        if lease is not None:   # running jobs waiting for memory come first: nothing starts meanwhile
            # a compressed job waiting to be thawed comes before any new job: nothing starts meanwhile
            mem_room = -1.0 if lease["stalled"] or lease["short"] or lease["compressed"] else lease["room"]
        self.admit(cfg, now, mem_room, cpu_commit, len(running), disk_room)
        self.idle_events(now)
        if now - self.last_backup > 300 and DB != os.path.join(HOME, "queue.db"):
            try:
                backup_db(c)
            except (OSError, sqlite3.Error):
                pass
            try:  # the measured growth history survives daemon restarts
                with open(RISE_HIST + ".tmp", "w") as f:
                    json.dump(self.rise_hist, f)
                os.replace(RISE_HIST + ".tmp", RISE_HIST)
            except OSError:
                pass
            self.last_backup = now
        try:
            self.health(cfg, now, c.execute("SELECT * FROM jobs WHERE state='running'").fetchall())
        except (OSError, sqlite3.Error) as e:
            dlog(f"health check failed: {e}")
        self.sys.setdefault("health", [])
        self.sys["deployed"] = deployed()
        tmp = f"{BEAT}.tmp{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump({"pid": os.getpid(), "ts": now, "sys": self.sys}, f)
        os.replace(tmp, BEAT)

    def demote_light(self, cfg, now, jobs):
        """heavy_boost: move every thread of jobs that are not memory-heavy (expected peak under keep_gb, past
        lease_warm_s) one CPU step down: timed to timed_nice + 1, batch to SCHED_IDLE. Re-applied every 30 s, for
        threads started since. Heavy jobs keep the step they started with (a priority cannot be raised again)."""
        self.demote_ts = now
        for j in jobs:
            if now - (j["started"] or now) < cfg.get("lease_warm_s", 120) or j["expect"] >= cfg["keep_gb"] * 1024:
                continue
            try:
                with open(os.path.join(j["cg"], "cgroup.threads")) as f:
                    tids = [int(x) for x in f.read().split()]
            except (OSError, ValueError):
                continue
            for t in tids:
                try:
                    if j["timed"]:
                        if os.getpriority(os.PRIO_PROCESS, t) < cfg["timed_nice"] + 1:
                            os.setpriority(os.PRIO_PROCESS, t, int(cfg["timed_nice"]) + 1)
                    elif os.sched_getscheduler(t) != os.SCHED_IDLE:
                        os.sched_setscheduler(t, os.SCHED_IDLE, os.sched_param(0))
                except OSError:
                    pass                          # the thread ended
            if j["id"] not in self.demoted:
                self.demoted.add(j["id"])
        self.demoted &= {j["id"] for j in jobs}

    def lease(self, cfg, now, running, usage, avail, reserve):
        """Grow, trim and enforce running jobs' memory grants (kaeq.lease_plan); requeue a victim if a job has
        waited lease_stall_s for memory nothing frees. Returns what the rest of the tick needs to know."""
        c = self.c
        jobs, cgs, other, fleet = [], {}, 0.0, 0.0
        for j in running:
            cg = self.cgroups.get(j["id"])
            if not cg or not os.path.isdir(cg):  # (a cached scope of an earlier attempt is gone: look it up again)
                cg = job_cgroup(j["pid"]) if j["pid"] else None
            m = cg_mem(cg) if cg else None
            if m is None:      # no scope (yet): what it declared and has not used yet stays set aside
                other += max(0.0, self.need_mb(j, cfg) - usage.get(j["id"], (0.0, 0))[0])
                continue
            self.cgroups[j["id"]] = cgs[j["id"]] = cg
            st = self.lease_st.get(j["id"])
            if st is None:     # new, or adopted from an earlier daemon: its freeze state is in the database (and
                               # in the scope itself, should an older daemon have left it frozen unrecorded)
                fs = j["frozen_since"] or (now if cg_frozen(cg) else 0.0)
                st = self.lease_st[j["id"]] = {"slack_since": 0.0, "stall_since": fs, "set": "unknown", "frozen_since": fs,
                                               "last": (now, m[0]), "rate": 0.0}
                if fs and not j["frozen_since"]:
                    c.execute("UPDATE jobs SET frozen_since=?, freezes=freezes+1 WHERE id=?", (fs, j["id"]))
            swapped = cg_swap_mb(cg)       # (compressed, in zram) comes back as the job touches it; read from the
            if swapped > 0 and st.get("frozen_since"):   # scope, so a restarted daemon knows a compressed job
                st["compressed"] = st["was_compressed"] = True
            elif swapped > 0 and (j["qos"] or "timed") == "timed":   # running timed with pages in swap: squeezed
                st["squeezed"] = True
            st["max_use"] = max(st.get("max_use", 0.0), m[0] + swapped)
            t0, u0 = st["last"]
            grew = max(0.0, m[0] - u0)
            if now - (j["started"] or now) >= cfg.get("lease_warm_s", 120):
                fleet += m[0] - u0  # net: one job's fall offsets another's rise (young jobs are set aside in full)
            if now > t0:       # growth rate (MB/s), rises at once and decays slowly; a frozen job does not grow
                r = max(0.0, (m[0] - u0) / (now - t0))
                st["rate"] = r if r > st["rate"] else 0.9 * st["rate"] + 0.1 * r
            st["last"] = (now, m[0])
            g = j["grant_mb"] or max(self.need_mb(j, cfg), m[0] + 2 * cfg["lease_margin_mb"])  # adopted job: a first grant
            jobs.append(dict(id=j["id"], prio=j["prio"], started=j["started"], grant=float(g), use=m[0], declared=j["mem_mb"],
                             slack_since=st["slack_since"], stall_since=st["stall_since"], rate=st["rate"],
                             frozen=bool(st.get("frozen_since")), grew=grew, timed=(j["qos"] or "timed") == "timed",
                             waited_frozen=frozen_for(j, now) - st.get("wait_base", 0.0),
                             protected=j["preempts"] >= cfg["evict_protect_after"],
                             invest=active_for(j, now) * max(1.0, j["cpus"]),
                             compressed=bool(st.get("compressed") and st.get("frozen_since")),
                             mpress=0.0 if st.get("frozen_since") or not at_high(cg, st.get("set")) else cg_mem_pressure(cg),
                             swapped=0.0 if st.get("squeezed") else swapped,   # squeezed: cold, stays out
                             owner=j["owner"], expect=max(self.need_mb(j, cfg), st["max_use"]),
                             held_out=swapped if st.get("squeezed") else 0.0, cg=cg))
            jj = jobs[-1]
            if not jj["timed"]:
                st["dear"] = keep_flags(jj, cfg, now, st.get("no_freeze_until", 0.0), swapped)
        for jid in set(self.lease_st) - set(cgs):
            del self.lease_st[jid]
        if cfg["heavy_boost"] and now - self.demote_ts >= 30:
            self.demote_light(cfg, now, jobs)
        room = avail - reserve
        if cfg["mem_budget_gb"] > 0:
            used = sum(j["use"] for j in jobs) + sum(usage.get(j["id"], (0.0, 0))[0] for j in running if j["id"] not in cgs)
            room = min(room, cfg["mem_budget_gb"] * 1024 - used)
        self.growth.append((now, max(0.0, fleet)))   # the fleet's net growth per tick, for the buffer
        while self.growth and self.growth[0][0] < now - 600:
            self.growth.pop(0)
        buffer = max(cfg["lease_buffer_gb"] * 1024, cfg["lease_buffer_ticks"] * max(g for _, g in self.growth))
        # timed work done (core-s while running) and the adaptive share of timed grants set aside
        if self.oc_t:
            self.oc_done += sum(max(1.0, j["cpus"]) for j in running if (j["qos"] or "timed") == "timed") * (now - self.oc_t)
        self.oc_t = now
        hold = self.oc.get("hold", cfg["timed_hold_frac"]) if cfg["timed_hold_auto"] else cfg["timed_hold_frac"]
        z = self.oc.get("z", cfg["timed_z"])
        hist = self.oc.setdefault("hist", [])
        if not hist or now - hist[-1][0] >= cfg["overcommit_every_s"]:
            hist.append((now, self.oc_done, self.oc_lost))
            while hist and hist[0][0] < now - 2 * cfg["overcommit_window_s"]:
                hist.pop(0)
            if cfg["timed_hold_auto"]:
                new, loss = adapt_hold(hold, hist, cfg, now)
                if new != hold:
                    dlog(f"overcommit: timed grants set aside {hold:.0%} -> {new:.0%} (work lost to requeues "
                         f"{loss:.1%} of timed work, target {cfg['overcommit_loss_target']:.0%})")
                hold = self.oc["hold"] = new
                self.oc["loss"] = loss
            if cfg["timed_forecast"]:
                new, loss = adapt_z(z, hist, cfg, now)
                if new != z:
                    dlog(f"overcommit: timed forecast z {z:.2f} -> {new:.2f} (work lost to requeues "
                         f"{loss:.1%} of timed work, target {cfg['overcommit_loss_target']:.0%})")
                z = self.oc["z"] = new
                self.oc["loss"] = loss
            try:
                with open(OVERCOMMIT + ".tmp", "w") as f:
                    json.dump(self.oc, f)
                os.replace(OVERCOMMIT + ".tmp", OVERCOMMIT)
            except OSError:
                pass
        timed_held = None
        if cfg["timed_forecast"]:         # forecast growth of timed jobs past their warm-up, pooled (pooled_headroom)
            warm = cfg.get("lease_warm_s", 120)
            grow = [(j["owner"], j["expect"], j["use"] + j["held_out"],   # squeezed pages: used, not room to grow into
                     None if j.get("protected") else self.profiles.get(j["owner"]))
                    for j in jobs if j["timed"] and now - (j["started"] or now) >= warm]
            timed_held = pooled_headroom(grow, z, cfg["mem_pool_rho"], {o: r for o, (r, _) in self.rho.items()})[0]
        credit = 0.0
        if cfg["squeeze"] and cfg["squeeze_credit"] > 0:
            gain = 1 - 1 / max(1.0, cfg["zram_ratio"])
            steady = sum(j["use"] for j in jobs if j["timed"] and not j.get("frozen")
                         and now - (j["started"] or now) >= cfg.get("lease_warm_s", 120)
                         and not (self.lease_st.get(j["id"]) or {}).get("hot"))
            credit = min(cfg["squeeze_credit"] * steady, compress_room_mb(cfg["compress_frozen"])) * gain
        plan = lease_plan(jobs, room - other, dict(cfg, timed_hold_frac=hold), now, buffer, timed_held, credit, room)
        by = {j["id"]: j for j in running}
        for j in jobs:
            st, g = self.lease_st[j["id"]], int(plan["grants"][j["id"]])
            st["slack_since"], st["stall_since"] = plan["slack_since"][j["id"]], plan["stall_since"][j["id"]]
            if g != by[j["id"]]["grant_mb"]:
                c.execute("UPDATE jobs SET grant_mb=? WHERE id=?", (g, j["id"]))
                if by[j["id"]]["grant_mb"]:
                    dlog(f"lease #{j['id']}: {fgb(by[j['id']]['grant_mb'])} -> {fgb(g)} (uses {fgb(j['use'])})")
            # a timed job is never throttled (memory.high max): throttling would cost it time, like a freeze
            high = None if j.get("timed") or j.get("keep") else int(g + max(1024, cfg.get("lease_backstop_frac", 0.1) * g))
            if st["set"] == high and cg_high_mb(cgs[j["id"]]) != high:
                st["set"] = "reverted"           # changed behind kaeq's back (systemd re-applied a property): set again
            if st["set"] != high and cg_set_high(cgs[j["id"]], high):
                st["set"] = high
            # a job that needs memory nobody can give waits frozen (no pressure for systemd-oomd to kill it for);
            # its time frozen does not count towards its --timeout (active_for) and is recorded (frozen_s, freezes)
            wait = j["id"] in plan["stalled"]
            if wait and not st.get("frozen_since"):
                if cg_freeze(cgs[j["id"]], True):
                    st["frozen_since"] = now
                    self.compress_frozen(j["id"], cgs[j["id"]], j["use"], cfg)
                    c.execute("UPDATE jobs SET frozen_since=?, freezes=freezes+1 WHERE id=?", (now, j["id"]))
                    dlog(f"lease #{j['id']}: frozen at {fgb(j['use'])} (grant {fgb(g)}): no memory free")
            elif not wait and st.get("frozen_since") and not st.get("cpu_frozen"):   # (cpu_freeze thaws those)
                st["no_freeze_until"] = now + max(cfg["thaw_min_run_s"], cfg["thaw_min_frac"] * (now - st["frozen_since"]))
                if cg_freeze(cgs[j["id"]], False):
                    if st.pop("compressed", None):
                        uncompress(cgs[j["id"]])
                    self.thawed(j["id"], now)
        if plan["victim"] is not None:
            w = by[plan["waiter"]]          # its wait starts again: the next victim only after another lease_stall_s
            self.lease_st[w["id"]]["wait_base"] = frozen_for(w, now)
            v = by[plan["victim"]]
            need = max(v["mem_mb"], int(max(v["peak_mb"] or 0, v["grant_mb"] or 0) * 1.2))
            self.preempt(v, now, f"requeued: job(s) {plan['stalled']} waited {fdur(cfg['lease_stall_s'])} for memory "
                                 f"nothing freed; this job was {'the furthest past its --mem' if v['peak_mb'] > v['mem_mb'] else 'the newest'} "
                                 f"(restarts with --mem {fgb(need)})")
            c.execute("UPDATE jobs SET mem_mb=?, grant_mb=0 WHERE id=?", (need, v["id"]))
        self.mem_stalled = set(plan["stalled"])
        self.squeeze_one(cfg, now, jobs, room, buffer)
        ev = plan["evict"]
        if ev is not None and self.squeezing is not None and room >= buffer / 4:
            ev = None                    # a squeeze is under way: give it the time, unless free is under a quarter
        if ev is not None and now - self.evict_ts >= cfg["evict_every_s"]:
            self.evict_ts = now
            v = by[ev]
            self.oc_lost += active_for(v, now) * max(1.0, v["cpus"])
            self.preempt(v, now, f"requeued: memory ran short (free {fgb(room)} beyond the reserve, under half the "
                                 f"{fgb(buffer)} buffer); it lost the least work per GB freed and restarts from "
                                 f"scratch, so its results are unaffected")
            c.execute("UPDATE jobs SET grant_mb=0 WHERE id=?", (v["id"],))
        else:
            ev = None
        tv = plan["timed_victim"]
        if tv is not None and now - self.timed_preempt_ts >= cfg["timed_preempt_s"]:
            self.timed_preempt_ts = now
            v = by[tv]
            self.preempt(v, now, f"requeued: job(s) {plan['short']} kept running (timed, or expensive) needed memory "
                                 f"nobody could give; the least valuable frozen batch job makes room (it restarts later)")
            c.execute("UPDATE jobs SET grant_mb=0 WHERE id=?", (v["id"],))
        else:
            tv = None
        grants = {i: plan["grants"][i] for i in plan["grants"] if i not in (plan["victim"], tv, ev)}
        use = {j["id"]: j["use"] for j in jobs}
        return dict(room=plan["free"], credit=credit, held=other + plan["held"] + buffer, buffer=buffer,
                    unused=sum(max(0.0, g - use[i]) for i, g in grants.items()),
                    granted=sum(grants.values()), used=sum(use.values()), stalled=plan["stalled"],
                    victim=plan["victim"], short=plan["short"], jobs=len(jobs), hold=hold, z=z, loss=self.oc.get("loss"),
                    timed_held=timed_held, compressed=[j["id"] for j in jobs if j["compressed"]
                                                        and not (self.lease_st.get(j["id"]) or {}).get("cpu_frozen")])

    def squeeze_one(self, cfg, now, jobs, real_mb, buffer):
        """Free memory beyond the reserve is under the growth buffer: compress the coldest memory of the running
        timed job that has the most of it, while it keeps running (compress(running=True)). One at a time."""
        if not cfg["squeeze"] or real_mb >= buffer or self.squeezing or now - self.squeeze_ts < cfg["squeeze_every_s"]:
            return
        room = compress_room_mb(cfg["compress_frozen"])
        for j in jobs:                    # judge earlier squeezes: what came back was hot
            st = self.lease_st.get(j["id"]) or {}
            if st.get("squeeze_base") is not None and st.get("squeezed_total", 0) > 0:
                back = (cg_anon_refaults(j["cg"])[1] - st["squeeze_base"]) * 4 / 1024
                if back > 0.25 * st["squeezed_total"] and not st.get("hot"):
                    st["hot"] = True
                    dlog(f"#{j['id']}: hot ({fgb(back)} of {fgb(st['squeezed_total'])} squeezed came back): not squeezed again")
        cand = [(cg_anon_refaults(j["cg"])[0], j) for j in jobs if j["timed"] and not j.get("frozen")
                and not (self.lease_st.get(j["id"]) or {}).get("hot")]
        cand = [(anon, j) for anon, j in cand if anon >= cfg["squeeze_min_gb"] * 1024]
        if not cand or room < 256:
            return
        # the biggest of the jobs not growing fast (under 50 MB/s), else the biggest
        anon, j = max(cand, key=lambda x: (x[1].get("rate", 0.0) < 50.0, x[0]))
        cold = anon / 2
        mb = min(cold, room, max(1024.0, 2 * (buffer - real_mb)))
        self.squeezing, self.squeeze_ts = j["id"], now
        st = self.lease_st[j["id"]]
        st["squeezed"] = True
        if st.get("squeeze_base") is None:
            st["squeeze_base"] = cg_anon_refaults(j["cg"])[1]
        jid = j["id"]

        def done(got):
            self.squeezed_add[jid] = self.squeezed_add.get(jid, 0.0) + got
            st["squeezed_total"] = st.get("squeezed_total", 0.0) + got
            self.squeezing = None
        compress(j["cg"], mb, running=True, done=done, pressure=self.host.user_pressure)
        dlog(f"#{jid}: squeezing up to {fgb(mb)} of its {fgb(anon)} into zram while it runs "
             f"(free beyond the reserve {fgb(real_mb)} < buffer {fgb(buffer)})")

    def compress_frozen(self, jid, cg, use_mb, cfg):
        """A job was just frozen: compress its memory into zram (compress_frozen), so the freeze frees RAM."""
        room = compress_room_mb(cfg["compress_frozen"])
        if room < 256 or use_mb < 256:
            return
        st = self.lease_st.setdefault(jid, {})
        st["compressed"] = st["was_compressed"] = True
        compress(cg, min(use_mb, room), pressure=self.host.user_pressure)
        dlog(f"#{jid}: frozen; compressing up to {fgb(min(use_mb, room))} of its memory into swap")

    def sample_cpu(self, cfg, now, running, usage=None):
        """Every 10 s per job: cores used (cpu.stat) and seconds some / all of its threads waited for a CPU
        (cpu.pressure); the timed jobs' share of time spent waiting, smoothed. Each sample also goes to the job's
        trace (write_trace), the data the simulator (tools/kaeq/sim.py) replays."""
        live = {j["id"] for j in running}
        for jid in set(self.cpuj) - live:
            del self.cpuj[jid]
        wait, span = 0.0, 0.0
        for j in running:
            cg = self.cgroups.get(j["id"])
            pr = cg_pressure(cg) if cg else None
            if pr is None:
                continue
            cpu = self.cpu_s.get(j["id"], 0.0)
            st = self.cpuj.get(j["id"])
            if st is None:
                self.cpuj[j["id"]] = dict(t=now, cpu=cpu, some=pr[0], full=pr[1], rates=[], wait_s=0.0, stall_s=0.0,
                                          peak=0.0, timed=(j["qos"] or "timed") == "timed")
                continue
            dt = now - st["t"]
            if dt < 10:
                continue
            r = max(0.0, cpu - st["cpu"]) / dt
            dw, df = max(0.0, pr[0] - st["some"]), max(0.0, pr[1] - st["full"])
            st.update(t=now, cpu=cpu, some=pr[0], full=pr[1], peak=max(st["peak"], r))
            st["wait_s"] += dw
            st["stall_s"] += df
            st["starved_since"] = (st.get("starved_since") or now) if df / dt >= cfg["starve_full"] else 0.0
            m = cg_mem(cg)
            write_trace(j, now, rss=(usage or {}).get(j["id"], (0.0, 0))[0], use=m[0] if m else 0.0, cores=r,
                        wait=dw / dt, stall=df / dt, frozen=bool((self.lease_st.get(j["id"]) or {}).get("frozen_since")),
                        grant=j["grant_mb"] or 0)
            st["rates"].append((now, r))
            while st["rates"] and st["rates"][0][0] < now - cfg["cpu_window_s"]:
                st["rates"].pop(0)
            if st["timed"]:                       # "full": all its runnable threads waited (with "some", one
                wait, span = wait + df, span + dt   # thread of a multi-threaded job waiting counted, too touchy)
        if span:
            self.timed_wait = 0.7 * self.timed_wait + 0.3 * min(1.0, wait / span)
        elif not any((j["qos"] or "timed") == "timed" for j in running):
            self.timed_wait = 0.0    # no timed job runs, so none waits (span is also 0 between a running job's samples)
        if now - self.runq_class_ts >= 10:          # threads ready to run, by class and by scheduling policy
            self.runq_class_ts, self.runq_class = now, {"timed": 0, "batch": 0, "idle": 0}
            for j in running:
                cg = self.cgroups.get(j["id"])
                if not cg:
                    continue
                try:
                    tids = open(os.path.join(cg, "cgroup.threads")).read().split()
                except OSError:
                    continue
                n = idle = 0
                for t in tids:
                    try:
                        with open(f"/proc/{t}/stat") as f:
                            fs = f.read().rpartition(")")[2].split()
                        if fs[0] == "R":
                            n += 1
                            idle += fs[38] == "5"            # SCHED_IDLE
                    except (OSError, IndexError):
                        pass
                self.runq_class["timed" if (j["qos"] or "timed") == "timed" else "batch"] += n
                self.runq_class["idle"] += idle

    def flush_cpu(self, jid=None):
        rows = [(st["wait_s"], st["stall_s"], st["peak"], k) for k, st in self.cpuj.items() if jid in (None, k)]
        self.c.executemany("UPDATE jobs SET cpu_wait_s=?, cpu_stall_s=?, cpu_peak=? WHERE id=?", rows)

    def cpu_profile(self, j, cfg, now):
        """(mean, peak) cores a running timed job is expected to use: measured over cpu_window_s once it has a
        minute of samples, else what its owner's finished jobs used (else its --cpus)."""
        st = self.cpuj.get(j["id"])
        if st and len(st["rates"]) >= 6:
            rs = [r for _, r in st["rates"]]
            learned = self.learned_cpu(j, cfg, now)
            return sum(rs) / len(rs), max(max(rs), learned[1] if learned[2] else max(rs))
        m, p, _ = self.learned_cpu(j, cfg, now)
        return m, p

    def learned_cpu(self, j, cfg, now):
        """(mean, peak, learned?) cores of an owner's finished timed jobs: median of mean use (cpu_s over active
        time), p90 of their peak; --cpus for both until 5 have finished."""
        if now - self.cpu_learn_ts >= 300:
            self.cpu_learn, self.cpu_learn_ts = {}, now
        o = j["owner"]
        if o not in self.cpu_learn:
            rows = self.c.execute(
                "SELECT cpu_s, finished-started-frozen_s AS act, cpu_peak FROM jobs WHERE owner=? AND state='ok' "
                "AND cpu_peak>0 AND finished-started-frozen_s>30 ORDER BY finished DESC LIMIT 50", (o,)).fetchall()
            if len(rows) >= 5:
                means = sorted(r["cpu_s"] / r["act"] for r in rows)
                peaks = sorted(r["cpu_peak"] for r in rows)
                self.cpu_learn[o] = (means[len(means) // 2], peaks[int(0.9 * (len(peaks) - 1))])
            else:
                self.cpu_learn[o] = None
        got = self.cpu_learn[o]
        return (got[0], max(got), True) if got else (float(j["cpus"]), float(j["cpus"]), False)

    def timed_cpu_fits(self, j, cfg, now, running):
        """Whether timed job j may start: timed jobs' measured use with pooled bursts, plus j's expected use, fit
        in the CPUs jobs may use beside other users' load, and timed jobs are not already waiting for CPUs."""
        if self.timed_wait >= cfg["timed_wait_start"]:
            return False
        pool = job_cpus(cfg)
        cap = (len(pool) if pool else cfg["threads"] - cfg["reserve_cpu"]) - self.others_ema
        timed = [self.cpu_profile(r, cfg, now) for r in running if (r["qos"] or "timed") == "timed"]
        m, p, _ = self.learned_cpu(j, cfg, now)
        return burst_fits(timed, (m, p), cap)

    def cpu_freeze(self, cfg, now, running):
        """Timed jobs waiting for CPUs (timed_wait above timed_wait_freeze): freeze the newest running batch job,
        one per cpu_freeze_every_s; once it has stayed below timed_wait_thaw that long, thaw the oldest again.
        Batch jobs are SCHED_IDLE already; this is for the CPU time they still take from timed jobs."""
        batch = [j for j in running if j["qos"] == "batch" and j["id"] in self.cgroups]
        if now - self.cpu_freeze_ts < cfg["cpu_freeze_every_s"]:
            return
        pool = len(job_cpus(cfg) or ()) or cfg["threads"] - cfg["reserve_cpu"]
        qv = quantile([r for t, r, _ in self.runq_hist if t >= now - cfg["runq_window_s"]] or [self.runq_ema],
                      self.runq_q or cfg["runq_q"])
        # starved batch jobs: frozen and compressed (they hardly progress, but hold their memory)
        starved = [j for j in batch if not (self.lease_st.get(j["id"]) or {}).get("frozen_since")
                   and not (self.lease_st.get(j["id"]) or {}).get("dear")
                   and (self.lease_st.get(j["id"]) or {}).get("no_freeze_until", 0.0) <= now
                   and (self.cpuj.get(j["id"]) or {}).get("starved_since")
                   and now - self.cpuj[j["id"]]["starved_since"] >= cfg["starve_s"]]
        if starved:
            v = min(starved, key=lambda j: self.cpuj[j["id"]]["starved_since"])
            if cg_freeze(self.cgroups[v["id"]], True):
                st = self.lease_st.setdefault(v["id"], {"slack_since": 0.0, "stall_since": 0.0, "set": None,
                                                        "last": (now, 0.0), "rate": 0.0})
                st["frozen_since"], st["cpu_frozen"] = now, True
                m = cg_mem(self.cgroups[v["id"]])
                if m:
                    self.compress_frozen(v["id"], self.cgroups[v["id"]], m[0], cfg)
                self.c.execute("UPDATE jobs SET frozen_since=?, freezes=freezes+1 WHERE id=?", (now, v["id"]))
                dlog(f"cpu: batch #{v['id']} starved of CPU {fdur(now - self.cpuj[v['id']]['starved_since'])}: frozen "
                     f"and compressed until the run queue has room for it")
                self.cpuj[v["id"]]["starved_since"] = 0.0
                self.cpu_freeze_ts = now
                return
        if self.timed_wait > cfg["timed_wait_freeze"]:
            self.calm_since = 0.0
            free = [j for j in batch if not (self.lease_st.get(j["id"]) or {}).get("frozen_since")
                    and not (self.lease_st.get(j["id"]) or {}).get("dear")
                    and (self.lease_st.get(j["id"]) or {}).get("no_freeze_until", 0.0) <= now]
            if free:                      # the newest of the cheap ones (expensive jobs run on)
                v = max(free, key=lambda j: j["started"])
                if cg_freeze(self.cgroups[v["id"]], True):
                    st = self.lease_st.setdefault(v["id"], {"slack_since": 0.0, "stall_since": 0.0, "set": None,
                                                            "last": (now, 0.0), "rate": 0.0})
                    st["frozen_since"], st["cpu_frozen"] = now, True
                    m = cg_mem(self.cgroups[v["id"]])
                    if m:
                        self.compress_frozen(v["id"], self.cgroups[v["id"]], m[0], cfg)
                    self.c.execute("UPDATE jobs SET frozen_since=?, freezes=freezes+1 WHERE id=?", (now, v["id"]))
                    dlog(f"cpu: batch #{v['id']} frozen: timed jobs waited for CPUs {self.timed_wait:.0%} of the time")
                    self.cpu_freeze_ts = now
            return
        if self.timed_wait < cfg["timed_wait_thaw"]:
            self.calm_since = self.calm_since or now
            # thawed only when the run queue (as batch admission sees it) has room for its CPUs
            held = [j for j in batch if (self.lease_st.get(j["id"]) or {}).get("cpu_frozen") and qv + j["cpus"] <= pool]
            if held and now - self.calm_since >= cfg["cpu_freeze_every_s"]:
                v = min(held, key=lambda j: j["started"])
                st = self.lease_st[v["id"]]
                st["cpu_frozen"] = False
                if v["id"] not in self.mem_stalled:          # else it stays frozen, now waiting for memory
                    st["no_freeze_until"] = now + max(cfg["thaw_min_run_s"],
                                                      cfg["thaw_min_frac"] * (now - (st.get("frozen_since") or now)))
                    self.thawed(v["id"], now)
                    cg_freeze(self.cgroups[v["id"]], False)
                    if st.pop("compressed", None):
                        uncompress(self.cgroups[v["id"]])
                self.cpu_freeze_ts = now
        else:
            self.calm_since = 0.0

    def health(self, cfg, now, running):
        """Every 60 s: look for kaeq's own failure symptoms; report each issue once it has lasted its threshold,
        at most once an hour (log, sys["health"] for kaeqtop, a "health" event to the job's owner)."""
        if now - self.health_ts < 60:
            return
        self.health_ts = now
        seen, out = {}, []
        lease_on = cfg["mem_pool"] == "lease" and self.use_cgroup(cfg)

        def issue(key, j, msg, after=0.0):
            first = self.health_first.get(key) or now
            seen[key] = first
            if now - first < after:
                return
            out.append(msg)
            if now - self.health_said.get(key, 0.0) >= 3600:
                self.health_said[key] = now
                dlog(f"health: {msg}")
                if j is not None:
                    event(self.c, j, "health", f"#{j['id']} {msg} | {j['name'] or j['cmd'][:60]}")
        for j in running:
            cg = self.cgroups.get(j["id"])
            st = self.lease_st.get(j["id"]) or {}
            if lease_on and now - (j["started"] or now) > 120 and (not cg or not os.path.isdir(cg) or cg_mem(cg) is None):
                issue(("nocg", j["id"]), j, f"runs without a readable cgroup: kaeq cannot see or lease its memory",
                      cfg["health_after_s"])
                continue
            if j["frozen_since"] and now - j["frozen_since"] > cfg["health_frozen_s"]:
                issue(("frozen", j["id"]), j, f"frozen {fdur(now - j['frozen_since'])}"
                      + (" (for CPU)" if st.get("cpu_frozen") else " (waiting for memory)"))
            if cg and isinstance(st.get("set"), (int, float)) and not j["frozen_since"]:
                try:
                    full = float([l for l in open(os.path.join(cg, "memory.pressure")) if l.startswith("full")][0]
                                 .split()[2].split("=")[1])
                except (OSError, IndexError, ValueError):
                    full = 0.0
                if full > cfg["health_mem_pct"]:
                    issue(("throttled", j["id"]), j, f"stalled on memory {full:.0f}% of the time at the limit kaeq set "
                          f"({fgb(st['set'])}): it hardly progresses", cfg["health_after_s"])
        timed_running = any((j["qos"] or "timed") == "timed" for j in running)
        if not timed_running and self.timed_wait >= cfg["timed_wait_start"]:
            issue(("stale_wait",), None, f"timed_wait {self.timed_wait:.0%} with no timed job running: timed starts "
                  f"are refused for nothing", cfg["health_after_s"])
        waiting = self.c.execute("SELECT COUNT(*) FROM jobs WHERE state='queued' AND qos='timed' AND not_before<=?",
                                 (now,)).fetchone()[0]
        pool = len(job_cpus(cfg) or ()) or cfg["threads"] - cfg["reserve_cpu"]
        if waiting and now - self.last_timed_start > cfg["health_timed_idle_s"] \
                and self.sys.get("ours_cpu", 0) + self.others_ema < pool - 8:
            issue(("timed_idle",), None, f"no timed job started for {fdur(now - self.last_timed_start)} while {waiting} "
                  f"wait and CPUs are idle")
        dep = deployed()
        if dep and dep.get("installed_at", 0) > self.started_at:
            issue(("restart",), None, f"kaeq {dep.get('sha', '?')[:7]} was installed after this daemon started: "
                  f"systemctl --user restart kaeq", cfg["health_after_s"])
        self.health_first = seen
        self.sys["health"] = out

    def thawed(self, jid, now):
        """Record the end of a job's freeze: its length goes into frozen_s."""
        st = self.lease_st.get(jid) or {}
        since = st.get("frozen_since") or (self.c.execute("SELECT frozen_since FROM jobs WHERE id=?", (jid,)).fetchone() or [0])[0]
        if since:
            self.c.execute("UPDATE jobs SET frozen_s=frozen_s+?, frozen_since=0 WHERE id=?", (max(0.0, now - since), jid))
            dlog(f"lease #{jid}: thawed after {fdur(now - since)}")
        st["frozen_since"] = 0.0

    def account(self, j, now, lost=False, end=None):
        """Close a job's attempt in its time accounting: an open freeze ends now, its CPU seconds are stored. lost:
        the attempt is thrown away (requeued), so its active and CPU time move to lost_run_s/lost_cpu_s and the
        per-attempt counters start again from zero."""
        self.thawed(j["id"], now)
        cpu = self.cpu_s.pop(j["id"], None)
        if cpu is not None:
            self.c.execute("UPDATE jobs SET cpu_s=? WHERE id=?", (cpu, j["id"]))
        self.flush_cpu(j["id"])
        self.cpuj.pop(j["id"], None)
        close_trace(j, end or ("requeued" if lost else "ended"))
        if lost:
            r = self.c.execute("SELECT * FROM jobs WHERE id=?", (j["id"],)).fetchone()
            self.c.execute("UPDATE jobs SET lost_run_s=lost_run_s+?, lost_cpu_s=lost_cpu_s+cpu_s, cpu_s=0, frozen_s=0, "
                           "freezes=0 WHERE id=?", (active_for(r, now), j["id"]))
        self.lease_st.pop(j["id"], None)

    def preempt(self, v, now, note, disk_mb=None):
        dlog(f"preempt #{v['id']}: {note}")
        self.kill(v)
        self.account(v, now, lost=True)
        drop_scratch(config(), v["id"])
        self.c.execute("UPDATE jobs SET state='queued',pid=NULL,preempts=preempts+1,not_before=?,note=?,disk_mb=?,grant_mb=0 WHERE id=?",
                       (now + 60, note, disk_mb or v["disk_mb"], v["id"]))

    def admit(self, cfg, now, mem_room, cpu_commit, n_running, disk_room=float("inf")):
        c = self.c
        cpu_room = cfg["threads"] - cfg["reserve_cpu"] - self.others_ema - cpu_commit
        # no start while threads already queue for a CPU: more work would only slow every running job. The run
        # queue counts as its runq_q quantile over runq_window_s (a dip must last), plus the CPUs of jobs started
        # in the last 60 s, which have not ramped up yet
        win = [r for t, r, _ in self.runq_hist if t >= now - cfg["runq_window_s"]] or [self.runq_ema]
        q = self.runq_q or cfg["runq_q"]
        fresh = sum(j["cpus"] for j in c.execute("SELECT cpus FROM jobs WHERE state='running' AND started>?", (now - 60,)))
        cpu_room = min(cpu_room, cfg["threads"] - cfg["reserve_cpu"] - quantile(win, q) - fresh)
        queued = c.execute("SELECT * FROM jobs WHERE state='queued' AND not_before<=?", (now,)).fetchall()
        running = c.execute("SELECT * FROM jobs WHERE state='running'").fetchall()
        pool = len(job_cpus(cfg) or ()) or cfg["threads"] - cfg["reserve_cpu"]
        # a filler starts when CPUs are spare right now (all threads ready to run, idle priority included, below
        # the CPUs jobs may use): at idle priority it cannot hurt anyone if that is brief. filler_frac x those CPUs
        # caps fillers' declared CPUs, a loose sanity limit
        fill = [sum(j["cpus"] for j in running if j["qos"] == "batch" and self.is_filler(j, cfg)),
                self.host.runnable_threads()]
        filler_ok = lambda j: (fill[1] + j["cpus"] <= pool and fill[0] + j["cpus"] <= cfg["filler_frac"] * pool)
        per_owner = {}
        for j in c.execute("SELECT owner, COUNT(*) n FROM jobs WHERE state='running' GROUP BY owner"):
            per_owner[j["owner"]] = j["n"]
        started = 0
        short = None
        while queued and started < cfg["starts_per_tick"] and n_running < cfg["max_running"]:
            queued.sort(key=lambda j: (-j["prio"], per_owner.get(j["owner"], 0), j["submitted"]))
            fits = lambda j: (self.need_mb(j, cfg) <= mem_room and j["disk_mb"] <= disk_room
                              and (n_running == 0 or (self.timed_cpu_fits(j, cfg, now, running)
                                                      if (j["qos"] or "timed") == "timed"
                                                      else filler_ok(j) if self.is_filler(j, cfg)
                                                      else j["cpus"] <= cpu_room)))
            fit = next((j for j in queued if fits(j)), None)
            # the first job that is not a filler (fillers wait for spare CPU, opportunistically: they hold no room)
            head = next((j for j in queued if not self.is_filler(j, cfg)), queued[0])
            if fit is not None and fit is not head and now - head["submitted"] > cfg["starve_after_s"] \
                    and not self.is_filler(head, cfg):
                # head is starving: hold the room for it. Jobs that end soon (short owners) and fillers may still
                # start, but only if they leave the head's memory free: a backfill job must never delay it. (Letting
                # short jobs take freed memory regardless meant a head needing more than any one job frees never
                # started while short jobs kept coming: a priority-6 timed job waited behind 179 short batch starts
                # an hour.)
                # The reservation applies when our own jobs finishing can free the head's memory; a head that needs
                # more (it waits on other users) holds no memory, or it would block the queue indefinitely.
                short = self.short_owners(cfg) if short is None else short
                ours = sum(r["grant_mb"] or self.need_mb(r, cfg) for r in running)
                reserve_head = self.need_mb(head, cfg) <= max(0.0, mem_room) + ours
                fit = next((j for j in queued if fits(j) and (j["owner"] in short or self.is_filler(j, cfg))
                            and (mem_room - self.need_mb(j, cfg) >= self.need_mb(head, cfg)
                                 or not reserve_head and not self.is_filler(j, cfg))), None)
            if fit is None:
                # jobs that fit in memory but wait for CPUs: what the runq_q controller weighs idle CPUs against
                self.cpu_waiting = any(self.need_mb(j, cfg) <= mem_room and j["cpus"] > cpu_room for j in queued[:50])
                break
            queued.remove(fit)
            if self.start(fit, cfg):
                if fit["qos"] == "batch" and self.is_filler(fit, cfg):
                    fill[0] += fit["cpus"]
                    fill[1] += fit["cpus"]            # its threads appear as it starts up
                mem_room -= self.need_mb(fit, cfg)
                cpu_room -= fit["cpus"]
                disk_room -= fit["disk_mb"]
                n_running += 1
                started += 1
                per_owner[fit["owner"]] = per_owner.get(fit["owner"], 0) + 1

    def is_filler(self, j, cfg):
        """A batch job that runs at SCHED_IDLE (heavy_boost: expected under keep_gb): it takes only spare CPU."""
        return cfg["heavy_boost"] and (j["qos"] or "timed") == "batch" and self.need_mb(j, cfg) < cfg["keep_gb"] * 1024

    def short_owners(self, cfg):
        """Owners whose recent jobs (p90 of the last 50, at least 5) ran within backfill_short_s."""
        out = set()
        if cfg["backfill_short_s"] <= 0:
            return out
        for (owner,) in self.c.execute("SELECT DISTINCT owner FROM jobs WHERE state='queued'").fetchall():
            d = sorted(r[0] for r in self.c.execute(
                "SELECT finished-started-frozen_s FROM jobs WHERE owner=? AND state='ok' AND started IS NOT NULL "
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
        timed = (j["qos"] or "timed") == "timed"
        if shutil_which("ionice"):   # batch: idle I/O; timed: lowest best-effort (idle I/O could starve its timing)
            argv = (["ionice", "-c2", "-n7"] if timed else ["ionice", "-c3"]) + argv
        grant = 0
        if self.use_cgroup(cfg):
            if cfg["mem_pool"] == "lease":
                # the grant is the scope's memory.high: above it the kernel stalls the job (it is never killed for
                # it) until the queue grants more; the slice's MemoryMax is the hard backstop
                grant = int(self.need_mb(j, cfg))
                lim = [] if timed else ["-p", f"MemoryHigh={grant}M"]   # a timed job is never throttled
            else:
                lim = ["-p", f"MemoryMax={int(j['mem_mb'] * cfg['mem_overrun'] * 2 + 1024)}M"]
            argv = ["systemd-run", "--user", "--scope", "--quiet", "--collect",
                    *([f"--slice={cfg['slice']}"] if cfg["slice"] else []),
                    *lim, "-p", "MemorySwapMax=0"] + argv
        pinned = job_cpus(cfg)
        tnice = int(cfg["timed_nice"])
        # one step up only if it is expected to be memory-heavy (heavy_boost): its learned size, or its --mem when
        # its owner has no history, at least keep_gb. A job that turns heavy later cannot be raised (no privileges)
        light = cfg["heavy_boost"] and self.need_mb(j, cfg) < cfg["keep_gb"] * 1024
        boosted = cfg["heavy_boost"] and not light

        def pre():
            os.setsid()
            if pinned:
                os.sched_setaffinity(0, pinned)
            try:  # batch: nice 19 and SCHED_IDLE, below every normal task; timed: nice timed_nice (10), well above;
                # light jobs one step down (heavy_boost): timed + 1 nice
                os.setpriority(os.PRIO_PROCESS, 0, (tnice if boosted or not cfg["heavy_boost"] else tnice + 1) if timed else 19)
            except OSError:
                pass
            if not timed and not boosted:     # (a boosted batch job stays SCHED_OTHER at nice 19 until demoted)
                try:
                    os.sched_setscheduler(0, os.SCHED_IDLE, os.sched_param(0))
                except OSError:
                    pass
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
        self.cpu_s.pop(j["id"], None)
        # a new attempt has a new scope: nothing cached about the last one may carry over (a retried job's lease
        # kept reading its first attempt's gone cgroup, so it was never leased: held at its first grant, throttled)
        for cache in (self.cgroups, self.lease_st, self.cpuj, self.trace, self.prev_ours):
            cache.pop(j["id"], None)
        self.c.execute("UPDATE jobs SET state='running',pid=?,started=?,deadline=?,peak_mb=0,note=NULL,grant_mb=?,"
                       "frozen_s=0,frozen_since=0,freezes=0,cpu_s=0,cpu_wait_s=0,cpu_stall_s=0,cpu_peak=0,squeezed_mb=0 WHERE id=?",
                       (p.pid, time.time(), time.time() + j["timeout_s"], grant, j["id"]))
        if timed:
            self.last_timed_start = time.time()
        dlog(f"start #{j['id']} attempt {j['attempt']} pid {p.pid} mem {fgb(j['mem_mb'])} "
             f"{'timed' if timed else 'batch'} {j['name'] or j['cmd'][:60]}")
        return True

    def kill(self, j, sig=signal.SIGTERM):
        cg = self.cgroups.get(j["id"]) or (job_cgroup(j["pid"]) if j["pid"] and pid_alive(j["pid"]) else None)
        if cg and cg_frozen(cg):
            cg_freeze(cg, False)                     # a frozen job handles no signal but SIGKILL
        kill_tree(j["pid"], cg, sig)
        if sig == signal.SIGTERM:  # a hard kill after a short grace
            time.sleep(0.2)
            kill_tree(j["pid"], cg, signal.SIGKILL)

    def check(self, j, rss, now, cfg, disk=0.0, lease=False):
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
        if active_for(j, now) > j["timeout_s"]:     # time frozen waiting for memory does not count
            self.kill(j)
            return self.finish_fail(j, "timeout", f"exceeded --timeout {fdur(j['timeout_s'])}; raise --timeout or split the job", peak)
        if disk > j["disk_mb"] * cfg["disk_overrun"] + 5 * 1024:
            self.kill(j)
            drop_scratch(cfg, j["id"])
            new = int(disk * 1.3) + 1024
            if j["preempts"] < 2:
                self.account(j, now, lost=True)
                c.execute("UPDATE jobs SET state='queued',pid=NULL,disk_mb=?,preempts=preempts+1,note=? WHERE id=?",
                          (new, f"killed at scratch {fgb(disk)} > declared {fgb(j['disk_mb'])}; auto-requeued with --disk {fgb(new)}", j["id"]))
            else:
                self.finish_fail(j, "failed", f"scratch {fgb(disk)} exceeded declared {fgb(j['disk_mb'])}; resubmit with --disk {fgb(new)}")
            return
        if rss > j["mem_mb"] * cfg["mem_overrun"] + 1024 and not lease:  # under a lease, memory.high holds it
            self.kill(j)
            new = int(rss * 1.3) + 1024
            drop_scratch(cfg, j["id"])
            if j["preempts"] < 2:  # one automatic re-queue with a corrected estimate
                self.account(j, now, lost=True)
                c.execute("UPDATE jobs SET state='queued',pid=NULL,mem_mb=?,preempts=preempts+1,note=? WHERE id=?",
                          (new, f"killed at {fgb(rss)} > declared {fgb(j['mem_mb'])}; auto-requeued with --mem {fgb(new)}", j["id"]))
            else:
                self.finish_fail(j, "oom", f"RSS {fgb(rss)} exceeded declared {fgb(j['mem_mb'])}; resubmit with --mem {fgb(new)}", peak)

    def learn_ratios(self, cfg, now):
        """{owner: median of peak/--mem over its last 100 finished jobs} for owners with enough of them
        (refreshed every 5 minutes). The median, not a high quantile: a few badly under-declared jobs would
        otherwise size every job of their owner by their ratio."""
        if now - self.ratios_ts < 300:
            return
        out, samples = {}, {}
        for (o,) in self.c.execute("SELECT DISTINCT owner FROM jobs WHERE state IN ('queued','running')").fetchall():
            r = sorted(p / m for m, p in self.c.execute(
                "SELECT mem_mb, peak_mb FROM jobs WHERE owner=? AND state='ok' AND peak_mb>0 AND mem_mb>0 "
                "ORDER BY finished DESC LIMIT 100", (o,)))
            if len(r) >= cfg["mem_learn_min_jobs"]:
                out[o] = r[len(r) // 2]
                samples[o] = r
        self.ratios, self.ratio_samples, self.ratios_ts = out, samples, now

    def need_mb(self, j, cfg):
        """Memory a job is expected to need: --mem, scaled by its owner's median peak/--mem (x mem_learn_margin).
        Not capped at --mem: an owner whose jobs use more than they declare gets them sized up."""
        q = self.ratios.get(j["owner"])
        return j["mem_mb"] if q is None else max(256.0, j["mem_mb"] * q * cfg["mem_learn_margin"])

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
            now = time.time()
            self.account(j, now, end="ok")
            _, tr, first = self.trace.pop(j["id"], [0, [], now])
            seen = (now - first) / max(1.0, now - (j["started"] or now))  # share of its run observed (< 1 after a restart)
            hist = json.dumps(mem_hist(tr, peak)) if seen >= 0.5 and len(tr) >= 6 and peak > 0 else None
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
        retry = j["retries_left"] > 0 and state != "timeout"
        self.account(j, time.time(), lost=retry, end=state)
        if retry:
            c.execute("UPDATE jobs SET state='queued',pid=NULL,attempt=attempt+1,retries_left=retries_left-1,note=? WHERE id=?",
                      (f"auto-retry after: {note}", j["id"]))
            return
        c.execute("UPDATE jobs SET state=?,rc=?,finished=?,pid=NULL,peak_mb=?,note=? WHERE id=?",
                  (state, rc if rc is not None else -1, time.time(), peak, note, j["id"]))
        drop_worktree(j)
        r = c.execute("SELECT * FROM jobs WHERE id=?", (j["id"],)).fetchone()
        head = f"#{j['id']} {state.upper()} {note} | {j['name'] or j['cmd'][:60]} | {ref(j)} | {times(r)} peak {fgb(peak)}/{fgb(j['mem_mb'])} attempt {j['attempt']}"
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
