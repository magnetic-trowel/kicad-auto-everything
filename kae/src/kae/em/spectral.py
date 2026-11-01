# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Router prices weighted over the whole spectrum (stage R4 of
docs/topics/architecture/physics-frequency-coverage.md).

At each refresh the copper as it stands (every unrouted connection a field-free short) holds the whole
circuit (kae.excite.circuit.lump_all), and kae.em.reduce projects it onto a real basis V of order m:
every source and observer is a fixed port, and its solution at any w is V y_P(w).

A new hop perturbs that system. By reciprocity (Tellegen) its first-order change of the transfer
impedance of an (observer k, source s) pair is

    dZ_ks(w) = jw [ i_k i_s L_hop + i_k Pi_s(w) + i_s Pi_k(w) ] + i_k X_s(w) + i_s X_k(w)

- i_P(w): the current pattern P drives through the hop, i.e. what the hop's island injects. It is read
  from the model's part currents, so the switch-node ring and the copper's own current split are in it.
- Pi_P: the flux of P's currents through the loop of the hop and its return (kae.em.t1).
- X_P: the potential steps where that return crosses a void.

Both are linear in the currents. So Pi_P(w) = sum_j F_j y_Pj(w), with F_j the price field of basis
vector j: m fixed fields per refresh, and every frequency's currents are a combination of them (option
"basis fields"; the alternative, one 10 MHz field per pattern with spectral weights, misses the current
split's change below the R-L transition and the ring above 30 MHz: tools/research/physics/em_r4_check.py).

The harms are the evaluator's (kae.excite.wideband). At each corner of the ledger, each pair's waveform
is v(t) = sum_n Re(a_n H_ks(n w_sw) e^{j n w_sw t}), with a_n the trapezoid's harmonics and H_ks the
layout share. Its harm is u = max|v| / bound. With t* the time of the peak,

    du = sgn v(t*) / bound * sum_n Re(a_n e^{j n w_sw t*} dZ_ks(n w_sw)).

The robust objective's derivative is therefore a complex weight G_ks(f) per harmonic. A hop's cost is
sum_ks sum_f Re(G_ks(f) dZ_ks(f)). For the move-cost arrays that is one real combination per hop,
sum_j c_j F_j, with c_j = sum_f sum_P Re(A_P(f) y_Pj(f)) and A_P(f) = sum over P's pairs of G jw i_other.

The router (kae.em.pnr) sees one pseudo pair whose price is that combination; it keeps its own self,
via, crossing and cut terms. Cutting a return pour is bilinear in two patterns' currents, so its weight
matrix over the basis is split into rank-one pseudo pairs (its leading eigenvectors).

