# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fab capability classes: what a fab builds at its standard price, as an advanced (surcharged
or reviewed) option, or only with HDI processes. kae never relaxes a board's rules; its
diagnoses (escape certificates, kae.route.blocked) suggest relaxations to the caller, and
every suggested value is clipped at the finest class of the board's fab and labelled with
the cheapest class that builds it (docs/topics/rules/dfm-fab-limits.md, "Fab classes").

PROFILES is the table: per fab, per class (cheapest first), the smallest value each
parameter may take, in mm, 1 oz copper:
- track, space: track width and track-to-track spacing;
- pad_track: copper of a (BGA) pad to a track;
- via: (diameter, drill) of the smallest via;
- via_in_pad: True where filled and capped vias in pads are part of the class (a number: from
  that many copper layers on).
`multilayer` keys apply to boards of 4 or more copper layers, `two_layer` to 1-2; a class
missing from a fab's table is one the fab does not publish (ask it). Which fab: the board's
KAE_FAB text variable, opts["fab"] (--set fab=...), else constraints.DEFAULTS["fab"];
opts["fab_profiles"] adds or replaces whole profiles (same shape).
"""
from __future__ import annotations

CLASSES = ("standard", "advanced", "hdi")

# Sources, read 2026-11-03 (dfm-fab-limits.md cites them):
# JLCPCB capabilities page (jlcpcb.com/capabilities/pcb-capabilities): 1-2 layer 0.10/0.10, multilayer
#   0.09/0.09 mm, "3 mil is acceptable in BGA fan-outs"; BGA pad-to-trace ">= 0.1 mm (min. 0.09 mm for
#   multilayer boards)"; via 0.15/0.25 mm minimum, "0.2mm or 0.25mm hole size with via diameter less than
#   0.45mm ... will cost more", 0.1/0.2 mm only for boards <= 1 mm with ENIG/OSP; HDI 1-3 step, laser blind
#   vias 0.075-0.15 mm, "3 mil / 3 mil; Extreme capability: 2.7 mil / 2.7 mil", "may increase both cost and
#   production time". JLCPCB BGA design guidelines: trace-to-BGA-pad 0.10 mm (2 and 4 layers), 0.076 mm
#   (3 mil) traces only "on some traces"; via-in-pad (POFV) free on 6-20 layer boards.
# PCBWay capabilities page: 0.1/0.1 mm (4/4 mil), drill 0.15 mm with a surcharge below 0.2 mm, via ring
#   0.15 mm; its advanced and HDI tables give difficulty tiers, not one number per class.
# OSH Park docs: 2 layer 6/6 mil, 10 mil drill, 5 mil ring; 4 layer 5/5 mil, 4 mil ring; no blind, buried
#   or filled vias.
PROFILES = {
    "jlcpcb": dict(
        name="JLCPCB",
        multilayer=dict(
            standard=dict(track=0.09, space=0.09, pad_track=0.10, via=(0.45, 0.20), via_in_pad=6,
                          cost="no surcharge (via-in-pad free from 6 layers)"),
            advanced=dict(track=0.076, space=0.076, pad_track=0.09, via=(0.25, 0.15), via_in_pad=True,
                          cost="surcharge: vias under 0.45 mm or drills under 0.2 mm; 3 mil tracks only "
                               "locally in BGA fan-outs; via-in-pad filled and capped (free from 6 layers)"),
            hdi=dict(track=0.069, space=0.069, pad_track=0.076, via=(0.20, 0.10), via_in_pad=True,
                     cost="HDI: laser microvias (0.075-0.15 mm), 2.7 mil extreme capability or a "
                          "0.1/0.2 mm via on a board <= 1 mm thick; more cost and lead time"),
        ),
        two_layer=dict(
            standard=dict(track=0.10, space=0.10, pad_track=0.10, via=(0.45, 0.20), via_in_pad=False,
                          cost="no surcharge"),
            advanced=dict(track=0.10, space=0.10, pad_track=0.10, via=(0.25, 0.15), via_in_pad=True,
                          cost="surcharge: vias under 0.45 mm or drills under 0.2 mm; via-in-pad filled "
                               "and capped"),
        ),
    ),
    "pcbway": dict(
        name="PCBWay",
        multilayer=dict(
            standard=dict(track=0.10, space=0.10, pad_track=0.10, via=(0.50, 0.20), via_in_pad=False,
                          cost="no surcharge"),
            advanced=dict(track=0.10, space=0.10, pad_track=0.10, via=(0.45, 0.15), via_in_pad=True,
                          cost="surcharge: drills under 0.2 mm; via-in-pad"),
        ),
    ),
    "oshpark": dict(
        name="OSH Park",
        multilayer=dict(standard=dict(track=0.127, space=0.127, pad_track=0.127, via=(0.458, 0.254),
                                      via_in_pad=False, cost="no surcharge (4 layer service)")),
        two_layer=dict(standard=dict(track=0.152, space=0.152, pad_track=0.152, via=(0.508, 0.254),
                                     via_in_pad=False, cost="no surcharge (2 layer service)")),
    ),
}

# the rule names of the diagnoses -> the profile parameter that limits them
PARAM = {"track width": "track", "clearance": "space", "via diameter": "via", "via-in-pad": "via_in_pad"}


def profile(name=None, opts=None, board_path=None):
    """The fab profile in force: dict(key, name, multilayer, two_layer)."""
    if name is None:
        from .constraints import setting
        name = setting("fab", board_path, opts)
    table = dict(PROFILES, **((opts or {}).get("fab_profiles") or {}))
    key = str(name).strip().lower()
    if key not in table:
        raise KeyError(f"unknown fab profile {name!r} (known: {', '.join(sorted(table))})")
    return dict(table[key], key=key)


def classes(prof, layers):
    """[(class, limits)] cheapest first, for a board of `layers` copper layers."""
    t = prof.get("two_layer") if layers <= 2 and prof.get("two_layer") else prof.get("multilayer") or {}
    return [(c, t[c]) for c in CLASSES if c in t]


def _ok(lim, param, value, layers):
    if param == "via_in_pad":
        v = lim.get("via_in_pad")
        return v is True or (not isinstance(v, bool) and isinstance(v, int) and layers >= v)
    m = lim.get(param)
    if m is None:
        return False
    if param == "via":
        D, d = value if isinstance(value, (tuple, list)) else (value, None)
        return D >= m[0] - 1e-6 and (d is None or d >= m[1] - 1e-6)
    return value >= m - 1e-6


def cheapest(prof, layers, param, value):
    """The cheapest class that builds `value` of `param`, or None (beyond every class)."""
    for c, lim in classes(prof, layers):
        if _ok(lim, param, value, layers):
            return c
    return None


def floor(prof, layers, param):
    """The smallest value of `param` the fab builds in any class (its finest), or None."""
    cs = [lim[param] for _c, lim in classes(prof, layers) if lim.get(param) is not None]
    return min(cs) if cs else None


def label(prof, layers, param, value):
    """dict(fab, fab_class, cost) for a suggested value (fab_class None: no class builds it)."""
    c = cheapest(prof, layers, param, value)
    lim = dict(classes(prof, layers)).get(c) or {}
    return dict(fab=prof["name"], fab_class=c, fab_cost=lim.get("cost"))


def hazard(prof, layers, entry, objects, what):
    """The manufacturing hazard of a suggestion beyond the fab's standard class, or None.
    `entry` carries rule, value, fab_class (label()); `what` says where (a package, a net)."""
    c = entry.get("fab_class")
    if c == "standard":
        return None
    v = entry.get("value")
    val = f" {v} mm" if isinstance(v, (int, float)) else ""
    if c is None:
        msg = (f"{what}: the suggested {entry['rule']}{val} is finer than any class {prof['name']} "
               f"publishes; it cannot be built there")
        sev = "warn"
    else:
        msg = (f"{what}: the suggested {entry['rule']}{val} needs {prof['name']}'s {c} class, not its "
               f"standard one ({entry.get('fab_cost')})")
        sev = "warn"
    std = dict(classes(prof, layers)).get("standard") or {}
    p = PARAM.get(entry["rule"].split(" (")[0], entry.get("param"))
    return dict(code="relaxation_beyond_standard_fab", severity=sev, category="manufacturing", message=msg,
                objects=list(objects), evidence=dict(rule=entry["rule"], value=v, fab=prof["name"], fab_class=c,
                                                     standard_limit=std.get(p) if p else None,
                                                     source="kae.route.fab.PROFILES (dfm-fab-limits.md)"),
                fix=(f"accept the {c} class and its cost at {prof['name']}, or prefer another relaxation the "
                     f"report lists (more layers, a smaller package pitch, via-in-pad)") if c else
                    "do not apply it; prefer another relaxation the report lists, or a fab with an HDI process")
