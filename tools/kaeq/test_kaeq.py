# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
import json
import os
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture
def kq(tmp_path, monkeypatch):
    monkeypatch.setenv("KAEQ_HOME", str(tmp_path))
    monkeypatch.setenv("KAEQ_OWNER", "t")
    sys.path.insert(0, HERE)
    import kaeq
    importlib.reload(kaeq)
    with open(kaeq.CONF, "w") as f:
        f.write('{"threads": 4, "reserve_cpu": 1, "reserve_mem_gb": 0, "cgroup": "off", "scratch_dir": "%s"}'
                % (tmp_path / "scratch"))
    yield kaeq
    sys.path.remove(HERE)


def submit(kq, cmd, **kw):
    ns = dict(qos="timed", batch=None, jobs=None, command=[cmd], env=None, owner=None, name=None, tag=None, cwd=None, cpus=1.0, mem="50M",
              disk="10M", timeout="1m", prio=0, retries=0, live=False, link=None)
    ns.update(kw)
    import argparse
    kq.ensure_daemon = lambda: None  # tests drive ticks themselves
    kq.cmd_submit(argparse.Namespace(**ns))


def drive(kq, d, until, secs=15):
    end = time.time() + secs
    while time.time() < end:
        d.tick()
        if until():
            return
        time.sleep(0.2)
    raise AssertionError("timeout")


def joblog(path):
    """A job's log without kaeq's own === lines."""
    return "\n".join(l for l in path.read_text().splitlines() if not l.startswith("=== "))


def states(d):
    return {r["name"]: r["state"] for r in d.c.execute("SELECT name,state FROM jobs")}


def test_ok_fail_timeout_and_events(kq):
    d = kq.Daemon()
    submit(kq, "echo hi", name="ok")
    submit(kq, "echo 'Traceback: boom'; exit 3", name="bad")
    submit(kq, "sleep 30", name="slow", timeout="1s")
    drive(kq, d, lambda: all(s not in kq.ACTIVE for s in states(d).values()))
    assert states(d) == {"ok": "ok", "bad": "failed", "slow": "timeout"}
    msgs = [r["msg"] for r in d.c.execute("SELECT * FROM events")]
    assert any("Traceback: boom" in m for m in msgs)
    assert any(m.startswith("all jobs finished") for m in msgs)


def test_memory_gate_and_backfill(kq):
    d = kq.Daemon()
    free = kq.meminfo()["MemAvailable"]
    submit(kq, "sleep 5", name="huge", mem=f"{free * 2}M")
    submit(kq, "sleep 1", name="small")
    drive(kq, d, lambda: states(d).get("small") == "running" or states(d).get("small") == "ok")
    assert states(d)["huge"] == "queued"


def test_starving_head_lets_only_short_owners_backfill(kq):
    d = kq.Daemon()
    free = kq.meminfo()["MemAvailable"]
    submit(kq, "sleep 5", name="huge", mem=f"{free * 2}M", owner="big")
    submit(kq, "sleep 1", name="slowpoke", owner="slow")
    submit(kq, "sleep 1", name="quick", owner="fast")
    old = time.time() - 3600
    d.c.execute("UPDATE jobs SET submitted=?", (old,))  # every job has waited past starve_after_s
    for i in range(5):  # history: "fast" jobs end in 10 s, "slow" ones take an hour
        for owner, dur in (("fast", 10), ("slow", 3600)):
            d.c.execute("INSERT INTO jobs (owner,cmd,cpus,mem_mb,timeout_s,prio,state,attempt,retries_left,preempts,"
                        "submitted,started,finished,not_before,disk_mb) VALUES (?,'x',1,1,60,0,'ok',1,0,0,?,?,?,0,1)",
                        (owner, old, old, old + dur))
    d.c.commit()
    drive(kq, d, lambda: states(d).get("quick") in ("running", "ok"))
    assert states(d)["slowpoke"] == "queued" and states(d)["huge"] == "queued"
    d.c.execute("UPDATE jobs SET state='cancelled' WHERE state IN ('queued','running')")
    d.c.commit()


def test_overrun_requeues_with_larger_mem(kq):
    d = kq.Daemon()
    submit(kq, "python3 -c 'x=bytearray(1300*1024*1024); import time; time.sleep(30)'", name="hog", mem="50M")
    drive(kq, d, lambda: d.c.execute("SELECT mem_mb FROM jobs").fetchone()[0] > 1500)
    d.c.execute("UPDATE jobs SET state='cancelled' WHERE 1")


def test_retry_only_own_failures(kq):
    d = kq.Daemon()
    submit(kq, "exit 1", name="mine")
    submit(kq, "exit 1", name="theirs", owner="other")
    drive(kq, d, lambda: all(s not in kq.ACTIVE for s in states(d).values()))
    import argparse
    kq.cmd_retry(argparse.Namespace(ids=[], owner=None, tag=None, mem=None, cpus=None, timeout=None, disk=None, retries=0))
    assert states(d) == {"mine": "queued", "theirs": "failed"}


def test_snapshot_isolates_code_from_later_checkouts(kq, tmp_path):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    run("init", "-q"), run("config", "user.email", "t@t"), run("config", "user.name", "t")
    (repo / "sub" / "f.txt").write_text("v1")
    (repo / "data").mkdir()
    (repo / ".gitignore").write_text("data/\n")
    (repo / "data" / "big").write_text("ignored-input")
    run("add", "-A"), run("commit", "-qm", "c")
    (repo / "sub" / "f.txt").write_text("v1-dirty")  # uncommitted edit must be captured
    d = kq.Daemon()
    submit(kq, "cat f.txt; echo; cat ../data/big", name="j", cwd=str(repo / "sub"), link=["data"])
    (repo / "sub" / "f.txt").write_text("v2-after-submit")  # later edit/checkout must not leak in
    drive(kq, d, lambda: all(s not in kq.ACTIVE for s in states(d).values()))
    assert states(d) == {"j": "ok"}
    log = joblog(tmp_path / "jobs" / "1" / "log")
    assert log.split() == ["v1-dirty", "ignored-input"]
    assert not (tmp_path / "jobs" / "1" / "src").exists()


def test_scratch_dir_per_job_is_removed(kq, tmp_path):
    d = kq.Daemon()
    submit(kq, 'echo "$KAEQ_SCRATCH"; test "$TMPDIR" = "$KAEQ_SCRATCH" && dd if=/dev/zero of=$KAEQ_SCRATCH/f bs=1M count=2 2>/dev/null',
           name="s")
    drive(kq, d, lambda: all(s not in kq.ACTIVE for s in states(d).values()))
    assert states(d) == {"s": "ok"}
    path = joblog(tmp_path / "jobs" / "1" / "log").split()[0]
    assert path == str(tmp_path / "scratch" / "1")
    assert not os.path.exists(path)


def test_disk_budget_gates_admission(kq):
    with open(kq.CONF, "w") as f:
        f.write('{"threads": 4, "reserve_cpu": 1, "reserve_mem_gb": 0, "cgroup": "off", "scratch_gb": 1, "scratch_dir": "%s"}'
                % os.path.join(kq.HOME, "scratch"))
    d = kq.Daemon()
    submit(kq, "sleep 3", name="a", disk="700M")
    submit(kq, "sleep 1", name="b", disk="700M")
    drive(kq, d, lambda: states(d)["a"] == "running")
    d.tick()
    assert states(d)["b"] == "queued"  # 700M + 700M > 1G budget
    drive(kq, d, lambda: states(d)["b"] in ("running", "ok"))


def test_affinity_pins_jobs_and_reserves_cpus(kq, tmp_path):
    d = kq.Daemon()
    submit(kq, "python3 -c 'import os; print(len(os.sched_getaffinity(0)))'", name="p")
    drive(kq, d, lambda: all(s not in kq.ACTIVE for s in states(d).values()))
    n = int(joblog(tmp_path / "jobs" / "1" / "log").split()[0])
    assert n == min(4, len(os.sched_getaffinity(0))) - 1  # threads 4, reserve_cpu 1


def test_reserve_defaults_to_a_fraction(kq):
    with open(kq.CONF, "w") as f:
        f.write('{"threads": 10}')
    cfg = kq.config()
    assert cfg["reserve_cpu"] == 2
    assert abs(cfg["reserve_mem_gb"] - kq.meminfo()["MemTotal"] / 1024 * 0.2) < 0.1


