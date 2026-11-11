# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Differential pairs: which nets are one, whether one matters, and a hazard when it was not routed as one.

For reports and hazards only. Nothing here changes what the benchmark scores.

`detect(board, brief=None)` finds pairs by the net names KiCad's DRC pairs (the same
DRC_ENGINE::MatchDpSuffix rule the board's own `diff_pair_gap` rules use; `kae.route.rules`)
and by the brief's name and class matching when a brief is given. Each pair carries the
evidence that it is a real pair and the tier it matters at:

  rule       the board's own rules ask for it: a `.kicad_dru` rule with a `diff_pair_*` or
             `skew` constraint matching the net, or a net class that sets a diff-pair width or
             gap distinct from its defaults, or a class named for pairs;
  interface  the brief (or the net class name) places it in a high-speed serial interface:
             usb2, usb3, hdmi, displayport, pcie, sata, ethernet_mdi, mipi, lvds, serdes;
  name       only a complementary name (BAT+/BAT-, LED_P/LED_N, IN+/IN-).

The copper is measured once, by the bus scorecard (`kae.bus.scorecard`, its pair rows: pad-to-pad
skew, coupled share within 3 trace widths, vias per leg, the interface's skew limit from
`kae.bus.limits`). `tier_of` and `reference_stats` add what the scorecard does not have: the tier,
and where the pair runs relative to its reference plane; the scorecard carries both in its pair rows.
`hazards` reads those rows.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely import prepared as shapely_prepared

from . import rules as R

STEP_MM = 0.25                # sampling step along an arc
POWER_NAME = re.compile(r"^(/.*/)?([+-]?\d+V\d*|V[CDS][CDS].*|VBUS|VBAT|VIN|GND.*|AGND|DGND|PGND|VEE|VSS)$", re.I)

# The interfaces whose pairs a reviewer checks. name_iface (roles) and the brief use these names.
HS_INTERFACES = ("usb2", "usb3", "hdmi", "displayport", "pcie", "sata", "ethernet_mdi", "mipi", "lvds", "serdes")

# A pair is flagged uncoupled when less than this share of its pad-to-pad length runs coupled (the scorecard's coupled_3w).
COUPLED_MIN = 0.5


@dataclass
class Pair:
    p: str
    n: str
    tier: str = "name"            # rule | interface | name
    interface: str = ""           # brief's or class's interface, "" when unknown
    speed: str = ""
    confidence: float = 0.0       # the brief's, 0 without a brief
    kicad: bool = False           # KiCad's own suffix rule pairs these names
    why: list = field(default_factory=list)   # evidence strings

    def key(self):
        return tuple(sorted((self.p, self.n)))


def _candidate_names(names):
    """(a, b) pairs of net names KiCad pairs by name: complement exists, both non-power."""
    out = []
    seen = set()
    for n in sorted(names):
        if not n or POWER_NAME.match(n):
            continue
        m = R.complement_net(n)
        if not m or m == n or m not in names or POWER_NAME.match(m):
            continue
        k = tuple(sorted((n, m)))
        if k in seen:
            continue
        seen.add(k)
        out.append((n, m))
    return out


_CLASS_IFACE = (("usb3", r"USB\s*3|SS(TX|RX)"), ("usb2", r"USB"), ("hdmi", r"HDMI|TMDS"), ("displayport", r"\bDP\b|DISPLAYPORT"),
                ("pcie", r"PCIE|PCI_E"), ("sata", r"SATA"), ("ethernet_mdi", r"\bMDI\b|ETH|RJ45"), ("mipi", r"MIPI|CSI|DSI"),
                ("lvds", r"LVDS"), ("serdes", r"SERDES|SGMII|GT[XYHPL]|MGT"))
_DIFF_CLASS = re.compile(r"DIFF|\b(85|90|100|120)\s*_?(R|OHMS?)?\b|IMPEDANCE", re.I)


def _class_iface(nc):
    for iface, pat in _CLASS_IFACE:
        if re.search(pat, nc, re.I):
            return iface
    return ""


def _pair_rules(rules):
    """Condition texts of `.kicad_dru` rules that constrain nets as a pair or a matched group."""
    out = []
    for r in getattr(rules, "custom", None) or []:
        kinds = {c.get("type") or "" for c in (r.get("constraints") or [])}
        if kinds & {"diff_pair_gap", "diff_pair_uncoupled", "skew"} or ("length" in kinds and "DiffPair" in str(r.get("condition"))):
            out.append(str(r.get("condition") or ""))
    return out


