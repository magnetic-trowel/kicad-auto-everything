# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Text-level edits of a KiCad 10 board's routing: add locked tracks and vias, list,
lock, unlock and remove routing items, add and remove guard zones, and transplant a work
board's routing onto the untouched input.

KiCad 10 files reference nets by name, and pcbnew writes a track as

    (segment (start x y) (end x y) (width w) (locked yes) (layer "F.Cu") (net "GND") (uuid "..."))

(one item per line in the file). Edits here keep every other byte of the file, so a board
written by `transplant` differs from its input only in routing, which is what a route
task allows (kaebench's transplant check). Guard zones (`kae-crit:` names, hard obstacles
for the bridge) live only on work boards.
"""
from __future__ import annotations

import math
import re
import shutil
import uuid as _uuid
from pathlib import Path

from kae.board import sexpr

ROUTING = ("segment", "arc", "via")
GUARD_PREFIX = "kae-crit:"


def fmt(v):
    """A length as KiCad writes it: at most 6 decimals (nm), no trailing zeros."""
    s = f"{float(v):.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def new_uuid():
    return str(_uuid.uuid4())


def track_sexpr(net, layer, width, a, b, uid=None, locked=True):
    lk = "\t\t(locked yes)\n" if locked else ""
    return (f"\t(segment\n\t\t(start {fmt(a[0])} {fmt(a[1])})\n\t\t(end {fmt(b[0])} {fmt(b[1])})\n"
            f"\t\t(width {fmt(width)})\n{lk}\t\t(layer {q(layer)})\n\t\t(net {q(net)})\n"
            f"\t\t(uuid {q(uid or new_uuid())})\n\t)\n")


def via_sexpr(net, x, y, size, drill, layers=("F.Cu", "B.Cu"), uid=None, locked=True):
    lk = "\t\t(locked yes)\n" if locked else ""
    ls = " ".join(q(l) for l in layers)
    return (f"\t(via\n\t\t(at {fmt(x)} {fmt(y)})\n\t\t(size {fmt(size)})\n\t\t(drill {fmt(drill)})\n"
            f"\t\t(layers {ls})\n{lk}\t\t(net {q(net)})\n\t\t(uuid {q(uid or new_uuid())})\n\t)\n")


def zone_sexpr(net, layer, rings, name, uid=None, clearance=0.0, min_thickness=0.1, priority=0):
    """A copper zone (solid pad connection, no thermals) of `net` on `layer` over the
    polygon `rings` ([outer, holes...]); KiCad fills it on the next refill."""
    def pts(r):
        return " ".join(f"(xy {fmt(x)} {fmt(y)})" for x, y in r)
    outer = rings[0]
    return (f"\t(zone\n\t\t(net {q(net)})\n\t\t(layer {q(layer)})\n\t\t(uuid {q(uid or new_uuid())})\n"
            f"\t\t(name {q(name)})\n\t\t(hatch edge 0.5)\n\t\t(priority {int(priority)})\n"
            f"\t\t(connect_pads yes\n\t\t\t(clearance {fmt(clearance)})\n\t\t)\n"
            f"\t\t(min_thickness {fmt(min_thickness)})\n\t\t(filled_areas_thickness no)\n"
            f"\t\t(fill\n\t\t\t(thermal_gap 0.5)\n\t\t\t(thermal_bridge_width 0.5)\n\t\t)\n"
            f"\t\t(polygon\n\t\t\t(pts {pts(outer)})\n\t\t)\n\t)\n")


# ----------------------------------------------------------------------------- reading
def _blocks(text, heads):
    """(head, start, end) of top-level blocks with these heads."""
    out = []
    i = 0
    n = len(text)
    pat = re.compile(r"\n\t\((" + "|".join(heads) + r")\b")
    while True:
        m = pat.search(text, i)
        if not m:
            break
        a = m.start() + 1
        b = sexpr.block_end(text, a)
        out.append((m.group(1), a, b))
        i = b
    return out


def _uuid_of(block):
    m = re.search(r'\(uuid\s+"([^"]+)"\)', block)
    return m.group(1) if m else None


def routing(path_or_text):
    """[{kind, uuid, locked, start, end}] of a board's routing items, in file order."""
    text = path_or_text if "\n" in str(path_or_text)[:200] else Path(path_or_text).read_text(encoding="utf-8")
    out = []
    for head, a, b in _blocks(text, ROUTING):
        blk = text[a:b]
        out.append(dict(kind=head, uuid=_uuid_of(blk), locked="(locked yes)" in blk, start=a, end=b))
    return out


