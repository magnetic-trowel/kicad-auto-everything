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

from . import harm as HA
from . import models as M
from . import observe as O
from . import sources as S


def _vin_net(bd, brief, st):
    """A cell's input rail: the inductor's terminal that is not the switch node."""
    uuid = {u: p["ref"] for u, p in brief["parts"].items()}
    ref = uuid.get(st.get("inductor"))
    nets = {bd.net_of.get(t) for t in bd.net_of if ref and t.startswith(ref + ".")}
    nets.discard(st.get("sw"))
    nets.discard(None)
    return next(iter(nets), None)


def ledger_for(bd, brief, srcs, intent=None):
    """The assumption ledger of the board's aggressors: {source name: {param: Param}}, Ledger."""
    from kae.circuit.netlist import Netlist  # noqa: F401  (part text comes from the brief's parts)
    from .beliefs import Ledger
    from . import params as PA
    L = Ledger()
    text = {p["ref"]: " ".join(str(p.get(k) or "") for k in ("value", "lib_id")) for p in brief["parts"].values()}
    uuid = {u: p["ref"] for u, p in brief["parts"].items()}
    P = {}
    for s in srcs:
        if s.kind == "cell":
            st = next((x for x in brief.get("structures") or [] if x.get("id") == s.meta["cell"]), {})
            ctrl = uuid.get(st.get("controller"))
            rect = next((uuid.get(u) for u, _ in st.get("loop") or []
                         if bd.part_kind.get(uuid.get(u), ("",))[0] == "diode"), None)
            P[s.name] = PA.cell(L, s, brief, bd, intent, text.get(ctrl, ""), text.get(rect, ""),
                                vin_net=_vin_net(bd, brief, st))
        else:
            P[s.name] = PA.generic(L, s, s.kind)
    return P, L


