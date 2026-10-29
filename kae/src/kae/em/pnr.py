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


def phi_prime(u):
    """Slope of the margin price phi (kae.physics.priors): linear to 1, then a quadratic barrier."""
    return 1.0 if u <= 1 else min(1.0 + 8.0 * (u - 1.0), 50.0)


class PhysRouter:
    def __init__(self, path, out, pitch=0.25, lam=30.0, nsub=2, plain=False, refresh=4, log=print, work=None):
        from kae.board.kicad_file import load
        from kae.circuit import brief as B
        from kae.excite import models as M
        from kae.excite import observe as O
        from kae.excite import sources as S
        from kae.route import critical_write as W
        self.log, self.pitch, self.lam, self.nsub, self.plain, self.refresh = log, pitch, lam, nsub, plain, refresh
        self.src_path, self.out = Path(path), Path(out)
        self.work = Path(work or tempfile.mkdtemp(prefix="kae-pnr-"))
        b = load(path)
        self.brief = B.build(b)
        bd = self.bd = M.build(b, self.brief)
        self.srcs = S.add_all(bd, self.brief)
        self.obs = O.observers(bd, self.brief, self.srcs)
        self.f = O.F_PATTERN
        self.w = 2 * math.pi * self.f
        self.pat = {}
        for s in self.srcs:
            self.pat[("s", s.name)] = bd.circuit.solve(self.f, [s])[s.name]["J"]
        for o in self.obs:
            self.pat[("o", o.name)] = O.pattern(bd, o, self.f)
        # priced nets: every non-ground net carrying pattern current (above 1% of the pattern's largest)
        load_ = {}
        for key, J in self.pat.items():
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
        """Mesh the copper as it stands, short what is not yet connected, solve every pattern."""
        t0 = time.time()
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
        net = ES.Network(bm.m)
        op = ES.Operator(net)
        self.prices, self.pot_at = {}, {}
        layers = list(range(len(bm.m.layers)))
        keys, injs = [], []
        for key, J in self.pat.items():
            inj = {q: v for q, v in J.items() if q in ok}
            if inj:
                keys.append(key)
                injs.append(inj)
        for key, (v, info) in zip(keys, ES.potentials_many(bm.m, injs, self.f, net=net, op=op)):
            if v is None:
                self.log(f"pnr: pattern {key[1]} cannot close in the copper ({info['open_terms'][:4]}); unpriced")
                continue
            cp = T1.cell_potentials(info["sys"], info["x"])
            self.prices[key] = {l: T1.price(bm.m, op, info["I"], cp, None, l, w=self.w) for l in layers}
            self.pot_at[key] = v
        self.mesh = bm.m
        self.layer_names = [l.name for l in bm.m.layers]
        self._weights()
        self.log(f"pnr: fields of {len(self.prices)} patterns on {bm.m.nx}x{bm.m.ny}x{len(layers)} "
                 f"({shorted} unrouted connections shorted) in {time.time() - t0:.1f}s")

    def _weights(self):
        """w[(k, s)] = phi'(u) sign(L) scale_s / bound_k: harm (u) per henry of L_ks."""
        from kae.excite import observe as O
        self.wts = {}
        self.harm = {}
        src = {s.name: s for s in self.srcs}
        for o in self.obs:
            kk = ("o", o.name)
            for s in self.srcs:
                ks = ("s", s.name)
                if o.kind == "overshoot" and o.meta.get("source") != s.name:
                    continue
                if ks not in self.pot_at:
                    continue
                r = sum(self.pat[kk].get(q, 0) * self.pot_at[ks].get(q, 0) for q in self.pat[kk] if q in self.pot_at[ks])
                L = r.imag / self.w
                volts, bound = O.size(o, src[s.name], L)
                u = volts / bound if bound else 0.0
                scale = volts / abs(L) if abs(L) > 0 else (O.size(o, src[s.name], 1e-9)[0] / 1e-9)
                self.wts[(kk, ks)] = phi_prime(u) * np.sign(L or 1.0) * scale / (bound or 1.0)
                self.harm[(o.name, s.name)] = u

    # ------------------------------------------------------------------ hop prices
    def hop_currents(self, n, a_pads, b_pads):
        """Current of each pattern on a hop joining island A (pads a_pads) toward island B of net n:
        the pattern's injection summed over the islands on A's side of the hop (one hop per pair of
        islands in a chain, so A's side is A)."""
        out = {}
        for key, J in self.pat.items():
            i = sum(J.get(q, 0) for q in a_pads)
            if abs(i) > 1e-6:
                out[key] = complex(i).real            # injected at A's pads, flowing A -> B in the copper
        return out

    def phys(self, cur, width):
        """The move-cost callable for GridRouter.connect, for a hop carrying `cur` {pattern: A}."""
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
            if self.plain:
                return dict(self=selfc, px=px, py=py, pot=pot, void=void, floor=1.0)
            for li, lname in enumerate(layers):
                L = self.layer_names.index(lname) if lname in self.layer_names else None
                if L is None:
                    continue
                ref, main = T1.reference(m, L)
                zs = np.array([l.z + l.t / 2 for l in m.layers])
                h = np.where(ref >= 0, np.abs(zs[np.maximum(ref, 0)] - zs[L]) - m.layers[L].t, 1.6)
                Lp = strip_L_per_mm(width, h[sel])
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
                selfc[li] = max(wself, 0.0) * Lp
            return dict(self=lam * selfc, px=lam * px, py=lam * py, pot=lam * pot, void=void, floor=0.2)
        return f

    # ------------------------------------------------------------------ routing
    def route(self):
        from kae.route.critical_grid import Anchor
        t0 = time.time()
        done = 0
        self.failed = []
        for n in self.nets:
            if done % self.refresh == 0:
                self.solve_fields()
            isl = [g for g in self.islands.get(n, []) if g]
            if len(isl) < 2:
                continue
            # chain the islands nearest-first (a spanning tree on island centroids)
            def cen(g):
                pts = [self._pad_xy(q) for q in g]
                return np.mean(pts, axis=0)
            left = isl[1:]
            tree = [isl[0]]
            while left:
                best = min(((a, b_) for a in tree for b_ in left), key=lambda ab: np.linalg.norm(cen(ab[0]) - cen(ab[1])))
                a, b_ = best
                cur = self.hop_currents(n, b_, a)
                layer0 = self.sp.cu
                width = self.sp.width_limits(n, layer0[0])[1]
                if any(k[0] == "s" and k[1].startswith("cell:") for k in cur):
                    # a commutation current: wide copper lowers its inductance per length
                    width = self.sp.clamp_width(n, layer0[0], max(width, 0.8))
                srcs = [self._anchor(q) for q in b_]
                dsts = [self._anchor(q) for q in a]
                rt = self.router.connect(n, [x for x in srcs if x], [x for x in dsts if x], width, list(layer0),
                                         phys=self.phys(cur, width))
                if rt is None or not rt.segs and not rt.vias:
                    if rt is None:
                        self.failed.append((n, b_[0], a[0]))
                else:
                    for l, p0, p1 in rt.segs:
                        it = self.sp.add_track(n, l, rt.width, p0, p1, owner=("pnr", n))
                        self.tracks.append((n, l, rt.width, p0, p1, "", False))
                    for (x, y) in rt.vias:
                        self.sp.add_via(n, x, y, owner=("pnr", n))
                        D, d = self.sp.via_size(n)
                        self.vias.append((n, x, y, D, d, "", False))
                tree.append(b_)
                left.remove(b_)
            done += 1
        from kae.route import critical_write as W
        W.append_items(self.base, self.out, tracks=self.tracks, vias=self.vias)
        for ext in (".kicad_pro", ".kicad_dru"):
            s_ = self.base.with_suffix(ext)
            if s_.exists():
                import shutil
                shutil.copy2(s_, self.out.with_suffix(ext))
        self.log(f"pnr: {len(self.tracks)} tracks, {len(self.vias)} vias, {len(self.failed)} failed hops, "
                 f"{time.time() - t0:.1f}s")
        return self

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
    ap.add_argument("--refresh", type=int, default=4)
    a = ap.parse_args(argv)
    PhysRouter(a.board, a.out, pitch=a.pitch, lam=a.lam, plain=a.plain, refresh=a.refresh).route()


if __name__ == "__main__":
    main()
