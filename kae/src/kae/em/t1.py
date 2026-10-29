# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tier-1 prices for the router, from one tier-2 solve of each excitation.

A new hop on layer L carrying current i (from pad a toward pad b) over its reference layer R
changes an excitation's bilinear form J_k^T Z J_s by (per unit i):

  mutual  sum over its bars of  Pi = Phi(L) - Phi(R)      the flux of every existing current through
                                                          the loop the hop makes with its return under it
  crossing  phi_R(B) - phi_R(A)  where it crosses a void   the voltage the excitation's currents develop
            of R, from copper cell A to copper cell B      across the gap: the return must detour there

Both come from the excitation's own solve: Phi from kae.em.fields, phi from its node potentials.
The crossing term is written per move as the difference of an extended potential (copper cells
keep phi; void cells take the potential of the nearest copper): along any path it telescopes to
phi(B) - phi(A), however the path threads the void. A void whose two sides are different copper
islands cannot carry the return at all (a split): its moves are reported in `split` and priced by
the caller as blocked or very expensive. Checked against two-port solves in
tools/research/physics/em_t1_check.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from . import fields as EF


@dataclass
class Price:
    """Per routing layer: Px, Py (mutual, per bar step, H per unit current) and phi (extended reference
    potential, H per unit current in the inductive limit: Im part over w), plus the reference layer
    used per cell and the void/split masks."""
    Px: np.ndarray
    Py: np.ndarray
    phi: np.ndarray
    ref: np.ndarray
    void: np.ndarray
    split: np.ndarray


def reference(mesh, layer):
    """Per cell, the nearest other copper layer that has copper there (-1 if none), and the void mask
    of the layer that serves as reference where copper is missing: cells with no copper on the
    layer that is the reference of most of the board."""
    zs = np.array([l.z + l.t / 2 for l in mesh.layers])
    order = [k for k in np.argsort(np.abs(zs - zs[layer])) if k != layer]
    ref = np.full((mesh.ny, mesh.nx), -1, np.int64)
    for k in order[::-1]:
        ref[mesh.lab[k] >= 0] = k
    occ = [(mesh.lab[k] >= 0).sum() for k in order]
    main = order[int(np.argmax(occ))] if order else -1
    return ref, main


def price(mesh, op, I, node, comp, layer, w=1.0):
    """Price maps for routing on `layer`, from one solve of an excitation (branch currents I, node
    potentials per cell `node` mapped through comp). Values are per unit current, as inductances (H)."""
    phi_all = EF.flux(op, I)
    ref, main = reference(mesh, layer)
    Px = phi_all[(layer, "x")].copy()
    Py = phi_all[(layer, "y")].copy()
    if main < 0:
        z = np.zeros_like(Px.real)
        return Price(Px.real, Py.real, z, ref, z.astype(bool), z.astype(bool))
    # subtract the flux at the reference under each cell (main reference where the cell has none)
    r = np.where(ref >= 0, ref, main)
    for k in np.unique(r):
        sel = r == k
        Px[sel] -= phi_all[(int(k), "x")][sel]
        Py[sel] -= phi_all[(int(k), "y")][sel]
    occ = mesh.lab[main] >= 0
    pot = node["phi"][main]
    cmp_ = node["comp"][main]
    # extend the main reference's potential into its voids: nearest copper cell's value
    _, (jj, ii) = ndimage.distance_transform_edt(~occ, return_indices=True)
    ext = pot[jj, ii]
    ext_comp = cmp_[jj, ii]
    void = ~occ
    # a void is a split where its rim touches more than one copper island
    lab, n = ndimage.label(void)
    split = np.zeros_like(void)
    rim = ndimage.binary_dilation(void) & occ
    for v in range(1, n + 1):
        region = lab == v
        touch = np.unique(cmp_[ndimage.binary_dilation(region) & rim])
        if len(touch) > 1:
            split |= region
    # Z = jw Phi on the bars (inductance Re Phi) and the node potentials are jw L (inductance Im phi / w)
    return Price(Px.real, Py.real, ext.imag / w, ref, void, split)


def cell_potentials(sysm, x):
    """{'phi': (layers, ny, nx) complex potential per copper cell (nan elsewhere), 'comp': island ids}."""
    net, m = sysm.net, sysm.net.m
    phi = np.full(m.lab.shape, np.nan, complex)
    comp = np.full(m.lab.shape, -1, np.int64)
    occ = net.node >= 0
    nd = net.node[occ]
    k = sysm.free_idx[nd]
    vals = np.where(k >= 0, x[net.n_br + np.maximum(k, 0)], 0.0) / sysm.kap
    phi[occ] = vals
    comp[occ] = net.comp[nd]
    return dict(phi=phi, comp=comp)


def path_price(pr: Price, cells, pitch):
    """Price (H per unit current squared) of a path given as [(j, i), ...] on the routing layer, its
    current flowing along the path: sum of the mutual steps plus the telescoped crossing term."""
    tot = 0.0
    for (j0, i0), (j1, i1) in zip(cells[:-1], cells[1:]):
        di, dj = i1 - i0, j1 - j0
        tot += 0.5 * (pr.Px[j0, i0] + pr.Px[j1, i1]) * di + 0.5 * (pr.Py[j0, i0] + pr.Py[j1, i1]) * dj
        if pr.void[j0, i0] or pr.void[j1, i1]:
            tot += pr.phi[j1, i1] - pr.phi[j0, i0]
    return tot
