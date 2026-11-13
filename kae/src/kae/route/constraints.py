# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Effective routing constraints: what KiCad's DRC will require of every track and via the
router may draw, per net, copper layer and partner, reduced to what Freerouting can hold.

Freerouting's model is a set of net classes (a track width per layer, a via padstack, a
clearance matrix between clearance classes per layer) plus obstacles. KiCad's is a rule
engine evaluated per pair of items. `plan(info, board_path)` maps one onto the other:

- **Routing classes.** Nets that KiCad treats alike (same effective netclass, diff-pair
  membership, same width and via limits, same answers to net-specific custom rules) share
  a class. Width per layer = the netclass width (KiCad's "opt") clamped into [min, max] of
  the track-width constraint on that layer; via = netclass size raised to the via-diameter,
  hole-size and annular-ring minimums, in whole micrometres.
- **Vias.** Freerouting holds separate clearances for a class's vias when the class rule
  has typed clearances (wire_via, via_via): KiCad's hole-to-hole and hole clearances, which
  bind only vias, go there, so vias are not over-constrained against tracks or tracks
  against vias.
- **Clearance matrix.** For every pair of classes and layer: track-track, track-via and
  via-via clearances, each KiCad's requirement (rules.strictest) with hole clearance taken
  through the via's annular ring and hole-to-hole through both drills.
- **Pin classes.** Every pad gets a clearance class: its copper clearance to each routing
  class on each layer, raised by hole clearance through its annular ring, by solder-mask
  aperture clearance on outer layers (expansion + mask-to-copper), and by how far its real
  copper on a layer extends beyond the shape the DSN carries (per-layer padstacks, custom
  pads with several outlines).
- **Obstacles.** NPTH holes, board cut-outs and stray Edge.Cuts/Margin shapes, copper
  graphics and texts, solder-mask openings drawn as graphics (on their outer copper layer,
  minus room round the netted pads they expose: _mask_openings), rule areas and
  thermal-spoke corridors become keepouts, each in an
  obstacle class carrying KiCad's requirement (rule areas and corridors: zero). A copper
  graphic that carries a net becomes a pin of that net instead (net_graphics), so the
  router connects its net to it and keeps the other nets away. So does the fill of every
  zone named "kae-crit:..." (opts["crit_zones"], pours that kae.route.critical emitted): a
  hard obstacle for other nets at the zone's clearance, while the zone stays a plane of
  its own net; other zones are planes only, which other nets may cross (KiCad's refill
  flows around them).

All lengths mm. Requirements are rounded up to 0.1 um (the DSN resolution).
"""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

from . import rules as R

RES = 1e-4          # mm: DSN resolution (0.1 um)
EPS_SHORT = 0.001   # mm: smallest clearance kept against foreign copper (overlap is a short)


def up(v, q=RES):
    """Round up to a multiple of q (with a little slack for float noise)."""
    return math.ceil(v / q - 1e-6) * q


# ----------------------------------------------------------------------------- items
def net_item(info, net, kind, layer=None, width=None):
    """A routed track or via of `net` as a rules item."""
    nc = info["nets"].get(net, {}).get("netclass", "Default")
    it = dict(type="Track" if kind == "track" else "Via", net=net, netclass=nc,
              constituents=nc.split(","), copper=True, connected=True, layer=layer)
    if kind == "track":
        it.update(width=width, layers=[layer] if layer else [])
    else:
        it.update(via_type="Through", drilled=True, plated=True, layers=list(info["copper"]))
    return it


def pad_item(info, pad):
    net = pad.get("net") or ""
    nc = info["nets"].get(net, {}).get("netclass", "Default") if net else "Default"
    return dict(type="Pad", net=net, netclass=nc, constituents=nc.split(","),
                copper=bool(pad.get("layers")), connected=True,
                pad_type={"pth": "Through-hole", "smd": "SMD", "conn": "Edge connector",
                          "npth": "NPTH, mechanical"}.get(pad.get("attr"), "SMD"),
                fab_property=pad.get("fab") or "None", ref=pad.get("ref"), lib=pad.get("lib"),
                drilled=bool(pad.get("drilled")), override=pad.get("override"),
                local=pad.get("local_clearance"), layers=pad.get("layers") or [])


def graphic_item(info, g):
    net = g.get("net") or ""
    connected = g.get("cls") == "PCB_SHAPE"
    nc = info["nets"].get(net, {}).get("netclass", "Default") if net else "Default"
    it = dict(type="Graphic" if connected else "Text", copper=True, connected=connected,
              layers=list(g.get("layers") or []), ref=None if not g.get("owner") else g["owner"])
    if connected:
        it.update(net=net, netclass=nc, constituents=nc.split(","))
    return it


EDGE_ITEM = dict(type="Graphic", copper=False, connected=False, layer="Edge.Cuts", layers=["Edge.Cuts"])


# ----------------------------------------------------------------------------- data
@dataclass
class RoutingClass:
    name: str
    nets: list
    netclass: str
    widths: dict            # layer -> mm
    via: tuple              # (diameter, drill) mm, the real via
    rep: str = ""           # representative net
    rep2: str = ""          # a second net of the class (for same-class pairs), or ""


@dataclass
class ObstacleClass:
    name: str
    values: dict            # (routing class name, layer) -> clearance mm


@dataclass
class Obstacle:
    kind: str               # 'keepout' | 'via_keepout' | 'wire_keepout' (tracks only; vias pass, as in KiCad)
    layer: str              # copper layer name or 'signal'
    geom: object            # shapely Polygon / MultiPolygon, or ('circle', x, y, d)
    cls: str                # obstacle class name
    why: str = ""


@dataclass
class Plan:
    copper: list
    classes: dict = field(default_factory=dict)        # name -> RoutingClass
    net_class: dict = field(default_factory=dict)      # net -> routing class name
    matrix: dict = field(default_factory=dict)         # (R, S, layer) -> mm (R <= S by name)
    pin_class: dict = field(default_factory=dict)      # (comp, pin) -> obstacle class name
    pin_exact: dict = field(default_factory=dict)      # (comp, pin) -> {(class, layer): (track, via) mm} measured
                                                       # from the pad's real copper (Space), where the DSN shape
                                                       # lies inside it
    obstacle_classes: dict = field(default_factory=dict)
    obstacles: list = field(default_factory=list)
    net_graphics: list = field(default_factory=list)   # (net, {layer: polygon}, obstacle class, why)
    edge_clearance: float = 0.0                        # for Freerouting's board outline
    neck_width: float | None = None
    min_width: float = 0.0                             # narrowest legal track for every net
    notes: dict = field(default_factory=dict)
    rule_board: object = None
    bridging_openings: list = field(default_factory=list)  # (layer, polygon, why, nets): mask openings that
                                                           # shut a pad in or expose two nets (kae.route.blocked)
    pad_entry: str = "centreline"                      # where the grid router ends tracks at pads (pad_entry_mode)
    arc_policy: str = "arcs"                           # "arcs" or "keep45" (arc_policy)
    pad_rules: dict = field(default_factory=dict)      # info pad index -> PadRule (every pad routing may end on)
    process: str = "reflow"                            # soldering process (power_copper.process_of)
    hazards: list = field(default_factory=list)        # kae.hazards entries the plan raises (land_enlarged_by_track)
    mask: object = field(default=None, repr=False)     # _MaskIndex: other nets' mask apertures (PadRule.mask)

    def pad_rule(self, idx):
        """The PadRule of info pad `idx`, or None (a pad no routing ends on)."""
        return self.pad_rules.get(idx)


# ----------------------------------------------------------------------------- helpers
# clearance checks a board's project may turn off (rule_severities key -> constraint type)
IGNORABLE = {"clearance": "clearance", "hole_clearance": "hole_clearance", "copper_edge_clearance": "edge_clearance"}
# Our own limits apply only where the board's rules are silent, and each can be overridden without
# code: a KAE_<NAME> text variable in the KiCad project wins over the run's opts (<name>), which win
# over the default here.
DEFAULTS = dict(
    ignored_clearance_floor=0.1,   # mm: gap kept for a clearance check the board turns off (or the
                                   # board's own minimum, if larger); KiCad then checks only shorts
    plane_strict_share="odd",      # with planes "cost": inner layers whose one-net fill (refilled input)
                                   # covers at least this share of the board carry no traces (Freerouting
                                   # power layers); human boards leave 30 of 33 such layers at >= 0.8 free of
                                   # signals. "odd": 0.8 on odd seeds, none on even ones, so restarts try both
                                   # and the DRC picks (z280 needs it: ~94 open -> 3; heypcb kestrel, whose
                                   # human routes 1.6 m on its planes, is hurt: 28 -> 53); a number: every
                                   # seed; 0: never (bridge.strict_share)
    ball_escapes=1,                # 1: dog-bones for the inner rings of ball grids, laid with the plane
                                   # escapes (escape.dog_bones; gecko5 101 -> 69 open, nekoink 99 -> 77); 0: none
    pad_entry_overlap=0.05,        # mm: a track may end outside a pad when its copper still overlaps the pad by
                                   # this much (KiCad connects any overlap); a 0.4 mm-pitch WLP ball is left
                                   # cleanly no other way at 0.2 / 0.2 mm (critical_grid._escapes)
    pad_entry="centreline",        # where kae's grid router ends a track at a pad: "centreline" (rule D: the
                                   # plan's per-pad rule, pad_entry.centreline_targets: on the land's long centre
                                   # line, the crossing within 10 deg of the outline normal, no copper past the
                                   # land, necked at small two-terminal lands), or "centre" (snapped onto the pad
                                   # centre where legal; the A/B arm). "edge" (the superseded edge rule) reads as
                                   # "centreline". Env KAE_PAD_ENTRY when neither the project nor opts set it
    arc_policy="arcs",             # corners of shaped copper (taut, finish): "arcs" (tangent arcs) or "keep45"
                                   # (keep the board's 45/90 style: rule-genealogy R02/R03 keep 45 deg for
                                   # editability, an editing reason, not physics or fab); env KAE_ARC_POLICY
    escape_ground_vias=0,          # arm E (routing-stages.md): 1 lays power_copper's ground vias at decap and IC
                                   # ground pads in lastmile.plane_escapes, before routing, so the site is
                                   # reserved; 0: off (power copper fits them afterwards); env KAE_ESCAPE_GROUND_VIAS
    escape_band=0,                 # placement (kae.place.escape_band): the surface escapes of each ball grid
                                   # and fine-pitch ring kept free of parts that are not its own (1: a soft
                                   # annealer term; 2: hard occupancy against every part; 0: off). Off: on
                                   # escape-ab3 (63 merit boards x 3 seeds) soft left open connections unchanged
                                   # (ring boards -1.5%, grid boards +19% in total, per-board median +-0%) and hard
                                   # was worse on the grids (+11%); soft trims ~1 DRC error per run
    escape_band_w=1.0,             # weight of the soft band term (overlap / mean part area, as silk)
    escape_band_scale=1.0,         # band depth per side = scale x escapes on that side x (track + clearance)
    escape_band_max_mm=2.5,        # mm: the deepest band on one side
    escape_ring_pitch=0.5,         # mm: pad rings (QFN, QFP) at most this fine get bands
    place_severity="strict_then_level_c",  # placement legality: courtyards, copper-to-edge, rule areas,
                                   # clearance, shorts and hole clearance are errors whatever the project says.
                                   # "strict_then_level_c" (default) places with drawn courtyards and, only when
                                   # that leaves placement errors, again with courtyards at IPC Level C where
                                   # the project waives them (kae.place.pipeline LADDER); "strict" and
                                   # "level_c" one rung each; "board" follows the project (kae.place.problem)
    relax_bodies="escalate",       # placement: "escalate" (default) frees a courtyard-less part to its pads only when
                                   # legalization fails (each such overlap a body_overlap block hazard); "off" never;
                                   # "auto" also up front on a board over 95% full (kae.place.pipeline)
    place_w_cong=0.0,              # placement: weight of the annealer's RUDY + pin-escape congestion term
                                   # (kae.place.cost.Congestion). Off: the placement-decide-staged A/B (213
                                   # merit boards, k=2) found 0 / 10 / 30 equal (cp1 0.305 / 0.310 / 0.305,
                                   # completion 0.941-0.943), so the simpler setting wins; RUDY also ranks PCB
                                   # routability near chance (docs/research/placement/kae-routability-estimators.md)
    place_margin=0.0,              # placement: routing room between movable parts, mm (Problem.set_margin);
                                   # negative = auto (Problem.auto_margin: 2 x (0.7 - utilization), 0..1 mm).
                                   # 0: placement-decide-staged found auto and 0 equal (cp1 0.305 both,
                                   # completion 0.942 / 0.941), so the formula with no source is dropped
    connector_edge=2,              # placement: user-facing connectors kae places (kae.place.edge_check:
                                   # USB, barrel, audio, RJ/modular, video/D-sub; at or near 100 % on an
                                   # edge on human boards) 2: pinned to the edge facing out after the seed,
                                   # 1: only the connector_off_edge hazard, 0: neither (audit P4)
    fab="jlcpcb",                  # the fab whose classes clip and label suggested relaxations (escape
                                   # certificates, kae.route.blocked): kae.route.fab.PROFILES
    operating="",                  # placement and routing: the board's operating facts (JSON: requirements.thermal
                                   # heat sinks, parts' P_sustained_W; kae.place.heat); "" none
    heat_pull_w=1.0,               # placement: label-term weight per sustained W pulling a hot part into a region sink
    heat_min_W=0.25,               # placement and routing: parts dissipating less are not pulled (placement) and
                                   # get no thermal vias (routing)
    thermal_vias=1,                # routing (kae.route.thermal_vias): 1: each part dissipating heat_min_W or more
                                   # gets vias from its thermal pad and pour pads into the same net's copper on
                                   # the other face (a region sink's face, else the net's pour there); 0: off
    thermal_via_pitch=1.0,         # mm: grid pitch of thermal vias (the board's same-net via pitch still applies)
    thermal_via_max=16,            # thermal vias per part at most
    thermal_via_in_pad=1,          # 1: thermal vias inside an exposed pad (as critical routing's plane vias); 0:
                                   # only on the pour around it (for assembly that cannot plug vias in pads)
    escape_fanout=0,               # placement: 1 also reserves the dog-bone via sites of each ball grid on the
                                   # other side (no part there covers them); 0: off
    zone_pull=0.0,                 # placement (kae.place.zones): weight of pads off their own net's fixed copper
                                   # zone (all of them off = zone_pull x the seed HPWL), also the seed's pull and
                                   # package pins; 0: off. Off by default: zone-ab (48 boards, 3 seeds) at 3 left
                                   # 4.7 % more open (polarfire, sdi-mipi, nekoink worse): zone nets were 11-51 of
                                   # 168-545 opens without it, the router reaches planes by vias, and the pull cost
                                   # signal routing. Movable pads over their zone after 300 s, off / 1 / 3
                                   # (human): polarfire 139-151 / 268-283 / 265-361 of 465 (387), nekoink
                                   # 52-56 / 108-114 / 115-117 of 226 (196), gecko5 1-2 / 46-52 / 52-55 of 73
                                   # (61); HPWL no worse (polarfire 12.7k at 3 vs 15.8k off, same seed)
    tht_neck="on",                 # power copper (kae.route.power_copper, finish's "power" part): "on" necks grown
                                   # copper within neck_len of plated through-hole pads of power and ground nets to
                                   # the width their current needs (neck_rule tht; the routed track's width is kept),
                                   # so wave, selective and iron soldering are not starved of heat; "off": none.
                                   # Env KAE_THT_NECK when neither the project nor opts set it
    tht_wide="",                   # refs and ref.pad names (comma-separated, or a list in opts) whose THT pads keep
                                   # wide copper anyway: a heat path, a selectively soldered part (each necked pad
                                   # is a tht_pad_necked hazard naming this setting); env KAE_THT_WIDE
    zone_keepout=1.0,              # placement: weight of pads whose mask opening would bridge another net's
                                   # fixed outer-layer zone or sit in a board-level mask aperture with another
                                   # net (each 0.1 x this; gecko5: all staged DRC errors, 14 -> 0); 0: off
)


def _project(board_path):
    pro = Path(board_path).with_suffix(".kicad_pro")
    try:
        return json.loads(pro.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}


def board_severities(board_path):
    """DRC rule severities from the board's project file (as KiCad's DRC reads them)."""
    return ((_project(board_path).get("board") or {}).get("design_settings") or {}).get("rule_severities") or {}


def setting(name, board_path=None, opts=None):
    """One of our own limits (DEFAULTS): the project's KAE_<NAME> text variable, else opts[name],
    else the default. Numbers come back as floats; a word (plane_strict_share "odd") as it is, where
    the default is one too (a word for a numeric limit is skipped)."""
    tv = (_project(board_path).get("text_variables") or {}).get("KAE_" + name.upper()) if board_path else None
    for v in (tv, (opts or {}).get(name)):
        if v in (None, ""):
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            if isinstance(DEFAULTS[name], str):
                return v
    return DEFAULTS[name]


def setting_env(name, board_path=None, opts=None):
    """setting(), with env KAE_<NAME> where neither the project nor opts set it."""
    import os
    v = setting(name, board_path, opts)
    if v == DEFAULTS[name]:
        e = os.environ.get("KAE_" + name.upper())
        if e not in (None, ""):
            try:
                return float(e)
            except ValueError:
                return e if isinstance(DEFAULTS[name], str) else v
    return v


PAD_ENTRY_MODES = ("centreline", "centre")
ARC_POLICIES = ("arcs", "keep45")


def pad_entry_mode(board_path=None, opts=None):
    """The pad_entry setting ("centreline", rule D, or "centre"): project text variable, opts,
    else env KAE_PAD_ENTRY, else the default. The superseded "edge" reads as "centreline"."""
    v = setting_env("pad_entry", board_path, opts)
    v = "centreline" if v == "edge" else v
    return v if v in PAD_ENTRY_MODES else DEFAULTS["pad_entry"]


def arc_policy(board_path=None, opts=None):
    """The arc_policy setting ("arcs" or "keep45"): project text variable KAE_ARC_POLICY, opts,
    else env KAE_ARC_POLICY, else "arcs"."""
    v = setting_env("arc_policy", board_path, opts)
    return v if v in ARC_POLICIES else DEFAULTS["arc_policy"]


def rule_board(info, board_path, opts=None):
    dru = Path(board_path).with_suffix(".kicad_dru")
    rb = R.build(info["copper"], info["settings"], info["netclasses"], set(info["nets"]),
                 str(dru) if dru.exists() else None)
    # kelu124 pic0rick: clearance "ignore", GND in a 0.5 mm class beside 0.5 mm-pitch pins; the
    # human's tracks pass 0.245 mm from GND pads and DRC passes, ours walled the IC in (45 open)
    sev = board_severities(board_path)
    s = info["settings"]
    mins = {"clearance": s.get("min_clearance", 0.0), "hole_clearance": s.get("hole_clearance", 0.0),
            "edge_clearance": s.get("edge_clearance", 0.0)}
    floor = setting("ignored_clearance_floor", board_path, opts)
    # the same floor holds where a custom rule with severity ignore/warning wins (rules._soften)
    rb.soft_floor = {ct: max(floor, mins.get(ct) or 0.0) for ct in IGNORABLE.values()}
    rb.ignored = {ct: rb.soft_floor[ct] for key, ct in IGNORABLE.items() if _severity_ignored(sev, key)}
    return rb


def _strict_min(rb, ctype, a, b, layer):
    c = R.strictest(rb, ctype, a, b, layer)
    return c.min or 0.0


def _severity_ignored(severities, key):
    return severities.get(key) in ("ignore", "warning", "info", "exclusion")


def _width_choice(probe_w, strict, nc_width):
    """Width for a net on a layer: the opt (netclass) width clamped into [min, max]."""
    mn = max(v for v in ((probe_w or [None])[0], strict.min) if v is not None) if (probe_w or strict.min) else 0.0
    mx_c = [v for v in (((probe_w or [None, None, None])[2]), strict.max) if v is not None]
    mx = min(mx_c) if mx_c else None
    opt = (probe_w or [None, None])[1]
    if opt is None:
        opt = strict.opt if strict.opt is not None else nc_width
    w = opt if opt is not None else mn
    w = max(w, mn or 0.0)
    if mx is not None and w > mx:
        w = max(mx, mn or 0.0)
    return up(w), mn or 0.0, mx


def _via_choice(info, rb, net):
    """(diameter, drill, ring) for through vias of `net`, whole micrometres."""
    pr = info["probes"].get(net, {}).get("via", {})
    vi = net_item(info, net, "via")
    dia = R.strictest(rb, "via_diameter", vi)
    drl = R.strictest(rb, "hole_size", vi)
    ann = max([R.strictest(rb, "annular_width", vi, None, l).min or 0.0 for l in info["copper"]] +
              [v for v in (pr.get("annulus") or {}).values() if v is not None] + [0.0])
    pd, pdr = pr.get("diameter") or [None, None, None], pr.get("drill") or [None, None, None]
    d_min = max(v for v in (pdr[0], drl.min, 0.0) if v is not None)
    d_opt = pdr[1] if pdr[1] is not None else drl.opt
    d = max(d_opt or d_min, d_min)
    d_max = min([v for v in (pdr[2], drl.max) if v is not None] or [None]) if (pdr[2] or drl.max) else None
    if d_max is not None and d > d_max:
        d = max(d_max, d_min)
    D_min = max(v for v in (pd[0], dia.min, 0.0) if v is not None)
    D_opt = pd[1] if pd[1] is not None else dia.opt
    D = max(D_opt or D_min, D_min, d + 2 * ann)
    D_max = min([v for v in (pd[2], dia.max) if v is not None] or [None]) if (pd[2] or dia.max) else None
    if D_max is not None and D > D_max:
        D = max(D_max, D_min, d + 2 * ann)
    d = math.ceil(d * 1000 - 1e-6) / 1000
    D = math.ceil(D * 1000 - 1e-6) / 1000
    return D, d, (D - d) / 2


# ----------------------------------------------------------------------------- planning
def plan(info, board_path, opts=None):
    """The routing plan for a board (see the module docstring)."""
    opts = dict(opts or {})
    rb = rule_board(info, board_path, opts)
    cu = list(info["copper"])
    p = Plan(copper=cu, rule_board=rb)
    p.pad_entry = pad_entry_mode(board_path, opts)
    p.arc_policy = arc_policy(board_path, opts)
    sev = opts.get("severities") or {}
    s = info["settings"]

    # ---- per-net limits and signatures
    nets = [n for n in info["nets"] if n]
    custom_net_rules = [r for r in rb.rules if not r.implicit and r.text and
                        any(k in r.text.lower() for k in ("net", "indiffpair", "fromto", "memberof"))]
    sig_of, per_net = {}, {}
    for net in nets:
        pr = info["probes"].get(net, {})
        nc_name = info["nets"][net]["netclass"]
        nc = info["netclasses"].get(nc_name, {})
        widths, wmin = {}, {}
        for l in cu:
            ti = net_item(info, net, "track", l, width=None)
            strict = R.strictest(rb, "track_width", ti, None, l)
            w, mn, mx = _width_choice((pr.get("track") or {}).get(l, {}).get("width"), strict, nc.get("track_width"))
            widths[l], wmin[l] = w, mn
        D, d, ring = _via_choice(info, rb, net)
        dp = R.diff_base(net) is not None and R.complement_net(net) in info["nets"]
        rsig = []
        for r in custom_net_rules:
            for kind in ("track", "via"):
                it = net_item(info, net, kind, cu[0], widths[cu[0]])
                try:
                    rsig.append(R.truth(R.ev(r.condition, R.Ctx(it, None, cu[0], "", False, rb)))
                                if r.condition is not None else True)
                except KeyError:
                    rsig.append(None)
        sig = (nc_name, dp, tuple(widths[l] for l in cu), (D, d), tuple(rsig))
        sig_of[net] = sig
        per_net[net] = dict(widths=widths, wmin=wmin, via=(D, d), ring=ring)
    groups = {}
    for net in nets:
        groups.setdefault(sig_of[net], []).append(net)
    # class names: kae_<netclass>[_k]; never Freerouting's default class (see translate)
    order = sorted(groups.items(), key=lambda kv: (kv[0][0] != "Default", -len(kv[1]), kv[0][0]))
    used = set()
    for i, (sig, members) in enumerate(order):
        name = _class_name(sig[0], used)
        used.add(name)
        members = sorted(members)
        w = per_net[members[0]]["widths"]
        rc = RoutingClass(name=name, nets=members, netclass=sig[0], widths=dict(w), via=per_net[members[0]]["via"],
                          rep=members[0], rep2=members[1] if len(members) > 1 else "")
        p.classes[name] = rc
        for n in members:
            p.net_class[n] = name
    if not p.classes:  # a board with no nets still needs a class
        nc = info["netclasses"].get("Default", {})
        w = up(max(nc.get("track_width") or 0.0, s.get("min_track", 0.0)) or 0.2)
        p.classes["kae_Default"] = RoutingClass("kae_Default", [], "Default", {l: w for l in cu},
                                                  (max(nc.get("via_diameter") or 0.6, s.get("min_via", 0.0)),
                                                   max(nc.get("via_drill") or 0.3, s.get("min_drill", 0.0))))
    # Freerouting retries a connection it failed at min(class width, neck width) along its
    # whole length (one value for every class): the neck is the largest minimum (legal for
    # every class); with no minimum at all, the narrowest class width, so that a class wider
    # than its pads (a 0.64 mm USB class into a 0.5 mm pitch connector) still connects
    widths_all = [w for rc in p.classes.values() for w in rc.widths.values() if w]
    neck = max([v for pn in per_net.values() for v in pn["wmin"].values()] + [0.0])
    p.min_width = up(neck) if neck > 0 else 0.0
    if neck <= 0:
        neck = min(widths_all or [0.0])
    if neck > 0 and any(w > neck + 1e-9 for w in widths_all):
        p.neck_width = up(neck)

    # ---- class pair requirements: tracks and vias of R vs S, per layer
    names = sorted(p.classes)
    req = {}   # (R, S, layer) -> dict(ww, wv, vw, vv)
    for i, a in enumerate(names):
        for b in names[i:]:
            ra, rbc = p.classes[a], p.classes[b]
            na = ra.rep
            nb = rbc.rep if a != b else ra.rep2
            if not na or not nb:
                continue
            # a coupled diff pair's clearance is its gap (KiCad's implicit "diff pair" rule),
            # above or below the class clearance every other pair of the two classes needs
            # (bms-c1: /BAT- and /BAT+ represented Default_2 x HV at 0.25 mm, and Freerouting
            # laid /BAT- 0.28 mm from a /PACK+ via where KiCad wants HV's 0.3 mm): one coupled
            # and one uncoupled pair of the two classes, when they have them, the strictest kept
            pairs = [(na, nb)]
            for want in (True, False):
                if _coupled(na, nb) != want:
                    alt = next(((x, y) for x in ra.nets for y in rbc.nets
                                if x and y and x != y and _coupled(x, y) == want), None)
                    if alt is not None:
                        pairs.append(alt)
            for l in cu:
                rs = [pair_clearances(info, rb, x, y, l, ra.widths[l], rbc.widths[l], ra.via, rbc.via) for x, y in pairs]
                req[(a, b, l)] = {k: max(r[k] for r in rs) for k in rs[0]}
    # same-net via pairs: hole-to-hole between two vias of one net (Freerouting has no
    # clearance within a net; recorded so the repair loop knows what to look for)
    for n in names:
        rc = p.classes[n]
        if rc.rep:
            va = net_item(info, rc.rep, "via")
            h = _strict_min(rb, "hole_to_hole", va, dict(va), None)
            p.notes.setdefault("same_net_via_pitch", {})[n] = up(h + rc.via[1])
    for (a, b, l), r in req.items():
        p.matrix[(a, b, l)] = (up(max(r["ww"], EPS_SHORT)), up(max(r["wv"], r["vw"], EPS_SHORT)),
                               up(max(r["vv"], EPS_SHORT)))

    # ---- pins
    pin_req = {}
    outside = opts.get("pad_shapes") == "outside"
    pad_vec = {i: _pad_requirements(info, rb, p, pad, sev, outside=outside)
               for i, pad in enumerate(info["pads"]) if pad.get("pin") and pad.get("layers")}
    # solder-mask openings drawn as graphics: keepouts, and around the pads they expose a
    # clearance raised to cover the opening where a keepout would shut the pad in
    mask_obs = _mask_openings(info, p, sev, pad_vec, outside)
    for i, vec in pad_vec.items():
        pad = info["pads"][i]
        key = tuple(sorted(vec.items()))
        cls = pin_req.get(key)
        if cls is None:
            cls = f"kae_pin{len(pin_req)}"
            pin_req[key] = cls
            p.obstacle_classes[cls] = ObstacleClass(cls, dict(vec))
        p.pin_class[(pad["comp"], pad["pin"])] = cls
        if not outside:
            # the DSN shape lies inside the real copper (chords of rounded corners, a custom pad's
            # first outline): the class above adds the largest excess on every side. For exact
            # checks against the real copper (critical_space.Space) the requirement without it
            dsn, real = _pad_shapes(pad)
            if any(_excess(real.get(l), dsn) > 1e-6 for l in pad["layers"]):
                p.pin_exact[(pad["comp"], pad["pin"])] = _pad_requirements(info, rb, p, pad, sev, outside=True)

    # ---- obstacles
    _obstacles(info, rb, p, sev, opts)
    p.obstacles.extend(mask_obs)

    # ---- the board outline (Freerouting applies one value to every class)
    edge_vals = [v[0] for v in p.obstacle_classes.get("kae_edge", ObstacleClass("", {})).values.values()]
    p.edge_clearance = max(edge_vals) if edge_vals else s.get("edge_clearance", 0.0)
    p.notes["unsupported_functions"] = sorted(rb.unsupported)
    p.notes["rule_errors"] = list(rb.errors)
    if rb.dru_rejected:
        p.notes["dru_rejected"] = rb.dru_rejected   # KiCad drops the file: no custom rules applied

    # ---- per-pad entry rules: rule D, necks, current, mask web (PadRule)
    _pad_rules(info, p, board_path, opts, sev)
    return p


def _coupled(na, nb):
    """Whether nets na and nb form a diff pair as KiCad matches them (AB.isCoupledDiffPair)."""
    return bool(na and nb and R.diff_base(na) is not None and R.complement_net(na) == nb)


def pair_clearances(info, rb, na, nb, layer, wa=None, wb=None, via_a=None, via_b=None):
    """KiCad's requirements between copper of nets `na` and `nb` on `layer`, in mm:
    dict(ww, wv, vw, vv) for track-track, track of a - via of b, via of a - track of b and
    via-via, with hole clearance taken through each via's annular ring and hole-to-hole
    through both drills; a diff pair's own gap raises track-track. `wa`, `wb` are the track
    widths (rules may test Width) and `via_a`, `via_b` the vias as (diameter, drill)."""
    l = layer
    Da, da = via_a or (0.0, 0.0)
    Db, db = via_b or (0.0, 0.0)
    ringa, ringb = (Da - da) / 2, (Db - db) / 2
    ta = net_item(info, na, "track", l, wa)
    tb = net_item(info, nb, "track", l, wb)
    va, vb = net_item(info, na, "via", l), net_item(info, nb, "via", l)
    ww = _strict_min(rb, "clearance", ta, tb, l)
    wv = max(_strict_min(rb, "clearance", ta, vb, l), _strict_min(rb, "hole_clearance", ta, vb, l) - ringb)
    vw = max(_strict_min(rb, "clearance", va, tb, l), _strict_min(rb, "hole_clearance", tb, va, l) - ringa)
    vv = max(_strict_min(rb, "clearance", va, vb, l),
             _strict_min(rb, "hole_to_hole", va, vb, None) + (da + db) / 2 - (Da + Db) / 2,
             _strict_min(rb, "hole_clearance", va, vb, l) - ringb,
             _strict_min(rb, "hole_clearance", vb, va, l) - ringa)
    if R.diff_base(na) is not None and R.complement_net(na) == nb:
        gap = R.strictest(rb, "diff_pair_gap", ta, tb, l).min or 0.0
        ww = max(ww, gap)
    return dict(ww=ww, wv=wv, vw=vw, vv=vv)


def _class_name(netclass, used):
    base = "kae_" + "".join(ch if ch.isalnum() else "_" for ch in netclass)[:40]
    name, k = base, 1
    while name in used:
        k += 1
        name = f"{base}_{k}"
    return name


def via_name(rc, n_layers):
    """A class's via padstack: Via[0-n]_<D>:<d>_um in whole micrometres (Freerouting drops a
    decimal fraction from via names, KiCad reads the drill from the name)."""
    return f"Via[0-{n_layers - 1}]_{round(rc.via[0] * 1000)}:{round(rc.via[1] * 1000)}_um"


# ----------------------------------------------------------------------------- pads
def _poly(rings):
    if not rings or len(rings[0]) < 3:
        return None
    g = Polygon(rings[0], [h for h in rings[1:] if len(h) >= 3])
    return g if g.is_valid else g.buffer(0)


def _pad_shapes(pad):
    """(dsn shape, {layer: real copper}) as shapely geometry. KiCad's DSN pin carries one
    shape for all layers (the pad's ALL_LAYERS shape, first outline of a custom pad)."""
    real = {}
    if "poly" in pad:
        g = unary_union([x for x in (_poly(r) for r in pad["poly"]) if x is not None])
        for l in pad["layers"]:
            real[l] = g
        first = _poly(pad["poly"][0]) if pad["poly"] else None
    else:
        byl = pad.get("poly_by_layer") or {}
        for l, polys in byl.items():
            real[l] = unary_union([x for x in (_poly(r) for r in polys) if x is not None])
        f = byl.get(pad["layers"][0]) if pad["layers"] else None
        first = _poly(f[0]) if f else None
    return first, real


def _excess(real, dsn):
    """How far `real` copper reaches beyond the `dsn` shape (directed Hausdorff, mm)."""
    if real is None or dsn is None or real.is_empty:
        return 0.0
    out = real.difference(dsn.buffer(1e-6))
    if out.is_empty or out.area < 1e-10:
        return 0.0
    pts = shapely.get_coordinates(shapely.segmentize(out.boundary, 0.01))
    return max(float(dsn.distance(Point(x, y))) for x, y in pts) if len(pts) else 0.0


def _ring(pad, dsn):
    """Smallest distance from the pad's hole edge to the DSN shape's boundary (negative when
    the hole is not inside the shape)."""
    h = pad.get("hole")
    if not h or dsn is None:
        return None
    seg = LineString([h["a"], h["b"]]) if h["a"] != h["b"] else Point(h["a"])
    return float(dsn.exterior.distance(seg)) - h["width"] / 2 if dsn.contains(seg) else -h["width"] / 2


def _pad_requirements(info, rb, p, pad, sev, outside=False):
    """{(routing class, layer): clearance mm} for one pad (see module docstring). `outside`: the
    DSN pin is the pad's own copper (pad_shapes "outside", translate.circumscribe_pins), so the
    clearance needs no allowance for chords inside the outline (applied on every side, that
    allowance closed the one legal escape between 0.4 mm-pitch pads 0.2 mm apart at 0.2 mm
    clearance: kata0510 rp2040, qubik bmps)."""
    s = info["settings"]
    cu = p.copper
    pi = pad_item(info, pad)
    dsn, real = _pad_shapes(pad)
    ring = _ring(pad, dsn)
    mask_on = not _severity_ignored(sev, "solder_mask_bridge") and not pad.get("allow_bridges")
    out = {}
    own = pad.get("net") or ""
    for n, rc in p.classes.items():
        if not rc.rep:
            continue
        # the class's tracks that need the clearance are other nets': a representative on the
        # pad's own net reads net-conditional rules wrongly ("A.Net != B.Net" never holds; on
        # oasis C2's +18V pad got the class's 0.15 mm instead of the custom rule's 0.2 mm,
        # and Freerouting routed 30 um inside it)
        rep = rc.rep if rc.rep != own else next((x for x in rc.nets if x and x != own), rc.rep)
        D, d = rc.via
        rv = (D - d) / 2
        for l in cu:
            if l not in pad["layers"]:
                continue
            e = 0.0 if outside else _excess(real.get(l), dsn)
            t = net_item(info, rep, "track", l, rc.widths[l])
            v = net_item(info, rep, "via", l)
            tw = _strict_min(rb, "clearance", pi, t, l) + e
            vw = _strict_min(rb, "clearance", pi, v, l) + e
            if pad.get("hole"):
                hc_t = _strict_min(rb, "hole_clearance", pi, t, l)
                hc_v = _strict_min(rb, "hole_clearance", pi, v, l)
                if ring is not None:
                    tw = max(tw, hc_t - ring)
                    vw = max(vw, hc_v - ring)
                if pad.get("drilled") and ring is not None:
                    vw = max(vw, _strict_min(rb, "hole_to_hole", pi, v, None) - rv - ring)
            vw = max(vw, _strict_min(rb, "hole_clearance", v, pi, l) - rv + e)
            side = "F" if l == cu[0] else ("B" if l == cu[-1] else None)
            if mask_on and side and side in (pad.get("mask") or {}):
                m = pad["mask"][side] + s.get("mask_to_copper", 0.0) + e
                tw = max(tw, m)
                tented = s.get("tent_vias_front" if side == "F" else "tent_vias_back", True)
                vw = max(vw, m if tented else m + s.get("mask_min_web", 0.0) + s.get("mask_expansion", 0.0))
            if pad.get("attr") == "npth" and pad.get("hole") and pad["hole"]["a"] != pad["hole"]["b"]:
                ec_t = _strict_min(rb, "edge_clearance", t, EDGE_ITEM, l)
                ec_v = _strict_min(rb, "edge_clearance", v, EDGE_ITEM, l)
                tw, vw = max(tw, ec_t + e), max(vw, ec_v + e)
            out[(n, l)] = (up(max(tw, EPS_SHORT)), up(max(vw, EPS_SHORT)))
    return out


# ----------------------------------------------------------------------------- obstacles
def _obstacle_class(p, prefix, vec):
    for name, oc in p.obstacle_classes.items():
        if name.startswith(prefix) and oc.values == vec:
            return name
    name = f"{prefix}{sum(1 for k in p.obstacle_classes if k.startswith(prefix))}"
    p.obstacle_classes[name] = ObstacleClass(name, dict(vec))
    return name


def _zero_class(p):
    name = "kae_zero"
    if name not in p.obstacle_classes:
        p.obstacle_classes[name] = ObstacleClass(name, {(n, l): (0.0, 0.0) for n in p.classes for l in p.copper})
    return name


def _edge_geoms(info):
    """(cut-outs and stray edge geometry as polygons, board region). Edges are Edge.Cuts
    shapes at zero width (board and footprint) and Margin shapes at their stroke width."""
    board = None
    rings = info.get("outline") or []
    polys = [x for x in (_poly(r) for r in rings) if x is not None]
    if polys:
        board = unary_union(polys)
    cut = []
    for pg in polys:
        for h in pg.interiors:
            hp = Polygon(h)
            if hp.area > 1e-8:
                cut.append(hp)
    stray = []
    bnd = board.boundary if board is not None else None
    for e in info.get("edges") or []:
        g = _edge_line(e)
        if g is None or g.is_empty or g.length <= 1e-9:
            continue  # zero-length edge shapes (gitberthe, keebio, neotron): nothing to keep out,
                      # and shapely.segmentize raises on them
        w = e.get("width", 0.0) if e.get("layer") == "Margin" else 0.0
        if e.get("layer") == "Edge.Cuts" and bnd is not None:
            pts = shapely.get_coordinates(shapely.segmentize(g, 0.05))
            if all(bnd.distance(Point(x, y)) < 0.002 for x, y in pts):
                continue  # part of the outline: Freerouting's boundary or a cut-out
        stray.append(g.buffer(max(w / 2, 0.0005), quad_segs=8))
    return cut, stray, board


def _edge_line(e):
    k = e.get("kind")
    if k == "segment":
        return LineString(e["pts"])
    if k == "arc":
        from kae.board.geom import arc_points
        return LineString(arc_points(tuple(e["pts"][0]), tuple(e["pts"][1]), tuple(e["pts"][2]), 0.001))
    if k == "circle":
        return Point(e["center"]).buffer(e["radius"], quad_segs=64).exterior
    if k == "rect":
        (x1, y1), (x2, y2) = e["pts"]
        return box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)).exterior
    if k == "poly":
        gs = [x for x in (_poly(r) for r in e.get("rings") or []) if x is not None]
        return unary_union([g.boundary for g in gs]) if gs else None
    if k == "polyline" and len(e.get("pts") or []) >= 2:
        return LineString(e["pts"])
    return None


