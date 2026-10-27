# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.board.transform: KiCad's rotation sense, flips, vectorized forms."""
import math
import random

import numpy as np
import pytest
from shapely.geometry import Polygon

from kae.board import transform as T
from kae.board.model import Footprint, Pad


def _fp(side="F", rot=0.0, pads=((1.0, 0.5, 0.0), (-2.0, 1.5, 90.0))):
    ps = [Pad(number=str(i + 1), net="", kind="smd", shape="rect", size=(1, 0.5), lx=lx, ly=ly, lrot=lr,
              x=0, y=0) for i, (lx, ly, lr) in enumerate(pads)]
    return Footprint(ref="U1", value="", lib_id="x:y", uuid="u", x=10.0, y=20.0, rot=rot, side=side,
                     locked=False, pads=ps,
                     courtyard=[Polygon([(-3, -1), (2, -1), (2, 2), (-3, 2)])])


def test_rotation_sense_is_kicads():
    # KiCad, y down: +90 degrees turns counter-clockwise on screen, so +x goes to -y (up)
    assert T.rotate(1.0, 0.0, 90) == (0.0, -1.0)
    assert T.rotate(0.0, 1.0, 90) == (1.0, 0.0)
    assert T.rotate(1.0, 0.0, 180) == (-1.0, 0.0)
    assert T.rotate(1.0, 0.0, -90) == (0.0, 1.0)
    u, v = T.rotate(1.0, 0.0, 30)
    assert u == pytest.approx(math.cos(math.radians(30))) and v == pytest.approx(-0.5)


def test_flip_mirrors_local_y():
    fp = _fp()
    p = fp.pads[0]
    assert T.pad_xy(fp, p, 0, 0, 0, "F") == (1.0, 0.5)
    assert T.pad_xy(fp, p, 0, 0, 0, "B") == (1.0, -0.5)
    # back side at 90: (1, -0.5) rotated by 90 -> (-0.5, -1)
    assert T.pad_xy(fp, p, 0, 0, 90, "B") == (-0.5, -1.0)
    assert T.pad_angle(fp, fp.pads[1], 30, "F") == 120.0
    assert T.pad_angle(fp, fp.pads[1], 30, "B") == 300.0


def test_to_local_inverts_to_board():
    rng = random.Random(3)
    for _ in range(200):
        lx, ly, x, y = (rng.uniform(-50, 50) for _ in range(4))
        rot, side = rng.choice([0, 90, 180, 270, rng.uniform(0, 360)]), rng.choice("FB")
        bx, by = T.to_board(lx, ly, x, y, rot, side)
        u, v = T.to_local(bx, by, x, y, rot, side)
        assert abs(u - lx) < 1e-9 and abs(v - ly) < 1e-9


def test_vectorized_matches_scalar():
    rng = np.random.default_rng(7)
    n = 500
    lx, ly = rng.uniform(-10, 10, n), rng.uniform(-10, 10, n)
    x, y = rng.uniform(0, 100, n), rng.uniform(0, 100, n)
    rot = np.where(rng.random(n) < 0.5, rng.choice([0, 90, 180, 270, -90, 450], n), rng.uniform(-720, 720, n))
    back = rng.random(n) < 0.5
    px, py = T.pads_xy(lx, ly, x, y, rot, back)
    for i in range(n):
        ex, ey = T.to_board(lx[i], ly[i], x[i], y[i], rot[i], "B" if back[i] else "F")
        assert abs(px[i] - ex) < 1e-12 and abs(py[i] - ey) < 1e-12
    sides = np.where(back, "B", "F")
    qx, qy = T.pads_xy(lx, ly, x, y, rot, sides)
    assert np.array_equal(px, qx) and np.array_equal(py, qy)
    # exact at multiples of 90 degrees
    qx, qy = T.pads_xy(np.array([1.25]), np.array([-0.75]), 0.0, 0.0, np.array([90.0]), "F")
    assert (qx[0], qy[0]) == (-0.75, -1.25)


def test_many_poses_of_one_footprint():
    fp = _fp()
    loc = T.local_pads(fp)
    xs, ys, rots = np.array([0.0, 5.0]), np.array([0.0, 1.0]), np.array([90.0, 33.0])
    px, py = T.pads_xy(loc[None, :, 0], loc[None, :, 1], xs[:, None], ys[:, None], rots[:, None], "B")
    assert px.shape == (2, 2)
    for k in range(2):
        for j, p in enumerate(fp.pads):
            ex, ey = T.pad_xy(fp, p, xs[k], ys[k], rots[k], "B")
            assert abs(px[k, j] - ex) < 1e-12 and abs(py[k, j] - ey) < 1e-12


def test_courtyard_follows_points():
    fp = _fp()
    for rot, side in ((0, "F"), (90, "F"), (37.5, "B"), (270, "B")):
        cy = T.courtyard(fp, 3.0, 4.0, rot, side)[0]
        for (u, v), (bx, by) in zip(fp.courtyard[0].exterior.coords, cy.exterior.coords):
            ex, ey = T.to_board(u, v, 3.0, 4.0, rot, side)
            assert abs(bx - ex) < 1e-12 and abs(by - ey) < 1e-12
    d = T.courtyard(fp, 0, 0, 0, "F", deflate=0.005)[0]
    assert d.bounds == pytest.approx((-2.995, -0.995, 1.995, 1.995))
    assert T.courtyard_layers(fp, "B") == ("B.CrtYd", "F.CrtYd")
    assert T.courtyard(fp, which="opposite") == []


def test_flip_layer():
    assert T.flip_layer("F.Cu") == "B.Cu" and T.flip_layer("B.SilkS") == "F.SilkS"
    assert T.flip_layer("In1.Cu", 4) == "In2.Cu" and T.flip_layer("In2.Cu", 6) == "In3.Cu"
    assert T.flip_layer("Edge.Cuts") == "Edge.Cuts"
    assert T.layers_at(["F.Cu", "F.Mask"], "F", "B") == ["B.Cu", "B.Mask"]
    assert T.layers_at(["F.Cu"], "F", "F") == ["F.Cu"]


def test_side_sign_inputs():
    assert T.side_sign("F") == 1 and T.side_sign("B") == -1 and T.side_sign(True) == -1
    assert T.side_sign(-1) == -1 and T.side_sign("B.Cu") == -1
    assert list(T.side_sign(np.array(["F", "B"]))) == [1, -1]
    with pytest.raises(ValueError):
        T.side_sign("X")
