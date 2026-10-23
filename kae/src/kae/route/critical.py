# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics-first routing of the decisive nets, before the general router.

The copper whose geometry decides a board's physics is routed first, at its physical
optimum, and locked; the Freerouting bridge (kae.route.bridge) then routes everything else
around it (locked items go to Freerouting as fixed wiring). See
docs/topics/routing/critical-net-routing.md.

    from kae.route import critical
    rep = critical.route_critical("in.kicad_pcb", "out.kicad_pcb")      # critical copper only
    rep = critical.run("in.kicad_pcb", "out.kicad_pcb", time_s=900)     # critical, bridge, recheck

What is routed (critical_modules, critical_rails):
- commutation cells: every board hop of the hot loop, as wide as its terminals, on the
  layer next to the reference plane; return vias where they minimize loop L;
- decoupling: capacitor -> IC power pin; capacitor ground and IC ground -> plane vias;
- crystals: XIN/XOUT and the load capacitors, shortest; load-cap ground into the plane;
- protection chains: connector -> protector -> protected part, in that order;
- power rails: widths from E5 currents and a drop budget, zones used where they exist.

Joint use (the month plan's joint loop):
- `optimize_modules(board, brief, terms, locked)` co-optimizes each module's movable part
  poses and its copper on the routed physics and returns (poses, copper);
- `recheck(board_routed, brief, stage)` recomputes each module on the finished copper and
  returns the modules to re-tweak.
"""
from __future__ import annotations

import json
import math
import tempfile
import time
from pathlib import Path

from kae.board import pcbnew_io
from kae.board.kicad_file import load
from kae.board.model import Track, Via

from . import critical_write as W
from .critical_grid import GridRouter
from .critical_modules import Ctx, modules_from_brief, route_module
from .critical_space import Space

DEFAULTS = dict(
    kinds=("cell", "decap", "crystal", "chain"),
    rails="auto",          # auto: rails whose E5 current needs more than the class width; all; none
    res=0.05,              # grid resolution (mm)
    via_in_pad=False,      # vias inside small SMD pads (thermal pads always allow them)
    decap_max_mm=10.0,     # a capacitor farther than this from its pin: no local decoupling, left to the bridge
    chain_power_a=1.0,     # E5 current of a protected power pin without a rail estimate
)


def _log(msg):
    print(f"[kae.critical {time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ----------------------------------------------------------------------------- setup
class Session:
    """Everything critical routing needs for one board: model, brief, rules, space, router."""

    def __init__(self, board_path, brief=None, info=None, opts=None, log=_log, board=None, terms=None):
        t0 = time.monotonic()
        self.path = Path(board_path).resolve()
        self.opts = {**DEFAULTS, **(opts or {})}
        self.log = log
        self.board = board or load(self.path)
        if brief is None:
            from kae.circuit.brief import build
            brief = build(self.board)
        self.brief = brief
        if info is None:
            with tempfile.TemporaryDirectory(prefix="kae-crit-") as d:
                info = pcbnew_io.export_dsn(self.path, Path(d) / "board.dsn")
        self.info = info
        from .bridge import severities
        self.sev = severities(self.path)
        self.space = Space(self.board, info, sev=self.sev, opts=self.opts)
        self.router = GridRouter(self.space, res=self.opts["res"])
        self.ctx = Ctx(self.space, self.router, brief, self.board, dict(self.opts, log=log), terms=terms)
        self.modules = []
        self.rails = []
        self.t_setup = time.monotonic() - t0

    # ------------------------------------------------------------------ routing
    def route(self):
        t0 = time.monotonic()
        mods = modules_from_brief(self.brief, self.opts["kinds"])
        for m in mods:
            t1 = time.monotonic()
            route_module(self.ctx, m)
            m.physics["seconds"] = round(time.monotonic() - t1, 3)
            self.log(f"{m.id}: {m.status}, {len(m.copper)} items, "
                     f"{m.physics.get('value')} {m.physics.get('unit', '')} (u {m.physics.get('u')})"
                     + (f" [{'; '.join(m.notes[:3])}]" if m.notes else ""))
        self.modules = mods
        if self.opts.get("rails", "auto") != "none":
            from .critical_rails import route_rails
            self.rails = route_rails(self.ctx, mode=self.opts.get("rails", "auto"))
        self.t_route = time.monotonic() - t0
        return self

    # ------------------------------------------------------------------ output
    def copper(self):
        """The committed critical copper as kae.board.model Track and Via objects (locked)."""
        out_t, out_v = [], []
        for it in self.space.routed:
            if not it.uuid:
                it.uuid = W.new_uuid()
            if it.kind == "track":
                (x0, y0), (x1, y1) = it.geom.coords[0], it.geom.coords[-1]
                out_t.append(Track(uuid=it.uuid, net=it.net, layer=next(iter(it.layers)), width=it.width,
                                   start=(x0, y0), end=(x1, y1), locked=True))
            elif it.kind == "via":
                out_v.append(Via(uuid=it.uuid, net=it.net, x=it.geom.x, y=it.geom.y, size=it.width, drill=it.drill,
                                 layers=[self.space.cu[0], self.space.cu[-1]], locked=True))
        return out_t, out_v

    def write(self, dst, guards=()):
        tracks, vias = self.copper()
        W.append_items(self.path, dst,
                       tracks=[(t.net, t.layer, t.width, t.start, t.end, t.uuid) for t in tracks],
                       vias=[(v.net, v.x, v.y, v.size, v.drill, v.uuid) for v in vias],
                       zones=list(guards))
        for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
            s = self.path.with_suffix(ext)
            t = Path(dst).with_suffix(ext)
            if s.exists() and s.resolve() != t.resolve():
                import shutil
                shutil.copy2(s, t)
        return len(tracks), len(vias)

    def report(self):
        tracks, vias = self.copper()
        return dict(
            board=str(self.path),
            setup_s=round(self.t_setup, 2), route_s=round(getattr(self, "t_route", 0.0), 2),
            tracks=len(tracks), vias=len(vias),
            track_mm=round(sum(math.dist(t.start, t.end) for t in tracks), 2),
            router=dict(self.router.stats),
            modules=[dict(id=m.id, kind=m.kind, status=m.status, items=len(m.copper), physics=m.physics,
                          notes=m.notes[:6]) for m in self.modules],
            rails=self.rails,
        )


# ----------------------------------------------------------------------------- API
def route_critical(board_path, out_path=None, brief=None, info=None, opts=None, log=_log):
    """Route the critical copper of a placed board; write `out_path` (input + locked copper)
    when given. Returns (report, session)."""
    s = Session(board_path, brief=brief, info=info, opts=opts, log=log).route()
    if out_path:
        s.write(out_path)
    return s.report(), s


def to_json(rep):
    return json.dumps(rep, default=str)


# ----------------------------------------------------------------------------- full pipeline
def run(input_path, output_path, seed=0, time_s=900.0, opts=None, bridge_opts=None, rounds=0, workdir=None,
        log=_log, bridge=True):
    """Critical routing, then the bridge around the locked copper, then (rounds > 0) the
    recheck / re-tweak loop; OUTPUT = INPUT + all routing (nothing else changes). Returns a
    JSON-able report."""
    t0 = time.monotonic()
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    own = workdir is None
    wd = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="kae-crit-", dir=output_path.parent))
    wd.mkdir(parents=True, exist_ok=True)
    rep = dict(input=str(input_path), seed=seed, budget_s=time_s)

    def left():
        return time_s - (time.monotonic() - t0)
    try:
        s = Session(input_path, opts=opts, log=log).route()
        rep["critical"] = s.report()
        w0 = wd / "crit.kicad_pcb"
        s.write(w0)
        W.transplant(w0, input_path, output_path)        # a valid output from the start
        best = w0
        if bridge and left() > 30:
            from . import bridge as BR
            r0 = wd / "routed0.kicad_pcb"
            budget = left() - 15.0 if rounds <= 0 else 0.6 * (left() - 15.0)
            b = BR.route(w0, r0, seed=seed, time_s=max(20.0, budget), workdir=wd / "bridge0",
                         opts=dict(bridge_opts or {}, keep=True), log=log)
            rep["bridge"] = {k: v for k, v in b.items() if k in ("status", "seconds", "router", "repair", "drc")}
            if r0.exists():
                best = r0
                W.transplant(r0, input_path, output_path)
            if rounds > 0 and r0.exists() and left() > 60:
                from .critical_recheck import retweak_loop
                rep["retweak"] = retweak_loop(s, r0, input_path, output_path, wd, rounds=rounds, seed=seed,
                                              deadline=t0 + time_s - 10.0, bridge_opts=bridge_opts, log=log)
        rep["status"] = "ok"
    except Exception as e:  # noqa: BLE001 - always leave a report
        import traceback
        traceback.print_exc()
        rep["status"] = "error"
        rep["error"] = f"{type(e).__name__}: {e}"
    finally:
        rep["seconds"] = round(time.monotonic() - t0, 2)
        if own and not (opts or {}).get("keep"):
            import shutil
            shutil.rmtree(wd, ignore_errors=True)
        else:
            rep["workdir"] = str(wd)
    return rep


def write_joint(src, dst, poses, copper):
    """dst = src with parts moved to `poses` (pcbnew_io.write_poses: KiCad's own writer, any
    angle) and the critical copper added (locked). Project files are copied beside dst."""
    import shutil
    src, dst = Path(src), Path(dst)
    if poses:
        pcbnew_io.write_poses(src, dst, {u: tuple(p) for u, p in poses.items()})
    elif src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    tracks = [c for c in copper if isinstance(c, Track)]
    vias = [c for c in copper if isinstance(c, Via)]
    W.append_items(dst, dst, tracks=[(t.net, t.layer, t.width, t.start, t.end, t.uuid) for t in tracks],
                   vias=[(v.net, v.x, v.y, v.size, v.drill, v.uuid) for v in vias])
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        s = src.with_suffix(ext)
        t = dst.with_suffix(ext)
        if s.exists() and s.resolve() != t.resolve():
            shutil.copy2(s, t)
    return dst
