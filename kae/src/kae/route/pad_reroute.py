# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-route the tails of oblique pad entries so they arrive along the edge normal, DRC-gated.

A track that crosses a pad edge at an angle leaves an acute wedge between its side and the pad
edge: an acid trap, where etchant pools and over-etches (acute copper angles are flagged in
docs/topics/rules/rf.md, RF-08 "acute angles banned", and as a cleanup metric in
docs/topics/routing/autorouter-skepticism.md). kae.route.pad_trim could re-end only 47 of 2,113
such ends by changing the last segment, because there was no room to turn outside the pad. This
pass rips up the connection's tail and routes it again with kae's grid router:

1. **Entries.** A segment with one end inside a same-net pad's copper on its layer and the other
   outside. It is re-routed when it enters more than ENTRY_DEG (10 deg) off the edge normal, or
   when its copper beside the pad (sliver risk: a centre-aimed track wider than the land, or one
   crossing a corner) is over SLIVER_X times what a perpendicular entry leaves.
2. **Release point.** Walk the track from the pad along the chain of segments (same layer, same
   width, no other branch): stop at the first via, junction, width change, arc or other pad
   within R, else at the point R along the path. R = max(3 widths, 1 mm), then 2 and 4 mm.
3. **Target.** pad_entry.approach_targets: the approach point a stub (at least one width)
   outside the edge the release point faces, and the end `pad_entry_overlap` inside along the
   normal; rails, grounds and tracks 0.4 mm or wider take the edge's middle a width deep.
4. **Route.** critical_grid.GridRouter from the release point to the approach point, on the
   tail's layer, at the tail's width, no vias, the pad kept out of the search (the track
   reaches it only by the straight final piece). On a board whose tracks are 45/90-degree
   (OCTO_SHARE of their length), every new piece must be too (doglegs, checked exactly).
5. **Accept** only if every piece is exactly legal (critical_space.Space.track_violations),
   the tail is no longer than LEN_ABS + LEN_REL x the old one, and then KiCad DRC on the whole
   board is no worse (by type, and the unconnected count); worse boards revert stepwise
   (changes within 1 mm, 2.5 mm of a new violation, then all). Otherwise the old tail stays.

Not touched: pads of ball grids, pads with a via in their copper (heat pads, via-in-pad), an
entry segment whose outside end is a via (dog-bones, fan-out stubs: escape-stage copper),
locked tracks, and arcs.

    python -m kae.route.pad_reroute IN.kicad_pcb OUT.kicad_pcb [--report R.json]
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
import time
import uuid as _uuid
from pathlib import Path

from shapely import STRtree
from shapely.geometry import LineString, Point

from . import critical_write as W
from . import pad_entry as PE
from . import pad_trim as PT

ENTRY_DEG = 10.0
SLIVER_X = 2.0
RELEASE = (None, 2.0, 4.0)       # None = max(3 widths, 1 mm)
LEN_ABS, LEN_REL = 1.0, 0.2
OCTO_SHARE = 0.9
TOL = 1e-3


def _key(p):
    return (round(p[0], 4), round(p[1], 4))


def _arcs(text):
    import re
    out = []
    for _h, a, b in W._blocks(text, ("arc",)):
        blk = text[a:b]
        for k in ("start", "end"):
            m = re.search(r"\(" + k + " " + PT.NUM + " " + PT.NUM + r"\)", blk)
            if m:
                out.append((float(m.group(1)), float(m.group(2))))
    return out


def octilinear_share(segs):
    """Share of track length at a multiple of 45 degrees."""
    tot = ok = 0.0
    for s in segs:
        L = math.dist(s["a"], s["b"])
        if L < 1e-6:
            continue
        ang = math.degrees(math.atan2(s["b"][1] - s["a"][1], s["b"][0] - s["a"][0])) % 45.0
        tot += L
        if min(ang, 45.0 - ang) < 0.5:
            ok += L
    return ok / tot if tot else 0.0


def _is_octo(a, b):
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 45.0
    return min(ang, 45.0 - ang) < 0.5 or math.dist(a, b) < 1e-6


