# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Part cards for prius-solar-mppt: one PartDef per distinct part (DESIGN.md section 8).

Every typed fact cites where it was read (source=). Datasheets were downloaded and read in
October 2026 unless the source says [S] (secondary: distributor page, family drawing, search
snippet) or [unverified]. Lifecycle is what the vendor page or datasheet showed; no distributor
API was queried.
"""
from kaesynth import Isolation, PartDef, PinDef, Ratings, VLimit
from kaesynth.lib import IC, LED, C, C_pol, Conn, Fuse, L, MountingHole, R, TestPoint, Thermistor

TI = "Texas Instruments"
DS = {
    "LM5176": "https://www.ti.com/lit/ds/symlink/lm5176-q1.pdf",
    "LM74700": "https://www.ti.com/lit/ds/symlink/lm74700-q1.pdf",
    "INA186": "https://www.ti.com/lit/ds/symlink/ina186-q1.pdf",
    "TLV9001": "https://www.ti.com/lit/ds/symlink/tlv9002-q1.pdf",
    "TLV9062": "https://www.ti.com/lit/ds/symlink/tlv9062-q1.pdf",
    "UCC27282": "https://www.ti.com/lit/ds/symlink/ucc27282-q1.pdf",
    "AMC3330": "https://www.ti.com/lit/ds/symlink/amc3330-q1.pdf",
    "AMC3302": "https://www.ti.com/lit/ds/symlink/amc3302-q1.pdf",
    "LM2901B": "https://www.ti.com/lit/ds/symlink/lm2901b-q1.pdf",
    "LVC2G74": "https://www.ti.com/lit/ds/symlink/sn74lvc2g74-q1.pdf",
    "TPS3850": "https://www.ti.com/lit/ds/symlink/tps3850-q1.pdf",
    "LM4040": "https://www.ti.com/lit/ds/symlink/lm4040-n-q1.pdf",
    "TPL7407": "https://www.ti.com/lit/ds/symlink/tpl7407la-q1.pdf",
    "LM5164": "https://www.ti.com/lit/ds/symlink/lm5164-q1.pdf",
    "HVD230": "https://www.ti.com/lit/ds/symlink/sn65hvd230q-q1.pdf",
    "DSPIC": "https://ww1.microchip.com/downloads/aemDocuments/documents/MCU16/ProductDocuments/DataSheets/"
             "dsPIC33CK256MP508-Family-Data-Sheet-DS70005349.pdf",
    "EE": "https://ww1.microchip.com/downloads/en/DeviceDoc/20005715A.pdf",
    "IAUC": "https://www.infineon.com/dgdl/Infineon-IAUC100N10S5L040-DataSheet-v01_00-EN.pdf",
    "VS6": "https://www.vishay.com/docs/94985/vs-6esh06hm3.pdf",
    "TNPW": "https://www.vishay.com/docs/28758/tnpw_e3.pdf",
    "WSK": "https://www.vishay.com/docs/30108/wsk2512.pdf",
    "G9KB": "https://components.omron.com/us-en/products/relays/G9KB",
    "EVM10": "https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/"
             "eaton-evm10-high-breaking-capacity-dc-fuse-data-sheet-elx1304.pdf",
    "C60": "https://us.sunpower.com/sites/default/files/media-library/data-sheets/ds-c60-solar-cells.pdf",
}

# ---------------------------------------------------------------------------------------------
# Passives. One PartDef per MPN, built on first use and cached.

_CACHE = {}


def _code_panasonic(ohms):
    """Panasonic ERJ 4-character resistance code: 10k -> 1002, 2.2 -> 2R20, 100 -> 1000."""
    if ohms < 100:
        s = f"{ohms:.3g}"
        if "." in s:
            a, b = s.split(".")
            return (a + "R" + b).ljust(4, "0")[:4]
        return s + "R0" if len(s) == 2 else s
    e, v = 0, ohms
    while v >= 1000:
        v /= 10
        e += 1
    return f"{int(round(v)):03d}{e}"


def _code_vishay(ohms):
    """Vishay TNPW 4-character code: 10k -> 10K0, 1M -> 1M00, 249 -> 249R, 9.76k -> 9K76."""
    for div, letter in ((1e6, "M"), (1e3, "K"), (1, "R")):
        if ohms >= div:
            v = ohms / div
            s = f"{v:.3g}"
            if "." in s:
                a, b = s.split(".")
            else:
                a, b = s, ""
            return (a + letter + b).ljust(4, "0")[:4]
    raise ValueError(ohms)


def _fmt(ohms):
    if ohms >= 1e6:
        return f"{ohms / 1e6:g}M"
    if ohms >= 1e3:
        return f"{ohms / 1e3:g}k"
    return f"{ohms:g}"


def res(ohms, pkg="0603", prec=False):
    """Resistor card. prec=False: Panasonic ERJ thick film 1 %; prec=True: Vishay TNPW thin film 0.1 % 25 ppm/K."""
    key = ("R", ohms, pkg, prec)
    if key in _CACHE:
        return _CACHE[key]
    if prec:
        mpn = f"TNPW{pkg}{_code_vishay(ohms)}BEEA"
        vmax, pmax = {"0603": (100, 0.1), "1206": (200, 0.25)}[pkg]
        d = R(_fmt(ohms), pkg, tol="0.1%", p_max=pmax, v_max=vmax, mpn=mpn, manufacturer="Vishay Dale",
              datasheet=DS["TNPW"], lifecycle="active", second_source="Panasonic ERA-3AEB/ERA-8AEB, Susumu RG",
              fields={"TCR": "25ppm/K"},
              source={"ratings": "Vishay TNPW e3 doc 28758 p.1 Technical Specifications: 0603 Umax 100 V, 1206 Umax "
                                 "200 V, 0.1 %, 25 ppm/K, AEC-Q200; power taken below the P70 column (conservative); "
                                 "part number format p.? 'Part number and product description'"})
    else:
        series = "ERJ-3EKF" if pkg == "0603" and ohms >= 10 else "ERJ-3RQF" if pkg == "0603" else "ERJ-8ENF"
        mpn = f"{series}{_code_panasonic(ohms)}V"
        vmax, pmax = {"0603": (75, 0.1), "1206": (200, 0.25)}[pkg]
        d = R(_fmt(ohms), pkg, tol="1%", p_max=pmax, v_max=vmax, mpn=mpn, manufacturer="Panasonic",
              datasheet="https://industrial.panasonic.com/cdbs/www-data/pdf/RDA0000/AOA0000C304.pdf",
              lifecycle="active", second_source="Yageo AC series (AEC-Q200), Vishay CRCW-HP",
              source={"ratings": "Panasonic ERJ thick-film AEC-Q200 series [S]: 0603 0.1 W 75 V, 1206 0.25 W 200 V; "
                                 "MPN built from the Panasonic value code [S]"})
    _CACHE[key] = d
    return d


# capacitor key -> (MPN, maker, package, value, volts, dielectric, footprint)
CAPS = {
    "100n100V": ("GCM188R72A104KA64D", "Murata", "0603", "100n", 100, "X7R", None),
    "1u25V": ("GCM188R71E105KA64D", "Murata", "0603", "1u", 25, "X7R", None),
    "4u7100V": ("CGA6P3X7S2A475K250AB", "TDK", "1210", "4.7u", 100, "X7S", None),
    "10u25V": ("GCM32ER71E106KA57L", "Murata", "1210", "10u", 25, "X7R", None),
    "1n50V": ("GCM1885C1H102JA16D", "Murata", "0603", "1n", 50, "C0G", None),
    "10n50V": ("GCM188R71H103KA37D", "Murata", "0603", "10n", 50, "X7R", None),
    "47n50V": ("GCM188R71H473KA55D", "Murata", "0603", "47n", 50, "X7R", None),
    "2n2_50V": ("GCM188R71H222KA37D", "Murata", "0603", "2.2n", 50, "X7R", None),
    "100p50V": ("GCM1885C1H101JA16D", "Murata", "0603", "100p", 50, "C0G", None),
    "47p50V": ("GCM1885C1H470JA16D", "Murata", "0603", "47p", 50, "C0G", None),
    "680p50V": ("GCM1885C1H681JA16D", "Murata", "0603", "680p", 50, "C0G", None),
    "100nC0G": ("CGA5L1C0G2A104J160AC", "TDK", "1206", "100n", 100, "C0G", None),
    "100n630V": ("CGA6L1X7T2J104K160AC", "TDK", "1210", "100n", 630, "X7T", None),
    "220p630V": ("CGA5H4C0G2J221J115AA", "TDK", "1206", "220p", 630, "C0G", None),
}


def cap(key):
    if key in _CACHE:
        return _CACHE[key]
    if key == "100u63V":
        d = C_pol("100u", 63, "Capacitor_SMD:CP_Elec_10x10", mpn="EEH-ZA1J101P", manufacturer="Panasonic",
                  i_ripple=2.0, datasheet="https://industrial.panasonic.com/cdbs/www-data/pdf/RDE0000/ABA0000C1259.pdf",
                  lifecycle="active", second_source="Nichicon GYA1J101MCQ1GS [unverified]",
                  source={"ratings": "Panasonic ZA hybrid series [S]: 63 V, 100 uF, 10x10.2 mm, ripple 2.0 A rms at "
                                     "100 kHz 125 C, AEC-Q200"})
    else:
        mpn, mfr, pkg, val, volts, diel, fp = CAPS[key]
        unverified = key == "220p630V"
        d = C(val, volts, pkg, diel, mpn=mpn, manufacturer=mfr, footprint=fp, lifecycle="active",
              datasheet=("https://www.murata.com/en-us/products/productdetail?partno=" + mpn) if mfr == "Murata"
              else "https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=" + mpn,
              second_source="Kemet/Samsung automotive equivalent, same package and voltage",
              source={"ratings": f"{mfr} part page [S]: {val}F {volts} V {diel} {pkg}, AEC-Q200"
                                 + (" [unverified: MPN not confirmed on the vendor site]" if unverified else "")})
    _CACHE[key] = d
    return d


L_MPPT = L("22u", "Inductor_SMD:L_Coilcraft_XAL1510-223", i_max=10.5, mpn="XAL1510-223MEB", manufacturer="Coilcraft",
           i_sat=18.7, datasheet="https://www.coilcraft.com/getmedia/xal15xx.pdf", lifecycle="active",
           second_source="Wurth 74439370220 [unverified]",
           source={"ratings": "Coilcraft XAL1510 document 947-1 [S]: 22 uH, Isat 18.7 A (30 % drop), Irms 10.5 A "
                              "(40 K rise), DCR 16 mOhm max, AEC-Q200 grade 1"})
L_AUX12 = L("100u", "Inductor_SMD:L_Coilcraft_MSS1210-XXX", i_max=2.4, mpn="MSS1210-104KED", manufacturer="Coilcraft",
            i_sat=3.1, datasheet="https://www.coilcraft.com/getmedia/mss1210.pdf", lifecycle="active",
            second_source="Bourns SRR1210-101M [unverified]",
            source={"ratings": "Coilcraft MSS1210 data sheet [S]: 100 uH, Isat 3.1 A (10 % drop), Irms 2.4 A, "
                               "DCR 0.125 Ohm max"})
L_3V3 = L("33u", "Inductor_SMD:L_Coilcraft_MSS1048-XXX", i_max=1.9, mpn="MSS1048-333MLB", manufacturer="Coilcraft",
          i_sat=1.66, datasheet="https://www.coilcraft.com/getmedia/mss1048.pdf", lifecycle="active",
          second_source="Bourns SRR1050HA-330M [unverified]",
          source={"ratings": "Coilcraft MSS1048 data sheet [S]: 33 uH, Isat 1.66 A (10 % drop), DCR 68 mOhm max"})


def _shunt(ohms, mpn):
    return PartDef(mpn=mpn, manufacturer="Vishay Dale", symbol="Device:R_Shunt",
                   footprint="Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm", value=f"{ohms * 1000:g}m",
                   category="resistor", description=f"Shunt {ohms * 1000:g} mOhm 1 % 1 W 4-terminal 2512",
                   datasheet=DS["WSK"], pin_names={"1": "I+", "2": "S+", "3": "S-", "4": "I-"},
                   ratings=Ratings(p_max=1.0, pin_i_max={"I+": (1.0 / ohms) ** 0.5, "I-": (1.0 / ohms) ** 0.5}),
                   lifecycle="active", second_source="Bourns CSS2H-2512 4-terminal [unverified]",
                   source={"ratings": "Vishay WSK2512 doc 30108 p.1 table: 1.0 W, 1 % from 0.0005 to 0.2 Ohm, "
                                      "TCR +/-35 ppm/K for 5-200 mOhm; ordering code p.1 (R0050 = 5 mOhm)",
                           "pin_names": "KiCad R_Shunt_Vishay_WSK2512 footprint: pads 1/4 force (outer), 2/3 sense "
                                        "(inner) per the WSK2512 4-terminal land pattern [S]"})


SHUNT_5M = _shunt(0.005, "WSK2512R0050FEA")
SHUNT_10M = _shunt(0.010, "WSK2512R0100FEA")
SHUNT_100M = _shunt(0.100, "WSK2512R1000FEA")

NTC_BOARD = Thermistor("10k", footprint="Resistor_SMD:R_0603_1608Metric", mpn="NTCG163JF103FTDS", manufacturer="TDK",
                       datasheet="https://product.tdk.com/en/search/sensor/ntc/chip-ntc-thermistor/info?part_no=NTCG163JF103FTDS",
                       lifecycle="active", second_source="Murata NCU18XH103F6SRB",
                       fields={"B25/85": "3435K"},
                       source={"ratings": "TDK NTCG series [unverified]: 10 kOhm 1 %, B25/85 3435 K, AEC-Q200"})

# ---------------------------------------------------------------------------------------------
# ICs

LM5176 = IC(
    "LM5176QPWPRQ1", manufacturer=TI, datasheet=DS["LM5176"],
    footprint="Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.5mm_ThermalVias",
    description="55 V 4-switch buck-boost controller with average current loop, AEC-Q100",
    pins=[PinDef(1, "EN/UVLO", "input", "left"), PinDef(2, "VIN", "power_in", "left"),
          PinDef(3, "VISNS", "input", "left"), PinDef(4, "MODE", "input", "left"),
          PinDef(5, "DITH", "passive", "left"), PinDef(6, "RT/SYNC", "input", "left"),
          PinDef(7, "SLOPE", "passive", "left"), PinDef(8, "SS", "passive", "left"),
          PinDef(9, "COMP", "passive", "left"), PinDef(10, "AGND", "power_in", "bottom"),
          PinDef(11, "FB", "input", "left"), PinDef(12, "VOSNS", "input", "right"),
          PinDef(13, "ISNS-", "input", "left"), PinDef(14, "ISNS+", "input", "left"),
          PinDef(15, "CSG", "input", "left"), PinDef(16, "CS", "input", "left"),
          PinDef(17, "PGOOD", "open_collector", "right"), PinDef(18, "SW2", "passive", "right"),
          PinDef(19, "HDRV2", "output", "right"), PinDef(20, "BOOT2", "passive", "right"),
          PinDef(21, "LDRV2", "output", "right"), PinDef(22, "PGND", "power_in", "bottom"),
          PinDef(23, "VCC", "power_out", "right"), PinDef(24, "BIAS", "power_in", "right"),
          PinDef(25, "LDRV1", "output", "right"), PinDef(26, "BOOT1", "passive", "right"),
          PinDef(27, "HDRV1", "output", "right"), PinDef(28, "SW1", "passive", "right"),
          PinDef(29, "PAD", "passive", "bottom")],
    ratings=Ratings(limits=[
        VLimit(("VIN", "EN/UVLO", "VISNS", "VOSNS", "ISNS+", "ISNS-"), ("AGND",), 60, "abs max"),
        VLimit(("BIAS",), ("AGND",), 40, "abs max"),
        VLimit(("FB", "SS", "DITH", "RT/SYNC", "SLOPE", "COMP"), ("AGND",), 3.6, "abs max"),
        VLimit(("VCC", "MODE", "PGOOD"), ("AGND",), 8.5, "abs max"),
        VLimit(("SW1", "SW2"), ("PGND",), 60, "abs max -1..60 V"),
        VLimit(("BOOT1",), ("SW1",), 8.5, "BOOT-SW abs max"), VLimit(("BOOT2",), ("SW2",), 8.5, "BOOT-SW abs max")],
        t_min=-40, t_max=150),
    lifecycle="active", second_source="LM5175-Q1 (same pinout, no average current loop) [S]",
    source={"pins": "LM5176-Q1 DS SNVSB46B p.3 Fig. 5-1 and Table 5-1 (PWP); KiCad's LM5176PWP symbol types VOSNS "
                    "as an output, so this card generates its own symbol with the datasheet pin directions",
            "ratings": "LM5176-Q1 DS SNVSB46B p.5 Table 6.1 abs max; p.6 6.5: VREF 0.788-0.812 V, VEN(OP) 1.17-1.29 V, "
                       "hysteresis 2.15-4.25 uA, VSNS 43-57 mV"})

LM74700 = PartDef(
    mpn="LM74700QDBVRQ1", manufacturer=TI, symbol="Power_Management:LM74700", footprint="Package_TO_SOT_SMD:SOT-23-6",
    value="LM74700-Q1", category="ic", description="Ideal-diode controller, 65 V, reverse-polarity protection",
    datasheet=DS["LM74700"],
    ratings=Ratings(limits=[VLimit(("ANODE",), ("GND",), 65, "abs max +/-65 V"),
                            VLimit(("GATE",), ("ANODE",), 15, "GATE-ANODE abs max"),
                            VLimit(("VCAP",), ("ANODE",), 15, "VCAP-ANODE abs max"),
                            VLimit(("CATHODE",), ("ANODE",), 75, "CATHODE-ANODE -5..75 V")]),
    lifecycle="active", second_source="LM74700D-Q1 (DDF) [S]",
    source={"pins": "LM74700-Q1 DS SNOSD17G p.3 Fig. 5-1/Table 5-1 (DBV): 1 VCAP, 2 GND, 3 EN, 4 CATHODE, 5 GATE, "
                    "6 ANODE; matches KiCad Power_Management:LM74700",
            "ratings": "LM74700-Q1 DS SNOSD17G p.4 6.1 Absolute Maximum Ratings"})

INA186 = IC(
    "INA186A2QDBVRQ1", manufacturer=TI, datasheet=DS["INA186"], footprint="Package_TO_SOT_SMD:SOT-23-5",
    description="Current-sense amplifier 50 V/V, -0.2..40 V common mode",
    pins=[PinDef(1, "GND", "power_in"), PinDef(2, "OUT", "output"), PinDef(3, "VS", "power_in"),
          PinDef(4, "IN-", "input"), PinDef(5, "IN+", "input")],
    ratings=Ratings(limits=[VLimit(("VS",), ("GND",), 6, "abs max"),
                            VLimit(("IN+", "IN-"), ("GND",), 42, "abs max; may exceed if pin current <= 5 mA (note 3)")]),
    lifecycle="active", second_source="INA186A2-Q1 in DCK (SC-70) [S]",
    source={"pins": "INA186-Q1 DS SBOS386B p.3 Fig. 5-2/Table 5-1 (DBV): 1 GND, 2 OUT, 3 VS, 4 IN-, 5 IN+",
            "ratings": "INA186-Q1 DS SBOS386B p.4 6.1: VS 6 V, inputs GND-0.3..42 V, note 3 (5 mA)"})

TLV9001 = PartDef(
    mpn="TLV9001QDBVRQ1", manufacturer=TI, symbol="Amplifier_Operational:TLV9061xDBV",
    footprint="Package_TO_SOT_SMD:SOT-23-5", value="TLV9001-Q1", category="ic",
    description="Op-amp 1 MHz RRIO 1.8-5.5 V", datasheet=DS["TLV9001"],
    pin_names={"1": "OUT", "3": "IN+", "4": "IN-"},
    ratings=Ratings(limits=[VLimit(("V+",), ("V-",), 6, "abs max supply")]),
    lifecycle="active", second_source="TLV9061-Q1 (pin compatible) [S]",
    source={"pins": "TLV900x-Q1 DS SBOS980G p.3 Fig. 5-1/Table 5-1 (DBV): 1 OUT, 2 V-, 3 IN+, 4 IN-, 5 V+; same "
                    "pinout as the KiCad TLV9061xDBV symbol",
            "pin_names": "same table; KiCad symbol leaves OUT/IN+/IN- unnamed",
            "ratings": "SBOS980G p.4 6.1: supply 0-6 V, inputs (V-)-0.5..(V+)+0.5 V"})

TLV9062 = PartDef(
    mpn="TLV9062QDRQ1", manufacturer=TI, symbol="Amplifier_Operational:TLV9062xD",
    footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", value="TLV9062-Q1", category="ic",
    description="Dual op-amp 10 MHz RRIO 1.8-5.5 V", datasheet=DS["TLV9062"],
    pin_names={"1": "OUTA", "2": "INA-", "3": "INA+", "5": "INB+", "6": "INB-", "7": "OUTB"},
    ratings=Ratings(limits=[VLimit(("V+",), ("V-",), 6, "abs max supply")]),
    lifecycle="active", second_source="TLV9002-Q1 D package (pin compatible) [S]",
    source={"pins": "TLV906x-Q1 DS SBOS966H Pin Configuration (D, SOIC-8): 1 OUT A, 2 IN A-, 3 IN A+, 4 V-, 5 IN B+, "
                    "6 IN B-, 7 OUT B, 8 V+; matches KiCad TLV9062xD",
            "pin_names": "same table",
            "ratings": "SBOS966H 6.1 Absolute Maximum Ratings: supply 6 V"})

UCC27282 = IC(
    "UCC27282QDRCRQ1", manufacturer=TI, datasheet=DS["UCC27282"],
    footprint="Package_SON:VSON-10-1EP_3x3mm_P0.5mm_EP1.65x2.4mm",
    description="120 V half-bridge driver with enable, 3 A", pins=[
        PinDef(1, "VDD", "power_in"), PinDef(2, "NC", "no_connect"), PinDef(3, "HB", "passive"),
        PinDef(4, "HO", "output"), PinDef(5, "HS", "passive"), PinDef(6, "EN", "input"),
        PinDef(7, "HI", "input"), PinDef(8, "LI", "input"), PinDef(9, "VSS", "power_in"),
        PinDef(10, "LO", "output"), PinDef(11, "PAD", "passive")],
    ratings=Ratings(limits=[VLimit(("VDD",), ("VSS",), 20, "abs max"),
                            VLimit(("EN", "HI", "LI"), ("VSS",), 20, "abs max -5..20 V"),
                            VLimit(("HS",), ("VSS",), 100, "abs max -10..100 V DC"),
                            VLimit(("HB",), ("VSS",), 120, "abs max"),
                            VLimit(("HB",), ("HS",), 20, "HB-HS abs max")]),
    lifecycle="active", second_source="UCC27284-Q1 (VSON-8, different pinout) [S]",
    source={"pins": "UCC27282-Q1 DS SLUSDN5D p.3 Fig. 5-1/Table 5-1 (DRC): 1 VDD, 2 NC, 3 HB, 4 HO, 5 HS, 6 EN, "
                    "7 HI, 8 LI, 9 VSS, 10 LO, thermal pad to VSS",
            "ratings": "SLUSDN5D p.4 6.1 Absolute Maximum Ratings; EN on 1.54-2.0 V, off 0.7-1.21 V (6.5)"})


def _amc(mpn, desc, ratings_src, pins_src, gain_note):
    return IC(
        mpn, manufacturer=TI, datasheet=DS["AMC3330" if "3330" in mpn else "AMC3302"],
        footprint="Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm", description=desc, pins=[
            PinDef(1, "DCDC_OUT", "power_out", "left"), PinDef(2, "DCDC_HGND", "passive", "left"),
            PinDef(3, "HLDO_IN", "power_in", "left"), PinDef(4, "NC", "no_connect", "left"),
            PinDef(5, "HLDO_OUT", "power_out", "left"), PinDef(6, "INP", "input", "left"),
            PinDef(7, "INN", "input", "left"), PinDef(8, "HGND", "power_in", "left"),
            PinDef(9, "GND", "power_in", "right"), PinDef(10, "OUTN", "output", "right"),
            PinDef(11, "OUTP", "output", "right"), PinDef(12, "VDD", "power_in", "right"),
            PinDef(13, "LDO_OUT", "power_out", "right"), PinDef(14, "DIAG", "open_collector", "right"),
            PinDef(15, "DCDC_GND", "passive", "right"), PinDef(16, "DCDC_IN", "power_in", "right")],
        ratings=Ratings(
            limits=[VLimit(("VDD",), ("GND",), 6.5, "abs max")],
            isolation=[Isolation(("DCDC_OUT", "DCDC_HGND", "HLDO_IN", "HLDO_OUT", "INP", "INN", "HGND"),
                                 ("GND", "OUTN", "OUTP", "VDD", "LDO_OUT", "DIAG", "DCDC_GND", "DCDC_IN"),
                                 v_iso_rms=4250, grade="reinforced", v_work_rms=1200, creepage_mm=8.0,
                                 standard="DIN VDE V 0884-11 reinforced; UL 1577 4250 Vrms; VIOWM 1200 Vrms / "
                                          "1700 VDC; CTI >= 600 V (material group I)")],
            t_min=-40, t_max=125),
        lifecycle="active", second_source="none drop-in (TI only); AMC1351-Q1 needs an isolated supply [S]",
        source={"pins": pins_src, "ratings": ratings_src + "; " + gain_note})


AMC3330 = _amc("AMC3330QDWERQ1", "Reinforced isolated amplifier, +/-1 V input, integrated DC/DC, gain 2",
               "AMC3330-Q1 DS SBASA35B p.4 6.1 (VDD 6.5 V), p.5-6 6.6/6.7 insulation (CLR/CPG >= 8 mm, CTI >= 600, "
               "VIOTM 6000 Vpk, VIOWM 1200 Vrms/1700 VDC, VISO 4250 Vrms)",
               "AMC3330-Q1 DS SBASA35B p.3 Fig. 4-1/Table 4-1: 1 DCDC_OUT, 2 DCDC_HGND, 3 HLDO_IN, 4 NC, 5 HLDO_OUT, "
               "6 INP, 7 INN, 8 HGND, 9 GND, 10 OUTN, 11 OUTP, 12 VDD, 13 LDO_OUT, 14 DIAG (open drain), "
               "15 DCDC_GND, 16 DCDC_IN. KiCad's AMC3330 symbol types DIAG as push-pull and DCDC_HGND as power "
               "output; two of them on one net would be false ERC conflicts, so this card generates its own symbol",
               "gain 2 V/V, +/-1 V FSR, gain error +/-0.2 % max")
AMC3302 = _amc("AMC3302QDWERQ1", "Reinforced isolated amplifier, +/-50 mV shunt input, integrated DC/DC, gain 41",
               "AMC3302-Q1 DS SBASA84A p.4 6.1 (VDD 6.5 V; INP/INN HGND-6..HLDO_OUT+0.5 V), p.5 6.3 (FSR +/-50 mV, "
               "clip +/-64 mV), p.6 6.6/6.7 (CLR/CPG >= 8 mm, CTI >= 600 material group I, VIOWM 1200 Vrms/1700 "
               "VDC, VIOTM 6000 Vpk, VISO 4250 Vrms)",
               "AMC3302-Q1 DS SBASA84A p.3 Fig. 5-1/Table 5-1: same 16-pin assignment as AMC3330-Q1 (DIAG open drain)",
               "gain 41 V/V, gain error +/-0.2 %, offset +/-50 uV, input bias -36 uA (needs low source impedance)")

LM2901B = PartDef(
    mpn="LM2901BQDRQ1", manufacturer=TI, symbol="Comparator:LM2901", footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    value="LM2901B-Q1", category="ic", description="Quad comparator, open collector, 2-36 V", datasheet=DS["LM2901B"],
    pin_names={"1": "1OUT", "2": "2OUT", "3": "VCC", "4": "2IN-", "5": "2IN+", "6": "1IN-", "7": "1IN+",
               "8": "3IN-", "9": "3IN+", "10": "4IN-", "11": "4IN+", "12": "GND", "13": "4OUT", "14": "3OUT"},
    ratings=Ratings(limits=[VLimit(("VCC",), ("GND",), 38, "abs max (36 V operating)")]),
    lifecycle="active", second_source="LM2901-Q1 (32 V) [S]",
    source={"pins": "LM2901B-Q1 DS SLCS142H p.3 Fig. 4-1 (D): 1 1OUT, 2 2OUT, 3 VCC, 4 2IN-, 5 2IN+, 6 1IN-, 7 1IN+, "
                    "8 3IN-, 9 3IN+, 10 4IN-, 11 4IN+, 12 GND, 13 4OUT, 14 3OUT",
            "pin_names": "same figure; KiCad Comparator:LM2901 unit 1 = pins 2/4/5 = TI channel 2, etc.",
            "ratings": "SLCS142H 6.1: supply -0.3..38 V, differential input +/-38 V"})

LVC2G74 = PartDef(
    mpn="SN74LVC2G74QDCURQ1", manufacturer=TI, symbol="74xGxx:74LVC2G74", footprint="Package_SO:VSSOP-8_2.3x2mm_P0.5mm",
    value="SN74LVC2G74-Q1", category="ic", description="D flip-flop with preset and clear (OVP latch)",
    datasheet=DS["LVC2G74"],
    ratings=Ratings(limits=[VLimit(("VCC",), ("GND",), 6.5, "abs max")]),
    lifecycle="active", second_source="74LVC1G74 (DCU) NXP [S]",
    source={"pins": "SN74LVC2G74-Q1 DS SCES563C p.1 DCU pinout: 1 CLK, 2 D, 3 ~Q, 4 GND, 5 Q, 6 ~CLR, 7 ~PRE, 8 VCC",
            "ratings": "SCES563C 6.1: VCC and inputs -0.5..6.5 V"})

TPS3850 = IC(
    "TPS3850G33QDRCRQ1", manufacturer=TI, datasheet=DS["TPS3850"],
    footprint="Package_SON:VSON-10-1EP_3x3mm_P0.5mm_EP1.65x2.4mm",
    description="3.3 V supervisor with window watchdog", pins=[
        PinDef(1, "VDD", "power_in"), PinDef(2, "CWD", "passive"), PinDef(3, "SET0", "input"),
        PinDef(4, "CRST", "passive"), PinDef(5, "GND", "power_in"), PinDef(6, "SET1", "input"),
        PinDef(7, "WDI", "input"), PinDef(8, "WDO", "open_collector"), PinDef(9, "RESET", "open_collector"),
        PinDef(10, "SENSE", "input"), PinDef(11, "PAD", "passive")],
    ratings=Ratings(limits=[VLimit(("VDD", "SENSE", "WDI", "SET0", "SET1", "WDO", "RESET"), ("GND",), 7, "abs max")]),
    lifecycle="active", second_source="TPS3851-Q1 [S]",
    source={"pins": "TPS3850-Q1 DS SBVS264B p.3 Fig. 5-1/Table 5-1 (DRC): 1 VDD, 2 CWD, 3 SET0, 4 CRST, 5 GND, 6 SET1, "
                    "7 WDI, 8 WDO, 9 RESET, 10 SENSE, pad GND",
            "ratings": "SBVS264B p.4 6.1: VDD, RESET, WDO, SET0/1, WDI, SENSE -0.3..7 V"})

LM4040 = PartDef(
    mpn="LM4040QBIM3X2.5/NOPB", manufacturer=TI, symbol="Reference_Voltage:LM4040DBZ-2.5",
    footprint="Package_TO_SOT_SMD:SOT-23", value="2.500V 0.2%", category="ic",
    description="Shunt reference 2.500 V 0.2 % (B grade)", datasheet=DS["LM4040"],
    ratings=Ratings(pin_i_max={"K": 0.015, "A": 0.015}), lifecycle="active", second_source="LM4040-Q1 SNOSD... [S]",
    source={"pins": "LM4040-N-Q1 DS SNOS633N p.3 Fig. 4-1 (DBZ): 1 +, 2 -, 3 NC (* = no connect or tie to pin 2)",
            "ratings": "SNOS633N 6.1: reverse current 20 mA abs (15 mA used as limit)"})

TPL7407 = PartDef(
    mpn="TPL7407LAQPWRQ1", manufacturer=TI, symbol="Transistor_Array:TPL7407LAPW",
    footprint="Package_SO:TSSOP-16_4.4x5mm_P0.65mm", value="TPL7407LA-Q1", category="ic",
    description="7-channel low-side driver 30 V 500 mA with clamp diodes", datasheet=DS["TPL7407"],
    ratings=Ratings(limits=[VLimit(("OUT1", "OUT2", "OUT3", "OUT4", "OUT5", "OUT6", "OUT7", "COM"), ("GND",), 32,
                                   "abs max"),
                            VLimit(("IN1", "IN2", "IN3", "IN4", "IN5", "IN6", "IN7"), ("GND",), 30, "abs max")]),
    lifecycle="active", second_source="ULQ2003A-Q1 (Darlington, higher VOL) [S]",
    source={"pins": "TPL7407LA-Q1 DS SLRS074 p.3 PW pinout: 1-7 IN1-IN7, 8 GND, 9 COM, 10-16 OUT7-OUT1; matches "
                    "KiCad Transistor_Array:TPL7407LAPW",
            "ratings": "SLRS074 p.4 6.1/6.3: OUT/COM 32 V abs, 600 mA abs and 500 mA recommended per channel, "
                       "VIL 0.9 V, VIH 1.5 V, COM 6.5-30 V for full drive"})

LM5164 = PartDef(
    mpn="LM5164QDDARQ1", manufacturer=TI, symbol="Regulator_Switching:LM5164DDA",
    footprint="Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm_ThermalVias", value="LM5164-Q1",
    category="ic", description="100 V 1 A COT synchronous buck", datasheet=DS["LM5164"],
    ratings=Ratings(limits=[VLimit(("VIN", "EN/UVLO"), ("GND",), 100, "abs max"),
                            VLimit(("FB", "RON"), ("GND",), 5.5, "abs max"),
                            VLimit(("BST",), ("SW",), 5.5, "BST-SW abs max"),
                            VLimit(("SW",), ("GND",), 100, "abs max -1.5..100 V"),
                            VLimit(("PGOOD",), ("GND",), 14, "abs max")]),
    lifecycle="active", second_source="LM5163-Q1 (0.5 A) [S]",
    source={"pins": "LM5164-Q1 DS SNVSB51C p.3 Fig. 4-1/Table 4-1: 1 GND, 2 VIN, 3 EN/UVLO, 4 RON, 5 FB, 6 PGOOD, "
                    "7 BST, 8 SW, 9 EP; matches KiCad LM5164DDA",
            "ratings": "LM5164-Q1 DS p.4 6.1 Absolute Maximum Ratings"})

HVD230 = PartDef(
    mpn="SN65HVD230QDRQ1", manufacturer=TI, symbol="Interface_CAN_LIN:SN65HVD230",
    footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", value="SN65HVD230Q-Q1", category="ic",
    description="3.3 V CAN transceiver, standby (driver off) by RS high", datasheet=DS["HVD230"],
    ratings=Ratings(limits=[VLimit(("VCC",), ("GND",), 6, "abs max"),
                            VLimit(("CANH", "CANL"), ("GND",), 16, "bus terminal abs max -7..16 V")]),
    lifecycle="active", second_source="TCAN3404-Q1 [S]",
    source={"pins": "SN65HVD230Q-Q1 DS SGLS398A p.1 D package: 1 D, 2 GND, 3 VCC, 4 R, 5 Vref, 6 CANL, 7 CANH, 8 RS",
            "ratings": "SGLS398A p.4 abs max: VCC -0.3..6 V, bus -7..16 V; p.2 RS > 0.75 VCC = standby with the "
                       "driver off; 'unpowered node does not disturb the bus' p.1"})

EEPROM = PartDef(
    mpn="25LC256-E/SN", manufacturer="Microchip", symbol="Memory_EEPROM:25LCxxx",
    footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", value="25LC256", category="ic",
    description="256 kbit SPI EEPROM, 1M cycles (fault and charge log)", datasheet=DS["EE"],
    ratings=Ratings(limits=[VLimit(("VCC",), ("GND",), 6.5, "abs max")]),
    lifecycle="active", second_source="ST M95256-A125 (automotive) [S]",
    source={"pins": "Microchip DS20005715A pin function table: CS, SO, WP, VSS, SI, SCK, HOLD, VCC in the standard "
                    "SPI-EEPROM order 1-8 (KiCad 25LCxxx) [S: the read copy shows the MF package of the same die]",
            "ratings": "DS20005715A: VCC 2.5-5.5 V, 1M erase/write cycles, 5 MHz at 3.3 V"})

DSPIC_PINS = [
    (1, "RB14/PWM1H"), (2, "RB15/PWM1L"), (3, "RC12/PWM8H"), (4, "RC13/PWM8L"), (5, "MCLR"), (6, "RD13/RP77"),
    (7, "RC0/AN12"), (8, "RA0/AN0"), (9, "RA1/ANA1"), (10, "RA2/AN9"), (11, "RA3/AN3"), (12, "RA4/AN4"),
    (13, "AVDD"), (14, "AVSS"), (15, "RC1/AN13"), (16, "RC2/AN14"), (17, "RC6/AN17"), (18, "VDD"), (19, "VSS"),
    (20, "RC3/AN15"), (21, "RB0/AN5"), (22, "RB1/AN6"), (23, "RD10/AN18"), (24, "RC7/AN16"), (25, "RB2/AN1"),
    (26, "RB3/PGD2"), (27, "RB4/PGC2"), (28, "RC8/SCK2"), (29, "RC9/SDI2"), (30, "RD8/SDO2"), (31, "VSS"),
    (32, "VDD"), (33, "RB5/PGD3"), (34, "RB6/PGC3"), (35, "RB7/TDO"), (36, "RB8/PGD1"), (37, "RB9/PGC1"),
    (38, "RC4/RP52"), (39, "RC5/RP53"), (40, "RC10/PWM7H"), (41, "RC11/PWM7L"), (42, "VSS"), (43, "VDD"),
    (44, "RD1/RP65"), (45, "RB10/TMS"), (46, "RB11/TCK"), (47, "RB12/TDI"), (48, "RB13/RP45")]


def _dspic_pin(num, name):
    if name in ("VDD", "AVDD"):
        return PinDef(num, name, "power_in", "top")
    if name in ("VSS", "AVSS"):
        return PinDef(num, name, "power_in", "bottom")
    if name == "MCLR":
        return PinDef(num, name, "input", "left")
    side = "left" if ("/AN" in name or "/ANA" in name) else "right"
    return PinDef(num, name, "bidirectional", side)


DSPIC = IC(
    "DSPIC33CK256MP505-E/PT", manufacturer="Microchip", datasheet=DS["DSPIC"],
    footprint="Package_QFP:TQFP-48_7x7mm_P0.5mm",
    description="dsPIC33CK 100 MIPS DSC, 3 ADC cores, high-resolution PWM, CAN FD, AEC-Q100",
    pins=[_dspic_pin(n, s) for n, s in DSPIC_PINS],
    ratings=Ratings(limits=[VLimit(("VDD", "AVDD"), ("VSS",), 4.0, "abs max VDD")]),
    lifecycle="active", second_source="dsPIC33CK128MP505 / dsPIC33CK64MP505 (same pinout, less memory)",
    source={"pins": "dsPIC33CK256MP508 family DS70005349K p.8 Table 6 (48-pin TQFP): pin names abbreviated to the "
                    "port and the function used; full alternate functions in that table",
            "ratings": "DS70005349K electrical characteristics: VDD 3.0-3.6 V, abs max 4.0 V [S: section 30 not "
                       "re-read]; JTAG pins RB7/RB10-RB12 need JTAGEN = 0 (Table 6 note 2)"})

# ---------------------------------------------------------------------------------------------
# Discretes

IAUC = PartDef(
    mpn="IAUC100N10S5L040", manufacturer="Infineon", symbol="Transistor_FET:BSC040N10NS5",
    footprint="Package_TO_SOT_SMD:TDSON-8-1", value="IAUC100N10S5L040", category="mosfet",
    description="N-MOSFET 100 V 4 mOhm, logic level, AEC-Q101, PG-TDSON-8", datasheet=DS["IAUC"],
    ratings=Ratings(limits=[VLimit(("D",), ("S",), 100, "VDS"), VLimit(("G",), ("S",), 20, "VGS +/-20 V")],
                    pin_i_max={"D": 100, "S": 100}, p_max=167, t_max=175),
    lifecycle="active", second_source="IAUC100N10S5N040 (standard level) / BSC040N10NS5 (industrial) [S]",
    source={"pins": "IAUC100N10S5L040 DS rev 1.0 p.1 PG-TDSON-8: S 1-3, G 4, D 5-8 + tab; KiCad BSC040N10NS5 "
                    "(same package and pinout) numbers S 1,2,3, G 4, D 5 = TDSON-8-1 pads",
            "ratings": "IAUC100N10S5L040 DS rev 1.0 p.2: VDS 100 V, VGS +/-20 V, ID 100 A at Tc 25 C, Ptot 167 W, "
                       "RthJC 0.9 K/W, RDS(on) 4.0 mOhm at 10 V"})

D_HV = IC(
    "VS-6ESH06HM3/86A", manufacturer="Vishay", datasheet=DS["VS6"], footprint="Package_TO_SOT_SMD:TO-277A",
    category="diode", description="Hyperfast rectifier 600 V 6 A, AEC-Q101, eSMP TO-277A",
    pins=[PinDef(1, "A", "passive", "left"), PinDef(2, "A", "passive", "left"), PinDef(3, "K", "passive", "right")],
    ratings=Ratings(limits=[VLimit(("K",), ("A",), 600, "VRRM")], i_max=6.0, t_max=175),
    lifecycle="active", second_source="VS-6EVH06-M3 [unverified]",
    source={"pins": "VS-6ESH06HM3 DS doc 94985 p.1 package drawing: two anode leads, cathode = heatsink tab; pads per "
                    "KiCad TO-277A (1, 2 leads, 3 tab)",
            "ratings": "VS-6ESH06HM3 DS doc 94985 p.1-2: VRRM 600 V, IF(AV) 6 A, TJ max 175 C"})
D_HV.prefix = "D"

TVS39 = PartDef(
    mpn="TPSMB39A", manufacturer="Littelfuse", symbol="Device:D_Zener", footprint="Diode_SMD:D_SMB",
    value="TPSMB39A", category="tvs", description="TVS unidirectional 600 W, VWM 33.3 V, VC 53.9 V",
    datasheet="https://www.littelfuse.com/assetdocs/tvs-diodes-tpsmb-datasheet",
    ratings=Ratings(v_max=33.3), lifecycle="active", second_source="Vishay TPSMB39A-E3 [S]",
    source={"ratings": "Littelfuse TPSMB series [unverified: datasheet download blocked]: VR 33.3 V, VBR 37.1-41.0 V, "
                       "VC 53.9 V at 11.1 A, AEC-Q101",
            "pins": "D_SMB pad 1 = cathode band; Device:D_Zener K = 1"})

BAT46 = PartDef(
    mpn="BAT46WJ,115", manufacturer="Nexperia", symbol="Diode:BAT46", footprint="Diode_SMD:D_SOD-323F",
    value="BAT46WJ", category="diode", description="Schottky 100 V 250 mA SOD-323F, AEC-Q101",
    datasheet="https://assets.nexperia.com/documents/data-sheet/BAT46WJ.pdf",
    ratings=Ratings(v_max=100, i_max=0.25), lifecycle="active", second_source="ST BAT46JFILM [S]",
    source={"ratings": "Nexperia BAT46WJ data sheet [unverified: download blocked]: VR 100 V, IF 250 mA, AEC-Q101",
            "pins": "KiCad Diode:BAT46 K = 1, A = 2; SOD-323F pad 1 = cathode band"})

BAS21 = PartDef(
    mpn="SBAS21LT1G", manufacturer="onsemi", symbol="Diode:BAS21", footprint="Package_TO_SOT_SMD:SOT-23",
    value="BAS21", category="diode", description="Switching diode 250 V 200 mA SOT-23, AEC-Q101",
    datasheet="https://www.onsemi.com/download/data-sheet/pdf/bas21lt1-d.pdf",
    ratings=Ratings(v_max=250, i_max=0.2), lifecycle="active", second_source="Nexperia BAS21 [S]",
    source={"ratings": "onsemi BAS21LT1 data sheet [unverified: download blocked]: VR 250 V, IF 200 mA",
            "pins": "KiCad Diode:BAS21: 1 A, 2 NC, 3 K (SOT-23 single diode)"})

NPN_HV = PartDef(
    mpn="SMMBTA42LT1G", manufacturer="onsemi", symbol="Transistor_BJT:MMBTA42", footprint="Package_TO_SOT_SMD:SOT-23",
    value="MMBTA42", category="bjt", description="NPN 300 V 500 mA SOT-23, AEC-Q101",
    datasheet="https://www.onsemi.com/download/data-sheet/pdf/mmbta42lt1-d.pdf",
    ratings=Ratings(limits=[VLimit(("C",), ("E",), 300, "VCEO")], pin_i_max={"C": 0.5}), lifecycle="active",
    second_source="Nexperia PMBTA42 [S]",
    source={"ratings": "onsemi MMBTA42LT1 data sheet [unverified: download blocked]: VCEO 300 V, IC 500 mA",
            "pins": "KiCad Transistor_BJT:MMBTA42: 1 B, 2 E, 3 C (SOT-23)"})

LED_G = LED("green", "0603", mpn="APT1608SGC", manufacturer="Kingbright", i_max=0.025,
            datasheet="https://www.kingbrightusa.com/images/catalog/SPEC/APT1608SGC.pdf", lifecycle="active",
            second_source="Wurth 150060VS75000",
            source={"ratings": "APT1608SGC DS p.2 abs max: IF 25 mA, VR 5 V [S, as used in rpi-mains-relay]",
                    "pins": "APT1608SGC DS p.1: pin 1 cathode"})
LED_R = LED("red", "0603", mpn="APT1608SURCK", manufacturer="Kingbright", i_max=0.03,
            datasheet="https://www.kingbrightusa.com/images/catalog/SPEC/APT1608SURCK.pdf", lifecycle="active",
            second_source="Wurth 150060RS75000",
            source={"ratings": "APT1608SURCK DS [unverified]: IF 30 mA, VR 5 V", "pins": "pin 1 cathode [S]"})

NETTIE = PartDef(symbol="Device:NetTie_2", footprint="NetTie:NetTie-2_SMD_Pad0.5mm", value="NetTie", category="other",
                 description="AGND-PGND star tie (copper, no BOM item)", generic=True, in_bom=False, prefix="NT")
TP = TestPoint()
MH_PAD = MountingHole(pad=True, description="M3 plated hole bonded to GND/chassis")
MH = MountingHole(description="M3 non-plated hole, no net")

# ---------------------------------------------------------------------------------------------
# Magnetics and HV parts (custom)

T_DCX = IC(
    "T301-ETD39-DCX22 (custom)", manufacturer="magnetics vendor to specification (DESIGN.md 7.3)",
    datasheet="designs/prius-solar-mppt/DESIGN.md#73-llc-dcx-and-t301",
    footprint="custom:ETD39_20pin_DCX", category="transformer",
    description="LLC-DCX transformer ETD39 N97, Np 4 (litz) : Ns 88 (TIW), Lm 18 uH, Lr 0.8 uH, reinforced",
    pins=[PinDef(1, "P_START", "passive", "left"), PinDef(2, "P_START", "passive", "left"),
          PinDef(3, "P_END", "passive", "left"), PinDef(4, "P_END", "passive", "left"),
          PinDef(11, "S_START", "passive", "right"), PinDef(20, "S_END", "passive", "right")],
    ratings=Ratings(limits=[VLimit(("P_START",), ("P_END",), 60, "primary winding (VINT/2 square wave)"),
                            VLimit(("S_START",), ("S_END",), 900, "secondary winding, TIW rated")],
                    pin_i_max={"P_START": 15, "P_END": 15, "S_START": 1.5, "S_END": 1.5},
                    isolation=[Isolation(("P_START", "P_END"), ("S_START", "S_END"), v_iso_rms=5000,
                                         grade="reinforced", v_work_rms=600, creepage_mm=10.0,
                                         standard="specified: IEC 61558-1 style reinforced, TIW secondary, 5.0 kVrms "
                                                  "60 s type / 4.25 kVrms 1 s routine, >= 10 mm pin-to-pin creepage")]),
    lifecycle="active", second_source="any qualified magnetics vendor (Wurth custom, Pulse, Sumida)",
    source={"pins": "our pin assignment on the TDK ETD 39 20-pin coil former: 1/2 primary start, 3/4 primary end, "
                    "11 secondary start, 20 secondary end; unused positions have no pad [I]",
            "ratings": "design specification DESIGN.md 7.3 [I]; to be confirmed by the vendor's type test (V-5)"})
T_DCX.prefix = "T"

RELAY_HV = IC(
    "G9KB-1A DC12", manufacturer="Omron", datasheet=DS["G9KB"], footprint="custom:Omron_G9KB-1A",
    category="relay", description="PCB power relay SPST-NO 600 VDC 50 A, double break, 3.6 mm gap, 12 V coil",
    pins=[PinDef(1, "COIL_1", "passive", "left"), PinDef(2, "COIL_2", "passive", "left"),
          PinDef(3, "C3", "passive", "right"), PinDef(4, "C4", "passive", "right")],
    ratings=Ratings(
        limits=[VLimit(("COIL_1",), ("COIL_2",), 13.2, "max coil voltage 110 % of 12 V"),
                VLimit(("C3",), ("C4",), 600, "open contact: max switching voltage / rated insulation voltage 600 V")],
        pin_i_max={"C3": 50, "C4": 50},
        isolation=[Isolation(("COIL_1", "COIL_2"), ("C3", "C4"), v_iso_rms=5000, grade="reinforced", v_work_rms=600,
                             creepage_mm=12.6, standard="IEC 61810-1 reinforced 600 V, OVC III, PD2; 5000 VAC 1 min; "
                                                        "10 kV impulse"),
                   Isolation(("C3",), ("C4",), v_iso_rms=2500, grade="functional", v_work_rms=600,
                             standard="open contact (micro disconnection), 2500 VAC 1 min, gap >= 3.6 mm")],
        t_min=-40, t_max=85),
    lifecycle="active", second_source="G9KB-1A DC24 with a 24 V coil supply; TE LEV100 (panel mount) [S]",
    source={"pins": "Omron G9KB Cat. No. K340-E1-06 p.3 'Terminal Arrangement/Internal Connections (BOTTOM VIEW)': "
                    "coil 1-2 (no coil polarity), contact 3-4 (double break, bidirectional)",
            "ratings": "K340-E1-06 p.1 coil (12 V, 235 mA, 51 Ohm, must operate 75 %, max 110 %, holding 45-60 %), "
                       "p.2 contacts (600 VDC 50 A, 600 VDC making 1 A/breaking 1 A), dielectric 5000 VAC coil-contact "
                       "and 2500 VAC same-polarity contacts, impulse 10 kV, -40..85 C; p.4 insulation: coil-contact "
                       "reinforced 600 V OVC III PD2, creepage 12.6 mm, clearance 8.0 mm, IIIa"})
RELAY_HV.prefix = "K"

FUSE_HV = Fuse(5, 500, "custom:Eaton_EVM10-2P", mpn="EVM10-5-2P", manufacturer="Eaton Bussmann", i2t=105,
               breaking_a=20000, datasheet=DS["EVM10"], lifecycle="active",
               second_source="Littelfuse 10x38 1000 VDC PV fuse SPXV001 (gPV) [unverified]",
               description="Fuse 10x38 mm 5 A 500 VDC 20 kA, 2-pin PCB terminals per cap",
               source={"ratings": "Eaton ELX1304 (effective Jan 2026) p.2 product table: EVM10-5 500 Vdc, 5 A, "
                                  "500 Vdc/20 kA, cold resistance 32.3 mOhm, melting I2t 38 A2s, total I2t 105 A2s; "
                                  "minimum breaking 3 x In (p.1)",
                       "pins": "ELX1304 p.2 '2P: 2 pin PCB terminal' drawing; one symbol pin per end cap, two pads "
                               "each (custom footprint)"})

# ---------------------------------------------------------------------------------------------
# Connectors

MSTB = "Phoenix Contact"
MSTB_SRC = {"ratings": "Phoenix MSTBA 2,5 header family page [S]: 12 A, 320 V (IEC, III/2), UL 300 V"}
J_PV = Conn(2, "Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal", i_max=12,
            v_max=320, mpn="1757242", manufacturer=MSTB, datasheet="https://www.phoenixcontact.com/en-us/products/1757242",
            lifecycle="active", second_source="Wurth 691311500102 [unverified]", source=MSTB_SRC,
            description="MSTBA 2,5/2-G-5,08 header (plug MSTB 2,5/2-ST-5,08)")
J_3P = Conn(3, "Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_3-G-5,08_1x03_P5.08mm_Horizontal", i_max=12,
            v_max=320, mpn="1757255", manufacturer=MSTB, datasheet="https://www.phoenixcontact.com/en-us/products/1757255",
            lifecycle="active", second_source="Wurth 691311500103 [unverified]", source=MSTB_SRC,
            description="MSTBA 2,5/3-G-5,08 header")
J_6P = Conn(6, "Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_6-G-5,08_1x06_P5.08mm_Horizontal", i_max=12,
            v_max=320, mpn="1757284", manufacturer=MSTB, datasheet="https://www.phoenixcontact.com/en-us/products/1757284",
            lifecycle="active", second_source="Wurth 691311500106 [unverified]", source=MSTB_SRC,
            description="MSTBA 2,5/6-G-5,08 header")
GMSTB_SRC = {"ratings": "Phoenix GMSTBA 2,5 (7.62 mm) family page [S]: 12 A, 630 V (IEC, III/2); UL 300 V "
                        "[unverified] - the IEC rating is the one used (vehicle, not UL listed)"}
J_HV2 = Conn(2, "Connector_Phoenix_GMSTB:PhoenixContact_GMSTBA_2,5_2-G-7,62_1x02_P7.62mm_Horizontal", i_max=12,
             v_max=630, mpn="1766343", manufacturer=MSTB, datasheet="https://www.phoenixcontact.com/en-us/products/1766343",
             lifecycle="active", second_source="none drop-in (pitch-specific)", source=GMSTB_SRC,
             description="GMSTBA 2,5/2-G-7,62 header [item number unverified]")
J_HV3 = Conn(3, "Connector_Phoenix_GMSTB:PhoenixContact_GMSTBA_2,5_3-G-7,62_1x03_P7.62mm_Horizontal", i_max=12,
             v_max=630, mpn="1766356", manufacturer=MSTB, datasheet="https://www.phoenixcontact.com/en-us/products/1766356",
             lifecycle="active", second_source="none drop-in (pitch-specific)", source=GMSTB_SRC,
             description="GMSTBA 2,5/3-G-7,62 header [item number unverified]")
J_FAN = Conn(2, "Connector_Molex:Molex_Micro-Fit_3.0_43650-0215_1x02_P3.00mm_Vertical", i_max=5, v_max=250,
             mpn="43650-0215", manufacturer="Molex", datasheet="https://www.molex.com/en-us/products/part-detail/436500215",
             lifecycle="active", second_source="Amphenol Minitek [unverified]",
             source={"ratings": "Molex Micro-Fit 3.0 series [S]: 5 A, 250 V"})
J_ICSP = Conn(6, "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical", i_max=3, v_max=50, mpn="61300611121",
              manufacturer="Wurth Elektronik", datasheet="https://www.we-online.com/catalog/datasheet/61300611121.pdf",
              lifecycle="active", second_source="any 2.54 mm 1x6 header",
              source={"ratings": "Wurth WR-PHD 2.54 mm header [S]: 3 A"})

# ---------------------------------------------------------------------------------------------
# Off-board (board="off"): array, harness items

C60 = PartDef(
    mpn="C60 bin H (Gen II)", manufacturer="Maxeon (SunPower)", symbol="Device:Solar_Cell", value="C60",
    category="other", prefix="SC", description="Back-contact mono-Si cell 125 mm, Pmp 3.38-3.42 W, Vmp 0.578 V",
    datasheet=DS["C60"], on_board=True,
    ratings=Ratings(i_max=6.3), lifecycle="active", second_source="Maxeon Gen III back-contact cells [S]",
    source={"ratings": "SunPower C60 solar cell data sheet (bins G-J) [P]: 125 x 125 mm, Pmp 3.34-3.42 W, Vmp "
                       "0.574-0.582 V, Imp 5.83-5.93 A, Voc 0.682-0.687 V, Isc 6.24-6.28 A, -1.8 mV/K, -0.32 %/K; "
                       "'positive ground' note"})
D_BYPASS = PartDef(
    mpn="V10P45-M3/86A", manufacturer="Vishay", symbol="Device:D_Schottky", value="V10P45", category="diode",
    description="Schottky 45 V 10 A TO-277A (bypass, laminated in the array junction strip)",
    datasheet="https://www.vishay.com/en/product/88941/", ratings=Ratings(v_max=45, i_max=10),
    lifecycle="active", second_source="Diodes SBR10U45SP5 [unverified]",
    source={"ratings": "Vishay V10P45 product page [S]: VRRM 45 V, IF(AV) 10 A, eSMP TO-277A, AEC-Q101",
            "pins": "Device:D_Schottky K = 1, A = 2"})


def cable(n_cores, spec, i_max, v_max, desc):
    """Harness cable as an off-board part: pin 2k-1 = core k at the board end, pin 2k = core k at the far end."""
    names = {}
    for k in range(1, n_cores + 1):
        names[str(2 * k - 1)] = f"C{k}_NEAR"
        names[str(2 * k)] = f"C{k}_FAR"
    return Conn(2 * n_cores, None, i_max=i_max, v_max=v_max, rows=2, generic=True, prefix="W", value=spec,
                description=desc, pin_names=names, in_bom=True,
                source={"pin_names": "harness convention of this design: odd pin = conductor at the board end, even "
                                     "pin = the same conductor at the far end"})


W_PV = cable(2, "2-core 2.5 mm2 FLRY-B, 4 m", 20, 60, "PV string cable roof -> main box (through a sealed roof-header gland)")
W_HV = cable(3, "3-core screened HV cable 2 x 2.5 mm2 + 1 x 0.75 mm2, orange, >= 600 V, 2 m", 20, 600,
             "HV cable main box J301 -> battery-end box J901 (screen to both metal glands)")
W_LV3 = cable(3, "3-core 0.75 mm2 FLRY-B, 2 m", 8, 60, "relay coil harness main J703 -> battery-end J903")
W_NTC = cable(3, "screened 6-core 0.35 mm2 (4 NTC + 2 ground)", 1, 60, "pack-case NTC harness -> main J706")
NTC_PACK = Thermistor("10k", footprint=None, generic=True,
                      description="NTC 10 kOhm 1 %, B25/85 3435 K, M4 ring lug, epoxy, insulated leads (bonded to the "
                                  "HV battery case, which is chassis potential)",
                      fields={"B25/85": "3435K"},
                      source={"ratings": "generic lug-mount NTC (e.g. Vishay NTCALUG series) [unverified]"})
FUSE_IG = Fuse(1, 32, None, mpn="0287001.PXCN", manufacturer="Littelfuse", description="ATO blade fuse 1 A 32 V in an "
               "add-a-fuse tap on an IG2-switched fuse", datasheet="https://www.littelfuse.com/products/fuses/automotive-"
               "passenger-car/blade-fuses/287", lifecycle="active", second_source="Bussmann ATM-1 [S]",
               source={"ratings": "Littelfuse ATO 287 series [S]: 1 A, 32 VDC, 1000 A interrupting"})
