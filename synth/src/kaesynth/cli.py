# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kaesynth command line: build designs, inspect KiCad library symbols and footprints."""
import argparse
import re
import sys

from .kicadlib import FootprintLibs, SymbolLibs


def cmd_build(a):
    from .build import build
    rc = 0
    for path in a.design:
        d, findings, status, kicad = build(path, a.out if len(a.design) == 1 else None,
                                           use_kicad=not a.no_kicad, date=a.date)
        active = [f for f in findings if not f.waived_by]
        shown = [f for f in active if f.severity == "error" or (a.verbose and f.severity == "warning")]
        for f in shown:
            print(f"  {f.severity:7s} {f.check}: {f.message}")
        kc = (f"ERC {kicad['erc_summary']}, netlist {'identical' if not kicad['netlist_problems'] else 'MISMATCH'}"
              if kicad.get("ran") else f"KiCad: {kicad.get('reason')}")
        print(f"{d.slug}: {status['error']} errors, {status['warning']} warnings, {status['waived']} waived; {kc}"
              + (f"; BLOCKING questions open: {', '.join(status['blocking_questions'])}" if status["blocking_questions"] else ""))
        if status["error"]:
            rc = 1
    return rc


def cmd_sym(a):
    libs = SymbolLibs()
    if ":" in a.query and not any(c in a.query for c in "*?[]()|+\\"):
        s = libs.get(a.query)
        print(f"{s.lib_id}: {s.units} unit(s){' power' if s.power else ''}")
        for p in sorted(s.pins, key=lambda p: (p.unit, _nat(p.number))):
            print(f"  unit {p.unit} pin {p.number:>4} {p.name:20s} {p.type}{' HIDDEN' if p.hidden else ''}")
        return 0
    rx = re.compile(a.query, re.I)
    n = 0
    for lib in libs.libraries():
        if a.lib and lib != a.lib:
            continue
        for name in libs.names(lib):
            if rx.search(f"{lib}:{name}"):
                print(f"{lib}:{name}")
                n += 1
                if n >= a.limit:
                    return 0
    return 0


def cmd_fp(a):
    fl = FootprintLibs()
    if ":" in a.query and fl.has(a.query):
        print(f"{a.query}: pads {sorted(fl.pads(a.query), key=_nat)}")
        return 0
    rx = re.compile(a.query, re.I)
    n = 0
    for d in sorted(fl.root.glob("*.pretty")):
        for f in sorted(d.glob("*.kicad_mod")):
            lid = f"{d.stem}:{f.stem}"
            if rx.search(lid):
                print(lid)
                n += 1
                if n >= a.limit:
                    return 0
    return 0


def _nat(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s))]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kaesynth", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="check a design and write its KiCad project, intent, BOM and report")
    b.add_argument("design", nargs="+", help="path(s) to designs/<slug>/design.py")
    b.add_argument("-o", "--out", help="output directory (default: <design dir>/out)")
    b.add_argument("--no-kicad", action="store_true", help="skip kicad-cli ERC and netlist round trip")
    b.add_argument("--date", help="title-block date (default: today)")
    b.add_argument("-v", "--verbose", action="store_true", help="also print warnings")
    b.set_defaults(fn=cmd_build)
    s = sub.add_parser("sym", help="search KiCad symbols by regex, or show pins of Lib:Name")
    s.add_argument("query")
    s.add_argument("--lib")
    s.add_argument("--limit", type=int, default=200)
    s.set_defaults(fn=cmd_sym)
    f = sub.add_parser("fp", help="search KiCad footprints by regex, or show pads of Lib:Name")
    f.add_argument("query")
    f.add_argument("--limit", type=int, default=200)
    f.set_defaults(fn=cmd_fp)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
