# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Does a projection on a few frequencies' solutions reproduce a board's response at all others?

The board's copper with its two-pad parts lumped in (as kae.excite.evaluate builds it) is solved for
the first commutation cell's edge-band injection and every observer pattern at DC and 10 MHz; more
snapshot frequencies are added greedily where the full system's scaled residual of the reduced
solution is largest (1 kHz .. 300 MHz). The full saddle system is projected by congruence onto the
real span of the snapshots (Galerkin), and every observer read through the reduced solution is
compared with a direct solve at test frequencies that are not snapshots.

    python tools/research/physics/em_reduced_basis_check.py BOARD.kicad_pcb

Finding (docs/topics/architecture/physics-frequency-coverage.md section 3): with source and observer
solutions in the basis, six frequencies give every observer to <= 3.7e-3 relative error from 2 kHz
to 220 MHz; the residual does not track that error (an output-based estimate is needed).
"""
import sys
import time

import numpy as np

import kae.em.solve as ES
import kae.excite.evaluate as EV
import kae.excite.observe as O

GRID = np.logspace(3, np.log10(3e8), 23)            # residual search, 1 kHz .. 300 MHz
TESTS = (2e3, 5e4, 7e5, 4.4e6, 2.5e7, 1.1e8, 2.2e8)  # none of them a snapshot
F_EDGE = 5e6                                         # patterns above this are the edge band's


class Bare(ES.System):
    """The system's operator without its preconditioner factor: enough for residuals."""

    def _precond(self):
        pass


def capture(board):
    """The evaluator's mesh, network, operator, the edge-band source injection and observer patterns."""
    cap, opat = {}, {}
    real_pm, real_pat = ES.potentials_many, O.pattern

    def grab(mesh, injs, f, net=None, op=None, **k):
        if f > F_EDGE:
            cap.update(mesh=mesh, injs=injs, net=net, op=op)
            raise StopIteration
        return real_pm(mesh, injs, f, net=net, op=op, **k)

    def pat(bd, o, f, active=False):
        J = real_pat(bd, o, f, active=active)
        if f > F_EDGE:
            opat[o.name] = J
        return J
    ES.potentials_many, EV.O.pattern = grab, pat
    try:
        EV.evaluate(board, pitch=0.25, log=lambda *a: None, dc=False)
    except StopIteration:
        pass
    finally:
        ES.potentials_many, EV.O.pattern = real_pm, real_pat
    return cap, opat


def main(board):
    cap, opat = capture(board)
    net, op = cap["net"], cap["op"]
    nb = net.n_br
    sy0 = Bare(op, 1e6)
    D = sy0.D

    def vec(J):
        s = np.zeros(sy0.nfree, complex)
        for t, a in J.items():
            if t in net.term_node:
                k = sy0.free_idx[net.term_node[t]]
                if k >= 0:
                    s[k] += a
        return s
    src = vec(cap["injs"][0])
    obs = [vec(J) for J in opat.values()]
    RHS = np.stack([src] + obs, 1)

    def direct(f, R):
        sy = ES.System(op, f)
        x, its = sy.solve_many(R, tol=1e-9, maxiter=3000)
        return np.concatenate([x[:nb], x[nb:] / sy.kap]), int(its.max())

    class Basis:
        def __init__(self):
            self.X = []

        def add(self, X):
            self.X.append(X)
            Xa = np.concatenate(self.X, 1)
            U, sv, _ = np.linalg.svd(np.concatenate([Xa.real, Xa.imag], 1), full_matrices=False)
            self.V = U[:, sv > 1e-10 * sv[0]]
            VI, Vp = self.V[:nb], self.V[nb:]
            self.GL = VI.T @ op.L_apply(VI.astype(complex)).real      # L is real
            self.GD = VI.T @ (D @ Vp)

        def solve(self, f, sy, R):
            """Reduced solutions and the full system's scaled residual (the iterative solver's measure)."""
            VI, Vp = self.V[:nb], self.V[nb:]
            Ar = VI.T @ (sy.zdiag[:, None] * VI) + 2j * np.pi * f * self.GL - self.GD - self.GD.T
            X = self.V @ np.linalg.solve(Ar, Vp.T @ (-R))
            rhs = np.concatenate([np.zeros((nb, R.shape[1]), complex), -R])
            r = rhs - sy.matvec(np.concatenate([X[:nb], X[nb:] * sy.kap]))
            return X, float((np.linalg.norm(r, axis=0) / np.linalg.norm(rhs, axis=0)).max())

    t0 = time.time()
    B = Basis()
    for f in (0.0, 10e6):
        B.add(direct(f, RHS)[0])
    systems = {f: Bare(op, f) for f in GRID}
    for _ in range(4):
        res = {f: B.solve(f, systems[f], RHS)[1] for f in GRID}
        fw = max(res, key=res.get)
        print(f"basis {B.V.shape[1]:2d} vectors: worst residual {res[fw]:.1e} at {fw / 1e6:.4g} MHz", flush=True)
        B.add(direct(fw, RHS)[0])
    print(f"built in {time.time() - t0:.0f}s ({B.V.shape[1]} vectors)", flush=True)
    for f in TESTS:
        xr, r = B.solve(f, Bare(op, f), src[:, None])
        xd, its = direct(f, src[:, None])
        vr = np.array([J @ xr[nb:, 0] for J in obs])
        vd = np.array([J @ xd[nb:, 0] for J in obs])
        rel = np.abs(vr - vd) / np.maximum(np.abs(vd), 1e-30)
        print(f"{f / 1e6:9.4f} MHz: residual {r:.1e}; observers: worst relative error {rel.max():.1e}, "
              f"worst error / largest observer {np.abs(vr - vd).max() / np.abs(vd).max():.1e} "
              f"(direct {its} iterations)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
