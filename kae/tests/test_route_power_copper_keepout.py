# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Power copper written as zones (vector mode) stays out of rule areas that forbid copper pours.

hotloop-sw, danielmcmillan irrigation: a kae-pc:GND zone landed in a board rule area with (copperpour
not_allowed); the scorer marks such an output invalid. Rule areas that forbid only pours never reach the router's
keep-outs (the DSN holds wire and via keep-outs), so the vector growth clips its zones to them itself."""
import json

from shapely.geometry import box

import critical_fixtures as F
from kae.route import power_copper as pc

SEG = '\t(segment\n\t\t(start {} {})\n\t\t(end {} {})\n\t\t(width 0.25)\n\t\t(layer "F.Cu")\n\t\t(net "{}")\n\t\t(uuid "{}")\n\t)\n'
KEEPOUT = '''\t(zone
\t\t(layer "F.Cu")
\t\t(uuid "0000000b-0000-0000-0000-00000000bbbb")
\t\t(name "no_pour")
\t\t(hatch edge 0.5)
\t\t(connect_pads (clearance 0))
\t\t(min_thickness 0.25)
\t\t(keepout (tracks allowed) (vias allowed) (pads allowed) (copperpour not_allowed) (footprints allowed))
\t\t(fill (thermal_gap 0.5) (thermal_bridge_width 0.5))
\t\t(polygon (pts (xy {} {}) (xy {} {}) (xy {} {}) (xy {} {})))
\t)
'''
AREA = (106.0, 109.0, 112.0, 113.0)     # over the VIN track's middle, room beside it on both sides


def _vector(tmp_path, keepout):
    from kae.board.kicad_file import load
    p = F.write_board(tmp_path)
    s = p.read_text()
    i = s.rindex("\t(embedded_fonts no)")
    add = SEG.format(104.0, 111.0, 114, 111, "VIN", "0000000a-0000-0000-0000-00000000aaaa")
    add += SEG.format(114, 111, 119.69, 110.95, "VIN", "0000000a-0000-0000-0000-00000000aaab")
    if keepout:
        x0, y0, x1, y1 = AREA
        add += KEEPOUT.format(x0, y0, x1, y0, x1, y1, x0, y1)
    p.write_text(s[:i] + add + s[i:])
    b = load(p)
    obj = pc.PowerCopper(p, dict(vias=False, stitch=False, mode="vector", vector_out="zones", max_width=3.0),
                         info=F.synth_info(b), fills={}, log=lambda *a: None)
    obj.grow_vector(nets={"VIN"})
    return obj, b


def test_vector_zones_stay_out_of_rule_areas_that_forbid_pours(tmp_path):
    area = box(*AREA)
    free, _ = _vector(tmp_path / "free", keepout=False)
    assert any(poly.intersection(area).area > 0.05 for net, layer, poly, _ in free.zones if net == "VIN"), \
        "the control must grow VIN copper into the area, or the test proves nothing"
    held, b = _vector(tmp_path / "held", keepout=True)
    assert [k.copperpour for k in b.keepouts] == [True]
    assert held.zones, "VIN still gets copper outside the rule area"
    for net, layer, poly, _ in held.zones:
        assert poly.intersection(area).area < 1e-6, (net, layer, poly.intersection(area).area)