def _obstacles(info, rb, p, sev, opts):
    cu = p.copper
    # ---- edges: Freerouting's outline and the edge class carry the track requirement; where
    # vias need more (KiCad's board setup often asks more of vias than a custom track rule),
    # a via keepout band of the difference lines every edge
    vec, band = {}, 0.0
    for n, rc in p.classes.items():
        if not rc.rep:
            continue
        for l in cu:
            t = net_item(info, rc.rep, "track", l, rc.widths[l])
            v = net_item(info, rc.rep, "via", l)
            ew = _strict_min(rb, "edge_clearance", t, EDGE_ITEM, l)
            ev_ = _strict_min(rb, "edge_clearance", v, EDGE_ITEM, l)
            vec[(n, l)] = (up(max(ew, 0.0)), up(max(ev_, 0.0)))
            band = max(band, ev_)
    p.obstacle_classes["kae_edge"] = ObstacleClass("kae_edge", vec)
    track_edge = max(v[0] for v in vec.values()) if vec else 0.0
    cut, stray, board = _edge_geoms(info)
    for g in cut:
        p.obstacles.append(Obstacle("keepout", "signal", g, "kae_edge", "board cut-out"))
    for g in stray:
        p.obstacles.append(Obstacle("keepout", "signal", g, "kae_edge", "edge shape"))
    p.notes["via_edge_band"] = round(band, 4)
    if band > track_edge + 1e-6 and board is not None and not opts.get("no_band"):
        # Freerouting's outline has one clearance for tracks and vias: a band inside the
        # outer outline keeps vias at their own distance (cut-outs and stray edges carry
        # both values in their class)
        w = up(band)
        shell = unary_union([Polygon(pg.exterior) for pg in getattr(board, "geoms", [board])])
        inner = shell.buffer(-w, quad_segs=16)
        geo = shell.difference(inner) if not inner.is_empty else shell
        if not geo.is_empty:
            p.obstacles.append(Obstacle("via_keepout", "signal", geo, _zero_class(p), "via edge band"))
    # ---- NPTH round holes (KiCad exports them as round keepouts at hole + board hole clearance)
    for pad in info["pads"]:
        h = pad.get("hole")
        if not h or not pad.get("round_keepout"):
            continue
        pi = pad_item(info, pad)
        vec = {}
        for n, rc in p.classes.items():
            if not rc.rep:
                continue
            D, d = rc.via
            for l in cu:
                t = net_item(info, rc.rep, "track", l, rc.widths[l])
                v = net_item(info, rc.rep, "via", l)
                tw = _strict_min(rb, "hole_clearance", pi, t, l)
                vw = max(_strict_min(rb, "hole_clearance", pi, v, l),
                         _strict_min(rb, "hole_to_hole", pi, v, None) + d / 2 - D / 2)
                if pad.get("attr") != "npth":
                    tw = max(tw, _strict_min(rb, "clearance", pi, t, l))
                    vw = max(vw, _strict_min(rb, "clearance", pi, v, l))
                vec[(n, l)] = (up(max(tw, EPS_SHORT)), up(max(vw, EPS_SHORT)))
        cls = _obstacle_class(p, "kae_hole", vec)
        p.obstacles.append(Obstacle("keepout", "signal", ("circle", h["a"][0], h["a"][1], h["width"]), cls,
                                    f"hole {pad['ref']}.{pad['number']}"))
    # ---- copper graphics and texts (no net: shorts; with a net: foreign copper)
    for g in info.get("graphics") or []:
        gi = graphic_item(info, g)
        vec = {}
        for n, rc in p.classes.items():
            if not rc.rep:
                continue
            for l in cu:
                if l not in g["layers"]:
                    continue
                t = net_item(info, rc.rep, "track", l, rc.widths[l])
                v = net_item(info, rc.rep, "via", l)
                tw = _strict_min(rb, "clearance", gi, t, l)
                vw = _strict_min(rb, "clearance", gi, v, l)
                vec[(n, l)] = (up(max(tw, EPS_SHORT)), up(max(vw, EPS_SHORT)))
        if not vec:
            continue
        cls = _obstacle_class(p, "kae_cu", vec)
        why = f"copper {g.get('cls')} {g.get('owner') or 'board'} {g.get('net') or 'no net'}"
        shapes = {}
        for l, polys in g["layers"].items():
            geo = unary_union([x for x in (_poly(r) for r in polys) if x is not None])
            if not geo.is_empty:
                shapes[l] = geo
        net = g.get("net") or ""
        if net in p.net_class and shapes and all(isinstance(s, Polygon) and len(s.interiors) == 0
                                                 for s in shapes.values()):
            # copper of a net: a pin of that net in the DSN (a connection target for its
            # own net, an obstacle in class `cls` for the others)
            p.net_graphics.append((net, shapes, cls, why))
            continue
        for l, geo in shapes.items():
            p.obstacles.append(Obstacle("keepout", l, geo, cls, why))
    # ---- kae.route.critical's pours: hard obstacles for the other nets
    for z in opts.get("crit_zones") or []:
        net = z.get("net") or ""
        if net not in p.net_class:
            continue
        nc = info["nets"].get(net, {}).get("netclass", "Default")
        zi = dict(type="Zone", net=net, netclass=nc, constituents=nc.split(","), copper=True,
                  connected=True, layers=list(z.get("layers") or []))
        zc = z.get("clearance") or 0.0
        vec = {}
        for n, rc in p.classes.items():
            if not rc.rep:
                continue
            ring = (rc.via[0] - rc.via[1]) / 2
            for l in cu:
                t = net_item(info, rc.rep, "track", l, rc.widths[l])
                v = net_item(info, rc.rep, "via", l)
                tw = max(zc, _strict_min(rb, "clearance", zi, t, l))
                vw = max(zc, _strict_min(rb, "clearance", zi, v, l), _strict_min(rb, "hole_clearance", zi, v, l) - ring)
                vec[(n, l)] = (up(max(tw, EPS_SHORT)), up(max(vw, EPS_SHORT)))
        cls = _obstacle_class(p, "kae_crit", vec)
        for l, polys in (z.get("layers") or {}).items():
            for rings in polys:
                g = _poly(rings)
                for part in (_hole_free(g) if g is not None else []):
                    p.net_graphics.append((net, {l: part}, cls, f"zone {z.get('name')} {net}"))
    # ---- rule areas: KiCad's disallow test is plain intersection
    for z in info.get("zones") or []:
        if not z.get("rule_area") or not (z.get("no_tracks") or z.get("no_vias")):
            continue
        geo = unary_union([x for x in (_poly(r) for r in z["rings"]) if x is not None])
        if geo.is_empty:
            continue
        # no tracks but vias allowed (e.g. a board's unused layer: a full-layer area): a through via
        # passes, as KiCad's disallow test does; a plain keepout would stop every via on the board
        kind = ("keepout" if z.get("no_vias") else "wire_keepout") if z.get("no_tracks") else "via_keepout"
        zc = _zero_class(p)
        for l in z["layers"]:
            p.obstacles.append(Obstacle(kind, l, geo, zc, f"rule area {z.get('name') or ''} {z.get('owner') or ''}"))
    # ---- thermal-spoke corridors: for the pads named in opts["thermal_pads"] (pad uuids;
    # the repair loop adds the pads KiCad reports starved), or for all pads with "all"
    pads = opts.get("thermal_pads")
    if pads:
        for geo, layer, pad in thermal_corridors(info, p, None if pads == "all" else set(pads), sev):
            p.obstacles.append(Obstacle("keepout", layer, geo, _zero_class(p),
                                        f"thermal spokes {pad['ref']}.{pad['number']}"))


