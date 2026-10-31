# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Buses, their DSN order and pin fields (kae.route.bus) on synthetic pads."""
from shapely.geometry import box

from kae.route import bus, translate


def _pad(ref, number, net, x, y, w=0.25, h=0.8, hole=None):
    ring = [[x - w / 2, y - h / 2], [x + w / 2, y - h / 2], [x + w / 2, y + h / 2], [x - w / 2, y + h / 2]]
    return dict(ref=ref, number=str(number), net=net, pos=[x, y], layers=["F.Cu"], poly=[[ring]], hole=hole)


def _poly(rings):
    from shapely.geometry import Polygon
    return Polygon(rings[0])


def _qfn(ref="U1", n=8, pitch=0.5, half=2.0, nets=None):
    """A QFN with n pins per side and an exposed pad, nets 'S<i>' unless given."""
    pads, k = [], 1
    for side in range(4):
        for i in range(n):
            t = (i - (n - 1) / 2) * pitch
            x, y = [(t, -half), (half, t), (-t, half), (-half, -t)][side]
            w, h = (0.25, 0.8) if side % 2 == 0 else (0.8, 0.25)
            pads.append(_pad(ref, k, (nets or {}).get(k, f"S{k}"), x, y, w, h))
            k += 1
    ep = dict(_pad(ref, k, "GND", 0, 0, 2.5, 2.5))
    pads.append(ep)
    return pads


def test_bus_found_in_pin_order_on_both_ends():
    pads = _qfn()
    # pins 1..8 (top side) go to a 2.54 mm header in the same order
    for i in range(8):
        pads.append(_pad("J1", i + 1, f"S{i + 1}", -9 + 2.54 * i, -10, 1.7, 1.7))
    found = bus.find(pads)
    assert found == [[f"S{i}" for i in range(1, 9)]]


def test_no_bus_when_one_end_is_scattered():
    pads = _qfn()
    for i in range(8):
        pads.append(_pad("J1", i + 1, f"S{i + 1}", -9 + 2.54 * (i * 3 % 8) * 3, -10, 1.7, 1.7))
    assert bus.find(pads) == []


def test_order_moves_bus_nets_together():
    tree = ["pcb", ["network", ["net", "A"], ["net", "S3"], ["net", "B"], ["net", "S1"], ["net", "S2"]]]
    moved = bus.order(tree, [["S1", "S2", "S3"]])
    names = [c[1] for c in translate.find(tree, "network")[1:]]
    assert names == ["A", "S1", "S2", "S3", "B"]
    assert moved == 4


def test_pin_field_is_the_ring_without_the_exposed_pad():
    fields = bus.pin_fields(_qfn(), _poly)
    assert [r for r, _ in fields] == ["U1"]
    geo = fields[0][1]
    assert not geo.intersects(box(-1.0, -1.0, 1.0, 1.0))     # the exposed pad stays free for its vias
    assert geo.contains(box(1.6, -0.2, 1.7, 0.2))            # between the pads and the exposed pad


def test_no_pin_field_for_coarse_pitch_or_two_row_connectors():
    assert bus.pin_fields(_qfn(pitch=1.27, half=6.0), _poly) == []
    two_rows = [_pad("J1", i, f"S{i}", 0.5 * (i % 12), 0.0 if i < 12 else 1.5) for i in range(24)]
    assert bus.pin_fields(two_rows, _poly) == []


def test_switches_from_the_board(tmp_path):
    """KAE_PIN_FIELDS / KAE_BUS_ORDER in the project win over opts (--set), which win over the
    defaults (both off), as for every kae limit."""
    import json
    from kae.route import constraints
    pcb = tmp_path / "b.kicad_pcb"
    pro = pcb.with_suffix(".kicad_pro")
    assert constraints.setting("pin_fields", pcb) is False
    assert constraints.setting("bus_order", pcb, dict(bus_order="1")) is True
    pro.write_text(json.dumps({"text_variables": {"KAE_PIN_FIELDS": "yes", "KAE_BUS_ORDER": "0"}}))
    assert constraints.setting("pin_fields", pcb, dict(pin_fields=False)) is True
    assert constraints.setting("bus_order", pcb, dict(bus_order=True)) is False
    pro.write_text(json.dumps({"text_variables": {"KAE_BUS_ORDER": "maybe"}}))
    assert constraints.setting("bus_order", pcb, dict(bus_order="on")) is True
