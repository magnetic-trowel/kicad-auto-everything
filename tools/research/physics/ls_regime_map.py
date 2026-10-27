# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scales, regimes and orders of the circuit limit on a reference 4-layer board (lens LS).

Used by docs/topics/physics/lens-ls.md.  Four parts, all closed forms or tiny numerics:

1. The ordered list of characteristic lengths and times of a PCB, computed from one set of
   material constants (copper, FR-4, air) and the reference board RB4 below.
2. The impedance-level split of the first-order corrections.  For a structure of length l with
   characteristic impedance Z0 carrying a circuit whose impedance level is Z = V/I, the circuit
   (Kirchhoff) term is order 0 and the layout adds
        eps_L = theta * Z0/Z  (inductive EMF: the correction to KVL)
        eps_C = theta * Z/Z0  (displacement current: the correction to KCL),  theta = w l / v.
   eps_L * eps_C = theta^2 (retardation, second order); eps_L + eps_C >= 2 theta with equality at
   Z0 = Z, where the two corrections combine into a pure delay.  A short two-port between equal
   terminations Z has amplitude error (theta^2/8)(Z0/Z - Z/Z0)^2 and phase theta (Z0/Z + Z/Z0)/2.
   Checked here against the exact ABCD transfer.
3. The regime map: small parameters and the required model for 15 structures on RB4.
4. Two causality checks: (a) the critical length of an unterminated line as a family in source
   mismatch, load and overshoot budget (exact lossless line, ramp drive, FFT), replacing the
   contested t_r/6 vs t_r/2; (b) Kramers-Kronig: a causal wideband-Debye (Djordjevic-Sarkar)
   FR-4 fitted at 1 GHz, its Dk drift per decade versus -(2/pi) tan(delta) ln(10) Dk, and the
   loss length beyond which a line sets its own rise time.

RB4: 60 x 40 mm, 1.6 mm, L1 1 oz signal / 0.1 mm prepreg / L2 GND 0.5 oz / 1.2 mm core /
L3 GND 0.5 oz / 0.1 mm prepreg / L4 1 oz 3.3 V pour; FR-4 er 4.3, tan d 0.02 at 1 GHz.
Circuits as in worked-thought-experiments.md (12 V buck, MCU, USB 2.0 HS, 24 MHz crystal,
24-bit ADC, 2.4 GHz radio, USB-C).  Values marked "assumed" are illustrative design points.

