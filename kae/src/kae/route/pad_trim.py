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
  axis), at least the track width on rails, grounds and tracks CURRENT_W or wider (an edge
  entry would halve a joint that carries current), centred on the edge when re-ended;
- the cut piece is a subset of the original copper, so no clearance can get worse; the gate
  (KiCad DRC on the re-opened board, errors by type and the unconnected count) is the judge
  all the same, and a worse board reverts the trims near each new violation, then all;
- not cut: a via at either end (dog-bones and fan-out stubs, escape-stage copper), pads with a
  via inside their copper (heat pads, via-in-pad: their joint is meant to be whole), a segment
  whose far end is inside the pad, and ball-grid pads (escape-stage geometry, escape.dog_bone).

`stats` counts pad entries on any board: how many end at the centre or near the edge, and
their angle to the edge's normal (an acute wedge between track and pad edge is an acid trap).

- re-ending (the CLI's default; `--no-reend` off, the bridge hook off): an end that enters more
  than 10 degrees off the edge normal turns onto the normal before the nearest edge and runs
  straight in (pad_entry.entries), every new piece checked exactly against KiCad's
  requirements (critical_space.Space.track_violations) before the DRC gate.

    python -m kae.route.pad_trim trim IN.kicad_pcb OUT.kicad_pcb [--report R.json] [--no-reend]
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
from shapely.geometry import LineString, Point

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


CURRENT_W = 0.4            # mm: a track this wide carries current whatever its net's name


def plan(text, info, overlap=0.05, tol=1e-3, legal=None, reend_deg=10.0, rails="centre"):
    """Changes [(segment, which end 'a'|'b', new end, turn or None, "cut"|"reend")] for the board text.

    Each end of a segment at a same-net pad centre, its other end outside the pad, is cut back
    to `overlap` inside the edge it crosses (the width on rails, grounds and tracks at least
    CURRENT_W wide). With `legal(net, layer, w, a, b)` (an exact clearance check), an end that
    enters more than `reend_deg` off the edge normal is re-ended instead: the track turns onto
    the normal before the nearest edge and runs straight in (pad_entry.entries); the segment
    then ends at the turn and a new piece runs from it into the pad. `rails`: "centre" leaves
    current-carrying ends at the pad centre (the physics evaluator saw rail drop and copper loss
    rise 0.1-1.3 % when they were cut a width deep), "width" cuts them a width deep."""
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
            cur = PE.current_net(s["net"]) or s["w"] >= CURRENT_W - 1e-9
            if cur and rails == "centre":
                continue
            depth = max(overlap, s["w"] if cur else 0.0)
            if legal is not None and (PE.entry_angle(g, Q, E) or 0.0) > reend_deg:
                got = None
                for tail in PE.entries(g, c, Q, s["w"], overlap, centred=cur, current=cur):
                    pts = [Q] + tail
                    ang = PE.entry_angle(g, pts[-2], pts[-1])
                    if ang is None or ang > reend_deg:
                        continue        # a direct piece that crosses another edge, or no better
                    if all(legal(s["net"], s["layer"], s["w"], a, b) for a, b in zip(pts[:-1], pts[1:])):
                        got = (s, end, tail[-1], tail[0] if len(tail) == 2 else None, "reend")
                        break
                if got is not None:
                    out.append(got)
                    break
            if math.dist(e, E) <= depth + 1e-4:
                continue
            u = ((E[0] - Q[0]) / math.dist(Q, E), (E[1] - Q[1]) / math.dist(Q, E))
            out.append((s, end, (e[0] + depth * u[0], e[1] + depth * u[1]), None, "cut"))
            break
    return out


def write(text, trims, skip=frozenset()):
    """The board text with `trims` applied (segment uuids in `skip` left as they are); a re-ended
    end adds a piece from its turn into the pad, with a uuid derived from the segment's."""
    import uuid as _uuid
    edits, extra = [], []
    for s, end, new, turn, _kind in trims:
        if s["uuid"] in skip:
            continue
        a0, b0 = s["span"]
        sp = s["sa"] if end == "a" else s["se"]
        key = "start" if end == "a" else "end"
        p = turn if turn is not None else new
        edits.append((a0 + sp[0], a0 + sp[1], f"({key} {W.fmt(p[0])} {W.fmt(p[1])})"))
        if turn is not None:
            uid = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"kae-pad-trim:{s['uuid']}:{end}"))
            locked = "(locked yes)" in text[a0:b0]
            extra.append(W.track_sexpr(s["net"], s["layer"], s["w"], turn, new, uid=uid, locked=locked))
    out, pos = [], 0
    for a, b, rep in sorted(edits):
        out.append(text[pos:a])
        out.append(rep)
        pos = b
    out.append(text[pos:])
    text = "".join(out)
    return W._insert(text, extra) if extra else text


