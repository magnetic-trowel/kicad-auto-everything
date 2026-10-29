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


Z_CABLE = 150.0         # ohm, a cable's common-mode impedance (as kae.excite.observe's CISPR line assumes)


def world(b, bm, log=print):
    """{net: capacitance to the world (F)}: every conductor at 1 V at once, so each net's charge is its
    Maxwell row sum (no cancellation of mutual terms)."""
    from kae.em.static import Electrostatic
    st, zs = stack_of(bm, b.stackup)
    es = Electrostatic(bm.m, st, zs)
    m = bm.m
    idx = np.nonzero(m.lab >= 0)
    t0 = np.array([es._t00(l) for l in range(es.L)])
    q, its = es._cg(np.ones(len(idx[0])), idx, t0, 1e-6, 2000)
    Q = np.zeros(m.lab.shape)
    Q[idx] = q
    out = {n: float(Q[m.lab == k].sum()) for k, n in enumerate(m.nets) if (m.lab == k).any()}
    log(f"capacitive: capacitance to the world of {len(out)} nets (CG {its}): "
        + ", ".join(f"{n} {c * 1e12:.2f} pF" for n, c in sorted(out.items(), key=lambda kv: -kv[1])[:4]))
    return out


def add_world(bd, cw):
    """The board's capacitances to the world as capacitors from each net's pad to a "world" node, and
    each connector's cable as Z_CABLE from the world to the connector's ground pad. Returns the
    common-mode observers (the voltage across each cable's impedance, against the CISPR line)."""
    from .observe import TOL, Observer
    c = bd.circuit
    for n, C in cw.items():
        pa = _pad(bd, n)
        if pa is None or C < MIN_C:
            continue
        c.z(f"cw:{n}", n, "world", (lambda w, C=C: 1 / (1j * w * C)), pa, None, KIND)
    obs = []
    for net in sorted(bd.grounds):
        for tok in bd.pads_of.get(net, []):
            ref = tok.rsplit(".", 1)[0]
            if bd.part_kind.get(ref, ("",))[0] != "connector" or any(o.meta.get("ref") == ref for o in obs):
                continue
            c.z(f"cable:{ref}", "world", net, (lambda w: Z_CABLE + 0j), None, tok, KIND)
            obs.append(Observer(f"cm_cap:{ref}", "cm", "world", net, None, tok, 0.0,
                                f"capacitive common mode on {ref}'s cable: {TOL['cm'][1]}", "standard", dict(ref=ref)))
    return obs
