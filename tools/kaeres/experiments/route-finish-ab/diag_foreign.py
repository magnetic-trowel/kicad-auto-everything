# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""diag_foreign.py OPS_DIR OUTPUT INPUT_NEW INPUT_OLD: why a stored output is invalid at a newer harness.
Runs in KiCad's Python (pcbnew_ops imports pcbnew). Prints _foreign of the output against the task input of
each harness, and of the two task inputs against each other, with the first tokens of each differing object."""
import json
import sys

sys.path.insert(0, sys.argv[1])
import pcbnew_ops as P  # noqa: E402

out, new, old = (open(p, encoding="utf-8").read() for p in sys.argv[2:5])
ign = P.ROUTING_HEADS + P.UNSCORED_HEADS


def show(name, a_text, b_text):
    f = P._foreign(a_text, b_text)
    print(f"== {name}: {json.dumps({k: f[k] for k in f if k != 'items'})}")
    a, b = P._keyed(a_text, ign), P._keyed(b_text, ign)
    for it in (f.get("items") or [])[:6]:
        k = (it["kind"], it["id"])
        print(f"  {it['change']:10s} {k[0]} {k[1]}")
        for side, d in (("out", a), ("in ", b)):
            if k in d:
                print(f"     {side}: {' '.join(d[k][:60])[:400]}")


show("output vs new input", out, new)
show("output vs old input", out, old)
show("new input vs old input", new, old)
