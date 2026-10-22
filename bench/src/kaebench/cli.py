# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kaebench command line.

    kaebench doctor
    kaebench fetch   -m MANIFEST
    kaebench prepare -m MANIFEST
    kaebench run     --adapter freerouting -k 5
    kaebench report  RUN_DIR [RUN_DIR ...]
"""
import argparse
import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import __version__, adapters, fetch, manifest, prepare, report, runner, tools


def _split(s):
    """Comma-separated list, or @FILE with one entry per line (# comments allowed)."""
    if not s:
        return None
    if s.startswith("@"):
        lines = Path(s[1:]).read_text().splitlines()
        return [ln.split("#")[0].strip() for ln in lines if ln.split("#")[0].strip()]
    return [x for x in s.split(",") if x]


def _dirs(a):
    w = Path(a.workdir)
    return w / "cache", w / "tasks", w / "results"


def cmd_doctor(a):
    ok = True
    for name, fn in (("kicad-cli", tools.kicad_cli), ("kicad python (pcbnew)", tools.kicad_python),
                     ("freerouting", tools.freerouting_cmd)):
        try:
            print(f"ok   {name}: {fn()}")
        except tools.ToolError as e:
            ok = False
            print(f"FAIL {name}: {e}")
    print(json.dumps(tools.versions(), indent=1))
    return 0 if ok else 1


def _entries(a):
    es = manifest.load(a.manifest, only=_split(a.only), tiers=_split(a.tiers), tags=_split(a.tags))
    # smallest boards first, so useful results arrive early on long runs (and --limit picks small ones)
    es.sort(key=lambda e: e.get("footprints") or float("inf"))
    return es[:a.limit] if a.limit else es


def _parallel(items, fn, jobs, label):
    failures = 0
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        futs = {ex.submit(fn, it): it for it in items}
        for i, f in enumerate(as_completed(futs), 1):
            it = futs[f]
            try:
                msg = f.result()
                print(f"[{i}/{len(futs)}] {it['id']}: {msg}")
            except Exception as e:
                failures += 1
                print(f"[{i}/{len(futs)}] {it['id']}: FAILED {type(e).__name__}: {e}", file=sys.stderr)
                if getattr(fn, "verbose", False):
                    traceback.print_exc()
    print(f"{label}: {len(items) - failures} ok, {failures} failed")
    return 0 if failures == 0 else 2


def cmd_fetch(a):
    cache, _, _ = _dirs(a)
    return _parallel(_entries(a), lambda e: fetch.fetch(e, cache, force=a.force)["pcb_sha256"][:12],
                     a.jobs, "fetch")


def cmd_prepare(a):
    cache, tasks, _ = _dirs(a)
    kinds = _split(a.kinds) or list(prepare.TASK_KINDS)

    def one(e):
        f = fetch.fetch(e, cache)
        r = prepare.prepare_board(e, f, tasks, kinds=kinds, keep_locked=a.keep_locked, force=a.force)
        rd = r["reference"]["drc"]
        return (f"split={r['split']} pads={r['reference']['stats']['pads']} qualified={r['qualified']}"
                f" (unconn={rd['unconnected']} err={rd['errors']})")
    return _parallel(_entries(a), one, a.jobs, "prepare")


ROW_FIELDS = ("repo", "commit", "pcb_path", "license", "license_tier", "tags")


def _local_boards(root, pattern, only):
    """Board folders under root (e.g. PCBWorld's exacad_sorted): one board per subfolder.

    A folder's row.json (the local corpus writes one per board) supplies the manifest
    fields: repo, commit, licence, licence tier and tags.
    """
    root = Path(root)
    items = []
    dirs = [root / name for name in sorted(set(only))] if only else sorted(root.iterdir())
    for d in dirs:
        if not d.is_dir():
            continue
        pcbs = sorted(d.glob(pattern))
        if not pcbs:
            continue
        pcb = pcbs[0]
        pros = [pcb.with_suffix(".kicad_pro")] + sorted(d.glob("*.kicad_pro"))
        pro = next((p for p in pros if p.exists()), None)
        dru = pcb.with_suffix(".kicad_dru")
        fetched = {"kicad_pcb": str(pcb), "pcb_sha256": fetch.sha256(pcb)}
        if pro:
            fetched["kicad_pro"] = str(pro)
        if dru.exists():
            fetched["kicad_dru"] = str(dru)
        entry = dict(id=d.name, repo=f"local:{root}", commit=None, pcb_path=str(pcb.relative_to(root)),
                     license="unknown (local)", license_tier=None, tags=[])
        row = d / "row.json"
        if row.exists():
            meta = json.loads(row.read_text())
            entry.update({k: meta[k] for k in ROW_FIELDS if meta.get(k) is not None})
        items.append((entry, fetched))
    missing = sorted(set(only or []) - {e["id"] for e, _ in items})
    if missing:
        print(f"warning: {len(missing)} requested boards not found under {root}: {missing[:5]}...", file=sys.stderr)
    return items


def cmd_prepare_dir(a):
    _, tasks, _ = _dirs(a)
    kinds = _split(a.kinds) or list(prepare.TASK_KINDS)
    items = _local_boards(a.dir, a.board_glob, _split(a.only))
    by_id = {e["id"]: f for e, f in items}

    def one(e):
        r = prepare.prepare_board(e, by_id[e["id"]], tasks, kinds=kinds, keep_locked=a.keep_locked,
                                  force=a.force)
        rd = r["reference"]["drc"]
        return (f"split={r['split']} pads={r['reference']['stats']['pads']} qualified={r['qualified']}"
                f" (unconn={rd['unconnected']} err={rd['errors']})")
    return _parallel([e for e, _ in items], one, a.jobs, "prepare-dir")


def cmd_run(a):
    _, tasks, results = _dirs(a)
    sandbox = adapters.Sandbox(enabled=not a.no_sandbox, network=a.sandbox_net,
                               ro=[Path(x) for x in a.sandbox_ro or []])
    ad = adapters.make(a.adapter, command=a.command, passes=a.passes, sandbox=sandbox)
    probe = adapters.make(a.probe) if a.probe else None
    run_dir = runner.run(tasks, results, ad, kinds=_split(a.kinds) or ["route"], k=a.k,
                         timeout=a.timeout, jobs=a.jobs, probe=probe, only=_split(a.only),
                         splits=_split(a.splits), qualified_only=not a.all, name=a.name,
                         keep_work=a.keep_work)
    summary, _ = report.report([run_dir])
    md = report.to_markdown(summary)
    (run_dir / "report.md").write_text(md + "\n")
    print(md)
    print(f"\nresults: {run_dir}")
    return 0


def cmd_tasks(a):
    """Qualification yield of prepared tasks by split, licence tier and tag."""
    _, tasks, _ = _dirs(a)
    recs = prepare.load_tasks(tasks, qualified_only=False)
    if not recs:
        print(f"no tasks under {tasks}")
        return 1
    def table(title, keyfn):
        groups = {}
        for r in recs:
            for k in keyfn(r):
                g = groups.setdefault(k, [0, 0])
                g[0] += 1
                g[1] += r["qualified"]
        print(f"\n| {title} | boards | qualified |\n|---|---|---|")
        for k, (n, q) in sorted(groups.items(), key=lambda kv: (-kv[1][0], str(kv[0]))):
            print(f"| {k} | {n} | {q} |")
    table("split", lambda r: [r["split"]])
    def why(r):
        if r["qualified"]:
            return []
        if not r.get("human_clean", True):
            return ["human layout not DRC-clean"]
        return [f"round trip fails: {k}" for k, v in (r.get("roundtrip") or {}).items() if not v["ok"]]
    if any(why(r) for r in recs):
        table("not qualified because", why)
    table("license tier", lambda r: [r.get("license_tier")])
    table("tag", lambda r: r.get("tags") or ["(none)"])
    if a.write_suite:
        ids = sorted(r["id"] for r in recs if r["qualified"])
        Path(a.write_suite).write_text("\n".join(ids) + "\n")
        print(f"\nwrote {len(ids)} qualified ids to {a.write_suite}")
    return 0


def cmd_report(a):
    summary, rows = report.report(a.run_dirs)
    md = report.to_markdown(summary)
    print(md)
    if a.out:
        Path(a.out).write_text(md + "\n")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="kaebench", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--workdir", default="kae-work", help="cache/tasks/results root (default ./kae-work)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check KiCad, pcbnew and Freerouting").set_defaults(fn=cmd_doctor)

    def board_filters(sp):
        sp.add_argument("-m", "--manifest", required=True)
        sp.add_argument("--only", help="comma-separated board ids, or @FILE with one id per line")
        sp.add_argument("--tiers", help="license tiers, e.g. permissive,weak-copyleft")
        sp.add_argument("--tags", help="keep boards with any of these tags")
        sp.add_argument("--limit", type=int)
        sp.add_argument("-j", "--jobs", type=int, default=4)
        sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("fetch", help="download boards at their pinned commits")
    board_filters(sp)
    sp.set_defaults(fn=cmd_fetch)

    sp = sub.add_parser("prepare", help="convert, qualify and build route/place tasks")
    board_filters(sp)
    sp.add_argument("--kinds", default="route,place")
    sp.add_argument("--keep-locked", action="store_true",
                    help="route tasks keep locked copper (place tasks always keep locked footprints)")
    sp.set_defaults(fn=cmd_prepare)

    sp = sub.add_parser("prepare-dir", help="build tasks from local board folders (e.g. PCBWorld output)")
    sp.add_argument("--dir", required=True, help="directory with one board per subfolder")
    sp.add_argument("--board-glob", default="*.kicad_pcb",
                    help="board file inside each folder, e.g. processed_v9_guide_v3.kicad_pcb")
    sp.add_argument("--only", help="comma-separated folder names, or @FILE")
    sp.add_argument("--kinds", default="route,place")
    sp.add_argument("--keep-locked", action="store_true")
    sp.add_argument("-j", "--jobs", type=int, default=4)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=cmd_prepare_dir)

    sp = sub.add_parser("run", help="run an adapter on prepared tasks and score it")
    sp.add_argument("--adapter", required=True, help="reference | noop | freerouting | <name> with --command")
    sp.add_argument("--command", help="external tool template: {input} {output} {workdir} {kind} {attempt} {timeout}")
    sp.add_argument("--kinds", default="route")
    sp.add_argument("-k", type=int, default=1, help="attempts per board (best-of-k)")
    sp.add_argument("--timeout", type=float, default=600, help="seconds per attempt")
    sp.add_argument("-j", "--jobs", type=int, default=1)
    sp.add_argument("--probe", help="router used to score placements, e.g. freerouting")
    sp.add_argument("--passes", type=int, help="freerouting: fixed -mp instead of the per-attempt schedule")
    sp.add_argument("--only")
    sp.add_argument("--splits", help="e.g. A,B")
    sp.add_argument("--all", action="store_true", help="include boards whose human layout is not clean")
    sp.add_argument("--name", help="run name (reuse to resume)")
    sp.add_argument("--keep-work", action="store_true")
    sp.add_argument("--no-sandbox", action="store_true",
                    help="run --command methods unsandboxed (they can then read reference layouts; "
                         "results are marked unsandboxed)")
    sp.add_argument("--sandbox-net", action="store_true", help="give sandboxed methods network access")
    sp.add_argument("--sandbox-ro", action="append", metavar="PATH",
                    help="extra path a sandboxed method may read (repeatable)")
    sp.set_defaults(fn=cmd_run)

    sp = sub.add_parser("tasks", help="qualification yield of prepared tasks")
    sp.add_argument("--write-suite", help="write qualified board ids to this file")
    sp.set_defaults(fn=cmd_tasks)

    sp = sub.add_parser("report", help="summarize one or more runs")
    sp.add_argument("run_dirs", nargs="+")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_report)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
