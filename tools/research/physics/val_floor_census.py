# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pilot floor census: how far real power copper sits above its variational floors (validation program).

Used by docs/topics/physics/validation-program.md (computational track, pilot). Lens VP showed that
DC loss in copper of fixed area has certified floors: Beckmann's closed form
    R >= W1^2 / (I^2 sum_l A_l / R_s,l)          (W1 = sum_k I_k d_k, earth-mover distance)
and a convex relaxation (SIMP with p = 1) whose Lagrangian dual certifies a floor for every copper
layout of the same area inside a domain. It recommended reporting the avoidable loss (R - floor)/R
for every pour. This script does that on real KiCad boards (saved zone fills required).

Per net (multi-layer: fills, tracks and pads of the net on every layer, joined by its vias and
plated pads), with a stated current pattern (one source footprint at 0 V, sink footprints drawing
given DC currents; capacitors carry no DC):
  R_act    loss-equivalent resistance P/I^2 of the copper as drawn: cell-centred finite volumes,
           0.1 mm cells, each footprint's pads one equipotential node, via barrels as resistors;
  R_B      Beckmann floor at the net's area (any shape, any place; via resistance ignored);
  floors   convex floors at equal area inside three domains of growing freedom:
           shape      the net's zone outlines and copper minus every other net's copper (zone
                      clearance) and holes: only the net's own pour shape may change (thermal
                      reliefs, islands, necks);
           routing    other nets' tracks and vias removed (what co-routing could buy);
           partition  the whole layer within the board edge, other nets' pads, tracks and vias kept,
                      other nets' zone fills negotiable (what re-partitioning the planes could buy).
