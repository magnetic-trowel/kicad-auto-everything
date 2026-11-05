# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402


class CpuAll:
    """Admits everything (to test CPU contention alone)."""
    name = "all"

    def prepare(self, s):
        pass

    def admit(self, s, job):
        return True

    def commit(self, s, job):
        pass


def flat(n, use=1024.0, cores=1.0, owner="o", cpus=1, mem=2048.0, **kw):
    return sim.Template(owner, cpus, mem, [use] * n, [cores] * n, **kw)


def test_loader_plain_and_gz(tmp_path):
    d = tmp_path / "traces"
    d.mkdir()
    t0 = 1_800_000_000
    hdr = dict(id=7, owner="a@main", name="x", cpus=4, mem_mb=8192, qos="timed", started=t0, timeout_s=600, prio=1)
    rows = [(10, 100, 0), (20, 200, 0), (30, 999, 1), (40, 300, 0), (50, 400, 0)]   # one frozen sample
    with open(d / "7.1.0.tsv", "w") as f:
        f.write(json.dumps(hdr) + "\n")
        for dt, use, fr in rows:
            f.write(f"{t0 + dt}\t{use * 1.2:.0f}\t{use}\t2.50\t0.010\t0.000\t{fr}\t{use * 2}\n")
        f.write("123\t4\n")                        # a line cut short is skipped
        f.write(f"# end ok {t0 + 50}\n")
    gz = sim.write_template_trace(str(d), flat(6, use=500.0, cores=3.0, owner="b", id=8))
    assert gz.endswith(".tsv.gz")
    sim.write_template_trace(str(d), flat(3, owner="c", id=9), state="requeued")
    with open(d / "10.1.0.tsv", "w") as f:            # still running: no end line
        f.write(json.dumps(dict(hdr, id=10)) + "\n")
        f.write(f"{t0 + 10}\t1\t1\t1\t0\t0\t0\t1\n")
    tpls, counts = sim.load_traces(str(d))
    assert counts == {"ok": 2, "requeued": 1, "running": 1}
    by = {t.id: t for t in tpls}
    a = by[7]
    assert (a.owner, a.cpus, a.mem_mb, a.prio, a.timeout_s) == ("a@main", 4, 8192, 1, 600)
    assert a.use == [100, 200, 300, 400]               # the frozen interval is not active time
    assert a.duration == 40 and a.frozen_s == 10
    assert a.cores == [2.5] * 4
    b = by[8]
    assert b.use == [500.0] * 6 and b.cores == [3.0] * 6 and b.duration == 60


def test_work_conserved_without_contention():
    t = flat(30, cores=4.0, cpus=4)
    s = sim.Sim([t], sim.Reserve(), sim.CpuDeclared(), ram_mb=10_000, cpus=8)
    m = s.run()
    assert m["jobs"] == 1 and m["makespan_h"] * 3600 == pytest.approx(t.duration)
    assert m["slow_mean"] == pytest.approx(1.0)
    assert m["useful_ch"] * 3600 == pytest.approx(4.0 * t.duration)
    assert m["lost_ch"] == 0


def test_cpu_contention_slows_everyone():
    ts = [flat(30, cores=8.0, cpus=8, id=i) for i in range(2)]   # 16 cores wanted, 8 there: half speed
    s = sim.Sim(ts, sim.Overcommit(1.0), CpuAll(), ram_mb=10_000, cpus=8, starts_per_tick=2)
    m = s.run()
    assert m["jobs"] == 2
    assert m["makespan_h"] * 3600 == pytest.approx(2 * ts[0].duration)
    assert m["slow_mean"] == pytest.approx(2.0)
    assert m["cpu_util"] == pytest.approx(1.0)


def test_reserve_never_overflows():
    ts = sim.synth_templates(80, seed=3, under=0.3)
    m = sim.simulate(ts, "reserve", "declared", ram_gb=100, cpus=64)
    assert m["jobs"] == 80
    assert m["overflow_n"] == 0 and m["oom"] == 0 and m["overflow_max_gb"] == 0
    assert m["limit"] > 0                     # under-declared jobs hit their reservation and are requeued


class AdmitAll(sim.MemPolicy):
    name = "all"


