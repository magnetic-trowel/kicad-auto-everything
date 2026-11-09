#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep only the listed nets in a Specctra DSN: other nets lose their (net ...) entries, class memberships and planes.

Their pins stay, as obstacles with no net: Freerouting then routes only the bus nets, with every other pad in the way.
Usage: filter_dsn.py DSN KEEP_FILE (one net name per line). Exits non-zero, leaving DSN untouched, if it would keep no net."""
import json
import sys


def _skip_string(t, i):
    i += 1
    while i < len(t):
        if t[i] == '"':
            if t[i + 1:i + 2] == '"':     # doubled quote inside a string
                i += 2
                continue
            return i + 1
        i += 1
    return i


def _node_end(t, i):
    """Index just past the parenthesised node starting at i."""
    depth = 0
    while i < len(t):
        c = t[i]
        if c == '"':
            i = _skip_string(t, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced DSN")


def _token(t, i):
    """(token, start, end) of the atom at or after i, or (None, i, i) at a '(' or ')'."""
    while i < len(t) and t[i].isspace():
        i += 1
    if i >= len(t) or t[i] in "()":
        return None, i, i
    if t[i] == '"':
        j = _skip_string(t, i)
        return t[i + 1:j - 1].replace('""', '"'), i, j
    j = i
    while j < len(t) and not t[j].isspace() and t[j] not in "()":
        j += 1
    return t[i:j], i, j


def _children(t, i):
    """Spans of the direct parenthesised children of the node at i."""
    end = _node_end(t, i)
    j = i + 1
    while j < end - 1:
        if t[j] == '"':
            j = _skip_string(t, j)
        elif t[j] == "(":
            k = _node_end(t, j)
            yield j, k
            j = k
        else:
            j += 1


def _find(t, head, start=0):
    i = start
    while True:
        i = t.find("(" + head, i)
        if i < 0:
            return -1
        c = t[i + 1 + len(head)]
        if c.isspace() or c in '(")':
            return i
        i += 1


def filter_text(t, keep):
    """The DSN text with only the kept nets; (new text, kept nets, removed nets)."""
    edits = []    # (start, end, replacement)
    net_i = _find(t, "network")
    kept, removed = set(), set()
    for s, e in _children(t, net_i):
        name, _a, b = _token(t, s + 1)
        if name == "net":
            nname, _a2, _b2 = _token(t, b)
            if nname in keep:
                kept.add(nname)
            else:
                removed.add(nname)
                edits.append((s, e, ""))
        elif name == "class":
            cname, _a2, j = _token(t, b)
            # nets listed after the class name, until its first parenthesised child
            start = j
            while True:
                tok, a2, b2 = _token(t, j)
                if tok is None:
                    break
                if tok not in keep:
                    edits.append((a2, b2, ""))
                j = b2
    struct = _find(t, "structure")
    if struct >= 0:
        for s, e in _children(t, struct):
            name, _a, b = _token(t, s + 1)
            if name == "plane":
                nname, _a2, _b2 = _token(t, b)
                if nname not in keep:
                    edits.append((s, e, ""))
    edits.sort(reverse=True)
    for s, e, r in edits:
        t = t[:s] + r + t[e:]
    return t, kept, removed


def main():
    dsn, keep_file = sys.argv[1], sys.argv[2]
    with open(keep_file) as f:
        keep = {ln.rstrip("\n") for ln in f if ln.strip()}
    with open(dsn) as f:
        text = f.read()
    new, kept, removed = filter_text(text, keep)
    if not kept:
        print(f"filter_dsn: none of the {len(keep)} listed nets is in the DSN", file=sys.stderr)
        return 7
    with open(dsn, "w") as f:
        f.write(new)
    with open("busfilter.json", "w") as f:
        json.dump(dict(kept=len(kept), removed=len(removed), listed=len(keep), missing=sorted(keep - kept)[:50]), f)
    print(f"filter_dsn: kept {len(kept)} nets of {len(keep)} listed, removed {len(removed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
