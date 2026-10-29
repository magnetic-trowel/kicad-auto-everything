# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capacitive coupling as parts of the board's circuit (stage E2 of
docs/topics/architecture/physics-frequency-coverage.md).

The nets that swing fast (aggressors: every commutation cell's switch node, every clock) are held at
1 V in turn, with every other copper at 0 V, in the board's own copper and stackup (kae.em.static):
the charge induced on each other net is its Maxwell capacitance to the aggressor. Each coupling above
MIN_C becomes a capacitor in the circuit (kind "Cm", between the nets' IC pads), so the copper
co-simulation, the reduced model and every harm carry it like any other part. It is the layout's
own parasitic: an ideal-copper reference leaves it out (Circuit.solve(skip=("Cm",))).

Permittivities are the stackup's (Stackup.er); a board without one is FR4, 4.5.
"""
from __future__ import annotations

import time

import numpy as np

MIN_C = 10e-15          # F: couplings below are left out
KIND = "Cm"


def stack_of(bm, stackup):
    """(kae.em.static.Stack, sheet height (m) of each mesh layer): zero-thickness sheets at the dielectric
    interfaces, the gaps' permittivities between them."""
    from kae.em.static import Stack
    names = [l.name for l in bm.m.layers]
    order = list(stackup.copper)                     # top to bottom
    z, zs = 0.0, {}
    for k in range(len(order) - 1, -1, -1):          # bottom up
        zs[order[k]] = z
        if k > 0:
            z += stackup.gaps[k - 1] * 1e-3
    zif = sorted(zs.values())
    eps = [float(e) for e in reversed(list(stackup.er))]      # bottom gap first
    return Stack(zif, eps), [zs[n] for n in names]


def aggressors(bd, brief, srcs):
    """{net: why}: switch nodes of commutation cells and clock nets."""
    out = {}
    for st in brief.get("structures") or []:
        if st.get("kind") == "commutation_cell" and st.get("sw"):
            out[st["sw"]] = f"switch node of {st['id']}"
    for s in srcs:
        if s.kind == "clock" and s.meta.get("net"):
            out[s.meta["net"]] = f"clock {s.name}"
    return out


def _pad(bd, net):
    """The net's first pad on an IC (where a coupling acts on a circuit), else its first pad."""
    pads = bd.pads_of.get(net, [])
    return next((q for q in pads if q.rsplit(".", 1)[0] in bd.ic_nodes), pads[0] if pads else None)


def couplings(b, bm, bd, brief, srcs, log=print):
    """[(aggressor net, other net, C (F))] above MIN_C, and {aggressor: capacitance to the world (F)}."""
    from kae.em.static import Electrostatic
    t0 = time.time()
    agg = {n: w for n, w in aggressors(bd, brief, srcs).items() if n in bm.m.nets}
    if not agg:
        return [], {}
    st, zs = stack_of(bm, b.stackup)
    es = Electrostatic(bm.m, st, zs)
    cols, its = es.capacitance(sorted(agg))
    out, world = [], {}
    for a, col in cols.items():
        world[a] = sum(col.values())                 # the Maxwell row sum: to infinity
        for n, q in col.items():
            if n != a and -q > MIN_C:
                out.append((a, n, -q))
    log(f"capacitive: {len(agg)} aggressor nets, {len(out)} couplings above {MIN_C * 1e15:.0f} fF "
        f"({'stackup from the file' if b.stackup.source == 'file' else 'default stackup, FR4'}), "
        f"CG {its} in {time.time() - t0:.1f}s")
    return out, world


def add_to_circuit(bd, coupl):
    """Each coupling as a capacitor of kind "Cm" in bd.circuit between the nets' IC pads. Returns the
    number added."""
    c, k = bd.circuit, 0
    for a, n, C in coupl:
        pa, pb = _pad(bd, a), _pad(bd, n)
        if pa is None or pb is None:
            continue
        c.z(f"cm:{a}~{n}", a, n, (lambda w, C=C: 1 / (1j * w * C)), pa, pb, KIND)
        k += 1
    return k
