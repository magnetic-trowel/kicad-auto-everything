# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Coverage statistics for the derivation audit (round 3, prefix da).

Parses docs/topics/physics/derivation-audit-table.md (one row per rule P01-P59, S01-S55, R01-R46) and
counts verdicts, principles, number status and changes against round 1.  The counts quoted in
docs/topics/physics/derivation-audit.md come from this script, so the table is the single source.

Columns: ID | Rule | R1 (origin/verdict) | Principles (';'-separated, first = primary; code + sub-tag) |
Derivation | Regime | Num | Verdict | Change vs round 1.

Run:  python da_coverage.py [path/to/derivation-audit-table.md]
"""
import collections
import pathlib
import re
import sys

VERDICTS = ["derivable", "derivable-with-regime", "convention", "legal", "habit-wrong", "not derivable"]
NUMS = ["derived", "instance", "data", "arbitrary", "—"]
CODES = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "MP", "LG", "CG"]
ORIGIN_GROUP = {"Ph": "physics", "Sp": "simplicity", "Mf": "manufacturing", "Hb": "habit",
                "Cg": "cog/tool/legal/CT", "Tl": "cog/tool/legal/CT", "Lg": "cog/tool/legal/CT",
                "CT": "cog/tool/legal/CT"}


def parse(path):
    rows = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*([PSR]\d\d)\s*\|", line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 9:
            raise SystemExit(f"{m.group(1)}: expected 9 cells, got {len(cells)}")
        rid, rule, r1, princ, deriv, regime, num, verdict, change = cells
        if verdict not in VERDICTS:
            raise SystemExit(f"{rid}: bad verdict {verdict!r}")
        if num not in NUMS:
            raise SystemExit(f"{rid}: bad num {num!r}")
        if not regime:
            raise SystemExit(f"{rid}: empty regime")
        plist = []
        for p in princ.split(";"):
            p = p.strip()
            if not p or p.startswith("(") or p == "—":
                continue
            code, _, tag = p.partition(" ")
            if code not in CODES:
                raise SystemExit(f"{rid}: bad principle code {code!r}")
            plist.append((code, tag.strip()))
        origin = re.split(r"[+/?]", r1)[0]
        r1v = r1.split("/", 1)[1].split()[0] if "/" in r1 else "?"
        ctag = change.split(":", 1)[0].strip()
        rows.append(dict(id=rid, rule=rule, origin=origin, r1v=r1v, princ=plist, regime=regime, num=num,
                         verdict=verdict, change=change, ctags=set(ctag.split("+")) - {"none"}))
    return rows


def table(title, counter, keys=None, total=None):
    keys = keys or sorted(counter, key=lambda k: -counter[k])
    print(f"\n{title}")
    for k in keys:
        v = counter.get(k, 0)
        pct = f" ({100*v/total:4.1f}%)" if total else ""
        print(f"   {k:28s} {v:4d}{pct}")


def main():
    here = pathlib.Path(__file__).resolve()
    default = here.parents[3] / "docs/topics/physics/derivation-audit-table.md"
    path = sys.argv[1] if len(sys.argv) > 1 else default
    rows = parse(path)
    ids = [r["id"] for r in rows]
    expect = [f"P{i:02d}" for i in range(1, 60)] + [f"S{i:02d}" for i in range(1, 56)] + \
             [f"R{i:02d}" for i in range(1, 47)]
    missing = sorted(set(expect) - set(ids))
    dup = [k for k, v in collections.Counter(ids).items() if v > 1]
    print(f"rows {len(rows)}; missing {missing or 'none'}; duplicates {dup or 'none'}")
    n = len(rows)

    table("Verdicts", collections.Counter(r["verdict"] for r in rows), VERDICTS, n)
    for pre in "PSR":
        c = collections.Counter(r["verdict"] for r in rows if r["id"].startswith(pre))
        print(f"   {pre}: " + ", ".join(f"{v} {c.get(v, 0)}" for v in VERDICTS))

    der = [r for r in rows if r["verdict"] in ("derivable", "derivable-with-regime")]
    nd = len(der)
    print(f"\nderived (derivable + with regime): {nd} of {n}")
    table("Primary principle of derived rules", collections.Counter(r["princ"][0][0] for r in der if r["princ"]),
          CODES, nd)
    table("Any mention among derived rules", collections.Counter(c for r in der for c in {p[0] for p in r["princ"]}),
          CODES, nd)
    table("Any mention among all rules", collections.Counter(c for r in rows for c in {p[0] for p in r["princ"]}),
          CODES, n)
    only_core = [r["id"] for r in der if r["princ"] and {p[0] for p in r["princ"]} <= {"P1", "P2", "P3", "P4", "P5", "P6"}]
    print(f"\nderived from P1-P6 alone (no MP, LG, CG, P7): {len(only_core)}")
    needs_p7 = [r for r in rows if any(p[0] == "P7" for p in r["princ"])]
    print(f"rules naming P7 (extremes and accumulation): {len(needs_p7)}: " +
          ", ".join(f"{r['id']}({r['verdict']})" for r in needs_p7))
    p7_der = [r["id"] for r in needs_p7 if r["verdict"] in ("derivable", "derivable-with-regime")]
    print(f"   of which derived: {len(p7_der)} {p7_der}")
    mp = [r for r in rows if any(p[0] == "MP" for p in r["princ"])]
    mp_core = [r["id"] for r in mp if {p[0] for p in r["princ"]} & {"P1", "P2", "P3", "P4", "P5", "P6", "P7"}]
    print(f"rules naming MP: {len(mp)}; with a P1-P7 core as well: {len(mp_core)}; MP alone: "
          f"{[r['id'] for r in mp if r['id'] not in mp_core]}")

    tags = collections.Counter(f"{c} {t}" for r in rows for (c, t) in r["princ"] if t)
    table("Sub-tags (all rules)", tags)
    zz = [r for r in rows if ("P4", "Z/Z0") in r["princ"]]
    print(f"\nimpedance level (P4 Z/Z0): {len(zz)} rules: {[r['id'] for r in zz]}; verdicts "
          f"{dict(collections.Counter(r['verdict'] for r in zz))}")

    table("Num status (all rules)", collections.Counter(r["num"] for r in rows), NUMS, n)
    with_num = [r for r in rows if r["num"] != "—"]
    print(f"   rules stating a number: {len(with_num)}")
    for v in VERDICTS:
        c = collections.Counter(r["num"] for r in rows if r["verdict"] == v)
        print(f"   {v:24s} " + ", ".join(f"{k} {c.get(k, 0)}" for k in NUMS))

    print("\nOrigin (round 1, first listed) x verdict")
    groups = ["physics", "simplicity", "manufacturing", "habit", "cog/tool/legal/CT"]
    print("   " + " " * 20 + "".join(f"{v[:14]:>15s}" for v in VERDICTS) + "   total")
    for g in groups:
        rr = [r for r in rows if ORIGIN_GROUP.get(r["origin"], "?") == g]
        c = collections.Counter(r["verdict"] for r in rr)
        print(f"   {g:20s}" + "".join(f"{c.get(v, 0):15d}" for v in VERDICTS) + f"   {len(rr):5d}")
    unk = [r["id"] for r in rows if r["origin"] not in ORIGIN_GROUP]
    if unk:
        print(f"   unknown origin: {unk}")

    print("\nRound-1 verdict x new verdict")
    r1keys = sorted({r["r1v"] for r in rows})
    for k in r1keys:
        c = collections.Counter(r["verdict"] for r in rows if r["r1v"] == k)
        print(f"   R1 {k:12s}: " + ", ".join(f"{v} {c[v]}" for v in VERDICTS if c.get(v)))

    ct = collections.Counter(t for r in rows for t in r["ctags"])
    table("Change tags", ct, ["principle", "adds", "verdict", "regime", "derived"])
    print(f"   rows with any change: {sum(1 for r in rows if r['ctags'])}")
    ph_principle = [r["id"] for r in rows if "principle" in r["ctags"] and r["origin"] == "Ph"]
    print(f"   physics-origin rows whose principle changed: {len(ph_principle)}: {ph_principle}")
    hb = [r for r in rows if r["origin"] == "Hb"]
    print(f"   habit-origin rows: {len(hb)}; verdicts {dict(collections.Counter(r['verdict'] for r in hb))}")


if __name__ == "__main__":
    main()
