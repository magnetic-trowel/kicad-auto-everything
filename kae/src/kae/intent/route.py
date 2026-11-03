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
AREA_COST = 0.05                   # neutral/1: currency per mm^2 of copper when the intent says nothing


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

    def dT_max(self, net):
        """The tightest heating limit (K) a term puts on the net's tracks, or None."""
        lims = [U.quantity(t["max"])[0] for t in self.heat if "max" in t and _net_matches(t, net, self.secs, "dc_heat")]
        return min(lims) if lims else None

    def width(self, net, I, t_mm, clearance, ladder, w_lo, w_hi):
        """(width mm, reason) for a hop of `net` on copper t_mm thick carrying corner currents I."""
        k, why = self.k_R(net, I)
        lo = max(w_lo, float(self.wmin.get(net, 0.0)))
        hi = min(w_hi if w_hi is not None else math.inf, float(self.wmax.get(net, math.inf)))
        dT = self.dT_max(net)
        Imax = max((abs(x) for x in I), default=0.0)
        if dT is not None and Imax > 0:
            from kae.route.critical_physics import ipc2221_width
            w_ipc = ipc2221_width(Imax, dT, t_mm, internal=False)
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
    HARD_RATE = 1e6                  # currency per V of a hard term's violation: never worth trading

    def pair_terms(self, bd, o, s):
        """The intent's terms on the (observer, aggressor) pair's peak voltage: [(term, rate per V, limit V or
        None, tier)]. Pairs no term names are not priced (and not solved) by the router."""
        from kae.excite import observe as O
        ob = O.observation(bd, o, s, [0.0], [0.0])
        out = []
        hit = [t for t in self.intent.get("terms", []) if t["tier"] not in ("report", "ignore")
               and any(fnmatch.fnmatch(k, t["obs"]) for k in self.PHYS) and OB._match(t, ob, self.secs)]
        for t in OB.resolve(hit, f"{o.name} <- {s.name}"):     # the most specific term, as the evaluator prices it
            lim = U.quantity(t["max"])[0] if "max" in t else None
            r = U.rate(t["rate"], self.cur)[0] if "rate" in t else self.HARD_RATE
            out.append((t, r, lim, t["tier"]))
        return out

    def dC_dV(self, terms, V):
        """d(intent cost)/d(peak V) of a pair at corner values V (array): each cost term's rate; each limit's
        rate where V exceeds it; a hard term's large rate where it is violated."""
        import numpy as np
        V = np.asarray(V, float)
        d = np.zeros_like(V)
        for t, r, lim, tier in terms:
            if tier == "cost":
                d += r
            elif lim is not None:
                d += r * (V > lim)
        return d

    def pair_cost(self, terms, V):
        """The intent's cost of a pair at corner peak voltages V (array), in its currency."""
        import numpy as np
        V = np.asarray(V, float)
        c = np.zeros_like(V)
        for t, r, lim, tier in terms:
            if tier == "cost":
                c += r * V
            elif lim is not None:
                c += r * np.maximum(0.0, V - lim)
        return c

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

