# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pour-damage maps from the Dirichlet/Thomson principle (transformations.md, T4).

For every pour (zone net n, copper layer l) of a pnr World:

  region   cells the pour could fill: inside the zone outline and the board, and not in a
           foreign net's halo (World.DT - own occT == 0), so placed parts and routed
           tracks of other nets are holes in it (the model of collapse_pour/netcond.py:
           sheet conductance 1 per square, pads of n as equipotential terminals)
  solve    on a coarse grid (default 0.4 mm, factor f fine cells per side) the cell
           conductivity is the free fraction sigma of its f x f block; edge conductance is
           the harmonic mean 2 sa sb / (sa + sb). One sparse LU of the grounded Laplacian
           per connected component, then one back-solve per terminal (unit current in at
           t, out at the ground terminal).
  metric   R_eff = 1 / mean over all pad pairs of 1/R_ij (disconnected pairs count 0), as
           netcond.net_resistance.
  map      Thomson: dR_ij / dc_e = -(dphi_e^ij)^2. Removing one fine free cell of block a
           lowers sigma_a by 1/f^2, so its first-order relative damage is
               s_a = R_eff / P / f^2 * sum_{e at a} dc_e/dsigma_a * sum_{i<j} (dphi_e^ij)^2 / R_ij^2
           E[y, x] = s_a(y,x) * free[y, x] (relative R_eff increase per removed fine cell),
           scaled by the layer's share of the net's conductance so that the maps of all
           layers of a net add up to the relative change of the whole net.

