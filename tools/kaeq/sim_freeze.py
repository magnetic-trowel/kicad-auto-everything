#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trace replay of kaeq's batch-job FREEZING under memory pressure: the current lease policy vs "protect".

Extends sim.py's engine (same 2-s tick, trace loader, growth buffer, eviction) with batch jobs that can be
frozen (cgroup.freeze: no progress, no CPU, memory kept) and compressed into zram while frozen (frees
`gain` x their use, up to `zram_gb` of pages over all frozen jobs).

    python3 tools/kaeq/sim_freeze.py --traces /var/tmp/$USER/kaeq/traces -j 8
    python3 tools/kaeq/sim_freeze.py --traces DIR --ram-gb 150 --policies current,protect,protect:-3,protect:T=4

Policies (FreezePolicy):
  current   kaeq.lease_plan as of 2026-11-04 for batch jobs: grants step by max(1 GB, 25% of grant, need) in order
            (frozen-and-compressed first, timed, priority, oldest); a batch job gets a whole step or, at its grant,
            is frozen; free = real free - buffer - held (young jobs' unused grant in full, 10% of other batch jobs',
            timed jobs' pooled forecast growth); admission only while no job waits frozen; real free < buffer
            freezes the batch jobs that grew this tick (lowest priority, newest first; the oldest of the highest
            priority spared above half the buffer); below half the buffer the cheapest job per MB is requeued; a
            job frozen lease_stall_s requeues the newest other batch job (or one past 1.5x its --mem).
  protect   current plus five parts (drop one with protect:-K, e.g. protect:-3; K in 1..5):
            1 expensive batch jobs (expected peak >= T GB or invested >= 1 core-h) set aside their forecast growth
              (expected peak - use) in full, so neither grants nor admission use that room;
            2 grants go in order of value = memory held / expected remaining time (highest first), freezes to the
              lowest value first (remaining time: owner's median duration scaled by --mem, or value=oracle);
            3 a protected job that needs a step none can give makes room: freeze + compress low-value unprotected
              batch jobs, then requeue unprotected jobs with the least invested work per MB, instead of freezing;
            4 a thawed job is not frozen again for max(win, 25% of its last freeze), unless free < buffer / 2;
            5 a big job (expected peak >= T) starts only when its expected peak fits beside the protected jobs'
              set-aside and no job waits frozen; small jobs may backfill while jobs wait frozen, into room beyond
              what those need to thaw (and beyond the protected set-aside).
  Options: T=GB (8), win=s (300), invest=core-h (1), value=est|oracle, requeue=all|young|none (part 3's
  requeues: any unprotected job, only jobs active < 10 min, or none: freeze only), sa=share (1: of the forecast
  growth part 1 sets aside).

Not modelled: compression and thaw are instant (the real ones take seconds and cost CPU); a thawed job's zram pages
come back at once; batch jobs at SCHED_IDLE (all jobs share the CPU equally here); the cpu.pressure freezer; other
users' memory varies (here a constant reserve); jobs' curves recorded under the live queue's contention.
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
STEP_MB, STEP_FRAC, MARGIN_MB, MARGIN_FRAC = 1024.0, 0.25, 512.0, 0.15     # kaeq lease_step_*, lease_margin_*
FREEZE_MB = 256.0                       # lease_freeze_mb
RELEASE_MB, RELEASE_FRAC, RELEASE_AFTER = 2048.0, 0.25, 120.0
HOLD = 0.1                              # lease_hold_frac
STALL_S = 900.0                         # lease_stall_s
OVERRUN = 1.5                           # mem_overrun
EVICT_EVERY = 10.0                      # evict_every_s
TIMED_PREEMPT = 30.0                    # timed_preempt_s
TIMED_Z = 2.0
YOUNG_S = 600.0                         # protect requeue=young: jobs active less than this may be requeued for room


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

class FreezePolicy(sim.MemPolicy):
    """kaeq's lease plan for batch jobs (`current`), with any of the five parts of `protect` (see module doc)."""
    H = None                             # the learner forecasts growth over the rest of a job (timed held)

    def __init__(self, parts=(), T_gb=8.0, win=300.0, invest_ch=1.0, value="est", requeue="all", sa=1.0, name=None):
        self.parts = frozenset(parts)
        self.T, self.win, self.invest_cs, self.value_mode = T_gb * GB, win, invest_ch * 3600, value
        self.requeue = requeue          # part 3 may requeue: "all" unprotected jobs, "young" (< YOUNG_S active), "none"
        self.short = False
        self.sa_frac = sa               # share of a protected job's forecast growth part 1 sets aside
        self.name = name or ("current" if not self.parts else "protect")
        self.room, self.blocked, self.thaw_need, self.setaside = 0.0, False, 0.0, 0.0
        self.sa = {}

    # ---- what a job is expected to need and to be worth
    def expect(self, sim_, job, peak=0.0):
        return max(sim_.need(job), peak)

    def protected(self, sim_, r):
        return (not r.timed) and (self.expect(sim_, r.job, r.peak) >= self.T or r.invest >= self.invest_cs)

    def remaining(self, sim_, r):
        tpl = r.job.tpl
        if self.value_mode == "oracle":
            return max(10.0, (tpl.duration - r.p) * r.noise)
        od = sim_.owner_dur(tpl.owner)
        if od is None:
            est = 1800.0
        else:
            est = od[0] * min(2.0, max(0.5, tpl.mem_mb / max(1.0, od[1])))
        return max(60.0, est - r.p, 0.25 * r.p)

    def value(self, sim_, r):
        return r.logical / self.remaining(sim_, r)

    def step_of(self, g, u, free=0.0):
        margin = max(MARGIN_MB, MARGIN_FRAC * g)
        s = max(STEP_MB, STEP_FRAC * g, u + margin - g)
        if free > 4 * s:
            s = max(s, 0.5 * g)
        return s

    def can_freeze(self, sim_, r, real):
        return 4 not in self.parts or sim_.t >= r.guard_until or real < sim_.buffer / 2

    def window(self):
        return self.win if 4 in self.parts else 0.0

    # ---- held: memory counted as taken beyond real use
    def held(self, sim_):
        h, mu, var, setaside = 0.0, 0.0, 0.0, 0.0
        self.sa = sa = {}                # protected run -> its forecast growth beyond 10% of its unused grant
        for r in sim_.running:
            unused = max(0.0, r.grant - r.logical)
            if r.wall < sim.WARM_S:
                h += unused
            elif r.timed:
                g = sim_.learner.growth(r.job.tpl.owner, r.p, r.use, r.peak, r.job.tpl.mem_mb)
                if g is None:
                    mu += max(0.0, self.expect(sim_, r.job, r.peak) - r.use)
                else:
                    mu += g[0]
                    var += g[1]
            elif self.protected(sim_, r):
                grow = max(0.0, self.expect(sim_, r.job, r.peak) - r.logical)
                sa[id(r)] = max(0.0, self.sa_frac * grow - HOLD * unused)
                setaside += sa[id(r)]
                h += HOLD * unused
            else:
                h += HOLD * unused
        self.setaside = setaside
        h += mu + TIMED_Z * math.sqrt(var)
        if 1 in self.parts:
            h += setaside
        return h

    # ---- admission (two-phase, see sim.MemPolicy)
    def prepare(self, sim_):
        self.left = self.room

    def admit(self, sim_, job):
        need = sim_.need(job)
        if 5 not in self.parts:
            return not self.blocked and need <= self.left
        room = self.left - (0.0 if 1 in self.parts else self.setaside)
        if self.expect(sim_, job) >= self.T:
            return not self.blocked and self.expect(sim_, job) <= room
        return not self.short and need <= room - (self.thaw_need if self.blocked else 0.0)

    def commit(self, sim_, job):
        self.left -= sim_.need(job)

    def start(self, sim_, run):
        run.grant = sim_.need(run.job)

    # ---- the lease plan, once per tick
    def on_tick(self, sim_):
        t, run = sim_.t, sim_.running
        real = sim_.cap - sim_.used
        buf = sim_.buffer
        for r in run:                                   # trim grants far above use
            g, u = r.grant, r.logical
            if g - u > max(RELEASE_MB, RELEASE_FRAC * u) and r.wall >= sim.WARMUP_S and not r.frozen:
                r.slack_since = r.slack_since or t
                if t - r.slack_since >= RELEASE_AFTER:
                    r.grant = min(g, max(u * 1.25, u + 1024.0))
                    r.slack_since = 0.0
            else:
                r.slack_since = 0.0
        held = self.held(sim_)
        free = real - buf - held
        val = {id(r): self.value(sim_, r) for r in run} if 2 in self.parts else None
        stalled = {}                                    # id -> run, to be frozen (or stay frozen)
        kills = []
        # the fleet grew into the buffer: freeze who grew
        if real < buf:
            grew = [r for r in run if r.grew > 0 and not r.timed and not r.frozen and self.can_freeze(sim_, r, real)]
            if val is None:
                grew.sort(key=lambda r: (r.job.prio, -r.start))
            else:
                grew.sort(key=lambda r: (r.job.prio, val[id(r)]))
            if grew and real > buf / 2:
                grew.pop()
            for r in grew:
                r.grant = min(r.grant, r.logical)
                stalled[id(r)] = r
        # below half the buffer: requeue the cheapest job per MB freed (one per EVICT_EVERY)
        if real < buf / 2 and t - sim_.evict_ts >= EVICT_EVERY:
            v = sim_.cheapest_victim()
            if v is not None:
                kills.append((v, "evict"))
                sim_.evict_ts = t
        dead = {id(v) for v, _ in kills}
        short = []
        if val is None:
            order = sorted(run, key=lambda r: (not r.frozen, not r.timed, -r.job.prio, r.start, r.job.jid))
        else:
            order = sorted(run, key=lambda r: (not r.timed, -r.job.prio, -val[id(r)], r.job.jid))
        for r in order:
            if id(r) in stalled or id(r) in dead:
                continue
            g, u = r.grant, r.logical
            margin = max(MARGIN_MB, MARGIN_FRAC * g)
            if u < g - margin:
                continue
            step = self.step_of(g, u, free)
            at_grant = u >= g - max(FREEZE_MB, 2 * sim_.tick * r.rate)
            if r.timed:
                if free >= min(step, 256.0):
                    take = min(step, free)
                    r.grant, free = g + take, free - take
                elif at_grant:
                    short.append(r)
                continue
            own = self.sa.get(id(r), 0.0) if 1 in self.parts else 0.0    # its step comes out of its own set-aside
            if free + own >= step:
                r.grant, free = g + step, free - max(0.0, step - own)
                continue
            if not (r.frozen or at_grant):
                continue                                # wants more, still has room of its own: runs on
            if 3 in self.parts and self.protected(sim_, r):
                got = self.make_room(sim_, r, step - free - own, real, val, stalled, dead, kills)
                if got is not None:
                    free += got - max(0.0, step - own)
                    r.grant = g + step
                    continue
            if r.frozen or self.can_freeze(sim_, r, real):
                stalled[id(r)] = r
            # else: inside its minimum run window, it runs on past its grant (the buffer covers it)
        # a job frozen lease_stall_s with nothing freeing: requeue a peer (furthest past --mem, else the newest)
        waited = [(r.wait_acc + (t - r.frozen_since if r.frozen else 0.0), r) for r in stalled.values()]
        waited = [(w, r) for w, r in waited if w >= STALL_S]
        if waited:
            _, s = max(waited, key=lambda x: (x[0], -x[1].job.jid))
            peers = [r for r in run if r.job.prio <= s.job.prio and not r.timed and id(r) not in dead]
            over = [r for r in peers if r.logical > r.job.tpl.mem_mb * OVERRUN]
            if over:
                v = max(over, key=lambda r: (r.logical - r.job.tpl.mem_mb, r.job.jid))
            else:
                others = [r for r in peers if r is not s]
                v = max(others, key=lambda r: (r.start, r.job.jid)) if others else None
            if v is not None:
                s.wait_acc = -(t - s.frozen_since) if s.frozen else 0.0     # its wait starts again
                kills.append((v, "victim"))
                dead.add(id(v))
                stalled.pop(id(v), None)
        # a timed job short of memory: requeue the newest batch job, a frozen one first
        if short and real <= buf and t - sim_.tpre_ts >= TIMED_PREEMPT:
            batch = [r for r in run if not r.timed and id(r) not in dead]
            if batch:
                v = max(batch, key=lambda r: (r.frozen, r.start, r.job.jid))
                kills.append((v, "timed_victim"))
                dead.add(id(v))
                stalled.pop(id(v), None)
                sim_.tpre_ts = t
        for v, why in kills:
            if v in sim_.running:
                sim_.kill(v, why)
        for r in list(sim_.running):
            if id(r) in stalled:
                sim_.freeze(r)
            elif r.frozen:
                sim_.thaw(r, self.window())
        frozen = [r for r in sim_.running if r.frozen]
        self.blocked, self.short = bool(frozen or short), bool(short)
        self.thaw_need = sum(r.zfree + self.step_of(r.grant, r.logical) for r in frozen)
        self.room = free
        return [v for v, _ in kills]

    def make_room(self, sim_, p, need, real, val, stalled, dead, kills):
        """Free `need` MB for protected job p: freeze + compress low-value unprotected batch jobs, then requeue
        unprotected jobs with the least invested work per MB. Returns MB freed (>= need), or None (nothing done)."""
        zroom = max(0.0, sim_.zram_cap - sim_.zram_used)
        cand = [r for r in sim_.running if r is not p and not r.timed and not r.frozen and id(r) not in stalled
                and id(r) not in dead and not self.protected(sim_, r) and self.can_freeze(sim_, r, real)]
        if val is not None:
            cand.sort(key=lambda r: (r.job.prio, val[id(r)], r.job.jid))
        else:
            cand.sort(key=lambda r: (r.job.prio, -r.start, r.job.jid))
        plan_f, plan_k, got = {}, [], 0.0           # id -> (run, MB its freeze frees)
        for r in cand:
            if got >= need:
                break
            pages = min(r.use, zroom)
            gain = pages * sim_.gain + HOLD * max(0.0, r.grant - r.logical)
            if gain <= 0:
                continue
            zroom -= pages
            plan_f[id(r)] = (r, gain)
            got += gain
        if got < need and self.requeue != "none":   # requeue (a planned freeze may become a requeue instead)
            kc = [r for r in sim_.running if r is not p and not r.timed and id(r) not in dead
                  and not self.protected(sim_, r) and r.job.preempts < sim.PROTECT_AFTER and r.use > 256
                  and (self.requeue == "all" or r.active < YOUNG_S)]
            kc.sort(key=lambda r: (r.invest / r.use, r.job.jid))
            for r in kc:
                if got >= need:
                    break
                unused = max(0.0, r.grant - r.logical)
                got += r.use + (unused if r.wall < sim.WARM_S else HOLD * unused)
                if id(r) in plan_f:
                    got -= plan_f.pop(id(r))[1]
                plan_k.append(r)
        if got < need:
            return None
        for r, _ in plan_f.values():
            r.grant = min(r.grant, r.logical)
            stalled[id(r)] = r
            sim_.freeze(r)                # compressed now, so its memory is free for p this tick
        for r in plan_k:
            kills.append((r, "room"))
            dead.add(id(r))
            stalled.pop(id(r), None)
        return got


def parse_policy(spec):
    """current | protect[:-K,...,T=GB,win=s,invest=core-h,value=est|oracle] | protect:parts=135"""
    name, _, arg = spec.partition(":")
    if name not in ("current", "protect"):
        raise ValueError(f"unknown policy {spec}")
    parts = set() if name == "current" else {1, 2, 3, 4, 5}
    kw = {}
    for a in filter(None, arg.split(",")):
        if a.startswith("-") and a[1:].isdigit():
            parts.discard(int(a[1:]))
        elif a.startswith("+") and a[1:].isdigit():
            parts.add(int(a[1:]))
        else:
            k, _, v = a.partition("=")
            if k == "parts":
                parts = {int(c) for c in v}
            elif k == "T":
                kw["T_gb"] = float(v)
            elif k == "win":
                kw["win"] = float(v)
            elif k == "invest":
                kw["invest_ch"] = float(v)
            elif k == "value":
                kw["value"] = v
            elif k == "sa":
                kw["sa"] = float(v)
            elif k == "requeue":
                kw["requeue"] = v
            else:
                raise ValueError(f"{name}: unknown option {k}")
    return lambda: FreezePolicy(parts, name=spec, **kw)


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


ABLATE = ["current", "protect", "protect:-1", "protect:-2", "protect:-3", "protect:-4", "protect:-5",
          "protect:T=4", "protect:T=16", "protect:win=0", "protect:win=120", "protect:win=600",
          "protect:value=oracle"]


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
