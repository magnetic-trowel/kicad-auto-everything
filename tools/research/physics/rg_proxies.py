# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Closed-form checks that decompress common PCB rules of thumb into physics.

Each section prints the numbers quoted with [C] tags in
docs/topics/physics/rule-genealogy-*.md and rule-basis-set.md.
Everything is a textbook closed form (Hammerstad microstrip, Grover partial
inductance, parallel-plate via-pair inductance, fin equation, IPC-2221 fit,
Johnson's crosstalk estimate). Deterministic, runs in well under a second:

    python tools/research/physics/rg_proxies.py

Units are SI unless a name says otherwise. Default dielectric: FR-4, er = 4.3.
"""
import math

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
C0 = 2.998e8
RHO_CU = 1.72e-8      # ohm*m at 20 C
K_CU = 390.0          # W/m/K
T_1OZ = 35e-6         # m
ER = 4.3


def ms_z0(w, h, er=ER):
    """Hammerstad-Jensen microstrip Z0 and eps_eff (zero thickness)."""
    u = w / h
    if u <= 1:
        ee = (er + 1) / 2 + (er - 1) / 2 * ((1 + 12 / u) ** -0.5 + 0.04 * (1 - u) ** 2)
        z0 = 60 / math.sqrt(ee) * math.log(8 / u + u / 4)
    else:
        ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / u) ** -0.5
        z0 = 120 * math.pi / (math.sqrt(ee) * (u + 1.393 + 0.667 * math.log(u + 1.444)))
    return z0, ee


def w_for_z0(z0_target, h, er=ER):
    lo, hi = 0.01 * h, 30 * h
    for _ in range(100):
        mid = math.sqrt(lo * hi)
        if ms_z0(mid, h, er)[0] > z0_target:
            lo = mid
        else:
            hi = mid
    return mid


def grover_strip(l, w, t=T_1OZ):
    """Partial self-inductance of a straight rectangular strip (H)."""
    return 2e-7 * l * (math.log(2 * l / (w + t)) + 0.5 + 0.2235 * (w + t) / l)


def via_pair_cavity(s, a, d):
    """Loop inductance of two vias (radius a, pitch s) through a plane pair of spacing d."""
    return MU0 * d / math.pi * math.log(s / a)


def section(title):
    print("\n== " + title)


def main():
    section("A. 3W rule vs Johnson NEXT bound K = 1/(1+(D/H)^2), D = 3W centre-to-centre")
    cases = [("4L, h=0.10 mm, 50 ohm", 0.10e-3, None), ("4L, h=0.20 mm, 50 ohm", 0.20e-3, None),
             ("2L, h=1.50 mm, 50 ohm", 1.50e-3, None), ("2L, h=1.50 mm, 0.25 mm signal", 1.50e-3, 0.25e-3),
             ("4L, h=0.20 mm, 0.10 mm signal", 0.20e-3, 0.10e-3)]
    for name, h, w in cases:
        w = w or w_for_z0(50, h)
        d = 3 * w
        k = 1 / (1 + (d / h) ** 2)
        print(f"{name:32s} w={w*1e3:5.2f} mm  D/h={d/h:5.2f}  K={k*100:5.1f} %")

    section("B. Inductance per mm: trace over a plane (L'=Z0*sqrt(ee)/c) vs w/h; isolated strip")
    h = 0.2e-3
    for u in (0.1, 0.3, 1, 3, 10, 30):
        z0, ee = ms_z0(u * h, h)
        print(f"w/h={u:5.1f}  Z0={z0:6.1f} ohm  L'={z0*math.sqrt(ee)/C0*1e9*1e-3:6.3f} nH/mm")
    for w in (0.25e-3, 1e-3, 4e-3):
        print(f"isolated strip l=20 mm w={w*1e3:4.2f} mm: Lp={grover_strip(20e-3, w)*1e9:5.2f} nH")
    for hh in (1.5e-3, 0.2e-3, 0.1e-3):
        z0, ee = ms_z0(1e-3, hh)
        print(f"1 mm wide, 20 mm long over plane at h={hh*1e3:4.2f} mm: L={z0*math.sqrt(ee)/C0*20e-3*1e9:5.2f} nH")

    section("C. Return-via / decap spreading inductance in a cavity, L=(mu0 d/pi) ln(s/a), a=0.15 mm")
    for d in (0.075e-3, 0.1e-3, 0.25e-3, 1.0e-3):
        row = [f"s={s*1e3:4.1f}mm:{via_pair_cavity(s, 0.15e-3, d)*1e12:6.0f}pH" for s in (1e-3, 1.3e-3, 5e-3, 20e-3)]
        print(f"d={d*1e3:5.3f} mm  " + "  ".join(row))

    section("D. Via partial inductance (Johnson: 0.2*h*(ln(4h/d)+1) nH, mm)")
    for hv, dv in ((1.6, 0.3), (0.2, 0.3), (0.8, 0.2)):
        print(f"h={hv} mm d={dv} mm: {0.2*hv*(math.log(4*hv/dv)+1):.2f} nH")

    section("E. ESD 8 kV contact (IEC 61000-4-2: ~30 A peak, ~0.8 ns rise): V = L di/dt")
    didt = 30 / 0.8e-9
    for L in (0.25e-9, 0.5e-9, 1.0e-9, 1.3e-9):
        print(f"L={L*1e9:4.2f} nH -> {L*didt:5.1f} V (di/dt={didt:.2e} A/s)")

    section("F. IPC-2221 width (1 oz external, dT=10 C) vs IR drop over 20 mm")
    for i in (1, 3, 10):
        area_mil2 = (i / (0.048 * 10 ** 0.44)) ** (1 / 0.725)
        w_mm = area_mil2 / 1.378 * 0.0254
        r = RHO_CU * 20e-3 / (w_mm * 1e-3 * T_1OZ)
        dv = i * r
        print(f"I={i:2d} A  w={w_mm:5.2f} mm  R(20mm)={r*1e3:5.1f} mOhm  drop={dv*1e3:6.1f} mV"
              f"  = {dv/1.0*100:4.1f}% of 1.0 V, {dv/3.3*100:4.1f}% of 3.3 V, {dv/12*100:4.2f}% of 12 V")

    section("G. Skin depth in copper")
    for f in (1e5, 5e5, 1e6, 1e7, 1e8, 1e9):
        print(f"f={f:8.0e} Hz  delta={math.sqrt(RHO_CU/(math.pi*f*MU0))*1e6:6.1f} um")

    section("H. Copper fin length sqrt(k t / 2h) and TI SNVA419 15.3 cm^2/W")
    for t, name in ((35e-6, "1 oz"), (70e-6, "2 oz"), (4 * 35e-6, "4 x 1 oz planes")):
        for hconv in (8.0, 15.0):
            print(f"{name:16s} h={hconv:4.1f} W/m2K: fin length {math.sqrt(K_CU*t/(2*hconv))*1e3:5.1f} mm")
    a = 15.3e-4
    print(f"15.3 cm^2/W at 40 C rise, both sides => h_eff = {1/(40*2*a):.1f} W/m2K")

    section("I. Thermal via (plated barrel) and thermal-relief spokes")
    for d, tp in ((0.3e-3, 25e-6), (0.3e-3, 18e-6), (0.2e-3, 25e-6)):
        area = math.pi * ((d / 2 + tp) ** 2 - (d / 2) ** 2)
        print(f"via d={d*1e3:.1f} mm plating {tp*1e6:.0f} um, 1.6 mm: Rth={1.6e-3/(K_CU*area):5.0f} K/W,"
              f" R={RHO_CU*1.6e-3/area*1e3:4.2f} mOhm, barrel area = {area*1e6:.4f} mm^2"
              f" (= {area/T_1OZ*1e3:.2f} mm of 1 oz trace)")
    sw, sl = 0.25e-3, 0.5e-3
    r_th = sl / (K_CU * sw * T_1OZ)
    r_el = RHO_CU * sl / (sw * T_1OZ)
    lp = grover_strip(sl, sw)
    print(f"spoke {sw*1e3} x {sl*1e3} mm, 1 oz: Rth={r_th:5.0f} K/W each, {r_th/4:4.0f} K/W for 4;"
          f" R={r_el*1e3:4.2f} mOhm each; Lp={lp*1e12:4.0f} pH each (4 in parallel ~{lp/4*1e12:3.0f}-{lp/2*1e12:3.0f} pH)")

    section("J. Crystal: trace capacitance and pulling")
    h = 0.2e-3
    for w in (0.15e-3, 0.3e-3):
        z0, ee = ms_z0(w, h)
        print(f"w={w*1e3:.2f} mm over h=0.2 mm: C'={math.sqrt(ee)/(C0*z0)*1e12*1e-3:.3f} pF/mm")
    for c1, c0, cl in ((3e-15, 1.5e-12, 10e-12), (2e-15, 1.0e-12, 6e-12)):
        s = c1 / (2 * (c0 + cl) ** 2)
        print(f"C1={c1*1e15:.0f} fF C0={c0*1e12:.1f} pF CL={cl*1e12:.0f} pF -> pull {s*1e-12*1e6:5.1f} ppm/pF")

    section("K. Kelvin: 1 oz copper sheet resistance vs milliohm shunts")
    rs = RHO_CU / T_1OZ
    print(f"1 oz sheet resistance = {rs*1e3:.2f} mOhm/sq; 1 sq shared with a 1 mOhm shunt = {rs/1e-3*100:.0f}% error,"
          f" tempco ~{rs/(rs+1e-3)*3900:.0f} ppm/K")

    section("L. Leakage: surface path with rho_s 1e12..1e14 ohm/sq, gap 1 mm x 10 mm (0.1 sq), 5 V")
    for rho_s in (1e10, 1e12, 1e14):
        print(f"rho_s={rho_s:.0e}: I = {5/(rho_s*0.1)*1e15:10.1f} fA")

    section("M. HV: mean field at clearance; Paschen minimum ~327 V in air")
    for v, g in ((325, 1.0e-3), (325, 0.2e-3), (1500, 1.5e-3), (4000, 3.0e-3)):
        print(f"{v} V over {g*1e3} mm = {v/g/1e6:.2f} kV/mm (uniform-field air breakdown ~3 kV/mm)")

    section("N. Return-current spread in the plane under a microstrip, frac within +-k h = (2/pi) atan(k)")
    for k in (1, 3, 5, 10):
        print(f"k={k:2d}: {2/math.pi*math.atan(k)*100:5.1f} %")

    section("O. Path-length overhead vs Euclidean (uniform direction)")
    n = 100000
    octo = sum(math.cos(t) + (math.sqrt(2) - 1) * math.sin(t) for t in (i / n * math.pi / 4 for i in range(n))) / n
    manh = sum(math.cos(t) + math.sin(t) for t in (i / n * math.pi / 4 for i in range(n))) / n
    print(f"octilinear (45 deg): mean +{(octo-1)*100:.1f}%, max +{(math.cos(math.pi/8)+(math.sqrt(2)-1)*math.sin(math.pi/8)-1)*100:.1f}%;"
          f" Manhattan: mean +{(manh-1)*100:.1f}%, max +{(math.sqrt(2)-1)*100:.1f}%")

    section("P. Switch-node copper: capacitance to the plane below and C dv/dt")
    for area, hh in ((20e-6, 0.1e-3), (50e-6, 0.1e-3), (50e-6, 1.5e-3), (100e-6, 0.1e-3)):
        c = EPS0 * ER * area / hh
        print(f"A={area*1e6:4.0f} mm^2 h={hh*1e3:3.1f} mm: C={c*1e12:5.1f} pF, i at 12 V/2 ns = {c*6e9*1e3:6.1f} mA,"
              f" CV^2f at 12 V 500 kHz = {c*144*5e5*1e3:.2f} mW")

    section("Q. Plane cavity f10 = c/(2 a sqrt(er)); 20H; lambda_g/20 stitching")
    for a in (50e-3, 100e-3, 200e-3):
        print(f"a={a*1e3:4.0f} mm: f10 = {C0/(2*a*math.sqrt(ER))/1e6:6.0f} MHz")
    for hh in (0.1e-3, 0.2e-3, 1.0e-3):
        print(f"plane spacing {hh*1e3} mm: 20H = {20*hh*1e3:.0f} mm")
    for f in (0.3e9, 1e9, 3e9):
        print(f"{f/1e9:.1f} GHz: lambda/20 in er=4.3 = {C0/f/math.sqrt(ER)/20*1e3:.1f} mm")

    section("R. Stub quarter-wave resonance f = c/(4 l sqrt(ee)), ee=3.6 microstrip / 4.3 stripline")
    for l in (0.25e-3, 1e-3, 1.27e-3, 6.35e-3):
        print(f"stub {l*1e3:5.2f} mm: {C0/(4*l*math.sqrt(4.3))/1e9:6.1f} GHz (stripline)")

    section("S. 2-layer vs 4-layer differential-mode loop height (radiation ~ loop area)")
    print(f"h 1.5 mm vs 0.2 mm: {20*math.log10(1.5/0.2):.1f} dB; vs 0.1 mm: {20*math.log10(1.5/0.1):.1f} dB")

    section("T. Hot loop: V = L di/dt and ring frequency with Coss")
    for L in (0.4e-9, 1e-9, 2e-9, 5e-9):
        print(f"L={L*1e9:3.1f} nH: 10 A/2 ns -> {L*5e9:4.1f} V; ring with 1 nF -> {1/(2*math.pi*math.sqrt(L*1e-9))/1e6:4.0f} MHz")

    section("U. Critical length t_r/6 and knee 0.5/t_r (microstrip ~6.3 ps/mm at ee 3.6)")
    tpd = math.sqrt(3.6) / C0
    for tr in (5e-9, 1e-9, 0.3e-9, 0.1e-9, 0.03e-9):
        print(f"t_r={tr*1e12:6.0f} ps: t_r/6 = {tr/6/tpd*1e3:7.1f} mm, knee = {0.5/tr/1e9:5.2f} GHz")

    section("V. Skew -> common mode: Vcm/Vdiff ~ dt/(2 t_r)")
    for dt, tr in ((5e-12, 100e-12), (20e-12, 100e-12), (50e-12, 500e-12)):
        print(f"skew {dt*1e12:.0f} ps, t_r {tr*1e12:.0f} ps -> {dt/(2*tr)*100:.1f} % common mode")

    section("W. Resistive/inductive crossover f_x = R'/(2 pi L') of a 1 oz trace over a plane (h = 0.2 mm)")
    h = 0.2e-3
    for w in (0.15e-3, 0.5e-3, 2e-3, 10e-3):
        z0, ee = ms_z0(w, h)
        lp = z0 * math.sqrt(ee) / C0
        rp = RHO_CU / (w * T_1OZ)
        print(f"w={w*1e3:5.2f} mm: R'={rp*1e3*1e-3:6.3f} mOhm/mm L'={lp*1e9*1e-3:5.3f} nH/mm f_x={rp/(2*math.pi*lp)/1e3:6.0f} kHz")


if __name__ == "__main__":
    main()
