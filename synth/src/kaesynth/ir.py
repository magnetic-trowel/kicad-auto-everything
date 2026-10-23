# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Typed circuit IR: design, domains, blocks, parts, nets, intent records.

A design is authored in Python (an LLM writes `designs/<slug>/design.py`) and is the single
source for the schematic, the checks and the placement intent. Everything is explicit:
every pin is connected or marked no-connect, every net has a domain and a voltage range,
every part carries the ratings the checks compare against.
"""
import copy
import re
from dataclasses import dataclass, field

PIN_TYPES = ("input", "output", "bidirectional", "tri_state", "passive", "free", "unspecified",
             "power_in", "power_out", "open_collector", "open_emitter", "no_connect")
NET_KINDS = ("signal", "power", "ground", "hv", "mains", "switching", "sense", "analog",
             "high_current", "pe", "clock", "diff")
GRADES = {"none": 0, "functional": 1, "basic": 2, "supplementary": 2, "double": 3, "reinforced": 3}
SIDES = ("left", "right", "top", "bottom")
# threat on an external wire -> part categories that count as a protector on that net
THREATS = {"esd": ("tvs",), "surge": ("tvs", "mov"), "overcurrent": ("fuse", "ptc"),
           "reverse_polarity": ("diode", "mosfet"), "load_dump": ("tvs",), "overvoltage": ("tvs", "mov")}


class DesignError(ValueError):
    pass


def _interval(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return (float(v), float(v))
    lo, hi = v
    return (float(min(lo, hi)), float(max(lo, hi)))


# ---------------------------------------------------------------------------------------------
# Parts


@dataclass
class PinDef:
    number: str
    name: str = ""
    type: str = "passive"
    side: str = None      # generated symbols only: left/right/top/bottom
    unit: int = 1

    def __post_init__(self):
        self.number = str(self.number)
        if self.type not in PIN_TYPES:
            raise DesignError(f"pin {self.number}: unknown type {self.type!r}; use one of {PIN_TYPES}")
        if self.side is not None and self.side not in SIDES:
            raise DesignError(f"pin {self.number}: side must be one of {SIDES}")


@dataclass
class VLimit:
    """Absolute max |V(a) - V(b)| between two pin groups (pin names or numbers)."""
    a: tuple
    b: tuple
    v_max: float
    note: str = ""


@dataclass
class Isolation:
    """Rated galvanic isolation between two pin groups (an approved barrier component)."""
    a: tuple
    b: tuple
    v_iso_rms: float              # withstand/test voltage, Vrms, 60 s
    grade: str = "basic"          # basic | reinforced | functional
    v_work_rms: float = None      # rated working voltage across the barrier
    creepage_mm: float = None     # package creepage, for the layout to respect
    standard: str = ""

    def __post_init__(self):
        if self.grade not in GRADES:
            raise DesignError(f"isolation grade {self.grade!r} not in {list(GRADES)}")


@dataclass
class Ratings:
    v_max: float = None            # 2-terminal parts: max |V| across the part
    limits: list = field(default_factory=list)   # [VLimit]
    i_max: float = None            # continuous current through any pin (A)
    pin_i_max: dict = field(default_factory=dict)  # {pin name/number: A}
    p_max: float = None            # power rating (W) at the design's ambient
    isolation: list = field(default_factory=list)  # [Isolation]
    polarity: tuple = None         # (positive pin, negative pin) for polarized parts
    t_min: float = None
    t_max: float = None


CATEGORIES = ("resistor", "capacitor", "capacitor_ceramic", "capacitor_electrolytic", "capacitor_film",
              "inductor", "transformer", "diode", "tvs", "led", "mosfet", "bjt", "ic", "opto",
              "connector", "fuse", "ptc", "relay", "mov", "switch", "crystal", "mechanical",
              "testpoint", "heatsink", "module", "thermistor", "other")


class PartDef:
    """A part type: identity, symbol, footprint, pins and ratings.

    Either `symbol` names a KiCad library symbol (`Lib:Name`, pins read from the library;
    `pinmap` renumbers symbol pins to footprint pads) or `pins` lists PinDefs and a
    symbol is generated.
    """

    def __init__(self, *, mpn=None, manufacturer=None, symbol=None, pins=None, footprint=None,
                 value=None, prefix=None, category="ic", description="", datasheet="",
                 ratings=None, pinmap=None, lifecycle="active", generic=False, fields=None,
                 second_source=None, dnp=False, in_bom=True, on_board=True, notes="", source=None):
        if category not in CATEGORIES:
            raise DesignError(f"category {category!r} not in {CATEGORIES}")
        if symbol is None and not pins:
            raise DesignError(f"{mpn or value}: give a KiCad `symbol` or a `pins` list")
        self.mpn = mpn
        self.manufacturer = manufacturer
        self.symbol = symbol
        self.pins = [p if isinstance(p, PinDef) else PinDef(*p) for p in (pins or [])]
        self.footprint = footprint
        self.value = value
        self.prefix = prefix or _default_prefix(category)
        self.category = category
        self.description = description
        self.datasheet = datasheet
        self.ratings = ratings or Ratings()
        self.pinmap = {str(k): str(v) for k, v in (pinmap or {}).items()}
        self.lifecycle = lifecycle
        self.generic = generic
        self.fields = dict(fields or {})
        self.second_source = second_source
        self.dnp = dnp
        self.in_bom = in_bom
        self.on_board = on_board
        self.notes = notes
        # provenance per fact: {"pins": "DS rev C p.3 Table 1", "ratings": "DS p.5", "pinmap": ...}
        self.source = dict(source or {})
        # resolved at finalize: list of PinDef with numbers as on the footprint
        self.resolved_pins = None

    def with_(self, **kw):
        new = copy.copy(self)
        new.ratings = copy.deepcopy(self.ratings)
        new.fields = dict(self.fields)
        new.resolved_pins = None
        for k, v in kw.items():
            if not hasattr(new, k):
                raise DesignError(f"PartDef has no attribute {k!r}")
            setattr(new, k, v)
        return new

    @property
    def key(self):
        return self.mpn or f"{self.category}:{self.value}:{self.footprint}"

    def __repr__(self):
        return f"PartDef({self.mpn or self.value!r}, {self.symbol or 'generated'})"


def _default_prefix(cat):
    return {"resistor": "R", "capacitor": "C", "capacitor_ceramic": "C", "capacitor_electrolytic": "C",
            "capacitor_film": "C", "inductor": "L", "transformer": "T", "diode": "D", "tvs": "D",
            "led": "D", "mosfet": "Q", "bjt": "Q", "ic": "U", "opto": "U", "connector": "J",
            "fuse": "F", "ptc": "F", "relay": "K", "mov": "RV", "switch": "SW", "crystal": "Y",
            "mechanical": "H", "testpoint": "TP", "heatsink": "HS", "module": "U",
            "thermistor": "TH", "other": "X"}[cat]


class PinRef:
    def __init__(self, part, pin):
        self.part = part
        self.pin = pin           # PinDef (resolved)

    @property
    def net(self):
        return self.part.conn.get(self.pin.number)

    def __repr__(self):
        return f"{self.part.label}.{self.pin.name or self.pin.number}"


class Part:
    def __init__(self, block, defn, name, ref=None, value=None, p_diss=None, fields=None,
                 dnp=None, notes="", v_across=None):
        self.block = block
        self.defn = defn
        self.name = name             # local name used in the design file, e.g. "Q1"
        self.ref = ref               # explicit refdes or None (assigned at finalize)
        self.fixed_ref = ref is not None
        self.value = value if value is not None else (defn.value or defn.mpn)
        self.p_diss = p_diss         # expected dissipation (W) from the design's calcs
        self.v_across = v_across     # declared max voltage across a 2-terminal part (overrides net envelopes)
        self.fields = dict(fields or {})
        self.dnp = defn.dnp if dnp is None else dnp
        self.notes = notes
        self.conn = {}               # pin number -> Net
        self.nc = set()              # pin numbers explicitly not connected
        self.nc_reason = {}          # pin number -> why it is left open
        self._pins = None

    @property
    def label(self):
        return self.ref or f"{self.block.name}.{self.name}"

    @property
    def pins(self):
        if self._pins is None:
            self._pins = self.block.design._resolve_pins(self.defn)
        return self._pins

    def pin(self, key):
        """All pins matching a pin number or name (several pins may share a name, e.g. GND)."""
        key = str(key)
        hits = [p for p in self.pins if p.number == key]
        if not hits:
            hits = [p for p in self.pins if p.name == key]
        if not hits:
            raise DesignError(f"{self.label} ({self.defn.mpn or self.defn.value}): no pin {key!r}; "
                              f"pins are {[(p.number, p.name) for p in self.pins]}")
        return [PinRef(self, p) for p in hits]

    def __getitem__(self, key):
        refs = self.pin(key)
        return refs[0] if len(refs) == 1 else refs

    def nc_pins(self, *keys, reason=""):
        """Leave pins unconnected on purpose; give the datasheet's reason (e.g. 'NC, p.3')."""
        for k in keys:
            for r in self.pin(k):
                if r.pin.number in self.conn:
                    raise DesignError(f"{r} is connected to {self.conn[r.pin.number].name}; cannot mark NC")
                self.nc.add(r.pin.number)
                if reason:
                    self.nc_reason[r.pin.number] = reason
        return self

    def __repr__(self):
        return f"Part({self.label}, {self.defn.mpn or self.value})"


