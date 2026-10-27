# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Closed-form checks: when does trace geometry matter? (docs/topics/physics/rf-geometry.md)

Sections (all deterministic, < 1 s):
  A. "geometry matters above X": per rise time t_r, the knee frequency, the
     reflection from a 90-degree corner / 50 % mitre / teardrop / unvoided 0402 pad
     (C-only worst case |G| ~ Z0*C/(2 t_r)), diff-pair skew from one 90-degree turn
     vs a 0.1*t_r budget, and the longest via stub with |S11| <= 0.1 at f_knee.
     Corner capacitances: Kirschning/Jansen fits via the Qucs technical notes;
     the same numbers appear in rg_corners.py (workstream 1).
  B. fibre-weave skew: delay difference per mm for a Dk contrast, and the bounded
     residual when the trace is rotated by theta to a weave of pitch P; the Bragg
     frequency of the periodic loading; the minimum angle for a segment length.
  C. via-stub quarter-wave frequencies, and the longest stub for a reflection budget:
     an open stub of impedance Zs shunting a Z0 line gives |S11| ~ (Z0/2Zs) tan(beta L),
     so |S11| <= g at f needs f_qw >= (pi/4)(Z0/Zs) f / g  (~8x f for g = 0.1).
  D. RF: phase/mismatch of putting a line between an RF pin and its match
     (match-at-the-pin), Chu-limit minimum antenna sphere for a bandwidth,
     copper-plane absorption vs frequency.
  E. differential-pair EMI crossover: residual (quadrupole) radiation of a pair,
     ~ k*s relative to single-ended, vs driver imbalance eps; s* = eps*lambda/(2 pi).
  F. return via at a reference change through a plane pair (spacing t): radial-
     waveguide model Z_pair = (w mu t / 2) [H0(ka) - H0(ks)]. Im part -> loop
     inductance (mu t/pi) ln(s/a); Re part -> power launched into the cavity,
     relative to an unpaired via: (1 - J0(ks)). Gives the distance s for which
     cavity excitation is 10 dB below an unpaired via (ks ~ 0.63, s ~ lambda_d/10).
