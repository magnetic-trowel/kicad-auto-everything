# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""How many filaments through the copper does kae.em need? Skin and proximity loss vs nsub.

kae.em splits each bar through its thickness into `nsub` filaments (Chebyshev spacing, kae.em.mesh.Layer).
The default nsub = 2 gives two equal halves. This script solves three canonical structures at
nsub = 1, 2, 3, 4, 6, 8 (8 is the reference) and 1-200 MHz, and compares:

  closed   the 1-D slab: a conductor of thickness t with its field on one side (a trace over its plane,
           the plane under its trace), exact R/R_dc = Re[(1+j) D coth((1+j) D)], D = t/delta (Dowell m = 1);
           and the same slab cut into n Chebyshev filaments (the discrete limit of each nsub).
  solver   the port R(f), L(f) of
             decap    an IC supply pad, a trace to a 0402 capacitor (an ideal short) and a via back to the
                      plane: trace length 1/3/6 mm, plane depth h 0.1/0.2 mm
             hotloop  a buck hot loop on the top layer (input capacitor, high-side and low-side switch
                      footprints, 1.5 mm or 0.6 mm wide copper) over its ground plane at h 0.1/0.2/0.4 mm
             planes   a power/ground plane pair 20 x 20 mm, h 0.1/0.2 mm, a port via pair and a decap short
                      6 or 14 mm away
             coplanar go and return side by side on one layer, no plane (two-sided crowding)
  ring     each hot loop with C_oss 1 or 4 nF and the cell stand-in's 0.05 Ohm: the ring frequency, its Q
           (copper + 0.05 Ohm) and the ring-band peak, which scales with Q, per nsub
  rank     whether the order of the variants (by R at each f, by L, by ring Q) changes with nsub
  fix      the surface-impedance correction: each conductor's filament R scaled by
           k_n(f) = F(D) / F_n(D) (the closed slab over its n-filament limit), applied to the whole port R

Run:  OMP_NUM_THREADS=4 python tools/research/physics/em_skin_nsub_check.py [-o out.json]
Minutes on 4 cores at pitch 0.25 mm.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time

import numpy as np
from shapely.geometry import Point, box

from kae.em import solve as S
from kae.em.mesh import SIGMA_CU, Layer, Mesh

MU0 = 4e-7 * math.pi
T_CU = 0.035
FREQS = [1e6, 3e6, 10e6, 30e6, 100e6, 200e6]
NSUBS = [1, 2, 3, 4, 6, 8]


def delta(f, sigma=SIGMA_CU):
    return math.sqrt(2 / (2 * math.pi * f * MU0 * sigma))


def slab_exact(f, t=T_CU * 1e-3):
    """R/R_dc of a slab with its field on one side."""
    D = t / delta(f)
    g = (1 + 1j) * D
    return float((g / np.tanh(g)).real)


def slab_filaments(f, n, t=T_CU * 1e-3, fine=4000):
    """R/R_dc of the same slab cut into n Chebyshev filaments (kae.em.mesh.Layer.subs), each carrying a
    uniform current: the partial flux of filament k is the mean over k of the flux between the field-side
    face (z = 0, toward the return) and z, from every filament's uniform current."""
    e = (1 - np.cos(np.pi * np.arange(n + 1) / n)) / 2 * t
    z = (np.arange(fine) + 0.5) / fine * t                       # z = 0: the face toward the field
    dz = t / fine
    # H(z) from filament m carrying unit sheet current, field-free at z = t: 1 below it, linear inside, 0 above
    H = np.zeros((n, fine))
    for m in range(n):
        a, b = e[m], e[m + 1]
        H[m] = np.where(z < a, 1.0, np.where(z > b, 0.0, (b - z) / (b - a)))
    # flux between the field-side face and z per unit length, per unit current of m (a filament deeper
    # from the return links more of it: the current crowds toward the return)
    Phi = MU0 * (np.cumsum(H, 1) - H / 2) * dz                    # (n, fine)
    L = np.zeros((n, n))
    for k in range(n):
        sel = (z >= e[k]) & (z < e[k + 1])
        L[k] = Phi[:, sel].mean(1)
    L = (L + L.T) / 2
    w = 2 * math.pi * f
    Rk = 1 / (SIGMA_CU * np.diff(e))                             # per square
    Z = np.diag(Rk) + 1j * w * L
    # common voltage V: Z K = V 1, sum K = 1
    y = np.linalg.solve(Z, np.ones(n))
    K = y / y.sum()
    return float(np.sum(Rk * np.abs(K) ** 2) * SIGMA_CU * t)


