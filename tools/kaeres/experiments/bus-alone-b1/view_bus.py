#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kicad-cli DRC of the bus-only view of stored runs: net -> unconnected items, per run.

Usage: view_bus.py TASKS OUT_DIR BUSNETS_DIR; TASKS lines are `board arm run_dir`. Writes OUT_DIR/<board>.<arm>.json.
Needs KAE_KICAD_WRAP (source ~/.cache/kaebench/env.sh) and APPTAINER_BIND covering the scratch directory."""
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
NET = re.compile(r'\[(.*?)\](?= of | on |\s*$)')


def main():
    tasks, out, nets_dir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    wrap = os.environ.get("KAE_KICAD_WRAP", "").split()
    scratch = Path(tempfile.mkdtemp(prefix="busview", dir=os.environ.get("KAEQ_SCRATCH") or "/var/tmp/eriks"))
    for line in Path(tasks).read_text().splitlines():
        bid, arm, rd = line.split()
        dest = out / f"{bid}.{arm}.json"
        if dest.exists():
            continue
        rec = dict(board=bid, arm=arm, run=rd)
        try:
            pcb = Path(rd) / "output.kicad_pcb.gz"
            if not pcb.exists():
                rec["error"] = "no output"
            else:
                src, view, rep = scratch / "in.kicad_pcb", scratch / "view.kicad_pcb", scratch / "drc.json"
                for p in (src, view, rep):
                    p.unlink(missing_ok=True)
                with gzip.open(pcb, "rb") as f, open(src, "wb") as g:
                    shutil.copyfileobj(f, g)
                r = subprocess.run([*wrap, "python3", str(HERE / "make_view.py"), str(src), str(view), str(nets_dir / f"{bid}.txt")],
                                   capture_output=True, text=True, timeout=1800)
                if not view.exists():
                    raise RuntimeError(f"view failed rc={r.returncode}: {r.stderr[-400:]}")
                r = subprocess.run([*wrap, "kicad-cli", "pcb", "drc", "--format", "json", "--refill-zones", "--severity-all", "--units", "mm",
                                    "-o", str(rep), str(view)], capture_output=True, text=True, timeout=3600, cwd=scratch)
                d = json.load(open(rep))
                opens = {}
                for it in d.get("unconnected_items", []):
                    for sub in it.get("items", []):
                        m = NET.search(sub.get("description", ""))
                        if m:
                            opens[m.group(1)] = opens.get(m.group(1), 0) + 1
                rec.update(opens=opens, n_unconnected=len(d.get("unconnected_items", [])))
        except Exception as e:
            rec["error"] = repr(e)[:400]
        dest.write_text(json.dumps(rec))
    shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