def stats(text, info, tol=1e-3):
    """Pad entries of the board: {entries, at_centre, near_edge, perpendicular (<= 10 deg off
    the edge normal), oblique (10-45), acute (> 45: a wedge under 45 deg), overhanging (the
    entering piece adds copper beside or beyond the land, pad_entry.overhang), overhang_mm2
    (that copper, summed), track_mm}."""
    from shapely.ops import unary_union
    pads = {}
    for k, lst in _pads(info).items():
        # touching shapes of one net (a pad of several shapes, a THT pad with an SMD twin) are
        # one land: a track running from one into the other is no entry
        merged = unary_union([g for g, _, _ in lst])
        for g in getattr(merged, "geoms", [merged]):
            cs = [c for h, c, _ in lst if g.buffer(1e-6).contains(Point(c))]
            pads.setdefault(k, []).append((g, cs, None))
    segs = _segments(text)
    st = dict(entries=0, at_centre=0, near_edge=0, on_centreline=0, perpendicular=0, oblique=0, acute=0,
              overhanging=0, overhang_mm2=0.0, track_mm=round(sum(math.dist(s["a"], s["b"]) for s in segs), 3), vias=len(_vias(text)))
    for s in segs:
        for g, c, _ in pads.get((s["net"], s["layer"]), ()):
            ina, inb = g.contains(Point(s["a"])), g.contains(Point(s["b"]))
            if ina == inb:
                continue
            inside = s["a"] if ina else s["b"]
            ang = PE.entry_angle(g, s["a"], s["b"])
            st["entries"] += 1
            st["at_centre" if any(math.dist(inside, x) <= tol for x in c) else "near_edge"] += 1
            a0, b0 = PE.centreline(g)
            if LineString([a0, b0]).distance(Point(inside)) <= 0.01 if math.dist(a0, b0) > 0 else math.dist(a0, inside) <= 0.01:
                st["on_centreline"] += 1
            ov = PE.overhang(g, s["b"] if ina else s["a"], inside, s["w"])
            if ov > PE.OVER_AREA:
                st["overhanging"] += 1
                st["overhang_mm2"] = round(st["overhang_mm2"] + ov, 4)
            if ang is None:
                continue
            st["perpendicular" if ang <= 10 else "oblique" if ang <= 45 else "acute"] += 1
    return st


def _info(board):
    from kae.board import pcbnew_io
    with tempfile.TemporaryDirectory(prefix="kae-trim-") as d:
        return pcbnew_io.export_dsn(Path(board), Path(d) / "board.dsn", probes=False)


def _legal(staged, info):
    """An exact clearance check on the routed board (critical_space.Space.track_violations)."""
    from kae.board.kicad_file import load
    from .bridge import severities
    from .critical_space import Space
    sp = Space(load(staged), info, sev=severities(staged))
    return lambda net, layer, w, a, b: not sp.track_violations(net, layer, w, a, b, first=True)


