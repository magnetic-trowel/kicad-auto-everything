# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Part and net roles from what a .kicad_pcb states: names, values, footprints, lib ids, pin
functions and types, fields, net classes and connectivity. Never positions.

Part roles come in two steps.
1. Kind (what the part is): a softmax over per-kind evidence scores from the reference
   prefix, lib id, value, Description/MPN fields, pin names and count, and attributes, with an
   explicit 'unknown' class. Kinds: resistor, resistor_array, capacitor, inductor, ferrite,
   common_mode_choke, transformer, diode, led, transistor, ic, crystal, oscillator,
   connector, antenna, test_point, mounting_hole, fiducial, switch, heatsink, jumper, net_tie,
   fuse, battery, buzzer, microphone, relay, potentiometer, thermistor, varistor,
   optocoupler, module, graphic, mechanical. A subtype refines it (schottky, tvs, esd_array,
   zener, rectifier, signal; nmos, pmos, npn, pnp; linear/switching/module regulator, mcu,
   fpga, memory, phy, opamp, ...; usb, power, header, rf, ethernet, audio, debug, ... for
   connectors).
2. Role (what it does on this board), from its nets: a capacitor between a rail and ground is
   decoupling or bulk by value and body; a resistor at or below 0.2 ohm (or a 4-terminal
   body) is a shunt; a resistor pair from a node to a rail and to ground is a divider; and so
   on. structures.py refines roles for parts that belong to a structure.

Net roles: ground (signal, analog, power, chassis, isolated), rails with a voltage
Belief (name, regulator part number, USB, battery; capacitor ratings bound it), switch
nodes, clocks, high-speed nets and differential pairs (by interface), analog-sensitive nets,
RF, reset and boot, and general signals with an interface tag. Each net gets one primary
role (priority ground > rail > switch_node > rf > clock > high_speed > analog > reset/boot
> signal) and keeps the others as tags.

All decisions carry `Evidence` (evidence.py); confidences are logistic in summed log odds.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import values as V
from .evidence import MODERATE, STRONG, WEAK, Evidence, confidence, ev, softmax_pick
from .netlist import Netlist, Part, Pin

# =============================================================================== keyword tables
I = re.I


def rx(p, flags=I):
    """Compile a pattern; rx(0, pattern) compiles it case-sensitively (lib ids are CamelCase, and
    case-insensitive substrings misfire: 'ExtraFootprints' contains 'traFo')."""
    if isinstance(p, int):
        p, flags = flags, p
    return re.compile(p, flags)


# reference-designator prefix -> {kind: weight}
PREFIX = {
    'C': {'capacitor': 2.5}, 'CP': {'capacitor': 2.0}, 'CE': {'capacitor': 1.5}, 'CIN': {'capacitor': 2.0},
    'COUT': {'capacitor': 2.0},
    'R': {'resistor': 2.5}, 'RS': {'resistor': 1.5}, 'RSH': {'resistor': 2.0},
    'RN': {'resistor_array': 2.5}, 'RA': {'resistor_array': 1.5}, 'RR': {'resistor_array': 1.5},
    'L': {'inductor': 2.0, 'ferrite': 0.7}, 'FB': {'ferrite': 3.0}, 'FL': {'ferrite': 1.0, 'common_mode_choke': 1.0},
    'D': {'diode': 2.0, 'led': 0.8}, 'CR': {'diode': 1.5}, 'VD': {'diode': 1.5}, 'ZD': {'diode': 2.0}, 'DZ': {'diode': 2.0},
    'TVS': {'diode': 2.5}, 'ESD': {'diode': 2.5},
    'LED': {'led': 3.0}, 'LD': {'led': 1.5}, 'DL': {'led': 1.5}, 'DS': {'led': 1.5},
    'Q': {'transistor': 2.0}, 'T': {'transformer': 1.2, 'transistor': 0.8}, 'TR': {'transformer': 1.0, 'transistor': 1.0},
    'VT': {'transistor': 2.0}, 'FET': {'transistor': 2.5}, 'M': {'module': 0.5, 'mechanical': 0.5},
    'U': {'ic': 2.5}, 'IC': {'ic': 2.5}, 'Z': {'ic': 0.7}, 'N': {'ic': 0.5}, 'DA': {'ic': 1.0}, 'DD': {'ic': 1.0},
    'VR': {'ic': 1.0, 'potentiometer': 1.0}, 'PS': {'ic': 1.0, 'module': 1.0}, 'REG': {'ic': 2.0},
    'Y': {'crystal': 2.5, 'oscillator': 1.0}, 'XTAL': {'crystal': 3.0}, 'X': {'crystal': 0.8, 'connector': 0.8, 'oscillator': 0.4},
    'XT': {'crystal': 2.0}, 'OSC': {'oscillator': 3.0}, 'XO': {'oscillator': 2.0}, 'G': {'graphic': 0.8},
    'J': {'connector': 2.5}, 'P': {'connector': 1.5}, 'CN': {'connector': 2.5}, 'CON': {'connector': 2.5},
    'CONN': {'connector': 2.5}, 'USB': {'connector': 2.0}, 'JK': {'connector': 2.0}, 'XS': {'connector': 2.0},
    'XP': {'connector': 2.0}, 'J_P': {'connector': 2.0}, 'PWR': {'connector': 1.0}, 'TB': {'connector': 2.0},
    'TP': {'test_point': 3.0}, 'H': {'mounting_hole': 2.0}, 'MH': {'mounting_hole': 3.0}, 'HOLE': {'mounting_hole': 3.0},
    'MTG': {'mounting_hole': 3.0}, 'ST': {'mounting_hole': 1.0},
    'FID': {'fiducial': 3.0}, 'FD': {'fiducial': 2.0}, 'REF': {'graphic': 1.0},
    'SW': {'switch': 2.5}, 'S': {'switch': 1.5}, 'BTN': {'switch': 2.5}, 'KEY': {'switch': 2.0}, 'KSW': {'switch': 2.5},
    'SWA': {'switch': 1.5}, 'SWB': {'switch': 1.5}, 'SWC': {'switch': 1.5}, 'SWD': {'switch': 1.0}, 'RSW': {'switch': 2.0},
    'K': {'relay': 2.0, 'switch': 0.5}, 'RL': {'relay': 1.5}, 'RLY': {'relay': 2.5},
    'JP': {'jumper': 2.5}, 'SJ': {'jumper': 2.5}, 'W': {'jumper': 1.5}, 'NT': {'net_tie': 3.0},
    'F': {'fuse': 2.5}, 'FU': {'fuse': 2.5}, 'PTC': {'fuse': 2.0}, 'PF': {'fuse': 1.5},
    'BT': {'battery': 2.5}, 'BAT': {'battery': 2.0, 'connector': 0.8},
    'BZ': {'buzzer': 2.5}, 'LS': {'buzzer': 2.0}, 'SPK': {'buzzer': 2.0}, 'MK': {'microphone': 2.5}, 'MIC': {'microphone': 2.5},
    'RV': {'potentiometer': 2.0, 'varistor': 0.8}, 'POT': {'potentiometer': 2.5},
    'TH': {'thermistor': 1.5}, 'RT': {'thermistor': 1.5}, 'NTC': {'thermistor': 2.5},
    'AE': {'antenna': 3.0}, 'ANT': {'antenna': 3.0}, 'E': {'antenna': 0.5},
    'HS': {'heatsink': 3.0}, 'A': {'module': 1.0}, 'MOD': {'module': 2.0}, 'SH': {'mechanical': 1.5}, 'MCU': {'ic': 1.5, 'module': 1.0},
    'OK': {'optocoupler': 2.0}, 'OC': {'optocoupler': 1.5}, 'ISO': {'optocoupler': 1.0, 'ic': 1.0},
    'LOGO': {'graphic': 3.0}, 'KIBUZZARD': {'graphic': 3.0}, 'GRAPHIC': {'graphic': 3.0},
}

# (kind, subtype or None, weight, regex on value/MPN/description text)
TEXT_RULES = [
    # capacitors
    ('capacitor', None, 2.0, rx(r'\bcapacitor\b|\bcap(acitor)?\s+(cer|ceramic|tant|alu|elec)|\bMLCC\b|unpolari[sz]ed cap|polari[sz]ed cap')),
    ('capacitor', None, 1.5, rx(r'\b(GRM|GCM|CL\d{2}[ABC]|C\d{4}X\d|CC\d{4}|EMK|JMK|LMK|TMK|UMK|C1005|C1608|C2012|C3216|'
                                 r'CGA\d|GJM|EEE-|EEU-|UVR|UWT|T491|T520|TAJ[A-E]|TPS[A-E]\d)\w*', 0)),
    # resistors
    ('resistor', None, 2.0, rx(r'\bresistor\b|\bthick film\b|\bthin film\b|\bres\s+(smd|thick|thin|0402|0603|0805)')),
    ('resistor', None, 1.5, rx(r'\b(RC\d{4}|ERJ-?\w+|CRCW\d+|RMCF|WR\d{2}|ERA-|RK73|MCR\d{2}|CR\d{4}-|0402WGF|0603WAF|'
                                r'RT0402|RT0603|RC0402|RC0603)', 0)),
    ('resistor', 'shunt', 2.0, rx(r'\bshunt\b|current sense res|\bWSL\d|\bWSK\d|\bWSR\d|\bCSR\d|\bPMR\d|\bLRMAP|\bKRL\d|\bCSS\d|\bULR\d|\bERJ-?\w*M\w*|Kelvin')),
    # inductors, beads, chokes, transformers
    ('inductor', None, 2.0, rx(r'\binductor\b|power ind|\bIHLP|\bSRP\d|\bSRN\d|\bSRR\d|\bXAL\d|\bXFL\d|\bMAPI|\bCD5\d|\bSWPA\d|'
                                r'\bASPI|\bLQH\d|\bLQM\d|\bNR\d{4}|\bVLS\d|\bDFE\d|\bTFM\d|\bMLZ\d|\bLPS\d|\bME3220|\bYSRH|\bWE-?P|\bSER29|'
                                r'\bCBW\d|\bLMSC\d|\b744\d{3}')),
    ('inductor', 'rf', 1.0, rx(r'\bLQW\d|\bLQG\d|\bLQP\d|\b0402CS|\b0603CS|\bL-07C|\bLL1005|\bLQW15')),
    ('ferrite', None, 3.0, rx(r'ferrite|\bbead\b|\bBLM\d|\bMPZ\d|\bBK\d{4}|\bHZ\d{4}|\bFBMH|\bMMZ\d|\bBLA\d|\bHI\d{4}|\bMI\d{4}|'
                               r'\bPE-\d{4}PFB|\bFB_\d|\bWE-CBF|\bUPZ\d|\bCIM\d|\bBKP\d|\bCBW\d{6}|\bGZ\d{4}|\bSBY\d|'
                               r'\b\d+\s*(R|Ω|ohm|Ohm|OHM|Z)\s*@|@\s*100\s*MHz')),
    ('common_mode_choke', None, 3.0, rx(r'common.?mode|\bCMC\b|\bACM\d|\bDLW\d|\bDLP\d|\bWE-CNSW|\bSRF\d{4}|\bACT45|\bCMM\d|\bMCZ\d')),
    ('transformer', None, 2.5, rx(r'transformer|\btrafo\b|\bpulse transformer|\bmagnetics\b|\bHX\d{4}|\bH1102|\bHR6\d{4}|\bTL016')),
    # diodes
    ('diode', 'schottky', 3.0, rx(r'schottky|\bBAT\d{2}|\bBAS40|\bSS\d{2,3}\b|\bSK\d{2,3}|\bSM5819|\b1N58\d{2}|\bMBRS?\d|\bPMEG\d|'
                                   r'\bSBR\d|\bSTPS\d|\bRB\d{3}|\bCUS\d|\bBS5817|\bSSA\d{2}|\bSKL\d|\bVSS\d|\bNSR\d|\bCDBA|\bDSS\d|'
                                   r'\bB\d{3,4}(-13|W|LW)?\b|\bSBRT|\bPDS\d|\bSL\d{2}\b|\bXBS\d|\b1N5817|\b1N5819')),
    ('diode', 'tvs', 3.0, rx(r'\bTVS\b|transient|\bSMAJ|\bSMBJ|\bSMCJ|\bSMF\d|\bP6KE|\bP4SMA|\b1\.5KE|\bSMDJ|\bSZ\w*\d|\bSLVU|'
                              r'\bLXES|\bSD\d{2}C?\b|\bPESD\d|\bESDA\d|\bESD\d{1,2}[A-Z]|\bD5V0|\bCDSOD|\bH5V|\bNSPM|\bSMS\d|\bTVS\d|'
                              r'\bSP\d{4}|\bGBLC|\bESD5|\bCESD|\bMMBZ|\bSMAZ|\bTPSMA|\bSMBZ|\bUCLAMP|\bDT1042|\bESDLC|\bLC03')),
    ('diode', 'esd_array', 3.0, rx(r'\bUSBLC\d|\bTPD\d+E|\bESD\d{3}|\bPRTR5V|\bRCLAMP|\bSRV05|\bIP42\d{2}|\bNUP\d|\bSP05\d|'
                                    r'\bTPD\d[A-Z]|\bCM1213|\bESDA6|\bSRDA|\bPGB\d|\bNUF\d|\bECMF|\bESD7|\bTPD2|\bTPD4|\bPESD2CAN|'
                                    r'\bLCDA|\bULC\d|\bSMF05|\bCDDFN|\bH5VU|\besd protection|ESD array')),
    ('diode', 'zener', 2.5, rx(r'zener|\bBZX\d|\bBZT\d|\bMMSZ|\bBZV\d|\bMM3Z|\bDZ2|\b1N47[2-6]\d|\bTZM|\bBZB\d|\bMMBZ52|\bPDZ\d|\bUDZ')),
    ('diode', 'rectifier', 2.0, rx(r'\brectifier\b|\b1N400\d|\b1N540\d|\bS1[A-M]\b|\bUS1[A-M]|\bES[12][A-J]\b|\bMURS?\d|\bUF400\d|'
                                   r'\bRS1[A-M]|\bGS1[A-M]|\bSM4007|\bSOD4007|\bFR10\d|\bRL20\d|\bM7\b|\bUS2[A-M]|\bES1D|\bSF\d{2}\b')),
    ('diode', 'signal', 2.0, rx(r'switching diode|small signal|\b1N4148|\b1N914|\bBAV\d{2}|\bBAS\d{2,3}|\bBAW\d{2}|\b1SS\d|\bLL4148|'
                                r'\bMMBD\d|\bLBAV|\b4148\b')),
    ('diode', 'bridge', 2.5, rx(r'bridge rectifier|\bMB\d{1,2}[SF]\b|\bDB\d{3}|\bKBP\d|\bGBU\d|\bABS\d{1,2}\b|\bDF\d{2}S?\b|\bHD0\d')),
    ('diode', None, 1.5, rx(r'\bdiode\b')),
    ('led', None, 3.0, rx(r'light emitting|\bLED\b|\bWS2812|\bSK6812|\bSK6805|\bAPA102|\bAPA107|\bLTST|\bKP-\d|\bKPH-|\bAPT\d{4}|\bSML-|'
                           r'\bOSK\d|\bNCD\d{4}|\bLTE-|\bTLPR|\bRGB\b|\bXTEAWT|\bAPHB|\bORH-')),
    ('led', None, 1.5, rx(r'^(RED|GREEN|BLUE|YELLOW|WHITE|AMBER|ORANGE|GRN|YLW|BLU|RLED|GLED|BLED)\b')),
    ('led', None, 0.6, rx(r'^(PWR|POWER|STATUS)\b')),
    # transistors
    ('transistor', 'nmos', 2.5, rx(r'N-?MOS|N-?ch(annel)?\b|\b2N7002|\bBSS138|\bBSS123|\bAO3400|\bAO34[01][02]\b|\bIRLML(2502|0030|6244|2060)|'
                                   r'\bSI2302|\bSI2300|\bDMN\d|\bDMG1012|\bNTR4\d|\bFDN3[35]\d|\bFDC3601|\bCSD\d{5}|\bBSC\d{3}N|\bIPT\d{3}N|'
                                   r'\bIPB\d{3}N|\bIPD\d{3}N|\bPMV\d{2}EN|\bPMZ\d{3}UN|\bBS170|\bIRF\w*\d|\bIRL[BRSZ]\d|\bEPC\d{4}|\bAON\d|'
                                   r'\bSQ\d{4}EN|\bBUK\d|\bPSMN|\bNVMFS|\bNTMFS|\bMMBT7002|\bDMN10H|\bPMV50ENE|\bRQ\dE|\bAOD4\d\d\b')),
    ('transistor', 'pmos', 2.5, rx(r'P-?MOS|P-?ch(annel)?\b|\bBSS84|\bAO3401|\bAO3407|\bIRLML(6402|6401|9301)|\bSI230[17]|\bSI2305|\bDMP\d|'
                                   r'\bDMG2305|\bDMG3415|\bFDN3[0-4]\dP|\bNTR1P|\bPMZB\d{3}UP|\bAOD403|\bSIA445|\bZXMP\d|\bBC2301|\bIRF9|\bSI4435|'
                                   r'\bFDS\d{4}P|\bAO4407')),
    ('transistor', 'npn', 2.5, rx(r'\bNPN\b|\b2N3904|\b2N2222|\bMMBT3904|\bMMBT2222|\bBC8[1-4]\d|\bBC54[6-9]|\bBC23[7-9]|\bBC18[2-4]|\bS8050|\bS9013|'
                                  r'\bPMBT3904|\bMPSA4[2-4]|\bBCX5[456]|\bTIP\d{2}\b|\bBD13\d|\bMJD\d{2}|\bMBT3904|\bLBC846|\bBCV27')),
    ('transistor', 'pnp', 2.5, rx(r'\bPNP\b|\b2N3906|\b2N2907|\bMMBT3906|\bMMDT3906|\bBC8[5-6]\d|\bBC80[7-8]|\bBC5[5-6]\d|\bBC30[7-9]|\bS8550|\bS9012|'
                                  r'\bMPSA9[2-3]|\bBCX5[1-3]|\bBCM857|\b3906\b|\bHN4A56')),
    ('transistor', None, 2.0, rx(r'\bMOSFET\b|\btransistor\b|\bBJT\b|\bIGBT\b|\bFET\b')),
    # crystals, oscillators
    ('crystal', None, 3.0, rx(r'\bcrystal\b|\bquartz\b|\bresonator\b|\bXTAL|\bABM\d|\bABS\d{2}|\bECS-\d{2,3}|\bTSX-?\d|\bCX3225|\bFA-\d{3}|'
                               r'\bNX\d{4}|\bFC-\d{3}|\b7A-\d|\bYIC-|\bASEK|\bQ\d+(\.\d+)?MHz|\bCrystal_GND')),
    ('oscillator', None, 3.0, rx(r'oscillator|\bTCXO\b|\bVCXO\b|\bOCXO\b|\bMEMS osc|\bASE-|\bASDM|\bDSC\d{4}|\bSIT\d{4}|\bSG-?\d{3}|'
                                  r'\bKC2520|\bOB3225|\bECS-\d{4}MV|\bASFL|\bCB3LV|\bASV-|\bFXO-|\b512MLF|\bSi5\d{2}\b')),
    # connectors and friends
    ('connector', None, 2.5, rx(r'\bconn(ector)?\b|Conn_\d|\bheader\b|\breceptacle\b|\bplug\b|\bbarrel\b|\bterminal block|\bscrew terminal|'
                                 r'\bjack\b|\bUSB_?[ABC]\b|USB_C_|\bmicro.?SD\b|\bRJ45\b|\bDB\d{1,2}\b|\bDSUB|\bD-SUB|\bIDC\b|\bFFC\b|\bFPC\b|'
                                 r'\bJST\b|\bMolex\b|\bPinHeader|\bPinSocket|\bPin_Header|\bSocket_Strip|Conn_0\dx|CONN_\d|\bSMA\b|\bU\.?FL\b|'
                                 r'\bMMCX\b|\bBNC\b|\bMagJack\b|\bHDMI\b|\bSODIMM\b|\bM\.2\b|\bFMC\b|\bTag-?Connect|\bTC20[35]0|\bSFP\b')),
    ('antenna', None, 3.0, rx(r'\bantenna\b|\bANT[-_ ]\w|\b2450AT|\bW3\d{3}\b|\bAH316|\bchip ant|\bPCB_?ant|\bRF_Antenna')),
    ('test_point', None, 3.0, rx(r'\btest.?point\b|\btest.?pad\b|^TP\d*$|\bTestPoint')),
    ('mounting_hole', None, 3.0, rx(r'mounting.?hole|\bMountingHole|\bSCREWHOLE|\bScrew.?hole|\bstandoff\b|\bMTG\d|\bPLATED_HOLE|\bTooling_Hole|'
                                     r'\bClearanceHole|^Hole$|^H$|^M[2-6]$')),
    ('fiducial', None, 3.5, rx(r'\bfiducial\b|^FID\d*$')),
    ('switch', None, 2.5, rx(r'\bswitch\b|\bbutton\b|\bpush.?button|\btactile\b|^SW_|\bSW_Push|\bSW_SPDT|\bencoder\b|\bKailh|\bCherry\b|\bchoc\b|'
                              r'_SW\b|^SW\d*$|\bS[PD][DS]T\b|\bDP\dT\b|\bslide\b|\btoggle\b|\bDIP.?SW|'
                              r'\bTL3305|\bSKRK|\bTASV|\bSKQG|\bEVQ|\bPTS\d{3}')),
    ('heatsink', None, 3.5, rx(r'heat.?sink|\bHEATSINK')),
    ('jumper', None, 2.5, rx(r'\bjumper\b|SolderJumper|\bJumper_|^JP\d*$|^SJ\d*$')),
    ('net_tie', None, 3.5, rx(r'net.?tie|NetTie')),
    ('fuse', None, 3.0, rx(r'\bfuse\b|\bpolyfuse\b|\bPTC\b|\bMF-MSMF|\bnSMD\d|\bmSMD\d|\b0ZCJ|\b0ZCG|\bMF-R\d|\b1812L\d|\bSMD\d{3}P|\bPTCR|\bresettable')),
    ('battery', None, 3.0, rx(r'\bbattery\b|\bCR2032|\bCR\d{4}\b|\bcell holder|\bCellHolder|\bBatteryHolder|\bBattery_Cell')),
    ('buzzer', None, 3.0, rx(r'\bbuzzer\b|\bbeeper\b|\bspeaker\b|\bpiezo\b|\bPS1240|\bCMI-\d|\bCMT-\d')),
    ('microphone', None, 3.0, rx(r'microphone|\bMEMS mic|\bSPH0\d|\bSPK0\d|\bICS-\d{5}|\bCMC-\d{4}|\bMic_')),
    ('relay', None, 3.0, rx(r'\brelay\b|\bSRD-\d|\bG5V|\bG6K|\bHF\d{2}F|\bTQ2|\bAQY\d')),
    ('potentiometer', None, 3.0, rx(r'potentiometer|\btrimmer\b|\btrimpot|\bR_POT|\b3296W|\b3362P|\b3266W|\bRV09|\bAlpha_RV')),
    ('thermistor', None, 3.0, rx(r'thermistor|\bNTC\b|\bNTCG|\bNCP\d{2}[XW]|\b\d+k\s*\d{4}K\b|\bB57\d{3}')),
    ('varistor', None, 3.0, rx(r'varistor|\bMOV\b|\bMOV-|\bV\d{2,3}E|\bS\d{2}K\d')),
    ('optocoupler', None, 4.0, rx(r'opto.?coupler|optoisolator|photocoupler|solid.?state relay|PhotoMOS|\bPC817|\b6N13[5-9]|\bTLP\d{3}|\bH11[A-L]\d|\b4N2[5-8]|\b4N3[5-7]|'
                                   r'\bMOC\d{4}|\bGAQY|\bEL817|\bPS2501|\bVTL5C|\bLTV-?\d|\bSFH\d{3}|\bACPL|\bHCPL|\bVO\d{3,4}')),
    ('module', None, 3.0, rx(r'\bmodule\b|\bWROOM|\bWROVER|\bESP32-[A-Z0-9]+-MINI|\bMINI-1|\bESP-\d{2}|\bXIAO|\bRPi_Pico|^Pico\w*$|\bArduino|'
                              r'\bWeMos|\bDevKit|\bbreakout|\bXBEE|\bXB24|\bNORA-|\bBL54L|\bRFM9\d|\bSIM\d{3,4}|\bProMicro|\bRP2040-Zero|'
                              r'\bDFPlayer|\bMini360|\bSC14CVMDECT|\bmikoto|\bSAMD21_breakout|SUPERMINI|\bHC-0\d|\bnRF52\d{2}-\w*module')),
    ('graphic', None, 2.5, rx(r'\blogo\b|\bOSHW\b|\bWEEE\b|\bROHS\b|\bkibuzzard|\bQRCode|\bgraphic|\bSign_|\bLONGTHING|\bart\b|\bCreative_Commons')),
    ('mechanical', None, 1.5, rx(r'\bMECHANICAL\b|\bPCM_kikit:Board|\bpanel|\bmouse.?bite|\bcutout')),
]