def layers(h, nsub):
    return [Layer("T", h + T_CU, T_CU, nsub), Layer("G", 0.0, T_CU, nsub)]


def decap(nsub, pitch, lt=3.0, h=0.2, w=0.3):
    """IC VCC pad -> trace -> 0402 capacitor (ideal) -> pad with a via -> plane -> via -> IC GND pad."""
    x1 = 1.0 + lt
    m = Mesh.over(-1, -2, x1 + 3.5, 3, pitch, layers(h, nsub))
    m.rect(1, "GND", -1, -2, x1 + 3.5, 3)
    m.rect(0, "VCC", 0.5, -0.3, 1.0, 0.3)                         # IC supply pad
    m.rect(0, "GND", 0.5, 0.7, 1.0, 1.3)                          # IC ground pad
    m.rect(0, "VCC", 1.0, -w / 2, x1, w / 2)                      # trace
    m.rect(0, "VCC", x1, -0.3, x1 + 0.5, 0.3)                     # capacitor pads, 1 mm pitch
    m.rect(0, "GND", x1 + 1.0, -0.3, x1 + 1.5, 0.3)
    m.via(0.75, 1.0, [0, 1], "GND", drill=0.3)
    m.via(x1 + 1.25, 0.0, [0, 1], "GND", drill=0.3)
    m.terminal("icv", 0, geom=box(0.5, -0.3, 1.0, 0.3), net="VCC")
    m.terminal("icg", 0, geom=box(0.5, 0.7, 1.0, 1.3), net="GND")
    m.terminal("ca", 0, geom=box(x1, -0.3, x1 + 0.5, 0.3), net="VCC")
    m.terminal("cb", 0, geom=box(x1 + 1.0, -0.3, x1 + 1.5, 0.3), net="GND")
    m.part("ca", "cb")
    m.port("p", "icv", "icg")
    return m


def hotloop(nsub, pitch, h=0.1, w=1.5):
    """VIN (top) from the input capacitor to the high-side drain; SW from the high-side source to the
    low-side drain; GND from the low-side source back to the capacitor, with vias to the plane under it.
    The port is the high-side switch; capacitor and low side are ideal shorts."""
    m = Mesh.over(-1, -4, 9, 4, pitch, layers(h, nsub))
    m.rect(1, "GND", -1, -4, 9, 4)
    m.rect(0, "VIN", 1.0, 0.4, 7.0, 0.4 + w)
    m.rect(0, "GND", 1.0, -0.4 - w, 3.4, -0.4)
    m.rect(0, "SW", 4.0, -0.4 - w, 7.0, -0.4)
    for x in (1.4, 2.2, 3.0):
        m.via(x, -0.4 - w / 2, [0, 1], "GND", drill=0.3)
    m.terminal("cin_p", 0, geom=box(1.0, 0.4, 2.0, 0.4 + w), net="VIN")
    m.terminal("cin_n", 0, geom=box(1.0, -0.4 - w, 2.0, -0.4), net="GND")
    m.terminal("hs_d", 0, geom=box(6.0, 0.4, 7.0, 0.4 + w), net="VIN")
    m.terminal("hs_s", 0, geom=box(6.0, -0.4 - w, 7.0, -0.4), net="SW")
    m.terminal("ls_s", 0, geom=box(2.6, -0.4 - w, 3.4, -0.4), net="GND")
    m.terminal("ls_d", 0, geom=box(4.0, -0.4 - w, 4.8, -0.4), net="SW")
    m.part("cin_p", "cin_n")
    m.part("ls_s", "ls_d")
    m.port("p", "hs_d", "hs_s")
    return m


def planes(nsub, pitch, h=0.1, d=14.0):
    """A plane pair; the port at (3, 10) between the planes, a decap (ideal short) d mm away."""
    m = Mesh.over(0, 0, 20, 20, pitch, [Layer("P", h + T_CU, T_CU, nsub), Layer("G", 0.0, T_CU, nsub)])
    m.rect(0, "PWR", 0, 0, 20, 20)
    m.rect(1, "GND", 0, 0, 20, 20)
    for nm, x in (("a", 3.0), ("b", 3.0 + d)):
        g = Point(x, 10.0).buffer(0.3)
        m.terminal(nm + "p", 0, geom=g, net="PWR")
        m.terminal(nm + "g", 1, geom=g, net="GND")
    m.part("bp", "bg")
    m.port("p", "ap", "ag")
    return m


