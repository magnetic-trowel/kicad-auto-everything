# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Board operations that need KiCad's pcbnew module.

Runs under KiCad's own Python interpreter (only stdlib + pcbnew), as a separate
process from the harness. Every operation prints one JSON object on stdout.

    python pcbnew_ops.py stats BOARD
    python pcbnew_ops.py convert IN OUT
    python pcbnew_ops.py strip-routing IN OUT [--keep-locked]
    python pcbnew_ops.py strip-placement IN OUT
    python pcbnew_ops.py classify-mech BOARD
    python pcbnew_ops.py lock-footprints IN OUT UUIDS_JSON
    python pcbnew_ops.py export-dsn IN DSN
    python pcbnew_ops.py import-ses IN SES OUT
    python pcbnew_ops.py unconnected BOARD
    python pcbnew_ops.py transplant-routing OUTPUT INPUT DEST [REFERENCE] [--zones]
    python pcbnew_ops.py transplant-placement OUTPUT INPUT DEST [REFERENCE] [--zones]
    python pcbnew_ops.py covered-micro-arcs BOARD [MAX_MM]
"""
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import uuid

# pcbnew prints wx asserts on import and SWIG prints leak warnings at exit, both
# on stdout. Keep a private handle to the real stdout for JSON and send fd 1 to
# stderr for the rest of the process.
_JSON_OUT = os.fdopen(os.dup(1), "w")
os.dup2(2, 1)
import pcbnew  # noqa: E402

try:  # A wx debug assert (e.g. GetRectangleWidth on a polygon) can SIGTRAP the process when it
    import wx  # fires off the main thread; with asserts off KiCad takes its normal release path.

    wx.DisableAsserts()
except Exception:  # noqa: BLE001 - KiCad builds without wxPython
    pass

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


def _anchored(fp):
    """A footprint that may not move in a place task: locked by the designer, or carrying
    Edge.Cuts graphics (switch cut-outs, slots, card edges), which are part of the board
    outline itself."""
    return fp.IsLocked() or any(g.GetLayer() == pcbnew.Edge_Cuts for g in fp.GraphicalItems())


def _placement(board):
    # "inside" = every pad centre lies within the board outline; "pads_outside" counts the
    # pad centres that do not (edge connectors may overhang).
    outline = pcbnew.SHAPE_POLY_SET()
    has_outline = board.GetBoardPolygonOutlines(outline, False) and outline.OutlineCount() > 0
    rows = []
    for fp in board.GetFootprints():
        p = fp.GetPosition()
        out = sum(1 for pad in fp.Pads() if not outline.Contains(pad.GetCenter())) if has_outline else None
        rows.append(dict(ref=fp.GetReference(), uuid=fp.m_Uuid.AsString(),
                         x=round(_mm(p.x), 4), y=round(_mm(p.y), 4),
                         rot=round(fp.GetOrientationDegrees() % 360.0, 3),
                         back=bool(fp.IsFlipped()), locked=bool(fp.IsLocked()),
                         anchored=bool(_anchored(fp)),
                         inside=None if out is None else out == 0, pads_outside=out))
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
                 min_clearance_mm=_mm(ds.m_MinClearance), hole_clearance_mm=_mm(ds.m_HoleClearance),
                 min_via_diameter_mm=_mm(ds.m_ViasMinSize), min_through_drill_mm=_mm(ds.m_MinThroughDrill))
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


def unconnected(path):
    """Unrouted connections counted by pcbnew's connectivity after filling zones, as DRC does
    but without DRC's report cap of 499 unconnected items."""
    board = _load(path)
    zones = pcbnew.ZONES()
    for i in range(board.GetAreaCount()):
        zones.append(pcbnew.Cast_to_ZONE(board.GetArea(i)))
    if len(zones):
        pcbnew.ZONE_FILLER(board).Fill(zones)
    board.BuildConnectivity()
    _out(dict(ok=True, path=path, unconnected=board.GetConnectivity().GetUnconnectedCount(False)))


def convert(src, dst):
    board = _load(src)
    _save(board, dst)
    n = _dedupe_uuids(dst)
    _out(dict(ok=True, path=dst, footprint_uuids_reassigned=n["footprint"],
              zone_uuids_reassigned=n["zone"]))


_OWN_UUID = re.compile(r'^\t\t\(uuid "([^"]+)"\)', re.M)


