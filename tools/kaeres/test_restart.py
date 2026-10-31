# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""restart.py: the placement legality gate and the successive-halving wave plan (stdlib only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import restart  # noqa: E402


def _v(t, *descs):
    return dict(type=t, severity="error", items=[dict(description=d) for d in descs])


def test_overlaps_are_part_pairs():
    rep = dict(violations=[
        _v("shorting_items", "PTH pad 2 [TXO] of JP8", "PTH pad 7 [D3] of JP1"),
        _v("shorting_items", "Pad 1 [/A/B] of R503 on F.Cu", "Pad 9 [X] of U404 on F.Cu"),
        _v("shorting_items", "Track [VCC] on F.Cu, length 2 mm", "Pad 1 [GND] of C1 on F.Cu"),  # the router's
        _v("courtyards_overlap", "Footprint J6", "Footprint A1"),
        _v("courtyards_overlap", "Footprint J6", "Footprint J6"),
        _v("clearance", "Pad 1 [A] of R1 on F.Cu", "Pad 2 [B] of R2 on F.Cu"),
    ])
    assert restart.overlaps(rep) == [("A1", "J6"), ("JP1", "JP8"), ("R503", "U404")]


def test_judge_overlaps_beyond_the_input_are_illegal(monkeypatch, tmp_path):
    d = dict(types={"shorting_items": 4}, unconnected=3, overlaps=[["JP1", "JP8"], ["A1", "J6"]])
    monkeypatch.setattr(restart, "drc", lambda *a: d)
    monkeypatch.setattr(restart, "outside", lambda b: 0)
    b = tmp_path / "b.kicad_pcb"
    assert restart.judge(b, b, {}, 10, placement=True, base_pairs=[("A1", "J6")]) == (1, 1, 3, 4, 1)
    assert restart.judge(b, b, {}, 10, placement=True, base_pairs=[("A1", "J6"), ("JP1", "JP8")]) == (0, 1, 3, 4, 0)
    assert restart.judge(b, b, {}, 10, placement=False) == (0, 1, 3, 4, 0)    # routers: no gate


def test_rung_plan_is_sized_from_the_budget():
    budgets, n0 = restart.rung_plan(795, 4, 150)
    assert budgets == [150, 300, 600] and n0 == 7
    assert restart.rung_plan(725, 4, 304) == ([304, 608], 4)     # never a single rung
    assert restart.rung_plan(100, 4, 150) == ([150, 300], 4)


def test_halving_promotes_the_top_half_then_resumes_the_best():
    h = restart.Halving([100, 200], n0=4)
    cands, k = [], 0
    for _ in range(4):                       # rung 0: four fresh placements
        c, r, b, src = h.next()
        assert c is None and r == 0 and b == 100 and src is None
        cands.append(h.started(c, k, 1000 + k)); k += 1
    for c, opens in zip(cands, (9, 3, 7, 5)):
        h.judged(c, c["rungs"][0]["k"], (0, 1, opens, 0, 0))
    got = []
    for _ in range(2):                       # the two best go up a rung, the best first
        c, r, b, src = h.next()
        got.append((c["id"], r, b, src)); h.started(c, k, 1000 + k); k += 1
    assert got == [(1, 1, 200, 1), (3, 1, 200, 3)]     # each resumes its own rung-0 board
    c, r, b, src = h.next(left=1000)         # nothing to promote, time to climb: a new placement
    assert (c, r, src) == (None, 0, None)
    c, r, b, src = h.next(left=250)          # no time for a new one to climb:
    assert (c["id"], r, src) == (1, 1, 1)    # the best judged board, at the top rung
    s = h.summary()
    assert [len(x["rungs"]) for x in s["candidates"]] == [1, 2, 1, 2] and s["budgets"] == [100, 200]
