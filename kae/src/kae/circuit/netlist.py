# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A read-only netlist view of the board model (Contract 1), the only input comprehension uses.

`Netlist.from_board(board)` reads these Contract-1 fields and nothing else:
  Board.footprints (list or ref -> Footprint), Board.nets (name -> Net), Board.zones (net only);
  Footprint.ref, value, lib_id, uuid, attrs, fields, pads;
  Pad.number, net, kind, pinfunction, pintype;
  Net.name, netclass.
Positions (x, y, rot, side), courtyards, tracks and vias are never read: comprehension
must not depend on where parts sit, so the same brief serves the place task (parts off the
board) and the routed reference. The only optional extra is a footprint's schematic sheet
(`sheet` attribute, or the 'Sheetname'/'Sheetfile' fields) when a loader provides it.

Pins are deduplicated per (pad number, net): an exposed pad split into nine pads is one pin.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .values import NetName, clean_net, package


def _items(container):
    if container is None:
        return []
    if isinstance(container, dict):
        return list(container.values())
    return list(container)


def _attrs(a) -> frozenset:
    if a is None:
        return frozenset()
    if isinstance(a, dict):
        return frozenset(str(k) for k, v in a.items() if v)
    if isinstance(a, str):
        return frozenset(a.split())
    return frozenset(str(x) for x in a)


def _netname(n) -> str | None:
    if n is None:
        return None
    if isinstance(n, str):
        return n or None
    name = getattr(n, 'name', None)
    return name or None


def _sheet_of(fp) -> str | None:
    for attr in ('sheet', 'sheet_path', 'sheetname'):
        s = getattr(fp, attr, None)
        if s:
            return str(s)
    flds = getattr(fp, 'fields', None) or {}
    for k in ('Sheetname', 'Sheetfile', 'sheetname', 'sheetfile'):
        if flds.get(k):
            return str(flds[k])
    return None


@dataclass(frozen=True)
class Pin:
    ref: str
    number: str
    net: str | None
    function: str      # pin function from the symbol ('' when absent)
    ptype: str         # pin electrical type without '+no_connect' ('' when absent)
    nc: bool           # typed no_connect
    pad_kind: str      # smd, thru_hole, np_thru_hole, connect

    @property
    def fn(self) -> str:
        """Pin function, upper case, KiCad overbar markup removed."""
        f = re.sub(r'~\{([^}]*)\}', r'\1', self.function or '')
        return f.replace('{slash}', '/').strip().upper()

    @property
    def label(self) -> str:
        return f"{self.ref}.{self.number}" + (f" ({self.function})" if self.function and self.function != self.number else '')


@dataclass
class Part:
    ref: str                  # unique key (the reference designator; '#n' added to repeats)
    refdes: str               # as written on the board
    value: str
    lib_id: str
    fields: dict
    attrs: frozenset
    pins: list
    npads: int
    sheet: str | None
    uuid: str | None
    prefix: str = ''
    number: int | None = None
    nets: frozenset = frozenset()
    _by_net: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        m = re.match(r'([A-Za-z_#]+)(\d*)', self.refdes or '')
        self.prefix = (m.group(1).upper().rstrip('_') if m else '')
        self.number = int(m.group(2)) if m and m.group(2) else None
        by = defaultdict(list)
        for p in self.pins:
            if p.net:
                by[p.net].append(p)
        self._by_net = dict(by)
        self.nets = frozenset(by)

    @property
    def lib(self) -> str:
        return self.lib_id.split(':', 1)[0] if ':' in self.lib_id else ''

    @property
    def fpname(self) -> str:
        return self.lib_id.split(':', 1)[-1]

    @property
    def package(self):
        return package(self.lib_id)

    @property
    def dnp(self) -> bool:
        return 'dnp' in self.attrs

    @property
    def description(self) -> str:
        return str(self.fields.get('Description') or self.fields.get('description') or '')

    def text(self) -> str:
        """Value, footprint, description and part-number fields joined: the text keyword rules read."""
        keys = ('Description', 'MPN', 'Manufacturer Part Number', 'Manufacturer_Part_Number', 'Part Number',
                'PartNumber', 'MFR_PN', 'MFN', 'Mfr. No.', 'Comment', 'Val')
        extra = ' '.join(str(self.fields[k]) for k in keys if self.fields.get(k))
        return f"{self.value} {self.lib_id} {extra}"

    def pins_on(self, net: str) -> list:
        return self._by_net.get(net, [])

    def active_pins(self) -> list:
        """Pins with a net, not typed no_connect."""
        return [p for p in self.pins if p.net and not p.nc]


