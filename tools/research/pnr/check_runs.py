# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sanity checks of joint runs: non-ok attempts (with the adapter log's last error line),
invalid scores and why, the engine's own unrouted count vs KiCad's unconnected count,
and DRC error types per board.

    python check_runs.py kae-v7/results/RUN [...]
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path


def main(runs):
    for run in runs:
        print(f"== {Path(run).name}")
        types = Counter()
        for f in sorted(Path(run).glob("*/joint/*/attempt-*/attempt.json")):
            r = json.loads(f.read_text())
            s = r.get("score") or {}
            tag = f"{r['id'][:44]} #{r['attempt']}"
            log = (f.parent / "adapter.log").read_text(errors="replace") if (f.parent / "adapter.log").exists() else ""
            if r.get("status") != "ok":
                err = [ln for ln in log.splitlines() if ln.strip()][-1:] or ["(empty log)"]
                print(f"  {tag}: {r.get('status')} t={r.get('runtime_s')} :: {err[0][:160]}")
                continue
            m = re.findall(r'\{"length_mm".*\}', log)
            eng = json.loads(m[-1]) if m else {}
            if not s.get("valid"):
                bad = [k for k, v in (s.get("integrity") or {}).items() if not v]
                print(f"  {tag}: INVALID {bad} locked_moved={s.get('locked_moved')}")
            if eng and s.get("valid") and eng.get("unrouted") != s.get("unconnected"):
                print(f"  {tag}: engine unrouted {eng.get('unrouted')} vs KiCad unconnected {s.get('unconnected')}")
            e = s.get("errors_by_type") or {}
            types.update(e)
            if e or s.get("outside"):
                print(f"  {tag}: legal={s.get('legal')} outside={s.get('outside')} errors={e}")
        print(f"  error types: {dict(types.most_common())}")


if __name__ == "__main__":
    main(sys.argv[1:])
