# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small-signal models of a board's parts, built from comprehension (kae.circuit brief + netlist).

Each part becomes impedances between its pads (or to its internal nodes). Values are the part's
own (C, R, L from its value field) plus parasitics by package; where a part's data is unknown the
model is a class stand-in, recorded in `Board.assumptions`. The stand-ins set how the circuit's
high-frequency current divides between parts; they never decide geometry rankings (an error in
them scales a structure's price, see docs/topics/architecture/physics-driven-design.md §3).

Ports: a connector, or a module (a board of its own soldered onto this one), is where the board's
copper meets circuitry the board does not model. A port's pins carry what arrives from or leaves to
that circuitry, returning through the port's own ground pin nearest to the pin (the cable's return, or
the module's ground): a clock arriving or leaving there (kae.excite.sources), and a rail that only the
port supplies (`_port_supplies`: the cable from the host's decoupling, or the module's own). A port is
never modelled as an IC.

Integrated circuits: every ground pin reaches one internal ground node, every supply pin of one
rail an internal supply node, each through its package (1 nH, 5 mOhm); the die holds a
decoupling capacitance between the two. Signal pins load the internal ground: outputs through a
driver resistance, inputs as their pin capacitance, analog inputs also high resistance.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from kae.circuit import values as V

from .circuit import Circuit

# package parasitics of chip passives (ESL, H) by imperial size; MLCC values from vendor data
# (Murata/TDK SPICE models put 0402 at 0.3-0.5 nH, 0805 at 0.6-1 nH), the larger end used
ESL = {"0201": 0.3e-9, "0402": 0.45e-9, "0603": 0.6e-9, "0805": 0.8e-9, "1206": 1.0e-9, "1210": 1.1e-9,
       "1812": 1.3e-9, "2512": 2.0e-9}
ESL_DEFAULT = 1.0e-9
ESL_THT = 7e-9                  # a through-hole disc or film capacitor: "a small 0.1 uF disc ... as low as 7 nH"
#                                 (Bogatin, Smith & Sandler, SIJ 2020); Murata: ~10 nH with 10 mm of lead
# MLCC capacitance under DC bias (docs/research/physics/component-priors.md). Class-2 ceramics lose
# capacitance with the DC field in their layers (Zednicek, EPCI "High CV MLCC DC/AC bias, ageing:
# capacitance loss explained", 2019: "proportional to the DC field (V/mm)"). A footprint gives the body,
# not the layer thickness t; at fixed permittivity C/volume ~ 1/t^2, so the field V/t ~ V sqrt(C/volume)
# (z, V sqrt(F/mm^3)) for a part that fills its body, as high-value parts do. C(V)/C = 1/(1 + (z/Z0)^P),
# fitted to vendor bias curves (10 uF X5R 0402/0603/0805 and 100 nF X7R 0402/0603 at 3.3 and 5 V;
# decoupling-pdn.md: 10 uF 6.3 V 0402 ~ 1.5 uF at 5 V; EPCI: 10 uF 6.3 V 0805 keeps 68-88 % at 3.3 V):
# within about 0.15 of the curves, which spread 2x between vendors for one nominal part.
DCB_Z0 = 0.011
DCB_P = 1.3
# body width = height of a full chip (mm), for its volume L x W x H with H = W (capped at 2.5 mm)
CHIP_LW = {"01005": (0.4, 0.2), "0201": (0.6, 0.3), "0402": (1.0, 0.5), "0603": (1.6, 0.8), "0805": (2.0, 1.25),
           "1206": (3.2, 1.6), "1210": (3.2, 2.5), "1812": (4.5, 3.2), "2220": (5.7, 5.0)}
CLASS1_MAX_C = 1e-9             # an unmarked ceramic at or below 1 nF is taken as C0G (no bias loss)
DIELECTRIC_RE = re.compile(r"\b(X5R|X7R|X7S|X7T|X6S|X8R|X8L|Y5V|Z5U|C0G|COG|NP0|NPO|U2J|X5S)\b", re.I)
# MLCC ESR at self-resonance falls with capacitance (more electrodes in parallel): 10 mOhm x (C/1 uF)^-1/2
# gives 32 mOhm at 100 nF, 3 mOhm at 10 uF, typical of vendor impedance curves (a class stand-in, stated
# in the assumptions), clamped to 2 mOhm .. 0.5 Ohm.
ESR_1UF = 0.01
# Polarized capacitors (docs/research/physics/component-priors.md), ESL (H) and ESR (Ohm) at 100 kHz:
# - tantalum chips by EIA case: ESL of molded MnO2 parts from Vishay's tantalum FAQ (doc 40110: A 1.2,
#   B 1.6, C 2.4, D 2.7, E 2.9, V 2.5 nH); ESR from AVX TAJ maxima at 6.3-16 V (A 3-4, B 2.5-3, C 1-2,
#   D 0.4-1.1, E 0.9 Ohm), taken near the low end (typicals sit below the maxima). Polymer parts share
#   the case ESL; ESR 40 mOhm (Vishay polymer guide: 5-200 mOhm; KEMET T520 25-40 mOhm).
# - SMD aluminium (V-chip) by can diameter: ESL 4 nH (Chemi-Con: "4nH for miniature radial"); ESR from
#   Panasonic FK impedance at 100 kHz (6.3 mm 0.36, 10 mm 0.08 Ohm).
# - radial aluminium by can diameter: ESL from TDK B41858 ("8...12.5 mm -> 20 nH; 16 mm -> 26 nH; 18 mm ->
#   34 nH"), 10 nH below 8 mm (Chemi-Con 4 nH to Vishay's 5-25 nH range); ESR of low-impedance series at
#   100 kHz (TDK B41858, Panasonic FR: 5 mm 0.3, 6.3 mm 0.13, 8 mm 0.15, 10 mm 0.08 Ohm). A general-purpose
#   series runs higher. The "47 uF electrolytic ~30 nH" of decoupling-pdn.md is Bogatin's upper bound.
TANT_CASE = {"A": (1.2e-9, 3.0), "B": (1.6e-9, 2.0), "C": (2.4e-9, 1.0), "D": (2.7e-9, 0.5), "E": (2.9e-9, 0.5),
             "V": (2.5e-9, 0.5), "W": (2.6e-9, 0.5), "R": (1.2e-9, 4.0), "P": (1.2e-9, 4.0), "T": (1.6e-9, 2.0)}
TANT_EIA = {"2012": "R", "3216": "A", "3528": "B", "6032": "C", "7343": "D", "7360": "E", "7361": "V"}
POLYMER_ESR = 0.04
SMD_ALU = ((4.0, 1.35), (5.0, 0.8), (6.3, 0.36), (8.0, 0.17), (10.0, 0.08), (99.0, 0.05))     # (<= D mm, ESR)
SMD_ALU_ESL = 4e-9
RADIAL = ((5.0, 10e-9, 0.3), (6.3, 10e-9, 0.13), (8.0, 20e-9, 0.15), (12.5, 20e-9, 0.08), (16.0, 26e-9, 0.05),
          (999.0, 34e-9, 0.04))                                                         # (<= D mm, ESL, ESR)
AXIAL = (20e-9, 0.3)
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
# a part the brief left unclassified, or called a jumper, that is a connector by its value or footprint:
# an Eagle pin header (1X07, 2X05, with a JP refdes), a card holder, a display's FPC socket
PORT_FN = re.compile(r"conn|header|socket|holder|receptacle|(?<![a-z])sim(?![a-z])|fpc|ffc|(?<![a-z0-9])\d{1,2}x\d{2}", re.I)
L_CABLE = 50e-9                 # a rail supplied through a connector: the cable's loop to the host's decoupling,
R_CABLE = 5.0                   # damped (wire, the host capacitor's ESR, the line's loss); stand-ins
C_MODULE = 1e-6                 # a rail supplied by a module's pin: the module's own decoupling


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
    port: dict = field(default_factory=dict)       # ref -> "connector" | "module": where the copper meets
    #                                                circuitry off this board's model


def port_kind(kind, part, pads):
    """"connector" or "module" when the part is a port (module docstring), else None. pads: its pad count."""
    if kind in ("connector", "module"):
        return kind
    text = f"{part.value} {part.lib_id.split(':')[-1]}"
    if kind == "jumper" and pads > 3 and PORT_FN.search(text) or kind == "unknown" and PORT_FN.search(text):
        return "connector"
    return None


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
        pk = port_kind(kind, part, len(pins))
        if pk:
            bd.port[ref] = pk
            if pk != kind:
                bd.assumptions.append(f"{ref} ({kind} in the brief) is named '{part.value} {part.lib_id}': taken as a connector")
            continue                 # no circuit inside the board: the world is outside
        _part(bd, ref, part, pins, kind, sub, role, rec, in_cell)
    from kae.board import transform
    for fp in board.footprints:
        for p in fp.pads:
            bd.pad_xy.setdefault(f"{fp.ref}.{p.number}", transform.pad_xy(fp, p))
    _port_supplies(bd)
    return bd


def nearest_ground(bd, ref, pad):
    """The part's ground pin nearest to its pad (the return path of a signal it drives or receives)."""
    import math
    gs = [t for nt in bd.grounds for t in bd.pads_of.get(nt, []) if t.rsplit(".", 1)[0] == ref]
    if not gs:
        return None
    x, y = bd.pad_xy.get(pad, (0.0, 0.0))
    return min(gs, key=lambda t: math.dist(bd.pad_xy.get(t, (x, y)), (x, y)) if t in bd.pad_xy else math.inf)


SINKS = ("pkg", "in", "die")    # elements that draw from a rail, but cannot supply its AC current


def _port_supplies(bd):
    """A rail whose only parts on the board draw from it (IC supply and input pins) is supplied, at AC as at
    DC, by what feeds it through a port: the cable to the host's decoupling (a connector) or the module's
    own decoupling. Each such port pin becomes that supply, to the port's nearest ground pin (a module's pins
    only, when one is on the rail: a connector beside it exports the rail). A rail with
    any other part on it (a capacitor, a regulator's output, a series part to another net) is supplied on
    the board and keeps its model unchanged."""
    c = bd.circuit
    for net in bd.rails:
        toks = bd.pads_of.get(net, [])
        pins = [t for t in toks if bd.port.get(t.rsplit(".", 1)[0])]
        mods = [t for t in pins if bd.port[t.rsplit(".", 1)[0]] == "module"]
        pins = mods or pins          # a module on the rail is its supplier; the connectors beside it export it
        if not pins or any(e.kind not in SINKS for e in c.elems if net in (e.a, e.b)):
            continue
        for t in pins:
            ref = t.rsplit(".", 1)[0]
            g = nearest_ground(bd, ref, t)
            if g is None:
                bd.assumptions.append(f"{net}: supplied through {t}, which has no ground pin beside it; left open")
                continue
            if bd.port[ref] == "module":
                z, what = _rlc(0.01, PKG_L + ESL_DEFAULT, C_MODULE), f"the module's decoupling ({C_MODULE * 1e6:g} uF)"
            else:
                z, what = _rl(R_CABLE, L_CABLE), f"a cable of {L_CABLE * 1e9:g} nH to the host's decoupling"
            c.z(f"{t}:supply", net, bd.net_of[g], z, t, g, "port")
            bd.assumptions.append(f"{net}: nothing on the board supplies it but {t}: {what}, returning at {g}")


def dielectric(text):
    """The ceramic dielectric named in a part's text ('C0G' for NP0/COG), or None."""
    m = DIELECTRIC_RE.search(text or "")
    if not m:
        return None
    d = m.group(1).upper()
    return "C0G" if d in ("COG", "NP0", "NPO", "U2J") else d


def mlcc_bias_factor(C, v_bias, size, diel=None):
    """(C(V)/C, basis) of a ceramic chip capacitor of nominal C (F) at DC bias v_bias (V), body `size`
    (imperial code) and dielectric (None: unknown). See DCB_Z0."""
    if diel == "C0G" or (diel is None and C <= CLASS1_MAX_C):
        return 1.0, "class 1 (C0G): no DC-bias loss"
    if not v_bias or v_bias <= 0:
        return 1.0, "no DC bias known"
    lw = CHIP_LW.get(size or "", CHIP_LW["0603"])
    vol = lw[0] * lw[1] * min(lw[1], 2.5)
    z = v_bias * math.sqrt(C / vol)
    z0 = DCB_Z0 / (2.0 if diel in ("Y5V", "Z5U") else 1.0)
    k = 1.0 / (1.0 + (z / z0) ** DCB_P)
    return k, (f"DC bias {v_bias:g} V on {V.si(C, 'F')} {diel or 'class 2'} {size or '0603 (size unknown)'}: "
               f"C x {k:.2f} (field proxy V sqrt(C/volume))")


def mlcc_esr(C):
    return min(max(ESR_1UF * (C / 1e-6) ** -0.5, 2e-3), 0.5)


def polar_model(pkg, text):
    """(ESL H, ESR Ohm, basis) of a polarized capacitor from its footprint and text (see TANT_CASE)."""
    t = f"{pkg.text} {text}"
    poly = re.search(r"polymer|POSCAP|SP-?Cap|OS-?CON|T52\d|T53\d|TPE|TCJ|NOJ|PolyTan", t, re.I)
    if re.search(r"Tantal|CP_Tant|CP_EIA|TAJ|T491|T52\d|T53\d|TPS[A-Z]|293D|TCJ|NOJ|Case[-_][A-EVWRPT]\b", t, re.I) or \
            (poly and not re.search(r"Elec|Radial|D\d", t)):
        m = re.search(r"(?:Case|Kemet|AVX)[-_]([A-EVWRPT])\b", t)
        e = re.search(r"EIA[-_]?(\d{4})", t)
        case = m.group(1) if m else TANT_EIA.get(e.group(1)) if e else None
        esl, esr = TANT_CASE.get(case or "B")
        if poly:
            esr = POLYMER_ESR
        return esl, esr, (f"{'polymer' if poly else 'MnO2 tantalum'} chip, case {case or 'B (unknown)'}: "
                          f"ESL {esl * 1e9:.2g} nH, ESR {esr * 1e3:.3g} mOhm")
    d = re.search(r"(?:D|_)(\d+(?:\.\d+)?)(?:mm)?(?:_|x)", pkg.text)
    dia = float(d.group(1)) if d else None
    dia = dia if dia and 3.0 <= dia <= 40.0 else None
    if re.search(r"Axial", t, re.I):
        esl, esr = AXIAL
        return esl, esr, f"axial aluminium electrolytic: ESL {esl * 1e9:.2g} nH, ESR {esr:g} Ohm"
    if pkg.through_hole or re.search(r"Radial", t, re.I):
        _, esl, esr = next(r for r in RADIAL if (dia or 6.3) <= r[0])
        esr = POLYMER_ESR if poly else esr
        return esl, esr, (f"radial aluminium {'polymer' if poly else 'electrolytic'}, D {dia or '6.3 (unknown)'} mm: "
                          f"ESL {esl * 1e9:.2g} nH, ESR {esr * 1e3:.3g} mOhm")
    esr = POLYMER_ESR if poly else next(r for r in SMD_ALU if (dia or 6.3) <= r[0])[1]
    return SMD_ALU_ESL, esr, (f"SMD aluminium {'polymer' if poly else 'electrolytic'}, D {dia or '6.3 (unknown)'} mm: "
                              f"ESL {SMD_ALU_ESL * 1e9:.2g} nH, ESR {esr * 1e3:.3g} mOhm")


def _bias(bd, a, b):
    """The DC voltage across two nets from the brief's rail voltages (grounds at 0), or None."""
    def v(n):
        if n in bd.grounds:
            return 0.0
        return bd.rails.get(n)
    va, vb = v(a), v(b)
    if va is None or vb is None:
        return None
    return abs(va - vb)


def _two(pins):
    nets = {}
    for p in pins:
        nets.setdefault(p.net, p)
    return list(nets.values())


def _part(bd, ref, part, pins, kind, sub, role, rec, in_cell):
    c = bd.circuit
    tw = _two(pins)
    pkg = V.package(part.lib_id)
    esl = ESL_THT if pkg.through_hole else ESL.get(pkg.size or "", ESL_DEFAULT)

    def tok(p):
        return f"{ref}.{p.number}"
    if kind == "capacitor" and len(tw) == 2:
        C = V.capacitance(part.value)
        if C is None:
            C = 100e-9
            bd.assumptions.append(f"{ref}: value '{part.value}' unread; 100 nF assumed")
        a, b = tw
        text = part.text() if hasattr(part, "text") else f"{part.value} {part.lib_id}"
        if pkg.polarized:
            esl, esr, why = polar_model(pkg, text)
            bd.assumptions.append(f"{ref}: {why} (class stand-in)")
        else:
            esr = mlcc_esr(C)
            vb = _bias(bd, a.net, b.net)
            k, why = mlcc_bias_factor(C, vb, pkg.size, dielectric(text)) if not pkg.through_hole else (1.0, "")
            if k < 0.97:
                bd.assumptions.append(f"{ref}: {why}; ESR {esr * 1e3:.3g} mOhm (class stand-in)")
            vr = V.rated_voltage(text)
            if vr and vb and vb > vr:
                bd.assumptions.append(f"{ref}: {vb:g} V across a part rated {vr:g} V")
            C *= k
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
