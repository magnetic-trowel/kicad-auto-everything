# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.writer: the S-expression writer moves footprints the way pcbnew does."""
import math
import random
import re
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


def test_sexpr_writer_spells_footprint_angles_as_kicad(tmp_path):
    """FOOTPRINT::SetOrientation keeps the footprint angle in (-180, 180]: 270 is written -90."""
    src = _copy(tmp_path)
    b = kicad_file.load(src)
    f = next(f for f in b.footprints if not f.locked and f.side == "F")
    out = tmp_path / "o.kicad_pcb"
    write_sexpr(src, out, {f.uuid: (f.x, f.y, 270.0, "F")})
    text = out.read_text()
    blk = text[text.index(f'(uuid "{f.uuid}")'):]
    assert blk.split("(at ", 1)[1].split(")", 1)[0] == f"{fmt(f.x)} {fmt(f.y)} -90"
    assert kicad_file.load(out).by_uuid()[f.uuid].rot % 360 == 270.0


def test_sexpr_writer_takes_the_loaders_keys(tmp_path):
    """Footprints with no uuid, a repeated uuid or a KiCad 5 tstamp are found by the key
    kicad_file.load gives them, as pcbnew_io.write_poses finds them."""
    text = FIXTURE.read_text()
    uu = [m.group(1) for m in re.finditer(r'\t\(footprint "[^"]*"\n\t\t\(layer "[^"]*"\)\n\t\t\(uuid "([^"]*)"\)', text)]
    assert len(uu) >= 3
    text = text.replace(f'(uuid "{uu[1]}")', f'(uuid "{uu[0]}")', 1)          # repeated
    text = text.replace(f'\t\t(uuid "{uu[2]}")\n', "", 1)                    # missing
    p = tmp_path / "keys.kicad_pcb"
    p.write_text(text)
    b = kicad_file.load(p)
    flags = {f.uuid: f.flags for f in b.footprints}
    assert sum("uuid_duplicate" in v for v in flags.values()) == 1
    assert sum("uuid_synthesized" in v for v in flags.values()) == 1
    poses = {f.uuid: (f.x + 1.0, f.y, f.rot, f.side) for f in b.footprints if not f.locked}
    out = tmp_path / "o.kicad_pcb"
    assert write_sexpr(p, out, poses)["moved"] == len(poses)
    # a synthesized key hashes the pose, so compare in file order
    for f1, f2 in zip(b.footprints, kicad_file.load(out).footprints):
        assert abs(f2.x - (poses[f1.uuid][0] if f1.uuid in poses else f1.x)) < 1e-6
    # KiCad 5: (module ... (tstamp 5C0A1B2C)) is keyed as pcbnew reads it
    k5 = ('(kicad_pcb (version 20171130) (host pcbnew 5.1.6)\n'
          '  (module R_0603 (layer F.Cu) (tedit 5B301BBD) (tstamp 5C0A1B2C)\n    (at 10 20 90)\n'
          '    (fp_text reference R1 (at 0 -1.4 90) (layer F.SilkS))\n'
          '    (pad 1 smd rect (at -0.8 0 90) (size 0.8 0.9) (layers F.Cu F.Paste F.Mask))\n  )\n)\n')
    p5 = tmp_path / "k5.kicad_pcb"
    p5.write_text(k5)
    key = kicad_file.load(p5).footprints[0].uuid
    assert key == "00000000-0000-0000-0000-00005c0a1b2c"
    write_sexpr(p5, tmp_path / "k5o.kicad_pcb", {key: (11.0, 20.0, 90.0, "F")})
    assert kicad_file.load(tmp_path / "k5o.kicad_pcb").footprints[0].x == 11.0


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
