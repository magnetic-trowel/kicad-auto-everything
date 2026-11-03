# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-import real repair-round sessions with kae.route.bridge.import_session and report
what the checks find: session vs landed counts, pre-existing items KiCad's import moved to
another net (kae restores them), and the post-write check.

    python ses_import_audit.py PAIRS OUTDIR > rows.jsonl

PAIRS: lines "BOARD SES" (the board the session was imported into, and the session).
"""
import json
import shutil
import sys
from pathlib import Path

from kae.route.bridge import import_session


def main(pairs, outdir):
    outdir = Path(outdir)
    for i, ln in enumerate(open(pairs)):
        board, ses = ln.split()
        d = outdir / f"{i:03d}"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        src = d / "board.kicad_pcb"
        shutil.copy(board, src)
        for ext in (".kicad_pro", ".kicad_dru"):
            p = Path(board).with_suffix(ext)
            if p.exists():
                shutil.copy(p, src.with_suffix(ext))
        row = dict(board=board, ses=ses)
        try:
            res = import_session(src, ses, d / "out.kicad_pcb")
            row.update(import_check=res["import_check"], renetted=len(res.get("renetted") or []),
                       renetted_ex=(res.get("renetted") or [])[:3], kept=len(res.get("kept") or []),
                       write_check={k: v for k, v in res["write_check"].items() if k != "counts"},
                       hazards=[(h["code"], h["severity"]) for h in res["hazards"]])
        except Exception as e:  # noqa: BLE001
            row["error"] = f"{type(e).__name__}: {e}"[:600]
        print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