def _mask_openings(info, p, sev, pad_vec, outside=False):
    """Keepouts for the solder-mask openings drawn as
    graphics (board and footprint shapes and texts on F.Mask/B.Mask).

    KiCad's DRC (drc_test_provider_solder_mask.cpp) counts a bridge whenever one such
    opening exposes copper of two nets on its outer layer (within the mask-to-copper
    clearance); no-net copper never bridges, and openings in footprints that allow
    bridges are skipped. So the router's copper of a net must stay out of an opening that
    exposes another net's copper, and of an empty one altogether. An opening becomes a
    keepout (class kae_mask: mask-to-copper clearance), minus a hole round every netted pad
    it exposes, so the pad's net can still reach it: the hole is as large as the pad's own
    clearance (other nets keep that far away anyway). An opening that shuts a pad in (no gap
    a track of its net fits through on the hole's rim: a solder jumper's, a crystal's) is left
    out, as before (raising the pad's clearance over its share of the opening walled
    protocentral pulse-express in: 5 -> 12-13 open).

    Before, any opening that touched a pad was left out entirely: a fiducial's mask ring
    touching its no-net dot let other nets' tracks through it (adafruit fona: HP+ under FID1),
    a text over a jumper's corner did too (lenaschimmel bestelampe 'Lampe': one track, 36-42
    bridges)."""
    if _severity_ignored(sev, "solder_mask_bridge") or not info.get("mask_openings"):
        return []
    cu = p.copper
    m2c = info["settings"].get("mask_to_copper", 0.0)
    side_layer = {"F.Mask": cu[0], "B.Mask": cu[-1]}
    allow = {pad.get("comp") for pad in info["pads"] if pad.get("allow_bridges")}
    exposed = {}  # layer -> [(pad index, real copper, clearance of other nets from it, own track width)]
    for i, vec in pad_vec.items():
        pad = info["pads"][i]
        net = pad.get("net") or ""
        if not net:
            continue
        dsn, real = _pad_shapes(pad)
        for l in (cu[0], cu[-1]):
            g = real.get(l)
            if g is None or g.is_empty or l not in pad["layers"]:
                continue
            e = 0.0 if outside else _excess(g, dsn)
            r = min(min(v) for (n, ll), v in vec.items() if ll == l) - e if any(ll == l for _, ll in vec) else 0.0
            rc = p.classes.get(p.net_class.get(net))
            w = rc.widths[l] if rc else 0.0
            exposed.setdefault(l, []).append((i, g, max(r, 0.0), w))
    trees = {l: shapely.STRtree([g for _, g, _, _ in v]) for l, v in exposed.items()}
    vec = {(n, l2): (up(max(m2c, EPS_SHORT)), up(max(m2c, EPS_SHORT))) for n in p.classes for l2 in cu}
    obs = []
    for m in info["mask_openings"]:
        l = side_layer.get(m.get("layer"))
        if l is None or (m.get("owner") and m["owner"] in allow):
            continue
        geo = unary_union([x for x in (_poly(r) for r in m.get("polys") or []) if x is not None])
        if geo.is_empty:
            continue
        reach_geo = geo.buffer(m2c) if m2c > 0 else geo
        hits = []
        if l in trees:
            for k in trees[l].query(reach_geo):
                i, g, r, w = exposed[l][int(k)]
                if g.intersects(reach_geo):
                    hits.append((i, g, r, w))
        keep = geo
        shut = False
        for i, g, r, w in hits:
            hole = g.buffer(r, quad_segs=8)
            if hole.exterior.difference(geo.buffer(m2c + 1e-4)).length < max(w, 1e-3):
                shut = True   # a pad the opening shuts in (a jumper's, a crystal's): left as before
                break
            keep = keep.difference(hole)
        nets = sorted({info["pads"][j].get("net") or "" for j, _, _, _ in hits})
        if shut or len(nets) > 1:
            # KiCad counts a bridge for any copper of a net in an opening that exposes another
            # net's: the holes let a pad's own net in (the router joins a jumper's pads at the
            # price of bridges, jkiv cm4-carrier JP1-JP4); kae.route.blocked holds it exactly
            p.bridging_openings.append((l, reach_geo, f"mask opening {m.get('cls')} {m.get('owner') or 'board'}", nets))
        if shut or keep.is_empty or keep.area < 1e-6:
            continue
        obs.append(Obstacle("keepout", l, keep, _obstacle_class(p, "kae_mask", vec),
                            f"mask opening {m.get('cls')} {m.get('owner') or 'board'}"
                            + (f" (around {len(hits)} pads)" if hits else "")))
    return obs


