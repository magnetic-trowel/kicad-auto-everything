# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate R2 of docs/topics/architecture/physics-frequency-coverage.md: the reduced model against direct
solves.

The board's whole circuit goes into its copper (kae.excite.circuit.lump_all); every commutation cell's
source and every observer is a fixed port. kae.em.reduce builds the model greedily up to 300 MHz with
errors relative to each pair's layout share (the solve minus the circuit with ideal copper). Then at
ten seeded random frequencies (log-uniform, 10 Hz .. 300 MHz, none a snapshot) every source-to-observer
layout share from the model is compared with a direct solve, and the model's port impedance matrix is
checked for passivity (its Hermitian part positive semidefinite).

    python tools/research/physics/em_reduce_gate.py BOARD.kicad_pcb [--pitch 0.25] [--seed 0]
"""
import argparse
import time

import numpy as np

from kae.board import transform
from kae.board.kicad_file import load
from kae.circuit import brief as B
from kae.em import reduce as RD
from kae.em import solve as ES
from kae.em.kicad import BoardMesh
from kae.excite import models as M
from kae.excite import observe as O
from kae.excite import sources as S
from kae.excite.circuit import lump_all, port


def ports_of(bd, srcs, obs, term):
    """(names, injections, circuit nodes) of every cell source and every observer."""
    names, injs, nodes = [], [], []
    for s in srcs:
        if s.kind == "cell":
            names.append(s.name), injs.append(port(term, s.a, s.b, s.pa, s.pb)), nodes.append(("node", s))
    for o in obs:
        if o.kind == "cm":
            a, b = o.meta["pads"]
            names.append(o.name), injs.append({term(None, a): 1.0, term(None, b): -1.0}), nodes.append(("pads", o))
        else:
            names.append(o.name), injs.append(port(term, o.a, o.b, o.pa, o.pb)), nodes.append(("node", o))
    return names, injs, nodes


def ideal(bd, f, nodes, n_src):
    """Z with ideal copper: the circuit alone (cm ports between pads of one net read zero)."""
    c = bd.circuit
    Z = np.zeros((len(nodes), n_src), complex)
    for j in range(n_src):
        s = nodes[j][1]
        V = c.solve(f, [s])[s.name]["V"]
        for k, (kind, o) in enumerate(nodes):
            if kind == "pads":
                a, b = o.meta["pads"]
                Z[k, j] = V.get(bd.net_of[a], 0) - V.get(bd.net_of[b], 0)
            else:
                Z[k, j] = V.get(o.b, 0) - V.get(o.a, 0)
    return Z


def setup(path, pitch):
    """The board's copper with its whole circuit lumped in: (bd, op, names, injections, nodes, n_src)."""
    b = load(path)
    br = B.build(b)
    bd = M.build(b, br)
    srcs = S.add_all(bd, br)
    obs = O.observers(bd, br, srcs)
    xs, ys = [], []
    for fp in b.footprints:
        for p in fp.pads:
            x, y = transform.pad_xy(fp, p)
            xs.append(x), ys.append(y)
    bm = BoardMesh(path, (min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3), pitch, nsub=2, b=b)
    pads = {q for e in bd.circuit.elems for q in (e.pa, e.pb) if q}
    pads |= {q for s in srcs for q in (s.pa, s.pb) if q} | {q for o in obs for q in (o.pa, o.pb) if q}
    pads |= {q for o in obs if o.kind == "cm" for q in o.meta["pads"]}
    for q in sorted(pads):
        try:
            bm.pad(q)
        except (KeyError, ValueError):
            pass

    def mesh_pad(t):
        if t not in bm.m.terminals:
            raise KeyError(t)
        return t
    term, skipped = lump_all(bd, mesh_pad, lambda x, y, zf, nm: bm.m.part(x, y, name=nm, zf=zf), bm.m.internal_node)
    net = ES.Network(bm.m)
    op = ES.Operator(net)
    names, injs, nodes = ports_of(bd, srcs, obs, term)
    n_src = sum(1 for s in srcs if s.kind == "cell")
    print(f"{len(bm.m.lumped)} parts lumped, {len(bm.m.internal)} internal nodes, {len(skipped)} skipped; "
          f"{n_src} sources, {len(names) - n_src} observers", flush=True)
    return bd, op, names, injs, nodes, n_src


