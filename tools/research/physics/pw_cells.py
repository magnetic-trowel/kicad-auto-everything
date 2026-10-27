# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Waveform-driven copper objectives for switching cells, plus small closed-form power-layout checks.

Workstream 4 (power). Everything here is closed form or a tiny network solve:

  classify  per-node dv/dt and per-branch di/dt, I_rms, I_dc for a synchronous buck from its
            idealised waveforms; the resulting objective per piece of copper (L, C, R weights)
  width     loss-optimal width of a copper piece over a plane: minimise a L + b C + g R with
            L = mu0 h l / w, C = eps w l / h, R = rho l / (w t)  ->  w* and Z0* = sqrt(b / a)
  emi       switch-node capacitance to the outside world -> common-mode current -> field (Ott)
  sharing   current sharing among N parallel parts on a bus: same-end vs opposite-end
            (Tichelmann / reverse-return) feed, DC (resistive) and HF (inductive)
  ring      commutation-loop ring frequency, Q from copper AC resistance, turn-off loss 1/2 L I^2 f
  thermal   heat vs capacitance through a dielectric: G/C = k/eps (geometry-free exchange rate);
            trace-to-plane conductance vs convection; copper-plane healing length
  shield    thin-sheet eddy-current onset f_c = 1/(pi mu0 sigma t a)

