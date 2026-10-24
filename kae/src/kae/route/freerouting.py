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
import fcntl
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
    # a bounded heap: by default the JVM may take a quarter of the cgroup's memory and, on a
    # long budget, grows toward it whether or not the board needs it (KAE_FR_XMX, e.g. 6g)
    if "-Xmx" not in opts:
        opts = (opts + " -Xmx" + env.get("KAE_FR_XMX", "6g")).strip()
    env["JAVA_TOOL_OPTIONS"] = opts
    return env


def _gb(v):
    v = str(v).strip().lower()
    mult = {"k": 1 / 2 ** 20, "m": 1 / 1024, "g": 1.0, "t": 1024.0}
    return float(v[:-1]) * mult[v[-1]] if v and v[-1] in mult else float(v) / 2 ** 30


def _host_gb():
    """Memory this process may use: the cgroup limit if one is set, else MemTotal."""
    lims = []
    for f in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            t = Path(f).read_text().strip()
            if t.isdigit() and int(t) < 2 ** 60:
                lims.append(int(t) / 2 ** 30)
        except OSError:
            pass
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                lims.append(int(line.split()[1]) / 2 ** 20)
    except OSError:
        pass
    return min(lims) if lims else None


def slots():
    """How many Freerouting JVMs may run at once on this host, across processes: KAE_FR_SLOTS,
    else 60% of the host's memory over the heap cap (at least 1). Several agents or jobs on a
    small host otherwise get JVMs OOM-killed (rc -9), which silently degrades their results."""
    if os.environ.get("KAE_FR_SLOTS"):
        return max(1, int(os.environ["KAE_FR_SLOTS"]))
    host = _host_gb()
    if not host:
        return None
    xmx = _gb(os.environ.get("KAE_FR_XMX", "6g"))
    return max(1, int(0.6 * host // (xmx + 0.5)))


class _Slot:
    """A host-wide slot (flock on one of N files in KAE_FR_LOCKDIR, default /tmp/kae-fr-slots);
    waits for a free one. No-op when the directory cannot be used."""

    def __init__(self):
        self.f = None
        self.waited = 0.0

    def __enter__(self):
        n = slots()
        d = Path(os.environ.get("KAE_FR_LOCKDIR", "/tmp/kae-fr-slots"))
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            return self
        if not n:
            return self
        t0 = time.monotonic()
        while True:
            for i in range(n):
                try:
                    f = open(d / f"slot{i}", "a")
                except OSError:
                    return self
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.f, self.waited = f, round(time.monotonic() - t0, 1)
                    return self
                except OSError:
                    f.close()
            time.sleep(1.0)

    def __exit__(self, *exc):
        if self.f is not None:
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()


# Freerouting's job clock starts after the JVM has started and the DSN is loaded; at its
# job_timeout it asks the router to stop and waits up to 30 s for it to stop between items
# (RoutingJobSchedulerActionThread.GRACE_PERIOD), then writes the session. A process is
# killed only after that grace and the write: earlier, under load, there is no session.
GRACE_S = 45.0
SLOT_WARN = 0.10     # a slot wait above this share of the budget is logged


def route(dsn, ses, workdir, *, passes=0, settings=None, budget_s=600.0, margin_s=None, hard_s=None,
          log_path=None):
    """Route `dsn` into `ses`. `passes` caps the autorouter passes (0 = until it stops
    improving). Freerouting's own deadline (job_timeout) is `budget_s` less its start-up
    (`margin_s`, default min(15 s, 10%)) and less the time spent waiting for a host slot
    (_Slot; a wait over SLOT_WARN of the budget is logged): it then stops between items and
    writes what it has routed. The process is killed only at `hard_s` (default budget_s +
    GRACE_S), also counted from the call. Returns a Run (ses None when nothing was written)."""
    workdir = Path(workdir).resolve()
    dsn, ses = Path(dsn).resolve(), Path(ses).resolve()
    user = workdir / "fr-user"
    user.mkdir(parents=True, exist_ok=True)
    result = workdir / f"{ses.stem}.result.json"
    if ses.exists():
        ses.unlink()
    margin = margin_s if margin_s is not None else min(15.0, 0.1 * budget_s)
    slot = _Slot().__enter__()
    # the wait for a slot is part of the caller's budget: Freerouting gets what is left of it
    waited = slot.waited or 0.0
    if waited > SLOT_WARN * budget_s:
        print(f"[kae.route {time.strftime('%H:%M:%S')}] warning: waited {waited:.0f}s for a Freerouting slot "
              f"({waited / max(budget_s, 1e-9):.0%} of the {budget_s:.0f}s budget; KAE_FR_SLOTS / KAE_FR_XMX)",
              flush=True)
    job_s = max(5.0, budget_s - margin - waited)
    hard = max(job_s + 5.0, (hard_s if hard_s is not None else budget_s + GRACE_S) - waited)
    argv = [*command(), "-de", str(dsn), "-do", str(ses), "-mt", "1", "--gui.enabled=false", "-da",
            f"--user_data_path={user}", f"--router.result_json={result}",
            f"--router.job_timeout={_hms(job_s)}"]
    if passes:
        argv += ["-mp", str(int(passes))]
    for k, v in (settings or {}).items():
        argv.append(f"--router.{k}={v}")
    try:
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
    finally:
        slot.__exit__()
    dt = time.monotonic() - t0
    if log_path:
        Path(log_path).write_text(out or "")
    report = {}
    try:
        report = json.loads(result.read_text())
    except (OSError, ValueError):
        pass
    return Run(rc=p.returncode, ses=ses if ses.exists() and ses.stat().st_size > 0 else None, log=out or "",
               seconds=round(dt, 2), timed_out=timed_out,
               report=dict(_summary(report, out or ""), slot_wait_s=slot.waited, job_timeout_s=round(job_s, 1)),
               argv=argv)


def _autorouter_stop(log, final_state):
    """Why the autorouter's pass loop ended (the fork's StopReason), from its log: it logs
    stagnation and no-improvement stops; a job past its deadline ends TIMED_OUT; otherwise the
    loop ran out of work (COMPLETED: every connection it could attempt was routed)."""
    if "not able to improve the board" in log:
        return "NO_IMPROVEMENT"
    if "has not improved by more than" in log:
        return "STAGNATION"
    if final_state == "TIMED_OUT":
        return "TIMED_OUT"
    return "COMPLETED" if final_state else None


def _optimizer_stop(log):
    """Why the optimizer stage ended, from Freerouting's log (the result file does not say)."""
    if "Stopping optimizer because the improvement" in log:
        return "below_threshold"
    if "Optimizer stage timed out" in log:
        return "timed_out"
    if "Skipping optimization stage" in log:
        return "skipped"
    return None


def _summary(d, log=""):
    """The parts of Freerouting's result file the bridge reports, plus why each stage stopped:
    `autorouter_stop` is the fork's StopReason for the chosen attempt (COMPLETED: nothing left
    to route; STAGNATION / NO_IMPROVEMENT: its score stopped improving; TIMED_OUT: the clock;
    MAX_PASSES), `optimizer_stop` is below_threshold, timed_out or skipped."""
    if not d:
        return {}
    use = d.get("resource_usage") or {}
    fb = (d.get("phases") or {}).get("fallback") or {}
    att = fb.get("attempts") or []
    chosen = next((a for a in att if a.get("strategy") == fb.get("chosen")), att[-1] if att else {})
    ar_stop = chosen.get("stop_reason") or _autorouter_stop(log, d.get("final_state"))
    return dict(final_state=d.get("final_state"), router_score=d.get("normalized_score"),
                optimizer_score=d.get("optimizer_score"), cpu_s=use.get("cpu_time"),
                peak_mb=use.get("peak_memory"), app_version=d.get("app_version"),
                autorouter_stop=ar_stop, optimizer_stop=_optimizer_stop(log))
