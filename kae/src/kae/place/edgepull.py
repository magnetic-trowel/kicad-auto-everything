# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Edge-facing parts: connectors and mounting holes a human puts at the board edge.

`fp_class` names a footprint's class from its library id, value and the brief's part kind
(USB, barrel jack, audio jack, RF, terminal block, wire-to-board, pin header, mounting
hole, ...). `mating` infers the side a connector mates on, where the footprint makes it
inferable: the body reaching well past the pads on one side (a USB receptacle's opening, a
right-angle header's pins). `edge_distance` is a placed part's courtyard distance from the
board edge.

`anchors` turns the classes kept by the validation (tools/research/place/edgepull.py: how
often the human has each class within EDGE_MM of the edge) into annealer targets in the
label term's format (kae.place.labels.anchors): per rotation an origin that puts the part
against its nearest edge (chosen at the seed), with a dead zone of `d0` across the edge and
the whole edge along it; a rotation whose mating side does not face that edge has its
target pushed `wrong_mm` further in, so the pull prefers the outward orientation. Off by
default (anneal_args w_edge).
"""
import math
import re

import numpy as np

EDGE_MM = 6.0

# class -> library-id / value keywords (lower case), first match wins
CLASSES = (
    ("mounting_hole", ("mountinghole", "mounting_hole", "mounting-hole", "mount_hole")),
    ("usb", ("usb",)),
    ("barrel", ("barrel", "dc_jack", "dcjack", "dc-jack", "powerjack", "power_jack")),
    ("audio", ("audio", "jack_3.5", "jack_6.35", "thonkiconn", "3.5mm", "phonejack", "pj-3", "pj3")),
    ("rf", ("sma", "u.fl", "ufl", "coax", "bnc", "mmcx", "ipex")),
    ("modular", ("rj45", "rj11", "rj12", "8p8c", "modular")),
    ("dsub", ("dsub", "d-sub", "db9", "db25", "de9", "db-9")),
    ("terminal", ("terminalblock", "terminal_block", "screw_terminal", "phoenix", "terminal")),
    ("card", ("microsd", "sd_card", "sdcard", "card", "sim_")),
    ("ffc", ("ffc", "fpc")),
    ("idc", ("idc", "box_header", "boxheader")),
    ("wire_to_board", ("jst", "molex", "picoblade", "hirose", "micro-fit", "mini-fit", "microfit", "minifit",
                       "kk_", "kk254", "xh", "_ph_", "zh_", "_sh_", "gh_", "tyco", "amp_", "wago")),
    ("header", ("pinheader", "pinsocket", "pin_header", "pin_socket", "header", "socket")),
    ("wire_pads", ("wire", "solder_pad", "solderwire")),
)


IC_SOCKET = ("package_dip", "dip-", "dip_", "plcc", "zif", "40tex", "textool", "sip-")


def fp_class(fp, kind=""):
    """The footprint's edge class, or None when it is not a connector or mounting hole (IC
    sockets are not connectors here)."""
    text = f"{fp.lib_id} {fp.value}".lower()
    lib, _, name = fp.lib_id.lower().partition(":")
    if kind not in ("connector", "mounting_hole") and not re.match(r"^(j|p|cn|con|x|h|mh)\d", fp.ref.lower()):
        return None
    if any(k in text for k in IC_SOCKET):
        return None
    # a mounting hole by its library or footprint name (a D-sub's "MountingHolesOffset" is not one)
    if any(lib.startswith(k) or name.startswith(k) for k in CLASSES[0][1]):
        return "mounting_hole"
    for cname, keys in CLASSES[1:]:
        if any(k in text for k in keys):
            return cname
    if kind == "mounting_hole":
        return "mounting_hole"
    return "connector_other" if kind == "connector" else None


def _lib_extent(fp):
    """(x0, y0, x1, y1) of the courtyard (else pads) in the library frame."""
    from .legalize import pad_shape
    import shapely
    gs = list(fp.courtyard or []) or list(fp.body or [])
    if not gs:
        gs = [pad_shape(pd) for pd in fp.pads]
    if not gs:
        return None
    return shapely.union_all(gs).bounds


def mating(fp, frac=0.2):
    """Library-frame unit vector of the side the part mates on, or None: the courtyard
    reaching past the pads' extent by more than `frac` of its size on one side only."""
    if not fp.pads:
        return None
    ext = _lib_extent(fp)
    if ext is None:
        return None
    xs = [pd.lx for pd in fp.pads]
    ys = [pd.ly for pd in fp.pads]
    px0, px1, py0, py1 = min(xs), max(xs), min(ys), max(ys)
    w, h = ext[2] - ext[0], ext[3] - ext[1]
    over = {(-1, 0): px0 - ext[0], (1, 0): ext[2] - px1, (0, -1): py0 - ext[1], (0, 1): ext[3] - py1}
    size = {(-1, 0): w, (1, 0): w, (0, -1): h, (0, 1): h}
    best = max(over, key=lambda k: over[k] / max(size[k], 1e-9))
    opp = (-best[0], -best[1])
    if over[best] <= frac * size[best] or over[best] < 2.0 * max(over[opp], 0.0) + 0.5:
        return None
    return best


