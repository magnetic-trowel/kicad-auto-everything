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
        self.pad_T = c + w / 2 + m
        self.pad_V = max(c + dv / 2, self.hc + dr / 2) + m

    def __repr__(self):
        return (f"Rules(g={self.g} w={self.w} c={self.c} via={self.via_d}/{self.via_drill} "
                f"hc={self.hc} h2h={self.h2h} ec={self.ec})")


class Part:
    def __init__(self, idx, fp):
        self.idx = idx
        self.ref, self.uuid = fp["ref"], fp["uuid"]
        self.locked = fp["locked"]
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
        # through-hole parts block both sides (their pads reach the far side)
        self.sides = (0, 1) if any(p["cu"] == "both" for p in self.pads) else (self.side,)
        self.cache = {}
        self.area = sum(_poly_area(c) for c in self.court)

    def nets(self):
        return {p["net"] for p in self.pads if p["net"]}


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
        self.court = np.zeros((2, H, W), np.int16)
        self.hist = np.zeros((L, H, W), np.float32)
        self._static_masks()
        self.parts = [Part(i, fp) for i, fp in enumerate(data["footprints"])]
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
        for ko in self.data["keepouts"]:
            for poly in ko["poly"]:
                cells = raster_poly(np.array(poly, float), R.m, self.x0, self.y0, g)
                for l in range(self.nl):
                    lid = 0 if l == 0 else (2 if l == self.nl - 1 else 4 + 2 * (l - 1))  # KiCad 9+ ids
                    if lid not in ko["layers"]:
                        continue
                    for (x, y) in cells:
                        if 0 <= x < self.W and 0 <= y < self.H:
                            if ko["tracks"]:
                                self.blockT[l, y, x] = True
                            if ko["vias"]:
                                self.blockV[l, y, x] = True

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
            for pl in polys:
                cu.append(raster_poly(pl, 0.0, -fx, -fy, g))
                hT.append(raster_poly(pl, R.pad_T, -fx, -fy, g))
                hV.append(raster_poly(pl, R.pad_V, -fx, -fy, g))
            drill = max(pad["drill"]) if pad["drill"] else 0.0
            if drill > 0:
                rv = drill / 2 + max(R.h2h + R.via_drill / 2, R.hc + R.via_d / 2) + R.m
                cc = np.round((c + np.array([fx, fy])) / g).astype(np.int32)
                d = disc(rv + 0.71 * g, g) + cc
                hV.append(d.astype(np.int32))
                if pad["npth"] or not polys:
                    rt = drill / 2 + R.hc + R.w / 2 + R.m
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
        for e in part.data.get("edges", []):
            if len(e) < 3:
                continue
            pl = rot_pts(np.array(e, float), deg)
            pads.append(dict(net=0, layers=[], npth=True, center=np.array([fx, fy]),
                             cu=np.zeros((0, 2), np.int32), layers_halo=list(range(self.nl)),
                             hT=raster_poly(pl, R.ec + R.w / 2 + R.m, -fx, -fy, g),
                             hV=raster_poly(pl, R.ec + R.via_d / 2 + R.m, -fx, -fy, g)))
        # keep-out = courtyard, the part's own board cutouts, and its pads grown by half the
        # clearance (some library courtyards do not cover their pads)
        padkeep = [raster_poly(rot_pts(np.array(p_, float), deg), R.c / 2 + 0.05 + 0.75 * g, -fx, -fy, g)
                   for pad in part.pads for p_ in pad["poly"] if len(p_) >= 3]
        court = np.concatenate(padkeep + [raster_poly(rot_pts(c, deg), 0.75 * g, -fx, -fy, g) for c in part.court] +
                               [raster_poly(rot_pts(np.array(e, float), deg), R.ec + 0.75 * g, -fx, -fy, g)
                                for e in part.data.get("edges", []) if len(e) >= 3])
        court = np.unique(court, axis=0).astype(np.int32)
        allcu = [p["cu"] for p in pads if len(p["cu"])]
        allcu = np.concatenate(allcu) if allcu else np.zeros((0, 2), np.int32)
        r = dict(pads=pads, court=np.ascontiguousarray(court), cu=np.ascontiguousarray(allcu, np.int32),
                 bbox=(court[:, 0].min(), court[:, 1].min(), court[:, 0].max(), court[:, 1].max()))
        part.cache[key] = r
        return r

    def _stamp_part(self, part, cx, cy, ri, delta, frac=(0.0, 0.0)):
        r = self.part_raster(part, ri, frac)
        for ent in r["pads"]:
            for l in ent["layers_halo"]:
                stamp(self.occT, self.DT, ent["net"], l, ent["hT"], cx, cy, delta)
                stamp(self.occV, self.DV, ent["net"], l, ent["hV"], cx, cy, delta)
        for side in part.sides:
            count_add(self.court, side, r["court"], cx, cy, delta)

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
        c = r["court"]
        side = part.side
        xs, ys = c[:, 0] + cx, c[:, 1] + cy
        okb = (xs >= 0) & (ys >= 0) & (xs < self.W) & (ys < self.H)
        outside = int((~okb).sum())
        xs, ys = xs[okb], ys[okb]
        overlap = sum(int((self.court[s, ys, xs] - own > 0).sum()) for s in part.sides)
        outside += int((~self.ok_court[ys, xs]).sum())
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
