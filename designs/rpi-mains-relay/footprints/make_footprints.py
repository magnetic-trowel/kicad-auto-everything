# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write the custom footprints of rpi-mains-relay into custom.pretty/ (run: python make_footprints.py).

Geometry sources (see parts.py for the full citations):
  WAGO 2606-310x/020-000  data sheets 2606-3102/020-000 (v28.02.2024) and 2606-3103/020-000 (v22.10.2026),
                          'Dimensions in mm': pole 1 pin 5.5 mm from the body end and 7.7 mm from the wire-entry
                          face; pins staggered, odd poles on the 7.7 mm row, even poles 12.5 mm further back;
                          pitch 7.5 mm; body L = (poles - 1) x 7.5 + 10.35 mm, depth 24 mm; hole 2.0 (+0.1) mm.
  Raspberry Pi Zero 2 W   mechanical drawing (datasheets.raspberrypi.com/rpizero2/...mechanical-drawing.pdf):
                          65 x 30 mm, holes 3.5 mm from each edge, 40-pin header centred on the long edge
                          (29 mm from the left hole = 32.5 mm from the left edge), row centre 3.5 mm from the
                          header edge. Antenna zone between the mini-HDMI (centre 12.4 mm) and the USB (41.4 mm)
                          on the connector edge [I: inferred from the Zero W layout and the 'Proant' silkscreen].
