# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage E3 check: does the capacitive price field predict the change of mutual capacitance that a
fresh static solve gives?

An aggressor strip A over a ground plane, a victim pad V elsewhere. The prediction uses only the
fields of the copper as it stands: a victim segment at edge gap d from A adds C'(x) phi_A(x) dl
(kae.em.cprice); an aggressor segment beside a victim strip adds C'(x) phi_V(x) dl (reciprocity).
The exact change is a re-solve with the segment painted in (CapPrices.after_hop).

    python em_cap_price_check.py [--pitch 0.25] [--h 1.51] [--er 4.5]
    python em_cap_price_check.py --board BOARD.kicad_pcb [--victim NET] [--hops HOPS.json]
    python em_cap_price_check.py --measure BOARD.kicad_pcb ...

On a board: the victim net's tracks are removed, the fields solved, and the tracks (or the hops in
HOPS.json, [[layer, [x0, y0], [x1, y1], width], ...] per hop) added back one hop at a time, each
predicted and then re-solved; last, the board with every hop is re-meshed from scratch and solved.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "kae" / "src"))

from kae.em import cprice as CP  # noqa: E402
from kae.em import static as ST  # noqa: E402
from kae.em.mesh import Layer, Mesh  # noqa: E402


def setup(pitch, h, er, victim_strip=False):
    m = Mesh.over(0, 0, 30, 20, pitch, [Layer("F", h, 0.035, 1), Layer("B", 0, 0.035, 1)])
    m.rect(1, "GND", 0, 0, 30, 20)
    m.rect(0, "A", 5, 9.5, 25, 10.5)                    # 1 mm aggressor strip, 20 mm long
    if victim_strip:
        m.rect(0, "V", 5, 13, 25, 13.25)                # a victim strip, one pitch wide
    else:
        m.rect(0, "V", 27, 2, 28, 3)                    # a victim pad far away
    es = ST.Electrostatic(m, ST.Stack([0.0, h * 1e-3], [er]), [h * 1e-3, 0.0])
    cp = CP.CapPrices.__new__(CP.CapPrices)
    cp.log, cp.tol, cp._es = (lambda s: None), 1e-7, (None, es)
    cp.pairs = [dict(obs="k", src="s", a="A", n="V", bound=1.0, R=1e4, Cc=5e-12, V0=5.0)]
    cp.nets, cp.cval = ["A", "V"], {"s": [{}]}
    F = CP.Fields(m)
    cp._drive(es, F, ["A", "V"])
    cp._pairs(F)
    return cp, F


def measure(path, pitch):
    """C_m, C_node and u of every capacitive pair of a board as it stands, by a fresh static solve."""
    from kae.board import transform
    from kae.board.kicad_file import load
    from kae.circuit import brief as B
    from kae.em.kicad import BoardMesh
    from kae.excite import models as M
    from kae.excite import observe as O
    from kae.excite import sources as S
    from kae.excite.beliefs import corners
    from kae.excite.evaluate import ledger_for
    from kae.excite.harm import robust
    b = load(path)
    brief = B.build(b)
    bd = M.build(b, brief)
    srcs = S.add_all(bd, brief)
    obs = O.observers(bd, brief, srcs)
    P, _ = ledger_for(bd, brief, srcs, None)
    cval = {s.name: [{k[1]: v for k, v in c.items()} for c in corners(P[s.name].values(), n=16, seed=0)] for s in srcs}
    cp = CP.CapPrices(bd, brief, srcs, obs, cval, log=lambda s: None)
    xs, ys = zip(*[transform.pad_xy(f, p) for f in b.footprints for p in f.pads])
    window = (min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3)
    F = cp.solve(BoardMesh(path, window, pitch, nsub=1, b=b), b)
    tot = np.sum([[CP.phi(x) for x in us] for us in F.u.values()], axis=0)
    for (o, a, n), C in F.Cm.items():
        u = F.u[(o, a, n)]
        print(f"{path}: {o} <- {a}: C_m {C * 1e15:.3f} fF, C_node {(cp._pair(o, a)['Cc'] + F.Cself[n]) * 1e12:.3f} pF, "
              f"u typ {u[0]:.3f} [{u.min():.3f} .. {u.max():.3f}]")
    print(f"{path}: capacitive harm, robust {robust(list(tot))[0]:.2f}, typical {tot[0]:.2f}")


