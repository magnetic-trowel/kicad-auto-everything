# SPDX-License-Identifier: GPL-3.0-or-later
"""Sum infield.py outputs: human (if-h) against ours (if-r, if-m). usage: aggif.py <ana dir>"""
import glob, json, os, sys
from collections import Counter
A = sys.argv[1]
hs = {}
for p in glob.glob(f"{A}/if-h/*.json"):
    hs[os.path.basename(p)[:-5]] = {r["ref"]: r for r in json.load(open(p))}
for tag in ("r", "m"):
    s, parts, withpin = Counter(), 0, Counter()
    for p in glob.glob(f"{A}/if-{tag}/*.json"):
        b = os.path.basename(p)[:-5]
        if tag == "m":
            b = b.split("-", 1)[1].rsplit("-a", 1)[0]
        h = hs.get(b)
        if h is None:
            continue
        for r in json.load(open(p)):
            hr = h.get(r["ref"])
            if not hr:
                continue
            parts += 1
            for k in ("foreign_vias", "own_vias", "pin_vias", "foreign_len_side", "foreign_len_other"):
                s["h_" + k] += hr[k]
                s["o_" + k] += r[k]
            withpin["h"] += hr["pin_vias"] > 0
            withpin["o"] += r["pin_vias"] > 0
    print(f"ours={tag}: {parts} fine-pitch perimeter parts; parts with pin-net vias in the field: "
          f"human {withpin['h']}, ours {withpin['o']}")
    for k in ("pin_vias", "foreign_vias", "own_vias", "foreign_len_side", "foreign_len_other"):
        print(f"  {k}: human {s['h_' + k]:.1f}  ours {s['o_' + k]:.1f}")
