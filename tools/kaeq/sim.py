#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Trace-replay simulator for kaeq's memory and CPU admission policies.

Replays per-job resource curves (kaeq's traces, or a synthetic workload) through a discrete
2-s model of one shared host and compares admission/overcommit policies on throughput,
utilization, work lost to requeues and memory overflow (sum of use above capacity, which on
the real host is a kernel OOM).

    python3 tools/kaeq/sim.py --synthetic 300 --seed 1
    python3 tools/kaeq/sim.py --traces /var/tmp/$USER/kaeq/traces --policies reserve,adaptive,predictive
    python3 tools/kaeq/sim.py --traces DIR --eval-predictor        # calibration of the growth model

Model (see `Sim`): every 2-s tick (kaeq's) each running job advances along its template curve at the
rate CPU contention allows (all jobs slow by pool / cores wanted when the CPUs are oversubscribed);
its memory is the template's non-reclaimable use at its progress, interpolated between 10-s samples. Jobs are "timed": never frozen
or throttled. The only remedy for memory is to kill a job and requeue it (front of the queue,
preempts + 1; its work is lost). If the sum of use exceeds capacity anyway, that is an overflow:
the kernel kills the largest job (all of kaeq's jobs have oom_score_adj 1000).

Stdlib only; deterministic for a given seed.

Not modelled: anything faster than the 10-s samples (a spike between two samples is invisible); other
users' memory and CPU vary (here a constant); a job's own CPU demand when it was recorded under contention
(its curve and duration include that slowdown); a timed job's budget shrinking under contention (reported as
slowdown, its resource curve does not change); work that survives a restart (checkpoints); freezing batch jobs
(sim_freeze.py extends this engine with them).
"""
import argparse
import bisect
import gzip
import json
import math
import os
import random
import sys
import time
from collections import deque

DT = 10.0              # trace sample interval, s (kaeq writes one every ~10 s)
TICK = 2.0             # simulation tick, s (kaeq's daemon tick)
WARM_S = 120.0         # kaeq lease_warm_s: a young job's unused grant counts in full
WARMUP_S = 300.0       # kaeq warmup_s: no grant trims before this; CPU measured after this
BUFFER_MIN_MB = 4096.0  # kaeq lease_buffer_gb
BUFFER_TICKS = 3       # kaeq lease_buffer_ticks
GROWTH_WINDOW_S = 600  # the buffer looks back on the fleet's growth over 10 min
PROTECT_AFTER = 2      # kaeq evict_protect_after
LOSS_TARGET = 0.02     # kaeq overcommit_loss_target
LOSS_WINDOW_S = 21600  # kaeq overcommit_window_s
ADAPT_EVERY_S = 600    # kaeq overcommit_every_s


# ---------------------------------------------------------------- templates and loading

class Template:
    """One job's resource curve: use[k], cores[k] for the k-th DT of active (unfrozen) time."""
    __slots__ = ("id", "owner", "name", "cpus", "mem_mb", "prio", "timeout_s", "started", "use", "cores",
                 "state", "frozen_s")

    def __init__(self, owner, cpus, mem_mb, use, cores, id=None, name="", prio=0, timeout_s=None,
                 started=0.0, state="ok", frozen_s=0.0):
        self.id, self.owner, self.name = id, owner, name
        self.cpus, self.mem_mb, self.prio = float(cpus), float(mem_mb), prio
        self.timeout_s, self.started, self.state, self.frozen_s = timeout_s, started, state, frozen_s
        self.use, self.cores = list(use), list(cores)

    @property
    def duration(self):
        return len(self.use) * DT

    @property
    def peak(self):
        return max(self.use)


def read_trace(path):
    """(header dict, [(t, rss, use, cores, wait, stall, frozen, grant)], (state, t) or None) of one trace file."""
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt") as f:
        lines = f.read().splitlines()
    hdr = json.loads(lines[0])
    samples, end = [], None
    for ln in lines[1:]:
        if ln.startswith("#"):
            p = ln.split()
            if len(p) >= 3 and p[1] == "end":
                end = (p[2], float(p[3]) if len(p) > 3 else None)
            continue
        f = ln.split("\t")
        if len(f) < 8:
            continue                      # empty, or cut short by a daemon that died mid-write
        try:
            samples.append(tuple(float(x) for x in f[:8]))
        except ValueError:
            continue
    return hdr, samples, end


def trace_template(hdr, samples, state):
    """A Template from one attempt's samples. Frozen samples are dropped and their time removed: a frozen job
    makes no progress, so the curve is over active time (what the job needs when it is never frozen)."""
    if not samples:
        return None
    prev = hdr.get("started") or samples[0][0] - DT
    act, acts, pts, frozen_s = 0.0, [], [], 0.0
    for t, _rss, use, cores, _w, _s, frozen, _g in samples:
        dt = max(0.0, t - prev)
        prev = t
        if frozen:
            frozen_s += dt
            continue
        act += dt
        acts.append(act)
        pts.append((use, cores))
    if not pts:
        return None
    n = max(1, int(round(act / DT)))
    use, cores = [], []
    for k in range(n):               # the sample whose interval covers the end of step k
        i = min(bisect.bisect_left(acts, (k + 1) * DT - 1e-6), len(pts) - 1)
        use.append(max(0.0, pts[i][0]))
        cores.append(max(0.0, pts[i][1]))
    return Template(hdr.get("owner") or "?", hdr.get("cpus") or 1, hdr.get("mem_mb") or 1024, use, cores,
                    id=hdr.get("id"), name=hdr.get("name") or "", prio=hdr.get("prio") or 0,
                    timeout_s=hdr.get("timeout_s"), started=hdr.get("started") or samples[0][0],
                    state=state, frozen_s=frozen_s)


def load_traces(d, states=("ok", "timeout")):
    """Templates from a traces directory, oldest start first, and counts {state: attempts}.
    Only attempts that ended in `states` are templates: `ok` ran to the end; `timeout` ran its whole budget, so
    its curve is what that job costs. Attempts requeued/preempted/failed/cancelled are cut short (their curve
    would teach the predictor that jobs end early) and are only counted. An attempt still running has no end
    line and is skipped."""
    out, counts = [], {}
    for fn in sorted(os.listdir(d)):
        if not (fn.endswith(".tsv") or fn.endswith(".tsv.gz")):
            continue
        try:
            hdr, samples, end = read_trace(os.path.join(d, fn))
        except (OSError, ValueError, EOFError):
            counts["unreadable"] = counts.get("unreadable", 0) + 1
            continue
        st = end[0] if end else "running"
        counts[st] = counts.get(st, 0) + 1
        if st in states:
            t = trace_template(hdr, samples, st)
            if t is not None:
                out.append(t)
    out.sort(key=lambda t: (t.started or 0.0, str(t.id)))
    return out, counts


def write_template_trace(d, tpl, attempt=1, preempts=0, t0=1.8e9, state="ok"):
    """Write a Template in kaeq's trace format (for tests, and to time the loader on real-sized sets)."""
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{tpl.id}.{attempt}.{preempts}.tsv.gz")
    with gzip.open(path, "wt") as f:
        f.write(json.dumps(dict(id=tpl.id, owner=tpl.owner, name=tpl.name, cpus=tpl.cpus, mem_mb=tpl.mem_mb,
                                qos="timed", started=t0, timeout_s=tpl.timeout_s, prio=tpl.prio)) + "\n")
        for k, (u, c) in enumerate(zip(tpl.use, tpl.cores)):
            f.write(f"{t0 + (k + 1) * DT:.0f}\t{u * 1.1:.0f}\t{u:.0f}\t{c:.2f}\t0.000\t0.000\t0\t{u * 1.25:.0f}\n")
        f.write(f"# end {state} {t0 + tpl.duration:.0f}\n")
    return path


# ---------------------------------------------------------------- synthetic workload

def _noise(rng, x, s):
    return max(0.0, x * rng.gauss(1.0, s))


def curve_sawtooth(rng, peak, n, cpus, low=0.6):
    """Physics-like: ramp to `low` x peak over ~1 min, then saw up to the peak and drop, every 30-60 s;
    CPU high while memory climbs (a field solve), lower at the drop (a zone refill)."""
    period, off, ramp = rng.choice((30.0, 40.0, 60.0)), rng.random(), rng.uniform(40, 90)
    use, cores = [], []
    for k in range(n):
        t = (k + 1) * DT
        if t < ramp:
            u, c = low * peak * t / ramp, cpus * 0.5
        else:
            ph = ((t - ramp) / period + off) % 1.0
            u, c = peak * (low + (1 - low) * ph), cpus * (0.4 + 0.6 * ph)
        use.append(_noise(rng, u, 0.02))
        cores.append(min(cpus * 1.1, _noise(rng, c, 0.1)))
    return use, cores


def curve_ramp(rng, peak, n, cpus):
    """Ramp up over 20-50 % of the run, then a plateau (routers, placers)."""
    r = max(1, int(n * rng.uniform(0.2, 0.5)))
    eff = rng.uniform(0.6, 1.0)
    use = [_noise(rng, peak * min(1.0, (k + 1) / r) ** 0.7, 0.03) for k in range(n)]
    cores = [min(cpus * 1.1, _noise(rng, cpus * eff, 0.1)) for _ in range(n)]
    return use, cores


def curve_spike(rng, peak, n, cpus):
    """Flat at a third to a fifth of the peak, then a spike to the peak for 1-3 min late in the run (DRC)."""
    base = peak / rng.uniform(3, 5)
    s0 = int(n * rng.uniform(0.75, 0.9))
    s1 = min(n, s0 + rng.randint(6, 18))
    use, cores = [], []
    for k in range(n):
        if s0 <= k < s1:
            u, c = peak, cpus
        else:
            u, c = base * min(1.0, (k + 1) / 6), cpus * 0.6
        use.append(_noise(rng, u, 0.03))
        cores.append(min(cpus * 1.1, _noise(rng, c, 0.1)))
    return use, cores


# owner -> (share, curve, cpus choices, peak GB range, duration min range)
MIX = {
    "physics": (0.25, curve_sawtooth, (16,), (20, 60), (15, 45)),
    "route": (0.45, curve_ramp, (4, 6, 8), (3, 8), (5, 25)),
    "drc": (0.20, curve_spike, (8,), (6, 20), (10, 30)),
    "small": (0.10, curve_ramp, (1, 2), (0.5, 2), (1, 5)),
}


def synth_templates(n, seed=0, under=0.08, mix=None, prefix="s"):
    """n synthetic job templates from owners with curve families (`MIX`), noise, and declared --mem of
    1.0-1.5x the true peak, except `under` of them declare a quarter of it."""
    rng = random.Random(seed)
    mix = mix or MIX
    owners = list(mix)
    w = [mix[o][0] for o in owners]
    out = []
    for i in range(n):
        o = rng.choices(owners, w)[0]
        _, fn, cpus_c, (p0, p1), (d0, d1) = mix[o]
        cpus = rng.choice(cpus_c)
        peak = rng.uniform(p0, p1) * 1024
        steps = max(2, int(rng.uniform(d0, d1) * 60 / DT))
        use, cores = fn(rng, peak, steps, cpus)
        true_peak = max(use)
        decl = true_peak * rng.uniform(1.0, 1.5)
        if rng.random() < under:
            decl = true_peak / 4
        decl = max(512.0, math.ceil(decl / 512) * 512)
        out.append(Template(o, cpus, decl, use, cores, id=f"{prefix}{i}", name=f"{o}-{i}",
                            timeout_s=steps * DT * 2, started=float(i)))
    return out


def sawtooth_mix():
    """A workload of only physics-like sawtooth jobs (for tests)."""
    return {"physics": (1.0, curve_sawtooth, (8,), (10, 30), (5, 10))}


# ---------------------------------------------------------------- learning from finished jobs

def quantile(xs, q):
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, int(math.ceil(q * len(s))) - 1))]


