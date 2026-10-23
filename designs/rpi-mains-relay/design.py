# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""rpi-mains-relay: six individually switched 120 VAC receptacles run by an on-board Raspberry Pi Zero 2 W.

Encodes designs/rpi-mains-relay/DESIGN.md (engineering rationale, evidence tags, sources) and
CONNECTIONS.md (pin rationale). Build: `kaesynth build designs/rpi-mains-relay/design.py -v`.
Custom footprints: footprints/make_footprints.py writes footprints/custom.pretty/.

Assembly: E1 = polycarbonate UL 50 enclosure (this PCB, the Pi on J5, the IRM-20-5 supply);
E2 = 3-gang PVC device box with three split-tab TR duplex receptacles; three 14/3 NM-B cables join them.

Domain model:
  LINE    root, ref L_IN. The line conductor is the 0 V of the mains side, so the voltage across an open
          relay contact (L_IN to L_SWk) is exact (+/-187 V peak) instead of an envelope sum.
  NEUTRAL floats on L_IN (N is +/-187 V peak from L).
  OUT1..6 float on L_IN: a switched output is L when its relay is closed and is pulled to N by the load
          when open, so +/-187 V peak from L.
  SELV    root, ref GND: IRM-20-5 output, Pi Zero 2 W, coil drive and watchdog. Floating (Class II supply).
  PE      root, ref PE: EGCs and receptacle yokes. No copper on the PCB; kept so the mains-to-PE spacing
          reaches intent.yaml and the DRU edge rule.