LIB_RULES = [
    ('capacitor', 3.0, rx(0, r'(^|:)(C|CP|CAP)_|Capacitor|CAP[CM]\d{4}|EIA_\d{4}_CAP|Cap_|_Elec_|C_Elec|Capacitors|CP_Radial|C_Disc|C_Rect')),
    ('resistor', 3.0, rx(0, r'(^|:)R_(?!Array|Pack|POT)|Resistor(?!_Array)|RES[CM]\d{4}|EIA_\d{4}_RES|Resistors')),
    ('resistor_array', 3.0, rx(0, r'R_Array|Resistor_Array|R_Pack|Resistor_Pack|ARRAY|CAY16|_Array_')),
    ('inductor', 2.5, rx(0, r'(^|:)L_|Inductor|IND[CM]?\d{4}|IND_|EIA_\d{4}_INDUCTOR|IHLP|SRP\d|SRN\d|SRR\d|CD5\d|SWPA|Coil|INDC|HSMRH|SMDRI')),
    ('ferrite', 3.0, rx(0, r'Ferrite|(^|:)FB_\d|Bead')),
    ('common_mode_choke', 3.0, rx(0, r'CommonMode|Choke_Common|L_CommonMode|CMC_')),
    ('transformer', 3.0, rx(0, r'Transformer|Trafo|PulseTransformer|Audio_transformer')),
    ('diode', 2.5, rx(0, r'(^|:)D_|Diode|SOD-?\d{2,3}|(^|[_:])SMA(_|$)|(^|[_:])SM[BC](_|$)|DO-?\d{2}|MELF|DO214|SMA-KA|SOD\d{3}|D_SMA|Diodes_SM')),
    ('led', 3.0, rx(0, r'(^|:)LED|LED_|_LED|WS2812|SK6812|SK6805|APA102|PLCC.?\d|LED-\d')),
    ('transistor', 1.0, rx(0, r'Package_TO_SOT|SOT-?23|SOT-?323|SOT-?523|TO-92|TO-220|TO-252|TO-263|D2PAK|DPAK|PowerPAK|PowerDI|LFPAK|SOT-?89|'
                           r'SOT-?223|SC-?70|PG-HSOF|TDSON|SuperSO|Transistor')),
    ('ic', 1.5, rx(0, r'Package_(SO|QFP|DFN_QFN|BGA|DIP|SON|CSP|LGA|PLCC|SIP)|SOIC|SSOP|TSSOP|MSOP|QFN|DFN|LQFP|TQFP|PQFP|BGA|WSON|USON|VSON|'
                   r'VQFN|WQFN|UQFN|LGA-\d|LFCSP|TSOT|PLCC|SOP-?\d|DIP-\d|WLCSP|XQFN|XSON|SON\d|QFP')),
    ('crystal', 3.0, rx(0, r'Crystal|Resonator|XTAL|(^|:)Q_|Quartz')),
    ('oscillator', 3.0, rx(0, r'Oscillator|(^|:)OSC|_OSC|TCXO|VCXO')),
    ('connector', 3.0, rx(0, r'Connector|connector|Conn_|CONN|_jst_|jst_ph|jst_sh|PinHeader|PinSocket|Pin_Header|Socket_Strip|TerminalBlock|Terminal_|BarrelJack|DC_?Jack|'
                          r'(^|[_:])USB|Jack_|_Jack|AudioJack|RJ45|RJ11|MagJack|Coax|(^|[_:])SMA_|U\.?FL|IPEX|MMCX|BNC|SMPM|DSUB|D-Sub|IDC-|JST|'
                          r'Molex|Phoenix|Hirose|HRS_|FFC|FPC|microSD|SD_?Card|SDCARD|SIM_|M\.2|PCIe|PCBEdge|PCB-Edge|SODIMM|Tag-Connect|TC20[35]0|'
                          r'Samtec|FTSH|SHF|HDR-|SolderWirePad|Solderpad|WirePad|Wire_Pads|XT30|XT60|Harwin|Keystone5|MIDI|DIN5|XLR|SCART|HDMI|'
                          r'DisplayPort|SFP|QSFP|CardEdge|FMC|USB-C|TYPE-C|MINI-USB|Eurorack_Power|FanPinHeader|Power_Jack|JACK_ALIM|'
                          r'powertab|SolderPads|Socket|_Plug|Receptacle|Header')),
    ('antenna', 3.5, rx(0, r'RF_Antenna|Antenna|(^|[_:])ANT_|_ANT(_|$)|PCB_Antenna')),
    ('test_point', 3.5, rx(0, r'TestPoint|Test_Point|(^|:)TP_|TestPad')),
    ('mounting_hole', 4.0, rx(0, r'MountingHole|Mounting_Hole|MTG\d|SCREWHOLE|ClearanceHole|_Clearance_|Tooling_Hole|Standoff|(^|:)Hole|MECHANICAL_CLEARANCE|MTG_|DrillHole|(^|:)M[2-6]_|PanelHole_Bourns')),
    ('fiducial', 3.5, rx(0, r'Fiducial')),
    ('switch', 3.0, rx(0, r'Button_Switch|(^|:)SW_|Switch|_switch|switch_|button|Tactile|TASV|TL3305|SKRK|choc|Kailh|Cherry|MX_|Rotary_Encoder|Encoder|Slide')),
    ('heatsink', 3.5, rx(0, r'Heatsink|HEATSINK|Heat_Sink')),
    ('jumper', 3.0, rx(0, r'Jumper|SolderJumper|SolderBridge')),
    ('net_tie', 3.5, rx(0, r'NetTie|Net_Tie')),
    ('fuse', 3.0, rx(0, r'(^|:)Fuse|Fuse_|PTC_|Polyfuse|Littelfuse')),
    ('battery', 3.0, rx(0, r'Battery|CellHolder|BatteryHolder|Keystone_?30\d\d|battery_holder')),
    ('buzzer', 3.0, rx(0, r'Buzzer|Speaker|Beeper')),
    ('microphone', 3.0, rx(0, r'Microphone|Sensor_Audio|MIC_')),
    ('relay', 3.0, rx(0, r'Relay')),
    ('potentiometer', 3.0, rx(0, r'Potentiometer|TRIM_|Trimmer|RV2X4')),
    ('optocoupler', 2.5, rx(0, r'OptoDevice|Opto')),
    ('module', 3.5, rx(0, r'(^|:)Module|RF_Module|ESP32-|WROOM|XIAO|RPi_Pico|Arduino|WeMos|DevKit|Breakout|XBEE|NORA-|RFM9\d|BL54L|SC14CVMDECT|'
                       r'ProMicro|RP2040.Zero|DFPlayer|Mini360|SUPERMINI|wemos|nice_nano|nano_|_nano|xiao')),
    ('graphic', 3.0, rx(0, r'Logo|LOGO|logo|(^|:)Symbol|kibuzzard|Graphic|GRAPHIC|OSHW|oshw|QRCode|Sign_|Panelization|w_logo|Aesthetic|LONGTHING|bongo|Bongo')),
    ('mechanical', 2.0, rx(0, r'(^|:)Board$|kikit|MECHANICAL|Mechanical|mikoto|Cutout|PanelHole|Mech_')),
]

