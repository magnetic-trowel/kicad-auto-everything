# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check a KiCad 10 custom-rules file (.kicad_dru) before anything relies on it.

KiCad drops the WHOLE file without any message when one rule fails to parse: kicad-cli
DRC then runs without custom rules, so a broken file makes DRC easier to pass, silently
(measured on 10.0.7: a `;` comment, a misspelled constraint/function/property/layer/
severity/option, a time unit on a clearance, a duplicate constraint or a missing paren
each make every rule vanish). Two passes:

    static_check(text)  -> [Issue]   pure Python, instant; names line, column and the fix
    kicad_check(text)   -> KicadResult   KiCad's own parser, ~1 s: runs kicad-cli DRC on a
                        probe board with a sentinel rule appended; if the sentinel's
                        violation is missing, KiCad rejected the file, and each rule is then
                        tried alone to name the culprits

CLI: `kae dru-check FILE [--kicad auto|on|off]`, or `python -m kae.board.dru_check FILE`.
Exit 0 = clean (warnings allowed), 1 = errors found, 2 = could not run.
Language reference: docs/topics/kicad/drc-rule-language-reference.md.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- vocabulary
# Names come from kae/board/dru_vocab/<label>.json, generated from KiCad's source and
# verified against a running KiCad (kae.board.dru_vocab); use_vocab() loads one.
# Argument forms are not in the source in a parseable shape and stay here.
RANGE = "range"            # (min v) (opt v) (max v)
FORMS = {"via_dangling": "none", "bridged_mask": "none", "disallow": "disallow",
         "zone_connection": "zone_connection", "min_resolved_spokes": "int", "assertion": "string"}
UNITLESS = {"via_count", "min_resolved_spokes"}
TIME_OK = {"length", "skew"}
ANGLE = {"track_angle"}
UNITS = {"mm", "mil", "in", "deg", "ps", "fs"}
REPLACEMENTS = {"insidearea": "enclosedByArea/intersectsArea", "insidecourtyard": "intersectsCourtyard",
                "insidefrontcourtyard": "intersectsFrontCourtyard",
                "insidebackcourtyard": "intersectsBackCourtyard", "memberof": "memberOfGroup"}
VOCAB_LABEL = ""
CONSTRAINTS: dict = {}
DEPRECATED_CONSTRAINTS: dict = {}
MASTER_ONLY_CONSTRAINTS: set = set()
DISALLOW_ITEMS: set = set()
ZONE_CONNECTIONS: set = set()
SEVERITIES: set = set()
FUNCTIONS: set = set()
DEPRECATED_FUNCTIONS: dict = {}
MASTER_ONLY_FUNCTIONS: set = set()
PROPERTIES: set = set()


def use_vocab(label: str | None = None) -> str:
    """Load the vocabulary for `label` (e.g. '10.0'); default: the newest release label."""
    global VOCAB_LABEL, CONSTRAINTS, DEPRECATED_CONSTRAINTS, MASTER_ONLY_CONSTRAINTS, DISALLOW_ITEMS
    global ZONE_CONNECTIONS, SEVERITIES, FUNCTIONS, DEPRECATED_FUNCTIONS, MASTER_ONLY_FUNCTIONS, PROPERTIES
    from kae.board import dru_vocab
    have = dru_vocab.labels()
    releases = sorted((l for l in have if re.fullmatch(r"\d+\.\d+", l)), key=lambda l: tuple(map(int, l.split("."))))
    label = label or (releases[-1] if releases else have[-1])
    if label == VOCAB_LABEL:
        return label
    v = dru_vocab.load(label)
    CONSTRAINTS = {c: FORMS.get(c, RANGE) for c in v["constraints"]}
    DEPRECATED_CONSTRAINTS = dict(v["deprecated_constraints"])
    DISALLOW_ITEMS, ZONE_CONNECTIONS = set(v["disallow_items"]), set(v["zone_connections"])
    SEVERITIES = set(v["severities"])
    FUNCTIONS = {f.lower() for f in v["functions"]}
    DEPRECATED_FUNCTIONS = {f.lower(): REPLACEMENTS.get(f.lower(), "a current function")
                            for f in v["deprecated_functions"]}
    PROPERTIES = {p.lower() for p in v["properties"]}
    MASTER_ONLY_CONSTRAINTS, MASTER_ONLY_FUNCTIONS = set(), set()
    if "master" in have and label != "master":
        m = dru_vocab.load("master")
        MASTER_ONLY_CONSTRAINTS = set(m["constraints"]) - set(CONSTRAINTS)
        MASTER_ONLY_FUNCTIONS = {f.lower() for f in m["functions"]} - FUNCTIONS
    VOCAB_LABEL = label
    return label


