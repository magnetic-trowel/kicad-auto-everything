# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Simulator-safe names for board objects.

ngspice folds names to lower case, forbids `= % ( ) , [ ] < > ~` in node names, and resolves
`x1.n` to node n inside instance X1. So every node and element gets a generated name: a counter
plus a short lower-case hint of letters, digits and underscores (`n12_p3v3`), never a dot.
The map is kept both ways, so results translate back to KiCad's names.
"""
from __future__ import annotations

import re

GROUND = "0"
_HINT = re.compile(r"[^a-z0-9]+")


def _hint(text, n=16):
    t = text.lower().replace("+", "p").replace("-", "m")
    return _HINT.sub("_", t).strip("_")[:n]


class Namer:
    """Node and element names; `node(key)` for keys such as 'net:+3V3', 'pin:U5.12', 'x:<id>'."""

    def __init__(self):
        self._node = {}
        self._elem = {}
        self.back = {}            # simulator name -> key

    def node(self, key):
        if key == GROUND:
            return GROUND
        v = self._node.get(key)
        if v is None:
            v = f"n{len(self._node) + 1}"
            h = _hint(key.split(":", 1)[-1])
            if h:
                v = f"{v}_{h}"
            self._node[key] = v
            self.back[v] = key
        return v

    def element(self, kind, key):
        """A fresh element name of SPICE type `kind` (R, L, C, K, V, I, B, S, E, D, X)."""
        k = (kind, key)
        v = self._elem.get(k)
        if v is None:
            v = f"{kind.lower()}{len(self._elem) + 1}"
            h = _hint(key, 12)
            if h:
                v = f"{v}_{h}"
            self._elem[k] = v
            self.back[v] = key
        return v
