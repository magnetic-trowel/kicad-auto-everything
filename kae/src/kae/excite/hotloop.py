# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Each switching cell's hot loop, solved again in a window around it at a finer pitch: the per-cell primaries
L_loop, R_loop at f_sw and its odd harmonics, and the switch node's overshoot peak.

The board solve (kae.excite.evaluate) runs at 0.25 mm, where hot loops read 5-12 % high and tracks narrower than
three cells are under-resolved (docs/research/physics/field-solver-accuracy.md, E7). A cell's loop current
closes within a few millimetres of its parts, so its window is solved at CELL_PITCH (chosen by the convergence
test in tools/research/physics/hl_cell_convergence.py; docs/topics/physics/pdn-and-commutation.md section 7).

The window is the bounding box of the parts that carry at least SHARE of the cell's peak pad current in the
copper-free circuit solve (input caps, switches, the pads of the overshoot observer), grown by
max(MARGIN_MM, MARGIN_H x h), h the outer layers' depth to their next layer, so the return current spreading in the
planes is held (a loop at height h over its plane returns 1 - (2/pi) atan(x/h) of its current beyond x; on the
test board, 2 layers 1.5 mm apart, L_loop in the window reads +3 % at 3 mm, -0.3 % at 10 mm against the whole
board at the same pitch). It
depends only on the placement and the circuit, never on the copper: every layout of one placement is judged in the
same window at the same pitch. When the copper closes the loop only outside the window, the margin doubles until it
closes (reported); a loop open on the whole board is an open cell (kae.excite.evaluate.open_cell_observations).

