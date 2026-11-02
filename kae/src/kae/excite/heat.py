# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where the board's power turns into heat, and how hot each part gets (kae.em.thermal).

Heat, per corner of the ledger (the DC band's operating point, kae.excite.dc):

    copper       I^2 R of every bar of the DC flow, half to each of its two cells; a lumped part's own
                 DC loss (an inductor's winding) at its pads
    linear feed  (V_in - V_out) I at the regulator's pads (LDO, charger, load switch, series diode)
    switching    (1/eta - 1) P_out at the regulator's pads (no cell model)
    cell         switch conduction I_L^2 R_on D, switching V I_L (t_i + t_v) f_sw at the controller's
                 pads; the rectifier's V_f I_out at its pads
    load         V I of every load at its pads (an export through a connector leaves the board)
    ac           each part's loss from the switching harmonics (kae.excite.spectrum), when given

Each part's junction is its pads' mean temperature plus theta_jb P (a class prior by pin count); its
bound is its class's rating above ambient. Ambient, the surface's cooling and theta_jb are flagged
priors in the ledger; the intent file can state them.
"""
from __future__ import annotations

import numpy as np

from .beliefs import Param, corners, intent_value

T_MAX = {"ic": 125.0, "module": 85.0, "diode": 125.0, "transistor": 125.0, "inductor": 125.0,
         "capacitor": 105.0, "resistor": 125.0, "ferrite": 125.0, "led": 85.0, "connector": 85.0}
V_F = (0.3, 0.4, 0.5)           # V, a small Schottky's forward drop (lo, typ, hi)
R_ON = (0.03, 0.1, 0.3)         # ohm, an integrated switch's on-resistance without a datasheet value
# parts that pass the power they draw on to another rail or a battery: what they draw is not their heat
# (a charger's or regulator's own loss is its conversion loss, kae.excite.dc's feeds)
PASS_ON = ("charger", "regulator_linear", "regulator_switching", "regulator_module", "pmic", "load_switch",
           "charge_pump")


MODULE_AREA_MM2 = 1500.0   # a part this large (its body, else its footprint) has a board of its own that cools it


def rail_demand(dcp, rail, load_amps, depth=0):
    """Sustained current (A) a rail delivers: its loads (load_amps(ld) each) and, through the regulators and
    converters it feeds, what their rails deliver (a linear one passes its output current through; a switching
    one or a cell draws output power / (efficiency x input voltage))."""
    if depth > 6:
        return 0.0
    tot = sum(load_amps(ld) for ld in dcp.loads if ld["rail"] == rail)
    v_in = dcp.volts.get(rail) or 0.0
    for r2, f in dcp.feeds.items():
        c = f.get("cell")
        if f["kind"] == "cell" and c and c.get("vin") == rail and r2 != rail:
            d = rail_demand(dcp, r2, load_amps, depth + 1)
            tot += d * (dcp.volts.get(r2) or v_in) / (0.88 * max(v_in, 0.5)) if v_in else d
        elif f.get("rin") == rail and r2 != rail and f["kind"] in ("linear", "switching"):
            d = rail_demand(dcp, r2, load_amps, depth + 1)
            tot += d if f["kind"] == "linear" else d * (dcp.volts.get(r2) or v_in) / (0.85 * max(v_in, 0.5)) if v_in else d
    return tot


THETA_CS = (0.5, 0.2, 1.0)  # K/W, case to sink through grease or a thermal pad (class range)
THETA_JC = (5.0, 1.0, 20.0)  # K/W, junction to case without a datasheet value (power packages to small SMD)


def heatsinks(intent):
    """The operating facts' heat sinks (requirements.thermal.heatsinks): on a part ({part, theta_sa_C_W,
    theta_cs_C_W?, theta_jc_C_W?}) or under a region of one face ({side: top|bottom, region: "board" | [x0, y0,
    x1, y1] mm, theta_C_W (the whole interface to the sink) or h_W_m2K (a stronger surface cooling, e.g. a fan),
    T_C?: the sink's temperature, default ambient})."""
    th = (((intent or {}).get("requirements") or {}).get("thermal") or {})
    return [h for h in (th.get("heatsinks") or []) if isinstance(h, dict)]


def _rng(v):
    """(typ, lo, hi) of a number or [lo, hi] (typ: geometric mean), or None."""
    if isinstance(v, (int, float)) and v > 0:
        return float(v), float(v), float(v)
    if isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and x > 0 for x in v):
        lo, hi = sorted(map(float, v))
        return (lo * hi) ** 0.5, lo, hi
    return None


def _theta_jb(npins):
    """(typ, lo, hi) K/W junction to board by package size."""
    return (60.0, 30.0, 120.0) if npins <= 8 else (20.0, 10.0, 40.0)


def params(bd, dcp, P, intent=None):
    """The heat band's own parameters: ambient, surface cooling, rectifier drops, switches' R_on, every
    dissipating part's theta_jb."""
    from .beliefs import intent_value
    out = []
    iv = intent_value(intent, "requirements", "thermal", "T_amb_C")
    out.append(Param("heat", "T_amb_C", *(iv or (25.0, 25.0, 50.0)), "C", "intent" if iv else "prior",
                     "ambient air temperature" + ("" if iv else " (unknown: 25-50 C)")))
    air = _rng((((intent or {}).get("requirements") or {}).get("thermal") or {}).get("airflow_h_W_m2K"))
    out.append(Param("heat", "h_W_m2K", *air, "W/m^2/K", "intent", "forced air over the board (the intent file)") if air else
               Param("heat", "h_W_m2K", 12.0, 8.0, 20.0, "W/m^2/K", "prior",
                     "still-air cooling of the board's faces, convection plus radiation"))
    for k, hs in enumerate(heatsinks(intent)):
        why = hs.get("why") or "the intent file"
        if hs.get("part"):
            sa = _rng(hs.get("theta_sa_C_W"))
            if sa is None:
                continue
            cs = _rng(hs.get("theta_cs_C_W")) or THETA_CS
            jc = _rng(hs.get("theta_jc_C_W")) or intent_value(intent, "parts", hs["part"], "theta_jc_C_W") or THETA_JC
            out.append(Param(f"heat:{hs['part']}", "R_sink", sa[0] + cs[0] + jc[0], sa[1] + cs[1] + jc[1], sa[2] + cs[2] + jc[2],
                             "K/W", "intent", f"junction to air through its heat sink: theta_JC + theta_CS + theta_SA ({why})"))
        elif _rng(hs.get("theta_C_W")):
            t, lo, hi = _rng(hs["theta_C_W"])
            out.append(Param(f"heat:sink{k}", "G_W_K", 1 / t, 1 / hi, 1 / lo, "W/K", "intent",
                             f"{hs.get('side', 'bottom')} face to its heat sink ({why})"))
        elif _rng(hs.get("h_W_m2K")):
            out.append(Param(f"heat:sink{k}", "h_W_m2K", *_rng(hs["h_W_m2K"]), "W/m^2/K", "intent",
                             f"extra surface cooling over a region of the {hs.get('side', 'top')} face ({why})"))
    hot = {ld["ref"] for ld in dcp.loads if bd.part_kind.get(ld["ref"], ("",))[0] != "connector"}
    for f in dcp.feeds.values():
        hot |= {f["cell"]["ctrl"], f["cell"]["rect"]} if f["kind"] == "cell" else ({f["ref"]} if f["kind"] in ("linear", "switching") else set())
    for ref in sorted(r for r in hot if r):
        iv = intent_value(intent, "parts", ref, "theta_jb_C_W")       # from the part's datasheet, via the facts
        if iv:
            why = ((intent or {}).get("provenance") or {}).get("why", {}).get(f"parts.{ref}.theta_jb_C_W")
            out.append(Param(f"heat:{ref}", "theta_jb", *iv, "K/W", "intent", why or "the intent file"))
            continue
        npins = sum(1 for t in bd.net_of if t.rsplit(".", 1)[0] == ref)
        typ, lo, hi = _theta_jb(npins)
        out.append(Param(f"heat:{ref}", "theta_jb", typ, lo, hi, "K/W", "prior",
                         f"junction to board by package size ({npins} pins; class range), no datasheet value"))
    for f in dcp.feeds.values():
        if f["kind"] != "cell":
            continue
        c = f["cell"]
        if c["rect"]:
            out.append(Param(f"heat:{c['rect']}", "V_f_V", V_F[1], V_F[0], V_F[2], "V", "prior",
                             "rectifier forward drop (small Schottky class range)"))
        ron = (P.get(c["src"]) or {}).get("R_on")
        out.append(Param(f"heat:{c['ctrl']}", "R_on_ohm", ron.typ, ron.lo, ron.hi, "ohm", ron.source, ron.basis) if ron else
                   Param(f"heat:{c['ctrl']}", "R_on_ohm", R_ON[1], R_ON[0], R_ON[2], "ohm", "prior",
                         "switch on-resistance (integrated switch class range); no datasheet value"))
    return out


def part_heat(bd, dcp, cv, val, inj, ac_parts=None, losses=None):
    """{part ref: W} at one corner. cv: the DC band's corner (kae.excite.dc); val: {(subject, name): value}
    of the heat parameters; inj: the DC flow's injections at this corner. losses: a dict that gets each
    part's loss alone (the heat without the loads' own consumption, which is the board's purpose, not a loss)."""
    from . import dc as DC
    out = {}

    def add(ref, w, loss=True):
        if ref and w > 0:
            out[ref] = out.get(ref, 0.0) + w
            if loss and losses is not None:
                losses[ref] = losses.get(ref, 0.0) + w
    xs = DC.load_currents(dcp, cv)
    for ld, x in zip(dcp.loads, xs):
        pk = bd.part_kind.get(ld["ref"], ("", None))
        if pk[0] != "connector" and (pk[1] if len(pk) > 1 else None) not in PASS_ON:
            add(ld["ref"], x * (dcp.volts.get(ld["rail"]) or 0.0), loss=False)
    for r, f in dcp.feeds.items():
        if f["kind"] == "cell":
            c = f["cell"]
            v = cv.get(c["src"]) or {}
            IL, D, V = v.get("I_A", 1.0), min(max(v.get("D", 0.5), 0.02), 0.98), v.get("V_V", dcp.volts.get(r) or 5.0)
            I_out = IL * (1 - D) if c["cls"] == "boost" else IL
            ron = val.get((f"heat:{c['ctrl']}", "R_on_ohm"), R_ON[1])
            add(c["ctrl"], IL ** 2 * ron * D + V * IL * (v.get("t_i_s", 3e-9) + v.get("t_v_s", 1e-9)) * v.get("f_sw_Hz", 1e6))
            if c["rect"]:
                add(c["rect"], val.get((f"heat:{c['rect']}", "V_f_V"), V_F[1]) * (I_out if c["cls"] == "boost" else IL * (1 - D)))
            continue
        I_out = sum(inj.get(q, 0.0) for q in f.get("out") or [])
        if I_out <= 0:
            continue
        if f["kind"] == "linear":
            vi, vo = dcp.volts.get(f["rin"]) or 0.0, dcp.volts.get(r) or 0.0
            kind = bd.part_kind.get(f["ref"], ("",))[0]
            drop = val.get((f"heat:{f['ref']}", "V_f_V"), V_F[1]) if kind == "diode" else max(vi - vo, 0.0)
            if kind not in ("inductor", "ferrite", "resistor"):       # those dissipate in the DC copper model
                add(f["ref"], drop * I_out)
        elif f["kind"] == "switching":
            eta = cv.get((f["eta"].subject, "eta"), 0.85)
            add(f["ref"], (1 / eta - 1) * (dcp.volts.get(r) or 0.0) * I_out)
    for ref, w in (ac_parts or {}).items():
        add(ref, w)
    return out


LUMP_HEAT_KINDS = ("R", "L", "FB")     # lumped parts whose own DC loss is heat at their pads (a diode's is V_f I
                                        # in part_heat; a 'short' is a jumper stand-in)


def lumped_heat(net, x, kinds):
    """{lumped part name: W}: |I|^2 Re z(0) of the lumped branches of a DC solution x whose element kind
    (kinds: {name: kind}) is in LUMP_HEAT_KINDS (an inductor's winding, a ferrite, a shunt)."""
    out = {}
    I = x[:net.n_br]
    for k, (_, _, q) in enumerate(net.lump):
        if kinds.get(q.name) not in LUMP_HEAT_KINDS:
            continue
        w = abs(I[net.off["l"] + k]) ** 2 * q.z(0.0).real
        if w > 0 and np.isfinite(w):
            out[q.name] = out.get(q.name, 0.0) + float(w)
    return out


def copper_heat(net, x, shape):
    """Q (L, ny, nx) W: I^2 R of every bar of a DC solution x (amperes in its first n_br entries), half to
    each of its two cells; vias half to each landing."""
    Q = np.zeros(shape)
    I = np.real(x[:net.n_br])
    # via segments, in Network's order (consecutive landings of one via, skipping shorted pairs)
    k = net.off["v"]
    for land in net.via_nodes:
        for (la, ca), (lb, cb) in zip(land[:-1], land[1:]):
            if int(net.node[ca]) == int(net.node[cb]):
                continue
            p = I[k] ** 2 * net.R[k]
            Q[ca] += p / 2
            Q[cb] += p / 2
            k += 1
    assert k == net.off["l"], (k, net.off["l"])
    for o, (dj, di) in (("x", (0, 1)), ("y", (1, 0))):
        f = net.fil[o]
        a0, n = net.off[o], len(f["a"])
        if not n:
            continue
        p = I[a0:a0 + n] ** 2 * net.R[a0:a0 + n]
        lay = np.zeros(n, np.int64)
        for l, subs in enumerate(net.sub_of):
            lay[np.isin(f["s"], subs)] = l
        np.add.at(Q, (lay, f["j"], f["i"]), p / 2)
        np.add.at(Q, (lay, f["j"] + dj, f["i"] + di), p / 2)
    return Q


def evaluate(bm, b, bd, dcp, P, net_dc, op_dc, cps, srcs, n_corners, seed, tot, notes, intent=None, ac_parts=None,
             log=print, ledger=None, obs_out=None):
    """Thermal harms per part at every corner, added into the per-corner totals. ac_parts: {ref: [W per
    corner]} from the switching harmonics. obs_out: a list that gets kae.intent observations: each
    dissipating part's junction temperature (temp.junction, C) and its loss (loss.part, W) per corner."""
    import time
    from kae.em import solve as ES
    from kae.em import thermal as TH
    from . import dc as DC
    from . import harm as HA
    t0 = time.time()
    hp = params(bd, dcp, P, intent)
    for p in hp if ledger is not None else []:
        ledger.add(p)
    ncp = n_corners + 3
    hc = corners(hp, n=n_corners, seed=seed + 2)
    own = corners(dcp.params, n=n_corners, seed=seed + 1) if dcp.params else [{} for _ in range(ncp)]
    # a package's thermal time constant is seconds: its temperature follows the sustained draw, not a
    # radio's transmit burst or a boot peak, so the loads' currents sit at their typical point here (the
    # corners still span cooling, ambient, theta and the converters' operating points; the DC band keeps
    # the peaks for drop and heating of the copper)
    # A connector's export current that nothing states (a class prior, a tenth of its rating) is not
    # evidence of heat: a header's 3V3 pin usually feeds a sensor. Temperatures take such exports at
    # their low end (1% of the rating), so a guess cannot make a regulator overheat; a stated one counts.
    sustained = dict(own[0])
    exports = {ld["key"] for ld in dcp.loads if ld.get("key") and bd.part_kind.get(ld["ref"], ("",))[0] == "connector"}
    for p in dcp.params:
        if p.name != "I_A" or not str(p.subject).startswith("dc:"):
            continue
        ref = p.subject[3:].rsplit("@", 1)[0]
        iv = ((intent or {}).get("parts") or {}).get(ref, {}).get("I_sustained_A")
        if isinstance(iv, (int, float)) and iv >= 0:      # the intent's typical draw (its datasheet's)
            sustained[(p.subject, p.name)] = min(max(float(iv), p.lo), p.hi)
        elif (p.subject, p.name) in exports and p.source == "prior":
            sustained[(p.subject, p.name)] = p.lo
    for c in range(len(own)):
        own[c] = dict(own[c])
        own[c].update({k: v for k, v in sustained.items() if k[1] == "I_A" and str(k[0]).startswith("dc:")})
    # A converter cell's current is what its rail's loads sustain, not its own class prior or a guessed
    # operating point (a 600 mA buck feeding a microcontroller was heated as if it carried 2 A). Loads count at
    # their sustained draw (connector exports nobody states at their low end); a cell whose rail has no known
    # load takes the low end of its own range. Its hot-loop losses (ac_parts) scale with the current squared.
    def load_amps(ld):
        if ld.get("key"):
            return sustained.get(ld["key"], 0.0)
        iv = ((intent or {}).get("parts") or {}).get(ld["ref"], {}).get("I_sustained_A")
        if isinstance(iv, (int, float)) and iv >= 0:
            return float(iv)
        return ld.get("prior", 0.0) / (10.0 if bd.part_kind.get(ld["ref"], ("",))[0] == "connector" else 1.0)
    cell_out = {}
    for f in dcp.feeds.values():
        if f["kind"] == "cell":
            cell_out[f["cell"]["src"]] = (f["cell"], rail_demand(dcp, f["cell"]["vout"], load_amps))
    cvs, ac_scale = [], {}
    for c in range(ncp):
        cv = dict(own[c])
        for s in srcs:
            if s.kind == "cell":
                cv[s.name] = {k[1]: v for k, v in cps[s.name][c].items()}
                cell, demand = cell_out.get(s.name, (None, 0.0))
                il0 = cv[s.name].get("I_A")
                if cell is None or il0 is None:
                    continue
                if demand > 0:
                    D = min(max(cv[s.name].get("D", 0.5), 0.02), 0.98)
                    il = demand / (1 - D) if cell["cls"] == "boost" else demand
                else:
                    pi = next((p for p in (P.get(s.name) or {}).values() if getattr(p, "name", "") == "I_A"), None)
                    il = pi.lo if pi is not None else il0
                cv[s.name]["I_A"] = il
                if cell.get("ctrl") and il0 > 0:
                    ac_scale.setdefault(cell["ctrl"], [1.0] * ncp)[c] = (il / il0) ** 2
        cvs.append(cv)
    if ac_parts:
        ac_parts = {k: [w * ac_scale.get(k, [1.0] * ncp)[c] for c, w in enumerate(v)] for k, v in ac_parts.items()}
    m = bm.m
    injs = [{q: a for q, a in DC.injections(dcp, cv).items() if q in m.terminals} for cv in cvs]
    res = ES.potentials_many(m, injs, 0.0, net=net_dc, op=op_dc)
    if any(V is None for V, _ in res):
        notes.append("thermal: the DC flow does not close in the copper; temperatures not computed")
        return []
    gaps = list(b.stackup.gaps) if len(b.stackup.gaps) == len(m.layers) - 1 else [1.6 / max(len(m.layers) - 1, 1)] * (len(m.layers) - 1)
    kinds = {e.name: e.kind for e in bd.circuit.elems}
    pads_of = {}
    for t, cells in m.terminals.items():
        ref = t.rsplit(".", 1)[0]
        pads_of.setdefault(ref, []).extend(cells)
    # heat sinks under a region of a face: their cells, on that face's layer
    L_, ny, nx = m.lab.shape
    names = [getattr(l, "name", "") for l in m.layers]
    regions = []
    for k, hs in enumerate(heatsinks(intent)):
        if hs.get("part"):
            continue
        side = (hs.get("side") or "bottom").lower()
        li = names.index("B.Cu" if side.startswith("b") else "F.Cu") if ("B.Cu" if side.startswith("b") else "F.Cu") in names \
            else (L_ - 1 if side.startswith("b") else 0)
        mask = np.zeros((ny, nx), bool)
        r = hs.get("region", "board")
        if isinstance(r, list) and len(r) == 4:
            j0, i0 = m.cell(min(r[0], r[2]), min(r[1], r[3]))
            j1, i1 = m.cell(max(r[0], r[2]), max(r[1], r[3]))
            mask[max(j0, 0):max(j1 + 1, 0), max(i0, 0):max(i1 + 1, 0)] = True
        else:
            mask[:] = True
        if mask.any() and ((f"heat:sink{k}", "G_W_K") in hc[0] or (f"heat:sink{k}", "h_W_m2K") in hc[0]):
            regions.append((k, li, mask, _rng(hs.get("T_C"))))
    if regions:
        notes.append("thermal: heat sinks under " + ", ".join(f"{int(mk.sum())} cells of {names[li] or li}" for _, li, mk, _ in regions))
    part_sinks = {hs["part"] for hs in heatsinks(intent) if hs.get("part")}
    # each part's own area (mm2): its datasheet's body (the intent's parts.<ref>.body_mm2), else the largest of
    # its courtyard, body outline and pad span
    from shapely.ops import unary_union
    areas = {}
    for fp in b.footprints:
        iv = intent_value(intent, "parts", fp.ref, "body_mm2")
        if iv:
            areas[fp.ref] = iv[0]
            continue
        a = max((unary_union(g).area if g else 0.0) for g in (fp.courtyard, fp.body))
        cells = pads_of.get(fp.ref) or []
        if cells:
            js, is_ = [q[1] for q in cells], [q[2] for q in cells]
            a = max(a, (max(js) - min(js) + 1) * (max(is_) - min(is_) + 1) * m.pitch ** 2)
        areas[fp.ref] = a
    U, Tj, Lp = {}, {}, {}
    th_cache = {}
    for c in range(ncp):
        val = hc[c]
        h = round(val[("heat", "h_W_m2K")], 3)
        sinks, t_sinks, key = [], [], [h]
        for k, li, mask, tc in regions:
            if (f"heat:sink{k}", "G_W_K") in val:
                G = val[(f"heat:sink{k}", "G_W_K")]
                sinks.append((li, mask * (G / mask.sum())))
            else:
                G = val[(f"heat:sink{k}", "h_W_m2K")]
                sinks.append((li, mask * (G * (m.pitch * 1e-3) ** 2)))
            t_sinks.append((tc[0] - val[("heat", "T_amb_C")]) if tc else 0.0)
            key.append(round(G, 6))
        key = tuple(key)
        if key not in th_cache:
            th_cache = {key: TH.Thermal(m, gaps, h=h, sinks=sinks)}   # one factor at a time (memory)
        th = th_cache[key]
        V, info = res[c]
        Q = copper_heat(info["net"], info["x"], m.lab.shape)
        lc = {}
        heat = part_heat(bd, dcp, cvs[c], val, injs[c], {k: v[c] for k, v in (ac_parts or {}).items()}, losses=lc)
        for ref, w in lc.items():
            Lp.setdefault(ref, [0.0] * ncp)[c] = w
        # the lumped parts' own DC loss at their pads (part_heat leaves inductors, ferrites and resistors
        # to the copper model, whose bars and vias alone never counted them)
        for ref, w in lumped_heat(info["net"], info["x"], kinds).items():
            heat[ref] = heat.get(ref, 0.0) + w
        for ref, w in heat.items():
            cells = pads_of.get(ref)
            if cells:
                for (l, j, i) in cells:
                    Q[l, j, i] += w / len(cells)
        T = th.solve(Q, t_sinks)
        # A part with a second way out for its heat besides its pads: a heat sink on it (junction to air through
        # theta_JC + theta_CS + theta_SA), or a module's own board, cooling from both faces (h x 2 x its area).
        # That path (R) runs beside the one into the carrier (theta_JB, then the carrier's rise per watt under
        # its pads), which therefore takes R / (R + theta_JB + R_board) of the heat.
        mods = {}
        for ref, w in heat.items():
            cells = pads_of.get(ref)
            if not cells or w <= 0:
                continue
            rs = []
            if ref in part_sinks and (f"heat:{ref}", "R_sink") in val:
                rs.append(val[(f"heat:{ref}", "R_sink")])
            area = areas.get(ref, 0.0)
            if bd.part_kind.get(ref, ("",))[0] == "module" or area >= MODULE_AREA_MM2:
                rs.append(1.0 / max(h * 2 * area * 1e-6, 1e-9))
            if not rs:
                continue
            r = 1.0 / sum(1.0 / x for x in rs)
            rise = max(float(np.mean([T[l, j, i] for (l, j, i) in cells])), 1e-3)
            npins = len({t for t in m.terminals if t.rsplit(".", 1)[0] == ref})
            tjb = val.get((f"heat:{ref}", "theta_jb"), _theta_jb(npins)[0])
            f = r / (r + tjb + rise / w)
            mods[ref] = f
            for (l, j, i) in cells:
                Q[l, j, i] -= (1 - f) * w / len(cells)
        if mods:
            T = th.solve(Q, t_sinks)
        Tamb = val[("heat", "T_amb_C")]
        for ref, w in heat.items():
            cells = pads_of.get(ref)
            if not cells:
                continue
            kind = bd.part_kind.get(ref, ("",))[0]
            Tmax = T_MAX.get(kind, 85.0)
            npins = len({t for t in m.terminals if t.rsplit(".", 1)[0] == ref})
            tj = val.get((f"heat:{ref}", "theta_jb"), _theta_jb(npins)[0])
            # a sinked part's junction sits theta_JB above its pads for the share that goes into the board
            dT = float(np.mean([T[l, j, i] for (l, j, i) in cells])) + tj * w * mods.get(ref, 1.0)
            U.setdefault(ref, [0.0] * ncp)[c] = dT / max(Tmax - Tamb, 1.0)
            Tj.setdefault(ref, [0.0] * ncp)[c] = Tamb + dT
    rows = []
    for ref, us in U.items():
        for c in range(ncp):
            tot[c] += HA.phi(us[c])
        rows.append(dict(observer=f"heat:{ref}", source="dc", kind="heat", u=us[0], u_lo=min(us), u_hi=max(us),
                         T_C=round(Tj[ref][0], 1), T_hi_C=round(max(Tj[ref]), 1),
                         basis=f"junction (pads' mean + theta_jb P) against {T_MAX.get(bd.part_kind.get(ref, ('',))[0], 85.0):g} C"))
    if obs_out is not None:
        for ref, ts in Tj.items():
            kind = bd.part_kind.get(ref, ("",))[0]
            obs_out.append(dict(id="temp.junction", unit="C", values=[float(t) for t in ts], u=list(U[ref]),
                                scope=dict(kind="heat", observer=f"heat:{ref}", source="dc", part=ref, parts=[ref],
                                           part_kind=kind),
                                reference=dict(value=T_MAX.get(kind, 85.0), basis=f"{kind or 'part'} class rating"),
                                label=f"junction temperature of {ref}"))
        for ref, ws in Lp.items():
            obs_out.append(dict(id="loss.part", unit="W", values=[float(w) for w in ws], u=[0.0] * ncp,
                                scope=dict(kind="part_loss", observer=f"loss:{ref}", source="dc", part=ref, parts=[ref]),
                                reference=dict(value=None, basis="none: a loss is priced, not bounded"),
                                label=f"dissipation of {ref} (switching, conduction, rectification, linear drop)"))
    log(f"thermal: {len(U)} dissipating parts, {ncp} corners in {time.time() - t0:.1f}s")
    return rows
