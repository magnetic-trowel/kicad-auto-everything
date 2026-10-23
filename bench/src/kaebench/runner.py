# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run an adapter over prepared tasks, k attempts each, and score every attempt."""
import json
import os
import platform
import random
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
from .prepare import INPUT_KIND, MIN_TASK_SPEC, TASK_SPEC, load_tasks
from .score import SCORE_VERSION, score_joint_task, score_place_task, score_route_task, score_routing


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
    copy_board(task_dir / INPUT_KIND[kind] / "input", inp)
    reference = None
    if adapter.needs_reference:
        reference = {"route": board_path(task_dir / "reference"), "joint": board_path(task_dir / "reference"),
                     "joint_placement": board_path(task_dir / "route" / "input"),
                     "place": board_path(task_dir / "route" / "input")}
    row = dict(adapter=adapter.name, kind=kind, id=rec["id"], split=rec["split"], attempt=attempt,
               tags=rec.get("tags", []), score_version=SCORE_VERSION, load_avg_start=os.getloadavg())
    tools.usage_take()  # start this attempt's accounting from zero
    t0 = time.monotonic()
    try:
        res = adapter.run(kind, inp, work, attempt, timeout, reference=reference)
        row["status"] = "ok" if res.output else "no_output"
        row["adapter_meta"] = res.meta
        (adir / "adapter.log").write_text(res.log or "")
        _keep_artifacts(res.meta, adir / "artifacts")
    except Exception as e:  # adapters are untrusted; record and move on
        res = None
        row["status"] = "adapter_error"
        row["error"] = f"{type(e).__name__}: {e}"
        meta = getattr(e, "adapter_meta", None)  # what an adapter got done before it failed
        if meta:
            row["adapter_meta"] = meta
            _keep_artifacts(meta, adir / "artifacts")
        (adir / "adapter.log").write_text(getattr(e, "adapter_log", "") + traceback.format_exc())
    row["runtime_s"] = round(time.monotonic() - t0, 3)
    row["method_usage"] = tools.usage_take()  # CPU and peak RSS of every process the method ran
    if row["runtime_s"] > timeout * 1.05:
        row["over_time"] = True
    if res and res.output:
        out_dir = adir / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(res.output, board_path(out_dir))
        # Only the built-in reference adapter may reproduce the human layout.
        t1 = time.monotonic()
        _score(row, task_dir, rec, kind, adir, adapter.needs_reference, probe=probe,
               probe_args=(attempt, timeout))
        row["scoring_s"] = round(time.monotonic() - t1, 3)
        u = tools.usage_take()  # rebuild, stats and DRC (a placement's probe is counted separately)
        row.setdefault("scoring_usage", u)
    row["load_avg_end"] = os.getloadavg()
    if not keep_work and work.exists():
        shutil.rmtree(work, ignore_errors=True)
    done.write_text(json.dumps(row, indent=1))
    return row


def _keep_artifacts(meta, dest):
    """Copy the files a method lists in meta["artifacts"] (e.g. the router's DSN, SES and own
    result report) into the attempt before its work directory is deleted."""
    paths = [Path(p) for p in (meta or {}).pop("artifacts", []) or []]
    kept = []
    for p in paths:
        if p.is_file():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest / p.name)
            kept.append(p.name)
    if kept:
        meta["artifacts_kept"] = kept


def _score(row, task_dir, rec, kind, adir, allow_copy, probe=None, probe_args=None, rescore_probe=False):
    """Score adir/output into row (and route the placement with the probe, or re-score the
    probe's saved output when rescoring)."""
    out = board_path(adir / "output")
    try:
        if kind == "route":
            row["score"] = score_route_task(task_dir, out, adir / "score", rec, allow_copy=allow_copy)
            return
        if kind == "joint":
            row["score"] = score_joint_task(task_dir, out, adir / "score", rec, allow_copy=allow_copy)
            return
        pscore, placed_stats = score_place_task(task_dir, out, adir / "score", rec, allow_copy=allow_copy)
        row["score"] = pscore
        row["scoring_usage"] = tools.usage_take()  # before the probe starts its own accounting
        if probe is not None and pscore["valid"]:
            # the probe routes the rebuilt placement, never the method's own file
            row["probe"] = _probe(task_dir, rec, probe, adir / "score", placed_stats,
                                  pscore["unconnected"], *probe_args, adir)
        elif rescore_probe and row.get("probe"):
            row["probe"] = _rescore_probe(task_dir, rec, row["probe"], pscore, placed_stats, adir)
    except Exception as e:
        row["status"] = "score_error"
        row["error"] = f"{type(e).__name__}: {e}"
        (adir / "score_error.log").write_text(traceback.format_exc())


