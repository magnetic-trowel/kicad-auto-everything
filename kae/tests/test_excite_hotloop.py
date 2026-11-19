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


def test_a_window_over_its_budget_keeps_the_board_values(tmp, monkeypatch):
    from kae.excite import hotloop as HL
    monkeypatch.setattr(HL, "MAX_CELLS", 1000)
    p = write_hotloop_board(f"{tmp}/budget", "closed")
    c = _cell(evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False))
    assert c["state"] == "ok" and c["window"]["refined"] is False
    assert c["L_loop_nH"] == c["global"]["L_loop_nH"] and c["R_loop_mohm"] == c["global"]["R_loop_mohm"]
    assert HL.summary([c])[0].count("board values") == 1


def _misplaced_window(monkeypatch, always):
    """Make the cell's first window (or every window, `always`) close the loop on a long path the board does not
    use, 20 nH at the board's pitch and 14 nH at the fine one: the naive two-grid correction then comes out
    negative (nekoink's boost read -0.17 nH this way)."""
    import math
    from kae.excite import hotloop as HL
    real, first = HL._solve_window, []

    def fake(path, b, bd, s, o, win, pitch, *a, **k):
        z, info, m = real(path, b, bd, s, o, win, pitch, *a, **k)
        first.append(first[0] if first else win)
        if z is not None and (always or win == first[0]):
            extra = 20e-9 if pitch == 0.25 else 14e-9
            z = {f: v + 2j * math.pi * f * extra + 0.2 for f, v in z.items()}
        return z, info, m
    monkeypatch.setattr(HL, "_solve_window", fake)


def test_a_window_that_misses_the_loops_path_grows(tmp, monkeypatch):
    _misplaced_window(monkeypatch, always=False)
    p = write_hotloop_board(f"{tmp}/trunc-grow", "closed")
    c = _cell(evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cell_pitch=0.125))
    ref = _cell(_ev("closed", tmp))
    assert c["state"] == "ok" and c["window"]["refined"] and c["window"]["grown"] >= 1
    assert c["L_loop_nH"] > 0 and abs(c["window"]["trunc_L_nH"]) <= 0.5 * c["global"]["L_loop_nH"]
    assert c["L_loop_nH"] == pytest.approx(ref["L_loop_nH"], rel=0.1)


def test_a_window_whose_truncation_stays_large_keeps_the_board_values(tmp, monkeypatch):
    from kae.excite import hotloop as HL
    _misplaced_window(monkeypatch, always=True)
    p = write_hotloop_board(f"{tmp}/trunc-bad", "closed")
    c = _cell(evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cell_pitch=0.125))
    assert c["state"] == "ok" and c["window"]["refined"] is False and "truncation" in c["window"]["why"]
    assert c["L_loop_nH"] == c["global"]["L_loop_nH"] > 0 and c["R_loop_mohm"] == c["global"]["R_loop_mohm"]
    assert HL.summary([c])[0].count("board values") == 1


def _drc(*descs):
    return {"unconnected_items": [{"items": [{"description": d}, {"description": "Zone [GND] on B.Cu"}]} for d in descs]}


def test_a_loop_member_drc_lists_unconnected_makes_the_cell_open(tmp):
    """The copper may still close a loop (through whatever is left); KiCad says a loop pad is unconnected: open."""
    import json
    from kae.excite.evaluate import drc_open_cells
    p = write_hotloop_board(f"{tmp}/drc", "closed")
    (p.parent / "drc.json").write_text(json.dumps(_drc("Pad 4 [GND] of U1 on F.Cu")))   # found beside the board
    ev = evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cells=False)
    assert [c["source"] for c in ev["open_cells"]] == [CELL] and "DRC" in ev["open_cells"][0]["why"]
    assert ev["drc"] == "drc.json" and _obs(ev, "loss.loop")[0]["open"]
    ev = evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cells=False, drc=False)
    assert ev["open_cells"] == []
    from kae.board.kicad_file import load
    from kae.circuit import brief as B
    from kae.excite import models as M, sources as S
    b = load(p)
    br = B.build(b)
    srcs = S.add_all(M.build(b, br), br)
    assert drc_open_cells(_drc("Pad 2 [GND] of U2 on F.Cu"), br, srcs) == {}     # not a loop member
    assert CELL in drc_open_cells(_drc("Pad 1 [VIN] of C1 on F.Cu"), br, srcs)


