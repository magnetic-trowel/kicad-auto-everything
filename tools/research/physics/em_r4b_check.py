# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A hop that replaces an unrouted connection, priced from the board before it: which trial currents give the
board after it (stage R4b, docs/topics/architecture/physics-frequency-coverage.md).

The unrouted connection is a part of negligible impedance (branch b). From the board before the hop:
every port's solution x_P, the current I_P^b each drives through b, and the solution x_e of a unit EMF in b
(the loop through b closed by the rest of the board; I_e^b = Y_b, its admittance). After the hop the board
has the hop's copper instead of b. Trial currents for it (all mapped by position; b's current moves onto
the hop's bars):

- x~_P: each port's solution, its current through b carried by the hop (exact KCL);
- x~_e: the loop through b, likewise: the hop with the return the board had (exact at low frequency);
- u_img: the hop with its image return in the plane under it (the high-frequency return).

The Galerkin projection of the full post-hop system onto these is compared with its direct solve, and with
the one-sided identity dZ_vs = I'_v jw Phi_s(hop), Phi_s the raw flux of x_s along the hop.

    python em_r4b_check.py [--pitch 0.25] [--case self|victim] [--slot]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "kae" / "src"))

from kae.em import solve as ES  # noqa: E402
from kae.em.mesh import Layer, Mesh  # noqa: E402

T, H = 0.035, 0.2
C_SW, ESR, ESL, C_OUT = 200e-12, 0.02, 0.5e-9, 1e-6
SLOT = (14.5, 4.0, 15.5, 26.0)
FREQS = (1e3, 1e4, 1e5, 3e5, 1e6, 3e6, 1e7, 3e7, 6e7, 1e8, 1.3e8, 1.6e8, 2e8, 3e8)
Z_SHORT = 1e-6


def board(pitch, d, case, hop, slot):
    """case 'self': the aggressor's trace is the hop (its pads joined by the unrouted connection before);
    'victim': the victim's trace is."""
    m = Mesh.over(0, 0, 40, 30, pitch, [Layer("F", H + T, T, 2), Layer("B", 0, T, 2)])
    m.rect(1, "GND", 0, 0, 40, 30)
    if slot:
        X, Y = m.centres()
        x0, y0, x1, y1 = SLOT
        m.lab[1][(X > x0) & (X < x1) & (Y > y0) & (Y < y1)] = -1
    yv = 10 + d
    for net, y, w, is_hop in (("A", 10, 0.5, case == "self"), ("V", yv, 0.4, case == "victim")):
        m.rect(0, net, 5, y - w / 2, 5.6, y + w / 2)
        m.rect(0, net, 29.4, y - w / 2, 30, y + w / 2)
        if hop or not is_hop:
            m.rect(0, net, 5, y - w / 2, 30, y + w / 2)
    X, Y = m.centres()

    def mask(x0, x1, y, w):
        return (X > x0) & (X < x1) & (abs(Y - y) < w / 2)
    for nm, lay, mk in (("as", 0, mask(5, 5.6, 10, 0.5)), ("ag", 1, mask(5, 5.6, 10, 0.5)),
                        ("ae", 0, mask(29.4, 30, 10, 0.5)), ("aeg", 1, mask(29.4, 30, 10, 0.5)),
                        ("vs", 0, mask(5, 5.6, yv, 0.4)), ("vg", 1, mask(5, 5.6, yv, 0.4)),
                        ("ve", 0, mask(29.4, 30, yv, 0.4)), ("veg", 1, mask(29.4, 30, yv, 0.4))):
        m.terminal(nm, lay, mask=mk)
    m.part("as", "ag", name="C_sw", zf=lambda w: 1 / (1j * w * C_SW))
    m.part("ae", "aeg", name="C_out", zf=lambda w: ESR + 1j * w * ESL + 1 / (1j * w * C_OUT))
    m.part("ve", "veg", name="tie")
    if not hop:
        a, b = ("as", "ae") if case == "self" else ("vs", "ve")
        m.part(a, b, name="unrouted", zf=lambda w: Z_SHORT + 0j)
    return m


PORTS = [{"as": 1.0, "ag": -1.0}, {"vs": 1.0, "vg": -1.0}]


def inj(sy, net, p):
    s = np.zeros(sy.nfree, complex)
    for t, v in p.items():
        k = sy.free_idx[net.term_node[t]]
        if k >= 0:
            s[k] += v
    return s


