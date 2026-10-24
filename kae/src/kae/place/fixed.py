# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The board's mechanical interface: parts that keep their given pose while the rest is placed.

Three classes:
  connectors  what a cable, card or mating board plugs into: kind 'connector' of
              kae.circuit.roles (reference prefix, lib id, value, description, pins), except
              IC sockets (a DIP/PLCC/ZIF socket holds a part, it is not an interface) and
              programming / debug headers (JTAG, SWD, ISP, Tag-Connect: placed with the chip
              they program; programming_header says why).
  mounting    mounting holes, standoffs and fiducials.
  user        what a person touches or looks at: switches and buttons (encoders included),
              panel potentiometers (trimmers excepted), displays, buzzers / speakers, and
              panel LEDs: through-hole LEDs and LED bars (an SMD LED is a status light
              placed with the circuit, not a panel part).
Keyboard key switches are user parts. Jumpers, test points, SMD LEDs and batteries are none
of these (placed like any part).

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
# programming / debug headers (JTAG, SWD, ISP, ...): free, placed with their MCU / FPGA
_PROG_TEXT = re.compile(r"jtag|\bswd\b|swd_|_swd|\bisp\b|icsp|avr.?isp|tag.?connect|\bTC20[35]0|\bdebug|cortex.?(debug|m)|"
                        r"(?<![A-Za-z0-9])prog(ram(ming)?)?(_?port)?(?![A-Za-z])|clip.?prog|\bspi.?flash.?prog|\bpdi\b|\bupdi\b|\bSWIM\b|ARM.?(JTAG|SWD)|"
                        r"Conn_ARM|XILINX_JTAG|\bESP.?PROG|\bPICKIT|\bICD\b", re.I)
# interface: (name, groups of net-name tokens (any one of a group names that signal), how many
# groups must appear, extra tokens that belong to the interface without being needed)
_PROG_NETS = (("SWD", (("SWDIO", "SWD", "SWDAT", "SWDATA"), ("SWCLK", "SWDCLK", "SWC", "SWCK")), 2, ("SWO", "TRACESWO")),
              ("JTAG", (("TCK",), ("TMS",), ("TDI",), ("TDO",)), 3, ("TRST", "NTRST", "RTCK")),
              ("ISP", (("MISO",), ("MOSI",), ("SCK",), ("RESET",)), 4, ()),
              ("UPDI", (("UPDI", "UDPI"),), 1, ()),
              ("PDI", (("PDIDATA", "PDI"),), 1, ("PDICLK", "CLK")))


_NOT_PROG = re.compile(r"charg", re.I)        # a charger's PROG (current-set) pin is not programming
# panel / cable interfaces that may carry a programming interface's nets (sonde-xilinx's DB9
# JTAG cable): by their nets alone they stay connectors
_INTERFACE = re.compile(r"dsub|d-sub|\bdb-?\d|\bde-?9|usb|rj\d\d|modular|card|barrel|audio|jack", re.I)
PROG_MAX_PADS = 20       # a programming header by its nets has at most this many pads
PROG_OTHER_NETS = 2      # ... and at most this many signal nets outside the interface
_POWER = re.compile(r"gnd|vss|vcc|vdd|vbus|vref|vbat|vin|^\+|[0-9]v[0-9]?$|^/?[0-9.]+v", re.I)


def _net_tokens(name):
    return {t for t in re.split(r"[^A-Z0-9]+", (name or "").upper()) if t}


def programming_header(fp):
    """Why `fp` is a programming / debug header, or None: its lib id, value or description
    names one (JTAG, SWD, ISP, Tag-Connect, debug, prog...), or its pads carry an interface's
    nets (SWDIO+SWCLK; 3 of TCK/TMS/TDI/TDO; MISO+MOSI+SCK+RESET; UPDI; PDI)."""
    text = " ".join([fp.lib_id, fp.value, str((fp.fields or {}).get("Description", ""))])
    m = _PROG_TEXT.search(text)
    if m and not _NOT_PROG.search(text):
        return f"programming/debug header: '{m.group(0)}' in lib id/value/description"
    if len(fp.pads) > PROG_MAX_PADS or _INTERFACE.search(text):
        return None
    # nets: a small header whose signal pads are (nearly) all one programming interface's; a
    # wide connector carrying those nets among others (FMC, an expansion FFC, a card slot)
    # is an interface, not a programming header
    sig = {}
    for pd in fp.pads:
        net = pd.net or ""
        if not net or _POWER.search(net) or net.lower().startswith("unconnected"):
            continue
        leaf = net.replace("{slash}", "|").split("/")[-1]
        if "|" in leaf:
            sig[net] = {"MUXED"}          # a net named for two functions: not a dedicated one
            continue
        t = _net_tokens(leaf)
        if t & {"RST", "NRST", "NRESET", "RESETN", "MCLR"}:
            t |= {"RESET"}
        sig[net] = t
    for name, groups, need, extra in _PROG_NETS:
        hit = [g[0] for g in groups if any(set(g) & t for t in sig.values())]
        if len(hit) < need:
            continue
        mine = {x for g in groups for x in g} | set(extra) | {"RESET"}
        other = [net for net, t in sig.items() if not t & mine]
        if len(other) <= PROG_OTHER_NETS:
            return f"programming/debug header: {name} nets {'+'.join(hit)} on its pads ({len(other)} other signals)"
    return None


def classify(board, with_free=False):
    """{uuid: dict(ref, cls, kind, why)} for the parts of the three classes (module doc);
    with_free also returns the connectors judged free, {uuid: dict(ref, why)} (programming /
    debug headers, with why they were judged so)."""
    from kae.circuit.netlist import Netlist
    from kae.circuit.roles import infer_roles
    nl = Netlist.from_board(board)
    roles = infer_roles(nl)
    fp_by_uuid = {f.uuid: f for f in board.footprints}
    out, free = {}, {}
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
            prog = programming_header(fp)
            if prog:
                free[fp.uuid] = dict(ref=fp.ref, cls=None, kind=pr.kind, why=[prog])
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
    if with_free:
        return out, free
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
