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
    python pcbnew_ops.py unconnected BOARD
    python pcbnew_ops.py transplant-routing OUTPUT INPUT DEST [REFERENCE]
    python pcbnew_ops.py transplant-placement OUTPUT INPUT DEST [REFERENCE]
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


def _foreign(out_text, in_text, limit=50):
    """Top-level objects added, removed or changed, routing, zone fills, groups and tuning
    patterns excepted."""
    ignore = ROUTING_HEADS + UNSCORED_HEADS
    a, b = _keyed(out_text, ignore), _keyed(in_text, ignore)
    diffs = []
    for k in sorted(set(a) | set(b)):
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


def transplant_routing(out_path, inp_path, dst, ref_path=None):
    """DEST = INPUT + the tracks, arcs and vias of OUTPUT. Report OUTPUT's other changes.

    Works on KiCad's own re-save of OUTPUT: accepted routing objects are copied as text
    into INPUT (nets are referenced by name in KiCad 10 files). pcbnew objects are never
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
    with open(inp_path, encoding="utf-8") as f:
        in_text = f.read()
    end = in_text.rstrip().rfind(")")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(in_text[:end] + "".join("\t" + blk + "\n" for blk in blocks) + in_text[end:])
    check = _load(dst)
    n_routing = len(list(check.GetTracks()))
    if n_routing != len(given) + len(blocks):
        raise RuntimeError(f"transplant produced {n_routing} routing items, expected "
                           f"{len(given)} + {len(blocks)}")

    _unfill(out)
    _unfill(board)
    foreign = _foreign(_canonical(out), _canonical(board))
    _out(dict(ok=True, loadable=True, added=len(blocks), bad_layer=bad_layer, new_net_items=new_net,
              missing_given=missing_given, output=ident, foreign=foreign, copy=copy))


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


def transplant_placement(out_path, inp_path, dst, ref_path=None):
    """DEST = INPUT with each footprint that is not anchored (_anchored) moved to its pose in
    OUTPUT (position, orientation, side). Report OUTPUT's other changes, moved anchored parts
    (as locked_moved), and footprints
    missing from or added to OUTPUT. Place inputs carry no copper, so neither does DEST."""
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
    _unfill(out)
    _unfill(fresh)
    foreign = _foreign(_canonical(out), _canonical(fresh))
    _out(dict(ok=True, loadable=True, missing=missing[:50], n_missing=len(missing), extra=extra[:50],
              n_extra=len(extra), locked_moved=locked_moved[:50], n_locked_moved=len(locked_moved),
              routing_added=routing_added, output=ident, foreign=foreign, copy=copy))


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
        elif op == "unconnected":
            unconnected(args[0])
        elif op == "transplant-routing":
            transplant_routing(*args[:4])
        elif op == "transplant-placement":
            transplant_placement(*args[:4])
        else:
            raise SystemExit(f"unknown op {op}")
    except Exception as e:  # report failures as JSON so the harness can record them
        _out(dict(ok=False, op=op, error=f"{type(e).__name__}: {e}"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