# ---------------------------------------------------------------------------------------------
# Nets, domains, barriers


class Net:
    def __init__(self, design, name, block=None, domain=None, v=None, kind="signal", i_max=None,
                 i_peak=None, netclass=None, external=False, threats=(), notes=""):
        if kind not in NET_KINDS:
            raise DesignError(f"net {name}: kind {kind!r} not in {NET_KINDS}")
        if not re.match(r"^[A-Za-z0-9_+\-.~]+$", name):
            raise DesignError(f"net name {name!r}: use letters, digits and _+-.~ only")
        self.design = design
        self.name = name
        self.block = block           # None = global net
        self.domain = domain
        self.v = _interval(v)
        self.kind = kind
        self.i_max = i_max
        self.i_peak = i_peak
        self.netclass = netclass
        self.external = external     # leaves the board through a connector
        bad = set(threats) - set(THREATS)
        if bad:
            raise DesignError(f"net {name}: unknown threats {sorted(bad)}; use {sorted(THREATS)}")
        self.threats = tuple(threats)  # what can arrive on this wire from outside
        self.notes = notes
        self.pins = []

    @property
    def is_global(self):
        return self.block is None

    @property
    def full_name(self):
        return self.name if self.block is None else f"{self.block.name}/{self.name}"

    def connect(self, *items):
        for it in _flatten(items):
            if isinstance(it, Part):
                raise DesignError(f"connect pins, not parts ({it.label}); use part['PIN']")
            if not isinstance(it, PinRef):
                raise DesignError(f"cannot connect {it!r} to net {self.name}")
            num = it.pin.number
            prev = it.part.conn.get(num)
            if prev is self:
                continue
            if prev is not None:
                raise DesignError(f"{it} already on net {prev.full_name}; cannot also join {self.full_name}")
            if num in it.part.nc:
                raise DesignError(f"{it} is marked no-connect")
            it.part.conn[num] = self
            self.pins.append(it)
        return self

    __iadd__ = connect

    def __repr__(self):
        return f"Net({self.full_name})"


