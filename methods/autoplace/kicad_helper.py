# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""pcbnew side of the experimental autoplacer (runs in KiCad's Python).

  extract BOARD OUT.json     outline, keep-outs, locked obstacles, and for every free
                             footprint its rectangle and pad offsets at 0/90/180/270 deg,
                             read from pcbnew itself (no rotation maths of our own)
  write BOARD POSES.json DST set each listed footprint's position and rotation
  unconnected BOARD          fill zones, report unconnected items, tracks, vias
"""
import json
import sys

import pcbnew

NM = 1e6
ROTS = (0, 90, 180, 270)


def mm(v):
    return v / NM


def _chain(c):
    return [(mm(c.CPoint(i).x), mm(c.CPoint(i).y)) for i in range(c.PointCount())]


def _polys(ps):
    return [dict(outer=_chain(ps.Outline(i)), holes=[_chain(ps.Hole(i, h)) for h in range(ps.HoleCount(i))])
            for i in range(ps.OutlineCount())]


def _box(b):
    return [mm(b.GetLeft()), mm(b.GetTop()), mm(b.GetRight()), mm(b.GetBottom())]


def _union(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _rect(fp):
    """Courtyard bbox (either side) united with the pads' bboxes. None for artwork (no
    courtyard, no pads): DRC never checks it against anything."""
    fp.BuildCourtyardCaches()
    r = None
    for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        ps = fp.GetCourtyard(layer)
        if ps.OutlineCount():
            r = _union(r, _box(ps.BBox()))
    for p in fp.Pads():
        r = _union(r, _box(p.GetBoundingBox()))
    return r


def _tht(fp):
    return any(p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH) for p in fp.Pads())


def _pads(fp):
    return [[mm(p.GetPosition().x), mm(p.GetPosition().y), p.GetNetname()] for p in fp.Pads()]


def extract(path, out):
    board = pcbnew.LoadBoard(path)
    ps = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(ps, False)
    ds = board.GetDesignSettings()
    pour_nets = set()
    keepouts = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            if z.GetDoNotAllowFootprints() or z.GetDoNotAllowPads():
                ls = z.GetLayerSet()
                keepouts.append(dict(front=ls.Contains(pcbnew.F_Cu), back=ls.Contains(pcbnew.B_Cu),
                                     polys=_polys(z.Outline())))
        elif z.GetNetCode() > 0:
            pour_nets.add(z.GetNetname())
    fixed, free = [], []
    for fp in board.GetFootprints():
        rec = dict(uuid=fp.m_Uuid.AsString(), ref=fp.GetReference(), back=fp.IsFlipped(), tht=_tht(fp))
        if fp.IsLocked():
            rec.update(rect=_rect(fp), pads=_pads(fp))
            fixed.append(rec)
            continue
        pos, ori = fp.GetPosition(), fp.GetOrientation()
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        rec["rots"] = []
        for r in ROTS:
            fp.SetOrientationDegrees(r)
            rec["rots"].append(dict(rot=r, rect=_rect(fp), pads=_pads(fp)))
        fp.SetOrientation(ori)
        fp.SetPosition(pos)
        free.append(rec)
    with open(out, "w") as f:
        json.dump(dict(outline=_polys(ps), keepouts=keepouts, fixed=fixed, free=free, pour_nets=sorted(pour_nets),
                       edge_clearance=mm(ds.m_CopperEdgeClearance), min_clearance=mm(ds.m_MinClearance),
                       layers=board.GetCopperLayerCount()), f)


def write(path, poses, dst):
    board = pcbnew.LoadBoard(path)
    with open(poses) as f:
        poses = json.load(f)
    for fp in board.GetFootprints():
        p = poses.get(fp.m_Uuid.AsString())
        if p is None or fp.IsLocked():
            continue
        fp.SetOrientationDegrees(p[2])
        fp.SetPosition(pcbnew.VECTOR2I(round(p[0] * NM), round(p[1] * NM)))
    board.Save(dst)


def unconnected(path):
    board = pcbnew.LoadBoard(path)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    vias = 0
    length = 0.0
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias += 1
        else:
            length += mm(t.GetLength())
    conn = board.GetConnectivity()
    # unrouted nets: pads of one net that copper does not join, as clusters of footprint refs
    by_net = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() > 0:
                by_net.setdefault(p.GetNetname(), []).append(p)
    failed = {}
    for net, pads in by_net.items():
        seen, clusters = set(), []
        for p in pads:
            if p.m_Uuid.AsString() in seen:
                continue
            group = [p] + [q for q in conn.GetConnectedItems(p)
                           if type(q).__name__ == "PAD" and q.GetNetname() == net]
            seen.update(q.m_Uuid.AsString() for q in group)
            clusters.append(sorted({q.GetParentFootprint().GetReference() for q in group}))
        if len(clusters) > 1:
            failed[net] = clusters
    print(json.dumps(dict(unconnected=conn.GetUnconnectedCount(False), vias=vias,
                          length_mm=round(length, 3), failed=failed)))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "extract":
        extract(sys.argv[2], sys.argv[3])
    elif cmd == "write":
        write(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "unconnected":
        unconnected(sys.argv[2])
