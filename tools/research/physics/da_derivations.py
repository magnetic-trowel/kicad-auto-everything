# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Derivation audit (round 3, prefix da): closed-form checks behind docs/topics/physics/derivation-audit.md.

Each section checks one derivation that the audit table uses to decide whether a rule of thumb
follows from first principles, and in which regime.  All closed forms; runs in about a second.

  A  Thermal reliefs and vias: Wiedemann-Franz ties a spoke's thermal and electrical resistance
     (R_el = rho*k*R_th).  Reflow vs hand soldering from the pad's thermal couplings.
  B  Stitching: a 2-D via lattice is a wire medium (cut-off k_p, decay length ~0.7 pitch, independent
     of plane spacing and of frequency below cut-off); a 1-D fence is an inductive grid whose leakage
     grows as pitch/lambda.  Compared with the lambda/20 and lambda_g/20 rules.
  C  Star versus plane: the frequency below which half of a return spreads beyond distance x,
     f = R_s/(2 pi mu0 x) (lens VP's l50), for 0.5/1/2 oz planes.
  D  "Three values per pin": Foster's reactance theorem (dX/dw > 0 for a lossless one-port) forces an
     anti-resonance between any two distinct series resonances; its height scales with Q (1/ESR).
  E  Impedance level: first-order errors eps_L = theta*Z0/Z and eps_C = theta*Z/Z0 (lens LS) for the
     structures behind a dozen rules; which rules the "match Z0 to Z" principle derives.
  F  "As close as possible": marginal parasitic per mm for a series path (linear), a plane-spreading
     decap (logarithmic, then screened) and a node capacitance (linear).
  G  Small constants: the PDN 1.57 factor (square-wave fundamental), spread-spectrum peak reduction,
     the ESD 2.6 mm radius (V/E_bd), the gate-loop damping bound, the bootstrap ratio.
  H  Corner exponents: scalar wedge (current, E-field) and the elastic Williams eigenvalue (teardrops).

Run:  OMP_NUM_THREADS=1 python da_derivations.py
"""
import math

import numpy as np
from scipy.optimize import brentq

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
C0 = 299792458.0
ETA0 = MU0 * C0
RHO_CU = 1.72e-8          # ohm m, PCB copper
K_CU = 385.0              # W/(m K)
K_FR4 = 0.3               # W/(m K)
ER = 4.3
OZ = {0.5: 17.5e-6, 1.0: 35e-6, 2.0: 70e-6}
mm = 1e-3


def rs(t):
    return RHO_CU / t


# ---------------------------------------------------------------------------------------------
def sec_a_reliefs():
    print("== A. Thermal reliefs and vias: Wiedemann-Franz")
    wf = 1.0 / (RHO_CU * K_CU)                     # K/W per ohm
    print(f"   R_th / R_el = 1/(rho k) = {wf:.3e} K/(W ohm) = {wf*1e-6:.3f} K/W per micro-ohm "
          f"(Lorenz number rho k / T = {RHO_CU*K_CU/300:.2e} W ohm/K^2 at 300 K)")
    t = OZ[1.0]
    for w, l in ((0.25 * mm, 0.25 * mm), (0.25 * mm, 0.5 * mm)):
        r_el = RHO_CU * l / (w * t) / 4
        r_th = l / (K_CU * w * t) / 4
        print(f"   4 spokes {w/mm:.2f} x {l/mm:.2f} mm, 1 oz: R_el = {r_el*1e3:.3f} mOhm, R_th = {r_th:5.1f} K/W, "
              f"G_th = {1e3/r_th:5.1f} mW/K")
    # reflow: the pad follows the plane unless the spoke conductance falls below the pad's own coupling
    g_pad = 1e-4          # W/K, a small pad's coupling to the oven (round 1 WS7: ~0.1 mW/K)
    r_needed = 1.0 / g_pad
    print(f"   reflow: pad coupling to the oven ~{g_pad*1e3:.1f} mW/K; to make the pad follow the air rather than the "
          f"plane the spokes need R_th >= {r_needed:.0f} K/W, i.e. R_el >= {r_needed/wf*1e3:.0f} mOhm by Wiedemann-Franz")
    c_pad = 8e-5          # J/K, 0402 pad copper + paste (estimate)
    r_sp = 37.0
    print(f"   pad time constant through a 37 K/W relief: {c_pad*r_sp*1e3:.1f} ms; at a 3 K/s ramp the pad lags the "
          f"plane by {c_pad*r_sp*3:.3f} K -> a relief cannot desynchronise or resynchronise two pads in reflow")
    # hand soldering: plane drain vs relief (steady radial spreading in one 1 oz plane out to R)
    for nplanes in (1, 4):
        r0, R = 0.5 * mm, 25 * mm
        r_plane = math.log(R / r0) / (2 * math.pi * K_CU * t) / nplanes
        print(f"   hand/wave soldering, {nplanes} plane(s): spreading drain {r_plane:5.1f} K/W; with a 37 K/W relief in "
              f"series the joint's drain falls {(r_plane+37)/r_plane:4.1f}x")
    # via barrel
    d, tp, h = 0.3 * mm, 25e-6, 1.6 * mm
    a = math.pi * ((d / 2) ** 2 - (d / 2 - tp) ** 2)
    print(f"   via 0.3 mm, 25 um plating, 1.6 mm: R_el = {RHO_CU*h/a*1e3:.2f} mOhm, R_th = {h/(K_CU*a):.0f} K/W "
          f"(ratio {h/(K_CU*a)/(RHO_CU*h/a)*1e-6:.3f} K/W per micro-ohm)")
    # Kohlrausch: an end-cooled conductor's peak self-heating depends only on its voltage drop
    l0t = RHO_CU * K_CU
    r_via = RHO_CU * h / a
    v10 = math.sqrt(10 * 8 * l0t)
    print(f"   end-cooled barrel (Kohlrausch, from Wiedemann-Franz): dT_max = V^2/(8 L0 T); 1 A x {r_via*1e3:.2f} mOhm -> "
          f"{(r_via)**2/(8*l0t):.3f} K; 10 K needs V = {v10*1e3:.0f} mV = {v10/r_via:.0f} A per via (planes held cool)")
    # IPC-2221 check: a trace on a laminate fin, two-sided convection
    for hconv in (10.0, 15.0):
        tb, w_tr = 1.6 * mm, 0.30 * mm
        lam = math.sqrt(K_FR4 * tb / (2 * hconv))
        q = 1.0 ** 2 * RHO_CU / (w_tr * t)
        print(f"   IPC-2221 check: 0.30 mm 1 oz trace at 1 A on 1.6 mm FR-4, h = {hconv:.0f} W/m2K per face: fin length "
              f"{lam/mm:.1f} mm, dT = q' lam/(2 k t_b) = {q*lam/(2*K_FR4*tb):.1f} K (chart: 10 K)")
    # heat through a thin dielectric costs capacitance: G/C = k/eps
    print(f"   heat through FR-4: G_th/C = k/eps = {K_FR4/(ER*EPS0):.2e} W/(K F): 1 K/W costs "
          f"{ER*EPS0/K_FR4*1e12:.0f} pF")


# ---------------------------------------------------------------------------------------------
def kp_lattice(a, r):
    """Wire-medium cut-off wavenumber of a square via lattice (Belov), independent of plane spacing."""
    return math.sqrt(2 * math.pi / (a * a * (math.log(a / (2 * math.pi * r)) + 0.5275)))


def sec_b_stitching():
    print("\n== B. Stitching lattice (2-D) and via fence (1-D)")
    r = 0.15 * mm
    vf = C0 / math.sqrt(ER)
    print("   2-D lattice: k_p^2 = 2 pi / (a^2 (ln(a/2 pi r) + 0.5275)) (no dependence on plane spacing d);")
    print("   below cut-off the parallel-plate field decays as exp(-sqrt(k_p^2 - k^2) x)")
    for a in (2 * mm, 5 * mm, 10 * mm, 20 * mm):
        kp = kp_lattice(a, r)
        fp = kp * vf / (2 * math.pi)
        print(f"     pitch {a/mm:4.0f} mm: f_p = {fp/1e9:5.2f} GHz, decay length 1/k_p = {1/kp/mm:4.2f} mm "
              f"= {1/(kp*a):.2f} pitch, {8.686*kp*mm:4.2f} dB/mm (f << f_p)")
    for frac in (20, 10, 4):
        # choose f_max, pitch = lambda/frac in the dielectric; report f_p/f_max and attenuation per mm at f_max
        fmax = 2.45e9
        lam = vf / fmax
        a = lam / frac
        kp = kp_lattice(a, r)
        k = 2 * math.pi / lam
        att = math.sqrt(max(kp * kp - k * k, 0.0))
        print(f"   pitch lambda/{frac:<2d} at {fmax/1e9:.2f} GHz = {a/mm:5.2f} mm: f_p/f_max = {kp/k:4.2f}; "
              f"decay {8.686*att*mm:5.2f} dB/mm = {8.686*att*a:5.1f} dB per pitch")
    print("   reading: below cut-off each pitch screens ~11-19 dB (only logarithmic in pitch/radius) whatever the")
    print("   frequency, so isolation over a distance D sets the pitch (N dB needs ~N/13 pitches across D), and")
    print("   f_p > f_max (a <~ lambda/4) is the only frequency condition; lambda/20 is a ~6x margin on cut-off")
    print("   1-D fence (one row): shunt reactance X/eta = (a/lambda) ln(a/(2 pi r)) (inductive grid), "
          "|T| = 1/sqrt(1+(eta/2X)^2)")
    for frac in (20, 10, 5):
        lam = vf / 2.45e9
        a = lam / frac
        x = (a / lam) * math.log(a / (2 * math.pi * r))
        tmag = 1 / math.sqrt(1 + (1 / (2 * x)) ** 2)
        print(f"     fence pitch lambda_g/{frac:<2d} ({a/mm:4.2f} mm at 2.45 GHz): leakage {20*math.log10(tmag):6.1f} dB per row")
    print("   reading: a single fence leaks in proportion to a/lambda (frequency matters); a 2-D lattice does not")


# ---------------------------------------------------------------------------------------------
def sec_c_star():
    print("\n== C. Star vs plane: frequency below which half the return spreads beyond distance x, f = R_s/(2 pi mu0 x)")
    xs = (1, 3, 10, 30, 60)
    print("   copper    " + "  ".join(f"x={x:>3d} mm" for x in xs))
    for oz, t in OZ.items():
        row = []
        for x in xs:
            f = rs(t) / (2 * math.pi * MU0 * x * mm)
            row.append(f"{f/1e3:7.1f} kHz")
        print(f"   {oz:3.1f} oz   " + "  ".join(row))
    for oz, t in OZ.items():
        for h in (0.1 * mm, 0.2 * mm, 1.6 * mm):
            fx = rs(t) / (2 * math.pi * MU0 * h)
            print(f"   f_x (x = h = {h/mm:.1f} mm, {oz} oz) = {fx/1e3:7.0f} kHz", end="")
        print()
    print("   reading: a quiet victim 10 mm from an aggressor's return is reached by that return only below ~6 kHz on")
    print("   1 oz; the star/split regime is DC to kHz at board scale, not 'below f_x' (0.3-1 MHz)")


# ---------------------------------------------------------------------------------------------
def zcap(f, c, esl, esr):
    w = 2 * np.pi * f
    return esr + 1j * (w * esl - 1 / (w * c))


def sec_d_foster():
    print("\n== D. Three values per pin vs Foster's reactance theorem")
    f = np.logspace(5, 9.5, 40001)
    for esr in (0.010, 0.003, 0.030):
        mix = 1 / sum(1 / zcap(f, c, 1e-9, esr) for c in (10e-6, 100e-9, 1e-9))
        same = 1 / sum(1 / zcap(f, c, 1e-9, esr) for c in (10e-6, 10e-6, 10e-6))
        zm = np.abs(mix)
        # local maxima above 1 MHz
        idx = [i for i in range(1, len(f) - 1) if zm[i] > zm[i - 1] and zm[i] > zm[i + 1] and f[i] > 1e6]
        peaks = ", ".join(f"{zm[i]:.2f} ohm at {f[i]/1e6:.0f} MHz" for i in idx)
        zs = np.abs(same)
        idx2 = [i for i in range(1, len(f) - 1) if zs[i] > zs[i - 1] and zs[i] > zs[i + 1] and f[i] > 1e6]
        print(f"   ESR {esr*1e3:4.0f} mOhm, ESL 1 nH each: 10u+100n+1n peaks: {peaks or 'none'}; 3x10u peaks: "
              f"{len(idx2)}")
    # Foster: lossless reactance is monotone increasing between poles
    with np.errstate(divide="ignore", invalid="ignore"):
        mix0 = 1 / sum(1 / zcap(f, c, 1e-9, 0.0) for c in (10e-6, 100e-9, 1e-9))
    x = mix0.imag
    sgn = np.sign(x)
    zeros = int(np.sum((sgn[:-1] < 0) & (sgn[1:] > 0)))      # series resonances: X crosses 0 upward
    poles = int(np.sum((sgn[:-1] > 0) & (sgn[1:] < 0)))      # anti-resonances: X jumps from +inf to -inf
    dx = np.diff(x)
    smooth = (sgn[:-1] == sgn[1:]) | (np.abs(x[:-1]) < 1.0)
    mono = np.mean(dx[smooth] > 0)
    print(f"   lossless mix: {zeros} series resonances, {poles} anti-resonances; reactance increases on "
          f"{mono*100:.1f}% of steps away from poles (Foster: poles and zeros alternate)")
    print("   reading: distinct values guarantee anti-resonances (energy positivity, dX/dw = 4(Wm+We)/|I|^2 > 0);")
    print("   their height is set only by loss (Q); equal values with equal mounting L have none")


# ---------------------------------------------------------------------------------------------
def z0_wide(w, h, er=ER):
    """Parallel-plate estimate for w >> h (fringing ignored)."""
    return ETA0 / math.sqrt(er) * h / w


def z0_microstrip(w, h, er=ER):
    """Hammerstad-style closed form, adequate for w/h 0.1-10."""
    u = w / h
    ee = (er + 1) / 2 + (er - 1) / 2 / math.sqrt(1 + 12 / u)
    if u <= 1:
        return 60 / math.sqrt(ee) * math.log(8 / u + u / 4)
    return 120 * math.pi / (math.sqrt(ee) * (u + 1.393 + 0.667 * math.log(u + 1.444)))


def sec_e_impedance_level():
    print("\n== E. Impedance level: eps_L = theta Z0/Z (KVL error), eps_C = theta Z/Z0 (KCL error), theta = w l/v")
    v = C0 / math.sqrt(3.3)
    cases = [
        # name, Z = V/I of the circuit, copper as drawn (w, h), length, t_r, rules
        ("hot loop 12 V/10 A, 2 mm over 0.1 mm", 12 / 10, z0_wide(2 * mm, 0.1 * mm), 10 * mm, 2e-9, "P01-P06, P35"),
        ("same loop on a 2-layer board, h 1.5 mm", 12 / 10, z0_microstrip(2 * mm, 1.5 * mm), 10 * mm, 2e-9, "P04, P05"),
        ("gate loop 12 V/2 A, 0.3 mm trace, h 0.1", 12 / 2, z0_microstrip(0.3 * mm, 0.1 * mm), 15 * mm, 5e-9, "P19"),
        ("ESD clamp node 10 V/30 A, 0.5 mm over 0.1", 10 / 30, z0_microstrip(0.5 * mm, 0.1 * mm), 5 * mm, 0.8e-9, "S35"),
        ("plane pair 50 mm wide, d 0.1 mm vs Z_t 10 mOhm", 0.010, z0_wide(50 * mm, 0.1 * mm), 50 * mm, 1e-9, "P26"),
        ("50 ohm RF line", 50.0, z0_microstrip(0.19 * mm, 0.1 * mm), 30 * mm, 0.1e-9, "S44, S28, R07, R23"),
        ("crystal node ~640 ohm, 0.15 mm trace", 640.0, z0_microstrip(0.15 * mm, 0.1 * mm), 8 * mm, 2e-9, "S51, S52"),
        ("FB node 100 kOhm, 0.15 mm trace", 1e5, z0_microstrip(0.15 * mm, 0.1 * mm), 20 * mm, 5e-9, "P10, P42"),
    ]
    print("   structure                                   Z (ohm)   Z0 (ohm)  theta   eps_L    eps_C   lever")
    for name, z, z0, l, tr, rules in cases:
        f = 0.35 / tr
        th = 2 * math.pi * f * l / v
        el, ec = th * z0 / z, th * z / z0
        if abs(math.log(z0 / z)) < 0.1:
            lever = "matched: a pure delay at any length"
        elif el > ec:
            lever = "lower Z0: wider, thinner dielectric, overlap"
        else:
            lever = "raise Z0: narrower, farther, void below"
        print(f"   {name:43s} {z:8.3g} {z0:9.3g} {th:7.3f} {el:8.3g} {ec:8.3g}   {lever}  [{rules}]")
    print("   reading: every self-term rule above points Z0 toward Z; at Z0 = Z both errors equal theta (a pure delay).")
    print("   The rule's number is set by the slack, e.g. L*di/dt vs margin; interaction rules (P07, S15-S17, S31) are")
    print("   not of this form: they are couplings, not a structure's own impedance.")


# ---------------------------------------------------------------------------------------------
def sec_f_close():
    print("\n== F. 'As close as possible': what one millimetre buys")
    h, w = 0.1 * mm, 2 * mm
    print(f"   series path over a plane (hot loop CIN, TVS ground): dL/dl = mu0 h/w = {MU0*h/w*1e9:.0f} pH/mm "
          f"(h 0.1 mm, w 2 mm), constant with distance")
    for d in (0.1 * mm, 1.0 * mm):
        vals = ", ".join(f"{MU0*d/(math.pi*s)*1e9:5.1f} pH/mm at s = {s/mm:4.1f} mm" for s in (2 * mm, 5 * mm, 15 * mm))
        print(f"   decap on a plane pair d = {d/mm:.1f} mm: dL/ds = mu0 d/(pi s) = {vals}")
    print("   beyond the screening length lambda(f) = v/sqrt(w_p^2 - w^2) (4-24 mm, lens LS) a decap stops contributing")
    print("   crystal trace: 0.07-0.10 pF/mm x 11-20 ppm/pF = 0.8-2 ppm per mm (linear)")
    print("   reading: 'close' is linear for series paths and node capacitance, logarithmic for plane spreading,")
    print("   and bounded by a screening length; the rule is right for the first two and a weak lever for the third")


# ---------------------------------------------------------------------------------------------
def sec_g_constants():
    print("\n== G. Constants that derive in one line")
    a1 = 2 / math.pi
    print(f"   PDN: a load toggling between 0 and dI at the resonance has fundamental amplitude (2/pi) dI = {a1:.3f} dI;"
          f" a high-Q peak passes only that, so Z_pk <= Z_t/(2/pi) = {1/a1:.3f} Z_t")
    for f0, dev in ((100e6, 0.01), (100e6, 0.005)):
        for n in (1, 5):
            spread = n * f0 * dev
            print(f"   spread spectrum {dev*100:.1f}% at {f0/1e6:.0f} MHz, harmonic {n}: peak drop "
                  f"10 log(spread/120 kHz) = {10*math.log10(spread/120e3):4.1f} dB (energy unchanged: Parseval)")
    e_bd = 3.0e6
    for v in (8e3, 15e3):
        r = v / e_bd
        # Peek's law for a sphere: E_c = 3.0 (1 + 0.3/sqrt(r_cm)) kV/mm
        rc = brentq(lambda rr: v / rr - 3.0e6 * (1 + 0.3 / math.sqrt(rr * 100)), 1e-5, 1.0)
        print(f"   ESD: an isolated feature of radius r at {v/1e3:.0f} kV has surface field ~V/r; air (3 kV/mm) breaks "
              f"down for r < {r/mm:.2f} mm (Peek-corrected {rc/mm:.2f} mm)")
    rg, rs_, cgs = 2.0, 0.5, 2e-9
    print(f"   gate loop: critical damping zeta >= 1 gives L_G <= (R_G+R_S)^2 C_GS/4 = {(rg+rs_)**2*cgs/4*1e9:.1f} nH "
          f"for R = {rg+rs_} ohm, C_GS = {cgs*1e9:.0f} nF")
    print(f"   bootstrap: charge conservation, dV/V = C_g/(C_boot + C_g) = {1/11*100:.1f}% at C_boot = 10 C_g")


# ---------------------------------------------------------------------------------------------
def sec_h_corners():
    print("\n== H. Corner exponents")
    for name, alpha in (("current at a concave (inside) corner, copper angle 270 deg", 1.5 * math.pi),
                        ("E-field at a convex corner, gap angle 270 deg", 1.5 * math.pi),
                        ("current at a convex (outside) corner, copper angle 90 deg", 0.5 * math.pi),
                        ("current at a 135 deg bend inside, copper angle 225 deg", 1.25 * math.pi)):
        print(f"   {name:60s}: r^({math.pi/alpha - 1:+.3f})")
    # Williams eigenvalue, traction-free wedge of material angle 2b, symmetric (mode I): sin(2 l b) + l sin(2 b) = 0
    for deg in (270.0, 315.0, 360.0):
        b = math.radians(deg) / 2
        g1 = lambda lam: math.sin(2 * lam * b) + lam * math.sin(2 * b)
        lam1 = brentq(g1, 0.3, 0.999)
        g2 = lambda lam: math.sin(2 * lam * b) - lam * math.sin(2 * b)
        try:
            lam2 = brentq(g2, 0.3, 0.999)
            s2 = f", mode II r^({lam2-1:+.3f})"
        except ValueError:
            s2 = ", mode II not singular"
        print(f"   elastic stress at a re-entrant corner, material angle {deg:.0f} deg: mode I r^({lam1-1:+.3f}){s2}")
    print("   reading: one wedge law, three physics (current, field, stress); fillets and teardrops remove the")
    print("   singularity, which matters for damage (local, high-order), not for loss (an energy)")


if __name__ == "__main__":
    sec_a_reliefs()
    sec_b_stitching()
    sec_c_star()
    sec_d_foster()
    sec_e_impedance_level()
    sec_f_close()
    sec_g_constants()
    sec_h_corners()
