# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Critical copper with and without stage-2 tightening (kae.route.critical_taut) on one board.

    python tools/research/routing/crit_tighten_smoke.py ROUTED.kicad_pcb OUTDIR ARM [--time S] [--opt K=V ...]

ARM: "grid" (tighten off) or "taut" (tighten on). ROUTED is any board with the placement to use;
its routing is stripped first (router A/Bs start from bare placement), its .kicad_pro/.kicad_dru
are copied beside. Then kae.route.critical.run (critical copper, then the bridge) writes
OUTDIR/ARM.kicad_pcb; KiCad's DRC on it (zones refilled) gives errors by type and unconnected.
OUTDIR/ARM.json: critical copper length and corners (on the locked copper the bridge got),
module physics, tightening counters, DRC, seconds. Summary: crit_tighten_summary.py.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path


def strip(src, dst):
    from kae.route import critical_write as W
    uu = [r["uuid"] for r in W.routing(src)]
    W.edit(src, dst, remove=uu)
    for ext in (".kicad_pro", ".kicad_dru"):
        s = Path(src).with_suffix(ext)
        if s.exists():
            shutil.copy2(s, Path(dst).with_suffix(ext))


def crit_stats(board):
    """Length, corners and arcs of the locked (critical) copper of a board file."""
    import math
    from kae.board.kicad_file import load
    from kae.route import arcs as A
    b = load(board)
    ts = [t for t in b.tracks if t.locked]
    ends = {}
    for t in ts:
        cs = A.track_coords(t)
        d0 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
        d1 = (cs[-1][0] - cs[-2][0], cs[-1][1] - cs[-2][1])
        for p, d in ((cs[0], (-d0[0], -d0[1])), (cs[-1], d1)):
            n = math.hypot(*d) or 1.0
            ends.setdefault((t.net, t.layer, round(p[0], 4), round(p[1], 4)), []).append((d[0] / n, d[1] / n))
    corners = sum(1 for ds in ends.values() if len(ds) == 2
                  and -(ds[0][0] * ds[1][0] + ds[0][1] * ds[1][1]) < math.cos(math.radians(5.0)))
    return dict(tracks=len(ts), arcs=sum(1 for t in ts if t.mid is not None),
                length_mm=round(sum(A.track_length(t) for t in ts), 3), corners=corners,
                vias=sum(1 for v in b.vias if v.locked))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("routed")
    ap.add_argument("outdir")
    ap.add_argument("arm", choices=("grid", "taut"))
    ap.add_argument("--time", type=float, default=600.0)
    ap.add_argument("--opt", action="append", default=[])
    a = ap.parse_args(argv)
    from kae.route import critical, drc
    out = Path(a.outdir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    inp = out / "in.kicad_pcb"
    if not inp.exists():
        strip(a.routed, inp)
    opts = dict(tighten=a.arm == "taut", keep=True)
    for kv in a.opt:
        k, _, v = kv.partition("=")
        for cast in (int, float):
            try:
                v = cast(v)
                break
            except ValueError:
                pass
        opts[k] = v
    dst = out / f"{a.arm}.kicad_pcb"
    wd = out / f"{a.arm}-work"
    if wd.exists():
        shutil.rmtree(wd)
    t0 = time.monotonic()
    rep = critical.run(inp, dst, time_s=a.time, opts=opts, workdir=wd,
                       log=lambda m: print(f"[crit] {m}", file=sys.stderr, flush=True))
    secs = time.monotonic() - t0
    crit = rep.get("critical") or {}
    res = dict(arm=a.arm, status=rep.get("status"), seconds=round(secs, 1),
               setup_s=crit.get("setup_s"), route_s=crit.get("route_s"),
               tighten=crit.get("tighten"), tighten_error=rep.get("tighten_error"),
               modules=[dict(id=m["id"], kind=m["kind"], status=m["status"], value=(m.get("physics") or {}).get("value"),
                             unit=(m.get("physics") or {}).get("unit"), u=(m.get("physics") or {}).get("u"))
                        for m in crit.get("modules") or []],
               rails=[dict(net=r.get("net"), branches=[dict(load=b.get("load"), drop_mV=b.get("drop_mV"))
                                                      for b in r.get("branches") or []])
                      for r in crit.get("rails") or [] if r.get("routed")],
               bridge={k: v for k, v in (rep.get("bridge") or {}).items() if k in ("status", "seconds")})
    w0 = wd / "crit.kicad_pcb"
    if w0.exists():
        res["crit_copper"] = crit_stats(w0)
    if dst.exists():
        d = drc.run(dst, out / f"{a.arm}.drc.json", timeout=1800)
        errs = drc.errors(d)
        by = {}
        for v in errs:
            by[v["type"]] = by.get(v["type"], 0) + 1
        res["drc"] = dict(errors=len(errs), by_type=by, unconnected=len(d.get("unconnected_items") or []))
    for f in wd.rglob("*.kicad_pcb"):
        if f.name != "crit.kicad_pcb":
            f.unlink()
    (out / f"{a.arm}.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: res.get(k) for k in ("arm", "status", "seconds", "crit_copper", "drc")}, default=str))


if __name__ == "__main__":
    main()
