# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Board operations that need KiCad's pcbnew module.

Runs under KiCad's own Python interpreter (only stdlib + pcbnew), as a separate
process from the harness. Every operation prints one JSON object on stdout.

    python pcbnew_ops.py stats BOARD
    python pcbnew_ops.py convert IN OUT
    python pcbnew_ops.py strip-routing IN OUT [--keep-locked]
    python pcbnew_ops.py strip-placement IN OUT
    python pcbnew_ops.py export-dsn IN DSN
    python pcbnew_ops.py import-ses IN SES OUT
"""
import hashlib
import json
import math
import os
import sys

# pcbnew prints wx asserts on import and SWIG prints leak warnings at exit, both
# on stdout. Keep a private handle to the real stdout for JSON and send fd 1 to
# stderr for the rest of the process.
_JSON_OUT = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)
import pcbnew  # noqa: E402

NM = 1e6  # internal units per mm


def _mm(v):
    return v / NM


def _out(obj):
    _JSON_OUT.write(json.dumps(obj) + "\n")
    _JSON_OUT.flush()


def _load(path):
    board = pcbnew.LoadBoard(path)
    if board is None:
        raise RuntimeError(f"could not load {path}")
    return board


def _save(board, path):
    if not pcbnew.SaveBoard(path, board):
        raise RuntimeError(f"could not save {path}")


def _is_routing(item):
    return item.GetClass() in ("PCB_TRACK", "PCB_ARC", "PCB_VIA")


def _track_length(t):
    if t.GetClass() == "PCB_ARC":
        return _mm(t.GetLength())
    s, e = t.GetStart(), t.GetEnd()
    return _mm(math.hypot(e.x - s.x, e.y - s.y))


def _placement(board):
    # "inside" = every pad centre lies within the board outline (connectors may overhang).
    outline = pcbnew.SHAPE_POLY_SET()
    has_outline = board.GetBoardPolygonOutlines(outline, False) and outline.OutlineCount() > 0
    rows = []
    for fp in board.GetFootprints():
        p = fp.GetPosition()
        inside = all(outline.Contains(pad.GetCenter()) for pad in fp.Pads()) if has_outline else None
        rows.append(dict(ref=fp.GetReference(), uuid=fp.m_Uuid.AsString(),
                         x=round(_mm(p.x), 4), y=round(_mm(p.y), 4),
                         rot=round(fp.GetOrientationDegrees() % 360.0, 3),
                         back=bool(fp.IsFlipped()), locked=bool(fp.IsLocked()), inside=inside))
    rows.sort(key=lambda r: r["uuid"])
    return rows


def _pad_nets(board):
    rows = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            rows.append(f"{fp.m_Uuid.AsString()}:{pad.GetNumber()}:{pad.GetNetname()}")
    rows.sort()
    return rows


def _hash(rows):
    return hashlib.sha256("\n".join(map(str, rows)).encode()).hexdigest()


def stats(path):
    board = _load(path)
    tracks = arcs = vias = 0
    length = 0.0
    locked_routing = 0
    for t in board.GetTracks():
        cls = t.GetClass()
        if cls == "PCB_VIA":
            vias += 1
        else:
            if cls == "PCB_ARC":
                arcs += 1
            else:
                tracks += 1
            length += _track_length(t)
        if t.IsLocked():
            locked_routing += 1
    # pads per net -> HPWL over pad centres, connections = pads - 1 per net
    net_pads = {}
    n_pads = 0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            n_pads += 1
            code = pad.GetNetCode()
            if code <= 0:
                continue
            c = pad.GetCenter()
            net_pads.setdefault(code, []).append((c.x, c.y))
    hpwl = 0.0
    connections = 0
    for pts in net_pads.values():
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        hpwl += _mm(max(xs) - min(xs) + max(ys) - min(ys))
        connections += len(pts) - 1
    bb = board.GetBoardEdgesBoundingBox()
    ds = board.GetDesignSettings()
    rules = dict(edge_clearance_mm=_mm(ds.m_CopperEdgeClearance), min_track_width_mm=_mm(ds.m_TrackMinWidth),
                 min_clearance_mm=_mm(ds.m_MinClearance), hole_clearance_mm=_mm(ds.m_HoleClearance))
    placement = _placement(board)
    pad_nets = _pad_nets(board)
    _out(dict(
        ok=True, path=path, kicad_version=pcbnew.Version(),
        copper_layers=board.GetCopperLayerCount(),
        footprints=len(placement), locked_footprints=sum(r["locked"] for r in placement),
        pads=n_pads, nets=len([1 for p in net_pads.values() if len(p) >= 2]),
        connections=connections, tracks=tracks, arcs=arcs, vias=vias,
        locked_routing=locked_routing, track_length_mm=round(length, 3),
        zones=board.GetAreaCount(), hpwl_mm=round(hpwl, 3), rules=rules,
        board_mm=[round(_mm(bb.GetWidth()), 3), round(_mm(bb.GetHeight()), 3)],
        board_origin_mm=[round(_mm(bb.GetX()), 3), round(_mm(bb.GetY()), 3)],
        placement_hash=_hash([(r["uuid"], r["x"], r["y"], r["rot"], r["back"]) for r in placement]),
        padnet_hash=_hash(pad_nets),
        placement=placement,
    ))


def convert(src, dst):
    board = _load(src)
    _save(board, dst)
    _out(dict(ok=True, path=dst))


def _strip_routing(board, keep_locked):
    # Stale fills would hide unrouted connections; DRC refills zones before checking.
    # Unfill before removing tracks: after Remove() SWIG returns untyped zone objects.
    for i in range(board.GetAreaCount()):
        pcbnew.Cast_to_ZONE(board.GetArea(i)).UnFill()
    removed = 0
    for t in list(board.GetTracks()):
        if keep_locked and t.IsLocked():
            continue
        board.Remove(t)
        removed += 1
    return removed


def strip_routing(src, dst, keep_locked):
    board = _load(src)
    removed = _strip_routing(board, keep_locked)
    _save(board, dst)
    _out(dict(ok=True, path=dst, removed=removed))


def strip_placement(src, dst):
    """Strip all routing and move every unlocked footprint to a staging grid right of the board.

    Locked footprints stay where the designer put them: they are part of the task (mounting
    holes, connectors), and the scorer requires them unmoved.
    """
    board = _load(src)
    # Move footprints before removing tracks: after Remove() SWIG returns untyped objects.
    bb = board.GetBoardEdgesBoundingBox()
    x0 = bb.GetRight() + int(10 * NM)
    y0 = bb.GetTop()
    col_h = max(bb.GetHeight(), int(50 * NM))
    x, y, col_w = x0, y0, 0
    moved = 0
    fps = [fp for fp in board.GetFootprints() if not fp.IsLocked()]
    fps.sort(key=lambda f: f.GetReference())
    for fp in fps:
        fp.SetOrientationDegrees(0)
        fbb = fp.GetBoundingBox(False)
        w, h = fbb.GetWidth() + int(1 * NM), fbb.GetHeight() + int(1 * NM)
        if y + h > y0 + col_h:
            x, y, col_w = x + col_w, y0, 0
        # place footprint so its bounding box starts at (x, y)
        off_x = fp.GetPosition().x - fbb.GetX()
        off_y = fp.GetPosition().y - fbb.GetY()
        fp.SetPosition(pcbnew.VECTOR2I(x + off_x, y + off_y))
        y += h
        col_w = max(col_w, w)
        moved += 1
    removed = _strip_routing(board, False)
    _save(board, dst)
    _out(dict(ok=True, path=dst, removed=removed, moved=moved))


def export_dsn(src, dsn):
    board = _load(src)
    ok = pcbnew.ExportSpecctraDSN(board, dsn)
    if ok is not True:
        raise RuntimeError("ExportSpecctraDSN failed")
    _out(dict(ok=True, path=dsn))


def import_ses(src, ses, dst):
    board = _load(src)
    ok = pcbnew.ImportSpecctraSES(board, ses)
    if ok is not True:
        raise RuntimeError("ImportSpecctraSES failed")
    _save(board, dst)
    _out(dict(ok=True, path=dst))


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    op, args = argv[1], argv[2:]
    keep_locked = "--keep-locked" in args
    args = [a for a in args if not a.startswith("--")]
    try:
        if op == "stats":
            stats(args[0])
        elif op == "convert":
            convert(args[0], args[1])
        elif op == "strip-routing":
            strip_routing(args[0], args[1], keep_locked)
        elif op == "strip-placement":
            strip_placement(args[0], args[1])
        elif op == "export-dsn":
            export_dsn(args[0], args[1])
        elif op == "import-ses":
            import_ses(args[0], args[1], args[2])
        else:
            raise SystemExit(f"unknown op {op}")
    except Exception as e:  # report failures as JSON so the harness can record them
        _out(dict(ok=False, op=op, error=f"{type(e).__name__}: {e}"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