Run:  python ls_regime_map.py      (numpy only, a few seconds)
"""
import math

import numpy as np

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
C0 = 299792458.0
ETA0 = 376.73
RHO = 1.72e-8
SIG = 1 / RHO
ER, TAND = 4.3, 0.02
mm = 1e-3


def rs(t):
    return RHO / t


def delta(f):
    return math.sqrt(RHO / (math.pi * f * MU0))


def ell_m(f, t):
    return rs(t) / (math.pi * MU0 * f)


def ms_z0(w, h, er=ER):
    """Hammerstad-Jensen-style microstrip Z0 and eps_eff (zero thickness)."""
    u = w / h
    ee = (er + 1) / 2 + (er - 1) / 2 / math.sqrt(1 + 12 / u)
    if u <= 1:
        z = 60 / math.sqrt(ee) * math.log(8 / u + u / 4)
    else:
        z = 120 * math.pi / math.sqrt(ee) / (u + 1.393 + 0.667 * math.log(u + 1.444))
    return z, ee


# ------------------------------------------------------------------ part 1: scales
def scales():
    print("== 1. characteristic lengths of a PCB (RB4 unless stated), ordered")
    v = C0 / math.sqrt(ER)
    t05, t1 = 17.5e-6, 35e-6
    rows = []
    rows.append(("skin depth at 2.45 GHz", delta(2.45e9), "Cu"))
    rows.append(("skin depth at 100 MHz", delta(1e8), "Cu"))
    rows.append(("plane copper L2/L3 (0.5 oz)", t05, ""))
    rows.append(("skin depth = 0.5 oz thickness at f", t05, f"f = {RHO/(math.pi*MU0*t05**2)/1e6:.1f} MHz"))
    rows.append(("plane resolution length l_m at 2 MHz, 0.5 oz", ell_m(2e6, t05), "l_m = delta^2/t"))
    rows.append(("prepreg height h (L1-L2)", 0.1e-3, ""))
    rows.append(("plane resolution length l_m at 500 kHz, 0.5 oz", ell_m(5e5, t05), "buck fundamental"))
    rows.append(("evanescent length of higher plane-pair modes d/pi (1.2 mm core)", 1.2e-3 / math.pi, ""))
    rp = 0.15e-3; tp = 25e-6
    rvia = RHO * 1.6e-3 / (math.pi * (2 * rp - tp) * tp)
    rows.append(("via-row transfer length L_T (0.3 mm via, 1 mm pitch, 1 oz + 1 oz)", 1e-3 * math.sqrt(rvia / (2 * rs(t1))), "p sqrt(R_via/(R_s1+R_s2))"))
    rows.append(("fibre-weave bundle pitch (1080/2116)", 0.45e-3, "fixed by glass style"))
    rows.append(("core height (L2-L3)", 1.2e-3, ""))
    rows.append(("copper thermal diffusion length sqrt(alpha t) at 10 ms", math.sqrt(1.1e-4 * 0.01), "pulse heating"))
    rows.append(("v t_r / 6 at t_r = 100 ps", v * 100e-12 / 6, "'review' electrical length"))
    for pitch, label in ((10e-3, "10 mm"),):
        kp = math.sqrt(2 * math.pi / (pitch ** 2 * (math.log(pitch / (2 * math.pi * 0.15e-3)) + 0.5275)))
        rows.append((f"stitching-lattice screening 1/k_p ({label} pitch)", 1 / kp, "below f_p"))
    rows.append(("decap reach lambda_pdn, 0.1 mm L3-L4 pair, 10 mm pitch, 0.7 nH", math.sqrt(0.7e-9 / (MU0 * 0.1e-3 * 1e4)), "SRF < f < f_p"))
    rows.append(("lambda_g/10 at 2.45 GHz (microstrip)", v / 2.45e9 / 10 * math.sqrt(ER / 3.3), ""))
    rows.append(("Chu-sphere radius, 2.4 GHz BLE band", 7.5e-3, "rf-geometry.md"))
    rows.append(("plane resolution length l_m at 20 kHz (audio top), 0.5 oz", ell_m(2e4, t05), ""))
    rows.append(("v t_r / 6 at t_r = 1 ns", v * 1e-9 / 6, ""))
    rows.append(("lambda/2pi at 2.45 GHz (air): reactive near field", C0 / 2.45e9 / (2 * math.pi), ""))
    rows.append(("thermal spreading length (4L planes, still air)", 46e-3, "thermal-physics.md"))
    rows.append(("board size", 60e-3, "RB4"))
    rows.append(("plane-pair half wavelength at 1 GHz", v / 1e9 / 2, "cavity scale"))
    rows.append(("dielectric loss length (line sets its own 100 ps edge)", 100e-12 * C0 / (3.08 * math.sqrt(ER) * TAND), "c t_r/(3.08 sqrt(er) tan d)"))
    rows.append(("cable length", 1.0, "lambda/2 at 150 MHz"))
    rows.append(("plane resolution length l_m at 50 Hz, 0.5 oz", ell_m(50, t05), "mains: plane transparent"))
    rows.append(("lambda/2pi at 30 MHz (air)", C0 / 30e6 / (2 * math.pi), "board+cable in its own near field"))
    rows.sort(key=lambda r: r[1])
    for name, val, note in rows:
        print(f"   {val*1e3:12.4g} mm  {name}  {('(' + note + ')') if note else ''}")
    print("== 1b. characteristic times, ordered")
    w05 = 2 * rs(t05) / MU0
    trows = [
        ("charge relaxation of copper eps0/sigma", EPS0 / SIG, ""),
        ("transit across a 0.1 mm dielectric", 0.1e-3 / v, ""),
        ("fast edge (10 Gb/s class)", 35e-12, ""),
        ("transit across the 60 mm board", 0.06 / v, ""),
        ("USB 2.0 HS edge", 0.5e-9, ""),
        ("buck switch-node edge", 2e-9, ""),
        ("hot-loop ring period (1 nH, 1 nF C_oss)", 2 * math.pi * math.sqrt(1e-9 * 1e-9), ""),
        ("receding-image hold time, h = 0.1 mm, 0.5 oz plane", 0.1e-3 / w05, "h/w_s, w_s = 2R_s/mu0"),
        ("decap L/ESR (0.7 nH, 10 mOhm)", 0.7e-9 / 0.01, ""),
        ("buck switching period (500 kHz)", 2e-6, ""),
        ("receding-image hold time, 4 mm hot loop, 0.5 oz", 4e-3 / w05, "a/w_s"),
        ("receding-image hold time, 60 mm board, 0.5 oz", 0.06 / w05, "below this rate the plane is resistive at board scale"),
        ("surface charge relaxation, 1 mm gap, humid + residue (sigma_s 1e-9 S/sq, assumed)", EPS0 * 2.65 * 1e-3 / 1e-9, ""),
        ("FR-4 through-plane thermal diffusion, 0.1 mm", (0.1e-3) ** 2 / 1.5e-7, ""),
        ("copper lateral thermal diffusion over 10 mm", (10e-3) ** 2 / 1.1e-4, ""),
        ("surface charge relaxation, 1 mm gap, clean 50% RH (sigma_s 1e-14 S/sq, assumed)", EPS0 * 2.65 * 1e-3 / 1e-14, ""),
        ("FR-4 bulk charge relaxation (rho_v 1e12 Ohm m, assumed)", EPS0 * ER * 1e12, ""),
        ("board thermal time constant rho c t /(2h), still air", 1850 * 1100 * 1.6e-3 / 20, ""),
        ("CAF/ECM qualification (85 C/85% RH)", 500 * 3600, "hv-and-manufacturing-physics.md"),
    ]
    trows.sort(key=lambda r: r[1])
    for name, val, note in trows:
        print(f"   {val:12.3g} s   {name}  {('(' + note + ')') if note else ''}")
    print(f"   two speeds: signal v = {v:.3g} m/s; receding image w_s = {w05:.0f} m/s (0.5 oz), {2*rs(t1)/MU0:.0f} m/s (1 oz);"
          f" ratio v/w_s(1 oz) = {v/(2*rs(t1)/MU0):.2e}; eta0/R_s(1 oz) = {ETA0/rs(t1):.2e}")
    a = 10e-3
    print(f"   mirror window of a {a*1e3:.0f} mm structure (1 oz): f from R_s/(pi mu0 a) = {rs(t1)/(math.pi*MU0*a)/1e3:.1f} kHz "
          f"to v/(10 a) = {v/(10*a)/1e9:.2f} GHz, a ratio of {v/(10*a)/(rs(t1)/(math.pi*MU0*a)):.2e}")


# ------------------------------------------------------------------ part 2: the impedance-level split
def split_check():
    print("== 2. impedance-level split: short two-port between equal terminations Z, exact ABCD vs series")
    print("     theta    Z0/Z   |H|/|H0| - 1 exact   (theta^2/8)(m-1/m)^2   phase exact   theta(m+1/m)/2")
    for theta in (0.05, 0.2):
        for m in (0.1, 0.5, 1.0, 2.0, 10.0):
            Z0, Z = m, 1.0
            A = D = math.cos(theta); B = 1j * Z0 * math.sin(theta); C = 1j * math.sin(theta) / Z0
            H = Z / (A * Z + B + C * Z * Z + D * Z)
            amp = abs(H) / 0.5 - 1
            print(f"     {theta:5.2f}  {m:6.2f}   {amp:+12.3e}          {-(theta**2/8)*(m-1/m)**2:+12.3e}     "
                  f"{-np.angle(H):8.4f}      {theta*(m+1/m)/2:8.4f}")


# ------------------------------------------------------------------ part 3: regime map
def regime_map():
    print("== 3. regime map for RB4 (theta at the band top; Z0/Z at that frequency; S/B = signal / budget)")
    v = C0 / math.sqrt(ER)
    t05 = 17.5e-6
    z_ms50 = ms_z0(0.19e-3, 0.1e-3)
    z_wide = ms_z0(2e-3, 0.1e-3)
    S = []

    def add(name, l, f_lo, f_hi, Z, Z0, ee, SB, scale_a, h, extra, model):
        """Z or Z0 = None: no circuit impedance level applies (resonators, antennas, DC victims)."""
        th = 2 * math.pi * f_hi * l * math.sqrt(ee) / C0
        if Z is None or Z0 is None:
            m = eL = eC = float("nan")
        else:
            m = Z0 / Z
            eL, eC = th * m, th / m
        lm = ell_m(f_lo, t05)
        S.append((name, l, f_lo, f_hi, th, m, eL, eC, (2 * h / lm) if h else float("nan"),
                  (scale_a / lm) if scale_a else float("nan"), SB, extra, model))

    # 1 hot loop: 12 V -> 1.2 V, 10 A, 2 ns edges, 4 mm x 2 mm loop on 2 mm copper over L2 at 0.1 mm
    add("buck hot loop (12 V, 10 A, 2 ns)", 8e-3, 5e5, 0.35 / 2e-9, 12 / 10, z_wide[0], z_wide[1], 3.2, 4e-3, 0.1e-3,
        "Q of L-C_oss ring 30-170 (power-copper.md)", "order 1 is O(1) and resonant: co-simulate L with C_oss (C2); F2 image PEEC; complex images at f_sw")
    # 2 switch node -> crystal (E-field), victim impedance ~ 1/(w C_L) at the band top
    fhi = 0.35 / 2e-9
    zv = 1 / (2 * math.pi * fhi * 10e-12)
    eps_c = 2 * math.pi * fhi * 1e-15 * zv
    add("SW node -> crystal XIN (1 fF, 10 pF load)", 3e-3, 5e5, fhi, zv, z_ms50[0], z_ms50[1], 12 / 1e-3, 0, 0,
        f"eps = w C_m Z_victim = {eps_c:.1e}; x S/B = {eps_c*12/1e-3:.2f}", "order 1 coupling (C_m) with plane image; F1 per-layer kernel")
    # 3 SPI clock 48 MHz, 1 ns, 30 mm, 50 ohm, CMOS load 5 pF
    zl = 1 / (2 * math.pi * 0.35e9 * 5e-12)
    add("SPI clock 48 MHz, 1 ns, 30 mm", 30e-3, 48e6, 0.35e9, zl, z_ms50[0], z_ms50[1], 10, 0, 0.1e-3,
        "source 30 Ohm < Z0: underdamped; see part 4", "order 2 (line + load ring): critical-length family; TL in SPICE (C2)")
    # 4 USB 2.0 HS pair, matched
    z_usb = 45.0
    add("USB 2.0 HS pair, 25 mm, matched", 25e-3, 240e6, 0.35 / 0.5e-9, z_usb, z_usb, 3.3, 100, 0, 0.1e-3,
        "matched: amplitude error ~ theta^2 (m-1/m)^2/8 + tolerance; skew -> CM (EMI)", "order 1 delay + Bal; F1 cross-section; skew budget from EMI")
    # 5 MCU PDN on the L3-L4 0.1 mm pair, 30 mm wide, target 0.5 ohm
    z0_pp = ETA0 * 0.1e-3 / (30e-3 * math.sqrt(ER))
    add("MCU PDN, L3-L4 pair 0.1 mm, target 0.5 Ohm", 30e-3, 1e6, 0.35e9, 0.5, z0_pp, ER, 33, 0, 0,
        f"N_sq = Lc/(mu0 d) = {0.7e-9/(MU0*0.1e-3):.1f}: continuum decap field", "2-D telegrapher sheet (wire medium); lumped only near f_p")
    # 6 crystal node 24 MHz, 3 mm trace
    zx = 1 / (2 * math.pi * 24e6 * 10e-12)
    add("24 MHz crystal node, 3 mm", 3e-3, 24e6, 24e6, zx, z_ms50[0], z_ms50[1], 10, 0, 0,
        "eps_C = C_trace/C_L; pull 45 ppm/pF", "order 1 (C to plane and to aggressors)")
    # 7 24-bit ADC input
    add("24-bit ADC bridge input (DC-10 Hz)", 20e-3, 1, 10, None, None, z_ms50[1], 78e-3 / 9.3e-9, 0, 0,
        "foreign current x shared R; Seebeck x grad T; leakage; plane is resistive (l_m >> board)", "orders 1-4 at DC: resistive sheet, thermal field, thermal EMF, leakage network")
    # 8 plane return of the buck fundamental
    add("return of the buck fundamental in L2 (0.5 oz)", 60e-3, 5e5, 5e5, 1.2, z_wide[0], z_wide[1], 1e3, 4e-3, 0.1e-3,
        "2h < l_m(f_sw) < loop size: transition band", "complex images (4-6) on intact planes; meshed thin-sheet solve near slots")
    # 9 GND/GND cavity
    add("L2-L3 GND/GND cavity, 60 x 40 mm, 10 mm stitching", 60e-3, 0.7e9, 2.45e9, None, None, ER, float("nan"), 0, 0,
        "f_p(10 mm) = 3.39 GHz > 2.45 GHz: screened; 20 mm pitch (1.52 GHz) would propagate", "wire-medium plasma model; eigenmodes only if f > f_p")
    # 10 USB cable common mode
    add("USB cable CM, 1 m", 1.0, 30e6, 300e6, None, None, 1.0, float("nan"), 0, 0,
        "cable is lambda/2 at 150 MHz; board (60 mm) is a lumped CM source", "MREMC-type chain; board as lumped source; cable as antenna")
    # 11 antenna + ground plane
    add("2.45 GHz chip antenna + 60 mm ground plane", 60e-3, 2.4e9, 2.5e9, None, None, 1.0, float("nan"), 0, 0,
        "plane ~ lambda/2: part of the radiator", "full wave (F3) + vendor reference; radiation is the function")
    # 12 RF feed
    add("RF feed 50 Ohm, 3 mm", 3e-3, 2.4e9, 2.5e9, 50, z_ms50[0], z_ms50[1], 100, 0, 0,
        "matched: phase only", "order 1 (delay, pin Q); F1")
    # 13 ESD path through TVS ground via, via to L2 (0.03 nH) vs through to L4 (1.3 nH)
    for lab, Lv in (("ESD via to L2 (0.03 nH)", 0.03e-9), ("ESD via through to L4 (1.3 nH)", 1.3e-9)):
        z_clamp = 10 / 30
        fk = 0.35 / 0.8e-9
        eL = 2 * math.pi * fk * Lv / z_clamp
        S.append((lab, 0.1e-3 if Lv < 1e-10 else 1.5e-3, fk, fk, float("nan"), float("nan"), eL, float("nan"),
                  float("nan"), float("nan"), float("nan"), f"w L / Z_clamp = {eL:.2g} (30 A, 0.8 ns, 10 V clamp)",
                  "order 1 if eps_L < 1, else the parasitic is the circuit: time-domain with nonlinear clamp"))
    # 14 thermal
    S.append(("buck heat 0.4 W on RB4", 60e-3, 0, 0, float("nan"), float("nan"), float("nan"), float("nan"),
              float("nan"), float("nan"), float("nan"), "board/lambda_th = 60/46 = 1.3 (< 2: near-isothermal plus peaks)",
              "fin kernel + edge images; FV on accepted moves"))
    # 15 high-Z input leakage
    tau = EPS0 * 2.65 * 1e-3 / 1e-12
    S.append(("electrometer input, 1 mm gap to 3.3 V, humid (sigma_s 1e-12)", 5e-3, 0, 10, float("nan"), float("nan"),
              float("nan"), float("nan"), float("nan"), float("nan"), float("nan"), f"tau_e = {tau:.2g} s: resistive below {1/(2*math.pi*tau):.0f} Hz",
              "leakage network (G) + guard; capacitive (EQS) above 1/(2 pi tau_e)"))
    print("     structure                                   l(mm)  theta    Z0/Z    eps_L    eps_C   2h/l_m  a/l_m     S/B")
    for r in S:
        name, l, flo, fhi, th, m, eL, eC, hl, al, SB, extra, model = r
        def fmt(x):
            return "     -  " if (x is None or (isinstance(x, float) and math.isnan(x))) else f"{x:8.3g}"
        print(f"     {name[:44]:44s} {l*1e3:6.1f} {fmt(th)} {fmt(m)} {fmt(eL)} {fmt(eC)} {fmt(hl)} {fmt(al)} {fmt(SB)}")
        print(f"        -> {extra}; model: {model}")
    print("   required order n* = ceil(ln(B/S)/ln eps) for a victim with budget/signal B/S and a small parameter eps:")
    for eps in (0.1, 0.01):
        for lab, bs in (("10% digital", 0.1), ("1 mV on 3.3 V", 3e-4), ("16-bit", 1.5e-5), ("24-bit", 1.2e-7)):
            print(f"     eps={eps:5.2f}  {lab:14s}: n* = {math.ceil(math.log(bs)/math.log(eps) - 1e-9)}")


# ------------------------------------------------------------------ part 4a: critical length family
def ramp_response(Td, tr, Rs, CL, Z0=50.0, Tw=None, N=2 ** 15):
    """Load voltage of a lossless line (delay Td) driven through Rs by a 0..1 V ramp of rise tr into CL."""
    Tw = Tw or max(40 * Td + 20 * tr, 40e-9)
    dt = Tw / N
    t = np.arange(N) * dt
    vs = np.clip(t / tr, 0, 1)
    vs[t > Tw / 2] = 0.0  # a long pulse so the FFT is periodic; we read only the first half
    Vs = np.fft.rfft(vs)
    w = 2 * math.pi * np.fft.rfftfreq(N, dt)
    w[0] = 1e-3
    ZL = 1 / (1j * w * CL)
    A = D = np.cos(w * Td)
    B = 1j * Z0 * np.sin(w * Td)
    C = 1j * np.sin(w * Td) / Z0
    H = ZL / (A * ZL + B + C * Rs * ZL + D * Rs)
    vl = np.fft.irfft(Vs * H, N)
    half = t < Tw / 2 * 0.95
    return t[half], vl[half]


def critical_length():
    print("== 4a. critical length: largest Td/t_r with load overshoot <= budget (exact lossless line, ramp drive)")
    tr = 1e-9
    ratios = np.concatenate([np.linspace(0.02, 0.3, 15), np.linspace(0.32, 1.5, 30)])
    print("     Rs/Z0   CL (pF, Z0 CL/t_r)    Td/t_r at overshoot 5% / 10% / 20%      overshoot at Td = t_r/6 , t_r/2")
    for Rs in (5.0, 15.0, 30.0, 50.0):
        for CL in (2e-12, 10e-12):
            ov = []
            for r in ratios:
                _, vl = ramp_response(r * tr, tr, Rs, CL)
                ov.append(max(vl.max() - 1.0, 0.0))
            ov = np.array(ov)

            def first_exceed(level):
                idx = np.nonzero(ov > level)[0]
                return ratios[idx[0]] if idx.size else float("inf")
            o6 = max(ramp_response(tr / 6, tr, Rs, CL)[1].max() - 1, 0)
            o2 = max(ramp_response(tr / 2, tr, Rs, CL)[1].max() - 1, 0)
            cells = " / ".join("  >1.5" if math.isinf(first_exceed(x)) else f"{first_exceed(x):6.2f}" for x in (0.05, 0.10, 0.20))
            print(f"     {Rs/50:5.2f}   {CL*1e12:4.0f} ({50*CL/tr:4.2f})              {cells}               {o6*100:5.1f}% , {o2*100:5.1f}%")
    print("     (Johnson: review above t_r/6; LearnEMC/ADI: terminate above t_r/2. Inf = never exceeds within 1.5 t_r)")


# ------------------------------------------------------------------ part 4b: Kramers-Kronig
def djordjevic_sarkar(f, einf, de, m1=3.0, m2=12.0):
    w = 2 * math.pi * f
    w1, w2 = 2 * math.pi * 10 ** m1, 2 * math.pi * 10 ** m2
    return einf + de / (m2 - m1) * np.log10((w2 + 1j * w) / (w1 + 1j * w))


def kk():
    print("== 4b. causality: wideband Debye (Djordjevic-Sarkar) FR-4 fitted to Dk 4.3, Df 0.02 at 1 GHz")
    # solve for einf, de from eps(1 GHz) = 4.3 (1 - j 0.02)
    f0 = 1e9
    g = djordjevic_sarkar(f0, 0.0, 1.0)  # unit-de shape
    de = -(4.3 * 0.02) / g.imag
    einf = 4.3 - de * g.real
    print(f"   fit: eps_inf = {einf:.3f}, delta_eps = {de:.3f} (poles 1 kHz .. 1 THz)")
    for f in (1e6, 1e8, 1e9, 1e10, 2.5e10):
        e = djordjevic_sarkar(f, einf, de)
        print(f"   f = {f:8.0e} Hz: Dk = {e.real:.3f}, Df = {-e.imag/e.real:.4f}")
    e1, e2 = djordjevic_sarkar(1e8, einf, de).real, djordjevic_sarkar(1e9, einf, de).real
    print(f"   Dk drift per decade (100 MHz -> 1 GHz) = {(e2-e1)/e2*100:+.2f}%; KK estimate -(2/pi) tan d ln10 = "
          f"{-(2/math.pi)*0.02*math.log(10)*100:+.2f}%; a 'flat Dk, flat Df' model violates causality")
    z1 = 1 / math.sqrt(djordjevic_sarkar(1e6, einf, de).real)
    z2 = 1 / math.sqrt(djordjevic_sarkar(5e9, einf, de).real)
    print(f"   stripline Z0 and delay between 1 MHz and 5 GHz: Z0 {(z2/z1-1)*100:+.1f}%, delay {(z1/z2-1)*100:+.1f}%")
    for tr in (100e-12, 35e-12):
        print(f"   loss length (line's own 10-90% rise = t_r) for t_r = {tr*1e12:.0f} ps: "
              f"{tr*C0/(3.08*math.sqrt(ER)*TAND)*1e3:.0f} mm (tan d 0.02), "
              f"{tr*C0/(3.08*math.sqrt(3.6)*0.004)*1e3:.0f} mm (low-loss, Dk 3.6, tan d 0.004)")


if __name__ == "__main__":
    scales()
    split_check()
    regime_map()
    critical_length()
    kk()
