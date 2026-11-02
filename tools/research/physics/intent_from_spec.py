# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A board's two structured inputs from its spec (numbers a model or a designer states about the board):

  OPERATING  kae.excite.evaluate --intent: what the board does electrically. cells.<cell id>.{V_V,
             f_sw_Hz, I_A, t_i_s}, parts.<ref>.I_A (loads and output connectors), nets.<rail>.source,
             requirements.thermal.T_amb_C. Each replaces one of the evaluator's priors.
  INTENT     kae.intent: what matters. Standing priorities on every board (copper loss = power loss and
             efficiency; ripple), the spec's limits (rail tolerance -> drop.rail, rail and IC ripple ->
             supply.peak, sensitive pins -> pickup.peak, switch ratings -> overshoot.peak hard, track heat),
             and EMI terms on boards with a radio or GNSS receiver (its supply and pins, declared cables).

    python intent_from_spec.py SPEC.json SUMMARY.json --intent INTENT.json --operating OPERATING.json

SPEC is kae.board-spec/1 (tools/research/physics/board_spec_prompt.md). Every id, ref and net is checked
against the board's summary and every number against physical bounds; what fails is dropped and listed
in provenance.rejected, never guessed around.
"""
import argparse
import json
import math
import sys

STANDING = "standing benchmark priority: power loss, efficiency (copper, parts, hot loops), ripple and thermals on every board; EMI on boards with a radio or GNSS"
BASES = ("datasheet", "typical", "guess")
# plausible ranges per field: (lo, hi) in SI units
BOUNDS = {"V": (0.3, 1000.0), "pct": (0.05, 50.0), "mV": (0.01, 5000.0), "A": (1e-9, 200.0), "Hz": (1e3, 1e8),
          "s": (1e-10, 1e-5), "C": (-55.0, 150.0), "K": (1.0, 200.0), "m": (0.01, 50.0)}
RATE = {"guess": 1.0, "typical": 1.0, "datasheet": 1.0}   # one rate scale: the basis is recorded, not weighted


_LIB = None


def library():
    """The datasheet library's identified parts (datasheet_prompt.md), as (compiled match, facts)."""
    global _LIB
    if _LIB is None:
        import glob
        import os
        import re
        d = os.path.expanduser(os.environ.get("KAE_DATASHEETS", "~/kae-datasheets"))
        _LIB = []
        for p in sorted(glob.glob(f"{d}/facts/*.json")):
            try:
                f = json.load(open(p))
                pat = re.sub(r"\$$", r"\\b", f.get("match") or re.escape(f.get("part") or f.get("query") or ""))
                if f.get("identified") and pat:
                    _LIB.append((re.compile(pat, re.I), f))
            except (ValueError, OSError, re.error):
                continue
    return _LIB


def datasheet(part):
    """The library facts for a board part (its value, then value + lib_id, as kae's part table matches)."""
    text = f"{part.get('value') or ''} {part.get('lib_id') or ''}"
    for rx, f in library():
        if rx.search(part.get("value") or "") or rx.search(text):
            return f
    return None


def verified(f, name):
    """(typ, max, cite) of a verified datasheet value, or None."""
    v = ((f or {}).get("values") or {}).get(name)
    if not isinstance(v, dict) or not v.get("verified"):
        return None
    typ = v.get("typ") if isinstance(v.get("typ"), (int, float)) else None
    mx = v.get("max") if isinstance(v.get("max"), (int, float)) else None
    if typ is None and mx is None:
        return None
    return typ, mx, f"{f.get('part') or f.get('query')} datasheet p.{v.get('page')}"


AMPS_PER_PAD = 3.0      # A a connector pin carries at most, generously (0.1" headers ~3 A)
AMPS_BY_KIND = ((r"screw|terminal|\bTB\d|barrel|jack|DCJ|XT\d\d|anderson|mini.?fit|micro.?fit|power", 15.0),
                (r"JST.?(SH|GH|ZH)|SM\d\dB.?SR|picoblade", 1.0))


