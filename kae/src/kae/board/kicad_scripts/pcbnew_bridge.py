# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""pcbnew side of kae.board.pcbnew_io. Runs under KiCad's own Python (stdlib + pcbnew
only), in a separate process from kae. Every operation writes its JSON result to OUT
and prints one status line ({"ok": ...}) on stdout.

    python pcbnew_bridge.py extract BOARD OUT [--no-courtyards] [--no-outline]
    python pcbnew_bridge.py write-poses BOARD POSES OUT_JSON DEST [--allow-locked]
    python pcbnew_bridge.py resave BOARD OUT_JSON DEST
    python pcbnew_bridge.py export-dsn BOARD DSN OUT_JSON [--no-probes]
    python pcbnew_bridge.py import-ses BOARD SES OUT_JSON DEST
    python pcbnew_bridge.py edit-routing BOARD EDITS OUT_JSON DEST
    python pcbnew_bridge.py zone-fills BOARD OUT_JSON

export-dsn: KiCad's Specctra export of BOARD (loaded with its project, so net classes and
the .kicad_dru rules are active), plus what the DSN leaves out, as JSON (see route_info):
design settings, net classes, every pad with its DSN pin id, copper polygons, hole, local
clearances, mask expansion and zone connection; copper graphics and texts, solder-mask
openings drawn as graphics, Edge.Cuts and Margin shapes, zones and rule areas; and KiCad's own rule engine evaluated on probe tracks
and vias of every net on every copper layer (width, via diameter and drill as min/opt/max,
own clearance, annular ring).

import-ses: KiCad's Specctra session import into BOARD (unlocked routing is replaced,
locked routing kept), written to DEST with the plain writer.

edit-routing: EDITS is JSON {delete: [uuid], width: {uuid: mm}, add: [{net, layer, a, b,
width}], lock_all: bool, unlock_all: bool, keep_locked: [uuid]}; applied to BOARD's tracks
and vias (added tracks are locked with lock_all; unlock_all leaves keep_locked locked),
written to DEST with the plain writer.

zone-fills: every zone of BOARD (loaded with its project) refilled as kicad-cli's DRC does
with --refill-zones, and its filled copper per copper layer as polygons with holes.

extract: pcbnew's own footprint poses, pads (absolute and footprint-relative), courtyards
(F/B.CrtYd caches), the board outline (GetBoardPolygonOutlines), design rules, net classes
and layers. Lengths in mm, angles in degrees as pcbnew reports them.

