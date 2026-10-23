# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Placement intent for the placer/router: pcb-intent/0.2 (docs/topics/architecture/constraint-ir.md)
plus the relation bundle the design authored, and relations inferred from the circuit."""
import re

from .. import yamlish
from ..placement import MAGNITUDES_MM
from .project import kicad_net_name

_GND = re.compile(r"^(GND|VSS|AGND|PGND|SGND|DGND|EP|PAD|VEE|0V|COM)", re.I)


def infer_relations(design, explicit):
    """Relations implied by the circuit: block groups, decoupling caps, external connectors."""
    d = design
    out = []
    grouped = {r["block"].name if hasattr(r.get("block"), "name") else r.get("block")
               for r in explicit if r["kind"] in ("group", "region")}
    for b in d.blocks:
        if b.name not in grouped and len(b.parts) > 1:
            out.append({"kind": "group", "block": f"block:{b.name}", "strength": "close", "source": "auto"})
    for b in d.blocks:
        for c in b.parts:
            if not c.defn.category.startswith("capacitor") or len(c.conn) != 2:
                continue
            nets = list(c.conn.values())
            gnd = [n for n in nets if n.kind == "ground" or _GND.match(n.name)]
            if len(gnd) != 1:
                continue
            rail = nets[0] if nets[1] is gnd[0] else nets[1]
            ics = [r for r in rail.pins if r.part.defn.category in ("ic", "module", "opto")
                   and r.pin.type in ("power_in", "power_out") and r.part.block is c.block]
            if len(ics) == 1:
                r = ics[0]
                out.append({"kind": "near", "a": c.ref, "b": f"{r.part.ref}.{r.pin.number}", "strength": "tight",
                            "source": "auto", "note": f"decoupling {rail.name}"})
    for p in d.all_parts():
        if p.defn.category == "connector" and any(n.external for n in p.conn.values()):
            if not any(r["kind"] == "edge" and r.get("obj") in (p, p.ref) for r in explicit):
                out.append({"kind": "edge", "obj": p.ref, "side": "any", "source": "auto",
                            "note": "carries external nets"})
    return out


def compile_relation(i, r, d):
    k = r["kind"]
    base = {"id": f"rel.{i}", "from": k}
    if k == "group":
        blk = r["block"].split(":", 1)[1] if isinstance(r["block"], str) else r["block"]
        members = [p.ref for b in d.blocks if b.name == blk for p in b.parts]
        return {**base, "kind": "cluster", "component_class": blk, "members": members,
                "max_span": MAGNITUDES_MM[r["strength"]] * 4, "hard": False}
    if k == "near":
        return {**base, "kind": "proximity", "a": r["a"], "b": r["b"], "max": MAGNITUDES_MM[r["strength"]],
                "basis": "pad_edge", "hard": r["strength"] == "tight"}
    if k == "far":
        return {**base, "kind": "separation", "a": r["a"], "b": r["b"], "min": MAGNITUDES_MM[r["strength"]] * 2,
                "hard": False}
    if k == "hot_loop":
        return {**base, "kind": "loop_area", "path": r["members"], "minimize": True, "same_layer": True,
                "hard": False}
    if k == "edge":
        return {**base, "kind": "edge_placement", "ref": r["obj"], "edge": r["side"],
                **({"overhang": r["overhang_mm"]} if r.get("overhang_mm") is not None else {})}
    if k == "separate":
        bar = next((b for b in d.barriers if {b.a, b.b} == {_dn(r["a"]), _dn(r["b"])}), None)
        out = {**base, "kind": "isolation", "domains": [_dn(r["a"]), _dn(r["b"])]}
        if bar:
            out.update({"grade": bar.grade, "clearance_mm": bar.clearance_mm, "creepage_mm": bar.creepage_mm,
                        "slot": bar.slot if r.get("slot") is None else r["slot"], "kicad_dru": f"IR:barrier.{bar.a}.{bar.b}"})
        return out
    return {**base, **{kk: vv for kk, vv in r.items() if kk not in ("note", "source")}, "kind": k}


def _dn(x):
    return x.split(":", 1)[1] if isinstance(x, str) and x.startswith("domain:") else x


def _refs_in(v):
    if isinstance(v, list):
        return [x for y in v for x in _refs_in(y)]
    if isinstance(v, str) and not v.startswith(("domain:", "block:", "net:")) and " " not in v:
        return [v.split(".", 1)[0]]
    return []


def intent_dict(design, netclasses, board=None):
    """Whole-design intent, or with `board` only that board's parts and the relations about them."""
    d = design.finalize()
    explicit = [{k: v for k, v in r.items() if v is not None} for r in d.place.resolve()]
    sig = {(r["kind"], r.get("a"), r.get("b"), r.get("obj"), r.get("block")) for r in explicit}
    auto = [r for r in infer_relations(d, d.place.relations)
            if (r["kind"], r.get("a"), r.get("b"), r.get("obj"), r.get("block")) not in sig]
    relations = [dict(r, source="design") for r in explicit] + auto
    parts = [p for p in d.all_parts() if board is None or p.block.board_name == board]
    if board is not None:
        mine = {p.ref for p in parts}
        others = {p.ref for p in d.all_parts()} - mine
        blocks = {f"block:{b.name}" for b in d.blocks if b.board_name == board}
        def about_board(r):
            refs = [x for k, v in r.items() if k not in ("note", "kind", "source", "strength", "side", "axis")
                    for x in _refs_in(v)]
            if any(x in others for x in refs):
                return False
            blk = r.get("block")
            return blk is None or blk in blocks
        relations = [r for r in relations if about_board(r)]
    compiled = [compile_relation(i + 1, r, d) for i, r in enumerate(relations)]
    comps = []
    for p in parts:
        doms = sorted({d.domain_of(n).name for n in p.conn.values() if d.domain_of(n)})
        c = {"ref": p.ref, "block": p.block.name, "board": p.block.board_name, "value": p.value,
             "footprint": p.defn.footprint,
             "category": p.defn.category, "domains": doms}
        if p.defn.mpn:
            c["mpn"] = p.defn.mpn
        if p.p_diss:
            c["p_diss_w"] = p.p_diss
        comps.append(c)
    doc = {
        "schema": "pcb-intent/0.2",
        "x-generator": "kaesynth 0.1",
        "design": {"slug": d.slug, "title": d.title, "revision": d.revision},
        "units": "mm",
        "board": (d.boards[board].as_dict() if board in d.boards else {}) if board else
                 (d.board_spec.as_dict() if d.board_spec else {}),
        "boards": [b.as_dict() for b in d.boards.values()],
        "magnitudes": dict(MAGNITUDES_MM),
        "domains": [{"name": x.name, "kind": x.kind, "ref": x.ref, "earthed": x.earthed,
                     **({"description": x.description} if x.description else {})} for x in d.domains.values()],
        "barriers": [{k: v for k, v in b.__dict__.items() if v not in (None, "")} for b in d.barriers],
        "netclasses": [{"name": c["name"], "domain": c["domain"], "clearance": c["clearance"],
                        "track_width": c["track_width"], "nets": sorted(kicad_net_name(n) for n in c["nets"])}
                       for c in sorted(netclasses.classes.values(), key=lambda c: c["name"])],
        "components": comps,
        "relations": relations,
        "constraints": compiled,
    }
    return doc


def intent_yaml(design, netclasses, board=None):
    head = ("# Placement intent generated by kaesynth from the design's relations (source: design)\n"
            "# and from the circuit (source: auto). Magnitudes are ordinal; `magnitudes` gives the\n"
            "# solver-side defaults. Spacing between domains comes from `barriers`.\n")
    return head + yamlish.dump(intent_dict(design, netclasses, board)) + "\n"
