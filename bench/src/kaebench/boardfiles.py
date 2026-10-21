# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Board file handling: project file sets and raw S-expression checks."""
import hashlib
import re
import shutil
from pathlib import Path

STEM = "board"
PROJECT_EXTS = (".kicad_pro", ".kicad_dru")


def board_path(d):
    return Path(d) / f"{STEM}.kicad_pcb"


def install_rules(rules_dir, dest_dir):
    """Copy the project files that carry design rules next to board.kicad_pcb in dest_dir.

    The scorer always installs the reference rules, so a method cannot change the
    rules it is judged by.
    """
    dest_dir = Path(dest_dir)
    for ext in PROJECT_EXTS:
        src = Path(rules_dir) / f"{STEM}{ext}"
        dst = dest_dir / f"{STEM}{ext}"
        if dst.exists():
            dst.unlink()
        if src.exists():
            shutil.copy2(src, dst)


def copy_board(src_dir, dest_dir):
    """Copy board.kicad_pcb and its project files from src_dir to dest_dir."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(board_path(src_dir), board_path(dest_dir))
    install_rules(src_dir, dest_dir)
    return board_path(dest_dir)


def top_level_block(text, head):
    """Return the text of the first top-level `(head ...)` block in a KiCad S-expression."""
    depth, i, n = 0, 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
            if depth == 2 and text.startswith(head, i + 1) and not text[i + 1 + len(head)].isalnum():
                end = block_end(text, i)
                return None if end is None else text[i:end]
        elif c == ")":
            depth -= 1
        i += 1
    return None


def block_end(text, start):
    """Index just past the S-expression block opening at text[start] == "(", or None."""
    d, j, n = 0, start, len(text)
    s_in = False
    while j < n:
        cj = text[j]
        if s_in:
            if cj == "\\":
                j += 1
            elif cj == '"':
                s_in = False
        elif cj == '"':
            s_in = True
        elif cj == "(":
            d += 1
        elif cj == ")":
            d -= 1
            if d == 0:
                return j + 1
        j += 1
    return None


_ZONE_LAYER = re.compile(r'\(layer "([^"]+)"\)')
_ZONE_UUID = re.compile(r'\(uuid "([^"]+)"\)')


def art_zones_to_polys(text):
    """Turn net-less zones on non-copper layers into filled graphic polygons.

    The Eagle importer makes a zone of every <rectangle>, and bitmap logos are often
    drawn as tens of thousands of silkscreen rectangles; DRC on such boards takes
    100+ GB of RAM. As graphics they keep their shape and DRC treats them as silkscreen.
    Returns (new_text, number_converted).
    """
    out, pos, n_conv = [], 0, 0
    depth, i, n = 0, 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
            if depth in (2, 3) and text.startswith("zone", i + 1) and text[i + 5].isspace():
                end = block_end(text, i)
                zone = text[i:end]
                layer = _ZONE_LAYER.search(zone)
                pi = zone.find("(pts", zone.find("(polygon"))
                if (layer and not layer.group(1).endswith(".Cu") and pi >= 0
                        and "(keepout" not in zone and "(net " not in zone):
                    uid = _ZONE_UUID.search(zone)
                    kw = "gr_poly" if depth == 2 else "fp_poly"
                    out += [text[pos:i], f'({kw} {zone[pi:block_end(zone, pi)]} (stroke (width 0) (type solid)) '
                            f'(fill yes) (layer "{layer.group(1)}")' + (f' (uuid "{uid.group(1)}")' if uid else "") + ")"]
                    pos, n_conv = end, n_conv + 1
                i, depth = end, depth - 1
                continue
        elif c == ")":
            depth -= 1
        i += 1
    out.append(text[pos:])
    return "".join(out), n_conv


def block_hash(pcb, head):
    text = Path(pcb).read_text(encoding="utf-8", errors="replace")
    blk = top_level_block(text, head)
    if blk is None:
        return None
    return hashlib.sha256(" ".join(blk.split()).encode()).hexdigest()


_DSN_UNIT_PER_MM = {"um": 1000.0, "mm": 1.0, "mil": 1000.0 / 25.4, "inch": 1.0 / 25.4, "cm": 0.1}


def clamp_dsn_widths(dsn_path, min_width_mm):
    """Raise every `(width X)` rule in a Specctra DSN to at least the board's minimum track width.

    Some projects give a netclass a track width below the board minimum; KiCad exports the
    netclass width and the router then draws tracks the board's own DRC rejects.
    Returns the number of widths raised.
    """
    text = Path(dsn_path).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"\(unit\s+(\w+)\)", text)
    scale = _DSN_UNIT_PER_MM.get(m.group(1) if m else "um", 1000.0)
    floor = min_width_mm * scale
    raised = 0

    def bump(mo):
        nonlocal raised
        w = float(mo.group(1))
        if w + 1e-9 < floor:
            raised += 1
            return f"(width {floor:g})"
        return mo.group(0)

    text = re.sub(r"\(width\s+([0-9.]+)\)", bump, text)
    Path(dsn_path).write_text(text, encoding="utf-8")
    return raised


def strip_ses_placement(ses_in, ses_out):
    """Drop the `(placement ...)` block of a Specctra session.

    KiCad 10's SES import applies the placement block (moving and flipping parts) and
    aborts on duplicate references; a router must only add copper.
    """
    text = Path(ses_in).read_text(encoding="utf-8", errors="replace")
    blk = top_level_block(text, "placement")
    if blk is not None:
        text = text.replace(blk, "", 1)
    Path(ses_out).write_text(text, encoding="utf-8")
    return blk is not None