def _hole_free(g):
    """Simple polygons that together cover polygon `g`: each hole is cut open by a vertical
    line through it (a DSN pin shape has no holes)."""
    from shapely.ops import split
    out, todo = [], [g]
    while todo:
        q = todo.pop()
        if not isinstance(q, Polygon) or q.is_empty or q.area < 1e-9:
            continue
        if not q.interiors:
            out.append(q)
            continue
        x = Polygon(q.interiors[0]).representative_point().x
        _, y0, _, y1 = q.bounds
        pieces = [x_ for x_ in split(q, LineString([(x, y0 - 1), (x, y1 + 1)])).geoms]
        if len(pieces) < 2:
            out.append(Polygon(q.exterior))
            continue
        todo.extend(pieces)
    return out


def thermal_corridors(info, p, pad_uuids=None, sev=None):
    """[(geometry, layer, pad)]: strips to keep foreign copper out of so that KiCad's zone
    filler can draw enough thermal spokes for a pad that connects to a zone of its net with
    thermal relief (starved_thermal; a pad whose spokes are all cut is also left unconnected).

    A spoke runs from the pad along one of four directions (the pad's spoke angle + k*90)
    and must land in zone fill past the thermal gap. Fill can only exist inside the zone,
    away from foreign pads and copper by the zone clearance and from the board edge; so each
    strip (spoke width + 2 clearances wide, reaching past the gap by the zone's minimum width)
    is cut to that potential fill, and only the `min_resolved_spokes` strips with the most
    landing area are kept. `pad_uuids` limits the pads (None: all).

    A strip gives way where it would block another pin's only escape (gives_way): strips that
    block none are preferred; when fewer than `min_resolved_spokes` of those are left and the
    pad has a way out for a track itself, the pad gets no strips at all. Its zone then reaches
    it through the routing or not at all (has_way): KiCad reports no starved thermal for a pad with no
    spoke that a track joins to its net (checked with kicad-cli on a pad with every spoke cut),
    and a lone spoke would be one (actual 1 < 2). bancouver40 dogema48: with a 0.508 mm zone
    clearance, the strips of a 0.5 mm-pitch QFN's GND pins closed their neighbours' only
    escapes, every seed; the human's GND pins there have no spokes and no error."""
    if sev and _severity_ignored(sev, "starved_thermal"):
        return []
    s = info["settings"]
    need = int(s.get("min_resolved_spokes") or 2)
    zones = [z for z in info.get("zones") or [] if not z.get("rule_area") and z.get("net") and not z.get("teardrop")]
    out = []
    if not zones or need <= 0:
        return out
    board = None
    rings = info.get("outline") or []
    polys = [x for x in (_poly(r) for r in rings) if x is not None]
    if polys:
        board = unary_union(polys)
    foreign_cache = {}
    lane_w = max(s.get("min_track") or 0.0, 0.1)
    by_layer = {}

    def pads_on(layer):
        """(STRtree, [(pad, copper)]) of every pad with copper on `layer`."""
        if layer not in by_layer:
            items = []
            for q in info["pads"]:
                g = _pad_shapes(q)[1].get(layer)
                if g is not None and not g.is_empty:
                    items.append((q, g))
            by_layer[layer] = (shapely.STRtree([g for _, g in items]), items)
        return by_layer[layer]

    def free_lanes(q, g, layer):
        """Straight ways out of pad q (copper g) for a track of the board's minimum width along
        its own axes that cross no other pad: where a track from it can go."""
        tree, items = pads_on(layer)
        cx, cy = q["pos"]
        x0, y0, x1, y1 = g.bounds
        far = max(x1 - cx, cx - x0, y1 - cy, cy - y0) + 1.0
        out = []
        for k in range(4):
            a = math.radians((q.get("orient") or 0.0) + 90 * k)
            lane = LineString([(cx, cy), (cx + far * math.cos(a), cy - far * math.sin(a))]).buffer(
                lane_w / 2, cap_style="flat")
            if board is not None and not board.contains(lane):
                continue
            hit = False
            for i in tree.query(lane):
                o, og = items[int(i)]
                if o is not q and o.get("net") != q.get("net") and og.intersects(lane):
                    hit = True
                    break
            if not hit:
                out.append(lane.difference(g))
        return out

    def has_way(q, g, layer):
        """Whether a track can leave pad q (copper g): a free lane, or a short straight piece to
        another pad of its net that crosses no other net's pad (a QFN's exposed pad to its GND pins)."""
        if free_lanes(q, g, layer):
            return True
        from shapely.ops import nearest_points
        tree, items = pads_on(layer)
        for i in tree.query(g.buffer(2.0)):
            o, og = items[int(i)]
            if o is q or o.get("net") != q.get("net"):
                continue
            a, b2 = nearest_points(g, og)
            piece = LineString([a, b2]).buffer(lane_w / 2) if a.distance(b2) > 1e-6 else None
            if piece is None or not any(oo.get("net") != q.get("net") and oog.intersects(piece)
                                        for oo, oog in (items[int(j)] for j in tree.query(piece))):
                return True
        return False

    def gives_way(strip, pad, layer):
        """Whether `strip` (the pad's strips together) covers every free lane of some other pin
        (another net's pad next to it)."""
        tree, items = pads_on(layer)
        for i in tree.query(strip.buffer(lane_w)):
            q, g = items[int(i)]
            if q is pad or q.get("net") == pad.get("net") or not q.get("net"):
                continue
            lanes = free_lanes(q, g, layer)
            if lanes and all(strip.intersection(x).area > 1e-6 for x in lanes):
                return True
        return False

    def foreign(layer, net, clr):
        key = (layer, net, round(clr, 4))
        if key not in foreign_cache:
            geos = []
            for q in info["pads"]:
                if q.get("net") == net and net:
                    continue
                _, rq = _pad_shapes(q)
                g = rq.get(layer)
                if g is not None and not g.is_empty:
                    geos.append(g.buffer(clr, quad_segs=4))
                h = q.get("hole")
                if h and not rq.get(layer):
                    geos.append(LineString([h["a"], h["b"]]).buffer(h["width"] / 2 + clr) if h["a"] != h["b"]
                                else Point(h["a"]).buffer(h["width"] / 2 + clr))
            for g in info.get("graphics") or []:
                if g.get("net") == net and net:
                    continue
                for r in (g.get("layers") or {}).get(layer, []):
                    pg = _poly(r)
                    if pg is not None:
                        geos.append(pg.buffer(clr, quad_segs=4))
            foreign_cache[key] = unary_union(geos) if geos else Polygon()
        return foreign_cache[key]

    for pad in info["pads"]:
        if not pad.get("net") or not pad.get("layers"):
            continue
        if pad_uuids is not None and pad.get("uuid") not in pad_uuids:
            continue
        dsn, real = _pad_shapes(pad)
        for z in zones:
            if z["net"] != pad["net"]:
                continue
            conn = pad.get("zone_connection") or "inherited"
            if conn == "inherited":
                conn = z.get("pad_connection") or "thermal"
            if conn == "thru_hole_only":
                conn = "thermal" if pad.get("attr") == "pth" else "full"
            if conn != "thermal":
                continue
            zg = unary_union([x for x in (_poly(r) for r in z["rings"]) if x is not None])
            for l in pad["layers"]:
                if l not in z["layers"]:
                    continue
                cop = real.get(l)
                if cop is None or cop.is_empty or not zg.intersects(cop):
                    continue
                gap = pad.get("thermal_gap") or z.get("thermal_gap") or 0.5
                mt = z.get("min_thickness") or 0.0
                # KiCad draws no spoke wider than the pad (kata0510 rp2040: the human's GND pin
                # U2.19, 0.2 mm wide between 0.4 mm-pitch neighbours that both escape straight
                # out, has its spokes with the zone's 0.508 mm spoke width; a strip that wide
                # closed both neighbours' only escapes)
                rr = cop.minimum_rotated_rectangle
                rc = list(rr.exterior.coords) if rr.geom_type == "Polygon" else []
                pmin = min(math.dist(rc[0], rc[1]), math.dist(rc[1], rc[2])) if len(rc) >= 3 else None
                sw = pad.get("spoke_width") or z.get("spoke_width") or 0.5
                if pmin:
                    sw = min(sw, pmin)
                sw = max(sw, mt)
                clr = max(z.get("clearance") or 0.0, s.get("min_clearance", 0.0))
                fill = zg
                if board is not None:
                    fill = fill.intersection(board.buffer(-s.get("edge_clearance", 0.0)))
                fill = fill.difference(foreign(l, pad["net"], clr))
                if fill.is_empty:
                    continue
                cx, cy = pad["pos"]
                minx, miny, maxx, maxy = cop.bounds
                half = max(maxx - cx, cx - minx, maxy - cy, cy - miny)
                reach = half + gap + max(mt, 0.1) + clr
                ring = cop.buffer(gap, quad_segs=8)
                cand = []
                for k in range(4):
                    # KiCad lays the spokes out in the pad's frame: the spoke angle is relative to the
                    # pad's orientation (bancouver40: a 45-degree QFN's GND pins U1.15 and U1.23 got
                    # axis-aligned corridors across their neighbours' only escapes, every seed)
                    a = math.radians((pad.get("spoke_angle") or 0.0) + (pad.get("orient") or 0.0) + 90 * k)
                    ex, ey = cx + reach * math.cos(a), cy - reach * math.sin(a)
                    strip = LineString([(cx, cy), (ex, ey)]).buffer(sw / 2 + clr, cap_style="flat")
                    # fill the spoke can reach: pieces of the strip's fill that enter the relief gap
                    # (beyond a foreign pad in its way, fill is no landing: KiCad's spoke stops there)
                    sf = strip.intersection(fill)
                    land = unary_union([q for q in getattr(sf, "geoms", [sf]) if q.intersects(ring)] or [Polygon()])
                    land = land.difference(ring)
                    if land.area < sw * max(mt, 0.05):
                        continue
                    cand.append((land.area, strip.intersection(fill.union(ring)).difference(cop.buffer(1e-4))))
                cand.sort(key=lambda t: -t[0])
                clear = []    # the best strips that, together, leave every neighbour a way out
                for c in cand:
                    if len(clear) < need and not gives_way(unary_union([g for _, g in clear] + [c[1]]), pad, l):
                        clear.append(c)
                if len(clear) < min(need, len(cand)) and has_way(pad, cop, l):
                    continue      # strips that close a neighbour in: none, the pad joins its net by a track
                if len(clear) >= min(need, len(cand)):
                    cand = clear
                corridor = unary_union([g for _, g in cand[:need]]) if cand else None
                if corridor is not None and not corridor.is_empty:
                    out.append((corridor, l, pad))
    return out


