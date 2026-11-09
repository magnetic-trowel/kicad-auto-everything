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
import re

from kae import budget
import fcntl
import json
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import stepcache

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

    def __init__(self, timeout=None):
        self.f = None
        self.waited = 0.0
        self.timeout = timeout      # give up waiting after this many seconds (None: wait on)
        self.gave_up = False

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
            if self.timeout is not None and time.monotonic() - t0 >= self.timeout:
                # no slot within the budget: run without one rather than never
                self.waited, self.gave_up = round(time.monotonic() - t0, 1), True
                return self
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


def _pins(dsn):
    """Pins on the nets of a Specctra file: a pass's time grows as its square."""
    try:
        text = Path(dsn).read_text(errors="replace")
    except OSError:                      # the router reports a missing input itself
        return 1
    return max(1, sum(len(m.split()) for m in re.findall(r"\(pins\s+([^)]*)\)", text)))


PASS_DONE = re.compile(r"Auto-routing pass #\d+ on board .* was completed")


def route(dsn, ses, workdir, *, passes=0, settings=None, budget_s=600.0, margin_s=None, hard_s=None,
          log_path=None):
    """_route (below). In work mode (kae.budget) the budget is a pass cap, budget_s / the nominal
    seconds of one pass over this .dsn: Freerouting is deterministic while its job timeout does not
    fire, so the timeout is only the run's wall ceiling, and the passes done are charged."""
    size = _pins(dsn) ** 2
    if not budget.work_mode():
        run = _route(dsn, ses, workdir, passes=passes, settings=settings, budget_s=budget_s, margin_s=margin_s,
                     hard_s=hard_s, log_path=log_path)
        budget.charge("fr_pass_pin2", max(1, len(PASS_DONE.findall(run.log or ""))) * size)    # counted only
        return run
    cap = max(1, int(budget_s / max(1e-9, budget.clock().rates["fr_pass_pin2"] * size)))
    passes = min(passes, cap) if passes else cap
    wall = budget.wall_timeout(budget_s)
    run = _route(dsn, ses, workdir, passes=passes, settings=settings, budget_s=wall, margin_s=30.0,
                 hard_s=wall + GRACE_S, log_path=log_path)
    done = len(PASS_DONE.findall(run.log or ""))
    budget.charge("fr_pass_pin2", max(1, done) * size)
    run.report["passes_done"], run.report["passes_cap"] = done, passes
    return run


def _route(dsn, ses, workdir, *, passes=0, settings=None, budget_s=600.0, margin_s=None, hard_s=None,
           log_path=None):
    """Route `dsn` into `ses`. `passes` caps the autorouter passes (0 = until it stops
    improving). Freerouting's own deadline (job_timeout) is `budget_s` less its start-up
    (`margin_s`, default min(15 s, 10%)) and less the time spent waiting for a host slot
    (_Slot; a wait over SLOT_WARN of the budget is logged): it then stops between items and
    writes what it has routed. The process is killed only at `hard_s` (default budget_s +
    GRACE_S), also counted from the call. Returns a Run (ses None when nothing was written)."""
    workdir = Path(workdir).resolve()
    dsn, ses = Path(dsn).resolve(), Path(ses).resolve()
    settings = fork_settings(dsn, settings)
    user = workdir / "fr-user"
    user.mkdir(parents=True, exist_ok=True)
    result = workdir / f"{ses.stem}.result.json"
    if ses.exists():
        ses.unlink()
    margin = margin_s if margin_s is not None else min(15.0, 0.1 * budget_s)
    key = _cache_key(dsn, ses, workdir, user, result, passes, settings) if stepcache.enabled() else None
    if key:   # KAE_STEP_CACHE: the same DSN and settings routed before replay that session (see stepcache)
        hit = _replay(key, ses, result, workdir, budget_s, margin, hard_s, log_path, passes, settings, dsn, user)
        if hit is not None:
            return hit
    # the wait for a slot is part of the caller's budget: Freerouting gets what is left of it,
    # and after the budget it runs without a slot (a wait without end would hang the caller)
    # (work mode: a wait costs no budget, so it waits as long as the wall ceiling allows)
    slot = _Slot(timeout=max(1.0, budget_s - margin - 5.0)).__enter__()
    waited = slot.waited or 0.0
    if slot.gave_up:
        print(f"[kae.route {time.strftime('%H:%M:%S')}] warning: no Freerouting slot within {waited:.0f}s; "
              "running without one", flush=True)
    if waited > SLOT_WARN * budget_s:
        print(f"[kae.route {time.strftime('%H:%M:%S')}] warning: waited {waited:.0f}s for a Freerouting slot "
              f"({waited / max(budget_s, 1e-9):.0%} of the {budget_s:.0f}s budget; KAE_FR_SLOTS / KAE_FR_XMX)",
              flush=True)
    job_s = max(5.0, budget_s - margin - waited)
    hard = max(job_s + 5.0, (hard_s if hard_s is not None else budget_s + GRACE_S) - waited)
    argv = _argv(dsn, ses, user, result, job_s, passes, settings)
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
    if key:
        _store(key, p.returncode, dt, timed_out, out or "", report, ses, result, workdir, job_s)
    return Run(rc=p.returncode, ses=ses if ses.exists() and ses.stat().st_size > 0 else None, log=out or "",
               seconds=round(dt, 2), timed_out=timed_out,
               report=dict(_summary(report, out or ""), slot_wait_s=slot.waited, job_timeout_s=round(job_s, 1),
                          **({"slot_gave_up": True} if slot.gave_up else {})),
               argv=argv)


