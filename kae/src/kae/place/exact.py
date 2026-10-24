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


def mask_margin(P, pd):
    """A pad's solder-mask expansion: its own or its footprint's override, else the board's
    pad_to_mask_clearance."""
    m = getattr(pd, "mask_margin", None)
    if m is None:
        r = getattr(P.board, "rules", None)
        m = float(getattr(r, "mask_margin", 0.0) or 0.0) if r is not None else 0.0
    return float(m)


def mask_sides(pd):
    """Board sides (0 front, 1 back) where the pad has a solder-mask opening."""
    out = set()
    for ly in pd.layers or []:
        if ly in ("F.Mask", "*.Mask", "F&B.Mask"):
            out.add(0)
        if ly in ("B.Mask", "*.Mask", "F&B.Mask"):
            out.add(1)
    return out


_NET_TIE = __import__("re").compile(r"net[_ -]?tie", __import__("re").I)


def _no_copper(pd):
    """A pad with no copper anywhere: an NPTH that flashes none, or one whose layers are all
    technical (a paste-only pad, a footprint's cut-out marks)."""
    lays = pd.layers or []
    if lays and not any(ly.endswith(".Cu") for ly in lays):
        return True
    return _npth_without_copper(pd)


def _npth_without_copper(pd):
    """An NPTH pad whose copper is no larger than its hole (KiCad PAD::IsNPTHWithNoCopper):
    the solder-mask test skips it."""
    if pd.kind != "np_thru_hole":
        return False
    if not any(ly.endswith(".Cu") for ly in pd.layers or []):
        return True          # no copper layer: it flashes nowhere
    if tuple(pd.offset or (0.0, 0.0)) != (0.0, 0.0):
        return False
    w, h = pd.size
    if pd.shape == "circle":
        return w <= (pd.drill or 0.0) + 1e-9
    if pd.shape == "oval":
        sw, sh = pd.slot if pd.slot else (pd.drill, pd.drill)
        return w <= max(sw, sh) + 1e-9 and h <= max(sw, sh) + 1e-9 and min(w, h) <= min(sw, sh) + 1e-9
    return False


