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
from types import SimpleNamespace

import numpy as np

from . import dc as DC
from . import harm as HA
from . import models as M
from . import observe as O
from . import sources as S


NO_COPPER = 1e-4         # A per unit source: a pattern below this everywhere is the circuit's leak, not current


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
             intent=None, n_corners=16, seed=0, dc=True):
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
    dcp = DC.plan(b, brief, bd, P, srcs, intent) if dc else None
    for p in (dcp.params if dcp else []):
        ledger.add(p)
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
    if lumped or dcp:
        pads |= {p for e in bd.circuit.elems if e.pa and e.pb for p in (e.pa, e.pb)}
    if dcp:
        pads |= dcp.dc_pads
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
    from .circuit import lump_into

    def tpad(t):
        if t not in bm.m.terminals:
            raise KeyError(t)
        return t
    base = list(bm.m.lumped)
    if lumped:
        n_lumped = len(lump_into(bd.circuit, tpad, lambda a, c, zf, nm: bm.m.part(a, c, name=nm, zf=zf)))
    net = ES.Network(bm.m)
    op = ES.Operator(net)
    if dcp:
        # the DC copper: only the parts that conduct at DC (a capacitor is open; a closed path through one
        # would hide an open in the copper)
        ac = bm.m.lumped
        bm.m.lumped = list(base)
        lump_into(SimpleNamespace(elems=[e for e in bd.circuit.elems if e.kind in DC.DC_KINDS]), tpad,
                  lambda a, c, zf, nm: bm.m.part(a, c, name=nm, zf=zf))
        net_dc = ES.Network(bm.m)
        bm.m.lumped = ac
        op_dc = ES.Operator(net_dc)
    log(f"{n_lumped} parts lumped into the copper; mesh {bm.m.nx}x{bm.m.ny}x{len(bm.m.layers)} at {pitch} mm, "
        f"{len(srcs)} sources, {len(obs)} observers, {len(pads)} pads ({len(missing)} outside or unresolved), "
        f"bands {[round(f / 1e6, 3) for f in freqs]} MHz, setup {time.time() - t0:.1f}s")
    solved, solver_stats = {}, []
    last = {}            # source -> (f, injections, solution): the start of its next band's solve
    for f in freqs:
        keys = [k for k, (ff, _) in pats.items() if ff == f]
        injs = [{p: j for p, j in pats[k][1].items() if p in bm.m.terminals} for k in keys]
        # a pattern whose every injection is the circuit's leak (G_LEAK): the source's current closes inside
        # its part (a core current from a rail no other part is on): none of it reaches the copper
        none_ = [all(abs(j) < NO_COPPER for j in pats[k][1].values()) for k in keys]
        for k in (k for k, z in zip(keys, none_) if z):
            solved[k] = (None, dict(unbalanced=0, no_copper=True))
        keys = [k for k, z in zip(keys, none_) if not z]
        injs = [i for i, z in zip(injs, none_) if not z]
        t_band = time.time()
        band_res = ES.potentials_many(bm.m, injs, f, net=net, op=op, light=True,
                                      x0=[_band_start(last.get(k[0]), inj, f, net.n_br) for k, inj in zip(keys, injs)]) \
            if keys else []
        for k, inj, res in zip(keys, injs, band_res):
            solved[k] = res
            if res[1].get("x") is not None and not res[1].get("unbalanced"):
                last[k[0]] = (f, inj, res[1]["x"])
        if band_res:
            solver_stats.append(_solver_row(f, band_res, time.time() - t_band))
            log("solver: " + _solver_line(solver_stats[-1]))
    notes = []
    uncomputed = []
    # an aggressor whose pattern drives current into a pad outside the copper model loses that current
    # from its solve: its harms are not computed (a dropped contribution is not a zero one)
    miss = set(missing)
    for s in srcs:
        out_ = sorted({p for band in bands[s.name] for p, j in pats[(s.name, band)][1].items() if p in miss and abs(j) > 1e-9})
        if out_:
            notes.append(f"{s.name}: pads outside the copper model ({', '.join(out_[:6])}): its harms are not computed")
            uncomputed.append(s.name)
    pairs = []
    for s in srcs:
        if s.name in uncomputed:
            continue
        res = {}
        for band, f in bands[s.name].items():
            v, info = solved[(s.name, band)]
            if info["unbalanced"]:
                notes.append(f"{s.name}: copper open: {open_note(info, bd.net_of)} (unrouted or outside the window): "
                             f"its harms are not computed")
                uncomputed.append(s.name)
                res = None
                break
            res[band] = (f, v)
        if res is None:
            continue
        if any(v is None for _, v in res.values()):
            notes.append(f"{s.name}: none of its current reaches the copper (it closes inside its part): its layout "
                         f"harms are zero")
        for o in obs:
            if o.kind == "overshoot" and o.meta.get("source") != s.name:
                continue
            z = {}
            for band, (f, v) in res.items():
                if v is None:
                    z[band] = 0j
                    continue
                Jk = opats[(o.name, f)]
                # the layout's share: the copper solve minus the same parts with ideal copper
                z[band] = O.bilinear(Jk, v) - (O.bilinear(Jk, vid[(s.name, band)]) if lumped else 0.0)
            w_e = 2 * math.pi * res["edge"][0]
            pairs.append(dict(o=o, s=s, Zf=z["fund"], Le=z["edge"].imag / w_e))
    # harms at the typical point and at the corners of each aggressor's intervals
    cps = {s.name: corners(P[s.name].values(), n=n_corners, seed=seed) for s in srcs}
    ncp = n_corners + 3
    harms = []
    observations = []
    hazards = []
    tot = [0.0] * ncp
    for pr in pairs:
        o, s = pr["o"], pr["s"]
        us, parts_, vals, fs = [], None, [], []
        for c in range(ncp):
            val = {k[1]: v for k, v in cps[s.name][c].items()}
            u, d = HA.pair_u(o.kind, o.bound, pr["Zf"], pr["Le"], val)
            if c == 0:
                parts_ = (dict(f_worst_MHz=round(d["f_worst"] / 1e6, 1) if d["f_worst"] else None) if o.kind == "cm" else
                          dict(volts=d["volts"], bound=d["bound"], edge_share=round(d["ve"] / d["volts"], 3) if d["volts"] else None))
            if o.kind == "cm":
                fs.append(d["f_worst"])
                vals.append(u * O.cm_v_lim(d["f_worst"]) if d["f_worst"] else 0.0)
            else:
                vals.append(d["volts"])
            us.append(u)
            tot[c] += HA.phi(u)
        observations.append(O.observation(bd, o, s, vals, us, fs))
        if o.kind == "overshoot":
            h = HA.overshoot_hazard(s.name, sorted({r for r in (O._ref(s.pa), O._ref(s.pb)) if r}) + [s.meta.get("sw") or s.a],
                                    [{k[1]: v for k, v in cps[s.name][c].items()} for c in range(ncp)], vals,
                                    where=" (copper ring at the edge and fundamental bands)")
            if h:
                hazards.append(h)
        harms.append(dict(observer=o.name, source=s.name, kind=o.kind, u=us[0], u_lo=min(us), u_hi=max(us),
                          L_nH=round(pr["Le"] * 1e9, 4), Zf_mohm=round(abs(pr["Zf"]) * 1e3, 3),
                          basis=o.basis, src_class=o.src_class, **(parts_ or {})))
        if o.kind == "overshoot" and pr["Le"] > 0:
            # the hot loop's efficiency cost: its copper inductance's energy, dumped into the switch at
            # every turn-off (1/2 L I^2 per cycle), at each corner's operating current and frequency
            lv = []
            for c in range(ncp):
                val = {k[1]: v for k, v in cps[s.name][c].items()}
                lv.append(0.5 * pr["Le"] * val.get("I_A", 0.0) ** 2 * val.get("f_sw_Hz", 0.0))
            ob = O.observation(bd, o, s, lv, [0.0] * ncp)
            ob.update(id="loss.loop", unit="W", reference=dict(value=None, basis="none: a loss is priced, not bounded"),
                      label=f"hot-loop loss of {s.name}: 1/2 L_loop I^2 f_sw, L_loop {pr['Le'] * 1e9:.3g} nH (copper)")
            ob["scope"]["kind"] = "loop_loss"
            ob["scope"]["L_loop_H"] = pr["Le"]
            observations.append(ob)
            # the hot loop's copper resistance at the switching frequency (the layout's share, Re Z at the
            # fundamental) carrying the loop's pulsed current: AC RMS I sqrt(D (1 - D)). The raster has no
            # skin or proximity effect, so above a few MHz this is a lower bound.
            R = max(float(pr["Zf"].real), 0.0)
            rv = []
            for c in range(ncp):
                val = {k[1]: v for k, v in cps[s.name][c].items()}
                D = min(max(val.get("D", 0.5), 0.0), 1.0)
                rv.append(val.get("I_A", 0.0) ** 2 * D * (1 - D) * R)
            ob = O.observation(bd, o, s, rv, [0.0] * ncp)
            ob.update(id="loss.loop_ac", unit="W", reference=dict(value=None, basis="none: a loss is priced, not bounded"),
                      label=f"hot-loop AC conduction loss of {s.name}: I_ac,rms^2 R_loop, R_loop {R * 1e3:.3g} mOhm "
                            f"at f_sw (copper, no skin effect)")
            ob["scope"]["kind"] = "loop_ac_loss"
            ob["scope"]["R_loop_ohm"] = R
            observations.append(ob)
    # each switch node's capacitance in the layout (its copper to every other net and the world, in the
    # board's own stackup: kae.excite.capacitive), charged and discharged through the switch every cycle:
    # 1/2 C V^2 f_sw lost at each hard turn-on
    cells = {pr["s"].name: pr["s"] for pr in pairs if pr["o"].kind == "overshoot" and pr["s"].meta.get("sw")}
    if cells:
        from . import capacitive as CAP
        try:
            cpl, cworld = CAP.couplings(b, bm, bd, brief, [], log=log)
        except Exception as e:                                   # the electrostatic solve is optional here
            cpl, cworld = [], {}
            notes.append(f"switch-node capacitance not computed ({type(e).__name__}: {e})")
        for name, s in cells.items():
            sw = s.meta["sw"]
            # the node's whole capacitance: to the world (the Maxwell row sum) plus to every other net
            C = (cworld.get(sw) or 0.0) + sum(c for a, _, c in cpl if a == sw)
            if not C:
                continue
            sv = []
            for c in range(ncp):
                val = {k[1]: v for k, v in cps[name][c].items()}
                sv.append(0.5 * C * val.get("V_V", 0.0) ** 2 * val.get("f_sw_Hz", 0.0))
            o = next(pr["o"] for pr in pairs if pr["s"].name == name and pr["o"].kind == "overshoot")
            ob = O.observation(bd, o, s, sv, [0.0] * ncp)
            ob.update(id="loss.swnode", unit="W", reference=dict(value=None, basis="none: a loss is priced, not bounded"),
                      label=f"switch-node capacitance loss of {name}: 1/2 C_sw V^2 f_sw, C_sw {C * 1e12:.3g} pF (copper)")
            ob["scope"]["kind"] = "swnode_loss"
            ob["scope"]["C_sw_F"] = C
            observations.append(ob)
    part_power = {}
    if dcp:
        # the DC band and the heat band solve the same network at f = 0: one factorization for both, handed to the
        # heat band in a holder it empties (freed before the heat band factors its own conduction network)
        sys_dc = {}                          # built by the first solve that needs it (_dc_system)
        harms += _dc_harms(dcp, bm, b, net_dc, op_dc, cps, srcs, n_corners, seed, tot, notes, log, obs_out=observations,
                           system=sys_dc)
        if dcp.loads and not any(n.startswith("DC: copper open") for n in notes):
            # part temperatures from the board's own heat flow, and each part's loss (kae.excite.heat)
            from . import heat as HT
            harms += HT.evaluate(bm, b, bd, dcp, P, net_dc, op_dc, cps, srcs, n_corners, seed, [0.0] * ncp, notes,
                                 intent, log=log, ledger=ledger, obs_out=observations,   # not in the legacy total
                                 power_out=part_power, system=sys_dc)
        del sys_dc
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
    bad = [ob for ob in observations if ob.get("implausible")]
    if bad:
        notes.append(f"{len(bad)} observation(s) implausible, left for kae.intent to report unpriced: "
                     f"{bad[0]['label']}: {bad[0]['implausible']}")
    if any(n.startswith(DC_VOID) for n in notes):
        uncomputed.append("dc")
    return dict(board=path, pitch=pitch, window=window, seconds=round(time.time() - t0, 1), seed=seed,
                total=totals(tot, uncomputed),
                ledger=ledger.rows(), questions=[dict(subject=p.subject, name=p.name, lo=p.lo, hi=p.hi, unit=p.unit,
                                                      basis=p.basis) for p in ledger.flagged()],
                bands={k: v for k, v in bands.items()}, rings=rings,
                observers=[dict(name=o.name, kind=o.kind, bound=o.bound, basis=o.basis) for o in obs],
                harms=harms, observations=observations, hazards=hazards,
                part_power_W={k: round(v, 6) for k, v in sorted(part_power.items())},
                solver_stats=solver_stats,
                notes=notes + [f"pad {p}: not in the copper model" for p in missing][:20],
                assumptions=bd.assumptions)


