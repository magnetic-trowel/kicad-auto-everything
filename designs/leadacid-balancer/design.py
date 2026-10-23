# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""leadacid-balancer: MCU-free 2:1 switched-capacitor equalizer for 2-4 series 12 V lead-acid batteries.

Encodes designs/leadacid-balancer/DESIGN.md (engineering rationale, evidence tags, sources) and
CONNECTIONS.md (net naming, pin rationale). Build: `kaesynth build designs/leadacid-balancer/design.py -v`.

Domain model (exact stack, no interval blow-up):
  B1     root, ref TAP0 (system negative). Holds TAP0, TAP1 and every net referenced to TAP0.
  Bk     (k = 2..4) floats on TAP(k-1): battery k's domain. Holds TAPk (v = one battery, 0-20 V) and
         every net referenced to TAP(k-1). Bk is the "band" of DESIGN.md section 6 plus its top tap.
  CHk_HSU floats on CHk_X (upper switch node): bootstrap BSTU, OUTA/GA of the upper driver, C_FLY +.
  CHk_HSL floats on CHk_Y (lower switch node): BSTL, OUTA/GC of the lower driver, C_FLY -.
  CHk_LS  floats on T_H: the base of level-shift PNP Q(k)07, within one V_BE of T_H.
  CHk_QFB floats on CHk_V5: the base of fault-driver PNP Q(k)05, within one V_BE of V5.
  CHk_SPAN floats on T_L: nets that swing across both batteries of the pair (PON_A, LSD, LSM), kept out
         of the band domains so each band stays within 30 V inside.
  ISO    root, ref ALM_E: the opto-isolated alarm contact.