"""
import importlib.util
import math
from pathlib import Path

from kaesynth import Design, Hole

_spec = importlib.util.spec_from_file_location("rpi_mains_relay_parts", Path(__file__).with_name("parts.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

BRIEF = ("I want you to make a breakout board for a Raspberry Pi that has the ability to switch 120 volts. "
         "Maybe 4 or 6 of them. It should use stuff that is reliable. It should have terminals that make it "
         "really easy to access. Maybe all with shared inputs and then a whole bunch of outputs or something "
         "like that. Kind of like the outlets. It should probably be mounted into an outlet type box.")

V_MAINS_PK = 187.0          # 132 Vrms (120 V + 10 %) x sqrt(2)
I_BRANCH = 15.0             # branch breaker ceiling, A
W_MAINS = 7.5               # mains current-path width per layer, mm (2 oz, both layers; calc C-7)
CHANNELS = (1, 2, 3, 4, 5, 6)
# Pi Zero 2 W 40-pin header: channel GPIOs (all default pull-down, BCM >= 9; RPi docs 'GPIO' pad table)
PI_PIN = {1: 11, 2: 13, 3: 15, 4: 16, 5: 18, 6: 22}
PI_BCM = {1: 17, 2: 27, 3: 22, 4: 23, 5: 24, 6: 25}
PIN_HB, PIN_ARM_FB = 32, 36          # BCM12, BCM16
PINS_5V, PINS_3V3 = (2, 4), (1, 17)
PINS_GND = (6, 9, 14, 20, 25, 30, 34, 39)
TERM = {1: ("J2", "1"), 2: ("J2", "3"), 3: ("J3", "1"), 4: ("J3", "3"), 5: ("J4", "1"), 6: ("J4", "3")}
# board geometry (mm, origin lower-left, y north). Pi Zero 2 W: left edge x = PI_X0, connector edge y = PI_Y0
BOARD_W, BOARD_H = 200.0, 150.0
PI_X0, PI_Y0 = 12.0, 1.0


def pi_xy(xd, yd):
    """Zero 2 W drawing coordinates (x from the SD-card end, y down from the header edge) -> board."""
    return PI_X0 + xd, PI_Y0 + 30.0 - yd


def intent(d):
    # -- requirements (DESIGN.md section 2) --------------------------------------------------------
    R = d.require
    R("REQ-1", "Supply: 120 VAC nominal, 60 Hz, 1-phase, L + N + EGC; single 2-wire branch, not a MWBC",
      value="108-132 V, 60 Hz", source="brief; ASM-1", verify="inspection, T-FUNC")
    R("REQ-2", "Branch: 15 A breaker with GFCI protection (NEC 210.8) and AFCI where 210.12 applies; default a "
      "15 A dual-function AFCI/GFCI breaker; Cu 14 AWG min (12 AWG allowed)", value="15 A",
      source="NEC 210.8, 210.12, 240.4(D) [S]; relays 16 A (C-9)", verify="label, install check (Q-6)")
    R("REQ-3", "Six individually switched outlets: three split-tab duplex NEMA 5-15R receptacles, one relay per "
      "outlet", value="6", source="Q-2, Q-4 (user decisions)", verify="T-FUNC")
    R("REQ-4", "Switch line only; neutral not switched; EGC never through the PCB", value="-",
      source="NEC 404.2(B) [I], 250.148(B) [S]", verify="netlist review")
    R("REQ-5", "Per-outlet rating", value="<= 15 A general use, <= 12 A continuous; <= 1/2 hp at 120 V (9.8 A FLA); "
      "tungsten <= TV-8 (TV-5 with the HR second source); capacitive inrush <= 100 A peak",
      source="relay UL/VDE ratings [P]", verify="T-LOAD, T-OL")
    R("REQ-6", "Total current, all outlets", value="<= 15 A; <= 12 A for loads on >= 3 h",
      source="branch OCPD; NEC 210.19/210.20 [S]", verify="T-HEAT")
    R("REQ-7", "Enclosures: E1 listed nonmetallic UL 50 Type 4X/12 polycarbonate enclosure for the board, Pi and "
      "supply; E2 listed nonmetallic 3-gang device box for the receptacles; joined by three 14/3 NM-B cables; both "
      "surface-mounted indoors; no ventilation openings", value="Carlon NS1086 + JP108P; Carlon BH353A",
      source="Q-3, Q-4, Q-8; C-1, C-6, C-13", verify="inspection")
    R("REQ-8", "Box fill: E2 per NEC 314.16; E1 > 100 in3 (outside the 314.16(A) table) shown with free space",
      value="E2 <= 53 in3", source="NEC 314.16 [S/I]", verify="calc box_fill_*")
    R("REQ-9", "Field terminals in E1: lever push-in, UL 1059 >= 300 V / >= 20 A, 14-12 AWG Cu; one (L, N) input, "
      "three (OUTa, N, OUTb) receptacle feeds", value="WAGO 2606, 600 V 31 A",
      source="brief ('really easy to access', 'shared inputs ... outputs')", verify="inspection")
    R("REQ-10", "Mains <-> SELV reinforced everywhere: PCB creepage/clearance; relay coil-contact; AC/DC module; "
      "field conductors kept out of the PCB/Pi compartment by partition MP1", value=">= 8.0 mm / >= 8.0 mm; module "
      "Class II 4.2 kVAC; 3 kVrms 60 s hi-pot", source="UL/IEC 62368-1, IEC 60664-1 (C-8)",
      verify="T-CREEP, T-HIPOT")
    R("REQ-11", "Opposite-polarity mains spacing (L or L_SWk to N; L_SWj to L_SWk)",
      value="creepage >= 6.4 mm, clearance >= 3.2 mm", source="UL 1059 use group C [S]", verify="T-CREEP")
    R("REQ-12", "Mains copper to a board edge or mounting hole (where a bare EGC can lie)",
      value=">= 6.4 mm (DRU edge_clearance)", source="UL field wiring 1/4 in to dead metal [S]", verify="DRC")
    R("REQ-13", "Fail-safe OFF: all outlets OFF when the Pi is absent, unpowered, booting, rebooting, halted or "
      "hung, when its SD card fails, when the 5 V supply sags or fails, and after the heartbeat stops at either "
      "level", value="<= 0.1 s after the last heartbeat edge", source="brief ('reliable'); review M1",
      verify="T-BOOT, T-HB, T-BROWNOUT")
    R("REQ-14", "Two-key rule: no single stuck GPIO or single shorted driver energizes an outlet while the "
      "heartbeat is absent", value="-", source="derived", verify="FMEA (hazards), T-HB")
    R("REQ-15", "Load on the Pi", value="<= 0.7 mA per CH pin; +3V3 <= 1 mA; only default-pull-down GPIOs",
      source="RPi docs GPIO pad table [P]", verify="T-PWR")
    R("REQ-16", "Heartbeat arms the outlets; DC (either level) or no signal disarms them",
      value="3.3 V square wave 100 Hz-10 kHz, 20-80 % duty, toggled by the control loop", source="C-4",
      verify="T-HB")
    R("REQ-17", "Coil voltage at the relay pins, worst case", value=">= 4.5 V", source="must-operate [P]; C-3",
      verify="T-COIL (also at 4.63 V)")
    R("REQ-18", "Leakage at an OFF outlet (no snubber or MOV across the contacts)", value="<= 0.1 mA",
      source="derived (C-12)", verify="T-LEAK")
    R("REQ-19", "Thermal: internal air of E1 at 40 C room with all coils on, 15 A through one outlet and the Pi "
      "at full load", value="<= 60 C (Pi <= 70 C, IRM within derating)", source="derived (C-6)", verify="T-HEAT")
    R("REQ-20", "Fault withstand: mains copper survives the branch breaker's let-through; F1 interrupts any "
      "fault at E1", value="available fault <= 2 kA (copper), F1 10 kA at 125 VAC", source="C-7, C-9",
      verify="T-SC")
    R("REQ-21", "Indicators on the SELV side: LED per channel (coil energized), ARM LED, 5 V LED", value="8 LEDs",
      source="task", verify="T-FUNC")
    R("REQ-22", "Environment", value="indoor dry, PD2, OVC III (conservative), <= 2000 m, room 0-40 C",
      source="ASM-2; review m7", verify="-")
    R("REQ-23", "Parts active and orderable; listed/recognized relays, terminals, supply module, fuse, receptacles, "
      "enclosures, PCB laminate", value="-", source="brief ('reliable')", verify="BOM review")
    R("REQ-24", "Installation by a licensed electrician; approval by the authority having jurisdiction (AHJ)",
      value="-", source="NEC 110.2/110.3 [I]", verify="Q-1")
    R("REQ-25", "Markings: ratings, conductor size and strip length, terminal labels, 'disconnect before opening', "
      "'outlets are not a disconnecting means', Pi orientation", value="-", source="UL practice [I]",
      verify="inspection")
    R("REQ-26", "Pi: Raspberry Pi Zero 2 W, component side up on J5, 2x20 header soldered on its underside; no "
      "USB/HDMI peripherals; powered only through J5 pins 2/4, never also from its micro-USB",
      value="Zero 2 W only", source="Q-5 (user decision)", verify="inspection, T-PWR")
    R("REQ-27", "5 V supply: listed encapsulated AC/DC module from the shared L/N input through its own fuse; 5 V "
      "budget within its derated capacity", value="IRM-20-5, F1 1 A T; <= 1.9 A at 70 C, 108 VAC",
      source="Q-5; C-2, C-9", verify="T-PWR, T-BROWNOUT")
    R("REQ-28", "Watchdog readback and self-test: ARM_FB on BCM16. Software checks disarmed -> armed -> disarmed "
      "(timing) at boot and whenever all outlets are off (at least daily); on failure it never arms, keeps all "
      "outlets off and alarms", value="disarm measured <= 0.1 s", source="review M2", verify="T-SELFTEST")
    R("REQ-29", "Software: read-only root filesystem (overlay), power-safe logging, all outlets OFF at boot, "
      "heartbeat from the control loop, documented power-restore policy (default OFF)", value="-",
      source="review M2; H17", verify="code review, T-BOOT")
    R("REQ-30", "Wi-Fi: Pi PCB antenna inside a nonmetallic enclosure; antenna zone free of copper on all layers; "
      ">= 30 mm from relays, mains copper and the supply", value="RSSI >= -67 dBm at the install location",
      source="C-13", verify="T-RF")
    R("REQ-31", "E1 compartments: field-wiring compartment (north) separated from the PCB/Pi compartment by "
      "partition MP1; no exposed copper outside the terminal bodies north of MP1; conductors tied down",
      value="-", source="review M3", verify="inspection")

    # -- assumptions and questions (DESIGN.md section 3) -------------------------------------------
    A = d.assume
    A("ASM-1", "North-American dwelling or light commercial; one 120 V branch from a 15 A breaker; available "
      "fault current at E1 <= 2 kA (>= 10 m of 14 AWG limits it to < 1 kA)")
    A("ASM-2", "Indoor dry location, PD2, altitude <= 2000 m, room 0-40 C; E1 and E2 surface-mounted on a wall or "
      "backboard, not in an insulated cavity")
    A("ASM-3", "Loads are plug-in appliances, LED or tungsten lighting, small motors; none hazardous if left "
      "on (a welded contact is a credible failure)")
    A("ASM-4", "Pi Zero 2 W draws <= 0.6 A at full CPU load (published measurements); the budget allows 1.0 A")
    A("ASM-5", "PCB laminate taken as material group IIIb (CTI >= 100 V) so the tables apply at their most "
      "conservative; FR-4 is usually IIIa")
    A("ASM-6", "Control software toggles HB at >= 100 Hz from its main loop while any outlet should be on")
    A("ASM-7", "The hardware retains no output state: every Pi reboot or power cut leaves all outlets OFF")
    A("ASM-8", "Zero 2 W antenna lies on the connector edge between the mini-HDMI and the USB socket (as on the "
      "Zero W; inferred, verify on the board)")
    Q = d.question
    Q("Q-1", "Certification path: who evaluates (AHJ field evaluation) and who installs (licensed electrician) "
      "this unlisted assembly? If neither is acceptable, buy listed products.", blocking=True,
      default="designed to UL/IEC 62368-1 spacings with listed/recognized parts; licensed electrician installs; "
              "not certified")
    Q("Q-2", "Outputs: terminals for field wiring, or receptacles in the box?", blocking=True,
      answer="Switched receptacles: actual receptacles in the box that loads plug into, each outlet individually "
             "switched (e.g. split-tab duplex receptacles, one relay per outlet).")
    Q("Q-3", "Where does the Raspberry Pi live and how is it powered?", blocking=True,
      answer="Inside, plugged on the board: a self-contained box; the Pi mounts on/plugs onto our board, powered "
             "from an on-board safety-certified AC/DC module fed from the shared input.")
    Q("Q-4", "How many channels, and in what box?", blocking=True,
      answer="6 channels, bigger box: choose a larger listed box/enclosure that legally holds 3 duplex receptacles "
             "(6 outlets) plus the board, the Pi and the supply.")
    Q("Q-5", "Which Pi, and where does its power come from?", blocking=True,
      answer="also the pi should get its power from the 120Vac in the box, so it will need some power conversion "
             "stuff. design this for a zero 2W")
    Q("Q-6", "Branch protection: 15 A dual-function AFCI/GFCI breaker? (GFCI is required in kitchens, baths, "
      "garages, basements, laundry, outdoors; AFCI in most dwelling rooms.) A 20 A circuit must be re-breakered "
      "at 15 A.", blocking=True, default="15 A dual-function AFCI/GFCI breaker")
    Q("Q-7", "Load list: any heaters, pumps, compressors or life-safety loads that are unsafe if a contact "
      "welds? Motors cycled more than about 5 times a day should drive a contactor.", blocking=True,
      default="general plug loads, no hazard-if-on loads")
    Q("Q-8", "Accept a two-box assembly: E1 (10 x 8 x 6 in polycarbonate, electronics) next to E2 (3-gang PVC "
      "device box, receptacles), joined by three short 14/3 NM-B cables? No listed nonmetallic box was found that "
      "takes duplex receptacles and the electronics together.", blocking=True,
      default="two boxes side by side on one backboard")
    Q("Q-9", "Partition MP1: confirm 1.5 mm polycarbonate UL 94 V-0, fixed to the back panel at both ends, and "
      "AHJ acceptance as the wiring/electronics separation.", default="as specified")
    Q("Q-10", "Watchdog semantics: OFF when the control app hangs (software heartbeat) or keep ON through app "
      "hangs (hardware-PWM heartbeat)?", default="software heartbeat, outlets OFF on hang")
    Q("Q-11", "Power-restore policy: outlets stay OFF after a power cut until the user switches them, or the app "
      "restores the last state after its self-test?", default="stay OFF")
    Q("Q-12", "Surge protection: listed Type 2 SPD at the panel instead of an MOV in the box?", default="no MOV in box")
    Q("Q-13", "Relay supply (Omron -> Aratas): qualify the second source.",
      default="G5RL-1A-E-HR DC5 drop-in, TV-5 limit")
    Q("Q-14", "Pi header: the user solders a 2x20 header on the Zero 2 W underside. A Zero 2 WH (header on top) "
      "would have to sit face-down and mirrors the pinout; it is NOT supported.", default="solder on the underside")
    Q("Q-15", "Generic hardware (nylon standoffs, NM connectors, wallplate, splice) to be fixed to MPNs.",
      default="specs in the BOM descriptions")
    Q("Q-16", "Add per-channel readback (detects a shorted channel MOSFET)? Six more GPIOs and 18 parts.",
      default="no; the channel LED shows it")


def hazards(d):
    H = d.hazard
    relays = [f"K{k}" for k in CHANNELS]
    terms = ["J1", "J2", "J3", "J4"]
    chq = [f"Q{k}" for k in CHANNELS]
    H("H1", "Shock from live parts with E1 or E2 open",
      "listed enclosures with screw covers (tool needed); 'disconnect before opening' label; electrician installs; "
      "partition MP1 keeps field conductors away from the Pi/SD-card area", parts=["MP1", "MP2", "MP4"],
      single_fault_safe=False, notes="service condition: de-energize at the breaker before opening")
    H("H2", "Mains reaches SELV, the Pi or a person touching the Pi",
      "reinforced insulation: IRM-20-5 Class II 4.2 kVAC; relays 8/8 mm 6 kVAC 10 kV; PCB 8/8 mm barrier band; "
      "partition MP1 adds supplementary insulation over field-conductor insulation; no SELV wiring leaves E1",
      parts=relays + ["PS1", "MP1"], single_fault_safe=True)
    H("H3", "Bare EGC or receptacle yoke contacts live copper",
      "nonmetallic enclosures (no box metal); EGCs spliced in the wire compartment with a listed connector; "
      "mains copper >= 6.4 mm from board edges and mounting holes (DRU edge rule); no copper outside the "
      "terminal bodies north of MP1", parts=terms + ["MP1", "MP16"], single_fault_safe=True)
    H("H4", "Overload heats conductors, PCB, terminals, relays or receptacles",
      "single protective device = 15 A branch breaker; every downstream element rated >= 15 A at temperature "
      "(calcs mains_copper_*, relay_contact_*); receptacles 15 A", parts=terms + relays + ["MP5", "MP6", "MP7"],
      single_fault_safe=True, notes="15-20 A overloads before the breaker trips are covered by T-OL")
    H("H5", "Short circuit on an outlet or in the supply module",
      "breaker clears outlet faults (copper I2t margin 1.4x at 2 kA); F1 (1 A T, 10 kA at 125 VAC) clears a "
      "module fault before the breaker; UL 50 polycarbonate enclosure contains the arc",
      parts=terms + ["F1", "MP2"], single_fault_safe=True)
    H("H6", "Loose or partially inserted conductor heats up",
      "spring clamps (no torque relaxation); strip length on silkscreen; pull test at commissioning; receptacles "
      "back-wired under clamp plates, not push-in", parts=terms + ["MP5", "MP6", "MP7"], single_fault_safe=False,
      notes="inspection is the barrier")
    H("H7", "Fail-ON: welded relay contact",
      "inrush-rated relay (TV-8, 100 A peak); load limits REQ-5; no snubber; documented that outlets are not "
      "for loads hazardous if left on", parts=relays, single_fault_safe=False, notes="residual risk, disclosed (Q-7)")
    H("H8", "Fail-ON from control: software bug, hung Pi, stuck GPIO, shorted MOSFET",
      "coil current needs both Qk (CH GPIO) and Q7 (U1 heartbeat monostable); 4.7 k pull-downs; HB edge-triggered",
      parts=chq + ["Q7", "U1", "R21", "C6", "R22", "R7", "R8", "R9", "R10", "R11", "R12"], single_fault_safe=False,
      notes="hung software, stuck GPIO or shorted Q7: safe (the other key still blocks; Q7 short is caught by the "
            "self-test). Shorted Qk while the heartbeat runs: outlet k follows ARM (its LED shows it); stopping "
            "the heartbeat turns it OFF")
    H("H9", "Glitch to ON at boot, reset or power-up",
      "default-pull-down GPIOs plus 4.7 k / 100 k pull-downs; U1 glitch-free power-up reset; arming needs "
      "rising edges on B; Q7 gate pull-down holds it off while U1 is unpowered (Ioff)",
      parts=["U1", "R22", "R23", "R7", "R8", "R9", "R10", "R11", "R12"], single_fault_safe=True)
    H("H10", "Remote energization while a load is being serviced",
      "label: outlets are not a disconnecting means; unplug the load or lock out the breaker", parts=[],
      single_fault_safe=False, notes="procedural by nature")
    H("H11", "Shock from an 'OFF' outlet",
      "no snubber or MOV across contacts; line-only switching; polarity check at commissioning", parts=relays,
      single_fault_safe=False, notes="leakage: single-fault safe; L/N miswire: procedural (T-MISWIRE)")
    H("H12", "Overtemperature in the closed enclosure",
      "13.3 W worst case into 0.21 m2 of polycarbonate: 52 C at 40 C room (C-6); surface mounting; 12 A continuous "
      "limit", parts=["MP2", "PS1"], single_fault_safe=True)
    H("H13", "Surge flashover or arc tracking",
      "OVC III coordinated spacing; relay 10 kV impulse; IRM-20 tested to 2 kV L-N; no MOV in the box; panel SPD "
      "recommended", parts=relays + ["PS1"], single_fault_safe=True)
    H("H14", "Pi fitted wrongly: face-down (Zero 2 WH) or offset by a row, putting 5 V on GPIO pins",
      "Zero 2 W only, header on its underside; socket footprint uses the Pi's own top-view numbering; Pi outline, "
      "'components up' and pin-1 marks on silkscreen; standoffs only line up with the correct orientation",
      parts=["J5", "MP9", "MP10"], single_fault_safe=False, notes="assembly error; inspection before power-up")
    H("H15", "Motor stall on an outlet",
      "the motor's own overload protection (NEC 430); 1/2 hp relay rating; contactor for larger motors",
      parts=[], single_fault_safe=False, notes="load-side protection, outside this board")
    H("H16", "Supply module failure: output lost, output high, or input short",
      "lost 5 V: coils drop and the Pi stops -> OFF; high: module OVP 5.75-6.75 V shuts it down, TVS D15, coil "
      "max 6.5 V; input short: F1 opens; PTC F2 limits a Pi-side short", parts=["PS1", "F1", "F2", "D15"],
      single_fault_safe=True)
    H("H17", "Pi reboot, kernel hang or SD-card corruption leaves outlets in an unknown state",
      "any stop of the heartbeat disarms within 0.1 s (C-4); a Pi that cannot boot never arms; read-only root "
      "filesystem (REQ-29) makes corruption unlikely; self-test before arming (REQ-28)",
      parts=["U1", "Q7", "R24", "R25", "D16"], single_fault_safe=True)
    H("H18", "Watchdog part failure (U1, R21, C6, Q7, R22, divider) arms without a heartbeat",
      "readback ARM_FB and self-test: U1 Q stuck high, C6 or R21 open/short and Q7 D-S short all show as 'armed "
      "while HB stopped' or 'disarm too slow' and block operation; Q7 open or U1 Q stuck low cannot arm (safe)",
      parts=["U1", "R21", "C6", "Q7", "R22", "R24", "R25", "R26", "D16"], single_fault_safe=True,
      notes="FMEA table in DESIGN.md section 5")
    H("H19", "Ground fault in a plugged-in load",
      "GFCI protection of the branch (REQ-2, Q-6); EGC to every receptacle; module leakage 0.12 mA << 4 mA trip",
      parts=["MP5", "MP6", "MP7"], single_fault_safe=True, notes="GFCI device is upstream, not on this board")


def calcs(d):
    c = d.calc
    # C-1 box fill
    c("box_fill_E2_14awg_in3", 9 * 2.0 + 2.0 + 3 * 2 * 2.0 + 2.0, "in3",
      expr="9 conductors (3 x 14/3) x 2.0 + EGCs 2.0 + 3 devices x 2 x 2.0 + clamps 2.0", limit=53.0,
      note="Carlon BH353A 53 in3 (NEC 314.16(B))")
    c("box_fill_E2_12awg_in3", 9 * 2.25 + 2.25 + 3 * 2 * 2.25 + 2.25, "in3", expr="same with 12 AWG (2.25 in3)",
      limit=53.0)
    e1_gross = 9.9 * 7.9 * 5.98
    c("box_free_E1_in3", round(e1_gross - (12 * 2.25 + 200 * 150 * 45 / 16387.0), 0), "in3",
      expr="NS1086 inside ~9.9 x 7.9 x 5.98 in - 12 conductor allowances x 2.25 - board assembly 82 in3",
      limit=0, op=">=", note="> 100 in3 box: 314.16(A) table not applicable, free space shown")
    # C-2 5 V budget and supply capacity
    i_pi = 1.0
    i_coils = 6 * 5.125 / 56.25
    i_leds = 8 * (5.125 - 1.9) / 1500
    i5 = i_pi + i_coils + i_leds + 0.002
    c("i_5v_max_A", round(i5, 3), "A", expr="Pi 1.0 + 6 coils x 5.125 V / 56.25 ohm + 8 LEDs x 2.15 mA + 2 mA")
    cap = 4.0 * 0.50 * 0.95
    c("psu_capacity_70C_108V_A", cap, "A", expr="IRM-20-5 4 A x 50 % (70 C) x 95 % (108 VAC)")
    c("psu_load_ratio_worst", round(i5 / cap, 3), "", expr="i_5v_max / capacity at 70 C, 108 VAC", limit=0.9)
    c("psu_load_ratio_60C", round(i5 / (4.0 * 0.70 * 0.95), 3), "", expr="at 60 C (70 %) and 108 VAC", limit=0.8)
    c("gpio_ch_current_mA", round(3.3 / 4.8, 3), "mA", expr="3.3 V / (100 + 4.7 k)", limit=0.7, note="REQ-15")
    c("pi_5v_at_socket_V", round(4.875 - 1.0 * 0.070 - 0.02 - 0.01, 3), "V",
      expr="4.875 (5 V -2.5 %) - F2 1.0 A x 0.070 - trace 0.02 - contacts 0.01", limit=4.63, op=">=",
      note="Pi under-voltage threshold ~4.63 V [S]")
    # C-3 coil voltage
    drop = 0.55 * 0.02 + 0.093 * 0.048 + 0.55 * 0.048 + 0.55 * 0.02
    c("coil_voltage_worst_V", round(4.875 - drop, 3), "V",
      expr="4.875 - (0.55 A x 20 mOhm trace + Qk 0.093 x 48 mOhm + Q7 0.55 x 48 mOhm + return 0.55 x 20 mOhm)",
      limit=4.5, op=">=", note="REQ-17")
    must_hot = 70 * (234.5 + 95) / 257.5
    c("must_operate_hot_pct", round(must_hot, 1), "%", expr="70 % x (234.5 + 95 C) / 257.5 (60 C air + 35 K coil rise)",
      limit=round(100 * (4.875 - drop) / 5.0, 1), note="vs coil_voltage_worst; T-COIL also at 4.63 V")
    c("coil_voltage_max_pct", round(100 * 5.25 / 5.0, 1), "%", expr="5.25 V / 5.0 V", limit=130)
    # C-4 heartbeat watchdog: U1 74LVC1G123, R21 330 k, C6 100 nF X7R
    tw_min = 1.0 * 330e3 * 100e-9 * 0.99 * 0.90 * 0.85
    tw_max = 1.1 * 330e3 * 100e-9 * 1.01 * 1.10 * 1.15
    c("wd_tw_min_ms", round(tw_min * 1e3, 1), "ms", expr="K 1.0 x 330 k x 100 nF x R -1 % x C -10 % x X7R -15 %")
    c("wd_tw_max_ms", round(tw_max * 1e3, 1), "ms", expr="K 1.1 x 330 k x 100 nF x R +1 % x C +10 % x X7R +15 %")
    c("wd_hb_period_margin", round(tw_min / 0.010, 2), "x", expr="tw_min / 10 ms (HB >= 100 Hz)", limit=2.0, op=">=")
    rel = 0.015
    c("disarm_hb_stuck_high_s", round(tw_max + 1e-6 + rel, 4), "s",
      expr="no rising edge on B: Q falls tw_max after the last edge + gate fall (push-pull, ns) + release 15 ms",
      limit=0.1, note="REQ-13; release 5 ms max without diode [P], 15 ms allowed with the flyback diode [I]")
    c("disarm_hb_stuck_low_s", round(tw_max + 1e-6 + rel, 4), "s",
      expr="identical: B is edge-triggered, so a low level cannot hold Q either", limit=0.1, note="REQ-13")
    c("arm_gate_V", round(3.3 * 0.95 - 0.1, 3), "V", expr="VOH >= VCC - 0.1 V (100 uA), VCC = 3.3 V - 5 %",
      limit=2.5, op=">=", note="AO3400A Rds(on) specified at Vgs 2.5 V (review m1)")
    # C-5 gate drive and readback levels
    c("gate_on_V", round(3.0 * 4.7 / 4.8, 3), "V", expr="VOH 3.0 V (RP3A0, 2 mA) x 4.7 k / 4.8 k", limit=2.5, op=">=",
      note="review m1")
    c("gate_pullup_misconfig_V", round(3.3 * 4.7 / (4.7 + 0.1 + 50), 3), "V",
      expr="internal pull-up 50 k enabled by mistake: 3.3 x 4.7 / 54.8", limit=0.65, note="< AO3400A Vgs(th) min")
    v_rtn_off = 4.875 * (47 + 68) / (10 + 47 + 68)
    c("arm_fb_disarmed_V", round(v_rtn_off * 68 / 115, 3), "V",
      expr="COIL_RTN = 4.875 x 115 k / 125 k (R26 pull-up); x 68 / 115", limit=1.6, op=">=", note="RP3A0 VIH 1.6 V")
    c("arm_fb_armed_V", round(0.55 * 0.048 * 68 / 115, 4), "V", expr="0.55 A x 48 mOhm x 68/115", limit=0.9,
      note="RP3A0 VIL 0.9 V")
    c("arm_fb_max_steady_V", round(5.25 * 68 / 115, 3), "V", expr="COIL_RTN 5.25 V (disarmed, a CH on) x 68/115",
      limit=3.3, note="flyback transients above this are clamped by D16 to +3V3")
    # C-6 thermal (E1, NS1086 polycarbonate, wall-mounted: back face excluded)
    area = (2 * 10.4 * 6.49 + 2 * 8.4 * 6.49 + 10.4 * 8.4) * 0.00064516
    parts_w = {"coils": 6 * 5.125 ** 2 / 56.25, "contacts": 15 ** 2 * 0.010, "pcb_copper": 15 ** 2 * 0.0057,
               "terminals": 4 * 15 ** 2 * 0.001, "conductors": 15 ** 2 * 0.0048, "psu": 5.82 * (1 / 0.76 - 1),
               "pi": 3.0, "leds_misc": 0.14}
    p_tot = sum(parts_w.values())
    c("e1_dissipation_W", round(p_tot, 2), "W",
      expr=" + ".join(f"{k} {v:.2f}" for k, v in parts_w.items()))
    c("e1_area_m2", round(area, 4), "m2", expr="2 x 10.4 x 6.49 + 2 x 8.4 x 6.49 + 10.4 x 8.4 in2 (back excluded)")
    t_air = 40 + p_tot / (5.0 * area)
    c("e1_internal_air_C", round(t_air, 1), "C", expr="40 C room + P / (5.0 W/m2K x area)", limit=60,
      note="h = 5.0 for a sealed polycarbonate box (5.5 convection+radiation, 3.5 mm PC wall) [I]")
    c("pi_ambient_margin_K", round(70 - (t_air + 7), 1), "K", expr="Pi max 70 C - (air + 7 K local)", limit=0,
      op=">=")
    # C-7 mains copper
    c("mains_copper_width_per_layer_mm", W_MAINS, "mm", limit=6.3, op=">=",
      note="IPC-2221 single-layer width for 15 A, 10 K, 2 oz = 6.3 mm; 7.5 mm on both layers (Net width_mm)")
    c("mains_copper_dT_K", 1.6, "K", expr="IPC-2221 external, 7.5 A per layer in 813 mil2", limit=10)
    c("mains_fault_i2t_margin", round(92 / 67, 2), "x",
      expr="Onderdonk melt 92 kA2s / breaker let-through 67 kA2s at 2 kA in 1 cycle", limit=1.0, op=">=")
    # C-8 creepage and clearance at OVC III (review m7)
    c("barrier_clearance_margin_ovc3", round(8.0 / 3.0, 2), "x",
      expr="8.0 / 3.0 mm (reinforced = 4 kV impulse, IEC 60664-1 F.2 PD2)", limit=1.0, op=">=")
    c("barrier_creepage_margin_120V", round(8.0 / 3.0, 2), "x", expr="8.0 / (2 x 1.5 mm, F.4 125 V MG III)",
      limit=1.0, op=">=")
    c("functional_clearance_margin_ovc3", round(3.2 / 1.5, 2), "x", expr="3.2 / 1.5 mm (2.5 kV, F.2)", limit=1.0,
      op=">=")
    # C-9 protection coordination
    c("relay_contact_current_ratio", round(15 / 16, 3), "", expr="15 A breaker ceiling / 16 A UL general use",
      limit=1.0)
    c("relay_contact_continuous_ratio", 12 / 16, "", expr="12 A continuous / 16 A", limit=0.8)
    c("f1_load_ratio_60C", round(0.6 / (1.0 * 0.9), 3), "", expr="0.6 A (module full load) / (1 A x 0.9 at 60 C)",
      limit=0.75)
    c("f1_breaking_margin", round(10000 / 2000, 1), "x", expr="10 kA at 125 VAC / 2 kA available (ASM-1)", limit=1.0,
      op=">=")
    c("ptc_hold_at_70C_A", 1.43, "A", expr="MF-MSMF200/16X derating table", limit=1.0, op=">=",
      note="Pi branch allowance 1.0 A (review m10)")
    c("tvs_standoff_ratio", round(5.25 / 7.0, 2), "", expr="5.25 V / VWM 7.0 V", limit=0.8)
    # C-10..C-13
    c("relay_life_years_10ops_day", round(15000 / 10 / 365, 1), "years",
      expr="VDE 16 A / 85 C rating 15k ops (worst) / 10 ops a day", limit=3, op=">=",
      note="UL general use 50k ops at 40 C; frequently cycled motors should drive a contactor")
    c("off_state_leakage_mA", 0.0002, "mA", expr="187 V / 1000 Mohm open-contact insulation", limit=0.1)
    c("selv_touch_current_mA", round(0.25 * 132 / 277, 3), "mA",
      expr="IRM leakage < 0.25 mA at 277 VAC scaled to 132 VAC", limit=0.5, note="62368-1 ES1 touch current [I]")
    c("gfci_leakage_ratio", round(0.25 * 132 / 277 / 4.0, 3), "", expr="module leakage / 4 mA GFCI no-trip",
      limit=0.5)
    c("hold_up_ms_est", round(8 * 20 / (5 * (0.6 + i_coils + i_leds)), 1), "ms",
      expr="8 ms at 20 W (115 VAC) x 20 W / 5.8 W actual [I]",
      note="rides through a 1-cycle dropout; longer cuts reset the Pi -> OFF")
    c("wifi_enclosure_loss_dB", 1.0, "dB", expr="3.5 mm polycarbonate at 2.4 GHz, < 1 dB [I]",
      note="steel box: > 30 dB (rejected)")


def build():
    d = Design("rpi-mains-relay", title="RPi Zero 2 W six-outlet 120 VAC relay board (polycarbonate enclosure)",
               description="6 x 16 A relays switch line to 3 split-tab TR duplex receptacles; on-board Pi Zero 2 W "
                           "fed by a Mean Well IRM-20-5; heartbeat watchdog",
               brief=BRIEF, ambient_c=(0, 60))
    intent(d)

    # -- domains and global nets -------------------------------------------------------------------
    edge_src = ("UL 1059/508 field wiring: 1/4 in (6.4 mm) through air and over surface from live parts to dead "
                "or grounded metal; a bare EGC may lie against a board edge or a mounting-hole standoff (H3)")
    d.net("L_IN", domain="LINE", v=0, kind="mains", i_max=I_BRANCH, external=True, threats=("surge", "overcurrent"),
          width_mm=W_MAINS, notes="line from the branch circuit; reference of the mains side")
    d.domain("LINE", ref="L_IN", kind="mains", description="mains line conductor (root; 120 VAC 60 Hz, OVC III)",
             edge_clearance_mm=6.4, edge_source=edge_src)
    d.net("N", domain="NEUTRAL", v=(-V_MAINS_PK, V_MAINS_PK), kind="mains", i_max=I_BRANCH, external=True,
          threats=("surge",), width_mm=W_MAINS, notes="neutral; not switched")
    d.domain("NEUTRAL", ref="L_IN", kind="mains", description="neutral, +/-187 V peak from line")
    for k in CHANNELS:
        d.net(f"L_SW{k}", domain=f"OUT{k}", v=(-V_MAINS_PK, V_MAINS_PK), kind="mains", i_max=I_BRANCH,
              external=True, threats=("overcurrent",), width_mm=W_MAINS,
              notes=f"switched line, outlet {k}: equals L_IN when K{k} is closed, pulled to N by the load when open")
        d.domain(f"OUT{k}", ref="L_IN", kind="mains", description=f"switched outlet {k}, floats on line")
    d.net("PE", domain="PE", v=0, kind="pe", external=True,
          notes="protective earth: EGCs spliced in E1, receptacle yokes in E2; no copper on this PCB")
    d.domain("PE", ref="PE", kind="other", earthed=True, description="protective earth, off-board")

    gnd = d.net("GND", domain="SELV", v=0, kind="ground", i_max=1.6,
                notes="IRM-20-5 -Vo; Pi ground; floating (Class II supply)")
    d.domain("SELV", ref="GND", kind="selv",
             description="IRM-20-5 output, Pi Zero 2 W, coil drive and watchdog (ES1, LPS); not earthed")
    v5 = d.net("+5V", domain="SELV", v=(0, 5.25), kind="power", i_max=1.6,
               notes="IRM-20-5 +Vo: coils, LEDs, Pi branch")
    v5pi = d.net("+5V_PI", domain="SELV", v=(0, 5.25), kind="power", i_max=1.0,
                 notes="after PTC F2 to Pi header pins 2/4 (back-feeds the Pi 5 V rail)")
    v33 = d.net("+3V3", domain="SELV", v=(0, 3.47), kind="power", i_max=0.01,
                notes="Pi 3.3 V from header pins 1/17; powers U1 only")
    coil_rtn = d.net("COIL_RTN", domain="SELV", v=(0, 6.1), kind="power", i_max=0.55,
                     notes="common low side of all coils via Q7; up to 5.25 + 0.86 V flyback when disarmed")
    hb = d.net("HB", domain="SELV", v=(0, 3.47), kind="signal", notes=f"heartbeat, Pi pin {PIN_HB} (BCM12)")
    ch_in = {k: d.net(f"CH{k}", domain="SELV", v=(0, 3.47), kind="signal",
                      notes=f"outlet {k} command, Pi pin {PI_PIN[k]} (BCM{PI_BCM[k]})") for k in CHANNELS}

    # -- barriers (DESIGN.md section 6) --------------------------------------------------------------
    sp = "TI SLUP419 (Mar 2024) Tables 3-5 and worked example (IEC 60664-1 F.1/F.2/F.4 subsets, IEC 62368-1 Table 10)"
    d.barrier("SELV", "LINE", grade="reinforced", v_work=V_MAINS_PK, creepage_mm=8.0, clearance_mm=8.0,
              standard="UL/IEC 62368-1 Tables 10 and 17; IEC 60664-1 Tables F.1, F.2, F.4", v_test_rms=3000,
              pollution_degree=2, material_group="IIIb", ovc="III", slot=False,
              source=f"{sp}. Required at 120 V OVC III: clearance 3.0 mm (reinforced = 4 kV, F.2), creepage 3.0 mm "
                     "(2 x F.4 125 V MG III); design 8.0/8.0 matches the relay's own 8/8 mm",
              notes="covers NEUTRAL and OUT1-6 (they float on LINE). Hi-pot 3.0 kVrms 60 s type, 1 s production")
    ul = "UL 1059 use group C, 51-150 V: 1/8 in air, 1/4 in surface [S, secondary table]"
    for k in CHANNELS:      # declared first: the narrower NEUTRAL/OUT rules below override overlaps
        d.barrier("LINE", f"OUT{k}", grade="functional", v_work=V_MAINS_PK, creepage_mm=2.5, clearance_mm=1.5,
                  standard="IPC-2221B Table 6-1 B2; IEC 60664-1 F.2 2.5 kV", pollution_degree=2, ovc="III",
                  source="IPC-2221B B2 151-170 V: 1.25 mm [S]; OVC III functional 1.5 mm; design 2.5/1.5 outside "
                         "the relay footprint",
                  notes=f"across K{k}'s open contact; inside the relay footprint the 5.0 mm pin pitch governs")
    d.barrier("LINE", "NEUTRAL", grade="functional", v_work=V_MAINS_PK, creepage_mm=6.4, clearance_mm=3.2,
              standard="UL 1059 / UL 508 practice", pollution_degree=2, ovc="III", source=ul,
              notes="opposite polarity; field-wiring terminals")
    for k in CHANNELS:
        d.barrier("NEUTRAL", f"OUT{k}", grade="functional", v_work=V_MAINS_PK, creepage_mm=6.4, clearance_mm=3.2,
                  standard="UL 1059 / UL 508 practice", pollution_degree=2, ovc="III", source=ul,
                  notes="switched line vs neutral, opposite polarity")
    for j in CHANNELS:
        for k in CHANNELS:
            if j < k:
                d.barrier(f"OUT{j}", f"OUT{k}", grade="functional", v_work=V_MAINS_PK, creepage_mm=6.4,
                          clearance_mm=3.2, standard="UL 1059 / UL 508 practice", pollution_degree=2, ovc="III",
                          source=ul, notes="one outlet on, the other off: 120 V between them")
    d.barrier("LINE", "PE", grade="basic", v_work=V_MAINS_PK, creepage_mm=6.4, clearance_mm=6.4,
              standard="IEC 62368-1 basic; UL field wiring to dead metal", pollution_degree=2, ovc="III",
              source="62368-1 basic: clearance 1.5 mm at 2.5 kV (SLUP419 Table 5), creepage 1.5 mm [I]; UL field "
                     "wiring to grounded dead metal 1/4 in [S]",
              notes="PE has no copper on the PCB: met by the LINE edge_clearance rule (board edges, mounting holes) "
                    "and by keeping EGC splices in the wire compartment")

    # -- block: mains input and supply ---------------------------------------------------------------
    mi = d.block("mains_in", title="Mains input J1, supply fuse F1 and IRM-20-5", domain="LINE",
                 description="J1 = branch L/N; F1 1 A T feeds PS1; PS1 makes the floating 5 V (Class II, LPS)")
    j1 = mi.add(P.TERM_IN, ref="J1")
    f1 = mi.add(P.FUSE_PSU, ref="F1", i_through=0.6)        # module full-load input current at 115 VAC (C-9)
    ps1 = mi.add(P.PSU, ref="PS1", p_diss=1.84)
    l_psu = mi.net("L_PSU", v=(-V_MAINS_PK, V_MAINS_PK), kind="mains", i_max=0.6,
                   notes="L after F1; equals L_IN, or is pulled toward N through PS1 when F1 is open")
    d.nets["L_IN"].connect(j1[1], f1[1])
    d.nets["N"].connect(j1[2], ps1["AC/N"])
    l_psu.connect(f1[2], ps1["AC/L"])

    # -- block: 5 V distribution (SELV) ----------------------------------------------------------------
    pw = d.block("power5", title="5 V rail: bulk caps, TVS, PWR LED, Pi branch PTC", domain="SELV",
                 description="+5V from PS1; F2 2 A PTC feeds the Pi; D15 clamps transients")
    c1 = pw.add(P.C_10U, ref="C1")
    c2 = pw.add(P.C_10U, ref="C2")
    c3 = pw.add(P.C_100N, ref="C3")
    d15 = pw.add(P.TVS_5V, ref="D15")
    d14 = pw.add(P.LED_GREEN, ref="D14", v_across=2.5, i_through=0.0023)   # forward only, (5.25-1.9)/1.5 k
    r20 = pw.add(P.R_1K5, ref="R20")
    f2 = pw.add(P.PTC_PI, ref="F2", i_through=1.0)                        # Pi branch allowance (C-2)
    tp1 = pw.add(P.TP, ref="TP1")
    tp2 = pw.add(P.TP, ref="TP2")
    led_pwr = pw.net("LED_PWR_A", v=(0, 5.25))
    gnd.connect(ps1["-Vo"], c1[2], c2[2], c3[2], d15["A"], d14["K"], tp2[1])
    v5.connect(ps1["+Vo"], c1[1], c2[1], c3[1], d15["K"], r20[1], f2[1], tp1[1])
    led_pwr.connect(r20[2], d14["A"])
    v5pi.connect(f2[2])

    # -- block: Pi Zero 2 W socket -------------------------------------------------------------------------
    pi = d.block("pi", title="Raspberry Pi Zero 2 W socket J5 (Pi component side up)", domain="SELV",
                 description="J5 back-feeds 5 V on pins 2/4; 3V3 from pins 1/17 powers U1; antenna zone keepout")
    j5 = pi.add(P.SOCKET_PI, ref="J5")
    c4 = pi.add(P.C_10U, ref="C4")
    c5 = pi.add(P.C_100N, ref="C5")
    tp6 = pi.add(P.TP, ref="TP6")
    v5pi.connect(*[j5[p] for p in PINS_5V], c4[1], c5[1])
    gnd.connect(*[j5[p] for p in PINS_GND], c4[2], c5[2])
    v33.connect(*[j5[p] for p in PINS_3V3], tp6[1])
    for k in CHANNELS:
        ch_in[k].connect(j5[PI_PIN[k]])
    hb.connect(j5[PIN_HB])
    used = set(PINS_5V) | set(PINS_3V3) | set(PINS_GND) | set(PI_PIN.values()) | {PIN_HB, PIN_ARM_FB}
    j5.nc_pins(*[str(p) for p in range(1, 41) if p not in used and p not in (27, 28)],
               reason="Pi GPIO not used by this board, left free (no pull, no load)")
    j5.nc_pins("27", "28", reason="ID_SD/ID_SC: leave unconnected when no HAT ID EEPROM is fitted (Zero 2 W "
                                  "schematic note)")

    # -- block: heartbeat watchdog -------------------------------------------------------------------------
    arm = d.block("arm", title="Heartbeat watchdog U1, arming switch Q7 and readback", domain="SELV",
                  description="Q7 closes the coil return only while HB has rising edges; OFF <= 0.1 s after they stop")
    u1 = arm.add(P.WATCHDOG, ref="U1", p_diss=0.001)
    r21 = arm.add(P.R_330K, ref="R21")
    c6 = arm.add(P.C_100N, ref="C6")
    c7 = arm.add(P.C_100N, ref="C7")
    r23 = arm.add(P.R_100K, ref="R23")
    q7 = arm.add(P.MOSFET, ref="Q7", p_diss=0.015)                  # 0.55^2 x 48 mOhm
    r22 = arm.add(P.R_100K, ref="R22")
    d13 = arm.add(P.LED_GREEN, ref="D13", v_across=2.5, i_through=0.0023)   # forward only; 2.3 mA when armed
    r19 = arm.add(P.R_1K5, ref="R19")
    r26 = arm.add(P.R_10K, ref="R26")
    r24 = arm.add(P.R_47K, ref="R24")
    r25 = arm.add(P.R_68K, ref="R25")
    d16 = arm.add(P.DIODE_CLAMP, ref="D16", i_through=0.001)         # clamp current <= 0.1 mA (C-5)
    tp3 = arm.add(P.TP, ref="TP3")
    tp4 = arm.add(P.TP, ref="TP4")
    tp5 = arm.add(P.TP, ref="TP5")
    arm_g = arm.net("ARM_G", v=(0, 3.47), notes="U1 Q -> Q7 gate")
    wd_rc = arm.net("WD_RC", v=(0, 3.47), notes="U1 Rext/Cext: R21 to +3V3, C6 positive side")
    wd_cx = arm.net("WD_CX", v=(0, 3.47), notes="U1 Cext: C6 other side only")
    arm_fb = arm.net("ARM_FB", v=(-0.3, 3.6), notes=f"readback to Pi pin {PIN_ARM_FB} (BCM16), clamped by D16")
    led_arm = arm.net("LED_ARM_A", v=(0, 5.25))
    v33.connect(u1["VCC"], u1["~{CLR}"], r21[1], c7[1], d16["K"])
    gnd.connect(u1["GND"], u1["~{A}"], c7[2], r23[2], q7["S"], r22[2], r25[2], d16["A"])
    hb.connect(u1["B"], r23[1], tp5[1])
    wd_rc.connect(u1["RCext"], r21[2], c6[1])
    wd_cx.connect(u1["Cext"], c6[2])
    arm_g.connect(u1["Q"], q7["G"], r22[1], tp3[1])
    coil_rtn.connect(q7["D"], d13["K"], r26[2], r24[1], tp4[1])
    v5.connect(r19[1], r26[1])
    led_arm.connect(r19[2], d13["A"])
    arm_fb.connect(r24[2], r25[1], d16["COM"], j5[PIN_ARM_FB])

    # -- blocks: six identical channels ---------------------------------------------------------------
    ch = {}
    for k in CHANNELS:
        jref, jpin = TERM[k]
        b = d.block(f"ch{k}", title=f"Outlet {k}: relay K{k}, driver Q{k}", domain="SELV",
                    description=f"CH{k} = Pi pin {PI_PIN[k]} (BCM{PI_BCM[k]}); K{k} switches L_IN to L_SW{k} "
                                f"-> {jref}.{jpin}")
        rk = b.add(P.R_100, ref=f"R{k}")
        rpd = b.add(P.R_4K7, ref=f"R{k + 6}")
        q = b.add(P.MOSFET, ref=f"Q{k}", p_diss=0.0005)
        dk = b.add(P.DIODE_FLYBACK, ref=f"D{k}", i_through=0.093)   # coil current at release only (5.25 V / 56.25)
        led = b.add(P.LED_GREEN, ref=f"D{k + 6}", v_across=2.5, i_through=0.0023)   # 2.3 mA; reverse <= 0.9 V
        rled = b.add(P.R_1K5, ref=f"R{k + 12}")
        rel = b.add(P.RELAY, ref=f"K{k}")
        g = b.net(f"CH{k}_G", v=(0, 3.47))
        coil = b.net(f"COIL{k}", v=(0, 6.1), kind="switching", i_max=0.093,
                     notes="coil low side; 5.25 V + 0.86 V flyback")
        la = b.net(f"LED{k}_A", v=(0, 5.25))
        ch_in[k].connect(rk[1])
        g.connect(rk[2], rpd[1], q["G"])
        gnd.connect(rpd[2])
        coil_rtn.connect(q["S"])
        coil.connect(q["D"], dk["A"], led["K"], rel["COIL_8"])
        v5.connect(dk["K"], rel["COIL_1"], rled[1])
        la.connect(rled[2], led["A"])
        d.nets["L_IN"].connect(rel["C_3_6"])
        ch[k] = dict(r=rk, rpd=rpd, q=q, d=dk, led=led, rled=rled, k=rel, block=b)

    # -- block: receptacle feed terminals --------------------------------------------------------------
    mo = d.block("outlets", title="Receptacle feeds J2-J4 (one 14/3 NM-B cable per duplex receptacle)",
                 domain="LINE", description="Jx.1 = top outlet (black), Jx.2 = N (white), Jx.3 = bottom outlet (red)")
    jout = {n: mo.add(P.TERM_OUT, ref=n) for n in ("J2", "J3", "J4")}
    for k in CHANNELS:
        jref, jpin = TERM[k]
        d.nets[f"L_SW{k}"].connect(ch[k]["k"]["C_4_5"], jout[jref][jpin])
    d.nets["N"].connect(*[jout[n][2] for n in jout])

    # -- block: mechanical ---------------------------------------------------------------------------------
    me = d.block("mech", title="Holes; partition; enclosures, receptacles, Pi and hardware (BOM only)",
                 description="H1-H6 board standoffs, H7-H10 Pi standoffs; MP1 partition; MP2-MP18 off-board items")
    holes = [me.add(P.HOLE_M3, ref=f"H{i}") for i in range(1, 7)]
    pi_holes = [me.add(P.HOLE_M25, ref=f"H{i}") for i in range(7, 11)]
    mp1 = me.add(P.PARTITION, ref="MP1")
    me.add(P.ENCLOSURE, ref="MP2")
    me.add(P.BACK_PANEL, ref="MP3")
    me.add(P.BOX_RECEPT, ref="MP4")
    for i in (5, 6, 7):
        me.add(P.RECEPTACLE, ref=f"MP{i}")
    me.add(P.WALLPLATE, ref="MP8")
    me.add(P.PI, ref="MP9")
    me.add(P.PI_HEADER, ref="MP10")
    me.add(P.HW_PI, ref="MP11")
    me.add(P.HW_BOARD, ref="MP12")
    me.add(P.FUSE_CLIPS, ref="MP13")
    me.add(P.SD_CARD, ref="MP14")
    me.add(P.HW_FIELD, ref="MP16")

    hazards(d)
    calcs(d)
    placement(d, j1, f1, ps1, jout, j5, u1, q7, r21, c6, c7, r22, r23, r24, r25, r26, d16, c1, c2, c3, d15, f2,
              c4, c5, ch, holes, pi_holes, mp1, pw, arm)
    board(d)
    waivers(d)
    return d


def placement(d, j1, f1, ps1, jout, j5, u1, q7, r21, c6, c7, r22, r23, r24, r25, r26, d16, c1, c2, c3, d15, f2,
              c4, c5, ch, holes, pi_holes, mp1, pw, arm):
    pl = d.place
    relays = [ch[k]["k"] for k in CHANNELS]
    terms = [j1] + list(jout.values())
    # floorplan, north to south: wire compartment | J1-J4 | MP1 partition | L/N buses, F1, relay contacts |
    # 8 mm barrier band | coil pins, drivers, U1/Q7 | Pi Zero 2 W (south-west, antenna on the south edge)
    for t in terms:
        pl.edge(t, "north", note="wire-entry face 1 mm inside the north edge; conductors enter from above")
        pl.pins_toward(t, ["1"], "north", note="odd-pole row (wire-entry face) toward the north edge")
    pl.array([jout["J2"], jout["J3"], jout["J4"]], "x", note="J2 over K1/K2, J3 over K3/K4, J4 over K5/K6")
    pl.region(j1, "corner-ne", note="J1 next to F1 and PS1 at the east end")
    pl.array(relays, "x", note="20 mm pitch, K1 west")
    for k in CHANNELS:
        c = ch[k]
        pl.pins_toward(c["k"], ["COIL_1", "COIL_8"], "south",
                       note="coil pins (y=0 in the footprint) toward the SELV band, contacts (y=+20/+25) north")
        pl.region([c["q"], c["d"], c["r"], c["rpd"], c["led"], c["rled"]], "south",
                  note=f"channel {k} SELV parts south of the barrier band, in K{k}'s column")
        pl.align([c["k"], c["q"], c["led"]], "y", note=f"channel {k} column")
        pl.near(c["d"], c["k"]["COIL_1"], "tight")
        pl.near(c["d"], c["k"]["COIL_8"], "tight")
        pl.near(c["q"], c["k"]["COIL_8"], "close")
        pl.near(c["rpd"], c["q"]["G"], "tight")
        pl.near(c["r"], c["rpd"], "tight")
        pl.near(c["rled"], c["led"], "tight")
        pl.hot_loop([c["d"]["K"], c["k"]["COIL_1"], c["k"]["COIL_8"], c["d"]["A"]],
                    note="coil flyback loop; keep spikes off SELV wiring")
        pl.thermal(c["k"], 1.5, "copper", note="coil 0.47 W + contact up to 2.25 W at 15 A; L/L_SW pours both layers")
        pl.near(q7, c["q"], "close", note="short COIL_RTN")
        jref, _ = TERM[k]
        pl.near(c["k"]["C_4_5"], jout[jref], "close", note=f"L_SW{k} short and straight north to {jref}")
    # supply: AC end north (mains), DC end south (SELV); the barrier band runs under the potted body
    pl.region(ps1, "east", note="east end, away from the Pi antenna and its relays")
    pl.pins_toward(ps1, ["AC/L", "AC/N"], "north", note="AC pins north of the barrier band, +Vo/-Vo south")
    pl.near(f1, j1, "close", note="F1 between J1.1 and PS1 AC/L, both clips in the mains region")
    pl.near(f1, ps1["AC/L"], "close")
    pl.thermal(ps1, 1.84, "air", note="potted module; 10 mm to other parts where possible (Mean Well manual)")
    pl.near(c1, ps1["+Vo"], "tight")
    pl.near(c2, c1, "tight")
    pl.near(c3, ps1["+Vo"], "tight")
    pl.near(d15, ps1["+Vo"], "close")
    pl.group(pw, "close")
    pl.near(f2, j5[2], "loose", note="Pi branch PTC between the rail and J5")
    # Pi socket: position fixed by the board holes H7-H10 (Zero 2 W drawing)
    pl.region(j5, "corner-sw", note="Pi over the south-west corner, connector/antenna edge on the south edge")
    pl.edge(j5, "south", note="Pi connector edge 1 mm inside the south edge: antenna faces free space")
    pl.custom("datum", obj=j5, holes="H7 H8 H9 H10",
              at=f"J5 pin 1 at ({pi_xy(8.37, 4.77)[0]:.2f}, {pi_xy(8.37, 4.77)[1]:.2f}) mm, 0 deg (pin 2 north)",
              note="from the Zero 2 W drawing: header centred 32.5 mm from the SD-card end, rows 3.5 -/+ 1.27 mm "
                   "from the header edge; holes 3.5 mm from each edge")
    pl.keepout(j5, what="Wi-Fi antenna zone (rule area in the J5 footprint): no copper, vias, pours or parts",
               layers="all", note="board x 24-57 mm, y 0-13 mm, plus 10 mm beyond the south edge")
    for r in relays:
        pl.far(j5, r, "loose", note=">= 30 mm from the antenna zone (lambda/4 at 2.4 GHz)")
    pl.far(j5, ps1, "loose", note="supply switching at 65 kHz and its magnetics away from the antenna")
    pl.far(j5, f1, "loose")
    pl.keepout(j5, what="parts under the Pi (courtyard = Pi outline)", layers="top")
    pl.near(c4, j5[2], "close")
    pl.near(c5, j5[4], "tight")
    # watchdog cluster between the Pi header and the driver row
    pl.group(arm, "close")
    pl.region(arm, "south")
    pl.near(u1, j5[PIN_HB], "close")
    pl.near(c7, u1["VCC"], "tight")
    pl.near(r21, u1["RCext"], "tight")
    pl.near(c6, u1["Cext"], "tight")
    pl.near(r23, u1["B"], "tight")
    pl.near(r22, q7["G"], "tight")
    pl.near(q7, u1["Q"], "close")
    pl.near(d16, j5[PIN_ARM_FB], "close")
    pl.near(r25, d16, "tight")
    pl.near(r24, q7["D"], "close")
    pl.near(r26, q7["D"], "close")
    pl.side("all", "top", note="all parts on the top side")
    # isolation: every barrier becomes a separate() relation and a .kicad_dru rule
    for bar in d.barriers:
        pl.separate(d.domains[bar.a], d.domains[bar.b], slot=bar.slot)
    pl.custom("barrier_part", part=mp1, line="south faces of J1-J4 (y ~ 122 mm), full enclosure width",
              height_mm="PCB to lid (~130)", fixing="10 mm folded foot on the PCB; nylon screws to the back panel "
                                                     "beyond both board ends (no board holes)",
              covers="field-wiring compartment north of it; PCB, relays, PS1 and the Pi south of it",
              note="supplementary insulation between field conductors (basic) and SELV/Pi (review M3, REQ-31)")
    pl.custom("volume_keepout", region="north of MP1, above J1-J4 up to the lid",
              what="no parts; only terminal bodies, field conductors, EGC splice",
              note="wire-bending space for 14-12 AWG solid conductors entering the terminals from above")
    for net in ["L_IN", "N"] + [f"L_SW{k}" for k in CHANNELS]:
        pl.custom("current_path", net=f"net:{net}", amps=15, layers="F.Cu,B.Cu", copper_oz=2,
                  stitching="4 x 0.6 mm vias every 10 mm",
                  note="width from Net(width_mm=7.5). L runs from J1.1 west under the relay bodies into pads 13; "
                       "L_SWk goes north from pads 14 to its terminal; N runs along the J1-J4 even-pole row, "
                       ">= 6.4 mm from every L/L_SW pad, under or south of the terminal bodies")
    pl.custom("enclosure_layout", walls="NS1086 inside ~251 x 200 x 152 mm; board 200 x 150 on JP108P",
              arrangement="board north edge toward the top wall; wire compartment = top ~60 mm; branch cable in "
                          "through the top wall (west); 3 x 14/3 NM-B out through the east wall above MP1 to E2",
              note="E2 (3-gang PVC box, receptacles) mounted east of E1 on the same backboard")
    pl.custom("ground_splice", where="wire compartment, west end, >= 25 mm from J1",
              note="branch EGC + 3 outgoing EGCs in one listed lever connector; tied to the back panel")
    pl.custom("label", obj=j1, text="LINE IN: L (black) / N (white) - 120 VAC 15 A")
    for n, (a, b) in zip(("J2", "J3", "J4"), ((1, 2), (3, 4), (5, 6))):
        pl.custom("label", obj=jout[n], text=f"RECEPTACLE {'ABC'[(a - 1) // 2]}: TOP OUT{a} (black) / N (white) / "
                                             f"BOTTOM OUT{b} (red)")
    pl.custom("label", obj="board", text="120 VAC 60 Hz, 15 A max branch; Cu 14-12 AWG, strip 11-13 mm; DANGER "
                                         "disconnect before opening; outlets are not a disconnecting means")


def board(d):
    pi = [pi_xy(3.5, 3.5), pi_xy(61.5, 3.5), pi_xy(3.5, 26.5), pi_xy(61.5, 26.5)]
    holes = [Hole(4, 4, 3.2, note="H1, M3 nylon standoff"), Hole(196, 4, 3.2, note="H2"),
             Hole(4, 75, 3.2, note="H3"), Hole(196, 75, 3.2, note="H4"),
             Hole(4, 146, 3.2, note="H5"), Hole(196, 146, 3.2, note="H6")]
    holes += [Hole(x, y, 2.7, note=f"H{7 + i}, Pi Zero 2 W standoff M2.5 x 11 mm nylon") for i, (x, y) in enumerate(pi)]
    d.board(width_mm=BOARD_W, height_mm=BOARD_H, layers=2, thickness_mm=1.6, copper_oz=2, holes=holes,
            max_component_height_mm=31, max_bottom_height_mm=2.4,
            enclosure="ABB/Carlon NS1086 polycarbonate 10 x 8 x 6 in (UL 50 Type 4X/12), JP108P PVC back panel; "
                      "board on 6 x M3 x 12 mm nylon standoffs; partition MP1 across the board at the south faces "
                      "of J1-J4; Pi Zero 2 W on J5 at 11 mm (socket 8.51 + header 2.54) on 4 x M2.5 x 11 mm nylon "
                      "standoffs; receptacles in a separate Carlon BH353A 3-gang box (E2)",
            coating="",
            keepouts=[
                {"rect": [PI_X0 + 12, 0, PI_X0 + 45, PI_Y0 + 12], "what": "copper, vias, pours, parts",
                 "layers": "all", "note": "Pi Zero 2 W antenna zone (also a rule area in the J5 footprint)"},
                {"rect": [PI_X0, PI_Y0, PI_X0 + 65, PI_Y0 + 30], "what": "parts other than J5", "layers": "top",
                 "note": "under the Pi"},
                {"relative": "north edge to the south faces of J1-J4 (~28 mm), outside the terminal bodies",
                 "what": "all copper", "layers": "all", "note": "wire compartment: no exposed copper (REQ-31)"},
                {"relative": "K1-K6 coil-pad north edge +1 mm to +9 mm, full width (also under PS1)",
                 "what": "copper and vias", "layers": "all", "note": "SELV/mains 8 mm barrier band"},
                {"relative": "3 mm either side of the MP1 line (south faces of J1-J4)",
                 "what": "parts taller than 1 mm", "layers": "top", "note": "partition foot"},
            ],
            notes="FR-4 UL 94 V-0, UL ZPMV2 laminate, CTI >= 175 V preferred (IIIb assumed). All parts top side. "
                  "Solder tails <= 2.4 mm below the board. Mains copper >= 6.4 mm from edges and holes (DRU "
                  "edge_clearance). Pi standoff holes H7-H10 fix J5's position (see placement datum).")


def waivers(d):
    W = d.waive
    W("rating.current", r"^K[1-6] \(G5RL",
      "Relay contacts at 15 A vs 16 A (94 %): UL E41643 lists 16 A general use at 40 C (50k ops) and VDE lists "
      "16 A at 85 C (15k ops). 15 A is the branch-breaker ceiling, not a continuous load; continuous loads are limited "
      "to 12 A = 75 % (REQ-5, calc relay_contact_continuous_ratio). Verified by T-OL and T-HEAT.")
    W("protect.threat", r"threat 'surge'",
      "No MOV/TVS on mains by design (DESIGN.md C-11): insulation is coordinated for OVC III (2.5 kV transient; "
      "relay 10 kV impulse coil-contact, PCB 8 mm reinforced, 6.4 mm functional); PS1 is tested to EN 61000-4-5 "
      "level 4 (2 kV L-N) without external parts. An MOV ages and is a fire source in a closed box; a listed Type 2 "
      "SPD at the panel is recommended (Q-12). Verified by T-SURGE.")
    W("protect.threat", r"net (L_IN|L_SW[1-6]) declares threat 'overcurrent'",
      "The upstream 15 A branch breaker (REQ-2) is the single overcurrent device for the outlet paths; every element "
      "on these nets is rated >= 15 A at temperature (terminals 31 A, relays 16 A, copper 7.5 mm x 2 layers x 2 oz "
      "with 1.4x I2t margin at 2 kA; calcs mains_*). F1 protects only the PS1 branch.")
    W("protect.entry_fuse", r"net (L_IN|N|L_SW[1-6]) reaches",
      "Same as the overcurrent waiver: the 15 A branch breaker protects every outlet element downstream (C-9).")
    W("conn.empty_net", r"net PE",
      "PE exists only off-board (EGC splice in E1, receptacle yokes in E2); no PCB copper by design (REQ-4, NEC "
      "250.148(B)). The net is declared so the LINE-PE barrier reaches intent.yaml and the DRU.")
    W("hazard.procedural", r"^H10:",
      "Outlets are not a disconnecting means; unplugging the load or locking out the breaker is the only correct "
      "mitigation.")
    W("hazard.procedural", r"^H15:",
      "Motor overload protection belongs to the load (NEC 430), outside this board; REQ-5 limits motors to 1/2 hp.")