Cost: the first refresh builds the model greedily, as the evaluator does. Later refreshes recycle its
snapshot frequencies, solve them concurrently, and add a snapshot only where the calibrated error
estimate says so.
"""
from __future__ import annotations

import json
import math
import time

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy import ndimage

from kae.excite import harm as HA
from kae.excite import observe as O
from kae.excite import spectrum as SP

from . import fields as EF
from . import reduce as RD
from . import solve as ES
from . import t1 as T1

SNAP_TOL = 1e-5         # the snapshots' solver tolerance (port quantities are variational: kae.em.solve.TOL)
MODEL_TOL = 1e-2        # the router model's tolerance on every pair's layout share (the evaluator's: 1e-3)
CUT_RANK = 12           # rank-one terms kept of the pour-cut weight matrix
GRID = 12               # the greedy build's error grid, 1 kHz .. f_max (the evaluator's: 24)
Z_SHORT = 1e-5          # ohm: an unrouted connection with a port (kae.em.hopport), a part instead of a node merge
F_LOG = O.F_PATTERN     # the frequency the per-pair dL log is read at (comparable with the 10 MHz router)


def _key(f):
    return round(f / 1e3)


def peak(V):
    """(|v(t*)|, sgn v(t*), phases n w t*) of the waveform v(t) = sum_n Re(V_n e^{j n w t}), n = 1..len(V),
    sampled as kae.excite.spectrum.totals does: d|v(t*)| = sgn sum_n Re(e^{j phase_n} dV_n)."""
    n = np.arange(1, len(V) + 1)
    N = int(2 ** np.ceil(np.log2(8 * (len(V) + 1))))
    spec = np.zeros(N // 2 + 1, complex)
    spec[1:len(V) + 1] = V * (N / 2)
    wave = np.fft.irfft(spec, n=N)
    t = int(np.argmax(np.abs(wave)))
    return float(abs(wave[t])), float(np.sign(wave[t]) or 1.0), 2 * np.pi * n * t / N


def path_integrals(bf, L, cells):
    """(flux (m,), crossing (2, m)): a path's line integral of every basis vector's price fields on routing
    layer L (kae.em.t1.path_price for each), for a unit current along cells [(j, i), ...]; the crossing's
    rows are the R and the L part (dZ = cr[0] y + jw cr[1] y)."""
    jj = np.array([c[0] for c in cells])
    ii = np.array([c[1] for c in cells])
    di, dj = np.diff(ii), np.diff(jj)
    Px, Py = bf["Px"][L][:, jj, ii], bf["Py"][L][:, jj, ii]
    fl = (0.5 * (Px[:, :-1] + Px[:, 1:]) * di + 0.5 * (Py[:, :-1] + Py[:, 1:]) * dj).sum(1)
    cr = np.zeros((2, len(fl)))
    tm = bf["tmpl"][L]
    for q_, sfx in ((0, ""), (1, "L")):
        for ph, vo in ((bf["phi" + sfx][L], tm.void), (bf["phi2" + sfx][L], tm.void2)):
            v = vo[jj, ii]
            stp = v[:-1] | v[1:]
            if stp.any():
                q = ph[:, jj, ii]
                cr[q_] += (q[:, 1:] - q[:, :-1])[:, stp].sum(1)
    return fl, cr


class Spectral:
    """The whole-spectrum prices of a kae.em.pnr.PhysRouter `r` (which calls it at every refresh and hop)."""

    def __init__(self, r, tol=MODEL_TOL, snap_tol=SNAP_TOL, workers=1, probes=True, log=print, grid=GRID):
        self.r, self.tol, self.snap_tol, self.workers, self.probes, self.log = r, tol, snap_tol, workers, probes, log
        self.grid = grid
        self.freqs, self.cal = None, None
        self.costs = []
        self.trace = r.work / "spectral.jsonl"

    # ------------------------------------------------------------------ refresh
    def refresh(self, bm, base, ok, t0, sig, shorted):
        """The model of the copper as it stands, its harms and weights, the basis price fields; sets the
        router's state (prices, wts, K, H, ...) and logs predicted against actual changes."""
        from kae.excite.circuit import lump_all, port
        from kae.excite.wideband import EPS_EFF, F_TOP, THETA, _ideal, _wave_params
        r = self.r
        m = bm.m
        # the field-free shorts; the upcoming nets' connections, along the router's own tree, as parts of
        # negligible impedance with an EMF port each (kae.em.hopport); then the whole circuit
        edges = self._tree_shorts(m, base, ok, self._upcoming())

        def mpad(t):
            if t not in ok:
                raise KeyError(t)
            return t
        term, skipped = lump_all(r.bd, mpad, lambda a, c, zf, nm: m.part(a, c, name=nm, zf=zf), m.internal_node)
        srcs, obs, ports = [], [], []
        for x in list(r.srcs) + list(r.obs):
            try:
                if getattr(x, "kind", "") == "cm" and "pads" in x.meta:
                    a, b = x.meta["pads"]
                    p = {term(None, a): 1.0, term(None, b): -1.0}
                else:
                    p = port(term, x.a, x.b, x.pa, x.pb)
            except (KeyError, ValueError):
                self.log(f"spectral: {x.name}: a port terminal is outside the copper model; left out")
                continue
            (srcs if x in r.srcs else obs).append(x)
            ports.append(p)
        ns = len(srcs)
        net = ES.Network(m)
        op = ES.Operator(net)
        t_mesh = time.time() - t0
        rows, cols = list(range(ns, ns + len(obs))), list(range(ns))
        at_l = {q.name: k for k, (_, _, q) in enumerate(net.lump)}
        edges = [dict(e, lump=at_l[e["name"]]) for e in edges if e["name"] in at_l]
        nP0 = len(ports)
        model = RD.Reduced(op, ports, log=lambda s: None, emf=[net.off["l"] + e["lump"] for e in edges])
        xs = [r.window[0], r.window[2]]
        ys = [r.window[1], r.window[3]]
        diag = math.hypot(xs[1] - xs[0], ys[1] - ys[0]) * 1e-3
        f_max = min(F_TOP, THETA * 299792458.0 / math.sqrt(EPS_EFF) / (2 * math.pi * diag))
        ideal_cache = {}

        def ideal(s, f):
            k = (s.name, _key(f))
            if k not in ideal_cache:
                ideal_cache[k] = _ideal(r.bd, s, obs, f)
            return ideal_cache[k]

        def scale(f):
            Zl = model.Z(f)[np.ix_(rows, cols)] - np.stack([ideal(s, f) for s in srcs], 1)
            return np.abs(Zl) + 1e-3 * np.abs(Zl).max()
        t1 = time.time()
        built = self._model(model, f_max, rows, cols, scale)
        t_model = time.time() - t1
        # ---------------------------------------------------------------- harmonics and weights
        t2 = time.time()
        F, at = [], {}

        def fidx(f):
            k = _key(f)
            if k not in at:
                at[k] = len(F)
                F.append(f)
            return at[k]
        waves = {}
        for j, s in enumerate(srcs):
            for c, val in enumerate(r.cval[s.name]):
                I, D, tr, fsw = _wave_params(None, s, val)
                n_max = int(f_max // fsw)
                if n_max < 1:
                    continue
                n = np.arange(1, n_max + 1)
                waves[(j, c)] = (n, 2 * SP.trapezoid(I, D, tr, fsw, n), np.array([fidx(x * fsw) for x in n]), val)
        i_log = fidx(F_LOG)
        F = np.array(F)
        Yall = np.stack([model.solve(f) for f in F])                      # (nF, m, nP + edges)
        Y = Yall[:, :, :nP0]
        Z = np.einsum("mp,fmq->fpq", model.Pr[:, :nP0], Y)                 # (nF, nP, nP): Z_pq = p_p^T phi_q
        Zi = {j: np.stack([ideal(s, f) for f in F]) for j, s in enumerate(srcs)}     # (nF, nobs)
        ncp = len(next(iter(r.cval.values()), [None]))
        tot = np.zeros(ncp)
        pairs = []                                  # (observer index, source index or None for cm, name key)
        U, sgn, peak_t = {}, {}, {}
        cm_amp = {}
        for k, o in enumerate(obs):
            for j, s in enumerate(srcs):
                if o.kind == "overshoot" and o.meta.get("source") != s.name:
                    continue
                pairs.append((k, j))
                us, sg, tt = np.zeros(ncp), np.zeros(ncp), {}
                for c in range(ncp):
                    if (j, c) not in waves:
                        continue
                    n, a, fi, val = waves[(j, c)]
                    H = Z[fi, ns + k, j] - Zi[j][fi, k]
                    V = a * H
                    if o.kind == "cm":
                        band = (F[fi] >= O.F_CM[0]) & (F[fi] <= O.F_CM[1])
                        d = cm_amp.setdefault(k, [dict() for _ in range(ncp)])[c]
                        for q in np.nonzero(band)[0]:
                            d[fi[q]] = d.get(fi[q], 0.0) + abs(V[q])
                        continue
                    bound = o.bound
                    if o.kind == "overshoot" and "V_max_V" in val:
                        bound = max(val["V_max_V"] - val.get("V_V", 0.0), 1e-3)
                    pk, sg_, th = peak(V)
                    us[c] = pk / bound if bound else 0.0
                    sg[c] = sg_ / bound if bound else 0.0
                    tt[c] = th
                if o.kind != "cm":
                    U[(k, j)], sgn[(k, j)], peak_t[(k, j)] = us, sg, tt
                    tot += np.where(us <= 1, us, us + 4 * (us - 1) ** 2)
        for k, per in cm_amp.items():
            us = np.array([max((v / (O.CM_V_LIM_HZ / F[q]) for q, v in d.items()), default=0.0) for d in per])
            U[(k, None)] = us
            tot += np.where(us <= 1, us, us + 4 * (us - 1) ** 2)
        for c, ob in enumerate(r.dc_obs or []):
            tot[c] += HA.phi(ob["loss"][0]) + sum(HA.phi(d[2]) for d in ob["drops"])
        if r.cap:                             # capacitive pairs (kae.em.cprice) join the same objective
            tot = tot + r.cap.corner_phi(r.capf)
        H, idx = HA.robust(list(tot))
        if r.cap:
            from .pnr import phi_prime as _pp
            r.cap.set_weights(r.capf, idx, _pp)
        # G[(k, j)] (nF,): d(robust objective)/d(layout share) per harmonic; G0: d(u at the typical corner)
        from .pnr import UNPRICED, phi_prime
        G, G0 = {}, {}
        for (k, j), us in U.items():
            if j is None:
                continue
            g, g0 = np.zeros(len(F), complex), np.zeros(len(F), complex)
            for c in set(idx) | {0}:
                if (j, c) not in waves or c not in peak_t[(k, j)]:
                    continue
                n, a, fi, _ = waves[(j, c)]
                z = sgn[(k, j)][c] * a * np.exp(1j * peak_t[(k, j)][c])
                if c in idx:
                    np.add.at(g, fi, phi_prime(us[c]) * z / len(idx))
                if c == 0:
                    np.add.at(g0, fi, z)
            G0[(k, j)] = g0
            if obs[k].kind not in UNPRICED:
                G[(k, j)] = g
        t_harm = time.time() - t2
        # ---------------------------------------------------------------- basis fields
        t3 = time.time()
        bf = self._basis(model, net, op, m, r.ref_ids)
        # the pour-cut weight over the basis: sum_ks sum_f Re(G jw C X_k X_s), X = K y
        w = 2 * np.pi * F
        Q = np.zeros((model.V.shape[1],) * 2)
        for (k, j), g in G.items():
            Q += np.real(np.einsum("f,fa,fb->ab", g * 1j * w, Y[:, :, ns + k], Y[:, :, j]))
        Q = 0.5 * (Q + Q.T)
        lam_, vec = np.linalg.eigh(Q)
        keep = np.argsort(-np.abs(lam_))[:CUT_RANK]
        keep = [q for q in keep if abs(lam_[q]) > 1e-6 * (np.abs(lam_).max() or 1)]
        K, wcut = {}, {}
        for q in keep:
            key = ("cut", int(q))
            K[key] = {l: (np.tensordot(vec[:, q], bf["Kx"][l], 1), np.tensordot(vec[:, q], bf["Ky"][l], 1))
                      for l in bf["Kx"]}
            wcut[(key, key)] = float(lam_[q])
        t_fields = time.time() - t3
        # ---------------------------------------------------------------- the router's state
        st = dict(model=model, net=net, op=op, m=m, srcs=srcs, obs=obs, ports=ports, ns=ns, F=F, w=w, Y=Y, Z=Z,
                  Zi=Zi, G=G, G0=G0, pairs=pairs, i_log=i_log, bf=bf, U=U, f_max=f_max,
                  Jb=self._pad_injection(model, net, ports), edges=self._edge_data(model, edges, Yall, nP0, w))
        prev = r.spec_m
        r.spec_m, r.spec_hops = st, ()
        r.mesh, r.op = m, op
        r.layer_names = [l.name for l in m.layers]
        r.K, r._cut_w = K, wcut
        self._pseudo(np.zeros(model.V.shape[1]), np.zeros(model.V.shape[1]), 0.0, [])
        r.Lks, r.harm, r.u_c = {}, {}, {}
        for (k, j) in pairs:
            nm = (obs[k].name, srcs[j].name)
            r.Lks[nm] = float((Z[i_log, ns + k, j] - Zi[j][i_log, k]).imag / w[i_log])
            us = U.get((k, j), U.get((k, None)))
            if us is not None:
                r.u_c[nm] = us
                r.harm[nm] = float(us[0])
        r.H, r.H_typ, r.H_corners = H, float(tot[0]), idx
        self._compare(prev, st, H)
        r._H, r._pred, r._sig = H, 0.0, sig
        r.spec_pred = {}
        top = sorted(((float(np.mean(np.sort(us)[-len(idx):])), float(us[0]), (obs[k].name, srcs[j].name if j is not None else "all"))
                      for (k, j), us in U.items()), reverse=True)[:6]
        self.log("pnr: spectral harms (u: mean of the worst corners, typical): "
                 + "; ".join(f"{nm[0]} <- {nm[1]} {a:.2f}, {b:.2f}" for a, b, nm in top))
        cost = dict(total=time.time() - t0, mesh=t_mesh, model=t_model, harmonics=t_harm, fields=t_fields, **built)
        self.costs.append(cost)
        self.log(f"pnr: spectral fields of {len(ports)} ports and {len(edges)} connection ports on {m.nx}x{m.ny}x{len(m.layers)} ({shorted} unrouted "
                 f"connections shorted): model order {model.V.shape[1]} from {len(model.freqs)} snapshots "
                 f"{[round(f / 1e6, 3) for f in model.freqs]} MHz ({built['mode']}), {len(F)} harmonics to "
                 f"{f_max / 1e6:.0f} MHz; {cost['total']:.1f}s (mesh {t_mesh:.0f}, model {t_model:.0f}: snapshots "
                 f"{built['t_snap']:.0f}, probes {built['t_probe']:.0f}; harmonics {t_harm:.1f}, fields {t_fields:.1f}); "
                 f"harm robust {H:.2f}, typical {tot[0]:.2f}")

    def _model(self, model, f_max, rows, cols, scale):
        """First refresh: the greedy build (the evaluator's, at the router's tolerance). Later ones recycle
        its frequencies: all snapshots at once, then the calibrated estimate at the probes (geometric
        midpoints between snapshots) adds one where it exceeds the tolerance."""
        if self.freqs is None:
            t = time.time()
            model.build(f_max, fmin=1e3, tol=self.tol, rows=rows, cols=cols, scale=scale, grid=self.grid,
                        f0=(0.0, min(F_LOG, f_max / 3)), snap_tol=self.snap_tol)
            self.freqs = list(model.freqs)
            self.cal = max([tr / es for _, tr, es in model.calibration if es > 0], default=1.0)
            return dict(mode="greedy", t_snap=time.time() - t, t_probe=0.0, est=model.history[-1][3] if model.history else None)
        t = time.time()
        model.snapshots(self.freqs, tol=self.snap_tol, workers=self.workers)
        t_snap = time.time() - t
        t = time.time()
        est = None
        added = []
        if self.probes:
            for _ in range(2):
                fs = sorted(f for f in model.freqs if f > 0)
                cand = [math.sqrt(a * b) for a, b in zip([1e3] + fs, fs + [f_max]) if b / a > 1.5]
                worst, fw = 0.0, None
                for f in cand:
                    E = model.error(f, rows, cols)
                    S = scale(f)
                    rel = float(np.max(E / np.maximum(S, 1e-12 * np.max(np.abs(S)) + 1e-300))) * self.cal
                    if rel > worst:
                        worst, fw = rel, f
                est = worst
                if worst < self.tol or fw is None:
                    break
                model.snapshot(fw, tol=self.snap_tol)
                self.freqs.append(fw)
                added.append(fw)
        return dict(mode="recycled" + (f" + {[round(f / 1e6, 3) for f in added]} MHz" if added else ""), t_snap=t_snap,
                    t_probe=time.time() - t, est=est)

    def _basis(self, model, net, op, m, ref_ids):
        """Per routing layer, every basis vector's price fields (as kae.em.t1.price, for unit coefficient):
        Px, Py (flux minus the share-weighted flux of the return planes), phi / phi2 (the lower / upper main
        plane's potential extended into its voids, times its share), psi (the transfer potential); their
        masks; and per layer the sheet currents Kx, Ky.

        The potentials are not the projection's own: in the reduced saddle system they are multipliers of
        the projected KCL, right at the ports (variational) and at the snapshots, but off by factors of 10
        between them across a slot (tools/research/physics/em_r4_check.py --slot). They are recovered from
        the currents through the copper's branch equation D phi = (R + jw L) I instead, by least squares
        over the copper branches (exact for an exact current): phi(w) = phi_R y + jw phi_L y, with the R
        and the L parts kept apart as fields (phi, phi2, psi and their *L twins)."""
        nb = model.nb
        VI = model.V[:nb]
        mm = VI.shape[1]
        nl = len(m.layers)
        Fl = {}
        for j in range(0, mm, 2):
            I = VI[:, j].astype(complex) + (1j * VI[:, j + 1] if j + 1 < mm else 0.0)
            for key, v in EF.flux(op, I).items():
                arr = Fl.setdefault(key, np.zeros((mm, m.ny, m.nx), np.float32))
                arr[j] = v.real
                if j + 1 < mm:
                    arr[j + 1] = v.imag
        sy = model.sys0
        lo = net.off["l"]
        Dc = sy.D[:lo]                                     # the copper's branches (bars, vias), not the parts
        G = (Dc.T @ Dc).tocsc() + 1e-9 * sp.identity(sy.nfree, format="csc")
        LV = model.LV if getattr(model, "LV", None) is not None and model.LV.shape[1] == mm else \
            np.concatenate([op.L_apply(VI[:, k:k + ES.BATCH].astype(complex)).real for k in range(0, mm, ES.BATCH)], 1)
        lu = spla.splu(G)
        phR = lu.solve(np.ascontiguousarray(Dc.T @ (net.R[:lo, None] * VI[:lo])))
        phL = lu.solve(np.ascontiguousarray(Dc.T @ (LV[:lo] + net.Lc[:lo, None] * VI[:lo])))
        del LV
        occ = net.node >= 0
        nd = net.node[occ]
        kf = sy.free_idx[nd]
        comp = np.full(m.lab.shape, -1, np.int64)
        comp[occ] = net.comp[nd]
        out = dict(Px={}, Py={}, Rx={}, Ry={}, phi={}, phi2={}, psi={}, phiL={}, phi2L={}, psiL={}, tmpl={}, Kx={}, Ky={})
        plane = {}
        for k in range(nl):
            occk = T1.ref_copper(m, k, ref_ids)
            if occk.any():
                _, (jj, ii) = ndimage.distance_transform_edt(~occk, return_indices=True)
                void = ~occk
                ext = []
                for ph in (phR, phL):
                    pot = np.zeros((mm,) + m.lab.shape, np.float32)
                    pot[:, occ] = np.where(kf[None, :] >= 0, ph[np.maximum(kf, 0)].T, 0.0)
                    ext.append(np.ascontiguousarray(pot[:, k][:, jj, ii]))
                plane[k] = (ext, void, T1._splits(void, occk, comp[k]), occk)
        for L in range(nl):
            if (L, "x") not in Fl:
                continue
            up, dn, hu, hd, a_up, a_dn = T1.references(m, L, ref_ids)
            Px, Py = Fl[(L, "x")].copy(), Fl[(L, "y")].copy()
            for ref, a in ((up, a_up), (dn, a_dn)):
                for k in np.unique(ref[ref >= 0]):
                    sel = ref == k
                    Px[:, sel] -= (a[sel] * Fl[(int(k), "x")][:, sel]).astype(np.float32)
                    Py[:, sel] -= (a[sel] * Fl[(int(k), "y")][:, sel]).astype(np.float32)
            z = np.zeros((mm, m.ny, m.nx), np.float32)
            f = np.zeros((m.ny, m.nx), bool)
            out["Px"][L], out["Py"][L] = Px, Py
            out["Rx"][L], out["Ry"][L] = Fl[(L, "x")], Fl[(L, "y")]        # the raw flux: no return subtracted
            for q, sfx in ((0, ""), (1, "L")):
                terms, psi = {}, np.zeros((mm, m.ny, m.nx), np.float32)
                for side, a in (("up", a_up), ("dn", a_dn)):
                    k = T1.main_plane(m, L, side, ref_ids)
                    if k >= 0 and k in plane:
                        ext, void, split, occk = plane[k]
                        share = float(np.median(a[occk]))
                        terms[side] = ((share * np.where(split[None], 0.0, ext[q])).astype(np.float32), void & ~split, split)
                        psi += (a[None] * ext[q]).astype(np.float32)
                pu, vu, su = terms.get("up", (z, f, f))
                pd, vd, sd = terms.get("dn", (z, f, f))
                out["phi" + sfx][L], out["phi2" + sfx][L], out["psi" + sfx][L] = pd, pu, psi
            tm = T1.Price(None, None, None, dn, vd, sd | su)
            tm.void2, tm.h_up, tm.h_dn = vu, hu, hd
            out["tmpl"][L] = tm
        # sheet currents: each cell's bar currents summed through the thickness, per basis vector
        for o, key in (("x", "Kx"), ("y", "Ky")):
            f = net.fil[o]
            a0, n = net.off[o], len(f["a"])
            for l in range(nl):
                sel = np.nonzero(np.isin(f["s"], net.sub_of[l]))[0] if n else np.zeros(0, int)
                if not len(sel):
                    out[key][l] = np.zeros((mm, m.ny, m.nx), np.float32)
                    continue
                S = sp.csr_matrix((np.ones(len(sel)), (f["j"][sel] * m.nx + f["i"][sel], np.arange(len(sel)))),
                                  shape=(m.ny * m.nx, len(sel)))
                out[key][l] = np.asarray((S @ VI[a0 + sel]).T, np.float32).reshape(mm, m.ny, m.nx)
        return out

    def _pad_injection(self, model, net, ports):
        """{pad: (row (m,), port injections (nP,))}: the current the parts and ports push into the copper
        at each pad terminal, as a linear form of the reduced coefficients (plus the ports' fixed part)."""
        Vl = model.Vl
        out = {}
        for k, (_, _, q) in enumerate(net.lump):
            for t, sg in ((q.a, -1.0), (q.b, 1.0)):            # a part's current leaves the copper at a
                if t.startswith("node:"):
                    continue
                row = out.setdefault(t, [np.zeros(Vl.shape[1]), np.zeros(len(ports))])
                row[0] += sg * Vl[k]
        for P, p in enumerate(ports):
            for t, v in p.items():
                row = out.setdefault(t, [np.zeros(Vl.shape[1]), np.zeros(len(ports))])
                row[1][P] += v
        return out

    # ------------------------------------------------------------------ hops
    def currents(self, pads):
        """(nF, nP) complex: the current every port's pattern drives from the island of `pads` into the hop,
        at every harmonic frequency."""
        st = self.r.spec_m
        Jb = st["Jb"]
        e = st.get("edges", {}).get(tuple(pads))
        if e is not None:
            return e["I"]                          # the model's own current through the connection
        row = np.zeros(st["Y"].shape[1])
        fix = np.zeros(st["Y"].shape[2])
        for q in pads:
            if q in Jb:
                row += Jb[q][0]
                fix += Jb[q][1]
        return np.einsum("m,fmp->fp", row, st["Y"]) + fix[None]

    def _adjoint(self, i):
        """A (nF, nP) and B (nF, nP): per port, the weight of its solution's coefficients in the hop's flux
        cost (A, with jw) and its crossing cost (B), for hop currents i; and the self weight."""
        st = self.r.spec_m
        ns, jw = st["ns"], 1j * st["w"]
        B = np.zeros(i.shape, complex)
        g_self = 0.0
        for (k, j), g in st["G"].items():
            kp = ns + k
            B[:, j] += g * i[:, kp]
            B[:, kp] += g * i[:, j]
            g_self += float(np.real(np.sum(g * jw * i[:, kp] * i[:, j])))
        return B * jw[:, None], B, g_self

    def hop(self, cur, width=0.25):
        """Pseudo state for PhysRouter.phys: one pair of unit weight whose price fields are this hop's
        combination of the basis fields; returns the pseudo hop currents."""
        st = self.r.spec_m
        pads = next((k[1] for k in cur if k[0] == "pads"), ())
        e = st.get("edges", {}).get(tuple(pads))
        if e is not None:
            return self._hop_port(e, width)
        i = self.currents(pads)
        A, B, g_self = self._adjoint(i)
        c = np.real(np.einsum("fp,fmp->m", A, st["Y"]))
        d = np.real(np.einsum("fp,fmp->m", B, st["Y"]))
        e = [float(np.real(np.sum(A * ih))) for _, ih in self.r.spec_hops]
        return self._pseudo(c, d, g_self, e)

    def _pseudo(self, c, d, g_self, e, raw=False):
        """raw: c weighs the basis's raw flux (kae.em.hopport: nothing subtracted, no crossing terms)."""
        r, st = self.r, self.r.spec_m
        bf = st["bf"]
        comb, zero = {}, {}
        for L, tm in bf["tmpl"].items():
            Px = np.tensordot(c, bf["Rx" if raw else "Px"][L], 1)
            Py = np.tensordot(c, bf["Ry" if raw else "Py"][L], 1)
            for eh, (dF, _) in zip(e, r.spec_hops):
                if eh and L in dF:
                    Px = Px + eh * dF[L][0]
                    Py = Py + eh * dF[L][1]
            def pot(k):                     # the crossing potential: R part with d, L part (jw inside c) with c
                if raw:
                    return np.zeros_like(Px)
                return np.tensordot(d, bf[k][L], 1) + np.tensordot(c, bf[k + "L"][L], 1)
            pr = T1.Price(Px, Py, pot("phi"), tm.ref, tm.void, tm.split)
            pr.phi2, pr.void2, pr.psi, pr.h_up, pr.h_dn = pot("phi2"), tm.void2, pot("psi"), tm.h_up, tm.h_dn
            comb[L] = pr
            z = np.zeros_like(Px)
            pz = T1.Price(z, z, z, tm.ref, np.zeros_like(tm.void), np.zeros_like(tm.split))
            pz.phi2, pz.void2, pz.psi = z, np.zeros_like(tm.void), z
            zero[L] = pz
        r.prices = {("spec", "s"): comb, ("spec", "k"): zero}
        r.wts = {(("spec", "k"), ("spec", "s")): 1.0, **r._cut_w}
        return {("spec", "k"): 1.0, ("spec", "s"): g_self}

    def _path_cells(self, p0, p1):
        m = self.r.mesh
        n = max(2, int(math.ceil(math.dist(p0, p1) / (m.pitch / 2))) + 1)
        cells = []
        for t in np.linspace(0, 1, n):
            c = m.cell(p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
            if 0 <= c[0] < m.ny and 0 <= c[1] < m.nx and (not cells or c != cells[-1]):
                cells.append(c)
        return cells

    def path(self, rt, cur, width):
        """The robust objective's change the prices predict for a routed hop (its segments' self, flux and
        crossing terms, as the router's own _path_harm), and per pair the predicted dZ(f) (accumulated
        until the next refresh compares it with the solve)."""
        from .pnr import strip_L_per_mm
        r, st = self.r, self.r.spec_m
        bf, m = st["bf"], r.mesh
        pads = next((k[1] for k in cur if k[0] == "pads"), ())
        e = st.get("edges", {}).get(tuple(pads))
        if e is not None:
            return self._path_port(e, rt, width)
        i = self.currents(pads)
        mm = st["Y"].shape[1]
        fl, cr, ln_L = np.zeros(mm), np.zeros((2, mm)), 0.0
        eh = np.zeros(len(r.spec_hops))
        for l, p0, p1 in rt.segs:
            if l not in r.layer_names:
                continue
            L = r.layer_names.index(l)
            cells = self._path_cells(p0, p1)
            if len(cells) < 2 or L not in bf["tmpl"]:
                continue
            a_, b_ = path_integrals(bf, L, cells)
            fl += a_
            cr += b_
            jj = np.array([c[0] for c in cells])
            ii = np.array([c[1] for c in cells])
            di, dj = np.diff(ii), np.diff(jj)
            for h, (dF, _) in enumerate(r.spec_hops):
                if L in dF:
                    dx, dy = dF[L][0][jj, ii], dF[L][1][jj, ii]
                    eh[h] += float((0.5 * (dx[:-1] + dx[1:]) * di + 0.5 * (dy[:-1] + dy[1:]) * dj).sum())
            up, dn, hu, hd, a_up, a_dn = T1.references(m, L, r.ref_ids)
            j, i_ = cells[len(cells) // 2]
            Lu = strip_L_per_mm(width, hu[j, i_]) if np.isfinite(hu[j, i_]) else np.inf
            Ld = strip_L_per_mm(width, hd[j, i_]) if np.isfinite(hd[j, i_]) else np.inf
            g = (0.0 if not np.isfinite(Lu) else 1.0 / float(Lu)) + (0.0 if not np.isfinite(Ld) else 1.0 / float(Ld))
            ln_L += (1.0 / g if g > 0 else float(strip_L_per_mm(width, 1.6))) * math.dist(p0, p1)
        Y, ns, jw = st["Y"], st["ns"], 1j * st["w"]
        PiF = np.einsum("m,fmp->fp", fl, Y)                    # the flux every port's currents link with the hop
        for h, (_, ih) in enumerate(r.spec_hops):
            PiF = PiF + eh[h] * ih
        XF = np.einsum("m,fmp->fp", cr[0], Y) + jw[:, None] * np.einsum("m,fmp->fp", cr[1], Y)
        tot = 0.0
        pz = dict(r.spec_pred)
        for (k, j) in st["pairs"]:
            kp = ns + k
            dZ = jw * (i[:, kp] * i[:, j] * ln_L + i[:, kp] * PiF[:, j] + i[:, j] * PiF[:, kp]) \
                + i[:, kp] * XF[:, j] + i[:, j] * XF[:, kp]
            pz[(k, j)] = pz.get((k, j), 0.0) + dZ
            g = st["G"].get((k, j))
            if g is not None:
                tot += float(np.real(np.sum(g * dZ)))
        r.spec_pred = pz
        return tot

    def add_hop(self, rt, cur):
        """Between refreshes a routed hop joins every pattern's fields as one more vector: its own flux (the
        hop and its return under it, per routing layer net of the return planes' share) times the current
        each pattern drives through it at each frequency."""
        r = self.r
        m = r.mesh
        bars = []
        for l, p0, p1 in rt.segs:
            if l not in r.layer_names:
                continue
            L = r.layer_names.index(l)
            up, dn, hu, hd, a_up, a_dn = T1.references(m, L, r.ref_ids)
            cells = self._path_cells(p0, p1)
            for (j0, i0), (j1, i1) in zip(cells[:-1], cells[1:]):
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
        if not bars:
            return
        fl = EF.flux_of_cells(r.op, bars)
        dF = {}
        for L in r.spec_m["bf"]["tmpl"]:
            up, dn, hu, hd, a_up, a_dn = T1.references(m, L, r.ref_ids)
            dx, dy = fl[(L, "x")].copy(), fl[(L, "y")].copy()
            for ref, a in ((up, a_up), (dn, a_dn)):
                for k in np.unique(ref[ref >= 0]):
                    sel = ref == k
                    dx[sel] -= a[sel] * fl[(int(k), "x")][sel]
                    dy[sel] -= a[sel] * fl[(int(k), "y")][sel]
            dF[L] = (dx.astype(np.float32), dy.astype(np.float32))
        pads = next((k[1] for k in cur if k[0] == "pads"), ())
        r.spec_hops = r.spec_hops + ((dF, self.currents(pads)),)

    # ------------------------------------------------------------------ connection ports (kae.em.hopport)
    def _upcoming(self):
        """The nets routed before the next refresh: the first priced nets in pieces that the router has not
        laid copper for yet (one with --verify)."""
        r = self.r
        n_up = 1 if r.verify else max(1, r.refresh)
        routed = {t[0] for t in r.tracks} | {v[0] for v in r.vias}
        return [n for n in r.nets if n not in routed and len([g for g in r.islands.get(n, []) if g]) > 1][:n_up]

    def _tree_shorts(self, m, base, ok, up):
        """Set m.lumped: the field-free shorts of every other net; for each net in `up`, field-free shorts
        between the mesh groups inside each of its exact islands, and one part of negligible impedance per
        edge of the spanning tree kae.em.pnr._route_net will route (nearest island centroids first), between
        the closest meshed pads of its two islands. Returns the edges."""
        from .mesh import Lumped
        r = self.r
        keep = [q for q in base if r.bd.net_of.get(q.a) not in up]
        m.lumped = []
        bare = ES.Network(m)
        comp = {q: int(bare.comp[bare.term_node[q]]) for q in ok if q in bare.term_node}
        edges = []
        for n in up:
            isl = [g for g in r.islands.get(n, []) if g]
            for g in isl:
                reps = {}
                for q in g:
                    if q in comp:
                        reps.setdefault(comp[q], q)
                rs = list(reps.values())
                keep += [Lumped(x, y) for x, y in zip(rs[:-1], rs[1:])]

            def cen(g):
                return np.mean([r._pad_xy(q) for q in g], axis=0)
            tree, left = [isl[0]], isl[1:]
            while left:
                a, b_ = min(((a, b_) for a in tree for b_ in left), key=lambda ab: np.linalg.norm(cen(ab[0]) - cen(ab[1])))
                pa, pb = [q for q in a if q in comp], [q for q in b_ if q in comp]
                if pa and pb:
                    qb, qa = min(((x, y) for x in pb for y in pa), key=lambda xy: np.linalg.norm(r._pad_xy(xy[0]) - r._pad_xy(xy[1])))
                    nm = f"hop:{n}:{len(edges)}"
                    keep.append(Lumped(qb, qa, name=nm, zf=lambda w: Z_SHORT + 0j))
                    edges.append(dict(name=nm, net=n, key=tuple(b_), qb=qb, qa=qa))
                elif pa or pb:
                    keep.append(Lumped((pb or pa)[0], (pa or pb)[0]))
                tree.append(b_)
                left.remove(b_)
        m.lumped = keep
        return edges

    def _edge_data(self, model, edges, Yall, nP0, w):
        """Per connection port: the current every pattern drives through it (nF, nP), its loop's admittance
        Y (nF), the loop's coefficients ye (nF, m), and Y Z(l_e): the copper part of the loop's impedance
        times Y (stable as Y -> 0)."""
        out = {}
        Gc = model.G_L + model.G_Lc
        for q, e in enumerate(edges):
            ce = nP0 + q
            ye = Yall[:, :, ce]
            Yb = np.einsum("m,fm->f", model.Vl[e["lump"]], ye)
            I = np.einsum("m,fmp->fp", model.Vl[e["lump"]], Yall[:, :, :nP0])
            E = np.einsum("fm,mn,fn->f", ye, model.G_R, ye) + 1j * w * np.einsum("fm,mn,fn->f", ye, Gc, ye)
            with np.errstate(divide="ignore", invalid="ignore"):
                YZrr = np.where(np.abs(Yb) > 1e-12, E / Yb, np.inf)
            out[e["key"]] = dict(e, I=I, Yb=Yb, ye=ye, YZrr=YZrr, loops={})
        return out

    def _open(self, e):
        """The patterns' coefficients with the connection opened: y_P - (I_P / Y) y_e (no correction where
        the loop admits no current: the connection is then fed by a current source alone)."""
        st = self.r.spec_m
        Yb = e["Yb"]
        with np.errstate(divide="ignore", invalid="ignore"):
            s = np.where(np.abs(Yb)[:, None] > 1e-9, e["I"] / Yb[:, None], 0.0)
        return st["Y"] - s[:, None, :] * e["ye"][:, :, None]

    def _loop(self, e, segs, width):
        from . import hopport as HP
        r, st = self.r, self.r.spec_m
        m = r.mesh
        bars, ln = HP.path_bars(m, segs, r.layer_names, width)
        if not bars:
            return None
        L, o, j, i, _ = bars[len(bars) // 2]
        up, dn, hu, hd, a_up, a_dn = T1.references(m, L, r.ref_ids)
        h = min(float(hu[j, i]), float(hd[j, i]))
        return HP.Loop(r.op, m, st["bf"], bars, ln, width, r.ref_ids, h_ref=h if np.isfinite(h) else None)

    def _nominal(self, e, width):
        """The straight hop between the connection's two pads, on the first routing layer either pad is on."""
        k = round(width, 3)
        if k not in e["loops"]:
            r = self.r
            p0, p1 = tuple(r._pad_xy(e["qb"])), tuple(r._pad_xy(e["qa"]))
            lay = next((l for l in r.layer_names if r._anchor(e["qb"]) and l in r._anchor(e["qb"]).layers), r.layer_names[0])
            e["loops"][k] = self._loop(e, [(lay, p0, p1)], width)
        return e["loops"][k]

    def _hop_port(self, e, width):
        """The hop's move costs, linear in its path about the straight hop: the hop's loop current I_P
        scaled by the compensation kap0 of the straight hop's loop, plus the current the loop picks up
        from the other patterns' flux there (the second-order term, linearized), against the raw flux of
        every pattern with the connection opened."""
        st = self.r.spec_m
        ns, w = st["ns"], st["w"]
        jw = 1j * w
        I, Yb = e["I"], e["Yb"]
        yo = self._open(e)
        lp = self._nominal(e, width)
        if lp is None:
            kap, Po = np.ones(len(w)), np.zeros(I.shape, complex)
        else:
            _, dZ = lp.impedance(w, e["ye"], Yb, e["YZrr"])
            kap = 1.0 / (1.0 + Yb * dZ)
            Po = np.einsum("m,fmp->fp", lp.rh, yo)
        It = I - (Yb * jw)[:, None] * Po
        A = np.zeros(I.shape, complex)
        g_self = 0.0
        for (k, j), g in st["G"].items():
            kp = ns + k
            A[:, j] += g * jw * kap * It[:, kp]
            A[:, kp] += g * jw * kap * It[:, j]
            g_self += float(np.real(np.sum(g * jw * kap * I[:, kp] * I[:, j])))
        c = np.real(np.einsum("fp,fmp->m", A, yo))
        eh = [float(np.real(np.sum(A * ih))) for _, ih in self.r.spec_hops]
        return self._pseudo(c, None, g_self, eh, raw=True)

    def _path_port(self, e, rt, width):
        """kae.em.hopport's prediction for the routed path: the loop's stationary return, the compensation,
        the raw flux of the opened patterns along the path (and of the hops routed since the refresh)."""
        r, st = self.r, self.r.spec_m
        ns, w = st["ns"], st["w"]
        jw = 1j * w
        I, Yb = e["I"], e["Yb"]
        yo = self._open(e)
        lp = self._loop(e, rt.segs, width)
        if lp is None:
            return 0.0
        _, dZ = lp.impedance(w, e["ye"], Yb, e["YZrr"])
        kap = 1.0 / (1.0 + Yb * dZ)
        Po = np.einsum("m,fmp->fp", lp.rh, yo)
        m = r.mesh
        for h, (dF, ih) in enumerate(r.spec_hops):
            v = sum(c * (dF[l][0] if o == "x" else dF[l][1])[j, i] for (l, o, j, i, c) in lp.bars if l in dF)
            Po = Po + v * ih
        tot = 0.0
        pz = dict(r.spec_pred)
        for (k, j) in st["pairs"]:
            kp = ns + k
            dZp = kap * (I[:, kp] * I[:, j] * dZ + jw * (I[:, kp] * Po[:, j] + I[:, j] * Po[:, kp])) \
                - Yb * kap * (jw * Po[:, kp]) * (jw * Po[:, j])
            pz[(k, j)] = pz.get((k, j), 0.0) + dZp
            g = st["G"].get((k, j))
            if g is not None:
                tot += float(np.real(np.sum(g * dZp)))
        r.spec_pred = pz
        return tot

    # ------------------------------------------------------------------ predicted against actual
    def _compare(self, prev, st, H):
        """Log the change of the objective and of every pair since the last refresh against the prediction
        of the hops' prices; append both, per pair and frequency, to work/spectral.jsonl."""
        r = self.r
        if prev is None:
            return
        if [o.name for o in prev["obs"]] != [o.name for o in st["obs"]] or not np.array_equal(prev["F"], st["F"]):
            return
        pred = r._pred or 0.0
        self.log(f"pnr: harm {r._H:.2f} -> {H:.2f} (change {H - r._H:+.2f}; the hops' prices predicted {pred:+.2f})")
        ns, i_log, w = st["ns"], st["i_log"], st["w"]
        rows, rec = [], []
        for (k, j) in prev["pairs"]:
            pz = r.spec_pred.get((k, j), np.zeros(len(st["F"]), complex))
            kp = ns + k
            dZ = (st["Z"][:, kp, j] - st["Zi"][j][:, k]) - (prev["Z"][:, kp, j] - prev["Zi"][j][:, k])
            dl, pl = dZ[i_log].imag / w[i_log], pz[i_log].imag / w[i_log]
            g0 = prev["G0"].get((k, j))
            du = float(np.real(np.sum(g0 * dZ))) if g0 is not None else None
            pu = float(np.real(np.sum(g0 * pz))) if g0 is not None else None
            u_now = st["U"].get((k, j))
            u_was = prev["U"].get((k, j))
            nm = (st["obs"][k].name, st["srcs"][j].name)
            rows.append((abs(dl) + abs(pl), nm, dl, pl, du, pu,
                         None if u_now is None or u_was is None else float(u_now[0] - u_was[0])))
            rec.append(dict(pair=nm, f=st["F"].tolist(), dZ_re=dZ.real.tolist(), dZ_im=dZ.imag.tolist(),
                            pred_re=pz.real.tolist(), pred_im=pz.imag.tolist(), du_lin=du, du_pred=pu,
                            du=rows[-1][6], dL=dl, dL_pred=pl))
        for _, nm, dl, pl, du, pu, dux in sorted(rows, key=lambda x: -x[0])[:8]:
            self.log(f"pnr:   dL {nm[0][:34]:34s} <- {nm[1][:24]:24s} actual {dl * 1e9:+8.3f} nH predicted "
                     f"{pl * 1e9:+8.3f} nH" + (f"; du (typical corner) actual {dux:+.3f} linear {du:+.3f} predicted "
                                               f"{pu:+.3f}" if du is not None and dux is not None else ""))
        with open(self.trace, "a") as fh:
            fh.write(json.dumps(dict(H_was=r._H, H=H, pred=pred, hops=len(r.spec_hops), pairs=rec)) + "\n")
