# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Several routings of one board side by side as an interactive page: tracks by copper layer, pads, vias,
part outlines and pour outlines (fills are not drawn), with synced zoom and pan, layer toggles and a net
highlighted across every version on hover.

    python tools/research/physics/route_view/route_view.py OUT.html --title "Boost" \
        --version human="Human layout"=human/board.kicad_pcb \
        --version fr="Freerouting alone"=runs/fr.kicad_pcb ... [--meta META.json]

META.json (optional): {"note": "...", "rerouted": [nets highlighted by the 'routed by kae' toggle],
"rows": {"loss": ["53.6 mW", ...], ...}, "row_labels": [["loss", "Copper loss", 1], ...]} where each row has
one value per version and a 1 marks rows whose smallest number is highlighted.
The page is template.html beside this file with the data inlined."""
import argparse
import json
import math
from pathlib import Path

from kae.board import transform as T
from kae.board.kicad_file import load


def r(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def poly_path(g):
    out = []
    for p in getattr(g, "geoms", [g]):
        if p.is_empty or not hasattr(p, "exterior"):
            continue
        for ring in [p.exterior, *p.interiors]:
            cs = list(ring.coords)
            out.append("M" + "L".join(f"{r(x)} {r(y)}" for x, y in cs) + "Z")
    return "".join(out)


def pad_svg(fp, p):
    x, y = T.pad_xy(fp, p)
    w, h = p.size
    if p.shape == "circle" or (p.shape == "oval" and abs(w - h) < 1e-6):
        return f'<circle cx="{r(x)}" cy="{r(y)}" r="{r(w / 2)}"/>'
    a = T.pad_angle(fp, p)
    rx = min(w, h) / 2 if p.shape == "oval" else (min(w, h) * (p.rratio or 0) if p.shape == "roundrect" else 0)
    return (f'<rect x="{r(-w / 2)}" y="{r(-h / 2)}" width="{r(w)}" height="{r(h)}" rx="{r(rx)}" '
            f'transform="translate({r(x)} {r(y)}) rotate({r(-a)})"/>')


def draw(path, layers, nets):
    b = load(path)
    lay_idx = {n: i for i, n in enumerate(layers)}
    bs = [g.bounds for g in b.outline] or [(fp.x, fp.y, fp.x, fp.y) for fp in b.footprints]
    box = (min(q[0] for q in bs), min(q[1] for q in bs), max(q[2] for q in bs), max(q[3] for q in bs))
    parts = {"outline": "".join(poly_path(g) for g in b.outline)}
    # pours: outlines per layer
    pours = {L: [] for L in layers}
    for z in b.zones:
        for L in z.layers:
            if L in pours:
                pours[L].append(poly_path(z.outline))
    # tracks per layer, grouped by net
    trk = {L: {} for L in layers}
    length = 0.0
    for t in b.tracks:
        if t.layer not in trk:
            continue
        n = nets.setdefault(t.net or "", len(nets))
        pts = [t.start, t.mid, t.end] if getattr(t, "mid", None) else [t.start, t.end]
        length += sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
        d = "M" + "L".join(f"{r(px)} {r(py)}" for px, py in pts)
        trk[t.layer].setdefault((n, r(t.width)), []).append(d)
    tracks = {L: "".join(f'<path data-n="{n}" stroke-width="{w}" d="{"".join(ds)}"/>' for (n, w), ds in g.items())
              for L, g in trk.items()}
    vias = "".join(f'<circle data-n="{nets.setdefault(v.net or "", len(nets))}" cx="{r(v.x)}" cy="{r(v.y)}" '
                   f'r="{r(v.size / 2)}"/>' for v in b.vias)
    pads_f, pads_b, fps = [], [], []
    for fp in b.footprints:
        for p in fp.pads:
            if p.kind == "np_thru_hole" or not p.size or min(p.size) <= 0:
                continue
            s = pad_svg(fp, p)
            n = nets.get(p.net, None) if p.net else None
            if n is None and p.net:
                n = nets.setdefault(p.net, len(nets))
            s = s[:-2] + (f' data-n="{n}"/>' if n is not None else "/>")
            (pads_b if fp.side == "B" and p.kind == "smd" else pads_f).append(s)
        try:
            from shapely.ops import unary_union
            cy = T.courtyard(fp)
            cy = unary_union(cy) if isinstance(cy, list) and cy else (None if isinstance(cy, list) else cy)
        except Exception:
            cy = None
        if cy is not None and not cy.is_empty:
            cx0, cy0, cx1, cy1 = cy.bounds
            big = (cx1 - cx0) * (cy1 - cy0) > 12
            fps.append(f'<g><title>{fp.ref} {fp.value}</title><path d="{poly_path(cy)}"/>'
                       + (f'<text x="{r((cx0 + cx1) / 2)}" y="{r((cy0 + cy1) / 2)}">{fp.ref}</text>' if big else "")
                       + "</g>")
    return dict(box=box, outline=parts["outline"], pours={L: "".join(v) for L, v in pours.items()},
                tracks=tracks, vias=vias, pads_f="".join(pads_f), pads_b="".join(pads_b), fps="".join(fps),
                stats=dict(length_mm=round(length), vias=len(b.vias), segments=len(b.tracks)))




def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--title", default="Board")
    ap.add_argument("--version", action="append", required=True, help="KEY=LABEL=PATH, in display order")
    ap.add_argument("--meta")
    a = ap.parse_args(argv)
    vs_in = [v.split("=", 2) for v in a.version]
    b0 = load(vs_in[0][2])
    layers = [L for L in b0.layers if L.endswith(".Cu")]
    nets = {}
    vs = [dict(name=k, label=lab, **draw(p, layers, nets)) for k, lab, p in vs_in]
    data = [dict(key="board", title=a.title, layers=layers, variants=vs, parts=len(b0.footprints),
                 nets=[n for n, _ in sorted(nets.items(), key=lambda kv: kv[1])])]
    meta = json.loads(Path(a.meta).read_text()) if a.meta else {}
    meta.setdefault("note", "")
    meta.setdefault("rerouted", [])
    meta.setdefault("rows", {})
    page = (Path(__file__).with_name("template.html").read_text()
            .replace("__TITLE__", a.title)
            .replace("__DATA__", json.dumps(data).replace("</", "<\/"))
            .replace("__META__", json.dumps({"board": meta}).replace("</", "<\/")))
    Path(a.out).write_text(page)


if __name__ == "__main__":
    main()
