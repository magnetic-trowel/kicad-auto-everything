# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The commander's view of an evaluation, under an intent. No physics runs: an evaluation's saved
observations (python -m kae.excite.evaluate BOARD -o EVAL.json) are re-scored in seconds.

    python -m kae.intent catalog EVAL.json                 what kae measures on this board, and its sections
    python -m kae.intent status EVAL.json [--intent I.json] [--detailed] [-o STATUS.json]
    python -m kae.intent compare EVAL_A.json EVAL_B.json ... [--intent I.json]
"""
from __future__ import annotations

import argparse
import json
import sys

from . import objective as OB
from . import sections as SE


def _brief(ev):
    from kae.board.kicad_file import load
    from kae.circuit import brief as B
    return B.build(load(ev["board"]))


def catalog(ev, brief):
    secs = SE.from_brief(brief)
    kinds = {}
    for o in ev.get("observations") or []:
        kinds.setdefault(o["id"], []).append(o.get("label"))
    return dict(schema="kae.catalog/1", board=ev.get("board"),
                kinds={k: dict(unit=u, description=d, instances=len(kinds.get(k, [])),
                               examples=kinds.get(k, [])[:3]) for k, (u, d) in OB.KINDS.items()},
                scope_keys=OB.SCOPE_KEYS, tiers=OB.TIERS, aggs=OB.AGGS,
                sections={s.id: dict(kind=s.kind, parts=sorted(s.parts)[:12], nets=sorted(s.nets)[:8])
                          for s in secs.values()},
                not_yet=["knobs (router consumption) arrive with the router's intent support",
                         "bands above the quasi-static limit (~300 MHz) are not computable"])


def text(st, detailed=False):
    out = []
    if st.get("tiers") is None:
        return f"{st.get('board')}: no score ({st.get('why_incomplete')})"
    t = st["tiers"]
    out.append(f"{st['board']}  [intent generation {st['observedGeneration']}, defaults {st['defaults']}]")
    out.append(f"  hard violations {t['hard']:g}; limits {t['limit']:.4g} + costs {t['cost']:.4g} = "
               f"{t['limit'] + t['cost']:.4g} {st['currency']}")
    for r in st["terms"]:
        if r["tier"] == "ignore":
            out.append(f"  {r['id']:4s} ignore  {r['obs']} ({r['matched']} matched): {r.get('why')}")
            continue
        met = "" if "met" not in r else ("  met" if r["met"] else "  NOT MET")
        lim = f" vs {r['limit']} (margin {r['margin']})" if r.get("limit") else ""
        con = f"  -> {r['contribution']:.4g} {st['currency']} ({r['share']:.0%})" if "contribution" in r else ""
        out.append(f"  {r['id']:4s} {r['tier']:6s} {r['obs']}: {r.get('value', '-')} ({r.get('agg')}, "
                   f"{r['matched']} matched){lim}{met}{con}")
        if r.get("dominant"):
            out.append(f"         dominant: {r['dominant']}" + (f" at {r['f_MHz']} MHz" if r.get("f_MHz") else ""))
        if detailed and r.get("rests_on"):
            out.append(f"         rests on: {'; '.join(r['rests_on'])}")
    n = len(st["unclaimed"])
    if n:
        out.append(f"  unpriced (no term asks about them), largest against the evaluator's old reference first:")
        for u in st["unclaimed"][: (n if detailed else 6)]:
            ref = f" (reference {u['reference']}, x{u['ratio']:g})" if u.get("reference") else ""
            out.append(f"    {u['obs']:16s} {u['worst']:>12s}{ref}  {u['label']}")
    for q in st["questions"][: (99 if detailed else 4)]:
        out.append(f"  question {q['id']}: {q['ask']}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kae.intent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("catalog")
    c.add_argument("eval")
    s = sub.add_parser("status")
    s.add_argument("eval")
    s.add_argument("--intent")
    s.add_argument("--detailed", action="store_true")
    s.add_argument("-o")
    m = sub.add_parser("compare")
    m.add_argument("evals", nargs="+")
    m.add_argument("--intent")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "catalog":
            ev = json.load(open(a.eval))
            print(json.dumps(catalog(ev, _brief(ev)), indent=1))
        elif a.cmd == "status":
            ev = json.load(open(a.eval))
            st = OB.evaluate(ev, a.intent, _brief(ev))
            print(text(st, a.detailed))
            if a.o:
                json.dump(st, open(a.o, "w"), indent=1, default=str)
        else:
            evs = [json.load(open(p)) for p in a.evals]
            brief = _brief(evs[0])                 # versions of one board share its parts and structures
            sts = [OB.evaluate(ev, a.intent, brief) for ev in evs]
            order = sorted(range(len(sts)), key=lambda i: OB.key(sts[i]))
            for rank, i in enumerate(order, 1):
                k = OB.key(sts[i])
                top = max((r for r in sts[i]["terms"] if "contribution" in r), key=lambda r: r["contribution"],
                          default=None)
                print(f"{rank}. {a.evals[i]}: hard {k[0]:g}, {k[1]:.4g} {sts[i]['currency']}"
                      + (f"; dominant {top['id']} {top['obs']} = {top.get('value')}" if top else ""))
    except (OB.IntentError, SE.SectionError, ValueError) as e:
        print(f"intent error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
