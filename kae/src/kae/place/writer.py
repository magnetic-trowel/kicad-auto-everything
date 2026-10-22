# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write placed poses into a copy of the input board.

    write(path_in, poses, path_out, mode="auto")   # poses: {uuid: (x, y, rot, side)}

Two writers:
- `pcbnew`: kae.board.pcbnew_io.write_poses (KiCad's own Flip/SetOrientation/SetPosition),
  the reference behaviour.
- `sexpr`: a pure-Python edit of the S-expression text, for when KiCad's Python is not
  reachable (e.g. inside a sandbox without the KiCad container). It does what
  FOOTPRINT::SetOrientation + SetPosition do to the saved file for a same-side move: the
  footprint `(at x y rot)`, every pad's and text's absolute angle (+ the rotation change),
  and the board-frame points of zones the footprint owns (rotated about the old position
  and translated). Library-frame children (graphics, pad positions) are untouched. Side
  changes are not supported here (v0 keeps sides).
`auto` tries pcbnew when a KiCad Python answers quickly and falls back to sexpr.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from kae.board import transform

_TOK = re.compile(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+')


def fmt(v):
    """A number as KiCad writes it: up to 6 decimals, no trailing zeros."""
    s = f"{float(v):.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ----------------------------------------------------------------------------- spans
class _Node:
    __slots__ = ("head", "a", "b", "kids", "atoms")

    def __init__(self, head, a):
        self.head = head
        self.a = a          # offset of '('
        self.b = None       # offset after ')'
        self.kids = []
        self.atoms = []     # (text, start, end) direct atoms after the head


def _tree(text, a, b):
    """Spans of the S-expression text[a:b] (one block)."""
    root = None
    stack = []
    expect_head = False
    for m in _TOK.finditer(text, a, b):
        t = m.group(0)
        if t == "(":
            node = _Node(None, m.start())
            if stack:
                stack[-1].kids.append(node)
            stack.append(node)
            expect_head = True
        elif t == ")":
            node = stack.pop()
            node.b = m.end()
            if not stack:
                root = node
                break
        else:
            node = stack[-1]
            if expect_head:
                node.head = t
                expect_head = False
            else:
                node.atoms.append((t, m.start(), m.end()))
    return root


def _top_blocks(text):
    """(head, start, end) of each top-level child of (kicad_pcb ...)."""
    out = []
    depth = 0
    start = None
    head_next = False
    for m in _TOK.finditer(text):
        t = m.group(0)
        if t == "(":
            depth += 1
            if depth == 2:
                start = m.start()
                head_next = True
        elif t == ")":
            if depth == 2:
                out.append((head, start, m.end()))
            depth -= 1
        elif head_next:
            head = t
            head_next = False
    return out


def _child(node, head):
    for k in node.kids:
        if k.head == head:
            return k
    return None


def _uuid_of(node):
    u = _child(node, "uuid") or _child(node, "tstamp")
    if u is None or not u.atoms:
        return None
    return u.atoms[0][0].strip('"')


def _at_edit(at_node, new_angle_fn):
    """Edit the angle of an (at x y [a]) node: returns (start, end, text) or None."""
    atoms = at_node.atoms
    if len(atoms) < 2:
        return None
    x, y = atoms[0][0], atoms[1][0]
    a = float(atoms[2][0]) if len(atoms) > 2 and _is_num(atoms[2][0]) else 0.0
    rest = [t for (t, _, _) in atoms[3:]] if len(atoms) > 2 and _is_num(atoms[2][0]) else [t for (t, _, _) in atoms[2:]]
    na = new_angle_fn(a)
    parts = [x, y] + ([fmt(na)] if abs(na) > 1e-9 else []) + rest
    return (at_node.a, at_node.b, "(at " + " ".join(parts) + ")")


def _is_num(t):
    try:
        float(t)
        return True
    except ValueError:
        return False


def _norm_angle(a):
    """KiCad keeps angles in (-360, 360); write them in [0, 360)."""
    a = a % 360.0
    return 0.0 if abs(a) < 1e-9 or abs(a - 360.0) < 1e-9 else a


def edit_footprint(text, a, b, pose):
    """Edits [(start, end, replacement)] that move the footprint block text[a:b] to pose."""
    node = _tree(text, a, b)
    at = _child(node, "at")
    if at is None or len(at.atoms) < 2:
        raise ValueError("footprint without (at)")
    ox, oy = float(at.atoms[0][0]), float(at.atoms[1][0])
    orot = float(at.atoms[2][0]) if len(at.atoms) > 2 and _is_num(at.atoms[2][0]) else 0.0
    x, y, rot, side = pose
    layer = _child(node, "layer")
    cur_side = "B" if layer is not None and layer.atoms and layer.atoms[0][0].strip('"') == "B.Cu" else "F"
    if side != cur_side:
        raise ValueError("the S-expression writer does not flip footprints")
    rot = _norm_angle(rot)
    d = rot - orot
    edits = []
    parts = [fmt(x), fmt(y)] + ([fmt(rot)] if abs(rot) > 1e-9 else [])
    edits.append((at.a, at.b, "(at " + " ".join(parts) + ")"))
    for k in node.kids:
        if k.head in ("pad", "property", "fp_text"):
            kat = _child(k, "at")
            if kat is not None:
                e = _at_edit(kat, lambda ang: _norm_angle(ang + d))
                if e:
                    edits.append(e)
        elif k.head == "zone":
            edits += _zone_edits(text, k, ox, oy, x, y, d)
        elif k.head in ("fp_text_box",):
            # text boxes keep (start)/(end) in the footprint frame; their angle is absolute
            ang = _child(k, "angle")
            if ang is not None and ang.atoms:
                na = _norm_angle(float(ang.atoms[0][0]) + d)
                edits.append((ang.a, ang.b, f"(angle {fmt(na)})"))
    return edits


def _zone_edits(text, zone, ox, oy, x, y, d):
    """Board-frame points of a footprint-owned zone, rotated by d about (ox, oy) and moved."""
    edits = []

    def walk(n):
        if n.head == "xy" and len(n.atoms) >= 2:
            px, py = float(n.atoms[0][0]), float(n.atoms[1][0])
            u, v = transform.rotate(px - ox, py - oy, d)
            edits.append((n.a, n.b, f"(xy {fmt(x + u)} {fmt(y + v)})"))
            return
        if n.head in ("start", "mid", "end") and len(n.atoms) >= 2 and _is_num(n.atoms[0][0]):
            px, py = float(n.atoms[0][0]), float(n.atoms[1][0])
            u, v = transform.rotate(px - ox, py - oy, d)
            edits.append((n.a, n.b, f"({n.head} {fmt(x + u)} {fmt(y + v)})"))
            return
        for c in n.kids:
            walk(c)
    for c in zone.kids:
        if c.head in ("polygon", "filled_polygon"):
            walk(c)
    return edits


def write_sexpr(path_in, poses, path_out):
    """Pure-Python writer (see module docstring). Returns {moved}."""
    text = Path(path_in).read_text(encoding="utf-8")
    edits = []
    moved = 0
    seen = set()
    for head, a, b in _top_blocks(text):
        if head not in ("footprint", "module"):
            continue
        node_uuid = _uuid_of(_tree(text, a, b))
        if node_uuid in poses and node_uuid not in seen:
            seen.add(node_uuid)
            edits += edit_footprint(text, a, b, poses[node_uuid])
            moved += 1
    missing = set(poses) - seen
    if missing:
        raise KeyError(f"footprints not found: {sorted(missing)[:5]}")
    edits.sort(key=lambda e: e[0])
    out = []
    pos = 0
    for s, e, rep in edits:
        if s < pos:
            raise ValueError("overlapping edits")
        out.append(text[pos:s])
        out.append(rep)
        pos = e
    out.append(text[pos:])
    tmp = str(path_out) + ".tmp"
    Path(tmp).write_text("".join(out), encoding="utf-8")
    os.replace(tmp, path_out)
    return dict(moved=moved, writer="sexpr")


# ----------------------------------------------------------------------------- pcbnew
def pcbnew_ready(timeout=60):
    """True when kae.board.pcbnew_io can reach a KiCad Python (checked with a short probe)."""
    try:
        from kae.board import pcbnew_io
    except ImportError:
        return False
    cands = []
    if os.environ.get("KAE_KICAD_PYTHON") or os.environ.get("KAE_KICAD_WRAP"):
        cands = None  # trust the configured command; pcbnew_io probes it
    else:
        cands = [c for c in ("/usr/bin/python3", "/usr/bin/python3.12", "/usr/bin/python3.11") if Path(c).exists()]
        if not cands:
            return False
    if cands is not None:
        ok = False
        for c in cands:
            try:
                r = subprocess.run([c, "-c", "import pcbnew"], capture_output=True, timeout=timeout)
                ok = r.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                ok = False
            if ok:
                break
        if not ok:
            return False
    try:
        return bool(pcbnew_io.available())
    except Exception:
        return False


def write(path_in, poses, path_out, mode="auto", log=None):
    """Write poses with the chosen writer. Returns a report dict."""
    mode = os.environ.get("KAE_WRITER", mode)
    Path(path_out).parent.mkdir(parents=True, exist_ok=True)
    if mode in ("auto", "pcbnew") and pcbnew_ready():
        try:
            import inspect

            from kae.board import pcbnew_io
            pz = {u: tuple(p) for u, p in poses.items()}
            names = list(inspect.signature(pcbnew_io.write_poses).parameters)
            if len(names) >= 3 and names[1] == "poses":
                rep = pcbnew_io.write_poses(str(path_in), pz, str(path_out))
            else:
                rep = pcbnew_io.write_poses(str(path_in), str(path_out), pz)
            rep = dict(rep or {}, writer="pcbnew")
            return rep
        except Exception as e:  # fall back to the S-expression writer
            if mode == "pcbnew":
                raise
            if log:
                log(f"pcbnew writer failed ({type(e).__name__}: {e}); using the S-expression writer")
    rep = write_sexpr(path_in, poses, path_out)
    _copy_project(path_in, path_out)
    return rep


def _copy_project(path_in, path_out):
    """Keep the project files beside the output (KiCad reads rules from them)."""
    pi, po = Path(path_in), Path(path_out)
    for ext in (".kicad_pro", ".kicad_dru"):
        src = pi.with_suffix(ext)
        dst = po.with_suffix(ext)
        if src.exists() and not dst.exists() and src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
