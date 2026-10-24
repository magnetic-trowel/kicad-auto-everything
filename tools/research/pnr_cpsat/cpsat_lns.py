# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact simultaneous place-and-route of small windows with CP-SAT, as an LNS step.

Catalog ideas 12 + 36 (docs/ideas/original/joint-pnr.md); sources: SP&R (Lee et al.,
TCAD 2021, SMT simultaneous P&R of standard cells), Numberlink / Flow-Free SAT
encodings, Factorio-SAT.

Loop: start from a placed + routed board (methods.seq). Pick a target net (unrouted,
else most detoured), a rectangular window around it holding 2-6 movable parts, rip up
those parts and every net that touches them or crosses the window, and solve one CP-SAT
model on a coarse grid (pitch = smallest even multiple of the engine cell >= the
track-to-track halo radius, so different nets on 4-adjacent coarse cells are legal):

  pose      one Boolean per (part, origin on the coarse lattice, rotation) whose
            courtyard is legal against fixed parts (checked on the 0.1 mm grid) and
            lies inside the window; exactly one per part; courtyard bounding boxes
            pairwise disjoint (NoOverlap2D, per board side)
  occupancy o[n, l, c] Boolean per net, layer, coarse cell (cells blocked by fixed
            foreign copper on the fine grid get no variable); sum_n o <= 1 per cell;
            a pose forces o[pad net] on its pad's clearance halo cells and blocks cells
            where two pads of one part compete
  routing   per net single-commodity flow on 4-neighbour edges and vias: the root
            (an exit cell on the window border with cost = distance to the nearest
            outside pin, or one in-window pin) supplies one unit per connected
            terminal; terminals are pad copper cells chosen by the poses (or fixed
            pads / boundary crossings of passing nets); a via clears its 8 neighbours
  objective 3000 * missed terminals + wirelength (0.1 mm) + 20 per via + exit cost

