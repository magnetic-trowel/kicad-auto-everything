# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The board's passives as circuit elements between pin keys ('pin:C5.1').

Values come from the value field (kae.circuit.values, which drops ratings such as "10uF 35V").
Capacitors get a series ESR and ESL by package (E5 priors: ceramic chips; electrolytics larger), since
decoupling and switching behaviour depend on them. Ferrite beads are a series R and L (E5). Parts
whose value cannot be read are listed in `skipped` with the reason; ICs, connectors and other active
parts are left to the testbench, which models them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from kae.circuit import values as V

# ESL (H) and ESR (ohm) of a mounted ceramic chip capacitor by imperial size (E5: vendor curves of
# X7R/X5R parts; the mounting loop is the extracted copper, not this)
CAP_ESL = {"01005": 0.25e-9, "0201": 0.3e-9, "0402": 0.4e-9, "0603": 0.6e-9, "0805": 0.8e-9,
           "1206": 1.0e-9, "1210": 1.0e-9, "1812": 1.2e-9}
CAP_ESR = 0.01
ELEC_ESL, ELEC_ESR = 5e-9, 0.1
FERRITE_R, FERRITE_L = 0.1, 1e-6


@dataclass
class Part:
    ref: str
    kind: str                       # R | C | L | FB
    pins: tuple                     # (pin key a, pin key b)
    value: float
    esr: float = 0.0
    esl: float = 0.0
    basis: str = ""


@dataclass
class Design:
    parts: list = field(default_factory=list)
    skipped: dict = field(default_factory=dict)      # ref -> reason
    pin_net: dict = field(default_factory=dict)      # pin key -> net

    def touching(self, nets):
        nets = set(nets)
        return [p for p in self.parts if any(self.pin_net.get(k) in nets for k in p.pins)]


def _kind(fp, brief_part):
    k = (brief_part or {}).get("kind") or ""
    ref = re.sub(r"\d+$", "", fp.ref.upper())
    if k == "resistor" or ref in ("R", "RN"):
        return "R"
    if k == "capacitor" or ref == "C":
        return "C"
    if k in ("ferrite", "ferrite_bead") or ref in ("FB", "FL") or "ferrite" in (fp.lib_id or "").lower():
        return "FB"
    if k == "inductor" or ref == "L":
        return "L"
    return None


def build(board, brief=None):
    parts = (brief or {}).get("parts") or {}
    d = Design()
    for fp in board.footprints:
        for p in fp.pads:
            if p.net:
                d.pin_net[f"pin:{fp.ref}.{p.number}"] = p.net
    for fp in board.footprints:
        kind = _kind(fp, parts.get(fp.uuid))
        if kind is None:
            continue
        pads = [p for p in fp.pads if p.net]
        nets = {p.net for p in pads}
        if len(pads) != 2 or len(nets) != 2:
            d.skipped[fp.ref] = f"{len(pads)} connected pads on {len(nets)} nets (need 2 on 2)"
            continue
        keys = tuple(f"pin:{fp.ref}.{p.number}" for p in pads)
        text = fp.value or ""
        if kind == "R":
            v = V.resistance(text)
            if v is None:
                d.skipped[fp.ref] = f"resistance unreadable from {text!r}"
                continue
            d.parts.append(Part(fp.ref, "R", keys, max(v, 1e-6), basis=f"value {text!r}"))
        elif kind == "C":
            v = V.capacitance(text)
            if v is None:
                d.skipped[fp.ref] = f"capacitance unreadable from {text!r}"
                continue
            pkg = V.package(fp.lib_id)
            if pkg.polarized:
                esl, esr, why = ELEC_ESL, ELEC_ESR, "electrolytic prior"
            else:
                esl, esr, why = CAP_ESL.get(pkg.size or "", 0.8e-9), CAP_ESR, f"ceramic {pkg.size or 'unknown size'} prior"
            d.parts.append(Part(fp.ref, "C", keys, v, esr=esr, esl=esl, basis=f"value {text!r}; ESR/ESL {why} (E5)"))
        elif kind == "L":
            v = V.inductance(text)
            if v is None:
                d.skipped[fp.ref] = f"inductance unreadable from {text!r}"
                continue
            d.parts.append(Part(fp.ref, "L", keys, v, esr=0.05, basis=f"value {text!r}; DCR 50 mOhm prior (E5)"))
        else:
            d.parts.append(Part(fp.ref, "FB", keys, FERRITE_L, esr=FERRITE_R, basis="ferrite bead prior R + L (E5)"))
    return d
