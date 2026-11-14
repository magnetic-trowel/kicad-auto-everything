# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hot loops in kae.excite.evaluate and kae.intent: an open cell is priced at its caps, never left out."""
from functools import lru_cache

import pytest

from hotloop_fixtures import plane_fills, write_hotloop_board
from kae.excite.evaluate import evaluate
from kae.intent import objective as OB

CELL = "cell:cell:buck:U1"
TERMS = {"terms": [{"id": "P3", "tier": "cost", "obs": "loss.loop", "rate": "1 mW_eq/mW", "why": "loop"},
                   {"id": "P4", "tier": "cost", "obs": "loss.loop_ac", "rate": "1 mW_eq/mW", "why": "loop ac"},
                   {"id": "O0", "tier": "hard", "obs": "overshoot.peak", "max": "60 V", "why": "rating"},
                   {"id": "S0", "tier": "cost", "obs": "supply.peak", "rate": "1 mW_eq/mV", "why": "ripple"}]}


@lru_cache(maxsize=None)
def _ev(variant, tmp, **kw):
    p = write_hotloop_board(f"{tmp}/{variant}", variant)
    return evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, **kw)


@pytest.fixture(scope="module")
def tmp(tmp_path_factory):
    return str(tmp_path_factory.mktemp("hotloop"))


def _obs(ev, id_):
    return [o for o in ev["observations"] if o["id"] == id_ and o["scope"].get("source") == CELL]


def test_an_open_hot_loop_is_observed_at_its_caps_and_priced(tmp):
    ev = _ev("open", tmp)
    assert [c["source"] for c in ev["open_cells"]] == [CELL]
    assert CELL in ev["total"]["not_computed"]                   # its other harms are still not computed
    for id_ in ("overshoot.peak", "loss.loop", "loss.loop_ac"):
        (ob,) = _obs(ev, id_)
        assert ob["open"].startswith("hot loop open")
        assert len(ob["values"]) == len(ob["u"]) and min(ob["values"]) > 0
    st = OB.evaluate(ev, TERMS)
    rows = {r["id"]: r for r in st["terms"]}
    for t in ("P3", "P4", "O0"):                                 # priced, not reported as incomplete
        assert not rows[t].get("incomplete") and rows[t]["open_cells"] == [CELL]
    assert rows["S0"].get("incomplete")                          # supply noise from it: still not computed
    assert st["open_cells"][0]["source"] == CELL and st["open_cells"][0]["priced"] == ["O0", "P3", "P4"]
    # it rings to the switch's absolute maximum: above any corner of the closed loop
    assert max(_obs(ev, "overshoot.peak")[0]["values"]) > max(_obs(_ev("closed", tmp), "overshoot.peak")[0]["values"])


def test_an_open_cell_costs_more_than_any_closed_layout_of_it(tmp):
    keys = {v: OB.key(OB.evaluate(_ev(v, tmp), {"terms": TERMS["terms"][:3]})) for v in ("closed", "long", "open")}
    assert keys["closed"] < keys["long"] < keys["open"]


def test_a_closed_cell_keeps_its_loop_observations(tmp):
    ev = _ev("closed", tmp)
    assert ev["open_cells"] == []
    for id_ in ("overshoot.peak", "loss.loop", "loss.loop_ac"):
        (ob,) = _obs(ev, id_)
        assert not ob.get("open")
