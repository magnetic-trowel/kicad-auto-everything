# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Part cards for rpi-mains-relay: one PartDef per distinct part (see DESIGN.md section 8).

Every fact typed here cites where it was read (source=). Evidence was gathered in October 2026:
datasheets downloaded and read, lifecycle from Digi-Key search results.
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
                             v_work_rms=250, creepage_mm=8.0,
                             standard="EN 61810-1 (VDE 40007172): reinforced coil-contact, rated insulation "
                                      "voltage 250 V, PD3, OVC III; 10 kV 1.2/50 impulse")],
        t_min=-40, t_max=85),
    lifecycle="active",
    second_source="G5RL-1A-E-HR DC5 (same footprint, TV-5); G2RL-1A-E DC5 (same footprint, general use only)",
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

TERM_MAINS = Conn(
    2, "custom:WAGO_2606-3102_020-000", i_max=31, v_max=600, mpn="2606-3102/020-000", manufacturer="WAGO",
    datasheet="https://www.wago.com/2606-3102/020-000",
    lifecycle="active", second_source="none drop-in (footprint is WAGO-specific); Phoenix Contact 7.5 mm lever "
                                      "terminal [unverified]",
    notes="custom footprint from WAGO datasheet p.1 drawing: Ø2.0(+0.1) mm drill (2.1 mm finished), pad Ø3.5 mm, "
          "pole 2 pin at (+7.5, +12.5) mm from pole 1; body 17.85 x 24.0 mm; pole-1 pin 5.5 mm from its end face "
          "and 7.7 mm from the nearer long face; height 27 mm (31 mm with lever)",
    source={"ratings": "WAGO data sheet 2606-3102/020-000 v28.02.2024 p.1-3: UL 1059 (cURus E45172) use groups "
                       "B/C 600 V 31 A; solid 24-8 AWG; -60..105 C; PA66 UL94 V-0",
            "pins": "same data sheet p.1 'Dimensions in mm' (1 solder pin per pole, staggered)",
            "lifecycle": "Digi-Key 2606-3102/020-000 Active, Oct 2026"}).with_(
    description="PCB terminal block 2-pole, lever, push-in CAGE CLAMP, 6 mm2, 7.5 mm pitch, staggered pins")

# ---------------------------------------------------------------------------------------------
# SELV side

TERM_SELV = Conn(
    8, "TerminalBlock_WAGO:TerminalBlock_WAGO_2601-3108_1x08_P3.50mm_Vertical", i_max=10, v_max=300,
    mpn="2601-3108", manufacturer="WAGO",
    datasheet="https://www.wago.com/2601-3108", lifecycle="active", second_source="none drop-in",
    source={"ratings": "WAGO data sheet 2601-3108 (Digi-Key copy) p.1-2: UL 1059 use groups B/D 300 V 10 A; "
                       "solid 26-16 AWG; 2 solder pins per potential",
            "lifecycle": "Digi-Key 2946-2601-3108-ND Active, Oct 2026"}).with_(
    description="PCB terminal block 8-pole, lever, push-in, 1.5 mm2, 3.5 mm pitch (Class 2 link)")

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

DIODE_PUMP = PartDef(
    mpn="BAT54S-7-F", manufacturer="Diodes Incorporated", symbol="Diode:BAT54S",
    footprint="Package_TO_SOT_SMD:SOT-23", value="BAT54S", category="diode",
    description="Dual series Schottky 30 V 200 mA (heartbeat charge pump)",
    datasheet="https://www.diodes.com/assets/Datasheets/ds11005.pdf",
    ratings=Ratings(limits=[VLimit(("K",), ("COM",), 30), VLimit(("COM",), ("A",), 30)],
                    pin_i_max={"A": 0.2, "K": 0.2, "COM": 0.2}),
    lifecycle="active", second_source="Nexperia BAT54S [unverified]",
    source={"pins": "Diodes DS11005 p.1 'BAT54S' top-view diagram: pin 1 anode D1, pin 2 cathode D2, pin 3 common",
            "ratings": "DS11005 p.2: VRRM 30 V, IO 200 mA, VF <= 240 mV at 0.1 mA, <= 320 mV at 1 mA"})

