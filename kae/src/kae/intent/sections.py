# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Board sections: the brief's structures (commutation cells, decaps, victims, crystals, chains, heat
sources, ...) as named groups of parts and nets, which the intent accepts, renames, merges, drops or adds
to. An observation belongs to a section on its source side ('from') or its observer side ('to') when they
share a part, a net or the structure itself."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Section:
    id: str
    kind: str
    parts: set = field(default_factory=set)
    nets: set = field(default_factory=set)
    structures: set = field(default_factory=set)     # brief structure ids it was made from
    origin: str = "brief"                            # brief | intent


NET_FIELDS = ("nets", "net", "rail", "sw")       # not "ground": every section would share it


def from_brief(brief):
    """{id: Section} for every structure of the brief, with its parts as references."""
    from kae.circuit.brief import GROUP_FIELDS, KEYED_FIELDS, PAIR_FIELDS, REF_FIELDS
    ref = {u: p["ref"] for u, p in brief["parts"].items()}
    out = {}
    for st in brief.get("structures") or []:
        parts = set()
        for k, v in st.items():
            if k in REF_FIELDS:
                for u in (v if isinstance(v, list) else [v]):
                    if isinstance(u, str) and u in ref:
                        parts.add(ref[u])
            elif k in PAIR_FIELDS and isinstance(v, list):
                for x in v:
                    if isinstance(x, (list, tuple)) and x and x[0] in ref:
                        parts.add(ref[x[0]])
            elif k in GROUP_FIELDS and isinstance(v, list):
                parts |= {ref[u] for g in v for u in (g if isinstance(g, list) else [g]) if u in ref}
            elif k in KEYED_FIELDS and isinstance(v, dict):
                parts |= {ref[u] for u in v if u in ref}
        nets = set()
        for k in NET_FIELDS:
            v = st.get(k)
            nets |= {n for n in (v if isinstance(v, list) else [v]) if isinstance(n, str)}
        out[st["id"]] = Section(st["id"], st.get("kind", ""), parts, nets, {st["id"]})
    return out


class SectionError(ValueError):
    pass


def apply(sections, spec):
    """The intent's edits: {"accept": "all" | [ids], "drop": [ids], "rename": {old: new},
    "add": [{"id", "parts", "nets", "merge": [ids]}]}. Returns {id: Section}; unknown ids are errors that
    name the ids that exist."""
    spec = spec or {}
    secs = dict(sections)
    acc = spec.get("accept", "all")
    if acc != "all":
        bad = [i for i in acc if i not in secs]
        if bad:
            raise SectionError(f"sections.accept: unknown {bad}; this board's sections: {sorted(secs)[:40]}")
        secs = {i: secs[i] for i in acc}
    for i in spec.get("drop", []):
        if i not in secs:
            raise SectionError(f"sections.drop: unknown '{i}'")
        del secs[i]
    for old, new in (spec.get("rename") or {}).items():
        if old not in secs:
            raise SectionError(f"sections.rename: unknown '{old}'; this board's sections: {sorted(secs)[:40]}")
        s = secs.pop(old)
        s.id = new
        secs[new] = s
    for a in spec.get("add", []):
        sid = a.get("id")
        if not sid:
            raise SectionError("sections.add: every added section needs an 'id'")
        s = Section(sid, a.get("kind", "intent"), set(a.get("parts", [])), set(a.get("nets", [])), set(), "intent")
        for m in a.get("merge", []):
            if m not in sections and m not in secs:
                raise SectionError(f"sections.add '{sid}': merge of unknown '{m}'")
            src = secs.get(m) or sections[m]
            s.parts |= src.parts
            s.nets |= src.nets
            s.structures |= src.structures
        secs[sid] = s
    return secs


def side(sec, scope, which):
    """Does the observation's 'from' (source) or 'to' (observer) side touch the section?"""
    if which == "from":
        parts, nets, st = scope.get("from_parts", []), scope.get("from_nets", []), scope.get("from_struct")
    else:
        parts, nets, st = scope.get("to_parts", []) + scope.get("parts", []), \
            scope.get("to_nets", []) + scope.get("nets", []), None
    return bool(sec.parts & set(parts) or sec.nets & set(nets) or (st and st in sec.structures))
