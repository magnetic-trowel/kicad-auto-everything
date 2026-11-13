# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The DC band: where each rail's current flows in the copper, and what it costs there.

Power flow. Every rail of the brief has a source part; its loads are the parts that draw supply
current from it (an IC only through its supply pins) and return it at their own ground pads,
with class-prior currents (kae.route.critical_rails.load_current, E5) as intervals x/3 .. x3, or
the intent file's. Each load's current is walked back to the board's input through the chain of
parts that feed its rail, so every copper island balances (KCL) and the ground copper carries
each return to where it really goes:

    external source (connector, battery)  delivers I at its rail pads, takes it back at its ground pads
    linear (LDO, charger, load switch)     takes I from its input rail, delivers it to its output
    switching regulator (no cell found)    takes I Vout / (eta Vin) from its input, the rest to ground
    commutation cell (kae.circuit)         its inductor and rectifier conduct (lumped into the copper);
                                           the switches are injected: boost: the switch takes D I_L to
                                           ground, I_L = I_out / (1 - D); buck: the high side takes
                                           D I_out from the input; synchronous rectifiers likewise

A rail fed by a cell carries the cell's operating current (the AC ledger's I_A and D, the same
operating point the switching harms use), split among its loads by their priors.

Observers (requirements: the intent file's, else these priors):

    loss     copper dissipation (sum of J V over the pads, less the lumped parts' own) against
             LOSS_SHARE of the power the loads take
    drop     per load, rail plus ground drop from its rail's source (rail-side minus load-side, plus
             load ground minus source ground, at least 0) against DROP_SHARE of the rail voltage
    heating  per track, the temperature rise by IPC-2221 (conservative against IPC-2152) of the
             current through its cross-section, against DT_MAX
"""
from __future__ import annotations

import math
import re

import numpy as np

from .beliefs import Param

LOSS_SHARE = 0.01       # copper may dissipate 1 % of the delivered power (prior requirement)
DROP_SHARE = 0.02       # rail + ground drop: 2 % of the rail voltage (as kae.route.critical_rails)
DT_MAX = 10.0           # K, track temperature rise (the common IPC design point)
ETA = (0.75, 0.85, 0.95)   # efficiency of a switching regulator without a cell model (lo, typ, hi)
DC_KINDS = ("R", "L", "FB", "D_on", "short")     # circuit elements that conduct at DC
LINEAR = ("regulator_linear", "charger", "load_switch", "battery_monitor", "usb_pd")
SWITCHING = ("regulator_switching", "pmic", "regulator_module")
# parts that consume power as well as supply a rail: a module (an MCU board of its own: Teensy, XIAO, Pico, ESP32
# modules) whose regulator feeds the carrier's 3V3 while its own MCU draws from its input; an MCU, FPGA or radio
# whose internal regulator feeds a core rail. Their own draw is a load on their input (or, fed from their own
# connector, heat with no DC flow in the carrier's copper). A regulator's own draw is its quiescent current.
CONSUMER_SUB = ("mcu", "fpga", "processor", "soc", "rf", "phy", "memory", "logic", "adc_dac", "interface", "sensor",
                "audio_amp")
# what a part with a supply and a ground pad draws (A) where kae.route.critical_rails has no class prior
LOAD_PRIOR = {"optocoupler": 0.01, "oscillator": 0.01}
# an LED with a pad on a rail and one on ground draws from the rail (an addressable LED's VDD and GND pins; a plain
# LED returning to ground beside its series resistor's rail end is not on the rail and is not a load here)
LOAD_KINDS = ("ic", "module", "connector", "led") + tuple(LOAD_PRIOR)
SUPPLY_PIN = re.compile(r"^(V(CC|DD|IN|BAT|BUS|S|M|PP|IO|CORE|DDA|DDIO|USB|SYS|P|\+)\w*|AVDD|DVDD|IOVDD|PVDD|PVIN|"
                        r"AVCC|DVCC|VIN\d*|PWR|POWER|\+V\w*|V\+|VREG_IN|IN)$", re.I)
VOLT_PIN = re.compile(r"^\+?\d+V\d*$|^\+?\d+(\.\d+)?V$", re.I)     # '3V3', '5V', '+1.8V': a supply pin by its voltage


def draws_from(pp, net, rails):
    """Whether an IC or module with pads pp [(number, net, pintype, pinfunction)] takes supply current
    from rail `net`: a pad on it typed power_in or named as a supply (VCC, VDD, 3V3...), or, on a board
    whose pads carry neither name nor type (KiCad 5, Eagle and other imports: about half the corpus), a
    pad on a net the brief classed as a rail or whose name says supply (kae.circuit.roles' rule)."""
    from kae.circuit.roles import _unannotated_pin_sem
    for _, nt, pt, fn in pp:
        if nt != net:
            continue
        f = (fn or "").split("/")[0].strip()
        if pt == "power_in" or (pt != "power_out" and (SUPPLY_PIN.match(f) or VOLT_PIN.match(f))):
            return True
        if not f and not pt and (net in rails or _unannotated_pin_sem(net) == "supply"):
            return True
    return False


OUT_PIN = re.compile(r"^(V?OUT\w*|VO|VREG|LDO\w*|BAT\w*|VSYS|SYS|CHG\w*)$", re.I)
K_IPC = {True: 0.048, False: 0.024}      # IPC-2221: I = k dT^0.44 A^0.725 (A in mil^2), external / internal


def ipc_dT(I, w_mm, t_mm, external=True):
    """Temperature rise (K) of a track of width w and thickness t carrying I (IPC-2221)."""
    A = (w_mm / 0.0254) * (t_mm / 0.0254)
    if I <= 0 or A <= 0:
        return 0.0
    return (I / (K_IPC[bool(external)] * A ** 0.725)) ** (1 / 0.44)


class Plan:
    """The DC power flow of one board: feeds per rail, loads, their current parameters."""

    def __init__(self):
        self.feeds = {}         # rail -> dict(kind, ...)
        self.loads = []         # dict(ref, rail, sup, gnd, key | (cell, share))
        self.params = []        # Params of the DC band (load currents, efficiencies)
        self.notes = []
        self.dc_pads = set()
        self.self_loads = []    # dict(ref, rail, key, pads): parts that power themselves from off the board (heat only)


def _pads(board):
    """{ref: [(number, net, pintype, pinfunction)]}. Footprints that share a reference are one part (a module's
    edge pins and its back pins, a split symbol): their pads are merged, as the copper model's pad tokens (REF.NUM,
    kae.em.kicad) merge them. Keeping only the last footprint lost a Teensy's supply and ground pins."""
    out = {}
    for f in board.footprints:
        out.setdefault(f.ref, []).extend((p.number, p.net, p.pintype or "", (p.pinfunction or "").split("/")[0].strip())
                                         for p in f.pads if p.net)
    return out


def plan(board, brief, bd, P, srcs, intent=None):
    """The DC plan from the brief (rails, sources, cells), the circuit model's ground set and the AC
    ledger P ({source name: {param: Param}}) for the cells' operating points."""
    from kae.route.critical_modules import Ctx
    from kae.route.critical_rails import load_current, source_rating
    ctx = Ctx(None, None, brief, board)
    pl = Plan()
    nets = brief.get("nets") or {}
    parts = brief.get("parts") or {}
    ref_of = {u: p["ref"] for u, p in parts.items()}
    uuid_of = {p["ref"]: u for u, p in parts.items()}
    pads = _pads(board)
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
        fv = (facts.get(net) or {}).get("V_V")
        if isinstance(fv, (int, float)) and fv > 0:
            return float(fv)
        v = (nets.get(net) or {}).get("volts")
        return abs(float(v)) if v else None

    # commutation cells: their parts, rails and operating points
    cells = {}
    src_of_cell = {s.meta.get("cell"): s.name for s in srcs if s.kind == "cell"}
    for st in brief.get("structures") or []:
        if st.get("kind") != "commutation_cell" or st.get("class") not in ("boost", "buck"):
            continue
        sname = src_of_cell.get(st["id"])
        if sname is None or sname not in P:
            continue
        sw = st.get("switches") or {}
        c = dict(id=st["id"], cls=st["class"], src=sname, vin=st.get("vin"), vout=st.get("vout"), sw=st.get("sw"),
                 ctrl=ref_of.get(st.get("controller")), rect=ref_of.get(sw.get("rectifier")),
                 parts={ref_of.get(u) for u, _ in st.get("loop") or []} | {ref_of.get(st.get("controller")),
                                                                         ref_of.get(st.get("inductor"))})
        c["parts"] |= {ref_of.get(u) for u in st.get("caps") or []}
        c["parts"].discard(None)
        cells[st["id"]] = c
    cell_parts = set().union(*[c["parts"] for c in cells.values()]) if cells else set()
    # feeds: what delivers each rail's current
    over = {n: (d or {}).get("source") for n, d in ((intent or {}).get("nets") or {}).items() if (d or {}).get("source")}
    for r in sorted(rails):
        d = nets.get(r) or {}
        cell = next((c for c in cells.values() if c["vout"] == r), None)
        src_ref = over.get(r) or ref_of.get((d.get("source") or {}).get("part"))
        if cell is not None:
            pl.feeds[r] = dict(kind="cell", cell=cell, ref=cell["ctrl"])
            continue
        if src_ref is None or src_ref not in pads:
            pl.notes.append(f"{r}: no source part; its loads are not in the DC band")
            continue
        kind, sub = (parts.get(uuid_of.get(src_ref)) or {}).get("kind"), (parts.get(uuid_of.get(src_ref)) or {}).get("subtype")
        ins = [(n, net) for n, net, pt, fn in pads[src_ref] if net in rails and net != r and
               (pt == "power_in" or SUPPLY_PIN.match(fn))] if kind in ("ic", "module") else []
        fr = (facts.get(r) or {}).get("from")
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
                fe = (facts.get(r) or {}).get("eta")
                if isinstance(fe, list) and len(fe) == 2 and 0 < min(fe) <= max(fe) <= 1:
                    f["eta"] = Param(f"dc:{src_ref}", "eta", (fe[0] + fe[1]) / 2, fe[0], fe[1], "", "intent",
                                     "the intent file")
                else:
                    f["eta"] = Param(f"dc:{src_ref}", "eta", ETA[1], ETA[0], ETA[2], "", "prior",
                                     "efficiency of a switching regulator without a cell model (class range)")
                pl.params.append(f["eta"])
            pl.feeds[r] = f
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
            pl.feeds[r] = dict(kind="external", ref=src_ref, out=on(src_ref, r), gnd=gnd_pads(src_ref))
    # feeds that feed each other in a cycle (AMP_VDD from PCM_AVDD through U2, PCM_AVDD from AMP_VDD through U2: an
    # intent fact read the regulator backwards) have no way in for their current, and the DC flow cannot close.
    # Power cannot circulate among regulators, so one link is wrong: the one whose part's pins least say it outputs on
    # its rail and takes its input from the other (power_out or an OUT name there, power_in or an IN name on its input)
    # is dropped, the intent's fact before the brief's; the rail it fed is then fed by a connector on it with a ground
    # pad (the board's way in), else by nothing.
    def evidence(r, f):
        out_ = sum(1 for _, nt, pt, fn in pads.get(f["ref"], []) if nt == r and (pt == "power_out" or OUT_PIN.match(fn)))
        in_ = sum(1 for _, nt, pt, fn in pads.get(f["ref"], []) if nt == f.get("rin") and (pt == "power_in" or SUPPLY_PIN.match(fn)))
        bad = sum(1 for _, nt, pt, fn in pads.get(f["ref"], []) if nt == r and (pt == "power_in" or SUPPLY_PIN.match(fn)))
        return (bool(out_) + bool(in_) - bool(bad), r not in over)
    for _ in range(len(pl.feeds)):
        cyc = None
        for r0 in sorted(pl.feeds):
            seen, x = [], r0
            while x in pl.feeds and x not in seen and pl.feeds[x]["kind"] in ("linear", "switching"):
                seen.append(x)
                x = pl.feeds[x].get("rin")
            if x == r0 and seen:
                cyc = seen
                break
        if not cyc:
            break
        r = min(cyc, key=lambda q: (evidence(q, pl.feeds[q]), q))
        f = pl.feeds.pop(r)
        conns = [(sum(1 for _, nt, _, _ in pp if nt == r), ref) for ref, pp in pads.items()
                 if (parts.get(uuid_of.get(ref)) or {}).get("kind") == "connector" and any(nt == r for _, nt, _, _ in pp)
                 and gnd_pads(ref)]
        if conns:
            ref = max(conns)[1]
            pl.feeds[r] = dict(kind="external", ref=ref, out=on(ref, r), gnd=gnd_pads(ref))
        pl.notes.append(f"{r}: feeds {' -> '.join(cyc)} form a cycle with no way in; {f['ref']} as {r}'s source from "
                        f"{f.get('rin')} contradicts its pins most and is dropped"
                        + (f"; {pl.feeds[r]['ref']} (a connector on it) feeds it" if r in pl.feeds else ""))
    # a regulator whose input net has no feed of its own: the DC flow enters the board at it (its input
    # current has nowhere to come from in the copper); its loss still comes from its input's voltage
    for r, f in pl.feeds.items():
        if f["kind"] in ("linear", "switching") and f.get("rin") not in pl.feeds:
            f["flow_external"] = True
            f["gnd"] = f.get("gnd") or gnd_pads(f["ref"])
            pl.notes.append(f"{r}: {f['ref']}'s input {f.get('rin')} has no feed; the DC flow enters at {f['ref']}")
    # an external feed returns at its own ground pads, else at the connectors' (the board's way out)
    conn_g = [t for ref, pp in pads.items() if (parts.get(uuid_of.get(ref)) or {}).get("kind") == "connector"
              for t in tok(ref, [n for n, net, _, _ in pp if net in grounds])]
    for r in list(pl.feeds):
        f = pl.feeds[r]
        if (f["kind"] == "external" or f.get("flow_external")) and not f["gnd"]:
            if conn_g:
                f["gnd"] = conn_g
                pl.notes.append(f"{r}: source {f['ref']} has no ground pad; its return is taken at the connectors' ground")
            else:
                del pl.feeds[r]
                pl.notes.append(f"{r}: source {f['ref']} has no ground pad and the board no connector ground; left out")
    # what each feed can deliver (its class rating, E5): a source current-limits, so no corner draws more
    for r, f in pl.feeds.items():
        if f["kind"] != "cell":
            f["rating"] = source_rating(ctx, uuid_of.get(f["ref"]), r, {})
    feeders = {f["ref"] for f in pl.feeds.values()}

    def consumer(ref):
        p = parts.get(uuid_of.get(ref)) or {}
        k, sb = p.get("kind"), p.get("subtype")
        return (k == "module" and sb not in LINEAR + SWITCHING + ("charge_pump",)) or (k == "ic" and sb in CONSUMER_SUB)

    def part_share(ref, r):
        """Rail r's share of part ref's supply pads over the fed rails it draws from (not one it feeds)."""
        n = {r2: len(supply(ref, r2)) for r2 in pl.feeds if pl.feeds[r2].get("ref") != ref
             and any(net == r2 for _, net, _, _ in pads.get(ref, []))}
        return n.get(r, 0) / sum(n.values()) if sum(n.values()) else 1.0
    # loads: parts that draw from a rail and return at their own ground
    shares = {}
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
            stated = ((intent or {}).get("parts") or {}).get(ref, {}).get("I_A") is not None
            if not g and kind == "connector" and stated and conn_g_all:
                g = [t for t in conn_g_all if not t.startswith(ref + ".")]
                if g:
                    pl.notes.append(f"{r}: export {ref} has no ground pad; its return is taken at the other connectors' ground")
            if not g:
                continue
            if kind in LOAD_PRIOR:
                a = LOAD_PRIOR[kind] if supply(ref, r) and draws_from(pp, r, rails) or kind == "oscillator" else 0.0
            else:
                a = load_current(ctx, u, r, {}, draws=draws_from(pp, r, rails) if kind in ("ic", "module") else None)
            if kind == "connector":
                a = 0.1 * a                          # an export: a tenth of its rating, typically
            if a <= 0:
                continue
            ld = dict(ref=ref, rail=r, sup=supply(ref, r), gnd=g, prior=a)
            iv = ((intent or {}).get("parts") or {}).get(ref, {}).get("I_A")
            # the intent states a part's whole current: on several rails it is split by their share of the part's
            # supply pads (an MCU's 3V3 pins carry its current, not its VBUS-detect pin as well)
            ld["part_share"] = share = part_share(ref, r)
            if pl.feeds[r]["kind"] == "cell":
                shares.setdefault(r, []).append(ld)
            else:
                if iv is not None:
                    lo, hi = (iv if isinstance(iv, list) else [iv, iv])
                    lo, hi = lo * share, hi * share
                    p = Param(f"dc:{ref}@{r}", "I_A", math.sqrt(lo * hi) if lo > 0 else hi, lo, hi, "A", "intent",
                              "the intent file" + (f" ({share:.0%} of the part's current: its share of supply pads)" if share < 1 else ""))
                else:
                    lo, hi = (a / 10, 5 * a) if kind == "connector" else (a / 3, 3 * a)
                    p = Param(f"dc:{ref}@{r}", "I_A", a, lo, hi, "A", "prior",
                              f"{kind} load current by class (E5) {'0.01-0.5 x its rating' if kind == 'connector' else 'x/3 .. x3'}")
                pl.params.append(p)
                ld["key"] = (p.subject, p.name)
            pl.loads.append(ld)
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
            lo, hi = iv if isinstance(iv, list) else [iv, iv]
            p = Param(f"dc:{ref}@{r}", "I_A", math.sqrt(lo * hi) if lo > 0 else hi, lo, hi, "A", "intent",
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
    for r, lds in shares.items():
        tot = sum(ld["prior"] for ld in lds)
        for ld in lds:
            ld["share"] = ld["prior"] / tot
            ld["cell"] = pl.feeds[r]["cell"]
    for r, f in pl.feeds.items():
        if f["kind"] == "cell" and r not in shares:
            pl.notes.append(f"{r}: fed by {f['cell']['id']} but no load with a ground pad found; the cell's DC flow is not modelled")
    pl.dc_pads = {t for ld in pl.loads for t in ld["sup"] + ld["gnd"]} | {t for sl in pl.self_loads for t in sl["pads"]}
    for f in pl.feeds.values():
        for k in ("out", "gnd", "inp"):
            pl.dc_pads |= set(f.get(k) or [])
        if f["kind"] == "cell":
            c = f["cell"]
            for ref in (c["ctrl"], c["rect"]):
                if ref:
                    pl.dc_pads |= {f"{ref}.{n}" for n, net, _, _ in pads.get(ref, [])
                                   if net in rails or net in grounds or net == c["sw"]}
    pl.pads = pads
    pl.grounds = grounds
    pl.volts = {r: volts(r) for r in rails}
    return pl


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


def load_currents(pl, cv):
    """Each load's current at one corner: its parameter (or its share of a cell's output), scaled down
    where a rail on its chain would carry more than its feed's rating (the feed current-limits)."""
    xs = []
    for ld in pl.loads:
        if "cell" in ld:
            IL, D = _cell_vals(ld["cell"], cv)
            xs.append(ld["share"] * (IL * (1 - D) if ld["cell"]["cls"] == "boost" else IL))
        else:
            xs.append(cv.get(ld["key"], 0.0))
    # each rail's total, through the chain's conversion ratios
    tot = {}
    for ld, x in zip(pl.loads, xs):
        a = x
        for r in _chain(pl, ld["rail"]):
            tot[r] = tot.get(r, 0.0) + a
            a *= _ratio(pl, r, cv)
    out = []
    for ld, x in zip(pl.loads, xs):
        k = 1.0
        for r in _chain(pl, ld["rail"]):
            R = pl.feeds[r].get("rating")
            if R and tot.get(r, 0.0) > R:
                k = min(k, R / tot[r])
        out.append(x * k)
    return out


def _ratio(pl, r, cv):
    """Input current per output current of rail r's feed."""
    f = pl.feeds[r]
    if f["kind"] == "switching":
        return (pl.volts.get(r) or 1.0) / (cv.get((f["eta"].subject, "eta"), ETA[1]) * (pl.volts.get(f["rin"]) or 1.0))
    if f["kind"] == "cell":
        _, D = _cell_vals(f["cell"], cv)
        return 1 / (1 - D) if f["cell"]["cls"] == "boost" else D
    return 1.0


def injections(pl, cv):
    """{pad: A} of the DC power flow at one corner. cv: {source name: {param: value}} for the cells'
    corners plus {(subject, name): value} for the DC band's own parameters."""
    inj = {}
    pads = pl.pads

    def on(ref, net):
        return [f"{ref}.{n}" for n, nt, _, _ in pads.get(ref, []) if nt == net]

    def gnd(ref):
        return [f"{ref}.{n}" for n, nt, _, _ in pads.get(ref, []) if nt in pl.grounds]

    def deliver(r, x, depth=0):
        """x amperes into rail r from its feed, walked back to the board's input."""
        f = pl.feeds.get(r)
        if f is None or depth > 8 or x == 0:
            return
        k = f["kind"]
        if f.get("flow_external"):
            _add(inj, f["out"], x)
            _add(inj, f["gnd"], -x)
            return
        if k == "external":
            _add(inj, f["out"], x)
            _add(inj, f["gnd"], -x)
        elif k == "linear":
            _add(inj, f["out"], x)
            _add(inj, f["inp"], -x)
            deliver(f["rin"], x, depth + 1)
        elif k == "switching":
            vo, vi = pl.volts.get(r) or 1.0, pl.volts.get(f["rin"]) or 1.0
            xin = x * vo / (cv.get((f["eta"].subject, "eta"), ETA[1]) * vi)
            _add(inj, f["out"], x)
            _add(inj, f["inp"], -xin)
            _add(inj, f["gnd"], xin - x)
            deliver(f["rin"], xin, depth + 1)
        elif k == "cell":
            c = f["cell"]
            _, D = _cell_vals(c, cv)
            ctrl, sw = c["ctrl"], c["sw"]
            if c["cls"] == "boost":
                IL = x / (1 - D)
                _add(inj, on(ctrl, sw), -D * IL)                 # the switch: D I_L from the switch node
                _add(inj, gnd(ctrl), D * IL)                     # to ground
                if not c["rect"]:                                # synchronous: the rectifier inside too
                    _add(inj, on(ctrl, sw), -(1 - D) * IL)
                    _add(inj, on(ctrl, r), x)
                deliver(c["vin"], IL, depth + 1)                # the input feeds the inductor (lumped)
            else:
                _add(inj, on(ctrl, c["vin"]), -D * x)            # the high side: D I_out from the input
                _add(inj, on(ctrl, sw), D * x)
                if not c["rect"]:
                    _add(inj, gnd(ctrl), -(1 - D) * x)
                    _add(inj, on(ctrl, sw), (1 - D) * x)
                deliver(c["vin"], D * x, depth + 1)
    for ld, x in zip(pl.loads, load_currents(pl, cv)):
        _add(inj, ld["sup"], -x)
        _add(inj, ld["gnd"], x)
        deliver(ld["rail"], x)
    return inj


def planned_injections(board, intent, brief=None):
    """{"REF.NUM": A} of the DC power flow at the typical point of every parameter, from the plan the
    physics evaluator scores (kae.excite.evaluate: rails, feeds, regulators, loads and their currents
    under the operating facts `intent`), positive into the copper; {} when the plan has no rail with a
    source and a load. For callers outside the evaluator (power copper's THT neck); no field solve."""
    from kae.circuit import brief as B
    from . import models as M
    from . import sources as S
    from .evaluate import ledger_for
    from kae.board import pinfacts as PF
    PF.apply(board, (intent or {}).get("pins"))         # the schematic's pin facts, as the evaluator applies them
    brief = brief or B.build(board)
    bd = M.build(board, brief)
    srcs = S.add_all(bd, brief)
    P, _ = ledger_for(bd, brief, srcs, intent)
    pl = plan(board, brief, bd, P, srcs, intent)
    cv = {(p.subject, p.name): p.typ for p in pl.params}
    for s_ in srcs:
        if s_.kind == "cell":
            cv[s_.name] = {k: getattr(v, "typ", v) for k, v in (P.get(s_.name) or {}).items()}
    return {k: float(v) for k, v in injections(pl, cv).items() if v}


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
    P_del = sum(xk * (pl.volts.get(ld["rail"]) or 3.3) for ld, xk in zip(pl.loads, xs))
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
        else:
            src_r, src_g = f["out"], f["gnd"] or []
        vs, vl = _mean(V, src_r), _mean(V, ld["sup"])
        if vs is None or vl is None:
            continue
        dv = vs - vl
        gs, gl = _mean(V, src_g), _mean(V, ld["gnd"])
        if gs is not None and gl is not None:
            dv += gl - gs
        b = pl.drop_share * (pl.volts.get(ld["rail"]) or 3.3)
        # the drop is what the load loses of its source's voltage, so never below 0. The signed sum can be negative
        # by physics, not by a reference choice: another rail's return current through shared ground copper (or a
        # source whose own ground pin carries current) puts the load's ground below the source's, and the load then
        # sees more than the source's voltage. That is no drop (and no credit against one); the signed value is kept
        # for the reader (`drops_signed`).
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

    from kae.em.kicad import _arc_points
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