def doglegs(a, b):
    """The two 45/90-degree two-piece paths from a to b (diagonal first, straight first)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    m = min(abs(dx), abs(dy))
    sx, sy = math.copysign(1, dx), math.copysign(1, dy)
    p1 = (a[0] + sx * m, a[1] + sy * m)
    p2 = (b[0] - sx * m, b[1] - sy * m)
    return [[a, p1, b], [a, p2, b]]


def sliver_ratio(pad, a, b, w):
    """Copper of piece a -> b (outside end a, inside end b) beside the pad, within a width of it,
    over what a perpendicular entry of the same width leaves (w x w)."""
    seg = LineString([a, b]).buffer(w / 2, quad_segs=8)
    near = seg.intersection(pad.buffer(w, quad_segs=8)).difference(pad)
    return near.area / (w * w) if w > 0 else 0.0


def chain(segs_by_node, start_seg, pad_end, R, stop_nodes, at_pad=lambda q: False, taps=(), tol=TOL):
    """Walk from the pad end of `start_seg` outward: [(segment, from point, to point)] and the
    release point. Stops at a node in `stop_nodes` (vias, junctions, arcs, other pads), at a
    width change or a node of degree != 2, or R along the path (the release point then splits a
    segment). A track or via of the net that meets a piece between its ends (`taps`: points of
    the net on the layer, a T-junction) releases there too. Returns (pieces, release, kind) with
    kind "node" or "split"."""
    pieces, dist = [], 0.0
    s, p = start_seg, pad_end
    w = s["w"]
    seen = set()
    while True:
        q = s["b"] if math.dist(s["a"], p) <= tol else s["a"]
        L = math.dist(p, q)
        if L > tol and taps:
            ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
            hits = []
            for t in taps:
                d = (t[0] - p[0]) * ux + (t[1] - p[1]) * uy
                if tol < d < L - tol and abs((t[0] - p[0]) * uy - (t[1] - p[1]) * ux) <= s["w"] / 2:
                    hits.append(d)
            if hits and dist + min(hits) < R:
                d = min(hits)
                r = (p[0] + d * ux, p[1] + d * uy)
                pieces.append((s, p, r))
                return pieces, r, "split"
        if dist + L >= R - 1e-9:
            t = (R - dist) / L if L > 0 else 0.0
            r = (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
            pieces.append((s, p, r))
            return pieces, r, "split"
        pieces.append((s, p, q))
        dist += L
        seen.add(s["uuid"])
        k = _key(q)
        nxt = [x for x in segs_by_node.get((s["net"], s["layer"], k), ()) if x["uuid"] not in seen]
        if k in stop_nodes or at_pad(q) or len(nxt) != 1 or nxt[0]["w"] != w or nxt[0].get("locked"):
            return pieces, q, "node"
        s, p = nxt[0], q


def plan(text, info, sp, gr, overlap=0.05, log=print, deadline=None, rails="middle", target="centreline"):
    """Re-routes [(change dict)] and per-entry outcomes {reason: count}. `sp` is a Space of the
    board (updated as changes are accepted), `gr` a GridRouter on it."""
    from .critical_grid import Anchor
    pads = PT._pads(info, balls=False)
    vias = PT._vias(text)
    vtree = STRtree([Point(v) for v in vias]) if vias else None
    segs = PT._segments(text)
    for s in segs:
        s["locked"] = "(locked yes)" in text[s["span"][0]:s["span"][1]]
    octo = octilinear_share(segs) >= OCTO_SHARE
    by_node = {}
    for s in segs:
        for p in (s["a"], s["b"]):
            by_node.setdefault((s["net"], s["layer"], _key(p)), []).append(s)
    stop = {_key(v) for v in vias} | {_key(p) for p in _arcs(text)}
    taps = {}
    for x in segs:
        for p in (x["a"], x["b"]):
            taps.setdefault((x["net"], x["layer"]), []).append(p)
    allpads = PT._pads(info)
    pad_nodes = {}
    for (net, layer), lst in allpads.items():
        for g, c, _ in lst:
            pad_nodes.setdefault((net, layer), []).append(g)
    items = {it.uuid: it for it in sp.existing if it.kind == "track" and it.uuid}
    outcome = {}
    changes = []
    done = set()

    def note(k):
        outcome[k] = outcome.get(k, 0) + 1

    for s in segs:
        if deadline is not None and time.monotonic() > deadline:
            note("time")
            break
        if s["uuid"] in done or s["locked"]:
            continue
        for g, c, pd in pads.get((s["net"], s["layer"]), ()):
            ina, inb = g.contains(Point(s["a"])), g.contains(Point(s["b"]))
            if ina == inb:
                continue
            E, Q = (s["a"], s["b"]) if ina else (s["b"], s["a"])
            # a pad of several shapes (a castellated or custom pad, a THT pad with an SMD twin):
            # its whole copper is the target, so no route crosses a sister shape on its way in
            sis = [h for h in pad_nodes.get((s["net"], s["layer"]), ()) if h is not g and h.intersects(g.buffer(0.01))]
            if sis:
                from shapely.ops import unary_union
                gu = unary_union([g] + sis)
                g = gu if gu.geom_type == "Polygon" else g
                if g.contains(Point(Q)):
                    continue                     # from one shape of the land into another
            ang = PE.entry_angle(g, Q, E)
            w = s["w"]
            sl = sliver_ratio(g, Q, E, w)
            if (ang is None or ang <= ENTRY_DEG) and sl <= SLIVER_X:
                continue
            note("candidates")
            if vtree is not None and (len(vtree.query(Point(Q).buffer(TOL))) or len(vtree.query(g, predicate="intersects"))):
                note("skip_via")
                break
            cur = PE.current_net(s["net"]) or w >= PT.CURRENT_W - 1e-9
            if cur and rails == "centre":
                note("skip_rail")
                break
            got = None
            why = "no_route"
            for R0 in RELEASE:
                R = max(3 * w, 1.0) if R0 is None else R0
                others = [h for h in pad_nodes.get((s["net"], s["layer"]), ()) if not h.within(g.buffer(0.01))]
                pieces, rel, kind = chain(by_node, s, E, R, stop,
                                          at_pad=lambda q: any(h.distance(Point(q)) < 1e-6 for h in others),
                                          taps=taps.get((s["net"], s["layer"]), ()))
                if any(x[0]["uuid"] in done for x in pieces):
                    why = "overlap"
                    break
                if g.distance(Point(rel)) < w:
                    why = "release_at_pad"
                    continue
                old_len = sum(math.dist(p, q) for _, p, q in pieces)
                if target == "centreline":
                    # rule D: end on the long centre line, the crossing piece square to the outline;
                    # every candidate is routed and the shortest legal one kept
                    tgts = [(a, end, None, kind) for a, end, kind in PE.centreline_targets(g, rel, w)]
                else:
                    tgts = PE.approach_targets(g, c, rel, w, overlap, current=cur)
                if not tgts:
                    why = "no_target"
                    continue
                best = None
                for a, end, u, facing in tgts:
                    rt = _route(gr, sp, Anchor, s["net"], s["layer"], w, rel, a, g)
                    if rt is None:
                        continue
                    pts = rt
                    if octo:
                        pts = _octo(sp, s["net"], s["layer"], w, pts)
                        if pts is None or any(g.distance(LineString([p, q])) < w / 2 - 1e-6
                                              for p, q in zip(pts[:-1], pts[1:])):
                            why = "style"
                            continue
                    if target != "centreline" and any(c2["net"] == s["net"] and c2["layer"] == s["layer"] and not c2.get("joined")
                           and _key(c2["pts"][-2]) == _key(a) and _key(c2["pts"][-1]) == _key(end) for c2 in changes):
                        # a second track into the same land meets the first at its approach point
                        # (no doubled final piece)
                        pts = pts if len(pts) >= 2 else pts + [a]
                        got = dict(id=s["uuid"], net=s["net"], layer=s["layer"], w=w, pieces=pieces, release=rel,
                                   kind=kind, pts=pts, old_len=old_len,
                                   new_len=sum(math.dist(p, q) for p, q in zip(pts[:-1], pts[1:])), angle_in=ang,
                                   current=cur, joined=True)
                        break
                    pts = pts + [end]
                    if not sp_legal(sp, s["net"], s["layer"], w, pts[-2], end):
                        why = "final_piece"
                        continue
                    new_len = sum(math.dist(p, q) for p, q in zip(pts[:-1], pts[1:]))
                    if new_len > old_len * (1 + LEN_REL) + LEN_ABS:
                        why = "length"
                        continue
                    if PE.entry_angle(g, pts[-2], end) is None or PE.entry_angle(g, pts[-2], end) > ENTRY_DEG:
                        why = "angle"
                        continue
                    cand = dict(id=s["uuid"], net=s["net"], layer=s["layer"], w=w, pieces=pieces, release=rel,
                                kind=kind, pts=pts, old_len=old_len, new_len=new_len, angle_in=ang,
                                current=cur, entry=facing if target == "centreline" else "edge")
                    if target != "centreline":
                        got = cand
                        break
                    if best is None or new_len < best["new_len"]:
                        best = cand
                if best is not None:
                    got = best
                if got is not None:
                    break
            if got is None:
                note("fail_" + why)
                break
            # commit in the Space: the old tail out, the new pieces in
            old = [items[p[0]["uuid"]] for p in got["pieces"] if p[0]["uuid"] in items]
            sp.remove(old)
            last = got["pieces"][-1]
            if got["kind"] == "split":
                keep_from = last[2]
                far = last[0]["b"] if math.dist(last[0]["a"], last[1]) <= TOL else last[0]["a"]
                if math.dist(keep_from, far) > 1e-6:
                    sp.add_track(s["net"], s["layer"], w, keep_from, far, owner=("pad-reroute", "kept"))
            for p, q in zip(got["pts"][:-1], got["pts"][1:]):
                sp.add_track(s["net"], s["layer"], w, p, q, owner=("pad-reroute", got["id"]))
            done.update(p[0]["uuid"] for p in got["pieces"])
            changes.append(got)
            note("rerouted")
            break
    return changes, outcome, octo


def sp_legal(sp, net, layer, w, a, b):
    return not sp.track_violations(net, layer, w, a, b, first=True)


def _route(gr, sp, Anchor, net, layer, w, rel, a, pad):
    """Grid route from `rel` to the approach point `a`, the pad kept out: the points, or None."""
    r = max(w / 2, gr.res)
    src = Anchor(Point(rel).buffer(r, quad_segs=8), (layer,), centre=tuple(rel), kind="track")
    dst = Anchor(Point(a).buffer(r, quad_segs=8), (layer,), centre=tuple(a), kind="track")
    rt = gr.connect(net, [src], [dst], w, [layer], via=False, avoid=[(pad, w / 2 + 1e-3, layer)])
    if rt is None or rt.vias:
        return None
    if not rt.segs:
        if math.dist(rel, a) < 1e-6:
            return [tuple(rel)]
        return [tuple(rel), tuple(a)] if sp_legal(sp, net, layer, w, rel, a) else None
    pts = [rt.segs[0][1]] + [s[2] for s in rt.segs]
    # the search ends on cells: the route must start at the release point and end at a exactly
    if math.dist(pts[0], rel) > 1e-6:
        if not sp_legal(sp, net, layer, w, rel, pts[0]):
            return None
        pts = [tuple(rel)] + pts
    if math.dist(pts[-1], a) > 1e-6:
        if not sp_legal(sp, net, layer, w, pts[-1], a):
            return None
        pts = pts + [tuple(a)]
    # no piece may run inside the pad before the final one
    if any(pad.distance(LineString([p, q])) < w / 2 - 1e-6 for p, q in zip(pts[:-1], pts[1:])):
        return None
    return pts


def _octo(sp, net, layer, w, pts):
    """The path with each piece that is not at a multiple of 45 degrees replaced by a legal
    dogleg; None when one has none."""
    out = [pts[0]]
    for p, q in zip(pts[:-1], pts[1:]):
        if _is_octo(p, q):
            out.append(q)
            continue
        for d in doglegs(p, q):
            if all(sp_legal(sp, net, layer, w, x, y) for x, y in zip(d[:-1], d[1:])):
                out += d[1:]
                break
        else:
            return None
    return out


def write(text, changes, skip=frozenset()):
    """The board text with the re-routes in `changes` (ids in `skip` left as they are)."""
    remove, edits, extra = set(), [], []
    segs = {s["uuid"]: s for s in PT._segments(text)}
    for ch in changes:
        if ch["id"] in skip:
            continue
        locked = False
        for k, (s, p, q) in enumerate(ch["pieces"]):
            last = k == len(ch["pieces"]) - 1
            if last and ch["kind"] == "split":
                cur = segs[s["uuid"]]
                end = "a" if math.dist(cur["a"], p) <= TOL else "b"
                a0, _ = cur["span"]
                spn = cur["sa"] if end == "a" else cur["se"]
                key = "start" if end == "a" else "end"
                edits.append((a0 + spn[0], a0 + spn[1], f"({key} {W.fmt(q[0])} {W.fmt(q[1])})"))
            else:
                remove.add(s["uuid"])
        for i, (p, q) in enumerate(zip(ch["pts"][:-1], ch["pts"][1:])):
            uid = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"kae-pad-reroute:{ch['id']}:{i}"))
            extra.append(W.track_sexpr(ch["net"], ch["layer"], ch["w"], p, q, uid=uid, locked=locked))
    out, pos = [], 0
    for _h, a, b in W._blocks(text, ("segment",)):
        u = W._uuid_of(text[a:b])
        if u in remove:
            out.append((a, W._eat_newline(text, b), ""))
    for a, b, rep in edits:
        out.append((a, b, rep))
    res = []
    for a, b, rep in sorted(out):
        res.append(text[pos:a])
        res.append(rep)
        pos = b
    res.append(text[pos:])
    t = "".join(res)
    return W._insert(t, extra) if extra else t


def run(input_path, output_path, overlap=None, workdir=None, timeout=3600, rails="middle", target="centreline",
        log=print):
    """The DRC-gated pass. Returns a report: entries considered and their outcomes, the kept
    re-routes, DRC in and out, pad-entry counts in and out, seconds."""
    from kae.board.kicad_file import load
    from . import constraints as CN
    from . import drc
    from .bridge import severities
    from .critical_grid import GridRouter
    from .critical_space import Space
    t0 = time.monotonic()
    end_t = t0 + timeout
    inp = Path(input_path).resolve()
    wd = Path(workdir or tempfile.mkdtemp(prefix="kae-reroute-"))
    wd.mkdir(parents=True, exist_ok=True)
    staged = W.stage(inp, wd / "in", "board")
    ovl = float(CN.setting("pad_entry_overlap", staged)) if overlap is None else float(overlap)
    info = PT._info(staged)
    text = staged.read_text(encoding="utf-8")
    sp = Space(load(staged), info, sev=severities(staged))
    gr = GridRouter(sp, pad_entry="centre")
    t1 = time.monotonic()
    changes, outcome, octo = plan(text, info, sp, gr, ovl, log=log, deadline=t0 + 0.6 * timeout, rails=rails,
                                  target=target)
    t_plan = time.monotonic() - t1
    rep = dict(board=str(inp), target=target, overlap=ovl, octilinear=octo, outcome=outcome, planned=len(changes),
               stats_in=PT.stats(text, info), setup_s=round(t1 - t0, 1), plan_s=round(t_plan, 1),
               len_old_mm=round(sum(c["old_len"] for c in changes), 3),
               len_new_mm=round(sum(c["new_len"] for c in changes), 3))
    base_rep = drc.run(staged, wd / "in.drc.json", timeout=max(10, end_t - time.monotonic()))
    base = drc.summary(base_rep)
    rep["drc_in"] = base
    cand = wd / "out" / "board.kicad_pcb"
    cand.parent.mkdir(parents=True, exist_ok=True)
    for ext in (".kicad_pro", ".kicad_dru"):
        if staged.with_suffix(ext).exists():
            shutil.copy2(staged.with_suffix(ext), cand.with_suffix(ext))
    skip, final = set(), None
    steps = [1.0, 2.5, "all"]
    for rnd in range(len(steps) + 1):
        if not changes or len(skip) >= len(changes) or end_t - time.monotonic() < 10:
            break
        cand.write_text(write(text, changes, skip), encoding="utf-8")
        r = drc.run(cand, wd / f"out.r{rnd}.json", timeout=max(10, end_t - time.monotonic()))
        s = drc.summary(r)
        worse = {t: n for t, n in s["by_type"].items() if n > base["by_type"].get(t, 0)}
        if s["unconnected"] > base["unconnected"]:
            worse["unconnected"] = s["unconnected"] - base["unconnected"]
        log(f"[pad-reroute] round {rnd}: {s['errors']} errors, {s['unconnected']} unconnected "
            f"(input {base['errors']}, {base['unconnected']}); reverted {len(skip)}; worse {worse or 'none'}")
        if not worse:
            final = s
            break
        if rnd == len(steps):
            break
        step = steps[rnd]
        if step == "all":
            skip |= {c["id"] for c in changes}
            continue
        pts = [(it["pos"]["x"], it["pos"]["y"]) for v in drc.errors(r) + list(r.get("unconnected_items") or [])
               for it in v.get("items") or [] if it.get("pos")]
        for c in changes:
            geo = LineString(c["pts"]).union(LineString([c["pieces"][0][1]] + [p[2] for p in c["pieces"]]))
            if any(geo.distance(Point(p)) <= step for p in pts):
                skip.add(c["id"])
    out = Path(output_path)
    if final is not None:
        shutil.copy2(cand, out)
        kept = [c for c in changes if c["id"] not in skip]
        rep["kept"] = len(kept)
        rep["reverted_drc"] = len(changes) - len(kept)
        rep["drc_out"] = final
        rep["stats_out"] = PT.stats(cand.read_text(encoding="utf-8"), info)
        rep["len_delta_mm"] = round(sum(c["new_len"] - c["old_len"] for c in kept), 3)
    else:
        shutil.copy2(staged, out)
        rep["kept"] = 0
        rep["reverted_drc"] = len(changes)
        rep["drc_out"] = base
        rep["stats_out"] = rep["stats_in"]
        rep["len_delta_mm"] = 0.0
    for ext in (".kicad_pro", ".kicad_dru"):
        s_ = inp.with_suffix(ext)
        if s_.exists() and s_.resolve() != out.with_suffix(ext).resolve():
            shutil.copy2(s_, out.with_suffix(ext))
    rep["total_s"] = round(time.monotonic() - t0, 1)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kae.route.pad_reroute", description=__doc__.split("\n\n")[0])
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--overlap", type=float)
    ap.add_argument("--workdir")
    ap.add_argument("--report")
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--rails", choices=("middle", "centre"), default="middle",
                    help="rails, grounds and wide tracks: re-route them (edge rule: into the edge middle a width deep; rule D: "
                         "to the centre line like any track), or leave their tails as they are")
    ap.add_argument("--target", choices=("centreline", "edge"), default="centreline",
                    help="rule D (default): end on the pad's long centre line, the crossing piece within 10 deg "
                         "of the outline normal; edge: the approach-target rule (end overlap-deep past the facing edge)")
    a = ap.parse_args(argv)
    rep = run(a.input, a.output, a.overlap, a.workdir, a.timeout, rails=a.rails, target=a.target)
    if a.report:
        Path(a.report).write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: v for k, v in rep.items()}))


if __name__ == "__main__":
    main()