def _rescore_probe(task_dir, rec, old, pscore, placed_stats, adir):
    """Re-score a probe's saved route of the placement. The probe routed the board rebuilt
    by the old scorer; if the new one rebuilds it differently, the probe result comes out
    invalid (its placement no longer matches) instead of silently mixing versions."""
    pdir = adir / "probe"
    routed = board_path(pdir / "output")
    if old.get("status") != "ok" or not routed.exists():
        return old
    if not pscore["valid"]:
        return dict(old, status="skipped_invalid_placement", score=None)
    new = dict(old)
    new["score"] = score_routing(routed, board_path(pdir / "input"), placed_stats, pscore["unconnected"],
                                 rec["reference"]["stats"], task_dir / "reference", pdir / "score")
    return new


def rescore(results_run_dir, jobs=1, progress=print, force=False):
    """Score every saved output of a run again with the current scorer (after a scoring fix),
    without re-running the method. Attempts that produced no output keep their status;
    attempts already scored by this scorer version are skipped unless force."""
    run_dir = Path(results_run_dir)
    meta = json.loads((run_dir / "run.json").read_text())
    tasks_dir = Path(meta["tasks_dir"])
    recs = {r["id"]: r for r in load_tasks(tasks_dir, qualified_only=False)}
    kinds = {p.parent.parent.name for p in run_dir.glob("*/*/*/attempt-*")}  # <arm>/<kind>/<id>/attempt-N
    stale = sorted({r["id"] for r in recs.values() for kind in kinds
                    if INPUT_KIND.get(kind, kind) in r.get("tasks", {})
                    and r.get("task_spec", 1) < MIN_TASK_SPEC.get(kind, TASK_SPEC)})
    if stale:
        raise ValueError(f"{len(stale)} tasks were prepared with an older task spec (e.g. {stale[0]}); "
                         "re-prepare and re-run instead")
    paths = sorted(run_dir.glob("*/*/*/attempt-*/attempt.json"))
    stamp = datetime.now(timezone.utc).isoformat()
    # Only the built-in reference adapter may reproduce the human layout (it may carry a --label).
    reference = meta.get("reference_adapter", meta["adapter"].get("name", "").startswith("reference"))
    per_arm = meta.get("reference_adapters") or {}

    def one(path):
        row = json.loads(path.read_text())
        adir = path.parent
        if row["status"] not in ("ok", "score_error") or not board_path(adir / "output").exists():
            return row
        if row.get("score_version") == SCORE_VERSION and row["status"] == "ok" and not force:
            return row
        old = row.get("score_version")
        row["status"] = "ok"
        row.pop("error", None)
        row.pop("scoring_usage", None)
        tools.usage_take()
        _score(row, tasks_dir / row["id"], recs[row["id"]], row["kind"], adir,
               allow_copy=per_arm.get(row["adapter"], reference), rescore_probe=True)
        u = tools.usage_take()
        row.setdefault("scoring_usage", u)
        row["score_version"] = SCORE_VERSION
        row.setdefault("rescored", []).append(dict(at=stamp, from_version=old))
        path.write_text(json.dumps(row, indent=1))
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        for i, row in enumerate(ex.map(one, paths), 1):
            rows.append(row)
            s = row.get("score") or {}
            progress(f"[{i}/{len(paths)}] {row['id']} {row['kind']} #{row['attempt']}: {row['status']}"
                     f" clean={s.get('clean', s.get('legal'))} valid={s.get('valid')}")
    rows.sort(key=lambda r: (r["kind"], r["id"], r["attempt"]))
    with open(run_dir / "results.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    meta.setdefault("rescored", []).append(dict(at=stamp, score_version=SCORE_VERSION, git=_git_rev(),
                                                attempts=len(rows)))
    (run_dir / "run.json").write_text(json.dumps(meta, indent=1))
    return run_dir


def _probe(task_dir, rec, probe, placed_dir, placed_stats, placed_unconnected, attempt, timeout, adir):
    """Route a placement with a fixed router (Cypress-style routability)."""
    pdir = adir / "probe"
    pin = pdir / "input"
    copy_board(placed_dir, pin)
    install_rules(task_dir / "reference", pin)  # the probe routes under the board's own rules
    t0 = time.monotonic()
    out = {"router": probe.name}
    tools.usage_take()  # the placement's own scoring was taken just before
    try:
        res = probe.run("route", pin, pdir, attempt, timeout)
    except Exception as e:
        out.update(status="adapter_error", error=f"{type(e).__name__}: {e}", method_usage=tools.usage_take())
        return out
    out["runtime_s"] = round(time.monotonic() - t0, 3)
    out["method_usage"] = tools.usage_take()
    out["adapter_meta"] = res.meta
    (pdir / "probe.log").write_text(res.log or "")
    _keep_artifacts(res.meta, pdir / "artifacts")
    if not res.output:
        out["status"] = "no_output"
        return out
    out["status"] = "ok"
    t1 = time.monotonic()
    out["score"] = score_routing(res.output, board_path(pin), placed_stats, placed_unconnected,
                                 rec["reference"]["stats"], task_dir / "reference", pdir / "score")
    out["scoring_s"] = round(time.monotonic() - t1, 3)
    out["scoring_usage"] = tools.usage_take()
    return out


