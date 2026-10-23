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


def _local_clr(pd):
    """A pad's local clearance override (pad or footprint level, KiCad's 'clearance'), 0 when
    the board model does not carry one."""
    return float(getattr(pd, "clearance", 0.0) or 0.0)


class ExactModel:
    def __init__(self, P, st):
        from .legalize import _copper_sides
        self.P, self.st = P, st
        self.deflate = P.max_error
        self.clr_of = {}
        fbs = (getattr(P, "feedback", None) or {}).get("sep", {})
        rules = getattr(P.board, "rules", None)
        holes = [float(getattr(rules, k, 0.0) or 0.0) for k in ("hole_clearance", "hole_to_hole")] if rules else []
        loc = [max([_local_clr(pd) for pd in q.fp.pads] or [0.0]) for q in P.parts]
        self.reach = max([P.clr_max, P.edge_clearance] + holes + loc + list(fbs.values())) + 0.05
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
        # graphics: library F.* is the part's own side
        gfx = {"cu": {0: [], 1: []}, "mask": {0: [], 1: []}}
        for ly, polys in (getattr(fp, "graphics", None) or {}).items():
            kind = "cu" if ly.endswith(".Cu") else "mask" if ly.endswith(".Mask") else None
            if kind is None:
                continue
            bs = si if ly.startswith("F.") else 1 - si
            gfx[kind][bs] += [transform.place_geom(g, x, y, rot, side) for g in polys if not g.is_empty]
        geoms = [g for g, _, _ in pads] + [c for c in cy.values() if c is not None] + cuts + [g for _, _, g in kos] + \
            [g for d in gfx.values() for v in d.values() for g in v]
        if geoms:
            b = np.array([g.bounds for g in geoms])
            env = (b[:, 0].min() - self.reach, b[:, 1].min() - self.reach, b[:, 2].max() + self.reach,
                   b[:, 3].max() + self.reach)
        else:
            env = (x, y, x, y)
        return dict(cy=cy, pads=pads, holes=holes, side=si, cuts=cuts, kos=kos, gfx=gfx, env=env)

    @staticmethod
    def hull(A):
        """A part's pads and courtyards as one geometry (for KiCad-feedback separations)."""
        if "hull" not in A:
            gs = [g for g, _, _ in A["pads"]] + [c for c in A["cy"].values() if c is not None] + \
                [g for d in A["gfx"].values() for v in d.values() for g in v]
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
        ok_out = getattr(P.parts[i], "outside_ok", ())
        for geom, k, pd in A["pads"]:
            if k in ok_out:
                continue        # a straddling part's outer pads (Problem._straddle_check)
            if not outline.contains(geom.centroid):
                add("pad_outside", [i], pd.number)
            elif e > 0 and geom.distance(boundary) < e - 1e-4:
                add("copper_edge_clearance", [i], f"{pd.number} {geom.distance(boundary):.3f}<{e}")
            elif not outline.contains(geom):
                add("copper_edge_clearance", [i], f"{pd.number} crosses the edge")
        for side, gm, net in getattr(P, "fixed_copper", []):
            for geom, k, pd in A["pads"]:
                if side not in self.cs[i][k] or (net and pd.net == net):
                    continue
                need = max(self._net_clr(pd.net), self._net_clr(net))
                if geom.distance(gm) < need - 1e-4:
                    add("clearance", [i], f"pad {pd.number} vs fixed copper {net}")
        for ko, sides, outline_k in self.ko_board:
            self._keepout(i, A, ko, sides, outline_k, add, None)
        for g, why in self.avoid.get(i, ()):
            h = self.hull(A)
            if h is not None and h.intersects(g):
                add("kicad_feedback", [i], why)

    def _keepout(self, i, A, ko, sides, outline_k, add, owner):
        if A["side"] not in sides:
            return
        who = [i] if owner is None else [i, owner]
        if ko.footprints:
            c = A["cy"].get(A["side"])
            if c is not None and c.intersects(outline_k) and c.intersection(outline_k).area > AREA_EPS:
                add("items_not_allowed", who, f"keepout {ko.name}")
                return
        if ko.pads and any(g.intersects(outline_k) for g, _, _ in A["pads"]):
            add("items_not_allowed", who, f"keepout {ko.name} (pads)")

    def _pair(self, i, A, j, B, add):
        P = self.P
        if P.is_error("courtyards_overlap"):
            for side in (0, 1):
                ca, cb = A["cy"].get(side), B["cy"].get(side)
                if ca is not None and cb is not None and ca.intersects(cb) and ca.intersection(cb).area > AREA_EPS:
                    add("courtyards_overlap", [i, j], "FB"[side])
        for (X, Y, rx, ry) in ((A, B, i, j), (B, A, j, i)):
            for hgeom, k in X["holes"]:
                kind = "npth_inside_courtyard" if X["pads"][k][2].kind == "np_thru_hole" else "pth_inside_courtyard"
                if not P.is_error(kind):
                    continue
                for side in (0, 1):
                    c = Y["cy"].get(side)
                    if c is not None and hgeom.intersects(c):
                        add(kind, [rx, ry], "FB"[side])
        # holes against other copper (KiCad hole_clearance) and other holes (hole_to_hole)
        rules = getattr(P.board, "rules", None)
        hc = float(getattr(rules, "hole_clearance", 0.0) or 0.0) if rules is not None else 0.0
        hh = float(getattr(rules, "hole_to_hole", 0.0) or 0.0) if rules is not None else 0.0
        if hc > 0 and P.is_error("hole_clearance"):
            for (X, Y, rx, ry) in ((A, B, i, j), (B, A, j, i)):
                for hgeom, k in X["holes"]:
                    hnet = X["pads"][k][2].net
                    hloc = _local_clr(X["pads"][k][2])
                    for geom, l, pd in Y["pads"]:
                        if hnet and pd.net == hnet:
                            continue
                        if hgeom.distance(geom) < max(hc, hloc, _local_clr(pd)) - 1e-4:
                            add("hole_clearance", [rx, ry], f"hole {X['pads'][k][2].number} - pad {pd.number}")
        if hh > 0 and P.is_error("hole_to_hole"):
            for ha, _ in A["holes"]:
                for hb, _ in B["holes"]:
                    if ha.distance(hb) < hh - 1e-4:
                        add("hole_to_hole", [i, j], "holes")
        csi, csj = self.cs[i], self.cs[j]
        for side in (0, 1):
            pa = [(g, k, pd) for g, k, pd in A["pads"] if side in csi[k]]
            pb = [(g, k, pd) for g, k, pd in B["pads"] if side in csj[k]]
            if not pa or not pb:
                continue
            ga = np.array([g for g, _, _ in pa], dtype=object)
            gb = np.array([g for g, _, _ in pb], dtype=object)
            near = shapely.dwithin(ga[:, None], gb[None, :], max([P.clr_max] + [_local_clr(q) for _, _, q in pa + pb]))
            for a, b in zip(*np.nonzero(near)):
                da, db = pa[a][2], pb[b][2]
                if da.net and da.net == db.net:
                    continue
                need = max(self._net_clr(da.net), self._net_clr(db.net), _local_clr(da), _local_clr(db))
                d = ga[a].distance(gb[b])
                if d < need - 1e-4:
                    add("clearance", [i, j], f"{da.number}-{db.number} {d:.3f}<{need:.3f}")
        # graphics: a mask aperture over another part's pads bridges them (KiCad's
        # solder_mask_bridge); copper graphics keep copper clearance
        for (X, Y, rx, ry, cy_) in ((A, B, i, j, csj), (B, A, j, i, csi)):
            for side in (0, 1):
                masks, cus = X["gfx"]["mask"][side], X["gfx"]["cu"][side]
                if not masks and not cus:
                    continue
                for geom, k, pd in Y["pads"]:
                    if side not in cy_[k]:
                        continue
                    if masks and P.is_error("solder_mask_bridge") and any(m.intersects(geom) for m in masks):
                        add("solder_mask_bridge", [rx, ry], f"mask graphic over pad {pd.number}")
                    need = self._net_clr(pd.net)
                    if cus and any(c.distance(geom) < need - 1e-4 for c in cus):
                        add("clearance", [rx, ry], f"copper graphic near pad {pd.number}")
                if cus and X is A:
                    for c in cus:
                        if any(c.distance(o) < P.clr_min - 1e-4 for o in Y["gfx"]["cu"][side]):
                            add("clearance", [rx, ry], "copper graphics")
        e = P.edge_clearance
        for (X, Y, rx, ry) in ((A, B, i, j), (B, A, j, i)):
            for cg in Y["cuts"]:
                cb = cg.boundary
                for geom, k, pd in X["pads"]:
                    if geom.distance(cb) < e - 1e-4 or cg.contains(geom.centroid):
                        add("copper_edge_clearance", [rx, ry], f"{pd.number} near a cut-out")
                cyo = X["cy"].get(X["side"])
                if cyo is not None and cyo.intersection(cg).area > AREA_EPS:
                    add("over_cutout", [rx, ry], "courtyard over a cut-out")
        for (x, X, Y, y) in ((i, A, B, j), (j, B, A, i)):
            for ko, sides, outline_k in Y["kos"]:
                self._keepout(x, X, ko, sides, outline_k, add, y)
        d = self.sep.get((min(i, j), max(i, j)))
        if d:
            ha, hb = self.hull(A), self.hull(B)
            if ha is not None and hb is not None and ha.distance(hb) < d - 1e-6:
                add("kicad_feedback", [i, j], f"keep {d:.2f} mm apart (KiCad DRC)")

    # ------------------------------------------------------------------ queries
    def check(self, parts=None, max_items=60):
        """Findings of `parts` (default: the movable ones) against everything."""
        P = self.P
        check = set(P.mov if parts is None else parts)
        out = []

        def add(kind, idx, detail=""):
            if len(out) < max_items:
                out.append(dict(type=kind, refs=[P.parts[q].ref for q in idx], parts=list(idx), detail=detail))
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
        P = self.P
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

        def add(kind, idx, detail=""):
            if len(out) < max_items:
                out.append(dict(type=kind, refs=[P.parts[q].ref for q in idx], parts=list(idx), detail=detail))
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
def culprits(P, findings, allowed=None):
    """Movable parts to move for a list of findings, biggest first: a finding with one
    movable part names it; with two, the smaller one (it finds room more easily) unless the
    bigger one is the one out of the board."""
    out = {}
    for v in findings:
        mv = [q for q in v["parts"] if P.parts[q].movable and (allowed is None or q in allowed)]
        if not mv:
            continue
        i = min(mv, key=lambda q: P.parts[q].area) if len(mv) > 1 else mv[0]
        out[i] = out.get(i, 0) + 1
    return sorted(out, key=lambda q: -P.parts[q].area)


