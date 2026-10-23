# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""E5 priors: the budgets (allocations) and excitations of the place terms.

Every number here is a belief of exactness class E5 (conjectured; physics-core-v2 §2):
a datasheet, a simulation or a measurement replaces it through the brief
(`structure['budget']`, `structure['excite']`). Each allocation is derived, not chosen:
the comment on each function gives the physics and its source. The derivations and the
sensitivity of the results to them are in docs/topics/physics/place-terms.md.

Conventions: nH, pF, ns, V, A, W, K, mm. A `Belief` is (value, unit, basis, cls).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Belief:
    value: float
    unit: str
    basis: str
    cls: str = 'E5'

    def to_json(self):
        return {'value': round(self.value, 6), 'unit': self.unit, 'basis': self.basis, 'class': self.cls}


# ----------------------------------------------------------------------------- knobs
# Expected routed copper length of a straight pad-to-pad hop of length l (mm), by the kind
# of structure the hop belongs to: l (1 + c sqrt(l / 1 mm)). Routes detour around pads,
# vias and other nets, more the farther they go (a random obstacle field makes the excess
# grow about as sqrt(l)). c is the least-squares fit (log ratio) over the hops of 69 human
# boards' routed copper (least-L' path per net, kae.route.critical_recheck), measured by
# tools/research/physics/pt_routed_calib.py: decap rail hops 0.127 (614 hops, 90 % board
# bootstrap 0.100-0.145), surge paths 0.110 (297, 0.065-0.130), hot-loop hops 0.087 (32,
# 0.035-0.155), crystal nets 0.048 (41, 0.010-0.100). At 1, 4 and 16 mm a decap hop
# stretches by 1.13, 1.25 and 1.5; a pad-avoiding single-layer route alone gives 1.14 at
# the corpus' typical 2-5 mm (pt_grid_route) (E5: measured on the corpus;
# docs/topics/physics/place-terms.md, "Routed copper").
HOP_DETOUR = {
    'commutation': 0.09,
    'decap': 0.125,
    'esd': 0.11,
    'crystal': 0.05,
}


@dataclass
class Knobs:
    """The few explicit knobs of the objective (everything else is a budget)."""
    barrier: float = 4.0          # phi(u) = u + barrier * max(0, u - 1)^2 ...
    u_sat: float = 10.0           # ... and a logarithmic tail beyond u_sat (estimates 10x over budget are model error)
    use_confidence: bool = True   # weight each structure by the brief's confidence
    hop_detour: object = None     # None: HOP_DETOUR; a number: that c for every kind (0: straight hops);
    #                               a dict: per-kind overrides of HOP_DETOUR
    pair_cos_min: float = 0.3     # loop pairs with |cos| below this are dropped in the fast path
    pour_decaps: bool = True      # decap loops through rail and ground pours when both join the ends
    jit: str = 'auto'             # 'auto' (numba when installed), 'on', 'off' (pure Python)

    def detour(self, kind):
        """c of a structure kind's expected hop detour 1 + c sqrt(l) (see HOP_DETOUR)."""
        d = self.hop_detour
        if d is None:
            return HOP_DETOUR.get(kind, 0.0)
        if isinstance(d, dict):
            return float(d.get(kind, HOP_DETOUR.get(kind, 0.0)))
        return float(d)


def phi(u, barrier=4.0, u_sat=10.0):
    """One currency: utilisation u = spend / allocation, priced linearly below budget, with a
    quadratic barrier above it, and a logarithmic tail beyond u_sat: an estimate an order of
    magnitude over budget says "fails" whatever its exact value (and is as likely an
    estimator outlier: a straight hop through an obstacle, a misidentified structure), so it
    keeps a gradient without dominating every other term. phi and phi' are continuous."""
    if u <= 1.0:
        return u
    if u <= u_sat:
        return u + barrier * (u - 1.0) ** 2
    ps = u_sat + barrier * (u_sat - 1.0) ** 2
    dps = 1.0 + 2.0 * barrier * (u_sat - 1.0)
    return ps + dps * u_sat * math.log(u / u_sat)


# ----------------------------------------------------------------------------- (a) hot loops
V_ABS_LADDER = (5.5, 6.0, 7.0, 10.0, 12.0, 16.0, 18.0, 20.0, 24.0, 28.0, 30.0, 36.0, 40.0, 42.0, 50.0,
                60.0, 65.0, 80.0, 100.0, 150.0, 200.0, 250.0, 400.0, 600.0)