@dataclass
class NetView:
    name: str
    nn: NetName
    netclass: str
    pins: list = field(default_factory=list)

    @property
    def short(self) -> str:
        return self.nn.short

    @property
    def refs(self) -> set:
        return {p.ref for p in self.pins}


class Netlist:
    """Parts, nets and pins, with the indexes the inference rules need."""

    def __init__(self, parts: dict, nets: dict, zone_layers: dict | None = None, path: str = ''):
        self.parts = parts
        self.nets = nets
        self.zone_layers = zone_layers or {}
        self.path = path

    # ------------------------------------------------------------ construction
    @classmethod
    def from_board(cls, board) -> 'Netlist':
        parts: dict[str, Part] = {}
        seen = defaultdict(int)
        netclass = {}
        for n in _items(getattr(board, 'nets', None)):
            nm = _netname(n)
            if nm:
                netclass[nm] = str(getattr(n, 'netclass', '') or '')
        for fp in _items(getattr(board, 'footprints', None)):
            refdes = str(getattr(fp, 'ref', '') or '?')
            seen[refdes] += 1
            key = refdes if seen[refdes] == 1 else f"{refdes}#{seen[refdes]}"
            pins, keyset, npads = [], set(), 0
            for pd in _items(getattr(fp, 'pads', None)):
                npads += 1
                num = str(getattr(pd, 'number', '') or '')
                net = _netname(getattr(pd, 'net', None))
                pt = str(getattr(pd, 'pintype', '') or '')
                k = (num, net)
                if k in keyset:
                    continue
                keyset.add(k)
                pins.append(Pin(ref=key, number=num, net=net, function=str(getattr(pd, 'pinfunction', '') or ''),
                                ptype=pt.split('+')[0], nc='no_connect' in pt,
                                pad_kind=str(getattr(pd, 'kind', '') or '')))
            parts[key] = Part(ref=key, refdes=refdes, value=str(getattr(fp, 'value', '') or ''),
                              lib_id=str(getattr(fp, 'lib_id', '') or ''), fields=dict(getattr(fp, 'fields', None) or {}),
                              attrs=_attrs(getattr(fp, 'attrs', None)), pins=pins, npads=npads, sheet=_sheet_of(fp),
                              uuid=getattr(fp, 'uuid', None))
        nets: dict[str, NetView] = {}
        for p in parts.values():
            for pin in p.pins:
                if pin.net:
                    nv = nets.get(pin.net)
                    if nv is None:
                        nv = nets[pin.net] = NetView(pin.net, clean_net(pin.net), netclass.get(pin.net, ''))
                    nv.pins.append(pin)
        zl = defaultdict(int)
        for z in _items(getattr(board, 'zones', None)):
            nm = _netname(getattr(z, 'net', None)) or getattr(z, 'net_name', None)
            if nm:
                lys = getattr(z, 'layers', None) or [getattr(z, 'layer', None)]
                zl[nm] += max(1, len([x for x in lys if x]))
        return cls(parts, nets, dict(zl), str(getattr(board, 'path', '') or ''))

    # ------------------------------------------------------------ queries
    def pins(self, net: str) -> list:
        nv = self.nets.get(net)
        return nv.pins if nv else []

    def parts_on(self, net: str) -> list:
        return [self.parts[r] for r in sorted(self.nets[net].refs)] if net in self.nets else []

    def other_net(self, part: Part, net: str) -> str | None:
        """For a two-net part, the net on its other side."""
        ns = [n for n in part.nets if n != net]
        return ns[0] if len(part.nets) == 2 and len(ns) == 1 else None

    def two_nets(self, part: Part) -> tuple | None:
        """(net_a, net_b) for a part with exactly two distinct nets on its active pins."""
        ns = sorted({p.net for p in part.active_pins()})
        return (ns[0], ns[1]) if len(ns) == 2 else None

    def netclass(self, net: str) -> str:
        nv = self.nets.get(net)
        return nv.netclass if nv else ''
