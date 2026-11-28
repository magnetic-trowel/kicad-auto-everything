# SPDX-FileCopyrightText: 2026 HaslamPCB contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The DC band: where each rail's current flows in the copper, and what it costs there.

Power flow. Every rail of the brief has a source part; its loads are the parts that draw supply
current from it (an IC only through its supply pins) and return it at their own ground pads,
with class-prior currents (haslam.route.critical_rails.load_current, E5) as intervals x/3 .. x3, or
the intent file's. Each load's current is walked back to the board's input through the chain of
parts that feed its rail, so every copper island balances (KCL) and the ground copper carries
each return to where it really goes (a do-not-populate part takes no part in it):

    external source (connector, battery)  delivers I at its rail pads, takes it back at its ground pads; a
                                           rail with no source part whose voltage the facts state is fed
                                           at the connector on it
    linear (LDO, charger, load switch)     takes I from its input rail, delivers it to its output; also any
                                           part the facts give as the rail's source from another rail
                                           (nets.<rail>.from, a load switch transistor)
    switching regulator (no cell found)    takes I Vout / (eta Vin) from its input, the rest to ground
    commutation cell (haslam.circuit)         its inductor and rectifier conduct (lumped into the copper);
                                           the switches are injected: boost: the switch takes I_L - I_out
                                           to ground, I_L = I_in = I_out / (1 - D) with D = 1 - V_in eta /
                                           V_out; buck: the input gives I_in = D I_out / eta (the power
                                           balance), the high side D I_out, the cell's losses return through
                                           its ground; synchronous rectifiers likewise (haslam.physics.converter);
                                           a 4-switch buck-boost drives I_L out of SW1, takes it back at SW2
                                           and delivers I_out at its output pins. With the facts' eta,
                                           I_in = I_out Vout / (eta Vin); an input with no feed of its own
                                           enters at the controller

Every load draws its own current (the facts' I_A, the part table's supply current, else a class prior:
a sense, monitor or data-converter IC microamperes to milliamperes; a connector's export the facts do not state,
EXPORT_SHARE of its rating, and the evaluation asks for it), whatever feeds its rail. A rail fed by a cell carries the sum of its loads' currents
(and of the regulators it feeds, through their ratios); the cell's I_A interval (the AC ledger's, the
operating range the switching harms use) only bounds it from above.