write-poses: POSES is a JSON list of {uuid or ref, x, y, rot, side}; a reference must
name exactly one footprint, and unknown, ambiguous or locked footprints fail the whole
call (unless --allow-locked) before anything is written. A side change uses
FOOTPRINT::Flip (left-right, about the footprint's own position); then SetOrientation
and SetPosition. Nothing else is touched: the board is read and written with KiCad's
plain S-expression reader and writer (PCB_IO_MGR.Load/Save). pcbnew.LoadBoard and
SaveBoard build connectivity, which gives copper overlapping a pad that pad's net. The
file is written to a temporary directory and moved to DEST, so no project file is written.
"""
import ctypes
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


_WARM = []


def _warm_up():
    """pcbnew.LoadBoard sets up what KiCad's reader needs (wx image handlers for embedded
    images); without that, PCB_IO_MGR.Load aborts the whole process on a board with an
    image ("Failed to read image data"). Loading a minimal board once is enough (~5 ms)."""
    if _WARM:
        return
    d = tempfile.mkdtemp(prefix="kae-warm-")
    try:
        p = os.path.join(d, "warm.kicad_pcb")
        with open(p, "w") as f:
            f.write('(kicad_pcb (version 20240108) (generator "pcbnew") (generator_version "8.0"))\n')
        pcbnew.LoadBoard(p)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    _WARM.append(True)


def _load_plain(path):
    """The board as KiCad's S-expression reader returns it, with no project and no
    connectivity. pcbnew.LoadBoard builds connectivity, which gives copper overlapping a
    pad that pad's net, and a writer must not carry that into its output."""
    if hasattr(pcbnew, "PCB_IO_MGR") and hasattr(pcbnew.PCB_IO_MGR, "KICAD_SEXP"):
        _warm_up()
        board = pcbnew.PCB_IO_MGR.Load(pcbnew.PCB_IO_MGR.KICAD_SEXP, path)
        if board is not None:
            return board
    return _load(path)


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
    """Write the board with KiCad's plain S-expression writer. pcbnew.SaveBoard first
    rebuilds connectivity, which gives copper under a moved pad that pad's net (a GND
    track became Net-(U1B-K) in a test); PCB_IO_MGR.Save writes the board as it is.
    The file goes to a temporary directory first, so no project file is written."""
    d = tempfile.mkdtemp(prefix="kae-save-")
    try:
        tmp = os.path.join(d, os.path.basename(dest))
        if hasattr(pcbnew, "PCB_IO_MGR") and hasattr(pcbnew.PCB_IO_MGR, "KICAD_SEXP"):
            pcbnew.PCB_IO_MGR.Save(pcbnew.PCB_IO_MGR.KICAD_SEXP, tmp, board)
        elif not pcbnew.SaveBoard(tmp, board, True):
            raise RuntimeError(f"could not save {dest}")
        shutil.move(tmp, dest)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def write_poses(path, poses_path, out, dest, allow_locked=False):
    with open(poses_path) as f:
        poses = json.load(f)
    board = _load_plain(path)
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
    _save(_load_plain(path), dest)
    _write(out, dict(ok=True, path=dest))
    _status(dict(ok=True))


# ----------------------------------------------------------------------------- routing
# Used by kae.route: the Specctra round trip and what the DSN cannot carry. Lengths in mm,
# board coordinates (y down), polygons as lists of rings.

class _MinOptMax(ctypes.Structure):
    """KiCad's MINOPTMAX<int> (libs/core/include/core/minoptmax.h): SWIG returns it as an
    unwrapped pointer, so its fields are read in place."""
    _fields_ = [("is_null", ctypes.c_bool), ("min", ctypes.c_int), ("opt", ctypes.c_int),
                ("max", ctypes.c_int), ("has_min", ctypes.c_bool), ("has_opt", ctypes.c_bool),
                ("has_max", ctypes.c_bool)]


def _mom(obj):
    """[min, opt, max] in mm (None where unset) of a MINOPTMAX<int> returned by SWIG."""
    try:
        m = _MinOptMax.from_address(int(obj))
    except (TypeError, ValueError):
        return None
    if m.is_null:
        return [None, None, None]
    return [_mm(m.min) if m.has_min else None, _mm(m.opt) if m.has_opt else None,
            _mm(m.max) if m.has_max else None]


def _xy(p):
    return [_mm(p.x), _mm(p.y)]


def _item_poly(item, layer, max_error, clearance=0):
    ps = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(ps, layer, int(clearance), int(max_error), pcbnew.ERROR_OUTSIDE)
    ps.Simplify()
    return _polyset(ps)


def _component_ids(board):
    """KiCad's DSN component ids (specctra_export.cpp FromBOARD): the reference, REF** when
    empty, uniquified case-insensitively with _1, _2 ... in footprint order."""
    used, out = set(), []
    for fp in board.GetFootprints():
        ref = fp.GetReference() or "REF**"
        unique, k = ref, 0
        while unique.lower() in used:
            k += 1
            unique = f"{ref}_{k}"
        used.add(unique.lower())
        out.append(unique)
    return out


