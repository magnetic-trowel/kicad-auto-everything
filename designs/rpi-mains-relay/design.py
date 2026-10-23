# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""rpi-mains-relay: 4-channel 120 VAC relay board for a Raspberry Pi, in a 4-11/16 in box.

Encodes designs/rpi-mains-relay/DESIGN.md (engineering rationale, evidence tags, sources) and
CONNECTIONS.md (pin rationale). Build: `kaesynth build designs/rpi-mains-relay/design.py -v`.

Domain model:
  LINE   root, ref L_IN. The line conductor is the 0 V of the mains side, so the voltage across
         an open relay contact (L_IN to L_SWk) is exact (+/-187 V peak) instead of an envelope sum.
  NEUTRAL floats on L_IN (N is +/-187 V peak from L).
  OUT1..OUT4 float on L_IN: a switched output is L when its relay is closed and is pulled to N
         by the load when open, so +/-187 V peak from L.
  SELV   root, ref GND: the Raspberry Pi side (Class 2 / ES1), coil drive and watchdog.
  PE     root, ref PE: box, ring, cover and EGCs. No copper on the PCB; kept so the mains-to-PE
         spacing reaches intent.yaml.
"""
import importlib.util
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
CHANNELS = (1, 2, 3, 4)
PI_PIN = {1: "11 (BCM17)", 2: "13 (BCM27)", 3: "15 (BCM22)", 4: "16 (BCM23)"}
ESD_PIN = {1: "D1+", 2: "D1-", 3: "D2+", 4: "D2-"}     # U1 channel per CH (SLVSBO7O Table 4-3)


def intent(d):
    # -- requirements (DESIGN.md section 2) --------------------------------------------------------
    R = d.require
    R("REQ-1", "Supply: 120 VAC nominal, 60 Hz, 1-phase, L + N + EGC; single 2-wire branch, not a MWBC",
      value="108-132 V, 60 Hz", source="brief; ASM-1", verify="inspection, T-FUNC")
    R("REQ-2", "Branch overcurrent device (OCPD) <= 15 A; Cu conductors 14 AWG min, 12 AWG allowed",
      value="<= 15 A", source="derived; NEC 240.4(D) [I]", verify="label, install check")
    R("REQ-3", "Four independently controlled outputs", value="4", source="brief ('4 or 6'); box size (C-1)",
      verify="T-FUNC")
    R("REQ-4", "Switch line only; neutral not switched; EGC never through the PCB", value="-",
      source="NEC 404.2(B) [I], 250.148(B) [S]", verify="netlist review")
    R("REQ-5", "Per-output rating", value="<= 15 A general use, <= 12 A continuous; <= 1/2 hp at 120 V (9.8 A FLA); "
      "tungsten <= TV-8; capacitive inrush <= 100 A peak", source="relay UL/VDE ratings [P]", verify="T-LOAD, T-OL")
    R("REQ-6", "Total current (sum of outputs)", value="<= 15 A", source="branch OCPD", verify="T-HEAT")
    R("REQ-7", "Enclosure: listed steel 4-11/16 in box 2-1/8 in deep + 1-1/2 in ring + flat blank cover, "
      "surface-mounted indoors", value="RACO 257 + 250 + 832", source="brief ('outlet type box'); C-1, C-6",
      verify="inspection")
    R("REQ-8", "Box fill: displaced volume + NEC allowances <= box volume", value="<= 71.5 in3",
      source="NEC 314.16 [S/I]", verify="calc box_fill_*")
    R("REQ-9", "Field terminals: lever push-in, UL 1059 >= 300 V / >= 20 A, 14-12 AWG Cu; one (L, N) input, "
      "four (L_SW, N) outputs, labelled", value="WAGO 2606, 600 V 31 A",
      source="brief ('really easy to access', 'shared inputs ... outputs')", verify="inspection")
    R("REQ-10", "Mains <-> SELV: reinforced; PCB creepage and clearance; relay coil-contact reinforced",
      value=">= 8.0 mm / >= 8.0 mm; 3 kVrms 60 s", source="UL/IEC 62368-1, IEC 60664-1 (C-8)",
      verify="T-CREEP, T-HIPOT")
    R("REQ-11", "Opposite-polarity mains spacing (L or L_SWk to N; L_SWj to L_SWk)",
      value="creepage >= 6.4 mm, clearance >= 3.2 mm", source="UL 1059 use group C [S]", verify="T-CREEP")
    R("REQ-12", "Mains <-> PE: copper to box metal; copper to any board edge",
      value=">= 6.4 mm to box metal; >= 2.0 mm to a board edge", source="UL field wiring [S]; 62368-1 basic [P/I]",
      verify="T-CREEP, T-HIPOT")
    R("REQ-13", "Fail-safe OFF: all outputs OFF when the Pi is unplugged, unpowered, booting, rebooting or "
      "halted, when any CH line floats, and after the heartbeat stops", value="<= 0.5 s after heartbeat stops",
      source="brief ('reliable'); task", verify="T-BOOT, T-FLOAT, T-HB")
    R("REQ-14", "Two-fault rule: no single stuck GPIO or single shorted driver energizes an output while the "
      "heartbeat is absent", value="-", source="derived", verify="FMEA (hazards), T-HB")
    R("REQ-15", "Load on the Pi", value="GPIO <= 0.6 mA DC per CH pin, <= 3.3 mA peak on HB; 5 V <= 0.40 A; "
      "only default-pull-down GPIOs", source="Raspberry Pi docs [P]", verify="T-PWR")
    R("REQ-16", "Heartbeat arms the outputs; DC or no signal disarms them",
      value="3.3 V square wave 100 Hz-2 kHz, 40-60 % duty", source="derived (C-4)", verify="T-HB")
    R("REQ-17", "Coil voltage at the relay pins, worst case", value=">= 4.5 V", source="must-operate [P]; C-3",
      verify="T-COIL")
    R("REQ-18", "Leakage at an OFF output (no snubber or MOV across the contacts)", value="<= 0.1 mA",
      source="derived (C-12)", verify="T-LEAK")
    R("REQ-19", "Thermal: every part within its derated limit at 40 C room, surface-mounted box, 12 A "
      "continuous plus all coils on", value="internal air <= 70 C", source="derived (C-6)", verify="T-HEAT")
    R("REQ-20", "Fault withstand: mains copper survives a 15 A breaker's let-through", value="<= 2 kA prospective",
      source="derived (C-7)", verify="T-SC")
    R("REQ-21", "Indicators on the SELV side: LED per channel (coil energized), ARM LED, 5 V LED", value="6 LEDs",
      source="task", verify="T-FUNC")
    R("REQ-22", "Environment", value="indoor dry, PD2, OVC II, <= 2000 m, room 0-40 C", source="ASM-2", verify="-")
    R("REQ-23", "Parts active and orderable; UL-recognized relays, terminals, PTC, PCB laminate", value="-",
      source="brief ('reliable')", verify="BOM review")
    R("REQ-24", "Installation by a licensed electrician; approval by the authority having jurisdiction (AHJ)",
      value="-", source="NEC 110.2/110.3 [I]", verify="Q-1")
    R("REQ-25", "Markings: ratings, conductor size and strip length, warnings, 'Class 2 only' at J6", value="-",
      source="UL practice [I]", verify="inspection")
    R("REQ-26", "SELV link: 8-conductor Class 2 cable on its own knockout, separated from mains by a barrier",
      value="22 AWG <= 3 m (24 AWG <= 2 m)", source="NEC 725.136(B)/(D) [S]; C-3", verify="inspection")

    # -- assumptions and questions (DESIGN.md section 3) -------------------------------------------
    A = d.assume
    A("ASM-1", "North-American dwelling or light commercial; one 120 V branch from a <= 15 A breaker; "
      "prospective fault current at the box <= 2 kA (>= 10 m of 14 AWG limits it to < 1 kA)")
    A("ASM-2", "Indoor dry location, PD2, OVC II, altitude <= 2000 m, room 0-40 C; box surface-mounted")
    A("ASM-3", "Loads are plug-in appliances, LED or tungsten lighting, small motors; none hazardous if left "
      "on (a welded contact is a credible failure)")
    A("ASM-4", "Raspberry Pi 4 or 5 on its official 5.1 V supply, in its own case outside the box, <= 3 m away")
    A("ASM-5", "PCB laminate taken as material group IIIb (CTI >= 100 V) so the tables apply at their most "
      "conservative; FR-4 is usually IIIa")
    A("ASM-6", "Control software toggles HB at >= 100 Hz from its main loop while any output should be on")
    A("ASM-7", "Outputs drop to OFF on every Pi reboot; no state is retained")
    Q = d.question
    Q("Q-1", "Certification path: who evaluates (AHJ field evaluation) and who installs (licensed electrician) "
      "this unlisted assembly? If neither is acceptable, buy listed products (alternative A5).", blocking=True,
      default="designed to UL/IEC 62368-1 spacings with UL-recognized parts; installation by a licensed "
              "electrician assumed; not certified")
    Q("Q-2", "Confirm 4 channels (6 do not fit a 4-11/16 in box; they need a 6 x 6 x 4 in enclosure).",
      blocking=True, default="4 channels")
    Q("Q-3", "Confirm the branch circuit is <= 15 A (20 A needs per-channel fuses or 20 A relays).",
      blocking=True, default="15 A branch")
    Q("Q-4", "Load list: any heaters, pumps, compressors or life-safety loads that are unsafe if a contact "
      "welds? Motors cycled more than about 5 times a day should drive a contactor.", blocking=True,
      default="general plug loads, no hazard-if-on loads")
    Q("Q-5", "Confirm surface mounting (flush mounting in an insulated wall overheats the box).", blocking=True,
      default="surface-mounted box")
    Q("Q-6", "Insulating SELV cover MP1: confirm material and fixing, and AHJ acceptance as the NEC 725.136(B) "
      "barrier.", blocking=True, default="0.43 mm PP UL 94 V-0 cover, 2 snap holes")
    Q("Q-7", "Watchdog semantics: OFF when the control app hangs (software heartbeat) or keep ON through app "
      "hangs (hardware-PWM heartbeat)?", default="software heartbeat, outputs OFF on hang")
    Q("Q-8", "Pi-side termination of the cable: GPIO screw-terminal HAT or crimped 2.54 mm housings.",
      default="user's choice; pin map in CONNECTIONS.md")
    Q("Q-9", "Surge protection: Type 2 SPD at the panel instead of an MOV in the box?", default="no MOV in box")
    Q("Q-10", "Do the outputs feed downstream receptacle boxes ('like outlets') or loads wired directly?",
      default="either; outputs are terminals")
    Q("Q-11", "Relay supply (Omron -> Aratas, 26-week lead time): qualify the second source.",
      default="G5RL-1A-E-HR DC5 as drop-in")


def hazards(d):
    H = d.hazard
    relays = ["K1", "K2", "K3", "K4"]
    terms = ["J1", "J2", "J3", "J4", "J5"]
    H("H1", "Shock from live parts with the cover off",
      "listed steel box, ring and screw cover (tool needed); 'disconnect before opening' label; electrician "
      "installs", parts=["MP2", "MP3", "MP4"], single_fault_safe=False,
      notes="service condition: de-energize at the breaker")
    H("H2", "Mains reaches SELV and the Pi",
      "reinforced insulation: relay 8/8 mm, 6 kVAC, 10 kV impulse; PCB 8/8 mm barrier band; SELV cover MP1 keeps "
      "field conductors off SELV parts; Class 2 cable on its own knockout", parts=relays + ["MP1"],
      single_fault_safe=True)
    H("H3", "Metal box becomes live",
      "all EGCs spliced with a listed connector, pigtail to the box ground screw; ring and cover bonded by "
      "their screws", parts=["MP2", "MP3", "MP4"], single_fault_safe=True,
      notes="needs insulation failure plus loss of EGC; splice is installer work")
    H("H4", "Overload heats conductors, PCB, terminals or relays",
      "single protective device = branch OCPD <= 15 A; every downstream element rated >= 15 A at temperature "
      "(calcs mains_copper_*, relay_contact_*)", parts=terms + relays, single_fault_safe=True,
      notes="15-20 A overloads before the breaker trips are covered by T-OL")
    H("H5", "Short circuit on an output",
      "breaker clears; copper I2t margin 1.4x at 2 kA; steel box contains any arc", parts=terms + ["MP2"],
      single_fault_safe=True)
    H("H6", "Loose or partially inserted conductor heats up",
      "spring clamps (no torque relaxation); strip length on silkscreen; pull test at commissioning",
      parts=terms, single_fault_safe=False, notes="inspection is the barrier")
    H("H7", "Fail-ON: welded relay contact",
      "inrush-rated relay (TV-8, 100 A peak); load limits REQ-5; no snubber; documented that outputs are not "
      "for loads hazardous if left on", parts=relays, single_fault_safe=False,
      notes="residual risk, disclosed (Q-4)")
    H("H8", "Fail-ON from control: software bug, hung Pi, stuck GPIO, shorted MOSFET",
      "coil current needs both Qk (GPIO) and Q5 (heartbeat pump); 4.7 k pull-downs; coils powered from the Pi",
      parts=["Q1", "Q2", "Q3", "Q4", "Q5", "D12", "C3", "C4", "R5", "R6", "R7", "R8"], single_fault_safe=False,
      notes="hung software / stuck GPIO / shorted Q5: safe (the other path still blocks). Shorted Qk while the "
            "heartbeat runs: channel k follows ARM (LED shows it); stopping the heartbeat turns it OFF")
    H("H9", "Glitch to ON at boot or reset",
      "default-pull-down GPIOs plus 4.7 k pull-downs; arming needs >= 100 Hz toggling",
      parts=["R5", "R6", "R7", "R8", "Q5", "D12"], single_fault_safe=True)
    H("H10", "Remote energization while a load is being serviced",
      "label: relays are not a disconnecting means; lock out at the breaker", parts=[], single_fault_safe=False,
      notes="procedural by nature")
    H("H11", "Shock from an 'OFF' output",
      "no snubber or MOV across contacts; line-only switching; polarity check at commissioning", parts=relays,
      single_fault_safe=False, notes="leakage: single-fault safe; L/N miswire: procedural (T-MISWIRE)")
    H("H12", "Overtemperature in the closed box",
      "4 W budget; surface mounting required; 12 A continuous limit", parts=["MP2", "MP3"],
      single_fault_safe=True)
    H("H13", "Surge flashover or arc tracking",
      "OVC II coordinated spacing; relay 10 kV impulse; no unprotected MOV in the box; panel SPD recommended",
      parts=relays, single_fault_safe=True)
    H("H14", "Pi damaged by wiring errors at J6 or a cable fault",
      "PTC F1, TVS D11, ESD array U1, two GND conductors, no back-power path from the GPIOs (U1 has no supply "
      "pin)", parts=["F1", "D11", "U1"], single_fault_safe=True)
    H("H15", "Motor stall on an output",
      "the motor's own overload protection (NEC 430); 1/2 hp relay rating; contactor for larger motors",
      parts=[], single_fault_safe=False, notes="load-side protection, outside this board")


def calcs(d):
    c = d.calc
    # C-1 box fill (12 AWG worst case)
    c("box_volume_in3", 42.0 + 29.5, "in3", expr="RACO 257 42.0 + RACO 250 ring 29.5")
    allow = 10 * 2.25 + 1.25 * 2.25 + 2.0 + 2.25
    displaced = 259.0 / 16.387
    c("box_fill_allowances_in3", round(allow, 1), "in3",
      expr="10 cond x 2.25 + EGC 1.25 x 2.25 + Class 2 cable 2.0 + clamps 2.25",
      limit=round(71.5 - displaced, 1), note="allowances <= box + ring - displaced board volume (15.8 in3)")
    c("box_fill_available_without_ring_in3", round(42.0 - displaced, 1), "in3",
      expr="42.0 - 15.8", note="< 29.6 in3 needed: the extension ring is required")
    # C-2 5 V budget
    i5 = 4 * 5.25 / 56.25 + 6 * (5.25 - 1.9) / 1485 + 0.001
    c("i_5v_max_A", round(i5, 3), "A", expr="4 x 5.25 V / 56.25 ohm + 6 LEDs x 2.25 mA + 1 mA",
      limit=0.55, note="Pi 4 headroom: 3.0 A PSU - 1.2 A USB - 1.25 A stress")
    c("gpio_ch_current_mA", round(3.3 / 5.7, 3), "mA", expr="3.3 V / (1 k + 4.7 k)", limit=0.6,
      note="REQ-15; Pi limit 16 mA per pin, 50 mA total")
    # C-3 coil voltage
    drop = 0.388 * (0.238 + 0.20 + 0.048) + 0.093 * 0.048
    c("coil_supply_drop_V", round(drop, 3), "V", expr="0.388 A x (cable 0.238 + PTC 0.20 + Q5 0.048) + 0.093 x 0.048")
    c("coil_voltage_worst_V", round(4.75 - drop, 2), "V", expr="V_hdr 4.75 V - drop", limit=4.5, op=">=",
      note="REQ-17")
    must_hot = 70 * (234.5 + 90) / 257.5
    c("must_operate_hot_restart_pct", round(must_hot, 1), "%", expr="70 % x (234.5 + 90 C) / 257.5",
      limit=round(100 * (4.75 - drop) / 5.0, 1), note="coil at 90 C (55 C box + 35 K rise [I]); verify T-COIL")
    c("coil_voltage_max_pct", 105.0, "%", expr="5.25 V / 5.0 V", limit=130, note="G5RL max coil voltage")
    # C-4 heartbeat pump (R13 1 k, C3 1 uF, D12 BAT54S, C4 100 nF, R14 1 M)
    v_pk = 3.2 - 2 * 0.24
    i_bleed = v_pk / 1e6
    v_arm_min = v_pk - i_bleed / (100 * 1e-6) - i_bleed * 5e-3 / 100e-9
    c("arm_gate_min_100Hz_V", round(v_arm_min, 2), "V",
      expr="(3.2 - 2 x 0.24) - I/(f C3) - I x 5 ms / C4, I = V/1 Mohm", limit=2.5, op=">=",
      note="AO3400A Rds(on) is specified at Vgs 2.5 V")
    t_off = 1e6 * 100e-9 * __import__("math").log(v_pk / 0.65) + 0.005
    c("disarm_time_s", round(t_off, 3), "s", expr="R14 C4 ln(2.72 / 0.65) + 5 ms release", limit=0.5,
      note="REQ-13")
    # C-5 gate drive
    c("gate_on_V", round(3.3 * 4.7 / 5.7, 2), "V", expr="3.3 x 4.7 / 5.7", limit=2.5, op=">=")
    c("gate_miswire_pullup_V", round(3.3 * 4.7 / (4.7 + 1 + 33), 2), "V",
      expr="GPIO with 33 k internal pull-up: 3.3 x 4.7 / 38.7", limit=0.65, note="< AO3400A Vgs(th) min")
    # C-6 thermal
    c("box_dissipation_W", 4.0, "W", expr="coils 1.6 + contacts 1.13 + copper 0.79 + terminals 0.45 + LEDs 0.06")
    c("box_internal_air_C", 40 + 3.2 / (6.5 * 0.0589) + 5, "C",
      expr="40 C room + 3.2 W / (6.5 W/m2K x 0.0589 m2) + 5 K internal", limit=70,
      note="surface-mounted; flush in an insulated wall gives ~80 C and is excluded (Q-5)")
    # C-7 mains copper
    c("mains_copper_width_per_layer_mm", 7.5, "mm", limit=6.3, op=">=",
      note="IPC-2221 single-layer width for 15 A, 10 K, 2 oz = 6.3 mm; we use 7.5 mm on both layers")
    c("mains_copper_dT_K", 1.6, "K", expr="IPC-2221 external, 7.5 A per layer in 813 mil2", limit=10)
    c("mains_fault_i2t_margin", round(92 / 67, 2), "x",
      expr="Onderdonk melt 92 kA2s / breaker let-through 67 kA2s at 2 kA in 1 cycle", limit=1.0, op=">=")
    # C-8 creepage and clearance
    c("barrier_creepage_margin_120V", round(8.0 / 3.0, 2), "x", expr="8.0 / (2 x 1.5 mm, F.4 125 V MG III)",
      limit=1.0, op=">=")
    c("barrier_creepage_margin_240V", 8.0 / 5.0, "x", expr="8.0 / 5.0 mm", limit=1.0, op=">=")
    c("barrier_clearance_margin_240V", round(8.0 / 3.6, 2), "x", expr="8.0 / 3.6 mm (62368-1 T10 2.5 kV reinforced)",
      limit=1.0, op=">=")
    # C-9 protection coordination
    c("relay_contact_current_ratio", round(15 / 16, 3), "", expr="15 A breaker ceiling / 16 A UL general use",
      limit=1.0)
    c("relay_contact_continuous_ratio", 12 / 16, "", expr="12 A continuous / 16 A", limit=0.8)
    c("ptc_hold_at_55C_A", 0.85, "A", expr="1.1 A x ~0.77 [I]", limit=0.39, op=">=")
    c("tvs_standoff_ratio", round(5.25 / 7.0, 2), "", expr="5.25 V / VWM 7.0 V", limit=0.8)
    # C-10..C-12
    c("relay_life_motor_days", 6000 / 20, "days", expr="1/2 hp UL rating 6000 ops / 20 ops a day",
      note="frequently cycled motors should drive a contactor (A300 pilot duty)")
    c("mov_energy_catB_J", 30, "J", expr="450 V x 3 kA x 22 us", note="~55 % of a 14 mm MOV rating; no MOV in box")
    c("snubber_leakage_if_fitted_mA", round(2 * 3.1416 * 60 * 0.1e-6 * 120 * 1000, 2), "mA",
      expr="2 pi 60 Hz x 0.1 uF x 120 V", note="why there is no snubber across the contacts")
    c("off_state_leakage_mA", 0.0002, "mA", expr="187 V / 1000 Mohm open-contact insulation", limit=0.1)


def build():
    d = Design("rpi-mains-relay", title="RPi 4-channel 120 VAC relay board (4-11/16 in box)",
               description="4 x 16 A relays switch line; Pi drives them over a Class 2 cable via a heartbeat watchdog",
               brief=BRIEF, ambient_c=(0, 55))
    intent(d)

    # -- domains and global nets -------------------------------------------------------------------
    d.net("L_IN", domain="LINE", v=0, kind="mains", i_max=I_BRANCH, external=True, threats=("surge", "overcurrent"),
          notes="line from the branch circuit; reference of the mains side")
    d.domain("LINE", ref="L_IN", kind="mains", description="mains line conductor (root; 120 VAC 60 Hz, OVC II)")
    d.net("N", domain="NEUTRAL", v=(-V_MAINS_PK, V_MAINS_PK), kind="mains", i_max=I_BRANCH, external=True,
          threats=("surge",), notes="neutral; not switched")
    d.domain("NEUTRAL", ref="L_IN", kind="mains", description="neutral, +/-187 V peak from line")
    for k in CHANNELS:
        d.net(f"L_SW{k}", domain=f"OUT{k}", v=(-V_MAINS_PK, V_MAINS_PK), kind="mains", i_max=I_BRANCH,
              external=True, threats=("overcurrent",),
              notes=f"switched line, output {k}: equals L_IN when K{k} is closed, pulled to N by the load when open")
        d.domain(f"OUT{k}", ref="L_IN", kind="mains", description=f"switched output {k}, floats on line")
    d.net("PE", domain="PE", v=0, kind="pe", external=True,
          notes="protective earth: box, ring, cover, EGCs; no copper on this PCB")
    d.domain("PE", ref="PE", kind="other", earthed=True, description="protective earth (box metal), off-board")

    gnd = d.net("GND", domain="SELV", v=0, kind="ground", i_max=0.39, external=True,
                notes="Pi ground via W1 (two conductors)")
    d.domain("SELV", ref="GND", kind="selv", description="Raspberry Pi side, Class 2 / ES1; may be earthed via the Pi")
    v5 = d.net("+5V", domain="SELV", v=(0, 5.25), kind="power", i_max=0.39, notes="coil and LED rail after F1")
    coil_rtn = d.net("COIL_RTN", domain="SELV", v=(0, 3.5), kind="power", i_max=0.39,
                     notes="common low side of all coils; floats <= 3.5 V when disarmed")
    hb_in = d.net("HB_IN", domain="SELV", v=(0, 3.3), kind="signal", external=True, threats=("esd",),
                  notes="heartbeat from BCM12 (Pi pin 32)")
    ch_in = {k: d.net(f"CH{k}_IN", domain="SELV", v=(0, 3.3), kind="signal", external=True, threats=("esd",),
                      notes=f"channel {k} command from Pi pin {PI_PIN[k]}") for k in CHANNELS}

    # -- barriers (DESIGN.md section 6) --------------------------------------------------------------
    sp = "TI SLUP419 (Mar 2024) Tables 3-5 and worked example (IEC 60664-1 F.1/F.2/F.4 subsets, IEC 62368-1 Table 10)"
    d.barrier("SELV", "LINE", grade="reinforced", v_work=V_MAINS_PK, creepage_mm=8.0, clearance_mm=8.0,
              standard="UL/IEC 62368-1 Tables 10 and 17; IEC 60664-1 Tables F.1, F.2, F.4", v_test_rms=3000,
              pollution_degree=2, material_group="IIIb", ovc="II", slot=False,
              source=f"{sp}. Required at 120 V: creepage 3.0 (F.4 125 V MG III x2 [I]), clearance 1.5 (F.2 at 2.5 kV); "
                     "at 240 V: 5.0 / 3.6. Design 8.0/8.0 matches the relay's own 8/8 mm",
              notes="covers NEUTRAL and OUT1-4 (they float on LINE). Hi-pot 3.0 kVrms 60 s type, 1 s production")
    ul = "UL 1059 use group C, 51-150 V: 1/8 in air, 1/4 in surface [S, secondary table]"
    for k in CHANNELS:      # declared first: the narrower NEUTRAL/OUT rules below override overlaps
        d.barrier("LINE", f"OUT{k}", grade="functional", v_work=V_MAINS_PK, creepage_mm=2.5, clearance_mm=1.5,
                  standard="IPC-2221B Table 6-1 B2", pollution_degree=2, ovc="II",
                  source="IPC-2221B B2 151-170 V: 1.25 mm [S]; design 2.5/1.5 outside the relay footprint",
                  notes=f"across K{k}'s open contact; inside the relay footprint the 5.0 mm pin pitch governs")
    d.barrier("LINE", "NEUTRAL", grade="functional", v_work=V_MAINS_PK, creepage_mm=6.4, clearance_mm=3.2,
              standard="UL 1059 / UL 508 practice", pollution_degree=2, ovc="II", source=ul,
              notes="opposite polarity; field-wiring terminals")
    for k in CHANNELS:
        d.barrier("NEUTRAL", f"OUT{k}", grade="functional", v_work=V_MAINS_PK, creepage_mm=6.4, clearance_mm=3.2,
                  standard="UL 1059 / UL 508 practice", pollution_degree=2, ovc="II", source=ul,
                  notes="switched line vs neutral, opposite polarity")
    for j in CHANNELS:
        for k in CHANNELS:
            if j < k:
                d.barrier(f"OUT{j}", f"OUT{k}", grade="functional", v_work=V_MAINS_PK, creepage_mm=6.4,
                          clearance_mm=3.2, standard="UL 1059 / UL 508 practice", pollution_degree=2, ovc="II",
                          source=ul, notes="one output on, the other off: 120 V between them")
    d.barrier("LINE", "PE", grade="basic", v_work=V_MAINS_PK, creepage_mm=6.4, clearance_mm=6.4,
              standard="IEC 62368-1 basic; UL field wiring to dead metal", pollution_degree=2, ovc="II",
              source="62368-1 basic: clearance 0.76 mm at 1.5 kV (SLUP419 Table 5), creepage 1.5 mm [I]; UL field "
                     "wiring to grounded dead metal 1/4 in [S]. Applies to box walls, bottom and ground screw; "
                     ">= 2.0 mm copper-to-board-edge covers a stray bare EGC (basic)",
              notes="PE has no copper on the PCB: met by placement (board 4.95 mm from E/W walls + 2.0 mm edge "
                    "keepout; 12.7 mm nylon supports)")

    # -- block: SELV link input -----------------------------------------------------------------------
    sel = d.block("selv_in", title="Class 2 link from the Pi: terminal, PTC, TVS, ESD", domain="SELV",
                  description="J6 = Class 2 cable from Pi pins 2,6,11,13,15,16,32,34; D11 behind F1 trips it on faults")
    j6 = sel.add(P.TERM_SELV, ref="J6")
    f1 = sel.add(P.PTC_5V, ref="F1")
    d11 = sel.add(P.TVS_5V, ref="D11")
    c1 = sel.add(P.C_10U, ref="C1")
    c2 = sel.add(P.C_100N, ref="C2")
    u1 = sel.add(P.ESD6, ref="U1")
    d10 = sel.add(P.LED_GREEN, ref="D10", v_across=2.5)    # forward only; can never be reverse biased
    r16 = sel.add(P.R_1K5, ref="R16")
    tp1 = sel.add(P.TP, ref="TP1")
    tp2 = sel.add(P.TP, ref="TP2")
    v5_in = sel.net("+5V_IN", v=(0, 5.25), kind="power", i_max=0.39, external=True,
                    threats=("overcurrent", "overvoltage", "reverse_polarity"),
                    notes="Pi 5 V (header pin 2) before the PTC")
    led_pwr = sel.net("LED_PWR_A", v=(0, 5.25))
    v5_in.connect(j6[1], f1[1])
    gnd.connect(j6[2], j6[8], d11["A"], c1[2], c2[2], u1[5], u1[10], d10["K"], tp2[1])
    for k in CHANNELS:
        ch_in[k].connect(j6[k + 2], u1[ESD_PIN[k]])
    hb_in.connect(j6[7], u1["D3+"])
    v5.connect(f1[2], d11["K"], c1[1], c2[1], r16[1], tp1[1])
    led_pwr.connect(r16[2], d10["A"])
    u1.nc_pins("1", "2", "3", "4", "6", "7", reason="NC: not connected internally (SLVSBO7O Table 4-3)")
    u1.nc_pins("8", reason="D3- spare protected channel, left open (unused I/O may float, SLVSBO7O Table 4-3) [I]")

    # -- block: heartbeat watchdog ----------------------------------------------------------------------
    arm = d.block("arm", title="Heartbeat watchdog (charge pump) and common coil enable", domain="SELV",
                  description="Q5 closes the coil return only while HB toggles 100 Hz-2 kHz; OFF <= 0.15 s after it stops")
    r13 = arm.add(P.R_1K, ref="R13")
    c3 = arm.add(P.C_1U, ref="C3")
    d12 = arm.add(P.DIODE_PUMP, ref="D12")
    c4 = arm.add(P.C_100N, ref="C4")
    r14 = arm.add(P.R_1M, ref="R14")
    q5 = arm.add(P.MOSFET, ref="Q5", p_diss=0.011)
    d9 = arm.add(P.LED_GREEN, ref="D9", v_across=2.5)      # forward only; never reverse biased
    r15 = arm.add(P.R_1K5, ref="R15")
    tp3 = arm.add(P.TP, ref="TP3")
    tp4 = arm.add(P.TP, ref="TP4")
    hb_r = arm.net("HB_R", v=(0, 3.3))
    pump = arm.net("PUMP", v=(-0.3, 3.0))
    arm_g = arm.net("ARM_G", v=(0, 2.75))
    led_arm = arm.net("LED_ARM_A", v=(0, 5.25))
    hb_in.connect(r13[1])
    hb_r.connect(r13[2], c3[1])
    pump.connect(c3[2], d12["COM"])
    gnd.connect(d12["A"], c4[2], r14[2], q5["S"])
    arm_g.connect(d12["K"], c4[1], r14[1], q5["G"], tp3[1])
    coil_rtn.connect(q5["D"], d9["K"], tp4[1])
    v5.connect(r15[1])
    led_arm.connect(r15[2], d9["A"])

    # -- blocks: four identical channels ---------------------------------------------------------------
    ch = {}
    for k in CHANNELS:
        b = d.block(f"ch{k}", title=f"Channel {k}: relay K{k}, driver Q{k}, output J{k + 1}", domain="SELV",
                    description=f"CH{k}_IN = Pi pin {PI_PIN[k]}; K{k} switches L_IN to L_SW{k}; J{k + 1} = OUT{k} L/N")
        rk = b.add(P.R_1K, ref=f"R{k}")
        rpd = b.add(P.R_4K7, ref=f"R{k + 4}")
        q = b.add(P.MOSFET, ref=f"Q{k}", p_diss=0.0005)
        dk = b.add(P.DIODE_FLYBACK, ref=f"D{k}")
        led = b.add(P.LED_GREEN, ref=f"D{k + 4}", v_across=2.5)   # forward 2.5 V max; reverse <= 0.9 V (flyback)
        rled = b.add(P.R_1K5, ref=f"R{k + 8}")
        rel = b.add(P.RELAY, ref=f"K{k}")
        jk = b.add(P.TERM_MAINS, ref=f"J{k + 1}")
        g = b.net(f"CH{k}_G", v=(0, 3.3))
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
        d.nets[f"L_SW{k}"].connect(rel["C_4_5"], jk[1])
        d.nets["N"].connect(jk[2])
        ch[k] = dict(r=rk, rpd=rpd, q=q, d=dk, led=led, rled=rled, k=rel, j=jk)

    # -- block: mains input ----------------------------------------------------------------------------
    mi = d.block("mains_in", title="Mains input terminal (shared L, N)", domain="LINE",
                 description="J1 = branch line and neutral; EGCs are spliced in the box, never on this board")
    j1 = mi.add(P.TERM_MAINS, ref="J1")
    d.nets["L_IN"].connect(j1[1])
    d.nets["N"].connect(j1[2])

    # -- block: mechanical -------------------------------------------------------------------------------
    me = d.block("mech", title="Mounting holes, SELV cover and box parts (BOM only)",
                 description="H1-H4 + LCBS-8-19 supports MP5-MP8; MP1 SELV cover; MP2-MP4 box, ring, cover")
    holes = [me.add(P.HOLE_4MM, ref=f"H{i}") for i in (1, 2, 3, 4)]
    mp1 = me.add(P.SELV_COVER, ref="MP1")
    me.add(P.BOX, ref="MP2")
    me.add(P.RING, ref="MP3")
    me.add(P.COVER, ref="MP4")
    for i in (5, 6, 7, 8):
        me.add(P.SUPPORT, ref=f"MP{i}")

    hazards(d)
    calcs(d)
    placement(d, j1, j6, u1, f1, d11, c1, c2, r13, c3, d12, c4, r14, q5, ch, holes, mp1, sel, arm, mi, me)
    board(d)
    waivers(d)
    return d


def placement(d, j1, j6, u1, f1, d11, c1, c2, r13, c3, d12, c4, r14, q5, ch, holes, mp1, sel, arm, mi, me):
    pl = d.place
    # floorplan, south to north: SELV band | coil pins | 8 mm barrier band | L bus, contacts | terminals | N bus
    pl.region(sel, "south", note="SELV band; J6 in the south-west corner next to the Class 2 knockout")
    pl.region(arm, "south")
    pl.region(mi, "north", note="J1 at the west end of the terminal row")
    pl.group(sel, "close")
    pl.group(arm, "close")
    terms = [j1] + [ch[k]["j"] for k in CHANNELS]
    relays = [ch[k]["k"] for k in CHANNELS]
    for t in terms:
        pl.edge(t, "north", note="wire entry from above; free band along the north wall holds slack and the EGC splice")
        pl.orient(t, "north", note="pole-2 (N) pin row toward the north edge, pole-1 row toward the relays")
    pl.edge(j6, "south")
    pl.custom("corner", obj=j6, corner="southwest", note="next to the west-wall knockout used by the Class 2 cable")
    pl.array(terms, "x", note="butted 2-pole blocks, 17.85 mm pitch")
    pl.array(relays, "x")
    for k in CHANNELS:
        c = ch[k]
        pl.group(next(b for b in d.blocks if b.name == f"ch{k}"), "close")
        pl.align([c["k"], c["j"]], "x", note=f"channel {k} column: relay under its terminal")
        pl.align([c["q"], c["k"]], "x")
        pl.align([c["led"], c["k"]], "x")
        pl.orient(c["k"], "south", note="coil pins A1/A2 toward the SELV band (south), contacts toward the terminals")
        pl.near(c["d"], c["k"]["COIL_1"], "tight")
        pl.near(c["d"], c["k"]["COIL_8"], "tight")
        pl.near(c["q"], c["k"]["COIL_8"], "close")
        pl.near(c["rpd"], c["q"]["G"], "tight")
        pl.near(c["r"], c["rpd"], "tight")
        pl.near(c["led"], c["k"], "close", note="LED visible next to its relay; silkscreen channel number")
        pl.near(c["rled"], c["led"], "tight")
        pl.hot_loop([c["d"]["K"], c["k"]["COIL_1"], c["k"]["COIL_8"], c["d"]["A"]],
                    note="coil flyback loop; keep spikes off SELV wiring")
        pl.hot_loop([c1[1], c["k"]["COIL_1"], c["k"]["COIL_8"], c["q"]["D"], c["q"]["S"], q5["D"], q5["S"], c1[2]],
                    note="coil switching loop")
        pl.thermal(c["k"], 1.5, "copper", note="coil 0.4 W + contacts ~1.1 W at 15 A; L/L_SW pours both layers, "
                                                "no airflow (closed box)")
        pl.near(q5, c["q"], "close", note="short COIL_RTN")
    pl.near(u1, j6, "tight")
    pl.near(f1, j6[1], "close")
    pl.near(d11, f1[2], "tight")
    pl.near(c1, d11, "close")
    pl.near(c2, c1, "tight")
    pl.near(r13, u1["D3+"], "close")
    pl.near(c3, r13, "tight")
    pl.near(d12, c3, "tight")
    pl.near(c4, d12["K"], "tight")
    pl.near(r14, c4, "tight")
    pl.near(q5, c4, "close")
    pl.thermal(j1, 0.3, "copper")
    pl.far(j6, j1, "loose")
    pl.side("all", "top", note="all parts on the top side")
    # isolation: every barrier becomes a separate() relation and a .kicad_dru rule
    for bar in d.barriers:
        # Domain objects, not names: placement treats bare strings like "OUT1" as refdes (framework issue)
        pl.separate(d.domains[bar.a], d.domains[bar.b], slot=bar.slot)
    pl.keepout("barrier band: from the K1-K4 coil-pad north edge (+1.0 mm from the pin row) to +9.25 mm, "
               "full board width", what="copper and vias", layers="all",
               note="only relay bodies may overhang it; mains copper starts >= 8.25 mm from the coil pads")
    pl.keepout("2.0 mm strip along every board edge", what="mains copper", layers="all",
               note="E/W walls: 4.95 mm + 2.0 mm = 6.95 mm >= 6.4 mm; basic insulation to a stray bare EGC")
    for h in holes:
        pl.keepout(h, what="copper and parts, Ø8 mm", layers="all")
    pl.custom("volume_keepout", region="above J1-J5 up to 45 mm", what="parts and MP1",
              note="wire-bending volume for 14-12 AWG solid conductors entering the terminals from above")
    pl.custom("volume_keepout", region="SELV band under MP1", what="parts taller than 18 mm")
    for net in ["L_IN", "N"] + [f"L_SW{k}" for k in CHANNELS]:
        pl.custom("current_path", net=f"net:{net}", amps=15, width_mm=7.5, layers="F.Cu,B.Cu", copper_oz=2,
                  stitching="4 x 0.6 mm vias every 10 mm",
                  note="L comes down the west side from J1.1 then E-W under the relay bodies into pads 13; L_SWk "
                       "goes north from pads 14 to J(k+1).1; N follows the north edge through every J.2, >= 6.4 mm "
                       "from the L_SW pads (place J1-J5 ~2 mm in from the north edge)")
    pl.custom("barrier_part", part=mp1, covers="SELV band except the J6 wire entry", height_mm=20,
              fixing="2 NPTH snap holes in the SELV band",
              note="keeps field mains conductors off SELV parts (reinforced insulation, NEC 725.136(B))")
    pl.custom("box_walls", walls="RACO 257: inner ~115.9 mm square, inner depth 54 mm + 39.7 mm ring",
              board_position="south edge against the south wall; ~36 mm free band along the north wall",
              note="box metal is PE: mains copper >= 6.4 mm from walls, bottom and ground screw")
    pl.custom("ground_screw", where="free band; RACO 257 #10-32 tap 30.2 mm from the north outer edge",
              note="orient the box so the screw falls in the free band, or use a listed ground clip")
    pl.custom("cable_entry", mains="north/east/west walls and ring knockouts, above the terminals",
              selv="west-wall knockout next to J6 with a listed bushing", note="Class 2 cable kept away from mains")
    pl.custom("label", obj="J1", text="LINE IN / NEUTRAL IN")
    for k in CHANNELS:
        pl.custom("label", obj=ch[k]["j"], text=f"OUT{k} L / N")
    pl.custom("label", obj=j6, text="+5V GND CH1 CH2 CH3 CH4 HB GND - CLASS 2 ONLY")
    pl.custom("label", obj="board", text="120 VAC 60 Hz, 15 A max branch; Cu 14-12 AWG, strip 11-13 mm; DANGER "
                                         "disconnect before opening; outputs are not a disconnecting means")


def board(d):
    holes = [Hole(4, 4, 4.0, note="H1, LCBS-8-19 nylon support"), Hole(102, 4, 4.0, note="H2, LCBS-8-19"),
             Hole(4, 76, 4.0, note="H3, LCBS-8-19"), Hole(102, 76, 4.0, note="H4, LCBS-8-19")]
    d.board(width_mm=106, height_mm=80, layers=2, thickness_mm=1.6, copper_oz=2, holes=holes,
            max_component_height_mm=31, max_bottom_height_mm=2.4,
            enclosure="Hubbell RACO 257 steel box 4-11/16 x 2-1/8 in (42.0 in3) + RACO 250 1-1/2 in extension "
                      "ring (29.5 in3) + RACO 832 flat blank cover; board on 4 x Essentra LCBS-8-19 12.7 mm nylon "
                      "supports in installer-drilled 4.75 mm holes; inner depth ~93.7 mm",
            coating="",
            keepouts=[
                {"rect": [0, 0, 106, 2.0], "what": "mains copper", "layers": "all", "note": "edge strip"},
                {"rect": [0, 78.0, 106, 80], "what": "mains copper", "layers": "all", "note": "edge strip"},
                {"rect": [0, 0, 2.0, 80], "what": "mains copper", "layers": "all", "note": "edge strip"},
                {"rect": [104.0, 0, 106, 80], "what": "mains copper", "layers": "all", "note": "edge strip"},
                {"relative": "K1-K4 coil-pad edge to +8.25 mm north, full width", "what": "copper and vias",
                 "layers": "all", "note": "SELV/mains barrier band"},
            ],
            notes="FR-4 UL 94 V-0, UL ZPMV2 laminate, CTI >= 175 V preferred (IIIb assumed). All parts top side. "
                  "Solder tails <= 2.4 mm below the board, 10.3 mm above the box bottom. Pi outside the box, <= 3 m. "
                  "Flush mounting in an insulated wall is excluded (thermal).")


def waivers(d):
    W = d.waive
    W("rating.current", r"^K[1-4] \(G5RL",
      "Relay contacts at 15 A vs 16 A (94 %): UL E41643 lists 16 A general use at 40 C (50k ops) and VDE lists "
      "16 A at 85 C. 15 A is the branch-breaker ceiling, not a continuous load; continuous loads are limited to "
      "12 A = 75 % (REQ-5, calc relay_contact_continuous_ratio). Verified by T-OL and T-HEAT.")
    W("rating.current", r"^D(1|2|3|4|5|6|7|8|9|10|12) \(",
      "Checker applies the whole net current to every series-category pin on the net, but these parts are in "
      "shunt: flyback diodes D1-D4 carry only the 93 mA coil current for a few ms at release (I_FM 300 mA); "
      "LEDs D5-D10 carry 2.3 mA (25 mA rating); D12 carries the < 0.1 mA pump current (200 mA rating).")
    W("protect.threat", r"threat 'surge'",
      "No MOV/TVS on mains by design (DESIGN.md C-11): insulation is coordinated for OVC II (1.5 kV transient; "
      "relay 10 kV impulse coil-contact, PCB 8 mm reinforced, 6.4 mm functional). An MOV ages and is a fire source "
      "in a closed unlisted box; a listed Type 2 SPD at the panel is recommended (Q-9). Verified by T-SURGE.")
    W("protect.threat", r"net (L_IN|L_SW[1-4]) declares threat 'overcurrent'",
      "The upstream branch breaker (<= 15 A, REQ-2) is the single overcurrent device; every element on these nets "
      "is rated >= 15 A at temperature (terminals 31 A, relays 16 A, copper 7.5 mm x 2 layers x 2 oz with 1.4x "
      "I2t margin at 2 kA; calcs mains_*). A fuse inside a closed box is not serviceable (C-9).")
    W("protect.entry_fuse", r"net (L_IN|N|L_SW[1-4]) reaches",
      "Same as the overcurrent waiver: the branch breaker (<= 15 A) protects every element downstream (C-9).")
    W("protect.threat", r"\+5V_IN declares threat '(overvoltage|reverse_polarity)'",
      "D11 (SMAJ7.0A) sits on +5V directly behind F1 (PolyZen arrangement): transients are clamped through F1's "
      "0.06-0.2 ohm; a sustained overvoltage or a reversed supply makes D11 conduct and F1 trips (2.2 A). A TVS "
      "ahead of F1 would burn instead. The check only looks for protectors on the same net.")
    W("lib.footprint_custom", r"WAGO_2606",
      "No KiCad library footprint exists for WAGO 2606-3102/020-000. Geometry from the WAGO data sheet p.1 drawing "
      "(drill 2.0 +0.1 mm, pole 2 at +7.5/+12.5 mm, body 17.85 x 24 mm); lever side to be checked against WAGO "
      "CAD before layout freeze.")
    W("conn.empty_net", r"net PE",
      "PE exists only off-board (box, ring, cover, EGC splice); no PCB copper by design (REQ-4, NEC 250.148(B)). "
      "The net is declared so the LINE-PE barrier reaches intent.yaml.")
    W("hazard.procedural", r"^H10:",
      "Relays are not a disconnecting means; locking out the branch breaker is the only correct mitigation.")
    W("hazard.procedural", r"^H15:",
      "Motor overload protection belongs to the load (NEC 430), outside this board; REQ-5 limits motors to 1/2 hp.")