# ----------------------------------------------------------------------------- validation
# ----------------------------------------------------------------------------- per-pad entry rules
ENTRY_DEG = 10.0      # degrees off the outline normal the crossing piece of a rule-D entry may run
MASK_REACH = 1.0      # mm beyond a land within which other nets' mask apertures are looked at


class PadRule:
    """How copper may end on one pad (the plan's copy; every producer and checker reads it):

    - **Rule D** (`targets`): pad_entry.centreline_targets on the land, the crossing within
      ENTRY_DEG of the outline normal, no copper past the land (pad_entry.overhang), and no
      approach that leaves less than the board's solder-mask web to another net's aperture
      (`mask_on`).
    - **Neck** (`neck`): power_copper.neck_rule for the lands of two-terminal SMD parts, by the
      assembly process, the land's package class and the part's series current; None: no neck.
    - **Current** (`current_a`, `need`): the pad's current (power_copper.pad_currents on the
      operating facts) and the width it asks (power_copper.current_need), the floor of any neck.
    The frame and the mask apertures are computed on first use and kept."""

    __slots__ = ("idx", "ref", "number", "net", "layers", "smd", "neck", "series_a", "current_a", "need",
                 "two_terminal", "_pad", "_plan", "_land", "_frame", "_mask")

    def __init__(self, idx, pad, plan):
        self.idx, self._pad, self._plan = idx, pad, plan
        self.ref, self.number, self.net = pad.get("ref"), pad.get("number") or pad.get("pin"), pad.get("net") or ""
        self.layers = tuple(pad.get("layers") or ())
        self.smd = pad.get("attr") == "smd"
        self.neck, self.series_a, self.current_a, self.need = None, 0.0, 0.0, 0.0
        self.two_terminal = False
        self._land = self._frame = None
        self._mask = {}

    def __repr__(self):
        return f"PadRule({self.ref}.{self.number}, {self.net!r}, neck={self.neck}, need={self.need:.3f})"

    @property
    def land(self):
        """The land's copper as the router sees it (the DSN shape, else the union of its layers)."""
        if self._land is None:
            dsn, real = _pad_shapes(self._pad)
            g = dsn
            if g is None or g.is_empty:
                vals = [x for x in real.values() if x is not None and not x.is_empty]
                g = unary_union(vals) if vals else Polygon()
            self._land = g
        return self._land

    @property
    def frame(self):
        """pad_entry.pad_frame of the land: (centre, long axis u, normal v, long side, short side)."""
        if self._frame is None:
            from . import pad_entry as PE
            self._frame = PE.pad_frame(self.land)
        return self._frame

    @property
    def land_w(self):
        return self.frame[4]

    def mask_on(self, layer):
        """(apertures, web) on `layer`: the solder-mask openings near the land that expose other
        nets' copper (their pads grown by their mask expansion, and drawn openings that expose
        this pad's net and another), and the board's minimum mask web; None when no mask check
        applies (inner layer, bridges allowed or ignored, nothing near)."""
        if layer not in self._mask:
            m = self._plan.mask
            self._mask[layer] = m.near(self, layer) if m is not None else None
        return self._mask[layer]

    def width_at(self, w, min_w=0.0):
        """The width of the final piece for copper of width w: w, or the neck (never below the
        current's need nor min_w) where w is wider; and the stub the wide copper then keeps off the
        outline (pad_entry.NECK_LEN + w/2), else None."""
        from . import pad_entry as PE
        if self.neck is None or w <= self.neck + 1e-9:
            return w, None
        wn = max(self.neck, self.need, min_w)
        if wn >= w - 1e-9:
            return w, None
        return wn, PE.NECK_LEN + w / 2

    def targets(self, release, width, land=None, layer=None, stub=None, check_overhang=True):
        """Rule-D targets [(approach point a, end, kind)] from `release` at `width` (pad_entry.
        centreline_targets with this pad's rules); `land`: the copper to enter (default the pad's
        own), `layer`: for the mask web."""
        from . import pad_entry as PE
        return PE.centreline_targets(self.land if land is None else land, release, width, stub=stub,
                                     max_deg=ENTRY_DEG, check_overhang=check_overhang,
                                     mask=self.mask_on(layer) if layer is not None else None)