def _flatten(items):
    for it in items:
        if isinstance(it, (list, tuple)):
            yield from _flatten(it)
        else:
            yield it


@dataclass
class Domain:
    """A voltage domain. `ref` is the net that is its 0 V.

    If `ref` belongs to this domain the domain is a root (galvanically separate from other
    roots); otherwise the domain floats on top of the ref net's domain (e.g. one battery of a
    series stack sits on the previous battery's positive terminal).
    """
    name: str
    ref: str
    kind: str = "selv"          # selv | elv | hv | mains | battery | other
    description: str = ""
    earthed: bool = False       # ref tied to protective earth / chassis
    v_range: tuple = None       # default (min, max) for nets in this domain that give no v
    notes: str = ""


@dataclass
class Barrier:
    """Insulation required between two domains, and the spacing the layout must keep."""
    a: str
    b: str
    grade: str                    # functional | basic | reinforced | double
    v_work: float                 # working voltage (V peak or DC) across the barrier
    creepage_mm: float
    clearance_mm: float
    standard: str = ""
    v_test_rms: float = None      # required withstand of components bridging the barrier
    pollution_degree: int = 2
    material_group: str = "IIIb"
    ovc: str = None
    slot: bool = False
    source: str = ""
    notes: str = ""

    def __post_init__(self):
        if self.grade not in GRADES:
            raise DesignError(f"barrier grade {self.grade!r} not in {list(GRADES)}")


# ---------------------------------------------------------------------------------------------
# Intent records


@dataclass
class Requirement:
    id: str
    text: str
    value: str = ""
    source: str = "brief"
    verify: str = ""


@dataclass
class Assumption:
    id: str
    text: str
    confirm_by: str = "human"


@dataclass
class Question:
    id: str
    text: str
    blocking: bool = False
    answer: str = None
    default: str = ""           # what the design currently does if unanswered


@dataclass
class Hazard:
    id: str
    text: str
    mitigation: str
    parts: list = field(default_factory=list)   # Part objects or refdes implementing it
    single_fault_safe: bool = False
    notes: str = ""


@dataclass
class Calc:
    name: str
    value: float
    unit: str = ""
    expr: str = ""
    note: str = ""
    limit: float = None
    op: str = "<="              # value <op> limit must hold
    severity: str = "error"


