# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Part cards for rpi-mains-relay: one PartDef per distinct part (see DESIGN.md section 8).

Every fact typed here cites where it was read (source=). Evidence was gathered in October 2026:
datasheets downloaded and read, lifecycle from Digi-Key search results. [S] = distributor listing
or secondary source only; [I] = inferred; both are flagged in DESIGN.md.
"""
from kaesynth import Isolation, PartDef, Ratings, VLimit
from kaesynth.lib import C, LED, R, Conn, Fuse, MountingHole, TestPoint

# ---------------------------------------------------------------------------------------------
# Mains side

RELAY = PartDef(
    mpn="G5RL-1A-E-TV8 DC5", manufacturer="Omron Electronic Components (Aratas)",
    symbol="Relay:G2RL-1A-E", footprint="Relay_THT:Relay_SPST_Omron_G2RL-1A-E",
    value="G5RL-1A-E-TV8 DC5", category="relay",
    description="Relay SPST-NO 16 A 277 VAC, TV-8, 1/2 hp, 5 VDC coil 400 mW, reinforced coil-contact 8/8 mm",
    datasheet="https://omronfs.omron.com/en_US/ecb/products/pdf/en-g5rl.pdf",
    # KiCad's G2RL-1A-E symbol names its pins after their numbers; give them datasheet meaning.
    # Coil = A1/A2 (left side of the symbol graphic), contact = 13 (moving) / 14 (fixed).
    pin_names={"A1": "COIL_1", "A2": "COIL_8", "13": "C_3_6", "14": "C_4_5"},
    ratings=Ratings(
        limits=[VLimit(("COIL_1",), ("COIL_8",), 6.5, "coil max voltage 130 % of 5 V"),
                VLimit(("C_3_6",), ("C_4_5",), 354, "max switching voltage 250 VAC = 354 V peak")],
        pin_i_max={"C_3_6": 16, "C_4_5": 16},
        isolation=[Isolation(("COIL_1", "COIL_8"), ("C_3_6", "C_4_5"), v_iso_rms=6000, grade="reinforced",
                             v_work_rms=250, creepage_mm=8.0, material_group="IIIa",
                             standard="EN 61810-1 (VDE 40007172): reinforced coil-contact, rated insulation "
                                      "voltage 250 V, PD3, OVC III; 10 kV 1.2/50 impulse; MG IIIa (PTI 250)")],
        t_min=-40, t_max=85),
    lifecycle="active",
    second_source="G5RL-1A-E-HR DC5 (same footprint; TV-5, not TV-8); G2RL-1A-E DC5 (same footprint, general "
                  "use only)",
    source={
        "pin_names": "G5RL DS Cat. No. K132-E1-10 p.5 'G5RL-1A-E-LN/-E-HR/-E-TV8 Terminal Arrangement/Internal "
                     "Connections (Bottom View)': coil 1-8, contact 3+6 (joined) to 4+5 (joined); KiCad pads "
                     "13 = (0,20)/(7.5,20) = pins 3/6, 14 = (0,25)/(7.5,25) = pins 4/5, A1/A2 = pins 1/8 (coil, "
                     "no polarity); hole pattern 7.5/20/5 mm, 1.3 mm (p.5) matches the G2RL-1A-E footprint",
        "ratings": "G5RL DS p.1-2 coil table (high-inrush: 5 V 80 mA 62.5 ohm ~400 mW, operate <=70 %, release "
                   ">=10 %, max 130 %), p.2 contacts (16 A 250 VAC, max switching 250 VAC), p.3 characteristics "
                   "(6000 VAC coil-contact 1 min, 10 kV impulse, clearance/creepage 8/8 mm, release 5 ms, "
                   "-40..85 C), p.6 approvals (UL/CSA E41643/LR31928: 16 A 277 VAC general use 40 C 50k ops, "
                   "TV-8 120 VAC 25k, 1/2 hp 120 VAC 6k, A300; VDE: 16 A 250 VAC 85 C, 240 VAC 100 A pk "
                   "inrush/10 A steady 50k; reinforced, MG IIIa, PTI 250)",
        "lifecycle": "Digi-Key Z5885-ND, Active, Oct 2026 (listed as Aratas, formerly Omron Components)",
    })

_WAGO_RATINGS = ("UL 1059 (cURus E45172) use groups B/C 600 V 31 A; IEC 60664-1 1000 V (PD2, OVC II), 8 kV, "
                 "41 A; solid 24-8 AWG; strip 11-13 mm; PA66 UL94 V-0; -60..105 C")

TERM_IN = Conn(
    2, "custom:WAGO_2606-3102_020-000", i_max=31, v_max=600, mpn="2606-3102/020-000", manufacturer="WAGO",
    datasheet="https://www.wago.com/2606-3102/020-000",
    lifecycle="active", second_source="none drop-in (footprint is WAGO-specific)",
    notes="custom footprint (footprints/make_footprints.py) from the data sheet drawing: hole 2.0 (+0.1) mm, pad "
          "3.5 mm, pole 2 pin at (+7.5, +12.5) mm from pole 1; body 17.85 x 24.0 mm; pole-1 pin 5.5 mm from its end "
          "face and 7.7 mm from the wire-entry face; height 27 mm (31 mm with lever)",
    source={"ratings": f"WAGO data sheet 2606-3102/020-000 v28.02.2024 p.1-3: {_WAGO_RATINGS}",
            "pins": "same data sheet p.1 'Dimensions in mm' (1 solder pin per pole, staggered)",
            "lifecycle": "Digi-Key 2606-3102/020-000 Active, Oct 2026"}).with_(
    description="PCB terminal block 2-pole, lever, push-in CAGE CLAMP, 6 mm2, 7.5 mm pitch, staggered pins")

TERM_OUT = Conn(
    3, "custom:WAGO_2606-3103_020-000", i_max=31, v_max=600, mpn="2606-3103/020-000", manufacturer="WAGO",
    datasheet="https://www.wago.com/2606-3103/020-000",
    lifecycle="active", second_source="none drop-in (footprint is WAGO-specific)",
    notes="custom footprint as TERM_IN; pole 3 on the pole-1 row at +15 mm; body 25.35 x 24 mm",
    source={"ratings": f"WAGO data sheet 2606-3103/020-000 v22.10.2026 p.1-3: {_WAGO_RATINGS}; width 25.35 mm, "
                       "depth 24 mm, solder pin 1.5 x 1.2 mm, drilled hole 2 (+0.1) mm, 1 pin per pole staggered",
            "pins": "data sheet 2606-3102/020-000 'Dimensions in mm' (same series drawing; L = (poles - 1) x 7.5 + "
                    "10.35 mm confirmed on the -3103 sheet)",
            "lifecycle": "WAGO data sheet current (v22.10.2026); distributor stock not checked [I]"}).with_(
    description="PCB terminal block 3-pole, lever, push-in CAGE CLAMP, 6 mm2, 7.5 mm pitch, staggered pins")

FUSE_PSU = Fuse(
    1, 354, "Fuse:Fuseholder_Clip-6.3x32mm_Littelfuse_102071_Inline_P34.70x7.60mm_D2.00mm_Horizontal",
    mpn="0326001.MXP", manufacturer="Littelfuse", breaking_a=10000,
    datasheet="https://www.standardelectricsupply.com/Littelfuse-0326001-MXP-Slo-Blo-Cartridge-Fuse",
    lifecycle="active", second_source="Eaton Bussmann MDA-1-R (3AB ceramic time-delay) [unverified]",
    notes="cartridge in 2 x Littelfuse 01020071Z PCB clips (BOM line MP13); clips are live L: mains region only",
    source={"ratings": "[S] distributor listings for 0326001.MXP/.VXP (Standard Electric Supply, Van Meter, "
                       "Buerklin): 1 A, 250 VAC, 3AB 6.3 x 32 mm ceramic, slo-blo; interrupting 10 kA at 125 "
                       "VAC/VDC, 100 A at 250 VAC; 135 % 1 h, 200 % 5-30 s. Littelfuse 325/326 data sheet not "
                       "opened (Akamai block): re-check before release",
            "lifecycle": "Littelfuse 326 series product pages list 0326.100 ... 03262.5 as current [S]"}).with_(
    description="Fuse 1 A 250 VAC time-lag, 3AB 6.3 x 32 mm ceramic, 10 kA at 125 VAC (supply branch)")

PSU = PartDef(
    mpn="IRM-20-5", manufacturer="Mean Well", symbol="Converter_ACDC:IRM-20-5",
    footprint="Converter_ACDC:Converter_ACDC_MeanWell_IRM-20-xx_THT", value="IRM-20-5", category="module",
    description="AC/DC module 85-305 VAC in, 5 V 4 A, Class II (reinforced), UL/IEC 62368-1, LPS, encapsulated",
    datasheet="https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF",
    pin_names={"1": "AC/L", "2": "AC/N", "3": "-Vo", "4": "+Vo"},
    ratings=Ratings(
        limits=[VLimit(("AC/L",), ("AC/N",), 431, "305 VAC max input = 431 V peak")],
        pin_i_max={"+Vo": 4.0, "-Vo": 4.0},
        isolation=[Isolation(("AC/L", "AC/N"), ("-Vo", "+Vo"), v_iso_rms=4200, grade="reinforced",
                             v_work_rms=305, creepage_mm=42.0,
                             standard="UL/IEC/EN 62368-1 (OVC II), IEC/EN 61558-1/-2-16 (OVC III), Class II "
                                      "(no FG pin); creepage = pin-to-pin outside the potting (KiCad footprint)")],
        t_min=-30, t_max=85),
    lifecycle="active", second_source="RECOM RAC20-05SK (different footprint) [unverified]; IRM-15-5 (same "
                                      "case 219A footprint, 3 A, steeper derating)",
    source={"pin_names": "IRM-20 SPEC (2025-11-21) p.3 'Mechanical Specification' bottom view: AC/N and AC/L 20.8 mm "
                         "apart at one end, -V and +V 8 mm apart at the other, 45 mm between ends; KiCad footprint "
                         "pads 1 AC/L (0,0), 2 AC/N (0,20.8), 3 -Vo (45,20.8), 4 +Vo (45,12.8) agree",
            "ratings": "IRM-20 SPEC p.1-2: 5 V 4 A 20 W, +/-2.5 %, ripple 200 mVp-p, 85-305 VAC, setup 1000 ms, "
                       "hold-up 8 ms typ at 115 VAC full load, inrush 20 A typ cold 115 VAC, AC current 0.6 A at "
                       "115 VAC, leakage < 0.25 mA at 277 VAC, overload 115-160 % hiccup, OVP 5.75-6.75 V (shut "
                       "off, zener clamp), I/P-O/P 4.2 kVAC, 100 Mohm/500 VDC, -30..85 C with derating (5 V: 100 % "
                       "to 45 C, 50 % at 70 C), input derating below 115 VAC (80 % at 85 VAC); EN 55032 class B "
                       "without external parts, EN 61000-4-5 level 4 2 kV L-N; 'Isolation Class II', 'Pass LPS', "
                       "OVC III (61558), OVC II (62368-1); 52.4 x 27.2 x 24 mm",
            "lifecycle": "Mean Well spec revision 2025-11-21 (current); Digi-Key listing 7704667 seen in search [S]"})

# ---------------------------------------------------------------------------------------------
# SELV side

SOCKET_PI = Conn(
    40, "custom:RPi_Zero2W_Socket_2x20_P2.54mm", i_max=3.0, v_max=250, mpn="PPPC202LFBN-RC",
    manufacturer="Sullins Connector Solutions", rows=2,
    datasheet="https://www.futureelectronics.com/p/interconnect--connectors-pcb--socket-plug-board-mount/"
              "pppc202lfbn-rc-sullins-1050247",
    lifecycle="active", second_source="Samtec SSW-120-01-G-D (8.38 mm body) [unverified]",
    notes="custom footprint: PinHeader handedness (Pi component side up, header on its underside), Pi outline, "
          "antenna rule area",
    source={"ratings": "[S] Digi-Key / Future / Zenode listings: 2 x 20, 2.54 mm, female, through hole, insulator "
                       "8.51 mm (0.335 in), 3 A, 250 VDC, gold, polyester UL94 V-0, -40..105 C",
            "lifecycle": "distributor listings show it stocked (Future, Digi-Key) [S]; Sullins drawing not opened"}).with_(
    description="Socket 2x20 2.54 mm, 8.51 mm, gold: Raspberry Pi Zero 2 W carrier (Pi component side up)")

MOSFET = PartDef(
    mpn="AO3400A", manufacturer="Alpha & Omega Semiconductor", symbol="Transistor_FET:AO3400A",
    footprint="Package_TO_SOT_SMD:SOT-23", value="AO3400A", category="mosfet",
    description="N-MOSFET 30 V 5.7 A, Rds(on) <= 48 mOhm at Vgs 2.5 V",
    datasheet="https://www.aosmd.com/res/datasheets/AO3400A.pdf",
    ratings=Ratings(limits=[VLimit(("D",), ("S",), 30), VLimit(("G",), ("S",), 12)],
                    pin_i_max={"D": 4.7, "S": 4.7}, p_max=0.9, t_max=150),
    lifecycle="active", second_source="Diodes DMN2041L [unverified]",
    source={"pins": "AO3400A DS rev 3.1 (Jul 2023) p.1 'SOT23 Top View': 1 G, 2 S, 3 D; KiCad symbol "
                    "Transistor_FET:AO3400A numbers G=1 S=2 D=3",
            "ratings": "AO3400A DS rev 3.1 p.1 abs max: VDS 30 V, VGS +/-12 V, ID 4.7 A at 70 C, PD 0.9 W at 70 C; "
                       "p.2 VGS(th) 0.65-1.45 V, RDS(on) <= 48 mOhm at VGS 2.5 V",
            "lifecycle": "datasheet rev Jul 2023; Digi-Key listing (status not shown) [I]"})

WATCHDOG = PartDef(
    mpn="SN74LVC1G123DCTR", manufacturer="Texas Instruments", symbol="74xGxx:74LVC1G123",
    footprint="Package_SO:SSOP-8_2.95x2.8mm_P0.65mm", value="74LVC1G123", category="ic",
    description="Retriggerable monostable, Schmitt inputs, glitch-free power-up reset (heartbeat watchdog)",
    datasheet="https://www.ti.com/lit/ds/symlink/sn74lvc1g123.pdf",
    ratings=Ratings(limits=[VLimit(("VCC",), ("GND",), 6.5, "abs max 6.5 V; recommended 1.65-5.5 V", v_min=-0.5,
                                   v_rec=5.5),
                            VLimit(("~{A}", "B", "~{CLR}"), ("GND",), 6.5, "abs max 6.5 V; inputs accept 5.5 V",
                                   v_min=-0.5, v_rec=5.5)],
                    t_min=-40, t_max=125),
    lifecycle="active", second_source="Nexperia 74LVC1G123DP (different package) [unverified]",
    source={"pins": "TI SCES586E (Mar 2024) Fig. 4-1 DCT SSOP-8 top view and Table 4-1: 1 A, 2 B, 3 CLR, 4 GND, "
                    "5 Q, 6 Cext, 7 Rext/Cext, 8 VCC; KiCad 74xGxx:74LVC1G123 uses the same numbers",
            "ratings": "SCES586E 5.1 abs max: VCC and VI -0.5..6.5 V, IO +/-50 mA; 5.3: VCC 1.65-5.5 V, Rext >= 1 kohm at VCC >= 3 V, Rext/Cext never directly to "
                       "GND/VCC, -40..125 C; 5.5 VOH >= VCC - 0.1 V at -100 uA, II +/-1 uA, Rext/Cext leakage "
                       "+/-0.25 uA; 5.8/5.9 twOUT 1.0-1.1 ms at Rext 10 kohm, Cext 0.1 uF, 3.3 V; features: "
                       "retriggerable, glitch-free power-up reset, Ioff partial power-down; Table 4-1: A falling-edge "
                       "(B, CLR high), B rising-edge (A low, CLR high), CLR also a rising-edge trigger with A low, "
                       "B high",
            "lifecycle": "SCES586E (Mar 2024) is PRODUCTION DATA; distributor status not checked [I]"})

DIODE_FLYBACK = PartDef(
    mpn="1N4148W-7-F", manufacturer="Diodes Incorporated", symbol="Diode:1N4148W",
    footprint="Diode_SMD:D_SOD-123", value="1N4148W", category="diode",
    description="Switching diode 100 V 300 mA SOD-123 (relay coil flyback)",
    datasheet="https://www.diodes.com/assets/Datasheets/ds30086.pdf",
    ratings=Ratings(v_max=100, i_max=0.3, p_max=0.4),
    lifecycle="active", second_source="Vishay 1N4148W [unverified]",
    source={"ratings": "Diodes DS30086 p.2 max ratings: VRWM 100 V, IFM 300 mA, IFSM 2 A (1 us), PD 400 mW",
            "pins": "DS30086 p.1 'Polarity: Cathode Band'; KiCad Diode:1N4148W pin 1 = K, 2 = A"})

LED_GREEN = LED(
    "green", "0603", mpn="APT1608SGC", manufacturer="Kingbright", i_max=0.025,
    datasheet="https://www.kingbrightusa.com/images/catalog/SPEC/APT1608SGC.pdf",
    lifecycle="active", second_source="Wurth 150060VS75000",
    source={"ratings": "APT1608SGC DS p.2 abs max: IF 25 mA, PD 62.5 mW, VR 5 V, -40..85 C; VF 2.2/2.5 V at 20 mA",
            "pins": "APT1608SGC DS p.1 package drawing: pin 1 cathode, pin 2 anode (polarity mark)",
            "lifecycle": "Digi-Key Active, Oct 2026"})

TVS_5V = PartDef(
    mpn="SMAJ7.0A-E3/61", manufacturer="Vishay General Semiconductor", symbol="Diode:SMAJ5.0A",
    footprint="Diode_SMD:D_SMA", value="SMAJ7.0A", category="tvs",
    description="TVS unidirectional 400 W, VWM 7.0 V, VC 12.0 V at 33.3 A",
    datasheet="https://www.vishay.com/docs/88390/smaj50a.pdf",
    # KiCad's SMAJ5.0A symbol (same family and package) names its pins A1/A2; the bar is drawn at pin 1.
    pin_names={"1": "K", "2": "A"},
    ratings=Ratings(v_max=7.0, polarity=None),
    lifecycle="active", second_source="Littelfuse SMAJ7.0A [unverified]",
    source={"ratings": "Vishay SMAJ5.0A-188CA DS p.2 table: SMAJ7.0A VBR 7.78-8.60 V, VWM 7.0 V, ID 200 uA, "
                       "IPPM 33.3 A, VC 12.0 V; p.1 400 W 10/1000 us, UL 497B",
            "pin_names": "DS p.1 'Polarity: for unidirectional types the band denotes cathode'; D_SMA pad 1 = "
                         "cathode; KiCad Diode:SMAJ5.0A graphic has the bar at pin 1",
            "lifecycle": "Digi-Key listing, status not shown [I]"})

DIODE_CLAMP = PartDef(
    mpn="BAT54S-7-F", manufacturer="Diodes Incorporated", symbol="Diode:BAT54S",
    footprint="Package_TO_SOT_SMD:SOT-23", value="BAT54S", category="diode",
    description="Dual series Schottky 30 V 200 mA (ARM_FB clamp to GND and +3V3)",
    datasheet="https://www.diodes.com/assets/Datasheets/ds11005.pdf",
    ratings=Ratings(limits=[VLimit(("K",), ("COM",), 30), VLimit(("COM",), ("A",), 30)],
                    pin_i_max={"A": 0.2, "K": 0.2, "COM": 0.2}),
    lifecycle="active", second_source="Nexperia BAT54S [unverified]",
    source={"pins": "Diodes DS11005 p.1 'BAT54S' top-view diagram: pin 1 anode D1, pin 2 cathode D2, pin 3 common",
            "ratings": "DS11005 p.2: VRRM 30 V, IO 200 mA, VF <= 240 mV at 0.1 mA, <= 320 mV at 1 mA"})

PTC_PI = Fuse(
    2.0, 16, "Fuse:Fuse_1812_4532Metric", ptc=True, mpn="MF-MSMF200/16X-2", manufacturer="Bourns",
    datasheet="https://www.bourns.com/docs/Product-Datasheets/mfmsmf.pdf",
    lifecycle="active", second_source="MF-MSMF260/16X-2 (2.6 A hold, same package)",
    source={"ratings": "Bourns MF-MSMF DS table: MF-MSMF200/16X Vmax 16 V, Imax 100 A, Ihold 2.00 A, Itrip 3.50 A, "
                       "Rmin 0.020, R1max 0.070 ohm (23 C); thermal derating Ihold 1.48 A at 60 C, 1.43 A at 70 C; "
                       "cUL E174545, TUV",
            "lifecycle": "Bourns MF-MSMF data sheet current; distributor status not checked [I]"}).with_(
    description="PTC resettable fuse 2.0 A hold, 3.5 A trip, 16 V, 1812 (Pi 5 V branch)")

# ---------------------------------------------------------------------------------------------
# Passives (Yageo RC0603 thick film: 0.1 W, 75 V; Yageo CC MLCC)

_RC_DS = "https://yageogroup.com/content/datasheet/asset/file/PYU-RC_GROUP_51_ROHS_L"
_CC_DS = "https://yageogroup.com/content/datasheet/asset/file/UPY-GPHC_X7R_6_3V-TO-250V"


def _r(value, mpn):
    return R(value, "0603", mpn=mpn, manufacturer="YAGEO", datasheet=_RC_DS, lifecycle="active",
             second_source="any 0603 1 % thick film, 0.1 W, 75 V",
             source={"ratings": "Yageo RC_L datasheet: 0603 0.1 W, max working voltage 75 V",
                     "lifecycle": "Digi-Key Active, Oct 2026"})


R_100 = _r("100", "RC0603FR-07100RL")
R_1K5 = _r("1.5k", "RC0603FR-071K5L")
R_4K7 = _r("4.7k", "RC0603FR-074K7L")
R_10K = _r("10k", "RC0603FR-0710KL")
R_47K = _r("47k", "RC0603FR-0747KL")
R_68K = _r("68k", "RC0603FR-0768KL")
R_100K = _r("100k", "RC0603FR-07100KL")
R_330K = _r("330k", "RC0603FR-07330KL")

C_10U = C("10u", 16, "0805", dielectric="X5R", mpn="GRM21BR61C106KE15L", manufacturer="Murata",
          datasheet="https://www.murata.com/en-us/products/productdetail?partno=GRM21BR61C106KE15L",
          lifecycle="active", second_source="YAGEO CC0805KKX5R7BB106",
          source={"ratings": "Murata GRM21BR61C106KE15L: 10 uF 16 V X5R 0805",
                  "lifecycle": "Digi-Key Active (backordered), Oct 2026"})
C_100N = C("100n", 50, "0603", dielectric="X7R", mpn="CC0603KRX7R9BB104", manufacturer="YAGEO",
           datasheet=_CC_DS, lifecycle="active", second_source="Murata GRM188R71H104KA93D [unverified]",
           source={"ratings": "Yageo CC series: 100 nF 50 V X7R 0603 (+/-10 %, X7R +/-15 % over -55..125 C)",
                   "lifecycle": "Digi-Key Active, Oct 2026"})

# ---------------------------------------------------------------------------------------------
# Mechanical: holes on the PCB; enclosure, receptacles, Pi and hardware are BOM lines, not on the board

HOLE_M3 = MountingHole("MountingHole:MountingHole_3.2mm_M3",
                       notes="NPTH 3.2 mm for an M3 x 12 mm nylon 6/6 hex standoff to the JP108P back panel")
HOLE_M25 = MountingHole("MountingHole:MountingHole_2.7mm_M2.5",
                        notes="NPTH 2.7 mm for an M2.5 x 11 mm nylon standoff under a Pi Zero 2 W hole")
TP = TestPoint()


def _mech(mpn, manufacturer, description, datasheet, source, prefix="MP", generic=False, **kw):
    return PartDef(mpn=mpn, manufacturer=manufacturer, symbol="Mechanical:Housing", footprint=None,
                   value=mpn or "generic", category="mechanical", prefix=prefix, description=description,
                   datasheet=datasheet, on_board=False, source=source, generic=generic, **kw)


_CARLON = "https://tnb.ca.abb.com/en/pdf-catalogues/boxes-and-covers-meter-sockets/enclosures/E-Enclosures-E.pdf"

PARTITION = _mech("KAE-RPMR-MP1", "custom (die-cut and folded to drawing, TBD)",
                  "Partition: 1.5 mm polycarbonate UL 94 V-0 (Lexan FR class): wall across the enclosure from the "
                  "PCB to the lid at the J1-J4 south faces, plus a flat sheet die-cut around J1-J4 covering the PCB "
                  "north of the wall; separates field wiring from the PCB/Pi",
                  "", {"ratings": "requirement from DESIGN.md H2/REQ-31 (supplementary insulation over THHN/NM "
                                  "basic insulation) [I]; material [unverified]"},
                  lifecycle="active", second_source="0.43 mm Formex GK-17 polypropylene, two layers")
ENCLOSURE = _mech("NS1086", "ABB (Carlon) Circuit Safe",
                  "Enclosure 10 x 8 x 6 in, polycarbonate, opaque screw cover, captive screws, nonmetallic "
                  "hinges/rails; UL 50 / CSA C22.2 No.94.1 Types 4X, 12, 13 (file E88685); RF-transparent",
                  _CARLON, {"ratings": "ABB/Carlon catalog 'E Enclosures' p.12-14: NS1086 10 x 8 x 6 in, kit with "
                                       "body, lid and mounting-rail kit; outside 10.40 x 8.40 x 6.49 in; back panel "
                                       "JP108 (steel) / JP108P (PVC) 8.75 x 6.88 in; 'applications where the "
                                       "ability to pass wireless signals is needed'"},
                  lifecycle="active", second_source="NS1084 (4 in deep: tighter wire bending, hotter); Hammond "
                                                    "PC series [unverified]")
BACK_PANEL = _mech("JP108P", "ABB (Carlon)", "Back panel PVC 8.75 x 6.88 in for NS108x (10-32 x 3/8 screws "
                   "ordered separately)", _CARLON, {"ratings": "catalog p.13-14 back panel table"},
                   lifecycle="active", second_source="JP108 steel panel (then bond it to the EGC)")
BOX_RECEPT = _mech("BH353A", "ABB (Carlon) Superblue",
                   "3-gang nonmetallic (PVC) device box, 53 in3, nail/screw mount, UL listed E11461",
                   "https://www.elliottelectric.com/P/Item/TAB/BH353A/",
                   {"ratings": "[S] distributor listings: three-gang new-work outlet box, 53 cu in, PVC, UL E11461"},
                   lifecycle="active", second_source="Carlon B355R (3-gang old work, 55 in3)")
RECEPTACLE = _mech("TR5252", "Legrand Pass & Seymour",
                   "Duplex receptacle NEMA 5-15R 15 A 125 V, tamper-resistant, spec grade, back and side wire, "
                   "break-off line-side tab (split circuit)",
                   "https://www.crescentelectric.com/product/825123/tr5252i-15-amp-125v-spec-grade-duplex-receptacle-"
                   "back-and-side-wire-ivory",
                   {"ratings": "[S] distributor listings (Crescent, North Coast, Electrozad): TR5252x 15 A 125 V "
                               "spec-grade TR duplex, back & side wire, break-off line-contact tab"},
                   lifecycle="active", second_source="Hubbell BR15TR [unverified]; Leviton TR 15 A spec grade")
PI = _mech("Raspberry Pi Zero 2 W", "Raspberry Pi Ltd",
           "Single-board computer 65 x 30 mm, RP3A0, 2.4 GHz Wi-Fi with PCB antenna; no header fitted",
           "https://datasheets.raspberrypi.com/rpizero2/raspberry-pi-zero-2-w-product-brief.pdf",
           {"ratings": "product brief (Apr 2024): 5 V DC 2.5 A input, -20..+70 C, 65 x 30 mm, unpopulated "
                       "40-pin header; RPi docs power table: typical bare-board 350 mA, recommended PSU 2 A; "
                       "mechanical drawing: holes 3.5 mm from edges; reduced schematic: J1 PWR IN VBUS goes "
                       "straight to the 5 V net (47 uF, no fuse) so header pins 2/4 back-feed the same rail"},
           lifecycle="active", second_source="none (the footprint is Zero-specific); production until >= 2030 "
                                             "per product brief [S]")
PI_HEADER = _mech("PRPC020DAAN-RC", "Sullins Connector Solutions",
                  "Male header 2 x 20, 2.54 mm, 2.54 mm insulator: user solders it to the Pi UNDERSIDE (pins down)",
                  "", {"ratings": "[I] Sullins PRPC series, 0.100 in pitch; mating length checked against the "
                                  "8.51 mm socket at assembly"},
                  lifecycle="active", second_source="any 2 x 20 2.54 mm male header, 2.5 mm insulator, gold")
FUSE_CLIPS = _mech("01020071Z", "Littelfuse", "Fuse clip pair for 6.3 mm (3AB) cartridge, PCB (part of F1 "
                   "footprint), 2 per F1",
                   "https://www.littelfuse.com/~/media/electronics/datasheets/fuse_clips/"
                   "littelfuse_fuse_clip_520_521_102071_datasheet.pdf.pdf",
                   {"ratings": "[S] KiCad footprint Fuseholder_Clip-6.3x32mm_Littelfuse_102071 description"},
                   lifecycle="active", second_source="Keystone 3517 class 1/4 in clips (different footprint)")
HW_PI = _mech(None, "generic", "Pi mounting kit: 4 x M2.5 x 11 mm female-female hex standoff + 8 x M2.5 x 5 mm "
              "screws, all nylon 6/6 (UL 94 V-2 or better)", "", {}, generic=True, lifecycle="active")
HW_BOARD = _mech(None, "generic", "Board mounting kit: 6 x M3 x 12 mm female-female hex standoff + 12 x M3 x 6 mm "
                 "screws, nylon 6/6; back panel drilled 3.2 mm to the board hole pattern", "", {}, generic=True,
                 lifecycle="active")
HW_FIELD = _mech(None, "generic", "Field-wiring kit: 4 x listed nonmetallic NM-B cable connectors (1/2 in); "
                 "1 x listed 5-port lever splicing connector for the EGCs (e.g. WAGO 221-415); 3 x 14/3 NM-B "
                 "with ground, ~0.5 m (E1 to E2); 3 x 6 in green EGC pigtails; 4 adhesive-free screw-on cable-tie "
                 "mounts", "", {}, generic=True, lifecycle="active")
WALLPLATE = _mech(None, "generic", "Wallplate 3-gang duplex receptacle, nylon (unbreakable), standard size", "", {},
                  generic=True, lifecycle="active")
SD_CARD = _mech(None, "generic", "microSD 16-32 GB industrial grade (pSLC or high-endurance), for a read-only "
                "root filesystem", "", {}, generic=True, lifecycle="active")
