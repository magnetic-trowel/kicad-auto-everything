# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate R4 seed (docs/topics/architecture/physics-frequency-coverage.md): does a hop's price, taken from the
reduced model's basis fields, predict the change of a pair's transfer impedance at every frequency?

An aggressor trace over a plane (optionally slotted under both traces), driven at its near end by a current
source with a switch-node capacitance across it (C_sw), closed at its far end by a capacitor with ESR and
ESL: a series loop that rings with C_sw. A victim at offset d has its two pads present and joined by a
field-free short (an unrouted connection, as in kae.em.pnr); its far pad is tied to the plane, and its port
sits at the near pad. The hop is the victim's trace, which replaces the short, along one of two paths
(straight, or a detour 2 mm further out).

- exact: Z_vs with the trace, and the difference between the two paths, from direct solves.
- basis (kae.em.spectral): a reduced model of the board before the hop; the hop pays, per unit current,
  jw sum_j y_sj(w) (F_j along its path) plus the crossing steps of the basis potentials.
- single band: the same price taken at 10 MHz and continued as a constant inductance, dZ = jw dL(10 MHz).

    python em_r4_check.py [--pitch 0.2] [--d 1.0] [--slot]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "kae" / "src"))

from kae.em import reduce as RD  # noqa: E402
from kae.em import solve as ES  # noqa: E402
from kae.em.mesh import Layer, Mesh  # noqa: E402
from kae.em.spectral import Spectral, path_integrals  # noqa: E402

T, H = 0.035, 0.2
C_SW, ESR, ESL, C_OUT = 200e-12, 0.02, 0.5e-9, 1e-6
SLOT = (14.5, 4.0, 15.5, 26.0)
FREQS = (1e3, 1e4, 1e5, 3e5, 1e6, 3e6, 1e7, 3e7, 6e7, 1e8, 1.3e8, 1.6e8, 2e8, 3e8)


def paths(d):
    """The hop's two candidate centrelines (mm): straight, and a detour 2 mm further out."""
    yv = 10 + d
    return {"straight": [(5.3, yv), (29.7, yv)],
            "detour": [(5.3, yv), (10, yv), (10, yv + 2), (25, yv + 2), (25, yv), (29.7, yv)]}


def board(pitch, d, hop, slot):
    """hop: None (the victim's pads joined by a field-free short) or a centreline (its 0.4 mm trace)."""
    m = Mesh.over(0, 0, 40, 30, pitch, [Layer("F", H + T, T, 2), Layer("B", 0, T, 2)])
    m.rect(1, "GND", 0, 0, 40, 30)
    if slot:
        X, Y = m.centres()
        x0, y0, x1, y1 = SLOT
        m.lab[1][(X > x0) & (X < x1) & (Y > y0) & (Y < y1)] = -1
    m.rect(0, "A", 5, 10 - 0.25, 30, 10 + 0.25)
    yv = 10 + d
    m.rect(0, "V", 5, yv - 0.2, 5.6, yv + 0.2)
    m.rect(0, "V", 29.4, yv - 0.2, 30, yv + 0.2)
    for (x0, y0), (x1, y1) in zip(hop[:-1], hop[1:]) if hop else ():
        m.rect(0, "V", min(x0, x1) - 0.2, min(y0, y1) - 0.2, max(x0, x1) + 0.2, max(y0, y1) + 0.2)
    X, Y = m.centres()

    def mask(x0, x1, y, w):
        return (X > x0) & (X < x1) & (abs(Y - y) < w / 2)
    for nm, lay, mk in (("as", 0, mask(5, 5 + pitch, 10, 0.5)), ("ag", 1, mask(5, 5 + pitch, 10, 0.5)),
                        ("ae", 0, mask(30 - pitch, 30, 10, 0.5)), ("aeg", 1, mask(30 - pitch, 30, 10, 0.5)),
                        ("vs", 0, mask(5, 5.6, yv, 0.4)), ("vg", 1, mask(5, 5.6, yv, 0.4)),
                        ("ve", 0, mask(29.4, 30, yv, 0.4)), ("veg", 1, mask(29.4, 30, yv, 0.4))):
        m.terminal(nm, lay, mask=mk)
    m.part("as", "ag", name="C_sw", zf=lambda w: 1 / (1j * w * C_SW))
    m.part("ae", "aeg", name="C_out", zf=lambda w: ESR + 1j * w * ESL + 1 / (1j * w * C_OUT))
    m.part("ve", "veg", name="tie")
    if not hop:
        m.part("vs", "ve", name="unrouted")
    return m


