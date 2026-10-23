# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.joint.ripup, kae.joint.penalty and kae.joint.replace on the synthetic fixture board."""
import dataclasses
from pathlib import Path

import numpy as np
from kae.board.kicad_file import load
from kae.joint.feedback import CongestionHistory, Window
from kae.joint.penalty import apply_history
from kae.joint.replace import replace_window, window_board
from kae.joint.ripup import plan_ripup

FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def _uuid(b, ref):
    return next(fp.uuid for fp in b.footprints if fp.ref == ref)


def test_ripup_whole_small_nets_partial_poured_nets_and_modules():
    b = load(FIXTURE)
    u1 = _uuid(b, "U1")
    win = Window(rect=(7.0, 7.0, 13.0, 13.0), parts=(u1,))
    plan = plan_ripup(b, win, {u1}, owners={}, module_parts={})
    sig1 = sorted(t.uuid for t in list(b.tracks) + list(b.vias) if t.net == "SIG1")
    assert plan.remove == sig1                       # U1's small net, whole (also outside the window)
    assert "SIG1" in plan.whole and "GND" in plan.nets
    assert all(v.uuid not in plan.remove for v in b.vias if v.net == "GND")   # poured, outside: kept
    # a locked via owned by a module with a moved part: the module is redone and its copper goes
    gnd_via = next(v for v in b.vias if v.net == "GND")
    vias = [dataclasses.replace(v, locked=True) if v is gnd_via else v for v in b.vias]
    b2 = dataclasses.replace(b, vias=vias)
    plan2 = plan_ripup(b2, win, {u1}, owners={gnd_via.uuid: "decap:U1"},
                       module_parts={"decap:U1": [u1], "cell:X": [_uuid(b, "U3")]})
    assert plan2.redo == ["decap:U1"] and gnd_via.uuid in plan2.remove
    # nothing moved, nothing inside the window: nothing ripped
    far = Window(rect=(52.0, 2.0, 58.0, 8.0), parts=())
    assert plan_ripup(b, far, set(), owners={}, module_parts={}).remove == []


def test_crossing_nets_inside_the_window_are_ripped():
    b = load(FIXTURE)
    win = Window(rect=(14.0, 11.0, 16.0, 13.0), parts=())
    plan = plan_ripup(b, win, set(), owners={}, module_parts={}, max_cross=4)
    assert set(plan.remove) == {t.uuid for t in list(b.tracks) + list(b.vias) if t.net == "SIG1"}
    assert plan.whole == ["SIG1"]


def test_window_board_locks_everything_outside():
    b = load(FIXTURE)
    u1 = _uuid(b, "U1")
    w = window_board(b, [u1])
    assert [fp.locked for fp in w.footprints if fp.uuid == u1] == [False]
    assert all(fp.locked for fp in w.footprints if fp.uuid != u1)
    assert not next(fp for fp in b.footprints if fp.ref == "U2").locked     # the input is untouched


class _Cong:
    def __init__(self):
        self.x0, self.y0, self.b, self.nbx, self.nby, self.S0 = 0.0, 0.0, 2.0, 30, 20, 10.0
        self.Dp = np.zeros((30, 20))
        self.Dn = np.zeros((30, 20))
        self.target = 0.5

    def total(self):
        u = (self.Dn + self.Dp) / self.S0 - self.target
        return float(np.square(np.clip(u, 0, None)).sum())


def test_history_becomes_static_demand_in_the_window_only():
    class Ann:
        cong = _Cong()
    h = CongestionHistory((0, 0, 60, 40), bin_mm=1.0)
    h.add_corridor((10, 10), (50, 10), width=1.0, amount=2.0)
    a = Ann()
    r = apply_history(a, h, scale=1.0, window=(8, 8, 14, 12))
    assert r["applied"] and r["cong_after"] > r["cong_before"]
    assert a.cong.Dp[5, 5] > 0 and a.cong.Dp[20, 5] == 0     # far bins of the corridor untouched
    assert not apply_history(type("N", (), {"cong": None})(), h)["applied"]


