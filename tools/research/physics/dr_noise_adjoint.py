# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Victim susceptibility map of a schematic from one adjoint solve per frequency.

What it computes
----------------
A 24-bit bridge-sensor ADC front end (sensor legs, cable, RC anti-alias filter
with a 10 % common-mode cap mismatch, ADC input, and a sensor-to-ADC ground
path of 1 mOhm + 5 nH).  Five candidate injection sites stand for the ways a
layout couples noise in:

  ser_gnd   series voltage in the sensor->ADC ground path (shared impedance)
  ser_ainn  series voltage in the AINN trace (magnetic M*di/dt into the loop)
  inj_ainp  current into AINP (C*dv/dt from a switch node)
  inj_midp  current into the filter input node on the P leg
  inj_midn  current into the filter input node on the N leg

The output is the differential ADC input v(ainp) - v(ainn).  The script builds
a modified-nodal-analysis matrix Y(f) and gets every site's transfer function
two ways: directly (one solve per site) and by the adjoint (one transposed
solve, H_k = (Y^-T e_out) . b_k), and checks they agree.  If an `ngspice`
binary is found (env NGSPICE or PATH) it repeats the calculation with ngspice's
.noise analysis, which is itself an adjoint method: each fictitious noise
resistor's output contribution divided by its own noise density is |H_k|.

From |H| it derives the allowed coupling for each site at the converter's
switching frequency, given a budget of 9.3 nV (1 LSB at gain 32) referred to
the ADC input -- before the ADC's digital filter, so it is a conservative,
alias-prone-band number.

Run:  python dr_noise_adjoint.py        (numpy; ngspice optional; < 5 s)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

import numpy as np

K_B, T_K = 1.380649e-23, 300.15

# (name, kind, n1, n2, value)   kind: R C L V(injection, 0 V)
ELEMENTS = [
    ("Rsp", "R", "exc", "sp", 175.0),      # bridge half, P leg (Thevenin)
    ("Rsn", "R", "exc", "sn", 175.0),      # bridge half, N leg
    ("Rbot_p", "R", "sp", "gs", 175.0),
    ("Rbot_n", "R", "sn", "gs", 175.0),
    ("Vexc", "E", "exc", "gs", 0.0),       # excitation, AC-grounded to sensor ground
    ("Rcp", "R", "sp", "mp", 0.05),        # cable/trace resistance
    ("Rcn", "R", "sn", "mn0", 0.05),
    ("ser_ainn", "V", "mn0", "mn", 0.0),   # series injection in the N trace
    ("Rfp", "R", "mp", "ainp", 1000.0),    # anti-alias filter
    ("Rfn", "R", "mn", "ainn", 1000.0),
    ("Cd", "C", "ainp", "ainn", 100e-9),
    ("Ccp", "C", "ainp", "agnd", 1.0e-9),
    ("Ccn", "C", "ainn", "agnd", 1.1e-9),  # 10 % mismatch
    ("Rinp", "R", "ainp", "agnd", 10e6),   # ADC input
    ("Rinn", "R", "ainn", "agnd", 10e6),
    ("Csp", "C", "ainp", "agnd", 10e-12),
    ("Csn", "C", "ainn", "agnd", 10e-12),
    ("Rg", "R", "gs", "g1", 1e-3),         # ground path sensor -> ADC
    ("Lg", "L", "g1", "g2", 5e-9),
    ("ser_gnd", "V", "g2", "agnd", 0.0),   # series injection in the ground path
    ("Ragnd", "R", "agnd", "0", 1e-6),
]
CURRENT_SITES = {"inj_ainp": "ainp", "inj_midp": "mp", "inj_midn": "mn"}
VOLTAGE_SITES = ["ser_gnd", "ser_ainn"]


def build(f):
    nodes = sorted({n for e in ELEMENTS for n in e[2:4]} - {"0"})
    ni = {n: i for i, n in enumerate(nodes)}
    branches = [e[0] for e in ELEMENTS if e[1] in ("L", "V", "E")]
    bi = {b: len(nodes) + i for i, b in enumerate(branches)}
    N = len(nodes) + len(branches)
    Y = np.zeros((N, N), complex)
    w = 2 * np.pi * f

    def stamp(a, b, y):
        for p, q, s in ((a, a, 1), (b, b, 1), (a, b, -1), (b, a, -1)):
            if p != "0" and q != "0":
                Y[ni[p], ni[q]] += s * y

    for name, kind, a, b, val in ELEMENTS:
        if kind == "R":
            stamp(a, b, 1 / val)
        elif kind == "C":
            stamp(a, b, 1j * w * val)
        else:                          # branch element: V, E (0 V) or L
            k = bi[name]
            for node, s in ((a, 1), (b, -1)):
                if node != "0":
                    Y[ni[node], k] += s
                    Y[k, ni[node]] += s
            if kind == "L":
                Y[k, k] = -1j * w * val
    e_out = np.zeros(N)
    e_out[ni["ainp"]], e_out[ni["ainn"]] = 1, -1
    rhs = {}
    for s, node in CURRENT_SITES.items():
        b = np.zeros(N, complex)
        b[ni[node]] = 1.0                 # 1 A injected into the node
        rhs[s] = b
    for s in VOLTAGE_SITES:
        b = np.zeros(N, complex)
        b[bi[s]] = 1.0                    # 1 V in series with the branch
        rhs[s] = b
    return Y, e_out, rhs


