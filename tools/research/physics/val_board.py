# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Design-stage predictions for the first validation board, VAL-1 (validation program).

Used by docs/topics/physics/validation-program.md. VAL-1 is a 4-layer board (12 V -> 3.3 V
buck, MCU/2.4 GHz module with USB 2.0, 24-bit ADC front end) laid out twice: R (rule-following)
and P (physics-first). The registered predictions are recomputed from the frozen copper by
the system's own evaluators before fabrication; this script gives the design-stage values and
intervals that set expectations and fix the methods. Three sections:

  ring  switch-node ring of the buck: frequency, Q, overshoot, ring-band emission and snubber
        loss for five variants selectable by population: S0 no snubber; S1 textbook RC
        (C_s = 3 C_oss at the pins, L_s ~ 0.2 L); S2 tuned RC (C_s = C_oss, L_s ~ L: lens TH's
        Den Hartog absorber); S3 S1 placed far (L_s ~ L); E1 no snubber, slowed edge (boot
        resistor, t_sw 1.5 -> 4 ns). Model: series loop (L, R = Z0/Q0) driving the switch node
        (C_oss || snubber branch) with an erf voltage edge (dr_switch_cell_budget.py), solved as
        an ODE; worst modal Q from the characteristic polynomial (th_damping_ledger.py). Also the
        spectrum-analyser reading of the ring: comb line at f_ring ~ A f_sw Q / (pi f_ring).
  adc   DC transfer resistance from a 1 A ground-current injector to the ADC's bridge reading,
        on a generic 80 x 60 mm board (0.5 oz inner GND plane): R arm returns the bridge
        excitation into the plane at the sensor connector and references REFN at the ADC;
        P arm senses REFN at the connector (Kelvin) and returns the excitation on its own trace,
        tying it to the plane at one point. Sheet Laplace (ct_cut_topology.sheet_laplacian).
  pdn   |Z| at an IC supply pin, 1-500 MHz, for two layer assignments of the same decaps:
        R: 3.3 V on L3 across the 1.265 mm core; P: 3.3 V pour on L1 over the L2 GND at
        0.0994 mm. Continuum plane-pair model with decaps (ls_post_lattice.continuum_zin) plus
        via and mounting inductance.