def direct(op, P, rows, cols, f, tol):
    """Z[rows][:, cols] of a direct solve at f, and its iterations."""
    sy = ES.System(op, f)
    X, its = sy.solve_many(P[:, cols], tol=tol, maxiter=3000)
    return P[:, rows].T @ (X[op.net.n_br:] / sy.kap), int(np.max(its))


def check_reference(op, injs, rows, cols, bd, nodes, n_src, names, freqs, tols=(1e-9, 1e-11, 1e-13)):
    """How far the direct solve's layout share moves as its tolerance tightens: the reference's own error."""
    model = RD.Reduced(op, injs)
    for f in freqs:
        Zi = ideal(bd, f, nodes, n_src)[rows]
        L = []
        for t in tols:
            Z, its = direct(op, model.P, rows, cols, f, t)
            L.append((Z - Zi, its, np.abs(Z).max()))
        best = L[-1][0]
        floor = 1e-3 * np.abs(best).max()
        for (Ld, its, zmax), t in zip(L[:-1], tols):
            rel = np.abs(Ld - best) / np.maximum(np.abs(best), floor)
            k = int(np.argmax(rel.max(axis=1)))
            print(f"{f / 1e6:10.4f} MHz tol {t:.0e} ({its} iterations): layout share off by {rel.max():.1e} "
                  f"({names[rows[k]]}: |layout share| {np.abs(best[k]).max():.1e}, |Z| {np.abs(Zi[k]).max():.1e}); "
                  f"largest |Z| {zmax:.1e}", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--pitch", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tol", type=float, default=1e-3)
    ap.add_argument("--fmax", type=float, default=3e8, help="the model's and the test frequencies' top")
    ap.add_argument("--reference-only", type=float, nargs="+", metavar="HZ",
                    help="no model: how the direct solve's layout share at these frequencies moves with its tolerance")
    a = ap.parse_args(argv)
    bd, op, names, injs, nodes, n_src = setup(a.board, a.pitch)
    rows, cols = list(range(n_src, len(names))), list(range(n_src))
    if a.reference_only:
        check_reference(op, injs, rows, cols, bd, nodes, n_src, names, a.reference_only)
        return
    model = RD.Reduced(op, injs, log=lambda m: print(m, flush=True))

    def scale(f):
        Zl = model.Z(f)[np.ix_(rows, cols)] - ideal(bd, f, nodes, n_src)[rows]
        return np.abs(Zl) + 1e-3 * np.abs(Zl).max()
    model.build(a.fmax, tol=a.tol, rows=rows, cols=cols, scale=scale, f0=(0.0, min(10e6, a.fmax / 3)))
    cal = max([tr / es for _, tr, es in model.calibration if es > 0], default=1.0)
    print(f"built in {model.seconds:.0f}s: snapshots {[round(f / 1e6, 4) for f in model.freqs]} MHz, "
          f"basis {model.V.shape[1]}", flush=True)
    rng = np.random.default_rng(a.seed)
    worst = 0.0
    for f in sorted(10 ** rng.uniform(1, np.log10(a.fmax), 10)):
        t0 = time.time()
        sy = ES.System(op, f)
        X, its = sy.solve_many(model.P[:, cols], tol=1e-9, maxiter=3000)
        phi = X[model.nb:] / sy.kap
        Zd = model.P[:, rows].T @ phi
        Zr = model.Z(f)[np.ix_(rows, cols)]
        Zi = ideal(bd, f, nodes, n_src)[rows]
        Ld, Lr = Zd - Zi, Zr - Zi
        floor = 1e-3 * np.abs(Ld).max()
        rel = np.abs(Lr - Ld) / np.maximum(np.abs(Ld), floor)
        Zall = model.Z(f)
        herm = np.linalg.eigvalsh((Zall + Zall.conj().T) / 2)
        worst = max(worst, float(rel.max()))
        k = int(np.argmax(rel.max(axis=1)))
        est = float(np.max(model.error(f, rows, cols) / scale(f))) * cal      # what the build believed
        print(f"{f / 1e6:10.4f} MHz: worst relative error of the layout share {rel.max():.1e} ({names[rows[k]]}; "
              f"estimated {est:.1e}); cond A_r {np.linalg.cond(model.A(f)):.0e}; "
              f"min eig of Re Z {herm.min():+.1e} (max {herm.max():.1e}); direct {int(its.max())} iterations "
              f"{time.time() - t0:.0f}s", flush=True)
    print(f"GATE R2: worst {worst:.1e} against {a.tol:g}: {'PASS' if worst <= a.tol else 'FAIL'}", flush=True)


if __name__ == "__main__":
    main()
