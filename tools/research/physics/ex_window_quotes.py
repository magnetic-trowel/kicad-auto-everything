# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact incremental quotes for placement moves inside a module window
(docs/topics/physics/exact-physics-options.md, design d).

The physics engine design (docs/topics/architecture/physics-engine-design.md) quotes copper
edits from a window's boundary Schur complement in 25-110 us, for rank-1 to rank-8 edits.
A placement move is a larger edit: the moved part's pads and its hops' copper leave some
cells and enter others, so k branches of the window change at once. This script measures
what an exact quote costs as k grows, on a real board operator:

  1. the whole-board DC network of BLDCM-Power (eng_board_scaling.build_operator: every net,
     layer and via barrel; the HF stack operator has the same sparsity class);
  2. windows of |W| = 1600 and 6400 nodes centred on the first hot-loop capacitor (all layers);
  3. K_W by the boundary Schur complement (factor the rest, |B| solves), and the dense window
     inverse G_W = K_W^-1;
  4. a two-terminal impedance z = (e_p - e_q)' G_W (e_p - e_q) between the capacitor's pads
     (an effective resistance here; a loop inductance on the HF operator);
  5. a "move": k branches inside W change conductance (half lose 90% of it, as copper leaving a
     cell; half are added between other window node pairs, as copper arriving). Exact quote by Woodbury, O(k^2) gathers from G_W and one k x k solve:
     dz = -v' (C^-1 + A' G_W A)^-1 v, v = A' G_W (e_p - e_q); checked against a brute-force
     refactorization of the edited whole board;
  6. the commit: a rank-k update of G_W (O(|W|^2 k)), against a dense refactorization of K_W.

Usage:  python tools/research/physics/ex_window_quotes.py [--board ID] [--h 0.2] [--json OUT]
CPU seconds on one core. Deterministic.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'kae' / 'src'))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import scipy.linalg as sla  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402