def _is_round_keepout(pad):
    """specctra_export.cpp isRoundKeepout: a circular pad whose drill fills it, or without
    copper, is exported as a round keepout instead of a pin."""
    al = pcbnew.PADSTACK.ALL_LAYERS
    if pad.GetShape(al) == pcbnew.PAD_SHAPE_CIRCLE:
        if pad.GetDrillSize().x >= pad.GetSize(al).x:
            return True
        if not _has_copper(pad):
            return True
    return False


def _has_copper(pad):
    return any(pcbnew.IsCopperLayer(l) for l in pad.GetLayerSet().Seq())


def _pin_ids(fp):
    """DSN pin id per pad (None for pads that are not pins), as makeIMAGE names them:
    the pad number, with @1, @2 ... appended to repeats within the footprint."""
    pinmap, out = {}, []
    for pad in fp.Pads():
        if _is_round_keepout(pad) or not _has_copper(pad):
            out.append(None)
            continue
        num = pad.GetNumber()
        if num != "" and num not in pinmap:
            pinmap[num] = 0
            out.append(num)
        else:
            pinmap[num] = pinmap.get(num, 0) + 1
            out.append(f"{num}@{pinmap[num]}")
    return out


_ZC = {-1: "inherited", 0: "none", 1: "thermal", 2: "full"}


def _design_settings(board):
    ds = board.GetDesignSettings()
    out = {}
    for key, attr in (("min_clearance", "m_MinClearance"), ("min_track", "m_TrackMinWidth"),
                      ("min_conn", "m_MinConn"), ("min_via", "m_ViasMinSize"),
                      ("min_annular", "m_ViasMinAnnularWidth"), ("min_drill", "m_MinThroughDrill"),
                      ("min_uvia", "m_MicroViasMinSize"), ("min_uvia_drill", "m_MicroViasMinDrill"),
                      ("hole_clearance", "m_HoleClearance"), ("hole_to_hole", "m_HoleToHoleMin"),
                      ("edge_clearance", "m_CopperEdgeClearance"), ("mask_expansion", "m_SolderMaskExpansion"),
                      ("mask_min_web", "m_SolderMaskMinWidth"), ("mask_to_copper", "m_SolderMaskToCopperClearance"),
                      ("max_error", "m_MaxError"), ("zone_clearance", "m_ZoneClearance"),
                      ("zone_min_thickness", "m_ZoneMinThickness"), ("thermal_spoke", "m_ThermalReliefSpokeWidth")):
        if hasattr(ds, attr):
            out[key] = _mm(getattr(ds, attr))
    for key, attr in (("min_resolved_spokes", "m_MinResolvedSpokes"),
                      ("allow_mask_bridges_in_fps", "m_AllowSoldermaskBridgesInFPs"),
                      ("tent_vias_front", "m_TentViasFront"), ("tent_vias_back", "m_TentViasBack")):
        if hasattr(ds, attr):
            v = getattr(ds, attr)
            out[key] = bool(v) if isinstance(v, bool) else int(v)
    return out


def _netclasses(board):
    """Effective net classes by name (composites such as 'HS,Default' included); a net's
    NETINFO_ITEM.GetNetClass() comes back unwrapped from SWIG, NET_SETTINGS' does not."""
    out = {}
    ns = board.GetDesignSettings().m_NetSettings
    for code, net in board.GetNetInfo().NetsByNetcode().items():
        name = net.GetNetClassName()
        if name in out:
            continue
        nc = ns.GetEffectiveNetClass(net.GetNetname()) if net.GetNetname() else ns.GetDefaultNetclass()
        # GetConstituentNetclasses() comes back unwrapped from SWIG; a composite class is
        # named by joining its constituents with ',' (see transform-math-pitfalls.md)
        rec = dict(constituents=[c for c in name.split(",") if c])
        for key, has, get in (("clearance", "HasClearance", "GetClearance"),
                              ("track_width", "HasTrackWidth", "GetTrackWidth"),
                              ("via_diameter", "HasViaDiameter", "GetViaDiameter"),
                              ("via_drill", "HasViaDrill", "GetViaDrill"),
                              ("uvia_diameter", "HasuViaDiameter", "GetuViaDiameter"),
                              ("uvia_drill", "HasuViaDrill", "GetuViaDrill"),
                              ("dp_width", "HasDiffPairWidth", "GetDiffPairWidth"),
                              ("dp_gap", "HasDiffPairGap", "GetDiffPairGap")):
            try:
                rec[key] = _mm(getattr(nc, get)()) if getattr(nc, has)() else None
            except AttributeError:
                rec[key] = None
        out[name] = rec
    return out


