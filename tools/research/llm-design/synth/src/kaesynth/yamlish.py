# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tiny YAML writer (block style) for dicts/lists/scalars; no dependency on PyYAML."""
import json
import re

_PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_./:+\-]*$")
_RESERVED = {"yes", "no", "true", "false", "on", "off", "null", "y", "n", "~"}


def scalar(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(round(v, 6))
    s = str(v)
    if _PLAIN.match(s) and s.lower() not in _RESERVED:
        return s
    return json.dumps(s, ensure_ascii=False)


def dump(obj, indent=0):
    pad = "  " * indent
    lines = []
    if isinstance(obj, dict):
        if not obj:
            return pad + "{}"
        for k, v in obj.items():
            key = scalar(k)
            if isinstance(v, (dict, list)) and v:
                if isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v) and len(v) <= 12:
                    lines.append(f"{pad}{key}: [{', '.join(scalar(x) for x in v)}]")
                else:
                    lines.append(f"{pad}{key}:")
                    lines.append(dump(v, indent + 1))
            else:
                lines.append(f"{pad}{key}: {scalar(v) if not isinstance(v, (dict, list)) else ('{}' if isinstance(v, dict) else '[]')}")
    elif isinstance(obj, list):
        if not obj:
            return pad + "[]"
        for x in obj:
            if isinstance(x, dict) and x:
                sub = dump(x, indent + 1).split("\n")
                lines.append(f"{pad}- {sub[0].lstrip()}")
                lines.extend(sub[1:])
            elif isinstance(x, list) and x:
                if all(not isinstance(y, (dict, list)) for y in x):
                    lines.append(f"{pad}- [{', '.join(scalar(y) for y in x)}]")
                else:
                    sub = dump(x, indent + 1).split("\n")
                    lines.append(f"{pad}- {sub[0].lstrip()}")
                    lines.extend(sub[1:])
            else:
                lines.append(f"{pad}- {scalar(x)}")
    else:
        return pad + scalar(obj)
    return "\n".join(lines)