def test_overflow_is_counted_and_oom_kills_largest():
    big = sim.Template("o", 1, 1024, [500.0] * 3 + [5000.0] * 3, [1.0] * 6, id="big")
    small = flat(6, use=500.0, mem=1024.0, id="small")
    s = sim.Sim([big, small], AdmitAll(), CpuAll(), ram_mb=5000, cpus=8)
    m = s.run()
    assert m["oom"] == 1 and m["overflow_n"] == 1
    assert 0 < m["overflow_max_gb"] * 1024 <= 500.0 + 1e-6      # big + small - capacity at most
    assert m["jobs"] == 2 and m["lost_ch"] > 0                  # the killed job ran again


def test_sawtooth_overcommit_beats_reserve_on_ram():
    ts = sim.synth_templates(60, seed=5, under=0.0, mix=sim.sawtooth_mix())
    hist = sim.synth_templates(30, seed=6, under=0.0, mix=sim.sawtooth_mix(), prefix="h")
    res = {p: sim.simulate(ts, p, "burst", history=hist, ram_gb=120, cpus=200)
           for p in ("reserve", "overcommit:0.25", "predictive:H=300")}
    for p, m in res.items():
        assert m["jobs"] == 60, p
    assert res["overcommit:0.25"]["ram_util"] > res["reserve"]["ram_util"]
    assert res["predictive:H=300"]["ram_util"] > res["reserve"]["ram_util"]
    assert res["predictive:H=300"]["makespan_h"] < res["reserve"]["makespan_h"]


def test_eviction_picks_cheapest_per_mb():
    ts = [flat(100, use=1000.0, id=i, cpus=c) for i, c in enumerate((1, 4, 1, 1))]
    s = sim.Sim(ts, sim.Overcommit(0.25), CpuAll(), ram_mb=100_000, cpus=64)
    for j in s.pending:
        s.enqueue(j)
    runs = [s.start(j) for j in list(s.queue)]
    for r, (wall, use, pre) in zip(runs, ((600, 1000, 0), (100, 1000, 0), (100, 4000, 0), (10, 9000, 2))):
        r.wall, r.use, r.job.preempts = wall, use, pre
    s.used = sum(r.use for r in runs)
    # invest/MB: 0.6, 0.4, 0.025, (protected); the third is cheapest
    assert s.cheapest_victim() is runs[2]
    runs[2].use = 200                          # too small to be worth it
    assert s.cheapest_victim() is runs[1]
    s.cap, s.buffer = s.used + 100, 1000.0     # below half the buffer: evict, cheapest first
    out = s.fallback_evictions()
    assert out and out[0] is runs[1]
    assert runs[1].job in s.queue and s.queue[0] is runs[1].job and runs[1].job.preempts == 1


def test_deterministic_for_seed():
    def go(seed):
        ts = sim.synth_templates(40, seed=seed)
        hist = sim.synth_templates(20, seed=seed + 1, prefix="h")
        return [sim.simulate(ts, p, c, history=hist, ram_gb=150, cpus=64)
                for p in ("adaptive", "predictive:H=rest") for c in ("declared", "burst")]
    assert go(11) == go(11)
    assert go(11) != go(12)


def test_learner_growth_and_need():
    L = sim.Learner(min_jobs=3, horizon=60.0)
    assert L.growth("o", 0, 0, 0, 1000) is None and L.need("o", 1000) == 1000
    for i in range(10):        # ramp 0 -> 2000 over 10 samples, then flat; declared 1000 (2x under)
        L.add(sim.Template("o", 1, 1000, [200.0 * min(k + 1, 10) for k in range(30)], [1.0] * 30))
    assert L.need("o", 1000) == pytest.approx(2000)
    # a new job grows by 1200 MB in its first 60 s (only the first job learned it against --mem, not the 2x)
    m0, v0 = L.growth("o", 0.0, 0.0, 0.0, 1000)
    assert m0 == pytest.approx(1200, rel=0.15) and v0 ** 0.5 < 0.3 * m0
    m1, _ = L.growth("o", 250.0, 2000.0, 2000.0, 1000)
    assert m1 == pytest.approx(0, abs=1e-6)                                            # on the plateau


def test_policy_parsing():
    assert sim.split_policies("reserve,predictive:H=300,z=2,adaptive") == ["reserve", "predictive:H=300,z=2", "adaptive"]
    p = sim.parse_policy("predictive:H=rest,z=1.5")()
    assert p.H is None and p.z == 1.5 and not p.adapt
    assert sim.parse_policy("overcommit:0.5")().hold == 0.5
    assert sim.burst_fits([(2, 4)], (2, 6), 8.5) and not sim.burst_fits([(2, 4)], (2, 6), 8.0)
    with pytest.raises(ValueError):
        sim.parse_policy("nope")


