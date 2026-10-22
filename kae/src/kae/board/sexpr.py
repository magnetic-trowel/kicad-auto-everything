# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fast reader for KiCad S-expressions.

`parse(text)` returns nested lists: the head symbol first, atoms as `str`, quoted
strings unquoted (and unescaped). Numbers stay strings; callers convert what they use.

`strip_blocks(text, heads)` cuts blocks the board model never reads (zone fills,
embedded files) out of the text before tokenizing; on large routed boards they are
most of the bytes. A block's end is found from KiCad's pretty-printing (the closing
parenthesis sits at the opening line's indentation), checked by balanced parenthesis
counts, with an exact scan as the fallback.

Adapted from tools/research/physics/pc_refplane.py (parse, first, kids).
"""
import re

_TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')
_PAREN_OR_STR = re.compile(r'"(?:[^"\\]|\\.)*"|[()]')
_ESC = re.compile(r'\\(.)')
_ESC_MAP = {'n': '\n', 't': '\t', 'r': '\r'}

# Blocks no part of the board model reads.
SKIP_HEADS = ("filled_polygon", "fill_segments", "embedded_files")


def _unescape(tok):
    return _ESC.sub(lambda m: _ESC_MAP.get(m.group(1), m.group(1)), tok[1:-1])


def parse(text):
    """Parse one S-expression (the first in `text`) into nested lists."""
    stack = []
    cur = []
    push = stack.append
    pop = stack.pop
    for t in _TOK.findall(text):
        if t == "(":
            push(cur)
            cur = []
        elif t == ")":
            done = cur
            cur = pop()
            cur.append(done)
        elif t[0] == '"':
            cur.append(_unescape(t) if "\\" in t else t[1:-1])
        else:
            cur.append(t)
    if stack:
        raise ValueError("unbalanced S-expression: missing ')'")
    if not cur or not isinstance(cur[0], list):
        raise ValueError("no S-expression found")
    return cur[0]


def _scan_end(text, a):
    """Exact end (exclusive) of the block opening at text[a] == '('."""
    depth = 0
    for m in _PAREN_OR_STR.finditer(text, a):
        c = m.group(0)
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return m.end()
    raise ValueError("unbalanced S-expression block")


def block_end(text, a):
    """End (exclusive) of the block whose '(' is at text[a]."""
    ls = text.rfind("\n", 0, a) + 1
    indent = text[ls:a]
    if indent and not indent.strip():
        e = text.find("\n" + indent + ")", a)
        if e >= 0:
            e += len(indent) + 2
            if text.count("(", a, e) == text.count(")", a, e):
                return e
    return _scan_end(text, a)


def strip_blocks(text, heads=SKIP_HEADS):
    """Return `text` without the blocks whose head is in `heads`."""
    pat = re.compile(r"\((?:%s)(?=[\s)])" % "|".join(map(re.escape, heads)))
    out, pos = [], 0
    for m in pat.finditer(text):
        a = m.start()
        if a < pos:  # nested in a block already cut
            continue
        out.append(text[pos:a])
        pos = block_end(text, a)
    if not out:
        return text
    out.append(text[pos:])
    return "".join(out)


def kids(node, name):
    """Children of `node` with head `name`."""
    return [c for c in node if type(c) is list and c and c[0] == name]


def first(node, name):
    """First child of `node` with head `name`, or None."""
    for c in node:
        if type(c) is list and c and c[0] == name:
            return c
    return None


def value(node, name, default=None):
    """The first atom of child `name` (e.g. value(fp, 'layer') -> 'F.Cu')."""
    c = first(node, name)
    return c[1] if c is not None and len(c) > 1 else default


def flag(node, name):
    """KiCad booleans: `(name yes)`, `(name)` or a bare atom `name` are true."""
    for c in node:
        if type(c) is list:
            if c and c[0] == name:
                return len(c) < 2 or c[1] not in ("no", "false")
        elif c == name:
            return True
    return False
