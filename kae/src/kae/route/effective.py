# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Effective KiCad constraints per net and layer: the numbers kae.route enforces.

kae.route.constraints.plan resolves KiCad's DRC rules (board setup, net classes, custom
.kicad_dru rules, pad and footprint overrides; kae.route.rules is the port of KiCad's rule
engine) into what the Freerouting bridge writes into the DSN. This module gives the same
numbers to routers that draw copper themselves (kae.route.critical), so that every router
enforces identical rules:

    from kae.route import effective
    r = effective.load("board.kicad_pcb")      # KiCad's pcbnew must be available (pcbnew_io)
    r.track_width("GND", "F.Cu")               # Width(min, opt, max)
    r.via("GND")                               # Via(diameter, drill)
    r.clearance("GND", "VCC", "F.Cu")          # Clearance(track_track, track_via, via_track, via_via)
    r.clearance("GND", None, "F.Cu")           # the largest against any other net
    r.pad_clearance("GND", "F.Cu", "U1", "3")  # ItemClearance(track, via) from that pad
    r.edge_clearance("GND", "F.Cu")            # ItemClearance(track, via) from board edges

Lengths in mm, layers by canonical name (F.Cu, In1.Cu, ..., B.Cu), nets by name.

- track_width: min and max are KiCad's limits for the net on the layer (track_width rules,
  board minimum; max is None when unbounded); opt is the width the bridge routes (the net
  class width clamped into [min, max]). Anything in [min, max] passes KiCad's DRC.
- via: the through via the bridge uses for the net: the net class size raised to the via
  diameter, hole size and annular width minimums, in whole micrometres.
- clearance: from copper of `net` to copper of `other` on the layer, for tracks and vias
  of each: KiCad's clearance, with hole clearance taken through the via's annular ring and
  hole-to-hole through both drills. Values are for tracks of the routed width and the vias
  above; `other` is a net name, a net class name (its nets) or None (every other net).
- pad_clearance: what a track or a via of `net` needs from a pad on the layer: clearance,
  hole clearance through the pad's ring, solder-mask aperture clearance on outer layers.
- edge_clearance: from Edge.Cuts (outline, cut-outs, footprint edges) and Margin.

