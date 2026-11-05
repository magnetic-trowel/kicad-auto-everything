# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""churn_check.py OPS_DIR OUTPUT INPUT OUT_JSON: is an invalid re-score only uuid churn?

A board whose source objects carry no uuid (old formats, generated files) gets fresh random uuids each time
prepare converts it, so a stored output re-scored against a newly prepared task shows those objects as
removed and added although nothing changed. This diagnosis (it changes no score) pairs the foreign objects
by content with the uuid left out: all_churn is true when every removed object has an added twin of equal
content and nothing else differs. Runs in KiCad's Python (pcbnew_ops imports pcbnew)."""
import json
import sys
from collections import Counter

sys.path.insert(0, sys.argv[1])
import pcbnew_ops as P  # noqa: E402

out, inp = (open(p, encoding="utf-8").read() for p in sys.argv[2:4])
ign = P.ROUTING_HEADS + P.UNSCORED_HEADS
f = P._foreign(out, inp, limit=10 ** 6)
a, b = P._keyed(out, ign), P._keyed(inp, ign)
added = Counter(tuple(a[(i["kind"], i["id"])]) for i in f.get("items") or [] if i["change"] == "added" and (i["kind"], i["id"]) in a)
removed = Counter(tuple(b[(i["kind"], i["id"])]) for i in f.get("items") or [] if i["change"] == "removed" and (i["kind"], i["id"]) in b)
other = [i for i in f.get("items") or [] if i["change"] not in ("added", "removed")]
paired = sum((added & removed).values())
res = dict(foreign=f.get("count"), paired_by_content=paired, unpaired_added=sum((added - removed).values()),
           unpaired_removed=sum((removed - added).values()), other=len(other),
           all_churn=bool(f.get("count")) and not other and added == removed)
open(sys.argv[4], "w").write(json.dumps(res))
print(json.dumps(res))
