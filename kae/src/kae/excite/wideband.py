# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Whole-spectrum evaluation of a laid-out board: every harm summed over every harmonic, from one
reduced model (docs/topics/architecture/physics-frequency-coverage.md).

    python -m kae.excite.wideband BOARD.kicad_pcb [--pitch 0.25] [--intent FILE] [-o out.json]

1. The whole circuit goes into the copper (kae.excite.circuit.lump_all): every source and every
   observer is a fixed unit port.
2. kae.em.reduce builds the board's passive reduced model from DC to f_max, the smaller of 300 MHz and
   the quasi-static limit of the board's size (theta = w l / v = 0.3 across its diagonal), with its
   error estimated on the layout share of every source-observer pair.
3. At every corner of the assumption ledger, each source's trapezoid (I, D, t_i, f_sw) is summed over
   its harmonics up to f_max (kae.excite.spectrum): each observer's waveform peak (overshoot, supply,
   victim pickup) against its bound, each harmonic of the cable common mode against the CISPR line,
   and the AC losses in the copper and in every part.
4. The DC band (kae.excite.dc) as in kae.excite.evaluate; its copper loss is the DC and the AC copper
   loss together.

Sources sharing a harmonic add in amplitude (their phases are unknown: the worst case).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from types import SimpleNamespace

import numpy as np

from . import capacitive as CP
from . import dc as DC
from . import harm as HA
from . import heat as HT
from . import models as M
from . import observe as O
from . import sources as S
from . import spectrum as SP

F_TOP = 3e8
THETA = 0.3                 # electrical size below which the quasi-static model holds
EPS_EFF = 3.5               # FR4 microstrip, for the limit's wave speed


def _ports(srcs, obs, term):
    from .circuit import port
    out = []
    for s in srcs:
        out.append(port(term, s.a, s.b, s.pa, s.pb))
    for o in obs:
        if o.kind == "cm":
            a, b = o.meta["pads"]
            out.append({term(None, a): 1.0, term(None, b): -1.0})
        else:
            out.append(port(term, o.a, o.b, o.pa, o.pb))
    return out


def _ideal(bd, s, obs, f):
    """The observers' values for source s with ideal copper (the circuit alone)."""
    V = bd.circuit.solve(f, [s], skip=(CP.KIND,))[s.name]["V"]
    out = np.zeros(len(obs), complex)
    for k, o in enumerate(obs):
        if o.kind == "cm":
            a, b = o.meta["pads"]
            out[k] = V.get(bd.net_of[a], 0) - V.get(bd.net_of[b], 0)
        else:
            out[k] = V.get(o.b, 0) - V.get(o.a, 0)
    return out


def _wave_params(P, s, val):
    """(I, D, t_r, f_sw) of source s at one corner's values."""
    return val["I_A"], (val.get("D", 0.5) if s.kind == "cell" else 0.5), val["t_i_s"], val["f_sw_Hz"]


