# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Engineering-notation values: '4k7', '10u', '2.2nF', '0R1', '1M' -> float."""
import re

PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3,
          "M": 1e6, "G": 1e9, "R": 1.0, "": 1.0}
_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([pnuµmkKMGR]?)([0-9]*)\s*([A-Za-zΩ]*)\s*$")


def parse_value(s):
    """Numeric value of a component value string, or None if it is not a plain value."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = _RE.match(str(s).split()[0] if str(s).split() else "")
    if not m:
        return None
    num, pre, frac, unit = m.groups()
    if unit and unit.lower() not in ("f", "h", "ohm", "ohms", "Ω", "r", "v", "a", "w", "hz"):
        return None
    if pre == "m" and unit == "" and frac == "":
        pass  # "10m" = milli
    val = float(num + ("." + frac if frac else ""))
    return val * PREFIX[pre]


def fmt_si(v, unit=""):
    if v == 0:
        return f"0{unit}"
    for p, f in (("G", 1e9), ("M", 1e6), ("k", 1e3), ("", 1), ("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if abs(v) >= f:
            return f"{v / f:.3g}{p}{unit}"
    return f"{v:.3g}{unit}"
