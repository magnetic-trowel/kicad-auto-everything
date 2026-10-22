# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Closed-form numbers behind the [C] tags in docs/topics/physics/vocabulary.md
and docs/topics/physics/physics-ir-examples.md.

Sections (each prints its inputs and results):
  general   skin depth, microstrip L'/C'/Z0/delay (Hammerstad), critical length,
            trapezoid spectrum envelope
  halo      magnetic coupling between two small coplanar loops vs distance,
            in free space and over a perfectly conducting plane at depth h
            (image method): the plane turns a dipole into a near-quadrupole
  buck      12 V -> 3.3 V, 3 A: di/dt, dv/dt, SW-node displacement current,
            FB edge pickup bound, IR drop
  usb3      Gen1 channel loss spend (Bogatin-style dB/in rules), skew -> CM
  xtal      pullability ppm/pF, stray-C budget, trace-length budget
  adc       24-bit LSB, thermal EMF, common impedance, leakage, 50 Hz pickup
  rf        2.45 GHz wavelengths, reactances, pad capacitance, SMPS harmonic
  motor     48 V half-bridge: ring frequency, common-source and shunt numbers,
            heatsink-tab displacement current

All inputs are illustrative design points, stated in the output; the docs say
which ones are assumptions. Deterministic, standard library only:
    python vo_numbers.py [section ...]
"""
import math
import sys

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
C0 = 299792458.0
RHO_CU = 1.72e-8


def microstrip(w, h, er):
    """Hammerstad-Jensen (zero thickness). Returns Z0, eps_eff, L'(H/m), C'(F/m), t_pd(s/m)."""
    u = w / h
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / u) ** -0.5
    if u < 1:
        ee += (er - 1) / 2 * 0.04 * (1 - u) ** 2
        z0 = 60 / math.sqrt(ee) * math.log(8 / u + u / 4)
    else:
        z0 = 120 * math.pi / (math.sqrt(ee) * (u + 1.393 + 0.667 * math.log(u + 1.444)))
    tpd = math.sqrt(ee) / C0
    return z0, ee, z0 * tpd, tpd / z0, tpd


def trapezoid_env_db(f, f0, duty, tr):
    """Envelope of a trapezoid's harmonic amplitudes relative to 2*A*duty (dB)."""
    env = 1.0
    f1 = 1 / (math.pi * duty / f0)  # 1/(pi*tau)
    f2 = 1 / (math.pi * tr)
    if f > f1:
        env *= f1 / f
    if f > f2:
        env *= f2 / f
    return 20 * math.log10(env)


def general():
    print("== general")
    f35 = RHO_CU / (math.pi * MU0 * (35e-6) ** 2)
    print("skin depth = 35 um (1 oz) at f = %.2f MHz" % (f35 / 1e6))
    for w, h in ((0.2e-3, 0.1e-3), (0.35e-3, 0.2e-3)):
        z0, ee, lp, cp, tpd = microstrip(w, h, 4.3)
        print("microstrip w=%.2f h=%.2f mm: Z0=%.1f ohm eeff=%.2f L'=%.3f nH/mm C'=%.3f pF/mm t_pd=%.2f ps/mm"
              % (w * 1e3, h * 1e3, z0, ee, lp * 1e6, cp * 1e9, tpd * 1e9))
    tpd = microstrip(0.35e-3, 0.2e-3, 4.3)[4]
    for tr in (1e-9, 100e-12):
        print("t_r=%.0f ps: t_r/6 critical length = %.1f mm" % (tr * 1e12, tr / 6 / tpd * 1e3))
    print("trapezoid 12 V, 1 MHz, D=0.275, t_r=2 ns: knee1=%.2f MHz knee2=%.0f MHz; envelope at 2.45 GHz = %.1f dB re 2*A*D"
          % (1e6 / (math.pi * 0.275) / 1e6, 1 / (math.pi * 2e-9) / 1e6, trapezoid_env_db(2.45e9, 1e6, 0.275, 2e-9)))


def bz_dipole(m, dx, dz):
    """B_z at offset (dx, dz) from a z-directed magnetic dipole m (A m^2)."""
    r = math.hypot(dx, dz)
    cos = dz / r
    return MU0 * m / (4 * math.pi) * (3 * cos * cos - 1) / r ** 3