def board_check(path, victim, hops_file, pitch):
    import json
    import math
    import time

    from kae.board import transform
    from kae.board.kicad_file import load
    from kae.circuit import brief as B
    from kae.em.kicad import BoardMesh
    from kae.excite import models as M
    from kae.excite import observe as O
    from kae.excite import sources as S
    from kae.excite.beliefs import corners
    from kae.excite.evaluate import ledger_for
    from kae.excite.harm import robust
    from kae.route.critical_recheck import fills_of
    t0 = time.time()
    b = load(path)
    brief = B.build(b)
    bd = M.build(b, brief)
    srcs = S.add_all(bd, brief)
    obs = O.observers(bd, brief, srcs)
    P, _ = ledger_for(bd, brief, srcs, None)
    cval = {s.name: [{k[1]: v for k, v in c.items()} for c in corners(P[s.name].values(), n=16, seed=0)] for s in srcs}
    cp = CP.CapPrices(bd, brief, srcs, obs, cval, log=print)
    victim = victim or next(p["n"] for p in cp.pairs)
    xs, ys = zip(*[transform.pad_xy(f, p) for f in b.footprints for p in f.pads])
    window = (min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3)
    if hops_file:
        hops = json.load(open(hops_file))
    else:
        hops = [[[t.layer, list(t.start), list(t.end), t.width]] for t in b.tracks if t.net == victim]
    fills = fills_of(path)
    keep = [t for t in b.tracks if t.net != victim]
    b.tracks = keep
    bm = BoardMesh(path, window, pitch, nsub=1, b=b, fills=fills)
    F = cp.solve(bm, b)
    ncp = len(next(iter(cval.values())))
    idx = robust(list(np.sum([F.u[k] for k in F.u], axis=0) if F.u else np.zeros(ncp)))[1]
    from kae.em.pnr import phi_prime
    cp.set_weights(F, idx, phi_prime)
    print(f"setup and first solve {time.time() - t0:.1f}s; {cp.report(F)}")
    names = [l.name for l in bm.m.layers]
    tot_p = tot_x = 0.0
    for h in hops:
        segs = [(l, tuple(p0), tuple(p1)) for l, p0, p1, w in h]
        w = h[0][3]
        G, r = cp.after_hop(F, victim, segs, [], w, 0.6, names)
        for key, (p, x) in r.items():
            ln = sum(math.dist(p0, p1) for _, p0, p1 in segs)
            print(f"hop {len(segs)} segs {ln:5.2f} mm w {w:g}: C_m {key[0]} <- {key[1]}: {F.Cm[key] * 1e15:7.3f} -> "
                  f"{G.Cm[key] * 1e15:7.3f} fF; change predicted {p * 1e15:+7.3f}, solved {x * 1e15:+7.3f} fF; "
                  f"u typ {F.u[key][0]:.3f} -> {G.u[key][0]:.3f}")
            tot_p, tot_x = tot_p + p, tot_x + x
        F = G
    print(f"all hops: predicted {tot_p * 1e15:+.3f} fF, solved hop by hop {tot_x * 1e15:+.3f} fF")
    from kae.board.model import Track
    b2 = load(path)
    b2.tracks = keep + [Track(uuid="", start=tuple(p0), end=tuple(p1), width=w, layer=l, net=victim)
                        for h in hops for l, p0, p1, w in h]
    bm2 = BoardMesh(path, window, pitch, nsub=1, b=b2, fills=fills)
    F2 = cp.solve(bm2, b2)
    for key in F2.Cm:
        print(f"re-meshed board: C_m {key[0]} <- {key[1]} {F2.Cm[key] * 1e15:.3f} fF (hop by hop {F.Cm[key] * 1e15:.3f}); "
              f"C_node {(cp._pair(key[0], key[1])['Cc'] + F2.Cself[key[2]]) * 1e12:.3f} pF; u typ {F2.u[key][0]:.3f}, "
              f"max {F2.u[key].max():.3f}")
    print(f"total {time.time() - t0:.1f}s")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pitch", type=float, default=0.25)
    ap.add_argument("--h", type=float, default=1.51)
    ap.add_argument("--er", type=float, default=4.5)
    ap.add_argument("--board")
    ap.add_argument("--victim")
    ap.add_argument("--hops")
    ap.add_argument("--measure", nargs="+", help="boards to measure as they stand")
    a = ap.parse_args(argv)
    if a.measure:
        for p in a.measure:
            measure(p, a.pitch)
        return
    if a.board:
        return board_check(a.board, a.victim, a.hops, a.pitch)
    w = a.pitch
    print(f"h {a.h} mm, er {a.er}, pitch {a.pitch} mm, victim track one pitch wide, 10 mm long")
    cp, F = setup(a.pitch, a.h, a.er)
    key = ("k", "A", "V")
    print(f"C_m before: {F.Cm[key] * 1e15:.3f} fF")
    print(f"{'case':34s} {'predicted fF':>12s} {'actual fF':>10s} {'ratio':>6s}")
    for d in (0.25, 0.5, 1.0, 2.0, 4.0):
        y = 10.5 + d + w / 2                       # the segment's centre line: edge gap d from A
        segs = [("F", (10.0, y), (20.0, y))]
        G, r = cp.after_hop(F, "V", segs, [], w, 0.6, ["F", "B"])
        p, x = r[key]
        print(f"{'victim parallel, gap ' + format(d, 'g') + ' mm':34s} {p * 1e15:12.3f} {x * 1e15:10.3f} {p / x:6.3f}")
    # a victim segment approaching the aggressor end-on
    segs = [("F", (26.0, 10.0), (29.0, 10.0))]
    G, r = cp.after_hop(F, "V", segs, [], w, 0.6, ["F", "B"])
    p, x = r[key]
    print(f"{'victim end-on, 1 .. 4 mm':34s} {p * 1e15:12.3f} {x * 1e15:10.3f} {p / x:6.3f}")
    # reciprocity: aggressor copper added beside a victim strip
    cp, F = setup(a.pitch, a.h, a.er, victim_strip=True)
    print(f"victim strip at 2.5 mm: C_m before {F.Cm[key] * 1e15:.3f} fF")
    for d in (0.5, 1.0):
        y = 13.0 - d - w / 2
        segs = [("F", (10.0, y), (20.0, y))]
        G, r = cp.after_hop(F, "A", segs, [], w, 0.6, ["F", "B"])
        p, x = r[key]
        print(f"{'aggressor segment, gap ' + format(d, 'g') + ' mm to V':34s} {p * 1e15:12.3f} {x * 1e15:10.3f} {p / x:6.3f}")


if __name__ == "__main__":
    main()
