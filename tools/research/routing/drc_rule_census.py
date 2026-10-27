# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Census of KiCad DRC violations in a kaebench run, by type, rule source and size of the miss.

Reads every attempt's score/drc.json under a run directory and groups the violations so that
translation faults (a constraint the router never saw) separate from routing faults:

  type             KiCad's violation key (track_width, clearance, ...)
  source           the rule KiCad applied, parsed from the description: "board setup",
                   "netclass 'X'", "rule 'Y'" (custom .kicad_dru), or "?" when absent
  ratio            actual / required for min-type constraints (track width, clearance, annular
                   width, hole clearance, ...), binned; a tight cluster just under 1.0 points at
                   rounding or a systematic offset, a cluster far below at a missing constraint
  items            the item kinds involved (Track, Via, Pad, Zone, ...)

Usage: python -I drc_rule_census.py RUN_DIR [--json OUT] [--examples 3]
Prints a markdown summary; --json writes the full aggregation.
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

NUM = r"(-?[\d.]+)\s*mm"
SRC_RE = re.compile(r"\((?P<src>[^;()]*?)\s+(?:min|max|clearance|opt)[^;()]*?" + NUM + r"[^()]*?actual\s+" + NUM)
GENERIC_RE = re.compile(r"\((?P<src>[^;()]*?)(?:;|\))")
KIND_RE = re.compile(r"^(Track|Via|Pad|Zone|Arc|Hole|Footprint|Graphic|Text|PTH pad|NPTH pad|Segment|Rule area|Line|Rectangle|Polygon|Circle)",
                     re.I)


def parse(desc):
    """(source, required, actual) from a KiCad DRC description, or (source, None, None)."""
    m = SRC_RE.search(desc)
    if m:
        req = float(re.search(NUM, desc[m.start():]).group(1))
        act = float(m.group(len(m.groups())))
        return m.group("src").strip(), req, act
    m = GENERIC_RE.search(desc)
    return (m.group("src").strip() if m else "?"), None, None


def norm_source(src):
    s = src.lower()
    if "board setup" in s:
        return "board setup"
    if "netclass" in s:
        return "netclass"
    if "rule" in s:
        return "custom rule"
    return src[:40] or "?"


def ratio_bin(r):
    if r is None:
        return "n/a"
    for hi in (0.5, 0.75, 0.9, 0.95, 0.99, 0.999, 1.0):
        if r < hi:
            return f"<{hi}"
    return ">=1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--json")
    ap.add_argument("--examples", type=int, default=3)
    a = ap.parse_args()
    agg = collections.defaultdict(lambda: dict(n=0, boards=set(), ratios=collections.Counter(), items=collections.Counter(),
                                                 examples=[]))
    attempts = 0
    for f in sorted(Path(a.run_dir).glob("**/score/drc.json")):
        attempts += 1
        board = f.parts[-4] if f.parts[-3].startswith("attempt") else f.parts[-3]
        try:
            d = json.load(open(f))
        except (OSError, ValueError):
            continue
        for v in d.get("violations", []):
            if v.get("severity") != "error":
                continue
            src, req, act = parse(v.get("description", ""))
            key = (v["type"], norm_source(src))
            g = agg[key]
            g["n"] += 1
            g["boards"].add(board)
            g["ratios"][ratio_bin(act / req if req else None)] += 1
            for it in v.get("items", []):
                m = KIND_RE.match(it.get("description", ""))
                g["items"][m.group(1) if m else it.get("description", "")[:20]] += 1
            if len(g["examples"]) < a.examples:
                g["examples"].append(dict(board=board, desc=v.get("description"),
                                          items=[it.get("description") for it in v.get("items", [])]))
    rows = sorted(agg.items(), key=lambda kv: -kv[1]["n"])
    print(f"# DRC rule census: {a.run_dir}\n\n{attempts} attempts\n")
    print("| type | source | errors | boards | actual/required | items |\n|---|---|---|---|---|---|")
    for (t, s), g in rows:
        rat = ", ".join(f"{k} {v}" for k, v in sorted(g["ratios"].items()))
        its = ", ".join(f"{k} {v}" for k, v in g["items"].most_common(4))
        print(f"| {t} | {s} | {g['n']} | {len(g['boards'])} | {rat} | {its} |")
    print("\n## Examples\n")
    for (t, s), g in rows[:12]:
        for e in g["examples"]:
            print(f"- **{t} / {s}** ({e['board']}): {e['desc']} — {'; '.join(e['items'])}")
    if a.json:
        out = {f"{t}|{s}": dict(n=g["n"], boards=sorted(g["boards"]), ratios=dict(g["ratios"]), items=dict(g["items"]),
                                examples=g["examples"]) for (t, s), g in rows}
        Path(a.json).write_text(json.dumps(dict(run=a.run_dir, attempts=attempts, groups=out), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
