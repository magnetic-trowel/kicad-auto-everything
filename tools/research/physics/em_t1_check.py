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


def board4(pitch, d, victim=True, slot_up=None, slot_dn=None, h_dn=0.2, h_up=0.2):
    """Stripline version: traces on a middle layer between a lower and an upper ground plane, the
    planes tied by vias along the board edges."""
    zt = T + h_dn
    zu = zt + T + h_up
    m = Mesh.over(0, 0, 40, 30, pitch, [Layer("U", zu, T, 2), Layer("S", zt, T, 2), Layer("D", 0, T, 2)])
    for k, sl in ((0, slot_up), (2, slot_dn)):
        m.rect(k, "GND", 0, 0, 40, 30)
        if sl:
            X, Y = m.centres()
            x0, y0, x1, y1 = sl
            m.lab[k][(X > x0) & (X < x1) & (Y > y0) & (Y < y1)] = -1
    for x in np.arange(1.0, 40.0, 2.0):
        for y in (1.0, 29.0):
            m.via(x, y, [0, 1, 2], "GND", drill=0.3)
    for y in np.arange(3.0, 28.0, 2.0):
        for x in (1.0, 39.0):
            m.via(x, y, [0, 1, 2], "GND", drill=0.3)
    m.rect(1, "A", 5, 10 - 0.15, 30, 10 + 0.15)
    X, Y = m.centres()

    def ends(net_y, w, name):
        near = (X > 5) & (X < 5 + pitch) & (abs(Y - net_y) < w / 2)
        far = (X > 30 - pitch) & (X < 30) & (abs(Y - net_y) < w / 2)
        m.terminal(f"{name}s", 1, mask=near)
        m.terminal(f"{name}g", 2, mask=near)
        m.terminal(f"{name}e", 1, mask=far)
        m.terminal(f"{name}eg", 2, mask=far)
        m.part(f"{name}e", f"{name}eg")
    ends(10, 0.3, "a")
    m.port("A", "as", "ag")
    if victim:
        m.rect(1, "V", 5, 10 + d - 0.15, 30, 10 + d + 0.15)
        ends(10 + d, 0.3, "v")
        m.port("V", "vs", "vg")
    return m


def main_t1_4l(pitch=0.2):
    """The two-sided price model on striplines: solid planes, a slot in the upper plane only, and in
    the lower plane only (both traces cross it)."""
    from kae.em import t1 as T1
    print(f"{'planes':22s} {'d mm':>5s} {'M exact':>9s} {'t1':>8s} {'ratio':>6s}")
    slots = {"solid": (None, None), "slot in upper only": ((14.5, 4.0, 15.5, 26.0), None),
             "slot in lower only": (None, (14.5, 4.0, 15.5, 26.0))}
    for name, (su, sd) in slots.items():
        m = board4(pitch, 1.0, victim=False, slot_up=su, slot_dn=sd)
        v, info = ES.potentials(m, {"as": 1.0, "ag": -1.0}, INF)
        pr = T1.price(m, info["op"], info["I"], T1.cell_potentials(info["sys"], info["x"]), None, 1, w=1.0,
                      ref_ids={m.nets.index("GND")})
        X, Y = m.centres()
        for d in (0.6, 2.0, 8.0):
            mm = board4(pitch, d, victim=True, slot_up=su, slot_dn=sd)
            Me = ES.solve(mm, [INF])["L"][0, 0, 1]
            rows = np.nonzero(abs(Y[:, 0] - (10 + d)) < 0.15)[0]
            cols = np.nonzero((X[0] > 5) & (X[0] < 30))[0]
            Mt = np.mean([T1.path_price(pr, [(r, c) for c in cols], pitch, T_start=2, T_end=2) for r in rows])
            print(f"{name:22s} {d:5.1f} {Me * 1e12:9.1f} {Mt * 1e12:8.1f} {Mt / Me:6.3f}", flush=True)