def _dedupe_uuids(path):
    """Give footprints, and zones, that share a uuid unique ones. Returns the number
    reassigned per kind. The new uuids are derived from the old, so every task built from
    the same board gets the same ones.

    Footprints: old libraries left placeholders such as all-zero uuids on logos and mounting
    holes, and everything that matches an output to its task input goes by footprint uuid.

    Zones: boards from KiCad 4 and older store `(tstamp 0)` on zones, which loads as the
    all-zero uuid. KiCad 10.0.7's zone filler breaks priority ties by uuid
    (ZONE::HigherPriority), so two overlapping zones on different nets with equal priority
    and equal uuid each wait for the other to be filled first. The dependency cycle is never
    dispatched and ZONE_FILLER::Fill polls forever at ~0% CPU: `kicad-cli pcb drc
    --refill-zones` and pcbnew's ZONE_FILLER hang instead of failing."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    seen = {"footprint": set(), "zone": set()}
    n = {"footprint": 0, "zone": 0}
    parts, last = [], 0
    for head, a, b in _top_spans(text):
        if head not in seen:
            continue
        m = _OWN_UUID.search(text, a, b)
        if not m:
            continue
        u = m.group(1)
        if u in seen[head]:
            n[head] += 1
            # footprints keep the derivation earlier task specs used
            key = f"kaebench:{u}:{n[head]}" if head == "footprint" else f"kaebench:{head}:{u}:{n[head]}"
            new = str(uuid.uuid5(uuid.NAMESPACE_URL, key))
            parts += [text[last:m.start(1)], new]
            last = m.end(1)
        seen[head].add(u)
    if any(n.values()):
        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(parts) + text[last:])
    return n


def _strip_routing(board, keep_locked):
    """Remove tracks, arcs and vias, and the teardrops KiCad generated at their ends.

    Teardrops are zones that belong to the routing: left behind, they are stray copper at
    old track ends and, in a place task, they mark the human pad positions.
    """
    # Stale fills would hide unrouted connections; DRC refills zones before checking.
    # Unfill before removing anything: after Remove() SWIG returns untyped zone objects.
    zones = [pcbnew.Cast_to_ZONE(board.GetArea(i)) for i in range(board.GetAreaCount())]
    for z in zones:
        z.UnFill()
    teardrops = [z for z in zones if z.IsTeardropArea()]
    removed = 0
    for t in list(board.GetTracks()):
        if keep_locked and t.IsLocked():
            continue
        board.Remove(t)
        removed += 1
    for z in teardrops:
        board.Remove(z)
    return removed + len(teardrops)


def strip_routing(src, dst, keep_locked):
    board = _load(src)
    removed = _strip_routing(board, keep_locked)
    _save(board, dst)
    _out(dict(ok=True, path=dst, removed=removed))


def strip_placement(src, dst):
    """Strip all routing and move every footprint that is not anchored to a staging grid right
    of the board.

    Anchored footprints stay where the designer put them, and the scorer requires them
    unmoved: locked ones are part of the task (mounting holes, connectors), and ones carrying
    Edge.Cuts are part of the board outline (staged off-board they would leave holes or open
    edges in the outline and add outline polygons in the staging area).
    """
    board = _load(src)
    # Move footprints before removing tracks: after Remove() SWIG returns untyped objects.
    bb = board.GetBoardEdgesBoundingBox()
    x0 = bb.GetRight() + int(10 * NM)
    y0 = bb.GetTop()
    col_h = max(bb.GetHeight(), int(50 * NM))
    x, y, col_w = x0, y0, 0
    moved = 0
    fps = [fp for fp in board.GetFootprints() if not _anchored(fp)]
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


def _mech_row(fp):
    pads = list(fp.Pads())
    attrs = [p.GetAttribute() for p in pads]
    fpid = fp.GetFPID()
    return dict(uuid=fp.m_Uuid.AsString(), ref=fp.GetReference(), lib=str(fpid.GetLibNickname()),
                name=str(fpid.GetLibItemName()), value=fp.GetValue(), desc=fp.GetLibDescription(),
                nets=sorted({p.GetNetname() for p in pads} - {""}), pads=len(pads),
                pth=sum(a == pcbnew.PAD_ATTRIB_PTH for a in attrs),
                npth=sum(a == pcbnew.PAD_ATTRIB_NPTH for a in attrs),
                smd=sum(a in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN) for a in attrs),
                locked=bool(fp.IsLocked()), anchored=bool(_anchored(fp)))


def classify_mech(path):
    """The board's mechanical interface (connectors, mounting, user controls), by the rules in
    mech_rules.py. One row per footprint: uuid, ref, fpid, value, class (None if not
    mechanical) and the rule that decided (evidence)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mech_rules

    rows = []
    for fp in _load(path).GetFootprints():
        r = _mech_row(fp)
        r["class"], r["evidence"] = mech_rules.classify(r)
        r["fpid"] = f"{r['lib']}:{r['name']}" if r["lib"] else r["name"]
        del r["nets"]  # used by the rules; too bulky for the record
        rows.append(r)
    rows.sort(key=lambda r: r["uuid"])
    _out(dict(ok=True, path=path, rules_version=mech_rules.RULES_VERSION, footprints=rows))