Decode: place the parts at the solved poses (on the engine grid by construction,
checked with World.part_violation), re-route the ripped nets with the engine's
PathFinder (optionally biased toward the CP-SAT corridors), accept if Kit.total_cost
fell.
"""
import math
import random
import sys
import time

import numpy as np

sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")

from ortools.sat.python import cp_model  # noqa: E402

import methods  # noqa: E402
from placekit import Clock, Kit  # noqa: E402

MISS = 3000  # objective units (0.1 mm) per terminal left unconnected
VIA = 20     # 2 mm per via, as in Kit.total_cost


# ---------------------------------------------------------------- window choice
def _court_bbox(world, pi, pose=None):
    cx, cy, ri = pose or world.pose[pi]
    frac = world.frac.get(pi, (0.0, 0.0)) if pose is None else (0.0, 0.0)
    bx0, by0, bx1, by1 = world.part_raster(world.parts[pi], ri, frac)["bbox"]
    return cx + bx0, cy + by0, cx + bx1, cy + by1


def _npads(world, pi):
    return len(world.parts[pi].pads)


def pick_window(world, kit, rng, max_parts=5, side_mm=9.0, margin_mm=1.2, max_pads=20):
    """Target net (unrouted, else most detoured), seed part on it, window of side_mm
    centred between the seed and the nearest other pin; parts fully inside (blockers of
    the net and the net's own parts first). Returns (net, parts, (fx0, fy0, fx1, fy1))."""
    r = kit.r
    mov = {q for q in kit.movable() if q in world.pose}
    unr = [n for n in world.net_pins if r.unrouted.get(n)]
    if unr:
        net = rng.choice(unr)
    else:
        ratios = {n: kit.net_cost(n, unrouted_mm=0) / (world.hpwl([n]) + 1.0) for n in world.net_pins}
        net = max(ratios, key=lambda n: ratios[n] * rng.uniform(0.7, 1.3))
    side = int(side_mm / world.g)
    snap = kit.snapshot([net])
    bl = methods.blockers(world, kit, net)
    kit.restore(snap)
    for grow in (1.0, 1.4, 1.8):
        res = _window_at(world, kit, rng, net, mov, bl, int(side * grow), max_parts, margin_mm, max_pads)
        if res[1] is not None:
            return (net,) + res
    return net, [], None


def _window_at(world, kit, rng, net, mov, bl, side, max_parts, margin_mm, max_pads):
    small = {pi for pi in mov if _npads(world, pi) <= max_pads}
    own = [pi for pi, k in world.net_pins[net] if pi in small]
    if not own:
        own = [rng.choice(sorted(small))] if small else []
    if not own:
        return [], None
    seed = rng.choice(own)
    sx0, sy0, sx1, sy1 = _court_bbox(world, seed)
    scx, scy = (sx0 + sx1) / 2, (sy0 + sy1) / 2
    # nearest other pin of the net
    best = None
    for pi, k in world.net_pins[net]:
        if pi == seed or pi not in world.pose:
            continue
        x, y = world.cell(*world.pad_world(pi, k))
        d = abs(x - scx) + abs(y - scy)
        if best is None or d < best[0]:
            best = (d, x, y)
    cx, cy = scx, scy
    if best is not None and abs(best[1] - scx) < side * 0.8 and abs(best[2] - scy) < side * 0.8:
        cx, cy = (scx + best[1]) / 2, (scy + best[2]) / 2
    wx0, wy0 = int(cx - side / 2), int(cy - side / 2)
    wx1, wy1 = wx0 + side, wy0 + side
    # rank candidate parts: the net's own, blockers, then distance to the centre
    inside = []
    for pi in small:
        x0, y0, x1, y1 = _court_bbox(world, pi)
        if x0 >= wx0 and y0 >= wy0 and x1 <= wx1 and y1 <= wy1:
            key = (0 if pi == seed else 1, -(pi in own) - bl.get(pi, 0) / 10.0,
                   abs((x0 + x1) / 2 - cx) + abs((y0 + y1) / 2 - cy))
            inside.append((key, pi))
    inside.sort()
    parts = [pi for _, pi in inside[:max_parts]]
    if len(parts) < 2:
        return parts, None
    # shrink the window to the parts' bbox + margin (kept inside the side limit)
    m = int(margin_mm / world.g)
    bbs = np.array([_court_bbox(world, pi) for pi in parts])
    fx0 = max(wx0, int(bbs[:, 0].min()) - m)
    fy0 = max(wy0, int(bbs[:, 1].min()) - m)
    fx1 = min(wx1, int(bbs[:, 2].max()) + m)
    fy1 = min(wy1, int(bbs[:, 3].max()) + m)
    fx0, fy0 = max(1, fx0), max(1, fy0)
    fx1, fy1 = min(world.W - 2, fx1), min(world.H - 2, fy1)
    return parts, (fx0, fy0, fx1, fy1)


# ---------------------------------------------------------------- model
class Window:
    """Everything needed to build, solve and decode one CP-SAT window."""

    def __init__(self, world, kit, parts, box, pitch=None, workers=1, cross=False, lin=0,
                 radius=None, cmargin=2):
        self.w, self.kit, self.parts, self.box = world, kit, list(parts), box
        R = world.R
        s = pitch or int(math.ceil(R.R_TT / world.g / 2.0)) * 2
        self.s = max(2, s)
        fx0, fy0, fx1, fy1 = box
        self.NX = (fx1 - fx0) // self.s + 1
        self.NY = (fy1 - fy0) // self.s + 1
        self.layers = [0] if world.nl == 1 else [0, world.nl - 1]
        self.workers = workers
        self.lin = lin
        self.presolve = False
        self.radius = radius    # pose search radius around the current pose (coarse cells)
        self.cmargin = cmargin  # routing corridor margin around a connection's terminals
        self.cross = cross  # sample pad halos at cell centre + edge midpoints (stricter)
        self.stats = {}

    # fine coordinates of coarse cell (i, j)
    def fxy(self, i, j):
        return self.box[0] + i * self.s, self.box[1] + j * self.s

    def inside_fine(self, x, y):
        fx0, fy0, fx1, fy1 = self.box
        return fx0 <= x <= fx1 and fy0 <= y <= fy1

    # ------------------------------------------------------------ rip
    def rip(self):
        """Collect the nets to rip (window parts' nets + nets whose copper crosses the
        window), record boundary crossings of passing nets, rip them, unplace parts."""
        w, r = self.w, self.kit.r
        own = self.kit.part_nets(self.parts)
        fx0, fy0, fx1, fy1 = self.box
        passing = {}
        for n, ps in r.routes.items():
            if n in own or not ps:
                continue
            cross = []
            hit = False
            for p in ps:
                ins = (p[:, 2] >= fx0) & (p[:, 2] <= fx1) & (p[:, 1] >= fy0) & (p[:, 1] <= fy1)
                if not ins.any():
                    continue
                hit = True
                for i in range(len(p)):
                    if ins[i] and ((i > 0 and not ins[i - 1]) or (i + 1 < len(p) and not ins[i + 1])):
                        cross.append((int(p[i, 2]), int(p[i, 1])))
            if hit:
                passing[n] = cross
        self.own_nets = own
        self.passing = passing
        self.rip_nets = sorted(own | set(passing))
        self.snap = self.kit.snapshot(self.rip_nets)
        self.poses0 = {pi: w.pose[pi] for pi in self.parts}
        self.frac0 = {pi: w.frac.get(pi, (0.0, 0.0)) for pi in self.parts}
        for n in self.rip_nets:
            r.rip(n)
        for pi in self.parts:
            w.unplace(pi)

    def undo(self):
        """Back to the state before rip()."""
        w = self.w
        for pi in self.parts:
            if pi in w.pose:
                w.unplace(pi)
        for pi, (cx, cy, ri) in self.poses0.items():
            w.place(pi, cx, cy, ri, self.frac0[pi])
        self.kit.restore(self.snap)

    # ------------------------------------------------------------ fixed-state masks
    def _masks(self):
        """Per net: usable coarse cells per model layer, usable edges, via sites."""
        w, s = self.w, self.s
        fx0, fy0, fx1, fy1 = self.box
        sl = (slice(fy0, fy1 + 1), slice(fx0, fx1 + 1))
        nets = self.model_nets
        self.cell_ok, self.edge_ok, self.via_ok = {}, {}, {}
        jj, ii = np.mgrid[0:self.NY, 0:self.NX]
        cyf, cxf = jj * s, ii * s  # local fine coords of coarse centres
        allL = range(w.nl)
        for n in nets:
            free = {}
            for li, l in enumerate(self.layers):
                fr = (~w.blockT[l][sl]) & ((w.DT[l][sl] - (w.occT[n, l][sl] > 0)) == 0)
                free[li] = fr
                self.cell_ok[n, li] = fr[cyf, cxf]
                # horizontal edge (i,j)-(i+1,j): every fine cell on the segment free
                h = np.ones((self.NY, self.NX - 1), bool)
                for d in range(s + 1):
                    h &= fr[cyf[:, :-1], cxf[:, :-1] + d]
                v = np.ones((self.NY - 1, self.NX), bool)
                for d in range(s + 1):
                    v &= fr[cyf[:-1, :] + d, cxf[:-1, :]]
                self.edge_ok[n, li, 0] = h
                self.edge_ok[n, li, 1] = v
            vo = np.ones((fy1 - fy0 + 1, fx1 - fx0 + 1), bool)
            for l in allL:
                vo &= ~w.blockV[l][sl] & ~w.blockT[l][sl]
                vo &= (w.DV[l][sl] - (w.occV[n, l][sl] > 0)) == 0
                vo &= (w.DT[l][sl] - (w.occT[n, l][sl] > 0)) == 0
            self.via_ok[n] = vo[cyf, cxf] if len(self.layers) > 1 else np.zeros((self.NY, self.NX), bool)

    # ------------------------------------------------------------ pose tables
    def _pose_tables(self, pi, ri, phase):
        """Coarse offsets (relative to the origin's coarse cell) for part pi at rotation ri
        with the origin at fine offset `phase` from a coarse centre:
        owners[(li, di, dj)] = net (or -1 = blocked), terms[k] = [(li, di, dj)]."""
        w, s = self.w, self.s
        rr = w.part_raster(w.parts[pi], ri)
        px, py = phase
        h = s // 2
        cross = np.array([[0, 0], [h, 0], [-h, 0], [0, h], [0, -h]] if self.cross else [[0, 0]], np.int32)
        owners = {}
        terms = {}
        for k, ent in enumerate(rr["pads"]):
            n = ent["net"] if ent["net"] in self.model_set else -1
            hT = ent["hT"]
            if len(hT):
                pts = (hT[None, :, :] + cross[:, None, :]).reshape(-1, 2) + np.array([px, py])
                pts = pts[(pts[:, 0] % s == 0) & (pts[:, 1] % s == 0)] // s
                pts = np.unique(pts, axis=0)
                for l in ent["layers_halo"]:
                    li = self._li(l)
                    if li is None:
                        continue
                    for di, dj in pts:
                        key = (li, int(di), int(dj))
                        prev = owners.get(key)
                        owners[key] = n if prev is None or prev == n else -1
            if ent["net"] in self.model_set and k < len(w.parts[pi].pads):
                cu = ent["cu"] + np.array([px, py])
                c = cu[(cu[:, 0] % s == 0) & (cu[:, 1] % s == 0)] // s if len(cu) else np.zeros((0, 2), int)
                if len(c) == 0:
                    cc = (ent["center"] / w.g + np.array([px, py])) / s
                    c = np.round(cc).astype(int)[None]
                c = np.unique(c, axis=0)
                terms[k] = [(self._li(l), int(di), int(dj)) for l in ent["layers"] if self._li(l) is not None
                            for di, dj in c]
        for k in list(terms):
            terms[k] = [t for t in terms[k] if owners.get(t) == rr["pads"][k]["net"]]
            if not terms[k]:  # contested by a neighbouring pad (fine pitch): not modelled
                del terms[k]
        return owners, terms

    def _li(self, l):
        if l == 0:
            return 0
        if l == self.w.nl - 1 and len(self.layers) > 1:
            return 1
        return None

    def _legal_origins(self, pi, ri, ox, oy):
        """Bool per candidate fine origin: keep-out planes free (courtyard per side, pad
        keep-out per copper layer, as World.part_violation), pad copper inside the board."""
        w = self.w
        rr = w.part_raster(w.parts[pi], ri)
        ok = np.ones(len(ox), bool)
        for plane, c in rr["keep"]:
            xs = ox[:, None] + c[None, :, 0]
            ys = oy[:, None] + c[None, :, 1]
            inb = (xs >= 0) & (ys >= 0) & (xs < w.W) & (ys < w.H)
            xs, ys = np.clip(xs, 0, w.W - 1), np.clip(ys, 0, w.H - 1)
            ok &= ~((w.court[plane][ys, xs] > 0) & inb).any(1)
        cu = rr["cu"]
        if len(cu):
            xs = ox[:, None] + cu[None, :, 0]
            ys = oy[:, None] + cu[None, :, 1]
            inb = ((xs >= 0) & (ys >= 0) & (xs < w.W) & (ys < w.H)).all(1)
            xs, ys = np.clip(xs, 0, w.W - 1), np.clip(ys, 0, w.H - 1)
            ok &= inb & w.ok_cu[ys, xs].all(1)
        return ok

    # ------------------------------------------------------------ build
    def build(self, extra=None, lattice=True, phys=None, phys_w=2.0):
        w, s = self.w, self.s
        fx0, fy0, fx1, fy1 = self.box
        t0 = time.time()
        self.model_nets = [n for n in self.rip_nets if n in self.own_nets or len(self.passing.get(n, [])) >= 1]
        self.model_set = set(self.model_nets)
        self._masks()
        M = cp_model.CpModel()
        self.M = M
        NX, NY, LL = self.NX, self.NY, len(self.layers)
        # ---- poses
        self.pv = {}  # pi -> list of (var, ox, oy, ri, owners_abs, terms_abs)
        block_terms = {}  # (pi, li, i, j) -> [vars]
        own_terms = {}    # (n, li, i, j) -> {pi: [vars]}
        term_cov = {}     # (pi, k) -> {(li, i, j): [vars]}
        npose = 0
        for pi in self.parts:
            part = w.parts[pi]
            lst = []
            cur = self.poses0[pi]
            for ri in range(4):
                rr = w.part_raster(part, ri)
                bx0, by0, bx1, by1 = rr["bbox"]
                # coarse origins with the courtyard bbox inside the window
                cand = []
                for j in range(NY if lattice else 0):
                    for i in range(NX):
                        ox, oy = self.fxy(i, j)
                        if self.radius is not None and (abs(ox - cur[0]) > self.radius * s or
                                                        abs(oy - cur[1]) > self.radius * s):
                            continue
                        if ox + bx0 >= fx0 and oy + by0 >= fy0 and ox + bx1 <= fx1 and oy + by1 <= fy1:
                            cand.append((ox, oy, i, j, 0, 0))
                # off-lattice poses: the current one (so "stay" is always representable) and
                # any extra candidates (e.g. the heuristic's HPWL candidates, fine grid)
                offl = [tuple(cur)] if self.frac0[pi] == (0.0, 0.0) else []
                offl += [tuple(p) for p in (extra or {}).get(pi, [])]
                seen = {(c[0], c[1]) for c in cand}
                for (ox, oy, rj) in offl:
                    if rj != ri or (ox, oy) in seen:
                        continue
                    seen.add((ox, oy))
                    i, j = (ox - fx0) // s, (oy - fy0) // s
                    px, py = (ox - fx0) - i * s, (oy - fy0) - j * s
                    if ox + bx0 >= fx0 and oy + by0 >= fy0 and ox + bx1 <= fx1 and oy + by1 <= fy1:
                        cand.append((ox, oy, i, j, px, py))
                if not cand:
                    continue
                ca = np.array(cand)
                ok = self._legal_origins(pi, ri, ca[:, 0], ca[:, 1])
                tabs = {}
                for (ox, oy, i, j, px, py), good in zip(cand, ok):
                    if not good:
                        continue
                    if (px, py) not in tabs:
                        tabs[px, py] = self._pose_tables(pi, ri, (px, py))
                    owners, terms = tabs[px, py]
                    # every routed pad must have a terminal cell inside the window
                    bad = False
                    oabs = [(n, li, i + di, j + dj) for (li, di, dj), n in owners.items()
                            if 0 <= i + di < NX and 0 <= j + dj < NY]
                    tabs_abs = {}
                    for k, tl in terms.items():
                        tt = [(li, i + di, j + dj) for li, di, dj in tl if 0 <= i + di < NX and 0 <= j + dj < NY]
                        if not tt:
                            bad = True
                            break
                        tabs_abs[k] = tt
                    if bad:
                        continue
                    v = M.NewBoolVar(f"p{pi}_{ri}_{ox}_{oy}")
                    lst.append((v, ox, oy, ri, oabs, tabs_abs))
                    for n, li, a, b in oabs:
                        if n < 0:
                            block_terms.setdefault((pi, li, a, b), []).append(v)
                        else:
                            own_terms.setdefault((n, li, a, b), {}).setdefault(pi, []).append(v)
                    for k, tt in tabs_abs.items():
                        d = term_cov.setdefault((pi, k), {})
                        for t in tt:
                            d.setdefault(t, []).append(v)
            if not lst:
                self.stats["fail"] = f"no pose for {part.ref}"
                return False
            npose += len(lst)
            M.AddExactlyOne([e[0] for e in lst])
            self.pv[pi] = lst
        # ---- physics place terms (kae.physics), first order: per-pose delta vs the current
        # board, in objective units (0.1 mm of routed copper per phys_w^-1 units of physics)
        self.phys_obj = []
        if phys is not None:
            for pi, lst in self.pv.items():
                if pi not in phys.active:
                    continue
                for v, ox, oy, ri, _, _ in lst:
                    d = phys.delta(pi, (ox, oy, ri))
                    c = int(round(10 * phys_w * d))
                    if c:
                        self.phys_obj.append(c * v)
        # ---- keep-out bounding boxes disjoint, per keep-out plane (courtyard per side, pad
        # keep-out per copper layer). Boxes are shrunk by one cell: a raster's edge rows are
        # partial (rounded corners), so touching legal parts share them; decode re-checks.
        ivs = {}
        for pi, lst in self.pv.items():
            part = w.parts[pi]
            planes = {}
            for ri in range(4):
                for plane, c in w.part_raster(part, ri)["keep"]:
                    x0, y0 = c.min(0)
                    x1, y1 = c.max(0)
                    planes.setdefault(plane, {})[ri] = (x0 + 1, y0 + 1, max(x0 + 1, x1 - 1), max(y0 + 1, y1 - 1))
            for plane, bbs in planes.items():
                if len(bbs) < 4:
                    continue
                xs = sum(v * int(ox + bbs[ri][0]) for v, ox, oy, ri, _, _ in lst)
                ys = sum(v * int(oy + bbs[ri][1]) for v, ox, oy, ri, _, _ in lst)
                ws = sum(v * int(bbs[ri][2] - bbs[ri][0] + 1) for v, ox, oy, ri, _, _ in lst)
                hs = sum(v * int(bbs[ri][3] - bbs[ri][1] + 1) for v, ox, oy, ri, _, _ in lst)
                lo, hi = min(fx0, fy0) - 400, max(fx1, fy1) + 400
                X = M.NewIntVar(lo, hi, "")
                Y = M.NewIntVar(lo, hi, "")
                Wd = M.NewIntVar(1, hi - lo, "")
                Hd = M.NewIntVar(1, hi - lo, "")
                M.Add(X == xs)
                M.Add(Y == ys)
                M.Add(Wd == ws)
                M.Add(Hd == hs)
                Xe = M.NewIntVar(lo, 2 * hi, "")
                Ye = M.NewIntVar(lo, 2 * hi, "")
                M.Add(Xe == X + Wd)
                M.Add(Ye == Y + Hd)
                ivs.setdefault(plane, []).append((M.NewIntervalVar(X, Wd, Xe, ""), M.NewIntervalVar(Y, Hd, Ye, "")))
        for plane, lst_ in ivs.items():
            if len(lst_) > 1:
                M.AddNoOverlap2D([a for a, b in lst_], [b for a, b in lst_])
        # ---- routing
        nets = self.model_nets
        o = {}
        for n in nets:
            for li in range(LL):
                ok = self.cell_ok[n, li]
                for j in range(NY):
                    for i in range(NX):
                        if ok[j, i]:
                            o[n, li, i, j] = M.NewBoolVar("")
        self.o = o
        # exclusivity of nets per cell
        S = {}
        for li in range(LL):
            for j in range(NY):
                for i in range(NX):
                    terms = [o[n, li, i, j] for n in nets if (n, li, i, j) in o]
                    S[li, i, j] = terms
                    if len(terms) > 1:
                        M.Add(sum(terms) <= 1)
        # a pad's clearance halo keeps other nets out (one constraint per part and cell;
        # a part's poses are mutually exclusive); cells two pads of a part compete for
        # are closed to every net
        for (m, li, a, b), byp in own_terms.items():
            others = [o[n, li, a, b] for n in nets if n != m and (n, li, a, b) in o]
            if not others:
                continue
            for pi, vs in byp.items():
                M.Add(sum(others) + sum(vs) <= 1)
        for (pi, li, a, b), vs in block_terms.items():
            if S[li, a, b]:
                M.Add(sum(S[li, a, b]) + sum(vs) <= 1)
        obj = []
        self.u, self.vv = {}, {}
        self.term_info = {}
        self.miss = {}
        nterm = 0
        # via site per net (shared by the net's connections) with its clearance rule
        vnet = {}
        wnet = {}  # (n, li, i, j, dirn) -> net-level edge literal (wirelength counted once)

        def net_edge(n, key):
            if key not in wnet:
                wnet[key] = M.NewBoolVar("")
                obj.append(s * wnet[key])
                self.u[key] = wnet[key]
            return wnet[key]

        def net_via(n, i, j):
            key = (n, i, j)
            if key in vnet:
                return vnet[key]
            v = M.NewBoolVar("")
            vnet[key] = v
            self.vv[key] = v
            obj.append(VIA * v)
            M.AddImplication(v, o[n, 0, i, j])
            M.AddImplication(v, o[n, 1, i, j])
            for dj in (-1, 0, 1):
                for di in (-1, 0, 1):
                    a2, b2 = i + di, j + dj
                    if (di, dj) == (0, 0) or not (0 <= a2 < NX and 0 <= b2 < NY):
                        continue
                    for li in range(LL):
                        foreign = [t for t in S[li, a2, b2] if t is not o.get((n, li, a2, b2))]
                        if foreign:
                            M.Add(sum(foreign) + v <= 1)
            return v

        for n in nets:
            # terminals: (kind, data, representative fine position)
            terms = []
            ext = []
            for pi, k in w.net_pins[n]:
                if pi not in self.pv and pi not in w.pose:
                    continue  # unplaced part (no legal spot): its pins are not routed
                if pi in self.pv:
                    cx, cy, ri = self.poses0[pi]
                    c = w.part_raster(w.parts[pi], ri, self.frac0[pi])["pads"][k]["center"] / w.g
                    terms.append(("pose", (pi, k), (cx + c[0], cy + c[1])))
                    continue
                x, y = w.cell(*w.pad_world(pi, k))
                if self.inside_fine(x, y):
                    cells = []
                    for (l, yy, xx) in w.terminals(pi, k):
                        li = self._li(l)
                        if li is None:
                            continue
                        if (xx - fx0) % s == 0 and (yy - fy0) % s == 0:
                            a, b = (xx - fx0) // s, (yy - fy0) // s
                            if (n, li, a, b) in o:
                                cells.append((li, a, b))
                    if not cells:  # nearest usable coarse cell to the pad centre
                        a = int(round((x - fx0) / s))
                        b = int(round((y - fy0) / s))
                        for l in w.raster(pi)["pads"][k]["layers"]:
                            li = self._li(l)
                            if li is not None and (n, li, a, b) in o:
                                cells.append((li, a, b))
                    if cells:
                        terms.append(("fixed", sorted(set(cells)), (x, y)))
                else:
                    ext.append((x, y))
            if n not in self.own_nets:  # passing net: boundary crossings are terminals
                ext = []
                for (x, y) in set(self.passing.get(n, [])):
                    a = min(NX - 1, max(0, int(round((x - fx0) / s))))
                    b = min(NY - 1, max(0, int(round((y - fy0) / s))))
                    cells = [(li, a2, b2) for li in range(LL) for a2 in (a - 1, a, a + 1) for b2 in (b - 1, b, b + 1)
                             if (n, li, a2, b2) in o and (a2 in (0, NX - 1) or b2 in (0, NY - 1))]
                    if cells:
                        terms.append(("fixed", cells, (x, y)))
            if ext:
                # one exit terminal on the window border; cost = distance to nearest outside pin
                exits = {}
                for li in range(LL):
                    for j in range(NY):
                        for i in range(NX):
                            if (i in (0, NX - 1) or j in (0, NY - 1)) and (n, li, i, j) in o:
                                X_, Y_ = self.fxy(i, j)
                                exits[li, i, j] = int(min(abs(X_ - ex) + abs(Y_ - ey) for ex, ey in ext))
                if exits:
                    ex, ey = min(ext, key=lambda p: sum(abs(p[0] - t[2][0]) + abs(p[1] - t[2][1]) for t in terms))
                    terms.append(("exit", exits, (min(max(ex, fx0), fx1), min(max(ey, fy0), fy1))))
            if len(terms) < 2:
                continue
            # topology: minimum spanning tree over the terminals' current positions; each
            # tree edge is one 2-terminal connection (Numberlink degree encoding)
            P = np.array([t[2] for t in terms], float)
            inT = [0]
            conns = []
            while len(inT) < len(terms):
                best = None
                for a in inT:
                    for b in range(len(terms)):
                        if b in inT:
                            continue
                        d = abs(P[a] - P[b]).sum()
                        if best is None or d < best[0]:
                            best = (d, a, b)
                conns.append((best[1], best[2]))
                inT.append(best[2])
            miss = []
            for ci, (ta, tb) in enumerate(conns):
                mv = M.NewBoolVar("")
                miss.append(mv)
                obj.append(MISS * mv)
                X = {}

                def choose(t):
                    kind, data, _ = t
                    if kind == "pose":
                        lits = [((n, li, a, b), vs) for (li, a, b), vs in term_cov.get(data, {}).items()]
                    elif kind == "fixed":
                        lits = [((n,) + c, None) for c in data]
                    else:
                        lits = [((n,) + c, None) for c in data]
                    sv = []
                    for node, vs in lits:
                        if node not in o:
                            continue
                        x = M.NewBoolVar("")
                        if vs is not None:
                            M.Add(x <= sum(vs))
                        M.AddImplication(x, o[node])
                        X.setdefault(node, []).append(x)
                        sv.append(x)
                        if kind == "exit":
                            obj.append(data[node[1:]] * x)
                    M.Add(sum(sv) + mv == 1)
                choose(terms[ta])
                choose(terms[tb])
                inc = {}
                # the connection may only use cells near its terminals' candidate cells
                ij = np.array([nd[2:] for nd in X]) if X else np.zeros((1, 2), int)
                cm = self.cmargin if self.cmargin is not None else max(NX, NY)
                ci0, cj0 = ij.min(0) - cm
                ci1, cj1 = ij.max(0) + cm
                for li in range(LL):
                    for dirn, (di, dj) in enumerate(((1, 0), (0, 1))):
                        eok = self.edge_ok[n, li, dirn]
                        for j in range(NY - dj):
                            for i in range(NX - di):
                                a, b = (n, li, i, j), (n, li, i + di, j + dj)
                                if not eok[j, i] or a not in o or b not in o:
                                    continue
                                if not (ci0 <= i <= ci1 - di and cj0 <= j <= cj1 - dj):
                                    continue
                                u = M.NewBoolVar("")
                                M.AddImplication(u, net_edge(n, (n, li, i, j, dirn)))
                                M.AddImplication(u, o[a])
                                M.AddImplication(u, o[b])
                                inc.setdefault(a, []).append(u)
                                inc.setdefault(b, []).append(u)
                if LL > 1:
                    vok = self.via_ok[n]
                    for j in range(NY):
                        for i in range(NX):
                            a, b = (n, 0, i, j), (n, 1, i, j)
                            if not vok[j, i] or a not in o or b not in o:
                                continue
                            if not (ci0 <= i <= ci1 and cj0 <= j <= cj1):
                                continue
                            v = M.NewBoolVar("")
                            M.AddImplication(v, net_via(n, i, j))
                            inc.setdefault(a, []).append(v)
                            inc.setdefault(b, []).append(v)
                # degree: chosen endpoint 1, any other node 0 or 2 (deg + X = 2 z)
                for node in set(inc) | set(X):
                    z = M.NewBoolVar("")
                    M.Add(sum(inc.get(node, [])) + sum(X.get(node, [])) == 2 * z)
            nterm += len(conns)
            self.term_info[n] = len(conns)
            self.miss[n] = (miss, conns, [t[0] for t in terms])
        M.Minimize(sum(obj) + sum(self.phys_obj))
        # hint: current poses
        for pi, lst in self.pv.items():
            cur = self.poses0[pi]
            for v, ox, oy, ri, _, _ in lst:
                M.AddHint(v, int((ox, oy, ri) == tuple(cur)))
        self.stats.update(cells=NX * NY, nx=NX, ny=NY, poses=npose, nets=len(self.term_info),
                          terms=nterm, build_s=round(time.time() - t0, 2),
                          vars=len(M.Proto().variables), cons=len(M.Proto().constraints))
        return True

    # ------------------------------------------------------------ solve / decode
    def _solver(self, tlim, seed):
        S = cp_model.CpSolver()
        # deterministic time: independent of machine load (budgets are CPU seconds); wall
        # time only as a safety net
        S.parameters.max_deterministic_time = tlim
        S.parameters.max_time_in_seconds = 4 * tlim
        S.parameters.num_workers = self.workers
        # pure CP/SAT search: the LP relaxation of the routing part is weak and slow; with
        # it off a single worker finds far better routings in the same time
        S.parameters.linearization_level = self.lin
        S.parameters.random_seed = seed
        # presolve (probing especially) costs seconds on these models and buys little
        S.parameters.cp_model_presolve = self.presolve
        S.parameters.cp_model_probing_level = 0
        return S

    def solve(self, tlim=4.0, seed=0, phase1=0.35):
        """Phase 1: route the window with the parts at their current poses (assumptions),
        which yields a complete incumbent; phase 2: free poses, hinted with phase 1."""
        M = self.M
        cur = []
        for pi, lst in self.pv.items():
            hit = [v for v, ox, oy, ri, _, _ in lst if (ox, oy, ri) == tuple(self.poses0[pi])]
            cur += hit[:1]
        t0 = time.time()
        self.stats["cur_obj"] = None
        if len(cur) == len(self.pv) and phase1 > 0:
            M.AddAssumptions(cur)
            S = self._solver(tlim * phase1, seed)
            st = S.Solve(M)
            M.ClearAssumptions()
            if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                self.stats["cur_obj"] = S.ObjectiveValue()
                M.ClearHints()
                sol = S.ResponseProto().solution
                hp = M.Proto().solution_hint
                hp.vars.extend(range(len(sol)))
                hp.values.extend(sol)
            tlim = tlim * (1 - phase1)
        S = self._solver(tlim, seed)
        st = S.Solve(M)
        self.stats.update(solve_s=round(time.time() - t0, 2), status=S.StatusName(st))
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None
        self.stats["obj"] = S.ObjectiveValue()
        self.stats["bound"] = S.BestObjectiveBound()
        poses = {}
        for pi, lst in self.pv.items():
            for v, ox, oy, ri, _, _ in lst:
                if S.Value(v):
                    poses[pi] = (ox, oy, ri)
        self.solution_poses = poses
        # per-net CP-SAT corridor (fine cells of used edges / vias)
        corr = {}
        for (n, li, i, j, dirn), u in self.u.items():
            if S.Value(u):
                corr.setdefault(n, []).append((li, i, j, dirn))
        self.corridors = corr
        self.cp_moved = sum(1 for pi in poses if poses[pi] != tuple(self.poses0[pi]))
        return poses


# ---------------------------------------------------------------- engine decode
def _place_poses(world, poses):
    for pi, (ox, oy, ri) in poses.items():
        world.place(pi, ox, oy, ri)
    for pi in poses:
        if world.part_violation(pi) != (0, 0):
            return False
    return True


def _guided_route(world, kit, win, nets):
    """Route the window's nets one by one in hard mode with a history bias that makes
    window cells off the net's CP-SAT corridor expensive; leftovers go to PathFinder."""
    r = kit.r
    fx0, fy0, fx1, fy1 = win.box
    s = win.s
    for n in nets:
        r.rip(n)
    bias = 2.0
    order = sorted(nets, key=lambda n: -len(win.corridors.get(n, [])))
    for n in order:
        if n not in world.net_pins:
            continue
        mask = None
        if n in win.corridors:
            mask = np.ones((world.nl, fy1 - fy0 + 1, fx1 - fx0 + 1), bool)
            for li, i, j, dirn in win.corridors[n]:
                l = win.layers[li]
                x, y = i * s, j * s
                x2, y2 = (x + s, y) if dirn == 0 else (x, y + s)
                mask[l, max(0, min(y, y2) - 2):max(y, y2) + 3, max(0, min(x, x2) - 2):max(x, x2) + 3] = False
            world.hist[:, fy0:fy1 + 1, fx0:fx1 + 1] += bias * mask
        r.route_net(n, hard=True)
        if mask is not None:
            world.hist[:, fy0:fy1 + 1, fx0:fx1 + 1] -= bias * mask
    left = [n for n in nets if r.unrouted.get(n)] + kit.conflicted_nets()
    if left:
        kit.reroute(left, iters=6)


def heuristic_window(world, kit, parts, rng, k=5):
    """Control on the same window: repair-style greedy re-placement of `parts` (unplaced)
    with candidates scored by real routing (methods.repair's inner loop)."""
    for n in kit.part_nets(parts):
        kit.r.rip(n)
    order = list(parts)
    rng.shuffle(order)
    for q in order:
        cs = kit.candidates(q, k=k)
        if not cs:
            return False
        best = None
        for _, cx, cy, ri in cs:
            world.place(q, cx, cy, ri)
            aff = kit.part_nets([q]) | set(kit.conflicted_nets())
            sn = kit.snapshot(aff)
            kit.reroute(aff, iters=3)
            c = kit.total_cost()
            kit.restore(sn)
            world.unplace(q)
            if best is None or c < best[0]:
                best = (c, cx, cy, ri)
        world.place(q, *best[1:])
        kit.reroute(kit.part_nets([q]) | set(kit.conflicted_nets()), iters=3)
    return True


def _full_state(world, kit, mov):
    return dict((q, world.pose[q]) for q in mov if q in world.pose), kit.snapshot(list(world.net_pins))


def _restore_full(world, kit, mov, st):
    poses, snap = st
    for q in list(world.pose):
        if q in mov:
            world.unplace(q)
    kit.r.rip_all()
    for q, p in poses.items():
        world.place(q, *p)
    kit.restore(snap)


def _dump_rows(world, rows):
    """Window statistics next to the harness attempt (attempt-N/cpsat_windows.json)."""
    import json
    from pathlib import Path
    p = Path(world.data.get("path", ""))
    for d in p.parents:
        if d.name.startswith("attempt-"):
            try:
                (d / "cpsat_windows.json").write_text(json.dumps(rows, default=float))
            except OSError:
                pass
            return


# ---------------------------------------------------------------- the method
def cpsat(world, seed=0, budget=300, log=print, start="seq_phys", max_parts=3, side_mm=9.0,
          tlim=3.0, workers=1, guide=False, compare=False, pitch=None, radius=None, cmargin=2,
          phys=True, phys_w=2.0, cands=6, lattice=False, null=False, **kw):
    """Window LNS with exact CP-SAT place-and-route of each window.
    Score = Kit.total_cost() + phys_w * physics place terms (if phys). Pose candidates per
    part: the coarse lattice (lattice), the current pose and the top `cands` HPWL candidates
    of Kit.candidates on the fine grid. compare=True also runs the repair-style heuristic
    on every window from the same state and keeps the better (diagnostic mode)."""
    rng = random.Random(seed)
    clock = Clock(budget)
    if start == "seq_phys":
        import methods_phys
        r = methods_phys.seq_phys(world, seed=seed, budget=budget * 0.25, log=log, phys_w=phys_w, **kw)
    else:
        starter = {"seq": methods.seq, "grow": methods.grow}[start]
        r = starter(world, seed=seed, budget=budget * 0.25, log=log, **kw)
    kit = Kit(world, r)
    ph = None
    if phys and world.data.get("path"):
        try:
            from physics import Phys
            ph = getattr(world, "phys", None) or Phys(world, world.data["path"])
        except Exception as e:  # kae not importable: route cost only
            log(f"  physics unavailable: {e!r}")
    mov = [q for q in kit.movable() if q in world.pose]

    def score():
        c = kit.total_cost()
        if ph is not None:
            ph.sync()
            c += phys_w * ph.total()
        return c

    cur = score()
    log(f"cpsat start score={cur:.1f} cost={kit.total_cost():.1f} {r.stats()}"
        + (f" phys={ph.total():.2f}" if ph else ""))
    tries = acc = acc_h = both = 0
    tabu = {}
    rows = []
    while clock.left() > tlim + 2 and mov:
        net, parts, box = pick_window(world, kit, rng, max_parts=max_parts, side_mm=side_mm)
        tries += 1
        key = (net, tuple(sorted(parts)))
        if box is None or tabu.get(key, -1) >= tries:
            continue
        state0 = _full_state(world, kit, mov)
        if ph is not None:
            ph.sync()
        win = Window(world, kit, parts, box, pitch=pitch, workers=workers, radius=radius, cmargin=cmargin)
        win.rip()
        extra = {}
        if cands:
            for q in parts:
                extra[q] = [(cx, cy, ri) for _, cx, cy, ri in kit.candidates(q, k=cands)]
        if null:  # control: same windows and rip-up, parts stay, nets re-routed
            ok, poses = True, {q: tuple(win.poses0[q]) for q in parts}
            win.cp_moved = 0
        else:
            ok = win.build(extra=extra, lattice=lattice, phys=ph, phys_w=phys_w)
            poses = win.solve(tlim=tlim, seed=tries) if ok else None
        row = dict(net=world.net_names[net], parts=len(parts), **win.stats)
        new = None
        if poses is not None:
            if _place_poses(world, poses):
                if guide:
                    _guided_route(world, kit, win, win.rip_nets)
                else:
                    kit.reroute(win.rip_nets, iters=6)
                new = score()
            else:
                row["decode"] = "illegal"
        row.update(moved=getattr(win, "cp_moved", None), before=round(cur, 1),
                   after=None if new is None else round(new, 1))
        cp_gain = (cur - new) if new is not None else None
        if compare:
            st_cp = _full_state(world, kit, mov) if new is not None else None
            _restore_full(world, kit, mov, state0)
            for q in parts:
                world.unplace(q)
            th = time.process_time()
            okh = heuristic_window(world, kit, parts, rng)
            hn = None
            if okh:
                kit.reroute(win.rip_nets, iters=6)
                hn = score()
            row["heur_after"] = None if hn is None else round(hn, 1)
            row["heur_cpu"] = round(time.process_time() - th, 2)
            h_gain = (cur - hn) if hn is not None else None
            if cp_gain is not None and cp_gain > 1e-6 and (h_gain is None or cp_gain >= h_gain):
                _restore_full(world, kit, mov, st_cp)
                cur = new
                acc += 1
            elif h_gain is not None and h_gain > 1e-6:
                cur = hn
                acc_h += 1
            else:
                _restore_full(world, kit, mov, state0)
                tabu[key] = tries + 5
            if cp_gain is not None and h_gain is not None and cp_gain > 1e-6 and h_gain > 1e-6:
                both += 1
        elif new is not None and new < cur - 1e-6:
            cur = new
            acc += 1
        else:
            _restore_full(world, kit, mov, state0)
            tabu[key] = tries + 5
        rows.append(row)
        log(f"  win {tries}: {row}")
    r.legalize(list(world.net_pins))
    world.cpsat_rows = rows
    _dump_rows(world, rows)
    if ph is not None:
        ph.sync()
        world.phys = ph
    log(f"cpsat {r.stats()} cost={kit.total_cost():.1f} score={score():.1f} tries={tries} acc={acc} "
        f"acc_heur={acc_h} both={both}" + (f" phys={ph.total():.2f}" if ph else ""))
    return r


def cpsat_guided(world, seed=0, budget=300, log=print, **kw):
    kw.setdefault("guide", True)
    return cpsat(world, seed=seed, budget=budget, log=log, **kw)


def cpsat_null(world, seed=0, budget=300, log=print, **kw):
    """Control: the same window LNS loop with the CP-SAT step removed (rip + re-route)."""
    kw.setdefault("null", True)
    return cpsat(world, seed=seed, budget=budget, log=log, **kw)
