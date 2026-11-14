# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Score kaeres runs on PCBWorld's D3 boards with PCBWorld's own evaluation chain (report-only).

For each method (a kaeres method id) this builds one PCBWorld "cell": a directory whose boards/ holds
<board_id>_<cell>_s00_r<RR>.kicad_pcb, one per attempt RR, plus <board_id>.kicad_pro (PCBWorld's rules),
in the file grammar PCBWorld's eval pipeline reads (eval/eval_utils.parse_cell_artifact). The copper of
each run's output board is copied onto PCBWorld's own unrouted KiCad 9 input board by transplant_v9.py,
because their KiCad 9.0.8 engine cannot open KiCad 10 files. Then it runs, from the PCBWorld checkout,

    python -m eval.pipeline --skip-rollout --output-dir CELL --boards-list LIST --stages eval,aggregate \
        --reward-config drc_dense_promoted --selection-method final_potential --check-angle 45

which are the paper's scoring settings (experiments/kdd/configs/paper_train_flags.sh). Nothing here
changes a kaebench score; it adds a second, independent scorer's view.

    python3 score_pcbworld.py --pcbworld PCBWORLD --python PCBWORLD_ENV/bin/python --corpus CORPUS \
        --exacad DATA/pcbench/exacad_sorted --out OUT --attempts 5 --cell kae-bridge=<method id> ...
    # --reference: also a cell of PCBWorld's own routed guide boards (their Reference row), and
    # --cell NAME=@guide: PCBWorld's guide boards pushed through the transplant (checks transplant_v9.py)
"""
import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEM = "processed_v9_guide_v3"


def rows_of(corpus):
    with open(corpus / "manifest.jsonl") as f:
        return [json.loads(l) for l in f if l.strip()]


def run_dir(store, bid, mid, attempt):
    runs = store / "boards" / bid / "runs"
    hits = sorted(runs.glob(f"*.{mid[:8]}.a{attempt}")) if runs.is_dir() else []
    return hits[0] if hits else None


def pipeline_env(a):
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{a.pcbworld / 'build_rl' / 'pcbnew' / 'python' / 'rl'}:{a.pcbworld}"
    env.setdefault("PCBWORLD_DATA_ROOT", str(a.exacad.parent.parent))
    env.pop("VIRTUAL_ENV", None)
    return env


def transplant(a, jobs, log):
    """Run transplant_v9.py over jobs in the PCBWorld interpreter with KiCad 9's pcbnew."""
    if not jobs:
        return []
    jf = log.with_suffix(".jobs.jsonl")
    jf.write_text("".join(json.dumps(j) + "\n" for j in jobs))
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    out = subprocess.run([str(a.python), "-I", str(HERE / "transplant_v9.py"), str(jf),
                          str(a.pcbworld / "build_rl" / "pcbnew")],
                         capture_output=True, text=True, env=env, cwd=str(log.parent))
    log.write_text(out.stdout + "\n--- stderr\n" + out.stderr)
    recs = [json.loads(l) for l in out.stdout.splitlines() if l.startswith("{")]
    if out.returncode != 0 or len(recs) != len(jobs):
        raise SystemExit(f"transplant failed (rc {out.returncode}, {len(recs)}/{len(jobs)} done): see {log}")
    for r in recs:  # SaveBoard may write the loaded board's project beside the copy: the shared one wins
        for ext in (".kicad_pro", ".kicad_prl"):
            Path(r["out"]).with_suffix(ext).unlink(missing_ok=True)
    return recs


def build_cell(a, rows, cell, mid=None, reference=False):
    d = a.out / cell
    b = d / "boards"
    if d.exists():
        shutil.rmtree(d)
    b.mkdir(parents=True)
    jobs, have = [], []
    for r in rows:
        src = a.exacad / r["pcbworld_folder"]
        bid = r["pcbworld_folder"]
        shutil.copy2(src / f"{STEM}.kicad_pro", b / f"{bid}.kicad_pro")
        if reference:
            shutil.copy2(src / f"{STEM}.kicad_pcb", b / f"{bid}_{cell}_s00_r00.kicad_pcb")
            have.append(dict(board=bid, attempt=0, run="pcbworld guide board"))
            continue
        for att in range(1 if mid == "@guide" else a.attempts):
            if mid == "@guide":  # transplant check: PCBWorld's own routed guide board through the transplant
                rd, out = src, src / f"{STEM}.kicad_pcb"
            else:
                rd = run_dir(a.store, r["id"], mid, att)
                out = rd / "output.kicad_pcb.gz" if rd else None
            if out is None or not out.exists():
                have.append(dict(board=bid, attempt=att, run=str(rd) if rd else None, missing=True))
                continue
            jobs.append(dict(routed=str(out), base=str(src / f"{STEM}_unrouted.kicad_pcb"),
                             out=str(b / f"{bid}_{cell}_s00_r{att:02d}.kicad_pcb")))
            have.append(dict(board=bid, attempt=att, run=str(rd)))
    recs = transplant(a, jobs, d / "transplant.log")
    (d / "sources.json").write_text(json.dumps(dict(cell=cell, method=mid, attempts=a.attempts, runs=have,
                                                    transplant=recs), indent=1))
    bad = [r for r in recs if r.get("error") or r.get("missing_nets") or r.get("skipped")]
    if bad:
        print(f"{cell}: {len(bad)} transplant(s) with errors or missing nets, e.g. {bad[0]}", file=sys.stderr)
    lst = d / "boards.list"
    lst.write_text("".join(f"{a.exacad / r['pcbworld_folder'] / (STEM + '.kicad_pcb')}\n" for r in rows))
    cmd = [str(a.python), "-m", "eval.pipeline", "--skip-rollout", "--output-dir", str(d), "--boards-list", str(lst),
           "--stages", "eval,aggregate", "--reward-config", "drc_dense_promoted",
           "--selection-method", "final_potential", "--check-angle", "45",
           "--rollout-mode", "parallel", "--n-envs", str(a.workers)]
    with open(d / "pipeline.log", "w") as f:
        rc = subprocess.run(cmd, cwd=str(a.pcbworld), env=pipeline_env(a), stdout=f, stderr=subprocess.STDOUT).returncode
    print(f"{cell}: {len(jobs) or len(have)} boards scored, pipeline rc {rc} ({d / 'pipeline.log'})")
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pcbworld", type=Path, required=True, help="PCBWorld checkout with build_rl/ (engine built)")
    ap.add_argument("--python", type=Path, required=True, help="PCBWorld env's python")
    ap.add_argument("--corpus", type=Path, required=True, help="d3_corpus.py output (KAE_CORPUS)")
    ap.add_argument("--exacad", type=Path, required=True, help="PCBWorld's pcbench/exacad_sorted")
    ap.add_argument("--store", type=Path, default=Path(os.path.expanduser(os.environ.get("KAE_RESULTS", "~/kae-baselines"))))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--attempts", type=int, default=1)
    ap.add_argument("--workers", type=int, default=int(os.environ.get("KAEQ_CPUS", "4")))
    ap.add_argument("--only", help="corpus ids, comma-separated or @FILE")
    ap.add_argument("--cell", action="append", default=[], metavar="NAME=METHOD_ID")
    ap.add_argument("--reference", action="store_true", help="also score PCBWorld's own routed guide boards")
    a = ap.parse_args()
    rows = rows_of(a.corpus)
    if a.only:
        ids = set(Path(a.only[1:]).read_text().split() if a.only.startswith("@") else a.only.split(","))
        rows = [r for r in rows if r["id"] in ids]
    a.out.mkdir(parents=True, exist_ok=True)
    rc = 0
    if a.reference:
        rc |= build_cell(a, rows, "reference", reference=True)
    for spec in a.cell:
        name, _, mid = spec.partition("=")
        rc |= build_cell(a, rows, name, mid=mid)
    return rc


if __name__ == "__main__":
    sys.exit(main())
