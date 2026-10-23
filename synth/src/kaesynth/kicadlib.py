# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read KiCad symbol and footprint libraries: flattened symbols, pin geometry, pad sets."""
import copy
import functools
import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import sexpr
from .sexpr import Sym

ENV_SYM = ("KICAD10_SYMBOL_DIR", "KICAD9_SYMBOL_DIR", "KICAD_SYMBOL_DIR")
ENV_FP = ("KICAD10_FOOTPRINT_DIR", "KICAD9_FOOTPRINT_DIR", "KICAD_FOOTPRINT_DIR")
DEFAULT_ROOTS = ("/usr/share/kicad", "/usr/local/share/kicad",
                 "/Applications/KiCad/KiCad.app/Contents/SharedSupport")


def _dir(envs, sub):
    for e in envs:
        v = os.environ.get(e)
        if v and Path(v).is_dir():
            return Path(v)
    for r in DEFAULT_ROOTS:
        p = Path(r) / sub
        if p.is_dir():
            return p
    return None


def symbol_dir():
    return _dir(ENV_SYM, "symbols")


def footprint_dir():
    return _dir(ENV_FP, "footprints")


@dataclass
class LibPin:
    number: str
    name: str
    type: str
    x: float          # library coordinates (Y up)
    y: float
    angle: int        # direction from the connection point towards the body
    length: float
    hidden: bool
    unit: int         # 0 = common to all units


@dataclass
class LibSymbol:
    lib_id: str
    node: list        # flattened (symbol "Lib:Name" ...) ready for lib_symbols
    pins: list
    units: int
    power: bool

    def pins_of(self, unit):
        return [p for p in self.pins if p.unit in (0, unit)]

    def bbox(self, unit):
        """(xmin, ymin, xmax, ymax) in library coordinates, body graphics plus pin ends."""
        xs, ys = [], []
        for sub in sexpr.find_all(self.node, "symbol"):
            u = _unit_of(sub[1])
            if u not in (0, unit):
                continue
            for g in sub[2:]:
                if not isinstance(g, list):
                    continue
                for pt in _points(g):
                    xs.append(pt[0])
                    ys.append(pt[1])
        for p in self.pins_of(unit):
            xs.append(p.x)
            ys.append(p.y)
        if not xs:
            return (-2.54, -2.54, 2.54, 2.54)
        return (min(xs), min(ys), max(xs), max(ys))


def _points(g):
    head = g[0]
    if head == "rectangle":
        s, e = sexpr.find(g, "start"), sexpr.find(g, "end")
        return [(float(s[1]), float(s[2])), (float(e[1]), float(e[2]))]
    if head in ("polyline", "bezier"):
        pts = sexpr.find(g, "pts") or []
        return [(float(p[1]), float(p[2])) for p in pts[1:] if isinstance(p, list) and p[0] == "xy"]
    if head == "circle":
        c, r = sexpr.find(g, "center"), sexpr.find(g, "radius")
        cx, cy, rr = float(c[1]), float(c[2]), float(r[1])
        return [(cx - rr, cy - rr), (cx + rr, cy + rr)]
    if head == "arc":
        return [(float(x[1]), float(x[2])) for x in g[1:]
                if isinstance(x, list) and x[0] in ("start", "mid", "end")]
    return []


def _unit_of(subname):
    m = re.search(r"_(\d+)_(\d+)$", subname)
    return int(m.group(1)) if m else 0