# IC subtypes from part numbers; first match wins, order matters
IC_RULES = [  # specific families first: the first match wins
    ('esd_array', rx(r'\bUSBLC\d|\bTPD\d+E|\bESD\d{3}|\bPRTR5V|\bRCLAMP|\bSRV05|\bIP42\d{2}|\bNUP\d|\bSP05\d|\bCM1213|\bECMF|\bNUF\d|\bCDDFN|\bH5VU')),
    ('fpga', rx(r'\bXC[2-7][A-Z]?\d|\bXCR3|\bXC95|\bXCKU|\bXCZU|\bICE40|\bLFE5|\bLCMXO|\bECP5|\b10M\d{2}|\bEP4C|\bEP2C|\bEPM\d|\bGW1N|'
                  r'\bATF1[56]|\bGAL\d|\bPAL\d|\bAGL\d|\bA3P\d|\bT20F|\bTi60|\bCCGM|\bS5933|\bXC1736|\bXC4\d{3}')),
    ('mcu', rx(r'\bSTM32|\bSTM8|\bATMEGA|\bATTINY|\bATXMEGA|\bAVR\d{2,3}[A-Z]{2}|\bAT90|\bPIC1\d|\bPIC2\d|\bPIC_\d|\bdsPIC|\bRP2040|\bRP2350|'
                 r'\bESP32(?!-[A-Z0-9]+-(MINI|WROOM|WROVER))|\bESP8266|\bnRF5\d|\bnRF9\d|\bSAM[DEGLCV]\d|\bATSAM|\bMCF52|\bCH55\d|\bCH32V|\bEFM32|'
                 r'\bEFR32|\bGD32|\bLPC\d{3,4}|\bMSP430|\bCY8C|\bMKL\d|\bMK\d{2}|\bK\d{2}F|\bR7FA|\bRA[246][A-Z]\d|\bTM4C|\bF1C100|\bT113|'
                 r'\bZ80|\bW806|\bCC2\d{3}|\bCC13\d{2}|\bCC26\d{2}|\bAPM32|\bMIMXRT|\bIMXRT|\bi\.MX|\bSTM32H|\bMyra|\bBM1362|\bmicrocontroller')),
    ('memory', rx(r'\bW25[QNX]\d|\bMX25|\bMX66|\bS25FL|\bIS25|\bGD25|\bAT25|\bAT24|\b24C\d|\b24AA|\b24LC|\bM24C|\bM24\d|\b93C\d|\bMT4[17]|\bMT48|'
                    r'\bMT29|\bMT25|\bMT60|\bMT53|\bIS6[1-6]|\bIS4[2-6]|\bIDT61|\bSST\d{2}|\bAPS6404|\bS27K|\beMMC|\bMB85|\bFM25|\bFM24|'
                    r'\b23LC|\bCY62|\bAS4C|\bK4[ABT]\d|\bH5[TA]Q|\bDDR\d|\bSDRAM|\bZDSD|\b4C4001|\bKGST|\bTHGB|\bFLASH\b|\bEEPROM\b|'
                    r'\bSRAM\b|\b28C\d{2}|\b27C\d{2}|\b62256|\bAT28|\bAT49')),
    ('phy', rx(r'\bRTL8\d{3}|\bDP83\d{3}|\bKSZ\d{4}|\bLAN87\d{2}|\bLAN9\d{3}|\bVSC8\d{3}|\bAR8\d{3}|\bW5500|\bENC28J60|\bTUSB\d{3,4}|'
                 r'\bUSB33\d\d|\bUSB2514|\bUSB4604|\bFUSB3\d{2}|\bSTUSB|\bHUSB\d{3}|\bCYPD\d|\bTPS65987|\bLT8912|\bADV7\d{3}|\bTFP\d{3}|'
                 r'\bSN65DSI|\bTC358|\bPTN3\d{3}|\bIT66\d{2}|\bDS90|\bSN75LVDS|\bCH7\d{3}|\bAD724|\bTDA8501|\bTHS7\d{3}|\bMAX985')),
    ('interface', rx(r'\bFT2232|\bFT232|\bFT230|\bFT231|\bFT4232|\bFT201|\bCP210\d|\bCH340|\bCH341|\bCH343|\bCH9102|\bPL2303|\bMCP2200|'
                       r'\bMCP2221|\bMCP255\d|\bMCP2562|\bMCP251\d|\bSN65HVD|\bTCAN\d|\bSIT10\d{2}|\bPCA82C|\bTJA10\d{2}|\bMAX3485|'
                       r'\bMAX485|\bMAX13487|\bTHVD\d|\bSP3485|\bMAX232|\bMAX202|\bMAX3232|\bMAX3237|\bSP3232|\bXR2\d{4}|\bSC18IS|'
                       r'\bPCA9\d{3}|\bTCA9\d{3}|\bTCA6\d{3}|\bPCA6\d{3}|\bMCP230\d{2}|\bTXS0\d{3}|\bTXB0\d{3}|\bPCA9306|\bNTS0\d{3}|'
                       r'\bSN74AVC|\bSN74LVC\dT|\b74LVC\dT|\bLVC1T45|\bLVC8T245|\bTXS02612|\bSI86\d{2}|\bISO7\d{3}|\bADUM\d|\bCH9350')),
    ('motor_driver', rx(r'\bDRV8\d{2,3}|\bTB6612|\bTB67|\bA49\d{2}|\bA39\d{2}|\bL29[38]|\bL62\d{2}|\bTMC2\d{3}|\bTMC5\d{3}|\bTMC6\d{3}|'
                        r'\bMP65\d{2}|\bBD6\d{3}|\bMCF83\d{2}|\bSTSPIN|\bL6474|\bDRV2603|\bAT8236|\bMX1508|\bVNH\d|\bBTN\d{4}|\bMCF8316|'
                        r'\bmotor driver|\bH-?bridge')),
    ('gate_driver', rx(r'\bIX44\d{2}|\bUCC27\d{3}|\bUCC21\d{3}|\bIR21\d{2}|\bIR2\d{3}|\bLM510[0-9]|\bDRV83\d{2}|\bFAN73\d{2}|\bNCP51\d{2}|'
                       r'\bMIC44\d{2}|\bTC44\d{2}|\bADUM4\d{3}|\bLTC70\d{2}|\bMAX1561|\bgate driver|\bEPC23104|\bLM5113|\bLMG1\d{3}')),
    ('audio_amp', rx(r'\bMAX9835\d|\bMAX9836\d|\bTPA\d{4}|\bPAM8\d{3}|\bTAS\d{4}|\bSSM2\d{3}|\bNS4168|\bLM386|\bTDA\d{4}|\bCS4\d{3}|\bPCM\d{4}|'
                     r'\bWM8\d{3}|\bTLV320|\bSGTL5000|\bES8\d{3}|\bAK4\d{3}|\bCS42\d{2}|\bmax98357')),
    ('current_sense', rx(r'\bINA1[89]\d|\bINA2[0-9]\d|\bINA3\d{2}|\bINA4\d{2}|\bACS7\d{2}|\bMAX40\d{2}|\bMAX9938|\bLMP86\d{2}|\bAD8418|'
                         r'\bZXCT\d|\bLT6106|\bINA2\d{2}A|\bcurrent sense')),
    ('load_switch', rx(r'\bTPS22\d{3}|\bTPS2[01]\d{2}|\bAP22[89]\d|\bAP25\d{2}|\bSLG5NT|\bRT9742|\bMAX17613|\bNCP4556\d|\bSY62\d{2}|\bMIC20\d{2}|'
                       r'\bLTC4412|\bTPS2115|\bLM6600|\bpower switch|\bload switch|\bideal diode|\bLM5050|\bLTC435\d|\bTPS2116')),
    ('adc_dac', rx(r'\bADS\d{4}|\bADS1\d{3}|\bMCP3\d{3}|\bMCP4\d{3}|\bAD7\d{3}|\bAD5\d{3}|\bDAC\d{3,5}|\bMAX11\d{3}|\bMAX5\d{3}|\bLTC2\d{3}|'
                    r'\bMAX6675|\bMAX31855|\bMAX318\d{2}|\bADC\d{3,4}|\bPCM18\d{2}|\bDS4432|\bAD9\d{3}|\bHX711|\bNAU7802|\bCS55\d{2}')),
    ('reference', rx(r'\bLM4040|\bLM4041|\bREF\d{2,4}|\bTL431|\bLM431|\bADR\d{3}|\bMAX6\d{3}|\bLT6656|\bLT1009|\bAZ431|\bvoltage reference|\bshunt reference')),
    ('rf', rx(r'\bSX12\d{2}|\bSX127\d|\bSX126\d|\bCC1101|\bCC1\d{3}|\bnRF24|\bAT86RF|\bSI44\d{2}|\bRFM6\d|\bRFM9\d|\bA7105|\bRFX\d{4}|'
                r'\bSKY\d{5}|\bQPF\d{4}|\bLNA\b|\bBGA7\d{2}|\bMAX2\d{3}|\bTRF\d{4}|\bADF\d{4}|\bSi4\d{3}|\bLR11\d{2}|\bRF\s*transceiver')),
    ('sensor', rx(r'\bBME\d{3}|\bBMP\d{3}|\bBMI\d{3}|\bBMA\d{3}|\bBNO\d{3}|\bBMM\d{3}|\bLIS[23]\w+|\bLSM\d|\bISM330|\bLSM6|\bMPU\d{4}|'
                    r'\bICM\d{5}|\bMMC5\d{3}|\bQMC\d|\bAPDS\d|\bTSL\d{4}|\bVEML\d|\bOPT\d{4}|\bPAW\d{4}|\bPMW\d{4}|\bDHT\d{2}|\bSHT\d{2}|'
                    r'\bSHTC\d|\bHDC\d{4}|\bSi70\d{2}|\bMCP98\d{2}|\bTMP\d{3,4}|\bAT30TS|\bLM75|\bDS18B20|\bMAX3\d{4}|\bSCD\d{2}|'
                    r'\bSGP\d{2}|\bCCS811|\bMQ-\d|\bVL53|\bAH\d{4}|\bDRV5\d{3}|\bA13\d{2}|\bTMAG|\bTSOP\d{4}|\bQRE1113|\bRV-8263|'
                    r'\bPCF85\d{2}|\bDS3231|\bRV-\d{4}|\bsensor\b|\bAS5\d{3}|\bMLX9\d{4}')),
    ('regulator_module', rx(r'\bTPSM\d|\bMPM\d{4}|\bLMZ\d|\bMYMG|\bMYRG|\bLTM4\d|\bLTM8\d|\bMUN12|\bRPM\d|\bRPX-|\bR-78|\bRAC\d|\bIRM-\d|'
                            r'\bTSR[ -]?\d|\bTMR[ -]?\d|\bTEN[ -]?\d|\bA05\d\dS|\bA12\d\dS|\bB05\d\dS|\bMORNSUN|\bURB\d{4}|\bP78E|\bVX78|\bCRV1D|'
                            r'\bMini360|\bConverter_DCDC|\bMPT1584|\bVXO\d|power module')),
    ('charge_pump', rx(r'\bICL7660|\bLM2664|\bLM2775|\bTPS60\d{3}|\bMAX1044|\bLTC1044|\bMAX660|\bCAT3200|\bLM27762|\bMAX1680')),
    ('pmic', rx(r'\bnPM\d{4}|\bAXP\d{3}|\bTPS65\d{3}|\bDA9\d{3}|\bACT88\d{2}|\bRT5\d{3}|\bMAX7765|\bBD71\d{3}|\bPF\d{4}|\bMP5\d{3}|\bTPS6521')),
    ('charger', rx(r'\bBQ24\d{3}|\bBQ25\d{3}|\bMCP7383\d|\bMCP73831|\bTP4056|\bTP4054|\bLTC4054|\bIP5306|\bMAX1555|\bCN3065|\bLTC4067|'
                   r'\bSL9062|\bMCP7303\d|\bBQ2105\d|\bLTC4162|\bMAX7765')),
    ('regulator_switching', rx(r'\bTPS5\d{3,4}|\bTPS56\d|\bTPS6[0-3]\d{2,3}|\bTPS82|\bTLV6[12]\d{3}|\bLMR\d{4,5}|\bLM259[16]|\bLM257[56]|'
                               r'\bLM267\d|\bLM25\d{3}|\bLM3671|\bLM3670|\bMP1584|\bMP2\d{3}|\bMP1\d{3}|\bMP8\d{3}|\bMPQ\d|\bSY8\d{3}|'
                               r'\bAP63\d{3}|\bAP62\d{3}|\bAP3441|\bAP3012|\bAP3015|\bAOZ\d{4}|\bRT8\d{3}|\bRT60\d{2}|\bRT7\d{3}|\bXL[1-7]\d{3}|'
                               r'\bMT2492|\bMT3410|\bMT3608|\bSX1308|\bTX4138|\bFAN53\d{2}|\bISL85\d{2}|\bLTC3\d{3}|\bLT8\d{3}|'
                               r'\bLT3\d{3}|\bLT1373|\bLT1930|\bLT1935|\bMAX1503\d|\bMAX1750\d|\bMIC2\d{4}|\bMIC28\d{3}|\bNCP3\d{3}|\bADP2\d{3}|'
                               r'\bST1S\d|\bL5973|\bBD9\w+|\bSC4\d{2}|\bJW5\d|\bETA\d{4}|\bLM27313|\bLM2731|\bLM2735|\bMCP16\d{2}|\bNCP1402|'
                               r'\bBL8530|\bCE8301|\bRT9266|\bHT77\d\d|\bACT4\d{3}|\bSGM61\d{2}|\bLM5\d{3}|\bLM3478|\bMAX1724|\bMIC2250|'
                               r'\bME2108|\bLT8364|\bLM25119|\bTPS55340|\bLM2842|\bLM2853|\bAP3211|\bMIC28517|\bR7\d{3}|\bbuck\b|\bboost\b|'
                               r'step.?down|step.?up|switching regulator|\bDC-?DC\b|DC/DC')),
    ('regulator_linear', rx(r'\bLDO\b|\b(AMS|AZ|LM|LT|LD|NCP|SPX|TLV|BL|REG|IL|CJT|MC33|UA)?1117|\bLM317|\bLM337|\b(L|LM|MC|UA|KA|NJM|AN|LM3)?78[LM]?\d\d\b|'
                            r'\b(L|LM|MC|UA|KA)?79[LM]?\d\d\b|\bAP21\d{2}|\bAP22\d{2}|\bAP7\d{3}|\bMCP17\d{2}|\bMCP18\d{2}|\bXC62\d{2}|\bRT90\d{2}|'
                            r'\bRT91\d{2}|\bTLV7\d{2,3}|\bTLV1117|\bTPS7\d{2}|\bTPS7A|\bLP59\d{2}|\bLP29\d{2}|\bLP38\d{2}|\bMIC5\d{3}|\bMIC29\d{3}|'
                            r'\bSPX\d{4}|\bHT7[0-9]{3}|\bME62\d{2}|\bME2188|\bLD39\d{3}|\bLD29\d{3}|\bLDL\d|\bLDLN|\bLDO\d{2}|\bL4931|'
                            r'\bNCP1[01]\d|\bNCP7\d{2}|\bNCV\d{4}|\bNCP177|\bNJM\d{4}|\bLT1129|\bLT1763|\bLT3042|\bLT1086|\bADP1\d{2}|\bADP7\d{3}|'
                            r'\bRT9078|\bSGM2\d{3}|\bTC1185|\bTC1262|\bTPL810|\bR5617|\bZLDO|\blinear regulator|\blow.?dropout|\bvoltage regulator')),
    ('opamp', rx(r'\bLM358|\bLM324|\bLM2904|\bLM6\d{3}|\bTL07\d|\bTL08\d|\bNE5532|\bNE5534|\bOPA\d{3,4}|\bMCP60\d{2}|\bMCP6\d{3}|\bMCP6N|'
                   r'\bLMV3\d{2}|\bLMV7\d{2}|\bAD8\d{2,3}|\bAD86\d{2}|\bADA4\d{3}|\bLT1\d{3}|\bLT6\d{3}|\bTLV9\d{3}|\bTLV2\d{3}|'
                   r'\bTSV\d{3}|\bGS32\d|\bGSV33\d|\bINA8\d{2}|\bINA12\d|\bTHS4\d{3}|\bECC83|\bop.?amp|\boperational amplifier|'
                   r'\binstrumentation amp|\bLM393|\bLM339|\bLMV331|\bTLV3\d{3}|\bcomparator|\bAD8338|\bLT1794')),
    ('logic', rx(r'\b74[A-Z]*\d{2,4}|\bSN74|\bCD40\d{2}|\bCD74|\bNC7[SZ]|\bHEF4\d{3}|\bMC14\d{3}|\bTC74|\bAiP74|\b4C\d{3}|\bTC7S|\bMAX809|'
                   r'\bAPX8\d{2}|\bTPS3\d{3}|\bSTM6\d{3}|\bMCP1[0-3]\d\b|\bsupervisor|\bDS1\d{3}|\bNE555|\bLM555|\bTLC555|\bICM7555')),
]

# pin function patterns
PWR_PIN = rx(r'^(P?VIN\d*[A-Z]?|VIN_?\w*|VCC\w*|VDD\w*|AVDD\w*|DVDD\w*|IOVDD|PVDD\w*|VCCIO\w*|VCCINT|VCCAUX\w*|VCCA\w*|VCCB\w*|VBAT\w*|'
             r'VSYS|VBUS|VUSB|VS|VS\d|V\+|\+VS|VM|VMOT\w*|VBB|VPP|VDDQ\w*|VDDIO\w*|VDDA\w*|VREG_?IN|VSUP\w*|VCORE|VIO|V_?IO|'
             r'3V3|5V|1V8|1V2|VLED|VDRV|VAUX|VHV|VPWR|PWR|V_?IN|V_?CC|V_?DD|VLOGIC|VL|VCP)$')
GND_PIN = rx(r'^(P?GND\w*|AGND\w*|DGND\w*|SGND|VSS\w*|AVSS\w*|DVSS\w*|EP|EPAD|E?PAD|THERMAL\w*|TAB|GNDA|GNDD|0V|COM|V-|-VS|PAD\d?|'
             r'GND_?EP|EXP|SLUG|PGND\d*|GROUND|SUB)$')
SW_PIN = rx(r'^(SW\d?[A-Z]?|LX\d?|PH|PHASE\d?|SW_?\d|LX_?\d|L\d|SWA|SWB|SW[12]|L[12]|LXA|LXB|DRAIN|SH[ABC]?|VSW\d?|'
            r'V?LX_?SMPS|VLX\w*|\w*_LX\d?|LX_\w+|SW_(BUCK|BOOST|REG|DCDC)\w*|(BUCK|BOOST|DCDC|SMPS|REG)\d?_?(SW|LX)\d?|SMPS_?(SW|LX))$')
OUT_PIN = rx(r'^(V?OUT\d?|VO|OUTPUT|VREG(_?OUT)?|V_?OUT|LDO_?OUT|VOUT_?\w*|VREG_VOUT|OUT[12]?|[+-]V?O(UT)?\d?|V?O(UT)?[+-]|'
             r'[+-]VOUT\w*|VOUT[+-]\w*|V[+-]OUT)$')
IN_PIN = rx(r'^(P?VIN\d?|VI|VCC|VDD|IN|VS|VBAT|PVDD|AVIN|VSUP|VSYS|V\+|INPUT|VIN_\w+|[+-]VIN|VIN[+-]|[+-]?V_?IN)$')
FB_PIN = rx(r'^(V?FB\d?|FB[+-]?|ADJ|ADJ/GND|VSENSE|VOS|FBK|FB_?\w*|SENSE)$')
SUPPLY_PIN = rx(r'^(P?VIN\d*|AVIN|VBAT\w*|VDD\w*|VCC\w*|AVDD\w*|DVDD\w*|IOVDD|PVDD\w*|VBUS|VSYS|VDDIO\w*|VDDA\w*|VCCIO\w*|VREG_?IN|REGIN|'
                 r'VSUP\w*|VMOT\w*|VM|VBB|VCORE|VCCINT|VCCAUX\w*)$')
BOOT_PIN = rx(r'^(BST\d?|BOOT\d?|CB|BS|CBOOT|VBST|BOOTSTRAP|HB|BTST|C_?BOOT)$')
EN_PIN = rx(r'^(EN\w*|SHDN\w*|ON|ON/OFF|CE|RUN|INH|STBY|SLEEP|nSLEEP|CTRL)$')
XTAL_PIN = rx(r'(XTAL|XIN|XOUT|X_?IN|X_?OUT|^XI$|^XO$|^X[12]$|OSC_?IN|OSC_?OUT|OSC\d?_?(IN|OUT)|OSCI|OSCO|OSC32|HSE|LSE|CLKIN|CLK_?IN|'
             r'XTAL[12PN]|XC[12]$|^XT[12]$|EXTAL|^XA$|^XB$|RTC_?X|32K_?X)')
# PH0/PH1/PC14/PC15 are STM32 GPIO names that double as oscillator pins: a clock only with a crystal on the net
RF_PIN = rx(r'(^|[^A-Z])(RF|ANT\d?|RFIO|RF_?IO|LNA_?IN|PA_?OUT|RF_?IN|RF_?OUT|RFP|RFN|RF[+-]|ANTENNA|TX_?RF|RX_?RF|RF\d)($|[^A-Z])')
RESET_PIN = rx(r'^(N?RST\w*|RESET\w*|N?RESET|MCLR\w*|RUN|POR|CHIP_?EN|CHIP_?PU|EN|XRES|SRST|RSTN|RST_?N|RESETB|RESET_?N)$')
BOOTSEL_PIN = rx(r'^(BOOT\d?|BOOTSEL|BOOT_?\d|BOOT_?MODE\w*|MODE\d?|IO0|GPIO0|PROG|FLASH_?MODE|BOOTSTRAP\w*|STRAP\w*)$')
ANALOG_PIN = rx(r'^(A?IN\d*[+-]?|[+-]IN\w*|IN[+-]\w*|INP\w*|INN\w*|AIN\w*|ADC\w*|AN\d+|VREF\w*|REF\w*|REFIN\w*|REFOUT|FB\w*|COMP\w*|SENSE\w*|'
                 r'ISNS\w*|IS[+-]|CS[+-]|CSP|CSN|SNS\w*|SRP|SRN|IMON|VMON|TS|NTC|THERM\w*|VCM|BIAS|MIC\w*|LINE\w*|AUX\w*|XADC\w*|'
                 r'VP|VN|VIN[+-]|V[+-]IN|SENSEP|SENSEN|-|\+|-IN\w*|\+IN\w*|IN[AB][+-]|[+-]IN[AB])$')
