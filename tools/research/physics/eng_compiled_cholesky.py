# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sparse factorization backends for the physics engine, on real-board DC operators.

Prefix eng (physics-engine design): docs/topics/architecture/physics-engine-design.md.

Reads a grounded board operator exported by eng_board_scaling.py --export DIR (lower triangle,
CSC, plus a geometric nested-dissection permutation) and times, on one core:

  superlu  SciPy SuperLU, MMD on A'+A, symmetric mode, no pivoting (the prototypes' solver);
  cholmod  CHOLMOD supernodal LL' through scikit-sparse (if installed), AMD and METIS orderings:
           analysis + factorization, numeric refactorization on the same pattern, solves, and a
           rank-8 downdate/update of the factor (CHOLMOD Modify) that removes and restores eight
           branches, checked against refactorization;
  faer     faer's supernodal LL' (Rust, MIT) with its AMD and with the nested-dissection order:
           symbolic analysis, numeric factorization, solves. The Rust source is embedded below;
           it is built with cargo into --workdir (or pass --faer-bin to reuse a build).

Usage:  python -I eng_compiled_cholesky.py DIR [--workdir W] [--faer-bin PATH] [--no-faer] [--json]
Deterministic. OMP_NUM_THREADS=1 is set; faer runs with Par::Seq.
"""
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402

CARGO_TOML = """[package]
name = "faerbench"
version = "0.1.0"
edition = "2024"

[dependencies]
faer = { version = "0.24", default-features = false, features = ["std", "rayon", "linalg", "sparse", "sparse-linalg"] }

[profile.release]
opt-level = 3
codegen-units = 4
"""

MAIN_RS = r"""
// Sparse Cholesky benchmark on an exported board operator (lower triangle, CSC).
use faer::dyn_stack::{MemBuffer, MemStack};
use faer::linalg::cholesky::llt::factor::LltRegularization;
use faer::perm::PermRef;
use faer::sparse::linalg::cholesky::{factorize_symbolic_cholesky, LltRef, SymmetricOrdering};
use faer::sparse::{SparseColMat, SymbolicSparseColMat};
use faer::{Conj, Mat, Par, Side};
use std::time::Instant;