@dataclass
class Waiver:
    check: str
    match: str                  # substring or regex matched against finding objects/message
    reason: str
    by: str = "designer"


# ---------------------------------------------------------------------------------------------
# Blocks and the design


class Block:
    def __init__(self, design, name, title="", description="", domain=None, reqs=None, recipe=None):
        if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", name):
            raise DesignError(f"block name {name!r}: letters, digits, underscore; start with a letter")
        self.design = design
        self.name = name
        self.title = title or name
        self.description = description
        self.domain = domain         # default domain for nets created in this block
        self.reqs = list(reqs or [])
        self.recipe = recipe
        self.parts = []
        self.nets = {}
        self.index = len(design.blocks) + 1

    def add(self, defn, name=None, ref=None, **kw):
        if not isinstance(defn, PartDef):
            raise DesignError(f"block {self.name}: add() takes a PartDef, got {defn!r}")
        name = name or f"{defn.prefix}{sum(p.defn.prefix == defn.prefix for p in self.parts) + 1}"
        if any(p.name == name for p in self.parts):
            raise DesignError(f"block {self.name}: duplicate part name {name}")
        p = Part(self, defn, name, ref=ref, **kw)
        self.parts.append(p)
        return p

    def net(self, name, **kw):
        """A net local to this block (or an existing one). Global nets come from Design.net."""
        if name in self.nets:
            n = self.nets[name]
            if kw:
                _update_net(n, kw)
            return n
        if name in self.design.nets:
            raise DesignError(f"block {self.name}: {name} is a global net; use design.net() or a different name")
        kw.setdefault("domain", self.domain)
        n = Net(self.design, name, block=self, **kw)
        self.nets[name] = n
        return n

    def connect(self, net, *pins):
        if isinstance(net, str):
            net = self.design.nets.get(net) or self.nets.get(net) or self.net(net)
        return net.connect(*pins)

    def part(self, name):
        for p in self.parts:
            if p.name == name or p.ref == name:
                return p
        raise DesignError(f"block {self.name}: no part {name}")

    def __repr__(self):
        return f"Block({self.name})"


def _update_net(n, kw):
    for k, v in kw.items():
        if k == "v":
            v = _interval(v)
        setattr(n, k, v)


