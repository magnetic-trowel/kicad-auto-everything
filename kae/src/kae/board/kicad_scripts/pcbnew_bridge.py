# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""pcbnew side of kae.board.pcbnew_io. Runs under KiCad's own Python (stdlib + pcbnew
only), in a separate process from kae. Every operation writes its JSON result to OUT
and prints one status line ({"ok": ...}) on stdout.

    python pcbnew_bridge.py extract BOARD OUT [--no-courtyards] [--no-outline]
    python pcbnew_bridge.py write-poses BOARD POSES OUT_JSON DEST [--allow-locked]
    python pcbnew_bridge.py resave BOARD OUT_JSON DEST

extract: pcbnew's own footprint poses, pads (absolute and footprint-relative), courtyards
(F/B.CrtYd caches), the board outline (GetBoardPolygonOutlines), design rules, net classes
and layers. Lengths in mm, angles in degrees as pcbnew reports them.

write-poses: POSES is a JSON list of {uuid or ref, x, y, rot, side}; a reference must
name exactly one footprint, and unknown, ambiguous or locked footprints fail the whole
call (unless --allow-locked) before anything is written. A side change uses
FOOTPRINT::Flip (left-right, about the footprint's own position); then SetOrientation
and SetPosition. Nothing else is touched. Saved with SaveBoard(skip settings) to a
temporary directory and moved to DEST, so no project file is written.
"""
import json
import os
import shutil
import sys
import tempfile
import uuid as _uuid

# pcbnew prints wx asserts on import and SWIG prints leak warnings at exit, both on stdout.
# Keep a private handle to the real stdout and send fd 1 to stderr for the rest.
_STATUS = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)
import pcbnew  # noqa: E402

NM = 1e6


def _mm(v):
    return v / NM


def _synth_uuid(fp, index):
    """Same key as kae.board.kicad_file.synth_uuid (footprints without a usable uuid)."""
    p = fp.GetPosition()
    rm = int(round((fp.GetOrientationDegrees() % 360.0) * 1000)) % 360000
    side = "B" if fp.IsFlipped() else "F"
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL,
                           f"kae-footprint:{fp.GetFPIDAsString()}:{p.x}:{p.y}:{rm}:{side}:{index}"))


def _keys(board):
    """Each footprint's key: its uuid, or the synthesized key when the uuid repeats an
    earlier footprint's. Also every footprint's synthesized key, for files whose
    footprints had no uuid (pcbnew then invents random ones)."""
    keys, alias, seen = [], {}, set()
    for i, fp in enumerate(board.GetFootprints()):
        u = fp.m_Uuid.AsString()
        a = _synth_uuid(fp, i)
        alias[a] = fp
        keys.append(a if u in seen else u)
        seen.add(u)
    return keys, alias


def _status(obj):
    _STATUS.write(json.dumps(obj) + "\n")
    _STATUS.flush()


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def _load(path):
    board = pcbnew.LoadBoard(path)
    if board is None:
        raise RuntimeError(f"could not load {path}")
    return board


def _chain(lc):
    return [[_mm(lc.CPoint(i).x), _mm(lc.CPoint(i).y)] for i in range(lc.PointCount())]


def _polyset(ps):
    out = []
    for i in range(ps.OutlineCount()):
        rings = [_chain(ps.Outline(i))]
        for h in range(ps.HoleCount(i)):
            rings.append(_chain(ps.Hole(i, h)))
        out.append(rings)
    return out


def _layer_names(board, lset, enabled):
    # canonical names (GetLayerName returns user names such as "GND" for In1.Cu)
    return [board.GetStandardLayerName(l) for l in lset.Seq() if l in enabled]


_PAD_ATTR = {pcbnew.PAD_ATTRIB_PTH: "thru_hole", pcbnew.PAD_ATTRIB_SMD: "smd",
             pcbnew.PAD_ATTRIB_CONN: "connect", pcbnew.PAD_ATTRIB_NPTH: "np_thru_hole"}


def extract(path, out, courtyards=True, outline=True):
    board = _load(path)
    enabled = set(board.GetEnabledLayers().Seq())
    fps = []
    keys, _ = _keys(board)
    for fp, key in zip(board.GetFootprints(), keys):
        p = fp.GetPosition()
        rec = dict(uuid=key, kicad_uuid=fp.m_Uuid.AsString(), ref=fp.GetReference(), value=fp.GetValue(),
                   lib_id=fp.GetFPIDAsString(), x=_mm(p.x), y=_mm(p.y),
                   rot=fp.GetOrientationDegrees(), side="B" if fp.IsFlipped() else "F",
                   locked=bool(fp.IsLocked()), attrs=int(fp.GetAttributes()),
                   dnp=bool(fp.IsDNP()), board_only=bool(fp.IsBoardOnly()),
                   fields={f.GetName(): f.GetText() for f in fp.GetFields()}, pads=[])
        for pad in fp.Pads():
            c = pad.GetPosition()
            r = pad.GetFPRelativePosition()
            sz = pad.GetSize(pcbnew.F_Cu)
            rec["pads"].append(dict(
                number=pad.GetNumber(), uuid=pad.m_Uuid.AsString(), x=_mm(c.x), y=_mm(c.y),
                rot=pad.GetOrientationDegrees(), rx=_mm(r.x), ry=_mm(r.y),
                rrot=pad.GetFPRelativeOrientation().AsDegrees(), net=pad.GetNetname(),
                kind=_PAD_ATTR.get(pad.GetAttribute(), str(pad.GetAttribute())),
                size=[_mm(sz.x), _mm(sz.y)], drill=[_mm(pad.GetDrillSizeX()), _mm(pad.GetDrillSizeY())],
                layers=_layer_names(board, pad.GetLayerSet(), enabled)))
        if courtyards:
            rec["courtyard"] = {"F.CrtYd": _polyset(fp.GetCourtyard(pcbnew.F_CrtYd)),
                                "B.CrtYd": _polyset(fp.GetCourtyard(pcbnew.B_CrtYd))}
        fps.append(rec)
    res = dict(ok=True, kicad_version=pcbnew.Version(), path=path, footprints=fps)
    if outline:
        ps = pcbnew.SHAPE_POLY_SET()
        ok = board.GetBoardPolygonOutlines(ps, False)
        res["outline_ok"] = bool(ok)
        res["outline"] = _polyset(ps)
    ds = board.GetDesignSettings()
    res["rules"] = dict(clearance=_mm(ds.m_MinClearance), track_min=_mm(ds.m_TrackMinWidth),
                        via_min=_mm(ds.m_ViasMinSize), edge_clearance=_mm(ds.m_CopperEdgeClearance),
                        hole_clearance=_mm(ds.m_HoleClearance), via_drill_min=_mm(ds.m_MinThroughDrill),
                        hole_to_hole=_mm(ds.m_HoleToHoleMin), annular_min=_mm(ds.m_ViasMinAnnularWidth),
                        microvia_min=_mm(ds.m_MicroViasMinSize), microvia_drill_min=_mm(ds.m_MicroViasMinDrill),
                        max_error=_mm(ds.m_MaxError))
    res["thickness"] = _mm(ds.GetBoardThickness())
    res["copper"] = [board.GetStandardLayerName(l) for l in board.GetEnabledLayers().CuStack()]
    nets = {}
    for code, item in board.GetNetInfo().NetsByNetcode().items():
        name = item.GetNetname()
        if name:
            nets[name] = item.GetNetClassName()
    res["netclass"] = nets
    _write(out, res)
    _status(dict(ok=True, footprints=len(fps)))


def _save(board, dest):
    d = tempfile.mkdtemp(prefix="kae-save-")
    try:
        tmp = os.path.join(d, os.path.basename(dest))
        if not pcbnew.SaveBoard(tmp, board, True):
            raise RuntimeError(f"could not save {dest}")
        shutil.move(tmp, dest)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def write_poses(path, poses_path, out, dest, allow_locked=False):
    with open(poses_path) as f:
        poses = json.load(f)
    board = _load(path)
    keys, alias = _keys(board)
    by_uuid, by_ref = dict(alias), {}
    for fp, key in zip(board.GetFootprints(), keys):
        by_uuid.setdefault(key, fp)
        by_ref.setdefault(fp.GetReference(), []).append(fp)
    missing, ambiguous, locked, seen = [], [], [], set()
    todo = []
    for p in poses:
        key = p.get("uuid") or p.get("ref")
        fp = by_uuid.get(key)
        if fp is None:
            cands = by_ref.get(key, [])
            if len(cands) > 1:
                ambiguous.append(key)
                continue
            fp = cands[0] if cands else None
        if fp is None:
            missing.append(key)
            continue
        if id(fp) in seen:
            ambiguous.append(key)
            continue
        seen.add(id(fp))
        if fp.IsLocked() and not allow_locked:
            locked.append(fp.GetReference())
            continue
        todo.append((fp, p))
    if missing or ambiguous or locked:
        res = dict(ok=False, error=f"{len(missing)} unknown footprints, {len(ambiguous)} ambiguous or repeated "
                                   f"references, {len(locked)} locked footprints",
                   missing=missing[:50], ambiguous=ambiguous[:50], locked=locked[:50])
        _write(out, res)
        _status(dict(ok=False, error=res["error"]))
        return
    moved = flipped = 0
    for fp, p in todo:
        back = p["side"] == "B"
        if bool(fp.IsFlipped()) != back:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            flipped += 1
        fp.SetOrientation(pcbnew.EDA_ANGLE(float(p["rot"]), pcbnew.DEGREES_T))
        fp.SetPosition(pcbnew.VECTOR2I(int(round(float(p["x"]) * NM)), int(round(float(p["y"]) * NM))))
        moved += 1
    _save(board, dest)
    _write(out, dict(ok=True, moved=moved, flipped=flipped, path=dest))
    _status(dict(ok=True, moved=moved, flipped=flipped))


def resave(path, out, dest):
    _save(_load(path), dest)
    _write(out, dict(ok=True, path=dest))
    _status(dict(ok=True))


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    op, args = argv[1], [a for a in argv[2:] if not a.startswith("--")]
    flags = {a for a in argv[2:] if a.startswith("--")}
    try:
        if op == "extract":
            extract(args[0], args[1], courtyards="--no-courtyards" not in flags,
                    outline="--no-outline" not in flags)
        elif op == "write-poses":
            write_poses(args[0], args[1], args[2], args[3], allow_locked="--allow-locked" in flags)
        elif op == "resave":
            resave(args[0], args[1], args[2])
        else:
            raise SystemExit(f"unknown op {op}")
    except Exception as e:  # report failures as JSON
        _status(dict(ok=False, op=op, error=f"{type(e).__name__}: {e}"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