"""
from pathlib import Path

OUT = Path(__file__).with_name("custom.pretty")
HDR = """(footprint "{name}"
	(version 20260206)
	(generator "kaesynth-design")
	(layer "F.Cu")
	(descr "{descr}")
	(tags "{tags}")
	(property "Reference" "REF**"
		(at {rx:.3f} {ry:.3f} 0)
		(layer "F.SilkS")
		(effects (font (size 1 1) (thickness 0.15)))
	)
	(property "Value" "{name}"
		(at {vx:.3f} {vy:.3f} 0)
		(layer "F.Fab")
		(effects (font (size 1 1) (thickness 0.15)))
	)
	(attr through_hole)
	(duplicate_pad_numbers_are_jumpers no)
"""


def rect(x0, y0, x1, y1, layer, width):
    return (f"\t(fp_rect (start {x0:.3f} {y0:.3f}) (end {x1:.3f} {y1:.3f})\n"
            f"\t\t(stroke (width {width}) (type solid)) (fill no) (layer \"{layer}\"))\n")


def line(x0, y0, x1, y1, layer, width):
    return (f"\t(fp_line (start {x0:.3f} {y0:.3f}) (end {x1:.3f} {y1:.3f})\n"
            f"\t\t(stroke (width {width}) (type solid)) (layer \"{layer}\"))\n")


def text(s, x, y, layer, size=1.0):
    return (f"\t(fp_text user \"{s}\" (at {x:.3f} {y:.3f} 0) (layer \"{layer}\")\n"
            f"\t\t(effects (font (size {size} {size}) (thickness {size * 0.15:.3f}))))\n")


def pad(num, x, y, size, drill, shape="circle"):
    return (f"\t(pad \"{num}\" thru_hole {shape} (at {x:.3f} {y:.3f}) (size {size} {size}) (drill {drill})\n"
            f"\t\t(layers \"*.Cu\" \"*.Mask\") (remove_unused_layers no))\n")


def keepout(pts, what):
    xy = " ".join(f"(xy {x:.3f} {y:.3f})" for x, y in pts)
    return ("\t(zone (net 0) (net_name \"\") (layers \"F.Cu\" \"B.Cu\") (name \"" + what + "\")\n"
            "\t\t(hatch full 0.508) (connect_pads (clearance 0)) (min_thickness 0.254)\n"
            "\t\t(keepout (tracks not_allowed) (vias not_allowed) (pads not_allowed) (copperpour not_allowed)"
            " (footprints not_allowed))\n"
            "\t\t(placement (enabled no) (sheetname \"\"))\n"
            "\t\t(fill (thermal_gap 0.508) (thermal_bridge_width 0.508))\n"
            f"\t\t(polygon (pts {xy}))\n\t)\n")


def wago_2606(poles):
    """Origin = pole 1 pin. +y = away from the wire-entry (lever) face."""
    name = f"WAGO_2606-310{poles}_020-000"
    length = (poles - 1) * 7.5 + 10.35
    x0, x1, y0, y1 = -5.5, -5.5 + length, -7.7, -7.7 + 24.0
    s = HDR.format(name=name, rx=(x0 + x1) / 2, ry=y0 - 1.5, vx=(x0 + x1) / 2, vy=y1 + 1.5,
                   descr=f"WAGO 2606-310{poles}/020-000 PCB terminal block, lever, push-in CAGE CLAMP, 6 mm2, "
                         f"{poles}-pole, 7.5 mm pitch, staggered pins (odd poles 7.7 mm from the wire-entry face, "
                         f"even poles +12.5 mm), drill 2.0 (+0.1) mm; body {length:.2f} x 24 mm, 27 mm high "
                         f"(31 mm with lever). Data sheet 2606-310{poles}/020-000 'Dimensions in mm'.",
                   tags="WAGO 2606 terminal block lever push-in 7.5mm")
    s += rect(x0, y0, x1, y1, "F.Fab", 0.1)
    s += text("WIRE ENTRY", (x0 + x1) / 2, y0 + 1.5, "F.Fab", 0.8)
    s += rect(x0 - 0.12, y0 - 0.12, x1 + 0.12, y1 + 0.12, "F.SilkS", 0.12)
    s += line(x0 - 0.12, y0 - 0.6, x0 + 3.0, y0 - 0.6, "F.SilkS", 0.12)   # pole-1 / wire-entry marker
    s += rect(x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5, "F.CrtYd", 0.05)
    for i in range(1, poles + 1):
        s += pad(str(i), (i - 1) * 7.5, 0.0 if i % 2 else 12.5, 3.5, 2.1, "rect" if i == 1 else "circle")
    return name, s + "\t(embedded_fonts no)\n)\n"


def rpi_zero2w_socket():
    """2x20 socket for a Raspberry Pi Zero 2 W mounted component-side UP above this board, its header
    soldered on the Pi's underside. Pin numbering therefore matches the Pi's own top view (pin 2 on the
    edge row, north of pin 1): this is the PinHeader handedness, NOT KiCad's PinSocket one (which assumes a
    board flipped face-down). Origin = pin 1. Pi outline, holes and the antenna keepout are drawn relative
    to the pins; the Pi standoff holes themselves are board holes (design.py board()), not pads here."""
    name = "RPi_Zero2W_Socket_2x20_P2.54mm"
    # Pi top-view coordinates (x right from the SD-card end, y down from the header edge); pin 1 at (8.37, 4.77)
    px, py = 32.5 - 9.5 * 2.54, 3.5 + 1.27

    def t(x, y):     # Pi coordinates -> footprint coordinates (KiCad y down, same as the Pi drawing)
        return x - px, y - py

    s = HDR.format(name=name, rx=t(32.5, -2.0)[0], ry=t(32.5, -2.0)[1], vx=t(32.5, 15)[0], vy=t(32.5, 15)[1],
                   descr="Sullins PPPC202LFBN-RC 2x20 2.54 mm socket (8.51 mm) carrying a Raspberry Pi Zero 2 W "
                         "component side up (header soldered on the Pi underside, 11 mm stack, M2.5 x 11 mm "
                         "standoffs). Pin numbering = Pi top view. F.Fab: Pi 65 x 30 mm outline and holes; "
                         "rule area: Wi-Fi antenna zone, no copper/vias/pads/pours/parts on either layer.",
                   tags="Raspberry Pi Zero 2 W socket 2x20 antenna keepout")
    # socket body (2 x 20 at 2.54 mm: 5.08 x 50.8 mm) around the pins
    s += rect(-1.27, -3.81, 19 * 2.54 + 1.27, 1.27, "F.SilkS", 0.12)
    s += line(-1.9, 0.0, -1.9, 1.9, "F.SilkS", 0.12)   # pin-1 marker
    s += rect(-1.27, -3.81, 19 * 2.54 + 1.27, 1.27, "F.Fab", 0.1)
    # Pi outline and mounting holes (F.Fab), courtyard = Pi outline + 0.5 mm (nothing else under the Pi)
    x0, y0 = t(0, 0)
    x1, y1 = t(65, 30)
    s += rect(x0, y0, x1, y1, "F.Fab", 0.1)
    s += text("Pi Zero 2 W, component side UP", *t(32.5, 12), "F.Fab", 1.0)
    s += text("header on the Pi's underside", *t(32.5, 14.5), "F.Fab", 0.8)
    for hx, hy in ((3.5, 3.5), (61.5, 3.5), (3.5, 26.5), (61.5, 26.5)):
        cx, cy = t(hx, hy)
        s += (f"\t(fp_circle (center {cx:.3f} {cy:.3f}) (end {cx + 1.35:.3f} {cy:.3f})\n"
              "\t\t(stroke (width 0.1) (type solid)) (fill no) (layer \"F.Fab\"))\n")
    s += rect(x0 - 0.12, y0 - 0.12, x1 + 0.12, y1 + 0.12, "F.SilkS", 0.12)
    s += text("PI ZERO 2 W - COMPONENTS UP", *t(32.5, 9), "F.SilkS", 1.2)
    s += text("ANTENNA - NO COPPER", *t(27.5, 27.5), "F.SilkS", 1.0)
    s += rect(x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5, "F.CrtYd", 0.05)
    # antenna keepout: x 12..45 mm (between the mini-HDMI and USB), from 12 mm inside the connector edge to
    # 10 mm beyond it; place the Pi so its connector edge is at the board edge (design.py)
    ax0, ay0 = t(12, 18)
    ax1, ay1 = t(45, 40)
    s += keepout([(ax0, ay0), (ax1, ay0), (ax1, ay1), (ax0, ay1)], "PI_ANTENNA")
    for k in range(20):
        x = k * 2.54
        s += pad(str(2 * k + 1), x, 0.0, 1.7, 1.0, "rect" if k == 0 else "circle")
        s += pad(str(2 * k + 2), x, -2.54, 1.7, 1.0)
    return name, s + "\t(embedded_fonts no)\n)\n"


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for fn in (lambda: wago_2606(2), lambda: wago_2606(3), rpi_zero2w_socket):
        n, body = fn()
        (OUT / f"{n}.kicad_mod").write_text(body)
        print("wrote", OUT / f"{n}.kicad_mod")
