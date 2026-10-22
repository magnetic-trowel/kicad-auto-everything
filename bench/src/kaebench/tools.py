# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Locate and drive external tools: kicad-cli, KiCad's Python (pcbnew), Freerouting."""
import functools
import json
import os
import shlex
import shutil
import signal
import subprocess
import threading
import time
from importlib import resources
from pathlib import Path

KAE_HOME = Path(os.environ.get("KAE_HOME", Path.home() / ".cache" / "kaebench"))

# Violation types that depend on the local library setup, not on the board.
ENV_DEPENDENT_CHECKS = ("lib_footprint_issues", "lib_footprint_mismatch")


class ToolError(RuntimeError):
    pass


# --- resource accounting -------------------------------------------------------------
# Every external process (method, router, KiCad) runs through run_measured, which reaps it
# with wait4 to read its CPU time and peak memory. Totals accumulate per thread, so the
# runner (one attempt per thread) can split them into method, scoring and probe costs.

_usage = threading.local()


def usage_take():
    """Return and reset this thread's accumulated usage of external processes."""
    u = getattr(_usage, "u", None) or dict(cpu_user_s=0.0, cpu_sys_s=0.0, max_rss_mb=0.0, processes=0)
    _usage.u = None
    return dict(cpu_s=round(u["cpu_user_s"] + u["cpu_sys_s"], 3), cpu_user_s=round(u["cpu_user_s"], 3),
                cpu_sys_s=round(u["cpu_sys_s"], 3), max_rss_mb=round(u["max_rss_mb"], 1),
                processes=u["processes"])


def _account(ru):
    u = getattr(_usage, "u", None)
    if u is None:
        u = _usage.u = dict(cpu_user_s=0.0, cpu_sys_s=0.0, max_rss_mb=0.0, processes=0)
    u["cpu_user_s"] += ru.ru_utime
    u["cpu_sys_s"] += ru.ru_stime
    u["max_rss_mb"] = max(u["max_rss_mb"], ru.ru_maxrss / 1024.0)  # Linux: KiB
    u["processes"] += 1


