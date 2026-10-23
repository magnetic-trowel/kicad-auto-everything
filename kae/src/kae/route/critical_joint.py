# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Joint module optimization: each module's movable parts and its critical copper together.

    poses, copper, report = optimize_modules(board, brief, terms, locked)

For each module of the brief (physically decisive first), its parts that may move do move,
to any angle, while its copper is routed; every candidate is judged on the routed physics
(critical_modules.quote on the routed segments), not on straight hops:

1. **What may move.** Not task-locked parts (`locked`), and not parts shared with another
   routed module (an IC that is both a cell's switch and a decap's load keeps the placer's
   pose). Heatsink-mount packages (TO-220, TO-247, TO-3P, TO-218, TO-264, TO-126 with a
   tab hole) move but keep right angles; a part on a described heatsink is in `locked`.
2. **Candidates.** Small translations (0.25-2 mm), rotations (15-180 degrees), and the
   physics-aligned pose: a two-terminal part turned so its terminals face their partners
   (a decap's rail pad toward the power pin and its ground pad toward the ground pin) and
   slid along the line to them.
3. **Legality, exact.** Courtyards at the actual angle (kae.board.transform.courtyard, with
   KiCad's 5 um deflation) on both courtyard layers, pad-to-pad clearance (each pad's own
   KiCad clearance), clearance to committed copper (the pad's clearance class), pads inside
   the outline at the edge clearance, rule areas that keep out footprints or pads.
4. **Screen and judge.** Candidates are ranked by the place terms (`terms.delta`, straight
   hops, microseconds) when given; the best few are routed and quoted; a move is kept when
   the routed value improves by more than 1 %.
5. Then the rails are routed around the modules (critical_rails).

All poses are (x, y, rot, side) in KiCad board coordinates; sides never change here.
"""
from __future__ import annotations

import math
import re
import time

import shapely
from shapely.ops import unary_union

from kae.board import transform

from .critical_modules import Ctx, modules_from_brief, quote, route_module

HEATSINK_RE = re.compile(r"TO-?220|TO-?247|TO-?3P|TO-?218|TO-?264|TO-?126|TO-?3\b|SOT-?93|Heatsink", re.I)


def heatsink_mount(fp):
    """A package that mounts on a heatsink by its tab: right angles only."""
    return bool(HEATSINK_RE.search(f"{fp.lib_id} {fp.value}")) and any(p.drill for p in fp.pads)


# ----------------------------------------------------------------------------- legality
class Legality:
    """Exact placement legality of one part at a trial pose against everything else (see
    the module docstring)."""

    def __init__(self, sess):
        self.sess = sess
        self.sp = sess.space
        self.board = sess.board
        self.cy = {}             # uuid -> {courtyard layer: geometry} at current poses
        self.poses = {}
        for f in self.board.footprints:
            if not f.on_board:
                continue
            self.poses[f.uuid] = (f.x, f.y, f.rot, f.side)
            self.cy[f.uuid] = self._cy(f, self.poses[f.uuid])
        self.own_clr = {}
        for it in self.sp.pads:
            if it.idx >= 0:
                self.own_clr[id(it)] = (self.sp.info["pads"][it.idx].get("own_clearance") or {})
        self.edge = self.sp.settings.get("edge_clearance", 0.0) or 0.0
        self.keepouts = [k for k in self.board.keepouts if k.footprints or k.pads]

    def _cy(self, f, pose):
        out = {}
        own, opp = transform.courtyard_layers(f, pose[3])
        for which, layer in (("own", own), ("opposite", opp)):
            polys = transform.courtyard(f, *pose, which=which, deflate=transform.KICAD_COURTYARD_DEFLATE)
            if polys:
                g = unary_union(polys)
                if not g.is_empty:
                    out[layer] = g
        return out

    def ok(self, u, pose):
        """(True, '') when part u at `pose` is legal; else (False, why)."""
        f = self.sess.ctx.fp[u]
        cy = self._cy(f, pose)
        for v, ocy in self.cy.items():
            if v == u:
                continue
            for layer, g in cy.items():
                o = ocy.get(layer)
                if o is not None and g.intersects(o) and g.intersection(o).area > 1e-6:
                    return False, f"courtyard {layer} vs {self.sess.ctx.fp[v].ref}"
        for ko in self.keepouts:
            for layer, g in cy.items():
                if g.intersects(ko.outline):
                    return False, f"rule area {ko.name}"
        # pads at the trial pose (moved in the space, restored after)
        sp = self.sp
        old = self.poses[u]
        sp.set_pose(u, old, pose)
        try:
            return self._pads_ok(u)
        finally:
            sp.set_pose(u, pose, old)

    def _pads_ok(self, u):
        sp = self.sp
        mine = sp.pads_by_fp.get(u) or []
        ob = sp.outline
        # the part's own thermal spokes must stay free of other nets' pads
        for cor in sp.corridors_by_fp.get(u) or []:
            for layer in cor.layers:
                for o in sp.query(layer, cor.bbox, 0.0):
                    if o.kind == "pad" and o.fp != u and o.net != cor.net and cor.geom.intersects(o.geom):
                        return False, f"spokes of {cor.owner} blocked by pad {o.owner}"
        for it in mine:
            if it.kind != "pad":
                continue
            if ob is not None:
                if not ob.contains(it.geom):
                    return False, f"pad {it.owner} outside the outline"
                if ob.boundary.distance(it.geom) < self.edge - 1e-4:
                    return False, f"pad {it.owner} edge clearance"
            for layer in it.layers:
                for o in sp.query(layer, it.bbox, sp.max_need + 1.0):
                    if o is it or o.fp == u:
                        continue
                    if o.kind == "pad":
                        if it.net and o.net == it.net:
                            continue
                        c1 = (self.own_clr.get(id(it)) or {}).get(layer, 0.0) or 0.0
                        c2 = (self.own_clr.get(id(o)) or {}).get(layer, 0.0) or 0.0
                        need = max(c1, c2)
                        if it.geom.distance(o.geom) < need - 1e-4:
                            return False, f"pad {it.owner} vs pad {o.owner}"
                    elif o.kind in ("track", "via"):
                        if it.net and o.net == it.net:
                            continue
                        nd = sp.need(it, o.net, o.kind, layer) or 0.0
                        if o.geom.distance(it.geom) - o.r < nd - 1e-4:
                            return False, f"pad {it.owner} vs {o.kind} of {o.net}"
                    elif o.kind == "corridor":
                        # another pad's thermal spokes: a foreign pad there starves them
                        if it.net and o.net == it.net:
                            continue
                        if it.geom.intersects(o.geom):
                            return False, f"pad {it.owner} on the spokes of {o.owner}"
                    elif o.kind in ("hole", "shape", "keepout"):
                        if o.kind == "keepout":
                            if it.geom.intersects(o.geom):
                                return False, f"pad {it.owner} in a rule area"
                            continue
                        if it.geom.distance(o.geom) - o.r < 0.0:
                            return False, f"pad {it.owner} on {o.kind}"
        return True, ""

    def commit(self, u, pose):
        old = self.poses[u]
        self.sp.set_pose(u, old, pose)
        self.poses[u] = pose
        self.cy[u] = self._cy(self.sess.ctx.fp[u], pose)


# ----------------------------------------------------------------------------- candidates
def _partners(sess, m, u):
    """[(own pad number, partner point)] for part u in module m: where its terminals want to be."""
    ctx = sess.ctx
    sp = sess.space
    s = m.spec
    f = ctx.fp[u]
    out = []
    if m.kind == "decap":
        ic = s.get("ic")
        rail = s.get("rail")
        pins = [str(p) for p in s.get("power_pins") or []]
        pc = s.get("pin_caps") or {}
        pin = next((p for p, cs in pc.items() if u in cs), pins[0] if pins else None)
        tp = sp.terminal(ic, [pin]) if pin else None
        if tp is None:
            return out
        from .critical_modules import _ic_ground
        tG = _ic_ground(ctx, s, tp)
        for p in f.pads:
            if p.net == rail:
                out.append((p.number, (tp.x, tp.y)))
            elif tG is not None and p.net == tG.net:
                out.append((p.number, (tG.x, tG.y)))
    elif m.kind in ("cell", "chain", "crystal"):
        T = m.spec.get("_T") or []
        for p in f.pads:
            for t in T:
                if t.fp != u and t.net == p.net:
                    out.append((p.number, (t.x, t.y)))
                    break
    return out


def candidates(sess, m, u, pose, right_angles=False):
    """Trial poses for part u (see the module docstring)."""
    x, y, rot, side = pose
    out = []
    for d in (0.25, 0.5, 1.0, 2.0):
        for k in range(8):
            a = math.pi * k / 4
            out.append((x + d * math.cos(a), y + d * math.sin(a), rot, side))
    steps = (90, 180, 270) if right_angles else (15, 30, 45, 90, 180, 270, 315, 330, 345)
    for r in steps:
        out.append((x, y, (rot + r) % 360.0, side))
    part = _partners(sess, m, u)
    f = sess.ctx.fp[u]
    if len(part) >= 1:
        pads = {p.number: p for p in f.pads}
        tx = sum(q[0] for _, q in part) / len(part)
        ty = sum(q[1] for _, q in part) / len(part)
        rots = [rot]
        if len(part) >= 2 and part[0][0] in pads and part[1][0] in pads:
            p0, p1 = pads[part[0][0]], pads[part[1][0]]
            s = -1.0 if side == "B" else 1.0
            # library-frame vector between the two pads and the board-frame vector between partners
            lv = math.atan2(-(p1.ly - p0.ly) * s, p1.lx - p0.lx)
            bv = math.atan2(-(part[1][1][1] - part[0][1][1]), part[1][1][0] - part[0][1][0])
            th = math.degrees(bv - lv) % 360.0
            if right_angles:
                th = round(th / 90.0) * 90.0 % 360.0
            rots = [th, (th + 180.0) % 360.0, rot]
        for r in rots:
            for frac in (0.25, 0.5, 0.75, 1.0):
                out.append((x + frac * (tx - x), y + frac * (ty - y), r, side))
    return out


# ----------------------------------------------------------------------------- the optimizer
def _active_parts(m):
    """The parts whose pose decides the module's physics: a cell's loop parts and input
    caps, a decap's capacitors, a crystal and its load capacitors, a chain's protectors."""
    s = m.spec
    if m.kind == "cell":
        out = [x[0] for x in s.get("loop") or []] + list(s.get("caps") or [])
    elif m.kind == "decap":
        out = list(s.get("hf_caps") or s.get("caps") or [])
    elif m.kind == "crystal":
        out = [s.get("crystal")] + list(s.get("load_caps") or [])
    elif m.kind == "chain":
        out = list(s.get("protection") or [])
    else:
        out = list(m.parts)
    return [u for u in dict.fromkeys(out) if u]


def _rip(sess, m):
    sess.space.remove(m.copper)
    m.copper = []
    m.hops = {}
    m.vias = {}
    m.status = "pending"
    m.physics = {}
    m.notes = []
    for k in ("_T", "_loops", "_nets"):
        m.spec.pop(k, None)


def optimize_modules(board, brief, terms=None, locked=(), info=None, poses=None, opts=None, log=None,
                     time_s=120.0, top_k=6, passes=2, rails=True, session=None):
    """Co-optimize each module's movable parts and its critical copper (see the module
    docstring). Returns (poses, copper, report): poses {uuid: (x, y, rot, side)} of the parts
    that moved, copper (tracks, vias) as kae.board.model objects (locked), and a report."""
    from .critical import Session
    t0 = time.monotonic()
    log = log or (lambda *a: None)
    sess = session or Session(board.path, brief=brief, info=info, opts=dict(opts or {}, rails="none"), log=log,
                              board=board, terms=terms)
    leg = Legality(sess)
    if poses:
        for u, p in poses.items():
            if u in leg.poses and tuple(p) != tuple(leg.poses[u]) and p[3] == leg.poses[u][3]:
                leg.commit(u, tuple(p))
    ctx = sess.ctx
    locked = set(locked or ())
    mods = modules_from_brief(brief, sess.opts["kinds"])
    owner = {}
    for m in mods:
        for u in m.parts:
            owner.setdefault(u, set()).add(m.id)
    cur_poses = dict(leg.poses)
    moved = {}
    rep = dict(modules=[])
    for m in mods:
        route_module(ctx, m)
        v0 = m.physics.get("value")
        mrep = dict(id=m.id, kind=m.kind, value0=v0, u0=m.physics.get("u"), moves=[])
        movable = []
        for u in _active_parts(m):
            f = ctx.fp.get(u)
            if f is None or u in locked or f.locked or len(owner.get(u, ())) > 1 or not f.on_board:
                continue
            kind = (ctx.parts.get(u) or {}).get("kind")
            if kind in ("connector", "mounting_hole", "mechanical"):
                continue
            movable.append(u)
        mrep["movable"] = [ctx.fp[u].ref for u in movable]
        best = v0
        for _ in range(passes):
            if v0 is None or not movable or time.monotonic() - t0 > time_s:
                break
            improved = False
            for u in movable:
                f = ctx.fp[u]
                pose = cur_poses[u]
                ok_status = m.status
                # the module's own copper is re-routed for every trial: candidates are
                # checked against everything else
                _rip(sess, m)
                cands = candidates(sess, m, u, pose, right_angles=heatsink_mount(f))
                legal = [c for c in cands if leg.ok(u, c)[0]]
                if terms is not None and legal:
                    base = dict(cur_poses)
                    try:
                        legal.sort(key=lambda c: terms.delta(base, [u], [c]))
                    except Exception:  # noqa: BLE001 - screening is optional
                        pass
                for c in legal[:top_k]:
                    leg.commit(u, c)
                    route_module(ctx, m)
                    v = m.physics.get("value")
                    good = m.status == "routed" or (m.status == "partial" and ok_status != "routed")
                    if (v is not None and math.isfinite(v) and v > 0 and best is not None
                            and v < best - 0.01 * abs(best) and good):
                        best = v
                        mrep["moves"].append(dict(part=f.ref, pose=[round(z, 4) if isinstance(z, float) else z for z in c],
                                                  value=round(v, 4)))
                        cur_poses[u] = c
                        moved[u] = c
                        improved = True
                    _rip(sess, m)
                    leg.commit(u, cur_poses[u])
                # leave the module routed at the kept pose
                route_module(ctx, m)
            if not improved:
                break
        mrep.update(value=m.physics.get("value"), u=m.physics.get("u"), status=m.status)
        rep["modules"].append(mrep)
        log(f"{m.id}: {mrep['value0']} -> {mrep['value']} {m.physics.get('unit', '')} "
            f"({len(mrep['moves'])} moves of {mrep['movable']})")
    sess.modules = mods
    if rails and sess.opts.get("rails_joint", "auto") != "none":
        from .critical_rails import route_rails
        sess.rails = route_rails(ctx, mode=sess.opts.get("rails_joint", "auto"))
        rep["rails"] = sess.rails
    if sess.opts.get("corner_joins", True):
        rep["joins"] = sess.join_at_corners()
    tracks, vias = sess.copper()
    rep["seconds"] = round(time.monotonic() - t0, 2)
    rep["moved"] = {ctx.fp[u].ref: p for u, p in moved.items()}
    return moved, tracks + vias, rep
