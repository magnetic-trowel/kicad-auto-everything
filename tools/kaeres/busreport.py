#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Report-only bus scorecard over stored kaeres runs (see kae.bus.scorecard).

Measures finished boards; never runs a router and never changes a score. Scorecards live beside each run in
`runs/<run>/bus/<evaluator>.json.gz`, not in `evals/`, so no DRC or physics reader sees them. The evaluator id is a hash
of this file and kae/src/kae/bus at the commit named; a new scorer version gives new records beside the old ones.

  kaeres bus submit NAME --boards @FILE --method NAME_OR_ID [...] [--kae REF] [--chunk N]
  kaeres bus report NAME                                       # BUS.md and bus.csv under ~/kae-baselines/bus/NAME/

`kaeres exp report` adds the same tables to REPORT.md when an experiment's runs have scorecards.
"""
import argparse
import csv
import gzip
import json
import os
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kaeres as K  # noqa: E402

BUS_ROOT = K.STORE / "bus"
BUDGET_KINDS = ("ddr_byte", "sd_emmc", "eth_mii", "pair")      # classes with a timing budget in kae.bus.limits


def evaluator(commit):
    """The id of the scorecard at a repo commit: the content of kae/src/kae/bus and this script."""
    code = K.tree_ids(commit, ["kae/src/kae/bus", "tools/kaeres/busreport.py"])
    eid = K.ident(dict(type="kae-bus-scorecard", code=code))
    p = K.STORE / "evaluators" / f"{eid}.json"
    if not p.exists():
        K.write_json(p, dict(schema=K.SCHEMA, id=eid, name="bus-scorecard", created=K.now(), recipe=dict(code=code),
                             commits=dict(kae=dict(commit=commit, link=K.github_link("https://github.com/magnetic-trowel/kicad-auto-everything", commit)))))
    return eid


def _result_path(run_dir, eid):
    return Path(run_dir) / "bus" / f"{eid}.json.gz"


def _drc_of(run_dir):
    """The run's kicad-cli DRC report (newest evaluator), or None when the run keeps none."""
    fs = sorted((Path(run_dir) / "evals").glob("*.drc.json.gz"), key=lambda f: f.stat().st_mtime)
    if not fs:
        return None
    try:
        with gzip.open(fs[-1], "rt") as f:
            return json.load(f)
    except (OSError, ValueError, EOFError):
        return None


def cmd_job(a):
    """One chunk of boards: measure every listed run that lacks this evaluator's scorecard."""
    import resource
    import shutil
    import tempfile
    from kae.board.kicad_file import load
    from kae.bus.scorecard import board_scorecard
    resource.setrlimit(resource.RLIMIT_AS, (24 * 2 ** 30, 24 * 2 ** 30))
    tmpd = Path(tempfile.mkdtemp(prefix="busrep", dir=os.environ.get("KAEQ_SCRATCH") or "/var/tmp"))
    rc = 0
    for line in Path(a.tasks).read_text().splitlines():
        bid, run = line.split()
        rd = K.board_dir(bid) / "runs" / run
        out = _result_path(rd, a.evaluator)
        if out.exists():
            continue
        pcb = rd / "output.kicad_pcb.gz"
        rec = dict(schema=K.SCHEMA, evaluator=a.evaluator, board=bid, run=run)
        if not pcb.exists():
            continue
        try:
            with gzip.open(pcb, "rb") as f, open(tmpd / "b.kicad_pcb", "wb") as g:
                shutil.copyfileobj(f, g)
            board = load(str(tmpd / "b.kicad_pcb"), rules=False)
            rec.update(board_scorecard(board, drc=_drc_of(rd), decompose=True))
        except Exception as e:     # one board's failure must not lose the chunk
            rec["error"] = repr(e)[:400]
            rc = 0
        out.parent.mkdir(exist_ok=True)
        tmp = out.with_name(out.name + f".tmp{os.getpid()}")
        with gzip.open(tmp, "wt") as f:
            json.dump(rec, f, separators=(",", ":"))
        os.replace(tmp, out)
    shutil.rmtree(tmpd, ignore_errors=True)
    return rc


def _boards(spec):
    if spec.startswith("@"):
        return Path(spec[1:]).read_text().split()
    return [x for x in spec.split(",") if x]


