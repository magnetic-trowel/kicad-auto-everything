# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Functional EM evaluation of a laid-out board: every aggressor's pad currents injected into a
field solve of the board's copper (kae.em), every observer read through its adjoint pattern.

    python -m kae.excite.evaluate BOARD.kicad_pcb [--pitch 0.25] [--window x0 y0 x1 y1]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time

from . import models as M
from . import observe as O
from . import sources as S


def evaluate(path, pitch=0.25, window=None, nsub=2, b=None, brief=None, fills=None, log=print, lumped=True):
    """lumped: two-pad parts (capacitors with ESL/ESR, resistors, inductors, ferrites, conducting
    rectifiers) are branches of the copper model and only the other parts' pads are injected, so the
    geometry decides which capacitor closes a loop or carries a return between planes. Harms are then
    totals (copper plus those parts); without it they are the copper's share with the circuit's
    ideal-copper current split."""
    from kae.board.kicad_file import load
    from kae.circuit import brief as B
    from kae.em import solve as ES
    from kae.em.kicad import BoardMesh
    t0 = time.time()
    b = b or load(path)
    brief = brief or B.build(b)
    bd = M.build(b, brief)
    srcs = S.add_all(bd, brief)
    obs = O.observers(bd, brief, srcs)
    # every pad any pattern touches becomes a terminal of the copper model
    key = "Ja" if lumped else "J"
    pats, pads, vid = {}, set(), {}
    for s in srcs:
        f = O.gentle_f(s)
        sol = bd.circuit.solve(f, [s])[s.name]
        pats[s.name] = (f, sol[key])
        vid[s.name] = O.ideal(bd, sol)
        pads |= {p for p, j in pats[s.name][1].items() if abs(j) > 1e-9}
    opats = {}
    for o in obs:
        for f in {pf for pf, _ in pats.values()}:
            opats[(o.name, f)] = O.pattern(bd, o, f, active=lumped)
            pads |= {p for p, j in opats[(o.name, f)].items() if abs(j) > 1e-9}
    if lumped:
        pads |= {p for e in bd.circuit.elems if e.pa and e.pb for p in (e.pa, e.pb)}
    if window is None:
        from kae.board import transform
        xs, ys = [], []
        for fp in b.footprints:
            for p in fp.pads:
                x, y = transform.pad_xy(fp, p)
                xs.append(x), ys.append(y)
        window = (min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3)
    bm = BoardMesh(path, window, pitch, nsub=nsub, b=b, fills=fills)
    missing = []
    for p in sorted(pads):
        try:
            bm.pad(p)
        except (KeyError, ValueError):
            missing.append(p)
    n_lumped = 0
    if lumped:
        from .circuit import lump_into

        def tpad(t):
            if t not in bm.m.terminals:
                raise KeyError(t)
            return t
        n_lumped = len(lump_into(bd.circuit, tpad, lambda a, c, zf, nm: bm.m.part(a, c, name=nm, zf=zf)))
    net = ES.Network(bm.m)
    op = ES.Operator(net)
    log(f"{n_lumped} parts lumped into the copper; mesh {bm.m.nx}x{bm.m.ny}x{len(bm.m.layers)} at {pitch} mm, {len(srcs)} sources, {len(obs)} observers, "
        f"{len(pads)} pads ({len(missing)} outside or unresolved), setup {time.time() - t0:.1f}s")
    harms, notes = [], []
    solved = {}
    for f in sorted({pats[s.name][0] for s in srcs}):
        group = [s for s in srcs if pats[s.name][0] == f]
        injs = [{p: j for p, j in pats[s.name][1].items() if p in bm.m.terminals} for s in group]
        for s, res in zip(group, ES.potentials_many(bm.m, injs, f, net=net, op=op)):
            solved[s.name] = res
    for s in srcs:
        f, J = pats[s.name]
        w = 2 * math.pi * f
        v, info = solved[s.name]
        if info["unbalanced"]:
            notes.append(f"{s.name}: copper open between {', '.join(sorted(info['open_terms'])[:6])} "
                         f"(unrouted or outside the window): its harms are not computed")
            continue
        for o in obs:
            if o.kind == "overshoot" and o.meta.get("source") != s.name:
                continue
            Jk = opats[(o.name, f)]
            # the layout's share: the copper solve minus the same parts with ideal copper (with lumped
            # parts the solve also holds the circuit's own, intended coupling)
            r = O.bilinear(Jk, v) - (O.bilinear(Jk, vid[s.name]) if lumped else 0.0)
            L = r.imag / w
            volts, bound = O.size(o, s, L)
            harms.append(dict(observer=o.name, source=s.name, L_nH=round(L * 1e9, 4), volts=volts,
                              bound=bound, u=volts / bound if bound else None, basis=o.basis,
                              src_class=o.src_class, iters=info["iters"]))
    harms.sort(key=lambda h: -(h["u"] or 0))
    return dict(board=path, pitch=pitch, window=window, seconds=round(time.time() - t0, 1),
                sources=[dict(name=s.name, **{k: v for k, v in s.meta.items() if isinstance(v, (int, float, str))})
                         for s in srcs],
                observers=[dict(name=o.name, kind=o.kind, bound=o.bound, basis=o.basis) for o in obs],
                harms=harms, notes=notes + [f"pad {p}: not in the copper model" for p in missing][:20],
                assumptions=bd.assumptions)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kae.excite.evaluate")
    ap.add_argument("board")
    ap.add_argument("--pitch", type=float, default=0.25)
    ap.add_argument("--window", type=float, nargs=4)
    ap.add_argument("-o")
    ap.add_argument("--no-lumped", action="store_true", help="copper only, with the circuit's ideal-copper split")
    a = ap.parse_args(argv)
    r = evaluate(a.board, a.pitch, tuple(a.window) if a.window else None, log=lambda m: print(m, file=sys.stderr),
                 lumped=not a.no_lumped)
    for h in r["harms"][:25]:
        print(f"{h['u']:8.3f}  {h['volts']*1e3:9.2f} mV / {h['bound']*1e3:7.2f}  L {h['L_nH']:8.3f} nH  "
              f"{h['observer']}  <-  {h['source']}")
    for n in r["notes"]:
        print("note:", n)
    if a.o:
        json.dump(r, open(a.o, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
