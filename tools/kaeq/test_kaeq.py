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
        f.write('{"threads": 4, "reserve_cpu": 1, "reserve_mem_gb": 0, "cgroup": "off"}')
    yield kaeq
    sys.path.remove(HERE)


def submit(kq, cmd, **kw):
    ns = dict(batch=None, command=[cmd], env=None, owner=None, name=None, tag=None, cwd=None, cpus=1.0, mem="50M",
              timeout="1m", prio=0, retries=0)
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
    kq.cmd_retry(argparse.Namespace(ids=[], owner=None, tag=None, mem=None, cpus=None, timeout=None, retries=0))
    assert states(d) == {"mine": "queued", "theirs": "failed"}