def work_list(recs, arms, kinds, k):
    """Attempts in execution order: board by board, and within a board every arm back to back
    in an order shuffled per board (seeded), so all arms see the same host conditions and none
    systematically runs first. Largest boards (by pads) start first, so the run does not end
    waiting on a few slow stragglers. arms: [(adapter, probe)]."""
    work = []
    recs = sorted(recs, key=lambda r: -((r.get("reference") or {}).get("stats") or {}).get("pads", 0))
    for rec in recs:
        for a in range(k):
            order = list(arms)
            random.Random(f"{rec['id']}:{a}").shuffle(order)
            for adapter, probe in order:
                for kind in kinds:
                    if kind in adapter.kinds and INPUT_KIND[kind] in rec["tasks"]:
                        work.append((rec, kind, a, adapter, probe))
    return work


def run(tasks_dir, results_dir, adapter=None, kinds=("route",), k=1, timeout=600, jobs=1, probe=None,
        only=None, splits=None, qualified_only=True, name=None, keep_work=False, progress=print,
        arms=None):
    """Run one adapter (with an optional placement probe), or several interleaved arms
    [(adapter, probe)] in one run; results go to <run>/<adapter name>/<kind>/<id>/attempt-N."""
    arms = list(arms) if arms else [(adapter, probe)]
    names = [ad.name for ad, _ in arms]
    if len(set(names)) != len(names):
        raise ValueError(f"arm names must be unique (use labels): {names}")
    tasks_dir, results_dir = Path(tasks_dir), Path(results_dir)
    recs = load_tasks(tasks_dir, only=only, qualified_only=qualified_only, splits=splits)
    stale = [r["id"] for r in recs for kind in kinds
             if INPUT_KIND[kind] in r["tasks"] and r.get("task_spec", 1) < MIN_TASK_SPEC.get(kind, TASK_SPEC)]
    if stale:
        raise ValueError(f"{len(stale)} tasks were prepared with an older task spec "
                         f"(e.g. {stale[0]}); re-run `kaebench prepare --force`")
    for ad, pr in arms:
        for method in (ad, pr):  # a command probe is as untrusted as a command method
            if method is not None and hasattr(method, "hide"):
                method.hide(tasks_dir, results_dir)
    name = name or f"{'+'.join(names)}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = results_dir / name
    run_dir.mkdir(parents=True, exist_ok=True)
    first_ad, first_probe = arms[0]
    meta = dict(name=name, harness=__version__, git=_git_rev(), host=platform.node(),
                platform=platform.platform(), started=datetime.now(timezone.utc).isoformat(),
                tools=tools.versions(), adapter=first_ad.describe(),
                probe=first_probe.describe() if first_probe else None,
                arms=[dict(adapter=ad.describe(), probe=pr.describe() if pr else None,
                           reference_adapter=ad.needs_reference) for ad, pr in arms],
                interleaved=len(arms) > 1, kinds=list(kinds), k=k, timeout=timeout,
                tasks_dir=str(tasks_dir), boards=len(recs), qualified_only=qualified_only,
                score_version=SCORE_VERSION, task_spec=TASK_SPEC,
                reference_adapter=first_ad.needs_reference,
                reference_adapters={ad.name: ad.needs_reference for ad, _ in arms})
    meta_path = run_dir / "run.json"
    if meta_path.exists():
        prev = json.loads(meta_path.read_text())
        meta["started"] = prev.get("started", meta["started"])
        meta["resumed"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=1))
    work = work_list(recs, arms, kinds, k)
    lock = threading.Lock()
    rows = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        # the pool starts work in submission order, so the interleaving holds in time
        futs = {ex.submit(_attempt, tasks_dir / rec["id"], rec, ad, kind, a, timeout,
                          run_dir / ad.name / kind / rec["id"] / f"attempt-{a}", pr,
                          keep_work): (rec["id"], kind, a) for rec, kind, a, ad, pr in work}
        for i, f in enumerate(as_completed(futs), 1):
            row = f.result()
            with lock:
                rows.append(row)
            s = row.get("score") or {}
            progress(f"[{i}/{len(futs)}] {row['adapter']} {row['id']} {row['kind']} #{row['attempt']}: "
                     f"{row['status']} clean={s.get('clean', s.get('legal'))} unconn={s.get('unconnected')}"
                     f" err={s.get('errors')} t={row['runtime_s']}s")
    rows.sort(key=lambda r: (r["adapter"], r["kind"], r["id"], r["attempt"]))
    with open(run_dir / "results.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    meta["finished"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=1))
    return run_dir
