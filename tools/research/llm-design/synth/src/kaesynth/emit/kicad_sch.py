# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write a hierarchical KiCad 10 schematic: a root sheet plus one sheet per block.

Connectivity is carried by labels on short pin stubs: local labels for block nets, global
labels for design nets. That keeps generated sheets readable without wire routing, and makes
the KiCad netlist export an exact check of the IR (see netlist.compare).
"""
import datetime
import math
import uuid as _uuid

from .. import sexpr
from ..sexpr import S, Sym
from .symbols import CHAR_W, GRID, SymbolTable, font, prop

SCH_VERSION = 20260306
PAPERS = [("A4", 297, 210), ("A3", 420, 297), ("A2", 594, 420), ("A1", 841, 594), ("A0", 1189, 841)]
MARGIN = 25.4
TITLE_BLOCK_H = 40.0
STUB = GRID
GAP = 7.62


def snap(v, g=GRID):
    return round(round(v / g) * g, 4)


class Uuids:
    def __init__(self, slug):
        self.ns = _uuid.uuid5(_uuid.NAMESPACE_URL, f"kaesynth:{slug}")

    def __call__(self, *key):
        return str(_uuid.uuid5(self.ns, "/".join(map(str, key))))


def _rot(dx, dy, ang):
    """Rotate a library-coordinate vector by `ang` degrees (counterclockwise, Y up)."""
    a = math.radians(ang)
    return dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)


class Item:
    """One placed symbol unit with its pins in schematic coordinates relative to the origin."""

    def __init__(self, part, unit, lib_id, sym, refdes, value, pins_override=None):
        self.part = part
        self.unit = unit
        self.lib_id = lib_id
        self.sym = sym
        self.ref = refdes
        self.value = value
        x0, y0, x1, y1 = sym.bbox(unit)
        # schematic Y grows downward: flip library Y
        self.body = (x0, -y1, x1, -y0)
        self.pins = []
        for p in (pins_override or sym.pins_of(unit)):
            ox, oy = _rot(1.0, 0.0, p.angle + 180)      # outward direction, library coords
            self.pins.append((p, p.x, -p.y, round(ox), round(-oy)))
        self.x = self.y = 0.0
        self.labels = []          # filled by the sheet: (pin, text, is_global, nc)
        self.extent = self.body

    def measure(self, label_text):
        x0, y0, x1, y1 = self.body
        for p, px, py, ox, oy in self.pins:
            text = label_text(self, p)
            if text is None:
                continue
            ln = STUB + len(text) * CHAR_W + 3.5
            ex, ey = px + ox * ln, py + oy * ln
            x0, x1 = min(x0, ex, px), max(x1, ex, px)
            y0, y1 = min(y0, ey - 1.5, py), max(y1, ey + 1.5, py)
        # room for reference/value text around the body
        self.extent = (x0 - 2.54, y0 - 3.81, x1 + 2.54, y1 + 3.81)

    @property
    def width(self):
        return self.extent[2] - self.extent[0]

    @property
    def height(self):
        return self.extent[3] - self.extent[1]


class _Group:
    """An anchor part and the small parts clustered under it, laid out as a unit."""

    def __init__(self, members):
        self.members = members
        self.offsets = []
        self.width = self.height = 0.0

    def arrange(self):
        head, rest = self.members[0], self.members[1:]
        row_w = max(head.width, min(len(rest), 4) * 25.0)
        self.offsets = [(0.0, 0.0)]
        x, y, rh = 0.0, head.height + GAP / 2, 0.0
        w = head.width
        for it in rest:
            if x > 0 and x + it.width > row_w:
                x, y, rh = 0.0, y + rh + GAP / 2, 0.0
            self.offsets.append((x, y))
            x += it.width + GAP / 2
            rh = max(rh, it.height)
            w = max(w, x)
        self.width = w
        self.height = (y + rh) if rest else head.height

    def place(self, x, y):
        for it, (dx, dy) in zip(self.members, self.offsets):
            it.x = snap(x + dx - it.extent[0])
            it.y = snap(y + dy - it.extent[1])


class SchematicWriter:
    def __init__(self, design, symlibs, title_date=None, blocks=None, slug=None, board=None):
        """Write `blocks` (default: all) as project `slug`; `board` names the board for notes."""
        self.d = design
        self.blocks = list(blocks if blocks is not None else design.blocks)
        self.slug = slug or design.slug
        self.board = board
        self.st = SymbolTable(symlibs)
        self.u = Uuids(self.slug)
        self.root_uuid = self.u("root")
        self.date = title_date or datetime.date.today().isoformat()
        self.flags = {}           # net -> list of PWR_FLAG refs
        self.flag_count = 0

    # -- public ---------------------------------------------------------------------------------
    def write(self, outdir):
        d = self.d.finalize()
        outdir.mkdir(parents=True, exist_ok=True)
        files = {}
        flag_nets = self._nets_needing_flag()
        sheet_of_flag = {}
        mine = set(id(b) for b in self.blocks)
        for n in flag_nets:
            first = next(r.part.block for r in n.pins if id(r.part.block) in mine)
            sheet_of_flag.setdefault(first.name, []).append(n)
        for i, b in enumerate(self.blocks):
            text = self._sheet(b, page=i + 2, flag_nets=sheet_of_flag.get(b.name, []))
            files[f"{b.name}.kicad_sch"] = text
        files[f"{self.slug}.kicad_sch"] = self._root()
        for name, text in files.items():
            (outdir / name).write_text(text)
        (outdir / "kaesynth.kicad_sym").write_text(self.st.project_library())
        return files

    # -- helpers --------------------------------------------------------------------------------
    def _nets_needing_flag(self):
        out = []
        mine = set(id(b) for b in self.blocks)
        for n in self.d.all_nets():
            pins = [r for r in n.pins if id(r.part.block) in mine]
            types = {r.pin.type for r in pins}
            if "power_in" in types and "power_out" not in types:
                out.append(n)
        return out

    def _label_text(self, item, p):
        part = item.part
        if part is None:              # PWR_FLAG
            return item.flag_net.name
        num = p.number
        net = part.conn.get(num)
        if net is None:
            return None
        return net.name

    def _items_for_block(self, b):
        items = []
        for part in b.parts:
            pins = part.pins
            lib_id, sym = self.st.resolve(part.defn, pins)
            for u in range(1, sym.units + 1):
                if not sym.pins_of(u) and sym.units > 1:
                    continue
                items.append(Item(part, u, lib_id, sym, part.ref, part.value))
        return items

    def _flag_item(self, net):
        lib_id = "power:PWR_FLAG"
        sym = self.st.libs.get(lib_id)
        self.st.used_libs.add("power")
        self.flag_count += 1
        it = Item(None, 1, lib_id, sym, f"#FLG{self.flag_count:02d}", "PWR_FLAG")
        it.flag_net = net
        return it

    def _layout(self, items):
        for it in items:
            it.measure(self._label_text)
        groups = self._groups(items)
        total = sum(g.width * g.height for g in groups) * 1.2
        widest = max([g.width for g in groups] + [50])
        for paper, pw, ph in PAPERS:
            uw, uh = pw - 2 * MARGIN, ph - 2 * MARGIN - TITLE_BLOCK_H
            if widest > uw:
                continue
            if self._pack(groups, uw) <= uh and total <= uw * uh:
                return paper, pw, ph
        paper, pw, ph = PAPERS[-1]
        self._pack(groups, pw - 2 * MARGIN)
        return paper, pw, ph

    def _nets_of(self, it):
        if it.part is None:
            return {it.flag_net}
        return set(it.part.conn.values())

    def _groups(self, items):
        """Cluster small parts under the multi-pin part they share the most with."""
        def weight(n):
            if n.kind == "ground":
                return 0.1
            if n.kind in ("power", "hv", "mains"):
                return 1.0
            return 3.0 if not n.is_global else 2.0

        anchors = [it for it in items if it.part is not None and len(it.part.pins) >= 3]
        seen_parts = set()
        groups = {id(a): _Group([a]) for a in anchors}
        order = [groups[id(a)] for a in anchors]
        loose = []
        for it in items:
            if it in anchors:
                continue
            nets = self._nets_of(it)
            best, score = None, 0.0
            for a in anchors:
                sc = sum(weight(n) for n in nets & self._nets_of(a))
                if sc > score:
                    best, score = a, sc
            if best is None:
                loose.append(it)
            else:
                groups[id(best)].members.append(it)
        # loose parts sharing a signal net with an already grouped part join that group
        for it in list(loose):
            nets = self._nets_of(it)
            for g in order:
                if any(weight(n) >= 2.0 for m in g.members for n in nets & self._nets_of(m)):
                    g.members.append(it)
                    loose.remove(it)
                    break
        # remaining loose parts: chain them by shared nets into small groups
        while loose:
            g = _Group([loose.pop(0)])
            changed = True
            while changed and len(g.members) < 6:
                changed = False
                nets = set().union(*(self._nets_of(m) for m in g.members))
                for it in list(loose):
                    if any(weight(n) >= 1.0 for n in nets & self._nets_of(it)):
                        g.members.append(it)
                        loose.remove(it)
                        changed = True
            order.append(g)
        for g in order:
            g.arrange()
        return order

    @staticmethod
    def _pack(groups, width):
        x, y, row_h = MARGIN, MARGIN, 0.0
        for g in groups:
            if x > MARGIN and x + g.width > MARGIN + width:
                x, y, row_h = MARGIN, y + row_h + GAP, 0.0
            g.place(x, y)
            x += g.width + GAP
            row_h = max(row_h, g.height)
        return y + row_h - MARGIN

    def _symbol_node(self, it, sheet_path, key):
        part = it.part
        x, y = it.x, it.y
        node = S("symbol", S("lib_id", it.lib_id), S("at", x, y, 0), S("unit", it.unit),
                 S("exclude_from_sim", Sym("no")),
                 S("in_bom", Sym("yes" if part and part.defn.in_bom and not part.dnp else "no")),
                 S("on_board", Sym("yes" if part is None or part.on_board else "no")),
                 S("dnp", Sym("yes" if part and part.dnp else "no")),
                 S("uuid", self.u("sym", *key)))
        lib_props = {p[1]: p for p in sexpr.find_all(it.sym.node, "property")}

        def lib_pos(name, dx=0.0, dy=0.0):
            lp = lib_props.get(name)
            if lp is None:
                return x + dx, y + dy, 0, None
            at = sexpr.find(lp, "at")
            eff = sexpr.find(lp, "effects")
            just = sexpr.find(eff, "justify") if eff else None
            return x + float(at[1]), y - float(at[2]), int(float(at[3])) if len(at) > 3 else 0, \
                (" ".join(str(j) for j in just[1:]) if just else None)

        rx, ry, ra, rj = lib_pos("Reference")
        vx, vy, va, vj = lib_pos("Value")
        hide_ref = part is None
        node.append(prop("Reference", it.ref, rx, ry, ra, hide=hide_ref, justify=rj))
        node.append(prop("Value", it.value, vx, vy, va, hide=False, justify=vj))
        if part is not None:
            defn = part.defn
            node.append(prop("Footprint", defn.footprint or "", x, y, hide=True))
            node.append(prop("Datasheet", defn.datasheet or "", x, y, hide=True))
            node.append(prop("Description", defn.description or "", x, y, hide=True))
            extra = {}
            if defn.mpn:
                extra["MPN"] = defn.mpn
            if defn.manufacturer:
                extra["Manufacturer"] = defn.manufacturer
            extra["Block"] = part.block.name
            extra["Component Class"] = part.block.name
            extra.update({k: str(v) for k, v in defn.fields.items()})
            extra.update({k: str(v) for k, v in part.fields.items()})
            for k, v in extra.items():
                if k in ("Reference", "Value", "Footprint", "Datasheet", "Description"):
                    continue
                node.append(prop(k, v, x, y, hide=True))
        else:
            node.append(prop("Footprint", "", x, y, hide=True))
        for p in it.sym.pins_of(it.unit):
            node.append(S("pin", p.number, S("uuid", self.u("pin", *key, p.number))))
        node.append(S("instances", S("project", self.slug,
                                      S("path", sheet_path, S("reference", it.ref), S("unit", it.unit)))))
        return node

    def _pin_furniture(self, it, key, nc_pins, global_names):
        out = []
        for p, px, py, ox, oy in it.pins:
            ax, ay = snap(it.x + px, 1.27), snap(it.y + py, 1.27)
            if it.part is not None and p.number in nc_pins:
                out.append(S("no_connect", S("at", ax, ay), S("uuid", self.u("nc", *key, p.number))))
                continue
            text = self._label_text(it, p)
            if text is None:
                continue
            bx, by = snap(ax + ox * STUB, 1.27), snap(ay + oy * STUB, 1.27)
            out.append(S("wire", S("pts", S("xy", ax, ay), S("xy", bx, by)),
                         S("stroke", S("width", 0), S("type", Sym("default"))),
                         S("uuid", self.u("wire", *key, p.number))))
            if ox > 0:
                ang, just = 0, "left"
            elif ox < 0:
                ang, just = 180, "right"
            elif oy < 0:
                ang, just = 90, "left"
            else:
                ang, just = 270, "right"
            eff = S("effects", S("font", S("size", 1.27, 1.27)), S("justify", Sym(just)))
            if text in global_names:
                out.append(S("global_label", text, S("shape", Sym("passive")), S("at", bx, by, ang),
                             S("fields_autoplaced", Sym("yes")), eff,
                             S("uuid", self.u("glabel", *key, p.number)),
                             S("property", "Intersheetrefs", "${INTERSHEET_REFS}", S("at", bx, by, 0),
                               S("hide", Sym("yes")), font())))
            else:
                out.append(S("label", text, S("at", bx, by, ang), S("fields_autoplaced", Sym("yes")), eff,
                             S("uuid", self.u("label", *key, p.number))))
        return out

    def _sheet(self, b, page, flag_nets):
        items = self._items_for_block(b)
        for n in flag_nets:
            items.append(self._flag_item(n))
        paper, pw, ph = self._layout(items)
        sheet_uuid = self.u("sheet", b.name)
        path = f"/{self.root_uuid}/{sheet_uuid}"
        global_names = set(self.d.nets)
        body = []
        for it in items:
            key = (b.name, it.ref, it.unit)
            body.append(self._symbol_node(it, path, key))
            nc = it.part.nc | {p.number for p in it.part.pins if p.type == "no_connect"} if it.part else set()
            body.extend(self._pin_furniture(it, key, nc, global_names))
        lib_ids = sorted({it.lib_id for it in items})
        return self._file(b.title, paper, self.u("file", b.name), lib_ids, body,
                          comment=(b.description or "")[:200], page=page)

    def _file(self, title, paper, file_uuid, lib_ids, body, comment="", page=1, root=False):
        libsyms = S("lib_symbols")
        for lid in lib_ids:
            sym = self.st.project.get(lid) or self.st.libs.get(lid)
            node = sexpr.loads(sexpr.dumps(sym.node))
            node[1] = lid
            libsyms.append(node)
        tb = S("title_block", S("title", title), S("date", self.date), S("rev", self.d.revision),
               S("company", self.d.author))
        if comment:
            tb.append(S("comment", 1, comment))
        if not root:
            tb.append(S("comment", 2, f"{self.d.title} — generated by kaesynth from design.py; do not edit by hand"))
        doc = S("kicad_sch", S("version", SCH_VERSION), S("generator", "kaesynth"), S("generator_version", "0.1"),
                S("uuid", file_uuid), S("paper", paper), tb, libsyms, *body)
        if root:
            doc.append(S("sheet_instances", S("path", "/", S("page", "1"))))
        doc.append(S("embedded_fonts", Sym("no")))
        return sexpr.dumps(doc) + "\n"

    def _root(self):
        d = self.d
        body = []
        notes = self._root_notes()
        x, y, row_h = MARGIN, snap(MARGIN + (notes.count("\n") + 2) * 2.54 + 5.08), 0.0
        width_limit = 420 - 2 * MARGIN
        for i, b in enumerate(self.blocks):
            w = snap(max(40.64, len(b.title) * 1.6 + 10))
            h = 15.24
            if x > MARGIN and x + w > MARGIN + width_limit:
                x, y = MARGIN, y + row_h + 12.7
                row_h = 0
            sx, sy = snap(x), snap(y)
            body.append(S("sheet", S("at", sx, sy), S("size", w, h), S("exclude_from_sim", Sym("no")),
                          S("in_bom", Sym("yes")), S("on_board", Sym("yes")), S("dnp", Sym("no")),
                          S("fields_autoplaced", Sym("yes")),
                          S("stroke", S("width", 0.1524), S("type", Sym("solid"))),
                          S("fill", S("color", 0, 0, 0, 0.0)),
                          S("uuid", self.u("sheet", b.name)),
                          prop("Sheetname", b.name, sx, sy - 0.7, justify="left bottom"),
                          prop("Sheetfile", f"{b.name}.kicad_sch", sx, sy + h + 0.6, justify="left top"),
                          S("instances", S("project", self.slug, S("path", f"/{self.root_uuid}", S("page", str(i + 2)))))))
            body.append(S("text", b.title, S("exclude_from_sim", Sym("no")), S("at", sx + 1.27, sy + 7.62, 0),
                          S("effects", S("font", S("size", 1.27, 1.27)), S("justify", Sym("left"))),
                          S("uuid", self.u("sheettext", b.name))))
            x += w + 12.7
            row_h = max(row_h, h)
        body.append(S("text", notes, S("exclude_from_sim", Sym("no")), S("at", MARGIN, MARGIN, 0),
                      S("effects", S("font", S("size", 1.27, 1.27)), S("justify", Sym("left"), Sym("top"))),
                      S("uuid", self.u("rootnotes"))))
        paper = next((p for p, pw, ph in PAPERS[1:] if y + row_h + MARGIN + TITLE_BLOCK_H <= ph), "A0")
        return self._file(d.title, paper, self.root_uuid, [], body, comment=d.description[:200], root=True)

    def _root_notes(self):
        import textwrap
        lines = []
        for ln in self._root_note_lines():
            lines.extend(textwrap.wrap(ln, 150, subsequent_indent="    ") or [""])
        return "\n".join(lines)

    def _root_note_lines(self):
        d = self.d
        lines = [f"{d.title} (rev {d.revision})" + (f" — board '{self.board}'" if self.board else "")]
        boards = d.board_names()
        if len(boards) > 1 or any(b.board_name == "off" for b in d.blocks):
            lines.append("Boards: " + "; ".join(
                f"{name}: {', '.join(b.name for b in d.blocks if b.board_name == name)}"
                for name in boards + (["off"] if any(b.board_name == "off" for b in d.blocks) else [])))
        if d.domains:
            lines.append("Domains: " + "; ".join(
                f"{x.name} ({x.kind}, 0 V = {x.ref})" for x in d.domains.values()))
        for bar in d.barriers:
            lines.append(f"Barrier {bar.a}/{bar.b}: {bar.grade}, {bar.v_work:g} V working, "
                         f"creepage {bar.creepage_mm:g} mm, clearance {bar.clearance_mm:g} mm ({bar.standard})")
        open_q = [q for q in d.questions if q.blocking and not q.answer]
        if open_q:
            lines.append("NOT READY FOR FABRICATION — blocking questions: " + ", ".join(q.id for q in open_q))
        return lines