def _dc_system(holder, op):
    """The DC system shared by the DC and heat bands, built on first use (a board whose DC band solves nothing
    never builds one) and kept in the holder for the heat band, which empties it."""
    if "sys" not in holder:
        from kae.em import solve as ES
        holder["sys"] = ES.System(op, 0.0)
    return holder["sys"]


def _band_start(prev, inj, f, n_br):
    """A source's solution at an earlier band as the start of its solve at f: its branch currents scaled by the
    injections' ratio (least squares over the terminals), its node potentials by that and f / f_prev too (above a
    few MHz the copper is inductive: the same currents' voltages grow with frequency). None without one."""
    if prev is None or not np.isfinite(f) or f <= 0:
        return None
    f0, inj0, x = prev
    if not np.isfinite(f0) or f0 <= 0:
        return None
    ts = [t for t in inj if t in inj0]
    den = sum(abs(inj0[t]) ** 2 for t in ts)
    if not ts or den == 0:
        return None
    c = sum(inj[t] * np.conj(inj0[t]) for t in ts) / den
    out = np.array(x, complex) * c
    out[n_br:] *= f / f0
    return out


def _solver_row(f, results, seconds, band=None):
    """One band's solver statistics: right-hand sides, COCG iterations, factorization and total time."""
    its = sorted(int(info.get("iters", 0)) for _, info in results)
    tf = next((info.get("t_factor") for _, info in results if info.get("t_factor") is not None), None)
    return dict(band=band or ("dc" if f == 0 else "ac"), f_Hz=f, rhs=len(results), iters_min=its[0], iters_med=its[len(its) // 2],
                iters_max=its[-1], t_factor_s=round(tf, 2) if tf is not None else None, t_total_s=round(seconds, 2))


def _solver_line(r):
    f = "DC" if r["f_Hz"] == 0 else f"{r['f_Hz'] / 1e6:g} MHz"
    return (f"{r['band']} {f}: {r['rhs']} rhs, COCG iterations {r['iters_min']}/{r['iters_med']}/{r['iters_max']} "
            f"(min/median/max), factor {r['t_factor_s']} s, total {r['t_total_s']} s")


def open_note(info, net_of=None):
    """The copper pieces a pattern's current cannot leave (kae.em.solve.open_islands), the largest first:
    the current, the nets and a few terminals of each."""
    out = []
    for isl in info["open_islands"][:3]:
        nets = sorted({(net_of or {}).get(t, "?") for t in isl["terms"]})
        out.append(f"{abs(isl['current']):.3g} A enters {'/'.join(nets[:3])} ({', '.join(isl['terms'][:4])}"
                   f"{', ...' if len(isl['terms']) > 4 else ''}) with no way out")
    more = len(info["open_islands"]) - 3
    return "; ".join(out) + (f"; {more} more pieces" if more > 0 else "")


def totals(tot, uncomputed=()):
    """The per-corner totals' summary; none when any source or band could not be computed (open copper):
    an incomplete evaluation has no score (a missing harm is not a zero harm)."""
    if uncomputed:
        return dict(complete=False, not_computed=list(uncomputed), robust=None, typical=None, p90=None, worst=None,
                    best=None)
    ts = sorted(tot)
    return dict(complete=True, robust=round(HA.robust(tot)[0], 2), typical=round(tot[0], 2),
                p90=round(ts[int(0.9 * (len(ts) - 1))], 2), worst=round(max(tot), 2), best=round(min(tot), 2))


def print_total(t):
    if not t.get("complete", True):
        print(f"total harm: NOT COMPUTED: the copper is open for {', '.join(t['not_computed'][:6])} "
              f"(an unrouted or broken connection); this board has no score")
        return
    print(f"total harm: robust {t['robust']} (mean of the worst {HA.WORST_SHARE:.0%} of corners), typical {t['typical']}, "
          f"90% of corners below {t['p90']}, worst {t['worst']}, best {t['best']}")
    if t.get("uncertain"):
        print("total harm: UNCERTAIN: the reduced model did not converge to its tolerance (see the notes)")


# the DC band's notes that void the score: an open flow, or load/source currents left out of the copper
DC_VOID = ("DC: copper open", "DC: pads outside the copper model")


def _dc_harms(dcp, bm, b, net_dc, op_dc, cps, srcs, n_corners, seed, tot, notes, log, ac_copper=None, obs_out=None,
              system=None):
    """The DC band's harms (kae.excite.dc) at every corner, added into the per-corner totals `tot`. A
    corner's cells take the values of the same corner of their switching harms (one operating point).
    ac_copper: the switching harmonics' copper loss per corner (W), counted with the DC copper loss.
    obs_out: a list the band's observations (kae.intent: physical values per corner) are appended to."""
    from kae.em import solve as ES
    from .beliefs import corners
    t0 = time.time()
    ncp = n_corners + 3
    own = corners(dcp.params, n=n_corners, seed=seed + 1) if dcp.params else [{} for _ in range(ncp)]
    cvs = []
    for c in range(ncp):
        cv = dict(own[c])
        for s in srcs:
            if s.kind == "cell":
                cv[s.name] = {k[1]: v for k, v in cps[s.name][c].items()}
        cvs.append(cv)
    m = bm.m
    raw = [DC.injections(dcp, cv) for cv in cvs]
    out_ = sorted({p for inj in raw for p in inj if p not in m.terminals})
    if out_:
        notes.append(f"DC: pads outside the copper model ({', '.join(out_[:6])}): their currents are left out")
    injs = [{p: a for p, a in inj.items() if p in m.terminals} for inj in raw]
    net_of = {f"{fp.ref}.{p.number}": p.net for fp in b.footprints for p in fp.pads}
    if not any(injs):
        notes.append("DC: no rail with a source and a load; the DC band is empty")
        return []
    t_band = time.time()
    res = ES.potentials_many(m, injs, 0.0, net=net_dc, op=op_dc, light=True,
                             system=_dc_system(system, op_dc) if isinstance(system, dict) else system)
    log("solver: " + _solver_line(_solver_row(0.0, res, time.time() - t_band, band="dc")))
    trk = DC.track_currents(bm, b.tracks, net_dc, nets=set(dcp.feeds) | set(dcp.grounds))
    loss, drops, heat = [], {}, []
    for c, (V, info) in enumerate(res):
        if V is None:
            notes.append(f"DC: copper open: {open_note(info, net_of)} (unrouted, or a path "
                         f"only through a part that is open at DC): the DC band is not computed")
            return []
        ob = DC.observe(dcp, cvs[c], V, info, tracks=trk)
        if ac_copper is not None:
            u_, P_, bud = ob["loss"]
            P_ += float(ac_copper[c])
            ob["loss"] = (P_ / bud if bud > 0 else 0.0, P_, bud)
        loss.append(ob["loss"])
        for ref, rail, u, dv, bnd in ob["drops"]:
            drops.setdefault((ref, rail), [None] * ncp)[c] = (u, dv, bnd)
        heat.append(max(ob["heat"], key=lambda h: h[1]) if ob["heat"] else None)
    rows = []
    us = [x[0] for x in loss]
    rows.append(dict(observer="dc:copper_loss", source="dc", kind="dc_loss", u=us[0], u_lo=min(us), u_hi=max(us),
                     P_mW=round(loss[0][1] * 1e3, 3), budget_mW=round(loss[0][2] * 1e3, 3),
                     basis=f"copper dissipation{' (DC and switching harmonics)' if ac_copper is not None else ''} "
                           f"against {dcp.loss_share:.0%} of the delivered power"))
    for c in range(ncp):
        tot[c] += HA.phi(us[c])
    obs = [] if obs_out is None else obs_out
    obs.append(dict(id="loss.copper", unit="W", values=[x[1] for x in loss], u=us,
                    scope=dict(kind="dc_loss", nets=sorted(set(dcp.feeds) | set(dcp.grounds))),
                    reference=dict(value=loss[0][2], basis=f"{dcp.loss_share:.0%} of the delivered power"),
                    label="copper dissipation" + (" (DC and switching harmonics)" if ac_copper is not None else " (DC)")))
    for (ref, rail), vals in drops.items():
        u_ = [v[0] if v else 0.0 for v in vals]
        for c in range(ncp):
            tot[c] += HA.phi(u_[c])
        v0 = vals[0] or (0.0, 0.0, 0.0)
        obs.append(dict(id="drop.rail", unit="V", values=[v[1] if v else 0.0 for v in vals], u=u_,
                        scope=dict(kind="dc_drop", load=ref, rail=rail, parts=[ref], nets=[rail]),
                        reference=dict(value=v0[2], basis=f"{dcp.drop_share:.0%} of the rail's voltage"),
                        label=f"DC drop from {rail}'s source to {ref}"))
        rows.append(dict(observer=f"dc:drop:{ref}@{rail}", source="dc", kind="dc_drop", u=u_[0], u_lo=min(u_), u_hi=max(u_),
                         dV_mV=round(v0[1] * 1e3, 3), budget_mV=round(v0[2] * 1e3, 2),
                         basis=f"rail + ground drop from the rail's source against {dcp.drop_share:.0%} of its voltage"))
    if any(heat):
        u_ = [h[1] if h else 0.0 for h in heat]
        for c in range(ncp):
            tot[c] += HA.phi(u_[c])
        worst = max((h for h in heat if h), key=lambda h: h[1])
        tr = trk.tracks[worst[0]]
        h0 = heat[0]
        obs.append(dict(id="heat.track", unit="K", values=[h[2] if h else 0.0 for h in heat], u=u_,
                        scope=dict(kind="dc_heat", nets=[tr.net], layer=tr.layer, width_mm=tr.width),
                        reference=dict(value=dcp.dT_max, basis="IPC-2221 rise"),
                        label=f"temperature rise of the hottest track (worst corner: {tr.net} on {tr.layer}, "
                              f"{tr.width} mm)"))
        rows.append(dict(observer=f"dc:heating:{tr.net}@{tr.layer}", source="dc", kind="dc_heat", u=u_[0], u_lo=min(u_),
                         u_hi=max(u_), dT_K=round(h0[2], 2) if h0 else None, I_A=round(abs(worst[3]), 3),
                         track=dict(net=tr.net, layer=tr.layer, width=tr.width, start=tr.start, end=tr.end),
                         basis=f"hottest track by IPC-2221 against {dcp.dT_max:g} K"))
    log(f"DC band: {len(dcp.loads)} loads on {len(dcp.feeds)} rails, {len(cvs)} corners in {time.time() - t0:.1f}s")
    notes.extend(f"DC: {n}" for n in dcp.notes)
    return rows


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
    print_total(r["total"])
    print("assumptions:")
    for p in r["ledger"]:
        print(f"  {p['subject'][:28]:28s} {p['name']:9s} {p['typ']:10.4g} [{p['lo']:.4g} .. {p['hi']:.4g}] {p['unit']:2s} "
              f"{p['source']:10s} {p['basis'][:90]}")
    for rg in r["rings"]:
        print(f"ring: {rg['cell']}: copper loop {rg['L_copper_nH']} nH, f_ring {rg['f_ring_MHz']} MHz (C_sw hi/typ/lo)")
    print("harms (u at typical, [lowest .. highest over the corners]):")
    for h in r["harms"][:25]:
        extra = (f"edge share {h['edge_share']:.0%}" if h.get("edge_share") is not None else
                 f"worst harmonic {h.get('f_worst_MHz')} MHz" if h.get("f_worst_MHz") else
                 f"{h['P_mW']} of {h['budget_mW']} mW" if h["kind"] == "dc_loss" else
                 f"{h['dV_mV']} of {h['budget_mV']} mV" if h["kind"] == "dc_drop" else
                 f"{h['dT_K']} K at {h['I_A']} A" if h["kind"] == "dc_heat" else "")
        if h["kind"] == "heat":
            extra = f"T_j {h.get('T_C')} C (worst {h.get('T_hi_C')} C)"
        if h["kind"].startswith("dc_") or h["kind"] == "heat":
            print(f"  {h['u']:8.3f} [{h['u_lo']:7.3f} .. {h['u_hi']:7.3f}]  {extra:38s} {h['observer']}")
            continue
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