class Design:
    def __init__(self, slug, title="", description="", revision="A", author="kaesynth",
                 brief="", ambient_c=(0, 40)):
        if not re.match(r"^[a-z0-9][a-z0-9\-]*$", slug):
            raise DesignError("slug: lowercase letters, digits and dashes")
        self.slug = slug
        self.title = title or slug
        self.description = description
        self.revision = revision
        self.author = author
        self.brief = brief
        self.ambient_c = ambient_c
        self.blocks = []
        self.nets = {}               # global nets
        self.domains = {}
        self.barriers = []
        self.requirements = []
        self.assumptions = []
        self.questions = []
        self.hazards = []
        self.calcs = []
        self.waivers = []
        self.derating = dict(DEFAULT_DERATING)
        self.board_spec = None
        from .placement import Placement
        self.place = Placement(self)
        self._pin_cache = {}
        self.libs = None             # (SymbolLibs, FootprintLibs), set by finalize/build
        self.finalized = False

    # -- structure --------------------------------------------------------------------------
    def block(self, name, **kw):
        if any(b.name == name for b in self.blocks):
            raise DesignError(f"duplicate block {name}")
        b = Block(self, name, **kw)
        self.blocks.append(b)
        return b

    def net(self, name, **kw):
        if name in self.nets:
            n = self.nets[name]
            if kw:
                _update_net(n, kw)
            return n
        n = Net(self, name, **kw)
        self.nets[name] = n
        return n

    def domain(self, name, ref, **kw):
        if name in self.domains:
            raise DesignError(f"duplicate domain {name}")
        d = Domain(name, ref, **kw)
        self.domains[name] = d
        return d

    def barrier(self, a, b, **kw):
        a = a.name if isinstance(a, Domain) else a
        b = b.name if isinstance(b, Domain) else b
        bar = Barrier(a, b, **kw)
        self.barriers.append(bar)
        return bar

    # -- intent records ---------------------------------------------------------------------
    def require(self, id, text, **kw):
        self.requirements.append(Requirement(id, text, **kw))

    def assume(self, id, text, **kw):
        self.assumptions.append(Assumption(id, text, **kw))

    def question(self, id, text, **kw):
        self.questions.append(Question(id, text, **kw))

    def hazard(self, id, text, mitigation, parts=(), **kw):
        self.hazards.append(Hazard(id, text, mitigation, list(parts), **kw))

    def calc(self, name, value, unit="", expr="", note="", limit=None, op="<=", severity="error"):
        c = Calc(name, value, unit, expr, note, limit, op, severity)
        self.calcs.append(c)
        return value

    def waive(self, check, match, reason, by="designer"):
        self.waivers.append(Waiver(check, match, reason, by))

    def board(self, **kw):
        from .placement import BoardSpec
        self.board_spec = BoardSpec(**kw)
        return self.board_spec

    # -- queries ----------------------------------------------------------------------------
    def all_nets(self):
        out = list(self.nets.values())
        for b in self.blocks:
            out.extend(b.nets.values())
        return out

    def all_parts(self):
        return [p for b in self.blocks for p in b.parts]

    def find_part(self, key):
        if isinstance(key, Part):
            return key
        for p in self.all_parts():
            if p.ref == key or f"{p.block.name}.{p.name}" == key:
                return p
        raise DesignError(f"no part {key!r}")

    def net_by_name(self, name):
        if name in self.nets:
            return self.nets[name]
        blk, _, local = name.partition("/")
        for b in self.blocks:
            if b.name == blk and local in b.nets:
                return b.nets[local]
        raise DesignError(f"no net {name!r}")

    def domain_of(self, net):
        d = net.domain
        if d is None:
            return None
        return d if isinstance(d, Domain) else self.domains.get(d)

    # -- pins ---------------------------------------------------------------------------------
    def _resolve_pins(self, defn):
        if defn.resolved_pins is not None:
            return defn.resolved_pins
        if defn.pins:
            pins = [copy.copy(p) for p in defn.pins]
        else:
            from .kicadlib import SymbolLibs
            libs = self._symlibs()
            sym = libs.get(defn.symbol)
            pins = [PinDef(p.number, p.name, p.type if p.type in PIN_TYPES else "passive",
                           unit=max(p.unit, 1)) for p in sym.pins]
            if defn.pinmap:
                unknown = set(defn.pinmap) - {p.number for p in pins}
                if unknown:
                    raise DesignError(f"{defn}: pinmap keys {sorted(unknown)} are not pins of {defn.symbol}")
                for p in pins:
                    p.number = defn.pinmap.get(p.number, p.number)
        nums = [p.number for p in pins]
        dup = {n for n in nums if nums.count(n) > 1}
        if dup:
            raise DesignError(f"{defn}: duplicate pin numbers {sorted(dup)}")
        defn.resolved_pins = pins
        return pins

    def _symlibs(self):
        if self.libs is None:
            from .kicadlib import FootprintLibs, SymbolLibs
            self.libs = (SymbolLibs(), FootprintLibs())
        return self.libs[0]

    # -- finalize -------------------------------------------------------------------------------
    def finalize(self):
        """Assign reference designators and freeze. Idempotent."""
        if self.finalized:
            return self
        if len(self.domains) == 1:
            only = next(iter(self.domains.values()))
            for n in self.all_nets():
                if n.domain is None:
                    n.domain = only.name
        used = {}
        for p in self.all_parts():
            if p.fixed_ref:
                if p.ref in used:
                    raise DesignError(f"refdes {p.ref} used by {used[p.ref].label} and {p.block.name}.{p.name}")
                used[p.ref] = p
        counts = {}
        for b in self.blocks:
            for p in b.parts:
                counts[(b.index, p.defn.prefix)] = counts.get((b.index, p.defn.prefix), 0) + 1
        width = max([2] + [len(str(c)) for c in counts.values()])
        for b in self.blocks:
            n = {}
            for p in b.parts:
                if p.fixed_ref:
                    continue
                pre = p.defn.prefix
                while True:
                    n[pre] = n.get(pre, 0) + 1
                    ref = f"{pre}{b.index}{n[pre]:0{width}d}"
                    if ref not in used:
                        break
                p.ref = ref
                used[ref] = p
        self.finalized = True
        return self


DEFAULT_DERATING = {
    # fraction of the rating allowed before a warning (stress / rating)
    "voltage": {"default": 0.8, "resistor": 1.0, "fuse": 1.0, "ptc": 1.0, "connector": 0.8, "relay": 1.0,
                "capacitor_ceramic": 0.8, "capacitor_electrolytic": 0.8, "capacitor_film": 0.8},
    "current": {"default": 0.8, "fuse": 0.75, "ptc": 1.0, "connector": 0.8, "relay": 0.8},
    "power": {"default": 0.5, "ic": 0.8, "mosfet": 0.8, "diode": 0.8, "module": 0.8},
}
