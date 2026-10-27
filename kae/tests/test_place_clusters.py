# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.clusters: soft cap ownership, protection-order rules and their annealer term."""
from pathlib import Path

import numpy as np

from kae.board.kicad_file import load
from kae.place import clusters
from kae.place.anneal import Annealer
from kae.place.legalize import legalize
from kae.place.problem import Problem
from kae.place.state import State, grid_violations

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def _problem():
    b = load(FIXTURE)
    P = Problem.build(b)
    return P, {p.ref: p for p in P.parts}


def test_caps_bind_only_when_owned_and_crowded_rails_stay_free():
    P, ref = _problem()
    u = {r: p.uuid for r, p in ref.items()}
    brief = {"structures": [
        {"kind": "decap", "ic": u["U1"], "rail": "VCC", "ground": "GND", "power_pins": ["3"],
         "caps": [u["U4"], u["U5"]], "caps_p": {u["U4"]: 0.9, u["U5"]: 0.4}, "function": "load"},
        # a rail of many interchangeable loads: no owner worth binding to
        {"kind": "decap", "ic": u["U3"], "rail": "VCC", "ground": "GND", "power_pins": ["3"],
         "caps": [u["U4"], u["U5"]], "caps_p": {u["U4"]: 0.3, u["U5"]: 0.3}, "shared_by": 3},
        # the load may be any part (here the connector of an entry decap)
        {"kind": "decap", "ic": u["J1"], "rail": "VCC", "ground": "GND", "power_pins": ["1"],
         "caps": [u["U7"]], "caps_p": {u["U7"]: 0.8}, "function": "entry"}]}
    ss = clusters.structures(P, brief)
    members = sorted(sorted(ref_of for ref_of in (P.parts[i].ref for i in s.members)) for s in ss)
    assert members == [["J1", "U7"], ["U1", "U4"]]
    # the segment weight carries the ownership probability
    s1 = next(s for s in ss if ref["U1"].i in s.members)
    assert max(w for _, _, w in s1.segs) <= clusters.KIND_WEIGHT["decap"] * 0.9 + 1e-9


def _order_setup():
    P, ref = _problem()
    u = {r: p.uuid for r, p in ref.items()}
    brief = {"structures": [
        {"kind": "connector_chain", "connector": u["J1"], "pin": "1", "net": "VCC", "protected": True,
         "protection": [u["U7"]], "chain": [[u["J1"], "1"], [u["U7"], "3"], [u["U1"], "3"]]}]}
    rules = clusters.protection_order(P, brief)
    return P, ref, rules


def test_protection_order_rule_from_a_protected_chain():
    P, ref, rules = _order_setup()
    assert len(rules) == 1
    (c, cp), (t, tp), (i, ip) = rules[0]
    assert (P.parts[c].ref, P.parts[t].ref, P.parts[i].ref) == ("J1", "U7", "U1")
    assert [P.parts[t].fp.pads[k].number for k in tp] == ["3"]