# class -> (C_oss pF, t_sw ns, I A, rating margin, ring Q)
CELL_CLASS = {
    'buck': (100.0, 1.5, 1.0, 1.25, 8.0),          # integrated switches, <= 3 A
    'boost': (100.0, 1.5, 1.0, 1.25, 8.0),
    'bridge_driver': (200.0, 5.0, 1.0, 1.25, 8.0),  # integrated motor driver
    'half_bridge': (500.0, 10.0, 5.0, 1.25, 8.0),   # discrete FETs
    'unknown': (150.0, 3.0, 1.0, 1.25, 8.0),
}


# GaN half-bridges (edges <= 2 ns): C_oss ~ 50-300 pF in EPC/GaN Systems datasheets at the
# currents these boards switch, about 5x below silicon at equal R_on (E5)
GAN_C_OSS_PF = 100.0


def v_abs_rating(v_in, margin=1.25):
    """Smallest standard rating >= margin * V_in (E5: parts are rated one step above)."""
    for v in V_ABS_LADDER:
        if v >= margin * v_in:
            return v
    return margin * v_in


def hot_loop_budget(cell_class='buck', v_in=12.0, c_oss_pf=None, t_sw_ns=None, derate=0.85, q=None):
    """Commutation-loop inductance budget from the allowed switch-node overshoot.

    An erf edge of 10-90 % time t_sw driving the LC of the loop L and the switch C_oss
    overshoots by a = exp(-(2 pi sigma/T)^2 / 2) exp(-pi/(2Q)), sigma = t_sw/2.563,
    T = 2 pi sqrt(L C) (dr_switch_cell_budget.py; schematic-to-physics.md), so
        L_max = sigma^2 / (2 C ln(1/a')),  a' = a exp(pi/(2Q)),
    with a = (derate V_abs - V_in) / V_in and V_abs the next standard rating above
    1.25 V_in. Example: 12 V, 120 pF, 1.5 ns -> 1.3 nH (the ODE gives 1.05 nH)."""
    c0, t0, _, margin, q0 = CELL_CLASS.get(cell_class, CELL_CLASS['unknown'])
    if cell_class == 'half_bridge' and t_sw_ns and t_sw_ns <= 2.0:
        c0 = GAN_C_OSS_PF          # edges this fast mean GaN switches
    c = c_oss_pf or c0
    t = t_sw_ns or t0
    q = q or q0
    v_in = max(v_in, 1.0)
    vabs = v_abs_rating(v_in, margin)
    a = max(1e-3, (derate * vabs - v_in) / v_in)
    ap = a * math.exp(math.pi / (2.0 * q))
    sigma = t / 2.563
    if ap >= 1.0:
        lmax = 50.0
        basis = 'overshoot never reaches the rating: capped at 50 nH'
    else:
        lmax = sigma * sigma / (2.0 * c * 1e-3 * math.log(1.0 / ap))     # ns^2 / nF = nH
        basis = (f'overshoot: L_max = sigma^2/(2 C ln(1/a\')), {cell_class}, V_in {v_in:g} V, V_abs {vabs:g} V, '
                 f'C_oss {c:g} pF, t_sw {t:g} ns, a = {a:.2f}')
    return Belief(min(lmax, 50.0), 'nH', basis)


# Input voltage of a converter whose input rail the brief cannot name (excite.V null, about
# 20 % of cells). A high prior, so these loops still count rather than vanish: 24 V lies above
# 90 % of the 51 named converter inputs of the 112-board corpus (median 12 V, p80 15 V), and a
# higher V_in both tightens the overshoot budget and raises the excitation (E5).
V_IN_UNKNOWN = Belief(24.0, 'V', 'unnamed converter input: high prior, above 90 % of named inputs in the corpus')


def hot_loop_excite(cell_class='buck', v_in=12.0, i_out=None, t_sw_ns=None):
    """(dI/dt A/ns, dV/dt V/ns, I A, V V, t_sw ns) of a commutation cell (E5 class priors)."""
    c0, t0, i0, _, _ = CELL_CLASS.get(cell_class, CELL_CLASS['unknown'])
    t = t_sw_ns or t0
    i = i_out or i0
    return dict(didt=i / t, dvdt=v_in / t, I=i, V=v_in, t_sw=t)