Per frequency the quantities are those of the board solve, on the window's copper: the layout's share
z = J_k^T v - J_k^T v_ideal of the overshoot observer k for the cell's own pattern; L_loop = Im z / w at the edge
band, R_loop(f) = Re z at f_sw, 3 f_sw and 5 f_sw (a trapezoid's odd harmonics), with each copper layer's
resistance corrected for skin and proximity crowding beyond the nsub filaments (kae.em.skin, one-sided crowding:
a loop over its return plane). The overshoot peak per corner is kae.excite.harm.peak with the window's L_loop and
Z(f_sw): L di/dt with the switch's edge time plus the fundamental's share, the same model the board solve prices.
"""
from __future__ import annotations

import math
import time

import numpy as np

from . import harm as HA
from . import observe as O

CELL_PITCH = 0.0625          # mm: see the module docstring and the convergence test
SHARE = 0.05                 # a pad carrying this share of the cell's peak pad current sets the window
MARGIN_MM = 3.0              # mm around the pads
MARGIN_H = 6.0               # x the outer layers' depth to their next layer, if larger (the return spreads over a few h)
HARMONICS = (1, 3, 5)        # R_loop at these multiples of f_sw
MAX_CELLS = 6e6              # raster budget of one window (cells x copper layers): the pitch doubles past it
MAX_GROW = 4                 # margin doublings when the loop closes only outside the window


def _pad_box(bm, tokens):
    xs, ys = [], []
    for t in tokens:
        for _, g, _ in bm.pads.get(t, []):
            x0, y0, x1, y1 = g.bounds
            xs += [x0, x1]
            ys += [y0, y1]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def window_pads(bd, s, o, freqs):
    """The pads that set a cell's window: every pad of a part through which SHARE of the peak pad current of the
    cell's own pattern or of its overshoot observer's passes (half its pads' summed |J|: a connector or module
    takes its share over many pins), at any of `freqs`, in the copper-free circuit (the same for every layout)."""
    out = set()
    for f in freqs:
        sol = bd.circuit.solve(f, [s])[s.name]
        for J in (sol["J"], O.pattern(bd, o, f)):
            big = max((abs(j) for j in J.values()), default=0.0)
            part = {}
            for p, j in J.items():
                part.setdefault(p.rsplit(".", 1)[0], []).append((p, abs(j)))
            for pads in part.values():
                if big and sum(j for _, j in pads) / 2 >= SHARE * big:
                    out |= {p for p, j in pads if j > 0}
    return out


def _skin_R(net, f, nsub):
    """The network's branch resistances with each layer's filaments scaled by kae.em.skin.correction at f."""
    from kae.em.mesh import MM
    from kae.em.skin import correction
    R = net.R.copy()
    for o in ("x", "y"):
        fl = net.fil[o]
        if not len(fl["a"]):
            continue
        lay = net.layer_of_sub[fl["s"]]
        k = np.array([correction(f, net.m.layers[l].t * MM, nsub) for l in range(len(net.m.layers))])
        R[net.off[o]:net.off[o] + len(fl["a"])] *= k[lay]
    return R


def _solve_window(path, b, bd, s, o, win, pitch, nsub, fills, freqs, skin, log):
    """{f: z} (the layout's share at the overshoot observer) for the cell's pattern in window `win`, or
    (None, why) when the window's copper leaves the pattern open. Also the mesh's size."""
    from kae.em import solve as ES
    from kae.em.kicad import BoardMesh
    from .circuit import lump_into
    bm = BoardMesh(path, win, pitch, nsub=nsub, b=b, fills=fills)
    sols = {f: bd.circuit.solve(f, [s])[s.name] for f in freqs}
    pats = {f: O.pattern(bd, o, f, active=True) for f in freqs}
    pads = set()
    for f in freqs:
        pads |= {p for p, j in sols[f]["Ja"].items() if abs(j) > 1e-9} | {p for p, j in pats[f].items() if abs(j) > 1e-9}
    pads |= {p for e in bd.circuit.elems if e.pa and e.pb for p in (e.pa, e.pb)}
    for p in sorted(pads):
        try:
            bm.pad(p)
        except (KeyError, ValueError):
            pass

    def tpad(t):
        if t not in bm.m.terminals:
            raise KeyError(t)
        return t
    lump_into(bd.circuit, tpad, lambda a, c, zf, nm: bm.m.part(a, c, name=nm, zf=zf))
    net = ES.Network(bm.m)
    op = ES.Operator(net)
    from .evaluate import _band_start
    R0 = net.R
    out, dropped, prev = {}, 0.0, None
    for f in freqs:                      # ascending: each starts from the last one's solution (_band_start)
        Ja = sols[f]["Ja"]
        inj = {p: j for p, j in Ja.items() if p in bm.m.terminals and abs(j) > 1e-12}
        tot = sum(abs(j) for j in Ja.values()) or 1.0
        dropped = max(dropped, sum(abs(j) for p, j in Ja.items() if p not in bm.m.terminals) / tot)
        if skin:
            net.R = _skin_R(net, f, nsub)
        try:
            # a pad the window left out carries less than SHARE of the peak (window_pads): its current may leak
            (v, info), = ES.potentials_many(bm.m, [inj], f, net=net, op=op, light=True, leak=SHARE,
                                            x0=[_band_start(prev, inj, f, net.n_br)])
        finally:
            net.R = R0
        if info["unbalanced"]:
            return None, info, bm.m
        prev = (f, inj, info.pop("x"))
        info.pop("I", None)
        Jk = pats[f]
        vid = O.ideal(bd, sols[f])
        out[f] = O.bilinear(Jk, v) - O.bilinear(Jk, vid)
    return out, dict(dropped=dropped), bm.m


def cell_rows(path, b, bd, bm, srcs, obs, cps, bands, board_window, n_cu, nsub=2, pitch=CELL_PITCH,
              global_pairs=None, global_pitch=None, open_cells=None, uncomputed=(), skin=True, log=print):
    """One row per switching cell: its primaries from the window solve (state "ok"), or state "open" (the loop is
    open on the whole board: priced at its caps by kae.excite.evaluate) or "not_computed" (its pads are not in the
    board's copper model). bm: the board solve's BoardMesh (its pads' shapes and KiCad's zone fills). global_pairs:
    {source: (Le, Zf)} of the board solve, reported beside the window's."""
    from kae.em.kicad import BoardMesh  # noqa: F401  (import cost before the timers)
    from .evaluate import coarsen_pitch
    open_cells = open_cells or {}
    global_pairs = global_pairs or {}
    gaps = list(getattr(b.stackup, "gaps", None) or [1.5])
    margin0 = max(MARGIN_MM, MARGIN_H * max(gaps[0], gaps[-1]))
    rows = []
    for s in srcs:
        if s.kind != "cell":
            continue
        o = next((x for x in obs if x.kind == "overshoot" and x.meta.get("source") == s.name), None)
        row = dict(cell=s.meta.get("cell"), source=s.name)
        g = global_pairs.get(s.name)
        if g is not None:
            row["global"] = dict(pitch=global_pitch, L_loop_nH=round(g[0] * 1e9, 4),
                                 R_loop_mohm=round(max(g[1].real, 0.0) * 1e3, 4))
        if s.name in open_cells:
            rows.append(dict(row, state="open", why=open_cells[s.name]))
            continue
        if o is None or s.name in uncomputed or g is None:
            rows.append(dict(row, state="not_computed",
                             why="pads outside the copper model" if s.name in uncomputed else "no overshoot observer"))
            continue
        t0 = time.time()
        f_fund, f_edge = bands[s.name]["fund"], bands[s.name]["edge"]
        fh = [n * f_fund for n in HARMONICS]
        freqs = sorted(set(fh) | {f_edge})
        box_ = _pad_box(bm, window_pads(bd, s, o, [f_fund, f_edge]))
        if box_ is None:
            rows.append(dict(row, state="not_computed", why="no pad of the cell in the copper model"))
            continue
        res, margin, grown = None, margin0, 0
        while True:
            win = (max(board_window[0], box_[0] - margin), max(board_window[1], box_[1] - margin),
                   min(board_window[2], box_[2] + margin), min(board_window[3], box_[3] + margin))
            pc, _ = coarsen_pitch(win, pitch, n_cu, MAX_CELLS)
            z, info, m = _solve_window(path, b, bd, s, o, win, pc, nsub, bm.fills, freqs, skin, log)
            whole = win == tuple(board_window)
            if z is not None or whole or grown >= MAX_GROW:
                break
            margin *= 2
            grown += 1
        if z is None:
            rows.append(dict(row, state="open_in_window", why="the loop closes in the board solve but not in its "
                             f"window grown {grown} times to {margin:g} mm"))
            continue
        w_e = 2 * math.pi * f_edge
        Le = z[f_edge].imag / w_e
        Zf = z[f_fund]
        R = [dict(n=n, f_MHz=round(f / 1e6, 4), R_mohm=round(max(z[f].real, 0.0) * 1e3, 4)) for n, f in zip(HARMONICS, fh)]
        peaks = []
        for c in range(len(cps[s.name])):
            val = {k[1]: v for k, v in cps[s.name][c].items()}
            peaks.append(HA.peak(Zf, Le, val["I_A"], val.get("D", 0.5), val["t_i_s"])[0])
        val0 = {k[1]: v for k, v in cps[s.name][0].items()}
        rows.append(dict(row, state="ok", L_loop_nH=round(Le * 1e9, 4), R_loop_mohm=R[0]["R_mohm"], R_harmonics=R,
                         overshoot_V=dict(typ=round(peaks[0], 4), worst=round(max(peaks), 4)),
                         di_dt_A_per_ns=round(val0["I_A"] / val0["t_i_s"] * 1e-9, 4),
                         f_edge_MHz=round(f_edge / 1e6, 4),
                         window=dict(box=[round(x, 3) for x in win], pitch=pc, margin_mm=margin, grown=grown,
                                     cells=int(m.nx * m.ny * len(m.layers)), dropped_injection=round(info["dropped"], 5),
                                     skin=bool(skin), seconds=round(time.time() - t0, 1))))
        log(f"cell {s.name}: window {win[2] - win[0]:.1f} x {win[3] - win[1]:.1f} mm at {pc:g} mm: L_loop "
            f"{Le * 1e9:.3f} nH (board {g[0] * 1e9:.3f}), R_loop {R[0]['R_mohm']:.3f} mOhm at f_sw, "
            f"{time.time() - t0:.1f}s")
    return rows


def summary(rows):
    """{state: count} and the cells' primaries, one line each (for logs and the status)."""
    out = []
    for r in rows:
        if r["state"] == "ok":
            out.append(f"{r['source']}: L_loop {r['L_loop_nH']:.3f} nH, R_loop {r['R_loop_mohm']:.3f} mOhm at f_sw "
                       f"({', '.join(str(x['R_mohm']) for x in r['R_harmonics'][1:])} at "
                       f"{', '.join(str(x['n']) for x in r['R_harmonics'][1:])} f_sw), overshoot "
                       f"{r['overshoot_V']['typ']:.3g} V typ, {r['overshoot_V']['worst']:.3g} V worst"
                       + (f" [window {r['window']['pitch']:g} mm, {r['window']['seconds']}s]" if r.get("window") else ""))
        else:
            out.append(f"{r['source']}: {r['state'].upper()}: {r.get('why', '')}")
    return out


PRIMARIES = (("L_loop_nH", lambda r: r["L_loop_nH"]), ("R_loop_mohm", lambda r: r["R_loop_mohm"]),
             ("overshoot_V", lambda r: r["overshoot_V"]["worst"]))


def paired(pairs):
    """Per-cell B/A ratios of the primaries over [(rows of A, rows of B)] (one pair per board): a cell open in one
    arm only ranks worst for that arm (ratio inf or 0), never leaves the table; open in both (or not computed in
    either) it is counted, not compared. Returns (rows, summary {primary: median ratio}, counts)."""
    out, counts = [], dict(cells=0, open_a=0, open_b=0, open_both=0, not_computed=0)
    for ra, rb in pairs:
        a = {r["source"]: r for r in ra}
        for src, x in sorted(a.items()):
            y = next((r for r in rb if r["source"] == src), None)
            counts["cells"] += 1
            if y is None or "not_computed" in (x["state"], y["state"]) or "open_in_window" in (x["state"], y["state"]):
                counts["not_computed"] += 1
                continue
            oa, ob = x["state"] == "open", y["state"] == "open"
            counts["open_a"] += oa
            counts["open_b"] += ob
            if oa and ob:
                counts["open_both"] += 1
                continue
            row = dict(source=src, a=x["state"], b=y["state"])
            for k, get in PRIMARIES:
                row[k] = math.inf if ob else 0.0 if oa else get(y) / get(x) if get(x) > 0 else math.inf
            out.append(row)
    med = {k: (float(np.median([r[k] for r in out])) if out else None) for k, _ in PRIMARIES}
    return out, med, counts


def main(argv=None):
    """python -m kae.excite.hotloop A.ev.json B.ev.json [A2.ev.json B2.ev.json ...]: the cells of each pair of
    evaluations (arm A, arm B of one board) side by side, B/A per cell and the medians (open cells ranked worst)."""
    import json
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or len(argv) % 2:
        print(main.__doc__)
        return 2
    evs = [json.load(open(p)) for p in argv]
    for e, p in zip(evs, argv):
        for line in summary(e.get("cells") or []):
            print(f"{p}: {line}")
    rows, med, counts = paired([(evs[k].get("cells") or [], evs[k + 1].get("cells") or []) for k in range(0, len(evs), 2)])
    for r in rows:
        print(f"{r['source']:32s} {r['a']:5s} {r['b']:5s} " + "  ".join(f"{k} {r[k]:.3g}" for k, _ in PRIMARIES))
    print("median B/A:", {k: (round(v, 3) if v is not None else None) for k, v in med.items()}, counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
