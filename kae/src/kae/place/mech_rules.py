# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Which footprints are the board's mechanical interface (place-fixed tasks).

A placer that moves the connectors, mounting holes or user controls can beat the human
on wire length while making a board that no longer fits its enclosure or cables. In
place-fixed tasks these parts stay at the human pose, locked like the designer's own
locked parts. This module decides which parts they are.

Pure Python (no pcbnew): pcbnew_ops.py feeds it one dict per footprint, and the unit
tests call it directly. Each footprint gets a class and the rule that matched:

  connector  anything the outside world plugs into: USB, pin headers and sockets,
             JST/Molex/FPC/FFC, terminal blocks, barrel and audio jacks, RF connectors,
             card slots (SD/SIM), edge connectors, wire pads
  mounting   screw holes, standoffs, fiducials, footprints whose pads are all NPTH
  user       switches and keyboard key switches (Cherry MX, Kailh/Choc, Gateron...),
             buttons, potentiometers and encoders, displays, through-hole, light-pipe and
             LED-bar indicators, buzzers and speakers
  None       everything else: heatsinked power parts, SMD LEDs, and the borderline parts
             the user chose to leave free (rule 1 and the debug-header rule)

Rules, in order; the first that matches decides:

  1. exclude   test points (TestPoint* library, TestPoint, TP, Test-TH/pad/pin in the name; reference TP
               only after rule 5),
               jumpers and solder bridges (Jumper* library, SolderJumper/Jumper/Bridge in
               the name, reference JP/SJ), net ties, heatsinks (they move with their part),
               batteries and battery holders (Battery* library, battery (not battery
               connector), cell holder, coin cell, CR2032 in the name, reference BT),
               trimmers (trim, Bourns 3266/3296/3299/3314/3339/3362/3386, Piher PT in the
               name), IC sockets (DIP/PLCC/SOIC socket, ZIF, Textool in the name, value
               SUPPnn), footprints without pads
               (logos, graphics) -> not fixed
  2. lib       KiCad library nickname (LIB_RULES): Connector*, TerminalBlock*,
               MountingHole*, Fiducial*, Button_Switch*, Potentiometer*, Rotary_Encoder*,
               Display*, Buzzer_Beeper*, LED_THT, older or third-party names that contain
               "connector", "mountinghole", "fiducial", "switch" or "oled", and connector
               makers' libraries (Molex, JST, Hirose, Samtec, Amphenol)
  3. npth      every pad is NPTH (a hole with no copper) -> mounting
     THT LED   a through-hole LED footprint (LED_D5.0mm, LED-3MM) with >= 2 plated pads,
               an LED (library, name, or LED/D reference with an LED value) with 2-4 pads,
               all plated through-hole, a light pipe or LED bar -> user (panel indicator);
               SMD LEDs are not fixed
  4. conflict  a library or footprint name that says the part is a passive, diode, LED,
               crystal, fuse, transistor or IC package, or a plug-in module (CONFLICT_LIBS,
               CONFLICT_NAME), or
               a passive/diode/transistor reference (R, C, L, D, Q, FB, Y, F, VR...),
               stops rules 5-7: a resistor called "USB" is still a resistor, and an SMA
               diode package is not an SMA connector
  5. name      patterns on the footprint name (NAME_RULES): USB, PinHeader/PinSocket,
               JST, Molex, FPC/FFC, Jack, SMA/U.FL, microSD/SIM, card edge, terminal
               block, RJ45, D-Sub, CON/CONN; MountingHole, standoff, fiducial, hole (with
               at most one net: TSOP39238_Standoff is a part, not a standoff);
               switch, button, encoder, pot, OLED/LCD/display, buzzer, key switches
               (MX, Choc, Kailh)
  6. value     KiCad symbol names used as values (VALUE_RULES): Conn_01x04,
               USB_C_Receptacle, Barrel_Jack, Micro_SD_Card, RJ45/MagJack, SW_Push,
               Rotary_Encoder, R_POT, Buzzer, MountingHole, Fiducial; display names
               (OLED, LCD, TFT, e-paper, SSD13xx, HD44780...) in the value
  7. ref       reference prefixes, only with a footprint that fits (REF_RULES): J, CN,
               CON, P, USB -> connector; H, MH, HOLE, MTG with a drilled pad -> mounting;
               FID with at most 3 SMD pads -> mounting; SW*, S, KSW, BTN, KEY, ENC, LS,
               BZ, SPK, RST, BOOT with at least 2 pads, RV/POT with at least 3 -> user. Not X
               (crystals), VR (regulators), DS (often diodes), K (relays).

  Then jumpers (a connector whose value says JUMP...) and programming and debug headers are
  freed: a part classed connector whose footprint
  name, value, library description or reference says JTAG, SWD, ISP/ICSP, PDI/UPDI, SWIM,
  BDM, Tag-Connect (TC2030/TC2050/TC2070), Cortex/ARM debug, ESP-Prog, PICkit, ICD, debug or
  prog (DEBUG_HEADERS; not when it says "charg": a charger's PROG pin), or a connector of at
  most 20 pads, not a panel/cable interface, whose signal nets are one programming interface
  (SWDIO+SWCLK; 3 of TCK/TMS/TDI/TDO; MISO+MOSI+SCK+reset; UPDI; PDI) plus at most two others
  (PROG_NETS) is not fixed: they face a programmer, not the enclosure. A button named PROG
  stays fixed (the rule only frees connectors). These follow the placement research
  classifier (kae.place.fixed) so both fix the same parts.

Overrides per board (prepare --fixed-overrides) can fix or free parts by reference.
"""
import re

CLASSES = ("connector", "mounting", "user")
# 2: the user's choices on borderline parts: key switches fixed; debug headers, batteries,
#    trimmers and IC sockets free; light pipes and LED bars fixed
# 3: aligned with the placement session's classifier (kae.place.fixed): debug headers also by
#    their nets and a longer keyword list, displays by value, any THT LED with 2-4 pads,
#    switches by value/reference (RST, BOOT), a trimmer's panel hole stays a hole
# 4: the user's judgement calls: SIMM sockets, microphone headers and pots whose value
#    says trim are free (NPTH-only parts stay fixed as mounting)
RULES_VERSION = 4

_I = re.IGNORECASE

# 1. never fixed: (what, library, footprint name, reference prefix)
NEVER = re.compile(r"(?!)")
EXCLUDE = (
    ("test point", re.compile(r"^test_?points?", _I),
     re.compile(r"test_?point|(?<![a-z])tp(?![a-z])|^test(?![a-z])|test[-_](th|pad|pin)", _I),
     None),
    ("jumper", re.compile(r"^jumper", _I), re.compile(r"solder_?jumper|jumper|(?<![a-z])bridge", _I),
     re.compile(r"^(JP|SJ)$")),
    ("net tie", re.compile(r"^nettie", _I), re.compile(r"net_?tie", _I), re.compile(r"^NT$")),
    ("heatsink", re.compile(r"heatsink", _I), re.compile(r"heat_?sink", _I), None),
    ("battery", re.compile(r"^batter(y|ies)", _I),
     re.compile(r"battery(?![-_]?conn)|batt_?holder|cell_?holder|coin_?cell|(?<![a-z])cr\d{4}|(?<![a-z0-9])18650", _I),
     re.compile(r"^BT$")),
    ("trimmer", NEVER,
     re.compile(r"(?<![a-z])trim|bourns_?3(266|296|299|314|339|362|386)|"
                r"(?<![a-z0-9])3(266|296|299|314|339|362|386)[a-z]|piher_?pt", _I), None),
    ("SIMM socket", NEVER, re.compile(r"(?<![a-z])simm|(?<![a-z])sim\d", _I), None),
    ("microphone", NEVER, re.compile(r"microphone", _I), re.compile(r"^MK$")),
    ("IC socket", NEVER,
     re.compile(r"(dip|plcc|soic|sop|qfp|pga|sip)[-_\w]*socket|zif|textool|(?<![a-z])\d+tex(?![a-z])", _I),
     None),
)
# a pin header used as a jumper (value JUMPER, Jumper_2_Open, ..._JUMP): freed like a
# debug header
JUMPER_VALUE = re.compile(r"jump", _I)
# a pot whose value says trim (Mix_trim_50k) is a trimmer even on a panel-pot footprint
TRIM_VALUE = re.compile(r"(?<![a-z])trim", _I)


def _one_net(fp):
    """A mounting hole connects to at most one net (GND); a part named ..._Standoff with
    several nets is a component on a standoff (TSOP39238_Standoff), not a hole."""
    return len(fp.get("nets") or ()) <= 1


IC_SOCKET_VALUE = re.compile(r"^supp\d", _I)  # KiCad 4's IC socket symbol

# programming and debug headers: freed when classed connector
# (the placement research classifier's list, kae.place.fixed, plus BDM, PGM and UDPI)
DEBUG_HEADERS = re.compile(
    r"jtag|swd|swclk|icsp|avr.?isp|(?<![a-z])isp(?![a-z])|updi|udpi|(?<![a-z])pdi(?![a-z])|(?<![a-z])swim(?![a-z])|"
    r"(?<![a-z])bdm|tag.?connect|(?<![a-z])tc20[357]0|debug|cortex.?m|conn_arm|esp.?prog|pickit|(?<![a-z])icd(?![a-z])|"
    r"clip.?prog|(?<![a-z0-9])prog(ram(ming)?)?(_?port)?(?![a-z])|(?<![a-z])pgm(?![a-z])", _I)
NOT_DEBUG = re.compile(r"charg", _I)  # a charger's PROG (current-set) pin is not programming
# Debug headers by their nets: a small connector (not a panel/cable interface) whose signal
# nets are one programming interface plus at most PROG_OTHER_NETS others. (interface, groups
# of net-name tokens (any one names that signal), groups needed, tokens that also belong)
PROG_NETS = (("SWD", (("SWDIO", "SWD", "SWDAT", "SWDATA"), ("SWCLK", "SWDCLK", "SWC", "SWCK")), 2,
              ("SWO", "TRACESWO")),
             ("JTAG", (("TCK",), ("TMS",), ("TDI",), ("TDO",)), 3, ("TRST", "NTRST", "RTCK")),
             ("ISP", (("MISO",), ("MOSI",), ("SCK",), ("RESET",)), 4, ()),
             ("UPDI", (("UPDI", "UDPI"),), 1, ()),
             ("PDI", (("PDIDATA", "PDI"),), 1, ("PDICLK", "CLK")))
PROG_MAX_PADS = 20
PROG_OTHER_NETS = 2
PANEL_INTERFACE = re.compile(r"dsub|d-sub|(?<![a-z])db-?\d|(?<![a-z])de-?9|usb|rj\d\d|modular|card|barrel|audio|jack",
                             _I)
POWER_NET = re.compile(r"gnd|vss|vcc|vdd|vbus|vref|vbat|vin|^\+|[0-9]v[0-9]?$|^/?[0-9.]+v", _I)


def _net_header(fp):
    """The programming interface whose nets a small connector carries, or None."""
    if fp["pads"] > PROG_MAX_PADS or PANEL_INTERFACE.search(f"{fp.get('name')} {fp.get('value')}"):
        return None
    sig = {}
    for net in fp.get("nets") or ():
        if not net or POWER_NET.search(net) or net.lower().startswith("unconnected"):
            continue
        leaf = net.replace("{slash}", "|").split("/")[-1]
        if "|" in leaf:  # a net named for two functions is not a dedicated one
            sig[net] = {"MUXED"}
            continue
        t = {x for x in re.split(r"[^A-Z0-9]+", leaf.upper()) if x}
        if t & {"RST", "NRST", "NRESET", "RESETN", "MCLR"}:
            t |= {"RESET"}
        sig[net] = t
    for name, groups, need, extra in PROG_NETS:
        hit = [g[0] for g in groups if any(set(g) & t for t in sig.values())]
        if len(hit) < need:
            continue
        own = {x for g in groups for x in g} | set(extra) | {"RESET"}
        if sum(1 for t in sig.values() if not t & own) <= PROG_OTHER_NETS:
            return f"{name} nets {'+'.join(hit)}"
    return None

# 2. library nickname -> class (case-insensitive; first match wins)
LIB_RULES = (
    ("connector", re.compile(r"^(connector|terminalblock|terminal_block|socket_strips|pin_headers|"
                             r"wire_pads)", _I)),
    ("mounting", re.compile(r"^(mountinghole|mounting_holes|mountingequipment|fiducial)", _I)),
    ("user", re.compile(r"^(button_switch|buttons_switches|potentiometer|rotary_encoder|display|"
                        r"buzzer|buzzers_beepers|led_tht)", _I)),
    ("connector", re.compile(r"connector|^(molex|jst|hirose|samtec|amphenol)(?![a-z])", _I)),
    ("mounting", re.compile(r"mounting_?hole|fiducial", _I)),
    ("user", re.compile(r"switch(?!ing|science|craft)|oled", _I)),
)

# 4. libraries and names that say "not a mechanical part"
CONFLICT_LIBS = re.compile(
    r"^(resistor|capacitor|inductor|diode|led_smd|package_|crystal|oscillator|fuse|transistor|"
    r"varistor|ferrite|housings_|to_sot_packages|smd_packages|symbol|logo|sensor|relay|"
    r"rf_module|module(?![a-z])|converter|battery|opto)", _I)
CONFLICT_NAME = re.compile(
    r"^(R|C|CP|L|D|F|FB)_(\d{4}|axial|radial|do-?\d|sod|melf|array)|^led[-_]|"
    r"^(sot|soic|sop|ssop|tssop|msop|vssop|qfn|vqfn|uqfn|hvqfn|dfn|wson|son|qfp|lqfp|tqfp|bga|lga|"
    r"dip|sod|to-|plcc|sc-|wlcsp|csp|hc-?49|crystal|oscillator)|"
    # an IC package anywhere in the name (ST_STUSB03EQR_QFN-16 is a USB switch, not a USB port),
    # and plug-in modules (a dev board on headers is placed like a part)
    r"(?<![a-z])(qfn|vqfn|dfn|soic|ssop|tssop|msop|qfp|lqfp|tqfp|bga|lga|wson)-?\d|wemos|devkit|"
    r"(?<![a-z])module", _I)

# 4. reference prefixes of passives, diodes and transistors (an SMA diode package is not an
# SMA connector)
CONFLICT_REFS = {"R", "C", "L", "D", "Q", "FB", "Y", "F", "TVS", "ZD", "VR"}

DISPLAY = re.compile(r"oled|(?<![a-z])(lcd|tft|vfd)(?![a-z])|display|7_?seg|7-segment|seven.?seg|dot.?matrix|"
                     r"e.?paper|eink|nixie|ssd13\d\d|st77\d\d|hd44780|ili9\d\d\d", _I)

# 5. footprint name patterns -> class (case-insensitive). (?<![a-z]) / (?![a-z]) keep short
# tokens from matching inside longer words.
NAME_RULES = (
    ("connector", "usb", re.compile(r"usb(?!lc)", _I)),
    ("connector", "header/socket", re.compile(
        r"pin_?header|pinhd|pin_?socket|socket_strip|(?<![a-z])hdr|idc[-_]?header|box_?header", _I)),
    ("connector", "JST/Molex", re.compile(r"(?<![a-z])jst|molex|micro-?fit|pico-?blade|(?<![a-z])jwt", _I)),
    ("connector", "FPC/FFC", re.compile(r"(?<![a-z])(fpc|ffc)(?![a-z])", _I)),
    ("connector", "jack", re.compile(r"jack|switchcraft|(?<![a-z])(trs|trrs|xlr)(?![a-z])", _I)),
    ("connector", "RF", re.compile(r"(?<![a-z])(sma|smb|bnc|mmcx|mcx|u\.?fl|ipex|coax|subclick)(?![a-z])", _I)),
    ("connector", "card slot", re.compile(
        r"micro_?sd|(?<![a-z])(sd|tf)_?card|(?<![a-z])sim(?![a-z])|sim_?card|card_?edge|edge_?conn|"
        r"pci_?e(xpress)?(?![a-z])", _I)),
    ("connector", "terminal", re.compile(r"terminal_?block|screw_?terminal|(?<![a-z])(phoenix|wago)", _I)),
    ("connector", "connector", re.compile(
        r"(?<![a-z])conn?(?![a-z])|connector|rj45|rj11|rj12|8p8c|magjack|hdmi|displayport|d-?sub|"
        r"(?<![a-z])db\d\d?(?![0-9])|xt[369]0|tag-?connect|tc20[35]0|solder_?wire|wire_?pad", _I)),
    ("mounting", "hole", re.compile(
        r"mounting_?hole|mount_?hole|(?<![a-z])mtg|standoff|screw_?hole|clearance_?hole|"
        r"(?<![a-z])hole(?![a-z])|tooling_?hole", _I)),
    ("mounting", "fiducial", re.compile(r"fiducial|(?<![a-z])fid(?![a-z])", _I)),
    ("user", "switch", re.compile(
        r"(?<![a-z])sw(?![a-z])|switch|button|(?<![a-z])btn|(?<![a-z])tact|(?<![a-z])push", _I)),
    ("user", "key switch", re.compile(
        r"cherry|(?<![a-z])mx(?![a-z])|kailh|(?<![a-z])choc|gateron|keyswitch|key_?switch", _I)),
    ("user", "encoder/pot", re.compile(
        r"encoder|(?<![a-z])ec1[12]|potentiometer|(?<![a-z])pot(?![a-z])|trim_?pot", _I)),
    ("user", "display", DISPLAY),
    ("user", "buzzer", re.compile(r"buzzer|beeper|speaker", _I)),
)
# a through-hole LED (panel indicator): LED_D3.0mm, LED_D5.0mm_BigPads, LED-5MM
THT_LED_NAME = re.compile(r"led[-_]?(d?\d(\.\d)?_?mm|tht)", _I)
LED_WORD = re.compile(r"(?<![a-z])led", _I)  # not OLED
# light pipes and LED bars (bar graphs), SMD or not
LED_INDICATOR_NAME = re.compile(r"light_?pipe|lightpipe|led[-_]?bar|bar_?graph", _I)

# 6. values that are KiCad symbol names
VALUE_RULES = (
    ("connector", re.compile(r"^conn_|_receptacle|^usb_|barrel_jack|audiojack|micro_sd|^sd_card|"
                             r"^sim_card|screw_terminal|rj45|magjack", _I)),
    ("user", re.compile(r"^sw_|(?<![a-z])sw(?![a-z])|^rotary_encoder|^r_pot|^buzzer|^speaker", _I)),
    ("user", DISPLAY),
    ("mounting", re.compile(r"^mountinghole|^fiducial", _I)),
)

# 7. reference prefix -> (class, check of the footprint, what the check means)
REF_RULES = {
    "connector": ({"J", "CN", "CON", "CONN", "P", "USB"}, lambda f: f["pads"] >= 1, ">=1 pad"),
    "mounting-hole": ({"H", "MH", "HOLE", "MTG"}, lambda f: f["pth"] + f["npth"] >= 1 and _one_net(f),
                      "a drilled pad, at most one net"),
    "mounting-fid": ({"FID", "FD"}, lambda f: 1 <= f["pads"] <= 3 and f["smd"] == f["pads"],
                     "1-3 SMD pads"),
    "user": ({"SW", "S", "KSW", "BTN", "KEY", "ENC", "LS", "BZ", "BUZ", "SPK", "RST", "RESET", "BOOT"},
             lambda f: f["pads"] >= 2, ">=2 pads"),
    "user-pot": ({"RV", "POT"}, lambda f: f["pads"] >= 3, ">=3 pads"),
}


def ref_prefix(ref):
    m = re.match(r"[A-Za-z_]*", ref or "")
    return m.group(0).rstrip("_").upper()


def classify(fp):
    """fp: dict with ref, lib, name, value, pads (count), pth, npth, smd (pad counts).
    Returns (class or None, evidence)."""
    cls, evidence = _classify(fp)
    if cls == "user" and TRIM_VALUE.search(fp.get("value") or ""):
        return None, f"exclude: trimmer (value {fp['value']}; was {evidence})"
    if cls == "connector" and JUMPER_VALUE.search(fp.get("value") or ""):
        return None, f"exclude: jumper (value {fp['value']}; was {evidence})"
    if cls == "connector":
        text = " ".join(fp.get(k) or "" for k in ("name", "value", "desc"))
        if not NOT_DEBUG.search(text):
            for field in ("name", "value", "desc", "ref"):
                m = DEBUG_HEADERS.search(fp.get(field) or "")
                if m:
                    return None, f"exclude: programming/debug header ({field} {m.group(0)}; was {evidence})"
        how = _net_header(fp)
        if how:
            return None, f"exclude: programming/debug header ({how}; was {evidence})"
    return cls, evidence


def _classify(fp):
    ref, lib, name, value = fp.get("ref") or "", fp.get("lib") or "", fp.get("name") or "", fp.get("value") or ""
    prefix = ref_prefix(ref)
    if not fp["pads"]:
        return None, "exclude: no pads"
    for what, lib_re, name_re, ref_re in EXCLUDE:
        if what == "trimmer" and fp["npth"] == fp["pads"]:
            continue  # a panel hole for a trimmer is a hole (npth rule)
        if lib_re.search(lib) or name_re.search(name) or (ref_re and ref_re.match(prefix)):
            return None, f"exclude: {what}"
    if IC_SOCKET_VALUE.search(value):
        return None, "exclude: IC socket"
    for cls, rx in LIB_RULES:
        m = rx.search(lib)
        if m:
            return cls, f"lib: {lib}"
    if fp["npth"] == fp["pads"]:
        return "mounting", "npth: all pads NPTH"
    if THT_LED_NAME.search(name) and fp["pth"] >= 2:
        return "user", "name: THT LED"
    led = LED_WORD.search(f"{lib} {name}") or prefix in ("LED", "D") and LED_WORD.search(value)
    if led and 2 <= fp["pads"] <= 4 and fp["pth"] == fp["pads"]:
        return "user", "THT LED: an LED with 2-4 plated through-hole pads"
    m = LED_INDICATOR_NAME.search(name)
    if m:
        return "user", f"name: LED indicator ({m.group(0)})"
    if CONFLICT_LIBS.search(lib) or CONFLICT_NAME.search(name):
        return None, f"conflict: {lib}:{name}"
    if prefix in CONFLICT_REFS:
        return None, f"conflict: reference {prefix}"
    for cls, what, rx in NAME_RULES:
        m = rx.search(name)
        if m and (cls != "mounting" or _one_net(fp)):
            return cls, f"name: {what} ({m.group(0)})"
    if prefix == "TP":  # after the name rules: a U.FL used as an RF test port is still a connector
        return None, "exclude: test point (reference TP)"
    for cls, rx in VALUE_RULES:
        m = rx.search(value)
        if m:
            return cls, f"value: {value}"
    for key, (prefixes, check, means) in REF_RULES.items():
        if prefix in prefixes and check(fp):
            return key.split("-")[0], f"ref: {prefix} with {means}"
    return None, ""


def apply_overrides(rows, overrides):
    """rows: classify-mech rows (ref, class, evidence...). overrides: {"fix": [refs], "free": [refs]}.
    Sets row["fixed"]; returns what was applied, and references that matched no footprint."""
    overrides = overrides or {}
    fix, free = set(overrides.get("fix") or []), set(overrides.get("free") or [])
    refs = {r["ref"] for r in rows}
    for r in rows:
        r["fixed"] = r["class"] is not None
        if r["ref"] in fix:
            r["fixed"] = True
            r["evidence"] = f"override: fix ({r['evidence'] or 'unclassified'})"
            r["class"] = r["class"] or "override"
        elif r["ref"] in free:
            r["fixed"] = False
            r["evidence"] = f"override: free ({r['evidence']})"
    return dict(fix=sorted(fix & refs), free=sorted(free & refs), unknown=sorted((fix | free) - refs))
