# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Static lint for generated .kicad_dru files.

kicad-cli 10.0.7 `pcb drc` silently ignores unknown constraints and unknown condition
functions, so running DRC proves nothing about the rules. This checks them against the
KiCad 10.0 grammar in docs/topics/kicad/drc-rule-language-reference.md.
"""
import re

from . import sexpr

CONSTRAINTS = {
    "clearance", "physical_clearance", "physical_hole_clearance", "hole_clearance", "edge_clearance",
    "courtyard_clearance", "creepage", "connection_width", "silk_clearance", "hole_size", "hole_to_hole",
    "annular_width", "via_diameter", "via_count", "via_dangling", "disallow", "track_width", "track_angle",
    "track_segment_length", "diff_pair_gap", "diff_pair_uncoupled", "length", "skew",
    "solder_mask_expansion", "solder_mask_sliver", "solder_paste_abs_margin", "solder_paste_rel_margin",
    "bridged_mask", "text_height", "text_thickness", "zone_connection", "thermal_relief_gap",
    "thermal_spoke_width", "min_resolved_spokes", "assertion",
}
FUNCTIONS = {
    "enclosedByArea", "intersectsArea", "intersectsKeepout", "existsOnLayer", "fromTo", "getField",
    "hasComponentClass", "hasNetclass", "hasExactNetclass", "inDiffPair", "isCoupledDiffPair",
    "intersectsCourtyard", "intersectsFrontCourtyard", "intersectsBackCourtyard", "isBlindVia",
    "isBuriedVia", "isBlindBuriedVia", "isMicroVia", "isPlated", "memberOfGroup", "memberOfFootprint",
    "memberOfSheet", "memberOfSheetOrChildren",
}
LENGTH_UNITS = ("mm", "mil", "in")
TIME_UNITS = ("ps", "fs")


def lint(text, netclasses=None):
    """Problems found in a .kicad_dru text (empty list = clean)."""
    probs = []
    body = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    try:
        forms = sexpr.loads("(dru\n" + body + "\n)")
    except ValueError as e:
        return [f"not an s-expression: {e}"]
    forms = forms[1:]
    if not forms or forms[0] != ["version", "1"]:
        probs.append("first form must be (version 1)")
    for f in forms[1:]:
        if not isinstance(f, list) or not f or f[0] != "rule":
            probs.append(f"unexpected top-level form {f!r:.60}")
            continue
        name = f[1] if len(f) > 1 and isinstance(f[1], str) else "?"
        conds = sexpr.find_all(f, "condition")
        if len(conds) > 1:
            probs.append(f"rule {name}: {len(conds)} conditions (KiCad keeps only the last)")
        for c in conds:
            probs += [f"rule {name}: {p}" for p in _lint_condition(str(c[1]), netclasses)]
        seen = set()
        for c in sexpr.find_all(f, "constraint"):
            kind = str(c[1])
            if kind not in CONSTRAINTS:
                probs.append(f"rule {name}: unknown constraint {kind!r}")
            if kind in seen:
                probs.append(f"rule {name}: constraint {kind} appears twice")
            seen.add(kind)
            for v in c[2:]:
                if isinstance(v, list) and v and v[0] in ("min", "opt", "max") and len(v) > 1:
                    m = re.match(r"^-?[0-9.]+([a-z]*)$", str(v[1]))
                    unit = m.group(1) if m else None
                    if m is None:
                        probs.append(f"rule {name}: bad value {v[1]!r}")
                    elif unit in TIME_UNITS and kind not in ("length", "skew"):
                        probs.append(f"rule {name}: time unit {unit} only valid in length/skew")
                    elif unit and unit not in LENGTH_UNITS + TIME_UNITS + ("deg",):
                        probs.append(f"rule {name}: unit {unit!r} not accepted by KiCad 10")
        for x in f[2:]:
            if isinstance(x, list) and x and x[0] not in ("condition", "constraint", "layer", "severity"):
                probs.append(f"rule {name}: unknown clause {x[0]!r}")
    return probs


def _lint_condition(expr, netclasses):
    probs = []
    if expr.count("(") != expr.count(")"):
        probs.append("unbalanced parentheses in condition")
    for fn in re.findall(r"\b[AB]{1,2}\.([A-Za-z_]+)\s*\(", expr):
        if fn not in FUNCTIONS:
            probs.append(f"unknown function {fn}()")
    if netclasses is not None:
        for nc in re.findall(r"hasNetclass\('([^']*)'\)", expr):
            if nc not in netclasses:
                probs.append(f"net class {nc!r} does not exist")
    return probs
