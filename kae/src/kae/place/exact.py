# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact legality, kept per part so a placement can be repaired against it in a loop.

`ExactModel(P, st)` holds every part's shapes at its pose (deflated courtyards per side,
pad and hole shapes, footprint cut-outs, the rule areas it owns) and checks the rules KiCad
reports for a placement, as `legalize.exact_check` always did (it now delegates here):

- env (one part against the board): pads outside the outline, copper-to-edge clearance,
  fixed copper of other nets, board-level rule areas;
- pairs (two parts, found by their clearance envelopes): courtyard overlap per side, holes
  inside another courtyard, pad clearance per copper side, pads near or courtyards over
  another part's cut-out, pads or courtyards inside another part's rule area.

Severities follow the project (Problem.is_error). `findings_at(i, X, Y, K)` prices a trial
pose of one part without committing it, so a repair can try many spots per second.

`repair(P, st, ...)` is the closed loop on top: exact findings -> the movable parts that
cause them -> each moved to the nearest spot that is free on the grid (a prefilter) AND
exactly clean, evicting smaller parts when no free spot is, round after round until the
placement is exactly legal or the time is up; what it could not fix is reported per part
with the reason (`diagnose`: no room for it even with every movable part gone, the board
side too full, or a crowded region).

KiCad's own DRC closes the loop where this model is blind (a footprint's solder-mask
aperture drawn beyond its courtyard, custom rules): `kicad_feedback(P, st, report)` turns
every placement error into a constraint kept on P (`P.feedback`: a pair of parts keeps a
minimum separation, or a part keeps off a spot) that ExactModel reports as `kicad_feedback`
until satisfied, so the next repair round moves the culprit and later checks keep it away.
"""
from __future__ import annotations

import time

import numpy as np
import shapely

from kae.board import transform

from .problem import edge_cut_polys, geom_to_lib, keepout_sides

AREA_EPS = 1e-6


class ExactModel:
    def __init__(self, P, st):
        from .legalize import _copper_sides
        self.P, self.st = P, st
        self.deflate = P.max_error
        self.clr_of = {}
        fbs = (getattr(P, "feedback", None) or {}).get("sep", {})
        self.reach = max([P.clr_max, P.edge_clearance] + list(fbs.values())) + 0.05
        self._copper_sides = _copper_sides
        owner_of = {p.uuid: p.i for p in P.parts}
        self.ko_board, self.ko_owned = [], {}
        if P.is_error("items_not_allowed"):
            for ko in P.board.keepouts:
                if not (ko.footprints or ko.pads):
                    continue
                sides = keepout_sides(ko)
                if not sides:
                    continue
                oi = owner_of.get(ko.footprint) if ko.footprint else None
                if oi is None:
                    self.ko_board.append((ko, sides, ko.outline))
                else:
                    q = P.parts[oi]
                    self.ko_owned.setdefault(oi, []).append(
                        (ko, sides, geom_to_lib(ko.outline, q.x0, q.y0, q.rot0, q.fp.side)))
        self.cuts = {p.i: edge_cut_polys(p.fp) for p in P.parts}
        self.cs = {p.i: [self._copper_sides(pd, p.side) for pd in p.fp.pads] for p in P.parts}
        fb = getattr(P, "feedback", None) or {}
        self.sep = fb.get("sep", {})          # (i, j) i < j -> min distance (mm), from KiCad
        self.avoid = fb.get("avoid", {})      # i -> [(geometry, why)], from KiCad
        n = len(P.parts)
        self.env = np.zeros((n, 4))
        self.sh = [None] * n
        for p in P.parts:
            self.sh[p.i] = self._shapes(p.i, st.pose(p.i))
            self.env[p.i] = self.sh[p.i]["env"]

    # ------------------------------------------------------------------ shapes
    def _shapes(self, i, pose):
        from .legalize import hole_shape, pad_shape
        P = self.P
        p = P.parts[i]
        fp = p.fp
        x, y, rot, side = pose
        own = transform.courtyard(fp, x, y, rot, side, which="own", deflate=self.deflate)
        back = transform.courtyard(fp, x, y, rot, side, which="opposite", deflate=self.deflate)
        pads, holes = [], []
        for k, pd in enumerate(fp.pads):
            pads.append((transform.place_geom(pad_shape(pd), x, y, rot, side), k, pd))
            if pd.drill:
                holes.append((transform.place_geom(hole_shape(pd), x, y, rot, side), k))
        si = 0 if p.s > 0 else 1
        cy = {si: shapely.union_all(own) if own else None, 1 - si: shapely.union_all(back) if back else None}
        cuts = [transform.place_geom(c, x, y, rot, side) for c in self.cuts[i]]
        kos = [(ko, sides, transform.place_geom(lib, x, y, rot, side)) for ko, sides, lib in self.ko_owned.get(i, ())]
        geoms = [g for g, _, _ in pads] + [c for c in cy.values() if c is not None] + cuts + [g for _, _, g in kos]
        if geoms:
            b = np.array([g.bounds for g in geoms])
            env = (b[:, 0].min() - self.reach, b[:, 1].min() - self.reach, b[:, 2].max() + self.reach,
                   b[:, 3].max() + self.reach)
        else:
            env = (x, y, x, y)
        return dict(cy=cy, pads=pads, holes=holes, side=si, cuts=cuts, kos=kos, env=env)

    @staticmethod
    def hull(A):
        """A part's pads and courtyards as one geometry (for KiCad-feedback separations)."""
        if "hull" not in A:
            gs = [g for g, _, _ in A["pads"]] + [c for c in A["cy"].values() if c is not None]
            A["hull"] = shapely.union_all(gs) if gs else None
        return A["hull"]

    def neighbours(self, env, skip=None):
        e = self.env
        m = (e[:, 0] <= env[2]) & (e[:, 2] >= env[0]) & (e[:, 1] <= env[3]) & (e[:, 3] >= env[1])
        out = np.nonzero(m)[0].tolist()
        return [j for j in out if j != skip]

    def set_pose(self, i, X, Y, K):
        st = self.st
        st.X[i], st.Y[i], st.K[i] = X, Y, K
        self.sh[i] = self._shapes(i, st.pose(i))
        self.env[i] = self.sh[i]["env"]

    # ------------------------------------------------------------------ rules
    def _net_clr(self, net):
        from .legalize import _net_clr
        return _net_clr(self.P, net, self.clr_of)

    def _env(self, i, A, add):
        P = self.P
        ref = P.parts[i].ref
        outline = P.outline
        boundary = outline.boundary
        e = P.edge_clearance
        for geom, k, pd in A["pads"]:
            if not outline.contains(geom.centroid):
                add("pad_outside", [ref], pd.number)
            elif e > 0 and geom.distance(boundary) < e - 1e-4:
                add("copper_edge_clearance", [ref], f"{pd.number} {geom.distance(boundary):.3f}<{e}")
            elif not outline.contains(geom):
                add("copper_edge_clearance", [ref], f"{pd.number} crosses the edge")
        for side, gm, net in getattr(P, "fixed_copper", []):
            for geom, k, pd in A["pads"]:
                if side not in self.cs[i][k] or (net and pd.net == net):
                    continue
                need = max(self._net_clr(pd.net), self._net_clr(net))
                if geom.distance(gm) < need - 1e-4:
                    add("clearance", [ref], f"pad {pd.number} vs fixed copper {net}")
        for ko, sides, outline_k in self.ko_board:
            self._keepout(i, A, ko, sides, outline_k, add)
        for g, why in self.avoid.get(i, ()):
            h = self.hull(A)
            if h is not None and h.intersects(g):
                add("kicad_feedback", [ref], why)

    def _keepout(self, i, A, ko, sides, outline_k, add):
        if A["side"] not in sides:
            return
        ref = self.P.parts[i].ref
        if ko.footprints:
            c = A["cy"].get(A["side"])
            if c is not None and c.intersects(outline_k) and c.intersection(outline_k).area > AREA_EPS:
                add("items_not_allowed", [ref], f"keepout {ko.name}")
                return
        if ko.pads and any(g.intersects(outline_k) for g, _, _ in A["pads"]):
            add("items_not_allowed", [ref], f"keepout {ko.name} (pads)")

    def _pair(self, i, A, j, B, add):
        P = self.P
        ri, rj = P.parts[i].ref, P.parts[j].ref
        if P.is_error("courtyards_overlap"):
            for side in (0, 1):
                ca, cb = A["cy"].get(side), B["cy"].get(side)
                if ca is not None and cb is not None and ca.intersects(cb) and ca.intersection(cb).area > AREA_EPS:
                    add("courtyards_overlap", [ri, rj], "FB"[side])
        for (X, Y, rx, ry) in ((A, B, ri, rj), (B, A, rj, ri)):
            for hgeom, k in X["holes"]:
                kind = "npth_inside_courtyard" if X["pads"][k][2].kind == "np_thru_hole" else "pth_inside_courtyard"
                if not P.is_error(kind):
                    continue
                for side in (0, 1):
                    c = Y["cy"].get(side)
                    if c is not None and hgeom.intersects(c):
                        add(kind, [rx, ry], "FB"[side])
        csi, csj = self.cs[i], self.cs[j]
        for side in (0, 1):
            pa = [(g, k, pd) for g, k, pd in A["pads"] if side in csi[k]]
            pb = [(g, k, pd) for g, k, pd in B["pads"] if side in csj[k]]
            if not pa or not pb:
                continue
            ga = np.array([g for g, _, _ in pa], dtype=object)
            gb = np.array([g for g, _, _ in pb], dtype=object)
            near = shapely.dwithin(ga[:, None], gb[None, :], P.clr_max)
            for a, b in zip(*np.nonzero(near)):
                da, db = pa[a][2], pb[b][2]
                if da.net and da.net == db.net:
                    continue
                need = max(self._net_clr(da.net), self._net_clr(db.net))
                d = ga[a].distance(gb[b])
                if d < need - 1e-4:
                    add("clearance", [ri, rj], f"{da.number}-{db.number} {d:.3f}<{need:.3f}")
        e = P.edge_clearance
        for (X, Y, rx, ry) in ((A, B, ri, rj), (B, A, rj, ri)):
            for cg in Y["cuts"]:
                cb = cg.boundary
                for geom, k, pd in X["pads"]:
                    if geom.distance(cb) < e - 1e-4 or cg.contains(geom.centroid):
                        add("copper_edge_clearance", [rx, ry], f"{pd.number} near the cut-out of {ry}")
                cyo = X["cy"].get(X["side"])
                if cyo is not None and cyo.intersection(cg).area > AREA_EPS:
                    add("over_cutout", [rx, ry], "courtyard over a cut-out")
        for (x, X, Y) in ((i, A, B), (j, B, A)):
            for ko, sides, outline_k in Y["kos"]:
                self._keepout(x, X, ko, sides, outline_k, add)
        d = self.sep.get((min(i, j), max(i, j)))
        if d:
            ha, hb = self.hull(A), self.hull(B)
            if ha is not None and hb is not None and ha.distance(hb) < d - 1e-6:
                add("kicad_feedback", [ri, rj], f"keep {d:.2f} mm apart (KiCad DRC)")

    # ------------------------------------------------------------------ queries
    def check(self, parts=None, max_items=60):
        """Findings of `parts` (default: the movable ones) against everything."""
        P = self.P
        check = set(P.mov if parts is None else parts)
        out = []

        def add(kind, refs, detail=""):
            if len(out) < max_items:
                out.append(dict(type=kind, refs=refs, detail=detail))
        for i in sorted(check):
            A = self.sh[i]
            self._env(i, A, add)
            for j in self.neighbours(A["env"], skip=i):
                if j in check and j < i:
                    continue
                self._pair(i, A, j, self.sh[j], add)
        return out

    def part_findings(self, i, max_items=1000):
        return self.findings_at(i, None, None, None, max_items=max_items)

    def findings_at(self, i, X, Y, K, max_items=1000, first=False):
        """Findings of part i (default: where it is; else at grid pose X, Y, K, not
        committed). first=True stops at the first one."""
        if X is None:
            A = self.sh[i]
        else:
            st = self.st
            saved = (st.X[i], st.Y[i], st.K[i])
            st.X[i], st.Y[i], st.K[i] = X, Y, K
            try:
                A = self._shapes(i, st.pose(i))
            finally:
                st.X[i], st.Y[i], st.K[i] = saved
        out = []

        class _Stop(Exception):
            pass

        def add(kind, refs, detail=""):
            if len(out) < max_items:
                out.append(dict(type=kind, refs=refs, detail=detail))
            if first:
                raise _Stop
        try:
            self._env(i, A, add)
            for j in self.neighbours(A["env"], skip=i):
                self._pair(i, A, j, self.sh[j], add)
        except _Stop:
            pass
        return out


