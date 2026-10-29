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


def ref_copper(mesh, k, ref_ids=None):
    """Cells of layer k that can carry a return: copper of the reference nets (ref_ids, the board's
    grounds), or any copper when ref_ids is None. Another net's track is not a return path."""
    lab = mesh.lab[k]
    return (lab >= 0) if ref_ids is None else np.isin(lab, list(ref_ids))


def reference(mesh, layer, ref_ids=None):
    """Per cell, the nearest other layer with reference copper there (-1 if none), and the main
    reference layer (the one with the most reference copper)."""
    zs = np.array([l.z + l.t / 2 for l in mesh.layers])
    order = [k for k in np.argsort(np.abs(zs - zs[layer])) if k != layer]
    ref = np.full((mesh.ny, mesh.nx), -1, np.int64)
    for k in order[::-1]:
        ref[ref_copper(mesh, k, ref_ids)] = k
    occ = [ref_copper(mesh, k, ref_ids).sum() for k in order]
    main = order[int(np.argmax(occ))] if order and max(occ) > 0 else -1
    return ref, main


def references(mesh, layer, ref_ids=None):
    """Per cell, the nearest layer with return copper above (higher z) and below (-1 if none), the
    dielectric gap to each (mm, inf if none), and the share of a track's return each carries: a
    track between two planes returns on them in inverse proportion to its distance from each (the
    charge division of a stripline, exact for TEM between wide planes)."""
    zs = np.array([l.z + l.t / 2 for l in mesh.layers])
    t = np.array([l.t for l in mesh.layers])
    out = {}
    for side, sel in (("up", lambda k: zs[k] > zs[layer]), ("dn", lambda k: zs[k] < zs[layer])):
        ks = sorted([k for k in range(len(zs)) if sel(k)], key=lambda k: -abs(zs[k] - zs[layer]))
        ref = np.full((mesh.ny, mesh.nx), -1, np.int64)
        for k in ks:                                  # far first, near overwrites
            ref[ref_copper(mesh, k, ref_ids)] = k
        gap = np.where(ref >= 0, np.abs(zs[np.maximum(ref, 0)] - zs[layer]) - (t[np.maximum(ref, 0)] + t[layer]) / 2,
                       np.inf)
        out[side] = (ref, np.maximum(gap, 1e-3))
    hu, hd = out["up"][1], out["dn"][1]
    a_up = np.where(np.isfinite(hu), np.where(np.isfinite(hd), hd / (hu + hd), 1.0), 0.0)
    return out["up"][0], out["dn"][0], hu, hd, a_up, 1.0 - a_up


def main_plane(mesh, layer, side, ref_ids=None):
    """The layer above (side 'up') or below ('dn') with the most return copper: the plane whose voids
    are crossings for this routing layer on that side; -1 if none."""
    zs = np.array([l.z + l.t / 2 for l in mesh.layers])
    ks = [k for k in range(len(zs)) if (zs[k] > zs[layer] if side == "up" else zs[k] < zs[layer])]
    if not ks:
        return -1
    occ = [ref_copper(mesh, k, ref_ids).sum() for k in ks]
    if max(occ) == 0:
        return -1
    # the nearest plane that holds at least half as much return copper as the best one
    best = max(occ)
    near = sorted(ks, key=lambda k: abs(zs[k] - zs[layer]))
    return next(k for k in near if ref_copper(mesh, k, ref_ids).sum() >= 0.5 * best)


def _plane_terms(mesh, node, k, ref_ids, w):
    """Extended potential (H per unit current) of plane k into its voids, its void mask (voids that
    one return island surrounds) and its split mask (voids between islands)."""
    occ = ref_copper(mesh, k, ref_ids)
    pot = node["phi"][k]
    cmp_ = node["comp"][k]
    _, (jj, ii) = ndimage.distance_transform_edt(~occ, return_indices=True)
    ext = pot[jj, ii]
    void = ~occ
    split = _splits(void, occ, cmp_)
    ext = np.where(split, 0.0, ext)
    return np.nan_to_num(ext.imag / w), void & ~split, split


def _splits(void, occ, cmp_):
    """Void regions whose rim touches more than one copper island (one pass over the four neighbour
    shifts, not one dilation per region)."""
    lab, n = ndimage.label(void)
    if n == 0:
        return np.zeros_like(void)
    pairs = []
    for dj, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        a = np.roll(lab, (dj, di), axis=(0, 1))
        c = cmp_
        m = (a > 0) & occ & (c >= 0)
        pairs.append(np.stack([a[m], c[m]], axis=1))
    pr = np.unique(np.concatenate(pairs), axis=0)
    cnt = np.bincount(pr[:, 0], minlength=n + 1)
    return np.isin(lab, np.nonzero(cnt > 1)[0]) & void