def halo():
    print("== halo: coplanar loops, source A1=20 mm^2 (1 A), victim A2=10 mm^2")
    a1, a2 = 20e-6, 10e-6
    print("  r mm   M free(pH)  M over plane h=1.6mm  h=0.1mm   (pH)")
    for r in (5e-3, 10e-3, 20e-3, 40e-3):
        mfree = abs(bz_dipole(a1, r, 0)) * a2
        row = []
        for h in (1.6e-3, 0.1e-3):
            b = bz_dipole(a1, r, 0) + bz_dipole(-a1, r, 2 * h)  # image at depth 2h, sign reversed
            row.append(abs(b) * a2)
        print("  %4.0f   %9.3f   %9.4f   %12.6f" % (r * 1e3, mfree * 1e12, row[0] * 1e12, row[1] * 1e12))
    print("  (point-dipole approximation; valid for r >> loop size and above the plane's R/L regime boundary)")


def buck():
    print("== buck: 12 V -> 3.3 V, 3 A, 1 MHz, SW edge 2 ns")
    vin, iout, tr = 12.0, 3.0, 2e-9
    didt, dvdt = iout / tr, vin / tr
    print("di/dt = %.1f A/ns, dv/dt = %.1f V/ns, L*di/dt for 1 nH = %.1f V (first-order, see dr_switch_cell_budget.py for the LC regime)"
          % (didt / 1e9, dvdt / 1e9, 1e-9 * didt))
    a, d = 20e-6, 0.1e-3
    csw = EPS0 * 4.3 * a / d
    print("SW pour 20 mm^2 over plane 0.1 mm: C=%.1f pF, displacement current C*dv/dt=%.0f mA" % (csw * 1e12, csw * dvdt * 1e3))
    for dd in (0.5e-3, 1.0e-3, 2.0e-3):
        k = 1 / (1 + (dd / 0.1e-3) ** 2)
        print("FB trace parallel to SW at D=%.1f mm, H=0.1 mm: K=%.4f -> edge pickup bound %.0f mV (fully parallel)"
              % (dd * 1e3, k, k * vin * 1e3))
    r = RHO_CU * 20e-3 / (1e-3 * 35e-6)
    print("3 A over 20 mm x 1 mm x 35 um: R=%.1f mOhm, drop=%.0f mV, P=%.0f mW; as 5 mm pour: %.1f mOhm"
          % (r * 1e3, r * iout * 1e3, r * iout ** 2 * 1e3, r / 5 * 1e3))


def usb3():
    print("== usb3 Gen1: 5 Gb/s, Nyquist 2.5 GHz, FR-4 Df 0.02, 5 mil traces, 85-90 ohm diff")
    f, df, dk, wmil, z0 = 2.5, 0.02, 3.3, 5.0, 45.0
    a_d = 2.3 * f * df * math.sqrt(dk)
    a_c = 36 / (wmil * z0) * math.sqrt(f)
    per_in = a_d + a_c
    print("dielectric %.3f + conductor %.3f = %.3f dB/in (%.4f dB/mm)" % (a_d, a_c, per_in, per_in / 25.4))
    budget = 5.5
    fixed = {"2 vias (~1 in each)": 2 * per_in, "ESD+CMC (~1 in)": per_in, "AC caps + receptacle [I]": 0.5}
    spent = sum(fixed.values())
    for k, v in fixed.items():
        print("  spend %-26s %.2f dB" % (k, v))
    print("  remaining for trace: %.2f dB -> %.0f mm of routing" % (budget - spent, (budget - spent) / per_in * 25.4))
    tpd = math.sqrt(dk) / C0
    skew = 0.127e-3 * tpd
    tr = 60e-12
    print("5 mil intra-pair skew = %.2f ps; CM spike ~ 0.5*V_leg*skew/t_r = %.1f mV (V_leg 0.5 V, t_r 60 ps)"
          % (skew * 1e12, 0.5 * 0.5 * skew / tr * 1e3))


def xtal():
    print("== xtal: 32 MHz, C1=5 fF, C0=1.5 pF, CL=8 pF")
    c1, c0, cl = 5e-15, 1.5e-12, 8e-12
    s = c1 / (2 * (c0 + cl) ** 2)
    print("pullability S = C1/(2(C0+CL)^2) = %.1f ppm/pF" % (s * 1e6 / 1e12))
    total, tol, temp, age = 40, 10, 10, 3
    left = total - tol - temp - age
    print("+-%d ppm total - %d tol - %d temp - %d aging = +-%d ppm -> stray-C uncertainty +-%.2f pF"
          % (total, tol, temp, age, left, left / (s * 1e6 / 1e12)))
    cp = microstrip(0.15e-3, 0.1e-3, 4.3)[3]
    print("0.15 mm trace over 0.1 mm: C'=%.3f pF/mm -> 0.3 pF of trace = %.1f mm" % (cp * 1e9, 0.3e-12 / cp * 1e3))
    print("XOUT 1 Vpp sine at 32 MHz: peak dv/dt = %.2f V/ns" % (math.pi * 32e6 * 1.0 / 1e9))


