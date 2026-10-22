# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Parse the free-text facts a board file carries: component values, packages, net names.

Everything here is a pure function of one string. Parsers return None when the text does
not say; they never guess a unit (a bare "100" on a capacitor is unreadable, "0.1" is uF by
the common convention). Callers attach the matched text as evidence.

- `capacitance`, `resistance`, `inductance`, `frequency`: SI values from a value field
  ("100nF/50V", "4u7", "0R05", "10uH 3A", "32.768kHz").
- `rated_voltage`: a capacitor's voltage rating ("10uF 25V") or a field ("Voltage": "16V").
- `net_voltage`: nominal voltage from a rail name ("+3V3", "VCC_12V", "1V8", "-12V").
- `package`: imperial chip size and body class from a footprint name ("C_0402_1005Metric",
  "CAPC1608X90N", "CP_Elec_6.3x5.4").
- `clean_net`: a net name without its sheet path and KiCad escapes ("~{RESET}" -> "RESET",
  with the active-low flag; "{slash}" -> "/"), upper case.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_MICRO = str.maketrans({'µ': 'u', 'μ': 'u'})
_SEP = re.compile(r'[_/,;|()\[\]]+')

_PKG_IMPERIAL = ('01005', '0201', '0402', '0603', '0805', '1008', '1206', '1210', '1806', '1812',
                 '2010', '2220', '2512', '2920')
_METRIC_TO_IMPERIAL = {'0402': '01005', '0603': '0201', '1005': '0402', '1608': '0603', '2012': '0805',
                       '2520': '1008', '3216': '1206', '3225': '1210', '4532': '1812', '5025': '2010',
                       '5750': '2220', '6332': '2512'}
_CHIP_AREA = {'01005': 0.08, '0201': 0.18, '0402': 0.5, '0603': 1.28, '0805': 2.5, '1008': 5.0,
              '1206': 5.12, '1210': 8.0, '1806': 7.2, '1812': 14.4, '2010': 12.5, '2220': 28.5,
              '2512': 20.0, '2920': 37.5}
_PKG_RE = re.compile(r'(?<![\d.])(' + '|'.join(_PKG_IMPERIAL) + r')(?![\d.])')
_IPC_RE = re.compile(r'(?:CAP|RES|IND|LED|DIO)[CM]?(\d{4})X', re.I)
_METRIC_RE = re.compile(r'(\d{4})Metric', re.I)


def _norm(text: str | None) -> str:
    return (text or '').translate(_MICRO).strip()


# ------------------------------------------------------------------ component values
def capacitance(text: str | None) -> float | None:
    """Farads from a capacitor value ('100nF', '0.1uF/16V', '4u7', '22p', '1µF', '0.1')."""
    v = _SEP.sub(' ', _norm(text))
    if not v:
        return None
    mult = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'U': 1e-6, 'N': 1e-9, 'P': 1e-12}
    m = re.search(r'(?<![\w.])(\d+)([pnu])(\d+)(?:F)?(?![\w.])', v)            # 4u7, 2n2, 4p7
    if m:
        return float(f"{m.group(1)}.{m.group(3)}") * mult[m.group(2)]
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*([pnuPNU])(?:F|f)?(?![a-zA-Z])', v)
    if m:
        return float(m.group(1)) * mult[m.group(2)]
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*[mM][fF](?![a-zA-Z])', v)          # 1mF
    if m:
        return float(m.group(1)) * 1e-3
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*F(?![a-zA-Z])', v)                 # 1F, 0.47F supercaps
    if m:
        return float(m.group(1))
    m = re.fullmatch(r'\s*(0?\.\d+)\s*', v)                                         # bare 0.1 -> uF
    if m:
        return float(m.group(1)) * 1e-6
    return None


def resistance(text: str | None) -> float | None:
    """Ohms from a resistor value ('10k', '4K7', '0R05', 'R010', '50m', '2.2 kOhm', '0', '1M').

    Package codes are removed first so '10k/0402' does not read as 0.0402 ohm."""
    v = _norm(text).replace('Ω', 'R').replace('Ohm', 'R').replace('ohm', 'R').replace('OHM', 'R')
    v = _PKG_RE.sub(' ', _SEP.sub(' ', v))
    if not v.strip():
        return None
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*m(?:R)?(?![\w])', v)                # 50m, 50mR
    if m:
        return float(m.group(1)) * 1e-3
    m = re.search(r'(?<![\w.])(\d+)R(\d+)(?![\w.])', v)                              # 0R05, 2R2
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.search(r'(?<![\w.])R(\d+)(?![\w.])', v)                                   # R050
    if m:
        return float(f"0.{m.group(1)}")
    m = re.search(r'(?<![\w.])(\d+)([kKM])(\d+)(?![\w.])', v)                        # 4K7, 1M5
    if m:
        return float(f"{m.group(1)}.{m.group(3)}") * {'k': 1e3, 'K': 1e3, 'M': 1e6}[m.group(2)]
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*([kKM])?\s*R?(?![\w.])', v)
    if m:
        return float(m.group(1)) * {None: 1.0, 'k': 1e3, 'K': 1e3, 'M': 1e6}[m.group(2)]
    return None