def test_jobs_jsonl_carries_per_job_resources(kq, tmp_path):
    f = tmp_path / "jobs.jsonl"
    f.write_text('{"cmd": "true", "name": "x", "cpus": 2, "mem": "3G", "disk": "5G", "timeout": "2h"}\n'
                 '{"cmd": "true", "name": "y"}\n')
    submit(kq, None, command=[], jobs=str(f), mem="1G", disk="1G")
    c = kq.db()
    rows = {r["name"]: r for r in c.execute("SELECT * FROM jobs")}
    assert (rows["x"]["cpus"], rows["x"]["mem_mb"], rows["x"]["disk_mb"], rows["x"]["timeout_s"]) == (2, 3072, 5120, 7200)
    assert (rows["y"]["mem_mb"], rows["y"]["disk_mb"]) == (1024, 1024)


def test_kill_reaches_children_in_their_own_session(kq, tmp_path):
    # without a scope (cgroup off) only the process group is killed; with one, the whole scope
    d = kq.Daemon()
    if not d.use_cgroup(dict(kq.config(), cgroup="auto")):
        pytest.skip("no systemd --user memory cgroup")
    with open(kq.CONF, "w") as f:
        f.write('{"threads": 4, "reserve_cpu": 1, "reserve_mem_gb": 0, "cgroup": "on", "slice": "", "scratch_dir": "%s"}'
                % (tmp_path / "scratch"))
    marker = tmp_path / "orphan-alive"
    submit(kq, f"setsid sh -c 'sleep 3; touch {marker}' & sleep 30", name="o", timeout="2s")
    drive(kq, d, lambda: states(d)["o"] == "timeout")
    time.sleep(4)
    assert not marker.exists()


def test_one_daemon_holds_the_lock(kq):
    lk = kq.take_lock()
    assert lk is not None
    r = subprocess.run([sys.executable, "-c", "import kaeq, sys; sys.exit(0 if kaeq.take_lock() is None else 1)"],
                       env=dict(os.environ, PYTHONPATH=HERE), capture_output=True)
    assert r.returncode == 0  # a second process cannot take it
    r = subprocess.run([sys.executable, "-c", "import kaeq, sys; sys.exit(0 if kaeq.daemon_status() is not None else 1)"],
                       env=dict(os.environ, PYTHONPATH=HERE), capture_output=True)
    assert r.returncode == 0  # held lock = a daemon runs, whatever pids say (POSIX locks are per process)
    lk.close()


def test_client_refuses_a_missing_db_when_a_backup_exists(kq):
    kq.db().close()
    os.replace(kq.DB, kq.DB_BACKUP)
    for ext in ("-wal", "-shm"):
        if os.path.exists(kq.DB + ext):
            os.unlink(kq.DB + ext)
    with pytest.raises(SystemExit):
        kq.db()
    kq.db(restore=True).close()  # the daemon restores it
    assert os.path.exists(kq.DB)


def test_reservation_drops_to_observed_peak_after_warmup(kq):
    with open(kq.CONF, "w") as f:
        f.write('{"threads": 4, "reserve_cpu": 1, "reserve_mem_gb": 0, "cgroup": "off", "warmup_s": 1, "scratch_dir": "%s"}'
                % os.path.join(kq.HOME, "scratch"))
    d = kq.Daemon()
    submit(kq, "sleep 20", name="w", mem="10G")
    drive(kq, d, lambda: states(d)["w"] == "running")
    d.tick()
    assert d.sys["unrealized"] > 9 * 1024  # declared 10G held while it warms up (10G: the test host may be busy)
    time.sleep(1.5)
    d.tick()
    assert d.sys["unrealized"] < 1024  # then only its (tiny) observed peak with a margin
    d.c.execute("UPDATE jobs SET state='cancelled' WHERE 1")


