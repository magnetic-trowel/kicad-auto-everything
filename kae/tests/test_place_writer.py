# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.writer: the S-expression writer moves footprints the way pcbnew does."""
import math
import random
import shutil
from pathlib import Path

import pytest

from kae.board import kicad_file, transform
from kae.place.writer import fmt, write_sexpr

DATA = Path(__file__).parent / "data" / "board"
FIXTURE = DATA / "fixture.kicad_pcb"


def _copy(tmp_path):
    p = tmp_path / "board.kicad_pcb"
    shutil.copy(FIXTURE, p)
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(FIXTURE.with_suffix(ext), p.with_suffix(ext))
    return p


def _poses(b, seed=7):
    rng = random.Random(seed)
    return {f.uuid: (round(f.x + rng.uniform(-6, 6), 4), round(f.y + rng.uniform(-6, 6), 4),
                     rng.choice([0.0, 90.0, 180.0, 270.0]), f.side)
            for f in b.footprints if not f.locked}


def test_fmt():
    assert fmt(1.0) == "1" and fmt(-0.0) == "0" and fmt(12.3456789) == "12.345679" and fmt(-0.5) == "-0.5"


def test_sexpr_writer_poses_and_pads(tmp_path):
    src = _copy(tmp_path)
    b = kicad_file.load(src)
    poses = _poses(b)
    out = tmp_path / "out.kicad_pcb"
    rep = write_sexpr(src, out, poses)
    assert rep["moved"] == len(poses)
    b2 = kicad_file.load(out)
    old = b.by_uuid()
    for f2 in b2.footprints:
        f1 = old[f2.uuid]
        if f2.uuid not in poses:
            assert (f2.x, f2.y, f2.rot, f2.side) == (f1.x, f1.y, f1.rot, f1.side)
            continue
        x, y, rot, side = poses[f2.uuid]
        assert abs(f2.x - x) < 1e-6 and abs(f2.y - y) < 1e-6 and abs((f2.rot - rot) % 360) < 1e-6
        # pad positions and absolute angles as the transform predicts; library frame unchanged
        q1 = {p.uuid: p for p in f1.pads}
        for p in f2.pads:
            ex, ey = transform.pad_xy(f1, q1[p.uuid], x, y, rot, side)
            assert math.hypot(p.x - ex, p.y - ey) < 2e-6
            assert abs(p.lx - q1[p.uuid].lx) < 2e-6 and abs(p.ly - q1[p.uuid].ly) < 2e-6
            assert abs((p.lrot - q1[p.uuid].lrot + 180) % 360 - 180) < 1e-6


def test_sexpr_writer_refuses_flips_and_unknowns(tmp_path):
    src = _copy(tmp_path)
    b = kicad_file.load(src)
    f = next(f for f in b.footprints if not f.locked and f.side == "F")
    with pytest.raises(ValueError):
        write_sexpr(src, tmp_path / "o.kicad_pcb", {f.uuid: (f.x, f.y, 0.0, "B")})
    with pytest.raises(KeyError):
        write_sexpr(src, tmp_path / "o.kicad_pcb", {"no-such-uuid": (0.0, 0.0, 0.0, "F")})


@pytest.mark.kicad
def test_sexpr_writer_matches_pcbnew(tmp_path):
    from kae.board import pcbnew_io, sdiff
    if not pcbnew_io.available():
        pytest.skip("no Python with pcbnew")
    src = _copy(tmp_path)
    b = kicad_file.load(src)
    poses = _poses(b, seed=11)
    ours = tmp_path / "ours.kicad_pcb"
    write_sexpr(src, ours, poses)
    ours_saved = tmp_path / "ours_saved.kicad_pcb"
    pcbnew_io.resave(ours, ours_saved)
    theirs = tmp_path / "theirs.kicad_pcb"
    pcbnew_io.write_poses(src, theirs, poses)
    assert sdiff.diff(theirs, ours_saved, tol=1e-4, rotation_artifacts=True) == []
