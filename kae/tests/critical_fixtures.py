# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A synthetic test board for the critical router (our own design, no third-party copper).

40 x 30 mm, two layers, a ground pour on B.Cu:

- J1 (2-pin connector) feeds VIN; D1 (SMBJ24A TVS) clamps it next to the connector;
- U1 (AP63203, integrated synchronous buck, TSOT-23-6) with input cap C1 and inductor L1
  makes +3V3; C2 is the output cap;
- U2 (ATtiny85, SOIC-8) runs from +3V3 with decap C3; crystal Y1 on XTAL1/XTAL2 with load
  caps C4, C5.

`write_board(dir, back=())` writes board.kicad_pcb and board.kicad_pro (KiCad 10 syntax),
with the parts named in `back` on the bottom side;
`synth_info(board)` builds, without KiCad, the dict pcbnew_io.export_dsn returns, enough
for kae.route.constraints.plan and the critical router's Space.
"""
import json
import math
import shutil
import uuid
from pathlib import Path

DATA = Path(__file__).parent / "data" / "board"
ORIGIN = (100.0, 100.0)
SIZE = (40.0, 30.0)

# (ref, value, lib_id, x, y, rot, [(number, net, lx, ly, w, h, kind, drill, pinfunction, pintype)], courtyard half w, h)
PARTS = [
    ("J1", "Conn_01x02", "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical", 104.0, 112.0, 0.0,
     [("1", "VIN", 0.0, -1.0, 1.4, 1.4, "thru_hole", 0.8, "Pin_1", "passive"),
      ("2", "GND", 0.0, 1.0, 1.4, 1.4, "thru_hole", 0.8, "Pin_2", "passive")], (1.6, 2.4)),
    ("D1", "SMBJ24A", "Diode_SMD:D_SMB", 108.0, 108.0, 0.0,
     [("1", "VIN", -2.15, 0.0, 2.5, 2.3, "smd", 0.0, "K", "passive"),
      ("2", "GND", 2.15, 0.0, 2.5, 2.3, "smd", 0.0, "A", "passive")], (3.7, 1.6)),
    ("C1", "10uF", "Capacitor_SMD:C_0805_2012Metric", 117.0, 110.0, 90.0,
     [("1", "VIN", -0.95, 0.0, 1.0, 1.45, "smd", 0.0, "", "passive"),
      ("2", "GND", 0.95, 0.0, 1.0, 1.45, "smd", 0.0, "", "passive")], (1.7, 1.0)),
    ("U1", "AP63203WU", "Package_TO_SOT_SMD:TSOT-23-6", 121.0, 110.0, 0.0,
     [("1", "+3V3", -1.31, -0.95, 1.06, 0.65, "smd", 0.0, "FB", "input"),
      ("2", "VIN", -1.31, 0.0, 1.06, 0.65, "smd", 0.0, "EN", "input"),
      ("3", "VIN", -1.31, 0.95, 1.06, 0.65, "smd", 0.0, "VIN", "power_in"),
      ("4", "GND", 1.31, 0.95, 1.06, 0.65, "smd", 0.0, "GND", "power_in"),
      ("5", "Net-(U1-SW)", 1.31, 0.0, 1.06, 0.65, "smd", 0.0, "SW", "output"),
      ("6", "Net-(U1-BST)", 1.31, -0.95, 1.06, 0.65, "smd", 0.0, "BST", "passive")], (2.1, 1.8)),
    ("L1", "4.7uH 3A", "Inductor_SMD:L_1210_3225Metric", 127.5, 110.0, 0.0,
     [("1", "Net-(U1-SW)", -1.5, 0.0, 1.2, 2.7, "smd", 0.0, "", "passive"),
      ("2", "+3V3", 1.5, 0.0, 1.2, 2.7, "smd", 0.0, "", "passive")], (2.4, 1.8)),
    ("C2", "22uF", "Capacitor_SMD:C_0805_2012Metric", 132.0, 110.0, 90.0,
     [("1", "+3V3", -0.95, 0.0, 1.0, 1.45, "smd", 0.0, "", "passive"),
      ("2", "GND", 0.95, 0.0, 1.0, 1.45, "smd", 0.0, "", "passive")], (1.7, 1.0)),
    ("U2", "ATtiny85-20S", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 124.0, 122.0, 0.0,
     [("1", "", -2.475, -1.905, 1.95, 0.6, "smd", 0.0, "PB5", "bidirectional"),
      ("2", "Net-(U2-XTAL1)", -2.475, -0.635, 1.95, 0.6, "smd", 0.0, "XTAL1/PB3", "bidirectional"),
      ("3", "Net-(U2-XTAL2)", -2.475, 0.635, 1.95, 0.6, "smd", 0.0, "XTAL2/PB4", "bidirectional"),
      ("4", "GND", -2.475, 1.905, 1.95, 0.6, "smd", 0.0, "GND", "power_in"),
      ("5", "", 2.475, 1.905, 1.95, 0.6, "smd", 0.0, "PB0", "bidirectional"),
      ("6", "", 2.475, 0.635, 1.95, 0.6, "smd", 0.0, "PB1", "bidirectional"),
      ("7", "", 2.475, -0.635, 1.95, 0.6, "smd", 0.0, "PB2", "bidirectional"),
      ("8", "+3V3", 2.475, -1.905, 1.95, 0.6, "smd", 0.0, "VCC", "power_in")], (3.7, 2.7)),
    ("C3", "100nF", "Capacitor_SMD:C_0402_1005Metric", 129.0, 119.0, 0.0,
     [("1", "+3V3", -0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive"),
      ("2", "GND", 0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive")], (0.95, 0.5)),
    ("Y1", "8MHz", "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", 116.0, 122.0, 270.0,
     [("1", "Net-(U2-XTAL1)", -1.25, 0.0, 1.0, 1.8, "smd", 0.0, "1", "passive"),
      ("2", "Net-(U2-XTAL2)", 1.25, 0.0, 1.0, 1.8, "smd", 0.0, "2", "passive")], (2.0, 1.1)),
    ("C4", "22pF", "Capacitor_SMD:C_0402_1005Metric", 113.0, 120.5, 0.0,
     [("1", "Net-(U2-XTAL1)", -0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive"),
      ("2", "GND", 0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive")], (0.95, 0.5)),
    ("C5", "22pF", "Capacitor_SMD:C_0402_1005Metric", 113.0, 123.5, 0.0,
     [("1", "Net-(U2-XTAL2)", -0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive"),
      ("2", "GND", 0.48, 0.0, 0.56, 0.62, "smd", 0.0, "", "passive")], (0.95, 0.5)),
]

SETTINGS = dict(min_clearance=0.15, min_track=0.15, min_conn=0.0, min_via=0.6, min_annular=0.1, min_drill=0.3,
                min_uvia=0.2, min_uvia_drill=0.1, hole_clearance=0.25, hole_to_hole=0.25, edge_clearance=0.3,
                mask_expansion=0.0, mask_min_web=0.0, mask_to_copper=0.0, max_error=0.005, zone_clearance=0.3,
                zone_min_thickness=0.25, thermal_spoke=0.5, min_resolved_spokes=2, allow_mask_bridges_in_fps=False,
                tent_vias_front=True, tent_vias_back=True)
NETCLASS = dict(constituents=["Default"], clearance=0.2, track_width=0.25, via_diameter=0.6, via_drill=0.3,
                uvia_diameter=0.3, uvia_drill=0.1, dp_width=0.2, dp_gap=0.25)


def _u(k):
    return str(uuid.UUID(int=0xC0FFEE << 64 | k))


def _f(v):
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def board_text(back=(), twin=False):
    """The board's text; `twin` gives J1 pad 1 an SMD twin on F.Cu (a castellated pad: one
    number, a through-hole pad plus surface copper on one side only)."""
    k = [0]

    def u():
        k[0] += 1
        return _u(k[0])
    head = (DATA / "fixture.kicad_pcb").read_text().split("\t(setup")[0]
    # two copper layers only
    head = head.replace('\t\t(4 "In1.Cu" signal "GND")\n', "").replace('\t\t(6 "In2.Cu" power)\n', "")
    out = [head, "\t(setup\n\t\t(pad_to_mask_clearance 0)\n\t\t(allow_soldermask_bridges_in_footprints no)\n\t)\n"]
    for ref, val, lib, x, y, rot, pads, (cw, ch) in PARTS:
        at = f"(at {_f(x)} {_f(y)}{(' ' + _f(rot)) if rot else ''})"
        sd = "B" if ref in back else "F"
        if twin and ref == "J1":
            pads = pads + [("1", "VIN", 1.4, -1.0, 1.6, 0.9, "smd", 0.0, "Pin_1", "passive")]
        s = [f'\t(footprint "{lib}"\n\t\t(layer "{sd}.Cu")\n\t\t(uuid "{u()}")\n\t\t{at}\n'
             f'\t\t(property "Reference" "{ref}"\n\t\t\t(at 0 -3 0)\n\t\t\t(layer "F.Fab")\n\t\t\t(hide yes)\n'
             f'\t\t\t(uuid "{u()}")\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1 1)\n\t\t\t\t\t(thickness 0.15)\n'
             f'\t\t\t\t)\n\t\t\t)\n\t\t)\n'
             f'\t\t(property "Value" "{val}"\n\t\t\t(at 0 3 0)\n\t\t\t(layer "F.Fab")\n\t\t\t(hide yes)\n'
             f'\t\t\t(uuid "{u()}")\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1 1)\n\t\t\t\t\t(thickness 0.15)\n'
             f'\t\t\t\t)\n\t\t\t)\n\t\t)\n'
             f'\t\t(attr {"through_hole" if any(p[6] == "thru_hole" for p in pads) else "smd"})\n'
             f'\t\t(fp_rect\n\t\t\t(start {_f(-cw)} {_f(-ch)})\n\t\t\t(end {_f(cw)} {_f(ch)})\n'
             f'\t\t\t(stroke\n\t\t\t\t(width 0.05)\n\t\t\t\t(type solid)\n\t\t\t)\n\t\t\t(fill no)\n'
             f'\t\t\t(layer "{sd}.CrtYd")\n\t\t\t(uuid "{u()}")\n\t\t)\n']
        for num, net, lx, ly, w, h, kind, drill, fn, pt in pads:
            pat = f"(at {_f(lx)} {_f(ly)}{(' ' + _f(rot)) if rot else ''})"
            if kind == "thru_hole":
                body = (f'\t\t(pad "{num}" thru_hole {"rect" if num == "1" else "circle"}\n\t\t\t{pat}\n'
                        f'\t\t\t(size {_f(w)} {_f(h)})\n\t\t\t(drill {_f(drill)})\n\t\t\t(layers "*.Cu" "*.Mask")\n'
                        f'\t\t\t(remove_unused_layers no)\n')
            else:
                body = (f'\t\t(pad "{num}" smd rect\n\t\t\t{pat}\n\t\t\t(size {_f(w)} {_f(h)})\n'
                        f'\t\t\t(layers "{sd}.Cu" "{sd}.Mask" "{sd}.Paste")\n')
            if net:
                body += f'\t\t\t(net "{net}")\n'
            if fn:
                body += f'\t\t\t(pinfunction "{fn}")\n'
            body += f'\t\t\t(pintype "{pt}")\n\t\t\t(uuid "{u()}")\n\t\t)\n'
            s.append(body)
        s.append("\t\t(embedded_fonts no)\n\t)\n")
        out.append("".join(s))
    x0, y0 = ORIGIN
    x1, y1 = x0 + SIZE[0], y0 + SIZE[1]
    for (a, b) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        out.append(f'\t(gr_line\n\t\t(start {_f(a[0])} {_f(a[1])})\n\t\t(end {_f(b[0])} {_f(b[1])})\n'
                   f'\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type solid)\n\t\t)\n\t\t(layer "Edge.Cuts")\n'
                   f'\t\t(uuid "{u()}")\n\t)\n')
    out.append(f'\t(zone\n\t\t(net "GND")\n\t\t(layer "B.Cu")\n\t\t(uuid "{u()}")\n\t\t(name "gnd_pour")\n'
               f'\t\t(hatch edge 0.5)\n\t\t(connect_pads\n\t\t\t(clearance 0.3)\n\t\t)\n\t\t(min_thickness 0.25)\n'
               f'\t\t(fill\n\t\t\t(thermal_gap 0.5)\n\t\t\t(thermal_bridge_width 0.5)\n\t\t)\n'
               f'\t\t(polygon\n\t\t\t(pts\n\t\t\t\t(xy {_f(x0 + 0.5)} {_f(y0 + 0.5)}) (xy {_f(x1 - 0.5)} {_f(y0 + 0.5)}) '
               f'(xy {_f(x1 - 0.5)} {_f(y1 - 0.5)}) (xy {_f(x0 + 0.5)} {_f(y1 - 0.5)})\n\t\t\t)\n\t\t)\n\t)\n')
    out.append("\t(embedded_fonts no)\n)\n")
    return "".join(out)


def write_board(d, back=(), twin=False):
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "board.kicad_pcb"
    p.write_text(board_text(back, twin))
    pro = json.loads((DATA / "fixture.kicad_pro").read_text())
    pro["meta"]["filename"] = "board.kicad_pro"
    (d / "board.kicad_pro").write_text(json.dumps(pro, indent=2))
    return p


# ----------------------------------------------------------------------------- KiCad-free export info
def synth_info(board):
    """What pcbnew_io.export_dsn returns for `board` (kae.board model), built without KiCad:
    rectangular and circular pads, the outline, zones, the Default net class."""
    from shapely.geometry import Point, Polygon

    from kae.board import transform
    from kae.place.legalize import pad_shape
    cu = list(board.stackup.copper)
    pads = []
    for fi, f in enumerate(board.footprints):
        for p in f.pads:
            g = transform.place_geom(pad_shape(p), f.x, f.y, f.rot, f.side)
            if not isinstance(g, Polygon):
                g = g.convex_hull
            ring = [list(c) for c in g.exterior.coords]
            x, y = transform.pad_xy(f, p)
            layers = [l for l in cu if l in p.layers]
            hole = None
            if p.drill:
                hole = dict(a=[x, y], b=[x, y], width=p.drill, plated=p.kind == "thru_hole")
            pads.append(dict(ref=f.ref, comp=f.ref, fp_index=fi, lib=f.lib_id, fp_clearance=None, allow_bridges=False,
                             net_tie=False, number=p.number, pin=p.number, net=p.net, uuid=p.uuid,
                             attr="pth" if p.kind == "thru_hole" else "smd", pos=[x, y], layers=layers, hole=hole,
                             local_clearance=None, override=None, own_clearance={l: NETCLASS["clearance"] for l in layers},
                             mask={"F": 0.0} if "F.Cu" in layers else {}, zone_connection="inherited", thermal_gap=None,
                             spoke_width=None, spoke_angle=90.0, round_keepout=False, fab="None",
                             drilled=bool(p.drill), poly=[[ring]]))
    nets = {n: dict(code=i + 1, netclass="Default") for i, n in enumerate(sorted(board.nets))}
    outline = [[[list(c) for c in pg.exterior.coords]] for pg in board.outline]
    zones = []
    for z in board.zones:
        zones.append(dict(owner="", name=z.name, layers=list(z.layers), rings=[[[list(c) for c in z.outline.exterior.coords]]],
                          rule_area=False, net=z.net, priority=z.priority, clearance=z.clearance or 0.3,
                          min_thickness=z.min_thickness or 0.25, pad_connection="thermal", thermal_gap=0.5,
                          spoke_width=0.5, teardrop=False))
    return dict(ok=True, path=board.path, dsn="", kicad_version="synthetic", copper=cu,
                layer_types={l: 0 for l in cu}, settings=dict(SETTINGS), netclasses={"Default": dict(NETCLASS)},
                nets=nets, pads=pads, graphics=[], edges=[], zones=zones, outline_ok=True, outline=outline,
                tracks=0, probes={})


def session(tmp_path, back=(), twin=False, **opts):
    """A critical-router Session on the synthetic board, without KiCad."""
    from kae.board.kicad_file import load
    from kae.route.critical import Session
    p = write_board(tmp_path, back, twin)
    b = load(p)
    return Session(p, info=synth_info(b), board=b, opts=opts, log=lambda *a: None)
