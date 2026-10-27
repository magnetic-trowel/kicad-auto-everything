# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact window macro-models for the optimizer's inner loop: boundary Schur complement vs Green block.

Prefix eng (physics-engine design): docs/topics/architecture/physics-engine-design.md.

A hot window W (a box of the board, all layers and nets in it) can be served exactly in two ways:

  green   the dense block (Y^-1)[W, W] by |W| solves with the whole-board factorization
          (the hot-window cache of pc2_core_skeleton.py); valid until anything changes;
  schur   eliminate the rest R once: factor Y_RR, then Sigma = Y_BR Y_RR^-1 Y_RB for the window's
          boundary nodes B (|B| solves), so K_W = Y_WW - Sigma (on B x B) is the exact Kron-reduced
          board seen from W. (Y^-1)[W, W] = K_W^-1. Edits inside W change only Y_WW, so a commit
          inside the window is a dense update of K_W (milliseconds), with no whole-board work.

On a real board (rb_board_passports.build_dc network, all nets, via barrels) this script measures
both, checks that they agree, then commits a rank-8 removal inside the window and checks the
updated window against a brute-force refactorization of the whole edited board.

Usage:  python -I eng_window_schur.py BOARD.kicad_pcb --h 0.1 [--window 1600] [--json]
Deterministic; OMP_NUM_THREADS=1 is set before numpy loads.
"""
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402
import scipy.linalg as sla  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eng_board_scaling import build_operator, rss_mb, peak_mb  # noqa: E402


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def splu_sym(M):
    return spla.splu(M.tocsc(), permc_spec='MMD_AT_PLUS_A', diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('board')
    ap.add_argument('--h', type=float, default=0.1)
    ap.add_argument('--h-small', type=float, default=None)
    ap.add_argument('--window', type=int, default=1600)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--skip-green', action='store_true', help='skip the |W|-solve Green block')
    args = ap.parse_args(argv)
    N, G, keep, res = build_operator(args.board, args.h, args.h_small)
    n = G.shape[0]
    G = G.tocsr()
    x, y = N.x[keep], N.y[keep]
    # the source: two far nodes on the largest island (as eng_board_scaling.quotes)
    t0 = time.perf_counter()
    lu = splu_sym(G)
    res['t_factor_full'] = time.perf_counter() - t0
    log(f"built {res['nodes']} nodes in {res['t_build']:.1f} s; factor {res['t_factor_full']:.1f} s")
    comp = N.comp[keep]
    big = np.bincount(comp).argmax()
    cand = np.nonzero((comp == big) & (N.node_kind[keep] == 0))[0]
    s = np.zeros(n)
    s[cand[np.argmin(x[cand])]], s[cand[np.argmax(x[cand])]] = 1.0, -1.0
    t0 = time.perf_counter()
    phi = lu.solve(s)
    res['t_solve1'] = time.perf_counter() - t0
    Gc = G.tocoo()
    off = Gc.row < Gc.col
    ea, eb, gv = Gc.row[off], Gc.col[off], -Gc.data[off]
    I = gv * (phi[ea] - phi[eb])
    k0 = int(np.argmax(np.abs(I)))
    cx, cy = 0.5 * (x[ea[k0]] + x[eb[k0]]), 0.5 * (y[ea[k0]] + y[eb[k0]])
    d = np.maximum(np.abs(x - cx), np.abs(y - cy))
    W = np.sort(np.argsort(d)[:args.window])
    inW = np.zeros(n, bool)
    inW[W] = True
    R = np.nonzero(~inW)[0]
    # boundary nodes of W: window nodes with a neighbour outside
    GWR = G[W][:, R]
    B_loc = np.nonzero(np.diff(GWR.tocsr().indptr) > 0)[0]
    res.update(window_nodes=int(len(W)), boundary_nodes=int(len(B_loc)))

    # ---- green block: |W| solves with the whole-board factorization
    t0 = time.perf_counter()
    Gw = None
    if not args.skip_green:
        Gw = np.zeros((len(W), len(W)))
        for c0 in range(0, len(W), 200):
            c = np.arange(c0, min(len(W), c0 + 200))
            E = np.zeros((n, len(c)))
            E[W[c], np.arange(len(c))] = 1.0
            Gw[:, c] = lu.solve(E)[W]
        res['t_green_block'] = time.perf_counter() - t0

    log(f"green block done {res.get('t_green_block', 0):.1f} s; |W| {len(W)}, |B| {len(B_loc)}")
    # ---- schur: factor Y_RR, |B| solves (chunked, sparse coupling block), dense K_W
    t0 = time.perf_counter()
    GRR = G[R][:, R]
    lur = splu_sym(GRR)
    t_rr = time.perf_counter() - t0
    t0 = time.perf_counter()
    GRB = G[R][:, W[B_loc]].tocsc()                  # sparse: each boundary node has a few outside neighbours
    GBR = GRB.T.tocsr()
    Sigma = np.zeros((len(B_loc), len(B_loc)))
    for c0 in range(0, len(B_loc), 64):
        c = np.arange(c0, min(len(B_loc), c0 + 64))
        Xc = lur.solve(GRB[:, c].toarray())
        Sigma[:, c] = GBR @ Xc
    t_sig = time.perf_counter() - t0
    log(f"schur boundary map done: factor rest {t_rr:.1f} s, {len(B_loc)} solves {t_sig:.1f} s")
    t0 = time.perf_counter()
    KW = G[W][:, W].toarray()
    KW[np.ix_(B_loc, B_loc)] -= Sigma
    cho = sla.cho_factor(KW)
    Gw2 = sla.cho_solve(cho, np.eye(len(W)))
    t_inv = time.perf_counter() - t0
    res.update(t_factor_rest=t_rr, t_boundary_solves=t_sig, t_window_inverse=t_inv)
    if Gw is not None:
        res['schur_vs_green'] = float(np.max(np.abs(Gw2 - Gw)) / np.max(np.abs(Gw)))
    # ---- the same Schur complement from ONE factorization with the window ordered last:
    # block LU gives K_W = L_WW U_WW (the trailing blocks); the rest keeps its fill-reducing order
    t0 = time.perf_counter()
    order_R = R[np.argsort(lur.perm_c)]
    perm = np.r_[order_R, W]
    Ap = G[perm][:, perm].tocsc()
    lul = spla.splu(Ap, permc_spec='NATURAL', diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))
    w = len(W)
    Lw = lul.L[-w:, -w:].toarray()
    Uw = lul.U[-w:, -w:].toarray()
    KW_last = Lw @ Uw
    res['t_schur_one_factor'] = time.perf_counter() - t0
    res['pivoting_free'] = bool(np.all(lul.perm_r == np.arange(n)) and np.all(lul.perm_c == np.arange(n)))
    res['schur_last_vs_boundary'] = float(np.max(np.abs(KW_last - KW)) / np.max(np.abs(KW)))
    del lul, Ap

    # ---- commit inside the window: remove 8 branches, update K_W, re-invert; check vs brute force
    rng = np.random.default_rng(11)
    brW = np.nonzero(inW[ea] & inW[eb])[0]
    Bk = rng.choice(brW, 8, replace=False)
    loc = -np.ones(n, int)
    loc[W] = np.arange(len(W))
    t0 = time.perf_counter()
    KW2 = KW.copy()
    for k in Bk:
        a, b, g = loc[ea[k]], loc[eb[k]], gv[k]
        KW2[a, a] -= g; KW2[b, b] -= g; KW2[a, b] += g; KW2[b, a] += g
    Gw3 = sla.cho_solve(sla.cho_factor(KW2), np.eye(len(W)))
    res['t_commit_window'] = time.perf_counter() - t0
    # the same commit as a rank-k update of the cached window inverse (no refactorization):
    # G' = G - G A (diag(1/dy) + A' G A)^-1 A' G, dy = -g for removed branches
    t0 = time.perf_counter()
    A = np.zeros((len(W), len(Bk)))
    A[loc[ea[Bk]], np.arange(len(Bk))] = 1.0
    A[loc[eb[Bk]], np.arange(len(Bk))] = -1.0
    GA = Gw2 @ A
    Cap = np.diag(-1.0 / gv[Bk]) + A.T @ GA
    Gw4 = Gw2 - GA @ np.linalg.solve(Cap, GA.T)
    res['t_commit_lowrank'] = time.perf_counter() - t0
    res['lowrank_vs_reinvert'] = float(np.max(np.abs(Gw4 - Gw3)) / np.max(np.abs(Gw3)))
    # brute force: refactor the whole edited board, compare a block of columns
    t0 = time.perf_counter()
    a, b, g = ea[Bk], eb[Bk], gv[Bk]
    D = sp.coo_matrix((np.r_[-g, -g, g, g], (np.r_[a, b, a, b], np.r_[a, b, b, a])), shape=(n, n))
    Ge = (G + D).tocsr()
    t_lil = time.perf_counter() - t0
    t0 = time.perf_counter()
    lue = splu_sym(Ge)
    res['t_refactor_full'] = time.perf_counter() - t0
    cols = rng.choice(len(W), 40, replace=False)
    E = np.zeros((n, len(cols)))
    E[W[cols], np.arange(len(cols))] = 1.0
    ref = lue.solve(E)[W]
    res['commit_vs_bruteforce'] = float(np.max(np.abs(Gw3[:, cols] - ref)) / np.max(np.abs(ref)))
    res['t_edit_assembly'] = t_lil
    res['rss_mb'] = rss_mb()
    res['peak_mb'] = peak_mb()
    if args.json:
        print(json.dumps(res), flush=True)
    else:
        for k, v in res.items():
            print(f"{k:22s} {v}")


if __name__ == '__main__':
    main()