_PAD_PROPS = None


def _pad_prop(pad):
    """The pad's fabrication property as the rule language names it (ENUM_MAP<PAD_PROP>)."""
    global _PAD_PROPS
    if _PAD_PROPS is None:
        names = (("NONE", "None"), ("BGA", "BGA pad"), ("FIDUCIAL_GLBL", "Fiducial, global to board"),
                 ("FIDUCIAL_LOCAL", "Fiducial, local to footprint"), ("TESTPOINT", "Test point pad"),
                 ("HEATSINK", "Heatsink pad"), ("CASTELLATED", "Castellated pad"),
                 ("MECHANICAL", "Mechanical pad"), ("PRESSFIT", "Press-fit pad"))
        _PAD_PROPS = {getattr(pcbnew, "PAD_PROP_" + k): v for k, v in names if hasattr(pcbnew, "PAD_PROP_" + k)}
    try:
        return _PAD_PROPS.get(int(pad.GetProperty()), "None")
    except Exception:
        return "None"


def _hole(pad):
    if not pad.HasHole():
        return None
    hs = pad.GetEffectiveHoleShape()
    seg = hs.GetSeg()
    return dict(a=_xy(seg.A), b=_xy(seg.B), width=_mm(hs.GetWidth()),
                plated=pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH)


def _pads(board, cu, max_error, comp_ids):
    out = []
    ds = board.GetDesignSettings()
    for fi, fp in enumerate(board.GetFootprints()):
        pins = _pin_ids(fp)
        fp_rec = dict(ref=fp.GetReference(), comp=comp_ids[fi], fp_index=fi, lib=fp.GetFPIDAsString(),
                      fp_clearance=None, allow_bridges=False, net_tie=False)
        lc = fp.GetLocalClearance()
        fp_rec["fp_clearance"] = None if lc is None else _mm(lc)
        if hasattr(fp, "AllowSolderMaskBridges"):
            fp_rec["allow_bridges"] = bool(fp.AllowSolderMaskBridges())
        if hasattr(fp, "IsNetTie"):
            fp_rec["net_tie"] = bool(fp.IsNetTie())
        for pad, pin in zip(fp.Pads(), pins):
            layers = [board.GetStandardLayerName(l) for l in cu if pad.IsOnLayer(l) and pad.FlashLayer(l)]
            polys = {}
            shapes = set()
            for l in cu:
                if pad.IsOnLayer(l) and pad.FlashLayer(l):
                    rings = _item_poly(pad, l, max_error)
                    key = json.dumps(rings)
                    polys[board.GetStandardLayerName(l)] = rings
                    shapes.add(key)
            rec = dict(fp_rec, number=pad.GetNumber(), pin=pin, net=pad.GetNetname(), uuid=pad.m_Uuid.AsString(),
                       attr={pcbnew.PAD_ATTRIB_PTH: "pth", pcbnew.PAD_ATTRIB_SMD: "smd",
                             pcbnew.PAD_ATTRIB_CONN: "conn", pcbnew.PAD_ATTRIB_NPTH: "npth"}.get(pad.GetAttribute(), "?"),
                       pos=_xy(pad.GetPosition()), layers=layers, hole=_hole(pad),
                       local_clearance=None if pad.GetLocalClearance() is None else _mm(pad.GetLocalClearance()),
                       override=None if pad.GetClearanceOverrides(None) is None else _mm(pad.GetClearanceOverrides(None)),
                       own_clearance={board.GetStandardLayerName(l): _mm(pad.GetOwnClearance(l)) for l in cu
                                      if pad.IsOnLayer(l)},
                       mask={}, zone_connection=_ZC.get(int(pad.GetZoneConnectionOverrides(None)), "inherited"),
                       thermal_gap=None, spoke_width=None, spoke_angle=pad.GetThermalSpokeAngleDegrees(),
                       round_keepout=_is_round_keepout(pad), fab=_pad_prop(pad),
                       drilled=bool(pad.HasHole() and pad.GetDrillSizeX() == pad.GetDrillSizeY()))
            if len(shapes) == 1 and polys:
                rec["poly"] = next(iter(polys.values()))
            else:
                rec["poly_by_layer"] = polys
            for side, ml in (("F", pcbnew.F_Mask), ("B", pcbnew.B_Mask)):
                if pad.IsOnLayer(ml):
                    rec["mask"][side] = _mm(pad.GetSolderMaskExpansion(ml))
            g = pad.GetLocalThermalGapOverride(None) if hasattr(pad, "GetLocalThermalGapOverride") else None
            rec["thermal_gap"] = _mm(g) if g else None
            s = pad.GetLocalSpokeWidthOverride(None) if hasattr(pad, "GetLocalSpokeWidthOverride") else None
            rec["spoke_width"] = _mm(s) if s else None
            out.append(rec)
    return out


