# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Grid world shared by every joint place-and-route method.

Clearance model ("halos"): every copper object stamps its copper, dilated by
clearance + the half-width of the object that will be tested against it, into two
per-net count maps: occT (where a track centreline may not go) and occV (where a via
centre may not go). D* counts distinct nets per cell, so the number of *foreign* nets
at a cell for net n is D - (occ[n] > 0). A margin of 0.75 grid cells covers the
sampling error of centrelines between cell centres (including 45 degree steps).

Footprints sit with their origin on a cell centre; pad/courtyard rasters are cached per
orientation as cell offsets, so moving a part is a re-stamp, not a re-raster.
"""
import math

import numpy as np

from raster import count_add, disc, edge_dist, nearest_cell, raster_poly, stamp

ROTS = (0.0, 90.0, 180.0, 270.0)


def rot_pts(pts, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    x, y = pts[:, 0], pts[:, 1]
    return np.stack([x * c + y * s, -x * s + y * c], axis=1)


class Rules:
    def __init__(self, data, g):
        r, d = data["rules"], data["default"]
        cl = [d["clearance"], r["min_clearance"]] + [v["clearance"] for v in data["nets"].values()]
        self.c = max(cl)
        self.w = max(r["min_track"], min(d["width"], 0.2)) if d["width"] >= 0.2 else max(r["min_track"], d["width"])
        self.via_d = max(d["via_d"], r["min_via"])
        self.via_drill = max(d["via_drill"], r["min_drill"])
        if (self.via_d - self.via_drill) / 2 < r["min_annular"]:
            self.via_d = self.via_drill + 2 * r["min_annular"]
        self.hc = r["hole_clearance"]
        self.h2h = r["hole_to_hole"]
        self.ec = r["edge_clearance"]
        self.g = g
        self.m = 0.75 * g
        w, c, dv, dr, m = self.w, self.c, self.via_d, self.via_drill, self.m
        self.R_TT = w + c + m
        self.R_TV = max(w / 2 + c + dv / 2, w / 2 + self.hc + dr / 2) + m
        self.R_VV = max(dv + c, dr + self.h2h, dv / 2 + self.hc + dr / 2) + m
        # solder mask: a pad's aperture (pad + expansion) must not expose other nets' tracks,
        # and two pads' apertures (plus the minimum web) must not merge
        self.mask_exp = r.get("mask_exp", 0.0)
        self.mask_web = r.get("mask_web", 0.0)
        self.pad_T = max(c, self.mask_exp + 0.02) + w / 2 + m
        self.pad_gap = max(c, 2 * self.mask_exp + self.mask_web)
        self.pad_V = max(c + dv / 2, self.hc + dr / 2) + m

    def __repr__(self):
        return (f"Rules(g={self.g} w={self.w} c={self.c} via={self.via_d}/{self.via_drill} "
                f"hc={self.hc} h2h={self.h2h} ec={self.ec})")


class Part:
    def __init__(self, idx, fp):
        self.idx = idx
        self.ref, self.uuid = fp["ref"], fp["uuid"]
        self.locked = fp["locked"] or fp.get("anchored", False)  # locked, or carries Edge.Cuts
        self.side = 1 if fp["back"] else 0
        self.x0, self.y0, self.rot0 = fp["x"], fp["y"], fp["rot"] % 360
        self.pads = fp["pads"]
        self.data = fp
        self.court = [np.array(p, float) for p in fp["courtyard"] if len(p) >= 3]
        if not self.court:  # synthesize from pad extents
            pts = [np.array(q, float) for p in self.pads for q in p["poly"]]
            pts += [np.array([[p["x"], p["y"]]]) for p in self.pads]
            allp = np.concatenate(pts) if pts else np.zeros((1, 2))
            x0, y0 = allp.min(0) - 0.25
            x1, y1 = allp.max(0) + 0.25
            self.court = [np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])]
        self.cache = {}
        self.area = sum(_poly_area(c) for c in self.court)

    def nets(self):
        return {p["net"] for p in self.pads if p["net"]}


def _cutout_cells(part, deg, fx, fy, g):
    """Cells inside the closed regions bounded by a footprint's own Edge.Cuts strokes."""
    edges = [np.array(e, float) for e in part.data.get("edges", []) if len(e) >= 3]
    if not edges:
        return np.zeros((0, 2), np.int32)
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    u = unary_union([Polygon(rot_pts(e, deg)).buffer(0) for e in edges])
    holes = []
    for geom in getattr(u, "geoms", [u]):
        for ring in getattr(geom, "interiors", []):
            holes.append(np.array(ring.coords)[:-1])
    if not holes:
        return np.zeros((0, 2), np.int32)
    cells = np.concatenate([raster_poly(h, 0.75 * g, -fx, -fy, g) for h in holes])
    return np.ascontiguousarray(np.unique(cells, axis=0), np.int32)