Channel k uses T_L = TAP(k-1), T_M = TAPk, T_H = TAP(k+1); its L side lives in Bk, its U side in B(k+1).
"""
import importlib.util
import math
from pathlib import Path

from kaesynth import Design, Hole

_spec = importlib.util.spec_from_file_location("leadacid_balancer_parts", Path(__file__).with_name("parts.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

BRIEF = ("I want a battery balancer that can balance a string, series string of 12 volt lead acid batteries. "
         "I want another one that can balance a series string of lithium ion batteries. This would be in the "
         "10 kilowatt hour range, so home packs. It should make sure that there's no pathways for voltage to jump "
         "from places. I don't know if you want to do a flying capacitor or inductor or some other elegant "
         "approach, but it needs to keep the charge balanced without bleed resistors. Ideally, it would be as "
         "efficient as possible, as robust as possible, and allow us to have little wires that go to the system "
         "ground and then all of the individual positive terminals.")

# -- configuration ----------------------------------------------------------------------------------
N_BATT = 4                  # batteries in the string: 2, 3 or 4 (REQ-25, Q-1, Q-13)
CHANNELS = (1, 2, 3)        # the board always carries three channels; channel k needs batteries k and k+1

# -- voltage and current envelopes (DESIGN.md sections 2 and 7) ---------------------------------------
VB = 20.0                   # survive maximum per battery incl. charger transients (REQ-3), V
VB_OP = 17.6                # operating maximum: 16.20 V equalize + 30 mV/K x 45 K (REQ-3)
V12 = 12.5                  # 12 V gate rails: 1.193 V x (1 + 909/100) = 12.04 V nominal, +4 % worst [I]
V5MAX = 5.05                # TPS70950 5.0 V +/-1 %
R_SC_MIN, R_SC_NOM, R_SC_MAX = 0.476, 0.514, 0.567      # calc r_sc_* (Ohm)
K_FLY, K_FET = 2.13, 1.51                               # rms flying / FET current per A of balancing current
R_HI_WORST = 1.1153                                     # upper lockout trip, worst (REQ-11; calc ratio_hi_worst)
I_EDGE = (R_HI_WORST - 1) * 17.55 / R_SC_MIN            # 4.38 A: window edge, worst tolerances, 17.55 V, -20 C
I_FLY = K_FLY * I_EDGE                                  # 9.3 A rms in the flying path at that edge


def _ratio(top, bot):
    return bot / (top + bot)


# Supervisor divider strings (review M-1, M-3): 0.1 % TNPW1206 thin film (<= 2 MOhm per segment), node
# voltages raised to ~2.5 V so comparator offset + hysteresis stay small. Each top is a series chain; each lower
# element is two equal resistors in parallel, so one open or shorted part at most doubles a node voltage. The
# PLO and PHI strings carry a second tap ~2 % away (a small parallel pair) for the imbalance warning.
#            name   from  top segments (Ohm)             [(output node, lower pair, each Ohm), ...]
STRINGS = {"PON": ("TH", (2.00e6,) * 4, [("PON", 1.67e6)]),
           "PLO": ("TH", (2.00e6,) * 3 + (1.96e6,), [("PWH", 30.9e3), ("PLO", 1.58e6)]),
           "PHI": ("TH", (2.00e6,) * 4, [("PHI", 36.5e3), ("PWL", 1.70e6)]),
           "N": ("TM", (2.00e6,) * 2, [("N", 1.85e6)])}


def string_total(sname):
    _, tops, lows = STRINGS[sname]
    return sum(tops) + sum(r / 2 for _, r in lows)


def k_of(node):
    """Division ratio of an output node (V_node / V_source)."""
    for sname, (_, tops, lows) in STRINGS.items():
        below = 0.0
        for name, r in reversed(lows):
            below += r / 2
            if name == node:
                return below / string_total(sname)
    raise KeyError(node)


WIN_TOL = 0.015     # on V_pair/V_bot: offset + V_HYS/2 (linear, 0.88 %) + 0.1 % resistors and TCR (RSS, 0.58 %)


def intent(d):
    # -- requirements (DESIGN.md section 2) -----------------------------------------------------------
    R = d.require
    R("REQ-1", "Balance a series string of N 12 V lead-acid batteries", value="N = 2, 3 or 4 (24/36/48 V)",
      source="brief + derived (ASM-1, Q-1)", verify="V-1")
    R("REQ-2", "Battery types", value="flooded, AGM, gel; 100-400 Ah per 12 V battery", source="brief ('10 kWh')",
      verify="analysis 7.1")
    R("REQ-3", "Per-battery voltage: operate / survive", value="10.5-17.6 V / 0-20 V",
      source="Trojan 16.20 V equalize + 30 mV/K at -20 C [P]", verify="analysis 7.1, V-2")
    R("REQ-4", "Maximum stack voltage", value="70.2 V (4 x 17.55 V)", source="derived", verify="analysis")
    R("REQ-5", "No dissipative balancing", value="no bleed resistor or linear shunt in the balancing path",
      source="brief", verify="inspection")
    R("REQ-6", "Balancing current with the harness of REQ-22, worst case incl. finite tap capacitance and the "
      "1.5 s tap-check pauses", value=">= 0.09 A at 0.1 V; >= 0.26 A at 0.3 V",
      source="derived 7.2 (relaxed from 0.10/0.30 A after the review's periodic-steady-state model; a 0.1 A float "
             "mismatch still settles at <= 0.11 V per pair)", verify="V-3; calcs i_bal_*")
    R("REQ-7", "Charge-transfer efficiency", value=">= 97 % for dV <= 0.3 V", source="brief", verify="V-4")
    R("REQ-8", "Active overhead per channel", value="<= 0.30 W, only while a charger is present",
      source="derived (0.25 W before the fail-safe alarm LED, review M-4)", verify="V-4")
    R("REQ-9", "Sleep current per battery / mismatch between batteries", value="<= 50 uA / <= 40 uA",
      source="derived from the brief's 'as efficient as possible' (no stored-energy drain at rest)", verify="V-5")
    R("REQ-10", "Wake threshold on the pair voltage", value="rising 26.25-26.8 V (13.23 V per battery nominal, "
      "offset and centred hysteresis included); falling >= 26.0 V worst case", source="derived 7.7 (Q-2)",
      verify="V-6")
    R("REQ-11", "Ratio lockout (stop, red LED, alarm open) and imbalance warning (alarm open, keeps running)",
      value="lockout 0.915 / 1.090 nominal; warning 0.956 / 1.043; +/-1.5 % on V_pair/V_bot",
      source="derived: a shorted cell gives r = 0.833 or 1.20 (review M-1, M-3)", verify="V-7; calcs ratio_*, warn_*")
    R("REQ-12", "Window-edge dissipation per channel (failing battery, worst tolerances) / thermal cut-out",
      value="<= 7.2 W at 50 C ambient, <= 9.5 W at -20 C (17.55 V) / cut-out 90-102 C",
      source="derived 7.6", verify="V-8")
    R("REQ-13", "Fault containment: no single fault causes a sustained short or connects >= 2 batteries through "
      "< 100 kOhm; every board fault current is interrupted by an on-board fuse", value="-",
      source="brief ('no pathways')", verify="FMEA (hazards), V-9..V-15")
    R("REQ-14", "Tap fusing", value="battery end (<= 150 mm from post): >= 80 VDC, >= 10 kA DC; on board: >= 80 VDC, "
      ">= 1 kA DC", source="brief + derived 7.10", verify="inspection, V-9")
    R("REQ-15", "Spacing", value="adjacent battery domains 0.6/0.6 mm; non-adjacent 1.5/1.0 mm; ISO 4.0/4.0 mm "
      "(creepage/clearance)", source="IPC-2221B B2; IEC 60664-1 F.4 [S]", verify="KiCad DRC (.kicad_dru), inspection")
    R("REQ-16", "Hot-plug: any mating order of the tap plug, any missing tap, any broken tap wire", value="no damage",
      source="derived", verify="V-12")
    R("REQ-17", "Mis-wiring (swapped taps, reversed battery)", value="no fire; fuses clear; FETs and the logic LDOs "
      "of the affected channel may need replacement (review MINOR-8)", source="derived", verify="V-13")
    R("REQ-18", "Environment", value="-20..+50 C, indoor, pollution degree 2, <= 2000 m", source="Trojan [P]",
      verify="analysis")
    R("REQ-19", "Control", value="no MCU, no firmware", source="decision (DESIGN.md 5)", verify="inspection")
    R("REQ-20", "Indication per channel", value="green ACTIVE, red FAULT (lockout or over-temperature)",
      source="brief", verify="V-6, V-7")
    R("REQ-21", "Telemetry: one isolated fail-safe contact, closed only while every channel charges without fault "
      "or imbalance warning; open at rest, on any fault, warning, open tap (within one pause) or lost supply",
      value="<= 30 V, <= 1 mA; reverse-protected", source="derived; review M-4", verify="V-14; calcs opto_*")
    R("REQ-22", "Harness: N + 1 wires (system negative and every battery positive), ring terminals, fused at the "
      "battery, pluggable at the board", value="14 AWG <= 3 m (16 AWG allowed <= 1.5 m)",
      source="brief; REQ-6 (calc i_bal_*): R_ext must stay small against R_SC, so the wires cannot be thinner",
      verify="inspection")
    R("REQ-23", "Service: the board unplugs in one action to replace a battery", value="-", source="derived",
      verify="inspection")
    R("REQ-24", "Component derating in normal operation: semis <= 80 % V, caps <= 80 % V (DC bias counted), "
      "resistors <= 50 % P, fuses <= 75 % I. At the abnormal window edge (failing battery): <= 100 % of the "
      "temperature-derated rating", value="-", source="task default", verify="kaesynth rating.* checks; calcs")
    R("REQ-25", "Battery-count configuration: shunts on JP101..JP(N-1)01 (channel enable); for each unused "
      "channel a shunt on JPk02 (bridges its alarm opto); every unused tap-plug position bridged to the highest used "
      "position inside the plug", value=f"design default N = {N_BATT} (N_BATT)", source="REQ-1; H-12",
      verify="V-1; label next to J1")

    # -- assumptions and questions (DESIGN.md section 3) -----------------------------------------------
    A = d.assume
    A("ASM-1", "Primary target N = 4 (48 V, 4 x 12 V x ~200 Ah = 9.6 kWh); N = 2 and 3 supported by jumpers")
    A("ASM-2", "Batteries in a string are the same model and similar age")
    A("ASM-3", "Charger is a 3-stage temperature-compensated unit (equalize for flooded); no communication")
    A("ASM-4", "Negative-ground system: TAP0 is the system ground")
    A("ASM-5", "One string per board")
    A("ASM-6", "Prospective short-circuit current at the battery posts <= 10 kA")
    A("ASM-7", "FR-4 with CTI >= 175 V (material group IIIa)")
    A("ASM-8", "Board lives in a ventilated IP54 enclosure outside the battery compartment")
    A("ASM-9", "No certification for now; spacing from IEC 62368-1 / 60664-1 principles via secondary values")
    A("ASM-10", "Harness 0.3-3 m per tap")
    A("ASM-11", "The alarm circuit (ALM_E) stays within +/-100 V of TAP0")
    Q = d.question
    Q("Q-1", "Confirm N = 2-4. Is a > 4-battery (96 V) bank needed? A > 70 V stack is outside this safety analysis.",
      blocking=True, default="N = 2-4 by jumper; N_BATT = 4")
    Q("Q-2", "Battery model and charger set-points (float, absorb, equalize, temperature compensation)? The wake "
      "threshold is 13.23 +/- 0.09 V per battery (R120-R125); a float below ~13.3 V may never wake the balancer.",
      blocking=True, default="13.23 V per battery wake (R120-R123 2.00 M, R124-R125 1.67 M)")
    Q("Q-3", "Are flooded batteries equalized at >= 16.2 V? The stack then exceeds 60 VDC (ES2): labelling.",
      default="yes, assumed (17.6 V per battery max)")
    Q("Q-4", "MLCCs and an electrolytic sit directly across each battery. If one shorts, the on-board fuse clears. "
      "Acceptable, or must they be series-redundant pairs (+16 caps per channel, +8 mm board)?", blocking=True,
      default="single parts, fused")
    Q("Q-5", "Board fuse DC breaking capacity.", blocking=False,
      answer="Closed by review B-1: 0477004 breaks only 500 A at 400 VDC; replaced by Littelfuse KLKD006.T "
             "(600 VDC, 10 kA DC UL 248-19, read in the KLKD datasheet Rev 061217) in Keystone 3576 holders",
      default="KLKD006.T")
    Q("Q-6", "Phoenix MSTB/MSTBA, Eaton HEB and Nichicon UCZ ratings are [S]; verify.",
      default="as listed in parts.py")
    Q("Q-7", "Is the isolated alarm wanted, and what does it drive (voltage, polarity)?",
      default="fail-safe contact, <= 30 V, <= 1 mA, + to J2.1")
    Q("Q-8", "Should balancing also run during discharge/rest ('always on', 0.66 W continuous)? A burst mode "
      "(switch only while |dV| > ~30 mV) would cut float overhead (review MINOR-10).",
      default="no: runs only while a charger holds >= 13.23 V per battery; no burst mode")
    Q("Q-14", "Should the imbalance warning (+/-4 %) be delayed (e.g. sustained > 1 h) before it opens the alarm "
      "contact? Today it opens at once, also after replacing a battery.", default="no delay")
    Q("Q-9", "Conformal coating (acrylic, IPC-CC-830) for battery-room humidity and acid mist?",
      default="not coated; spacing uses IPC-2221B B2 (uncoated)")
    Q("Q-10", "Re-evaluate the ADI LTC7820 integrated SC controller once its datasheet can be read.",
      default="discrete design")
    Q("Q-11", "Must the board survive mis-wiring without FET damage? Then add per-channel reverse protection.",
      default="no: fuses clear, FETs may need replacement")
    Q("Q-12", "Certification target (UL 1973 / IEC 62368-1)? If yes, re-derive spacing from purchased standards.",
      blocking=True, default="no certification")
    Q("Q-13", "How many batteries will this unit serve (sets N_BATT, the shunts on JP101-JP301 and the plug "
      "bridges, REQ-25)?", default=f"N = {N_BATT}")


def hazards(d, ch, inp, har):
    H = d.hazard
    every = lambda key: [ch[k][key] for k in CHANNELS]
    flt = [p for k in CHANNELS for p in (ch[k]["U08"], ch[k]["R26"], ch[k]["R30"], ch[k]["R34"])]
    H("H-1", "Arc, fire or burns from a battery short through the harness (one 200 Ah AGM gives 3.3 kA)",
      "KLKD010 600 VDC 10 kA DC fuse in a sealed in-line holder <= 150 mm from each post; 600 V insulation; loom",
      parts=har["fuses"] + har["holders"], single_fault_safe=False,
      notes="the <= 150 mm pigtail before the fuse is unprotected: double-insulate and clamp it")
    H("H-2", "Fire on the board (shorted FET, flying cap or bulk cap; contamination)",
      "on-board KLKD006.T 6 A 600 VDC fuse per tap, 10 kA DC (F1-F5); prospective current 128-670 A "
      "(calc board_fault_*)",
      parts=inp["fuses"], single_fault_safe=True, notes="the harness fuse backs up the board fuse")
    H("H-3", "Two or more batteries bridged ('voltage jumping')",
      "potential-ordered layout (bands west to east); spacing rules (barriers); no part spans >= 2 batteries except "
      "divider strings (>= 4.99 MOhm, top split in two), the level shifter (2 x 49.9 kOhm in series) and certified "
      "isolation barriers (UCC21520, SFH617A)",
      parts=every("R47") + every("R51") + every("R20") + every("R26") + every("R30") + every("U01") + every("U02")
      + every("U10"), single_fault_safe=True)
    H("H-4", "Balancer drains good batteries into a failed one (shorted cell)",
      "ratio lockout ~+/-9 % (U(k)08 B/C, 0.1 % strings) stops the channel and opens the alarm", parts=flt,
      single_fault_safe=True,
      notes="lockout and thermal cut-out are independent comparators")
    H("H-5", "Mis-wiring: swapped taps or a reversed battery",
      "keyed single plug, numbered/coloured wires, pre-plug voltage check (V-13); body diodes conduct and the 6 A "
      "fast fuse clears in ms", parts=inp["fuses"] + [inp["J1"]], single_fault_safe=False,
      notes="no fire; FETs and the logic LDOs of the affected channel may fail (review MINOR-8, Q-11)")
    H("H-6", "Hydrogen ignition (LEL 4 %)",
      "enclosure outside the battery box and not above vents; plug only at the board; harness fuses enclosed; "
      "no relays", parts=[], single_fault_safe=True, notes="installation rule (DESIGN.md 9)")
    H("H-7", "Board overheating at the ratio-window edge (failing battery: up to 6.4 W per channel at 50 C) or "
      "blocked vents", "thermal cut-out 90-102 C (NTC RTk01 + U(k)08 D); power bounded by the window (calc edge_*); "
      "R_CF doubled so it stays within its rating at the cut-out temperature",
      parts=every("RT01") + every("U08"), single_fault_safe=True, notes="window and cut-out are independent")
    H("H-8", "Shock: stack up to 70.2 VDC (ES2 during cold equalize)",
      "enclosure; insulated pluggable connector; alarm opto with reinforced package, 4 mm board spacing, reverse "
      "diode D1 in the alarm loop", parts=every("U10") + [inp["J1"]], single_fault_safe=True)
    H("H-9", "Bank drained in storage (balancer awake at rest)",
      "wakes only at >= 13.2 V per battery; sleep <= 36 uA; a stuck-awake fault shows on the green LED",
      parts=every("R20") + every("R24") + every("U08") + every("D04"), single_fault_safe=False,
      notes="partial: needs a human to see the LED")
    H("H-10", "A battery opens internally under load (broken strap)",
      "body diodes carry string current until the tap fuses clear (ms)", parts=inp["fuses"], single_fault_safe=True)
    H("H-11", "Corrosion or leakage across divider nodes (acid mist, humidity)",
      "strings <= 10 MOhm; each divider top split in two; conformal coat optional (Q-9); IP54 box",
      parts=every("R26") + every("R27") + every("R34") + every("R35"), single_fault_safe=True)
    H("H-12", "Unused or broken top tap floats ~0.8 V below T_M (N < 4 without bridges, or a broken T_H wire), "
      "reverse-biasing that channel's upper LDO and bulk cap",
      "plug bridges for N < 4 (REQ-25); the ratio window lights FAULT on a broken wire",
      parts=har["bridges"] + every("U08"), single_fault_safe=False, notes="no fire; LDO stress at uA only")
    H("H-13", "A failing battery (soft short, high self-discharge) absorbs amps from the balancer during charge: "
      "internal heating, dry-out (review M-3)",
      "imbalance warning at ~+/-4 % (U(k)11 B/C) opens the alarm contact while the channel keeps running; above "
      "~9 % the lockout stops it; the current before the warning is <= 2.4 A (calc silent_current_max_A)",
      parts=every("U11") + every("R60") + every("R62"), single_fault_safe=False,
      notes="needs someone to act on the alarm; a time-delayed warning is Q-14")
    H("H-14", "Broken tap wire goes unnoticed (T0 or a middle tap while charging: the SC cell holds the floating "
      "node at a plausible voltage, review M-4)",
      "U(k)11 D stops both drivers for 1.5 s every ~33 s; the LDO loads then slew a floating middle tap out of "
      "the window, and a floating T0 collapses CH1's V5; the fail-safe series alarm contact opens in both cases",
      parts=every("U11") + every("C51") + every("U10"), single_fault_safe=False,
      notes="at rest the contact is open by design, so a tap that breaks at rest shows at the next charge; V-12")


def numbers():
    """Every calculated value (DESIGN.md section 7), with its inputs in one place."""
    n = {}
    f, t_dt = 100e3, 0.2e-6
    t_p = 1 / (2 * f) - t_dt

    def r_sc(cap, r_loop):
        return 1 / (cap * f * math.tanh(t_p / (2 * r_loop * cap)))
    r_cf = 0.043                                    # each position: 2 x 0.086 Ohm in parallel
    r_lo = 2 * 8.1e-3 + 2 * r_cf + 5e-3             # Ron typ 25 C, + ESR and copper
    r_hi = 2 * 9.9e-3 * 1.4 + 2 * r_cf + 5e-3       # Ron max x 1.4 hot
    corners = [r_sc(c, r) for c in (30e-6, 50e-6) for r in (r_lo, r_hi)]
    n["r_sc_min"], n["r_sc_max"] = min(corners), max(corners)
    n["r_sc_nom"] = r_sc(40e-6, (r_lo + r_hi) / 2)

    def r_tap(length, ohm_per_m):
        return 12.8e-3 + ohm_per_m * length + 3e-3 + 26.1e-3    # KLKD010 + wire + lugs/plug + KLKD006 [P]
    awg14, awg16 = 8.28e-3, 13.2e-3
    n["r_ext_3m_14awg"] = 6 * r_tap(3, awg14) + 2 * 4e-3
    n["r_ext_1m5_16awg"] = 6 * r_tap(1.5, awg16) + 2 * 4e-3
    n["r_ext_0m3"] = 6 * r_tap(0.3, awg14) + 2 * 4e-3
    rx = max(n["r_ext_3m_14awg"], n["r_ext_1m5_16awg"])
    # pause oscillator (U(k)11 D): thresholds 1/3 and 2/3 V5, pause = charge through R76 + R77 + D05
    c_t, r_fast, r_slow = 4.7e-6, 100e3 + 249e3, 2 * 4.99e6
    n["t_pause"] = r_fast * c_t * math.log((4.4 - 5 / 3) / (4.4 - 10 / 3))
    n["t_run"] = r_slow * c_t * math.log(2)
    n["duty"] = n["t_run"] / (n["t_run"] + n["t_pause"])
    sim = 0.92          # review MINOR-1: periodic-steady-state model with the real C_TOP/C_BOT gave 0.095 vs 0.103 A
    n["i_bal_0v1"] = 0.1 / (n["r_sc_max"] + rx) * sim * n["duty"]
    n["i_bal_0v3"] = 0.3 / (n["r_sc_max"] + rx) * sim * n["duty"]
    n["eff_0v3"] = 1 - 0.3 / 13.2                   # lowest running voltage is the wake threshold
    # overhead (7.5) + fail-safe alarm opto LED (<= 5.0 mA from V5, fed from the battery through the LDO)
    qg = 13e-9
    i_l = 2 * 1.4e-3 + 2 * 1.0e-3 + 2 * qg * f + 0.3e-3 + 1.0e-3
    i_u = 2 * 1.0e-3 + 2 * qg * f
    n["overhead_W"] = 13.5 * (i_l + i_u + 4.5e-3) + 4 * 0.5 * 15e-9 * 13.5 * f
    n["ldo_l_W"] = (VB_OP - 12.04) * i_l
    # sleep (7.9), uA at 12.8 V per battery
    pair, vb = 2 * 12.8, 12.8
    s_pair = sum(pair / string_total(x) * 1e6 for x in ("PON", "PLO", "PHI"))
    s_n = vb / string_total("N") * 1e6
    s_ntc = 5.0 / (24.9e3 + 470e3) * 1e6
    s_osc = 5.0 / (2 * 4.99e6) * 1e6
    n["sleep_bot_uA"] = 1.4 + 0.65 + 2 * 4 * 0.335 + 0.1 + s_ntc + s_n + s_osc + 0.59 + s_pair + 1.0
    n["sleep_top_uA"] = s_pair + 0.59 + 1.0
    n["sleep_batt_max_uA"] = n["sleep_bot_uA"] + n["sleep_top_uA"]      # a middle battery serves two channels
    n["sleep_mismatch_uA"] = n["sleep_batt_max_uA"] - n["sleep_top_uA"]
    # wake (7.7): offset 8 mV and half of the 3-25 mV hysteresis, centred (SLVSE13J 6.4.2), on 2.5 V
    k_on = k_of("PON")
    res, ref = 2 * 0.001, 0.0005 + 0.0007
    n["wake_rise"] = 2.5 / k_on
    n["wake_rise_hi"] = (2.5 + 0.008 + 0.0125) / k_on * (1 + res + ref)
    n["wake_rise_lo"] = (2.5 - 0.008 + 0.0015) / k_on * (1 - res - ref)
    n["wake_fall_lo"] = (2.5 - 0.008 - 0.0125) / k_on * (1 - res - ref)
    # ratio windows (7.7), tolerance on V_pair/V_bot = r + 1
    k_n = k_of("N")
    n_low = k_n * 26.0 / (1 + 1.088)                 # N node at the lowest running pair voltage
    n["tol_offset"] = (0.008 + 0.0125) / n_low
    n["tol_res"] = math.hypot(2 * 2 * 0.001, 2 * 25e-6 * 45)
    n["tol"] = n["tol_offset"] + n["tol_res"]
    for tag, sname in (("hi", "PLO"), ("lo", "PHI"), ("wh", "PWH"), ("wl", "PWL")):
        q = k_n / k_of(sname)
        n[f"r_{tag}"], n[f"r_{tag}_up"], n[f"r_{tag}_dn"] = q - 1, q * (1 + WIN_TOL) - 1, q * (1 - WIN_TOL) - 1
    # one lower resistor open: that lower pair doubles; worst node at 17.6 V per battery
    worst = 0.0
    for sname, (src, tops, lows) in STRINGS.items():
        v = 35.2 if src == "TH" else 17.6
        for j in range(len(lows)):
            dbl = [r * (2 if i == j else 1) for i, (_, r) in enumerate(lows)]
            worst = max(worst, v * (sum(dbl) / 2) / (sum(tops) + sum(dbl) / 2))
    n["node_fault_max"] = worst
    # NTC trip (7.6)
    trips = []
    for v5 in (4.95, 5.05):
        for r138 in (24.9e3 * 0.99, 24.9e3 * 1.01):
            for r25 in (470e3 * 0.97, 470e3 * 1.03):
                for b in (4582 * 0.97, 4582 * 1.03):
                    for vref in (2.5 - 0.0205, 2.5 + 0.0205):
                        r_t = r138 * vref / (v5 - vref)
                        trips.append(1 / (1 / 298.15 + math.log(r_t / r25) / b) - 273.15)
    n["ntc_trip_nom"] = 1 / (1 / 298.15 + math.log(24.9e3 / 470e3) / 4582) - 273.15
    n["ntc_trip_lo"], n["ntc_trip_hi"] = min(trips), max(trips)
    # window edge (7.6): lockout upper trip at its worst, hot (board at cut-out, equalize at 45 C) and cold
    n["r_sc_hot"] = r_sc(50e-6, 2 * 8.1e-3 * 1.45 + 2 * r_cf + 5e-3)
    for tag, vbot, rsc in (("hot", 15.6, n["r_sc_hot"]), ("cold", 17.55, n["r_sc_min"])):
        dv = (n["r_hi_up"] - 1) * vbot
        i = dv / rsc
        n[f"edge_dv_{tag}"], n[f"edge_I_{tag}"], n[f"edge_P_{tag}"] = dv, i, dv * i
        n[f"edge_rcf_each_{tag}"] = (K_FLY * i) ** 2 * r_cf / 2
        n[f"edge_fet_{tag}"] = (K_FET * i) ** 2 * 13.9e-3
    n["rcf_rating_99C"] = 2.0 * (170 - 99) / (170 - 70)
    n["fet_tj_edge"] = 99 + n["edge_fet_hot"] * (1.9 + 10)
    # current a failing battery can absorb without a lockout, and the warning bound (review M-3)
    n["silent_I"] = (n["r_wh_up"] - 1) * 15.6 / n["r_sc_min"]
    # fuses and faults (7.10)
    n["board_fault_max_A"] = 70.2 / (2 * r_tap(0.3, awg14) + 4 * 4e-3)
    n["board_fault_min_A"] = 17.6 / (2 * r_tap(3, awg14) + 4e-3)
    # alarm opto: RUN (VOH >= V5 min - 0.3 V at 5 mA) through R72 825 Ohm
    i_f_min = (4.95 - 0.3 - 1.4) / (825 * 1.01)
    n["opto_if_min_mA"] = i_f_min * 1e3
    n["opto_sink_min_mA"] = i_f_min * 0.34 * 0.8 * 1e3
    n["opto_if_max_mA"] = (V5MAX - 1.0) / (825 * 0.99) * 1e3
    # open-tap detection in a pause (review M-4): net LDO current into the floating tap node
    n["open_tap_slew"] = 4.1e-3 / 240e-6                  # V/s: |I_12VL - I_12VU| into C_TOP + C_BOT [I]
    return n


def calcs(d):
    n = numbers()
    c = d.calc
    c("r_sc_min_ohm", round(n["r_sc_min"], 3), "Ohm", expr="1/(C f tanh(t_p/2RC)), C 30-50 uF, R_loop 107-119 mOhm")
    c("r_sc_max_ohm", round(n["r_sc_max"], 3), "Ohm", expr="same corners")
    c("r_ext_3m_14awg_ohm", round(n["r_ext_3m_14awg"], 3), "Ohm",
      expr="6 x (KLKD010 12.8 + 8.28/m x 3 m + 3 + KLKD006 26.1 mOhm) + 2 x 4 mOhm")
    c("pause_s", round(n["t_pause"], 2), "s", expr="(R76 + R77) C51 ln(2.73/1.07)", limit=1.2, op=">=",
      note="> 3 x the 0.35 s divider filters, so the ratio is read at rest")
    c("pause_period_run_s", round(n["t_run"], 1), "s", expr="(R78 + R79) C51 ln 2", limit=60,
      note="an open tap is found within one period")
    c("i_bal_0v1_worst_A", round(n["i_bal_0v1"], 4), "A",
      expr="0.1 V / (R_SC max + R_ext max) x 0.92 (finite C_TOP/C_BOT, review sim) x run duty", limit=0.09, op=">=",
      note="REQ-6")
    c("i_bal_0v3_worst_A", round(n["i_bal_0v3"], 4), "A", expr="same at 0.3 V", limit=0.26, op=">=", note="REQ-6")
    c("transfer_eff_0v3", round(n["eff_0v3"], 4), "", expr="1 - 0.3 V / 13.2 V", limit=0.97, op=">=", note="REQ-7")
    c("overhead_per_channel_W", round(n["overhead_W"], 3), "W",
      expr="13.5 V x (12V_L 8.7 + 12V_U 4.6 + alarm opto 4.5 mA) + Coss 41 mW", limit=0.30, note="REQ-8")
    c("ldo_12vl_W", round(n["ldo_l_W"], 3), "W", expr="(17.6 - 12.04) V x 8.7 mA", limit=0.2)
    c("sleep_batt_max_uA", round(n["sleep_batt_max_uA"], 1), "uA", expr="middle battery: B_bot + B_top",
      limit=50, note="REQ-9")
    c("sleep_mismatch_uA", round(n["sleep_mismatch_uA"], 1), "uA", expr="max - min per battery (N = 4)", limit=40,
      note="REQ-9")
    c("wake_rise_V", round(n["wake_rise"], 3), "V", expr="2.5 V / 0.09451")
    c("wake_rise_max_V", round(n["wake_rise_hi"], 3), "V", expr="(2.5 + 8 mV + 25 mV/2) / k x (1 + 0.32 %)",
      limit=26.8, note="REQ-10 (review MINOR-2)")
    c("wake_rise_min_V", round(n["wake_rise_lo"], 3), "V", expr="(2.5 - 8 mV + 3 mV/2) / k x (1 - 0.32 %)",
      limit=26.25, op=">=", note="REQ-10")
    c("wake_fall_min_V", round(n["wake_fall_lo"], 3), "V", expr="(2.5 - 8 mV - 25 mV/2) / k x (1 - 0.32 %)",
      limit=26.0, op=">=", note="REQ-10: resting AGM 12.8-12.95 V per battery is below it")
    c("window_tol", round(n["tol"], 4), "", expr="(8 mV + 12.5 mV)/N(26 V pair) + RSS(0.4 % ratio, 0.45 % TCR)",
      limit=WIN_TOL, note="REQ-11 (review M-1)")
    for tag, what in (("hi", "lockout, top high"), ("lo", "lockout, top low"), ("wh", "warning, top high"),
                      ("wl", "warning, top low")):
        c(f"ratio_{tag}_nom", round(n[f"r_{tag}"], 4), "", expr=f"k_N / k - 1 ({what})")
    c("ratio_hi_worst", round(n["r_hi_up"], 4), "", expr="(r + 1) x 1.015 - 1", limit=1.20,
      note="trips on a shorted cell in the bottom battery (r = 1.20)")
    c("ratio_lo_worst", round(n["r_lo_dn"], 4), "", expr="(r + 1) x 0.985 - 1", limit=0.833, op=">=",
      note="trips on a shorted cell in the top battery (r = 0.833)")
    c("ratio_hi_min", round(n["r_hi_dn"], 4), "", expr="(r + 1) x 0.985 - 1", limit=1.037, op=">=",
      note="no lockout at 0.5 V imbalance at 13.5 V")
    c("ratio_lo_max", round(n["r_lo_up"], 4), "", expr="(r + 1) x 1.015 - 1", limit=0.964,
      note="no lockout at 0.5 V imbalance at 13.5 V")
    c("warn_hi_early", round(n["r_wh_dn"], 4), "", expr="(r + 1) x 0.985 - 1", limit=1.01, op=">=",
      note="no warning in a balanced string (the lockout also opens the alarm, so overlap is harmless)")
    c("warn_lo_early", round(n["r_wl_up"], 4), "", expr="(r + 1) x 1.015 - 1", limit=0.99,
      note="no warning in a balanced string")
    c("comparator_input_fault_V", round(n["node_fault_max"], 2), "V",
      expr="one bottom resistor open at 17.6 V per battery", limit=7.0, note="TLV7044 input abs max")
    c("silent_current_max_A", round(n["silent_I"], 2), "A",
      expr="warning upper trip at its worst x 15.6 V / R_SC min",
      note="largest current into a failing battery before the alarm opens (review M-3; was 4.4 A)")
    c("ntc_trip_nom_C", round(n["ntc_trip_nom"], 1), "C", expr="R_NTC = R138 x VREF/(V5 - VREF); B 4582 K")
    c("ntc_trip_max_C", round(n["ntc_trip_hi"], 1), "C", expr="corners incl. offset + hysteresis/2", limit=110,
      note="REQ-12")
    c("ntc_trip_min_C", round(n["ntc_trip_lo"], 1), "C", expr="same corners", limit=85, op=">=")
    c("edge_power_hot_W", round(n["edge_P_hot"], 2), "W", expr="dV = (r_hi worst - 1) x 15.6 V, I = dV / 0.505 Ohm",
      limit=7.2, note="REQ-12, 50 C ambient")
    c("edge_power_cold_W", round(n["edge_P_cold"], 2), "W", expr="dV = (r_hi worst - 1) x 17.55 V, R_SC 0.476 Ohm", limit=9.5,
      note="REQ-12, -20 C")
    c("edge_rcf_each_hot_W", round(n["edge_rcf_each_hot"], 2), "W", expr="(2.13 I)^2 x 0.043 / 2",
      limit=round(n["rcf_rating_99C"], 2), note="WSL2816 rating at the 99 C cut-out; REQ-24 abnormal")
    c("edge_rcf_each_cold_W", round(n["edge_rcf_each_cold"], 2), "W", expr="same at 17.55 V", limit=2.0)
    c("edge_middle_tap_A", round(2 * n["edge_I_cold"], 1), "A", expr="2 x I_edge (cold)",
      note="KLKD006 opens: safe end state of a failing-battery condition")
    c("edge_fet_tj_C", round(n["fet_tj_edge"], 1), "C", expr="99 C + (1.51 I)^2 x 13.9 mOhm x 11.9 K/W", limit=125)
    c("gate_vgs_ratio", round(V12 / 20, 3), "", expr="12.5 V / 20 V", limit=0.8)
    c("bootstrap_ratio", round(1e-6 / (13e-9 / 12), 0), "x", expr="1 uF / (13 nC / 12 V)", limit=10, op=">=")
    c("bootstrap_inrush_A", round(12.5 / (4.7 + 0.3), 2), "A", expr="12.5 V / (R_BOOT 4.7 + ESR ~0.3 Ohm)",
      limit=3.0, note="BAS16W I_FSM 2 A at 1 us, decays with tau = 5 us (review MINOR-4)")
    c("deadtime_margin_ns", 160 - (19 + 20), "ns", expr="DT min 160 ns - (skew 19 + fall 20)", limit=0, op=">")
    c("board_fault_max_A", round(n["board_fault_max_A"]), "A", expr="70.2 V / (2 R_tap(0.3 m) + 4 R_int)",
      limit=10000, note="KLKD006 DC 10 kA (UL 248-19) [P] (review B-1)")
    c("board_fault_min_A", round(n["board_fault_min_A"]), "A", expr="17.6 V / (2 R_tap(3 m) + R_int)", limit=60,
      op=">=", note=">= 10 x In: the 6 A fast fuse clears in milliseconds")
    c("harness_fault_max_A", 3300, "A", expr="AGM 200 Ah I_sc [P]", limit=10000, note="KLKD010 DC 10 kA [P]")
    c("fuse_selectivity_ratio", round(96.8 / 278, 2), "",
      expr="KLKD006 clearing I2t 96.8 A2s / KLKD010 melting I2t 278 A2s (both at 20 kA) [P]", limit=1.0,
      note="board faults clear on the board fuse")
    c("hotplug_i2t_A2s", 0.3, "A2s", expr="140 uF per leg, 200 A peak, tau 14 us", limit=6.3,
      note="<= 1/10 of the KLKD006 melting I2t 63 A2s [P]")
    c("opto_sink_min_mA", round(n["opto_sink_min_mA"], 2), "mA",
      expr="I_F min (4.65 - 1.4 V)/833 Ohm x CTR 34 % x 0.8 ageing", limit=1.0, op=">=", note="REQ-21")
    c("opto_if_max_mA", round(n["opto_if_max_mA"], 1), "mA", expr="(5.05 - 1.0 V)/817 Ohm", limit=16)
    c("open_tap_detect_s", round(1.5 / n["open_tap_slew"] + 3 * 0.35, 2), "s",
      expr="1.5 V of window / (4.1 mA / 240 uF) + 3 filter tau", limit=round(n["t_pause"], 2),
      note="an open middle tap leaves the window within one pause (review M-4) [I], verify V-12")
    c("wire_drop_3m_V", round(4 * 8.28e-3 * 3, 3), "V", expr="4 A x 8.28 mOhm/m x 3 m")


# =====================================================================================================
# Channel builder


def channel(d, k):
    """Channel k (DESIGN.md 3.1-3.5 for k = 1; CONNECTIONS.md 4 substitution rule for k = 2, 3)."""
    TL, TM, TH = (d.nets[f"TAP{j}"] for j in (k - 1, k, k + 1))
    bL, bU = f"B{k}", f"B{k + 1}"
    used = k <= N_BATT - 1
    blk = d.block(f"ch{k}", domain=bL,
                  title=f"Channel {k}: SC cell B{k} <-> B{k + 1}",
                  description=f"T_L TAP{k - 1}, T_M TAP{k}, T_H TAP{k + 1}; PWR, DRV, OSC, SUP, SUPV; refdes {k}nn; "
                              f"{'enabled' if used else 'disabled (no shunt on JP' + str(k) + '01)'} for N = {N_BATT}")
    p = {}

    def add(defn, key, prefix=None, **kw):
        part = blk.add(defn, ref=f"{prefix or defn.prefix}{k}{key[-2:]}", **kw)
        p[key] = part
        return part

    def net(name, **kw):
        return blk.net(f"CH{k}_{name}", **kw)

    # -- nets -----------------------------------------------------------------------------------------
    X = net("X", domain=bU, v=(-1.0, VB + 1.0), kind="switching", i_max=round(I_FLY, 1),
            notes="upper switch node: T_M (phase 2) / T_H (phase 1), 100 kHz; body diodes clamp 0.7 V beyond")
    Y = net("Y", domain=bL, v=(-1.0, VB + 1.0), kind="switching", i_max=round(I_FLY, 1),
            notes="lower switch node: T_L (phase 2) / T_M (phase 1)")
    hsu, hsl, ls, qfb_dom, span = f"CH{k}_HSU", f"CH{k}_HSL", f"CH{k}_LS", f"CH{k}_QFB", f"CH{k}_SPAN"
    # nets that swing across both batteries of the pair (> 30 V from T_L) get their own domain, so the
    # band domains keep <= 30 V inside and fine-pitch parts in them can use the 0.2 mm in-domain rule
    d.domain(span, ref=TL.name, kind="battery",
             description=f"rides on TAP{k - 1}, spans T_L..T_H: top wake-divider node, level-shift drain/midpoint")
    d.domain(hsu, ref=X.full_name, kind="battery", description=f"rides on CH{k}_X: BSTU, OA_U, GA, C_FLY +")
    d.domain(hsl, ref=Y.full_name, kind="battery", description=f"rides on CH{k}_Y: BSTL, OA_L, GC, C_FLY -")
    cfp = net("CFP", domain=hsu, v=(-0.4, 0.4), kind="switching", i_max=round(I_FLY, 1),
              notes="C_FLY +: X minus the drop on R_CF (<= 8 A pk x 0.043 Ohm)")
    cfn = net("CFN", domain=hsl, v=(-0.4, 0.4), kind="switching", i_max=round(I_FLY, 1), notes="C_FLY -")
    ga = net("GA", domain=hsu, v=(-2.0, V12), kind="switching", i_peak=4.0, notes="Q_A gate; -2 V for <= 200 ns")
    oa_u = net("OA_U", domain=hsu, v=(-2.0, V12), kind="switching", i_peak=6.0)
    bstu = net("BSTU", domain=hsu, v=(0, V12), kind="power", i_max=0.0013, i_peak=1.0,
               notes="9-11.5 V above X; 1.3 mA average")
    gb = net("GB", domain=bU, v=(-2.0, V12), kind="switching", i_peak=4.0)
    ob_u = net("OB_U", domain=bU, v=(-2.0, V12), kind="switching", i_peak=6.0)
    gc = net("GC", domain=hsl, v=(-2.0, V12), kind="switching", i_peak=4.0)
    oa_l = net("OA_L", domain=hsl, v=(-2.0, V12), kind="switching", i_peak=6.0)
    bstl = net("BSTL", domain=hsl, v=(0, V12), kind="power", i_max=0.0013, i_peak=1.0)
    gd = net("GD", v=(-2.0, V12), kind="switching", i_peak=4.0)
    ob_l = net("OB_L", v=(-2.0, V12), kind="switching", i_peak=6.0)
    v12l = net("12VL", v=(0, V12), kind="power", i_max=0.015, notes="gated by RUN; 0 V asleep")
    v12u = net("12VU", domain=bU, v=(0, V12), kind="power", i_max=0.008, notes="gated by ENU; 0 V asleep")
    fbl = net("FBL", v=(0, 1.25), kind="analog")
    fbu = net("FBU", domain=bU, v=(0, 1.25), kind="analog")
    v5in = net("V5IN", v=(0, VB), kind="power", i_max=0.010, notes=f"= TAP{k} when JP{k}01 has its shunt")
    v5 = net("V5", v=(0, V5MAX), kind="power", i_max=0.010, notes="always on while JP fitted; fault LED <= 9 mA")
    d.domain(qfb_dom, ref=v5.full_name, kind="battery", description=f"rides on CH{k}_V5: base of Q{k}05")
    v5en = net("V5EN", v=(0, 6.5), kind="signal",
               notes="TPS709 EN left floating (allowed, SBVS186H Table 5-1): internal 300 nA pull-up, stays < 6.5 V")
    vref = net("VREF", v=(0, 2.5), kind="analog")
    vpair = 2 * VB
    snet = {}           # divider nets by string: top mid nodes, then the output nodes
    for sname, (src, tops, lows) in STRINGS.items():
        span_v = vpair if src == "TH" else VB
        total = string_total(sname)
        nodes = []
        for i in range(1, len(tops)):
            vmax = round(span_v * (total - sum(tops[:i])) / total, 1)
            nodes.append(net(f"{sname}_M{i}", domain=span if vmax > 30 else bL, v=(0, vmax), kind="sense"))
        for oname, _ in lows:
            nodes.append(net(oname, v=(0, round(span_v * k_of(oname), 2)), kind="sense",
                             notes=f"divider output, {k_of(oname):.5f} x {'V_pair' if src == 'TH' else 'V_bot'}"))
        snet[sname] = nodes
    named = {x.name.split("_", 1)[1]: x for v in snet.values() for x in v}
    pon, plo, phi, pwh, pwl, n_ = (named[x] for x in ("PON", "PLO", "PHI", "PWH", "PWL", "N"))
    th = net("TH", v=(0, V5MAX), kind="sense", notes="NTC node: 4.75 V at 25 C, 2.5 V at 95 C")
    nchg = net("NCHG", v=(0, V5MAX), kind="signal", notes="high = not charging")
    flt_n = net("FLT_N", v=(0, V5MAX), kind="signal", notes="wired-AND open drain, low = fault")
    qfb = net("QFB", domain=qfb_dom, v=(-0.8, 0), kind="signal")
    flt = net("FLT", v=(0, V5MAX), kind="signal", notes="NOT FLT_N, push-pull from U(k)09 gate 1")
    ledq = net("LEDQ", v=(0, V5MAX), kind="signal", i_max=0.0045, notes="Q(k)05 collector: red FAULT LED drive")
    oka = net("OKA", v=(0, 1.65), kind="signal", i_max=0.0047,
              notes="alarm-opto LED anode: RUN through R(k)72; pulled low by the warning comparators")
    pause = net("PAUSE", v=(0, V5MAX), kind="signal",
                notes="U(k)11 D relaxation oscillator: high 1.5 s every ~33 s disables both drivers (tap check)")
    tpn = net("TPN", v=(0, V5MAX), kind="analog", notes="oscillator threshold, 1/3 or 2/3 of V5")
    tct = net("TCT", v=(0, V5MAX), kind="analog", notes="oscillator timing capacitor")
    tsm = net("TSM", v=(0, V5MAX), kind="analog")
    pda = net("PDA", v=(0, V5MAX), kind="analog")
    bsu_a = net("BSU_A", domain=bU, v=(0, V12), kind="power", i_max=0.0013, i_peak=1.0)
    bsl_a = net("BSL_A", v=(0, V12), kind="power", i_max=0.0013, i_peak=1.0)
    run = net("RUN", v=(0, V5MAX), kind="signal", notes="high = run")
    lsd = net("LSD", domain=span, v=(0, vpair), kind="signal", i_max=0.0004,
              notes="level shift: 0 V (on) .. V_pair - 0.6 V (off)")
    lsm = net("LSM", domain=span, v=(0, vpair), kind="signal", i_max=0.0004, notes="midpoint of R(k)47/R(k)51")
    d.domain(ls, ref=TH.name, kind="battery", description=f"rides on TAP{k + 1}: base of Q{k}07")
    lsb = net("LSB", domain=ls, v=(-1.0, 0), kind="signal", i_max=0.0004)
    lsc = net("LSC", domain=bU, v=(0, VB), kind="signal")
    enu = net("ENU", domain=bU, v=(0, VB / 2), kind="signal", notes="V_top/2 when on")
    dtu = net("DTU", v=(0, 1.2), kind="analog")
    dtl = net("DTL", v=(0, 1.2), kind="analog")
    ph1 = net("PH1", v=(0, V12), kind="clock")
    ph2 = net("PH2", v=(0, V12), kind="clock")
    oscc = net("OSCC", v=(-0.5, V12 + 0.5), kind="analog")
    oscr = net("OSCR", v=(-0.5, V12 + 0.5), kind="analog")
    oscrc = net("OSCRC", v=(-0.5, V12 + 0.5), kind="analog")
    ledr = net("LEDR_A", v=(0, 2.6), kind="signal", i_max=0.0045, notes="clamped by the red LED V_F")
    ledg = net("LEDG_A", v=(0, 2.6), kind="signal", i_max=0.0011)
    alm_in = d.nets[f"ALM_S{k}"]                          # series alarm chain (review M-4: closed = healthy)
    alm_out = d.nets["ALM_E"] if k == 3 else d.nets[f"ALM_S{k + 1}"]

    # -- 3.1 PWR: switched-capacitor cell --------------------------------------------------------------
    edge = numbers()
    q_a = add(P.FET_SC, "Q01", p_diss=round(edge["edge_fet_hot"], 2))
    q_b = add(P.FET_SC, "Q02", p_diss=round(edge["edge_fet_hot"], 2))
    q_c = add(P.FET_SC, "Q03", p_diss=round(edge["edge_fet_hot"], 2))
    q_d = add(P.FET_SC, "Q04", p_diss=round(edge["edge_fet_hot"], 2))
    X.connect(q_a["S"], q_b["D"])
    ga.connect(q_a["G"])
    TH.connect(q_a["D"])
    TM.connect(q_b["S"], q_c["D"])
    gb.connect(q_b["G"])
    Y.connect(q_c["S"], q_d["D"])
    gc.connect(q_c["G"])
    TL.connect(q_d["S"])
    gd.connect(q_d["G"])
    # R_CF: two 0.086 Ohm in parallel per position. p_diss = window edge at 50 C (abnormal, bounded by the
    # thermal cut-out; calc edge_rcf_each_hot_W); normal operation is <= 0.04 W each.
    pd_rcf = round(edge["edge_rcf_each_hot"], 2)
    r01 = add(P.R_CF, "R01", p_diss=pd_rcf)
    r52 = add(P.R_CF, "R52", p_diss=pd_rcf)
    r02 = add(P.R_CF, "R02", p_diss=pd_rcf)
    r53 = add(P.R_CF, "R53", p_diss=pd_rcf)
    X.connect(r01[1], r52[1])
    cfp.connect(r01[2], r52[2])
    cfn.connect(r02[1], r53[1])
    Y.connect(r02[2], r53[2])
    ceff = {"Ceff": "~5-6 uF each at 13-17 V (X7S DC bias), 30-50 uF per bank [I]"}
    for i in range(1, 9):
        # C_FLY always sits across one battery (phase 1 B_top, phase 2 B_bot) through on-FETs, so it never sees
        # more than one battery voltage plus the R_CF drop; the HSU/HSL envelope difference (~42 V) is not physical.
        cf = add(P.C_10U50, f"C{i:02d}", v_across=VB + 0.5, fields=ceff)
        cfp.connect(cf[1])
        cfn.connect(cf[2])
    for i in range(9, 13):
        ct = add(P.C_10U50, f"C{i:02d}", fields=ceff)
        TH.connect(ct[1])
        TM.connect(ct[2])
    for i in range(13, 17):
        cb = add(P.C_10U50, f"C{i:02d}", fields=ceff)
        TM.connect(cb[1])
        TL.connect(cb[2])
    c17 = add(P.C_BULK, "C17")
    TH.connect(c17[1])
    TM.connect(c17[2])
    c18 = add(P.C_BULK, "C18")
    TM.connect(c18[1])
    TL.connect(c18[2])
    r03 = add(P.R_100K, "R03")
    X.connect(r03[1])
    TH.connect(r03[2])
    r04 = add(P.R_100K, "R04")
    Y.connect(r04[1])
    TM.connect(r04[2])

    # -- 3.2 DRV: gate drivers ---------------------------------------------------------------------------
    u01 = add(P.GATE_DRV, "U01", p_diss=0.05)
    u02 = add(P.GATE_DRV, "U02", p_diss=0.05)
    for u, dt, vssb, outb, vddb, vssa, outa, vdda in ((u01, dtu, TM, ob_u, v12u, X, oa_u, bstu),
                                                       (u02, dtl, TL, ob_l, v12l, Y, oa_l, bstl)):
        ph1.connect(u["INA"])
        ph2.connect(u["INB"])
        v12l.connect(u["VCCI"])
        TL.connect(u["GND"])
        pause.connect(u["DIS"])            # periodic 1.5 s stop: an open tap then slews out of the window
        dt.connect(u["DT"])
        vssb.connect(u["VSSB"])
        outb.connect(u["OUTB"])
        vddb.connect(u["VDDB"])
        vssa.connect(u["VSSA"])
        outa.connect(u["OUTA"])
        vdda.connect(u["VDDA"])
    # gate resistors: p_diss = Qg x V x f = 13 nC x 12 V x 100 kHz, all of it as an upper bound
    for key, a, b in (("R05", oa_u, ga), ("R06", ob_u, gb), ("R07", oa_l, gc), ("R08", ob_l, gd)):
        r = add(P.R_4R7, key, p_diss=0.016)
        a.connect(r[1])
        b.connect(r[2])
    for key, a, b in (("R09", ga, X), ("R10", gb, TM), ("R11", gc, Y), ("R12", gd, TL)):
        r = add(P.R_10K, key)
        a.connect(r[1])
        b.connect(r[2])
    for rk, ck, dt in (("R13", "C19", dtu), ("R14", "C20", dtl)):
        r = add(P.R_20K, rk)
        cc = add(P.C_470P, ck)
        dt.connect(r[1], cc[1])
        TL.connect(r[2], cc[2])
    for key, defn, rail, gnd in (("C21", P.C_1U25, v12l, TL), ("C22", P.C_100N, v12l, TL),
                                 ("C23", P.C_1U25, v12l, TL), ("C24", P.C_100N, v12l, TL),
                                 ("C25", P.C_1U25, v12u, TM), ("C26", P.C_100N, v12u, TM),
                                 ("C27", P.C_1U25, v12l, TL), ("C28", P.C_100N, v12l, TL),
                                 ("C29", P.C_1U25, bstu, X), ("C30", P.C_1U25, bstl, Y)):
        cc = add(defn, key)
        rail.connect(cc[1])
        gnd.connect(cc[2])
    # R_BOOT 4.7 Ohm in series with each bootstrap diode (review MINOR-4, SLUSCJ9F 9.2.2.2): limits the first
    # charge of C_boot at every wake to < 2.7 A (BAS16W I_FSM 2 A at 1 us is reached only for < 1 us)
    for rk, dk, rail, mid, bst in (("R58", "D01", v12u, bsu_a, bstu), ("R59", "D02", v12l, bsl_a, bstl)):
        r = add(P.R_4R7, rk, p_diss=0.001)
        rail.connect(r[1])
        mid.connect(r[2])
        dd = add(P.DIODE_BOOT, dk)
        mid.connect(dd["A"])
        bst.connect(dd["K"])

    # -- 3.3 OSC: 100 kHz complementary clock -----------------------------------------------------------
    u03 = add(P.OSC, "U03")
    oscc.connect(u03[1])
    oscr.connect(u03[2])
    oscrc.connect(u03[3])
    v12l.connect(u03[4], u03[5], u03[6], u03[14])
    TL.connect(u03[7], u03[8], u03[9], u03[12])
    ph1.connect(u03[10])
    ph2.connect(u03[11])
    u03.nc_pins("13", reason="OSC OUT unused in free-running astable (SCHS044C p.2 functional connections)")
    r15 = add(P.R_22K1, "R15")
    oscr.connect(r15[1])
    oscrc.connect(r15[2])
    c31 = add(P.C_100P, "C31")
    oscc.connect(c31[1])
    oscrc.connect(c31[2])
    c32 = add(P.C_100N, "C32")
    v12l.connect(c32[1])
    TL.connect(c32[2])

    # -- 3.4 SUP: supplies, enable level shifter, channel jumper -----------------------------------------
    u04 = add(P.LDO_12V, "U04", p_diss=0.05)
    v12l.connect(u04["OUT"])
    fbl.connect(u04["FB"])
    TL.connect(u04["GND"], u04["PAD"])
    run.connect(u04["EN"])
    TM.connect(u04["IN"])
    u05 = add(P.LDO_12V, "U05", p_diss=0.03)
    v12u.connect(u05["OUT"])
    fbu.connect(u05["FB"])
    TM.connect(u05["GND"], u05["PAD"])
    enu.connect(u05["EN"])
    TH.connect(u05["IN"])
    for u in (u04, u05):
        u.nc_pins("PG", "DELAY", reason="power-good unused; PG open drain and DELAY may float (SBVS171F Pin Functions)")
        u.nc_pins("NC", reason="NC: no internal connection (SBVS171F Pin Functions)")
    for key, defn, a, b in (("R16", P.R_909K, v12l, fbl), ("R17", P.R_100K, fbl, TL),
                            ("C33", P.C_1U50, TM, TL), ("C34", P.C_10U25, v12l, TL),
                            ("R18", P.R_909K, v12u, fbu), ("R19", P.R_100K, fbu, TM),
                            ("C35", P.C_1U50, TH, TM), ("C36", P.C_10U25, v12u, TM)):
        x = add(defn, key)
        a.connect(x[1])
        b.connect(x[2])
    u06 = add(P.LDO_5V, "U06")
    v5in.connect(u06["IN"])
    TL.connect(u06["GND"])
    v5en.connect(u06["EN"])
    v5.connect(u06["OUT"])
    u06.nc_pins("NC", reason="NC (SBVS186H Table 5-1)")
    for key, defn, a, b in (("C37", P.C_1U50, v5in, TL), ("C38", P.C_4U7, v5, TL), ("C39", P.C_10N, v5en, TL)):
        x = add(defn, key)
        a.connect(x[1])
        b.connect(x[2])
    jp = add(P.JUMPER, "JP01", prefix="JP", i_through=0.010)     # V5 rail incl. fault LED; not the tap current
    TM.connect(jp[1])
    v5in.connect(jp[2])
    add(P.SHUNT, "JS01", prefix="JS", dnp=not used)
    q06 = add(P.FET_LS, "Q06", i_through=0.0004)      # level-shift current (V_pair / 100 k)
    run.connect(q06["G"])
    TL.connect(q06["S"])
    lsd.connect(q06["D"])
    for key, a, b in (("R47", lsd, lsm), ("R51", lsm, lsb)):
        r = add(P.R_49K9, key)
        a.connect(r[1])
        b.connect(r[2])
    q07 = add(P.PNP, "Q07", i_through=0.0004)         # emitter on T_H carries base + ENU divider current only
    lsb.connect(q07["B"])
    TH.connect(q07["E"])
    lsc.connect(q07["C"])
    for key, defn, a, b in (("R48", P.R_100K, lsb, TH), ("R49", P.R_100K, lsc, enu), ("R50", P.R_100K, enu, TM),
                            ("C50", P.C_10N, enu, TM)):
        x = add(defn, key)
        a.connect(x[1])
        b.connect(x[2])

    # -- 3.5 SUPV: wake, ratio lockout, thermal, indication, alarm ----------------------------------------
    u07 = add(P.VREF, "U07")
    TL.connect(u07["GND"])
    v5.connect(u07["EN"], u07["VIN"])
    vref.connect(u07["VREF"])
    u07.nc_pins("NR", reason="NR: noise-reduction filter pin, may be left floating (SNAS809C Table 5-1)")
    for key, defn, a, b in (("C40", P.C_100N, v5, TL), ("C41", P.C_1U25, vref, TL)):
        x = add(defn, key)
        a.connect(x[1])
        b.connect(x[2])
    u08 = add(P.COMP, "U08")
    nchg.connect(u08["OUTA"])
    pon.connect(u08["INA-"])
    vref.connect(u08["INA+"], u08["IND-"])
    v5.connect(u08["VCC"])
    n_.connect(u08["INB+"], u08["INC-"])
    plo.connect(u08["INB-"])
    flt_n.connect(u08["OUTB"], u08["OUTC"], u08["OUTD"])
    phi.connect(u08["INC+"])
    TL.connect(u08["VEE"])
    th.connect(u08["IND+"])
    # divider strings: tops in series from T_H (T_M for N), lower elements as parallel pairs, filter caps to T_L
    rnum = {"PON": [20, 21, 22, 23, 24, 25], "PLO": [26, 27, 54, 55, 60, 61, 28, 29],
            "PHI": [30, 31, 56, 57, 62, 63, 32, 33], "N": [34, 35, 36, 37]}
    filt = {"PON": "C43", "PLO": "C44", "PHI": "C45", "PWH": "C53", "PWL": "C54", "N": "C46"}
    rdef = {2.00e6: P.R_2M00, 1.96e6: P.R_1M96, 1.67e6: P.R_1M67, 1.58e6: P.R_1M58, 1.70e6: P.R_1M70,
            1.85e6: P.R_1M85, 30.9e3: P.R_30K9, 36.5e3: P.R_36K5}
    for sname, (src, tops, lows) in STRINGS.items():
        refs = iter(rnum[sname])
        nodes = [TH if src == "TH" else TM] + snet[sname]
        for i, rv in enumerate(tops):
            x = add(rdef[rv], f"R{next(refs)}")
            nodes[i].connect(x[1])
            nodes[i + 1].connect(x[2])
        outs = nodes[len(tops):] + [TL]
        for j, (oname, rv) in enumerate(lows):
            for _ in range(2):
                x = add(rdef[rv], f"R{next(refs)}")
                outs[j].connect(x[1])
                outs[j + 1].connect(x[2])
            x = add(P.C_470N, filt[oname])
            outs[j].connect(x[1])
            TL.connect(x[2])
    c42 = add(P.C_100N, "C42")
    v5.connect(c42[1])
    TL.connect(c42[2])
    chain = (("R38", P.R_24K9, v5, th), ("C47", P.C_1U25, th, TL),
             ("R39", P.R_100K, v5, flt_n), ("R40", P.R_100K, v5, nchg),
             ("C48", P.C_100N, v5, TL), ("R41", P.R_100K, run, TL), ("C49", P.C_10N, run, TL),
             # Q(k)05 base: forced beta ~ 20 at 4.5 mA (review M-2); drives the red LED only
             ("R42", P.R_10K, flt_n, qfb), ("R43", P.R_100K, qfb, v5), ("R44", P.R_100K, ledq, TL),
             ("R46", P.R_10K, v12l, ledg))
    for key, defn, a, b in chain:
        x = add(defn, key)
        a.connect(x[1])
        b.connect(x[2])
    r45 = add(P.R_750, "R45", p_diss=0.01)       # red LED (4.85 - 1.8) / 750 <= 4.1 mA: 13 mW
    ledq.connect(r45[1])
    ledr.connect(r45[2])
    rt = add(P.NTC, "RT01", prefix="RT")
    th.connect(rt[1])
    TL.connect(rt[2])
    # U(k)09 dual NOR (review M-2): gate 1 FLT = NOT FLT_N (clean push-pull level), gate 2 RUN = NOR(NCHG, FLT).
    # Inputs come only from open-drain outputs with 100 k pull-ups or a gate output, never from an LED node.
    u09 = add(P.NOR2, "U09")
    flt_n.connect(u09["1A"], u09["1B"])
    flt.connect(u09["1Y"], u09["2B"])
    nchg.connect(u09["2A"])
    run.connect(u09["2Y"])
    TL.connect(u09["GND"])
    v5.connect(u09["VCC"])
    q05 = add(P.PNP, "Q05")
    qfb.connect(q05["B"])
    v5.connect(q05["E"])
    ledq.connect(q05["C"])
    d03 = add(P.LED_RED, "D03", i_through=0.0041)     # cathode on T_L; <= 4.1 mA through R(k)45
    TL.connect(d03["K"])
    ledr.connect(d03["A"])
    # Alarm opto (review M-4): fail-safe contact, LED on while RUN is high and no imbalance warning; the three
    # opto outputs are in series, so the contact is closed only while every channel charges healthily.
    r72 = add(P.R_825, "R72", p_diss=0.02)      # (4.65 - 1.4) / 833 >= 3.9 mA, <= 5.0 mA (calc opto_*)
    run.connect(r72[1])
    oka.connect(r72[2])
    u10 = add(P.OPTO, "U10")
    oka.connect(u10["A"])
    TL.connect(u10["K"])
    alm_in.connect(u10["C"])
    alm_out.connect(u10["E"])
    jp2 = add(P.JUMPER, "JP02", prefix="JP")     # bridges this opto when the channel is unused (REQ-25)
    alm_in.connect(jp2[1])
    alm_out.connect(jp2[2])
    add(P.SHUNT, "JS02", prefix="JS", dnp=used)
    d04 = add(P.LED_GRN, "D04", i_through=0.0011)     # cathode on T_L; (12 - 2.0) V / 10 k
    TL.connect(d04["K"])
    ledg.connect(d04["A"])
    # U(k)11: second quad comparator. B/C = imbalance warning (review M-3), D = pause oscillator (review M-4).
    u11 = add(P.COMP, "U11")
    v5.connect(u11["VCC"])
    TL.connect(u11["VEE"], u11["INA+"])
    vref.connect(u11["INA-"])
    u11.nc_pins("OUTA", reason="spare comparator A: inputs tied (+IN to VEE, -IN to VREF), output held low, unused")
    n_.connect(u11["INB+"], u11["INC-"])
    pwh.connect(u11["INB-"])
    pwl.connect(u11["INC+"])
    oka.connect(u11["OUTB"], u11["OUTC"])        # open drain: shunts the opto LED on imbalance > ~4 %
    tpn.connect(u11["IND+"])
    tct.connect(u11["IND-"])
    pause.connect(u11["OUTD"])
    for key, defn, a, b in (("C52", P.C_100N, v5, TL), ("R73", P.R_4M99, v5, tpn), ("R74", P.R_4M99, tpn, TL),
                            ("R75", P.R_4M99, pause, tpn), ("R76", P.R_100K, run, pause),
                            ("R77", P.R_249K, pda, tct), ("R78", P.R_4M99, pause, tsm), ("R79", P.R_4M99, tsm, tct),
                            ("C51", P.C_4U7, tct, TL)):
        x = add(defn, key)
        a.connect(x[1])
        b.connect(x[2])
    d05 = add(P.DIODE_BOOT, "D05")               # fast charge path: pause phase short, run phase long
    pause.connect(d05["A"])
    pda.connect(d05["K"])
    p.update(block=blk, X=X, Y=Y, PH1=ph1, PH2=ph2, PON=pon, PLO=plo, PHI=phi, N=n_, TL=TL, TM=TM, TH=TH)
    return p


# =====================================================================================================


def build():
    d = Design("leadacid-balancer", title="Lead-acid string balancer, 2:1 switched capacitor, 2-4 x 12 V",
               description="Three independent MCU-free SC ratio cells; fused taps; opto-isolated alarm",
               brief=BRIEF, ambient_c=(-20, 50))
    intent(d)
    if N_BATT not in (2, 3, 4):
        raise ValueError("N_BATT must be 2, 3 or 4 (Q-1)")

    # -- domains and global nets -------------------------------------------------------------------------
    i_tap = {0: round(I_EDGE, 1), 4: round(I_EDGE, 1)}
    edge_note = "edge current of one channel at the ratio-window edge (worst tolerances, 17.55 V); normal <= 1.2 A"
    for j in range(5):
        dom = "B1" if j == 0 else f"B{j}"
        live = j <= N_BATT
        v = 0 if j == 0 else ((0, VB) if live else (0, 0))
        imax = i_tap.get(j, round(2 * I_EDGE, 1)) if live else None
        kind = "ground" if j == 0 else "power"
        what = "system negative (T0)" if j == 0 else f"positive of battery B{j}" + ("" if live else " (bridged: unused)")
        d.net(f"TAP{j}", domain=dom, v=v, kind=kind, i_max=imax, notes=f"fused tap bus, {what}; {edge_note}")
        d.net(f"TAP{j}_IN", domain=dom, v=v, kind=kind, i_max=imax, external=live,
              threats=("overcurrent", "reverse_polarity") if live else (),
              notes=f"J1 pin {j + 1} to F{j + 1}: harness wire from the battery-end fuse")
        if live:
            d.net(f"POST{j}", domain=dom, v=v, kind=kind, i_max=imax, external=True, threats=("overcurrent",),
                  notes=f"battery terminal T{j} (ring lug LG{j} to fuse FH{j}); off-board")
        if j == 0:
            d.domain("B1", ref="TAP0", kind="battery", edge_clearance_mm=1.5,
                     edge_source="IEC 60664-1 F.4 PD2 MG IIIa ~1.4 mm at 100 V to hardware and the board edge [S]",
                     description="battery B1 and every net referenced to TAP0 (root of the stack)")
        elif j >= 2:
            d.domain(f"B{j}", ref=f"TAP{j - 1}", kind="battery",
                     description=f"battery B{j}: TAP{j} and every net referenced to TAP{j - 1}")
    d.net("ALM_E", domain="ISO", v=0, kind="signal", i_max=0.001, external=True,
          notes="alarm contact emitter side (to the external return)")
    d.domain("ISO", ref="ALM_E", kind="selv", edge_clearance_mm=1.5, edge_source="as B1",
             description="opto-isolated alarm contact; external circuit within +/-100 V of TAP0 (ASM-11)")
    d.net("ALM_C", domain="ISO", v=(0, 30), kind="signal", i_max=0.001, external=True,
          notes="alarm contact + side (external pull-up <= 30 V, <= 1 mA); closed = all channels charging and healthy")
    for i in (1, 2, 3):
        d.net(f"ALM_S{i}", domain="ISO", v=(0, 30), kind="signal", i_max=0.001,
              notes="series alarm chain: reverse diode D1, then U110, U210, U310 collector-emitter in series")

    # -- board-level blocks ----------------------------------------------------------------------------------
    blk_in = d.block("input", title="Tap input: header J1 and fuses F1-F5", domain="B1",
                     description="J1 = MSTBA 5-pos (TAP0..TAP4); F1-F5 KLKD006.T 6 A 600 VDC 10 kA DC in Keystone "
                                 "3576 holders (review B-1)")
    j1 = blk_in.add(P.J_TAP, ref="J1")
    fuses = []
    for j in range(5):
        d.nets[f"TAP{j}_IN"].connect(j1[j + 1])
        f = blk_in.add(P.FUSE_BOARD, ref=f"F{j + 1}")
        d.nets[f"TAP{j}_IN"].connect(f[1])
        d.nets[f"TAP{j}"].connect(f[2])
        fuses.append(f)
    for i in range(1, 6):
        blk_in.add(P.FUSE_HOLDER_PCB, ref=f"XH{i}")

    ch = {k: channel(d, k) for k in CHANNELS}

    blk_al = d.block("alarm", title="Isolated alarm output J2", domain="ISO",
                     description="J2 = MSTBA 2-pos: 1 ALM_C, 2 ALM_E; D1 blocks a reversed loop (review MINOR-9); "
                                 "U110, U210, U310 outputs in series: closed = healthy (fail-safe)")
    j2 = blk_al.add(P.J_ALM, ref="J2")
    d.nets["ALM_C"].connect(j2[1])
    d.nets["ALM_E"].connect(j2[2])
    d1 = blk_al.add(P.DIODE_BOOT, ref="D1", i_through=0.001)   # alarm loop <= 1 mA; VR 75 V vs 30 V reversed
    d.nets["ALM_C"].connect(d1["A"])
    d.nets["ALM_S1"].connect(d1["K"])

    blk_me = d.block("mech", title="Mounting holes (M3, nylon standoffs)")
    holes = [blk_me.add(P.HOLE_M3, ref=f"H{i}") for i in (1, 2, 3, 4)]

    har = harness(d)
    inp = {"J1": j1, "fuses": fuses}
    hazards(d, ch, inp, har)
    calcs(d)
    barriers(d)
    placement(d, ch, j1, j2, fuses, holes, blk_in, blk_al)
    board(d)
    waivers(d)
    return d


def harness(d):
    """Off-board harness (CONNECTIONS.md 5): BOM only, board='off'."""
    h = d.block("harness", board="off", title=f"Off-board harness (N = {N_BATT})",
                description="per used tap j: ring lug LGj on the battery post, KLKD010 fuse FHj in holder XFj "
                            "<= 150 mm from the lug, 14 AWG wire Wj, ferrule FEj into plug P1 position j+1; unused "
                            "positions bridged to the highest used one (BRj)")
    out = {"fuses": [], "holders": [], "bridges": []}
    p1 = h.add(P.PLUG_TAP, ref="P1")
    for j in range(5):
        d.nets[f"TAP{j}_IN"].connect(p1[j + 1])
        if j <= N_BATT:
            lug = h.add(P.RING_LUG, ref=f"LG{j}")
            fh = h.add(P.FUSE_HARNESS, ref=f"FH{j}")
            d.nets[f"POST{j}"].connect(lug[1], fh[1])
            d.nets[f"TAP{j}_IN"].connect(fh[2])
            out["fuses"].append(fh)
            out["holders"].append(h.add(P.FUSE_HOLDER, ref=f"XF{j}"))
            h.add(P.WIRE, ref=f"W{j}")
            h.add(P.FERRULE, ref=f"FE{j}")
        else:
            br = h.add(P.PLUG_BRIDGE, ref=f"BR{j}")
            d.nets[f"TAP{j}_IN"].connect(br[1])
            d.nets[f"TAP{N_BATT}_IN"].connect(br[2])
            out["bridges"].append(br)
    p2 = h.add(P.PLUG_ALM, ref="P2")
    d.nets["ALM_C"].connect(p2[1])
    d.nets["ALM_E"].connect(p2[2])
    return out


def barriers(d):
    """DESIGN.md section 6. Declaration order matters for the .kicad_dru (last matching rule wins):
    adjacent pairs first, wider pairs after, so an inherited rule never narrows a wider one."""
    ipc = "IPC-2221B Table 6-1 B2 (external, uncoated)"
    f4 = "IEC 60664-1 Table F.4 PD2 MG IIIa (SLUP419 in repo for 63 V: 1.25 mm [P]; 80-100 V 1.3-1.4 mm [S])"
    for a, b in (("B1", "B2"), ("B2", "B3"), ("B3", "B4")):
        d.barrier(a, b, grade="functional", v_work=round(2 * VB_OP + V12 + 2, 1), creepage_mm=0.6, clearance_mm=0.6,
                  standard=ipc, pollution_degree=2, material_group="IIIa",
                  source="B2 31-50 V: 0.6 mm [S]. A battery domain holds its top tap, so adjacent domains reach "
                         "2 Vb + 12.5 V + 2 V (49.7 V operating)",
                  notes="adjacent battery domains (and their HSU/HSL/LS/QFB children)")
    for k in CHANNELS:      # review MINOR-7: bootstrap children reach Vb + 13.5 V above their parent's reference
        for child, parent in ((f"CH{k}_HSU", f"B{k + 1}"), (f"CH{k}_HSL", f"B{k}")):
            d.barrier(parent, child, grade="functional", v_work=round(VB_OP + V12 + 1, 1), creepage_mm=0.6,
                      clearance_mm=0.6, standard=ipc, pollution_degree=2, material_group="IIIa",
                      source="B2 31-50 V: 0.6 mm [S]; BSTx/Gx reach Vb + 13.5 V (31 V operating) above the band "
                             "reference", notes="bootstrap domain against its own band")
    for a, b, m in (("B1", "B3", 3), ("B2", "B4", 3), ("B1", "B4", 4)):
        d.barrier(a, b, grade="functional", v_work=round(m * VB_OP + V12 + 2, 1), creepage_mm=1.5, clearance_mm=1.0,
                  standard=f"{ipc}; {f4}", pollution_degree=2, material_group="IIIa",
                  source=f"B2 51-100 V: 0.6 mm [S]; F.4 at <= 100 V: 1.4 mm [S]; design 1.5/1.0 mm margin "
                         f"(fails to a fuse, not to shock); worst {m} Vb + 14.5 V",
                  notes="non-adjacent battery domains")
    d.barrier("ISO", "B1", grade="basic", v_work=round(4 * VB_OP + V12 + 2 + 100, 0), creepage_mm=4.0,
              clearance_mm=4.0, standard="IEC 62368-1 ES2 to ES1 basic; IEC 60664-1 F.4 / F.2", v_test_rms=1061,
              pollution_degree=2, material_group="IIIa",
              source="F.4 PD2 MG IIIa at 200 V: 2.0 mm creepage [S]; F.2 1.5 kV impulse: 0.5 mm clearance [S]; "
                     "design 4.0/4.0 mm and no copper under U(k)10 (package >= 7 mm, CTI 175 [P]). v_work = stack "
                     "84 V + ALM_E +/-100 V (ASM-11); v_test 1.5 kV DC hi-pot (V-14) = 1.06 kVrms",
              notes="covers every stack domain (they all float on B1)")


def placement(d, ch, j1, j2, fuses, holes, blk_in, blk_al):
    pl = d.place
    doms = [d.domains[f"B{k}"] for k in (1, 2, 3, 4)]
    # -- board level ---------------------------------------------------------------------------------------
    pl.region(blk_in, "south", note="J1 centred on the south edge, F1-F5 just north of it")
    pl.region(blk_al, "corner-nw", note="J2 at the north-west corner inside the ISO strip")
    pl.edge(j1, "south")
    pl.orient(j1, "out", note="plug entry faces off the south edge")
    pl.edge(j2, "north")
    pl.orient(j2, "out")
    pl.near(j2, ch[1]["U10"], "loose")
    pl.array(fuses, "x", note="tap order T0..T4 west to east, like the bands")
    pl.near(j1, fuses[0], "close")
    pl.near(j1, fuses[4], "close")
    pl.custom("order", axis="x", direction="west_to_east", members=doms,
              note="potential-ordered floor plan: physical neighbours are electrical neighbours (H-3)")
    pl.array([ch[k]["block"] for k in CHANNELS], "x", note="three channel columns west to east, CH1 CH2 CH3")
    pl.custom("strip", edge="north", depth="8 mm", domain=d.domains["ISO"],
              note="reserved edge band for the alarm bus; optos straddle its south border")
    for bar in d.barriers:
        pl.separate(d.domains[bar.a], d.domains[bar.b], slot=False)
    for h in holes:
        pl.keepout(h, what="copper, 4.0 mm ring around the M3 hole", layers="all")
    pl.side("all", "top", note="all parts on the top side")
    for k in CHANNELS:
        channel_placement(d, ch[k], k)


def channel_placement(d, c, k):
    pl = d.place
    g = lambda *keys: [c[x] for x in keys]
    pl.custom("cluster", name=f"ch{k}.pwr", members=g("Q01", "Q02", "Q03", "Q04", "R01", "R52", "R02", "R53",
                                                  *[f"C{i:02d}" for i in range(1, 19)], "R03", "R04"))
    pl.custom("cluster", name=f"ch{k}.drv", members=g("U01", "U02", "R05", "R06", "R07", "R08", "R09", "R10", "R11",
                                                  "R12", "R13", "R14", "C19", "C20", *[f"C{i}" for i in range(21, 31)],
                                                  "D01", "D02", "R58", "R59"))
    pl.custom("cluster", name=f"ch{k}.osc", members=g("U03", "R15", "C31", "C32"))
    pl.custom("cluster", name=f"ch{k}.sup", members=g("U04", "U05", "U06", "R16", "R17", "R18", "R19",
                                                  *[f"C{i}" for i in range(33, 40)], "JP01", "Q06", "Q07", "R47",
                                                  "R48", "R49", "R50", "R51", "C50"))
    pl.custom("cluster", name=f"ch{k}.supv", members=g("U07", "U08", "U09", "U10", "U11", "Q05", "RT01", "D03", "D04",
                                                   "D05", "JP02", *[f"R{i}" for i in (54, 55, 56, 57, 60, 61, 62, 63)],
                                                   *[f"R{i}" for i in range(72, 80)], "C51", "C52", "C53", "C54",
                                                   *[f"R{i}" for i in range(20, 47)], *[f"C{i}" for i in range(40, 50)]))
    pl.custom("floorplan", block=c["block"],
              note=f"L side (B{k}: logic, lower half-bridge, Y) west; U side (B{k + 1}: upper driver, X) east")
    # PWR: 2x2 FET quad around the C_FLY bank, Y column west, X column east
    pl.array(g("Q03", "Q01"), "x")
    pl.array(g("Q04", "Q02"), "x")
    pl.align(g("Q03", "Q04"), "x")
    pl.align(g("Q01", "Q02"), "x")
    pl.array([c[f"C{i:02d}"] for i in range(1, 9)], "y", note="C_FLY bank between the FET columns")
    pl.symmetric([g("Q03", "Q01"), g("Q04", "Q02")], axis="v", note="mirror about the C_FLY centre line")
    for r in g("R01", "R52"):
        pl.near(r, c["Q01"]["S"][0], "tight")
        pl.near(r, c["C01"], "tight")
    for r in g("R02", "R53"):
        pl.near(r, c["Q03"]["S"][0], "tight")
        pl.near(r, c["C08"], "tight")
    for i in range(9, 13):
        pl.near(c[f"C{i:02d}"], c["Q01"]["D"], "tight")
        pl.near(c[f"C{i:02d}"], c["Q03"]["D"], "tight")
    for i in range(13, 17):
        pl.near(c[f"C{i:02d}"], c["Q02"]["S"][0], "tight")
        pl.near(c[f"C{i:02d}"], c["Q04"]["S"][0], "tight")
    q = lambda key, pin: c[key][pin] if not isinstance(c[key][pin], list) else c[key][pin][0]
    pl.hot_loop([c["C09"][1], q("Q01", "D"), q("Q01", "S"), c["R01"][1], c["R01"][2], c["C01"][1], c["C01"][2],
                 c["R02"][1], c["R02"][2], q("Q03", "S"), q("Q03", "D"), c["C09"][2]],
                note="phase 1: C_TOP -> Q_A -> R_CF -> C_FLY -> R_CF -> Q_C -> C_TOP (R52/R53 in parallel)")
    pl.hot_loop([c["C13"][1], q("Q02", "S"), q("Q02", "D"), c["R01"][1], c["R01"][2], c["C01"][1], c["C01"][2],
                 c["R02"][1], c["R02"][2], q("Q04", "D"), q("Q04", "S"), c["C13"][2]],
                note="phase 2: C_BOT -> Q_B -> X -> C_FLY -> Y -> Q_D -> T_L")
    pl.near(c["C17"], c["C09"], "close")
    pl.near(c["C18"], c["C13"], "close")
    pl.near(c["R03"], c["Q01"], "close")
    pl.near(c["R04"], c["Q03"], "close")
    for r in g("R01", "R52", "R02", "R53"):
        pl.thermal(r, round(numbers()["edge_rcf_each_hot"], 2), "copper", note="window edge only; normal <= 0.04 W")
    for fet in g("Q01", "Q02", "Q03", "Q04"):
        pl.thermal(fet, round(numbers()["edge_fet_hot"], 2), "copper + thermal vias")
    pl.far(c["RT01"], c["C17"], "close", note="NTC senses R_CF and FETs, not the bulk caps")
    pl.far(c["RT01"], c["C18"], "close")
    pl.near(c["RT01"], c["R01"], "close")
    pl.near(c["RT01"], c["Q01"], "close")
    pl.custom("pour", nets=[c["TL"], c["TM"], c["TH"], c["X"], c["Y"]], layers="F.Cu,B.Cu", min_width_mm=3,
              note="power and heat-spreading copper per net")
    # DRV
    pl.near(c["U01"], c["Q01"], "close")
    pl.near(c["U01"], c["Q02"], "close")
    pl.near(c["U02"], c["Q03"], "close")
    pl.near(c["U02"], c["Q04"], "close")
    for r, fet in (("R05", "Q01"), ("R06", "Q02"), ("R07", "Q03"), ("R08", "Q04")):
        pl.near(c[r], c[fet]["G"], "tight")
    for u, r, fet, out, ret in (("U01", "R05", "Q01", "OUTA", "VSSA"), ("U01", "R06", "Q02", "OUTB", "VSSB"),
                                ("U02", "R07", "Q03", "OUTA", "VSSA"), ("U02", "R08", "Q04", "OUTB", "VSSB")):
        pl.hot_loop([c[u][out], c[r][1], c[r][2], c[fet]["G"], q(fet, "S"), c[u][ret]], note="gate loop")
    pl.near(c["C29"], c["U01"]["VDDA"], "tight")
    pl.near(c["D01"], c["U01"]["VDDA"], "close")
    pl.near(c["C30"], c["U02"]["VDDA"], "tight")
    pl.near(c["D02"], c["U02"]["VDDA"], "close")
    pl.near(c["C21"], c["U01"]["VCCI"][0], "tight")
    pl.near(c["C22"], c["U01"]["VCCI"][0], "tight")
    pl.near(c["C23"], c["U02"]["VCCI"][0], "tight")
    pl.near(c["C24"], c["U02"]["VCCI"][0], "tight")
    pl.near(c["C25"], c["U01"]["VDDB"], "tight")
    pl.near(c["C27"], c["U02"]["VDDB"], "tight")
    pl.near(c["R13"], c["U01"]["DT"], "tight")
    pl.near(c["R14"], c["U02"]["DT"], "tight")
    for u in g("U01", "U02"):
        pl.keepout(u, what="copper under the package between pin rows 1-8 and 9-16 (isolation barrier)", layers="all")
        pl.pins_toward(u, ["INA", "INB", "GND", "DT"], "west",
                       note="input side faces the lower-potential side; outputs east toward the FETs")
    # OSC
    pl.near(c["U03"], c["U01"]["INA"], "close")
    pl.near(c["U03"], c["U02"]["INA"], "close")
    pl.custom("matched", nets=[c["PH1"], c["PH2"]], to=g("U01", "U02"), tolerance="loose",
              note="equal delay from U(k)03 to both drivers")
    pl.near(c["R15"], c["U03"][2], "tight")
    pl.near(c["C31"], c["U03"][1], "tight")
    pl.far(c["U03"], c["X"], "close")
    pl.far(c["U03"], c["Y"], "close")
    # SUP / SUPV: quiet corner of B(k), west of PWR
    pl.far(c["U08"], c["Q01"], "loose", note="divider nodes are 0.2-1 MOhm; keep them away from the switch nodes")
    pl.far(c["U08"], c["Q03"], "loose")
    pl.near(c["U04"], c["U02"], "close")
    pl.near(c["U05"], c["U01"], "close")
    pl.near(c["U08"], c["U07"], "close")
    for cap in g("C43", "C44", "C45", "C46", "C47"):
        pl.near(cap, c["U08"], "tight")
    pl.custom("connect_at", net=c["TH"], pins=[c["R20"][1], c["R26"][1], c["R30"][1]], at=c["C09"][1],
              note="sense taps at the C_TOP pads, channel side of the fuses")
    pl.custom("connect_at", net=c["TM"], pins=[c["R34"][1]], at=c["C13"][1])
    pl.custom("connect_at", net=c["TL"], pins=[c[x][2] for x in ("R24", "R25", "R28", "R29", "R32", "R33", "R36",
                                                                  "R37")], at=c["C13"][2])
    pl.custom("guard", nets=[c["PON"], c["PLO"], c["PHI"], c["N"]], ring=c["TL"],
              note="guard ring at T_L around the high-impedance divider nodes")
    pl.near(c["Q06"], c["Q07"], "loose")
    pl.near(c["Q07"], c["U05"], "close")
    pl.custom("row", members=g("D03", "D04", "JP01"), where="just south of the ISO strip",
              note=f"silkscreen 'CH{k} ACT / FLT / EN(N>={k + 1})'")
    pl.align(g("D03", "D04", "JP01"), "y")
    pl.near(c["U10"], c["D03"], "close")
    pl.custom("straddle", part=c["U10"], domains=[d.domains[f"B{k}"], d.domains["ISO"]],
              note="opto bridges the 4 mm ISO barrier; no copper under its body")
    pl.pins_toward(c["U10"], ["C", "E"], "north", note="output side into the ISO strip")


def board(d):
    holes = [Hole(5, 5, 3.2, note="H1, M3 on nylon standoff"), Hole(175, 5, 3.2, note="H2"),
             Hole(5, 125, 3.2, note="H3"), Hole(175, 125, 3.2, note="H4")]
    d.board(width_mm=180, height_mm=130, layers=4, thickness_mm=1.6, copper_oz=2, holes=holes,
            max_component_height_mm=25,
            enclosure="IP54 polycarbonate wall box ~250 x 200 x 90 mm, M20 gland for the harness (bottom), M12 for "
                      "the alarm; LEDs behind a clear lid; mounted beside the rack, outside any battery box, not "
                      "above vents",
            coating="",
            keepouts=[{"rect": [0, 122, 180, 130], "what": "copper of any domain except ISO", "layers": "all",
                       "note": "8 mm ISO strip along the north edge (BoardSpec origin is the lower-left corner, "
                               "y up, so y 122-130 is north)"},
                      {"relative": "4.0 mm ring around each mounting hole", "what": "copper", "layers": "all"}],
            notes="Coordinates: origin at the lower-left corner, x east, y north (kaesynth BoardSpec). Board grew "
                  "from 160 x 110 mm for the five 43 x 18 mm 10x38 fuse holders. "
                  "FR-4 CTI >= 175 (IIIa), 2 oz outer / 1 oz inner; all parts top side; no heatsink, power copper "
                  "poured on L1/L4 per net with thermal vias under Q_A-Q_D and R_CF. Uncoated (Q-9).")


def waivers(d):
    n = numbers()
    i_end, i_mid = n["edge_I_cold"], 2 * n["edge_I_cold"]
    W = d.waive
    W("rating.current", r"^F[234] \(6A\)",
      f"Middle tap fuses at the abnormal ratio-window edge: {i_mid:.1f} A worst case ({i_mid / 6:.0%} of the 6 A "
      "KLKD006; failing battery, worst tolerances, 17.55 V, -20 C; calc edge_middle_tap_A). Normal operation "
      "(dV <= 0.5 V) is <= 2.0 A (33 %). At the edge the fuse opening is a safe end state: the tap opens, the next "
      "tap-check pause trips the window and the fail-safe alarm opens. A larger fuse would weaken selectivity "
      "against the KLKD010 (calc fuse_selectivity_ratio).")
    W("rating.current", r"^FH[0-4] \(10A\)",
      f"KLKD010 at the abnormal window edge: {i_mid:.1f} A worst ({i_mid / 10:.0%} of 10 A; a fuse carries 100 % "
      "of its rating continuously); normal <= 2.0 A (20 %).")
    W("rating.power", r"^R[123](01|02|52|53) \(0.086\)",
      f"R_CF at the abnormal window edge, 50 C ambient: {n['edge_rcf_each_hot']:.2f} W each "
      f"({n['edge_rcf_each_hot'] / 2:.0%} of 2 W at 70 C; {n['edge_rcf_each_hot'] / n['rcf_rating_99C']:.0%} of the "
      f"{n['rcf_rating_99C']:.2f} W rating at the 99 C cut-out; calc edge_rcf_each_hot_W). REQ-24: <= 100 % of the "
      "temperature-derated rating when abnormal. Normal operation (dV <= 0.5 V) <= 0.05 W each. This is why each "
      "position has two 0.086 Ohm parts in parallel instead of one 0.043 Ohm part.")
    W("rating.voltage", r"^RT[123]01 ",
      "NCP15 'maximum voltage' 5.00 V is Murata's self-heating limit (spec note *4). The NTC sees 5.05 V only when "
      "cold (R_NTC >= 6 MOhm below -20 C), where it dissipates < 5 uW (< 0.002 K self-heating); at the 95 C trip "
      "it has 2.5 V and 0.25 mW.")
    W("rating.voltage", r"^U[123]06 \(TPS70950DBVR\): V\(EN-GND\)",
      "EN is left floating with only C(k)39 to GND, which SBVS186H Table 5-1 allows ('can be left floating to "
      "enable'; must stay below 6.5 V). The self-biased level of the internal 300 nA pull-up is not published, so "
      "the net envelope is the 6.5 V recommended maximum (93 % of the 7 V absolute maximum); nothing drives EN "
      "higher.")
    if N_BATT < 4:
        W("protect.threat", r"BR[1-4] sit on the wire side",
          "The plug bridge BRj is a link inside P1 from an unused position to TAP(N)_IN, downstream of the harness "
          "fuse FH(N) at the battery; it carries only divider/sleep current (uA). Its wire side is protected by FH(N).")
        W("protect.entry_fuse", r"BR[1-4] connect on the wire side", "Same as the plug-bridge threat waiver.")
    W("hazard.procedural", r"^H-6:",
      "Hydrogen ignition is controlled by where the enclosure is installed (outside the battery box, not above "
      "vents) and by having no relays or user-operated contacts on the board; installation rule in DESIGN.md 9.")
