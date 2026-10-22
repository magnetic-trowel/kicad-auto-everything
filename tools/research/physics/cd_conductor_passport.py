# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Conductor passports: what each piece of copper is doing, per frequency band.

Round-2 lens CD (conductor-centric representation), docs/topics/physics/lens-cd.md.

A netlist says which pins share a conductor. This script computes, for every
piece of copper (every PEEC branch: a 0.5 mm strip of a pour or trace, a via,
a plane strip) on a small synthetic 2-layer board, what that piece does in each
band:

  * its share of each source's current (superposition: i_b = sum_p s_b^p I_p);
  * its Tellegen attribution of every budget (port impedance, coupling): the
    exact, additive split  Z_qp = sum_b 1/2 (v_b^p i_b^q + v_b^q i_b^p);
  * its exact removal cost for every budget, by the rank-1 identity
        dZ_qp = s_b^p s_b^q / y_bb,   y_bb = (N K^-1 N^T)_bb  (cut admittance),
    which is exact (Sherman-Morrison), unlike a first-order adjoint;
  * its leverage rho_b = 1 - z_b y_bb (DC: the probability that the piece is in
    a random spanning tree; sum over pieces = nodes - components, Foster);
  * its carry / image split: transport current (resistive-limit distribution)
    vs circulation (inductive redistribution and eddy currents);
  * for the switch-node copper, its charge partition by destination (local
    return, victim, world) and its thermal (heat-spreading) removal cost.

Board (26 x 18 mm, 0.5 mm cells, 1 oz copper on both layers, plane 0.8 mm below
the top layer, i.e. a 0.8 mm 2-layer board; f_x = R_s/(2 pi mu0 h) = 78 kHz):
  * a buck cell: input connector J1, VIN pour, input capacitor CIN, buck IC U1
    (VIN, SW, GND pins), SW pour, inductor L1, VOUT pour, COUT, output connector J2,
    top GND pours G1 (left) and G2 (right) stitched to the plane;
  * a sensitive trace (sensor S at the right to ADC A at the left, returns via
    single vias at both ends);
  * a GND plane with a 0.5 mm slot from the top edge down to y = 7 mm, so the
    left and right plane halves meet only under the inductor ("the neck").
Sources: feed (DC input current), load (DC output current), hot (hot-loop
commutation current, closes through CIN), ripple (output loop through COUT),
victim (unit probe current around the sensor loop: reciprocity).
Bands: DC, f_x (78 kHz), f_sw (500 kHz), HF (100 MHz).

Model: quasi-static RL-PEEC. x- and y-strips with Neumann partial inductances
(exact for parallel filaments; coplanar near neighbours use the exact strip GMD;
functions reused from fe_peec_plane.py), resistance R_s per square, vias as
vertical branches (R and self-L only, no via-via mutuals), lumped CIN/COUT/sensor
branches. Mesh (loop) formulation on a BFS fundamental-cycle basis:
    K = N^T Z N,  K z = -N^T Z i_p,  i = i_p + N z.
No skin effect (fine for distributions; R_ac at 100 MHz is ~5x higher), no
retardation (the board is < lambda/50 at 100 MHz). Electrostatics: point-matched
potential coefficients in a homogeneous medium (eps_r = 1; fractions are
eps-independent, absolute pF are not). Thermal: 2-layer finite-volume network
with FR-4, vias and h = 10 W/m^2K per face.

Also: checks of the removal identity against brute-force re-solves (rank-1 and
Woodbury), Foster's sum, an f/f_x sweep of where the hot-loop and victim currents
live, the Thevenin addition test for stitching vias (with a brute-force check),
a slot bridge and the unslotted board, the non-additivity of collective
removals, the crack (slit) law on a uniform sheet, and a Johnson-Lindenstrauss
(Spielman-Srivastava) estimate of whole-board leverage.

Run:  python tools/research/physics/cd_conductor_passport.py   (~2 min on 2 threads, ~1 GB)
Deterministic (fixed seeds). Numbers quoted [C] in lens-cd.md come from here.
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from collections import deque  # noqa: E402

import numpy as np  # noqa: E402
import scipy.linalg as sla  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fe_peec_plane import gmd_segments, mutual_parallel  # noqa: E402  (nH for mm inputs)

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
RHO_CU = 1.72e-8
T_CU = 35e-6
RS = RHO_CU / T_CU                 # ohm per square, 1 oz
D = 0.5                            # mm, cell pitch
NX, NY = 52, 36                    # 26 x 18 mm board
H = 0.8                            # mm, top copper above the plane
XC = (np.arange(NX) + 0.5) * D
YC = (np.arange(NY) + 0.5) * D
FX = RS / (2 * math.pi * MU0 * H * 1e-3)
BANDS = [("DC", 0.0), ("f_x", FX), ("f_sw", 5e5), ("HF", 1e8)]

GND, VIN, SW, VOUT, SIG = 0, 1, 2, 3, 4
NETNAME = {GND: "GND", VIN: "VIN", SW: "SW", VOUT: "VOUT", SIG: "SIG"}

R_VIA = RHO_CU * H * 1e-3 / (math.pi * 0.3e-3 * 25e-6)       # 0.3 mm drill, 25 um wall
L_VIA = 2e-7 * H * 1e-3 * (math.log(2 * H / 0.15) - 1.0)      # H


def tic():
    return time.perf_counter()


def cell(x, y):
    """(j, i) of the cell whose centre is nearest to (x, y) mm."""
    return int(round(y / D - 0.5)), int(round(x / D - 0.5))


def rect(x0, x1, y0, y1):
    yy, xx = np.meshgrid(YC, XC, indexing="ij")
    return (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)


# ----------------------------------------------------------------------------
# layout
# ----------------------------------------------------------------------------
def layout():
    top = np.full((NY, NX), -1)
    top[rect(0.5, 11.5, 0.5, 3.0)] = GND      # G1
    top[rect(15.0, 25.5, 0.5, 3.0)] = GND     # G2
    top[rect(0.5, 9.0, 3.5, 6.0)] = VIN
    top[rect(9.5, 13.5, 3.5, 6.0)] = SW
    top[rect(15.5, 25.5, 3.5, 6.0)] = VOUT
    top[rect(2.5, 23.5, 14.5, 15.0)] = SIG    # sensitive trace, 0.5 mm wide
    top[rect(2.5, 3.0, 13.5, 14.0)] = GND     # A.GND pad
    top[rect(23.0, 23.5, 13.5, 14.0)] = GND   # S.GND pad
    plane = np.ones((NY, NX), bool)
    plane[rect(13.0, 13.5, 7.0, 18.0)] = False  # slot from the top edge down to y = 7 mm
    pads = {"J1.VIN": (1.75, 4.75), "J1.GND": (1.75, 1.75), "CIN+": (6.25, 3.75), "CIN-": (6.25, 2.75),
            "U1.VIN": (8.75, 4.25), "U1.SW": (9.75, 4.25), "U1.GND": (8.75, 2.75),
            "L1.1": (12.75, 4.75), "L1.2": (16.25, 4.75), "COUT+": (18.25, 3.75), "COUT-": (18.25, 2.75),
            "J2.VOUT": (24.75, 4.75), "J2.GND": (24.75, 1.75),
            "A.in": (2.75, 14.75), "A.GND": (2.75, 13.75), "S.out": (23.25, 14.75), "S.GND": (23.25, 13.75)}
    vias = {"via J1": (1.75, 1.25), "via CIN-a": (5.75, 2.25), "via CIN-b": (6.75, 2.25),
            "via U1a": (8.25, 2.25), "via U1b": (9.25, 2.25), "via G1w": (3.75, 1.25), "via G1e": (10.75, 1.25),
            "via COUTa": (17.75, 2.25), "via COUTb": (18.75, 2.25), "via G2m": (21.25, 1.25),
            "via J2a": (24.25, 1.25), "via J2b": (25.25, 1.25), "via A.GND": (2.75, 13.75),
            "via S.GND": (23.25, 13.75)}
    return top, plane, pads, vias


