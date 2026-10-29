# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the layout can harm, as observers, and the bilinear form that prices every harm.

The copper's parasitic voltage at each pad, v = Z_cu J_s, enters the circuit in series with the
part at that pad. By reciprocity, the change of an observed quantity y_k (a voltage across a
switch, between an IC's supply and ground, at a victim input, between two connectors' grounds)
is J_k^T v, where J_k is the pad-current pattern of a unit current driven at the observation
port: one adjoint solve per observer (Director and Rohrer 1969). So every requirement is

    r_{k,s} = J_k^T Z_cu J_s        (V per A of aggressor s, at the edge band)

and the copper enters only through Z_cu: one field solve per aggressor serves every observer.
A cell's own overshoot is the case k = s. Time-domain size: the inductive part times the
aggressor's di/dt, L_ks * di/dt with L_ks = Im(r)/w.

Bounds are stated with their source class: datasheet and standard values where the board names
them, otherwise documented priors (flagged `prior`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# priors for what each observer tolerates from the copper (V, peak), used when nothing better is known
TOL = {
    "supply_digital": (0.05, "5% of the rail: half a CMOS noise margin (JESD8 V_IL/V_IH 30/70%)"),
    "supply_analog": (0.01, "1% of the rail: analog supply rejection budget"),
    "feedback": (0.01, "1% of the reference: the regulator's output accuracy class"),
    "analog": (1e-3, "1 mV at an analog input"),
    "adc_input": (1e-3, "1 mV at an ADC input"),
    "reference": (1e-3, "1 mV on a reference"),
    "sense": (1e-3, "1 mV on a sense line"),
    "reset": (0.3, "30% of the rail at a reset input (CMOS V_IL)"),
    "crystal": (0.01, "10 mV at an oscillator pin"),
    "cm": (None, "CISPR 32 class B (30 dBuV/m at 10 m, 30-230 MHz) radiated by 1 m of cable, E = 1.26e-6 f l I / r "
                 "(Ott, EMC Engineering, eq. 12-7), cable common-mode impedance 150 ohm: V_lim(f) = 3.8e4 / f V "
                 "per harmonic"),
    "overshoot": (0.2, "20% of the bus as copper ring (no switch rating known)"),
}


@dataclass
class Observer:
    name: str
    kind: str
    a: str              # observation port: unit current from a to b
    b: str
    pa: str | None = None
    pb: str | None = None
    bound: float = 0.0  # V peak
    basis: str = ""
    src_class: str = "prior"
    meta: dict = field(default_factory=dict)


def observers(bd, brief, sources):
    out = []
    for s in sources:
        m = s.meta
        if s.kind == "cell":
            frac, why = TOL["overshoot"]
            out.append(Observer(f"overshoot:{m['cell']}", "overshoot", s.a, s.b, s.pa, s.pb, frac * m["V"],
                                f"{why}; V = {m['V']:g} V", "prior", dict(source=s.name)))
    for ref, nodes in bd.ic_nodes.items():
        kind, sub, role = bd.part_kind.get(ref, ("ic", None, ""))
        for rail, v in nodes.items():
            if rail == "g":
                continue
            analog = sub in ("opamp", "adc_dac", "reference")
            frac, why = TOL["supply_analog" if analog else "supply_digital"]
            V = bd.rails.get(rail) or 3.3
            out.append(Observer(f"supply:{ref}:{rail}", "supply", v, nodes["g"], bound=frac * V,
                                basis=f"{why}; {rail} = {V:g} V", meta=dict(ref=ref, rail=rail)))
    for st in brief.get("structures") or []:
        if st.get("kind") != "victim":
            continue
        cls = st.get("class") or "analog"
        nets = st.get("nets") or ([st["net"]] if st.get("net") else [])
        for net in nets:
            for tok in bd.pads_of.get(net, []):
                ref = tok.rsplit(".", 1)[0]
                if ref in bd.ic_nodes:          # the receiving pin
                    frac, why = TOL.get(cls, TOL["analog"])
                    vref = (st.get("divider") or {}).get("vref_V") or 1.0
                    bound = frac * vref if cls == "feedback" else frac * (3.3 if cls == "reset" else 1.0)
                    out.append(Observer(f"victim:{cls}:{tok}", "victim", bd.ic_nodes[ref]["g"], net, None, tok,
                                        bound, why, "prior", dict(net=net, cls=cls)))
    conn_gnd = {}
    for net in bd.grounds:
        for tok in bd.pads_of.get(net, []):
            ref = tok.rsplit(".", 1)[0]
            if bd.part_kind.get(ref, ("",))[0] == "connector":
                conn_gnd.setdefault(ref, tok)
    refs = sorted(conn_gnd)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            _, why = TOL["cm"]
            out.append(Observer(f"cm:{refs[i]}-{refs[j]}", "cm", "", "", conn_gnd[refs[i]], conn_gnd[refs[j]], 0.0, why,
                                "standard", dict(pads=(conn_gnd[refs[i]], conn_gnd[refs[j]]))))
    return out


def pattern(bd, obs, f):
    """J_k: pad currents of a unit current driven at the observer's port (adjoint solve); a direct pad
    pair (cm) is its own pattern."""
    if obs.kind == "cm":
        a, b = obs.meta["pads"]
        return {a: 1.0, b: -1.0}
    c = bd.circuit
    s = c.src(f"adj:{obs.name}", obs.a, obs.b, obs.pa, obs.pb, kind="adjoint")
    c.sources.remove(s)
    return c.solve(f, [s])[s.name]["J"]


F_PATTERN = 10e6


def gentle_f(src, f_cap=F_PATTERN):
    """The frequency at which an aggressor's current pattern is taken: its edge band, capped at 10 MHz.
    Above the capacitors' self-resonance (1-5 MHz for microfarads) they share current by their
    package inductance, as at the edge; well below the loop's parasitic resonance (C_oss or the
    switch node with nanohenries: 50-300 MHz) the pattern carries no resonant gain. First-order
    pricing holds only below that resonance (the gentleness criterion); the ring is a sign-off
    question (`gain` reports it)."""
    return min(src.meta.get("f_e") or 1e8, f_cap)


CM_V_LIM_HZ = 3.8e4        # V_lim(f) = CM_V_LIM_HZ / f, see TOL["cm"]
F_CM = (30e6, 230e6)


def size(o, s, L):
    """(observed size in V, bound in V) of an observer o for aggressor s at copper inductance L (H).
    Peak quantities: L di/dt. Emissions (cm): per harmonic, against the CISPR limit at the worst
    frequency of the band. A trapezoid of amplitude I, repetition f_rep and edge t_r has harmonic
    currents I f_rep / (pi f) up to f_r = 1 / (pi t_r), falling as 1/f^2 beyond, so
    w L I_h = 2 L I f_rep is flat to f_r and the ratio to the 1/f limit peaks at min(f_r, 230 MHz)."""
    m = s.meta
    if o.kind != "cm":
        return abs(L) * m.get("didt", 0.0), o.bound
    I = m.get("I", 0.0)
    f_rep = m.get("f_sw") or m.get("f_rep") or 1e6
    f_r = m.get("f_e") or 1e8
    f = min(max(f_r, F_CM[0]), F_CM[1])
    v = 2 * abs(L) * I * f_rep * (1.0 if f <= f_r else (f_r / f) ** 1)
    return v, CM_V_LIM_HZ / f


def bilinear(Ja, v):
    """J_a^T v over the pads both know (v from a copper solve of the aggressor)."""
    return sum(Ja[p] * v[p] for p in Ja if p in v)


@dataclass
class Harm:
    observer: str
    source: str
    L_nH: float          # Im(J_k^T Z J_s) / w
    volts: float         # L * di/dt
    bound: float
    u: float             # volts / bound
    basis: str


def harms(bd, srcs, obs, copper, f_of=gentle_f, min_u=1e-3):
    """[Harm] for every (observer, aggressor) pair: copper(J, f) -> {pad: V} is the field solve."""
    out = []
    pats = {}
    for s in srcs:
        f = f_of(s)
        w = 2 * math.pi * f
        Js = bd.circuit.solve(f, [s])[s.name]["J"]
        v = copper(Js, f)
        for o in obs:
            key = (o.name, f)
            if key not in pats:
                pats[key] = pattern(bd, o, f)
            r = bilinear(pats[key], v)
            L = r.imag / w
            volts = abs(L) * s.meta.get("didt", 0.0)
            u = volts / o.bound if o.bound else float("inf")
            if o.kind == "overshoot" and o.meta.get("source") != s.name:
                continue
            if u >= min_u:
                out.append(Harm(o.name, s.name, L * 1e9, volts, o.bound, u, o.basis))
    return sorted(out, key=lambda h: -h.u)