Run:  python tools/research/physics/val_board.py [ring|adc|pdn]   (numpy + scipy, ~1-2 min)
"""
import math
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np  # noqa: E402
from scipy.integrate import solve_ivp  # noqa: E402
from scipy.special import erf, kv  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ct_cut_topology as ct  # noqa: E402  (sheet Laplacian, reused)
import th_damping_ledger as th  # noqa: E402  (snubber Q ledger, reused)

MU0, EPS0 = 4e-7 * math.pi, 8.854e-12
K_RISE = 2.563
V_IN, I_L, F_SW = 12.0, 2.0, 1.0e6


# ----------------------------------------------------------------------------------------------- ring
def simulate(L, C, Q0, t_sw, snub=None):
    """Switch-node voltage after the high-side turn-on: erf collapse of V_ds,hs with 10-90 % time t_sw.
    snub = (C_s, L_s, R_s) or None. Returns t, v."""
    sigma = t_sw / K_RISE
    z0 = math.sqrt(L / C)
    R = z0 / Q0
    T = 2 * math.pi * math.sqrt(L * C)
    t0 = 4 * sigma
    t_end = t0 + 4 * sigma + 8 * T

    def vhs(t):
        return V_IN * 0.5 * (1 - erf((t - t0) / (math.sqrt(2) * sigma)))

    def f(t, y):
        i, v, i_s, v_cs = y
        i_d = 50.0 * max(0.0, -0.7 - v)
        di = (V_IN - vhs(t) - v - R * i) / L
        if snub is None:
            return [di, (i - I_L + i_d) / C, 0.0, 0.0]
        cs, ls, rs = snub
        return [di, (i - I_L + i_d - i_s) / C, (v - v_cs - rs * i_s) / ls, i_s / cs]
    y0 = [0.0, -0.7 - I_L / 50.0, 0.0, -0.7 - I_L / 50.0]
    sol = solve_ivp(f, (0.0, t_end), y0, method="LSODA", max_step=min(sigma, T) / 40, rtol=1e-7, atol=1e-10)
    return sol.t, sol.y[1]


def worst_q(L, C, Q0, snub):
    if snub is None:
        return Q0
    cs, ls, rs = snub
    z0 = math.sqrt(L / C)
    return th.worst_q(cs / C, ls / L, rs / z0, 1.0, Q0)


def best_rs(L, C, Q0, cs, ls):
    z0 = math.sqrt(L / C)
    rs = np.logspace(-2, 1.5, 200) * z0
    q = [worst_q(L, C, Q0, (cs, ls, r)) for r in rs]
    return rs[int(np.argmin(q))]


def ring_band_db(L, C, Q0, snub):
    """Peak of the loop-current spectrum relative to no snubber (th_damping_ledger emission proxy)."""
    if snub is None:
        return 0.0
    cs, ls, rs = snub
    z0 = math.sqrt(L / C)
    base, _ = th.loop_current_peak(3, 0.0, None, 1.0, Q0, snub=False)
    pk, _ = th.loop_current_peak(cs / C, ls / L, rs / z0, 1.0, Q0)
    return 20 * math.log10(pk / base)


def variants(L, C, Q0):
    ls_near = 0.2 * L
    out = {"S0 none": (None, 1.5e-9)}
    rs1 = best_rs(L, C, Q0, 3 * C, ls_near)
    out["S1 textbook 3C, at pins"] = ((3 * C, ls_near, rs1), 1.5e-9)
    rs2 = best_rs(L, C, Q0, C, L)
    out["S2 tuned C, L_s = L"] = ((C, L, rs2), 1.5e-9)
    out["S3 textbook 3C, far (L_s = L)"] = ((3 * C, L, rs1), 1.5e-9)
    out["E1 no snubber, t_sw 4 ns"] = (None, 4.0e-9)
    return out


def ring_metrics(L, C, Q0, snub, t_sw):
    t, v = simulate(L, C, Q0, t_sw, snub)
    k = int(np.argmax(v))
    ovs = (v[k] - V_IN) / V_IN
    q = worst_q(L, C, Q0, snub)
    fr = 1 / (2 * math.pi * math.sqrt(L * C))
    # ring-band change from the edge itself, relative to 1.5 ns: an erf (Gaussian) edge falls super-exponentially,
    # a trapezoid's envelope as 1/(pi f t_r); the true edge lies between, so the slow-edge variant gets both bounds
    edge_gauss = 20 * math.log10(math.exp(-0.5 * (2 * math.pi * fr * t_sw / K_RISE) ** 2)
                                 / math.exp(-0.5 * (2 * math.pi * fr * 1.5e-9 / K_RISE) ** 2))
    edge_trap = 20 * math.log10(min(1.0, 1 / (math.pi * fr * t_sw)) / min(1.0, 1 / (math.pi * fr * 1.5e-9)))
    band = ring_band_db(L, C, Q0, snub) + edge_trap
    band_g = ring_band_db(L, C, Q0, snub) + edge_gauss
    loss = (snub[0] * V_IN ** 2 * F_SW) if snub is not None else 0.0
    loss += 0.5 * V_IN * I_L * max(t_sw - 1.5e-9, 0.0) * F_SW     # extra turn-on loss of a slowed edge
    amp = max(v[k] - V_IN, 0.0)
    line = amp * F_SW * q / (math.pi * fr)          # spectrum-analyser comb line at f_ring (V peak)
    return ovs, q, band, loss, line, band_g


def sec_ring():
    print("== ring: 12 V -> 3.3 V buck switch node, I_L 2 A, f_sw 1 MHz; arms R (lateral loop) and P (tight, overlapped loop)")
    arms = {"R": (1.0e-9, (0.8e-9, 1.3e-9)), "P": (0.6e-9, (0.5e-9, 0.8e-9))}
    C, c_rng, Q0, q_rng = 150e-12, (100e-12, 220e-12), 10.0, (5.0, 20.0)
    rng = np.random.default_rng(3)
    summary = {}
    for arm, (L, l_rng) in arms.items():
        fr = 1 / (2 * math.pi * math.sqrt(L * C))
        fr_lo = 1 / (2 * math.pi * math.sqrt(l_rng[1] * c_rng[1]))
        fr_hi = 1 / (2 * math.pi * math.sqrt(l_rng[0] * c_rng[0]))
        print(f"\n  arm {arm}: L_loop {L*1e9:.2f} nH [{l_rng[0]*1e9:.1f}, {l_rng[1]*1e9:.1f}], C_oss {C*1e12:.0f} pF "
              f"[{c_rng[0]*1e12:.0f}, {c_rng[1]*1e12:.0f}], Q0 {Q0:.0f} [{q_rng[0]:.0f}, {q_rng[1]:.0f}]: "
              f"f_ring {fr/1e6:.0f} MHz [{fr_lo/1e6:.0f}, {fr_hi/1e6:.0f}], Z0 {math.sqrt(L/C):.2f} ohm")
        print("     variant                        overshoot %        worst Q        ring band dB vs S0     loss W    comb line at f_ring")
        draws = [(math.exp(rng.uniform(*np.log(l_rng))), math.exp(rng.uniform(*np.log(c_rng))),
                  math.exp(rng.uniform(*np.log(q_rng)))) for _ in range(24)]
        nominal = variants(L, C, Q0)
        summary[arm] = {}
        for name, (snub, tsw) in nominal.items():
            o, q, b, w, line, bg = ring_metrics(L, C, Q0, snub, tsw)
            mc = []
            for (l_, c_, q_) in draws:
                vv = variants(l_, c_, q_)[name]
                mc.append(ring_metrics(l_, c_, q_, vv[0], vv[1]))
            mc = np.array(mc)
            lo_b = min(np.percentile(mc[:, 2], 5), np.percentile(mc[:, 5], 5))
            hi_b = max(np.percentile(mc[:, 2], 95), np.percentile(mc[:, 5], 95))
            summary[arm][name] = (o, q, b, w)
            print(f"     {name:30s} {o*100:5.1f} [{np.percentile(mc[:,0],5)*100:4.0f},{np.percentile(mc[:,0],95)*100:4.0f}]"
                  f"   {q:5.2f} [{np.percentile(mc[:,1],5):4.1f},{np.percentile(mc[:,1],95):4.1f}]"
                  f"   {b:+6.1f} [{lo_b:+.0f},{hi_b:+.0f}]"
                  f"        {w:5.3f}     {line*1e3:6.2f} mV pk")
    r = summary["R"]
    s1, s2, s3, e1 = (r[k] for k in ("S1 textbook 3C, at pins", "S2 tuned C, L_s = L", "S3 textbook 3C, far (L_s = L)",
                                     "E1 no snubber, t_sw 4 ns"))
    print("\n  registered differential predictions, arm R (same board, variants by population):")
    print(f"   - tuned S2 vs textbook S1: ring band {s2[2]-s1[2]:+.1f} dB, worst Q {s2[1]:.2f} vs {s1[1]:.2f},"
          f" snubber loss {s2[3]/s1[3]:.2f}x")
    print(f"   - textbook moved far (S3 vs S1): worst Q {s3[1]:.2f} vs {s1[1]:.2f}, ring band {s3[2]-s1[2]:+.1f} dB")
    print(f"   - slowed edge E1 vs S0: overshoot {e1[0]*100:.0f}% vs {r['S0 none'][0]*100:.0f}%, Q unchanged,"
          f" extra loss {e1[3]*1e3:.0f} mW (ring-band bounds: trapezoid to Gaussian edge, see table)")
    p_ = summary["P"]
    print(f"   - arm P vs R, no snubber: overshoot {p_['S0 none'][0]*100:.0f}% vs {r['S0 none'][0]*100:.0f}%;"
          f" f_ring ratio sqrt(1.0/0.6) = {math.sqrt(1/0.6):.2f}")


# ----------------------------------------------------------------------------------------------- adc
def sec_adc():
    print("\n== adc: DC transfer resistance, injected ground current -> bridge reading (generic 80 x 60 mm board)")
    d = 0.25                                       # mm cells
    nx, ny = int(80 / d), int(60 / d)
    mask = np.ones((ny, nx), bool)
    rs = 1.72e-8 / 15.2e-6                         # 0.5 oz inner plane
    L, idx = ct.sheet_laplacian(mask, g=1.0 / rs)
    n = L.shape[0]

    def node(x, y):
        return idx[int(y / d), int(x / d)]
    import scipy.sparse.linalg as spla
    inj_a, inj_b = node(4, 8), node(76, 8)         # injector test points along the bottom edge
    conn, adc = node(77, 20), node(58, 20)         # sensor connector ground tie (R arm) and ADC AVSS tie
    keep = np.setdiff1d(np.arange(n), [inj_b])
    b = np.zeros(n)
    b[inj_a] = 1.0
    phi = np.zeros(n)
    lu = spla.splu(L[keep][:, keep].tocsc())
    phi[keep] = lu.solve(b[keep])
    r_t = abs(phi[conn] - phi[adc])
    # sensitivity to the tie positions (+-3 mm) and to copper thickness (+-15 %)
    vals = []
    for dx in (-3, 0, 3):
        for dy in (-3, 0, 3):
            vals.append(abs(phi[node(77, 20 + dy)] - phi[node(58 + dx, 20 + dy)]))
    print(f"   R arm: plane carries the injector current; bridge EXC- into the plane at the connector, REFN at the ADC")
    print(f"     transfer resistance {r_t*1e6:7.1f} uOhm = uV of error per A injected"
          f" [{min(vals)*1e6*0.85:.1f}, {max(vals)*1e6*1.15:.1f}] (tie positions +-3 mm, copper +-15 %)")
    print("   P arm: REFN sensed at the bridge's EXC- pin (Kelvin), excitation returned on its own trace, one plane tie:")
    print("     no plane current flows in the measurement loop at DC, so the transfer resistance is zero by topology;")
    print("     registered bound: < 1 % of R's, limited by the ADC's CMRR (~100 dB) on the mV common-mode shift")
    cm = max(abs(phi[conn]), abs(phi[adc]))
    print(f"     common-mode shift of the tie point {cm*1e3:.2f} mV per A -> {cm*1e-5*1e9:.1f} nV per A at 100 dB CMRR")
    print(f"   24-bit ADC at PGA 128, 20 SPS: ~0.1 uV rms noise, so R's error is {r_t/1e-7:.0f} noise sigmas per A")


# ----------------------------------------------------------------------------------------------- pdn
def zin_plane(f, d, er, lc, pitch, rload):
    """Input impedance at a load via of radius rload in a plane pair (spacing d) loaded by decaps of total
    inductance lc (part + mounting) on a square pitch (continuum wire medium, lens LS)."""
    w = 2 * math.pi * f
    rs_ = 2 * math.sqrt(math.pi * f * MU0 * 1.72e-8) if f > 1e7 else 2 * 1.72e-8 / 35e-6
    zsq = rs_ + 1j * w * MU0 * d
    zpost = 0.01 + 1j * w * lc + 1 / (1j * w * 100e-9)
    g = np.sqrt(zsq * (1j * w * EPS0 * er / d * (1 - 0.02j) + (1 / pitch ** 2) / zpost))
    g = g if g.real >= 0 else -g
    return zsq / (2 * math.pi) * kv(0, g * rload)


def sec_pdn():
    print("\n== pdn: |Z| at an IC 3.3 V pin with the same four 100 nF 0402 decaps (one per 5 mm cell around it)")
    # R: rail on L3, decap and pin reach it through L1 -> L3 vias (1.38 mm); P: rail on L1 over L2 at 0.1 mm
    cases = {"R  rail on L3, core 1.265 mm": dict(d=1.265e-3, er=4.6, via=1.38e-3),
             "P  rail pour on L1 over L2, 0.0994 mm": dict(d=0.0994e-3, er=4.1, via=0.10e-3)}
    l_part = 0.35e-9                               # 0402 MLCC body
    print("   case                                      L_mount/decap  " + "  ".join(f"{f/1e6:5.0f}MHz" for f in (10e6, 50e6, 100e6, 300e6)))
    out = {}
    for name, c in cases.items():
        # mounting: two vias of length 'via' to the rail plane (pair, 0.5 mm apart) + pad loop
        lvia = MU0 * c["via"] / (2 * math.pi) * (math.log(0.5e-3 / 0.15e-3) + 0.5)
        lc = l_part + lvia + 0.15e-9
        zs = [abs(zin_plane(f, c["d"], c["er"], lc, 5e-3, 0.15e-3) + 1j * 2 * math.pi * f * lvia / 2) for f in (10e6, 50e6, 100e6, 300e6)]
        out[name] = zs
        print(f"   {name:42s} {lc*1e9:6.2f} nH      " + "  ".join(f"{z*1e3:7.0f}m" for z in zs))
    a, b = list(out.values())
    ratios = []
    for kv_ in (0.7, 1.0, 1.4):          # via/mounting inductance model error
        for kd in (0.9, 1.1):             # dielectric thickness
            zz = []
            for name, c in cases.items():
                lvia = kv_ * MU0 * c["via"] / (2 * math.pi) * (math.log(0.5e-3 / 0.15e-3) + 0.5)
                lc = l_part + lvia + 0.15e-9
                zz.append(abs(zin_plane(100e6, c["d"] * kd, c["er"], lc, 5e-3, 0.15e-3)
                              + 1j * 2 * math.pi * 100e6 * lvia / 2))
            ratios.append(zz[1] / zz[0])
    print(f"   registered: P/R |Z| ratio at 100 MHz = {b[2]/a[2]:.2f} [{min(ratios):.2f}, {max(ratios):.2f}]")


if __name__ == "__main__":
    which = sys.argv[1:] or ["ring", "adc", "pdn"]
    if "ring" in which:
        sec_ring()
    if "adc" in which:
        sec_adc()
    if "pdn" in which:
        sec_pdn()