# ----------------------------------------------------------------------------
# copper network (nodes = cells, branches = strips, vias, lumped parts)
# ----------------------------------------------------------------------------
class Copper:
    def __init__(self, top, plane, pads, vias, extra_plane=None):
        self.top, self.plane = top, plane.copy()
        if extra_plane is not None:
            self.plane |= extra_plane
        self.node = {}
        nl = []
        for j in range(NY):
            for i in range(NX):
                if top[j, i] >= 0:
                    self.node[(0, j, i)] = len(nl)
                    nl.append((0, j, i, top[j, i]))
        for j in range(NY):
            for i in range(NX):
                if self.plane[j, i]:
                    self.node[(1, j, i)] = len(nl)
                    nl.append((1, j, i, GND))
        self.nodes = np.array(nl)
        self.nn = len(nl)
        br = []   # (a, b, fam, s0, s1, c, z, layer, net, R, Lself, name)

        def zl(layer):
            return H if layer == 0 else 0.0
        for layer, mask, netmap in ((0, top >= 0, top), (1, self.plane, None)):
            for j in range(NY):
                for i in range(NX):
                    if not mask[j, i]:
                        continue
                    net = netmap[j, i] if netmap is not None else GND
                    if i + 1 < NX and mask[j, i + 1] and (netmap is None or netmap[j, i + 1] == net):
                        br.append((self.node[(layer, j, i)], self.node[(layer, j, i + 1)], 0, XC[i], XC[i + 1],
                                   YC[j], zl(layer), layer, net, RS, 0.0, ""))
                    if j + 1 < NY and mask[j + 1, i] and (netmap is None or netmap[j + 1, i] == net):
                        br.append((self.node[(layer, j, i)], self.node[(layer, j + 1, i)], 1, YC[j], YC[j + 1],
                                   XC[i], zl(layer), layer, net, RS, 0.0, ""))
        self.via_names = []
        for name, (x, y) in vias.items():
            j, i = cell(x, y)
            assert top[j, i] == GND and self.plane[j, i], name
            br.append((self.node[(0, j, i)], self.node[(1, j, i)], 2, 0.0, H, 0.0, 0.0, -1, GND,
                       R_VIA, L_VIA, name))
        self.pad = {k: self.node[(0,) + cell(*v)] for k, v in pads.items()}
        # lumped parts: (name, a, b, R, L, bands where present)
        lumped = [("CIN", "CIN+", "CIN-", 3e-3, 0.3e-9), ("COUT", "COUT+", "COUT-", 3e-3, 0.5e-9),
                  ("SENSOR", "S.out", "S.GND", 1.0, 0.0)]
        for name, pa, pb, r, l in lumped:
            br.append((self.pad[pa], self.pad[pb], 3, 0.0, 0.0, 0.0, 0.0, -1, -1, r, l, name))
        self.nb = len(br)
        arr = list(zip(*br))
        self.a = np.array(arr[0]); self.b = np.array(arr[1]); self.fam = np.array(arr[2])
        self.s0 = np.array(arr[3], float); self.s1 = np.array(arr[4], float); self.c = np.array(arr[5], float)
        self.z = np.array(arr[6], float); self.layer = np.array(arr[7]); self.net = np.array(arr[8])
        self.R = np.array(arr[9], float); self.Lself = np.array(arr[10], float); self.name = list(arr[11])
        self.lumped_idx = {n: k for k, n in enumerate(self.name) if n in ("CIN", "COUT", "SENSOR")}
        self.via_idx = {n: k for k, n in enumerate(self.name) if n.startswith("via ")}
        # branch midpoints (mm) for regions and maps
        self.mx = np.where(self.fam == 0, 0.5 * (self.s0 + self.s1), self.c)
        self.my = np.where(self.fam == 1, 0.5 * (self.s0 + self.s1), self.c)
        for n, k in self.via_idx.items():
            self.mx[k], self.my[k] = vias[n]
        for n, k in self.lumped_idx.items():
            self.mx[k], self.my[k] = pads[{"CIN": "CIN+", "COUT": "COUT+", "SENSOR": "S.out"}[n]]
        self.build_L()

    def build_L(self):
        """Dense partial inductances (H) for the x and y families; diagonal for vias and lumped parts."""
        self.Lfam = {}
        for f in (0, 1):
            k = np.nonzero(self.fam == f)[0]
            c, z, s0, s1 = self.c[k], self.z[k], self.s0[k], self.s1[k]
            dc = np.abs(c[:, None] - c[None, :])
            dz = np.abs(z[:, None] - z[None, :])
            d = np.sqrt(dc * dc + dz * dz)
            near = (dz < 1e-9) & (dc < 3 * D)
            ii, jj = np.nonzero(near)
            d[ii, jj] = gmd_segments(c[ii], D, c[jj], D)
            self.Lfam[f] = (k, mutual_parallel(s0[:, None], s1[:, None], s0[None, :], s1[None, :], d) * 1e-9)

    # -------------------------------------------------------------- operators
    def Zmul(self, v, w, active):
        """Branch voltages Z v for branch currents v (nb x m), at angular frequency w."""
        v = np.asarray(v)
        out = (self.R + 1j * w * self.Lself)[:, None] * v if w else self.R[:, None] * v
        if w:
            for f in (0, 1):
                k, L = self.Lfam[f]
                out[k] += 1j * w * (L @ v[k])
        out[~active] = 0
        return out

    def cycle_basis(self, active):
        """BFS spanning forest + fundamental cycles over the active branches. Returns N (nb x nm)."""
        nb, nn = self.nb, self.nn
        adj = [[] for _ in range(nn)]
        for k in np.nonzero(active)[0]:
            adj[self.a[k]].append((self.b[k], k))
            adj[self.b[k]].append((self.a[k], k))
        parent = np.full(nn, -1); pbr = np.full(nn, -1); depth = np.full(nn, -1)
        order = []
        comps = 0
        cx = np.array([XC[n[2]] for n in self.nodes]); cy = np.array([YC[n[1]] for n in self.nodes])
        seen = np.zeros(nn, bool)
        # roots: node nearest the centroid of each component (shorter cycles)
        for start in range(nn):
            if seen[start]:
                continue
            comp = []
            q = deque([start]); seen[start] = True
            while q:
                u = q.popleft(); comp.append(u)
                for v, _ in adj[u]:
                    if not seen[v]:
                        seen[v] = True; q.append(v)
            comp = np.array(comp)
            root = comp[np.argmin((cx[comp] - cx[comp].mean()) ** 2 + (cy[comp] - cy[comp].mean()) ** 2)]
            comps += 1
            depth[root] = 0
            q = deque([root])
            while q:
                u = q.popleft(); order.append(u)
                for v, k in adj[u]:
                    if depth[v] < 0:
                        depth[v] = depth[u] + 1; parent[v] = u; pbr[v] = k; q.append(v)
        intree = np.zeros(nb, bool)
        intree[pbr[pbr >= 0]] = True
        rows, cols, vals = [], [], []
        m = 0
        for k in np.nonzero(active & ~intree)[0]:
            u, v = self.a[k], self.b[k]
            path = [(k, 1.0)]
            # v up to LCA (child -> parent steps), u up to LCA (reversed later)
            x, y = v, u
            up_v, up_u = [], []
            while depth[x] > depth[y]:
                up_v.append(x); x = parent[x]
            while depth[y] > depth[x]:
                up_u.append(y); y = parent[y]
            while x != y:
                up_v.append(x); x = parent[x]
                up_u.append(y); y = parent[y]
            for ch in up_v:      # traverse child -> parent
                kb = pbr[ch]
                path.append((kb, 1.0 if self.a[kb] == ch else -1.0))
            for ch in reversed(up_u):   # traverse parent -> child
                kb = pbr[ch]
                path.append((kb, 1.0 if self.b[kb] == ch else -1.0))
            for kb, sgn in path:
                rows.append(kb); cols.append(m); vals.append(sgn)
            m += 1
        N = sp.csr_matrix((vals, (rows, cols)), shape=(nb, m))
        self.ncomp = comps
        return N, (parent, pbr, order)

    def particular(self, inj, tree):
        """Tree-path branch currents carrying the node injections (inj: nn x m, current INTO the copper)."""
        parent, pbr, order = tree
        S = np.array(inj, dtype=complex).copy()
        ip = np.zeros((self.nb, S.shape[1]), complex)
        for u in reversed(order):
            p = parent[u]
            if p < 0:
                assert np.allclose(S[u], 0, atol=1e-9), "injections do not sum to zero on a component"
                continue
            k = pbr[u]
            ip[k] = S[u] if self.a[k] == u else -S[u]
            S[p] += S[u]
        return ip