def run_measured(cmd, timeout=None, cwd=None):
    """subprocess.run(cmd, capture_output=True, text=True) that also accounts the process
    tree's CPU time and peak RSS (wait4), and kills the whole tree on timeout
    (raises subprocess.TimeoutExpired like subprocess.run)."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd,
                         errors="replace", start_new_session=True)
    chunks = {}

    def read(name, f):
        chunks[name] = f.read()

    readers = [threading.Thread(target=read, args=(n, f), daemon=True)
               for n, f in (("out", p.stdout), ("err", p.stderr))]
    for t in readers:
        t.start()
    deadline = time.monotonic() + timeout if timeout else None
    timed_out = False
    while True:
        pid, status, ru = os.wait4(p.pid, os.WNOHANG)
        if pid:
            break
        if deadline and time.monotonic() > deadline:
            timed_out = True
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            pid, status, ru = os.wait4(p.pid, 0)
            break
        time.sleep(0.05)
    p.returncode = os.waitstatus_to_exitcode(status)
    for t in readers:
        t.join(timeout=30)
    _account(ru)
    out, err = chunks.get("out", ""), chunks.get("err", "")
    if timed_out:
        raise subprocess.TimeoutExpired(cmd, timeout, output=out, stderr=err)
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def _first_existing(cands):
    for c in cands:
        if c and Path(c).exists():
            return str(c)
    return None


def _env_cmd(name):
    """An environment variable holding a command, possibly with a wrapper prefix."""
    v = os.environ.get(name)
    return shlex.split(v) if v else None


@functools.lru_cache(maxsize=None)
def kicad_cli():
    """Command prefix for kicad-cli.

    KAE_KICAD_CLI overrides it (may include a wrapper, e.g. "flatpak run
    --command=kicad-cli org.kicad.KiCad"); KAE_KICAD_WRAP prefixes the default name
    (e.g. "apptainer exec ~/kicad.sif" for KiCad in a container, no root needed).
    """
    cmd = _env_cmd("KAE_KICAD_CLI")
    if cmd:
        return cmd
    wrap = _env_cmd("KAE_KICAD_WRAP")
    if wrap:
        return [*wrap, "kicad-cli"]
    path = shutil.which("kicad-cli") or _first_existing([
        "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
        r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
    ])
    if not path:
        raise ToolError("kicad-cli not found; install KiCad 10, or set KAE_KICAD_CLI / KAE_KICAD_WRAP")
    return [path]


@functools.lru_cache(maxsize=None)
def kicad_python():
    """Command prefix for a Python that can `import pcbnew` (KAE_KICAD_PYTHON / KAE_KICAD_WRAP)."""
    cmd = _env_cmd("KAE_KICAD_PYTHON")
    wrap = _env_cmd("KAE_KICAD_WRAP")
    if cmd:
        cands = [cmd]
    elif wrap:
        cands = [[*wrap, "python3"]]
    else:
        cands = [[c] for c in ("/usr/bin/python3", "/usr/bin/python3.12", "/usr/bin/python3.11",
                               "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
                               r"C:\Program Files\KiCad\10.0\bin\python.exe") if Path(c).exists()]
    for c in cands:
        try:
            r = subprocess.run([*c, "-c", "import pcbnew"], capture_output=True, timeout=300)
        except OSError:
            continue
        if r.returncode == 0:
            return c
    raise ToolError("no Python with pcbnew found; set KAE_KICAD_PYTHON or KAE_KICAD_WRAP")


@functools.lru_cache(maxsize=None)
def freerouting_cmd():
    """Command prefix for Freerouting (native bundle preferred; the JAR needs Java 25)."""
    env = os.environ.get("KAE_FREEROUTING")
    if env:
        return [env] if not env.endswith(".jar") else ["java", "-jar", env]
    native = sorted(KAE_HOME.glob("freerouting-*-linux-x64/bin/freerouting"))
    if native:
        return [str(native[-1])]
    exe = shutil.which("freerouting")
    if exe:
        return [exe]
    jars = sorted(KAE_HOME.glob("freerouting-*.jar"))
    if jars:
        return ["java", "-jar", str(jars[-1])]
    raise ToolError("Freerouting not found; run bench/scripts/setup.sh or set KAE_FREEROUTING")


def ops_script():
    return str(resources.files("kaebench") / "kicad_scripts" / "pcbnew_ops.py")


def run_ops(op, *args, timeout=600):
    """Run a pcbnew operation in KiCad's Python; return its JSON result."""
    cmd = [*kicad_python(), ops_script(), op, *map(str, args)]
    try:
        r = run_measured(cmd, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolError(f"pcbnew {op} timed out after {timeout}s")
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("{")]
    if not lines:
        raise ToolError(f"pcbnew {op} produced no result (rc={r.returncode}): {r.stderr[-800:]}")
    res = json.loads(lines[-1])
    if not res.get("ok"):
        raise ToolError(f"pcbnew {op} failed: {res.get('error')}")
    return res


def run_drc(board, out_json, timeout=None):
    """kicad-cli DRC with zone refill; returns the parsed JSON report.

    Timeout defaults to $KAE_DRC_TIMEOUT or 900 s (zone refill on big boards is slow).
    """
    timeout = timeout or float(os.environ.get("KAE_DRC_TIMEOUT", 900))
    board = Path(board)
    # absolute paths, so wrapped (containerised) kicad-cli does not depend on the cwd
    cmd = [*kicad_cli(), "pcb", "drc", "--format", "json", "--refill-zones", "--severity-all",
           "--units", "mm", "-o", str(Path(out_json).resolve()), str(board.resolve())]
    try:
        r = run_measured(cmd, timeout=timeout, cwd=board.parent)
    except subprocess.TimeoutExpired:
        raise ToolError(f"DRC timed out after {timeout}s")
    if not Path(out_json).exists():
        raise ToolError(f"DRC failed (rc={r.returncode}): {(r.stdout + r.stderr)[-800:]}")
    with open(out_json) as f:
        return json.load(f)


def summarize_drc(report, ignore=ENV_DEPENDENT_CHECKS):
    """Counts used for scoring. Severities come from the board's own project settings."""
    errors, warnings, by_type = 0, 0, {}
    for v in report.get("violations", []):
        if v.get("type") in ignore:
            continue
        sev = v.get("severity")
        if sev == "error":
            errors += 1
            by_type[v["type"]] = by_type.get(v["type"], 0) + 1
        elif sev == "warning":
            warnings += 1
    return dict(unconnected=len(report.get("unconnected_items", [])), errors=errors,
                warnings=warnings, errors_by_type=by_type)


@functools.lru_cache(maxsize=None)
def versions():
    out = {}
    try:
        out["kicad_cli"] = subprocess.run([*kicad_cli(), "version"], capture_output=True, text=True,
                                          timeout=60).stdout.strip()
    except (ToolError, OSError) as e:
        out["kicad_cli"] = f"unavailable: {e}"
    try:
        out["kicad_python"] = " ".join(kicad_python())
    except ToolError as e:
        out["kicad_python"] = f"unavailable: {e}"
    try:
        cmd = freerouting_cmd()
        out["freerouting"] = " ".join(cmd)
    except ToolError as e:
        out["freerouting"] = f"unavailable: {e}"
    return out