def carry(net0, sy0, X0, net1, sy1, moved):
    """Vectors (physical units) of net0 on net1 by position: filaments by sublayer and cell, parts by name,
    nodes by a cell of theirs (re-grounded per island). moved: [(row of net0's branch whose current moves,
    [(layer, o, j, i, share)] the bars it moves onto)]."""
    m = net1.m
    out = np.zeros((net1.n_br + sy1.nfree, X0.shape[1]), complex)
    for o in ("x", "y"):
        fo, fn = net0.fil[o], net1.fil[o]
        key = lambda f: (f["s"] * m.ny + f["j"]) * m.nx + f["i"]
        lut = -np.ones(len(net0.subs) * m.ny * m.nx, np.int64)
        lut[key(fo)] = np.arange(len(fo["a"]))
        hit = lut[key(fn)]
        ok = hit >= 0
        out[net1.off[o] + np.nonzero(ok)[0]] = X0[net0.off[o] + hit[ok]]
    names = {q.name: k for k, (_, _, q) in enumerate(net0.lump)}
    for k, (_, _, q) in enumerate(net1.lump):
        if q.name in names:
            out[net1.off["l"] + k] = X0[net0.off["l"] + names[q.name]]
    occ = net1.node >= 0
    cells = np.argwhere(occ)
    nd = net1.node[occ]
    nn, first = np.unique(nd, return_index=True)
    on = net0.node[tuple(cells[first].T)]
    of = np.where(on >= 0, sy0.free_idx[np.maximum(on, 0)], -1)
    val = np.zeros((net1.n_nodes, X0.shape[1]), complex)
    val[nn[of >= 0]] = X0[net0.n_br + of[of >= 0]]
    for g in np.nonzero(sy1.free_idx < 0)[0]:
        val[net1.comp == net1.comp[g]] -= val[g]
    free = sy1.free_idx >= 0
    out[net1.n_br + sy1.free_idx[free]] = val[free]
    for row, bars in moved:
        out += np.outer(bar_vector(net1, sy1, bars), X0[row])
    return out


def bar_vector(net, sy, bars, face=None):
    """face: put each bar's current on the one sublayer nearest that height (mm), not split over all."""
    v = np.zeros(net.n_br + sy.nfree, complex)
    for o in ("x", "y"):
        fn = net.fil[o]
        lut = {(int(s_), int(j), int(i)): k for k, (s_, j, i) in enumerate(zip(fn["s"], fn["j"], fn["i"]))}
        for (l, oo, j, i, c) in bars:
            if oo != o:
                continue
            subs = net.sub_of[l]
            if face is not None:
                subs = [min(subs, key=lambda q: abs(net.subs[q][0] + net.subs[q][1] / 2 - face))]
            for s_ in subs:
                k = lut.get((int(s_), j, i))
                if k is not None:
                    v[net.off[o] + k] += c / len(subs)
    return v


def hop_bars(m, y, rows, layer, sign=1.0, spread=None):
    """The hop's x-bars from x = 5.3 to 29.7 at height y over `rows` cell rows (its unit current split); with
    spread = (h, w), a return in the plane: the current density of a strip of width w at height h over a wide
    plane, (1 / pi) h / (dy^2 + h^2) convolved over the strip, to 6 h + w / 2 either side."""
    i0, i1 = m.cell(5.3, y)[1], m.cell(29.7, y)[1]
    if spread is None:
        js = [j for j in range(m.ny) if abs((m.y0 + (j + 0.5) * m.pitch) - y) < rows * m.pitch / 2]
        wt = {j: 1.0 / len(js) for j in js}
    else:
        h, w = spread
        yc = m.y0 + (np.arange(m.ny) + 0.5) * m.pitch
        sel = np.abs(yc - y) <= 6 * h + w / 2
        k = (np.arctan((yc - y + w / 2) / h) - np.arctan((yc - y - w / 2) / h)) / (np.pi * w)
        k = np.where(sel, k, 0.0)
        wt = {int(j): float(k[j] / k.sum()) for j in np.nonzero(sel)[0]}
    return [(layer, "x", j, i, sign * c) for j, c in wt.items() for i in range(i0, i1)]