def run(input_path, output_path, overlap=None, workdir=None, timeout=1800, reend=False, rails="centre", log=print,
        gate=True):
    """The DRC-gated pass: plan, write, KiCad DRC, revert what made it worse. With `reend`, entries
    more than 10 degrees off the edge normal are re-ended perpendicular (pieces checked exactly).
    Returns a report: planned/kept changes, cut and re-ended counts, DRC in and out, and the pad
    entries (stats) of the input and the output. `gate=False` (kae.route.finish): no DRC; every
    trim is written and returned as kae.route.journal entries (one per segment) in rep["_entries"]."""
    from . import constraints as CN
    from . import drc
    import time
    end_t = time.monotonic() + timeout
    inp = Path(input_path).resolve()
    wd = Path(workdir or tempfile.mkdtemp(prefix="kae-trim-"))
    wd.mkdir(parents=True, exist_ok=True)
    staged = W.stage(inp, wd / "in", "board")
    ovl = float(CN.setting("pad_entry_overlap", staged)) if overlap is None else float(overlap)
    info = _info(staged)
    text = staged.read_text(encoding="utf-8")
    trims = plan(text, info, ovl, legal=_legal(staged, info) if reend else None, rails=rails)
    rep = dict(board=str(inp), planned=len(trims), overlap=ovl, reend=bool(reend), rails=rails,
               reended=sum(1 for t in trims if t[4] == "reend"),
               cut_mm=round(sum(math.dist(t[0][t[1]], t[2]) for t in trims if t[4] == "cut"), 3),
               stats_in=stats(text, info))
    if not gate:
        from . import journal as J
        new = write(text, trims)
        J.write(new, output_path, inp)
        rep.update(kept=len(trims), stats_out=stats(new, info), gate=False,
                   _entries=J.diff_entries("trim", text, new, {t[0]["uuid"]: t[0]["uuid"] for t in trims}))
        return rep
    base_rep = drc.run(staged, wd / "in.drc.json", timeout=max(10, end_t - time.monotonic()))
    base = drc.summary(base_rep)
    rep["drc_in"] = base
    cand = wd / "out" / "board.kicad_pcb"
    cand.parent.mkdir(parents=True, exist_ok=True)
    for ext in (".kicad_pro", ".kicad_dru"):
        if staged.with_suffix(ext).exists():
            shutil.copy2(staged.with_suffix(ext), cand.with_suffix(ext))
    skip = set()
    final = None
    # reverts after a worse round: changes within 1 mm of a new violation's items, within 2.5 mm,
    # every re-end (keeping the plain cuts), then everything
    steps = [1.0, 2.5, "reend", "all"]
    for rnd in range(len(steps) + 1):
        if not trims or len(skip) >= len(trims) or end_t - time.monotonic() < 10:
            break
        cand.write_text(write(text, trims, skip), encoding="utf-8")
        r = drc.run(cand, wd / f"out.r{rnd}.json", timeout=max(10, end_t - time.monotonic()))
        s = drc.summary(r)
        worse = {t: n for t, n in s["by_type"].items() if n > base["by_type"].get(t, 0)}
        if s["unconnected"] > base["unconnected"]:
            worse["unconnected"] = s["unconnected"] - base["unconnected"]
        log(f"[pad-trim] round {rnd}: {s['errors']} errors, {s['unconnected']} unconnected "
            f"(input {base['errors']}, {base['unconnected']}); skipped {len(skip)}; worse {worse or 'none'}")
        if not worse:
            final = s
            break
        if rnd == len(steps):
            break
        step = steps[rnd]
        if step == "reend":
            skip |= {t[0]["uuid"] for t in trims if t[4] == "reend"}
        elif step == "all":
            skip |= {t[0]["uuid"] for t in trims}
        else:
            pts = [(it["pos"]["x"], it["pos"]["y"]) for v in drc.errors(r) + list(r.get("unconnected_items") or [])
                   for it in v.get("items") or [] if it.get("pos")]
            skip |= {t[0]["uuid"] for t in trims if any(math.dist(t[2], p) <= step or math.dist(t[0]["a"], p) <= step
                                                         or math.dist(t[0]["b"], p) <= step for p in pts)}
    out = Path(output_path)
    if final is not None:
        shutil.copy2(cand, out)
        rep["kept"] = sum(1 for t in trims if t[0]["uuid"] not in skip)
        rep["drc_out"] = final
        rep["stats_out"] = stats(cand.read_text(encoding="utf-8"), info)
    else:
        shutil.copy2(staged, out)
        rep["kept"] = 0
        rep["drc_out"] = base
        rep["stats_out"] = rep["stats_in"]
    for ext in (".kicad_pro", ".kicad_dru"):
        s_ = inp.with_suffix(ext)
        if s_.exists() and s_.resolve() != out.with_suffix(ext).resolve():
            shutil.copy2(s_, out.with_suffix(ext))
    return rep


def hook(output_path, project_board, workdir, timeout=900, log=print):
    """The router's last stage (bridge opts pad_trim): the pass on the routed `output_path`
    (staged with `project_board`'s project files), which it replaces when trims were kept."""
    from . import drc
    wd = Path(workdir)
    staged = drc.stage_board(output_path, project_board, wd / "routed")
    try:
        rep = run(staged, wd / "out.kicad_pcb", workdir=wd / "pass", timeout=timeout, log=log)
    except Exception as e:      # noqa: BLE001 - a post-pass never costs the routed board
        log(f"[pad-trim] skipped: {type(e).__name__}: {e}")
        return dict(error=f"{type(e).__name__}: {e}")
    if rep.get("kept"):
        Path(output_path).write_text((wd / "out.kicad_pcb").read_text(encoding="utf-8"), encoding="utf-8")
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
    t.add_argument("--rails", choices=("centre", "width"), default="centre",
                   help="rails, grounds and wide tracks: keep their centre ends (default) or cut a width deep")
    t.add_argument("--no-reend", action="store_true",
                   help="only shorten along each track's axis (no perpendicular re-ending)")
    s = sub.add_parser("stats")
    s.add_argument("board")
    a = ap.parse_args(argv)
    if a.cmd == "trim":
        rep = run(a.input, a.output, a.overlap, a.workdir, a.timeout, reend=not a.no_reend, rails=a.rails)
        if a.report:
            Path(a.report).write_text(json.dumps(rep, indent=1))
        print(json.dumps(rep))
    else:
        print(json.dumps(stats(Path(a.board).read_text(encoding="utf-8"), _info(a.board))))


if __name__ == "__main__":
    main()
