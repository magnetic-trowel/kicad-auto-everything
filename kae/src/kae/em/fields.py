# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Price fields: what a new piece of copper would couple to, everywhere on the board.

After a field solve of an excitation (kae.em.solve.potentials), its branch currents I fill every
filament of the existing copper, return currents in the planes included. The flux a new x- or
y-directed bar would link at any cell of any layer is the partial-inductance operator applied to
I and read without the copper mask:

    Phi[layer, o](j, i) = sum_s K_{r(layer), s} * I_s     (V s per A of the excitation)

One FFT product per excitation and layer. A router adding a bar at (layer, o, j, i) that carries
current i_k of pattern k changes the copper's bilinear form J_k^T Z J_s by jw i_k Phi_s there
(plus the symmetric term with Phi_k), the mutual part of its cost. Its self part (the new copper
with its own return in the reference below) is local and closed-form (kae.em.t1).
"""
from __future__ import annotations

import numpy as np
import scipy.fft as sfft

from .solve import WORKERS, _kmul


def flux(op, I, layers=None):
    """{(layer index, 'x'|'y'): complex (ny, nx)} flux per unit excitation at each layer's mid-plane.
    I: branch currents of op.net (from a potentials solve: info['x'][:n_br])."""
    net = op.net
    m = net.m
    layers = range(len(m.layers)) if layers is None else layers
    out = {}
    for o in ("x", "y"):
        S, slot, Kh = op._index()[o]
        f = net.fil[o]
        a0 = net.off[o]
        n = len(f["a"])
        used = list(op.used[o])
        G = np.zeros((2, S, op.Ny, op.Nx))
        if n:
            seg = I[a0:a0 + n]
            G[0, slot, f["j"], f["i"]] = seg.real
            G[1, slot, f["j"], f["i"]] = seg.imag
        X = sfft.rfft2(G, workers=WORKERS)
        sh = X.shape
        Y = _kmul(Kh, np.ascontiguousarray(X.reshape(2, S, -1))).reshape(sh)
        Y = sfft.irfft2(Y, s=(op.Ny, op.Nx), workers=WORKERS)[:, :, :m.ny, :m.nx]
        for l in layers:
            subs = [s for s in net.sub_of[l] if s in used]
            if not subs:
                continue
            k = used.index(subs[len(subs) // 2])
            out[(l, o)] = Y[0, k] + 1j * Y[1, k]
    return out
