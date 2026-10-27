# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tables from ex_fidelity.py outputs (docs/topics/physics/exact-physics-in-kae.md section 4).

    python tools/research/physics/ex_fidelity_report.py kae-work-v3/physics/exact-fidelity/*.json
"""
import json
import sys

import numpy as np


def med(x):
    x = [v for v in x if v is not None]
    return float(np.median(x)) if x else float("nan")


def main(paths):
    print("| Board | loop modules | closed form ms | PEEC ms cold / warm | stage s fast / multi / exact | PEEC calls multi / exact |")
    print("|---|---|---|---|---|---|")
    rows2 = []
    for p in paths:
        r = json.load(open(p))
        M = r["modules"] if "modules" in r else r["modes"]
        f, mu, ex = M["fast"]["modules"], M["multi"]["modules"], M["exact"]["modules"]
        ids = [k for k, v in f.items() if v["kind"] in ("cell", "path", "decap", "chain") and v["status"] in ("routed", "partial")]
        tm = r.get("timing", {})
        name = r["board"].replace("pcbcorpus-", "")[:34]
        sec = [round(sum(M[m]["modules"][k]["seconds"] for k in ids), 1) for m in ("fast", "multi", "exact")]
        calls = [sum(M[m]["modules"][k]["exact_calls"] for k in ids) for m in ("multi", "exact")]
        print(f"| {name} | {len(ids)} | {med([t['fast_ms'] for t in tm.values()]):.2f} | "
              f"{med([t['exact_cold_ms'] for t in tm.values()]):.1f} / {med([t['exact_warm_ms'] for t in tm.values()]):.1f} | "
              f"{sec[0]} / {sec[1]} / {sec[2]} | {calls[0]} / {calls[1]} |")
        dec = sum(mu[k]["decisions"] for k in ids)
        chg = sum(mu[k]["changed"] for k in ids)
        via_m = sum(1 for k in ids if mu[k]["vias"] != f[k]["vias"])
        via_e = sum(1 for k in ids if ex[k]["vias"] != f[k]["vias"])

        def rel(a, b):
            return [(a[k]["exact"] / b[k]["exact"] - 1.0) for k in ids
                    if a[k]["exact"] is not None and b[k]["exact"] is not None and b[k]["exact"] > 0]
        rm, re_ = rel(mu, f), rel(ex, f)
        cf = [(f[k]["fast"] / f[k]["exact"] - 1.0) for k in ids if f[k]["fast"] and f[k]["exact"]]
        tot = [sum(d[k]["exact"] for k in ids if all(x[k]["exact"] for x in (f, mu, ex))) for d in (f, mu, ex)]
        rows2.append((name, dec, chg, via_m, via_e, len(ids), rm, re_, cf, tot))
    print()
    print("| Board | multi decisions (changed) | modules with other vias: multi / exact | exact L of multi vs fast choice: median, min | exact vs fast choice: median, min | sum of exact L fast / multi / exact (nH) | closed form / PEEC on fast copper: median (min..max) |")
    print("|---|---|---|---|---|---|---|")
    for name, dec, chg, vm, ve, n, rm, re_, cf, tot in rows2:
        def mm(x):
            return f"{100 * med(x):+.2f}%, {100 * min(x):+.1f}%" if x else "-"
        print(f"| {name} | {dec} ({chg}) | {vm} / {ve} of {n} | {mm(rm)} | {mm(re_)} | "
              f"{tot[0]:.2f} / {tot[1]:.2f} / {tot[2]:.2f} | "
              f"{100 * med(cf):+.1f}% ({100 * min(cf):+.1f}..{100 * max(cf):+.1f}%) |")


if __name__ == "__main__":
    main(sys.argv[1:])
