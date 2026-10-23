# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run Freerouting (2.5.x CLI) on a DSN with explicit, isolated settings.

Freerouting merges settings from defaults, `freerouting.json` in its user-data folder,
the DSN, environment variables named FREEROUTING__* and the command line (in that order of
precedence). A host's leftover freerouting.json or environment could silently change
results, so every run gets a private, empty user-data
folder (`--user_data_path`) and an environment without FREEROUTING__* variables, and every
setting the bridge depends on is passed on the command line.

The bridge prefers the magnetic-trowel fork (it honours `min_trace_width_um`; see
tools/research/routing/install_freerouting_fork.sh): KAE_BRIDGE_FREEROUTING, else the newest
KAE_HOME/kae-freerouting-fork-*/bin/freerouting. Without one it falls back as kaebench does:
KAE_FREEROUTING (a binary or a .jar), the native bundle in KAE_HOME (default
~/.cache/kaebench), `freerouting` on PATH, a jar in KAE_HOME. Settings an older build does not
know are logged as unknown and ignored.
"""
import json
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

KAE_HOME = Path(os.environ.get("KAE_HOME", Path.home() / ".cache" / "kaebench"))

# Settings that stop Freerouting from drawing tracks narrower than their class: automatic
# neck-down at pins is off, and so is the fanout pre-pass, whose escape insertion retries a
# blocked segment at 3/4, 3/5 and 1/2 of the class half-width whether or not neck-down is
# enabled (FoundConnectionInserter.insertFanoutMicroNeckdown, Freerouting 2.5.0).
NO_NARROWING = {"automatic_neckdown": "false", "fanout.enabled": "false"}


class FreeroutingError(RuntimeError):
    pass


def command():
    """Command prefix for Freerouting."""
    env = os.environ.get("KAE_BRIDGE_FREEROUTING")
    if env:
        return ["java", "-jar", env] if env.endswith(".jar") else [env]
    fork = sorted(KAE_HOME.glob("kae-freerouting-fork-*/bin/freerouting"), key=lambda q: q.stat().st_mtime)
    if fork:
        return [str(fork[-1])]
    env = os.environ.get("KAE_FREEROUTING")
    if env:
        return ["java", "-jar", env] if env.endswith(".jar") else [env]
    native = sorted(KAE_HOME.glob("freerouting-*-linux-x64/bin/freerouting"))
    if native:
        return [str(native[-1])]
    exe = shutil.which("freerouting")
    if exe:
        return [exe]
    jars = sorted(KAE_HOME.glob("freerouting-*.jar"))
    if jars:
        return ["java", "-jar", str(jars[-1])]
    raise FreeroutingError("Freerouting not found; set KAE_FREEROUTING or run bench/scripts/setup.sh")


@dataclass
class Run:
    rc: int | None
    ses: Path | None
    log: str
    seconds: float
    timed_out: bool = False
    report: dict = field(default_factory=dict)
    argv: list = field(default_factory=list)


def _hms(s):
    s = max(1, int(s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("FREEROUTING__")}
    # one CPU and a lean collector: the harness runs several boards in parallel
    opts = env.get("JAVA_TOOL_OPTIONS", "")
    for o in ("-XX:+UseSerialGC", "-XX:ActiveProcessorCount=1"):
        if o.split("=")[0].split(":")[-1] not in opts:
            opts = (opts + " " + o).strip()
    env["JAVA_TOOL_OPTIONS"] = opts
    return env


# Freerouting's job clock starts after the JVM has started and the DSN is loaded; at its
# job_timeout it asks the router to stop and waits up to 30 s for it to stop between items
# (RoutingJobSchedulerActionThread.GRACE_PERIOD), then writes the session. A process is
# killed only after that grace and the write: earlier, under load, there is no session.
GRACE_S = 45.0


def route(dsn, ses, workdir, *, passes=0, settings=None, budget_s=600.0, margin_s=None, hard_s=None,
          log_path=None):
    """Route `dsn` into `ses`. `passes` caps the autorouter passes (0 = until it stops
    improving). Freerouting's own deadline (job_timeout) is `budget_s` less its start-up
    (`margin_s`, default min(15 s, 10%)): it then stops between items and writes what it has
    routed. The process is killed only at `hard_s` (default budget_s + GRACE_S). Returns a
    Run (ses None when nothing was written)."""
    workdir = Path(workdir).resolve()
    dsn, ses = Path(dsn).resolve(), Path(ses).resolve()
    user = workdir / "fr-user"
    user.mkdir(parents=True, exist_ok=True)
    result = workdir / f"{ses.stem}.result.json"
    if ses.exists():
        ses.unlink()
    margin = margin_s if margin_s is not None else min(15.0, 0.1 * budget_s)
    job_s = max(5.0, budget_s - margin)
    hard = max(job_s + 5.0, hard_s if hard_s is not None else budget_s + GRACE_S)
    argv = [*command(), "-de", str(dsn), "-do", str(ses), "-mt", "1", "--gui.enabled=false", "-da",
            f"--user_data_path={user}", f"--router.result_json={result}",
            f"--router.job_timeout={_hms(job_s)}"]
    if passes:
        argv += ["-mp", str(int(passes))]
    for k, v in (settings or {}).items():
        argv.append(f"--router.{k}={v}")
    t0 = time.monotonic()
    p = subprocess.Popen(argv, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         errors="replace", env=_env(), start_new_session=True)
    timed_out = False
    try:
        out, _ = p.communicate(timeout=hard)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _ = p.communicate()
    dt = time.monotonic() - t0
    if log_path:
        Path(log_path).write_text(out or "")
    report = {}
    try:
        report = json.loads(result.read_text())
    except (OSError, ValueError):
        pass
    return Run(rc=p.returncode, ses=ses if ses.exists() and ses.stat().st_size > 0 else None, log=out or "",
               seconds=round(dt, 2), timed_out=timed_out, report=_summary(report), argv=argv)


def _summary(d):
    if not d:
        return {}
    use = d.get("resource_usage") or {}
    return dict(final_state=d.get("final_state"), router_score=d.get("normalized_score"),
                optimizer_score=d.get("optimizer_score"), cpu_s=use.get("cpu_time"),
                peak_mb=use.get("peak_memory"), app_version=d.get("app_version"))