def lock_footprints(src, dst, uuids_json):
    """Lock the footprints whose uuids are listed (a JSON list in a file); nothing else changes."""
    with open(uuids_json) as f:
        want = set(json.load(f))
    board = _load(src)
    locked = 0
    for fp in board.GetFootprints():
        if fp.m_Uuid.AsString() in want and not fp.IsLocked():
            fp.SetLocked(True)
            locked += 1
    _save(board, dst)
    _out(dict(ok=True, path=dst, locked=locked))


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


# --- Scoring a method's output: transplant the allowed changes, report everything else ---
#
# The scorer never judges the file a method wrote. It rebuilds the board from the task
# input plus only what the task lets a method change (tracks and vias for routing,
# footprint poses for placement), so edits to rules, outline, keepouts, pads or layers
# cannot affect the score. Those edits are still reported, as `foreign` changes, by
# comparing canonical re-saves of the output and the input with the allowed changes
# normalized away.

_TOK = re.compile(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+')
COORD_TOL = 5e-4  # mm (and degrees) when comparing canonical re-saves
POSE_TOL_NM = 1000
ROUTING_HEADS = ("segment", "arc", "via")
# Never transplanted and without effect on DRC: groups, and the tuning patterns
# ("generated") that wrap meandered tracks. Stripping routing drops the ones that held only
# tracks, so they would otherwise show up as changes of every human layout. Teardrop zones
# are skipped the same way (see _keyed): they are part of the routing and are not scored.
UNSCORED_HEADS = ("group", "generated")


def _try_load(path):
    try:
        return _load(path), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _unfill(board):
    for i in range(board.GetAreaCount()):
        pcbnew.Cast_to_ZONE(board.GetArea(i)).UnFill()


def _canonical(board):
    """The board as KiCad itself saves it (fixed formatting and order)."""
    d = tempfile.mkdtemp(prefix="kae-canon-")
    try:
        p = os.path.join(d, "canon.kicad_pcb")
        _save(board, p)
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _top_spans(text):
    """(head, start, end) of each top-level child of (kicad_pcb ...), as text offsets."""
    spans, depth, start, i, n = [], 0, None, 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif c == "(":
            depth += 1
            if depth == 2:
                start = i
        elif c == ")":
            if depth == 2:
                head = _TOK.findall(text[start:start + 64])[1]
                spans.append((head, start, i + 1))
            depth -= 1
        i += 1
    return spans


def _block_uuid(blk):
    depth = 0
    for i, t in enumerate(blk):
        if t == "(":
            depth += 1
            if depth == 2 and i + 2 < len(blk) and blk[i + 1] == "uuid":
                return blk[i + 2].strip('"')
        elif t == ")":
            depth -= 1
    return None


def _is_teardrop(blk):
    return any(t == "teardrop" and blk[i - 1] == "(" for i, t in enumerate(blk) if i)


def _keyed(text, ignore_heads=()):
    """Top-level objects keyed by (kind, uuid), or (kind, name) for named objects without a
    uuid such as board properties, or (kind, ordinal); as comparable token lists.
    Teardrops (saved without uuid, in no fixed order) are skipped like ignore_heads."""
    out, seen = {}, {}
    for head, a, b in _top_spans(text):
        if head in ignore_heads:
            continue
        blk = _TOK.findall(text[a:b])
        if head == "zone" and _is_teardrop(blk):
            continue
        u = _block_uuid(blk)
        if u is None:
            name = blk[2] if len(blk) > 2 and blk[2].startswith('"') else ""
            seen[(head, name)] = seen.get((head, name), 0) + 1
            u = f"{name.strip(chr(34))}#{seen[(head, name)]}"
        # nested uuids carry no electrical meaning, and KiCad invents fresh ones on load
        # for some implicit fields; compare without them
        toks = _drop_zero_angles([("~" if i > 1 and blk[i - 1] == "uuid" and blk[i - 2] == "(" else t)
                                  for i, t in enumerate(blk)])
        if head.startswith("gr_"):
            toks = _drop_net(toks)
        out[(head, u)] = toks
    return out


def _drop_net(toks):
    """Drop (net X) from a board graphic: KiCad gives copper graphics the net of the tracks
    that touch them when routing is imported, so the net is derived, not set by a method
    (the rebuilt board keeps the input's)."""
    out, i, n = [], 0, len(toks)
    while i < n:
        if toks[i] == "(" and i + 3 < n and toks[i + 1] == "net" and toks[i + 3] == ")":
            i += 4
            continue
        out.append(toks[i])
        i += 1
    return out


def _drop_zero_angles(toks):
    """(at x y A) with A = 0 mod 360 -> (at x y): KiCad writes a zero angle as 360 or leaves
    it out depending on how the object was rotated."""
    out, i, n = [], 0, len(toks)
    while i < n:
        if toks[i] == "at" and i and toks[i - 1] == "(" and i + 4 < n and toks[i + 4] == ")":
            try:
                a = float(toks[i + 3]) % 360.0
            except ValueError:
                a = None
            if a is not None and min(a, 360.0 - a) <= COORD_TOL:
                out += toks[i:i + 3]
                i += 4
                continue
        out.append(toks[i])
        i += 1
    return out


def _same_tokens(a, b):
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y:
            continue
        try:
            fx, fy = float(x), float(y)
        except ValueError:
            return False
        d = abs(fx - fy)
        if d > COORD_TOL and abs(d - 360.0) > COORD_TOL:
            return False
    return True


def _foreign(out_text, in_text, limit=50, skip=()):
    """Top-level objects added, removed or changed, routing, zone fills, groups and tuning
    patterns excepted, and the (kind, uuid) keys in skip (judged elsewhere)."""
    ignore = ROUTING_HEADS + UNSCORED_HEADS
    a, b = _keyed(out_text, ignore), _keyed(in_text, ignore)
    diffs = []
    for k in sorted((set(a) | set(b)) - set(skip)):
        if k not in a:
            diffs.append(dict(kind=k[0], id=k[1], change="removed"))
        elif k not in b:
            diffs.append(dict(kind=k[0], id=k[1], change="added"))
        elif not _same_tokens(a[k], b[k]):
            diffs.append(dict(kind=k[0], id=k[1], change="changed"))
    counts = {}
    for d in diffs:
        counts[d["kind"]] = counts.get(d["kind"], 0) + 1
    return dict(count=len(diffs), by_kind=counts, items=diffs[:limit])


def _um(v):
    return int(round(v / 1000.0))


def _route_key(t):
    cls = t.GetClass()
    if cls == "PCB_VIA":
        p = t.GetPosition()
        return ("via", _um(p.x), _um(p.y), t.TopLayer(), t.BottomLayer())
    s, e = t.GetStart(), t.GetEnd()
    ends = tuple(sorted([(_um(s.x), _um(s.y)), (_um(e.x), _um(e.y))]))
    if cls == "PCB_ARC":
        m = t.GetMid()
        return ("arc", t.GetLayer(), ends, _um(m.x), _um(m.y), _um(t.GetWidth()))
    return ("seg", t.GetLayer(), ends, _um(t.GetWidth()))


def _copy_stats(matched, total, min_items, min_frac):
    frac = round(matched / total, 4) if total else 0.0
    return dict(matched=matched, total=total, frac=frac,
                suspect=matched >= min_items and frac >= min_frac)


def _identity(board):
    placement = _placement(board)
    return dict(
        placement_hash=_hash([(r["uuid"], r["x"], r["y"], r["rot"], r["back"]) for r in placement]),
        padnet_hash=_hash(_pad_nets(board)),
        copper_layers=board.GetCopperLayerCount(),
    )


def _net_names(board):
    names = {""}
    for fp in board.GetFootprints():
        names.update(p.GetNetname() for p in fp.Pads())
    for i in range(board.GetAreaCount()):
        names.add(board.GetArea(i).GetNetname())
    names.update(t.GetNetname() for t in board.GetTracks())
    return names


# --- Zones a route method adds (transplant-routing --zones; score v10) ---
OUTLINE_TOL_NM = 10000  # board outline grown by 10 um: its arcs are polygonized to ~5 um
AREA_TOL_NM2 = 1e8  # 100 um^2: overlaps smaller than this are rounding, not copper
ZONE_COPY_IOU = 0.8  # an added zone this close to a human zone (same net and layer) is a copy


def _zones(board):
    return [pcbnew.Cast_to_ZONE(board.GetArea(i)) for i in range(board.GetAreaCount())]


def _zone_layers(z):
    return list(z.GetLayerSet().Seq())


def _poly(z):
    return pcbnew.SHAPE_POLY_SET(z.Outline())


def _overlap(a, b):
    """Area (nm^2) where the outlines of zones a and b meet."""
    p = _poly(a)
    p.BooleanIntersection(_poly(b))
    return p.Area()


def _iou(a, b):
    inter = _overlap(a, b)
    if inter <= 0:
        return 0.0
    u = _poly(a)
    u.BooleanAdd(_poly(b))
    return inter / u.Area() if u.Area() > 0 else 0.0


def _outer_outline(board):
    """The board's outer outline (cut-outs filled in), grown by OUTLINE_TOL_NM; None if none."""
    poly = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(poly, False) or poly.OutlineCount() == 0:
        return None
    outer = pcbnew.SHAPE_POLY_SET()
    for i in range(poly.OutlineCount()):
        outer.AddOutline(poly.COutline(i))
    outer.Inflate(OUTLINE_TOL_NM, pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, 1000)
    return outer


def _share_layer(a, b):
    return any(b.IsOnLayer(l) for l in _zone_layers(a))


def _added_zones(out, board, ref, nets):
    """Judge the zones OUTPUT adds to INPUT (score v10). Returns (accepted uuids, problems, copy).

    Added = not a teardrop and a uuid no input zone has. Each must be a copper zone (no rule
    area) on the board's enabled copper layers, on a net the task has (named; no net-less
    zones), inside the board's outer outline, out of every rule area that forbids copper pours
    on a shared layer, and, where it overlaps another zone on a shared layer, at a strictly
    different priority (so the fill never depends on uuid tie-breaks; KiCad 10.0.7's filler
    deadlocks on overlapping zones of different nets that tie on priority and uuid). Zone
    uuids must be unique. Input zones that are missing or changed are reported by _foreign.
    copy: added zones whose outline matches a human zone on the same net and a shared layer
    (IoU >= ZONE_COPY_IOU)."""
    in_ids = {z.m_Uuid.AsString() for z in _zones(board) if not z.IsTeardropArea()}
    out_zones = [z for z in _zones(out) if not z.IsTeardropArea()]
    ids = [z.m_Uuid.AsString() for z in out_zones]
    added = [z for z in out_zones if z.m_Uuid.AsString() not in in_ids]
    # a second zone under an input zone's uuid would hide behind it in _foreign's keyed compare
    problems = [dict(uuid=u, net="", reasons=["duplicate uuid of a task zone"], given=True)
                for u in sorted({u for u in ids if u in in_ids and ids.count(u) > 1})]
    if not added:
        return [], problems, None
    enabled = board.GetEnabledLayers()
    outline = _outer_outline(board)
    keepouts = [z for z in _zones(board) if z.GetIsRuleArea() and z.GetDoNotAllowZoneFills()]
    keepouts += [z for fp in board.GetFootprints() for z in fp.Zones()
                 if z.GetIsRuleArea() and z.GetDoNotAllowZoneFills()]
    others = [z for z in out_zones if not z.GetIsRuleArea()]
    accepted = []
    for z in added:
        u = z.m_Uuid.AsString()
        why = []
        if ids.count(u) > 1:
            why.append("duplicate uuid")
        if z.GetIsRuleArea():
            why.append("rule area")
        layers = _zone_layers(z)
        if not layers or any(not pcbnew.IsCopperLayer(l) or not enabled.Contains(l) for l in layers):
            why.append("not on the board's copper layers")
        name = z.GetNetname()
        if not name:
            why.append("no net")
        elif name not in nets:
            why.append(f"net {name!r} not in the task")
        if not why:
            if outline is None:
                why.append("board has no outline")
            else:
                rest = _poly(z)
                rest.BooleanSubtract(outline)
                if rest.Area() > AREA_TOL_NM2:
                    why.append("outside the board outline")
            for k in keepouts:
                if _share_layer(z, k) and _overlap(z, k) > AREA_TOL_NM2:
                    why.append("in a keepout that forbids copper pours")
                    break
            for w in others:
                if (w is not z and _share_layer(z, w) and w.GetAssignedPriority() == z.GetAssignedPriority()
                        and _overlap(z, w) > AREA_TOL_NM2):
                    why.append(f"overlaps zone {w.m_Uuid.AsString()} at equal priority")
                    break
        if why:
            problems.append(dict(uuid=u, net=name, reasons=why))
        else:
            accepted.append(u)
    copy = None
    if ref is not None:
        human = [h for h in _zones(ref) if not h.IsTeardropArea() and not h.GetIsRuleArea()]
        matched = sum(1 for z in added if any(
            h.GetNetname() == z.GetNetname() and _share_layer(z, h) and _iou(z, h) >= ZONE_COPY_IOU for h in human))
        copy = dict(matched=matched, total=len(added), suspect=matched > 0)
    return accepted, problems, copy


def _pad_zone_connections(out, board):
    """Pads whose own zone connection (zone_connect: inherited, solid, thermal, none) OUTPUT
    changed: {pad key: (output pad, input pad)}. The only footprint edit a route method may make."""
    in_pads = _pads_by_key(board)
    changed = {}
    for k, p in _pads_by_key(out).items():
        q = in_pads.get(k)
        if q is not None and p.GetLocalZoneConnection() != q.GetLocalZoneConnection():
            changed[k] = (p, q)
    return changed


def _pads_by_key(board):
    """Pads keyed by (footprint uuid, index, number): pad uuids are invented afresh on load when a
    file has none, the order of a footprint's pads is kept."""
    return {(fp.m_Uuid.AsString(), i, p.GetNumber()): p for fp in board.GetFootprints() for i, p in enumerate(fp.Pads())}


def transplant_routing(out_path, inp_path, dst, ref_path=None, zones=False):
    """DEST = INPUT + the tracks, arcs and vias of OUTPUT. Report OUTPUT's other changes.

    With zones (route tasks, score v10), also the copper zones OUTPUT adds (unfilled; DRC
    refills every zone) when they pass _added_zones, and pads' own zone connection
    (zone_connect) as OUTPUT sets it; both are then left out of the foreign changes.

    Works on KiCad's own re-save of OUTPUT: accepted routing objects and zones are copied as
    text into INPUT (nets are referenced by name in KiCad 10 files). pcbnew objects are never
    moved between boards or removed, which upsets SWIG's type tracking.
    """
    out, err = _try_load(out_path)
    if out is None:
        _out(dict(ok=True, loadable=False, error=err))
        return
    board = _load(inp_path)
    ref = _load(ref_path) if ref_path else None
    enabled = board.GetEnabledLayers()
    nets = _net_names(board)
    given = {_route_key(t) for t in board.GetTracks()}
    out_keys, accepted = [], set()
    bad_layer = new_net = 0
    for t in out.GetTracks():
        key = _route_key(t)
        out_keys.append(key)
        layers = [t.TopLayer(), t.BottomLayer()] if t.GetClass() == "PCB_VIA" else [t.GetLayer()]
        if any(not pcbnew.IsCopperLayer(l) or not enabled.Contains(l) for l in layers):
            bad_layer += 1
            continue
        # A net no pad, zone or given copper uses (e.g. stray copper on a pad-less net in an
        # imported design) becomes a new net: it cannot connect anything, only add errors.
        if t.GetNetname() not in nets:
            new_net += 1
        if key not in given:
            accepted.add(t.m_Uuid.AsString())
    copy = None
    if ref is not None:
        # Straight pad-to-pad segments are what any router draws, so they are not evidence
        # of copying (a breadboard is nothing else).
        pads = {(_um(p.GetCenter().x), _um(p.GetCenter().y)) for fp in board.GetFootprints() for p in fp.Pads()}
        ref_keys = {_route_key(t) for t in ref.GetTracks()}
        mine = [k for k in out_keys if k not in given and not (k[0] == "seg" and all(e in pads for e in k[2]))]
        copy = _copy_stats(sum(1 for k in mine if k in ref_keys), len(mine), 20, 0.6)
    ident = _identity(out)
    missing_given = len(given - set(out_keys))

    out_text = _canonical(out)
    blocks = []
    for head, a, b in _top_spans(out_text):
        if head in ROUTING_HEADS and _block_uuid(_TOK.findall(out_text[a:b])) in accepted:
            blocks.append(out_text[a:b])
    zone_ok, zone_problems, zone_copy, pad_conn = [], [], None, {}
    zone_blocks = []
    if zones:
        zone_ok, zone_problems, zone_copy = _added_zones(out, board, ref, nets - {""})
        pad_conn = _pad_zone_connections(out, board)
        if zone_ok:
            _unfill(out)  # the method's fill is never used: DRC refills every zone
            ztext = _canonical(out)
            for head, a, b in _top_spans(ztext):
                if head == "zone" and _block_uuid(_TOK.findall(ztext[a:b])) in zone_ok:
                    zone_blocks.append(ztext[a:b])
    with open(inp_path, encoding="utf-8") as f:
        in_text = f.read()
    end = in_text.rstrip().rfind(")")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(in_text[:end] + "".join("\t" + blk + "\n" for blk in blocks + zone_blocks) + in_text[end:])
    if pad_conn:
        staged = _load(dst)
        pads = _pads_by_key(staged)
        for k, (p, _) in pad_conn.items():
            pads[k].SetLocalZoneConnection(p.GetLocalZoneConnection())
        _save(staged, dst)
    check = _load(dst)
    n_routing = len(list(check.GetTracks()))
    if n_routing != len(given) + len(blocks):
        raise RuntimeError(f"transplant produced {n_routing} routing items, expected "
                           f"{len(given)} + {len(blocks)}")
    if check.GetAreaCount() != board.GetAreaCount() + len(zone_blocks):
        raise RuntimeError(f"transplant produced {check.GetAreaCount()} zones, expected "
                           f"{board.GetAreaCount()} + {len(zone_blocks)}")

    # Placement unchanged within the tolerance the place side allows anchored parts (_same_pose):
    # a joint output that rounds a locked part's pose by under 1 um passed transplant-placement
    # but failed an exact hash here. Parts within it are put back at the input pose, so their
    # re-save does not count as a foreign change either.
    in_fps = {fp.m_Uuid.AsString(): fp for fp in board.GetFootprints()}
    out_fps = {fp.m_Uuid.AsString(): fp for fp in out.GetFootprints()}
    moved = sorted(set(in_fps) ^ set(out_fps))
    for u, o in out_fps.items():
        f = in_fps.get(u)
        if f is None:
            continue
        if _same_pose(f, o):
            _set_pose(o, f.GetPosition(), f.GetOrientation(), f.IsFlipped())
        else:
            moved.append(f.GetReference())
    for p, q in pad_conn.values():  # an allowed edit: compare the rest of the pad
        p.SetLocalZoneConnection(q.GetLocalZoneConnection())
    _unfill(out)
    _unfill(board)
    skip = [("zone", z["uuid"]) for z in zone_problems if not z.get("given")] + [("zone", u) for u in zone_ok]
    foreign = _foreign(_canonical(out), _canonical(board), skip=skip)
    res = dict(ok=True, loadable=True, added=len(blocks), bad_layer=bad_layer, new_net_items=new_net,
               missing_given=missing_given, output=ident, placement_moved=moved[:50], n_placement_moved=len(moved),
               foreign=foreign, copy=copy)
    if zones:
        if zone_copy is not None:
            copy = dict(copy or {}, zones=zone_copy)
            copy["suspect"] = bool(copy.get("suspect")) or zone_copy["suspect"]
            res["copy"] = copy
        res.update(zones_added=len(zone_ok) + sum(1 for z in zone_problems if not z.get("given")), zones_transplanted=len(zone_blocks),
                   zone_problems=zone_problems[:50], n_zone_problems=len(zone_problems),
                   pad_zone_connections=len(pad_conn))
    _out(res)


def _same_pose(a, b):
    pa, pb = a.GetPosition(), b.GetPosition()
    da = (a.GetOrientationDegrees() - b.GetOrientationDegrees()) % 360.0
    return (abs(pa.x - pb.x) <= POSE_TOL_NM and abs(pa.y - pb.y) <= POSE_TOL_NM
            and min(da, 360.0 - da) <= 0.01 and a.IsFlipped() == b.IsFlipped())


def _set_pose(fp, pos, orientation, flipped):
    if fp.IsFlipped() != flipped:
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fp.SetOrientation(orientation)
    fp.SetPosition(pos)


def transplant_placement(out_path, inp_path, dst, ref_path=None, zones=False):
    """DEST = INPUT with each footprint that is not anchored (_anchored) moved to its pose in
    OUTPUT (position, orientation, side). Report OUTPUT's other changes, moved anchored parts
    (as locked_moved), and footprints
    missing from or added to OUTPUT. Place inputs carry no copper, so neither does DEST.

    With zones (joint tasks, score v10): the zones OUTPUT adds and pads' own zone connection are
    the routing half's to judge and transplant (transplant-routing --zones), so they are left out
    of the foreign changes here, and never put into DEST: placement legality is judged on the
    placement alone."""
    out, err = _try_load(out_path)
    if out is None:
        _out(dict(ok=True, loadable=False, error=err))
        return
    board, fresh = _load(inp_path), _load(inp_path)
    ref = _load(ref_path) if ref_path else None
    in_fps = {fp.m_Uuid.AsString(): fp for fp in board.GetFootprints()}
    if len(in_fps) != len(board.GetFootprints()):
        raise RuntimeError("task input has duplicate footprint uuids; re-run prepare")
    out_list = list(out.GetFootprints())
    out_fps = {fp.m_Uuid.AsString(): fp for fp in out_list}
    missing = sorted(u for u in in_fps if u not in out_fps)
    # a footprint repeated under an existing uuid counts as added
    extra = sorted(u for u in out_fps if u not in in_fps) + ["(duplicate uuid)"] * (len(out_list) - len(out_fps))
    copy = None
    if ref is not None:
        ref_fps = {fp.m_Uuid.AsString(): fp for fp in ref.GetFootprints()}
        free = [u for u, fp in in_fps.items() if not _anchored(fp) and u in out_fps and u in ref_fps]
        copy = _copy_stats(sum(1 for u in free if _same_pose(out_fps[u], ref_fps[u])), len(free), 5, 0.5)
    ident = _identity(out)
    routing_added = len(list(out.GetTracks()))
    locked_moved = []
    for u, fp in in_fps.items():
        o = out_fps.get(u)
        if o is None:
            continue
        if _anchored(fp):
            if not _same_pose(fp, o):
                locked_moved.append(fp.GetReference())
            continue
        _set_pose(fp, o.GetPosition(), o.GetOrientation(), o.IsFlipped())
    _save(board, dst)

    # Normalize the allowed change away: put every output footprint back at its input pose.
    # The input copy makes the same round trip first (to the output's pose and back): KiCad
    # rewrites some footprint graphics when it rotates them (an fp_rect at a non-right angle
    # becomes an fp_poly, and stays one when rotated back), so a placed footprint compared
    # with an input that never moved would always look changed.
    fresh_fps = {fp.m_Uuid.AsString(): fp for fp in fresh.GetFootprints()}
    for u, o in out_fps.items():
        f = fresh_fps.get(u)
        if f is not None:
            pose = f.GetPosition(), f.GetOrientation(), f.IsFlipped()
            _set_pose(f, o.GetPosition(), o.GetOrientation(), o.IsFlipped())
            _set_pose(f, *pose)
            _set_pose(o, *pose)
    skip = []
    if zones:
        for p, q in _pad_zone_connections(out, fresh).values():
            p.SetLocalZoneConnection(q.GetLocalZoneConnection())
        in_ids = {z.m_Uuid.AsString() for z in _zones(fresh)}
        skip = [("zone", u) for u in {z.m_Uuid.AsString() for z in _zones(out) if not z.IsTeardropArea()} - in_ids]
    _unfill(out)
    _unfill(fresh)
    foreign = _foreign(_canonical(out), _canonical(fresh), skip=skip)
    _out(dict(ok=True, loadable=True, missing=missing[:50], n_missing=len(missing), extra=extra[:50],
              n_extra=len(extra), locked_moved=locked_moved[:50], n_locked_moved=len(locked_moved),
              routing_added=routing_added, output=ident, foreign=foreign, copy=copy))
def covered_micro_arcs(path, max_mm=0.001):
    """List track arcs whose start, mid and end lie within max_mm of each other and whose
    copper lies wholly inside the other tracks, vias and pads of the same net and layer.

    Removing them leaves the copper (and so connectivity) unchanged. Zone fills are not
    counted as cover, since they can be refilled. Polygons use a 0.1 um error, the arc
    rounded inward and its cover outward.
    """
    board = _load(path)
    lim, err = max_mm * NM, 100

    def tiny(t):
        if t.GetClass() != "PCB_ARC":
            return False
        p = [t.GetStart(), t.GetMid(), t.GetEnd()]
        return max(math.hypot(a.x - b.x, a.y - b.y) for a, b in ((p[0], p[1]), (p[0], p[2]), (p[1], p[2]))) < lim

    tracks = list(board.GetTracks())
    groups = {}
    for t in tracks:
        if tiny(t):
            groups.setdefault((t.GetNetCode(), t.GetLayer()), []).append(t)
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    covered, n = [], 0
    for (net, layer), arcs in groups.items():
        n += len(arcs)
        cover = pcbnew.SHAPE_POLY_SET()
        for t in tracks:
            if t.GetNetCode() == net and t.IsOnLayer(layer) and not tiny(t):
                t.TransformShapeToPolygon(cover, layer, 0, err, pcbnew.ERROR_OUTSIDE)
        for p in pads:
            if p.GetNetCode() == net and p.IsOnLayer(layer):
                p.TransformShapeToPolygon(cover, layer, 0, err, pcbnew.ERROR_OUTSIDE)
        if cover.OutlineCount() == 0:
            continue
        cover.Simplify()
        for a in arcs:
            own = pcbnew.SHAPE_POLY_SET()
            a.TransformShapeToPolygon(own, layer, 0, err, pcbnew.ERROR_INSIDE)
            own.BooleanSubtract(cover)
            if own.Area() < 0.25e6:  # below 0.25 um^2 (internal units are nm)
                covered.append(a.m_Uuid.AsString())
    _out(dict(ok=True, candidates=n, covered=covered))


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
        elif op == "classify-mech":
            classify_mech(args[0])
        elif op == "lock-footprints":
            lock_footprints(args[0], args[1], args[2])
        elif op == "export-dsn":
            export_dsn(args[0], args[1])
        elif op == "import-ses":
            import_ses(args[0], args[1], args[2])
        elif op == "unconnected":
            unconnected(args[0])
        elif op == "transplant-routing":
            transplant_routing(*args[:4], zones="--zones" in argv)
        elif op == "transplant-placement":
            transplant_placement(*args[:4], zones="--zones" in argv)
        elif op == "covered-micro-arcs":
            covered_micro_arcs(args[0], *(float(a) for a in args[1:2]))
        else:
            raise SystemExit(f"unknown op {op}")
    except Exception as e:  # report failures as JSON so the harness can record them
        _out(dict(ok=False, op=op, error=f"{type(e).__name__}: {e}"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
