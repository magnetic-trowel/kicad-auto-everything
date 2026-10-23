# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""liion-balancer: active cell balancer for a 13-16S home Li-ion pack (about 10 kWh).

Encodes designs/liion-balancer/DESIGN.md (engineering rationale, evidence tags, sources) and
CONNECTIONS.md (net table and naming rules). Build: `kaesynth build designs/liion-balancer/design.py -v`.

One LT8584 isolated flyback per cell (cell -> whole stack, about 2.5 A), an ADBMS1818 monitor whose
S pins enable the balancers, an STM32G031 controller, a second enable path through an opto string,
and an isolated UART plus a PhotoMOS fault contact for the user.

Voltage model (what the rating checks run on):
  BAT0      root, ref TAP0 (B-, the user's "system ground"). GND_B joins TAP0 at net tie NT1.
  C1..C16   cell k floats on TAP(k-1); TAPk is (0, 4.2) V above it. 0 V is allowed because a
            13-15S pack bridges the unused top positions (CONNECTIONS.md section 11). The stack
            envelope is therefore 0-67.2 V: the 16S NMC hardware limit (REQ-2 caps use at 60 V,
            which the envelope cannot express - see the framework notes in the report).
  SNS1..15  nets at tap potential through >= 100 ohm (filtered sense CS_k, LT8584 MODE_k):
            float on TAPk, +/-10 mV.
  STACK     floats on TAP16: fused stack supply, VPLUS, buck input, CS_16, MODE_16, string top.
  RET       floats on TAP0: flyback return bus FLYBUS, secondaries SEC_k, buck switch node,
            opto-string bottom STR_Q.
  BOOT      floats on the buck switch node (bootstrap).
  STR1..16  opto-string nodes: LEDA_k floats on LEDA_(k-1) (STR_Q for k = 1), 0-1.4 V forward.
  CTRL      floats on GND_B: 5 V / 3.3 V logic.
  USER      root, ref GND_ISO: isolated UART port (reinforced barrier to the battery).
  FAULT     root, ref FLT_B: PhotoMOS fault contact (reinforced barrier to the battery).
  CHASSIS   root: mounting screws / enclosure metal (no copper on the board).

Net ranges are normal-operation worst cases (all tolerances). Single-fault stresses (open return,
shorted parts) are calculations with explicit limits, as DESIGN.md section 7 states them.
"""
import importlib.util
import math
from pathlib import Path

from kaesynth import Design, Hole

_spec = importlib.util.spec_from_file_location("liion_balancer_parts", Path(__file__).with_name("parts.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

BRIEF = ("I want a battery balancer that can balance a string, series string of 12 volt lead acid batteries. "
         "I want another one that can balance a series string of lithium ion batteries. This would be in the "
         "10 kilowatt hour range, so home packs. It should make sure that there's no pathways for voltage to "
         "jump from places. I don't know if you want to do a flying capacitor or inductor or some other "
         "elegant approach, but it needs to keep the charge balanced without bleed resistors. Ideally, it "
         "would be as efficient as possible, as robust as possible, and allow us to have little wires that go "
         "to the system ground and then all of the individual positive terminals.")

N = 16                       # channels (series positions); 13-15S bridge the top positions
TAPS = range(0, N + 1)
CH = range(1, N + 1)
V_CELL = (0.0, 4.2)          # per position: 0 V when bridged, 4.2 V NMC full
V_STACK = N * V_CELL[1]      # 67.2 V hardware envelope
V_FLY = V_STACK + 0.5        # FLYBUS: stack + D1 forward drop
V_SW = (-0.7, 38.5)          # LT8584 SW: body diode .. V_IN + RCD clamp (C-5, C-6)
I_TAP = 2.6                  # A, per tap (C-7)
I_FLY = 1.6                  # A, FLYBUS with 8 channels at the 32.5 V minimum stack (C-8)
W_TAP = 1.5                  # mm: taps run on inner layer L3 (corridors); 2.6 A, 2 oz, dT <= 10 K (IPC-2152 [S])


def kk(k):
    return f"{k:02d}"


# =================================================================================================
# Intent: requirements, assumptions, questions (DESIGN.md sections 2-3)

def intent(d):
    R = d.require
    R("REQ-1", "Pack: one series string, 13-16 positions (a position may be a parallel group), about 10 kWh",
      value="13-16S", source="brief; ASM-1", verify="T-FUNC at 13S and 16S")
    R("REQ-2", "Chemistry and stack voltage: LFP 2.50-3.65 V/cell or NMC/NCA 3.00-4.20 V/cell; stack <= 60.0 V "
      "in use; hardware rated to 67.2 V", value="<= 60.0 V (ES1)", source="IEC 62368-1 ES1 [S]; C-3",
      verify="configuration check at boot (REQ-F7)")
    R("REQ-3", "No bleed resistors: energy returned to the stack", value=">= 72 % with a 1 m harness, >= 78 % "
      "board only (3.3 V cell, 51 V stack)", source="brief", verify="T-EFF; calc eff_*")
    R("REQ-4", "Balancing current per discharged cell", value=">= 2.0 A average (typ 2.5 A)", source="C-2",
      verify="T-EFF; calc i_in_avg_A")
    R("REQ-5", "Concurrency", value="<= 8 channels at once, NTC derated", source="C-12", verify="T-THERM")
    R("REQ-6", "Cell measurement with balancing muted", value="<= +/-4 mV at 3.3 V over temperature",
      source="ADBMS1818 Rev A Table 3 [P]; C-4", verify="T-MEAS")
    R("REQ-7", "Wiring: N+1 wires, the B- cell terminal (system ground) plus every cell positive",
      value="17 wires for 16S", source="brief", verify="inspection")
    R("REQ-8", "Tap fusing: battery end 7 A >= 125 VDC >= 10 kA; board 5 A very fast, 300 A at <= 32 VDC, "
      "replaceable", value="0324007 + 0154005", source="brief; C-7", verify="F-1..F-6")
    R("REQ-9", "No voltage jumps: no single part fault creates a path between non-adjacent taps able to carry "
      "> 0.5 A; a one-cell short clears in <= 10 ms. Exception: T1kk interwinding insulation (1500 Vrms vs "
      "<= 67 V, 22x) is a safeguard; its residual is cleared by the battery-end fuses",
      value="<= 0.5 A; <= 10 ms", source="brief", verify="FMEA (hazards H-1, H-2); F-1..F-4; calc t_clear_*")
    R("REQ-10", "Bounded fault energy: every fault path has a fuse rated for its voltage and prospective current",
      value="-", source="derived", verify="calc fuse_*")
    R("REQ-11", "Spacing per DESIGN.md 6.3: functional per IPC-2221B inside the battery; reinforced to the "
      "user port and fault contact", value="B-1..B-6", source="IPC-2221B, IEC 60664-1, IEC 62368-1 [S]",
      verify="DRC (.kicad_dru), T-HIPOT")
    R("REQ-12", "Per-cell standing current (balancing off), equal across cells", value="<= 30 uA worst case "
      "(sum of datasheet maxima), typ <= 3 uA; mismatch drift <= 0.15 %/yr of 200 Ah",
      source="brief ('balanced'); C-9", verify="T-IQ; calc iq_cell_*")
    R("REQ-13", "Stack standing current", value="<= 50 uA sleep, <= 5 mA monitoring", source="C-9",
      verify="T-IQ; calc iq_stack_max_uA")
    R("REQ-14", "Mis-wiring (swapped, reversed, offset or out-of-order taps) causes no fire and no cell damage; "
      "fuses open and the self-test locks out", value="-", source="brief ('robust')", verify="F-6, F-7")
    R("REQ-15", "Open tap detected before each session and within 1 s while balancing", value="<= 1 s",
      source="C-11", verify="F-5")
    R("REQ-16", "Stuck-on channel: two independent enables per channel plus a hardware watchdog",
      value="watchdog <= 2.2 s", source="H-4", verify="F-8; calc adbms_watchdog_max_s")
    R("REQ-17", "No overcharge: a cell at >= V_full - 20 mV is never net-charged by balancing", value="-",
      source="H-5", verify="F-9 (REQ-F2)")
    R("REQ-18", "Coexist with the pack BMS: never switch the pack or replace protection; measure every cell; "
      "expose data and a fault contact", value="-", source="task; Q-2", verify="review")
    R("REQ-19", "Telemetry: isolated UART 115200 8N1, host logic 2.25-5.5 V; firmware update over it",
      value="UART", source="Q-7", verify="T-FUNC")
    R("REQ-20", "Environment: indoor (garage, utility room), 0-45 C operating, -20..60 C storage, "
      "non-condensing, <= 2000 m, pollution degree 2", value="0-45 C", source="task", verify="T-THERM")
    R("REQ-21", "Temperatures: LT8584 TJ <= 105 C; every part >= 20 C below its rating at 45 C ambient with "
      "the derating of REQ-F3", value="-", source="derived", verify="T-THERM; calc *_temp_*")
    R("REQ-22", "Harness connector: pluggable, polarized, >= 12 A and >= 300 V per pole", value="MSTB 5.08",
      source="derived", verify="inspection")
    R("REQ-23", "Follow UL 1973 / UL 9540 / IEC 62619 BMS practice; no certification claim", value="-",
      source="task", verify="review")
    # Firmware-enforced constraints (the hardware relies on them; each has a firmware test)
    R("REQ-F1", "Kick the ADBMS1818 watchdog (any valid command) at least every 0.5 s while balancing",
      value="<= 0.5 s", source="C-11", verify="firmware test F-8: halt the MCU, DCC clears in 1.8-2.2 s")
    R("REQ-F2", "Active-set rule: every cell >= V_full - 20 mV is in the discharge set; if more than 8 cells "
      "qualify, do not balance", value="-", source="H-5", verify="firmware test F-9")
    R("REQ-F3", "Thermal derating from TH1-TH3: 8 channels below 60 C, 4 below 70 C, none at >= 80 C",
      value="-", source="C-12, H-11", verify="firmware test F-13 and T-THERM")
    R("REQ-F4", "Measure only with balancing muted (MUTE or DCP = 0), then unmute; plausibility: sum of cells "
      "vs SC within 50 mV", value="-", source="H-6", verify="firmware test F-12")
    R("REQ-F5", "FLYBUS supervision: ADC analog watchdog on PA0 (FLY_SNS), threshold = last stack + 4 V; on "
      "trip drop BAL_EN and clear DCC within 1 ms", value="<= 1 ms", source="C-11, C-15 (D2 clamp energy)",
      verify="firmware test F-10: lift D1 while balancing")
    R("REQ-F6", "Before each session: pulse test every tap (open wire, harness resistance) and prove both "
      "enable paths (BAL_EN off -> no step; DCC off -> no step)", value="5 ms pulse", source="C-11",
      verify="firmware test F-5 and F-8")
    R("REQ-F7", "Series count N configured; at boot cells N+1..16 must read < 50 mV and cells 1..N 2.5-4.2 V, "
      "else lock out and close the fault contact", value="-", source="H-8, H-14",
      verify="firmware test F-6, F-14")
    R("REQ-F8", "Discharge floor 3.0 V (LFP) / 3.4 V (NMC); deep sleep below 2.8 V per cell", value="-",
      source="H-4, H-13", verify="firmware test F-8, T-IQ")

    A = d.assume
    A("ASM-1", "Reference pack 16S LFP 3.2 V 200 Ah = 51.2 V, 10.24 kWh; 15S LFP and 13-14S NMC also occur, so "
      "the series count is configurable")
    A("ASM-2", "The pack keeps its own BMS for protection")
    A("ASM-3", "M6 studs or busbar holes at the cells; harness <= 1.0 m")
    A("ASM-4", "A parallel group counts as one cell; balancing time scales with its capacity")
    A("ASM-5", "The inverter may be transformerless, so the battery may sit at mains potential: the user port "
      "is reinforced for 250 Vrms")
    A("ASM-6", "UL 94 V-0 plastic enclosure, pollution degree 2, natural convection")
    A("ASM-7", "Imbalance drift <= 0.25 %/day worst case, about 0.04 %/day typical")
    A("ASM-8", "Pack-bus transients are absorbed by the milliohm cells; taps see the cell voltage plus tens of mV")
    A("ASM-9", "Firmware implements REQ-F1..F8 (not part of this step)")

    Q = d.question
    Q("Q-1", "Pack range: confirm 13-16S at <= 60 V. Above 60 V leaves ES1/SELV; below 13S the transformer's "
      "30 V output minimum is not met (NA6252-AL would be needed).", blocking=True,
      default="13-16S, <= 60 V in use; hardware checked to the 67.2 V 16S NMC envelope")
    Q("Q-2", "BMS interaction: disable the pack BMS's bleed balancing? Is a CAN/RS-485 link required?",
      blocking=True, default="BMS untouched; isolated UART and fault contact only")
    Q("Q-3", "Is the battery isolated from mains by the inverter? If so the user barrier can be functional.",
      blocking=True, default="reinforced (safe either way)")
    Q("Q-4", "Harness: accept 18 AWG <= 1 m, M6 rings and an axial fuse sealed in heat-shrink? Who builds it?",
      blocking=True, default="0324007.HXP sealed in adhesive heat-shrink, built per CONNECTIONS.md section 11")
    Q("Q-5", "Balancing window: LFP top-balance only, or also near empty?", default="top-balance only")
    Q("Q-6", "Fault contact: close on fault (no standing current) or open on fault (fail-safe, 5 mA)?",
      default="close on fault")
    Q("Q-7", "Is UART enough for telemetry?", default="UART 115200 8N1")
    Q("Q-8", "Enclosure, mounting and conformal coating: who provides them?", default="V-0 enclosure TBD, no coating")
    Q("Q-9", "Wiring an add-on to a listed UL 1973/9540 battery may void the listing: acceptable to owner and AHJ?",
      default="owner's decision; documented")
    Q("Q-10", "Bidirectional version (LTC3300-1) wanted? Weaker fault containment.", default="no")
    Q("Q-11", "ADBMS1818 lead time 52 weeks: qualify the pin-identical LTC6813-1 as second source?",
      default="yes, same footprint")


# =================================================================================================
# Domains, global nets, barriers

def domains_and_nets(d):
    n = {}
    # -- battery side ---------------------------------------------------------------------------
    n["TAP0"] = d.net("TAP0", domain="BAT0", v=0, kind="power", i_max=I_TAP, width_mm=W_TAP,
                      notes="stack - (B- cell terminal) after F100; also the flyback return of every secondary")
    d.domain("BAT0", ref="TAP0", kind="battery", edge_clearance_mm=3.0,
             edge_source="B-5 basic insulation to chassis screws, 250 Vrms worst case: 2.5 mm creepage, "
                         "1.5 mm clearance (IEC 60664-1 F.4/F.2 via TI SLUP419 [S]); 3.0 mm used",
             description="bottom of the stack (root). Floating cells, stack, return and controller nets "
                         "all float on it")
    n["GND_B"] = d.net("GND_B", domain="BAT0", v=0, kind="ground", i_max=0.06,
                       notes="controller ground; joins TAP0 only at NT1 on pad F100.2")
    n["CS_0"] = d.net("CS_0", domain="BAT0", v=(-0.01, 0.01), kind="sense", notes="filtered C0 sense")
    for k in CH:
        d.domain(f"C{k}", ref=f"TAP{k - 1}", kind="battery",
                 description=f"cell {k}: floats on TAP{k - 1}; TAP{k} is 0-4.2 V above it")
        n[f"TAP{k}"] = d.net(f"TAP{k}", domain=f"C{k}", v=V_CELL, kind="power", i_max=I_TAP, width_mm=W_TAP,
                             notes=f"cell {k} + after F1{kk(k)}")
        n[f"S_{k}"] = d.net(f"S_{k}", domain=f"C{k}", v=V_CELL, kind="signal",
                            notes=f"ADBMS1818 S{k} -> LT8584 DIN (low = enable)")
    for t in TAPS:
        dom = "BAT0" if t == 0 else f"C{t}"
        n[f"TAP{t}_IN"] = d.net(
            f"TAP{t}_IN", domain=dom, v=(-0.05, 0.05) if t == 0 else V_CELL, kind="power", i_max=I_TAP,
            external=True, threats=("overcurrent", "overvoltage", "esd", "reverse_polarity"),
            notes=f"harness wire {t} through J1 pin {t + 1}, before the board fuse; hot-plug, swapped or "
                  f"reversed taps arrive here")
    for k in range(1, N):
        d.domain(f"SNS{k}", ref=f"TAP{k}", kind="battery",
                 description=f"nets at TAP{k} potential through >= 100 ohm (CS_{k}, MODE_{k})")
        n[f"CS_{k}"] = d.net(f"CS_{k}", domain=f"SNS{k}", v=(-0.01, 0.01), kind="sense",
                             notes="R3 x 100 uA open-wire current = 10 mV")
    d.domain("STACK", ref="TAP16", kind="battery",
             description="stack-top nets: fused supply, VPLUS, buck input, CS_16, MODE_16, LED-string top")
    n["CS_16"] = d.net("CS_16", domain="STACK", v=(-0.01, 0.01), kind="sense")
    n["STK_F"] = d.net("STK_F", domain="STACK", v=(-0.05, 0), kind="power", i_max=0.012,
                       notes="TAP16 after F1 (1.7 ohm x 10 mA); 0.66 A in a buck or V+ short until F1 opens")
    d.domain("RET", ref="TAP0", kind="battery",
             description="flyback return bus, secondaries, buck switch node, LED-string bottom (0-68 V on TAP0)")
    n["FLYBUS"] = d.net("FLYBUS", domain="RET", v=(0, V_FLY), kind="power", i_max=I_FLY,
                        notes="flyback outputs -> D1 -> TAP16. Normal = stack + 0.5 V; an open return lets D2 "
                              "clamp it at <= 94 V for <= 1 ms (calc flybus_clamp_*)")
    n["STR_Q"] = d.net("STR_Q", domain="RET", v=(0, V_STACK), kind="signal",
                       notes="bottom of the 16-LED opto string, Q1 collector: 2.4-40 V on, floats up when off")
    for k in CH:
        d.domain(f"STR{k}", ref="STR_Q" if k == 1 else f"LEDA_{k - 1}", kind="battery",
                 description=f"opto string node {k}: one TLP293 LED above the node below it")
        n[f"LEDA_{k}"] = d.net(f"LEDA_{k}", domain=f"STR{k}", v=(0, 1.4), kind="signal",
                               notes="series string, same current in every LED: never reverse biased; "
                                     "<= 1.4 V forward (TLP293 VF max)")
    d.domain("CTRL", ref="GND_B", kind="selv", description="5 V / 3.3 V controller logic on GND_B")
    V5, V33 = (0, 5.15), (0, 3.37)
    n["5V_SYS"] = d.net("5V_SYS", domain="CTRL", v=V5, kind="power", i_max=0.06,
                        notes="LM5164 output 4.99 V (+3 % with 1 % resistors)")
    n["+3V3"] = d.net("+3V3", domain="CTRL", v=V33, kind="power", i_max=0.025, notes="MCP1700 +/-2 %")
    for name, v, kind in (("SPI_CS", V33, "signal"), ("SPI_SCK", V33, "clock"), ("SPI_MOSI", V33, "signal"),
                          ("SPI_MISO", V33, "signal"), ("ADBMS_WDT", V33, "signal"), ("PGOOD", V33, "signal"),
                          ("FLY_SNS", (0, 3.3), "sense"), ("BAL_EN", V33, "signal"), ("MCU_TX", V33, "signal"),
                          ("MCU_RX", V33, "signal"), ("ISO_VCC1", V33, "power"), ("FLT_DRV", V33, "signal")):
        n[name] = d.net(name, domain="CTRL", v=v, kind=kind)
    n["FLY_SNS"].notes = "FLYBUS x 100k/2.1M: 3.22 V at 67.7 V; MCU clamp takes <= 7 uA in a clamp fault"
    n["ISO_VCC1"].notes = "U5 side-1 supply from PB0 (<= 4 mA); off when no host is present"
    # -- user side ------------------------------------------------------------------------------
    n["GND_ISO"] = d.net("GND_ISO", domain="USER", v=0, kind="ground", external=True, threats=("esd",),
                         notes="host ground (J2.1)")
    d.domain("USER", ref="GND_ISO", kind="selv",
             description="isolated UART port; may be earthed by the host while the battery floats at mains "
                         "potential (ASM-5)")
    n["FLT_B"] = d.net("FLT_B", domain="FAULT", v=0, kind="signal", external=True, threats=("esd",),
                       i_max=0.05, notes="fault contact, terminal B (J4.2)")
    d.domain("FAULT", ref="FLT_B", kind="other", description="PhotoMOS dry contact, user circuit <= 30 V, 50 mA")
    n["CHASSIS"] = d.net("CHASSIS", domain="CHASSIS", v=0, kind="pe",
                         notes="mounting screws and enclosure metal; no copper on the PCB (barrier B-5)")
    d.domain("CHASSIS", ref="CHASSIS", kind="other", earthed=True, description="chassis / PE (off-board)")
    return n


def barriers(d):
    ipc = "IPC-2221B Table 6-1"
    seq = ["BAT0"] + [f"C{k}" for k in CH] + ["STACK"]   # potential order along the stack
    # B-1: adjacent positions (one cell apart). Declared first so the B-2 rules inherited through
    # floating domains (declared later) override them for every non-adjacent pair.
    for a, b in zip(seq, seq[1:]):
        d.barrier(a, b, grade="functional", v_work=8.4, creepage_mm=0.2, clearance_mm=0.2,
                  standard=f"{ipc} B2 0-15 V: 0.1 mm [S]", pollution_degree=2,
                  source="DESIGN.md 6.3 B-1: <= 4.2 V, 8.4 V in a swap fault; 0.2 mm used",
                  notes="SW_k/SNB_k reach 38.5 V on their own cell: their copper keeps 0.6 mm (custom "
                        "relation 'spacing'); the LT8584 pins themselves are ADI's pitch")
    # B-2: two or more positions apart (up to 67 V). Each barrier covers seq[i] vs everything that
    # floats on seq[i+2] (inherited), so this chain covers every non-adjacent pair.
    for a, b in zip(seq, seq[2:]):
        d.barrier(a, b, grade="functional", v_work=V_STACK, creepage_mm=0.6, clearance_mm=0.6,
                  standard=f"{ipc} B2 31-150 V: 0.6 mm external; B1 internal 0.1-0.2 mm [S]",
                  pollution_degree=2,
                  source="DESIGN.md 6.3 B-2. 0.6 mm is the IPC requirement; 1.0 mm preferred on open board. "
                         "1.0 mm cannot be held at the LM5164 HSOP-8 (EP to SW 0.75 mm) or ADBMS1818 pins")
    # B-2 / B-3: return bus and controller vs every cell. RET carries the T1kk secondaries: the
    # transformer primary/secondary interface is this functional barrier (T1kk Isolation 1500 Vrms).
    d.barrier("RET", "C1", grade="functional", v_work=V_STACK + 38.5, creepage_mm=0.6, clearance_mm=0.6,
              standard=f"{ipc} B2 31-150 V [S]", pollution_degree=2,
              source="DESIGN.md 6.3 B-3: T1kk primary (cell k) to secondary (FLYBUS/TAP0), <= 106 V peak; "
                     "the footprint gives about 10 mm between pad rows")
    d.barrier("CTRL", "C1", grade="functional", v_work=V_STACK, creepage_mm=0.6, clearance_mm=0.6,
              standard=f"{ipc} B2 31-150 V [S]", pollution_degree=2, source="DESIGN.md 6.3 B-2")
    d.barrier("BAT0", "RET", grade="functional", v_work=V_FLY, creepage_mm=0.6, clearance_mm=0.6,
              standard=f"{ipc} B2 31-150 V [S]", pollution_degree=2,
              source="FLYBUS/SEC_k/BUCK_SW (<= 68 V) vs TAP0, GND_B and the logic")
    # B-6: user port vs fault contact
    d.barrier("USER", "FAULT", grade="functional", v_work=36, creepage_mm=0.5, clearance_mm=0.5,
              standard=f"{ipc} B2 31-50 V: 0.6 mm [S]", pollution_degree=2,
              source="DESIGN.md 6.3 B-6: <= 30 V + 5.5 V; separate connectors J2 and J4")
    # B-5: battery side vs chassis screws (basic)
    d.barrier("BAT0", "CHASSIS", grade="basic", v_work=354, creepage_mm=3.0, clearance_mm=3.0,
              standard="IEC 60664-1 Tables F.2/F.4, IEC 62368-1 [S]", pollution_degree=2, material_group="IIIa",
              ovc="II", v_test_rms=1500,
              source="DESIGN.md 6.3 B-5: 250 Vrms worst case (ASM-5): 2.5 mm creepage, 1.5 mm clearance at "
                     "2.5 kV; 3.0 mm copper-free ring around each M4 screw (TI SLUP419 tables [S])")
    # B-4: battery side vs the user port (reinforced)
    sl = "IEC 60664-1 F.4 (250 V, PD2, MG III: 2.5 mm basic -> 5.0 reinforced) and F.2 / IEC 62368-1 Table 10 " \
         "(3.8 mm at 4 kV) via TI SLUP419 [S]"
    d.barrier("BAT0", "USER", grade="reinforced", v_work=354, creepage_mm=8.0, clearance_mm=8.0,
              standard="IEC 62368-1, IEC 60664-1", v_test_rms=3000, pollution_degree=2, material_group="IIIa",
              ovc="II", slot=False,
              source=f"{sl}. Required 5.0 / 3.8 mm; design 8.0 / 8.0 mm (ISO7721DWV 8.5 mm package, pad gap 8.85 mm)")
    d.barrier("BAT0", "FAULT", grade="reinforced", v_work=354, creepage_mm=5.0, clearance_mm=3.8,
              standard="IEC 62368-1, IEC 60664-1", v_test_rms=3000, pollution_degree=2, material_group="IIIa",
              ovc="II", slot=False,
              source=f"{sl}. The AQY210EH SMDIP-4 pads leave 5.6 mm, so the fault-contact barrier is held at "
                     "the required 5.0 / 3.8 mm, not the 8 mm used for the UART")


# =================================================================================================
# Blocks

def tap_blocks(d, n):
    """J1 + net tie, then one block per tap t: board fuse F1tt, filter R3tt, differential cap C7tt."""
    b = d.block("tapin", title="Harness header J1 and the TAP0/GND_B net tie", domain="BAT0",
                description="J1 pin t+1 = TAPt_IN (t = 0..16); NT1 joins TAP0 and GND_B on pad F100.2")
    j1 = b.add(P.J_TAPS, ref="J1")
    nt1 = b.add(P.NETTIE, ref="NT1")
    for t in TAPS:
        n[f"TAP{t}_IN"].connect(j1[t + 1])
    n["TAP0"].connect(nt1[1])
    n["GND_B"].connect(nt1[2])
    parts = {"J1": j1, "NT1": nt1}
    for t in TAPS:
        tb = d.block(f"tap{t}", title=f"Tap {t}: board fuse, ADBMS1818 C{t} filter",
                     domain="BAT0" if t == 0 else f"C{t}",
                     description=f"F1{kk(t)} 5 A (replaceable), R3{kk(t)} 100 ohm Kelvin at F1{kk(t)}.2, "
                                 f"C7{kk(t)} 10 nF differential to tap {t - 1 if t else 'GND_B'}")
        f = tb.add(P.F_TAP, ref=f"F1{kk(t)}", p_diss=I_TAP ** 2 * 0.0125)
        r = tb.add(P.R_100, ref=f"R3{kk(t)}")
        c = tb.add(P.C_10N, ref=f"C7{kk(t)}")
        n[f"TAP{t}_IN"].connect(f[1])
        n[f"TAP{t}"].connect(f[2], r[1])
        n[f"CS_{t}"].connect(r[2], c[1])
        (n["GND_B"] if t == 0 else n[f"CS_{t - 1}"]).connect(c[2])
        parts[f"F{t}"], parts[f"R{t}"], parts[f"C{t}"] = f, r, c
    return parts


def channel_block(d, n, k):
    """Channel k: LT8584 flyback from cell k (TAP(k-1)..TAPk) into FLYBUS, with its opto enable."""
    x = kk(k)
    b = d.block(f"ch{k}", title=f"Channel {k}: LT8584 balancer for cell {k}", domain=f"C{k}",
                description=f"U1{x} LT8584 simple mode, T1{x} 1:4, out via D1{x} to FLYBUS; DIN = S_{k} "
                            f"(ADBMS1818), DCHRG = opto U2{x} (BAL_EN string)")
    top, ref = n[f"TAP{k}"], n[f"TAP{k - 1}"]
    u = b.add(P.LT8584, ref=f"U1{x}")
    # i_through: the transformer's only current rating is the 7 A primary peak; the LT8584 limits the
    # peak to 6.0-6.8 A (C-5). Nets carry average/rms values that do not apply to it.
    t = b.add(P.NA5743, ref=f"T1{x}", i_through=6.8)
    d1 = b.add(P.ES1G, ref=f"D1{x}", i_through=0.2)   # output diode: average secondary current (C-8)
    d2 = b.add(P.ES1G, ref=f"D2{x}", i_through=0.05)  # snubber diode: 0.23 W / 4.99 k clamp, avg (C-6)
    d3 = b.add(P.TVS_CELL, ref=f"D3{x}")
    c1 = b.add(P.C_100U, ref=f"C1{x}")
    c2 = b.add(P.C_100U, ref=f"C2{x}")
    c3 = b.add(P.C_1U, ref=f"C3{x}")
    c4 = b.add(P.C_47N, ref=f"C4{x}")
    c5 = b.add(P.C_22N_100V, ref=f"C5{x}")
    c6 = b.add(P.C_2U2_100V, ref=f"C6{x}")
    r1 = b.add(P.R_4K99_2010, ref=f"R1{x}", p_diss=0.23)   # RCD clamp loss (C-6)
    r2 = b.add(P.R_33K, ref=f"R2{x}")
    r4 = b.add(P.R_10K, ref=f"R4{x}")
    opto = b.add(P.TLP293, ref=f"U2{x}")
    sw = b.net(f"SW_{k}", v=V_SW, kind="switching", i_max=3.2, i_peak=6.8,
               notes="primary switch node: 21.4 V flat top, 38.5 V clamped spike (C-5)")
    snb = b.net(f"SNB_{k}", v=(0, 38.5), kind="switching", i_max=0.05, i_peak=6.8,
                notes="RCD clamp node, TAPk + 15..34 V")
    out = b.net(f"OUT_{k}", v=V_CELL, kind="analog", notes="LT8584 OUT, needs 47 nF")
    dch = b.net(f"DCH_{k}", v=V_CELL, kind="signal", notes="DCHRG: high (opto on) = enable")
    mode = b.net(f"MODE_{k}", domain="STACK" if k == N else f"SNS{k}", v=(-0.01, 0.0), kind="signal",
                 notes="MODE tied to VIN through R4 so a pin 4/5/6 solder bridge cannot short the cell")
    sec = b.net(f"SEC_{k}", domain="RET", v=(-18, V_FLY + 1), kind="switching", i_max=0.4, i_peak=1.7,
                notes="secondary: -4 x VIN while on, FLYBUS + 1 V while delivering")
    ref.connect(u["GND"], u["RTMR"], d3["A"], c1[2], c2[2], c3[2], c4[2], r2[2])
    top.connect(u["VIN"], u["VCELL"], u["VSNS"], t["PRI_A"], t["PRI_B"], d3["K"], c1[1], c2[1], c3[1], c5[2],
                r1[2], r4[1], opto["C"])
    mode.connect(u["MODE"], r4[2])
    n[f"S_{k}"].connect(u["DIN"])
    out.connect(u["OUT"], c4[1])
    dch.connect(u["DCHRG"], r2[1], opto["E"])
    sw.connect(u["SW"], t["PRI_A_END"], t["PRI_B_END"], d2["A"])
    snb.connect(d2["K"], c5[1], r1[1])
    sec.connect(t["SEC_END"], d1["A"])
    n["FLYBUS"].connect(d1["K"], c6[1])
    n["TAP0"].connect(t["SEC_DOT"], c6[2])
    n[f"LEDA_{k}"].connect(opto["A"])
    (n["STR_Q"] if k == 1 else n[f"LEDA_{k - 1}"]).connect(opto["K"])
    t.nc_pins("NC6", "NC7", reason="no winding (Coilcraft Doc 1075 schematic shows windings 1-3, 2-4, 5-8 "
                                   "only); pads soldered, no copper to other nets")
    return dict(blk=b, u=u, t=t, d1=d1, d2=d2, d3=d3, c1=c1, c2=c2, c3=c3, c4=c4, c5=c5, c6=c6, r1=r1, r2=r2,
                r4=r4, opto=opto, sw=sw, sec=sec)


def ret_block(d, n):
    b = d.block("ret", title="Stack return: D1 blocking diode, D2 clamp, FLYBUS sense", domain="RET",
                description="FLYBUS -> D1 (V8P10) -> TAP16. Two diodes (D1kk, D1) in series on every return "
                            "path; D2 clamps FLYBUS if the return opens; R19/R20 feed PA0")
    d1 = b.add(P.V8P10, ref="D1", i_through=I_FLY)   # 0.7 W: see calc d1_tj_C
    d2 = b.add(P.SMBJ70A, ref="D2")
    r19 = b.add(P.R_2M_1206, ref="R19")
    r20 = b.add(P.R_100K, ref="R20")
    c19 = b.add(P.C_10N, ref="C19")
    tp1 = b.add(P.TP, ref="TP1")
    n["FLYBUS"].connect(d1["A"], d2["K"], r19[1], tp1[1])
    n["TAP16"].connect(d1["K"])
    n["TAP0"].connect(d2["A"])
    n["FLY_SNS"].connect(r19[2], r20[1], c19[1])
    n["GND_B"].connect(r20[2], c19[2])
    return dict(blk=b, d1=d1, d2=d2, r19=r19)


def afe_block(d, n):
    b = d.block("afe", title="ADBMS1818 cell monitor and temperature sensing", domain="CTRL",
                description="SPI mode (ISOMD = V-), DTEN = V- (2 s watchdog clears DCC), VREG from the 5 V buck, "
                            "C17/C18 tied to C16 (16 cells), TH1-TH3 on GPIO1-3")
    u = b.add(P.ADBMS1818, ref="U1")
    r1 = b.add(P.R_100_0805, ref="R1")
    c1 = b.add(P.C_100N_100V, ref="C1")
    c2 = b.add(P.C_1U_16V, ref="C2")
    c3 = b.add(P.C_1U, ref="C3")
    c4 = b.add(P.C_1U, ref="C4")
    r2 = b.add(P.R_20K, ref="R2")
    # IPB-IMB termination: port B drive = 20 x IB = 20 x 2.0 V / 20 k = 2 mA (max 2.45 mA, LTC6813-1 p.7),
    # 0.25 V across 100 ohm, pulsed: 0.6 mW worst case.
    r3 = b.add(P.R_100, ref="R3", p_diss=0.0006)
    r4 = b.add(P.R_4K99, ref="R4")
    r5 = b.add(P.R_1M, ref="R5")
    rn = [b.add(P.R_10K_01, ref=f"R{6 + i}") for i in range(3)]
    th = [b.add(P.NTC_10K, ref=f"TH{1 + i}") for i in range(3)]
    cn = [b.add(P.C_100N, ref=f"C{5 + i}") for i in range(3)]
    vplus = b.net("VPLUS", domain="STACK", v=(-0.3, 0), kind="power", i_max=0.0014,
                  notes="V+ through R1 100 ohm: 1.35 mA x 100 = 0.14 V")
    vref1 = b.net("VREF1", v=(0, 3.3), kind="analog")
    vref2 = b.net("VREF2", v=(0, 3.1), kind="analog", notes="3.000 V, NTC bias")
    ibias = b.net("IBIAS", v=(0, 2.1), kind="analog")
    ipb = b.net("IPB", v=(0, 5.15), kind="signal", notes="isoSPI port B, terminated, no device above")
    imb = b.net("IMB", v=(0, 5.15), kind="signal")
    ntc = [b.net(f"NTC{1 + i}", v=(0, 3.1), kind="sense") for i in range(3)]
    n["STK_F"].connect(r1[1])
    vplus.connect(r1[2], c1[1], u["V+"])
    for t in range(0, N + 1):
        n[f"CS_{t}"].connect(u[f"C{t}"])
    n["CS_16"].connect(u["C17"], u["C18"])
    for k in CH:
        n[f"S_{k}"].connect(u[f"S{k}"])
    u.nc_pins("S17", "S18", reason="unused balance outputs are left open (LTC6813-1 Rev B p.85 / ADBMS1818 "
                                   "'using fewer than 18 cells')")
    for i in range(3):
        ntc[i].connect(u[f"GPIO{1 + i}"], rn[i][2], th[i][1], cn[i][1])
        vref2.connect(rn[i][1])
        n["GND_B"].connect(th[i][2], cn[i][2])
    n["GND_B"].connect(*[u[f"GPIO{g}"] for g in range(4, 10)])   # unused GPIOs held low [I]
    n["5V_SYS"].connect(u["VREG"], c2[1])
    u.nc_pins("DRIVE", reason="VREG is supplied by the buck, no NPN pass transistor: DRIVE output left open "
                              "(ADBMS1818 Rev A p.68 'Providing DC Power') [I]")
    vref2.connect(u["VREF2"], c4[1])
    vref1.connect(u["VREF1"], c3[1])
    n["GND_B"].connect(u["DTEN"], u["ISOMD"], u["V-"], c1[2], c2[2], c3[2], c4[2], r2[2])
    n["SPI_MOSI"].connect(u["SDI"])
    n["SPI_MISO"].connect(u["SDO"], r4[1])
    n["ADBMS_WDT"].connect(u["WDT"], r5[1])
    n["+3V3"].connect(r4[2], r5[2])
    ibias.connect(u["IBIAS"], u["ICMP"], r2[1])
    n["SPI_CS"].connect(u["CSB"])
    n["SPI_SCK"].connect(u["SCK"])
    ipb.connect(u["IPB"], r3[1])
    imb.connect(u["IMB"], r3[2])
    return dict(blk=b, u=u, c1=c1, c2=c2, c3=c3, c4=c4, th=th)


def psu_block(d, n):
    b = d.block("psu", title="Stack-fed supply: F1, LM5164 5 V buck, MCP1700 3.3 V", domain="CTRL",
                description="TAP16 -> F1 125 mA -> D3 -> R9 100 ohm -> LM5164 (250 kHz, UVLO 25 V) -> 5V_SYS -> "
                            "MCP1700 -> +3V3. All controller loads hang on the whole stack (H-12)")
    f1 = b.add(P.F_SUPPLY, ref="F1", i_through=0.012)   # 10 mA load; TAP16's 2.6 A does not flow in it
    d3 = b.add(P.ES1G, ref="D3")
    r9 = b.add(P.R_100_2512, ref="R9")
    u3 = b.add(P.LM5164, ref="U3")
    c8 = b.add(P.C_2U2_100V, ref="C8")
    c9 = b.add(P.C_100N_100V, ref="C9")
    r10 = b.add(P.R_4M7_1206, ref="R10")
    r11 = b.add(P.R_300K, ref="R11")
    r12 = b.add(P.R_49K9, ref="R12")
    c10 = b.add(P.C_2N2, ref="C10")
    l1 = b.add(P.L_47U, ref="L1")
    c11 = b.add(P.C_22U, ref="C11")
    r13 = b.add(P.R_316K, ref="R13")
    r14 = b.add(P.R_100K, ref="R14")
    r15 = b.add(P.R_470K_1206, ref="R15")
    c12 = b.add(P.C_1N_C0G, ref="C12")
    c13 = b.add(P.C_220P_C0G, ref="C13")
    r16 = b.add(P.R_100K, ref="R16")
    u4 = b.add(P.MCP1700, ref="U4", p_diss=0.043)
    c14 = b.add(P.C_1U_16V, ref="C14")
    c15 = b.add(P.C_1U, ref="C15")
    tp6 = b.add(P.TP, ref="TP6")
    pre = b.net("BUCK_PRE", domain="STACK", v=(-1.3, 0), kind="power", i_max=0.012)
    vin = b.net("BUCK_IN", domain="STACK", v=(-2.5, 0), kind="power", i_max=0.012,
                notes="R9 limits inrush and a U3 short to 0.66 A until F1 opens")
    en = b.net("BUCK_EN", v=(0, 4.1), kind="analog", notes="UVLO divider: 0.06 x BUCK_IN, on at 25.0 V")
    ron = b.net("BUCK_RON", v=(0, 5.0), kind="analog", notes="R_RON only; pin voltage internal [I]")
    fb = b.net("BUCK_FB", v=(0, 1.3), kind="analog", notes="1.2 V reference")
    ramp = b.net("BUCK_RAMP", v=(0, 5.2), kind="analog", notes="Type-3 ripple injection, 5 V +/- 40 mV")
    sw = b.net("BUCK_SW", domain="RET", v=(-0.7, V_STACK), kind="switching", i_max=0.3, i_peak=0.26,
               notes="250 kHz switch node, swings GND_B .. BUCK_IN")
    d.domain("BOOT", ref="psu/BUCK_SW", kind="battery", description="LM5164 bootstrap, rides on BUCK_SW")
    bst = b.net("BUCK_BST", domain="BOOT", v=(0, 5.0), kind="switching",
                notes="charged from the internal 5 V VCC through the internal boot diode")
    n["TAP16"].connect(f1[1])
    n["STK_F"].connect(f1[2], d3["A"], tp6[1])
    pre.connect(d3["K"], r9[1])
    vin.connect(r9[2], u3["VIN"], c8[1], c9[1], r10[1])
    en.connect(u3["EN/UVLO"], r10[2], r11[1])
    ron.connect(u3["RON"], r12[1])
    fb.connect(u3["FB"], r13[2], r14[1], c13[2])
    n["PGOOD"].connect(u3["PGOOD"], r16[1])
    bst.connect(u3["BST"], c10[1])
    sw.connect(u3["SW"], c10[2], l1[1], r15[1])
    ramp.connect(r15[2], c12[1], c13[1])
    n["5V_SYS"].connect(l1[2], c11[1], r13[1], c12[2], u4["VI"], c14[1])
    n["+3V3"].connect(u4["VO"], c15[1], r16[2])
    n["GND_B"].connect(u3["GND"], u3["EP"], c8[2], c9[2], r11[2], r12[2], c11[2], r14[2], u4["GND"], c14[2],
                       c15[2])
    return dict(blk=b, f1=f1, u3=u3, c8=c8, c10=c10, l1=l1, c11=c11, r12=r12, r13=r13, u4=u4)


def mcu_block(d, n):
    b = d.block("mcu", title="STM32G031 controller, SWD pads, status LEDs", domain="CTRL",
                description="SPI1 to U1, USART2 to the isolator, PA0 = FLY_SNS (ADC + analog watchdog), PA1 = "
                            "BAL_EN, PB0 powers U5 side 1, PB1 drives the fault PhotoMOS")
    u = b.add(P.STM32G031, ref="U2")
    c16 = b.add(P.C_100N, ref="C16")
    c17 = b.add(P.C_4U7, ref="C17")
    c18 = b.add(P.C_100N, ref="C18")
    r17 = b.add(P.R_1K, ref="R17")
    r18 = b.add(P.R_1K, ref="R18")
    d5 = b.add(P.LED_GREEN, ref="D5", i_through=0.0013)   # (3.3 - 2.0) V / 1 k
    d6 = b.add(P.LED_RED, ref="D6", i_through=0.0015)
    j3 = b.add(P.TAGCONNECT, ref="J3")
    tps = {i: b.add(P.TP, ref=f"TP{i}") for i in (2, 3, 4)}
    nrst = b.net("NRST", v=(0, 3.37))
    swdio = b.net("SWDIO", v=(0, 3.37))
    swclk = b.net("SWCLK", v=(0, 3.37), kind="clock")
    ledg, ledga = b.net("LEDG", v=(0, 3.37)), b.net("LEDG_A", v=(0, 3.37))
    ledr, ledra = b.net("LEDR", v=(0, 3.37)), b.net("LEDR_A", v=(0, 3.37))
    ledr.connect(u["PB9"], r18[1])
    n["+3V3"].connect(u["VDD"], c16[1], c17[1], j3["VCC"], tps[3][1])
    n["GND_B"].connect(u["VSS"], c16[2], c17[2], c18[2], d5["K"], d6["K"], j3["GND"], tps[4][1])
    nrst.connect(u["PF2"], c18[1], j3["~{RESET}"])
    n["FLY_SNS"].connect(u["PA0"])
    n["BAL_EN"].connect(u["PA1"])
    n["MCU_TX"].connect(u["PA2"])
    n["MCU_RX"].connect(u["PA3"])
    n["SPI_CS"].connect(u["PA4"])
    n["SPI_SCK"].connect(u["PA5"])
    n["SPI_MISO"].connect(u["PA6"])
    n["SPI_MOSI"].connect(u["PA7"])
    n["ISO_VCC1"].connect(u["PB0"])
    n["FLT_DRV"].connect(u["PB1"])
    n["ADBMS_WDT"].connect(u["PB2"])
    n["PGOOD"].connect(u["PA8"])
    swdio.connect(u["PA13"], j3["SWDIO"])
    swclk.connect(u["PA14"], j3["SWCLK"])
    ledg.connect(u["PB8"], r17[1])
    ledga.connect(r17[2], d5["A"])
    ledra.connect(r18[2], d6["A"])
    n["5V_SYS"].connect(tps[2][1])
    u.nc_pins("2", "3", "20", "22", "23", "26", "27", "28", "29", "30", "31",
              reason="unused GPIO: left open and set to analog mode by firmware (ST AN4899 practice) [I]")
    j3.nc_pins("SWO", reason="SWO trace not used by the STM32G0 (Cortex-M0+ has no SWO)")
    return dict(blk=b, u=u, c16=c16, c18=c18, j3=j3)


def en_block(d, n):
    b = d.block("en", title="Global balance enable: Q1 current sink and the 16-LED opto string", domain="CTRL",
                description="STK_F -> D4 -> R24 -> LEDA_16 -> U216 ... U201 -> STR_Q -> Q1 -> R23 -> GND_B. "
                            "BAL_EN high sinks 1.5 mA: every opto pulls its DCHRG high (second enable)")
    q1 = b.add(P.MMBT5551, ref="Q1", p_diss=0.045)          # 1.5 mA x 30 V (C-14)
    d4 = b.add(P.ES1G, ref="D4")
    r21 = b.add(P.R_10K, ref="R21")
    r22 = b.add(P.R_100K, ref="R22")
    r23 = b.add(P.R_1K6_0805, ref="R23")
    r24 = b.add(P.R_4K7_2010, ref="R24", p_diss=0.18)      # Q1 C-E short: 6.2 mA (C-14)
    tp5 = b.add(P.TP, ref="TP5")
    qb = b.net("Q1_B", v=(0, 0.8))
    qe = b.net("Q1_E", v=(0, 2.6))
    strd = b.net("STR_D", domain="STACK", v=(-1.3, 0), kind="signal", notes="string top, STK_F - D4")
    n["BAL_EN"].connect(r21[1])
    qb.connect(r21[2], r22[1], q1["B"])
    qe.connect(q1["E"], r23[1])
    n["STR_Q"].connect(q1["C"], tp5[1])
    n["GND_B"].connect(r22[2], r23[2])
    n["STK_F"].connect(d4["A"])
    strd.connect(d4["K"], r24[1])
    n["LEDA_16"].connect(r24[2])
    return dict(blk=b, q1=q1, r24=r24)


def iso_block(d, n):
    b = d.block("iso", title="Isolated UART port and fault contact (reinforced barrier)", domain="USER",
                description="U5 ISO7721DWV (reinforced) to J2; U6 AQY210EH PhotoMOS to J4; U7 ESD array on the "
                            "UART pins, D7 TVS across the contact")
    u5 = b.add(P.ISO7721, ref="U5")
    u6 = b.add(P.AQY210EH, ref="U6")
    u7 = b.add(P.TPD4E05U06, ref="U7")
    d7 = b.add(P.SMBJ40CA, ref="D7")
    c20 = b.add(P.C_100N, ref="C20")
    c21 = b.add(P.C_100N, ref="C21")
    r25 = b.add(P.R_1K, ref="R25")
    r26 = b.add(P.R_1K, ref="R26")
    r27 = b.add(P.R_100K, ref="R27")
    r28 = b.add(P.R_390, ref="R28")
    j2 = b.add(P.J_USER, ref="J2")
    j4 = b.add(P.J_FAULT, ref="J4")
    vio = b.net("VIO_ISO", v=(0, 5.5), kind="power", i_max=0.005, external=True, threats=("esd",),
                notes="host logic supply 2.25-5.5 V, feeds U5 side 2 only")
    outb = b.net("ISO_OUTB", v=(0, 5.5))
    txd = b.net("TXD_ISO", v=(0, 5.5), external=True, threats=("esd",), notes="board -> host")
    rxd = b.net("RXD_ISO", v=(0, 5.5), external=True, threats=("esd",), notes="host -> board")
    ina = b.net("ISO_INA", v=(0, 5.5))
    fled = b.net("FLT_LED", domain="CTRL", v=(0, 1.5), notes="LED forward-clamped: VF <= 1.5 V at 5.3 mA")
    flta = b.net("FLT_A", domain="FAULT", v=(-30, 30), i_max=0.05, external=True, threats=("esd",),
                 notes="fault contact terminal A (J4.1): user circuit <= 30 V either polarity")
    n["ISO_VCC1"].connect(u5["VCC1"], c20[1])
    n["MCU_RX"].connect(u5["OUTA"])
    n["MCU_TX"].connect(u5["INB"])
    n["GND_B"].connect(u5["GND1"], c20[2], u6["LED_K"])
    n["GND_ISO"].connect(u5["GND2"], c21[2], u7["GND"], j2[1])
    outb.connect(u5["OUTB"], r25[1])
    ina.connect(u5["INA"], r26[2], r27[1])
    vio.connect(u5["VCC2"], c21[1], r27[2], u7["D1+"], j2[2])
    txd.connect(r25[2], u7["D1-"], j2[3])
    rxd.connect(r26[1], u7["D2+"], j2[4])
    u7.nc_pins("D2-", reason="spare ESD channel, left open (TI SLVSBO7O Table 4-2 allows floating)")
    u7.nc_pins("6", "7", "9", "10", reason="NC, flow-through routing only; may float (SLVSBO7O Table 4-2)")
    n["FLT_DRV"].connect(r28[1])
    fled.connect(r28[2], u6["LED_A"])
    flta.connect(u6["OUT1"], d7["A1"], j4[1])
    n["FLT_B"].connect(u6["OUT2"], d7["A2"], j4[2])
    return dict(blk=b, u5=u5, u6=u6, u7=u7, d7=d7, j2=j2, j4=j4)


def harness_block(d, n):
    """Off-board harness: ring terminal + inline fuse per tap; plug HP1 mates J1 (TAPt_IN on both)."""
    b = d.block("harness", title="Tap harness (off-board): rings, inline 7 A fuses, plug", board="off",
                description="17 x (PV18-14R ring, 50 mm 18 AWG, 0324007.HXP fuse sealed in heat-shrink, UL 1015 "
                            "18 AWG <= 1 m) into plug HP1 MSTB 2,5/17-ST-5,08; EBP 2-5 bridges for N < 16")
    hp1 = b.add(P.PLUG_TAPS, ref="HP1")
    parts = {"HP1": hp1}
    for t in TAPS:
        dom = "BAT0" if t == 0 else f"C{t}"
        term = b.net(f"CELLTERM{t}", domain=dom, v=0 if t == 0 else V_CELL, kind="power", i_max=I_TAP,
                     external=True, threats=("overcurrent",),
                     notes="B- cell terminal" if t == 0 else f"cell {t} + terminal")
        ht = b.add(P.RING, ref=f"HT{t}")
        hf = b.add(P.F_INLINE, ref=f"HF{t}")
        term.connect(ht[1], hf[1])
        n[f"TAP{t}_IN"].connect(hf[2], hp1[t + 1])
        parts[f"HT{t}"], parts[f"HF{t}"] = ht, hf
    return parts


def mech_block(d):
    b = d.block("mech", title="Mounting holes", domain="BAT0",
                description="H1-H6 M4 non-plated, nylon standoffs; 3.0 mm copper-free ring (B-5)")
    return [b.add(P.HOLE_M4, ref=f"H{i}") for i in range(1, 7)]


# =================================================================================================
# Hazards (DESIGN.md section 4)

def hazards(d):
    F = [f"F1{kk(t)}" for t in TAPS]
    HF = [f"HF{t}" for t in TAPS]
    H = d.hazard
    H("H-1", "Fire or burns at the board: a part shorts one cell (LT8584 switch, cracked 1210 MLCC, TVS); "
      "about 34 A limited by the harness",
      "board fuse F1tt clears in about 5 ms (calc t_clear_1cell_ms), inline 7 A fuse is the backup; 1210 "
      "MLCCs >= 5 mm from edges and holes; LT8584 MODE (pin 5, between GND pins 4 and 6) tied to VIN through "
      "R4kk 10 k so a solder bridge draws 0.4 mA; 100 % AOI",
      parts=F + HF + [f"R4{kk(k)}" for k in CH], single_fault_safe=True)
    H("H-2", "Multi-cell short ('voltage jump'), kA: a part spanning non-adjacent taps fails short",
      "by construction: every return path has D1kk and D1 in series (D1kk short -> D1 blocks; D1 short -> each "
      "D1kk blocks; C6kk or D2 short -> D1 blocks); supplies through F1 125 mA + R9 100 ohm; LED string through "
      "R24 and a current sink; sense divider 2 M; an ADBMS1818 pin-to-pin short passes <= 0.3 A through two "
      "100 ohm filters (fusible)",
      parts=[f"D1{kk(k)}" for k in CH] + ["D1", "F1", "R9", "R1", "R24", "Q1", "R19"] + [f"R3{kk(t)}" for t in TAPS],
      single_fault_safe=True,
      notes="Residual: T1kk interwinding insulation (1500 Vrms [P], 22x the working voltage) joins TAPk to TAP0 "
            "if it breaks down; treated as a safeguard (incoming hipot T-XFMR), cleared by the 10 kA inline "
            "fuses (calc i_fault_stack_A). Double fault D1 + D1kk: cleared by F116/F100 and the inline fuses")
    H("H-3", "Harness short near the battery: up to 2.5 kA, arc", "3AB 7 A fuse at the ring (10 kA at 125 VDC); "
      "UL 1015 wire; bundled in tap order; strain relief", parts=HF + [f"HT{t}" for t in TAPS],
      single_fault_safe=True)
    H("H-4", "Over-discharge by a stuck balancer: the BMS cannot disconnect this load; copper dissolution -> "
      "internal short -> runaway on recharge",
      "two independent enables (S_k -> DIN and BAL_EN -> opto -> DCHRG); ADBMS1818 watchdog clears DCC in "
      "<= 2.2 s (REQ-F1); firmware floor (REQ-F8); LT8584 UVLO 2.1-2.45 V; both paths proof-tested each "
      "session (REQ-F6); fault contact",
      parts=["U1", "U2", "Q1", "R21", "R22"] + [f"U2{kk(k)}" for k in CH] + [f"R2{kk(k)}" for k in CH],
      single_fault_safe=True, notes="Residual: an LT8584 internal logic fault that ignores both enables")
    H("H-5", "Overcharge of a full cell by the returned energy (0.12-0.2 A per active channel into every cell)",
      "firmware active-set rule REQ-F2: net current of a full cell -2.5 + n x 0.15 A < 0 for n <= 8",
      parts=["U1", "U2"], single_fault_safe=False, notes="firmware-only barrier; reviewed and tested (F-9)")
    H("H-6", "Wrong decisions from IR drop on the single-wire taps", "MUTE/DCP = 0 during conversions, sum-of-"
      "cells plausibility (REQ-F4)", parts=["U1", "U2"], single_fault_safe=True)
    H("H-7", "Hot-plug overvoltage from random mating order", "TVS D3kk per cell; 100 ohm / 10 nF C-pin filters "
      "and the ADBMS1818 internal clamps; 2 x 100 uF per cell damps the overshoot (calc hotplug_*)",
      parts=[f"D3{kk(k)}" for k in CH] + [f"R3{kk(t)}" for t in TAPS] + [f"C7{kk(t)}" for t in TAPS],
      single_fault_safe=True)
    H("H-8", "Swapped, reversed or offset taps (installer error)", "pre-plug DMM check; TVS crowbars open the "
      "board fuses; replaceable OMNI-BLOK fuses; boot lockout (REQ-F7)",
      parts=[f"D3{kk(k)}" for k in CH] + F, single_fault_safe=True, notes="no fire; the board may need repair")
    H("H-9", "Open tap (including TAP0 or TAP16)", "pulse test before each session (REQ-F6); FLY_SNS analog "
      "watchdog stops balancing in <= 1 ms (REQ-F5); D2 clamps FLYBUS; D316 clamps an open TAP16 node to "
      "TAP15 + 7.1 V; the BAL_EN string spans TAP16..TAP0, so losing either end disables every channel",
      parts=["D2", "R19", "R20", "C19", "D316", "U2"], single_fault_safe=True)
    H("H-10", "Shock through the user port with the battery at mains potential (ASM-5)",
      "ISO7721DWV and AQY210EH, both reinforced 5 kVrms; 8 mm (UART) / 5 mm (contact) board barrier; separate "
      "connectors", parts=["U5", "U6", "J2", "J4"], single_fault_safe=True)
    H("H-11", "Overtemperature (8 x 1.5 W)", "TH1-TH3; derating REQ-F3; NTCs at U103, U106, U112",
      parts=["TH1", "TH2", "TH3"], single_fault_safe=True)
    H("H-12", "The balancer itself causes imbalance through unequal standing loads",
      "all controller loads hang on the whole stack (F1 from TAP16); per-cell loads <= 30 uA (calc iq_cell_*)",
      parts=["F1", "U3"], single_fault_safe=False, notes="not a fault scenario; design property")
    H("H-13", "Drains a pack the BMS has shut off (the board is upstream of the BMS switch)",
      "<= 50 uA sleep; buck UVLO 25 V; deep sleep below 2.8 V/cell (REQ-F8)", parts=["U3", "R10", "R11"],
      single_fault_safe=True)
    H("H-14", "TAP0 landed on P- instead of B-", "label and procedure; with a low-side-FET BMS open, cell 1 "
      "reads out of range and the board locks out (REQ-F7); CH1 TVS and fuse limit damage",
      parts=["D301", "F100", "F101"], single_fault_safe=False, notes="partly procedural")


# =================================================================================================
# Calculations (DESIGN.md section 7)

def calcs(d):
    c = d.calc
    # C-1 / C-3 pack and envelope
    c("pack_energy_kWh", 16 * 3.2 * 200 / 1000, "kWh", expr="16 x 3.2 V x 200 Ah")
    c("stack_max_hw_V", V_STACK, "V", expr="16 x 4.2 V (16S NMC)", limit=80,
      note="NA5743-AL output range 30-80 V (Doc 1075)")
    c("stack_min_V", 13 * 2.5, "V", expr="13 x 2.5 V (13S LFP empty)", limit=30, op=">=",
      note="NA5743-AL output minimum 30 V")
    c("adbms_vplus_to_c12_V", 4 * 4.2, "V", expr="4 cells x 4.2 V", limit=40, note="V+ - C12 operating max")
    # C-2 balancing current
    vin, ipk, lp, ls = 3.15, 6.3, 4e-6, 64e-6
    t_on = lp * ipk / vin
    t_off = ls * (ipk / 4) / (55.5 + 1 + 4 * 0)
    f = 1 / (t_on + t_off + 0.5e-6)
    i_in = 0.5 * ipk * t_on * f
    c("lt8584_f_kHz", round(f / 1e3, 1), "kHz", expr="1 / (t_on 8.0 us + t_off 1.71 us + 0.5 us delay)")
    c("i_in_avg_A", round(i_in, 2), "A", expr="0.5 x Ipk 6.3 A x t_on x f at VIN 3.15 V", limit=2.0, op=">=",
      note="REQ-4; matches LT8584 Fig. G32 (2.4-2.6 A)")
    c("i_pri_rms_A", round(ipk * math.sqrt(t_on * f / 3), 2), "A", expr="6.3 x sqrt(D / 3)")
    c("balance_capacity_pct_day", 2 * 2.5 / 200 * 100, "%/day", expr="2 h top window x 2.5 A / 200 Ah",
      limit=0.25, op=">=", note="vs ASM-7 worst drift 0.25 %/day")
    # C-5 LT8584 and transformer stresses
    c("xfmr_ipk_ratio", round(6.8 / 7.0, 3), "", expr="LT8584 Ipk max 6.8 A / NA5743 Ipk 7.0 A", limit=1.0,
      note="ADI's own pairing (Table 3); saturation checked in T-EFF")
    flat = 4.2 + (V_FLY + 1) / 4
    c("sw_flat_top_V", round(flat, 1), "V", expr="VIN 4.2 + (FLYBUS 67.7 + 1) / 4", limit=40,
      note="LT8584 Note 3: <= 40 VDC on SW")
    c("sw_spike_V", 38.5, "V", expr="VIN 4.2 + RCD clamp 34 V", limit=50, note="SW abs max incl. spike")
    c("lt8584_vin_max_V", 4.2, "V", limit=5.3, note="recommended VIN max")
    # C-6 snubber
    p_snb = 0.5 * 0.116e-6 * 6.3 ** 2 * f
    c("snubber_power_W", round(p_snb, 3), "W", expr="0.5 x Llk 0.116 uH x 6.3^2 x f", limit=0.25,
      note="R1kk 0.5 W at 50 %")
    c("snubber_clamp_V", round(math.sqrt(p_snb * 4990), 1), "V", expr="sqrt(P x 4.99 k)",
      limit=round((V_FLY + 1) / 4, 1), op=">=", note="must exceed the reflected voltage")
    # C-7 fuses and fault currents
    r_tap = 0.0226 + 0.0187 + 0.0125 + 0.006
    c("r_tap_ohm", round(r_tap, 4), "ohm", expr="wire 22.6 + 0324007 18.7 + 0451005 12.5 + contacts 6 mOhm")
    i1 = 4.2 / 0.125
    c("i_fault_1cell_A", round(i1, 1), "A", expr="4.2 V / 0.125 ohm (two taps + cell)", limit=300,
      note="Nano2 interrupting rating at 32 VDC")
    c("t_clear_1cell_ms", round(5.566 / i1 ** 2 * 1000, 2), "ms", expr="I2t 5.566 A2s / I^2", limit=10,
      note="REQ-9")
    c("t_clear_2cell_ms", round(5.566 / (2 * i1) ** 2 * 1000, 2), "ms", expr="swap fault, 8.4 V / 0.125", limit=10)
    c("fuse_selectivity_i2t_ratio", round(71 / 5.566, 1), "", expr="0324007 I2t 71 / 0451005 I2t 5.566",
      limit=2, op=">=", note="board fuse clears first")
    c("i_fault_stack_A", round(V_STACK / 0.12, 0), "A", expr="67.2 V / 0.12 ohm (needs two faults)",
      limit=10000, note="inline 3AB interrupting 10 kA at 125 VDC; beyond Nano2's 50 A at 125 V")
    c("tap_fuse_load_ratio", round(I_TAP / (5 * 0.75 * 0.9), 2), "", expr="2.6 A / (5 A x 0.75 x 0.9 at 60 C)",
      limit=1.0)
    c("inline_fuse_load_ratio", round(I_TAP / (7 * 0.75), 2), "", expr="2.6 A / (7 A x 0.75)", limit=1.0)
    c("f1_fault_overload_x", round(V_STACK / 101.7 / 0.125, 1), "x", expr="67.2 V / (R9 100 + F1 1.7 ohm) / 0.125 A",
      limit=3, op=">=", note="a buck or V+ short opens F1 within milliseconds")
    # C-8 efficiency
    p_cell = 2.5 * 3.45
    p_out = (p_cell - 2.5 ** 2 * 0.12) * 0.82
    c("eff_end_to_end", round(p_out / p_cell, 3), "", expr="(8.63 W - harness 0.75 W) x 0.82 / 8.63 W",
      limit=0.72, op=">=", note="REQ-3")
    c("eff_board", 0.82, "", expr="LT8584 Fig. G33 at 50-60 V", limit=0.78, op=">=")
    # C-9 standing currents
    iq = 1 + 4 + 0.25 + 20 + 0.08
    c("iq_cell_worst_uA", round(iq, 2), "uA", expr="LT8584 1 + SW leak 4 + C pin 0.25 + TVS 20 (at 5 V) + opto 0.08",
      limit=30, note="REQ-12")
    c("iq_cell_drift_pct_yr", round(iq * 1e-6 * 8760 / 200 * 100, 3), "%/yr", expr="I x 8760 h / 200 Ah",
      limit=0.15, note="REQ-12")
    iqs = 25 + V_STACK / 5.0 + 9 + 1.4
    c("iq_stack_max_uA", round(iqs, 1), "uA", expr="LM5164 25 + UVLO 67.2 V / 5.0 M + V+ 9 + reflected 1.4",
      limit=50, note="REQ-13")
    # C-10 hot plug (C1kk + C2kk X6S 6.3 V at 4.2 V: about 80 uF total [I])
    zeta = 0.06 * math.sqrt(80e-6 / 2e-6)
    ov = math.exp(-math.pi * zeta / math.sqrt(1 - zeta ** 2))
    c("hotplug_zeta", round(zeta, 2), "", expr="(R 0.12 / 2) x sqrt(C 80 uF / L 2 uH)")
    c("hotplug_peak_V", round(4.2 * (1 + ov), 2), "V", expr="4.2 x (1 + overshoot)", limit=6.3,
      note="C1kk/C2kk 6.3 V rating (LT8584 VIN abs max 9 V)")
    c("open_tap16_vin_V", round(7.07 + (9.1 - 7.07) * 1.6 / 68, 2), "V",
      expr="D316 VBR max 7.07 V + (VC 9.1 - 7.07) x 1.6 A / 68 A", limit=9,
      note="open TAP16 wire while balancing: returned current flows in D316; LT8584 VIN abs max 9 V. C116/C216 "
           "see 1.13 x rating for <= 1 ms (MLCC surge 2.5x)")
    # C-11 timing
    c("adbms_watchdog_max_s", 2.2, "s", expr="DTEN = V-: 1.8-2.2 s (ADBMS1818 Rev A p.7)", limit=2.2,
      note="REQ-16")
    c("wdt_kick_period_s", 0.5, "s", limit=0.9, note="half the minimum watchdog time")
    c("flybus_fault_stop_ms", 1.0, "ms", expr="ADC analog watchdog + BAL_EN drop (REQ-F5)", limit=1.0)
    c("flybus_clamp_V", round(86 + (113 - 86) * I_FLY / 5.3, 1), "V",
      expr="SMBJ70A VBR max 86 V + (VC 113 - 86) x 1.6 A / 5.3 A", limit=100,
      note="C6kk and D1 are 100 V parts")
    c("flybus_clamp_energy_J", round(I_FLY * 94.2 * 1e-3, 3), "J", expr="1.6 A x 94.2 V x 1 ms",
      limit=0.87, note="SMBJ70A 600 W 10/1000 us = about 0.87 J; a 10 ms software loop (1.5 J) would not hold")
    c("open_wire_step_V", round(2.5 * 0.12, 2), "V", expr="2.5 A pulse x R_loop 0.12 ohm (healthy tap)")
    # C-12 thermal
    c("d1_tj_C", round(70 + I_FLY * 0.45 * 60, 1), "C", expr="70 C local + 1.6 A x VF 0.45 V x RthJA 60 C/W (doc 89005)",
      limit=130, note="REQ-21: TJ max 150 C - 20 C; >= 400 mm2 tab copper lowers it")
    c("lt8584_tj_C", round(70 + 0.55 * 38, 1), "C", expr="70 C local + 0.55 W x 38 C/W (650 mm2)", limit=105,
      note="REQ-21")
    c("board_temp_8ch_uncontrolled_C", 45 + 17 + 10, "C", expr="45 C + 12 W / (0.07 m2 x 10 W/m2K) + 10 K enclosure",
      note="why REQ-F3 derates: 8 channels only below 60 C")
    c("ctran_temp_margin_C", 105 - (80 + 5), "C", expr="X6S 105 C - (80 C derating stop + 5 K next to U1kk)",
      limit=20, op=">=", note="REQ-21; the 85 C X5R part gave 0 C")
    c("afe_temp_margin_C", 85 - (60 + 5), "C", expr="ADBMS1818 85 C - (60 C 8-channel limit + 5 K)", limit=20,
      op=">=", note="REQ-21; U1 kept away from the transformers")
    c("iso_temp_margin_C", 85 - (45 + 10 + 5), "C", expr="AQY210EH / STM32 85 C - (45 + 10 enclosure + 5 local)",
      limit=20, op=">=", note="REQ-21; ISO and MCU >= 30 mm from channels 8 and 9")
    # C-13 buck
    c("buck_f_kHz", round(5 * 2500 / 49.9, 0), "kHz", expr="LM5164: f = VOUT x 2500 / RRON(k)")
    c("buck_ton_min_ns", round(5 / (V_STACK * 250e3) * 1e9, 0), "ns", expr="5 V / (67.2 V x 250 kHz)", limit=50,
      op=">=", note="minimum on-time 50 ns")
    di = (V_STACK - 5) * (5 / V_STACK) / (47e-6 * 250e3)
    c("l1_ipk_A", round(0.06 + di / 2, 3), "A", expr="60 mA + ripple/2", limit=1.44, note="L1 Isat 10 %")
    c("buck_vout_V", round(1.2 * (1 + 316 / 100), 3), "V", expr="1.2 x (1 + 316k/100k)")
    c("buck_uvlo_on_V", round(1.5 * 5000 / 300, 1), "V", expr="1.5 V x (4.7 M + 300 k) / 300 k", limit=32.5,
      op="<=", note="must start below the 13S LFP minimum")
    c("vplus_drop_V", round(100 * 1.35e-3, 3), "V", expr="R1 100 ohm x 1.35 mA", limit=0.3,
      note="V+ >= C18 - 0.3 V")
    c("ldo_power_mW", round((5 - 3.3) * 25, 1), "mW", expr="(5 - 3.3) V x 25 mA")
    # C-14 BAL_EN string
    i_str = (3.3 - 0.65 - 0.2) / 1.6
    c("string_current_mA", round(i_str, 2), "mA", expr="(3.3 - VBE 0.65 - 0.2) / 1.6 k")
    comp = 32.5 - 0.9 - 4.7 * i_str - 16 * 1.15 - 0.3 - i_str * 1.6
    c("string_compliance_V", round(comp, 2), "V", expr="32.5 - D4 0.9 - R24 drop - 16 x 1.15 - Q1 0.3 - R23 drop",
      limit=1.0, op=">=", note="at the 13S LFP minimum stack")
    c("opto_drive_margin", round(i_str * 0.3 / (4.2 / 33), 1), "x", expr="1.5 mA x CTR 30 % / (4.2 V / 33 k)",
      limit=1.5, op=">=")
    c("dchrg_off_V", round(5e-6 * 33e3, 3), "V", expr="dark current 5 uA (hot) x 33 k", limit=0.5,
      note="DCHRG threshold 0.5 V min")
    # C-15 FLYBUS
    c("flybus_cap_uF", 16 * 1.0, "uF", expr="16 x C6kk about 1.0 uF at 60 V", limit=1.5, op=">=",
      note="needed 400 x L / V^2 = 1.5 uF at 32.5 V (LT8584 Rev B p.21)")
    c("fly_sns_max_V", round(V_FLY * 100 / 2100 * 1.02, 2), "V", expr="67.7 V x 100k / 2.1M + 2 % tolerance",
      limit=3.3, note="PA0 within VDD")
    # C-16 NTC
    c("ntc_v25_V", 1.5, "V", expr="3.000 V x 10k / (10k + 10k)")


# =================================================================================================
# Placement (DESIGN.md section 9)

def placement(d, n, tp, chs, ret, afe, psu, mcu, en, iso, holes):
    pl = d.place
    pl.side("all", "top", note="single-sided assembly; tallest part T1kk 11.4 mm")
    # floorplan: west = J1 + fuses + filters + U1; south row CH01..CH08 west->east; north row CH16..CH09
    # west->east (U-shape: neighbours one cell apart, CH08/CH09 meet on TAP8 in the east); spine between
    pl.region(tp["J1"], "west")
    for t in TAPS:
        pl.region(d.blocks[[b.name for b in d.blocks].index(f"tap{t}")], "west")
    pl.region(afe["blk"], "west", note="between the fuse column and the channels, away from transformers")
    for k in CH:
        pl.region(chs[k]["blk"], "south" if k <= 8 else "north")
        pl.group(chs[k]["blk"], "close")
    pl.region(ret["blk"], "center", note="west end of the spine, at F116")
    pl.region(en["blk"], "center", note="spine")
    for blk in (psu["blk"], mcu["blk"], iso["blk"]):
        pl.region(blk, "east")
        pl.group(blk, "close")
    pl.group(afe["blk"], "close")
    pl.edge(tp["J1"], "west")
    pl.orient(tp["J1"], "out")
    pl.custom("pin_order", obj=tp["J1"], axis="y", pin1="south",
              note="taps enter in potential order: pin 1 (TAP0) at the south end next to CH01")
    for j in (iso["j2"], iso["j4"]):
        pl.edge(j, "east")
        pl.orient(j, "out")
    pl.far(iso["j2"], tp["J1"], "loose")
    pl.array([tp[f"F{t}"] for t in TAPS], "y", note="fuse column in tap order, one per J1 pin")
    for t in TAPS:
        pl.near(tp[f"F{t}"], tp["J1"][t + 1], "tight")
        pl.custom("kelvin", sense=tp[f"R{t}"][1], at=tp[f"F{t}"][2],
                  note="sense trace leaves pad F1tt.2 on its own, not along the power path")
        pl.near(tp[f"R{t}"], afe["u"][f"C{t}"], "close", note="filters at the IC pins (LTC6813-1 p.73)")
        pl.near(tp[f"C{t}"], afe["u"][f"C{t}"], "close")
    pl.custom("net_tie", part=tp["NT1"], a=n["TAP0"], b=n["GND_B"], at=tp["F0"][2],
              note="the only joint between the battery return and controller ground")
    # channels
    pl.array([chs[k]["blk"] for k in range(1, 9)], "x", note="south row, west to east")
    pl.array([chs[k]["blk"] for k in range(16, 8, -1)], "x", note="north row, west to east")
    pl.symmetric([(chs[k]["blk"], chs[17 - k]["blk"]) for k in range(1, 9)], axis="h",
                 note="mirror about the spine")
    pl.near(chs[1]["blk"], tp["J1"][1], "close")
    pl.near(chs[16]["blk"], tp["J1"][17], "close")
    for k in CH:
        c = chs[k]
        u, t = c["u"], c["t"]
        outer = "south" if k <= 8 else "north"
        inner = "north" if k <= 8 else "south"
        pl.pins_toward(t, ["PRI_A", "PRI_B", "PRI_A_END", "PRI_B_END"], outer,
                       note="primary toward the cell's own copper, secondary (pins 5, 8) toward the spine")
        pl.pins_toward(t, ["SEC_DOT", "SEC_END"], inner)
        pl.hot_loop([c["c2"][1], t["PRI_A"], t["PRI_B"], t["PRI_A_END"], t["PRI_B_END"], u["SW"], u["GND"],
                     c["c2"][2]], note="primary loop, <= 15 mm perimeter")
        pl.hot_loop([t["SEC_END"], c["d1"]["A"], c["d1"]["K"], c["c6"][1], c["c6"][2], t["SEC_DOT"]],
                    note="secondary loop")
        pl.hot_loop([u["SW"], c["d2"]["A"], c["d2"]["K"], c["c5"][1], c["c5"][2], u["VIN"]], note="RCD clamp")
        pl.near(c["c3"], u["VIN"], "tight")
        pl.near(c["c2"], t["PRI_A"], "tight")
        pl.near(c["c2"], u["GND"][-1], "tight")
        pl.near(c["c1"], c["d3"], "tight")
        pl.near(c["c4"], u["OUT"], "tight")
        pl.near(c["r2"], u["DCHRG"], "tight")
        pl.near(c["r4"], u["MODE"], "tight")
        pl.near(c["opto"], u["DCHRG"], "close")
        pl.near(c["c6"], c["d1"]["K"], "tight")
        pl.far(afe["u"], t, "close", note="keep the monitor cool and away from switching fields")
        pl.thermal(u, 0.6, "copper", note=f"EP to >= 650 mm2 TAP{k - 1} copper on L1+L2+L4, >= 9 vias "
                                          "(LT8584 p.28)")
        pl.thermal(t, 0.5, "air")
        pl.custom("island", net=n[f"TAP{k - 1}"], layers="In1.Cu", under=c["blk"],
                  note="per-channel reference plane at the channel's own potential")
        pl.custom("spacing", nets=[c["sw"], f"ch{k}/SNB_{k}"], min_mm=0.6,
                  note="SW/SNB reach 38.5 V above TAP(k-1): IPC-2221B B2 31-50 V external, except at the "
                       "U1kk/T1kk/D2kk pads themselves")
        pl.keepout(t, what="foreign-domain copper in the primary-secondary pad gap", layers="all")
    pl.custom("corridor", nets=[n[f"TAP{t}"] for t in range(0, 9)] + [n[f"S_{k}"] for k in range(1, 9)],
              edge="south", layer="In2.Cu", ordered="by index",
              note="taps and S lines run in potential order: neighbours differ by one cell")
    pl.custom("corridor", nets=[n[f"TAP{t}"] for t in range(16, 7, -1)] + [n[f"S_{k}"] for k in range(16, 8, -1)],
              edge="north", layer="In2.Cu", ordered="by index")
    for t in TAPS:
        pl.custom("current", net=n[f"TAP{t}"], amps=I_TAP, layer="In2.Cu", width_mm=W_TAP,
                  note="2.6 A average, 34-67 A for <= 5 ms until F1tt opens (C-7)")
    pl.custom("current", net=n["FLYBUS"], amps=I_FLY, layer="F.Cu", note="spine bus, D1kk cathodes to D1")
    pl.custom("keepout_mlcc", parts=[chs[k][x] for k in CH for x in ("c1", "c2", "c6")] + [psu["c8"], psu["c11"]],
              what="1210 MLCC within 5 mm of a board edge or hole", note="flex cracking shorts a cell (H-1)")
    # return and thermal sensing
    pl.near(ret["d1"], tp["F16"], "close")
    pl.near(ret["d2"], ret["d1"], "close")
    pl.thermal(ret["d1"], 0.7, "copper", note=">= 400 mm2 on the TAP16 tab")
    for th, k in zip(afe["th"], (3, 6, 12)):
        pl.near(th, chs[k]["u"], "close", note="board temperature at a hot channel; keep 0.6 mm to its copper")
    # monitor and supply
    for cap, pin in ((afe["c1"], "V+"), (afe["c2"], "VREG"), (afe["c3"], "VREF1"), (afe["c4"], "VREF2")):
        pl.near(cap, afe["u"][pin], "tight")
    pl.hot_loop([psu["c8"][1], psu["u3"]["VIN"], psu["u3"]["SW"], psu["l1"][1], psu["l1"][2], psu["c11"][1],
                 psu["c11"][2], psu["u3"]["GND"], psu["c8"][2]], note="buck input and output loop")
    pl.near(psu["c8"], psu["u3"]["VIN"], "tight")
    pl.near(psu["c10"], psu["u3"]["BST"], "tight")
    pl.near(psu["r12"], psu["u3"]["RON"], "tight")
    pl.near(psu["r13"], psu["u3"]["FB"], "close")
    pl.far(psu["u3"], afe["u"], "close")
    pl.near(mcu["c16"], mcu["u"]["VDD"], "tight")
    pl.near(mcu["c18"], mcu["u"]["PF2"], "tight")
    pl.far(iso["blk"], chs[8]["blk"], "close", note="AQY210EH/STM32 are 85 C parts (calc iso_temp_margin_C)")
    pl.far(iso["blk"], chs[9]["blk"], "close")
    # isolation
    pl.custom("straddle", part=iso["u5"], a=d.domains["CTRL"], b=d.domains["USER"],
              note="body across the 8 mm reinforced gap; no copper or vias under it")
    pl.custom("straddle", part=iso["u6"], a=d.domains["CTRL"], b=d.domains["FAULT"],
              note="body across the 5 mm reinforced gap")
    pl.keepout(iso["u5"], what="copper and vias in the pad-row gap", layers="all")
    pl.keepout(iso["u6"], what="copper and vias in the pad-row gap", layers="all")
    for bar in d.barriers:
        pl.separate(d.domains[bar.a], d.domains[bar.b], slot=bar.slot)
    for h in holes:
        pl.keepout(h, what="copper, 3.0 mm ring around the screw head", layers="all", note="barrier B-5")
    pl.custom("label", obj=tp["J1"], text="TAP 0 (B- CELL, NOT P-) ... 16 (B+); bridge N+1..16 for N < 16")
    pl.custom("label", obj=iso["j2"], text="UART: GND VIO TX RX (isolated)")
    pl.custom("label", obj=iso["j4"], text="FAULT contact, <= 30 V 50 mA")


def board(d):
    holes = [Hole(5, 5, 4.3, note="H1, M4 NPTH, nylon standoff"), Hole(135, 5, 4.3, note="H2"),
             Hole(265, 5, 4.3, note="H3"), Hole(5, 125, 4.3, note="H4"), Hole(135, 125, 4.3, note="H5"),
             Hole(265, 125, 4.3, note="H6")]
    d.board("main", width_mm=270, height_mm=130, layers=4, thickness_mm=1.6, copper_oz=2, holes=holes,
            max_component_height_mm=15, max_bottom_height_mm=2.5,
            enclosure="UL 94 V-0 plastic enclosure in the battery cabinet next to the cells (Q-8); harness <= 1 m",
            coating="",
            keepouts=[{"relative": "3.0 mm ring around each of H1-H6", "what": "copper", "layers": "all",
                       "note": "B-5 basic insulation to chassis screws"}],
            notes="FR-4 CTI >= 175 V (material group IIIa), 1.6 mm. L1/L4 2 oz; L2 per-channel reference islands; "
                  "L3 2 oz tap corridors and spine. Top-side assembly; J1 THT leads <= 2.5 mm below. Six M4 NPTH "
                  "on nylon standoffs")


# =================================================================================================
# Waivers (each is an accepted, recorded exception; see report.md)

def waivers(d):
    W = d.waive
    W("rating.current", r"^T1\d\d \(NA5743",
      "Transformer peak 6.8 A vs 7.0 A rating (97 %): the LT8584 sets the peak (6.0-6.8 A, Rev B p.3) and ADI "
      "pairs it with this transformer (Rev B Table 3). There is no rms rating to derate against; saturation is "
      "checked in T-EFF (calc xfmr_ipk_ratio <= 1.0).")
    W("rating.voltage", r"^(D3\d\d \(SMA6T6V7AY|D2 \(SMBJ70A|U7 \(TPD4E05U06)",
      "TVS stand-off by design sits just above the working voltage: VRWM is itself the working-voltage rating "
      "(leakage specified at VRWM: 20 uA, 1 uA, 10 nA). An 80 % derating would push the clamp above what it "
      "protects (LT8584 VIN 9 V, C6kk/D1 100 V, ISO7721 6 V).")
    W("rating.voltage", r"^(U2 \(STM32G031K8T6\)|U5 \(ISO7721DWV\)|U1 \(ADBMS1818ASWZ\)|U3 \(LM5164\)): "
      r"V\((VDD|PA0|VCC2|OUTB|VREG|IPB|BST)",
      "IC supply or I/O pin at its own rail inside the recommended operating range (STM32 VDD 3.37 V of 1.7-3.6 V; "
      "ISO7721 VCC2 = host 2.25-5.5 V; ADBMS1818 VREG/IPB/IMB = 5 V regulator; LM5164 BST-SW = its internal 5 V "
      "VCC). The stress is set by the rail, not the design; derating a CMOS abs max on its own rail does not apply.")
    W("protect.threat", r"TAP\d+_IN declares threat 'reverse_polarity'",
      "Reversed or swapped taps are handled by crowbar, not blocking: the unidirectional TVS D3kk conducts "
      "forward on reversal and the board fuse F1tt opens (H-8, F-6). A series diode would add 0.5 V x 2.5 A "
      "per tap and halve the efficiency budget. The framework counts only diode/MOSFET categories.")
    W("protect.entry_fuse", r"VIO_ISO",
      "VIO_ISO is the host's logic supply into U5 side 2 only (<= 4 mA, ISO7721 SLLSEP3G); the host port limits "
      "it. A fuse would not open at these currents.")
    W("kicad.erc.pin_to_pin", r"Bidirectional and Power output.*#FLG",
      "The power output is a PWR_FLAG the emitter adds to nets with power inputs and no regulator output: GND_B "
      "(U1 GPIO4-9 tied to V- as unused inputs) and ISO_VCC1 (U5 side 1 is powered from MCU pin PB0, <= 4 mA, so "
      "the MCU can remove isolator power when no host is present). Neither is a driver conflict.")
    W("conn.empty_net", r"CHASSIS",
      "Chassis has no copper on the board by design; the net exists so the BAT0-CHASSIS barrier (B-5) reaches "
      "intent.yaml and the .kicad_dru.")


def build():
    d = Design("liion-balancer", title="Li-ion active cell balancer, 13-16S (LT8584 x 16 + ADBMS1818)",
               description="Per-cell isolated flyback (cell -> stack) with fused taps, two enables per channel, "
                           "isolated UART and fault contact",
               brief=BRIEF, ambient_c=(0, 45))
    intent(d)
    n = domains_and_nets(d)
    barriers(d)
    tp = tap_blocks(d, n)
    chs = {k: channel_block(d, n, k) for k in CH}
    ret = ret_block(d, n)
    afe = afe_block(d, n)
    psu = psu_block(d, n)
    mcu = mcu_block(d, n)
    en = en_block(d, n)
    iso = iso_block(d, n)
    harness_block(d, n)
    holes = mech_block(d)
    hazards(d)
    calcs(d)
    board(d)
    placement(d, n, tp, chs, ret, afe, psu, mcu, en, iso, holes)
    waivers(d)
    return d