def amps_per_pad(part):
    """A per pad for a connector by its library and value (power connectors carry far more than headers)."""
    import re
    text = f"{part.get('lib_id') or ''} {part.get('value') or ''}"
    for pat, a in AMPS_BY_KIND:
        if re.search(pat, text, re.I):
            return a
    return AMPS_PER_PAD


def infer_input(summary, spec, src, out, v_out):
    """A regulator's input rail from its own pads: the one other supply rail it touches (higher than the
    output for a linear or buck regulator; a boost's is lower, so any other rail when v_out is unknown)."""
    nets = next((p.get("nets") or {} for p in summary.get("parts") or [] if p["ref"] == src), {})
    grounds = set(summary.get("ground_nets") or [])
    volts = {r["net"]: r.get("V_nom") for r in spec.get("rails") or [] if r.get("net")}
    for n, d in (summary.get("rails") or {}).items():
        volts.setdefault(n, (d or {}).get("volts"))
    cands = [n for n in nets if n != out and n not in grounds and n in volts]
    hi = [n for n in cands if v_out and volts.get(n) and volts[n] > v_out]
    pick = hi if len(hi) == 1 else (cands if len(cands) == 1 else [])
    return pick[0] if pick else None


class Spec:
    def __init__(self, spec, summary):
        self.s, self.sum = spec, summary
        self.pads = {p["ref"]: p.get("nets") or {} for p in summary.get("parts") or []}
        self.part = {p["ref"]: p for p in summary.get("parts") or []}
        self.refs = {p["ref"] for p in summary.get("parts") or []} | {r for x in summary.get("sections") or [] for r in x.get("parts") or []}
        self.nets = set(summary.get("rails") or {}) | set(summary.get("ground_nets") or []) | {n for x in summary.get("sections") or [] for n in x.get("nets") or []}
        self.sections = {x["id"]: x for x in summary.get("sections") or []}
        self.rejected = []

    def num(self, item, key, kind, where):
        v = item.get(key)
        if v is None:
            return None
        lo, hi = BOUNDS[kind]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not (lo <= abs(v) <= hi):
            self.rejected.append(f"{where}.{key}={v!r}: outside {lo:g}..{hi:g} {kind}")
            return None
        return float(v)

    def ref(self, r, where):
        if r in self.refs:
            return r
        self.rejected.append(f"{where}: ref {r!r} not on the board")
        return None

    def net(self, n, where):
        if n in self.nets:
            return n
        self.rejected.append(f"{where}: net {n!r} not on the board")
        return None


def basis(item):
    b = item.get("basis")
    return b if b in BASES else "guess"


def why(item, what):
    return f"{what} ({basis(item)}: {item.get('why') or 'no reason given'})"


