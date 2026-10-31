# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Quantities in an intent: "27 mV", "-180 dBm/Hz", "2 mW_eq/mV". A quantity parses to (SI value, dimension);
a rate to (currency per SI unit of its dimension). Errors say what would be accepted."""
from __future__ import annotations

import math
import re

PREFIX = {"G": 1e9, "M": 1e6, "k": 1e3, "": 1.0, "m": 1e-3, "u": 1e-6, "µ": 1e-6, "n": 1e-9, "p": 1e-12}
# dimension -> base unit names (with SI prefixes allowed)
BASE = {"V": "V", "A": "A", "W": "W", "K": "K", "Ohm": "Ohm", "Ω": "Ohm", "H": "H", "F": "F", "Hz": "Hz", "s": "s",
        "m": "m"}
# logarithmic units: dimension name -> (linear dimension, reference in SI, 10 or 20 log)
LOG = {"dBuV": ("V", 1e-6, 20), "dBµV": ("V", 1e-6, 20), "dBV": ("V", 1.0, 20), "dBm": ("W", 1e-3, 10),
       "dBuV/m": ("V/m", 1e-6, 20), "dBµV/m": ("V/m", 1e-6, 20), "dB": ("ratio", 1.0, 20)}
CURRENCY = {"W_eq": 1.0, "mW_eq": 1e-3, "uW_eq": 1e-6, "µW_eq": 1e-6}
_NUM = r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"


class UnitError(ValueError):
    pass


def unit(u):
    """(factor to SI, dimension) of a unit name such as mV, kHz, mOhm, dBuV, K; logarithmic units keep
    their own dimension (values in them are compared in dB)."""
    u = u.strip()
    if u in LOG:
        return 1.0, u
    if u in ("°C", "degC", "C"):
        return 1.0, "K"                      # a temperature rise or a limit in Celsius: same steps
    for base, dim in sorted(BASE.items(), key=lambda kv: -len(kv[0])):
        if u.endswith(base):
            p = u[: -len(base)]
            if p in PREFIX:
                return PREFIX[p], dim
    raise UnitError(f"unit '{u}' unknown: use V, A, W, K (or °C), Ohm, H, F, Hz, s with a prefix G M k m u n p, "
                    f"or one of {', '.join(LOG)}")


def quantity(text):
    """'27 mV' -> (0.027, 'V'); '-180 dBm' -> (-180.0, 'dBm'); a bare number is dimensionless."""
    if isinstance(text, (int, float)):
        return float(text), ""
    m = re.fullmatch(r"\s*" + _NUM + r"\s*(\S*)\s*", str(text))
    if not m:
        raise UnitError(f"'{text}' is not a quantity: write a number and a unit, e.g. '27 mV' or '-180 dBm'")
    v, u = float(m.group(1)), m.group(2)
    if not u:
        return v, ""
    k, dim = unit(u)
    return v * k, dim


def rate(text, currency):
    """'2 mW_eq/mV' -> currency units per SI unit of V (here 2000 mW_eq per V); per a log unit: per dB."""
    m = re.fullmatch(r"\s*" + _NUM + r"\s*(\S+)/(\S+)\s*", str(text))
    if not m:
        raise UnitError(f"'{text}' is not a rate: write e.g. '2 mW_eq/mV' (the intent's currency per unit of the "
                        f"quantity)")
    v, cur, per = float(m.group(1)), m.group(2), m.group(3)
    if cur not in CURRENCY:
        raise UnitError(f"rate '{text}': '{cur}' is not a currency; use {', '.join(CURRENCY)}")
    if per in ("dB", "K", "°C") or per in LOG:
        k, dim = 1.0, ("dB" if per in LOG or per == "dB" else "K")
    else:
        k, dim = unit(per)
    return v * CURRENCY[cur] / CURRENCY[currency] / k, dim


def to_log(value_si, log_unit):
    """An SI value (V, W, V/m) in a logarithmic unit."""
    _, ref, n = LOG[log_unit]
    return n * math.log10(max(abs(value_si), 1e-30) / ref)


def fmt(value_si, dim):
    """A readable string for an SI value of a dimension."""
    if dim in LOG or dim in ("dB", ""):
        return f"{value_si:.4g} {dim}".strip()
    a = abs(value_si)
    for p, k in (("G", 1e9), ("M", 1e6), ("k", 1e3), ("", 1.0), ("m", 1e-3), ("µ", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if a >= k or k == 1e-12:
            if dim == "K" and p:
                return f"{value_si:.4g} K"
            return f"{value_si / k:.4g} {p}{dim}"
    return f"{value_si:.4g} {dim}"
