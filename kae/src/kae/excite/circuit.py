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


def lump_into(bd_circuit, mesh_pad, part):
    """Every two-pad element of the circuit as a lumped part of a copper model: mesh_pad(token) makes
    or finds the terminal (raises if the pad is not in the model); part(a, b, zf, name) adds it.
    Returns the names lumped."""
    done = []
    for e in bd_circuit.elems:
        if not (e.pa and e.pb):
            continue
        try:
            a, b = mesh_pad(e.pa), mesh_pad(e.pb)
        except (KeyError, ValueError):
            continue
        part(a, b, e.z, e.name)
        done.append(e.name)
    return done


def lump_all(bd, mesh_pad, part, internal):
    """The whole circuit inside a copper model: every element a lumped part between the terminals of
    its pads, or internal nodes (an IC's die) where it has none. bd: kae.excite.models.Board;
    mesh_pad(token) the pad's terminal (raises if not meshed); part(a, b, zf, name) adds a part;
    internal(name) makes an internal node. Returns (term, skipped): term(node, pad) maps a circuit
    endpoint to its terminal (for sources and observers), skipped the elements with a pad outside."""
    nets = set(bd.net_of.values())
    gpad = {}

    def term(node, pad):
        if pad:
            return mesh_pad(pad)
        if node in nets:
            # a board net reached without a pad (an IC with no ground pin references the board's
            # ground): the net's first meshed pad
            if node not in gpad:
                gpad[node] = next((mesh_pad(q) for q in bd.pads_of.get(node, []) if _meshed(mesh_pad, q)), None)
            if gpad[node] is None:
                raise KeyError(node)
            return gpad[node]
        return internal(f"node:{node}")
    skipped = []
    for e in bd.circuit.elems:
        try:
            a, b = term(e.a, e.pa), term(e.b, e.pb)
        except (KeyError, ValueError):
            skipped.append(e.name)
            continue
        if a != b:
            part(a, b, e.z, e.name)
    return term, skipped


def _meshed(mesh_pad, q):
    try:
        mesh_pad(q)
        return True
    except (KeyError, ValueError):
        return False


def port(term, a, b, pa=None, pb=None):
    """{terminal: A} of a unit port between circuit nodes a and b: 1 A into b, out of a (the convention
    of Circuit.solve's sources, and of observers' adjoint ports)."""
    out = {}
    for t, v in ((term(b, pb), 1.0), (term(a, pa), -1.0)):
        out[t] = out.get(t, 0.0) + v
    return out


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

    def _Y(self, w, elems=None):
        elems = self.elems if elems is None else elems
        n = len(self.nodes)
        ia = np.array([self.nodes[e.a] for e in elems])
        ib = np.array([self.nodes[e.b] for e in elems])
        y = np.array([1.0 / max_abs(e.z(w)) for e in elems], complex)
        rows = np.concatenate([ia, ib, ia, ib, np.arange(n)])
        cols = np.concatenate([ia, ib, ib, ia, np.arange(n)])
        vals = np.concatenate([y, y, -y, -y, np.full(n, G_LEAK)])
        Y = sp.csc_matrix((vals, (rows, cols)), shape=(n, n))
        keep = np.arange(1, n)                         # node 0 (ground) is the reference
        return Y[keep][:, keep].tocsc(), ia, ib, y

    def solve(self, f, sources=None, skip=()):
        """{source name: dict(V={node: V}, J={pad: A}, I={elem name: A})} at frequency f (Hz), each source
        driving 1 A. skip: element kinds left out (the layout's own parasitics, for an ideal-copper
        reference)."""
        w = 2 * np.pi * f
        elems = [e for e in self.elems if e.kind not in skip] if skip else self.elems
        Y, ia, ib, y = self._Y(w, elems)
        lu = sla.splu(Y)
        out = {}
        names = list(self.nodes)
        for s in (sources or self.sources):
            rhs = np.zeros(len(self.nodes), complex)
            rhs[self.nodes[s.b]] += 1.0
            rhs[self.nodes[s.a]] -= 1.0
            V = np.r_[0.0, lu.solve(rhs[1:])]
            Ie = (V[ia] - V[ib]) * y                     # a -> b through each element
            J, Ja = {}, {}
            for e, i in zip(elems, Ie):
                two = bool(e.pa and e.pb)
                for pad, v in ((e.pa, -i), (e.pb, i)):    # leaves the copper at a into the part, back at b
                    if pad:
                        J[pad] = J.get(pad, 0) + v
                        if not two:
                            Ja[pad] = Ja.get(pad, 0) + v
            for pad, v in ((s.pa, -1.0), (s.pb, 1.0)):
                if pad:
                    J[pad] = J.get(pad, 0) + v
                    Ja[pad] = Ja.get(pad, 0) + v
            # J: every pad (ideal copper); Ja: only the pads of parts that stay outside the copper model
            # (ICs, connectors, the source): the injection when two-pad parts are lumped into the copper
            out[s.name] = dict(V=dict(zip(names, V)), J=J, Ja=Ja, I={e.name: i for e, i in zip(elems, Ie)})
        return out


def max_abs(z, floor=1e-6):
    """An impedance kept away from zero (an ideal short becomes 1 micro-ohm)."""
    return z if abs(z) > floor else floor
