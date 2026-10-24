# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact physics of routed copper, and the fidelity switch `--physics-fidelity fast|exact|multi`.

Where copper exists (the critical router's module stage, the post-route recheck, the joint
loop's acceptance), loops are evaluated with the research's reference solver instead of the
closed forms (docs/topics/physics/exact-physics-in-kae.md; the choice of where:
docs/topics/physics/exact-physics-options.md section 5, design (e) then (b)).

**Loops (PEEC).** `loop_value(lp)` evaluates a `kae.route.critical_physics.Loop` (the network
the module stage and the recheck build: strips at a height over the reference plane, vertical
pieces, parallel alternatives tied by Kirchhoff's current law) by multi-filament PEEC over a
perfectly conducting image plane, in the inductive limit (pw_peec, ex_exact.peec_solve):

- a strip of width w at height h is nw filaments across its width (nw as ex_exact._nw: the
  filament width below about h/3, at most 60 and not thinner than 1.2 t), thickness t, at
  h + t/2; a vertical piece of radius r is a ring of 6 filaments (plating 25 um);
- partial inductances by Neumann's integral: parallel filaments in Grover's closed form
  (self terms at the filament's GMD 0.2235 (w + t)), perpendicular ones do not couple,
  oblique ones (any-angle routes) by Gauss-Legendre quadrature over one filament of the
  analytic integral over the other, graded geometrically toward their closest points (log
  singularities of touching or crossing filaments); images: mirrored end points, current
  reversed;
- each piece carries its element's current, free to crowd across its filaments; the loop's
  inductance is the minimum magnetic energy under the pieces' sums and the Loop's KCL rows
  (the inductive limit), with the Loop's active set keeping alternative currents >= 0.

On axis-aligned copper this is pw_peec to rounding (tests: 1e-9). Blocks of the partial-
inductance matrix are cached per pair of pieces, so a search that changes only vias re-uses
its hops' blocks. A loop mixing strips over a plane and strips without one gives the latter
a stand-in height (twice the highest strip, at least 3.2 mm), as Loop does without the mixed
fastloop.

**Thermal (finite volume).** `ThermalFV(terms)` is ex_exact's 2.5-D operator over the
board's box (every copper layer, the zones' coverage, FR-4, h per side), factored once; a
source's 1 W field is solved once per pose and cached, so a victim's move is a lookup.

**Fidelity.** `configure(mode, k)` sets the process-wide fidelity (CLI `--physics-fidelity`,
`--physics-k`); `scope(mode, k)` sets it for a block.
- fast (default): nothing changes.
- exact: every Loop the module stage and the recheck evaluate is PEEC (`loop_hook`, called
  first thing in Loop.value).
- multi: Loop stays closed-form for the search; `pick(cands, rescore)` re-scores the fast
  top K of a decision with PEEC and keeps the best; the routed physics of finished boards
  (`final_fidelity`, on critical_recheck.board_physics) is PEEC.
`stats()` counts decisions, changed choices and PEEC calls.
"""
from __future__ import annotations

import contextlib
import functools
import math
import time

import numpy as np

MU = 0.1            # mu0 / 4 pi, nH per mm
T_CU = 0.035        # mm
T_PLATE = 0.025     # mm via plating of the PEEC ring (pw_peec.Net.via default)
RVIA = 0.15         # mm
N_RING = 6
GMD = 0.2235
INF = math.inf
FIDELITIES = ("fast", "exact", "multi")


# ============================================================================ fidelity
class _State:
    def __init__(self):
        self.mode = "fast"
        self.k = 4
        self.depth = 0
        self.stats = _new_stats()


def _new_stats():
    return dict(decisions=0, changed=0, exact_calls=0, exact_s=0.0, failures=0, rank=[], gain=[], what={})


STATE = _State()


def configure(mode="fast", k=4):
    """Set the process-wide fidelity (fast | exact | multi) and the top-K of `multi`."""
    if mode not in FIDELITIES:
        raise ValueError(f"physics fidelity {mode!r} not in {FIDELITIES}")
    STATE.mode = mode
    STATE.k = max(1, int(k or 4))
    return STATE


@contextlib.contextmanager
def scope(mode, k=None):
    """The fidelity `mode` (and top-K `k`) for the duration of a block."""
    old = (STATE.mode, STATE.k)
    configure(mode, STATE.k if k is None else k)
    try:
        yield STATE
    finally:
        STATE.mode, STATE.k = old


@contextlib.contextmanager
def exact_now():
    """Loops evaluate by PEEC inside this block, whatever the mode (measurements, re-scoring)."""
    STATE.depth += 1
    try:
        yield
    finally:
        STATE.depth -= 1


def wants_exact():
    return STATE.mode == "exact" or STATE.depth > 0


def final_fidelity(fn):
    """Decorator: in exact and multi modes `fn` runs with loops evaluated by PEEC (the routed
    physics of a finished board is a final value, not a search); fast mode is untouched."""
    @functools.wraps(fn)
    def run(*a, **kw):
        if STATE.mode == "fast":
            return fn(*a, **kw)
        with exact_now():
            return fn(*a, **kw)
    return run


def stats(reset=False):
    """Counters since the last reset: decisions (multi picks), changed (PEEC kept another
    candidate than the fast best), exact_calls / exact_s (PEEC loop solves), failures (PEEC
    fell back to the closed form), rank (fast rank of each pick), gain (relative PEEC gain of
    the pick over the fast best), what ({decision kind: [decisions, changed]})."""
    s = dict(STATE.stats)
    s["rank"] = list(s["rank"])
    s["gain"] = list(s["gain"])
    s["what"] = {k: list(v) for k, v in s["what"].items()}
    if reset:
        STATE.stats = _new_stats()
    return s


def summary():
    """The fidelity and its counters as a report dict (JSON-able)."""
    s = STATE.stats
    return dict(mode=STATE.mode, k=STATE.k, decisions=s["decisions"], changed=s["changed"],
                exact_calls=s["exact_calls"], exact_s=round(s["exact_s"], 3), failures=s["failures"],
                what={k: list(v) for k, v in s["what"].items()},
                median_gain=round(float(np.median(s["gain"])), 5) if s["gain"] else None)


def add_cli_args(parser):
    """--physics-fidelity and --physics-k on an argparse parser (then configure(a.physics_fidelity,
    a.physics_k))."""
    parser.add_argument("--physics-fidelity", default="fast", choices=FIDELITIES,
                        help="routed-loop physics: fast closed forms (default), exact PEEC everywhere, or multi "
                             "(closed forms to search, PEEC on each decision's fast top K and on finished boards)")
    parser.add_argument("--physics-k", type=int, default=4, help="top K that multi re-scores by PEEC (default 4)")
    return parser


def loop_hook(lp, shares=False):
    """What Loop.value returns when loops are exact now (None otherwise: the closed form runs).
    A PEEC failure (degenerate copper) falls back to the closed form and is counted."""
    if not wants_exact():
        return None
    t0 = time.perf_counter()
    try:
        r = loop_value(lp, shares=shares)
    except (np.linalg.LinAlgError, ValueError, FloatingPointError):
        STATE.stats["failures"] += 1
        return None
    finally:
        STATE.stats["exact_calls"] += 1
        STATE.stats["exact_s"] += time.perf_counter() - t0
    v = r[0] if shares else r
    if not (math.isfinite(v) and v > 0):
        STATE.stats["failures"] += 1
        return None
    return r


def pick(cands, rescore, k=None, what="choice"):
    """The chosen candidate of a decision. cands: [(fast value, ...)] in proposal order;
    rescore(c) -> the candidate's value (it is called inside exact_now()). fast and exact: the
    first of the lowest values (as a strict-< scan); multi: the fast top K re-scored by PEEC,
    the lowest kept (ties: the better fast rank). None when there is no candidate."""
    cands = [c for c in cands if c is not None and c[0] is not None and math.isfinite(c[0])]
    if not cands:
        return None
    order = sorted(range(len(cands)), key=lambda i: cands[i][0])
    if STATE.mode != "multi" or len(cands) == 1 or STATE.depth > 0:
        return cands[order[0]]
    K = max(1, int(k or STATE.k))
    top = [cands[i] for i in order[:K]]
    vals = []
    with exact_now():
        for c in top:
            try:
                v = rescore(c)
            except Exception:  # noqa: BLE001 - a failed re-score leaves that candidate out
                v = None
            vals.append(v if v is not None and math.isfinite(v) and v > 0 else None)
    ok = [(v, j) for j, v in enumerate(vals) if v is not None]
    st = STATE.stats
    st["decisions"] += 1
    w = st["what"].setdefault(what, [0, 0])
    w[0] += 1
    if not ok:
        st["rank"].append(0)
        return top[0]
    v, j = min(ok)
    st["rank"].append(j)
    if j != 0:
        st["changed"] += 1
        w[1] += 1
    if vals[0] is not None:
        st["gain"].append((vals[0] - v) / vals[0])
    return top[j]


# ============================================================================ filaments
class Piece:
    """Parallel filaments that carry one current together: start points A (k, 3), end points
    B (k, 3) in the current's direction, GMDs g (k,); all of one length and direction."""

    __slots__ = ("A", "B", "g", "key", "u", "l", "w")

    def __init__(self, A, B, g, key, w=0.0):
        self.A = np.asarray(A, float).reshape(-1, 3)
        self.B = np.asarray(B, float).reshape(-1, 3)
        self.g = np.asarray(g, float).reshape(-1)
        d = self.B[0] - self.A[0]
        self.l = float(np.linalg.norm(d))
        self.u = d / self.l if self.l > 0 else d
        self.key = key
        self.w = float(w)

    def __len__(self):
        return len(self.g)


def _r(x, n=7):
    return round(float(x), n)


def bar(p0, axis, length, w, t, nw=1, nt=1, reverse=False):
    """pw_peec.Net.bar's filaments (mm): an axis-aligned bar from corner p0 along `axis`
    (0, 1, 2) for `length`, cross-section w along the first other axis and t along the second;
    reverse: the current runs toward -axis."""
    tr = [k for k in range(3) if k != axis]
    A, B, g = [], [], []
    for i in range(nw):
        for j in range(nt):
            c = [0.0, 0.0, 0.0]
            c[tr[0]] = p0[tr[0]] + (i + 0.5) * w / nw
            c[tr[1]] = p0[tr[1]] + (j + 0.5) * t / nt
            a = list(c)
            b = list(c)
            a[axis] = p0[axis]
            b[axis] = p0[axis] + length
            if reverse:
                a, b = b, a
            A.append(a)
            B.append(b)
            g.append(GMD * (w / nw + t / nt))
    key = ("bar", axis, *(_r(x) for x in p0), _r(length), _r(w), _r(t), nw, nt, reverse)
    return Piece(A, B, g, key, w)


def strip(p, q, w, z, t=T_CU, nw=1, nt=1):
    """A horizontal strip from p to q (x, y; mm) of width w with its bottom face at height z:
    nw x nt filaments, as pw_peec's bar for axis-aligned strips, at any angle otherwise."""
    p = (float(p[0]), float(p[1]))
    q = (float(q[0]), float(q[1]))
    L = math.hypot(q[0] - p[0], q[1] - p[1])
    ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
    nx, ny = -uy, ux
    A, B, g = [], [], []
    for i in range(nw):
        o = -0.5 * w + (i + 0.5) * w / nw
        for j in range(nt):
            zz = z + (j + 0.5) * t / nt
            A.append((p[0] + o * nx, p[1] + o * ny, zz))
            B.append((q[0] + o * nx, q[1] + o * ny, zz))
            g.append(GMD * (w / nw + t / nt))
    key = ("strip", _r(p[0]), _r(p[1]), _r(q[0]), _r(q[1]), _r(w), _r(z), _r(t), nw, nt)
    return Piece(A, B, g, key, w)


def ring(x, y, z0, z1, r, n=N_RING, tp=T_PLATE):
    """A via barrel (or a round vertical conductor) from height z0 to z1 as n filaments on a
    ring of radius r (pw_peec.Net.via)."""
    arc = 2 * math.pi * r / n
    A, B, g = [], [], []
    for k in range(n):
        th = 2 * math.pi * (k + 0.5) / n
        cx, cy = x + r * math.cos(th), y + r * math.sin(th)
        A.append((cx, cy, z0))
        B.append((cx, cy, z1))
        g.append(GMD * (arc + tp))
    key = ("ring", _r(x), _r(y), _r(z0), _r(z1), _r(r), n, _r(tp))
    return Piece(A, B, g, key, 2 * r)


def nw_strip(w, z, t=T_CU):
    """Filaments across a strip (ex_exact._nw on pw_peec._nw): filament width below about
    z/3 near a plane (8 without one), at most 60, none thinner than 1.2 t."""
    MM = 1e-3
    pw_nw = int(min(160, max(8, math.ceil(3 * (w * MM) / (z * MM))))) if z > 0 else 8
    return max(1, min(pw_nw, 60, int(w / (1.2 * t))))


# ----------------------------------------------------------------------------- mutuals
def _G(z, d):
    return z * np.arcsinh(z / d) - np.sqrt(z * z + d * d)


def _gl(n):
    x, w = np.polynomial.legendre.leggauss(n)
    return 0.5 * (x + 1.0), 0.5 * w


_GL8 = _gl(8)


def _graded(m=14, r=0.25, n=5):
    """A rule on [0, 1] graded toward 0: subintervals [0, r^m], [r^m, r^(m-1)], ..., [r, 1],
    n Gauss points each (the integral of log x on [0, 1] to 2e-6 at m = 14)."""
    x, w = _gl(n)
    edges = [0.0] + [r ** k for k in range(m, -1, -1)]
    X, W = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        X.append(a + (b - a) * x)
        W.append((b - a) * w)
    return np.concatenate(X), np.concatenate(W)


_R_GRADE = 0.25
_GRADED = [None] + [_graded(m) for m in range(1, 15)]


def _closest_s(PA, u, lP, QA, v, lQ):
    """Parameter s in [0, lP] on each filament P_i of the point closest to filament Q_j
    (segments; Ericson's clamped closest points), and that distance: arrays (kP, kQ)."""
    r = PA[:, None, :] - QA[None, :, :]                  # (kP, kQ, 3)
    b = float(u @ v)
    c = r @ u                                            # (kP, kQ)
    f = r @ v
    den = 1.0 - b * b
    s = np.clip((b * f - c) / den, 0.0, lP) if den > 1e-12 else np.zeros_like(c)
    t = np.clip(b * s + f, 0.0, lQ)
    s = np.clip(b * t - c, 0.0, lP)
    d = r + s[..., None] * u - t[..., None] * v
    return s, np.sqrt((d * d).sum(-1))


def _inner(Pts, QA, v, lQ):
    """Integral over filament Q_j of dt / |p - q(t)| at points p: Pts (kP, kQ, n, 3)."""
    r = Pts - QA[None, :, None, :]
    tau = r @ v
    rho2 = (r * r).sum(-1) - tau * tau
    rho = np.sqrt(np.maximum(rho2, 1e-24))
    return np.arcsinh((lQ - tau) / rho) + np.arcsinh(tau / rho)


def mutual(P, QA, QB, gmd_rows=None):
    """Neumann mutual (nH) of every filament of piece P with the filaments QA -> QB (all
    parallel to one another and of one length): (kP, kQ)."""
    PA = P.A
    lP = P.l
    u = P.u
    dq = QB[0] - QA[0]
    lQ = float(np.linalg.norm(dq))
    if lP < 1e-12 or lQ < 1e-12:
        return np.zeros((len(PA), len(QA)))
    v = dq / lQ
    c = float(u @ v)
    if abs(c) < 1e-9:
        return np.zeros((len(PA), len(QA)))
    if abs(abs(c) - 1.0) < 1e-9:
        # parallel: Grover on the oriented projections of Q's ends onto P's axis
        ra = QA[None, :, :] - PA[:, None, :]
        b1 = ra @ u
        b2 = (QB[None, :, :] - PA[:, None, :]) @ u
        perp = ra - b1[..., None] * u
        d = np.sqrt((perp * perp).sum(-1))
        g = P.g if gmd_rows is None else gmd_rows
        d = np.where(d < 1e-12, g[:, None], d)
        return MU * (_G(lP - b1, d) - _G(-b1, d) - _G(lP - b2, d) + _G(-b2, d))
    # oblique: quadrature along P of the analytic integral along Q
    s_star, dist = _closest_s(PA, u, lP, QA, v, lQ)
    if float(dist.min()) > lP:
        x, w = _GL8
        S = lP * x[None, None, :] * np.ones(dist.shape)[..., None]
        Wt = lP * w[None, None, :] * np.ones(dist.shape)[..., None]
    else:
        # geometric levels down to the closest approach (14 for touching or crossing filaments)
        dmin = max(float(dist.min()), 1e-12)
        m = int(np.clip(math.ceil(math.log(dmin / lP) / math.log(_R_GRADE)) + 2, 1, 14))
        x, w = _GRADED[m]
        left = s_star[..., None]
        right = (lP - s_star)[..., None]
        S = np.concatenate([s_star[..., None] - left * x, s_star[..., None] + right * x], -1)
        Wt = np.concatenate([left * w, right * w], -1)
    Pts = PA[:, None, None, :] + S[..., None] * u
    F = _inner(Pts, QA, v, lQ)
    return MU * c * (F * Wt).sum(-1)


_MIRROR = np.array([1.0, 1.0, -1.0])
_BLOCKS = {}
_BLOCK_CAP = 6000


def _block(P, Q, plane):
    key = (P.key, Q.key, plane)
    blk = _BLOCKS.get(key)
    if blk is not None:
        return blk
    blk = mutual(P, Q.A, Q.B)
    if plane:
        # the image of Q: mirrored end points, current reversed
        blk = blk - mutual(P, Q.A * _MIRROR, Q.B * _MIRROR)
    if len(_BLOCKS) > _BLOCK_CAP:
        _BLOCKS.clear()
    _BLOCKS[key] = blk
    return blk


def clear_cache():
    _BLOCKS.clear()


def lmatrix(pieces, plane=True):
    """Partial-inductance matrix (nH) of all filaments of `pieces`, with the image plane z=0."""
    sizes = [len(p) for p in pieces]
    off = np.concatenate([[0], np.cumsum(sizes)]).astype(int)
    n = int(off[-1])
    L = np.zeros((n, n))
    for i, P in enumerate(pieces):
        for j in range(i, len(pieces)):
            Q = pieces[j]
            blk = _block(P, Q, plane)
            L[off[i]:off[i + 1], off[j]:off[j + 1]] = blk
            if j != i:
                L[off[j]:off[j + 1], off[i]:off[i + 1]] = blk.T
    return L, off


def piece_matrix(pieces, plane=True):
    """Piece-level partial inductances (nH): Z = (B L^-1 B')^-1 for unit piece currents, each
    free to distribute over its filaments (the inductive limit). Returns (Z, info)."""
    import scipy.linalg as sla
    L, off = lmatrix(pieces, plane)
    n = L.shape[0]
    B = np.zeros((len(pieces), n))
    for i in range(len(pieces)):
        B[i, off[i]:off[i + 1]] = 1.0
    clipped = False
    try:
        cho = sla.cho_factor(L, lower=False, check_finite=False)
        X = sla.cho_solve(cho, B.T, check_finite=False)
    except np.linalg.LinAlgError:
        # overlapping filaments (a route jogging by less than its own width): clip the
        # spectrum, as ex_exact with PEEC_CLIP
        clipped = True
        ev, V = np.linalg.eigh(L)
        ev = np.maximum(ev, 1e-6 * ev.max())
        X = V @ ((V.T @ B.T) / ev[:, None])
    Y = B @ X
    Z = np.linalg.inv(Y)
    return 0.5 * (Z + Z.T), dict(filaments=n, pieces=len(pieces), clipped=clipped)


# ============================================================================ networks
def min_energy(P, names, cons):
    """Element currents x minimizing x'Px under 'A' = 1 and the KCL rows `cons`
    ([({element: coeff}, rhs)]), alternatives kept >= 0 by an active set (as Loop.value).
    Returns (energy, x)."""
    n = len(names)
    ev, U = np.linalg.eigh(P)
    floor = 1e-9 * max(float(ev.max()), 1e-12)
    if ev.min() < floor:
        P = (U * np.maximum(ev, floor)) @ U.T
    rows, rhs = [], []
    if "A" in names:
        r = np.zeros(n)
        r[names.index("A")] = 1.0
        rows.append(r)
        rhs.append(1.0)
    for co, v in cons:
        r = np.zeros(n)
        ok = False
        for k, c in co.items():
            if k in names:
                r[names.index(k)] = c
                ok = True
        if ok:
            rows.append(r)
            rhs.append(v)
    pinned = []
    x = np.zeros(n)
    for _ in range(n + 1):
        R = rows + [np.eye(n)[k] for k in pinned]
        C = np.array(R)
        m = C.shape[0]
        K = np.zeros((n + m, n + m))
        K[:n, :n] = 2.0 * P
        K[:n, n:] = C.T
        K[n:, :n] = C
        b = np.zeros(n + m)
        b[n:] = rhs + [0.0] * len(pinned)
        x = np.linalg.lstsq(K, b, rcond=None)[0][:n]
        neg = [k for k in np.argsort(x) if x[k] < -1e-9 and names[k] != "A" and k not in pinned
               and all(sum(1 for q in np.nonzero(r)[0] if q != k and q not in pinned) > 0
                       for r in rows if r[k] != 0)]
        if not neg:
            break
        pinned.append(int(neg[0]))
    return float(x @ P @ x), x


def network_value(elements, cons=(), plane=True, shares=False, detail=False):
    """Inductance (nH) of a network of elements {name: [Piece]} carrying currents x_e: 'A' (the
    series part) 1, the others tied by `cons`; without cons every element is in series.
    shares: also {element: current}; detail: also an info dict."""
    names = [k for k, ps in elements.items() if ps]
    t0 = time.perf_counter()
    if not cons or names == ["A"]:
        pieces = [p for k in names for p in elements[k]]
        Z, info = piece_matrix(pieces, plane)
        val = float(Z.sum())
        x = {k: 1.0 for k in names}
    else:
        pieces, owner = [], []
        for e, k in enumerate(names):
            for p in elements[k]:
                pieces.append(p)
                owner.append(e)
        Z, info = piece_matrix(pieces, plane)
        S = np.zeros((len(pieces), len(names)))
        S[np.arange(len(pieces)), owner] = 1.0
        val, xv = min_energy(S.T @ Z @ S, names, list(cons))
        x = {k: float(v) for k, v in zip(names, xv)}
    info["seconds"] = time.perf_counter() - t0
    out = (val,)
    if shares:
        out += (x,)
    if detail:
        out += (info,)
    return out[0] if len(out) == 1 else out


def loop_network(lp, t=T_CU):
    """({element: [Piece]}, cons, plane) of a critical_physics.Loop (see the module docstring)."""
    el = lp.el
    fin = [h[5] for H, _ in el.values() for h in H if h[5] != INF]
    has_v = any(V for _, V in el.values())
    plane = bool(fin) or has_v
    hf = max(3.2, 2.0 * max(fin)) if fin else 3.2
    out = {}
    for name, (H, V) in el.items():
        ps = []
        for (x0, y0, x1, y1, w, h) in H:
            if math.hypot(x1 - x0, y1 - y0) < 1e-9:
                continue
            z = (hf if h == INF else h) if plane else 0.0
            nw = nw_strip(w, z if plane else 1.0, t)
            ps.append(strip((x0, y0), (x1, y1), w, z, t, nw=nw))
        for (x, y, z0, z1, r) in V:
            if abs(z1 - z0) < 1e-9:
                continue
            ps.append(ring(x, y, z0, z1, r))
        out[name] = ps
    return out, list(lp.cons), plane


def loop_value(lp, shares=False, detail=False, t=T_CU):
    """PEEC inductance (nH) of a critical_physics.Loop (same pieces, KCL and active set)."""
    els, cons, plane = loop_network(lp, t)
    return network_value(els, cons, plane, shares=shares, detail=detail)


def surge_path(pts, w, h, r=RVIA, t=T_CU):
    """PEEC L (nH) of a surge path: the routed strip pts [(x, y), ...] of width w at height h
    over the plane, then the protector's via down to the plane at the last point (the place
    terms' and the module stage's ESD model; the connector end is the source)."""
    ps = []
    for a, b in zip(pts[:-1], pts[1:]):
        if math.dist(a, b) > 1e-9:
            ps.append(strip(a, b, w, h, t, nw=nw_strip(w, h, t)))
    x, y = pts[-1]
    ps.append(ring(x, y, h, 0.0, r))
    return network_value({"A": ps}, (), True)


# ============================================================================ routed modules
def chain_module_exact(ctx, m):
    """PEEC surge path of a routed protection-chain module (critical_modules._chain_value's
    geometry: the routed hops from the connector pin to the protector at the plane height of
    their layer, then the protector's via). None when the chain has no routed hop."""
    T = m.spec.get("_T") or []
    prot = set(m.spec.get("protection") or [])
    pts, w, h = [], 0.25, INF
    for k in range(len(T) - 1):
        ta, tb = T[k], T[k + 1]
        rt = m.hops.get(f"hop{k}")
        if rt is not None and rt.segs:
            w = rt.width
            l = rt.segs[0][0]
            for _, a, b in rt.segs:
                if not pts or math.dist(pts[-1], a) > 1e-9:
                    pts.append(tuple(a))
                pts.append(tuple(b))
        else:
            l = ctx.side_layer(tb.fp)
            if not pts:
                pts.append((ta.x, ta.y))
            pts.append((tb.x, tb.y))
        h, _, _ = ctx.plane(l, ta.x, ta.y, gnd=False)
        if tb.fp in prot:
            break
    if len(pts) < 2:
        return None
    hh = h if h != INF else ctx.sp.thickness
    return surge_path(pts, w, hh)


def module_values(ctx, m):
    """(fast value, exact value) of a routed module on its committed copper (cells, power
    paths and decaps through the module stage's quote; chains by surge_path), either None."""
    from kae.route.critical_modules import quote
    with scope("fast"):
        vf = quote(ctx, m, store=False)
    if m.kind == "chain":
        try:
            ve = chain_module_exact(ctx, m)
        except (np.linalg.LinAlgError, ValueError):
            ve = None
        return vf, ve
    if m.kind not in ("cell", "path", "decap"):
        return vf, None
    with exact_now():
        ve = quote(ctx, m, store=False)
    return vf, ve


def routed_utilizations(board, brief=None, terms=None, stage=None, fills="kicad", window=None, rise=0.15):
    """The joint loop's routed physics with exact loops: {module id: u} as Scorecard.modules
    takes it (critical_recheck.recheck's u_routed when `stage` is given, else board_physics'
    u of every module), evaluated with PEEC whatever the mode."""
    from kae.route import critical_recheck as R
    with exact_now():
        if stage:
            rc = R.recheck(board, brief, stage, rise=rise, fills=fills, terms=terms, window=window)
            return {k: (v or {}).get("u_routed") for k, v in (rc.get("modules") or {}).items()}
        ph = R.board_physics(board, brief=brief, fills=fills, terms=terms, window=window, rails=False)
    return {k: v.get("u") for k, v in ph.items() if not k.startswith("_") and isinstance(v, dict)}


# ============================================================================ thermal (FV)
K_CU = 390.0        # W/mK
K_XY = 0.8          # FR-4 in-plane
K_Z = 0.3           # FR-4 through-plane


def fv_operator(t_cu, gaps, cov, via, dx, h_top=10.0, h_bot=10.0):
    """Conductance matrix (W/K, scipy CSR) of the 2.5-D board: layers of nodes (nl, nx, ny) on a
    grid of pitch dx (m); t_cu (m) per layer, gaps (m) between layers, cov (nl, nx, ny) copper
    mask, via (nx, ny) barrel k*A (W m/K) between all layers; h per outer side (W/m^2K).
    tm_board_thermal_fv.Board.solve's operator."""
    import scipy.sparse as sp
    nl, nx, ny = cov.shape
    n = nl * nx * ny
    idx = np.arange(n).reshape(nl, nx, ny)
    rows, cols, vals = [], [], []
    diag = np.zeros(n)

    def couple(a, c, g):
        a, c, g = a.ravel(), c.ravel(), np.broadcast_to(g, a.shape).ravel()
        rows.extend([a, c])
        cols.extend([c, a])
        vals.extend([-g, -g])
        np.add.at(diag, a, g)
        np.add.at(diag, c, g)
    for l in range(nl):
        share = 0.0
        if l > 0:
            share += gaps[l - 1] / 2
        if l < nl - 1:
            share += gaps[l] / 2
        gs = K_XY * share + K_CU * t_cu[l] * cov[l]
        gx = 2 * gs[:-1, :] * gs[1:, :] / (gs[:-1, :] + gs[1:, :])
        gy = 2 * gs[:, :-1] * gs[:, 1:] / (gs[:, :-1] + gs[:, 1:])
        couple(idx[l, :-1, :], idx[l, 1:, :], gx)
        couple(idx[l, :, :-1], idx[l, :, 1:], gy)
    for l in range(nl - 1):
        g = K_Z * dx * dx / gaps[l] + via / gaps[l]
        couple(idx[l], idx[l + 1], g)
    diag[idx[0].ravel()] += h_top * dx * dx
    diag[idx[-1].ravel()] += h_bot * dx * dx
    rows.append(np.arange(n))
    cols.append(np.arange(n))
    vals.append(diag)
    return sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)).tocsr()


