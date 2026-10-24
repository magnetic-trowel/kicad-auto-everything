# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""xf_common/physics_score_xf.py for another seed: score attempt-N instead of attempt-0.

    python phys_seed.py N RUN_DIR [RUN_DIR ...] --suite ... --out ... --md ...

Only the attempt directory lookup changes; scoring is physics_score.py's, untouched.
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
N = int(sys.argv.pop(1))
_orig = ps.attempt_dir


def attempt_dir(run, bid):
    hits = sorted(Path(run).glob(f"*/*/{bid}/attempt-{N}"))
    return hits[0] if hits else None


ps.attempt_dir = attempt_dir
if __name__ == "__main__":
    sys.exit(ps.main())