A part's damage at every origin is then corr(E_{n,l}, its foreign-pad halo cells on l)
(FFT), and a track's per-step damage is corr(E, track halo disc) / disc diameter.
"""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.sparse.csgraph import connected_components


def _block_mean(m, f, Hc, Wc):
    H, W = m.shape
    p = np.zeros((Hc * f, Wc * f), np.float64)
    p[:H, :W] = m
    return p.reshape(Hc, f, Wc, f).mean((1, 3))


def solve_sheet(sigma, term, max_terms=48, rng=None):
    """One layer: solve_stack with L = 1 (the round-1 per-layer model)."""
    out = solve_stack(sigma[None], term[None])
    out["s"] = out["s"][0]
    return out


def solve_stack(sigma, term, links=None):
    """sigma (L, Hc, Wc) conductivity in [0, 1]; term (L, Hc, Wc) int terminal ids (0 none,
    ids 1..T; one id may cover cells on several layers, i.e. a plated pad is one
    equipotential terminal on all its layers); links (K, 3) rows (flat cell a, flat cell b,
    conductance) of fixed inter-layer edges (vias of the net). Returns dict(R_eff, Gm, R
    (TxT), s (L, Hc, Wc) relative R_eff sensitivity per unit of sigma removed, i.e.
    d(R_eff)/R_eff for d sigma_a = -1). Fixed links carry no sensitivity."""
    L, Hc, Wc = sigma.shape
    T = int(term.max())
    out = dict(R_eff=None, Gm=0.0, T=T, s=np.zeros((L, Hc, Wc)))
    if T < 2:
        return out
    sig = np.where(term > 0, 1.0, sigma)
    alive = sig > 1e-6
    # node ids: terminals 0..T-1, free cells T..
    node = -np.ones((L, Hc, Wc), np.int64)
    node[term > 0] = term[term > 0] - 1
    free = alive & (term == 0)
    nf = int(free.sum())
    node[free] = T + np.arange(nf)
    N = T + nf
    # edges (a, b) between in-plane 4-neighbours, both alive
    ea, eb, ca, cb = [], [], [], []
    ia = np.arange(L * Hc * Wc).reshape(L, Hc, Wc)
    S = slice(None)
    for (A, B) in (((S, S, slice(0, -1)), (S, S, slice(1, None))),
                   ((S, slice(0, -1), S), (S, slice(1, None), S))):
        na, nb = node[A], node[B]
        m = (na >= 0) & (nb >= 0) & (na != nb)
        ea.append(na[m]); eb.append(nb[m])
        ca.append(ia[A][m]); cb.append(ia[B][m])
    ea = np.concatenate(ea); eb = np.concatenate(eb)
    ca = np.concatenate(ca); cb = np.concatenate(cb)
    sa = sig.ravel()[ca]; sb = sig.ravel()[cb]
    ce = 2 * sa * sb / (sa + sb)
    # fixed inter-layer links (no sensitivity)
    xa = xb = np.zeros(0, np.int64)
    xg = np.zeros(0)
    if links is not None and len(links):
        lk = np.asarray(links, np.float64)
        fa, fb = lk[:, 0].astype(np.int64), lk[:, 1].astype(np.int64)
        na, nb = node.ravel()[fa], node.ravel()[fb]
        m = (na >= 0) & (nb >= 0) & (na != nb)
        xa, xb, xg = na[m], nb[m], lk[m, 2]
    A = sp.coo_matrix((np.concatenate([ce, xg]), (np.concatenate([ea, xa]), np.concatenate([eb, xb]))),
                      shape=(N, N)).tocsr()
    A = A + A.T
    ncomp, lab = connected_components(A, directed=False)
    R = np.full((T, T), np.inf)
    np.fill_diagonal(R, 0.0)
    phi_cols = {}  # terminal -> potential vector (N,), grounded per component
    Lfull = (sp.diags(np.asarray(A.sum(1)).ravel()) - A).tocsr()
    comps = {}
    for t in range(T):
        comps.setdefault(lab[t], []).append(t)
    for c, tids in comps.items():
        if len(tids) < 2:
            continue
        nodes = np.flatnonzero(lab == c)
        g0 = tids[0]
        keep = nodes[nodes != g0]
        pos = -np.ones(N, np.int64)
        pos[keep] = np.arange(len(keep))
        Lc = Lfull[keep][:, keep].tocsc()
        lu = spla.splu(Lc)
        B = np.zeros((len(keep), len(tids) - 1))
        for k, t in enumerate(tids[1:]):
            B[pos[t], k] = 1.0
        X = lu.solve(B)
        phi_cols[g0] = None
        for k, t in enumerate(tids[1:]):
            v = np.zeros(N)
            v[keep] = X[:, k]
            phi_cols[t] = v
        Xt = np.array([[phi_cols[a][b] for b in tids[1:]] for a in tids[1:]])
        dg = np.diag(Xt)
        ids = np.array(tids)
        R[ids[0], ids[1:]] = dg
        R[ids[1:], ids[0]] = dg
        R[np.ix_(ids[1:], ids[1:])] = dg[:, None] + dg[None, :] - 2 * Xt
    iu = np.triu_indices(T, 1)
    rv = R[iu]
    P = len(rv)
    Gp = np.where(np.isfinite(rv) & (rv > 0), 1.0 / np.maximum(rv, 1e-12), 0.0)
    Gm = float(Gp.mean())
    out["R"] = R
    out["Gm"] = Gm
    if Gm <= 0:
        return out
    R_eff = 1.0 / Gm
    out["R_eff"] = R_eff
    # per-edge Q_e = sum_{i<j, connected} w_ij (dphi_e^i - dphi_e^j)^2, w = 1/R_ij^2
    Q = np.zeros(len(ea))
    for c, tids in comps.items():
        if len(tids) < 2:
            continue
        ids = np.array(tids)
        Rs = R[np.ix_(ids, ids)]
        Wt = np.where((Rs > 0) & np.isfinite(Rs), 1.0 / np.maximum(Rs, 1e-12) ** 2, 0.0)
        np.fill_diagonal(Wt, 0.0)
        sel = lab[ea] == c
        D = np.zeros((len(ids), int(sel.sum())))
        for k, t in enumerate(tids):
            v = phi_cols.get(t)
            if v is not None:
                D[k] = v[ea[sel]] - v[eb[sel]]
        d = Wt.sum(1)
        Q[sel] = (d[:, None] * D * D).sum(0) - (D * (Wt @ D)).sum(0)
    Q = np.maximum(Q, 0.0)
    # dc_e/dsigma_a = 2 sb^2 / (sa + sb)^2
    da = 2 * sb * sb / (sa + sb) ** 2
    db = 2 * sa * sa / (sa + sb) ** 2
    s = np.zeros(L * Hc * Wc)
    np.add.at(s, ca, da * Q)
    np.add.at(s, cb, db * Q)
    s *= R_eff / P
    s[(term > 0).ravel()] = 0.0
    out["s"] = s.reshape(L, Hc, Wc)
    return out


class PourMaps:
    """Per (net, layer) pour of a World: region, terminals, coarse solve and the fine
    damage map E (relative R_eff increase of the net per removed fine cell)."""

    VIA_G = 0.5  # through-stack conductance of one plated hole, squares^-1 (netcond.VIA_G)

    def __init__(self, world, coarse_mm=0.4, max_terms=48, seed=0, coupled=False, vias=None):
        """coupled: solve each net's pour layers together (plated pads are one terminal on
        all their layers, the net's vias link the layers), instead of one sheet per layer.
        vias: callable net -> (K, 2) int array of the net's via cells (y, x) on the fine grid."""
        from raster import raster_poly
        self.coupled = coupled
        self.vias = vias
        self.w = w = world
        self.f = max(1, int(round(coarse_mm / w.g)))
        self.Hc = -(-w.H // self.f)
        self.Wc = -(-w.W // self.f)
        self.max_terms = max_terms
        self.rng = np.random.default_rng(seed)
        zm = {}
        for z in w.data.get("zones", []):
            nid = w.net_id.get(z["net"])
            if not nid or nid not in w.net_pins:
                continue
            for lid in z["layers"]:
                l = 0 if lid == 0 else (w.nl - 1 if lid == 2 else (lid - 4) // 2 + 1)
                m = zm.setdefault((nid, l), np.zeros((w.H, w.W), bool))
                for poly in z["poly"]:  # outlines (kicad_io drops holes)
                    if len(poly) < 3:
                        continue
                    c = raster_poly(np.array(poly, float), 0.0, w.x0, w.y0, w.g)
                    ok = (c[:, 0] >= 0) & (c[:, 1] >= 0) & (c[:, 0] < w.W) & (c[:, 1] < w.H)
                    m[c[ok, 1], c[ok, 0]] = True
        self.zone = {k: v & w.inside for k, v in zm.items() if v.any()}
        self.pours = sorted(self.zone)
        self.E = {}
        self.info = {}

    def free(self, n, l, extra_cut=None):
        w = self.w
        fr = self.zone[(n, l)] & ((w.DT[l] - (w.occT[n, l] > 0)) == 0)
        if extra_cut is not None:
            fr = fr & ~extra_cut
        return fr

    def terminals(self, n, l):
        """(Hc, Wc) int terminal ids from the placed pads of net n on layer l."""
        w, f = self.w, self.f
        term = np.zeros((self.Hc, self.Wc), np.int32)
        pins = [(pi, k) for pi, k in w.net_pins.get(n, []) if pi in w.pose]
        cells = []
        for pi, k in pins:
            ent = w.raster(pi)["pads"][k]
            if l not in ent["layers"] or not len(ent["cu"]):
                continue
            cx, cy, _ = w.pose[pi]
            xs, ys = ent["cu"][:, 0] + cx, ent["cu"][:, 1] + cy
            ok = (xs >= 0) & (ys >= 0) & (xs < w.W) & (ys < w.H)
            if ok.any():
                cells.append(np.unique(np.stack([ys[ok] // f, xs[ok] // f], 1), axis=0))
        if len(cells) > self.max_terms:
            idx = np.sort(self.rng.choice(len(cells), self.max_terms, replace=False))
            cells = [cells[i] for i in idx]
        for t, c in enumerate(cells):
            term[c[:, 0], c[:, 1]] = t + 1
        # renumber (a later pad may cover an earlier one completely)
        u = np.unique(term[term > 0])
        remap = np.zeros(len(cells) + 1, np.int32)
        remap[u] = np.arange(1, len(u) + 1)
        return remap[term]

    def solve(self, n, l, extra_cut=None, term=None):
        fr = self.free(n, l, extra_cut)
        sigma = _block_mean(fr, self.f, self.Hc, self.Wc)
        if term is None:
            term = self.terminals(n, l)
        return solve_sheet(sigma, term), fr, term

    # ------------------------------------------------------------ coupled (round 2)
    def net_layers(self, n):
        return sorted(l for nn, l in self.pours if nn == n)

    def terminals_net(self, n, layers):
        """(len(layers), Hc, Wc) terminal ids; one id per pad over all its layers."""
        w, f = self.w, self.f
        term = np.zeros((len(layers), self.Hc, self.Wc), np.int32)
        pads = []
        for pi, k in w.net_pins.get(n, []):
            if pi not in w.pose:
                continue
            ent = w.raster(pi)["pads"][k]
            if not len(ent["cu"]):
                continue
            cx, cy, _ = w.pose[pi]
            xs, ys = ent["cu"][:, 0] + cx, ent["cu"][:, 1] + cy
            ok = (xs >= 0) & (ys >= 0) & (xs < w.W) & (ys < w.H)
            if not ok.any():
                continue
            c = np.unique(np.stack([ys[ok] // f, xs[ok] // f], 1), axis=0)
            ks = [j for j, l in enumerate(layers) if l in ent["layers"]]
            if ks:
                pads.append((ks, c))
        if len(pads) > self.max_terms:
            idx = np.sort(self.rng.choice(len(pads), self.max_terms, replace=False))
            pads = [pads[i] for i in idx]
        for t, (ks, c) in enumerate(pads):
            for j in ks:
                term[j, c[:, 0], c[:, 1]] = t + 1
        u = np.unique(term[term > 0])
        remap = np.zeros(len(pads) + 1, np.int32)
        remap[u] = np.arange(1, len(u) + 1)
        return remap[term]

    def links_net(self, n, layers):
        if self.vias is None or len(layers) < 2:
            return None
        v = np.asarray(self.vias(n), np.int64).reshape(-1, 2)
        if not len(v):
            return None
        f, HW = self.f, self.Hc * self.Wc
        cc = np.unique((v[:, 0] // f) * self.Wc + v[:, 1] // f)
        rows = []
        for j in range(len(layers) - 1):
            g = self.VIA_G * (self.w.nl - 1) / (layers[j + 1] - layers[j])
            rows.append(np.stack([cc + j * HW, cc + (j + 1) * HW, np.full(len(cc), g)], 1))
        return np.concatenate(rows)

    def solve_net(self, n, extra_cut=None, cut_layer=None, term=None):
        layers = self.net_layers(n)
        frs = [self.free(n, l, extra_cut if l == cut_layer else None) for l in layers]
        sigma = np.stack([_block_mean(fr, self.f, self.Hc, self.Wc) for fr in frs])
        if term is None:
            term = self.terminals_net(n, layers)
        return solve_stack(sigma, term, self.links_net(n, layers)), frs, term

    def refresh_coupled(self):
        w, f = self.w, self.f
        self.E = {}
        self.info = {}
        for n in sorted({n for n, _ in self.pours}):
            layers = self.net_layers(n)
            r, frs, term = self.solve_net(n)
            for j, l in enumerate(layers):
                self.info[(n, l)] = dict(R_eff=r["R_eff"], T=r["T"], weight=1.0)
                if r["R_eff"] is None:
                    continue
                s = np.kron(r["s"][j], np.ones((f, f)))[:w.H, :w.W] / (f * f)
                self.E[(n, l)] = (s * frs[j]).astype(np.float32)
        return self.E

    def refresh(self):
        """Recompute every pour's map. Returns the total relative-free cost in seconds."""
        if self.coupled:
            return self.refresh_coupled()
        w, f = self.w, self.f
        res = {}
        for (n, l) in self.pours:
            r, fr, term = self.solve(n, l)
            res[(n, l)] = (r, fr, term)
        # layer weights: share of the net's conductance
        gsum = {}
        for (n, l), (r, _, _) in res.items():
            gsum[n] = gsum.get(n, 0.0) + r["Gm"]
        self.E = {}
        self.info = {}
        for (n, l), (r, fr, term) in res.items():
            wl = r["Gm"] / gsum[n] if gsum[n] > 0 else 0.0
            self.info[(n, l)] = dict(R_eff=r["R_eff"], T=r["T"], weight=wl)
            if wl <= 0 or r["R_eff"] is None:
                continue
            s = np.kron(r["s"], np.ones((f, f)))[:w.H, :w.W] / (f * f)
            self.E[(n, l)] = (wl * s * fr).astype(np.float32)
        return self.E

    def layer_total(self, l, skip_net=None):
        acc = None
        for (n, ll), E in self.E.items():
            if ll != l or n == skip_net:
                continue
            acc = E.copy() if acc is None else acc + E
        return acc
