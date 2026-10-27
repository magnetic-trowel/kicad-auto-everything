# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for anytime.py (no KiCad needed): which states get written, and early stop.

    pytest tools/research/pnr/test_anytime.py
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("shapely")  # test_world's helpers

import anytime  # noqa: E402
from router import Router  # noqa: E402
from test_world import board, footprint, pad, rect  # noqa: E402
from world import World  # noqa: E402


def two_parts():
    sq = rect(-0.3, -0.3, 0.3, 0.3)
    fps = [footprint("A", [pad("N", sq)], x=2.0, y=2.0), footprint("B", [pad("N", sq)], x=6.0, y=2.0)]
    w = World(board(rect(0, 0, 10, 5), fps, ["N"]), g=0.1)
    w.place(0, *w.cell(2.0, 2.0), 0)
    w.place(1, *w.cell(6.0, 2.0), 0)
    return w


class FakeWriter:
    def __init__(self):
        self.boards = []

    def __call__(self, payload, final=False):
        return payload

    def commit(self, tmp):
        self.boards.append(tmp)

    def discard(self, tmp):
        pass


def test_problem_finds_stale_copper():
    w = two_parts()
    r = Router(w)
    assert anytime.problem(w, r) is not None  # nothing routed, nothing counted open
    r.pathfinder(iters=5)
    assert anytime.problem(w, r) is None
    w.place(1, *w.cell(6.0, 4.0), 0)  # moved without a re-route: the copper misses its pad
    assert "stale" in anytime.problem(w, r)


def test_offer_writes_and_stops():
    try:
        w = two_parts()
        anytime.install(w, FakeWriter(), 100.0, lambda m: None)
        with pytest.raises(anytime.Routed):
            Router(w).pathfinder(iters=5)  # Router.legalize offers the state: complete, so stop

        w = two_parts()
        wr = FakeWriter()
        at = anytime.install(w, wr, 100.0, lambda m: None, stop_when_routed=False)
        r = Router(w)
        r.pathfinder(iters=5)
        r.pathfinder(iters=5)  # as good, within every_s: not written again
        th = at.thread
        if th is not None:
            th.join()  # the checkpoint is committed (close() would discard one in flight)
        at.close()
        assert at.best[0] == 0 and len(wr.boards) == 1 and wr.boards[0]["tracks"]
    finally:
        anytime._A = None