OPAMP_IN_PIN = rx(r'^([+-]|IN[+-]|[+-]IN|[+-]IN[A-D]?|IN[A-D]?[+-]|IN[A-D]?_?[PN]|[+-]IN_?[A-D]|V[+-]IN|INP|INN|NON-?INV\w*|INV\w*|IN_?[PN]\d?)$')

GND_NET = rx(r'(^|[^A-Z])(A|D|P|S|C|E)?GND|^VSS|^0V$|^GND|GND$|GROUND')
GND_ANY = rx(r'GND|VSS|EARTH|CHASSIS|GROUND')
CHASSIS_NET = rx(r'EARTH|CHASSIS|SHIELD|^PE$|^FG$|^CGND|^SGND$|CASE|^SH$|SHLD|FRAME|^GNDCHASSIS|CHASSIS_?GND|^EGND')
PWR_NET = rx(r'^(\+?\d+(\.\d+)?V\d*\w*|\+[A-Z0-9_.]+|V(CC|DD|BUS|IN|SYS|BAT|MOT|M|PP|REG|CORE|CAP|S|IO|LOGIC|AUX|LED|DRV|SUP)\w*|'
             r'[AD]V(DD|CC)\w*|P\d+V\d*\w*|\d+V\d+\w*|[0-9]+V[0-9]*_?\w*|-\d+(\.\d+)?V\w*|V_?\d+V\d*|VDD_?\w+|VCC_?\w+|'
             r'BATT?\+?|VBATT?\w*|PWR\w*|POWER\w*|SUPPLY\w*|RAW|VUSB\w*|USB_?5V|USB_?VBUS|VIN_?\w*|VOUT\w*|V_\w+|\w+_(3V3|5V|1V8|12V|24V|3V|VCC|VDD))$')
PWR_WEAK = rx(r'VOUT|VDD|VCC|VBUS|VBAT|VIN|PWR|SUPPLY|BATT|\bV\d|^P\d+V\d*|VSYS|VMOT|VLED|RAIL|VREG')
CTRL_NET = rx(r'(^|[^A-Z])(FB|VFB|BOOT|BST|BS|EN|ENABLE|COMP|SS|PG|PGOOD|ILIM|RT|CT|TRK|SENSE|SNS|ISNS|CS|XTAL|XI|XO|OSC|RST|RESET|NRST|'
              r'ADC|AIN|SDA|SCL|TXD?|RXD?|LED|GATE|HO|LO|PWM|SIG|DATA|CLK|INT|IRQ|MISO|MOSI|SCK|CSN?|USB|D[PMN+-]|CC\d?|SBU\d?|'
              r'STAT|CHG|FAULT|ALERT|SDO|SDI|DIN|DOUT|DET|MON|MODE|SEL|CTRL|SET|ADJ|TS|NTC|ON|OFF|SW\d|BTN|KEY|ROW|COL|GPIO|IO\d+|'
              r'PA\d|PB\d|PC\d|PD\d|P\d_\d|SPI|I2C|UART|CAN|HS|LS)([^A-Z]|$)')

# net-name interfaces: (interface, speed, regex on the short name)
IFACE = [
    ('usb3', 'gbps', rx(r'SSTX|SSRX|USB3|SS_?TX|SS_?RX|^TX[12][+-PN]|^RX[12][+-PN]|USB_?SS')),
    ('usb2', 'hs', rx(r'USB.*(D[PMN+-]|DP|DM|DN|_P$|_N$|D\+|D-)|^D[+-]$|^USB_?D?[PMN+-]$|^(USB)?D[PMN]\d?$|^U?D[PM]$|^USB\d?_?[PN]$|^D_?[PN]$|'
                      r'HSIC|ULPI|^USB_?DATA[+-]')),
    ('pcie', 'gbps', rx(r'PCIE|PCI_?E|PE[TR][PN]\d|PE_?[TR]X|PERST|CLKREQ|PCIE_?CLK')),
    ('sata', 'gbps', rx(r'SATA')),
    ('hdmi', 'gbps', rx(r'HDMI|TMDS|^DDC|_DDC|CEC|HPD')),
    ('displayport', 'gbps', rx(r'^DP_?(AUX|ML|LANE)|DISPLAYPORT|EDP')),
    ('mipi', 'gbps', rx(r'MIPI|CSI|DSI')),
    ('lvds', 'gbps', rx(r'LVDS|^LV_')),
    ('serdes', 'gbps', rx(r'SFP|QSFP|MGT|^GT[PXHY]|SERDES|_?TX_?[PN]\d?$|_?RX_?[PN]\d?$|^TX[PN]\d?$|^RX[PN]\d?$|SGMII|XAUI|XFI|GTREF')),
    ('ethernet_mdi', 'hs', rx(r'MDI|TRD\d?_?[PN+-]|TRX\d?_?[PN+-]|ETH.*(TX|RX|TD|RD)\w*[PN+-]$|^TD_?[PN+-]$|^RD_?[PN+-]$|ETH_?(TX|RX)[+-]|'
                              r'^(TX|RX)[+-]$|MDI\.|^TPI|^TPO')),
    ('rgmii', 'hs', rx(r'RGMII|RMII|^MII|GMII|^E?TXD\d|^E?RXD\d|TX_?EN$|RX_?DV|CRS_?DV|TX_?CLK|RX_?CLK|ETH_?REF_?CLK|RX_?ER|TX_?ER|'
                       r'^ETH_?(TXD|RXD)|ETH_?(TX|RX)_?(EN|DV|CLK)')),
    ('mdio', 'ls', rx(r'MDIO|^MDC$|_MDC$')),
    ('ddr', 'gbps', rx(r'DDR|DQS|^DQ\d|_DQ\d|DQM|^DM\d|_DM\d$|SDRAM|^MA\d|^BA\d|_BA\d|_A\d{1,2}$|RAS|CAS|ODT|CKE|^CK_?[PN]|DRAM|^WE$|_WE$|'
                     r'HYPERBUS|HYPERRAM|^HB_')),
    ('emmc_sd', 'medium', rx(r'SDIO|SDMMC|EMMC|MMC|SD_?(CMD|CLK|DAT|D\d)|SDC\d?_?(CMD|CLK|D\d)|^SD_|_SD_?(CMD|CLK|D\d)|^DAT[0-7]$|^CMD$')),
    ('qspi', 'medium', rx(r'QSPI|OSPI|OCTOSPI|QIO\d|QSPI_?SD|FLASH_?(IO|D)\d|^IO[0-3]$|_SIO\d|QSPI_?S?CLK|QSPI_?SS|OSPI_?')),
    ('spi', 'medium', rx(r'SPI|MOSI|MISO|^SCK|_SCK|SCLK|^SDO$|^SDI$|COPI|CIPO|^SDA$(?!)')),
    ('i2s', 'medium', rx(r'I2S|BCLK|LRCLK|LRCK|^WS$|MCLK|^SDOUT|^SDIN|^DOUT$|^DIN$|PDM|^ASDO|^DSDI')),
    ('can', 'ls', rx(r'^CAN_?[HL]$|CANH|CANL|CAN_?[+-]$|CAN\d?_[HL]$|CAN.*[_.](H|L|DP|DN|P|N)$|CAN\.[HL]')),
    ('rs485', 'ls', rx(r'RS-?485|485_?[AB]|RS485_?[AB+-]|^RS_?[AB]$|MODBUS|DMX')),
    ('i2c', 'ls', rx(r'SDA|SCL|I2C|IIC|TWI|I3C')),
    ('uart', 'ls', rx(r'UART|USART|TXD|RXD|^TX\d?$|^RX\d?$|RTS|CTS|_TX$|_RX$|^TX_|^RX_|SERIAL|CONSOLE')),
    ('debug', 'ls', rx(r'JTAG|^TCK|_TCK|^TMS|_TMS|^TDI|_TDI|^TDO|_TDO|TRST|SWD|SWCLK|SWDIO|^SWO|_SWO|UPDI|^PDI|^ICSP|^PGC|^PGD|^DEBUG|^SPY')),
    ('video', 'medium', rx(r'VGA|HSYNC|VSYNC|CVBS|LUMA|CHROMA|^PAL$|^NTSC$|COMPOSITE|^Y_?IN|^C_?IN|VIDEO')),
]
I2C_NAME = rx(r'I2C|IIC|TWI|SMBUS|PMBUS|I3C')


def name_iface(s: str, skip=()) -> tuple[str | None, str | None]:
    """(interface, speed) from a net name: the first IFACE row that matches, except that an I2C word wins
    (an 'I2C1_SCLK' is a two-wire bus, not SPI)."""
    if 'i2c' not in skip and I2C_NAME.search(s):
        return 'i2c', 'ls'
    for name_, sp, r in IFACE:
        if name_ not in skip and r.search(s):
            return name_, sp
    return None, None


CLOCK_NET = rx(r'CLK|CLOCK|XTAL|^XIN|^XOUT|^XI$|^XO$|^X[12]$|OSC|^HSE|^LSE|REFCLK|MCLK|BCLK|SCK|SCLK|^CK_?[PN]?$|_CK$|^CK\d|32K|RTC_?X|'
              r'^EXTAL|^XTAL')
ANALOG_NET = rx(r'(^|[^A-Z])(ADC|AIN|AN\d+|ANA|ANALOG|VREF|REF(IN|OUT|P|N)?|SENSE|SNS|KELVIN|ISENSE|ISNS|IMON|VSENSE|VMON|CSP|CSN|FB|VFB|COMP|'
               r'AUDIO|MIC|LINE_?(IN|OUT)?|HP_?[LR]|HPL|HPR|HPCOM|IN[+-]|INP|INN|AINP|AINN|THERM|NTC|RTD|TC[+-]?|TEMP|BRIDGE|STRAIN|LOADCELL|'
               r'PIEZO|PHOTO|TIA|VCM|BIAS|ECG|EEG|EMG|XADC|CV|SIGNAL_?IN|PREAMP|GAIN|VOL|POT|DRY|WET|MIX|AUDIO|SPDIF|SENS|SENSOR|LDR|'
               r'CURR|CURRENT|SHUNT|VBAT_?SENSE|VBAT_?ADC|VDIV|DIV|ISET|IREF|IPROG|PROG|RSET)([^A-Z]|$)')
RF_NET = rx(r'(^|[^A-Z])(RF|ANT|ANTENNA|RFIN|RFOUT|RF_?IN|RF_?OUT|LNA|PA_?OUT|2G4|GNSS|GPS|LORA|SUBGHZ|915|868|433|BLE_?ANT|WIFI_?ANT|'
            r'RFIO|U\.?FL|SMA|COAX|50R|50OHM)([^A-Z]|$)')
RESET_NET = rx(r'(^|[^A-Z])(N?RST|RESET|N?RESET|MCLR|POR|CHIP_?EN|CHIP_?PU|SRST|TRST|RST_?N|RESETN|RESETB|XRES|RUN)([^A-Z0-9]|$)')
BOOT_NET = rx(r'(^|[^A-Z])(BOOT\d?|BOOTSEL|BOOT_?MODE|BOOT_?\d|USB_?BOOT|FLASH_?MODE|PROG_?MODE|STRAP)([^A-Z]|$)')

POLARITY = {'P': 'N', 'N': 'P', '+': '-', '-': '+', 'M': 'P', 'H': 'L', 'L': 'H', 'T': 'C', 'C': 'T', 'A': 'B', 'B': 'A'}
COMPLEMENTS = (('P', 'N'), ('P', 'M'), ('+', '-'), ('H', 'L'), ('T', 'C'), ('A', 'B'))   # (positive, negative)

ZDIFF = {'usb2': (90.0, 0.15), 'usb3': (90.0, 0.10), 'ethernet_mdi': (100.0, 0.10), 'hdmi': (100.0, 0.10), 'lvds': (100.0, 0.10),
         'mipi': (100.0, 0.10), 'pcie': (85.0, 0.15), 'sata': (100.0, 0.15), 'serdes': (100.0, 0.10), 'ddr': (100.0, 0.10),
         'displayport': (100.0, 0.10), 'can': (120.0, 0.10), 'rs485': (120.0, 0.10), 'clock': (100.0, 0.10)}
ZDIFF_SRC = {'usb2': 'docs/topics/rules/interfaces/usb2.md (TI SLLA414A: 90 ohm +-15%)',
             'usb3': 'docs/topics/rules/interfaces/usb3-usb4-typec.md',
             'ethernet_mdi': 'docs/topics/rules/interfaces/ethernet.md (TI SNLA387: 100 ohm +-10%)',
             'hdmi': 'docs/topics/rules/interfaces/hdmi-dp.md', 'displayport': 'docs/topics/rules/interfaces/hdmi-dp.md',
             'lvds': 'TIA/EIA-644 100 ohm termination [I]', 'mipi': 'docs/topics/rules/interfaces/mipi.md',
             'pcie': 'docs/topics/rules/interfaces/pcie.md (85 ohm CEM add-in)', 'sata': 'docs/topics/rules/interfaces/sata-ufs-sd.md',
             'serdes': 'generic 100 ohm differential [I]', 'ddr': 'docs/topics/rules/interfaces/ddr.md',
             'can': 'docs/topics/rules/interfaces/can-rs485.md (120 ohm cable)', 'rs485': 'docs/topics/rules/interfaces/can-rs485.md (120 ohm cable)',
             'clock': 'differential clock, 100 ohm [I]'}


# =============================================================================== result types
@dataclass
class PartRole:
    ref: str
    kind: str
    subtype: str | None
    role: str
    confidence: float
    evidence: list
    kind_confidence: float = 0.0
    attrs: dict = field(default_factory=dict)

    @property
    def is_passive2(self) -> bool:
        return self.kind in ('resistor', 'capacitor', 'inductor', 'ferrite')


@dataclass
class NetRole:
    net: str
    role: str
    subrole: str | None
    confidence: float
    evidence: list
    tags: dict = field(default_factory=dict)     # other roles this net also plays: role -> confidence
    attrs: dict = field(default_factory=dict)    # volts Belief, interface, speed, pair, ...


@dataclass
class DiffPair:
    p: str
    n: str
    interface: str
    speed: str
    confidence: float
    evidence: list
    channel: str = ''


@dataclass
class Roles:
    nl: Netlist
    parts: dict = field(default_factory=dict)     # ref -> PartRole
    nets: dict = field(default_factory=dict)      # net -> NetRole
    grounds: list = field(default_factory=list)   # ground nets, primary first
    gnd: str | None = None                        # primary ground
    rails: dict = field(default_factory=dict)     # net -> NetRole (role 'rail')
    pairs: list = field(default_factory=list)     # DiffPair
    switch_nodes: dict = field(default_factory=dict)   # net -> dict(kind, parts, evidence)
    caps_to: dict = field(default_factory=dict)   # net -> [(cap ref, gnd net)]
    log: list = field(default_factory=list)

    def kind(self, ref) -> str:
        r = self.parts.get(ref)
        return r.kind if r else 'unknown'

    def is_ground(self, net) -> bool:
        return net in self._gset

    def is_rail(self, net) -> bool:
        return net in self.rails

    @property
    def _gset(self):
        return set(self.grounds)


# =============================================================================== helpers
def _text(part: Part) -> str:
    return part.text()


def _ic_subtype(part: Part) -> tuple[str | None, str]:
    t = f"{part.value} {part.fields.get('MPN', '')} {part.fields.get('Manufacturer Part Number', '')} " \
        f"{part.fields.get('Part Number', '')} {part.fpname} {part.description}"
    for sub, r in IC_RULES:
        m = r.search(t)
        if m:
            return sub, m.group(0).strip()
    return None, ''


def regulator_vout(text: str) -> tuple[float, str] | None:
    """Fixed output voltage from a regulator part number ('AMS1117-3.3', 'MCP1700-3302E', 'XC6206P332MR',
    'L7805', 'NCP177AMX330', 'TLV74318'); None for adjustable or unknown parts."""
    t = (text or '').upper().replace(',', '.')
    if re.search(r'ADJ', t):
        return None
    m = re.search(r'(?<![\d.])(\d{1,2})\.(\d{1,2})\s*V?(?![\d])', t)          # -3.3, 3.3V, 5.0
    if m and 0.5 <= float(f"{m.group(1)}.{m.group(2)}") <= 60:
        return float(f"{m.group(1)}.{m.group(2)}"), m.group(0)
    m = re.search(r'(?<!\d)(\d)V(\d)(?!\d)', t)                               # 3V3
    if m:
        return float(f"{m.group(1)}.{m.group(2)}"), m.group(0)
    m = re.search(r'\b(?:L|LM|MC|UA|KA|NJM|AN|VX|L)?(78|79)[LM]?(\d{2})(?!\d)', t)          # 7805, 78L05, LM7812, VX7805
    if m and m.group(2) not in ('00',):
        v = float(m.group(2))
        return (-v if m.group(1) == '79' else v), m.group(0)
    fam = (r'(ME62\d\d[A-Z]?|ME2188[A-Z]?|XC62\d\d[A-Z]?|HT7[0-9]?|MCP17\d\d[A-Z]?-?|MCP18\d\d[A-Z]?-?|L4931[A-Z]{0,2}|LDLN\d{3}[A-Z]?|'
           r'LDL1117[A-Z]*|AP7375[A-Z]?-?|AP21\d\d[A-Z]?-?|AP22\d\d[A-Z]?-?|TLV7\d\d|TLV76\d|TLV75\d|TLV73\d|TLV1117LV|TPS76\d|TPS7A\d\d|'
           r'LP59\d\d[A-Z]*-?|RT9013-?|RT9193-?|RT9080-?|NJM\d{4}[A-Z]?|SPX3819[A-Z0-9]*-?|MIC5219-?|MIC5317-?|LDO40LPU|NCP177[A-Z]{2,4}|'
           r'NCV59801[A-Z]{2,4}|BL8555-?|SGM20\d\d-?|AP632|AP633|TLV1117-)')
    m = re.search(fam + r'(\d{2,4})', t)
    if m:
        code = m.group(2)
        if code in ('01', '00'):
            return None
        if len(code) == 2:
            v = float(code[0] + '.' + code[1])
        elif len(code) == 3:
            v = float(code[0] + '.' + code[1:]) if m.group(1).startswith(('NCP177', 'NCV59801')) else float(code[0] + '.' + code[1])
        else:
            v = float(code[0] + '.' + code[1])
        if m.group(1).startswith(('AP632', 'AP633')):
            v = {'03': 3.3, '05': 5.0, '00': None}.get(code[-2:], None) or 0
            if not v:
                return None
        if 0.5 <= v <= 60:
            return v, m.group(0)
    return None


