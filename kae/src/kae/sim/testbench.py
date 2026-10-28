# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The testbench file: plain SPICE plus `*@` annotations, naming board objects as KiCad does.

    *@kae-testbench 1
    *@test rail_dc:+3V3 kind=rail_dc
    *@nets +3V3 GND
    *@range I_U22 0.02 0.3 src=prior:"IC transient current by pin count"
    .param I_U22=0.08
    Itb1 <U22.5> 0 DC {I_U22}
    Vtb1 <U9.3> 0 DC 3.3
    .tran 10n 1u
    .meas tran v_U22_5 MIN v(<U22.5>) from=0.5u to=1u
    *@require v_U22_5 >= 3.201 src=prior:"drop <= 3% of 3.3 V"
    *@end

- `<REF.PAD>` is the node at that pad; `<NET>` the node of a net that the test does not extract (a
  rail driven by an ideal source, for example). Angle brackets are illegal in ngspice node names,
  so an unresolved name can never pass through silently.
- `*@test ID kind=K structure=S`: S names the brief structure the test judges; kae.sim.budget
  writes the budget it derives under that id.
- `*@nets` lists the nets replaced by their extracted copper in the routed run.
- `*@range NAME lo hi src=...` makes `.param NAME` an interval: the test runs at its corners.
- `*@require MEAS OP BOUND src=...` (OP one of <=, >=, <, >) judges a `.meas` result; `*@info MEAS`
  reports one without a bound.
- `*@extract signal|power` picks the extraction profile of the routed run (extract.PROFILES; default
  signal: line capacitance and coupling; power: long R-L sections, pour and via parasitics only).
- `*@exclude REF ...` leaves board parts out of the test (it models them itself, e.g. an inductor held
  as a current source).
- `*@unknown reason` marks what the test cannot know (no rail voltage, no source found); its verdicts
  are then unknown, never pass or fail. `*@note` is free text kept with the results.
- A test may end in a `.control` block (`run`, then `let`, `meas` and `print` on the result vectors) for
  quantities computed from the converged waveforms, such as v * i products: as a B-source probe a
  product is a circuit node that the solver must also converge, and it can stall a run whose circuit
  converges. In it, ground is `0`, not `v(0)` (the evaluator rewrites it).
- `kae_pdiss`, in the `.control` block after `run`, is the power the board's own resistances (copper,
  resistors, capacitor ESR, inductor DCR) dissipate at each instant; the evaluator computes it for any
  test that names it.
- Sources: kind:"citation", kind one of human, board_rule, datasheet, board_value, schematic,
  standard, inferred, prior.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

PDISS = "kae_pdiss"                                   # node: watts dissipated in the board's resistances
SOURCES = ("human", "board_rule", "datasheet", "board_value", "schematic", "standard", "inferred", "prior")
_SUFFIX = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}
_NUM = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)(meg|[tgkmunpf])?[a-z]*$", re.I)
TOKEN = re.compile(r"<([^<>\s]+)>")


def num(text):
    """A SPICE number ('2.2u', '1meg', '300n', '3.3'); ValueError otherwise."""
    m = _NUM.match(str(text).strip())
    if not m:
        raise ValueError(f"not a SPICE number: {text!r}")
    v = float(m.group(1))
    s = (m.group(2) or "").lower()
    return v * _SUFFIX.get(s, 1.0)


def fmt(v):
    return f"{v:.6g}"


@dataclass
class Param:
    name: str
    typ: float
    lo: float
    hi: float
    src: str = "prior"


@dataclass
class Require:
    meas: str
    op: str
    bound: float
    src: str = "prior"


@dataclass
class Test:
    id: str
    kind: str = ""
    nets: list = field(default_factory=list)
    lines: list = field(default_factory=list)       # SPICE lines with <tokens>, .param lines included
    params: dict = field(default_factory=dict)      # name -> Param (only those with *@range)
    requires: list = field(default_factory=list)
    info: list = field(default_factory=list)
    unknown: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    exclude: list = field(default_factory=list)     # board parts left out of this test (the testbench models them)
    structure: str = ""                             # the brief structure this test judges (its budget's owner)
    extract: str = "signal"                         # extraction profile of the routed run (extract.PROFILES)

    def meas_names(self):
        """`.meas` names, and `meas` names in a `.control` block (outside one, a line starting with
        `meas` is an element: a MOSFET)."""
        out, ctl = [], False
        for ln in self.lines:
            low = ln.strip().lower()
            ctl = (ctl or low.startswith(".control")) and not low.startswith(".endc")
            m = re.match(r"\s*\.meas(?:ure)?\s+\w+\s+(\w+)", ln, re.I) or \
                (ctl and re.match(r"\s*meas(?:ure)?\s+\w+\s+(\w+)", ln, re.I))
            if m:
                out.append(m.group(1))
            elif ctl and re.match(r"\s*print\s", ln, re.I):
                out += ln.split()[1:]                    # printed vectors read as results
        return out


