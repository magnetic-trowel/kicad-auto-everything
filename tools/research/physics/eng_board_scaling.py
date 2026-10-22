# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics-engine costs on a real board: whole-board DC operator, factorization, solves, quotes.

Prefix eng (physics-engine design): docs/topics/architecture/physics-engine-design.md.

For one routed .kicad_pcb and one grid size h it builds the whole-board DC conductor model
(every net with copper, every layer, every via barrel; per-net rasters from
rb_board_passports.build_dc, which supersamples saved zone fills, tracks and pads), grounds
one node per conductor island, and measures, on one core:

  build    rasterization (point sampling of polygons) and assembly, with the number of
           point-in-polygon tests, so the throughput of the rasterizer is known;
  factor   SciPy SuperLU with three orderings on the same grounded matrix:
             colamd   SuperLU's default (unsymmetric column ordering, partial pivoting);
             mmd      MMD on A'+A, symmetric mode, no pivoting;
             nd       geometric nested dissection computed here from cell coordinates
                      (recursive coordinate bisection, vertex separators from cut edges),
                      then NATURAL order, symmetric mode, no pivoting;
           with nnz(L+U), factor time and solve times (1 and 48 right-hand sides);
  quotes   on a hot window of about --window nodes around the most loaded branch of a
           two-terminal source on the largest net: the dense Green block (Y^-1)[W, W]
           (W solves), then exact rank-k removal quotes (k = 1, 8, 32) from the block and
           by direct Woodbury solves (agreement printed), and exact Thevenin additions for
           500 candidate links from the block and by chunked solves;
  memory   resident set size after each stage and the process peak.

With --export DIR it writes the grounded matrix (lower triangle, CSC) and the nested-
dissection permutation for eng_compiled_cholesky.py.

Usage:  python -I eng_board_scaling.py BOARD.kicad_pcb --h 0.2 [--h-small H] [--window 1600]
            [--skip colamd,mmd] [--export DIR] [--json]
