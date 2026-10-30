# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The board's aggressors as unit sources in its circuit, each with its physical scale.

- Commutation cells: the active switch is a current source (the commutated current I steps in
  t_sw); the rectifier conducts and the inductor is open at the edge, so the circuit solve itself
  finds the hot loop (switch, rectifier, the capacitors that close it) and how the capacitors
  share it, whatever the topology.
- ICs: the dynamic supply current of the core, drawn from the internal supply node to ground.
- Clock drivers: the output pin charges the net's load, returning through the driver's ground.

Each source carries di/dt (A/s) and the edge frequency f_e = 1/(pi t_r) at which its injection
vector is solved; requirements scale the unit solution by these.
"""
from __future__ import annotations

import math

from .models import PKG_L, SW_FN, _rl

# dynamic core current and edge of IC classes (stand-ins; an IC's datasheet replaces them)
DYNAMIC = {"mcu": (0.05, 1e-9), "fpga": (0.5, 0.5e-9), "memory": (0.1, 1e-9), "logic": (0.02, 1e-9),
           "adc_dac": (0.01, 2e-9), "": (0.01, 2e-9)}
DIGITAL = ("mcu", "fpga", "memory", "logic", "adc_dac", "interface", "phy", "module", "processor", "soc")
CLOCK_TR = 1e-9
CLOCK_F = 25e6                   # a clock whose frequency the board does not state
CORE_F = 50e6                    # core clock of an IC whose clock is not known
CLOCK_C = 10e-12                 # load of a short clock net (receiver plus trace)
HIGH_SIDE = ("buck", "half_bridge", "motor_driver", "sepic", "flyback", "forward")


def add_all(bd, brief, nl=None):
    """Add every source to bd.circuit; returns the list of Source objects."""
    out = []
    uuid = {u: p["ref"] for u, p in brief["parts"].items()}
    for s in brief.get("structures") or []:
        if s.get("kind") == "commutation_cell":
            src = _cell(bd, s, uuid)
            if src is not None:
                out.append(src)
    for ref, nodes in bd.ic_nodes.items():
        kind, sub, role = bd.part_kind.get(ref, ("ic", None, ""))
        if sub not in DIGITAL:
            continue                 # only clocked logic draws a core current at its clock; a charger, a
            #                          regulator or an analog part does not
        I, tr = DYNAMIC.get(sub or "", DYNAMIC[""])
        for rail, v in nodes.items():
            if rail == "g":
                continue
            src = bd.circuit.src(f"core:{ref}:{rail}", v, nodes["g"], kind="core", ref=ref, rail=rail,
                                 I=I, didt=I / tr, f_e=1 / (math.pi * tr), V=bd.rails.get(rail) or 3.3, f_rep=CORE_F)
            out.append(src)
    for net, d in brief["nets"].items():
        if d.get("role") != "clock":
            continue
        drv = None
        for tok in bd.pads_of.get(net, []):
            ref = tok.rsplit(".", 1)[0]
            if ref in bd.ic_nodes:
                drv = drv or tok
        if drv:
            ref = drv.rsplit(".", 1)[0]
            V = 3.3
            I = CLOCK_C * V / CLOCK_TR
            src = bd.circuit.src(f"clk:{net}", bd.ic_nodes[ref]["g"], net, pb=drv, kind="clock", net=net,
                                 I=I, didt=I / CLOCK_TR, f_e=1 / (math.pi * CLOCK_TR), V=V,
                                 f_rep=(d.get("f_Hz") or CLOCK_F))
            out.append(src)
    return out


def _cell(bd, s, uuid):
    c = bd.circuit
    sw, gnd, bus = s.get("sw"), s.get("gnd") or bd.ground, s.get("rail")
    ex = s.get("excite") or {}
    I, V = ex.get("I") or 1.0, ex.get("V") or bd.rails.get(bus) or 12.0
    t_sw = (ex.get("t_sw_ns") or 10.0) * 1e-9
    high = (s.get("class") or "") in HIGH_SIDE
    meta = dict(kind="cell", cell=s["id"], I=I, V=V, t_sw=t_sw, didt=I / t_sw, f_e=1 / (math.pi * t_sw),
                f_sw=ex.get("f_sw_Hz"), cls=s.get("class"), sw=sw, bus=bus, gnd=gnd)
    ctrl = uuid.get(s.get("controller"))
    # an integrated switch: the controller's SW pin(s) on the switch node
    if ctrl and ctrl in bd.ic_nodes:
        swp = [t for t in bd.pads_of.get(sw, []) if t.startswith(ctrl + ".")]
        if swp:
            nodes = bd.ic_nodes[ctrl]
            if high:
                a = nodes.get(bus) or bus
                src = c.src(f"cell:{s['id']}", a, sw, pb=swp[0], **meta)
            else:
                src = c.src(f"cell:{s['id']}", sw, nodes["g"], pa=swp[0], **meta)
            loop_refs = {uuid.get(u) for u, _ in s.get("loop") or []}
            rect = [r for r in loop_refs if r and r != ctrl and bd.part_kind.get(r, ("",))[0] in ("diode", "transistor")]
            if not rect:
                # synchronous: the other switch is inside the controller and conducts
                other = nodes["g"] if high else (nodes.get(bus) or bus)
                # the rectifier's far end: an internal node, or the bus net itself at the controller's own pin on
                # it (a net end without a pad would carry the cell's current into the net from nowhere)
                op_ = next((t for t in bd.pads_of.get(bus, []) if t.rsplit(".", 1)[0] == ctrl), None) \
                    if other == bus else None
                c.z(f"{ctrl}:sync", sw if high else other, other if high else sw, _rl(0.05, PKG_L),
                    swp[0] if high else op_, op_ if high else swp[0], "sync_on")
                bd.assumptions.append(f"{s['id']}: no rectifier part in the loop; a synchronous switch inside {ctrl} conducts")
            return src
    # a discrete switch: the transistor in the loop between the switch node and the far net
    far = bus if high else gnd
    for u, _ in s.get("loop") or []:
        ref = uuid.get(u)
        if ref and bd.part_kind.get(ref, ("",))[0] == "transistor":
            pa = next((t for t in bd.pads_of.get(sw, []) if t.startswith(ref + ".")), None)
            pb = next((t for t in bd.pads_of.get(far, []) if t.startswith(ref + ".")), None)
            if pa and pb:
                a, b = (far, sw) if high else (sw, far)
                return c.src(f"cell:{s['id']}", a, b, pa=pb if high else pa, pb=pa if high else pb, **meta)
    bd.assumptions.append(f"{s['id']}: switch not found; cell not excited")
    return None
