# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""KiCad project files: .kicad_pro (net classes and patterns), lib tables, .kicad_dru."""
import json
import math

from ..checks import Checker
from ..ir import GRADES

# IPC-2221B Table 6-1, minimum conductor spacing (mm). Columns: B1 internal, B2 external
# uncoated <=3050 m, B4 external with permanent polymer coating, A6 external component lead
# uncoated. Rows: upper bound of peak/DC voltage between conductors. Above 500 V: mm per volt.
# B4/A6 >500 V use the corrected 0.00305 mm/V (docs/topics/rules/isolation-creepage.md).
IPC2221B = [
    (15, {"B1": 0.05, "B2": 0.1, "B4": 0.05, "A6": 0.13}),
    (30, {"B1": 0.05, "B2": 0.1, "B4": 0.05, "A6": 0.25}),
    (50, {"B1": 0.1, "B2": 0.6, "B4": 0.13, "A6": 0.4}),
    (100, {"B1": 0.1, "B2": 0.6, "B4": 0.13, "A6": 0.5}),
    (150, {"B1": 0.2, "B2": 0.6, "B4": 0.4, "A6": 0.8}),
    (170, {"B1": 0.2, "B2": 1.25, "B4": 0.4, "A6": 0.8}),
    (250, {"B1": 0.2, "B2": 1.25, "B4": 0.4, "A6": 0.8}),
    (300, {"B1": 0.2, "B2": 1.25, "B4": 0.4, "A6": 0.8}),
    (500, {"B1": 0.25, "B2": 2.5, "B4": 0.8, "A6": 1.5}),
]
IPC2221B_PER_V = {"B1": 0.0025, "B2": 0.005, "B4": 0.00305, "A6": 0.00305}


def ipc2221b_spacing(volts, column="B2"):
    v = abs(volts)
    for vmax, row in IPC2221B:
        if v <= vmax:
            return row[column]
    return round(IPC2221B_PER_V[column] * v, 3)


def ipc2221_width_mm(amps, rise_c=10.0, oz=1.0, external=True):
    """IPC-2221 trace width for a current and temperature rise (conservative vs IPC-2152)."""
    if not amps:
        return None
    k = 0.048 if external else 0.024
    area_mil2 = (amps / (k * rise_c ** 0.44)) ** (1 / 0.725)
    width_mil = area_mil2 / (1.378 * oz)
    return round(math.ceil(width_mil * 0.0254 / 0.05) * 0.05, 2)


class NetClasses:
    """Derive one net class per (domain, current bucket); clearance from in-domain voltage."""

    def __init__(self, design, checker=None):
        self.d = design
        self.ck = checker or Checker(design)
        self.classes = {}       # name -> dict
        self.assign = {}        # net full kicad name -> class

    def build(self):
        d = self.d
        nets = [n for n in d.all_nets() if n.pins]
        # worst voltage from each net to any other net in the same root domain
        worst = {}
        by_root = {}
        for n in nets:
            rt = self.ck.root(n)
            by_root.setdefault(rt.name if rt else None, []).append(n)
        for root, group in by_root.items():
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    r = self.ck.vdiff(a, b)
                    if r is None:
                        continue
                    m = max(abs(r[0]), abs(r[1]))
                    worst[a] = max(worst.get(a, 0), m)
                    worst[b] = max(worst.get(b, 0), m)
        coated = bool(d.board_spec and d.board_spec.coating)
        col = "B4" if coated else "B2"
        oz = d.board_spec.copper_oz if d.board_spec else 1.0
        for n in nets:
            dom = d.domain_of(n)
            base = n.netclass or (dom.name if dom else "Default")
            cls = base
            width = ipc2221_width_mm(n.i_max, oz=oz) if n.i_max and n.i_max >= 0.5 else None
            if width and not n.netclass:
                cls = f"{base}_{_bucket(n.i_max)}A"
                width = ipc2221_width_mm(_bucket(n.i_max), oz=oz)
            clr = max(0.2, ipc2221b_spacing(worst.get(n, 0), col))
            c = self.classes.setdefault(cls, {"name": cls, "clearance": 0.2, "track_width": 0.25,
                                              "domain": dom.name if dom else None, "nets": []})
            c["clearance"] = max(c["clearance"], clr)
            if width:
                c["track_width"] = max(c["track_width"], width)
            c["nets"].append(n)
            self.assign[kicad_net_name(n)] = cls
        return self

    def project_json(self, template):
        pro = json.loads(json.dumps(template))
        ns = pro.setdefault("net_settings", {})
        classes = [{"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.6,
                    "via_drill": 0.3, "priority": 2147483647}]
        for i, c in enumerate(sorted(self.classes.values(), key=lambda c: c["name"])):
            if c["name"] == "Default":
                classes[0]["clearance"] = c["clearance"]
                continue
            classes.append({"name": c["name"], "clearance": c["clearance"], "track_width": c["track_width"],
                            "via_diameter": max(0.6, round(c["track_width"] * 0.8 + 0.3, 2)),
                            "via_drill": max(0.3, round(c["track_width"] * 0.4, 2)), "priority": i})
        ns["classes"] = classes
        ns["meta"] = {"version": 4}
        ns["netclass_patterns"] = [{"netclass": cls, "pattern": name}
                                   for name, cls in sorted(self.assign.items())]
        return pro