# ----------------------------------------------------------------------------- writing
def _insert(text, chunks):
    end = text.rstrip().rfind(")")
    return text[:end] + "".join(chunks) + text[end:]


def append_items(src, dst, tracks=(), vias=(), zones=()):
    """dst = src plus tracks [(net, layer, width, a, b, uuid)], vias [(net, x, y, size,
    drill, uuid)] (locked) and zones [(net, layer, rings, name)]."""
    text = Path(src).read_text(encoding="utf-8")
    chunks = [track_sexpr(n, l, w, a, b, u) for (n, l, w, a, b, u) in tracks]
    chunks += [via_sexpr(n, x, y, D, d, uid=u) for (n, x, y, D, d, u) in vias]
    chunks += [zone_sexpr(n, l, r, name) for (n, l, r, name) in zones]
    Path(dst).write_text(_insert(text, chunks), encoding="utf-8")


def edit(src, dst, remove=(), lock=None, unlock=None, drop_guards=False):
    """dst = src with routing items `remove` (uuids) dropped, items `lock` / `unlock`
    (uuids, or 'all') locked / unlocked, and guard zones dropped."""
    text = Path(src).read_text(encoding="utf-8")
    remove = set(remove or ())
    out, pos = [], 0
    heads = ROUTING + (("zone",) if drop_guards else ())
    for head, a, b in _blocks(text, heads):
        blk = text[a:b]
        if head == "zone":
            if GUARD_PREFIX in blk:
                out.append(text[pos:a])
                pos = _eat_newline(text, b)
            continue
        u = _uuid_of(blk)
        if u in remove:
            out.append(text[pos:a])
            pos = _eat_newline(text, b)
            continue
        new = blk
        if lock is not None and (lock == "all" or u in lock) and "(locked yes)" not in blk:
            new = _set_locked(blk, True)
        elif unlock is not None and (unlock == "all" or u in unlock) and "(locked yes)" in blk:
            new = _set_locked(blk, False)
        if new is not blk:
            out.append(text[pos:a])
            out.append(new)
            pos = b
    out.append(text[pos:])
    Path(dst).write_text("".join(out), encoding="utf-8")


def _eat_newline(text, b):
    return b + 1 if b < len(text) and text[b] == "\n" else b


def _set_locked(blk, locked):
    if locked:
        # after the width/size line, as pcbnew writes it
        m = re.search(r"\n(\t+)\((width|size) [^)]*\)", blk)
        if m:
            k = m.end()
            return blk[:k] + f"\n{m.group(1)}(locked yes)" + blk[k:]
        return blk[:-1] + " (locked yes))"
    return re.sub(r"\n\t+\(locked yes\)", "", blk).replace(" (locked yes)", "")


def transplant(work, inp, dst):
    """dst = inp plus every routing item of `work` (the route task's allowed change)."""
    wt = Path(work).read_text(encoding="utf-8")
    it = Path(inp).read_text(encoding="utf-8")
    have = {_uuid_of(it[a:b]) for _, a, b in _blocks(it, ROUTING)}
    chunks = []
    for head, a, b in _blocks(wt, ROUTING):
        blk = wt[a:b]
        if _uuid_of(blk) in have:
            continue
        chunks.append("\t" + blk + "\n")
    Path(dst).write_text(_insert(it, chunks), encoding="utf-8")
    return len(chunks)


def stage(board, dst_dir, name="board"):
    """Copy a board and its project files (.kicad_pro, .kicad_dru, .kicad_prl) into dst_dir
    as <name>.*; returns the new board path."""
    src = Path(board)
    d = Path(dst_dir)
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{name}.kicad_pcb"
    if src.resolve() != out.resolve():
        shutil.copy2(src, out)
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        s = src.with_suffix(ext)
        t = d / f"{name}{ext}"
        if s.exists() and s.resolve() != t.resolve():
            shutil.copy2(s, t)
    return out


def segment_length(a, b):
    return math.dist(a, b)
