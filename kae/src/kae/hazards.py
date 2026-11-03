# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hazards: what in a board kae hands back would not work, could not be built, or is risky.

The rule this module serves: kae never hands back a board that electrically would not work
without saying so, and anything that makes manufacture or use problematic is flagged to the
commanding LLM. Every JSON report the LLM reads (kae place, kae.route.cli, critical_cli,
kae.joint.cli, kae brief, the physics evaluators) ends with

    "hazards": [entry, ...],            # most severe first, capped (see finalize)
    "hazard_summary": {"block": n, "warn": n, "info": n, "blocked": bool, "shown": n,
                       "total": n, "omitted": {code: n}, "objects_truncated": n}

An entry (docs/topics/kicad/mcp-tool-surface-spec.md, "Hazards"):

    {"code": "short_check_ignored",          # stable snake_case id
     "severity": "block" | "warn" | "info",  # block: the board would not work, or cannot be built as-is
     "category": "electrical" | "manufacturing" | "assembly" | "thermal" | "safety" | "data",
     "message": "one plain sentence the LLM can act on",
     "objects": ["U3", "+5V"],               # refs, nets, rules, layers
     "evidence": {...},                      # numbers: measured, limit, source of the limit
     "fix": "the concrete relaxation or action"}

Code that relaxes, skips, caps, assumes or ignores something that matters appends an entry to
the report it already produces (`add(rep, make(...))`, or a plain dict in this schema);
`finalize(rep)` at the CLI hoists nested sub-reports' lists to the top, dedupes, sorts, caps,
and writes the summary. Plain dicts, no classes: reports are JSON.
"""
from __future__ import annotations

SEVERITIES = ("block", "warn", "info")
CATEGORIES = ("electrical", "manufacturing", "assembly", "thermal", "safety", "data")
_RANK = {s: i for i, s in enumerate(SEVERITIES)}

MAX_ENTRIES = 40          # entries shown; the rest are counted per code in hazard_summary.omitted
MAX_PER_CODE = 8          # entries of one code shown (one cause on 300 nets is one finding)
MAX_OBJECTS = 12          # objects per entry; the rest counted in the entry's objects_more
MAX_MESSAGE = 300         # characters of message and fix
MAX_EVIDENCE = 12         # evidence keys per entry
MAX_DEPTH = 6             # how deep collect() looks for nested "hazards" lists


def make(code, severity, category, message, objects=(), evidence=None, fix=None, **extra):
    """One hazard entry. Unknown severities or categories raise: a typo must not hide a block."""
    if severity not in _RANK:
        raise ValueError(f"hazard {code}: severity {severity!r} not in {SEVERITIES}")
    if category not in CATEGORIES:
        raise ValueError(f"hazard {code}: category {category!r} not in {CATEGORIES}")
    h = dict(code=str(code), severity=severity, category=category, message=str(message),
             objects=[str(o) for o in (objects or ()) if o is not None and o != ""])
    if evidence:
        h["evidence"] = dict(evidence)
    if fix:
        h["fix"] = str(fix)
    h.update({k: v for k, v in extra.items() if v is not None})
    return h


def add(report, *entries):
    """Append entries to report["hazards"] (created when missing); returns the report."""
    lst = report.setdefault("hazards", [])
    lst.extend(e for e in entries if e)
    return report


def normalize(h):
    """A well-formed copy of a (possibly hand-written) entry, or None when it is not one.
    Unknown severity reads as warn (never silently dropped), unknown category as data."""
    if not isinstance(h, dict) or not h.get("code"):
        return None
    out = dict(h)
    out["code"] = str(out["code"])
    if out.get("severity") not in _RANK:
        out["evidence"] = dict(out.get("evidence") or {}, severity_given=out.get("severity"))
        out["severity"] = "warn"
    if out.get("category") not in CATEGORIES:
        out["category"] = "data"
    out["message"] = str(out.get("message") or out["code"])
    obj = out.get("objects") or []
    if isinstance(obj, (str, bytes)):
        obj = [obj]
    out["objects"] = [str(o) for o in obj if o is not None and o != ""]
    return out


def _key(h):
    return (h["code"], tuple(sorted(h.get("objects") or ())))


def dedupe(entries):
    """One entry per (code, objects): the most severe one, with the sources that reported it.
    Order of first appearance is kept (sort afterwards)."""
    seen = {}
    for h in entries:
        h = normalize(h)
        if h is None:
            continue
        k = _key(h)
        if k not in seen:
            seen[k] = h
            continue
        old = seen[k]
        if _RANK[h["severity"]] < _RANK[old["severity"]]:
            h["sources"] = _merge_sources(h, old)
            seen[k] = h
        else:
            old["sources"] = _merge_sources(old, h)
    for h in seen.values():
        if h.get("sources") and len(h["sources"]) < 2:
            h.pop("sources")
    return list(seen.values())


def _merge_sources(a, b):
    out = []
    for h in (a, b):
        for s in h.get("sources") or ([h["source"]] if h.get("source") else []):
            if s not in out:
                out.append(s)
    return out


def sort(entries):
    """Most severe first; within a severity block-relevant categories first, then by code."""
    cat = {c: i for i, c in enumerate(CATEGORIES)}
    return sorted(entries, key=lambda h: (_RANK.get(h.get("severity"), 1), cat.get(h.get("category"), 99),
                                          h.get("code", ""), tuple(h.get("objects") or ())))


def merge(*lists):
    """Several hazard lists as one: deduped and sorted."""
    return sort(dedupe([h for lst in lists for h in (lst or [])]))


def collect(report, hoist=True):
    """Every entry of report["hazards"] and of the "hazards" lists nested in its sub-reports
    (critical, bridge, portfolio, place, joint iterations, physics ...), each tagged with the
    path it came from ("source"). With hoist, nested lists are removed (they are reported once,
    at the top)."""
    out = []

    def walk(node, path, depth):
        if depth > MAX_DEPTH:
            return
        if isinstance(node, dict):
            lst = node.get("hazards")
            if isinstance(lst, list) and node is not report:
                for h in lst:
                    if isinstance(h, dict):
                        out.append(dict(h, source=h.get("source") or path or "report"))
                if hoist:
                    node.pop("hazards", None)
                    node.pop("hazard_summary", None)
            for k, v in list(node.items()):
                if k in ("hazards", "hazard_summary"):
                    continue
                if isinstance(v, (dict, list)):
                    walk(v, f"{path}.{k}" if path else str(k), depth + 1)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                if isinstance(v, (dict, list)):
                    walk(v, f"{path}[{i}]", depth + 1)
    top = [h for h in (report.get("hazards") or []) if isinstance(h, dict)]
    walk(report, "", 0)
    return top + out


def _compact(h):
    h = dict(h)
    for k in ("message", "fix"):
        if isinstance(h.get(k), str) and len(h[k]) > MAX_MESSAGE:
            h[k] = h[k][:MAX_MESSAGE - 3] + "..."
    obj = h.get("objects") or []
    if len(obj) > MAX_OBJECTS:
        h["objects"] = obj[:MAX_OBJECTS]
        h["objects_more"] = len(obj) - MAX_OBJECTS
    ev = h.get("evidence")
    if isinstance(ev, dict) and len(ev) > MAX_EVIDENCE:
        keys = list(ev)[:MAX_EVIDENCE]
        h["evidence"] = {k: ev[k] for k in keys}
        h["evidence"]["keys_more"] = len(ev) - MAX_EVIDENCE
    return h


def cap(entries, max_entries=MAX_ENTRIES, max_per_code=MAX_PER_CODE):
    """(shown, omitted {code: n}): sorted entries, at most max_per_code per code and
    max_entries in all. Block entries are never omitted for warn or info ones: sorting puts
    them first, and every block entry is kept even past max_entries."""
    shown, omitted, per = [], {}, {}
    for h in sort(entries):
        n = per.get(h["code"], 0)
        over = n >= max_per_code or len(shown) >= max_entries
        if over and not (h["severity"] == "block" and n < max_per_code):
            omitted[h["code"]] = omitted.get(h["code"], 0) + 1
            continue
        per[h["code"]] = n + 1
        shown.append(_compact(h))
    return shown, omitted


def summary(entries, shown=None, omitted=None):
    """Counts by severity over all entries (shown or not), and whether the board is blocked."""
    c = {s: 0 for s in SEVERITIES}
    for h in entries:
        c[h["severity"]] = c.get(h["severity"], 0) + 1
    out = dict(c, blocked=c["block"] > 0, total=len(entries))
    if shown is not None:
        out["shown"] = len(shown)
        if omitted:
            out["omitted"] = dict(sorted(omitted.items()))
        tr = sum(h.get("objects_more", 0) for h in shown)
        if tr:
            out["objects_truncated"] = tr
    codes = {}
    for h in entries:
        if h["severity"] == "block":
            codes[h["code"]] = codes.get(h["code"], 0) + 1
    if codes:
        out["block_codes"] = dict(sorted(codes.items()))
    return out


def finalize(report, extra=(), derive_flags=True):
    """Make `report` end with "hazards" and "hazard_summary": nested lists hoisted, entries
    derived from the flags kae already writes (derive), `extra` added, deduped, sorted,
    capped. Keys are re-inserted last so they close the JSON. Returns the report."""
    if not isinstance(report, dict):
        return report
    entries = collect(report)
    if derive_flags:
        entries += derive(report)
    entries += list(extra or ())
    entries = dedupe(entries)
    shown, omitted = cap(entries)
    report.pop("hazards", None)
    report.pop("hazard_summary", None)
    report["hazards"] = shown
    report["hazard_summary"] = summary(entries, shown, omitted)
    return report


# ---- flags kae already writes, as hazards ------------------------------------------------

def _walk_dicts(node, depth=0):
    if depth > MAX_DEPTH + 2:
        return
    if isinstance(node, dict):
        yield node
        for k, v in node.items():
            if k in ("hazards", "hazard_summary"):
                continue
            if isinstance(v, (dict, list)):
                yield from _walk_dicts(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            if isinstance(v, (dict, list)):
                yield from _walk_dicts(v, depth + 1)


def derive(report):
    """Hazards from the risk signals kae's stages already put in their reports (module flags,
    dru_rejected, relaxed bodies, BGA escape certificates, unchecked joint steps). Deduped by
    finalize, so the same flag seen in several iterations is one entry."""
    out = []
    for d in _walk_dicts(report):
        f = d.get("flag")
        if f in _FLAG_HAZARDS:
            out.append(_FLAG_HAZARDS[f](d))
        if d.get("dru_rejected"):
            out.append(make("dru_rejected", "warn", "data",
                            "KiCad drops the board's .kicad_dru custom rules file, so none of its rules "
                            "were applied or checked.", objects=[".kicad_dru"],
                            evidence=dict(reason=str(d["dru_rejected"])[:200]),
                            fix="Fix the rules file (kae dru-check names the error) and run again."))
        relaxed = d.get("bodies_relaxed")
        if d.get("step") == "bodies relaxed":
            relaxed = d.get("relaxed") or ["(escalation)"]
        if relaxed:
            refs = relaxed if isinstance(relaxed, list) else []
            out.append(make("bodies_relaxed", "warn", "assembly",
                            "The board was too full to keep part bodies apart: through-hole parts without a "
                            "courtyard were placed by their pads only, so their bodies may overlap other parts.",
                            objects=refs, evidence=dict(parts=len(refs), rule="place/problem.py relax_bodies"),
                            fix="Add courtyards to those footprints, enlarge the board, or check body "
                                "clearance in 3D before ordering."))
    return out


def _flag_rail_max_cap(d):
    return make("rail_max_cap", "warn", "thermal",
                f"Rail {d.get('net')} needs a {d.get('ipc_mm')} mm track for {d.get('I_A')} A (IPC-2221) but its "
                "net class caps the width lower, so the track runs hotter than the rise target.",
                objects=[d.get("net")], evidence={k: d[k] for k in ("hop", "I_A", "ipc_mm", "max_mm") if k in d},
                fix="Raise the net class's maximum track width, add a pour, or accept the extra temperature rise.")


def _flag_class_max_below_ipc(d):
    return make("class_max_below_ipc", "warn", "thermal",
                f"Net {d.get('net')}'s class maximum width {d.get('max_mm')} mm is below the IPC-2221 width "
                f"{d.get('ipc_mm')} mm for its current.", objects=[d.get("net")],
                evidence={k: d[k] for k in ("hop", "ipc_mm", "max_mm") if k in d},
                fix="Raise the class maximum width or feed the rail with a pour.")


def _flag_ipc_floor_unroutable(d):
    return make("ipc_floor_unroutable", "warn", "thermal",
                f"Rail {d.get('net')} could not be routed at the IPC-2221 width for {d.get('I_A')} A; the hop "
                "was left to narrower routing.", objects=[d.get("net")],
                evidence={k: d[k] for k in d if k not in ("flag", "net")},
                fix="Make room for a wider track or a pour on this rail, or confirm the current is lower.")


_FLAG_HAZARDS = dict(rail_max_cap=_flag_rail_max_cap, class_max_below_ipc=_flag_class_max_below_ipc,
                     ipc_floor_unroutable=_flag_ipc_floor_unroutable)