class Band:
    """Factorized mesh system for one band and one active-branch set."""

    def __init__(self, cu, f, active, copper_R_only=False, need_cut=True):
        self.cu, self.f, self.w = cu, f, 2 * math.pi * f
        self.active = active
        t0 = tic()
        self.N, self.tree = cu.cycle_basis(active)
        self.ncomp = cu.ncomp
        w = self.w
        N = self.N
        dense = N.toarray()
        if w == 0 or copper_R_only:
            # copper resistive (lumped parts keep their band impedance)
            zd = cu.R.astype(complex).copy()
            lum = cu.fam == 3
            zd[lum] += 1j * w * cu.Lself[lum]
            via = cu.fam == 2
            if copper_R_only:
                zd[via] = cu.R[via]
            self.zdiag = zd
            ZN = zd[:, None] * dense
            self.Rlimit = True
        else:
            ZN = self.cu.Zmul(dense, w, np.ones(cu.nb, bool))
            self.zdiag = cu.R + 1j * w * cu.Lself
            for f_ in (0, 1):
                k, L = cu.Lfam[f_]
                self.zdiag[k] = cu.R[k] + 1j * w * np.diag(L)
            self.Rlimit = False
        ZN[~active] = 0
        self.ZN = ZN
        K = N.T @ ZN
        if w == 0:
            K = K.real
        self.lu = sla.lu_factor(K)
        self.t_factor = tic() - t0
        self.y = None
        if need_cut:
            self.cut_admittance()

    def Zv(self, v):
        if self.Rlimit:
            return self.zdiag[:, None] * v
        return self.cu.Zmul(v, self.w, self.active)

    def solve_inj(self, inj):
        ip = self.cu.particular(inj, self.tree)
        rhs = -(self.N.T @ self.Zv(ip))
        zz = sla.lu_solve(self.lu, rhs)
        I = ip + self.N @ zz
        I[~self.active] = 0
        return I

    def cut_admittance(self, chunk=600):
        """y_bb = (N K^-1 N^T)_bb for every branch, and the generalized leverage 1 - (Z N K^-1 N^T)_bb."""
        t0 = tic()
        nb = self.cu.nb
        y = np.zeros(nb, complex)
        zp = np.zeros(nb, complex)
        NT = self.N.T.tocsc()
        for c0 in range(0, nb, chunk):
            c = np.arange(c0, min(nb, c0 + chunk))
            W = sla.lu_solve(self.lu, NT[:, c].toarray())          # nm x |c|
            Nc = self.N[c].toarray()                                # |c| x nm
            y[c] = np.einsum("km,mk->k", Nc, W)
            zp[c] = np.einsum("km,mk->k", self.ZN[c], W)
        self.y = y
        self.rho_gen = 1 - zp            # generalized leverage, sums to nodes - components
        self.t_cut = tic() - t0

    def potentials(self, V):
        """Node potentials from branch voltages V (nb x m), integrated along the spanning tree."""
        parent, pbr, order = self.tree
        phi = np.zeros((self.cu.nn, V.shape[1]), complex)
        for u in order:
            pa = parent[u]
            if pa < 0:
                continue
            k = pbr[u]
            phi[u] = phi[pa] - V[k] if self.cu.a[k] == pa else phi[pa] + V[k]
        return phi

    def woodbury(self, B, Ip, Iq):
        """Exact change of Z_qp when all branches in B are removed (Ip, Iq: currents per unit source)."""
        NB = self.N[B].toarray()
        W = sla.lu_solve(self.lu, NB.T)
        Y = NB @ W
        ip, iq = Ip[B], Iq[B]
        sol, res, rank, sv = np.linalg.lstsq(Y, ip, rcond=1e-12)
        if np.linalg.norm(Y @ sol - ip) > 1e-6 * max(np.linalg.norm(ip), 1e-30):
            return np.inf
        return iq @ sol


# ----------------------------------------------------------------------------
# sources and budgets
# ----------------------------------------------------------------------------
def injections(cu, names):
    """Node injection vectors (current INTO the copper) for the named sources; columns sum to zero per conductor."""
    defs = {
        "feed": [("J1.VIN", "U1.VIN"), ("U1.GND", "J1.GND")],
        "load": [("U1.SW", "L1.1"), ("L1.2", "J2.VOUT"), ("J2.GND", "U1.GND")],
        "hot": [("U1.GND", "U1.VIN")],                 # closes through CIN
        "ripple": [("U1.SW", "L1.1"), ("L1.2", "U1.GND")],   # closes through COUT
        "victim": [("A.in", "A.GND")],                 # unit probe around the sensor loop
    }
    S = np.zeros((cu.nn, len(names)))
    for m, n in enumerate(names):
        for p_in, p_out in defs[n]:
            S[cu.pad[p_in], m] += 1.0
            S[cu.pad[p_out], m] -= 1.0
    return S


SRC = {"DC": ["feed", "load", "victim"], "AC": ["hot", "ripple", "victim"]}


def budgets_for(band):
    if band == "DC":
        return [("R_feed", "feed", "feed"), ("R_load", "load", "load"), ("Z_vic<-load", "victim", "load"),
                ("Z_vic<-feed", "victim", "feed"), ("R_vic", "victim", "victim")]
    return [("Z_hot", "hot", "hot"), ("Z_vic<-hot", "victim", "hot"), ("Z_rip", "ripple", "ripple"),
            ("Z_vic<-rip", "victim", "ripple"), ("Z_vic", "victim", "victim")]


BUDGET_PQ = {nm: (p, q) for band in ("DC", "AC") for nm, p, q in budgets_for(band)}


def bmetric(nm, z, f):
    """The scalar a budget is judged by: DC -> R; AC self term -> L (H); AC coupling -> |Z| (V per A)."""
    if f == 0:
        return np.real(z)
    p, q = BUDGET_PQ[nm]
    return np.imag(z) / (2 * math.pi * f) if p == q else np.abs(z)


def dpct(nm, z0, dz, f):
    """Exact % change of a budget's metric when its Z changes by dz (array-safe)."""
    m0 = bmetric(nm, z0, f)
    return 100.0 * (bmetric(nm, z0 + dz, f) - m0) / abs(m0)


def active_mask(cu, band):
    act = np.ones(cu.nb, bool)
    if band == "DC":
        act[cu.lumped_idx["CIN"]] = False
        act[cu.lumped_idx["COUT"]] = False
    return act


def fmt_z(z, w):
    """Readable impedance: DC in mOhm/uOhm, AC as R + L."""
    if w == 0:
        return f"{z.real * 1e3:.4f} mOhm"
    return f"R {z.real * 1e3:.3f} mOhm, L {z.imag / w * 1e9:.4f} nH"


# ----------------------------------------------------------------------------
# regions for the readable passport
# ----------------------------------------------------------------------------
def regions(cu):
    mx, my, net, lay, fam = cu.mx, cu.my, cu.net, cu.layer, cu.fam
    reg = np.full(cu.nb, -1)
    names = []

    def add(name, m):
        names.append(name)
        reg[(reg < 0) & m] = len(names) - 1
    top, pl = lay == 0, lay == 1
    vias = fam == 2
    add("VIN pour near CIN/U1", top & (net == VIN) & (mx >= 5.0))
    add("VIN feed trunk (J1 side)", top & (net == VIN))
    add("SW pour", top & (net == SW))
    add("VOUT pour", top & (net == VOUT))
    add("G1 top under hot loop", top & (net == GND) & (mx >= 5.0) & (mx < 10.0) & (my < 3.5))
    add("G1 top, rest", top & (net == GND) & (mx < 11.6) & (my < 3.5))
    add("G2 top", top & (net == GND) & (my < 3.5))
    add("sensitive trace", top & (net == SIG))
    add("victim GND pads", top & (net == GND))
    add("vias at hot loop", vias & (mx >= 5.0) & (mx < 10.0) & (my < 3.5))
    add("other G1/G2 vias", vias & (my < 3.5))
    add("victim vias", vias)
    add("plane at slot end", pl & (mx >= 11.5) & (mx < 15.0) & (my >= 6.0) & (my < 8.5))
    add("plane under hot loop", pl & (mx >= 4.0) & (mx < 11.0) & (my < 7.0))
    add("plane neck under L1", pl & (mx >= 11.0) & (mx < 16.0) & (my < 7.0))
    add("plane right low", pl & (mx >= 16.0) & (my < 7.0))
    add("plane left low", pl & (mx < 4.0) & (my < 7.0))
    add("plane under trace, left", pl & (mx < 13.0) & (my >= 12.5) & (my < 17.0))
    add("plane under trace, right", pl & (mx >= 13.0) & (my >= 12.5) & (my < 17.0))
    add("plane left middle", pl & (mx < 13.0) & (my < 12.5))
    add("plane right middle", pl & (mx >= 13.0) & (my < 12.5))
    add("plane top strip", pl)
    add("lumped parts", fam == 3)
    assert (reg >= 0).all()
    return reg, names


