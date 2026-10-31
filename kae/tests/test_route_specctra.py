# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.specctra: DSN/SES trees and the session fix-up (no KiCad needed)."""
from types import SimpleNamespace

from kae.route import specctra as S
from kae.route import translate
from kae.route.constraints import RoutingClass, via_name

DSN = '''(pcb "/tmp/x.dsn"
  (parser
    (string_quote ")
    (space_in_quoted_tokens on)
    (host_cad "KiCad's Pcbnew")
  )
  (resolution um 10)
  (unit um)
  (structure
    (layer F.Cu (type signal) (property (index 0)))
    (via "Via[0-1]_600:300_um")
    (rule (width 250) (clearance 200))
  )
  (network
    (net "VCC 3.3V" (pins U1-1 C1-2))
    (net ADD|SUB (pins U1-2 R1-1))
  )
)
'''


def test_round_trip_keeps_tokens():
    t = S.parse(DSN)
    again = S.parse(S.dumps(t))
    assert again == t
    parser = S.find(t, "parser")
    assert S.find(parser, "string_quote")[1] == S._DQ
    assert '(string_quote ")' in S.dumps(t)
    net = S.findall(S.find(t, "network"), "net")[0]
    assert net[1] == "VCC 3.3V" and isinstance(net[1], S.Q)
    assert S.unit_scale(t) == 1000.0


def test_atoms_are_quoted_when_needed():
    assert S.atom("abc") == "abc"
    assert S.atom(S.Q("abc")) == '"abc"'
    assert S.atom("a b") == '"a b"'
    assert S.atom("") == '""'
    assert S.fmt(250.0) == "250" and S.fmt(0.12345678) == "0.1235" and S.fmt(-3.5) == "-3.5"


SES = '''(session board
  (base_design board)
  (placement
    (resolution um 10)
    (component R (place R1 1000 -2000 front 0))
  )
  (routes
    (resolution um 10)
    (library_out
      (padstack "Via[0-1]_700:300_um"
        (shape (circle F.Cu 7000 0 0))
        (shape (circle B.Cu 7000 0 0))
        (attach off)
      )
    )
    (network_out
      (net ADD|SUB
        (wire (path F.Cu 2000 0 0 1000 0))
        (via "Via[0-1]_700:300_um" 1000 0)
      )
      (net "VCC 3.3V" (wire (path F.Cu 2000 0 0 0 1000)))
    )
  )
)
'''


def test_fix_session_strips_placement_quotes_nets_restores_vias():
    rc = RoutingClass("kae_Default", ["ADD|SUB"], "Default", {"F.Cu": 0.2, "B.Cu": 0.2}, (0.7, 0.3))
    assert via_name(rc, 2) == "Via[0-1]_700:300_um"
    plan = SimpleNamespace(classes={"kae_Default": rc}, copper=["F.Cu", "B.Cu"])
    t = S.parse(SES)
    out = translate.fix_session(t, plan)
    assert out == dict(placement_stripped=True, nets_quoted=1, vias_restored=2)
    text = S.dumps(t)
    assert "(placement" not in text
    assert '(net "ADD|SUB"' in text
    assert "(circle F.Cu 7000 0 0)" in text  # 0.7 mm in SES units (0.1 um)


SNAP_DSN = '''(pcb "/tmp/x.dsn"
  (resolution um 10)
  (unit um)
  (structure (layer F.Cu (type signal)) (layer B.Cu (type signal)))
  (placement
    (component C0805 (place C2 136250 -107800 front 0) (place C9 136250 -110000 back 90))
  )
  (library
    (image C0805
      (pin Rect 1 -1037.5 0)
      (pin Rect 2 1037.5 0)
    )
  )
  (network
    (net A (pins C2-2 C9-1))
    (net B (pins C2-1))
  )
  (wiring
    (wire (path F.Cu 701  137288 -107800  139000 -107800)(net A)(type fix))
    (wire (path F.Cu 200  139000 -107800  139000.4 -108500.3)(net A)(type fix))
    (wire (path B.Cu 200  139000 -108500  136250 -108963)(net A)(type fix))
    (wire (path F.Cu 200  135212 -107800  135000 -106000)(net B)(type fix))
    (via "Via[0-1]_600:300_um"  139000 -108500 (net A)(type fix))
  )
)
'''


