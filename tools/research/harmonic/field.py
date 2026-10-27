# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Harmonic (Laplace) fields per net on a coarse grid of the pnr engine's World
(docs/ideas/original/joint-pnr.md, idea 19).

The board is a resistor network: one node per coarse cell (s x s fine cells, default
0.4 mm) per copper layer, 4-neighbour edges in-plane and one via edge per (y, x) between
adjacent layers. Cell conductance is the mean over its fine cells of

    sigma = 1 / (1 + hist + beta * foreign)      (0 where a track centre is statically blocked)

so at beta = inf other nets' copper and pads are insulating walls (Neumann) and at finite
beta they are priced like PathFinder's present cost. Edge conductance is the harmonic mean
of its two cells; via edges are scaled by `via_sigma` (a via costs ~1/via_sigma cells).

Per net: the pin nearest the pins' centroid is the source (phi = 1), every other pin is a
sink (phi = 0) (Dirichlet), everything else is solved (L_ff phi_f = -L_fd phi_d). By the
discrete maximum principle phi has no interior extrema, so steepest ascent from any sink
reaches the source: a route without search. Streamlines of the field ascending from every
sink merge into a tree.

Outputs per net: phi, the current density |J| / I (expected wire occupancy: it integrates
to about the mean streamline length), and the streamline tree (coarse (l, y, x) cells).
"""
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve


def block_mean(a, s, Hc, Wc):
    """Mean over s x s blocks of the last two axes (padding with zeros -> blocked)."""
    *lead, H, W = a.shape
    pad = np.zeros((*lead, Hc * s, Wc * s), np.float32)
    pad[..., :H, :W] = a
    return pad.reshape(*lead, Hc, s, Wc, s).mean(axis=(-3, -1))


class Field:
    def __init__(self, world, coarse_mm=0.4, via_sigma=0.2, eps=1e-4):
        self.w = world
        self.s = s = max(1, int(round(coarse_mm / world.g)))
        self.Hc = -(-world.H // s)
        self.Wc = -(-world.W // s)
        self.L = world.nl
        self.via_sigma = via_sigma
        self.eps = eps
        self.n = self.L * self.Hc * self.Wc
        L, Hc, Wc = self.L, self.Hc, self.Wc
        idx = np.arange(self.n).reshape(L, Hc, Wc)
        # edge lists (i, j, kind): kind 0 = x, 1 = y, 2 = via
        ex = np.stack([idx[:, :, :-1].ravel(), idx[:, :, 1:].ravel()], 1)
        ey = np.stack([idx[:, :-1, :].ravel(), idx[:, 1:, :].ravel()], 1)
        ev = np.stack([idx[:-1].ravel(), idx[1:].ravel()], 1) if L > 1 else np.zeros((0, 2), int)
        self.E = np.concatenate([ex, ey, ev])
        self.kind = np.concatenate([np.zeros(len(ex)), np.ones(len(ey)), 2 * np.ones(len(ev))])
        self.static = (~world.blockT).astype(np.float32)  # (L, H, W) 1 where a track may go
        self.warm = {}
        self._edges = {}
        self.solves = 0

    # ------------------------------------------------------------ geometry
    def coarse(self, l, y, x):
        return (l * self.Hc + y // self.s) * self.Wc + x // self.s

    def pins(self, net):
        """Coarse node sets per placed pin of `net`."""
        w = self.w
        out = []
        for pi, k in w.net_pins[net]:
            if pi not in w.pose:
                continue
            t = np.array(w.terminals(pi, k), np.int64).reshape(-1, 3)
            t = t[(t[:, 1] >= 0) & (t[:, 2] >= 0) & (t[:, 1] < w.H) & (t[:, 2] < w.W)]
            if len(t):
                out.append(np.unique(self.coarse(t[:, 0], t[:, 1], t[:, 2])))
        return out

    def sigma(self, net, beta=np.inf, hist=None, extra=None):
        """Coarse cell conductance (L, Hc, Wc) for `net`."""
        w = self.w
        foreign = (w.DT - (w.occT[net] > 0)).astype(np.float32)
        if np.isinf(beta):
            sf = (foreign <= 0).astype(np.float32)
            if hist is not None:
                sf = sf / (1.0 + hist)
        else:
            den = 1.0 + beta * np.maximum(foreign, 0)
            if hist is not None:
                den = den + hist
            if extra is not None:
                den = den + extra
            sf = 1.0 / den
        sf *= self.static
        return block_mean(sf, self.s, self.Hc, self.Wc)

    # ------------------------------------------------------------ solve
    def edges(self, L, h, wd):
        key = (L, h, wd)
        e = self._edges.get(key)
        if e is None:
            idx = np.arange(L * h * wd).reshape(L, h, wd)
            ex = np.stack([idx[:, :, :-1].ravel(), idx[:, :, 1:].ravel()], 1)
            ey = np.stack([idx[:, :-1, :].ravel(), idx[:, 1:, :].ravel()], 1)
            ev = np.stack([idx[:-1].ravel(), idx[1:].ravel()], 1) if L > 1 else np.zeros((0, 2), int)
            E = np.concatenate([ex, ey, ev])
            via = np.r_[np.zeros(len(ex) + len(ey), bool), np.ones(len(ev), bool)]
            e = self._edges[key] = (E, via)
        return e

    def solve(self, net, sig, pins=None, src=None, margin_mm=4.0, wall=0.02, **_):
        """Dirichlet solve in the pins' bounding box + margin (Neumann at the window edge and
        at walls: cells with conductance < `wall` are removed). Returns (phi, pins, src) with
        phi over the whole coarse grid (0 outside the window)."""
        from scipy.sparse.csgraph import connected_components
        pins = self.pins(net) if pins is None else pins
        if len(pins) < 2:
            return None, pins, None
        HW = self.Hc * self.Wc
        ys = np.concatenate([(p % HW) // self.Wc for p in pins])
        xs = np.concatenate([p % self.Wc for p in pins])
        if src is None:
            cents = np.array([[np.mean((p % HW) // self.Wc), np.mean(p % self.Wc)] for p in pins])
            src = int(np.argmin(((cents - cents.mean(0)) ** 2).sum(1)))
        m = int(np.ceil(margin_mm / (self.s * self.w.g)))
        y0, y1 = max(0, ys.min() - m), min(self.Hc, ys.max() + m + 1)
        x0, x1 = max(0, xs.min() - m), min(self.Wc, xs.max() + m + 1)
        L, h, wd = self.L, y1 - y0, x1 - x0
        sub = np.ascontiguousarray(sig[:, y0:y1, x0:x1], np.float64)
        nn = L * h * wd
        fixed = np.full(nn, -1.0)

        def loc(p):
            l, r = np.divmod(p, HW)
            y, x = np.divmod(r, self.Wc)
            return (l * h + (y - y0)) * wd + (x - x0)
        for i, p in enumerate(pins):
            if i != src:
                fixed[loc(p)] = 0.0
        fixed[loc(pins[src])] = 1.0
        sv = sub.ravel().copy()
        sv[fixed >= 0] = np.maximum(sv[fixed >= 0], 0.5)  # pads conduct
        sub[...] = sv.reshape(L, h, wd)
        sig[:, y0:y1, x0:x1] = sub  # (in place: density/streamlines see the same cells)
        alive = sv >= wall
        E, via = self.edges(L, h, wd)
        a, b = E[:, 0], E[:, 1]
        ok = alive[a] & alive[b]
        a, b = a[ok], b[ok]
        c = 2.0 * sv[a] * sv[b] / (sv[a] + sv[b])
        c = np.where(via[ok], self.via_sigma * c, c)
        A = sp.coo_matrix((np.r_[c, c], (np.r_[a, b], np.r_[b, a])), shape=(nn, nn)).tocsr()
        ncomp, lab = connected_components(A, directed=False)
        good = np.zeros(ncomp + 1, bool)
        good[lab[fixed >= 0]] = True
        live = alive & good[lab]
        d = np.asarray(A.sum(1)).ravel()
        Lap = (sp.diags(d) - A).tocsr()
        free = np.flatnonzero(live & (fixed < 0))
        dn = np.flatnonzero(fixed >= 0)
        phis = np.zeros(nn)
        phis[dn] = fixed[dn]
        if len(free):
            Af = Lap[free][:, free]
            rhs = -(Lap[free][:, dn] @ fixed[dn])
            phis[free] = spsolve(Af.tocsc(), rhs)
        self.solves += 1
        self.cells_solved = getattr(self, "cells_solved", 0) + len(free)
        phis[~live] = np.nan
        phi = np.full(self.n, np.nan)
        phi.reshape(L, self.Hc, self.Wc)[:, y0:y1, x0:x1] = phis.reshape(L, h, wd)
        # NaN outside the window and in walls / dead components: no current, never entered
        return phi, pins, src

    def density(self, phi, sig):
        """|J| / I per node: current through each node (half the sum of |edge currents|)
        over the total current from the source: the expected wire occupancy."""
        sv = sig.ravel() + self.eps
        a, b = self.E[:, 0], self.E[:, 1]
        c = 2.0 * sv[a] * sv[b] / (sv[a] + sv[b])
        c = np.where(self.kind == 2, self.via_sigma * c, c)
        cur = np.nan_to_num(np.abs(c * (phi[a] - phi[b])))
        node = np.zeros(self.n)
        np.add.at(node, a, cur)
        np.add.at(node, b, cur)
        node *= 0.5
        sa, sb = phi[a] >= 1.0 - 1e-9, phi[b] >= 1.0 - 1e-9
        I = cur[sa ^ sb].sum()
        return node / max(I, 1e-12)

    def streamlines(self, phi, sig, pins, src):
        """Steepest-ascent tree (by edge current) from every sink pin to the source; paths
        stop when they meet the tree. Returns list of coarse node arrays (sink -> tree)."""
        sv = sig.ravel() + self.eps
        Hc, Wc, L = self.Hc, self.Wc, self.L
        HW = Hc * Wc
        on_tree = np.zeros(self.n, bool)
        on_tree[pins[src]] = True
        paths = []
        for i, p in enumerate(pins):
            if i == src:
                continue
            if on_tree[p].any():
                paths.append(p[on_tree[p]][:1])
                continue
            cur = int(p[np.argmax(phi[p])])
            path = [cur]
            seen = {cur}
            ok = False
            for _ in range(4 * (Hc + Wc) * L + 100):
                if on_tree[cur]:
                    ok = True
                    break
                l, r = divmod(cur, HW)
                y, x = divmod(r, Wc)
                best, bv = -1, 0.0
                for dl, dy, dx, f in ((0, 0, 1, 1.0), (0, 0, -1, 1.0), (0, 1, 0, 1.0), (0, -1, 0, 1.0),
                                      (1, 0, 0, self.via_sigma), (-1, 0, 0, self.via_sigma)):
                    ll, yy, xx = l + dl, y + dy, x + dx
                    if not (0 <= ll < L and 0 <= yy < Hc and 0 <= xx < Wc):
                        continue
                    nb = (ll * Hc + yy) * Wc + xx
                    if nb in seen:
                        continue
                    ce = f * 2 * sv[cur] * sv[nb] / (sv[cur] + sv[nb])
                    v = ce * (phi[nb] - phi[cur])
                    if v > bv:
                        best, bv = nb, v
                if best < 0:
                    break
                cur = best
                seen.add(cur)
                path.append(cur)
            arr = np.array(path, np.int64)
            paths.append(arr if ok else None)
            if ok:
                on_tree[arr] = True
                on_tree[p] = True
        return paths

    def unravel(self, nodes):
        HW = self.Hc * self.Wc
        l, r = np.divmod(nodes, HW)
        y, x = np.divmod(r, self.Wc)
        return l, y, x