fn rd<'a>(b: &'a [u8], off: &mut usize, w: usize) -> &'a [u8] { let s = &b[*off..*off + w]; *off += w; s }

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let b = std::fs::read(&args[1]).expect("matrix file");
    let mut o = 0usize;
    let n = u64::from_le_bytes(rd(&b, &mut o, 8).try_into().unwrap()) as usize;
    let nnz = u64::from_le_bytes(rd(&b, &mut o, 8).try_into().unwrap()) as usize;
    let cp: Vec<u32> = (0..=n).map(|_| u64::from_le_bytes(rd(&b, &mut o, 8).try_into().unwrap()) as u32).collect();
    let ri: Vec<u32> = (0..nnz).map(|_| u32::from_le_bytes(rd(&b, &mut o, 4).try_into().unwrap())).collect();
    let va: Vec<f64> = (0..nnz).map(|_| f64::from_le_bytes(rd(&b, &mut o, 8).try_into().unwrap())).collect();
    let sym = SymbolicSparseColMat::<u32>::new_checked(n, n, cp, None, ri);
    let a = SparseColMat::<u32, f64>::new(sym, va);
    let par = Par::Seq;
    let perm: Option<(Vec<u32>, Vec<u32>)> = args.get(2).map(|p| {
        let pb = std::fs::read(p).expect("perm file");
        let fwd: Vec<u32> = pb.chunks_exact(4).map(|c| u32::from_le_bytes(c.try_into().unwrap())).collect();
        let mut inv = vec![0u32; n];
        for (k, &i) in fwd.iter().enumerate() { inv[i as usize] = k as u32; }
        (fwd, inv)
    });
    let orders: Vec<&str> = if perm.is_some() { vec!["amd", "nd"] } else { vec!["amd"] };
    for ordname in orders {
        let ord = match ordname {
            "amd" => SymmetricOrdering::Amd,
            _ => { let (f, i) = perm.as_ref().unwrap(); SymmetricOrdering::Custom(PermRef::new_checked(f, i, n)) }
        };
        let t0 = Instant::now();
        let symb = factorize_symbolic_cholesky(a.symbolic(), Side::Lower, ord, Default::default()).expect("symbolic");
        let t_sym = t0.elapsed().as_secs_f64();
        let mut lval = vec![0.0f64; symb.len_val()];
        let mut mem = MemBuffer::new(symb.factorize_numeric_llt_scratch::<f64>(par, Default::default()));
        let mut t_num = f64::INFINITY;
        for _ in 0..3 {
            let t1 = Instant::now();
            symb.factorize_numeric_llt::<f64>(&mut lval, a.as_ref(), Side::Lower, LltRegularization::default(), par,
                MemStack::new(&mut mem), Default::default()).expect("numeric");
            t_num = t_num.min(t1.elapsed().as_secs_f64());
        }
        let llt = LltRef::<'_, u32, f64>::new(&symb, &lval);
        let mut res = vec![];
        for &m in &[1usize, 48] {
            let mut rhs = Mat::<f64>::from_fn(n, m, |i, j| (((i * 7 + j * 13) % 17) as f64) - 8.0);
            let mut smem = MemBuffer::new(symb.solve_in_place_scratch::<f64>(m, par));
            let reps = if m == 1 { 10 } else { 2 };
            let mut best = f64::INFINITY;
            for _ in 0..reps {
                let t2 = Instant::now();
                llt.solve_in_place_with_conj(Conj::No, rhs.as_mut(), par, MemStack::new(&mut smem));
                best = best.min(t2.elapsed().as_secs_f64());
            }
            res.push(best);
        }
        println!("{{\"order\": \"{}\", \"n\": {}, \"len_L\": {}, \"t_symbolic\": {:.4}, \"t_numeric\": {:.4}, \"t_solve1\": {:.5}, \"t_solve48\": {:.4}}}",
                 ordname, n, symb.len_val(), t_sym, t_num, res[0], res[1]);
    }
}
"""


def load(d):
    raw = open(os.path.join(d, 'matrix.bin'), 'rb').read()
    n, nnz = np.frombuffer(raw[:16], '<u8')
    n, nnz = int(n), int(nnz)
    o = 16
    indptr = np.frombuffer(raw[o:o + 8 * (n + 1)], '<u8').astype(np.int64)
    o += 8 * (n + 1)
    indices = np.frombuffer(raw[o:o + 4 * nnz], '<u4').astype(np.int32)
    o += 4 * nnz
    data = np.frombuffer(raw[o:o + 8 * nnz], '<f8').copy()
    L = sp.csc_matrix((data, indices, indptr), shape=(n, n))
    return L


def bench_superlu(A):
    t0 = time.perf_counter()
    lu = spla.splu(A.tocsc(), permc_spec='MMD_AT_PLUS_A', diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))
    tf = time.perf_counter() - t0
    b = np.ones((A.shape[0], 48))
    t0 = time.perf_counter()
    lu.solve(b[:, 0])
    t1 = time.perf_counter() - t0
    t0 = time.perf_counter()
    lu.solve(b)
    t48 = time.perf_counter() - t0
    return dict(t_factor=tf, nnz_LU=int(lu.L.nnz + lu.U.nnz), t_solve1=t1, t_solve48=t48)


def bench_cholmod(Lw, A):
    try:
        from sksparse import cholmod
    except ImportError:
        return None
    out = {}
    n = A.shape[0]
    Lc = sp.csc_array(Lw)
    rng = np.random.default_rng(3)
    for order in ('amd', 'metis'):
        t0 = time.perf_counter()
        f = cholmod.cho_factor(Lc, lower=True, order=order)
        t_af = time.perf_counter() - t0
        t0 = time.perf_counter()
        f.factorize(Lc)
        t_num = time.perf_counter() - t0
        b = np.ones((n, 48))
        t0 = time.perf_counter()
        f.solve(b[:, 0])
        t1 = time.perf_counter() - t0
        t0 = time.perf_counter()
        f.solve(b)
        t48 = time.perf_counter() - t0
        out[order] = dict(t_analyze_factor=t_af, t_numeric=t_num, nnz_L=int(f.nnz), t_solve1=t1, t_solve48=t48)
    # rank-8 downdate (remove 8 branches) and update (restore them), against refactorization
    Acoo = sp.tril(A, -1).tocoo()
    cand = rng.choice(len(Acoo.data), 8, replace=False)
    a, bb, g = Acoo.row[cand], Acoo.col[cand], -Acoo.data[cand]
    C = sp.csc_array(sp.coo_matrix((np.r_[np.sqrt(g), -np.sqrt(g)], (np.r_[a, bb], np.r_[np.arange(8), np.arange(8)])),
                                   shape=(n, 8)).tocsc())
    C.has_sorted_indices = False         # cholmod_updown needs sorted row indices within each column
    C.sort_indices()
    f = cholmod.cho_factor(Lc, lower=True, order='amd')
    x0 = rng.standard_normal(n)
    t0 = time.perf_counter()
    f.downdate(C)
    t_dd = time.perf_counter() - t0
    A2 = (A - C @ C.T).tocsc()
    y = f.solve(x0)
    ref = spla.spsolve(A2, x0)
    err = float(np.max(np.abs(y - ref)) / np.max(np.abs(ref)))
    t0 = time.perf_counter()
    f.update(C)
    t_up = time.perf_counter() - t0
    t0 = time.perf_counter()
    f.solve(x0)
    t_s_simpl = time.perf_counter() - t0
    out['updown'] = dict(rank=8, t_downdate=t_dd, t_update=t_up, rel_err_vs_spsolve=err, t_solve1_after=t_s_simpl)
    return out


def bench_faer(d, workdir, faer_bin):
    if faer_bin is None:
        if shutil.which('cargo') is None:
            return None
        proj = os.path.join(workdir, 'faerbench')
        os.makedirs(os.path.join(proj, 'src'), exist_ok=True)
        open(os.path.join(proj, 'Cargo.toml'), 'w').write(CARGO_TOML)
        open(os.path.join(proj, 'src', 'main.rs'), 'w').write(MAIN_RS)
        subprocess.run(['cargo', 'build', '--release', '-q', '-j', '2'], cwd=proj, check=True)
        faer_bin = os.path.join(proj, 'target', 'release', 'faerbench')
    out = subprocess.run([faer_bin, os.path.join(d, 'matrix.bin'), os.path.join(d, 'perm.bin')],
                         capture_output=True, text=True, check=True).stdout
    return [json.loads(line) for line in out.splitlines() if line.startswith('{')]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('dir')
    ap.add_argument('--workdir', default='.')
    ap.add_argument('--faer-bin', default=None)
    ap.add_argument('--no-faer', action='store_true')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)
    Lw = load(args.dir)
    A = (Lw + sp.tril(Lw, -1).T).tocsc()
    res = dict(dir=os.path.basename(os.path.normpath(args.dir)), n=int(A.shape[0]), nnz_A=int(A.nnz))
    res['superlu'] = bench_superlu(A)
    res['cholmod'] = bench_cholmod(Lw, A)
    if not args.no_faer:
        res['faer'] = bench_faer(args.dir, args.workdir, args.faer_bin)
    if args.json:
        print(json.dumps(res), flush=True)
    else:
        for k, v in res.items():
            print(f"{k:8s} {v}")


if __name__ == '__main__':
    main()