def _custom_clearances(P):
    """Parsable .kicad_dru clearance rules for pads: [(order, kind, pattern, min)], kind
    'ref' | 'lib' | 'area'. A condition is a selector (A.memberOfFootprint('ref or lib:glob'),
    A.intersectsArea('name'), A.Reference == 'glob') with optional Type/zone qualifiers that
    do not exclude pads; anything else (track widths, nets, layers) is not applied."""
    import re
    out = []
    rules = getattr(P.board, "rules", None)
    sel = re.compile(r"^A\.(memberOfFootprint|intersectsArea)\('([^']+)'\)$|^A\.Reference\s*==\s*'([^']+)'$")
    benign = re.compile(r"^[AB]\.[Tt]ype\s*!=\s*'Zone'$|^A\.Type\s*==\s*'[Pp]ad'$|^B\.Type\s*==\s*'[Pp]ad'$")
    for n, rule in enumerate(getattr(rules, "custom", None) or []):
        vals = [c["min"] for c in rule.get("constraints", []) if c.get("type") == "clearance"
                and isinstance(c.get("min"), (int, float))]
        if not vals:
            continue
        clauses = []
        for c in (rule.get("condition") or "").split("&&"):
            c = c.strip()
            while c.startswith("(") and c.endswith(")") and c.count("(") == c.count(")"):
                c = c[1:-1].strip()
            clauses.append(c)
        picks, ok = [], True
        for c in clauses:
            m = sel.match(c)
            if m:
                picks.append(m)
            elif not benign.match(c):
                ok = False
        if not ok or len(picks) != 1:
            continue
        m = picks[0]
        if m.group(3):
            out.append((n, "ref", m.group(3), float(vals[0])))
        elif m.group(1) == "intersectsArea":
            out.append((n, "area", m.group(2), float(vals[0])))
        else:
            pat = m.group(2)
            out.append((n, "lib" if ":" in pat else "ref", pat, float(vals[0])))
    return out


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
        # KiCad approximates arcs to max_error: a gap equal to the rule is legal
        self.tol = max(1e-4, float(getattr(P, "max_error", 0.005) or 0.005))
        fbs = (getattr(P, "feedback", None) or {}).get("sep", {})
        rules = getattr(P.board, "rules", None)
        holes = [float(getattr(rules, k, 0.0) or 0.0) for k in ("hole_clearance", "hole_to_hole")] if rules else []
        loc = [max([_local_clr(pd) for pd in q.fp.pads] or [0.0]) for q in P.parts]
        mm = [2 * max([mask_margin(P, pd) for pd in q.fp.pads] or [0.0]) for q in P.parts]
        web = float(getattr(rules, "mask_min_width", 0.0) or 0.0) if rules else 0.0
        self.reach = max([P.clr_max, P.edge_clearance] + holes + loc + [m + web for m in mm] +
                         list(fbs.values())) + 0.05
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
        # an NPTH pad that flashes no copper is no copper (KiCad skips it for clearance and
        # shorting; its hole still counts for hole clearance)
        self.cs = {p.i: [() if _no_copper(pd) else self._copper_sides(pd, p.side) for pd in p.fp.pads]
                   for p in P.parts}
        # custom clearance rules of the .kicad_dru for one footprint, library or rule area
        # (pingdevkit: 0.17 mm for its 0201s, 0.1 mm in the 'BGA' area): they replace the
        # netclass clearance for the parts they name
        self.rules_clr = _custom_clearances(P)
        self.areas = {ko.name: ko.outline for ko in (P.board.keepouts or []) if ko.name}
        # net-tie footprints: their copper graphics may touch pads of the tie's nets
        self.tie_nets = {p.i: {pd.net for pd in p.fp.pads if pd.net} for p in P.parts
                         if _NET_TIE.search(p.fp.lib_id or "")}
        self.ms = {p.i: [mask_sides(pd) for pd in p.fp.pads] for p in P.parts}
        self.mm = {p.i: [mask_margin(P, pd) for pd in p.fp.pads] for p in P.parts}
        rules_ = getattr(P.board, "rules", None)
        self.mask_web = float(getattr(rules_, "mask_min_width", 0.0) or 0.0) if rules_ is not None else 0.0
        self.mask_on = P.is_error("solder_mask_bridge")
        # zones (fills are not read): a pad's mask opening reaching past the gap a fill keeps
        # from it exposes the zone's copper with the pad (another net: a bridge)
        self.zones = []
        for z in getattr(P.board, "zones", None) or []:
            if getattr(z, "footprint", "") or not z.net:
                continue
            sides = {0 for ly in z.layers if ly == "F.Cu"} | {1 for ly in z.layers if ly == "B.Cu"}
            if sides and z.outline is not None and not z.outline.is_empty:
                self.zones.append((z.net, sides, z.outline, float(z.clearance or 0.0)))
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
        edge_on = P.is_error("copper_edge_clearance")
        e = getattr(P, "edge_by_ref", {}).get(P.parts[i].ref, e)   # a custom rule for this part
        etol = 0.05      # kae.board polygonizes outline arcs: chords sit inside the true edge
        for geom, k, pd in A["pads"]:
            if k in ok_out:
                continue        # a straddling part's outer pads (Problem._straddle_check)
            if not outline.contains(geom.centroid):
                add("pad_outside", [i], pd.number)
            elif not edge_on or _no_copper(pd):
                continue
            elif e > 0 and geom.distance(boundary) < e - etol:
                add("copper_edge_clearance", [i], f"{pd.number} {geom.distance(boundary):.3f}<{e}")
            elif not outline.contains(geom):
                add("copper_edge_clearance", [i], f"{pd.number} crosses the edge")
        for side in (0, 1) if edge_on else ():
            for g in A["gfx"]["cu"][side]:
                if not outline.contains(g):
                    add("copper_edge_clearance", [i], "copper graphic crosses the edge")
                elif e > 0 and g.distance(boundary) < e - etol:
                    add("copper_edge_clearance", [i], f"copper graphic {g.distance(boundary):.3f}<{e}")
        for side, gm, net in getattr(P, "fixed_copper", []):
            for geom, k, pd in A["pads"]:
                if side not in self.cs[i][k] or (net and pd.net == net):
                    continue
                need = max(self._net_clr(pd.net), self._net_clr(net), _local_clr(pd))
                if geom.distance(gm) < need - self.tol:
                    add("clearance", [i], f"pad {pd.number} vs fixed copper {net}")
        if self.mask_on and self.zones:
            # KiCad (drc_test_provider_solder_mask.cpp, testMaskItemAgainstZones): the pad's copper
            # against the zone's FILL, colliding closer than solder_mask_to_copper_clearance + the
            # pad's mask expansion; a pad on the zone's net is skipped, a net-less pad is not, an
            # NPTH pad without copper is never tested. The fill keeps the clearance rule's gap from
            # the pad (zone, netclass and pad-local clearances), so the opening reaches copper only
            # when s2c + expansion exceeds that gap (arcs approximated to max_error)
            s2c = float(getattr(getattr(P.board, "rules", None), "mask_to_copper", 0.0) or 0.0)
            tol = max(1e-6, float(getattr(P, "max_error", 0.005) or 0.005))
            for geom, k, pd in A["pads"]:
                if _npth_without_copper(pd):
                    continue
                m = self.mm[i][k]
                for net, sides, outline_z, zc in self.zones:
                    if (pd.net and net == pd.net) or not (sides & self.ms[i][k] & set(self.cs[i][k])):
                        continue
                    gap = max(zc, self._net_clr(pd.net), self._net_clr(net), _local_clr(pd))
                    if s2c + m > gap + tol and outline_z.distance(geom) < s2c + m + 1e-6:
                        add("solder_mask_bridge", [i], f"mask opening of pad {pd.number} over zone {net}")
                        break
        # board-level mask apertures: simple apertures, a bridge only over two positive nets
        web = max(self.mask_web, 1e-4)
        s2c = float(getattr(getattr(P.board, "rules", None), "mask_to_copper", 0.0) or 0.0)
        for side, gm in getattr(P, "fixed_mask", []):
            mine = {pd.net for geom, k, pd in A["pads"] if pd.net and side in self.cs[i][k]
                    and not _npth_without_copper(pd) and gm.distance(geom) < s2c + web - 1e-6}
            if not mine:
                continue
            nets = set(mine) | {net for net, sides, oz, _ in self.zones if side in sides and oz.intersects(gm)}
            for j in self.neighbours(gm.bounds, skip=i):
                B = self.sh[j]
                nets |= {pd.net for geom, k, pd in B["pads"] if pd.net and side in self.cs[j][k]
                         and not _npth_without_copper(pd) and gm.distance(geom) < s2c + web - 1e-6}
            if len(nets) >= 2:
                add("solder_mask_bridge", [i], f"a board mask aperture exposes nets {sorted(nets)[:3]}")
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

    def _aperture(self, rx, X, ry, Y, side, masks, add):
        """KiCad's simple mask apertures (graphics on a mask layer, no copper): a bridge only
        when an aperture exposes copper of two distinct positive nets (its footprint's pads,
        the other part's pads, zones under it); net-less copper cannot bridge. Reported when
        the other part's copper is among them."""
        web = max(self.mask_web, 1e-4)
        s2c = float(getattr(getattr(self.P.board, "rules", None), "mask_to_copper", 0.0) or 0.0)
        for m in masks:
            mine, theirs = set(), set()
            for (Z, idx, out) in ((X, rx, mine), (Y, ry, theirs)):
                for geom, k, pd in Z["pads"]:
                    if pd.net and side in self.cs[idx][k] and not _npth_without_copper(pd) and \
                            m.distance(geom) < s2c + web - 1e-6:
                        out.add(pd.net)
            if not theirs:
                continue
            nets = mine | theirs | {net for net, sides, oz, _ in self.zones if side in sides and oz.intersects(m)}
            if len(nets) >= 2:
                add("solder_mask_bridge", [rx, ry], f"mask graphic exposes nets {sorted(nets)[:3]}")
                return

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
                        if (hnet and pd.net == hnet) or _no_copper(pd):
                            continue
                        if hgeom.distance(geom) < max(hc, hloc, _local_clr(pd)) - self.tol:
                            add("hole_clearance", [rx, ry], f"hole {X['pads'][k][2].number} - pad {pd.number}")
        if hh > 0 and P.is_error("hole_to_hole"):
            for ha, _ in A["holes"]:
                for hb, _ in B["holes"]:
                    if ha.distance(hb) < hh - self.tol:
                        add("hole_to_hole", [i, j], "holes")
        csi, csj = self.cs[i], self.cs[j]
        rule = self._rule_clr(i, A, j, B)
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
                base = rule if rule is not None else max(self._net_clr(da.net), self._net_clr(db.net))
                need = max(base, _local_clr(da), _local_clr(db))
                d = ga[a].distance(gb[b])
                if d < need - self.tol:
                    add("clearance", [i, j], f"{da.number}-{db.number} {d:.3f}<{need:.3f}")
        # graphics: a mask aperture over another part's pads bridges them (KiCad's
        # solder_mask_bridge); copper graphics keep copper clearance
        for (X, Y, rx, ry, cy_) in ((A, B, i, j, csj), (B, A, j, i, csi)):
            for side in (0, 1):
                masks, cus = X["gfx"]["mask"][side], X["gfx"]["cu"][side]
                if not masks and not cus:
                    continue
                if masks and self.mask_on:
                    self._aperture(rx, X, ry, Y, side, masks, add)
                ties = self.tie_nets.get(rx, ())
                for geom, k, pd in Y["pads"]:
                    if side not in cy_[k] or (pd.net and pd.net in ties):
                        continue
                    need = self._net_clr(pd.net)
                    if cus and any(c.distance(geom) < need - self.tol for c in cus):
                        add("clearance", [rx, ry], f"copper graphic near pad {pd.number}")
                if cus and X is A and not (ties and ties & self.tie_nets.get(ry, set())):
                    for c in cus:
                        if any(c.distance(o) < P.clr_min - self.tol for o in Y["gfx"]["cu"][side]):
                            add("clearance", [rx, ry], "copper graphics")
        # solder-mask apertures (pad + its mask expansion) of different nets closer than the
        # board's minimum mask web bridge (KiCad solder_mask_bridge)
        if self.mask_on:
            msi, msj, mmi, mmj = self.ms[i], self.ms[j], self.mm[i], self.mm[j]
            web = max(self.mask_web, 1e-4)
            for side in (0, 1):
                pa = [(g, k, pd) for g, k, pd in A["pads"] if side in msi[k]]
                pb = [(g, k, pd) for g, k, pd in B["pads"] if side in msj[k]]
                if not pa or not pb:
                    continue
                ga = np.array([g for g, _, _ in pa], dtype=object)
                gb = np.array([g for g, _, _ in pb], dtype=object)
                reach = max(mmi + mmj) + web if (mmi and mmj) else web
                near = shapely.dwithin(ga[:, None], gb[None, :], reach)
                for a, b in zip(*np.nonzero(near)):
                    (_, ka, da), (_, kb, db) = pa[a], pb[b]
                    if (da.net and da.net == db.net) or _npth_without_copper(da) or _npth_without_copper(db):
                        continue
                    gap = ga[a].distance(gb[b]) - mmi[ka] - mmj[kb]
                    if gap < web - 1e-6:
                        add("solder_mask_bridge", [i, j], f"mask openings of {da.number} and {db.number} {gap:.3f} apart")
        e = P.edge_clearance
        for (X, Y, rx, ry) in ((A, B, i, j), (B, A, j, i)):
            for cg in Y["cuts"]:
                cb = cg.boundary
                for geom, k, pd in X["pads"]:
                    if geom.distance(cb) < e - self.tol or cg.contains(geom.centroid):
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

    def _rule_clr(self, i, A, j, B):
        """The custom clearance rule for a pair (the last matching rule in the file, as KiCad
        evaluates them), or None for the netclass clearance."""
        best = None
        for order, kind, pat, value in self.rules_clr:
            if self._matches(i, A, kind, pat) or self._matches(j, B, kind, pat):
                if best is None or order > best[0]:
                    best = (order, value)
        return None if best is None else best[1]

    def _matches(self, q, Q, kind, pat):
        import fnmatch
        p = self.P.parts[q]
        if kind == "ref":
            return fnmatch.fnmatchcase(p.ref, pat)
        if kind == "lib":
            return fnmatch.fnmatchcase(p.fp.lib_id or "", pat)
        if kind == "area":
            area = self.areas.get(pat)
            h = self.hull(Q)
            return area is not None and h is not None and h.intersects(area)
        return False

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


