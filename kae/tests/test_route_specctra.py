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
