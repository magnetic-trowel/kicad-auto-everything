# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""prius-solar-mppt: roof C60 array -> 2 x analog MPPT -> isolated LLC-DCX -> 2017 Prius Prime Li-ion pack.

Encodes designs/prius-solar-mppt/DESIGN.md (rationale, evidence tags, sources); CONNECTIONS.md
summarises the netlist this file produces. Build: `kaesynth build designs/prius-solar-mppt/design.py -v`.

Domain model (README "Domains and voltages"):
  LV    root, ref GND (bonded to chassis at the main box). PV strings, VINT bus, AUX12, logic, the
        vehicle IG/CAN wires and the pack-case NTCs (the HV battery case is chassis potential).
        Bootstrap and gate supplies float on their switch nodes (BSTA1.., DCXBST, ..); relay/fan coil
        low sides float on AUX12; the LM74700 charge pumps float on the string input.
  HV    root, ref HV_N: T301 secondary, rectifier, HV sense high sides, HV cable, D901/K901/K902 on
        the battery-end board. Floating: no Y-capacitors, no reference to chassis.
  PACK  root, ref BAT_TAP_N: the traction pack tapped on the cell side of its system main relays,
        fuses F901/F902. A separate root because K901/K902 are open whenever we are not charging.
Voltage to chassis under one insulation fault: HV and PACK nets up to 420 V / 399 V (the floating
system's full voltage); recorded on the domains, the barriers and HZ-1.
"""
import importlib.util
from pathlib import Path

from kaesynth import Design, Hole

_spec = importlib.util.spec_from_file_location("prius_solar_mppt_parts", Path(__file__).with_name("parts.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

BRIEF = (
    "I want to put solar panels on my Prius. It should take a bunch of C60s in strings and mppt them. They should "
    "fit on the top roof so you can measure the size of the roof of a 2017 Prius and shrink it a little bit for "
    "margins. It should take that raw voltage, step it up, and dump it into the battery. It should make sure that "
    "the battery can't go over voltage. It should make sure that if the wires outside of the battery are shorted, "
    "that the battery can't dump, you know, the 200 or whatever volts into it. It should make sure it doesn't "
    "overheat, so it might need a fan depending on how much current it's pushing. Or maybe it just has a bit of an "
    "aluminum heatsink.\n"
    "Follow-up 1: on the prius it must work on or off. it will have to have some smarts, and to be weak enough that "
    "the batteries can't get themselves in trouble. so that means it would have to stop charging by 80%, have a "
    "voltage clamp, it would need temp compensation, etc. also i know on older prius the pack was electrically "
    "split in two while off. check to see if that's still the case. this is a complex board. that's the point\n"
    "Follow-up 2: it's a prius prime with li-ion")

# ---- pack and thresholds (DESIGN.md 7.1 and 7.4) ----------------------------------------------
CELLS = 95                 # Toyota DM T-DM-017-D p.10 [P]
CELL_AH = 25.0             # Toyota PHV spec table [P]
V_CELL_MAX = 4.20          # assumed upper cell limit, NMC [I]
V_CELL_MIN = 3.00          # [I]
V_PACK_MAX = CELLS * V_CELL_MAX          # 399 V
V_HV_MAX = 420.0           # our HV envelope incl. the L2b double-fault ceiling
I_CAP = 0.30               # hardware charge-current cap at the pack, A (7.1)
I_HV_MAX = 0.85            # physical worst case if every limiter failed: 1.2 suns x 191.5 W / 285 V
VREF_LM4040 = 2.500
K_DIV = (6.0e6 + 12.7e3) / 12.7e3        # HV dividers 6 x 1 MOhm over 12.7 kOhm
G_AMC = 2.0                # AMC3330 gain
G_PATH1 = 15.0 / 10.0      # pack-voltage difference amplifier U402
G_PATH2 = 12.1 / 10.0      # L3 difference amplifier U422
VREF_CV = VREF_LM4040 * 39.2 / (39.2 + 1.5)
VREF_CC = VREF_LM4040 * 9.76 / (9.76 + 10.0)
VTH_OC = VREF_LM4040 * 19.1 / (19.1 + 10.0)
VTH2V0 = VREF_LM4040 * 10.0 / (10.0 + 2.49)
L1_V = CELLS * 3.95
L2_V = VREF_CV * K_DIV / (G_AMC * G_PATH1)
L3_V = VTH2V0 * K_DIV / (G_AMC * G_PATH2)
VINT_CEIL = 0.8 * (1 + 442 / 10.0)       # LM5176 FB divider (L2b)
VINT_OVP = VTH2V0 * (1 + 180 / 10.0)     # comparator ch2 (L3b)
N_DCX = 88 / 4                            # T301 Ns/Np


class Blk:
    """Thin helper: add parts with fixed refdes and connect pins to nets by name."""

    def __init__(self, d, name, title, description, board="main", domain="LV", nets=()):
        self.d = d
        self.b = d.block(name, title=title, description=description, domain=domain, board=board)
        for spec in nets:
            nm, v, kind = spec[0], spec[1], spec[2]
            kw = spec[3] if len(spec) > 3 else {}
            self.b.net(nm, v=v, kind=kind, **kw)

    def n(self, name):
        if name in self.d.nets:
            return self.d.nets[name]
        if name in self.b.nets:
            return self.b.nets[name]
        raise KeyError(f"{self.b.name}: net {name} not declared")

    def add(self, defn, ref, conns, nc=None, nc_reason="", **kw):
        p = self.b.add(defn, ref=ref, **kw)
        for pin, net in conns.items():
            self.n(net).connect(p[pin])
        if nc:
            p.nc_pins(*nc, reason=nc_reason)
        return p

    def R(self, ref, ohms, a, b, pkg="0603", prec=False, p=None, va=None, note="", **kw):
        return self.add(P.res(ohms, pkg, prec), ref, {"1": a, "2": b}, p_diss=p, v_across=va, notes=note, **kw)

    def C(self, ref, key, a, b, note="", **kw):
        return self.add(P.cap(key), ref, {"1": a, "2": b}, notes=note, **kw)


def gnet(d, name, dom, v, kind, i=None, **kw):
    return d.net(name, domain=dom, v=v, kind=kind, i_max=i, **kw)


# =============================================================================================
# Intent records

def intent(d):
    R = d.require
    R("REQ-1", "Array fits the flat part of the 2017 Prius Prime (ZVW52) roof with margins; no structural change",
      value="baseline 56 C60 cells, cell field 1016 x 889 mm (8 x 7 at 127 mm pitch); >= 40 mm to mouldings, glass "
            "and antenna", source="brief; Q-3 template", verify="V-1 template fit")
    R("REQ-2", "Cells and strings", value="Maxeon C60, 2 strings x 28 cells (electronics accept 28-40 cells/string), "
      "one bypass diode per 7-cell column", source="brief", verify="BOM, V-2")
    R("REQ-3", "Independent MPPT per string", value="2 analog channels, static tracking >= 98 %", source="brief",
      verify="V-3")
    R("REQ-4", "String voltage stays extra-low", value="Voc <= 33 V at -40 C (<= 60 V DC, ISO 6469-3 class A)",
      source="standard", verify="calc string_voc_cold, V-2")
    R("REQ-5", "Output into the Prius Prime Li-ion pack (95 cells in series, 25 Ah, 351.5 V nominal)",
      value="285-399 V, charge current <= 0.30 A (hardware cap), <= 120 W", source="Toyota DM T-DM-017-D [P]; 7.1",
      verify="V-4")
    R("REQ-6", "Charges with the car ON (READY) and OFF (parked)", value="both; no dependence on the car's ECUs",
      source="user answer Q-1, 2026-10-23", verify="V-17")
    R("REQ-7", "Weak by design: even with every firmware layer failed, the pack cannot reach a damaging state "
      "within two sunny days", value="cap 0.30 A = C/83; >= 2.1 sun-days from 80 % to 100 % SOC at the cap",
      source="user ('weak enough'); 7.1", verify="calc days_80_to_100_at_cap, V-18")
    R("REQ-8", "Stop by 80 % SOC on its own estimate", value="coulomb count (own isolated shunt) + rest-OCV "
      "correction + CAN read of the car's SOC when awake; firmware target 75 %, never above 3.95 V/cell average at "
      "rest", source="user", verify="V-18, V-23")
    R("REQ-9", "Firmware-free voltage clamp and latch", value="L2 analog CV at 4.00 V/cell avg; L3 latch at 4.12 "
      "V/cell avg (HV_P); L2b VINT ceiling; L3b VINT latch", source="user, brief", verify="V-7")
    R("REQ-10", "Temperature limits from our own pack sensors", value="4 NTCs on the HV battery case; charge 0-45 C; "
      "3.95 V/cell (0-35 C), 3.90 V/cell (35-45 C); hardware OTP at 50 C on two sensors; the car's own thermistors "
      "are not touched", source="user", verify="V-9")
    R("REQ-11", "Battery cannot feed a fault in our wiring", value="D901 blocking diode, fuse on each pole first from "
      "the pack, 2-pole disconnect K901/K902, all at the battery end", source="brief", verify="V-8")
    R("REQ-12", "Battery-end fuses", value=">= 500 VDC, breaking >= 20 kA (pack Isc ~3.3 kA)", source="derived 7.6",
      verify="datasheet")
    R("REQ-13", "PV/LV <-> HV/PACK isolation", value="reinforced; PCB creepage >= 10.0 mm, clearance >= 8.0 mm; "
      "components >= 4250 Vrms", source="IEC 60664-1 F.1/F.2/F.4 via TI SLUP419", verify="V-5")
    R("REQ-14", "Added HV insulation to chassis", value=">= 100 MOhm at 500 V; no Y-capacitors; < 1 nF HV-chassis",
      source="Toyota insulation monitor ('several hundred kOhm' = fault) [P]", verify="V-6")
    R("REQ-15", "No overheating", value="firmware derating + firmware-free OTP (T301, pack x2); Tj <= 80 % of max",
      source="brief", verify="V-9")
    R("REQ-16", "Ambient", value="-40..+85 C; full power to 60 C", source="ISO 16750-4 passenger compartment [I]",
      verify="V-10")
    R("REQ-17", "Firmware failures contained by hardware", value="window watchdog; analog CV/CC; PERMIT wired-AND; "
      "reset state = converter off, relays open, CAN transmitter off", source="derived", verify="V-11")
    R("REQ-18", "No 12 V battery drain", value="powered from PV only; IG sense < 1 mA while IG is on; CAN "
      "transceiver on our own 3.3 V", source="derived", verify="V-12")
    R("REQ-19", "CAN use is read-only diagnostics, and only while the car is awake", value="transmitter disabled in "
      "hardware unless IG is on (RS held high by Q702/Q703); no termination; requests <= 10/s", source="derived",
      verify="V-13")
    R("REQ-20", "EMC", value="CISPR 25 class 3 target", source="standard", verify="V-14")
    R("REQ-21", "HV wiring", value="orange screened >= 600 V cable, metal glands, IP67 boxes; unfused tap leads <= "
      "0.3 m, double insulated, inside the battery cover", source="ISO 6469-3 practice", verify="inspection")
    R("REQ-22", "Logging", value="faults, trips, daily Ah, SOC estimates, OCV points in EEPROM (1M cycles, wear "
      "levelled); UART log port", source="user ('smarts')", verify="V-11")
    R("REQ-23", "Reverse-connected string", value="-33 V indefinitely, no damage", source="derived", verify="V-19")
    R("REQ-24", "Output discharge after stop", value="< 60 V within 10 s", source="derived", verify="V-20")
    R("REQ-25", "Parts", value="AEC-Q where available, active lifecycle", source="task", verify="BOM")

    A = d.assume
    A("ASM-1", "Prime roof: the flat-enough area is about 1.1 m (fore-aft) x 1.1 m. Toyota covered ~0.80 m2 of "
      "cells (180 W at 22.5 %) on the same roof for the Japanese Prius PHV, leaving the curved edges bare [S]; the "
      "baseline 56-cell field (0.86 m2 of cell) assumes a similar flat area")
    A("ASM-2", "Pack cell window 3.00-4.20 V (NMC-class chemistry, 25 Ah prismatic); pack 285-399 V; the car's "
      "own full charge is ~4.10 V/cell average and its hybrid-mode floor ~3.6 V/cell [I]")
    A("ASM-3", "OCV at 80 % SOC is 3.97-4.02 V/cell for NMC; 3.95 V average at rest is <= ~78 % [I]; calibrated on "
      "the car via CAN at commissioning")
    A("ASM-4", "Pack short-circuit current ~3.3 kA (95 cells x ~1.0 mOhm + busbars ~0.12 Ohm) [I]")
    A("ASM-5", "Main box in the cargo area; battery-end box next to the HV battery under the cargo floor [P: DM "
      "shows the pack in the luggage area]")
    A("ASM-6", "LV ground (PV-, PGND) bonded to chassis at the main box (EMC); conflicts with the C60 'positive "
      "ground' note (Q-7)")
    A("ASM-7", "The HV battery case is metal at chassis potential and isolated from the cells [P: DM p.10], so "
      "NTCs bolted to it are LV parts")
    A("ASM-8", "Pack thermal mass ~70 kJ/K (95 cells x ~0.75 kg x ~1 J/gK); case-to-cabin conductance ~10 W/K "
      "with the battery fan off [I]")

    Q = d.question
    Q("Q-1", "Mode: charge only while READY, or also while parked?", blocking=True,
      answer="Both: 'on the prius it must work on or off' - user, 2026-10-23. Parked charging is core; the pack-side "
             "tap, own SOC/voltage/temperature layers and the current cap follow from it.",
      default="charge on and off")
    Q("Q-2", "Which pack?", blocking=True, answer="2017 Prius Prime (ZVW52), Li-ion - user, 2026-10-23. NiMH variant "
      "removed.", default="Prime Li-ion 95s")
    Q("Q-3", "Measure the Prime roof (template) and confirm the 8 x 7 field; any roof rack/antenna conflicts?",
      blocking=True, default="56 cells, 1016 x 889 mm field")
    Q("Q-4", "Get the 2017-2022 Prius Prime repair manual pages for the HV battery junction block: SMRB/SMRP/SMRG, "
      "CHRB/CHRG and current-sensor positions, and the cell-side tap studs. Our - tap should sit on the relay side "
      "of the car's current sensor so the battery ECU counts our current when it is awake.", blocking=True,
      default="tap the cell side of SMRB and SMRG; current-sensor position unconfirmed")
    Q("Q-5", "Who installs the pack-side tap (HV-trained technician, service-plug procedure, 10-minute wait [P]), "
      "and is the modification acceptable to insurer, registration and warranty?", blocking=True,
      default="not decided")
    Q("Q-6", "How is the array fixed to the roof (bonded flexible laminate vs rails)? Detachment at speed (HZ-9).",
      blocking=True, default="not decided")
    Q("Q-7", "C60 sheet asks for positive-ground systems [P]; we bond PV- to chassis. Accept with the polarization "
      "test V-22, or float the LV domain?", default="negative ground + V-22")
    Q("Q-8", "Fit the optional fan in hot climates?", default="no fan; finned box")
    Q("Q-9", "Custom magnetics vendor for T301 and owner of hipot/partial-discharge tests", default="open")
    Q("Q-10", "How does the Prime battery ECU re-estimate SOC after charge added while asleep, and does it set "
      "DTCs? Validate on the car (V-23) before parked charging is enabled by default.", blocking=True,
      default="firmware ships with parked charging off until V-23 passes")
    Q("Q-11", "Where in the 95-cell string does the service plug sit (it splits the pack only when removed)?",
      default="unknown; firmware refuses to charge if the pack reads < 280 V or open")

    H = d.hazard
    H("HZ-1", "Electric shock from 285-420 V on our cable or boards; up to 420 V to chassis under one insulation "
      "fault (the HV and PACK systems float)",
      "Reinforced LV/HV and LV/PACK barriers (T301, U401, U421, U441, K901/K902 coil-contact; 10 mm/8 mm PCB). "
      "Screened orange cable in metal glands; IP67 metal boxes bonded to chassis; K901/K902 open both poles when "
      "idle; output bleeds < 60 V in 10 s; labels",
      parts=["T301", "U401", "U421", "U441", "K901", "K902"], single_fault_safe=True)
    H("HZ-2", "Short in our HV cable or main board lets the pack dump kA",
      "D901 blocks pack current toward our side; F901/F902 (20 kA) are the first elements from each pole; K901/K902 "
      "open when not charging", parts=["D901", "F901", "F902", "K901", "K902"], single_fault_safe=True,
      notes="D901 shorted -> F901/F902 clear; relay welded -> D901 still blocks")
    H("HZ-3", "Pack overvoltage (cell overcharge) while the car's battery ECU sleeps",
      "L1 firmware 80 % SOC / 3.95 V avg with temperature table; L2 analog CV clamp 4.00 V avg (U802A, own reference "
      "U801); L3 AMC#2 -> U502 ch1 -> latch U503 -> PERMIT 4.12 V avg; L3b VINT latch; L2b LM5176 VINT ceiling; "
      "current cap keeps any overshoot slow (REQ-7)",
      parts=["U802", "U801", "U421", "U422", "U502", "U503", "D501", "U103", "U203", "R114", "R214"],
      single_fault_safe=True)
    H("HZ-4", "Cell imbalance pushes one cell over its limit while we charge on pack-level data",
      "Series charge is common to all cells; our stop (3.95 V avg) is below the car's own full charge (~4.10 V avg), "
      "so every cell ends lower than after a normal plug-in charge; CAN read of the car's min/max cell voltage when "
      "awake lowers the stop if the spread exceeds 50 mV; cap limits the error rate",
      parts=["U701", "U702", "U401"], single_fault_safe=True)
    H("HZ-5", "Our SOC estimate drifts high/low", "Coulomb count from U441 (0.2 % gain), rest-OCV correction each "
      "dawn, CAN SOC when awake, conservative (stop on the higher estimate); L2/L3 bound the error",
      parts=["U441", "U401"], single_fault_safe=True)
    H("HZ-6", "Car SOC estimate corrupted -> DTC or mismanagement", "Per-parking budget (<= 10 % SOC), V-23 "
      "validation, our current inside the car's sensor loop if Q-4 allows", parts=["U701", "U702", "U441"],
      notes="not single-fault safe until V-23 shows how the ECU re-estimates")
    H("HZ-7", "Insulation fault hidden, or false P0AA6 (car won't READY)", ">= 100 MOhm design; differential-only HV "
      "dividers; no Y-caps; T301 shield; megger at install; the car's monitor sees our circuit when both are on",
      parts=["T301"], single_fault_safe=True)
    H("HZ-8", "Roof array arc, hot spot or fire", "<= 33 V class A; bypass diode per 7-cell column; one string per "
      "input; ideal diode; 2.5 mm2 wire", parts=["D161", "D261", "U101", "U201"], single_fault_safe=True)
    H("HZ-9", "Array detaches at speed", "mechanical design out of scope (Q-6)", parts=[])
    H("HZ-10", "Converter overheats", "Firmware derating (RT301); comparator ch3 OTP on RT302; LM5176 TSD; metal box",
      parts=["RT302", "U502"], single_fault_safe=True)
    H("HZ-11", "Firmware hang or wild PWM", "TPS3850 window watchdog resets the MCU; MCU_RUN pulled down -> PERMIT "
      "low; analog CV/CC hold limits; DCX open loop and bounded", parts=["U504", "R519", "R518"],
      single_fault_safe=True)
    H("HZ-12", "Sensor failure masks overvoltage", "Three isolated amplifiers each pull PERMIT low on DIAG; L3 uses its "
      "own divider, AMC, amplifier and reference; L2b needs none of them", parts=["U401", "U421", "U441", "U103"],
      single_fault_safe=True)
    H("HZ-13", "Pack disconnects under load (fuse, relay)", "DCX output <= n*VINT/2 <= L2b ceiling; L3 latch; output "
      "caps only 70 mJ", parts=["U421", "U503"], single_fault_safe=True)
    H("HZ-14", "String reversed", "LM74700 + FET block reverse current", parts=["U101", "Q101", "U201", "Q201"],
      single_fault_safe=True)
    H("HZ-15", "Pack too hot/cold to charge", "Firmware 0-45 C window on 4 case NTCs; hardware OTP 50 C on two of "
      "them (U502 ch4, U506 ch2)", parts=["U502", "U506"], single_fault_safe=True)
    H("HZ-16", "Vehicle transients on IG and CAN wires", "BAS21 250 V + 22.1 kOhm 1206 on IG; CAN transceiver bus "
      "pins -7..16 V; no transmit unless IG on", parts=["D701", "U702", "Q703"], single_fault_safe=True)
    H("HZ-17", "Service: our tap is live (cell side of SMRs) and can bridge an open service plug through 6 MOhm",
      "K901/K902 open when idle; label on the battery cover; install guide: unplug J902 before pulling the service "
      "plug", parts=["K901", "K902"], notes="procedural part: labels and install guide")
    H("HZ-18", "Crash crushes the HV cable", "route away from crush zones; D901 and fuses at the battery end",
      parts=["D901", "F901", "F902"], single_fault_safe=True)
    H("HZ-19", "Our CAN node disturbs the car (bus wake, error frames)", "Transmitter physically off unless IG is on "
      "(RS forced high by Q703); unpowered transceiver is passive on the bus [P]; diagnostic requests only",
      parts=["U702", "Q702", "Q703"], single_fault_safe=True)
    H("HZ-20", "Relay coil left at 100 % (firmware) overheats the coil", "economiser PWM after 100 ms; watchdog; "
      "coil class F", parts=["U504", "U505"])


# =============================================================================================
# Domains, global nets, barriers

def domains(d):
    gnet(d, "GND", "LV", 0, "ground", 16, notes="PV-, PGND, signal ground; bonded to chassis at H701-H704")
    d.domain("LV", ref="GND", kind="elv", earthed=True,
             description="Roof strings, VINT bus, AUX, logic, IG/CAN wires, pack-case NTCs. <= 38 V (PV inputs "
                         "clamped at 54 V by TVS); ISO 7637 pulses on IGN_IN. Chassis-referenced.")
    gnet(d, "HV_N", "HV", 0, "hv", I_HV_MAX, external=True, notes="converter output -, cable core 2, to K902")
    d.domain("HV", ref="HV_N", kind="hv",
             description="T301 secondary, rectifier, HV sense high sides, HV cable, D901/K901/K902. 0-420 V internal. "
                         "Floating: under one insulation fault any HV net can be at 0..420 V to chassis.")
    gnet(d, "BAT_TAP_N", "PACK", 0, "hv", I_HV_MAX, external=True, notes="Prime pack - (cell side of SMRG)")
    d.domain("PACK", ref="BAT_TAP_N", kind="battery",
             description="Prius Prime Li-ion pack, 95s, 285-399 V, tapped on the cell side of the system main relays. "
                         "Floats with the car's IT system: under one insulation fault a pole can be 399 V from chassis.")
    # LV globals
    gnet(d, "VINT", "LV", (0, 38), "power", 8, notes="intermediate bus 26-36 V running; LM5176 ceiling 36.2 V")
    gnet(d, "AUX12", "LV", (0, 12.5), "power", 0.6, notes="gate drive, relays, comparators, references")
    gnet(d, "AUX_IN", "LV", (0, 38), "power", 0.6, notes="OR of PV A, PV B and VINT")
    gnet(d, "+3V3", "LV", (0, 3.4), "power", 0.35)
    gnet(d, "+3V3A", "LV", (0, 3.4), "power", 0.02, notes="MCU AVDD")
    for X in "AB":
        gnet(d, f"PV{X}_IN", "LV", (-33, 33), "power", 7.5, external=True,
             threats=("reverse_polarity", "surge", "esd"), notes=f"string {X} + at J{1 if X == 'A' else 2}01")
        gnet(d, f"PV{X}_P", "LV", (0, 33), "power", 7.5, notes=f"string {X} after the ideal diode")
        gnet(d, f"PV{X}_VDIV", "LV", (0, 3.3), "analog", notes="PV voltage / 12 to MCU and the PV loop")
        gnet(d, f"PV{X}_I_ADC", "LV", (0, 3.3), "analog", notes="PV current 0.25 V/A")
        gnet(d, f"MPPT_{X}_PWM", "LV", (0, 3.3), "signal", notes="MCU setpoint PWM; default high = zero power")
    for nm in ["LIM", "HV_V_ADC", "HV_V2_ADC", "HV_V_OVP", "HV_V_LIM", "I_HV_ADC", "I_HV_LIM", "I_HV_OCP",
               "VINT_DIV", "NTC_HS", "NTC_T1", "NTC_P3", "NTC_P4", "VREF2V5", "VTH2V0", "VTH_OTP", "VTH_OC",
               "LIM_ADC", "AUX12_DIV"]:
        gnet(d, nm, "LV", (0, 3.3), "analog")
    for nm in ["NTC_P1", "NTC_P2"]:
        gnet(d, nm, "LV", (0, 3.3), "analog", external=True, notes="pack-case NTC via J706 (comparator + ADC)")
    for nm in ["OVP_TRIP_N", "LATCH_Q", "LATCH_QN", "PERMIT", "MCU_RUN", "RESET_N", "MCLR_N", "WDI", "RELAY_REQ",
               "K_IN", "FAN_PWM", "DCX_HI", "DCX_LI", "READY_N", "CAN_TX", "CAN_RX", "CAN_EN", "EE_SCK", "EE_SO",
               "EE_SI", "EE_CS_N", "UART_TX", "PGD", "PGC", "PERMIT_SNS"]:
        gnet(d, nm, "LV", (0, 3.4), "signal")
    for coil, dom in (("K1_COIL_N", "K1C"), ("K2_COIL_N", "K2C"), ("FAN_N", "FANC")):
        d.domain(dom, ref="AUX12", kind="elv", description=f"{coil}: low side of an inductive load on AUX12; "
                                                            "clamped to AUX12 + 0.7 V by the TPL7407 COM diodes")
        gnet(d, coil, dom, (-12.5, 0.7), "power", 0.3 if coil != "FAN_N" else 0.3)
    gnet(d, "IGN_CAR", "LV", (-150, 112), "signal", 0.01, external=True, notes="car IG2-switched fuse socket")
    gnet(d, "IGN_IN", "LV", (-150, 112), "signal", 0.01, external=True, notes="IG feed after the 1 A tap fuse")
    gnet(d, "CAN_H", "LV", (-2, 7), "diff", external=True, notes="OBD-II pin 6 (no termination here)")
    gnet(d, "CAN_L", "LV", (-2, 7), "diff", external=True, notes="OBD-II pin 14")
    # HV globals
    gnet(d, "HV_P", "HV", (0, V_HV_MAX), "hv", I_HV_MAX, external=True, notes="converter output +, cable core 1")
    gnet(d, "HV_RTN", "HV", (-0.07, 0.07), "hv", I_HV_MAX, notes="rectifier return; HV_N - I x 0.1 Ohm")
    gnet(d, "PACK_SNS", "HV", (0, V_HV_MAX), "hv", 0.001, external=True,
         notes="pack + through 3 MOhm at the battery end; cable core 3")
    # PACK globals
    gnet(d, "BAT_TAP_P", "PACK", (0, V_PACK_MAX), "hv", I_HV_MAX, external=True, notes="pack + (cell side of SMRB)")

    sp = ("IEC 60664-1 via TI SLUP419 Tables (docs/topics/rules/isolation-creepage.md): F.4 PD2 material group III "
          "400 V row = 4.0 mm basic [P]; 500 V row = 5.0 mm basic [S]; working voltage 420 V -> 500 V row -> 10.0 mm "
          "reinforced. F.1 <= 600 V OVC II = 4 kV basic, reinforced one step up = 6 kV -> F.2 5.5 mm; design 8.0 mm "
          "(matches the G9KB coil-contact clearance). AC test = 6 kV peak / sqrt 2 = 4.24 kVrms")
    for a, b, vw in (("LV", "HV", V_HV_MAX), ("LV", "PACK", V_PACK_MAX)):
        d.barrier(a, b, grade="reinforced", v_work=vw, creepage_mm=10.0, clearance_mm=8.0,
                  standard="IEC 60664-1 Tables F.1, F.2, F.4", v_test_rms=4250, pollution_degree=2,
                  material_group="IIIa", ovc="II", slot=True, source=sp,
                  notes="routed slot >= 2 mm wide under T301, U401, U421, U441; no copper on any layer in the band; "
                        "isolator packages are material group I (5.0 mm needed, 8 mm provided) with the slot "
                        "giving the PCB path")
    d.barrier("HV", "PACK", grade="functional", v_work=V_PACK_MAX, creepage_mm=5.0, clearance_mm=5.0,
              standard="IPC-2221B Table 6-1 B2 (301-500 V: 2.5 mm; >500 V: +0.005 mm/V)", pollution_degree=2,
              source="IPC-2221B B2 via docs/topics/rules/isolation-creepage.md [S]; 5.0 mm also covers the 820 V "
                     "transient case (4.1 mm) when the converter runs with the relays open (fault)",
              notes="normal: relays open only with the converter stopped, so our side is unpowered and <= 400 V "
                    "appears across an open contact; G9KB open contact 600 V / 2500 VAC")
    float_doms = [("IDA", "PVA_IN", "LM74700 A charge pump (VCAP, GATE) above the string A input"),
                  ("IDB", "PVB_IN", "LM74700 B charge pump above the string B input")]
    for name, ref, desc in float_doms:
        d.domain(name, ref=ref, kind="elv", description=desc)


# =============================================================================================
# Blocks

def mppt(d, X, base):
    def r(k):
        return f"{k + base}"
    bst1, bst2 = f"BST{X}1", f"BST{X}2"
    b = Blk(d, f"MPPT_{X}", f"MPPT {X}: string {X} input, PV sense, LM5176 buck-boost, analog PV-voltage loop",
            f"String {X} (28 C60 cells) -> ideal diode -> 5 mOhm shunt -> 4-switch buck-boost into VINT. The PV "
            f"voltage is regulated to 12 x VSET by U{r(4)}; VSET comes from the MCU PWM or from the limiter (LIM) "
            f"through D{base + 5}, whichever is higher.",
            nets=[("VIN", (0, 33), "power", {"i_max": 7.5}), ("ISK_P", (0, 33), "sense"), ("ISK_N", (0, 33), "sense"),
                  ("ISNS_P", (0, 33), "sense"), ("ISNS_N", (0, 33), "sense"), ("INA_P", (0, 33), "sense"),
                  ("INA_N", (0, 33), "sense"), ("I_RAW", (0, 3.3), "analog"), ("SINK_B", (0, 3.3), "analog"),
                  ("SINK_E", (0, 2.7), "analog"), ("MPPT_OUT", (0, 3.3), "analog"), ("EN", (0, 3.0), "signal"),
                  ("VINF", (0, 33), "power", {"i_max": 0.07}), ("VISNS", (0, 33), "sense"),
                  ("MODE", (0, 3.3), "analog"), ("DITH", (0, 3.3), "analog"), ("RT", (0, 3.3), "analog"),
                  ("SLOPE", (0, 3.3), "analog"), ("SS", (0, 1.25), "analog"), ("COMP", (0, 3.0), "analog"),
                  ("COMP_RC", (0, 3.0), "analog"), ("FB", (0, 1.0), "analog"), ("CS", (-0.2, 0.2), "sense"),
                  ("CSG", (-0.2, 0.2), "sense"), ("CS_K", (-0.2, 0.2), "sense"), ("CSG_K", (-0.2, 0.2), "sense"),
                  ("SRC", (-0.1, 0.2), "power", {"i_max": 7.5}), ("SW1", (-1, 33), "switching", {"i_max": 7.5}),
                  ("SW2", (-1, 38), "switching", {"i_max": 7.5}), ("LD1", (0, 8), "signal"),
                  ("LD1_G", (0, 8), "signal"), ("LD2", (0, 8), "signal"), ("LD2_G", (0, 8), "signal"),
                  ("VCC", (0, 7.6), "power", {"i_max": 0.065}), ("BIAS", (0, 12.5), "power", {"i_max": 0.04}),
                  ("AGND", 0, "ground"), ("INT_N", (0, 3.3), "analog"), ("PI", (0, 3.3), "analog"),
                  ("VSET1", (0, 3.3), "analog"), ("VSET", (0, 3.3), "analog"),
                  ("VCAP", (0, 13.9), "signal", {"domain": f"ID{X}"}), ("IDG", (0, 13.9), "signal", {"domain": f"ID{X}"})])
    d.domain(bst1, ref=f"MPPT_{X}/SW1", kind="elv", description=f"high-side gate supply riding on MPPT_{X}/SW1")
    d.domain(bst2, ref=f"MPPT_{X}/SW2", kind="elv", description=f"high-side gate supply riding on MPPT_{X}/SW2")
    for nm, dom in (("BT1", bst1), ("HD1", bst1), ("HD1_G", bst1), ("BT2", bst2), ("HD2", bst2), ("HD2_G", bst2)):
        b.b.net(nm, v=(0, 7.6), kind="signal", domain=dom)
    PIN, PP = f"PV{X}_IN", f"PV{X}_P"
    b.add(P.J_PV, f"J{r(1)}", {"1": PIN, "2": "GND"}, i_through=7.5,
          notes=f"string {X} input; plug MSTB 2,5/2-ST-5,08; i_through: carries only its own string current")
    b.add(P.TVS39, f"D{r(1)}", {"K": PIN, "A": "GND"}, notes="string surge/ESD clamp (54 V at 11 A)")
    b.C(f"C{r(1)}", "100n100V", "VCAP", PIN, note="LM74700 charge-pump cap (VCAP-ANODE)")
    b.add(P.LM74700, f"U{r(1)}", {"VCAP": "VCAP", "GND": "GND", "EN": PIN, "CATHODE": PP, "GATE": "IDG",
                                   "ANODE": PIN}, notes="reverse-polarity ideal diode controller")
    b.add(P.IAUC, f"Q{r(1)}", {"S": PIN, "G": "IDG", "D": PP}, notes="ideal-diode FET: S = string, D = output")
    b.C(f"C{r(2)}", "100n100V", PP, "GND", note="LM74700 CATHODE cap")
    b.add(P.SHUNT_5M, f"R{r(1)}", {"I+": PP, "S+": "ISK_P", "S-": "ISK_N", "I-": "VIN"}, p_diss=0.28,
          notes="PV shunt; Kelvin taps to U2 and the LM5176 CC loop (0.28 W at 7.5 A)")
    b.add(P.INA186, f"U{r(2)}", {"GND": "GND", "OUT": "I_RAW", "VS": "+3V3", "IN-": "INA_N", "IN+": "INA_P"},
          notes="PV current 50 V/V -> 0.25 V/A")
    b.R(f"R{r(31)}", 10e3, "ISK_P", "INA_P", p=0.01, va=12, note="limits INA186 input current < 5 mA when the TVS "
        "clamps at 54 V (DS note 3); v_across: only the INA186 clamp overdrive (54-42 V) appears across it")
    b.R(f"R{r(32)}", 10e3, "ISK_N", "INA_N", p=0.01, va=12, note="matched with R{0}31".format(base // 100))
    b.C(f"C{r(3)}", "100n100V", "+3V3", "GND", note="U2 VS")
    b.R(f"R{r(2)}", 1e3, "I_RAW", f"PV{X}_I_ADC", note="ADC anti-alias")
    b.C(f"C{r(4)}", "10n50V", f"PV{X}_I_ADC", "GND")
    b.R(f"R{r(3)}", 1e3, "ISK_P", "ISNS_P", p=0.001, va=0.2,
        note="R_iso: Q2 sinks <= 150 uA through it (0.15 V) to offset the CC-loop sense")
    b.R(f"R{r(4)}", 100, "ISK_N", "ISNS_N", p=0.001, va=0.01, note="CC-loop sense filter; carries only the 3 uA "
        "ISNS bias")
    b.C(f"C{r(5)}", "100n100V", "ISNS_P", "ISNS_N", note="CC-loop differential filter")
    b.add(P.NPN_HV, f"Q{r(2)}", {"B": "SINK_B", "E": "SINK_E", "C": "ISNS_P"}, notes="MPPT current-setpoint sink")
    b.R(f"R{r(5)}", 20e3, "SINK_E", "GND", note="sink emitter")
    b.R(f"R{r(6)}", 10e3, "MPPT_OUT", "SINK_B", note="sink base")
    b.C(f"C{r(6)}", "4u7100V", "VIN", "GND", note="buck-side hot-loop input cap")
    b.C(f"C{r(7)}", "4u7100V", "VIN", "GND", note="buck-side hot-loop input cap")
    b.add(P.cap("100u63V"), f"C{r(8)}", {"1": "VIN", "2": "GND"}, notes="input bulk (polymer hybrid)")
    b.add(P.LM5176, f"U{r(3)}", {
        "EN/UVLO": "EN", "VIN": "VINF", "VISNS": "VISNS", "MODE": "MODE", "DITH": "DITH", "RT/SYNC": "RT",
        "SLOPE": "SLOPE", "SS": "SS", "COMP": "COMP", "AGND": "AGND", "FB": "FB", "VOSNS": "VINT",
        "ISNS-": "ISNS_N", "ISNS+": "ISNS_P", "CSG": "CSG", "CS": "CS", "SW2": "SW2", "HDRV2": "HD2", "BOOT2": "BT2",
        "LDRV2": "LD2", "PGND": "GND", "VCC": "VCC", "BIAS": "BIAS", "LDRV1": "LD1", "BOOT1": "BT1", "HDRV1": "HD1",
        "SW1": "SW1", "PAD": "AGND"}, nc=["PGOOD"],
        nc_reason="PGOOD unused: open-drain status output, may be left open (DS SNVSB46B Table 5-1)",
        notes="4-switch buck-boost, string -> VINT")
    b.R(f"R{r(7)}", 1.5e6, "VIN", "EN", note="UVLO top: on 11.6 V, off 6.9 V; high value so EN back-feeds PERMIT "
        "<= 22 uA through D2")
    b.R(f"R{r(8)}", 137e3, "EN", "AGND", note="UVLO bottom")
    b.C(f"C{r(29)}", "10n50V", "EN", "AGND", note="EN filter")
    b.add(P.BAT46, f"D{r(2)}", {"K": "PERMIT", "A": "EN"}, notes="PERMIT low pulls EN/UVLO below 0.55 V (shutdown)")
    b.R(f"R{r(9)}", 10, "VIN", "VINF", p=0.05, va=0.7, note="VIN filter; <= 65 mA VCC load -> 0.65 V, 42 mW")
    b.C(f"C{r(9)}", "100n100V", "VINF", "AGND")
    b.R(f"R{r(10)}", 2e3, "VIN", "VISNS", p=0.001, va=0.1, note="VISNS series R (TI: required > 40 V)")
    b.R(f"R{r(11)}", 93.1e3, "MODE", "AGND", note="CCM, hiccup enabled")
    b.C(f"C{r(10)}", "47n50V", "DITH", "AGND", note="dither")
    b.R(f"R{r(12)}", 41.2e3, "RT", "AGND", note="fsw 201 kHz")
    b.C(f"C{r(11)}", "680p50V", "SLOPE", "AGND", note="slope compensation")
    b.C(f"C{r(12)}", "100n100V", "SS", "AGND", note="soft start 16 ms; the CC loop acts on SS")
    b.R(f"R{r(13)}", 10e3, "COMP", "COMP_RC", note="Rc1 (tune by simulation, V-21)")
    b.C(f"C{r(13)}", "47n50V", "COMP_RC", "AGND", note="Cc1")
    b.C(f"C{r(14)}", "1n50V", "COMP", "AGND", note="Cc2")
    b.R(f"R{r(14)}", 442e3, "VINT", "FB", pkg="1206", prec=True,
        note=f"FB top: L2b VINT ceiling {VINT_CEIL:.2f} V (pack ~{N_DCX / 2 * VINT_CEIL - 1.6:.0f} V no-load)")
    b.R(f"R{r(15)}", 10e3, "FB", "AGND", prec=True, note="FB bottom")
    b.add(P.SHUNT_10M, f"R{r(16)}", {"I+": "SRC", "S+": "CS_K", "S-": "CSG_K", "I-": "GND"}, p_diss=0.33,
          notes="cycle-by-cycle sense in the low-side source path; boost mode carries D x I_L: 7.5 A^2 x 0.6 x 10 mOhm = 0.33 W")
    b.R(f"R{r(17)}", 100, "CS_K", "CS", note="CS filter")
    b.R(f"R{r(18)}", 100, "CSG_K", "CSG", note="CSG filter")
    b.C(f"C{r(15)}", "47p50V", "CS", "CSG", note="CS filter")
    b.R(f"R{r(19)}", 2.2, "HD2", "HD2_G", p=0.05, va=8, note="gate R QH2 (gate charge loss, <= 50 mW)")
    b.C(f"C{r(16)}", "100n100V", "BT2", "SW2", note="bootstrap 2")
    b.add(P.BAT46, f"D{r(3)}", {"K": "BT2", "A": "VCC"}, notes="bootstrap diode 2")
    b.R(f"R{r(20)}", 2.2, "LD2", "LD2_G", p=0.05, va=8, note="gate R QL2")
    b.C(f"C{r(17)}", "1u25V", "VCC", "GND", note="VCC bypass")
    b.R(f"R{r(21)}", 10, "AUX12", "BIAS", p=0.02, va=0.4, note="BIAS from AUX12 (VCC from BIAS above 8 V); <= 40 mA")
    b.C(f"C{r(18)}", "100n100V", "BIAS", "GND")
    b.R(f"R{r(22)}", 2.2, "LD1", "LD1_G", p=0.05, va=8, note="gate R QL1")
    b.C(f"C{r(19)}", "100n100V", "BT1", "SW1", note="bootstrap 1")
    b.add(P.BAT46, f"D{r(4)}", {"K": "BT1", "A": "VCC"}, notes="bootstrap diode 1")
    b.R(f"R{r(23)}", 2.2, "HD1", "HD1_G", p=0.05, va=8, note="gate R QH1")
    b.add(P.IAUC, f"Q{r(3)}", {"S": "SW1", "G": "HD1_G", "D": "VIN"}, notes="QH1 buck high side", p_diss=1.0)
    b.add(P.IAUC, f"Q{r(4)}", {"S": "SRC", "G": "LD1_G", "D": "SW1"}, notes="QL1 buck low side", p_diss=1.0)
    b.add(P.IAUC, f"Q{r(5)}", {"S": "SW2", "G": "HD2_G", "D": "VINT"}, notes="QH2 boost synchronous rectifier",
          p_diss=1.0)
    b.add(P.IAUC, f"Q{r(6)}", {"S": "SRC", "G": "LD2_G", "D": "SW2"}, notes="QL2 boost switch", p_diss=1.0)
    b.add(P.L_MPPT, f"L{r(1)}", {"1": "SW1", "2": "SW2"}, notes="buck-boost inductor 22 uH")
    for k in range(20, 24):
        b.C(f"C{r(k)}", "4u7100V", "VINT", "GND", note="boost-side hot-loop output cap")
    b.add(P.NETTIE, f"NT{r(1)}", {"1": "AGND", "2": "GND"}, notes="single AGND-PGND tie under the PowerPAD")
    b.R(f"R{r(24)}", 110e3, "VIN", f"PV{X}_VDIV", note="PV divider 1/12")
    b.R(f"R{r(25)}", 10e3, f"PV{X}_VDIV", "GND", prec=True, note="PV divider bottom")
    b.C(f"C{r(24)}", "10n50V", f"PV{X}_VDIV", "GND")
    b.add(P.TLV9001, f"U{r(4)}", {"OUT": "MPPT_OUT", "V-": "GND", "IN+": "VSET", "IN-": "INT_N", "V+": "+3V3"},
          notes="PV-voltage regulator (PI)")
    b.R(f"R{r(26)}", 100e3, f"PV{X}_VDIV", "INT_N", note="integrator input")
    b.C(f"C{r(25)}", "100n100V", "INT_N", "PI", note="integrator C")
    b.R(f"R{r(27)}", 10e3, "PI", "MPPT_OUT", note="PI zero")
    b.C(f"C{r(26)}", "100n100V", "+3V3", "GND", note="op-amp decoupling")
    b.R(f"R{r(28)}", 10e3, f"MPPT_{X}_PWM", "VSET1", note="setpoint PWM filter stage 1")
    b.C(f"C{r(27)}", "1u25V", "VSET1", "GND")
    b.R(f"R{r(29)}", 10e3, "VSET1", "VSET", note="setpoint PWM filter stage 2")
    b.C(f"C{r(28)}", "1u25V", "VSET", "GND")
    b.R(f"R{r(30)}", 100e3, "+3V3", f"MPPT_{X}_PWM", note="default high = setpoint above Voc = zero current")
    b.add(P.BAT46, f"D{r(5)}", {"A": "LIM", "K": "VSET"},
          notes="limiter override: VSET >= LIM - 0.3 V, so the analog CV/CC limiter can cut power without firmware")
    return b


def dcx(d):
    b = Blk(d, "DCX", "VINT bus and LLC-DCX: half-bridge, T301 (1:22), rectifier, HV output",
            "Fixed-ratio resonant DC transformer: HV = 11 x VINT (no-load). Open loop; power is set by the MPPT stages. "
            "T301 is the reinforced LV/HV barrier.",
            nets=[("HB_SW", (-1, 38), "switching", {"i_max": 8}), ("MID", (-2, 40), "switching", {"i_max": 8}),
                  ("LO", (0, 12.5), "signal"), ("LO_G", (0, 12.5), "signal"), ("HI_F", (0, 3.4), "signal"),
                  ("LI_F", (0, 3.4), "signal"),
                  ("T1_S1", (-1.5, V_HV_MAX + 1.5), "switching", {"i_max": I_HV_MAX, "domain": "HV"}),
                  ("T1_S2", (-1.5, V_HV_MAX + 1.5), "switching", {"i_max": I_HV_MAX, "domain": "HV"}),
                  ("T1_SNB", (0, V_HV_MAX), "hv", {"domain": "HV"})])
    d.domain("DCXBST", ref="DCX/HB_SW", kind="elv", description="UCC27282 high-side supply riding on HB_SW")
    for nm in ("DCX_HB", "HO", "HO_G"):
        b.b.net(nm, v=(0, 12.5), kind="signal", domain="DCXBST")
    b.add(P.cap("100u63V"), "C301", {"1": "VINT", "2": "GND"}, notes="VINT bulk")
    b.add(P.cap("100u63V"), "C302", {"1": "VINT", "2": "GND"}, notes="VINT bulk")
    for k in range(303, 311):
        b.C(f"C{k}", "4u7100V", "VINT", "GND", note="half-bridge DC-link MLCC (hot loop with Q301/Q302)")
    b.add(P.IAUC, "Q301", {"S": "HB_SW", "G": "HO_G", "D": "VINT"}, notes="half-bridge high side", p_diss=0.6)
    b.add(P.IAUC, "Q302", {"S": "GND", "G": "LO_G", "D": "HB_SW"}, notes="half-bridge low side", p_diss=0.6)
    b.add(P.UCC27282, "U301", {"VDD": "AUX12", "HB": "DCX_HB", "HO": "HO", "HS": "HB_SW", "EN": "PERMIT",
                               "HI": "HI_F", "LI": "LI_F", "VSS": "GND", "LO": "LO", "PAD": "GND"},
          notes="half-bridge driver; EN = PERMIT; internal bootstrap diode")
    b.C("C311", "1u25V", "AUX12", "GND", note="U301 VDD bulk")
    b.C("C312", "100n100V", "AUX12", "GND", note="U301 VDD HF")
    b.C("C313", "1n50V", "PERMIT", "GND", note="EN filter")
    b.C("C314", "1u25V", "DCX_HB", "HB_SW", note="bootstrap HB-HS")
    b.R("R301", 2.2, "HO", "HO_G", p=0.05, va=12.5, note="gate R high side")
    b.R("R302", 2.2, "LO", "LO_G", p=0.05, va=12.5, note="gate R low side")
    b.R("R303", 100, "DCX_HI", "HI_F", p=0.001, note="input filter (100 pF at 95 kHz: 0.1 mW)")
    b.C("C315", "100p50V", "HI_F", "GND")
    b.R("R304", 100, "DCX_LI", "LI_F", p=0.001, note="input filter")
    b.C("C316", "100p50V", "LI_F", "GND")
    for k in range(317, 333):
        b.C(f"C{k}", "100nC0G", "VINT", "MID", note="resonant split cap, upper leg (16 x 100 nF)")
    for k in range(333, 349):
        b.C(f"C{k}", "100nC0G", "MID", "GND", note="resonant split cap, lower leg (16 x 100 nF)")
    b.add(P.T_DCX, "T301", {"P_START": "HB_SW", "P_END": "MID", "S_START": "T1_S1", "S_END": "T1_S2"},
          notes="reinforced LV/HV barrier; n = 22; pins 5-10, 12-19 have no pad", p_diss=1.5)
    b.add(P.D_HV, "D301", {"A": "T1_S1", "K": "HV_P"}, notes="bridge upper", p_diss=0.3)
    b.add(P.D_HV, "D302", {"A": "T1_S2", "K": "HV_P"}, notes="bridge upper", p_diss=0.3)
    b.add(P.D_HV, "D303", {"A": "HV_RTN", "K": "T1_S1"}, notes="bridge lower", p_diss=0.3)
    b.add(P.D_HV, "D304", {"A": "HV_RTN", "K": "T1_S2"}, notes="bridge lower", p_diss=0.3)
    b.R("R305", 100, "T1_S1", "T1_SNB", pkg="1206", dnp=True, p=0.1, va=50,
        note="secondary RC snubber, DNP; fitted only if V-21 shows ringing (then 0.1 W at 220 pF x 420 V^2 x 190 kHz /2)")
    b.C("C349", "220p630V", "T1_SNB", "T1_S2", dnp=True, note="secondary RC snubber, DNP")
    for k in range(350, 358):
        b.C(f"C{k}", "100n630V", "HV_P", "HV_RTN", note="HV output cap (8 x 100 nF 630 V)")
    b.add(P.J_HV3, "J301", {"1": "HV_P", "2": "HV_N", "3": "PACK_SNS"},
          notes="HV out to the battery-end board J901 (orange 3-core cable, EMC gland)")
    b.R("R307", 191e3, "VINT", "VINT_DIV", note="VINT ADC divider 1/20.1")
    b.R("R308", 10e3, "VINT_DIV", "GND", prec=True)
    b.C("C358", "10n50V", "VINT_DIV", "GND")
    b.add(P.NTC_BOARD, "RT301", {"1": "NTC_HS", "2": "GND"}, notes="firmware temperature at Q301/Q302")
    b.R("R309", 10e3, "+3V3A", "NTC_HS", prec=True, note="ratiometric to AVDD")
    b.C("C359", "10n50V", "NTC_HS", "GND")
    b.add(P.NTC_BOARD, "RT302", {"1": "NTC_T1", "2": "GND"}, notes="hardware OTP sensor between T301 and Q301")
    b.R("R310", 2.2e3, "VREF2V5", "NTC_T1", prec=True, note="NTC pull-up from the 2.5 V reference")
    b.C("C360", "10n50V", "NTC_T1", "GND")
    return b


def amc_path(b, ref_u, h, hgnd, inp, inn, diag="PERMIT"):
    """Isolated amplifier U (AMC3330/3302) with the TI decoupling set, nets prefixed h."""
    u = b.add(P.AMC3302 if h == "H3" else P.AMC3330, ref_u, {
        "DCDC_OUT": f"{h}_DCDC", "DCDC_HGND": hgnd, "HLDO_IN": f"{h}_DCDC", "HLDO_OUT": f"{h}_HLDO",
        "INP": inp, "INN": inn, "HGND": hgnd, "GND": "GND", "OUTN": f"{h}_OUTN", "OUTP": f"{h}_OUTP", "VDD": "+3V3",
        "LDO_OUT": f"{h}_LDO", "DIAG": diag, "DCDC_GND": "GND", "DCDC_IN": f"{h}_LDO"},
        notes="isolated amplifier; DIAG (open drain) pulls PERMIT low on a high-side supply fault")
    return u


def hvsense(d):
    nets = []
    for h in ("H1", "H2", "H3"):
        nets += [(f"{h}_DCDC", (0, 4.5), "power", {"domain": "HV"}), (f"{h}_HLDO", (0, 3.6), "power", {"domain": "HV"}),
                 (f"{h}_LDO", (0, 3.6), "power"), (f"{h}_OUTP", (0, 3.3), "analog"), (f"{h}_OUTN", (0, 3.3), "analog"),
                 (f"{h}_DA_P", (0, 3.3), "analog"), (f"{h}_DA_N", (0, 3.3), "analog"),
                 (f"{h}_DA_OUT", (0, 3.3), "analog")]
    nets += [("S1A", (0, V_HV_MAX), "hv", {"domain": "HV"}), ("S1B", (0, V_HV_MAX), "hv", {"domain": "HV"}),
             ("HVS1_INP", (0, 1.0), "analog", {"domain": "HV"}), ("HVS2_INP", (0, 1.0), "analog", {"domain": "HV"}),
             ("I_SP", (-0.1, 0.1), "sense", {"domain": "HV"}), ("I_SN", (-0.1, 0.1), "sense", {"domain": "HV"}),
             ("H3_INP", (-0.1, 0.1), "sense", {"domain": "HV"}), ("H3_INN", (-0.1, 0.1), "sense", {"domain": "HV"})]
    nets += [(f"S2{c}", (0, V_HV_MAX), "hv", {"domain": "HV"}) for c in "ABCDE"]
    b = Blk(d, "HVSENSE", "HV sensing: pack voltage (path 1), output voltage (path 2, L3), charge current",
            "Three reinforced isolated amplifiers. Path 1 reads the pack through the battery-end string R902-R904 and "
            "the cable's sense core (exact rest OCV with the converter off). Path 2 reads HV_P for the L3 latch. "
            "U441 reads the 0.1 Ohm return shunt for coulomb counting, the CC limiter and the OC latch.", nets=nets)
    hv_r = dict(pkg="1206", prec=True, p=0.006, va=75)
    # path 1: pack voltage (3 MOhm here + 3 MOhm at the battery end)
    b.R("R401", 1e6, "PACK_SNS", "S1A", note="pack divider top (main-board half); v_across: 1/6 of <= 420 V", **hv_r)
    b.R("R402", 1e6, "S1A", "S1B", note="pack divider top", **hv_r)
    b.R("R403", 1e6, "S1B", "HVS1_INP", note="pack divider top", **hv_r)
    b.R("R407", 12.7e3, "HVS1_INP", "HV_N", prec=True, note=f"divider bottom: ratio {K_DIV:.1f}")
    b.C("C401", "1n50V", "HVS1_INP", "HV_N", note="input filter")
    amc_path(b, "U401", "H1", "HV_N", "HVS1_INP", "HV_N")
    # path 2: HV_P for L3
    prev = "HV_P"
    for k, nxt in zip(range(421, 427), ["S2A", "S2B", "S2C", "S2D", "S2E", "HVS2_INP"]):
        b.R(f"R{k}", 1e6, prev, nxt, note="HV_P divider top (6 x 1 MOhm); also the output bleeder", **hv_r)
        prev = nxt
    b.R("R427", 12.7e3, "HVS2_INP", "HV_N", prec=True, note="divider bottom")
    b.C("C421", "1n50V", "HVS2_INP", "HV_N", note="input filter")
    amc_path(b, "U421", "H2", "HV_N", "HVS2_INP", "HV_N")
    # current
    b.add(P.SHUNT_100M, "R441", {"I+": "HV_N", "S+": "I_SP", "S-": "I_SN", "I-": "HV_RTN"}, p_diss=0.05,
          notes="charge-current shunt in the HV return; 30 mV at the 0.30 A cap")
    b.R("R442", 10, "I_SP", "H3_INP", p=0.001, va=0.01, note="AMC3302 input filter (TI: 10 Ohm)")
    b.R("R443", 10, "I_SN", "H3_INN", p=0.001, va=0.01, note="AMC3302 input filter")
    b.C("C441", "10n50V", "H3_INP", "H3_INN", note="differential filter, fc 800 kHz")
    amc_path(b, "U441", "H3", "HV_RTN", "H3_INP", "H3_INN")
    for h, base in (("H1", 402), ("H2", 422), ("H3", 442)):
        hg = "HV_RTN" if h == "H3" else "HV_N"
        b.C(f"C{base}", "1u25V", f"{h}_DCDC", hg, note="DCDC_OUT bulk (TI C2)")
        b.C(f"C{base + 1}", "1n50V", f"{h}_DCDC", hg, note="DCDC_OUT HF (TI C3)")
        b.C(f"C{base + 2}", "100n100V", f"{h}_DCDC", hg, note="HLDO_IN (TI C1)")
        b.C(f"C{base + 3}", "100n100V", f"{h}_HLDO", hg, note="HLDO_OUT (TI C5)")
        b.C(f"C{base + 4}", "1n50V", f"{h}_HLDO", hg, note="HLDO_OUT HF (TI C6)")
        b.C(f"C{base + 5}", "100n100V", f"{h}_LDO", "GND", note="DCDC_IN (TI C4)")
        b.C(f"C{base + 6}", "1n50V", "+3V3", "GND", note="VDD HF (TI C8)")
        b.C(f"C{base + 7}", "1u25V", "+3V3", "GND", note="VDD bulk (TI C9)")
    # difference amplifiers
    for h, u, base, rf, note in (("H1", "U402", 408, 15e3, "G = 1.5: pack/157.8 to ADC and the CV limiter"),
                                 ("H2", "U422", 428, 12.1e3, "G = 1.21: L3 trip at 391 V"),
                                 ("H3", "U442", 444, 10e3, "G = 1: 4.1 V/A")):
        b.add(P.TLV9001, u, {"OUT": f"{h}_DA_OUT", "V-": "GND", "IN+": f"{h}_DA_P", "IN-": f"{h}_DA_N",
                             "V+": "+3V3"}, notes=f"difference amplifier, {note}")
        b.R(f"R{base}", 10e3, f"{h}_OUTP", f"{h}_DA_P", prec=True)
        b.R(f"R{base + 1}", rf, f"{h}_DA_P", "GND", prec=True)
        b.R(f"R{base + 2}", 10e3, f"{h}_OUTN", f"{h}_DA_N", prec=True)
        b.R(f"R{base + 3}", rf, f"{h}_DA_N", f"{h}_DA_OUT", prec=True)
    b.C("C410", "100n100V", "+3V3", "GND", note="U402 decoupling")
    b.C("C430", "100n100V", "+3V3", "GND", note="U422 decoupling")
    b.C("C450", "100n100V", "+3V3", "GND", note="U442 decoupling")
    b.R("R412", 1e3, "H1_DA_OUT", "HV_V_ADC", note="ADC filter")
    b.C("C411", "10n50V", "HV_V_ADC", "GND")
    b.R("R413", 10e3, "H1_DA_OUT", "HV_V_LIM", note="to the CV limiter")
    b.C("C412", "10n50V", "HV_V_LIM", "GND")
    b.R("R432", 1e3, "H2_DA_OUT", "HV_V_OVP", note="comparator input filter (1 us)")
    b.C("C431", "1n50V", "HV_V_OVP", "GND")
    b.R("R433", 10e3, "H2_DA_OUT", "HV_V2_ADC", note="path-2 cross-check to the MCU")
    b.C("C432", "10n50V", "HV_V2_ADC", "GND")
    b.R("R448", 1e3, "H3_DA_OUT", "I_HV_ADC", note="ADC filter")
    b.C("C451", "10n50V", "I_HV_ADC", "GND")
    b.R("R449", 10e3, "H3_DA_OUT", "I_HV_LIM", note="to the CC limiter")
    b.C("C452", "10n50V", "I_HV_LIM", "GND")
    b.R("R450", 1e3, "H3_DA_OUT", "I_HV_OCP", note="OC comparator filter")
    b.C("C453", "1n50V", "I_HV_OCP", "GND")
    return b


def limiter(d):
    b = Blk(d, "LIMIT", "L2 analog limiter: CV on pack voltage, CC on charge current (firmware-free)",
            "Two integrators on their own 2.5 V reference (U801, independent of the L3 reference U501). Either output "
            "rises when its limit is exceeded and lifts both PV setpoints through D105/D205, cutting power.",
            nets=[("VREF_LIM", (0, 2.6), "analog"), ("VREF_CV", (0, 2.6), "analog"), ("VREF_CC", (0, 2.6), "analog"),
                  ("CV_N", (0, 3.3), "analog"), ("CV_RZ", (0, 3.3), "analog"), ("CV_OUT", (0, 3.3), "analog"),
                  ("CC_N", (0, 3.3), "analog"), ("CC_RZ", (0, 3.3), "analog"), ("CC_OUT", (0, 3.3), "analog")])
    b.R("R801", 6.8e3, "AUX12", "VREF_LIM", p=0.015, va=10, note="reference bias 1.4 mA")
    b.add(P.LM4040, "U801", {"K": "VREF_LIM", "A": "GND"}, notes="limiter reference (independent of U501)")
    b.C("C801", "100n100V", "VREF_LIM", "GND")
    b.R("R802", 1.5e3, "VREF_LIM", "VREF_CV", prec=True, note=f"CV reference {VREF_CV:.4f} V = {L2_V:.1f} V pack")
    b.R("R803", 39.2e3, "VREF_CV", "GND", prec=True)
    b.C("C802", "100n100V", "VREF_CV", "GND")
    b.R("R804", 10e3, "VREF_LIM", "VREF_CC", prec=True, note=f"CC reference {VREF_CC:.4f} V = {VREF_CC / 4.1:.3f} A")
    b.R("R805", 9.76e3, "VREF_CC", "GND", prec=True)
    b.C("C803", "100n100V", "VREF_CC", "GND")
    b.add(P.TLV9062, "U802", {"OUTA": "CV_OUT", "INA-": "CV_N", "INA+": "HV_V_LIM", "V-": "GND", "INB+": "I_HV_LIM",
                              "INB-": "CC_N", "OUTB": "CC_OUT", "V+": "+3V3"},
          notes="A: CV integrator, B: CC integrator; output rises while the input exceeds its reference")
    b.R("R806", 100e3, "VREF_CV", "CV_N", note="integrator R (tune by simulation, V-21)")
    b.C("C804", "1u25V", "CV_N", "CV_RZ", note="integrator C")
    b.R("R807", 10e3, "CV_RZ", "CV_OUT", note="PI zero")
    b.R("R808", 100e3, "VREF_CC", "CC_N", note="integrator R")
    b.C("C805", "1u25V", "CC_N", "CC_RZ", note="integrator C")
    b.R("R809", 10e3, "CC_RZ", "CC_OUT", note="PI zero")
    b.C("C806", "100n100V", "+3V3", "GND", note="U802 decoupling")
    b.add(P.BAT46, "D801", {"A": "CV_OUT", "K": "LIM"}, notes="max(CV, CC)")
    b.add(P.BAT46, "D802", {"A": "CC_OUT", "K": "LIM"}, notes="max(CV, CC)")
    b.R("R810", 100e3, "LIM", "GND", note="LIM pull-down")
    b.R("R811", 10e3, "LIM", "LIM_ADC", note="limiter activity to the MCU")
    b.C("C807", "10n50V", "LIM_ADC", "GND")
    return b


def safety(d):
    b = Blk(d, "SAFETY", "Hardware safety: references, comparators, OVP/OC latch, supervisor, PERMIT, drivers",
            "PERMIT is a wired-AND: sourced only by MCU_RUN through R518, pulled low by any isolated-amplifier DIAG, "
            "the latch, the OTP comparators or a watchdog reset. It enables both LM5176s, the half-bridge driver and "
            "(with RELAY_REQ) the relays.",
            nets=[("VINT_OVP", (0, 2.2), "analog"), ("VTH_OT1", (0, 2.5), "analog"), ("TPS_CWD", (0, 3.4), "signal"),
                  ("WDO_N", (0, 3.4), "signal"), ("LED_OK_K", (0, 12.5), "signal"), ("LED_OK_A", (0, 12.5), "signal"),
                  ("LED_FLT_K", (0, 12.5), "signal"), ("LED_FLT_A", (0, 12.5), "signal")])
    b.R("R501", 6.8e3, "AUX12", "VREF2V5", p=0.015, va=10, note="reference bias 1.4 mA")
    b.add(P.LM4040, "U501", {"K": "VREF2V5", "A": "GND"}, notes="threshold reference for L3, OTP and OC")
    b.C("C501", "100n100V", "VREF2V5", "GND")
    b.R("R502", 2.49e3, "VREF2V5", "VTH2V0", prec=True, note=f"{VTH2V0:.4f} V threshold")
    b.R("R503", 10e3, "VTH2V0", "GND", prec=True)
    b.C("C502", "10n50V", "VTH2V0", "GND")
    b.add(P.LM2901B, "U502", {"1": "OVP_TRIP_N", "2": "OVP_TRIP_N", "3": "AUX12", "4": "VINT_OVP", "5": "VTH2V0",
                              "6": "HV_V_OVP", "7": "VTH2V0", "8": "VTH_OT1", "9": "NTC_T1", "10": "VTH_OTP",
                              "11": "NTC_P1", "12": "GND", "13": "PERMIT", "14": "PERMIT"},
          notes="ch1 HV OVP (L3), ch2 VINT OVP (L3b): both latch; ch3 T301 OTP, ch4 pack OTP #1: non-latching")
    b.C("C503", "100n100V", "AUX12", "GND")
    b.R("R504", 180e3, "VINT", "VINT_OVP", prec=True, note=f"VINT OVP divider: trip {VINT_OVP:.1f} V")
    b.R("R505", 10e3, "VINT_OVP", "GND", prec=True)
    b.C("C504", "1n50V", "VINT_OVP", "GND")
    b.R("R506", 24.9e3, "VREF2V5", "VTH_OT1", prec=True, note="T301 OTP threshold 0.716 V (~105 C)")
    b.R("R507", 10e3, "VTH_OT1", "GND", prec=True)
    b.R("R508", 100e3, "PERMIT", "NTC_T1", note="T301 OTP hysteresis (~3 K)")
    b.R("R509", 24.3e3, "VREF2V5", "VTH_OTP", prec=True, note="pack OTP threshold 0.729 V (50 C)")
    b.R("R510", 10e3, "VTH_OTP", "GND", prec=True)
    b.R("R511", 330e3, "PERMIT", "NTC_P1", note="pack OTP #1 hysteresis (~1.5 K)")
    b.R("R512", 10e3, "VREF2V5", "NTC_P1", prec=True, note="pack NTC 1 pull-up")
    b.C("C505", "100n100V", "NTC_P1", "GND", note="harness filter")
    b.R("R513", 10e3, "VREF2V5", "NTC_P2", prec=True, note="pack NTC 2 pull-up")
    b.C("C511", "100n100V", "NTC_P2", "GND", note="harness filter")
    b.R("R523", 330e3, "PERMIT", "NTC_P2", note="pack OTP #2 hysteresis")
    b.R("R514", 10e3, "+3V3", "OVP_TRIP_N", note="trip line pull-up")
    b.C("C506", "1n50V", "OVP_TRIP_N", "GND", note="10 us glitch filter")
    b.add(P.LVC2G74, "U503", {"1": "GND", "2": "GND", "3": "LATCH_QN", "4": "GND", "5": "LATCH_Q", "6": "RESET_N",
                              "7": "OVP_TRIP_N", "8": "+3V3"},
          notes="trip latch: set by ~PRE (OV, VINT OV, OC), cleared only by the power-on RESET_N")
    b.C("C507", "100n100V", "+3V3", "GND")
    b.add(P.BAT46, "D501", {"K": "LATCH_QN", "A": "PERMIT"}, notes="latched trip pulls PERMIT low")
    b.add(P.TPS3850, "U504", {"VDD": "+3V3", "CWD": "TPS_CWD", "SET0": "GND", "GND": "GND", "SET1": "GND", "WDI": "WDI",
                              "WDO": "WDO_N", "RESET": "RESET_N", "SENSE": "+3V3", "PAD": "GND"}, nc=["CRST"],
          nc_reason="CRST open = 200 ms reset delay (DS SBVS264B Table 5-1)",
          notes="3.3 V supervisor + window watchdog 9-109 ms")
    b.C("C508", "100n100V", "+3V3", "GND")
    b.R("R515", 10e3, "+3V3", "TPS_CWD", note="CWD to VDD: window 9-109 ms with SET1 = SET0 = 0")
    b.R("R516", 10e3, "+3V3", "RESET_N", note="RESET pull-up")
    b.R("R517", 1e3, "WDO_N", "MCLR_N", note="watchdog resets the MCU; 1 kOhm lets ICSP override")
    b.add(P.BAT46, "D502", {"K": "RESET_N", "A": "MCLR_N"}, notes="supervisor reset also resets the MCU")
    b.R("R518", 2.2e3, "MCU_RUN", "PERMIT", note="the only PERMIT source")
    b.R("R519", 1e3, "MCU_RUN", "GND", note="holds PERMIT <= 0.2 V while the MCU pins are tri-stated in reset")
    b.C("C509", "1n50V", "PERMIT", "GND")
    b.R("R520", 10e3, "RELAY_REQ", "K_IN", note="relay drive = RELAY_REQ AND PERMIT")
    b.add(P.BAT46, "D503", {"K": "PERMIT", "A": "K_IN"}, notes="relay AND gate: PERMIT low forces K_IN low")
    b.add(P.TPL7407, "U505", {"IN1": "K_IN", "IN2": "K_IN", "IN3": "FAN_PWM", "IN4": "PERMIT", "IN5": "LATCH_Q",
                              "IN6": "GND", "IN7": "GND", "GND": "GND", "COM": "AUX12", "OUT5": "LED_FLT_K",
                              "OUT4": "LED_OK_K", "OUT3": "FAN_N", "OUT2": "K2_COIL_N", "OUT1": "K1_COIL_N"},
          nc=["OUT6", "OUT7"], nc_reason="channels 6/7 unused; inputs tied low (DS SLRS074: outputs high impedance)",
          notes="low-side drivers with clamp diodes to COM = AUX12")
    b.C("C510", "100n100V", "AUX12", "GND")
    b.add(P.LED_G, "D504", {"K": "LED_OK_K", "A": "LED_OK_A"}, v_across=2.4,
          notes="green: PERMIT high; v_across: forward drop only (anode via R521, cathode open drain to the same rail)")
    b.R("R521", 4.7e3, "AUX12", "LED_OK_A", p=0.022, va=10.2, note="~2 mA")
    b.add(P.LED_R, "D505", {"K": "LED_FLT_K", "A": "LED_FLT_A"}, v_across=2.4, notes="red: trip latched")
    b.R("R522", 4.7e3, "AUX12", "LED_FLT_A", p=0.022, va=10.2, note="~2 mA")
    b.add(P.LM2901B, "U506", {"1": "OVP_TRIP_N", "6": "I_HV_OCP", "7": "VTH_OC", "2": "PERMIT", "4": "VTH_OTP",
                              "5": "NTC_P2", "8": "GND", "9": "VTH_OC", "10": "GND", "11": "VTH_OC", "3": "AUX12",
                              "12": "GND"}, nc=["13", "14"],
          nc_reason="channels 3/4 unused; IN+ above IN- keeps the open-collector outputs off",
          notes="ch1 charge-current OC (latching), ch2 pack OTP #2 (non-latching)")
    b.C("C512", "100n100V", "AUX12", "GND")
    b.R("R524", 10e3, "VREF2V5", "VTH_OC", prec=True, note=f"OC threshold {VTH_OC:.3f} V = {VTH_OC / 4.1:.3f} A")
    b.R("R525", 19.1e3, "VTH_OC", "GND", prec=True)
    b.C("C513", "10n50V", "VTH_OC", "GND")
    return b


def aux(d):
    b = Blk(d, "AUX", "Auxiliary supplies: PV/VINT OR -> AUX12 (LM5164) -> +3V3 (LM5164)",
            "Powered only from the roof (no 12 V battery drain). AUX12 starts at ~15 V on the string Voc and is then "
            "held up by VINT.",
            nets=[("AUX_EN", (0, 3.5), "signal"), ("AUX12_RON", (0, 3.0), "analog"), ("AUX12_FB", (0, 1.5), "analog"),
                  ("AUX12_RA", (0, 12.5), "analog"), ("AUX12_SW", (-1.5, 38), "switching", {"i_max": 1.0}),
                  ("V33_EN", (0, 2.5), "signal"), ("V33_RON", (0, 3.0), "analog"), ("V33_FB", (0, 1.5), "analog"),
                  ("V33_RA", (0, 3.4), "analog"), ("V33_SW", (-1.5, 12.5), "switching", {"i_max": 0.5})])
    d.domain("AUXBST", ref="AUX/AUX12_SW", kind="elv", description="LM5164 BST riding on AUX12_SW")
    d.domain("V33BST", ref="AUX/V33_SW", kind="elv", description="LM5164 BST riding on V33_SW")
    b.b.net("AUX12_BST", v=(0, 5.0), kind="signal", domain="AUXBST")
    b.b.net("V33_BST", v=(0, 5.0), kind="signal", domain="V33BST")
    b.add(P.D_HV, "D601", {"A": "PVA_P", "K": "AUX_IN"}, i_through=0.6, notes="aux OR from string A (carries only "
          "the aux current, <= 0.6 A)")
    b.add(P.D_HV, "D602", {"A": "PVB_P", "K": "AUX_IN"}, i_through=0.6, notes="aux OR from string B")
    b.add(P.D_HV, "D603", {"A": "VINT", "K": "AUX_IN"}, i_through=0.6, notes="aux OR from VINT")
    b.C("C601", "4u7100V", "AUX_IN", "GND", note="U601 input bulk")
    b.C("C602", "100n100V", "AUX_IN", "GND")
    b.add(P.LM5164, "U601", {"GND": "GND", "VIN": "AUX_IN", "EN/UVLO": "AUX_EN", "RON": "AUX12_RON", "FB": "AUX12_FB",
                             "BST": "AUX12_BST", "SW": "AUX12_SW", "EP": "GND"}, nc=["PGOOD"],
          nc_reason="PGOOD unused (open drain, DS Table 4-1)", notes="AUX12 buck, 300 kHz")
    b.R("R601", 90.9e3, "AUX_IN", "AUX_EN", note="EN/UVLO: start ~15 V")
    b.R("R602", 10e3, "AUX_EN", "GND")
    b.R("R603", 100e3, "AUX12_RON", "GND", note="fsw = 12 x 2500 / 100 = 300 kHz")
    b.C("C603", "2n2_50V", "AUX12_BST", "AUX12_SW", note="BST cap (TI: 2.2 nF)")
    b.add(P.L_AUX12, "L601", {"1": "AUX12_SW", "2": "AUX12"}, notes="100 uH")
    b.C("C604", "10u25V", "AUX12", "GND")
    b.C("C605", "10u25V", "AUX12", "GND")
    b.R("R604", 90.9e3, "AUX12", "AUX12_FB", note="FB top: 12.1 V")
    b.R("R605", 10e3, "AUX12_FB", "GND")
    b.R("R606", 150e3, "AUX12_SW", "AUX12_RA", note="type-3 ripple injection RA")
    b.C("C606", "2n2_50V", "AUX12_RA", "AUX12", note="ripple CA")
    b.C("C607", "10n50V", "AUX12_RA", "AUX12_FB", note="ripple CB")
    b.C("C608", "10u25V", "AUX12", "GND", note="U602 input")
    b.C("C609", "100n100V", "AUX12", "GND")
    b.add(P.LM5164, "U602", {"GND": "GND", "VIN": "AUX12", "EN/UVLO": "V33_EN", "RON": "V33_RON", "FB": "V33_FB",
                             "BST": "V33_BST", "SW": "V33_SW", "EP": "GND"}, nc=["PGOOD"],
          nc_reason="PGOOD unused (open drain, DS Table 4-1)", notes="+3V3 buck, 300 kHz")
    b.R("R607", 49.9e3, "AUX12", "V33_EN", note="EN/UVLO: start ~9 V")
    b.R("R608", 10e3, "V33_EN", "GND")
    b.R("R609", 27.4e3, "V33_RON", "GND", note="fsw = 3.3 x 2500 / 27.4 = 301 kHz")
    b.C("C610", "2n2_50V", "V33_BST", "V33_SW")
    b.add(P.L_3V3, "L602", {"1": "V33_SW", "2": "+3V3"}, notes="33 uH")
    b.C("C611", "10u25V", "+3V3", "GND")
    b.C("C612", "10u25V", "+3V3", "GND")
    b.R("R610", 17.4e3, "+3V3", "V33_FB", note="FB top: 3.29 V")
    b.R("R611", 10e3, "V33_FB", "GND")
    b.R("R612", 150e3, "V33_SW", "V33_RA", note="ripple RA")
    b.C("C613", "2n2_50V", "V33_RA", "+3V3")
    b.C("C614", "10n50V", "V33_RA", "V33_FB")
    return b


DSPIC_NETS = {1: "DCX_HI", 2: "DCX_LI", 3: "MPPT_A_PWM", 4: "MPPT_B_PWM", 5: "MCLR_N", 6: "FAN_PWM", 7: "NTC_P1",
              8: "HV_V_ADC", 9: "HV_V2_ADC", 10: "I_HV_ADC", 11: "PVA_VDIV", 12: "PVA_I_ADC", 13: "+3V3A", 14: "GND",
              15: "PVB_VDIV", 16: "PVB_I_ADC", 17: "NTC_P2", 18: "+3V3", 19: "GND", 20: "VINT_DIV", 21: "NTC_HS",
              22: "NTC_P3", 23: "NTC_P4", 24: "AUX12_DIV", 25: "LIM_ADC", 26: "LATCH_Q", 27: "READY_N", 28: "EE_SCK",
              29: "EE_SO", 30: "EE_SI", 31: "GND", 32: "+3V3", 33: "EE_CS_N", 34: "WDI", 35: "PERMIT_SNS", 36: "PGD",
              37: "PGC", 38: "CAN_TX", 39: "CAN_RX", 40: "RELAY_REQ", 41: "CAN_EN", 42: "GND", 43: "+3V3",
              44: "MCU_RUN", 45: "UART_TX"}


def mcu(d):
    b = Blk(d, "MCU", "MCU, logging, IG sense, CAN (OBD-II, read-only), connectors",
            "dsPIC33CK256MP505: MPPT, DCX PWM, SOC estimation (coulomb + OCV + CAN), temperature compensation, "
            "relay sequencing and logging to U703. The CAN transmitter is enabled only while IG is on (Q702 AND Q703).",
            nets=[("IGN_D", (0, 112), "signal"), ("READY_B", (0, 0.8), "signal"), ("IG_GB", (0, 0.8), "signal"),
                  ("CAN_GE", (0, 3.4), "signal"), ("CAN_EN_B", (0, 0.8), "signal"), ("CAN_RS", (0, 3.4), "signal")])
    b.add(P.DSPIC, "U701", {str(k): v for k, v in DSPIC_NETS.items()}, nc=["46", "47", "48"],
          nc_reason="spare GPIO (RB11-RB13, JTAG TCK/TDI unused with JTAGEN = 0), driven low by firmware",
          notes="config: JTAGEN = 0, FRC + PLL, ICSP on PGC1/PGD1; PPS: C1TX RP52, C1RX RP53, U1TX RP42, SCCP RP77")
    b.R("R701", 10, "+3V3", "+3V3A", p=0.005, va=0.2, note="AVDD filter")
    b.C("C701", "1u25V", "+3V3A", "GND", note="AVDD bulk")
    b.C("C702", "100n100V", "+3V3A", "GND", note="AVDD HF")
    for k, pin in ((703, 18), (704, 32), (705, 43)):
        b.C(f"C{k}", "100n100V", "+3V3", "GND", note=f"VDD pin {pin}")
    b.C("C706", "10u25V", "+3V3", "GND", note="MCU bulk")
    b.R("R702", 10e3, "+3V3", "MCLR_N", note="MCLR pull-up")
    b.add(P.J_ICSP, "J701", {"1": "MCLR_N", "2": "+3V3", "3": "GND", "4": "PGD", "5": "PGC", "6": "UART_TX"},
          i_through=0.1, notes="ICSP (1-5) + log UART TX (6); programmer current only")
    b.R("R703", 10e3, "PERMIT", "PERMIT_SNS", note="PERMIT read-back")
    b.R("R713", 47e3, "AUX12", "AUX12_DIV", note="AUX12 monitor 1/5.7")
    b.R("R714", 10e3, "AUX12_DIV", "GND")
    b.C("C714", "10n50V", "AUX12_DIV", "GND")
    b.R("R715", 10e3, "+3V3A", "NTC_P3", prec=True, note="pack NTC 3 pull-up (ratiometric)")
    b.C("C715", "100n100V", "NTC_P3", "GND")
    b.R("R716", 10e3, "+3V3A", "NTC_P4", prec=True, note="pack NTC 4 pull-up (ratiometric)")
    b.C("C716", "100n100V", "NTC_P4", "GND")
    b.add(P.J_6P, "J706", {"1": "NTC_P1", "2": "NTC_P2", "3": "NTC_P3", "4": "NTC_P4", "5": "GND", "6": "GND"},
          i_through=0.001, notes="pack-case NTC harness (sensor currents < 1 mA)")
    # IG sense
    b.add(P.J_PV, "J702", {"1": "IGN_IN", "2": "GND"}, i_through=0.01, notes="IG2-switched 12 V (fuse tap) + ground; < 10 mA")
    b.add(P.BAS21, "D701", {"A": "IGN_IN", "K": "IGN_D"}, nc=["NC"], nc_reason="BAS21 pin 2 is not connected inside",
          v_across=150, notes="blocks ISO 7637 negative pulses; v_across: reverse = -150 V pulse 1 while IGN_D sits near 0 V on the base resistors (the interval sum pairs +112 V on IGN_D with -150 V, impossible)")
    b.R("R704", 22.1e3, "IGN_D", "READY_B", pkg="1206", p=0.011, va=112,
        note="series R: 11 mW at 16 V; ISO 7637 pulse 2a (112 V, 50 us) is 0.57 W for 50 us = 28 uJ")
    b.R("R705", 10e3, "READY_B", "GND", note="threshold ~2.2 V on IG")
    b.add(P.NPN_HV, "Q701", {"B": "READY_B", "E": "GND", "C": "READY_N"}, notes="READY_N low = IG on")
    b.R("R706", 4.7e3, "+3V3", "READY_N", note="pull-up")
    b.C("C707", "10n50V", "READY_N", "GND")
    # CAN transmit gate: RS low only if IG on (Q703) AND MCU CAN_EN (Q702)
    b.R("R717", 22.1e3, "IGN_D", "IG_GB", pkg="1206", p=0.011, va=112, note="IG -> Q703 base; 11 mW at 16 V")
    b.R("R718", 10e3, "IG_GB", "GND")
    b.add(P.NPN_HV, "Q703", {"B": "IG_GB", "E": "GND", "C": "CAN_GE"}, notes="IG on -> lower switch of the AND")
    b.add(P.NPN_HV, "Q702", {"B": "CAN_EN_B", "E": "CAN_GE", "C": "CAN_RS"}, notes="CAN_EN -> upper switch of the AND")
    b.R("R719", 22e3, "CAN_EN", "CAN_EN_B", note="Q702 base")
    b.R("R720", 10e3, "+3V3", "CAN_RS", note="RS high = standby, driver off (default)")
    b.add(P.HVD230, "U702", {"D": "CAN_TX", "GND": "GND", "VCC": "+3V3", "R": "CAN_RX", "CANL": "CAN_L",
                             "CANH": "CAN_H", "Rs": "CAN_RS"}, nc=["Vref"],
          nc_reason="Vref (VCC/2 output) unused, may be left open (DS SGLS398A p.2)",
          notes="CAN transceiver; no termination (stub on the car's diagnostic bus)")
    b.C("C717", "100n100V", "+3V3", "GND")
    b.add(P.J_3P, "J707", {"1": "CAN_H", "2": "CAN_L", "3": "GND"}, i_through=0.07,
          notes="to the OBD-II Y cable (pins 6, 14, 5); CAN drive current only")
    # log memory
    b.add(P.EEPROM, "U703", {"1": "EE_CS_N", "2": "EE_SO", "3": "+3V3", "4": "GND", "5": "EE_SI", "6": "EE_SCK",
                             "7": "+3V3", "8": "+3V3"}, notes="fault/charge log; WP and HOLD tied high")
    b.C("C718", "100n100V", "+3V3", "GND")
    b.R("R721", 10e3, "+3V3", "EE_CS_N", note="deselect during reset")
    # harness connectors
    b.add(P.J_3P, "J703", {"1": "AUX12", "2": "K1_COIL_N", "3": "K2_COIL_N"}, notes="relay coils to battery-end J903")
    b.add(P.J_FAN, "J704", {"1": "AUX12", "2": "FAN_N"}, notes="optional 12 V fan")
    for i, net in enumerate(["VINT", "AUX12", "+3V3", "PERMIT", "GND", "LIM"], start=1):
        b.add(P.TP, f"TP70{i}", {"1": net}, notes="test pad")
    for i in range(1, 5):
        b.add(P.MH_PAD, f"H70{i}", {"1": "GND"}, notes="LV-side mount; bonds GND to the box (chassis)")
    for i in (5, 6):
        b.add(P.MH, f"H70{i}", {}, notes="HV-side mount, non-plated, >= 10 mm from LV copper")
    return b


def batt_end(d):
    b = Blk(d, "BATEND", "Battery-end board: fuses on both poles, blocking diode, 2-pole disconnect, pack sense",
            "Mounted next to the Prime HV battery. F901/F902 are the first elements from the pack; D901 stops the pack "
            "feeding our cable; K901/K902 open both poles when idle; R902-R904 carry the pack voltage to path 1.",
            board="batt_end", domain="HV",
            nets=[("BE_DK", (0, V_HV_MAX), "hv", {"i_max": I_HV_MAX}), ("SNS_A", (0, V_HV_MAX), "hv"),
                  ("SNS_B", (0, V_HV_MAX), "hv"),
                  ("BAT_F_P", (0, V_PACK_MAX), "hv", {"i_max": I_HV_MAX, "domain": "PACK"}),
                  ("BAT_F_N", 0, "hv", {"i_max": I_HV_MAX, "domain": "PACK"})])
    b.add(P.J_HV3, "J901", {"1": "HV_P", "2": "HV_N", "3": "PACK_SNS"}, notes="from main J301")
    b.add(P.J_HV2, "J902", {"1": "BAT_TAP_P", "2": "BAT_TAP_N"}, notes="to the pack tap leads (cell side of SMRs)")
    b.add(P.J_3P, "J903", {"1": "AUX12", "2": "K1_COIL_N", "3": "K2_COIL_N"}, notes="relay coils from main J703")
    b.add(P.FUSE_HV, "F901", {"1": "BAT_TAP_P", "2": "BAT_F_P"}, v_across=V_PACK_MAX,
          notes="first element from pack +; v_across: a blown fuse sees the pack voltage")
    b.add(P.FUSE_HV, "F902", {"1": "BAT_TAP_N", "2": "BAT_F_N"}, v_across=V_PACK_MAX, notes="first element from pack -")
    b.add(P.RELAY_HV, "K901", {"COIL_1": "AUX12", "COIL_2": "K1_COIL_N", "C3": "BAT_F_P", "C4": "BE_DK"},
          notes="+ pole disconnect (double break, no contact polarity)")
    b.add(P.RELAY_HV, "K902", {"COIL_1": "AUX12", "COIL_2": "K2_COIL_N", "C3": "BAT_F_N", "C4": "HV_N"},
          notes="- pole disconnect")
    b.add(P.D_HV, "D901", {"A": "HV_P", "K": "BE_DK"}, p_diss=0.3, notes="blocking diode: the pack cannot feed the "
          "cable (0.85 V x 0.3 A = 0.26 W)")
    hv_r = dict(pkg="1206", prec=True, p=0.006, va=75)
    b.R("R902", 1e6, "BE_DK", "SNS_A", note="pack sense string (battery-end half); a sense-core short draws <= "
        "133 uA", **hv_r)
    b.R("R903", 1e6, "SNS_A", "SNS_B", **hv_r)
    b.R("R904", 1e6, "SNS_B", "PACK_SNS", **hv_r)
    for i in range(1, 5):
        b.add(P.MH, f"H90{i}", {}, notes="non-plated mount, >= 10 mm from HV copper")
    return b


def array(d):
    nets = []
    for X in "AB":
        nets += [(f"PV{X}_C{k}", (0, 33), "power", {"i_max": 7.5}) for k in range(1, 4)]
    b = Blk(d, "ARRAY", "Roof array (off-board): 2 strings x 4 columns x 7 C60 cells, bypass diode per column",
            "Cell field 8 columns x 7 rows at 127 mm pitch (1016 x 889 mm), 56 cells. String A = columns 1-4 (left), "
            "string B = columns 5-8; each column is 7 cells in series with its own bypass diode.",
            board="off", nets=nets)
    for X, base in (("A", 100), ("B", 200)):
        node = ["GND"] + [f"PV{X}_C{k}" for k in range(1, 4)] + [f"PV{X}_IN"]
        for c in range(4):
            b.add(P.C60_COLUMN, f"SC{base + c + 1}", {"+": node[c + 1], "-": node[c]},
                  notes=f"string {X} column {c + 1} (7 cells)")
            b.add(P.D_BYPASS, f"D{base + 61 + c}", {"K": node[c + 1], "A": node[c]}, v_across=5.7, i_through=7.5,
                  notes=f"bypass for column {c + 1} of string {X}; v_across: 7 cells x 0.81 V (Voc at -40 C) "
                        "reverse; i_through: the string current when bypassing")
    return b


def harness(d):
    b = Blk(d, "HARNESS", "Harness items (off-board): cables, tap fuse, pack-case NTCs",
            "Bought or made-up wiring, listed so the BOM and the voltage/current checks cover it.",
            board="off", nets=[])

    def w(defn, ref, cores, note, **kw):
        conns = {}
        for k, net in enumerate(cores, start=1):
            conns[f"C{k}_NEAR"] = net
            conns[f"C{k}_FAR"] = net
        return b.add(defn, ref, conns, notes=note, **kw)
    w(P.W_PV, "W1", ["PVA_IN", "GND"], "string A cable, roof -> J101", i_through=7.5)
    w(P.W_PV, "W2", ["PVB_IN", "GND"], "string B cable, roof -> J201", i_through=7.5)
    w(P.W_HV, "W3", ["HV_P", "HV_N", "PACK_SNS"], "HV cable J301 -> J901; screen to the metal glands")
    w(P.W_LV3, "W4", ["AUX12", "K1_COIL_N", "K2_COIL_N"], "relay-coil cable J703 -> J903")
    w(P.W_NTC, "W5", ["NTC_P1", "NTC_P2", "NTC_P3", "NTC_P4", "GND"], "pack-case NTC cable -> J706", i_through=0.001)
    w(P.W_CAN, "W6", ["CAN_H", "CAN_L", "GND"], "OBD-II Y cable breakout (pins 6, 14, 5) -> J707", i_through=0.07)
    w(P.W_IG, "W7", ["IGN_IN", "GND"], "IG feed from the fuse tap + chassis ground -> J702; v_across: rated system "
      "voltage 16 V; ISO 7637 pulses are within the ISO 6722 1 kV insulation test", i_through=0.01, v_across=16)
    w(P.W_TAP, "W8", ["BAT_TAP_P", "BAT_TAP_N"], "pack tap leads (<= 0.3 m, double insulated) -> J902")
    b.add(P.FUSE_IG, "F701", {"1": "IGN_CAR", "2": "IGN_IN"}, v_across=16,
          notes="1 A tap fuse at the source; v_across: it interrupts the 12-16 V system, not the transient envelope")
    b.add(P.FUSE_TAP, "X701", {"1": "IGN_CAR"}, notes="add-a-fuse holder in an IG2-switched fuse position")
    for k in range(1, 5):
        b.add(P.NTC_PACK, f"TH{k}", {"1": f"NTC_P{k}", "2": "GND"},
              notes=f"pack-case NTC {k} (1, 2: hardware OTP + firmware; 3, 4: firmware)")
    return b


# =============================================================================================
# Calculations (DESIGN.md section 7)

def calcs(d):
    c = d.calc
    voc_cold = 28 * (0.687 + 0.0018 * 65)
    c("string_voc_cold", round(voc_cold, 2), "V", "28 x (0.687 V + 1.8 mV/K x 65 K)", "28-cell string at -40 C",
      limit=33, op="<=")
    c("string_voc_cold_40cells", round(40 * (0.687 + 0.0018 * 65), 2), "V", "40 cells, -40 C",
      "largest string the electronics accept", limit=33, op="<=")
    vmp_hot_shaded = 21 * (0.574 - 0.0018 * 45) - 0.45
    c("uvlo_off_vs_shaded_vmp", round(vmp_hot_shaded - (1.22 * (1 + 1.5e6 / 137e3) - 1.5e6 * 2e-6 - 3.15e-6 * 1.5e6), 2),
      "V", "Vmp(one column bypassed, 70 C) - UVLO off", "UVLO must stay below the shaded MPP", limit=0, op=">")
    c("array_stc_w", round(56 * 3.42, 1), "W", "56 x 3.42 W", "array at STC")
    c("cap_power_w", round(I_CAP * L1_V, 1), "W", "I_cap x 375 V", "power at the cap near the stop voltage")
    ah_day = I_CAP * 8
    c("ah_per_sun_day_at_cap", ah_day, "Ah", "0.30 A x 8 h (generous clear-sky day)", "upper bound of daily charge")
    c("days_80_to_100_at_cap", round(0.2 * CELL_AH / ah_day, 2), "days", "0.2 x 25 Ah / (0.30 A x 8 h)",
      "every firmware layer failed; L2/L3 still stop it earlier", limit=2.0, op=">=")
    c("days_80_to_110_at_cap", round(0.3 * CELL_AH / ah_day, 2), "days", "0.3 x 25 Ah / 2.4 Ah",
      "onset of plating/cathode damage taken at 110 % [I]", limit=3.0, op=">=")
    c("pack_rise_if_all_heat_k", round(I_CAP * L1_V / 10.0, 1), "K", "114 W / 10 W/K (fan off, ASM-8)",
      "steady pack rise if ALL charge power became heat (overcharge)", limit=15, op="<=")
    c("pack_rise_adiabatic_k_per_h", round(I_CAP * L1_V * 3600 / 70e3, 2), "K/h", "114 W x 3600 s / 70 kJ/K",
      "adiabatic bound")
    c("phys_max_current_a", round(56 * 3.42 * 1.2 / (CELLS * V_CELL_MIN), 2), "A", "1.2 suns x 191.5 W / 285 V",
      "what the array could push with every limiter failed", limit=I_HV_MAX, op="<=")
    c("L1_stop_v", round(L1_V, 1), "V", "95 x 3.95 V", "firmware stop (rest OCV)")
    c("L2_cv_v", round(L2_V, 1), "V", "VREF_CV x K_div / (G_AMC x G1)", "analog clamp, 4.00 V/cell")
    c("L2_cc_a", round(VREF_CC / (41 * 0.1), 4), "A", "VREF_CC / (41 x 0.1 Ohm)", "analog current cap", limit=0.31,
      op="<=")
    c("L3_trip_v", round(L3_V, 1), "V", "2.000 V x K_div / (2 x 1.21)", "latch, measured on HV_P")
    c("L1_below_L2min", round(L2_V * 0.991 - L1_V, 2), "V", "L2 x (1 - 0.9 %) - L1", "firmware stops first",
      limit=0, op=">")
    c("L2max_below_L3min", round(L3_V * 0.991 - 0.9 - L2_V * 1.009, 2), "V",
      "L3 x (1 - 0.9 %) - D901 drop - L2 x (1 + 0.9 %)", "no nuisance latch at the clamp", limit=0, op=">")
    c("L3max_per_cell", round(L3_V * 1.009 / CELLS, 3), "V/cell", "L3 x 1.009 / 95", "last-resort latch below 4.20 V "
      "average", limit=V_CELL_MAX, op="<")
    c("oc_trip_a", round(VTH_OC / 4.1, 3), "A", "VTH_OC / 4.1 V/A", "latching OC", limit=0.45, op="<=")
    c("vint_ceiling_v", round(VINT_CEIL, 2), "V", "0.8 x (1 + 442k/10k)", "L2b (LM5176 FB)")
    c("hv_at_vint_ceiling_v", round(N_DCX / 2 * VINT_CEIL - 1.6, 1), "V", "11 x VINT - 2 Vf", "L2b no-load output",
      limit=V_HV_MAX, op="<=")
    c("vint_ovp_v", round(VINT_OVP, 2), "V", "2.000 x (1 + 180k/10k)", "L3b latch", limit=VINT_CEIL * 1.015, op=">")
    c("vint_at_pack_min_v", round(2 * (CELLS * V_CELL_MIN + 1.6) / N_DCX, 2), "V", "2 x (285 + 1.6) / 22",
      "lowest VINT while charging")
    c("amc_input_at_420v", round(V_HV_MAX / K_DIV, 3), "V", "420 V / 473.4", "inside the +/-1 V FSR", limit=1.0,
      op="<")
    c("amc3302_input_at_oc", round(0.4 * 0.1 * 1000, 1), "mV", "0.4 A x 0.1 Ohm", "inside the +/-50 mV FSR",
      limit=50, op="<")
    c("hv_bleed_time_s", round(6.0e6 * 0.8e-6 * 2.0, 1), "s", "tau = 6 MOhm x 0.8 uF; ln(420/60) = 1.95",
      "output < 60 V", limit=10, op="<=")
    c("fuse_breaking_ratio", round(3300 / 20000, 3), "", "pack Isc ~3.3 kA / 20 kA", "breaking capacity margin",
      limit=0.8, op="<=")
    c("relay_coil_pullin_a", round(2 * 0.235, 3), "A", "2 x 235 mA (sequenced in firmware: one at a time)",
      "AUX12 budget", limit=0.6, op="<=")
    c("t301_bpk_t", round((VINT_CEIL / 2) * (1 / 95e3 / 2) / (4 * 125e-6) / 2, 3), "T",
      "(VINT/2 x T/2) / (Np x Ae) / 2", "N97 at 95 kHz", limit=0.2, op="<=")


# =============================================================================================
# Placement intent (README "Placement relations"), boards, waivers

def placement(d):
    pl = d.place
    blocks = {b.name: b for b in d.blocks}
    for name, where in (("MPPT_A", "west"), ("MPPT_B", "west"), ("DCX", "center"), ("HVSENSE", "east"),
                        ("LIMIT", "south"), ("SAFETY", "south"), ("AUX", "north"), ("MCU", "south")):
        pl.group(blocks[name], "close")
        pl.region(blocks[name], where)
    pl.group(blocks["BATEND"], "close")
    pl.symmetric([("U103", "U203"), ("L101", "L201"), ("Q103", "Q203"), ("Q105", "Q205")], axis="h",
                 note="channel A above channel B, mirrored")
    for X, base in (("A", 100), ("B", 200)):
        pl.edge(f"J{base + 1}", "west", note="PV gland")
        pl.hot_loop([f"C{base + 6}.1", f"Q{base + 3}.D", f"Q{base + 3}.S", f"Q{base + 4}.D", f"Q{base + 4}.S",
                     f"R{base + 16}.I+", f"R{base + 16}.I-", f"C{base + 6}.2"], note="buck-side loop, top layer")
        pl.hot_loop([f"C{base + 20}.1", f"Q{base + 5}.D", f"Q{base + 5}.S", f"Q{base + 6}.D", f"Q{base + 6}.S",
                     f"R{base + 16}.I+", f"R{base + 16}.I-", f"C{base + 20}.2"], note="boost-side loop, top layer")
        for q in (3, 4, 5, 6):
            pl.thermal(f"Q{base + q}", 1.0, "box wall via thermal pad", note="TDSON drain tab to the copper/box")
        pl.near(f"R{base + 23}", f"Q{base + 3}.G", "tight")
        pl.near(f"R{base + 22}", f"Q{base + 4}.G", "tight")
        pl.near(f"R{base + 19}", f"Q{base + 5}.G", "tight")
        pl.near(f"R{base + 20}", f"Q{base + 6}.G", "tight")
        pl.near(f"C{base + 19}", f"U{base + 3}.BOOT1", "tight")
        pl.near(f"C{base + 16}", f"U{base + 3}.BOOT2", "tight")
        pl.near(f"Q{base + 1}", f"J{base + 1}", "close", note="ideal diode right after the input")
        pl.custom("kelvin", obj=f"R{base + 1}", pins=["S+", "S-"], to=[f"U{base + 2}", f"U{base + 3}"],
                  note="sense traces from the inner WSK2512 pads, routed as a pair away from SW nodes")
        pl.custom("kelvin", obj=f"R{base + 16}", pins=["S+", "S-"], to=[f"U{base + 3}.CS", f"U{base + 3}.CSG"])
        pl.keepout(f"MPPT_{X}/SW1", what="analog traces under the switch node", layers="all")
    # DCX
    pl.hot_loop(["C303.1", "Q301.D", "Q301.S", "Q302.D", "Q302.S", "C303.2"], note="half-bridge loop")
    pl.hot_loop(["D301.K", "C350.1", "C350.2", "D303.A"], note="rectifier loop, HV side")
    pl.near("U301", "Q302.G", "tight")
    pl.thermal("T301", 1.5, "box wall via gap pad", note="ETD39 core and winding loss")
    pl.thermal("Q301", 0.6, "box wall")
    pl.thermal("Q302", 0.6, "box wall")
    for dref in ("D301", "D302", "D303", "D304"):
        pl.thermal(dref, 0.3, "copper")
    pl.near("RT302", "T301", "tight", note="hardware OTP sensor between T301 and Q301")
    pl.near("RT301", "Q301", "tight")
    pl.edge("J301", "east", note="HV output through the EMC gland")
    pl.custom("height", obj="T301", height_mm=42, note="ETD39 horizontal former")
    pl.custom("height", members=["C108", "C208", "C301", "C302"], height_mm=11)
    pl.custom("straddle", obj="T301", barrier="LV/HV", note="primary pins on LV, secondary on HV; slot under the former")
    for u in ("U401", "U421", "U441"):
        pl.custom("straddle", obj=u, barrier="LV/HV", note="pins 1-8 HV, 9-16 LV; >= 2 mm slot under the body")
        pl.keepout(u, what="copper and vias under the package body", layers="all")
    pl.keepout("T301", what="copper and vias in the barrier band under the former", layers="all")
    pl.custom("kelvin", obj="R441", pins=["S+", "S-"], to=["R442", "R443"], note="AMC3302 inputs, short and symmetric")
    for h in ("H1", "H2", "H3"):
        pl.custom("diff_pair", nets=[f"net:HVSENSE/{h}_OUTP", f"net:HVSENSE/{h}_OUTN"], note="to the difference amp")
    pl.custom("diff_pair", nets=["net:CAN_H", "net:CAN_L"], impedance_ohm=120)
    pl.near("U402", "U401", "close")
    pl.near("U422", "U421", "close")
    pl.near("U442", "U441", "close")
    pl.far("U401", "U421", "close", note="the two voltage paths physically apart (no common-cause damage)")
    # safety, MCU
    pl.near("U503", "U502", "close")
    pl.near("U504", "U701", "close")
    for j in ("J702", "J703", "J704", "J706", "J707"):
        pl.edge(j, "south", note="LV harness gland")
    pl.custom("cable_entry", members=["J101", "J201"], gland="M16 sealed, PV cable", edge="west")
    pl.custom("cable_entry", obj="J301", gland="M20 EMC (screen 360 deg)", edge="east")
    pl.custom("cable_entry", members=["J702", "J703", "J706", "J707"], gland="M20 multi-hole, LV", edge="south")
    pl.custom("cable_entry", members=["J901", "J902"], gland="M20 EMC (J901), M16 (J902)", edge="north")
    # battery end
    pl.edge("J901", "north")
    pl.edge("J902", "north")
    pl.edge("J903", "south")
    pl.near("F901", "J902", "tight", note="fuses first from the pack")
    pl.near("F902", "J902", "tight")
    pl.custom("relay_gap", members=["K901", "K902"], gap_mm=20, note="Omron G9KB installation gap >= 20 mm (K340-E1-06)")
    pl.custom("height", members=["K901", "K902"], height_mm=51)
    pl.custom("straddle", members=["K901", "K902"], barrier="LV/HV,PACK", note="coil pins toward J903, contacts toward "
              "J902/J901; slot between coil and contact pins")
    pl.thermal("D901", 0.3, "copper")
    for bar in d.barriers:
        # Domain objects, not names: placement treats bare strings like "HV" as refdes-like (framework issue)
        pl.separate(d.domains[bar.a], d.domains[bar.b], slot=bar.slot)
    pl.side("all", "top", note="all parts on the top side; bottom flat on the thermal pad")


def boards(d):
    d.board("main", width_mm=200, height_mm=140, layers=4, thickness_mm=1.6, copper_oz=2,
            holes=[Hole(5, 5, 3.2, 6.0, True, "GND", "H701"), Hole(5, 135, 3.2, 6.0, True, "GND", "H702"),
                   Hole(120, 5, 3.2, 6.0, True, "GND", "H703"), Hole(120, 135, 3.2, 6.0, True, "GND", "H704"),
                   Hole(195, 5, 3.2, note="H705 HV side, non-plated"),
                   Hole(195, 135, 3.2, note="H706 HV side, non-plated")],
            max_component_height_mm=45, max_bottom_height_mm=0,
            enclosure="die-cast aluminium IP67 box with external fins (>= 0.12 m2), bonded to chassis; thermal "
                      "pad under the FETs, T301 and the bridge",
            coating="acrylic conformal coat (not credited for creepage)",
            keepouts=[{"relative": "barrier band 10 mm wide between LV and HV sections, slot >= 2 mm",
                       "what": "copper and vias", "layers": "all"}],
            notes="HV section along the east edge (x > 150 mm); FR-4 CTI >= 175 (IIIa)")
    d.board("batt_end", width_mm=140, height_mm=100, layers=2, thickness_mm=1.6, copper_oz=2,
            holes=[Hole(5, 5, 3.2, note="H901"), Hole(135, 5, 3.2, note="H902"), Hole(5, 95, 3.2, note="H903"),
                   Hole(135, 95, 3.2, note="H904")],
            max_component_height_mm=55,
            enclosure="IP67 metal box bonded to chassis, next to the HV battery; two glands",
            coating="acrylic conformal coat (not credited)",
            notes="all copper is HV/PACK except the coil pins and J903; 10 mm band around them")


def waivers(d):
    W = d.waive
    W("protect.entry_fuse", r"net PV[AB]_IN",
      "A PV string is a current source (Isc 6.3 A at 1 sun, 7.3 A worst case) below every rating in its path "
      "(J101 12 A, 2.5 mm2 cable, Q101 100 A); one string per input, no parallel strings to back-feed it, so no "
      "string fuse is needed [S: IEC 62548 requires string fuses only for >= 3 parallel strings].")
    W("protect.entry_fuse", r"net (HV_P|HV_N|PACK_SNS) reaches",
      "These nets are fused where the energy is: F901/F902 sit first from the pack at the battery end and D901 blocks "
      "pack current toward the cable; from our side HV_P is current-limited (0.30 A cap, 0.40 A latch, < 0.7 A "
      "physical). PACK_SNS has 3 MOhm in series at the battery end (<= 133 uA).")
    W("protect.entry_fuse", r"net BAT_TAP_P reaches",
      "BAT_TAP_P is the unfused stub between the pack terminal and F901 itself (<= 0.3 m, double insulated, inside "
      "the battery cover, REQ-21); F901 on this net is the fuse.")
    W("lib.footprint_custom", r"T301|ETD39",
      "Custom magnetics: pad grid from the TDK ETD 39 20-pin coil-former drawing; only pins 1-4, 11, 20 are populated "
      "and the rest omitted for creepage. Drawn and reviewed with the vendor sample (V-5).")
    W("lib.footprint_custom", r"Omron_G9KB",
      "No KiCad footprint for Omron G9KB: holes from K340-E1-06 p.3 'PCB Mounting Holes (bottom view)': 4 contact "
      "slots 3.8 x 3.1 mm, 2 coil slots 1.5 x 3.2 mm, +/-0.1 mm; to be drawn and checked against Omron CAD.")
    W("lib.footprint_custom", r"Eaton_EVM10",
      "No KiCad footprint for EVM10-2P: two PCB pins per end cap per ELX1304 p.2 'PCB layout 2P'.")
    W("barrier.package_creepage", r"U4[024]1",
      "The 10 mm barrier creepage is the PCB (material group IIIa) value. AMC3330/AMC3302 packages are CTI >= 600 V "
      "(group I) [P], for which IEC 60664-1 F.4 needs 2.5 mm basic / 5.0 mm reinforced at 500 V [S]; the packages "
      "give >= 8 mm, and a >= 2 mm routed slot under each body gives the PCB path >= 10 mm (framework compares one "
      "number; see report note).")
    W("rating.voltage", r"^U[12]01 \(LM74700-Q1\): V\((GATE|VCAP)-ANODE\)",
      "Set by the IC's own charge pump: turn-off at 11.6-13.9 V above ANODE (SNOSD17G 6.5); the 15 V absolute "
      "maximum is the vendor's margin over its own regulation, not a stress we choose.")
    W("rating.voltage", r"^U[12]01 \(LM74700-Q1\): V\(CATHODE-ANODE\)",
      "Interval artefact: 66 V pairs +33 V on PVx_P with the string reversed at -33 V. PVx_P is fed only by its "
      "string (no back-feed path from VINT through the buck-boost body diodes or from AUX_IN through D601/D602), so "
      "with the string reversed PVx_P decays to 0 V and V(CATHODE-ANODE) <= 33 V (44 % of 75 V).")
    W("rating.voltage", r"^U[12]03 \(LM5176QPWPRQ1\): V\((FB/SS|VCC/MODE|BOOT)",
      "Pins driven by the LM5176 itself: SS clamp 1.21 V, COMP <= 3.0 V, VCC regulator ~7.5 V, BOOT = VCC - diode "
      "(SNVSB46B 6.5). The abs max (3.6 V / 8.5 V) is the vendor's margin over its own regulation.")
    W("rating.voltage", r"^U60[12] \(LM5164-Q1\): V\(BST-SW\)",
      "BST-SW is the LM5164's internal 5 V gate-drive regulator (SNVSB51C); abs max 5.5 V is its own margin.")
    W("rating.voltage", r"^U701 \(DSPIC33CK256MP505-E/PT\): V\(VDD/AVDD-VSS\)",
      "+3V3 is 3.29 V regulated (3.4 V envelope incl. ripple) inside the recommended 3.0-3.6 V; 4.0 V is the "
      "absolute maximum, not a derating base for a regulated logic rail.")
    W("hazard.procedural", r"^HZ-9:",
      "Array attachment is mechanical and outside this electrical design; it is a BLOCKING question (Q-6).")
    W("kicad.erc.ground_pin_not_ground", r"HGND",
      "HGND of U401/U421/U441 is the isolated high-side ground, tied to the HV domain reference HV_N / HV_RTN as the "
      "AMC datasheets require; KiCad's rule only recognises nets named like GND.")
    W("rating.voltage", r"^K90[12] .*COIL",
      "A 12 V coil on the 12.1 V AUX12 rail is the rated operating point; 110 % (13.2 V) is the datasheet maximum, "
      "not a derating base. After 100 ms pull-in the coil is PWM-held at 45-60 % (K340-E1-06 p.1, 5).")


def build():
    d = Design("prius-solar-mppt", title="Prius Prime solar MPPT charger",
               description="Roof C60 array (2 x 28 cells) -> 2 analog MPPT buck-boost -> reinforced LLC-DCX 1:22 -> "
                           "battery-end board with fuses, blocking diode and 2-pole disconnect on the Prime Li-ion "
                           "pack; own SOC/voltage/temperature layers for charging while the car sleeps.",
               revision="B", author="kaesynth design agent", brief=BRIEF, ambient_c=(-40, 85))
    intent(d)
    domains(d)
    mppt(d, "A", 100)
    mppt(d, "B", 200)
    dcx(d)
    hvsense(d)
    limiter(d)
    safety(d)
    aux(d)
    mcu(d)
    batt_end(d)
    array(d)
    harness(d)
    calcs(d)
    boards(d)
    placement(d)
    waivers(d)
    return d
