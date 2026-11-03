# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The objective a board is held to, from its intent (docs/topics/architecture/intent-driven-objectives.md).

The evaluator measures; the intent decides what matters. An evaluation's observations (physical values per
operating corner, each with its scope) are matched by the intent's terms:

    {"id": "T2", "tier": "limit", "obs": "drop.rail", "where": {"rail": "+1V8"}, "max": "27 mV",
     "rate": "2 mW_eq/mV", "source": "U5 datasheet", "why": "core rail tolerance"}

- tier "hard": never traded; any violation ranks a layout below every layout without one.
  Limits and costs share the intent's currency (their rates say what each is worth), so they rank together:
  key = (hard violations, limit + cost).
- tier "limit": met costs nothing; beyond it, rate x the excess (in the limit's own unit).
- tier "cost": rate x the value, summed.
- tier "report": listed, unpriced; "ignore": dropped from the report.
- an observation the evaluator flags `implausible` (noise beyond half its rail) is priced at that cap (its
  values clipped to it), the same for every layout: left unpriced, it let the worse of two layouts escape
  its term whenever only that one crossed the cap. The status lists them under "implausible", with the reason.
- where: scope filters (glob patterns): section, from, to (a boundary: from a section's sources into
  another section's observers), observer, source, kind, rail, load, net, part, connector.
- agg over corners: worst (default for hard and limit), cvar20 (mean of the worst fifth; default for cost), typ.
- combine over matched instances: each (default for hard and limit: each instance against the limit),
  sum (default for cost), max.

Contracts between sections are limit or hard terms with from/to. Defaults when the intent is silent
("defaults": "neutral/1"): copper dissipation is a cost at 1 mW_eq/mW; nothing else is priced, everything
is reported against the evaluator's old bounds, which are references, not limits. "legacy/u" reproduces the
evaluator's own total (sum of phi(u) per corner, mean of the worst fifth) for regression."""
from __future__ import annotations

import fnmatch
import json
import math
import re
from pathlib import Path

from . import sections as SE
from . import units as U

SCHEMA = "kae.intent/1"
TIERS = ("hard", "limit", "cost", "report", "ignore")
AGGS = ("worst", "cvar20", "typ")
CVAR_SHARE = 0.2
# the catalogue of observation kinds: what kae measures, for a model to read (kae.intent.catalog)
KINDS = {
    "loss.copper": ("W", "Copper dissipation of the DC band (and, in the wideband evaluator, the switching "
                    "harmonics): every rail's current through its copper, at each operating corner."),
    "drop.rail": ("V", "DC voltage drop from a rail's source to one load's pins (rail and ground copper together)."),
    "heat.track": ("K", "Temperature rise of the hottest track (IPC-2221) at each corner; scope names it."),
    "pickup.peak": ("V", "Peak noise the layout's copper couples from one aggressor (a switching cell, a clock, "
                    "an IC's core current) into one victim pin (feedback, analog, reset), switching fundamental "
                    "plus edge: the layout's share only (routed minus ideal copper)."),
    "supply.peak": ("V", "Peak noise on one IC's supply pin from one aggressor through the layout's copper."),
    "overshoot.peak": ("V", "Peak ring voltage of a switching cell's own loop (its copper inductance times di/dt "
                       "plus the fundamental): compare with the switch's voltage rating."),
    "cable_cm.v": ("V", "Common-mode voltage between two connectors' grounds at its worst harmonic (f_Hz per "
                   "corner), driven by an aggressor through shared ground copper. It radiates only if cables "
                   "are attached: declare them in environment.cables to get emission.cable_E."),
    "loss.part": ("W", "A part's own dissipation at the DC operating point: a switch's conduction and switching "
                  "loss, a rectifier's forward loss, a linear regulator's drop times its current, a converter "
                  "without a cell model at its efficiency. Loads' own consumption is not a loss and is left out."),
    "loss.loop": ("W", "Energy a switching cell's commutation loop inductance (the copper's share) dumps into the "
                  "switch at every turn-off, 1/2 L_loop I^2 f_sw: the hot loop's layout cost in efficiency."),
    "loss.loop_ac": ("W", "A switching cell's hot loop's copper resistance at the switching frequency (the layout's "
                     "share) carrying the loop's pulsed current, I^2 D (1 - D) R: a lower bound above a few MHz "
                     "(no skin or proximity effect in the raster)."),
    "loss.swnode": ("W", "The layout's capacitance of a switch node (its copper to every other net and the world, "
                    "in the board's stackup) charged through the switch every cycle, 1/2 C V^2 f_sw."),
    "temp.junction": ("C", "A dissipating part's junction temperature: the board's heat flow (copper I^2 R, every "
                      "part's heat, face cooling) at its pads plus theta_jb times its power, at each corner."),
    "emission.cable_E": ("dBuV/m", "Field at 10 m from a declared cable driven by cable_cm.v (Ott 12-7: "
                         "E = 1.26e-6 f l I / r, I = V / 150 Ohm), per connector pair with a declared cable."),
}
SCOPE_KEYS = ("section", "from", "to", "observer", "source", "kind", "rail", "load", "net", "part", "connector")


class IntentError(ValueError):
    pass


def load(path_or_dict):
    """The intent (dict) from a file or a dict; checked for shape. Missing: the neutral defaults."""
    if path_or_dict is None:
        it = {}
    elif isinstance(path_or_dict, dict):
        it = dict(path_or_dict)
    else:
        it = json.loads(Path(path_or_dict).read_text())
    if it.get("schema", SCHEMA) != SCHEMA:
        raise IntentError(f"schema '{it.get('schema')}' unknown; this kae reads {SCHEMA}")
    it.setdefault("schema", SCHEMA)
    it.setdefault("generation", 0)
    it.setdefault("currency", "mW_eq")
    it.setdefault("defaults", "neutral/1")
    if it["currency"] not in U.CURRENCY:
        raise IntentError(f"currency '{it['currency']}' unknown; use one of {list(U.CURRENCY)}")
    if it["defaults"] not in ("neutral/1", "legacy/u", "none"):
        raise IntentError(f"defaults '{it['defaults']}' unknown; use neutral/1, legacy/u or none")
    seen = set()
    for t in it.get("terms", []):
        tid = t.get("id")
        if not tid or tid in seen:
            raise IntentError(f"term {t}: every term needs a unique 'id'")
        seen.add(tid)
        if t.get("tier") not in TIERS:
            raise IntentError(f"term {tid}: tier '{t.get('tier')}' unknown; use one of {TIERS}")
        if not t.get("obs"):
            raise IntentError(f"term {tid}: 'obs' names what it measures; kinds: {sorted(KINDS)}")
        if not any(fnmatch.fnmatch(k, t["obs"]) for k in KINDS):
            raise IntentError(f"term {tid}: obs '{t['obs']}' matches no kind; kinds: {sorted(KINDS)}")
        bad = [k for k in (t.get("where") or {}) if k not in SCOPE_KEYS]
        if bad:
            raise IntentError(f"term {tid}: where keys {bad} unknown; use {SCOPE_KEYS}")
        if t.get("agg", "worst") not in AGGS:
            raise IntentError(f"term {tid}: agg '{t['agg']}' unknown; use {AGGS}")
        if t["tier"] in ("hard", "limit") and not ("max" in t or "min" in t):
            raise IntentError(f"term {tid}: a {t['tier']} term needs 'max' or 'min' (a quantity with its unit)")
        if t["tier"] == "limit" and "rate" not in t:
            raise IntentError(f"term {tid}: a limit term needs a 'rate' (what exceeding it by one unit costs, e.g. "
                              f"'2 mW_eq/mV'); without one, make it 'hard' or 'report'")
        if t["tier"] == "cost" and "rate" not in t:
            raise IntentError(f"term {tid}: a cost term needs a 'rate', e.g. '1 mW_eq/mW'")
        if not (t.get("why") or t.get("source")):
            raise IntentError(f"term {tid}: say why (a 'why' or a 'source'): every priced quantity is traceable")
    return it


# ----------------------------------------------------------------------------------- observations
def _emission(ob, cables):
    """emission.cable_E for a cable_cm.v observation whose pair has a declared cable (the longer one)."""
    lens = [c.get("length_m", 1.0) for c in cables if c.get("connector") in ob["scope"].get("connectors", [])]
    if not lens:
        return None
    l = max(lens)
    vals = [U.to_log(1.26e-6 * f * l * (v / 150.0) / 10.0, "dBuV/m") if f else -300.0
            for v, f in zip(ob["values"], ob.get("f_Hz") or [0.0] * len(ob["values"]))]
    sc = dict(ob["scope"])
    sc["cable_m"] = l
    return dict(id="emission.cable_E", unit="dBuV/m", values=vals, u=None, scope=sc,
                reference=dict(value=30.0, basis="CISPR 32 class B, 30-230 MHz, 10 m"),
                label=f"cable emission at 10 m via {'-'.join(sc.get('connectors', []))} ({l:g} m) <- "
                      f"{sc.get('source')}", f_Hz=ob.get("f_Hz"))


def observations(ev, intent):
    """The evaluation's observations plus those derived from the intent's environment."""
    obs = list(ev.get("observations") or [])
    cables = (intent.get("environment") or {}).get("cables") or []
    if cables:
        obs += [e for e in (_emission(o, cables) for o in obs if o["id"] == "cable_cm.v") if e]
    return obs


def _match(t, ob, secs):
    if not fnmatch.fnmatch(ob["id"], t["obs"]):
        return False
    sc = ob["scope"]
    for k, pat in (t.get("where") or {}).items():
        pats = pat if isinstance(pat, list) else [pat]
        if k in ("section", "from", "to"):
            ids = [s for s in secs if any(fnmatch.fnmatch(s, p) for p in pats)]
            if not ids:
                raise IntentError(f"term {t['id']}: where.{k} {pats} names no section; sections: {sorted(secs)[:40]}")
            sides = ("from", "to") if k == "section" else (k,)
            if not any(SE.side(secs[i], sc, w) for i in ids for w in sides):
                return False
            continue
        vals = {"observer": [sc.get("observer")], "source": [sc.get("source")], "kind": [sc.get("kind")],
                "rail": [sc.get("rail")], "load": [sc.get("load")],
                "net": sc.get("nets", []) + sc.get("to_nets", []) + sc.get("from_nets", []),
                "part": sc.get("parts", []) + sc.get("to_parts", []) + sc.get("from_parts", []),
                "connector": sc.get("connectors", [])}[k]
        if not any(v and fnmatch.fnmatch(str(v), p) for v in vals for p in pats):
            return False
    return True


def _agg(vals, how, side=None):
    """The corners' values aggregated: typical, worst, or the mean of the worst CVAR_SHARE. For a
    'min' bound the worst corners are the smallest (max judged it at its best corner)."""
    if how == "typ":
        return vals[0]
    lo = side == "min"
    if how == "worst":
        return min(vals) if lo else max(vals)
    k = max(1, math.ceil(CVAR_SHARE * len(vals)))
    return sum(sorted(vals)[:k] if lo else sorted(vals)[-k:]) / k


def _in(ob, dim):
    """The observation's per-corner values in the term's dimension (a log unit converts from SI; a dB
    limit on a log-unit observation compares its values as they are)."""
    if dim == "dB" and ob["unit"] in U.LOG:
        return ob["values"]
    if dim in U.LOG and ob["unit"] != dim:
        return [U.to_log(v, dim) for v in ob["values"]]
    if ob["unit"] == "C" and dim == "K":
        return ob["values"]                     # temperatures in C against limits in C (or K steps)
    if dim not in ("", ob["unit"]) and not (dim == "dB" and ob["unit"] in U.LOG):
        raise IntentError(f"{ob['id']} is in {ob['unit']}; a limit in {dim} cannot be compared with it")
    return ob["values"]


def _defaults(intent, obs, terms):
    out = []
    if intent["defaults"] == "neutral/1" and not any(fnmatch.fnmatch("loss.copper", t["obs"]) for t in terms):
        out.append(dict(id="D1", tier="cost", obs="loss.copper", rate="1 mW_eq/mW", agg="cvar20",
                        why="neutral/1: energy needs no assumed bound; every other quantity waits for intent"))
    return out


def evaluate(ev, intent=None, brief=None):
    """The status of one evaluation (kae.excite.evaluate's result) under an intent: tiers, a row per term,
    the unclaimed observations against their references, and questions. Deterministic; no physics runs."""
    intent = load(intent)
    if brief is None:
        from kae.board.kicad_file import load as load_board
        from kae.circuit import brief as B
        brief = B.build(load_board(ev["board"]))
    secs = SE.apply(SE.from_brief(brief), intent.get("sections"))
    obs = observations(ev, intent)
    cur = intent["currency"]
    complete = (ev.get("total") or {}).get("complete", True)
    missing = list((ev.get("total") or {}).get("not_computed") or []) if not complete else []
    status = dict(schema="kae.status/1", observedGeneration=intent["generation"], board=ev.get("board"),
                  complete=complete, currency=cur, defaults=intent["defaults"], terms=[], unclaimed=[],
                  questions=[], sections=sorted(secs), not_computed=missing)
    if intent["defaults"] == "legacy/u":
        if not complete:
            status["tiers"] = None
            status["why_incomplete"] = f"copper open for {missing}: no legacy total"
            return status
        return _legacy(ev, status)
    if not obs:
        # nothing observed (kae.excite.wideband emits no observations): every term would match nothing and
        # the board rank as perfect (0, 0); missing data is no score
        status["tiers"] = None
        status["complete"] = False
        status["why_incomplete"] = "the evaluation has no observations: no score"
        return status
    obs = [_capped(ob) for ob in obs]
    terms = list(intent.get("terms", [])) + _defaults(intent, obs, intent.get("terms", []))
    claimed = set()
    hard = limit = cost = 0.0
    rows = []
    for t in terms:
        hit = [i for i, ob in enumerate(obs) if _match(t, ob, secs)]
        tier = t["tier"]
        claimed |= set(hit) if tier != "report" else set()
        if tier == "ignore":
            rows.append(dict(id=t["id"], tier=tier, obs=t["obs"], matched=len(hit), why=t.get("why")))
            continue
        agg = t.get("agg", "cvar20" if tier == "cost" else "worst")
        combine = t.get("combine", "sum" if tier == "cost" else "each")
        bound, side_ = None, None
        if "max" in t or "min" in t:
            side_ = "max" if "max" in t else "min"
            bound, dim = U.quantity(t[side_])
        else:
            dim = ""
        r = None
        if "rate" in t:
            r, rdim = U.rate(t["rate"], cur)
        inst = []
        for i in hit:
            ob = obs[i]
            vals = _in(ob, dim) if dim else ob["values"]
            inst.append((_agg(vals, agg, side_), ob))
        row = dict(id=t["id"], tier=tier, obs=t["obs"], where=t.get("where"), matched=len(hit), agg=agg,
                   why=t.get("why"), source=t.get("source"))
        gap = _gap(t, missing)
        if gap:
            # a source this term could see was not computed (open copper): the value below covers only the
            # sources that were; it is reported, never priced, and never read as zero
            row.update(incomplete=True, not_computed=gap)
        if not inst:
            row.update(note="matched no observation on this board" + ("" if not gap else
                                                                      " (its sources were not computed)"))
            rows.append(row)
            continue
        unit_ = dim or inst[0][1]["unit"]
        if r is not None and rdim != unit_ and not (rdim == "dB" and unit_ in U.LOG):
            raise IntentError(f"term {t['id']}: rate '{t['rate']}' is per {rdim}, the quantity is in {unit_}")
        if combine == "sum":
            val = sum(v for v, _ in inst)
            dom = max(inst, key=lambda x: x[0])
        else:
            dom = (max if side_ != "min" else min)(inst, key=lambda x: x[0])
            val = dom[0]
        shown = (lambda x: f"{x:.4g} C") if inst[0][1]["unit"] == "C" else (lambda x: U.fmt(x, unit_))
        row.update(value=shown(val), dominant=dom[1].get("label"), rests_on=_rests(dom[1], ev))
        if dom[1].get("f_Hz"):
            row["f_MHz"] = round(max(dom[1]["f_Hz"]) / 1e6, 1)
        contrib = 0.0
        if bound is not None:
            excess = [(v - bound) if side_ == "max" else (bound - v) for v, _ in inst]
            if combine == "sum":
                excess = [(val - bound) if side_ == "max" else (bound - val)]
            over = [max(0.0, e) for e in excess]
            row.update(limit=f"{side_} {t[side_]}", met=all(o <= 0 for o in over),
                       margin=U.fmt(-max(excess), unit_))
            if tier == "hard":
                h = sum(o / max(abs(bound), 1e-30) for o in over)
                row["hard"] = round(h, 6)
                hard += 0.0 if gap else h
            elif tier == "limit":
                contrib = r * sum(over)
        if tier == "cost":
            contrib = r * val
        if tier in ("limit", "cost"):
            row["contribution"] = round(contrib, 4)
            if not gap:
                if tier == "limit":
                    limit += contrib
                else:
                    cost += contrib
        rows.append(row)
    total = limit + cost
    for row in rows:
        if "contribution" in row and not row.get("incomplete"):
            row["share"] = round(row["contribution"] / total, 3) if total > 0 else 0.0
    status["tiers"] = dict(hard=round(hard, 6), limit=round(limit, 4), cost=round(cost, 4))
    status["terms"] = rows
    status["incomplete_terms"] = [r["id"] for r in rows if r.get("incomplete")]
    if missing:
        status["why_incomplete"] = (f"copper open for {missing}: the tiers count only the terms none of those "
                                    f"sources could feed; {status['incomplete_terms']} are reported, not priced")
    # what nobody asked about, largest against its old reference first
    un = []
    for i, ob in enumerate(obs):
        if i in claimed:
            continue
        ref = (ob.get("reference") or {}).get("value")
        w = max(ob["values"])
        un.append(dict(obs=ob["id"], label=ob.get("label"), worst=U.fmt(w, ob["unit"]),
                       reference=U.fmt(ref, ob["unit"]) if ref else None,
                       ratio=round(w / ref, 3) if ref else None, basis=(ob.get("reference") or {}).get("basis")))
        if ob.get("implausible"):
            un[-1]["implausible"] = ob["implausible"]
    un.sort(key=lambda x: (not x.get("implausible"), -(x["ratio"] or 0)))
    status["unclaimed"] = un
    # observations priced at their cap (implausible: noise beyond half the rail), with why
    status["implausible"] = [dict(label=ob.get("label"), id=ob.get("id"), capped_at=ob.get("capped_at"),
                                  worst=max((v for v in ob.get("values") or []), default=None), why=ob["implausible"])
                             for ob in obs if ob.get("implausible")]
    status["questions"] = _questions(ev, intent, obs, rows)
    return status


def _rests(ob, ev):
    """The ledger priors behind an observation's source (what the commander could supply)."""
    src = (ob.get("scope") or {}).get("source")
    return [f"{q['subject']} {q['name']} {q['lo']:.3g}..{q['hi']:.3g} {q['unit']}" for q in ev.get("questions", [])
            if src and q["subject"] in src][:4]


def _questions(ev, intent, obs, rows):
    qs = []
    env = intent.get("environment") or {}
    if any(o["id"] == "cable_cm.v" for o in obs) and "cables" not in env:
        conns = sorted({c for o in obs if o["id"] == "cable_cm.v" for c in o["scope"].get("connectors", [])})
        qs.append(dict(id="Q-cables", ask=f"Which of {', '.join(conns)} carry cables in use, and how long? "
                       "(environment.cables: [{connector, length_m}]); until then cable emissions are not judged.",
                       schema={"type": "array"}))
    for q in ev.get("questions", [])[:8]:
        qs.append(dict(id=f"Q-{q['subject']}-{q['name']}", ask=f"{q['subject']} {q['name']}: is it known? "
                       f"(assumed {q['lo']:.3g}..{q['hi']:.3g} {q['unit']}; {q['basis'][:80]})",
                       schema={"type": "number"}))
    return qs


def _legacy(ev, status):
    """The evaluator's own total from the observations' u (regression: equals ev['total']['robust'])."""
    from kae.excite import harm as HA
    obs = [o for o in ev.get("observations") or [] if o.get("u")]
    n = len(obs[0]["u"]) if obs else 0
    tot = [sum(HA.phi(o["u"][c]) for o in obs) for c in range(n)]
    status["tiers"] = dict(hard=0.0, limit=0.0, cost=round(HA.robust(tot)[0], 2) if tot else 0.0)
    status["terms"] = [dict(id="L1", tier="cost", obs="*", matched=len(obs), agg="cvar20", value=status["tiers"]["cost"],
                            why="legacy/u: sum of phi(u) per corner, worst fifth")]
    return status


DC_KINDS = ("loss.copper", "drop.rail", "heat.track", "loss.part", "temp.junction")      # the DC band's observations


def _gap(t, missing):
    """The uncomputed sources ("dc" for the DC band, else an aggressor's name) this term could have seen."""
    if not missing:
        return []
    kinds = [k for k in KINDS if fnmatch.fnmatch(k, t["obs"])]
    out = []
    if "dc" in missing and any(k in DC_KINDS for k in kinds):
        out.append("dc")
    ac = [s for s in missing if s != "dc"]
    if ac and any(k not in DC_KINDS for k in kinds):
        pat = (t.get("where") or {}).get("source")
        pats = (pat if isinstance(pat, list) else [pat]) if pat else None
        out += [s for s in ac if pats is None or any(fnmatch.fnmatch(s, p) for p in pats)]
    return out


def _capped(ob):
    """An implausible observation (kae.excite.observe.implausible) with its values clipped at its cap:
    cap_V, or for an evaluation from before that field, half the rail its reason names."""
    if not ob.get("implausible"):
        return ob
    cap = ob.get("cap_V")
    if cap is None:
        m = re.search(r"exceeds (\d+)% of its ([0-9.eE+-]+) V rail", ob["implausible"])
        cap = float(m.group(1)) / 100 * float(m.group(2)) if m else None
    if cap is None:
        return ob
    return dict(ob, values=[min(v, cap) for v in ob.get("values") or []], capped_at=cap)


def key(status, terms=None):
    """The ranking key: hard violations first, then limit cost plus cost (smaller is better). With `terms`
    (ids), only those terms count: comparing layouts of one board on the terms complete for all of them."""
    t = status.get("tiers")
    if t is None:
        return (math.inf, math.inf)
    if terms is None:
        return (t["hard"], t["limit"] + t["cost"])
    rows = [r for r in status.get("terms") or [] if r["id"] in terms]
    return (sum(r.get("hard", 0.0) for r in rows), sum(r.get("contribution", 0.0) for r in rows))


def common_terms(statuses):
    """The term ids complete in every status (a term one layout could not compute is left out for all)."""
    ids = [{r["id"] for r in s.get("terms") or [] if not r.get("incomplete")} for s in statuses]
    return set.intersection(*ids) if ids else set()
