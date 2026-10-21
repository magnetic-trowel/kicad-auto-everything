# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Locate and drive external tools: kicad-cli, KiCad's Python (pcbnew), Freerouting."""
import functools
import json
import os
import shutil
import subprocess
from importlib import resources
from pathlib import Path

KAE_HOME = Path(os.environ.get("KAE_HOME", Path.home() / ".cache" / "kaebench"))

# Violation types that depend on the local library setup, not on the board.
ENV_DEPENDENT_CHECKS = ("lib_footprint_issues", "lib_footprint_mismatch")


class ToolError(RuntimeError):
    pass


def _first_existing(cands):
    for c in cands:
        if c and Path(c).exists():
            return str(c)
    return None


@functools.lru_cache(maxsize=None)
def kicad_cli():
    path = os.environ.get("KAE_KICAD_CLI") or shutil.which("kicad-cli") or _first_existing([
        "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
        r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
    ])
    if not path:
        raise ToolError("kicad-cli not found; install KiCad 10 or set KAE_KICAD_CLI")
    return path


@functools.lru_cache(maxsize=None)
def kicad_python():
    """An interpreter that can `import pcbnew`."""
    cands = [os.environ.get("KAE_KICAD_PYTHON"), "/usr/bin/python3", "/usr/bin/python3.12",
             "/usr/bin/python3.11",
             "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
             r"C:\Program Files\KiCad\10.0\bin\python.exe"]
    for c in cands:
        if not c or not Path(c).exists():
            continue
        r = subprocess.run([c, "-c", "import pcbnew"], capture_output=True, timeout=120)
        if r.returncode == 0:
            return c
    raise ToolError("no Python with pcbnew found; set KAE_KICAD_PYTHON to KiCad's interpreter")


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
    cmd = [kicad_python(), ops_script(), op, *map(str, args)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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
    cmd = [kicad_cli(), "pcb", "drc", "--format", "json", "--refill-zones", "--severity-all",
           "--units", "mm", "-o", str(out_json), board.name]
    try:
        r = subprocess.run(cmd, cwd=board.parent, capture_output=True, text=True, timeout=timeout)
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
        out["kicad_cli"] = subprocess.run([kicad_cli(), "version"], capture_output=True, text=True,
                                          timeout=60).stdout.strip()
    except (ToolError, OSError) as e:
        out["kicad_cli"] = f"unavailable: {e}"
    try:
        out["kicad_python"] = kicad_python()
    except ToolError as e:
        out["kicad_python"] = f"unavailable: {e}"
    try:
        cmd = freerouting_cmd()
        out["freerouting"] = " ".join(cmd)
    except ToolError as e:
        out["freerouting"] = f"unavailable: {e}"
    return out