def test_pooled_headroom_sets_aside_less_when_peaks_are_rare(kq):
    B = kq.MEM_BINS
    always_top = [0.0] * (B - 1) + [1.0]
    brief_peak = [0.9 / (B // 4)] * (B // 4) + [0.0] * (B - B // 4 - 1) + [0.1]  # 90% of life low, 10% at peak
    jobs = [("a", 2000.0, 400.0, None)] * 3
    assert kq.pooled_headroom(jobs, 3, 0.5) == (4800.0, 4800.0)  # unknown jobs count in full
    jobs = [("a", 2000.0, 400.0, always_top)] * 10
    aside, worst = kq.pooled_headroom(jobs, 3, 0.5)
    assert worst == 16000.0 and aside == worst  # jobs that sit at their peak: nothing to pool
    jobs = [(f"o{i}", 2000.0, 400.0, brief_peak) for i in range(20)]
    aside, worst = kq.pooled_headroom(jobs, 3, 0.5)
    assert 1600.0 <= aside < 0.5 * worst  # independent owners, rare peaks: well under the sum, >= one job's headroom
    lock = kq.pooled_headroom([("one", 2000.0, 400.0, brief_peak)] * 20, 3, 1.0)[0]
    assert lock > aside  # the same jobs in lockstep need more


def test_finished_job_records_its_memory_histogram(kq):
    d = kq.Daemon()
    submit(kq, "python3 -c 'import time; b = bytearray(60 << 20); time.sleep(70)'", name="h", timeout="3m")
    drive(kq, d, lambda: states(d)["h"] == "ok", secs=120)
    h = json.loads(d.c.execute("SELECT mem_hist FROM jobs WHERE name='h'").fetchone()[0])
    assert len(h) == kq.MEM_BINS and sum(h) >= 6 and h[-1] > 0


def test_owner_correlation_is_measured_from_concurrent_jobs(kq):
    import math
    import random
    rnd = random.Random(1)
    wave = [1000 + 500 * math.sin(i / 5) for i in range(90)]
    lockstep = [[w * f for w in wave] for f in (1.0, 1.5, 0.7, 2.0)]
    rho, n = kq.owner_correlation(lockstep, 0.5)
    assert n == 6 and rho > 0.85
    noise = [[1000 + rnd.gauss(0, 200) for _ in range(90)] for _ in range(6)]
    rho, n = kq.owner_correlation(noise, 0.5)
    assert n == 15 and rho < 0.2
    assert kq.owner_correlation([[5.0] * 90] * 3, 0.5) == (0.5, 0)  # flat jobs: no evidence, the prior
    jobs = [("lm", 2000.0, 400.0, [1 / kq.MEM_BINS] * kq.MEM_BINS)] * 9
    assert kq.pooled_headroom(jobs, 3, 0.5, {"lm": 0.0})[0] < kq.pooled_headroom(jobs, 3, 0.5)[0]


def test_admission_learns_what_an_owners_jobs_really_use(kq):
    d = kq.Daemon()
    old = time.time() - 3600
    for i in range(25):  # history: owner "x" declares 10G and peaks at 1-2G
        d.c.execute("INSERT INTO jobs (owner,cmd,cpus,mem_mb,timeout_s,prio,state,attempt,retries_left,preempts,"
                    "submitted,started,finished,not_before,disk_mb,peak_mb) VALUES ('x','x',1,10240,60,0,'ok',1,0,0,?,?,?,0,1,?)",
                    (old, old, old + 10, 1024 + 40 * i))
    submit(kq, "true", owner="x", mem="10G")  # ratios are learned for owners with work queued
    cfg = kq.config()
    d.learn_ratios(cfg, time.time())
    need = d.need_mb({"owner": "x", "mem_mb": 10240}, cfg)
    assert need == pytest.approx(1504 * 1.1)  # median peak/--mem (1504/10240) x 1.1 margin, not the declared 10G
    assert d.need_mb({"owner": "new", "mem_mb": 10240}, cfg) == 10240  # no history: what it asked for


def test_max_rise_finds_the_largest_growth_within_a_window(kq):
    s = [(0, 0.0), (10, 5.0), (20, 2.0), (30, 9.0), (40, 1.0), (50, 4.0), (60, 20.0)]
    assert kq.max_rise(s, 100) == 20.0  # 0 at t=0 -> 20 at t=60
    assert kq.max_rise(s, 20) == 19.0   # 1 at t=40 -> 20 at t=60
    assert kq.max_rise(s, 10) == 16.0   # 4 -> 20
    assert kq.max_rise([(0, 5.0), (10, 3.0)], 60) == 0.0  # shrinking is no rise


def test_warm_jobs_count_their_owners_spread_of_sizes(kq):
    rs = [0.2] * 18 + [1.0, 1.1]  # most jobs use a fifth of --mem, a few all of it
    jobs = [(100.0, 7900.0, 8000.0, rs)] * 10
    aside = kq.warm_headroom(jobs, 2)
    assert 7900.0 <= aside < 0.6 * 79000.0  # >= one job's full headroom, well under all ten at their worst
    assert kq.warm_headroom([(100.0, 7900.0, 8000.0, None)] * 10, 2) == 79000.0  # unknown owner: in full


def test_no_start_while_threads_queue_for_a_cpu(kq):
    clock = [0]

    def idle_cpus():  # the test machine may be busy: report it idle, so only the run queue decides
        clock[0] += 4000
        return 0, clock[0]
    kq.cpu_ticks = idle_cpus
    conf = json.load(open(kq.CONF)); conf.update(runq_window_s=1, heavy_boost=False)   # a short window; no fillers
    json.dump(conf, open(kq.CONF, "w"))
    d = kq.Daemon()
    submit(kq, "sleep 20", name="busy", qos="batch")
    drive(kq, d, lambda: states(d)["busy"] == "running")  # (with nothing running, one job always starts)
    kq.runnable_threads = lambda: 50  # 4 threads, 1 reserved: 50 runnable threads is oversubscribed
    submit(kq, "true", name="wait", qos="batch")
    for _ in range(10):
        d.tick()
        time.sleep(0.1)
    assert states(d)["wait"] == "queued"
    # a timed job is not held back by batch jobs' threads: it takes their cycles (they are SCHED_IDLE)
    submit(kq, "true", name="timed")
    drive(kq, d, lambda: states(d)["timed"] in ("running", "ok"))
    assert states(d)["wait"] == "queued"
    kq.runnable_threads = lambda: 0
    drive(kq, d, lambda: states(d)["wait"] in ("running", "ok"))
    d.c.execute("UPDATE jobs SET state='cancelled' WHERE state IN ('queued','running')")
    d.c.commit()


def test_batch_jobs_run_at_sched_idle_timed_jobs_above_them(kq, tmp_path):
    d = kq.Daemon()
    submit(kq, f"ps -o ni=,cls= -p $$ > {tmp_path / 'b'}", name="b", qos="batch")
    submit(kq, f"ps -o ni=,cls= -p $$ > {tmp_path / 't'}", name="t")
    drive(kq, d, lambda: all(v == "ok" for v in states(d).values()))
    # light (--mem 50M, no history): one step down from the start; timed at timed_nice + 1
    ni, cls = (tmp_path / "b").read_text().split()
    assert cls == "IDL" and ni in ("19", "-")
    assert (tmp_path / "t").read_text().split() == ["11", "TS"]
    submit(kq, f"ps -o ni=,cls= -p $$ > {tmp_path / 'bh'}", name="bh", qos="batch", mem="16G")   # heavy: a step up
    drive(kq, d, lambda: states(d)["bh"] in ("ok", "queued") and (tmp_path / "bh").exists() or states(d)["bh"] == "ok")
    assert (tmp_path / "bh").read_text().split() == ["19", "TS"]
    conf = json.load(open(kq.CONF)); conf["heavy_boost"] = False; json.dump(conf, open(kq.CONF, "w"))
    submit(kq, f"ps -o ni=,cls= -p $$ > {tmp_path / 'b2'}", name="b2", qos="batch")
    drive(kq, d, lambda: states(d)["b2"] == "ok")
    ni, cls = (tmp_path / "b2").read_text().split()
    assert cls == "IDL" and ni in ("19", "-")  # without the boost: SCHED_IDLE (ps may print "-" for its nice)


LEASE = dict(lease_margin_frac=0.15, warmup_s=300, lease_release_frac=0.25, mem_overrun=1.5, lease_release_gb=2.0, lease_release_after_s=120, lease_margin_mb=512, lease_step_gb=1.0,
             lease_step_frac=0.25, lease_stall_s=900)


def plan(kq, jobs, free, cfg, now, buffer=0.0):
    """lease_plan given memory nobody holds (the old meaning): real free memory = that + every unused grant."""
    return kq.lease_plan(jobs, free + sum(max(0.0, j["grant"] - j["use"]) for j in jobs), cfg, now, buffer)


def test_lease_plan_grows_by_priority_trims_idle_grants_and_stalls_the_rest(kq):
    jobs = [dict(id=1, prio=0, started=10, grant=4096, use=4000),     # at its grant
            dict(id=2, prio=0, started=20, grant=4096, use=3900),     # at its grant, younger
            dict(id=3, prio=0, started=5, grant=20480, use=1024, slack_since=1.0)]  # holds far more than it uses
    assert plan(kq, jobs, 500.0, LEASE, now=200.0)["grants"][3] == 20480   # under 5 min old: kept
    p = plan(kq, jobs, 500.0, LEASE, now=400.0)
    assert p["grants"][3] == pytest.approx(2048)            # trimmed to use + 1 GB: 18 GB freed
    # plenty free (the 18 GB trimmed): each grows by half its grant, well ahead of a fast-growing job
    assert p["grants"][1] == pytest.approx(4096 + 2048)
    assert p["grants"][2] == pytest.approx(4096 + 2048)
    # a job within 15% of its grant already gets more (here 3500 of 4096: within 614 MB)
    q = plan(kq, [dict(id=9, prio=0, started=10, grant=4096, use=3500)], 100000.0, LEASE, now=400.0)
    assert q["grants"][9] > 4096
    assert p["stalled"] == [] and p["victim"] is None
    p = plan(kq, jobs[:2], 1200.0, LEASE, now=400.0)   # room for one step: the older job gets it
    assert p["grants"][1] > 4096 and p["grants"][2] == 4096 and p["stalled"] == [2]


def test_lease_plan_requeues_the_newest_job_only_after_a_long_stall(kq):
    jobs = [dict(id=1, prio=0, started=10, grant=4096, use=4090, stall_since=100.0),
            dict(id=2, prio=0, started=50, grant=2048, use=1000),
            dict(id=3, prio=5, started=60, grant=2048, use=1000)]       # higher priority: never a victim for #1
    assert plan(kq, jobs, 0.0, LEASE, now=500.0)["victim"] is None  # stalled 400 s: wait
    p = plan(kq, jobs, 0.0, LEASE, now=1100.0)
    assert p["stalled"] == [1] and p["victim"] == 2 and p["stall_since"][1] == 1100.0
    # a runaway (far past its --mem) is the victim, even when it is the one waiting
    jobs[0]["declared"], jobs[1]["declared"] = 1024, 2048        # #1 uses 4x its --mem
    assert plan(kq, jobs, 0.0, LEASE, now=1100.0)["victim"] == 1
    # waiting only for other users' memory, alone: it keeps waiting
    assert plan(kq, jobs[:1] and [dict(jobs[0], declared=8192)], 0.0, LEASE, now=1100.0)["victim"] is None


def test_lease_plan_freezes_only_a_job_at_its_grant(kq):
    """A job that wants more but still has room of its own runs on; it is frozen only at its grant, or when it grows
    fast enough to reach it within two ticks."""
    room = [dict(id=1, prio=0, started=10, grant=4096, use=3500)]               # within 15%: wants more
    p = plan(kq, room, 0.0, LEASE, now=400.0)
    assert p["grants"][1] == 4096 and p["stalled"] == [] and p["stall_since"][1] == 0.0
    at = [dict(id=1, prio=0, started=10, grant=4096, use=3900)]                 # within lease_freeze_mb
    assert plan(kq, at, 0.0, LEASE, now=400.0)["stalled"] == [1]
    fast = [dict(room[0], rate=200.0)]                                           # 200 MB/s: 800 MB in two ticks
    assert plan(kq, fast, 0.0, LEASE, now=400.0)["stalled"] == [1]
    frozen = [dict(room[0], frozen=True)]                                        # frozen: shows no growth; stays
    assert plan(kq, frozen, 0.0, LEASE, now=400.0)["stalled"] == [1]
    assert plan(kq, frozen, 8192.0, LEASE, now=400.0)["grants"][1] > 4096   # until it gets more


def test_frozen_time_does_not_count_towards_the_timeout(kq):
    d = kq.Daemon()
    submit(kq, "sleep 30", name="slow", timeout="2s")
    drive(kq, d, lambda: states(d)["slow"] == "running")
    d.c.execute("UPDATE jobs SET frozen_s=100")     # as if it had waited 100 s for memory
    t = time.time()
    while time.time() - t < 3:
        d.tick()
        time.sleep(0.2)
    assert states(d)["slow"] == "running"
    d.c.execute("UPDATE jobs SET frozen_s=0, frozen_since=?", (time.time() - 50,))   # frozen right now: on hold
    d.tick()
    assert states(d)["slow"] == "running"
    j = d.c.execute("SELECT * FROM jobs").fetchone()
    assert kq.frozen_for(j, time.time()) >= 50 and kq.active_for(j, time.time()) < 5
    d.c.execute("UPDATE jobs SET frozen_since=0")
    drive(kq, d, lambda: states(d)["slow"] == "timeout")


def test_a_requeued_attempt_is_counted_as_lost(kq):
    d = kq.Daemon()
    submit(kq, "python3 -c 'while 1: pass'", name="spin", timeout="1m")
    drive(kq, d, lambda: states(d)["spin"] == "running")
    t = time.time()
    while time.time() - t < 2.5:
        d.tick()
        time.sleep(0.2)
    j = d.c.execute("SELECT * FROM jobs").fetchone()
    d.preempt(j, time.time(), "test")
    j = d.c.execute("SELECT * FROM jobs").fetchone()
    assert j["state"] == "queued" and j["lost_run_s"] >= 2 and j["lost_cpu_s"] >= 1 and j["cpu_s"] == 0
    assert kq.active_for(j, time.time()) == 0
    d.c.execute("UPDATE jobs SET not_before=0")
    drive(kq, d, lambda: states(d)["spin"] == "running")
    assert "earlier attempts" in kq.times(d.c.execute("SELECT * FROM jobs").fetchone())
    d.c.execute("UPDATE jobs SET state='cancelled'")
    kq.kill_tree(j["pid"] or d.c.execute("SELECT pid FROM jobs").fetchone()[0])


def test_lease_plan_counts_only_part_of_old_jobs_unused_grants(kq):
    cfg = dict(LEASE, lease_hold_frac=0.25, lease_warm_s=120)
    jobs = [dict(id=1, prio=0, started=1, grant=20480, use=10240),          # old: 10 GB unused, 2.5 GB counted
            dict(id=2, prio=0, started=950, grant=4096, use=1024)]          # young: 3 GB unused, all counted
    p = kq.lease_plan(jobs, 16384.0, cfg, now=1000.0, buffer=4096.0)
    assert p["held"] == pytest.approx(2560 + 3072)
    assert p["free"] == pytest.approx(16384 - 4096 - 2560 - 3072) and p["stalled"] == []


def test_lease_plan_never_stalls_a_timed_job_and_makes_room_with_a_batch_job(kq):
    cfg = dict(LEASE, lease_hold_frac=0.25, timed_hold_frac=1.0)
    jobs = [dict(id=1, prio=0, started=10, grant=4096, use=4000, timed=True),     # at its grant, nothing free
            dict(id=2, prio=0, started=20, grant=4096, use=4000),                 # batch, at its grant
            dict(id=3, prio=0, started=30, grant=8192, use=2048, frozen=True),    # batch, frozen
            dict(id=4, prio=0, started=40, grant=8192, use=2048)]                 # batch, newest
    p = kq.lease_plan(jobs, 0.0, cfg, now=1000.0)
    assert 1 not in p["stalled"] and p["short"] == [1] and 2 in p["stalled"]
    # making room in two stages: first the running batch job is frozen (its memory compressed), no requeue yet
    assert 4 in p["stalled"] and p["timed_victim"] is None
    jobs[3]["frozen"] = True                       # all batch jobs frozen: for a timed job, requeue the newest
    assert kq.lease_plan(jobs, 0.0, cfg, now=1000.0)["timed_victim"] == 4
    jobs[3]["frozen"] = False
    # timed jobs get memory first, and their unused grant counts in full; never frozen as growers
    jobs[0]["grew"] = jobs[1]["grew"] = 500.0
    p = kq.lease_plan(jobs, 1100.0, cfg, now=1000.0, buffer=4096.0 + 0)
    assert 1 not in p["stalled"]
    p = kq.lease_plan(jobs[:2], 1100.0 + 96 + 96 * 0.25, cfg, now=1000.0)
    assert p["grants"][1] > 4096 and p["stalled"] == [2]
    assert kq.lease_plan(jobs[:1], 0.0, cfg, now=1000.0)["timed_victim"] is None   # no batch job: it runs on


def test_timed_cpu_pools_bursts_and_waits_for_calm(kq):
    # three jobs averaging 2 cores with bursts to 10: their means add up, their bursts rarely coincide
    jobs = [(2.0, 10.0)] * 3
    assert kq.burst_fits(jobs, (2.0, 10.0), cap=24.0)            # 8 + sqrt(4 * 64) = 24
    assert not kq.burst_fits(jobs, (2.0, 10.0), cap=23.0)
    assert not kq.burst_fits([(10.0, 10.0)] * 3, (2.0, 2.0), cap=31.0)   # steady jobs count in full
    d = kq.Daemon()
    submit(kq, "true", name="a", cpus=2)
    j = d.c.execute("SELECT * FROM jobs").fetchone()
    assert d.timed_cpu_fits(j, kq.config(), time.time(), [])          # 2 of 3 CPUs (test pool: 4 threads, 1 kept)
    d.timed_wait = 0.03                                               # timed jobs already wait for CPUs: no start
    assert not d.timed_cpu_fits(j, kq.config(), time.time(), [])


def test_lease_plan_counts_a_thrashing_jobs_frozen_time_as_waiting(kq):
    """Frozen and thawed over and over, a job's stall restarts each time; its time frozen still counts."""
    jobs = [dict(id=1, prio=0, started=10, grant=4096, use=4090, declared=1024, stall_since=990.0,
                 waited_frozen=1000.0),                                 # 4x its --mem: a runaway
            dict(id=2, prio=0, started=50, grant=2048, use=1000, declared=2048)]
    p = kq.lease_plan(jobs, 0.0, LEASE, now=1000.0)
    assert p["stalled"] == [1] and p["victim"] == 1 and p["waiter"] == 1
    jobs[0]["waited_frozen"] = 100.0
    assert kq.lease_plan(jobs, 0.0, LEASE, now=1000.0)["victim"] is None


def test_lease_plan_requeues_the_cheapest_job_when_memory_runs_short(kq):
    """Below half the buffer, the job that loses the least work per MB freed is requeued (it restarts from
    scratch, results unaffected); a job requeued evict_protect_after times is spared."""
    cfg = dict(LEASE, lease_hold_frac=0.25, timed_hold_frac=0.5)
    jobs = [dict(id=1, prio=0, started=10, grant=30000, use=20000, timed=True, invest=4 * 3600.0),   # 0.72 s/MB
            dict(id=2, prio=0, started=900, grant=8000, use=6000, timed=True, invest=4 * 100.0),     # 0.07 s/MB
            dict(id=3, prio=0, started=950, grant=4000, use=3000, timed=True, invest=4 * 50.0, protected=True)]
    assert kq.lease_plan(jobs, 3000.0, cfg, now=1000.0, buffer=4096.0)["evict"] is None   # above half: no
    p = kq.lease_plan(jobs, 1000.0, cfg, now=1000.0, buffer=4096.0)
    assert p["evict"] == 2 and p["stalled"] == []          # timed jobs are never frozen
    # timed grants are only partly set aside (old jobs: timed_hold_frac), young or protected ones in full
    q = kq.lease_plan(jobs, 100000.0, dict(cfg, lease_warm_s=0), now=1000.0)
    assert q["held"] == pytest.approx(0.5 * 10000 + 0.5 * 2000 + 1000)


def test_overcommit_adapts_to_the_work_lost_to_requeues(kq):
    cfg = dict(overcommit_window_s=21600, overcommit_loss_target=0.02)
    hist = [(0, 0.0, 0.0), (3600, 100000.0, 5000.0)]       # 5% of the work lost: set more aside
    assert kq.adapt_hold(0.5, hist, cfg, now=3600)[0] == pytest.approx(0.6)
    hist = [(0, 0.0, 0.0), (3600, 100000.0, 500.0)]        # 0.5%: set less aside
    assert kq.adapt_hold(0.5, hist, cfg, now=3600)[0] == pytest.approx(0.45)
    hist = [(0, 0.0, 0.0), (3600, 1000.0, 500.0)]          # under a core-hour of work: no evidence, no change
    assert kq.adapt_hold(0.5, hist, cfg, now=3600) == (0.5, None)
    assert kq.adapt_hold(1.0, [(0, 0.0, 0.0), (1, 1e6, 1e6)], cfg, now=1)[0] == 1.0     # capped


def test_jobs_are_sized_by_their_owners_median_not_by_a_few_under_declared_ones(kq):
    d = kq.Daemon()
    now = time.time()
    rows = [("o", 1000, 800)] * 18 + [("o", 1000, 4000)] * 2 + [("u", 1000, 2000)] * 20   # o: 2 of 20 under-declared
    for i, (o, m, p) in enumerate(rows):
        d.c.execute("INSERT INTO jobs(owner,cmd,cpus,mem_mb,timeout_s,state,submitted,started,finished,peak_mb) "
                    "VALUES(?,'x',1,?,60,'ok',?,?,?,?)", (o, m, now - 100 + i, now - 50, now - 10 + i * 1e-3, p))
    d.c.execute("INSERT INTO jobs(owner,cmd,cpus,mem_mb,timeout_s,state,submitted) VALUES('o','x',1,1000,60,'queued',?)", (now,))
    d.c.execute("INSERT INTO jobs(owner,cmd,cpus,mem_mb,timeout_s,state,submitted) VALUES('u','x',1,1000,60,'queued',?)", (now,))
    cfg = kq.config()
    d.learn_ratios(cfg, now)
    o, u = d.c.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY owner").fetchall()
    assert d.need_mb(o, cfg) == pytest.approx(1000 * 0.8 * cfg["mem_learn_margin"])    # not 4x
    assert d.need_mb(u, cfg) == pytest.approx(1000 * 2.0 * cfg["mem_learn_margin"])    # sized up, past --mem


def test_lease_plan_uses_the_timed_forecast_and_thaws_compressed_jobs_only_with_room(kq):
    cfg = dict(LEASE, lease_hold_frac=0.25, lease_warm_s=120)
    jobs = [dict(id=1, prio=0, started=10, grant=30000, use=20000, timed=True),          # old timed: forecast
            dict(id=2, prio=0, started=950, grant=4000, use=1000, timed=True),            # young: in full
            dict(id=3, prio=0, started=10, grant=8000, use=2000),                         # batch: 25%
            dict(id=4, prio=0, started=10, grant=3000, use=500, swapped=2000)]            # thawed, 2 GB to come back
    p = kq.lease_plan(jobs, 100000.0, cfg, now=1000.0, timed_held=5000.0)
    assert p["held"] == pytest.approx(5000 + 3000 + 0.25 * 6000 + 0.25 * 2500 + 2000)
    frozen = [dict(id=5, prio=0, started=10, grant=1200, use=1000, swapped=6000, compressed=True, frozen=True),
              dict(id=6, prio=0, started=20, grant=4096, use=4000, timed=True)]
    p = kq.lease_plan(frozen, 5000.0, cfg, now=1000.0, timed_held=0.0)
    assert 5 in p["stalled"] and p["grants"][6] > 4096    # 6 GB would come back: no room; others still get memory
    p = kq.lease_plan(frozen, 9000.0, cfg, now=1000.0, timed_held=0.0)
    assert 5 not in p["stalled"] and p["grants"][5] > 1200   # room for it: it goes first


def test_the_timed_forecast_z_adapts_to_lost_work(kq):
    cfg = dict(overcommit_window_s=21600, overcommit_loss_target=0.02)
    assert kq.adapt_z(2.0, [(0, 0.0, 0.0), (3600, 100000.0, 5000.0)], cfg, now=3600)[0] == 2.5
    assert kq.adapt_z(2.0, [(0, 0.0, 0.0), (3600, 100000.0, 100.0)], cfg, now=3600)[0] == 1.75
    assert kq.adapt_z(2.0, [(0, 0.0, 0.0), (3600, 10.0, 5.0)], cfg, now=3600) == (2.0, None)


def test_batch_jobs_get_whole_steps_or_wait_and_evict_for_timed_only_when_really_short(kq):
    cfg = dict(LEASE, lease_hold_frac=0.25)
    jobs = [dict(id=1, prio=0, started=10, grant=8192, use=8100),                 # batch at its grant: step 2 GB
            dict(id=2, prio=0, started=20, grant=4096, use=4000, timed=True)]     # timed at its grant
    p = kq.lease_plan(jobs, 1500.0, cfg, now=1000.0, buffer=1000.0, timed_held=0.0, credit=1000.0)
    assert p["grants"][2] > 4096 and 1 in p["stalled"]         # crumbs to the timed job; the batch job waits frozen
    assert p["timed_victim"] is None                            # real free (1.5 GB) is above the buffer: no eviction
    p = kq.lease_plan(jobs, 500.0, cfg, now=1000.0, buffer=1000.0, timed_held=0.0)
    assert p["timed_victim"] == 1                               # really short: the batch job makes room


def test_lease_plan_freezes_growers_when_the_buffer_is_eaten(kq):
    cfg = dict(LEASE, lease_hold_frac=0.0)
    jobs = [dict(id=1, prio=0, started=10, grant=60000, use=50000, grew=3000),   # oldest grower
            dict(id=2, prio=0, started=20, grant=8000, use=4000, grew=500),
            dict(id=3, prio=0, started=30, grant=8000, use=4000, grew=0),        # not growing: runs on
            dict(id=4, prio=1, started=40, grant=8000, use=4000, grew=100)]      # higher priority, newest
    p = kq.lease_plan(jobs, 3000.0, cfg, now=1000.0, buffer=4096.0)           # under the buffer, above half
    assert sorted(p["stalled"]) == [1, 2] and p["grants"][1] == 50000 and p["grants"][2] == 4000
    p = kq.lease_plan(jobs, 1000.0, cfg, now=1000.0, buffer=4096.0)           # under half: every grower waits
    assert sorted(p["stalled"]) == [1, 2, 4] and p["grants"][3] == 8000
    p = kq.lease_plan(jobs, 9000.0, cfg, now=1000.0, buffer=4096.0)           # room again: nobody frozen
    assert p["stalled"] == []


def test_timed_jobs_waiting_for_cpus_freeze_the_newest_batch_job(kq, tmp_path):
    d = _lease_daemon(kq, tmp_path, cpu_freeze_every_s=0, threads=512, reserve_cpu=0)  # admits both on a busy host
    submit(kq, "sleep 60", name="old", qos="batch")
    submit(kq, "sleep 60", name="new", qos="batch")
    drive(kq, d, lambda: list(states(d).values()) == ["running", "running"] and len(d.cgroups) == 2)
    d.timed_wait = 0.5                       # as if timed jobs waited for CPUs half the time
    running = d.c.execute("SELECT * FROM jobs WHERE state='running'").fetchall()
    d.cpu_freeze(kq.config(), time.time(), running)
    assert kq.cg_frozen(d.cgroups[2]) and not kq.cg_frozen(d.cgroups[1])
    d.tick()                                 # the memory leases leave a CPU-frozen job frozen
    assert kq.cg_frozen(d.cgroups[2])
    d.timed_wait = 0.0
    d.cpu_freeze(kq.config(), time.time(), running)     # calm: thawed
    d.cpu_freeze(kq.config(), time.time(), running)
    assert not kq.cg_frozen(d.cgroups[2])
    j = d.c.execute("SELECT * FROM jobs WHERE id=2").fetchone()
    assert j["freezes"] == 1 and j["frozen_s"] >= 0 and not j["frozen_since"]
    d.c.execute("UPDATE jobs SET state='cancelled'")
    for i in (1, 2):
        kq.kill_tree(d.c.execute("SELECT pid FROM jobs WHERE id=?", (i,)).fetchone()[0], d.cgroups.get(i))


def test_each_attempt_leaves_a_trace(kq, tmp_path):
    import gzip
    d = _lease_daemon(kq, tmp_path)
    submit(kq, "python3 -c 'import time\na = bytearray(200 << 20)\nt = time.time()\nwhile time.time() - t < 25: pass'",
           name="tr", timeout="1m")
    drive(kq, d, lambda: states(d)["tr"] == "ok", secs=60)
    files = os.listdir(kq.TRACES)
    assert files == ["1.1.0.tsv.gz"]
    lines = gzip.open(os.path.join(kq.TRACES, files[0]), "rt").read().splitlines()
    head = json.loads(lines[0])
    assert head["owner"] == "t" and head["qos"] == "timed" and lines[-1].startswith("# end ok")
    rows = [l.split("\t") for l in lines[1:-1]]
    assert len(rows) >= 1 and float(rows[-1][2]) >= 150 and float(rows[-1][3]) > 0.5   # ~200 MB, ~1 core


def test_a_frozen_job_is_compressed_and_nothing_starts_until_it_is_back(kq, tmp_path):
    if kq.compress_room_mb("any") < 700:
        pytest.skip("needs about 1.2 GB of free swap")
    d = _lease_daemon(kq, tmp_path, mem_budget_gb=1.6, compress_frozen="any")   # room for one 1 GB step
    submit(kq, HOG.format(n=4, after="", hold=3), name="hog", mem="300M", timeout="3m", qos="batch")
    drive(kq, d, lambda: d.cgroups.get(1) and kq.cg_frozen(d.cgroups[1]), secs=60)
    drive(kq, d, lambda: kq.cg_swap_mb(d.cgroups[1]) > 200, secs=60)        # its memory went to swap
    submit(kq, "true", name="later", mem="10M")
    for _ in range(10):
        d.tick()
        time.sleep(0.2)
    assert states(d)["later"] == "queued"                                   # nothing starts meanwhile
    assert d.sys["lease"]["compressed"] == [1]
    conf = json.load(open(kq.CONF)); conf["mem_budget_gb"] = 4; json.dump(conf, open(kq.CONF, "w"))
    drive(kq, d, lambda: states(d)["hog"] == "ok" and states(d)["later"] == "ok", secs=90)


def test_a_running_timed_job_has_its_cold_memory_squeezed_into_zram(kq, tmp_path):
    if kq.compress_room_mb("zram") < 2048:
        pytest.skip("needs a zram swap device")
    d = _lease_daemon(kq, tmp_path, mem_budget_gb=4, lease_buffer_gb=0.9, squeeze_min_gb=0.2, squeeze_every_s=0)
    prog = ("import time, os\ncold = bytearray(600 << 20)\nfor i in range(0, len(cold), 4096): cold[i] = 1\n"
            "f = os.path.join(os.environ['KAEQ_SCRATCH'], 'cache')\nopen(f, 'wb').write(bytes(200 << 20))\n"
            "open(f, 'rb').read()\n"   # page cache, which reclaim takes first: it must not count as squeezed
            "hot = bytearray(32 << 20)\nt = time.time()\n"
            "while time.time() - t < 25:\n    hot[int(time.time() * 1000) % len(hot)] = 1\nprint('ok', sum(cold[::4096]))")
    submit(kq, "python3 -c " + repr(prog).replace("\\n", "\n"), name="sq", mem="800M", timeout="2m")
    drive(kq, d, lambda: d.cgroups.get(1) and kq.cg_mem(d.cgroups[1])[0] > 600, secs=30)   # cold memory touched
    conf = json.load(open(kq.CONF)); conf["mem_budget_gb"] = 1.2; json.dump(conf, open(kq.CONF, "w"))  # now short
    drive(kq, d, lambda: kq.cg_swap_mb(d.cgroups[1]) > 200, secs=40)                     # squeezed...
    assert not kq.cg_frozen(d.cgroups[1])                                                  # ...while running
    drive(kq, d, lambda: states(d)["sq"] == "ok", secs=60)
    j = d.c.execute("SELECT * FROM jobs").fetchone()
    assert j["squeezed_mb"] > 200 and j["freezes"] == 0
    assert "ok 153600" in (tmp_path / "jobs" / "1" / "log").read_text()          # its memory came back intact


def test_jobs_that_are_not_memory_heavy_move_one_cpu_step_down(kq, tmp_path):
    d = _lease_daemon(kq, tmp_path, lease_warm_s=0, keep_gb=4, mem_budget_gb=200)
    prog = "import threading, time\nt = threading.Thread(target=time.sleep, args=(30,))\nt.start()\ntime.sleep(30)"
    submit(kq, "python3 -c " + repr(prog).replace("\\n", "\n"), name="b", qos="batch", mem="6G")   # starts up
    submit(kq, "python3 -c " + repr(prog).replace("\\n", "\n"), name="t", qos="timed", mem="6G")
    drive(kq, d, lambda: len(d.cgroups) == 2)
    d.ratios, d.ratios_ts = {"t": 0.01}, time.time() + 3600   # its owner's history now says: light after all
    d.demote_ts = 0.0
    drive(kq, d, lambda: d.demoted == {1, 2}, secs=20)
    tids = lambda i: [int(x) for x in open(d.cgroups[i] + "/cgroup.threads").read().split()]
    assert all(os.sched_getscheduler(t) == os.SCHED_IDLE for t in tids(1))       # batch: down to SCHED_IDLE
    assert all(os.getpriority(os.PRIO_PROCESS, t) == 11 for t in tids(2))         # timed: nice 10 -> 11
    d.c.execute("UPDATE jobs SET state='cancelled'")
    for i in (1, 2):
        kq.kill_tree(d.c.execute("SELECT pid FROM jobs WHERE id=?", (i,)).fetchone()[0], d.cgroups.get(i))


def _lease_daemon(kq, tmp_path, **cfg):
    conf = json.load(open(kq.CONF))
    conf.update(cgroup="auto", slice="kaeqtest.slice", mem_pool="lease", lease_buffer_gb=0.1, lease_buffer_ticks=0)
    conf.update(cfg)
    json.dump(conf, open(kq.CONF, "w"))
    d = kq.Daemon()
    if not d.use_cgroup(kq.config()):
        pytest.skip("no delegated cgroup memory controller here")
    kq.user_pressure = lambda: 0.0     # the live host's user manager pressure must not pause the tests' reclaims
    return d


HOG = ("python3 -c \"import time\na=[]\nfor i in range({n}):\n    a.append(bytearray(256<<20)); print(i, flush=True); "
       "time.sleep(0.1)\n{after}time.sleep({hold})\"")


def test_lease_stalls_a_job_at_its_grant_instead_of_killing_it(kq, tmp_path):
    """A job that outgrows what may be granted waits, frozen, near its grant; once the budget allows, it gets more,
    is thawed and finishes. It is never killed for using more than it declared."""
    d = _lease_daemon(kq, tmp_path, mem_budget_gb=1.5)
    submit(kq, HOG.format(n=8, after="", hold=1), name="hog", mem="300M", timeout="2m", qos="batch")
    log = tmp_path / "jobs" / "1" / "log"
    drive(kq, d, lambda: d.c.execute("SELECT grant_mb FROM jobs").fetchone()[0] >= 1200, secs=40)
    t = time.time()
    while time.time() - t < 6:
        d.tick()
        time.sleep(0.2)
    n = len(joblog(log).split())
    print(f"held: {n} of 8 chunks, cgroup at {int(open(d.cgroups[1] + '/memory.current').read()) >> 20} MB")
    assert states(d)["hog"] == "running" and n < 8               # held at ~1.5 GB, not killed
    ev = open(d.cgroups[1] + "/cgroup.events").read()
    assert "frozen 1" in ev                                      # it waits frozen: no memory pressure to be killed for
    g = d.c.execute("SELECT grant_mb FROM jobs").fetchone()[0]
    assert g <= 1.5 * 1024 + 1
    j = d.c.execute("SELECT * FROM jobs").fetchone()
    assert j["frozen_since"] > 0 and j["freezes"] >= 1          # the freeze is in the database, not only in memory
    # a daemon restart while the job is frozen: the new daemon adopts it, still frozen, and thaws it once it can
    d = kq.Daemon()
    d.tick()
    assert "frozen 1" in open(d.cgroups[1] + "/cgroup.events").read()
    conf = json.load(open(kq.CONF)); conf["mem_budget_gb"] = 4; json.dump(conf, open(kq.CONF, "w"))
    drive(kq, d, lambda: states(d)["hog"] == "ok", secs=60)
    j = d.c.execute("SELECT * FROM jobs").fetchone()
    assert j["frozen_s"] > 0 and j["frozen_since"] == 0 and j["cpu_s"] > 0


def test_lease_gives_back_what_a_job_no_longer_uses(kq, tmp_path):
    d = _lease_daemon(kq, tmp_path, lease_release_gb=0.5, lease_release_after_s=2, warmup_s=0)
    submit(kq, HOG.format(n=8, after="a.clear()\n", hold=30), name="hog", mem="300M", timeout="2m", qos="batch")
    drive(kq, d, lambda: d.c.execute("SELECT grant_mb FROM jobs").fetchone()[0] >= 2000, secs=40)
    drive(kq, d, lambda: d.c.execute("SELECT grant_mb FROM jobs").fetchone()[0] <= 1200, secs=30)
    d.c.execute("UPDATE jobs SET state='cancelled' WHERE 1")
    kq.kill_tree(d.c.execute("SELECT pid FROM jobs").fetchone()[0], d.cgroups.get(1))


def test_jobs_go_in_as_batch_unless_marked_timed(kq):
    submit(kq, "true", name="plain", qos=None)
    submit(kq, "true", name="bench", qos="timed")
    c = kq.db()
    assert dict(c.execute("SELECT name, qos FROM jobs").fetchall()) == {"plain": "batch", "bench": "timed"}


def test_retry_keeps_or_sets_cpus_timeout_and_books_the_lost_attempt(kq):
    import argparse
    c = kq.db()
    now = time.time()
    for name in ("a", "b"):
        c.execute("INSERT INTO jobs(owner,name,cmd,cpus,mem_mb,timeout_s,state,submitted,started,finished,peak_mb,"
                  "frozen_s) VALUES('t',?,'x',4,1000,3600,'failed',?,?,?,0,100)", (name, now - 1000, now - 900, now - 300))
    c.commit()
    ns = dict(owner=None, tag=None, mem=None, timeout=None, cpus=None, retries=0, disk=None)
    kq.ensure_daemon = lambda: None
    kq.cmd_retry(argparse.Namespace(ids=["1"], **ns))
    kq.cmd_retry(argparse.Namespace(ids=["2"], **dict(ns, timeout="5h", cpus=8.0)))
    a, b = c.execute("SELECT * FROM jobs ORDER BY id").fetchall()
    assert (a["cpus"], a["timeout_s"]) == (4, 3600) and (b["cpus"], b["timeout_s"]) == (8, 5 * 3600)
    for j in (a, b):   # the failed attempt ran 600 s, 100 s of it frozen: 500 s lost
        assert j["state"] == "queued" and j["lost_run_s"] == pytest.approx(500, abs=2)


def test_forecast_replays_the_queue_by_priority_capacity_and_run_times(kq):
    now = 1000.0
    J = lambda i, o, prio=0, sub=0.0, started=None: dict(id=i, owner=o, prio=prio, submitted=sub, started=started,
                                                          frozen_s=0.0)
    running = [J(1, "a", started=now - 600)]                       # expected 1000 s: 400 s left
    queued = [J(2, "a", sub=1), J(3, "b", prio=5, sub=2), J(4, "b", prio=5, sub=3)]
    dur = {1: 1000.0, 2: 100.0, 3: 300.0, 4: 300.0}
    mem = {1: 10.0, 2: 10.0, 3: 10.0, 4: 10.0}
    cpus = {i: 1.0 for i in dur}
    # room for two jobs at once: b (priority 5) takes the free slot now (ends 1300) and again when that one ends
    # (1300-1600); a's queued job gets the slot a's running job frees at 1400 (ends 1500)
    fc = kq.forecast_queue(running, queued, dur, mem, cpus, mem_cap=20.0, cpu_cap=100.0, now=now)
    assert fc["b"] == (None, pytest.approx(now + 600))
    assert fc["a"] == (None, pytest.approx(now + 500))
    fc = kq.forecast_queue([], queued, dur, mem, cpus, mem_cap=10.0, cpu_cap=100.0, now=now)   # one at a time
    assert fc["a"] == (pytest.approx(now + 600), pytest.approx(now + 700))    # starts after both of b's
    # plenty of room: everything at once
    fc = kq.forecast_queue(running, queued, dur, mem, cpus, mem_cap=1000.0, cpu_cap=100.0, now=now)
    assert fc["a"][1] == pytest.approx(now + 400) and fc["b"][1] == pytest.approx(now + 300)


def test_expected_durations_use_the_same_name_then_the_owner_then_a_guess(kq):
    c = kq.db()
    for i, (o, n, act) in enumerate([("x", "board1", 500), ("x", "b2", 100), ("x", "b3", 200), ("x", "b4", 300)]):
        c.execute("INSERT INTO jobs(owner,name,cmd,cpus,mem_mb,timeout_s,state,submitted,started,finished,frozen_s) "
                  "VALUES(?,?,'x',1,1,3600,'ok',0,?,?,10)", (o, n, 100 + i, 100 + i + act + 10))
    c.execute("INSERT INTO jobs(owner,name,cmd,cpus,mem_mb,timeout_s,state,submitted) VALUES('y','board1','x',1,1,3600,'queued',0)")
    c.execute("INSERT INTO jobs(owner,name,cmd,cpus,mem_mb,timeout_s,state,submitted) VALUES('x','new','x',1,1,3600,'queued',0)")
    c.execute("INSERT INTO jobs(owner,name,cmd,cpus,mem_mb,timeout_s,state,submitted) VALUES('z','new','x',1,1,3600,'queued',0)")
    q = c.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY id").fetchall()
    d = kq.expected_durations(c, q)
    assert d[q[0]["id"]] == (500, "name")          # the same board ran before (another owner): its time
    assert d[q[1]["id"]] == (300, "size")          # under 8 jobs: x's median (100, 200, 300, 500 -> 300)
    assert d[q[2]["id"]] == (1800, "guess")        # nothing known: half its timeout


def test_run_time_grows_with_size_and_overruns_extrapolate_from_history(kq):
    rows = [(m, 10.0 * m) for m in (1000, 2000, 4000, 8000, 1000, 2000, 4000, 8000)]   # time proportional to size
    pred, ratios = kq.size_model(rows)
    assert pred(16000) == pytest.approx(160000, rel=0.01) and pred(500) == pytest.approx(5000, rel=0.01)
    assert ratios == pytest.approx([1.0] * 8)
    # how jobs that ran past their prediction ended: actual/predicted 0.5 .. 3
    ratios = [0.5, 0.8, 1.0, 1.0, 1.2, 2.0, 3.0]
    assert kq.given_so_far(100.0, 10.0, ratios) == pytest.approx(100 * sum(ratios) / 7)   # early: the mean
    assert kq.given_so_far(100.0, 150.0, ratios) == pytest.approx(250.0)   # past 1.5x: those ended at 2x or 3x
    assert kq.given_so_far(100.0, 400.0, ratios) == pytest.approx(520.0)   # past them all: 1.3x what it has run


def test_run_time_is_owner_speed_times_board_difficulty(kq):
    c = kq.db()
    rows = []   # owner slow takes 4x fast; board big-board-aaaaaa takes 10x small-board-bbbbbb
    for o, f in (("fast", 1.0), ("slow", 4.0)):
        for b, g in (("big-board-aaaaaa", 10.0), ("small-board-bbbbbb", 1.0)):
            for k in range(3):
                rows.append((o, f"x:{b}:{k}", 100 * f * g))
    rows += [("fast", "x:huge-board-cccccc:0", 3000.0), ("fast", "x:huge-board-cccccc:1", 3000.0)]   # only fast ran it
    for i, (o, n, t) in enumerate(rows):
        c.execute("INSERT INTO jobs(owner,name,cmd,cpus,mem_mb,timeout_s,state,submitted,started,finished,frozen_s) "
                  "VALUES(?,?,'x',1,1,99999,'ok',0,?,?,0)", (o, n, i, i + t))
    c.execute("INSERT INTO jobs(owner,name,cmd,cpus,mem_mb,timeout_s,state,submitted) "
              "VALUES('slow','y:huge-board-cccccc:9','x',1,1,99999,'queued',0)")
    q = c.execute("SELECT * FROM jobs WHERE state='queued'").fetchall()
    d, src = kq.expected_durations(c, q, now=1e9)[q[0]["id"]]
    # slow's speed x the huge board's difficulty (seen twice: shrunk to 2/3 of its log effect): far above the
    # owner's typical job, below the unshrunk 4 x 3000
    assert src == "board" and 4 * 100 * 30 ** 0.5 < d < 4 * 3000


def test_expensive_batch_jobs_run_on_and_cheap_ones_make_room(kq):
    """A frozen job holds its memory for nothing, a big one most: expensive batch jobs are kept running (never
    frozen for a grant); room is made by freezing the newest cheap job, never by a requeue for a batch job; a
    just-thawed job is kept for its run window, which gives way below half the buffer."""
    cfg = dict(LEASE, lease_hold_frac=0.1)
    big = dict(id=1, prio=0, started=10, grant=20000, use=19900, keep=True, dear=True)
    small_a = dict(id=2, prio=0, started=20, grant=2000, use=1990)        # at its grant
    small_b = dict(id=3, prio=0, started=30, grant=2000, use=1000)        # running, newest
    p = kq.lease_plan([big, small_a, small_b], 0.0, cfg, now=1000.0)
    assert 1 not in p["stalled"] and p["short"] == [1]            # the big job is not frozen...
    assert 3 in p["stalled"] and 2 in p["stalled"]                # ...the cheap ones are (the newest made room)
    p = kq.lease_plan([big, dict(small_a, frozen=True), dict(small_b, frozen=True)], 0.0, cfg, now=1000.0)
    assert p["timed_victim"] is None                             # all frozen: no requeue for a batch job
    # with keep_reserve_frac, part of its forecast growth is set aside (the daemon passes reserve_mb)
    p = kq.lease_plan([dict(big, reserve_mb=4000), small_a, small_b], 100000.0, dict(cfg, lease_warm_s=0), now=1000.0)
    assert p["held"] == pytest.approx(4000 + 0.1 * 10 + 0.1 * 1000)
    # a just-thawed small job is kept (in its window): not frozen though at its grant with nothing free...
    p = kq.lease_plan([dict(small_a, keep=True)], 2000.0, cfg, now=1000.0, buffer=3000.0)
    assert p["stalled"] == [] and p["short"] == [2]
    # ...unless free memory is below half the buffer: then it may be frozen again
    p = kq.lease_plan([dict(small_a, keep=True)], 1000.0, cfg, now=1000.0, buffer=3000.0)
    assert p["stalled"] == [2]


def test_batch_cpu_admission_needs_a_lasting_dip_and_its_quantile_adapts(kq):
    assert kq.quantile([10, 120, 120, 120, 125], 0.8) == 125 and kq.quantile([], 0.8) == 0.0
    cfg = dict(runq_over_target=0.10, runq_idle_target=0.20, runq_idle_cpus=4)
    over = [(130, True)] * 3 + [(110, True)] * 7               # 30% of samples oversubscribed: more cautious
    assert kq.adapt_runq_q(0.8, over, 122, cfg)[0] == pytest.approx(0.85)
    idle = [(100, True)] * 5 + [(121, True)] * 5               # half the time 4+ CPUs idle while jobs waited: bolder
    assert kq.adapt_runq_q(0.8, idle, 122, cfg)[0] == pytest.approx(0.75)
    assert kq.adapt_runq_q(0.8, [(100, False)] * 10, 122, cfg)[0] == 0.8   # idle but nothing waits: unchanged
    assert kq.adapt_runq_q(0.95, over, 122, cfg)[0] == 0.95 and kq.adapt_runq_q(0.5, idle, 122, cfg)[0] == 0.5
    # one dip in a saturated window does not open the door
    clock = [0]

    def idle_cpus():
        clock[0] += 4000
        return 0, clock[0]
    kq.cpu_ticks = idle_cpus
    conf = json.load(open(kq.CONF)); conf.update(threads=64, reserve_cpu=0, runq_window_s=600, heavy_boost=False)
    json.dump(conf, open(kq.CONF, "w"))
    d = kq.Daemon()
    kq.runnable_threads = lambda: 0
    submit(kq, "sleep 20", name="busy", qos="batch")
    drive(kq, d, lambda: states(d)["busy"] == "running")      # (with nothing running, one job always starts)
    now = time.time()
    d.runq_hist = [(now - 100 + i, 70.0, True) for i in range(99)] + [(now, 0.0, True)]   # saturated, one dip
    submit(kq, "true", name="b", qos="batch", cpus=2)
    d.tick()
    assert states(d)["b"] == "queued"
    d.c.execute("UPDATE jobs SET state='cancelled' WHERE state IN ('queued','running')")


def test_a_batch_job_starved_of_cpu_is_frozen_compressed_and_thawed_when_there_is_room(kq, tmp_path):
    d = _lease_daemon(kq, tmp_path, cpu_freeze_every_s=0, threads=512, reserve_cpu=0)
    submit(kq, "python3 -c 'import time\na = bytearray(300 << 20)\nfor i in range(0, len(a), 4096): a[i] = 1\n"
               "time.sleep(40)'", name="b", qos="batch", mem="400M")
    submit(kq, "sleep 40", name="later", qos="batch")
    drive(kq, d, lambda: d.cgroups.get(1) and 1 in d.cpuj and kq.cg_mem(d.cgroups[1])[0] > 250, secs=30)
    d.cpuj[1]["starved_since"] = time.time() - 300            # as if its threads had waited for a CPU 5 min
    d.timed_wait = 0.03                                        # (not calm: no thaw in the same pass)
    running = d.c.execute("SELECT * FROM jobs WHERE state='running'").fetchall()
    d.cpu_freeze(kq.config(), time.time(), running)
    assert kq.cg_frozen(d.cgroups[1])
    drive(kq, d, lambda: kq.cg_swap_mb(d.cgroups[1]) > 100 and states(d)["later"] == "running", secs=40)
    assert 1 not in d.sys["lease"]["compressed"]             # waiting for CPU, not memory: starts go on
    d.timed_wait, d.calm_since = 0.0, time.time() - 60
    d.runq_hist = [(time.time(), 0.0, False)]
    d.cpu_freeze(kq.config(), time.time(), running)          # room in the run queue: thawed
    assert not kq.cg_frozen(d.cgroups[1])
    d.c.execute("UPDATE jobs SET state='cancelled'")
    for i in (1, 2):
        kq.kill_tree(d.c.execute("SELECT pid FROM jobs WHERE id=?", (i,)).fetchone()[0], d.cgroups.get(i))


def test_light_batch_jobs_fill_spare_cpus_and_heavy_ones_wait_for_the_run_queue(kq):
    clock = [0]

    def idle_cpus():
        clock[0] += 4000
        return 0, clock[0]
    kq.cpu_ticks = idle_cpus
    kq.runnable_threads = lambda: 0
    conf = json.load(open(kq.CONF)); conf.update(threads=64, reserve_cpu=0, runq_window_s=600, cgroup="off")
    json.dump(conf, open(kq.CONF, "w"))
    d = kq.Daemon()
    submit(kq, "sleep 20", name="busy", qos="timed")
    drive(kq, d, lambda: states(d)["busy"] == "running")
    now = time.time()
    d.runq_hist = [(now - 100 + i, 70.0, True) for i in range(100)]      # normal-priority threads saturate
    submit(kq, "sleep 20", name="heavy", qos="batch", cpus=2, mem="16G")    # starts at nice 19, normal policy
    submit(kq, "sleep 20", name="filler", qos="batch", cpus=2, mem="1G")    # starts at SCHED_IDLE
    for _ in range(3):
        d.tick()
    assert states(d)["filler"] == "running" and states(d)["heavy"] == "queued"
    d.c.execute("UPDATE jobs SET state='cancelled' WHERE state IN ('queued','running')")


def test_a_waiting_filler_holds_no_room_for_itself(kq):
    clock = [0]

    def idle_cpus():
        clock[0] += 4000
        return 0, clock[0]
    kq.cpu_ticks = idle_cpus
    kq.runnable_threads = lambda: 200                        # no spare CPU right now: fillers wait
    conf = json.load(open(kq.CONF)); conf.update(threads=64, reserve_cpu=0, cgroup="off", starve_after_s=0)
    json.dump(conf, open(kq.CONF, "w"))
    d = kq.Daemon()
    submit(kq, "sleep 20", name="busy", qos="timed")
    drive(kq, d, lambda: states(d)["busy"] == "running")
    submit(kq, "sleep 20", name="filler", qos="batch", cpus=2, mem="1G", prio=5)   # first in line, long "starving"
    submit(kq, "sleep 20", name="timed", qos="timed", cpus=1, mem="1G")
    drive(kq, d, lambda: states(d)["timed"] == "running")
    assert states(d)["filler"] == "queued"
    kq.runnable_threads = lambda: 0                          # CPUs spare: it starts
    drive(kq, d, lambda: states(d)["filler"] == "running")
    d.c.execute("UPDATE jobs SET state='cancelled' WHERE state IN ('queued','running')")
