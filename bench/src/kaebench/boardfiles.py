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
                start, d = i, 0
                j = i
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
                            return text[start:j + 1]
                    j += 1
                return None
        elif c == ")":
            depth -= 1
        i += 1
    return None


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
    netclass width and the router then draws tracks the board's own DRC rejects. A netclass
    with no track width at all (the project file omits it) exports as `(width -0.001)`.
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

    text = re.sub(r"\(width\s+(-?[0-9.]+)\)", bump, text)
    Path(dsn_path).write_text(text, encoding="utf-8")
    return raised


def _paren_block(text, start):
    """The balanced `(...)` starting at text[start] (Specctra via padstacks hold no quoted parens)."""
    depth = 0
    for j in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[j], 0)
        if depth == 0:
            return text[start:j + 1]
    return None


def fix_dsn_unsized_vias(dsn_path, diameter_mm, drill_mm):
    """Give vias that KiCad exported without a size the board's minimum via size.

    A netclass with no via diameter or drill (the project file omits them) exports as padstack
    `Via[0-1]_-0.001:-0.001_um` with `(circle F.Cu -0.001)` shapes. The router then places
    zero-size vias and KiCad's SES import reads the drill from the padstack name, so both the
    shapes and the name are rewritten. Returns the number of padstacks fixed.
    """
    if not diameter_mm or not drill_mm or diameter_mm <= 0 or drill_mm <= 0:
        return 0
    text = Path(dsn_path).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"\(unit\s+(\w+)\)", text)
    scale = _DSN_UNIT_PER_MM.get(m.group(1) if m else "um", 1000.0)
    names = set(re.findall(r'"?(Via\[\d+-\d+\]_(-?[0-9.]+):(-?[0-9.]+)_um)"?', text))
    fixed = 0
    for name, dia, drill in sorted(names):
        if float(dia) > 0 and float(drill) > 0:
            continue
        new = f"Via[{name[4:name.index(']')]}]_{diameter_mm * 1000:g}:{drill_mm * 1000:g}_um"
        start = text.find(f'(padstack "{name}"')
        if start < 0:
            start = text.find(f"(padstack {name}")
        blk = _paren_block(text, start) if start >= 0 else None
        if blk:
            shapes = re.sub(r"(\(circle\s+\S+\s+)-?[0-9.]+", lambda mo: f"{mo.group(1)}{diameter_mm * scale:g}", blk)
            text = text.replace(blk, shapes, 1)
        text = text.replace(name, new)
        fixed += 1
    Path(dsn_path).write_text(text, encoding="utf-8")
    return fixed


def ses_complete(path):
    """True if a Specctra session file is a whole s-expression (not cut off mid-write)."""
    text = re.sub(r'"[^"]*"', "", Path(path).read_text(errors="replace"))
    depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return not text[i + 1:].strip()
            if depth < 0:
                return False
    return False


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


def quote_ses_net_names(ses_path):
    """Quote every bare net name in a Specctra session, in place; return how many.

    KiCad writes a net like `ADD|SUB` bare in the DSN and Freerouting echoes it bare in
    `(net ADD|SUB ...)`, but KiCad 10's SES import then rejects the whole session
    ("ImportSpecctraSES failed"); the same name in double quotes imports onto the right net.
    """
    text = Path(ses_path).read_text(encoding="utf-8", errors="replace")
    text, n = re.subn(r'\(net(\s+)([^\s"()]+)', r'(net\1"\2"', text)
    Path(ses_path).write_text(text, encoding="utf-8")
    return n


def unblock_all_power_dsn(dsn_path):
    """When every copper layer of a Specctra DSN is `(type power)`, make them signal layers.

    KiCad exports its "power" layer type as Specctra `power`, but KiCad routes tracks on
    such layers while Freerouting treats them as planes only. With no signal layer left it
    refuses the board ("all layers are disabled"; 2.5.0 then hangs instead of exiting).
    Boards that still have a signal layer are left alone. Returns the layers changed.
    """
    text = Path(dsn_path).read_text(encoding="utf-8", errors="replace")
    kinds = re.findall(r"\(layer\s+(?:\"[^\"]*\"|[^\s()]+)\s+\(type\s+(\w+)\)", text)
    if not kinds or any(k != "power" for k in kinds):
        return 0
    text, n = re.subn(r"(\(layer\s+(?:\"[^\"]*\"|[^\s()]+)\s+\(type\s+)power\)", r"\1signal)", text)
    Path(dsn_path).write_text(text, encoding="utf-8")
    return n