def inductance(text: str | None) -> float | None:
    """Henries from an inductor value ('10uH', '4.7 uH', '2u2', '33n', 'IND_2.2UH_20%')."""
    v = _SEP.sub(' ', _norm(text))
    if not v:
        return None
    mult = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}
    m = re.search(r'(?<![\w.])(\d+)([nu])(\d+)(?:H)?(?![\w.])', v)                  # 2u2, 2u2H
    if m:
        return float(f"{m.group(1)}.{m.group(3)}") * mult[m.group(2)]
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*([pnumPNUM])H(?![a-zA-Z])', v)       # 10uH, 2.2UH, 1mH
    if m:
        return float(m.group(1)) * mult[m.group(2).lower()]
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*([nu])(?![a-zA-Z])', v)              # 10u, 33n
    if m:
        return float(m.group(1)) * mult[m.group(2)]
    return None


def frequency(text: str | None) -> float | None:
    """Hertz from a crystal or oscillator value ('8MHz', '32.768kHz', '32768Hz', '32k768', '12M')."""
    v = _SEP.sub(' ', _norm(text))
    m = re.search(r'(\d+(?:\.\d+)?)\s*([kKmMgG])?[hH][zZ]', v)
    if m:
        return float(m.group(1)) * {None: 1.0, 'k': 1e3, 'K': 1e3, 'm': 1e6, 'M': 1e6, 'g': 1e9, 'G': 1e9}[m.group(2)]
    m = re.search(r'(?<![\w.])(\d+)k(\d+)(?![\w.])', v)                             # 32k768
    if m:
        return float(f"{m.group(1)}.{m.group(2)}") * 1e3
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*M(?![\w.])', v)                      # 12M
    if m:
        return float(m.group(1)) * 1e6
    return None


def rated_voltage(text: str | None) -> float | None:
    """A voltage rating from a value or field ('10uF 25V', '100n/50V', '6.3V', '16 V')."""
    v = _SEP.sub(' ', _norm(text))
    m = re.search(r'(?<![\w.])(\d+(?:\.\d+)?)\s*[vV](?![a-zA-Z0-9])', v)
    if m:
        return float(m.group(1))
    m = re.search(r'(?<![\w.])(\d+)[vV](\d+)(?![\w.])', v)                            # 6V3
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    return None


# ------------------------------------------------------------------ net names
_ESC_RE = re.compile(r'\{(slash|SLASH|plus|minus|dblquote|quote|lt|gt|colon|space|backslash|tab|return)\}')
_ESC_MAP = {'slash': '/', 'plus': '+', 'minus': '-', 'dblquote': '"', 'quote': "'", 'lt': '<', 'gt': '>',
            'colon': ':', 'space': ' ', 'backslash': '\\', 'tab': ' ', 'return': ' '}


def split_sheet(name: str | None) -> str:
    """The net's own name without its hierarchical sheet path ('/Power/+3V3' -> '+3V3')."""
    if not name:
        return ''
    n = name
    if n.startswith('/') or ('/' in n and not n.startswith(('Net-(', 'unconnected-('))):
        n = n.rsplit('/', 1)[-1]
    return n


@dataclass(frozen=True)
class NetName:
    raw: str
    short: str           # without the sheet path, escapes resolved, upper case
    active_low: bool     # an overbar (~{...}), a leading n/N_ or a trailing _N/_B
    auto: bool           # KiCad's generated "Net-(R1-Pad2)" name: carries no designer intent
    unconnected: bool    # KiCad's "unconnected-(...)" single-pad net