def _strip(rows):
    out = []
    for r in rows:
        r = dict(r)
        if "window" in r:
            r["window"] = {k: v for k, v in r["window"].items() if k != "seconds"}
        out.append(r)
    return out


def test_scope_losses_gives_the_full_evaluations_values_and_nothing_else(tmp):
    from kae.excite.evaluate import SCOPE_KINDS
    p = write_hotloop_board(f"{tmp}/scope", "long")
    kw = dict(pitch=0.25, fills=plane_fills(), log=lambda *a: None, cell_pitch=0.125)
    full = evaluate(str(p), **kw)
    lp = evaluate(str(p), scope="losses", **kw)
    assert lp["scope"] == "losses" and {o["id"] for o in lp["observations"]} <= set(SCOPE_KINDS)
    assert {o["id"] for o in lp["observations"]} >= {"loss.loop", "loss.loop_ac", "loss.swnode"}
    key = lambda o: (o["id"], o["label"])
    want = sorted(((key(o), o["values"]) for o in full["observations"] if o["id"] in SCOPE_KINDS))
    got = sorted(((key(o), o["values"]) for o in lp["observations"]))
    assert got == want                                          # bit for bit
    assert _strip(lp["cells"]) == _strip(full["cells"])
    st = OB.evaluate(lp, {"terms": TERMS["terms"]})
    rows = {r["id"]: r for r in st["terms"]}
    assert rows["S0"]["incomplete"] and not rows["P3"].get("incomplete")


def test_the_ac_loop_loss_sums_harmonics_and_reduces_to_the_flat_formula():
    import numpy as np
    from kae.excite import hotloop as HL
    flat = lambda f: np.full(np.shape(f), 0.01)
    for D in (0.2, 0.5, 0.74):
        assert HL.ac_loop_loss(2.0, D, 1e6, 0.0, flat) == pytest.approx(4.0 * D * (1 - D) * 0.01, rel=0.01)
    row = {"R_harmonics": [dict(n=1, f_MHz=1.0, R_mohm=10.0), dict(n=3, f_MHz=3.0, R_mohm=14.0),
                           dict(n=5, f_MHz=5.0, R_mohm=18.0)]}
    R = HL.r_of_f(row)
    assert R(np.array([1e6, 3e6, 20e6])) == pytest.approx([0.010, 0.014, 0.018 * 2.0])
    rising = HL.ac_loop_loss(2.0, 0.5, 1e6, 5e-9, R)
    assert rising > HL.ac_loop_loss(2.0, 0.5, 1e6, 5e-9, flat)          # crowding raises it


def test_the_ac_loop_loss_observation_uses_the_windows_harmonics(tmp):
    from kae.excite import hotloop as HL
    ev = _ev("closed", tmp)
    c, (ob,) = _cell(ev), _obs(ev, "loss.loop_ac")
    assert ob["scope"]["R_harmonics_mohm"] == [h["R_mohm"] for h in c["R_harmonics"]]
    assert ob["values"][0] > 0 and "harmonics" in ob["label"]


def test_the_inductor_ripple_copper_loss_matches_a_hand_estimate(tmp):
    """Buck of the fixture: dI = V D (1 - D) / (L f) through SW trace, inductor, output trace, C2, its via, the plane
    and U1's ground via. By hand (0.5 mm tracks at 0.98 mOhm/mm outside the pads, ~5.8 mm; two 0.3 mm barrels
    ~1.05 mOhm each; ~1 mOhm of plane) R ~ 8.8 mOhm, so dI^2 / 12 R."""
    ev = _ev("closed", tmp)
    (ob,) = _obs(ev, "loss.copper_ac")
    R1 = ob["scope"]["R_eff_ohm"][0]
    assert 7e-3 < R1 < 12e-3
    dI = 12.0 * 0.275 * 0.725 / (ob["scope"]["L_H"] * 1.1e6)
    assert ob["values"][0] == pytest.approx(dI ** 2 / 12 * R1, rel=0.03)       # the harmonics add a little
    st = OB.evaluate(ev, {"terms": [{"id": "P1", "tier": "cost", "obs": "loss.copper", "rate": "1 mW_eq/mW", "why": "dc"}]})
    row = next(r for r in st["terms"] if r["id"] == "P1ac")
    assert row["obs"] == "loss.copper_ac" and row["contribution"] > 0             # priced like loss.copper