def coplanar(nsub, pitch, w=1.0, gap=0.5):
    """Go and return side by side on one layer, no plane, 10 mm, shorted at the far end: each trace's field
    is two-sided (the crowding the one-sided slab correction does not describe)."""
    m = Mesh.over(-1, -3, 12, 3, pitch, [Layer("T", 0.0, T_CU, nsub)])
    y0 = gap / 2
    m.rect(0, "A", 0, y0, 10, y0 + w)
    m.rect(0, "B", 0, -y0 - w, 10, -y0)
    m.terminal("a", 0, geom=box(0, y0, 0.5, y0 + w), net="A")
    m.terminal("b", 0, geom=box(0, -y0 - w, 0.5, -y0), net="B")
    m.terminal("ae", 0, geom=box(9.5, y0, 10, y0 + w), net="A")
    m.terminal("be", 0, geom=box(9.5, -y0 - w, 10, -y0), net="B")
    m.part("ae", "be")                                       # the far-end short
    m.port("p", "a", "b")
    return m


CASES = {
    "decap": [dict(lt=lt, h=h) for h in (0.1, 0.2) for lt in (1.0, 3.0, 6.0)],
    "hotloop": [dict(h=h, w=w) for h in (0.1, 0.2, 0.4) for w in (1.5, 0.6)],
    "planes": [dict(h=h, d=d) for h in (0.1, 0.2) for d in (6.0, 14.0)],
    "coplanar": [dict(w=w, gap=g) for w in (0.5, 1.5) for g in (0.25, 1.0)],
}
BUILD = dict(decap=decap, hotloop=hotloop, planes=planes, coplanar=coplanar)


def run_case(name, kw, nsub, pitch):
    m = BUILD[name](nsub, pitch, **kw)
    t0 = time.time()
    r = S.solve(m, [0.0] + FREQS, tol=1e-9, maxiter=2000)
    return dict(R=[float(x) for x in r["R"][:, 0, 0]], L=[float(x) if np.isfinite(x) else None for x in r["L"][:, 0, 0]],
                iters=[int(x) for x in r["iters"]], seconds=round(time.time() - t0, 2), stats=r["stats"])


def rank_flips(vals):
    """Pairs of variants whose order differs from the reference nsub's (vals: {nsub: [value per variant]})."""
    ref = vals[max(vals)]
    out = {}
    for n, v in vals.items():
        flips = 0
        for a in range(len(v)):
            for b in range(a + 1, len(v)):
                if (v[a] - v[b]) * (ref[a] - ref[b]) < 0:
                    flips += 1
        out[n] = flips
    return out


R_EXT = 0.05                 # Ohm: the cell stand-in's switch resistance (kae.circuit autotb, functional-evaluator.md)
C_OSS = (1e-9, 4e-9)


def _interp(f, fs, ys):
    return float(np.interp(math.log(f), [math.log(x) for x in fs], ys))


def ring(r, C):
    """(f_r, Q with R_EXT, Q of the copper alone) of a loop with port R(f), L(f) closed by C."""
    fs, R, L = FREQS, r["R"][1:], r["L"][1:]
    fr = 1 / (2 * math.pi * math.sqrt(L[-1] * C))
    for _ in range(20):                                       # L falls with f: iterate the crossing
        fr = 1 / (2 * math.pi * math.sqrt(_interp(fr, fs, L) * C))
    fr = min(max(fr, fs[0]), fs[-1])
    Lr, Rr = _interp(fr, fs, L), _interp(fr, fs, R)
    w = 2 * math.pi * fr
    return fr, w * Lr / (Rr + R_EXT), w * Lr / Rr


