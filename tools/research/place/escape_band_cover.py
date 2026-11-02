# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Which parts sit in each escape band of a placed board (docs/research/placement/escape-keepouts.md).

Per package side from escape_scan.py and depth rule (full: n x (track + clearance); half), the parts on the
package's side whose courtyard overlaps the band, as on-escape (shares a signal net with the package),
decap (<= 3 pads, all on the package's ground/power nets, one power) or other, and the band's covered fraction.

    python escape_band_cover.py SCAN.json BOARD_PATTERN OUT.json

BOARD_PATTERN has {bid}, e.g. ~/kae-boards/boards/{bid}/board.kicad_pcb or a kaeres run's output.kicad_pcb.gz.
"""
import json, sys
from shapely.geometry import box
from shapely.ops import unary_union
from kae.board.kicad_file import load
from kae.board.transform import place_geom, courtyard
from kae.place.problem import Problem
from kae.place import escape_band as EB
scan = json.load(open(sys.argv[1]))
out = {}
for bid, v in scan.items():
    if "rows" not in v:
        continue
    src = sys.argv[2].format(bid=bid)
    if src.endswith(".gz"):
        import gzip, tempfile, os
        if not os.path.exists(src):
            continue
        tmp = tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False)
        tmp.write(gzip.open(src).read()); tmp.close(); src = tmp.name
    try:
        b = load(src)
    except Exception as e:
        out[bid] = dict(error=repr(e)[:100]); continue
    P = Problem.build(b)
    w, c = EB._track_and_clearance(b)
    kind = {n.name: (n.kind if n.kind in ("ground", "power") else "signal") for n in P.nets}
    fps = {fp.ref: fp for fp in b.footprints}
    cy = {}
    for fp in b.footprints:
        try:
            g = unary_union(courtyard(fp) or [])
            cy[fp.ref] = g if g is not None and not g.is_empty else None
        except Exception:
            cy[fp.ref] = None
    rows = []
    for r in v["rows"]:
        fp = fps[r["ref"]]
        pk = EB.package(fp, kind, w, c)
        if pk is None:
            continue
        x0, y0, x1, y1 = EB._extent(fp, 0, 0, 0, 0)
        pnets = {p.net for p in fp.pads if p.net}
        for s, n in pk["counts"].items():
            if not n:
                continue
            full = n * (w + c)
            for rule, d in (("full", min(2.5, full)), ("half", min(2.5, full / 2))):
                lib = {"L": (x0 - d, y0, x0, y1), "R": (x1, y0, x1 + d, y1),
                       "T": (x0, y0 - d, x1, y0), "B": (x0, y1, x1, y1 + d)}[s]
                band = place_geom(box(*lib), fp.x, fp.y, fp.rot, fp.side)
                hits = []
                for o in b.footprints:
                    if o.ref == fp.ref or o.side != fp.side or cy.get(o.ref) is None:
                        continue
                    a = cy[o.ref].intersection(band).area
                    if a > 1e-4:
                        onets = {p.net for p in o.pads if p.net}
                        shared = onets & pnets
                        sig = {x for x in shared if kind.get(x, "signal") == "signal"}
                        role = ("on-escape" if sig else
                                "decap" if len(o.pads) <= 3 and onets and onets <= pnets
                                and any(kind.get(x) == "power" for x in onets) else "other")
                        hits.append(dict(ref=o.ref, pads=len(o.pads), role=role, area=round(a, 3)))
                cov = unary_union([cy[o["ref"]] for o in hits]).intersection(band).area if hits else 0.0
                rows.append(dict(ref=fp.ref, kind=pk["kind"], side=s, n=n, rule=rule, depth=round(d, 3),
                                 covered=round(cov / max(band.area, 1e-9), 3), hits=hits))
    out[bid] = rows
    print(bid, len(rows), flush=True)
json.dump(out, open(sys.argv[3], "w"), indent=1)
