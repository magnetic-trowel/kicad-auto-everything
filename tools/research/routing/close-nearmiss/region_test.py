# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline A/B of the region re-route on a routed board: join every open connection with
(1) free grid joins only (rip=False), then (2) lastmile_region._region at growing margins; write the
board and judge it with KiCad's DRC (open count, errors beyond the input's).

usage: region_test.py <task input> <routed board .gz> <drc.json.gz> <outdir> [margins] [seconds]
"""
import sys, json, gzip, shutil, time, math, os
from pathlib import Path
from kae.board import pcbnew_io
from kae.board.kicad_file import load
from kae.route import constraints, drc, bridge, repair, lastmile as LM, lastmile_region as LR
from kae.route.critical_space import Space

inp, routed, drcp, od = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
margins = [float(x) for x in (sys.argv[5] if len(sys.argv) > 5 else "1,3,6").split(",")]
T = float(sys.argv[6]) if len(sys.argv) > 6 else 600
od.mkdir(parents=True, exist_ok=True)
board = od / "routed.kicad_pcb"
with gzip.open(routed, "rb") as f, open(board, "wb") as g:
    shutil.copyfileobj(f, g)
rep0 = json.load(gzip.open(drcp))
t0 = time.monotonic()
deadline = t0 + T
opts = dict(bridge.DEFAULT_OPTS, seed=0)
info = pcbnew_io.export_dsn(inp, od / "kicad.dsn")
opts["severities"] = bridge.severities(inp)
plan = constraints.plan(info, inp, opts)
plan.plane_policy = bridge.plane_policy(opts)
plan.plane_cost = opts.get("plane_cost")
plan.pad_shapes = "kicad"
staged = drc.stage_board(board, inp, od / "base")
fills = pcbnew_io.zone_fills(staged)["zones"]
sp = Space(load(staged), info, plan=plan, sev=opts["severities"])
inb = load(inp)
input_ids = {t.uuid for t in inb.tracks} | {v.uuid for v in inb.vias}


def rippable(it):
    return it.uuid not in input_ids


gr = LM._SoftRouter(sp)
LR.REGION_DEBUG = bool(os.environ.get("RDEBUG"))
fp = LM._fill_polys(fills)
known = sorted({it.net for it in sp.pads if it.net and it.kind == "pad"})
by_shown = {LM.unescape(n): n for n in known}
nets = [n if n in known else by_shown.get(n, n) for n in LM.open_nets(rep0)]
ripped, log = [], []
SKIP = bool(os.environ.get("SKIPFAIL"))   # a part that finds no join is skipped, the net's other parts still tried
for net in nets:
    failed = set()
    for _ in range(12):
        ps = [p for p in LM.parts(sp, fp, net) if LM._relevant(p)]
        ps = [p for p in ps if id(p[0].item) not in failed] if SKIP else ps
        if len(ps) < 2 or time.monotonic() > deadline:
            break
        mn, opt, _mx = sp.width_limits(net, sp.cu[0])
        widths = sorted({round(w, 4) for w in (opt, mn) if w and w > 0}, reverse=True) or [0.2]
        src = LM._anchors(ps[-1], max(widths) / 2 + 0.02)
        pads = [f"{n.item.owner[0]}.{n.item.owner[1]}" for n in ps[-1] if n.kind == "pad"][:3]
        t = time.monotonic()
        got = LM._join(gr, sp, net, src, ps[:-1], widths, input_ids, {}, (), rip=False) if src else None
        if got:
            for it in got[1]:
                it.owner = ("lastmile", "free")
            rec = dict(net=net, pads=pads, how="free")
        else:
            rec = dict(net=net, pads=pads, how=None)
            for m in margins:
                r = LR._region(gr, sp, fp, net, src, ps[:-1], m, rippable, deadline=deadline, log=print) if src else None
                if r:
                    new, cand, k = r
                    for it in new:
                        it.owner = ("lastmile", "region")
                    ripped += [it for it in cand if not LM._own(it)]
                    rec.update(how=f"region m={m}", rounds=k, ripped=len(cand), nets=len({it.net for it in cand}))
                    break
        rec["s"] = round(time.monotonic() - t, 1)
        print(json.dumps(rec), flush=True)
        log.append(rec)
        if not rec["how"]:
            if SKIP and len(ps) > 2:
                failed.add(id(ps[-1][0].item))
                continue
            break
out = od / "out.kicad_pcb"
LM._write(sp, staged, out, remove=sorted({it.uuid for it in ripped}), locked=False)
base = repair.input_errors(inp, od, time.monotonic() + 900)
s0 = drc.summary(rep0)
rep = drc.run(drc.stage_board(out, inp, od / "drc"), od / "drc" / "drc.json", timeout=1800)
s = drc.summary(rep)
res = dict(before=dict(open=s0["unconnected"], errors=s0["errors"], excess=drc.excess(s0, base), by_type=s0["by_type"]),
           after=dict(open=s["unconnected"], errors=s["errors"], excess=drc.excess(s, base), by_type=s["by_type"]),
           joins=log, seconds=round(time.monotonic() - t0, 1))
json.dump(res, open(od / "result.json", "w"), indent=1)
print("RESULT", json.dumps({k: res[k] for k in ("before", "after", "seconds")}), flush=True)