Observers (requirements: the intent file's, else these priors):

    loss     copper dissipation (sum of J V over the pads, less the lumped parts' own) against
             LOSS_SHARE of the power the loads take
    drop     per load, rail plus ground drop from its rail's source (rail-side minus load-side, plus
             load ground minus source ground, at least 0) against DROP_SHARE of the rail voltage
    heating  per track, the temperature rise by IPC-2221 of the current through its cross-section,
             against DT_MAX. IPC-2221 is not the conservative formula for wide outer tracks: the
             Brooks-Adam fit of IPC-2152 (ipc2152_dT; no plane under the track) reads hotter wherever
             a 10 K track on 35 um is wider than 0.41 mm (above 1.25 A; 1.5-1.9x on 3 mm at 5-10 A)
             and cooler below; inner layers use IPC-2221's internal curve, which the fit does not
             cover (docs/research/physics/anchors-2611.md, check 3)
"""
from __future__ import annotations

import math
import re

import numpy as np

from haslam.physics import converter as CV

from .beliefs import Param
from .beliefs import lookup as lookup_part

LOSS_SHARE = 0.01       # copper may dissipate 1 % of the delivered power (prior requirement)
DROP_SHARE = 0.02       # rail + ground drop: 2 % of the rail voltage (as haslam.route.critical_rails)
DT_MAX = 10.0           # K, track temperature rise (the common IPC design point)
ETA = (0.75, 0.85, 0.95)   # efficiency of a switching regulator without a cell model (lo, typ, hi)
DC_KINDS = ("R", "L", "FB", "D_on", "short")     # circuit elements that conduct at DC
SERIES = ("transistor", "diode", "fuse", "ferrite", "resistor", "jumper", "inductor")   # a part in a rail's path
EPS = 1e-9              # float rounding, as a share of the largest injection: a plan's flow balances to this or is wrong
LINEAR = ("regulator_linear", "charger", "load_switch", "battery_monitor", "usb_pd")
SWITCHING = ("regulator_switching", "pmic", "regulator_module")
# parts that consume power as well as supply a rail: a module (an MCU board of its own: Teensy, XIAO, Pico, ESP32
# modules) whose regulator feeds the carrier's 3V3 while its own MCU draws from its input; an MCU, FPGA or radio
# whose internal regulator feeds a core rail. Their own draw is a load on their input (or, fed from their own
# connector, heat with no DC flow in the carrier's copper). A regulator's own draw is its quiescent current.
CONSUMER_SUB = ("mcu", "fpga", "processor", "soc", "rf", "phy", "memory", "logic", "adc_dac", "interface", "sensor",
                "audio_amp")
# what a part with a supply and a ground pad draws (A) where haslam.route.critical_rails has no class prior
LOAD_PRIOR = {"optocoupler": 0.01, "oscillator": 0.01}
# an LED with a pad on a rail and one on ground draws from the rail (an addressable LED's VDD and GND pins; a plain
# LED returning to ground beside its series resistor's rail end is not on the rail and is not a load here)
LOAD_KINDS = ("ic", "module", "connector", "led") + tuple(LOAD_PRIOR)
# sense, monitor and data-converter ICs: what they draw from a rail (A, lo .. hi; typical the geometric mean). A
# coulomb counter sleeps under 1 uA (LTC2959), a DAC channel takes 35 uA (DAC63002), a sensor or ADC converting
# up to a few mA; the copper-sizing priors (haslam.route.critical_rails.IC_A, 2-10 mA) are deliberately high
MONITOR_SUB = ("adc_dac", "sensor", "current_sense", "battery_monitor", "reference")
MONITOR_A = (1e-6, 1e-2)
# A connector on a fed rail with a ground pad exports the rail. Where the facts do not state its current, it draws
# 1 % of its class rating (0.01 x: 10 mA through a 1 A header pin, 30 mA through a 3 A USB receptacle): most
# such pins feed a sensor, a programmer or nothing on the bench, and a signal line through the same connector
# carries microamperes. The band is x/10 .. x10 around it (0.1 % .. 10 % of the rating): its top is the old
# typical guess (a tenth of the rating), so the DC band still checks drop and track heating at that current, and
# the load never leaves the plan (a board whose only loads are exports keeps its DC band; dropping unstated
# exports emptied sbarabe's and qubik's). The evaluation lists every such export in `questions` (kind
# "export_current") so the board's author states the real current or confirms it is signal-level.
EXPORT_SHARE = 0.01
EXPORT_BAND = (0.1, 10.0)       # lo, hi as factors of the assumed current
# A rail whose only loads are such exports takes what its feed delivers instead (plan): "stated" only where the facts
# state that current (cells.<id>.I_A or I_out_A, a charger's parts.<ref>.I_A), "all" also a ledger prior, "band" keeps
# the 1 % typical and raises the band's top to the feed's (stated or prior), "off" never
EXPORT_FROM_FEED = "band"
CHARGE_SINKS = True             # a charger with no load charges the external source one series part away (plan)
CHARGE_PATH = ("transistor", "diode")   # the blocking parts such a path runs through (any SERIES part for a charger IC)
SUPPLY_PIN = re.compile(r"^(V(CC|DD|IN|BAT|BUS|S|M|PP|IO|CORE|DDA|DDIO|USB|SYS|P|\+)\w*|AVDD|DVDD|IOVDD|PVDD|PVIN|"
                        r"AVCC|DVCC|VIN\d*|PWR|POWER|\+V\w*|V\+|VREG_IN|IN)$", re.I)
VOLT_PIN = re.compile(r"^\+?\d+V\d*$|^\+?\d+(\.\d+)?V$", re.I)     # '3V3', '5V', '+1.8V': a supply pin by its voltage


def fact_interval(v, what="value"):
    """(typ, lo, hi) of an operating fact's value: haslam.intent.facts.interval, the reader of every form the
    facts' checker accepts (a number, [lo, hi], [lo, typ, hi])."""
    from haslam.intent.facts import interval
    return interval(v, what)


def _eta(v, what):
    """(typ, lo, hi) of a stated efficiency, None when absent or outside (0, 1]. A [lo, typ, hi] eta was ignored
    (only [lo, hi] was read) and the regulator fell back to its class prior."""
    if v is None:
        return None
    t = fact_interval(v, what)
    return t if 0 < t[1] <= t[2] <= 1 else None


def draws_from(pp, net, rails):
    """Whether an IC or module with pads pp [(number, net, pintype, pinfunction)] takes supply current
    from rail `net`: a pad on it typed power_in or named as a supply (VCC, VDD, 3V3...), or, on a board
    whose pads carry neither name nor type (KiCad 5, Eagle and other imports: about half the corpus), a
    pad on a net the brief classed as a rail or whose name says supply (haslam.circuit.roles' rule)."""
    from haslam.circuit.roles import _unannotated_pin_sem
    for _, nt, pt, fn in pp:
        if nt != net:
            continue
        f = (fn or "").split("/")[0].strip()
        if pt == "power_in" or (pt != "power_out" and (SUPPLY_PIN.match(f) or VOLT_PIN.match(f))):
            return True
        if not f and not pt and (net in rails or _unannotated_pin_sem(net) == "supply"):
            return True
    return False


SIGNAL_PINS = ("input", "output", "bidirectional", "tri_state", "open_collector", "open_emitter")
OUT_PIN = re.compile(r"^(V?OUT\w*|VO|VREG|LDO\w*|BAT\w*|VSYS|SYS|CHG\w*)$", re.I)
K_IPC = {True: 0.048, False: 0.024}      # IPC-2221: I = k dT^0.44 A^0.725 (A in mil^2), external / internal


def ipc_dT(I, w_mm, t_mm, external=True):
    """Temperature rise (K) of a track of width w and thickness t carrying I (IPC-2221)."""
    A = (w_mm / 0.0254) * (t_mm / 0.0254)
    if I <= 0 or A <= 0:
        return 0.0
    return (I / (K_IPC[bool(external)] * A ** 0.725)) ** (1 / 0.44)


def ipc2152_dT(I, w_mm, t_mm):
    """Temperature rise (K) of an outer track of width w and thickness t carrying I by the Brooks-Adam fit
    of IPC-2152's external chart, dT = 215.3 I^2 W^-1.15 Th^-1 (mils; no plane under the track):
    haslam.route.critical_physics.ipc2152_dT, the one definition. The heating observer reports IPC-2221
    (ipc_dT); this is the second opinion beside it (docs/research/physics/anchors-2611.md, check 3)."""
    from haslam.route.critical_physics import ipc2152_dT as fit
    return fit(abs(I), w_mm, t_mm)


class Plan:
    """The DC power flow of one board: feeds per rail, loads, their current parameters."""

    def __init__(self):
        self.feeds = {}         # rail -> dict(kind, ...)
        self.loads = []         # dict(ref, rail, sup, gnd, key, prior, part_share): each draws its own current (key)
        self.params = []        # Params of the DC band (load currents, efficiencies)
        self.notes = []
        self.dc_pads = set()
        self.self_loads = []    # dict(ref, rail, key, pads): parts that power themselves from off the board (heat only)
        self.exports_assumed = []   # dict(ref, rail, key, rating_A, assumed_A, lo_A, hi_A, only_load): unstated exports
        self.piece = {}         # pad token -> its piece of the DC circuit (a net, with the nets DC parts join to it)
        self.offboard = {}      # piece -> connector ground pads: a ground piece the board joins to the others only off it


def export_questions(pl):
    """{(subject, name): fields} for each connector export the plan assumed at EXPORT_SHARE of its rating: the
    push-back to the board's author (haslam.excite.evaluate adds them to its `questions`, haslam.intent status lists
    them first). Machine-readable: the fact to state (`field`), the value used, and why it might differ."""
    out = {}
    for ex in pl.exports_assumed:
        why = []
        if ex.get("only_load"):
            why.append("it is its rail's only load: the assumption is the rail's whole current")
        if ex["rating_A"] >= 3.0:
            why.append(f"a {ex['rating_A']:g} A connector is likely a power connector")
        f = pl.feeds.get(ex["rail"]) or {}
        if f.get("kind") == "cell":
            why.append(f"its rail is fed by {f['cell']['id']}, whose operating current follows its loads")
        if ex.get("feed_top_A"):
            why.append(f"its rail's only loads are exports: their band reaches the {ex['feed_top_A']:.3g} A its feed delivers")
        if ex.get("feed_prior_A"):
            why.append(f"its rail's only loads are exports and its feed's prior current is {ex['feed_prior_A']:.3g} A")
        ref, r, a = ex["ref"], ex["rail"], ex["assumed_A"]
        how = (f"what its rail's feed {ex['from_feed']} delivers (its only loads are exports)" if ex.get("from_feed")
               else f"{EXPORT_SHARE * 100:g} % of its {ex['rating_A']:g} A rating")
        out[ex["key"]] = dict(
            kind="export_current", ref=ref, rail=r, rating_A=ex["rating_A"], assumed_A=a,
            assumed_share=None if ex.get("from_feed") else EXPORT_SHARE, from_feed=ex.get("from_feed"),
            band_A=[ex["lo_A"], ex["hi_A"]], field=f"parts.{ref}.I_A",
            also=f"parts.{ref}.I_sustained_A", might_differ=why, priority="high" if why else "normal",
            ask=(f"{ref} exports {r} off the board and the facts do not state its current; assumed "
                 f"{a * 1e3:.3g} mA ({how}). What does it carry? "
                 f"State parts.{ref}.I_A in A (a value or [lo, hi]; I_sustained_A for the typical draw), "
                 f"or 0 if only signals or nothing draw from it."))
    return out


def _pads(board):
    """{ref: [(number, net, pintype, pinfunction)]}. Footprints that share a reference are one part (a module's
    edge pins and its back pins, a split symbol): their pads are merged, as the copper model's pad tokens (REF.NUM,
    haslam.em.kicad) merge them. Keeping only the last footprint lost a Teensy's supply and ground pins.

    One pin is one entry: pads that share a number and net (a SOT-223's or DPAK's tab beside its pin, an exposed pad
    drawn as several pads, a THT pin on two layers) are one terminal of the copper model (REF.NUM, its copper on
    every pad: the field solve splits the pin's current over them by their conductance), so they are listed once.
    Listed twice, every token list built from them named the pin twice: a regulator's output `[U4.2, U4.2]` summed
    its injection twice in its heat (2x the loss of a SOT-223 LDO), and a part's supply pads were over-counted in its
    rails' shares. The entry keeps the first non-empty pin type and function among the pads."""
    out, at = {}, {}
    for f in board.footprints:
        out.setdefault(f.ref, [])            # a part with no pad on a net is still a part (no copper of its own)
        for p in f.pads:
            if not p.net:
                continue
            e = (p.number, p.net, p.pintype or "", (p.pinfunction or "").split("/")[0].strip())
            k = (f.ref, p.number, p.net)
            if k in at:
                lst, i = at[k]
                n0, nt0, pt0, fn0 = lst[i]
                lst[i] = (n0, nt0, pt0 or e[2], fn0 or e[3])
                continue
            lst = out[f.ref]
            at[k] = (lst, len(lst))
            lst.append(e)
    return out


def merge_buckboost(cells):
    """A 4-switch buck-boost (LTC3130, TPS63xxx) as one cell, in place. haslam.circuit finds a buck cell (the input
    switches, SW1) and a boost cell (the output switches, SW2) on one controller and one inductor between the two
    switch nodes. At DC it is one converter: the inductor current leaves the controller at SW1 and comes back at
    SW2 (the inductor joins the two, not SW1 to the output), and the output switches deliver the output current at
    the controller's output pins. Taken as two cells, the buck's current entered SW1 and had no way out."""
    for a in list(cells.values()):
        bst = next((c for c in cells.values() if a["cls"] == "buck" and c["cls"] == "boost" and c["ctrl"] == a["ctrl"]
                    and c.get("ind") and c.get("ind") == a.get("ind") and c["sw"] != a["sw"]
                    and (c["vin"], c["vout"]) == (a["vin"], a["vout"])), None)
        if bst is not None and a["id"] in cells and bst["id"] in cells:
            a.update(cls="buckboost", sw2=bst["sw"], src2=bst["src"], rect=None)
            a["parts"] |= bst["parts"]
            del cells[bst["id"]]
    return cells


def plan(board, brief, bd, P, srcs, intent=None):
    """The DC plan from the brief (rails, sources, cells), the circuit model's ground set and the AC
    ledger P ({source name: {param: Param}}) for the cells' operating points."""
    from haslam.route.critical_modules import Ctx
    from haslam.route.critical_rails import load_current, source_rating
    ctx = Ctx(None, None, brief, board)
    pl = Plan()
    nets = brief.get("nets") or {}
    parts = brief.get("parts") or {}
    ref_of = {u: p["ref"] for u, p in parts.items()}
    uuid_of = {p["ref"]: u for u, p in parts.items()}
    pads = _pads(board)
    # a part marked do-not-populate (the footprint's dnp attribute, as haslam.circuit reads it) is not on the
    # assembled board: it neither loads, feeds nor returns current (solar-small's J301 'DNP' header was a
    # 0.3 A connector export, heated as a load to 213 C)
    dnp = {p["ref"] for p in parts.values() if p.get("dnp")} | {f.ref for f in board.footprints if "dnp" in (f.attrs or [])}
    for ref in sorted(dnp & set(pads)):
        del pads[ref]
        pl.notes.append(f"{ref}: do not populate; not in the DC band")
    grounds = bd.grounds
    rails = {n for n, d in nets.items() if (d or {}).get("role") == "rail"}
    # the intent's operating facts may name rails the brief did not classify, with their voltage and
    # their regulator: nets.<rail> = {"source": ref, "from": input net, "kind": "linear"|"switching",
    # "eta": [lo, hi], "V_V": volts}
    facts = {n: d for n, d in ((intent or {}).get("nets") or {}).items() if isinstance(d, dict)}
    pad_nets = {p.net for fp in board.footprints for p in fp.pads if p.net}
    rails |= {n for n, d in facts.items() if d.get("source") and n in pad_nets and n not in grounds}
    req = (intent or {}).get("requirements") or {}
    pl.loss_share = float(req.get("copper_loss_share", LOSS_SHARE))
    pl.drop_share = float(req.get("drop_share", DROP_SHARE))
    pl.dT_max = float(req.get("dT_max_K", DT_MAX))

    def tok(ref, nums):
        return [f"{ref}.{n}" for n in nums]

    def gnd_pads(ref):
        return tok(ref, [n for n, net, _, _ in pads.get(ref, []) if net in grounds])

    def on(ref, net, sel=None):
        return tok(ref, [n for n, nt, pt, fn in pads.get(ref, []) if nt == net and (sel is None or sel(pt, fn))])

    def supply(ref, net):
        s = on(ref, net, lambda pt, fn: pt == "power_in" or SUPPLY_PIN.match(fn))
        return s or on(ref, net)

    def volts(net):
        """The rail's voltage with its sign (the operating facts', else the brief's), None unknown."""
        fv = (facts.get(net) or {}).get("V_V")
        if isinstance(fv, (int, float)) and fv != 0:
            return float(fv)
        v = (nets.get(net) or {}).get("volts")
        return float(v) if v else None

    def sgn(net):
        return -1.0 if (volts(net) or 0.0) < 0 else 1.0

    def input_connector(r):
        """Where a rail without a source part is fed: the facts state its voltage (V_V or range_V, an input the
        design expects) and a populated connector with a ground pad has a pad on it (the one with the most
        pads on the rail, then by reference), or on the far side of a series part on it (a reverse-polarity
        transistor or diode, a fuse: solar-small's panel J101 -> PV_RAW -> Q101 -> PV_IN). Returns (connector,
        None) or (connector, (series part, its far net)), else None."""
        fd = facts.get(r) or {}
        if not (isinstance(fd.get("V_V"), (int, float)) or isinstance(fd.get("range_V"), list)):
            return None

        def conn_on(net):
            c = [(-sum(1 for _, nt, _, _ in pp if nt == net), ref) for ref, pp in pads.items()
                 if (parts.get(uuid_of.get(ref)) or {}).get("kind") == "connector"
                 and any(nt == net for _, nt, _, _ in pp) and gnd_pads(ref)]
            return min(c)[1] if c else None
        if conn_on(r):
            return conn_on(r), None
        for ref, pp in sorted(pads.items()):
            if (parts.get(uuid_of.get(ref)) or {}).get("kind") not in SERIES or not any(nt == r for _, nt, _, _ in pp):
                continue
            for n2 in sorted({nt for _, nt, _, _ in pp} - {r} - set(grounds) - rails):
                if conn_on(n2):
                    return conn_on(n2), (ref, n2)
        return None

    # parts the copper model conducts through at DC (haslam.excite.circuit elements of DC_KINDS)
    conducting = {e.name.split(":")[0] for e in (getattr(getattr(bd, "circuit", None), "elems", None) or [])
                  if e.kind in DC_KINDS}
    extra_v = {}                    # a connector's net behind a series part: {net: the rail whose voltage it has}

    # commutation cells: their parts, rails and operating points
    cells = {}
    src_of_cell = {s.meta.get("cell"): s.name for s in srcs if s.kind == "cell"}
    for st in brief.get("structures") or []:
        if st.get("kind") != "commutation_cell" or st.get("class") not in ("boost", "buck", "inverting"):
            continue
        sname = src_of_cell.get(st["id"])
        if sname is None or sname not in P:
            continue
        sw = st.get("switches") or {}
        src_ = next((x for x in srcs if x.name == sname), None)
        eta = (src_.meta.get("eta") if src_ is not None else None) or CV.ETA[1]      # typical (haslam.excite.params)
        c = dict(id=st["id"], cls=st["class"], src=sname, vin=st.get("vin"), vout=st.get("vout"), sw=st.get("sw"),
                 ind=ref_of.get(st.get("inductor")),
                 top=cell_topology(st, nets), eta=float(eta),
                 ctrl=ref_of.get(st.get("controller")), rect=ref_of.get(sw.get("rectifier")),
                 high=ref_of.get(sw.get("high")), low=ref_of.get(sw.get("low")),
                 parts={ref_of.get(u) for u, _ in st.get("loop") or []} | {ref_of.get(st.get("controller")),
                                                                         ref_of.get(st.get("inductor"))})
        c["parts"] |= {ref_of.get(u) for u in st.get("caps") or []}
        if sw.get("in_high") and sw.get("out_high"):
            # a 4-switch buck-boost with external FETs: its DC flow enters and leaves at its high-side FETs' drains
            c["ext"] = {k: ref_of.get(sw.get(k)) for k in ("in_high", "in_low", "out_high", "out_low", "shunt")}
        c["parts"].discard(None)
        cells[st["id"]] = c
    merge_buckboost(cells)
    cell_parts = set().union(*[c["parts"] for c in cells.values()]) if cells else set()
    def fed_on_board(n):
        """Whether rail n's current comes from a converter on the board: a cell's output, a rail whose source part
        (the facts', else the brief's) is an IC or module, or one the facts give as fed from another rail."""
        if any(c["vout"] == n for c in cells.values()) or (facts.get(n) or {}).get("from"):
            return True
        sr = over.get(n) or ref_of.get(((nets.get(n) or {}).get("source") or {}).get("part"))
        return (parts.get(uuid_of.get(sr)) or {}).get("kind") in ("ic", "module")

    def link_of(ref, r):
        """The other rail of connector ref when it is a series link into rail r (no ground pad, its pads on r and
        on exactly one other rail, which an on-board converter feeds), else None."""
        ns = {nt for _, nt, _, _ in pads.get(ref, [])}
        if gnd_pads(ref) or r not in ns or len(ns) != 2:
            return None
        (r2,) = ns - {r}
        return r2 if r2 in rails and r2 not in grounds and fed_on_board(r2) else None
    # feeds: what delivers each rail's current
    over = {n: (d or {}).get("source") for n, d in ((intent or {}).get("nets") or {}).items() if (d or {}).get("source")}
    for r in sorted(rails):
        d = nets.get(r) or {}
        cell = next((c for c in cells.values() if c["vout"] == r), None)
        src_ref = over.get(r) or ref_of.get((d.get("source") or {}).get("part"))
        if cell is not None:
            pl.feeds[r] = dict(kind="cell", cell=cell, ref=cell["ctrl"])
            # the cell's stated or prior current is its operating range: the most it carries (an upper bound on
            # what its loads can draw through it), not a current its loads must take
            pi = next((p for p in (P.get(cell["src"]) or {}).values() if getattr(p, "name", "") == "I_A"), None)
            if pi is not None and pi.hi > 0:
                pl.feeds[r]["I_hi"] = float(pi.hi)
            # the facts' efficiency: the rail's (nets.<rail>.eta), else the cell's own (cells.<id>.eta, which the
            # facts compiler writes). The cell's own was read only as its typical (the ledger's D), so a buck's input
            # current held it at every corner and its heat ignored it (class R_on and C_sw priors instead)
            fe = _eta((facts.get(r) or {}).get("eta"), f"facts.nets.{r}.eta") or \
                _eta((((intent or {}).get("cells") or {}).get(cell["id"]) or {}).get("eta"), f"facts.cells.{cell['id']}.eta")
            if fe:
                # the input takes P_out / eta (without it the cell's duty, lossless)
                pl.feeds[r]["eta"] = Param(f"dc:{cell['ctrl']}", "eta", *fe, "", "intent", "the intent file")
                pl.params.append(pl.feeds[r]["eta"])
            continue
        if src_ref is None or src_ref not in pads:
            fed = input_connector(r)
            if fed is None:
                pl.notes.append(f"{r}: no source part; its loads are not in the DC band")
                continue
            # a rail the facts give a voltage (V_V or range_V) and no source part: the power arrives on the
            # board through a connector on it, or behind a series part (solar-small's panel on J101, through
            # Q101 to PV_IN, whose copper carried no DC while its converter's input current entered at the
            # controller)
            conn, via = fed
            if via is None or via[0] in conducting:
                # on the rail, or behind a part the copper model conducts through (a fuse, a ferrite)
                pl.feeds[r] = dict(kind="external", ref=conn, out=on(conn, via[1] if via else r), gnd=gnd_pads(conn))
            else:
                ser, n2 = via
                pl.feeds[n2] = dict(kind="external", ref=conn, out=on(conn, n2), gnd=gnd_pads(conn))
                pl.feeds[r] = dict(kind="linear", ref=ser, rin=n2, out=on(ser, r), inp=on(ser, n2), gnd=[])
                extra_v[n2] = r
            pl.notes.append(f"{r}: no source part; the facts give its voltage, so it is fed at connector {conn}"
                            + (f" through {via[0]} ({via[1]})" if via else ""))
            continue
        kind, sub = (parts.get(uuid_of.get(src_ref)) or {}).get("kind"), (parts.get(uuid_of.get(src_ref)) or {}).get("subtype")
        fr, fk = (facts.get(r) or {}).get("from"), (facts.get(r) or {}).get("kind")
        ins = [(n, net) for n, net, pt, fn in pads[src_ref] if net in rails and net != r and
               (pt == "power_in" or SUPPLY_PIN.match(fn))] if kind in ("ic", "module") else []
        if kind in ("ic", "module") and fr and fr != r and any(net == fr for _, net, _, _ in pads[src_ref]):
            ins = [(n, net) for n, net, _, _ in pads[src_ref] if net == fr]      # the facts' input net
        if kind in ("ic", "module") and ins:
            # an IC that supplies this rail from another one converts: switching by its class, else linear
            rin = ins[0][1]
            outs = on(src_ref, r, lambda pt, fn: pt == "power_out" or OUT_PIN.match(fn)) or on(src_ref, r)
            fk = (facts.get(r) or {}).get("kind")
            f = dict(kind=fk if fk in ("linear", "switching") else ("switching" if sub in SWITCHING else "linear"),
                     ref=src_ref, rin=rin, out=outs,
                     inp=tok(src_ref, [n for n, net in ins if net == rin]), gnd=gnd_pads(src_ref))
            if f["kind"] == "switching":
                fe = _eta((facts.get(r) or {}).get("eta"), f"facts.nets.{r}.eta")
                if fe:
                    f["eta"] = Param(f"dc:{src_ref}", "eta", *fe, "", "intent", "the intent file")
                else:
                    f["eta"] = Param(f"dc:{src_ref}", "eta", ETA[1], ETA[0], ETA[2], "", "prior",
                                     "efficiency of a switching regulator without a cell model (class range)")
                pl.params.append(f["eta"])
            pl.feeds[r] = f
        elif kind not in ("ic", "module") and fr and fr != r and fk in (None, "linear") and on(src_ref, fr) and on(src_ref, r):
            # the facts give the rail as fed from another one through this part (a load switch, a series pass
            # transistor): its current comes from that rail through the part's channel. Taken as external, a
            # switched rail's loads never reached the rail and regulator upstream (solar-small's +3V3_SW via Q301)
            pl.feeds[r] = dict(kind="linear", ref=src_ref, rin=fr, out=on(src_ref, r), inp=on(src_ref, fr), gnd=[])
        elif kind == "connector" and fk != "external" and link_of(src_ref, r):
            # a connector with no ground pad whose pins land on this rail and one other on-board rail fed by a
            # converter (duanestorey's J10, a 2-pin jumper header from 12V_OUT to 12V) links the two: its current
            # comes from the other rail through it. Read as an external source, the rail's 0.35 A appeared from
            # nowhere and the converter upstream (U7) carried only its own rail's load. The facts say otherwise with
            # nets.<rail>.kind "external" (a cable really brings the rail in on that header)
            other = link_of(src_ref, r)
            pl.feeds[r] = dict(kind="linear", ref=src_ref, rin=other, out=on(src_ref, r), inp=on(src_ref, other), gnd=[])
            pl.notes.append(f"{r}: source {src_ref} is a connector with no ground pad between {r} and {other}, which "
                            f"an on-board converter feeds: a series link from {other}, not the board's input")
        elif kind in ("diode", "inductor", "ferrite", "resistor", "jumper"):
            other = next((net for _, net, _, _ in pads[src_ref] if net != r and net in rails), None)
            if other is None:
                pl.notes.append(f"{r}: series source {src_ref} has no rail on its other side; taken as external")
                pl.feeds[r] = dict(kind="external", ref=src_ref, out=on(src_ref, r), gnd=gnd_pads(src_ref))
            else:
                pl.feeds[r] = dict(kind="linear", ref=src_ref, rin=other, out=on(src_ref, r), inp=on(src_ref, other), gnd=[])
        else:
            if kind in ("ic", "module"):
                pl.notes.append(f"{r}: source {src_ref} has no supply pin on another rail; taken as the board's input")
            out = on(src_ref, r)
            # an input connector through series parts (a fuse, a bead, a reverse-polarity diode: the brief's path,
            # the rail's neighbour first) has no pad on the rail: its current enters the rail at the series part's
            # pad there. Without it the feed delivered nothing and its loads' current had no way in.
            bs = d.get("source") or {}
            path = (bs.get("path_ref") or []) if ref_of.get(bs.get("part")) == src_ref else []
            if not out and path and on(path[0], r):
                out = on(path[0], r)
                pl.notes.append(f"{r}: source {src_ref} reaches it through {', '.join(path)}; its current enters at "
                                f"{path[0]}'s pad on {r}")
            pl.feeds[r] = dict(kind="external", ref=src_ref, out=out, gnd=gnd_pads(src_ref))
    # feeds that feed each other in a cycle (AMP_VDD from PCM_AVDD through U2, PCM_AVDD from AMP_VDD through U2: an
    # intent fact read the regulator backwards) have no way in for their current, and the DC flow cannot close.
    # Power cannot circulate among regulators, so one link is wrong: the one whose part's pins least say it outputs on
    # its rail and takes its input from the other (power_out or an OUT name there, power_in or an IN name on its input)
    # is dropped, the intent's fact before the brief's; the rail it fed is then fed by a connector on it with a ground
    # pad (the board's way in), else by nothing.
    def evidence(r, f):
        f = dict(f, rin=f.get("rin") or (f.get("cell") or {}).get("vin"))
        out_ = sum(1 for _, nt, pt, fn in pads.get(f["ref"], []) if nt == r and (pt == "power_out" or OUT_PIN.match(fn)))
        in_ = sum(1 for _, nt, pt, fn in pads.get(f["ref"], []) if nt == f.get("rin") and (pt == "power_in" or SUPPLY_PIN.match(fn)))
        bad = sum(1 for _, nt, pt, fn in pads.get(f["ref"], []) if nt == r and (pt == "power_in" or SUPPLY_PIN.match(fn)))
        return (bool(out_) + bool(in_) - bool(bad), r not in over)
    for _ in range(len(pl.feeds)):
        cyc = None
        for r0 in sorted(pl.feeds):
            seen, x = [], r0
            while x in pl.feeds and x not in seen and pl.feeds[x]["kind"] in ("linear", "switching", "cell"):
                seen.append(x)
                # a cell's input is its cell's (a boost from +3V3 to +5V beside an LDO from +5V to +3V3 is a cycle too)
                x = pl.feeds[x]["cell"]["vin"] if pl.feeds[x]["kind"] == "cell" else pl.feeds[x].get("rin")
            if x == r0 and seen:
                cyc = seen
                break
        if not cyc:
            break
        r = min(cyc, key=lambda q: (evidence(q, pl.feeds[q]), q))
        f = pl.feeds.pop(r)
        if f["kind"] == "cell":
            f = dict(f, rin=f["cell"]["vin"])
        conns = [(sum(1 for _, nt, _, _ in pp if nt == r), ref) for ref, pp in pads.items()
                 if (parts.get(uuid_of.get(ref)) or {}).get("kind") == "connector" and any(nt == r for _, nt, _, _ in pp)
                 and gnd_pads(ref)]
        if conns:
            ref = max(conns)[1]
            pl.feeds[r] = dict(kind="external", ref=ref, out=on(ref, r), gnd=gnd_pads(ref))
        pl.notes.append(f"{r}: feeds {' -> '.join(cyc)} form a cycle with no way in; {f['ref']} as {r}'s source from "
                        f"{f.get('rin')} contradicts its pins most and is dropped"
                        + (f"; {pl.feeds[r]['ref']} (a connector on it) feeds it" if r in pl.feeds else ""))
    # a linear regulator passes its output current through from its input, so both rails have one sign: one between
    # rails of opposite signs (a fact or a brief that read an inverter as linear) has no input current it could pass
    # on. Its flow enters the board at it, as a regulator's whose input has no feed does, and the note says why.
    for r, f in pl.feeds.items():
        if f["kind"] == "linear" and volts(r) and volts(f.get("rin")) and sgn(r) != sgn(f["rin"]):
            f["flow_external"] = True
            f["gnd"] = f.get("gnd") or gnd_pads(f["ref"])
            pl.notes.append(f"{r}: {f['ref']} is linear from {f['rin']}, a rail of the opposite sign, which no linear "
                            f"regulator does; the DC flow enters at {f['ref']}")
    for c in cells.values():
        if _top(c) not in ("inverting_buck_boost", "inverting_buck") and volts(c["vin"]) and volts(c["vout"]) \
                and sgn(c["vin"]) != sgn(c["vout"]):
            pl.notes.append(f"{c['vout']}: {c['id']} runs between rails of opposite signs as a {_top(c)}; its DC flow is "
                            f"taken as its output's mirror image")
    # a feed with no pad on its rail delivers nowhere (a fact naming a source part with no pad there): it is no feed,
    # and its rail's loads are not in the band (before, its loads' current was dropped and the plan did not balance)
    for r in [r for r, f in pl.feeds.items() if f["kind"] != "cell" and not f.get("out")]:
        f = pl.feeds.pop(r)
        pl.notes.append(f"{r}: source {f['ref']} has no pad on it; its loads are not in the DC band")
    # a regulator or cell whose input net has no feed of its own: the DC flow enters the board at it (its input
    # current has nowhere to come from in the copper); its loss still comes from its input's voltage. A feed left
    # out further down (no ground anywhere) can leave another's input without a feed, so this runs again then (a
    # cell whose input lost its feed that way walked its current into a rail with no feed, unbalanced)
    def rin_of(f):
        return f["cell"]["vin"] if f["kind"] == "cell" else f.get("rin")

    def mark_unfed():
        for r, f in pl.feeds.items():
            if f["kind"] in ("linear", "switching", "cell") and not f.get("flow_external") and rin_of(f) not in pl.feeds:
                f["flow_external"] = True
                if f["kind"] == "cell":
                    c = f["cell"]
                    # the input current enters at the cell's input: a boost's inductor (its input is the inductor's
                    # current), else the controller's input pins (or an external-FET leg's high side)
                    ent = (c.get("ext") or {}).get("in_high") or (c["ind"] if _top(c) in ("boost", "boost_led") else None)
                    f["entry"] = on(ent, c["vin"]) if ent and on(ent, c["vin"]) else on(c["ctrl"], c["vin"])
                    f["gnd"] = gnd_pads(c["ctrl"])
                else:
                    f["gnd"] = f.get("gnd") or gnd_pads(f["ref"])
                pl.notes.append(f"{r}: {f['ref']}'s input {rin_of(f)} has no feed; the DC flow enters at {f['ref']}")
    mark_unfed()
    # an external feed returns at its own ground pads, else at the connectors' (the board's way out)
    conn_g = [t for ref, pp in pads.items() if (parts.get(uuid_of.get(ref)) or {}).get("kind") == "connector"
              for t in tok(ref, [n for n, net, _, _ in pp if net in grounds])]
    # a switching regulator's input current differs from its output current: the difference returns through its
    # ground. One with no ground pad is an inverter whose GND pin is its negative rail (TI SLVA721): the difference
    # (its input current plus its output's magnitude) leaves its switch pin through the inductor to ground, so it
    # returns at its pads on a net an inductor or bead joins to a ground; else at the connectors' ground
    net_at = {f"{ref}.{n}": net for ref, pp in pads.items() for n, net, _, _ in pp}
    to_gnd = {}
    for e in bd.circuit.elems:
        a_, b_ = net_at.get(e.pa), net_at.get(e.pb)
        if e.kind in ("L", "FB") and a_ and b_ and (a_ in grounds) != (b_ in grounds):
            to_gnd.setdefault(b_ if a_ in grounds else a_, []).append(e.name)
    for r, f in pl.feeds.items():
        if f["kind"] == "switching" and not f["gnd"]:
            ret = [(n, net) for n, net, _, _ in pads.get(f["ref"], []) if net in to_gnd and net not in (r, f.get("rin"))]
            if ret:
                f["gnd"] = tok(f["ref"], [n for n, _ in ret])
                pl.notes.append(f"{r}: {f['ref']} has no ground pad; its return leaves at {', '.join(f['gnd'])} through "
                                f"{', '.join(sorted({x for _, net in ret for x in to_gnd[net]}))} to ground")
    changed = True
    while changed:
        changed = False
        for r in list(pl.feeds):
            f = pl.feeds[r]
            if (f["kind"] in ("external", "switching") or f.get("flow_external")) and not f["gnd"]:
                if conn_g:
                    f["gnd"] = conn_g
                    pl.notes.append(f"{r}: source {f['ref']} has no ground pad; its return is taken at the connectors' ground")
                else:
                    del pl.feeds[r]
                    changed = True
                    pl.notes.append(f"{r}: source {f['ref']} has no ground pad and the board no connector ground; left out")
        if changed:
            mark_unfed()
    # what each feed can deliver (its class rating, E5): a source current-limits, so no corner draws more
    for r, f in pl.feeds.items():
        if f["kind"] != "cell":
            f["rating"] = source_rating(ctx, uuid_of.get(f["ref"]), r, {})
    feeders = {f["ref"] for f in pl.feeds.values()}

    def consumer(ref):
        p = parts.get(uuid_of.get(ref)) or {}
        k, sb = p.get("kind"), p.get("subtype")
        return (k == "module" and sb not in LINEAR + SWITCHING + ("charge_pump",)) or (k == "ic" and sb in CONSUMER_SUB)

    def by_rail(ref):
        """{rail: value} the facts state per rail for part ref (parts.<ref>.I_A_by_rail)."""
        v = (((intent or {}).get("parts") or {}).get(ref) or {}).get("I_A_by_rail")
        return v if isinstance(v, dict) else {}

    def part_share(ref, r, skip=None):
        """Rail r's share of part ref's supply pads over the fed rails it draws from (not one it feeds, nor `skip`,
        nor one whose current the facts state on its own: parts.<ref>.I_A_by_rail)."""
        own = set(by_rail(ref))
        n = {r2: len(supply(ref, r2)) for r2 in pl.feeds if pl.feeds[r2].get("ref") != ref and r2 != skip
             and r2 not in own and any(net == r2 for _, net, _, _ in pads.get(ref, []))}
        return n.get(r, 0) / sum(n.values()) if sum(n.values()) else 1.0
    # loads: parts that draw from a rail and return at their own ground
    # an export through a connector without a ground pad of its own returns through the board's other connectors'
    # grounds (a stack connector carries the rail, its mate the ground)
    conn_g_all = conn_g
    for r in sorted(pl.feeds):
        for ref, pp in pads.items():
            if ref in feeders and pl.feeds[r]["ref"] == ref or ref in cell_parts or ref in feeders and not consumer(ref) and any(
                    f.get("rin") == r and f["ref"] == ref for f in pl.feeds.values()):
                continue
            if not any(net == r for _, net, _, _ in pp):
                continue
            u = uuid_of.get(ref)
            kind = (parts.get(u) or {}).get("kind")
            if kind not in LOAD_KINDS:
                continue
            g = gnd_pads(ref)
            stated = ((intent or {}).get("parts") or {}).get(ref, {}).get("I_A") is not None or r in by_rail(ref)
            if not g and kind == "connector" and stated and conn_g_all:
                g = [t for t in conn_g_all if not t.startswith(ref + ".")]
                if g:
                    pl.notes.append(f"{r}: export {ref} has no ground pad; its return is taken at the other connectors' ground")
            ret = None
            split = kind in ("ic", "module") and any(nt in pl.feeds and sgn(nt) < 0 for _, nt, _, _ in pp) and \
                any(nt in pl.feeds and sgn(nt) > 0 for _, nt, _, _ in pp)
            if split:
                # a part across a positive and a negative rail returns at a ground pad only through a ground pin: an
                # op-amp's non-inverting input tied to ground (a pin typed input) carries no supply current, and read
                # as its return it sent the op-amp's current into ground instead of into the negative rail
                g = [t for t, (_, nt, pt, _) in zip(tok(ref, [q[0] for q in pp]), pp) if nt in grounds and pt not in SIGNAL_PINS]
            if not g and split and sgn(r) > 0:
                # a split-supply part with no ground pin (an op-amp across +-12 V): its current runs from the positive
                # rail through it into the negative one, and none of it through ground. Without this it was no load.
                # Seen from its negative rail it is this same load (no ground pad there either: skipped below)
                negs = sorted(net for net in {nt for _, nt, _, _ in pp} if net in pl.feeds and sgn(net) < 0)
                if negs:
                    ret = max(negs, key=lambda n: (len(supply(ref, n)), n))
                    g = supply(ref, ret)
            if not g:
                continue
            iv = ((intent or {}).get("parts") or {}).get(ref, {}).get("I_A")
            if kind in LOAD_PRIOR:
                a = LOAD_PRIOR[kind] if supply(ref, r) and draws_from(pp, r, rails) or kind == "oscillator" else 0.0
            else:
                a = load_current(ctx, u, r, {}, draws=draws_from(pp, r, rails) if kind in ("ic", "module") else None)
            rating = a if kind == "connector" else None
            if kind == "connector":
                a = EXPORT_SHARE * a                 # an export: 1 % of its rating unless the facts say (EXPORT_SHARE)
            if a <= 0:
                continue
            ld = dict(ref=ref, rail=r, sup=supply(ref, r), gnd=g, prior=a)
            if ret:
                ld["ret"] = ret          # its return rail: its current leaves there, into that rail's feed
            # the intent states a part's whole current: on several rails it is split by their share of the part's
            # supply pads (an MCU's 3V3 pins carry its current, not its VBUS-detect pin as well); a split-supply
            # part's whole current crosses both its rails
            ld["part_share"] = share = part_share(ref, r, skip=ret)
            what = f"facts.parts.{ref}.I_A"
            if r in by_rail(ref):
                # the facts state this rail's current on its own (a connector exporting 5V and 3V3 to a board that
                # draws them unequally): no share of the part's whole current. Split by supply pads, J7's 5V and
                # 3V3 exports could only be stated equal
                iv, share, what = by_rail(ref)[r], 1.0, f"facts.parts.{ref}.I_A_by_rail.{r}"
                ld["part_share"] = 1.0
                ld["by_rail"] = True
            sub = (parts.get(u) or {}).get("subtype")
            tab = lookup_part(f"{(parts.get(u) or {}).get('value') or ''} {(parts.get(u) or {}).get('lib_id') or ''}") \
                if kind in ("ic", "module") else {}
            # every load draws its own current, whatever feeds its rail: a converter cell's output is what its
            # loads take (haslam.excite.heat sets its operating current from them), not a current its rail's loads
            # share out (solar-small's LTC2959 coulomb counter, < 1 uA, took the whole LTC3130 output: 1.5 W)
            if iv is not None:
                typ, lo, hi = (x * share for x in fact_interval(iv, what))
                p = Param(f"dc:{ref}@{r}", "I_A", typ, lo, hi, "A", "intent",
                          "the intent file" + (f" ({share:.0%} of the part's current: its share of supply pads)" if share < 1 else "")
                          + (" (its current on this rail)" if ld.get("by_rail") else ""))
            elif "I_supply_A" in tab:
                typ, lo, hi, src = tab["I_supply_A"]
                p = Param(f"dc:{ref}@{r}", "I_A", typ * share, lo * share, hi * share, "A", "part_table", src)
            elif kind == "ic" and sub in MONITOR_SUB:
                lo, hi = MONITOR_A
                p = Param(f"dc:{ref}@{r}", "I_A", math.sqrt(lo * hi), lo, hi, "A", "prior",
                          f"{sub} IC supply current (sense, monitor and data-converter ICs draw uA to mA; class range)")
            elif kind == "connector":
                lo, hi = a * EXPORT_BAND[0], a * EXPORT_BAND[1]
                p = Param(f"dc:{ref}@{r}", "I_A", a, lo, hi, "A", "prior",
                          f"connector export not stated by the facts: {EXPORT_SHARE * 100:g} % of its {rating:g} A rating "
                          f"({lo / rating * 100:.3g} % .. {hi / rating * 100:.3g} %); state parts.{ref}.I_A")
            else:
                p = Param(f"dc:{ref}@{r}", "I_A", a, a / 3, 3 * a, "A", "prior", f"{kind} load current by class (E5) x/3 .. x3")
            pl.params.append(p)
            ld["key"] = (p.subject, p.name)
            pl.loads.append(ld)
            if kind == "connector" and p.source == "prior":
                pl.exports_assumed.append(dict(ref=ref, rail=r, key=ld["key"], rating_A=rating, assumed_A=a,
                                               lo_A=p.lo, hi_A=p.hi))
    # a regulator's own stated draw (parts.<ref>.I_A on a part that feeds a rail and is no consumer) has no place in
    # this plan: its ground current is not modelled, and the facts compiler also writes a charger's charge current
    # there, so it cannot be read as a quiescent current. It was dropped without a word; now it is said
    unused = sorted(ref for ref in feeders if not consumer(ref) and ((intent or {}).get("parts") or {}).get(ref, {})
                    .get("I_A") is not None and not any(ld["ref"] == ref for ld in pl.loads))
    if unused:
        pl.notes.append("facts parts.<ref>.I_A not used for a regulator's own draw (its quiescent current is not in the "
                        "DC band): " + ", ".join(unused))
    # self-powered consumers: a part that sources a rail from off the board (its own USB or battery) and draws
    # its own current there: no DC flow in the carrier's copper, but its own dissipation heats the board
    pl.self_loads = []
    for ref in sorted({f["ref"] for f in pl.feeds.values() if f["kind"] == "external" and f.get("ref")}):
        if not consumer(ref) or any(ld["ref"] == ref for ld in pl.loads):
            continue
        fed = [r for r, f in pl.feeds.items() if f["kind"] == "external" and f.get("ref") == ref]
        r = max(fed, key=lambda n: (volts(n) or 0.0, n))
        u = uuid_of.get(ref)
        iv = ((intent or {}).get("parts") or {}).get(ref, {}).get("I_A")
        if iv is not None:
            p = Param(f"dc:{ref}@{r}", "I_A", *fact_interval(iv, f"facts.parts.{ref}.I_A"), "A", "intent",
                      "the intent file (the part's own draw, from its own input)")
        else:
            a = load_current(ctx, u, r, {}, draws=True)
            if a <= 0:
                continue
            p = Param(f"dc:{ref}@{r}", "I_A", a, a / 3, 3 * a, "A", "prior",
                      f"{(parts.get(u) or {}).get('kind')} own draw by class (E5) x/3 .. x3")
        pl.params.append(p)
        mine = [t for n, net, _, _ in pads.get(ref, []) for t in tok(ref, [n]) if net in fed or net in grounds]
        pl.self_loads.append(dict(ref=ref, rail=r, key=(p.subject, p.name), pads=mine or tok(ref, [n for n, _, _, _ in pads.get(ref, [])])))
        pl.notes.append(f"{r}: {ref} powers itself from off the board; its own draw heats it but flows in no carrier copper")
    for ex in pl.exports_assumed:
        ex["only_load"] = all(ld["ref"] == ex["ref"] for ld in pl.loads if ld["rail"] == ex["rail"])

    def feed_output(r, seen=()):
        """(typ, lo, hi, source, basis) of the current rail r's feed is stated or ledgered to deliver, None without
        one: a cell's output from its operating current (the facts' cells.<id>.I_out_A, else its ledger I_A, the
        commutated current, through its topology at its typical duty), a charger's from parts.<ref>.I_A (what the
        facts compiler writes for a charger: its charge current). A rail fed through a series part (a blocking diode,
        a fuse) from a rail that feeds nothing else and has no load of its own carries that rail's feed's current."""
        f = pl.feeds.get(r) or {}
        rin = f.get("rin")
        if f.get("kind") == "linear" and rin and rin not in seen and \
                (parts.get(uuid_of.get(f.get("ref"))) or {}).get("kind") in SERIES + ("connector",) and \
                not any(ld["rail"] == rin or ld.get("ret") == rin for ld in pl.loads) and \
                [r2 for r2, f2 in pl.feeds.items() if (f2["cell"]["vin"] if f2["kind"] == "cell" else f2.get("rin")) == rin] == [r]:
            up = feed_output(rin, seen + (r,))
            if up is not None:
                return (*up[:4], f"{up[4]}, through {f['ref']}")
        if f.get("kind") == "cell":
            c = f["cell"]
            sid = c["id"]
            io = (((intent or {}).get("cells") or {}).get(sid) or {}).get("I_out_A")
            if io is not None:
                return (*fact_interval(io, f"facts.cells.{sid}.I_out_A"), "intent", f"facts.cells.{sid}.I_out_A")
            ps = {getattr(p, "name", ""): p for p in (P.get(c["src"]) or {}).values()}
            pi = ps.get("I_A")
            if pi is None or pi.hi <= 0:
                return None
            D = min(max(ps["D"].typ if "D" in ps else 0.5, 0.02), 0.98)
            if c["cls"] == "buckboost":
                # I_L is the output current bucking, the input current boosting (as _cell_cap)
                vo, vi = abs(volts(r) or 0.0), abs(volts(c["vin"]) or 0.0)
                k = max(1.0, vo / (c.get("eta", 1.0) * vi)) if vo and vi else 1.0
                vals = [x / k for x in (pi.typ, pi.lo, pi.hi)]
            else:
                vals = [CV.output_from_inductor(_top(c), x, D) for x in (pi.typ, pi.lo, pi.hi)]
            return (*vals, pi.source, f"{sid}'s operating current ({pi.source}: {pi.basis})")
        ref = f.get("ref")
        if f.get("kind") in ("linear", "switching") and (parts.get(uuid_of.get(ref)) or {}).get("subtype") == "charger":
            iv = (((intent or {}).get("parts") or {}).get(ref) or {}).get("I_A")
            if iv is not None:
                return (*fact_interval(iv, f"facts.parts.{ref}.I_A"), "intent", f"facts.parts.{ref}.I_A (its charge current)")
        return None

    # A rail whose only loads are connector exports the facts do not state carries what its feed delivers, not 1 % of
    # the connectors' rating: a converter or charger on the board exists to power them (obd-solar's LTC3115-1 into
    # its USB-C receptacle read 30 mA, so 0.127 mm on its 3.5 A path read 0 K). The feed's current is split over the
    # exports by their rating (EXPORT_FROM_FEED says which feed currents count).
    if EXPORT_FROM_FEED != "off":
        by_key = {(p.subject, p.name): i for i, p in enumerate(pl.params)}
        for r in sorted({ex["rail"] for ex in pl.exports_assumed}):
            exs = [ex for ex in pl.exports_assumed if ex["rail"] == r]
            if any(ld["rail"] == r and not any(ld["key"] == ex["key"] for ex in exs) for ld in pl.loads):
                continue        # another load on the rail (an IC, a stated export): the 1 % prior stands
            if any(ld.get("ret") == r for ld in pl.loads) or any(
                    (f2["cell"]["vin"] if f2["kind"] == "cell" else f2.get("rin")) == r for f2 in pl.feeds.values()):
                continue        # it feeds a regulator or a split-supply load returns into it: drawn otherwise
            fo = feed_output(r)
            if fo is not None and EXPORT_FROM_FEED == "band":
                # the feed's current bounds the exports from above (as a cell's I_A bounds its rail's loads): the
                # band's top rises to it, the typical stays the 1 % prior, so the copper's worst corner (drop, track
                # heating) sees what the converter can deliver while temperatures, which take a prior export at its
                # typical (haslam.excite.heat), are not raised by a guess
                tot = sum(ex["rating_A"] for ex in exs) or 1.0
                for ex in exs:
                    k = ex["rating_A"] / tot
                    old = pl.params[by_key[ex["key"]]]
                    hi = max(old.hi, fo[2] * k)
                    if hi > old.hi:
                        pl.params[by_key[ex["key"]]] = Param(old.subject, "I_A", old.typ, old.lo, hi, "A", old.source,
                                                             old.basis + f"; its top is what {pl.feeds[r]['ref']} delivers "
                                                             f"({fo[2] * k:.3g} A, {fo[4]}): its rail's only loads are exports")
                        ex.update(hi_A=hi, feed_top_A=fo[2] * k)
                pl.notes.append(f"{r}: its only loads are unstated exports ({', '.join(ex['ref'] for ex in exs)}); their "
                                f"band reaches what {pl.feeds[r]['ref']} delivers ({fo[2]:.3g} A; {fo[3]}), the typical stays "
                                f"{EXPORT_SHARE * 100:g} % of their rating")
                continue
            if fo is not None and EXPORT_FROM_FEED == "stated" and fo[3] != "intent":
                # the converter's current is a class prior too: the 1 % stands, and the evaluation says what to state
                pl.notes.append(f"{r}: its only loads are unstated exports ({', '.join(ex['ref'] for ex in exs)}) and "
                                f"{pl.feeds[r]['ref']}'s current is a {fo[3]} ({fo[0]:.3g} A): they are taken at "
                                f"{EXPORT_SHARE * 100:g} % of their rating; state parts.<ref>.I_A or the converter's I_A")
                for ex in exs:
                    ex["feed_prior_A"] = fo[0]
                continue
            if fo is None:
                continue
            typ, lo, hi, src, basis = fo
            tot = sum(ex["rating_A"] for ex in exs) or 1.0
            for ex in exs:
                k = ex["rating_A"] / tot
                old = pl.params[by_key[ex["key"]]]
                p = Param(old.subject, "I_A", typ * k, lo * k, hi * k, "A", src,
                          f"its rail {r}'s only load{'s are' if len(exs) > 1 else ' is'} unstated export"
                          f"{'s' if len(exs) > 1 else ''}: what {pl.feeds[r]['ref']} delivers, {basis}"
                          + (f" ({k:.0%} of it: its share of the exports' rating)" if k < 1 else ""))
                pl.params[by_key[ex["key"]]] = p
                ex.update(assumed_A=p.typ, lo_A=p.lo, hi_A=p.hi, from_feed=pl.feeds[r]["ref"])
            pl.notes.append(f"{r}: its only loads are unstated exports ({', '.join(ex['ref'] for ex in exs)}); they take "
                            f"what {pl.feeds[r]['ref']} delivers ({typ:.3g} A, {lo:.3g} .. {hi:.3g}; {src})")
    # A charger with nothing on its rail charges a battery off the board: a converter rail that nothing draws from,
    # joined by one series part (a blocking FET or diode, a sense resistor) to a rail an external source feeds (the
    # battery's connector), delivers its current through that part into the source. obd-solar's CN3767 (CHG_OUT ->
    # Q203 -> VBAT -> F101 -> J101, the car's battery): its whole charge path carried no current. The battery takes it
    # at its feed pads and gives it back at its ground pads; the series part passes it (lumped, as a linear feed's).
    if CHARGE_SINKS:
        loaded = {ld["rail"] for ld in pl.loads} | {ld.get("ret") for ld in pl.loads}
        fed_from = {(f2["cell"]["vin"] if f2["kind"] == "cell" else f2.get("rin")) for f2 in pl.feeds.values()}
        for r in sorted(pl.feeds):
            f = pl.feeds[r]
            if r in loaded or r in fed_from or f.get("flow_external"):
                continue
            if f["kind"] != "cell" and (parts.get(uuid_of.get(f.get("ref"))) or {}).get("subtype") != "charger":
                continue
            fo = feed_output(r)
            if fo is None:
                continue
            own_parts = (f["cell"]["parts"] if f["kind"] == "cell" else {f["ref"]})
            # a charge path into a battery runs through a blocking part (obd-solar's Q203, a Schottky); a resistor,
            # jumper, bead or fuse between a converter and a connector's rail joins one rail (antmicro sdi-mipi's
            # U7 -> R40 -> +3V3, whose J7 the brief reads as its source: read as a charge, 1.6 A into J7). A charger
            # IC's output may reach its battery through any series part
            is_charger = (parts.get(uuid_of.get(f.get("ref"))) or {}).get("subtype") == "charger"
            kinds = SERIES if is_charger else CHARGE_PATH
            cands = []
            for ref, pp in sorted(pads.items()):
                if ref in own_parts or (parts.get(uuid_of.get(ref)) or {}).get("kind") not in kinds:
                    continue
                ns = {nt for _, nt, _, _ in pp}
                if r not in ns:
                    continue
                for r2 in sorted(ns - {r} - set(grounds)):
                    b = pl.feeds.get(r2) or {}
                    if b.get("kind") == "external" and b.get("out") and b.get("gnd") and on(ref, r2) and \
                            (parts.get(uuid_of.get(b.get("ref"))) or {}).get("kind") in ("connector", "battery"):
                        cands.append((-len(on(ref, r)), ref, r2))
            if len(cands) != 1:
                if cands:
                    pl.notes.append(f"{r}: {f['ref']} has no load and reaches {len(cands)} external sources through series "
                                    f"parts ({', '.join(c_[1] for c_ in cands)}); which one it charges is not known")
                continue
            _, ser, r2 = cands[0]
            b = pl.feeds[r2]
            typ, lo, hi, src, basis = fo
            p = Param(f"dc:{b['ref']}@{r}", "I_A", typ, lo, hi, "A", src,
                      f"{f['ref']} charges the source on {r2} ({b['ref']}) through {ser}: {basis}")
            pl.params.append(p)
            if ser in conducting:
                # a part the copper model conducts through (a Schottky, a sense resistor, a fuse): the current reaches
                # the source through it in the copper itself
                ld = dict(sup=list(b["out"]))
            else:
                ld = dict(sup=on(ser, r), through=(on(ser, r2), list(b["out"])))
            pl.loads.append(dict(ld, ref=b["ref"], rail=r, gnd=list(b["gnd"]), prior=typ, part_share=1.0,
                                 key=(p.subject, p.name), charge=r2))
            pl.notes.append(f"{r}: no load of its own; {f['ref']} charges the external source {b['ref']} on {r2} "
                            f"through {ser} ({typ:.3g} A, {lo:.3g} .. {hi:.3g}; {src})")
    share = [ex for ex in pl.exports_assumed if not ex.get("from_feed")]
    if share:
        pl.notes.append(f"connector exports the facts do not state, assumed at {EXPORT_SHARE * 100:g} % of their rating: "
                        + ", ".join(f"{ex['ref']}@{ex['rail']} {ex['assumed_A'] * 1e3:.3g} mA" for ex in share[:12])
                        + (f" (+{len(share) - 12} more)" if len(share) > 12 else ""))
    # a cell's rail with no load of its own still carries current when a regulator it feeds (or a split-supply load
    # returning into it) draws: deliver() walks that current back through the cell. Only a rail that nothing draws
    # from, directly or through what it feeds, leaves the cell's DC flow out of the model.
    def drawn(r, seen=()):
        if r in seen:
            return False
        if any(ld["rail"] == r or ld.get("ret") == r for ld in pl.loads):
            return True
        return any(drawn(r2, seen + (r,)) for r2, f2 in pl.feeds.items() if r2 != r and
                   (f2["cell"]["vin"] if f2["kind"] == "cell" else f2.get("rin")) == r and not f2.get("flow_external"))
    for r, f in pl.feeds.items():
        if f["kind"] == "cell" and not drawn(r):
            pl.notes.append(f"{r}: fed by {f['cell']['id']}, but nothing draws from it (no load with a ground pad, no "
                            f"regulator fed from it); the cell's DC flow is not modelled")
    pl.dc_pads = {t for ld in pl.loads for t in ld["sup"] + ld["gnd"] + [x for xs in ld.get("through") or () for x in xs]} \
        | {t for sl in pl.self_loads for t in sl["pads"]}
    for r, f in pl.feeds.items():
        # a cell carries current only when something draws from its rail; the pads only its current uses (an
        # external FET's, an unfed input's entry and return) join the DC terminals only then: a terminal no current
        # uses still changes the copper model (its pad made one equipotential)
        live = f["kind"] != "cell" or drawn(r)
        for k in ("out", "gnd", "inp", "entry") if live else ("out", "inp"):
            pl.dc_pads |= set(f.get(k) or [])
        if f["kind"] == "cell":
            c = f["cell"]
            for ref in (c["ctrl"], c["rect"], *((c.get("ext") or {}).values())):
                if ref:
                    pl.dc_pads |= {f"{ref}.{n}" for n, net, _, _ in pads.get(ref, [])
                                   if net in rails or net in grounds or net in (c["sw"], c.get("sw2"))}
            if live and not any(nt == c["sw"] for _, nt, _, _ in pads.get(c["ctrl"], [])):
                # an external switch FET carries the switch current (injections()): its drain, source and input pads
                if _top(c) in ("boost", "boost_led") and c.get("low"):
                    pl.dc_pads |= set(tok(c["low"], [n for n, nt, _, _ in pads.get(c["low"], []) if nt == c["sw"]]))
                    pl.dc_pads |= set(_fet_source(pads, c["low"], c["sw"]))
                elif _top(c) not in ("boost", "boost_led") and c.get("high"):
                    pl.dc_pads |= set(tok(c["high"], [n for n, nt, _, _ in pads.get(c["high"], [])
                                                      if nt in (c["sw"], c["vin"])]))
            if _top(c) == "inverting_buck_boost" and c.get("ind"):
                pl.dc_pads |= {f"{c['ind']}.{n}" for n, net, _, _ in pads.get(c["ind"], []) if net in grounds}
    pl.pads = pads
    pl.grounds = grounds
    pl.volts = {r: volts(r) for r in rails}
    pl.volts.update({n: volts(n) or pl.volts.get(r) for n, r in extra_v.items()})
    _offboard(pl, bd, P, cells, {ref for ref in pads if (parts.get(uuid_of.get(ref)) or {}).get("kind") == "connector"})
    return pl


def _pieces(pads, elems):
    """{pad token: piece}: the nets joined by the parts that conduct at DC (DC_KINDS), each net taken as one
    piece of copper (whether its copper is whole is the field solve's question), named by their first net."""
    net_at = {f"{ref}.{n}": net for ref, pp in pads.items() for n, net, _, _ in pp}
    par = {}

    def root(x):
        while par.get(x, x) != x:
            x = par[x]
        return x
    for e in elems:
        if e.kind in DC_KINDS and net_at.get(e.pa) and net_at.get(e.pb):
            a, b = sorted((root(net_at[e.pa]), root(net_at[e.pb])))
            if a != b:
                par[b] = a
    return {t: root(net) for t, net in net_at.items()}


def _offboard(pl, bd, P, cells, connectors):
    """Ground pieces joined outside the board's copper. A board whose grounds are separate nets with no part between
    them that conducts at DC (GND, AGND and RELAY_GND each on its own connectors, joined by the cables), or a module
    whose ground pins sit on two ground nets (a Nucleo's GND and its CN10 GND, joined inside it), sends a load's return
    into a piece where its source's ground is not: in the copper that current has no way out, and the DC band was void
    on a board KiCad finds fully connected. Where the plan's flow balances over the whole board but not per piece (at
    the typical point or with any one parameter at its other end), and every unbalanced piece has a way out, the current between the pieces is
    taken through it (pl.offboard; injections() moves each piece's excess there): the ground pads of a part whose
    ground pads sit in several pieces (joined inside it), else the piece's connector ground pads (joined off the board).
    Anything else that does not balance is left unbalanced, for imbalance() to report."""
    pl.piece = _pieces(pl.pads, bd.circuit.elems)
    cv0 = {c["src"]: {k: p.typ for k, p in (P.get(c["src"]) or {}).items()} for c in cells.values()}
    cv0.update({(p.subject, p.name): p.typ for p in pl.params})
    # which pieces are joined off the board is decided over the corners, not at the typical point alone: a load
    # across two rails (duanestorey's J9 on DC_POS and DC_NEG, returning through AGND_INT) leaves its ground piece
    # balanced at the typical point, where its two rails' currents are equal, but every corner that samples them
    # apart sends their difference into that piece, and those corners failed KCL. Each piece's balance moves with
    # each parameter on its own, so the typical point plus one point per parameter at its other end finds every
    # piece some corner can unbalance (injections() then moves each corner's own excess off the board)
    probes = [cv0]
    for p in pl.params:
        alt = p.hi if p.hi != p.typ else p.lo
        if alt != p.typ:
            probes.append({**cv0, (p.subject, p.name): alt})
    off = set()
    for cv in probes:
        inj = injections(pl, cv)
        big = max((abs(a) for a in inj.values()), default=0.0)
        if big == 0:
            continue
        bal = {}
        for t, a in inj.items():
            bal[pl.piece.get(t)] = bal.get(pl.piece.get(t), 0.0) + a
        if abs(sum(bal.values())) > EPS * big:
            return
        off |= {r for r, b in bal.items() if abs(b) > EPS * big}
    off = sorted(off)
    if not off:
        return
    gp = {ref: [(f"{ref}.{n}", net) for n, net, _, _ in pl.pads[ref] if net in pl.grounds] for ref in sorted(pl.pads)}
    inside = {ref: g for ref, g in gp.items() if ref not in connectors and len({pl.piece[t] for t, _ in g}) > 1}
    pads, how = {}, {}
    for r in off:
        ins = sorted({t for g in inside.values() for t, _ in g if pl.piece[t] == r})
        con = sorted({t for ref in connectors for t, _ in gp.get(ref, []) if pl.piece[t] == r})
        pads[r], how[r] = (ins, "inside " + ", ".join(sorted({t.rsplit(".", 1)[0] for t in ins}))) if ins else (con, "off the board")
    if not all(pads.values()):
        return
    pl.offboard = pads
    pl.dc_pads |= {t for ts in pads.values() for t in ts}
    net_at = {t: n for g in gp.values() for t, n in g}
    nets = sorted({net_at[t] for ts in pads.values() for t in ts})
    where = "; ".join(f"{'/'.join(sorted({net_at[t] for t in pads[r]}))} {how[r]} at {', '.join(pads[r][:3])}"
                      f"{', ...' if len(pads[r]) > 3 else ''}" for r in off)
    pl.notes.append(f"grounds {', '.join(nets)} are separate pieces of copper on the board (no part that conducts at DC "
                    f"joins them) and are joined outside it: the current between them is taken through their ground "
                    f"pads ({where})")


def _add(inj, toks, a):
    if not toks or a == 0:
        return
    for t in toks:
        inj[t] = inj.get(t, 0.0) + a / len(toks)


def _cell_vals(c, cv):
    v = cv.get(c["src"]) or {}
    return v.get("I_A", 1.0), min(max(v.get("D", 0.5), 0.02), 0.98)


def _chain(pl, r):
    """The rails from r up to the board's input (r first)."""
    out = []
    while r is not None and r not in out and r in pl.feeds:
        out.append(r)
        f = pl.feeds[r]
        r = f["cell"]["vin"] if f["kind"] == "cell" else f.get("rin")
    return out


def _cell_cap(pl, r, cv):
    """The most output current rail r's cell delivers at corner cv: its inductor current range's top (the
    ledger's I_A interval) through its topology; None without one."""
    f = pl.feeds[r]
    IL = f.get("I_hi")
    if f["kind"] != "cell" or not IL:
        return None
    c = f["cell"]
    if c["cls"] == "buckboost":       # I_L is the output current bucking, the input current boosting
        return IL / max(1.0, _ratio(pl, r, cv))
    _, D = _cell_vals(c, cv)
    return CV.output_from_inductor(_top(c), IL, D)


def cell_topology(st, nets):
    """A brief cell's topology (haslam.physics.converter.topology_of) from its rails' signed voltages in the brief's
    nets: a buck-class cell between rails of opposite signs inverts (its output is I_L (1 - D), not I_L)."""
    def sv(n):
        v = (nets.get(n) or {}).get("volts") if n else None
        return float(v) if isinstance(v, (int, float)) and v else None
    vin = sv(st.get("vin") if st.get("class") == "boost" else st.get("rail"))
    vout = sv(st.get("rail") if st.get("class") == "boost" else st.get("vout"))
    return CV.topology_of(st["class"], st, vout, vin)[0] or st["class"]


def load_currents(pl, cv):
    """Each load's current at one corner: its own parameter, scaled down where a rail on its chain would
    carry more than its feed delivers (a source's rating, a cell's top operating current: it current-limits)."""
    xs = [cv.get(ld["key"], 0.0) for ld in pl.loads]
    # each rail's total, through the chain's conversion ratios
    tot = {}
    for ld, x in zip(pl.loads, xs):
        for r0 in [ld["rail"]] + ([ld["ret"]] if ld.get("ret") else []):
            a = x
            for r in _chain(pl, r0):
                tot[r] = tot.get(r, 0.0) + a
                a *= _ratio(pl, r, cv)
    cap = {r: pl.feeds[r].get("rating") or _cell_cap(pl, r, cv) for r in tot}
    out = []
    for ld, x in zip(pl.loads, xs):
        k = 1.0
        for r in _chain(pl, ld["rail"]) + (_chain(pl, ld["ret"]) if ld.get("ret") else []):
            R = cap.get(r)
            if R and tot.get(r, 0.0) > R:
                k = min(k, R / tot[r])
        out.append(x * k)
    return out


def load_volts(pl, ld, default=3.3):
    """The voltage magnitude across a load: its rail's, or a split-supply load's span between its two rails."""
    return _mag(pl, ld["rail"], default) + (_mag(pl, ld["ret"], 0.0) if ld.get("ret") else 0.0)


def _mag(pl, r, default=1.0):
    """Rail r's voltage magnitude (pl.volts carries the sign), `default` when unknown."""
    v = pl.volts.get(r)
    return abs(v) if v else default


def _sign(pl, r):
    """+1 for a rail above ground (or of unknown voltage), -1 for one below it."""
    v = (getattr(pl, "volts", None) or {}).get(r)
    return -1.0 if v is not None and v < 0 else 1.0


def _ratio(pl, r, cv):
    """Input current per output current of rail r's feed (magnitudes)."""
    f = pl.feeds[r]
    if f["kind"] == "switching":
        return _mag(pl, r) / (cv.get((f["eta"].subject, "eta"), ETA[1]) * _mag(pl, f["rin"]))
    if f["kind"] == "cell":
        c = f["cell"]
        vo, vi = _mag(pl, r, None), _mag(pl, c["vin"], None)          # magnitudes: P_in = P_out / eta either sign
        eta = cv.get((f["eta"].subject, "eta"), f["eta"].typ) if f.get("eta") else None
        if eta and vo and vi:
            return vo / (eta * vi)              # the facts' efficiency: P_in = P_out / eta
        if c["cls"] == "buckboost":             # one converter of two legs: the power balance at its class eta
            return (vo / vi if vo and vi else 1.0) / c.get("eta", 1.0)
        _, D = _cell_vals(c, cv)
        return _cell_in(c, 1.0, D)
    return 1.0


def _top(c):
    return c.get("top") or c["cls"]


def _cell_in(c, x, D):
    """A cell's input current delivering x (magnitudes; haslam.physics.converter): a boost's its inductor current
    x / (1 - D), D = 1 - V_in eta / V_out holding its losses; an inverting stage's D I_L, I_L = x / (1 - D), its
    D = |V_out| / (V_in eta + |V_out|) holding them too (TI SLVA721); a buck's from the power balance, D x / eta
    (D = V_out / V_in)."""
    top = _top(c)
    IL = CV.inductor_from_output(top, x, D)
    if top in ("boost", "boost_led", "inverting_buck_boost"):
        return CV.input_from_inductor(top, IL, D)
    return CV.input_from_inductor(top, IL, D) / c.get("eta", 1.0)


def injections(pl, cv, lost=None):
    """{pad: A} of the DC power flow at one corner, positive into the copper. cv: {source name: {param: value}} for
    the cells' corners plus {(subject, name): value} for the DC band's own parameters.

    Currents carry their rails' signs: a load on a rail below ground (-12 V) takes its current from its ground pad
    and returns it into the rail (its supply pad injects +I), and every feed of that rail takes it back out. A
    feed between rails of one sign is the mirror image of its positive form; an inverting one (input above ground,
    output below) draws its input current at its input pins, takes its output current back at its reference pins
    on the negative rail, and sends both out of its switch pin through the inductor to ground. Every piece of the
    DC circuit then balances exactly (imbalance(); nothing absorbs an error). lost: a list that gets
    (what, amperes) for every current the plan had no pad for (a silent drop before)."""
    inj = {}
    pads = pl.pads

    def on(ref, net):
        return [f"{ref}.{n}" for n, nt, _, _ in pads.get(ref, []) if nt == net]

    def gnd(ref):
        return [f"{ref}.{n}" for n, nt, _, _ in pads.get(ref, []) if nt in pl.grounds]

    def add(toks, a, what):
        if a and not toks and lost is not None:
            lost.append((what, a))
        _add(inj, toks, a)

    def take_in(f, c, s_in, depth):
        """A cell's input current s_in (signed), from its input rail's feed, or, where that rail has no feed
        (flow_external), entering at the cell itself and returning at its ground."""
        if f.get("flow_external"):
            add(f["entry"], s_in, f"{c['vout']}: {c['id']} input (enters at it)")
            add(f["gnd"], -s_in, f"{c['vout']}: {c['id']} input's return")
        else:
            deliver(c["vin"], s_in, depth + 1)

    def deliver(r, s, depth=0):
        """s amperes (signed: the rail's own sign for current it delivers) into rail r from its feed, walked back
        to the board's input."""
        f = pl.feeds.get(r)
        if f is None or depth > 8 or s == 0:
            if s and lost is not None:
                lost.append((f"{r}: no feed" if f is None else f"{r}: feed chain deeper than 8", s))
            return
        k = f["kind"]
        if f.get("flow_external") and k != "cell":
            add(f["out"], s, f"{r}: {f['ref']} output")
            add(f["gnd"], -s, f"{r}: {f['ref']} return")
            return
        if k == "external":
            add(f["out"], s, f"{r}: {f['ref']} output")
            add(f["gnd"], -s, f"{r}: {f['ref']} return")
        elif k == "linear":
            add(f["out"], s, f"{r}: {f['ref']} output")
            add(f["inp"], -s, f"{r}: {f['ref']} input")
            deliver(f["rin"], s, depth + 1)
        elif k == "switching":
            # the power balance in magnitudes: |V_in| x_in eta = |V_out| |s|; the input current carries its rail's sign
            xin = abs(s) * _mag(pl, r) / (cv.get((f["eta"].subject, "eta"), ETA[1]) * _mag(pl, f["rin"]))
            s_in = _sign(pl, f["rin"]) * xin
            add(f["out"], s, f"{r}: {f['ref']} output")
            add(f["inp"], -s_in, f"{r}: {f['ref']} input")
            add(f["gnd"], s_in - s, f"{r}: {f['ref']} return")
            deliver(f["rin"], s_in, depth + 1)
        elif k == "cell":
            c = f["cell"]
            _, D = _cell_vals(c, cv)
            ctrl, rin = c["ctrl"], c["vin"]
            x, top = abs(s), _top(c)
            xin = x * _ratio(pl, r, cv)                         # the input current (the cell's duty, or P_out / eta)
            sw, ins, gs = on(ctrl, c["sw"]), on(ctrl, rin), gnd(ctrl)
            boost = top in ("boost", "boost_led")
            if top == "inverting_buck_boost":
                # TI SLVA721: the high side carries I_in = D I_L from the input pins into the switch node, the low side
                # (1 - D) I_L = |I_out| from the negative rail (the IC's reference pins, or the rectifier, which conducts
                # in the copper) into it, and the inductor takes I_L = I_in + |I_out| from the switch node to ground
                s_in = _sign(pl, rin) * xin
                add(ins, -s_in, f"{r}: {c['id']} input")
                add(sw, s_in, f"{r}: {c['id']} high side")
                if not c["rect"]:
                    add(on(ctrl, r), s, f"{r}: {c['id']} low side")
                    add(sw, -s, f"{r}: {c['id']} low side")
            elif c.get("ext"):
                # a 4-switch buck-boost with external FETs (either region): the input current enters at the input
                # leg's high-side FET's drain, the output current leaves at the output leg's, and their difference
                # (the conversion's balance) returns at the sense shunt's ground pad, else the low-side FETs'. P_in =
                # P_out / eta, at the facts' eta when they state it
                e = c["ext"]
                eta = cv.get((f["eta"].subject, "eta"), f["eta"].typ) if f.get("eta") else c.get("eta", 1.0)
                xin = x * _mag(pl, r) / (eta * _mag(pl, rin))
                s_in = _sign(pl, rin) * xin
                ins, boost = on(e["in_high"], rin), False
                gs = (gnd(e["shunt"]) if e.get("shunt") else []) or gnd(e["in_low"]) or gnd(e["out_low"])
                add(ins, -s_in, f"{r}: {c['id']} input")
                add(on(e["out_high"], r), s, f"{r}: {c['id']} output")
                add(gs, s_in - s, f"{r}: {c['id']} return")
            elif top == "inverting_buck":
                # an inverting buck (TPS6371x): its inductor runs from the negative rail into the switch node, so the
                # IC takes the output current s (signed: below ground) in at its switch pin and the input current
                # D |I_out| / eta at its input pins, and returns both through its ground pins (the flying capacitor
                # carries no DC)
                s_in = _sign(pl, rin) * xin
                add(ins, -s_in, f"{r}: {c['id']} input")
                add(sw, s, f"{r}: {c['id']} switch node (the inductor's current)")
                add(gs, s_in - s, f"{r}: {c['id']} return")
            else:
                # a buck, boost or 4-switch buck-boost between rails of one sign: its positive form's currents, all of
                # them mirrored on rails below ground
                m = _sign(pl, r)
                s_in = xin * m
                if c["cls"] == "buckboost":
                    IL = max(x, xin)                                # bucking the output current, boosting the input's
                    add(sw, IL * m, f"{r}: {c['id']} input switches")           # the input switches drive I_L into SW1
                    add(on(ctrl, c["sw2"]), -IL * m, f"{r}: {c['id']} inductor")  # it comes back through the inductor at SW2
                    add(on(ctrl, r), x * m, f"{r}: {c['id']} output")           # the output switches deliver the output current
                    add(ins, -s_in, f"{r}: {c['id']} input")
                    add(gs, (xin - x) * m, f"{r}: {c['id']} losses")
                elif boost:
                    IL = xin                                        # the input current flows in the inductor
                    sw_p, ret = sw, gs
                    if not sw_p and c.get("low") and c["low"] != ctrl:
                        # an external switch FET (an LT3754's, a MAX1771's): D I_L enters at its drain on the switch
                        # node and leaves at its source, to ground or through the current-sense resistor (lumped) to it
                        sw_p, ret = on(c["low"], c["sw"]), _fet_source(pl.pads, c["low"], c["sw"])
                    add(sw_p, -(IL - x) * m, f"{r}: {c['id']} switch")          # the switch: D I_L from the switch node
                    add(ret, (IL - x) * m, f"{r}: {c['id']} switch return")     # to ground
                    if not c["rect"]:                               # synchronous: the rectifier inside too
                        add(sw, -x * m, f"{r}: {c['id']} rectifier")
                        add(on(ctrl, r), x * m, f"{r}: {c['id']} rectifier")
                    ins = []                                        # the input feeds the inductor (lumped)
                else:
                    hs_sw = sw
                    if not hs_sw and c.get("high") and c["high"] != ctrl:
                        # an external high-side FET: the input current enters it at its drain, D I_out leaves its source
                        ins, hs_sw = on(c["high"], rin), on(c["high"], c["sw"])
                    add(ins, -s_in, f"{r}: {c['id']} input")                    # the input: D I_out / eta (the power balance)
                    add(hs_sw, D * x * m, f"{r}: {c['id']} high side")          # the high side: D I_out into the switch node
                    add(gs, (xin - D * x) * m, f"{r}: {c['id']} losses")        # the cell's own losses, back through its ground
                    if not c["rect"]:
                        add(gs, -(1 - D) * x * m, f"{r}: {c['id']} low side")   # the low side: the rest of I_out from ground
                        add(sw, (1 - D) * x * m, f"{r}: {c['id']} low side")
            if f.get("flow_external") or rin in pl.feeds:
                # the input current from its rail's feed, or, where that rail has none (flow_external), entering at
                # the cell's input (plan's mark_unfed: an external-FET leg's high side, a boost's inductor, else the
                # controller's input pins) and returning at its ground
                take_in(f, c, s_in, depth)
            else:
                # a plan made without mark_unfed (a hand-built one): the flow enters at the controller, its input
                # pins (a boost's inductor) or its ground; an input current from nowhere left the copper open (a
                # buck) or drew it through whatever resistors join the input to ground
                tgt = ins if not boost else (on(ctrl, rin) or [])
                if boost and not tgt:
                    tgt = [t for t in on(c["ind"], rin)] if c.get("ind") else []
                add(tgt or gs, s_in, f"{r}: {c['id']} unfed input")
                add(gs, -s_in, f"{r}: {c['id']} unfed input return")
    for ld, x in zip(pl.loads, load_currents(pl, cv)):
        s = _sign(pl, ld["rail"]) * x
        add(ld["sup"], -s, f"{ld['rail']}: load {ld['ref']}")
        add(ld["gnd"], s, f"{ld['rail']}: load {ld['ref']} return")
        if ld.get("through"):
            # a charge path (plan's charge sinks): the series part passes the current on into the source's rail, and
            # the source (a battery) takes it at its feed pads
            add(ld["through"][0], s, f"{ld['rail']}: charge of {ld['ref']} through its series part")
            add(ld["through"][1], -s, f"{ld['rail']}: charge into {ld['ref']}")
        deliver(ld["rail"], s)
        if ld.get("ret"):
            deliver(ld["ret"], -s)          # a split-supply load's current, taken back out by its negative rail's feed
    if pl.offboard:
        # ground pieces joined off the board (_offboard): each one's excess leaves through its connectors' ground
        bal = {}
        for t, a in inj.items():
            if pl.piece.get(t) in pl.offboard:
                bal[pl.piece[t]] = bal.get(pl.piece[t], 0.0) + a
        for r in sorted(bal):
            _add(inj, pl.offboard[r], -bal[r])
    return inj


def imbalance(pl, inj, lost=()):
    """Why a DC injection set (injections()) is no power flow: the currents the plan had no pad for, and every piece
    of the DC circuit (pl.piece; the whole board without one) whose injections do not sum to zero beyond float
    rounding (EPS of the largest). [] when it balances. The field solve would read either as an open in the copper
    (or absorb a small one as a cut-off pad): this tells a wrong plan from a broken board."""
    out = [f"{abs(a):.3g} A of {what} has no pad" for what, a in lost]
    big = max((abs(a) for a in inj.values()), default=0.0)
    bal = {}
    for t, a in inj.items():
        k = pl.piece.get(t, "?") if pl.piece else "board"
        bal[k] = bal.get(k, 0.0) + a
    for k in sorted(bal, key=lambda q: (-abs(bal[q]), q)):
        if abs(bal[k]) > EPS * big:
            out.append(f"{bal[k]:+.3g} A left on {k}")
    return out


def element_terminals(pads, elems, inj):
    """{pad: A}: injections with the current through each part the copper model conducts through at DC (DC_KINDS: a
    fuse, an inductor, a sense resistor, a forward diode, a divider) put on its two pads, so that every net balances
    on its own. A caller that solves one net's copper at a time (power copper's branch currents, synth's width gate)
    then sees where a series part's current enters and leaves the net: obd-solar's CHG_OUT took the charger's current
    from R203 and its OBD_RAW the battery's through F101, which the per-pad injections never named, so the gate fell
    back to the net's i_max everywhere (and the design wrote width_injections.json by hand).

    How: each piece of nets the elements join is solved as a lumped resistor network (one node per net, each element
    its DC resistance |z(0)|, the nets' summed injections as sources); an element's current is its voltage over its
    resistance. Exact for a chain of series parts; where parts join nets in parallel or in a loop (a divider beside a
    fuse) the current splits by their conductances, as in the copper (each net taken as one node: its own copper's
    resistance is the caller's to solve). Returns (injections, [notes])."""
    net_at = {f"{ref}.{n}": net for ref, pp in pads.items() for n, net, _, _ in pp}
    edges = []
    for e in elems:
        a, b = net_at.get(e.pa), net_at.get(e.pb)
        if e.kind not in DC_KINDS or not a or not b or a == b:
            continue
        try:
            r = abs(complex(e.z(0.0))) if callable(getattr(e, "z", None)) else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            r = 0.0
        edges.append((e, a, b, max(r, 1e-6)))       # a short (0 ohm link, jumper) as 1 uOhm
    tot = {}
    for t, a in inj.items():
        if t in net_at:
            tot[net_at[t]] = tot.get(net_at[t], 0.0) + a
    par = {}

    def root(x):
        while par.get(x, x) != x:
            x = par[x]
        return x
    for _, a, b, _ in edges:
        ra, rb = root(a), root(b)
        if ra != rb:
            par[max(ra, rb)] = min(ra, rb)
    comps = {}
    for _, a, b, _ in edges:
        comps.setdefault(root(a), set()).update((a, b))
    out, notes = dict(inj), []
    for k in sorted(comps):
        nodes = sorted(comps[k])
        if not any(abs(tot.get(n, 0.0)) > 0 for n in nodes):
            continue
        ix = {n: i for i, n in enumerate(nodes)}
        G = np.zeros((len(nodes), len(nodes)))
        es = [x for x in edges if x[1] in ix]
        for _, a, b, r in es:
            g = 1.0 / r
            G[ix[a], ix[a]] += g
            G[ix[b], ix[b]] += g
            G[ix[a], ix[b]] -= g
            G[ix[b], ix[a]] -= g
        rhs = np.array([tot.get(n, 0.0) for n in nodes])
        big = float(np.max(np.abs(rhs)))
        if abs(float(rhs.sum())) > 1e-6 * max(big, 1e-12):
            # the piece's injections do not balance (current leaves through a part the copper does not conduct,
            # off the board): its elements' currents are not determined, so nothing is added
            notes.append(f"{nodes[0]} (+{len(nodes) - 1} nets): injections sum to {rhs.sum():+.3g} A; not split")
            continue
        # one node held at 0 V (the network is floating): the rest solve exactly
        v = np.zeros(len(nodes))
        if len(nodes) > 1:
            v[1:] = np.linalg.solve(G[1:, 1:], rhs[1:])
        for e, a, b, r in es:
            i_ab = (v[ix[a]] - v[ix[b]]) / r           # through the element from a's pad to b's
            if abs(i_ab) <= 1e-12 * max(big, 1e-12):
                continue
            pa, pb = (e.pa, e.pb) if net_at[e.pa] == a else (e.pb, e.pa)
            out[pa] = out.get(pa, 0.0) - i_ab
            out[pb] = out.get(pb, 0.0) + i_ab
    return {t: a for t, a in out.items() if a}, notes


def planned_injections(board, intent, brief=None, heat=None, sources=None, per_net=False):
    """{"REF.NUM": A} of the DC power flow at the typical point of every parameter, from the plan the
    physics evaluator scores (haslam.excite.evaluate: rails, feeds, regulators, loads and their currents
    under the operating facts `intent`), positive into the copper; {} when the plan has no rail with a
    source and a load. For callers outside the evaluator (power copper's THT neck); no field solve. `sources`: a dict
    filled with {"REF.NUM": set of the sources ("intent", "part_table", "prior") of the load currents at that pad},
    so a caller can tell a stated current from a class prior. per_net: also the current through each series part
    the copper model conducts through, on its pads (element_terminals), so that every net balances on its own.

    The brief is built as the evaluator builds it (haslam.excite.evaluate.evaluate): from the operating facts (a
    haslam.intent/1 document's `facts`), with inverting cells. Built from the board
    alone, it lost the facts' rails and sources (a rail the facts give a voltage and no source part had no feed), so
    callers (power copper's necks and quiet nets, synth's width gate) solved a different plan from the one scored."""
    from haslam.circuit import brief as B
    from haslam.circuit.roles import cells_inverting
    from . import models as M
    from . import sources as S
    from .evaluate import ledger_for
    from haslam.board import pinfacts as PF
    if (intent or {}).get("schema") == "haslam.intent/1":
        intent = intent.get("facts") or {}
    PF.apply(board, (intent or {}).get("pins"))         # the schematic's pin facts, as the evaluator applies them
    brief = brief or B.build(board, facts=intent or None, inverting=cells_inverting(True))
    bd = M.build(board, brief)
    srcs = S.add_all(bd, brief, intent=intent)
    P, _ = ledger_for(bd, brief, srcs, intent)
    pl = plan(board, brief, bd, P, srcs, intent)
    cv = {(p.subject, p.name): p.typ for p in pl.params}
    for s_ in srcs:
        if s_.kind == "cell":
            cv[s_.name] = {k: getattr(v, "typ", v) for k, v in (P.get(s_.name) or {}).items()}
    if heat is not None:
        # heat: {ref: W} the linear regulators drop, (V_in - V_out) x their rail's total current
        tot = {}
        for ld, x in zip(pl.loads, load_currents(pl, cv)):
            a = x
            for r in _chain(pl, ld["rail"]):
                tot[r] = tot.get(r, 0.0) + a
                a *= _ratio(pl, r, cv)
        for r, f in pl.feeds.items():
            if f.get("kind") == "linear" and f.get("out"):
                vi, vo = abs(pl.volts.get(f.get("rin")) or 0.0), abs(pl.volts.get(r) or 0.0)
                if vi and vo and vi > vo:
                    ref = str(f["out"][0]).rsplit(".", 1)[0]
                    heat[ref] = heat.get(ref, 0.0) + tot.get(r, 0.0) * (vi - vo)
    lost = []
    inj = injections(pl, cv, lost)
    bad = imbalance(pl, inj, lost)
    if bad:
        raise ValueError(f"the DC plan's current does not balance: {'; '.join(bad[:4])}")
    if per_net:
        inj, _ = element_terminals(pl.pads, bd.circuit.elems, inj)
    if sources is not None:
        src_of = {(p.subject, p.name): p.source for p in pl.params}
        for ld in pl.loads:
            for t in list(ld.get("sup") or []) + list(ld.get("gnd") or []):
                sources.setdefault(t, set()).add(src_of.get(ld.get("key"), "prior"))
    return {k: float(v) for k, v in inj.items() if v}


def _fet_source(pads, ref, drain_net):
    """The pads of switch FET ref its current leaves by: those named S (source), else its pads off the drain net
    other than the gate, the FET's net with the fewest pads on the board (the gate drive is one trace; the source
    goes to ground or a sense resistor)."""
    pp = pads.get(ref, [])
    src = [f"{ref}.{n}" for n, nt, _, fn in pp if nt != drain_net and re.match(r"^S(OURCE)?\d*$", fn or "", re.I)]
    if src:
        return src
    count = {}
    for p2 in pads.values():
        for _, nt, _, _ in p2:
            count[nt] = count.get(nt, 0) + 1
    others = sorted({nt for _, nt, _, _ in pp if nt != drain_net})
    named_g = {nt for _, nt, _, fn in pp if re.match(r"^G(ATE)?\d*$", fn or "", re.I)}
    gate = named_g or ({min(others, key=lambda q: (count.get(q, 0), q))} if len(others) > 1 else set())
    return [f"{ref}.{n}" for n, nt, _, _ in pp if nt != drain_net and nt not in gate]


def _feed_pads(pl, rail):
    """The pads where rail's feed delivers its current: a cell's rectifier's (else its controller's) on the rail, any
    other feed's output pads."""
    f = pl.feeds.get(rail)
    if f is None:
        return []
    if f["kind"] != "cell":
        return list(f["out"])
    c = f["cell"]
    ref = c["rect"] or c["ctrl"]
    return [f"{ref}.{n}" for n, nt, _, _ in pl.pads.get(ref, []) if nt == rail]


def _mean(V, toks):
    vals = [V[t] for t in toks if t in V and V[t] is not None and np.isfinite(V[t])]
    return float(np.mean(np.real(vals))) if vals else None


def observe(pl, cv, V, info, tracks=None):
    """The DC observers at one corner from its solve: dict(loss=(u, P_cu, budget), drops=[(ref, rail, u,
    dV, budget)], drops_signed=[(ref, rail, signed dV)], heat=[(track index, u, dT, I)]). dV >= 0: a load whose
    ground sits below its source's (a ground shift) reads 0, its signed value in drops_signed."""
    inj = injections(pl, cv)
    net, x = info["net"], info["x"]
    P_all = float(np.real(sum(a * V[t] for t, a in inj.items() if t in V and V[t] is not None)))
    sysm = info["sys"]
    lo = net.off["l"]
    Il = x[lo:net.n_br]
    P_l = float(np.sum(np.abs(Il) ** 2 * np.real(sysm.zdiag[lo:net.n_br]))) if len(Il) else 0.0
    P_cu = max(P_all - P_l, 0.0)
    xs = load_currents(pl, cv)
    # a rail without a known voltage at the drop check's 3.3 V: at 0 V the budget was 0 and the loss u 0
    # (perfect) whatever the copper lost, or P_cu of every rail was divided by the known rails' budget
    P_del = sum(xk * load_volts(pl, ld) for ld, xk in zip(pl.loads, xs))
    budget = pl.loss_share * P_del
    out = dict(loss=(P_cu / budget if budget > 0 else 0.0, P_cu, budget), drops=[], drops_signed=[], heat=[])
    for ld, xk in zip(pl.loads, xs):
        f = pl.feeds.get(ld["rail"])
        if f is None or xk <= 0:
            continue
        if f["kind"] == "cell":
            c = f["cell"]
            src_r = [f"{c['rect']}.{n}" for n, nt, _, _ in pl.pads.get(c["rect"], []) if nt == ld["rail"]] if c["rect"] else \
                [f"{c['ctrl']}.{n}" for n, nt, _, _ in pl.pads.get(c["ctrl"], []) if nt == ld["rail"]]
            src_g = [f"{c['ctrl']}.{n}" for n, nt, _, _ in pl.pads.get(c["ctrl"], []) if nt in pl.grounds]
            if _top(c) == "inverting_buck_boost" and not src_g and c.get("ind"):
                # an inverter's IC has no ground pin (its reference is the negative rail): its ground is where its
                # inductor's current returns
                src_g = [f"{c['ind']}.{n}" for n, nt, _, _ in pl.pads.get(c["ind"], []) if nt in pl.grounds]
        else:
            src_r, src_g = f["out"], f["gnd"] or []
        if ld.get("ret"):
            # a split-supply load's other side is its negative rail, whose source stands in for the ground
            src_g = _feed_pads(pl, ld["ret"])
        vs, vl = _mean(V, src_r), _mean(V, ld["sup"])
        if vs is None or vl is None:
            continue
        dv = vs - vl
        gs, gl = _mean(V, src_g), _mean(V, ld["gnd"])
        if gs is not None and gl is not None:
            dv += gl - gs
        # what the load loses of its source's (rail - ground) voltage, toward ground whichever side the rail is on:
        # a -12 V load sits less negative than its source, so its signed loss is the mirror of a +12 V one's
        dv *= _sign(pl, ld["rail"])
        b = pl.drop_share * load_volts(pl, ld)
        # the drop is what the load loses of its source's voltage, so never below 0. The signed sum can be negative
        # by physics, not by a reference choice: another rail's return current through shared ground copper (or a
        # source whose own ground pin carries current) puts the load's ground below the source's, and the load then
        # sees more than the source's voltage. That is no drop (and no credit against one); the signed value is kept
        # for the reader (`drops_signed`). A one-sided clamp, not |dv|: drop.rail is typed Clamp (haslam.excite.quantity).
        out["drops_signed"].append((ld["ref"], ld["rail"], dv))
        d = max(dv, 0.0)
        out["drops"].append((ld["ref"], ld["rail"], d / b, d, b))
    if tracks:
        for k, (I, w_eff, t_mm, ext) in enumerate(tracks(x)):
            dT = ipc_dT(abs(I), w_eff, t_mm, ext)
            out["heat"].append((k, dT / pl.dT_max, dT, I))
    return out


def _arc_frame(t):
    """(f(q) -> (x, y, ux, uy) at fraction q of the arc, centre, radius, length) of an arc track; None
    when its three points are collinear."""
    (x0, y0), (xm, ym), (x1, y1) = t.start, t.mid, t.end
    d = 2.0 * (x0 * (ym - y1) + xm * (y1 - y0) + x1 * (y0 - ym))
    if abs(d) < 1e-14:
        return None
    a1, a2, a3 = x0 * x0 + y0 * y0, xm * xm + ym * ym, x1 * x1 + y1 * y1
    cx = (a1 * (ym - y1) + a2 * (y1 - y0) + a3 * (y0 - ym)) / d
    cy = (a1 * (x1 - xm) + a2 * (x0 - x1) + a3 * (xm - x0)) / d
    r = math.hypot(x0 - cx, y0 - cy)
    b0, bm_, b1 = (math.atan2(y - cy, x - cx) for x, y in ((x0, y0), (xm, ym), (x1, y1)))
    sw = (b1 - b0) % (2 * math.pi)
    if (bm_ - b0) % (2 * math.pi) > sw:
        sw -= 2 * math.pi

    def at(q):
        a = b0 + sw * q
        s = 1.0 if sw > 0 else -1.0
        return cx + r * math.cos(a), cy + r * math.sin(a), -s * math.sin(a), s * math.cos(a)
    return at, (cx, cy), r, abs(r * sw)


def _net_copper(bm, board_tracks, keys):
    """{(net, layer name): (STRtree, [geometry])} of each named net's copper on each named layer, from the
    board's geometry (tracks, arcs, pads, vias, KiCad's fills), not from the raster."""
    from shapely import STRtree
    from shapely.geometry import LineString, Point

    from haslam.em.kicad import _arc_points
    geo = {k: [] for k in keys}
    for t in board_tracks:
        k = (t.net, t.layer)
        if k in geo:
            pts = _arc_points(t, 64) if getattr(t, "mid", None) is not None else [t.start, t.end]
            geo[k].append(LineString(pts).buffer(t.width / 2, quad_segs=8))
    for net, per in (getattr(bm, "fills", None) or {}).items():
        for layer, pgs in per.items():
            if (net, layer) in geo:
                geo[(net, layer)].extend(pgs)
    for lst in (getattr(bm, "pads", None) or {}).values():
        for layer, g, p in lst:
            if (p.net, layer) in geo and g is not None:
                geo[(p.net, layer)].append(g)
    b = getattr(bm, "b", None)
    for v in (getattr(b, "vias", None) or []):
        for layer in bm.span(v.layers):
            if (v.net, layer) in geo:
                geo[(v.net, layer)].append(Point(v.x, v.y).buffer(v.size / 2, quad_segs=8))
    return {k: (STRtree(gs), gs) for k, gs in geo.items() if gs}


def _copper_across(tree, cx, cy, nx, ny, half):
    """Length of the net's copper along the segment through (cx, cy) in direction (nx, ny), half long each
    way: the piece that holds the centre."""
    from shapely.geometry import LineString
    seg = LineString([(cx - nx * half, cy - ny * half), (cx + nx * half, cy + ny * half)])
    st, gs = tree
    iv = []                                  # the pieces as intervals of the distance along the segment
    for k in st.query(seg):
        g = gs[k].intersection(seg)
        for q in getattr(g, "geoms", [g]):
            if q.geom_type == "LineString" and not q.is_empty:
                ts = [(x - cx) * nx + (y - cy) * ny for x, y in q.coords]
                iv.append((min(ts), max(ts)))
    iv.sort()
    lo = hi = None
    for a, b in iv:                          # merge touching pieces; keep the one holding the centre
        if hi is not None and a <= hi + 1e-6:
            hi = max(hi, b)
            continue
        if lo is not None and lo <= 1e-6 and hi >= -1e-6:
            return hi - lo
        lo, hi = a, b
    return hi - lo if lo is not None and lo <= 1e-6 and hi >= -1e-6 else 0.0


def track_currents(bm, board_tracks, net, nets=None):
    """A function x -> [(I, w_eff mm, t mm, external)] per track, at the hottest of its quarter points.

    The current is the flux of the solved bar currents through a grid line across the track (the
    vertical line between two cell columns for a track running nearer x, else the horizontal one),
    over the cells of the track's net on it: every bar crossing that line is counted once, whatever
    the track's angle and wherever it falls in its cells, so the raster's staircase of a thin track
    reads its true current. The width is the track's own unless more copper of its net lies across it
    (a pour, a pad, a wider track) within its width plus a cell each side: then the width is that
    copper's, measured on the board's geometry along the perpendicular, and the current is the flux
    through the same window (the grid line's cells weighted by their overlap with it). Reading both
    off cells sampled along the perpendicular gave 0.7x to 2x the true current, and 1x to 3x the
    width, by the track's angle and sub-cell position (docs/topics/physics/thermal-physics.md,
    'IPC-2221/2152 as a thermal model')."""
    m = bm.m
    p = m.pitch
    lname = [l.name for l in m.layers]
    sel_t = [t for t in board_tracks
             if t.layer in lname and (nets is None or t.net in nets) and t.net in m.nets]
    trees = _net_copper(bm, board_tracks, {(t.net, t.layer) for t in sel_t}) if sel_t else {}
    samples, kept = [], []
    for t in sel_t:
        l = lname.index(t.layer)
        nid = m.nets.index(t.net)
        (x0, y0), (x1, y1) = t.start, t.end
        L = math.hypot(x1 - x0, y1 - y0)
        arc = _arc_frame(t) if getattr(t, "mid", None) is not None else None
        if arc is not None:
            L = arc[3]
        if L < p:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        half = t.width / 2 + p
        pts = []
        for q in (0.25, 0.5, 0.75):
            if arc is not None:
                # an arc track: its quarter points on the arc, across its local direction (a chord
                # can run outside the copper and would see none of the track's current)
                cx, cy, ux, uy = arc[0](q)
            else:
                cx, cy = x0 + q * (x1 - x0), y0 + q * (y1 - y0)
            tree = trees.get((t.net, t.layer))
            across = _copper_across(tree, cx, cy, -uy, ux, half) if tree is not None else t.width
            wide = across > t.width + 0.25 * p
            vert = abs(ux) >= abs(uy)            # cut by a vertical grid line (x-bars) or a horizontal one
            ua, ub = (ux, uy) if vert else (uy, ux)
            ca, cb = (cx, cy) if vert else (cy, cx)
            a0, b0, na, nb = (m.x0, m.y0, m.nx, m.ny) if vert else (m.y0, m.x0, m.ny, m.nx)
            k = int(round((ca - a0) / p))        # the grid line a = a0 + k p, between cells k-1 and k
            if not 1 <= k < na:
                continue
            bline = cb + (a0 + k * p - ca) * ub / ua     # where the track's centre line crosses it
            if wide:
                H = half / abs(ua)               # the perpendicular window, projected on the grid line
            else:
                # every bar of the track's own copper: a thin track's 4-connected chain crosses the
                # line within 1.5 cells of its centre line
                H = t.width / 2 / abs(ua) + 1.5 * p
            lo, hi = bline - H, bline + H
            cells = []
            for c in range(max(0, int(math.floor((lo - b0) / p))), min(nb, int(math.floor((hi - b0) / p)) + 1)):
                c0 = b0 + c * p
                f = (min(hi, c0 + p) - max(lo, c0)) / p if wide else (1.0 if lo <= c0 + 0.5 * p <= hi else 0.0)
                if f > 0:
                    cells.append(((c, k - 1) if vert else (k - 1, c), f))
            pts.append(("x" if vert else "y", 1.0 if ua > 0 else -1.0, cells, max(t.width, across)))
        if pts:
            samples.append((l, nid, pts, m.layers[l]))
            kept.append(t)
    if not samples:
        f = lambda x: []          # noqa: E731
        f.tracks = []
        return f
    sub_of = net.sub_of

    def per_track(x):
        K = {}
        for o in ("x", "y"):
            f = net.fil[o]
            a0, n = net.off[o], len(net.fil[o]["a"])
            for l in range(len(m.layers)):
                sel = np.isin(f["s"], sub_of[l])
                arr = np.zeros((m.ny, m.nx))
                if n and sel.any():
                    np.add.at(arr, (f["j"][sel], f["i"][sel]), np.real(x[a0:a0 + n][sel]))
                K[(l, o)] = arr
        out = []
        for l, nid, pts, layer in samples:
            lab = m.lab[l]
            ext = l in (0, len(m.layers) - 1)
            best, weff, dT = 0.0, pts[0][3], -1.0
            for o, sgn, cells, w in pts:
                Ko = K[(l, o)]
                di, dj = (1, 0) if o == "x" else (0, 1)
                I = 0.0
                for (j, i), fr in cells:
                    if lab[j, i] == nid and lab[j + dj, i + di] == nid:
                        I += fr * Ko[j, i]
                I *= sgn
                d = ipc_dT(abs(I), w, layer.t, ext)
                if d > dT:
                    best, weff, dT = I, w, d
            out.append((best, weff, layer.t, ext))
        return out
    per_track.tracks = kept
    return per_track