def test_the_hot_loop_loss_is_charged_at_the_turnoff_current(tmp):
    """The fixture buck's switch turns off at the inductor's peak I + dI/2 (kae.physics.converter.turnoff_current):
    loss.loop = 1/2 L_loop I_pk^2 f_sw at every corner, with dI as the ripple observation reads it."""
    ev = _ev("closed", tmp)
    (lp,) = _obs(ev, "loss.loop")
    (rp,) = _obs(ev, "loss.copper_ac")
    led = {r["name"]: r for r in ev["ledger"] if str(r.get("subject", "")).startswith("cell:")} \
        if isinstance(ev["ledger"], list) else {}
    I, f = led["I_A"]["typ"], led["f_sw_Hz"]["typ"]
    dI = min(12.0 * 0.275 * 0.725 / (rp["scope"]["L_H"] * f), 2 * I)
    assert lp["values"][0] == pytest.approx(0.5 * lp["scope"]["L_loop_H"] * (I + dI / 2) ** 2 * f, rel=1e-6)
    assert "I_pk" in lp["label"]


def test_the_ripple_loss_is_deterministic_across_file_order(tmp):
    a = _obs(_ev("long", tmp), "loss.copper_ac")[0]["values"]
    p = write_hotloop_board(f"{tmp}/long-rev2", "long", reverse=True)
    ev = evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cell_pitch=0.125)
    assert _obs(ev, "loss.copper_ac")[0]["values"] == a


def test_loss_loop_ac_always_carries_skin_effect_per_harmonic(tmp):
    """With a window (cell R) and without one (--no-cells: the board solve at each harmonic, skin-corrected), the
    priced loss.loop_ac is the harmonic sum, never the fundamental-only, skin-free I^2 D (1 - D) R."""
    (win,) = _obs(_ev("closed", tmp), "loss.loop_ac")
    p = write_hotloop_board(f"{tmp}/nocells", "closed")
    ev = evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cells=False)
    (brd,) = _obs(ev, "loss.loop_ac")
    for ob, frm in ((win, "cell window"), (brd, "board solve")):
        assert ob["scope"]["R_from"] == frm and "skin" in ob["label"] and "no skin" not in ob["label"]
        hs = ob["scope"]["R_harmonics_mohm"]
        assert len(hs) == 3 and hs[2] > hs[0]                    # crowding raises R with frequency
    # skin on: the board-solve fallback's R at 5 f_sw exceeds the same solve without the correction
    from kae.excite import evaluate as EV
    from kae.excite import hotloop as HL
    import numpy as np
    orig = HL._skin_R
    try:
        HL._skin_R = lambda net, f, nsub: net.R.copy()
        ev0 = evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cells=False)
    finally:
        HL._skin_R = orig
    (b0,) = _obs(ev0, "loss.loop_ac")
    assert brd["scope"]["R_harmonics_mohm"][2] > b0["scope"]["R_harmonics_mohm"][2]
    assert brd["values"][0] > b0["values"][0]


def test_a_cell_with_discrete_switches_is_never_driven_through_its_controller(tmp):
    """A half bridge's gate driver has its HS pin on the switch node; the brief says the switches are discrete. The
    cell must be excited at its transistors, not at the driver (whose supply pins left it open on every layout)."""
    from kae.board.kicad_file import load
    from kae.circuit import brief as B
    from kae.excite import models as M, sources as S
    p = write_hotloop_board(f"{tmp}/discrete", "closed")
    b = load(p)
    br = B.build(b)
    bd = M.build(b, br)
    st = next(x for x in br["structures"] if x.get("kind") == "commutation_cell")
    uuid = {u: q["ref"] for u, q in br["parts"].items()}
    assert S._cell(bd, st, uuid) is not None                      # integrated: the controller's SW pin
    st = dict(st, integrated_switches=False)
    assert S._cell(bd, st, uuid) is None                          # discrete, and no transistor in this loop


