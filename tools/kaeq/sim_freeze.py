#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trace replay of kaeq's memory policy under pressure, with batch-job FREEZING modelled, running kaeq's own code.

Extends sim.py's engine (same 2-s tick, trace loader, growth buffer) with batch jobs that can be frozen
(cgroup.freeze: no progress, no CPU, memory kept) and compressed into zram while frozen (frees `gain` x their use,
up to `zram_gb` of pages over all frozen jobs). The policy is not a copy: each tick KaeqPolicy builds the lease
records the daemon builds (kaeqlib.leases.keep_flags) and runs the daemon's lease_plan, then applies its grants,
freezes, thaws (with the run window), victims and evictions.

    python3 tools/kaeq/sim_freeze.py --traces /var/tmp/$USER/kaeq/traces -j 8
    python3 tools/kaeq/sim_freeze.py --traces DIR --ram-gb 150 --policies kaeq,kaeq:thaw_min_run_s=0,kaeq:keep_gb=16

Policies: kaeq[:setting=value,...], any of kaeq's settings (DEFAULTS) overridden; --policies ablate runs a set of
variants (no protection, no run window, set-asides, thresholds).

Not modelled: compression and thaw are instant (the real ones take seconds and cost CPU); a thawed job's zram pages
come back at once; batch jobs at SCHED_IDLE (all jobs share the CPU equally here); the cpu.pressure freezer and
squeezing; the emergency requeue (at kaeq's floor, inside the reserve, which the replay counts as overflow);
admission is by memory (the plan's free room) and sim.py's CPU model, not kaeq's run-queue gate; other users'
memory varies (here a constant reserve); jobs' curves recorded under the live queue's contention.
"""
import argparse
import json
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402

GB = 1024.0
BIN_EDGES = ((2 * GB, "<2"), (8 * GB, "2-8"), (16 * GB, "8-16"), (float("inf"), ">16"))
BIN_NAMES = [b for _, b in BIN_EDGES]


def size_bin(mb):
    for edge, name in BIN_EDGES:
        if mb < edge:
            return name
    return BIN_NAMES[-1]


def timed_prefixes(spec):
    """'exp-,rescore-' -> predicate on owner; 'none': every job is batch; 'all': every job is timed."""
    if spec == "none":
        return lambda o: False
    if spec == "all":
        return lambda o: True
    pre = tuple(p for p in spec.split(",") if p)
    return lambda o: o.startswith(pre)


# ---------------------------------------------------------------- engine

class FRun(sim.Run):
    """A run that may be frozen. `use` is resident memory (what killing it frees); `zfree` is what compression
    took out of RAM while frozen (logical use = use + zfree); `active` is unfrozen wall time."""
    __slots__ = ("timed", "frozen", "frozen_since", "zfree", "zpages", "active", "grew", "rate", "guard_until",
                 "wait_acc", "noise")

    def __init__(self, job, t, hist_len, timed):
        super().__init__(job, t, hist_len)
        self.timed, self.frozen, self.frozen_since = timed, False, 0.0
        self.zfree = self.zpages = self.active = self.grew = self.rate = 0.0
        self.guard_until, self.wait_acc, self.noise = 0.0, 0.0, 1.0

    @property
    def invest(self):
        return self.active * max(1.0, self.job.tpl.cpus)

    @property
    def logical(self):
        return self.use + self.zfree


class FreezeSim(sim.Sim):
    def __init__(self, templates, mem, cpu, is_timed=lambda o: False, zram_gb=50.0, gain=0.3, seed=0,
                 owner_hist=(), **kw):
        super().__init__(templates, mem, cpu, **kw)
        self.is_timed, self.zram_cap, self.gain = is_timed, zram_gb * GB, gain
        self.zram_used = 0.0
        self.rng = random.Random(seed)
        self.evict_ts = self.tpre_ts = -1e9
        self.m.update(victim=0, timed_victim=0, room=0, freezes=0, thaws=0)
        self.bin = {b: dict(jobs=0, fz_mbs=0.0, fz_s=0.0, freezes=0, slow=[], wall=0.0, lost_cs=0.0, requeues=0)
                    for b in BIN_NAMES}
        self.jstat = {}                 # jid -> [freezes, frozen_s] over all attempts
        self.ohist = {}                 # owner -> [(duration, mem_mb)] of finished jobs (for value=est)
        for t in owner_hist:
            self.ohist.setdefault(t.owner, []).append((t.duration, t.mem_mb))
        self.ocache, self.ncache = {}, {}
        self.fin_t = []

    def need(self, job):
        if job.need_fix is not None:
            return min(job.need_fix, self.cap)
        o = self.learner.owners.get(job.tpl.owner)
        key = (job.tpl.owner, job.tpl.mem_mb, o.n if o else 0)
        v = self.ncache.get(key)
        if v is None:
            v = self.ncache[key] = min(self.learner.need(job.tpl.owner, job.tpl.mem_mb), self.cap)
        return v

    def jbin(self, r):
        return size_bin(r.job.tpl.peak)

    def start(self, job):
        self.queue.remove(job)
        r = FRun(job, self.t, self.win, self.is_timed(job.tpl.owner))
        r.noise = math.exp(random.Random(job.jid * 7919 + job.preempts).gauss(0.0, 0.3))
        if job.first_start is None:
            job.first_start = self.t
            self.m["wait"].append(self.t - job.arrival)
        self.running.append(r)
        self.mem.start(self, r)
        return r

    def freeze(self, r):
        if r.frozen:
            return
        r.frozen, r.frozen_since = True, self.t
        r.grant = min(r.grant, r.logical)
        pages = min(r.use, max(0.0, self.zram_cap - self.zram_used))
        r.zpages, r.zfree = pages, pages * self.gain
        self.zram_used += pages
        r.use -= r.zfree
        self.used -= r.zfree
        self.m["freezes"] += 1
        self.bin[self.jbin(r)]["freezes"] += 1
        self.jstat.setdefault(r.job.jid, [0, 0.0])[0] += 1

    def thaw(self, r, win):
        if not r.frozen:
            return
        f = self.t - r.frozen_since
        r.wait_acc += f
        r.frozen = False
        r.guard_until = self.t + max(win, 0.25 * f) if win > 0 else 0.0
        r.use += r.zfree
        self.used += r.zfree
        self.zram_used -= r.zpages
        r.zfree = r.zpages = 0.0
        self.m["thaws"] += 1

    def kill(self, r, why):
        if r.frozen:
            self.zram_used -= r.zpages
        b = self.bin[self.jbin(r)]
        b["lost_cs"] += r.core_s
        b["requeues"] += 1
        super().kill(r, why)

    def step(self):
        dt = self.tick
        cur = []
        for r in list(self.running):
            if r.frozen:
                cur.append((r, r.use, 0.0))
                continue
            u, c = sim.use_at(r.job.tpl, r.p)
            cur.append((r, u, c))
        U = sum(u for _, u, _ in cur)
        if U > self.cap:                                 # overflow: the kernel kills the largest job
            over = U - self.cap
            self.m["overflow_n"] += 1
            self.m["overflow_mbs"] += over * dt
            self.m["overflow_max"] = max(self.m["overflow_max"], over)
            cur.sort(key=lambda x: (-x[1], x[0].job.jid))
            while U > self.cap and cur:
                r, u, _ = cur.pop(0)
                U -= u
                self.kill(r, "oom")
            cur.sort(key=lambda x: x[0].job.jid)
        C = sum(c for _, _, c in cur)
        f = 1.0 if C <= self.pool or C <= 0 else max(0.0, self.pool) / C
        self.contended = C > self.pool
        grew, used = 0.0, 0.0
        for r, u, c in cur:
            r.wall += dt
            used += u
            if r.frozen:
                b = self.bin[self.jbin(r)]
                b["fz_mbs"] += u * dt
                b["fz_s"] += dt
                self.jstat.setdefault(r.job.jid, [0, 0.0])[1] += dt
                r.grew = 0.0
                continue
            if r.wall >= sim.WARM_S:
                grew += max(0.0, u - r.use)
            r.grew = u - r.use
            r.rate = 0.7 * r.rate + 0.3 * max(0.0, r.grew) / dt
            r.use = u
            r.peak = max(r.peak, u)
            r.core_s += c * f * dt
            r.hist.append(c * f)
            r.p += dt * f
            r.active += dt
            self.done_cs += max(1.0, r.job.tpl.cpus) * dt
        self.used = used
        self.growth.append(grew)
        self.buffer = max(sim.BUFFER_MIN_MB, self.buffer_ticks * max(self.growth))
        self.m["ram_int"] += U * dt
        self.m["cpu_int"] += C * f * dt
        if self.queue:
            self.m["busy_s"] += dt
            self.m["busy_ram"] += U * dt
            self.m["busy_cpu"] += C * f * dt

    def finish(self):
        for r in [r for r in self.running if not r.frozen and r.p >= r.job.tpl.duration - 1e-6]:
            self.running.remove(r)
            self.used -= r.use
            self.m["finished"] += 1
            self.m["useful_cs"] += r.core_s
            s = (self.t - r.job.first_start) / r.job.tpl.duration
            self.m["slow"].append(s)
            b = self.bin[self.jbin(r)]
            b["jobs"] += 1
            b["slow"].append(s)
            b["wall"] += self.t - r.job.first_start
            self.m["makespan"] = self.t
            self.fin_t.append(self.t)
            self.learner.add(r.job.tpl)
            self.ohist.setdefault(r.job.tpl.owner, []).append((r.job.tpl.duration, r.job.tpl.mem_mb))
            self.ocache.pop(r.job.tpl.owner, None)

    def owner_dur(self, owner):
        """(median duration, median --mem) of the owner's finished jobs, or None."""
        c = self.ocache.get(owner)
        if c is None:
            h = self.ohist.get(owner)
            if not h:
                return None
            c = self.ocache[owner] = (sim.quantile([d for d, _ in h], 0.5), sim.quantile([m for _, m in h], 0.5))
        return c

    def metrics(self):
        m = super().metrics()
        span = max(self.tick, self.m["makespan"] or self.t)
        m.update(victim=self.m["victim"], timed_victim=self.m["timed_victim"], room=self.m["room"],
                 freezes=self.m["freezes"], ram_gb=self.m["ram_int"] / span / GB,
                 requeues=sum(self.m[k] for k in ("evict", "victim", "timed_victim", "room", "oom", "limit")),
                 t90_h=sim.quantile(self.fin_t, 0.9) / 3600 if self.fin_t else 0.0,
                 fz_gbh=sum(b["fz_mbs"] for b in self.bin.values()) / GB / 3600)
        for name, b in self.bin.items():
            n = max(1, b["jobs"])
            m[f"bin{name}"] = dict(jobs=b["jobs"], fz_gbh=b["fz_mbs"] / GB / 3600,
                                   fz_share=b["fz_s"] / max(1.0, b["wall"]), freezes_per_job=b["freezes"] / n,
                                   slow=sum(b["slow"]) / n if b["slow"] else 1.0, requeues=b["requeues"],
                                   lost_ch=b["lost_cs"] / 3600)
        return m


# ---------------------------------------------------------------- policy

class KaeqPolicy(sim.MemPolicy):
    """kaeq's own memory policy, not a copy: each tick builds the lease records the daemon builds (keep_flags)
    and runs the daemon's lease_plan (kaeqlib.leases), then applies what it decides: grants, freezes (compressed),
    thaws (with the run window), the long-stall victim, the timed victim and evictions. Admission: the plan's free
    memory, nothing while a job waits frozen at its grant or a kept job is short. Settings are kaeq's DEFAULTS,
    overridden by the spec: kaeq:thaw_min_run_s=0,keep_gb=16,..."""
    H = None

    def __init__(self, overrides=None, name="kaeq"):
        from kaeqlib.store import DEFAULTS
        self.cfg = dict(DEFAULTS)
        for k, v in (overrides or {}).items():
            if k not in self.cfg:
                raise ValueError(f"kaeq: no setting {k}")
            self.cfg[k] = type(self.cfg[k])(v) if not isinstance(self.cfg[k], (str, bool)) else (
                v if isinstance(self.cfg[k], str) else str(v).lower() in ("1", "true", "yes"))
        self.name = name
        self.st = {}                    # id(run) -> lease bookkeeping lease_plan carries between ticks
        self.room, self.block, self.evict_ts, self.tvict_ts = 0.0, False, -1e9, -1e9

    def admit(self, sim_, job):
        return not self.block and sim_.need(job) <= self.room

    def commit(self, sim_, job):
        self.room -= sim_.need(job)

    def start(self, sim_, run):
        run.grant = sim_.need(run.job)

    def on_tick(self, s):
        from kaeqlib.leases import keep_flags, lease_plan, pooled_headroom
        # kaeq's times are epoch seconds and treat 0 as "not started": shift the replay's clock (from 0) for it
        OFF = 1e6
        cfg, now = self.cfg, s.t + OFF
        recs, by = [], {}
        for r in s.running:
            st = self.st.setdefault(id(r), {"slack": 0.0, "stall": 0.0})
            frozen_s = r.wait_acc + (s.t - r.frozen_since if r.frozen else 0.0)
            rec = dict(id=id(r), prio=r.job.prio, started=r.start + OFF, grant=float(r.grant or s.need(r.job)), use=r.use,
                       declared=r.job.tpl.mem_mb, slack_since=st["slack"], stall_since=st["stall"], rate=r.rate,
                       frozen=r.frozen, grew=r.grew, timed=r.timed, waited_frozen=frozen_s - st.get("base", 0.0),
                       protected=r.job.preempts >= cfg["evict_protect_after"], invest=r.invest,
                       compressed=r.frozen and r.zfree > 0, mpress=0.0, swapped=r.zfree if r.frozen else 0.0,
                       owner=r.job.tpl.owner, expect=max(s.need(r.job), r.peak), held_out=0.0)
            keep_flags(rec, cfg, now, r.guard_until + OFF if r.guard_until else 0.0)
            recs.append(rec)
            by[id(r)] = r
        for k in set(self.st) - set(by):
            del self.st[k]
        warm = cfg["lease_warm_s"]
        timed_held = pooled_headroom([(x["owner"], x["expect"], x["use"], None) for x in recs
                                      if x["timed"] and now - x["started"] >= warm], cfg["timed_z"], cfg["mem_pool_rho"])[0]
        real = s.cap - s.used
        plan = lease_plan(recs, real, cfg, now, s.buffer, timed_held, 0.0, real)
        for x in recs:
            r, st = by[x["id"]], self.st[x["id"]]
            r.grant = plan["grants"][x["id"]]
            st["slack"], st["stall"] = plan["slack_since"][x["id"]], plan["stall_since"][x["id"]]
            if x["id"] in plan["stalled"]:
                s.freeze(r)
            elif r.frozen:
                s.thaw(r, cfg["thaw_min_run_s"])
        out = []
        if plan["victim"] is not None:
            w = by.get(plan["waiter"])
            if w is not None:
                self.st[id(w)]["base"] = w.wait_acc + (s.t - w.frozen_since if w.frozen else 0.0)
            out.append((by[plan["victim"]], "victim"))
        if plan["timed_victim"] is not None and now - self.tvict_ts >= cfg["timed_preempt_s"]:
            self.tvict_ts = now
            out.append((by[plan["timed_victim"]], "timed_victim"))
        if plan["evict"] is not None and now - self.evict_ts >= cfg["evict_every_s"]:
            self.evict_ts = now
            out.append((by[plan["evict"]], "evict"))
        killed = []
        for r, why in out:
            if r in s.running:
                s.kill(r, why)
                killed.append(r)
        self.room = plan["free"]
        self.block = bool(plan["stalled"] or plan["short"]
                          or any(x["compressed"] for x in recs if x["id"] not in plan["stalled"]))
        return killed

    def knob(self):
        return ""


def parse_policy(spec):
    """kaeq[:setting=value,...]: kaeq's own lease plan, with any of its settings overridden."""
    name, _, arg = spec.partition(":")
    if name != "kaeq":
        raise ValueError(f"unknown policy {spec} (kaeq[:setting=value,...])")
    kv = dict(a.split("=", 1) for a in filter(None, arg.split(",")))
    return lambda: KaeqPolicy(kv, name=spec)


def simulate(templates, policy, history=(), ram_gb=221.0, reserve_gb=30.0, cpus=118, timed="exp-,rescore-",
             zram_gb=50.0, gain=0.3, cpu="burst", arrivals=None):
    mem = parse_policy(policy)() if isinstance(policy, str) else policy
    learner = sim.Learner(min_jobs=5, horizon=None)
    for t in history:
        learner.add(t)
    cpu_ = CpuBurstF() if cpu == "burst" else sim.CPUS[cpu]()
    s = FreezeSim(templates, mem, cpu_, is_timed=timed_prefixes(timed) if isinstance(timed, str) else timed,
                  zram_gb=zram_gb, gain=gain, owner_hist=history, ram_mb=ram_gb * GB, other_mb=reserve_gb * GB,
                  cpus=cpus, learner=learner, arrivals=arrivals)
    m = s.run()
    m["policy"] = mem.name
    return m


class CpuBurstF(sim.CpuBurst):
    """sim.CpuBurst, with frozen jobs left out (they use no CPU while frozen)."""

    def prepare(self, s):
        self.mean = self.sq = 0.0
        for r in s.running:
            if getattr(r, "frozen", False):
                continue
            m, p = self._est(s, r)
            self.mean += m
            self.sq += max(0.0, p - m) ** 2


# ---------------------------------------------------------------- CLI

_G = {}


def _job(a):
    spec, kw = a
    t0 = time.time()
    m = simulate(_G["tpls"], spec, _G["hist"], **kw)
    m["wall_s"] = time.time() - t0
    return m


def table(rows):
    hdr = ["policy", "jobs", "span_h", "t90_h", "jobs/h", "RAM_GB", "fzGBh", "<2", "2-8", "8-16", ">16",
           "frz/job<2,2-8,8-16,>16", "slow<2,2-8,8-16,>16", "fz%>16", "requeue", "lost_ch", "ovf", "oom"]
    out = [hdr]
    for r in rows:
        b = [r[f"bin{n}"] for n in BIN_NAMES]
        out.append([r["policy"], str(r["jobs"]), f"{r['makespan_h']:.2f}", f"{r['t90_h']:.2f}",
                    f"{r['jobs_per_h']:.1f}",
                    f"{r['ram_gb']:.0f}", f"{r['fz_gbh']:.1f}"] + [f"{x['fz_gbh']:.1f}" for x in b]
                   + [",".join(f"{x['freezes_per_job']:.1f}" for x in b),
                      ",".join(f"{x['slow']:.2f}" for x in b), f"{b[3]['fz_share']:.0%}",
                      f"{r['requeues']}({r['evict']}e{r['victim']}v{r['timed_victim']}t{r['room']}r)",
                      f"{r['lost_ch']:.1f}", str(r["overflow_n"]), str(r["oom"])])
    w = [max(len(c[i]) for c in out) for i in range(len(hdr))]
    return "\n".join("  ".join(c[i].ljust(w[i]) if i == 0 else c[i].rjust(w[i]) for i in range(len(hdr)))
                     for c in out)


ABLATE = ["kaeq", "kaeq:keep_gb=1e9,keep_core_h=1e9", "kaeq:thaw_min_run_s=0,thaw_min_frac=0",
          "kaeq:keep_reserve_frac=1", "kaeq:keep_reserve_frac=0.5", "kaeq:keep_gb=4", "kaeq:keep_gb=16",
          "kaeq:thaw_min_run_s=300", "kaeq:lease_hold_frac=0.25", "kaeq:lease_hold_frac=0"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--traces", required=True)
    ap.add_argument("--policies", default="current,protect", help="comma-separated; 'ablate' for the full set")
    ap.add_argument("--ram-gb", type=float, default=221.0, help="RAM for kaeq (251 GB host minus 30 GB)")
    ap.add_argument("--reserve-gb", type=float, default=30.0, help="held for other users")
    ap.add_argument("--cpus", type=float, default=118)
    ap.add_argument("--timed", default="exp-,rescore-", help="owner prefixes of timed jobs; none | all")
    ap.add_argument("--zram-gb", type=float, default=50.0, help="pages zram may hold (80%% of 63 GB)")
    ap.add_argument("--gain", type=float, default=0.3, help="share of a frozen job's memory compression frees")
    ap.add_argument("--history-frac", type=float, default=0.25, help="oldest share of templates only trains")
    ap.add_argument("--limit", type=int, default=0, help="replay only the first N jobs")
    ap.add_argument("-j", type=int, default=1)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    t0 = time.time()
    tpls, counts = sim.load_traces(a.traces)
    h = int(len(tpls) * a.history_frac)
    hist, tpls = tpls[:h], tpls[h:]
    if a.limit:
        tpls = tpls[:a.limit]
    _G.update(tpls=tpls, hist=hist)
    pol = ABLATE if a.policies == "ablate" else [p for p in a.policies.split(";")] if ";" in a.policies \
        else sim.split_policies(a.policies)
    kw = dict(ram_gb=a.ram_gb, reserve_gb=a.reserve_gb, cpus=a.cpus, timed=a.timed, zram_gb=a.zram_gb, gain=a.gain)
    isb = timed_prefixes(a.timed)
    nb = sum(1 for t in tpls if not isb(t.owner))
    print(f"{len(tpls)} jobs ({nb} batch), {len(hist)} history; RAM {a.ram_gb - a.reserve_gb:g} GB, {a.cpus:g} CPUs; "
          f"sum of use {sum(sum(t.use) for t in tpls) * sim.DT / GB / 3600:.0f} GB·h, "
          f"{sum(sum(t.cores) for t in tpls) * sim.DT / 3600:.0f} core-h (loaded in {time.time() - t0:.1f} s)",
          file=sys.stderr)
    jobs = [(p, kw) for p in pol]
    if a.j > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(min(a.j, len(jobs))) as ex:
            rows = list(ex.map(_job, jobs))
    else:
        rows = [_job(x) for x in jobs]
    print(table(rows))
    print(f"(max replay {max(r['wall_s'] for r in rows):.0f} s)", file=sys.stderr)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
