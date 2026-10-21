# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run an adapter over prepared tasks, k attempts each, and score every attempt."""
import json
import platform
import shutil
import subprocess
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, tools
from .boardfiles import board_path, copy_board, install_rules
from .prepare import TASK_SPEC, load_tasks
from .score import SCORE_VERSION, score_place_task, score_route_task, score_routing


def _git_rev():
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent,
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except OSError:
        return None


def _attempt(task_dir, rec, adapter, kind, attempt, timeout, adir, probe, keep_work):
    adir = Path(adir)
    done = adir / "attempt.json"
    if done.exists():
        return json.loads(done.read_text())
    if adir.exists():
        shutil.rmtree(adir)
    work = adir / "work"
    inp = work / "input"
    copy_board(task_dir / kind / "input", inp)
    reference = None
    if adapter.needs_reference:
        reference = {"route": board_path(task_dir / "reference"),
                     "place": board_path(task_dir / "route" / "input")}
    row = dict(adapter=adapter.name, kind=kind, id=rec["id"], split=rec["split"], attempt=attempt,
               tags=rec.get("tags", []), score_version=SCORE_VERSION)
    t0 = time.monotonic()
    try:
        res = adapter.run(kind, inp, work, attempt, timeout, reference=reference)
        row["status"] = "ok" if res.output else "no_output"
        row["adapter_meta"] = res.meta
        (adir / "adapter.log").write_text(res.log or "")
    except Exception as e:  # adapters are untrusted; record and move on
        res = None
        row["status"] = "adapter_error"
        row["error"] = f"{type(e).__name__}: {e}"
        (adir / "adapter.log").write_text(traceback.format_exc())
    row["runtime_s"] = round(time.monotonic() - t0, 3)
    if row["runtime_s"] > timeout * 1.05:
        row["over_time"] = True
    if res and res.output:
        out_dir = adir / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(res.output, board_path(out_dir))
        # Only the built-in reference adapter may reproduce the human layout.
        allow_copy = adapter.needs_reference
        try:
            if kind == "route":
                row["score"] = score_route_task(task_dir, board_path(out_dir), adir / "score", rec,
                                                allow_copy=allow_copy)
            else:
                pscore, placed_stats = score_place_task(task_dir, board_path(out_dir), adir / "score", rec,
                                                        allow_copy=allow_copy)
                row["score"] = pscore
                if probe is not None and pscore["valid"]:
                    # the probe routes the rebuilt placement, never the method's own file
                    row["probe"] = _probe(task_dir, rec, probe, adir / "score", placed_stats,
                                          pscore["unconnected"], attempt, timeout, adir)
        except Exception as e:
            row["status"] = "score_error"
            row["error"] = f"{type(e).__name__}: {e}"
            (adir / "score_error.log").write_text(traceback.format_exc())
    if not keep_work and work.exists():
        shutil.rmtree(work, ignore_errors=True)
    done.write_text(json.dumps(row, indent=1))
    return row


def _probe(task_dir, rec, probe, placed_dir, placed_stats, placed_unconnected, attempt, timeout, adir):
    """Route a placement with a fixed router (Cypress-style routability)."""
    pdir = adir / "probe"
    pin = pdir / "input"
    copy_board(placed_dir, pin)
    install_rules(task_dir / "reference", pin)  # the probe routes under the board's own rules
    t0 = time.monotonic()
    out = {"router": probe.name}
    try:
        res = probe.run("route", pin, pdir, attempt, timeout)
    except Exception as e:
        out.update(status="adapter_error", error=f"{type(e).__name__}: {e}")
        return out
    out["runtime_s"] = round(time.monotonic() - t0, 3)
    if not res.output:
        out["status"] = "no_output"
        return out
    out["status"] = "ok"
    out["score"] = score_routing(res.output, board_path(pin), placed_stats, placed_unconnected,
                                 rec["reference"]["stats"], task_dir / "reference", pdir / "score")
    return out


def run(tasks_dir, results_dir, adapter, kinds=("route",), k=1, timeout=600, jobs=1, probe=None,
        only=None, splits=None, qualified_only=True, name=None, keep_work=False, progress=print):
    tasks_dir, results_dir = Path(tasks_dir), Path(results_dir)
    recs = load_tasks(tasks_dir, only=only, qualified_only=qualified_only, splits=splits)
    stale = [r["id"] for r in recs if "place" in kinds and r.get("task_spec", 1) < TASK_SPEC]
    if stale:
        raise ValueError(f"{len(stale)} place tasks were prepared with an older task spec "
                         f"(e.g. {stale[0]}); re-run `kaebench prepare --force`")
    if hasattr(adapter, "hide"):
        adapter.hide(tasks_dir, results_dir)
    name = name or f"{adapter.name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = results_dir / name
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = dict(name=name, harness=__version__, git=_git_rev(), host=platform.node(),
                platform=platform.platform(), started=datetime.now(timezone.utc).isoformat(),
                tools=tools.versions(), adapter=adapter.describe(),
                probe=probe.describe() if probe else None, kinds=list(kinds), k=k, timeout=timeout,
                tasks_dir=str(tasks_dir), boards=len(recs), qualified_only=qualified_only,
                score_version=SCORE_VERSION, task_spec=TASK_SPEC)
    meta_path = run_dir / "run.json"
    if meta_path.exists():
        prev = json.loads(meta_path.read_text())
        meta["started"] = prev.get("started", meta["started"])
        meta["resumed"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=1))
    work = [(rec, kind, a) for rec in recs for kind in kinds
            if kind in adapter.kinds and kind in rec["tasks"] for a in range(k)]
    lock = threading.Lock()
    rows = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        futs = {ex.submit(_attempt, tasks_dir / rec["id"], rec, adapter, kind, a, timeout,
                          run_dir / adapter.name / kind / rec["id"] / f"attempt-{a}", probe,
                          keep_work): (rec["id"], kind, a) for rec, kind, a in work}
        for i, f in enumerate(as_completed(futs), 1):
            row = f.result()
            with lock:
                rows.append(row)
            s = row.get("score") or {}
            progress(f"[{i}/{len(futs)}] {row['id']} {row['kind']} #{row['attempt']}: {row['status']}"
                     f" clean={s.get('clean', s.get('legal'))} unconn={s.get('unconnected')}"
                     f" err={s.get('errors')} t={row['runtime_s']}s")
    rows.sort(key=lambda r: (r["kind"], r["id"], r["attempt"]))
    with open(run_dir / "results.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    meta["finished"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=1))
    return run_dir
