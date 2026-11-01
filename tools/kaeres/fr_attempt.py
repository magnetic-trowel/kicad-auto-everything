# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One Freerouting attempt through kaebench's own adapter, as a command for restart.py:

    python fr_attempt.py --binary FREEROUTING --input IN --output OUT --seed S --time T

The seed picks the adapter's pass count the way kaebench's attempt index does (the only
setting that varies between Freerouting attempts). Needs kaebench importable (PYTHONPATH).
"""
import argparse
import shutil
import sys
from pathlib import Path

from kaebench import adapters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--time", type=float, required=True)
    a = ap.parse_args()
    # The adapter keeps max(120 s, 10 %) of its timeout for DSN export and SES import, which
    # would leave a short attempt ~10 s of routing: size its timeout so Freerouting's own job
    # gets 80 % of this attempt's budget (restart.py allows the attempt slack for the rest).
    job = 0.8 * a.time
    timeout = job / 0.9 if job / 0.9 >= 1200 else job + 120
    res = adapters.make("freerouting", freerouting=a.binary).run(
        "route", Path(a.input).resolve().parent, Path.cwd() / "fr", a.seed, timeout)
    print(res.log[-4000:])
    if res.output is None:
        return 1
    shutil.copy2(res.output, a.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
