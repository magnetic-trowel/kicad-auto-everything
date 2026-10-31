# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small-signal models of a board's parts, built from comprehension (kae.circuit brief + netlist).

Each part becomes impedances between its pads (or to its internal nodes). Values are the part's
own (C, R, L from its value field) plus parasitics by package; where a part's data is unknown the
model is a class stand-in, recorded in `Board.assumptions`. The stand-ins set how the circuit's
high-frequency current divides between parts; they never decide geometry rankings (an error in
them scales a structure's price, see docs/topics/architecture/physics-driven-design.md §3).

Integrated circuits: every ground pin reaches one internal ground node, every supply pin of one
rail an internal supply node, each through its package (1 nH, 5 mOhm); the die holds a
decoupling capacitance between the two. Signal pins load the internal ground: outputs through a
driver resistance, inputs as their pin capacitance, analog inputs also high resistance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from kae.circuit import values as V

from .circuit import Circuit

# package parasitics of chip passives (ESL, H) by imperial size; MLCC values from vendor data
# (Murata/TDK SPICE models put 0402 at 0.3-0.5 nH, 0805 at 0.6-1 nH), the larger end used
ESL = {"0201": 0.3e-9, "0402": 0.45e-9, "0603": 0.6e-9, "0805": 0.8e-9, "1206": 1.0e-9, "1210": 1.1e-9,
       "1812": 1.3e-9, "2512": 2.0e-9}
ESL_DEFAULT = 1.0e-9
ESL_POLARIZED = 4e-9            # electrolytic and tantalum bodies
ESL_THT = 6e-9
PKG_L = 1.0e-9                  # IC pin: bond wire plus lead
PKG_R = 5e-3
DIE_C = {"logic": 1e-9, "memory": 5e-9, "mcu": 5e-9, "fpga": 50e-9, "opamp": 20e-12, "regulator_linear": 1e-9,
         "regulator_switching": 1e-9, "adc_dac": 1e-9, "reference": 50e-12, "motor_driver": 2e-9, "": 1e-9}
R_DRIVER = 40.0                 # CMOS output, ohm
C_PIN = 5e-12                   # input pin capacitance
R_ANALOG_IN = 10e6
GND_FN = re.compile(r"^(A|D|P|S)?(GND|VSS|VEE|EP|EPAD|PAD|THERMAL|SGND|PGND|AGND|DGND|GNDA|GNDD|0V|COM)\d*([_-].*)?$")
SUP_FN = re.compile(r"^(A|D|P)?(VDD|VCC|VIN|VBAT|VBUS|VS|VDDIO|VDDA|AVDD|DVDD|PVDD|VCCA|VCCIO|VDD\d|VCC\d|V\+|PVIN|VM)\w*$")
SW_FN = re.compile(r"^(SW|LX|PH|PHASE|SWN?\d?)$")


def _rl(R, L):
    return lambda w: R + 1j * w * L


def _rlc(R, L, C):
    return lambda w: R + 1j * w * L + (1 / (1j * w * C) if C else 0)


def _par(z1, z2):
    return lambda w: z1(w) * z2(w) / (z1(w) + z2(w))


@dataclass
class Board:
    """The circuit of one board plus what was assumed to build it."""
    circuit: Circuit
    ground: str
    grounds: set
    rails: dict
    pads_of: dict                 # net -> [pad tokens]
    net_of: dict                  # pad -> net
    part_kind: dict               # ref -> (kind, subtype, role)
    assumptions: list = field(default_factory=list)
    ic_nodes: dict = field(default_factory=dict)   # ref -> {"g": node, rail: node}
    pin_type: dict = field(default_factory=dict)   # pad -> the schematic's pin type ('' when absent)
    pad_xy: dict = field(default_factory=dict)     # pad -> (x, y) mm on the board


def build(board, brief=None):
    """Board from a loaded kae.board model (and its brief, built if absent)."""
    from kae.circuit import brief as B
    from kae.circuit.netlist import Netlist
    if brief is None:
        brief = B.build(board)
    nl = Netlist.from_board(board)
    by_ref = {p["ref"]: p for p in brief["parts"].values()}
    nets = brief["nets"]
    grounds = {n for n, d in nets.items() if d.get("role") == "ground"}
    rails = {n: d.get("volts") for n, d in nets.items() if d.get("role") == "rail"}
    ground = max(grounds, key=lambda g: len(nl.nets[g].pins) if g in nl.nets else 0) if grounds else "GND"
    c = Circuit(ground)
    bd = Board(c, ground, grounds, rails, {}, {}, {})
    cell_parts = {}
    for s in brief.get("structures") or []:
        if s.get("kind") == "commutation_cell":
            for k in ("controller", "inductor"):
                if s.get(k):
                    cell_parts[s[k]] = s
            for u, _ in s.get("loop") or []:
                cell_parts.setdefault(u, s)
    uuid_of = {p["ref"]: u for u, p in brief["parts"].items()}
    for ref, part in nl.parts.items():
        if part.dnp:
            continue
        rec = by_ref.get(ref) or {}
        kind, sub, role = rec.get("kind") or "unknown", rec.get("subtype"), rec.get("role") or ""
        bd.part_kind[ref] = (kind, sub, role)
        pins = [p for p in part.active_pins()]
        for p in pins:
            tok = f"{ref}.{p.number}"
            bd.net_of[tok] = p.net
            bd.pin_type[tok] = p.ptype
            bd.pads_of.setdefault(p.net, []).append(tok)
        in_cell = uuid_of.get(ref) in cell_parts
        _part(bd, ref, part, pins, kind, sub, role, rec, in_cell)
    from kae.board import transform
    for fp in board.footprints:
        for p in fp.pads:
            bd.pad_xy.setdefault(f"{fp.ref}.{p.number}", transform.pad_xy(fp, p))
    return bd


def _two(pins):
    nets = {}
    for p in pins:
        nets.setdefault(p.net, p)
    return list(nets.values())


def _part(bd, ref, part, pins, kind, sub, role, rec, in_cell):
    c = bd.circuit
    tw = _two(pins)
    pkg = V.package(part.lib_id)
    esl = ESL_POLARIZED if pkg.polarized else ESL_THT if pkg.through_hole else ESL.get(pkg.size or "", ESL_DEFAULT)

    def tok(p):
        return f"{ref}.{p.number}"
    if kind == "capacitor" and len(tw) == 2:
        C = V.capacitance(part.value)
        if C is None:
            C = 100e-9
            bd.assumptions.append(f"{ref}: value '{part.value}' unread; 100 nF assumed")
        esr = 0.3 if pkg.polarized else 0.01
        a, b = tw
        c.z(ref, a.net, b.net, _rlc(esr, esl, C), tok(a), tok(b), "C")
    elif kind == "resistor" and len(tw) == 2:
        R = V.resistance(part.value)
        if R is None:
            R = 1e3
            bd.assumptions.append(f"{ref}: value '{part.value}' unread; 1 kOhm assumed")
        a, b = tw
        c.z(ref, a.net, b.net, _rl(max(R, 1e-4), 0.5e-9), tok(a), tok(b), "R")
    elif kind == "inductor" and len(tw) == 2:
        L = V.inductance(part.value) or 10e-6
        a, b = tw
        # an inductor is open at the edges of a switching cell: winding capacitance carries it
        c.z(ref, a.net, b.net, _par(_rl(0.05, L), _rlc(0, 0, 5e-12)), tok(a), tok(b), "L")
    elif kind == "ferrite" and len(tw) == 2:
        a, b = tw
        R100 = 600.0
        m = re.search(r"(\d+(?:\.\d+)?)\s*(R|ohm|Ω)", part.value or "", re.I)
        if m:
            R100 = float(m.group(1))
        Lb = R100 / (2 * 3.14159 * 50e6)
        c.z(ref, a.net, b.net, _par(_rl(0.05, Lb), _rl(R100, 0)), tok(a), tok(b), "FB")
    elif kind == "diode" and len(tw) == 2:
        a, b = tw
        if in_cell:
            c.z(ref, a.net, b.net, _rl(0.05, 1e-9), tok(a), tok(b), "D_on")      # the commutation partner
        else:
            c.z(ref, a.net, b.net, _rlc(1.0, 1e-9, 30e-12), tok(a), tok(b), "D")
    elif kind == "transistor":
        nets = _two(pins)
        if in_cell and len(nets) >= 2:
            _switch_fet(bd, ref, pins)
        else:
            for i in range(len(nets)):
                for j in range(i + 1, len(nets)):
                    c.z(f"{ref}:{i}{j}", nets[i].net, nets[j].net, _rlc(1.0, 1e-9, 20e-12), tok(nets[i]), tok(nets[j]), "Q")
    elif kind in ("led", "crystal", "transformer", "optocoupler") and len(tw) >= 2:
        for i in range(len(tw)):
            for j in range(i + 1, len(tw)):
                c.z(f"{ref}:{i}{j}", tw[i].net, tw[j].net, _rlc(1.0, 1e-9, 10e-12), tok(tw[i]), tok(tw[j]), kind)
    elif kind in ("jumper", "switch") and len(tw) == 2 or (kind == "resistor" and len(tw) != 2):
        if len(tw) == 2:
            c.z(ref, tw[0].net, tw[1].net, _rl(0.01, 1e-9), tok(tw[0]), tok(tw[1]), "short")
    elif kind == "battery" and len(tw) == 2:
        c.z(ref, tw[0].net, tw[1].net, _rl(0.1, 10e-9), tok(tw[0]), tok(tw[1]), "batt")
    elif kind == "ic" or (kind == "unknown" and len(pins) > 3):
        _ic(bd, ref, part, pins, sub or "", role)
    # connectors, test points, holes, fiducials: no circuit inside the board (the world is outside)


def _ic(bd, ref, part, pins, sub, role):
    c = bd.circuit
    g = f"{ref}:gnd"
    nodes = {"g": g}
    gpins = [p for p in pins if p.net in bd.grounds or GND_FN.match(p.fn or "")]
    if not gpins:
        bd.assumptions.append(f"{ref}: no ground pin found; its signal pins reference the board ground")
        g = bd.ground
        nodes["g"] = g
    for p in gpins:
        c.z(f"{ref}.{p.number}:pkg", p.net, g, _rl(PKG_R, PKG_L), f"{ref}.{p.number}", None, "pkg")
    dc = DIE_C.get(sub, DIE_C[""])
    for p in pins:
        if p in gpins:
            continue
        t = f"{ref}.{p.number}"
        fn = p.fn or ""
        if p.net in bd.rails and (p.ptype in ("power_in", "") or SUP_FN.match(fn)) and not SW_FN.match(fn):
            v = f"{ref}:{p.net}"
            if v not in nodes.values():
                nodes[p.net] = v
                c.z(f"{ref}:{p.net}:die", v, g, _rlc(0.1, 0, dc), None, None, "die")
            c.z(f"{t}:pkg", p.net, v, _rl(PKG_R, PKG_L), t, None, "pkg")
        elif p.ptype == "power_out":
            c.z(f"{t}:out", p.net, g, _rl(0.05, 0.2e-6), t, None, "reg_out")
        elif SW_FN.match(fn):
            c.z(f"{t}:sw", p.net, g, _rlc(1.0, PKG_L, 200e-12), t, None, "sw_off")     # switch node C (off)
        elif p.ptype in ("output", "tri_state", "open_collector", "open_emitter"):
            c.z(f"{t}:drv", p.net, g, _rl(R_DRIVER, PKG_L), t, None, "drv")
        else:
            an = bd.part_kind and p.net and False
            c.z(f"{t}:in", p.net, g, _par(_rl(R_ANALOG_IN, PKG_L), _rlc(0, PKG_L, C_PIN)), t, None, "in")
    bd.ic_nodes[ref] = nodes


def _switch_fet(bd, ref, pins):
    """A discrete switch in a commutation cell: its drain-source path conducts (the source of the cell
    is placed across it by kae.excite.sources)."""
    c = bd.circuit
    by = {}
    for p in pins:
        by.setdefault(p.net, p)
    nets = list(by.values())
    for i in range(len(nets)):
        for j in range(i + 1, len(nets)):
            c.z(f"{ref}:{i}{j}", nets[i].net, nets[j].net, _rlc(1.0, 1e-9, 100e-12),
                f"{ref}.{nets[i].number}", f"{ref}.{nets[j].number}", "Q_cell")