# ----------------------------------------------------------------------------- order rules
class OrderGuard:
    """Protection-order rules (clusters.protection_order: ((conn, pads), (prot, pads),
    (target, pads))) the repair must not break: a rule is broken when the protected part is
    nearer the connector than the protection is, or nearer the protection than the connector
    (Annealer.order_violations, no margin). Rules with a lifted (parked) member are not judged."""

    def __init__(self, P, st, rules=None):
        self.P, self.st = P, st
        self.rules = list(rules if rules is not None else getattr(P, "order_rules", None) or [])
        self.of = {}
        for j, rule in enumerate(self.rules):
            for (i, _) in rule:
                self.of.setdefault(i, []).append(j)

    def _c(self, i, pads):
        xy = self.st.pins_xy(i)
        return xy[pads].mean(axis=0) if len(pads) else xy.mean(axis=0)

    def broken(self, j, lifted=()):
        (ci, cp), (ti, tp), (ii, ip) = self.rules[j]
        if ci in lifted or ti in lifted or ii in lifted:
            return False
        c, t, x = self._c(ci, cp), self._c(ti, tp), self._c(ii, ip)
        d_ct = float(np.hypot(*(t - c)))
        return d_ct > min(float(np.hypot(*(x - c))), float(np.hypot(*(x - t))))

    def count(self, i, lifted=()):
        return sum(1 for j in self.of.get(i, ()) if self.broken(j, lifted))

    def count_at(self, i, X, Y, K, lifted=()):
        st = self.st
        saved = (st.X[i], st.Y[i], st.K[i])
        st.X[i], st.Y[i], st.K[i] = X, Y, K
        try:
            return self.count(i, lifted)
        finally:
            st.X[i], st.Y[i], st.K[i] = saved

    def total(self):
        return sum(1 for j in range(len(self.rules)) if self.broken(j))


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