def test_wiring_snaps_onto_pin_centres_and_corners():
    """KiCad writes DSN coordinates with %.6g: a locked track ending on C2's pad 2 centre
    (137.2875 mm) is written 137288 um; Freerouting joins it only at the pin centre
    placement + offset = 137287.5. snap_wiring moves such points onto the centre (back-side
    images mirrored before the rotation), near-coincident corners onto each other, and
    leaves everything else alone."""
    t = S.parse(SNAP_DSN)
    pads = [dict(net="A", pos=[137.2875, 107.8]), dict(net="A", pos=[136.25, 108.9625]),
            dict(net="B", pos=[135.2125, 107.8])]
    summary, snaps = translate.snap_wiring(t, pads)
    w = [S.find(x, "path") for x in S.findall(S.find(t, "wiring"), "wire")]
    assert w[0][3:5] == ["137287.5", "-107800"]               # onto C2-2
    assert w[0][5:7] == ["139000", "-107800"]                 # a free corner stays
    assert w[1][5:7] == ["139000", "-108500"]                 # within 1.5 um of the via: onto it
    assert w[2][5:7] == ["136250", "-108962.5"]               # C9 (back: mirrored, then 90 deg) pin 1
    assert w[3][3:5] == ["135212.5", "-107800"]               # net B onto C2-1
    assert summary["to_pins"] == 3 and summary["to_corners"] == 1
    assert {k: len(v) for k, v in snaps.items()} == {"A": 2, "B": 1}


def test_session_points_get_kicads_coordinates_back():
    """A session point where the snap moved a DSN point (a kept pre-route, a new wire ending
    on that pin centre) gets the KiCad pad position back; other points are untouched."""
    rc = RoutingClass("kae_Default", ["A"], "Default", {"F.Cu": 0.2, "B.Cu": 0.2}, (0.7, 0.3))
    plan = SimpleNamespace(classes={"kae_Default": rc}, copper=["F.Cu", "B.Cu"],
                           wire_snaps={"A": [(137.2875, -107.8, 137.287499, -107.8)]})
    ses = SES.replace('(net "VCC 3.3V" (wire (path F.Cu 2000 0 0 0 1000)))',
                      '(net A (wire (path F.Cu 2000 1372875 -1078000 1380000 -1078000)))')
    t = S.parse(ses)
    out = translate.fix_session(t, plan)
    assert out["points_restored"] == 1
    path = [p for n in S.findall(S.find(S.find(t, "routes"), "network_out"), "net") if str(n[1]) == "A"
            for w in S.findall(n, "wire") for p in S.findall(w, "path")][0]
    assert path[3:] == ["1372874.99", "-1078000", "1380000", "-1078000"]


