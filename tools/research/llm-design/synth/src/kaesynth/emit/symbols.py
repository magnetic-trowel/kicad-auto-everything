# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve each PartDef to a schematic symbol: a KiCad library symbol, a renumbered copy
(pinmap), or a generated box symbol from the part's PinDefs."""
import re

from .. import sexpr
from ..kicadlib import LibSymbol, parse_symbol, renumber
from ..sexpr import S, Sym

PROJECT_LIB = "kaesynth"
GRID = 2.54
CHAR_W = 1.05     # mm per character at 1.27 mm font, generous


def font(size=1.27):
    return S("effects", S("font", S("size", size, size)))


def prop(name, value, x=0.0, y=0.0, angle=0, hide=False, justify=None):
    eff = font()
    if justify:
        eff.append(S("justify", *[Sym(j) for j in justify.split()]))
    node = S("property", name, str(value), S("at", float(x), float(y), angle))
    if hide:
        node.append(S("hide", Sym("yes")))
    node.append(eff)
    return node


def _sanitize(name):
    return re.sub(r"[^A-Za-z0-9_.\-]", "_", name)


_GND = re.compile(r"^(GND|VSS|AGND|DGND|PGND|SGND|GNDA|GNDD|EP|PAD|EPAD|VEE|V-|0V|COM)\w*$", re.I)
_PWR = re.compile(r"^(VCC|VDD|VIN|VBAT|VS|VDDA|VDDIO|AVDD|DVDD|V\+|VBUS|VREG|VOUT|VCCA|VCCB|VBST|BOOT|VM|VPP|5V|3V3)\w*$", re.I)


def _auto_side(pin):
    if pin.side:
        return pin.side
    if pin.type == "power_in" and _GND.match(pin.name or ""):
        return "left_bottom"
    if pin.type == "power_out":
        return "right"
    if pin.type == "power_in" or _PWR.match(pin.name or ""):
        return "left_top"
    if _GND.match(pin.name or ""):
        return "left_bottom"
    if pin.type in ("output", "open_collector", "open_emitter", "tri_state"):
        return "right"
    if pin.type == "input":
        return "left"
    return None


