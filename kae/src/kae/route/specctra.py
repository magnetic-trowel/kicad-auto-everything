# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Specctra DSN and SES files as S-expression trees.

`parse(text)` returns nested lists: the head symbol first, atoms as `str`, quoted strings as
`Q` (a `str` that remembers it was quoted). Numbers stay strings. `dumps(tree)` writes a tree
back; a parse/dump round trip keeps every token. Specctra strings have no escapes (KiCad
replaces a double quote in a name by two single quotes), and the parser header
`(string_quote ")` holds a lone quote character, which both directions special-case.

Units: a DSN has `(resolution um 10)` and `(unit um)` in KiCad's export, so coordinates and
widths are micrometres; a SES has its own `(resolution um 10)` (tenths of a micrometre) in
`routes` and `placement`. `unit_scale(tree)` gives the factor to millimetres.
"""
import re

_TOK = re.compile(r'\(|\)|"[^"]*"|[^\s()"]+')
_DQ = "__kae_double_quote__"
_SQ_IN = re.compile(r'\(string_quote\s+"\s*\)')
_NEEDS_QUOTE = re.compile(r'[\s()"]')


class Q(str):
    """A quoted string atom."""
    __slots__ = ()


def parse(text):
    """Parse the first S-expression in `text` into nested lists."""
    text = _SQ_IN.sub(f"(string_quote {_DQ})", text)
    stack, cur = [], []
    for t in _TOK.findall(text):
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            if not stack:
                raise ValueError("unbalanced S-expression: extra ')'")
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif t[0] == '"':
            cur.append(Q(t[1:-1]))
        else:
            cur.append(t)
    if stack:
        raise ValueError("unbalanced S-expression: missing ')'")
    if not cur or not isinstance(cur[0], list):
        raise ValueError("no S-expression found")
    return cur[0]


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse(f.read())


def atom(a):
    """An atom as it is written: quoted when it was or when it has to be."""
    if a == _DQ:
        return '"'
    if isinstance(a, Q) or not a or _NEEDS_QUOTE.search(a):
        return '"' + a.replace('"', "''") + '"'
    return a


def _flat(node):
    return all(not isinstance(c, list) for c in node)


def _dump(node, ind, out):
    pad = "  " * ind
    if _flat(node):
        out.append(pad + "(" + " ".join(atom(c) for c in node) + ")")
        return
    head = []
    i = 0
    while i < len(node) and not isinstance(node[i], list):
        head.append(atom(node[i]))
        i += 1
    out.append(pad + "(" + " ".join(head))
    for c in node[i:]:
        if isinstance(c, list):
            _dump(c, ind + 1, out)
        else:
            out.append("  " * (ind + 1) + atom(c))
    out.append(pad + ")")


def dumps(tree):
    out = []
    _dump(tree, 0, out)
    return "\n".join(out) + "\n"


def write(tree, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(dumps(tree))


# ----------------------------------------------------------------------------- lookups
def find(node, head):
    """First child list of `node` whose head is `head`, or None."""
    for c in node:
        if isinstance(c, list) and c and c[0] == head:
            return c
    return None


def findall(node, head):
    return [c for c in node if isinstance(c, list) and c and c[0] == head]


def walk(node):
    """Every list in the tree, depth first (the node itself first)."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        for c in reversed(n):
            if isinstance(c, list):
                stack.append(c)


def remove(node, child):
    for i, c in enumerate(node):
        if c is child:
            del node[i]
            return True
    return False


_UNIT_PER_MM = {"um": 1000.0, "mm": 1.0, "mil": 1000.0 / 25.4, "inch": 1.0 / 25.4, "cm": 0.1}


def unit_scale(scope):
    """Units per mm of a DSN (`(unit ...)`, else `(resolution ...)` units) or of a SES
    `routes`/`placement` scope (`(resolution um 10)` -> 10000 per mm)."""
    res = find(scope, "resolution")
    unit = find(scope, "unit")
    if unit is not None and len(unit) > 1:
        return _UNIT_PER_MM.get(unit[1], 1000.0)
    if res is not None and len(res) > 2:
        return _UNIT_PER_MM.get(res[1], 1000.0) * float(res[2])
    return 1000.0


def fmt(v):
    """A number as a compact DSN token (integers without a fraction)."""
    r = round(float(v), 4)
    if abs(r - round(r)) < 1e-9:
        return str(int(round(r)))
    return f"{r:.4f}".rstrip("0").rstrip(".")
