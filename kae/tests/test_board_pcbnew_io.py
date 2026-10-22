# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.board.pcbnew_io against live pcbnew (skipped without KiCad's Python)."""
import json
import math
import random
import shutil
from pathlib import Path

import pytest

from kae.board import kicad_file, pcbnew_io, sdiff, transform

DATA = Path(__file__).parent / "data" / "board"
FIXTURE = DATA / "fixture.kicad_pcb"

pytestmark = [pytest.mark.kicad,
              pytest.mark.skipif(not pcbnew_io.available(), reason="no Python with pcbnew")]


def _copy(tmp_path, name="board", text=None):
    p = tmp_path / f"{name}.kicad_pcb"
    if text is None:
        shutil.copy(FIXTURE, p)
    else:
        p.write_text(text)
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(FIXTURE.with_suffix(ext), p.with_suffix(ext))
    return p


def test_verify_live_and_golden_unchanged():
    x = pcbnew_io.extract(FIXTURE)
    rep = pcbnew_io.verify(FIXTURE, data=x)
    assert rep["pad_err"] < 1e-6 and rep["net_mismatch"] == rep["layer_mismatch"] == 0
    assert rep["courtyard"]["max_straight"] < 1e-5 and rep["netclass_diff"] == {}
    golden = json.loads((DATA / "fixture.pcbnew.json").read_text())
    pads = {(f["uuid"], p["uuid"]): (p["x"], p["y"]) for f in golden["footprints"] for p in f["pads"]}
    for f in x["footprints"]:
        for p in f["pads"]:
            gx, gy = pads[(f["uuid"], p["uuid"])]
            assert abs(gx - p["x"]) < 1e-9 and abs(gy - p["y"]) < 1e-9


def _random_poses(b, rng):
    poses = {}
    for fp in b.footprints:
        if fp.locked:
            continue
        rot = rng.choice([0.0, 90.0, 180.0, 270.0, rng.uniform(0, 360)])
        poses[fp.uuid] = (round(fp.x + rng.uniform(-8, 8), 6), round(fp.y + rng.uniform(-8, 8), 6), rot,
                          rng.choice("FB"))
    return poses


def test_write_poses_round_trip(tmp_path):
    src = _copy(tmp_path)
    b = kicad_file.load(src)
    poses = _random_poses(b, random.Random(11))
    assert any(s == "B" for *_, s in poses.values()) and any(r % 90 for _, _, r, _ in poses.values())
    out = tmp_path / "out.kicad_pcb"
    res = pcbnew_io.write_poses(src, out, poses)
    assert res["moved"] == len(poses) and res["flipped"] > 0
    assert not out.with_suffix(".kicad_pro").exists()          # no project files written
    x = pcbnew_io.extract(out, courtyards=False, outline=False)
    k = {f["uuid"]: f for f in x["footprints"]}
    worst = 0.0
    for fp in b.footprints:
        X, Y, R, S = poses.get(fp.uuid, (fp.x, fp.y, fp.rot, fp.side))
        kf = k[fp.uuid]
        assert kf["side"] == S
        kp = {p["uuid"]: p for p in kf["pads"]}
        for p in fp.pads:
            ex, ey = transform.pad_xy(fp, p, X, Y, R, S)
            worst = max(worst, math.hypot(ex - kp[p.uuid]["x"], ey - kp[p.uuid]["y"]))
    assert worst < 1e-6
    # the written file reads back the same in the library frame
    b2 = kicad_file.load(out)
    old = b.by_uuid()
    for f2 in b2.footprints:
        f1 = old[f2.uuid]
        q1 = {p.uuid: p for p in f1.pads}
        for p in f2.pads:
            assert abs(p.lx - q1[p.uuid].lx) < 2e-6 and abs(p.ly - q1[p.uuid].ly) < 2e-6
            assert transform.layers_at(q1[p.uuid].layers, f1.side, f2.side, 4) == p.layers or \
                set(transform.layers_at(q1[p.uuid].layers, f1.side, f2.side, 4)) == set(p.layers)
    # nothing but the moved footprints changed; moving them back restores the file
    base = tmp_path / "base.kicad_pcb"
    pcbnew_io.resave(src, base)
    assert sdiff.diff(src, base) == []
    changes = sdiff.diff(base, out)
    assert changes and all(c["kind"] == "footprint" and c["change"] == "changed" for c in changes)
    assert {c["id"] for c in changes} <= set(poses)
    back = tmp_path / "back.kicad_pcb"
    pcbnew_io.write_poses(out, back, {fp.uuid: (fp.x, fp.y, fp.rot, fp.side) for fp in b.footprints
                                      if fp.uuid in poses})
    # pcbnew keeps off-axis rectangles as polygons and text upright: nothing else differs
    assert sdiff.diff(base, back, tol=1e-4, rotation_artifacts=True) == []


def test_write_poses_refusals(tmp_path):
    src = _copy(tmp_path)
    b = kicad_file.load(src)
    locked = next(f for f in b.footprints if f.locked)
    out = tmp_path / "out.kicad_pcb"
    with pytest.raises(pcbnew_io.PcbnewError, match="locked"):
        pcbnew_io.write_poses(src, out, {locked.uuid: (1, 1, 0, "F")})
    with pytest.raises(pcbnew_io.PcbnewError, match="unknown"):
        pcbnew_io.write_poses(src, out, {"no-such-uuid": (1, 1, 0, "F")})
    assert not out.exists()
    pcbnew_io.write_poses(src, out, {locked.uuid: (locked.x + 1, locked.y, 0, "F")}, allow_locked=True)
    assert kicad_file.load(out).by_uuid()[locked.uuid].x == locked.x + 1
    # the older argument order, and a unique reference as the key
    u1 = next(f for f in b.footprints if f.ref == "U1")
    pcbnew_io.write_poses(src, {"U1": (u1.x, u1.y + 2, 180, "B")}, out)
    f = kicad_file.load(out).by_uuid()[u1.uuid]
    assert (f.y, f.rot, f.side) == (u1.y + 2, 180.0, "B")


def test_kicad8_dialect_through_pcbnew(tmp_path):
    from test_board_kicad_file import _to_kicad8
    p = _copy(tmp_path, "k8", _to_kicad8(FIXTURE.read_text()))
    rep = pcbnew_io.verify(p)
    assert rep["pad_err"] < 1e-6 and rep["net_mismatch"] == 0 and not rep["missing_fp"]
    assert rep["locked_mismatch"] == [] and rep["netclass_diff"] == {}
