# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Critical copper with the old pad entry against born-right rule D (routing-stages.md stage 2).

    python born_right_critical.py BOARD.kicad_pcb OUTDIR [--modes centre,centreline]

For each mode, kae.route.critical.route_critical on a copy of BOARD (an unrouted, placed board
with its .kicad_pro) with pad_entry=<mode>, then KiCad's DRC on the output. Writes
OUTDIR/<mode>/board.kicad_pcb and OUTDIR/<mode>.json: route time, the router's entries by kind,
necks and goal retries, pad-entry counts of the critical copper (pad_trim.stats: perpendicular /
oblique / acute, on the centre line, overhanging), track length, and DRC by type (errors and
unconnected, input and output). Run it under ulimit -v and the queue (tools/kaeq)."""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path


def _chained(s):
    """Necked lands (the plan's PadRule.neck) with two or more of the session's track ends in them,
    one of them a neck (a piece narrower than the copper it continues): current chained through
    the neck."""
    from shapely.geometry import Point
    sp = s.space
    n = 0
    for it in sp.pads:
        r = sp.plan.pad_rule(it.idx) if it.kind == "pad" else None
        if r is None or r.neck is None:
            continue
        ins, neck = 0, False
        for l in it.layers:
            for t in sp.items.get(l, ()):
                if t.kind != "track" or t.net != it.net or t not in sp.routed:
                    continue
                for q, o in ((t.geom.coords[0], t.geom.coords[-1]), (t.geom.coords[-1], t.geom.coords[0])):
                    if it.geom.contains(Point(q)):
                        ins += 1
                        po = Point(o)
                        neck |= any(x.kind == "track" and x.net == t.net and x.width > t.width + 1e-6
                                    and x.geom.distance(po) < 1e-6 for x in sp.items.get(l, ()))
        n += ins >= 2 and neck
    return n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("out")
    ap.add_argument("--modes", default="centre,centreline")
    a = ap.parse_args(argv)
    from kae.route import critical, drc
    from kae.route import pad_trim as PT
    src = Path(a.board).resolve()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base = drc.summary(drc.run(src, out / "in.drc.json"))
    for mode in a.modes.split(","):
        d = out / mode
        d.mkdir(exist_ok=True)
        inp = d / "in" / "board.kicad_pcb"
        inp.parent.mkdir(exist_ok=True)
        shutil.copy2(src, inp)
        for ext in (".kicad_pro", ".kicad_dru"):
            if src.with_suffix(ext).exists():
                shutil.copy2(src.with_suffix(ext), inp.with_suffix(ext))
        dst = d / "board.kicad_pcb"
        t0 = time.monotonic()
        rep, s = critical.route_critical(inp, dst, opts=dict(pad_entry=mode), log=lambda *x: None)
        t = time.monotonic() - t0
        for ext in (".kicad_pro", ".kicad_dru"):
            if inp.with_suffix(ext).exists():
                shutil.copy2(inp.with_suffix(ext), dst.with_suffix(ext))
        st = PT.stats(dst.read_text(encoding="utf-8"), s.info)
        st["necked_lands_chained"] = _chained(s)
        dr = drc.summary(drc.run(dst, d / "drc.json"))
        res = dict(board=src.parent.parent.parent.name if src.parent.name == "input" else src.stem, mode=mode,
                   route_s=round(t, 1), tracks=rep["tracks"], vias=rep["vias"], track_mm=rep["track_mm"],
                   router=rep["router"], entries=st, drc_in=base, drc_out=dr,
                   hazards=[h["code"] for h in rep.get("hazards") or []],
                   modules={m["id"]: (m.get("physics") or {}).get("value") for m in rep.get("modules") or []},
                   modules_acute=sorted(m.id for m in s.modules if any("centre_acute" in (r.entries if r else ())
                                                                    for r in m.hops.values())),
                   module_entries={m.id: {k: list(r.entries) for k, r in m.hops.items() if r is not None}
                                   for m in s.modules})
        (out / f"{mode}.json").write_text(json.dumps(res, indent=1))
        print(json.dumps(dict(mode=mode, route_s=res["route_s"], track_mm=res["track_mm"],
                              router_entries=rep["router"].get("entries"), necks=rep["router"].get("necks"),
                              stats={k: st[k] for k in ("entries", "on_centreline", "perpendicular", "oblique",
                                                        "acute", "overhanging", "necked_lands_chained")},
                              fallbacks={k: rep["router"].get(k) for k in ("fallback_old_entry", "fallback_crossing",
                                                                           "lands_kept_out", "neck_leaf")},
                              drc=dr.get("by_type"), unconnected=dr.get("unconnected"),
                              quote_s=round(rep["router"].get("quote_s", 0.0), 2), modules=res["modules"],
                              modules_acute=res["modules_acute"])), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