ESD6 = PartDef(
    mpn="TPD6E05U06RVZR", manufacturer="Texas Instruments", symbol="Power_Protection:TPD6E05U06RVZ",
    footprint="Package_SON:Texas_R-PUSON-N14", value="TPD6E05U06", category="tvs",
    description="6-channel ESD protection, VBR >= 6.5 V, +/-12 kV contact",
    datasheet="https://www.ti.com/lit/ds/symlink/tpd6e05u06.pdf",
    ratings=Ratings(limits=[VLimit(("D1+", "D1-", "D2+", "D2-", "D3+", "D3-"), ("GND",), 5.5,
                                   "recommended VIO max")]),
    lifecycle="active", second_source="2 x TPD4E05U06DQA",
    source={"pins": "TI SLVSBO7O (Aug 2024) p.5 Table 4-3 (RVZ): D1+ 14, D1- 13, D2+ 12, D2- 11, D3+ 9, "
                    "D3- 8, GND 5/10, NC 1-4, 6, 7",
            "ratings": "SLVSBO7O p.6 recommended VIO 0-5.5 V; p.1 VBR >= 6.5 V, IEC 61000-4-5 2.5 A",
            "lifecycle": "Digi-Key Active, Oct 2026"})

PTC_5V = Fuse(
    1.1, 16, "Fuse:Fuse_1812_4532Metric", ptc=True, mpn="MF-MSMF110/16X-2", manufacturer="Bourns",
    datasheet="https://www.bourns.com/docs/Product-Datasheets/mfmsmf.pdf",
    lifecycle="active", second_source="MF-MSMF110/16-2",
    source={"ratings": "Bourns MF-MSMF DS p.1 table: MF-MSMF110/16X Vmax 16 V, Imax 100 A, Ihold 1.10 A, "
                       "Itrip 2.20 A, Rmin 0.06 ohm, R1max 0.20 ohm; UL E174545",
            "lifecycle": "Digi-Key Active, Oct 2026"}).with_(
    description="PTC resettable fuse 1.1 A hold, 2.2 A trip, 16 V, 1812")

# ---------------------------------------------------------------------------------------------
# Passives (Yageo RC0603 thick film: 0.1 W, 75 V; Yageo CC MLCC)

_RC_DS = "https://yageogroup.com/content/datasheet/asset/file/PYU-RC_GROUP_51_ROHS_L"
_CC_DS = "https://yageogroup.com/content/datasheet/asset/file/UPY-GPHC_X7R_6_3V-TO-250V"


def _r(value, mpn):
    return R(value, "0603", mpn=mpn, manufacturer="YAGEO", datasheet=_RC_DS, lifecycle="active",
             second_source="any 0603 1 % thick film, 0.1 W, 75 V",
             source={"ratings": "Yageo RC_L datasheet: 0603 0.1 W, max working voltage 75 V",
                     "lifecycle": "Digi-Key Active, Oct 2026"})


R_1K = _r("1k", "RC0603FR-071KL")
R_4K7 = _r("4.7k", "RC0603FR-074K7L")
R_1K5 = _r("1.5k", "RC0603FR-071K5L")
R_1M = _r("1M", "RC0603FR-071ML")

C_10U = C("10u", 16, "0805", dielectric="X5R", mpn="GRM21BR61C106KE15L", manufacturer="Murata",
          datasheet="https://www.murata.com/en-us/products/productdetail?partno=GRM21BR61C106KE15L",
          lifecycle="active", second_source="YAGEO CC0805KKX5R7BB106",
          source={"ratings": "Murata GRM21BR61C106KE15L: 10 uF 16 V X5R 0805",
                  "lifecycle": "Digi-Key Active (backordered), Oct 2026"})
C_100N = C("100n", 50, "0603", dielectric="X7R", mpn="CC0603KRX7R9BB104", manufacturer="YAGEO",
           datasheet=_CC_DS, lifecycle="active", second_source="Murata GRM188R71H104KA93D [unverified]",
           source={"ratings": "Yageo CC series: 100 nF 50 V X7R 0603", "lifecycle": "Digi-Key Active, Oct 2026"})