def clean_net(name: str | None) -> NetName:
    raw = name or ''
    auto = raw.startswith('Net-(') or '/Net-(' in raw
    unc = raw.startswith('unconnected-(') or '/unconnected-(' in raw
    s = split_sheet(raw)
    low = '~{' in s
    s = re.sub(r'~\{([^}]*)\}', r'\1', s)
    s = re.sub(r'_\{([^}]*)\}', r'_\1', s)
    s = _ESC_RE.sub(lambda m: _ESC_MAP[m.group(1).lower()], s)
    s = s.replace('{', '').replace('}', '').strip()
    up = s.upper()
    if not low and (re.match(r'^N(?=[A-Z]{3})|^N_', up) and re.search(r'RST|RESET|CS|EN|INT|IRQ|OE|WE|RD|WR|FAULT|PG|SHDN|BOOT', up)):
        low = True
    if not low and re.search(r'_(N|B|L)$', up) and re.search(r'RST|RESET|CS|EN|INT|IRQ|OE|WE|FAULT|SHDN', up):
        low = True
    return NetName(raw=raw, short=up, active_low=low, auto=auto, unconnected=unc)


def net_voltage(name: str | None) -> tuple[float, str] | None:
    """Nominal volts from a rail name and the text that said so, or None.

    '+3V3' 3.3; '3.3V' 3.3; '1V8' 1.8; 'VCC_12V' 12; '12V0' 12.0; 'P3V3' 3.3; '-12V' -12;
    '+5VA' 5. Names without a digit-V pattern ('VCC', 'VBUS') return None."""
    n = clean_net(name).short
    if not n:
        return None
    neg = n.startswith('-') or re.match(r'^(N|NEG|M)\d', n) is not None or 'NEG' in n

    def prefix_ok(i):
        # the digits must start the name or follow a separator, a sign, P/N, or a supply word
        if i == 0 or not n[i - 1].isalnum():
            return True
        pre = n[:i]
        return re.search(r'(^[PNM]|VCC|VDD|VIN|VOUT|VBAT|VSYS|VBUS|VCCIO|VDDIO|PWR|AVDD|DVDD|VREG|V)$', pre) is not None
    for m in re.finditer(r'(?<![0-9.])(\d{1,3})V(\d{1,3})(?![0-9])', n):              # 3V3, 12V0, P3V3, VDD3V3
        if prefix_ok(m.start()):
            v = float(f"{m.group(1)}.{m.group(2)}")
            break
    else:
        for m in re.finditer(r'(?<![0-9.])(\d{1,3}(?:\.\d{1,3})?)\s*V(?![0-9])', n):     # 3.3V, 5V, VCC_12V
            if prefix_ok(m.start()):
                v = float(m.group(1))
                break
        else:
            return None
    if v <= 0 or v > 1000:
        return None
    return (-v if neg else v), m.group(0)


# ------------------------------------------------------------------ packages
@dataclass(frozen=True)
class Package:
    size: str | None          # imperial chip code ('0402') or None
    area_mm2: float | None    # body area for chip sizes
    polarized: bool           # electrolytic or tantalum body
    through_hole: bool
    text: str                 # the footprint name it came from


def package(lib_id: str | None) -> Package:
    """Chip size and body class from a footprint lib id ('Capacitor_SMD:C_0402_1005Metric')."""
    lib = lib_id or ''
    name = lib.split(':', 1)[-1]
    size = None
    m = _PKG_RE.search(name)
    if m:
        size = m.group(1)
    else:
        m = _IPC_RE.search(name) or _METRIC_RE.search(name)
        if m and m.group(1) in _METRIC_TO_IMPERIAL:
            size = _METRIC_TO_IMPERIAL[m.group(1)]
    pol = re.search(r'CP_|_Elec|Elec_|Tantal|CPol|Radial.*CP|Electrolytic|SMD_Elec|PANASONIC_[A-Z]?\d|EEE-', lib, re.I) is not None
    th = re.search(r'_THT|THT_|Radial|Axial|DIP-|TO-92|TO-220|_P\d+\.\d+mm_(Vertical|Horizontal)|Disc_', lib, re.I) is not None
    return Package(size=size, area_mm2=_CHIP_AREA.get(size or ''), polarized=pol, through_hole=th, text=name)


def si(value: float | None, unit: str) -> str:
    """Engineering notation for logs and evidence ('1e-07','F' -> '100 nF')."""
    if value is None:
        return '?'
    a = abs(value)
    for f, p in ((1e9, 'G'), (1e6, 'M'), (1e3, 'k'), (1.0, ''), (1e-3, 'm'), (1e-6, 'u'), (1e-9, 'n'), (1e-12, 'p')):
        if a >= f * 0.9995:
            return f"{value / f:.4g} {p}{unit}"
    return f"{value:.3g} {unit}"