def detect(board, brief=None):
    """The board's differential pairs (see the module docstring), by tier."""
    nets = board.nets if isinstance(board.nets, dict) else {n.name: n for n in board.nets}
    names = set(nets)
    found = {}
    for a, b in _candidate_names(names):
        found[tuple(sorted((a, b)))] = Pair(p=a, n=b, kicad=True, why=["names pair by KiCad's suffix rule"])
    for d in (brief or {}).get("diff_pairs") or []:
        if d["p"] in names and d["n"] in names:
            k = tuple(sorted((d["p"], d["n"])))
            pr = found.get(k) or Pair(p=d["p"], n=d["n"], why=["names pair by the brief"])
            pr.interface = d.get("interface") or pr.interface
            pr.speed = d.get("speed") or ""
            pr.confidence = float(d.get("confidence") or 0.0)
            pr.kicad = pr.kicad or bool(d.get("kicad_pair"))
            found[k] = pr
    for pr in found.values():
        _set_tier(board, pr, nets)
    return sorted(found.values(), key=lambda p: p.key())


def _polyline(t, step=STEP_MM):
    """The track as a polyline (arcs sampled on `step`); (points, per-piece length)."""
    a, b = tuple(t.start), tuple(t.end)
    m = getattr(t, "mid", None)
    if not m:
        return np.array([a, b], float)
    ax, ay, mx, my, bx, by = a[0], a[1], m[0], m[1], b[0], b[1]
    d = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    if abs(d) < 1e-9:
        return np.array([a, b], float)
    ux = ((ax**2 + ay**2) * (my - by) + (mx**2 + my**2) * (by - ay) + (bx**2 + by**2) * (ay - my)) / d
    uy = ((ax**2 + ay**2) * (bx - mx) + (mx**2 + my**2) * (ax - bx) + (bx**2 + by**2) * (mx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    t0, t1, tm = math.atan2(ay - uy, ax - ux), math.atan2(by - uy, bx - ux), math.atan2(my - uy, mx - ux)
    # direction through the mid point
    def norm(x):
        return (x + 2 * math.pi) % (2 * math.pi)
    s0, s1, sm = norm(t1 - t0), norm(tm - t0), 0
    ccw = norm(tm - t0) <= norm(t1 - t0)
    span = norm(t1 - t0) if ccw else -norm(t0 - t1)
    n = max(2, int(abs(span) * r / step) + 1)
    th = t0 + np.linspace(0, span, n)
    return np.stack([ux + r * np.cos(th), uy + r * np.sin(th)], axis=1)


def _set_tier(board, pr, nets=None):
    """Fill pr.tier (and interface from the class when unknown) from the board's rules and classes."""
    nets = nets if nets is not None else (board.nets if isinstance(board.nets, dict) else {n.name: n for n in board.nets})
    rules = getattr(board, "rules", None)
    classes = getattr(rules, "netclasses", {}) or {}
    default = classes.get("Default")
    conditions = _pair_rules(rules)
    na, nb = nets.get(pr.p), nets.get(pr.n)
    ca, cb = getattr(na, "netclass", ""), getattr(nb, "netclass", "")
    ci = classes.get(ca)
    in_diff_class = bool(ca == cb and ca != "Default" and _DIFF_CLASS.search(ca or ""))
    if not pr.interface or pr.interface == "unknown":
        pr.interface = _class_iface(ca or "") or _class_iface(cb or "") or pr.interface
    own_dp = ci is not None and default is not None and (
        (ci.diff_pair_width is not None and ci.diff_pair_width != default.diff_pair_width)
        or (ci.diff_pair_gap is not None and ci.diff_pair_gap != default.diff_pair_gap))
    base = R.diff_base(pr.p) or ""
    by_rule = any("diffpair" in c.lower() or pr.p in c or pr.n in c or (base and base in c) or (ca and ca != "Default" and ca in c)
                  for c in conditions)
    if by_rule:
        pr.why.append("a .kicad_dru rule constrains it")
    if own_dp and ca == cb:
        pr.why.append(f"net class '{ca}' sets a diff-pair width or gap")
    if in_diff_class:
        pr.why.append(f"net class '{ca}' names a differential class")
    if by_rule or (own_dp and ca == cb) or in_diff_class:
        pr.tier = "rule"
    elif pr.interface in HS_INTERFACES:
        pr.tier = "interface"
    else:
        pr.tier = "name"
    return pr


def tier_of(board, p, n, interface=""):
    """(tier, interface) of the pair p/n on `board`: what detect() would say for it."""
    pr = _set_tier(board, Pair(p=p, n=n, interface=interface or ""))
    return pr.tier, pr.interface


def reference_stats(board, pair, step=0.5):
    """Where the pair runs relative to its reference plane: (length with no plane on an adjacent layer,
    number of times the plane beneath changes net along the legs). Zones are outlines, not fills."""
    cu = list(getattr(getattr(board, "stackup", None), "copper", None) or [])
    if not cu:
        names = {t.layer for t in board.tracks} | {l for z in board.zones for l in z.layers}
        cu = sorted(n for n in names if n.endswith(".Cu"))
    adj = {l: [cu[i + k] for k in (-1, 1) if 0 <= i + k < len(cu)] for i, l in enumerate(cu)}
    planes = {l: [(z.net, shapely_prepared.prep(z.outline)) for z in board.zones
                  if l in z.layers and z.net and z.outline is not None] for l in cu}
    no_ref = 0.0
    changes = 0
    for t in board.tracks:
        if t.net not in (pair.p, pair.n) or t.layer not in adj:
            continue
        pts = _polyline(t)
        prev = None
        for u, v in zip(pts[:-1], pts[1:]):
            seg = float(np.hypot(*(v - u)))
            k = max(1, int(seg / step))
            for i in range(k):
                p = shapely.Point(u + (v - u) * ((i + 0.5) / k))
                nets = [n for l in adj[t.layer] for n, g in planes.get(l, ()) if g.contains(p)]
                ref = nets[0] if nets else None
                if ref is None:
                    no_ref += seg / k
                elif prev is not None and ref != prev:
                    changes += 1
                if ref is not None:
                    prev = ref
    return round(no_ref, 3), changes


def report(board, scorecard=None):
    """The scorecard's pair rows (kae.bus.scorecard.board_scorecard, computed when not given): skew_mm, coupled_3w,
    vias_lane, limit, plus tier, no_ref_mm and ref_changes. A row the scorecard could not measure (no two common end
    parts, or a leg with no pad-to-pad path) has no skew_mm and no coupled_3w."""
    if scorecard is None:
        from kae.bus.scorecard import board_scorecard
        scorecard = board_scorecard(board)
    out = []
    for r in scorecard.get("pairs") or []:
        if r.get("p") and r.get("n") and "tier" not in r:
            r = dict(r, tier=tier_of(board, r["p"], r["n"], r.get("iface") or "")[0])
        out.append(r)
    return out


def hazard_entries(rows, min_len=3.0):
    """kae.hazards entries from report() rows: pairs of tier rule or interface, measured, at least min_len mm a leg.
    pair_uncoupled is a warning; pair_skew is info, since kae.bus.limits' pair limits are vendor tables (TI's 5 mil for
    USB3 and PCIe) that many working human boards exceed."""
    from kae import hazards as H
    rows = [r for r in rows if r.get("tier") in ("rule", "interface") and r.get("coupled_3w") is not None
            and (r.get("len_mean") or 0.0) >= min_len]
    if not rows:
        return []
    name = lambda r: f"{r['p']}/{r['n']}"   # noqa: E731
    uncoupled = sorted((r for r in rows if r["coupled_3w"] < COUPLED_MIN), key=lambda r: r["coupled_3w"])
    lim = lambda r: (r.get("limit") or {}).get("skew_mm")   # noqa: E731
    skewed = sorted((r for r in rows if lim(r) is not None and r.get("skew_mm") is not None and r["skew_mm"] > lim(r)),
                    key=lambda r: -r["skew_mm"] / lim(r))
    out = []
    if uncoupled:
        out.append(H.make(
            "pair_uncoupled", "warn", "electrical",
            f"{len(uncoupled)} of {len(rows)} differential pairs run as two unrelated nets (less than {COUPLED_MIN:.0%} of the "
            "pad-to-pad length within 3 trace widths of the partner): DRC does not see this, a reviewer does.",
            objects=[name(r) for r in uncoupled],
            evidence=dict(pairs=len(rows), uncoupled=len(uncoupled), coupled_3w_worst=[r["coupled_3w"] for r in uncoupled[:8]],
                          source="kae.bus.scorecard coupled_3w"),
            fix="Route these pairs coupled (kae.route.cli --pairs), or say they are not pairs."))
    if skewed:
        out.append(H.make(
            "pair_skew", "info", "electrical",
            f"{len(skewed)} of {len(rows)} differential pairs are more skewed than their interface's limit (common mode grows "
            "with skew).",
            objects=[name(r) for r in skewed],
            evidence=dict(skew_mm_worst=[r["skew_mm"] for r in skewed[:8]], limit_mm=[lim(r) for r in skewed[:8]],
                          limit_source=[(r.get("limit") or {}).get("source") for r in skewed[:8]]),
            fix="Match the legs' lengths near the mismatch, or set the board's own skew rule."))
    return out


def hazards(board, min_len=3.0):
    """pair_uncoupled and pair_skew for a routed board (see hazard_entries)."""
    return hazard_entries(report(board), min_len=min_len)
