# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where the board's power turns into heat, and how hot each part gets (kae.em.thermal).

Heat, per corner of the ledger (the DC band's operating point, kae.excite.dc):

    copper       I^2 R of every bar of the DC flow, half to each of its two cells; a lumped part's own
                 DC loss (an inductor's winding) at its pads
    linear feed  (V_in - V_out) I at the regulator's pads (LDO, charger, load switch, series diode)
    switching    (1/eta - 1) P_out at the regulator's pads (no cell model)
    cell         switch conduction I_L^2 R_on D, switching V I_L (t_i + t_v) f_sw at the controller's
                 pads; the rectifier's V_f I_out at its pads
    load         V I of every load at its pads (an export through a connector leaves the board)
    ac           each part's loss from the switching harmonics (kae.excite.spectrum), when given

Each part's junction is its pads' mean temperature plus theta_jb P (a class prior by pin count); its
bound is its class's rating above ambient. Ambient, the surface's cooling and theta_jb are flagged
priors in the ledger; the intent file can state them.
"""
from __future__ import annotations

import numpy as np

from .beliefs import Param, corners

T_MAX = {"ic": 125.0, "module": 85.0, "diode": 125.0, "transistor": 125.0, "inductor": 125.0,
         "capacitor": 105.0, "resistor": 125.0, "ferrite": 125.0, "led": 85.0, "connector": 85.0}
V_F = (0.3, 0.4, 0.5)           # V, a small Schottky's forward drop (lo, typ, hi)
R_ON = (0.03, 0.1, 0.3)         # ohm, an integrated switch's on-resistance without a datasheet value


def _theta_jb(npins):
    """(typ, lo, hi) K/W junction to board by package size."""
    return (60.0, 30.0, 120.0) if npins <= 8 else (20.0, 10.0, 40.0)


def params(bd, dcp, P, intent=None):
    """The heat band's own parameters: ambient, surface cooling, rectifier drops, switches' R_on, every
    dissipating part's theta_jb."""
    from .beliefs import intent_value
    out = []
    iv = intent_value(intent, "requirements", "thermal", "T_amb_C")
    out.append(Param("heat", "T_amb_C", *(iv or (25.0, 25.0, 50.0)), "C", "intent" if iv else "prior",
                     "ambient air temperature" + ("" if iv else " (unknown: 25-50 C)")))
    out.append(Param("heat", "h_W_m2K", 12.0, 8.0, 20.0, "W/m^2/K", "prior",
                     "still-air cooling of the board's faces, convection plus radiation"))
    hot = {ld["ref"] for ld in dcp.loads if bd.part_kind.get(ld["ref"], ("",))[0] != "connector"}
    for f in dcp.feeds.values():
        hot |= {f["cell"]["ctrl"], f["cell"]["rect"]} if f["kind"] == "cell" else ({f["ref"]} if f["kind"] in ("linear", "switching") else set())
    for ref in sorted(r for r in hot if r):
        npins = sum(1 for t in bd.net_of if t.rsplit(".", 1)[0] == ref)
        typ, lo, hi = _theta_jb(npins)
        out.append(Param(f"heat:{ref}", "theta_jb", typ, lo, hi, "K/W", "prior",
                         f"junction to board by package size ({npins} pins; class range), no datasheet value"))
    for f in dcp.feeds.values():
        if f["kind"] != "cell":
            continue
        c = f["cell"]
        if c["rect"]:
            out.append(Param(f"heat:{c['rect']}", "V_f_V", V_F[1], V_F[0], V_F[2], "V", "prior",
                             "rectifier forward drop (small Schottky class range)"))
        ron = (P.get(c["src"]) or {}).get("R_on")
        out.append(Param(f"heat:{c['ctrl']}", "R_on_ohm", ron.typ, ron.lo, ron.hi, "ohm", ron.source, ron.basis) if ron else
                   Param(f"heat:{c['ctrl']}", "R_on_ohm", R_ON[1], R_ON[0], R_ON[2], "ohm", "prior",
                         "switch on-resistance (integrated switch class range); no datasheet value"))
    return out


def part_heat(bd, dcp, cv, val, inj, ac_parts=None):
    """{part ref: W} at one corner. cv: the DC band's corner (kae.excite.dc); val: {(subject, name): value}
    of the heat parameters; inj: the DC flow's injections at this corner."""
    from . import dc as DC
    out = {}

    def add(ref, w):
        if ref and w > 0:
            out[ref] = out.get(ref, 0.0) + w
    xs = DC.load_currents(dcp, cv)
    for ld, x in zip(dcp.loads, xs):
        if (bd.part_kind.get(ld["ref"], ("",))[0]) != "connector":
            add(ld["ref"], x * (dcp.volts.get(ld["rail"]) or 0.0))
    for r, f in dcp.feeds.items():
        if f["kind"] == "cell":
            c = f["cell"]
            v = cv.get(c["src"]) or {}
            IL, D, V = v.get("I_A", 1.0), min(max(v.get("D", 0.5), 0.02), 0.98), v.get("V_V", dcp.volts.get(r) or 5.0)
            I_out = IL * (1 - D) if c["cls"] == "boost" else IL
            ron = val.get((f"heat:{c['ctrl']}", "R_on_ohm"), R_ON[1])
            add(c["ctrl"], IL ** 2 * ron * D + V * IL * (v.get("t_i_s", 3e-9) + v.get("t_v_s", 1e-9)) * v.get("f_sw_Hz", 1e6))
            if c["rect"]:
                add(c["rect"], val.get((f"heat:{c['rect']}", "V_f_V"), V_F[1]) * (I_out if c["cls"] == "boost" else IL * (1 - D)))
            continue
        I_out = sum(inj.get(q, 0.0) for q in f.get("out") or [])
        if I_out <= 0:
            continue
        if f["kind"] == "linear":
            vi, vo = dcp.volts.get(f["rin"]) or 0.0, dcp.volts.get(r) or 0.0
            kind = bd.part_kind.get(f["ref"], ("",))[0]
            drop = val.get((f"heat:{f['ref']}", "V_f_V"), V_F[1]) if kind == "diode" else max(vi - vo, 0.0)
            if kind not in ("inductor", "ferrite", "resistor"):       # those dissipate in the DC copper model
                add(f["ref"], drop * I_out)
        elif f["kind"] == "switching":
            eta = cv.get((f["eta"].subject, "eta"), 0.85)
            add(f["ref"], (1 / eta - 1) * (dcp.volts.get(r) or 0.0) * I_out)
    for ref, w in (ac_parts or {}).items():
        add(ref, w)
    return out


def copper_heat(net, x, shape):
    """Q (L, ny, nx) W: I^2 R of every bar of a DC solution x (amperes in its first n_br entries), half to
    each of its two cells; vias half to each landing."""
    Q = np.zeros(shape)
    I = np.real(x[:net.n_br])
    for o, (dj, di) in (("x", (0, 1)), ("y", (1, 0))):
        f = net.fil[o]
        a0, n = net.off[o], len(f["a"])
        if not n:
            continue
        p = I[a0:a0 + n] ** 2 * net.R[a0:a0 + n]
        lay = np.zeros(n, np.int64)
        for l, subs in enumerate(net.sub_of):
            lay[np.isin(f["s"], subs)] = l
        np.add.at(Q, (lay, f["j"], f["i"]), p / 2)
        np.add.at(Q, (lay, f["j"] + dj, f["i"] + di), p / 2)
    return Q


def evaluate(bm, b, bd, dcp, P, net_dc, op_dc, cps, srcs, n_corners, seed, tot, notes, intent=None, ac_parts=None,
             log=print, ledger=None):
    """Thermal harms per part at every corner, added into the per-corner totals. ac_parts: {ref: [W per
    corner]} from the switching harmonics."""
    import time
    from kae.em import solve as ES
    from kae.em import thermal as TH
    from . import dc as DC
    from . import harm as HA
    t0 = time.time()
    hp = params(bd, dcp, P, intent)
    for p in hp if ledger is not None else []:
        ledger.add(p)
    ncp = n_corners + 3
    hc = corners(hp, n=n_corners, seed=seed + 2)
    own = corners(dcp.params, n=n_corners, seed=seed + 1) if dcp.params else [{} for _ in range(ncp)]
    cvs = []
    for c in range(ncp):
        cv = dict(own[c])
        for s in srcs:
            if s.kind == "cell":
                cv[s.name] = {k[1]: v for k, v in cps[s.name][c].items()}
        cvs.append(cv)
    m = bm.m
    injs = [{q: a for q, a in DC.injections(dcp, cv).items() if q in m.terminals} for cv in cvs]
    res = ES.potentials_many(m, injs, 0.0, net=net_dc, op=op_dc)
    if any(V is None for V, _ in res):
        notes.append("thermal: the DC flow does not close in the copper; temperatures not computed")
        return []
    gaps = list(b.stackup.gaps) if len(b.stackup.gaps) == len(m.layers) - 1 else [1.6 / max(len(m.layers) - 1, 1)] * (len(m.layers) - 1)
    pads_of = {}
    for t, cells in m.terminals.items():
        ref = t.rsplit(".", 1)[0]
        pads_of.setdefault(ref, []).extend(cells)
    U, Tj = {}, {}
    th_cache = {}
    for c in range(ncp):
        val = hc[c]
        h = round(val[("heat", "h_W_m2K")], 3)
        if h not in th_cache:
            th_cache = {h: TH.Thermal(m, gaps, h=h)}             # one factor at a time (memory)
        th = th_cache[h]
        V, info = res[c]
        Q = copper_heat(info["net"], info["x"], m.lab.shape)
        heat = part_heat(bd, dcp, cvs[c], val, injs[c], {k: v[c] for k, v in (ac_parts or {}).items()})
        for ref, w in heat.items():
            cells = pads_of.get(ref)
            if cells:
                for (l, j, i) in cells:
                    Q[l, j, i] += w / len(cells)
        T = th.solve(Q)
        Tamb = val[("heat", "T_amb_C")]
        for ref, w in heat.items():
            cells = pads_of.get(ref)
            if not cells:
                continue
            kind = bd.part_kind.get(ref, ("",))[0]
            Tmax = T_MAX.get(kind, 85.0)
            npins = len({t for t in m.terminals if t.rsplit(".", 1)[0] == ref})
            tj = val.get((f"heat:{ref}", "theta_jb"), _theta_jb(npins)[0])
            dT = float(np.mean([T[l, j, i] for (l, j, i) in cells])) + tj * w
            U.setdefault(ref, [0.0] * ncp)[c] = dT / max(Tmax - Tamb, 1.0)
            Tj.setdefault(ref, [0.0] * ncp)[c] = Tamb + dT
    rows = []
    for ref, us in U.items():
        for c in range(ncp):
            tot[c] += HA.phi(us[c])
        rows.append(dict(observer=f"heat:{ref}", source="dc", kind="heat", u=us[0], u_lo=min(us), u_hi=max(us),
                         T_C=round(Tj[ref][0], 1), T_hi_C=round(max(Tj[ref]), 1),
                         basis=f"junction (pads' mean + theta_jb P) against {T_MAX.get(bd.part_kind.get(ref, ('',))[0], 85.0):g} C"))
    log(f"thermal: {len(U)} dissipating parts, {ncp} corners in {time.time() - t0:.1f}s")
    return rows
