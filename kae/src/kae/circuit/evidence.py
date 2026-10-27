# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The evidence model: every role and structure is a sum of cited facts.

An `Evidence` item names one fact the board file states (a name, a value, a footprint, a
pin function or type, a field, a net class, or a topology fact such as "three capacitors
from this net to GND") and a weight in natural-log odds. Positive weights support the
claim, negative ones count against it. Weights add, as for independent likelihood ratios,
and the confidence is the logistic of prior + sum, clipped to [0.02, 0.98]: names and
values never make a claim certain.

Weight scale (log odds, so e^w is the likelihood ratio the fact is worth):
  STRONG 3.0 (~20:1)   e.g. a pin named SW on the inductor's net
  MODERATE 1.5 (~4.5:1) e.g. a net name matching a rail pattern
  WEAK 0.7 (~2:1)      e.g. a reference-designator prefix
The weights are hand-set priors, not fitted; the measured calibration of the resulting
confidences is in docs/topics/physics/comprehension.md.

Multi-class decisions (a part's kind) use `softmax_pick` over per-class scores with an
explicit "unknown" class, so a part whose evidence is thin stays unknown.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

STRONG = 3.0
MODERATE = 1.5
WEAK = 0.7

KINDS = ('name', 'value', 'footprint', 'lib_id', 'pinfunction', 'pintype', 'field', 'netclass',
         'refdes', 'topology', 'count', 'sheet', 'zone', 'attr', 'table', 'derived')

C_MIN, C_MAX = 0.02, 0.98


@dataclass(frozen=True)
class Evidence:
    kind: str       # one of KINDS: which board-file fact this is
    fact: str       # the fact, as text a reviewer can check against the board
    weight: float   # natural-log odds contribution

    def to_json(self) -> dict:
        return {'kind': self.kind, 'fact': self.fact, 'weight': round(self.weight, 2)}


def ev(kind: str, fact: str, weight: float) -> Evidence:
    assert kind in KINDS, kind
    return Evidence(kind, fact, float(weight))


def logistic(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def confidence(evidence, prior: float = 0.0) -> float:
    """Logistic of prior + sum of weights, clipped to [C_MIN, C_MAX]."""
    s = prior + sum(e.weight for e in evidence)
    return min(C_MAX, max(C_MIN, logistic(s)))


def softmax_pick(scores: dict, unknown: float = 1.0) -> tuple[str, float]:
    """The best class and its probability under a softmax that includes an 'unknown' class.

    `scores` maps class -> log-odds score; 'unknown' scores `unknown`. Returns ('unknown', p)
    when nothing beats it."""
    items = dict(scores)
    items.setdefault('unknown', unknown)
    mx = max(items.values())
    z = {k: math.exp(v - mx) for k, v in items.items()}
    tot = sum(z.values())
    best = max(items, key=lambda k: (items[k], k != 'unknown'))
    return best, min(C_MAX, max(C_MIN, z[best] / tot))


def evidence_json(evidence, limit: int = 12) -> list:
    """Strongest facts first (by |weight|), at most `limit`."""
    evs = sorted(evidence, key=lambda e: -abs(e.weight))[:limit]
    return [e.to_json() for e in evs]