def kicad_version(cli: list) -> str:
    r = subprocess.run([*cli, "version"], capture_output=True, text=True, timeout=120)
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""


def vocab_for(version: str) -> str | None:
    """The bundled vocabulary label for a KiCad version string ('10.0.7' -> '10.0'), or None."""
    from kae.board import dru_vocab
    m = re.match(r"(\d+)\.(\d+)", version)
    if m and f"{m.group(1)}.{m.group(2)}" in dru_vocab.labels():
        return f"{m.group(1)}.{m.group(2)}"
    return None


_LAYER = re.compile(r"(F|B)\.(Cu|Adhes|Adhesive|Paste|SilkS|Silkscreen|Mask|CrtYd|Courtyard|Fab)"
                    r"|In([1-9]|[12][0-9]|30)\.Cu|Dwgs\.User|Cmts\.User|Eco[12]\.User"
                    r"|User\.(Drawings|Comments|Eco[12]|[1-9][0-9]?)|Edge\.Cuts|Margin|outer|inner"
                    r"|[?*]\.(Cu|Adhes|Adhesive|Paste|SilkS|Silkscreen|Mask|CrtYd|Courtyard|Fab)")
_VALUE = re.compile(r"^(-?(?:\d+\.?\d*|\.\d+))(mm|mil|in|deg|ps|fs)?$")


@dataclass
class Issue:
    line: int
    col: int
    severity: str          # "error" | "warning"
    message: str
    rule: str = ""

    def __str__(self):
        where = f" (rule {self.rule!r})" if self.rule else ""
        return f"{self.line}:{self.col}: {self.severity}: {self.message}{where}"


@dataclass
class Node:
    items: list
    line: int
    col: int


@dataclass
class Atom:
    text: str
    quoted: bool
    line: int
    col: int


# ---------------------------------------------------------------- s-expression reader
def _read(text: str, issues: list) -> list:
    """Top-level nodes; records lexical errors in `issues`."""
    stack = [Node([], 0, 0)]
    i, line, col, n = 0, 1, 1, len(text)
    at_line_start = True

    def adv(k=1):
        nonlocal i, line, col
        for _ in range(k):
            if text[i] == "\n":
                line, col = line + 1, 1
            else:
                col += 1
            i += 1

    while i < n:
        c = text[i]
        if c == "\n":
            at_line_start = True
            adv()
            continue
        if c in " \t\r":
            adv()
            continue
        if c == "#":
            if not at_line_start:
                issues.append(Issue(line, col, "error",
                                    "'#' comments must start a line (after optional spaces); "
                                    "KiCad rejects a comment after other text on the same line"))
            while i < n and text[i] != "\n":
                adv()
            continue
        at_line_start = False
        if c == ";":
            issues.append(Issue(line, col, "error", "';' is not a comment in .kicad_dru; "
                                                    "put '#' at the start of its own line"))
            while i < n and text[i] != "\n":
                adv()
            continue
        if c == "(":
            stack.append(Node([], line, col))
            adv()
        elif c == ")":
            if len(stack) == 1:
                issues.append(Issue(line, col, "error", "unmatched ')'"))
            else:
                node = stack.pop()
                stack[-1].items.append(node)
            adv()
        elif c == '"':
            l0, c0 = line, col
            adv()
            buf = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    buf.append(text[i + 1])
                    adv(2)
                    continue
                buf.append(text[i])
                adv()
            if i >= n:
                issues.append(Issue(l0, c0, "error", "unterminated string"))
                break
            adv()
            stack[-1].items.append(Atom("".join(buf), True, l0, c0))
        else:
            l0, c0, j = line, col, i
            while i < n and text[i] not in ' \t\r\n()";':
                adv()
            stack[-1].items.append(Atom(text[j:i], False, l0, c0))
    while len(stack) > 1:
        node = stack.pop()
        issues.append(Issue(node.line, node.col, "error", "'(' is never closed"))
        stack[-1].items.append(node)
    return stack[0].items