def _graphic_rec(board, item, owner, cu, max_error):
    """A copper graphic or text: its polygon on each copper layer it is on, and its net."""
    rec = dict(cls=item.GetClass(), owner=owner, net=item.GetNetname() if hasattr(item, "GetNetname") else "",
               layers={})
    for l in cu:
        if item.IsOnLayer(l):
            try:
                rec["layers"][board.GetStandardLayerName(l)] = _item_poly(item, l, max_error)
            except Exception as e:  # odd items (images, tables) are reported, not fatal
                rec.setdefault("errors", []).append(f"{type(e).__name__}: {e}")
    return rec if rec["layers"] else None


def _edge_rec(board, shape, owner):
    """An Edge.Cuts or Margin shape as primitives (the DRC tests edges at zero width on
    Edge.Cuts and at their stroke width on Margin)."""
    t = shape.GetShape()
    rec = dict(owner=owner, layer=board.GetStandardLayerName(shape.GetLayer()), width=_mm(shape.GetWidth()))
    if t == pcbnew.SHAPE_T_SEGMENT:
        rec.update(kind="segment", pts=[_xy(shape.GetStart()), _xy(shape.GetEnd())])
    elif t == pcbnew.SHAPE_T_ARC:
        rec.update(kind="arc", pts=[_xy(shape.GetStart()), _xy(shape.GetArcMid()), _xy(shape.GetEnd())])
    elif t == pcbnew.SHAPE_T_CIRCLE:
        rec.update(kind="circle", center=_xy(shape.GetCenter()), radius=_mm(shape.GetRadius()))
    elif t == pcbnew.SHAPE_T_RECTANGLE:
        r = shape.GetCornerRadius() if hasattr(shape, "GetCornerRadius") else 0
        rec.update(kind="rect", pts=[_xy(shape.GetStart()), _xy(shape.GetEnd())], radius=_mm(r))
    elif t == pcbnew.SHAPE_T_POLY:
        rec.update(kind="poly", rings=_polyset(shape.GetPolyShape()))
    elif t == pcbnew.SHAPE_T_BEZIER:
        shape.RebuildBezierToSegmentsPointsList(int(board.GetDesignSettings().m_MaxError))
        rec.update(kind="polyline", pts=[_xy(p) for p in shape.GetBezierPoints()])
    else:
        return None
    rec["filled"] = bool(shape.IsSolidFill()) if hasattr(shape, "IsSolidFill") else False
    return rec