def test_cli_runs(capsys):
    sim.main(["--synthetic", "20", "--seed", "2", "--policies", "reserve,predictive", "--cpu", "burst"])
    out = capsys.readouterr().out
    assert "reserve" in out and "predictive:H=300" in out


# ---------------------------------------------------------------- freezing batch jobs (sim_freeze)

import sim_freeze as sf  # noqa: E402


def freeze_setup(policy, cap_mb, jobs, win=300.0):
    """A FreezeSim with jobs started by hand: jobs = [(id, mem_mb, use, grant, wall)], all batch, all past warm-up.
    The buffer is the 4 GB minimum."""
    tpls = [flat(100, use=u, mem=m, id=i) for i, m, u, _, _ in jobs]
    pol = sf.parse_policy(policy)() if isinstance(policy, str) else policy
    s = sf.FreezeSim(tpls, pol, CpuAll(), ram_mb=cap_mb, cpus=64)
    for j in s.pending:
        s.enqueue(j)
    s.pending = []
    runs = [s.start(j) for j in list(s.queue)]
    for r, (_, _, u, g, wall) in zip(runs, jobs):
        r.use = r.peak = u
        r.grant, r.wall, r.active, r.p = g, wall, wall, wall
    s.used = sum(r.use for r in runs)
    s.t = 2000.0
    return s, runs


# a big (12 GB declared) job at its grant and three small ones with room in their grants; 6 GB really free
BIG_AND_SMALL = [("big", 12000, 9000.0, 9000.0, 1000.0)] + [(f"s{k}", 4000, 3000.0, 4000.0, 1000.0) for k in range(3)]


def test_current_freezes_big_job_at_its_grant():
    s, runs = freeze_setup("current", 24000, BIG_AND_SMALL)
    s.mem.on_tick(s)
    assert runs[0].frozen                                  # no whole step free: the big job waits frozen
    assert not any(r.frozen for r in runs[1:])


def test_protect_freezes_small_jobs_not_the_big_one():
    s, runs = freeze_setup("protect", 24000, BIG_AND_SMALL)
    runs[1].start = runs[1].start - 1                      # make s0 the least valuable (it has the most left)
    runs[1].p = 10.0
    s.mem.on_tick(s)
    big = runs[0]
    assert not big.frozen and big.grant > 9000.0           # it got its step
    frozen = [r for r in runs[1:] if r.frozen]
    assert frozen == [runs[1]]                             # one small job, the lowest value, was frozen
    assert frozen[0].zfree == pytest.approx(0.3 * 3000.0)  # and compressed: 30% of it freed
    assert s.used == pytest.approx(9000.0 + 3 * 3000.0 - 900.0)
    assert s.m["room"] == 0                                # freezing was enough: nobody requeued


def test_protect_without_part3_freezes_big_job():
    s, runs = freeze_setup("protect:-3", 24000, BIG_AND_SMALL)
    s.mem.on_tick(s)
    assert runs[0].frozen and not any(r.frozen for r in runs[1:])


def test_make_room_freeze_only_does_not_requeue():
    s, runs = freeze_setup("protect:requeue=none", 24000, BIG_AND_SMALL)
    s.zram_cap = 0.0                                       # freezing frees (almost) nothing, requeues are off
    s.mem.on_tick(s)
    assert runs[0].frozen and s.m["room"] == 0 and len(s.running) == 4


def test_make_room_requeues_when_freezing_is_not_enough():
    # zram full: freezing frees nothing, so the cheapest unprotected job is requeued for the big one
    s, runs = freeze_setup("protect", 24000, BIG_AND_SMALL)
    s.zram_cap = 0.0
    for r, w in zip(runs[1:], (900.0, 300.0, 600.0)):
        r.active = w
    s.mem.on_tick(s)
    assert not runs[0].frozen and runs[0].grant > 9000.0
    assert s.m["room"] == 1 and runs[2] not in s.running   # least invested work per MB
    assert runs[2].job in s.queue


