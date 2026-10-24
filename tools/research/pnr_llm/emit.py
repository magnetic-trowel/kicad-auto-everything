# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kaebench --command adapter that hands the harness a board the LLM loop already wrote.

    python emit.py NAME {input} {output}

The task id is read from the input path (kae-work/tasks/<id>/place/input/board.kicad_pcb);
kae-work/pnr_llm/<id>/NAME.kicad_pcb is copied to {output}. Scoring is the harness's own.
"""
import shutil
import sys
from pathlib import Path

name, inp, out = sys.argv[1:4]
bid = Path(inp).resolve().parents[2].name
src = Path("/home/user/kicad-auto-everything/kae-work/pnr_llm") / bid / f"{name}.kicad_pcb"
if not src.exists():
    sys.exit(f"no {src}")
Path(out).parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(src, out)
print(f"copied {src}")
