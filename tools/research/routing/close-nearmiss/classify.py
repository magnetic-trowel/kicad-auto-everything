# SPDX-License-Identifier: GPL-3.0-or-later
"""Classify each open connection of a routed board (the last mile's view of it).

usage: classify.py <task input board> <routed board (.kicad_pcb[.gz])> <drc.json[.gz]> <outdir> [human board]

Per missing connection (each part of an open net but the largest, smallest first):
  free   : a grid path exists in the final copper (lastmile._join, rip=False)
  rip    : a path that rips N foreign items of ours (lastmile._join, rip=True), N reported
  empty  : a path with ALL our copper of other nets gone (only pads, obstacles, input copper):
           if this fails too, nothing we routed is in the way -> rule/geometry (d)
plus our and the human's copper in the connection's box (length per layer, vias, nets).
Every test starts from the same final copper (undone after).
"""
import sys, json, gzip, shutil, time, math
from pathlib import Path
from shapely.geometry import box
from kae.board import pcbnew_io
from kae.board.kicad_file import load
from kae.route import constraints, drc, bridge, lastmile as LM
from kae.route.critical_space import Space

inp, routed, drcp, od = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
human = sys.argv[5] if len(sys.argv) > 5 else None
od.mkdir(parents=True, exist_ok=True)


def ungz(p, dst):
    p = Path(p)
    if p.suffix == ".gz":
        with gzip.open(p, "rb") as f, open(dst, "wb") as g:
            shutil.copyfileobj(f, g)
        return Path(dst)
    return p


board = ungz(routed, od / "routed.kicad_pcb")
rep = json.load(gzip.open(drcp) if drcp.endswith(".gz") else open(drcp))
opts = dict(bridge.DEFAULT_OPTS, seed=0)
info = pcbnew_io.export_dsn(inp, od / "kicad.dsn")
opts["severities"] = bridge.severities(inp)
plan = constraints.plan(info, inp, opts)
plan.plane_policy = bridge.plane_policy(opts)
plan.plane_cost = opts.get("plane_cost")
plan.pad_shapes = "kicad"
staged = drc.stage_board(board, inp, od / "base")
fills = pcbnew_io.zone_fills(staged)["zones"]
b = load(staged)
import os
sp = Space(b, info, plan=plan, sev=opts["severities"], opts={"no_corridors": bool(os.environ.get("NOCOR"))})
inb = load(inp)
input_ids = {t.uuid for t in inb.tracks} | {v.uuid for v in inb.vias}
for it in sp.existing:          # everything we routed is ours to rip (the last mile wrote its copper locked)
    if it.uuid not in input_ids:
        it.locked = False
gr = LM._SoftRouter(sp)
fp = LM._fill_polys(fills)
known = sorted({it.net for it in sp.pads if it.net and it.kind == "pad"})
by_shown = {LM.unescape(n): n for n in known}
nets = [n if n in known else by_shown.get(n, n) for n in LM.open_nets(rep)]

hb = load(ungz(human, od / "human.kicad_pcb")) if human else None


def copper_in(bd, win, skip_net=None):
    out = dict(len={}, vias=0, nets=set())
    for t in bd.tracks:
        g = box(min(t.start[0], t.end[0]), min(t.start[1], t.end[1]), max(t.start[0], t.end[0]) + 1e-6,
                max(t.start[1], t.end[1]) + 1e-6)
        if not g.intersects(win):
            continue
        L = math.dist(t.start, t.end)
        out["len"][t.layer] = round(out["len"].get(t.layer, 0) + L, 2)
        out["nets"].add(t.net)
    for v in bd.vias:
        if win.contains(box(v.x - 1e-3, v.y - 1e-3, v.x + 1e-3, v.y + 1e-3)):
            out["vias"] += 1
            out["nets"].add(v.net)
    out["nets"] = len(out["nets"])
    return out


def undo(new, ripped=()):
    sp.remove(list(new))
    if ripped:
        LM._restore(sp, list(ripped))


def rt_info(rt):
    L = sum(math.dist(a, b2) for _, a, b2 in rt.segs)
    return dict(len=round(L, 2), vias=len(rt.vias), layers=sorted({l for l, _, _ in rt.segs}))


res = []
t0 = time.monotonic()
for net in nets:
    ps = [p for p in LM.parts(sp, fp, net) if LM._relevant(p)]
    mn, opt, _mx = sp.width_limits(net, sp.cu[0])
    widths = sorted({round(w, 4) for w in (opt, mn) if w and w > 0}, reverse=True) or [0.2]
    for k in range(len(ps) - 1, 0, -1):
        small, others = ps[k], ps[:k] + ps[k + 1:]
        src = LM._anchors(small, max(widths) / 2 + 0.02)
        kinds = sorted({n.kind for n in small})
        pads = [f"{n.item.owner[0]}.{n.item.owner[1]}" for n in small if n.kind == "pad"][:4]
        rec = dict(net=net, part=k, kinds=kinds, pads=pads, widths=widths)
        if not src:
            rec["cls"] = "no anchors"
            res.append(rec)
            continue
        win = LM._window(src, others, 0.5)
        rec["box"] = [round(x, 2) for x in win.bounds]
        rec["ours"] = copper_in(b, win)
        if hb is not None:
            rec["human"] = copper_in(hb, win)
        t = time.monotonic()
        got = LM._join(gr, sp, net, src, others, widths, set(input_ids), {}, (), rip=False)
        rec["free"] = rt_info(got[0]) if got else None
        if got:
            undo(got[1])
        rec["t_free"] = round(time.monotonic() - t, 1)
        t = time.monotonic()
        got = LM._join(gr, sp, net, src, others, widths, set(input_ids), {}, (), rip=True) if not rec["free"] else None
        if got:
            rec["rip"] = dict(rt_info(got[0]), n=len(got[2]), nets=sorted({it.net for it in got[2]}))
            undo(got[1], got[2])
        else:
            rec["rip"] = None
        rec["t_rip"] = round(time.monotonic() - t, 1)
        if not rec["free"] and not rec["rip"]:
            # all our copper of other nets out of the space
            ours = [it for it in sp.existing if it.kind in ("track", "via") and it.uuid not in input_ids and it.net != net]
            sp.remove(ours)
            try:
                got = None
                for m in (1.0, 3.0, 8.0, 20.0):
                    got = LM._try(gr, sp, net, src, others, LM._window(src, others, m), widths)
                    if got:
                        break
                if got:
                    rt, new = got
                    hit = [it for it in ours if LM._conflicts(sp, it, set(new))]
                    rec["empty"] = dict(rt_info(rt), window=m, crosses=len(hit),
                                        cross_nets=len({it.net for it in hit}))
                    sp.remove(new)
                else:
                    rec["empty"] = None
            finally:
                LM._restore(sp, ours)
        rec["cls"] = ("a-free" if rec["free"] else
                      ("a-rip" if rec["rip"]["n"] <= 3 else "b-rip>3") if rec["rip"] else
                      "b-region" if rec.get("empty") else "d-nopath")
        print(json.dumps(rec), flush=True)
        res.append(rec)
json.dump(dict(nets=nets, conns=res, seconds=round(time.monotonic() - t0, 1)), open(od / "classify.json", "w"), indent=1)
print("DONE", len(res), {c: sum(r["cls"] == c for r in res) for c in sorted({r["cls"] for r in res})}, flush=True)