# ----------------------------------------------------------------------------
# electrostatics of the switch node, thermal network
# ----------------------------------------------------------------------------
def electrostatics(cu):
    """Charge on each SW cell with SW at 1 V and everything else at 0 V, partitioned by destination."""
    nodes = cu.nodes
    z = np.where(nodes[:, 0] == 0, H, 0.0)
    x = XC[nodes[:, 2]]; y = YC[nodes[:, 1]]
    a = D * 1e-3
    r = np.sqrt((x[:, None] - x[None, :]) ** 2 + (y[:, None] - y[None, :]) ** 2 + (z[:, None] - z[None, :]) ** 2) * 1e-3
    np.fill_diagonal(r, 1.0)
    P = 1.0 / (4 * math.pi * EPS0 * r)
    np.fill_diagonal(P, 2.9732 / (4 * math.pi * EPS0 * a))      # average potential of a uniform square
    isw = (nodes[:, 0] == 0) & (nodes[:, 3] == SW)
    S = np.nonzero(isw)[0]; O = np.nonzero(~isw)[0]
    V = isw.astype(float)
    luP = sla.lu_factor(P)
    q = sla.lu_solve(luP, V)
    # induced charge on others due to each SW cell's own charge (others held at 0 V)
    luO = sla.lu_factor(P[np.ix_(O, O)])
    T = -sla.lu_solve(luO, P[np.ix_(O, S)])                     # nO x nS, per coulomb on SW cell
    grp = np.full(len(O), "", object)
    on = nodes[O]
    grp[on[:, 0] == 1] = "plane"
    grp[(on[:, 0] == 0) & (on[:, 3] == GND)] = "top GND"
    grp[(on[:, 0] == 0) & (on[:, 3] == VIN)] = "VIN"
    grp[(on[:, 0] == 0) & (on[:, 3] == VOUT)] = "VOUT"
    grp[(on[:, 0] == 0) & (on[:, 3] == SIG)] = "victim trace"
    part = {g: (T[grp == g] * q[S][None, :]).sum(0) for g in ("plane", "top GND", "VIN", "VOUT", "victim trace")}
    part["world"] = q[S] + sum(part.values())
    # exact removal of one SW cell e: q' = q - C[:, e] q_e / C_ee, with C = P^-1
    Ce = sla.lu_solve(luP, np.eye(cu.nn)[:, S])                 # nn x nS columns of C
    Cee = Ce[S, np.arange(len(S))]
    vic = (nodes[:, 0] == 0) & (nodes[:, 3] == SIG)
    dworld = -q[S] * Ce.sum(0) / Cee
    dvictim = -(q[S] / Cee) * Ce[vic].sum(0)
    return dict(S=S, q=q, part=part, Qsw=q[S].sum(), Qworld=q.sum(), Qvic=q[vic].sum(),
                dworld=dworld, dvictim=dvictim)


def thermal(cu, top, plane, pads, vias, P_src):
    """2-layer FV network on every board cell. Returns T, G^-1 and the copper-edge removal costs for T(U1)."""
    k_cu, k_fr4, h_c = 390.0, 0.3, 10.0
    t, hh, a = T_CU, H * 1e-3, D * 1e-3
    n = 2 * NX * NY
    nid = lambda l, j, i: (l * NY + j) * NX + i  # noqa: E731
    cu_mask = [top >= 0, plane]
    g_sq = [np.where(cu_mask[l], k_cu * t, 0.0) + k_fr4 * hh / 2 for l in (0, 1)]
    rows, cols, vals = [], [], []
    edges = []   # (node_a, node_b, g_total, g_copper, layer, j, i, dir)

    def add(p, q, g):
        rows.extend([p, q, p, q]); cols.extend([p, q, q, p]); vals.extend([g, g, -g, -g])
    for l in (0, 1):
        for j in range(NY):
            for i in range(NX):
                for dj, di, dr in ((0, 1, 0), (1, 0, 1)):
                    jj, ii = j + dj, i + di
                    if jj >= NY or ii >= NX:
                        continue
                    g = 1.0 / (0.5 / g_sq[l][j, i] + 0.5 / g_sq[l][jj, ii])
                    gc = (k_cu * t) if (cu_mask[l][j, i] and cu_mask[l][jj, ii]) else 0.0
                    if l == 0 and gc and top[j, i] != top[jj, ii]:
                        gc = 0.0
                    add(nid(l, j, i), nid(l, jj, ii), g)
                    edges.append((nid(l, j, i), nid(l, jj, ii), g, gc, l, j, i, dr))
    gv = k_fr4 * a * a / hh
    gvia = k_cu * math.pi * 0.3e-3 * 25e-6 / hh
    via_cells = {cell(*v) for v in vias.values()}
    for j in range(NY):
        for i in range(NX):
            add(nid(0, j, i), nid(1, j, i), gv + (gvia if (j, i) in via_cells else 0.0))
    diag = np.full(n, h_c * a * a)
    G = sp.csr_matrix((vals, (rows, cols)), shape=(n, n)) + sp.diags(diag)
    Ginv = np.linalg.inv(G.toarray())
    p = np.zeros(n)
    for pin, w in P_src.items():
        j, i = cell(*pads[pin]); p[nid(0, j, i)] += w
    wv = np.zeros(n)
    for pin in P_src:
        j, i = cell(*pads[pin]); wv[nid(0, j, i)] += 1.0 / len(P_src)
    T = Ginv @ p
    lam = Ginv @ wv
    E = np.array(edges, dtype=float)
    ea, eb = E[:, 0].astype(int), E[:, 1].astype(int)
    gcu = E[:, 3]
    dT = T[ea] - T[eb]; dl = lam[ea] - lam[eb]
    Rab = Ginv[ea, ea] + Ginv[eb, eb] - 2 * Ginv[ea, eb]
    with np.errstate(divide="ignore", invalid="ignore"):
        dTu = np.where(gcu > 0, gcu * dT * dl / (1 - gcu * Rab), 0.0)
    return dict(T=T, Tu=wv @ T, edges=E, dTu=dTu, attrib=gcu * dT * dl, flux=gcu * dT, nid=nid)


# ----------------------------------------------------------------------------
# main experiment
# ----------------------------------------------------------------------------
def pct(x, tot):
    return 100.0 * x / tot if tot else float("nan")


