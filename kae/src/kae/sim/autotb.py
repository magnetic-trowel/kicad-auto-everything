# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A default testbench from the board and its brief, with no LLM (testbench.py format).

Every number the board does not state is an interval prior with its source; what cannot be known
becomes `*@unknown` (the test still runs and reports values, but cannot pass or fail). Tests:

- rail_dc:<net>    DC voltage at each load pin (between its supply and ground pins) with the loads
                   drawing the IC current prior; requirement: within 3% of the rail voltage (prior).
- rail_step:<net>  the same loads stepping from 20% to 100% in T_STEP, with the board's capacitors on
                   the rail; requirement: within 5% (prior). An ideal source: regulator response excluded.
- i2c:<net>        open-drain bus: the board's pull-up, routed copper and a pin capacitance per device;
                   30-70% rise time at each pin against 1000 / 300 / 120 ns (UM10204 modes).
- sw:<cell>        switch-node peak of a buck cell: complementary switches in the controller's place,
                   the inductor held at I_OUT, C_oss on the switch node; against 85% of the next standard
                   rating above 1.25 V_in (kae.physics.priors.v_abs_rating).
- pair:<p>/<n>     delay from a driver pin to each other pin of a differential pair, and the skew.
"""
from __future__ import annotations

import re

from kae.physics import priors as PR

from .testbench import Param, Require, Test, fmt

DROP_DC, DROP_STEP = 0.03, 0.05
I2C_MODES = (("standard", 1000e-9), ("fast", 300e-9), ("fast_plus", 120e-9))


def _safe(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


def _probe(t, m, a, b):
    """`v(<node>)` for a single-ended probe, else a B-source probe node holding v(a) - v(b)
    (batch-mode .meas cannot read v(a,b))."""
    if b == "0":
        return f"v({a})"
    node = f"p_{m.lower()}"
    t.lines.append(f"B{m} {node} 0 V=v({a})-v({b})")
    return f"v({node})"


class _Ctx:
    def __init__(self, board, brief, design):
        self.b, self.brief, self.design = board, brief, design
        self.nets = brief.get("nets") or {}
        self.parts = brief.get("parts") or {}
        self.gnd = {n for n, r in self.nets.items() if (r or {}).get("role") == "ground"}
        self.by_uuid = {f.uuid: f for f in board.footprints}

    def kind(self, fp):
        return (self.parts.get(fp.uuid) or {}).get("kind") or ""

    def pins_on(self, fp, net):
        return [p.number for p in fp.pads if p.net == net]

    def gnd_pin(self, fp):
        g = [p.number for p in fp.pads if p.net in self.gnd]
        return f"<{fp.ref}.{g[0]}>" if g else "0"

    def gnd_nets(self):
        return sorted(self.gnd)


PASSIVE_KINDS = {"resistor", "capacitor", "inductor", "ferrite", "connector", "test_point", "mounting_hole",
                 "fiducial", "jumper", "switch", "diode", "tvs", "fuse", "crystal", "unknown", ""}
SERIES_KINDS = {"ferrite", "inductor", "resistor", "fuse", "jumper"}
STEP_KINDS = {"ic", "module"}      # loads whose supply current steps in nanoseconds (logic)


def _root(c, net):
    """Follow a derived rail up through series parts (ferrite, inductor, resistor, fuse) to the rail
    whose source is not one: (source footprint, source kind, [nets on the way], [series parts])."""
    nets, series = [net], []
    while True:
        src = ((c.nets.get(nets[-1]) or {}).get("source") or {})
        sfp = c.by_uuid.get(src.get("part")) if src.get("part") else None
        if sfp is None or c.kind(sfp) not in SERIES_KINDS or len(series) > 4:
            return sfp, src.get("kind"), nets, series
        up = [p.net for p in sfp.pads if p.net and p.net != nets[-1]]
        if len(up) != 1 or (c.nets.get(up[0]) or {}).get("role") != "rail" or up[0] in nets:
            return sfp, src.get("kind"), nets, series
        series.append(sfp)
        nets.append(up[0])


def rail_tests(c, net):
    r = c.nets.get(net) or {}
    v = r.get("volts")
    sfp, skind, chain, series = _root(c, net)
    out = []
    loads = []
    for fp in c.b.footprints:
        if (sfp is not None and fp.uuid == sfp.uuid) or fp in series:
            continue
        if c.kind(fp) in PASSIVE_KINDS:
            continue
        ps = c.pins_on(fp, net)
        if ps:
            loads.append((fp, ps))
    src = {"kind": skind}
    for kind in ("rail_dc", "rail_step"):
        t = Test(id=f"{kind}:{net}", kind=kind, nets=chain + c.gnd_nets(), extract="power")
        if series:
            t.notes.append(f"derived rail: fed from {chain[-1]} through {', '.join(f.ref for f in series)} "
                           "(board parts, priors where unvalued)")
        if v is None:
            t.unknown.append("rail voltage not stated (no voltage in its name or parts); values are reported, not judged")
        if sfp is None:
            t.unknown.append("no source found for this rail")
            out.append(t)
            continue
        if not loads:
            t.unknown.append("no IC or module draws from this rail")
            out.append(t)
            continue
        V = v if v is not None else 1.0
        sp = c.pins_on(sfp, chain[-1])
        t.notes.append(f"source {sfp.ref} ({src.get('kind') or 'unknown kind'}, inferred) as an ideal {fmt(V)} V "
                       f"source at pin {sp[0]}")
        t.params["SCALE"] = Param("SCALE", 1.0, 0.2, 2.0, 'prior:"load current x0.2 to x2 of the IC prior"')
        t.lines.append(".param SCALE=1")
        if kind == "rail_step":
            t.params["T_STEP"] = Param("T_STEP", 5e-9, 1e-9, 20e-9, 'prior:"digital load step edge"')
            t.lines.append(".param T_STEP=5n")
        t.lines.append(f"Vsrc <{sfp.ref}.{sp[0]}> {c.gnd_pin(sfp)} DC {fmt(V)}")
        meas = []
        conv = {s.get("controller"): s for s in c.brief.get("structures") or []
                if s.get("kind") == "commutation_cell" and s.get("rail") == net}
        for fp, ps in loads:
            if fp.uuid in conv:
                iout = ((conv[fp.uuid].get("excite") or {}).get("I")) or 1.0
                itot = 0.5 * iout
                t.notes.append(f"{fp.ref}: converter input, {fmt(itot)} A prior (I_out {fmt(iout)} A x duty 0.5) "
                               f"over {len(ps)} pin(s) on {net}")
            else:
                itot = PR.ic_current_prior(len(fp.pads))
                t.notes.append(f"{fp.ref}: {fmt(itot)} A prior ({len(fp.pads)} pins) over {len(ps)} pin(s) on {net}")
            per = itot / len(ps)
            gp = c.gnd_pin(fp)
            steps = c.kind(fp) in STEP_KINDS and fp.uuid not in conv
            if kind == "rail_step" and not steps:
                t.notes.append(f"{fp.ref} ({c.kind(fp)}) held at its DC current: only digital ICs and modules step in ns")
            for p in ps:
                nm = _safe(f"I_{fp.ref}_{p}")
                if kind == "rail_dc" or not steps:
                    t.lines.append(f"{nm} <{fp.ref}.{p}> {gp} DC {{{fmt(per)}*SCALE}}")
                else:
                    lo, hi = f"{{{fmt(0.2 * per)}*SCALE}}", f"{{{fmt(per)}*SCALE}}"
                    t.lines.append(f"{nm} <{fp.ref}.{p}> {gp} PULSE({lo} {hi} 1u {{T_STEP}} {{T_STEP}} 1u 4u)")
                m = _safe(f"v_{fp.ref}_{p}")
                meas.append((m, _probe(t, m, f"<{fp.ref}.{p}>", gp)))
        if kind == "rail_dc":
            t.lines.append(".tran 10n 2u")
            for m, probe in meas:
                t.lines.append(f".meas tran {m} MIN {probe} from=1u to=2u")
        else:
            t.lines.append(".tran 0.2n 2.5u")
            for m, probe in meas:
                t.lines.append(f".meas tran {m} MIN {probe} from=0.9u to=2.5u")
        lim = DROP_DC if kind == "rail_dc" else DROP_STEP
        if v is not None:
            for m, _ in meas:
                t.requires.append(Require(m, ">=", (1 - lim) * v, f'prior:"within {lim:.0%} of {fmt(v)} V"'))
        else:
            t.info.extend(m for m, _ in meas)
        out.append(t)
    return out


def i2c_tests(c):
    out = []
    for net, r in c.nets.items():
        if (r or {}).get("subrole") != "i2c":
            continue
        t = Test(id=f"i2c:{net}", kind="i2c", nets=[net] + c.gnd_nets())
        pull = None
        for p in c.design.parts:
            if p.kind != "R":
                continue
            nets = [c.design.pin_net.get(k) for k in p.pins]
            if net in nets:
                other = nets[1 - nets.index(net)]
                ov = (c.nets.get(other) or {}).get("volts")
                if (c.nets.get(other) or {}).get("role") == "rail" and ov:
                    pull = (p, other, ov)
                    break
        bus = []
        for fp in c.b.footprints:
            if c.kind(fp) in ("ic", "module", "connector"):
                for pn in c.pins_on(fp, net):
                    bus.append((fp, pn))
        if len(bus) < 1:
            t.unknown.append("no device pins on the bus")
            out.append(t)
            continue
        t.params["C_PIN"] = Param("C_PIN", 5e-12, 3e-12, 10e-12, 'prior:"UM10204 allows up to 10 pF per pin"')
        t.lines.append(".param C_PIN=5p")
        if pull is None:
            # off-board pull-up: a known 1 kohm at the connector pin measures the bus capacitance,
            # which gives the largest pull-up each mode allows (capability)
            t.unknown.append("no pull-up on this board (internal or off-board): rise time not judged; "
                             "bus capacitance and the largest pull-up per mode are reported")
            at = next(((fp, pn) for fp, pn in bus if c.kind(fp) == "connector"), bus[0])
            t.notes.append(f"probe pull-up 1 kohm to 1 V at {at[0].ref} pin {at[1]}")
            t.lines.append("Vpu vpu 0 DC 1")
            t.lines.append(f"Rpu vpu <{at[0].ref}.{at[1]}> 1k")
            V = 1.0
        else:
            p, rail, V = pull
            t.notes.append(f"pull-up {p.ref} {fmt(p.value)} ohm to {rail} ({fmt(V)} V, from its name)")
            t.lines.append(f"Vpu <{rail}> 0 DC {fmt(V)}")
        dfp, dp = bus[0]
        t.notes.append(f"driver: {dfp.ref} pin {dp} (open drain, 100 kHz)")
        t.lines.append(".model swod sw vt=0.5 vh=0.1 ron=30 roff=1e9")
        t.lines.append(f"Sdrv <{dfp.ref}.{dp}> {c.gnd_pin(dfp)} ctl 0 swod")
        t.lines.append("Vctl ctl 0 PULSE(1 0 0 5n 5n 5u 10u)")
        meas = []
        for k, (fp, pn) in enumerate(bus):
            t.lines.append(f"Cpin{k} <{fp.ref}.{pn}> {c.gnd_pin(fp)} {{C_PIN}}")
            m = _safe(f"tr_{fp.ref}_{pn}")
            meas.append(m)
            t.lines.append(f".meas tran {m} TRIG v(<{fp.ref}.{pn}>) VAL={fmt(0.3 * V)} RISE=2 "
                           f"TARG v(<{fp.ref}.{pn}>) VAL={fmt(0.7 * V)} RISE=2")
        t.lines.append(".tran 2n 25u")
        if pull is None:
            t.info.extend(meas)
        else:
            for m in meas:
                t.requires.append(Require(m, "<=", 300e-9, 'prior:"Fast-mode (400 kHz) assumed; UM10204 t_r <= 300 ns"'))
        out.append(t)
    return out


def sw_tests(c):
    out = []
    for s in c.brief.get("structures") or []:
        if s.get("kind") != "commutation_cell":
            continue
        t = Test(id=f"sw:{s.get('id')}", kind="sw", extract="power")
        ctrl = c.by_uuid.get(s.get("controller"))
        rail, sw, gnd = s.get("rail"), s.get("sw"), s.get("gnd")
        vin = (c.nets.get(rail) or {}).get("volts")
        t.nets = [n for n in (rail, sw) if n] + c.gnd_nets()
        if s.get("class") != "buck":
            t.unknown.append(f"class {s.get('class')}: only buck stand-ins exist so far")
            out.append(t)
            continue
        if ctrl is None or not rail or not sw:
            t.unknown.append("controller, input rail or switch node not identified")
            out.append(t)
            continue
        if vin is None:
            t.unknown.append(f"input rail {rail} voltage not stated")
            out.append(t)
            continue
        vp, sp, gp = c.pins_on(ctrl, rail), c.pins_on(ctrl, sw), [p.number for p in ctrl.pads if p.net in c.gnd]
        if not (vp and sp and gp):
            t.unknown.append(f"controller {ctrl.ref} has no pin on {'input' if not vp else 'switch' if not sp else 'ground'}")
            out.append(t)
            continue
        ind = c.by_uuid.get(s.get("inductor"))
        vout = s.get("vout")
        if ind is not None:
            t.exclude = [ind.ref]
        rating = PR.v_abs_rating(vin)
        t.notes.append(f"{ctrl.ref} replaced by ideal complementary switches (pins {vp[0]} -> {sp[0]} -> {gp[0]}); "
                       f"inductor {ind.ref if ind else '?'} held as a current source")
        t.params["F_SW"] = Param("F_SW", 1.5e6, 0.5e6, 3e6, 'prior:"integrated buck switching frequency"')
        t.params["I_OUT"] = Param("I_OUT", 1.0, 0.2, 2.0, 'prior:"buck class default 1 A"')
        t.params["C_OSS"] = Param("C_OSS", 100e-12, 50e-12, 300e-12, 'prior:"integrated switch node capacitance"')
        t.lines += [".param F_SW=1.5meg", ".param I_OUT=1", ".param C_OSS=100p", ".param D=0.5"]
        rsrc = ((c.nets.get(rail) or {}).get("source") or {}).get("part")
        rfp = c.by_uuid.get(rsrc)
        if rfp is not None and c.pins_on(rfp, rail):
            t.lines.append(f"Vin_src <{rfp.ref}.{c.pins_on(rfp, rail)[0]}> {c.gnd_pin(rfp)} DC {fmt(vin)}")
        else:
            t.lines.append(f"Vin_src <{ctrl.ref}.{vp[0]}> <{ctrl.ref}.{gp[0]}> DC {fmt(vin)}")
            t.notes.append("no rail source found: ideal input at the controller's own pins (pessimistic: no input copper)")
        t.lines.append(".model swb sw vt=0.5 vh=0.05 ron=0.05 roff=1e6")
        t.lines.append(f"Shs <{ctrl.ref}.{vp[0]}> <{ctrl.ref}.{sp[0]}> hs 0 swb")
        t.lines.append(f"Sls <{ctrl.ref}.{sp[0]}> <{ctrl.ref}.{gp[0]}> ls 0 swb")
        t.lines.append("Vhs hs 0 PULSE(0 1 {0.02/F_SW} 1n 1n {D/F_SW-0.04/F_SW} {1/F_SW})")
        t.lines.append("Vls ls 0 PULSE(1 0 0 1n 1n {D/F_SW+0.02/F_SW} {1/F_SW})")
        t.lines.append(f"Coss <{ctrl.ref}.{sp[0]}> <{ctrl.ref}.{gp[0]}> {{C_OSS}}")
        if ind is not None and vout:
            ip = [p.number for p in ind.pads if p.net == sw]
            t.lines.append(f"Iind <{ind.ref}.{ip[0] if ip else sp[0]}> <{vout}> DC {{I_OUT}}")
            t.lines.append(f"Vout_hold <{vout}> 0 DC {fmt(vin * 0.5)}")
        else:
            t.lines.append(f"Iind <{ctrl.ref}.{sp[0]}> 0 DC {{I_OUT}}")
        sw_probe = _probe(t, "vsw", f"<{ctrl.ref}.{sp[0]}>", f"<{ctrl.ref}.{gp[0]}>")
        t.lines.append(".tran 0.05n {4/F_SW}")
        t.lines.append(f".meas tran vsw_max MAX {sw_probe} from={{1/F_SW}} to={{4/F_SW}}")
        t.lines.append(f".meas tran vsw_min MIN {sw_probe} from={{1/F_SW}} to={{4/F_SW}}")
        t.requires.append(Require("vsw_max", "<=", 0.85 * rating,
                                  f'prior:"85% of {fmt(rating)} V, the next standard rating above 1.25 x {fmt(vin)} V"'))
        t.info.append("vsw_min")
        out.append(t)
    return out


def pair_tests(c):
    out = []
    for dp in c.brief.get("diff_pairs") or []:
        pn, nn = dp.get("p"), dp.get("n")
        t = Test(id=f"pair:{pn}/{nn}", kind="pair", nets=[pn, nn] + c.gnd_nets())
        drv, rcv = {}, {}
        for net in (pn, nn):
            pins = [(fp, p) for fp in c.b.footprints for p in c.pins_on(fp, net)]
            conn = [x for x in pins if c.kind(x[0]) == "connector"]
            d = (conn or pins or [None])[0]
            if d is None or len(pins) < 2:
                t.unknown.append(f"{net}: fewer than two pins")
                break
            drv[net] = d
            rcv[net] = [x for x in pins if x != d]
        if t.unknown:
            out.append(t)
            continue
        t.notes.append(f"interface {dp.get('interface') or 'unknown'}; driver at the connector pin when there is one")
        t.params["T_R"] = Param("T_R", 200e-12, 50e-12, 1e-9, 'prior:"driver edge"')
        t.lines.append(".param T_R=200p")
        meas = []
        for k, net in enumerate((pn, nn)):
            fp, p = drv[net]
            t.lines.append(f"Vd{k} s{k} 0 PULSE(0 1 1n {{T_R}} {{T_R}} 20n 40n)")
            t.lines.append(f"Rd{k} s{k} <{fp.ref}.{p}> 50")
            for j, (rf, rp) in enumerate(rcv[net]):
                t.lines.append(f"Cr{k}_{j} <{rf.ref}.{rp}> {c.gnd_pin(rf)} 2p")
                m = _safe(f"td{k}_{rf.ref}_{rp}")          # td0: P, td1: N (net names may differ only in +/-)
                meas.append(m)
                t.lines.append(f".meas tran {m} TRIG v(s{k}) VAL=0.5 RISE=1 TARG v(<{rf.ref}.{rp}>) VAL=0.5 RISE=1")
        t.lines.append(".tran 2p 12n")
        t.info.extend(meas)
        out.append(t)
    return out


def generate(board, brief, design):
    c = _Ctx(board, brief, design)
    tests = []
    for net, r in c.nets.items():
        if (r or {}).get("role") == "rail":
            tests += rail_tests(c, net)
    tests += i2c_tests(c)
    tests += sw_tests(c)
    tests += pair_tests(c)
    return tests