def _head(node) -> str:
    return node.items[0].text if isinstance(node, Node) and node.items and isinstance(node.items[0], Atom) else ""


# ---------------------------------------------------------------- condition expressions
_TOK = re.compile(r"\s*(?:(?P<str>'(?:[^'\\]|\\.)*')|(?P<num>\d+\.?\d*(?:mm|mil|in|deg|ps|fs)?)"
                  r"|(?P<id>[A-Za-z_][A-Za-z_0-9.]*)|(?P<op>&&|\|\||==|!=|>=|<=|[<>!+\-*/(),])"
                  r"|(?P<bad>\S))")


def _check_expr(expr: str, where: tuple, rule: str, issues: list):
    line, col = where
    if not expr.strip():
        return
    if '"' in expr:
        issues.append(Issue(line, col, "error", "double quote inside a condition; quote strings "
                                                "with single quotes: A.NetName == '/USB_DP'", rule))
    if "${" in expr:
        issues.append(Issue(line, col, "warning", "${...} is substituted before parsing; an undefined "
                                                  "or object-dependent variable (e.g. ${LAYER}) rejects the file", rule))
    toks = []
    pos = 0
    while pos < len(expr):
        m = _TOK.match(expr, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        kind = m.lastgroup
        toks.append((kind, m.group(kind)))
        if kind == "bad" and m.group(kind) == "'":
            break  # unterminated string: the rest is its contents
    depth = 0
    for k, t in toks:
        if k == "bad":
            if t == "'":
                issues.append(Issue(line, col, "warning", "unterminated '...' string in condition; KiCad "
                                                          "loads the file, but what the rule matches is unverified", rule))
                break
            elif t in "&|=":
                issues.append(Issue(line, col, "error", f"'{t}' alone is not an operator; use &&, || or ==", rule))
            else:
                issues.append(Issue(line, col, "error", f"unexpected character {t!r} in condition", rule))
        elif t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
            if depth < 0:
                issues.append(Issue(line, col, "error", "unmatched ')' in condition", rule))
                depth = 0
    if depth > 0:
        issues.append(Issue(line, col, "error", "unclosed '(' in condition", rule))
    for idx, (k, t) in enumerate(toks):
        if k != "id":
            continue
        low = t.lower()
        if low in ("and", "or", "not"):
            issues.append(Issue(line, col, "error", f"'{t}' is not an operator; use &&, || or !", rule))
            continue
        if low in ("true", "false"):
            issues.append(Issue(line, col, "error", f"no boolean literals: write 'A.Locked' or "
                                                    f"'!A.Locked', not '== {t}'", rule))
            continue
        if low == "null":
            continue
        parts = t.split(".")
        if len(parts) == 1:
            issues.append(Issue(line, col, "warning", f"bare name '{t}': KiCad loads it, but write A.{t}/B.{t} "
                                                      f"or quote it as a string unless you know it resolves", rule))
            continue
        obj, name = parts[0], ".".join(parts[1:])
        if len(parts) > 2 and obj in ("A", "B", "AB"):
            issues.append(Issue(line, col, "error", f"'{t}': one property per object; KiCad rejects chained "
                                                    f"properties (footprint properties such as Reference are "
                                                    f"inherited: write A.{parts[-1]} or A.memberOfFootprint('J1'))", rule))
            continue
        if obj not in ("A", "B", "AB"):
            issues.append(Issue(line, col, "error", f"'{obj}.' is not an object; use A., B. or AB.", rule))
            continue
        is_call = idx + 1 < len(toks) and toks[idx + 1][1] == "("
        nl = name.lower()
        if is_call:
            if nl in MASTER_ONLY_FUNCTIONS:
                issues.append(Issue(line, col, "error", f"{name}() exists only in KiCad master, not in "
                                                        f"KiCad {VOCAB_LABEL}; it rejects the file", rule))
            elif nl in DEPRECATED_FUNCTIONS:
                issues.append(Issue(line, col, "warning", f"{name}() is deprecated; use "
                                                          f"{DEPRECATED_FUNCTIONS[nl]}()", rule))
            elif nl not in FUNCTIONS:
                close = [f for f in FUNCTIONS if f[:5] == nl[:5]]
                hint = f"; did you mean {close[0]}()?" if close else ""
                issues.append(Issue(line, col, "error", f"unknown function {name}(){hint}", rule))
            elif obj == "AB" and nl != "iscoupleddiffpair":
                issues.append(Issue(line, col, "warning", f"AB.{name}(): only isCoupledDiffPair() "
                                                          f"is a pair function", rule))
        elif nl not in PROPERTIES and difflib.get_close_matches(nl, PROPERTIES, 1, 0.8):
            near = difflib.get_close_matches(nl, PROPERTIES, 1, 0.8)[0]
            issues.append(Issue(line, col, "error", f"unknown property '{name}'; did you mean '{near}'? "
                                                    f"(KiCad rejects the file on an unknown property)", rule))
        elif nl not in PROPERTIES:
            hint = (" (use A.getField('Value'))" if nl == "value" else
                    "; '-' is read as minus, so hyphenated property names cannot be used" if "-" in t else "")
            issues.append(Issue(line, col, "error", f"'{name}' is not among the {len(PROPERTIES)} properties "
                                                    f"KiCad {VOCAB_LABEL} accepts{hint}; KiCad rejects the "
                                                    f"whole file", rule))
    if toks and toks[-1] == ("bad", "'"):
        return  # unterminated string: structure checks would only repeat that warning
    # operand/operator alternation: catches dangling or doubled operators and missing ones
    BIN = {"&&", "||", "==", "!=", ">=", "<=", "<", ">", "+", "*", "/"}
    want_operand, prev = True, None
    for k, t in toks:
        if k == "bad":
            continue
        if t in ("(", ","):
            if t == "(" and not want_operand and prev and prev[0] != "id":
                issues.append(Issue(line, col, "error", f"missing operator before '('", rule))
            want_operand = True
        elif t == ")":
            if want_operand and prev and prev[1] not in ("(",):
                issues.append(Issue(line, col, "error", f"operator {prev[1]!r} has no right-hand side", rule))
            want_operand = False
        elif t in ("!",):
            if not want_operand:
                issues.append(Issue(line, col, "error", "'!' after an operand; did you mean '!='?", rule))
        elif t == "-":
            want_operand = True
        elif t in BIN:
            if want_operand:
                issues.append(Issue(line, col, "error", f"operator {t!r} has no left-hand side", rule))
            want_operand = True
        else:  # operand
            if not want_operand:
                issues.append(Issue(line, col, "error", f"missing operator before {t!r}", rule))
            want_operand = False
        prev = (k, t)
    if toks and want_operand and prev and prev[1] not in (")",):
        issues.append(Issue(line, col, "error", f"condition ends with operator {prev[1]!r}", rule))
    # precedence trap: && binds LOWER than || in KiCad (reverse of C)
    lvl, seen = 0, [set()]
    for k, t in toks:
        if t == "(":
            lvl += 1
            seen.append(set())
        elif t == ")":
            lvl = max(0, lvl - 1)
            if len(seen) > 1:
                seen.pop()
        elif t in ("&&", "||"):
            seen[-1].add(t)
            if len(seen[-1]) == 2:
                issues.append(Issue(line, col, "warning", "&& and || mixed without parentheses: in KiCad "
                                                          "'a && b || c' means 'a && (b || c)'; add parentheses", rule))
                seen[-1].add("reported")


# ---------------------------------------------------------------- rule structure
def _value(atom, ctype, rule, issues):
    if not isinstance(atom, Atom):
        issues.append(Issue(atom.line, atom.col, "error", "expected a value, found a list", rule))
        return
    m = _VALUE.match(atom.text)
    if not m and re.fullmatch(r"-?\d+,\d+(mm|mil|in|deg|ps|fs)?", atom.text):
        issues.append(Issue(atom.line, atom.col, "warning", f"decimal comma in '{atom.text}'; KiCad loads the "
                                                            f"file but the value it reads is unverified: use '.'", rule))
        return
    if not m:
        u = re.sub(r"^-?[\d.]+", "", atom.text)
        msg = (f"unit '{u}' not accepted; use one of {', '.join(sorted(UNITS))}" if u and u != atom.text
               else f"'{atom.text}' is not a number with a unit (e.g. 0.2mm)")
        issues.append(Issue(atom.line, atom.col, "error", msg, rule))
        return
    unit = m.group(2)
    if ctype in UNITLESS:
        if unit:
            issues.append(Issue(atom.line, atom.col, "error", f"{ctype} takes a bare count, not '{atom.text}'", rule))
        return
    if unit is None:
        issues.append(Issue(atom.line, atom.col, "error",
                            f"'{atom.text}' has no unit; KiCad rejects bare numbers here (write e.g. {atom.text}mm)", rule))
    elif unit in ("ps", "fs") and ctype not in TIME_OK:
        issues.append(Issue(atom.line, atom.col, "error", f"time unit '{unit}' only allowed in length and skew", rule))
    elif unit == "deg" and ctype not in ANGLE:
        issues.append(Issue(atom.line, atom.col, "error", f"'deg' is only for track_angle", rule))
    elif ctype in ANGLE and unit != "deg":
        issues.append(Issue(atom.line, atom.col, "error", "track_angle values take 'deg'", rule))
    return unit


def _check_constraint(node: Node, rule: str, issues: list) -> str:
    it = node.items
    if len(it) < 2 or not isinstance(it[1], Atom):
        issues.append(Issue(node.line, node.col, "error", "constraint needs a type", rule))
        return ""
    ctype = it[1].text
    if ctype in MASTER_ONLY_CONSTRAINTS:
        issues.append(Issue(it[1].line, it[1].col, "error", f"'{ctype}' exists only in KiCad master, not "
                                                            f"in KiCad {VOCAB_LABEL}; it rejects the whole file", rule))
        return ctype
    if ctype in DEPRECATED_CONSTRAINTS:
        issues.append(Issue(it[1].line, it[1].col, "warning",
                            f"'{ctype}' is deprecated; use '{DEPRECATED_CONSTRAINTS[ctype]}'", rule))
        ctype = DEPRECATED_CONSTRAINTS[ctype]
    form = CONSTRAINTS.get(ctype)
    if form is None:
        close = [c for c in CONSTRAINTS if c[:4] == ctype[:4]]
        hint = f"; did you mean '{close[0]}'?" if close else ""
        issues.append(Issue(it[1].line, it[1].col, "error", f"unknown constraint '{ctype}'{hint}", rule))
        return ctype
    args = it[2:]
    if form == RANGE:
        seen, vals = set(), {}
        for a in args:
            h = _head(a)
            if h in ("min", "opt", "max"):
                if h in seen:
                    issues.append(Issue(a.line, a.col, "warning", f"repeated ({h} ...); KiCad loads it, keep one", rule))
                seen.add(h)
                if (len(a.items) == 3 and all(isinstance(x, Atom) for x in a.items[1:])
                        and a.items[2].text in UNITS):
                    issues.append(Issue(a.line, a.col, "warning",
                                        f"write the unit attached: ({h} {a.items[1].text}{a.items[2].text})", rule))
                    a = Node([a.items[0], Atom(a.items[1].text + a.items[2].text, False, a.line, a.col)],
                             a.line, a.col)
                elif len(a.items) != 2:
                    issues.append(Issue(a.line, a.col, "error",
                                        f"({h} ...) takes one value with its unit attached, e.g. ({h} 0.2mm)", rule))
                    continue
                _value(a.items[1], ctype, rule, issues)
                m = _VALUE.match(a.items[1].text) if isinstance(a.items[1], Atom) else None
                if m:
                    vals[h] = (float(m.group(1)), m.group(2))
            elif h == "within_diff_pairs" and ctype == "skew":
                if len(a.items) != 1:
                    issues.append(Issue(a.line, a.col, "error", "(within_diff_pairs) takes no arguments", rule))
            else:
                what = f"({h} ...)" if isinstance(a, Node) else repr(a.text)
                hint = " (only skew takes (within_diff_pairs))" if h.startswith("within") else ""
                issues.append(Issue(a.line, a.col, "error", f"{what} not allowed in {ctype}{hint}", rule))
        if not seen:
            issues.append(Issue(node.line, node.col, "warning", f"{ctype} has no (min/opt/max); KiCad loads it "
                                                                f"(useful only with a severity such as ignore)", rule))
        if "min" in vals and "max" in vals and vals["min"][1] == vals["max"][1] and vals["min"][0] > vals["max"][0]:
            issues.append(Issue(node.line, node.col, "warning", "min is larger than max", rule))
    elif form == "none":
        if args:
            issues.append(Issue(node.line, node.col, "error", f"{ctype} takes no arguments", rule))
    elif form == "disallow":
        if not args:
            issues.append(Issue(node.line, node.col, "error", "disallow needs item types", rule))
        for a in args:
            if not isinstance(a, Atom) or a.text not in DISALLOW_ITEMS:
                bad = a.text if isinstance(a, Atom) else "(...)"
                issues.append(Issue(a.line, a.col, "error", f"'{bad}' is not a disallow item; use "
                                                            f"{' '.join(sorted(DISALLOW_ITEMS))}", rule))
    elif form == "zone_connection":
        if len(args) != 1 or not isinstance(args[0], Atom) or args[0].text not in ZONE_CONNECTIONS:
            issues.append(Issue(node.line, node.col, "error", "zone_connection takes one of solid, "
                                                              "thermal_reliefs, none", rule))
    elif form == "int":
        if len(args) != 1 or not isinstance(args[0], Atom) or not re.fullmatch(r"[0-4]", args[0].text):
            issues.append(Issue(node.line, node.col, "error", f"{ctype} takes a bare integer 0-4", rule))
    elif form == "string":
        if len(args) != 1 or not isinstance(args[0], Atom) or not args[0].quoted:
            issues.append(Issue(node.line, node.col, "error", "assertion takes one quoted expression", rule))
        else:
            _check_expr(args[0].text, (args[0].line, args[0].col), rule, issues)
    return ctype


def _check_rule(node: Node, issues: list) -> str:
    it = node.items
    if len(it) < 2 or not isinstance(it[1], Atom):
        issues.append(Issue(node.line, node.col, "error", "rule needs a name: (rule \"name\" ...)"))
        return ""
    name = it[1].text
    seen, ctypes = {}, set()
    for child in it[2:]:
        h = _head(child)
        if not isinstance(child, Node):
            issues.append(Issue(child.line, child.col, "error", f"stray token {child.text!r} inside rule", name))
            continue
        if h == "constraint":
            ct = _check_constraint(child, name, issues)
            if ct in ctypes:
                issues.append(Issue(child.line, child.col, "error", f"rule already has a '{ct}' constraint "
                                                                    f"(one per type per rule; KiCad rejects the file)", name))
            ctypes.add(ct)
            continue
        if h not in ("condition", "layer", "severity"):
            issues.append(Issue(child.line, child.col, "error", f"unknown clause ({h} ...); a rule takes "
                                                                "severity, layer, condition and constraint", name))
            continue
        if h in seen:
            if h == "condition":
                issues.append(Issue(child.line, child.col, "warning", "second condition silently overwrites the "
                                                                      "first; join them with && in one condition", name))
            else:
                issues.append(Issue(child.line, child.col, "error", f"second ({h} ...) clause", name))
        seen[h] = child
        args = child.items[1:]
        if len(args) != 1 or not isinstance(args[0], Atom):
            issues.append(Issue(child.line, child.col, "error", f"({h} ...) takes exactly one value", name))
            continue
        v = args[0]
        if h == "severity" and v.text not in SEVERITIES:
            issues.append(Issue(v.line, v.col, "error", f"severity '{v.text}' not one of "
                                                        f"{', '.join(sorted(SEVERITIES))}", name))
        elif h == "layer" and not _LAYER.fullmatch(v.text):
            issues.append(Issue(v.line, v.col, "error", f"layer '{v.text}' is not a KiCad layer name "
                                                        f"(e.g. \"F.Cu\", \"In1.Cu\", \"F.Courtyard\", outer, inner)", name))
        elif h == "condition":
            if not v.quoted:
                issues.append(Issue(v.line, v.col, "error", "condition must be a double-quoted string", name))
            _check_expr(v.text, (v.line, v.col), name, issues)
    if not ctypes:
        issues.append(Issue(node.line, node.col, "warning", "rule has no constraint; it does nothing", name))
    return name


def static_check(text: str, vocab: str | None = None) -> list[Issue]:
    """All problems found without KiCad, sorted by position. `vocab`: KiCad version label
    ('10.0'); default: the one already loaded, else the newest bundled release."""
    use_vocab(vocab) if vocab or not VOCAB_LABEL else None
    issues: list[Issue] = []
    top = _read(text, issues)
    names, version_seen = {}, False
    for k, node in enumerate(top):
        if isinstance(node, Atom):
            issues.append(Issue(node.line, node.col, "error", f"stray token {node.text!r} at top level"))
            continue
        h = _head(node)
        if h == "version":
            if k != 0 and not version_seen:
                issues.append(Issue(node.line, node.col, "warning", "(version 1) should be the first form"))
            version_seen = True
            if len(node.items) != 2 or not isinstance(node.items[1], Atom) or node.items[1].text != "1":
                issues.append(Issue(node.line, node.col, "warning", "KiCad 10 writes (version 1)"))
        elif h == "rule":
            name = _check_rule(node, issues)
            if name in names:
                issues.append(Issue(node.line, node.col, "warning", f"rule name repeated (first at line "
                                                                    f"{names[name]}); DRC reports cite rules by name", name))
            names.setdefault(name, node.line)
        else:
            issues.append(Issue(node.line, node.col, "error", f"({h} ...) at top level; only version and rule "
                                                              "are allowed"))
    if not version_seen and any(isinstance(n, Node) for n in top):
        issues.append(Issue(1, 1, "error", "missing (version 1); KiCad rejects the file without it"))
    return sorted(issues, key=lambda i: (i.line, i.col))


def rule_spans(text: str) -> list[tuple[str, int, str]]:
    """(name, line, source text) of each top-level (rule ...) form, comments stripped."""
    out, depth, start, line, i, n = [], 0, None, 1, 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "#" and (i == 0 or text[:i].rsplit("\n", 1)[-1].strip() == ""):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif c == "(":
            if depth == 0:
                start, sline = i, line
            depth += 1
        elif c == ")" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                src = text[start:i + 1]
                m = re.match(r'\(\s*rule\s+("(?:[^"\\]|\\.)*"|[^\s()]+)', src)
                if m:
                    out.append((m.group(1).strip('"'), sline, src))
        if c == "\n":
            line += 1
        i += 1
    return out


# ---------------------------------------------------------------- KiCad pass
SENTINEL = "__kae_dru_check_sentinel__"
_SENTINEL_RULE = (f'(rule "{SENTINEL}" (condition "A.NetName == \'KAE_PROBE_A\'") '
                  f'(constraint clearance (min 3mm)))')
# Two parallel 10 mm tracks 1 mm apart on different nets inside an outline: the sentinel's
# 3 mm clearance must fire whenever KiCad loaded the rules file.
_PROBE_PCB = """(kicad_pcb (version 20260206) (generator "pcbnew") (generator_version "10.0")
 (general (thickness 1.6) (legacy_teardrops no)) (paper "A4")
 (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))
 (setup (pad_to_mask_clearance 0))
 (net 0 "") (net 1 "KAE_PROBE_A") (net 2 "KAE_PROBE_B")
 (segment (start 0 0) (end 10 0) (width 0.2) (layer "F.Cu") (net 1))
 (segment (start 0 1) (end 10 1) (width 0.2) (layer "F.Cu") (net 2))
 (gr_rect (start -5 -5) (end 15 6) (stroke (width 0.1) (type solid)) (fill no) (layer "Edge.Cuts"))
)
"""


@dataclass
class KicadResult:
    accepted: bool
    culprits: list = field(default_factory=list)   # [(rule name, line)] rejected when tried alone
    outside_rules: bool = False                     # rejected although every rule alone is accepted
    version: str = ""
    empty: bool = False                             # no rules or other forms: nothing to load


def _kicad_accepts(cli: list, rules_text: str, tmp: Path) -> tuple[bool, str]:
    d = Path(tempfile.mkdtemp(dir=tmp))
    (d / "probe.kicad_pcb").write_text(_PROBE_PCB)
    (d / "probe.kicad_pro").write_text("{}\n")
    (d / "probe.kicad_dru").write_text(rules_text.rstrip("\n") + "\n" + _SENTINEL_RULE + "\n")
    out = d / "drc.json"
    r = subprocess.run([*cli, "pcb", "drc", "--format", "json", "-o", str(out), str(d / "probe.kicad_pcb")],
                       capture_output=True, text=True, timeout=300)
    if not out.exists():
        raise RuntimeError(f"kicad-cli wrote no report (rc {r.returncode}): {r.stderr.strip()[-400:]}")
    rep = json.loads(out.read_text())
    hit = any(SENTINEL in v.get("description", "") for v in rep.get("violations", []))
    return hit, rep.get("kicad_version", "")


def kicad_check(text: str, cli: list | None = None, workers: int = 8) -> KicadResult:
    """Ask KiCad itself whether it loads `text`; if not, find the rules it rejects."""
    if cli is None:
        from kae.route.drc import kicad_cli
        cli = kicad_cli()
    if not any(ln.strip() and not ln.lstrip().startswith("#") for ln in text.splitlines()):
        return KicadResult(True, empty=True)
    base = Path(tempfile.gettempdir())
    with tempfile.TemporaryDirectory(dir=base) as tmp:
        tmp = Path(tmp)
        ok, ver = _kicad_accepts(cli, text, tmp)
        if ok:
            return KicadResult(True, version=ver)
        rules = rule_spans(text)
        with concurrent.futures.ThreadPoolExecutor(max(1, workers)) as ex:
            alone = list(ex.map(lambda r: _kicad_accepts(cli, "(version 1)\n" + r[2], tmp)[0], rules))
        culprits = [(name, line) for (name, line, _), good in zip(rules, alone) if not good]
        return KicadResult(False, culprits, outside_rules=not culprits, version=ver)


# ---------------------------------------------------------------- CLI
def add_arguments(ap: argparse.ArgumentParser):
    ap.add_argument("files", nargs="+", help=".kicad_dru files (or '-' for stdin)")
    ap.add_argument("--kicad", default="auto", choices=("auto", "on", "off"),
                    help="also run KiCad's own parser (auto: when kicad-cli is found)")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--vocab", help="KiCad vocabulary label for the static pass (default: the installed "
                                    "KiCad's, else the newest bundled release)")


def run(a) -> int:
    cli = None
    if a.kicad != "off":
        try:
            from kae.route.drc import kicad_cli
            cli = kicad_cli()
        except Exception as e:  # kicad-cli missing
            if a.kicad == "on":
                print(f"error: KiCad pass requested but kicad-cli not found ({e})")
                return 2
    label = a.vocab
    if not label and cli:
        ver = kicad_version(cli)
        label = vocab_for(ver)
        if not label:
            print(f"warning: no bundled vocabulary for KiCad {ver}; static pass uses the newest one. "
                  f"Generate it: python -m kae.board.dru_vocab fetch <tag>; ... sync <src> <major.minor> --verify")
    label = use_vocab(label)
    worst = 0
    for f in a.files:
        text = sys.stdin.read() if f == "-" else Path(f).read_text(encoding="utf-8", errors="replace")
        issues = static_check(text)
        for i in issues:
            print(f"{f}:{i}")
        if any(i.severity == "error" or (a.strict and i.severity == "warning") for i in issues):
            worst = 1
        if not issues:
            print(f"{f}: no static problems (vocabulary {label})")
        if cli:
            try:
                res = kicad_check(text, cli)
            except Exception as e:
                print(f"{f}: error: KiCad pass failed to run: {e}")
                return 2
            if res.empty:
                print(f"{f}: no rules (only comments or blank)")
            elif res.accepted:
                print(f"{f}: KiCad {res.version} loads the file")
            else:
                worst = 1
                print(f"{f}: error: KiCad {res.version} REJECTS this file: DRC would silently run "
                      f"without any of its custom rules")
                for name, line in res.culprits:
                    print(f"{f}:{line}: error: KiCad rejects rule {name!r}")
                if res.outside_rules:
                    print(f"{f}: error: every rule loads alone; the problem is outside the rules "
                          f"(comment, stray token, missing (version 1))")
    return worst


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kae dru-check", description=__doc__.split("\n\n")[0])
    add_arguments(ap)
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