One JSON line per run with --json. Deterministic (fixed seeds). OMP_NUM_THREADS=1 is set.
Results quoted in the engine design docs come from runs of this script on bldcpower
(pcbcorpus-brenocq-bldc-motor-bldcm-power), libresolar bms-c1 and azonenberg latentred-linecard.
"""
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import resource  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rb_board_passports as rb  # noqa: E402  (KiCad parser, rasterizer, DC network builder)


def rss_mb():
    with open('/proc/self/statm') as f:
        return int(f.read().split()[1]) * os.sysconf('SC_PAGE_SIZE') / 2**20


def peak_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


# ---------------------------------------------------------------------------- instrumentation
_RASTER = {'t': 0.0, 'pts': 0}
_raster0 = rb.raster


def _raster_timed(geom, x0, y0, nx, ny, h, ss=3, fs=5):
    t0 = time.perf_counter()
    out = _raster0(geom, x0, y0, nx, ny, h, ss, fs)
    _RASTER['t'] += time.perf_counter() - t0
    _RASTER['pts'] += nx * ny * ss * ss + ny * fs * (nx - 1) + (ny - 1) * nx * fs
    return out


rb.raster = _raster_timed


# ---------------------------------------------------------------------------- ordering
def nested_dissection(x, y, A, leaf=96):
    """Geometric nested dissection order (new position -> old index) for a planar-ish graph.

    Bisect the node set at the median of its longer extent; the vertex separator is the set of
    left-side nodes with an edge to the right side. Order: left part, right part, separator.
    Layers are never split (they couple only through vias), so 2.5-D boards stay 2-D."""
    A = A.tocsr()
    side = np.full(len(x), -1, np.int8)
    out = []

    def rec(idx):
        if len(idx) <= leaf:
            out.append(idx)
            return
        xs, ys = x[idx], y[idx]
        c = xs if np.ptp(xs) >= np.ptp(ys) else ys
        med = np.median(c)
        left = c <= med
        if left.all() or not left.any():
            k = len(idx) // 2
            o = np.argsort(c, kind='stable')
            left = np.zeros(len(idx), bool)
            left[o[:k]] = True
        L, R = idx[left], idx[~left]
        side[L], side[R] = 0, 1
        sub = A[L]
        hit = np.zeros(len(L), bool)
        nb = side[sub.indices] == 1
        if nb.any():
            rows = np.repeat(np.arange(len(L)), np.diff(sub.indptr))
            hit[rows[nb]] = True
        side[idx] = -1
        S = L[hit]
        rec(L[~hit])
        rec(R)
        out.append(S)

    sys.setrecursionlimit(10000)
    rec(np.arange(len(x)))
    return np.concatenate(out)


# ---------------------------------------------------------------------------- factor + solve
def factor_stats(G, how, perm=None):
    t0 = time.perf_counter()
    if how == 'colamd':
        lu = spla.splu(G, permc_spec='COLAMD')
    elif how == 'mmd':
        lu = spla.splu(G, permc_spec='MMD_AT_PLUS_A', diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))
    else:
        Gp = G[perm][:, perm].tocsc()
        lu = spla.splu(Gp, permc_spec='NATURAL', diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))
    tf = time.perf_counter() - t0
    n = G.shape[0]
    rng = np.random.default_rng(1)
    b1 = rng.standard_normal(n)
    b48 = rng.standard_normal((n, 48))
    t0 = time.perf_counter()
    for _ in range(3):
        lu.solve(b1)
    t1 = (time.perf_counter() - t0) / 3
    t0 = time.perf_counter()
    lu.solve(b48)
    t48 = time.perf_counter() - t0
    return lu, dict(t_factor=tf, nnz_LU=int(lu.L.nnz + lu.U.nnz), t_solve1=t1, t_solve48=t48)


class Solver:
    """Grounded-matrix solver on the full node space (zero potential at each island's root)."""

    def __init__(self, lu, keep, n, perm=None):
        self.lu, self.keep, self.n, self.perm = lu, keep, n, perm

    def solve(self, S):
        S = np.asarray(S, float)
        one = S.ndim == 1
        S = S[:, None] if one else S
        X = np.zeros_like(S)
        rhs = S[self.keep]
        if self.perm is not None:
            y = np.zeros_like(rhs)
            y[self.perm] = self.lu.solve(np.ascontiguousarray(rhs[self.perm]))
            X[self.keep] = y
        else:
            X[self.keep] = self.lu.solve(np.ascontiguousarray(rhs))
        return X[:, 0] if one else X


# ---------------------------------------------------------------------------- build
def build_operator(path, h, h_small=None):
    """Whole-board DC network (all nets, all layers, via barrels) and its grounded matrix."""
    res = dict(board=os.path.basename(os.path.dirname(os.path.abspath(path))), h=h, h_small=h_small or h)
    t0 = time.perf_counter()
    b = rb.KBoard(path)
    b.fill_report()
    res['t_parse'] = time.perf_counter() - t0
    nets = sorted({p['net'] for p in b.pads if p['net']} | {t['net'] for t in b.tracks if t['net']}
                  | {z['net'] for z in b.zones})
    t0 = time.perf_counter()
    area = {n: b.area(n) for n in nets}
    res['t_geometry'] = time.perf_counter() - t0
    nets = [n for n in nets if area[n] > 0]
    hnet = {n: (h if area[n] > 150 else (h_small or h)) for n in nets}
    res.update(layers=len(b.cu), nets=len(nets), vias=len(b.vias), copper_mm2=float(sum(area.values())))
    t0 = time.perf_counter()
    N = rb.build_dc(b, nets, hnet, [])
    res['t_build'] = time.perf_counter() - t0
    res['t_raster'] = _RASTER['t']
    res['raster_points'] = _RASTER['pts']
    t0 = time.perf_counter()
    N.finalize()
    res['t_finalize'] = time.perf_counter() - t0
    res.update(nodes=int(N.nn), branches=int(N.nb), islands=int(N.ncomp), rss_build_mb=rss_mb())
    order = np.argsort(N.comp, kind='stable')
    starts = np.searchsorted(N.comp[order], np.arange(N.ncomp))
    roots = order[starts]
    keep = np.ones(N.nn, bool)
    keep[roots] = False
    keep = np.nonzero(keep)[0]
    G = N.G[keep][:, keep].tocsc()
    res['n_grounded'] = int(G.shape[0])
    res['nnz_A'] = int(G.nnz)
    return N, G, keep, res


# ---------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('board')
    ap.add_argument('--h', type=float, default=0.2, help='grid for every net (mm)')
    ap.add_argument('--h-small', type=float, default=None, help='grid for nets under 150 mm2 (default: --h)')
    ap.add_argument('--window', type=int, default=1600)
    ap.add_argument('--skip', default='', help='comma list of orderings to skip: colamd,mmd,nd')
    ap.add_argument('--no-quotes', action='store_true')
    ap.add_argument('--export', default=None)
    ap.add_argument('--complex', action='store_true', help='also time a complex-symmetric factorization')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)
    skip = set(filter(None, args.skip.split(',')))
    N, G, keep, res = build_operator(args.board, args.h, args.h_small)

    perm = None
    if 'nd' not in skip or args.export:
        t0 = time.perf_counter()
        A = G.copy().tocsr()
        A.setdiag(0)
        A.eliminate_zeros()
        perm = nested_dissection(N.x[keep], N.y[keep], A)
        res['t_nd_order'] = time.perf_counter() - t0
        assert len(np.unique(perm)) == G.shape[0]
    if args.complex:
        # an AC band on the same pattern: complex symmetric, every branch lossy (Re Y positive definite),
        # factored without pivoting in symmetric mode, as a telegrapher or R + jwL sheet would be
        d = G.diagonal().mean()
        Gc = (G * (1.0 + 0.7j) + sp.identity(G.shape[0]) * (0.05j * d)).tocsc()
        _, st = factor_stats(Gc.real.astype(float), 'mmd')
        t0 = time.perf_counter()
        luc = spla.splu(Gc, permc_spec='MMD_AT_PLUS_A', diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))
        res['complex'] = dict(t_factor_real=st['t_factor'], t_factor_complex=time.perf_counter() - t0,
                              nnz_LU_complex=int(luc.L.nnz + luc.U.nnz))
        b = np.ones(G.shape[0], complex)
        t0 = time.perf_counter()
        luc.solve(b)
        res['complex']['t_solve1_complex'] = time.perf_counter() - t0
        del luc
    lus = {}
    for how in ('colamd', 'mmd', 'nd'):
        if how in skip:
            continue
        lu, st = factor_stats(G, how, perm)
        lus[how] = lu
        res[how] = st
        res[how]['rss_mb'] = rss_mb()
        if how != 'nd':
            del lu
            lus.pop(how)
    if args.export:
        os.makedirs(args.export, exist_ok=True)
        Lw = sp.tril(G).tocsc()
        Lw.sort_indices()
        with open(os.path.join(args.export, 'matrix.bin'), 'wb') as f:
            f.write(np.array([Lw.shape[0], Lw.nnz], '<u8').tobytes())
            f.write(Lw.indptr.astype('<u8').tobytes())
            f.write(Lw.indices.astype('<u4').tobytes())
            f.write(Lw.data.astype('<f8').tobytes())
        with open(os.path.join(args.export, 'perm.bin'), 'wb') as f:
            f.write(perm.astype('<u4').tobytes())

    if not args.no_quotes and 'nd' in lus:
        quotes(N, G, keep, lus['nd'], perm, args.window, res)
    res['peak_mb'] = peak_mb()
    if args.json:
        print(json.dumps(res), flush=True)
    else:
        for k, v in res.items():
            print(f"{k:16s} {v}")
    return res