def transfer(f):
    Y, e_out, rhs = build(f)
    direct = {s: e_out @ np.linalg.solve(Y, b) for s, b in rhs.items()}
    lam = np.linalg.solve(Y.T, e_out)     # one adjoint solve for all sites
    adjoint = {s: lam @ b for s, b in rhs.items()}
    return direct, adjoint


def ngspice_check(freqs):
    exe = os.environ.get("NGSPICE") or shutil.which("ngspice")
    if not exe:
        return None
    r_ser, r_sh = 1e-3, 1e9
    lines = ["* adjoint check", "Vtest exc gs dc 0 ac 1"]
    for name, kind, a, b, val in ELEMENTS:
        if name == "Vexc":
            continue
        if kind == "V":                    # fictitious series noise resistor
            lines.append(f"R{name} {a} {b} {r_ser}")
        elif kind == "R":
            lines.append(f"{name} {a} {b} {val} noisy=0")
        else:
            lines.append(f"{name} {a} {b} {val}")
    for s, node in CURRENT_SITES.items():
        lines.append(f"R{s} {node} 0 {r_sh}")
    out = tempfile.mkdtemp()
    lines += [f".noise v(ainp,ainn) Vtest lin 1 {freqs[0]} {freqs[0]} 1", ".control"]
    res = {}
    for f in freqs:
        lines += [f"noise v(ainp,ainn) Vtest lin 1 {f} {f} 1", "setplot", "print all"]
    lines += [".endc", ".end"]
    path = os.path.join(out, "c.cir")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    txt = subprocess.run([exe, "-b", path], capture_output=True, text=True, timeout=60).stdout
    fourkt = 4 * K_B * T_K
    for s in CURRENT_SITES:
        vals = [float(v) for v in re.findall(rf"onoise_r{s}\s*=\s*([0-9.eE+-]+)", txt)]
        res[s] = [v / np.sqrt(fourkt / r_sh) for v in vals]
    for s in VOLTAGE_SITES:
        vals = [float(v) for v in re.findall(rf"onoise_r{s.lower()}\s*=\s*([0-9.eE+-]+)", txt)]
        res[s] = [v / np.sqrt(fourkt * r_ser) for v in vals]
    return res


def main():
    freqs = [10.0, 50e3, 500e3, 5e6]
    sites = list(CURRENT_SITES) + VOLTAGE_SITES
    table = {s: [] for s in sites}
    worst = 0.0
    for f in freqs:
        d, a = transfer(f)
        for s in sites:
            worst = max(worst, abs(d[s] - a[s]) / max(abs(d[s]), 1e-30))
            table[s].append(abs(a[s]))
    print("|H| from each injection site to v(ainp)-v(ainn)  (current sites in V/A = ohm, "
          "series sites in V/V)")
    print(f"{'site':>9} " + " ".join(f"{f:>10.0e}Hz" for f in freqs))
    for s in sites:
        print(f"{s:>9} " + " ".join(f"{v:12.3e}" for v in table[s]))
    print(f"adjoint vs direct: max relative difference {worst:.1e}")
    ng = ngspice_check(freqs)
    if ng:
        print("ngspice .noise (adjoint) |H|:")
        for s in sites:
            if ng[s]:
                print(f"{s:>9} " + " ".join(f"{v:12.3e}" for v in ng[s]))
    else:
        print("ngspice not found; skipped the .noise cross-check")
    budget = 9.3e-9
    k = freqs.index(500e3)
    print("\nallowed coupling at 500 kHz for a 9.3 nV (1 LSB, gain 32) input-referred budget,")
    print("aggressor = 12 V switch node (500 kHz fundamental ~ 7.6 V) or a 1 A/ns hot loop:")
    v1 = 12 * 2 / np.pi                    # fundamental of a 12 V square wave (amplitude)
    w = 2 * np.pi * 500e3
    for s in CURRENT_SITES:
        cmax = budget / (table[s][k] * w * v1)
        print(f"  {s:>9}: C_m,max = {cmax*1e15:9.3f} fF")
    i1 = 2 * 2 / np.pi                     # fundamental of the 2 A hot-loop current
    for s in VOLTAGE_SITES:
        mmax = budget / (table[s][k] * w * i1)
        print(f"  {s:>9}: M_max   = {mmax*1e12:9.3f} pH  (fundamental only)")


if __name__ == "__main__":
    main()