Run:  python pw_cells.py [classify|width|emi|sharing|ring|thermal|shield|all]
Deterministic, numpy only, runs in under a second.
"""
import math
import sys

import numpy as np

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
ER = 4.3
RHO = 1.72e-8
T_CU = 35e-6


def buck_waveforms(vin, vout, iout, fsw, L, t_edge):
    """Idealised synchronous buck: returns dict of node and branch metrics."""
    D = vout / vin
    di = (vin - vout) * D / (fsw * L)
    ipk = iout + di / 2
    irms_L = math.sqrt(iout ** 2 + di ** 2 / 12)
    irms_hs = math.sqrt(D) * irms_L
    irms_ls = math.sqrt(1 - D) * irms_L
    irms_cin = iout * math.sqrt(D * (1 - D))
    irms_cout = di / math.sqrt(12)
    return {
        "nodes": {
            "SW": dict(dvdt=vin / t_edge, swing=vin),
            "VIN": dict(dvdt=0.0, swing=0.0),
            "PGND": dict(dvdt=0.0, swing=0.0),
            "VOUT": dict(dvdt=0.0, swing=di * 0.01),  # ripple only (ESR ~10 mOhm)
            "BOOT": dict(dvdt=vin / t_edge, swing=vin),
            "FB": dict(dvdt=0.0, swing=0.0, sensitive=True),
        },
        "branches": {
            "CIN_HF-HS-LS loop (hot)": dict(didt=ipk / t_edge, irms=irms_cin, idc=0.0),
            "HS FET (VIN->SW)": dict(didt=ipk / t_edge, irms=irms_hs, idc=iout * D),
            "LS FET (SW->PGND)": dict(didt=ipk / t_edge, irms=irms_ls, idc=iout * (1 - D)),
            "SW->L": dict(didt=di * fsw / max(D, 1e-3), irms=irms_L, idc=iout),
            "L->COUT->load": dict(didt=di * fsw / max(D, 1e-3), irms=irms_L, idc=iout),
            "COUT branch": dict(didt=di * fsw / max(D, 1e-3), irms=irms_cout, idc=0.0),
            "gate HS (driver->G->S)": dict(didt=1.0 / 5e-9, irms=0.05, idc=0.0),
            "FB divider": dict(didt=0.0, irms=1e-5, idc=1e-5),
        },
        "D": D, "di": di, "ipk": ipk,
    }


def exp_classify():
    print("== classify: 12 V -> 1.2 V, 10 A, 500 kHz, 1 uH, 2 ns edges (idealised sync buck)")
    w = buck_waveforms(12, 1.2, 10, 5e5, 1e-6, 2e-9)
    print("  nodes: dv/dt (V/ns)  -> objective")
    for n, v in w["nodes"].items():
        obj = ("minimise C to world and to victims (E-field source)" if v["dvdt"] > 1e9 else
               "victim: minimise M and C to aggressors; Kelvin tap" if v.get("sensitive") else
               "quiet: capacitance to local return is free or helpful")
        print(f"    {n:6s} {v['dvdt']/1e9:6.1f}   {obj}")
    print("  branches: di/dt (A/ns)  I_rms (A)  I_dc (A)  -> objective")
    for n, v in w["branches"].items():
        if v["didt"] > 0.5e9:
            obj = "minimise loop L (short, wide, return directly beneath)"
        elif v["irms"] > 1.0:
            obj = "minimise R and temperature (cross-section, pour, many vias)"
        elif v["irms"] < 1e-3:
            obj = "victim: minimise loop area to aggressors, route away"
        else:
            obj = "low priority"
        print(f"    {n:26s} {v['didt']/1e9:7.3f}  {v['irms']:6.2f}  {v['idc']:6.2f}   {obj}")
    print(f"  (D = {w['D']:.2f}, ripple {w['di']:.2f} A p-p, peak {w['ipk']:.1f} A; inductor-branch di/dt is set by L, not by the edges)")


def exp_width():
    print("== width: loss-optimal copper width over a plane at h (per piece of length l)")
    print("   cost = a L + b C + g R; a = I_sw^2 f /2 (W/H), b = V^2 f /2 (W/F), g = I_rms^2 (W/ohm)")
    eps = EPS0 * ER
    cases = [
        ("LV buck SW->L copper (12 V, 10 A, 500 kHz)", 0.0, 0.5 * 144 * 5e5, 100.0, 0.1e-3),
        ("LV buck SW copper inside the hot loop", 0.5 * 10.5 ** 2 * 5e5, 0.5 * 144 * 5e5, 30.0, 0.1e-3),
        ("400 V PFC drain node (2 A rms, 100 kHz), h 0.1 mm", 0.0, 0.5 * 400 ** 2 * 1e5, 4.0, 0.1e-3),
        ("400 V PFC drain node, h 1.5 mm (2-layer)", 0.0, 0.5 * 400 ** 2 * 1e5, 4.0, 1.5e-3),
        ("48 V GaN half-bridge SW (20 A, 1 MHz), h 0.1 mm", 0.5 * 20 ** 2 * 1e6, 0.5 * 48 ** 2 * 1e6, 200.0, 0.1e-3),
    ]
    for name, a, b, g, h in cases:
        # L and R both scale 1/w; C scales w
        num = a * MU0 * h + g * RHO / T_CU
        den = b * eps / h
        wstar = math.sqrt(num / den)
        z0 = math.sqrt(MU0 / eps) * h / wstar
        print(f"  {name:48s}: w* = {wstar*1e3:8.2f} mm (Z0* ~ {z0:6.2f} ohm wide-strip); "
              f"cost split at w*: L {a*MU0*h/wstar:.2e}, R {g*RHO/T_CU/wstar:.2e}, C {b*eps*wstar/h:.2e} W/m")
    print("  pure L-vs-C piece (no R term): Z0* = sqrt(b/a) = V/I of the cell, e.g. 12 V/10 A -> 1.2 ohm, 400 V/2 A -> 200 ohm")


def exp_emi():
    print("== emi: switch-node copper capacitance to the outside world -> common-mode current (order of magnitude)")
    V, fsw, tr = 12.0, 1e6, 2e-9
    for area_mm2 in (10, 25, 100):
        for dworld in (10e-3, 30e-3):
            C = EPS0 * area_mm2 * 1e-6 / dworld
            for f in (30e6, 100e6):
                n = f / fsw
                vn = 2 * V / (math.pi * n) * min(1.0, 1 / (math.pi * f * tr))  # trapezoid envelope
                i = 2 * math.pi * f * C * vn
                E = 1.26e-6 * f * 1.0 * i / 3.0   # Ott CM model: 1 m cable, 3 m
                print(f"  A = {area_mm2:4d} mm2, d = {dworld*1e3:3.0f} mm: C = {C*1e15:6.1f} fF; at {f/1e6:4.0f} MHz"
                      f" I_cm = {i*1e6:6.2f} uA -> {20*math.log10(E/1e-6):5.1f} dBuV/m (class B ~40-43.5)")
    print("  local C to the plane under the SW pad (0.1 mm FR-4): %.0f pF per cm2 -> returns locally, not to the world" % (EPS0 * ER * 1e-4 / 1e-4 * 1e12))


def ladder(Zbus_in, Zbus_out, Zdev, opposite):
    """N devices between an input bus and an output bus (segment impedances), fed at the left of the
    input bus; current leaves the output bus at the left (same end) or at the right (opposite end)."""
    N = len(Zdev)
    # nodes: in_0..in_{N-1}, out_0..out_{N-1}; ground = exit node
    n = 2 * N + 1
    Y = np.zeros((n, n), complex)
    ex = 2 * N
    def add(a, b, z):
        y = 1 / z
        Y[a, a] += y
        Y[b, b] += y
        Y[a, b] -= y
        Y[b, a] -= y
    for k in range(N - 1):
        add(k, k + 1, Zbus_in)
        add(N + k, N + k + 1, Zbus_out)
    for k in range(N):
        add(k, N + k, Zdev[k])
    if opposite:
        add(N + N - 1, ex, Zbus_out)
    else:
        add(N, ex, Zbus_out)
    src = np.zeros(n, complex)
    src[0] = 1.0
    keep = list(range(n - 1))
    v = np.zeros(n, complex)
    v[keep] = np.linalg.solve(Y[np.ix_(keep, keep)], src[keep])
    return np.array([(v[k] - v[N + k]) / Zdev[k] for k in range(N)])


def exp_sharing():
    print("== sharing: 4 parallel parts on 5 mm-pitch buses (3 mm wide, 1 oz, plane 0.1 mm)")
    seg_R = RHO / T_CU * (5 / 3)
    seg_L = MU0 * 0.1e-3 * 5e-3 / 3e-3
    for name, Zdev, Zs in (("DC: MOSFETs 2 mOhm", [2e-3] * 4, seg_R),
                           ("DC: MOSFETs 10 mOhm", [10e-3] * 4, seg_R),
                           ("HF (100 MHz): MLCCs ESL+mount 0.5 nH", [1j * 2 * math.pi * 1e8 * 0.5e-9] * 4, 1j * 2 * math.pi * 1e8 * seg_L)):
        for opp in (False, True):
            I = np.abs(ladder(Zs, Zs, Zdev, opp))
            print(f"  {name:38s} {'opposite-end' if opp else 'same-end    '}: shares {np.round(I / I.sum(), 3)}  max/min {I.max()/I.min():5.2f}")


def exp_ring():
    print("== ring: commutation loop L with C_oss; copper does not damp it")
    for L, C, I, f in ((0.3e-9, 1e-9, 10, 5e5), (1e-9, 1e-9, 10, 5e5), (3e-9, 1e-9, 10, 5e5), (1e-9, 0.3e-9, 20, 1e6)):
        fr = 1 / (2 * math.pi * math.sqrt(L * C))
        z = math.sqrt(L / C)
        # copper AC resistance of a 4 mm x 2 mm overlapped loop at fr: R_s(f) = rho/delta per face, two faces, width 2 mm
        delta = math.sqrt(RHO / (math.pi * fr * MU0))
        Rcu = 2 * (RHO / delta) * (4e-3 / 2e-3)
        print(f"  L {L*1e9:3.1f} nH, Coss {C*1e9:3.1f} nF: f_ring {fr/1e6:5.0f} MHz, Z0 {z:5.2f} ohm,"
              f" R_cu {Rcu*1e3:4.1f} mOhm -> Q_cu {z/Rcu:5.0f}; overshoot ~ I Z0 = {I*z:5.1f} V;"
              f" 1/2 L I^2 f = {0.5*L*I*I*f*1e3:5.1f} mW; RC snubber R ~ Z0, C ~ 3-4 Coss")


def exp_thermal():
    print("== thermal: heat through a dielectric costs capacitance at a fixed exchange rate G/C = k/eps")
    for name, k, er in (("FR-4", 0.3, 4.3), ("thermal prepreg (~1 W/mK)", 1.0, 4.5), ("thermal prepreg (~3 W/mK)", 3.0, 5.0),
                        ("IMS dielectric (~2 W/mK)", 2.0, 6.0), ("AlN ceramic", 170.0, 8.8)):
        ratio = k / (EPS0 * er)
        # at 0.1 mm: per cm2
        G = k * 1e-4 / 1e-4
        C = EPS0 * er * 1e-4 / 1e-4
        print(f"  {name:28s}: G/C = {ratio:9.2e} (W/K)/F; at 0.1 mm per cm2: {G:6.2f} W/K and {C*1e12:5.1f} pF")
    print("  trace 1 mm wide over a plane 0.1 mm away: G' = k w/h = %.1f W/(m K) vs convection 10 W/m2K x 2 mm = %.2f W/(m K)"
          % (0.3 * 1e-3 / 1e-4, 10 * 2e-3))
    for t_oz, t in ((1, 35e-6), (2, 70e-6)):
        for g in (10.0, 20.0):
            lam = math.sqrt(390 * t / g)
            print(f"  healing length of a {t_oz} oz copper plane with {g:.0f} W/m2K total to ambient: {lam*1e3:5.1f} mm")


def exp_shield():
    print("== shield: a copper sheet starts mirroring a loop of size a above f_c = 1/(pi mu0 sigma t a)")
    sig = 1 / RHO
    for t in (18e-6, 35e-6, 70e-6):
        print("  t = %2.0f um: " % (t * 1e6) + ", ".join(f"a = {a*1e3:.0f} mm: {1/(math.pi*MU0*sig*t*a)/1e3:6.1f} kHz" for a in (1e-3, 3e-3, 10e-3)))


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    exps = {"classify": exp_classify, "width": exp_width, "emi": exp_emi, "sharing": exp_sharing,
            "ring": exp_ring, "thermal": exp_thermal, "shield": exp_shield}
    for k, f in exps.items():
        if which in (k, "all"):
            f()
