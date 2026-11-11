# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Differential pairs: which nets are one, whether one matters, and how it was laid.

Two independent readings, for reports and hazards only. Nothing here changes what the
benchmark scores.

`detect(board, brief=None)` finds pairs by the net names KiCad's DRC pairs (the same
DRC_ENGINE::MatchDpSuffix rule the board's own `diff_pair_gap` rules use; `kae.route.rules`)
and by the brief's name and class matching when a brief is given. Each pair carries the
evidence that it is a real pair and the tier it matters at:

  rule       the board's own rules ask for it: a `.kicad_dru` rule with a `diff_pair_*`,
             `skew within_diff_pairs` or `length` constraint matching the net, or a net
             class that sets a diff-pair width or gap distinct from its defaults;
  interface  the brief (or the net class name) places it in a high-speed serial interface:
             usb2, usb3, hdmi, displayport, pcie, sata, ethernet_mdi, mipi, lvds, serdes;
  name       only a complementary name: nothing says the pair is an interface or that the
             board treats it as one (BAT+/BAT-, LED_P/LED_N, IN+/IN-).

`measure(board, pair)` is what a reviewer reads off the copper: skew (absolute difference of
the legs' total length), share of the legs' length coupled to the other leg (edge to edge
within COUPLED_GAP_MM on the same layer), vias on each leg, layers used, length with no reference plane on an
adjacent layer and how often the plane net changes under the pair. An open or unrouted leg is reported as such, with no skew.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely import STRtree
from shapely import prepared as shapely_prepared

from . import rules as R

COUPLED_GAP_MM = 0.5          # edge to edge; the threshold E35 and dp_truth used (0.5 mm: Johnson's "close enough")
STEP_MM = 0.25                # sampling step along a track
POWER_NAME = re.compile(r"^(/.*/)?([+-]?\d+V\d*|V[CDS][CDS].*|VBUS|VBAT|VIN|GND.*|AGND|DGND|PGND|VEE|VSS)$", re.I)

# The interfaces whose pairs a reviewer checks. name_iface (roles) and the brief use these names.
HS_INTERFACES = ("usb2", "usb3", "hdmi", "displayport", "pcie", "sata", "ethernet_mdi", "mipi", "lvds", "serdes")

# Loosest published intra-pair skew limits (mm) among the sources cited in
# docs/topics/rules/interfaces/: above this, no vendor's guide accepts the pair. A pair's board-rule
# value, when it has one, replaces these (the board's own rules win).
SKEW_LIMIT_MM = dict(usb2=3.81, usb3=2.0, hdmi=3.0, displayport=3.0, pcie=0.635, sata=0.127, ethernet_mdi=2.0,
                     mipi=0.7, lvds=2.5, serdes=0.635)
SKEW_LIMIT_DEFAULT = 2.5      # mm, a pair of unknown interface in a net class that declares it a pair

# A pair is flagged uncoupled when less than this share of its length runs coupled.
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
    rules = getattr(board, "rules", None)
    classes = getattr(rules, "netclasses", {}) or {}
    default = classes.get("Default")
    conditions = _pair_rules(rules)
    for k, pr in found.items():
        na, nb = nets[pr.p], nets[pr.n]
        ca, cb = getattr(na, "netclass", ""), getattr(nb, "netclass", "")
        ci = classes.get(ca)
        in_diff_class = bool(ca == cb and ca != "Default" and _DIFF_CLASS.search(ca))
        if not pr.interface or pr.interface == "unknown":
            pr.interface = _class_iface(ca) or _class_iface(cb) or pr.interface
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


def measure(board, pair, gap=COUPLED_GAP_MM):
    """Reads the routed copper of one pair. Returns a dict (see module docstring)."""
    tracks = getattr(board, "tracks", None) or []
    vias = getattr(board, "vias", None) or []
    lens, coupled = {pair.p: 0.0, pair.n: 0.0}, {pair.p: 0.0, pair.n: 0.0}
    layers = set()
    by = {pair.p: {}, pair.n: {}}
    for t in tracks:
        if t.net not in lens:
            continue
        pts = _polyline(t)
        w = float(t.width)
        L = float(np.hypot(*np.diff(pts, axis=0).T).sum())
        lens[t.net] += L
        layers.add(t.layer)
        by[t.net].setdefault(t.layer, []).append((pts, w))
    vp = sum(1 for v in vias if v.net == pair.p)
    vn = sum(1 for v in vias if v.net == pair.n)
    total = 0.0
    for me, other in ((pair.p, pair.n), (pair.n, pair.p)):
        for layer, items in by[me].items():
            for pts, w in items:
                a, b = pts[:-1], pts[1:]
                L = np.hypot(*(b - a).T)
                total += float(L.sum())
            if layer not in by[other]:
                continue
            geoms = [shapely.buffer(shapely.linestrings(p), w2 / 2, quad_segs=2) for p, w2 in by[other][layer]]
            tree = STRtree(geoms)
            for pts, w in items:
                a, b = pts[:-1], pts[1:]
                for u, v in zip(a, b):
                    seg = float(np.hypot(*(v - u)))
                    if seg < 1e-6:
                        continue
                    k = max(1, int(seg / STEP_MM))
                    t_ = (np.arange(k) + 0.5) / k
                    xy = u + np.outer(t_, v - u)
                    ps = shapely.points(xy[:, 0], xy[:, 1])
                    i0, i1 = tree.query(ps, predicate="dwithin", distance=gap + w / 2 + 0.3)
                    g = np.full(k, np.inf)
                    if i0.size:
                        d = shapely.distance(ps[i0], np.array(geoms, dtype=object)[i1]) - w / 2
                        np.minimum.at(g, i0, d)
                    coupled[me] += float(np.sum((seg / k) * (g <= gap)))
    routed = lens[pair.p] > 0 and lens[pair.n] > 0
    share = None if total <= 0 else round((coupled[pair.p] + coupled[pair.n]) / total, 4)
    return dict(p=pair.p, n=pair.n, tier=pair.tier, interface=pair.interface, routed=routed,
                len_p=round(lens[pair.p], 3), len_n=round(lens[pair.n], 3),
                skew=round(abs(lens[pair.p] - lens[pair.n]), 3) if routed else None,
                coupled_share=share, vias_p=vp, vias_n=vn, layers=sorted(layers), **_ref_fields(board, pair))


def _ref_fields(board, pair):
    try:
        nr, ch = reference_stats(board, pair)
        return dict(no_ref_mm=nr, ref_changes=ch)
    except Exception:  # noqa: BLE001 - report-only
        return dict(no_ref_mm=None, ref_changes=None)


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


def report(board, brief=None, gap=COUPLED_GAP_MM):
    """Every detected pair with its measures; the report-only data of E36."""
    return [measure(board, p, gap=gap) for p in detect(board, brief=brief)]


def skew_limit(m):
    """Skew (mm) above which no cited vendor guide accepts this pair (SKEW_LIMIT_MM)."""
    return SKEW_LIMIT_MM.get(m.get("interface") or "", SKEW_LIMIT_DEFAULT)


def hazards(board, brief=None, min_len=3.0):
    """kae.hazards entries for pairs routed as two unrelated nets. Only pairs that matter (tier rule or
    interface), with both legs routed and at least min_len mm of copper (a very short pair has nothing to couple)."""
    from kae import hazards as H
    rows = [m for m in report(board, brief=brief) if m["tier"] in ("rule", "interface") and m["routed"]
            and m["len_p"] + m["len_n"] >= 2 * min_len]
    if not rows:
        return []
    uncoupled = [m for m in rows if (m["coupled_share"] or 0.0) < COUPLED_MIN]
    skewed = [m for m in rows if m["skew"] is not None and m["skew"] > skew_limit(m)]
    out = []
    if uncoupled:
        worst = sorted(uncoupled, key=lambda m: m["coupled_share"] or 0.0)
        out.append(H.make(
            "pair_uncoupled", "warn", "electrical",
            f"{len(uncoupled)} of {len(rows)} differential pairs run as two unrelated nets (less than {COUPLED_MIN:.0%} "
            f"of the copper within {COUPLED_GAP_MM} mm of the partner): DRC does not see this, a reviewer does.",
            objects=[f"{m['p']}/{m['n']}" for m in worst],
            evidence=dict(pairs=len(rows), uncoupled=len(uncoupled),
                          coupled_share_worst=[round(m["coupled_share"] or 0.0, 3) for m in worst[:8]],
                          coupled_gap_mm=COUPLED_GAP_MM, source="kae.route.pairs (E36)"),
            fix="Route these pairs coupled (kae.route.pair_route), or say they are not pairs."))
    if skewed:
        worst = sorted(skewed, key=lambda m: -m["skew"])
        out.append(H.make(
            "pair_skew", "warn", "electrical",
            f"{len(skewed)} of {len(rows)} differential pairs are more skewed than the loosest vendor limit for their "
            f"interface (common mode grows with skew).",
            objects=[f"{m['p']}/{m['n']}" for m in worst],
            evidence=dict(skew_mm_worst=[round(m["skew"], 2) for m in worst[:8]],
                          interface=[m["interface"] for m in worst[:8]], limit_source="pairs.SKEW_LIMIT_MM"),
            fix="Match the legs' lengths near the mismatch, or set the board's own skew rule."))
    return out
