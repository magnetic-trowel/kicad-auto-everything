# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics-priced routing of the nets the circuit says matter.

    python -m kae.em.pnr BOARD.kicad_pcb OUT.kicad_pcb [--plain] [--lam 30] [--pitch 0.25]

1. The circuit (kae.excite) gives every aggressor's and observer's pad-current pattern at the
   pattern band, and the prices: d(harm)/d(L) per (observer, aggressor) pair.
2. The priced nets (every non-ground net that carries pattern current) are ripped up.
3. The copper as it stands is meshed (kae.em). Connections not yet routed are ideal shorts
   (field-free), so every pattern can be solved; each solve gives the price fields and crossing
   potentials of that pattern (kae.em.t1).
4. Each priced net is routed hop by hop (a spanning tree of its copper islands) with the legality
   of kae.route.critical_grid and move costs from the price fields: its own loop inductance over
   the local reference, signed coupling to every other pattern, and the crossing term. The fields
   are re-solved after every `refresh` nets.
--plain routes the same nets in the same order with the same legality and no physics (the A/B).
"""
from __future__ import annotations

import argparse
import math
import tempfile
import time
from pathlib import Path

import numpy as np

from . import solve as ES
from . import t1 as T1
from .kicad import BoardMesh

MU0 = 4e-7 * math.pi


def strip_L_per_mm(w, h, t=0.035):
    """Air microstrip inductance per mm (H/mm), Hammerstad-Jensen with the thickness correction."""
    w = np.maximum(w, 1e-3)
    h = np.maximum(h, 1e-3)
    u, tn = w / h, t / h
    u = u + tn / np.pi * np.log(1 + 4 * np.e / (tn / np.tanh(np.sqrt(6.517 * u)) ** 2))
    f = 6 + (2 * np.pi - 6) * np.exp(-(30.666 / u) ** 0.7528)
    return 376.73 / (2 * np.pi) * np.log(f / u + np.sqrt(1 + 4 / u ** 2)) / 2.998e8 * 1e-3


def cpw_L_per_mm(w, g):
    """Coplanar return: a strip of width w with ground copper at gap g on its own layer, both sides
    (quasi-static, L' = mu0/4 K(k')/K(k), k = w/(w + 2g)); one side only doubles it (H/mm)."""
    from scipy.special import ellipk
    k = np.clip(w / (w + 2 * np.maximum(g, 1e-3)), 1e-6, 1 - 1e-9)
    return MU0 / 4 * ellipk(1 - k * k) / ellipk(k * k) * 1e-3


# the router's prices use the barrier's slope only up to this: past it, one observer whose bound is a
# crude prior would set every price (the true score, sum phi(u), is not capped)
PHI_SLOPE_CAP = 5.0
# observer kinds whose coupling prediction has not passed a check against exact solves: the router does
# not price them (the field solve that verifies each candidate still counts them)
UNPRICED = ("cm",)


def phi_prime(u):
    """Slope of the margin price phi (kae.physics.priors): linear to 1, then a quadratic barrier."""
    return 1.0 if u <= 1 else min(1.0 + 8.0 * (u - 1.0), PHI_SLOPE_CAP)


class PhysRouter:
    def __init__(self, path, out, pitch=0.25, lam=30.0, nsub=2, plain=False, refresh=4, log=print, work=None,
                 verify=False, intent=None, seed=0, n_corners=16):
        from kae.board.kicad_file import load
        from kae.circuit import brief as B
        from kae.excite import models as M
        from kae.excite import observe as O
        from kae.excite import sources as S
        from kae.route import critical_write as W
        self.log, self.pitch, self.lam, self.nsub, self.plain, self.refresh = log, pitch, lam, nsub, plain, refresh
        self.verify = verify
        self.explain_hops = True
        self.src_path, self.out = Path(path), Path(out)
        self.work = Path(work or tempfile.mkdtemp(prefix="kae-pnr-"))
        b = load(path)
        self.brief = B.build(b)
        bd = self.bd = M.build(b, self.brief)
        self.srcs = S.add_all(bd, self.brief)
        self.obs = O.observers(bd, self.brief, self.srcs)
        self.f = O.F_PATTERN
        self.w = 2 * math.pi * self.f
        # the evaluator's assumption ledger and corners: the router prices the harm the evaluator scores
        from kae.excite.beliefs import corners
        from kae.excite.evaluate import ledger_for
        self.P, self.ledger = ledger_for(bd, self.brief, self.srcs, intent)
        self.cval = {s.name: [{k[1]: v for k, v in c.items()} for c in corners(self.P[s.name].values(), n=n_corners, seed=seed)]
                     for s in self.srcs}
        for s in self.srcs:
            if O.gentle_f(s) != self.f:
                log(f"pnr: {s.name}: edge band {O.gentle_f(s) / 1e6:.3g} MHz, priced at {self.f / 1e6:.3g} MHz")
        for p in self.ledger.flagged():
            log(f"pnr: prior {p.subject} {p.name} [{p.lo:.4g} .. {p.hi:.4g}] {p.unit}: priced over the interval")
        # pat: the injection at the pads of parts outside the copper model (two-pad parts are lumped into
        # it); flow: every pad's current with ideal copper, which says what each net carries
        self.pat, self.flow, self.vid = {}, {}, {}
        for s in self.srcs:
            r = bd.circuit.solve(self.f, [s])[s.name]
            self.pat[("s", s.name)], self.flow[("s", s.name)] = r["Ja"], r["J"]
            self.vid[("s", s.name)] = O.ideal(bd, r)
        for o in self.obs:
            self.pat[("o", o.name)] = O.pattern(bd, o, self.f, active=True)
            self.flow[("o", o.name)] = O.pattern(bd, o, self.f)
        # priced nets: every non-ground net carrying pattern current (above 1% of the pattern's largest)
        load_ = {}
        for key, J in self.flow.items():
            mx = max((abs(v) for v in J.values()), default=0) or 1
            for p, v in J.items():
                n = bd.net_of.get(p)
                if n and n not in bd.grounds and abs(v) > 0.01 * mx:
                    load_[n] = load_.get(n, 0) + abs(v) / mx
        self.nets = sorted(load_, key=lambda n: -load_[n])
        self.net_load = load_
        # rip them up
        rip = [t.uuid for t in b.tracks if t.net in self.nets] + [v.uuid for v in b.vias if v.net in self.nets]
        self.base = self.work / "base.kicad_pcb"
        W.edit(path, self.base, remove=rip)
        left = sum(1 for t in load(self.base).tracks if t.net in self.nets)
        if left:
            raise RuntimeError(f"pnr: rip-up left {left} tracks on the priced nets ({path}): the board's item ids "
                               f"were not matched; routing would see every net connected")
        for ext in (".kicad_pro", ".kicad_dru"):
            s_ = Path(path).with_suffix(ext)
            if s_.exists():
                import shutil
                shutil.copy2(s_, self.base.with_suffix(ext))
        log(f"pnr: {len(self.srcs)} aggressors, {len(self.obs)} observers; priced nets {self.nets}; "
            f"ripped {len(rip)} items")
        from kae.route.critical import Session
        self.sess = Session(self.base, opts=dict(place_allocs=False), log=lambda m: None)
        self.sp, self.router = self.sess.space, self.sess.router
        self.tracks, self.vias = [], []
        self.window = None

    # ------------------------------------------------------------------ fields
    def _state_board(self):
        from kae.route import critical_write as W
        p = self.work / "state.kicad_pcb"
        W.append_items(self.base, p, tracks=self.tracks, vias=self.vias)
        for ext in (".kicad_pro", ".kicad_dru"):
            s_ = self.base.with_suffix(ext)
            if s_.exists():
                import shutil
                shutil.copy2(s_, p.with_suffix(ext))
        return p

    def solve_fields(self):
        """Mesh the copper as it stands, short what is not yet connected, solve every pattern. Copper that has
        not changed since the last solve keeps its fields (the solve is deterministic)."""
        t0 = time.time()
        sig = hash(repr((self.tracks, self.vias)))
        if sig == getattr(self, "_sig", None) and getattr(self, "prices", None) is not None:
            self.log("pnr: copper unchanged since the last solve; fields kept")
            return
        p = self._state_board()
        from kae.board.kicad_file import load
        b = load(p)
        if self.window is None:
            from kae.board import transform
            xs, ys = [], []
            for fp in b.footprints:
                for pd in fp.pads:
                    x, y = transform.pad_xy(fp, pd)
                    xs.append(x), ys.append(y)
            self.window = (min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3)
        bm = BoardMesh(p, self.window, self.pitch, nsub=self.nsub, b=b)
        pads = {q for J in self.pat.values() for q in J}
        pads |= {q for n in self.nets for q in self.bd.pads_of.get(n, [])}
        pads |= {q for e in self.bd.circuit.elems if e.pa and e.pb for q in (e.pa, e.pb)}
        ok = set()
        for q in sorted(pads):
            try:
                bm.pad(q)
                ok.add(q)
            except (KeyError, ValueError):
                pass
        net = ES.Network(bm.m)
        # islands of each net's pads; unrouted connections become field-free shorts
        self.islands = {}
        shorted = 0
        for n in set(self.bd.net_of[q] for q in ok):
            groups = {}
            for q in self.bd.pads_of.get(n, []):
                if q in ok:
                    groups.setdefault(int(net.comp[net.term_node[q]]), []).append(q)
            self.islands[n] = list(groups.values())
            reps = [g[0] for g in groups.values()]
            for a, c in zip(reps[:-1], reps[1:]):
                bm.m.part(a, c)
                shorted += 1
        from kae.excite.circuit import lump_into

        def tpad(t):
            if t not in ok:
                raise KeyError(t)
            return t
        lump_into(self.bd.circuit, tpad, lambda a, c, zf, nm: bm.m.part(a, c, name=nm, zf=zf))
        net = ES.Network(bm.m)
        op = ES.Operator(net)
        self.ref_ids = {bm.m.nets.index(g) for g in self.ref_nets() if g in bm.m.nets} or None
        self.prices, self.pot_at = {}, {}
        self.K = {}
        layers = list(range(len(bm.m.layers)))
        keys, injs = [], []
        for key, J in self.pat.items():
            inj = {q: v for q, v in J.items() if q in ok}
            if inj:
                keys.append(key)
                injs.append(inj)
        # (warm starts from the previous refresh did not converge faster: adding copper changes the solution
        # too much; kae.em.solve.System.warm stays available)
        # identical injection sets (e.g. an observer whose active and passive patterns coincide) solve once
        uniq, slot = {}, []
        for inj in injs:
            slot.append(uniq.setdefault(tuple(sorted((q, complex(v)) for q, v in inj.items())), len(uniq)))
        first = {i: inj for inj, i in zip(injs, slot)}
        resu = ES.potentials_many(bm.m, [first[i] for i in range(len(uniq))], self.f, net=net, op=op)
        res = [resu[i] for i in slot]
        if len(uniq) < len(injs):
            self.log(f"pnr: {len(injs)} patterns, {len(uniq)} distinct")
        self._warm = {}
        self.log(f"pnr: solve iterations {[r[1]['iters'] for r in res]}")
        for key, (v, info) in zip(keys, res):
            self._warm[key] = info.get("state")
            if v is None:
                self.log(f"pnr: pattern {key[1]} cannot close in the copper ({info['open_terms'][:4]}); unpriced")
                continue
            cp = T1.cell_potentials(info["sys"], info["x"])
            self.K[key] = self._sheet_currents(net, info["I"])
            from . import fields as EF
            fl = EF.flux(op, info["I"])
            self.prices[key] = {l: T1.price(bm.m, op, info["I"], cp, None, l, w=self.w, ref_ids=self.ref_ids,
                                            phi_all=fl) for l in layers}
            self.pot_at[key] = v
        self.mesh = bm.m
        self.op = op
        self.layer_names = [l.name for l in bm.m.layers]
        self._weights()
        H = self.H
        pred = getattr(self, "_pred", None)
        if pred is not None and getattr(self, "_H", None) is not None:
            self.log(f"pnr: harm {self._H:.2f} -> {H:.2f} (change {H - self._H:+.2f}; the hops' prices predicted "
                     f"{pred:+.2f})")
            # per (observer, aggressor) pair: the change of L the prices predicted against the solve's
            rows = []
            for key, L in self.Lks.items():
                L0 = self._L0.get(key)
                if L0 is None:
                    continue
                pl = self._predL.get(key, 0.0)
                rows.append((abs(L - L0) + abs(pl), key, L - L0, pl))
            for _, key, dl, pl in sorted(rows, reverse=True)[:8]:
                self.log(f"pnr:   dL {key[0][:34]:34s} <- {key[1][:24]:24s} actual {dl * 1e9:+8.3f} nH "
                         f"predicted {pl * 1e9:+8.3f} nH")
        self._H, self._pred = H, 0.0
        self._L0, self._predL = dict(self.Lks), {}
        self._sig = sig
        self.log(f"pnr: fields of {len(self.prices)} patterns on {bm.m.nx}x{bm.m.ny}x{len(layers)} "
                 f"({shorted} unrouted connections shorted) in {time.time() - t0:.1f}s; harm robust {H:.2f}, "
                 f"typical {self.H_typ:.2f}")

    def _weights(self):
        """Per (observer k, aggressor s) pair: u at every corner of s's intervals by the evaluator's model
        (kae.excite.harm.pair_u) from the solve's L_ks; the objective H is the robust total (mean over the
        worst corners, kae.excite.harm.robust) and w[(k, s)] its derivative per henry of L_ks. The router
        solves one band, so the fundamental's layout share is its inductive part (j w_sw L_ks); the
        resistive part is the DC band's."""
        from kae.excite import harm as HA
        self.wts, self.harm, self.Lks, self.u_c = {}, {}, {}, {}
        ncp = len(next(iter(self.cval.values()), [None]))
        tot = np.zeros(ncp)
        slope = {}
        for o in self.obs:
            kk = ("o", o.name)
            for s in self.srcs:
                ks = ("s", s.name)
                if o.kind == "overshoot" and o.meta.get("source") != s.name:
                    continue
                if ks not in self.pot_at:
                    continue
                r = sum(self.pat[kk].get(q, 0) * self.pot_at[ks].get(q, 0) for q in self.pat[kk] if q in self.pot_at[ks])
                r -= sum(self.pat[kk].get(q, 0) * self.vid[ks].get(q, 0) for q in self.pat[kk])   # the layout's share
                L = r.imag / self.w
                self.Lks[(o.name, s.name)] = L
                # both terms are proportional to |L| here, so u = g |L| with g per corner
                g = np.array([HA.pair_u(o.kind, o.bound, 2j * math.pi * v["f_sw_Hz"] * 1e-9, 1e-9, v)[0] / 1e-9
                              for v in self.cval[s.name]])
                us = g * abs(L)
                self.u_c[(o.name, s.name)] = us
                self.harm[(o.name, s.name)] = float(us[0])
                tot += np.where(us <= 1, us, us + 4 * (us - 1) ** 2)
                if o.kind not in UNPRICED:
                    slope[(kk, ks)] = (g, np.sign(L or 1.0), (o.name, s.name))
        self.H, idx = HA.robust(list(tot))
        self.H_typ, self.H_corners = float(tot[0]), idx
        for key, (g, sg, pk) in slope.items():
            us = self.u_c[pk]
            self.wts[key] = sg * float(np.mean([phi_prime(us[c]) * g[c] for c in idx]))

    def _islands_only(self):
        """The copper islands of each net (what is still to connect) without solving any field: the
        plain router's setup."""
        p = self._state_board()
        from kae.board.kicad_file import load
        b = load(p)
        if self.window is None:
            from kae.board import transform
            xs, ys = [], []
            for fp in b.footprints:
                for pd in fp.pads:
                    x, y = transform.pad_xy(fp, pd)
                    xs.append(x), ys.append(y)
            self.window = (min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3)
        bm = BoardMesh(p, self.window, self.pitch, nsub=1, b=b)
        ok = set()
        for q in sorted({q for n in self.nets for q in self.bd.pads_of.get(n, [])}):
            try:
                bm.pad(q)
                ok.add(q)
            except (KeyError, ValueError):
                pass
        net = ES.Network(bm.m)
        self.islands = {}
        for n in self.nets:
            groups = {}
            for q in self.bd.pads_of.get(n, []):
                if q in ok:
                    groups.setdefault(int(net.comp[net.term_node[q]]), []).append(q)
            self.islands[n] = list(groups.values())
        self.prices = {}

    def ref_nets(self):
        """Nets whose copper carries returns at the pattern band: the grounds, and every rail with a
        capacitor to a ground (an AC ground there: a power plane next to a track is its return)."""
        out = set(self.bd.grounds)
        for e in self.bd.circuit.elems:
            if e.kind == "C" and e.pa and e.pb:
                a, b = self.bd.net_of.get(e.pa), self.bd.net_of.get(e.pb)
                if a in self.bd.grounds and b in self.bd.rails:
                    out.add(b)
                elif b in self.bd.grounds and a in self.bd.rails:
                    out.add(a)
        return out

    # ------------------------------------------------------------------ hop prices
    def hop_currents(self, n, a_pads, b_pads):
        """Current of each pattern on a hop joining island A (pads a_pads) toward island B of net n:
        the pattern's injection summed over the islands on A's side of the hop (one hop per pair of
        islands in a chain, so A's side is A)."""
        out = {}
        for key, J in self.flow.items():
            i = sum(J.get(q, 0) for q in a_pads)
            if abs(i) > 1e-6:
                out[key] = complex(i).real            # injected at A's pads, flowing A -> B in the copper
        return out

    def phys(self, cur, width, ends=(None, None)):
        """The move-cost callable for GridRouter.connect, for a hop carrying `cur` {pattern: A}; ends: the
        mesh layer indices of the planes its source and target terminals' returns enter."""
        lam, m = self.lam, self.mesh

        def f(grid, layers):
            nl = len(layers)
            X = grid.x0 + np.arange(grid.nx) * grid.res
            Y = grid.y0 + np.arange(grid.ny) * grid.res
            jj = np.clip(((Y - m.y0) / m.pitch).astype(int), 0, m.ny - 1)
            ii = np.clip(((X - m.x0) / m.pitch).astype(int), 0, m.nx - 1)
            sel = np.ix_(jj, ii)
            selfc = np.zeros((nl, grid.ny, grid.nx))
            px = np.zeros_like(selfc)
            py = np.zeros_like(selfc)
            pot = np.zeros_like(selfc)
            void = np.zeros(selfc.shape, bool)
            pot2 = np.zeros_like(selfc)
            void2 = np.zeros(selfc.shape, bool)
            theta = np.zeros_like(selfc)
            th_src = np.zeros_like(selfc)
            th_dst = np.zeros_like(selfc)
            if self.plain:
                return dict(self=selfc, px=px, py=py, pot=pot, void=void, floor=1.0)
            for li, lname in enumerate(layers):
                L = self.layer_names.index(lname) if lname in self.layer_names else None
                if L is None:
                    continue
                up, dn, hu, hd, a_up, a_dn = T1.references(m, L, self.ref_ids)
                # the track's own loop over both return planes: the two returns in parallel (a
                # stripline's capacitances add, so its inductances combine in parallel in air)
                Lu = np.where(np.isfinite(hu[sel]), strip_L_per_mm(width, np.where(np.isfinite(hu), hu, 1.0)[sel]), np.inf)
                Ld = np.where(np.isfinite(hd[sel]), strip_L_per_mm(width, np.where(np.isfinite(hd), hd, 1.0)[sel]), np.inf)
                Lp = 1.0 / (1.0 / Lu + 1.0 / Ld)
                Lp = np.where(np.isfinite(Lp), Lp, strip_L_per_mm(width, 1.6))
                # a ground pour on the routing layer beside the track also carries return current:
                # in parallel with the reference below (one side: twice the two-sided coplanar value)
                gm = self._gnd_gap(L)
                if gm is not None:
                    g = np.maximum(gm[sel] - width / 2, 0.05)
                    Lc = 2 * cpw_L_per_mm(width, g)
                    Lp = Lp * Lc / (Lp + Lc)
                wself = 0.0
                for (kk, ks), wt in self.wts.items():
                    ik, is_ = cur.get(kk, 0.0), cur.get(ks, 0.0)
                    if ik == 0 and is_ == 0:
                        continue
                    wself += wt * ik * is_
                    for (pa, pb) in ((ks, ik), (kk, is_)):
                        if pb == 0 or pa not in self.prices:
                            continue
                        pr = self.prices[pa][L]
                        px[li] += wt * pb * pr.Px[sel] / m.pitch
                        py[li] += wt * pb * pr.Py[sel] / m.pitch
                        pot[li] += wt * pb * pr.phi[sel]
                        void[li] |= pr.void[sel]
                        pot2[li] += wt * pb * pr.phi2[sel]
                        void2[li] |= pr.void2[sel]
                        # vias only: replacing an unrouted (field-free) connection adds a circulating current
                        # (the hop, back through the field-free short) whose image in the planes closes on
                        # itself, so its ends move no return between planes; a via in the hop does
                        theta[li] += wt * pb * pr.psi[sel]
                split = np.zeros((grid.ny, grid.nx), bool)
                for pa in self.prices.values():
                    split |= pa[L].split[sel]
                    break
                # a split under the track: its return must find another layer or a capacitor; priced
                # as five times the track's own inductance there (not a potential difference)
                selfc[li] = max(wself, 0.0) * np.where(split, 6.0 * Lp, Lp)
            # a via's own loop: the hop's return changes planes at the nearest return transfer (a via or
            # through-hole pad of a return net): L = mu0 dz / (2 pi) ln(d / r), dz the board's copper span
            vs = np.zeros((grid.ny, grid.nx))
            wself_all = sum(wt * cur.get(kk, 0.0) * cur.get(ks, 0.0) for (kk, ks), wt in self.wts.items())
            if wself_all > 0:
                d = self._transfer_dist()[sel]
                zs = [l.z for l in m.layers]
                dz = (max(zs) - min(zs)) * 1e-3
                r = 0.15e-3
                Lv = MU0 * dz / (2 * math.pi) * np.log(np.maximum(d * 1e-3, 2 * r) / r)
                vs = lam * wself_all * Lv
            cxs = np.zeros_like(selfc)
            cys = np.zeros_like(selfc)
            for li, lname in enumerate(layers):
                if lname in self.layer_names:
                    cxs[li], cys[li] = self._cut_costs(self.layer_names.index(lname), self._hop_net, cur, sel,
                                                       (grid.ny, grid.nx))
            return dict(self=lam * selfc, px=lam * px, py=lam * py, pot=lam * pot, void=void, vself=vs,
                        cx=lam * cxs, cy=lam * cys,
                        pot2=lam * pot2, void2=void2, theta=lam * theta, th_src=lam * th_src, th_dst=lam * th_dst,
                        floor=0.2)
        return f

    def _gnd_gap(self, L):
        """Distance (mm) from each cell to the nearest ground copper on layer L, or None if it has none."""
        if not hasattr(self, "_gg") or self._gg[0] is not self.mesh:
            self._gg = (self.mesh, {})
        cache = self._gg[1]
        if L not in cache:
            from scipy import ndimage
            m = self.mesh
            ids = [m.nets.index(n) for n in self.bd.grounds if n in m.nets]
            gnd = np.isin(m.lab[L], ids) if ids else np.zeros((m.ny, m.nx), bool)
            cache[L] = ndimage.distance_transform_edt(~gnd) * m.pitch if gnd.any() else None
        return cache[L]

    # ------------------------------------------------------------------ routing
    def route(self):
        t0 = time.time()
        done = 0
        self.failed = []
        self.choices = []
        since = 0
        for n in self.nets:
            if not self.plain and (done == 0 or since >= self.refresh):
                self.solve_fields()           # plain routing reads no fields: it needs the islands only
                since = 0
            elif self.plain and done == 0:
                self._islands_only()
            since += 1
            isl = [g for g in self.islands.get(n, []) if g]
            if len(isl) < 2:
                done += 1
                continue
            if self.verify and not self.plain:
                self._route_verified(n)
                since = 0                      # the chosen candidate's fields are current
            else:
                res = self._route_net(n, plain=self.plain)
                self.failed += res["failed"]
            done += 1
        from kae.route import critical_write as W
        W.append_items(self.base, self.out, tracks=self.tracks, vias=self.vias)
        for ext in (".kicad_pro", ".kicad_dru"):
            s_ = self.base.with_suffix(ext)
            if s_.exists():
                import shutil
                shutil.copy2(s_, self.out.with_suffix(ext))
        self.log(f"pnr: {len(self.tracks)} tracks, {len(self.vias)} vias, {len(self.failed)} failed hops, "
                 f"{time.time() - t0:.1f}s" + (f"; chose {self.choices}" if self.choices else ""))
        return self

    # ------------------------------------------------------------------ verified candidates
    _STATE = ("prices", "pot_at", "K", "_warm", "wts", "harm", "u_c", "H", "H_typ", "H_corners", "_sig", "Lks", "mesh", "op", "islands", "ref_ids", "layer_names", "_H",
              "_pred", "_L0", "_predL")

    def _snap(self):
        import copy
        return {k: copy.deepcopy(getattr(self, k)) if k == "prices" else getattr(self, k, None) for k in self._STATE}

    def _restore(self, st):
        for k, v in st.items():
            setattr(self, k, v)

    def _true_harm(self):
        """The robust objective (kae.excite.harm.robust of the per-corner sums of phi(u)) by a field solve of the
        copper as it stands."""
        self.solve_fields()
        return self.H

    def _route_verified(self, n):
        """Route net n twice (physics prices, plain), keep the candidate the field solve says harms less:
        the router's own estimate never decides; with the plain route always a candidate, physics routing
        is never worse than plain by the evaluator's measure."""
        st0 = self._snap()
        cands = []
        for mode in ("phys", "plain"):
            self._restore(st0 if mode == "phys" else st0)
            if mode == "plain":
                import copy
                self.prices = copy.deepcopy(st0["prices"])
            res = self._route_net(n, plain=(mode == "plain"))
            H = self._true_harm()
            cands.append((H, mode, res, self._snap()))
            self._uncommit(res)
        H, mode, res, st = min(cands, key=lambda c: (c[0], c[1] != "plain"))
        self._recommit(res)
        self._restore(st)
        self.failed += res["failed"]
        self.choices.append((n, mode, round(cands[0][0], 2), round(cands[1][0], 2)))
        self.log(f"pnr: {n}: physics candidate {cands[0][0]:.2f}, plain {cands[1][0]:.2f} -> {mode}")

    def _uncommit(self, res):
        self.sp.remove(res["items"])
        for t in res["tracks"]:
            self.tracks.remove(t)
        for v in res["vias"]:
            self.vias.remove(v)

    def _recommit(self, res):
        items = []
        for (n, l, w, p0, p1, u, lk) in res["tracks"]:
            items.append(self.sp.add_track(n, l, w, p0, p1, owner=("pnr", n)))
            self.tracks.append((n, l, w, p0, p1, u, lk))
        for (n, x, y, D, d, u, lk) in res["vias"]:
            items.append(self.sp.add_via(n, x, y, owner=("pnr", n)))
            self.vias.append((n, x, y, D, d, u, lk))
        res["items"] = items

    def _route_net(self, n, plain=False):
        """Route every hop of net n (a spanning tree of its copper islands, nearest first); commits its
        copper and returns dict(items, tracks, vias, failed)."""
        out = dict(items=[], tracks=[], vias=[], failed=[])
        isl = [g for g in self.islands.get(n, []) if g]
        if len(isl) < 2:
            return out
        was = self.plain
        self.plain = plain

        def cen(g):
            return np.mean([self._pad_xy(q) for q in g], axis=0)
        left = isl[1:]
        tree = [isl[0]]
        try:
            while left:
                a, b_ = min(((a, b_) for a in tree for b_ in left), key=lambda ab: np.linalg.norm(cen(ab[0]) - cen(ab[1])))
                cur = self.hop_currents(n, b_, a)
                layer0 = self.sp.cu
                width = self.sp.width_limits(n, layer0[0])[1]
                if any(k[0] == "s" and k[1].startswith("cell:") for k in cur):
                    # a commutation current: wide copper lowers its inductance per length
                    width = self.sp.clamp_width(n, layer0[0], max(width, 0.8))
                srcs = [self._anchor(q) for q in b_]
                dsts = [self._anchor(q) for q in a]
                ends = (self._end_plane(b_), self._end_plane(a))
                self._hop_net = n
                rt = self.router.connect(n, [x for x in srcs if x], [x for x in dsts if x], width, list(layer0),
                                         phys=self.phys(cur, width, ends))
                if rt is None:
                    out["failed"].append((n, b_[0], a[0]))
                elif rt.segs or rt.vias:
                    if self.explain_hops and getattr(rt, "search", None) is not None and self.prices:
                        grid, lay, path, ph = rt.search
                        if plain:
                            # price the plain path with the physics arrays it was not searched with
                            self.plain = False
                            ph = self.phys(cur, width, ends)(grid, lay)
                            self.plain = True
                            rt.search = (grid, lay, path, ph)
                        self.log(f"pnr:   hop {n} {b_[0]}->{a[0]} {'plain' if plain else 'phys'}: "
                                 f"{self.explain(rt)} len {rt.length:.1f} vias {len(rt.vias)}")
                    for l, p0, p1 in rt.segs:
                        out["items"].append(self.sp.add_track(n, l, rt.width, p0, p1, owner=("pnr", n)))
                        t = (n, l, rt.width, p0, p1, "", False)
                        self.tracks.append(t)
                        out["tracks"].append(t)
                    if not plain:
                        try:
                            self._pred = (self._pred or 0.0) + self._path_harm(rt, cur, width)
                        except Exception as e:  # noqa: BLE001 - a diagnostic must not stop routing
                            self.log(f"pnr: prediction failed: {type(e).__name__}: {e}")
                        self._update_fields(rt, cur)
                    for (x, y) in rt.vias:
                        out["items"].append(self.sp.add_via(n, x, y, owner=("pnr", n)))
                        D, d = self.sp.via_size(n)
                        v = (n, x, y, D, d, "", False)
                        self.vias.append(v)
                        out["vias"].append(v)
                tree.append(b_)
                left.remove(b_)
        finally:
            self.plain = was
        return out

    @staticmethod
    def explain(rt, base=None):
        """Cost of the path a physics search found, term by term, with the arrays it was priced with:
        {base, self, mutual, crossing, transfer, via, cut} (mm-equivalent)."""
        grid, layers, path, ph = rt.search
        nl, ny, nx = len(layers), grid.ny, grid.nx
        plane = ny * nx
        out = dict(base=0.0, self=0.0, mutual=0.0, crossing=0.0, transfer=0.0, via=0.0, cut=0.0)
        f = lambda a: np.asarray(a, float).reshape(-1)
        S, PX, PY, POT, VO = f(ph["self"]), f(ph["px"]), f(ph["py"]), f(ph["pot"]), np.asarray(ph["void"]).reshape(-1)
        POT2, VO2 = f(ph.get("pot2", np.zeros(nl * plane))), np.asarray(ph.get("void2", np.zeros(nl * plane, bool))).reshape(-1)
        TH, TS, TD = (f(ph.get(k, np.zeros(nl * plane))) for k in ("theta", "th_src", "th_dst"))
        VS = f(ph.get("vself", np.zeros(plane)))
        CX, CY = f(ph.get("cx", np.zeros(nl * plane))), f(ph.get("cy", np.zeros(nl * plane)))
        p = [int(k) for k in path]
        out["transfer"] += TS[p[0]] - TD[p[-1]]
        for k, k2 in zip(p[:-1], p[1:]):
            l, r = divmod(k, plane)
            l2, r2 = divmod(k2, plane)
            if l2 != l:
                tr = TH[k2] - TH[k]
                tr = 0.0 if (tr < 0 and -tr > VS[r]) else tr
                out["via"] += VS[r]
                out["transfer"] += tr
                continue
            j, i = divmod(r, nx)
            j2, i2 = divmod(r2, nx)
            di, dj = i2 - i, j2 - j
            ln = grid.res * math.hypot(di, dj)
            out["self"] += ln * 0.5 * (S[k] + S[k2])
            out["mutual"] += grid.res * (0.5 * (PX[k] + PX[k2]) * di + 0.5 * (PY[k] + PY[k2]) * dj)
            if VO[k] or VO[k2]:
                out["crossing"] += POT[k2] - POT[k]
            if VO2[k] or VO2[k2]:
                out["crossing"] += POT2[k2] - POT2[k]
            out["cut"] += 0.5 * (CX[k] + CX[k2]) * abs(di) + 0.5 * (CY[k] + CY[k2]) * abs(dj)
            out["base"] += ln
        return {k: round(v, 2) for k, v in out.items()}

    def _path_harm(self, rt, cur, width):
        """The harm change (u, linearized) the price fields predict for a routed hop: its own loop over
        its references plus coupling and crossings along its segments (vias and ends not counted)."""
        m = self.mesh
        tot = 0.0
        for l, p0, p1 in rt.segs:
            if l not in self.layer_names:
                continue
            L = self.layer_names.index(l)
            n = max(2, int(math.ceil(math.dist(p0, p1) / (m.pitch / 2))) + 1)
            cells = []
            for t in np.linspace(0, 1, n):
                c = m.cell(p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
                if 0 <= c[0] < m.ny and 0 <= c[1] < m.nx and (not cells or c != cells[-1]):
                    cells.append(c)
            if len(cells) < 2:
                continue
            up, dn, hu, hd, a_up, a_dn = T1.references(m, L, self.ref_ids)
            j, i = cells[len(cells) // 2]
            Lu = strip_L_per_mm(width, hu[j, i]) if np.isfinite(hu[j, i]) else np.inf
            Ld = strip_L_per_mm(width, hd[j, i]) if np.isfinite(hd[j, i]) else np.inf
            g = (0.0 if not np.isfinite(Lu) else 1.0 / float(Lu)) + (0.0 if not np.isfinite(Ld) else 1.0 / float(Ld))
            Lp = 1.0 / g if g > 0 else float(strip_L_per_mm(width, 1.6))
            for (kk, ks), wt in self.wts.items():
                ik, is_ = cur.get(kk, 0.0), cur.get(ks, 0.0)
                if ik == 0 and is_ == 0:
                    continue
                dl = ik * is_ * Lp * math.dist(p0, p1)
                for pa, pb in ((ks, ik), (kk, is_)):
                    if pb and pa in self.prices:
                        dl += pb * T1.path_price(self.prices[pa][L], cells, m.pitch)
                tot += wt * dl
                key = (kk[1], ks[1])
                self._predL[key] = self._predL.get(key, 0.0) + dl
        return float(tot)

    # cutting a return pour (kae: em_t1_check main_cut): dL_ks = C(h) X_k X_s (1 - exp(-l / l0)), X the
    # current crossing the cut, C = CUT_C (h / mm)^CUT_B fitted at h = 0.2 and 1.5 mm with 4 mm stitching
    CUT_C, CUT_B = 1.92e-9, 0.65

    def _sheet_currents(self, net, I):
        """{layer: (Kx, Ky)}: each cell's x- and y-bar current (summed through the thickness, real part),
        A per unit pattern current."""
        m = self.mesh if hasattr(self, "mesh") and self.mesh is net.m else net.m
        out = {}
        for o in ("x", "y"):
            f = net.fil[o]
            a0 = net.off[o]
            n = len(f["a"])
            for l in range(len(m.layers)):
                sel = np.isin(f["s"], net.sub_of[l])
                arr = np.zeros((m.ny, m.nx))
                if n and sel.any():
                    np.add.at(arr, (f["j"][sel], f["i"][sel]), I[a0:a0 + n][sel].real)
                out.setdefault(l, {})[o] = arr
        return {l: (d["x"], d["y"]) for l, d in out.items()}

    def _cut_costs(self, L, net_name, cur, sel, shape):
        """Per-step costs (x moves, y moves) on routing layer L of cutting its return pour: over cells of
        return copper of another net, sum over priced pairs of w C X_k X_s, one side's crossing current
        summed over a window of l0 along the cut (the current a long cut interrupts)."""
        from scipy import ndimage
        m = self.mesh
        if not self.ref_ids:
            return np.zeros(shape), np.zeros(shape)
        own = m.nets.index(net_name) if net_name in m.nets else -2
        pour = np.isin(m.lab[L], list(self.ref_ids)) & (m.lab[L] != own)
        if not pour.any():
            return np.zeros(shape), np.zeros(shape)
        up, dn, hu, hd, a_up, a_dn = T1.references(m, L, self.ref_ids)
        h = np.minimum(np.where(np.isfinite(hu), hu, 1e3), np.where(np.isfinite(hd), hd, 1e3))
        h = np.where(h > 100, 1.6, h)
        C = self.CUT_C * np.power(h, self.CUT_B)
        n0 = max(1, int(round(max(1.0, 1.3 * float(np.median(h))) / m.pitch)))
        cx = np.zeros((m.ny, m.nx))
        cy = np.zeros((m.ny, m.nx))
        for (kk, ks), wt in self.wts.items():
            if kk not in self.K or ks not in self.K:
                continue
            Kkx, Kky = self.K[kk][L]
            Ksx, Ksy = self.K[ks][L]
            # an x move cuts the y-bars (current crossing it); its window runs along x
            wy_k = ndimage.uniform_filter1d(Kky, 2 * n0 + 1, axis=1) * (2 * n0 + 1)
            wy_s = ndimage.uniform_filter1d(Ksy, 2 * n0 + 1, axis=1) * (2 * n0 + 1)
            wx_k = ndimage.uniform_filter1d(Kkx, 2 * n0 + 1, axis=0) * (2 * n0 + 1)
            wx_s = ndimage.uniform_filter1d(Ksx, 2 * n0 + 1, axis=0) * (2 * n0 + 1)
            cx += wt * 0.5 * (Kky * wy_s + Ksy * wy_k)
            cy += wt * 0.5 * (Kkx * wx_s + Ksx * wx_k)
        cx = np.where(pour, np.maximum(C * cx, 0.0), 0.0)
        cy = np.where(pour, np.maximum(C * cy, 0.0), 0.0)
        return cx[sel], cy[sel]

    def _transfer_dist(self):
        """Distance (mm) from each mesh cell to the nearest place a return can change planes: a via or
        through-hole pad of a return net."""
        if getattr(self, "_td", (None,))[0] is self.mesh:
            return self._td[1]
        from scipy import ndimage
        m = self.mesh
        pts = np.zeros((m.ny, m.nx), bool)
        rid = self.ref_ids or set()
        for v in m.vias:
            if v.net in rid:
                j, i = m.cell(v.x, v.y)
                if 0 <= j < m.ny and 0 <= i < m.nx:
                    pts[j, i] = True
        d = ndimage.distance_transform_edt(~pts) * m.pitch if pts.any() else np.full((m.ny, m.nx), 50.0)
        self._td = (m, d)
        return d

    def _update_fields(self, rt, cur):
        """Between refreshes, a routed hop's own flux joins every pattern's price fields (its current in
        that pattern times the field of the hop and its return under it), so the nets after it see it."""
        if self.plain or not hasattr(self, "op"):
            return
        from . import fields as EF
        m = self.mesh
        bars = []
        for l, p0, p1 in rt.segs:
            if l not in self.layer_names:
                continue
            L = self.layer_names.index(l)
            up, dn, hu, hd, a_up, a_dn = T1.references(m, L, self.ref_ids)
            n = max(2, int(math.ceil(math.dist(p0, p1) / (m.pitch / 2))) + 1)
            prev = None
            for t in np.linspace(0, 1, n):
                c = m.cell(p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
                if prev is not None and c != prev and 0 <= c[0] < m.ny and 0 <= c[1] < m.nx:
                    (j0, i0), (j1, i1) = prev, c
                    for (ja, ia), (jb, ib) in (((j0, i0), (j0, i1)), ((j0, i1), (j1, i1))):
                        if (ja, ia) == (jb, ib):
                            continue
                        o = "x" if ja == jb else "y"
                        sg = (ib - ia) if o == "x" else (jb - ja)
                        jj, ii = min(ja, jb), min(ia, ib)
                        bars.append((L, o, jj, ii, float(sg)))
                        for ref, a in ((up, a_up), (dn, a_dn)):
                            k = ref[jj, ii]
                            if k >= 0 and a[jj, ii] > 0:
                                bars.append((int(k), o, jj, ii, -float(sg) * float(a[jj, ii])))
                prev = c
        if not bars:
            return
        fl = EF.flux_of_cells(self.op, bars)
        for key, i in cur.items():
            if key not in self.prices or i == 0:
                continue
            for L, pr in self.prices[key].items():
                up, dn, hu, hd, a_up, a_dn = T1.references(m, L, self.ref_ids)
                dx, dy = fl[(L, "x")].copy(), fl[(L, "y")].copy()
                for ref, a in ((up, a_up), (dn, a_dn)):
                    for k in np.unique(ref[ref >= 0]):
                        sel = ref == k
                        dx[sel] -= a[sel] * fl[(int(k), "x")][sel]
                        dy[sel] -= a[sel] * fl[(int(k), "y")][sel]
                pr.Px = pr.Px + i * dx
                pr.Py = pr.Py + i * dy

    def _end_plane(self, pads):
        """The plane the return of an island's terminal enters: nearest return copper to its first pad's
        copper layer (an SMD pad on F.Cu: the plane under F.Cu). None without a mesh (plain routing)."""
        if not getattr(self, "layer_names", None):
            return None
        for q in pads:
            ref, num = q.rsplit(".", 1)
            for it in self.sp.pads_by_fp.get(self._fp(ref), []):
                if str(it.owner[1]) == num:
                    ls = [l for l in self.layer_names if l in it.layers]
                    if ls:
                        return T1.end_plane(self.mesh, self.layer_names.index(ls[0]), self.ref_ids)
        return None

    def _pad_xy(self, tok):
        ref, num = tok.rsplit(".", 1)
        for it in self.sp.pads_by_fp.get(self._fp(ref), []):
            if str(it.owner[1]) == num:
                return np.array(it.pos)
        return np.array([0.0, 0.0])

    def _fp(self, ref):
        if not hasattr(self, "_fpmap"):
            self._fpmap = {}
            for fpu, its in self.sp.pads_by_fp.items():
                for it in its:
                    self._fpmap[it.owner[0]] = fpu
        return self._fpmap.get(ref)

    def _anchor(self, tok):
        from kae.route.critical_grid import Anchor
        ref, num = tok.rsplit(".", 1)
        for it in self.sp.pads_by_fp.get(self._fp(ref), []):
            if str(it.owner[1]) == num:
                return Anchor(it.geom, tuple(it.layers), it.pos, kind="pad")
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kae.em.pnr")
    ap.add_argument("board")
    ap.add_argument("out")
    ap.add_argument("--plain", action="store_true")
    ap.add_argument("--lam", type=float, default=30.0)
    ap.add_argument("--pitch", type=float, default=0.25)
    ap.add_argument("--refresh", type=int, default=6)
    ap.add_argument("--verify", action="store_true",
                    help="per priced net, route a physics and a plain candidate and keep the one a field solve says harms less")
    ap.add_argument("--intent", help="intent file (JSON): operating conditions, part facts, requirements")
    ap.add_argument("--seed", type=int, default=0, help="seed of the corners sampled over the parameters' intervals")
    a = ap.parse_args(argv)
    from kae.excite.beliefs import load_intent
    PhysRouter(a.board, a.out, pitch=a.pitch, lam=a.lam, plain=a.plain, refresh=a.refresh, verify=a.verify,
               intent=load_intent(a.intent), seed=a.seed).route()


if __name__ == "__main__":
    main()
