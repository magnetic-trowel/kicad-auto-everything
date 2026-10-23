# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Part cards for liion-balancer: one PartDef per distinct part (DESIGN.md section 8).

Every fact typed here says where it was read (source=). Datasheets were downloaded and read in
October 2026; lifecycle is from Digi-Key/LCSC listings of the same month unless noted.
Evidence tags as in DESIGN.md: [P] primary source read, [S] secondary, [I] our inference.
"""
from kaesynth import Isolation, PartDef, PinDef, Ratings, VLimit
from kaesynth.lib import IC, LED, C, Conn, D, Fuse, MountingHole, R, TestPoint, Thermistor

LT8584_DS = "https://www.analog.com/media/en/technical-documentation/data-sheets/8584fb.pdf"
ADBMS_DS = "https://www.analog.com/media/en/technical-documentation/data-sheets/adbms1818.pdf"
YAGEO_RC = "https://www.yageo.com/upload/media/product/productsearch/datasheet/rchip/PYu-RC_Group_51_RoHS_L_12.pdf"
MURATA = "https://www.murata.com/en-global/products/productdetail?partno="
SRC_R = {"lifecycle": "Yageo RC_L series, Active (Digi-Key, Oct 2026) [S]"}

# =============================================================================================
# Balancing channel (block chK)

LT8584 = IC(
    "LT8584EFE#PBF",
    pins=[
        # all pins on the left/right sides: the generator draws top/bottom pin names over side pins
        PinDef(9, "VIN", "power_in", "left"), PinDef(10, "VCELL", "input", "left"),
        PinDef(11, "VSNS", "input", "left"), PinDef(5, "MODE", "input", "left"),
        PinDef(6, "RTMR", "passive", "left"),
        PinDef(1, "GND", "power_in", "left"), PinDef(2, "GND", "power_in", "left"),
        PinDef(3, "GND", "power_in", "left"), PinDef(4, "GND", "power_in", "left"),
        PinDef(17, "GND", "power_in", "left"),
        PinDef(13, "SW", "passive", "right"), PinDef(14, "SW", "passive", "right"),
        PinDef(15, "SW", "passive", "right"), PinDef(16, "SW", "passive", "right"),
        PinDef(8, "OUT", "output", "right"), PinDef(7, "DIN", "input", "right"),
        PinDef(12, "DCHRG", "input", "right"),
    ],
    footprint="Package_SO:TSSOP-16-1EP_4.4x5mm_P0.65mm", manufacturer="Analog Devices",
    description="Monolithic isolated-flyback active cell balancer, 2.5 A discharge, simple mode",
    datasheet=LT8584_DS,
    ratings=Ratings(
        limits=[VLimit(("DIN",), ("GND",), 10, "DIN to GND +/-10 V"),
                VLimit(("VIN", "VCELL", "VSNS", "MODE", "OUT", "DCHRG"), ("GND",), 9, "-0.3 to 9 V"),
                VLimit(("SW",), ("GND",), 50, "-0.4 to 50 V incl. leakage spike; <= 40 VDC (Note 3)"),
                VLimit(("VIN",), ("VCELL", "VSNS"), 0.2, "VIN - VCELL, VIN - VSNS +/-200 mV"),
                VLimit(("MODE",), ("VIN",), 0.2, "MODE - VIN 200 mV")],
        t_min=-40, t_max=125),
    lifecycle="active", second_source="none (single source; LTC3300-1 is the architectural fallback, Q-10)",
    source={"pins": "LT8584 Rev B (8584fb) p.2 pin configuration (FE16, EP = pin 17 = GND, must be soldered) "
                    "and p.9 Pin Functions",
            "ratings": "LT8584 Rev B p.2 Absolute Maximum Ratings: DIN +/-10 V; VIN/VCELL/VSNS/MODE/OUT/DCHRG "
                       "-0.3..9 V; SW -0.4..50 V with Note 3 '<= 40 VDC'; VIN-VCELL, VIN-VSNS +/-200 mV; MODE-VIN "
                       "200 mV; RTMR: no source (Note 2); LT8584E TJ -40..125 C",
            "lifecycle": "Digi-Key LT8584EFE#PBF Active, $9.58 (Oct 2026)"})

NA5743 = IC(
    "NA5743-ALD",
    pins=[PinDef(1, "PRI_A", "passive", "left"), PinDef(2, "PRI_B", "passive", "left"),
          PinDef(3, "PRI_A_END", "passive", "left"), PinDef(4, "PRI_B_END", "passive", "left"),
          PinDef(8, "SEC_DOT", "passive", "right"), PinDef(5, "SEC_END", "passive", "right"),
          PinDef(6, "NC6", "passive", "right"), PinDef(7, "NC7", "passive", "right")],
    footprint="custom:Coilcraft_NA5743_2x4_P2.50mm", manufacturer="Coilcraft", category="transformer",
    description="Flyback transformer for LT8584, 4 uH primary (2 windings in parallel), 1:4, Ipk 7 A, 1500 Vrms",
    datasheet="https://www.coilcraft.com/pdfs/na5743.pdf",
    ratings=Ratings(
        i_max=7.0,
        isolation=[Isolation(("1", "2", "3", "4"), ("5", "8"), v_iso_rms=1500, grade="functional",
                             standard="Coilcraft Doc 1075: 1500 Vrms, one minute, primary to secondary")],
        t_min=-40, t_max=125),
    lifecycle="active",
    second_source="Wurth 750314018 (LT8584 Rev B Table 3 p.20 [P]; availability unverified)",
    notes="custom footprint from Doc 1075 recommended land pattern: 2 rows x 4 pads 2.03 x 1.27 mm, 2.50 mm "
          "pitch, rows 11.68 mm apart (check edge vs centre on the drawing); body 15.24 x 12.7 x 11.4 mm",
    source={"pins": "Coilcraft Doc 1075 (04/27/22) p.1 schematic: primary windings 1-3 and 2-4 (dots at 1 and 2, "
                    "paralleled on the PCB), secondary 5-8 (dot at 8); pins 6, 7 have pads only",
            "ratings": "Doc 1075 p.1 table: NA5743-AL input 2-8 V, L 4.0 uH +/-10 %, Ipk 7.0 A, DCR 0.012/0.500 "
                       "ohm, Llk <= 0.116 uH, 1:4, output 30-80 V; rated 7-12 W at 140 kHz; 1500 Vrms 1 min; "
                       "ambient -40..125 C, part <= 165 C",
            "lifecycle": "Coilcraft catalog listing, Farnell stock (Oct 2026) [S]"})

ES1G = D("ES1G-13-F", "Diode_SMD:D_SMA", 400, 1.0, manufacturer="Diodes Incorporated",
         datasheet="https://www.diodes.com/assets/Datasheets/ds14001.pdf",
         lifecycle="active", second_source="Vishay ES1G-E3/61T",
         source={"ratings": "Diodes DS14001 Rev 17-2 p.1 Maximum Ratings: ES1G VRRM 400 V, IO 1.0 A, IFSM 30 A "
                            "(8.3 ms), trr 25 ns, IR 5 uA",
                 "pins": "DS14001 p.1 'Polarity: cathode band'; Device:D pin 1 = K, D_SMA pad 1 = cathode",
                 "lifecycle": "LCSC C674398 / Digi-Key Active (Oct 2026) [S]"}).with_(
    description="Super-fast rectifier 400 V 1 A, 25 ns, SMA")

TVS_CELL = D("SMA6T6V7AY", "Diode_SMD:D_SMA", 5.0, 0, kind="D_TVS", manufacturer="STMicroelectronics",
             datasheet="https://www.st.com/resource/en/datasheet/sma6t.pdf",
             lifecycle="active", second_source="Littelfuse SMAJ6.0A (6.0 V standoff)",
             source={"ratings": "LT8584 Rev B p.26 Table 5 (ADI's recommended cell TVS): SMA6T6V7AY IR 20 uA at "
                                "5 V, VC 9.1 V at 68 A, SMA; 600 W class. ST's own datasheet was not readable "
                                "here [S]",
                     "pins": "unidirectional, cathode band = pad 1 (Device:D_Zener pin 1 = K) [S]",
                     "lifecycle": "Digi-Key SMA6T6V7AY Active (Oct 2026)"}).with_(
    description="TVS unidirectional 600 W, 5 V standoff, AEC-Q101 (cell input clamp)")
TVS_CELL.ratings.i_max = None

C_100U = C("100u", 6.3, "1210", dielectric="X6S", mpn="GRM32EC80J107ME20L", manufacturer="Murata",
           datasheet=MURATA + "GRM32EC80J107ME20%23", lifecycle="active",
           second_source="TDK C3225X6S0J107M250AC [unverified]",
           fields={"Ceff": "about 35-45 uF at 4.2 V [I]; two per channel (CVCELL + CTRAN), ADI uses 6.3 V "
                           "100 uF X5R/X7R here (LT8584 p.22, p.32 parts list)", "Temp": "-55..105 C"},
           source={"ratings": "Murata GRM32EC80J107ME20L: 100 uF +/-20 % 6.3 V X6S (-55..105 C), 1210 [S]; "
                              "chosen over the 10 V X5R (85 C) part for REQ-21 temperature margin (calc "
                              "ctran_temp_margin_C)",
                   "lifecycle": "Future Electronics / Murata listing, Oct 2026 [S]"})
C_1U = C("1u", 10, "0603", mpn="GRM188R71A105KA61D", manufacturer="Murata",
         datasheet=MURATA + "GRM188R71A105KA61%23", lifecycle="active", second_source="Samsung CL10B105KP8NNNC",
         source={"lifecycle": "Murata listing, Oct 2026 [S]"})
C_1U_16V = C("1u", 16, "0603", mpn="GRM188R71C105KA12D", manufacturer="Murata",
             datasheet=MURATA + "GRM188R71C105KA12%23", lifecycle="active", second_source="Samsung CL10B105KO8NNNC",
             source={"lifecycle": "Murata listing [S]; 16 V part on the 5 V rail keeps DC bias < 50 %"})
C_47N = C("47n", 50, "0603", mpn="GRM188R71H473KA61D", manufacturer="Murata",
          datasheet=MURATA + "GRM188R71H473KA61%23", lifecycle="active", second_source="any 50 V X7R 0603",
          source={"lifecycle": "Murata listing [S]"})
C_22N_100V = C("22n", 100, "0603", mpn="GCM188R72A223KA37D", manufacturer="Murata",
               datasheet=MURATA + "GCM188R72A223KA37%23", lifecycle="active",
               second_source="TDK CGA3E2X7R2A223K080AA", source={"lifecycle": "Murata listing [S]"})
C_2U2_100V = C("2.2u", 100, "1210", mpn="C1210C225K1RACTU", manufacturer="KEMET",
               datasheet="https://search.kemet.com/component-documentation/download/specsheet/C1210C225K1RACTU",
               lifecycle="active", second_source="Taiyo Yuden HMK325B7225KN-T",
               fields={"Ceff": "about 1.0 uF at 60-68 V [I] (X7R 100 V 1210); C-15 needs >= 1.5 uF total on "
                               "FLYBUS (16 in parallel); C8 needs >= 1 uF for 19 mV ripple"},
               source={"ratings": "KEMET C1210C225K1RACTU 2.2 uF 10 % 100 V X7R 1210 [P]; GRM32ER72A225KA35L is "
                                  "NRND (Digi-Key, Oct 2026)",
                       "lifecycle": "Digi-Key Active, Oct 2026"})
R_4K99_2010 = R("4.99k", "2010", p_max=0.5, mpn="RC2010FK-074K99L", manufacturer="Yageo", datasheet=YAGEO_RC,
                lifecycle="active", second_source="Vishay CRCW20104K99FKEF",
                source={**SRC_R, "ratings": "0.5 W used (conservative; RC2010 is rated 3/4 W [S]); 200 V"})
R_33K = R("33k", mpn="RC0603FR-0733KL", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
          second_source="any 1 % 0603", source=SRC_R)
R_10K = R("10k", mpn="RC0603FR-0710KL", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
          second_source="any 1 % 0603", source=SRC_R)

TLP293 = PartDef(
    mpn="TLP293(GB-TPL,E", manufacturer="Toshiba", symbol="Isolator:TLP293",
    footprint="Package_SO:SOIC-4_4.55x2.6mm_P1.27mm", value="TLP293(GB)", category="opto", prefix="U",
    description="Phototransistor optocoupler, CTR 100-600 % (GB), 80 V, 3750 Vrms, SO4",
    datasheet="https://toshiba.semicon-storage.com/info/TLP293_datasheet_en_20191129.pdf",
    pin_names={"1": "A", "2": "K", "3": "E", "4": "C"},
    ratings=Ratings(
        limits=[VLimit(("A",), ("K",), 5, "LED reverse voltage VR 5 V"),
                VLimit(("C",), ("E",), 7, "VECO 7 V (reverse); VCEO 80 V forward - the 7 V bound covers both")],
        pin_i_max={"A": 0.05, "K": 0.05, "C": 0.05, "E": 0.05},
        isolation=[Isolation(("A", "K"), ("C", "E"), v_iso_rms=3750, grade="basic", creepage_mm=5.0,
                             standard="Toshiba TLP293 2019-11-29: BVS 3750 Vrms 60 s; creepage/clearance 5.0 mm")],
        t_min=-55, t_max=125),
    lifecycle="active", second_source="Lite-On LTV-357T",
    source={"pin_names": "TLP293 datasheet 2019-11-29 p.1 section 4 'Packaging and Pin Assignment': 1 anode, "
                         "2 cathode, 3 emitter, 4 collector (KiCad Isolator:TLP293 pins are unnamed)",
            "ratings": "TLP293 2019-11-29 p.2 Absolute Maximum Ratings: IF 50 mA, VR 5 V, VCEO 80 V, VECO 7 V, IC 50 "
                       "mA, BVS 3750 Vrms; p.1 creepage/clearance 5.0 mm; Topr -55..125 C",
            "lifecycle": "Digi-Key TLP293(GB-TPL,E Active (Oct 2026)"})

# =============================================================================================
# Tap entry (blocks tapin, tapT)

J_TAPS = Conn(
    17, "custom:PhoenixContact_MSTBA_2,5_17-G-5,08_1x17_P5.08mm_Horizontal", i_max=12, v_max=320,
    mpn="1757394", manufacturer="Phoenix Contact",
    datasheet="https://www.phoenixcontact.com/en-us/products/pcb-header-mstba-25-17-g-508-1757394",
    lifecycle="active", second_source="Wurth 5.08 mm pluggable header, 17 positions [unverified]",
    notes="footprint: KiCad PhoenixContact_MSTBA_2,5_16-G-5,08 extended by one position at 5.08 mm",
    source={"ratings": "Phoenix MSTBA 2,5/17-G-5,08 (1757394): 12 A, 320 V (IEC, III/2) [S, distributor "
                       "listing; phoenixcontact.com returned 403]",
            "lifecycle": "RS / Automa listings Active, Oct 2026 [S]"}).with_(
    description="Pluggable header 17-pos 5.08 mm, plug MSTB 2,5/17-ST-5,08 (1757161); EBP 2-5 bridges for N < 16")

F_TAP = Fuse(
    5, 125, "Fuse:Fuseholder_Littelfuse_Nano2_154x", mpn="0154005.DR", manufacturer="Littelfuse",
    i2t=5.566, breaking_a=50,
    datasheet="https://www.littelfuse.com/assetdocs/littelfuse-fuse-451-453-datasheet",
    lifecycle="active", second_source="0451005.MRL soldered (same fuse, not replaceable)",
    fields={"Breaking_32VDC": "300 A", "R_cold": "12.5 mOhm"},
    source={"ratings": "Littelfuse 451/453 Nano2 datasheet (2010) p.1-2: 0451005 5 A very fast, 125 V; "
                       "interrupting 50 A at 125 VAC/VDC, 300 A at 32 VDC; cold R 0.0125 ohm; nominal melting "
                       "I2t 5.566 A2s. OMNI-BLOK 154 holder from a Farnell listing [S]",
            "lifecycle": "LCSC C48467 / Digi-Key Active, Oct 2026 [S]"})
R_100 = R("100", mpn="RC0603FR-07100RL", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
          second_source="any 1 % 0603", source=SRC_R)
C_10N = C("10n", 50, "0603", mpn="GRM188R71H103KA01D", manufacturer="Murata",
          datasheet=MURATA + "GRM188R71H103KA01%23", lifecycle="active", second_source="any 50 V X7R 0603",
          source={"lifecycle": "Murata listing [S]"})
NETTIE = PartDef(
    symbol="Device:NetTie_2", footprint="NetTie:NetTie-2_SMD_Pad0.5mm", value="NetTie", category="other",
    prefix="NT", generic=True, in_bom=False,
    description="Net tie: battery return TAP0 joins controller ground GND_B at one point (pad F100.2)")

# =============================================================================================
# Cell monitor (block afe)

_ADBMS_PINS = [PinDef(1, "V+", "power_in", "left", unit=2)]
# unit 1: cell inputs (C) on the left, balance outputs (S) on the right, top cell first
for n in range(18, -1, -1):
    _ADBMS_PINS.append(PinDef(38 - 2 * n, f"C{n}", "input", "left", unit=1))
for n in range(18, 0, -1):
    _ADBMS_PINS.append(PinDef(39 - 2 * n, f"S{n}", "output", "right", unit=1))
_ADBMS_PINS += [
    PinDef(39, "GPIO1", "bidirectional", "right", unit=2), PinDef(40, "GPIO2", "bidirectional", "right", unit=2),
    PinDef(41, "GPIO3", "bidirectional", "right", unit=2), PinDef(42, "GPIO4", "bidirectional", "right", unit=2),
    PinDef(43, "GPIO5", "bidirectional", "right", unit=2), PinDef(44, "GPIO6", "bidirectional", "right", unit=2),
    PinDef(45, "GPIO7", "bidirectional", "right", unit=2), PinDef(46, "GPIO8", "bidirectional", "right", unit=2),
    PinDef(47, "GPIO9", "bidirectional", "right", unit=2),
    PinDef(48, "VREG", "power_in", "left", unit=2), PinDef(49, "DRIVE", "output", "left", unit=2),
    PinDef(50, "VREF2", "power_out", "left", unit=2), PinDef(51, "VREF1", "power_out", "left", unit=2),
    PinDef(52, "DTEN", "input", "left", unit=2),
    PinDef(53, "SDI", "input", "right", unit=2), PinDef(54, "SDO", "open_collector", "right", unit=2),
    PinDef(55, "ISOMD", "input", "left", unit=2), PinDef(56, "WDT", "open_collector", "right", unit=2),
    PinDef(57, "IBIAS", "passive", "right", unit=2), PinDef(58, "ICMP", "input", "right", unit=2),
    PinDef(59, "V-", "power_in", "left", unit=2), PinDef(60, "V-", "power_in", "left", unit=2),
    PinDef(61, "CSB", "input", "right", unit=2), PinDef(62, "SCK", "input", "right", unit=2),
    PinDef(63, "IMB", "bidirectional", "right", unit=2), PinDef(64, "IPB", "bidirectional", "right", unit=2),
    PinDef(65, "V-", "power_in", "left", unit=2),
]
_adbms_limits = [VLimit(("V+",), ("V-",), 112.5, "V+ to V- 112.5 V"),
                 VLimit(("V+",), ("C12",), 50, "V+ to C12 50 V"),
                 VLimit(("C0",), ("V-",), 6, "C0 -0.3..6 V"),
                 VLimit(("IPB", "IMB"), ("V-",), 6, "-0.3 V..VREG + 0.3 V, <= 6 V"),
                 VLimit(("DRIVE",), ("V-",), 7, "DRIVE -0.3..7 V"),
                 VLimit(("VREG",), ("V-",), 6, "VREG -0.3..6 V (all other pins)"),
                 VLimit(("VREF1", "VREF2", "GPIO1", "GPIO2", "GPIO3", "GPIO4", "GPIO5", "GPIO6", "GPIO7",
                         "GPIO8", "GPIO9", "DTEN", "SDI", "SDO", "ISOMD", "WDT", "IBIAS", "ICMP", "CSB", "SCK"),
                        ("V-",), 6, "all other pins -0.3..6 V")]
for n in range(1, 19):
    _adbms_limits.append(VLimit((f"C{n}", f"S{n}"), ("V-",), min(8 * n, 112.5), f"C{n}, S{n}: MIN(8 x {n}, 112.5 V)"))
    _adbms_limits.append(VLimit((f"C{n}", f"S{n}"), (f"C{n - 1}",), 8, f"C{n}/S{n} to C{n - 1}: -0.3..8 V"))
for hi, lo in ((18, 15), (15, 12), (12, 9), (9, 6), (6, 3), (3, 0)):
    _adbms_limits.append(VLimit((f"C{hi}",), (f"C{lo}",), 21, f"C{hi} to C{lo}: -0.3..21 V"))

ADBMS1818 = IC(
    "ADBMS1818ASWZ", pins=_ADBMS_PINS, manufacturer="Analog Devices",
    footprint="Package_QFP:LQFP-64-1EP_10x10mm_P0.5mm_EP5x5mm_ThermalVias",
    description="18-cell battery monitor, 16-bit, TME 3-4.8 mV, isoSPI/SPI, S-pin balance outputs, 2 s watchdog",
    datasheet=ADBMS_DS,
    ratings=Ratings(limits=_adbms_limits, t_min=-40, t_max=85),
    lifecycle="active", second_source="LTC6813-1 (pin-identical: LTC6813-1 Rev B p.3 [P])",
    notes="EP land: ADI Fig. 113 shows a 5.74 mm exposed pad; the library land is 5 x 5 mm - review at layout",
    source={"pins": "ADBMS1818 Rev A p.12 Figure 3 (pin configuration) and p.12-13 Table 14 (pin functions); "
                    "identical to LTC6813-1 Rev B p.3",
            "ratings": "ADBMS1818 Rev A p.11 Table 11 Absolute Maximum Ratings: V+ to V- 112.5 V; V+ to C12 50 V; "
                       "C0 -0.3..6 V; C(n), S(n) -0.3..MIN(8n, 112.5) V; IPx/IMx -0.3..VREG+0.3 <= 6 V; DRIVE "
                       "7 V; others 6 V; C(n)-C(n-1), S(n)-C(n-1) -0.3..8 V; C18-C15 ... C3-C0 21 V; specified "
                       "TJ -40..85 C",
            "lifecycle": "Digi-Key ADBMS1818ASWZ Active, 52-week lead time (Oct 2026)"})

R_100_0805 = R("100", "0805", mpn="RC0805FR-07100RL", manufacturer="Yageo", datasheet=YAGEO_RC,
               lifecycle="active", second_source="any 1 % 0805", source=SRC_R)
C_100N_100V = C("100n", 100, "0603", mpn="GRM188R72A104KA35D", manufacturer="Murata",
                datasheet=MURATA + "GRM188R72A104KA35%23", lifecycle="active",
                second_source="TDK CGA3E3X7S2A104K080AB", source={"lifecycle": "Murata listing [S]"})
R_20K = R("20k", mpn="RC0603FR-0720KL", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
          second_source="any 1 % 0603", source=SRC_R)
R_4K99 = R("4.99k", mpn="RC0603FR-074K99L", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
           second_source="any 1 % 0603", source=SRC_R)
R_1M = R("1M", mpn="RC0603FR-071ML", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
         second_source="any 1 % 0603", source=SRC_R)
R_10K_01 = R("10.0k", tol="0.1%", mpn="RT0603BRD0710KL", manufacturer="Yageo",
             datasheet="https://www.yageo.com/upload/media/product/productsearch/datasheet/rchip/PYu-RT_1-to-0.01_RoHS_L_15.pdf",
             lifecycle="active", second_source="Vishay TNPW060310K0BEEA", source=SRC_R)
NTC_10K = Thermistor(
    "10k", mpn="NCP18XH103F03RB", manufacturer="Murata",
    datasheet="https://www.murata.com/en-global/products/productdetail?partno=NCP18XH103F03RB",
    lifecycle="active", second_source="TDK NTCG163JF103FT1",
    ratings=Ratings(p_max=0.1, t_min=-40, t_max=125),
    source={"ratings": "Murata NTC catalog (NCP18 series): 10 kohm +/-1 % at 25 C, B25/50 3380 K, B25/85 3434 K, "
                       "rated power 100 mW, -40..125 C [P]",
            "lifecycle": "LCSC C77131 Active [S]"}).with_(description="NTC thermistor 10 k 1 % B3380, 0603")
C_100N = C("100n", 50, "0603", mpn="GRM188R71H104KA93D", manufacturer="Murata",
           datasheet=MURATA + "GRM188R71H104KA93%23", lifecycle="active", second_source="any 50 V X7R 0603",
           source={"lifecycle": "Murata listing [S]"})

# =============================================================================================
# Stack return (block ret)

V8P10 = PartDef(
    mpn="V8P10-M3/86A", manufacturer="Vishay General Semiconductor", symbol="Device:D_Schottky_AAK",
    footprint="Package_TO_SOT_SMD:TO-277A", value="V8P10", category="diode",
    description="TMBS Schottky 100 V 8 A, TO-277A (SMPC): common stack-return blocking diode",
    datasheet="https://www.vishay.com/docs/89005/v8p10.pdf",
    ratings=Ratings(v_max=100, i_max=8.0, polarity=None, t_min=-40, t_max=150),
    lifecycle="active", second_source="Vishay V8PM10",
    source={"ratings": "Vishay doc 89005 (18-Dec-2019) p.1: VRRM 100 V, IF(AV) 8.0 A, IFSM 150 A, TJ max 150 C",
            "pins": "doc 89005 p.1 package drawing: pins 1, 2 = anode, tab = cathode; KiCad Device:D_Schottky_AAK "
                    "pins 1, 2 = A, 3 = K and TO-277A pad 3 = tab",
            "lifecycle": "Digi-Key Active, Oct 2026 [S]"})
SMBJ70A = D("SMBJ70A", "Diode_SMD:D_SMB", 70, 0, kind="D_TVS", manufacturer="Littelfuse",
            datasheet="https://www.littelfuse.com/assetdocs/littelfuse-tvs-diode-smbj-datasheet",
            lifecycle="active", second_source="Vishay SMBJ70A-E3/52",
            source={"ratings": "Littelfuse SMBJ series rev JC.07/04/25 v4 p.2 table: SMBJ70A VR 70 V, VBR 77.8-86.0 "
                               "V at 1 mA, IR 1 uA, VC 113 V at IPP 5.3 A; 600 W 10/1000 us (p.1)",
                    "pins": "SMBJ datasheet p.1 marking: cathode band (unidirectional); Device:D_Zener pin 1 = K",
                    "lifecycle": "LCSC C224025 Active [S]"}).with_(
    description="TVS unidirectional 600 W, VR 70 V: FLYBUS clamp if the stack return opens")
SMBJ70A.ratings.i_max = None
R_2M_1206 = R("2.0M", "1206", mpn="RC1206FR-072ML", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
              second_source="any 1 % 1206 200 V", source=SRC_R)

# =============================================================================================
# Supply (block psu)

F_SUPPLY = Fuse(0.125, 125, "Fuse:Fuse_Littelfuse-NANO2-451_453", mpn="0451.125MRL", manufacturer="Littelfuse",
                breaking_a=50, datasheet="https://www.littelfuse.com/assetdocs/littelfuse-fuse-451-453-datasheet",
                lifecycle="active", second_source="Bel Fuse 0685P0125-01",
                source={"ratings": "Littelfuse 451/453 datasheet p.1-2: 0451.125 125 mA very fast, 125 V, "
                                   "interrupting 50 A at 125 V, cold R about 1.7 ohm",
                        "lifecycle": "Digi-Key Active [S]"})
R_100_2512 = R("100", "2512", mpn="RC2512FK-07100RL", manufacturer="Yageo", datasheet=YAGEO_RC,
               lifecycle="active", second_source="Vishay CRCW2512100RFKEG", source=SRC_R)
LM5164 = PartDef(
    mpn="LM5164DDAR", manufacturer="Texas Instruments", symbol="Regulator_Switching:LM5164DDA",
    footprint="Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm_ThermalVias", value="LM5164",
    category="ic", description="100 V 1 A synchronous COT buck, IQ 10.5 uA, SO-8 PowerPAD",
    datasheet="https://www.ti.com/lit/ds/symlink/lm5164.pdf",
    ratings=Ratings(limits=[VLimit(("VIN",), ("GND", "EP"), 100, "VIN to GND -0.3..100 V"),
                            VLimit(("EN/UVLO",), ("GND", "EP"), 100, "EN to GND -0.3..100 V"),
                            VLimit(("FB",), ("GND", "EP"), 5.5, "FB to GND -0.3..5.5 V"),
                            VLimit(("BST",), ("GND", "EP"), 105.5, "BST to GND -0.3..105.5 V"),
                            VLimit(("BST",), ("SW",), 5.5, "BST to SW -0.3..5.5 V"),
                            VLimit(("SW",), ("GND", "EP"), 100, "SW to GND -1.5..100 V"),
                            VLimit(("PGOOD",), ("GND", "EP"), 14, "PGOOD to GND -0.3..14 V")],
                    t_min=-40, t_max=150),
    lifecycle="active", second_source="TI LM5163 (0.5 A, same pinout)",
    notes="RON (pin 4) has a 5.5 V abs max; it sees only R12 to GND, no external source, so no limit is "
          "checked on it",
    source={"ratings": "TI SNVSAU4D p.4 section 5.1 Absolute Maximum Ratings: VIN, EN 100 V; FB, RON 5.5 V; BST "
                       "105.5 V; BST-SW 5.5 V; SW -1.5..100 V; PGOOD 14 V; BST cap 1.5-2.5 nF (2.2 nF 50 V X7R "
                       "required, section 6.3.2)",
            "pins": "SNVSAU4D p.3 Table 4-1 Pin Functions = KiCad Regulator_Switching:LM5164DDA",
            "lifecycle": "TI.com Active (Oct 2026) [S]"})
R_4M7_1206 = R("4.7M", "1206", mpn="RC1206FR-074M7L", manufacturer="Yageo", datasheet=YAGEO_RC,
               lifecycle="active", second_source="any 1 % 1206 200 V", source=SRC_R)
R_300K = R("300k", mpn="RC0603FR-07300KL", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
           second_source="any 1 % 0603", source=SRC_R)
R_49K9 = R("49.9k", mpn="RC0603FR-0749K9L", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
           second_source="any 1 % 0603", source=SRC_R)
C_2N2 = C("2.2n", 50, "0603", mpn="GRM188R71H222KA01D", manufacturer="Murata",
          datasheet=MURATA + "GRM188R71H222KA01%23", lifecycle="active", second_source="any 50 V X7R 0603",
          source={"lifecycle": "Murata listing [S]; LM5164 requires 2.2 nF 50 V X7R (SNVSAU4D 6.3.2)"})
L_47U = PartDef(
    mpn="MSS1048-473MLB", manufacturer="Coilcraft", symbol="Device:L",
    footprint="Inductor_SMD:L_Coilcraft_MSS1048-XXX", value="47u", category="inductor",
    description="Shielded power inductor 47 uH 20 %, Isat 1.44 A (10 % drop)",
    datasheet="https://www.coilcraft.com/pdfs/mss1048.pdf",
    ratings=Ratings(i_max=1.44, t_min=-40, t_max=125),
    lifecycle="active", second_source="Bourns SRR1050A-470M",
    source={"ratings": "Coilcraft Doc 462 MSS1048 table: -473ML 47 uH, Isat 1.44 A (10 %) / 2.2 A (30 %); "
                       "-40..125 C ambient [P]; i_max uses the 10 % Isat (the LM5164 limit of 1.75 A only "
                       "applies in a fault)",
            "lifecycle": "Coilcraft listing Active [S]"})
C_22U = C("22u", 10, "1210", mpn="GRM32ER71A226KE20L", manufacturer="Murata",
          datasheet=MURATA + "GRM32ER71A226KE20%23", lifecycle="active", second_source="TDK C3225X7R1A226K230AB",
          fields={"Ceff": "about 14 uF at 5 V [I]: 14 mV ripple at 250 kHz (C-13)"},
          source={"lifecycle": "Murata listing [S]"})
R_316K = R("316k", mpn="RC0603FR-07316KL", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
           second_source="any 1 % 0603", source=SRC_R)
R_100K = R("100k", mpn="RC0603FR-07100KL", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
           second_source="any 1 % 0603", source=SRC_R)
R_470K_1206 = R("470k", "1206", mpn="RC1206FR-07470KL", manufacturer="Yageo", datasheet=YAGEO_RC,
                lifecycle="active", second_source="any 1 % 1206", source=SRC_R)
C_1N_C0G = C("1n", 50, "0603", dielectric="C0G", mpn="GRM1885C1H102JA01D", manufacturer="Murata",
             datasheet=MURATA + "GRM1885C1H102JA01%23", lifecycle="active", second_source="any 50 V C0G 0603",
             source={"lifecycle": "Murata listing [S]"})
C_220P_C0G = C("220p", 50, "0603", dielectric="C0G", mpn="GRM1885C1H221JA01D", manufacturer="Murata",
               datasheet=MURATA + "GRM1885C1H221JA01%23", lifecycle="active", second_source="any 50 V C0G 0603",
               source={"lifecycle": "Murata listing [S]"})
MCP1700 = PartDef(
    mpn="MCP1700T-3302E/TT", manufacturer="Microchip", symbol="Regulator_Linear:MCP1700x-330xxTT",
    footprint="Package_TO_SOT_SMD:SOT-23", value="MCP1700-3.3", category="ic",
    description="LDO 3.3 V 250 mA, IQ 1.6 uA, SOT-23",
    datasheet="https://ww1.microchip.com/downloads/en/DeviceDoc/MCP1700-Low-Quiescent-Current-LDO-20001826E.pdf",
    ratings=Ratings(limits=[VLimit(("VI",), ("GND",), 6.5, "VDD abs max +6.5 V"),
                            VLimit(("VO",), ("GND",), 6.5, "outputs VSS-0.3..VIN+0.3")],
                    t_min=-40, t_max=125),
    lifecycle="active", second_source="TI TPS7A0233DBVR",
    source={"ratings": "Microchip DS20001826E p.3 Absolute Maximum Ratings: VDD +6.5 V, I/O VSS-0.3..VIN+0.3 V; "
                       "operating VIN 2.3-6.0 V, TJ -40..125 C",
            "pins": "DS20001826E p.11 Table 3-1 SOT-23: 1 GND, 2 VOUT, 3 VIN = KiCad MCP1700x-330xxTT",
            "lifecycle": "Digi-Key Active [S]"})

# =============================================================================================
# Controller (block mcu)

STM32G031 = PartDef(
    mpn="STM32G031K8T6", manufacturer="STMicroelectronics", symbol="MCU_ST_STM32G0:STM32G031K8Tx",
    footprint="Package_QFP:LQFP-32_7x7mm_P0.8mm", value="STM32G031K8T6", category="ic",
    description="Arm Cortex-M0+ MCU 64 KB flash, 8 KB RAM, LQFP-32, -40..85 C",
    datasheet="https://www.st.com/resource/en/datasheet/stm32g031c6.pdf",
    ratings=Ratings(limits=[VLimit(("VDD",), ("VSS",), 4.0, "VDD-VSS -0.3..4.0 V"),
                            VLimit(("PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7", "PA8", "PA13", "PA14",
                                    "PB0", "PB1", "PB2", "PB8", "PB9", "PF2"), ("VSS",), 4.0,
                                   "4.0 V for non-FT pins; FT_xx pins allow VDD+4.0 - the lower bound is used")],
                    t_min=-40, t_max=85),
    lifecycle="active", second_source="STM32G031K6T6 (32 KB, same pinout)",
    source={"ratings": "ST DS12992 Rev 1 p.44 Table 18 Voltage characteristics: VDD-VSS -0.3..4.0 V; FT_xx "
                       "VSS-0.3..VDD+4.0; other pins VSS-0.3..4.0 V; 'T6' suffix -40..85 C",
            "pins": "DS12992 p.32 Figure 5 (LQFP32 pinout), Table 13 alternate functions (PA2/PA3 USART2 AF1, "
                    "PA5/6/7 SPI1 AF0), Table 12 (PA0 = ADC_IN0); KiCad symbol pins 19/21 are NC on G031",
            "lifecycle": "LCSC C432203 Active [S]"})
C_4U7 = C("4.7u", 10, "0603", dielectric="X5R", mpn="GRM188R61A475KE15D", manufacturer="Murata",
          datasheet=MURATA + "GRM188R61A475KE15%23", lifecycle="active", second_source="Samsung CL10A475KP8NNNC",
          source={"lifecycle": "Murata listing [S]"})
R_1K = R("1k", mpn="RC0603FR-071KL", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
         second_source="any 1 % 0603", source=SRC_R)
_LITEON = {"pins": "Lite-On LTST-C191 datasheet package drawing: cathode mark; Device:LED pin 1 = K",
           "lifecycle": "Digi-Key Active [S]"}
LED_GREEN = LED("green", "0603", mpn="LTST-C191KGKT", manufacturer="Lite-On", i_max=0.02,
                datasheet="https://optoelectronics.liteon.com/upload/download/DS22-2000-223/LTST-C191KGKT.pdf",
                lifecycle="active", second_source="Kingbright APT1608SGC",
                source={**_LITEON, "ratings": "LTST-C191 abs max IF 20 mA dc (25 mA pk), VR 5 V [S]"})
LED_RED = LED("red", "0603", mpn="LTST-C191KRKT", manufacturer="Lite-On", i_max=0.02,
              datasheet="https://optoelectronics.liteon.com/upload/download/DS22-2000-222/LTST-C191KRKT.pdf",
              lifecycle="active", second_source="Kingbright APT1608EC",
              source={**_LITEON, "ratings": "LTST-C191 abs max IF 20 mA dc, VR 5 V [S]"})
TAGCONNECT = PartDef(
    symbol="Connector:Conn_ARM_SWD_TagConnect_TC2030-NL",
    footprint="Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical", value="TC2030-IDC-NL",
    category="connector", prefix="J", generic=True, in_bom=False,
    description="SWD pads for a Tag-Connect TC2030-IDC-NL cable (no part fitted); factory programming only")
TP = TestPoint()

# =============================================================================================
# Global enable string (block en)

MMBT5551 = PartDef(
    mpn="MMBT5551LT1G", manufacturer="onsemi", symbol="Transistor_BJT:MMBT5551L",
    footprint="Package_TO_SOT_SMD:SOT-23", value="MMBT5551", category="bjt",
    description="NPN 160 V 600 mA, SOT-23 (opto-string current sink)",
    datasheet="https://www.onsemi.com/pdf/datasheet/mmbt5550lt1-d.pdf",
    ratings=Ratings(limits=[VLimit(("C",), ("E",), 160, "VCEO 160 V"), VLimit(("C",), ("B",), 180, "VCBO 180 V"),
                            VLimit(("E",), ("B",), 6.0, "VEBO 6.0 V")],
                    pin_i_max={"C": 0.6}, p_max=0.225, t_min=-55, t_max=150),
    lifecycle="active", second_source="Nexperia PMBT5551",
    source={"ratings": "onsemi MMBT5550L/5551L Rev 12 p.1: VCEO 160 V, VCBO 180 V, VEBO 6.0 V, IC 600 mA, PD 225 "
                       "mW (FR-5, 25 C); hFE >= 80 at 10 mA (p.2)",
            "pins": "Rev 12 p.1 SOT-23 diagram: 1 base, 2 emitter, 3 collector = KiCad Transistor_BJT:MMBT5551L",
            "lifecycle": "LCSC C150072 Active [S]"})
R_1K6_0805 = R("1.6k", "0805", mpn="RC0805FR-071K6L", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
               second_source="any 1 % 0805", source=SRC_R)
R_4K7_2010 = R("4.7k", "2010", p_max=0.5, mpn="RC2010FK-074K7L", manufacturer="Yageo", datasheet=YAGEO_RC,
               lifecycle="active", second_source="Vishay CRCW20104K70FKEF",
               source={**SRC_R, "ratings": "0.5 W used (conservative; RC2010 is rated 3/4 W [S]); 200 V"})

# =============================================================================================
# Isolated user port and fault contact (block iso)

ISO7721 = PartDef(
    mpn="ISO7721DWVR", manufacturer="Texas Instruments", symbol="Isolator:ISO7721DWV",
    footprint="Package_SO:SOIC-8_7.5x5.85mm_P1.27mm", value="ISO7721DWV", category="ic",
    description="Reinforced dual digital isolator (1 forward / 1 reverse), 5000 Vrms, 8.5 mm creepage, SOIC-8 DWV",
    datasheet="https://www.ti.com/lit/ds/symlink/iso7721.pdf",
    ratings=Ratings(
        limits=[VLimit(("VCC1",), ("GND1",), 6, "supply -0.5..6 V"),
                VLimit(("VCC2",), ("GND2",), 6, "supply -0.5..6 V"),
                VLimit(("OUTA", "INB"), ("GND1",), 6, "-0.5..VCC1+0.5 (<= 6 V)"),
                VLimit(("OUTB", "INA"), ("GND2",), 6, "-0.5..VCC2+0.5 (<= 6 V)")],
        pin_i_max={"OUTA": 0.015, "OUTB": 0.015},
        isolation=[Isolation(("VCC1", "OUTA", "INB", "GND1"), ("GND2", "OUTB", "INA", "VCC2"), v_iso_rms=5000,
                             grade="reinforced", v_work_rms=1500, creepage_mm=8.5,
                             standard="DIN EN IEC 60747-17 (VDE 0884-17) reinforced; UL 1577 5000 Vrms; "
                                      "IEC 62368-1")],
        t_min=-40, t_max=125),
    lifecycle="active", second_source="ADuM1201BRWZ (narrower ratings) [unverified]",
    source={"ratings": "TI SLLSEP3G (May 2024) p.7 section 6.1 abs max (VCC 6 V, IO +/-15 mA); p.10 section 6.6 "
                       "DWV: CLR/CPG 8.5 mm, VIORM 2121 Vpk, VIOWM 1500 Vrms, VIOTM 7071 Vpk, VISO 5000 Vrms, "
                       "CTI > 600 V, reinforced",
            "pins": "SLLSEP3G p.6 Table 5-1 (D/DWV): 1 VCC1, 2 OUTA, 3 INB, 4 GND1, 5 GND2, 6 OUTB, 7 INA, 8 VCC2 "
                    "= KiCad Isolator:ISO7721DWV",
            "lifecycle": "TI.com Active [S]"})

AQY210EH = PartDef(
    mpn="AQY210EHAX", manufacturer="Panasonic", symbol="Relay_SolidState:AQY280EH",
    footprint="Package_DIP:SMDIP-4_W7.62mm", value="AQY210EHAX", category="opto", prefix="U",
    description="PhotoMOS 1 Form A, 350 V 130 mA, reinforced 5000 Vrms, SMD 4-pin (fault contact)",
    datasheet="https://www3.panasonic.biz/ac/e_download/control/relay/photomos/catalog/semi_eng_ge2a_aqy21_eh.pdf",
    # KiCad's AQY280EH symbol (same 4-pin PhotoMOS pinout) has unnamed pins.
    pin_names={"1": "LED_A", "2": "LED_K", "3": "OUT1", "4": "OUT2"},
    ratings=Ratings(
        limits=[VLimit(("LED_A",), ("LED_K",), 3, "LED reverse voltage VR 3 V"),
                VLimit(("OUT1",), ("OUT2",), 350, "load voltage 350 V peak AC/DC")],
        pin_i_max={"LED_A": 0.05, "OUT1": 0.13, "OUT2": 0.13},
        isolation=[Isolation(("LED_A", "LED_K"), ("OUT1", "OUT2"), v_iso_rms=5000, grade="reinforced",
                             standard="Panasonic: 'reinforced insulation 5,000 V type', EN 41003 / EN 60950 "
                                      "reinforced; package creepage not stated (footprint pad gap 5.6 mm)")],
        t_min=-40, t_max=85),
    lifecycle="active", second_source="Panasonic AQY214EHAX (400 V 120 mA, same package)",
    source={"pin_names": "Panasonic AQY21xEH catalog p.1 schematic/terminal diagram: 1 LED anode, 2 LED cathode, "
                         "3-4 MOSFET output (AC/DC); package drawing gives positions 1-4 [P]; function convention [S]",
            "ratings": "AQY21xEH catalog p.1 absolute maximum ratings: IF 50 mA, VR 3 V, VL 350 V, IL 0.13 A, "
                       "Viso 5000 Vrms AC, Topr -40..85 C; 'Reinforced insulation 5,000 V type'",
            "lifecycle": "LCSC C24728 / Digi-Key Active [S]"})

TPD4E05U06 = PartDef(
    mpn="TPD4E05U06DQAR", manufacturer="Texas Instruments", symbol="Power_Protection:TPD4E05U06DQA",
    footprint="Package_SON:USON-10_2.5x1.0mm_P0.5mm", value="TPD4E05U06", category="tvs", prefix="U",
    description="4-channel ESD array, VRWM 5.5 V, IEC 61000-4-2 +/-12 kV contact (user-port pins)",
    datasheet="https://www.ti.com/lit/ds/symlink/tpd4e05u06.pdf",
    ratings=Ratings(limits=[VLimit(("D1+", "D1-", "D2+", "D2-"), ("GND",), 5.5, "VRWM 5.5 V")],
                    t_min=-40, t_max=125),
    lifecycle="active", second_source="TI TPD4E1U06DBVR (SOT-23-6)",
    source={"pins": "TI SLVSBO7O (Aug 2024) p.4 Table 4-2 (DQA): D1+ 1, D1- 2, GND 3 and 8, D2+ 4, D2- 5, NC 6, 7, "
                    "9, 10 (may float)",
            "ratings": "SLVSBO7O p.5 abs max: IEC 61000-4-5 2.5 A / 40 W (8/20 us); p.5 5.1 IEC 61000-4-2 +/-12 kV "
                       "contact; section 5.4 VRWM 5.5 V, VBR 6.5-8.5 V",
            "lifecycle": "TI.com Active [S]"})
SMBJ40CA = PartDef(
    mpn="SMBJ40CA", manufacturer="Littelfuse", symbol="Device:D_TVS", footprint="Diode_SMD:D_SMB",
    value="SMBJ40CA", category="tvs",
    description="TVS bidirectional 600 W, VR 40 V, VC 64.5 V (fault-contact surge/ESD clamp)",
    datasheet="https://www.littelfuse.com/assetdocs/littelfuse-tvs-diode-smbj-datasheet",
    ratings=Ratings(v_max=40),
    lifecycle="active", second_source="Vishay SMBJ40CA-E3/52",
    source={"ratings": "Littelfuse SMBJ series rev JC.07/04/25 v4 p.2: SMBJ40CA VR 40 V, VBR 44.4-49.1 V, IR 1 uA, "
                       "VC 64.5 V at 9.3 A; 600 W 10/1000 us",
            "lifecycle": "Littelfuse / LCSC listing Active [S]"})
R_390 = R("390", mpn="RC0603FR-07390RL", manufacturer="Yageo", datasheet=YAGEO_RC, lifecycle="active",
          second_source="any 1 % 0603", source=SRC_R)
_MC = {"ratings": "Phoenix MC 1,5/..-G-3,81 family: 8 A, 160 V (IEC III/2) [S, distributor listings]; order "
                  "number from the family numbering [I] - confirm before ordering",
       "lifecycle": "distributor listings Active [S]"}
J_USER = Conn(4, "Connector_Phoenix_MC:PhoenixContact_MC_1,5_4-G-3.81_1x04_P3.81mm_Horizontal", i_max=8,
              v_max=160, mpn="1803293", manufacturer="Phoenix Contact",
              datasheet="https://www.phoenixcontact.com/en-us/products/pcb-header-mc-15-4-g-381-1803293",
              lifecycle="active", second_source="Wurth 3.81 mm pluggable header", source=_MC).with_(
    description="User UART port: header MC 1,5/4-G-3,81, plug MC 1,5/4-ST-3,81")
J_FAULT = Conn(2, "Connector_Phoenix_MC:PhoenixContact_MC_1,5_2-G-3.81_1x02_P3.81mm_Horizontal", i_max=8,
               v_max=160, mpn="1803277", manufacturer="Phoenix Contact",
               datasheet="https://www.phoenixcontact.com/en-us/products/pcb-header-mc-15-2-g-381-1803277",
               lifecycle="active", second_source="Wurth 3.81 mm pluggable header", source=_MC).with_(
    description="Fault contact: header MC 1,5/2-G-3,81, plug MC 1,5/2-ST-3,81")

# =============================================================================================
# Off-board harness (block harness, board="off")

F_INLINE = Fuse(
    7, 125, None, mpn="0324007.HXP", manufacturer="Littelfuse", i2t=71.0, breaking_a=10000,
    datasheet="https://www.littelfuse.com/assetdocs/littelfuse-fuse-314-324-datasheet",
    lifecycle="active", second_source="0314007.MXP (ceramic 3AB, same rating) in a 6.3 x 32 mm in-line holder",
    fields={"R_cold": "18.7 mOhm", "Format": "3AB axial, butt-spliced, sealed in adhesive heat-shrink"},
    source={"ratings": "Littelfuse 314/324 series (revised 07/31/15) p.1 table: 324 007. 7 A, 250 V, interrupting "
                       "750 A at 250 VAC / 10 kA at 125 VAC and 125 VDC (004-008 rows), cold R 0.0187 ohm, "
                       "melting I2t 71.0 A2s; UL 248-14",
            "lifecycle": "Digi-Key listing, $3.03 (Oct 2026) [P]"}).with_(
    description="Inline tap fuse at the ring terminal: 3AB 7 A fast, 10 kA at 125 VDC")
RING = Conn(1, None, mpn="PV18-14R-MY", manufacturer="Panduit",
            datasheet="https://www.panduit.com/content/dam/panduit/en/products/media/7/31/831/PV18-14R-MY.pdf",
            lifecycle="active", second_source="TE PIDG 1/4 in ring for 22-18 AWG",
            source={"ratings": "Panduit PV18-14R-MY: vinyl-insulated ring, 22-18 AWG, 1/4 in (M6) stud [S, Digi-Key]",
                    "lifecycle": "Digi-Key Active [S]"}).with_(
    description="Ring terminal 22-18 AWG, 1/4 in (M6) stud, at each cell terminal")
PLUG_TAPS = Conn(17, None, i_max=12, v_max=320, mpn="1757161", manufacturer="Phoenix Contact",
                 datasheet="https://www.phoenixcontact.com/en-us/products/pcb-plug-mstb-25-17-st-508-1757161",
                 lifecycle="active", second_source="none drop-in",
                 source={"ratings": "Phoenix MSTB 2,5/17-ST-5,08 (1757161) screw plug: 12 A, 320 V [S]",
                         "lifecycle": "distributor listings Active [S]"}).with_(
    description="Harness plug MSTB 2,5/17-ST-5,08 mating J1; EBP 2-5 (1733169) bridges join positions N+1..17")

# =============================================================================================
# Mechanical

HOLE_M4 = MountingHole("MountingHole:MountingHole_4.3mm_M4",
                       description="M4 mounting hole, non-plated; 3.0 mm copper keepout ring (barrier B-5)")