class _MaskIndex:
    """Other nets' mask apertures per outer layer, for PadRule.mask_on (built on first use)."""

    def __init__(self, info, plan, sev):
        self.info, self.plan = info, plan
        cu = plan.copper
        self.outer = {cu[0]: "F", cu[-1]: "B"} if cu else {}
        self.on = not _severity_ignored(sev, "solder_mask_bridge")
        s = info.get("settings") or {}
        self.web = float(s.get("mask_min_web", 0.0) or 0.0)
        self._trees = None

    def _build(self):
        self._trees = {}
        for l, side in self.outer.items():
            geoms, owners = [], []
            for i, pad in enumerate(self.info.get("pads") or []):
                if not pad.get("net") or l not in (pad.get("layers") or ()) or side not in (pad.get("mask") or {}):
                    continue
                _dsn, real = _pad_shapes(pad)
                g = real.get(l)
                if g is None or g.is_empty:
                    continue
                e = float(pad["mask"][side] or 0.0)
                ap = g.buffer(e, quad_segs=8) if e > 0 else g
                geoms.append(ap)
                owners.append((pad.get("net"), pad.get("comp")))
            for layer, geo, _why, nets in self.plan.bridging_openings:
                if layer == l and len(nets) > 1:
                    geoms.append(geo)
                    owners.append((tuple(nets), None))
            self._trees[l] = (shapely.STRtree(geoms) if geoms else None, geoms, owners)

    def near(self, rule, layer):
        if not self.on or layer not in self.outer or rule._pad.get("allow_bridges"):
            return None
        if self._trees is None:
            self._build()
        tree, geoms, owners = self._trees.get(layer, (None, [], []))
        if tree is None:
            return None
        land = rule.land
        out = []
        for k in tree.query(land.buffer(MASK_REACH + max(rule.frame[3], 0.0))):
            net, comp = owners[int(k)]
            if isinstance(net, tuple):
                if rule.net not in net:
                    continue                 # an opening this net never reaches (a keepout for it)
            elif net == rule.net:
                continue
            out.append(geoms[int(k)])
        return (out, self.web) if out else None


