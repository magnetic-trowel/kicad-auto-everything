# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics core v2 skeleton (round 3, prefix pc2): one data model, existing kernels, one facade.

Design: docs/topics/physics/physics-core-v2.md; API: docs/topics/physics/physics-core-v2-api.md.

The point is coherence, not coverage: existing round-2 kernels sit behind the proposed
types and calls, on a tiny synthetic PWR/GND plane pair, and every number comes back as a
Belief with an exactness class.

Board: 30 x 20 mm PWR plane over GND (0.1 mm FR-4, 1 oz each), 0.5 mm cells; a 0.5 mm slot
from the top edge down to y = 12 mm at x = 14.5 mm; a VRM pad at the left; loads A (upper
right) and B (lower right); six decaps.
  * Band "DC": the PWR plane as a resistive sheet; the VRM pad is the reference conductor.
  * Bands "AC@f": the plane pair as one complex telegrapher sheet,
        gamma^2 = Z_sq * Y_p,  Z_sq = 2 R_s(f) + j w mu0 d,  Y_p = j w C'(1 - j tan d),
    with decaps and the VRM as posts to the GND plane (the reference conductor).
Ports A and B inject 1 A spread over their pads; port S is a Kelvin tap pair (a sense loop that
draws no current). Budgets per band: the self term Z_AA and two interaction terms, Z_BA (shared
path: B's voltage per ampere drawn by A) and Z_SA (what the sense loop reads per ampere of A).

Kernels wired here:
  * K-SHEET  operator per band: cd_conductor_passport.grid_laplacian (lens CD) gives the cell
             graph; branch admittances and shunts make it a DC, thermal or telegrapher sheet.
  * K-RESP   on any factored operator: states, Tellegen attribution, exact counterfactuals
             (rank-k Woodbury removals with K-TOP resolving singular cases; Thevenin
             additions), the Woodbury eigenvalues (event proximity / perturbation radius),
             leverage (exact and a Johnson-Lindenstrauss sketch), the generalized Foster sum,
             and the asymptotic crack screen of lenses CT/SY/CD.
  * K-TOP    band connectivity, bridges (Tarjan) and event classification, solver-free.
  * K-FLOOR  Beckmann floor; Prager-Synge bracket via vp_floors._q4_energy_solve (lens VP).
  * facade   PhysicsCore.passport(), why_here(), what_if_cut(), where_add(), explain().

Sections: python pc2_core_skeleton.py [exact|events|dispatch|passport|floors|bench|all]
  exact     Woodbury/Thevenin/Tellegen/Foster vs re-factorization; certified first-order bounds
  events    grow a cut until it disconnects: Woodbury eigenvalue -> 1 exactly at the K-TOP event
  dispatch  when first-order and crack prices hold, vs frequency (local vs resonant amplification)
  passport  passports, jobs, why_here(), explain(), what_if_cut(), where_add()
  floors    Beckmann floor; Prager-Synge bracket vs the cell-graph value
  bench     costs vs grid size (2.4k-153k cells)
'all' runs everything except 'bench' in under a minute on one core; 'bench' takes about
10-60 s. numpy + scipy; deterministic. Numbers quoted [C] in the pc2 docs come from here.
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import enum  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402

import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402
from scipy.sparse.csgraph import connected_components  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cd_conductor_passport import grid_laplacian  # noqa: E402  (lens CD: cell graph)
from ct_cut_topology import ligament_factor  # noqa: E402  (lens CT: finite-width crack factor)
import vp_floors  # noqa: E402  (lens VP: conforming Q4 energy solves for the bracket)

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
RHO = 1.72e-8
T_CU = 35e-6
RS = RHO / T_CU
DX = 0.5e-3
NX, NY = 60, 40
H_PAIR, ER, TAND = 0.1e-3, 4.3, 0.02


# ============================================================================ data model
class Exactness(enum.IntEnum):
    """What a number is guaranteed to be, and relative to what (Belief.relative_to)."""
    TOPOLOGICAL = 0   # E0 metric-free, true for any geometry with this connectivity
    ALGEBRAIC = 1     # E1 exact on the discretized model, to round-off (rank-k, Tellegen, Foster)
    CERTIFIED = 2     # E2 one- or two-sided variational bound on the continuum model
    ASYMPTOTIC = 3    # E3 closed form with a known error law (crack, polarization, images)
    CALIBRATED = 4    # E4 statistical, spread from calibration data
    CONJECTURED = 5   # E5 hypothesis, not yet checked by any model


@dataclass
class Belief:
    value: complex
    unit: str
    exactness: Exactness
    relative_to: str
    interval: tuple = None
    lineage: tuple = ()
    note: str = ""

    def __str__(self):
        v = self.value
        s = f"{v.real:+.4g}{v.imag:+.4g}j" if isinstance(v, complex) and abs(v.imag) > 1e-15 else f"{float(np.real(v)):+.4g}"
        iv = f" in [{self.interval[0]:.4g}, {self.interval[1]:.4g}]" if self.interval else ""
        return f"{s} {self.unit}{iv} ({self.exactness.name}, rel. {self.relative_to})"


@dataclass
class Band:
    name: str
    f: float            # Hz; 0 = DC
    reference: str      # the conductor that closes currents in this band


@dataclass
class ClosedLoopBudget:
    """A budget names the loop that observes it: the victim port's own terminal pair (its closure)."""
    id: str
    band: str
    source: str          # aggressor port
    victim: str          # observing port (== source for a self term)
    bound: float         # on |Z| in ohm (the demo uses 1.25 x the as-built value)

    @property
    def cls(self):
        return "self" if self.source == self.victim else "interaction"


@dataclass
class Piece:
    id: str
    kind: str            # tile | pad | post
    nodes: np.ndarray    # mesh nodes it owns (the mesh is disposable; the id is not)
    posts: tuple = ()    # names of post branches it owns


@dataclass
class Job:
    verb: str            # carries | lowers | raises | anchors | dead
    budget: str
    delta_rel: float     # exact relative change of |budget| if the piece's copper were removed
    value: float         # |delta| / slack


@dataclass
class Passport:
    piece: str
    band: str
    transit: dict        # port -> current through the piece per ampere of that port (A/A)
    attribution: dict    # budget -> exact additive Tellegen share (ohm)
    removal: dict        # budget -> Belief (exact change of Z if the piece's copper is removed)
    proximity: float     # largest Woodbury eigenvalue of the removal (1 = topological event)
    events: list
    jobs: list = field(default_factory=list)


# ============================================================================ K-SHEET
class GraphOperator:
    """Nodal operator Y = sum_b y_b a_b a_b^T. Branch b joins ea[b] and eb[b]; eb = -1 is the band's
    reference conductor. Real y: resistive or thermal sheet; complex y: telegrapher sheet with posts."""

    def __init__(self, n, ea, eb, y, kind, names=None):
        self.n, self.ea, self.eb = n, np.asarray(ea), np.asarray(eb)
        self.y = np.asarray(y)
        self.kind = np.asarray(kind)          # 'plane' | 'shunt' | 'post' | 'tie'
        self.names = np.asarray(names if names is not None else [""] * len(self.y))
        self.dtype = complex if np.iscomplexobj(self.y) else float
        t0 = time.perf_counter()
        self.lu = spla.splu(self.matrix().tocsc(), permc_spec="MMD_AT_PLUS_A")
        self.t_factor = time.perf_counter() - t0

    def incidence(self, B=None):
        B = np.arange(len(self.y)) if B is None else np.asarray(B)
        a, b = self.ea[B], self.eb[B]
        k = np.arange(len(B))
        g = b >= 0
        rows = np.r_[a, b[g]]
        cols = np.r_[k, k[g]]
        vals = np.r_[np.ones(len(B)), -np.ones(g.sum())]
        return sp.csr_matrix((vals, (rows, cols)), shape=(self.n, len(B)))

    def matrix(self, drop=None):
        y = self.y.copy()
        if drop is not None:
            y[np.asarray(drop)] = 0
        A = self.incidence()
        return (A @ sp.diags(y) @ A.T).tocsr()

    def solve(self, rhs):
        rhs = np.asarray(rhs)
        if self.dtype is float and np.iscomplexobj(rhs):
            return self.lu.solve(np.ascontiguousarray(rhs.real)) + 1j * self.lu.solve(np.ascontiguousarray(rhs.imag))
        return self.lu.solve(np.ascontiguousarray(rhs.astype(self.dtype)))

    def bv(self, U, B=None):
        """Branch voltages (len(B) x m) for node potentials U (n x m)."""
        return (self.incidence(B).T @ U)


def zsq(f):
    """Plane-pair series impedance per square: both planes' R (thin sheet or skin limited) + mu0 d."""
    if f == 0:
        return RS
    delta = math.sqrt(RHO / (math.pi * f * MU0))
    return 2 * RHO / min(T_CU, delta) + 1j * 2 * math.pi * f * MU0 * H_PAIR


def z_decap(f):
    w = 2 * math.pi * f
    return 0.010 + 1j * w * 0.7e-9 + 1 / (1j * w * 100e-9)


def z_vrm(f):
    return 0.010 + 1j * 2 * math.pi * f * 2e-9


class Board:
    """The synthetic plane pair: cells, pads, posts, ports and pieces (2 x 2 mm tiles + pads + posts)."""

    def __init__(self, nx=NX, ny=NY, dx=DX, slot=True):
        self.nx, self.ny, self.dx = nx, ny, dx
        jj, ii = np.mgrid[0:ny, 0:nx]
        self.xc, self.yc = (ii + 0.5) * dx * 1e3, (jj + 0.5) * dx * 1e3      # mm
        dead = ((self.xc > 14.5) & (self.xc < 15.0) & (self.yc > 12.0)) if slot else np.zeros((ny, nx), bool)
        idx, E, _, _ = grid_laplacian(nx, ny, dead)                          # lens CD's cell graph
        live = ~dead.ravel()
        self.node = -np.ones(nx * ny, int)
        self.node[live] = np.arange(live.sum())
        self.n = int(live.sum())
        self.E = self.node[E]                                                # plane branches (a, b)
        self.horiz = (E[:, 1] - E[:, 0]) == 1
        self.cell_of = np.nonzero(live)[0]                                   # node -> flat cell index

        def cells(x0, x1, y0, y1):
            m = (self.xc >= x0) & (self.xc < x1) & (self.yc >= y0) & (self.yc < y1) & ~dead
            return self.node[np.nonzero(m.ravel())[0]]
        self.pads = {"VRM": cells(0.5, 2.0, 9.0, 11.0), "A": cells(24.0, 25.0, 14.5, 15.5), "B": cells(24.0, 25.0, 4.5, 5.5)}
        self.decaps = {f"C{k + 1}": cells(x - 0.25, x + 0.25, y - 0.25, y + 0.25)[0]
                       for k, (x, y) in enumerate(((22, 15), (26, 15), (22, 5), (26, 5), (10, 3), (10, 17)))}
        self.pads["S"] = np.r_[cells(19.0, 19.5, 13.0, 13.5), cells(19.0, 19.5, 8.0, 8.5)]
        self.inj = {}
        for p in ("A", "B"):
            v = np.zeros(self.n)
            v[self.pads[p]] = 1.0 / len(self.pads[p])
            self.inj[p] = v
        v = np.zeros(self.n)                        # S: a sense pair (Kelvin taps) reading V(P1) - V(P2)
        v[self.pads["S"][0]], v[self.pads["S"][1]] = 1.0, -1.0
        self.inj["S"] = v
        self.ports = ["A", "B", "S"]

    def operator(self, band):
        """K-SHEET: build the band's operator on this board (one factorization per band and epoch)."""
        nE = len(self.E)
        ea, eb = list(self.E[:, 0]), list(self.E[:, 1])
        kind, names = ["plane"] * nE, [""] * nE
        if band.f == 0:
            y = [1 / RS] * nE
            for c in self.pads["VRM"]:                     # the VRM pad is this band's reference
                ea.append(c); eb.append(-1); y.append(1e4 / RS); kind.append("tie"); names.append("VRM.tie")
        else:
            w = 2 * math.pi * band.f
            y = [1 / zsq(band.f)] * nE
            ysh = 1j * w * EPS0 * ER * (1 - 1j * TAND) * self.dx ** 2 / H_PAIR
            for c in range(self.n):
                ea.append(c); eb.append(-1); y.append(ysh); kind.append("shunt"); names.append("")
            for name, c in self.decaps.items():
                ea.append(c); eb.append(-1); y.append(1 / z_decap(band.f)); kind.append("post"); names.append(name)
            nv = len(self.pads["VRM"])
            for c in self.pads["VRM"]:
                ea.append(c); eb.append(-1); y.append(1 / (z_vrm(band.f) * nv)); kind.append("post"); names.append("VRM.post")
        return GraphOperator(self.n, ea, eb, np.array(y), kind, names)

    def pieces(self, tile_mm=2.0):
        t = int(round(tile_mm / (self.dx * 1e3)))
        padnodes = np.concatenate([v for k, v in self.pads.items() if k != "S"])
        out = {}
        cj, ci = np.divmod(self.cell_of, self.nx)
        tid = (ci // t) * 1000 + (cj // t)
        for key in np.unique(tid):
            nodes = np.setdiff1d(np.nonzero(tid == key)[0], padnodes)
            if len(nodes):
                pid = f"PWR.t{key // 1000:02d}.{key % 1000:02d}"
                out[pid] = Piece(pid, "tile", nodes)
        for p, nodes in self.pads.items():
            if p != "S":
                out[f"PAD.{p}"] = Piece(f"PAD.{p}", "pad", nodes)
        for name in list(self.decaps) + ["VRM.post"]:
            out[name] = Piece(name, "post", np.array([], int), (name,))
        return out


# ============================================================================ K-TOP
def components(op, removed=()):
    """Connected components of the band graph (reference conductor = node n). Solver-free (E0)."""
    keep = np.ones(len(op.y), bool)
    keep[list(removed)] = False
    keep &= op.y != 0
    a, b = op.ea[keep], np.where(op.eb[keep] < 0, op.n, op.eb[keep])
    g = sp.csr_matrix((np.ones(a.size), (a, b)), shape=(op.n + 1, op.n + 1))
    return connected_components(g, directed=False)


def bridges(op, removed=()):
    """Branches whose removal disconnects the band graph (Tarjan, iterative; parallel branches ok)."""
    keep = np.ones(len(op.y), bool)
    keep[list(removed)] = False
    N = op.n + 1
    adj = [[] for _ in range(N)]
    for e in np.nonzero(keep)[0]:
        a, b = op.ea[e], (op.eb[e] if op.eb[e] >= 0 else op.n)
        adj[a].append((b, e)); adj[b].append((a, e))
    disc = np.full(N, -1); low = np.zeros(N, int); out = []; t = 0
    for s in range(N):
        if disc[s] >= 0:
            continue
        disc[s] = low[s] = t; t += 1
        stack = [(s, -1, iter(adj[s]))]
        while stack:
            v, pe, it = stack[-1]
            for w, e in it:
                if e == pe:
                    continue
                if disc[w] < 0:
                    disc[w] = low[w] = t; t += 1
                    stack.append((w, e, iter(adj[w])))
                    break
                low[v] = min(low[v], disc[w])
            else:
                stack.pop()
                if stack:
                    u = stack[-1][0]
                    low[u] = min(low[u], low[v])
                    if low[v] > disc[u]:
                        out.append(pe)
    return out


def classify(op, removed, terminals):
    """Topological reading of an edit: which terminals lose the reference, which copper floats."""
    _, lab = components(op, removed)
    ref = lab[op.n]
    ev = [f"disconnects {p}" for p, nodes in terminals.items() if np.any(lab[nodes] != ref)]
    keep = np.ones(len(op.y), bool)
    keep[list(removed)] = False
    deg = np.bincount(op.ea[keep], minlength=op.n) + np.bincount(op.eb[keep][op.eb[keep] >= 0], minlength=op.n)
    term = np.concatenate(list(terminals.values()))
    stray = np.setdiff1d(np.unique(lab[:op.n][deg > 0]), np.r_[ref, lab[term]])
    if len(stray):
        ev.append(f"floats {len(stray)} island(s)")
    return ev


# ============================================================================ K-RESP
def removal_quote(op, B, U):
    """Exact change of Z = E^T Y^-1 E (ports in the columns of U = Y^-1 E) when branches B are removed.

    dZ = V^T (Y_B^-1 - A_B^T Y^-1 A_B)^-1 V, V = A_B^T U (Woodbury; k = |B| solves). Singular cases
    are resolved by least squares and read by K-TOP: a consistent right-hand side means copper that
    merely floats (exact price finite); an inconsistent one means a terminal is cut off (infinite).
    Also returns the first Neumann term V^T Y_B V (the adjoint price) and the Woodbury eigenvalues,
    i.e. those of P_B = diag(y_B) A_B^T Y^-1 A_B."""
    B = np.asarray(B)
    A = op.incidence(B)
    S = A.T @ op.solve(A.toarray())
    yB = op.y[B]
    V = A.T @ U
    M = np.diag(1 / yB) - S
    X = np.linalg.lstsq(M, V, rcond=1e-11)[0]
    ok = np.linalg.norm(M @ X - V) <= 1e-7 * max(np.linalg.norm(V), 1e-300)
    dZ = V.T @ X if ok else np.full((U.shape[1], U.shape[1]), np.inf)
    first = V.T @ (yB[:, None] * V)
    lam = np.linalg.eigvals(yB[:, None] * S)
    return dZ, first, lam, ok


def addition_quote(op, m, n, z, U):
    """Exact change of Z when an impedance z is added between nodes m and n (n = -1: reference). One solve."""
    a = np.zeros(op.n, dtype=op.dtype)
    a[m] = 1
    if n >= 0:
        a[n] = -1
    zth = a @ op.solve(a)
    dv = a @ U
    return -np.outer(dv, dv) / (z + zth)


def attribution(op, U, p, q):
    """Tellegen: Z_qp = sum_b y_b v_b^q v_b^p, exact and additive over branches (any band)."""
    V = op.bv(U)
    return op.y * V[:, q] * V[:, p]


def leverage_exact(op, chunk=800):
    """rho_b = y_b a_b^T Y^-1 a_b for every branch (sum = n: the generalized Foster theorem)."""
    out = np.zeros(len(op.y), dtype=complex)
    for c0 in range(0, len(op.y), chunk):
        B = np.arange(c0, min(len(op.y), c0 + chunk))
        A = op.incidence(B)
        W = op.solve(A.toarray())
        out[B] = op.y[B] * np.asarray((A.multiply(W)).sum(0)).ravel()
    return out


def leverage_sketch(op, k=48, seed=7):
    """Johnson-Lindenstrauss (Spielman-Srivastava) estimate of rho for all branches from k solves (real y)."""
    rng = np.random.default_rng(seed)
    A = op.incidence()
    Q = rng.choice([-1.0, 1.0], size=(k, len(op.y))) / math.sqrt(k)
    Z = op.solve(np.asarray((A @ sp.diags(np.sqrt(op.y.real)) @ Q.T)))   # n x k
    return op.y.real * np.asarray(((A.T @ Z) ** 2).sum(1)).ravel()


def crack_screen(op, B, U, z_sq, edge=False, ligament_x=None):
    """Asymptotic (E3) price of a NEW straight zero-width cut B: dZ_qp ~ c (pi/4) Z_sq dpsi_p dpsi_q
    (c = 2 for an edge notch; lenses CT, SY, CD), dpsi = current through the cut line per unit port
    current, with the grid's effective crack length (k + 1) cells (lens CD). ligament_x = cut length /
    local strip width applies lens CT's finite-width factor (8/pi^2) ln sec(pi x/2) / x^2. Valid while
    the cut is short compared with the screening length 1/|gamma| and the mode bandwidths ('sweep')."""
    k = len(B)
    I = op.y[B][:, None] * op.bv(U, B)
    dpsi = I.sum(0) * (k + 1) / k
    lig = 1.0 if ligament_x is None else float(ligament_factor(ligament_x)[0])
    return (2 if edge else 1) * math.pi / 4 * z_sq * lig * np.outer(dpsi, dpsi)


def brute_force_Z(op, removed=(), added=None, E=None):
    """Re-factor after an edit; floating nodes without injection are dropped. For checks only."""
    y = op.y.copy()
    y[list(removed)] = 0
    ea, eb = list(op.ea), list(op.eb)
    if added is not None:
        m, n, z = added
        ea.append(m); eb.append(n); y = np.r_[y, 1 / z]
    o = GraphOperator.__new__(GraphOperator)
    o.n, o.ea, o.eb, o.y = op.n, np.array(ea), np.array(eb), y
    Y = o.matrix().tocsr()
    live = np.abs(Y.diagonal()) > 0
    ncomp, lab = components(o)
    ref = lab[op.n]
    live &= lab[:op.n] == ref
    Yl = Y[live][:, live].tocsc()
    if np.any(E[~live] != 0):
        return np.full((E.shape[1], E.shape[1]), np.inf)
    Ul = spla.splu(Yl).solve(np.ascontiguousarray(E[live].astype(complex if np.iscomplexobj(y) else float)))
    return E[live].T @ Ul


# ============================================================================ K-FLOOR
def beckmann_floor(w1_m, area_m2, rs=RS):
    """Continuum floor R >= R_s W1^2 / A for any copper of area A moving 1 A over transport work W1 (lens VP)."""
    return rs * w1_m ** 2 / area_m2


def bracket_notched_strip(n_per_mm=4, L=12.0, W=4.0, notch=(5.0, 6.0, 1.5)):
    """Prager-Synge bracket R_phi <= R <= R_psi (squares) for a strip with an edge notch, on one Q4 mesh
    (vp_floors._q4_energy_solve), plus the cell-graph (K-SHEET) value on the same cells."""
    nx, ny = int(L * n_per_mm), int(W * n_per_mm)
    jj, ii = np.mgrid[0:ny, 0:nx]
    xc, yc = (ii + 0.5) / n_per_mm, (jj + 0.5) / n_per_mm
    mask = ~((xc > notch[0]) & (xc < notch[1]) & (yc < notch[2]))
    nj, ni = np.mgrid[0:ny + 1, 0:nx + 1]
    nid = (nj * (nx + 1) + ni).ravel()
    used = np.zeros((ny + 1) * (nx + 1), int)
    cj, ci = np.nonzero(mask)
    for dj, di in ((0, 0), (0, 1), (1, 0), (1, 1)):
        np.add.at(used, (cj + dj) * (nx + 1) + ci + di, 1)
    nj, ni = nj.ravel(), ni.ravel()
    left, right = nid[(ni == 0) & (used > 0)], nid[(ni == nx) & (used > 0)]
    g = vp_floors._q4_energy_solve(mask, np.r_[left, right], np.r_[np.zeros(len(left)), np.ones(len(right))])
    bnd = (used > 0) & (used < 4)
    top = nid[bnd & (nj == ny)]
    bottom = nid[bnd & (nj < ny) & (((ni > 0) & (ni < nx)) | (nj == 0))]
    r_hi = vp_floors._q4_energy_solve(mask, np.r_[top, bottom], np.r_[np.zeros(len(top)), np.ones(len(bottom))])
    # cell graph with half-cell terminal links (the K-SHEET discretization)
    idx, E, _, G = grid_laplacian(nx, ny, ~mask)
    live = mask.ravel()
    node = -np.ones(nx * ny, int); node[live] = np.arange(live.sum())
    Gl = G[live][:, live].tolil()
    b = np.zeros(live.sum())
    for c in np.nonzero(live)[0]:
        j, i = divmod(c, nx)
        if i == 0:
            Gl[node[c], node[c]] += 2.0; b[node[c]] += 2.0
        if i == nx - 1:
            Gl[node[c], node[c]] += 2.0
    v = spla.spsolve(Gl.tocsc(), b)
    cur = sum(2.0 * (1 - v[node[c]]) for c in np.nonzero(live)[0] if c % nx == 0)
    return 1 / g, r_hi, 1 / cur


# ============================================================================ facade
class PhysicsCore:
    """One board, its bands and the queries the optimizer, the critics, the LLM and humans use."""

    def __init__(self, board, bands):
        self.board, self.bands = board, {b.name: b for b in bands}
        self.ops = {b.name: board.operator(b) for b in bands}
        self.E = np.stack([board.inj[p] for p in board.ports], 1)
        self.U = {k: op.solve(self.E) for k, op in self.ops.items()}
        self.Z = {k: self.E.T @ self.U[k] for k in self.ops}
        self.pieces = board.pieces()
        self.pidx = {p: i for i, p in enumerate(board.ports)}
        self.budgets = []
        for k in self.ops:
            for s, v in (("A", "A"), ("A", "B"), ("A", "S")):
                z0 = abs(self.Z[k][self.pidx[v], self.pidx[s]])
                self.budgets.append(ClosedLoopBudget(f"Z_{v}{s}@{k}", k, s, v, 1.25 * z0))
        self.epoch = 0
        self._removal_cache, self._attr = {}, {}

    # ---- edits and quotes --------------------------------------------------------------
    def piece_branches(self, pid, band):
        """The edit 'remove this piece's copper': every non-post branch touching its nodes (posts: the post)."""
        op, pc = self.ops[band], self.pieces[pid]
        if pc.kind == "post":
            return np.nonzero(op.names == pc.posts[0])[0]
        inc = np.isin(op.ea, pc.nodes) | np.isin(op.eb, pc.nodes)
        return np.nonzero(inc & (op.y != 0) & (op.kind != "post"))[0]

    def attr(self, bud):
        key = (bud.band, bud.id, self.epoch)
        if key not in self._attr:
            self._attr[key] = attribution(self.ops[bud.band], self.U[bud.band], self.pidx[bud.source], self.pidx[bud.victim])
        return self._attr[key]

    def quote_remove(self, band, B, terminals=True):
        """Stage-2 quote: exact deltas for every budget of the band, the first-order price, the Woodbury
        eigenvalues and the topological events. Returns {budget: (exact Belief, first Belief)}, lam, events."""
        op = self.ops[band]
        dZ, first, lam, ok = removal_quote(op, B, self.U[band])
        ev = classify(op, B, {p: self.board.pads[p] for p in self.board.ports}) if terminals else []
        out = {}
        for bud in self.budgets:
            if bud.band != band:
                continue
            q, p = self.pidx[bud.victim], self.pidx[bud.source]
            rel = f"M:{band}-sheet-{self.board.dx * 1e3:.1f}mm-e{self.epoch}"
            out[bud.id] = (Belief(complex(dZ[q, p]), "ohm", Exactness.ALGEBRAIC, rel, lineage=("K-SHEET", "K-RESP.woodbury")),
                           Belief(complex(first[q, p]), "ohm", Exactness.ASYMPTOTIC, rel, lineage=("K-RESP.adjoint",)))
        return out, lam, ev

    def rel_change(self, bud, dz):
        z0 = self.Z[bud.band][self.pidx[bud.victim], self.pidx[bud.source]]
        if not np.isfinite(dz):
            return np.inf
        return (abs(z0 + dz) - abs(z0)) / abs(z0)

    # ---- passports and the human/LLM queries --------------------------------------------------
    def passport(self, pid, band):
        op = self.ops[band]
        B = self.piece_branches(pid, band)
        key = (pid, band, self.epoch)
        if key not in self._removal_cache:
            self._removal_cache[key] = self.quote_remove(band, B)
        quotes, lam, ev = self._removal_cache[key]
        V = op.bv(self.U[band], B)
        I = op.y[B][:, None] * V
        pc = self.pieces[pid]
        if pc.kind != "post":         # current through the piece: half the boundary inflow
            inside_a, inside_b = np.isin(op.ea[B], pc.nodes), np.isin(op.eb[B], pc.nodes)
            bnd = inside_a ^ inside_b
            half = 1.0 if pc.kind == "pad" else 0.5
            transit = {p: float(half * np.abs(I[bnd, i]).sum()) for p, i in self.pidx.items()}
        else:
            transit = {p: float(np.abs(I[:, i]).sum()) for p, i in self.pidx.items()}
        attr = {}
        for bud in self.budgets:
            if bud.band != band:
                continue
            a = self.attr(bud)
            w = np.ones(len(B))
            if pc.kind != "post":     # a branch shared with a neighbour counts half to each
                both = np.isin(op.ea[B], pc.nodes) & (np.isin(op.eb[B], pc.nodes) | (op.eb[B] < 0))
                w = np.where(both, 1.0, 0.5)
            attr[bud.id] = complex((a[B] * w).sum())
        good = lam[np.abs(1 - lam) > 1e-8]      # modes of copper that merely floats are excluded
        prox = float(np.max(np.abs(good))) if len(good) else 0.0
        pp = Passport(pid, band, transit, attr, {k: v[0] for k, v in quotes.items()}, prox, ev)
        for bud in self.budgets:
            if bud.band != band:
                continue
            d = quotes[bud.id][0].value
            r = self.rel_change(bud, d)
            slack = bud.bound - abs(self.Z[band][self.pidx[bud.victim], self.pidx[bud.source]])
            if not np.isfinite(r):
                pp.jobs.append(Job("anchors", bud.id, np.inf, np.inf))
            elif abs(r) >= 0.01:
                verb = ("carries" if r > 0 else "loads") if bud.cls == "self" else ("lowers" if r > 0 else "raises")
                dabs = abs(abs(self.Z[band][self.pidx[bud.victim], self.pidx[bud.source]] + d) -
                           abs(self.Z[band][self.pidx[bud.victim], self.pidx[bud.source]]))
                pp.jobs.append(Job(verb, bud.id, r, dabs / slack))
        if not pp.jobs:
            pp.jobs.append(Job("dead", "-", 0.0, 0.0))
        return pp

    def why_here(self, pid):
        lines = []
        for band in self.ops:
            pp = self.passport(pid, band)
            for j in sorted(pp.jobs, key=lambda j: -j.value):
                if j.verb == "dead":
                    lines.append(f"{band}: no job above 1% (removal changes every budget < 1%)")
                elif j.verb == "anchors":
                    lines.append(f"{band}: anchors {j.budget} (removal cuts a terminal off: series path)")
                else:
                    tgt = j.budget.split("@")[0]
                    what = {"carries": "carries", "loads": "loads", "lowers": "lowers coupling", "raises": "raises coupling"}[j.verb]
                    lines.append(f"{band}: {what} {tgt}: without it {j.delta_rel * 100:+.1f}% (exact), value {j.value:.2f} of slack")
        return lines

    def explain(self, bud_id, top=4):
        """Self-like budgets (chi >= 0.5): additive attribution. Otherwise: exact counterfactuals."""
        bud = next(b for b in self.budgets if b.id == bud_id)
        tiles = [p for p, pc in self.pieces.items() if pc.kind == "tile"]
        pps = {p: self.passport(p, bud.band) for p in tiles}
        a = np.array([pps[p].attribution[bud_id] for p in tiles])
        chi = abs(a.sum()) / np.abs(a).sum()
        if chi >= 0.5:
            order = np.argsort(-np.abs(a))[:top]
            return chi, "attribution", [(tiles[i], a[i] / a.sum()) for i in order]
        r = np.array([self.rel_change(bud, pps[p].removal[bud_id].value) for p in tiles])
        r = np.where(np.isfinite(r), r, 0.0)
        order = np.argsort(-np.abs(r))[:top]
        return chi, "counterfactual", [(tiles[i], r[i]) for i in order]

    def where_add(self, band, candidates):
        """Exact (Thevenin) value of each candidate addition (m, n, z) for every budget of the band."""
        op = self.ops[band]
        rows = []
        for (m, n, z) in candidates:
            dZ = addition_quote(op, m, n, z, self.U[band])
            rows.append({b.id: self.rel_change(b, dZ[self.pidx[b.victim], self.pidx[b.source]])
                         for b in self.budgets if b.band == band})
        return rows


# ============================================================================ sections
def make_core(freqs=(300e6,)):
    bands = [Band("DC", 0.0, "VRM pad")] + [Band(f"AC{f / 1e6:g}M", f, "GND plane") for f in freqs]
    return PhysicsCore(Board(), bands)


def cut_line(board, op, x_mm, y0_mm, y1_mm):
    """Plane branches crossing the vertical line x = x_mm between y0 and y1 (a zero-width cut)."""
    a, b = board.E[:, 0], board.E[:, 1]
    xa, ya = board.xc.ravel()[board.cell_of[a]], board.yc.ravel()[board.cell_of[a]]
    xb = board.xc.ravel()[board.cell_of[b]]
    sel = board.horiz & (xa < x_mm) & (xb > x_mm) & (ya > y0_mm) & (ya < y1_mm)
    return np.nonzero(sel)[0]


def sec_exact(core):
    print("== exact: K-RESP identities vs brute-force re-factorization (max relative error)")
    rng = np.random.default_rng(3)
    for band, op in core.ops.items():
        U, Z0 = core.U[band], core.Z[band]
        lev = leverage_exact(op)
        errs1, errsk, errsa = [], [], []
        for b in rng.choice(len(op.y), 25, replace=False):
            dZ, _, _, ok = removal_quote(op, [b], U)
            Zb = brute_force_Z(op, [b], E=core.E)
            if ok and np.all(np.isfinite(Zb)):
                errs1.append(np.max(np.abs(Z0 + dZ - Zb)) / np.max(np.abs(Zb)))
        tiles = [p for p, pc in core.pieces.items() if pc.kind == "tile"]
        for p in rng.choice(tiles, 10, replace=False):
            B = core.piece_branches(p, band)
            dZ, _, _, ok = removal_quote(op, B, U)
            Zb = brute_force_Z(op, B, E=core.E)
            if ok:                       # a removed Kelvin tap is an infinite (disconnect) price in both
                errsk.append(np.max(np.abs(Z0 + dZ - Zb)) / np.max(np.abs(Zb)))
        for _ in range(10):
            m, n = rng.choice(op.n, 2, replace=False)
            z = RS if band == "DC" else zsq(core.bands[band].f)
            dZ = addition_quote(op, m, n, z, U)
            Zb = brute_force_Z(op, added=(m, n, z), E=core.E)
            errsa.append(np.max(np.abs(Z0 + dZ - Zb)) / np.max(np.abs(Zb)))
        a = attribution(op, U, 0, 1)
        print(f"  {band:7s} n = {op.n}, branches = {len(op.y)}, factor {op.t_factor * 1e3:.1f} ms | "
              f"rank-1 {max(errs1):.1e}, piece (rank 30-50) {max(errsk):.1e}, Thevenin {max(errsa):.1e} | "
              f"Foster sum(rho) - n = {abs(lev.sum() - op.n):.1e} | Tellegen sum(a) - Z_BA = {abs(a.sum() - Z0[1, 0]) / abs(Z0[1, 0]):.1e}")
    # first-order prices as certified bounds at DC (P_B is symmetric PSD there)
    op, U = core.ops["DC"], core.U["DC"]
    viol, vx, ratios_self, ratios_x = 0, 0, [], {1: [], 2: []}
    for p in [p for p, pc in core.pieces.items() if pc.kind == "tile"]:
        B = core.piece_branches(p, "DC")
        dZ, first, lam, ok = removal_quote(op, B, U)
        if not ok:                       # disconnects a terminal: an event, priced as infinite
            continue
        good = lam.real[np.abs(1 - lam) > 1e-8]
        lmax = good.max() if len(good) else 0.0
        w = np.sqrt(op.y[B].real)[:, None] * op.bv(U, B)
        nw = np.linalg.norm(w, axis=0)
        for i in (0, 1, 2):
            if first[i, i] > 1e-12 * core.Z["DC"][i, i]:
                r = dZ[i, i] / first[i, i]
                ratios_self.append(r)
                viol += not (1 - 1e-9 <= r <= 1 / (1 - lmax) + 1e-9)
        for q in (1, 2):
            if abs(first[q, 0]) > 1e-12 * RS:
                ratios_x[q].append(dZ[q, 0] / first[q, 0])
            vx += abs(dZ[q, 0] - first[q, 0]) > nw[q] * nw[0] * lmax / (1 - lmax) * (1 + 1e-9) + 1e-18
    rs_ = np.array(ratios_self)
    print(f"  DC tiles: self terms exact/first-order in [{rs_.min():.2f}, {rs_.max():.2f}], median {np.median(rs_):.2f};"
          f" bound 1 <= ratio <= 1/(1 - lambda_max) violated {viol}/{len(rs_)}")
    for q, nm in ((1, "Z_BA (shared path)"), (2, "Z_SA (Kelvin taps)")):
        rx = np.array(ratios_x[q])
        print(f"           interaction {nm}: exact/first-order in [{rx.min():.2f}, {rx.max():.2f}],"
              f" sign flips {np.sum(rx < 0)}/{len(rx)}")
    print(f"           |exact - first| <= |w_q||w_p| lambda/(1 - lambda) violated {vx}/{len(ratios_x[1]) + len(ratios_x[2])}")
    lev = leverage_exact(op).real
    est = leverage_sketch(op, 48)
    plane = op.kind == "plane"
    rel = np.abs(est[plane] - lev[plane]) / lev[plane]
    print(f"  DC leverage (plane branches): exact median {np.median(lev[plane]):.3f}, max {lev[plane].max():.3f};"
          f" JL sketch (48 solves) median rel. error {np.median(rel):.2f}, 90th pct {np.percentile(rel, 90):.2f}")


def sec_events(core):
    print("== events: grow a zero-width cut from the slot tip (y = 12 mm) to the bottom edge, x = 14.5 mm")
    print("   DC: exact dR_A, first-order, lambda_max of the Woodbury matrix, K-TOP bridges and events;"
          " AC 300 MHz: exact d|Z_A| and spectral radius")
    b = core.board
    opd, opa = core.ops["DC"], core.ops["AC300M"]
    full = cut_line(b, opd, 14.5, 0.0, 12.0)
    ys = b.yc.ravel()[b.cell_of[b.E[full, 0]]]
    full = full[np.argsort(-ys)]                       # from the tip downwards
    za, zd = core.Z["AC300M"][0, 0], core.Z["DC"][0, 0]
    print("   cut to y   k  | dR_A exact      first-order  lambda_max | bridges events               | AC d|Z_A|  rho(P)")
    for k in (1, 6, 12, 18, 21, 22, 23, 24):
        B = full[:k]
        dZ, first, lam, ok = removal_quote(opd, B, core.U["DC"])
        br = len([e for e in bridges(opd, B) if opd.kind[e] == "plane"])
        ev = classify(opd, B, {p: b.pads[p] for p in b.ports}) or ["none"]
        dZa, _, lama, _ = removal_quote(opa, B, core.U["AC300M"])
        ytip = 12.0 - 0.5 * k
        dr = f"{dZ[0, 0] / zd * 100:+9.1f}%" if ok else "   infinite"
        fo = f"{first[0, 0] / zd * 100:+9.1f}%"
        print(f"   {ytip:5.1f} mm {k:3d}  | {dr}   {fo}   {np.max(lam.real):8.5f}  | {br:4d}    {', '.join(ev):20s} |"
              f" {(abs(za + dZa[0, 0]) - abs(za)) / abs(za) * 100:+7.1f}%  {np.max(np.abs(lama)):6.3f}")


def sec_dispatch():
    print("== dispatch: when do first-order (adjoint) and asymptotic prices hold? Three edits vs frequency.")
    print("   exact = Woodbury / Thevenin (checked by re-factorization: max err). r = largest |eigenvalue| of the")
    print("   edit's Woodbury matrix (removals) or |Z_th/z| (additions); for one branch exact = first/(1 - rho).")
    print("   Shown: exact change of |Z_AA| and the complex ratio first-order/exact of dZ_AA (1 at 0 deg is perfect).")
    print("   f (MHz)    |Z_AA| | 3 mm slit: r   d|Z|  first/exact  crack/exact | remove decap C3: r   d|Z|  first/exact"
          " | add decap: r   d|Z|  first/exact | max err")
    b = Board()

    def cr_(x):
        return f"{abs(x):5.2f}<{math.degrees(np.angle(x)):+5.0f}"
    for f in (0.0, 100e6, 300e6, 800e6, 900e6, 1.0e9, 1.2e9, 2.0e9, 2.8e9):
        band = Band("DC" if f == 0 else f"AC{f / 1e6:g}M", f, "VRM pad" if f == 0 else "GND plane")
        op = b.operator(band)
        E = np.stack([b.inj[p] for p in b.ports], 1)
        U = op.solve(E)
        Z0 = E.T @ U
        z0 = Z0[0, 0]

        def pct(dz):
            return (abs(z0 + dz) - abs(z0)) / abs(z0) * 100
        B = cut_line(b, op, 8.0, 8.0, 11.0)
        dZ, first, lam, ok = removal_quote(op, B, U)
        cr = crack_screen(op, B, U, zsq(f))
        err = np.max(np.abs(Z0 + dZ - brute_force_Z(op, B, E=E))) / np.max(np.abs(Z0))
        row = (f"   {f / 1e6:7.0f} {abs(z0) * 1e3:8.2f}m | {np.max(np.abs(lam)):5.3f} {pct(dZ[0, 0]):+6.1f}%  {cr_(first[0, 0] / dZ[0, 0])}"
               f"  {cr_(cr[0, 0] / dZ[0, 0])} |")
        if f > 0:
            Bc = np.nonzero(op.names == "C3")[0]
            dZc, fc, lc, _ = removal_quote(op, Bc, U)
            err = max(err, np.max(np.abs(Z0 + dZc - brute_force_Z(op, Bc, E=E))) / np.max(np.abs(Z0)))
            m = b.node[int(10 / 0.5) * b.nx + int(16 / 0.5)]
            zc = z_decap(f)
            a_ = np.zeros(op.n, complex); a_[m] = 1
            zth = a_ @ op.solve(a_)
            dZa = addition_quote(op, m, -1, zc, U)
            fa = -np.outer(a_ @ U, a_ @ U) / zc
            err = max(err, np.max(np.abs(Z0 + dZa - brute_force_Z(op, added=(m, -1, zc), E=E))) / np.max(np.abs(Z0)))
            row += (f" {np.max(np.abs(lc)):5.3f} {pct(dZc[0, 0]):+7.1f}%  {cr_(fc[0, 0] / dZc[0, 0])} |"
                    f" {abs(zth / zc):5.3f} {pct(dZa[0, 0]):+7.1f}%  {cr_(fa[0, 0] / dZa[0, 0])} |")
        else:
            row += f"{'':39s}|{'':32s}|"
        print(row + f" {err:.0e}")
    print("   one more decap at each of 150 sites (2 mm grid): sites that RAISE |Z_AA| (exact Thevenin);")
    print("   a self impedance is monotone only in a single-energy band, not near the anti-resonance:")
    for f in (300e6, 1e9):
        op = b.operator(Band("x", f, "GND plane"))
        E = np.stack([b.inj[p] for p in b.ports], 1)
        U = op.solve(E)
        z0 = (E.T @ U)[0, 0]
        sites = [b.node[j * b.nx + i] for j in range(2, b.ny, 4) for i in range(2, b.nx, 4) if b.node[j * b.nx + i] >= 0]
        up = sum(abs(z0 + addition_quote(op, m, -1, z_decap(f), U)[0, 0]) > abs(z0) for m in sites)
        print(f"     {f / 1e6:6.0f} MHz: {up}/{len(sites)}")


def sec_passport(core):
    print("== passport: what pieces are doing (exact counterfactual jobs), and the human/LLM queries")
    for pid in ("PWR.t07.05", "PWR.t04.05", "PWR.t13.02", "PWR.t00.09", "C3", "PAD.B"):
        print(f"  {pid}:")
        for band in core.ops:
            if core.pieces[pid].kind == "post" and band == "DC":
                continue
            pp = core.passport(pid, band)
            tr = ", ".join(f"{p} {v:.2f}" for p, v in pp.transit.items())
            print(f"    {band}: transit A/A [{tr}]; Woodbury lambda_max {pp.proximity:.3f}; events {pp.events or ['none']}")
        for line in core.why_here(pid):
            print(f"      why: {line}")
    print("  explain(): chi = |sum a|/sum|a| over tiles; attribution only when chi >= 0.5")
    for bud in core.budgets:
        chi, mode, rows = core.explain(bud.id)
        txt = "; ".join(f"{p} {v * 100:+.0f}%" if mode == "counterfactual" else f"{p} {abs(v) * 100:.0f}%" for p, v in rows)
        print(f"    {bud.id:14s} ({bud.cls:11s}) chi {chi:4.2f} -> {mode}: {txt}")
    b = core.board
    print("  what_if_cut(): extend the slot as a zero-width cut down to y = 6 mm")
    B = cut_line(b, core.ops["DC"], 14.5, 6.0, 12.0)
    for band in core.ops:
        q, lam, ev = core.quote_remove(band, B)
        for bid, (ex, fo) in q.items():
            bud = next(x for x in core.budgets if x.id == bid)
            print(f"    {bid:14s} exact {core.rel_change(bud, ex.value) * 100:+7.2f}%   first-order "
                  f"{core.rel_change(bud, fo.value) * 100:+7.2f}%   events {ev or ['none']}")
    print("  what_if_cut(): a NEW 6 mm edge notch from the bottom edge at x = 20 mm (stage 1 vs stage 2 quote)")
    B = cut_line(b, core.ops["DC"], 20.0, 0.0, 6.0)
    for band in core.ops:
        op = core.ops[band]
        q, lam, ev = core.quote_remove(band, B)
        cr = crack_screen(op, B, core.U[band], zsq(core.bands[band].f), edge=True)
        crl = crack_screen(op, B, core.U[band], zsq(core.bands[band].f), edge=True, ligament_x=6.0 / 20.0)
        for bid, (ex, fo) in q.items():
            bud = next(x for x in core.budgets if x.id == bid)
            q_, p_ = core.pidx[bud.victim], core.pidx[bud.source]
            print(f"    {bid:14s} exact {core.rel_change(bud, ex.value) * 100:+7.2f}% | first-order {core.rel_change(bud, fo.value) * 100:+7.2f}%"
                  f" | edge crack {core.rel_change(bud, cr[q_, p_]) * 100:+7.2f}%, x ligament {core.rel_change(bud, crl[q_, p_]) * 100:+7.2f}%")
    print("  where_add(): one 0.5 mm bridge across the slot (2 squares), exact Thevenin, DC")
    opd = core.ops["DC"]
    cands, ys = [], []
    for y in np.arange(12.25, 20.0, 0.5):
        j = int(y / 0.5)
        m, n = b.node[j * b.nx + 28], b.node[j * b.nx + 30]
        cands.append((m, n, 2 * RS)); ys.append(y)
    rows = core.where_add("DC", cands)
    for y, r in list(zip(ys, rows))[::3]:
        print(f"    bridge at y = {y:5.2f} mm: " + ", ".join(f"{k.split('@')[0]} {v * 100:+.1f}%" for k, v in r.items()))
    zb = brute_force_Z(opd, added=cands[0], E=core.E)
    dz = addition_quote(opd, *cands[0], core.U["DC"])
    print(f"    (check vs re-factorization: {np.max(np.abs(core.Z['DC'] + dz - zb)) / np.max(np.abs(zb)):.1e})")
    print("  where_add(): one more decap (0.7 nH, 100 nF) at 300 MHz on a 2 mm grid; best 3 and median")
    sites = [(b.node[j * b.nx + i], -1, z_decap(300e6)) for j in range(2, b.ny, 4) for i in range(2, b.nx, 4)
             if b.node[j * b.nx + i] >= 0]
    rows = core.where_add("AC300M", sites)
    za = np.array([r["Z_AA@AC300M"] for r in rows])
    zx = np.array([r["Z_BA@AC300M"] for r in rows])
    zs = np.array([r["Z_SA@AC300M"] for r in rows])
    for i in np.argsort(za)[:3]:
        c = b.cell_of[sites[i][0]]
        print(f"    site ({b.xc.ravel()[c]:4.1f}, {b.yc.ravel()[c]:4.1f}) mm: |Z_AA| {za[i] * 100:+.1f}%, |Z_BA| {zx[i] * 100:+.1f}%,"
              f" |Z_SA| {zs[i] * 100:+.1f}%")
    print(f"    median site: |Z_AA| {np.median(za) * 100:+.1f}%; sites that RAISE |Z_AA|: {np.sum(za > 0)}/{len(za)},"
          f" |Z_BA|: {np.sum(zx > 0)}/{len(zx)}, |Z_SA|: {np.sum(zs > 0)}/{len(zs)}")


def sec_floors(core):
    print("== floors and certified beliefs")
    b = core.board
    va, vr = b.pads["A"], b.pads["VRM"]
    xa, ya = b.xc.ravel()[b.cell_of[va]], b.yc.ravel()[b.cell_of[va]]
    xr, yr = b.xc.ravel()[b.cell_of[vr]], b.yc.ravel()[b.cell_of[vr]]
    w1 = np.min(np.hypot(xa[:, None] - xr[None, :], ya[:, None] - yr[None, :])) * 1e-3 - b.dx   # pad edges, conservative
    area = b.n * b.dx ** 2
    fl = beckmann_floor(w1, area)
    za = core.Z["DC"][0, 0]
    print(f"  Beckmann floor for R_A: {fl * 1e3:.4f} mOhm (CERTIFIED, continuum sheet of this area) vs model"
          f" {za * 1e3:.4f} mOhm (ALGEBRAIC, cell graph): tau-type ratio {za / fl:.1f}")
    print("  Prager-Synge bracket, 12 x 4 mm strip with a 1 x 1.5 mm edge notch (squares; ideal 3.000 without the notch):")
    for npm in (2, 4, 8):
        lo, hi, cg = bracket_notched_strip(npm)
        bel = Belief(0.5 * (lo + hi), "sq", Exactness.CERTIFIED, "continuum sheet, pixel geometry", (lo, hi), ("K-SHEET.phi", "K-SHEET.psi"))
        inside = "inside" if lo <= cg <= hi else "OUTSIDE"
        print(f"    {npm} cells/mm: {bel}; cell-graph value {cg:.4f} ({inside} the bracket)")


def green_block_quote(op, G, widx, B, U):
    """Exact removal quote from a cached dense Green block G = (Y^-1)[W, W] of a hot window W:
    no solve at all, only algebra on the edit's endpoint nodes (valid while the epoch is unchanged)."""
    loc = -np.ones(op.n, int)
    loc[widx] = np.arange(len(widx))
    ends = np.unique(np.r_[op.ea[B], op.eb[B][op.eb[B] >= 0]])
    pos = {e: i for i, e in enumerate(ends)}
    k = len(B)
    A = np.zeros((len(ends), k))
    A[[pos[e] for e in op.ea[B]], np.arange(k)] = 1
    for c, e in enumerate(op.eb[B]):
        if e >= 0:
            A[pos[e], c] = -1
    S = A.T @ G[np.ix_(loc[ends], loc[ends])] @ A
    V = A.T @ U[ends]
    return V.T @ np.linalg.solve(np.diag(1 / op.y[B]) - S, V)


def sec_bench():
    print("== bench: costs vs cells, one core (scipy SuperLU, MMD ordering); DC real / AC complex")
    print("   cells     band  factor     1 solve   rank-32 quote  Thevenin quote   JL 24")
    for s in (1, 2, 4, 8):
        b = Board(NX * s, NY * s, DX / s)
        for band in (Band("DC", 0.0, "VRM pad"), Band("AC300M", 300e6, "GND plane")):
            op = b.operator(band)
            E = np.stack([b.inj[p] for p in b.ports], 1)
            U = op.solve(E)
            t0 = time.perf_counter(); op.solve(E[:, 0]); t1 = time.perf_counter() - t0
            B = cut_line(b, op, 8.0, 3.0, 3.0 + 32 * DX / s * 1e3)[:32]
            t0 = time.perf_counter(); removal_quote(op, B, U); t32 = time.perf_counter() - t0
            t0 = time.perf_counter(); addition_quote(op, 5, 9, RS, U); tth = time.perf_counter() - t0
            if band.f == 0:
                t0 = time.perf_counter(); leverage_sketch(op, 24); tjl = time.perf_counter() - t0
                jl = f"{tjl:7.2f} s"
            else:
                jl = "   -"
            print(f"   {b.n:7d}  {band.name:6s} {op.t_factor:7.3f} s  {t1 * 1e3:8.2f} ms  {t32:7.3f} s"
                  f"      {tth * 1e3:8.2f} ms     {jl}")
    print("   hot window: cache the dense Green block of a 40 x 40-cell window once per epoch, then quote")
    print("   every edit inside it with k x k algebra (38k-cell board, DC; the rank-32 cut lies in the window)")
    b = Board(NX * 4, NY * 4, DX / 4)
    op = b.operator(Band("DC", 0.0, "VRM pad"))
    E = np.stack([b.inj[p] for p in b.ports], 1)
    U = op.solve(E)
    B = cut_line(b, op, 8.0, 3.0, 7.0)[:32]
    cj, ci = np.divmod(b.cell_of, b.nx)
    i0, j0 = int(7.0 / (DX * 250)), int(2.5 / (DX * 250))
    widx = np.nonzero((ci >= i0) & (ci < i0 + 40) & (cj >= j0) & (cj < j0 + 40))[0]
    t0 = time.perf_counter()
    G = np.zeros((len(widx), len(widx)))
    for c0 in range(0, len(widx), 200):
        c = np.arange(c0, min(len(widx), c0 + 200))
        Ew = np.zeros((op.n, len(c)))
        Ew[widx[c], np.arange(len(c))] = 1
        G[:, c] = op.solve(Ew)[widx]
    tg = time.perf_counter() - t0
    t0 = time.perf_counter()
    for _ in range(1000):
        dz = green_block_quote(op, G, widx, B, U)
    tq = (time.perf_counter() - t0) / 1000
    t0 = time.perf_counter()
    dz_ref = removal_quote(op, B, U)[0]
    td = time.perf_counter() - t0
    print(f"   window {len(widx)} nodes: Green block {tg:.1f} s once per epoch; rank-32 quote {tq * 1e3:.2f} ms"
          f" vs {td:.3f} s direct; agreement {np.max(np.abs(dz - dz_ref)) / np.max(np.abs(dz_ref)):.1e}")


def main(which):
    t0 = time.perf_counter()
    core = None
    if set(which) & {"exact", "events", "passport", "floors", "all"}:
        core = make_core()
        print(f"[core: {core.board.n} cells, bands {list(core.ops)}, {len(core.pieces)} pieces,"
              f" Z_AA(DC) {core.Z['DC'][0, 0] * 1e3:.4f} mOhm, Z_BA(DC) {core.Z['DC'][1, 0] * 1e3:.4f} mOhm,"
              f" |Z_AA(300 MHz)| {abs(core.Z['AC300M'][0, 0]) * 1e3:.3f} mOhm]")
    if "exact" in which or "all" in which:
        sec_exact(core)
    if "events" in which or "all" in which:
        sec_events(core)
    if "dispatch" in which or "all" in which:
        sec_dispatch()
    if "passport" in which or "all" in which:
        sec_passport(core)
    if "floors" in which or "all" in which:
        sec_floors(core)
    if "bench" in which:
        sec_bench()
    print(f"[{time.perf_counter() - t0:.1f} s]")


if __name__ == "__main__":
    main(sys.argv[1:] or ["all"])