def evaluate(path, pitch=0.25, nsub=2, intent=None, n_corners=16, seed=0, log=print, tol=1e-3, capacitive=True):
    from kae.board import transform
    from kae.board.kicad_file import load
    from kae.circuit import brief as B
    from kae.em import reduce as RD
    from kae.em import solve as ES
    from kae.em.kicad import BoardMesh
    from .beliefs import corners
    from .circuit import lump_all, lump_into
    from .evaluate import _dc_harms, ledger_for
    t0 = time.time()
    b = load(path)
    brief = B.build(b)
    bd = M.build(b, brief)
    srcs = S.add_all(bd, brief)
    obs = O.observers(bd, brief, srcs)
    P, ledger = ledger_for(bd, brief, srcs, intent)
    dcp = DC.plan(b, brief, bd, P, srcs, intent)
    for p in dcp.params:
        ledger.add(p)
    xs, ys = [], []
    for fp in b.footprints:
        for pd in fp.pads:
            x, y = transform.pad_xy(fp, pd)
            xs.append(x), ys.append(y)
    window = (min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3)
    bm = BoardMesh(path, window, pitch, nsub=nsub, b=b)
    pads = {q for e in bd.circuit.elems for q in (e.pa, e.pb) if q}
    pads |= {q for s in srcs for q in (s.pa, s.pb) if q} | {q for o in obs for q in (o.pa, o.pb) if q}
    pads |= {q for o in obs if o.kind == "cm" for q in o.meta["pads"]} | dcp.dc_pads
    for q in sorted(pads):
        try:
            bm.pad(q)
        except (KeyError, ValueError):
            pass

    def mesh_pad(t):
        if t not in bm.m.terminals:
            raise KeyError(t)
        return t
    # the DC copper first (only the parts that conduct at DC), then the whole circuit for the AC model
    lump_into(SimpleNamespace(elems=[e for e in bd.circuit.elems if e.kind in DC.DC_KINDS]), mesh_pad,
              lambda a, c, zf, nm: bm.m.part(a, c, name=nm, zf=zf))
    net_dc = ES.Network(bm.m)
    op_dc = ES.Operator(net_dc)
    bm.m.lumped = []
    n_cm = 0
    if capacitive:
        # the layout's capacitive couplings become parts of the circuit (kae.excite.capacitive)
        coupl, world = CP.couplings(b, bm, bd, brief, srcs, log=log)
        n_cm = CP.add_to_circuit(bd, coupl)
        for e in bd.circuit.elems[-n_cm:] if n_cm else []:
            for q in (e.pa, e.pb):
                try:
                    bm.pad(q)
                except (KeyError, ValueError):
                    pass
    term, skipped = lump_all(bd, mesh_pad, lambda a, c, zf, nm: bm.m.part(a, c, name=nm, zf=zf), bm.m.internal_node)
    net = ES.Network(bm.m)
    op = ES.Operator(net)
    diag = math.hypot(window[2] - window[0], window[3] - window[1]) * 1e-3
    f_qs = THETA * 299792458.0 / math.sqrt(EPS_EFF) / (2 * math.pi * diag)
    f_max = min(F_TOP, f_qs)
    log(f"wideband: {len(bm.m.lumped)} parts in the copper ({n_cm} capacitive couplings, {len(skipped)} with a pad outside), "
        f"{len(bm.m.internal)} internal nodes; {len(srcs)} sources, {len(obs)} observers; "
        f"f_max {f_max / 1e6:.0f} MHz (quasi-static limit {f_qs / 1e6:.0f} MHz); setup {time.time() - t0:.1f}s")
    ns = len(srcs)
    rows, cols = list(range(ns, ns + len(obs))), list(range(ns))
    model = RD.Reduced(op, _ports(srcs, obs, term), log=log)

    def scale(f):
        Zr = model.Z(f)[np.ix_(rows, cols)]
        Zi = np.stack([_ideal(bd, s, obs, f) for s in srcs], 1)
        Zl = Zr - Zi
        return np.abs(Zl) + 1e-3 * np.abs(Zl).max()
    model.build(f_max, fmin=1e3, tol=tol, rows=rows, cols=cols, scale=scale, f0=(0.0, min(10e6, f_max / 3)))
    est = model.history[-1][1] if model.history else None
    log(f"wideband: model of order {model.V.shape[1]} from snapshots {[round(f / 1e6, 4) for f in model.freqs]} MHz "
        f"in {model.seconds:.0f}s; estimated worst relative error {est:.1e}")
    # per corner, per source: the harmonic sums
    cps = {s.name: corners(P[s.name].values(), n=n_corners, seed=seed) for s in srcs}
    ncp = n_corners + 3
    tot = [0.0] * ncp
    U = {}                                          # (observer, source) -> [u per corner]
    worst_f = {}
    ac_cu = np.zeros(ncp)
    parts = {}
    left = {}
    t1 = time.time()
    cm_amp = {}                                     # cm observer -> {harmonic frequency: summed amplitude} per corner
    for j, s in enumerate(srcs):
        for c in range(ncp):
            val = {k[1]: v for k, v in cps[s.name][c].items()}
            I, D, tr, fsw = _wave_params(P, s, val)
            if f_max < fsw:
                continue
            r = SP.totals(model, j, rows, I, D, tr, fsw, f_max, ideal=lambda f, s=s: _ideal(bd, s, obs, f))
            ac_cu[c] += r["copper"]
            for nm, pw in r["parts"].items():
                parts.setdefault(nm, np.zeros(ncp))[c] += pw
            left[s.name] = max(left.get(s.name, 0.0), r["left_out"])
            for k, o in enumerate(obs):
                if o.kind == "overshoot" and o.meta.get("source") != s.name:
                    continue
                if o.kind == "cm":
                    band = (r["f"] >= O.F_CM[0]) & (r["f"] <= O.F_CM[1])
                    d = cm_amp.setdefault(o.name, [dict() for _ in range(ncp)])[c]
                    for f, v in zip(r["f"][band], np.abs(r["V"][k][band])):
                        key = round(f / 1e3)                     # harmonics of different sources: by kHz
                        d[key] = d.get(key, 0.0) + v             # unknown phases: amplitudes add
                    continue
                bound = o.bound
                if o.kind == "overshoot" and "V_max_V" in val:
                    bound = max(val["V_max_V"] - val.get("V_V", 0.0), 1e-3)
                u = float(r["peak"][k]) / bound if bound else 0.0
                U.setdefault((o.name, s.name), [0.0] * ncp)[c] = u
    for oname, per in cm_amp.items():
        us = []
        for c, d in enumerate(per):
            best, fb = 0.0, None
            for key, v in d.items():
                f = key * 1e3
                rr = v / (O.CM_V_LIM_HZ / f)
                if rr > best:
                    best, fb = rr, f
            us.append(best)
            worst_f[oname] = fb if c == 0 else worst_f.get(oname)
        U[(oname, "all")] = us
    log(f"wideband: harmonic sums over {ncp} corners in {time.time() - t1:.1f}s")
    harms = []
    for (oname, sname), us in U.items():
        for c in range(ncp):
            tot[c] += HA.phi(us[c])
        o = next(x for x in obs if x.name == oname)
        harms.append(dict(observer=oname, source=sname, kind=o.kind, u=us[0], u_lo=min(us), u_hi=max(us),
                          basis=o.basis, f_worst_MHz=round(worst_f[oname] / 1e6, 2) if worst_f.get(oname) else None))
    notes = []
    dc_rows = _dc_harms(dcp, bm, b, net_dc, op_dc, cps, srcs, n_corners, seed, tot, notes, log, ac_copper=ac_cu) \
        if dcp.loads else []
    harms += dc_rows
    # temperatures: the DC flow's and the parts' heat, with each part's switching-harmonic loss
    ac_by_ref = {}
    for nm, v in parts.items():
        ref = nm.split(":")[0].split(".")[0]
        ac_by_ref[ref] = ac_by_ref.get(ref, np.zeros(ncp)) + v
    if dcp.loads:
        harms += HT.evaluate(bm, b, bd, dcp, P, net_dc, op_dc, cps, srcs, n_corners, seed, tot, notes, intent,
                             ac_parts=ac_by_ref, log=log, ledger=ledger)
    harms.sort(key=lambda h: -(h["u_hi"] or 0))
    ts = sorted(tot)
    return dict(board=path, pitch=pitch, seconds=round(time.time() - t0, 1), seed=seed, f_max=f_max,
                model=dict(order=int(model.V.shape[1]), snapshots=model.freqs, estimated_error=est,
                           history=model.history),
                total=dict(robust=round(HA.robust(tot)[0], 2), typical=round(tot[0], 2),
                           p90=round(ts[int(0.9 * (ncp - 1))], 2), worst=round(max(tot), 2), best=round(min(tot), 2)),
                ac_loss=dict(copper_W=dict(typical=float(ac_cu[0]), hi=float(ac_cu.max())),
                             parts_W={k: dict(typical=float(v[0]), hi=float(v.max())) for k, v in
                                      sorted(parts.items(), key=lambda kv: -kv[1].max()) if v.max() > 0}),
                left_out=left, ledger=ledger.rows(),
                questions=[dict(subject=p.subject, name=p.name, lo=p.lo, hi=p.hi, unit=p.unit, basis=p.basis)
                           for p in ledger.flagged()],
                harms=harms, notes=notes + ([f"{len(skipped)} parts with a pad outside the copper model: {skipped[:8]}"]
                                            if skipped else [])
                + ([f"cable common mode computed to {f_max / 1e6:.0f} MHz of the CISPR band's {O.F_CM[1] / 1e6:.0f} MHz: "
                    f"above, the board is not electrically small and the quasi-static model does not hold"]
                   if f_max < O.F_CM[1] else []))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kae.excite.wideband")
    ap.add_argument("board")
    ap.add_argument("--pitch", type=float, default=0.25)
    ap.add_argument("--intent")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tol", type=float, default=1e-3)
    ap.add_argument("--no-capacitive", action="store_true")
    ap.add_argument("-o")
    a = ap.parse_args(argv)
    from .beliefs import load_intent
    r = evaluate(a.board, a.pitch, intent=load_intent(a.intent), seed=a.seed, tol=a.tol, capacitive=not a.no_capacitive,
                 log=lambda m: print(m, file=sys.stderr, flush=True))
    t = r["total"]
    print(f"total harm: robust {t['robust']}, typical {t['typical']}, 90% of corners below {t['p90']}, worst {t['worst']}")
    print(f"model: order {r['model']['order']}, snapshots {[round(f / 1e6, 3) for f in r['model']['snapshots']]} MHz, "
          f"estimated error {r['model']['estimated_error']:.1e}; harmonics to {r['f_max'] / 1e6:.0f} MHz "
          f"(left out: {', '.join(f'{k} {v:.1%}' for k, v in r['left_out'].items())})")
    al = r["ac_loss"]
    print(f"AC loss: copper {al['copper_W']['typical'] * 1e3:.2f} mW (corners up to {al['copper_W']['hi'] * 1e3:.2f}); "
          + ", ".join(f"{k} {v['typical'] * 1e3:.2f} mW" for k, v in list(al["parts_W"].items())[:6]))
    print("harms (u at typical, [lowest .. highest over the corners]):")
    for h in r["harms"][:25]:
        print(f"  {h['u']:8.3f} [{h['u_lo']:7.3f} .. {h['u_hi']:7.3f}]  {h['observer']}  <-  {h['source']}"
              + (f"  (worst harmonic {h['f_worst_MHz']} MHz)" if h.get("f_worst_MHz") else "")
              + (f"  ({h['T_C']} C, corners up to {h['T_hi_C']} C)" if h.get("T_C") is not None else ""))
    for n in r["notes"]:
        print("note:", n)
    if a.o:
        json.dump(r, open(a.o, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