def report(out):
    """Tables from a results dict (main's -o)."""
    nsubs, ref = out["nsubs"], max(out["nsubs"])
    fs = out["freqs"]
    print("\n== R(f) / R(f, nsub=%d) and L(f) / L(f, nsub=%d), worst over each case's variants" % (ref, ref))
    for name, res in out["cases"].items():
        for n in nsubs:
            rr = [min(v[str(n)]["R"][k + 1] / v[str(ref)]["R"][k + 1] for v in res.values()) for k in range(len(fs))]
            lr = [max(abs(v[str(n)]["L"][k + 1] / v[str(ref)]["L"][k + 1] - 1) for v in res.values()) for k in range(len(fs))]
            sec = max(v[str(n)]["seconds"] for v in res.values()) / max(v[str(ref)]["seconds"] for v in res.values())
            print(f"{name:8s} nsub={n}: R " + " ".join(f"{x:5.2f}" for x in rr) + "   |dL| " +
                  " ".join(f"{x:5.1%}" for x in lr) + f"   time x{sec:.2f} of nsub={ref}")
        # the surface-impedance correction applied to nsub=2: R * F(D) / F_2(D)
        k = [slab_exact(f) / slab_filaments(f, 2) for f in fs]
        rc = [min(v["2"]["R"][q + 1] * k[q] / v[str(ref)]["R"][q + 1] for v in res.values()) for q in range(len(fs))]
        rc_hi = [max(v["2"]["R"][q + 1] * k[q] / v[str(ref)]["R"][q + 1] for v in res.values()) for q in range(len(fs))]
        print(f"{name:8s} nsub=2 x F/F_2: R " + " ".join(f"{a:4.2f}-{b:4.2f}" for a, b in zip(rc, rc_hi)))
        # rank flips by R at 100 MHz and by L at 10 MHz
        k100, k10 = fs.index(100e6) + 1, fs.index(10e6) + 1
        for lab, key, kk in (("R@100MHz", "R", k100), ("L@10MHz", "L", k10)):
            vals = {n: [v[str(n)][key][kk] for v in res.values()] for n in nsubs}
            print(f"{name:8s} rank flips by {lab} vs nsub={ref}: {rank_flips(vals)}")
    if "hotloop" in out["cases"]:
        res = out["cases"]["hotloop"]
        for C in C_OSS:
            print(f"\n== hot loop ring with C_oss {C * 1e12:g} pF and {R_EXT} Ohm: f_r MHz, Q, Q copper alone")
            qs = {}
            for key, v in res.items():
                row = []
                for n in nsubs:
                    fr, q, qc = ring(v[str(n)], C)
                    qs.setdefault(n, []).append(q)
                    row.append(f"n={n}: {fr / 1e6:5.0f} {q:5.1f} {qc:6.1f}")
                print(f"{key:14s} " + " | ".join(row))
            print("rank flips by Q vs nsub=%d: %s; ring-band peak (prop. Q) over nsub=%d: %s" % (
                ref, rank_flips(qs), ref, {n: f"{min(a / b for a, b in zip(qs[n], qs[ref])):.2f}-{max(a / b for a, b in zip(qs[n], qs[ref])):.2f}"
                                           for n in nsubs}))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pitch", type=float, default=0.25)
    ap.add_argument("--nsubs", default=",".join(map(str, NSUBS)))
    ap.add_argument("--cases", default="decap,hotloop,planes")
    ap.add_argument("-o")
    ap.add_argument("--report", nargs="+", help="print the tables of earlier -o results (merged) instead of solving")
    a = ap.parse_args(argv)
    if a.report:
        out = None
        for fn in a.report:
            r = json.load(open(fn))
            out = r if out is None else (out["cases"].update(r["cases"]) or out)
        report(out)
        return
    nsubs = [int(x) for x in a.nsubs.split(",")]
    out = dict(pitch=a.pitch, freqs=FREQS, nsubs=nsubs, slab={}, cases={})
    print("== slab: R/R_dc, one-sided field, 35 um copper")
    print("f MHz   delta um  exact  " + "  ".join(f"n={n}" for n in nsubs))
    for f in FREQS:
        ex = slab_exact(f)
        fl = [slab_filaments(f, n) for n in nsubs]
        out["slab"][f] = dict(exact=ex, filaments=dict(zip(nsubs, fl)))
        print(f"{f / 1e6:6.0f}  {delta(f) * 1e6:7.2f}  {ex:5.2f}  " + "  ".join(f"{x:4.2f}" for x in fl))
    for name in a.cases.split(","):
        res = {}
        for kw in CASES[name]:
            key = ",".join(f"{k}={v}" for k, v in kw.items())
            res[key] = {}
            for n in nsubs:
                r = run_case(name, kw, n, a.pitch)
                res[key][n] = r
                print(f"{name} {key} nsub={n}: {r['seconds']}s iters {r['iters']} "
                      f"R mOhm {[round(x * 1e3, 3) for x in r['R']]} L nH {[round(x * 1e9, 4) if x else None for x in r['L']]}",
                      flush=True)
        out["cases"][name] = res
    if a.o:
        json.dump(out, open(a.o, "w"), indent=1, default=str)
    report(json.loads(json.dumps(out, default=str)))


if __name__ == "__main__":
    main()
