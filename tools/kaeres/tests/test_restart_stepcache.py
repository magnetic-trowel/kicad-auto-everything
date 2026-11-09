# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""restart.py with KAE_STEP_CACHE (stand-in kicad-cli, no KiCad): time a cache hit saved is
charged, so a cached run gets no more effective time than an uncached one."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RESTART = Path(__file__).resolve().parents[1] / "restart.py"

# kicad-cli: `version`, and a DRC that takes a second and counts its runs
FAKE_CLI = """#!/usr/bin/env python3
import json, pathlib, re, sys, time
args = sys.argv[1:]
if args == ["version"]:
    print("10.0.7"); sys.exit(0)
n = pathlib.Path(__file__).with_name("runs")
n.write_text(str(int(n.read_text()) + 1 if n.exists() else 1))
time.sleep(1.0)
out = args[args.index("--output") + 1]
m = re.search(r"OPEN=(\\d+)", open(args[-1]).read())
json.dump(dict(violations=[], unconnected_items=[dict(items=[])] * int(m.group(1) if m else 0)), open(out, "w"))
"""

# an attempt that "replays" a step that took SAVED seconds, then works REAL seconds
HIT = ("echo '{\"step\": \"freerouting\", \"hit\": true, \"charged_s\": SAVED, \"real_s\": 0, \"saved_s\": SAVED}' "
       ">> \"$KAE_CHARGE_FILE\"; sleep REAL; echo '(kicad_pcb OPEN=2)' > @OUT@")


def _run(tmp_path, attempt, name="work", time_s=300, extra=(), cache=True, rc=0):
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    (bin_ / "kicad-cli").write_text(FAKE_CLI)
    (bin_ / "kicad-cli").chmod(0o755)
    inp = tmp_path / "in" / "board.kicad_pcb"
    inp.parent.mkdir(exist_ok=True)
    inp.write_text("(kicad_pcb OPEN=5)\n")
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", KAE_KICAD_WRAP="")
    env.pop("KAE_CHARGE_FILE", None)
    if cache:
        env["KAE_STEP_CACHE"] = str(tmp_path / "cache")
    else:
        env.pop("KAE_STEP_CACHE", None)
    work = tmp_path / name
    work.mkdir()
    args = [sys.executable, str(RESTART), "--input", str(inp), "--output", str(work / "out.kicad_pcb"),
            "--time", str(time_s), "--parallel", "1", "--first-s", "60", "--max-attempts", "1", *extra]
    t0 = time.monotonic()
    r = subprocess.run([*args, "--", attempt], cwd=work, env=env, capture_output=True, text=True, timeout=300)
    real = time.monotonic() - t0
    assert r.returncode == rc, r.stdout + r.stderr
    return json.loads((work / "restarts" / "summary.json").read_text()), real, bin_ / "runs"


def test_a_hit_is_charged_its_recorded_time(tmp_path):
    s, real, _ = _run(tmp_path, HIT.replace("SAVED", "40").replace("REAL", "1"))
    a0 = s["attempt_log"][0]
    assert a0["wall_s"] >= 41 and a0["step_cache"]["hits"] == 1 and a0["step_cache"]["saved_s"] == 40
    assert s["wall_s"] >= 41 and s["step_cache"]["real_wall_s"] < 25 and real < 25
    assert s["step_cache"]["hits"] == 1 and s["step_cache"]["misses"] == 2   # the judge's two DRCs


def test_charged_time_counts_against_the_budget(tmp_path):
    """An attempt whose hits saved more than its budget is killed as an uncached one would be."""
    s, real, _ = _run(tmp_path, HIT.replace("SAVED", "100").replace("REAL", "200"), rc=1)   # no board
    a0 = s["attempt_log"][0]
    assert real < 30 and a0["rank"] is None and a0["wall_s"] >= 100


def test_the_judges_drc_replays_across_runs(tmp_path):
    attempt = "echo '(kicad_pcb OPEN=2)' > @OUT@"
    s1, _, runs = _run(tmp_path, attempt, "w1")
    assert runs.read_text() == "2"
    s2, real2, _ = _run(tmp_path, attempt, "w2")
    assert runs.read_text() == "2"                               # both judgements replayed
    assert s2["best_rank"] == s1["best_rank"] == [0, 1, 2, 0, 0]
    assert s2["step_cache"]["hits"] == 2 and s2["step_cache"]["saved_s"] >= 1.5
    assert s2["judge_wall_s"] >= 0.9                             # charged as a judgement takes


def test_without_the_cache_nothing_changes(tmp_path):
    s, _, runs = _run(tmp_path, "echo '(kicad_pcb OPEN=2)' > @OUT@", cache=False)
    assert "step_cache" not in s and runs.read_text() == "2"
    assert "step_cache" not in s["attempt_log"][0]


def test_experiment_env_takes_only_result_neutral_settings():
    import argparse
    sys.path.insert(0, str(RESTART.parent))
    import kaeres
    assert kaeres.exp_env(argparse.Namespace(env=["KAE_STEP_CACHE=/var/tmp/x"])) == {"KAE_STEP_CACHE": "/var/tmp/x"}
    import pytest
    with pytest.raises(SystemExit):
        kaeres.exp_env(argparse.Namespace(env=["KAE_ROUTE_HISTORY=/x"]))   # would change results: a recipe's job


def test_the_sandbox_binds_the_step_cache(tmp_path, monkeypatch):
    sys.path.insert(0, str(RESTART.parents[2] / "bench" / "src"))
    import shutil
    from kaebench import adapters
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setenv("KAE_STEP_CACHE", str(tmp_path / "cache"))
    argv = adapters.Sandbox().wrap(["true"], tmp_path)
    i = argv.index(str(tmp_path / "cache"))
    assert argv[i - 1] == "--bind" and argv.index("--tmpfs") < i and (tmp_path / "cache").is_dir()
    monkeypatch.delenv("KAE_STEP_CACHE")
    assert str(tmp_path / "cache") not in adapters.Sandbox().wrap(["true"], tmp_path)