class SymbolLibs:
    """Lazy index of `<Lib>.kicad_sym` files in one or more directories."""

    def __init__(self, dirs=None):
        self.dirs = [Path(d) for d in (dirs or [symbol_dir()]) if d]
        self._raw = {}

    def libraries(self):
        names = set()
        for d in self.dirs:
            names.update(p.stem for p in d.glob("*.kicad_sym"))
        return sorted(names)

    def path(self, lib):
        for d in self.dirs:
            p = d / f"{lib}.kicad_sym"
            if p.exists():
                return p
        return None

    def _lib(self, lib):
        if lib not in self._raw:
            p = self.path(lib)
            if p is None:
                self._raw[lib] = None
            else:
                tree = sexpr.loads(p.read_text())
                self._raw[lib] = {s[1]: s for s in sexpr.find_all(tree, "symbol")}
        return self._raw[lib]

    def has(self, lib_id):
        lib, _, name = lib_id.partition(":")
        syms = self._lib(lib)
        return bool(syms) and name in syms

    def names(self, lib):
        return sorted(self._lib(lib) or {})

    @functools.lru_cache(maxsize=None)
    def get(self, lib_id):
        lib, _, name = lib_id.partition(":")
        syms = self._lib(lib)
        if not syms or name not in syms:
            raise KeyError(f"symbol {lib_id} not found in {', '.join(map(str, self.dirs))}")
        node = self._flatten(syms, name)
        node = copy.deepcopy(node)
        node[1] = lib_id
        return parse_symbol(lib_id, node)

    def _flatten(self, syms, name, depth=0):
        node = syms[name]
        ext = sexpr.find(node, "extends")
        if not ext:
            return node
        if depth > 8:
            raise ValueError(f"extends chain too deep at {name}")
        parent = copy.deepcopy(self._flatten(syms, ext[1], depth + 1))
        pname = parent[1]
        out = [Sym("symbol"), name]
        child_props = {p[1]: p for p in sexpr.find_all(node, "property")}
        for x in parent[2:]:
            if isinstance(x, list) and x and x[0] == "property" and x[1] in child_props:
                out.append(child_props.pop(x[1]))
            elif isinstance(x, list) and x and x[0] == "symbol":
                x[1] = re.sub("^" + re.escape(pname) + r"(?=_\d+_\d+$)", name, x[1])
                out.append(x)
            else:
                out.append(x)
        # properties only the child has go before the unit sub-symbols
        extra = list(child_props.values())
        if extra:
            idx = next((i for i, x in enumerate(out) if isinstance(x, list) and x[0] == "symbol"), len(out))
            out[idx:idx] = extra
        return out


def parse_symbol(lib_id, node):
    pins, units = [], 1
    for sub in sexpr.find_all(node, "symbol"):
        u = _unit_of(sub[1])
        units = max(units, u)
        for p in sexpr.find_all(sub, "pin"):
            at, ln = sexpr.find(p, "at"), sexpr.find(p, "length")
            nm, num = sexpr.find(p, "name"), sexpr.find(p, "number")
            hide = sexpr.find(p, "hide")
            hidden = (hide is not None and (len(hide) == 1 or hide[1] == "yes")) or "hide" in p[1:4]
            pins.append(LibPin(number=str(num[1]), name=str(nm[1]), type=str(p[1]),
                               x=float(at[1]), y=float(at[2]), angle=int(float(at[3])) if len(at) > 3 else 0,
                               length=float(ln[1]) if ln else 0.0, hidden=hidden, unit=u))
    power = sexpr.find(node, "power") is not None
    return LibSymbol(lib_id=lib_id, node=node, pins=pins, units=units, power=power)


def renumber(sym: LibSymbol, lib_id, pinmap):
    """Copy of `sym` named `lib_id` with pin numbers changed by `pinmap` {old: new}."""
    node = copy.deepcopy(sym.node)
    old_name = sym.lib_id.split(":", 1)[1]
    new_name = lib_id.split(":", 1)[1]
    node[1] = lib_id
    for sub in sexpr.find_all(node, "symbol"):
        sub[1] = re.sub("^" + re.escape(old_name) + r"(?=_\d+_\d+$)", new_name, sub[1])
        for p in sexpr.find_all(sub, "pin"):
            num = sexpr.find(p, "number")
            if str(num[1]) in pinmap:
                num[1] = str(pinmap[str(num[1])])
    return parse_symbol(lib_id, node)


class FootprintLibs:
    def __init__(self, root=None):
        self.root = Path(root) if root else footprint_dir()

    def path(self, lib_id):
        if not self.root or ":" not in lib_id:
            return None
        lib, _, name = lib_id.partition(":")
        p = self.root / f"{lib}.pretty" / f"{name}.kicad_mod"
        return p if p.exists() else None

    def has(self, lib_id):
        return self.path(lib_id) is not None

    @functools.lru_cache(maxsize=None)
    def pads(self, lib_id):
        """Set of named (electrical) pad numbers; '' (unnamed mechanical pads) excluded."""
        p = self.path(lib_id)
        if p is None:
            raise KeyError(f"footprint {lib_id} not found under {self.root}")
        return frozenset(n for n in re.findall(r'\(pad\s+"([^"]*)"', p.read_text()) if n)
