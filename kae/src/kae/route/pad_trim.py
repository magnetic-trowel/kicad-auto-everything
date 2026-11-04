# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shorten tracks that run to a pad's centre back to the pad's edge, DRC-gated.

Freerouting ends every trace at a pin's exact centre: a pin's connection shape is its centre
point (DrillItem.getTraceConnectionShape) and a trace touches a pin only when its end equals
that point (Trace.getNormalContacts). Its pin-exit rule (pin_edge_to_turn_dist, a straight run
out of a box pad's short side before the first turn) is switched off while the autorouter
inserts a connection (FoundConnectionInserter) and nothing in the DSN or the rules file asks
for an end on the pad's edge. So this pass works on the routed board instead:

- a segment with one end at a same-net pad's centre on its layer and the other end outside
  the pad's copper is cut back to `pad_entry_overlap` inside the edge it crosses (along its own
  axis), at least the track width on rails and grounds (an edge entry would halve a joint that
  carries current);
- the cut piece is a subset of the original copper, so no clearance can get worse; the gate
  (KiCad DRC on the re-opened board, errors by type and the unconnected count) is the judge
  all the same, and a worse board reverts the trims near each new violation, then all;
- not cut: a via at either end (dog-bones and fan-out stubs, escape-stage copper), pads with a
  via inside their copper (heat pads, via-in-pad: their joint is meant to be whole), a segment
  whose far end is inside the pad, and ball-grid pads (escape-stage geometry, escape.dog_bone).

`stats` counts pad entries on any board: how many end at the centre or near the edge, and
their angle to the edge's normal (an acute wedge between track and pad edge is an acid trap).

    python -m kae.route.pad_trim trim IN.kicad_pcb OUT.kicad_pcb [--report R.json]
    python -m kae.route.pad_trim stats BOARD.kicad_pcb
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import tempfile
from pathlib import Path

from shapely import STRtree
from shapely.geometry import Point

from . import critical_write as W
from . import pad_entry as PE

NUM = r"(-?[0-9.]+(?:e-?\d+)?)"
BALL_GRID_MIN = 9          # a footprint with this many round SMD pads is a ball grid (escape stage)


def _segments(text):
    out = []
    for _h, a, b in W._blocks(text, ("segment",)):
        blk = text[a:b]
        s = re.search(r"\(start " + NUM + " " + NUM + r"\)", blk)
        e = re.search(r"\(end " + NUM + " " + NUM + r"\)", blk)
        w = re.search(r"\(width " + NUM + r"\)", blk)
        l = re.search(r'\(layer\s+"([^"]+)"\)', blk)
        n = re.search(r'\(net\s+("(?:[^"\\]|\\.)*"|\S+?)\)', blk)
        if not (s and e and w and l):
            continue
        net = n.group(1) if n else ""
        if net.startswith('"'):
            net = json.loads(net)
        out.append(dict(a=(float(s.group(1)), float(s.group(2))), b=(float(e.group(1)), float(e.group(2))),
                        w=float(w.group(1)), layer=l.group(1), net=net, uuid=W._uuid_of(blk), span=(a, b),
                        sa=s.span(), se=e.span()))
    return out


def _vias(text):
    out = []
    for _h, a, b in W._blocks(text, ("via",)):
        blk = text[a:b]
        m = re.search(r"\(at " + NUM + " " + NUM + r"\)", blk)
        if m:
            out.append((float(m.group(1)), float(m.group(2))))
    return out


def _round(g):
    x0, y0, x1, y1 = g.bounds
    w, h = x1 - x0, y1 - y0
    return abs(w - h) < 1e-3 and abs(g.area - math.pi * w * h / 4) < 0.03 * g.area


