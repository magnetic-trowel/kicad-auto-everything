# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the intent asks of a hop's copper, in closed form: no field solve, so the plain router follows it.

Per millimetre of a hop that carries corner currents I_c (from the DC plan), copper of width w and
thickness t costs, in the intent's currency,
    loss:  k_R * rho / (w t)        k_R = loss rate x agg_c(I_c^2) + drop cost rate x max_c |I_c|
    area:  a * (w + s)              a = knobs["route.area_cost"] (currency per mm^2), s the clearance
so the best width is w* = sqrt(k_R rho / (t a)), taken from the router's ladder, clamped by the class, by
the intent's per-net knobs, and floored by IPC-2221 at the temperature rise of a heat.track term.
The loss and drop rates are the evaluator's (kae.intent.objective): the router prices what it is scored on.
A drop limit costs nothing once met, so it adds nothing per hop; dc_cost prices its excess."""
from __future__ import annotations

import fnmatch
import math

from . import objective as OB
from . import units as U

RHO_CU_OHM_MM = 1.72e-5            # copper resistivity, ohm mm
# neutral/1: currency per mm^2 of copper when the intent says nothing. w* = 3.1 mm/A on 35 um copper.
# Basis (economic, always-on): a mm^2 of a 2-layer board at volume costs about $0.0003-0.0008, and 1 mW
# for 5 years at $0.15/kWh about $0.0066, so 0.05-0.12 mW_eq/mm^2. Human layouts imply more: median 0.64
# (IQR 0.18-3.4) over 147 rail nets >= 0.1 A on 59 suite boards, i.e. tracks about 3.5x narrower
# (tools/research/physics/area_cost_widths.py). Kept until the A/B (tools/kaeres/experiments/area-cost-ab.sh)
# decides; reported as a defaulted knob (hazard area_cost_defaulted).
AREA_COST = 0.05
AREA_COST_BASIS = ("economic, always-on board: $0.0003-0.0008/mm^2 of 2-layer board vs 1 mW for 5 y at $0.15/kWh "
                   "($0.0066); human layouts imply about 0.6 (tracks ~3.5x narrower than this default)")


def _net_matches(t, net, secs, kind=None):
    """Does term t's scope take in a hop of `net`? Every where key must hold. net and rail name the net, a
    section (or from, to) takes in its nets, kind the observation kind (dc_loss, dc_drop, dc_heat) when given.
    Keys a bare net cannot answer (load, part, observer, source, connector) do not match: a term scoped to
    one load or part does not price every net's copper."""
    for k, pat in (t.get("where") or {}).items():
        pats = pat if isinstance(pat, list) else [pat]
        if k in ("net", "rail"):
            ok = any(fnmatch.fnmatch(net, p) for p in pats)
        elif k in ("section", "from", "to"):
            ok = any(net in s.nets for sid, s in secs.items() if any(fnmatch.fnmatch(sid, p) for p in pats))
        elif k == "kind" and kind is not None:
            ok = any(fnmatch.fnmatch(kind, p) for p in pats)
        else:
            ok = False
        if not ok:
            return False
    return True


