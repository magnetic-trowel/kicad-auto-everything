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
import sys
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
# Every external process (method, router, KiCad) runs through run_measured, which reads its
# CPU time and peak memory from wait4. Totals accumulate per thread, so the runner (one
# attempt per thread) can split them into method, scoring and probe costs.
#
# The command is not spawned from the runner directly. On exec, Linux folds the high-water
# RSS of the address space being replaced into the new process's ru_maxrss
# (exec_mmap -> setmax_mm_hiwater_rss). Python spawns with vfork/posix_spawn, so that is
# the runner's own address space, and every child reported at least the runner's peak RSS
# (a 1 MB /bin/true read as GBs). _LAUNCHER, a fresh `python -I -S` process of ~10 MB,
# forks and execs the command from its own small address space, reaps it with wait4 and
# reports the command's rusage on a pipe. max_rss_mb is therefore the peak RSS of the
# largest single process in the command's tree (ru_maxrss is a per-process maximum, not
# a sum over the tree), with a floor of the launcher's ~10 MB.

_usage = threading.local()

_LAUNCHER = r"""
import os, sys
fd = int(sys.argv[1]); argv = sys.argv[2:]
os.set_inheritable(fd, False)
er, ew = os.pipe()
pid = os.fork()
if pid == 0:
    try:
        os.setpgid(0, 0)
        os.execvp(argv[0], argv)
    except OSError as e:
        os.write(ew, str(e.errno).encode())
    os._exit(127)
try:
    os.setpgid(pid, pid)
except OSError:
    pass
os.close(ew)
os.write(fd, b"pid %d\n" % pid)
err = os.read(er, 64)
if err:
    os.write(fd, b"exec %s\n" % err)
_, status, ru = os.wait4(pid, 0)
os.write(fd, ("done %d %r %r %d\n" % (status, ru.ru_utime, ru.ru_stime, ru.ru_maxrss)).encode())
"""


def usage_take():
    """Return and reset this thread's accumulated usage of external processes."""
    u = getattr(_usage, "u", None) or dict(cpu_user_s=0.0, cpu_sys_s=0.0, max_rss_mb=0.0, processes=0)
    _usage.u = None
    return dict(cpu_s=round(u["cpu_user_s"] + u["cpu_sys_s"], 3), cpu_user_s=round(u["cpu_user_s"], 3),
                cpu_sys_s=round(u["cpu_sys_s"], 3), max_rss_mb=round(u["max_rss_mb"], 1),
                processes=u["processes"])


def _account(utime, stime, maxrss_kib=None):
    u = getattr(_usage, "u", None)
    if u is None:
        u = _usage.u = dict(cpu_user_s=0.0, cpu_sys_s=0.0, max_rss_mb=0.0, processes=0)
    u["cpu_user_s"] += utime
    u["cpu_sys_s"] += stime
    if maxrss_kib is not None:
        u["max_rss_mb"] = max(u["max_rss_mb"], maxrss_kib / 1024.0)  # Linux: KiB
    u["processes"] += 1


def _read_fd(fd, block):
    os.set_blocking(fd, block)
    data = b""
    while True:
        try:
            b = os.read(fd, 4096)
        except BlockingIOError:
            break
        if not b:
            break
        data += b
    return data


def _parse_report(data):
    rep = {}
    for line in data.decode(errors="replace").splitlines():
        k, _, v = line.partition(" ")
        rep[k] = v.split()
    return rep


class Stalled(subprocess.TimeoutExpired):
    """The command made no CPU progress for `stall` seconds (see run_measured)."""

    def __init__(self, cmd, timeout, stall, output=None, stderr=None):
        super().__init__(cmd, timeout, output=output, stderr=stderr)
        self.stall = stall

    def __str__(self):
        return f"Command {self.cmd!r} made no CPU progress for {self.stall} seconds"


# A command whose process tree uses less than this share of one core over the whole stall
# window is waiting on something that will not come (KiCad's zone filler polls a deadlocked
# job graph at ~0.4% of a core).
STALL_CPU_SHARE = 0.02
_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def _tree_cpu_s(pid):
    """CPU seconds of a live process and its descendants, including reaped children
    (Linux /proc; 0 elsewhere)."""
    ticks, stack, seen = 0, [pid], set()
    while stack:
        q = stack.pop()
        if q in seen:
            continue
        seen.add(q)
        try:
            with open(f"/proc/{q}/stat") as f:
                fields = f.read().rpartition(")")[2].split()
            ticks += sum(int(x) for x in fields[11:15])  # utime stime cutime cstime
            for t in os.listdir(f"/proc/{q}/task"):
                with open(f"/proc/{q}/task/{t}/children") as f:
                    stack += [int(c) for c in f.read().split()]
        except (OSError, ValueError, IndexError):
            pass
    return ticks / _CLK_TCK