def _pads(info, balls=True):
    """(net, layer) -> [(copper, centre, record)] of the board's pads (export_dsn info); without
    `balls`, not the pads of ball grids (footprints with BALL_GRID_MIN round SMD pads)."""
    from .constraints import _pad_shapes
    shapes, nball = [], {}
    for pd in info.get("pads") or []:
        if not pd.get("net") or not pd.get("pos"):
            continue
        _dsn, real = _pad_shapes(pd)
        real = {l: g for l, g in (real or {}).items() if g is not None and not g.is_empty}
        fp = pd.get("fp_index", pd.get("ref"))
        if pd.get("attr") == "smd" and real and _round(next(iter(real.values()))):
            nball[fp] = nball.get(fp, 0) + 1
        shapes.append((pd, fp, real))
    out = {}
    for pd, fp, real in shapes:
        if not balls and nball.get(fp, 0) >= BALL_GRID_MIN:
            continue
        for l, g in real.items():
            out.setdefault((pd["net"], l), []).append((g, (float(pd["pos"][0]), float(pd["pos"][1])), pd))
    return out


def plan(text, info, overlap=0.05, tol=1e-3):
    """Trims [(segment, which end 'a'|'b', new point)] for the board text."""
    pads = _pads(info, balls=False)
    vias = _vias(text)
    vtree = STRtree([Point(v) for v in vias]) if vias else None
    segs = _segments(text)
    out = []
    for s in segs:
        cands = pads.get((s["net"], s["layer"]))
        if not cands:
            continue
        for end, other in (("a", "b"), ("b", "a")):
            E, Q = s[end], s[other]
            if vtree is not None and (len(vtree.query(Point(E).buffer(tol))) or len(vtree.query(Point(Q).buffer(tol)))):
                continue
            hit = next(((g, c) for g, c, _ in cands if math.dist(c, E) <= tol), None)
            if hit is None:
                continue
            g, c = hit
            if g.contains(Point(Q)) or (vtree is not None and len(vtree.query(g, predicate="intersects"))):
                continue
            e = PE.crossing(g, Q, E)
            if e is None:
                continue
            depth = max(overlap, s["w"] if PE.current_net(s["net"]) else 0.0)
            run = math.dist(e, E)
            if run <= depth + 1e-4:
                continue
            u = ((E[0] - Q[0]) / math.dist(Q, E), (E[1] - Q[1]) / math.dist(Q, E))
            new = (e[0] + depth * u[0], e[1] + depth * u[1])
            out.append((s, end, new))
            break
    return out


def write(text, trims, skip=frozenset()):
    """The board text with `trims` applied (segment uuids in `skip` left as they are)."""
    edits = []
    for s, end, new in trims:
        if s["uuid"] in skip:
            continue
        a0, b0 = s["span"]
        sp = s["sa"] if end == "a" else s["se"]
        key = "start" if end == "a" else "end"
        edits.append((a0 + sp[0], a0 + sp[1], f"({key} {W.fmt(new[0])} {W.fmt(new[1])})"))
    out, pos = [], 0
    for a, b, rep in sorted(edits):
        out.append(text[pos:a])
        out.append(rep)
        pos = b
    out.append(text[pos:])
    return "".join(out)


def stats(text, info, tol=1e-3):
    """Pad entries of the board: {entries, at_centre, near_edge, perpendicular (<= 10 deg off
    the edge normal), oblique (10-45), acute (> 45: a wedge under 45 deg), track_mm}."""
    pads = _pads(info)
    segs = _segments(text)
    st = dict(entries=0, at_centre=0, near_edge=0, perpendicular=0, oblique=0, acute=0,
              track_mm=round(sum(math.dist(s["a"], s["b"]) for s in segs), 3))
    for s in segs:
        for g, c, _ in pads.get((s["net"], s["layer"]), ()):
            ina, inb = g.contains(Point(s["a"])), g.contains(Point(s["b"]))
            if ina == inb:
                continue
            inside = s["a"] if ina else s["b"]
            ang = PE.entry_angle(g, s["a"], s["b"])
            st["entries"] += 1
            st["at_centre" if math.dist(inside, c) <= tol else "near_edge"] += 1
            if ang is None:
                continue
            st["perpendicular" if ang <= 10 else "oblique" if ang <= 45 else "acute"] += 1
    return st


def _info(board):
    from kae.board import pcbnew_io
    with tempfile.TemporaryDirectory(prefix="kae-trim-") as d:
        return pcbnew_io.export_dsn(Path(board), Path(d) / "board.dsn", probes=False)


