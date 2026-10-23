# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal S-expression reader/writer for KiCad files.

Lists are Python lists. Unquoted tokens are `Sym` (a str subclass), quoted strings are
plain `str`, so a parse/dump round trip keeps KiCad's quoting.
"""
import re


class Sym(str):
    """An unquoted atom (keyword or number)."""
    __slots__ = ()


_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)
_UNESCAPE = re.compile(r'\\(.)')


def loads(text):
    """Parse the first S-expression in `text`."""
    stack, cur, pos, n = [], None, 0, len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip():
                raise ValueError(f"bad s-expression near offset {pos}: {text[pos:pos + 40]!r}")
            break
        pos = m.end()
        if m.group(1):
            new = []
            if cur is not None:
                cur.append(new)
                stack.append(cur)
            cur = new
        elif m.group(2):
            if cur is None:
                raise ValueError("unbalanced ')'")
            if not stack:
                return cur
            cur = stack.pop()
        elif m.group(3) is not None:
            cur.append(_UNESCAPE.sub(lambda e: {"n": "\n", "t": "\t"}.get(e.group(1), e.group(1)),
                                     m.group(3)))
        else:
            cur.append(Sym(m.group(4)))
    raise ValueError("unterminated s-expression")


def quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _atom(x):
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        return fmt_num(x)
    return quote(str(x))


def fmt_num(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def dumps(node, indent=0):
    """KiCad-style pretty printer: atoms stay on the head line, sublists go below."""
    if not isinstance(node, list):
        return _atom(node)
    pad = "\t" * indent
    head = [_atom(x) for x in node if not isinstance(x, list)]
    subs = [x for x in node if isinstance(x, list)]
    # keep short leaf-only lists on one line, e.g. (at 1 2 0) or (xy 1 2)
    if not subs:
        return pad + "(" + " ".join(head) + ")"
    if all(not any(isinstance(y, list) for y in s) for s in subs) and len(subs) <= 4 and \
            sum(len(s) for s in subs) <= 10 and node and node[0] in ("pts", "font"):
        return pad + "(" + " ".join(head + [dumps(s).strip() for s in subs]) + ")"
    first = next(i for i, x in enumerate(node) if isinstance(x, list))
    out = [pad + "(" + " ".join(_atom(x) for x in node[:first])]
    for x in node[first:]:
        out.append(dumps(x, indent + 1) if isinstance(x, list) else "\t" * (indent + 1) + _atom(x))
    out.append(pad + ")")
    return "\n".join(out)


def find(node, key):
    """First direct child list whose head is `key`."""
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def S(*items):
    """Build a list node; str heads become Sym."""
    out = []
    for i, x in enumerate(items):
        if i == 0 and isinstance(x, str) and not isinstance(x, Sym):
            x = Sym(x)
        out.append(x)
    return out
