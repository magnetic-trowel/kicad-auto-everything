# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
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