def quotes(N, G, keep, lu, perm, wsize, res):
    """Hot-window Green block and exact quotes from it, against direct solves."""
    sol = Solver(lu, keep, N.nn, perm)
    rng = np.random.default_rng(5)
    big = max(set(N.net), key=lambda n: np.sum(N.net == n))
    comp_big = np.bincount(N.comp[N.node_net == big]).argmax()
    cand = np.nonzero((N.comp == comp_big) & (N.node_kind == 0))[0]
    xa = N.x[cand]
    a_, b_ = cand[np.argmin(xa)], cand[np.argmax(xa)]
    s = np.zeros(N.nn)
    s[a_], s[b_] = 1.0, -1.0
    t0 = time.perf_counter()
    phi = sol.solve(s)
    res['t_solve_full1'] = time.perf_counter() - t0
    I = N.g * (phi[N.a] - phi[N.b])
    k0 = int(np.argmax(np.abs(I) * (N.kind <= 1)))
    cx, cy = N.mx[k0], N.my[k0]
    # square window around the hottest branch holding about wsize nodes (all layers and nets)
    d = np.maximum(np.abs(N.x - cx), np.abs(N.y - cy))
    o = np.argsort(d)
    W = np.sort(o[:wsize])
    W = W[np.isin(W, keep)]
    inW = np.zeros(N.nn, bool)
    inW[W] = True
    t0 = time.perf_counter()
    Gw = np.zeros((len(W), len(W)))
    chunk = max(8, min(200, int(2.5e8 / (8 * N.nn))))      # dense right-hand sides capped at ~250 MB
    for c0 in range(0, len(W), chunk):
        c = np.arange(c0, min(len(W), c0 + chunk))
        E = np.zeros((N.nn, len(c)))
        E[W[c], np.arange(len(c))] = 1.0
        Gw[:, c] = sol.solve(E)[W]
    res['window_nodes'] = int(len(W))
    res['t_green_block'] = time.perf_counter() - t0
    res['window_halfwidth_mm'] = float(d[o[wsize - 1]])
    loc = -np.ones(N.nn, int)
    loc[W] = np.arange(len(W))
    brW = np.nonzero(inW[N.a] & inW[N.b] & (N.kind <= 1))[0]
    out = {}
    for k in (1, 8, 32):
        for _try in range(50):      # skip edits that cut copper off (a topological event: M singular)
            B = rng.choice(brW, k, replace=False)
            # direct Woodbury: k solves
            t0 = time.perf_counter()
            E = np.zeros((N.nn, k))
            E[N.a[B], np.arange(k)] += 1.0
            E[N.b[B], np.arange(k)] -= 1.0
            P = sol.solve(E)
            RBB = P[N.a[B]] - P[N.b[B]]
            M = np.diag(1.0 / N.g[B]) - RBB
            v = phi[N.a[B]] - phi[N.b[B]]
            if np.linalg.cond(M) < 1e10:
                break
        dz_direct = float(v @ np.linalg.solve(M, v))
        t_direct = time.perf_counter() - t0
        # from the Green block: no solve
        reps = 2000
        t0 = time.perf_counter()
        for _ in range(reps):
            ia, ib = loc[N.a[B]], loc[N.b[B]]
            S = Gw[np.ix_(ia, ia)] - Gw[np.ix_(ia, ib)] - Gw[np.ix_(ib, ia)] + Gw[np.ix_(ib, ib)]
            M2 = np.diag(1.0 / N.g[B]) - S
            dz_blk = float(v @ np.linalg.solve(M2, v))
        t_blk = (time.perf_counter() - t0) / reps
        out[k] = dict(t_direct=t_direct, t_block=t_blk, rel_err=abs(dz_blk - dz_direct) / max(abs(dz_direct), 1e-300))
    res['removal_quotes'] = out
    # Thevenin additions: 500 candidate links (u, v) between window nodes on the source's island
    isl = W[N.comp[W] == comp_big]
    m = min(500, len(isl) // 2)
    U = rng.choice(isl, m, replace=False)
    V = rng.choice(isl, m, replace=False)
    z = 1.0 / np.median(N.g[N.kind <= 1])
    t0 = time.perf_counter()
    iu, iv = loc[U], loc[V]
    zth = Gw[iu, iu] + Gw[iv, iv] - 2 * Gw[iu, iv]
    dphi = phi[U] - phi[V]
    dz_blk = -dphi ** 2 / (z + zth)
    t_blk = time.perf_counter() - t0
    t0 = time.perf_counter()
    dz_dir = np.zeros(m)
    for c0 in range(0, m, min(48, chunk)):
        c = np.arange(c0, min(m, c0 + min(48, chunk)))
        E = np.zeros((N.nn, len(c)))
        E[U[c], np.arange(len(c))] += 1.0
        E[V[c], np.arange(len(c))] -= 1.0
        P = sol.solve(E)
        zt = P[U[c], np.arange(len(c))] - P[V[c], np.arange(len(c))]
        dz_dir[c] = -dphi[c] ** 2 / (z + zt)
    t_dir = time.perf_counter() - t0
    res['thevenin'] = dict(candidates=int(m), t_block_total=t_blk, t_direct_total=t_dir,
                           rel_err=float(np.max(np.abs(dz_blk - dz_dir)) / max(np.max(np.abs(dz_dir)), 1e-300)))


if __name__ == '__main__':
    main()