class ThermalFV:
    """Finite-volume rise (K) at the place terms' thermal targets (sources: mean over their
    courtyard box; victims: their centre) over the board's box with each layer's zone coverage
    as placed; factored once, one solve per distinct source pose (cached: superposition).
    inject: 'surface' (heat into the part's outer layer) or 'stack' (every layer under it).
    ex_exact.FVThermal."""

    def __init__(self, terms, dx=0.5, h_conv=10.0, max_nodes=400_000, inject="surface"):
        import scipy.sparse.linalg as spla
        self.T = terms
        self.inject = inject
        bv = terms.bv
        th = terms.thermal
        x0, y0, x1, y1 = bv.bbox
        nl = len(bv.copper)
        while ((x1 - x0) / dx) * ((y1 - y0) / dx) * nl > max_nodes:
            dx *= 1.25
        self.dx = dx
        self.x0, self.y0 = x0, y0
        self.nx = max(2, int(round((x1 - x0) / dx)))
        self.ny = max(2, int(round((y1 - y0) / dx)))
        MM = 1e-3
        t_cu = [bv.tcu.get(ly, T_CU) * MM for ly in bv.copper]
        gaps = [g * MM for g in (bv.gaps if hasattr(bv, "gaps") and len(bv.gaps) == nl - 1 else
                                 [bv.thickness / max(1, nl - 1)] * (nl - 1))]
        cov = np.zeros((nl, self.nx, self.ny), bool)
        X = x0 + (np.arange(self.nx) + 0.5) * dx
        Y = y0 + (np.arange(self.ny) + 0.5) * dx
        cx0, cy0, cres, cnx, cny = bv.cover_grid
        ii = np.clip(np.round((X - cx0) / cres).astype(int), 0, cnx - 1)
        jj = np.clip(np.round((Y - cy0) / cres).astype(int), 0, cny - 1)
        for li, ly in enumerate(bv.copper):
            C = bv.cover.get(ly)
            if C is not None:
                cov[li] = (C[np.ix_(jj, ii)] >= 0).T
        self.nl = nl
        t0 = time.perf_counter()
        A = fv_operator(t_cu, gaps, cov, np.zeros((self.nx, self.ny)), dx * MM, h_conv, h_conv)
        self.lu = spla.splu(A.tocsc(), permc_spec="MMD_AT_PLUS_A")
        self.t_factor = time.perf_counter() - t0
        self.nodes = A.shape[0]
        self.cache = {}
        self.solves = 0
        self.t_solve = 0.0
        self.src = list(th.src)
        self.P = np.array(th.P, float)
        self.targets = list(th.targets)
        self.Lx, self.Ly = (x1 - x0), (y1 - y0)
        self.hsum = 2 * h_conv

    def _box(self, i):
        st, bv = self.T.st, self.T.bv
        x0, y0, x1, y1 = bv.courtyard_obb(i, st.X[i], st.Y[i], st.R[i], st.G[i])
        i0 = int(np.clip((x0 - self.x0) / self.dx, 0, self.nx - 1))
        i1 = int(np.clip((x1 - self.x0) / self.dx, 0, self.nx - 1))
        j0 = int(np.clip((y0 - self.y0) / self.dx, 0, self.ny - 1))
        j1 = int(np.clip((y1 - self.y0) / self.dx, 0, self.ny - 1))
        layer = 0 if st.G[i] > 0 else self.nl - 1
        return layer, i0, i1, j0, j1

    def field(self, k):
        """Temperature field (nl, nx, ny) of 1 W from source k at its current pose (cached)."""
        key = (k, self._box(self.src[k]))
        f = self.cache.get(key)
        if f is None:
            layer, i0, i1, j0, j1 = key[1]
            p = np.zeros((self.nl, self.nx, self.ny))
            if self.inject == "stack":
                p[:, i0:i1 + 1, j0:j1 + 1] = 1.0 / ((i1 - i0 + 1) * (j1 - j0 + 1) * self.nl)
            else:
                p[layer, i0:i1 + 1, j0:j1 + 1] = 1.0 / ((i1 - i0 + 1) * (j1 - j0 + 1))
            t0 = time.perf_counter()
            f = self.lu.solve(p.ravel()).reshape(self.nl, self.nx, self.ny)
            self.t_solve += time.perf_counter() - t0
            self.solves += 1
            if len(self.cache) > 4000:
                self.cache.clear()
            self.cache[key] = f
        return f

    def rise(self):
        """(rise at each target (K), board mean rise (K)) at the terms' current poses."""
        st = self.T.st
        out = np.zeros(len(self.targets))
        fields = [self.field(k) for k in range(len(self.src))]
        for t, i in enumerate(self.targets):
            layer, i0, i1, j0, j1 = self._box(i)
            if t < len(self.src):
                val = sum(self.P[k] * fields[k][layer, i0:i1 + 1, j0:j1 + 1].mean() for k in range(len(self.src)))
            else:
                ci = int(np.clip((st.X[i] - self.x0) / self.dx, 0, self.nx - 1))
                cj = int(np.clip((st.Y[i] - self.y0) / self.dx, 0, self.ny - 1))
                val = sum(self.P[k] * fields[k][layer, ci, cj] for k in range(len(self.src)))
            out[t] = val
        mean = float(self.P.sum()) / (self.hsum * self.Lx * self.Ly * 1e-6)
        return out, mean

    def cost(self):
        """The thermal place term's cost at the current poses with FV rises (ex_exact.thermal_cost)."""
        from kae.physics import priors as PR
        T = self.T
        rise, mean = self.rise()
        b = T.knobs.barrier
        return float(sum(c * PR.phi(max(rise[t] - mean, 0.0) / a.value, b, T.knobs.u_sat)
                         for t, (a, c) in enumerate(zip(T._th_alloc, T._th_conf))))