def test_replace_window_moves_only_window_parts_legally():
    b = load(FIXTURE)
    u1, u2 = _uuid(b, "U1"), _uuid(b, "U2")
    h = CongestionHistory((0, 0, 60, 40), bin_mm=1.0)
    h.add_corridor((8, 10), (22, 10), width=3.0, amount=3.0)
    win = Window(rect=(4.0, 4.0, 26.0, 18.0), parts=(u1, u2), refs=("U1", "U2"))
    res = replace_window(b, win, {"nets": {}, "structures": []}, history=h, seed=3, time_s=30.0, physics=False,
                         bump_refs=("U1",))
    assert res.report.get("history", {}).get("applied")
    assert set(res.poses) <= {u1, u2}
    if res.poses:
        assert res.report["legal_grid"] and not res.report["exact"]
        for u, (x, y, _, side) in res.poses.items():
            assert 4.0 <= x <= 26.0 and 4.0 <= y <= 18.0
            assert side == next(fp.side for fp in b.footprints if fp.uuid == u)
    again = replace_window(b, win, {"nets": {}, "structures": []}, history=h, seed=3, time_s=30.0, physics=False,
                           bump_refs=("U1",))
    assert again.poses == res.poses                              # seeded


def test_stages_geometry_and_finish_without_kicad(tmp_path):
    import shutil

    from kae.joint.stages import KaeStages, Layout
    from kae.route import critical_write as W
    inp = tmp_path / "in.kicad_pcb"
    shutil.copy2(FIXTURE, inp)
    st = KaeStages(inp, tmp_path / "wd", opts=dict(writer="sexpr"))
    b = load(inp)
    st.locked = {fp.uuid for fp in b.footprints if fp.locked}
    work = tmp_path / "work.kicad_pcb"
    W.append_items(inp, work, tracks=[("GND", "F.Cu", 0.25, (1.0, 1.0), (2.0, 1.0), "11111111-2222-3333-4444-555555555555",
                                       False)])
    u1 = _uuid(b, "U1")
    poses = {fp.uuid: (fp.x, fp.y, fp.rot, fp.side) for fp in b.footprints}
    poses[u1] = (12.0, 11.0, 0.0, "F")
    lay = Layout(board=str(work), poses=poses)
    parts, bounds, centres, refs = st.geometry(lay)
    assert bounds == (0.0, 0.0, 60.0, 40.0)
    assert parts[_uuid(b, "U6")].locked and not parts[u1].locked and refs[u1] == "U1"
    assert parts[_uuid(b, "U7")].locked                       # staged off the board: never moves
    out = tmp_path / "out.kicad_pcb"
    rep = st.finish(lay, out)
    assert rep["moved"] == 1
    o = load(out)
    assert [t.uuid for t in o.tracks if t.net == "GND"] == ["11111111-2222-3333-4444-555555555555"]
    fp = next(f for f in o.footprints if f.uuid == u1)
    assert (round(fp.x, 6), round(fp.y, 6)) == (12.0, 11.0)


def test_stages_rudy_map_without_kicad(tmp_path):
    from kae.joint.stages import KaeStages, Layout
    st = KaeStages(FIXTURE, tmp_path / "wd")
    x0, y0, b, util = st.rudy(Layout(board=str(FIXTURE)))
    assert b > 0 and util.ndim == 2 and util.max() > 0 and (x0, y0) == (0.0, 0.0)


def test_copper_blamed_by_drc_is_ripped():
    b = load(FIXTURE)
    gnd_via = next(v for v in b.vias if v.net == "GND")
    far = Window(rect=(52.0, 2.0, 58.0, 8.0), parts=())
    plan = plan_ripup(b, far, set(), owners={}, module_parts={}, also={gnd_via.uuid})
    assert plan.remove == [gnd_via.uuid]


def test_supply_nets_are_ripped_locally():
    b = load(FIXTURE)
    u1 = _uuid(b, "U1")
    win = Window(rect=(7.0, 7.0, 13.0, 13.0), parts=(u1,))
    plan = plan_ripup(b, win, {u1}, owners={}, module_parts={}, supply_nets={"SIG1"})
    assert "SIG1" in plan.partial and "SIG1" not in plan.whole
    assert sorted(plan.remove) == ["00000000-0000-4000-8000-000000000157"]   # only the track at U1's pad
