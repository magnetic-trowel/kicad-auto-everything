# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The raster of a board's copper, the conductor network on it, and its terminals.

Every copper layer is rasterized on one square grid (pitch p, origin x0, y0, in mm), each cell
labelled with its net. Neighbouring cells of the same net on a layer are joined by a bar (x or
y directed, p long, p wide, the layer's thickness), split through the thickness into `nsub`
parallel filaments that share the bar's end nodes, so current can crowd toward a facing plane.
Vias are vertical barrels joining their own net's cells on each layer they pass. Terminals
(a pad, a via landing) are equipotential: their cells are contracted to one node. Lumped
branches (a part between two terminals: R, L, C in series) carry no mutual inductance.

The square grid is a finite-volume discretization of the sheet current: a square network is
isotropic in the continuum limit, so diagonal copper is represented, with an O(p) staircase
error at its edges. Conductors narrower than about 3 p are under-resolved; `Mesh.check` says so.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

MM = 1e-3
SIGMA_CU = 5.8e7          # S/m, annealed copper at 20 C
PLATING = 25e-6           # m, via barrel wall


@dataclass
class Layer:
    name: str
    z: float              # bottom of the copper, mm (B.Cu at 0 counts upward)
    t: float              # thickness, mm
    nsub: int = 2         # filaments through the thickness

    def subs(self):
        """[(z_bottom, thickness)] in m: slices graded toward both faces (Chebyshev spacing), where
        high-frequency current crowds."""
        n = self.nsub
        e = (1 - np.cos(np.pi * np.arange(n + 1) / n)) / 2
        return [((self.z + self.t * e[k]) * MM, self.t * (e[k + 1] - e[k]) * MM) for k in range(n)]


@dataclass
class Via:
    x: float
    y: float
    layers: list          # layer indices it joins, top to bottom
    net: int
    drill: float          # mm
    plating: float = PLATING


@dataclass
class Lumped:
    a: str
    b: str
    R: float = 0.0
    L: float = 0.0
    C: float | None = None
    name: str = ""
    zf: object = None        # callable w -> impedance (a circuit model), replacing R, L, C

    @property
    def short(self):
        return self.zf is None and self.R == 0 and self.L == 0 and not self.C

    def z(self, w):
        if self.zf is not None:
            return complex(self.zf(w)) if w > 0 else complex(self.zf(1e3))
        z = self.R + 1j * w * self.L
        if self.C:
            z = z + (1 / (1j * w * self.C) if w > 0 else 1e12)
        return z


@dataclass
class Mesh:
    x0: float
    y0: float
    nx: int
    ny: int
    pitch: float
    layers: list
    sigma: float = SIGMA_CU
    nets: list = field(default_factory=list)
    vias: list = field(default_factory=list)
    lumped: list = field(default_factory=list)
    terminals: dict = field(default_factory=dict)      # name -> list of (layer, j, i)
    ports: list = field(default_factory=list)          # (name, plus terminal, minus terminal)

    def __post_init__(self):
        self.lab = np.full((len(self.layers), self.ny, self.nx), -1, np.int32)
        self.thin = {}          # (layer, orientation, j, i) -> (width mm, length scale): sub-cell tracks
        self.cov = np.zeros(self.lab.shape)    # copper coverage of each cell (0..1), for edge cells

    @classmethod
    def over(cls, x0, y0, x1, y1, pitch, layers, **kw):
        nx = int(np.ceil((x1 - x0) / pitch - 1e-9))
        ny = int(np.ceil((y1 - y0) / pitch - 1e-9))
        return cls(x0, y0, nx, ny, pitch, layers, **kw)

    # ------------------------------------------------------------------ painting
    def net_id(self, name):
        if name not in self.nets:
            self.nets.append(name)
        return self.nets.index(name)

    def centres(self):
        xs = self.x0 + (np.arange(self.nx) + 0.5) * self.pitch
        ys = self.y0 + (np.arange(self.ny) + 0.5) * self.pitch
        return np.meshgrid(xs, ys)

    def cells_in(self, geom):
        """Boolean (ny, nx): cell centres inside a shapely geometry (mm)."""
        import shapely
        X, Y = self.centres()
        shapely.prepare(geom)
        return shapely.contains_xy(geom, X, Y)

    SUB = 4                # sub-samples per cell side for the coverage of edge cells
    MIN_COV = 0.25         # a cell less covered than this stays empty

    def coverage(self, geom=None, rect=None):
        """(ny, nx) fraction of each cell covered by the copper: exact 0/1 away from its edge, sampled
        on SUB x SUB points per cell along it."""
        from scipy import ndimage
        X, Y = self.centres()
        if rect is not None:
            x0, y0, x1, y1 = rect
            p = self.pitch
            fx = np.clip((np.minimum(X + p / 2, x1) - np.maximum(X - p / 2, x0)) / p, 0, 1)
            fy = np.clip((np.minimum(Y + p / 2, y1) - np.maximum(Y - p / 2, y0)) / p, 0, 1)
            return fx * fy
        import shapely
        shapely.prepare(geom)
        inside = shapely.contains_xy(geom, X, Y)
        cov = inside.astype(float)
        edge = ndimage.binary_dilation(inside) & ~ndimage.binary_erosion(inside)
        edge |= ndimage.binary_dilation(edge)
        jj, ii = np.nonzero(edge)
        if len(jj):
            n = self.SUB
            off = (np.arange(n) + 0.5) / n - 0.5
            ox, oy = np.meshgrid(off, off)
            px = X[jj, ii][:, None] + ox.ravel()[None] * self.pitch
            py = Y[jj, ii][:, None] + oy.ravel()[None] * self.pitch
            cov[jj, ii] = shapely.contains_xy(geom, px, py).mean(axis=1)
        return cov

    def paint(self, layer, net, geom=None, mask=None, cov=None):
        """Label the cells of `geom` (shapely, mm) or `mask` on layer index `layer` with `net`, keeping
        each cell's copper coverage (edge cells: partial). Later paint wins where it covers a cell at
        least as much. Partly covered cells carry their true width (Network)."""
        k = self.net_id(net)
        if mask is not None and cov is None:
            cov = mask.astype(float)
        elif cov is None:
            cov = self.coverage(geom)
        m = cov >= self.MIN_COV
        own = self.lab[layer] == k
        take = m & (own | (cov >= self.cov[layer] * 0.999) | (self.lab[layer] < 0))
        self.cov[layer][take] = np.where(own[take], np.maximum(self.cov[layer][take], cov[take]), cov[take])
        self.lab[layer][take] = k
        return int(take.sum())

    def paint_line(self, layer, net, pts, width):
        """A track narrower than a few cells: a 4-connected chain of cells along its centre line, so it
        conducts at any pitch. Its bars carry the track's true width and length (Network applies them to
        R and to the self inductance), unless the cells were copper of the net already (a pour)."""
        k = self.net_id(net)
        lab = self.lab[layer]
        p = self.pitch
        for (xa, ya), (xb, yb) in zip(pts[:-1], pts[1:]):
            seg = float(np.hypot(xb - xa, yb - ya))
            n = max(2, int(np.ceil(seg / (p / 4))) + 1)
            cells = []
            for t in np.linspace(0, 1, n):
                c = self.cell(xa + (xb - xa) * t, ya + (yb - ya) * t)
                if not cells or c != cells[-1]:
                    if cells and c[0] != cells[-1][0] and c[1] != cells[-1][1]:
                        # a diagonal step: go through the neighbour the line passes nearer
                        (j0, i0), (j1, i1) = cells[-1], c
                        cand = [(j0, i1), (j1, i0)]
                        cx = lambda q: (self.x0 + (q[1] + 0.5) * p, self.y0 + (q[0] + 0.5) * p)
                        dx, dy = xb - xa, yb - ya
                        dist = lambda q: abs((cx(q)[0] - xa) * dy - (cx(q)[1] - ya) * dx)
                        cells.append(min(cand, key=dist))
                    cells.append(c)
            cells = [(j, i) for j, i in cells if 0 <= j < self.ny and 0 <= i < self.nx]
            if len(cells) < 2:
                for j, i in cells:
                    lab[j, i] = k
                continue
            scale = seg / ((len(cells) - 1) * p)
            pre = {c: lab[c] == k for c in cells}
            for (j0, i0), (j1, i1) in zip(cells[:-1], cells[1:]):
                if pre[(j0, i0)] and pre[(j1, i1)] and self.cov[layer][j0, i0] >= 0.999 and self.cov[layer][j1, i1] >= 0.999:
                    continue
                o = "x" if j0 == j1 else "y"
                key = (layer, o, min(j0, j1), min(i0, i1))
                if key not in self.thin or self.thin[key][0] < width:
                    self.thin[key] = (width, scale)
            for j, i in cells:
                lab[j, i] = k
                self.cov[layer][j, i] = 1.0

    def rect(self, layer, net, x0, y0, x1, y1):
        return self.paint(layer, net, cov=self.coverage(rect=(x0, y0, x1, y1)))

    def via(self, x, y, layers, net, drill=0.3, plating=PLATING):
        self.vias.append(Via(x, y, list(layers), self.net_id(net), drill, plating))

    def cell(self, x, y):
        return (int(np.floor((y - self.y0) / self.pitch)), int(np.floor((x - self.x0) / self.pitch)))

    def terminal(self, name, layer, geom=None, net=None, xy=None, mask=None):
        """An equipotential terminal: the cells of `net` (any if None) under geom (or the one cell at
        xy, or mask) on `layer` (index, or a list of indices for a through-hole pad)."""
        cells = []
        for l in (layer if isinstance(layer, (list, tuple)) else [layer]):
            if xy is not None:
                j, i = self.cell(*xy)
                m = np.zeros((self.ny, self.nx), bool)
                if 0 <= j < self.ny and 0 <= i < self.nx:
                    m[j, i] = True
            else:
                m = self.cells_in(geom) if mask is None else mask
            lab = self.lab[l]
            m = m & ((lab >= 0) if net is None else (lab == self.net_id(net)))
            cells += [(l, int(j), int(i)) for j, i in zip(*np.nonzero(m))]
        if not cells:
            raise ValueError(f"terminal {name}: no copper under it")
        self.terminals.setdefault(name, []).extend(cells)
        return name

    def part(self, a, b, R=0.0, L=0.0, C=None, name="", zf=None):
        """A lumped part between terminals a and b; R = L = 0 with no C (and no zf) is an ideal short."""
        self.lumped.append(Lumped(a, b, R, L, C, name, zf))

    def port(self, name, plus, minus):
        self.ports.append((name, plus, minus))

    def check(self):
        """Resolution warnings: copper features narrower than 3 cells on any layer."""
        from scipy import ndimage
        out = []
        for l, lay in enumerate(self.layers):
            occ = self.lab[l] >= 0
            if not occ.any():
                continue
            thin = occ & ~ndimage.binary_opening(occ, structure=np.ones((3, 3)))
            frac = thin.sum() / occ.sum()
            if frac > 0.02:
                out.append(f"{lay.name}: {frac:.0%} of copper cells are in features narrower than 3 cells "
                           f"({3 * self.pitch:g} mm); refine the pitch for them")
        return out


def _thin_dL(p, w, lscale, t):
    """Self partial inductance of a bar p*lscale long and w wide minus that of the p x p bar the raster
    holds (H); 0 where w is nan (an ordinary bar)."""
    from .kernels import bar_mutual
    out = np.zeros(len(w))
    k = np.isfinite(w)
    if k.any():
        ww, ls = w[k], lscale[k]
        Lt = bar_mutual((0, p * ls, 0, ww, 0, t), (0, p * ls, 0, ww, 0, t))
        Lr = bar_mutual((0, p, 0, p, 0, t), (0, p, 0, p, 0, t))
        out[k] = Lt - Lr
    return out


class Network:
    """The branch network of a mesh: nodes, filaments, via segments, lumped parts."""

    def __init__(self, m: Mesh):
        self.m = m
        L, ny, nx = m.lab.shape
        p = m.pitch * MM
        # cell nodes, contracted by terminals and via landings
        occ = m.lab >= 0
        cid = -np.ones(m.lab.shape, np.int64)
        cid[occ] = np.arange(int(occ.sum()))
        n = int(occ.sum())
        parent = np.arange(n)

        def find(a):
            r = a
            while parent[r] != r:
                r = parent[r]
            while parent[a] != r:
                parent[a], a = r, parent[a]
            return r

        def union(cells):
            ids = [cid[c] for c in cells]
            r = find(ids[0])
            for q in ids[1:]:
                parent[find(q)] = r
            return r
        for name, cells in m.terminals.items():
            union(cells)
        shorts = [q for q in m.lumped if q.short]
        for q in shorts:
            union([m.terminals[q.a][0], m.terminals[q.b][0]])
        # via landings: the via's own-net cells within the barrel (radius + p/2) on each layer
        X, Y = m.centres()
        self.via_nodes = []
        for v in m.vias:
            rr = v.drill / 2 + m.pitch / 2
            disk = (X - v.x) ** 2 + (Y - v.y) ** 2 <= rr * rr
            if not disk.any():
                j, i = m.cell(v.x, v.y)
                disk = np.zeros_like(disk)
                if 0 <= j < ny and 0 <= i < nx:
                    disk[j, i] = True
            land = []
            for l in v.layers:
                cs = [(l, int(j), int(i)) for j, i in zip(*np.nonzero(disk & (m.lab[l] == v.net)))]
                if cs:
                    union(cs)
                    land.append((l, cs[0]))
            self.via_nodes.append(land)
        roots = np.array([find(a) for a in range(n)], np.int64)
        uniq, node_of = np.unique(roots, return_inverse=True)
        self.n_nodes = len(uniq)
        node = -np.ones(m.lab.shape, np.int64)
        node[occ] = node_of
        self.node = node
        self.term_node = {name: int(node[cells[0]]) for name, cells in m.terminals.items()}

        # sublayers
        subs, sub_of = [], []
        for l, lay in enumerate(m.layers):
            sub_of.append(list(range(len(subs), len(subs) + lay.nsub)))
            subs += lay.subs()
        self.subs = subs
        self.sub_of = sub_of

        # bars -> filaments, per orientation: arrays (s, j, i, a, b, R)
        self.fil = {}
        for o, (dj, di) in (("x", (0, 1)), ("y", (1, 0))):
            S, J, I, A, B, R, LC = [], [], [], [], [], [], []
            for l, lay in enumerate(m.layers):
                lab = m.lab[l]
                a = lab[: ny - dj, : nx - di]
                b = lab[dj:, di:]
                same = (a >= 0) & (a == b)
                jj, ii = np.nonzero(same)
                na = node[l, jj, ii]
                nb = node[l, jj + dj, ii + di]
                keep = na != nb                       # inside one terminal: shorted
                jj, ii, na, nb = jj[keep], ii[keep], na[keep], nb[keep]
                wfac = np.ones(len(jj))
                lscale = np.ones(len(jj))
                thin_w = np.full(len(jj), np.nan)
                # an edge bar of partly covered cells: its width is the smaller coverage times p
                cv = np.minimum(m.cov[l, jj, ii], m.cov[l, jj + dj, ii + di])
                part = (cv > 0) & (cv < 0.999)
                thin_w[part] = cv[part] * m.pitch
                wfac[part] = 1.0 / cv[part]
                if m.thin:
                    for q, (j_, i_) in enumerate(zip(jj, ii)):
                        th = m.thin.get((l, o, int(j_), int(i_)))
                        if th:
                            thin_w[q], lscale[q] = th
                            wfac[q] = m.pitch / th[0]
                for s in sub_of[l]:
                    zb, ts = subs[s]
                    S.append(np.full(len(jj), s))
                    J.append(jj), I.append(ii), A.append(na), B.append(nb)
                    R.append(wfac * lscale / (m.sigma * ts))     # p / (sigma w t), times the path's length scale
                    LC.append(_thin_dL(m.pitch * MM, thin_w * MM, lscale, ts))
            cat = (lambda xs, dt: np.concatenate(xs).astype(dt) if xs else np.zeros(0, dt))
            self.fil[o] = dict(s=cat(S, np.int64), j=cat(J, np.int64), i=cat(I, np.int64),
                               a=cat(A, np.int64), b=cat(B, np.int64), R=cat(R, float), Lc=cat(LC, float))
        # via segments between consecutive landings
        vs = []
        for v, land in zip(m.vias, self.via_nodes):
            for (la, ca), (lb, cb) in zip(land[:-1], land[1:]):
                za = (m.layers[la].z + m.layers[la].t / 2) * MM
                zb = (m.layers[lb].z + m.layers[lb].t / 2) * MM
                na, nb = int(node[ca]), int(node[cb])
                if na == nb:
                    continue
                h = abs(za - zb)
                r = v.drill / 2 * MM
                R = h / (m.sigma * np.pi * 2 * r * v.plating)
                vs.append((na, nb, v.x * MM, v.y * MM, min(za, zb), max(za, zb), r, R))
        self.vseg = np.array(vs, float).reshape(-1, 8)
        self.lump = [(self.term_node[q.a], self.term_node[q.b], q) for q in m.lumped
                     if not q.short and self.term_node[q.a] != self.term_node[q.b]]

        nf = {o: len(f["a"]) for o, f in self.fil.items()}
        self.off = {"x": 0, "y": nf["x"], "v": nf["x"] + nf["y"], "l": nf["x"] + nf["y"] + len(self.vseg)}
        self.n_br = self.off["l"] + len(self.lump)
        a = np.concatenate([self.fil["x"]["a"], self.fil["y"]["a"], self.vseg[:, 0].astype(np.int64),
                            np.array([q[0] for q in self.lump], np.int64)])
        b = np.concatenate([self.fil["x"]["b"], self.fil["y"]["b"], self.vseg[:, 1].astype(np.int64),
                            np.array([q[1] for q in self.lump], np.int64)])
        self.br_a, self.br_b = a, b
        self.R = np.concatenate([self.fil["x"]["R"], self.fil["y"]["R"], self.vseg[:, 7] if len(self.vseg) else [],
                                 np.zeros(len(self.lump))])
        # self-inductance correction of sub-cell tracks (the FFT operator sees p-wide bars)
        self.Lc = np.concatenate([self.fil["x"]["Lc"], self.fil["y"]["Lc"], np.zeros(len(self.vseg) + len(self.lump))])
        self._components()

    def _components(self):
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        n = self.n_nodes
        g = coo_matrix((np.ones(len(self.br_a)), (self.br_a, self.br_b)), shape=(n, n))
        self.ncomp, self.comp = connected_components(g, directed=False)

    def stats(self):
        return dict(nodes=self.n_nodes, x_fil=len(self.fil["x"]["a"]), y_fil=len(self.fil["y"]["a"]),
                    via_segs=len(self.vseg), lumped=len(self.lump), sublayers=len(self.subs),
                    components=int(self.ncomp))