def cmd_submit(a):
    commit = K.git(str(HERE), "rev-parse", a.kae)
    eid = evaluator(commit)
    kae_d, venv = K.ensure_harness(commit, kae=True, venv=True)
    methods = {K.find_method(m)["id"]: K.find_method(m) for m in a.method}
    boards = _boards(a.boards)
    tasks = []
    for bid in boards:
        for d, r in K.board_runs(bid):
            if r["method_id"] in methods and r.get("status") == "ok" and (d / "output.kicad_pcb.gz").exists() and not _result_path(d, eid).exists():
                tasks.append((bid, d.name))
    root = BUS_ROOT / a.name
    root.mkdir(parents=True, exist_ok=True)
    K.write_json(root / "meta.json", dict(schema=K.SCHEMA, name=a.name, evaluator=eid, kae=commit, boards=len(boards), created=K.now(),
                                          methods=[dict(id=m["id"], name=m["name"]) for m in methods.values()]))
    (root / "boards.txt").write_text("\n".join(boards) + "\n")
    jobs = []
    td = root / "tasks"
    td.mkdir(exist_ok=True)
    for i in range(0, len(tasks), a.chunk):
        f = td / f"{i // a.chunk:05d}.txt"
        f.write_text("".join(f"{b} {r}\n" for b, r in tasks[i:i + a.chunk]))
        jobs.append(dict(cmd=f"{venv / 'bin' / 'python'} {kae_d / 'tools' / 'kaeres' / 'busreport.py'} job --evaluator {eid} --tasks {f}",
                         name=f"bus-{a.name}-{i // a.chunk}", cpus=1, mem=a.mem, timeout="3h"))
    print(f"{len(tasks)} runs on {len(boards)} boards to measure, {len(jobs)} jobs, evaluator {eid} at {commit[:7]}")
    if a.dry_run or not jobs:
        return 0
    jf = root / "jobs.jsonl"
    jf.write_text("".join(json.dumps(j) + "\n" for j in jobs))
    env = dict(os.environ, KAEQ_OWNER=f"bus-{a.name}")
    subprocess.run(["kaeq", "submit", "--jobs", str(jf), "--tag", f"bus-{a.name}"], check=True, env=env)
    return 0


def _load(run_dir, eid):
    p = _result_path(run_dir, eid) if eid else None
    if p is None:
        fs = sorted((Path(run_dir) / "bus").glob("*.json.gz"), key=lambda f: f.stat().st_mtime) if (Path(run_dir) / "bus").is_dir() else []
        p = fs[-1] if fs else None
    if p is None or not p.exists():
        return None
    try:
        with gzip.open(p, "rt") as f:
            return json.load(f)
    except (OSError, ValueError, EOFError):
        return None


def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _f(x, nd=2):
    return "—" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def _bkey(b):
    return b.get("a"), b.get("b"), tuple(sorted(b.get("names") or []))


def aggregate(runs, eid=None):
    """runs: [(method, board, run dir)] -> per method per class, the columns for the tables."""
    per = defaultdict(lambda: defaultdict(list))        # method -> kind -> [bus records]
    n_runs = Counter()
    errors = Counter()
    for method, board, rd in runs:
        sc = _load(rd, eid)
        if sc is None:
            continue
        n_runs[method] += 1
        if "error" in sc:
            errors[method] += 1
            continue
        for b in sc.get("buses", []) + sc.get("pairs", []):
            per[method][b["kind"]].append(dict(b, _board=board, _src=sc.get("opens_src")))
    return per, n_runs, errors


CSV_FIELDS = ["method", "kind", "buses", "boards", "lanes", "lanes_open", "lanes_open_pct", "buses_complete_pct", "open_items",
              "measured_buses", "vias_lane_med", "via_equal_pct", "via_span_mismatch_med", "skew_mm_med", "skew_ps_med", "layer_agreement_med",
              "coupled_3w_med", "skew_ok_keyed", "skew_n_keyed", "skew_ok_assumed", "skew_n_assumed", "via_ok_pct"]


def _class_row(method, kind, bs):
    meas = [b for b in bs if b.get("measured", 0) >= 2 and b.get("len_mean") is not None]
    keyed = [b for b in meas if "skew_ok" in b and b["limit"].get("keyed")]
    assumed = [b for b in meas if "skew_ok" in b and not b["limit"].get("keyed")]
    viaok = [b["via_ok"] for b in meas if "via_ok" in b]
    lanes = sum(b["width"] for b in bs)
    op = sum(b.get("lanes_open", 0) for b in bs)
    return dict(method=method, kind=kind, buses=len(bs), boards=len({b["_board"] for b in bs}), lanes=lanes, lanes_open=op,
                lanes_open_pct=round(100 * op / lanes, 1) if lanes else None,
                buses_complete_pct=round(100 * sum(1 for b in bs if b.get("complete")) / len(bs), 1), open_items=sum(b.get("open_items", 0) for b in bs),
                measured_buses=len(meas), vias_lane_med=_med([b["vias_lane"] for b in meas]),
                via_equal_pct=round(100 * sum(b["via_equal"] for b in meas) / len(meas), 1) if meas else None,
                via_span_mismatch_med=_med([b.get("via_span_mismatch") for b in meas]),
                skew_mm_med=_med([b["skew_mm"] for b in meas if b.get("multi_lanes", 0) == 0]),
                skew_ps_med=_med([b.get("skew_ps") for b in meas if b.get("multi_lanes", 0) == 0]),
                layer_agreement_med=_med([b["layer_agreement"] for b in meas]), coupled_3w_med=_med([b.get("coupled_3w") for b in meas]),
                skew_ok_keyed=sum(b["skew_ok"] for b in keyed), skew_n_keyed=len(keyed), skew_ok_assumed=sum(b["skew_ok"] for b in assumed),
                skew_n_assumed=len(assumed), via_ok_pct=round(100 * sum(viaok) / len(viaok), 1) if viaok else None)


