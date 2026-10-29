# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Each aggressor's parameters as sourced intervals (kae.excite.beliefs), and the laws that derive
some from others.

Commutation cell (switch current I, bus voltage V, input voltage Vin, frequency f_sw):
- I: the intent file (a load, or the cell's current), else the rated current of the inductor or the
  controller over [0.15, 1.0] of it (a prior: the board does not say what it drives).
- f_sw: intent, part table, the comprehension's switcher table, else a prior [0.3, 3] MHz.
- t_i, the current commutation (switch to rectifier): intent or part table, else a prior by class
  (integrated converter <= 24 V: 1-10 ns; discrete Si: 5-30 ns; GaN: 0.5-3 ns).
- C_sw, the switch node's capacitance: the switch's C_oss from its on-resistance by a figure of merit
  R_on C_oss in [4, 15] ohm pF (low-voltage silicon), plus the rectifier's junction capacitance
  (part table, else [30, 300] pF for a small Schottky).
- t_v = C_sw V / I, the voltage edge once the current has commutated (physics): the switch node can
  move no faster than the current charging its capacitance.
- D: boost 1 - Vin/V, buck Vout/Vin (physics).
Cores and clocks keep class priors, as intervals.
"""
from __future__ import annotations

import math

from .beliefs import Param, intent_value, lookup

FOM_RC = (4.0, 15.0)          # ohm pF: R_on x C_oss of low-voltage silicon power switches (class range)
C_RECT = (30e-12, 300e-12)    # F: junction capacitance of a small Schottky rectifier at a few volts
T_I = {"integrated": (1e-9, 10e-9), "discrete": (5e-9, 30e-9), "gan": (0.5e-9, 3e-9)}
I_FRAC = (0.15, 1.0)          # operating current as a fraction of the rating, when nobody states it


def _p(L, subject, name, typ, lo, hi, unit, source, basis):
    return L.add(Param(subject, name, typ, lo, hi, unit, source, basis))


def cell(L, s, brief, bd, intent, text, rect_text="", vin_net=None):
    """Add the parameters of commutation-cell source s to ledger L; returns {name: Param}."""
    sid = s.meta["cell"]
    st = next((x for x in brief.get("structures") or [] if x.get("id") == sid), {})
    ex = st.get("excite") or {}
    tab = lookup(text)
    out = {}
    cls = s.meta.get("cls") or ""
    # bus and input voltages: the rails' own beliefs (net names, regulators, dividers)
    nets = brief.get("nets") or {}

    def volts(net):
        d = nets.get(net) or {}
        vb = d.get("volts_belief") or {}
        iv = vb.get("interval")
        if d.get("volts") is None:
            return None
        lo, hi = (iv or [d["volts"], d["volts"]])
        return float(d["volts"]), float(lo), float(hi)
    vb = volts(s.meta.get("bus"))
    iv = intent_value(intent, "cells", sid, "V_V")
    if iv:
        out["V"] = _p(L, sid, "V_V", *iv, "V", "intent", "the intent file")
    elif vb:
        out["V"] = _p(L, sid, "V_V", *vb, "V", "board", f"rail {s.meta.get('bus')}: its name, regulator or divider")
    else:
        out["V"] = _p(L, sid, "V_V", 12.0, 3.3, 48.0, "V", "prior", "bus voltage unknown")
    vin_net = st.get("vin") if cls == "boost" and st.get("vin") else vin_net
    vi = volts(vin_net) if vin_net else None
    # f_sw
    iv = intent_value(intent, "cells", sid, "f_sw_Hz")
    if iv:
        out["f_sw"] = _p(L, sid, "f_sw_Hz", *iv, "Hz", "intent", "the intent file")
    elif "f_sw_Hz" in tab:
        t, lo, hi, src = tab["f_sw_Hz"]
        out["f_sw"] = _p(L, sid, "f_sw_Hz", t, lo, hi, "Hz", "part_table", src)
    elif ex.get("f_sw_Hz"):
        f = float(ex["f_sw_Hz"])
        out["f_sw"] = _p(L, sid, "f_sw_Hz", f, f, f, "Hz", "part_table", "kae.circuit switcher table")
    else:
        out["f_sw"] = _p(L, sid, "f_sw_Hz", 1e6, 0.3e6, 3e6, "Hz", "prior", "switching frequency unknown")
    # operating current
    iv = intent_value(intent, "cells", sid, "I_A")
    if iv:
        out["I"] = _p(L, sid, "I_A", *iv, "A", "intent", "the intent file")
    else:
        rated = float(ex.get("I") or 1.0) / 0.6
        basis = "; ".join(b for b in ex.get("basis") or [] if b.startswith("I ="))
        out["I"] = _p(L, sid, "I_A", 0.6 * rated, I_FRAC[0] * rated, I_FRAC[1] * rated, "A", "prior",
                      f"operating current unknown: {I_FRAC[0]:g}-{I_FRAC[1]:g} x the {rated:.3g} A rating ({basis})")
    # current commutation time
    iv = intent_value(intent, "cells", sid, "t_i_s")
    gan = "GaN" in text or "EPC" in text
    klass = "gan" if gan else ("discrete" if cls in ("half_bridge", "motor_driver") and "integrated" not in text else "integrated")
    if iv:
        out["t_i"] = _p(L, sid, "t_i_s", *iv, "s", "intent", "the intent file")
    elif "t_i_s" in tab:
        t, lo, hi, src = tab["t_i_s"]
        out["t_i"] = _p(L, sid, "t_i_s", t, lo, hi, "s", "part_table", src)
    else:
        lo, hi = T_I[klass]
        out["t_i"] = _p(L, sid, "t_i_s", math.sqrt(lo * hi), lo, hi, "s", "prior",
                        f"current commutation time of a {klass} switch (class range); no datasheet value")
    # switch-node capacitance: C_oss from R_on by figure of merit, plus the rectifier's junction
    if "c_sw_F" in tab:
        t, lo, hi, src = tab["c_sw_F"]
        out["C_sw"] = _p(L, sid, "C_sw_F", t, lo, hi, "F", "part_table", src)
    else:
        rt = lookup(rect_text)
        if "r_on_ohm" in tab:
            r = tab["r_on_ohm"][0]
            co = (FOM_RC[0] / r * 1e-12, FOM_RC[1] / r * 1e-12)
            cbasis = f"C_oss {co[0]*1e12:.0f}-{co[1]*1e12:.0f} pF from R_on {r*1e3:g} mOhm ({tab['r_on_ohm'][3]}) by R_on C_oss in {FOM_RC[0]:g}-{FOM_RC[1]:g} ohm pF"
        else:
            co = (30e-12, 1000e-12)
            cbasis = "C_oss 30-1000 pF (no on-resistance known)"
        cd = (rt["cj_F"][1], rt["cj_F"][2]) if "cj_F" in rt else C_RECT
        dbasis = (f"rectifier C_j {cd[0]*1e12:.0f}-{cd[1]*1e12:.0f} pF" +
                  (f" ({rt['cj_F'][3]})" if "cj_F" in rt else " (small Schottky class range)"))
        lo, hi = co[0] + cd[0], co[1] + cd[1]
        out["C_sw"] = _p(L, sid, "C_sw_F", math.sqrt(lo * hi), lo, hi, "F", "physics", f"{cbasis}; {dbasis}")
    if "r_on_ohm" in tab:
        t, lo, hi, src = tab["r_on_ohm"]
        out["R_on"] = _p(L, sid, "R_on_ohm", t, lo, hi, "ohm", "part_table", src)
    # voltage edge: the switch node cannot move faster than I charges C_sw
    V, I, C = out["V"], out["I"], out["C_sw"]
    tv = (C.lo * V.lo / I.hi, C.typ * V.typ / I.typ, C.hi * V.hi / I.lo)
    out["t_v"] = _p(L, sid, "t_v_s", tv[1], tv[0], tv[2], "s", "physics",
                    "t_v = C_sw V / I: the switch node charged by the commutated current")
    # duty
    if vi and cls == "boost":
        D = (max(0.05, 1 - vi[2] / V.lo), 1 - vi[0] / V.typ, min(0.95, 1 - vi[1] / V.hi))
        clip = " (clipped: Vin >= Vout as the rails read, their voltages are suspect)" if vi[0] >= V.typ else ""
        out["D"] = _p(L, sid, "D", D[1], min(D), max(D), "", "physics", f"boost D = 1 - Vin/V with Vin from {vin_net}{clip}")
    elif cls == "buck" and volts(st.get("vout")):
        # a buck's bus (V) is its input; its output is the structure's vout
        vo = volts(st.get("vout"))
        D = (max(0.02, vo[1] / V.hi), vo[0] / V.typ, min(0.98, vo[2] / V.lo))
        clip = " (clipped: Vout >= Vin as the rails read, their voltages are suspect)" if vo[0] >= V.typ else ""
        out["D"] = _p(L, sid, "D", D[1], min(D), max(D), "", "physics",
                      f"buck D = Vout/Vin with Vout from {st.get('vout')}{clip}")
    else:
        why = f"input rail {vin_net} has no voltage" if vin_net else "input rail not identified"
        out["D"] = _p(L, sid, "D", 0.5, 0.1, 0.9, "", "prior", f"duty unknown ({why})")
    # the switch's voltage rating, for the overshoot requirement
    if "v_sw_max_V" in tab:
        t, lo, hi, src = tab["v_sw_max_V"]
        out["V_max"] = _p(L, sid, "V_max_V", t, lo, hi, "V", "part_table", src)
    return out


def generic(L, s, kind):
    """Cores and clocks: class priors as intervals around their meta values."""
    sid = s.name
    I0 = float(s.meta.get("I") or 0.01)
    t0 = 1.0 / (math.pi * float(s.meta.get("f_e") or 1e8))
    f0 = float(s.meta.get("f_rep") or 25e6)
    return {"I": L.add(Param(sid, "I_A", I0, I0 / 3, I0 * 3, "A", "prior", f"{kind} current, class value x/3")),
            "t_i": L.add(Param(sid, "t_i_s", t0, t0 / 2, t0 * 3, "s", "prior", f"{kind} edge, class value /2 .. x3")),
            "f_sw": L.add(Param(sid, "f_sw_Hz", f0, f0 / 2, f0 * 2, "Hz", "prior", f"{kind} repetition, class value"))}