def _placed_extent(fp, x, y, rot, side):
    from kae.board import transform
    from .legalize import pad_shape
    import shapely
    gs = list(fp.courtyard or []) or list(fp.body or []) or [pad_shape(pd) for pd in fp.pads]
    return shapely.union_all([transform.place_geom(g, x, y, rot, side) for g in gs]) if gs else None


def edge_distance(outline, fp, pose=None):
    """mm from the part's courtyard to the board edge (0 when it touches or crosses it)."""
    x, y, rot, side = pose or (fp.x, fp.y, fp.rot, fp.side)
    g = _placed_extent(fp, x, y, rot, side)
    if g is None or outline is None:
        return None
    if not outline.contains(g):
        return 0.0
    return float(outline.boundary.distance(g))


def faces_out(outline, fp, pose=None):
    """True / False: the mating side points at the nearest edge; None: no mating side."""
    from kae.board import transform
    from shapely.geometry import Point
    from shapely.ops import nearest_points
    m = mating(fp)
    if m is None or outline is None:
        return None
    x, y, rot, side = pose or (fp.x, fp.y, fp.rot, fp.side)
    g = _placed_extent(fp, x, y, rot, side)
    if g is None:
        return None
    c = g.centroid
    q = nearest_points(outline.boundary, c)[0]
    ox, oy = q.x - c.x, q.y - c.y
    a = transform.place_geom(Point(m[0], m[1]), 0.0, 0.0, rot, side)
    b = transform.place_geom(Point(0.0, 0.0), 0.0, 0.0, rot, side)
    return (a.x - b.x) * ox + (a.y - b.y) * oy > 0


def anchors(P, classes, weight=1.0, d0=1.0, wrong_mm=5.0, state=None):
    """Annealer targets ({part index: ([(X, Y) per rotation], (rx, ry), weight)}, the label
    term's format) pulling each movable part of `classes` against its nearest board edge:
    its courtyard `d0` mm inside the edge (dead zone d0 across the edge, the edge's whole
    length along it), the edge being the nearest of the outline's bounding box at the
    part's position in `state` (else its input pose). Rotations whose mating side does not
    face that edge aim `wrong_mm` further in."""
    from kae.board import transform
    from shapely.geometry import Point
    kinds = {p.i: getattr(p, "kind", "") for p in P.parts}
    bx0, by0, bx1, by1 = P.outline.bounds
    out = {}
    for p in P.parts:
        if not p.movable:
            continue
        cl = fp_class(p.fp, kinds.get(p.i, ""))
        if cl is None or cl not in classes:
            continue
        if state is not None:
            x = P.ox + state.X[p.i] * P.g
            y = P.oy + state.Y[p.i] * P.g
        else:
            x, y = p.x0, p.y0
        # the nearest side of the board's box: 0 left, 1 right, 2 top, 3 bottom
        d = [x - bx0, bx1 - x, y - by0, by1 - y]
        e = int(np.argmin(d))
        normal = [(-1, 0), (1, 0), (0, -1), (0, 1)][e]
        m = mating(p.fp)
        tg = []
        for r in p.rots:
            cx0, cy0, cx1, cy1 = r.crt
            if e == 0:
                tx, ty = bx0 + d0 - cx0, y
            elif e == 1:
                tx, ty = bx1 - d0 - cx1, y
            elif e == 2:
                tx, ty = x, by0 + d0 - cy0
            else:
                tx, ty = x, by1 - d0 - cy1
            if m is not None:
                a = transform.place_geom(Point(m[0], m[1]), 0.0, 0.0, r.rot, p.side)
                b = transform.place_geom(Point(0.0, 0.0), 0.0, 0.0, r.rot, p.side)
                if (a.x - b.x) * normal[0] + (a.y - b.y) * normal[1] < 0.5:
                    tx -= normal[0] * wrong_mm
                    ty -= normal[1] * wrong_mm
            tg.append((int(round((tx - P.ox) / P.g)), int(round((ty - P.oy) / P.g))))
        along = int(math.ceil(max(bx1 - bx0, by1 - by0) / P.g))
        across = max(1, int(math.ceil(d0 / P.g)))
        r = (across, along) if e in (0, 1) else (along, across)
        out[p.i] = (tg, r, float(weight))
    return out