def _complete_in_both(a, b):
    """Buses of two methods' records, on the same board, complete in both: [(bus in a, bus in b)]."""
    idx = {(x["_board"], _bkey(x)): x for x in b if x.get("complete") and x.get("len_mean") is not None}
    return [(x, idx[(x["_board"], _bkey(x))]) for x in a
            if x.get("complete") and x.get("len_mean") is not None and (x["_board"], _bkey(x)) in idx]


def _decomp_table(records):
    """A2: pooled shares of within-bus lane-length variance by term, and each term's R^2 alone; one row."""
    # records have skew_decomp with [Sxy, Sxx, range]
    sy = sum(r["skew_decomp"]["mm_yy"] for r in records)
    terms = {}
    for t in ("chord", "fan", "meander", "turn", "other"):
        sxy = sum(r["skew_decomp"]["mm"][t][0] for r in records)
        sxx = sum(r["skew_decomp"]["mm"][t][1] for r in records)
        r2 = (sxy * sxy / (sxx * sy)) if sxx > 0 and sy > 0 else 0.0
        terms[t] = (sxy / sy if sy else 0.0, r2, _med([r["skew_decomp"]["mm"][t][2] for r in records]))
    sy2 = sum(r["skew_decomp"]["ps_yy"] for r in records)
    ps = {}
    for t in ("length", "layer", "via"):
        sxy = sum(r["skew_decomp"]["ps"][t][0] for r in records)
        sxx = sum(r["skew_decomp"]["ps"][t][1] for r in records)
        r2 = (sxy * sxy / (sxx * sy2)) if sxx > 0 and sy2 > 0 else 0.0
        ps[t] = (sxy / sy2 if sy2 else 0.0, r2, _med([r["skew_decomp"]["ps"][t][2] for r in records]))
    return terms, ps


