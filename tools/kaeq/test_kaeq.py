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
    submit(kq, "sleep 20", name="w", mem="100G")
    drive(kq, d, lambda: states(d)["w"] == "running")
    d.tick()
    assert d.sys["unrealized"] > 90 * 1024  # declared 100G held while it warms up
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
    assert 1900 < need < 2600  # p95 of peak/--mem (~0.19) x 1.2 margin, not the declared 10G
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
    ni, cls = (tmp_path / "b").read_text().split()
    assert cls == "IDL" and ni in ("19", "-")  # ps prints "-" for the nice of SCHED_IDLE on some versions
    assert (tmp_path / "t").read_text().split() == ["10", "TS"]   # normal scheduling, far above SCHED_IDLE


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
    assert p["timed_victim"] == 3                  # the frozen batch job first, then the newest
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


def _lease_daemon(kq, tmp_path, **cfg):
    conf = json.load(open(kq.CONF))
    conf.update(cgroup="auto", slice="kaeqtest.slice", mem_pool="lease", lease_buffer_gb=0.1, lease_buffer_ticks=0)
    conf.update(cfg)
    json.dump(conf, open(kq.CONF, "w"))
    d = kq.Daemon()
    if not d.use_cgroup(kq.config()):
        pytest.skip("no delegated cgroup memory controller here")
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