def test_annealer_order_term_penalizes_and_stays_exact():
    P, ref, rules = _order_setup()
    st = State(P)
    rng = np.random.default_rng(0)
    for i in P.mov:
        st.X[i] = rng.integers(P.ncx // 4, 3 * P.ncx // 4)
        st.Y[i] = rng.integers(P.ncy // 4, 3 * P.ncy // 4)
    legalize(P, st, time_s=30.0, workers=2, seed=0)
    assert not grid_violations(st)
    J, T, U = ref["J1"].i, ref["U7"].i, ref["U1"].i
    # protected part right at the connector, protection far away: broken rule
    st2 = st.copy()
    st2.X[U], st2.Y[U] = st2.X[J] + 1, st2.Y[J]
    st2.X[T], st2.Y[T] = st2.X[J] + P.ncx // 2, st2.Y[J] + P.ncy // 2
    ann = Annealer(P, st2, terms=None, w_cong=0.0, order=rules)
    assert ann.order_violations() == 1 and ann.order_total > 0
    # the term pulls it right, and the incremental total matches a fresh evaluation
    ann = Annealer(P, st2.copy(), terms=None, w_cong=0.0, order=rules, w_order=50.0, seed=3)
    ann.run(cpu_s=30.0, max_moves=6000)
    ann.write_back()
    fresh = Annealer(P, ann.st.copy(), terms=None, w_cong=0.0, order=rules)
    assert abs(fresh.order_total - ann.order_total) < 1e-9
    assert ann.order_violations() == 0


def test_seed_keeps_macro_layouts_in_millimetres():
    """Regression: layout offsets are grid cells and the layout centre is in mm; the seed
    mixed them, spreading big-board macros 1/g times apart (10x at 0.1 mm)."""
    from kae.place import pipeline, seed as seedmod
    P, ref = _problem()
    a, b = ref["U1"].i, ref["U2"].i
    lay = clusters._layout(P, {a: (0, 0, 0), b: (30, 0, 0)}, 0.0)
    mac = clusters.Macro(members=[a, b], anchor=a, layouts=[lay], structs=[])
    objs, owner = seedmod._objects(P, [mac])
    rel = objs[owner[a]][3]
    assert abs((rel[b][0] - rel[a][0]) - 30 * P.g) < 1e-9
    net_w = {net.i: net.weight for net in P.nets}
    for partition in (False, True):
        st, _ = pipeline._seed_state(P, [mac], net_w, 0, None, partition=partition)
        assert abs(int(st.X[b] - st.X[a]) - 30) <= 1 and abs(int(st.Y[b] - st.Y[a])) <= 1


def _brief_problem(edit=None):
    b = load(FIXTURE)
    if edit:
        edit(b)
    P = Problem.build(b)
    ref = {p.ref: p for p in P.parts}
    return P, ref, {r: p.uuid for r, p in ref.items()}


def _refs(P, s):
    return sorted(P.parts[i].ref for i in s.members)


def test_nearest_load_and_rail_group_decaps_make_no_macro():
    """kae.brief/1: caps paired 'nearest_load' (entry bulk, rail groups) serve whichever
    load they sit next to; the place terms charge them, no macro binds them."""
    P, ref, u = _brief_problem()
    dec = dict(kind="decap", rail="VCC", ground="GND", power_pins=["3"], pin_caps={}, function="load")
    brief = {"structures": [
        dict(dec, ic=u["J1"], power_pins=["1"], caps=[u["U7"]], caps_p={u["U7"]: 0.97}, pairing="nearest_load",
             function="entry"),
        dict(dec, ic=u["U1"], caps=[u["U4"]], caps_p={u["U4"]: 0.9}, pairing="nearest_load", rail_group="rg:VCC"),
        dict(kind="rail_group", id="rg:VCC", rail="VCC", ground="GND", loads=[u["U1"], u["U3"]],
             caps=[u["U4"], u["U5"]], pairing="nearest_load"),
        dict(dec, ic=u["U3"], caps=[u["U5"]], caps_p={u["U5"]: 0.9}, pairing="pin", pin_caps={})]}
    ss = clusters.structures(P, brief)
    assert [_refs(P, s) for s in ss] == [["U3", "U5"]]


def test_nearest_pin_pairing_lets_cpsat_choose_the_pin():
    """kae.brief/1 pairing 'nearest_pin': a cap goes to the nearest of the IC's power-pin
    clusters, not to their centroid (inside the IC); full weight, unlike an unpaired cap."""
    def two_vcc_pins(b):
        next(f for f in b.footprints if f.ref == "U1").pads[0].net = "VCC"
    P, ref, u = _brief_problem(two_vcc_pins)
    s0 = dict(kind="decap", ic=u["U1"], rail="VCC", ground="GND", power_pins=["1", "3"], caps=[u["U4"]],
              caps_p={u["U4"]: 0.9}, pin_caps={}, function="load")
    near = clusters.structures(P, {"structures": [dict(s0, pairing="nearest_pin")]})[0]
    loose = clusters.structures(P, {"structures": [dict(s0, pairing="pin")]})[0]
    assert len(near.choices[0]) == 2
    assert near.segs[0][2] == clusters.KIND_WEIGHT["decap"] * 0.9 > loose.segs[0][2]
    mem = sorted(near.members)
    a = ref["U1"].i
    with_choice = clusters.micro_place(P, mem, [near], a, time_s=2.0, top_k=1, workers=1)[0]
    near.choices = {}
    centroid = clusters.micro_place(P, mem, [near], a, time_s=2.0, top_k=1, workers=1)[0]
    assert with_choice.cost < centroid.cost


def test_power_path_macro_follows_the_loop_and_ties_in_parallel_elements():
    """kae.brief/1 power_path: switches (every stage's parallel elements) plus caps_in and
    caps_out; segments follow the loop between them and a connector closing the loop stays
    out; members off the loop tie in by shared nets, once per net (a star, not all pairs)."""
    P, ref, u = _brief_problem()
    brief = {"structures": [dict(
        kind="power_path", id="path:U1", **{"class": "fet_bank"}, switches=[u["U1"], u["U3"]],
        stages=[[u["U1"], u["U3"]]], controller=None, rail_in="VCC", rail_out="SIG1", gnd="GND",
        caps_in=[u["U4"]], caps_out=[u["U5"]],
        loop=[[u["U4"], "3"], [u["U1"], "3"], [u["U1"], "1"], [u["J1"], "1"], [u["J1"], "2"], [u["U4"], "2"]])]}
    ss = clusters.structures(P, brief)
    assert len(ss) == 1 and ss[0].kind == "power_path"
    s = ss[0]
    assert _refs(P, s) == ["U1", "U3", "U4", "U5"]
    touched = {i for (ia, _), (ib, _), _ in s.segs for i in (ia, ib)}
    assert ref["J1"].i not in touched
    assert {ref["U3"].i, ref["U5"].i} <= touched
    per_net = {}
    for (ia, pa), (ib, pb), _ in s.segs:
        if ia == ref["U3"].i:
            net = P.parts[ia].fp.pads[pa[0]].net
            per_net[net] = per_net.get(net, 0) + 1
    assert per_net and max(per_net.values()) == 1
    macros = clusters.build_macros(P, ss, time_s=2.0, workers=1)
    assert len(macros) == 1 and sorted(macros[0].members) == sorted(s.members)


def test_commutation_cell_takes_its_snubber_and_bootstrap_parts():
    """kae.brief/1 commutation_cell optional members (snubbers [[r, c]], bootstrap_cap,
    bootstrap_r, charge_pump_caps, series_shunt) join the cell macro, tied by their nets."""
    P, ref, u = _brief_problem()
    brief = {"structures": [dict(
        kind="commutation_cell", id="cell:buck:U1", **{"class": "buck"}, rail="VCC", sw="SIG1", gnd="GND",
        loop=[[u["U4"], "3"], [u["U1"], "3"], [u["U1"], "2"], [u["U4"], "2"]],
        snubbers=[[u["R1"], u["U7"]]], bootstrap_cap=u["U5"], bootstrap_r=None, charge_pump_caps=[],
        series_shunt=[])]}
    ss = clusters.structures(P, brief)
    assert len(ss) == 1
    s = ss[0]
    assert _refs(P, s) == ["R1", "U1", "U4", "U5", "U7"]
    touched = {i for (ia, _), (ib, _), _ in s.segs for i in (ia, ib)}
    assert {ref["R1"].i, ref["U7"].i, ref["U5"].i} <= touched
    w_snub = max(w for (ia, _), _, w in s.segs if ia == ref["R1"].i)
    w_boot = max(w for (ia, _), _, w in s.segs if ia == ref["U5"].i)
    assert w_snub > w_boot
