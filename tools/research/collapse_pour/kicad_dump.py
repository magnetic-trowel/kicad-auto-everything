# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""KiCad side of the pour lab. Runs under KiCad's Python (needs pcbnew).

    python3 kicad_dump.py dump BOARD OUT.json [--refill]
    python3 kicad_dump.py write BOARD ZONES.json OUT_BOARD

dump: board-frame geometry for pour experiments: outline, every copper item (pads,
tracks, arcs, vias, copper drawings) as polygons per copper layer with its net, NPTH
holes, keep-out areas, and zones (net, layers, priority, settings, outline and filled
polygons per layer). --refill runs the zone filler first.

write: replace the zones listed in ZONES.json ({"replace": [[net, layer_name], ...],
"zones": [{net, layer, template: [net, layer], polys: [[outer, hole, ...], ...]}]}).
Each new zone clones the settings of the human zone named by `template`, gets the new
outline, and is filled; the board is saved to OUT_BOARD.
"""
import json
import os
import sys

_JSON_OUT = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)
import pcbnew  # noqa: E402

NM = 1e6
ERR = int(0.005 * NM)


def mm(v):
    return v / NM


def chain(c):
    return [[mm(c.CPoint(j).x), mm(c.CPoint(j).y)] for j in range(c.PointCount())]


def polys(sps):
    """SHAPE_POLY_SET -> [[outer, hole, ...], ...] in mm."""
    sps = sps.CloneDropTriangulation() if hasattr(sps, "CloneDropTriangulation") else sps
    try:
        sps.Unfracture()
    except Exception:
        pass
    out = []
    for i in range(sps.OutlineCount()):
        rings = [chain(sps.Outline(i))]
        for h in range(sps.HoleCount(i)):
            rings.append(chain(sps.CHole(i, h)))
        out.append(rings)
    return out


def item_poly(it, layer):
    sp = pcbnew.SHAPE_POLY_SET()
    it.TransformShapeToPolygon(sp, layer, 0, ERR, pcbnew.ERROR_INSIDE)
    return polys(sp)


def circle(c, r, n=16):
    import math
    return [[[mm(c.x + r * math.cos(2 * math.pi * k / n)), mm(c.y + r * math.sin(2 * math.pi * k / n))]
             for k in range(n)]]


def dump(path, out, refill=False):
    board = pcbnew.LoadBoard(path)
    if refill:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    cu = list(board.GetEnabledLayers().CuStack())
    lname = {l: board.GetLayerName(l) for l in cu}
    ds = board.GetDesignSettings()
    ns = ds.m_NetSettings
    netcl = {}
    for code, n in board.GetNetInfo().NetsByNetcode().items():
        if code <= 0:
            continue
        try:
            nc = ns.GetEffectiveNetClass(n.GetNetname())
            netcl[n.GetNetname()] = mm(nc.GetClearance())
        except Exception:
            netcl[n.GetNetname()] = mm(ns.GetDefaultNetclass().GetClearance())
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, True)
    items, holes = [], []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            net = p.GetNetname()
            if p.GetDrillSize().x > 0:
                holes.append(dict(x=mm(p.GetPosition().x), y=mm(p.GetPosition().y),
                                  d=mm(max(p.GetDrillSize().x, p.GetDrillSize().y)),
                                  plated=p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH))
            for l in cu:
                if not p.IsOnLayer(l):
                    continue
                pp = item_poly(p, l)
                if not pp and p.GetDrillSize().x > 0:  # unflashed PTH layer: annulus may be
                    pp = circle(p.GetPosition(), max(p.GetDrillSize().x, p.GetDrillSize().y) / 2 + 0.1 * NM)
                if not pp:
                    continue
                items.append(dict(kind="pad", net=net, layer=lname[l], poly=pp,
                                  ref=fp.GetReference(), pad=p.GetNumber(),
                                  x=mm(p.GetPosition().x), y=mm(p.GetPosition().y)))
    for t in board.GetTracks():
        net = t.GetNetname()
        if t.GetClass() == "PCB_VIA":
            holes.append(dict(x=mm(t.GetPosition().x), y=mm(t.GetPosition().y),
                              d=mm(t.GetDrillValue()), plated=True))
            for l in cu:
                if not t.IsOnLayer(l):
                    continue
                # unflashed layers (unused annular rings removed) still count: a zone of
                # the via's net that reaches it gets a ring (KiCad flashes it again)
                pp = item_poly(t, l) or circle(t.GetPosition(), t.GetWidth(pcbnew.F_Cu) / 2
                                               if hasattr(t, "GetWidth") else t.GetDrillValue())
                items.append(dict(kind="via", net=net, layer=lname[l], poly=pp,
                                  x=mm(t.GetPosition().x), y=mm(t.GetPosition().y)))
        else:
            items.append(dict(kind="track", net=net, layer=lname[t.GetLayer()],
                              poly=item_poly(t, t.GetLayer())))
    for d in board.GetDrawings():
        if d.GetClass() == "PCB_SHAPE" and pcbnew.IsCopperLayer(d.GetLayer()):
            items.append(dict(kind="shape", net=d.GetNetname(), layer=lname[d.GetLayer()],
                              poly=item_poly(d, d.GetLayer())))
    zones, keepouts = [], []
    for z in board.Zones():
        zl = [l for l in z.GetLayerSet().CuStack() if l in lname]
        if z.GetIsRuleArea():
            keepouts.append(dict(layers=[lname[l] for l in zl], tracks=z.GetDoNotAllowTracks(),
                                 vias=z.GetDoNotAllowVias(), zones=z.GetDoNotAllowZoneFills(),
                                 poly=polys(z.Outline())))
            continue
        fills = {}
        for l in zl:
            fills[lname[l]] = polys(z.GetFilledPolysList(l)) if z.HasFilledPolysForLayer(l) else []
        lc = z.GetLocalClearance()
        lc = mm(lc.value()) if hasattr(lc, "value") and lc.has_value() else (
            mm(lc) if isinstance(lc, int) else None)
        zones.append(dict(net=z.GetNetname(), layers=[lname[l] for l in zl],
                          priority=z.GetAssignedPriority(), name=z.GetZoneName(),
                          clearance=lc, min_width=mm(z.GetMinThickness()),
                          pad_conn=int(z.GetPadConnection()),
                          outline=polys(z.Outline()), fills=fills))
    data = dict(path=path, layers=[lname[l] for l in cu], outline=polys(outline),
                bbox=[mm(v) for v in (board.GetBoardEdgesBoundingBox().GetLeft(),
                                      board.GetBoardEdgesBoundingBox().GetTop(),
                                      board.GetBoardEdgesBoundingBox().GetRight(),
                                      board.GetBoardEdgesBoundingBox().GetBottom())],
                rules=dict(min_clearance=mm(ds.m_MinClearance),
                           edge_clearance=mm(ds.m_CopperEdgeClearance),
                           hole_clearance=mm(ds.m_HoleClearance)),
                netclass_clearance=netcl, items=items, holes=holes, zones=zones,
                keepouts=keepouts)
    with open(out, "w") as f:
        json.dump(data, f)
    _JSON_OUT.write(json.dumps(dict(ok=True, items=len(items), zones=len(zones))) + "\n")


def write(path, spec_path, out):
    board = pcbnew.LoadBoard(path)
    spec = json.load(open(spec_path))
    lid = {board.GetLayerName(l): l for l in board.GetEnabledLayers().CuStack()}
    replace = {(n, l) for n, l in spec["replace"]}
    templates = {}
    for z in list(board.Zones()):
        if z.GetIsRuleArea():
            continue
        names = [board.GetLayerName(l) for l in z.GetLayerSet().CuStack()]
        for ln in names:
            if (z.GetNetname(), ln) not in templates:
                templates[(z.GetNetname(), ln)] = pcbnew.ZONE(z)  # copy of the settings
        hit = [ln for ln in names if (z.GetNetname(), ln) in replace]
        if not hit:
            continue
        keep = [ln for ln in names if (z.GetNetname(), ln) not in replace]
        if keep:  # multi-layer zone: keep it on the layers we do not replace
            ls = pcbnew.LSET()
            for ln in keep:
                ls.AddLayer(lid[ln])
            z.SetLayerSet(ls)
        else:
            board.Remove(z)
    nets = board.GetNetInfo()
    new = []
    for zs in spec["zones"]:
        z = templates[tuple(zs["template"])]
        z = pcbnew.ZONE(z)
        ls = pcbnew.LSET()
        ls.AddLayer(lid[zs["layer"]])
        z.SetLayerSet(ls)
        z.SetNet(nets.GetNetItem(zs["net"]))
        z.SetZoneName("mbo")
        ol = z.Outline()
        ol.RemoveAllContours()
        for rings in zs["polys"]:
            for k, ring in enumerate(rings):
                ch = pcbnew.SHAPE_LINE_CHAIN()
                for x, y in ring:
                    ch.Append(int(round(x * NM)), int(round(y * NM)))
                ch.SetClosed(True)
                if k == 0:
                    ol.AddOutline(ch)
                else:
                    ol.AddHole(ch, ol.OutlineCount() - 1)
        board.Add(z)
        new.append(z)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(out, board)
    _JSON_OUT.write(json.dumps(dict(ok=True, zones=len(new))) + "\n")


if __name__ == "__main__":
    op = sys.argv[1]
    if op == "dump":
        dump(sys.argv[2], sys.argv[3], "--refill" in sys.argv)
    elif op == "write":
        write(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit(__doc__)
