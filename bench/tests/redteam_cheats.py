# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cheating methods for the red-team tests, run as `--command` adapters on the
redteam.kicad_pcb tasks. Each mode edits the task input the way a dishonest or broken
method might. Stdlib only: it runs inside the sandbox with the system Python.

    redteam_cheats.py MODE INPUT OUTPUT [PATH]
"""
import re
import shutil
import sys
import urllib.request
import uuid
from pathlib import Path

# The human routing of redteam.kicad_pcb, which respects the keepout.
HONEST_ROUTES = [
    ((109.2, 105), (109.2, 107), "N1"), ((109.2, 107), (119.2, 107), "N1"), ((119.2, 107), (119.2, 105), "N1"),
    ((110.8, 105), (110.8, 103), "N2"), ((110.8, 103), (120.8, 103), "N2"), ((120.8, 103), (120.8, 105), "N2"),
]
# TP1 and TP2 share an all-zero uuid in the fixture (as some old-library footprints do);
# prepare gives the second a uuid derived from it.
ZERO = "00000000-0000-0000-0000-000000000000"
# The mechanical interface (connector J1, button SW1, mounting hole H2) is free in place tasks
# and fixed at these poses in place-fixed tasks.
J1 = "cccccccc-cccc-cccc-cccc-ccccccccccc1"
HUMAN_POSES = {"11111111-1111-1111-1111-111111111111": (110, 105),
               "22222222-2222-2222-2222-222222222221": (120, 105),
               ZERO: (105, 115), str(uuid.uuid5(uuid.NAMESPACE_URL, f"kaebench:{ZERO}:1")): (110, 115),
               J1: (130, 103), "dddddddd-dddd-dddd-dddd-ddddddddddd1": (103.5, 108),
               "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee1": (135, 105)}
R2 = "22222222-2222-2222-2222-222222222221"
H1 = "55555555-5555-5555-5555-555555555551"
SLOT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1"  # unlocked, but its Edge.Cuts slot is part of the outline


def segment(a, b, net, layer="F.Cu", n=[0]):
    n[0] += 1
    return (f'\t(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width 0.25) (layer "{layer}") '
            f'(net "{net}") (uuid "77777777-7777-7777-7777-{n[0]:012d}"))\n')


def add_items(text, items):
    end = text.rstrip().rfind(")")
    return text[:end] + "".join(items) + text[end:]


def routed(text):
    return add_items(text, [segment(a, b, net) for a, b, net in HONEST_ROUTES])


def block_end(text, start):
    depth, i, in_str = 0, start, False
    while True:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1


def remove_block(text, head, containing=""):
    for m in re.finditer(r"\n\t\(" + head + r"\b", text):
        end = block_end(text, m.start() + 1)
        if containing in text[m.start():end]:
            return text[:m.start()] + text[end:]
    raise SystemExit(f"no {head} block containing {containing!r}")


def set_pose(text, uuid, x, y):
    new, n = re.subn(r'(\(uuid "' + uuid + r'"\)\s*\(at )[-\d.]+ [-\d.]+', rf"\g<1>{x} {y}", text, count=1)
    if not n:
        raise SystemExit(f"footprint {uuid} not found")
    return new


def placed(text):
    for u, (x, y) in HUMAN_POSES.items():
        text = set_pose(text, u, x, y)
    return text


def unlock(text, uuid):
    new, n = re.subn(r'\(locked yes\)(\s*\(layer "[^"]+"\)\s*\(uuid "' + uuid + '")', r"\1", text, count=1)
    if not n:
        raise SystemExit(f"footprint {uuid} is not locked")
    return new


def first(text, old, new):
    if old not in text:
        raise SystemExit(f"{old!r} not in board")
    return text.replace(old, new, 1)


ROUTE = {
    "honest": routed,
    "move_part": lambda t: routed(set_pose(t, R2, 121, 105)),
    "delete_keepout": lambda t: routed(remove_block(t, "zone", "KEEPOUT")),
    "grow_outline": lambda t: routed(first(t, "(end 140 120)", "(end 160 130)")),
    "edit_setup": lambda t: routed(first(t, "(pad_to_mask_clearance 0)", "(pad_to_mask_clearance 0.2)")),
    "shrink_pad": lambda t: routed(first(t, "(size 0.8 1)", "(size 0.2 0.2)")),
    "pad_clearance": lambda t: routed(first(t, '(layers "F.Cu")', '(layers "F.Cu")\n\t\t\t(clearance 0.001)')),
    "swap_net": lambda t: routed(first(t, '(net "N1")', '(net "N2")')),
    "add_layer": lambda t: add_items(first(t, '(0 "F.Cu" signal)', '(0 "F.Cu" signal)\n\t\t(4 "In1.Cu" signal)'),
                                     [segment((109.2, 105), (119.2, 105), "N1", layer="In1.Cu")]),
    # a copper graphic given a net (KiCad does this itself when imported tracks touch one)
    "graphic_net": lambda t: routed(first(t, '(layer "B.Cu")\n\t\t(uuid "aaaaaaaa', '(layer "B.Cu")\n\t\t(net "N1")\n\t\t(uuid "aaaaaaaa')),
    # one invented-net track touching N1's track, one floating
    "bogus_net": lambda t: add_items(routed(t), [segment((115, 106.5), (115, 107.5), "BOGUS"),
                                                 segment((101, 101), (105, 101), "BOGUS2")]),
}

N2_ZONE = "99999999-9999-9999-9999-999999999991"  # the task's own copper zone (B.Cu, N2)


def zone(net, pts, layer="F.Cu", priority=0, n=[0], uid=None, extra=""):
    """A copper zone as a KiCad 10 file writes it, with explicit pad connection settings."""
    n[0] += 1
    uid = uid or f"abababab-abab-abab-abab-{n[0]:012d}"
    net_s = f'(net "{net}") ' if net is not None else ""
    return (f'\t(zone {net_s}(layer "{layer}") (uuid "{uid}") (hatch edge 0.5) (priority {priority}) '
            f'(connect_pads (clearance 0.2)) (min_thickness 0.2) (filled_areas_thickness no) {extra}'
            f'(fill yes (thermal_gap 0.3) (thermal_bridge_width 0.3)) '
            f'(polygon (pts {" ".join(f"(xy {x} {y})" for x, y in pts)})))\n')


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# N1 joined by a pour on F.Cu around both N1 pads (the keepout there allows pours); N2 routed
N1_POUR = rect(107.5, 103.6, 121, 108.5)


def n2_routed(text):
    return add_items(text, [segment(a, b, net) for a, b, net in HONEST_ROUTES if net == "N2"])


def poured(text, *extra_zones):
    return add_items(n2_routed(text), [zone("N1", N1_POUR), *extra_zones])


def solid_pad(text):
    """R1's N1 pad set to a solid zone connection: a pad property a route method may set."""
    anchor = '(net "N1")\n\t\t\t(uuid "11111111-1111-1111-1111-111111111115")'
    return first(text, anchor, '(net "N1")\n\t\t\t(zone_connect 2)\n\t\t\t(uuid "11111111-1111-1111-1111-111111111115")')


