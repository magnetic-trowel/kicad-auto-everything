# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""How fabrication tolerances become impedance tolerance.

Microstrip Z0 from Hammerstad-Jensen with Wheeler's thickness correction;
symmetric stripline from the IPC-2141-style closed form. For a nominal 50 ohm
line it prints the sensitivity (% change in Z0 per % change of w, h, Dk, t)
and a Monte Carlo of Z0 with independent normal variations (3-sigma values
stated), then the fraction of boards inside +/-10 % and +/-5 %.

Inputs (3-sigma): width +/-15 um (etch, after compensation), dielectric
thickness +/-10 % (prepreg flow / core tolerance), Dk +/-0.2, copper
thickness +/-7 um (plating). Change them in main() to model a fab.

Run (numpy, scipy):

    python tools/research/physics/tm_impedance_tolerance.py
"""
import math

import numpy as np
from scipy.optimize import brentq

ETA0 = 376.73


def ms_z0(w, h, er, t):
    """Hammerstad-Jensen microstrip with thickness correction (w, h, t same units)."""
    if t > 0:
        dw1 = t / math.pi * math.log(1 + 4 * math.e / (t / h * (1 / math.tanh(math.sqrt(6.517 * w / h))) ** 2))
        dwr = 0.5 * (1 + 1 / math.cosh(math.sqrt(er - 1))) * dw1
    else:
        dw1 = dwr = 0.0

    def z01(u):
        f = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / u) ** 0.7528)
        return ETA0 / (2 * math.pi) * math.log(f / u + math.sqrt(1 + (2 / u) ** 2))

    def eeff(u):
        a = 1 + math.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49 + math.log(1 + (u / 18.1) ** 3) / 18.7
        b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
        return (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)
    u1 = (w + dw1) / h
    ur = (w + dwr) / h
    e = eeff(ur) * (z01(u1) / z01(ur)) ** 2
    return z01(ur) / math.sqrt(e)


def sl_z0(w, b, er, t):
    """Symmetric stripline, IPC-2141 style: Z = 60/sqrt(er)*ln(1.9*b/(0.8w+t))."""
    return 60 / math.sqrt(er) * math.log(1.9 * b / (0.8 * w + t))


def study(name, zfun, nom, sig3, n=200000, seed=1):
    w0 = brentq(lambda w: zfun(w, nom["h"], nom["er"], nom["t"]) - 50.0, 0.01 * nom["h"], 10 * nom["h"])
    z0 = zfun(w0, nom["h"], nom["er"], nom["t"])
    print(f"{name}: h={nom['h']*1e3:.3f} mm Dk={nom['er']} t={nom['t']*1e6:.0f} um -> w={w0*1e3:.3f} mm for {z0:.1f} ohm")
    base = dict(w=w0, **nom)
    for k in ("w", "h", "er", "t"):
        p = dict(base)
        p[k] *= 1.01
        z = zfun(p["w"], p["h"], p["er"], p["t"])
        print(f"    dZ/Z per 1 % {k:2s}: {100*(z/z0-1):+5.2f} %")
    rng = np.random.default_rng(seed)
    W = w0 + rng.normal(0, sig3["w"] / 3, n)
    H = nom["h"] * (1 + rng.normal(0, sig3["h"] / 3, n))
    E = nom["er"] + rng.normal(0, sig3["er"] / 3, n)
    T = nom["t"] + rng.normal(0, sig3["t"] / 3, n)
    Z = np.array([zfun(*v) for v in zip(W[:20000], H[:20000], E[:20000], T[:20000])])
    sd = Z.std()
    print(f"    MC (3-sigma w +/-{sig3['w']*1e6:.0f} um, h +/-{sig3['h']*100:.0f} %, Dk +/-{sig3['er']}, t +/-{sig3['t']*1e6:.0f} um):"
          f" sigma {sd:.2f} ohm ({100*sd/50:.1f} %), within +/-10 %: {100*np.mean(abs(Z-50)<5):.1f} %,"
          f" within +/-5 %: {100*np.mean(abs(Z-50)<2.5):.1f} %")
    for k in ("w", "h", "er", "t"):
        only = {kk: (sig3[kk] if kk == k else 0.0) for kk in sig3}
        Wk = w0 + rng.normal(0, only["w"] / 3 + 1e-30, 5000)
        Hk = nom["h"] * (1 + rng.normal(0, only["h"] / 3 + 1e-30, 5000))
        Ek = nom["er"] + rng.normal(0, only["er"] / 3 + 1e-30, 5000)
        Tk = nom["t"] + rng.normal(0, only["t"] / 3 + 1e-30, 5000)
        Zk = np.array([zfun(*v) for v in zip(Wk, Hk, Ek, Tk)])
        print(f"      share of variance from {k:2s}: {100*Zk.var()/Z.var():5.1f} %")


if __name__ == "__main__":
    sig3 = dict(w=15e-6, h=0.10, er=0.2, t=7e-6)
    study("Microstrip (L1 over L2, 7628-ish prepreg)", ms_z0, dict(h=0.20e-3, er=4.4, t=45e-6), sig3)
    study("Microstrip (thin 0.1 mm prepreg)", ms_z0, dict(h=0.10e-3, er=4.1, t=45e-6), sig3)
    study("Stripline (b = 0.4 mm between planes)", sl_z0, dict(h=0.40e-3, er=4.2, t=18e-6), sig3)
