# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.swaps: pair swaps of interchangeable parts lower the term and keep legality."""
from types import SimpleNamespace as NS

import numpy as np

from kae.place.swaps import groups, polish


class Terms:
    """Term = sum over parts of (x - target)^2: each part wants its target x."""

    def __init__(self, targets):
        self.t = targets

    def total(self, poses):
        return sum((poses[u][0] - self.t.get(u, poses[u][0])) ** 2 for u in poses)

    def delta(self, poses, moved, new):
        return sum((new[u][0] - self.t.get(u, new[u][0])) ** 2 - (poses[u][0] - self.t.get(u, poses[u][0])) ** 2 for u in moved)


class State:
    def __init__(self, xs):
        self.X = np.array(xs, float)
        self.Y = np.zeros(len(xs))
        self.K = np.zeros(len(xs), int)

    def pose(self, i):
        return (float(self.X[i]), 0.0, 0.0, "F")

    def hpwl(self):
        return float(self.X.sum())


def problem(n, value="10u", shape="s"):
    parts = [NS(i=i, uuid=f"C{i}", side="F", shape_key=shape, fp=NS(value=value, pads=[1, 2])) for i in range(n)]
    return NS(parts=parts, mov=list(range(n)))


def test_swaps_the_two_parts_that_trade_places():
    P = problem(2)
    st = State([0.0, 10.0])
    rep = polish(P, st, Terms({"C0": 10.0, "C1": 0.0}), time_s=5.0)
    assert rep["swaps"] == 1 and rep["after"] < rep["before"]
    assert list(st.X) == [10.0, 0.0]


def test_no_swap_when_it_does_not_help():
    P = problem(2)
    st = State([0.0, 10.0])
    rep = polish(P, st, Terms({"C0": 0.0, "C1": 10.0}), time_s=5.0)
    assert rep["swaps"] == 0 and list(st.X) == [0.0, 10.0]


def test_groups_need_same_value_and_shape():
    P = problem(3)
    P.parts[2].fp.value = "100n"
    P.parts[2].shape_key = "other"
    assert groups(P) == [[0, 1]]


def test_undone_when_the_exact_check_gets_worse():
    P = problem(2)
    st = State([0.0, 10.0])
    calls = iter([[], [1]])  # before: 0 violations; after: 1
    rep = polish(P, st, Terms({"C0": 10.0, "C1": 0.0}), time_s=5.0, check=lambda: next(calls))
    assert rep.get("undone") and list(st.X) == [0.0, 10.0]