def compile_spec(spec, summary):
    S = Spec(spec, summary)
    op = {"parts": {}, "nets": {}, "cells": {}, "requirements": {}}
    opwhy = {}
    terms = [dict(id="P1", tier="cost", obs="loss.copper", rate="1 mW_eq/mW", agg="cvar20",
                  why=f"power loss and efficiency: every mW the copper burns. {STANDING}"),
             dict(id="P2", tier="cost", obs="loss.part", rate="1 mW_eq/mW", agg="cvar20",
                  why=f"efficiency: switch, rectifier and regulator losses the layout's currents and voltages set. {STANDING}"),
             dict(id="P3", tier="cost", obs="loss.loop", rate="1 mW_eq/mW", agg="cvar20",
                  why=f"efficiency: the hot loops' inductance energy dumped into the switches, 1/2 L I^2 f_sw. {STANDING}"),
             dict(id="P4", tier="cost", obs="loss.loop_ac", rate="1 mW_eq/mW", agg="cvar20",
                  why=f"efficiency: the hot loops' AC copper resistance carrying their pulsed current. {STANDING}"),
             dict(id="P5", tier="cost", obs="loss.swnode", rate="1 mW_eq/mW", agg="cvar20",
                  why=f"efficiency: switch-node copper capacitance charged through the switch, 1/2 C V^2 f_sw. {STANDING}"),
             dict(id="R0", tier="cost", obs="supply.peak", rate="0.1 mW_eq/mV", agg="cvar20",
                  why=f"ripple on every IC supply pin, at a low base rate under the per-rail limits below. {STANDING}")]
    # rails: tolerance -> drop limit; ripple -> supply.peak limit; source -> who feeds it
    for i, r in enumerate(spec.get("rails") or []):
        w = f"rails[{i}]"
        n = S.net(r.get("net"), w)
        if not n:
            continue
        V = S.num(r, "V_nom", "V", w)
        tol = S.num(r, "tolerance_pct", "pct", w)
        rip = S.num(r, "ripple_max_mV", "mV", w)
        crit = bool(r.get("critical"))
        rate = 5 if crit else 1
        if V and tol:
            drop_mV = round(V * tol * 10.0 / 2.0, 3)          # half the tolerance band for the copper
            terms.append(dict(id=f"D{i}", tier="limit", obs="drop.rail", where={"rail": n}, max=f"{drop_mV:g} mV",
                              rate=f"{rate} mW_eq/mV", source=f"{n}: {V:g} V +/-{tol:g} %, half the band for copper",
                              why=why(r, "rail regulation")))
        if rip:
            terms.append(dict(id=f"S{i}", tier="limit", obs="supply.peak", where={"observer": f"supply:*:{n}"},
                              max=f"{rip:g} mV", rate=f"{rate} mW_eq/mV", source=f"{n}: ripple limit {rip:g} mV",
                              why=why(r, "ripple on the rail's loads")))
        src = r.get("source_ref")
        mine = S.pads.get(src) or {}
        if src and mine and n not in mine:
            S.rejected.append(f"{w}.source_ref={src}: it has no pad on {n} (its nets: {', '.join(list(mine)[:6])})")
            src = None
        if src and S.ref(src, w + ".source_ref"):
            fact = {"source": src}
            is_conn = (S.part.get(src) or {}).get("kind") == "connector"
            if is_conn and r.get("regulator") in ("linear", "switching"):
                S.rejected.append(f"{w}.regulator={r.get('regulator')}: {src} is a connector, not a regulator")
                r = dict(r, regulator="none", from_net=None)
            if r.get("from_net") and mine and r["from_net"] not in mine:
                S.rejected.append(f"{w}.from_net={r['from_net']}: not on {src}'s pads; inferring it instead")
                r = dict(r, from_net=None)
            if V:
                fact["V_V"] = V
            fr = r.get("from_net")
            if fr and S.net(fr, w + ".from_net"):
                fact["from"] = fr                               # the regulator's input rail
            elif r.get("regulator") in ("linear", "switching"):
                inf = infer_input(summary, spec, src, n, V)
                if inf:
                    fact["from"] = inf
                    opwhy[f"nets.{n}.from"] = f"inferred from {src}'s own pads: its only other supply rail ({inf})"
            if r.get("regulator") in ("linear", "switching"):
                fact["kind"] = r["regulator"]
            eta = r.get("eta")
            if fact.get("kind") == "switching" and isinstance(eta, list) and len(eta) == 2 and \
                    all(isinstance(x, (int, float)) for x in eta) and 0.3 <= min(eta) <= max(eta) <= 0.99:
                fact["eta"] = [float(min(eta)), float(max(eta))]
            op["nets"][n] = fact
            opwhy[f"nets.{n}"] = why(r, "rail source and its regulator")
    # loads: current per IC / module on a rail
    for i, l in enumerate(spec.get("loads") or []):
        w = f"loads[{i}]"
        r = S.ref(l.get("ref"), w)
        typ, mx = S.num(l, "I_typ_A", "A", w), S.num(l, "I_max_A", "A", w)
        ds = verified(datasheet(S.part.get(r) or {}), "I_supply_typ_A") if r else None
        dm = verified(datasheet(S.part.get(r) or {}), "I_supply_max_A") if r else None
        if ds or dm:                                   # the datasheet's current replaces the model's estimate
            typ = (ds[0] if ds and ds[0] is not None else (ds[1] if ds else None)) or typ
            mx = (dm[1] if dm and dm[1] is not None else (dm[0] if dm else None)) or mx
            l = dict(l, basis="datasheet", why=f"{(ds or dm)[2]}" + (f"; max {dm[2]}" if dm else ""))
        if r and (typ or mx):
            lo, hi = (typ or mx) * (0.5 if typ else 0.3), (mx or typ * 2)
            op["parts"][r] = {"I_A": [round(min(lo, hi), 6), round(max(lo, hi), 6)]}
            opwhy[f"parts.{r}.I_A"] = why(l, "load current")
    # converters: the brief's switching cells
    for i, c in enumerate(spec.get("converters") or []):
        w = f"converters[{i}]"
        cid = c.get("cell")
        if cid not in S.sections or not str(cid).startswith("cell:"):
            S.rejected.append(f"{w}: cell {cid!r} is not one of the board's cell sections")
            continue
        vin, vout = S.num(c, "V_in_V", "V", w), S.num(c, "V_out_V", "V", w)
        f, I, t = S.num(c, "f_sw_Hz", "Hz", w), S.num(c, "I_out_A", "A", w), S.num(c, "t_edge_s", "s", w)
        cell = {}
        if vin or vout:
            vb = max(v for v in (vin, vout) if v)
            cell["V_V"] = [round(0.9 * vb, 6), round(1.1 * vb, 6)]
        if f:
            cell["f_sw_Hz"] = [round(0.8 * f, 3), round(1.2 * f, 3)]
        if I:
            cell["I_A"] = [round(0.3 * I, 6), round(I, 6)]
        if t:
            cell["t_i_s"] = [t / 2, t * 2]
        if cell:
            op["cells"][cid] = cell
            opwhy[f"cells.{cid}"] = why(c, "converter operating point")
        vmax = S.num(c, "switch_V_max_V", "V", w)
        if vmax:
            terms.append(dict(id=f"O{i}", tier="hard", obs="overshoot.peak", where={"observer": f"overshoot:{cid}"},
                              max=f"{vmax:g} V", source=f"{cid}: switch rating {vmax:g} V", why=why(c, "switch voltage rating")))
    # sensitive pins: feedback, ADC, reset, reference, RF inputs
    for i, v in enumerate(spec.get("sensitive") or []):
        w = f"sensitive[{i}]"
        mx = S.num(v, "max_noise_mV", "mV", w)
        obs_id, part = v.get("victim"), v.get("ref")
        if not mx:
            continue
        if obs_id and str(obs_id).startswith("victim:"):
            where = {"observer": obs_id}
        elif part and S.ref(part, w):
            where = {"part": part}
        else:
            S.rejected.append(f"{w}: needs a victim:... section id or a part ref")
            continue
        terms.append(dict(id=f"V{i}", tier="limit", obs="pickup.peak", where=where, max=f"{mx:g} mV", rate="10 mW_eq/mV",
                          source=f"{v.get('what') or 'sensitive pin'}: {mx:g} mV", why=why(v, v.get("what") or "sensitive pin")))
    # radio / GNSS
    radios = []
    for i, r in enumerate(spec.get("radio") or []):
        ref = S.ref(r.get("ref"), f"radio[{i}]")
        if ref:
            radios.append(dict(r, ref=ref))
    cables = []
    for i, c in enumerate(spec.get("connectors") or []):
        w = f"connectors[{i}]"
        ref = S.ref(c.get("ref"), w)
        if not ref:
            continue
        I = S.num(c, "I_A", "A", w)
        if I:
            npads = ((S.pads.get(ref) or {}).get(c.get("rail")) or 0) if c.get("rail") else 0
            app = amps_per_pad(S.part.get(ref) or {})
            cap = app * npads if npads else None
            if cap and I > cap:
                S.rejected.append(f"{w}.I_A={I:g} A capped at {cap:g} A: {ref} has {npads} pad(s) on {c.get('rail')} "
                                  f"({app:g} A per pad)")
                I = cap
        if c.get("direction") == "output" and I:
            op["parts"][ref] = {"I_A": [round(0.5 * I, 6), round(1.5 * I, 6)]}
            opwhy[f"parts.{ref}.I_A"] = why(c, f"export current ({c.get('function') or 'output'})")
        L = S.num(c, "cable_length_m", "m", w)
        if L:
            cables.append(dict(connector=ref, length_m=L, why=why(c, c.get("function") or "cable")))
    if radios:
        refs = sorted({r["ref"] for r in radios})
        kinds = ", ".join(sorted({str(r.get("kind")) for r in radios}))
        rip = min([x for x in (S.num(r, "supply_ripple_max_mV", "mV", "radio") for r in radios) if x] or [10.0])
        terms += [dict(id="E1", tier="limit", obs="supply.peak", where={"part": refs}, max=f"{rip:g} mV", rate="20 mW_eq/mV",
                       source=f"{kinds} supply ripple {rip:g} mV", why=f"EMI: switching noise on the {kinds} supply desenses it. {STANDING}"),
                  dict(id="E2", tier="cost", obs="pickup.peak", where={"part": refs}, rate="20 mW_eq/mV", agg="cvar20",
                       why=f"EMI: noise coupled into the {kinds} pins. {STANDING}")]
        if cables:
            terms.append(dict(id="E3", tier="limit", obs="emission.cable_E", max="30 dBuV/m", rate="20 mW_eq/dB",
                              source="CISPR 32 class B, 30-230 MHz, 10 m (reference)", why=f"EMI from the cables of a board with a {kinds}. {STANDING}"))
    else:
        terms.append(dict(id="E3", tier="report", obs="cable_cm.v", why="no radio or GNSS: EMI is not a standing priority here"))
    hk = S.num(spec.get("thermal") or {}, "track_rise_max_K", "K", "thermal")
    if hk:
        terms.append(dict(id="H1", tier="limit", obs="heat.track", max=f"{hk:g} K", rate="5 mW_eq/K", why=why(spec["thermal"], "track heating")))
    # thermals: nothing may overheat. A part's own rating (a load's T_max_C) or its class rating is hard;
    # 20 K below it is a priced margin
    from kae.excite.heat import T_MAX
    own = {}
    for i, l in enumerate(spec.get("loads") or []):
        t = l.get("T_max_C")
        if l.get("ref") in S.refs and isinstance(t, (int, float)) and 40 <= t <= 200:
            own[l["ref"]] = float(t)
    for p in summary.get("parts") or []:                 # datasheet junction ratings, any part with a sheet
        tj = verified(datasheet(p), "T_j_max_C")
        t = (tj[1] if tj and tj[1] is not None else (tj[0] if tj else None))
        if isinstance(t, (int, float)) and 40 <= t <= 200:
            own[p["ref"]] = float(t)
    by_kind = {}
    for p in summary.get("parts") or []:
        if p["ref"] not in own and p.get("kind") in T_MAX:
            by_kind.setdefault(p["kind"], []).append(p["ref"])
    groups = [(f"part {r}", [r], t, "the spec's rating") for r, t in sorted(own.items())] + \
             [(f"{k} parts", sorted(refs), T_MAX[k], f"{k} class rating") for k, refs in sorted(by_kind.items())]
    for j, (what, refs, tmax, basis_) in enumerate(groups):
        terms.append(dict(id=f"T{j}", tier="hard", obs="temp.junction", where={"part": refs}, max=f"{tmax:g} C",
                          source=f"{what}: {basis_} {tmax:g} C", why=f"thermals: nothing may overheat. {STANDING}"))
        terms.append(dict(id=f"M{j}", tier="limit", obs="temp.junction", where={"part": refs}, max=f"{tmax - 20:g} C",
                          rate="2 mW_eq/C", source=f"{what}: 20 K margin below {tmax:g} C",
                          why="thermals: keep a margin below the rating (ambient and cooling are uncertain)"))
    # junction-to-board thermal resistance (the heat model adds theta_jb P to the board under the part):
    # the datasheet's own RthetaJB / psiJB; else between theta_JC and theta_JA (the JEDEC board's own path
    # to air is in theta_JA), typical at their geometric mean; else a share of theta_JA
    for p in summary.get("parts") or []:
        f = datasheet(p)
        jb, jc, ja = (verified(f, k) for k in ("theta_jb_C_W", "theta_jc_C_W", "theta_ja_C_W"))
        pick = lambda v: (v[0] if v[0] is not None else v[1]) if v else None
        jb_, jc_, ja_ = pick(jb), pick(jc), pick(ja)
        rng = rule = None
        if jb_ and 0.1 <= jb_ <= 500:
            rng, rule = [jb_, jb_], f"theta_JB from {jb[2]}"
        elif jc_ and ja_ and 0 < jc_ < ja_ <= 1000:
            rng, rule = [jc_, ja_], f"between theta_JC ({jc[2]}) and theta_JA ({ja[2]})"
        elif ja_ and 1 <= ja_ <= 1000:
            rng, rule = [0.3 * ja_, 0.8 * ja_], f"0.3-0.8 x theta_JA ({ja[2]}): no theta_JB or theta_JC stated"
        if rng:
            typ = (rng[0] * rng[1]) ** 0.5
            op["parts"].setdefault(p["ref"], {})["theta_jb_C_W"] = [round(rng[0], 3), round(rng[1], 3)] if rng[0] != rng[1] else round(typ, 3)
            opwhy[f"parts.{p['ref']}.theta_jb_C_W"] = f"junction to board: {rule}"
    th = spec.get("thermal") or {}
    ta = th.get("T_amb_C")
    if isinstance(ta, list) and len(ta) == 2 and all(isinstance(x, (int, float)) for x in ta) and -55 <= min(ta) <= max(ta) <= 150:
        op["requirements"]["thermal"] = {"T_amb_C": [float(min(ta)), float(max(ta))]}
        opwhy["requirements.thermal.T_amb_C"] = why(th, "ambient")
    intent = {"schema": "kae.intent/1", "generation": 1, "currency": "mW_eq", "defaults": "neutral/1",
              "environment": {"enclosure": {"kind": th.get("enclosure") or "unknown", "why": why(th, "enclosure")},
                              "cables": cables if radios else []},
              "terms": terms,
              "provenance": dict(spec_schema=spec.get("schema"), purpose=spec.get("purpose"), rejected=S.rejected,
                                 note="board spec written by a model from board_summary.py; limits from the spec, rates the "
                                      "benchmark's own, identical on every board; GNSS/Wi-Fi bands above ~300 MHz are not computable")}
    op["provenance"] = dict(why=opwhy, rejected=S.rejected)
    return intent, op


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("spec"), ap.add_argument("summary")
    ap.add_argument("--intent", required=True), ap.add_argument("--operating", required=True)
    a = ap.parse_args(argv)
    from kae.intent import objective as OBJ
    it, op = compile_spec(json.load(open(a.spec)), json.load(open(a.summary)))
    OBJ.load(dict(it))
    for path, obj in ((a.intent, it), (a.operating, op)):
        with open(path, "w") as f:
            json.dump(obj, f, indent=1)
            f.write("\n")
    print(f"terms {len(it['terms'])}, cells {len(op['cells'])}, loads {len(op['parts'])}, rejected {len(op['provenance']['rejected'])}")


if __name__ == "__main__":
    sys.exit(main())
