# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small-signal circuit of a board in the frequency domain (modified nodal analysis), at the pad level.

Nodes are the board's nets (ideal copper: the zeroth order) plus parts' internal nodes. Every
element records which pads it connects, so a solve returns, for each excitation source, the
current each part pushes into the copper at each pad: J[pad]. Those injection vectors are what
the copper has to carry. Inside any one net they sum to zero (KCL); injected into a field solve
of the copper, they give the parasitic voltages the layout adds (kae.excite.evaluate).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as sla

G_LEAK = 1e-9           # S to the reference from every node: keeps floating islands solvable


@dataclass
class Elem:
    name: str
    a: str
    b: str
    z: object               # callable w -> complex impedance
    pa: str | None = None   # pad at a (None: internal node)
    pb: str | None = None
    kind: str = ""


@dataclass
class Source:
    """A unit excitation: a current of 1 A (times `scale`) driven from a to b through the source."""
    name: str
    a: str
    b: str
    pa: str | None = None
    pb: str | None = None
    kind: str = ""
    meta: dict = field(default_factory=dict)


class Circuit:
    def __init__(self, ground):
        self.ground = ground
        self.elems: list[Elem] = []
        self.sources: list[Source] = []
        self.nodes = {ground: 0}

    def node(self, n):
        if n not in self.nodes:
            self.nodes[n] = len(self.nodes)
        return self.nodes[n]

    def z(self, name, a, b, z, pa=None, pb=None, kind=""):
        if a == b:
            return None
        self.node(a), self.node(b)
        e = Elem(name, a, b, z, pa, pb, kind)
        self.elems.append(e)
        return e

    def src(self, name, a, b, pa=None, pb=None, kind="", **meta):
        self.node(a), self.node(b)
        s = Source(name, a, b, pa, pb, kind, meta)
        self.sources.append(s)
        return s

    def _Y(self, w):
        n = len(self.nodes)
        ia = np.array([self.nodes[e.a] for e in self.elems])
        ib = np.array([self.nodes[e.b] for e in self.elems])
        y = np.array([1.0 / max_abs(e.z(w)) for e in self.elems], complex)
        rows = np.concatenate([ia, ib, ia, ib, np.arange(n)])
        cols = np.concatenate([ia, ib, ib, ia, np.arange(n)])
        vals = np.concatenate([y, y, -y, -y, np.full(n, G_LEAK)])
        Y = sp.csc_matrix((vals, (rows, cols)), shape=(n, n))
        keep = np.arange(1, n)                         # node 0 (ground) is the reference
        return Y[keep][:, keep].tocsc(), ia, ib, y

    def solve(self, f, sources=None):
        """{source name: dict(V={node: V}, J={pad: A}, I={elem name: A})} at frequency f (Hz), each source
        driving 1 A."""
        w = 2 * np.pi * f
        Y, ia, ib, y = self._Y(w)
        lu = sla.splu(Y)
        out = {}
        names = list(self.nodes)
        for s in (sources or self.sources):
            rhs = np.zeros(len(self.nodes), complex)
            rhs[self.nodes[s.b]] += 1.0
            rhs[self.nodes[s.a]] -= 1.0
            V = np.r_[0.0, lu.solve(rhs[1:])]
            Ie = (V[ia] - V[ib]) * y                     # a -> b through each element
            J = {}
            for e, i in zip(self.elems, Ie):
                if e.pa:
                    J[e.pa] = J.get(e.pa, 0) - i       # leaves the copper at a into the part
                if e.pb:
                    J[e.pb] = J.get(e.pb, 0) + i
            if s.pa:
                J[s.pa] = J.get(s.pa, 0) - 1.0
            if s.pb:
                J[s.pb] = J.get(s.pb, 0) + 1.0
            out[s.name] = dict(V=dict(zip(names, V)), J=J, I={e.name: i for e, i in zip(self.elems, Ie)})
        return out


def max_abs(z, floor=1e-6):
    """An impedance kept away from zero (an ideal short becomes 1 micro-ohm)."""
    return z if abs(z) > floor else floor