def test_min_run_window():
    # one small job at its grant with nothing free; it was just thawed after 2000 s frozen
    jobs = [("a", 4000, 3000.0, 3000.0, 1000.0), ("b", 30000, 13000.0, 20000.0, 5000.0)]
    for pol, win in (("protect", 300.0), ("protect:win=600", 600.0)):
        s, (a, b) = freeze_setup(pol, 20500, jobs)
        a.frozen, a.frozen_since = True, s.t - 2000.0
        s.thaw(a, s.mem.window())
        assert a.guard_until == pytest.approx(s.t + max(win, 500.0))
        s.mem.on_tick(s)
        assert not a.frozen                                # inside its window: runs on past its grant
        s.t = a.guard_until + 2
        s.mem.on_tick(s)
        assert a.frozen                                    # after it: frozen again
    s, (a, b) = freeze_setup("protect:-4", 20500, jobs)    # no window: frozen at once
    a.frozen, a.frozen_since = True, s.t - 2000.0
    s.thaw(a, s.mem.window())
    s.mem.on_tick(s)
    assert a.frozen
    s, (a, b) = freeze_setup("protect", 20500, jobs)       # below half the buffer the window does not hold
    a.frozen, a.frozen_since = True, s.t - 2000.0
    s.thaw(a, s.mem.window())
    assert not s.mem.can_freeze(s, a, 3000.0)
    assert s.mem.can_freeze(s, a, 1000.0)                  # real free 1000 MB < buffer / 2


def test_protected_room_not_used_by_admission():
    # a protected job (expects 20 GB, uses 10) and 14 GB really free: a 6 GB job fits in what is free, not beside
    # the 10 GB the big one will grow into
    jobs = [("big", 20000, 10000.0, 11000.0, 1000.0)]
    new = flat(100, use=6000.0, mem=6000.0, id="new")
    for pol, ok in (("current", True), ("protect", False), ("protect:-1", False), ("protect:parts=1", False),
                    ("protect:-1,-5", True)):
        s, _ = freeze_setup(pol, 24000 + 4096, jobs)
        s.mem.on_tick(s)
        job = sim.Job(99, new)
        s.mem.prepare(s)
        assert s.mem.admit(s, job) is ok, pol


def test_big_job_waits_while_jobs_are_frozen_small_backfills():
    jobs = [("a", 4000, 3000.0, 3000.0, 1000.0), ("b", 4000, 3000.0, 4000.0, 1000.0)]
    small, big = flat(100, use=500.0, mem=500.0, id="sm"), flat(100, use=9000.0, mem=9000.0, id="bg")
    for pol, ok_small in (("current", False), ("protect", True)):
        s, (a, b) = freeze_setup(pol, 60000, jobs)
        s.mem.on_tick(s)
        s.freeze(a)                                        # a waits frozen
        s.mem.on_tick(s)
        s.freeze(a)
        s.mem.blocked = True
        s.mem.thaw_need = 4000.0
        s.mem.prepare(s)
        assert s.mem.admit(s, sim.Job(98, small)) is ok_small, pol
        assert not s.mem.admit(s, sim.Job(99, big)), pol


def test_freeze_policies_replay_synthetic():
    ts = sim.synth_templates(60, seed=4, under=0.0)
    hist = sim.synth_templates(30, seed=5, under=0.0, prefix="h")
    for p in ("current", "protect", "protect:-3,value=oracle"):
        m = sf.simulate(ts, p, history=hist, ram_gb=110, reserve_gb=30, cpus=96, timed="none")
        assert m["jobs"] == 60 and m["unfinished"] == 0, p
        assert m["overflow_n"] == 0, p
        assert sum(m[f"bin{b}"]["jobs"] for b in sf.BIN_NAMES) == 60


def test_freeze_policy_parsing():
    p = sf.parse_policy("protect:-2,-4,T=4,win=120,value=oracle")()
    assert p.parts == {1, 3, 5} and p.T == 4 * 1024 and p.win == 120 and p.value_mode == "oracle"
    assert sf.parse_policy("current")().parts == set()
    q = sf.parse_policy("protect:parts=134,requeue=none,sa=0.5")()
    assert q.parts == {1, 3, 4} and q.requeue == "none" and q.sa_frac == 0.5
    assert sf.parse_policy("protect:parts=13")().parts == {1, 3}
    with pytest.raises(ValueError):
        sf.parse_policy("protect:bogus=1")
    assert [sf.size_bin(x * 1024) for x in (1, 2, 8, 15.9, 16)] == ["<2", "2-8", "8-16", "8-16", ">16"]
