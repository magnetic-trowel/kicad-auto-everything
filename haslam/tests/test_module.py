# SPDX-FileCopyrightText: 2026 HaslamPCB contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""haslam.module.plan on synthetic boards: slots matched by nets and fit, poses, vias, copper frames."""
import math
from types import SimpleNamespace as NS

import pytest

from haslam import module as M
from haslam.board import transform as T


def pad(num, net, lx, ly, w=0.5, h=0.5):
    return NS(number=num, net=net, lx=lx, ly=ly, size=(w, h), lrot=0.0)


def fp(ref, pads, x=0.0, y=0.0, rot=0.0, side="F"):
    return NS(ref=ref, uuid="u-" + ref, x=x, y=y, rot=rot, side=side, pads=pads)


def board(*fps):
    return NS(footprints=list(fps))


def ic(side="F"):
    # an anchor with three role pins: VIN (1), GND (2), OUT (3)
    return fp("U1", [pad("1", "VIN_NET", -1, 0), pad("2", "GND", 0, 0), pad("3", "OUT_NET", 1, 0)], 10, 20, 0, side)


def cap(ref, a, b, pitch=2.0):
    return fp(ref, [pad("1", a, -pitch / 2, 0), pad("2", b, pitch / 2, 0)], 50, 50)


MOD = dict(schema=M.SCHEMA, anchor=dict(pins={"1": "VIN", "2": "PGND", "3": "OUT"}),
           slots=[dict(pads=[dict(net="VIN", x=-3.0, y=2.0), dict(net="PGND", x=-3.0, y=4.0)])],
           copper=[dict(layer="F.Cu", net="VIN", outline=[[-4, 1], [-2, 1], [-2, 3], [-4, 3]])],
           vias=[dict(x=-3.0, y=2.0, net="PGND"), dict(x=-3.0, y=4.0, net="PGND"), dict(x=3.0, y=3.0, net="PGND")])


def placed(p, f):
    x, y, r, s = p["moves"][f.uuid]
    return {q.number: T.to_board(q.lx, q.ly, x, y, r, s) for q in f.pads}


def test_a_slot_takes_the_part_with_its_nets_and_lands_each_pad_on_its_point():
    u, c = ic(), cap("C1", "VIN_NET", "GND")
    p = M.plan(board(u, c, cap("C2", "OUT_NET", "GND")), MOD, "U1")
    assert [s["ref"] for s in p["slots"]] == ["C1"] and not p["unmatched"]
    got = placed(p, c)
    # the slot is vertical in the anchor frame: the part is turned 90 degrees, VIN pad at (7, 22), GND at (7, 24)
    assert got["1"] == pytest.approx((7.0, 22.0), abs=1e-6) and got["2"] == pytest.approx((7.0, 24.0), abs=1e-6)
    assert p["slots"][0]["rms_mm"] < 1e-6
    assert set(p["refs"]) == {"U1", "C1"}


def test_another_package_does_not_fill_a_slot():
    # same nets, pad pitch 3.4 mm against the slot's 2.0: rms 0.7 mm > fit_tol
    p = M.plan(board(ic(), cap("C1", "VIN_NET", "GND", pitch=3.4)), MOD, "U1")
    assert not p["slots"] and p["unmatched"][0]["slot"] == 0


def test_a_via_on_another_nets_pad_is_dropped_and_one_on_its_own_net_kept():
    p = M.plan(board(ic(), cap("C1", "VIN_NET", "GND")), MOD, "U1")
    # (-3, 2) is on C1's VIN pad: dropped; (-3, 4) is on its GND pad: kept; (3, 3) is clear: kept
    q = M.plan(board(ic(), cap("C1", "VIN_NET", "GND")), MOD, "U1", vias_on_copper=False)
    xy = sorted((round(v["x"], 3), round(v["y"], 3)) for v in q["vias"])
    assert xy == [(7.0, 24.0), (13.0, 23.0)] and q["vias_dropped"] == 1


def test_by_default_a_via_off_the_modules_copper_of_its_net_is_dropped():
    gnd = dict(layer="F.Cu", net="PGND", outline=[[-4, 3.5], [-2, 3.5], [-2, 4.5], [-4, 4.5]])
    mod = dict(MOD, copper=MOD["copper"] + [gnd])
    p = M.plan(board(ic(), cap("C1", "VIN_NET", "GND")), mod, "U1")
    # (-3, 4) lies on the PGND piece: kept; (3, 3) is on no PGND copper: dropped; (-3, 2) on VIN copper: dropped
    assert [(round(v["x"], 3), round(v["y"], 3)) for v in p["vias"]] == [(7.0, 24.0)] and p["vias_dropped"] == 2
    assert all(v["net"] == "GND" for v in p["vias"])


def test_copper_follows_the_anchor_pose_and_side():
    p = M.plan(board(ic(), cap("C1", "VIN_NET", "GND")), MOD, "U1", at=(0.0, 0.0, 90.0))
    z = p["zones"][0]
    assert z["net"] == "VIN_NET" and z["layer"] == "F.Cu"
    assert z["outline"][0] == pytest.approx(T.to_board(-4, 1, 0, 0, 90, "F"))
    pb = M.plan(board(ic(side="B"), cap("C1", "VIN_NET", "GND")), MOD, "U1")
    assert pb["zones"][0]["layer"] == "B.Cu"


def test_a_role_without_a_net_on_the_anchor_leaves_its_slot_empty():
    mod = dict(MOD, slots=[dict(pads=[dict(net="NOPE", x=0, y=3), dict(net="PGND", x=0, y=5)])])
    p = M.plan(board(ic(), cap("C1", "VIN_NET", "GND")), mod, "U1")
    assert p["unmatched"] and "no net" in p["unmatched"][0]["why"]


def test_load_checks_the_schema(tmp_path):
    f = tmp_path / "m.json"
    f.write_text('{"schema": "other"}')
    with pytest.raises(ValueError):
        M.load(f)