def test_a_loop_loss_beyond_a_tenth_of_the_throughput_is_flagged_and_capped(tmp, monkeypatch):
    from kae.excite import evaluate as EV
    monkeypatch.setattr(EV, "LOOP_LOSS_FRAC", 1e-6)
    p = write_hotloop_board(f"{tmp}/implausible", "closed")
    ev = evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cells=False)
    (ob,) = _obs(ev, "loss.loop_ac")
    assert "throughput" in ob["implausible"] and len(ob["cap_values"]) == len(ob["values"])
    st = OB.evaluate(ev, {"terms": [TERMS["terms"][1]]})
    row = st["terms"][0]
    assert row["contribution"] == pytest.approx(OB._agg([min(v, c) for v, c in zip(ob["values"], ob["cap_values"])],
                                                        "cvar20", None) * 1e3, abs=1e-4)
    assert any(i["id"] == "loss.loop_ac" for i in st["implausible"])


def test_a_loop_closing_only_through_more_than_its_load_impedance_is_open(tmp, monkeypatch):
    """gecko5 U14 under a keep-out read L -19388 nH, R 99 kOhm: the loop closed only through a part, not copper. A
    cell whose copper share exceeds its load V / I is open (priced at its caps), never a reported value. Here the
    load is made tiny (I x 1e7) so the fixture's few-mOhm loop exceeds it."""
    from kae.excite import evaluate as EV
    orig = EV.ledger_for

    def big_I(*a, **k):
        P, L = orig(*a, **k)
        for ps in P.values():
            if "I" in ps:
                ps["I"].typ *= 1e7
        return P, L
    monkeypatch.setattr(EV, "ledger_for", big_I)
    p = write_hotloop_board(f"{tmp}/effopen", "closed")
    ev = evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cells=False)
    assert [c["source"] for c in ev["open_cells"]] == [CELL] and "V / I" in ev["open_cells"][0]["why"]
    assert all(o.get("open") for o in _obs(ev, "loss.loop_ac") + _obs(ev, "overshoot.peak"))


def test_a_cell_quote_outside_physical_bounds_is_invalid_not_a_value():
    from kae.excite.cellquote import compare, unphysical
    assert unphysical(-0.049e-9, 0.028, 5.0, 1.0, 10e6)                 # sstv Kp U5: L <= 0
    assert unphysical(30e-9, 99.0, 5.0, 1.0, 10e6)                      # closes through a part
    assert unphysical(1.0e-9, 0.005, 5.0, 1.0, 10e6) is None
    a = [dict(source="c", state="invalid"), dict(source="d", state="ok", L_nH=1.0, R_mohm=5.0)]
    b = [dict(source="c", state="ok", L_nH=1.0, R_mohm=5.0), dict(source="d", state="ok", L_nH=2.0, R_mohm=5.0)]
    assert compare(a, b)[0] == {"d": -1}                                 # an invalid quote decides nothing


def _fake_bd(pads, kinds, ic_nodes=None):
    from types import SimpleNamespace
    from kae.excite.circuit import Circuit
    pads_of = {}
    for t, n in pads.items():
        pads_of.setdefault(n, []).append(t)
    return SimpleNamespace(circuit=Circuit("GND"), pads_of=pads_of, net_of=dict(pads), part_kind=kinds,
                           ic_nodes=ic_nodes or {}, rails={"VIN": 12.0}, ground="GND", assumptions=[])


def test_a_low_side_fet_above_a_sense_resistor_is_the_cells_switch():
    """MAX1771, LTC3783, LT3754 boosts: the FET's source sits on a current-sense net, not on ground. The cell is
    excited between the FET's drain (switch node) and its source, the loop's own pins."""
    from kae.excite import sources as S
    bd = _fake_bd({"Q1.2": "SW", "Q1.3": "CS", "Q1.1": "GATE", "R1.1": "CS", "R1.2": "GND", "U1.1": "VIN"},
                  {"Q1": ("transistor",), "R1": ("resistor",), "U1": ("ic",)})
    st = {"id": "cell:boost:U1", "class": "boost", "sw": "SW", "rail": "VOUT", "gnd": "GND", "controller": "u1",
          "integrated_switches": False, "loop": [["q1", "2"], ["q1", "3"]]}
    src = S._cell(bd, st, {"q1": "Q1", "u1": "U1"})
    assert src is not None and (src.pa, src.pb) == ("Q1.2", "Q1.3")