Run:  python tools/research/physics/fe_geometry.py
"""
import math

C0 = 2.998e8
ER = 4.3


def corner_C(w, h, er=ER, mitre=False):
    """Kirschning/Jansen right-angle (or 50 % mitred) microstrip bend capacitance, F (w, h in m)."""
    u = w / h
    if mitre:
        return w * ((3.93 * er + 0.62) * u + (7.6 * er + 3.80)) * 1e-12
    return w * ((10.35 * er + 2.5) * u + (2.6 * er + 5.64)) * 1e-12


def douville_james_mitre(u):
    return 0.52 + 0.65 * math.exp(-1.35 * u)


def section_a():
    print("== A. Geometry matters above X (50-ohm microstrip, h = 0.1 mm, w = 0.19 mm, er 4.3)")
    w, h, z0 = 0.19e-3, 0.1e-3, 50.0
    c90 = corner_C(w, h)
    cm = corner_C(w, h, mitre=True)
    c_tear = 8.854e-12 * ER * 0.04e-6 / h * 1.3   # ~0.04 mm^2 extra copper, 30 % fringing
    c_pad = (0.248 - 0.120) * 1e-12 / 1e-3 * 0.5e-3  # fe_field2d.py: 0.5 x 0.5 mm pad, unvoided
    tpd = math.sqrt(3.1) / C0                         # s/m, eeff from fe_field2d.py
    p = 0.3e-3                                        # diff-pair pitch
    skew_turn = p * math.pi / 2 * tpd                 # arc turn; square corner = 2p
    print(f"   C(90 deg) = {c90*1e15:.1f} fF, C(50% mitre) = {cm*1e15:.1f} fF, teardrop ~{c_tear*1e15:.0f} fF,"
          f" 0402 pad unvoided ~{c_pad*1e15:.0f} fF; Douville-James optimum mitre at w/h=1.9: "
          f"{douville_james_mitre(1.9)*100:.0f} %")
    print(f"   one 90-deg turn of a {p*1e3:.1f} mm pitch pair: {skew_turn*1e12:.2f} ps (arc), "
          f"{2*p*tpd*1e12:.2f} ps (square)")
    print("   t_r     f_knee  |G| 90deg  |G| mitre  |G| teardrop  |G| pad   turns to 0.1 t_r   stub max (|S11|<=0.1 @ f_knee)")
    for tr in (5e-9, 1e-9, 300e-12, 100e-12, 35e-12, 15e-12):
        fk = 0.35 / tr
        g = lambda c: z0 * c / (2 * tr) * 100
        turns = 0.1 * tr / skew_turn
        stub = C0 / (4 * math.sqrt(ER) * (math.pi / 4 / 0.1) * fk)
        print(f"   {tr*1e12:6.0f}ps {fk/1e9:6.2f}GHz  {g(c90):6.2f}%   {g(cm):6.2f}%    {g(c_tear):6.2f}%     "
              f"{g(c_pad):6.2f}%   {turns:8.0f}           {stub*1e3:6.2f} mm")
    print("   (|G| ~ Z0 C/(2 t_r) for a lumped C much shorter than the edge; 1 % is invisible on an eye.)")


def section_b():
    print("\n== B. Fibre-weave skew (local Dk contrast between the two legs of a pair)")
    dk0 = 3.7
    for ddk in (0.1, 0.2, 0.8):
        dt = (math.sqrt(dk0 + ddk / 2) - math.sqrt(dk0 - ddk / 2)) / C0
        print(f"   dDk {ddk:.1f}: {dt*1e12/1e3:.3f} ps/mm = {dt*1e12*25.4/1e3:.1f} ps/in aligned with a bundle;"
              f" 100 mm -> {dt*1e12*0.1:.1f} ps (25 Gb/s NRZ UI = 40 ps)")
    print("   Rotated by theta to a weave of pitch P: residual skew <= 2 * d * P / (2 pi sin(theta)) (length-independent)")
    d = (math.sqrt(dk0 + 0.4) - math.sqrt(dk0 - 0.4)) / C0  # worst case dDk 0.8
    for P in (0.45e-3, 0.8e-3):
        for th in (2, 5, 10, 15, 30):
            s = math.sin(math.radians(th))
            res = 2 * d * P / (2 * math.pi * s)
            period = P / s
            fb = C0 / (2 * math.sqrt(3.1) * period)
            print(f"   P={P*1e3:.2f} mm theta={th:2d} deg: residual <= {res*1e12:.2f} ps; period along trace "
                  f"{period*1e3:5.1f} mm -> Bragg {fb/1e9:5.1f} GHz")
    for L in (10e-3, 50e-3):
        th = math.degrees(math.asin(min(1, 3 * 0.45e-3 / L)))
        print(f"   segment {L*1e3:.0f} mm: theta >= {th:.1f} deg crosses >= 3 bundles (P = 0.45 mm)")


def section_c():
    print("\n== C. Via stubs: f_qw = c / (4 L sqrt(er_eff)); er_eff 4.3 (pads/NFPs lower it further)")
    for L in (0.25e-3, 0.5e-3, 1.0e-3, 1.4e-3, 2.4e-3):
        print(f"   stub {L*1e3:4.2f} mm: f_qw = {C0/(4*L*math.sqrt(ER))/1e9:5.1f} GHz")
    print("   longest stub with |S11| <= 0.1 at Nyquist (Zs = Z0), i.e. f_qw >= 7.9 x Nyquist (NRZ):")
    for gbps in (5, 10, 16, 28, 56):
        fn = gbps / 2 * 1e9
        L = C0 / (4 * math.sqrt(ER) * (math.pi / 4 / 0.1) * fn)
        print(f"   {gbps:3d} Gb/s: {L*1e3:.2f} mm ({L/25.4e-6:.0f} mil); Telian 0.3/Gbps in = "
              f"{0.3/gbps*25.4:.2f} mm")


def zin(zl, z0, beta_l):
    t = math.tan(beta_l)
    return z0 * (zl + 1j * z0 * t) / (z0 + 1j * zl * t)


def section_d():
    print("\n== D. RF")
    f = 2.44e9
    lam_g = C0 / (f * math.sqrt(3.1))
    print(f"   2.44 GHz microstrip (eeff 3.1): lambda_g = {lam_g*1e3:.1f} mm, {360/lam_g/1e3:.2f} deg/mm")
    for zchip in (complex(35, -10), complex(15, -30), complex(5, 20)):
        row = []
        znet = zchip.conjugate()  # network designed to present Z_chip* at the pin
        for l in (0.0, 1e-3, 2e-3, 5e-3):
            zi = zin(znet, 50.0, 2 * math.pi * l / lam_g)
            g = (zi - zchip.conjugate()) / (zi + zchip)
            row.append(10 * math.log10(1 - abs(g) ** 2))
        q = abs(zchip.imag) / zchip.real
        print(f"   pin Z = {zchip.real:4.0f}{zchip.imag:+4.0f}j (Q={q:3.1f}): mismatch loss at 0/1/2/5 mm of 50-ohm line = "
              + " / ".join(f"{x:5.2f}" for x in row) + " dB")
    print("   Chu limit Q >= 1/(ka)^3 + 1/(ka); VSWR-2 bandwidth B = 1/(sqrt(2) Q):")
    for fc, bw in ((2.44e9, 83.5e6), (915e6, 26e6), (868e6, 7e6), (5.5e9, 600e6)):
        k = 2 * math.pi * fc / C0
        qmax = 1 / (math.sqrt(2) * bw / fc)
        lo, hi = 0.01, 3.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if 1 / mid ** 3 + 1 / mid > qmax:
                lo = mid
            else:
                hi = mid
        print(f"   {fc/1e9:5.3f} GHz, BW {bw/1e6:5.1f} MHz: Q <= {qmax:5.1f} -> ka >= {hi:.3f}, "
              f"min sphere radius {hi/k*1e3:5.1f} mm (lambda/2pi = {1/k*1e3:.0f} mm)")
    print("   Absorption through a copper plane A = 8.686 t/delta:")
    for f in (1e5, 1e6, 1e7, 1e8, 1e9):
        delta = math.sqrt(2 / (2 * math.pi * f * 4e-7 * math.pi * 5.8e7))
        print(f"   {f/1e6:8.1f} MHz: delta {delta*1e6:6.1f} um; 35 um plane {8.686*35e-6/delta:6.1f} dB,"
              f" 17 um {8.686*17e-6/delta:6.1f} dB")


def section_e():
    print("\n== E. Differential pair: residual DM radiation ~ k*s vs imbalance eps (both relative to single-ended)")
    for f in (100e6, 1e9, 5e9):
        lam = C0 / f
        for eps in (0.01, 0.001):
            s_star = eps * lam / (2 * math.pi)
            print(f"   f = {f/1e9:4.1f} GHz, eps = {eps*100:.1f} %: tighter coupling stops helping below "
                  f"s* = {s_star*1e3:.2f} mm")
    print("   skew-to-CM: |V_cm/V_dm| = |sin(pi f dt)|/2; time domain peak ~ dt/(2 t_r) (Johnson)")
    for dt, f in ((5e-12, 2.5e9), (20e-12, 2.5e9), (20e-12, 240e6)):
        print(f"   dt = {dt*1e12:3.0f} ps at {f/1e9:.2f} GHz: CM/DM = {abs(math.sin(math.pi*f*dt))/2*100:.2f} %"
              f" ({20*math.log10(abs(math.sin(math.pi*f*dt))/2):.0f} dB)")


def section_f():
    from scipy.special import j0, y0
    print("\n== F. Return via at a reference change through a plane pair, t = 0.2 mm, via r = 0.15 mm, er 4.3")
    t, a, mu = 0.2e-3, 0.15e-3, 4e-7 * math.pi
    for f in (2.5e9, 4e9, 8e9, 16e9):
        k = 2 * math.pi * f * math.sqrt(ER) / C0
        lam_d = 2 * math.pi / k
        w = 2 * math.pi * f
        unpaired_re = w * mu * t / 4 * j0(k * a)
        cells = []
        for s in (0.5e-3, 1.3e-3, 2.5e-3, 5.08e-3, 10e-3):
            re = w * mu * t / 2 * (j0(k * a) - j0(k * s))
            im = -w * mu * t / 2 * (y0(k * a) - y0(k * s))
            cells.append(f"s={s*1e3:4.1f}mm L={im/w*1e12:4.0f}pH cav={10*math.log10(re/2/unpaired_re):5.1f}dB")
        s10 = 0.63 / k
        print(f"   {f/1e9:4.1f} GHz (lambda_d {lam_d*1e3:5.1f} mm; -10 dB at s = {s10*1e3:.2f} mm):")
        print("      " + " | ".join(cells))
    print("   (cav = power launched into the plane pair relative to an unpaired via; L = loop inductance)")


def main():
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()
    section_f()


if __name__ == "__main__":
    main()