def generate_symbol(lib_id, pins, ref_prefix, value):
    """Box symbol; pins on left/right (or top/bottom when PinDef.side asks for it)."""
    name = lib_id.split(":", 1)[1]
    units = sorted({max(p.unit, 1) for p in pins})
    node = S("symbol", lib_id, S("pin_names", S("offset", 1.016)), S("exclude_from_sim", Sym("no")),
             S("in_bom", Sym("yes")), S("on_board", Sym("yes")))
    body_nodes = []
    max_h = 0
    for u in units:
        upins = [p for p in pins if max(p.unit, 1) == u]
        sides = {"left": [], "right": [], "top": [], "bottom": []}
        left_top, left_bottom, free = [], [], []
        for p in upins:
            s = _auto_side(p)
            if s == "left_top":
                left_top.append(p)
            elif s == "left_bottom":
                left_bottom.append(p)
            elif s is None:
                free.append(p)
            else:
                sides[s].append(p)
        sides["left"] = left_top + sides["left"]
        for p in free:
            (sides["left"] if len(sides["left"]) + len(left_bottom) <= len(sides["right"]) else sides["right"]).append(p)
        sides["left"] += left_bottom
        nl, nr = len(sides["left"]), len(sides["right"])
        nt, nb = len(sides["top"]), len(sides["bottom"])
        rows = max(nl, nr, 1)
        name_w = lambda ps: max([len(p.name or "") for p in ps] + [0]) * CHAR_W
        # top/bottom pin names read vertically inside the body: keep side pins clear of them
        top_room = GRID * -(-(name_w(sides["top"]) + 1.27) // GRID) if nt else 0.0
        bot_room = GRID * -(-(name_w(sides["bottom"]) + 1.27) // GRID) if nb else 0.0
        w = max(name_w(sides["left"]) + name_w(sides["right"]) + 4.0, (max(nt, nb) + 1) * GRID, 10.16)
        half_w = GRID * max(2, -(-w / 2 // GRID))
        side_h = (rows + 1) * GRID + top_room + bot_room
        half_h = GRID * max(1, -(-side_h / 2 // GRID))
        if nt or nb:
            half_h = max(half_h, GRID * 2)
        max_h = max(max_h, half_h)
        pin_nodes = []

        def pin_node(p, x, y, ang):
            return S("pin", Sym(p.type), Sym("line"), S("at", round(x, 3), round(y, 3), ang),
                     S("length", GRID), S("name", p.name or "~", font()), S("number", p.number, font()))

        top_y = half_h - GRID - top_room
        for i, p in enumerate(sides["left"]):
            pin_nodes.append(pin_node(p, -half_w - GRID, top_y - i * GRID, 0))
        for i, p in enumerate(sides["right"]):
            pin_nodes.append(pin_node(p, half_w + GRID, top_y - i * GRID, 180))
        for i, p in enumerate(sides["top"]):
            pin_nodes.append(pin_node(p, -half_w + GRID * (i + 1), half_h + GRID, 270))
        for i, p in enumerate(sides["bottom"]):
            pin_nodes.append(pin_node(p, -half_w + GRID * (i + 1), -half_h - GRID, 90))
        body = S("symbol", f"{name}_{u}_1",
                 S("rectangle", S("start", -half_w, half_h), S("end", half_w, -half_h),
                   S("stroke", S("width", 0.254), S("type", Sym("default"))), S("fill", S("type", Sym("background")))),
                 *pin_nodes)
        body_nodes.append(body)
    node += [prop("Reference", ref_prefix, 0, max_h + 1.27, justify="left bottom"),
             prop("Value", value, 0, -max_h - 1.27, justify="left top"),
             prop("Footprint", "", hide=True), prop("Datasheet", "", hide=True),
             prop("Description", "", hide=True)]
    # left-align reference/value at the body's left edge
    for pn in node:
        if isinstance(pn, list) and pn and pn[0] == "property" and pn[1] in ("Reference", "Value"):
            at = sexpr.find(pn, "at")
            at[1] = -_body_half_w(body_nodes[0])
    node += body_nodes
    node.append(S("embedded_fonts", Sym("no")))
    return parse_symbol(lib_id, node)


def _body_half_w(body):
    rect = sexpr.find(body, "rectangle")
    return abs(float(sexpr.find(rect, "start")[1]))


class SymbolTable:
    """PartDef -> (lib_id, LibSymbol); collects project-library symbols."""

    def __init__(self, symlibs):
        self.libs = symlibs
        self.by_def = {}
        self.project = {}       # lib_id -> LibSymbol for kaesynth:* symbols
        self.used_libs = set()

    def resolve(self, defn, pins):
        key = id(defn)
        if key in self.by_def:
            return self.by_def[key]
        if defn.symbol and not defn.pinmap:
            sym = self.libs.get(defn.symbol)
            self.used_libs.add(defn.symbol.split(":", 1)[0])
            res = (defn.symbol, sym)
        elif defn.symbol:
            base = self.libs.get(defn.symbol)
            tag = "".join(f"{k}{v}" for k, v in sorted(defn.pinmap.items(), key=lambda kv: kv[1]))
            lib_id = f"{PROJECT_LIB}:{_sanitize(defn.symbol.split(':', 1)[1])}_{_sanitize(tag)}"
            if lib_id not in self.project:
                self.project[lib_id] = renumber(base, lib_id, defn.pinmap)
            res = (lib_id, self.project[lib_id])
        else:
            stem = _sanitize(defn.mpn or defn.value or "part")
            lib_id = f"{PROJECT_LIB}:{stem}"
            sig = tuple((p.number, p.name, p.type, p.side, p.unit) for p in pins)
            n = 1
            while lib_id in self.project and getattr(self.project[lib_id], "_sig", None) != sig:
                n += 1
                lib_id = f"{PROJECT_LIB}:{stem}_{n}"
            if lib_id not in self.project:
                sym = generate_symbol(lib_id, pins, defn.prefix, defn.mpn or defn.value or stem)
                sym._sig = sig
                self.project[lib_id] = sym
            res = (lib_id, self.project[lib_id])
        self.by_def[key] = res
        return res

    def project_library(self):
        """Contents of kaesynth.kicad_sym (symbol names without the library prefix)."""
        out = S("kicad_symbol_lib", S("version", 20251024), S("generator", "kaesynth"),
                S("generator_version", "0.1"))
        for lib_id, sym in sorted(self.project.items()):
            node = [x for x in sym.node]
            node = sexpr.loads(sexpr.dumps(node))
            node[1] = lib_id.split(":", 1)[1]
            out.append(node)
        return sexpr.dumps(out) + "\n"