def test_an_integrated_high_side_switch_without_a_bus_node_enters_at_the_controllers_bus_pad():
    """pms67's MP2359: the controller's VIN pin had no internal node; the source was driven at the bare net (no pad)
    and the copper saw 1 A with no way out on every layout. It now enters at the controller's own bus pad."""
    from kae.excite import sources as S
    bd = _fake_bd({"U1.5": "VIN", "U1.6": "SW", "U1.2": "GND"}, {"U1": ("ic",)}, {"U1": {"g": "U1:g"}})
    st = {"id": "cell:buck:U1", "class": "buck", "sw": "SW", "rail": "VIN", "gnd": "GND", "controller": "u1",
          "integrated_switches": True, "loop": [["u1", ["5"]], ["u1", ["6"]]]}
    src = S._cell(bd, st, {"u1": "U1"})
    assert src is not None and src.pa == "U1.5" and src.pb == "U1.6"


def test_board_level_copper_shapes_with_a_net_conduct(tmp):
    """KiCad 8+ connects gr_poly copper that carries a net; aravind7s' ADP2384 board drew its VIN, SW and output
    copper that way and read open on every one of those nets."""
    from types import SimpleNamespace
    from shapely.geometry import box
    from kae.board.model import Stackup
    from kae.em.kicad import BoardMesh
    su = Stackup(copper=["F.Cu", "B.Cu"], cu_thickness=[0.035, 0.035], gaps=[1.5], er=[4.5], thickness=1.6,
                 source="assumed")
    b = SimpleNamespace(tracks=[], vias=[], footprints=[], stackup=su, zones=[],
                        copper={"VIN": {"F.Cu": [box(1, 1, 4, 2)]}})
    m = BoardMesh(None, (0, 0, 5, 3), 0.25, b=b, fills={}).m
    assert (m.lab[0] == m.net_id("VIN")).sum() == 12 * 4


def test_a_non_positive_l_loop_is_flagged_never_reported():
    """olimex dcdc: the layout share reads +2.70 nH at 5 MHz, -2.62 at 10 and +1.33 at 30 (a resonance of the input
    capacitors near the edge band). Such a row is invalid, its L moved aside; kae.intent leaves terms on an invalid
    observation incomplete."""
    from kae.excite import hotloop as HL
    r = HL.flag_invalid(dict(source=CELL, state="ok", L_loop_nH=-2.62, R_loop_mohm=4.9, overshoot_V=dict(typ=1, worst=2)))
    assert r["state"] == "invalid" and "L_loop_nH" not in r and r["L_invalid_nH"] == -2.62 and "overshoot_V" not in r
    ev = {"board": "synthetic", "total": {"complete": True}, "questions": [], "observations": [
        dict(id="loss.loop", unit="W", values=[0.0, 0.0], u=[0, 0], scope=dict(source=CELL, kind="loop_loss"),
             reference=dict(value=None), label="loop", invalid="L_loop -2.62 nH"),
        dict(id="loss.copper", unit="W", values=[0.01, 0.01], u=[0, 0], scope=dict(kind="dc_loss"),
             reference=dict(value=None), label="cu")]}
    terms = {"terms": [{"id": "P3", "tier": "cost", "obs": "loss.loop", "rate": "1 mW_eq/mW", "why": "loop"}]}
    row = next(x for x in OB.evaluate(ev, terms, {"parts": {}, "structures": []})["terms"] if x["id"] == "P3")
    assert row["incomplete"] and row["not_computed"] == [f"{CELL}: invalid"]


def test_a_cell_the_circuit_cannot_excite_gets_a_row_saying_why(tmp, monkeypatch):
    from kae.excite import sources as S
    monkeypatch.setattr(S, "_cell", lambda bd, s, uuid: bd.assumptions.append(f"{s['id']}: switch not found; cell "
                                                                             f"not excited"))
    p = write_hotloop_board(f"{tmp}/unexcited", "closed")
    ev = evaluate(str(p), pitch=0.25, fills=plane_fills(), log=lambda *a: None, dc=False, cells=False)
    (c,) = ev["cells"]
    assert c["source"] == CELL and c["state"] == "not_computed" and "switch not found" in c["why"]


def test_r_loop_is_the_coppers_own_dissipation_never_negative(tmp):
    c = _cell(_ev("closed", tmp))
    assert c["R_loop_mohm"] > 0 and all(h["R_mohm"] > 0 for h in c["R_harmonics"])
    assert c["global"]["R_loop_mohm"] > 0
