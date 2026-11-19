# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A switching converter's currents from its topology and operating point: the one implementation every
physics and routing site calls (docs/topics/physics/converter-currents.md has the equations and sources).

CCM, steady state, efficiency eta folded into the duty cycle as the TI power-stage notes do:

  buck       D = V_out / V_in                      I_L = I_out          I_in = I_out V_out / (V_in eta)
             commutated (hot-loop) current I_L, input side; dI = (V_in - V_out) D / (L f)        SLVA477
  boost      D = 1 - V_in eta / V_out              I_L = I_out / (1 - D) = I_in = I_out V_out / (V_in eta)
             commutated current I_L, output side; dI = V_in D / (L f)                           SLVA372
  inverting  D = |V_out| / (V_in eta + |V_out|)    I_L = I_out / (1 - D) = I_in + I_out
  buck-boost commutated current I_L, one series loop; dI = V_in D / (L f)                       SLVA721
  4-switch   by region (V_in / V_out against BAND_4SW): buck region, the input leg switches as a buck and the
  buck-boost output leg is static (its high side on); boost region, the reverse; between, both legs
             switch at the inductor current                                                     SLVA535
  SEPIC/Cuk  D = V_out / (V_in eta + V_out)        I_L1 = I_in, I_L2 = I_out, switch I_in + I_out
             (the coupling capacitor carries both inductors' currents into the switch)           SLYT309, SNVA168
  boost LED  a boost at the string's current and voltage                                        SLVA372

The evaluator's corners know a cell's bus and duty, not both rails: there dI = V_sw D (1 - D) / (L f) with V_sw
the switch node's swing (buck V_in, boost V_out, inverting V_in + |V_out|), the same as the notes' forms for a
buck and, for a boost or inverting stage, V_in eta D / (L f): within eta of SLVA372's V_in D / (L f). Peak I_L + dI/2, valley I_L - dI/2; dI is
capped at 2 I_L (the DCM boundary). A buck's D keeps eta = 1: its eta correction is a conduction-loss
refinement of a few percent that moves no current between loops, and its input current is taken from the
power balance instead.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

ETA = (0.8, 0.9, 0.95)        # efficiency (lo, typ, hi) of a converter whose efficiency nobody states
BAND_4SW = 0.1                # a 4-switch buck-boost is in its buck (boost) region when V_in / V_out >= 1.1 (<= 0.9)
D_MIN, D_MAX = 0.02, 0.98
TOPOLOGIES = ("buck", "boost", "inverting_buck_boost", "buck_boost_4switch", "sepic", "cuk", "boost_led")
SOURCES = {
    "buck": "TI SLVA477 (buck power stage)",
    "boost": "TI SLVA372 (boost power stage)",
    "boost_led": "TI SLVA372 (boost power stage) at the LED string's current",
    "inverting_buck_boost": "TI SLVA721 (inverting buck-boost power stage)",
    "buck_boost_4switch": "TI SLVA535 (4-switch buck-boost power stage)",
    "sepic": "TI SLYT309 / SNVA168 (SEPIC)",
    "cuk": "Erickson and Maksimovic, Fundamentals of Power Electronics, ch. 2 (Cuk)",
}


@dataclass
class Operating:
    topology: str
    leg: str | None            # 4-switch: the cell's half-bridge ("buck" input leg, "boost" output leg)
    mode: str                  # buck, boost, buck_boost (4-switch transition), or the topology itself
    D: float                   # the switching leg's duty (a static leg: 0)
    I_in: float                # input current (A, average)
    I_out: float
    I_L: float                 # inductor current (average)
    I_sw: float                # the cell's commutated current: what its hot loop switches (0: a static leg)
    V_bus: float               # the switch node's swing
    loop: str                  # which capacitors close the hot loop: input, output, series, coupling, none
    dI: float | None = None    # inductor ripple, peak to peak (None: L or f_sw unknown)
    I_pk: float | None = None
    I_valley: float | None = None
    basis: list = field(default_factory=list)


def _clip(D):
    return min(max(D, D_MIN), D_MAX)


def topology_of(cls, struct=None, v_out=None):
    """(topology, leg) of a brief commutation cell (class, its structure), or (None, None) when it is no
    DC-DC converter (half bridges, motor and class-D drivers keep their stated or prior current)."""
    st = struct or {}
    top = st.get("topology")
    if top == "buck_boost_4switch":
        return "buck_boost_4switch", cls
    if top in TOPOLOGIES:
        return top, None
    if cls == "buck" and v_out is not None and v_out < 0:
        return "inverting_buck_boost", None
    if cls in ("buck", "boost", "sepic", "cuk", "inverting_buck_boost", "boost_led"):
        return cls, None
    return None, None


def region_4switch(V_in, V_out):
    r = V_in / V_out
    return "buck" if r >= 1 + BAND_4SW else ("boost" if r <= 1 - BAND_4SW else "buck_boost")


def duty(topology, V_in, V_out, eta=ETA[1], leg=None):
    """The switching leg's duty (clipped to [D_MIN, D_MAX]); 0 for a static 4-switch leg."""
    Vo = abs(V_out)
    if topology == "buck":
        return _clip(Vo / V_in)
    if topology in ("boost", "boost_led"):
        return _clip(1 - V_in * eta / Vo)
    if topology == "inverting_buck_boost":
        return _clip(Vo / (V_in * eta + Vo))
    if topology in ("sepic", "cuk"):
        return _clip(Vo / (V_in * eta + Vo))
    if topology == "buck_boost_4switch":
        mode = region_4switch(V_in, Vo)
        if mode == "buck":
            return _clip(Vo / V_in) if leg in (None, "buck") else 0.0
        if mode == "boost":
            return _clip(1 - V_in * eta / Vo) if leg in (None, "boost") else 0.0
        # both legs switch: V_out / V_in = D_1 / (1 - D_2), the boost leg at its minimum share
        return _clip(Vo / (V_in * eta + Vo))
    raise ValueError(f"unknown topology {topology!r}")


def ripple_pp(V_bus, D, L, f_sw):
    """dI = V_sw D (1 - D) / (L f_sw), peak to peak (buck: (V_in - V_out) D / (L f); boost: V_in D / (L f))."""
    if not (L and L > 0 and f_sw and f_sw > 0):
        return None
    D = min(max(D, 1e-3), 1 - 1e-3)
    return V_bus * D * (1 - D) / (L * f_sw)


def input_current(topology, V_in, V_out, I_out, eta=ETA[1]):
    """The converter's average input current from the power balance: I_out |V_out| / (V_in eta)."""
    return I_out * abs(V_out) / (V_in * eta)


def operating(topology, V_in, V_out, I_out, eta=ETA[1], L=None, f_sw=None, leg=None):
    """The converter's currents at one operating point (see the module docstring)."""
    src = SOURCES.get(topology, "")
    Vo = abs(V_out)
    I_in = input_current(topology, V_in, V_out, I_out, eta)
    D = duty(topology, V_in, V_out, eta, leg)
    basis = [src]
    mode = topology
    if topology == "buck":
        IL, Isw, Vb, loop = I_out, I_out, V_in, "input"
    elif topology in ("boost", "boost_led"):
        IL, Isw, Vb, loop = I_in, I_in, Vo, "output"
    elif topology == "inverting_buck_boost":
        IL = I_out / (1 - D)
        Isw, Vb, loop = IL, V_in + Vo, "series"
    elif topology in ("sepic", "cuk"):
        IL = I_in                                # L1; L2 carries I_out
        Isw, Vb, loop = I_in + I_out, V_in + Vo, "coupling"
    elif topology == "buck_boost_4switch":
        mode = region_4switch(V_in, Vo)
        basis.append(f"region {mode} (V_in/V_out {V_in / Vo:.3g}, band +/-{BAND_4SW:g})")
        if mode == "buck":
            IL = I_out
        elif mode == "boost":
            IL = I_in
        else:
            IL = max(I_out, I_in)
        switching = mode == "buck_boost" or leg in (None, mode)
        Isw = IL if switching else 0.0
        Vb = V_in if leg == "buck" else Vo if leg == "boost" else max(V_in, Vo)
        loop = ("input" if leg == "buck" else "output") if switching else "none"
        if not switching:
            basis.append(f"the {leg} leg is static in the {mode} region: no commutation")
    else:
        raise ValueError(f"unknown topology {topology!r}")
    op = Operating(topology, leg, mode, D, I_in, I_out, IL, Isw, Vb, loop, basis=basis)
    if Isw > 0 and L and L > 0 and f_sw and f_sw > 0:
        # the inductor's volt-seconds during the on time, as each note writes them
        v_on = (V_in - Vo) if (topology == "buck" or (topology == "buck_boost_4switch" and mode == "buck")) else V_in
        dI = max(v_on, 0.0) * D / (L * f_sw)
        if dI is not None:
            dI = min(dI, 2 * IL)
            op.dI, op.I_pk, op.I_valley = dI, IL + dI / 2, IL - dI / 2
    return op


def turnoff_current(I_L, dI):
    """The current the switch turns off: the inductor's peak I_L + dI/2 (dI capped at 2 I_L, the DCM boundary,
    where the peak is 2 I_L and the switch turns on at zero). The hard commutation is the turn-off: the loop's
    inductance then holds 1/2 L I_pk^2, which rings out across the switch (overshoot L dI/dt at I_pk). At turn-on
    the same inductance limits the current's rise and lowers the switch's overlap loss (a turn-on snubber), so
    switching loss is insensitive to it there (Bai 2003, sec. 3.6, 4.4.3): no second 1/2 L I_valley^2 is charged."""
    if dI is None or dI <= 0:
        return I_L
    return I_L + min(dI, 2 * I_L) / 2


def output_from_inductor(topology, I_L, D):
    """I_out a cell delivers at inductor current I_L and duty D (the inverse of operating's I_L)."""
    if topology in ("boost", "boost_led", "inverting_buck_boost"):
        return I_L * (1 - D)
    return I_L


def inductor_from_output(topology, I_out, D):
    """The inductor current that delivers I_out at duty D."""
    if topology in ("boost", "boost_led", "inverting_buck_boost"):
        return I_out / (1 - _clip(D))
    return I_out


def input_from_inductor(topology, I_L, D):
    """The average input current at inductor current I_L and duty D (the input switch conducts I_L for D)."""
    if topology in ("boost", "boost_led"):
        return I_L
    return I_L * D


def rectifier_current(topology, I_L, D):
    """The rectifier's average current: I_L (1 - D) (a boost's is its output current)."""
    return I_L * (1 - D)


def _iv(v):
    """(typ, lo, hi) of an intent value: a point or [lo, hi] (typ the geometric mean, as kae.excite.beliefs)."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        if not v:
            return None
        lo, hi = float(v[0]), float(v[-1])
        lo, hi = min(lo, hi), max(lo, hi)
        return (math.sqrt(lo * hi) if lo > 0 else (lo + hi) / 2, lo, hi)
    return (float(v), float(v), float(v))


@dataclass
class CellCurrent:
    I: tuple                   # (typ, lo, hi) A, the commutated current
    source: str                # intent | physics
    basis: str
    D: tuple | None = None     # (typ, lo, hi) when the operating point fixes it
    eta: tuple | None = None
    op: Operating | None = None
    I_L: tuple | None = None   # (typ, lo, hi) the inductor's current: what a static leg's closed switch carries


def from_intent(cell, topology, leg=None, V_in=None, V_out=None, eta=None):
    """The commutated current of a cell from its operating facts `cell` (an intent's cells.<id>): I_switch_A,
    stated, overrides; else a stated I_A (the commutated current, as intents before I_out_A gave it); else
    I_out_A through the topology at V_in_V / V_out_V (or V_in / V_out, the board's rails) and eta (cell eta,
    else `eta`, else ETA). None when the facts give no current, or give I_out_A without the voltages or
    topology to convert it (the caller then keeps I_out_A as the current and says so)."""
    cell = cell or {}
    v = _iv(cell.get("I_switch_A"))
    if v:
        return CellCurrent(v, "intent", "I_switch_A stated in the intent (override)")
    v = _iv(cell.get("I_A"))
    if v:
        return CellCurrent(v, "intent", "the intent file")
    Io = _iv(cell.get("I_out_A"))
    if not Io:
        return None
    vi = _iv(cell.get("V_in_V")) or ((V_in,) * 3 if V_in else None)
    vo = _iv(cell.get("V_out_V")) or ((V_out,) * 3 if V_out else None)
    if topology is None or not vi or not vo or not vi[0] or not vo[0]:
        why = "topology unknown" if topology is None else "V_in or V_out unknown"
        return CellCurrent(Io, "intent", f"I_out_A as the commutated current ({why}: not converted)")
    e = _iv(cell.get("eta")) or (tuple(eta) if eta else None)
    ebasis = "intent eta" if cell.get("eta") is not None else ("rail eta" if eta else f"eta {ETA[0]:g}-{ETA[2]:g} typical")
    e = e or (ETA[1], ETA[0], ETA[2])
    Vi, Vo = vi[0], vo[0]
    typ = operating(topology, Vi, Vo, Io[0], e[0], leg=leg)
    lo = operating(topology, Vi, Vo, Io[1], e[2], leg=leg)       # low current at high efficiency
    hi = operating(topology, Vi, Vo, Io[2], e[1], leg=leg)
    Dv = (typ.D, min(lo.D, hi.D), max(lo.D, hi.D))
    basis = (f"{(leg + ' leg, ' + typ.mode + ' region') if leg else typ.mode}, from I_out {Io[1]:.3g}-{Io[2]:.3g} A at "
             f"V_in {Vi:g} V, V_out {Vo:g} V, {ebasis}: I_sw {typ.I_sw:.3g} A, D {typ.D:.3g}, {typ.loop} loop "
             f"({'; '.join(typ.basis)})")
    return CellCurrent((typ.I_sw, lo.I_sw, hi.I_sw), "physics", basis, D=Dv, eta=e, op=typ,
                       I_L=(typ.I_L, lo.I_L, hi.I_L))