class Policy:
    """The intent's copper policy for the router (one per routing run)."""

    def __init__(self, intent, sections=None):
        self.intent = OB.load(intent)
        self.cur = self.intent["currency"]
        self.secs = sections or {}
        terms = list(self.intent.get("terms", []))
        terms += OB._defaults(self.intent, [], terms)
        self.loss = [t for t in terms if t["tier"] == "cost" and fnmatch.fnmatch("loss.copper", t["obs"])]
        self.drop = [t for t in terms if t["tier"] in ("limit", "cost") and fnmatch.fnmatch("drop.rail", t["obs"])]
        self.heat = [t for t in terms if t["tier"] in ("limit", "hard") and fnmatch.fnmatch("heat.track", t["obs"])]
        knobs = self.intent.get("knobs") or {}
        self.area = float(knobs.get("route.area_cost", AREA_COST))
        self.wmin = knobs.get("route.width.min_mm") or {}
        self.wmax = knobs.get("route.width.max_mm") or {}
        self.explicit_area = "route.area_cost" in knobs
        self.capped = []                 # hops whose heating-limit width the caps would not allow (width())

    def describe(self):
        return (f"intent copper policy: {len(self.loss)} loss, {len(self.drop)} drop, {len(self.heat)} heating terms; "
                f"area {self.area:g} {self.cur}/mm^2" + ("" if self.explicit_area else " (neutral/1 default)"))

    def k_R(self, net, I):
        """Currency per ohm of a hop of `net` carrying corner currents I (A), and the terms that set it."""
        why = []
        k = 0.0
        # the most specific term per net (objective.resolve). A drop limit is not priced per hop: once met it
        # costs nothing, and a hop does not know the drop; dc_cost prices its excess in physics routing
        for t in OB.resolve([t for t in self.loss if _net_matches(t, net, self.secs, "dc_loss")], net):
            r, _ = U.rate(t["rate"], self.cur)                 # currency per W
            agg = t.get("agg", "cvar20")
            k += r * OB._agg([x * x for x in I], agg)
            why.append(t["id"])
        for t in OB.resolve([t for t in self.drop if t["tier"] == "cost" and _net_matches(t, net, self.secs, "dc_drop")],
                            net):
            r, _ = U.rate(t["rate"], self.cur)                 # currency per V
            k += r * max(abs(x) for x in I)
            why.append(t["id"])
        return k, why

    def dT_max(self, net, with_term=False):
        """The tightest heating limit (K) a term puts on the net's tracks, or None (and its term)."""
        lims = sorted(((U.quantity(t["max"])[0], i, t) for i, t in enumerate(self.heat)
                       if "max" in t and _net_matches(t, net, self.secs, "dc_heat")), key=lambda x: x[:2])
        best = lims[0] if lims else (None, 0, None)
        return (best[0], best[2]) if with_term else best[0]

    def width(self, net, I, t_mm, clearance, ladder, w_lo, w_hi, internal=False):
        """(width mm, reason) for a hop of `net` on copper t_mm thick carrying corner currents I; `internal`:
        the hop is on an inner layer (IPC-2221 k = 0.024 there, 0.048 outside; high-current.md)."""
        k, why = self.k_R(net, I)
        lo = max(w_lo, float(self.wmin.get(net, 0.0)))
        hi = min(w_hi if w_hi is not None else math.inf, float(self.wmax.get(net, math.inf)))
        dT, ht = self.dT_max(net, with_term=True)
        Imax = max((abs(x) for x in I), default=0.0)
        if dT is not None and Imax > 0:
            from kae.route.critical_physics import ipc2221_width
            w_ipc = ipc2221_width(Imax, dT, t_mm, internal=internal)
            if w_ipc > hi + 1e-9:
                # the heating limit's width does not fit under the class or knob cap: the hop is narrower
                # than the limit allows; recorded for the router's hazards (a hard term: block)
                self.capped.append(dict(net=net, term=ht["id"], tier=ht["tier"], I_A=round(Imax, 3), dT_K=dT,
                                        w_need_mm=round(w_ipc, 3), w_cap_mm=round(hi, 3)))
            if w_ipc > lo:
                lo, why = w_ipc, why + [f"IPC-2221 {Imax:.2f} A at {dT:g} K"]
        if k <= 0:
            return min(max(lo, w_lo), hi), "no priced current"

        def cost(w):
            return k * RHO_CU_OHM_MM / (w * t_mm) + self.area * (w + clearance)
        w_star = math.sqrt(k * RHO_CU_OHM_MM / (t_mm * self.area))
        cands = sorted({w for w in ladder if lo - 1e-9 <= w <= hi + 1e-9} | {min(max(lo, 0.0), hi)})
        w = min(cands, key=cost)
        return w, (f"{k:.3g} {self.cur}/ohm from {', '.join(why)} (I up to {Imax:.2f} A); optimum {w_star:.2f} mm, "
                   f"ladder {w:g} mm" + (f", capped at {hi:g} mm" if w_star > hi else ""))

    # ------------------------------------------------------------------ physics terms (per section)
    PHYS = ("pickup.peak", "supply.peak", "overshoot.peak")
    # The kinds the router computes while routing: the pair terms above, the DC band's drops, and track
    # heating (as an IPC-2221 width floor). A hard term on any other kind is not checked by the router.
    ROUTED = PHYS + ("drop.rail", "heat.track", "loss.copper")
    # Hard terms are a tier of their own, never a price: the router compares candidates by (hard violation,
    # cost) lexicographically, as kae.intent.objective.key ranks layouts. HARD_SLOPE only steers the path
    # search (a hop's price per volt of a violated hard term) toward meeting it; it is an exact-penalty slope
    # (any slope above the cost tier's largest marginal rate gives the same paths), never part of the cost.
    HARD_SLOPE = 1e6

    def pair_terms(self, bd, o, s):
        """The intent's terms on the (observer, aggressor) pair's peak voltage: [(term, rate per V or None for
        a hard term, limit V or None, tier)]. Pairs no term names are not priced (and not solved)."""
        from kae.excite import observe as O
        ob = O.observation(bd, o, s, [0.0], [0.0])
        out = []
        hit = [t for t in self.intent.get("terms", []) if t["tier"] not in ("report", "ignore")
               and any(fnmatch.fnmatch(k, t["obs"]) for k in self.PHYS) and OB._match(t, ob, self.secs)]
        for t in OB.resolve(hit, f"{o.name} <- {s.name}"):     # the most specific term, as the evaluator prices it
            lim = U.quantity(t["max"])[0] if "max" in t else None
            r = None if t["tier"] == "hard" else U.rate(t["rate"], self.cur)[0]
            out.append((t, r, lim, t["tier"]))
        return out

    def dC_dV(self, terms, V):
        """The path search's slope per volt of a pair's peak at corner values V (array): each cost term's rate;
        each limit's rate where V exceeds it; HARD_SLOPE where a hard term is violated (steering only)."""
        import numpy as np
        V = np.asarray(V, float)
        d = np.zeros_like(V)
        for t, r, lim, tier in terms:
            if tier == "cost":
                d += r
            elif lim is not None:
                d += (self.HARD_SLOPE if tier == "hard" else r) * (V > lim)
        return d

    def pair_cost(self, terms, V):
        """The intent's cost (limit and cost tiers) of a pair at corner peak voltages V (array), in its
        currency. Hard terms are not in it: pair_hard."""
        import numpy as np
        V = np.asarray(V, float)
        c = np.zeros_like(V)
        for t, r, lim, tier in terms:
            if tier == "cost":
                c += r * V
            elif tier == "limit" and lim is not None:
                c += r * np.maximum(0.0, V - lim)
        return c

    def pair_hard(self, terms, V):
        """[(term, worst V, limit V, violation)] of the pair's hard terms at corner peaks V: the violation is
        the evaluator's (excess over the limit at the worst corner, relative to the limit)."""
        out = []
        for t, _, lim, tier in terms:
            if tier == "hard" and lim is not None:
                w = float(max(V))
                out.append((t, w, lim, max(0.0, w - lim) / max(abs(lim), 1e-30)))
        return out

    def dc_hard(self, obs):
        """[(term, load@rail, worst drop V, limit V, violation)] of the hard drop.rail terms over the DC
        band's corner observations `obs` (kae.excite.dc.observe), as the evaluator judges them."""
        hard = [t for t in self.intent.get("terms", []) if t["tier"] == "hard" and fnmatch.fnmatch("drop.rail", t["obs"])]
        if not hard or not obs:
            return []
        worst = {}
        for ob in obs:
            for ref, rail, _, dv, _ in ob["drops"]:
                worst[(ref, rail)] = max(worst.get((ref, rail), 0.0), dv)
        out = []
        for (ref, rail), dv in sorted(worst.items()):
            d = dict(id="drop.rail", scope=dict(kind="dc_drop", load=ref, rail=rail, parts=[ref], nets=[rail]))
            for t in OB.resolve([t for t in hard if OB._match(t, d, self.secs)], f"{ref}@{rail}"):
                if "max" in t:
                    lim = U.quantity(t["max"])[0]
                    out.append((t, f"{ref}@{rail}", dv, lim, max(0.0, dv - lim) / max(abs(lim), 1e-30)))
        return out

    def unchecked_hard(self):
        """The hard terms the router does not compute (their kinds), so its output never verified them."""
        return [t for t in self.intent.get("terms", []) if t["tier"] == "hard"
                and not any(fnmatch.fnmatch(k, t["obs"]) for k in self.ROUTED)]

    def dc_cost(self, ob):
        """The intent's cost of one corner's DC observation (kae.excite.dc.observe): its loss and drop terms."""
        _, P, _ = ob["loss"]
        c = 0.0
        for t in self.loss:
            c += U.rate(t["rate"], self.cur)[0] * P
        for ref, rail, _, dv, _ in ob["drops"]:
            # the evaluator's drop.rail observation of this load, matched and resolved as the evaluator does
            d = dict(id="drop.rail", scope=dict(kind="dc_drop", load=ref, rail=rail, parts=[ref], nets=[rail]))
            for t in OB.resolve([t for t in self.drop if OB._match(t, d, self.secs)], f"{ref}@{rail}"):
                r = U.rate(t["rate"], self.cur)[0]
                if "max" in t:
                    c += r * max(0.0, dv - U.quantity(t["max"])[0])
                elif "min" in t:
                    c += r * max(0.0, U.quantity(t["min"])[0] - dv)
                else:
                    c += r * dv
        return c


    # ------------------------------------------------------------------ hazards (shared schema)
    def hazards(self, hard_rows=None, checked_pairs=True, checked_dc=True):
        """What the routed board's reader must know: violated hard terms (block), hard terms the router never
        checked (warn), heating limits the width caps overrode, and a defaulted area price (info).
        hard_rows: [(term, instance, worst value, limit, violation)] from pair_hard and dc_hard;
        checked_pairs: False when no field solve priced the pair terms (plain routing); checked_dc: False when
        the DC band was not solved (its drops unknown)."""
        out = []
        for t, inst, val, lim, v in hard_rows or []:
            if v > 0:
                kind = t["obs"]
                out.append(dict(code="hard_term_violated", severity="block", category="electrical",
                                message=f"Hard requirement {t['id']} ({kind}) fails on {inst}: {U.fmt(val, 'V')} "
                                        f"against its limit {U.fmt(lim, 'V')}.",
                                objects=[t["id"], inst], evidence=dict(term=t["id"], obs=kind, measured_V=val,
                                                                       limit_V=lim, source=t.get("source"),
                                                                       why=t.get("why")),
                                fix="Move the parts it names closer or apart, give the router more room, or "
                                    "relax the term to a 'limit' with a rate if exceeding it is acceptable."))
        unchecked = self.unchecked_hard()
        if not checked_pairs:
            unchecked += [t for t in self.intent.get("terms", []) if t["tier"] == "hard"
                          and any(fnmatch.fnmatch(k, t["obs"]) for k in self.PHYS)]
        if not checked_dc:
            unchecked += [t for t in self.intent.get("terms", []) if t["tier"] == "hard"
                          and fnmatch.fnmatch("drop.rail", t["obs"]) and t not in unchecked]
        for t in unchecked:
            out.append(dict(code="hard_term_unchecked", severity="warn", category="data",
                            message=f"The router did not compute {t['obs']}, so hard term {t['id']} is unverified "
                                    f"on the routed board.",
                            objects=[t["id"]], evidence=dict(term=t["id"], obs=t["obs"]),
                            fix="Evaluate the routed board (kae.excite.evaluate, then kae.intent) before using it."))
        for c in self.capped:
            hard = c["tier"] == "hard"
            out.append(dict(code="heating_width_capped", severity="block" if hard else "warn", category="thermal",
                            message=f"{c['net']} needs {c['w_need_mm']:g} mm for {c['I_A']:g} A at {c['dT_K']:g} K "
                                    f"rise ({c['term']}), but its width is capped at {c['w_cap_mm']:g} mm.",
                            objects=[c["net"], c["term"]], evidence=dict(c, basis="IPC-2221"),
                            fix="Raise the net class's or the route.width.max_mm knob's maximum width, use a "
                                "pour or a second layer, or relax the heating term."))
        if not self.explicit_area:
            out.append(dict(code="area_cost_defaulted", severity="info", category="data",
                            message=f"Track widths traded copper loss against a default area price of "
                                    f"{self.area:g} {self.cur}/mm^2 (neutral/1); the intent did not set one.",
                            objects=["route.area_cost"], evidence=dict(area_cost=self.area, currency=self.cur,
                                                                      basis=AREA_COST_BASIS),
                            fix="Set knobs.route.area_cost: higher for narrower power tracks (dense boards), "
                                "lower for wider (battery or heat-limited designs)."))
        return out
