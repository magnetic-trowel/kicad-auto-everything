# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic design checks over the IR.

Each check yields Findings with a stable check id. Errors block the build's "checks pass"
status; waivers (Design.waive) turn a finding into an accepted, recorded exception.
"""
import itertools
import math
import re
from dataclasses import dataclass, field

from .ir import GRADES, OFF_BOARD, THREATS, DesignError
from .units import parse_value


@dataclass
class Finding:
    check: str
    severity: str          # error | warning | info
    message: str
    objects: list = field(default_factory=list)
    waived_by: str = None

    def as_dict(self):
        d = {"check": self.check, "severity": self.severity, "message": self.message,
             "objects": self.objects}
        if self.waived_by:
            d["waived_by"] = self.waived_by
        return d


SERIES_CATEGORIES = ("fuse", "ptc", "connector", "relay", "inductor", "switch", "mosfet", "diode",
                     "transformer", "led", "bjt")


class Checker:
    def __init__(self, design, symlibs=None, fplibs=None):
        self.d = design
        self.sym = symlibs
        self.fp = fplibs
        self.findings = []
        self._expand_cache = {}

    def add(self, check, severity, message, objects=()):
        self.findings.append(Finding(check, severity, message, [str(o) for o in objects]))

    def run(self):
        d = self.d.finalize()
        self.check_domains()
        self.check_boards()
        self.check_connectivity()
        self.check_pin_types()
        self.check_voltage()
        self.check_isolation()
        self.check_current()
        self.check_power()
        self.check_library()
        self.check_bom()
        self.check_provenance()
        self.check_dc_bias()
        self.check_protection()
        self.check_calcs()
        self.check_intent()
        self.apply_waivers()
        return self.findings

    # -- voltage model --------------------------------------------------------------------------
    def expand(self, net):
        """Express V(net) as a sum of independent net-range variables up to its root domain."""
        key = id(net)
        if key in self._expand_cache:
            return self._expand_cache[key]
        dom = self.d.domain_of(net)
        if dom is None:
            self._expand_cache[key] = (None, None)
            return None, None
        terms = {net: 1}
        seen = set()
        while True:
            if dom.name in seen:
                raise DesignError(f"domain reference cycle at {dom.name}")
            seen.add(dom.name)
            ref = self.d.net_by_name(dom.ref)
            rdom = self.d.domain_of(ref)
            if rdom is dom or rdom is None:
                break
            terms[ref] = terms.get(ref, 0) + 1
            dom = rdom
        self._expand_cache[key] = (terms, dom)
        return terms, dom

    def chain(self, dom):
        """(terms, root) for a domain's 0 V relative to its root: {net: coefficient}."""
        terms, d, seen = {}, dom, set()
        while True:
            if d.name in seen:
                raise DesignError(f"domain reference cycle at {d.name}")
            seen.add(d.name)
            ref = self.d.net_by_name(d.ref)
            rd = self.d.domain_of(ref)
            if rd is d or rd is None:
                return terms, d
            terms[ref] = terms.get(ref, 0) + 1
            d = rd

    def domain_pair_vmax(self, da, db):
        """Worst |V| between any net of domain da and any net of domain db (None if separate roots)."""
        ta, ra = self.chain(da)
        tb, rb = self.chain(db)
        if ra is not rb:
            return None
        rng_a = [self.vrange(n) for n in self.d.all_nets() if self.d.domain_of(n) is da and n.pins]
        rng_b = [self.vrange(n) for n in self.d.all_nets() if self.d.domain_of(n) is db and n.pins]
        rng_a, rng_b = [r for r in rng_a if r], [r for r in rng_b if r]
        if not rng_a or not rng_b:
            return None
        terms = dict(ta)
        for n, c in tb.items():
            terms[n] = terms.get(n, 0) - c
        lo = min(r[0] for r in rng_a) - max(r[1] for r in rng_b)
        hi = max(r[1] for r in rng_a) - min(r[0] for r in rng_b)
        for n, c in terms.items():
            v = self.vrange(n)
            if c == 0 or v is None:
                continue
            lo += min(c * v[0], c * v[1])
            hi += max(c * v[0], c * v[1])
        return max(abs(lo), abs(hi))

    def root(self, net):
        return self.expand(net)[1]

    def vrange(self, net):
        if net.v is not None:
            return net.v
        dom = self.d.domain_of(net)
        return getattr(dom, "v_range", None)

    def vdiff(self, a, b):
        """Interval of V(a) - V(b), or None if unknown or galvanically separate."""
        if a is b:
            return (0.0, 0.0)
        ta, ra = self.expand(a)
        tb, rb = self.expand(b)
        if ra is None or rb is None or ra is not rb:
            return None
        terms = dict(ta)
        for n, c in tb.items():
            terms[n] = terms.get(n, 0) - c
        lo = hi = 0.0
        for n, c in terms.items():
            if c == 0:
                continue
            v = self.vrange(n)
            if v is None:
                return None
            x0, x1 = c * v[0], c * v[1]
            lo += min(x0, x1)
            hi += max(x0, x1)
        return (lo, hi)

    def vmax_between(self, nets_a, nets_b):
        worst, pair = 0.0, None
        for a in nets_a:
            for b in nets_b:
                r = self.vdiff(a, b)
                if r is None:
                    continue
                m = max(abs(r[0]), abs(r[1]))
                if m > worst:
                    worst, pair = m, (a, b)
        return worst, pair

    # -- checks ---------------------------------------------------------------------------------
    def check_domains(self):
        d = self.d
        if not d.domains:
            self.add("domain.none", "warning", "design declares no voltage domains; voltage and isolation checks are skipped")
            return
        for dom in d.domains.values():
            try:
                ref = d.net_by_name(dom.ref)
            except DesignError:
                self.add("domain.ref", "error", f"domain {dom.name}: reference net {dom.ref} does not exist", [dom.name])
                continue
            rdom = d.domain_of(ref)
            if rdom is None:
                self.add("domain.ref", "error", f"domain {dom.name}: reference net {dom.ref} has no domain", [dom.name])
            elif rdom is dom and ref.v not in (None, (0.0, 0.0)):
                self.add("domain.ref", "error", f"root domain {dom.name}: its reference {dom.ref} must have v=0", [dom.name])
        for n in d.all_nets():
            if n.domain is None:
                self.add("net.no_domain", "error", f"net {n.full_name} has no domain", [n.full_name])
            elif d.domain_of(n) is None:
                self.add("net.no_domain", "error", f"net {n.full_name}: unknown domain {n.domain!r}", [n.full_name])
            elif self.vrange(n) is None and n.pins:
                self.add("net.no_voltage", "warning", f"net {n.full_name} has no voltage range; rating checks skip it",
                         [n.full_name])
        names = set(d.domains)
        for b in d.barriers:
            for x in (b.a, b.b):
                if x not in names:
                    self.add("barrier.domain", "error", f"barrier {b.a}-{b.b}: unknown domain {x}", [x])

    def check_boards(self):
        """Nets that leave a board must do so through a connector on that board."""
        d = self.d
        for b in d.blocks:
            if b.board is not None and b.board != OFF_BOARD and b.board not in d.boards:
                self.add("board.unknown", "error", f"block {b.name} is on undeclared board {b.board!r}", [b.name])
        if len(d.board_names()) + any(b.board_name == OFF_BOARD for b in d.blocks) < 2:
            return
        for n in d.all_nets():
            by_board = {}
            for r in n.pins:
                by_board.setdefault(r.part.block.board_name, []).append(r)
            if len(by_board) < 2:
                continue
            for board, refs in by_board.items():
                if board == OFF_BOARD:
                    continue
                if not any(r.part.defn.category == "connector" for r in refs):
                    self.add("board.crossing_without_connector", "error",
                             f"net {n.full_name} runs from board {board!r} to {sorted(set(by_board) - {board})} "
                             f"but has no connector pin on {board!r}", [n.full_name])

    def check_connectivity(self):
        for p in self.d.all_parts():
            for pin in p.pins:
                if pin.number in p.conn or pin.number in p.nc or pin.type == "no_connect":
                    continue
                self.add("conn.unconnected_pin", "error",
                         f"{p.ref} pin {pin.number} ({pin.name or '-'}) is neither connected nor marked NC",
                         [f"{p.ref}.{pin.number}"])
            for num in sorted(p.nc, key=_natkey):
                if num not in p.nc_reason and not p.defn.generic and p.defn.category not in ("connector", "relay"):
                    pin = next(x for x in p.pins if x.number == num)
                    self.add("conn.nc_without_reason", "warning",
                             f"{p.ref} pin {num} ({pin.name or '-'}) is left open without a reason "
                             f"(nc_pins(..., reason='datasheet says ...'))", [f"{p.ref}.{num}"])
        for n in self.d.all_nets():
            if not n.pins:
                if any(dom.ref == n.full_name or dom.ref == n.name for dom in self.d.domains.values()):
                    continue          # 0 V of a domain with no copper here (chassis, PE)
                self.add("conn.empty_net", "warning", f"net {n.full_name} has no pins", [n.full_name])
            elif len(n.pins) == 1:
                self.add("conn.single_pin_net", "error", f"net {n.full_name} connects only {n.pins[0].part.ref}.{n.pins[0].pin.number}",
                         [n.full_name])

    def check_pin_types(self):
        for n in self.d.all_nets():
            drivers = [r for r in n.pins if r.pin.type in ("output", "power_out")]
            if len(drivers) > 1:
                self.add("erc.output_conflict", "error",
                         f"net {n.full_name} has {len(drivers)} push-pull drivers: {[str(f'{r.part.ref}.{r.pin.number}') for r in drivers]}",
                         [n.full_name])
            if any(r.pin.type == "no_connect" for r in n.pins):
                self.add("erc.nc_pin_connected", "warning", f"net {n.full_name} connects a pin typed no_connect",
                         [n.full_name])

    def _pins_nets(self, part, keys):
        nets = []
        for k in keys:
            try:
                refs = part.pin(k)
            except DesignError as e:
                self.add("rating.bad_pin", "error", str(e), [part.ref])
                continue
            nets.extend(part.conn[r.pin.number] for r in refs if r.pin.number in part.conn)
        return nets

    def _derate(self, kind, cat):
        table = self.d.derating[kind]
        return table.get(cat, table.get("capacitor" if cat.startswith("capacitor") else cat, table["default"]))

    def _rate(self, check, part, stress, rating, what, extra=""):
        if rating is None or rating <= 0:
            return
        ratio = stress / rating
        lim = self._derate("voltage" if check == "rating.voltage" else
                           "current" if check == "rating.current" else "power", part.defn.category)
        msg = f"{part.ref} ({part.value}): {what} {stress:.3g} vs rating {rating:.3g} ({ratio:.0%}){extra}"
        if ratio > 1.0:
            self.add(check, "error", msg + " — exceeds rating", [part.ref])
        elif ratio > lim:
            self.add(check, "warning", msg + f" — above {lim:.0%} derating", [part.ref])

    def check_voltage(self):
        if not self.d.domains:
            return
        for p in self.d.all_parts():
            r = p.defn.ratings
            if getattr(p, "v_across", None) is not None and r.v_max:
                self._rate("rating.voltage", p, p.v_across, r.v_max, "declared voltage", " (declared v_across)")
            elif r.v_max:
                nets = list(dict.fromkeys(p.conn.values()))
                worst, pair = 0.0, None
                for a, b in itertools.combinations(nets, 2):
                    w, pr = self.vmax_between([a], [b])
                    if w > worst:
                        worst, pair = w, pr
                if pair:
                    self._rate("rating.voltage", p, worst, r.v_max, "voltage",
                               f" between {pair[0].full_name} and {pair[1].full_name}")
            for lim in r.limits:
                self._check_vlimit(p, lim)
            if r.polarity:
                pos, neg = self._pins_nets(p, [r.polarity[0]]), self._pins_nets(p, [r.polarity[1]])
                if pos and neg:
                    rng = self.vdiff(pos[0], neg[0])
                    if rng and rng[0] < -1.0:
                        self.add("rating.polarity", "error",
                                 f"{p.ref} ({p.value}): polarized part can see {rng[0]:.3g} V reverse "
                                 f"({pos[0].full_name} below {neg[0].full_name})", [p.ref])

    def _check_vlimit(self, p, lim):
        na, nb = self._pins_nets(p, lim.a), self._pins_nets(p, lim.b)
        what = f"V({'/'.join(map(str, lim.a))}-{'/'.join(map(str, lim.b))})"
        if lim.v_min is None:
            worst, pair = self.vmax_between(na, nb)
            if not pair:
                return
            where = f" ({pair[0].full_name} to {pair[1].full_name})"
        else:
            lo, hi, where = None, None, ""
            for a in na:
                for b in nb:
                    rng = self.vdiff(a, b)
                    if rng is None:
                        continue
                    lo = rng[0] if lo is None else min(lo, rng[0])
                    hi = rng[1] if hi is None else max(hi, rng[1])
            if lo is None:
                return
            if lo < lim.v_min:
                self.add("rating.voltage", "error",
                         f"{p.ref} ({p.value}): {what} can reach {lo:.3g} V, below its {lim.v_min:g} V limit", [p.ref])
            worst = max(hi, 0.0)
        if lim.v_rec is not None and worst <= lim.v_rec:
            if worst > lim.v_max:
                self._rate("rating.voltage", p, worst, lim.v_max, what, where)
            return
        if lim.v_rec is not None and worst <= lim.v_max:
            self.add("rating.voltage", "warning",
                     f"{p.ref} ({p.value}): {what} {worst:.3g} V is above the recommended {lim.v_rec:g} V "
                     f"(abs max {lim.v_max:g} V){where}", [p.ref])
            return
        self._rate("rating.voltage", p, worst, lim.v_max, what, where)

    def check_isolation(self):
        d = self.d
        if not d.domains:
            return
        for p in d.all_parts():
            roots = {}
            for num, net in p.conn.items():
                rt = self.root(net)
                if rt is not None:
                    roots.setdefault(rt.name, []).append(num)
            if len(roots) < 2:
                continue
            isos = p.defn.ratings.isolation
            pinsets = []
            for iso in isos:
                a = {r.pin.number for k in iso.a for r in p.pin(k)}
                b = {r.pin.number for k in iso.b for r in p.pin(k)}
                pinsets.append((iso, a, b))
            for (ra, pa), (rb, pb) in itertools.combinations(roots.items(), 2):
                covering = [iso for iso, a, b in pinsets
                            if (set(pa) <= a and set(pb) <= b) or (set(pa) <= b and set(pb) <= a)]
                if not covering:
                    self.add("domain.crossing", "error",
                             f"{p.ref} ({p.value}) bridges isolated domains {ra} (pins {sorted(pa)}) and {rb} "
                             f"(pins {sorted(pb)}) without a rated isolation between those pins",
                             [p.ref])
                    continue
                bar = self.barrier_between(ra, rb)
                if bar is None:
                    self.add("barrier.missing", "error",
                             f"{p.ref} crosses {ra}/{rb} but no Barrier is declared between them", [p.ref])
                    continue
                iso = max(covering, key=lambda i: GRADES[i.grade])
                if GRADES[iso.grade] < GRADES[bar.grade]:
                    self.add("barrier.grade", "error",
                             f"{p.ref} ({p.value}) isolation is {iso.grade}; barrier {bar.a}/{bar.b} needs {bar.grade}",
                             [p.ref])
                if bar.v_test_rms and iso.v_iso_rms < bar.v_test_rms:
                    self.add("barrier.withstand", "error",
                             f"{p.ref} ({p.value}) withstand {iso.v_iso_rms:g} Vrms < required {bar.v_test_rms:g} Vrms",
                             [p.ref])
                if iso.v_work_rms and iso.v_work_rms * math.sqrt(2) < bar.v_work * 0.999 and iso.v_work_rms < bar.v_work:
                    self.add("barrier.working_voltage", "error",
                             f"{p.ref} ({p.value}) rated working voltage {iso.v_work_rms:g} Vrms < barrier {bar.v_work:g} V",
                             [p.ref])
                if iso.creepage_mm is not None and iso.creepage_mm < bar.creepage_mm:
                    self.add("barrier.package_creepage", "error",
                             f"{p.ref} ({p.value}) package creepage {iso.creepage_mm:g} mm < required {bar.creepage_mm:g} mm",
                             [p.ref])

    def barrier_between(self, root_a, root_b):
        best = None
        for bar in self.d.barriers:
            da, db = self.d.domains.get(bar.a), self.d.domains.get(bar.b)
            if da is None or db is None:
                continue
            ra, rb = self._dom_root(da), self._dom_root(db)
            if {ra, rb} == {root_a, root_b}:
                if best is None or GRADES[bar.grade] > GRADES[best.grade]:
                    best = bar
        return best

    def _dom_root(self, dom):
        try:
            ref = self.d.net_by_name(dom.ref)
        except DesignError:
            return None
        rt = self.root(ref)
        return rt.name if rt else None

    def check_current(self):
        declared = set()
        for p in self.d.all_parts():
            if p.i_through is None or p.defn.category not in SERIES_CATEGORIES:
                continue
            declared.add(id(p))
            rat = p.defn.ratings
            if isinstance(p.i_through, dict):          # per pin/winding: {"1": 2.5, "SEC": 0.4}
                for key, amps in p.i_through.items():
                    for r in p.pin(key):
                        lim = rat.pin_i_max.get(r.pin.number, rat.pin_i_max.get(r.pin.name, rat.i_max))
                        self._rate("rating.current", p, amps, lim, f"declared current through pin {r.pin.number}")
                continue
            lim = rat.i_max if rat.i_max is not None else (min(rat.pin_i_max.values()) if rat.pin_i_max else None)
            self._rate("rating.current", p, p.i_through, lim, "declared current (i_through)")
        for n in self.d.all_nets():
            if not n.i_max:
                continue
            for r in n.pins:
                p = r.part
                if p.defn.category not in SERIES_CATEGORIES or id(p) in declared:
                    continue
                rat = p.defn.ratings
                lim = None
                for k in (r.pin.number, r.pin.name):
                    if k in rat.pin_i_max:
                        lim = rat.pin_i_max[k]
                if lim is None:
                    lim = rat.i_max
                self._rate("rating.current", p, n.i_max, lim,
                           f"current on {n.full_name} through pin {r.pin.number} (set i_through= if the part carries less)")

    def check_power(self):
        for p in self.d.all_parts():
            rat = p.defn.ratings
            if p.p_diss is not None:
                if rat.p_max:
                    self._rate("rating.power", p, p.p_diss, rat.p_max, "dissipation (W)")
                elif p.p_diss > 0.25:
                    self.add("rating.power", "warning",
                             f"{p.ref} ({p.value}) dissipates {p.p_diss:g} W but has no power rating to check against",
                             [p.ref])
                continue
            if p.defn.category == "resistor" and rat.p_max and len(p.conn) == 2:
                ohms = parse_value(p.value)
                a, b = list(p.conn.values())
                rng = self.vdiff(a, b)
                if ohms and rng:
                    v = max(abs(rng[0]), abs(rng[1]))
                    pw = v * v / ohms
                    if pw > rat.p_max * self._derate("power", "resistor"):
                        self.add("rating.power", "warning" if pw <= rat.p_max else "error",
                                 f"{p.ref} ({p.value}): worst case {v:.3g} V across it gives {pw:.3g} W vs "
                                 f"rating {rat.p_max:g} W — set p_diss from a calculation or fix the net ranges",
                                 [p.ref])

    def check_library(self):
        if self.sym is None:
            self.add("lib.unchecked", "info", "KiCad libraries not found; symbol/footprint checks skipped")
            return
        seen = set()
        for p in self.d.all_parts():
            defn = p.defn
            if id(defn) in seen:
                continue
            seen.add(id(defn))
            who = f"{p.ref} ({defn.mpn or defn.value})"
            if defn.symbol and not self.sym.has(defn.symbol):
                self.add("lib.symbol_missing", "error", f"{who}: symbol {defn.symbol} not in KiCad libraries", [p.ref])
                continue
            if defn.symbol:
                s = self.sym.get(defn.symbol)
                hidden = [x for x in s.pins if x.hidden and x.type in ("power_in", "power_out")]
                if hidden and not s.power:
                    self.add("lib.hidden_power_pins", "error",
                             f"{who}: symbol {defn.symbol} has hidden power pins {[x.number for x in hidden]} that "
                             f"connect implicitly by name; use a symbol without hidden pins", [p.ref])
            if not p.on_board:
                continue
            if not defn.footprint:
                self.add("lib.footprint_missing", "error", f"{who}: no footprint", [p.ref])
                continue
            if defn.footprint.startswith("custom:") and not self.fp.has(defn.footprint):
                self.add("lib.footprint_custom", "warning",
                         f"{who}: custom footprint {defn.footprint} is not drawn yet "
                         f"(designs/<slug>/footprints/custom.pretty/{defn.footprint.split(':', 1)[1]}.kicad_mod)",
                         [p.ref])
                continue
            if not self.fp.has(defn.footprint):
                self.add("lib.footprint_missing", "error", f"{who}: footprint {defn.footprint} not in KiCad libraries", [p.ref])
                continue
            pads = self.fp.pads(defn.footprint)
            pins = {x.number for x in p.pins}
            missing = sorted(pins - pads, key=_natkey)
            if missing:
                self.add("lib.pad_mismatch", "error",
                         f"{who}: symbol pins {missing} have no pad in {defn.footprint} (pads {sorted(pads, key=_natkey)})",
                         [p.ref])
            extra = sorted(pads - pins, key=_natkey)
            if extra:
                self.add("lib.unused_pads", "warning",
                         f"{who}: footprint {defn.footprint} pads {extra} have no symbol pin (left unconnected)",
                         [p.ref])

    def check_bom(self):
        seen = set()
        for p in self.d.all_parts():
            defn = p.defn
            if id(defn) in seen or not defn.in_bom:
                continue
            seen.add(id(defn))
            if not defn.generic and not defn.mpn:
                self.add("bom.no_mpn", "warning", f"{p.ref} ({p.value}): no manufacturer part number", [p.ref])
            lc = (defn.lifecycle or "").lower()
            if lc in ("obsolete", "eol", "discontinued"):
                self.add("bom.lifecycle", "error", f"{p.ref} ({defn.mpn}) is {defn.lifecycle}", [p.ref])
            elif lc in ("nrnd", "last time buy", "ltb"):
                self.add("bom.lifecycle", "warning", f"{p.ref} ({defn.mpn}) is {defn.lifecycle}", [p.ref])

    def check_provenance(self):
        """Facts the LLM typed (pins, pin maps, ratings) must say where they came from."""
        seen = set()
        for p in self.d.all_parts():
            defn = p.defn
            if id(defn) in seen or defn.generic:
                continue
            seen.add(id(defn))
            who = f"{p.ref} ({defn.mpn or defn.value})"
            if not defn.datasheet and defn.category not in ("mechanical", "testpoint", "heatsink"):
                self.add("part.no_datasheet", "warning", f"{who}: no datasheet URL", [p.ref])
            need = []
            if defn.pins:
                need.append("pins")
            if defn.pinmap:
                need.append("pinmap")
            if defn.pin_names:
                need.append("pin_names")
            r = defn.ratings
            if r.limits or r.isolation or (r.v_max and defn.category not in ("resistor", "capacitor_ceramic")):
                need.append("ratings")
            missing = [k for k in need if not defn.source.get(k)]
            if missing:
                self.add("part.no_provenance", "warning",
                         f"{who}: no source for {', '.join(missing)} (PartDef(source={{'pins': 'DS rev, page, table'}}))",
                         [p.ref])

    def check_dc_bias(self):
        """Class II MLCCs lose much of their capacitance near rated voltage."""
        for p in self.d.all_parts():
            defn = p.defn
            if defn.category != "capacitor_ceramic" or len(p.conn) != 2 or "Ceff" in {**defn.fields, **p.fields}:
                continue
            diel = str(defn.fields.get("Dielectric", "X7R")).upper()
            if diel in ("C0G", "NP0", "COG"):
                continue
            farads = parse_value(p.value)
            vr = defn.ratings.v_max
            if not farads or farads < 1e-6 or not vr:
                continue
            a, b = list(p.conn.values())
            rng = self.vdiff(a, b)
            if rng is None:
                continue
            v = max(abs(rng[0]), abs(rng[1]))
            if v / vr > 0.5:
                self.add("rating.dc_bias", "warning",
                         f"{p.ref} ({p.value} {diel} {vr:g} V) runs at {v:.3g} V ({v / vr:.0%} of rating): "
                         f"effective capacitance may be well under half; check the vendor DC-bias curve and "
                         f"record it as fields={{'Ceff': '...'}}", [p.ref])

    def check_protection(self):
        for n in self.d.all_nets():
            for t in n.threats:
                cats = THREATS[t]
                # overcurrent protection must be in series on the wire's own net; other
                # protectors may sit one series element in (e.g. a TVS behind a PTC or ferrite)
                reach = [n] if t == "overcurrent" else [n] + self._one_series_hop(n)
                if t == "reverse_polarity" and any(r.part.defn.category in ("fuse", "ptc") for r in n.pins) \
                        and any(r.part.defn.category == "tvs" for m in reach for r in m.pins):
                    continue          # crowbar: the TVS conducts on reversal and the fuse opens
                if not any(r.part.defn.category in cats for m in reach for r in m.pins):
                    self.add("protect.threat", "error",
                             f"external net {n.full_name} declares threat '{t}' but has no {'/'.join(cats)} on it",
                             [n.full_name])
        for n in self.d.all_nets():
            if not n.external or n.kind not in ("power", "hv", "mains", "high_current"):
                continue
            if not any(r.part.defn.category in ("fuse", "ptc") for r in n.pins):
                self.add("protect.entry_fuse", "warning",
                         f"external {n.kind} net {n.full_name} reaches the board without a fuse/PTC on it",
                         [n.full_name])

    def _one_series_hop(self, net):
        out = []
        for r in net.pins:
            p = r.part
            if p.defn.category in ("fuse", "ptc", "inductor", "resistor") and len(p.conn) == 2:
                out.extend(m for m in p.conn.values() if m is not net)
        return out

    def check_calcs(self):
        ops = {"<=": lambda a, b: a <= b, "<": lambda a, b: a < b, ">=": lambda a, b: a >= b,
               ">": lambda a, b: a > b, "==": lambda a, b: math.isclose(a, b, rel_tol=1e-6)}
        for c in self.d.calcs:
            if c.limit is None:
                continue
            if not ops[c.op](c.value, c.limit):
                self.add("calc.limit", c.severity,
                         f"{c.name} = {c.value:.4g} {c.unit} violates {c.op} {c.limit:g} {c.unit}"
                         + (f" ({c.note})" if c.note else ""), [c.name])

    def check_intent(self):
        d = self.d
        for h in d.hazards:
            if not h.parts:
                self.add("hazard.procedural", "warning",
                         f"{h.id}: mitigated only procedurally ({h.mitigation})", [h.id])
            for x in h.parts:
                try:
                    d.find_part(x)
                except DesignError:
                    self.add("hazard.unknown_part", "error", f"{h.id}: mitigation part {x} does not exist", [h.id])
        for q in d.questions:
            if q.blocking and not q.answer:
                self.add("intent.blocking_question", "info",
                         f"{q.id} is BLOCKING and unanswered: {q.text}", [q.id])
        unknown = []
        d.place.resolve(unknown)
        for u in sorted(set(unknown)):
            self.add("place.unknown_object", "warning",
                     f"placement relation names {u!r}, which is not a part, domain, block or net", [u])
        for rel in d.place.relations:
            if rel["kind"] == "separate":
                a, b = rel["a"].removeprefix("domain:"), rel["b"].removeprefix("domain:")
                for x in (a, b):
                    if x not in d.domains:
                        self.add("place.unknown_object", "error", f"separate(): {x!r} is not a domain", [x])
                if not any({bar.a, bar.b} == {a, b} for bar in d.barriers):
                    self.add("place.separate_without_barrier", "error",
                             f"separate({a}, {b}) has no matching Barrier giving its spacing", [a, b])

    def apply_waivers(self):
        for f in self.findings:
            for w in self.d.waivers:
                if w.check not in (f.check, "*"):
                    continue
                hay = " ".join([f.message] + f.objects)
                if re.search(w.match, hay):
                    f.waived_by = f"{w.by}: {w.reason}"
                    break


def _natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s))]


def summarize(findings):
    out = {"error": 0, "warning": 0, "info": 0, "waived": 0}
    for f in findings:
        if f.waived_by:
            out["waived"] += 1
        else:
            out[f.severity] += 1
    return out