# ----------------------------------------------------------------------------- repair
def culprits(P, findings):
    """Movable parts to move for a list of findings, biggest first: a finding with one
    movable part names it; with two, the smaller one (it finds room more easily) unless the
    bigger one is the one out of the board."""
    by_ref = {p.ref: p.i for p in P.parts}
    out = {}
    for v in findings:
        mv = [by_ref[r] for r in v["refs"] if r in by_ref and P.parts[by_ref[r]].movable]
        if not mv:
            continue
        i = min(mv, key=lambda q: P.parts[q].area) if len(mv) > 1 else mv[0]
        out[i] = out.get(i, 0) + 1
    return sorted(out, key=lambda q: -P.parts[q].area)


def _candidates(P, st, i, S, pad, ks, w_rot, limit):
    """Grid-free origins for part i (rotations ks) by L1 distance (+ w_rot when turning) from
    where it is, at most `limit`: [(cost, X, Y, k)]."""
    from .legalize import _inside_origins
    p = P.parts[i]
    si = 0 if p.s > 0 else 1
    X0, Y0, K0 = int(st.X[i]), int(st.Y[i]), int(st.K[i])
    nx, ny = P.ncx, P.ncy
    dist = np.abs(np.arange(nx)[:, None] - X0) + np.abs(np.arange(ny)[None, :] - Y0)
    out = []
    for k in ks:
        r = p.rots[k]
        ok = np.ones((nx, ny), dtype=bool)
        for brd in (r.g_boards or (r.g_board,)):
            ok &= _inside_origins(P, brd, 0, nx - 1, 0, ny - 1)
        for side, rect in [(si, o) for o in (r.g_own_rects or (r.g_own,))] + [(1 - si, o) for o in r.g_opp]:
            if not ok.any():
                break
            a, b, c, d = rect
            T = S[side]
            cnt = (T[b + pad:b + pad + nx, d + pad:d + pad + ny] - T[a + pad:a + pad + nx, d + pad:d + pad + ny]
                   - T[b + pad:b + pad + nx, c + pad:c + pad + ny] + T[a + pad:a + pad + nx, c + pad:c + pad + ny])
            ok &= cnt == 0
        xs, ys = np.nonzero(ok)
        if len(xs) == 0:
            continue
        c = dist[xs, ys] + (w_rot if k != K0 else 0.0)
        sel = np.argsort(c, kind="stable")[:limit]
        out += [(float(c[q]), int(xs[q]), int(ys[q]), k) for q in sel]
    out.sort()
    return out[:limit]