def mean_var(xs):
    m = sum(xs) / len(xs)
    return m, sum((x - m) ** 2 for x in xs) / len(xs)


AGE_EDGES = (0, 30, 60, 120, 300, 600, 1200, 2400, 4800)     # s: dense early (warm-up), sparse late
FRAC_EDGES = (0, .05, .1, .2, .35, .5, .65, .8, .9, 1.0)


class Owner:
    def __init__(self):
        self.n = 0
        self.ratio = []          # peak / declared --mem
        self.dur = []
        self.cmean, self.cpeak = [], []
        self.samples = {}        # bin -> deque of growth / ref
        self.cache = {}


class Learner:
    """What finished jobs teach about their owner's next ones (all from completed templates, like kaeq).
    `need`: declared --mem x the owner's p95 peak/--mem (kaeq's scaling), once `min_jobs` have finished.
    `growth`: distribution of a running job's FUTURE growth over a horizon H (s; None = the rest of the job),
    max(use over the next H) - current use, as a ratio to ref = max(peak so far, expected size), where the
    expected size is --mem x the owner's median peak/--mem. Binned by absolute age (or by age as a fraction of
    the owner's median duration, bins='frac')."""

    def __init__(self, min_jobs=5, horizon=300.0, bins="abs", max_samples=5000, norm="ref"):
        self.min_jobs, self.H, self.bins, self.max_samples = min_jobs, horizon, bins, max_samples
        self.norm = norm             # "ref": growth / ref (scale-free across job sizes); "abs": growth in MB
        self.owners = {}

    def _o(self, owner):
        return self.owners.setdefault(owner, Owner())

    def ready(self, owner):
        o = self.owners.get(owner)
        return o is not None and o.n >= self.min_jobs

    def need(self, owner, declared):
        o = self.owners.get(owner)
        if o is None or o.n < self.min_jobs:
            return declared
        return max(256.0, declared * quantile(o.ratio, 0.95))

    def est_size(self, owner, declared):
        o = self.owners.get(owner)
        if o is None or not o.ratio:
            return declared
        return declared * quantile(o.ratio, 0.5)

    def cpu_est(self, owner, cpus):
        """(mean, peak) cores of the owner's next job: median of finished jobs' mean, p90 of their peaks."""
        o = self.owners.get(owner)
        if o is None or o.n < self.min_jobs:
            return float(cpus), float(cpus)
        return quantile(o.cmean, 0.5), quantile(o.cpeak, 0.9)

    def _bin(self, o, age, dur=None):
        if self.bins == "frac":
            d = dur or (quantile(o.dur, 0.5) if o.dur else 3600.0)
            return bisect.bisect_right(FRAC_EDGES, age / max(DT, d)) - 1
        return bisect.bisect_right(AGE_EDGES, age) - 1

    def add(self, tpl):
        o = self._o(tpl.owner)
        est = self.est_size(tpl.owner, tpl.mem_mb)
        use, n = tpl.use, len(tpl.use)
        if self.H is None:                                 # max over the rest of the job
            fmax = use[:]
            for k in range(n - 2, -1, -1):
                fmax[k] = max(fmax[k], fmax[k + 1])
        else:                                              # sliding max over the next w steps
            w = max(1, int(round(self.H / DT)))
            fmax, dq = [0.0] * n, deque()
            for k in range(n - 1, -1, -1):
                while dq and use[dq[-1]] <= use[k]:
                    dq.pop()
                dq.append(k)
                while dq[0] >= k + w:
                    dq.popleft()
                fmax[k] = use[dq[0]]
        stride = max(1, n // 300)
        peak = 0.0
        for k in range(n):
            # at progress k*DT a running job has measured use[k-1] and peak max(use[:k]); age 0 is a new job
            cur = use[k - 1] if k else 0.0
            peak = max(peak, cur)
            if k % stride:
                continue
            ref = max(peak, est, 1.0) if self.norm == "ref" else 1.0
            r = max(0.0, fmax[k] - cur) / ref
            b = self._bin(o, k * DT, tpl.duration if self.bins == "frac" else None)
            for key in (b, "all"):
                dq_ = o.samples.get(key)
                if dq_ is None:
                    dq_ = o.samples[key] = deque(maxlen=self.max_samples)
                dq_.append(r)
        o.ratio.append(tpl.peak / max(1.0, tpl.mem_mb))
        o.dur.append(tpl.duration)
        o.cmean.append(sum(tpl.cores) / len(tpl.cores))
        o.cpeak.append(max(tpl.cores))
        o.n += 1
        o.cache = {}

    def growth(self, owner, age, use, peak, declared):
        """(mean, variance) MB of a job's growth over the horizon, or None without enough history."""
        o = self.owners.get(owner)
        if o is None or o.n < self.min_jobs:
            return None
        b = self._bin(o, age)
        st = o.cache.get(b)
        if st is None:
            xs = o.samples.get(b)
            if not xs or len(xs) < 20:
                xs = o.samples["all"]
            st = o.cache[b] = mean_var(xs)
        ref = max(peak, self.est_size(owner, declared), 1.0) if self.norm == "ref" else 1.0
        return ref * st[0], ref * ref * st[1]


# ---------------------------------------------------------------- engine

class Job:
    __slots__ = ("jid", "tpl", "arrival", "prio", "seq", "preempts", "need_fix", "queued_at", "first_start")

    def __init__(self, jid, tpl, arrival=0.0, seq=0):
        self.jid, self.tpl, self.arrival, self.prio, self.seq = jid, tpl, arrival, tpl.prio, seq
        self.preempts, self.need_fix, self.queued_at, self.first_start = 0, None, arrival, None


class Run:
    __slots__ = ("job", "start", "p", "wall", "use", "peak", "core_s", "grant", "limit", "slack_since", "hist")

    def __init__(self, job, t, hist_len):
        self.job, self.start, self.p, self.wall = job, t, 0.0, 0.0
        self.use = self.peak = self.core_s = 0.0
        self.grant, self.limit, self.slack_since = 0.0, None, 0.0
        self.hist = deque(maxlen=hist_len)          # cores actually used per tick, last 10 min

    @property
    def invest(self):
        """What a restart throws away, as kaeq counts it: active seconds x declared CPUs."""
        return self.wall * max(1.0, self.job.tpl.cpus)


def use_at(tpl, p):
    """(use MB, cores wanted) of a template at progress p (s). Sample k is the state at the end of its interval,
    (k + 1) x DT; use is interpolated linearly between samples (from 0 at the start), cores are the interval's."""
    x = p / DT
    k = int(x)
    n = len(tpl.use)
    if k >= n:
        return tpl.use[-1], tpl.cores[-1]
    lo = tpl.use[k - 1] if k else 0.0
    return lo + (tpl.use[k] - lo) * (x - k), tpl.cores[k]


class Sim:
    """One replay at kaeq's tick (2 s; traces are interpolated between their 10-s samples). mem/cpu: policy
    objects (see MemPolicy). ram_mb/cpus: what jobs may use beyond the reserve; other_mb/other_cpus: other
    users' steady use of it (taken first). Per tick, like kaeq: at most `starts_per_tick` jobs start and the
    eviction fallback requeues at most one job; the buffer is `buffer_ticks` x the fleet's largest growth in
    one tick over 10 min ("pos": each job's rise summed, as kaeq; "net": the change of the fleet's total)."""

    def __init__(self, templates, mem, cpu, ram_mb=221 * 1024, cpus=118, learner=None, arrivals=None,
                 other_mb=0.0, other_cpus=0.0, tick=TICK, starts_per_tick=1, hol_s=600.0, max_t=30 * 86400.0,
                 buffer_ticks=BUFFER_TICKS, growth="pos"):
        self.cap = ram_mb - other_mb
        self.pool = cpus - other_cpus
        self.mem, self.cpu = mem, cpu
        self.learner = learner or Learner(horizon=getattr(mem, "H", 300.0))
        self.tick, self.starts_per_tick, self.hol_s, self.max_t = float(tick), starts_per_tick, hol_s, max_t
        self.win = max(1, int(round(GROWTH_WINDOW_S / self.tick)))
        self.buffer_ticks, self.growth_mode = buffer_ticks, growth
        arr = arrivals or [0.0] * len(templates)
        self.unrunnable = [t for t in templates if t.peak > self.cap]
        jobs = [Job(i, t, a, i) for i, (t, a) in enumerate(zip(templates, arr)) if t.peak <= self.cap]
        self.pending = sorted(jobs, key=lambda j: (j.arrival, j.seq))
        self.queue, self.running = [], []
        self.t = 0.0
        self.front = 0
        self.growth = deque(maxlen=self.win)
        self.buffer = BUFFER_MIN_MB
        self.used = 0.0                 # sum of running jobs' last measured use, MB
        self.contended = False
        self.done_cs = self.lost_invest = 0.0       # kaeq's accounting (declared CPUs x active s)
        self.m = dict(finished=0, evict=0, limit=0, oom=0, forced=0, overflow_n=0, overflow_mbs=0.0,
                      overflow_max=0.0, ram_int=0.0, cpu_int=0.0, busy_s=0.0, busy_ram=0.0, busy_cpu=0.0,
                      useful_cs=0.0, lost_cs=0.0, slow=[], wait=[], makespan=0.0)

    # ---- queue
    def need(self, job):
        n = job.need_fix if job.need_fix is not None else self.learner.need(job.tpl.owner, job.tpl.mem_mb)
        return min(n, self.cap)

    def enqueue(self, job, front=False):
        if front:
            self.front += 1
            job.seq = -self.front
        job.queued_at = self.t
        self.queue.append(job)
        self.queue.sort(key=lambda j: (-j.prio, j.seq))

    def start(self, job):
        self.queue.remove(job)
        r = Run(job, self.t, self.win)
        if job.first_start is None:
            job.first_start = self.t
            self.m["wait"].append(self.t - job.arrival)
        self.running.append(r)
        self.mem.start(self, r)
        return r

    def kill(self, r, why):
        """Requeue a running job at the front of the queue; its work is lost."""
        self.running.remove(r)
        self.used -= r.use
        self.m[why] += 1
        self.m["lost_cs"] += r.core_s
        self.lost_invest += r.invest
        r.job.preempts += 1
        self.mem.on_kill(self, r, why)
        self.enqueue(r.job, front=True)

    def cheapest_victim(self):
        """The running job whose restart loses the least invested work per MB it frees (kaeq lease_plan evict);
        jobs requeued PROTECT_AFTER times, and small ones, are spared."""
        cand = [r for r in self.running if r.job.preempts < PROTECT_AFTER and r.use > 256]
        return min(cand, key=lambda r: (r.invest / r.use, r.job.jid)) if cand else None

    def fallback_evictions(self, per_tick=1):
        """Below half the buffer of real free memory, evict the cheapest job (kaeq: one per tick)."""
        out = []
        while self.cap - self.used < self.buffer / 2 and len(out) < per_tick:
            v = self.cheapest_victim()
            if v is None:
                break
            out.append(v)
            self.kill(v, "evict")
        return out

    # ---- the loop
    def admit_all(self):
        if not self.queue:
            return
        self.mem.prepare(self)
        self.cpu.prepare(self)
        strict = self.t - self.queue[0].queued_at > self.hol_s   # a head waiting long blocks backfill
        started = 0
        seen = set()
        for job in list(self.queue):
            if started >= self.starts_per_tick:
                break
            key = (job.tpl.owner, job.tpl.mem_mb, job.tpl.cpus, job.need_fix)
            if key in seen:               # a job like one that did not fit does not fit either
                continue
            if self.mem.admit(self, job) and self.cpu.admit(self, job):
                self.mem.commit(self, job)
                self.cpu.commit(self, job)
                self.start(job)
                started += 1
            elif strict:
                break
            else:
                seen.add(key)
        if not started and not self.running:         # nothing runs and nothing fits: run the head alone
            self.m["forced"] += 1
            self.start(self.queue[0])

    def step(self):
        """The interval [t, t + tick]."""
        dt = self.tick
        cur = []
        for r in list(self.running):
            u, c = use_at(r.job.tpl, r.p)
            if r.limit is not None and u > r.limit:      # a hard limit (memory.max) kills at once
                self.kill(r, "limit")
                continue
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
            if r.wall >= WARM_S:
                grew += max(0.0, u - r.use) if self.growth_mode == "pos" else u - r.use
            r.use = u
            r.peak = max(r.peak, u)
            r.core_s += c * f * dt
            r.hist.append(c * f)
            r.p += dt * f
            r.wall += dt
            used += u
            self.done_cs += max(1.0, r.job.tpl.cpus) * dt
        self.used = used
        self.growth.append(grew)
        self.buffer = max(BUFFER_MIN_MB, self.buffer_ticks * max(self.growth))
        self.m["ram_int"] += U * dt
        self.m["cpu_int"] += C * f * dt
        if self.queue:                    # jobs waited: what the policy left unused (not the drain-out tail)
            self.m["busy_s"] += dt
            self.m["busy_ram"] += U * dt
            self.m["busy_cpu"] += C * f * dt

    def finish(self):
        for r in [r for r in self.running if r.p >= r.job.tpl.duration - 1e-6]:
            self.running.remove(r)
            self.used -= r.use
            self.m["finished"] += 1
            self.m["useful_cs"] += r.core_s
            self.m["slow"].append(r.wall / r.job.tpl.duration)
            self.m["makespan"] = self.t
            self.learner.add(r.job.tpl)

    def run(self):
        while True:
            while self.pending and self.pending[0].arrival <= self.t:
                self.enqueue(self.pending.pop(0))
            if not (self.queue or self.running or self.pending) or self.t >= self.max_t:
                break
            if not self.queue and not self.running:      # idle until the next arrival
                self.t = math.ceil(self.pending[0].arrival / self.tick) * self.tick
                continue
            self.admit_all()
            self.step()
            self.t += self.tick
            self.finish()
            self.mem.on_tick(self)
        return self.metrics()

    def metrics(self):
        m = self.m
        span = max(self.tick, m["makespan"] or self.t)
        slow = m["slow"]
        return dict(
            jobs=m["finished"], unfinished=len(self.queue) + len(self.running) + len(self.pending),
            unrunnable=len(self.unrunnable), makespan_h=span / 3600, jobs_per_h=m["finished"] / (span / 3600),
            ram_util=m["ram_int"] / (self.cap * span), cpu_util=m["cpu_int"] / (self.pool * span),
            ram_busy=m["busy_ram"] / (self.cap * max(self.tick, m["busy_s"])),
            cpu_busy=m["busy_cpu"] / (self.pool * max(self.tick, m["busy_s"])),
            useful_ch=m["useful_cs"] / 3600, lost_ch=m["lost_cs"] / 3600,
            lost_pct=m["lost_cs"] / max(1.0, m["useful_cs"]), evict=m["evict"], limit=m["limit"], oom=m["oom"],
            forced=m["forced"], overflow_n=m["overflow_n"], overflow_gbs=m["overflow_mbs"] / 1024,
            overflow_max_gb=m["overflow_max"] / 1024, slow_mean=sum(slow) / len(slow) if slow else 1.0,
            slow_p95=quantile(slow, 0.95) if slow else 1.0,
            wait_mean_h=sum(m["wait"]) / len(m["wait"]) / 3600 if m["wait"] else 0.0,
            final_knob=self.mem.knob())


# ---------------------------------------------------------------- memory policies

class MemPolicy:
    """Admission is two-phase: prepare(sim) once per tick, admit(sim, job) -> bool (no side effects; the CPU
    side must agree too), then commit(sim, job) when it starts. start(sim, run) sets the run's grant/limit;
    on_tick(sim) runs after each tick and returns the runs it evicted (sim.kill); on_kill(sim, run, why)."""
    name = "?"
    H = 300.0

    def prepare(self, sim):
        pass

    def admit(self, sim, job):
        return True

    def commit(self, sim, job):
        pass

    def start(self, sim, run):
        run.grant = sim.need(run.job)

    def on_tick(self, sim):
        return []

    def on_kill(self, sim, run, why):
        pass

    def knob(self):
        return ""


class Reserve(MemPolicy):
    """Slurm-style: each job's need (owner's learned p95 peak, else declared) is reserved for its whole run and
    is its hard limit; a job over it is killed and requeued needing 1.5x its limit."""
    name = "reserve"

    def prepare(self, sim):
        self.res = sum(r.grant for r in sim.running)

    def admit(self, sim, job):
        return self.res + sim.need(job) <= sim.cap

    def commit(self, sim, job):
        self.res += sim.need(job)

    def start(self, sim, run):
        run.grant = run.limit = sim.need(run.job)

    def on_kill(self, sim, run, why):
        if why == "limit":
            run.job.need_fix = min(sim.cap, run.limit * 1.5)


class LossCtl:
    """kaeq.adapt_hold's evidence: work lost to requeues over LOSS_WINDOW_S as a share of the work done
    (declared CPUs x active s), sampled every ADAPT_EVERY_S; None until a core-hour of work."""

    def __init__(self):
        self.hist = []

    def loss(self, sim):
        if self.hist and sim.t - self.hist[-1][0] < ADAPT_EVERY_S:
            return None
        self.hist.append((sim.t, sim.done_cs, sim.lost_invest))
        while self.hist and self.hist[0][0] < sim.t - 2 * LOSS_WINDOW_S:
            self.hist.pop(0)
        old = [h for h in self.hist if h[0] >= sim.t - LOSS_WINDOW_S]
        if len(old) < 2 or old[-1][1] - old[0][1] < 3600:
            return None
        return (old[-1][2] - old[0][2]) / (old[-1][1] - old[0][1])


class Overcommit(MemPolicy):
    """kaeq's lease scheme for timed jobs: a grant starts at the job's need, grows when use nears it (never
    refused: timed jobs are not frozen), is trimmed when far above use. Unused grant counts `hold` as taken
    (young jobs in full); new jobs start from capacity - use - held - buffer; below half the buffer of real
    free memory the cheapest job is evicted."""

    def __init__(self, hold=0.25):
        self.hold = hold
        self.name = f"overcommit:{hold:g}"

    def held(self, sim):
        return sum(max(0.0, r.grant - r.use) * (1.0 if r.wall < WARM_S else self.hold) for r in sim.running)

    def prepare(self, sim):
        self.free = sim.cap - sim.used - self.held(sim) - sim.buffer

    def admit(self, sim, job):
        return sim.need(job) <= self.free

    def commit(self, sim, job):
        self.free -= sim.need(job)

    def grants(self, sim):
        for r in sim.running:
            g, u = r.grant, r.use
            if u >= g - max(512.0, 0.15 * g):                         # lease_margin: grow
                r.grant = g + max(1024.0, 0.25 * g, u + 512.0 - g)
                r.slack_since = 0.0
            elif r.wall >= WARMUP_S and g - u > max(2048.0, 0.25 * u):  # lease_release: trim after 2 min
                r.slack_since = r.slack_since or sim.t
                if sim.t - r.slack_since >= 120:
                    r.grant = min(g, max(u * 1.25, u + 1024.0))
                    r.slack_since = 0.0
            else:
                r.slack_since = 0.0

    def adapt(self, sim):
        pass

    def on_tick(self, sim):
        self.grants(sim)
        self.adapt(sim)
        return sim.fallback_evictions()

    def knob(self):
        return f"h={self.hold:.2f}"


class Adaptive(Overcommit):
    """Overcommit with hold adapted like kaeq.adapt_hold: +0.1 above the lost-work target, -0.05 below half."""

    def __init__(self, hold=1.0):
        super().__init__(hold)
        self.name = f"adaptive:{hold:g}" if hold != 1.0 else "adaptive"
        self.ctl = LossCtl()

    def adapt(self, sim):
        loss = self.ctl.loss(sim)
        if loss is None:
            return
        if loss > LOSS_TARGET:
            self.hold = min(1.0, self.hold + 0.1)
        elif loss < LOSS_TARGET / 2:
            self.hold = max(0.0, self.hold - 0.05)


class Predictive(MemPolicy):
    """Admit when the running jobs' predicted growth over the horizon H (mean + z standard deviations of the
    sum; jobs of different owners independent, of one owner correlated rho) plus the new job's predicted peak
    over H fit in real free memory above the eviction threshold (half the buffer). Owners without min_jobs finished jobs count their rest
    of need in full. Eviction fallback as overcommit; z adapts to the lost-work target unless adapt=0."""

    def __init__(self, H=300.0, z=2.0, rho=0.2, adapt=True, bins="abs", norm="ref"):
        self.H, self.z, self.rho, self.adapt, self.bins, self.norm = H, z, rho, adapt, bins, norm
        hs = "rest" if H is None else f"{H:g}"
        self.name = f"predictive:H={hs}" + ("" if adapt else f",z={z:g}") + (f",rho={rho:g}" if rho != 0.2 else "") \
            + ("" if bins == "abs" else f",bins={bins}") + ("" if norm == "ref" else f",norm={norm}")
        self.ctl = LossCtl()

    def pred(self, sim, job, age, use, peak):
        g = sim.learner.growth(job.tpl.owner, age, use, peak, job.tpl.mem_mb)
        if g is None:
            return max(0.0, sim.need(job) - use), 0.0
        return g

    def prepare(self, sim):
        # the predicted growth over H is the room set aside for growth; what must stay free after it is only
        # the eviction threshold (half the buffer), so the buffer is not counted twice
        self.free = sim.cap - sim.used - sim.buffer / 2
        self.mu, self.own = 0.0, {}
        for r in sim.running:
            m, v = self.pred(sim, r.job, r.p, r.use, r.peak)
            self.mu += m
            o = self.own.setdefault(r.job.tpl.owner, [0.0, 0.0])
            o[0] += v
            o[1] += v ** 0.5

    def _var(self, own):
        return sum((1 - self.rho) * v + self.rho * s * s for v, s in own.values())

    def _with(self, sim, job):
        m, v = self.pred(sim, job, 0.0, 0.0, 0.0)
        own = dict(self.own)
        o = own.get(job.tpl.owner, [0.0, 0.0])
        own[job.tpl.owner] = [o[0] + v, o[1] + v ** 0.5]
        return m, own

    def admit(self, sim, job):
        m, own = self._with(sim, job)
        return self.mu + m + self.z * self._var(own) ** 0.5 <= self.free

    def commit(self, sim, job):
        m, self.own = self._with(sim, job)
        self.mu += m

    def on_tick(self, sim):
        if self.adapt:
            loss = self.ctl.loss(sim)
            if loss is not None:
                if loss > LOSS_TARGET:
                    self.z = min(6.0, self.z + 0.5)
                elif loss < LOSS_TARGET / 2:
                    self.z = max(0.0, self.z - 0.25)
        return sim.fallback_evictions()

    def knob(self):
        return f"z={self.z:.2f}"


# ---------------------------------------------------------------- CPU policies

def burst_fits(jobs, new, cap):
    """kaeq.burst_fits: means add up, bursts (peak - mean) pool as independent."""
    allj = list(jobs) + [new]
    return sum(m for m, _ in allj) + sum(max(0.0, p - m) ** 2 for m, p in allj) ** 0.5 <= cap


class CpuDeclared:
    """Admit while the declared --cpus of running jobs fit in the pool."""
    name = "declared"

    def prepare(self, sim):
        self.sum = sum(r.job.tpl.cpus for r in sim.running)

    def admit(self, sim, job):
        return self.sum + job.tpl.cpus <= sim.pool

    def commit(self, sim, job):
        self.sum += job.tpl.cpus


class CpuBurst:
    """kaeq's measured CPU admission: running jobs' mean cores over the last 10 min plus their bursts pooled
    (burst_fits); young jobs and the new one use their owner's (median mean, p90 peak), else --cpus. No start
    while the last tick was oversubscribed (kaeq: no starts while threads queue for a CPU)."""
    name = "burst"

    def _est(self, sim, r):
        if r.wall < WARMUP_S or not r.hist:
            return sim.learner.cpu_est(r.job.tpl.owner, r.job.tpl.cpus)
        h = r.hist
        return sum(h) / len(h), max(h)

    def prepare(self, sim):
        self.mean = self.sq = 0.0
        for r in sim.running:
            m, p = self._est(sim, r)
            self.mean += m
            self.sq += max(0.0, p - m) ** 2

    def admit(self, sim, job):
        if sim.contended:
            return False
        m, p = sim.learner.cpu_est(job.tpl.owner, job.tpl.cpus)
        return self.mean + m + (self.sq + max(0.0, p - m) ** 2) ** 0.5 <= sim.pool

    def commit(self, sim, job):
        m, p = sim.learner.cpu_est(job.tpl.owner, job.tpl.cpus)
        self.mean += m
        self.sq += max(0.0, p - m) ** 2


# ---------------------------------------------------------------- CLI

def parse_policy(spec):
    """reserve | overcommit[:h] | adaptive[:h0] |
    predictive[:H=300|rest,z=2,rho=0.2,adapt=1,bins=abs|frac,norm=ref|abs] (a z given fixes z unless adapt=1)"""
    name, _, arg = spec.partition(":")
    if name == "reserve":
        return Reserve
    if name == "overcommit":
        h = float(arg) if arg else 0.25
        return lambda: Overcommit(h)
    if name == "adaptive":
        h = float(arg) if arg else 1.0
        return lambda: Adaptive(h)
    if name == "predictive":
        kw = dict(H=300.0, z=2.0, rho=0.2, adapt=True, bins="abs", norm="ref")
        for a in filter(None, arg.split(",")):
            k, _, v = a.partition("=")
            if k == "H":
                kw["H"] = None if v == "rest" else float(v)
            elif k in ("z", "rho"):
                kw[k] = float(v)
            elif k == "adapt":
                kw["adapt"] = v not in ("0", "false", "no")
            elif k in ("bins", "norm"):
                kw[k] = v
            else:
                raise ValueError(f"predictive: unknown option {k}")
        if "z=" in arg and "adapt=" not in arg:
            kw["adapt"] = False          # a z given explicitly is fixed
        return lambda: Predictive(**kw)
    raise ValueError(f"unknown policy {spec}")


CPUS = {"declared": CpuDeclared, "burst": CpuBurst}


def split_policies(s):
    """'reserve,predictive:H=300,z=2,adaptive' -> ['reserve', 'predictive:H=300,z=2', 'adaptive']: a token with
    '=' and no ':' is an option of the policy before it."""
    out = []
    for tok in filter(None, s.split(",")):
        if "=" in tok and ":" not in tok and out:
            out[-1] += "," + tok
        else:
            out.append(tok)
    return out


def simulate(templates, policy, cpu="burst", history=(), ram_gb=221.0, cpus=118, arrivals=None, other_gb=0.0,
             min_jobs=5, buffer_ticks=BUFFER_TICKS, growth="pos", tick=TICK):
    """Run one replay; returns the metrics dict with the policy names added."""
    mem = parse_policy(policy)() if isinstance(policy, str) else policy
    learner = Learner(min_jobs=min_jobs, horizon=getattr(mem, "H", 300.0), bins=getattr(mem, "bins", "abs"),
                      norm=getattr(mem, "norm", "ref"))
    for t in history:
        learner.add(t)
    sim = Sim(templates, mem, CPUS[cpu](), ram_mb=ram_gb * 1024, cpus=cpus, learner=learner,
              arrivals=arrivals, other_mb=other_gb * 1024, buffer_ticks=buffer_ticks, growth=growth, tick=tick)
    m = sim.run()
    m["policy"], m["cpu"] = mem.name, cpu
    return m


def _sim_job(a):
    return simulate(*a[0], **a[1])


COLS = (("policy", "policy", "{}"), ("cpu", "cpu", "{}"), ("jobs", "jobs", "{}"), ("makespan_h", "span_h", "{:.2f}"),
        ("jobs_per_h", "jobs/h", "{:.1f}"), ("ram_util", "ram%", "{:.0%}"), ("cpu_util", "cpu%", "{:.0%}"),
        ("ram_busy", "ram%q", "{:.0%}"), ("cpu_busy", "cpu%q", "{:.0%}"),
        ("lost_ch", "lost_ch", "{:.1f}"), ("lost_pct", "lost%", "{:.1%}"), ("evict", "evict", "{}"),
        ("limit", "limkill", "{}"), ("oom", "oom", "{}"), ("overflow_n", "ovf_n", "{}"),
        ("overflow_gbs", "ovf_GBs", "{:.0f}"), ("overflow_max_gb", "ovf_maxGB", "{:.1f}"),
        ("slow_mean", "slow", "{:.2f}"), ("slow_p95", "slow95", "{:.2f}"), ("wait_mean_h", "wait_h", "{:.2f}"),
        ("final_knob", "knob", "{}"))


def table(rows):
    cells = [[h for _, h, _ in COLS]] + [[fmt.format(r[k]) for k, _, fmt in COLS] for r in rows]
    w = [max(len(c[i]) for c in cells) for i in range(len(COLS))]
    return "\n".join("  ".join(c[i].ljust(w[i]) if i < 2 else c[i].rjust(w[i]) for i in range(len(COLS)))
                     for c in cells)


def eval_predictor(templates, H=300.0, bins="abs", z=2.0, min_jobs=5, norm="ref"):
    """Calibration of the growth model per owner: train on each owner's first half, test on the second.
    Per test sample (age, use so far): is the actual growth over H <= mean + z sd? Also the mean predicted
    upper bound vs the 'full' fallback (need - use) that counts every job's rest of need."""
    by = {}
    for t in templates:
        by.setdefault(t.owner, []).append(t)
    L = Learner(min_jobs=min_jobs, horizon=H, bins=bins, norm=norm)
    tests = []
    for o, ts in by.items():
        h = len(ts) // 2
        for t in ts[:h]:
            L.add(t)
        tests += ts[h:]
    rows = {}
    for t in tests:
        if not L.ready(t.owner):
            continue
        n = len(t.use)
        w = n if H is None else max(1, int(round(H / DT)))
        peak = 0.0
        acc = rows.setdefault(t.owner, [0, 0, 0.0, 0.0, 0.0])
        for k in range(0, n, max(1, n // 60)):
            cur = t.use[k - 1] if k else 0.0
            peak = max(t.use[:k]) if k else 0.0
            g = max(0.0, max(t.use[k:k + w]) - cur)
            m, v = L.growth(t.owner, k * DT, cur, peak, t.mem_mb)
            acc[0] += 1
            acc[1] += g <= m + z * v ** 0.5 + 1e-9
            acc[2] += g
            acc[3] += m + z * v ** 0.5
            acc[4] += max(0.0, L.need(t.owner, t.mem_mb) - cur)
    lines = [f"growth over {'rest of job' if H is None else f'{H:g} s'}, bins={bins}, norm={norm}, z={z:g}",
             "owner      samples  covered  actual_GB  pred_GB  full_GB"]
    for o, (n, c, g, p, f) in sorted(rows.items()):
        lines.append(f"{o[:10]:10} {n:7d}  {c / n:7.1%}  {g / n / 1024:9.2f}  {p / n / 1024:7.2f}  {f / n / 1024:7.2f}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--traces", help="kaeq traces directory (<id>.<attempt>.<preempts>.tsv[.gz])")
    src.add_argument("--synthetic", type=int, metavar="N", help="N synthetic jobs")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--history", type=int, default=None,
                    help="synthetic: finished jobs the queue learned from before (default N/2)")
    ap.add_argument("--history-frac", type=float, default=0.25,
                    help="traces: the oldest share of templates only trains the learner (default 0.25)")
    ap.add_argument("--states", default="ok,timeout", help="trace end states used as templates")
    ap.add_argument("--under", type=float, default=0.08, help="synthetic: share of jobs declaring 1/4 of peak")
    ap.add_argument("--ram-gb", type=float, default=221.0, help="RAM for jobs (251 GB - 30 GB reserve)")
    ap.add_argument("--other-gb", type=float, default=0.0, help="other users' steady use of that RAM")
    ap.add_argument("--cpus", type=float, default=118)
    ap.add_argument("--policies", default="reserve,overcommit:0.25,adaptive,predictive:H=300,predictive:H=rest")
    ap.add_argument("--cpu", default="declared,burst", help="CPU admission modes to cross with the policies")
    ap.add_argument("--arrivals", default="backlog", help="backlog | trace (original start times) | poisson:JOBS_PER_H")
    ap.add_argument("--tick", type=float, default=TICK, help="simulation tick, s (kaeq: 2)")
    ap.add_argument("--buffer-ticks", type=float, default=BUFFER_TICKS,
                    help="growth buffer = this x the fleet's largest growth in one tick over 10 min (kaeq: 3)")
    ap.add_argument("--growth", default="pos", choices=("pos", "net"),
                    help="fleet growth for the buffer: sum of jobs' rises (kaeq) or net change of the total")
    ap.add_argument("-j", type=int, default=1, help="parallel replays")
    ap.add_argument("--json", help="write the metrics rows to this file")
    ap.add_argument("--write-traces", metavar="DIR", help="synthetic: also write the jobs as kaeq traces")
    ap.add_argument("--eval-predictor", action="store_true", help="print the growth model's calibration and exit")
    a = ap.parse_args(argv)

    t0 = time.time()
    if a.traces:
        tpls, counts = load_traces(a.traces, tuple(a.states.split(",")))
        h = int(len(tpls) * a.history_frac)
        history, tpls = tpls[:h], tpls[h:]
        print(f"loaded {len(tpls) + len(history)} templates ({len(history)} history) in {time.time() - t0:.1f} s; "
              f"attempts by end state: {counts}", file=sys.stderr)
    else:
        tpls = synth_templates(a.synthetic, a.seed, a.under)
        nh = a.synthetic // 2 if a.history is None else a.history
        history = synth_templates(nh, a.seed + 1000003, a.under, prefix="h")
        if a.write_traces:
            for t in tpls:
                write_template_trace(a.write_traces, t)
    if not tpls:
        sys.exit("no templates")
    if a.eval_predictor:
        for H in (300.0, None):
            for bins, norm in (("abs", "ref"), ("frac", "ref"), ("abs", "abs")):
                print(eval_predictor(history + tpls, H, bins, norm=norm))
                print()
        return
    if a.arrivals == "backlog":
        arr = None
    elif a.arrivals == "trace":
        t_0 = min(t.started for t in tpls)
        arr = [t.started - t_0 for t in tpls]
    elif a.arrivals.startswith("poisson:"):
        rate = float(a.arrivals.split(":")[1]) / 3600
        rng, t, arr = random.Random(a.seed + 7), 0.0, []
        for _ in tpls:
            t += rng.expovariate(rate)
            arr.append(t)
    else:
        sys.exit(f"unknown --arrivals {a.arrivals}")
    jobs = [((tpls, p, c, history, a.ram_gb, a.cpus, arr, a.other_gb), dict(buffer_ticks=a.buffer_ticks,
                                                                            growth=a.growth, tick=a.tick))
            for p in split_policies(a.policies) for c in a.cpu.split(",")]
    t1 = time.time()
    if a.j > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(a.j) as ex:
            rows = list(ex.map(_sim_job, jobs))
    else:
        rows = [_sim_job(x) for x in jobs]
    peak_sum = sum(t.peak for t in tpls) / 1024
    print(f"{len(tpls)} jobs, {len(history)} history, RAM {a.ram_gb - a.other_gb:g} GB, {a.cpus:g} CPUs; "
          f"{len(rows)} replays in {time.time() - t1:.1f} s (sum of peaks {peak_sum:.0f} GB)")
    print(table(rows))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