def tables(per, n_runs, errors, title="Bus scorecard"):
    """Markdown lines for one set of methods. Numbers are descriptions: no score uses them."""
    out = [f"## {title}", "", "Report-only (kae.bus.scorecard): none of this enters any score. Open counts: `kicad-cli` DRC "
           "`unconnected_items` per net, or the copper graph when the DRC list is capped or missing (`opens_src`). Coupled share is "
           "shape only: it has no target and must not be rewarded. Skew budgets are keyed to the controller or interface where "
           "known; `assumed` budgets are class defaults (see kae.bus.limits). Compare methods only on buses complete in both.", ""]
    methods = list(per)
    kinds = sorted({k for m in per.values() for k in m}, key=lambda k: -sum(len(per[m].get(k, [])) for m in methods))
    out += ["### Per class", "",
            "| method | class | buses | lanes | lanes open % | complete % | vias/lane | via equal % | skew mm | layer agreement | coupled 3W | skew OK keyed | skew OK assumed | via OK % |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for kind in kinds:
        for m in methods:
            bs = per[m].get(kind)
            if not bs:
                continue
            r = _class_row(m, kind, bs)
            out.append(f"| {m} | {kind} | {r['buses']} | {r['lanes']} | {_f(r['lanes_open_pct'],1)} | {_f(r['buses_complete_pct'],1)} | {_f(r['vias_lane_med'])} | "
                       f"{_f(r['via_equal_pct'],1)} | {_f(r['skew_mm_med'])} | {_f(r['layer_agreement_med'])} | {_f(r['coupled_3w_med'])} | "
                       f"{r['skew_ok_keyed']}/{r['skew_n_keyed']} | {r['skew_ok_assumed']}/{r['skew_n_assumed']} | {_f(r['via_ok_pct'],1)} |")
    if "human" in per and len(methods) > 1:
        out += ["", "### Against the human layout, on buses complete in both", "",
                "Medians over buses connected in both. First number: the human layout.", "",
                "| class | method | n | vias/lane | via equal % | skew mm | layer agreement | coupled 3W |", "|---|---|---|---|---|---|---|---|"]
        for kind in kinds:
            for m in methods:
                if m == "human":
                    continue
                pairs = _complete_in_both(per["human"].get(kind, []), per[m].get(kind, []))
                pairs = [(h, r) for h, r in pairs if h.get("multi_lanes", 0) == 0]
                if len(pairs) < 3:
                    continue
                h, r = zip(*pairs)
                f2 = lambda vs: _f(_med(vs))
                out.append(f"| {kind} | {m} | {len(pairs)} | {f2([x['vias_lane'] for x in h])} / {f2([x['vias_lane'] for x in r])} | "
                           f"{_f(100*sum(x['via_equal'] for x in h)/len(h),0)} / {_f(100*sum(x['via_equal'] for x in r)/len(r),0)} | "
                           f"{f2([x['skew_mm'] for x in h])} / {f2([x['skew_mm'] for x in r])} | "
                           f"{f2([x['layer_agreement'] for x in h])} / {f2([x['layer_agreement'] for x in r])} | "
                           f"{f2([x.get('coupled_3w') for x in h])} / {f2([x.get('coupled_3w') for x in r])} |")
    # A2
    out += ["", "### Skew decomposition (A2, complete point-to-point buses of at least 3 lanes)", "",
            "Each lane's length minus its bus mean, split into additive terms: `chord` straight-line pad-to-pad difference (placement "
            "and pin positions), `fan` length of the fan-in stretches beyond their straight line, `meander` serpentine excess, `turn` "
            "trunk net turning d·Σf (a parallel offset around bends), `other` the rest. Delay terms: copper length, layer speed mix, "
            "via flight. Shares are pooled covariance shares and sum to 1 per row; R² is each term alone.", "",
            "| method | class | buses | chord | fan | meander | turn | other | R² chord | R² fan | R² meander | R² turn | R² other | ps: length | layer | via |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for kind in kinds:
        for m in methods:
            recs = [b for b in per[m].get(kind, []) if b.get("skew_decomp")]
            if len(recs) < 3:
                continue
            t, ps = _decomp_table(recs)
            out.append(f"| {m} | {kind} | {len(recs)} | " + " | ".join(_f(t[k][0]) for k in ("chord", "fan", "meander", "turn", "other")) + " | "
                       + " | ".join(_f(t[k][1]) for k in ("chord", "fan", "meander", "turn", "other")) + " | "
                       + " | ".join(_f(ps[k][0]) for k in ("length", "layer", "via")) + " |")
    if errors:
        out += ["", f"Scorecards with errors: {dict(errors)}."]
    return out


def write_csv(per, path):
    rows = [_class_row(m, k, per[m][k]) for m in per for k in per[m]]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def cmd_report(a):
    root = BUS_ROOT / a.name
    meta = K.read_json(root / "meta.json")
    boards = (root / "boards.txt").read_text().split()
    methods = {m["id"]: m["name"] for m in meta["methods"]}
    runs = []
    for bid in boards:
        for d, r in K.board_runs(bid):
            if r["method_id"] in methods:
                runs.append((methods[r["method_id"]], bid, d))
    per, n_runs, errors = aggregate(runs, meta["evaluator"])
    write_csv(per, root / "bus.csv")
    (root / "BUS.md").write_text("\n".join([f"# Bus report {a.name}", "", f"Boards: {len(boards)}; runs with scorecards: {dict(n_runs)}; "
                                            f"evaluator {meta['evaluator']}.", ""] + tables(per, n_runs, errors)) + "\n")
    print(f"wrote {root / 'BUS.md'}, bus.csv")
    return 0


def section_for_experiment(rows, name):
    """Lines for `kaeres exp report`, when the experiment's runs have scorecards: the same tables. Empty otherwise."""
    runs = [(r["method"], r["board"], K.board_dir(r["board"]) / "runs" / r["run"]) for r in rows if r.get("status") == "ok"]
    per, n_runs, errors = aggregate(runs)
    if not n_runs:
        return []
    return tables(per, n_runs, errors, title=f"Bus scorecard ({name}, report-only)") + [""]


def main():
    ap = argparse.ArgumentParser(prog="kaeres bus", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("job", help="one chunk of runs (what each queued job runs)")
    s.add_argument("--evaluator", required=True), s.add_argument("--tasks", required=True)
    s.set_defaults(f=cmd_job)
    s = sub.add_parser("submit", help="queue the scorecard for stored runs")
    s.add_argument("name"), s.add_argument("--boards", required=True, help="ids, or @FILE"), s.add_argument("--method", action="append", required=True)
    s.add_argument("--kae", default="HEAD", help="revision whose kae.bus and tools/kaeres/busreport.py measure (must be in the store's git)")
    s.add_argument("--chunk", type=int, default=8), s.add_argument("--mem", default="1500M", help="kaeq --mem per job (about 1 GB per large board)")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(f=cmd_submit)
    s = sub.add_parser("report", help="aggregate finished scorecards")
    s.add_argument("name")
    s.set_defaults(f=cmd_report)
    a = ap.parse_args()
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