def test_inner_planes_become_power_layers():
    """An inner layer that one net's zones cover (>= 30 % of the board) is a plane: with the
    plan's plane_policy 'power' it goes to Freerouting as a power layer (no traces on it);
    outer layers and a sparsely poured inner layer stay signal layers; 'signal' keeps
    KiCad's types. bridge.plane_policy falls back to 'signal' only for a free repair round
    with open connections under 'keep'."""
    from kae.route.bridge import plane_policy
    sq = lambda x0, y0, x1, y1: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]]          # noqa: E731
    info = dict(copper=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], outline=[sq(0, 0, 100, 50)],
                zones=[dict(net="GND", layers=["In1.Cu"], rings=[sq(1, 1, 99, 49)]),
                       dict(net="+3V3", layers=["In2.Cu"], rings=[sq(1, 1, 20, 20)]),
                       dict(net="GND", layers=["B.Cu"], rings=[sq(1, 1, 99, 49)]),
                       dict(net="", layers=["In2.Cu"], rings=[sq(0, 0, 100, 50)], rule_area=True)])
    assert translate.plane_layers(info) == {"In1.Cu": "GND"}
    tree = S.parse("(pcb x (structure (layer F.Cu (type signal)) (layer In1.Cu (type signal))"
                   " (layer In2.Cu (type signal)) (layer B.Cu (type signal))))")
    layers = S.findall(S.find(tree, "structure"), "layer")
    assert translate.mark_plane_layers(layers, info["copper"], info) == ["In1.Cu"]
    assert [str(S.find(l, "type")[1]) for l in layers] == ["signal", "power", "signal", "signal"]
    assert plane_policy({}) == "cost" and plane_policy(dict(planes="allow")) == "signal"
    assert plane_policy(dict(planes="keep")) == "power"
    assert plane_policy(dict(planes="keep"), free_round_with_open=True) == "signal"
    assert plane_policy(dict(planes="strict"), free_round_with_open=True) == "power"
    # soft: a rules file prices the plane layer at PLANE_COST, the others at Freerouting's defaults
    text = translate.layer_rules(["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], [False, True, False, False], [True] * 4, 4.0)
    assert "(layer_rule In1.Cu (preferred_direction_trace_costs 4) (against_preferred_direction_trace_costs 8))" in text
    assert "(layer_rule F.Cu (preferred_direction_trace_costs 1.8)" in text
    assert "(layer_rule In2.Cu (preferred_direction_trace_costs 1) " in text
    assert translate.layer_rules(["F.Cu", "B.Cu"], [False, False], [True, True]) is None


def test_strict_share_from_the_board(tmp_path):
    """The board's KAE_PLANE_STRICT_SHARE text variable wins over opts, as for every kae limit."""
    import json
    from kae.route.bridge import strict_share
    pcb = tmp_path / "b.kicad_pcb"
    pcb.with_suffix(".kicad_pro").write_text(json.dumps({"text_variables": {"KAE_PLANE_STRICT_SHARE": "0"}}))
    assert strict_share(dict(plane_strict_share=0.8), 1, pcb) is None
    pcb.with_suffix(".kicad_pro").write_text(json.dumps({"text_variables": {"KAE_PLANE_STRICT_SHARE": "0.85"}}))
    assert strict_share(dict(plane_strict_share="odd"), 0, pcb) == 0.85
    pcb.with_suffix(".kicad_pro").write_text(json.dumps({"text_variables": {"KAE_IGNORED_CLEARANCE_FLOOR": "x"}}))
    from kae.route import constraints
    assert constraints.setting("ignored_clearance_floor", pcb, dict(ignored_clearance_floor=0.2)) == 0.2


def test_strict_planes_alternate_with_the_seed():
    """plane_strict_share "odd" (the default): odd seeds make the inner layers that one net's
    fill covers >= 0.8 power layers under planes "cost", even seeds leave them costed; an
    explicit share applies to every seed and 0 to none."""
    from kae.route.bridge import DEFAULT_OPTS, strict_share
    assert [strict_share(DEFAULT_OPTS, s) for s in (0, 1, 2, 1001)] == [None, 0.8, None, 0.8]
    assert strict_share(dict(plane_strict_share=0.9), 0) == 0.9
    assert strict_share(dict(plane_strict_share=0), 1) is None
    assert strict_share({}, 3) == 0.8
    sq = lambda x0, y0, x1, y1: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]]          # noqa: E731
    info = dict(copper=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], outline=[sq(0, 0, 100, 50)], zones=[])
    fills = [dict(net="GND", layers={"In1.Cu": [sq(0, 0, 100, 45)], "F.Cu": [sq(0, 0, 100, 50)]}),
             dict(net="+5V", layers={"In2.Cu": [sq(0, 0, 50, 50)]}),
             dict(net="+3V3", layers={"In2.Cu": [sq(50, 0, 100, 50)]})]
    shares = translate.fill_planes(info, fills)
    assert shares["In1.Cu"] == ("GND", 0.9) and shares["In2.Cu"][1] == 0.5
    tree = S.parse("(pcb x (structure (layer F.Cu (type signal)) (layer In1.Cu (type signal))"
                   " (layer In2.Cu (type signal)) (layer B.Cu (type signal))))")
    layers = S.findall(S.find(tree, "structure"), "layer")
    assert translate.mark_plane_layers(layers, info["copper"], info, []) == []
    assert translate.mark_plane_layers(layers, info["copper"], info, ["In1.Cu"]) == ["In1.Cu"]
    assert [str(S.find(l, "type")[1]) for l in layers] == ["signal", "power", "signal", "signal"]


def test_plane_costs_go_beside_the_dsn(tmp_path):
    from types import SimpleNamespace
    dsn = tmp_path / "board.dsn"
    dsn.write_text("(pcb x)")
    translate.write_rules(SimpleNamespace(layer_rules="(rules PCB board)\n"), dsn)
    assert (tmp_path / "board.rules").read_text() == "(rules PCB board)\n"
    translate.write_rules(SimpleNamespace(layer_rules=None), dsn)
    assert not (tmp_path / "board.rules").exists()