def _tables(P, st, skip):
    from .legalize import _occupancy
    from .problem import sat
    ext = 1
    for i in P.mov:
        for r in P.parts[i].rots:
            for (a, b, c, d) in (r.g_own,) + tuple(r.g_opp):
                ext = max(ext, -a, b, -c, d)
    pad = ext + 1
    occ = _occupancy(P, st, skip, pad)
    return [sat(occ[0]), sat(occ[1])], pad


def move_clean(P, st, E, i, deadline, w_rot=4.0, limit=600, evict=True):
    """Move part i to the nearest spot that is grid-free (others where they are) and exactly
    clean; with evict, else to the nearest exactly clean spot where it only covers smaller
    movable parts, which are then re-placed the same way. Returns (moved, evicted refs)."""
    p = P.parts[i]
    ks = list(range(len(p.rots)))
    S, pad = _tables(P, st, {i})
    for c, X, Y, k in _candidates(P, st, i, S, pad, ks, w_rot, limit):
        if time.monotonic() > deadline:
            return False, []
        if not E.findings_at(i, X, Y, k, first=True):
            E.set_pose(i, X, Y, k)
            return True, []
    if not evict:
        return False, []
    # evict: grid tables without the smaller movable parts; the spot must be exactly clean
    # against everything but them, and they move out after
    small = {j for j in P.mov if j != i and P.parts[j].area < p.area}
    S2, pad2 = _tables(P, st, small | {i})
    for c, X, Y, k in _candidates(P, st, i, S2, pad2, ks, w_rot, limit):
        if time.monotonic() > deadline:
            return False, []
        f = E.findings_at(i, X, Y, k)
        refs = {r for v in f for r in v["refs"]} - {p.ref}
        by_ref = {P.parts[j].ref: j for j in small}
        if any(r not in by_ref for r in refs):
            continue
        E.set_pose(i, X, Y, k)
        out = []
        for r in sorted(refs, key=lambda r: -P.parts[by_ref[r]].area):
            ok, _ = move_clean(P, st, E, by_ref[r], deadline, w_rot, limit, evict=False)
            out.append(r)
        return True, out
    return False, []


