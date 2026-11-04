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


def match_rank(pattern, text, value=None):
    """How well a part-table or datasheet-library pattern names a part: None when it does not match, else a
    sortable key (it matched the value itself, the length of the match). A match must start at a word
    boundary ('CM5' names a Compute Module 5, not the 'PCM5102' it sits inside), and the longest match is the
    most specific ('AP2112K-1.8' beats a family-wide 'AP2112' that a 3.3 V variant's entry carries)."""
    pat = re.sub(r"^\(\?i\)", "", pattern or "")
    if not pat:
        return None
    try:
        rx = re.compile(r"(?<![A-Za-z0-9])(?:" + pat + ")", re.I)
    except re.error:
        return None
    for on_value, t in ((True, value), (False, text)):
        m = rx.search(t or "") if t is not None else None
        if m:
            return (on_value, len(m.group(0)))
    return None


def best_match(entries, pattern_of, text, value=None, name_of=None):
    """The entry whose pattern names the part best, or None: an entry whose own part number is the value
    first (name_of), then match_rank; ties go to the earlier entry."""
    norm = lambda x: re.sub(r"[^a-z0-9]", "", (x or "").lower())
    best, key = None, None
    for e in entries:
        k = match_rank(pattern_of(e), text, value)
        if k is not None:
            k = (bool(value) and name_of is not None and norm(name_of(e)) == norm(value),) + k
        if k is not None and (key is None or k > key):
            best, key = e, k
    return best


def lookup(text):
    """{name: (typ, lo, hi, source text)} for the table entry whose regex names the part text best
    (match_rank: from a word boundary, the most specific)."""
    e = best_match(parts_table(), lambda e: e["match"], text)
    if e is None:
        return {}
    out = {}
    for k, v in e.get("data", {}).items():
        if isinstance(v, list):
            lo, hi = float(v[0]), float(v[-1])
            out[k] = (math.sqrt(lo * hi) if lo > 0 else (lo + hi) / 2, lo, hi, e.get("source", ""))
        else:
            out[k] = (float(v), float(v), float(v), e.get("source", ""))
    return out


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
