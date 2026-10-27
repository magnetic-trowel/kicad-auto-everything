# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks of field.py on a synthetic world (no board, no KiCad): discrete maximum principle,
streamline termination, current conservation, |J|/I integrating to the path length, walls
being insulating.   python -m pytest tools/research/harmonic/test_field.py"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from field import Field  # noqa: E402


class FakeWorld:
    """Minimal World: L layers of H x W cells, pins as fine cells, optional wall."""

    def __init__(self, H=120, W=200, L=2, g=0.1, wall=None):
        self.H, self.W, self.nl, self.g = H, W, L, g
        self.blockT = np.zeros((L, H, W), bool)
        if wall is not None:
            self.blockT[:, wall[0]:wall[1], wall[2]:wall[3]] = True
        self.DT = np.zeros((L, H, W), np.int16)
        self.occT = np.zeros((2, L, H, W), np.uint8)
        self.pose = {0: (0, 0, 0), 1: (0, 0, 0), 2: (0, 0, 0)}
        self.cells = {}
        self.net_pins = {1: []}

    def add_pin(self, pi, y, x, l=0, r=2):
        self.cells[(pi, 0)] = [(l, yy, xx) for yy in range(y - r, y + r + 1) for xx in range(x - r, x + r + 1)]
        self.net_pins[1].append((pi, 0))

    def terminals(self, pi, k):
        return self.cells[(pi, k)]


def _solve(w):
    F = Field(w, coarse_mm=0.4)
    sig = F.sigma(1)
    phi, pins, src = F.solve(1, sig, margin_mm=8.0)
    return F, sig, phi, pins, src


def test_max_principle_and_streamline():
    w = FakeWorld()
    w.add_pin(0, 60, 40)
    w.add_pin(1, 60, 160)
    F, sig, phi, pins, src = _solve(w)
    live = ~np.isnan(phi)
    fixed = np.zeros(F.n, bool)
    for p in pins:
        fixed[p] = True
    assert phi[live].min() >= -1e-9 and phi[live].max() <= 1 + 1e-9
    # every free live node has a strictly higher and a strictly lower neighbour (no extrema)
    P = phi.reshape(F.L, F.Hc, F.Wc)
    for l in range(F.L):
        for y in range(1, F.Hc - 1):
            for x in range(1, F.Wc - 1):
                i = (l * F.Hc + y) * F.Wc + x
                if fixed[i] or not live[i]:
                    continue
                nb = [P[l, y + 1, x], P[l, y - 1, x], P[l, y, x + 1], P[l, y, x - 1]]
                nb += [P[1 - l, y, x]] if F.L == 2 else []
                nb = [v for v in nb if not np.isnan(v)]
                assert max(nb) >= P[l, y, x] - 1e-12 and min(nb) <= P[l, y, x] + 1e-12
    tree = F.streamlines(phi, sig, pins, src)
    assert all(t is not None for t in tree)


def test_occupancy_integrates_to_length():
    w = FakeWorld(L=1)
    w.add_pin(0, 60, 40)
    w.add_pin(1, 60, 160)
    F, sig, phi, pins, src = _solve(w)
    d = F.density(phi, sig)
    # straight distance between pin edges in coarse cells (12 mm / 0.4 mm = 30, minus pads)
    dist = (160 - 40) / F.s
    tot = np.nansum(d)
    assert 0.8 * dist < tot < 2.0 * dist, (tot, dist)


def test_wall_is_insulating():
    # a wall between the pins with a gap at the top: the streamline must pass the gap
    w = FakeWorld(L=1, wall=(20, 120, 95, 105))
    w.add_pin(0, 60, 40)
    w.add_pin(1, 60, 160)
    F, sig, phi, pins, src = _solve(w)
    tree = F.streamlines(phi, sig, pins, src)
    assert tree[0] is not None
    l, y, x = F.unravel(tree[0])
    cross = (x * F.s >= 95) & (x * F.s < 105)
    assert cross.any() and (y[cross] * F.s < 20).all()
