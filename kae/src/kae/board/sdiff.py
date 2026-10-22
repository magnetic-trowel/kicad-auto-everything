# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural diff of two .kicad_pcb files.

Top-level objects are keyed by (head, uuid), or (head, name#ordinal) for objects
without a uuid, and compared as token trees: numbers within `tol` (mm or degrees) are
equal, and an `(at x y a)` with a = 0 mod 360 equals `(at x y)`. A footprint's items are
paired by uuid (KiCad sorts them when it saves). Zone fills are compared too.

    changes = diff("before.kicad_pcb", "after.kicad_pcb")
    # [{'kind': 'footprint', 'id': '<uuid>', 'change': 'changed', 'ref': 'R1'}, ...]

With rotation_artifacts=True, two things pcbnew does when it rotates or flips a
footprint, and does not undo when it turns it back, compare equal: an `fp_rect` turned to
an off-axis angle is stored from then on as a 4-point `fp_poly` with the same corners,
and text (fields, fp_text) angles are kept upright, so they may differ by 180 degrees.
"""
from pathlib import Path

from . import sexpr


def _key_items(tree):
    out, seen = {}, {}
    for node in tree[1:]:
        if type(node) is not list or not node:
            continue
        head = node[0]
        u = sexpr.value(node, "uuid") or sexpr.value(node, "tstamp")
        if u is None:
            name = node[1] if len(node) > 1 and type(node[1]) is str else ""
            seen[(head, name)] = seen.get((head, name), 0) + 1
            u = f"{name}#{seen[(head, name)]}"
        out[(head, u)] = node
    return out


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _norm_at(node):
    if len(node) == 4 and node[0] == "at":
        a = _num(node[3])
        if a is not None and min(a % 360.0, 360.0 - a % 360.0) < 1e-9:
            return node[:3]
    return node


def _corners(node):
    """fp_rect or 4-point fp_poly -> ['quad', sorted corners, other children...]."""
    if node[0] == "fp_rect":
        s, e = sexpr.first(node, "start"), sexpr.first(node, "end")
        if s is None or e is None:
            return None
        pts = [(s[1], s[2]), (e[1], s[2]), (e[1], e[2]), (s[1], e[2])]
        rest = [c for c in node[1:] if not (type(c) is list and c and c[0] in ("start", "end"))]
    elif node[0] == "fp_poly":
        pl = sexpr.first(node, "pts")
        if pl is None or len(pl) != 5 or any(type(c) is not list or c[0] != "xy" for c in pl[1:]):
            return None
        pts = [(c[1], c[2]) for c in pl[1:]]
        rest = [c for c in node[1:] if not (type(c) is list and c and c[0] == "pts")]
    else:
        return None
    key = sorted((round(float(x), 4) + 0.0, round(float(y), 4) + 0.0) for x, y in pts)
    return ["quad", [["c", str(x), str(y)] for x, y in key]] + rest


def _artifacts(node):
    if node[0] in ("fp_rect", "fp_poly"):
        q = _corners(node)
        if q is not None:
            return q
    if node[0] in ("property", "fp_text"):
        out = []
        for c in node:
            if type(c) is list and len(c) == 4 and c[0] == "at":
                a = _num(c[3])
                c = c[:3] if a is None or a % 180.0 == 0 else c[:3] + [str(a % 180.0)]
            out.append(c)
        return out
    return node


def _split_uuid(node):
    keyed, rest = {}, []
    for c in node[1:]:
        u = sexpr.value(c, "uuid") if type(c) is list else None
        if u is not None and u not in keyed:
            keyed[u] = c
        else:
            rest.append(c)
    return keyed, rest


def same(a, b, tol=1e-4, rotation_artifacts=False):
    """Token trees equal up to numeric tolerance."""
    if type(a) is list:
        if type(b) is not list:
            return False
        a, b = _norm_at(a), _norm_at(b)
        if rotation_artifacts and a and b:
            a, b = _artifacts(a), _artifacts(b)
        if a and b and a[0] == "footprint" and b[0] == "footprint":
            # KiCad sorts a footprint's items when it saves; pair them by uuid
            ka, ra = _split_uuid(a)
            kb, rb = _split_uuid(b)
            if ka.keys() != kb.keys() or len(ra) != len(rb):
                return False
            return (all(same(ka[u], kb[u], tol, rotation_artifacts) for u in ka)
                    and all(same(x, y, tol, rotation_artifacts) for x, y in zip(ra, rb)))
        if len(a) != len(b):
            return False
        return all(same(x, y, tol, rotation_artifacts) for x, y in zip(a, b))
    if type(b) is list:
        return False
    if a == b:
        return True
    fa, fb = _num(a), _num(b)
    return fa is not None and fb is not None and abs(fa - fb) <= tol


def diff(path_a, path_b, tol=1e-4, rotation_artifacts=False):
    """Objects added, removed or changed from file a to file b."""
    ta = sexpr.parse(Path(path_a).read_text(encoding="utf-8", errors="replace"))
    tb = sexpr.parse(Path(path_b).read_text(encoding="utf-8", errors="replace"))
    out = []
    A, B = _key_items(ta), _key_items(tb)
    for k in sorted(set(A) | set(B)):
        node = A.get(k) or B.get(k)
        rec = dict(kind=k[0], id=k[1])
        if k[0] == "footprint":
            ref = next((p[2] for p in sexpr.kids(node, "property") if len(p) > 2 and p[1] == "Reference"), "")
            rec["ref"] = ref
        if k not in A:
            out.append(dict(rec, change="added"))
        elif k not in B:
            out.append(dict(rec, change="removed"))
        elif not same(A[k], B[k], tol, rotation_artifacts and k[0] == "footprint"):
            out.append(dict(rec, change="changed"))
    return out
