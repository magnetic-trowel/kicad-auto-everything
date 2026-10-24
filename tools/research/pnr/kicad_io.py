# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""KiCad side of the pnr lab. Runs under KiCad's Python (needs pcbnew).

    python3 kicad_io.py extract BOARD OUT.json
    python3 kicad_io.py apply BOARD RESULT.json OUT_BOARD

extract: board outline, rules, nets (with netclass width/clearance), footprints with
pad and courtyard polygons in the footprint frame (orientation 0, origin at the
footprint position), keep-out areas. A self-check re-derives every pad centre from the
local geometry and the footprint pose (KiCad rotation convention) and reports the error.

apply: set footprint poses and add tracks/vias from RESULT.json, then save.
"""
import json
import math
import os
import sys

_JSON_OUT = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)
import pcbnew  # noqa: E402

NM = 1e6


def mm(v):
    return v / NM


def poly_points(sps):
    """SHAPE_POLY_SET -> list of outlines (each a list of [x, y] mm); holes dropped."""
    out = []
    for i in range(sps.OutlineCount()):
        o = sps.Outline(i)
        out.append([[mm(o.CPoint(j).x), mm(o.CPoint(j).y)] for j in range(o.PointCount())])
    return out


def poly_holes(sps):
    """SHAPE_POLY_SET -> holes per outline (each a list of rings), parallel to poly_points."""
    return [[[[mm(h.CPoint(j).x), mm(h.CPoint(j).y)] for j in range(h.PointCount())]
             for h in (sps.CHole(i, k) for k in range(sps.HoleCount(i)))]
            for i in range(sps.OutlineCount())]


def cu_shape(item, layer):
    """A copper drawing (line, arc, circle, rectangle, polygon) as polygons with holes:
    an unfilled circle or rectangle is a ring, not a disc."""
    sp = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(sp, layer, 0, int(0.005 * NM), pcbnew.ERROR_OUTSIDE)
    try:
        sp.Simplify()  # KiCad 9+
    except TypeError:
        sp.Simplify(pcbnew.SHAPE_POLY_SET.PM_FAST)
    return dict(net=item.GetNetname() if hasattr(item, "GetNetname") else "", layer=layer,
                poly=poly_points(sp), holes=poly_holes(sp))


def rot(x, y, deg):
    # KiCad: y axis points down, positive orientation is counter-clockwise on screen
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return x * c + y * s, -x * s + y * c


def netclass_of(ns, name):
    try:
        nc = ns.GetEffectiveNetClass(name)
        return dict(clearance=mm(nc.GetClearance()), width=mm(nc.GetTrackWidth()),
                    via_d=mm(nc.GetViaDiameter()), via_drill=mm(nc.GetViaDrill()))
    except Exception:
        return None


def dru_edge_clearances(path):
    """edge_clearance minimums (mm) of the custom rules file beside the board, if any."""
    import re
    dru = os.path.splitext(path)[0] + ".kicad_dru"
    if not os.path.exists(dru):
        return []
    text = "\n".join(l.split("#", 1)[0] for l in open(dru, errors="replace").read().splitlines())
    out = []
    for m in re.finditer(r"\(constraint\s+edge_clearance\b[^()]*\(min\s+([0-9.]+)\s*(mm|mil|in)?\s*\)", text):
        v = float(m.group(1))
        out.append(v * {"mil": 0.0254, "in": 25.4}.get(m.group(2) or "mm", 1.0))
    return out


def extract(path, out):
    board = pcbnew.LoadBoard(path)
    ds = board.GetDesignSettings()
    ns = ds.m_NetSettings
    dnc = ns.GetDefaultNetclass()
    default = dict(clearance=mm(dnc.GetClearance()), width=mm(dnc.GetTrackWidth()),
                   via_d=mm(dnc.GetViaDiameter()), via_drill=mm(dnc.GetViaDrill()))
    nets = {}
    for code, n in board.GetNetInfo().NetsByNetcode().items():
        if code <= 0:
            continue
        nets[n.GetNetname()] = netclass_of(ns, n.GetNetname()) or default
    rules = dict(min_clearance=mm(ds.m_MinClearance), min_track=mm(ds.m_TrackMinWidth),
                 min_via=mm(ds.m_ViasMinSize), hole_clearance=mm(ds.m_HoleClearance),
                 edge_clearance=mm(ds.m_CopperEdgeClearance), min_drill=mm(ds.m_MinThroughDrill),
                 hole_to_hole=mm(ds.m_HoleToHoleMin), min_annular=mm(ds.m_ViasMinAnnularWidth),
                 mask_exp=mm(ds.m_SolderMaskExpansion), mask_web=mm(ds.m_SolderMaskMinWidth))
    # custom rules (board.kicad_dru) may raise the edge clearance for some items: take the
    # largest edge_clearance minimum for every item (conservative; conditions are ignored)
    rules["edge_clearance"] = max([rules["edge_clearance"], *dru_edge_clearances(path)])
    fps = []
    worst = 0.0
    moved_edges = []
    for fp in board.GetFootprints():
        pos, deg, flipped = fp.GetPosition(), fp.GetOrientationDegrees(), fp.IsFlipped()
        actual = [(mm(p.GetCenter().x), mm(p.GetCenter().y)) for p in fp.Pads()]
        fp.SetOrientationDegrees(0)
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        pads = []
        for p in fp.Pads():
            layers = [l for l in p.GetLayerSet().CuStack()]
            cu = "both" if len(layers) > 2 else ("B" if layers == [pcbnew.B_Cu] else
                                               ("F" if layers == [pcbnew.F_Cu] else
                                                ("none" if not layers else "both")))
            lay = pcbnew.B_Cu if cu == "B" else pcbnew.F_Cu
            sp = pcbnew.SHAPE_POLY_SET()
            if layers:
                p.TransformShapeToPolygon(sp, lay, 0, int(0.005 * NM), pcbnew.ERROR_OUTSIDE)
            d = p.GetDrillSize()
            c = p.GetCenter()
            loc = [v for v in (p.GetLocalClearance(), fp.GetLocalClearance()) if v is not None]
            pads.append(dict(num=p.GetNumber(), net=p.GetNetname(), cu=cu, x=mm(c.x), y=mm(c.y),
                             clear=mm(max(loc)) if loc else None,
                             poly=poly_points(sp), drill=[mm(d.x), mm(d.y)],
                             pth=p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
                             npth=p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH))
        # Edge.Cuts drawn inside a footprint (sensor windows, slots) move with the part.
        # Record them in the footprint frame and take them off Edge.Cuts so the board
        # outline below is the board's own.
        edges = []
        # the harness (task spec 5+) keeps footprints carrying Edge.Cuts where they are
        anchored = fp.IsLocked() or any(g.GetLayer() == pcbnew.Edge_Cuts for g in fp.GraphicalItems())
        for item in fp.GraphicalItems():
            if item.GetLayer() == pcbnew.Edge_Cuts:
                sp = pcbnew.SHAPE_POLY_SET()
                item.TransformShapeToPolygon(sp, pcbnew.Edge_Cuts, 0, int(0.005 * NM), pcbnew.ERROR_OUTSIDE)
                edges += poly_points(sp)
                item.SetLayer(pcbnew.Cmts_User)
                moved_edges.append(item)
        # copper drawings of the footprint (pad extensions, solder-jumper bridges) are copper
        # that moves with the part, like its pads
        fcu = [cu_shape(item, item.GetLayer()) for item in fp.GraphicalItems()
               if item.GetClass() == "PCB_SHAPE" and pcbnew.IsCopperLayer(item.GetLayer())]
        # rule areas drawn inside a footprint (keep-outs) move with the part
        fkos = []
        for z in fp.Zones():
            if z.GetIsRuleArea():
                fkos.append(dict(layers=[l for l in z.GetLayerSet().CuStack()],
                                 tracks=z.GetDoNotAllowTracks(), vias=z.GetDoNotAllowVias(),
                                 pads=z.GetDoNotAllowPads(), footprints=z.GetDoNotAllowFootprints(),
                                 poly=poly_points(z.Outline())))
        if hasattr(fp, "BuildCourtyardCaches"):
            fp.BuildCourtyardCaches()
        # courtyards on both sides (through-hole footprints often draw both)
        own = pcbnew.B_CrtYd if flipped else pcbnew.F_CrtYd
        other = pcbnew.F_CrtYd if flipped else pcbnew.B_CrtYd
        cy = fp.GetCourtyard(own)
        court = poly_points(cy) if cy.OutlineCount() else []
        cyo = fp.GetCourtyard(other)
        court_other = poly_points(cyo) if cyo.OutlineCount() else []
        # restore and self-check
        fp.SetPosition(pos)
        fp.SetOrientationDegrees(deg)
        for pd, (ax, ay) in zip(pads, actual):
            rx, ry = rot(pd["x"], pd["y"], deg)
            worst = max(worst, abs(rx + mm(pos.x) - ax), abs(ry + mm(pos.y) - ay))
        fps.append(dict(ref=fp.GetReference(), uuid=fp.m_Uuid.AsString(), x=mm(pos.x), y=mm(pos.y),
                        rot=deg, back=flipped, locked=fp.IsLocked(), anchored=anchored, pads=pads, courtyard=court,
                        courtyard_other=court_other,
                        edges=edges, keepouts=fkos, cu_shapes=fcu))
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    if outline.OutlineCount() == 0 and moved_edges:
        # the board outline itself is drawn inside footprints: keep it as the outline
        for item in moved_edges:
            item.SetLayer(pcbnew.Edge_Cuts)
        for f in fps:
            f["edges"] = []
        outline = pcbnew.SHAPE_POLY_SET()
        board.GetBoardPolygonOutlines(outline, False)
    holes = []
    for i in range(outline.OutlineCount()):
        for h in range(outline.HoleCount(i)):
            hh = outline.CHole(i, h)
            holes.append([[mm(hh.CPoint(j).x), mm(hh.CPoint(j).y)] for j in range(hh.PointCount())])
    keepouts = []
    for i in range(board.GetAreaCount()):
        z = board.GetArea(i)
        if not z.GetIsRuleArea():
            continue
        keepouts.append(dict(layers=[l for l in z.GetLayerSet().CuStack()],
                             tracks=z.GetDoNotAllowTracks(), vias=z.GetDoNotAllowVias(),
                             footprints=z.GetDoNotAllowFootprints(),
                             poly=poly_points(z.Outline())))
    zones = []
    for i in range(board.GetAreaCount()):
        z = board.GetArea(i)
        if z.GetIsRuleArea():
            continue
        zones.append(dict(net=z.GetNetname(), layers=[l for l in z.GetLayerSet().CuStack()],
                          poly=poly_points(z.Outline()), gap=mm(z.GetThermalReliefGap()),
                          spoke=mm(z.GetThermalReliefSpokeWidth()),
                          min_width=mm(z.GetMinThickness())))
    # board-level copper drawings (graphic lines/arcs/circles/rectangles/polygons on copper,
    # possibly with a net): fixed copper
    cu_shapes = [cu_shape(d, d.GetLayer()) for d in board.GetDrawings()
                 if d.GetClass() == "PCB_SHAPE" and pcbnew.IsCopperLayer(d.GetLayer())]
    data = dict(path=path, layers=board.GetCopperLayerCount(), outline=poly_points(outline),
                cu_shapes=cu_shapes,
                outline_holes=holes, rules=rules, default=default, nets=nets, footprints=fps,
                keepouts=keepouts, zones=zones, pose_selfcheck_mm=worst)
    with open(out, "w") as f:
        json.dump(data, f)
    _JSON_OUT.write(json.dumps(dict(ok=True, footprints=len(fps), nets=len(nets), selfcheck=worst)) + "\n")


def layer_id(board, idx, nlayers):
    # idx 0 = F.Cu, nlayers-1 = B.Cu, inner layers in between
    if idx == 0:
        return pcbnew.F_Cu
    if idx == nlayers - 1:
        return pcbnew.B_Cu
    return board.GetLayerID(f"In{idx}.Cu")


def apply(path, result, out):
    board = pcbnew.LoadBoard(path)
    res = json.load(open(result))
    n = board.GetCopperLayerCount()
    # poses are keyed by footprint index (UUIDs are not unique on some boards)
    fps = list(board.GetFootprints())
    for i, p in res.get("poses", {}).items():
        fp = fps[int(i)]
        assert fp.m_Uuid.AsString() == p["uuid"]
        fp.SetOrientationDegrees(p["rot"])
        fp.SetPosition(pcbnew.VECTOR2I(int(round(p["x"] * NM)), int(round(p["y"] * NM))))
    nets = board.GetNetInfo()
    added = 0
    for t in res.get("tracks", []):
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(pcbnew.VECTOR2I(int(round(t["x1"] * NM)), int(round(t["y1"] * NM))))
        tr.SetEnd(pcbnew.VECTOR2I(int(round(t["x2"] * NM)), int(round(t["y2"] * NM))))
        tr.SetWidth(int(round(t["w"] * NM)))
        tr.SetLayer(layer_id(board, t["layer"], n))
        tr.SetNet(nets.GetNetItem(t["net"]))
        board.Add(tr)
        added += 1
    for v in res.get("vias", []):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(int(round(v["x"] * NM)), int(round(v["y"] * NM))))
        via.SetWidth(int(round(v["d"] * NM)))
        via.SetDrill(int(round(v["drill"] * NM)))
        via.SetNet(nets.GetNetItem(v["net"]))
        board.Add(via)
    pcbnew.SaveBoard(out, board)
    _JSON_OUT.write(json.dumps(dict(ok=True, tracks=added, vias=len(res.get("vias", [])))) + "\n")


if __name__ == "__main__":
    op = sys.argv[1]
    if op == "extract":
        extract(sys.argv[2], sys.argv[3])
    elif op == "apply":
        apply(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit(__doc__)