def adc():
    print("== adc: 24 bit, +-2.5 V span (5 V)")
    lsb = 5.0 / 2 ** 24
    print("LSB = %.0f nV" % (lsb * 1e9))
    for s in (1e-6, 3e-6, 40e-6):
        print("thermal EMF %.0f uV/C x 0.1 C = %.2f uV" % (s * 1e6, s * 0.1 * 1e6))
    v, i = 0.3e-6, 20e-3
    rmax = v / i
    rsq = RHO_CU / 35e-6
    print("common impedance: 0.3 uV / 20 mA -> R_shared <= %.0f uOhm = %.3f squares of 1 oz copper (%.2f mOhm/sq)"
          % (rmax * 1e6, rmax / rsq, rsq * 1e3))
    print("leakage: 5 V across 10 GOhm into a 10 kOhm node = %.1f uV" % (5 * 10e3 / 10e9 * 1e6))
    b = MU0 * 1.0 / (2 * math.pi * 10e-3)
    print("50 Hz, 1 A conductor at 10 mm: B=%.0f uT; EMF in 1 cm^2 loop = %.2f uV" % (b * 1e6, 2 * math.pi * 50 * b * 1e-4 * 1e6))


def rf():
    print("== rf: 2.45 GHz feed")
    f = 2.45e9
    lam0 = C0 / f
    z0, ee, lp, cp, tpd = microstrip(0.35e-3, 0.2e-3, 4.3)
    lamg = lam0 / math.sqrt(ee)
    print("lambda0=%.1f mm, eeff=%.2f (w=0.35, h=0.2 mm, Z0=%.0f), lambda_g=%.1f mm, lambda_g/20=%.2f mm, lambda_g/10=%.1f mm"
          % (lam0 * 1e3, ee, z0, lamg * 1e3, lamg / 20 * 1e3, lamg / 10 * 1e3))
    print("X(1 nH)=%.1f ohm, X(0.2 pF)=%.0f ohm" % (2 * math.pi * f * 1e-9, 1 / (2 * math.pi * f * 0.2e-12)))
    cpad = EPS0 * 4.3 * 0.5e-3 * 0.6e-3 / 0.1e-3
    x = 1 / (2 * math.pi * f * cpad)
    y = 50 / x  # normalised shunt susceptance on a matched 50 ohm line: |G| = y / sqrt(4 + y^2)
    gamma = y / math.hypot(2, y)
    print("0402 pad 0.5x0.6 mm over plane 0.1 mm: C=%.3f pF, X=%.0f ohm, |S11| alone ~ %.1f dB"
          % (cpad * 1e12, x, 20 * math.log10(gamma)))
    print("SMPS 12 V/1 MHz/2 ns envelope at 2.45 GHz: %.0f dB below 2*A*D" % -trapezoid_env_db(f, 1e6, 0.275, 2e-9))


def motor():
    print("== motor: 48 V half-bridge, 20 A, t_sw 15 ns")
    v, i, t = 48.0, 20.0, 15e-9
    didt, dvdt = i / t, v / t
    print("di/dt=%.2f A/ns dv/dt=%.1f V/ns" % (didt / 1e9, dvdt / 1e9))
    for l in (5e-9, 10e-9):
        print("L=%.0f nH with Coss=700 pF: ring %.0f MHz, L*di/dt=%.1f V" % (l * 1e9, 1 / (2 * math.pi * math.sqrt(l * 700e-12)) / 1e6, l * didt))
    print("common-source 1 nH: %.2f V against the gate" % (1e-9 * didt))
    rs = 1e-3
    print("shunt 1 mOhm: %.0f mV signal, %.2f W; 0.1 mOhm of pad/solder in path = %.0f%% error" % (rs * i * 1e3, rs * i * i, 10))
    print("shunt ESL 0.3 nH: %.0f mV spike; sense-loop M 0.1 nH: %.0f mV" % (0.3e-9 * didt * 1e3, 0.1e-9 * didt * 1e3))
    ctab = EPS0 * 4.5 * 150e-6 / 0.23e-3
    print("TO-220 tab 150 mm^2 on 0.23 mm pad (er 4.5): C=%.0f pF, C*dv/dt=%.0f mA into heatsink" % (ctab * 1e12, ctab * dvdt * 1e3))


SECTIONS = {"general": general, "halo": halo, "buck": buck, "usb3": usb3, "xtal": xtal,
            "adc": adc, "rf": rf, "motor": motor}

if __name__ == "__main__":
    for name in sys.argv[1:] or SECTIONS:
        SECTIONS[name]()