def repair(P, st, time_s=30.0, log=None, rounds=8, w_rot=4.0):
    """Closed loop on the exact check: findings -> culprits -> moved to exactly clean spots,
    until no finding is left or the time is up. Returns a report (start/end findings,
    parts moved, evicted, parts left with their findings)."""
    t0 = time.monotonic()
    deadline = t0 + time_s
    E = ExactModel(P, st)
    found = E.check(max_items=100000)
    rep = dict(start=len(found), rounds=0, moved=[], evicted=[], stuck=[])
    for _ in range(rounds):
        if not found or time.monotonic() > deadline:
            break
        rep["rounds"] += 1
        progress = False
        for i in culprits(P, found):
            if time.monotonic() > deadline:
                break
            if not E.part_findings(i, max_items=1):
                continue
            ok, ev = move_clean(P, st, E, i, deadline, w_rot=w_rot)
            if ok:
                progress = True
                rep["moved"].append(P.parts[i].ref)
                rep["evicted"] += ev
        found = E.check(max_items=100000)
        if not progress:
            break
    left = {}
    by_ref = {p.ref: p.i for p in P.parts}
    for v in found:
        for r in v["refs"]:
            if r in by_ref and P.parts[by_ref[r]].movable:
                left.setdefault(r, []).append(v["type"])
    rep["stuck"] = sorted(left)
    rep["end"] = len(found)
    rep["findings"] = found[:60]
    rep["seconds"] = round(time.monotonic() - t0, 2)
    if log:
        log(f"exact repair: {rep['start']} -> {rep['end']} findings in {rep['rounds']} rounds, "
            f"moved {len(rep['moved'])}, evicted {len(rep['evicted'])} ({rep['seconds']}s)")
    return rep