def _zone_rec(board, z, owner, cu, max_error):
    layers = [board.GetStandardLayerName(l) for l in cu if z.IsOnLayer(l)]
    rec = dict(owner=owner, name=z.GetZoneName(), layers=layers, rings=_polyset(z.Outline()),
               rule_area=bool(z.GetIsRuleArea()))
    if z.GetIsRuleArea():
        rec.update(no_tracks=bool(z.GetDoNotAllowTracks()), no_vias=bool(z.GetDoNotAllowVias()),
                   no_pads=bool(z.GetDoNotAllowPads()), no_fills=bool(z.GetDoNotAllowZoneFills()),
                   no_footprints=bool(z.GetDoNotAllowFootprints()))
    else:
        lc = z.GetLocalClearance()
        rec.update(net=z.GetNetname(), priority=z.GetAssignedPriority(),
                   clearance=None if lc is None else _mm(lc), min_thickness=_mm(z.GetMinThickness()),
                   pad_connection=_ZC.get(int(z.GetPadConnection()), "thermal"),
                   thermal_gap=_mm(z.GetThermalReliefGap()), spoke_width=_mm(z.GetThermalReliefSpokeWidth()),
                   teardrop=bool(z.IsTeardropArea()) if hasattr(z, "IsTeardropArea") else False)
    return rec


def _probes(board, cu):
    """KiCad's rule engine on a probe track (each net, each copper layer) and a probe through
    via (each net): what the DRC will require of routing that has no partner item."""
    out = {}
    lnames = [board.GetStandardLayerName(l) for l in cu]
    # Probes stay alive until the end: BOARD::m_ItemNetclassCache (hasExactNetclass) is keyed
    # by item address, so a freed probe's address reused by the next one would inherit its
    # net class. Probes are also placed far off the board so area conditions do not match.
    keep = []
    flag = getattr(pcbnew, "ROUTER_TRANSIENT", 0)
    far = board.GetBoardEdgesBoundingBox()
    x0, y0 = far.GetRight() + int(1000 * NM), far.GetBottom() + int(1000 * NM)
    for code, net in board.GetNetInfo().NetsByNetcode().items():
        name = net.GetNetname()
        if code <= 0 or not name:
            continue
        rec = dict(netclass=net.GetNetClassName(), track={}, via={})
        for l, ln in zip(cu, lnames):
            t = pcbnew.PCB_TRACK(board)
            keep.append(t)
            if flag:
                t.SetFlags(flag)
            t.SetLayer(l)
            t.SetNet(net)
            t.SetWidth(100000)
            t.SetStart(pcbnew.VECTOR2I(x0, y0))
            t.SetEnd(pcbnew.VECTOR2I(x0 + 100000, y0))
            rec["track"][ln] = dict(width=_mom(t.GetWidthConstraint()), clearance=_mm(t.GetOwnClearance(l)))
        v = pcbnew.PCB_VIA(board)
        keep.append(v)
        if flag:
            v.SetFlags(flag)
        v.SetPosition(pcbnew.VECTOR2I(x0, y0))
        v.SetNet(net)
        v.SetLayerPair(cu[0], cu[-1])
        v.SetWidth(400000)
        v.SetDrill(200000)
        rec["via"] = dict(diameter=_mom(v.GetWidthConstraint()), drill=_mom(v.GetDrillConstraint()),
                          clearance={ln: _mm(v.GetOwnClearance(l)) for l, ln in zip(cu, lnames)},
                          annulus={ln: _mm(v.GetMinAnnulus(l, None)) for l, ln in zip(cu, lnames)})
        out[name] = rec
    return out


