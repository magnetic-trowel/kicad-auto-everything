# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The board's mechanical interface: parts that keep their given pose while the rest is placed.

Three classes:
  connectors  what a cable, card or mating board plugs into: kind 'connector' of
              kae.circuit.roles (reference prefix, lib id, value, description, pins), IC
              sockets excepted (a DIP/PLCC/ZIF socket holds a part, it is not an interface).
  mounting    mounting holes, standoffs and fiducials.
  user        what a person touches or looks at: switches and buttons (encoders included),
              panel potentiometers (trimmers excepted), displays, buzzers / speakers, and
              panel LEDs: through-hole LEDs and LED bars (an SMD LED is a status light
              placed with the circuit, not a panel part).
Jumpers, test points and batteries are none of these (placed like any part).

    classify(board) -> {uuid: dict(ref, cls, kind, why)}

`kae place --fix-class connectors,mounting,user` holds every part of the named classes at
its input pose (with --fix REF,... for single parts); see kae.place.pipeline.place(fixed=).
"""
import re

CLASSES = ("connectors", "mounting", "user")

_IC_SOCKET = re.compile(r"package_dip|\bdip-?\d|_socket_longpads|plcc|\bzif\b|textool|40tex|\bsupp\d+|ic.?socket", re.I)
_TRIMMER = re.compile(r"trimmer|trimpot|\b3296|\b3362|\b3266|\btrim\b|_trim", re.I)
_DISPLAY = re.compile(r"(^|[:_ ])display|\boled\b|\blcd\b|7.?segment|seven.?seg|\bdot.?matrix|\bvfd\b|e.?paper|eink|"
                      r"\bnixie|\bSSD13\d\d|\bST77\d\d|\bHD44780|\bILI9\d\d\d", re.I)
_LED_PANEL = re.compile(r"LED_THT|LED_D[1-9]\.?\d?mm|LED_[35]mm|\bLED_?Bar|bargraph|lightpipe|light_pipe|LED_Rectangular|"
                        r"\b(3|5)mm\b|\bT-1", re.I)
_PANEL_POT = re.compile(r"potentiometer|\bpot\b|alpha_rv|\brv(09|12|16|24)|\bbourns_pt|\bPTV\d|\bpanel", re.I)


def classify(board):
    """{uuid: dict(ref, cls, kind, why)} for the parts of the three classes (module doc)."""
    from kae.circuit.netlist import Netlist
    from kae.circuit.roles import infer_roles
    nl = Netlist.from_board(board)
    roles = infer_roles(nl)
    fp_by_uuid = {f.uuid: f for f in board.footprints}
    out = {}
    for k, pr in roles.parts.items():
        part = nl.parts[k]
        fp = fp_by_uuid.get(part.uuid)
        if fp is None:
            continue
        text = " ".join([fp.lib_id, fp.value, str((fp.fields or {}).get("Description", ""))])
        tht = any(pd.kind == "thru_hole" for pd in fp.pads)
        top = [f"{e.kind}: {e.fact}" for e in (pr.evidence or [])[:2]]
        cls, why = None, []
        if pr.kind == "connector":
            if _IC_SOCKET.search(text):
                continue
            cls, why = "connectors", top
        elif pr.kind in ("mounting_hole", "fiducial"):
            cls, why = "mounting", top
        elif pr.kind == "switch":
            cls, why = "user", top
        elif pr.kind == "potentiometer":
            if _TRIMMER.search(text) and not _PANEL_POT.search(fp.value):
                continue
            cls, why = "user", top
        elif pr.kind in ("buzzer",):
            cls, why = "user", top
        elif pr.kind == "led":
            if _LED_PANEL.search(text) or (tht and len(fp.pads) <= 4):
                cls, why = "user", top + [("through-hole LED" if tht else "panel LED footprint")]
        if cls is None and _DISPLAY.search(text) and pr.kind in ("module", "ic", "led", "unknown", "connector"):
            cls, why = "user", top + ["display footprint/value"]
        if cls is None:
            continue
        out[fp.uuid] = dict(ref=fp.ref, cls=cls, kind=pr.kind, subtype=pr.subtype, tht=tht, pads=len(fp.pads),
                            lib_id=fp.lib_id, value=fp.value, why=why)
    return out


def fixed_uuids(board, classes=(), refs=()):
    """uuids of the footprints held fixed: those of `classes` (classify) and those named by
    `refs`. Unknown class names or references raise ValueError."""
    bad = [c for c in classes if c not in CLASSES]
    if bad:
        raise ValueError(f"unknown fix classes {bad} (known: {', '.join(CLASSES)})")
    out = set()
    if classes:
        out |= {u for u, c in classify(board).items() if c["cls"] in classes}
    by_ref = {}
    for f in board.footprints:
        by_ref.setdefault(f.ref, []).append(f.uuid)
    missing = [r for r in refs if r not in by_ref]
    if missing:
        raise ValueError(f"--fix names unknown references {missing[:8]}")
    for r in refs:
        out |= set(by_ref[r])
    return out
