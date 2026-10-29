# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The assumption ledger: every circuit parameter the physics uses, as an interval with its source.

No parameter is a bare number. Each is a Param (typical value, low, high, unit) with the source it
came from, in order of trust:

    intent      the commanding program's intent file (a datasheet it read, a design target, a
                measurement); points or intervals as it states them
    board       the board's own fields (part values, net names)
    part_table  a curated table of part data in this package (parts.json), each entry citing its
                document
    physics     derived from other parameters by a stated law (e.g. a voltage edge from the switch
                node's capacitance and the current that charges it)
    prior       a class default, always as a wide interval, flagged

Results are computed across the intervals (`corners`): seeded Latin-hypercube samples plus the
extremes, so a decision that holds only at one assumed value shows up as one that flips.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

SOURCES = ("intent", "board", "part_table", "physics", "prior")
PARTS_FILE = Path(__file__).with_name("parts.json")


@dataclass
class Param:
    subject: str          # what it describes (a part ref, a cell id, a net)
    name: str             # e.g. f_sw_Hz, t_i_s, I_A
    typ: float
    lo: float
    hi: float
    unit: str
    source: str
    basis: str

    def __post_init__(self):
        self.lo, self.hi = min(self.lo, self.hi), max(self.lo, self.hi)
        self.typ = min(max(self.typ, self.lo), self.hi)

    @property
    def spread(self):
        """hi / lo (1 for a point)."""
        return self.hi / self.lo if self.lo > 0 else float("inf")


@dataclass
class Ledger:
    params: dict = field(default_factory=dict)      # (subject, name) -> Param

    def add(self, p: Param):
        self.params[(p.subject, p.name)] = p
        return p

    def get(self, subject, name):
        return self.params.get((subject, name))

    def rows(self):
        return [asdict(p) for p in self.params.values()]

    def flagged(self):
        """Parameters resting on a prior: what the commander could supply."""
        return [p for p in self.params.values() if p.source == "prior"]


def load_intent(path):
    """The intent file (JSON): {"parts": {ref: {name: value | [lo, hi]}}, "nets": {net: {...}},
    "cells": {cell id: {...}}, "requirements": {...}}. Missing file: empty intent."""
    if not path:
        return {}
    return json.loads(Path(path).read_text())


def parts_table():
    """The curated part table: list of {match (regex), data {name: value | [lo, hi]}, source}."""
    if not PARTS_FILE.exists():
        return []
    return json.loads(PARTS_FILE.read_text()).get("parts", [])


def lookup(text):
    """{name: (typ, lo, hi, source text)} for the first table entry whose regex matches the part text."""
    for e in parts_table():
        if re.search(e["match"], text or "", re.I):
            out = {}
            for k, v in e.get("data", {}).items():
                if isinstance(v, list):
                    lo, hi = float(v[0]), float(v[-1])
                    out[k] = (math.sqrt(lo * hi) if lo > 0 else (lo + hi) / 2, lo, hi, e.get("source", ""))
                else:
                    out[k] = (float(v), float(v), float(v), e.get("source", ""))
            return out
    return {}


def intent_value(intent, section, key, name):
    """(typ, lo, hi) from the intent file, or None."""
    v = ((intent or {}).get(section) or {}).get(key, {}).get(name)
    if v is None:
        return None
    if isinstance(v, list):
        lo, hi = float(v[0]), float(v[-1])
        return (math.sqrt(lo * hi) if lo > 0 else (lo + hi) / 2, lo, hi)
    return (float(v), float(v), float(v))


def corners(params, n=16, seed=0):
    """Sample points over the parameters' intervals: n seeded Latin-hypercube samples (log-uniform
    where lo > 0) plus the all-low and all-high corners and the typical point. Returns a list of
    {(subject, name): value}; the first entry is the typical point."""
    ps = list(params)
    rng = np.random.default_rng(seed)
    pts = [{(p.subject, p.name): p.typ for p in ps}]
    if not ps:
        return pts
    k = len(ps)
    u = (rng.permuted(np.tile(np.arange(n), (k, 1)), axis=1).T + rng.random((n, k))) / n
    for row in u:
        d = {}
        for p, x in zip(ps, row):
            if p.lo > 0 and p.hi > p.lo:
                d[(p.subject, p.name)] = math.exp(math.log(p.lo) + x * (math.log(p.hi) - math.log(p.lo)))
            else:
                d[(p.subject, p.name)] = p.lo + x * (p.hi - p.lo)
        pts.append(d)
    pts.append({(p.subject, p.name): p.lo for p in ps})
    pts.append({(p.subject, p.name): p.hi for p in ps})
    return pts
