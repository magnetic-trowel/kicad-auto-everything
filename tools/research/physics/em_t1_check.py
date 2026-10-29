# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate G2 seed: does the router's price field predict coupling as the full field solve does?

An aggressor trace over a ground plane (optionally slotted) and a victim trace at offset d. The
exact mutual inductance comes from a two-port solve with both traces present. The prediction uses
only a solve of the aggressor alone: the victim pays the line integral of the price field
Pi = Phi(trace layer) - Phi(reference layer) along its path (a trace and its return under it).

    python em_t1_check.py [--pitch 0.1]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "kae" / "src"))

from kae.em import fields as EF  # noqa: E402
from kae.em import solve as ES  # noqa: E402
from kae.em.mesh import Layer, Mesh  # noqa: E402

T, H = 0.035, 0.2
INF = float("inf")


def board(pitch, d, victim=True, slot=None):
    m = Mesh.over(0, 0, 40, 30, pitch, [Layer("F", H + T, T, 2), Layer("B", 0, T, 2)])
    m.rect(1, "GND", 0, 0, 40, 30)
    if slot:
        X, Y = m.centres()
        x0, y0, x1, y1 = slot
        m.lab[1][(X > x0) & (X < x1) & (Y > y0) & (Y < y1)] = -1
    m.rect(0, "A", 5, 10 - 0.25, 30, 10 + 0.25)
    X, Y = m.centres()

    def ends(net_y, w, name):
        near = (X > 5) & (X < 5 + pitch) & (abs(Y - net_y) < w / 2)
        far = (X > 30 - pitch) & (X < 30) & (abs(Y - net_y) < w / 2)
        m.terminal(f"{name}s", 0, mask=near)
        m.terminal(f"{name}g", 1, mask=near)
        m.terminal(f"{name}e", 0, mask=far)
        m.terminal(f"{name}eg", 1, mask=far)
        m.part(f"{name}e", f"{name}eg")
    ends(10, 0.5, "a")
    m.port("A", "as", "ag")
    if victim:
        m.rect(0, "V", 5, 10 + d - 0.15, 30, 10 + d + 0.15)
        ends(10 + d, 0.3, "v")
        m.port("V", "vs", "vg")
    return m


def predicted(pitch, d, slot, cache={}):
    key = (pitch, slot)
    if key not in cache:
        m = board(pitch, d, victim=False, slot=slot)
        v, info = ES.potentials(m, {"as": 1.0, "ag": -1.0}, INF)
        cache[key] = (m, EF.flux(info["op"], info["I"]))
    m, phi = cache[key]
    X, Y = m.centres()
    row = (abs(Y[:, 0] - (10 + d)) < 0.15)
    cols = (X[0] > 5) & (X[0] < 30 - pitch)
    Pi = phi[(0, "x")] - phi[(1, "x")]
    # the victim's unit current spreads over its rows; each x-bar of one row carries 1/rows of it
    return float(np.sum(Pi[np.ix_(row, cols)].imag if np.iscomplexobj(Pi) else Pi[np.ix_(row, cols)]) / row.sum()) \
        if False else float(np.sum(Pi[np.ix_(row, cols)]).real / row.sum())


def exact(pitch, d, slot):
    m = board(pitch, d, victim=True, slot=slot)
    r = ES.solve(m, [INF])
    return r["L"][0, 0, 1], r["L"][0, 0, 0]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pitch", type=float, default=0.1)
    a = ap.parse_args(argv)
    slots = {"solid": None, "slot under both": (14.5, 4.0, 15.5, 26.0), "slot under victim only": (14.5, 11.0, 15.5, 26.0)}
    print(f"{'plane':24s} {'d mm':>5s} {'M exact pH':>11s} {'M pred pH':>10s} {'ratio':>6s}")
    for name, slot in slots.items():
        for d in (0.6, 1.0, 2.0, 4.0, 8.0):
            Me, La = exact(a.pitch, d, slot)
            Mp = predicted(a.pitch, d, slot)
            print(f"{name:24s} {d:5.1f} {Me * 1e12:11.2f} {Mp * 1e12:10.2f} {Mp / Me:6.3f}", flush=True)


if __name__ == "__main__":
    main()