def evaluate(path, pitch=0.25, window=None, nsub=2, b=None, brief=None, fills=None, log=print, lumped=True,
             intent=None, n_corners=16, seed=0):
    """Every harm of a laid-out board, across the parameters' intervals.

    Each aggressor's pattern is solved in two bands: its switching fundamental (current split by the
    parts' C and ESR) and the edge band (split by ESL). Per (observer, aggressor) pair the copper's
    layout share is |Z| at the fundamental and L at the edge (the solve minus the same parts with
    ideal copper). Harm sizes (kae.excite.harm) are evaluated at the typical point and at seeded
    corners of the intervals (kae.excite.beliefs). lumped: two-pad parts are branches of the copper
    model and only the other parts' pads are injected."""
    from kae.board.kicad_file import load
    from kae.circuit import brief as B
    from kae.em import solve as ES
    from kae.em.kicad import BoardMesh
    from .beliefs import corners
    t0 = time.time()
    b = b or load(path)
    brief = brief or B.build(b)
    bd = M.build(b, brief)
    srcs = S.add_all(bd, brief)
    obs = O.observers(bd, brief, srcs)
    P, ledger = ledger_for(bd, brief, srcs, intent)
    key = "Ja" if lumped else "J"
    # the two bands of each aggressor
    bands = {}
    for s in srcs:
        f_fund = P[s.name]["f_sw"].typ
        f_edge = O.gentle_f(s)
        bands[s.name] = {"fund": f_fund, "edge": max(f_edge, 2 * f_fund) if f_fund >= f_edge else f_edge}
    pats, vid, pads = {}, {}, set()
    for s in srcs:
        for band, f in bands[s.name].items():
            sol = bd.circuit.solve(f, [s])[s.name]
            pats[(s.name, band)] = (f, sol[key])
            vid[(s.name, band)] = O.ideal(bd, sol)
            pads |= {p for p, j in sol[key].items() if abs(j) > 1e-9}
    freqs = sorted({f for (_, _), (f, _) in pats.items()})
    opats = {}
    for o in obs:
        for f in freqs:
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
    log(f"{n_lumped} parts lumped into the copper; mesh {bm.m.nx}x{bm.m.ny}x{len(bm.m.layers)} at {pitch} mm, "
        f"{len(srcs)} sources, {len(obs)} observers, {len(pads)} pads ({len(missing)} outside or unresolved), "
        f"bands {[round(f / 1e6, 3) for f in freqs]} MHz, setup {time.time() - t0:.1f}s")
    solved = {}
    for f in freqs:
        keys = [k for k, (ff, _) in pats.items() if ff == f]
        injs = [{p: j for p, j in pats[k][1].items() if p in bm.m.terminals} for k in keys]
        for k, res in zip(keys, ES.potentials_many(bm.m, injs, f, net=net, op=op)):
            solved[k] = res
    notes = []
    pairs = []
    for s in srcs:
        res = {}
        for band, f in bands[s.name].items():
            v, info = solved[(s.name, band)]
            if info["unbalanced"]:
                notes.append(f"{s.name}: copper open between {', '.join(sorted(info['open_terms'])[:6])} "
                             f"(unrouted or outside the window): its harms are not computed")
                res = None
                break
            res[band] = (f, v)
        if res is None:
            continue
        for o in obs:
            if o.kind == "overshoot" and o.meta.get("source") != s.name:
                continue
            z = {}
            for band, (f, v) in res.items():
                Jk = opats[(o.name, f)]
                # the layout's share: the copper solve minus the same parts with ideal copper
                z[band] = O.bilinear(Jk, v) - (O.bilinear(Jk, vid[(s.name, band)]) if lumped else 0.0)
            w_e = 2 * math.pi * res["edge"][0]
            pairs.append(dict(o=o, s=s, Zf=z["fund"], Le=z["edge"].imag / w_e))
    # harms at the typical point and at the corners of each aggressor's intervals
    cps = {s.name: corners(P[s.name].values(), n=n_corners, seed=seed) for s in srcs}
    ncp = n_corners + 3
    harms = []
    tot = [0.0] * ncp
    for pr in pairs:
        o, s = pr["o"], pr["s"]
        us, parts_ = [], None
        for c in range(ncp):
            val = {k[1]: v for k, v in cps[s.name][c].items()}
            u, d = HA.pair_u(o.kind, o.bound, pr["Zf"], pr["Le"], val)
            if c == 0:
                parts_ = (dict(f_worst_MHz=round(d["f_worst"] / 1e6, 1) if d["f_worst"] else None) if o.kind == "cm" else
                          dict(volts=d["volts"], bound=d["bound"], edge_share=round(d["ve"] / d["volts"], 3) if d["volts"] else None))
            us.append(u)
            tot[c] += HA.phi(u)
        harms.append(dict(observer=o.name, source=s.name, kind=o.kind, u=us[0], u_lo=min(us), u_hi=max(us),
                          L_nH=round(pr["Le"] * 1e9, 4), Zf_mohm=round(abs(pr["Zf"]) * 1e3, 3),
                          basis=o.basis, src_class=o.src_class, **(parts_ or {})))
    harms.sort(key=lambda h: -(h["u_hi"] or 0))
    # each cell's parasitic ring: its copper loop with the switch node's capacitance
    rings = []
    for pr in pairs:
        if pr["o"].kind == "overshoot":
            C = P[pr["s"].name].get("C_sw")
            if C is not None and pr["Le"] > 0:
                fr = [1 / (2 * math.pi * math.sqrt(pr["Le"] * c)) for c in (C.hi, C.typ, C.lo)]
                rings.append(dict(cell=pr["s"].name, L_copper_nH=round(pr["Le"] * 1e9, 3),
                                  f_ring_MHz=[round(x / 1e6) for x in fr]))
    tot_sorted = sorted(tot)
    return dict(board=path, pitch=pitch, window=window, seconds=round(time.time() - t0, 1), seed=seed,
                total=dict(robust=round(HA.robust(tot)[0], 2), typical=round(tot[0], 2),
                           p90=round(tot_sorted[int(0.9 * (ncp - 1))], 2),
                           worst=round(max(tot), 2), best=round(min(tot), 2)),
                ledger=ledger.rows(), questions=[dict(subject=p.subject, name=p.name, lo=p.lo, hi=p.hi, unit=p.unit,
                                                      basis=p.basis) for p in ledger.flagged()],
                bands={k: v for k, v in bands.items()}, rings=rings,
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
    ap.add_argument("--intent", help="intent file (JSON): operating conditions, part facts, requirements")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    from .beliefs import load_intent
    r = evaluate(a.board, a.pitch, tuple(a.window) if a.window else None, log=lambda m: print(m, file=sys.stderr),
                 lumped=not a.no_lumped, intent=load_intent(a.intent), seed=a.seed)
    t = r["total"]
    print(f"total harm: robust {t['robust']} (mean of the worst {HA.WORST_SHARE:.0%} of corners), typical {t['typical']}, "
          f"90% of corners below {t['p90']}, worst {t['worst']}, best {t['best']}")
    print("assumptions:")
    for p in r["ledger"]:
        print(f"  {p['subject'][:28]:28s} {p['name']:9s} {p['typ']:10.4g} [{p['lo']:.4g} .. {p['hi']:.4g}] {p['unit']:2s} "
              f"{p['source']:10s} {p['basis'][:90]}")
    for rg in r["rings"]:
        print(f"ring: {rg['cell']}: copper loop {rg['L_copper_nH']} nH, f_ring {rg['f_ring_MHz']} MHz (C_sw hi/typ/lo)")
    print("harms (u at typical, [lowest .. highest over the corners]):")
    for h in r["harms"][:25]:
        extra = (f"edge share {h['edge_share']:.0%}" if h.get("edge_share") is not None else
                 f"worst harmonic {h.get('f_worst_MHz')} MHz" if h.get("f_worst_MHz") else "")
        print(f"  {h['u']:8.3f} [{h['u_lo']:7.3f} .. {h['u_hi']:7.3f}]  L {h['L_nH']:7.3f} nH  |Zf| {h['Zf_mohm']:7.2f} mOhm  "
              f"{extra:22s} {h['observer']}  <-  {h['source']}")
    if r["questions"]:
        print("would settle it (resting on class priors):")
        for q in r["questions"]:
            print(f"  {q['subject']} {q['name']}: {q['lo']:.4g}..{q['hi']:.4g} {q['unit']} ({q['basis'][:80]})")
    for n in r["notes"]:
        print("note:", n)
    if a.o:
        json.dump(r, open(a.o, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