def shunt_ohms(text: str) -> float | None:
    """Milliohm codes in shunt part numbers: 'LVK25R005FER' -> 0.005, 'WSL2512R0100FEA' -> 0.01."""
    m = re.search(r'\d(?:R|L)(\d{3,4})(?=[A-Z]|\b)', text or '')
    if m and re.search(r'LVK|LVR|WSL|WSK|WSR|CSS|CSR|PMR|KRL|TLR|ULR|CSM|SMV|BVS|ERJ', text or '', re.I):
        return float('0.' + m.group(1))
    return None


# =============================================================================== part kinds
def classify_part(part: Part) -> tuple[str, str | None, float, list]:
    """(kind, subtype, confidence, evidence) for one part, from its own text and pins."""
    sc = defaultdict(float)
    evs = defaultdict(list)
    sub = {}

    def add(kind, w, e):
        sc[kind] += w
        evs[kind].append(e)

    pfx = part.prefix
    for k, w in PREFIX.get(pfx, {}).items():
        add(k, w * 0.9, ev('refdes', f"reference prefix '{pfx}'", w * 0.9))
    if pfx.startswith(('KIBUZZARD', 'LOGO', 'REF**', 'GRAPHIC', 'SIGN_', 'MOUSE')) and part.npads == 0:
        add('graphic', 3.0, ev('refdes', f"reference '{part.refdes}' with no pads", 3.0))
    lib = part.lib_id
    for k, w, r in LIB_RULES:
        m = r.search(lib)
        if m:
            add(k, w, ev('lib_id', f"footprint '{lib}' ({m.group(0).strip(':_')})", w))
    text = f"{part.value} | {part.description} | " + ' '.join(
        str(part.fields[k]) for k in ('MPN', 'Manufacturer Part Number', 'Part Number', 'Comment', 'Val', 'LCSC Part Number')
        if part.fields.get(k))
    for k, s, w, r in TEXT_RULES:
        m = r.search(text)
        if m:
            add(k, w, ev('value' if m.start() < len(part.value) + 1 else 'field', f"text '{m.group(0).strip()}'", w))
            if s and (k not in sub or w > sub[k][1]):
                sub[k] = (s, w)
    # value parses as a quantity
    val = part.value
    cap = V.capacitance(val)
    if cap is not None and re.search(r'\d\s*[pnuµμ]|\d[pnu]\d|F\b', val):
        add('capacitor', 1.5, ev('value', f"value '{val}' reads as {V.si(cap, 'F')}", 1.5))
    ind = V.inductance(val)
    if ind is not None and re.search(r'H\b|H\s|[nu]H|\d[nu]\d', val, re.I):
        add('inductor', 1.5, ev('value', f"value '{val}' reads as {V.si(ind, 'H')}", 1.5))
    res = V.resistance(val)
    if res is not None and (re.search(r'\d\s*[kKM]\b|\d[kKMR]\d|\dR\b|^R\d|\dm\b|^0$|^0R$', val) or re.search(r'\d\s*(Ω|ohm)', val, re.I)):
        add('resistor', 1.2, ev('value', f"value '{val}' reads as {V.si(res, 'Ω')}", 1.2))
        if re.search(r'Ω|ohm|\dR\b', val, re.I) and sc.get('inductor', 0) > 0 and res >= 10:
            # inductors are never specified in ohms; beads are (impedance at 100 MHz)
            add('ferrite', 4.0, ev('value', f"impedance value '{val}' on an inductor-like part", 4.0))
            sc['inductor'] -= 1.5
    fq = V.frequency(val)
    if fq is not None and re.search(r'hz|\dk\d|\dM\b', val, re.I):
        add('crystal', 1.0, ev('value', f"value '{val}' reads as {V.si(fq, 'Hz')}", 1.0))
        add('oscillator', 0.6, ev('value', f"value '{val}' reads as {V.si(fq, 'Hz')}", 0.6))
    # pins
    n_act = len(part.active_pins())
    fns = {p.fn for p in part.pins}
    types = Counter(p.ptype for p in part.pins if p.ptype)
    if part.npads == 0:
        add('graphic', 2.5, ev('count', 'no pads', 2.5))
        for k in ('capacitor', 'resistor', 'ic', 'connector', 'diode', 'transistor'):
            sc[k] -= 3.0
    if part.npads == 1:
        for k in ('test_point', 'mounting_hole', 'fiducial', 'connector', 'antenna', 'heatsink'):
            add(k, 0.5, ev('count', 'one pad', 0.5))
        for k in ('capacitor', 'resistor', 'inductor', 'ic', 'diode', 'transistor', 'crystal'):
            sc[k] -= 2.0
        if all(p.pad_kind == 'np_thru_hole' for p in part.pins) or not part.pins:
            add('mounting_hole', 1.0, ev('footprint', 'a non-plated hole', 1.0))
        if part.pins and not part.pins[0].net and part.pins[0].pad_kind == 'smd':
            add('fiducial', 0.8, ev('footprint', 'one SMD pad with no net', 0.8))
    if all(p.pad_kind == 'np_thru_hole' for p in part.pins) and part.pins:
        add('mounting_hole', 1.5, ev('footprint', 'only non-plated holes', 1.5))
    if fns and fns <= {'G', 'D', 'S', '1', '2', '3', '4', '5', '6', '7', '8', 'TAB', 'EP'} and {'G', 'D', 'S'} <= fns:
        add('transistor', 3.0, ev('pinfunction', 'pins named G, D, S', 3.0))
        sub.setdefault('transistor', ('mosfet', 1.0))
    if {'B', 'C', 'E'} <= fns and len(fns) <= 4:
        add('transistor', 3.0, ev('pinfunction', 'pins named B, C, E', 3.0))
        sub.setdefault('transistor', ('bjt', 1.0))
    if {'A', 'K'} <= fns and len(fns) <= 3:
        add('diode', 2.0, ev('pinfunction', 'pins named A, K', 2.0))
        add('led', 0.5, ev('pinfunction', 'pins named A, K', 0.5))
    if types.get('power_out') and n_act >= 3 and not (sc.get('connector', 0) > 0 or sc.get('fuse', 0) > 0 or sc.get('resistor', 0) > 0):
        add('ic', 0.5, ev('pintype', f"{types['power_out']} pin(s) typed power_out", 0.5))
    sig_t = sum(types.get(t, 0) for t in ('input', 'output', 'bidirectional', 'tri_state', 'open_collector'))
    if sig_t >= 2 and n_act >= 4:
        add('ic', 1.0, ev('pintype', f"{sig_t} pins typed as logic I/O", 1.0))
        add('module', 0.3, ev('pintype', f"{sig_t} pins typed as logic I/O", 0.3))
    if n_act >= 8 and not sc.get('connector'):
        add('ic', 0.5, ev('count', f"{n_act} connected pins", 0.5))
    if n_act > 2:
        for k in ('capacitor', 'resistor', 'ferrite'):
            if sc.get(k):
                sc[k] -= 1.5 if n_act > 4 else 0.5
    if n_act == 2 and len(part.pins) <= 3:
        for k in ('ic',):
            sc[k] -= 1.0
    if 'board_only' in part.attrs and part.npads == 0:
        add('graphic', 1.0, ev('attr', 'board_only with no pads', 1.0))
    # IC subtype: a part number that names a regulator, MCU, ... is itself evidence of an IC
    isub, imatch = _ic_subtype(part)
    if isub == 'esd_array':
        add('diode', 2.5, ev('table', f"ESD array part number '{imatch}'", 2.5))
        sub['diode'] = ('esd_array', 9.0)
        sc['ic'] -= 2.0
    elif isub == 'reference' and n_act >= 2:
        add('ic', 3.0, ev('table', f"voltage reference part number '{imatch}'", 3.0))
    elif isub and n_act >= 3 and not (sc.get('module', 0) >= 3.0 and isub in ('mcu', 'rf')):
        add('ic', 1.5, ev('table', f"part number '{imatch}' ({isub})", 1.5))
    if sc.get('mounting_hole', 0) >= 3.5 and part.npads <= 1 or (sc.get('mounting_hole', 0) >= 3.5 and
                                                                  len({p.net for p in part.pins}) <= 1):
        add('mounting_hole', 1.0, ev('footprint', 'a mounting-hole footprint with one net at most', 1.0))
    if re.search(r'\bjumper\b', part.value, re.I) and part.npads <= 3:
        add('jumper', 1.0, ev('value', f"value '{part.value}'", 1.0))
    # two-terminal crystal vs oscillator: an oscillator has a supply pin
    if (sc.get('crystal') or sc.get('oscillator')) and any(PWR_PIN.match(f) or f in ('OUT', 'OUTPUT', 'CLK', 'VDD', 'VCC', 'EN', 'OE', 'ST', 'TRI-STATE')
                                                           for f in fns):
        add('oscillator', 1.5, ev('pinfunction', 'a supply or output pin (active oscillator)', 1.5))
    kind, p = softmax_pick({k: v for k, v in sc.items() if v > 0}, unknown=1.0)
    subtype = sub.get(kind, (None, 0))[0]
    if kind == 'ic':
        subtype = isub
    if kind == 'transistor' and subtype in (None, 'mosfet'):
        for k2 in ('nmos', 'pmos', 'npn', 'pnp'):
            for _, s2, _, r2 in [t for t in TEXT_RULES if t[0] == 'transistor' and t[1] == k2]:
                if r2.search(text):
                    subtype = k2
    if kind == 'connector':
        subtype = None          # set from nets later (connector_type)
    if kind == 'resistor':
        ohm = res if res is not None else shunt_ohms(text)
        if ohm is not None and 0 < ohm <= 0.2:
            subtype = 'shunt'
    return kind, subtype, p, sorted(evs.get(kind, []), key=lambda e: -e.weight)


# =============================================================================== the inference
class _Ctx:
    """Indexes shared by the role rules."""

    def __init__(self, nl: Netlist, roles: Roles):
        self.nl = nl
        self.r = roles

    def kind(self, ref):
        return self.r.parts[ref].kind

    def parts_on(self, net):
        return self.nl.parts_on(net)

    def two(self, part):
        return self.nl.two_nets(part)


def infer_roles(nl: Netlist) -> Roles:
    roles = Roles(nl=nl)
    for ref, part in nl.parts.items():
        kind, sub, p, evs = classify_part(part)
        roles.parts[ref] = PartRole(ref=ref, kind=kind, subtype=sub, role=kind, confidence=p, evidence=evs, kind_confidence=p)
    _grounds(nl, roles)
    _caps_index(nl, roles)
    _switch_nodes(nl, roles)
    _rails(nl, roles)
    _connector_types(nl, roles)
    _rail_sources(nl, roles)
    _pairs(nl, roles)
    _signal_roles(nl, roles)
    _part_roles(nl, roles)
    return roles


# ------------------------------------------------------------------------------- grounds
def _grounds(nl: Netlist, roles: Roles):
    cands = {}
    two_pin_other = Counter()
    for part in nl.parts.values():
        if roles.parts[part.ref].kind == 'capacitor':
            t = nl.two_nets(part)
            if t:
                for n in t:
                    two_pin_other[n] += 1
    for net, nv in nl.nets.items():
        s = nv.short
        if nv.nn.unconnected:
            continue
        evs = []
        if GND_NET.search(s):
            evs.append(ev('name', f"name '{s}' matches a ground pattern", STRONG + 0.5))
        elif CHASSIS_NET.search(s):
            evs.append(ev('name', f"chassis/earth/shield name '{s}'", STRONG + 0.5))
        elif GND_ANY.search(s):
            evs.append(ev('name', f"name '{s}' contains GND/VSS/EARTH/CHASSIS", MODERATE + 0.5))
        gpins = [p for p in nv.pins if GND_PIN.match(p.fn) and p.fn not in ('COM', 'SUB')]
        if gpins:
            w = min(2.5, 0.5 + 0.25 * len(gpins))
            evs.append(ev('pinfunction', f"{len(gpins)} pins named like ground ({gpins[0].label})", w))
        pin_in = [p for p in nv.pins if p.ptype == 'power_in' and GND_PIN.match(p.fn)]
        if pin_in:
            evs.append(ev('pintype', f"{len(pin_in)} ground-named pins typed power_in", 0.5))
        if two_pin_other[net] >= 3:
            evs.append(ev('topology', f"{two_pin_other[net]} two-pin capacitors touch it", min(2.0, 0.2 * two_pin_other[net])))
        if 'GND' in nv.netclass.upper():
            evs.append(ev('netclass', f"net class '{nv.netclass}'", MODERATE))
        if nl.zone_layers.get(net):
            evs.append(ev('zone', f"pour on {nl.zone_layers[net]} layer(s)", 0.5))
        if PWR_NET.search(s) and not GND_ANY.search(s):
            evs.append(ev('name', f"name '{s}' matches a rail pattern", -STRONG))
        if not evs:
            continue
        name_ev = any(e.kind == 'name' and e.weight > 0 for e in evs)
        conf = confidence(evs, prior=-2.5 if name_ev else -4.0)
        if conf >= 0.5:
            cands[net] = (conf, evs)
    if not cands:
        # no ground name: the net with the most capacitor connections and ground-named pins
        best = max(nl.nets, key=lambda n: (two_pin_other[n], len(nl.nets[n].pins)), default=None)
        if best and two_pin_other[best] >= 3:
            evs = [ev('topology', f"no ground name; most capacitor connections ({two_pin_other[best]})", 1.0)]
            cands[best] = (0.6, evs)
    order = sorted(cands, key=lambda n: (-len(nl.nets[n].pins) * (0.3 if CHASSIS_NET.search(nl.nets[n].short) else 1.0), n))
    roles.grounds = order
    roles.gnd = order[0] if order else None
    for n in order:
        conf, evs = cands[n]
        s = nl.nets[n].short
        if CHASSIS_NET.search(s) and not re.search(r'^S?GND$', s):
            subrole = 'chassis'
        elif re.search(r'AGND|GNDA|VSSA|ANA|XADC|ADCGND|AVSS|^AG$|GND_?A$', s):
            subrole = 'analog_ground'
        elif re.search(r'PGND|GNDPWR|PWR_?GND|GND_?PWR|POWER_?GND|GNDP$|GND_?MOT|MGND', s):
            subrole = 'power_ground'
        elif re.search(r'DGND|GNDD|VSSD|DVSS', s):
            subrole = 'digital_ground'
        elif re.search(r'ISO|GND2|GNDB|GND_?B$|GND_?2$|GNDI|IGND', s):
            subrole = 'isolated_ground'
        else:
            subrole = 'ground' if n == roles.gnd else 'ground_secondary'
        roles.nets[n] = NetRole(n, 'ground', subrole, conf, evs, attrs={'primary': n == roles.gnd})


def _caps_index(nl: Netlist, roles: Roles):
    """rail -> [(cap ref, ground net)] for two-pin capacitors from a net to a ground."""
    g = set(roles.grounds)
    idx = defaultdict(list)
    for part in nl.parts.values():
        if roles.parts[part.ref].kind != 'capacitor' or part.dnp:
            continue
        t = nl.two_nets(part)
        if not t:
            continue
        a, b = t
        if a in g and b not in g:
            idx[b].append((part.ref, a))
        elif b in g and a not in g:
            idx[a].append((part.ref, b))
    roles.caps_to = dict(idx)


# ------------------------------------------------------------------------------- switch nodes
def _is_power_inductor(part: Part, pr: PartRole) -> tuple[bool, float | None]:
    if pr.kind != 'inductor':
        return False, None
    h = V.inductance(part.value)
    pk = part.package
    if h is not None:
        if h < 0.1e-6:
            return False, h               # RF or filter chip inductor
        if pk.size in ('0201', '0402') and h < 1e-6:
            return False, h
        return True, h
    return pk.size not in ('0201', '0402', '0603'), None


