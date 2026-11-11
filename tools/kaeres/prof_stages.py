# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Wall time per pipeline stage from py-spy raw profiles (README: Profiling a smoke).

  python prof_stages.py prof-*.txt [--rate 25]

Each sample goes to the first stage whose pattern its stack matches; record with --idle so samples
where kae waits on Freerouting, kicad-cli or pcbnew count. Prints each stage's share, seconds and
its top self-time functions."""
import argparse
import collections
import re

STAGES = [   # (stage, stack pattern), first match wins
    ("numba compile", r"numba/core/(dispatcher|compiler)|_compile_for_args"),
    ("imports", r"_find_and_load \(<frozen importlib"),
    ("freerouting", r"(route|_route) \(kae/route/freerouting\.py"),
    ("escape plan: HiGHS", r"_highs_wrapper|milp \(|linprog \("),
    ("escape plan: other", r"kae/route/escape\.py"),
    ("kicad drc", r"kae/route/drc\.py|restart\.py.*judge"),
    ("pcbnew calls", r"pcbnew_io\.py"),
    ("cp-sat", r"ortools/"),
    ("placement", r"kae/place/"),
    ("last mile / repair", r"kae/route/(lastmile|repair|critical|finish|blocked)"),
    ("board load / write", r"kicad_file\.py|sexpr\.py|critical_write"),
    ("route: other", r"kae/route/"),
    ("joint: other", r"kae/joint/"),
    ("physics", r"kae/(physics|excite|circuit)/"),
    ("restart wrapper", r"restart\.py"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--rate", type=float, default=25.0, help="py-spy sampling rate (-r)")
    a = ap.parse_args()
    rx = [(n, re.compile(p)) for n, p in STAGES]
    tot, st, fn = 0, collections.Counter(), collections.defaultdict(collections.Counter)
    for path in a.files:
        with open(path) as f:
            for line in f:
                stack, _, n = line.rstrip().rpartition(" ")
                try:
                    n = int(n)
                except ValueError:
                    continue
                tot += n
                name = next((nm for nm, r in rx if r.search(stack)), "other")
                st[name] += n
                fn[name][re.sub(r":\d+\)", ")", stack.split(";")[-1])[:80]] += n
    print(f"{tot} samples, {tot / a.rate:.0f} s of sampled thread time")
    for k, v in st.most_common():
        top = ", ".join(f"{f} {c / a.rate:.0f}s" for f, c in fn[k].most_common(3))
        print(f"  {100 * v / max(tot, 1):5.1f}%  {v / a.rate:8.1f}s  {k:20s} | {top}")


if __name__ == "__main__":
    main()
