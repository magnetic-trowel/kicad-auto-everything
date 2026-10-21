# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Board file handling: project file sets and raw S-expression checks."""
import hashlib
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