def price(mesh, op, I, node, comp, layer, w=1.0, ref_ids=None, phi_all=None):
    """Price maps for routing on `layer`, from one solve of an excitation (branch currents I, node
    potentials per cell `node`). Values are per unit current, as inductances (H). The return of a
    new track divides between the return planes above and below (`references`); its loop links the
    flux at the track minus the share-weighted flux at each plane, and it crosses each plane's voids
    with that share of the potential difference there. ref_ids: the net ids whose copper carries
    returns (grounds and decoupled rails); other nets' copper is never differenced."""
    phi_all = EF.flux(op, I) if phi_all is None else phi_all
    up, dn, hu, hd, a_up, a_dn = references(mesh, layer, ref_ids)
    Px = phi_all[(layer, "x")].copy()
    Py = phi_all[(layer, "y")].copy()
    for ref, a in ((up, a_up), (dn, a_dn)):
        for k in np.unique(ref[ref >= 0]):
            sel = ref == k
            Px[sel] -= a[sel] * phi_all[(int(k), "x")][sel]
            Py[sel] -= a[sel] * phi_all[(int(k), "y")][sel]
    terms = {}
    for side, a in (("up", a_up), ("dn", a_dn)):
        k = main_plane(mesh, layer, side, ref_ids)
        if k >= 0:
            ext, void, split = _plane_terms(mesh, node, k, ref_ids, w)
            # the share is the one the plane would carry with no void: the median over its copper
            share = float(np.median(a[ref_copper(mesh, k, ref_ids)])) if ref_copper(mesh, k, ref_ids).any() else 0.0
            terms[side] = (share * ext, void, split)
    z = np.zeros((mesh.ny, mesh.nx))
    f = np.zeros((mesh.ny, mesh.nx), bool)
    pu, vu, su = terms.get("up", (z, f, f))
    pd, vd, sd = terms.get("dn", (z, f, f))
    pr = Price(Px.real, Py.real, pd, dn, vd, sd | su)
    pr.phi2, pr.void2 = pu, vu
    pr.h_up, pr.h_dn = hu, hd
    # transfer potential: where a track's return moves between planes each plane's share pays that
    # plane's voltage there. psi = sum_k a_k phi_k over the planes the track's return uses; a via pays
    # psi(after) - psi(before) (the shares sum to one, so no reference plane enters), and an end pays
    # psi - phi_T, T being the plane its terminal's return enters (`end_plane`)
    psi = np.zeros((mesh.ny, mesh.nx))
    pr.ext = {}
    for side, a in (("up", a_up), ("dn", a_dn)):
        k = main_plane(mesh, layer, side, ref_ids)
        if k >= 0:
            e = np.nan_to_num(_extend(mesh, node, k, ref_ids).imag / w)
            pr.ext[k] = e
            psi += a * e
    for k in range(len(mesh.layers)):
        if k not in pr.ext and ref_copper(mesh, k, ref_ids).any():
            pr.ext[k] = np.nan_to_num(_extend(mesh, node, k, ref_ids).imag / w)
    pr.psi = psi
    return pr


def end_plane(mesh, pad_layer, ref_ids=None):
    """The plane a terminal's return enters: the nearest layer with return copper to the pad's layer
    (the pad's own layer when it carries return copper itself)."""
    zs = np.array([l.z + l.t / 2 for l in mesh.layers])
    ks = [k for k in np.argsort(np.abs(zs - zs[pad_layer])) if ref_copper(mesh, int(k), ref_ids).any()]
    return int(ks[0]) if ks else -1


def main_return(mesh, ref_ids=None):
    """The layer with the most return copper: where every return ends up (the reference of theta)."""
    occ = [ref_copper(mesh, k, ref_ids).sum() for k in range(len(mesh.layers))]
    return int(np.argmax(occ)) if max(occ) > 0 else -1


def _extend(mesh, node, k, ref_ids):
    """Plane k's potential extended to every cell from its nearest return copper."""
    occ = ref_copper(mesh, k, ref_ids)
    if not occ.any():
        return np.zeros((mesh.ny, mesh.nx), complex)
    _, (jj, ii) = ndimage.distance_transform_edt(~occ, return_indices=True)
    return node["phi"][k][jj, ii]


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


def path_price(pr: Price, cells, pitch, T_start=None, T_end=None):
    """Price (H per unit current squared) of a path given as [(j, i), ...] on the routing layer, its
    current flowing along the path: sum of the mutual steps plus the telescoped crossing terms of the
    planes below and above."""
    psi = getattr(pr, "psi", None)
    tot = 0.0
    if psi is not None and T_start is not None and T_start in pr.ext:
        tot += float(psi[cells[0]] - pr.ext[T_start][cells[0]])
    if psi is not None and T_end is not None and T_end in pr.ext:
        tot -= float(psi[cells[-1]] - pr.ext[T_end][cells[-1]])
    phi2 = getattr(pr, "phi2", None)
    for (j0, i0), (j1, i1) in zip(cells[:-1], cells[1:]):
        di, dj = i1 - i0, j1 - j0
        tot += 0.5 * (pr.Px[j0, i0] + pr.Px[j1, i1]) * di + 0.5 * (pr.Py[j0, i0] + pr.Py[j1, i1]) * dj
        if pr.void[j0, i0] or pr.void[j1, i1]:
            tot += pr.phi[j1, i1] - pr.phi[j0, i0]
        if phi2 is not None and (pr.void2[j0, i0] or pr.void2[j1, i1]):
            tot += phi2[j1, i1] - phi2[j0, i0]
    return tot