def _switch_nodes(nl: Netlist, roles: Roles):
    g = set(roles.grounds)
    sw = {}

    def score_side(net, other, ind_ref):
        evs = []
        nv = nl.nets[net]
        sw_pins = [p for p in nv.pins if p.ref != ind_ref and SW_PIN.match(p.fn) and roles.parts[p.ref].kind in ('ic', 'module', 'transistor')]
        if sw_pins:
            evs.append(ev('pinfunction', f"switch pin {sw_pins[0].label}", STRONG + 0.5))
        fets = [p for p in nv.pins if roles.parts[p.ref].kind == 'transistor']
        if fets:
            evs.append(ev('topology', f"transistor {fets[0].ref} has a terminal on it", MODERATE + 0.5))
        diodes = [p for p in nv.pins if roles.parts[p.ref].kind == 'diode' and roles.parts[p.ref].subtype not in ('tvs', 'esd_array', 'zener')]
        if diodes:
            evs.append(ev('topology', f"rectifier {diodes[0].ref} has a terminal on it", MODERATE))
        caps = roles.caps_to.get(net, [])
        if caps:
            evs.append(ev('topology', f"{len(caps)} capacitor(s) to ground (a switch node has none)", -1.5 * min(3, len(caps))))
        pin_in = [p for p in nv.pins if (p.ptype == 'power_in' or IN_PIN.match(p.fn) or PWR_PIN.match(p.fn))
                  and roles.parts[p.ref].kind in ('ic', 'module') and not SW_PIN.match(p.fn)]
        if pin_in:
            evs.append(ev('pinfunction', f"supply pin {pin_in[0].label} on it", -2.0))
        alone = [p for p in nv.pins if p.ref != ind_ref]
        if (len(alone) == 1 and roles.parts[alone[0].ref].kind in ('ic', 'module') and not caps and len(roles.caps_to.get(other, ())) >= 2
                and alone[0].ptype != 'power_in' and not PWR_PIN.match(alone[0].fn)
                and (alone[0].ptype == 'power_out' or re.search(r'REG|LX|SW|VOUT|DCDC|SMPS|BUCK', alone[0].fn))):
            evs.append(ev('topology', f"only {alone[0].label} and the inductor on this node; far end decoupled (integrated converter output)",
                          MODERATE + 1.0))
        if re.search(r'(^|[^A-Z])(SW|LX|PH|PHASE|SW_?NODE|SWN|SWITCH_?NODE)\d?([^A-Z]|$)', nv.short) and not re.search(r'^SW\d+$|KEY|BTN|ROW|COL', nv.short):
            evs.append(ev('name', f"name '{nv.short}'", MODERATE))
        if PWR_NET.search(nv.short) or V.net_voltage(net):
            evs.append(ev('name', f"rail-like name '{nv.short}'", -2.5))
        if net in g:
            evs.append(ev('topology', 'ground', -10))
        return sum(e.weight for e in evs), evs

    for ref, part in nl.parts.items():
        pr = roles.parts[ref]
        ok, h = _is_power_inductor(part, pr)
        if not ok or part.dnp:
            continue
        t = nl.two_nets(part)
        if not t or any(n in g for n in t):
            continue
        sa, ea = score_side(t[0], t[1], ref)
        sb, eb = score_side(t[1], t[0], ref)
        (s, evs, net, other) = (sa, ea, t[0], t[1]) if sa >= sb else (sb, eb, t[1], t[0])
        both = min(sa, sb) >= 2.5      # 4-switch buck-boost: both ends switch
        if s >= 2.0:
            evs = [ev('topology', f"one end of power inductor {ref} ({part.value})", 1.0)] + evs
            sw.setdefault(net, dict(kind='inductor', inductors=[], evidence=evs, score=s))['inductors'].append(ref)
            if both:
                (s2, e2, n2) = (sb, eb, t[1]) if net == t[0] else (sa, ea, t[0])
                sw.setdefault(n2, dict(kind='inductor', inductors=[], evidence=[ev('topology', f"other end of {ref}, also switched", 1.0)] + e2,
                                       score=s2))['inductors'].append(ref)
    # discrete half-bridge midpoints: two transistors, one to a rail-ish net, one to ground or a low-ohm shunt to ground
    shunt_to_g = {}
    for ref, part in nl.parts.items():
        if roles.parts[ref].kind == 'resistor':
            o = V.resistance(part.value)
            t = nl.two_nets(part)
            if o is not None and 0 < o <= 0.2 and t:
                for k in (0, 1):
                    if t[1 - k] in g:
                        shunt_to_g[t[k]] = ref
    for net, nv in nl.nets.items():
        if net in g or net in sw:
            continue
        qs = sorted({p.ref for p in nv.pins if roles.parts[p.ref].kind == 'transistor'})
        if len(qs) < 2:
            continue
        lo, hi = [], []
        for q in qs:
            others = nl.parts[q].nets - {net}
            if others & g or others & set(shunt_to_g):
                lo.append(q)
            elif any(roles.caps_to.get(o) for o in others):
                hi.append(q)
        if lo and hi:
            # power-stage evidence: an inductor or a connector on the node, a shunt in the return, a driver IC
            # on the gates, or power packages (logic pairs and level shifters have none)
            ind = [p.ref for p in nv.pins if roles.parts[p.ref].kind == 'inductor']
            con = [p.ref for p in nv.pins if roles.parts[p.ref].kind in ('connector',)]
            shunt = any(o in shunt_to_g for q in lo for o in nl.parts[q].nets - {net})
            pkg = all(re.search(r'TO-?220|TO-?252|TO-?263|D2?PAK|PowerPAK|PowerDI|LFPAK|DFN.?5x6|PG-?HSOF|TDSON|SuperSO|SO-?8|SOIC-8|'
                                r'DirectFET|PQFN|VSONP|HSOF|Q5A|DQJ|SON5x6|TOLL', nl.parts[q].lib_id, re.I) for q in hi[:1] + lo[:1])
            drv = False
            for q in hi[:1] + lo[:1]:
                for gn in nl.parts[q].nets - {net}:
                    for p in nl.pins(gn):
                        if roles.parts[p.ref].kind == 'ic' and roles.parts[p.ref].subtype in ('gate_driver', 'motor_driver', 'regulator_switching'):
                            drv = True
            power = ind or shunt or drv or pkg or (con and pkg)
            if not power:
                continue
            evs = [ev('topology', f"{hi[0]} to a decoupled net and {lo[0]} to ground share this node", STRONG)]
            evs.append(ev('topology', 'power stage: ' + ', '.join(x for x, y in (('inductor on the node', ind), ('shunt in the return', shunt),
                                                                                   ('gate driver', drv), ('power packages', pkg)) if y), MODERATE))
            if any(SW_PIN.match(p.fn) or p.fn in ('S', 'D') for p in nv.pins):
                evs.append(ev('pinfunction', 'drain/source pins on the node', 0.5))
            if roles.caps_to.get(net):
                evs.append(ev('topology', 'capacitors to ground on the node', -2.0))
            s = sum(e.weight for e in evs)
            if s >= 2.0:
                sw[net] = dict(kind='half_bridge', transistors=qs, high=hi, low=lo, evidence=evs, score=s)
    # integrated half-bridge stages (GaN/Si power stages): a switch pin with no inductor on its net, on an IC
    # that also has a decoupled supply input and a ground
    for ref, part in nl.parts.items():
        pr = roles.parts[ref]
        if pr.kind != 'ic':
            continue
        if pr.subtype in ('fpga', 'mcu', 'memory', 'logic', 'regulator_module', 'interface', 'phy', 'sensor'):
            continue
        for p in part.active_pins():
            if not re.match(r'^(SW\d?|PH|PHASE\d?|VSW|OUT_?SW|SW_?OUT|VPH|HSW|SW_?NODE)$', p.fn) or p.net in g or p.net in sw \
                    or roles.caps_to.get(p.net):
                continue
            if any(roles.parts[q.ref].kind == 'inductor' for q in nl.pins(p.net)):
                continue
            if not any(q.ref != ref for q in nl.pins(p.net)):
                continue          # a module's internal switch node brought out to pads only
            vin = [q for q in part.active_pins() if (IN_PIN.match(q.fn) or re.match(r'^P?VIN', q.fn)) and roles.caps_to.get(q.net)]
            if vin and any(q.net in g for q in part.active_pins()):
                sw[p.net] = dict(kind='bridge_output', ic=ref, evidence=[ev('pinfunction', f"switch pin {p.label} with no inductor; supply {vin[0].label} decoupled (integrated half-bridge)", STRONG)],
                                 score=STRONG)
    # integrated bridges: output pins of motor drivers / class-D amplifiers
    for ref, part in nl.parts.items():
        pr = roles.parts[ref]
        if pr.kind != 'ic' or pr.subtype not in ('motor_driver', 'audio_amp', 'gate_driver'):
            continue
        for p in part.pins:
            if not p.net or p.net in g or p.net in sw:
                continue
            if re.match(r'^([AB]?OUT\d?[AB]?[12]?|OUT[AB+-]\d?|[AB]OUT\d|OUT\d|OUT_?[ABCUVW]\d?|SH_?[ABC]|SH[ABC]|PH_?[ABC]|[UVW]|OUT[PN]|'
                        r'OUTP[LR]?|OUTN[LR]?|SPK[+-]?\w*|[LR]OUT[PN+-]|OUT_?[LR][PN+-]?|VOUT[+-]|OUT1[AB]|OUT2[AB]|MOT\w*)$', p.fn):
                if pr.subtype == 'gate_driver' and not re.match(r'^(SH|PH)', p.fn):
                    continue
                sw[p.net] = dict(kind='bridge_output', ic=ref, evidence=[ev('pinfunction', f"bridge output pin {p.label} of {pr.subtype}", STRONG)],
                                 score=STRONG)
    # an in-line phase shunt (<= 0.2 ohm) carries the switch node on to its far side
    for net, d in list(sw.items()):
        for p in nl.pins(net):
            if roles.parts[p.ref].kind != 'resistor':
                continue
            o = V.resistance(nl.parts[p.ref].value)
            far = nl.other_net(nl.parts[p.ref], net)
            if o is not None and 0 < o <= 0.2 and far and far not in g and far not in sw and not roles.caps_to.get(far):
                sw[far] = dict(kind=d['kind'] + '_via_shunt', via=p.ref, of=net, ic=d.get('ic'),
                               evidence=[ev('topology', f"far side of in-line shunt {p.ref} from switch node '{nl.nets[net].short}'", STRONG)],
                               score=STRONG)
    roles.switch_nodes = sw
    for net, d in sw.items():
        roles.nets[net] = NetRole(net, 'switch_node', d['kind'], confidence(d['evidence'], prior=-1.0), d['evidence'], attrs={k: v for k, v in d.items() if k not in ('evidence',)})


# ------------------------------------------------------------------------------- rails
INT_OUT_PIN = rx(r'^\d+(\.\d+)?V\d*_?OUT$|^\d+V\d+$|^VREG(_?OUT)?$|^VCAP\w*|^LDO_?OUT\w*|^REG_?OUT\w*|^VDD_?CORE$|^VCORE$|^DCPL\w*|^VCP$|'
                  r'^CP_?OUT$|^VDD_?OUT$|^V_?REG$|^VREG_VOUT$|^VDD_?(1V\d|1V|2V5|1P\d)\w*_?OUT$|^AVDD_?OUT$|^VINT\w*|^VDD_?INT\w*|^BYP\w*$|^VL$')
SENSE_NAME = rx(r'SENSE|SNS|KELVIN|(^|[^A-Z])K(ELV)?$|_MON$|MONITOR|MEAS|_DIV$|DIVIDER|_ADC$|ADC_|_FB$|^FB_|VFB|_REF$|REF_')


def _rails(nl: Netlist, roles: Roles):
    g = set(roles.grounds)

    def powered_pins(pins):
        return [p for p in pins if roles.parts[p.ref].kind in ('ic', 'module', 'oscillator', 'led') and
                (p.ptype in ('power_in', 'power_out') or PWR_PIN.match(p.fn)) and not GND_PIN.match(p.fn)]
    sw = set(roles.switch_nodes)
    pd_ctrl = any(re.search(r'FUSB30|STUSB|HUSB\d|CYPD|TPS6598|IP2721|CH224|AP33771|PD controller', p.text(), re.I) for p in nl.parts.values())
    for net, nv in nl.nets.items():
        if net in g or net in sw or nv.nn.unconnected:
            continue
        s = nv.short
        evs = []
        name = bool(PWR_NET.search(s)) and not GND_ANY.search(s)
        weak = bool(PWR_WEAK.search(s))
        vname = V.net_voltage(net)
        if name:
            evs.append(ev('name', f"name '{s}' matches a rail pattern", MODERATE + 1.0))
        elif weak:
            evs.append(ev('name', f"name '{s}' contains a supply word", WEAK))
        if vname and not name:
            evs.append(ev('name', f"name '{s}' states a voltage ({vname[1]})", WEAK))
        cls = nv.netclass.upper()
        if re.search(r'POWER|PWR|VCC|VDD|\dV|BIGPOWER|HIPOWER|SUPPLY|VBUS|VIN|VOUT|BOLD|RAIL|HV\b|\bV\d|POWER_\d|AMP', cls) and 'DEFAULT' != cls:
            evs.append(ev('netclass', f"net class '{nv.netclass}'", MODERATE))
        pins = nv.pins
        # a power_out pin makes a source only on an IC or module: library symbols of connectors, fuses
        # and resistors carry power_out pins too (suite run, docs/topics/physics/suite-physics-results.md)
        p_out = [p for p in pins if p.ptype == 'power_out' and roles.parts[p.ref].kind in ('ic', 'module')]
        p_in = [p for p in pins if p.ptype == 'power_in' and roles.parts[p.ref].kind in ('ic', 'module', 'oscillator', 'led', 'crystal')
                and not GND_PIN.match(p.fn)]
        n_in_parts = len({p.ref for p in p_in})
        reg_out = [p for p in pins if OUT_PIN.match(p.fn) and roles.parts[p.ref].subtype in ('regulator_linear', 'regulator_switching', 'regulator_module', 'pmic', 'charger', 'charge_pump')]
        name_pin_in = [p for p in pins if roles.parts[p.ref].kind in ('ic', 'module', 'oscillator') and not GND_PIN.match(p.fn) and
                       ((PWR_PIN.match(p.fn) and p.ptype not in ('input', 'output', 'bidirectional')) or SUPPLY_PIN.match(p.fn))]
        caps = roles.caps_to.get(net, [])
        int_out = [p for p in pins if roles.parts[p.ref].kind in ('ic', 'module') and INT_OUT_PIN.search(p.fn) and not p_out]
        if int_out and caps:
            evs.append(ev('pinfunction', f"IC supply-output pin {int_out[0].label} with a capacitor (internal regulator)", STRONG))
            p_out = int_out
        if p_out and not int_out:
            evs.append(ev('pintype', f"power_out pin {p_out[0].label}", STRONG))
        if reg_out and not p_out:
            evs.append(ev('pinfunction', f"regulator output pin {reg_out[0].label}", STRONG))
        if p_in:
            evs.append(ev('pintype', f"power_in pins on {n_in_parts} part(s) ({p_in[0].label})", MODERATE + min(1.0, 0.3 * (n_in_parts - 1))))
        elif name_pin_in:
            evs.append(ev('pinfunction', f"supply-named pins ({name_pin_in[0].label})", MODERATE))
        if caps:
            evs.append(ev('topology', f"{len(caps)} capacitor(s) to ground", min(2.4, 0.6 * len(caps))))
        fed_rail = False
        feed = [p for p in pins if roles.parts[p.ref].kind in ('diode', 'fuse', 'ferrite') and roles.parts[p.ref].subtype not in
                ('tvs', 'esd_array', 'zener', 'led') and len(nl.parts[p.ref].nets) == 2]
        if (name or weak) and feed:
            o = nl.other_net(nl.parts[feed[0].ref], net)
            if o and (roles.caps_to.get(o) or PWR_NET.search(nl.nets[o].short)):
                evs.append(ev('topology', f"supply input: feeds '{nl.nets[o].short}' through {roles.parts[feed[0].ref].kind} {feed[0].ref}", MODERATE))
                fed_rail = True
        ind_out = [d for d in roles.switch_nodes.values() if d.get('kind') == 'inductor' and any(
            net in nl.parts[i].nets for i in d['inductors'])]
        if ind_out:
            evs.append(ev('topology', f"output side of power inductor {ind_out[0]['inductors'][0]}", STRONG))
        if nl.zone_layers.get(net):
            evs.append(ev('zone', f"pour on {nl.zone_layers[net]} layer(s)", 1.0))
        conns = [p for p in pins if roles.parts[p.ref].kind in ('connector', 'battery')]
        if conns and (name or weak):
            evs.append(ev('topology', f"on connector {conns[0].ref}", 0.5))
        powered = bool(p_out or reg_out or p_in or ind_out or name_pin_in or fed_rail)
        if CTRL_NET.search(s) and not (p_out or reg_out or ind_out or name):
            evs.append(ev('name', f"control/signal name '{s}'", -3.0))
        sig = [p for p in pins if p.ptype in ('input', 'output', 'bidirectional', 'tri_state', 'open_collector') and roles.parts[p.ref].kind in ('ic', 'module')
               and not SUPPLY_PIN.match(p.fn)]
        if sig and not powered:
            evs.append(ev('pintype', f"{len(sig)} IC pin(s) typed as logic I/O ({sig[0].label}) and none as power", -2.0))
        con_sup = [p for p in conns if re.match(r'^(VBUS|VIN|VCC|VDD|V\+|\+\d+V\w*|\d+V\w*|PWR\w*|POWER|VBAT|BAT\+|\+)$', p.fn)]
        if con_sup:
            evs.append(ev('pinfunction', f"connector supply pin {con_sup[0].label}", MODERATE))
        if len(pins) <= 2 and not nl.zone_layers.get(net) and not (p_out or reg_out) and not ((powered_pins(pins) or name or con_sup) and caps) \
                and not (feed and (name or weak)):
            evs.append(ev('count', f"only {len(pins)} pin(s)", -1.5))
        if SENSE_NAME.search(s) and not (p_out or reg_out or ind_out):
            evs.append(ev('name', f"sense/monitor name '{s}' (a Kelvin or measurement line, not a supply)", -4.0))
        iface_, _ = name_iface(s)
        if iface_ and iface_ not in ('i2c', 'uart') and not name and not weak:
            evs.append(ev('name', f"interface name ({iface_})", -2.5))
        filt = [p for p in pins if roles.parts[p.ref].kind in ('ferrite', 'inductor') and roles.parts[p.ref].ref not in
                {i for d in roles.switch_nodes.values() for i in d.get('inductors', [])}]
        if caps and filt:
            o = nl.other_net(nl.parts[filt[0].ref], net)
            if o and o not in g and (roles.caps_to.get(o) or PWR_NET.search(nl.nets[o].short)):
                evs.append(ev('topology', f"{roles.parts[filt[0].ref].kind} {filt[0].ref} from '{nl.nets[o].short}' with capacitors on both "
                                          f"sides (filtered supply branch)", MODERATE))
                powered = True
        strong = name or powered or len(caps) >= 2 or bool(nl.zone_layers.get(net)) or (vname is not None and len(caps) >= 1)
        if SENSE_NAME.search(s) and not (p_out or reg_out or ind_out):
            strong = False
        if not strong:
            continue
        conf = confidence(evs, prior=-2.5)
        if conf < 0.5:
            continue
        nr = NetRole(net, 'rail', None, conf, evs)
        nr.attrs['volts'] = _rail_voltage(nl, roles, net, vname, pd_ctrl)
        roles.rails[net] = nr
        roles.nets[net] = nr
    # sub-roles
    for net, nr in roles.rails.items():
        s = nl.nets[net].short
        if re.search(r'VBUS|USB_?5V|VUSB|USB_?PWR|USB_?VCC', s):
            nr.subrole = 'usb_vbus'
        elif re.search(r'VBAT|BATT?|CELL|LIPO|LIION', s):
            nr.subrole = 'battery'
        elif any(OUT_PIN.match(p.fn) or p.ptype == 'power_out' for p in nl.nets[net].pins):
            nr.subrole = 'regulated'
        elif re.search(r'VIN|IN$|_IN|RAW|DC_?IN|PWR_?IN|VCC_?IN|EXT', s):
            nr.subrole = 'input'
        elif re.search(r'^-|NEG|VEE', s):
            nr.subrole = 'negative'
        else:
            nr.subrole = 'rail'


