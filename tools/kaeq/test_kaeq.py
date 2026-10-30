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
    ns = dict(batch=None, jobs=None, command=[cmd], env=None, owner=None, name=None, tag=None, cwd=None, cpus=1.0, mem="50M",
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
