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
