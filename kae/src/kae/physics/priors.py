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
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Belief:
    value: float
    unit: str
    basis: str
    cls: str = 'E5'

    def to_json(self):
        return {'value': round(self.value, 6), 'unit': self.unit, 'basis': self.basis, 'class': self.cls}


# ----------------------------------------------------------------------------- knobs
@dataclass
class Knobs:
    """The few explicit knobs of the objective (everything else is a budget)."""
    barrier: float = 4.0          # phi(u) = u + barrier * max(0, u - 1)^2
    use_confidence: bool = True   # weight each structure by the brief's confidence
    hop_detour: float = 1.0       # expected route length / octilinear pad distance (E5, measured on human boards)
    pair_cos_min: float = 0.3     # loop pairs with |cos| below this are dropped in the fast path


def phi(u, barrier=4.0):
    """One currency: utilisation u = spend / allocation, priced linearly below budget and
    with a quadratic barrier above it."""
    return u + barrier * (u - 1.0) ** 2 if u > 1.0 else u


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


def hot_loop_excite(cell_class='buck', v_in=12.0, i_out=None, t_sw_ns=None):
    """(dI/dt A/ns, dV/dt V/ns, I A, V V, t_sw ns) of a commutation cell (E5 class priors)."""
    c0, t0, i0, _, _ = CELL_CLASS.get(cell_class, CELL_CLASS['unknown'])
    t = t_sw_ns or t0
    i = i_out or i0
    return dict(didt=i / t, dvdt=v_in / t, I=i, V=v_in, t_sw=t)


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


def decap_budget(v_rail=3.3, n_ic_pins=32, n_power_pins=1, ripple=0.05, f_handover_ghz=0.1, i_ic=None):
    """Decoupling-loop inductance budget per IC power pin from a target impedance.

    Z_t = ripple V / I_transient for the whole IC (decoupling-pdn.md); with the transient
    shared by its n power pins, each pin's loop may present n Z_t up to the frequency
    where the package and die capacitance take over (f_h, E5 100 MHz):
        L_pin = n Z_t / (2 pi f_h)."""
    i = i_ic or ic_current_prior(n_ic_pins)
    zt = ripple * max(v_rail, 0.5) / i
    lpin = max(1, n_power_pins) * zt / (2.0 * math.pi * f_handover_ghz)
    return Belief(lpin, 'nH', f'target impedance {zt * 1e3:.0f} mOhm ({ripple:.0%} of {v_rail:g} V at {i * 1e3:.0f} mA)'
                              f' x {max(1, n_power_pins)} power pins up to {f_handover_ghz * 1e3:.0f} MHz')


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

THERMAL = dict(k_cu=390.0, k_fr4=0.8, h_top=10.0, h_bot=10.0, plane_fill=1.0, signal_fill=0.2,
               source_rise_K=40.0)


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
             esd_dv=40.0,            # V the protected pin's internal clamp absorbs on top of V_clamp
             feed_alpha_db_mm=0.015, # 2.4 GHz FR-4 50-ohm microstrip, conductor + dielectric loss
             feed_budget_db=0.5)


def esd_budget():
    lb = WORLD['esd_dv'] / WORLD['esd_didt']
    return Belief(lb, 'nH', f'ESD: {WORLD["esd_dv"]:g} V of L di/dt at {WORLD["esd_didt"]:g} A/ns (IEC 61000-4-2 level 4)')


def cm_budget():
    return Belief(WORLD['i_cm_budget_uA'], 'uA', 'cable common-mode current, Ott class B (>= 1 m cable)')


def feed_budget():
    return Belief(WORLD['feed_budget_db'], 'dB', 'antenna feed loss budget at 2.4 GHz')