# ----------------------------------------------------------------------------- ownership
def ownership_calibrated(p):
    """Calibrated probability that a capacitor belongs to a structure, from the brief's
    caps_p. kae.circuit's p is underconfident: p 0.24 is right 52 % of the time and p 0.96
    91 % (its reliability check over the corpus). A logistic recalibration through those two
    points, logit(q) = 0.67 + 0.515 logit(p), maps 0.24 -> 0.52, 0.5 -> 0.66, 0.96 -> 0.91,
    and keeps the order of the p's (E5: two-point fit)."""
    p = min(max(float(p), 0.01), 0.99)
    z = 0.67 + 0.515 * math.log(p / (1.0 - p))
    return 1.0 / (1.0 + math.exp(-z))


# Below this raw caps_p on a rail shared by >= 3 loads, the brief cannot tell which load a
# capacitor serves (keyboards, LED strings: p ~ 1/loads). The decap term then charges each
# such capacitor its loop to the nearest load power pin on the rail instead of the named one.
OWNERSHIP_NEAREST = 0.35


# ----------------------------------------------------------------------------- (b) decoupling
def ic_current_prior(n_pins):
    """Transient current of an IC (A) from its pin count (E5): small analog/logic 20 mA,
    small MCU 50 mA, MCU 150 mA, large MCU/SoC 300 mA, FPGA/SoC 1 A."""
    if n_pins <= 8:
        return 0.02
    if n_pins <= 32:
        return 0.05
    if n_pins <= 64:
        return 0.15
    if n_pins <= 144:
        return 0.3
    return 1.0


# Decap functions whose capacitor sets a regulator's stability rather than an IC's HF supply
# impedance: a core LDO's VCAP (bypass) and a linear regulator's output capacitor.
STABILITY_FUNCTIONS = ('bypass', 'regulator_output')
# Loop-inductance budget of a regulator-stability capacitor and of the bulk capacitor of a
# module that decouples itself (E5). The regulator needs the capacitor's C and ESR at its
# loop crossover (100 kHz-1 MHz): 10 nH adds 2 pi f L = 63 mOhm at 1 MHz, below the
# 0.1-1 ohm ESR windows LDO and VCAP datasheets give; the load's HF current comes from its
# own decoupling and die capacitance, not through this loop. Human boards: the median such
# loop is 3-4 nH, the 90th percentile 11-19 nH.
L_STABILITY_NH = 10.0


def decap_budget(v_rail=3.3, n_ic_pins=32, n_power_pins=1, ripple=0.05, f_handover_ghz=0.1, i_ic=None,
                 function=None, n_ic_power_pins=None, module=False):
    """Decoupling-loop inductance budget per IC power pin (nH).

    HF decoupling (functions load, entry, converter_*, regulator_input): from a target
    impedance Z_t = ripple V / I_transient of the whole IC (decoupling-pdn.md). The transient
    splits over all the IC's power pins (n, every rail: a 100-pin MCU's VDDA pin carries
    its share, not the whole 300 mA), so each pin's loop may present n Z_t up to the
    frequency where the package and die capacitance take over (f_h, E5 100 MHz: leaded and
    QFN packages' 2-5 nH against 1-10 nF of die capacitance resonate at 30-100 MHz):
        L_pin = n Z_t / (2 pi f_h).
    A 100 nF 0402 (ESL ~0.5 nH) resonates near 16 MHz at 1 nH of loop; above that its
    impedance is 2 pi f (ESL + L_loop), which meets n Z_t to f_h when L_loop <= L_pin - ESL:
    3-8 nH per pin for MCUs, which careful layouts meet. Regulator-stability capacitors
    (STABILITY_FUNCTIONS) and a module's bulk capacitor get L_STABILITY_NH instead."""
    if function in STABILITY_FUNCTIONS:
        return Belief(L_STABILITY_NH, 'nH', f'{function} capacitor: regulator stability (C and ESR at the loop '
                                            f'crossover <= 1 MHz), not an HF target impedance')
    if module:
        return Belief(L_STABILITY_NH, 'nH', 'bulk capacitor of a module that decouples itself')
    i = i_ic or ic_current_prior(n_ic_pins)
    zt = ripple * max(v_rail, 0.5) / i
    n = max(1, n_power_pins, n_ic_power_pins or 0)
    lpin = n * zt / (2.0 * math.pi * f_handover_ghz)
    return Belief(lpin, 'nH', f'target impedance {zt * 1e3:.0f} mOhm ({ripple:.0%} of {v_rail:g} V at {i * 1e3:.0f} mA)'
                              f' x {n} power pins of the IC up to {f_handover_ghz * 1e3:.0f} MHz')