def fork_settings(dsn, settings):
    """`settings` plus what a DSN written for the fork asks: `kae_pin_entries` when the DSN holds
    the fr_entry scope (rule D tails and class width floors; other builds ignore the setting and
    skip the scope)."""
    s = dict(settings or {})
    try:
        with open(dsn, "rb") as f:
            f.seek(0, 2)
            n = f.tell()
            f.seek(max(0, n - (8 << 20)))
            tail = f.read()
    except OSError:
        return s
    if b"(kae_pin_entries" in tail:
        s.setdefault("kae_pin_entries", "true")
    return s


def pin_entry_stats(log):
    """The fork's summary line of rule D tails (`kae_pin_entries: k=v ...`), as a dict, or {}."""
    out = {}
    for line in (log or "").splitlines():
        i = line.find("kae_pin_entries:")
        if i >= 0:
            out = {}
            for kv in line[i + len("kae_pin_entries:"):].split():
                k, _, v = kv.partition("=")
                try:
                    out[k] = int(v)
                except ValueError:
                    out[k] = v
    return out


def _argv(dsn, ses, user, result, job_s, passes, settings):
    argv = [*command(), "-de", str(dsn), "-do", str(ses), "-mt", "1", "--gui.enabled=false", "-da",
            f"--user_data_path={user}", f"--router.result_json={result}",
            f"--router.job_timeout={_hms(job_s)}"]
    if passes:
        argv += ["-mp", str(int(passes))]
    for k, v in (settings or {}).items():
        argv.append(f"--router.{k}={v}")
    return argv


def _cache_key(dsn, ses, workdir, user, result, passes, settings):
    """Step-cache key of a Freerouting run: the DSN's bytes (its work directory normalised), the
    program's jars, argv without its paths or job timeout (a run that stopped by itself does not
    depend on it; _replay checks that it fits; _timeout_key adds it for one that did), and the JVM
    options."""
    argv = _argv(dsn, ses, user, result, 0, passes, settings)
    exe = argv[2] if argv[:2] == ["java", "-jar"] else argv[0]
    rest = [a for a in argv[3 if argv[:2] == ["java", "-jar"] else 1:] if not a.startswith("--router.job_timeout=")]
    rest = stepcache.norm_argv(rest, workdir, ((dsn, "<DSN>"), (ses, "<SES>"), (user, "<USER>"), (result, "<RESULT>")))
    return stepcache.make_key("freerouting", dict(
        tool=stepcache.tool_sha(shutil.which(exe) or exe), java=argv[:2] == ["java", "-jar"], argv=rest,
        dsn=stepcache.file_sha(dsn, workdir), jvm=_env().get("JAVA_TOOL_OPTIONS", "")))


TIMEOUT_BUCKET_S = 10.0   # runs that stopped at their job timeout are keyed by it, in steps of this


def _stopped_by_itself(report, log):
    s = _summary(report, log)
    return (bool(report) and report.get("final_state") != "TIMED_OUT" and s.get("autorouter_stop") != "TIMED_OUT"
            and s.get("optimizer_stop") != "timed_out")


def _timeout_key(key, job_s):
    return stepcache.make_key("freerouting-timed-out", dict(base=key, job=round(job_s / TIMEOUT_BUCKET_S)))


def _store(key, rc, dt, timed_out, log, report, ses, result, workdir, job_s):
    """Cache a run that wrote a session and was not killed. One that stopped by itself is the result
    under any job timeout it fits in (key without it); one that stopped at its job timeout is the
    result under that timeout (key with it, to TIMEOUT_BUCKET_S)."""
    ok = rc == 0 and not timed_out and ses.exists() and ses.stat().st_size > 0
    if ok:
        own = _stopped_by_itself(report, log)
        logf = Path(workdir) / f"{ses.stem}.cache-log"
        logf.write_text(log)
        stepcache.put(key if own else _timeout_key(key, job_s),
                      dict(step="freerouting", rc=rc, seconds=round(dt, 3), job_s=round(job_s, 1), stopped_by_itself=own,
                           final_state=report.get("final_state")),
                      {"ses": ses, "result": result, "log": logf}, workdir)
        logf.unlink()
    stepcache.charge("freerouting", False, dt, dt, key, cacheable=ok)


def _replay(key, ses, result, workdir, budget_s, margin, hard_s, log_path, passes, settings, dsn, user):
    """A Run from the cache, or None: a run that stopped by itself and fits in this call's job
    timeout and kill time (with no slot wait), else one that stopped at this call's job timeout.
    Charged its recorded duration."""
    t0 = time.monotonic()
    job_s = max(5.0, budget_s - margin)
    hard = max(job_s + 5.0, hard_s if hard_s is not None else budget_s + GRACE_S)
    for k in (key, _timeout_key(key, job_s)):
        with stepcache.reading(k) as meta:
            if meta is None or meta["seconds"] > hard - 2.0 or (k == key and meta["seconds"] + 2.0 > job_s):
                continue
            logf = Path(workdir) / f"{ses.stem}.cache-log"
            try:
                stepcache.restore(meta, {"ses": ses, "result": result, "log": logf}, workdir)
            except OSError:
                continue
        log = logf.read_text(errors="replace")
        logf.unlink()
        if log_path:
            Path(log_path).write_text(log)
        try:
            report = json.loads(result.read_text())
        except (OSError, ValueError):
            report = {}
        stepcache.charge("freerouting", True, meta["seconds"], time.monotonic() - t0, k)
        return Run(rc=meta["rc"], ses=ses, log=log, seconds=meta["seconds"], timed_out=False,
                   report=dict(_summary(report, log), slot_wait_s=0.0, job_timeout_s=round(job_s, 1),
                               step_cache="hit"),
                   argv=_argv(dsn, ses, user, result, job_s, passes, settings))
    return None


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
                autorouter_stop=ar_stop, optimizer_stop=_optimizer_stop(log),
                **({"pin_entries": pe} if (pe := pin_entry_stats(log)) else {}))
