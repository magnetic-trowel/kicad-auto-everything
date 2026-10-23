# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""IR netlist as JSON, and a comparison against the netlist KiCad exports from the schematic."""
import xml.etree.ElementTree as ET

from .project import kicad_net_name


def ir_netlist(design):
    d = design.finalize()
    parts = []
    for p in d.all_parts():
        parts.append({"ref": p.ref, "block": p.block.name, "name": p.name, "value": p.value,
                      "mpn": p.defn.mpn, "manufacturer": p.defn.manufacturer,
                      "footprint": p.defn.footprint, "category": p.defn.category,
                      "dnp": p.dnp, "p_diss": p.p_diss,
                      "pins": {x.number: {"name": x.name, "type": x.type,
                                          "net": kicad_net_name(p.conn[x.number]) if x.number in p.conn else None,
                                          "nc": x.number in p.nc} for x in p.pins}})
    nets = []
    for n in d.all_nets():
        if not n.pins:
            continue
        dom = d.domain_of(n)
        nets.append({"name": kicad_net_name(n), "domain": dom.name if dom else None,
                     "v": list(n.v) if n.v else None, "kind": n.kind, "i_max": n.i_max,
                     "external": n.external,
                     "nodes": sorted([[r.part.ref, r.pin.number] for r in n.pins])})
    return {"design": d.slug, "parts": parts, "nets": nets}


def parse_kicad_xml(path):
    root = ET.parse(path).getroot()
    nets = {}
    for net in root.iter("net"):
        nodes = {(n.get("ref"), n.get("pin")) for n in net.iter("node")}
        nets[net.get("name")] = {"nodes": nodes, "class": net.get("class")}
    comps = {c.get("ref"): c for c in root.iter("comp")}
    return nets, comps


def compare(design, xml_path):
    """Mismatches between IR connectivity and KiCad's exported netlist (empty list = identical)."""
    kn, comps = parse_kicad_xml(xml_path)
    problems = []
    # drop pseudo parts (#FLG, #PWR) and KiCad's single-node 'unconnected-' nets for NC pins
    knets = {}
    for name, v in kn.items():
        nodes = {x for x in v["nodes"] if not x[0].startswith("#")}
        if not nodes:
            continue
        knets[name] = nodes
    by_node = {}
    for name, nodes in knets.items():
        for x in nodes:
            by_node[x] = name
    for n in design.all_nets():
        if not n.pins:
            continue
        want = {(r.part.ref, r.pin.number) for r in n.pins}
        got_names = {by_node.get(x) for x in want}
        if None in got_names:
            missing = sorted(x for x in want if x not in by_node)
            problems.append(f"net {kicad_net_name(n)}: pins {missing} missing from KiCad netlist")
            continue
        if len(got_names) > 1:
            problems.append(f"net {kicad_net_name(n)} is split in KiCad into {sorted(got_names)}")
            continue
        kname = got_names.pop()
        if knets[kname] != want:
            extra = sorted(knets[kname] - want)
            problems.append(f"net {kicad_net_name(n)}: KiCad net {kname} also contains {extra}")
        elif kname != kicad_net_name(n):
            problems.append(f"net {kicad_net_name(n)} is named {kname} in KiCad")
    ir_refs = {p.ref for p in design.all_parts()}
    k_refs = {r for r in comps if not r.startswith("#")}
    if ir_refs - k_refs:
        problems.append(f"parts missing from KiCad netlist: {sorted(ir_refs - k_refs)}")
    if k_refs - ir_refs:
        problems.append(f"unexpected parts in KiCad netlist: {sorted(k_refs - ir_refs)}")
    for p in design.all_parts():
        c = comps.get(p.ref)
        if c is None:
            continue
        fp = c.findtext("footprint") or ""
        if (p.defn.footprint or "") != fp:
            problems.append(f"{p.ref}: footprint {fp!r} in KiCad vs {p.defn.footprint!r} in IR")
    return problems


def netclass_mismatches(xml_path, netclasses):
    kn, _ = parse_kicad_xml(xml_path)
    out = []
    for name, cls in netclasses.assign.items():
        k = kn.get(name)
        if k and k["class"] != cls and cls not in (k["class"] or "").split(","):
            out.append(f"net {name}: class {k['class']!r} in KiCad, expected {cls!r}")
    return out
