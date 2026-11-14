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
def _ev(variant, tmp):
    """One evaluation per variant, its cells' windows at 0.125 mm (the test's speed; the default is finer)."""
    p = write_hotloop_board(f"{tmp}/{variant}", variant)
    return evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cell_pitch=0.125)


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


# ------------------------------------------------------------------------- per-cell window solves (E2)
def _cell(ev):
    (c,) = [c for c in ev["cells"] if c["source"] == CELL]
    return c


def test_every_cell_gets_its_primaries_or_its_state(tmp):
    c = _cell(_ev("closed", tmp))
    assert c["state"] == "ok" and c["L_loop_nH"] > 0 and c["R_loop_mohm"] > 0
    assert [h["n"] for h in c["R_harmonics"]] == [1, 3, 5]
    assert c["R_harmonics"][2]["R_mohm"] > c["R_harmonics"][0]["R_mohm"]       # skin and proximity crowding
    assert 0 < c["overshoot_V"]["typ"] <= c["overshoot_V"]["worst"]
    assert c["window"]["pitch"] == 0.125 and c["window"]["dropped_injection"] < 0.05
    assert _cell(_ev("open", tmp))["state"] == "open"
    st = OB.evaluate(_ev("closed", tmp), TERMS)
    assert st["cells"][0]["L_loop_nH"] == c["L_loop_nH"]


def test_the_window_ranks_layouts_as_the_board_solve_does(tmp):
    a, b = _cell(_ev("closed", tmp)), _cell(_ev("long", tmp))
    assert b["L_loop_nH"] > a["L_loop_nH"] and b["global"]["L_loop_nH"] > a["global"]["L_loop_nH"]
    assert b["R_loop_mohm"] > a["R_loop_mohm"] and b["global"]["R_loop_mohm"] > a["global"]["R_loop_mohm"]
    assert b["overshoot_V"]["worst"] > a["overshoot_V"]["worst"]
    for c in (a, b):                                    # the finer pitch reads lower, a few percent (E7)
        assert 0.8 < c["L_loop_nH"] / c["global"]["L_loop_nH"] < 1.05


def test_the_window_over_the_whole_board_at_its_pitch_is_the_board_solve(tmp, monkeypatch):
    from kae.excite import hotloop as HL
    monkeypatch.setattr(HL, "MARGIN_MM", 100.0)
    p = write_hotloop_board(f"{tmp}/whole", "closed")
    ev = evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cell_pitch=0.25,
                  cell_skin=False)
    c = _cell(ev)
    assert c["L_loop_nH"] == pytest.approx(c["global"]["L_loop_nH"], rel=5e-3)
    assert c["R_loop_mohm"] == pytest.approx(c["global"]["R_loop_mohm"], rel=5e-3)


def test_the_cells_do_not_depend_on_the_files_item_order(tmp):
    a = _cell(_ev("long", tmp))
    p = write_hotloop_board(f"{tmp}/long-rev", "long", reverse=True)
    b = _cell(evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cell_pitch=0.125))
    for k in ("L_loop_nH", "R_loop_mohm", "R_harmonics", "overshoot_V", "global"):
        assert a[k] == b[k]


_PROBE = r"""
import sys, json
sys.path.insert(0, sys.argv[2])
from hotloop_fixtures import plane_fills, write_hotloop_board
from kae.excite.evaluate import evaluate
p = write_hotloop_board(sys.argv[1], "long")
ev = evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cell_pitch=0.125)
c = ev["cells"][0]
print(json.dumps({k: c[k] for k in ("L_loop_nH", "R_loop_mohm", "R_harmonics", "overshoot_V", "global")}, default=float))
"""


def test_the_cells_are_identical_at_any_thread_count(tmp):
    import os
    import subprocess
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    outs = []
    for n in (1, 4):
        env = dict(os.environ, KAE_EM_THREADS=str(n), OMP_NUM_THREADS=str(n), OPENBLAS_NUM_THREADS=str(n),
                   MKL_NUM_THREADS=str(n), PYTHONHASHSEED=str(n))
        env.pop("KAE_EM_BLAS_THREADS", None)
        env["PYTHONPATH"] = os.pathsep.join([os.path.join(here, "..", "src")] + [p for p in [env.get("PYTHONPATH")] if p])
        r = subprocess.run([sys.executable, "-W", "ignore", "-c", _PROBE, f"{tmp}/thr{n}", here], env=env,
                           capture_output=True, text=True, timeout=900)
        assert r.returncode == 0, r.stderr[-2000:]
        outs.append(r.stdout.strip().splitlines()[-1])
    assert outs[0] == outs[1]