def route_info(board, probes=True):
    cu = list(board.GetEnabledLayers().CuStack())
    max_error = board.GetDesignSettings().m_MaxError
    comp_ids = _component_ids(board)
    info = dict(kicad_version=pcbnew.Version(), copper=[board.GetStandardLayerName(l) for l in cu],
                layer_types={board.GetStandardLayerName(l): int(board.GetLayerType(l)) for l in cu},
                settings=_design_settings(board), netclasses=_netclasses(board))
    nets = {}
    for code, net in board.GetNetInfo().NetsByNetcode().items():
        if code > 0 and net.GetNetname():
            nets[net.GetNetname()] = dict(code=code, netclass=net.GetNetClassName())
    info["nets"] = nets
    info["pads"] = _pads(board, cu, max_error, comp_ids)
    graphics, edges, masks = [], [], []
    edge_layers = (pcbnew.Edge_Cuts, pcbnew.Margin)
    mask_layers = {pcbnew.F_Mask: "F.Mask", pcbnew.B_Mask: "B.Mask"}

    def mask_recs(item, owner):  # solder-mask openings drawn as graphics
        for l, name in mask_layers.items():
            if item.IsOnLayer(l):
                try:
                    polys = _item_poly(item, l, max_error)
                except Exception:  # odd items (images, tables)
                    continue
                if polys:
                    masks.append(dict(layer=name, owner=owner, cls=item.GetClass(), polys=polys))

    for d in board.GetDrawings():
        mask_recs(d, "")
        if d.GetClass() == "PCB_SHAPE" and d.GetLayer() in edge_layers:
            r = _edge_rec(board, d, "")
            if r:
                edges.append(r)
        elif d.IsOnCopperLayer() if hasattr(d, "IsOnCopperLayer") else False:
            r = _graphic_rec(board, d, "", cu, max_error)
            if r:
                graphics.append(r)
    zones = [_zone_rec(board, z, "", cu, max_error) for z in board.Zones()]
    for fi, fp in enumerate(board.GetFootprints()):
        owner = comp_ids[fi]
        items = list(fp.GraphicalItems())
        if hasattr(fp, "GetFields"):
            items += [f for f in fp.GetFields() if f.IsVisible() and any(f.IsOnLayer(l) for l in cu)]
        for g in fp.GraphicalItems():
            mask_recs(g, owner)
        for g in items:
            if g.GetClass() == "PCB_SHAPE" and g.GetLayer() in edge_layers:
                r = _edge_rec(board, g, owner)
                if r:
                    edges.append(r)
            elif any(g.IsOnLayer(l) for l in cu):
                r = _graphic_rec(board, g, owner, cu, max_error)
                if r:
                    graphics.append(r)
        for z in fp.Zones():
            zones.append(_zone_rec(board, z, owner, cu, max_error))
    info["graphics"], info["edges"], info["zones"], info["mask_openings"] = graphics, edges, zones, masks
    ps = pcbnew.SHAPE_POLY_SET()
    info["outline_ok"] = bool(board.GetBoardPolygonOutlines(ps, True))
    info["outline"] = _polyset(ps)
    info["tracks"] = sum(1 for t in board.GetTracks())
    info["probes"] = _probes(board, cu) if probes else {}
    return info


def export_dsn(path, dsn, out, probes=True):
    board = _load(path)
    ok = pcbnew.ExportSpecctraDSN(board, dsn)
    if ok is not True:
        raise RuntimeError("ExportSpecctraDSN failed")
    info = route_info(board, probes=probes)
    _write(out, dict(ok=True, path=path, dsn=dsn, **info))
    _status(dict(ok=True, pads=len(info["pads"])))


def _routing(board):
    """Every track, arc and via: uuid, kind, net, layer(s), width or size, lock state."""
    out = []
    for t in board.GetTracks():
        cls = t.GetClass()
        rec = dict(uuid=t.m_Uuid.AsString(), net=t.GetNetname(), locked=bool(t.IsLocked()))
        if cls == "PCB_VIA":
            rec.update(kind="via", pos=_xy(t.GetPosition()), size=_mm(t.GetWidth(pcbnew.F_Cu)),
                       drill=_mm(t.GetDrillValue()))
        else:
            rec.update(kind="arc" if cls == "PCB_ARC" else "track", layer=board.GetStandardLayerName(t.GetLayer()),
                       width=_mm(t.GetWidth()), a=_xy(t.GetStart()), b=_xy(t.GetEnd()))
        out.append(rec)
    return out