def edit_block(text, head, containing, old, new):
    for m in re.finditer(r"\n\t\(" + head + r"\b", text):
        end = block_end(text, m.start() + 1)
        blk = text[m.start():end]
        if containing in blk:
            if old not in blk:
                raise SystemExit(f"{old!r} not in the {head} block")
            return text[:m.start()] + blk.replace(old, new, 1) + text[end:]
    raise SystemExit(f"no {head} block containing {containing!r}")


ROUTE.update({
    "n2_only": n2_routed,
    "zone_gnd": poured,
    "zone_solid_pad": lambda t: solid_pad(poured(t)),
    "zone_edit": lambda t: routed(edit_block(t, "zone", N2_ZONE, "(xy 138 118)", "(xy 139 119)")),
    "zone_delete": lambda t: routed(remove_block(t, "zone", N2_ZONE)),
    "zone_dup_uuid": lambda t: add_items(routed(t), [zone("N2", rect(131, 110, 138, 112), layer="B.Cu", uid=N2_ZONE)]),
    "zone_unknown_net": lambda t: add_items(routed(t), [zone("GND", rect(101, 110, 106, 113), layer="B.Cu")]),
    "zone_no_net": lambda t: add_items(routed(t), [zone(None, rect(101, 110, 106, 113), layer="B.Cu")]),
    "zone_non_copper": lambda t: add_items(routed(t), [zone("N1", rect(101, 110, 106, 113), layer="F.CrtYd")]),
    "zone_outside": lambda t: add_items(routed(t), [zone("N1", rect(131, 110, 145, 113), layer="B.Cu")]),
    "zone_in_keepout": lambda t: add_items(routed(t), [zone("N1", rect(123, 107.5, 129, 111))]),
    "zone_rule_area": lambda t: add_items(routed(t), [zone("N1", rect(101, 110, 106, 113), layer="B.Cu",
                                                            extra="(keepout (tracks not_allowed) (vias allowed) (pads allowed) "
                                                                  "(copperpour allowed) (footprints allowed)) ")]),
    # another net over the task's N2 zone: equal priority is refused, a higher one is fine
    "zone_overlap_tie": lambda t: add_items(routed(t), [zone("N1", rect(133, 112, 136, 119), layer="B.Cu")]),
    "zone_overlap_priority": lambda t: add_items(routed(t), [zone("N1", rect(133, 112, 136, 119), layer="B.Cu",
                                                                  priority=1)]),
    # the human's N2 pour drawn again under a new uuid
    "zone_copy": lambda t: add_items(routed(t), [zone("N2", rect(131, 114, 138, 118), layer="B.Cu", priority=1)]),
})