def cells_of(m, pts, off):
    out = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        n = int(np.ceil(np.hypot(x1 - x0, y1 - y0) / (m.pitch / 4))) + 1
        for t in np.linspace(0, 1, n):
            c = m.cell(x0 + (x1 - x0) * t + off, y0 + (y1 - y0) * t + off)
            if not out or c != out[-1]:
                out.append(c)
    return out


PORTS = [{"as": 1.0, "ag": -1.0}, {"vs": 1.0, "vg": -1.0}]


def direct(m, freqs):
    net = ES.Network(m)
    op = ES.Operator(net)
    md = RD.Reduced(op, PORTS, log=lambda s: None)
    out = []
    for f in freqs:
        sy = ES.System(op, f)
        X, _ = sy.solve_many(md.P, tol=1e-9, maxiter=3000)
        out.append(md.P.T @ (X[md.nb:] / sy.kap))
    return np.array(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pitch", type=float, default=0.2)
    ap.add_argument("--d", type=float, default=1.0)
    ap.add_argument("--slot", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    m = board(a.pitch, a.d, None, a.slot)
    net = ES.Network(m)
    op = ES.Operator(net)
    model = RD.Reduced(op, PORTS, log=lambda s: print(s, flush=True))
    model.build(3e8, fmin=1e3, tol=1e-4, f0=(0.0, 1e7), snap_tol=1e-9)
    bf = Spectral._basis(None, model, net, op, m, None)
    print(f"model order {model.V.shape[1]} from {[round(f / 1e6, 4) for f in model.freqs]} MHz; "
          f"{time.time() - t0:.0f}s", flush=True)
    P = paths(a.d)
    price = {}
    for nm, pts in P.items():
        fl, cr = np.zeros(model.V.shape[1]), np.zeros((2, model.V.shape[1]))
        for off in (-a.pitch / 2 + 1e-6, a.pitch / 2 - 1e-6):        # the trace's two cell rows
            f_, c_ = path_integrals(bf, 0, cells_of(m, pts, off))
            fl, cr = fl + f_ / 2, cr + c_ / 2
        price[nm] = (fl, cr)

    def pred(nm, f):
        y = model.solve(f)[:, 0]          # the aggressor's coefficients; the hop carries 1 A of the victim's pattern
        fl, cr = price[nm]
        return 1j * 2 * np.pi * f * (fl @ y + cr[1] @ y) + cr[0] @ y
    Zpre = direct(m, FREQS)
    Zp = {nm: direct(board(a.pitch, a.d, pts, a.slot), FREQS) for nm, pts in P.items()}
    w10 = 2 * np.pi * 1e7
    print("price / Z_vs with the hop (the hop's price counts its whole coupling: the field-free short's own return "
          "through the plane, the same for every path, is in Z_vs before it); path difference = detour - straight")
    print(f"{'f MHz':>9s} {'|Z_vs| hop':>11s} {'basis/exact':>18s} {'1-band/exact':>18s} | {'|diff| exact':>12s} "
          f"{'basis/exact':>18s} {'1-band/exact':>18s} {'model err':>9s}")
    rows = []
    for k, f in enumerate(FREQS):
        zs = Zp["straight"][k][1, 0]
        dd = Zp["detour"][k][1, 0] - zs
        pb = pred("straight", f)
        ps = 1j * 2 * np.pi * f * pred("straight", 1e7).imag / w10
        db = pred("detour", f) - pb
        ds = 1j * 2 * np.pi * f * (pred("detour", 1e7) - pred("straight", 1e7)).imag / w10
        me = abs(model.Z(f)[1, 0] - Zpre[k][1, 0]) / abs(zs)
        r = [pb / zs, ps / zs, db / dd, ds / dd]
        rows.append((f, r))
        print(f"{f / 1e6:9.3f} {abs(zs):11.3e} " + " ".join(f"{abs(x):7.3f} {np.angle(x, deg=True):+7.1f} deg" for x in r[:2])
              + f" | {abs(dd):12.3e} " + " ".join(f"{abs(x):7.3f} {np.angle(x, deg=True):+7.1f} deg" for x in r[2:])
              + f" {me:9.1e}", flush=True)
    for lo in (1e6, 3e5):
        sel = [r for f, r in rows if f >= lo]
        wb = max(max(abs(x[0] - 1), abs(x[2] - 1)) for x in sel)
        ws = max(max(abs(x[1] - 1), abs(x[3] - 1)) for x in sel)
        print(f"from {lo / 1e6:g} MHz: worst |price/exact - 1|: basis fields {wb:.3f}, single band {ws:.3f}")
    print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
