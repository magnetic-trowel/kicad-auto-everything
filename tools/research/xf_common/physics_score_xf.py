# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run tools/research/pnr_phys/physics_score.py against $XF_WORK, for any seed.

    python physics_score_xf.py [--attempt N] RUN_DIR [RUN_DIR ...] --suite ... --out ... --md ...

physics_score.py fixes its work directory at the path of the host it was written on and
reads attempt-0 only. This wrapper changes only where it looks, never how it scores:

- ROOT/WORK point at this worktree and $XF_WORK (default kae-work2);
- --attempt N scores attempt-N (seed N) instead of attempt-0. Seeds N > 0 get their own
  cache (WORK/phys-cache-seedN, since physics_score caches one output per run and board),
  pre-filled with the reference boards' briefs and human scores from WORK/phys-cache;
- the harness columns (legal, clean, completion) also read joint tasks, whose score holds
  placement and routing together (physics_score reads them from a place task's probe).
"""
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(os.environ.get("XF_ROOT") or Path(__file__).resolve().parents[3])
WORK = Path(os.environ.get("XF_WORK") or ROOT / "kae-work2")
spec = importlib.util.spec_from_file_location(
    "physics_score", ROOT / "tools" / "research" / "pnr_phys" / "physics_score.py")
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)
ps.ROOT, ps.WORK = ROOT, WORK
_harness_info = ps.harness_info


def harness_info(adir):
    try:
        r = json.loads((Path(adir) / "attempt.json").read_text())
    except (OSError, ValueError):
        return {}
    if r.get("kind") != "joint":
        return _harness_info(adir)
    s = r.get("score") or {}
    return dict(status=r.get("status"), legal=bool(s.get("legal")), clean=bool(s.get("legal")) and bool(s.get("clean")),
                completion=s.get("completion", 0.0) if s.get("valid") else 0.0,
                length_mm=s.get("track_length_mm"), vias=s.get("vias"))


def seed_cache(n, base):
    """Cache dir for seed n: its own run results, the reference work copied from base."""
    d = WORK / f"phys-cache-seed{n}"
    for b in Path(base).glob("*/brief.json"):
        t = d / b.parent.name
        t.mkdir(parents=True, exist_ok=True)
        for f in ("brief.json", "brief.meta.json", "human.json"):
            if (b.parent / f).exists() and not (t / f).exists():
                shutil.copy2(b.parent / f, t / f)
    return d


def main(argv):
    n = 0
    if "--attempt" in argv:
        i = argv.index("--attempt")
        n = int(argv[i + 1])
        del argv[i:i + 2]
    ps.harness_info = harness_info
    if n:
        def attempt_dir(run, bid):
            hits = sorted(Path(run).glob(f"*/*/{bid}/attempt-{n}"))
            return hits[0] if hits else None
        ps.attempt_dir = attempt_dir
        if "--cache" not in argv:
            argv += ["--cache", str(seed_cache(n, WORK / "phys-cache"))]
    return ps.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