def flux_along(op, I, bars):
    """Raw flux (V s per A) of branch currents I through the bars [(layer, o, j, i, share)]: the partial
    mutual inductance of the hop's unit current with I."""
    from kae.em import fields as EF
    fl = EF.flux(op, I.astype(complex), layers=sorted({l for l, *_ in bars}))
    return sum(c * fl[(l, o)][j, i] for (l, o, j, i, c) in bars)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pitch", type=float, default=0.25)
    ap.add_argument("--d", type=float, default=1.0)
    ap.add_argument("--case", default="self")
    ap.add_argument("--slot", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    m0, m1 = board(a.pitch, a.d, a.case, False, a.slot), board(a.pitch, a.d, a.case, True, a.slot)
    n0, n1 = ES.Network(m0), ES.Network(m1)
    op0, op1 = ES.Operator(n0), ES.Operator(n1)
    b = n0.off["l"] + next(k for k, (_, _, q) in enumerate(n0.lump) if q.name == "unrouted")
    y = 10.0 if a.case == "self" else 10 + a.d
    w = 0.5 if a.case == "self" else 0.4
    rows = int(round(w / a.pitch))
    hb = hop_bars(m1, y, rows, 0)
    img = hop_bars(m1, y, rows, 1, -1.0, spread=(H + T, w))
    imgs = [img, hop_bars(m1, y, rows, 1, -1.0, spread=(0.5 * (H + T), w)), hop_bars(m1, y, rows, 1, -1.0, spread=(2 * (H + T), w))]
    # the router's own route (kae.em.hopport on the reduced model of the board before the hop)
    from kae.em import reduce as RD
    from kae.em import hopport as HP
    from kae.em.spectral import Spectral
    md = RD.Reduced(op0, PORTS, log=lambda s: None, emf=[b])
    md.build(3e8, fmin=1e3, tol=1e-4, f0=(0.0, 1e7), snap_tol=1e-9)
    bf = Spectral._basis(None, md, n0, op0, m0, None)
    bars, ln = HP.path_bars(m0, [("F", (5.3, y), (29.7, y))], ["F", "B"], w)
    loop = HP.Loop(op0, m0, bf, bars, ln, w, None, h_ref=H)
    kb = next(k for k, (_, _, q) in enumerate(n0.lump) if q.name == "unrouted")
    Gc = md.G_L + md.G_Lc

    def router(f):
        Ya = md.solve(f)
        ye = Ya[:, 2]
        Yb = md.Vl[kb] @ ye
        I = md.Vl[kb] @ Ya[:, :2]
        YZrr = (ye @ md.G_R @ ye + 2j * np.pi * f * (ye @ Gc @ ye)) / Yb
        _, dZ = loop.impedance(np.array([2 * np.pi * f]), ye[None], np.array([Yb]), np.array([YZrr]))
        kap = 1 / (1 + Yb * dZ[0])
        so = I / Yb if abs(Yb) > 1e-9 else np.zeros(2)
        yo = Ya[:, :2] - np.outer(ye, so)
        Po = loop.rh @ yo
        jw = 2j * np.pi * f
        out = np.zeros((2, 2), complex)
        for k in range(2):
            for j in range(2):
                out[k, j] = kap * (I[k] * I[j] * dZ[0] + jw * (I[k] * Po[j] + I[j] * Po[k])) - Yb * kap * (jw * Po[k]) * (jw * Po[j])
        return out
    print(f"case {a.case}{' slot' if a.slot else ''}: dZ = Z after the hop - Z before; ratios model / direct "
          f"(magnitude, phase)", flush=True)
    print(f"{'f MHz':>9s} {'pair':>4s} {'|dZ| direct':>12s} {'kae.em.hopport':>16s} {'stationary':>16s} {'image return':>16s} {'P+e+img':>16s}")
    alpha_log = []
    for f in FREQS:
        s0 = ES.System(op0, f)
        S = np.stack([inj(s0, n0, p) for p in PORTS] + [np.zeros(s0.nfree)], 1)
        E = np.zeros((n0.n_br, 3))
        E[b, 2] = 1.0
        X, _ = s0.solve_many(S, tol=1e-10, maxiter=4000, E=E)
        X = np.concatenate([X[:n0.n_br], X[n0.n_br:] / s0.kap])
        Z0 = np.array([[inj(s0, n0, pk) @ X[n0.n_br:, j] for j in range(2)] for pk in PORTS])
        s1 = ES.System(op1, f)
        S1 = np.stack([inj(s1, n1, p) for p in PORTS], 1)
        X1, _ = s1.solve_many(S1, tol=1e-10, maxiter=4000)
        Z1 = S1.T @ (X1[n1.n_br:] / s1.kap)
        V = carry(n0, s0, X, n1, s1, [(b, hb)])
        u_img = bar_vector(n1, s1, hb + img)[:, None]
        res = {}
        for nm, cols in (("P+e+img", [0, 1, 2, 3]), ("P+e", [0, 1, 2]), ("P+img", [0, 1, 3]), ("P only", [0, 1])):
            W = np.concatenate([V, u_img], 1)[:, cols]
            Ws = np.concatenate([W[:n1.n_br], W[n1.n_br:] * s1.kap])          # the solver's scaled variables
            Ar = Ws.T @ s1.matvec(Ws)
            Br = Ws.T @ np.concatenate([np.zeros((n1.n_br, 2)), -S1])
            Yr = np.linalg.solve(Ar, Br)
            res[nm] = (Br.T @ Yr) * (-1 / s1.kap)                            # port impedances
        # the compensation model (kae.em.spectral): model quantities of the board before the hop only, plus the
        # hop's own loop with its image return
        jw = 2j * np.pi * f
        I, Yb = X[b, :2], X[b, 2]
        Phi = np.array([flux_along(op0, X[:n0.n_br, c], hb) for c in range(3)])          # raw, per unit
        PhiO = Phi[:2] - I * Phi[2] / Yb                     # the other currents' (the open board's) flux
        uI = u_img[:n1.n_br, 0]
        Z_T1 = uI @ (s1.matvec(np.concatenate([uI, np.zeros(s1.nfree)]))[:n1.n_br] / s1.kap)
        r = X[:n0.n_br, 2].copy()
        r[n0.off["l"]:] = 0.0
        YZr = r @ (s0.matvec(np.concatenate([r, np.zeros(s0.nfree)]))[:n0.n_br] / s0.kap) / Yb      # Y Z_r
        YdZ = Yb * Z_T1 - YZr
        kap = 1 / (1 + YdZ)
        M1 = np.zeros((2, 2), complex)
        for k in range(2):
            for j in range(2):
                M1[k, j] = kap * (I[k] * I[j] * (Z_T1 - YZr / Yb) + jw * (I[k] * PhiO[j] + I[j] * PhiO[k])) \
                    - Yb * kap * (jw * PhiO[k]) * (jw * PhiO[j])
        res["M1"] = Z0 + M1
        # the return the hop's loop takes: stationary over r (the board's own, as before the hop) and the image
        rp = carry(n0, s0, (X[:, 2:3] / Yb), n1, s1, [])[:, 0]
        rp[n1.off["l"]:] = 0.0
        rp[n1.n_br:] = 0.0
        hops = [bar_vector(n1, s1, hb)[:n1.n_br], bar_vector(n1, s1, hb, face=H)[:n1.n_br]]
        rets = [rp[:n1.n_br]] + [bar_vector(n1, s1, g)[:n1.n_br] for g in imgs]
        vecs = hops + rets
        ZZ = np.array([[u @ (s1.matvec(np.concatenate([v, np.zeros(s1.nfree)]))[:n1.n_br] / s1.kap) for v in vecs] for u in vecs])
        # the loop sum ga_i hop_i + sum be_j ret_j with sum ga = sum be = 1: stationary (two multipliers)
        nh, nv = len(hops), len(vecs)
        K = np.zeros((nv + 2, nv + 2), complex)
        K[:nv, :nv] = ZZ
        K[:nh, nv] = K[nv, :nh] = 1.0
        K[nh:nv, nv + 1] = K[nv + 1, nh:nv] = 1.0
        w = np.linalg.solve(K, np.r_[np.zeros(nv), 1.0, 1.0])[:nv]
        al = w[nh]
        Zl = w @ ZZ @ w
        Zr = ZZ[nh, nh]
        dZl = Zl - Zr
        kap2 = 1 / (1 + Yb * dZl)
        M2 = np.zeros((2, 2), complex)
        for k in range(2):
            for j in range(2):
                M2[k, j] = kap2 * (I[k] * I[j] * dZl + jw * (I[k] * PhiO[j] + I[j] * PhiO[k])) \
                    - Yb * kap2 * (jw * PhiO[k]) * (jw * PhiO[j])
        res["M2"] = Z0 + M2
        res["router"] = Z0 + router(f)
        alpha_log.append((f, al))
        for k, j in ((0, 0), (1, 0)):
            dz = Z1[k, j] - Z0[k, j]
            line = f"{f / 1e6:9.3f} {'ss' if k == 0 else 'vs':>4s} {abs(dz):12.3e} "
            for nm in ("router", "M2", "M1", "P+e+img"):
                r = (res[nm][k, j] - Z0[k, j]) / dz
                line += f"{abs(r):7.3f} {np.angle(r, deg=True):+7.1f}d "
            print(line, flush=True)
    print("share of the old return in the hop's loop:", ", ".join(f"{f / 1e6:g} MHz {abs(x):.2f}" for f, x in alpha_log))
    print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