# ----------------------------------------------------------------------------- (c) victims
# class -> (noise budget mV, source impedance ohm)
VICTIM_CLASS = {
    'feedback': (10.0, 2e4),     # 1-2 % of a 0.6-0.8 V reference, divider impedance
    'sense': (1.0, 100.0),       # 1-2 % of a 50-100 mV shunt full scale, RC filter impedance
    'analog': (1.0, 1e3),        # ~2 LSB of a 12-bit, 3.3 V ADC; 1 kOhm source
    'crystal': (10.0, 1e3),      # 1 % of the oscillator swing; |Z| of the load at a few MHz
    'reference': (0.5, 100.0),
    'connector': (1.0, 150.0),   # 1 mV between cable references (LearnEMC)
}


def victim_budget(cls):
    mv, z = VICTIM_CLASS.get(cls, (5.0, 1e3))
    return Belief(mv, 'mV', f'{cls} victim noise budget'), z


# ----------------------------------------------------------------------------- (d) crystals
def crystal_budget(f_hz=None, ppm_layout=5.0):
    """Pulling budget of the layout's stray capacitance on a Pierce oscillator.

    Pulling sensitivity S = C1 / (2 (C0 + C_L)^2) per pF of load change; motional C1 and
    shunt C0 by class: 32.768 kHz tuning fork (C1 3 fF, C0 1.2 pF, C_L 12.5 pF) gives
    ~8 ppm/pF; an AT-cut MHz crystal (C1 7 fF, C0 3 pF, C_L 12 pF) ~16 ppm/pF.
    Budget: 5 ppm of layout-induced shift (a quarter of a +-20 ppm part's tolerance).
    Returns (Belief in ppm, S in ppm/pF)."""
    if f_hz is not None and f_hz < 2e5:
        c1, c0, cl = 3e-3, 1.2, 12.5
    else:
        c1, c0, cl = 7e-3, 3.0, 12.0
    s = c1 / (2.0 * (c0 + cl) ** 2) * 1e6
    return Belief(ppm_layout, 'ppm', f'layout pulling budget; S = C1/(2(C0+C_L)^2) = {s:.1f} ppm/pF'), s


# ----------------------------------------------------------------------------- (e) thermal
THERMAL_VICTIM = {
    'electrolytic': 10.0,   # life halves per +10 K (Arrhenius, thermal-physics.md)
    'crystal_32k': 10.0,    # -0.034 ppm/K^2: ~5 ppm at +12 K from 25 C
    'crystal': 20.0,        # AT-cut: few ppm over tens of K
    'reference': 5.0,       # 10 ppm/K TC: 50 ppm at 5 K
    'sensor': 1.0,          # a temperature sensor reading ambient: 1 K = 1 K error
    'battery': 10.0,
    'precision': 5.0,
}

# Board fin (W/mK, W/m^2K) and budgets (K). Placement cannot change the board's mean rise
# sum P / (h_tot A) (heat balance over its area), only the local excess above it, so the
# thermal budgets apply to that excess: a source's hot spot above the board mean (a design
# rule of thumb: <= 20 K) and a victim's rise from its neighbours (THERMAL_VICTIM).
THERMAL = dict(k_cu=390.0, k_fr4=0.8, h_top=10.0, h_bot=10.0, plane_fill=1.0, signal_fill=0.2,
               source_local_K=20.0)


def converter_loss_split(p_total, v_in=None, v_out=None, i_out=None, boost=False, has_diode=False,
                         external_switches=False):
    """Split a converter's total loss (W) between its parts (E5): a Schottky rectifier
    conducts I_out for the off fraction, P_D = V_F I_out (1 - D) with V_F = 0.5 V and
    D = V_out / V_in (boost: 1 - V_in / V_out; 0.3 when unknown); the inductor (DCR + core)
    takes 15 %; the switches the rest (at least 20 %), split 60/40 high/low when they are
    discrete. Returns {'ic' | 'diode' | 'inductor' | 'high' | 'low': W}."""
    if v_in and v_out and v_in > 0 and v_out > 0:
        d = (1.0 - v_in / v_out) if boost else (v_out / v_in)
        d = min(max(d, 0.05), 0.95)
    else:
        d = 0.3
    out = {}
    p_l = 0.15 * p_total
    p_d = 0.0
    if has_diode and i_out:
        p_d = min(0.5 * i_out * (1.0 - d), 0.6 * p_total)
    p_sw = max(p_total - p_l - p_d, 0.2 * p_total)
    scale = p_total / (p_sw + p_l + p_d)
    if external_switches:
        out['high'] = 0.6 * p_sw * scale
        out['low'] = 0.4 * p_sw * scale
    else:
        out['ic'] = p_sw * scale
    out['inductor'] = p_l * scale
    if p_d > 0:
        out['diode'] = p_d * scale
    return out