def main():
    T0 = tic()
    top, plane, pads, vias = layout()
    t0 = tic()
    cu = Copper(top, plane, pads, vias)
    print(f"Board {NX * D:.0f} x {NY * D:.0f} mm, cell {D} mm, plane {H} mm below top copper, 1 oz;"
          f" f_x = R_s/(2 pi mu0 h) = {FX / 1e3:.1f} kHz")
    print(f"nodes {cu.nn}, branches {cu.nb} (x {np.sum(cu.fam == 0)}, y {np.sum(cu.fam == 1)}, vias {np.sum(cu.fam == 2)},"
          f" lumped {np.sum(cu.fam == 3)}); partial-L build {tic() - t0:.1f} s")
    reg, rnames = regions(cu)
    res = {}
    for bname, f in BANDS:
        t0 = tic()
        act = active_mask(cu, bname)
        bd = Band(cu, f, act)
        srcs = SRC["DC" if f == 0 else "AC"]
        I = bd.solve_inj(injections(cu, srcs))
        V = bd.Zv(I)
        out = dict(band=bd, I=I, V=V, srcs=srcs, f=f)
        if f > 0:      # resistive-limit (transport) distribution for the carry / image split
            bR = Band(cu, f, act, copper_R_only=True, need_cut=False)
            out["IR"] = bR.solve_inj(injections(cu, srcs))
        else:
            out["IR"] = I
        res[bname] = out
        nm = bd.N.shape[1]
        print(f"[{bname:4s}] f = {f:10.4g} Hz: meshes {nm}, components {bd.ncomp}, factor {bd.t_factor:.1f} s,"
              f" cut admittances {bd.t_cut:.1f} s, total {tic() - t0:.1f} s")

    # ---------------------------------------------------------------- budgets
    print("\n== Budgets (per unit source current; Z_qp = open-circuit volts at q per amp at p);"
          "\n   chi = |sum of per-piece Tellegen terms| / sum of their magnitudes (small = a residual of cancelling terms)")
    for bname, f in BANDS:
        o = res[bname]; w = 2 * math.pi * f
        si = {s: k for k, s in enumerate(o["srcs"])}
        o["Z"] = {}
        for nm_, p, q in budgets_for(bname):
            Zqp = o["V"][:, si[p]] @ o["I"][:, si[q]]
            o["Z"][nm_] = Zqp
            a_b = 0.5 * (o["V"][:, si[p]] * o["I"][:, si[q]] + o["V"][:, si[q]] * o["I"][:, si[p]])
            chi = abs(a_b.sum()) / np.abs(a_b).sum()          # cancellation index (1 = no cancellation)
            extra = f"  chi = {chi:.3f}"
            if bname == "DC" and nm_ == "Z_vic<-load":
                extra += f"  -> {abs(Zqp) * 3.0 * 1e6:.1f} uV error at the ADC for a 3 A load"
            print(f"  {bname:4s} {nm_:12s} {fmt_z(Zqp, w):34s}{extra}")

    # ---------------------------------------------------------------- checks
    print("\n== Checks")
    rng = np.random.default_rng(1)
    for bname, f in (("DC", 0.0), ("HF", 1e8)):
        o = res[bname]; bd = o["band"]; I = o["I"]; si = {s: k for k, s in enumerate(o["srcs"])}
        p_, q_ = ("load", "victim") if bname == "DC" else ("hot", "victim")
        Zpp = o["V"][:, si[p_]] @ I[:, si[p_]]
        Zqp = o["V"][:, si[p_]] @ I[:, si[q_]]
        cand = np.nonzero(bd.active & (np.abs(I[:, si[p_]]) > 1e-3) & (np.abs(bd.y) > 1e-9 * np.abs(bd.y).max()))[0]
        errs = []
        for k in rng.choice(cand, 4, replace=False):
            pred_pp = I[k, si[p_]] ** 2 / bd.y[k]
            pred_qp = I[k, si[p_]] * I[k, si[q_]] / bd.y[k]
            act2 = bd.active.copy(); act2[k] = False
            b2 = Band(cu, f, act2, need_cut=False)
            I2 = b2.solve_inj(injections(cu, o["srcs"]))
            V2 = b2.Zv(I2)
            d_pp = V2[:, si[p_]] @ I2[:, si[p_]] - Zpp
            d_qp = V2[:, si[p_]] @ I2[:, si[q_]] - Zqp
            errs.append(max(abs(pred_pp - d_pp) / abs(d_pp), abs(pred_qp - d_qp) / max(abs(d_qp), 1e-30)))
        print(f"  [{bname}] rank-1 removal identity vs brute-force re-solve, 4 random branches:"
              f" max rel. error {max(errs):.1e}")
        if bname == "DC":
            rho = 1 - (bd.zdiag * bd.y).real
            rho[~bd.active] = 0
            print(f"  [DC] Foster: sum of leverage = {rho.sum():.3f}; nodes - components = {cu.nn - bd.ncomp}")
            interior = bd.active & (cu.layer == 1) & (cu.mx > 2) & (cu.mx < 11) & (cu.my > 9) & (cu.my < 16)
            print(f"  [DC] leverage of interior plane strips (x 2-11, y 9-16 mm): median {np.median(rho[interior]):.3f},"
                  f" 10-90% {np.percentile(rho[interior], 10):.3f}-{np.percentile(rho[interior], 90):.3f}"
                  f" (infinite square lattice: exactly 0.5)")
            o["rho"] = rho
        gen = bd.rho_gen[bd.active].sum()
        print(f"  [{bname}] generalized leverage trace = {gen.real:.3f} (must equal {cu.nn - bd.ncomp})")

    # ---------------------------------------------------------------- per-band region passports
    print("\n== Region passports")
    print("   hold% = Tellegen share of a self budget (DC: of R; AC: of the inductive part of Z)")
    print("   rm%   = sum over the region's strips of the EXACT change of each budget when that one strip is removed")
    print("           (rank-1, % of the budget; S = the region contains sole-path strips for that budget)")
    print("   kappa = sum|I(f)| / sum|I_R| per source: >1 the band pulls current in (image), <1 it releases the copper,")
    print("           'eddy' = no transport current at all (pure induced circulation); '.' = region holds < 1% of that current")
    passports = {}
    for bname, f in BANDS:
        o = res[bname]; bd = o["band"]; I, V, IR = o["I"], o["V"], o["IR"]
        si = {s_: k for k, s_ in enumerate(o["srcs"])}
        bud = budgets_for(bname)
        part = "real" if f == 0 else "imag"
        ymax = np.abs(bd.y).max()
        print(f"\n[{bname}] {'region':26s} | hold% " + " ".join(f"{b_[0]:>8s}" for b_ in bud if b_[1] == b_[2])
              + " | rm% " + " ".join(f"{b_[0][:11]:>12s}" for b_ in bud) + " | kappa " + " ".join(o["srcs"]))
        rows = {}
        for r, rn in enumerate(rnames):
            sel = np.nonzero((reg == r) & bd.active)[0]
            if not len(sel):
                continue
            hold = []
            for nm_, p_, q_ in bud:
                if p_ != q_:
                    continue
                ap = (V[sel, si[p_]] * I[sel, si[p_]]).sum()
                hold.append(pct(getattr(ap, part), getattr(o["Z"][nm_], part)))
            rm, sole = [], []
            yb = bd.y[sel]
            bridge = np.abs(yb) < 1e-9 * ymax
            for nm_, p_, q_ in bud:
                prod = I[sel, si[p_]] * I[sel, si[q_]]
                hit = bridge & (np.abs(prod) > 1e-9)
                with np.errstate(divide="ignore", invalid="ignore"):
                    dz = np.where(bridge, 0, prod / np.where(bridge, 1, yb))
                rm.append(float(np.sum(dpct(nm_, o["Z"][nm_], dz, f))))
                sole.append(bool(hit.any()))
            kap = []
            for s_ in o["srcs"]:
                a_ = np.abs(I[sel, si[s_]]).sum(); r_ = np.abs(IR[sel, si[s_]]).sum()
                tot_ = np.abs(I[bd.active, si[s_]]).sum()
                if a_ < 0.01 * tot_:
                    kap.append(".")
                else:
                    kap.append("eddy" if r_ < 1e-6 else f"{a_ / r_:.2f}")
            rows[rn] = (hold, rm, sole, kap)
            cs = " ".join(f"{v:+11.1f}{'S' if so else ' '}" for v, so in zip(rm, sole))
            print(f"[{bname}] {rn:26s} | " + "     ".join(f"{v:5.1f}" for v in hold) + "    | " + cs
                  + " | " + " ".join(f"{k_:>5s}" for k_ in (kap if f else ["", "", ""])))
        passports[bname] = rows

    # ---------------------------------------------------------------- coupling attributions (cancellation)
    print("\n== Tellegen attribution of two couplings by region (sums to 100%; large +/- terms = cancellation)")
    for bname, nm_ in (("DC", "Z_vic<-load"), ("HF", "Z_vic<-hot")):
        o = res[bname]; I, V = o["I"], o["V"]; si = {s_: k for k, s_ in enumerate(o["srcs"])}
        p_, q_ = BUDGET_PQ[nm_]
        a_b = 0.5 * (V[:, si[p_]] * I[:, si[q_]] + V[:, si[q_]] * I[:, si[p_]])
        z0 = o["Z"][nm_]
        proj = (a_b * np.conj(z0)).real / abs(z0)          # component along the total
        shares = sorted(((100 * proj[reg == r].sum() / abs(z0), rn) for r, rn in enumerate(rnames)), reverse=True)
        hi_s = ", ".join(f"{rn} {v:+.1f}%" for v, rn in shares[:3])
        lo_s = ", ".join(f"{rn} {v:+.1f}%" for v, rn in shares[-2:])
        print(f"  [{bname}] {nm_}: largest {hi_s}; most negative {lo_s}")
    o = res["HF"]; bd = o["band"]; si = {s_: k for k, s_ in enumerate(o["srcs"])}
    okb = bd.active & (np.abs(bd.y) > 1e-9 * np.abs(bd.y).max())
    dLh = (o["I"][okb, si["hot"]] ** 2 / bd.y[okb]).imag
    zh = o["Z"]["Z_hot"].imag
    print(f"  [HF] magnetic Rayleigh check: strips whose removal lowers L_hot by more than 1e-9 of it:"
          f" {np.sum(dLh < -1e-9 * zh)} of {okb.sum()}; most negative change {dLh.min() / zh:.1e} of L_hot")

    # ---------------------------------------------------------------- what each conductor is doing
    print("\n== What each conductor is doing (verbs from the signs of exact single-strip removals; thresholds 5% / 10%)")
    for r, rn in enumerate(rnames):
        jobs = []
        for bname, f in BANDS:
            if rn not in passports[bname]:
                continue
            hold, rm, sole, kap = passports[bname][rn]
            o = res[bname]
            selfb = [b_ for b_ in budgets_for(bname) if b_[1] == b_[2]]
            for (nm_, p_, q_), h_ in zip(selfb, hold):
                if h_ >= 10:
                    jobs.append(f"{bname}: holds {h_:.0f}% of {nm_}")
            for (nm_, p_, q_), c_, so in zip(budgets_for(bname), rm, sole):
                if so:
                    jobs.append(f"{bname}: series path (sole) for {nm_}")
                elif p_ == q_ and c_ >= 5:
                    jobs.append(f"{bname}: carries {p_} (strip removals +{c_:.0f}% {nm_})")
                elif p_ != q_ and c_ >= 10:
                    jobs.append(f"{bname}: lowers coupling {q_}->{p_} (strip removals +{c_:.0f}%)")
                elif p_ != q_ and c_ <= -10:
                    jobs.append(f"{bname}: raises coupling {q_}->{p_} (strip removals {c_:.0f}%)")
            for s_, k_ in zip(o["srcs"], kap):
                if f and k_ == "eddy":
                    nm_ = [b_[0] for b_ in budgets_for(bname) if b_[1] == b_[2] == s_]
                    c_ = rm[[b_[0] for b_ in budgets_for(bname)].index(nm_[0])] if nm_ else 0
                    if c_ >= 1:
                        jobs.append(f"{bname}: images {s_} by induced current (strip removals +{c_:.1f}% {nm_[0]})")
        if jobs:
            print(f"  {rn}: " + "; ".join(dict.fromkeys(jobs)))
        else:
            print(f"  {rn}: no electrical job above threshold in any band")

    print("\n== Whole-region removal (Woodbury, exact): what would break without each region?")
    for rn in ("plane at slot end", "plane under hot loop", "plane neck under L1", "vias at hot loop", "other G1/G2 vias",
               "G1 top, rest"):
        r = rnames.index(rn)
        txt = []
        for bname, f in BANDS:
            o = res[bname]; bd = o["band"]; I = o["I"]
            si = {s_: k for k, s_ in enumerate(o["srcs"])}
            part = "real" if f == 0 else "imag"
            sel = np.nonzero((reg == r) & bd.active)[0]
            items = []
            for nm_, p_, q_ in budgets_for(bname):
                if nm_ in ("R_vic", "Z_vic"):
                    continue
                dz = bd.woodbury(sel, I[:, si[p_]], I[:, si[q_]])
                z0 = o["Z"][nm_]
                if np.isinf(dz):
                    items.append(f"{nm_} disconnects")
                else:
                    items.append(f"{nm_} {dpct(nm_, z0, dz, f):+.0f}%")
            txt.append(f"{bname}: " + ", ".join(items))
        print(f"  {rn} ({len(np.nonzero(reg == r)[0])} pieces): " + " | ".join(txt))

    # ---------------------------------------------------------------- per-harmonic return maps (f / f_x sweep)
    print("\n== Where the currents live vs f/f_x (plane strips; the f_x transition, per source)")
    print("   hot: share of its plane current within 4 mm of the loop, and share of its return that dives into the plane at CIN-")
    print("   victim: share of its plane current within 1.5 mm of the trace line (away from the slot), loop L")
    pl = cu.layer == 1
    dist = np.hypot(cu.mx - 7.5, cu.my - 3.25)
    under = pl & (np.abs(cu.my - 14.75) <= 1.5) & (np.abs(cu.mx - 13.25) > 2.0)
    cinv = [cu.via_idx["via CIN-a"], cu.via_idx["via CIN-b"]]
    act = active_mask(cu, "HF")
    rowsf = []
    for label, ff, ronly in [("R-limit", FX, True)] + [(f"{r_:g} f_x", r_ * FX, False) for r_ in (0.1, 0.3, 1, 3, 10, 100, 1000)]:
        b_ = Band(cu, ff, act, copper_R_only=ronly, need_cut=False)
        I_ = b_.solve_inj(injections(cu, ["hot", "victim"]))
        V_ = b_.Zv(I_)
        ah, av = np.abs(I_[:, 0]), np.abs(I_[:, 1])
        w_ = 2 * math.pi * ff
        Lh = (V_[:, 0] @ I_[:, 0]).imag / w_ * 1e9
        Lv = (V_[:, 1] @ I_[:, 1]).imag / w_ * 1e9
        rowsf.append((label, ah[pl & (dist < 4)].sum() / ah[pl].sum(), abs(I_[cinv, 0].sum()),
                      av[under].sum() / av[pl].sum(), Lh, Lv))
    print("   f            hot: within 4 mm   dives at CIN-   victim: under trace    L_hot (nH)   L_vic (nH)")
    for label, a1, a2, a3, lh, lv in rowsf:
        lhs = "    -" if label == "R-limit" else f"{lh:7.3f}"
        lvs = "    -" if label == "R-limit" else f"{lv:7.2f}"
        print(f"   {label:10s}        {a1:5.2f}            {a2:5.2f}              {a3:5.2f}            {lhs}      {lvs}")

    # ---------------------------------------------------------------- first-order vs exact
    print("\n== First-order (attribution) vs exact removal cost, per strip")
    for bname in ("DC", "HF"):
        o = res[bname]; bd = o["band"]; I, V = o["I"], o["V"]
        si = {s: k for k, s in enumerate(o["srcs"])}
        p = "load" if bname == "DC" else "hot"
        part = "real" if bname == "DC" else "imag"
        att = getattr(V[:, si[p]] * I[:, si[p]], part)
        with np.errstate(divide="ignore", invalid="ignore"):
            ex = getattr(I[:, si[p]] ** 2 / bd.y, part)
        ok = bd.active & (np.abs(att) > 1e-6 * np.abs(att).max()) & np.isfinite(ex) & (np.abs(bd.y) > 1e-9 * np.abs(bd.y).max())
        ratio = ex[ok] / att[ok]
        pl = ok & (cu.layer == 1)
        selfonly = getattr(I[:, si[p]] ** 2 * bd.zdiag, part)
        r2 = ex[ok] / selfonly[ok]
        print(f"  [{bname}] source {p}: exact / Tellegen-attribution over {ok.sum()} loaded strips: median {np.median(ratio):.2f},"
              f" 10-90% {np.percentile(ratio, 10):.2f}-{np.percentile(ratio, 90):.2f}; plane strips median"
              f" {np.median(ex[pl] / att[pl]):.2f}; exact / (I_b^2 z_bb, mutuals ignored): median {np.median(r2):.3f}")

    # ---------------------------------------------------------------- queries
    print("\n== Query: what are the hot-loop vias doing?")
    for vn in ("via CIN-a", "via U1a", "via U1b", "via G1e"):
        k = cu.via_idx[vn]
        parts = []
        for bname, f in BANDS:
            o = res[bname]; si = {s: m for m, s in enumerate(o["srcs"])}
            sh = ", ".join(f"{s} {abs(o['I'][k, si[s]]):.3f}" for s in o["srcs"])
            parts.append(f"{bname}: {sh}")
        o = res["HF"]; bd = o["band"]; si = {s: m for m, s in enumerate(o["srcs"])}
        Ih = o["I"][k, si["hot"]]
        dL = (Ih ** 2 / bd.y[k]).imag / (2 * math.pi * 1e8) * 1e12
        print(f"  {vn:10s} current share | " + " | ".join(parts) + f" | removing it: L_hot +{dL:.1f} pH at HF")

    print("\n== Query: what would break if the plane neck were cut? (x = 14.0-14.5 mm, y = 0-3 mm, i.e. a 3 mm notch)")
    notch = np.nonzero((cu.layer == 1) & (cu.fam == 0) & (np.abs(cu.mx - 14.0) < 0.01) & (cu.my < 3.0))[0]
    print(f"  removes {len(notch)} plane strips")
    for bname, f in BANDS:
        o = res[bname]; bd = o["band"]; I, V = o["I"], o["V"]; w = 2 * math.pi * f
        si = {s: m for m, s in enumerate(o["srcs"])}
        txt = []
        for nm_, p, q in budgets_for(bname):
            if nm_ in ("R_vic", "Z_vic", "R_feed", "Z_hot"):
                continue
            dz = bd.woodbury(notch, I[:, si[p]], I[:, si[q]])
            single = (I[notch, si[p]] * I[notch, si[q]] / bd.y[notch]).sum()
            fo = (0.5 * (V[notch, si[p]] * I[notch, si[q]] + V[notch, si[q]] * I[notch, si[p]])).sum()
            tot = o["Z"][nm_]
            extra = f", 1st-order {dpct(nm_, tot, fo, f):+.1f}%" if f == 0 else ""
            txt.append(f"{nm_} {dpct(nm_, tot, dz, f):+.1f}% (sum of single strips {dpct(nm_, tot, single, f):+.1f}%{extra})")
        print(f"  [{bname}] " + "; ".join(txt))
    # brute-force check of the notch at DC
    o = res["DC"]; bd = o["band"]; si = {s: m for m, s in enumerate(o["srcs"])}
    act2 = bd.active.copy(); act2[notch] = False
    b2 = Band(cu, 0.0, act2, need_cut=False)
    I2 = b2.solve_inj(injections(cu, o["srcs"])); V2 = b2.Zv(I2)
    dz_b = (V2[:, si["load"]] @ I2[:, si["victim"]]) - o["Z"]["Z_vic<-load"]
    dz_w = bd.woodbury(notch, o["I"][:, si["load"]], o["I"][:, si["victim"]])
    print(f"  [DC] Woodbury vs brute force for Z_vic<-load: {dz_w.real * 1e6:.4f} vs {dz_b.real * 1e6:.4f} uOhm")

    print("\n== Addition test: one more stitching via on top GND (exact: dZ_qp = -dV^p dV^q / (z_via + Z_th))")
    cand = [k for k in range(cu.nn) if cu.nodes[k, 0] == 0 and cu.nodes[k, 3] == GND
            and (1, cu.nodes[k, 1], cu.nodes[k, 2]) in cu.node and cu.nodes[k, 1] < 7]
    have = {(cu.nodes[cu.a[k], 1], cu.nodes[cu.a[k], 2]) for k in cu.via_idx.values()}
    cand = [k for k in cand if (cu.nodes[k, 1], cu.nodes[k, 2]) not in have]
    best_site = None
    for bname, f in (("HF", 1e8), ("DC", 0.0)):
        o = res[bname]; bd = o["band"]; V = o["V"]; w = 2 * math.pi * f
        si = {s: m for m, s in enumerate(o["srcs"])}
        phi = bd.potentials(V)
        kp = np.array([cu.node[(1, cu.nodes[k, 1], cu.nodes[k, 2])] for k in cand])
        kt = np.array(cand)
        inj = np.zeros((cu.nn, len(cand)))
        inj[kt, np.arange(len(cand))] = 1.0
        inj[kp, np.arange(len(cand))] = -1.0
        It = bd.solve_inj(inj)
        zth = np.einsum("bm,bm->m", bd.Zv(It), It)          # Thevenin impedance top->plane at each site
        zv = R_VIA + 1j * w * L_VIA
        pairs = (("hot", "hot", "pH"), ("hot", "victim", "pH")) if f else (("load", "victim", "uOhm"), ("load", "load", "uOhm"))
        for p, q, unit in pairs:
            dvp = phi[kt, si[p]] - phi[kp, si[p]]
            dvq = phi[kt, si[q]] - phi[kp, si[q]]
            dz = -dvp * dvq / (zv + zth)
            part = "real" if f == 0 else "imag"
            scale = (1e12 / w) if f else 1e6
            val = getattr(dz, part) * scale
            order_ = np.argsort(val)
            best = ", ".join(f"({XC[cu.nodes[cand[m], 2]]:.2f},{YC[cu.nodes[cand[m], 1]]:.2f}) {val[m]:+.2f}"
                             for m in order_[:3])
            print(f"  [{bname}] {p}->{q}: best of {len(cand)} sites (x,y mm) and change in {unit}: {best};"
                  f" median site {np.median(val):+.3f}, least useful {val[order_[-1]]:+.3f}")
            if f and p == q == "hot":
                best_site = (cand[order_[0]], val[order_[0]])
    # brute-force check of the best HF hot-loop site
    k0, pred = best_site
    xy = (XC[cu.nodes[k0, 2]], YC[cu.nodes[k0, 1]])
    cu3 = Copper(top, plane, pads, dict(vias, **{"via new": xy}))
    act3 = active_mask(cu3, "HF")
    b3 = Band(cu3, 1e8, act3, need_cut=False)
    I3 = b3.solve_inj(injections(cu3, SRC["AC"])); V3 = b3.Zv(I3)
    dL = ((V3[:, 0] @ I3[:, 0]) - res["HF"]["Z"]["Z_hot"]).imag / (2 * math.pi * 1e8) * 1e12
    print(f"  brute-force check, new via at ({xy[0]:.2f},{xy[1]:.2f}): L_hot change {dL:+.3f} pH vs formula {pred:+.3f} pH")

    print("\n== Addition test: bridge the slot under the trace (restore one plane cell at x = 13.25, y = 14.75)")
    extra = np.zeros((NY, NX), bool)
    extra[cell(13.25, 14.75)] = True
    cu2 = Copper(top, plane, pads, vias, extra_plane=extra)
    for bname, f in BANDS:
        o = res[bname]; w = 2 * math.pi * f
        act = active_mask(cu2, bname)
        b2 = Band(cu2, f, act, need_cut=False)
        I2 = b2.solve_inj(injections(cu2, o["srcs"])); V2 = b2.Zv(I2)
        si = {s: m for m, s in enumerate(o["srcs"])}
        txt = []
        for nm_, p, q in budgets_for(bname):
            z2 = V2[:, si[p]] @ I2[:, si[q]]
            z1 = o["Z"][nm_]
            txt.append(f"{nm_} {dpct(nm_, z1, z2 - z1, f):+.1f}%")
        print(f"  [{bname}] " + "; ".join(txt))

    # ---------------------------------------------------------------- non-additivity
    print("\n== Non-additivity of removals: delete the least-loaded strips (by DC load dissipation) all at once")
    o = res["DC"]; bd = o["band"]; I, V = o["I"], o["V"]; si = {s_: m for m, s_ in enumerate(o["srcs"])}
    rho = o["rho"]
    for label, mask in (("plane", cu.layer == 1), ("VOUT pour", (cu.layer == 0) & (cu.net == VOUT))):
        br_ = np.nonzero(bd.active & mask)[0]
        diss = (I[br_, si["load"]] ** 2 * cu.R[br_]).real
        order_ = np.argsort(diss)
        for frac in (0.2, 0.4):
            nsel = int(frac * len(br_))
            B = br_[order_[:nsel]]
            with np.errstate(divide="ignore", invalid="ignore"):
                single = (I[B, si["load"]] ** 2 / bd.y[B]).real
            single = single[np.isfinite(single)].sum()
            act2 = bd.active.copy(); act2[B] = False
            b2 = Band(cu, 0.0, act2, need_cut=False)
            try:
                I2 = b2.solve_inj(injections(cu, o["srcs"])); V2 = b2.Zv(I2)
            except AssertionError:
                print(f"  {label:9s} {int(frac * 100)}% least-loaded ({nsel} strips, {100 * diss[order_[:nsel]].sum() / diss.sum():.2f}%"
                      f" of its load dissipation): removing them together disconnects a terminal;"
                      f" summed single removal costs only +{pct(single, o['Z']['R_load'].real):.3f}%")
                continue
            coll = (V2[:, si["load"]] @ I2[:, si["load"]] - o["Z"]["R_load"]).real
            dzv = (V2[:, si["load"]] @ I2[:, si["victim"]] - o["Z"]["Z_vic<-load"]).real
            print(f"  {label:9s} {int(frac * 100)}% least-loaded ({nsel} strips, {100 * diss[order_[:nsel]].sum() / diss.sum():.2f}% of"
                  f" its load dissipation, mean leverage {rho[B].mean():.2f}): R_load +{pct(coll, o['Z']['R_load'].real):.2f}%"
                  f" collectively vs +{pct(single, o['Z']['R_load'].real):.3f}% summed singly ({coll / single:.1f}x);"
                  f" ADC common-impedance error {pct(dzv, o['Z']['Z_vic<-load'].real):+.1f}%")

    # ---------------------------------------------------------------- the slot as a whole
    print("\n== Reference: the same board without the slot (brute force)")
    cu0 = Copper(top, np.ones((NY, NX), bool), pads, vias)
    for bname, f in BANDS:
        o = res[bname]
        b0 = Band(cu0, f, active_mask(cu0, bname), need_cut=False)
        I0 = b0.solve_inj(injections(cu0, o["srcs"])); V0 = b0.Zv(I0)
        si = {s_: m for m, s_ in enumerate(o["srcs"])}
        part = "real" if f == 0 else "imag"
        txt = []
        for nm_, p_, q_ in budgets_for(bname):
            z0 = V0[:, si[p_]] @ I0[:, si[q_]]
            txt.append(f"{nm_} x{abs(bmetric(nm_, o['Z'][nm_], f)) / abs(bmetric(nm_, z0, f)):.2f}")
        print(f"  [{bname}] slotted / unslotted: " + "; ".join(txt))

    # ---------------------------------------------------------------- SW pour: three jobs, one piece of copper
    print("\n== The switch-node pour: thermal, electric and DC-carry jobs per column (from U1.SW to L1.1)")
    t0 = tic()
    es = electrostatics(cu)
    th = thermal(cu, top, plane, pads, vias, {"U1.SW": 0.4, "U1.GND": 0.4, "U1.VIN": 0.2})
    print(f"  (electrostatics + thermal: {tic() - t0:.1f} s)")
    Qsw, Qw, Qv = es["Qsw"], es["Qworld"], es["Qvic"]
    print(f"  SW node with everything else grounded (homogeneous eps_r = 1): C_SW = {Qsw * 1e12:.3f} pF;"
          f" to world {Qw * 1e12:.3f} pF ({100 * Qw / Qsw:.1f}%); to the victim trace {-Qv * 1e15:.2f} fF")
    tot = {g: v.sum() for g, v in es["part"].items()}
    print("  destination of the SW charge: " + ", ".join(f"{g} {100 * abs(v) / Qsw:.1f}%" for g, v in tot.items()))
    print(f"  T(U1) rise for 1 W: {th['Tu']:.1f} K above ambient")
    S = es["S"]
    sx = XC[cu.nodes[S, 2]]
    # thermal removal cost of the SW copper edges, mapped to columns
    E = th["edges"]
    sw_edge = (E[:, 4] == 0) & (E[:, 3] > 0) & (top[E[:, 5].astype(int), E[:, 6].astype(int)] == SW)
    ex_x = XC[E[:, 6].astype(int)] + np.where(E[:, 7] == 0, D / 2, 0)
    o = res["DC"]; si = {s: m for m, s in enumerate(o["srcs"])}
    swbr = (cu.layer == 0) & (cu.net == SW) & (cu.fam < 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        dR = (o["I"][:, si["load"]] ** 2 / o["band"].y).real
    print("  x column (mm) | world charge share | removal: dC_world (fF)  dC_victim (fF) | dT(U1) (mK) | dR_load (uOhm)")
    for x0 in np.unique(np.round(sx, 2)):
        m = np.abs(sx - x0) < 0.01
        share = es["part"]["world"][m].sum() / Qw
        dw = es["dworld"][m].sum() * 1e15
        dv = -es["dvictim"][m].sum() * 1e15
        me = sw_edge & (ex_x - x0 > -1e-6) & (ex_x - x0 < D / 2 + 1e-6)
        dt = th["dTu"][me].sum() * 1e3
        mr = swbr & (cu.mx - x0 > -1e-6) & (cu.mx - x0 < D / 2 + 1e-6)
        drl = dR[mr][np.isfinite(dR[mr])].sum() * 1e6
        print(f"   {x0:6.2f}      |      {share:6.3f}        |   {dw:+7.2f}         {dv:+7.3f}       |  {dt:+7.1f}    |  {drl:+8.2f}")

    # ---------------------------------------------------------------- leverage sketch on the board itself
    print("\n== Whole-board leverage at DC: exact (cut admittances) vs a Johnson-Lindenstrauss sketch (Spielman-Srivastava)")
    o = res["DC"]; bd = o["band"]
    act = np.nonzero(bd.active)[0]
    g = 1.0 / cu.R[act]
    m_ = len(act)
    Bi = sp.csr_matrix((np.r_[np.ones(m_), -np.ones(m_)], (np.r_[np.arange(m_), np.arange(m_)], np.r_[cu.a[act], cu.b[act]])),
                       shape=(m_, cu.nn))
    Gl = (Bi.T @ sp.diags(g) @ Bi).tocsc()
    roots = np.nonzero(bd.tree[0] < 0)[0]
    keep = np.setdiff1d(np.arange(cu.nn), roots)
    t0 = tic()
    luG = spla.splu(Gl[keep][:, keep].tocsc())
    rho_ex = o["rho"][act]
    rng = np.random.default_rng(3)
    crit = rho_ex > 0.9
    print(f"  {m_} pieces; exact leverage: {np.sum(rho_ex > 0.999)} sole-path pieces (rho = 1), {np.sum(crit)} with rho > 0.9,"
          f" median {np.median(rho_ex):.3f}")
    for k in (24, 96):
        t0 = tic()
        Q = rng.choice([-1.0, 1.0], size=(k, m_)) / math.sqrt(k)
        rhs = (Bi.T @ (np.sqrt(g)[:, None] * Q.T))          # n x k
        Y = np.zeros((cu.nn, k))
        Y[keep] = luG.solve(np.asarray(rhs[keep]))
        est = g * (((Y[cu.a[act]] - Y[cu.b[act]]) ** 2).sum(1))
        tk = tic() - t0
        rel = np.abs(est - rho_ex) / rho_ex
        flag = est > 0.9
        print(f"  k = {k:3d} solves ({tk * 1e3:.0f} ms): median rel. error {np.median(rel):.2f}, 90th pct {np.percentile(rel, 90):.2f};"
              f" pieces with exact rho > 0.9 recovered {np.sum(flag & crit)}/{np.sum(crit)}, false flags {np.sum(flag & ~crit)}")

    # ---------------------------------------------------------------- crack law and leverage sketch
    crack_and_sketch()
    print(f"\nTotal runtime {tic() - T0:.0f} s")


def grid_laplacian(nx, ny, dead=None):
    """Unit-conductance square-grid Laplacian; dead (ny x nx bool) removes nodes. Returns E, B, G."""
    idx = np.arange(nx * ny).reshape(ny, nx)
    dead = np.zeros((ny, nx), bool) if dead is None else dead
    E = []
    for j in range(ny):
        for i in range(nx - 1):
            if not (dead[j, i] or dead[j, i + 1]):
                E.append((idx[j, i], idx[j, i + 1]))
    for j in range(ny - 1):
        for i in range(nx):
            if not (dead[j, i] or dead[j + 1, i]):
                E.append((idx[j, i], idx[j + 1, i]))
    E = np.array(E); m = len(E); n = nx * ny
    B = sp.csr_matrix((np.r_[np.ones(m), -np.ones(m)], (np.r_[np.arange(m), np.arange(m)], np.r_[E[:, 0], E[:, 1]])),
                      shape=(m, n))
    return idx, E, B, (B.T @ B).tocsc()


def crack_and_sketch():
    """(1) Slit cost vs the crack law (pi/4) R_s dpsi^2; (2) JL leverage sketch vs exact on a bigger sheet."""
    print("\n== Uniform sheet (R_s = 1): removal of one strip vs a slit; the crack law (pi/4) R_s (dpsi)^2")
    nx, ny = 121, 91
    idx, E, Bm, G = grid_laplacian(nx, ny)
    n = nx * ny
    keep = np.arange(1, n)
    lu = spla.splu(G[keep][:, keep].tocsc())

    def solve(s_):
        x = np.zeros(n); x[keep] = lu.solve(s_[keep]); return x
    s0 = np.zeros(n); s0[idx[:, 0]] = 1.0 / ny; s0[idx[:, -1]] = -1.0 / ny
    phi = solve(s0)
    ic = nx // 2
    xb = {E[k, 0] // nx: k for k in range(len(E)) if E[k, 0] % nx == ic and E[k, 1] == E[k, 0] + 1}
    for k in (1, 4, 16, 32):
        j0 = ny // 2 - k // 2
        Bset = [xb[j] for j in range(j0, j0 + k)]
        BB = Bm[Bset]
        dV = BB @ phi
        X = np.array([solve(Bm[e].toarray().ravel()) for e in Bset]).T
        RBB = BB @ X
        dR = dV @ np.linalg.solve(np.eye(k) - RBB, dV)            # Woodbury, unit conductances
        first = (dV ** 2).sum()
        dpsi = dV.sum()
        print(f"  slit of {k:2d} strips across the flow: exact +{dR:.3e} = {dR / first:5.2f}x first-order;"
              f" crack law with length (k+1) cells: {math.pi / 4 * ((k + 1) * dpsi / k) ** 2 / dR:5.3f} of exact")
    print("\n== Leverage maps for a whole sheet: exact (one solve per strip) vs a Johnson-Lindenstrauss sketch")
    nx, ny = 161, 121
    slot = np.zeros((ny, nx), bool)
    slot[ny // 2:, nx // 3] = True            # a slot from the top edge to mid-height, like the board's
    idx, E, Bm, G = grid_laplacian(nx, ny, slot)
    m = len(E); n = nx * ny
    deg = np.asarray(G.diagonal())
    live = np.nonzero(deg > 0)[0]
    keep = live[1:]
    t0 = tic()
    lu = spla.splu(G[keep][:, keep].tocsc())
    tf = tic() - t0

    def solve(s):
        x = np.zeros(n); x[keep] = lu.solve(s[keep]); return x
    # JL sketch: R_eff(e) ~ || Q B G^+ b_e ||^2 with Q (k x m) random +-1/sqrt(k)
    rng = np.random.default_rng(7)
    ej, ei = np.divmod(E[:, 0], nx)
    fj, fi = np.divmod(E[:, 1], nx)
    mj, mi = 0.5 * (ej + fj), 0.5 * (ei + fi)
    tipj, tipi = ny // 2 - 1, nx // 3            # last plane row below the slot, slot column
    d_tip = np.hypot(mj - tipj, mi - tipi)
    edge = (np.minimum(np.minimum(mj, ny - 1 - mj), np.minimum(mi, nx - 1 - mi)) < 0.6)
    pick = np.unique(np.r_[np.nonzero(d_tip < 3)[0], rng.choice(np.nonzero(edge)[0], 100, replace=False),
                           rng.choice(m, 300, replace=False)])
    exact = np.empty(len(pick))
    t0 = tic()
    for t, e in enumerate(pick):
        u = np.zeros(n); u[E[e, 0]] = 1; u[E[e, 1]] = -1
        x = solve(u); exact[t] = x[E[e, 0]] - x[E[e, 1]]
    t_exact = (tic() - t0) / len(pick)
    print(f"  sheet {nx} x {ny} nodes ({m} strips), slot from the top edge to mid-height; factor {tf:.2f} s;"
          f" exact leverage = one solve per strip ({t_exact * 1e3:.1f} ms) -> {t_exact * m:.0f} s for all strips")
    tipm, edgem = d_tip[pick] < 3, edge[pick] & (d_tip[pick] >= 3)
    bulk = ~tipm & ~edgem
    print(f"  exact leverage: bulk median {np.median(exact[bulk]):.3f}; free edge median {np.median(exact[edgem]):.3f};"
          f" within 3 cells of the slot tip median {np.median(exact[tipm]):.3f}, max {exact[tipm].max():.3f}")
    hi = exact > 0.6
    for k in (24, 96):
        t0 = tic()
        Q = rng.choice([-1.0, 1.0], size=(k, m)) / math.sqrt(k)
        Y = np.array([solve(Bm.T @ Q[r]) for r in range(k)])   # k x n: rows of Q B G^+
        est_all = ((Y[:, E[:, 0]] - Y[:, E[:, 1]]) ** 2).sum(0)
        tk = tic() - t0
        est = est_all[pick]
        rel = np.abs(est - exact) / exact
        flag = est > 0.6
        print(f"  JL sketch, k = {k:3d} solves: {tk:.1f} s for ALL {m} strips; median rel. error {np.median(rel):.2f}"
              f" (90th pct {np.percentile(rel, 90):.2f}); strips with exact leverage > 0.6 flagged:"
              f" {np.sum(flag & hi)}/{np.sum(hi)}, false flags {np.sum(flag & ~hi)}/{np.sum(~hi)}")


def spearman(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    return np.corrcoef(ra, rb)[0, 1]


if __name__ == "__main__":
    main()