def main_transition(pitch=0.2):
    """Plane-transition term: where the victim's return must move between planes (its ends, which
    connect to the lower plane only), its upper-plane share pays the aggressor's U-D voltage there."""
    from kae.em import t1 as T1
    print(f"{'planes':22s} {'d':>4s} {'exact':>8s} {'t1':>8s} {'trans':>8s} {'t1+tr':>8s} {'ratio':>6s} {'t1-tr':>8s} {'ratio':>6s}")
    slots = {"solid": (None, None), "slot in upper only": ((14.5, 4.0, 15.5, 26.0), None),
             "slot in lower only": (None, (14.5, 4.0, 15.5, 26.0))}
    for name, (su, sd) in slots.items():
        m = board4(pitch, 1.0, victim=False, slot_up=su, slot_dn=sd)
        v, info = ES.potentials(m, {"as": 1.0, "ag": -1.0}, INF)
        cp = T1.cell_potentials(info["sys"], info["x"])
        pr = T1.price(m, info["op"], info["I"], cp, None, 1, w=1.0, ref_ids={m.nets.index("GND")})
        up, dn, hu, hd, a_up, a_dn = T1.references(m, 1, {m.nets.index("GND")})
        X, Y = m.centres()
        for d in (0.6, 2.0, 8.0):
            mm = board4(pitch, d, victim=True, slot_up=su, slot_dn=sd)
            Me = ES.solve(mm, [INF])["L"][0, 0, 1]
            rows = np.nonzero(abs(Y[:, 0] - (10 + d)) < 0.15)[0]
            cols = np.nonzero((X[0] > 5) & (X[0] < 30))[0]
            Mt = np.mean([T1.path_price(pr, [(r, c) for c in cols], pitch) for r in rows])
            r = rows[len(rows) // 2]
            c0, c1 = cols[0], cols[-1]

            def dUD(c):
                return (cp["phi"][0, r, c] - cp["phi"][2, r, c]).imag
            tr = float(a_up[r, c0]) * (dUD(c0) - dUD(c1))
            print(f"{name:22s} {d:4.1f} {Me*1e12:8.1f} {Mt*1e12:8.1f} {tr*1e12:8.1f} {(Mt+tr)*1e12:8.1f} "
                  f"{(Mt+tr)/Me:6.3f} {(Mt-tr)*1e12:8.1f} {(Mt-tr)/Me:6.3f}", flush=True)


def main_t1_4l_full(pitch=0.2):
    """main_t1_4l through t1.path_price with the transfer potential (the router's model)."""
    main_t1_4l(pitch)


def board_cut(pitch, cut=None, pour=True, h=H):
    """2 layers: solid ground on B, a ground pour on F around an aggressor trace on F (0.4 mm gap). A
    cutter (another net's track, no current) crosses the F pour at x = cut[0] from y = cut[1] to
    cut[2], its clearance band (0.3 mm track + 2 x 0.2 mm) removed from the pour as a refill would."""
    m = Mesh.over(0, 0, 40, 30, pitch, [Layer("F", h + T, T, 2), Layer("B", 0, T, 2)])
    m.rect(1, "GND", 0, 0, 40, 30)
    if pour:
        m.rect(0, "GND", 0, 0, 40, 30)
        X, Y = m.centres()
        gap = (abs(Y - 10) < 0.25 + 0.4) & (X > 4.6) & (X < 30.4)
        m.lab[0][gap] = -1
        m.cov[0][gap] = 0.0
        for x in np.arange(2.0, 40.0, 4.0):              # stitching between the pours
            for y in np.arange(2.0, 30.0, 4.0):
                if abs(y - 10) > 2:
                    m.via(x, y, [0, 1], "GND", drill=0.3)
    if cut:
        X, Y = m.centres()
        x0, y0, y1 = cut
        band = (abs(X - x0) < 0.15 + 0.2) & (Y > y0) & (Y < y1)
        m.lab[0][band & (m.lab[0] == m.nets.index("GND"))] = -1
        m.cov[0][band] = 0.0
    m.rect(0, "A", 5, 10 - 0.25, 30, 10 + 0.25)
    X, Y = m.centres()
    near = (X > 5) & (X < 5 + pitch) & (abs(Y - 10) < 0.25)
    far = (X > 30 - pitch) & (X < 30) & (abs(Y - 10) < 0.25)
    m.terminal("as", 0, mask=near)
    m.terminal("ag", 1, mask=near)
    m.terminal("ae", 0, mask=far)
    m.terminal("aeg", 1, mask=far)
    m.part("ae", "aeg")
    m.port("A", "as", "ag")
    return m


def main_cut(pitch=0.2, h=H):
    """How much a cut through a return-carrying pour raises a loop, and what the pour's sheet current
    across the cut line predicts (the calibration of the router's cut term)."""
    m0 = board_cut(pitch, h=h)
    v, info = ES.potentials(m0, {"as": 1.0, "ag": -1.0}, INF)
    L0 = (v["as"] - v["ag"]).imag
    net = info["net"]
    I = info["I"]
    f = net.fil["y"]
    a0 = net.off["y"]
    sel = np.isin(f["s"], net.sub_of[0])
    Ky = np.zeros((m0.ny, m0.nx))
    np.add.at(Ky, (f["j"][sel], f["i"][sel]), I[a0:a0 + len(f["a"])][sel].real)
    print(f"no cut: L = {L0 * 1e9:.4f} nH")
    print(f"{'cut':>22s} {'dL exact nH':>12s} {'crossing A':>11s} {'sum K^2 p^2':>12s}")
    for cut in [(15.0, 10.7, 12.0), (15.0, 10.7, 14.0), (15.0, 10.7, 18.0), (15.0, 10.7, 26.0), (15.0, 12.0, 26.0),
                (15.0, 15.0, 26.0), (15.0, 2.0, 9.3), (28.0, 10.7, 26.0)]:
        m = board_cut(pitch, cut, h=h)
        v, _ = ES.potentials(m, {"as": 1.0, "ag": -1.0}, INF)
        dL = (v["as"] - v["ag"]).imag - L0
        X, Y = m0.centres()
        col = int(np.argmin(abs(X[0] - cut[0])))
        rows = np.nonzero((Y[:, 0] > cut[1]) & (Y[:, 0] < cut[2]))[0]
        # current crossing the cut line in the F pour: the x-bars across column col
        fx = net.fil["x"]
        ax = net.off["x"]
        sx = np.isin(fx["s"], net.sub_of[0]) & (fx["i"] == col) & np.isin(fx["j"], rows)
        cross = I[ax:ax + len(fx["a"])][sx].real.sum()
        k2 = (I[ax:ax + len(fx["a"])][sx].real ** 2).sum()
        print(f"{str(cut):>22s} {dL * 1e9:12.4f} {cross:11.4f} {k2:12.5f}", flush=True)


def board_hop(pitch, path=None, slot=None):
    """A trace from x = 5 to 30 at y = 10 over a ground plane, shorted to it at the far end; the piece
    from x = 15 to 20 is a hop: absent (a field-free short between its end pads) or the given path,
    a list of (x0, y0, x1, y1) 0.5 mm wide rectangles."""
    m = Mesh.over(0, 0, 40, 30, pitch, [Layer("F", H + T, T, 2), Layer("B", 0, T, 2)])
    m.rect(1, "GND", 0, 0, 40, 30)
    if slot:
        X, Y = m.centres()
        x0, y0, x1, y1 = slot
        m.lab[1][(X > x0) & (X < x1) & (Y > y0) & (Y < y1)] = -1
        m.cov[1][(X > x0) & (X < x1) & (Y > y0) & (Y < y1)] = 0.0
    m.rect(0, "A", 5, 9.75, 15, 10.25)
    m.rect(0, "A", 20, 9.75, 30, 10.25)
    for r in path or []:
        m.rect(0, "A", *r)
    X, Y = m.centres()
    near = (X > 5) & (X < 5 + pitch) & (abs(Y - 10) < 0.25)
    far = (X > 30 - pitch) & (X < 30) & (abs(Y - 10) < 0.25)
    m.terminal("as", 0, mask=near)
    m.terminal("ag", 1, mask=near)
    m.terminal("ae", 0, mask=far)
    m.terminal("aeg", 1, mask=far)
    m.part("ae", "aeg")
    if path is None:
        pa = (X > 15 - pitch) & (X < 15) & (abs(Y - 10) < 0.25)
        pb = (X > 20) & (X < 20 + pitch) & (abs(Y - 10) < 0.25)
        m.terminal("ha", 0, mask=pa)
        m.terminal("hb", 0, mask=pb)
        m.part("ha", "hb")                      # the unrouted connection: a field-free short
    m.port("A", "as", "ag")
    return m


def free_L(length, w=0.5, t=T):
    """Free-space partial self inductance of a straight strip (Ruehli), mm in, H out."""
    l, w_, t_ = length * 1e-3, w * 1e-3, t * 1e-3
    return 2e-7 * l * (np.log(2 * l / (w_ + t_)) + 0.5 + 0.2235 * (w_ + t_) / l)


def main_hop(pitch=0.2):
    """Replacing a field-free short by copper: exact change of the loop against free self inductance
    plus twice the raw flux of the existing currents along the hop."""
    slots = {"solid": None, "slot across the straight path": (17.0, 6.0, 18.0, 10.6)}
    paths = {
        "straight": [(15, 9.75, 20, 10.25)],
        "dogleg 2 mm": [(14.75, 9.75, 15.25, 12.25), (14.75, 11.75, 20.25, 12.25), (19.75, 9.75, 20.25, 12.25)],
        "dogleg 2 mm down": [(14.75, 7.75, 15.25, 10.25), (14.75, 7.75, 20.25, 8.25), (19.75, 7.75, 20.25, 10.25)],
    }
    seglens = {"straight": [5.0], "dogleg 2 mm": [2.5, 5.5, 2.5], "dogleg 2 mm down": [2.5, 5.5, 2.5]}
    for sname, slot in slots.items():
        m0 = board_hop(pitch, None, slot)
        v, info = ES.potentials(m0, {"as": 1.0, "ag": -1.0}, INF)
        L0 = (v["as"] - v["ag"]).imag
        phi = EF.flux(info["op"], info["I"])
        X, Y = m0.centres()
        for pname, rects in paths.items():
            m = board_hop(pitch, rects, slot)
            vv, _ = ES.potentials(m, {"as": 1.0, "ag": -1.0}, INF)
            dL = (vv["as"] - vv["ag"]).imag - L0
            # predicted: free self of each piece + 2 x raw flux along it (current direction from 15 to 20)
            pred = sum(free_L(s) for s in seglens[pname])
            for (x0, y0, x1, y1) in rects:
                horiz = (x1 - x0) > (y1 - y0)
                sel = (X > x0) & (X < x1) & (Y > y0) & (Y < y1)
                rows = max(1, int(np.round(((y1 - y0) if horiz else (x1 - x0)) / pitch)))
                if horiz:
                    sign = 1.0
                    pred += 2 * sign * phi[(0, "x")][sel].real.sum() / rows
                else:
                    # the up/down legs: current goes away from the trace on the first leg, back on the last
                    first = x0 < 17.5
                    up = y1 > 10.3
                    sign = (1.0 if up else -1.0) * (1.0 if first else -1.0)
                    pred += 2 * sign * phi[(0, "y")][sel].real.sum() / rows
            print(f"{sname:30s} {pname:18s} dL exact {dL * 1e9:8.3f} nH  predicted {pred * 1e9:8.3f} nH  "
                  f"ratio {pred / dL if dL else float('nan'):6.3f}", flush=True)


def main_hop_image(pitch=0.2):
    """The same cases with the image (victim) model: microstrip self per length, twice the flux at the
    trace minus the flux at the plane, twice the crossing term; no end transfer."""
    from kae.em import t1 as T1
    from kae.em.pnr import strip_L_per_mm
    slots = {"solid": None, "slot across the straight path": (17.0, 6.0, 18.0, 10.6)}
    paths = {
        "straight": [(10, 17.5, 25)] and [[(15.0 + 0.2 * k, 10.0) for k in range(26)]],
        "dogleg 2 mm": [[(15.0, 10.0 + 0.2 * k) for k in range(11)] + [(15.0 + 0.2 * k, 12.0) for k in range(1, 26)]
                        + [(20.0, 12.0 - 0.2 * k) for k in range(1, 11)]],
        "dogleg 2 mm down": [[(15.0, 10.0 - 0.2 * k) for k in range(11)] + [(15.0 + 0.2 * k, 8.0) for k in range(1, 26)]
                             + [(20.0, 8.0 + 0.2 * k) for k in range(1, 11)]],
    }
    rects = {"straight": [(15, 9.75, 20, 10.25)],
             "dogleg 2 mm": [(14.75, 9.75, 15.25, 12.25), (14.75, 11.75, 20.25, 12.25), (19.75, 9.75, 20.25, 12.25)],
             "dogleg 2 mm down": [(14.75, 7.75, 15.25, 10.25), (14.75, 7.75, 20.25, 8.25), (19.75, 7.75, 20.25, 10.25)]}
    Lp = float(strip_L_per_mm(0.5, H)) * 1e3            # H/m
    for sname, slot in slots.items():
        m0 = board_hop(pitch, None, slot)
        v, info = ES.potentials(m0, {"as": 1.0, "ag": -1.0}, INF)
        L0 = (v["as"] - v["ag"]).imag
        pr = T1.price(m0, info["op"], info["I"], T1.cell_potentials(info["sys"], info["x"]), None, 0, w=1.0,
                      ref_ids={m0.nets.index("GND")})
        for pname, (pts,) in paths.items():
            m = board_hop(pitch, rects[pname], slot)
            vv, _ = ES.potentials(m, {"as": 1.0, "ag": -1.0}, INF)
            dL = (vv["as"] - vv["ag"]).imag - L0
            cells = []
            for (x, y) in pts:
                c = m0.cell(x, y)
                if not cells or c != cells[-1]:
                    cells.append(c)
            length = sum(np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts[:-1], pts[1:]))
            pred = Lp * length * 1e-3 + 2 * T1.path_price(pr, cells, pitch)
            print(f"{sname:30s} {pname:18s} dL exact {dL * 1e9:8.3f} nH  image model {pred * 1e9:8.3f} nH  "
                  f"ratio {pred / dL:6.3f}", flush=True)