# ----------------------------------------------------------------------------- KiCad feedback
def kicad_feedback(P, st, report, step=0.3):
    """Turn KiCad DRC placement errors (a kicad-cli JSON report) into constraints on P
    (P.feedback): two parts an error names keep their current distance + `step` (growing each
    time KiCad still objects); a part an error names alone (against a zone, a graphic, a
    track) keeps off the error's positions by `step`. Returns {errors, by_type, constraints,
    fixed_only}: errors between fixed items only cannot be repaired by placement."""
    from .legalize import kicad_violations, violation_parts
    viols = kicad_violations(report)
    fb = getattr(P, "feedback", None)
    if fb is None:
        fb = P.feedback = {"sep": {}, "avoid": {}}
    E = ExactModel(P, st)
    out = dict(errors=len(viols), by_type={}, constraints=0, fixed_only=0)
    for v in viols:
        out["by_type"][v["type"]] = out["by_type"].get(v["type"], 0) + 1
        ps = sorted(violation_parts(P, st, v))
        mv = [i for i in ps if P.parts[i].movable]
        if not mv:
            out["fixed_only"] += 1
            continue
        if len(ps) >= 2:
            for i in mv:
                for j in ps:
                    if j == i:
                        continue
                    key = (min(i, j), max(i, j))
                    ha, hb = E.hull(E.sh[i]), E.hull(E.sh[j])
                    d = ha.distance(hb) if ha is not None and hb is not None else 0.0
                    fb["sep"][key] = max(fb["sep"].get(key, 0.0), d + step)
                    out["constraints"] += 1
        else:
            i = mv[0]
            for it in v.get("items", []):
                pos = it.get("pos") or {}
                if "x" in pos and "y" in pos:
                    g = shapely.Point(pos["x"], pos["y"]).buffer(step)
                    fb["avoid"].setdefault(i, []).append((g, f"{v['type']} at ({pos['x']:.2f}, {pos['y']:.2f}) (KiCad DRC)"))
                    out["constraints"] += 1
    return out


