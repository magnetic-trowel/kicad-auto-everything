# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kicad-exec shows KiCad the job's CPU count, so KiCad's thread pool follows the grant (no KiCad needed)."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "kicad-exec"
ONLINE = os.sysconf("SC_NPROCESSORS_ONLN")


@pytest.fixture
def home(tmp_path):
    shutil.copy(SCRIPT, tmp_path / "kicad-exec")
    (tmp_path / "cpus").mkdir()
    for n in range(1, ONLINE + 1):
        (tmp_path / "cpus" / str(n)).write_text(f"0-{n - 1}\n")
    tool = tmp_path / "fake-apptainer"                       # prints the arguments it was given
    tool.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    tool.chmod(0o755)
    return tmp_path


def run(home, **env):
    e = {k: v for k, v in os.environ.items() if k not in ("KAEQ_CPUS", "KAE_KICAD_THREADS")}
    e.update(env)
    r = subprocess.run(["sh", str(home / "kicad-exec"), str(home / "fake-apptainer"), "/img", "kicad-cli", "version"],
                       capture_output=True, text=True, env=e, check=True)
    return r.stdout.split("\n")[:-1], r.stderr


@pytest.mark.skipif(ONLINE < 4, reason="needs a machine with at least 4 CPUs")
def test_the_queue_grant_sets_the_cpus_kicad_sees(home):
    args, _ = run(home, KAEQ_CPUS="2")
    assert args == ["exec", "--bind", f"{home}/cpus/2:/sys/devices/system/cpu/online", "/img", "kicad-cli", "version"]
    assert (home / "cpus" / "2").read_text() == "0-1\n"
    args, _ = run(home, KAEQ_CPUS="1.5")                       # a fractional grant rounds up
    assert args[2].startswith(f"{home}/cpus/2:")
    args, _ = run(home, KAEQ_CPUS="2", KAE_KICAD_THREADS="3")  # an explicit setting wins
    assert args[2].startswith(f"{home}/cpus/3:")


def test_no_cap_when_asked_or_when_the_grant_covers_the_machine(home):
    assert run(home, KAE_KICAD_THREADS="0")[0] == ["exec", "/img", "kicad-cli", "version"]
    assert run(home, KAEQ_CPUS=str(ONLINE))[0] == ["exec", "/img", "kicad-cli", "version"]


@pytest.mark.skipif(ONLINE < 4, reason="needs a machine with at least 4 CPUs")
def test_a_missing_cpu_file_runs_uncapped_and_says_so(home):
    (home / "cpus" / "2").unlink()
    args, err = run(home, KAEQ_CPUS="2")
    assert args == ["exec", "/img", "kicad-cli", "version"]
    assert "setup.sh" in err