C_1U = C("1u", 16, "0603", dielectric="X7R", mpn="CC0603KRX7R7BB105", manufacturer="YAGEO",
         datasheet=_CC_DS, lifecycle="active",
         second_source="Murata 1 uF 16 V X7R 0603 [unverified]; Murata GRM188R71C105KA12D is obsolete",
         source={"ratings": "Yageo CC series: 1 uF 16 V X7R 0603", "lifecycle": "Digi-Key Active, Oct 2026"})

# ---------------------------------------------------------------------------------------------
# Mechanical (mounting holes on the PCB; box items are in the BOM but not on the board)

HOLE_4MM = MountingHole("MountingHole:MountingHole_4mm",
                        notes="NPTH Ø4.0 mm for an Essentra LCBS-8-19 snap-lock nylon support")
TP = TestPoint()


def _mech(mpn, manufacturer, description, datasheet, source, prefix="MP", **kw):
    return PartDef(mpn=mpn, manufacturer=manufacturer, symbol="Mechanical:Housing", footprint=None,
                   value=mpn, category="mechanical", prefix=prefix, description=description,
                   datasheet=datasheet, on_board=False, source=source, **kw)


SELV_COVER = _mech("KAE-RPMR-MP1", "custom (die-cut to drawing, TBD)",
                   "Insulating cover over the SELV band, 0.43 mm polypropylene UL 94 V-0 (Formex GK-17 class), "
                   "height >= 20 mm, opening for J6 wire entry", "",
                   {"ratings": "requirement from DESIGN.md H2 / NEC 725.136(B) barrier [I]; material [unverified]"},
                   lifecycle="active", second_source="0.8 mm polycarbonate UL 94 V-0")
BOX = _mech("RACO 257", "Hubbell RACO", "Steel box 4-11/16 in square x 2-1/8 in deep, welded, 42.0 in3, "
            "raised ground (#10-32), UL listed", "https://hubbellcdn.com/specsheet/RACO-257-SPEC-EN.pdf",
            {"ratings": "RACO 257 spec sheet and sales drawing RTB_257_CUSTDWG_EN: 42 in3, 119.1 x 118.3 mm "
                        "outside, 54 mm inside depth, #10-32 tap 2.75 in / 1.19 in from the edges"},
            lifecycle="active", second_source="any listed 4-11/16 x 2-1/8 in steel box")
RING = _mech("RACO 250", "Hubbell RACO", "Extension ring 4-11/16 in square x 1-1/2 in, 29.5 in3, cULus",
             "https://hubbellcdn.com/specsheet/RACO-250-SPEC-EN.pdf",
             {"ratings": "RACO 250 spec sheet: 29.5 cu in, actual depth 1.563 in, cULus listed"},
             lifecycle="active", second_source="any listed 4-11/16 x 1-1/2 in extension ring")
COVER = _mech("RACO 832", "Hubbell RACO", "Flat blank cover 4-11/16 in square, steel, cULus",
              "https://hubbellcdn.com/specsheet/RACO-832-SPEC-EN.pdf",
              {"ratings": "RACO 832 spec sheet: 0.063 x 4.688 x 4.688 in, cULus listed"},
              lifecycle="active", second_source="any listed 4-11/16 in flat blank cover")
SUPPORT = _mech("LCBS-8-19", "Essentra Components (Richco)",
                "Snap-lock board support, nylon 6/6 UL 94 V-0, 12.7 mm, PCB hole 4.0 mm, chassis hole 4.75 mm "
                "in 0.79-1.98 mm panel",
                "https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/7134/lcbs.pdf",
                {"ratings": "Richco/Essentra drawing LCBS (rev F): -19 = nylon 6/6 UL 94 V-0, dim A 1/2 in "
                            "[12.7 mm], snap-lock in .156 in hole in .062 in board, .187 in hole in "
                            ".031-.078 in panel"},
                lifecycle="active", second_source="LCBS-8-01 (UL 94 V-2)")