def _rail_sources(nl: Netlist, roles: Roles):
    """Where each rail comes from: a regulator or converter output, a connector or battery, a series part
    from another rail (derived), an IC's own supply output (internal: core LDO, VCAP), or unknown.
    A rail without a stated voltage inherits one through a series part (fuse, bead, 0 ohm, switch;
    a diode costs ~0.4 V)."""
    g = set(roles.grounds)
    ind_out = {}
    for net, d in roles.switch_nodes.items():
        for L in d.get('inductors', []):
            o = nl.other_net(nl.parts[L], net)
            if o:
                ind_out[o] = (L, net)
    series = defaultdict(list)          # rail -> [(part, upstream net, kind)]
    for ref, part in nl.parts.items():
        pr = roles.parts[ref]
        t = nl.two_nets(part)
        if not t or len(part.active_pins()) > 3:
            continue
        a, b = t
        if a in g or b in g:
            continue
        k = pr.kind
        ohm = V.resistance(part.value) if k == 'resistor' else None
        if k in ('ferrite', 'fuse', 'jumper', 'net_tie') or (k == 'resistor' and ohm is not None and ohm <= 1.0) or \
                (k == 'inductor' and not any(ref in d.get('inductors', []) for d in roles.switch_nodes.values())):
            series[a].append((ref, b, k))
            series[b].append((ref, a, k))
        elif k == 'diode' and pr.subtype not in ('tvs', 'esd_array', 'zener'):
            for x, y in ((a, b), (b, a)):
                for p in part.pins_on(x):
                    if p.fn in ('K', 'CATHODE') or (p.number == '1' and not p.fn.isalpha()) or p.fn == '1':
                        series[x].append((ref, y, 'diode'))
    for net, nr in roles.rails.items():
        pins = nl.nets[net].pins
        src = None
        reg = [p for p in pins if roles.parts[p.ref].subtype in ('regulator_linear', 'regulator_switching', 'regulator_module', 'pmic',
                                                                    'charger', 'charge_pump', 'load_switch')
               and (OUT_PIN.match(p.fn) or p.ptype == 'power_out')]
        # a charger's battery pin is its output (MCP73831 VBAT, BQ24075 BAT, TP4056 BAT)
        reg += [p for p in pins if roles.parts[p.ref].subtype == 'charger' and re.match(r'^(V?BAT\w*|BATT?\+?)$', p.fn) and p not in reg]
        if reg:
            src = {'kind': 'regulator', 'ref': reg[0].ref, 'pin': reg[0].number}
        elif net in ind_out:
            src = {'kind': 'converter', 'ref': ind_out[net][0], 'switch_node': ind_out[net][1]}
        else:
            bat = [p for p in pins if roles.parts[p.ref].kind == 'battery']
            con = [p for p in pins if roles.parts[p.ref].kind == 'connector']
            con.sort(key=lambda p: (roles.parts[p.ref].subtype not in ('power', 'usb'), p.ref))
            internal = [p for p in pins if roles.parts[p.ref].kind in ('ic', 'module') and (p.ptype == 'power_out' or INT_OUT_PIN.search(p.fn))]
            act = {p.ref for p in pins if roles.parts[p.ref].kind not in ('capacitor', 'test_point')}
            # an auto-named net ('Net-(U22-VDD)') that only one IC and capacitors touch is that IC's own node;
            # a named rail ('+3V3') in the same state is fed from somewhere the board does not show
            only_ic = len(act) == 1 and roles.parts[next(iter(act))].kind in ('ic', 'module') and nl.nets[net].nn.auto
            if bat:
                src = {'kind': 'battery', 'ref': bat[0].ref}
            elif internal:
                src = {'kind': 'internal', 'ref': internal[0].ref, 'pin': internal[0].number}
            elif only_ic:
                ic = next(iter(act))
                p0 = next(p for p in pins if p.ref == ic)
                src = {'kind': 'internal', 'ref': ic, 'pin': p0.number,
                       'note': 'only this IC and capacitors on the rail: its own regulator output or bypass node'}
            elif series.get(net):
                up = [x for x in series[net] if x[1] in roles.rails or x[1] in roles.nets]
                if up:
                    ref, upn, k = up[0]
                    src = {'kind': 'derived', 'ref': ref, 'upstream': upn, 'via': k}
            if src is None and con:
                src = {'kind': 'connector', 'ref': con[0].ref, 'note': 'source or export, undecided'}
            if src is None:
                src = {'kind': 'unknown'}
        nr.attrs['source'] = src
    # voltage through series parts
    for _ in range(3):
        for net, nr in roles.rails.items():
            vb = nr.attrs.get('volts')
            if vb and vb.get('value') is not None:
                continue
            src = nr.attrs.get('source') or {}
            up = src.get('upstream')
            if src.get('kind') == 'derived' and up in roles.rails:
                ub = roles.rails[up].attrs.get('volts') or {}
                if ub.get('value') is not None:
                    v = ub['value'] - (0.4 if src.get('via') == 'diode' else 0.0)
                    nr.attrs['volts'] = belief(round(v, 3), 'V', f"inherited from '{nl.nets[up].short}' through {src['ref']} ({src['via']})",
                                               round(v * 0.9, 3), round(ub['interval'][1] if ub.get('interval') else v * 1.05, 3),
                                               lineage=[ub.get('relative_to', '')])


def belief(value, unit, src, lo=None, hi=None, exactness='E5', lineage=()):
    """A prior as JSON in the shape of physics-core-v2-api `Belief` (value, unit, exactness, relative_to, interval)."""
    d = {'value': value, 'unit': unit, 'exactness': exactness, 'relative_to': src}
    if lo is not None and hi is not None:
        d['interval'] = [lo, hi]
    if lineage:
        d['lineage'] = list(lineage)
    return d


def _rail_voltage(nl, roles, net, vname, pd_ctrl):
    s = nl.nets[net].short
    srcs = []
    if vname:
        v = vname[0]
        srcs.append(('name', v, f"net name '{s}' ({vname[1]})", abs(v) * 0.95, abs(v) * 1.05))
    for p in nl.nets[net].pins:
        pr = roles.parts.get(p.ref)
        if pr and pr.subtype in ('regulator_linear', 'regulator_switching', 'regulator_module') and (OUT_PIN.match(p.fn) or p.ptype == 'power_out'):
            rv = regulator_vout(nl.parts[p.ref].text())
            if rv:
                srcs.append(('regulator', rv[0], f"{p.ref} part number '{rv[1]}'", abs(rv[0]) * 0.97, abs(rv[0]) * 1.03))
    if re.search(r'VBUS|USB_?5V|VUSB', s) and not vname:
        if pd_ctrl:
            srcs.append(('usb', 5.0, 'USB VBUS with a power-delivery controller on the board', 4.4, 20.0))
        else:
            srcs.append(('usb', 5.0, 'USB VBUS (5 V nominal)', 4.4, 5.5))
    if re.search(r'VBAT|BATT|LIPO|LIION', s) and not vname:
        srcs.append(('battery', 3.7, 'battery rail, single Li-ion cell assumed', 3.0, 4.2))
    if not srcs:
        for p in nl.nets[net].pins:
            if roles.parts[p.ref].kind in ('connector', 'battery'):
                part = nl.parts[p.ref]
                cv = V.net_voltage(part.value) or V.net_voltage(part.refdes)
                if cv and abs(cv[0]) <= 60:
                    srcs.append(('connector', cv[0], f"connector {part.refdes} value '{part.value}'", abs(cv[0]) * 0.9, abs(cv[0]) * 1.1))
                    break
    ratings = []
    for cref, _ in roles.caps_to.get(net, []):
        part = nl.parts[cref]
        r = V.rated_voltage(part.fields.get('Voltage') or '') or V.rated_voltage(part.value)
        if r:
            ratings.append((r, cref))
    cap_hi = min(ratings) if ratings else None
    if not srcs:
        if cap_hi:
            # designers derate ceramics and electrolytics by 1.25-3x: the rail most likely sits near rating/1.6
            return belief(round(cap_hi[0] / 1.6, 2), 'V', f"estimate: lowest capacitor rating on the rail ({cap_hi[1]}, {cap_hi[0]:g} V) / 1.6",
                          round(cap_hi[0] / 3.0, 2), cap_hi[0], lineage=['capacitor-rating estimate'])
        return None
    best = srcs[0]
    lineage = [x[2] for x in srcs]
    lo, hi = best[3], best[4]
    for x in srcs[1:]:
        if abs(abs(x[1]) - abs(best[1])) > 0.1 * abs(best[1]):
            lo, hi = min(lo, x[3]), max(hi, x[4])
            lineage.append(f"conflict: {x[0]} says {x[1]:g} V")
    if cap_hi:
        lineage.append(f"capacitor {cap_hi[1]} rated {cap_hi[0]:g} V")
        if cap_hi[0] < abs(best[1]):
            lineage.append('capacitor rating below the nominal voltage: check the name')
    return belief(best[1], 'V', best[2], round(lo, 3), round(hi, 3), lineage=lineage)


# ------------------------------------------------------------------------------- connectors
def connector_type(nl: Netlist, roles: Roles, part: Part) -> tuple[str, list]:
    t = f"{part.lib_id} {part.value} {part.description}"
    fns = {p.fn for p in part.pins}
    nets = [nl.nets[p.net].short for p in part.pins if p.net and p.net in nl.nets]
    evs = []

    def r(pat):
        return re.search(pat, t, re.I)
    rules = [
        ('rf', r'Coax|(^|[_: ])SMA\b|SMA_|U\.?FL|IPEX|MMCX|BNC|SMPM|SMP_|subclick|Conn_Coaxial|MHF\d|W\.FL'),
        ('usb', r'USB|TYPE-?C|Type_?C|USB4105|HRO.?TYPE|MINI-USB|Micro_?B'),
        ('ethernet', r'RJ45|MagJack|LPJ\d|MTJ-\d|TRJ\d|RJ-45|8P8C|ARJ\d|J0011'),
        ('hdmi', r'HDMI|DisplayPort|\bDVI\b'),
        ('power', r'BarrelJack|Barrel_Jack|DC_?Jack|JACK_ALIM|Power_Jack|PowerJack|XT30|XT60|XT90|ATX12V|PCIE_PWR|PWR_?IN|Eurorack_Power|'
                  r'EURO_?PWR|Euro.?Power|powertab|PowerOne|MiniFit.*PWR|\bDC IN\b|DC_IN|\bPOWER\b|PWR\b|\bBATT?\b|Battery|Solar'),
        ('audio', r'AudioJack|Jack_3\.5|Jack_6\.35|\bTRRS\b|\bTRS\b|XLR|Audio|Phone_?Jack|SJ-\d{4}|PJ-3\d\d|MIDI|DIN5'),
        ('card', r'microSD|Micro_?SD|SD_?Card|SDCARD|\bSIM\b|SIM_|TF_?Card'),
        ('debug', r'SWD|JTAG|Tag-?Connect|TC20[35]0|Cortex|DEBUG|\bPROG|ICSP|UPDI|STDC14|SOICBite|ESP-?Prog|FTSH-1\d\d|SHF-1'),
        ('board_to_board', r'FMC|Samtec_ASP|DF40|M\.2|PCIe|PCI_?Express|PCBEdge|PCB-Edge|SODIMM|CardEdge|Mezzanine|Board_[AB]|B2B|Bus_PCI'),
        ('ffc_fpc', r'FFC|FPC'),
        ('sfp', r'SFP|QSFP'),
        ('header', r'PinHeader|PinSocket|Pin_Header|Socket_Strip|IDC-Header|IDC_Header|HDR-|Conn_0[12]x|CONN_0[12]X|Header|PinHd'),
        ('wire_to_board', r'JST|Molex|TerminalBlock|Terminal_?Block|Screw|Phoenix|Wuerth_6|WJ\d{3}|KF\d{3}|Micro-Fit|PicoBlade|Pico-Lock|wire2board|'
                          r'SolderWirePad|Wire_Pads|WirePad|Solderpad|Pad_D'),
    ]
    for typ, pat in rules:
        m = r(pat)
        if m:
            evs.append(ev('lib_id', f"'{m.group(0)}' in footprint/value", MODERATE))
            ctype = typ
            break
    else:
        ctype = None
    # pins and nets refine or decide
    if {'VBUS', 'CC1', 'CC2'} & fns or ({'D+', 'D-'} <= fns) or ({'DP', 'DM'} <= fns):
        evs.append(ev('pinfunction', 'USB pin functions (VBUS/CC/D+/D-)', STRONG))
        ctype = 'usb'
    if any(re.search(r'^(TD|RD|TX|RX|TRD|MDI)\d?[+-]', f) for f in fns) and ctype in (None, 'header', 'ethernet'):
        evs.append(ev('pinfunction', 'Ethernet pair pin functions', MODERATE))
        ctype = 'ethernet'
    sw_nets = [n for n in nets if re.search(r'SWDIO|SWCLK|^TCK$|^TMS$|^TDI$|^TDO$|JTAG|SWD|UPDI', n)]
    n_sig = len({p.net for p in part.pins if p.net and p.net not in roles.grounds and p.net not in roles.rails}) or 1
    if len(sw_nets) >= 2 and len(sw_nets) >= 0.3 * n_sig and ctype in (None, 'header', 'wire_to_board'):
        evs.append(ev('name', f"debug nets ({', '.join(sw_nets[:3])})", MODERATE))
        ctype = 'debug'
    can = [n for n in nets if re.search(r'CAN_?[HL]$|CANH|CANL|CAN.*[_.](H|L|DP|DN|P|N)$', n)]
    if len(can) >= 2 and ctype in (None, 'header', 'wire_to_board'):
        evs.append(ev('name', 'CAN_H/CAN_L nets', MODERATE))
        ctype = 'can'
    act = [p for p in part.pins if p.net and not p.nc]
    pw = [p for p in act if p.net in roles.rails or p.net in roles.grounds]
    rails_on = {p.net for p in act if p.net in roles.rails}
    if act and rails_on and len(pw) >= 0.6 * len(act) and len({p.net for p in act}) <= 6 and ctype in (None, 'header', 'wire_to_board'):
        evs.append(ev('topology', f"{len(pw)}/{len(act)} pins on rails or ground ({', '.join(sorted(nl.nets[n].short for n in rails_on))[:60]})", MODERATE))
        ctype = 'power'
    if ctype is None:
        ctype = 'header' if part.npads >= 3 else 'wire_to_board'
        evs.append(ev('count', f"{part.npads} pads, no type keyword", 0.0))
    return ctype, evs


def _connector_types(nl: Netlist, roles: Roles):
    for ref, part in nl.parts.items():
        pr = roles.parts[ref]
        if pr.kind == 'connector':
            ct, evs = connector_type(nl, roles, part)
            pr.subtype = ct
            pr.evidence = pr.evidence + evs


# ------------------------------------------------------------------------------- differential pairs
def _pairs(nl: Netlist, roles: Roles):
    by_key = defaultdict(list)
    for net, nv in nl.nets.items():
        if net in roles.rails or net in roles.grounds or nv.nn.unconnected:
            continue
        s = nv.short
        if not s or nv.nn.auto:
            continue
        for i, ch in enumerate(s):
            if ch in POLARITY:
                by_key[(s[:i], s[i + 1:])].append((ch, net))
    seen = set()
    pairs = []
    for (pre, post), lst in by_key.items():
        chars = {c: n for c, n in lst}
        for c, o in COMPLEMENTS:
            if c not in chars or o not in chars:
                continue
            n, m = chars[c], chars[o]
            key = tuple(sorted((n, m)))
            if key in seen or n == m:
                continue
            base = (pre + '*' + post)
            evs = []
            ok_pol = True
            if c in 'HL' and not re.search(r'CAN', base):
                ok_pol = False
            if c in 'AB' and not re.search(r'485|RS_?$|MODBUS|DMX', base):
                ok_pol = False
            if c in 'TC' and not re.search(r'CLK|CK', base):
                ok_pol = False
            if o == 'M' and not re.search(r'D\*|USB', base):
                ok_pol = False
            if c == 'P':
                # the polarity letter must be a token of its own (_P, P$, DP, TXP), not inside a word
                left = pre[-1:] if pre else ''
                right = post[:1] if post else ''
                if right and right.isalpha():
                    ok_pol = False
                if left and left.isalpha() and left not in 'DXTKRSL' and not re.search(r'(TX|RX|CLK|CK|DQS|REFCLK|D|DAT|DATA|LANE)$', pre):
                    ok_pol = False
            if not ok_pol:
                continue
            seen.add(key)
            evs.append(ev('name', f"names '{nl.nets[n].short}'/'{nl.nets[m].short}' differ only in polarity", MODERATE))
            pa, pb = nl.nets[n], nl.nets[m]
            common = (pa.refs & pb.refs)
            ics = [r for r in common if roles.parts[r].kind in ('ic', 'module', 'connector')]
            if ics:
                evs.append(ev('topology', f"both nets reach {', '.join(sorted(ics)[:3])}", MODERATE))
            else:
                evs.append(ev('topology', 'no common IC or connector', -1.0))
            cl = (pa.netclass + ' ' + pb.netclass).upper()
            if re.search(r'DIFF|ZDIFF|90R|100R|85R|USB|LVDS|PCIE|MDI|HDMI|TMDS|CLK DIFF|DDR DIFF|MGT|SERDES', cl):
                evs.append(ev('netclass', f"net class '{pa.netclass}'", MODERATE))
            pfa = {p.fn for p in pa.pins}
            pfb = {p.fn for p in pb.pins}
            if any(re.search(r'[+PN-]$|D[PMN]$', f) for f in pfa) and any(re.search(r'[+PN-]$|D[PMN]$', f) for f in pfb):
                evs.append(ev('pinfunction', 'complementary pin functions on the pair', WEAK))
            if any(roles.parts[r].kind in ('resistor', 'led', 'diode') and len(nl.parts[r].nets) == 2 and {n, m} <= nl.parts[r].nets for r in common):
                if not any(roles.parts[r].kind == 'resistor' and 80 <= (V.resistance(nl.parts[r].value) or 0) <= 150 for r in common):
                    evs.append(ev('topology', 'a two-pin part spans the pair (LED or load, not a pair)', -1.5))
            iface, speed = name_iface(pa.short)
            if iface is None:
                iface, speed = name_iface(base.replace('*', 'P'))
            iface, speed = iface or 'unknown', speed or 'unknown'
            if iface == 'unknown' and cl.strip():
                iface, speed = name_iface(cl, skip=('i2c', 'uart', 'debug', 'spi', 'mdio'))
                iface, speed = iface or 'unknown', speed or 'unknown'
                if iface == 'unknown' and 'CAN' in cl:
                    iface, speed = 'can', 'ls'
            if iface in ('i2c', 'uart', 'debug', 'spi', 'mdio'):
                continue
            if iface == 'unknown':
                if re.search(r'CLK|CK', base):
                    iface, speed = 'clock', 'hs'
                elif any(OPAMP_IN_PIN.match(f) or ANALOG_PIN.match(f) for f in pfa | pfb) or ANALOG_NET.search(base):
                    iface, speed = 'analog', 'analog'
            if iface == 'unknown':
                evs.append(ev('name', 'no interface keyword', -0.5))
            conf = confidence(evs, prior=-0.5)
            if conf < 0.5:
                continue
            pairs.append(DiffPair(p=n, n=m, interface=iface, speed=speed, confidence=conf, evidence=evs))
    roles.pairs = pairs