def _ok_map(P, i, k, S, pad):
    """Origins (ncx x ncy booleans) where part i in rotation k is inside its board rectangles
    and free in the occupancy tables S."""
    from .legalize import _inside_origins
    p = P.parts[i]
    si = 0 if p.s > 0 else 1
    nx, ny = P.ncx, P.ncy
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
    return ok


def _still_fits(P, st, j, maps, q):
    """Whether part j (its free-origin maps per rotation, without part q) still has an origin
    once q stands where it is: the origins where a rectangle of j would overlap one of q's
    (same side) are masked out, a few slices instead of new tables."""
    pj = P.parts[j]
    sj = 0 if pj.s > 0 else 1
    qr = list(st.grid_rects(q))
    nx, ny = P.ncx, P.ncy
    for k, ok in maps.items():
        if not ok.any():
            continue
        m = ok.copy()
        r = pj.rots[k]
        for side, (a, b, c, d) in [(sj, o) for o in (r.g_own_rects or (r.g_own,))] + [(1 - sj, o) for o in r.g_opp]:
            for qs, (qa, qb, qc, qd), _ in qr:
                if qs != side:
                    continue
                x0, x1 = max(0, qa - b + 1), min(nx, qb - a)
                y0, y1 = max(0, qc - d + 1), min(ny, qd - c)
                if x1 > x0 and y1 > y0:
                    m[x0:x1, y0:y1] = False
        if m.any():
            return True
    return False


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


