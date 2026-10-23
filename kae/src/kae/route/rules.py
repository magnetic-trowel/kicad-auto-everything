# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""KiCad 10's design-rule resolution for a pair of items, in Python.

KiCad's DRC engine (pcbnew/drc/drc_engine.cpp, DRC_ENGINE::EvalRules) is not exposed to
SWIG. Item methods that call it with no partner item (GetOwnClearance, a track's
GetWidthConstraint, a via's GetDrillConstraint) are, and kae.route uses them as probes; the
constraints between two items (a routed track and a pad, two classes of tracks) need the
resolution itself, which this module ports:

1. Clearance and hole clearance: a local override on either item (pad, else its footprint)
   wins, floored at the board minimum (hole minimum for hole clearance).
2. Otherwise every rule for the constraint type is tried in order: the implicit board-setup
   rule, the netclass rules (clearance rules sorted by value, so the larger of the two items'
   classes wins), then the custom .kicad_dru rules in file order. A matching rule replaces
   what is set before it; conditions are commutative (A,B or B,A); a rule's layer must
   contain the layer under test.
3. A custom winner is final. An implicit clearance is then raised to either item's local
   clearance and to the board minimum; a diff-pair gap to the board minimum.

Conditions are KiCad's expression language (pcbnew/pcbexpr_*.cpp): A./B. properties,
functions, ==, != (string compares are case-insensitive and honour * and ? wildcards; an
undefined value compares false both ways), <, >, &&, ||, !, numbers with units.
Geometry-dependent functions (intersectsArea, intersectsCourtyard, enclosedByArea, ...)
cannot be known before routing; `evaluate(..., geometric=True|False)` decides them, and
`strictest()` takes the tighter result of both, so a relaxation inside an area is ignored
and a tightening applies everywhere.

Items are dicts: type ('Track', 'Via', 'Pad', 'Zone', 'Graphic', 'Text'), net, netclass
(KiCad's effective name, e.g. 'HS,Default'), copper (bool), connected (bool), plated,
pad_type, fab_property, ref and lib (parent footprint), width, via_type, drilled, name,
override and local (clearances in mm), layers. Values are mm.
"""
import fnmatch
import re
from dataclasses import dataclass, field

from kae.board import sexpr

UNITS = {"mm": 1.0, "mil": 0.0254, "in": 25.4, "um": 0.001, "nm": 1e-6, "deg": 1.0}
CLEARANCE_TYPES = ("clearance", "hole_clearance", "edge_clearance", "physical_clearance",
                   "physical_hole_clearance", "courtyard_clearance", "silk_clearance")
GEOMETRIC = {"intersectsarea", "insidearea", "enclosedbyarea", "intersectscourtyard",
             "insidecourtyard", "intersectsfrontcourtyard", "insidefrontcourtyard",
             "intersectsbackcourtyard", "insidebackcourtyard", "intersectskeepout"}


class Undefined:
    """KiCad's VT_UNDEFINED: a property the item does not have."""
    def __repr__(self):
        return "undefined"


UNDEF = Undefined()


# ----------------------------------------------------------------------------- parsing
_TOK = re.compile(r"""\s*(?:
    (?P<num>\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+)(?P<unit>mm|mil|in|um|nm|deg)?
  | '(?P<str>(?:[^'\\]|\\.)*)(?:'|$)
  | (?P<id>[A-Za-z_][A-Za-z_0-9]*)
  | (?P<op>==|!=|<=|>=|&&|\|\||[()!<>.,+\-*/])
)""", re.X)


def tokenize(text):
    out, i = [], 0
    text = text.strip()
    while i < len(text):
        m = _TOK.match(text, i)
        if not m or m.end() == i:
            if text[i:].strip() == "":
                break
            raise ValueError(f"cannot parse rule condition at {text[i:i + 20]!r}")
        i = m.end()
        if m.group("num") is not None:
            out.append(("num", float(m.group("num")) * UNITS.get(m.group("unit") or "mm", 1.0)
                        if m.group("unit") else float(m.group("num")), m.group("unit")))
        elif m.group("str") is not None:
            out.append(("str", re.sub(r"\\(.)", r"\1", m.group("str")), None))
        elif m.group("id") is not None:
            out.append(("id", m.group("id"), None))
        elif m.group("op") is not None:
            out.append(("op", m.group("op"), None))
    return out


class _Parser:
    """Recursive descent: or > and > not > comparison > additive > term > unary > primary."""

    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self, kind=None, val=None):
        if self.i >= len(self.t):
            return None
        k, v, _ = self.t[self.i]
        if (kind is None or k == kind) and (val is None or v == val):
            return self.t[self.i]
        return None

    def take(self, kind=None, val=None):
        tok = self.peek(kind, val)
        if tok is None:
            raise ValueError(f"expected {val or kind} at token {self.i} in {self.t}")
        self.i += 1
        return tok

    def parse(self):
        e = self.orexpr()
        if self.i != len(self.t):
            raise ValueError(f"trailing tokens {self.t[self.i:]}")
        return e

    def orexpr(self):
        e = self.andexpr()
        while self.peek("op", "||"):
            self.take()
            e = ("or", e, self.andexpr())
        return e

    def andexpr(self):
        e = self.notexpr()
        while self.peek("op", "&&"):
            self.take()
            e = ("and", e, self.notexpr())
        return e

    def notexpr(self):
        if self.peek("op", "!"):
            self.take()
            return ("not", self.notexpr())
        return self.cmp()

    def cmp(self):
        e = self.add()
        for op in ("==", "!=", "<=", ">=", "<", ">"):
            if self.peek("op", op):
                self.take()
                return ("cmp", op, e, self.add())
        return e

    def add(self):
        e = self.term()
        while self.peek("op", "+") or self.peek("op", "-"):
            op = self.take()[1]
            e = ("arith", op, e, self.term())
        return e

    def term(self):
        e = self.unary()
        while self.peek("op", "*") or self.peek("op", "/"):
            op = self.take()[1]
            e = ("arith", op, e, self.unary())
        return e

    def unary(self):
        if self.peek("op", "-"):
            self.take()
            return ("neg", self.unary())
        return self.primary()

    def primary(self):
        if self.peek("op", "("):
            self.take()
            e = self.orexpr()
            self.take("op", ")")
            return e
        tok = self.take()
        if tok[0] == "num":
            return ("num", tok[1])
        if tok[0] == "str":
            return ("str", tok[1])
        if tok[0] == "id":
            name = tok[1]
            if self.peek("op", "."):
                self.take()
                attr = self.take("id")[1]
                if self.peek("op", "("):
                    self.take()
                    args = []
                    while not self.peek("op", ")"):
                        args.append(self.orexpr())
                        if self.peek("op", ","):
                            self.take()
                    self.take("op", ")")
                    return ("call", name, attr, args)
                return ("prop", name, attr)
            if name.lower() == "null":
                return ("null",)
            return ("str", name)  # bare words compare as strings
        raise ValueError(f"unexpected token {tok}")


def compile_condition(text):
    """AST of a rule condition ('' -> None, always true)."""
    text = (text or "").strip()
    if not text:
        return None
    return _Parser(tokenize(text)).parse()


# ----------------------------------------------------------------------------- evaluation
def _wild(pattern):
    return any(c in pattern for c in "*?")


def _str_eq(a, pat):
    """KiCad VALUE::EqualTo for strings: case-insensitive, wildcards in the literal."""
    if _wild(pat):
        return fnmatch.fnmatchcase(a.lower(), pat.lower())
    return a.lower() == pat.lower()


@dataclass
class Ctx:
    a: dict
    b: dict | None
    layer: str | None
    ctype: str
    geometric: bool = False
    board: "Board | None" = None


def _get(ctx, which):
    if which.upper() == "A":
        return ctx.a
    if which.upper() == "B":
        return ctx.b
    return None


_PROPS = {  # expression property (lower case, '_' for ' ') -> item key
    "type": "type", "net": "net", "netname": "net", "netclass": "netclass", "layer": "layer",
    "pad_type": "pad_type", "fabrication_property": "fab_property", "reference": "ref",
    "width": "width", "via_type": "via_type", "name": "name", "value": "value",
    "hole_size_x": "hole_x", "hole_size_y": "hole_y", "pad_shape": "pad_shape",
}


def _prop(ctx, which, attr):
    item = _get(ctx, which)
    if item is None:
        return UNDEF
    key = _PROPS.get(attr.lower(), attr.lower())
    if key == "layer":
        return ("layer", ctx.layer)
    if key not in item or item[key] is None:
        return UNDEF
    v = item[key]
    if key == "netclass":
        return ("netclass", v, item.get("constituents") or v.split(","))
    return v


def _eq(a, b):
    """== with KiCad's semantics; None when undefined (which makes == and != false)."""
    if a is UNDEF or b is UNDEF:
        return None
    if isinstance(a, tuple) and a[0] == "netclass" and isinstance(b, str):
        return any(_str_eq(c, b) for c in a[2]) or _str_eq(a[1], b)
    if isinstance(b, tuple) and b[0] == "netclass" and isinstance(a, str):
        return _eq(b, a)
    if isinstance(a, tuple) and a[0] == "layer" and isinstance(b, str):
        return a[1] is not None and _str_eq(a[1], b)
    if isinstance(b, tuple) and b[0] == "layer" and isinstance(a, str):
        return _eq(b, a)
    if isinstance(a, tuple) and isinstance(b, tuple) and a[0] == b[0] == "netclass":
        return a[1] == b[1]
    if isinstance(a, bool) or isinstance(b, bool):
        return float(a) == float(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-9
    if isinstance(a, str) and isinstance(b, str):
        return _str_eq(a, b)
    return False


def _num(v):
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _call(ctx, which, fn, args):
    f = fn.lower()
    item = _get(ctx, which)
    if f in GEOMETRIC:
        return 1.0 if (item is not None and ctx.geometric) else 0.0
    if f == "iscoupleddiffpair":
        a, b = ctx.a, ctx.b
        if not a or not a.get("net"):
            return 0.0
        coupled = complement_net(a["net"])
        if coupled is None:
            return 0.0
        if ctx.ctype in ("diff_pair_gap", "length", "skew") and ctx.board and coupled in ctx.board.nets:
            return 1.0
        return 1.0 if b is not None and b.get("net") == coupled else 0.0
    if item is None:
        return 0.0
    vals = [ev(a, ctx) for a in args]
    arg = vals[0] if vals and isinstance(vals[0], str) else ""
    if f == "isplated":
        return 1.0 if (item.get("type") == "Via" or (item.get("type") == "Pad" and item.get("pad_type") == "Through-hole")) else 0.0
    if f == "indiffpair":
        net = item.get("net") or ""
        base = diff_base(net)
        if base is None or ctx.board is None or complement_net(net) not in ctx.board.nets:
            return 0.0
        if fnmatch.fnmatchcase(base, arg) or (base.endswith("_") and fnmatch.fnmatchcase(base[:-1], arg)):
            return 1.0
        return 0.0
    if f in ("hasnetclass", "hasexactnetclass"):
        nc = item.get("netclass")
        if nc is None:
            return 0.0
        if f == "hasexactnetclass":
            return 1.0 if nc == arg else 0.0
        return 1.0 if any(fnmatch.fnmatchcase(c, arg) for c in (item.get("constituents") or nc.split(","))) else 0.0
    if f in ("memberoffootprint",):
        ref, lib = item.get("ref"), item.get("lib")
        if ref is None:
            return 0.0
        if fnmatch.fnmatchcase(ref, arg) or (":" in arg and lib and fnmatch.fnmatchcase(lib, arg)):
            return 1.0
        return 0.0
    if f == "existsonlayer":
        return 1.0 if any(fnmatch.fnmatchcase(l, arg) for l in item.get("layers") or ()) else 0.0
    if f == "ismicrovia":
        return 1.0 if item.get("via_type") == "Micro" else 0.0
    if f in ("isblindvia", "isburiedvia", "isblindburiedvia"):
        return 1.0 if item.get("via_type") in ("Blind", "Buried", "Blind/buried") else 0.0
    if f in ("memberofgroup", "memberof", "memberofsheet", "memberofsheetorchildren", "fromto",
             "hascomponentclass"):
        # not known for routed copper before routing: decided like a geometric test
        return 1.0 if ctx.geometric else 0.0
    if f == "getfield":
        return (item.get("fields") or {}).get(arg, UNDEF)
    raise KeyError(f"unsupported rule function {fn}()")


def ev(node, ctx):
    k = node[0]
    if k == "num":
        return node[1]
    if k == "str":
        return node[1]
    if k == "null":
        return None
    if k == "prop":
        return _prop(ctx, node[1], node[2])
    if k == "call":
        return _call(ctx, node[1], node[2], node[3])
    if k == "not":
        return 0.0 if truth(ev(node[1], ctx)) else 1.0
    if k == "and":
        return 1.0 if truth(ev(node[1], ctx)) and truth(ev(node[2], ctx)) else 0.0
    if k == "or":
        return 1.0 if truth(ev(node[1], ctx)) or truth(ev(node[2], ctx)) else 0.0
    if k == "neg":
        v = _num(ev(node[1], ctx))
        return UNDEF if v is None else -v
    if k == "arith":
        x, y = _num(ev(node[2], ctx)), _num(ev(node[3], ctx))
        if x is None or y is None:
            return UNDEF
        return {"+": x + y, "-": x - y, "*": x * y, "/": x / y if y else UNDEF}[node[1]]
    if k == "cmp":
        op, x, y = node[1], ev(node[2], ctx), ev(node[3], ctx)
        if op in ("==", "!="):
            r = _eq(x, y)
            if r is None:
                return 0.0
            return 1.0 if (r if op == "==" else not r) else 0.0
        xn, yn = _num(x), _num(y)
        if xn is None or yn is None:
            return 0.0
        return 1.0 if {"<": xn < yn, ">": xn > yn, "<=": xn <= yn, ">=": xn >= yn}[op] else 0.0
    raise ValueError(f"bad node {node}")


def truth(v):
    if v is UNDEF or v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return False
    return bool(v)


def diff_base(net):
    """DRC_ENGINE::MatchDpSuffix: the base name of a diff-pair net (suffix +/-, P/N,
    followed only by digits or '_'), else None."""
    for i in range(len(net) - 1, -1, -1):
        ch = net[i]
        if ch.isdigit() or ch == "_":
            continue
        if ch in "+-NP":
            return net[:i] if len(net) - i >= 1 else None
        return None
    return None


def complement_net(net):
    for i in range(len(net) - 1, -1, -1):
        ch = net[i]
        if ch.isdigit() or ch == "_":
            continue
        comp = {"+": "-", "-": "+", "N": "P", "P": "N"}.get(ch)
        if comp is None:
            return None
        return net[:i] + comp + net[i + 1:]
    return None


# ----------------------------------------------------------------------------- rules
@dataclass
class Constraint:
    type: str
    min: float | None = None
    opt: float | None = None
    max: float | None = None
    rule: str = ""
    implicit: bool = True
    severity: str | None = None

    def copy(self):
        return Constraint(self.type, self.min, self.opt, self.max, self.rule, self.implicit, self.severity)


@dataclass
class Rule:
    name: str
    condition: object            # compiled AST or None
    layers: object               # None (all) | set of layer names | callable(layer) -> bool
    constraints: list
    implicit: bool = False
    source: str = ""             # 'board', 'netclass:<name>', 'custom'
    netclass: str | None = None  # implicit netclass rules: hasExactNetclass(<netclass>)
    text: str = ""
    severity: str | None = None


def _layer_test(spec, copper):
    """A rule's (layer ...) as a predicate on layer names."""
    if not spec:
        return None
    s = spec.strip()
    low = s.lower()
    if low == "outer":
        return lambda l: l in (copper[0], copper[-1])
    if low == "inner":
        return lambda l: l in copper[1:-1]
    if "?" in s or "*" in s:
        return lambda l: fnmatch.fnmatchcase(l, s)
    return lambda l: l == s


def read_dru(path):
    """Custom rules of a .kicad_dru: [(name, condition text, layer text, constraints, severity)]."""
    text = "\n".join(ln for ln in open(path, encoding="utf-8", errors="replace").read().splitlines()
                     if not ln.lstrip().startswith("#"))
    tree = sexpr.parse("(dru " + text + ")")
    out = []
    for r in sexpr.kids(tree, "rule"):
        cons = []
        for c in sexpr.kids(r, "constraint"):
            ctype = c[1] if len(c) > 1 and isinstance(c[1], str) else ""
            d = Constraint(ctype, implicit=False)
            for k in ("min", "opt", "max"):
                v = sexpr.value(c, k)
                if v is not None:
                    setattr(d, k, parse_length(v))
            cons.append(d)
        cond = sexpr.value(r, "condition", "") or ""
        out.append(dict(name=r[1] if len(r) > 1 and isinstance(r[1], str) else "", condition=cond,
                        layer=sexpr.value(r, "layer", "") or "", constraints=cons,
                        severity=sexpr.value(r, "severity", None)))
    return out


def parse_length(v):
    if not isinstance(v, str):
        return v
    m = re.match(r"^\s*([-+]?[\d.]+(?:[eE][-+]?\d+)?)\s*(mm|mil|in|um|nm|deg)?\s*$", v)
    if not m:
        return None
    return float(m.group(1)) * UNITS.get(m.group(2) or "mm", 1.0)


@dataclass
class Board:
    """What rule resolution needs to know about a board."""
    copper: list
    settings: dict
    netclasses: dict
    nets: set = field(default_factory=set)
    rules: list = field(default_factory=list)       # implicit + custom, in KiCad's order
    errors: list = field(default_factory=list)      # conditions that failed to compile
    unsupported: set = field(default_factory=set)   # functions met but not modelled


def build(copper, settings, netclasses, nets, dru_path=None):
    """The rule list KiCad's DRC engine would build (DRC_ENGINE::loadImplicitRules + loadRules)."""
    s = settings
    b = Board(copper=list(copper), settings=dict(s), netclasses=dict(netclasses), nets=set(nets))
    board_rule = Rule("board setup constraints", None, None, [
        Constraint("track_width", min=s.get("min_track", 0.0)),
        Constraint("connection_width", min=s.get("min_conn", 0.0)),
        Constraint("hole_size", min=s.get("min_drill", 0.0)),
        Constraint("annular_width", min=s.get("min_annular", 0.0)),
        Constraint("via_diameter", min=s.get("min_via", 0.0)),
        Constraint("hole_to_hole", min=s.get("hole_to_hole", 0.0)),
        Constraint("hole_clearance", min=s.get("hole_clearance", 0.0)),
        Constraint("edge_clearance", min=s.get("edge_clearance", 0.0)),
    ], implicit=True, source="board")
    uvia_rule = Rule("board setup constraints micro-via", compile_condition("A.Via_Type == 'Micro'"), None, [
        Constraint("hole_size", min=s.get("min_uvia_drill", 0.0)),
        Constraint("via_diameter", min=s.get("min_uvia", 0.0))], implicit=True, source="board")
    rules = [board_rule, uvia_rule]
    clearance_rules, specific = [], []
    for name, nc in netclasses.items():
        if nc.get("clearance") is not None:
            clearance_rules.append(Rule(f"netclass '{name}'", None, None,
                                        [Constraint("clearance", min=nc["clearance"])],
                                        implicit=True, source=f"netclass:{name}", netclass=name))
        if nc.get("track_width") is not None:
            clearance_rules.append(Rule(f"netclass '{name}'", None, None,
                                        [Constraint("track_width", min=s.get("min_track", 0.0), opt=nc["track_width"])],
                                        implicit=True, source=f"netclass:{name}", netclass=name))
        if nc.get("dp_width") is not None:
            specific.append(Rule(f"netclass '{name}' (diff pair)", compile_condition("A.inDiffPair('*')"), None,
                                 [Constraint("track_width", min=s.get("min_track", 0.0), opt=nc["dp_width"])],
                                 implicit=True, source=f"netclass:{name}", netclass=name))
        if nc.get("dp_gap") is not None:
            specific.append(Rule(f"netclass '{name}' (diff pair)", None, None,
                                 [Constraint("diff_pair_gap", min=s.get("min_clearance", 0.0), opt=nc["dp_gap"])],
                                 implicit=True, source=f"netclass:{name}", netclass=name))
            if nc.get("clearance") is not None and nc["dp_gap"] < nc["clearance"]:
                specific.append(Rule(f"netclass '{name}' (diff pair)", compile_condition("AB.isCoupledDiffPair()"),
                                     None, [Constraint("clearance", min=nc["dp_gap"])],
                                     implicit=True, source=f"netclass:{name}", netclass=name))
        if nc.get("via_diameter") is not None:
            specific.append(Rule(f"netclass '{name}'", compile_condition("A.Via_Type != 'Micro'"), None,
                                 [Constraint("via_diameter", min=s.get("min_via", 0.0), opt=nc["via_diameter"])],
                                 implicit=True, source=f"netclass:{name}", netclass=name))
        if nc.get("via_drill") is not None:
            specific.append(Rule(f"netclass '{name}'", compile_condition("A.Via_Type != 'Micro'"), None,
                                 [Constraint("hole_size", min=s.get("min_drill", 0.0), opt=nc["via_drill"])],
                                 implicit=True, source=f"netclass:{name}", netclass=name))
        if nc.get("uvia_diameter") is not None:
            specific.append(Rule(f"netclass '{name}' (uvia)", compile_condition("A.Via_Type == 'Micro'"), None,
                                 [Constraint("via_diameter", min=nc["uvia_diameter"])],
                                 implicit=True, source=f"netclass:{name}", netclass=name))
        if nc.get("uvia_drill") is not None:
            specific.append(Rule(f"netclass '{name}' (uvia)", compile_condition("A.Via_Type == 'Micro'"), None,
                                 [Constraint("hole_size", min=s.get("min_uvia_drill", 0.0), opt=nc["uvia_drill"])],
                                 implicit=True, source=f"netclass:{name}", netclass=name))
    clearance_rules.sort(key=lambda r: r.constraints[0].min if r.constraints[0].min is not None else 0.0)
    rules += clearance_rules + specific
    if dru_path:
        for r in read_dru(dru_path):
            try:
                cond = compile_condition(r["condition"])
            except ValueError as e:
                b.errors.append(f"{r['name']}: {e}")
                cond = ("str", "")  # a condition KiCad itself would reject never matches
            rules.append(Rule(r["name"], cond, _layer_test(r["layer"], copper), r["constraints"],
                              implicit=False, source="custom", text=r["condition"], severity=r["severity"]))
    b.rules = rules
    return b


def _non_copper(item):
    return item is not None and (not item.get("copper", True) or item.get("type") == "Rule Area")


def _matches_layer(rule, layer):
    if rule.layers is None or layer is None:
        return True
    return bool(rule.layers(layer))


def evaluate(board, ctype, a, b=None, layer=None, geometric=False):
    """EvalRules(ctype, a, b, layer): the winning Constraint (min/opt/max in mm)."""
    s = board.settings
    a_nc, b_nc = _non_copper(a), _non_copper(b)
    out = Constraint(ctype)
    if ctype in ("clearance", "hole_clearance"):
        oa = a.get("override") if a is not None and a.get("connected") and not b_nc else None
        ob = b.get("override") if b is not None and b.get("connected") and not a_nc else None
        if oa is not None or ob is not None:
            val = max(v for v in (oa, ob) if v is not None)
            if val:
                floor = s.get("min_clearance", 0.0) if ctype == "clearance" else s.get("hole_clearance", 0.0)
                out.min, out.rule = max(val, floor), "local override"
                return out
    winner = None
    for rule in board.rules:
        for c in rule.constraints:
            if c.type != ctype:
                continue
            if ctype == "clearance" and (a_nc or b_nc):
                continue  # clearance rules apply only between copper items
            if rule.implicit and rule.netclass is not None:
                ok_a = a is not None and a.get("connected") and a.get("netclass") == rule.netclass
                ok_b = b is not None and b.get("connected") and b.get("netclass") == rule.netclass
                if not (ok_a or ok_b):
                    continue
            if not _matches_layer(rule, layer):
                continue
            if ctype == "hole_to_hole" and not (a.get("drilled") or (b is not None and b.get("drilled"))):
                continue
            if rule.condition is not None and not _cond(board, rule, ctype, a, b, layer, geometric):
                continue
            if c.min is not None:
                out.min = c.min
            if c.opt is not None:
                out.opt = c.opt
            if c.max is not None:
                out.max = c.max
            out.rule, out.implicit, out.severity = rule.name, rule.implicit, rule.severity
            winner = rule
    if ctype in CLEARANCE_TYPES and out.min is not None:
        out.min = min(out.min, 100.0)
    if winner is not None and not winner.implicit:
        return out
    if ctype == "clearance":
        clr = out.min or 0.0
        for it in (a, b):
            if it is not None and it.get("connected") and it.get("local") is not None and it["local"] > clr:
                clr, out.rule = it["local"], "local clearance"
        if not a_nc and not b_nc and clr < s.get("min_clearance", 0.0):
            clr, out.rule = s.get("min_clearance", 0.0), "board minimum"
        out.min = clr
    elif ctype == "diff_pair_gap":
        if (out.min or 0.0) < s.get("min_clearance", 0.0):
            out.min, out.rule = s.get("min_clearance", 0.0), "board minimum"
    return out


def _cond(board, rule, ctype, a, b, layer, geometric):
    try:
        if truth(ev(rule.condition, Ctx(a, b, layer, ctype, geometric, board))):
            return True
        if b is not None and truth(ev(rule.condition, Ctx(b, a, layer, ctype, geometric, board))):
            return True
    except KeyError as e:
        board.unsupported.add(str(e))
        return geometric  # unknown function: assume it matches only on the strict pass
    return False


def strictest(board, ctype, a, b=None, layer=None):
    """The tighter of evaluate(geometric=False) and evaluate(geometric=True): the larger
    minimum and the smaller maximum."""
    c0 = evaluate(board, ctype, a, b, layer, geometric=False)
    c1 = evaluate(board, ctype, a, b, layer, geometric=True)
    out = c0.copy()
    if c1.min is not None and (out.min is None or c1.min > out.min):
        out.min, out.rule = c1.min, c1.rule + " (inside its area)"
    if c1.max is not None and (out.max is None or c1.max < out.max):
        out.max = c1.max
    return out