Floors use bilinear (Q4) elements on 0.15 mm cells (0.25 mm for domains over 400 mm^2) with the net's vias as fixed links, solved by
optimality-criteria updates at the actual layout's copper area on that grid; the reported floor is
the best Lagrangian-dual bound (fractional knapsack), certified for every layout on that grid. The
actual copper is re-evaluated on the same grid (R_q4) so that it is a feasible point, and the
avoidable fraction is 1 - floor / R_q4 (Beckmann's: 1 - R_B / R_act). The partition floor ignores what
the other nets' planes lose, so it bounds a multi-net trade rather than prescribing one.

Nets and currents are a pilot assignment by inspection of the footprints (PILOT below), not a
circuit simulation; the census at scale needs the schematic's DC operating point.

Run:  python -I tools/research/physics/val_floor_census.py DIR      (DIR/<board>/board.kicad_pcb)
      Boards are third-party data: never copy them into the repo. ~5-10 min for the pilot set.
"""
import math
import os
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import Point, Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pc_refplane as pr  # noqa: E402  (round-1 board parser, reused)

RHO = 1.72e-8
EPS = 1e-6
KE = np.array([[4, -1, -2, -1], [-1, 4, -1, -2], [-2, -1, 4, -1], [-1, -2, -1, 4]], float) / 6.0

# board -> [(net, source footprint, {sink footprint: amps}, note)]; currents are assumptions [I]
PILOT = {
    "oasis": [
        ("+18V", "J6", {"fan1": 0.15, "fan2": 0.15, "L1": 0.40, "PS1": 0.50, "U6": 0.10}, "18 V input to fans, mister, LED driver, buck"),
        ("+3.3V", "L3", {"U2": 0.30, "i2c_header1": 0.02}, "buck output to ESP32 module"),
        ("Net-(Q1-D)", "Q1", {"fan1": 0.15, "fan2": 0.15}, "fan low-side switch"),
        ("Net-(Q3-D)", "Q3", {"L1": 0.40}, "mister switch node"),
        ("Net-(U6-SW)", "U6", {"L3": 0.30}, "buck switch node"),
        ("/led_N", "PS1", {"lights1": 0.70}, "LED string return"),
        ("/led_P", "PS1", {"lights1": 0.70}, "LED string feed"),
    ],
    "aftonsparv": [
        ("+24V", "J1", {"J2": 1.0}, "24 V pass-through"),
        ("+3.3V", "L1", {"U1": 0.30, "J4": 0.02}, "buck output to ESP32 module"),
        ("Net-(U2-LX)", "U2", {"L1": 0.30}, "buck switch node"),
    ],
    "pi5pcie": [
        ("+12V", "J1", {"J3": 2.0}, "12 V jack to PCIe slot"),
        ("+3V3", "U1", {"J3": 1.0}, "3.3 V module to PCIe slot"),
    ],
    "bldcpower": [
        ("VIN", "J3", {"U3": 1.0, "U8": 0.05}, "supply to motor driver and LDO"),
        ("3.3V", "U2", {"U5": 0.05, "J1": 0.05, "J5": 0.05, "U3": 0.005, "U1": 0.002, "U4": 0.002, "U6": 0.002},
         "LDO to logic"),
    ],
}


# ----------------------------------------------------------------------------------------------- parsing
class Census:
    def __init__(self, path):
        self.b = pr.Board(path)
        tree = pr.parse(open(path, encoding="utf-8", errors="replace").read())
        self.zones = []
        for z in pr.kids(tree, "zone"):
            if pr.first(z, "keepout"):
                continue
            net = self.b._net(z) or (pr.first(z, "net_name") or [None, ""])[1]
            ly = pr.first(z, "layer")
            layers = [ly[1]] if ly else [n for n in (pr.first(z, "layers") or [])[1:] if str(n).endswith(".Cu")]
            poly = pr.first(z, "polygon")
            pts = [pr.xy(p) for p in pr.first(poly, "pts") if isinstance(p, list) and p[0] == "xy"] if poly else []
            cp = pr.first(z, "connect_pads")
            clr = 0.2
            if cp:
                c = pr.first(cp, "clearance")
                clr = float(c[1]) if c else clr
            if len(pts) >= 3:
                self.zones.append(dict(net=net, layers=layers, poly=Polygon(pts).buffer(0), clearance=clr))
        if self.b.outline is not None:
            self.edge = self.b.outline.buffer(-0.3)
        else:   # no closed Edge.Cuts outline parsed: fall back to the envelope of all copper fills and pads
            env = unary_union(list(self.b.fills.values()) + [p["shape"] for p in self.b.pads]).envelope
            self.edge = env.buffer(-0.3)

    def net_layers(self, net):
        ls = set(k[0] for k in self.b.fills if k[1] == net)
        ls |= set(s["layer"] for s in self.b.segments if s["net"] == net)
        ls |= set(z for z in self.b.cu for p in self.b.pads if p["net"] == net and z in p["layers"]
                  if not p["through"])
        return [l for l in self.b.cu if l in ls]

    def copper(self, net, layer):
        parts = []
        if (layer, net) in self.b.fills:
            parts.append(self.b.fills[(layer, net)])
        for s in self.b.segments:
            if s["net"] == net and s["layer"] == layer:
                parts.append(shapely.LineString(s["pts"]).buffer(s["w"] / 2))
        for p in self.b.pads:
            if p["net"] == net and layer in p["layers"]:
                parts.append(p["shape"])
        for v in self.b.vias:
            if v["net"] == net and layer in v["layers"]:
                parts.append(Point(v["x"], v["y"]).buffer(v["size"] / 2))
        return unary_union(parts) if parts else Polygon()

    def others(self, net, layer, with_routing, with_fills=True):
        parts = []
        for p in self.b.pads:
            if p["net"] != net and layer in p["layers"]:
                parts.append(p["shape"])
        if with_fills:
            for (l, n), g in self.b.fills.items():
                if l == layer and n != net:
                    parts.append(g)
        if with_routing:
            for s in self.b.segments:
                if s["net"] != net and s["layer"] == layer:
                    parts.append(shapely.LineString(s["pts"]).buffer(s["w"] / 2))
            for v in self.b.vias:
                if v["net"] != net and layer in v["layers"]:
                    parts.append(Point(v["x"], v["y"]).buffer(v["size"] / 2))
        return unary_union(parts) if parts else Polygon()

    def domain(self, net, layer, mode):
        """mode 'shape': own zone outlines, all other copper fixed; 'routing': other nets' tracks and vias
        removed; 'partition': the whole layer, other nets' pads, tracks and vias fixed, their zone fills negotiable."""
        clr = max([z["clearance"] for z in self.zones if z["net"] == net and layer in z["layers"]] or [0.2])
        if mode == "partition" and self.edge is not None:
            base = self.edge.union(self.copper(net, layer))
            return base.difference(self.others(net, layer, True, with_fills=False).buffer(clr))
        outl = [z["poly"] for z in self.zones if z["net"] == net and layer in z["layers"]]
        base = unary_union(outl + [self.copper(net, layer)])
        if self.edge is not None:
            base = base.intersection(self.edge.union(self.copper(net, layer)))
        return base.difference(self.others(net, layer, mode == "shape").buffer(clr))


# ----------------------------------------------------------------------------------------------- grids
def raster(geom, xc, yc):
    if geom.is_empty:
        return np.zeros(xc.shape, bool)
    return shapely.contains_xy(geom, xc, yc)


def footprint_pads(b, net, ref):
    return [p for p in b.pads if p["net"] == net and p["ref"] == ref]


def via_link_g(v, za, zb):
    drill = max(0.2, 0.55 * v["size"]) * 1e-3
    area = math.pi * ((drill / 2 + 20e-6) ** 2 - (drill / 2) ** 2)
    return area / (RHO * max(abs(zb - za) * 1e-3, 1e-5))


def solve_actual(cs, net, src, sinks, layers, h=0.1):
    """Cell-centred FV DC solve of the net's copper. Returns R (ohm), node potentials, areas per layer."""
    b = cs.b
    geoms = {l: cs.copper(net, l) for l in layers}
    allg = unary_union(list(geoms.values()))
    x0, y0, x1, y1 = allg.bounds
    nx, ny = int(math.ceil((x1 - x0) / h)) + 2, int(math.ceil((y1 - y0) / h)) + 2
    xs = x0 - h / 2 + (np.arange(nx) + 0.5) * h
    ys = y0 - h / 2 + (np.arange(ny) + 0.5) * h
    XC, YC = np.meshgrid(xs, ys)
    node = -np.ones((len(layers), ny, nx), int)
    cnt = 0
    masks = {}
    for li, l in enumerate(layers):
        m = raster(geoms[l], XC, YC)
        masks[l] = m
        k = int(m.sum())
        node[li][m] = np.arange(cnt, cnt + k)
        cnt += k
    # terminal merges
    term = {}
    rep = np.arange(cnt)
    terms = [src] + list(sinks)
    for t in terms:
        ids = []
        for p in footprint_pads(b, net, t):
            for li, l in enumerate(layers):
                if l in p["layers"]:
                    mm = raster(p["shape"], XC, YC) & masks[l]
                    ids.extend(node[li][mm].tolist())
        if not ids:
            return None
        term[t] = ids
    nid = cnt
    for t in terms:
        rep[term[t]] = nid
        nid += 1
    rows, cols, vals = [], [], []
    for li, l in enumerate(layers):
        g = 1.0 / (RHO / (b.tcu.get(l, 0.035) * 1e-3))
        nd = node[li]
        for a_, b_ in ((nd[:, :-1], nd[:, 1:]), (nd[:-1, :], nd[1:, :])):
            ok = (a_ >= 0) & (b_ >= 0)
            rows.append(a_[ok]); cols.append(b_[ok]); vals.append(np.full(ok.sum(), g))
    # vias and plated pads of the net join consecutive layers
    links = [(v["x"], v["y"], v) for v in b.vias if v["net"] == net]
    links += [(p["x"], p["y"], dict(size=1.5 * min(p["shape"].bounds[2] - p["shape"].bounds[0],
                                                    p["shape"].bounds[3] - p["shape"].bounds[1]),
                                       layers=list(p["layers"])))
              for p in b.pads if p["net"] == net and p["through"]]
    for x, y, v in links:
        i, j = int((x - xs[0]) / h + 0.5), int((y - ys[0]) / h + 0.5)
        if not (0 <= i < nx and 0 <= j < ny):
            continue
        span = [li for li, l in enumerate(layers) if l in v["layers"] and node[li][j, i] >= 0]
        for a_, b_ in zip(span[:-1], span[1:]):
            g = via_link_g(v, b.z[layers[a_]], b.z[layers[b_]])
            rows.append(np.array([node[a_][j, i]])); cols.append(np.array([node[b_][j, i]])); vals.append(np.array([g]))
    r = rep[np.concatenate(rows)]
    c = rep[np.concatenate(cols)]
    v = np.concatenate(vals)
    keep = r != c
    r, c, v = r[keep], c[keep], v[keep]
    n = nid
    G = sp.coo_matrix((np.concatenate([v, v, -v, -v]), (np.concatenate([r, c, r, c]), np.concatenate([r, c, c, r]))),
                      shape=(n, n)).tocsc()
    src_id = cnt
    sink_ids = {t: cnt + 1 + k for k, t in enumerate(sinks)}
    bvec = np.zeros(n)
    for t, i in sinks.items():
        bvec[sink_ids[t]] = -i
    free = np.setdiff1d(np.arange(n), [src_id])
    # isolated pieces (no path to the source) would make G singular: keep the component of the source
    ncomp, lab = sp.csgraph.connected_components(G, directed=False)
    comp = lab[src_id]
    for t in sinks:
        if lab[sink_ids[t]] != comp:
            return None
    free = free[lab[free] == comp]
    V = np.zeros(n)
    V[free] = spla.spsolve(G[free][:, free], bvec[free])
    itot = sum(sinks.values())
    P = -sum(i * V[sink_ids[t]] for t, i in sinks.items())
    areas = {l: geoms[l].area for l in layers}
    return P / itot ** 2, areas


def beckmann(cs, net, src, sinks, layers, areas):
    b = cs.b
    sp_ = unary_union([p["shape"] for p in footprint_pads(b, net, src)])
    w1 = 0.0
    for t, i in sinks.items():
        st = unary_union([p["shape"] for p in footprint_pads(b, net, t)])
        w1 += i * sp_.distance(st) * 1e-3
    term_area = {l: sum(p["shape"].area for t in [src] + list(sinks) for p in footprint_pads(b, net, t) if l in p["layers"])
                 for l in layers}
    gsum = sum(max(areas[l] - term_area[l], 1e-3) * 1e-6 / (RHO / (b.tcu.get(l, 0.035) * 1e-3)) for l in layers)
    itot = sum(sinks.values())
    return w1 ** 2 / gsum / itot ** 2


class Q4Net:
    """Multi-layer Q4 grid on a domain: designable cells, fixed terminal pads, via links, merged terminals.
    Only cells that can hold copper (domain or terminal pads) are kept as elements."""

    def __init__(self, cs, net, src, sinks, layers, domains, h=0.15):
        b = cs.b
        self.h = h
        allg = unary_union(list(domains.values()) + [cs.copper(net, l) for l in layers])
        x0, y0, x1, y1 = allg.bounds
        nx, ny = int(math.ceil((x1 - x0) / h)) + 1, int(math.ceil((y1 - y0) / h)) + 1
        xc = x0 + (np.arange(nx) + 0.5) * h
        yc = y0 + (np.arange(ny) + 0.5) * h
        XC, YC = np.meshgrid(xc, yc)
        xn, yn = np.meshgrid(x0 + np.arange(nx + 1) * h, y0 + np.arange(ny + 1) * h)
        nl = len(layers)
        nnod1 = (nx + 1) * (ny + 1)
        ex, ey = np.meshgrid(np.arange(nx), np.arange(ny))
        n1 = (ey * (nx + 1) + ex).ravel()
        edof1 = np.stack([n1, n1 + 1, n1 + nx + 2, n1 + nx + 1], 1)
        edof = np.concatenate([edof1 + li * nnod1 for li in range(nl)])
        c0 = np.concatenate([np.full(nx * ny, 1.0 / (RHO / (b.tcu.get(l, 0.035) * 1e-3))) for l in layers])
        # actual copper and domain on this grid (cell-centre test); the actual layout must be a feasible point
        act = np.concatenate([raster(cs.copper(net, l), XC, YC).ravel() for l in layers])
        des = np.concatenate([raster(domains[l], XC, YC).ravel() for l in layers]) | act
        solid = np.zeros(nl * nx * ny, bool)
        rep = np.arange(nl * nnod1)
        nid = nl * nnod1
        term = {}
        for t in [src] + list(sinks):
            ids = []
            for p in footprint_pads(b, net, t):
                for li, l in enumerate(layers):
                    if l in p["layers"]:
                        solid[li * nx * ny + np.flatnonzero(raster(p["shape"], XC, YC).ravel())] = True
                        ids.extend((li * nnod1 + np.flatnonzero(raster(p["shape"], xn, yn).ravel())).tolist())
            rep[ids] = nid
            term[t] = nid
            nid += 1
        keep = des | solid
        edof, c0, act, des, solid = edof[keep], c0[keep], act[keep], des[keep], solid[keep]
        # DOF numbering over used nodes and terminal nodes only
        rep_full = np.concatenate([rep, np.arange(nl * nnod1, nid)])
        used = np.unique(np.concatenate([rep_full[np.unique(edof)], np.array(list(term.values()), int)]))
        remap = -np.ones(nid, int)
        remap[used] = np.arange(len(used))
        node_dof = remap[rep]                     # raw node -> dof (-1 if unused)
        self.term = {t: int(remap[i]) for t, i in term.items()}
        self.edof_dof = node_dof[edof]
        self.c0 = c0
        self.nel = len(c0)
        self.solid = solid
        self.des = des & ~solid
        self.void = np.zeros(self.nel, bool)
        self.act = act & ~solid
        self.ndof = len(used)
        # via / plated-pad links between consecutive layers
        lr, lc, lv = [], [], []
        links = [(v["x"], v["y"], v) for v in b.vias if v["net"] == net]
        links += [(p["x"], p["y"], dict(size=1.0, layers=list(p["layers"]))) for p in b.pads
                  if p["net"] == net and p["through"]]
        for x, y, v in links:
            i, j = int(round((x - x0) / h)), int(round((y - y0) / h))
            if not (0 <= i <= nx and 0 <= j <= ny):
                continue
            span = [li for li, l in enumerate(layers) if l in v["layers"]]
            for a_, b_ in zip(span[:-1], span[1:]):
                ra, rb = node_dof[a_ * nnod1 + j * (nx + 1) + i], node_dof[b_ * nnod1 + j * (nx + 1) + i]
                if ra >= 0 and rb >= 0 and ra != rb:
                    lr.append(ra); lc.append(rb)
                    lv.append(via_link_g(v, b.z[layers[a_]], b.z[layers[b_]]))
        self.links = (np.array(lr, int), np.array(lc, int), np.array(lv))
        self.ik = np.repeat(self.edof_dof, 4, axis=1).ravel()
        self.jk = np.tile(self.edof_dof, (1, 4)).ravel()
        self.src = self.term[src]
        self.f = np.zeros(self.ndof)
        for t, i in sinks.items():
            self.f[self.term[t]] = -i
        self.itot = sum(sinks.values())
        self.cell_area = h * h
        # solve only on the source's connected component (stray copper would make K singular)
        sk = np.ones(len(self.ik))
        A = sp.coo_matrix((np.concatenate([sk, np.ones(len(lr) * 2)]),
                           (np.concatenate([self.ik, np.array(lr, int), np.array(lc, int)]),
                            np.concatenate([self.jk, np.array(lc, int), np.array(lr, int)]))),
                          shape=(self.ndof, self.ndof)).tocsr()
        _, lab = sp.csgraph.connected_components(A, directed=False)
        comp = lab[self.src]
        self.ok = all(lab[self.term[t]] == comp for t in sinks)
        self.free = np.flatnonzero((lab == comp) & (np.arange(self.ndof) != self.src))

    def solve(self, coef):
        sk = (coef[:, None] * KE.ravel()[None, :]).ravel()
        lr, lc, lv = self.links
        r = np.concatenate([self.ik, lr, lc, lr, lc])
        c = np.concatenate([self.jk, lr, lc, lc, lr])
        v = np.concatenate([sk, lv, lv, -lv, -lv])
        K = sp.coo_matrix((v, (r, c)), shape=(self.ndof, self.ndof)).tocsc()
        fr = self.free
        u = np.zeros(self.ndof)
        u[fr] = spla.spsolve(K[fr][:, fr], self.f[fr])
        return u

    def r_of(self, mask):
        """Loss-equivalent R of a binary layout on this grid (designable cells in mask are copper)."""
        x = np.where(self.solid | mask, 1.0, 0.0)
        u = self.solve(self.c0 * (EPS + (1 - EPS) * x))
        return (self.f @ u) / self.itot ** 2

    def elem_energy(self, u):
        ue = u[self.edof_dof]
        return np.einsum("ei,ij,ej->e", ue, KE, ue)


def convex_floor(q, iters=150, eta=0.5, move=0.2, tol=1e-3):
    """min compliance over 0 <= rho <= 1 at the actual layout's copper area on this grid (SIMP p = 1, no filter);
    returns (relaxed, dual floor). The actual layout is feasible, so floor <= R(actual on this grid)."""
    a = q.cell_area
    nb = float(q.act.sum())
    des = np.flatnonzero(q.des)
    if nb >= len(des):
        x = np.where(q.void, 0.0, 1.0)
        u = q.solve(q.c0 * (EPS + (1 - EPS) * x))
        c = q.f @ u
        return c / q.itot ** 2, c / q.itot ** 2
    x = np.zeros(q.nel)
    x[q.solid] = 1.0
    x[des] = nb / len(des)
    best_lb, obj = 0.0, float("inf")
    for it in range(iters):
        u = q.solve(q.c0 * (EPS + (1 - EPS) * x))
        c = q.f @ u
        e = q.elem_energy(u)
        obj = c
        # dual bound: c^2 / max_rho u'K(rho)u (fractional knapsack over the designable cells)
        base = np.sum(q.c0[q.solid] * e[q.solid]) + EPS * np.sum(q.c0[q.void] * e[q.void])
        ed = (1 - EPS) * q.c0[des] * e[des]
        order = np.argsort(-ed)
        k = int(np.floor(nb))
        qmax = base + ed[order[:k]].sum() + (nb - k) * (ed[order[k]] if k < len(des) else 0.0)
        lr, lc, lv = q.links
        qmax += np.sum(lv * (u[lr] - u[lc]) ** 2)
        best_lb = max(best_lb, c * c / qmax)
        if (obj - best_lb) / obj < tol:
            break
        grad = -(1 - EPS) * q.c0[des] * e[des]
        xd = x[des]
        bb = np.maximum(-grad, 1e-300)
        lo, hi = 1e-40, 1e40
        while hi / lo > 1 + 1e-9:
            lm = math.sqrt(lo * hi)
            xn = np.clip(np.maximum(xd, 1e-4) * (bb / (lm * a)) ** eta, np.maximum(0.0, xd - move), np.minimum(1.0, xd + move))
            if xn.sum() > nb:
                lo = lm
            else:
                hi = lm
        x[des] = xn
    return obj / q.itot ** 2, best_lb / q.itot ** 2


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    print("== pilot floor census (R in mOhm, loss-equivalent P/I^2 for the stated current pattern; avoidable = 1 - floor/R)")
    print("   R_act from 0.1 mm finite volumes; each floor is compared with the same copper on its own Q4 grid")
    print("   avoidable fraction at equal area when the freedom is: shape (own zones) / routing (+ other tracks, vias)")
    print("   / partition (+ other zones' fills) / anywhere (Beckmann, no domain)")
    print(f"   {'board':10s} {'net':12s} {'layers':10s} {'A mm2':>7s} {'I A':>5s} {'R mOhm':>8s} {'P mW':>7s}   "
          "shape/rout/part/any %   avoidable mW (same order)   note")
    rows = []
    for board, nets in PILOT.items():
        path = os.path.join(root, board, "board.kicad_pcb")
        if not os.path.exists(path):
            print(f"   {board}: not found under {root}")
            continue
        cs = Census(path)
        for net, src, sinks, note in nets:
            t0 = time.time()
            layers = cs.net_layers(net)
            res = solve_actual(cs, net, src, sinks, layers)
            if res is None:
                print(f"   {board:10s} {net:12s} skipped: a terminal is not on the net's copper")
                continue
            r_act, areas = res
            r_b = beckmann(cs, net, src, sinks, layers, areas)
            a_tot = sum(areas.values())
            floors, r_grid = [], []
            fulls = []
            for mode in ("shape", "routing", "partition"):
                doms = {l: cs.domain(net, l, mode) for l in layers}
                dom_area = sum(d.area for d in doms.values())
                q = Q4Net(cs, net, src, sinks, layers, doms, h=0.15 if dom_area < 400 else 0.25)
                r_grid.append(q.r_of(q.act))
                fulls.append(q.r_of(q.des))
                _, lb = convex_floor(q)
                floors.append(lb / r_grid[-1])
            itot = sum(sinks.values())
            av = [1 - f for f in floors] + [1 - r_b / r_act]
            mw = [itot ** 2 * r_act * x * 1e3 for x in av]
            lay = "/".join(l.replace(".Cu", "") for l in layers)
            rows.append((board, net, av, itot ** 2 * r_act * 1e3))
            print(f"   {board:10s} {net:12s} {lay:10s} {a_tot:7.1f} {itot:5.2f} {r_act*1e3:8.3f} {itot**2*r_act*1e3:7.2f}   "
                  + "/".join(f"{x*100:3.0f}" for x in av) + " %   " + "/".join(f"{x:6.2f}" for x in mw)
                  + f"   {note} ({time.time()-t0:.0f} s)", flush=True)
    if rows:
        av = np.array([r[2] for r in rows])
        p = np.array([r[3] for r in rows])
        print(f"\n   {len(rows)} nets: median avoidable shape {np.median(av[:,0])*100:.0f} %, routing {np.median(av[:,1])*100:.0f} %,"
              f" partition {np.median(av[:,2])*100:.0f} %, anywhere {np.median(av[:,3])*100:.0f} %;"
              f" total loss {p.sum():.1f} mW, of which avoidable by partition {np.sum(p*av[:,2]):.1f} mW")


if __name__ == "__main__":
    main()