def gap_term(pitch, d, slot):
    """The slot as a multiport: ports across the gap at the two crossings (plane copper on either side),
    solved with the aggressor's copper present and no victim: the shared-detour mutual (H)."""
    m = board(pitch, d, victim=False, slot=slot)
    X, Y = m.centres()
    x0, y0, x1, y1 = slot

    def edge_cell(xe, y):
        j, i = m.cell(xe, y)
        return j, i
    for name, y in (("a", 10.0), ("v", 10.0 + d)):
        if not (y0 < y < y1):
            return 0.0
        for side, xe in (("L", x0 - pitch / 2), ("R", x1 + pitch / 2)):
            j, i = edge_cell(xe, y)
            mask = np.zeros((m.ny, m.nx), bool)
            mask[j, i] = True
            m.terminal(f"g{name}{side}", 1, mask=mask)
    # the return of a trace running in +x crosses the gap from R to L (it flows opposite to the trace)
    v, info = ES.potentials(m, {"gaR": 1.0, "gaL": -1.0}, INF)
    return float((v["gvR"] - v["gvL"]).imag)


def main_gap(pitch=0.2):
    slot = (14.5, 4.0, 15.5, 26.0)
    print(f"{'d mm':>5s} {'M exact':>9s} {'field':>8s} {'gap':>8s} {'field+gap':>10s} {'ratio':>6s}")
    for d in (0.6, 1.0, 2.0, 4.0, 8.0):
        Me, _ = exact(pitch, d, slot)
        Mp = predicted(pitch, d, slot)
        Mg = gap_term(pitch, d, slot)
        print(f"{d:5.1f} {Me * 1e12:9.1f} {Mp * 1e12:8.1f} {Mg * 1e12:8.1f} {(Mp + Mg) * 1e12:10.1f} {(Mp + Mg) / Me:6.3f}", flush=True)


def gap_read(pitch, d, slot):
    """The general crossing term: the voltage the aggressor (driven alone) develops across the gap where
    the victim would cross it, read from the aggressor's own solve (gap-edge terminals added)."""
    m = board(pitch, d, victim=False, slot=slot)
    x0, y0, x1, y1 = slot
    y = 10.0 + d
    if not (y0 < y < y1):
        return 0.0
    for side, xe in (("L", x0 - pitch / 2), ("R", x1 + pitch / 2)):
        j, i = m.cell(xe, y)
        mask = np.zeros((m.ny, m.nx), bool)
        mask[j, i] = True
        m.terminal(f"g{side}", 1, mask=mask)
    v, info = ES.potentials(m, {"as": 1.0, "ag": -1.0}, INF)
    return float((v["gR"] - v["gL"]).imag)


def main_read(pitch=0.2):
    print(f"{'plane':24s} {'d mm':>5s} {'M exact':>9s} {'field':>8s} {'gap V':>8s} {'sum':>8s} {'ratio':>6s}")
    for name, slot in {"slot under both": (14.5, 4.0, 15.5, 26.0), "slot under victim only": (14.5, 11.0, 15.5, 26.0)}.items():
        for d in (0.6, 1.0, 2.0, 4.0, 8.0):
            Me, _ = exact(pitch, d, slot)
            Mp = predicted(pitch, d, slot)
            Mg = gap_read(pitch, d, slot)
            print(f"{name:24s} {d:5.1f} {Me * 1e12:9.1f} {Mp * 1e12:8.1f} {Mg * 1e12:8.1f} {(Mp + Mg) * 1e12:8.1f} {(Mp + Mg) / Me:6.3f}", flush=True)


def main_t1(pitch=0.2):
    """The same comparison through kae.em.t1 (the router's price maps), all three planes."""
    from kae.em import t1 as T1
    print(f"{'plane':24s} {'d mm':>5s} {'M exact':>9s} {'t1':>8s} {'ratio':>6s}")
    slots = {"solid": None, "slot under both": (14.5, 4.0, 15.5, 26.0), "slot under victim only": (14.5, 11.0, 15.5, 26.0)}
    for name, slot in slots.items():
        m = board(pitch, 1.0, victim=False, slot=slot)
        v, info = ES.potentials(m, {"as": 1.0, "ag": -1.0}, INF)
        pr = T1.price(m, info["op"], info["I"], T1.cell_potentials(info["sys"], info["x"]), None, 0, w=1.0)
        X, Y = m.centres()
        for d in (0.6, 1.0, 2.0, 4.0, 8.0):
            Me, _ = exact(pitch, d, slot)
            rows = np.nonzero(abs(Y[:, 0] - (10 + d)) < 0.15)[0]
            cols = np.nonzero((X[0] > 5) & (X[0] < 30))[0]
            Mt = np.mean([T1.path_price(pr, [(r, c) for c in cols], pitch) for r in rows])
            print(f"{name:24s} {d:5.1f} {Me * 1e12:9.1f} {Mt * 1e12:8.1f} {Mt / Me:6.3f}", flush=True)