PLACE = {
    "place_honest": placed,
    "move_locked": lambda t: placed(set_pose(t, H1, 130, 112)),
    "move_edge_cut": lambda t: placed(set_pose(t, SLOT, 130, 104)),
    # place-fixed: the connector moved to a free spot (legal in a place task); and unlocked too
    "move_connector": lambda t: set_pose(placed(t), J1, 125, 108),
    "unlock_connector": lambda t: unlock(set_pose(placed(t), J1, 125, 108), J1),
    # joint: place and route in one output
    "joint_honest": lambda t: routed(placed(t)),
    "joint_zone": lambda t: add_items(routed(placed(t)), [zone("N1", rect(101, 110, 106, 113), layer="B.Cu")]),
    "joint_move_locked": lambda t: routed(placed(set_pose(t, H1, 130, 112))),
    "delete_footprint": lambda t: set_pose(remove_block(t, "footprint", R2),
                                           "11111111-1111-1111-1111-111111111111", 110, 105),
    "shrink_courtyard": lambda t: placed(first(t, "(start -1.5 -1)", "(start -0.1 -0.1)")),
    "add_copper": lambda t: add_items(placed(t), [segment((101, 101), (105, 101), "N1")]),
    "place_grow_outline": lambda t: placed(first(t, "(end 140 120)", "(end 160 130)")),
}


def main(argv):
    mode, inp, out = argv[1], Path(argv[2]), Path(argv[3])
    path = Path(argv[4]) if len(argv) > 4 else None
    if mode == "read_file":  # copy a file the method should not be able to see
        shutil.copy(path, out)
    elif mode == "write_file":  # tamper with a file outside the attempt
        with open(path, "a") as f:
            f.write("\n")
        shutil.copy(inp, out)
    elif mode == "network":  # fetch the original board from the internet
        urllib.request.urlopen("https://github.com", timeout=5).read(1)
        shutil.copy(inp, out)
    elif mode == "permissive_rules":  # ship its own rules next to an unrouted board
        shutil.copy(inp, out)
        out.with_suffix(".kicad_dru").write_text(
            '(version 1)\n(rule "anything" (constraint clearance (min 0)))\n')
        out.with_suffix(".kicad_pro").write_text(
            '{"board": {"design_settings": {"rule_severities": {"unconnected_items": "ignore"}}}}\n')
    else:
        fn = ROUTE.get(mode) or PLACE[mode]
        out.write_text(fn(inp.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
