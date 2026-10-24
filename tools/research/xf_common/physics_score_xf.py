# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run tools/research/pnr_phys/physics_score.py against this worktree's kae-work/.

physics_score.py fixes its work directory at the path of the host it was written on;
this wrapper points its ROOT/WORK at the worktree that holds this file (or $XF_ROOT)
before main() runs, and changes nothing else. Same arguments as physics_score.py.
"""
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("XF_ROOT") or Path(__file__).resolve().parents[3])
spec = importlib.util.spec_from_file_location(
    "physics_score", ROOT / "tools" / "research" / "pnr_phys" / "physics_score.py")
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)
ps.ROOT, ps.WORK = ROOT, ROOT / "kae-work"

if __name__ == "__main__":
    sys.exit(ps.main())