def _bucket(i):
    for b in (1, 2, 3, 5, 8, 10, 15, 20, 30, 40, 50, 75, 100):
        if i <= b:
            return b
    return int(math.ceil(i / 50.0) * 50)


def kicad_net_name(net):
    return net.name if net.is_global else f"/{net.block.name}/{net.name}"


def write_project(outdir, design, symtable, netclasses, slug=None, parts=None):
    slug = slug or design.slug
    parts = design.all_parts() if parts is None else parts
    template = {
        "board": {"design_settings": {"defaults": {}, "diff_pair_dimensions": [], "drc_exclusions": [],
                                      "rules": {}, "track_widths": [], "via_dimensions": []}},
        "boards": [],
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{slug}.kicad_pro", "version": 3},
        "net_settings": {},
        "pcbnew": {"page_layout_descr_file": ""},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [], "text_variables": {},
    }
    pro = netclasses.project_json(template)
    (outdir / f"{slug}.kicad_pro").write_text(json.dumps(pro, indent=2) + "\n")
    libs = sorted(symtable.used_libs)
    sym_rows = [f'  (lib (name "{lib}")(type "KiCad")(uri "${{KICAD10_SYMBOL_DIR}}/{lib}.kicad_sym")(options "")(descr ""))'
                for lib in libs]
    sym_rows.append('  (lib (name "kaesynth")(type "KiCad")(uri "${KIPRJMOD}/kaesynth.kicad_sym")(options "")(descr "generated by kaesynth"))')
    (outdir / "sym-lib-table").write_text("(sym_lib_table\n  (version 7)\n" + "\n".join(sym_rows) + "\n)\n")
    fps = sorted({p.defn.footprint.split(":", 1)[0] for p in parts
                  if p.defn.footprint and ":" in p.defn.footprint and not p.defn.footprint.startswith("custom:")})
    fp_rows = [f'  (lib (name "{lib}")(type "KiCad")(uri "${{KICAD10_FOOTPRINT_DIR}}/{lib}.pretty")(options "")(descr ""))'
               for lib in fps]
    (outdir / "fp-lib-table").write_text("(fp_lib_table\n  (version 7)\n" + "\n".join(fp_rows) + "\n)\n")


def dru_text(design, netclasses):
    """Custom DRC rules: barrier clearance/creepage between domain net classes."""
    lines = ["(version 1)", ""]
    by_domain = {}
    for c in netclasses.classes.values():
        by_domain.setdefault(c["domain"], []).append(c["name"])
    parent = {}
    for dom in design.domains.values():
        try:
            pd = design.domain_of(design.net_by_name(dom.ref))
        except Exception:
            pd = None
        parent[dom.name] = pd.name if pd is not None and pd is not dom else None

    def subtree(dom):
        """A domain and every domain floating on top of it."""
        out = set()
        for name in design.domains:
            x = name
            while x is not None:
                if x == dom:
                    out.add(name)
                    break
                x = parent.get(x)
        return out

    def classes(doms, side):
        names = sorted(n for d in doms for n in by_domain.get(d, []))
        if not names:
            return None
        return "(" + " || ".join(f"{side}.hasNetclass('{n}')" for n in names) + ")"

    def sides(bar):
        """Domains on each side. A barrier covers the domains floating on each side too,
        except those on the other side (a parent/child barrier must not apply inside the child)."""
        sa, sb = subtree(bar.a), subtree(bar.b)
        if bar.b in sa:
            return sa - sb, sb
        if bar.a in sb:
            return sa, sb - sa
        return sa, sb

    # KiCad applies the last matching rule. Rules inherited through floating domains come
    # first, rules naming the nets' own domains last, so a direct pair always wins.
    emitted = []
    for direct in (False, True):
        for bar in sorted(design.barriers, key=lambda b: GRADES[b.grade]):
            sa, sb = ({bar.a}, {bar.b}) if direct else sides(bar)
            if not direct and (sa, sb) == ({bar.a}, {bar.b}):
                continue          # nothing inherited: the direct rule covers it
            ca, cb, ca2, cb2 = classes(sa, "A"), classes(sb, "B"), classes(sb, "A"), classes(sa, "B")
            if not (ca and cb):
                continue
            rid = f"IR:barrier.{bar.a}.{bar.b}" + ("" if direct else ".inherited")
            emitted.append(rid)
            lines.append(f"# {bar.grade} insulation, {bar.v_work:g} V working, {bar.standard} {bar.source}".rstrip())
            lines.append(f'(rule "{rid}"')
            lines.append(f'  (condition "({ca} && {cb}) || ({ca2} && {cb2})")')
            lines.append(f"  (constraint clearance (min {bar.clearance_mm:g}mm))")
            lines.append(f"  (constraint creepage (min {bar.creepage_mm:g}mm)))")
            lines.append("")
    return "\n".join(lines)