Same-net copper has no clearance. Hole-to-hole between two vias of one net is not covered
(KiCad checks it; Freerouting cannot hold it): keep vias of a net at least
`same_net_via_pitch(net)` apart, centre to centre.
"""
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import constraints as C
from . import rules as R


@dataclass(frozen=True)
class Width:
    min: float
    opt: float
    max: float | None


@dataclass(frozen=True)
class Via:
    diameter: float
    drill: float


@dataclass(frozen=True)
class Clearance:
    track_track: float
    track_via: float      # track of net, via of other
    via_track: float      # via of net, track of other
    via_via: float


@dataclass(frozen=True)
class ItemClearance:
    track: float
    via: float


def load(board_path, workdir=None):
    """The effective rules of a .kicad_pcb (its .kicad_pro and .kicad_dru beside it)."""
    from kae.board import pcbnew_io
    with tempfile.TemporaryDirectory(prefix="kae-eff-", dir=workdir) as d:
        info = pcbnew_io.export_dsn(board_path, Path(d) / "board.dsn")
    return Rules(info, board_path)


class Rules:
    """Effective constraints of one board (see the module docstring). `info` is
    pcbnew_io.export_dsn's result for `board_path`; `plan` defaults to constraints.plan."""

    def __init__(self, info, board_path, plan=None):
        self.info = info
        self.board_path = Path(board_path)
        self.plan = plan or C.plan(info, board_path)
        self.rb = self.plan.rule_board
        self.layers = list(info["copper"])
        self.nets = sorted(n for n in info["nets"] if n)
        self._pads = {}
        for pd in info["pads"]:
            for key in ((pd.get("comp"), str(pd.get("number"))), (pd.get("ref"), str(pd.get("number")))):
                self._pads.setdefault(key, pd)

    # ---- lookups
    def _layer(self, layer):
        if layer not in self.layers:
            raise KeyError(f"not a copper layer of this board: {layer!r}")
        return layer

    def _net(self, net):
        if net not in self.plan.net_class:
            raise KeyError(f"unknown net {net!r}")
        return net

    def _class(self, net):
        return self.plan.classes[self.plan.net_class[self._net(net)]]

    def _others(self, net, other):
        if other is None:
            return [n for n in self.nets if n != net]
        if other in self.plan.net_class:
            return [other]
        members = [n for n in self.nets if other in self.info["nets"][n]["netclass"].split(",")]
        if not members:
            raise KeyError(f"neither a net nor a net class: {other!r}")
        return [n for n in members if n != net]

    # ---- constraints
    def track_width(self, net, layer):
        """Width(min, opt, max) for tracks of `net` on `layer`."""
        l = self._layer(layer)
        nc = self.info["netclasses"].get(self.info["nets"][self._net(net)]["netclass"], {})
        probe = ((self.info["probes"].get(net) or {}).get("track") or {}).get(l, {}).get("width")
        strict = R.strictest(self.rb, "track_width", C.net_item(self.info, net, "track", l), None, l)
        _, mn, mx = C._width_choice(probe, strict, nc.get("track_width"))
        return Width(min=mn, opt=self._class(net).widths[l], max=mx)

    def via(self, net):
        """Via(diameter, drill) for through vias of `net`."""
        D, d = self._class(net).via
        return Via(D, d)

    def clearance(self, net, other, layer):
        """Clearance between copper of `net` and of `other` on `layer` (see module docstring);
        the largest over all of `other`'s nets when it names a class or is None."""
        l = self._layer(layer)
        rc = self._class(net)
        best = None
        cache = {}
        for o in self._others(net, other):
            oc = self._class(o)
            # a net's diff-pair complement has its own value (the pair's gap), which must not
            # stand for the rest of its class
            key = o if (oc.name == rc.name or C._coupled(net, o)) else oc.name
            if key in cache:
                continue
            r = C.pair_clearances(self.info, self.rb, net, o, l, rc.widths[l], oc.widths[l], rc.via, oc.via)
            v = tuple(C.up(max(x, C.EPS_SHORT)) for x in (r["ww"], r["wv"], r["vw"], r["vv"]))
            cache[key] = v
            best = v if best is None else tuple(max(a, b) for a, b in zip(best, v))
        if best is None:
            return Clearance(0.0, 0.0, 0.0, 0.0)
        return Clearance(*best)

    def pad_clearance(self, net, layer, ref, number):
        """ItemClearance(track, via) of `net` from pad `number` of footprint `ref` on `layer`
        (0 when the pad is on the same net or has no copper there)."""
        l = self._layer(layer)
        pad = self._pads.get((ref, str(number)))
        if pad is None:
            raise KeyError(f"no pad {ref}.{number}")
        if pad.get("net") and pad.get("net") == net or l not in (pad.get("layers") or []):
            return ItemClearance(0.0, 0.0)
        rc = self._class(net)
        cls = self.plan.pin_class.get((pad.get("comp"), pad.get("pin")))
        vec = self.plan.obstacle_classes[cls].values if cls in self.plan.obstacle_classes else \
            C._pad_requirements(self.info, self.rb, self.plan, pad, {})
        tw, vw = vec.get((rc.name, l), (0.0, 0.0))
        return ItemClearance(tw, vw)

    def edge_clearance(self, net, layer):
        """ItemClearance(track, via) of `net` from board edges on `layer`."""
        l = self._layer(layer)
        rc = self._class(net)
        oc = self.plan.obstacle_classes.get("kae_edge")
        tw, vw = oc.values.get((rc.name, l), (0.0, 0.0)) if oc else (0.0, 0.0)
        return ItemClearance(tw, vw)

    def same_net_via_pitch(self, net):
        """Smallest centre distance between two vias of `net` (KiCad's hole-to-hole)."""
        vi = C.net_item(self.info, self._net(net), "via")
        return C.up(C._strict_min(self.rb, "hole_to_hole", vi, dict(vi), None) + self._class(net).via[1])

    def summary(self, net, layer):
        """Everything above for (net, layer) as a JSON-able dict."""
        from dataclasses import asdict
        return dict(net=net, layer=layer, track_width=asdict(self.track_width(net, layer)),
                    via=asdict(self.via(net)), clearance_any=asdict(self.clearance(net, None, layer)),
                    edge_clearance=asdict(self.edge_clearance(net, layer)),
                    same_net_via_pitch=self.same_net_via_pitch(net))