def run(input_path, output_path, overlap=None, workdir=None, timeout=1800, log=print):
    """The DRC-gated pass. Returns a report."""
    from . import constraints as CN
    from . import drc
    inp = Path(input_path).resolve()
    wd = Path(workdir or tempfile.mkdtemp(prefix="kae-trim-"))
    wd.mkdir(parents=True, exist_ok=True)
    staged = W.stage(inp, wd / "in", "board")
    ovl = float(CN.setting("pad_entry_overlap", staged)) if overlap is None else float(overlap)
    info = _info(staged)
    text = staged.read_text(encoding="utf-8")
    trims = plan(text, info, ovl)
    rep = dict(board=str(inp), planned=len(trims), overlap=ovl,
               cut_mm=round(sum(math.dist(s[e], n) for s, e, n in trims), 3))
    base_rep = drc.run(staged, wd / "in.drc.json", timeout=timeout)
    base = drc.summary(base_rep)
    rep["drc_in"] = base
    cand = wd / "out" / "board.kicad_pcb"
    cand.parent.mkdir(parents=True, exist_ok=True)
    for ext in (".kicad_pro", ".kicad_dru"):
        if staged.with_suffix(ext).exists():
            shutil.copy2(staged.with_suffix(ext), cand.with_suffix(ext))
    skip = set()
    final = None
    for rnd in range(3):
        if not trims or len(skip) >= len(trims):
            break
        cand.write_text(write(text, trims, skip), encoding="utf-8")
        r = drc.run(cand, wd / f"out.r{rnd}.json", timeout=timeout)
        s = drc.summary(r)
        worse = {t: n for t, n in s["by_type"].items() if n > base["by_type"].get(t, 0)}
        if s["unconnected"] > base["unconnected"]:
            worse["unconnected"] = s["unconnected"] - base["unconnected"]
        log(f"[pad-trim] round {rnd}: {s['errors']} errors, {s['unconnected']} unconnected "
            f"(input {base['errors']}, {base['unconnected']}); skipped {len(skip)}; worse {worse or 'none'}")
        if not worse:
            final = s
            break
        if rnd == 2:
            break
        # revert the trims near each new violation's items; at the last chance, all of them
        pts = [(it["pos"]["x"], it["pos"]["y"]) for v in drc.errors(r) + list(r.get("unconnected_items") or [])
               for it in v.get("items") or [] if it.get("pos")]
        near = {t[0]["uuid"] for t in trims if any(math.dist(t[2], p) <= 1.0 or math.dist(t[0]["a"], p) <= 1.0
                                                    or math.dist(t[0]["b"], p) <= 1.0 for p in pts)}
        skip |= near if rnd == 0 and near - skip else {t[0]["uuid"] for t in trims}
    out = Path(output_path)
    if final is not None:
        shutil.copy2(cand, out)
        rep["kept"] = len(trims) - len(skip)
        rep["drc_out"] = final
    else:
        shutil.copy2(staged, out)
        rep["kept"] = 0
        rep["drc_out"] = base
    for ext in (".kicad_pro", ".kicad_dru"):
        s_ = inp.with_suffix(ext)
        if s_.exists() and s_.resolve() != out.with_suffix(ext).resolve():
            shutil.copy2(s_, out.with_suffix(ext))
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kae.route.pad_trim", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trim")
    t.add_argument("input")
    t.add_argument("output")
    t.add_argument("--overlap", type=float)
    t.add_argument("--workdir")
    t.add_argument("--report")
    t.add_argument("--timeout", type=int, default=1800)
    s = sub.add_parser("stats")
    s.add_argument("board")
    a = ap.parse_args(argv)
    if a.cmd == "trim":
        rep = run(a.input, a.output, a.overlap, a.workdir, a.timeout)
        if a.report:
            Path(a.report).write_text(json.dumps(rep, indent=1))
        print(json.dumps(rep))
    else:
        print(json.dumps(stats(Path(a.board).read_text(encoding="utf-8"), _info(a.board))))


if __name__ == "__main__":
    main()