_ROLES = {}


def _roles(board_path, nets, opts):
    """(power, ground) net sets: opts "power" / "ground" when given; else the physics brief's rails
    and grounds (kae.circuit.brief, as power_copper.classify; cached per board content) together with
    the nets pad_entry.current_net names a rail or ground (on the 12 pad-entry boards the brief
    finds 24 rails the names miss, V_BATT, PWRIN, IPSOUT..., and misses 2 they find, secsense 3V3
    and VIN); switch nodes never. Names alone when no brief can be built."""
    from . import pad_entry as PE
    from . import power_copper as PC
    g_n = {n for n in nets if PE.GND_RE.search(n.rsplit("/", 1)[-1])}
    p_n = {n for n in nets if n not in g_n and PE.current_net(n)}
    p_b, g_b, sw = set(), set(), set()
    brief = opts.get("brief")
    if brief is None and board_path:
        try:
            import hashlib
            key = hashlib.sha1(Path(board_path).read_bytes()).hexdigest()      # staged copies share it
        except OSError:
            key = None
        if key is not None and key not in _ROLES:
            try:
                from kae.board.kicad_file import load
                from kae.circuit.brief import build
                b = load(board_path)
                _ROLES.clear() if len(_ROLES) > 64 else None
                _ROLES[key] = (build(b),)
            except Exception:                       # noqa: BLE001 - names are the fallback
                _ROLES[key] = None
        hit = _ROLES.get(key) if key is not None else None
        if hit is not None:
            brief = hit[0]
    if brief is not None:
        p_b, g_b, sw, _v = PC.classify(brief, nets)
    ground = set(opts["ground"]) if opts.get("ground") is not None else (g_n | g_b)
    power = set(opts["power"]) if opts.get("power") is not None else ((p_n | p_b) - ground - set(sw))
    return power, ground


