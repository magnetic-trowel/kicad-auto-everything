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
             load ground minus source ground) against DROP_SHARE of the rail voltage
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
SUPPLY_PIN = re.compile(r"^(V(CC|DD|IN|BAT|BUS|S|M|PP|IO|CORE|DDA|DDIO|USB|SYS|P|\+)\w*|AVDD|DVDD|IOVDD|PVDD|PVIN|"
                        r"AVCC|DVCC|VIN\d*|PWR|POWER|\+V\w*|V\+|VREG_IN|IN)$", re.I)
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


def _pads(board):
    """{ref: [(number, net, pintype, pinfunction)]}."""
    out = {}
    for f in board.footprints:
        out[f.ref] = [(p.number, p.net, p.pintype or "", (p.pinfunction or "").split("/")[0].strip()) for p in f.pads if p.net]
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
        if kind in ("ic", "module") and ins:
            # an IC that supplies this rail from another one converts: switching by its class, else linear
            rin = ins[0][1]
            outs = on(src_ref, r, lambda pt, fn: pt == "power_out" or OUT_PIN.match(fn)) or on(src_ref, r)
            f = dict(kind="switching" if sub in SWITCHING else "linear", ref=src_ref, rin=rin, out=outs,
                     inp=tok(src_ref, [n for n, net in ins if net == rin]), gnd=gnd_pads(src_ref))
            if f["kind"] == "switching":
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
    # an external feed returns at its own ground pads, else at the connectors' (the board's way out)
    conn_g = [t for ref, pp in pads.items() if (parts.get(uuid_of.get(ref)) or {}).get("kind") == "connector"
              for t in tok(ref, [n for n, net, _, _ in pp if net in grounds])]
    for r in list(pl.feeds):
        f = pl.feeds[r]
        if f["kind"] == "external" and not f["gnd"]:
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
    # loads: parts that draw from a rail and return at their own ground
    shares = {}
    for r in sorted(pl.feeds):
        for ref, pp in pads.items():
            if ref in feeders and pl.feeds[r]["ref"] == ref or ref in cell_parts or ref in feeders and any(
                    f.get("rin") == r and f["ref"] == ref for f in pl.feeds.values()):
                continue
            if not any(net == r for _, net, _, _ in pp):
                continue
            u = uuid_of.get(ref)
            kind = (parts.get(u) or {}).get("kind")
            if kind not in ("ic", "module", "connector"):
                continue
            g = gnd_pads(ref)
            if not g:
                continue
            a = load_current(ctx, u, r, {})
            if kind == "connector":
                a = 0.1 * a                          # an export: a tenth of its rating, typically
            if a <= 0:
                continue
            ld = dict(ref=ref, rail=r, sup=supply(ref, r), gnd=g, prior=a)
            iv = ((intent or {}).get("parts") or {}).get(ref, {}).get("I_A")
            if pl.feeds[r]["kind"] == "cell":
                shares.setdefault(r, []).append(ld)
            else:
                if iv is not None:
                    lo, hi = (iv if isinstance(iv, list) else [iv, iv])
                    p = Param(f"dc:{ref}@{r}", "I_A", math.sqrt(lo * hi) if lo > 0 else hi, lo, hi, "A", "intent", "the intent file")
                else:
                    lo, hi = (a / 10, 5 * a) if kind == "connector" else (a / 3, 3 * a)
                    p = Param(f"dc:{ref}@{r}", "I_A", a, lo, hi, "A", "prior",
                              f"{kind} load current by class (E5) {'0.01-0.5 x its rating' if kind == 'connector' else 'x/3 .. x3'}")
                pl.params.append(p)
                ld["key"] = (p.subject, p.name)
            pl.loads.append(ld)
    for r, lds in shares.items():
        tot = sum(ld["prior"] for ld in lds)
        for ld in lds:
            ld["share"] = ld["prior"] / tot
            ld["cell"] = pl.feeds[r]["cell"]
    for r, f in pl.feeds.items():
        if f["kind"] == "cell" and r not in shares:
            pl.notes.append(f"{r}: fed by {f['cell']['id']} but no load with a ground pad found; the cell's DC flow is not modelled")
    pl.dc_pads = {t for ld in pl.loads for t in ld["sup"] + ld["gnd"]}
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