RR_DSN = '''(pcb "/tmp/x.dsn"
  (resolution um 10)
  (unit um)
  (structure (layer F.Cu (type signal)) (layer B.Cu (type signal)))
  (placement
    (component C0805 (place C2 94000 -115050 back 90) (place C3 120000 -100000 front 30))
  )
  (library
    (image C0805
      (pin RR 1 -950 0)
      (pin RR (rotate 90) 2 950 0)
      (pin Round 3 0 1500)
    )
    (padstack RR
      (shape (polygon F.Cu 0  -500.951 475  -481.848 571.035  -427.449 652.449  -346.035 706.848
            -249.999 725.95  250 725.951  346.035 706.848  427.449 652.449
            481.848 571.035  500.95 474.999  500.951 -475  481.848 -571.035
            427.449 -652.449  346.035 -706.848  249.999 -725.95  -250 -725.951
            -346.035 -706.848  -427.449 -652.449  -481.848 -571.035  -500.95 -474.999
            -500.951 475))
      (attach off))
    (padstack Round (shape (circle F.Cu 600)) (attach off))
  )
  (network (net A (pins C2-1 C3-1)) (net B (pins C2-2 C3-2)))
)
'''


def test_rounded_pin_polygons_are_circumscribed():
    """KiCad's DSN writes a roundrect pad as a polygon whose corner chords lie up to 3.9 um
    inside the true outline (oasis C2: 1.0 x 1.45 mm, r 0.25 mm), so Freerouting kept its
    clearance from a smaller pad than KiCad checks. circumscribe_pins replaces it by a
    polygon that contains the pad (back side, placement and pin rotations included) and
    reaches at most max_error beyond it; exact shapes (circles) stay."""
    import math
    from shapely import affinity
    from shapely.geometry import Point, box
    t = S.parse(RR_DSN)

    def outline(cx, cy, rot, w=1.0, h=1.45, r=0.25):             # the true pad, board mm (y down)
        g = box(-w / 2 + r, -h / 2 + r, w / 2 - r, h / 2 - r).buffer(r, quad_segs=256)
        return affinity.translate(affinity.rotate(g, rot, origin=(0, 0)), cx, cy)

    def pad(comp, pin, g, layer):
        out = g.buffer(0.005 / math.cos(math.pi / 64), quad_segs=16, join_style="mitre")   # ERROR_OUTSIDE-like
        return dict(comp=comp, pin=pin, net="A", layers=[layer], poly=[[list(out.exterior.coords)]])

    # C2 back, 90 deg: pin 1 at (94.0, 114.1), pin 2 (pin rotated 90 more) at (94.0, 116.0); C3 front, 30 deg
    truth = {("C2", "1"): (outline(94.0, 114.1, -90), "B.Cu"), ("C2", "2"): (outline(94.0, 116.0, 0), "B.Cu")}
    a = math.radians(30)
    for pin, (px, py), rot in (("1", (-0.95, 0.0), 0), ("2", (0.95, 0.0), 90)):
        x, y = 120.0 + px * math.cos(a) - py * math.sin(a), 100.0 - (px * math.sin(a) + py * math.cos(a))
        truth[("C3", pin)] = (outline(x, y, -(30 + rot)), "F.Cu")
    info = dict(copper=["F.Cu", "B.Cu"], pads=[pad(c, p, g, l) for (c, p), (g, l) in truth.items()])
    before = translate.circumscribe_pins(S.parse(RR_DSN), info)
    assert before["pin_shapes_circumscribed"] == 1 and before["pin_deficit_um_max"] > 3
    pins = {(r, n): m for r, n, ps, side, m in translate.dsn_pins(t) if ps == "RR"}

    def pin_shape(tree, key):
        ps = next(p for p in S.findall(S.find(tree, "library"), "padstack") if p[1] == "RR")
        v = [float(x) for x in S.find(ps, "shape")[1][3:]]
        from shapely.geometry import Polygon
        return translate._apply_affine(Polygon(list(zip(v[0::2], v[1::2]))), pins[key])
    for key, (g, _) in truth.items():
        assert not pin_shape(t, key).contains(g)                  # KiCad's chords cut the corners
    translate.circumscribe_pins(t, info)
    for key, (g, _) in truth.items():
        s = pin_shape(t, key)
        assert s.contains(g)
        assert s.hausdorff_distance(g) <= 0.005 + 0.001           # max_error plus the 0.2 um growth
    assert translate.circumscribe_pins(t, info)["pin_shapes_circumscribed"] == 0
    rnd = next(p for p in S.findall(S.find(t, "library"), "padstack") if p[1] == "Round")
    assert S.find(rnd, "shape")[1] == ["circle", "F.Cu", "600"]
    c = pin_shape(t, ("C2", "1")).centroid                          # the transform matches dsn_pin_centres
    assert Point(c.x, c.y).distance(Point(94.0, 114.1)) < 1e-4