def cpu():
    return time.process_time()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--board', default='pcbcorpus-brenocq-bldc-motor-bldcm-power')
    ap.add_argument('--h', type=float, default=0.2)
    ap.add_argument('--windows', default='1600,6400')
    ap.add_argument('--ks', default='8,32,128,512,1024')
    ap.add_argument('--json', default=None)
    a = ap.parse_args(argv)
    from eng_board_scaling import build_operator, peak_mb
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.physics.place_terms import Terms
    path = str(ROOT / 'kae-work-v2' / 'tasks' / a.board / 'reference' / 'board.kicad_pcb')
    res = dict(board=a.board, h=a.h)
    b = load(path)
    T = Terms(b, build(b))
    cell = [s for s in T.structs if s.kind == 'commutation'] or [s for s in T.structs if s.kind == 'decap']
    lc = cell[0].comps[0]
    cap = lc.T[0].i
    p = T.bv.parts[cap]
    pads = [T.bv.pad_xy(cap, k, p.x0, p.y0, p.rot0, p.side0) for k in range(len(p.pad_num))]
    cx, cy = p.x0, p.y0
    res['centre'] = dict(part=p.ref, x=cx, y=cy)
    t0 = cpu()
    N, G, keep, info = build_operator(path, a.h)
    res['t_build'] = cpu() - t0
    res.update(nodes=int(G.shape[0]), nnz=int(G.nnz))
    n = G.shape[0]
    G = G.tocsr()
    x, y = N.x[keep], N.y[keep]
    Gc = G.tocoo()
    off = Gc.row < Gc.col
    ea, eb, gv = Gc.row[off], Gc.col[off], -Gc.data[off]
    t0 = cpu()
    lu_full = spla.splu(G.tocsc(), permc_spec='MMD_AT_PLUS_A', diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))
    res['t_factor_full'] = cpu() - t0
    rng = np.random.default_rng(5)
    res['windows'] = []
    for wsize in [int(v) for v in a.windows.split(',')]:
        d = np.maximum(np.abs(x - cx), np.abs(y - cy))
        W = np.sort(np.argsort(d)[:wsize])
        inW = np.zeros(n, bool)
        inW[W] = True
        loc = -np.ones(n, np.int64)
        loc[W] = np.arange(len(W))
        R = np.nonzero(~inW)[0]
        wr = dict(window_nodes=int(len(W)), half_side_mm=float(d[W].max()))
        # port: the window nodes nearest the capacitor's two pads (top layer first in order)
        pn = [int(W[np.argmin((x[W] - px) ** 2 + (y[W] - py) ** 2)]) for px, py in pads[:2]]
        if pn[0] == pn[1]:
            pn[1] = int(W[np.argsort((x[W] - pads[1][0]) ** 2 + (y[W] - pads[1][1]) ** 2)[1]])
        # ---- Schur window
        t0 = cpu()
        GRR = G[R][:, R]
        lur = spla.splu(GRR.tocsc(), permc_spec='MMD_AT_PLUS_A', diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))
        t_rr = cpu() - t0
        GWR = G[W][:, R].tocsr()
        B_loc = np.nonzero(np.diff(GWR.indptr) > 0)[0]
        t0 = cpu()
        GRB = G[R][:, W[B_loc]].tocsc()
        GBR = GRB.T.tocsr()
        Sigma = np.zeros((len(B_loc), len(B_loc)))
        for c0 in range(0, len(B_loc), 64):
            c = np.arange(c0, min(len(B_loc), c0 + 64))
            Sigma[:, c] = GBR @ lur.solve(GRB[:, c].toarray())
        t_sig = cpu() - t0
        t0 = cpu()
        KW = G[W][:, W].toarray()
        KW[np.ix_(B_loc, B_loc)] -= Sigma
        cho = sla.cho_factor(KW)
        GW = sla.cho_solve(cho, np.eye(len(W)))
        t_inv = cpu() - t0
        wr.update(boundary_nodes=int(len(B_loc)), t_factor_rest=t_rr, t_boundary=t_sig, t_inverse=t_inv,
                  setup_total=t_rr + t_sig + t_inv, GW_mb=GW.nbytes / 2**20)
        del lur, GRR
        s = np.zeros(len(W))
        s[loc[pn[0]]], s[loc[pn[1]]] = 1.0, -1.0
        u = GW @ s
        z0 = float(s @ u)
        wr['z0'] = z0
        brW = np.nonzero(inW[ea] & inW[eb])[0]
        quotes = []
        for k in [int(v) for v in a.ks.split(',')]:
            if 2 * k > len(brW):
                continue
            rem = rng.choice(brW, k // 2, replace=False)
            # added links: between window nodes that are grid neighbours of removed branches' ends
            addA = rng.choice(W, k - k // 2)
            addB = []
            for q in addA:
                dd = (x[W] - x[q]) ** 2 + (y[W] - y[q]) ** 2
                cand = W[np.argsort(dd)[1:4]]
                addB.append(int(rng.choice(cand)))
            a_idx = np.r_[ea[rem], addA]
            b_idx = np.r_[eb[rem], np.array(addB)]
            dg = np.r_[-0.9 * gv[rem], np.full(len(addA), np.median(gv[brW]))]
            la, lb = loc[a_idx], loc[b_idx]
            reps = 5 if k <= 128 else 2
            t0 = cpu()
            for _ in range(reps):
                M = GW[np.ix_(la, la)] - GW[np.ix_(la, lb)] - GW[np.ix_(lb, la)] + GW[np.ix_(lb, lb)]
                Cap = np.diag(1.0 / dg) + M
                v = u[la] - u[lb]
                dz = -float(v @ np.linalg.solve(Cap, v))
            t_quote = (cpu() - t0) / reps
            # brute force on the whole edited board
            t0 = cpu()
            D = sp.coo_matrix((np.r_[dg, dg, -dg, -dg], (np.r_[a_idx, b_idx, a_idx, b_idx], np.r_[a_idx, b_idx, b_idx, a_idx])),
                              shape=(n, n))
            Ge = (G + D).tocsc()
            lue = spla.splu(Ge, permc_spec='MMD_AT_PLUS_A', diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))
            sf = np.zeros(n)
            sf[pn[0]], sf[pn[1]] = 1.0, -1.0
            z_bf = float(sf @ lue.solve(sf))
            t_bf = cpu() - t0
            # commit: rank-k update of G_W vs dense re-inversion
            t0 = cpu()
            Acol = np.zeros((len(W), len(la)))
            Acol[la, np.arange(len(la))] += 1.0
            Acol[lb, np.arange(len(lb))] -= 1.0
            GA = GW @ Acol
            GW2 = GW - GA @ np.linalg.solve(Cap, GA.T)
            t_commit = cpu() - t0
            t0 = cpu()
            KW2 = KW.copy()
            np.add.at(KW2, (la, la), dg)
            np.add.at(KW2, (lb, lb), dg)
            np.add.at(KW2, (la, lb), -dg)
            np.add.at(KW2, (lb, la), -dg)
            sla.cho_factor(KW2)
            t_refactor_dense = cpu() - t0
            quotes.append(dict(k=k, t_quote=t_quote, z_quote=z0 + dz, z_bruteforce=z_bf,
                               rel_err=abs(z0 + dz - z_bf) / abs(z_bf), t_bruteforce=t_bf, t_commit=t_commit,
                               t_refactor_window=t_refactor_dense))
            del GW2
            print(f"|W| {len(W)} k {k}: quote {1e3 * t_quote:.2f} ms (rel err {quotes[-1]['rel_err']:.1e}), "
                  f"brute force {t_bf:.2f} s, commit {t_commit:.2f} s, dense window refactor {t_refactor_dense:.2f} s",
                  flush=True)
        wr['quotes'] = quotes
        res['windows'].append(wr)
        print(f"window {len(W)} nodes (half side {wr['half_side_mm']:.2f} mm, |B| {len(B_loc)}): setup "
              f"{wr['setup_total']:.2f} s (rest factor {t_rr:.2f}, boundary {t_sig:.2f}, inverse {t_inv:.2f}), "
              f"G_W {wr['GW_mb']:.0f} MB", flush=True)
        del GW, KW
    res['peak_mb'] = peak_mb()
    print(json.dumps({k: v for k, v in res.items() if k != 'windows'}))
    if a.json:
        os.makedirs(os.path.dirname(a.json), exist_ok=True)
        json.dump(res, open(a.json, 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