def move_clean(P, st, E, i, deadline, w_rot=4.0, limit=600, evict=True, allowed=None, guard=None):
    """Move part i to the nearest spot that is grid-free (others where they are) and exactly
    clean; with evict, else to the nearest exactly clean spot where it only covers smaller
    movable parts, which are then re-placed the same way. Returns (moved, evicted refs)."""
    p = P.parts[i]
    ks = list(range(len(p.rots)))
    guard = guard if guard is not None else OrderGuard(P, st)
    base = guard.count(i)          # a move may not break a protection-order rule that holds
    S, pad = _tables(P, st, {i})
    for c, X, Y, k in _candidates(P, st, i, S, pad, ks, w_rot, limit):
        if time.monotonic() > deadline:
            return False, []
        if not E.findings_at(i, X, Y, k, first=True) and guard.count_at(i, X, Y, k) <= base:
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
        if guard.count_at(i, X, Y, k) > base:
            continue
        out_parts = {q for v in f for q in v["parts"]} - {i}
        E.set_pose(i, X, Y, k)
        out = []
        for q in sorted(out_parts, key=lambda q: -P.parts[q].area):
            move_clean(P, st, E, q, deadline, w_rot, limit, evict=False, allowed=allowed, guard=guard)
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
    guard = OrderGuard(P, st)
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
        big = [j for j in order[n + 1:] if P.parts[j].area > 0.05 * board_area][:2] \
            if P.parts[q].area > 0.02 * board_area else []      # only a big part can shut a big one out
        first_clean = None
        tries = 0
        guard_tries = 0
        big_maps = {j: {k: _ok_map(P, j, k, S, pad) for k in range(len(P.parts[j].rots))} for j in big}
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
                # keep its protection-order rules (with every member placed); when no spot nearby
                # does, legality first
                ok = guard.count(q, lifted) == 0 or guard_tries > 200
                guard_tries += 1
                if ok and big:
                    ok = all(_still_fits(P, st, j, big_maps[j], q) for j in big)
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
    order0 = OrderGuard(P, st).total()
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
    rep["order_broken"] = [order0, OrderGuard(P, st).total()]      # protection-order rules, before/after
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
    import re
    zre = re.compile(r"^Zone \[([^\]]*)\] on (\S+?),?(\s|$)")
    tre = re.compile(r"^PCB text '.*' on \S+", re.S)
    texts = None
    for v in viols:
        out["by_type"][v["type"]] = out["by_type"].get(v["type"], 0) + 1
        # board text on copper (a grid obstacle only; the exact model has no text): the parts
        # the error names keep their hulls off the text's box, by `step` more each time KiCad
        # still objects. The text item names no part: matched by position it would blame
        # whichever part has a pad nearest the text's anchor.
        tx = [it for it in v.get("items", []) if tre.match(it.get("description", ""))]
        if tx:
            if texts is None:
                from .problem import board_texts
                texts = board_texts(P.board)
            v = dict(v, items=[it for it in v.get("items", []) if it not in tx])
            mv = [i for i in sorted(violation_parts(P, st, v)) if P.parts[i].movable]
            if not mv:
                out["fixed_only"] += 1
                continue
            tr = fb.setdefault("text_rounds", {})
            for it in tx:
                pos = it.get("pos") or {}
                g = texts.get(it.get("uuid", ""))
                if g is None and "x" in pos and "y" in pos:
                    g = shapely.Point(pos["x"], pos["y"])
                if g is None:
                    continue
                for i in mv:
                    key = (i, it.get("uuid") or (pos.get("x"), pos.get("y")))
                    tr[key] = tr.get(key, 0) + 1
                    fb["avoid"].setdefault(i, []).append(
                        (g.buffer(step * tr[key]), f"{v['type']} with {it['description'].splitlines()[0][:60]} (KiCad DRC)"))
                    out["constraints"] += 1
            continue
        # a zone item: the culprit keeps off that zone's whole outline (KiCad reports a zone at
        # one point; a disc there let the part slide to another spot of the same zone)
        zones = []
        for it in v.get("items", []):
            m = zre.match(it.get("description", ""))
            if m:
                zones += [z for z in getattr(P.board, "zones", None) or []
                          if z.net == m.group(1) and m.group(2) in z.layers and z.outline is not None]
        if zones:
            v = dict(v, items=[it for it in v.get("items", []) if not zre.match(it.get("description", ""))])
            g = shapely.union_all([z.outline for z in zones]).buffer(step)
            for i in sorted(violation_parts(P, st, v)):
                if P.parts[i].movable:
                    fb["avoid"].setdefault(i, []).append((g, f"{v['type']} with zone {zones[0].net} (KiCad DRC)"))
                    out["constraints"] += 1
            continue
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