def _pad_rules(info, p, board_path, opts, sev):
    """Fill p.pad_rules, p.process and p.hazards (see PadRule). Rails and grounds from the brief and
    the names (_roles), currents from the operating facts (opts "operating", else the project's
    KAE_OPERATING, as power_copper)."""
    from . import pad_entry as PE
    from . import power_copper as PC
    pads = info.get("pads") or []
    for i, pad in enumerate(pads):
        if pad.get("pin") and pad.get("layers") and pad.get("net"):
            p.pad_rules[i] = PadRule(i, pad, p)
    p.mask = _MaskIndex(info, p, sev)
    nets = {r.net for r in p.pad_rules.values()}
    power, ground = _roles(board_path, nets, opts)
    op = PC._operating(board_path, opts.get("operating")) if board_path else None
    asm = ((op or {}).get("requirements") or {}).get("assembly") or {}
    p.process = PC.process_of(asm)
    margin = float(opts.get("current_margin", PC.DEFAULTS["current_margin"]))
    pad_nets = [(r.ref, r.net) for r in p.pad_rules.values()]
    nets_of = {}
    for ref, net in pad_nets:
        nets_of.setdefault(ref, set()).add(net)
    cur = PC.pad_currents(op, pad_nets, power, ground) if op else {}
    net_cur = PC.net_currents(op, nets_of, power, ground) if op else {}
    for r in p.pad_rules.values():
        r.current_a = cur.get((r.ref, r.net), 0.0)
        r.need = PC.current_need(r.current_a, margin)
    # necks: the copper pads of each part (pads with no net count: a two-terminal part has two)
    by_comp = {}
    for i, pad in enumerate(pads):
        if pad.get("pin") and pad.get("layers") and pad.get("comp") is not None:
            by_comp.setdefault(pad.get("comp"), []).append(i)
    lands = {}
    for comp, idxs in by_comp.items():
        if len(idxs) != 2 or not all(pads[i].get("attr") == "smd" for i in idxs):
            continue
        lands[comp] = [(i, True, pads[i].get("net") or "",
                        p.pad_rules[i].land_w if i in p.pad_rules else PadRule(i, pads[i], p).land_w) for i in idxs]
    necks, series = PC.land_necks(lands, power, ground, net_cur, p.process, margin)
    if not opts.get("neck", True):
        necks = {}
    for i, w in necks.items():
        if i in p.pad_rules:
            p.pad_rules[i].neck = w
    for i, a in series.items():
        r = p.pad_rules.get(i)
        if r is None:
            continue
        r.two_terminal, r.series_a = True, a
        need = PC.current_need(a, margin)
        if a > 0 and need >= r.land_w:
            # the rail's current needs more copper than the land: no neck, and the land is enlarged
            p.hazards.append(PE.land_hazard(r.ref, r.number, r.net, need, r.land_w, need, a))


def validate(info, board_path):
    """Compare this module's rule resolution with KiCad's own engine on the probes
    (single-item constraints: track width, via diameter and drill, own clearance of
    tracks, vias and pads). Returns counts and the first mismatches."""
    rb = rule_board(info, board_path)
    cu = info["copper"]
    out = dict(checked=0, mismatched=0, examples=[])

    def check(what, mine, kicad):
        out["checked"] += 1
        if (mine is None) != (kicad is None) or (mine is not None and abs(mine - kicad) > 1e-6):
            out["mismatched"] += 1
            if len(out["examples"]) < 20:
                out["examples"].append(dict(what=what, ours=mine, kicad=kicad))

    for net, pr in info["probes"].items():
        for l in cu:
            ti = net_item(info, net, "track", l, width=0.1)
            c = R.evaluate(rb, "track_width", ti, None, l)
            kw = (pr["track"].get(l) or {}).get("width") or [None, None, None]
            check(f"track_width min {net} {l}", c.min, kw[0])
            check(f"track_width opt {net} {l}", c.opt if c.opt is not None else c.min, kw[1] if kw[1] is not None else kw[0])
            check(f"track_width max {net} {l}", c.max, kw[2])
            cl = R.evaluate(rb, "clearance", ti, None, l)
            check(f"track clearance {net} {l}", cl.min or 0.0, pr["track"][l]["clearance"])
            vi = net_item(info, net, "via", l)
            cv = R.evaluate(rb, "clearance", vi, None, l)
            check(f"via clearance {net} {l}", cv.min or 0.0, pr["via"]["clearance"][l])
            an = R.evaluate(rb, "annular_width", vi, None, l)
            check(f"via annulus {net} {l}", an.min or 0.0, pr["via"]["annulus"][l])
        vi = net_item(info, net, "via")
        for ctype, key in (("via_diameter", "diameter"), ("hole_size", "drill")):
            c = R.evaluate(rb, ctype, vi, None, None)
            k = pr["via"][key] or [None, None, None]
            check(f"{ctype} min {net}", c.min, k[0])
            check(f"{ctype} max {net}", c.max, k[2])
    for pad in info["pads"]:
        pi = pad_item(info, pad)
        ctype = "hole_clearance" if pad.get("attr") == "npth" else "clearance"
        for l, v in (pad.get("own_clearance") or {}).items():
            c = R.evaluate(rb, ctype, pi, None, l)
            check(f"pad {ctype} {pad['ref']}.{pad['number']} {l}", c.min or 0.0, v)
    out["unsupported"] = sorted(rb.unsupported)
    out["rule_errors"] = rb.errors
    out["dru_rejected"] = rb.dru_rejected
    return out