def _candidates(P, st, i, S, pad, ks, w_rot, limit, edge=False):
    """Grid-free origins for part i (rotations ks) by L1 distance (+ w_rot when turning) from
    where it is, at most `limit`: [(cost, X, Y, k)]. edge=True ranks them by the distance of
    the part's own rectangle to the board's edge first (a big part hugging an edge leaves the
    rest of the board in one piece)."""
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
        if edge:
            a, b, c0, d = r.g_own
            de = np.minimum.reduce([np.maximum(xs + a, 0), np.maximum(nx - (xs + b), 0),
                                    np.maximum(ys + c0, 0), np.maximum(ny - (ys + d), 0)])
            # and the board area its pieces cover (a keepout or overhang hanging off is free)
            onb = np.zeros(len(xs))
            for (a1, b1, c1, d1) in tuple(r.g_own_rects or (r.g_own,)) + tuple(r.g_opp):
                onb += (np.clip(xs + b1, 0, nx) - np.clip(xs + a1, 0, nx)) * (np.clip(ys + d1, 0, ny) - np.clip(ys + c1, 0, ny))
            c = 20.0 * de + onb + 0.05 * c
        order = np.argsort(c, kind="stable")
        out += [(float(c[q]), int(xs[q]), int(ys[q]), k) for q in order[:limit]]
        # and a spread over the farther ones, so a crowded neighbourhood is not all it sees
        far = order[limit:]
        if len(far):
            out += [(float(c[q]), int(xs[q]), int(ys[q]), k) for q in far[::max(1, len(far) // limit)][:limit]]
    out.sort()
    near = out[:limit]
    rest = out[limit:]
    return near + rest[::max(1, len(rest) // limit)][:limit]


def _pad(P):
    ext = 1
    for i in P.mov:
        for r in P.parts[i].rots:
            for (a, b, c, d) in (r.g_own,) + tuple(r.g_opp):
                ext = max(ext, -a, b, -c, d)
    return ext + 1


def _tables(P, st, skip):
    from .legalize import _occupancy
    from .problem import sat
    pad = _pad(P)
    occ = _occupancy(P, st, skip, pad)
    return [sat(occ[0]), sat(occ[1])], pad


def move_clean(P, st, E, i, deadline, w_rot=4.0, limit=600, evict=True, allowed=None):
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
    small = {j for j in P.mov if j != i and P.parts[j].area < p.area and (allowed is None or j in allowed)}
    S2, pad2 = _tables(P, st, small | {i})
    for c, X, Y, k in _candidates(P, st, i, S2, pad2, ks, w_rot, limit):
        if time.monotonic() > deadline:
            return False, []
        f = E.findings_at(i, X, Y, k)
        # every finding there must name a part that moves out (one naming only part i, or a
        # bigger or fixed part, stays)
        if any(not (set(v["parts"]) - {i}) or not (set(v["parts"]) - {i}) <= small for v in f):
            continue
        out_parts = {q for v in f for q in v["parts"]} - {i}
        E.set_pose(i, X, Y, k)
        out = []
        for q in sorted(out_parts, key=lambda q: -P.parts[q].area):
            move_clean(P, st, E, q, deadline, w_rot, limit, evict=False, allowed=allowed)
            out.append(P.parts[q].ref)
        return True, out
    return False, []


PARK = -10 ** 6


def reseed(P, st, E, parts, deadline, edge=False, first=(), w_rot=4.0, limit=600):
    """Constructive re-placement of a crowded set: lift `parts` off the board, then put them
    back one by one (`first`, then biggest first), each at the exactly clean spot nearest
    where it was (edge=True: hugging the board's edge), grid-free against what is already
    back. A part with no such spot goes back where it was. Returns the parts that did."""
    order = [q for q in first if q in parts] + sorted([q for q in parts if q not in first],
                                                       key=lambda q: -P.parts[q].area)
    home = {q: (int(st.X[q]), int(st.Y[q]), int(st.K[q])) for q in order}
    for q in order:
        E.set_pose(q, PARK, PARK, home[q][2])
    from .legalize import _mark, _occupancy
    from .problem import sat
    lifted = set(order)
    failed = []
    board_area = max(1.0, P.outline.area)
    pad = _pad(P)
    occ = _occupancy(P, st, lifted, pad)        # obstacles and the parts not lifted

    def stamp(o, q):
        for side, r, _ in st.grid_rects(q):
            _mark(o[side], r, pad, 1)
    for n, q in enumerate(order):
        lifted.discard(q)
        st.X[q], st.Y[q], st.K[q] = home[q]
        S = [sat(occ[0]), sat(occ[1])]
        done = False
        # lookahead: the next big parts (each > 5% of the board) must still find a spot
        big = [j for j in order[n + 1:] if P.parts[j].area > 0.05 * board_area][:2]
        first_clean = None
        tries = 0
        if time.monotonic() < deadline:
            for c, X, Y, k in _candidates(P, st, q, S, pad, list(range(len(P.parts[q].rots))), w_rot, limit,
                                          edge=edge):
                if time.monotonic() > deadline:
                    break
                if E.findings_at(q, X, Y, k, first=True):
                    continue
                E.set_pose(q, X, Y, k)
                if first_clean is None:
                    first_clean = (X, Y, k)
                ok = True
                if big:
                    o2 = [o.copy() for o in occ]
                    stamp(o2, q)
                    S2 = [sat(o2[0]), sat(o2[1])]
                    for j in big:
                        sv = (int(st.X[j]), int(st.Y[j]), int(st.K[j]))
                        st.X[j], st.Y[j], st.K[j] = home[j]
                        ok = ok and bool(_candidates(P, st, j, S2, pad, list(range(len(P.parts[j].rots))), 0.0, 1))
                        st.X[j], st.Y[j], st.K[j] = sv
                tries += 1
                if ok:
                    done = True
                    break
                if tries > 300:
                    break
            if not done and first_clean is not None:
                E.set_pose(q, *first_clean)
                done = True
        if done:
            stamp(occ, q)
        if not done:
            E.set_pose(q, *home[q])
            failed.append(q)
    return failed


def _crowd(P, E, base, scope, grow):
    """The movable parts around `base` (their clearance envelopes grown by `grow` x their
    size), within scope; every movable part of a small board."""
    pool = [q for q in P.mov if scope is None or q in scope]
    if len(pool) <= 40 or grow >= 3:
        return set(pool)
    env = E.env[list(base)]
    w = max(1.0, float(np.max(np.maximum(env[:, 2] - env[:, 0], env[:, 3] - env[:, 1]))))
    box = (env[:, 0].min() - grow * w, env[:, 1].min() - grow * w, env[:, 2].max() + grow * w,
           env[:, 3].max() + grow * w)
    return {q for q in E.neighbours(box) if q in set(pool)} | set(base)


def repair(P, st, time_s=30.0, log=None, rounds=8, w_rot=4.0, allowed=None):
    """Closed loop on the exact check: findings -> culprits -> moved to exactly clean spots,
    until no finding is left or the time is up. `allowed`: part indices it may move (default
    every movable part). Returns a report (start/end findings, parts moved, evicted, parts
    left with their findings)."""
    t0 = time.monotonic()
    deadline = t0 + time_s
    E = ExactModel(P, st)
    scope = None if allowed is None else set(allowed)
    found = E.check(parts=scope, max_items=100000)
    rep = dict(start=len(found), rounds=0, moved=[], evicted=[], stuck=[])
    def local_rounds(found):
        for _ in range(rounds):
            if not found or time.monotonic() > deadline:
                break
            rep["rounds"] += 1
            progress = False
            for i in culprits(P, found, scope):
                if time.monotonic() > deadline:
                    break
                if not E.part_findings(i, max_items=1):
                    continue
                ok, ev = move_clean(P, st, E, i, deadline, w_rot=w_rot, allowed=scope)
                if ok:
                    progress = True
                    rep["moved"].append(P.parts[i].ref)
                    rep["evicted"] += ev
            found = E.check(parts=scope, max_items=100000)
            if not progress:
                break
        return found
    found = local_rounds(found)
    # escalation: re-seed the crowded set constructively (home spots, then edge-hugging, the
    # parts that failed first), growing the set; keep an attempt only if it ends better
    rep["reseeds"] = []
    failed_first = []
    for attempt in range(6):
        if not found or time.monotonic() > deadline:
            break
        base = culprits(P, found, scope)
        if not base:
            break
        crowd = _crowd(P, E, base, scope, grow=1 + attempt // 2)
        if attempt >= 1:
            # courtyards may overhang the edge (pads stay in): the culprits and the big parts
            board_area = max(1.0, P.outline.area)
            hung = P.allow_overhang([q for q in crowd if q in set(base) or P.parts[q].area > 0.05 * board_area])
            if hung:
                rep.setdefault("overhang", []).extend(hung)
        saved = {q: (int(st.X[q]), int(st.Y[q]), int(st.K[q])) for q in crowd}
        before = len(found)
        failed = reseed(P, st, E, crowd, deadline, edge=attempt >= 2 and bool(attempt % 2), first=failed_first,
                        w_rot=w_rot)
        found2 = local_rounds(E.check(parts=scope, max_items=100000))
        rep["reseeds"].append(dict(parts=len(crowd), edge=attempt >= 2 and bool(attempt % 2),
                                   failed=[P.parts[q].ref for q in failed],
                                   findings=len(found2)))
        if len(found2) < before:
            found = found2
        else:
            for q, pose in saved.items():
                E.set_pose(q, *pose)
            found = E.check(parts=scope, max_items=100000)
        failed_first = failed + [q for q in failed_first if q not in failed]
    left = {}
    for v in found:
        for q in v["parts"]:
            if P.parts[q].movable and (scope is None or q in scope):
                left.setdefault(q, []).append(v["type"])
    rep["stuck_parts"] = sorted(left)
    rep["stuck"] = [P.parts[q].ref for q in rep["stuck_parts"]]
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
    fixed = {q.i for q in P.parts if not q.movable} | {i}
    cands = _candidates(P, st, i, S, pad, list(range(len(p.rots))), 4.0, limit)
    clean = None
    for c, X, Y, k in cands:
        f = E.findings_at(i, X, Y, k)
        if not [v for v in f if set(v["parts"]) <= fixed]:
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
        rep["diagnosis"] = {P.parts[q].ref: diagnose(P, st, E, q) for q in rep["stuck_parts"][:12]}
        if log:
            for r, d in rep["diagnosis"].items():
                log(f"illegal: {d['reason']}: {d['detail']}")
    return rep
