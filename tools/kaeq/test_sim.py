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
