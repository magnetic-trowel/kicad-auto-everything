# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit the rule port: Space's required clearance from pads against KiCad's DRC, with test copper.

    python rule_port_audit.py BOARD.kicad_pcb OUT.json [--pads 80] [--seed 0]

The board's tracks and vias are removed first (--keep-routing keeps them). For a sample of pads on the outer layers and one representative net of each routing class
(another net than the pad's), a short test track of the class width is laid at Space's
requirement (critical_space.Space.need) plus 3 um from the pad ("lax" run), and in a second
board at the requirement minus 10 um ("strict" run). KiCad's DRC on each board is the referee:
a lax-run violation between a test track and its pad means Space allows less than KiCad needs
(the port is too lax); no violation in the strict run means Space asks for more than KiCad.
Writes the pairs and KiCad's descriptions (with the rule it names) to OUT.json. Run it under
the queue (tools/kaeq) with KiCad available."""
import argparse
import json
import math
import random
import sys
import tempfile
from pathlib import Path


BATCH = 40


def _tracks(sp, plan, pads, gap_delta, nets=()):
    from shapely.geometry import LineString
    from kae.route import critical_write as W
    out, meta = [], {}
    want_net = set(nets)
    cu = sp.cu
    outer = {cu[0], cu[-1]}
    for it in pads:
        reps = [(rc, rc.rep if rc.rep != it.net else rc.rep2) for rc in plan.classes.values()]
        reps += [(plan.classes[plan.net_class[n]], n) for n in want_net if n in plan.net_class and n != it.net]
        for rc, net in reps:
            if not net:
                continue
            layer = next((l for l in sorted(it.layers) if l in outer), None)
            if layer is None:
                continue
            nd = sp.need(it, net, "track", layer)
            if nd is None:
                continue
            w = rc.widths[layer]
            c = it.pos or (it.geom.centroid.x, it.geom.centroid.y)
            best = None
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                far = (c[0] + 50 * dx, c[1] + 50 * dy)
                edge = LineString([c, far]).intersection(it.geom.boundary)
                if edge.is_empty:
                    continue
                pts = [(q[0], q[1]) for g in getattr(edge, "geoms", [edge]) for q in g.coords]
                e = max(pts, key=lambda q: math.dist(q, c))
                off = nd + gap_delta + w / 2
                for _ in range(4):           # land the track's edge at the gap from the real pad shape
                    m = (e[0] + off * dx, e[1] + off * dy)
                    a, b = (m[0] - 0.1 * dy, m[1] - 0.1 * dx), (m[0] + 0.1 * dy, m[1] + 0.1 * dx)
                    seg = LineString([a, b])
                    err = (it.geom.distance(seg) - w / 2) - (nd + gap_delta)
                    if abs(err) < 1e-4:
                        break
                    off -= err
                crowd = sum(1 for x in sp.query(layer, seg.bounds, 0.6) if x is not it and x.net != net
                            and x.geom.distance(seg) < x.r + w / 2 + 0.6)
                d_true = it.geom.distance(seg) - w / 2
                if best is None or crowd < best[0]:
                    best = (crowd, a, b, d_true)
            if best is None:
                continue
            u = W.new_uuid()
            out.append((net, layer, w, best[1], best[2], u, False))
            meta[u] = dict(pad=f"{it.owner[0]}.{it.owner[1]}", pad_uuid=it.uuid, pad_net=it.net, net=net,
                           layer=layer, need=round(nd, 4), gap=round(best[3], 4), cls=it.cls)
    return out, meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("out")
    ap.add_argument("--pads", type=int, default=80)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--refs", default="", help="parts whose pads are always tested (comma-separated)")
    ap.add_argument("--keep-routing", action="store_true", help="test on the board as it is (default: tracks and vias removed)")
    ap.add_argument("--nets", default="", help="test-copper nets besides each class's representative")
    a = ap.parse_args(argv)
    from kae.board import pcbnew_io
    from kae.board.kicad_file import load
    from kae.route import critical_write as W
    from kae.route import drc
    from kae.route.bridge import severities
    from kae.route.critical_space import Space
    src = Path(a.board).resolve()
    if not a.keep_routing:
        # test copper among the board's own tracks meets them first (KiCad then reports the short,
        # not the pad clearance): audit on the bare placement
        bare = Path(a.out).with_suffix(".bare.kicad_pcb")
        W.edit(src, bare, remove=[r["uuid"] for r in W.routing(src)])
        for ext in (".kicad_pro", ".kicad_dru"):
            if src.with_suffix(ext).exists():
                bare.with_suffix(ext).write_bytes(src.with_suffix(ext).read_bytes())
        src = bare
    with tempfile.TemporaryDirectory() as d:
        info = pcbnew_io.export_dsn(src, Path(d) / "b.dsn")
    sp = Space(load(src), info, sev=severities(src))
    pads = [it for it in sp.pads if it.kind == "pad" and it.uuid]
    random.Random(a.seed).shuffle(pads)
    want = set(filter(None, a.refs.split(",")))
    pads = [it for it in pads if it.owner[0] in want] + [it for it in pads if it.owner[0] not in want]
    pads = pads[:a.pads]
    res = {}
    for run, delta in (("lax", 0.003), ("strict", -0.01)):
        tracks, meta = _tracks(sp, sp.plan, pads, delta, [n for n in a.nets.split(",") if n])
        viol = []
        # KiCad stops reporting a check type past its error limit, so a board with many violating
        # test tracks hides some: at most BATCH test tracks per DRC run
        for k in range(0, len(tracks), BATCH):
            with tempfile.TemporaryDirectory(dir=src.parent) as d:
                b = Path(d) / "board.kicad_pcb"
                W.append_items(src, b, tracks=tracks[k:k + BATCH])
                for ext in (".kicad_pro", ".kicad_dru"):
                    if src.with_suffix(ext).exists():
                        b.with_suffix(ext).write_bytes(src.with_suffix(ext).read_bytes())
                viol += drc.run(b, Path(d) / "drc.json").get("violations") or []
        rep = dict(violations=viol)
        hits = {}
        for v in rep.get("violations") or []:
            if v.get("severity") not in ("error", "warning"):
                continue
            ids = [i.get("uuid") for i in v.get("items") or []]
            for u in ids:
                if u in meta and meta[u]["pad_uuid"] in ids:
                    hits.setdefault(u, []).append(dict(type=v["type"], severity=v["severity"],
                                                       description=v["description"]))
        res[run] = dict(tested=len(meta), pairs=[dict(meta[u], kicad=hits.get(u, [])) for u in meta])
    # only pairs whose test copper landed where intended count (the gap within 1 um of its aim)
    lax = [p for p in res["lax"]["pairs"] if p["kicad"] and p["gap"] >= p["need"] + 0.002]
    strict_quiet = [p for p in res["strict"]["pairs"] if not p["kicad"] and p["gap"] <= p["need"] - 0.009]
    summary = dict(board=str(src), lax_tested=res["lax"]["tested"], too_lax=len(lax),
                   strict_tested=res["strict"]["tested"], too_strict=len(strict_quiet),
                   too_lax_pairs=lax[:40], too_strict_pairs=strict_quiet[:20])
    Path(a.out).write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: summary[k] for k in ("lax_tested", "too_lax", "strict_tested", "too_strict")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
