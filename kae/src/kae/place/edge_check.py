# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""User-facing connectors that must sit on the board edge, and the hazard when one does not.

A USB jack, barrel jack or audio jack in the middle of a board cannot take its plug: the board
is unusable whatever its routing. Which connector kinds humans put on an edge was measured on
the local corpus (docs/research/placement/kae-fixed-interface.md, "Edge connectors in plain
place mode"): PIN_KINDS are pinned there by the placer (pin_poses), EDGE_KINDS get a hazard
when kae leaves them inside.

    kind(fp)                      -> panel-connector kind ('usb', 'barrel', ...) or None
    edge_parts(board)             -> {uuid: (ref, kind)} for the parts of EDGE_KINDS
    distance(fp, outline)         -> mm from the part's courtyard to the outline's outer edge
    hazards(board, ...)           -> hazard entries (kae.hazards schema) for each one off the edge
"""
from __future__ import annotations

import re

from . import mech_rules

_I = re.IGNORECASE
# Panel connectors, matched on library + footprint name, value and library description; first
# match wins. NOT_PANEL drops what mech_rules calls a connector but no plug reaches from outside
# (headers, wire-to-board, pads, interface ICs on custom footprints such as TUSB / FSUSB);
# VERTICAL drops top-entry parts, which humans place anywhere on the board.
KINDS = (
    ("usb", re.compile(r"usb(?!lc)|type-?c|micro[-_ ]?b(?![a-z])", _I)),
    ("barrel", re.compile(r"barrel|dc[-_ ]?jack|dcjack|power_?jack|(?<![a-z])pj-?0\d\d|(?<![a-z])dc-?0\d\d", _I)),
    ("audio", re.compile(r"audio_?jack|audiojack|3\.5 ?mm|(?<![a-z])trr?s(?![a-z])|phone_?jack|headphone|6\.35|"
                         r"jack_3\.5|(?<![a-z])pj-?3\d\d|(?<![a-z])sj-?[1-4]", _I)),
    ("rj/modular", re.compile(r"rj45|rj11|rj12|8p8c|6p6c|magjack", _I)),
    ("video/dsub", re.compile(r"hdmi|displayport|d-?sub|(?<![a-z])db-?(9|15|25)(?![0-9])|(?<![a-z])de-?9|"
                              r"(?<![a-z])vga|(?<![a-z])dvi", _I)),
    ("rf-edge", re.compile(r"(?<![a-z])(sma|bnc)(?![a-z])", _I)),
    ("card-slot", re.compile(r"micro_?sd|(?<![a-z])(sd|tf)_?card|sim_?card|card_?holder", _I)),
)
NOT_PANEL = re.compile(
    r"pin_?header|pinheader|pin_?socket|socket_strip|(?<![a-z])hdr|conn_\d|wire|_pad|solder|testpoint|qfn|ssop|"
    r"soic|bga|tqfp|(?<![a-z])(tusb|fsusb|cyusb|ft232|ch340|cp210)|idc|jst|molex_?(pico|micro)|picoblade|"
    r"(?<![a-z])(xh|ph|sh|gh|zh)[-_]?\d|grove|qwiic|(?<![a-z])usb\d{4}[a-z]|(?<![a-z])esd|(?<![a-z])phy(?![a-z])", _I)
VERTICAL = re.compile(r"vertical|_vert|(?<![a-z])vt(?![a-z])|top.?entry|upright", _I)
# Human boards (local corpus, docs/research/placement/kae-fixed-interface.md): courtyard within
# 2 mm of the outer edge for 93 % of horizontal USB, 83 % video/D-sub, 80 % barrel, 77 % RJ,
# 75 % SMA/BNC, 70 % card slots, 61 % audio jacks; facing out (FACE_MIN) for 84-99 % of the
# first five on the edge, about half of card slots and audio jacks.
PIN_KINDS = ("usb", "barrel", "rj/modular", "video/dsub", "rf-edge")   # pinned to the edge, facing out
EDGE_KINDS = PIN_KINDS + ("audio", "card-slot")                         # hazard when kae leaves them inside
EDGE_TOL = 1.0       # mm: the pin's target, courtyard to the outer edge
HAZARD_TOL = 2.0     # mm: farther than this is a hazard (6 % of human USB jacks are)


def kind(fp):
    """The panel-connector kind of a kae.board.model.Footprint (KINDS; mech_rules class
    connector, not a header, wire-to-board or vertical part), else None."""
    from .fixed import mech_row
    row = mech_row(fp)
    cls, _ = mech_rules.classify(row)
    if cls != "connector":
        return None
    text = " ".join(str(row.get(k) or "") for k in ("lib", "name", "value", "desc"))
    if NOT_PANEL.search(text) or VERTICAL.search(text):
        return None
    for name, rx in KINDS:
        if rx.search(text):
            return name
    return None


def edge_parts(board, kinds=EDGE_KINDS):
    """{uuid: (ref, kind)} of the board's connectors whose kind must sit on an edge."""
    out = {}
    for fp in board.footprints:
        if not fp.pads:
            continue
        k = kind(fp)
        if k in kinds:
            out[fp.uuid] = (fp.ref, k)
    return out


def _outline(board):
    from shapely.ops import unary_union
    polys = [p for p in (board.outline or []) if p is not None and not p.is_empty]
    return unary_union(polys) if polys else None


def distance(fp, outline, pose=None):
    """mm from fp's courtyard (else its pads' box) to the outer edge of the outline piece it is
    on; 0 when it touches or overhangs the edge. pose: (x, y, rot, side), else fp's own."""
    from shapely.geometry import MultiPolygon, box
    from shapely.ops import unary_union

    from kae.board import transform
    x, y, rot, side = pose or (fp.x, fp.y, fp.rot, fp.side)
    cy = transform.courtyard(fp, x, y, rot, side, which="extent")
    if cy:
        g = unary_union(cy)
    else:
        xy = transform.fp_pads_xy(fp, x, y, rot, side)
        g = box(float(xy[:, 0].min()), float(xy[:, 1].min()), float(xy[:, 0].max()), float(xy[:, 1].max()))
    parts = list(outline.geoms) if isinstance(outline, MultiPolygon) else [outline]
    host = min(parts, key=lambda p: p.distance(g.centroid))
    if not host.contains(g):
        return 0.0
    return float(g.distance(host.exterior))


def hazards(board, tol=HAZARD_TOL, kinds=EDGE_KINDS, moved=None, poses=None):
    """Hazard entries for each connector of `kinds` whose courtyard is more than `tol` mm from
    the board's outer edge. `moved`: uuids kae placed (others are the user's and not judged);
    None judges every one. `poses`: {uuid: (x, y, rot, side)} overriding the board's."""
    outline = _outline(board)
    if outline is None:
        return []
    out = []
    by = {fp.uuid: fp for fp in board.footprints}
    for u, (ref, k) in sorted(edge_parts(board, kinds).items(), key=lambda kv: kv[1][0]):
        fp = by[u]
        if moved is not None and u not in moved:
            continue
        pose = (poses or {}).get(u)
        if pose is None and not getattr(fp, "on_board", True):
            continue
        d = distance(fp, outline, pose)
        if d <= tol:
            continue
        out.append(dict(
            code="connector_off_edge", severity="warn", category="assembly",
            message=(f"{ref} is a {k} connector {d:.1f} mm inside the board edge: its plug cannot reach it "
                     f"in an enclosure or from outside"),
            objects=[ref],
            evidence=dict(distance_mm=round(d, 2), limit_mm=tol, kind=k,
                          source="human corpus edge rates (kae-fixed-interface.md)"),
            fix=(f"place {ref} at the edge facing out and keep it there (kae place --fix {ref}, or "
                 f"--fix-class connectors with the interface already placed)")))
    return out


FACE_MIN = 0.3       # cos between the part's body direction and the outward edge normal


def facing(fp, outline, pose=None):
    """cos of the angle between the part's body direction (pad centroid -> courtyard centroid:
    a jack's opening is ahead of its pins) and the outward normal of the nearest outer edge;
    None when the footprint gives no direction (courtyard centred on its pads)."""
    import math

    from shapely.geometry import MultiPolygon
    from shapely.ops import unary_union

    from kae.board import transform
    x, y, rot, side = pose or (fp.x, fp.y, fp.rot, fp.side)
    cy = transform.courtyard(fp, x, y, rot, side, which="extent")
    if not cy or not fp.pads:
        return None
    c = unary_union(cy).centroid
    xy = transform.fp_pads_xy(fp, x, y, rot, side)
    bx, by = c.x - float(xy[:, 0].mean()), c.y - float(xy[:, 1].mean())
    parts = list(outline.geoms) if isinstance(outline, MultiPolygon) else [outline]
    host = min(parts, key=lambda p: p.distance(c))
    ext = host.exterior
    q = ext.interpolate(ext.project(c))
    ox, oy = q.x - c.x, q.y - c.y
    if not host.contains(c):
        ox, oy = -ox, -oy
    nb, no = math.hypot(bx, by), math.hypot(ox, oy)
    if nb < 0.3 or no < 1e-6:
        return None
    return (bx * ox + by * oy) / (nb * no)


def pin_poses(P, st, parts, tol=EDGE_TOL, limit=3000, log=None):
    """Edge poses for the movable parts `parts` (indices into P.parts) of a seed state `st`:
    for each, the grid-free spot nearest its seed position (clear of the fixed parts and of
    the parts pinned before it) whose courtyard is within `tol` of the outer edge and whose
    body faces out (FACE_MIN, when the footprint shows a direction). Returns ({uuid: (x, y, rot,
    side)}, {ref: why} for the parts with no such spot)."""
    from shapely.geometry import box

    from . import exact
    outline = P.outline
    ext_parts = list(getattr(outline, "geoms", [outline]))
    poses, failed, pinned = {}, {}, set()
    mov = set(P.mov)

    def seed_d(i):
        x, y = st.xy(i)
        return min(pp.exterior.distance(box(x, y, x, y)) for pp in ext_parts)

    for i in sorted(parts, key=seed_d):
        p = P.parts[i]
        S, pad = exact._tables(P, st, mov - pinned)
        n_ortho = getattr(p, "n_ortho", len(p.rots))
        cands = exact._candidates(P, st, i, S, pad, list(range(n_ortho)), 0.0, limit)
        cands.sort(key=lambda c: c[0])
        hit = None
        for _, X, Y, k in cands:
            x, y = P.xy(X, Y)
            r = p.rots[k]
            x0, y0, x1, y1 = r.own
            bb = box(x + x0, y + y0, x + x1, y + y1)
            if min(pp.exterior.distance(bb) for pp in ext_parts) > tol + 0.5:
                continue
            pose = (float(x), float(y), r.rot, p.side)
            if distance(p.fp, outline, pose) > tol:
                continue
            f = facing(p.fp, outline, pose)
            if f is not None and f < FACE_MIN:
                continue
            hit = (X, Y, k, pose)
            break
        if hit is None:
            failed[p.ref] = "no free spot on the edge facing out" if cands else "no free spot"
            continue
        st.X[i], st.Y[i], st.K[i] = hit[0], hit[1], hit[2]
        pinned.add(i)
        poses[p.uuid] = hit[3]
        if log:
            log(f"edge: {p.ref} pinned at ({hit[3][0]:.2f}, {hit[3][1]:.2f}) rot {hit[3][2]:g}")
    return poses, failed


def with_poses(board, poses):
    """A copy of the board model with footprints moved to `poses` ({uuid: (x, y, rot, side)};
    the side must be the footprint's own) and marked on the board."""
    import dataclasses

    from kae.board import transform
    fps = []
    for fp in board.footprints:
        if fp.uuid in poses:
            x, y, rot, side = poses[fp.uuid]
            pads = [dataclasses.replace(pd, **dict(zip(("x", "y"), map(float, transform.pad_xy(fp, pd, x, y, rot, side)))))
                    for pd in fp.pads]
            fp = dataclasses.replace(fp, x=x, y=y, rot=rot, pads=pads, on_board=True)
        fps.append(fp)
    return dataclasses.replace(board, footprints=fps)
