# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A compact description of one board for whoever writes its intent (kae.intent): what the board is
(repo, path), its parts, rails, connectors and the brief's sections, with the exact ids an intent's
`where` clauses can name. No physics runs; about a second per board.

    python board_summary.py BOARD.kicad_pcb [--row row.json] [--pintypes pintypes.json] [-o OUT.json]
"""
import argparse
import json
import os
import sys

PASSIVE = {"resistor", "capacitor", "inductor", "ferrite", "fuse"}


def summarize(path, row=None, pintypes=None):
    from kae.board.kicad_file import load
    from kae.circuit import brief as BR
    from kae.intent import sections as SE
    b = load(path)
    if pintypes:
        refs = pintypes.get("refs") or {}
        for fp in b.footprints:
            m = refs.get(fp.ref) or {}
            for pad in fp.pads:
                pin = m.get(str(pad.number))
                if pin and not pad.pintype and not pad.pinfunction:
                    pad.pintype, pad.pinfunction = pin.get("type") or "", pin.get("name") or ""
    br = BR.build(b)
    parts, passives = [], {}
    for p in br["parts"].values():
        kind = p.get("kind") or ""
        if kind in PASSIVE and not p.get("structures"):
            passives[kind] = passives.get(kind, 0) + 1
            continue
        parts.append(dict(ref=p["ref"], kind=kind, role=p.get("role"), value=p.get("value"),
                          lib_id=p.get("lib_id"), external=p.get("external") or None))
    nets = br.get("nets") or {}
    rails = {n: dict(role=v.get("role"), volts=v.get("volts")) for n, v in nets.items()
             if v.get("role") in ("power", "rail", "supply") or v.get("volts")}
    secs = SE.from_brief(br)
    sections = [dict(id=s.id, kind=s.kind, parts=sorted(s.parts)[:10], nets=sorted(s.nets)[:6]) for s in secs.values()]
    out = dict(schema="kae.board-summary/1", board=os.path.abspath(path),
               source={k: (row or {}).get(k) for k in ("id", "repo", "pcb_path", "license", "tags")},
               layers=len([l for l in getattr(b, "layers", []) if str(l).endswith(".Cu")]) or None,
               footprints=len(b.footprints), parts=sorted(parts, key=lambda p: p["ref"]),
               passives_without_structure=passives, rails=rails,
               ground_nets=sorted(n for n, v in nets.items() if v.get("role") == "ground"),
               sections=sections, summary=br.get("summary"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("board"), ap.add_argument("--row"), ap.add_argument("--pintypes"), ap.add_argument("-o")
    a = ap.parse_args(argv)
    row = json.load(open(a.row)) if a.row and os.path.exists(a.row) else None
    pt = json.load(open(a.pintypes)) if a.pintypes and os.path.exists(a.pintypes) else None
    s = summarize(a.board, row, pt)
    txt = json.dumps(s, indent=1, default=str)
    if a.o:
        with open(a.o, "w") as f:
            f.write(txt + "\n")
    else:
        print(txt)


if __name__ == "__main__":
    sys.exit(main())