def run_measured(cmd, timeout=None, cwd=None, env=None, stall=None):
    """subprocess.run(cmd, capture_output=True, text=True) that also accounts the process
    tree's CPU time and peak RSS (wait4, via _LAUNCHER), and kills the whole tree on
    timeout (raises subprocess.TimeoutExpired like subprocess.run).

    With `stall` (seconds), the tree is also killed once it has used less than
    STALL_CPU_SHARE of one core over the last `stall` seconds, and Stalled (a
    TimeoutExpired) is raised: a hang is cut short instead of waiting out the timeout."""
    cmd = [os.fspath(c) for c in cmd]
    rfd, wfd = os.pipe()
    try:
        p = subprocess.Popen([sys.executable, "-I", "-S", "-c", _LAUNCHER, str(wfd), *cmd],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd, env=env,
                             errors="replace", start_new_session=True, pass_fds=(wfd,))
    finally:
        os.close(wfd)
    chunks = {}

    def read(name, f):
        chunks[name] = f.read()

    readers = [threading.Thread(target=read, args=(n, f), daemon=True)
               for n, f in (("out", p.stdout), ("err", p.stderr))]
    for t in readers:
        t.start()
    start = time.monotonic()
    deadline = start + timeout if timeout else None
    timed_out = stalled = False
    early = b""
    samples, next_sample = [], start
    try:
        while True:
            pid, status, ru = os.wait4(p.pid, os.WNOHANG)
            if pid:
                break
            now = time.monotonic()
            if stall and now >= next_sample:
                next_sample = now + min(5.0, stall / 4)
                samples.append((now, _tree_cpu_s(p.pid)))
                while len(samples) > 1 and samples[1][0] <= now - stall:
                    samples.pop(0)
                t0, c0 = samples[0]
                stalled = now - t0 >= stall and samples[-1][1] - c0 < STALL_CPU_SHARE * (now - t0)
            if stalled or (deadline and now > deadline):
                timed_out = True
                # Kill the command's group first so the launcher can still reap it and
                # report its usage; then the launcher itself.
                early = _read_fd(rfd, block=False)
                rep = _parse_report(early)
                for g in [int(rep["pid"][0])] if "pid" in rep else []:
                    try:
                        os.killpg(g, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                end = time.monotonic() + 10
                while not pid and time.monotonic() < end:
                    pid, status, ru = os.wait4(p.pid, os.WNOHANG)
                    time.sleep(0.05)
                if not pid:
                    try:
                        os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    pid, status, ru = os.wait4(p.pid, 0)
                break
            time.sleep(0.05)
        rest = _read_fd(rfd, block=True)
    finally:
        os.close(rfd)
    rep = _parse_report(early + rest)
    if "pid" in rep and timed_out:  # the pid may have arrived only after the first read
        try:
            os.killpg(int(rep["pid"][0]), signal.SIGKILL)
        except ProcessLookupError:
            pass
    for t in readers:
        t.join(timeout=30)
    out, err = chunks.get("out", ""), chunks.get("err", "")
    if "done" in rep:
        st, ut, syt, mx = rep["done"]
        p.returncode = os.waitstatus_to_exitcode(int(st))
        _account(float(ut), float(syt), int(mx))
    else:  # launcher killed before it could reap the command: CPU of what it reaped, no peak
        p.returncode = os.waitstatus_to_exitcode(status)
        _account(ru.ru_utime, ru.ru_stime)
    if "exec" in rep and not timed_out:
        e = int(rep["exec"][0])
        raise OSError(e, os.strerror(e), cmd[0])
    if stalled:
        raise Stalled(cmd, timeout, stall, output=out, stderr=err)
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


def run_drc(board, out_json, timeout=None, stall=None):
    """kicad-cli DRC with zone refill; returns the parsed JSON report.

    Timeout defaults to $KAE_DRC_TIMEOUT or 900 s (zone refill on big boards is slow).
    A DRC that makes no CPU progress for `stall` seconds ($KAE_DRC_STALL, default 600;
    0 disables) is a hang and fails early (see run_measured).
    """
    timeout = timeout or float(os.environ.get("KAE_DRC_TIMEOUT", 900))
    stall = float(os.environ.get("KAE_DRC_STALL", 600)) if stall is None else stall
    board = Path(board)
    # absolute paths, so wrapped (containerised) kicad-cli does not depend on the cwd
    cmd = [*kicad_cli(), "pcb", "drc", "--format", "json", "--refill-zones", "--severity-all",
           "--units", "mm", "-o", str(Path(out_json).resolve()), str(board.resolve())]
    try:
        r = run_measured(cmd, timeout=timeout, cwd=board.parent, stall=stall or None)
    except Stalled:
        raise ToolError(f"DRC stalled: no CPU progress for {stall}s (KiCad hang)")
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