# ----------------------------------------------------------------------------- diagnosis
def diagnose(P, st, E, i, limit=400):
    """Why part i found no clean spot: 'no_room' (not even with every other movable part
    gone: the outline, locked parts and rule areas leave none), 'side_full' (the movable
    parts' own area on its side exceeds the free area), else 'crowded' (room exists, the
    neighbours fill it). Returns {reason, detail}."""
    p = P.parts[i]
    S, pad = _tables(P, st, set(P.mov))
    fixed = {q.ref for q in P.parts if not q.movable} | {p.ref}
    cands = _candidates(P, st, i, S, pad, list(range(len(p.rots))), 4.0, limit)
    clean = None
    for c, X, Y, k in cands:
        f = E.findings_at(i, X, Y, k)
        if not [v for v in f if set(v["refs"]) <= fixed]:
            clean = (X, Y, k)
            break
    if clean is None:
        return dict(reason="no_room", detail=f"{p.ref}: no spot clean of the outline, locked parts and rule areas "
                                             f"({len(cands)} grid-free origins tried)")
    si = 0 if p.s > 0 else 1
    util = P.utilization()[si]
    if util > 1.0:
        return dict(reason="side_full", detail=f"{p.ref}: the movable parts need {100 * util:.0f}% of the free "
                                               f"area on side {'FB'[si]}")
    return dict(reason="crowded", detail=f"{p.ref}: room exists (e.g. grid {clean}) but its region is full")


def close_loop(P, st, time_s, log=None):
    """The closed legality loop at the end of a placement: exact repair, then for whatever is
    left, why. Returns the repair report with 'diagnosis' {ref: {reason, detail}}."""
    rep = repair(P, st, time_s=time_s, log=log)
    if rep["stuck"]:
        E = ExactModel(P, st)
        by_ref = {q.ref: q.i for q in P.parts}
        rep["diagnosis"] = {r: diagnose(P, st, E, by_ref[r]) for r in rep["stuck"][:12]}
        if log:
            for r, d in rep["diagnosis"].items():
                log(f"illegal: {d['reason']}: {d['detail']}")
    return rep
