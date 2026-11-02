# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Steady heat conduction on the raster of a Mesh (kae.em.mesh): the temperature rise of every cell of
every copper layer above ambient, for heat injected anywhere.

    in plane     each layer's sheet conductance k t: copper where the cell has copper, plus an equal
                 share of the laminate's own (k_fr4 times the board's dielectric thickness)
    between      layer l and l + 1 through their dielectric gap: k_fr4 p^2 / gap per cell, plus every
                 via's plated barrel, k_cu pi d t_plating / gap
    to the air   both outer layers: h p^2 per cell (natural convection and radiation)
    reliefs      optional (cut, links): a thermal relief's gap cells carry no copper in plane (their raster
                 labels the pad's or pour's copper), and each spoke is a lumped link k_cu t w / gap between
                 the pad and the pour
    to a sink    optional (sinks): extra conductance per cell to a body at its own temperature (a cold
                 plate or enclosure under the board, a fan's stronger cooling over a region)

Neighbouring cells join through their half-cells in series. The system is symmetric positive
definite; one sparse factorization serves every heat pattern.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as sla

K_CU = 390.0            # W/(m K)
K_FR4 = 0.3             # W/(m K), through and along the laminate (along it is nearer 0.8; conservative)
H_AIR = 12.0            # W/(m^2 K): natural convection plus radiation from a board in still air (prior)
T_PLATING = 25e-6       # m, via barrel plating


SPOKE_SPREAD = 1.25     # a spoke's resistance over its bar's, w / (k t gap): the spreading where it meets pad and
                        # pour, from the resolved geometry (tests: 0.25-0.5 mm gaps, 0.25-0.5 mm spokes at 0.05 mm)


def spoke_links(m, layer, w, a, z, gap, k_cu=K_CU):
    """A thermal-relief spoke as lumped links for Thermal(links=...): k_cu t w / (gap SPOKE_SPREAD) in all,
    across the spoke's width (one link per cell of it, side by side between its two ends a and z, (x, y) mm),
    so the heat enters pad and pour along the spoke's width as it does in copper, not through one cell. A raster
    at the evaluator's pitch cannot resolve a relief: painted, a 0.25-0.3 mm gap reads the same whatever its
    spokes' width."""
    n = max(1, int(round(w / m.pitch)))
    dx, dy = z[0] - a[0], z[1] - a[1]
    L = max(np.hypot(dx, dy), 1e-9)
    tx, ty = -dy / L, dx / L
    G = k_cu * m.layers[layer].t * 1e-3 * w / gap / SPOKE_SPREAD / n
    out = []
    for k in range(n):
        o = (k - (n - 1) / 2) * m.pitch
        out.append(((layer, *m.cell(a[0] + tx * o, a[1] + ty * o)), (layer, *m.cell(z[0] + tx * o, z[1] + ty * o)), G))
    return out


class Thermal:
    """The conduction network of a mesh. gaps: dielectric thickness (mm) between consecutive layers.
    sinks: [(layer index, G)] with G an (ny, nx) array of W/K per cell from that layer's cells to a sink
    (solve() takes each sink's temperature rise above ambient; 0 = at ambient)."""

    def __init__(self, m, gaps, h=H_AIR, k_fr4=K_FR4, k_cu=K_CU, sinks=(), cut=(), links=()):
        self.m = m
        self.sinks = [(int(l), np.asarray(G, float)) for l, G in sinks]
        L, ny, nx = m.lab.shape
        self.shape = (L, ny, nx)
        p = m.pitch * 1e-3
        n = L * ny * nx
        idx = np.arange(n).reshape(L, ny, nx)
        lam = k_fr4 * sum(gaps) * 1e-3 / L                         # each layer's share of the laminate
        g = np.where(m.lab >= 0, k_cu * np.array([l.t for l in m.layers])[:, None, None] * 1e-3, 0.0) + lam
        for l, mask in cut:                                        # relief gaps: laminate only
            g[l] = np.where(mask, lam, g[l])
        rows, cols, vals = [], [], []

        def link(a, b, G):
            rows.extend([a, b, a, b]), cols.extend([a, b, b, a]), vals.extend([G, G, -G, -G])
        # in plane: half-cells in series (a square: the sheet conductance itself)
        for (sa, sb) in ((np.s_[:, :, :-1], np.s_[:, :, 1:]), (np.s_[:, :-1, :], np.s_[:, 1:, :])):
            with np.errstate(divide="ignore"):                    # a cell without copper or laminate joins nothing
                G = 2.0 / (1.0 / g[sa] + 1.0 / g[sb])
            link(idx[sa].ravel(), idx[sb].ravel(), G.ravel())
        # between layers: the dielectric under each cell, and the vias' barrels
        for l in range(L - 1):
            gap = gaps[l] * 1e-3
            link(idx[l].ravel(), idx[l + 1].ravel(), np.full(ny * nx, k_fr4 * p * p / gap))
        for v in m.vias:
            j, i = m.cell(v.x, v.y)
            if not (0 <= j < ny and 0 <= i < nx):
                continue
            ls = sorted(v.layers)
            for la, lb in zip(ls[:-1], ls[1:]):
                dz = sum(gaps[la:lb]) * 1e-3
                if dz <= 0:                                   # not two meshed layers apart: no barrel to model
                    continue
                link(np.array([idx[la, j, i]]), np.array([idx[lb, j, i]]),
                     np.array([k_cu * np.pi * v.drill * 1e-3 * T_PLATING / dz]))
        for (la, ja, ia), (lb, jb, ib), G in links:                # relief spokes and other lumped paths
            if 0 <= ja < ny and 0 <= ia < nx and 0 <= jb < ny and 0 <= ib < nx:
                link(np.array([idx[la, ja, ia]]), np.array([idx[lb, jb, ib]]), np.array([float(G)]))
        rows = np.concatenate([np.atleast_1d(r) for r in rows])
        cols = np.concatenate([np.atleast_1d(c) for c in cols])
        vals = np.concatenate([np.atleast_1d(v) for v in vals])
        diag = np.zeros(n)
        diag[idx[0].ravel()] += h * p * p
        diag[idx[-1].ravel()] += h * p * p
        for l, G in self.sinks:
            diag[idx[l].ravel()] += G.ravel()
        A = sp.csc_matrix((vals, (rows, cols)), shape=(n, n)) + sp.diags(diag)
        self.lu = sla.splu(A.tocsc(), permc_spec="MMD_AT_PLUS_A", options=dict(SymmetricMode=True))

    def solve(self, Q, t_sinks=None):
        """Temperature rise (K) of every cell, (L, ny, nx), for heat Q (W) per cell, same shape; Q may
        carry a trailing axis of patterns. t_sinks: each sink's temperature rise above ambient (K)."""
        Q = np.array(Q, float)
        for (l, G), t in zip(self.sinks, t_sinks or ()):
            if t:
                Q[l] += (G * t).reshape(G.shape + (1,) * (Q.ndim - 3))
        flat = Q.reshape(int(np.prod(self.shape)), -1)
        return self.lu.solve(flat).reshape(Q.shape)