def _src(kv):
    s = kv.get("src", "prior")
    kind = s.split(":", 1)[0]
    if kind not in SOURCES:
        raise ValueError(f"unknown source kind {kind!r} in src={s!r}")
    return s


def _kv(words):
    pos, kv = [], {}
    for w in words:
        if "=" in w and not w.startswith(("<", ">")) and w.split("=", 1)[0].isidentifier():
            k, v = w.split("=", 1)
            kv[k] = v
        else:
            pos.append(w)
    return pos, kv


def parse(text):
    """Tests of a testbench file; ValueError (with the line number) on anything malformed."""
    tests, cur = [], None
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        try:
            if line.startswith("*@"):
                head = line[2:].strip().split(None, 1)
                if not head:
                    continue
                tag = head[0]
                if tag in ("note", "unknown"):
                    if cur is None:
                        raise ValueError(f"*@{tag} outside a test")
                    (cur.notes if tag == "note" else cur.unknown).append(head[1] if len(head) > 1 else "")
                    continue
                rest = shlex.split(head[1]) if len(head) > 1 else []
                if tag in ("kae-testbench", "board"):
                    continue
                if tag == "test":
                    if cur is not None:
                        raise ValueError("*@test inside a test (missing *@end)")
                    pos, kv = _kv(rest)
                    cur = Test(id=pos[0], kind=kv.get("kind", ""), structure=kv.get("structure", ""))
                    continue
                if cur is None:
                    raise ValueError(f"*@{tag} outside a test")
                if tag == "end":
                    tests.append(cur)
                    cur = None
                elif tag == "nets":
                    cur.nets.extend(rest)
                elif tag == "range":
                    pos, kv = _kv(rest)
                    cur.params[pos[0]] = Param(pos[0], float("nan"), num(pos[1]), num(pos[2]), _src(kv))
                elif tag == "require":
                    pos, kv = _kv(rest)
                    if pos[1] not in ("<=", ">=", "<", ">"):
                        raise ValueError(f"bad operator {pos[1]!r}")
                    cur.requires.append(Require(pos[0], pos[1], num(pos[2]), _src(kv)))
                elif tag == "info":
                    cur.info.extend(rest)
                elif tag == "exclude":
                    cur.exclude.extend(rest)
                elif tag == "extract":
                    if rest[0] not in ("signal", "power"):
                        raise ValueError(f"unknown extraction profile {rest[0]!r} (signal or power)")
                    cur.extract = rest[0]
                else:
                    raise ValueError(f"unknown annotation *@{tag}")
                continue
            if cur is None:
                continue
            if line.strip():
                cur.lines.append(line)
                m = re.match(r"\s*\.param\s+(\w+)\s*=\s*(\S+)", line, re.I)
                if m and m.group(1) in cur.params:
                    cur.params[m.group(1)].typ = num(m.group(2))
        except (ValueError, IndexError) as e:
            raise ValueError(f"line {i}: {e}: {raw!r}") from None
    if cur is not None:
        raise ValueError(f"test {cur.id} has no *@end")
    for t in tests:
        for p in t.params.values():
            if p.typ != p.typ:
                raise ValueError(f"test {t.id}: *@range {p.name} without a .param line")
            if not p.lo <= p.typ <= p.hi:
                raise ValueError(f"test {t.id}: {p.name} = {p.typ} outside [{p.lo}, {p.hi}]")
        names = set(t.meas_names())
        for r in t.requires:
            if r.meas not in names:
                raise ValueError(f"test {t.id}: *@require on unknown .meas {r.meas}")
    return tests


def render(tests, board_sha=""):
    out = ["*@kae-testbench 1"]
    if board_sha:
        out.append(f"*@board sha256={board_sha}")
    for t in tests:
        out.append("")
        out.append(f"*@test {t.id}" + (f" kind={t.kind}" if t.kind else "") + (f" structure={t.structure}" if t.structure else ""))
        if t.nets:
            out.append("*@nets " + " ".join(shlex.quote(n) for n in t.nets))
        if t.exclude:
            out.append("*@exclude " + " ".join(t.exclude))
        if t.extract != "signal":
            out.append(f"*@extract {t.extract}")
        for n in t.notes:
            out.append(f"*@note {n}")
        for u in t.unknown:
            out.append(f"*@unknown {u}")
        for p in t.params.values():
            out.append(f'*@range {p.name} {fmt(p.lo)} {fmt(p.hi)} src={shlex.quote(p.src)}')
        out.extend(t.lines)
        for r in t.requires:
            out.append(f"*@require {r.meas} {r.op} {fmt(r.bound)} src={shlex.quote(r.src)}")
        if t.info:
            out.append("*@info " + " ".join(t.info))
        out.append("*@end")
    return "\n".join(out) + "\n"