def source_power_prior(kind, v_in=None, v_out=None, n_pins=8, pkg=''):
    """Dissipation prior (W) of a heat source (E5)."""
    big = bool(re.search(r'DPAK|TO-?252|TO-?263|D2PAK|SOT-?223|PowerPAK|LFPAK|TO-?220|SO-8|SOIC-8', pkg, re.I))
    if kind == 'ldo':
        i = 0.5 if big else (0.3 if re.search(r'SOT-?89', pkg, re.I) else 0.1)
        dv = (v_in - v_out) if (v_in and v_out and v_in > v_out) else 1.7
        return max(0.01, dv * i), f'LDO: (V_in - V_out) I = {dv:.2g} V x {i:g} A'
    if kind in ('buck', 'boost', 'regulator'):
        vo = v_out or 3.3
        i = 2.0 if big or n_pins > 8 else 1.0
        p = vo * i * (1 / 0.88 - 1)
        return p, f'switching regulator: P_out (1/eta - 1), {vo:g} V x {i:g} A, eta 0.88'
    if kind == 'fet':
        return (1.0 if big else 0.3), 'power FET conduction + switching loss prior'
    if kind == 'inductor':
        return 0.15, 'inductor DCR + core loss prior'
    if kind == 'shunt':
        return 0.25, 'shunt I^2 R prior'
    if kind == 'bridge_driver':
        return 0.8, 'integrated bridge driver prior'
    if kind == 'mcu':
        if n_pins <= 48:
            return 0.05, 'MCU <= 48 pins'
        if n_pins <= 100:
            return 0.2, 'MCU/SoC <= 100 pins'
        if n_pins <= 200:
            return 0.5, 'SoC <= 200 pins'
        return 2.0, 'FPGA/SoC > 200 pins'
    if kind == 'led':
        return 0.05, 'indicator LED'
    return 0.1, 'generic'


# ----------------------------------------------------------------------------- (f) world node
WORLD = dict(f_ref_ghz=0.1,          # 100 MHz: cables of ~1 m radiate efficiently 30-300 MHz
             z_cm=150.0,             # typical common-mode impedance of a cable (fields-emi-budget.md)
             i_cm_budget_uA=5.0,     # Ott: < 5 uA on a >= 1 m cable for CISPR 32 / FCC class B
             period_ns=1000.0,       # 1 MHz switching
             esd_didt=37.5,          # A/ns: IEC 61000-4-2 level 4 contact, 30 A in 0.8 ns
             esd_dv=40.0,            # V a neighbouring (protected) pin's clamp absorbs on top of V_clamp
             esd_k_adj=0.2,          # M/L of an adjacent trace at minimum spacing over a plane (0.1-0.3)
             feed_alpha_db_mm=0.015, # 2.4 GHz FR-4 50-ohm microstrip, conductor + dielectric loss
             feed_budget_db=0.5,
             # cable pickup decays as the cube of distance: beyond 15 mm of gap between the
             # aggressor's and the connector's copper it is < 1e-3 of the 5 uA budget on the
             # corpus; a smooth window to zero at 30 mm keeps the term local (E5)
             cm_r0_mm=15.0,
             cm_r1_mm=30.0)


def esd_budget():
    """Surge-path inductance budget (connector pin -> protector -> its ground via).

    The surge current runs from the connector pin to the protector before it is shunted; a
    trace at minimum spacing alongside that path picks up k L dI/dt (k = M/L ~ 0.2 over a
    plane). Keeping that pickup within the 40 V a protected pin's own clamp absorbs at the
    IEC 61000-4-2 level-4 edge (37.5 A/ns) gives L <= 40 / (0.2 x 37.5) = 5.3 nH, about
    12 mm of 0.25 mm trace plus the via (E5)."""
    lb = WORLD['esd_dv'] / (WORLD['esd_k_adj'] * WORLD['esd_didt'])
    return Belief(lb, 'nH', f'ESD surge path: k L dI/dt <= {WORLD["esd_dv"]:g} V on an adjacent trace, '
                            f'k {WORLD["esd_k_adj"]:g}, {WORLD["esd_didt"]:g} A/ns (IEC 61000-4-2 level 4)')


def cm_budget():
    return Belief(WORLD['i_cm_budget_uA'], 'uA', 'cable common-mode current, Ott class B (>= 1 m cable)')


def feed_budget():
    return Belief(WORLD['feed_budget_db'], 'dB', 'antenna feed loss budget at 2.4 GHz')
