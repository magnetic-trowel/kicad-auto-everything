# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Part cards for leadacid-balancer: one PartDef per distinct part (DESIGN.md section 8).

Every typed fact cites where it was read (source=). Evidence tags as in DESIGN.md: [P] primary
datasheet read, [S] secondary source or KiCad library only, [I] inference. Datasheets were
downloaded and read in October 2026; lifecycle from the TI/Vishay/Diodes orderable addenda unless
tagged otherwise.
"""
from kaesynth import Isolation, PartDef, PinDef, Ratings, VLimit
from kaesynth.lib import C, C_pol, IC, LED, R, Conn, Fuse, MountingHole

# ---------------------------------------------------------------------------------------------
# Power stage

FET_SC = PartDef(
    mpn="CSD18543Q3A", manufacturer="Texas Instruments", symbol="Transistor_FET:CSD18543Q3A",
    footprint="Package_SON:VSON-8_3.3x3.3mm_P0.65mm_NexFET", value="CSD18543Q3A", category="mosfet",
    description="N-MOSFET 60 V, 8.1/9.9 mOhm at 10 V, Qg 11.1 nC, SON 3.3x3.3 (SC switch Q_A-Q_D)",
    datasheet="https://www.ti.com/lit/ds/symlink/csd18543q3a.pdf",
    ratings=Ratings(limits=[VLimit(("D",), ("S",), 60, "VDS"), VLimit(("G",), ("S",), 20, "VGS +/-20 V")],
                    pin_i_max={"D": 12, "S": 12}, p_max=2.8, t_min=-55, t_max=150),
    lifecycle="active", second_source="Infineon BSZ099N06LS5 [I]",
    source={"pins": "TI SLPS633 (Dec 2016) p.1 top view: 1-3 S, 4 G, 5-8 D + pad; KiCad "
                    "Transistor_FET:CSD18543Q3A pads 1-3 S, 4 G, 5 D (pins 5-8 and pad merged) [P]",
            "ratings": "SLPS633 p.1 abs max: VDS 60 V, VGS +/-20 V, ID 12 A and PD 2.8 W on 1 in2 2 oz Cu "
                       "(RthJA 45 C/W), TJ -55..150 C; p.2 RDS(on) 8.1/9.9 mOhm at VGS 10 V [P]",
            "lifecycle": "TI orderable addendum, Active, Oct 2026 [P]"})

R_CF = R("0.086", "2816", footprint="Resistor_SMD:R_2816_7142Metric", tol="1%", p_max=2.0,
         mpn="WSL2816R0860FEH", manufacturer="Vishay Dale",
         datasheet="https://www.vishay.com/docs/30100/wsl.pdf", lifecycle="active",
         second_source="Vishay WSL2816R0860FEB (0.5 %) or WSLP-series 0.086 Ohm >= 2 W [I]",
         source={"ratings": "Vishay 30100 (rev 14-Apr-2026) p.1 table: WSL2816 2.0 W at 70 C, 0.002-0.1 Ohm at "
                            "1 %; derated linearly above 70 C; max working voltage (P x R)^0.5 [P]",
                 "lifecycle": "Vishay product page, Active [P]"}).with_(
    description="Metal strip resistor 0.086 Ohm 1 % 2 W 2816; two in parallel per flying-path position (R_CF = 0.043 Ohm)")

C_10U50 = C("10u", 50, "1210", dielectric="X7S", mpn="GCJ32EC71H106KA01L", manufacturer="Murata",
            datasheet="https://pim.murata.com/en-us/pim/details/?partNum=GCJ32EC71H106KA01%23",
            lifecycle="active", second_source="TDK CGA6P3X7S1H106K [I]",
            source={"ratings": "Murata GCJ32EC71H106 product sheet (MA01 variant read via mirror, Mar 2026): "
                               "10 uF, 50 Vdc, X7S, soft termination; KA01 = +/-10 % listed at Arrow [S]",
                    "lifecycle": "in production per Murata product sheet [P]; KA01 listing [S]"}).with_(
    description="MLCC 10 uF 50 V X7S 1210 soft termination (C_FLY, C_TOP, C_BOT)")

C_BULK = C_pol("100u", 35, "Capacitor_SMD:CP_Elec_8x10", mpn="UCZ1V101MCL1GS", manufacturer="Nichicon",
               i_ripple=0.27, datasheet="https://www.nichicon.co.jp/english/products/pdfs/e-ucz.pdf",
               lifecycle="active", second_source="Panasonic EEE-FK1V101P [S]",
               source={"ratings": "Nichicon UCZ series (secondary listing): 100 uF 35 V, 125 C 3000 h, "
                                  "ESR 0.2 Ohm, 270 mA rms at 100 kHz [S]",
                       "pins": "KiCad CP_Elec_8x10 pad 1 = + (Device:C_Polarized pin 1 = +) [S]",
                       "lifecycle": "distributor listing [S]"}).with_(
    description="Aluminium electrolytic 100 uF 35 V 8x10 SMD, bulk damping across each battery")

# ---------------------------------------------------------------------------------------------
# Gate drive and clock

_UCC_IN = ("INA", "INB", "VCCI", "GND", "DIS", "DT")
_UCC_A = ("VSSA", "OUTA", "VDDA")
_UCC_B = ("VSSB", "OUTB", "VDDB")
GATE_DRV = PartDef(
    mpn="UCC21520ADWR", manufacturer="Texas Instruments", symbol="Driver_FET:UCC21520ADW",
    footprint="Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm", value="UCC21520ADWR", category="ic",
    description="Isolated dual gate driver 4 A/6 A, 5 V UVLO, reinforced 5.7 kVrms input-output, "
                "functional 1500 VDC between outputs, programmable dead time",
    datasheet="https://www.ti.com/lit/ds/symlink/ucc21520.pdf",
    ratings=Ratings(
        limits=[VLimit(("VCCI",), ("GND",), 20, "VCCI-GND abs max"),
                VLimit(("INA", "INB", "DIS", "DT"), ("GND",), 20, "<= VCCI + 0.3 V, VCCI <= 20 V"),
                VLimit(("VDDA",), ("VSSA",), 30, "VDDA-VSSA"), VLimit(("VDDB",), ("VSSB",), 30, "VDDB-VSSB"),
                VLimit(("OUTA",), ("VSSA",), 30, "<= VDDA + 0.3 V"), VLimit(("OUTB",), ("VSSB",), 30, "<= VDDB + 0.3 V"),
                VLimit(("VSSA",), ("VSSB",), 1500, "channel-to-channel"),
                VLimit(("GND",), ("VSSA", "VSSB"), 2121, "VIOWM DC")],
        isolation=[
            Isolation(_UCC_IN, _UCC_A, v_iso_rms=5700, grade="reinforced", v_work_rms=1500, creepage_mm=8.0,
                      standard="DIN EN IEC 60747-17 (VDE 0884-17) reinforced; UL 1577 5700 Vrms 60 s"),
            Isolation(_UCC_IN, _UCC_B, v_iso_rms=5700, grade="reinforced", v_work_rms=1500, creepage_mm=8.0,
                      standard="DIN EN IEC 60747-17 (VDE 0884-17) reinforced; UL 1577 5700 Vrms 60 s"),
            # Functional only: the datasheet gives 1500 V DC working (and abs max VSSA-VSSB), no
            # withstand test. Isolation() has only Vrms fields, so the DC figure is entered as-is.
            Isolation(_UCC_A, _UCC_B, v_iso_rms=1500, grade="functional", v_work_rms=None, creepage_mm=None,
                      standard="functional, 1500 VDC working between output channels (SLUSCJ9F section 3)"),
        ],
        p_max=0.95, t_min=-40, t_max=150),
    lifecycle="active", second_source="Skyworks Si8233 (pin-different) [I]",
    source={"pins": "TI SLUSCJ9F (Nov 2024) Table 5-1: 1 INA, 2 INB, 3 VCCI, 4 GND, 5 DIS, 6 DT, 7 NC, 8 VCCI, "
                    "9 VSSB, 10 OUTB, 11 VDDB, 12/13 NC, 14 VSSA, 15 OUTA, 16 VDDA; KiCad "
                    "Driver_FET:UCC21520ADW numbers match [P]",
            "ratings": "SLUSCJ9F 6.1 abs max (VCCI 20 V, VDD 30 V, outputs VDD + 0.3 V, inputs VCCI + 0.3 V, "
                       "VSSA-VSSB 1500 V); 6.3 VDD 6.5-25 V for the A (5 V UVLO) version; 6.5 PD 950 mW; "
                       "6.6 CLR/CPG > 8 mm, VIOWM 1500 Vrms / 2121 VDC, VIOTM 8000 Vpk; UL 1577 VISO "
                       "5700 Vrms; section 3: functional isolation between outputs, 1500 VDC [P]",
            "lifecycle": "TI orderable addendum: UCC21520ADWR Active; UCC21520ADW (tube) obsolete [P]"})

OSC = PartDef(
    mpn="CD4047BM96", manufacturer="Texas Instruments", symbol="4xxx:4047",
    footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", value="CD4047BM96", category="ic",
    description="CMOS monostable/astable multivibrator, 3-18 V, complementary buffered outputs",
    datasheet="https://www.ti.com/lit/ds/symlink/cd4047b.pdf",
    ratings=Ratings(limits=[VLimit(("VDD",), ("VSS",), 20, "DC supply -0.5..+20 V"),
                            VLimit(("1", "2", "3", "4", "5", "6", "8", "9", "12"), ("VSS",), 20,
                                   "inputs -0.5..VDD + 0.5 V")],
                    p_max=0.5, t_min=-55, t_max=125),
    lifecycle="active", second_source="Nexperia HEF4047B [I]",
    source={"pins": "TI SCHS044C (Sep 2003) p.1 terminal diagram (1 C, 2 R, 3 RC common, 4 /ASTABLE, "
                    "5 ASTABLE, 6 -TRIG, 7 VSS, 8 +TRIG, 9 EXT RESET, 10 Q, 11 /Q, 12 RETRIG, 13 OSC OUT, 14 VDD) "
                    "and p.2 functional terminal connections (free running); KiCad 4xxx:4047 matches [P]",
            "ratings": "SCHS044C p.1 maximum ratings: VDD -0.5..+20 V, inputs -0.5..VDD + 0.5 V, PD 500 mW; "
                       "recommended 3-18 V [P]",
            "lifecycle": "TI orderable addendum, CD4047BM96 Active [P]"})

DIODE_BOOT = PartDef(
    mpn="BAS16W-7-F", manufacturer="Diodes Incorporated", symbol="Diode:BAS16W",
    footprint="Package_TO_SOT_SMD:SOT-323_SC-70", value="BAS16W", category="diode",
    description="Switching diode 75 V 150 mA SOT-323 (bootstrap)",
    datasheet="https://www.diodes.com/assets/Datasheets/ds30117.pdf",
    ratings=Ratings(v_max=75, i_max=0.15, p_max=0.2),
    lifecycle="active", second_source="Nexperia BAS16W [S]",
    source={"ratings": "BAS16 family: VR 75 V, VRRM 85 V, IFRM 250 mA, Ptot 330 mW read in the SOT-23 BAS16 sheet "
                       "(Zetex 1996) [P]; BAS16W IF 150 mA, Ptot 200 mW from distributor listing [S]",
            "pins": "KiCad Diode:BAS16W: 1 A, 2 NC, 3 K; SOT-23 BAS16 sheet has the same order [S]",
            "lifecycle": "distributor listing [S]"})

# ---------------------------------------------------------------------------------------------
# Supplies

LDO_12V = IC(
    "TPS7A1601DGNR", manufacturer="Texas Instruments",
    footprint="Package_SO:Texas_DGN0008D_VSSOP-8-1EP_3x3mm_P0.65mm_EP2x2.94mm_Mask1.57x1.89mm",
    description="60 V 100 mA ultra-low-Iq adjustable LDO with enable, HVSSOP-8 PowerPAD",
    datasheet="https://www.ti.com/lit/ds/symlink/tps7a16.pdf",
    # all pins on the sides: generated top/bottom pins overlap the side pin names (framework layout)
    pins=[PinDef(8, "IN", "power_in", "left"), PinDef(5, "EN", "input", "left"),
          PinDef(4, "GND", "power_in", "left"), PinDef(9, "PAD", "passive", "left"),
          PinDef(1, "OUT", "power_out", "right"), PinDef(2, "FB", "input", "right"),
          PinDef(3, "PG", "open_collector", "right"), PinDef(7, "DELAY", "passive", "right"),
          PinDef(6, "NC", "no_connect", "right")],
    ratings=Ratings(limits=[VLimit(("IN",), ("GND",), 62), VLimit(("OUT",), ("GND",), 20),
                            VLimit(("FB",), ("GND",), 3), VLimit(("EN",), ("GND",), 62),
                            VLimit(("OUT", "FB", "EN"), ("IN",), 62, "true limit is +0.3 V above IN (asymmetric)"),
                            VLimit(("PG", "DELAY"), ("GND",), 5.5)],
                    t_min=-40, t_max=150),
    lifecycle="active", second_source="ADI LT3014 (pin-different) [I]",
    source={"pins": "TI SBVS171F (Oct 2015) Pin Functions (DGN): 1 OUT, 2 FB, 3 PG, 4 GND, 5 EN, 6 NC, 7 DELAY, "
                    "8 IN, thermal pad to GND; footprint pad 9 = PowerPAD [P]",
            "ratings": "SBVS171F 6.1 abs max: IN-GND -0.3..62, OUT-GND -0.3..20, OUT-IN -62..+0.3, FB-GND -0.3..3, "
                       "EN-IN -62..+0.3, EN-GND -0.3..62, PG/DELAY -0.3..5.5 V; TJ -40..150 C [P]",
            "lifecycle": "TI orderable addendum, Active [P]"})

LDO_5V = IC(
    "TPS70950DBVR", manufacturer="Texas Instruments", footprint="Package_TO_SOT_SMD:SOT-23-5",
    description="30 V 150 mA 1 uA-Iq LDO, 5.0 V fixed, SOT-23-5",
    datasheet="https://www.ti.com/lit/ds/symlink/tps709.pdf",
    pins=[PinDef(1, "IN", "power_in", "left"), PinDef(3, "EN", "input", "left"),
          PinDef(2, "GND", "power_in", "left"),
          PinDef(5, "OUT", "power_out", "right"), PinDef(4, "NC", "no_connect", "right")],
    ratings=Ratings(limits=[VLimit(("IN",), ("GND",), 32), VLimit(("EN",), ("GND",), 7),
                            VLimit(("OUT",), ("GND",), 7)], t_min=-55, t_max=150),
    lifecycle="active", second_source="TPS7A1650DGNR (Iq 5 uA, pin-different) [P]",
    source={"pins": "TI SBVS186H (Jul 2021) Table 5-1, DBV TPS709 column: 1 IN, 2 GND, 3 EN, 4 NC, 5 OUT [P]",
            "ratings": "SBVS186H 6.1 abs max: VIN -0.3..32 V, VEN -0.3..7 V, VOUT -0.3..7 V; recommended VIN "
                       "2.7-30 V; EN internal 300 nA pull-up, do not tie EN to IN [P]",
            "lifecycle": "TI orderable addendum, Active [P]"})

VREF = PartDef(
    mpn="REF35250QDBVR", manufacturer="Texas Instruments", symbol="Reference_Voltage:REF35250QDBVR",
    footprint="Package_TO_SOT_SMD:SOT-23-6", value="REF35250", category="ic",
    description="2.500 V nanopower series reference, +/-0.05 %, 12 ppm/K, 0.65 uA",
    datasheet="https://www.ti.com/lit/ds/symlink/ref35.pdf",
    ratings=Ratings(limits=[VLimit(("VIN",), ("GND",), 6.5), VLimit(("EN", "VREF"), ("GND",), 6.5,
                                                                    "<= IN + 0.3 V or 6.5 V")],
                    t_min=-55, t_max=125),
    lifecycle="active", second_source="TI REF3325 (pin-different) [I]",
    source={"pins": "TI SNAS809C (Sep 2024) Table 5-1: 1 GND, 2 GND, 3 EN, 4 VIN, 5 NR, 6 VREF; KiCad "
                    "Reference_Voltage:REF35250QDBVR matches [P]",
            "ratings": "SNAS809C 6.1 abs max: IN -0.3..6.5 V, EN and VREF -0.3..IN + 0.3 V (6.5 V max) [P]",
            "lifecycle": "TI orderable addendum, Active [P]"})

COMP = IC(
    "TLV7044PWR", manufacturer="Texas Instruments", footprint="Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
    description="Quad nanopower comparator, open-drain, 1.6-6.5 V, 0.335 uA/ch, built-in hysteresis",
    datasheet="https://www.ti.com/lit/ds/symlink/tlv7042.pdf",
    pins=[PinDef(3, "INA+", "input", "left"), PinDef(2, "INA-", "input", "left"),
          PinDef(5, "INB+", "input", "left"), PinDef(6, "INB-", "input", "left"),
          PinDef(10, "INC+", "input", "left"), PinDef(9, "INC-", "input", "left"),
          PinDef(12, "IND+", "input", "left"), PinDef(13, "IND-", "input", "left"),
          PinDef(1, "OUTA", "open_collector", "right"), PinDef(7, "OUTB", "open_collector", "right"),
          PinDef(8, "OUTC", "open_collector", "right"), PinDef(14, "OUTD", "open_collector", "right"),
          PinDef(4, "VCC", "power_in", "right"), PinDef(11, "VEE", "power_in", "right")],
    ratings=Ratings(limits=[VLimit(("VCC",), ("VEE",), 7, "supply"),
                            VLimit(("INA+", "INA-", "INB+", "INB-", "INC+", "INC-", "IND+", "IND-"), ("VEE",), 7,
                                   "inputs VEE - 0.3..7 V"),
                            VLimit(("OUTA", "OUTB", "OUTC", "OUTD"), ("VEE",), 7, "open-drain outputs")],
                    t_max=150),
    lifecycle="active", second_source="TI TLV3404IDR + external hysteresis (pin-compatible quad, SOIC) [P]",
    source={"pins": "TI SLVSE13J (Nov 2024) Table 4-3, TSSOP column: 1 OUTA, 2 -INA, 3 +INA, 4 VCC, 5 +INB, "
                    "6 -INB, 7 OUTB, 8 OUTC, 9 -INC, 10 +INC, 11 VEE, 12 +IND, 13 -IND, 14 OUTD [P]",
            "ratings": "SLVSE13J 5.1 abs max: VCC-VEE -0.3..7 V, inputs VEE - 0.3..7 V (diode-clamped to VEE, "
                       "<= 10 mA), TLV704x outputs VEE - 0.3..7 V; hysteresis 3-25 mV, offset +/-8 mV [P]",
            "lifecycle": "TI orderable addendum, Active [P]"})

NOR2 = PartDef(
    mpn="SN74LVC2G02DCTR", manufacturer="Texas Instruments", symbol="74xGxx:74LVC2G02",
    footprint="Package_SO:SSOP-8_2.95x2.8mm_P0.65mm", value="74LVC2G02", category="ic",
    description="Dual 2-input NOR gate, 1.65-5.5 V, SSOP-8 (DCT). Gate 1 inverts FLT_N, gate 2 makes RUN",
    datasheet="https://www.ti.com/lit/ds/symlink/sn74lvc2g02.pdf",
    pin_names={"1": "1A", "2": "1B", "7": "1Y", "5": "2A", "6": "2B", "3": "2Y"},
    ratings=Ratings(limits=[VLimit(("VCC",), ("GND",), 6.5), VLimit(("1A", "1B", "2A", "2B"), ("GND",), 6.5),
                            VLimit(("1Y", "2Y"), ("GND",), 6.5, "<= VCC + 0.5 V")], t_min=-40, t_max=125),
    lifecycle="active", second_source="Nexperia 74LVC2G02DP [I]",
    source={"pins": "TI SCES194N (May 2019) section 5 Pin Functions, DCT: 1 1A, 2 1B, 3 2Y, 4 GND, 5 2A, 6 2B, "
                    "7 1Y, 8 VCC [P]",
            "pin_names": "KiCad 74xGxx:74LVC2G02 leaves signal pins unnamed; names from SCES194N section 5 [P]",
            "ratings": "SCES194N 6.1 abs max: VCC -0.5..6.5 V, VI -0.5..6.5 V, VO -0.5..VCC + 0.5 V; 6.3 VIH 0.7 x VCC "
                       "at 4.5-5.5 V [P]",
            "lifecycle": "TI orderable addendum in SCES194N: SN74LVC2G02DCTR Active [P]"})

OPTO = PartDef(
    mpn="SFH617A-3X017T", manufacturer="Vishay Semiconductors", symbol="Isolator:SFH617A-3X017T",
    footprint="Package_DIP:SMDIP-4_W9.53mm_Clearance8mm", value="SFH617A-3", category="opto",
    description="Optocoupler, phototransistor, CTR 100-200 % at 10 mA, 70 V, 4470 Vrms, SMD-4 option 7",
    datasheet="https://www.vishay.com/docs/83740/sfh617a.pdf",
    pin_names={"1": "A", "2": "K", "3": "E", "4": "C"},
    ratings=Ratings(
        limits=[VLimit(("A",), ("K",), 6, "VR (LED)"), VLimit(("C",), ("E",), 70, "VCEO; VECO is 7 V (not expressible)")],
        pin_i_max={"A": 0.06, "K": 0.06, "C": 0.05, "E": 0.05},
        isolation=[Isolation(("A", "K"), ("C", "E"), v_iso_rms=4470, grade="reinforced", v_work_rms=629,
                             creepage_mm=7.0,
                             standard="DIN EN 60747-5-5 safe electrical insulation (VIORM 890 Vpk, VIOTM 8000 Vpk); "
                                      "UL 1577 4470 Vrms 1 min")],
        t_min=-55, t_max=100),
    lifecycle="active", second_source="Everlight EL817S1(C) [I]",
    source={"pins": "Vishay 83740 Rev 2.5 (18-Aug-2025) p.1 pinout: 1 A, 2 C(athode), 3 E, 4 C(ollector) [P]",
            "pin_names": "KiCad Isolator:SFH617A-3X017T leaves pins unnamed; names from 83740 p.1 [P]",
            "ratings": "83740 p.2 abs max: VR 6 V, IF 60 mA, VCEO 70 V, VECO 7 V, IC 50 mA; p.3 CTR -3: 100-200 % "
                       "at IF 10 mA, >= 34 % at 1 mA; p.4 safety: VISO 4470 Vrms 1 min (UL 1577), VIORM 890 Vpk, "
                       "VIOTM 8000 Vpk, CTI 175 (IIIa), creepage/clearance >= 7 mm (SMD-4 option 7), DTI >= 0.4 mm; "
                       "v_work_rms = 890 / sqrt(2) [P]",
            "lifecycle": "Vishay 83740 Rev 2.5 2025, ordering table lists -3X017T [P]"})

FET_LS = PartDef(
    mpn="2N7002-7-F", manufacturer="Diodes Incorporated", symbol="Transistor_FET:2N7002",
    footprint="Package_TO_SOT_SMD:SOT-23", value="2N7002", category="mosfet",
    description="N-MOSFET 60 V 120 mA (85 C) SOT-23 (enable level shifter)",
    datasheet="https://www.diodes.com/assets/Datasheets/2N7002.pdf",
    ratings=Ratings(limits=[VLimit(("D",), ("S",), 60), VLimit(("G",), ("S",), 20, "VGSS continuous")],
                    pin_i_max={"D": 0.12, "S": 0.12}, p_max=0.37, t_max=150),
    lifecycle="active", second_source="Nexperia 2N7002 [I]",
    source={"pins": "Diodes DS11303 Rev 40-2 (2024) p.1 SOT-23 top view: 1 G, 2 S, 3 D; KiCad "
                    "Transistor_FET:2N7002 matches [P]",
            "ratings": "DS11303 p.2: VDSS 60 V, VGSS +/-20 V continuous, ID 120 mA at 85 C (Note 5), PD 370 mW [P]",
            "lifecycle": "Diodes product page, Active 2024 [P]"})

PNP = PartDef(
    mpn="MMBT3906-7-F", manufacturer="Diodes Incorporated", symbol="Transistor_BJT:MMBT3906",
    footprint="Package_TO_SOT_SMD:SOT-23", value="MMBT3906", category="bjt",
    description="PNP 40 V 200 mA SOT-23 (fault driver, enable shifter)",
    datasheet="https://www.diodes.com/assets/Datasheets/MMBT3906.pdf",
    ratings=Ratings(limits=[VLimit(("C",), ("E",), 40, "VCEO"), VLimit(("C",), ("B",), 40, "VCBO"),
                            VLimit(("E",), ("B",), 6.0, "VEBO")],
                    pin_i_max={"C": 0.2}, p_max=0.31, t_max=150),
    lifecycle="active", second_source="onsemi MMBT3906 [I]",
    source={"pins": "Diodes DS30059 Rev 23-2 (2025) p.1 SOT-23: 1 B, 2 E, 3 C; KiCad Transistor_BJT:MMBT3906 "
                    "matches [P]",
            "ratings": "DS30059 p.2: VCBO -40 V, VCEO -40 V, VEBO -6.0 V, IC -200 mA, PD 310 mW (Note 5) [P]",
            "lifecycle": "Diodes product page, Active 2025 [P]"})

_ROHM_DS = "https://fscdn.rohm.com/en/products/databook/datasheet/opto/led/chip_mono/sml-d12x1-e.pdf"
LED_RED = LED("red", "0603", mpn="SML-D12V1WT86", manufacturer="Rohm", i_max=0.02, datasheet=_ROHM_DS,
              lifecycle="active", second_source="Vishay VLMS1300 [S]",
              source={"ratings": "Rohm SML-D12x1 (Rev.007, 2020) p.1 table: PD 54 mW, IF 20 mA, VR 5 V, "
                                 "Topr -40..85 C, VF 2.2 V typ at 20 mA [P]",
                      "pins": "KiCad Device:LED pin 1 = K, LED_0603 pad 1 = K; Rohm cathode mark not cross-checked [S]",
                      "lifecycle": "Rohm product page [S]"})
LED_RED.ratings.t_min, LED_RED.ratings.t_max = -40, 85
LED_GRN = LED("green", "0603", mpn="SML-D12M1WT86", manufacturer="Rohm", i_max=0.02, datasheet=_ROHM_DS,
              lifecycle="active", second_source="Vishay VLMG1300 [S]",
              source={"ratings": "Rohm SML-D12x1 (Rev.007, 2020) p.1 table (D12M1W yellowish green): IF 20 mA, "
                                 "VR 5 V, Topr -40..85 C [P]",
                      "pins": "KiCad Device:LED pin 1 = K [S]", "lifecycle": "Rohm product page [S]"})
LED_GRN.ratings.t_min, LED_GRN.ratings.t_max = -40, 85

NTC = PartDef(
    mpn="NCP15WM474E03RC", manufacturer="Murata", symbol="Device:Thermistor_NTC",
    footprint="Resistor_SMD:R_0402_1005Metric", value="470k NTC", category="thermistor",
    description="NTC thermistor 470 kOhm +/-3 %, B25/50 4500 K (B25/85 4582 K), 0402",
    datasheet="https://pim.murata.com/asset/pim4/ntcForTemperatureSensor/SPEC_NCP15_PDF_NTCFORTEMPERATURESENSOR",
    ratings=Ratings(v_max=5.0, t_min=-40, t_max=125),
    lifecycle="active", second_source="none verified; any 0402 470 kOhm B ~4500 K NTC with R138 re-check",
    source={"ratings": "Murata NCP15 spec table row NCP15WM474E03RC: 470 k +/-3 %, B 4500 +/-3 % (B25/85 4582 typ), "
                       "max operating current 0.015 mA (0.1 C self-heating, note *3), maximum voltage 5.00 V "
                       "(self-heating limit, note *4), -40..125 C [P]",
            "lifecycle": "in current Murata spec [P]; 70-week lead time reported [S]"})

# ---------------------------------------------------------------------------------------------
# Passives. Small MLCCs: Murata GRM, one MPN per value (DESIGN.md section 8).

_MUR = "https://www.murata.com/en-us/products/productdetail?partno="


def _mlcc(value, volts, pkg, diel, mpn, second):
    return C(value, volts, pkg, dielectric=diel, mpn=mpn, manufacturer="Murata", datasheet=_MUR + mpn,
             lifecycle="active", second_source=second,
             source={"ratings": f"Murata {mpn}: {value}F {volts} V {diel} {pkg} (product search) [S]",
                     "lifecycle": "Murata product search, in production [S]"})


C_1U50 = _mlcc("1u", 50, "0805", "X7R", "GRM21BR71H105KA12L", "Samsung CL21B105KBFNNNE [S]")
C_1U25 = _mlcc("1u", 25, "0603", "X7R", "GRM188R71E105KA12D", "Samsung CL10B105KA8NNNC [S]")
C_10U25 = _mlcc("10u", 25, "1206", "X7R", "GRM31CR71E106KA12L", "Samsung CL31B106KAHNNNE [S]")
C_4U7 = _mlcc("4.7u", 25, "0805", "X7R", "GRM21BR71E475KA73L", "Samsung CL21B475KAFNNNE [S]")
C_100N = _mlcc("100n", 50, "0603", "X7R", "GRM188R71H104KA93D", "Samsung CL10B104KB8NNNC [S]")
C_470N = _mlcc("470n", 25, "0603", "X7R", "GRM188R71E474KA12D", "Samsung CL10B474KA8NNNC [S]")
C_10N = _mlcc("10n", 50, "0603", "X7R", "GRM188R71H103KA01D", "Samsung CL10B103KB8NNNC [S]")
C_470P = _mlcc("470p", 50, "0603", "C0G", "GRM1885C1H471JA01D", "Samsung CL10C471JB8NNNC [S]")
C_100P = _mlcc("100p", 50, "0603", "C0G", "GRM1885C1H101JA01D", "Samsung CL10C101JB8NNNC [S]")

_CRCW_DS = "https://www.vishay.com/docs/20035/dcrcwe3.pdf"


def _crcw(value, code):
    return R(value, "0603", tol="1%", p_max=0.1, v_max=75, mpn=f"CRCW0603{code}FKEA", manufacturer="Vishay Dale",
             datasheet=_CRCW_DS, lifecycle="active", second_source="Yageo RC0603FR-07 same value [I]",
             source={"ratings": "Vishay 20035 (rev 01-Jan-2026) D11/CRCW0603: P70 0.10 W, Umax 75 V, "
                                "1 Ohm-10 MOhm at 1 % [P]",
                     "lifecycle": "Vishay product page, Active [P]"})


R_4R7 = _crcw("4.7", "4R70")
R_750 = _crcw("750", "750R")
R_825 = _crcw("825", "825R")
R_249K = _crcw("249k", "249K")
R_30K9 = _crcw("30.9k", "30K9")
R_36K5 = _crcw("36.5k", "36K5")
R_10K = _crcw("10k", "10K0")
R_20K = _crcw("20k", "20K0")
R_22K1 = _crcw("22.1k", "22K1")
R_24K9 = _crcw("24.9k", "24K9")
R_49K9 = _crcw("49.9k", "49K9")
R_100K = _crcw("100k", "100K")
R_909K = _crcw("909k", "909K")
R_1M = _crcw("1M", "1M00")
R_1M1 = _crcw("1.1M", "1M10")
R_2M26 = _crcw("2.26M", "2M26")
R_4M99 = _crcw("4.99M", "4M99")

_TNPW_DS = "https://www.vishay.com/docs/28758/tnpw_e3.pdf"


def _tnpw(value, code):
    return R(value, "1206", tol="0.1%", p_max=0.52, v_max=200, mpn=f"TNPW1206{code}BEEA", manufacturer="Vishay Draloric",
             datasheet=_TNPW_DS, lifecycle="active", second_source="Panasonic ERA-8AEB same value [I]",
             fields={"TCR": "25 ppm/K"},
             source={"ratings": "Vishay 28758 (rev 10-Apr-2026) p.1: TNPW1206 1 Ohm-2 MOhm, +/-0.1 %, 25 ppm/K, "
                                "P70 0.52 W, Umax 200 V [P]",
                     "lifecycle": "Vishay product page, Active [P]"})


R_2M00 = _tnpw("2M", "2M00")
R_1M67 = _tnpw("1.67M", "1M67")
R_1M85 = _tnpw("1.85M", "1M85")
R_1M96 = _tnpw("1.96M", "1M96")
R_1M58 = _tnpw("1.58M", "1M58")
R_1M70 = _tnpw("1.7M", "1M70")

# ---------------------------------------------------------------------------------------------
# Board I/O, fuses, jumper, mechanical

FUSE_BOARD = Fuse(6, 600, "custom:Fuseholder_Keystone_3576_10x38mm", mpn="KLKD006.T", manufacturer="Littelfuse",
                  breaking_a=10000, i2t=63,
                  datasheet="https://www.farnell.com/datasheets/2603270.pdf", lifecycle="active",
                  second_source="other UL 248-19 DC-rated 10x38 midget fuse, 6 A, >= 1 kA DC [I]",
                  source={"ratings": "Littelfuse KLKD datasheet Rev 061217 p.1: 600 VAC/VDC, fast acting, DC 10 kA "
                                     "(UL 248-19) / 50 kA (UL 248-14) for 1/10-30 A; p.2 KLKD 6: cold R 26.1 mOhm, "
                                     "average melting I2t 63 A2s, clearing I2t 96.8 A2s at 20 kA [P]",
                          "lifecycle": "Littelfuse catalog listing KLKD006.T [P]"}).with_(
    description="Fuse 10x38 mm midget 6 A fast, 600 VDC, 10 kA DC (board tap fuse), in a Keystone 3576 holder")

FUSE_HOLDER_PCB = PartDef(mpn="3576", manufacturer="Keystone Electronics", symbol="Mechanical:Housing", footprint=None,
                          value="3576", category="mechanical", prefix="XH",
                          description="PCB fuse holder for 10x38 mm (midget/SPF), THM, UL 30 A 500 VAC; pads are in "
                                      "the F footprint (custom:Fuseholder_Keystone_3576_10x38mm)",
                          datasheet="https://www.keyelco.com/userAssets/file/M65p45.pdf", on_board=False,
                          lifecycle="active", second_source="Littelfuse 01020078Z-style 10x38 PCB clips [I]",
                          source={"ratings": "Keystone catalog M65 p.45: Nylon 46 UL 94V-0, UL 30 A @ 500 VAC, 38.1 mm "
                                             "terminal pitch [P]"})

J_TAP = Conn(5, "Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_5-G-5,08_1x05_P5.08mm_Horizontal", i_max=12,
             v_max=320, mpn="1757271", manufacturer="Phoenix Contact",
             datasheet="https://www.phoenixcontact.com/en-us/products/pcb-header-mstba-25-5-g-508-1757271",
             lifecycle="active", second_source="Wurth 691313710005 [S]",
             source={"ratings": "MSTBA 2,5/5-G-5,08 (secondary listing): 12 A, 320 V (III/2) [S]",
                     "pins": "positions 1..5 along the header = KiCad pads 1..5 [S]",
                     "lifecycle": "distributor listing [S]"}).with_(
    description="PCB header MSTBA 2,5/5-G-5,08, 5 pos, 5.08 mm, keyed plug (tap input)")

J_ALM = Conn(2, "Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal", i_max=12,
             v_max=320, mpn="1757242", manufacturer="Phoenix Contact",
             datasheet="https://www.phoenixcontact.com/en-us/products/pcb-header-mstba-25-2-g-508-1757242",
             lifecycle="active", second_source="Wurth 691313710002 [S]",
             source={"ratings": "MSTBA 2,5/2-G-5,08 (secondary listing): 12 A, 320 V [S]",
                     "pins": "positions 1..2 = KiCad pads 1..2 [S]", "lifecycle": "distributor listing [S]"}).with_(
    description="PCB header MSTBA 2,5/2-G-5,08, 2 pos (isolated alarm contact)")

JUMPER = PartDef(mpn="61300211121", manufacturer="Wurth Elektronik", symbol="Jumper:Jumper_2_Open",
                 footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", value="EN", category="switch",
                 prefix="JP", description="Pin header 1x2 2.54 mm (channel enable jumper; shunt 60900213421)",
                 datasheet="https://www.we-online.com/catalog/en/PHD_2_54_THT_PIN_HEADER_61300211121",
                 ratings=Ratings(v_max=250, i_max=3),
                 lifecycle="active", second_source="any 2.54 mm 1x2 header",
                 source={"ratings": "Wurth WR-PHD 2.54 mm header: 3 A, 250 VAC [S]",
                         "lifecycle": "Wurth catalog [S]"})

SHUNT = PartDef(mpn="60900213421", manufacturer="Wurth Elektronik", symbol="Mechanical:Housing", footprint=None,
                value="60900213421", category="mechanical", prefix="JS",
                description="Jumper shunt 2.54 mm, closed top (fitted on JPk01 when channel k is used)",
                datasheet="https://www.we-online.com/catalog/en/WR-PHD_2_54_SHUNT_60900213421", on_board=False,
                lifecycle="active", second_source="any 2.54 mm shunt", source={"ratings": "Wurth catalog [S]"})

HOLE_M3 = MountingHole("MountingHole:MountingHole_3.2mm_M3",
                       notes="NPTH 3.2 mm for M3 on nylon standoffs; 4 mm copper-free ring")

# ---------------------------------------------------------------------------------------------
# Off-board harness (block board="off": BOM only)

FUSE_HARNESS = Fuse(10, 600, None, mpn="KLKD010.T", manufacturer="Littelfuse", breaking_a=10000, i2t=278,
                    datasheet="https://www.farnell.com/datasheets/2603270.pdf", lifecycle="active",
                    second_source="other UL 248-19 DC-rated 10x38 midget fuse >= 10 kA DC [I]",
                    source={"ratings": "Littelfuse KLKD datasheet Rev 061217 p.1: 600 VAC/VDC, fast acting, DC 10 kA "
                                       "(UL 248-19) / 50 kA (UL 248-14); p.2 KLKD 10: cold R 12.8 mOhm, average "
                                       "melting I2t 278 A2s, clearing I2t 455 A2s at 20 kA [P]",
                            "lifecycle": "Littelfuse catalog [P]"}).with_(
    description="Fuse 10x38 mm midget 10 A fast, 600 VDC, 10 kA DC (battery-end tap fuse)")


def _mech(mpn, manufacturer, description, datasheet, source, prefix, **kw):
    return PartDef(mpn=mpn, manufacturer=manufacturer, symbol="Mechanical:Housing", footprint=None, value=mpn,
                   category="mechanical", prefix=prefix, description=description, datasheet=datasheet,
                   on_board=False, source=source, **kw)


FUSE_HOLDER = _mech("HEB-AW-RLC-A", "Eaton Bussmann",
                    "In-line fuse holder for 13/32 x 1-1/2 in fuses, 30 A 600 V, crimp 16-8 AWG, sealed boot",
                    "https://www.eaton.com/us/en-us/skuPage.HEB-AW-RLC-A.html",
                    {"ratings": "Eaton HEB series listing: 30 A, 600 V, 13/32 x 1-1/2 in [S]"}, "XF",
                    lifecycle="active", second_source="Littelfuse LEY in-line holder [S]")
WIRE = _mech("3077 (14 AWG UL1015)", "Alpha Wire",
             "Hook-up wire UL1015 14 AWG tinned, 600 V 105 C, 8.3 mOhm/m; T0 black, T1-T4 red with number sleeves; "
             "<= 3 m per tap (16 AWG allowed <= 2 m)",
             "https://www.alphawire.com", {"ratings": "UL1015 14 AWG: 600 V, 105 C; 8.28 mOhm/m (AWG table) [S]; "
                                                   "Alpha Wire part number for 14 AWG UL1015 [I]"}, "W",
             lifecycle="active", second_source="any UL1015 / TXL 14 AWG").with_(value="UL1015 14AWG")
RING_LUG = Conn(1, None, mpn="PV14-516R-L", manufacturer="Panduit",
                datasheet="https://www.panduit.com/en/products/wire-terminals-and-accessories/ring-terminals/pv14-516r-l.html",
                lifecycle="active", second_source="TE PIDG 16-14 AWG 5/16 in ring [S]",
                source={"pins": "single crimp barrel / ring [S]"}).with_(
    description="Ring terminal vinyl-insulated 16-14 AWG, 5/16 in stud; stacked on top of the main cable lug",
    prefix="LG")
FERRULE = _mech("AI 2,5-8 BU (3200522)", "Phoenix Contact", "Ferrule 2.5 mm2 (14 AWG) with collar, 8 mm",
                "https://www.phoenixcontact.com/en-us/products/ferrule-ai-25-8-bu-3200522",
                {"ratings": "Phoenix AI 2,5-8 BU listing [S]"}, "FE", lifecycle="active",
                second_source="Weidmuller H2.5/14 [S]").with_(value="AI 2,5-8 BU")
PLUG_TAP = Conn(5, None, i_max=12, v_max=320, mpn="1757048", manufacturer="Phoenix Contact",
                datasheet="https://www.phoenixcontact.com/en-us/products/pcb-plug-mstb-25-5-st-508-1757048",
                lifecycle="active", second_source="Wurth 691304100005 [S]",
                source={"ratings": "MSTB 2,5/5-ST-5,08 (secondary listing): 12 A, 320 V, 0.2-2.5 mm2 [S]",
                        "pins": "positions 1..5 mate J1 pads 1..5 [S]", "lifecycle": "distributor listing [S]"}).with_(
    description="Plug MSTB 2,5/5-ST-5,08, 5 pos screw (tap harness to J1)", prefix="P")
PLUG_ALM = Conn(2, None, i_max=12, v_max=320, mpn="1757019", manufacturer="Phoenix Contact",
                datasheet="https://www.phoenixcontact.com/en-us/products/pcb-plug-mstb-25-2-st-508-1757019",
                lifecycle="active", second_source="Wurth 691304100002 [S]",
                source={"ratings": "MSTB 2,5/2-ST-5,08 (secondary listing): 12 A, 320 V [S]",
                        "pins": "positions 1..2 mate J2 pads 1..2 [S]", "lifecycle": "distributor listing [S]"}).with_(
    description="Plug MSTB 2,5/2-ST-5,08, 2 pos screw (alarm wiring to J2)", prefix="P")
PLUG_BRIDGE = PartDef(mpn="14 AWG link in P1", manufacturer="(harness)", symbol="Jumper:Jumper_2_Bridged",
                      footprint=None, value="BRIDGE", category="other", prefix="BR",
                      description="14 AWG link inside plug P1 from an unused position to the highest used position "
                                  "(N < 4 only)", datasheet="https://www.alphawire.com", on_board=False, lifecycle="active",
                      second_source="any 14-16 AWG wire",
                      source={"ratings": "harness item; carries divider/sleep current only (uA) [I]"})