# ------------------------------------------------------------------------------- clocks, high speed, analog, rf, reset, signal
def _signal_roles(nl: Netlist, roles: Roles):
    g = set(roles.grounds)
    pair_of = {}
    for dp in roles.pairs:
        pair_of[dp.p] = dp
        pair_of[dp.n] = dp
    xtal_nets = {}
    osc_out = {}
    for ref, part in nl.parts.items():
        pr = roles.parts[ref]
        if pr.kind == 'crystal':
            for p in part.active_pins():
                if p.net not in g:
                    xtal_nets[p.net] = ref
        if pr.kind == 'oscillator':
            for p in part.active_pins():
                if p.net not in g and p.net not in roles.rails and re.match(r'^(OUT\w*|CLK\w*|OUTPUT|3|Q|FOUT)$', p.fn or p.number):
                    osc_out[p.net] = ref
    opamp_in = {}
    for ref, part in nl.parts.items():
        pr = roles.parts[ref]
        if pr.kind == 'ic' and pr.subtype in ('opamp', 'adc_dac', 'current_sense'):
            for p in part.active_pins():
                if p.net in g or p.net in roles.rails:
                    continue
                if OPAMP_IN_PIN.match(p.fn) or (pr.subtype != 'opamp' and ANALOG_PIN.match(p.fn)):
                    opamp_in[p.net] = (ref, p)
    for net, nv in nl.nets.items():
        if net in roles.nets:          # ground, rail, switch node
            continue
        s = nv.short
        cands = {}

        def add(role, sub, evs, prior=-1.0, **attrs):
            c = confidence(evs, prior)
            if c >= 0.5 and (role not in cands or c > cands[role][0]):
                cands[role] = (c, sub, evs, attrs)
        if nv.nn.unconnected or (len(nv.pins) <= 1 and not nv.netclass):
            roles.nets[net] = NetRole(net, 'no_connect', 'single_pin', 0.95, [ev('count', f"{len(nv.pins)} pin(s)", 3.0)])
            continue
        pins = nv.pins
        fns = [p.fn for p in pins]
        # RF
        evs = []
        if RF_NET.search(s):
            evs.append(ev('name', f"name '{s}'", MODERATE))
        rfp = [p for p in pins if RF_PIN.search(p.fn) and roles.parts[p.ref].kind in ('ic', 'module')]
        if rfp:
            evs.append(ev('pinfunction', f"RF pin {rfp[0].label}", STRONG))
        ant = [p for p in pins if roles.parts[p.ref].kind == 'antenna' or (roles.parts[p.ref].kind == 'connector' and roles.parts[p.ref].subtype == 'rf')]
        if ant:
            evs.append(ev('topology', f"{roles.parts[ant[0].ref].kind} {ant[0].ref}", STRONG))
        if evs:
            add('rf', 'rf', evs, prior=-1.5)
        # clocks
        evs = []
        if net in xtal_nets:
            evs.append(ev('topology', f"crystal {xtal_nets[net]} terminal", STRONG + 1))
        if net in osc_out:
            evs.append(ev('topology', f"oscillator {osc_out[net]} output", STRONG + 1))
        xp = [p for p in pins if XTAL_PIN.search(p.fn) and not re.search(r'SWCLK|TCK|JTAG', p.fn) and roles.parts[p.ref].kind in ('ic', 'module')]
        if xp:
            evs.append(ev('pinfunction', f"clock pin {xp[0].label}", MODERATE))
        if CLOCK_NET.search(s) and not re.search(r'SCL|I2C|SWCLK|SWDCLK|TCK|JTAG|SWD', s):
            evs.append(ev('name', f"name '{s}'", MODERATE))
        if evs:
            sub = 'xtal' if net in xtal_nets else 'oscillator_out' if net in osc_out else (
                'diff_clock' if net in pair_of else 'bus_clock' if re.search(r'SCK|SCLK|SPI|QSPI|SD|MMC|BCLK|LRCLK|MCLK', s) else 'clock')
            add('clock', sub, evs, prior=-1.0, source=xtal_nets.get(net) or osc_out.get(net))
        # high-speed interfaces and pairs
        evs = []
        iface, speed = name_iface(s)
        dp = pair_of.get(net)
        if dp and dp.interface not in ('analog',):
            iface, speed = dp.interface if dp.interface != 'unknown' else iface, dp.speed if dp.speed != 'unknown' else speed
            evs.append(ev('topology', f"member of differential pair {dp.p}/{dp.n}", MODERATE))
        if iface and speed in ('gbps', 'hs', 'medium'):
            evs.append(ev('name', f"interface keyword in '{s}' ({iface})", MODERATE))
            cl = nv.netclass.upper()
            if re.search(r'DIFF|ZDIFF|USB|LVDS|PCIE|MDI|HDMI|DDR|DRAM|SDRAM|RGMII|MGT|OCTOSPI|QSPI|SDIO|HS', cl):
                evs.append(ev('netclass', f"net class '{nv.netclass}'", MODERATE))
            if iface == 'usb2' and not any(roles.parts[p.ref].subtype == 'usb' or re.search(r'USB|D[+-PMN]$|DP|DM', p.fn) for p in pins):
                evs.append(ev('topology', 'no USB connector or USB-named pin on the net', -1.0))
            add('high_speed', iface, evs, prior=-0.5, interface=iface, speed=speed)
        # analog-sensitive
        evs = []
        if ANALOG_NET.search(s) and not re.search(r'REFCLK|SCK|CLK', s):
            evs.append(ev('name', f"name '{s}'", MODERATE))
        ap = [p for p in pins if ANALOG_PIN.match(p.fn) and roles.parts[p.ref].kind in ('ic', 'module') and p.fn not in ('-', '+')
              and roles.parts[p.ref].subtype not in ('logic', 'memory')]
        if ap:
            evs.append(ev('pinfunction', f"analog pin {ap[0].label}", MODERATE))
        if net in opamp_in:
            ref, p = opamp_in[net]
            evs.append(ev('topology', f"input of {roles.parts[ref].subtype} {ref} ({p.label})", STRONG))
        if net in xtal_nets:
            evs.append(ev('topology', 'crystal terminal (high impedance)', MODERATE))
        if evs:
            sub = 'adc_input' if re.search(r'ADC|AIN|AN\d', s + ' '.join(fns)) else 'reference' if re.search(r'REF', s + ' '.join(fns)) else (
                'feedback' if re.search(r'(^|[^A-Z])V?FB|COMP', s + ' ' + ' '.join(fns)) else 'sense' if re.search(r'SENSE|SNS|CS[PN+-]|ISNS|IMON|SHUNT|CURR', s + ' '.join(fns))
                else 'audio' if re.search(r'AUDIO|MIC|LINE|HP|SPDIF|DRY|WET|MIX|VOL|PREAMP', s) else 'opamp_input' if net in opamp_in else 'analog')
            add('analog', sub, evs, prior=-1.5)
        # reset / boot
        evs = []
        if RESET_NET.search(s):
            evs.append(ev('name', f"name '{s}'", MODERATE))
        rp = [p for p in pins if RESET_PIN.match(p.fn) and roles.parts[p.ref].kind in ('ic', 'module') and roles.parts[p.ref].subtype not in ('regulator_linear', 'regulator_switching', 'regulator_module', 'load_switch', 'charger', 'pmic')]
        if rp:
            evs.append(ev('pinfunction', f"reset pin {rp[0].label}", MODERATE))
        if evs:
            add('reset', 'reset', evs, prior=-1.0)
        evs = []
        if BOOT_NET.search(s):
            evs.append(ev('name', f"name '{s}'", MODERATE))
        bp = [p for p in pins if BOOTSEL_PIN.match(p.fn) and roles.parts[p.ref].kind in ('ic', 'module') and roles.parts[p.ref].subtype in ('mcu', 'fpga', None)]
        if bp:
            evs.append(ev('pinfunction', f"boot-strap pin {bp[0].label}", WEAK + 0.3))
        if evs:
            add('boot', 'boot', evs, prior=-1.0)
        order = ('rf', 'clock', 'high_speed', 'analog', 'reset', 'boot')
        best = next((r for r in order if r in cands), None)
        if best is None:
            sub, _ = name_iface(s)
            if sub is None:
                sub = 'auto' if nv.nn.auto else 'signal'
            roles.nets[net] = NetRole(net, 'signal', sub, 0.6, [ev('derived', 'no specific role matched', 0.0)],
                                      attrs={'interface': sub} if sub not in ('auto', 'signal') else {})
            continue
        c, sub, evs, attrs = cands[best]
        nr = NetRole(net, best, sub, c, evs, attrs=dict(attrs))
        nr.tags = {r: round(cands[r][0], 3) for r in cands if r != best}
        if net in pair_of:
            dp = pair_of[net]
            nr.attrs['pair'] = dp.n if net == dp.p else dp.p
        roles.nets[net] = nr
    # pairs: tag rails/grounds never; record interface on pair members already roled as clock etc.
    for dp in roles.pairs:
        for n in (dp.p, dp.n):
            nr = roles.nets.get(n)
            if nr and 'pair' not in nr.attrs:
                nr.attrs['pair'] = dp.n if n == dp.p else dp.p


# ------------------------------------------------------------------------------- local part roles
def cap_class(part: Part) -> tuple[str, float | None, list]:
    """('hf' | 'mid' | 'bulk', farads, evidence) for a rail capacitor, from value and body."""
    c = V.capacitance(part.value)
    if c is None:
        c = V.capacitance(str(part.fields.get('Capacitance') or part.fields.get('Val') or ''))
    pk = part.package
    evs = []
    if pk.polarized:
        evs.append(ev('footprint', f"polarized body '{pk.text}'", STRONG))
        return 'bulk', c, evs
    if c is not None:
        if c <= 1.0e-6 + 1e-12:
            evs.append(ev('value', f"{V.si(c, 'F')} (<= 1 uF)", MODERATE))
            return 'hf', c, evs
        if c >= 4.7e-6 - 1e-12:
            evs.append(ev('value', f"{V.si(c, 'F')} (>= 4.7 uF)", MODERATE))
            return 'bulk', c, evs
        evs.append(ev('value', f"{V.si(c, 'F')} (between 1 and 4.7 uF)", WEAK))
        return 'mid', c, evs
    if pk.size in ('01005', '0201', '0402', '0603'):
        evs.append(ev('footprint', f"value unreadable; {pk.size} body", WEAK))
        return 'hf', None, evs
    if pk.size in ('1206', '1210', '1812', '2220') or pk.through_hole:
        evs.append(ev('footprint', f"value unreadable; large body '{pk.text}'", WEAK))
        return 'bulk', None, evs
    evs.append(ev('value', 'value and body unreadable', 0.0))
    return 'mid', None, evs


def _part_roles(nl: Netlist, roles: Roles):
    g = set(roles.grounds)
    rails = set(roles.rails)
    for ref, part in nl.parts.items():
        pr = roles.parts[ref]
        k = pr.kind
        t = nl.two_nets(part)
        evs = []
        role = k
        if k == 'capacitor' and t:
            a, b = t
            if (a in g) != (b in g):
                other = b if a in g else a
                cls, farads, cevs = cap_class(part)
                pr.attrs['farads'] = farads
                pr.attrs['class'] = cls
                if other in rails or roles.caps_to.get(other) and len(roles.caps_to[other]) >= 1 and other not in roles.switch_nodes:
                    if other in rails:
                        role = 'bulk' if cls == 'bulk' else 'decoupling'
                        evs = [ev('topology', f"between rail '{nl.nets[other].short}' and ground '{nl.nets[b if a == other else a].short}'", STRONG)] + cevs
                    else:
                        role = 'filter_to_ground'
                        evs = [ev('topology', f"from signal net '{nl.nets[other].short}' to ground", MODERATE)] + cevs
                if roles.nets.get(other) and roles.nets[other].role == 'clock' and roles.nets[other].subrole == 'xtal':
                    role = 'crystal_load'
                    evs = [ev('topology', f"from crystal net '{nl.nets[other].short}' to ground", STRONG)] + cevs
                if a in g and b in g:
                    role = 'ground_tie'
            elif a in g and b in g:
                role = 'ground_tie'
                evs = [ev('topology', 'between two ground nets', STRONG)]
            elif a in rails and b in rails:
                role = 'rail_to_rail'
                evs = [ev('topology', 'between two rails', MODERATE)]
            else:
                role = 'series_or_coupling'
                if a in roles.switch_nodes or b in roles.switch_nodes:
                    role = 'bootstrap_or_snubber'
                evs = [ev('topology', 'between two non-ground nets', WEAK)]
        elif k == 'resistor' and t and len(part.active_pins()) <= 2:
            ohm = V.resistance(part.value)
            if ohm is None:
                ohm = shunt_ohms(part.text())
            pr.attrs['ohms'] = ohm
            a, b = t
            if ohm is not None and 0 < ohm <= 0.2:
                role = 'shunt'
                evs = [ev('value', f"{V.si(ohm, 'Ω')} (<= 0.2 ohm)", STRONG)]
            elif ohm == 0:
                role = 'zero_ohm'
                evs = [ev('value', '0 ohm', STRONG)]
            elif (a in rails or b in rails) and not (a in g or b in g):
                sig = b if a in rails else a
                if sig in rails:
                    role = 'series_power'
                    evs = [ev('topology', 'between two rails', MODERATE)]
                else:
                    role = 'pull_up'
                    evs = [ev('topology', f"from rail to '{nl.nets[sig].short}'", MODERATE)]
            elif (a in g) != (b in g):
                sig = b if a in g else a
                role = 'pull_down'
                evs = [ev('topology', f"from '{nl.nets[sig].short}' to ground", WEAK)]
                if sig in roles.nets and roles.nets[sig].role == 'switch_node':
                    role = 'snubber'
            else:
                role = 'series'
                evs = [ev('topology', 'between two signal nets', WEAK)]
                sa, sb = roles.nets.get(a), roles.nets.get(b)
                if ohm is not None and 80 <= ohm <= 150 and any(dp for dp in roles.pairs if {dp.p, dp.n} == {a, b}):
                    role = 'termination'
                    evs = [ev('topology', 'across a differential pair', STRONG)]
                elif any(x and x.role == 'high_speed' for x in (sa, sb)) and ohm is not None and ohm <= 100:
                    role = 'series_termination'
                    evs.append(ev('value', f"{V.si(ohm, 'Ω')} on a high-speed net", MODERATE))
        elif k == 'resistor' and len(part.active_pins()) >= 3:
            ohm = V.resistance(part.value)
            if ohm is None:
                ohm = shunt_ohms(part.text())
            if ohm is not None and ohm <= 0.2:
                role = 'shunt'
                pr.attrs['ohms'] = ohm
                evs = [ev('value', f"{V.si(ohm, 'Ω')}, four terminals (Kelvin)", STRONG)]
        elif k == 'ic':
            sub = pr.subtype or 'ic'
            role = {'regulator_linear': 'regulator', 'regulator_switching': 'regulator', 'regulator_module': 'regulator',
                    'charge_pump': 'regulator', 'pmic': 'regulator', 'charger': 'charger'}.get(sub, sub)
            if sub in ('regulator_linear', 'regulator_switching', 'regulator_module', 'charge_pump', 'pmic'):
                pr.attrs['regulator'] = {'regulator_linear': 'linear', 'regulator_switching': 'switching', 'regulator_module': 'module',
                                         'charge_pump': 'charge_pump', 'pmic': 'pmic'}[sub]
                rv = regulator_vout(part.text())
                if rv:
                    pr.attrs['vout'] = belief(rv[0], 'V', f"part number '{rv[1]}'", rv[0] * 0.97, rv[0] * 1.03)
            elif sub is None and _looks_like_regulator(part, roles):
                role = 'regulator'
                pr.subtype = _looks_like_regulator(part, roles)
                pr.attrs['regulator'] = 'switching' if pr.subtype == 'regulator_switching' else 'linear'
                evs = [ev('pinfunction', 'regulator pin set (VIN/VOUT/GND, SW/FB)', MODERATE)]
        elif k == 'diode':
            role = pr.subtype or 'diode'
        elif k == 'transistor':
            role = 'transistor'
        elif k == 'connector':
            role = f"connector_{pr.subtype}"
        pr.role = role
        if evs:
            pr.evidence = list(pr.evidence) + evs
        if role != k:
            pr.confidence = min(pr.kind_confidence, confidence(evs, prior=0.0)) if evs else pr.kind_confidence


def _looks_like_regulator(part: Part, roles: Roles) -> str | None:
    fns = {p.fn for p in part.pins}
    n = len(part.active_pins())
    if n > 16:
        return None
    if any(SW_PIN.match(f) for f in fns) and any(IN_PIN.match(f) for f in fns) and (any(FB_PIN.match(f) for f in fns) or n <= 8):
        return 'regulator_switching'
    has_in = any(IN_PIN.match(f) for f in fns)
    has_out = any(OUT_PIN.match(f) for f in fns) or any(p.ptype == 'power_out' for p in part.pins)
    has_g = any(GND_PIN.match(f) for f in fns)
    if has_in and has_out and has_g and n <= 8:
        return 'regulator_linear'
    return None
