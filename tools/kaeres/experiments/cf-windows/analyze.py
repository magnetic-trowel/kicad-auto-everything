#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""cf-windows (PLAN.md): CF-W vs CF. Primary opens on boards open after phase 1; guards clean, errors, physics;
real vs charged CPU per arm; optimizer time-outs.    python3 analyze.py"""
import json, math, statistics as st, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "completion-first"))
import analyze as C  # noqa: E402

D = C.load(sys.argv[1] if len(sys.argv) > 1 else "cf-windows", lambda n: n.split()[2])
B = sorted(b for b in D if "CF" in D[b] and "CFW" in D[b])


def p1(b, arm):
    ph = ((D[b][arm].get("sum") or {}).get("phases") or [{}])[0].get("rank")
    return ph


S = [b for b in B if p1(b, "CF") is not None and p1(b, "CF")[1] != 0]
agree = sum(p1(b, "CF") == p1(b, "CFW") for b in B)


def cmp(sel, name):
    ow = [D[b]["CFW"]["s"]["unconnected"] for b in sel]; oc = [D[b]["CF"]["s"]["unconnected"] for b in sel]
    d = [(x - y) / (x + y + 1) for x, y in zip(ow, oc)]
    p = C.sign_flip(d)
    print(f"{name}: n {len(sel)} opens CF-W {sum(ow)} vs CF {sum(oc)} ({100 * (sum(ow) / max(1, sum(oc)) - 1):+.1f} %), "
          f"fewer/more {sum(x < y for x, y in zip(ow, oc))}/{sum(x > y for x, y in zip(ow, oc))}, mean d {st.mean(d) if d else 0:+.3f}, p {p:.4f}")
    return ow, oc, d, p


print(f"{len(B)} boards; phase 1 identical in both arms on {agree}; open after phase 1: {len(S)}")
ow, oc, d, p = cmp(S, "primary (open after phase 1)")
win = d and st.mean(d) < 0 and p < 0.05 and sum(ow) <= 0.97 * sum(oc)
lose = d and st.mean(d) > 0 and p < 0.05 and sum(ow) >= 1.03 * sum(oc)
cmp(B, "all boards")
g = lambda arm, k: sum(bool(D[b][arm]["s"].get(k)) if k in ("clean", "legal") else (D[b][arm]["s"].get(k) or 0) for b in B)  # noqa: E731
xs = [x for x in (C.phys(D[b]["CFW"], D[b]["CF"]) for b in B) if x is not None and abs(x) > 1e-12]
m = math.exp(st.median(xs)) if xs else float("nan")
fl = 1.04 if len(xs) >= 80 else 1.05 if len(xs) >= 50 else 1.06 if len(xs) >= 38 else 1.08 if len(xs) >= 30 else 1.12
guards = g("CFW", "clean") >= g("CF", "clean") - 2 and g("CFW", "errors") <= 1.03 * g("CF", "errors") and (not xs or m <= fl)
print(f"clean {g('CFW', 'clean')} vs {g('CF', 'clean')}; legal {g('CFW', 'legal')} vs {g('CF', 'legal')}; errors "
      f"{g('CFW', 'errors')} vs {g('CF', 'errors')}; physics CF-W/CF n {len(xs)} median {m:.3f} (floor {fl:.2f})")
print(f"verdict: {'CF-W wins' if win else 'CF wins' if lose else 'undecided'}; guards {'hold' if guards else 'fail'}")
for arm in ("CF", "CFW"):
    rows = [D[b][arm] for b in B]
    charged = sum((r.get("sum") or {}).get("budget_s") or 0 for r in rows)
    print(f"{arm}: real CPU {sum(r['cpu'] for r in rows) / 3600:.1f} h vs charged allowance (--time x 4 lanes) "
          f"{4 * charged / 3600:.1f} h; optimizer timed_out runs {sum(any('timed_out' in x for x in r['opt']) for r in rows)}; "
          f"second phase {dict(__import__('collections').Counter(str((r.get('sum') or {}).get('second')) for r in rows))}")