def _layer_index(lid, nl):
    """KiCad 9+ copper layer id -> grid layer index (0 = F.Cu, nl - 1 = B.Cu)."""
    return 0 if lid == 0 else (nl - 1 if lid == 2 else (lid - 4) // 2 + 1)


def region_cells(poly, holes, r, x0, y0, g):
    """Cells whose centre lies within r of the region `poly` minus `holes` (an unfilled
    circle or rectangle drawn on copper is a ring: its inside is not copper)."""
    cells = raster_poly(poly, r, x0, y0, g)
    for h in holes:
        if len(h) < 3 or not len(cells):
            continue
        h = np.ascontiguousarray(h, float)
        px = x0 + cells[:, 0] * g
        py = y0 + cells[:, 1] * g
        d = np.full(len(cells), 1e9)
        ins = np.zeros(len(cells), bool)
        edge_dist(px, py, h, d, ins)
        cells = cells[~(ins & (d > r))]
    return np.ascontiguousarray(cells, np.int32)


def _shape_rings(s):
    """(outline, holes) pairs of a copper drawing as float arrays."""
    holes = s.get("holes") or [[] for _ in s["poly"]]
    return [(np.array(p, float), [np.array(h, float) for h in hs if len(h) >= 3])
            for p, hs in zip(s["poly"], holes) if len(p) >= 3]


def _poly_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


class World:
    def __init__(self, data, g=0.1, margin=1.0, spokes=False, zone_nets="route"):
        self.data = data
        self.R = R = Rules(data, g)
        self.spokes = spokes
        self.g = g
        self.nl = data["layers"]
        outl = [np.array(o, float) for o in data["outline"]]
        if not outl:
            raise ValueError("board has no outline")
        allp = np.concatenate(outl)
        self.x0 = math.floor((allp[:, 0].min() - margin) / g) * g
        self.y0 = math.floor((allp[:, 1].min() - margin) / g) * g
        self.W = int(math.ceil((allp[:, 0].max() + margin - self.x0) / g)) + 1
        self.H = int(math.ceil((allp[:, 1].max() + margin - self.y0) / g)) + 1
        self.outline = outl
        self.holes = [np.array(h, float) for h in data["outline_holes"]]
        names = sorted(n for n in data["nets"])
        self.net_names = [""] + names
        self.net_id = {n: i for i, n in enumerate(self.net_names)}
        self.N = len(self.net_names)
        L, H, W = self.nl, self.H, self.W
        self.occT = np.zeros((self.N, L, H, W), np.uint8)
        self.occV = np.zeros((self.N, L, H, W), np.uint8)
        self.DT = np.zeros((L, H, W), np.int16)
        self.DV = np.zeros((L, H, W), np.int16)
        # keep-out planes: 0/1 = front/back courtyards, 2 + l = pad keep-out on copper layer l
        # (KiCad checks courtyards per side and copper clearance per layer)
        self.P = 2 + L
        self.court = np.zeros((self.P, H, W), np.int16)
        self.hist = np.zeros((L, H, W), np.float32)
        self._static_masks()
        self.parts = [Part(i, fp) for i, fp in enumerate(data["footprints"])]
        for p in self.parts:
            lay = set()
            for pad in p.pads:
                lay |= set(range(self.nl)) if (pad["npth"] or pad["cu"] == "both") else \
                    set(self.pad_layers(p, pad))
            other = (1 - p.side,) if p.data.get("courtyard_other") else ()
            p.sides = tuple([p.side, *other] + [2 + l for l in sorted(lay)])  # planes it occupies
        self._static_copper()
        self.pose = {}  # part idx -> (cx, cy, rot_index) for placed parts
        self.frac = {}  # part idx -> sub-cell origin offset (parts kept at input poses)
        self.fixed = set()  # parts that must not move (locked, or route-only runs)
        self.offs_TT = disc(R.R_TT, g)
        self.offs_TV = disc(R.R_TV, g)
        self.offs_VV = disc(R.R_VV, g)
        # pins per net: list of (part idx, pad idx)
        self.net_pins = {i: [] for i in range(1, self.N)}
        for p in self.parts:
            for k, pad in enumerate(p.pads):
                if pad["net"] and not pad["npth"]:
                    self.net_pins[self.net_id[pad["net"]]].append((p.idx, k))
        self.net_pins = {n: v for n, v in self.net_pins.items() if len(v) >= 2}
        # pads of nets that have a zone on their layer need room for thermal spokes
        self.zone_nets = {}
        for z in data.get("zones", []):
            for lid in z["layers"]:
                l = 0 if lid == 0 else (self.nl - 1 if lid == 2 else (lid - 4) // 2 + 1)
                prev = self.zone_nets.get((z["net"], l))
                spoke = (z.get("gap", 0.5), z.get("spoke", 0.5), z.get("min_width", 0.25))
                self.zone_nets[(z["net"], l)] = spoke if prev is None else tuple(map(max, prev, spoke))
        if zone_nets == "skip":
            # nets poured on every copper layer are left to their zones
            for name in {n for n, _ in self.zone_nets}:
                if all((name, l) in self.zone_nets for l in range(self.nl)):
                    self.net_pins.pop(self.net_id.get(name), None)

    # ---------------------------------------------------------------- static
    def _static_masks(self):
        R, g = self.R, self.g
        ys, xs = np.mgrid[0:self.H, 0:self.W]
        px = (self.x0 + xs * g).ravel()
        py = (self.y0 + ys * g).ravel()
        d_edge = np.full(px.shape, 1e9)
        inside = np.zeros(px.shape, bool)
        for poly in self.outline + self.holes:
            edge_dist(px, py, np.ascontiguousarray(poly), d_edge, inside)
        self.inside = inside.reshape(self.H, self.W)
        self.d_edge = d_edge.reshape(self.H, self.W)
        ok_T = self.inside & (self.d_edge >= R.ec + R.w / 2 + R.m)
        ok_V = self.inside & (self.d_edge >= R.ec + R.via_d / 2 + R.m)
        self.ok_cu = self.inside & (self.d_edge >= R.ec + R.m)  # pad copper allowed
        self.ok_court = self.inside & (self.d_edge >= 0)
        self.blockT = np.repeat(~ok_T[None], self.nl, 0)
        self.blockV = np.repeat(~ok_V[None], self.nl, 0)
        # board rule areas: no track / via may touch them, so block centrelines within half
        # a track width / via diameter (+ the sampling margin), as for footprint rule areas
        for ko in self.data["keepouts"]:
            for poly in ko["poly"]:
                if len(poly) < 3:
                    continue
                pl = np.array(poly, float)
                for flag, r, block in (("tracks", R.w / 2 + R.m, self.blockT), ("vias", R.via_d / 2 + R.m, self.blockV)):
                    if not ko[flag]:
                        continue
                    cells = raster_poly(pl, r, self.x0, self.y0, g)
                    ok = (cells[:, 0] >= 0) & (cells[:, 1] >= 0) & (cells[:, 0] < self.W) & (cells[:, 1] < self.H)
                    cells = cells[ok]
                    for l in range(self.nl):
                        lid = 0 if l == 0 else (2 if l == self.nl - 1 else 4 + 2 * (l - 1))  # KiCad 9+ ids
                        if lid in ko["layers"]:
                            block[l, cells[:, 1], cells[:, 0]] = True

    def _static_copper(self):
        """Board-level copper drawings (lines, arcs, circles, rectangles, polygons on a copper
        layer, with or without a net) are fixed copper:
        - wires and vias of other nets keep clear of them (halos in occT / occV);
        - pads of every part keep clear of them: they are stamped once into the pad keep-out
          planes (court[2 + l]), so legal_map / part_violation see them like another part's
          pads. Same-net pads are kept off too (the planes carry no nets);
        - drawings of a routed net are extra terminals of that net (`shape_terms`): the
          router connects them like pads, since KiCad counts them as connectable items."""
        R, g = self.R, self.g
        self.shape_terms = {}
        # a pad keeps pad_gap / 2 + 0.71 g; this side adds the rest of the copper clearance
        # (or of the pad's solder-mask aperture, which must not expose the drawing)
        rs = max(R.c / 2, max(R.c, R.mask_exp + 0.02) - R.pad_gap / 2) + 0.71 * g
        keep = {}
        for s in self.data.get("cu_shapes", []):
            l = _layer_index(s["layer"], self.nl)
            net = self.net_id.get(s["net"], 0) if s["net"] else 0
            for pl, hs in _shape_rings(s):
                stamp(self.occT, self.DT, net, l, region_cells(pl, hs, R.pad_T, self.x0, self.y0, g), 0, 0, 1)
                stamp(self.occV, self.DV, net, l, region_cells(pl, hs, R.pad_V, self.x0, self.y0, g), 0, 0, 1)
                keep.setdefault(l, []).append(region_cells(pl, hs, rs, self.x0, self.y0, g))
                cu = region_cells(pl, hs, 0.0, self.x0, self.y0, g)
                if net and len(cu):
                    t = np.stack([np.full(len(cu), l), cu[:, 1], cu[:, 0]], 1).astype(np.int32)
                    ok = (t[:, 1] >= 0) & (t[:, 2] >= 0) & (t[:, 1] < self.H) & (t[:, 2] < self.W)
                    if ok.any():
                        self.shape_terms.setdefault(net, []).append(np.ascontiguousarray(t[ok]))
        for l, cs in keep.items():  # one count per cell, however many drawings cover it
            cells = np.ascontiguousarray(np.unique(np.concatenate(cs), axis=0), np.int32)
            count_add(self.court, 2 + l, cells, 0, 0, 1)

    # ---------------------------------------------------------------- coords
    def cell(self, x, y):
        return int(round((x - self.x0) / self.g)), int(round((y - self.y0) / self.g))

    def xy(self, ix, iy):
        return self.x0 + ix * self.g, self.y0 + iy * self.g

    def pad_layers(self, part, pad):
        cu = pad["cu"]
        if cu == "both":
            return list(range(self.nl))
        if cu == "B":
            return [self.nl - 1]
        if cu == "F":
            return [0]
        return []

    # ---------------------------------------------------------------- part rasters
    def part_raster(self, part, ri, frac=(0.0, 0.0)):
        """Cached cell offsets for part at orientation index ri, with its origin at
        cell (0, 0) centre + frac (sub-cell offset, used for parts kept where they were)."""
        fx, fy = frac
        key = (ri, round(fx, 5), round(fy, 5))
        if key in part.cache:
            return part.cache[key]
        R, g = self.R, self.g
        deg = ROTS[ri] if ri < 4 else part.rot0
        pads = []
        for pad in part.pads:
            ent = dict(net=self.net_id.get(pad["net"], 0) if pad["net"] else 0,
                       layers=self.pad_layers(part, pad), npth=pad["npth"])
            c = rot_pts(np.array([[pad["x"], pad["y"]]]), deg)[0]
            ent["center"] = c + np.array([fx, fy])
            polys = [rot_pts(np.array(p, float), deg) for p in pad["poly"] if len(p) >= 3]
            cu, hT, hV = [], [], []
            # pad-local clearance overrides (fiducials, mounting holes, power pads)
            ex = max(0.0, (pad.get("clear") or 0.0) - R.c)
            # terminal cells (where a wire may end on the pad): centres inside the pad's inner
            # approximation (the outer one admits cells a few microns outside the pad, which
            # KiCad does not connect). Custom-shape pads: KiCad's connectivity misses track
            # ends well inside a ring pad (funkeleinhorn MK1), so only the anchor (a disc of
            # half the anchor size around the pad position) is a terminal there
            for q in pad.get("poly_in") or pad["poly"]:
                if len(q) >= 3:
                    cu.append(raster_poly(rot_pts(np.array(q, float), deg), 0.0, -fx, -fy, g))
            if pad.get("custom") and cu:
                cells = np.concatenate(cu)
                cc = c + np.array([fx, fy])
                d = np.hypot(-fx + cells[:, 0] * g - cc[0], -fy + cells[:, 1] * g - cc[1])
                near = d <= max(pad.get("anchor_r", 0.0) - 0.05, 0.0)
                cu = [np.ascontiguousarray(cells[near])] if near.any() else []
            for pl in polys:
                hT.append(raster_poly(pl, R.pad_T + ex, -fx, -fy, g))
                hV.append(raster_poly(pl, R.pad_V + ex, -fx, -fy, g))
            drill = max(pad["drill"]) if pad["drill"] else 0.0
            if drill > 0:
                rv = drill / 2 + max(R.h2h + R.via_drill / 2, R.hc + R.via_d / 2) + R.m + ex
                cc = np.round((c + np.array([fx, fy])) / g).astype(np.int32)
                d = disc(rv + 0.71 * g, g) + cc
                hV.append(d.astype(np.int32))
                if pad["npth"] or not polys:
                    rt = drill / 2 + R.hc + R.w / 2 + R.m + ex
                    hT.append((disc(rt + 0.71 * g, g) + cc).astype(np.int32))
            # thermal spoke corridors (4 axis directions) kept free of other nets
            for l in ent["layers"]:
                zs = self.zone_nets.get((pad["net"], l)) if pad["net"] else None
                if not zs or not polys or not self.spokes:
                    continue
                gap, spoke, minw = zs
                allp = np.concatenate(polys)
                x0, y0 = allp.min(0)
                x1, y1 = allp.max(0)
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                ext = gap + 2 * max(spoke, minw)
                hs = spoke / 2
                for rect in ([[x1, my - hs], [x1 + ext, my - hs], [x1 + ext, my + hs], [x1, my + hs]],
                             [[x0 - ext, my - hs], [x0, my - hs], [x0, my + hs], [x0 - ext, my + hs]],
                             [[mx - hs, y1], [mx + hs, y1], [mx + hs, y1 + ext], [mx - hs, y1 + ext]],
                             [[mx - hs, y0 - ext], [mx + hs, y0 - ext], [mx + hs, y0], [mx - hs, y0]]):
                    rc = np.array(rect, float)
                    hT.append(raster_poly(rc, R.c + R.w / 2 + R.m, -fx, -fy, g))
                    hV.append(raster_poly(rc, R.c + R.via_d / 2 + R.m, -fx, -fy, g))
                break
            cu = np.concatenate(cu) if cu else np.zeros((0, 2), np.int32)
            if len(cu) == 0 and polys:
                cu = nearest_cell(c[0] + fx, c[1] + fy, 0.0, 0.0, g)
            ent["cu"] = np.ascontiguousarray(cu, np.int32)
            ent["hT"] = np.ascontiguousarray(np.unique(np.concatenate(hT), axis=0) if hT else np.zeros((0, 2), np.int32), np.int32)
            ent["hV"] = np.ascontiguousarray(np.unique(np.concatenate(hV), axis=0) if hV else np.zeros((0, 2), np.int32), np.int32)
            if pad["npth"] or ent["layers"] == []:
                ent["layers_halo"] = list(range(self.nl))
            else:
                ent["layers_halo"] = ent["layers"]
            pads.append(ent)
        # the footprint's copper drawings (pad extensions, solder-jumper bridges): copper of
        # their net (usually none) that moves with the part. Not terminals; wires of other
        # nets keep clear of them, and so do other parts' pads (keep-out below).
        fcu_keep, fcu_edge = [], []
        padp = None
        for s in part.data.get("cu_shapes", []):
            l = _layer_index(s["layer"], self.nl)
            net = self.net_id.get(s["net"], 0) if s["net"] else 0
            for pl, hs in _shape_rings(s):
                pl = rot_pts(pl, deg)
                hs = [rot_pts(h, deg) for h in hs]
                # drawings touching one of the part's own pads (solder-jumper bridges between
                # two nets, pad extensions: espprog JP2/JP7) are left out: a no-net halo over
                # the pads would block their own wires
                from shapely.geometry import Polygon
                if padp is None:
                    padp = [(self.pad_layers(part, pd), Polygon(rot_pts(np.array(q, float), deg)).buffer(0))
                            for pd in part.pads for q in pd["poly"] if len(q) >= 3]
                gp = Polygon(pl).buffer(0)
                if any(l in lays and gp.intersects(pp) for lays, pp in padp):
                    continue
                pads.append(dict(net=net, layers=[l], npth=False, center=pl.mean(0) + np.array([fx, fy]),
                                 cu=region_cells(pl, hs, 0.0, -fx, -fy, g), layers_halo=[l],
                                 hT=region_cells(pl, hs, R.pad_T, -fx, -fy, g),
                                 hV=region_cells(pl, hs, R.pad_V, -fx, -fy, g)))
                fcu_keep.append((2 + l, region_cells(pl, hs, R.pad_gap / 2 + 0.71 * g, -fx, -fy, g)))
                fcu_edge.append(region_cells(pl, hs, 0.75 * g, -fx, -fy, g))
        for e in part.data.get("edges", []):
            if len(e) < 3:
                continue
            pl = rot_pts(np.array(e, float), deg)
            pads.append(dict(net=0, layers=[], npth=True, center=np.array([fx, fy]),
                             cu=np.zeros((0, 2), np.int32), layers_halo=list(range(self.nl)),
                             hT=raster_poly(pl, R.ec + R.w / 2 + R.m, -fx, -fy, g),
                             hV=raster_poly(pl, R.ec + R.via_d / 2 + R.m, -fx, -fy, g)))
        # the footprint's own rule areas (keep-outs) move with it: no-track / no-via areas are
        # obstacles of no net for every net's wires and vias (KiCad items_not_allowed)
        lids = [0 if l == 0 else (2 if l == self.nl - 1 else 4 + 2 * (l - 1)) for l in range(self.nl)]
        kos = []
        for ko in part.data.get("keepouts", []):
            lay = [l for l in range(self.nl) if lids[l] in ko["layers"]]
            for p_ in ko["poly"]:
                if len(p_) < 3 or not lay:
                    continue
                pl = rot_pts(np.array(p_, float), deg)
                kos.append((ko, lay, pl))
                if not (ko["tracks"] or ko["vias"]):
                    continue
                none = np.zeros((0, 2), np.int32)
                pads.append(dict(net=0, layers=[], npth=True, center=np.array([fx, fy]), cu=none,
                                 layers_halo=lay,
                                 hT=raster_poly(pl, R.w / 2 + R.m, -fx, -fy, g) if ko["tracks"] else none,
                                 hV=raster_poly(pl, R.via_d / 2 + R.m, -fx, -fy, g) if ko["vias"] else none))
        # keep-out = courtyard, the part's own board cutouts, and its pads grown by half the
        # clearance (some library courtyards do not cover their pads)
        keep = {}
        for plane, cells in fcu_keep:
            keep.setdefault(plane, []).append(cells)
        for ko, lay, pl in kos:  # other parts' pads / footprints may not enter its rule areas
            cells = raster_poly(pl, 0.75 * g, -fx, -fy, g)
            if ko["pads"]:
                for l in lay:
                    keep.setdefault(2 + l, []).append(cells)
            if ko["footprints"]:
                for side in {0 if l == 0 else 1 for l in lay if l in (0, self.nl - 1)}:
                    keep.setdefault(side, []).append(cells)
        for pad in part.pads:
            drilled = bool(pad["drill"]) and max(pad["drill"]) > 0
            ex = max(0.0, (pad.get("clear") or 0.0) - R.c)  # local clearance beyond the board's
            rk = (max(R.pad_gap, R.hc) if drilled else R.pad_gap) / 2 + ex + 0.71 * g
            lay = range(self.nl) if (pad["npth"] or pad["cu"] == "both") else self.pad_layers(part, pad)
            for p_ in pad["poly"]:
                if len(p_) < 3:
                    continue
                cells = raster_poly(rot_pts(np.array(p_, float), deg), rk, -fx, -fy, g)
                for l in lay:
                    keep.setdefault(2 + l, []).append(cells)
            # thermal-relief spoke corridors of pads poured by a zone of their own net:
            # other parts' pads stay out so the pour can form its spokes (starved_thermal)
            if pad["net"] and pad["poly"]:
                for l in lay:
                    zs = self.zone_nets.get((pad["net"], l))
                    if not zs:
                        continue
                    gap, spoke, minw = zs
                    allp = rot_pts(np.concatenate([np.array(q, float) for q in pad["poly"] if len(q) >= 3]), deg)
                    x0, y0 = allp.min(0)
                    x1, y1 = allp.max(0)
                    mx, my, ext, hs = (x0 + x1) / 2, (y0 + y1) / 2, gap + max(spoke, minw), spoke / 2
                    for rc in ([[x1, my - hs], [x1 + ext, my - hs], [x1 + ext, my + hs], [x1, my + hs]],
                               [[x0 - ext, my - hs], [x0, my - hs], [x0, my + hs], [x0 - ext, my + hs]],
                               [[mx - hs, y1], [mx + hs, y1], [mx + hs, y1 + ext], [mx - hs, y1 + ext]],
                               [[mx - hs, y0 - ext], [mx + hs, y0 - ext], [mx + hs, y0], [mx - hs, y0]]):
                        rc = np.array(rc) + np.array([fx, fy])
                        keep.setdefault(2 + l, []).append(raster_poly(rc, R.c / 2 + 0.71 * g, 0.0, 0.0, g))
            if drilled:  # the hole itself (NPTH has no copper polygon): hole clearance
                c0 = rot_pts(np.array([[pad["x"], pad["y"]]]), deg)[0] + np.array([fx, fy])
                rh = max(pad["drill"]) / 2 + max(R.hc - R.c / 2, R.hc / 2) + ex + 0.71 * g
                hole = disc(rh, g) + np.round(c0 / g).astype(np.int32)
                for l in range(self.nl):
                    keep.setdefault(2 + l, []).append(hole.astype(np.int32))
                # a hole may not sit under another part's courtyard on either side
                # (KiCad pth_inside_courtyard / npth_inside_courtyard)
                bare = disc(max(pad["drill"]) / 2 + 0.71 * g, g) + np.round(c0 / g).astype(np.int32)
                for side in (0, 1):
                    keep.setdefault(side, []).append(bare.astype(np.int32))
        # the board cutout a footprint draws (sensor window, slot) is a hole in the board:
        # nothing of another part may sit inside it, on any plane
        cut = _cutout_cells(part, deg, fx, fy, g)
        if len(cut):
            for plane in range(2 + self.nl):
                keep.setdefault(plane, []).append(cut)
        side_cells = [raster_poly(rot_pts(c, deg), 0.75 * g, -fx, -fy, g) for c in part.court] + \
                     [raster_poly(rot_pts(np.array(e, float), deg), R.ec + 0.75 * g, -fx, -fy, g)
                      for e in part.data.get("edges", []) if len(e) >= 3]
        keep.setdefault(part.side, []).extend(side_cells)
        other = [np.array(c, float) for c in part.data.get("courtyard_other", []) if len(c) >= 3]
        if other:
            keep.setdefault(1 - part.side, []).extend(
                raster_poly(rot_pts(c, deg), 0.75 * g, -fx, -fy, g) for c in other)
        keep = [(pl, np.ascontiguousarray(np.unique(np.concatenate(cs), axis=0), np.int32))
                for pl, cs in sorted(keep.items())]
        court = np.unique(np.concatenate([c for _, c in keep]), axis=0).astype(np.int32)
        # board-edge check: every point of the pad copper must keep the edge clearance.
        # Sampling only the cells whose centre is inside a pad misses up to a cell of copper
        # beyond them (a pad edge between cell centres), so test the cells within 0.71 g of
        # the copper instead (0.71 g, as in engine v6.3): every copper point is within g / sqrt(2)
        # of such a cell, and ok_cu demands ec + 0.75 g at that cell.
        allcu = [raster_poly(rot_pts(np.array(p_, float), deg), 0.71 * g, -fx, -fy, g)
                 for pad in part.pads for p_ in pad["poly"] if len(p_) >= 3]
        allcu += fcu_edge
        # a part's own board cutouts must lie inside the board, like copper
        allcu += [raster_poly(rot_pts(np.array(e, float), deg), 0.75 * g, -fx, -fy, g)
                  for e in part.data.get("edges", []) if len(e) >= 3]
        allcu = np.concatenate(allcu) if allcu else np.zeros((0, 2), np.int32)
        r = dict(pads=pads, court=np.ascontiguousarray(court), keep=keep, cu=np.ascontiguousarray(allcu, np.int32),
                 bbox=(court[:, 0].min(), court[:, 1].min(), court[:, 0].max(), court[:, 1].max()))
        part.cache[key] = r
        return r

    def _stamp_part(self, part, cx, cy, ri, delta, frac=(0.0, 0.0)):
        r = self.part_raster(part, ri, frac)
        for ent in r["pads"]:
            for l in ent["layers_halo"]:
                stamp(self.occT, self.DT, ent["net"], l, ent["hT"], cx, cy, delta)
                stamp(self.occV, self.DV, ent["net"], l, ent["hV"], cx, cy, delta)
        for plane, cells in r["keep"]:
            count_add(self.court, plane, cells, cx, cy, delta)

    def place(self, pi, cx, cy, ri, frac=(0.0, 0.0)):
        if pi in self.pose:
            self.unplace(pi)
        self._stamp_part(self.parts[pi], cx, cy, ri, 1, frac)
        self.pose[pi] = (cx, cy, ri)
        if frac != (0.0, 0.0):
            self.frac[pi] = frac
        else:
            self.frac.pop(pi, None)

    def unplace(self, pi):
        cx, cy, ri = self.pose.pop(pi)
        self._stamp_part(self.parts[pi], cx, cy, ri, -1, self.frac.pop(pi, (0.0, 0.0)))

    def raster(self, pi):
        cx, cy, ri = self.pose[pi]
        return self.part_raster(self.parts[pi], ri, self.frac.get(pi, (0.0, 0.0)))

    def rot_index(self, deg):
        deg = deg % 360
        return min(range(4), key=lambda i: min(abs(ROTS[i] - deg), 360 - abs(ROTS[i] - deg)))

    def place_original(self, pi, exact=True):
        """Put part pi where the input board has it. exact keeps the sub-cell offset and
        the exact orientation (only multiples of 90 degrees are supported for moves)."""
        p = self.parts[pi]
        cx, cy = self.cell(p.x0, p.y0)
        frac = (p.x0 - self.xy(cx, cy)[0], p.y0 - self.xy(cx, cy)[1]) if exact else (0.0, 0.0)
        ri = self.rot_index(p.rot0)
        if exact and abs((p.rot0 - ROTS[ri] + 180) % 360 - 180) > 1e-6:
            ri = 4  # off-axis orientation, only for parts that stay put
        self.place(pi, cx, cy, ri, frac)
        self.fixed.add(pi) if exact else None

    # ---------------------------------------------------------------- legality
    def part_violation(self, pi, cx=None, cy=None, ri=None):
        """(courtyard overlap cells, outside cells) for part pi at a pose (default: current).
        Assumes the part is not stamped at that pose when a pose is given."""
        part = self.parts[pi]
        if cx is None:
            cx, cy, ri = self.pose[pi]
            own = 1
        else:
            own = 0
        r = self.part_raster(part, ri, self.frac.get(pi, (0.0, 0.0)) if own else (0.0, 0.0))
        overlap = 0
        for plane, c in r["keep"]:
            xs, ys = c[:, 0] + cx, c[:, 1] + cy
            okb = (xs >= 0) & (ys >= 0) & (xs < self.W) & (ys < self.H)
            overlap += int((self.court[plane, ys[okb], xs[okb]] - own > 0).sum())
        outside = 0  # courtyards may overhang the board edge (KiCad does not check it)
        cu = r["cu"]
        xs, ys = cu[:, 0] + cx, cu[:, 1] + cy
        okb = (xs >= 0) & (ys >= 0) & (xs < self.W) & (ys < self.H)
        outside += int((~okb).sum()) + int((~self.ok_cu[ys[okb], xs[okb]]).sum())
        return overlap, outside

    def terminals(self, pi, k):
        """Copper cells (l, y, x) of pad k of placed part pi."""
        cx, cy, ri = self.pose[pi]
        ent = self.raster(pi)["pads"][k]
        out = []
        for l in ent["layers"]:
            for (x, y) in ent["cu"]:
                out.append((l, y + cy, x + cx))
        return out

    def pad_world(self, pi, k):
        cx, cy, ri = self.pose[pi]
        ent = self.raster(pi)["pads"][k]
        x, y = self.xy(cx, cy)
        return x + ent["center"][0], y + ent["center"][1]

    def hpwl(self, nets=None):
        tot = 0.0
        for n, pins in self.net_pins.items():
            if nets is not None and n not in nets:
                continue
            pts = [self.pad_world(pi, k) for pi, k in pins if pi in self.pose]
            if len(pts) < 2:
                continue
            a = np.array(pts)
            tot += np.ptp(a[:, 0]) + np.ptp(a[:, 1])
        return tot