def import_ses(path, ses, out, dest):
    board = _load(path)
    ok = pcbnew.ImportSpecctraSES(board, ses)
    if ok is not True:
        raise RuntimeError("ImportSpecctraSES failed")
    routing = _routing(board)
    _save(board, dest)
    _write(out, dict(ok=True, path=dest, routing=routing))
    _status(dict(ok=True, routing=len(routing)))


def edit_routing(path, edits_path, out, dest):
    with open(edits_path) as f:
        edits = json.load(f)
    board = _load_plain(path)
    delete = set(edits.get("delete") or [])
    widths = edits.get("width") or {}
    keep_locked = set(edits.get("keep_locked") or [])
    removed = widened = 0
    keep = []
    for t in list(board.GetTracks()):
        u = t.m_Uuid.AsString()
        if u in delete:
            keep.append(t)
            continue
        if u in widths and t.GetClass() != "PCB_VIA":
            t.SetWidth(int(round(float(widths[u]) * NM)))
            widened += 1
        if edits.get("lock_all"):
            t.SetLocked(True)
        elif edits.get("unlock_all") and u not in keep_locked:
            t.SetLocked(False)
    for t in keep:  # remove after iterating: Remove() untypes SWIG objects
        board.Remove(t)
        removed += 1
    added = 0
    for a in edits.get("add") or []:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(int(round(a["a"][0] * NM)), int(round(a["a"][1] * NM))))
        t.SetEnd(pcbnew.VECTOR2I(int(round(a["b"][0] * NM)), int(round(a["b"][1] * NM))))
        t.SetWidth(int(round(float(a["width"]) * NM)))
        t.SetLayer(board.GetLayerID(a["layer"]))
        net = board.FindNet(a["net"])
        if net is not None:
            t.SetNet(net)
        if edits.get("lock_all"):
            t.SetLocked(True)
        board.Add(t)
        added += 1
    routing = _routing(board)
    _save(board, dest)
    _write(out, dict(ok=True, path=dest, removed=removed, widened=widened, added=added, routing=routing))
    _status(dict(ok=True, removed=removed, widened=widened, added=added))


def zone_fills(path, out):
    board = _load(path)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    cu = list(board.GetEnabledLayers().CuStack())
    zones = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        layers = {}
        for l in cu:
            if not z.IsOnLayer(l):
                continue
            ps = pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(l))  # a copy: unfracture it
            ps.Unfracture()
            layers[board.GetStandardLayerName(l)] = _polyset(ps)
        lc = z.GetLocalClearance()
        zones.append(dict(uuid=z.m_Uuid.AsString(), net=z.GetNetname(), name=z.GetZoneName(),
                          priority=z.GetAssignedPriority(), layers=layers,
                          clearance=None if lc is None else _mm(lc),
                          teardrop=bool(z.IsTeardropArea()) if hasattr(z, "IsTeardropArea") else False))
    _write(out, dict(ok=True, zones=zones))
    _status(dict(ok=True, zones=len(zones)))


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
        elif op == "export-dsn":
            export_dsn(args[0], args[1], args[2], probes="--no-probes" not in flags)
        elif op == "import-ses":
            import_ses(args[0], args[1], args[2], args[3])
        elif op == "edit-routing":
            edit_routing(args[0], args[1], args[2], args[3])
        elif op == "zone-fills":
            zone_fills(args[0], args[1])
        else:
            raise SystemExit(f"unknown op {op}")
    except Exception as e:  # report failures as JSON
        _status(dict(ok=False, op=op, error=f"{type(e).__name__}: {e}"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