def _mean(V, toks):
    vals = [V[t] for t in toks if t in V and V[t] is not None and np.isfinite(V[t])]
    return float(np.mean(np.real(vals))) if vals else None


def observe(pl, cv, V, info, tracks=None):
    """The DC observers at one corner from its solve: dict(loss=(u, P_cu, budget), drops=[(ref, rail, u,
    dV, budget)], heat=[(track index, u, dT, I)])."""
    inj = injections(pl, cv)
    net, x = info["net"], info["x"]
    P_all = float(np.real(sum(a * V[t] for t, a in inj.items() if t in V and V[t] is not None)))
    sysm = info["sys"]
    lo = net.off["l"]
    Il = x[lo:net.n_br]
    P_l = float(np.sum(np.abs(Il) ** 2 * np.real(sysm.zdiag[lo:net.n_br]))) if len(Il) else 0.0
    P_cu = max(P_all - P_l, 0.0)
    xs = load_currents(pl, cv)
    P_del = sum(xk * (pl.volts.get(ld["rail"]) or 0.0) for ld, xk in zip(pl.loads, xs))
    budget = pl.loss_share * P_del
    out = dict(loss=(P_cu / budget if budget > 0 else 0.0, P_cu, budget), drops=[], heat=[])
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
        out["drops"].append((ld["ref"], ld["rail"], dv / b, dv, b))
    if tracks:
        for k, (I, w_eff, t_mm, ext) in enumerate(tracks(x)):
            dT = ipc_dT(abs(I), w_eff, t_mm, ext)
            out["heat"].append((k, dT / pl.dT_max, dT, I))
    return out


def track_currents(bm, board_tracks, net, nets=None):
    """A function x -> [(I, w_eff mm, t mm, external)] per track: the current through the track's
    cross-section at its quarter points (the largest), summed over the cells of its net along the
    perpendicular within its width plus a cell, and the width of the net's copper there (a track inside
    a pour of its net counts the pour's width)."""
    m = bm.m
    p = m.pitch
    lname = [l.name for l in m.layers]
    samples, kept = [], []
    for t in board_tracks:
        if t.layer not in lname or (nets is not None and t.net not in nets) or t.net not in m.nets:
            continue
        l = lname.index(t.layer)
        nid = m.nets.index(t.net)
        (x0, y0), (x1, y1) = t.start, t.end
        L = math.hypot(x1 - x0, y1 - y0)
        if L < p:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        pts = []
        for q in (0.25, 0.5, 0.75):
            cx, cy = x0 + q * (x1 - x0), y0 + q * (y1 - y0)
            cells = []
            half = t.width / 2 + p
            for s in np.arange(-half, half + 1e-9, p):
                j, i = _cell(m, cx - uy * s, cy + ux * s)
                if 0 <= j < m.ny and 0 <= i < m.nx:
                    cells.append((j, i))
            pts.append(cells)
        samples.append((l, nid, ux, uy, pts, t.width, m.layers[l]))
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
        for l, nid, ux, uy, pts, w, layer in samples:
            best, weff = 0.0, w
            lab = m.lab[l]
            for cells in pts:
                I = 0.0
                cnt = 0
                for j, i in cells:
                    if lab[j, i] != nid:
                        continue
                    I += K[(l, "x")][j, i] * ux + K[(l, "y")][j, i] * uy
                    cnt += 1
                if abs(I) > abs(best):
                    best = I
                    weff = max(w, cnt * m.pitch)
            ext = l in (0, len(m.layers) - 1)
            out.append((best, weff, layer.t, ext))
        return out
    per_track.tracks = kept
    return per_track


def _cell(m, x, y):
    return int(math.floor((y - m.y0) / m.pitch)), int(math.floor((x - m.x0) / m.pitch))
