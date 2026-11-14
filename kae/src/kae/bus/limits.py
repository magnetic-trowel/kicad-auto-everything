# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Class- and controller-keyed limits for the bus scorecard (report-only).

A check with no controller key fails most working boards (docs/research/routing/bus-yardstick-2611.md), so a limit is keyed when
the controller, the DRAM generation or the interface identifies it; otherwise it is a class default, marked `keyed=False`,
and must be read as "assumed". Sources are the rule packs under docs/topics/rules/. Skews are in mm of copper at about
6.8 ps/mm unless the source states otherwise. Classes with no timing budget (RGB, GPIO, ribbons, matrices, slow QSPI)
get none: length, skew and coupling do not matter there.
"""
from __future__ import annotations
import re
from dataclasses import asdict, dataclass

PS_PER_MM = 6.8


@dataclass(frozen=True)
class Limit:
    skew_mm: float | None = None      # within-group length skew
    via_max: int | None = None        # vias per lane
    via_spread: int | None = None     # max - min vias per lane
    keyed: bool = False               # from the controller or interface itself, not a class default
    source: str = ""

    def asdict(self):
        return asdict(self)


NONE = Limit(source="no budget for this class")

# DRAM part numbers to generation; value and MPN text
_DRAM_GEN = [(r"LPDDR5", "lpddr5"), (r"LPDDR4|^MT53[DEB]|^K4F[A-Z]|^H9HC", "lpddr4"), (r"LPDDR3|^MT52L", "lpddr3"), (r"LPDDR2|^MT42L", "lpddr2"),
             (r"DDR5|^MT60[BEP]", "ddr5"), (r"DDR4|^MT40A|^K4A[A-Z0-9]|^H5A[A-Z]|^NT5AD|^IS43QR", "ddr4"),
             (r"DDR3|^MT41[JKH]|^K4B[A-Z0-9]|^H5TQ|^H5TC|^NT5C|^IS43TR|^IS46TR|^AS4C\d+M\d+D3|^W63[0-9]", "ddr3"),
             (r"DDR2|^MT47H|^K4T[A-Z0-9]|^H5PS|^NT5T|^IS43DR|^AS4C\d+M\d+D2", "ddr2"),
             (r"DDR1?\b|^MT46V|^K4H[A-Z0-9]|^HY5DU|^IS43R", "ddr1")]

# Controller keys for DDR data skew: (regex on the controller's value/MPN, generation or None, limit)
_CTRL_DDR = [
    (r"AM62|AM64|AM6[0-9]", None, Limit(0.3, 2, 0, True, "TI AM62x DDR4: 2 ps within byte")),
    (r"TMS320C66|66AK2|TCI66", "ddr3", Limit(0.254, 2, 0, True, "TI KeyStone DDR3: 10 mil byte nets")),
    (r"A5E|AGILEX", None, Limit(0.51, 2, 0, True, "Intel Agilex 5: 3.5 ps within byte")),
    (r"EP[2-4]|5C[EGS]|10M\d\d|CYCLONE|ARRIA|STRATIX", "ddr3", Limit(1.47, 2, 0, True, "Intel DDR3: 10 ps within byte")),
    (r"MPF\d|MPFS|POLARFIRE", None, Limit(3.7, 2, 0, True, "Microchip PolarFire: +/-25 ps with read training")),
]
# Generation defaults: Micron's 0.5 mm at 625 ps for DDR3; DDR4's widest published controller figure; never a target.
_GEN_DEFAULT = {
    "ddr3": Limit(0.5, 2, 0, False, "Micron DDR3 +/-0.5 mm; controller not recognised"),
    "ddr4": Limit(3.7, 2, 0, False, "widest DDR4 controller figure (PolarFire); controller not recognised"),
    "lpddr4": Limit(22.0, 2, 0, False, "LPDDR4 150 ps with per-bit deskew; no deskew assumed would be 1.5 mm"),
}
_DRAM_ANY = Limit(None, 2, 0, False, "DRAM generation not recognised; via rule only")
_DDR_ADDR = Limit(None, 3, 1, False, "fly-by address: skew is per device, not whole-copper; via rule only")
_SD = Limit(6.0, None, 0, False, "SD at 100 MHz (Qualcomm 6 mm); bus speed unknown, HS400 would be 1.27 mm")
_EMMC = Limit(6.0, None, 0, False, "eMMC speed unknown; HS400 would be 1.27 mm (Micron)")
_RGMII = Limit(74.0, None, None, False, "RGMII v2.0 +/-500 ps; TI PHYs ask 1.5 mm")
_QSPI = Limit(None, None, None, False, "QSPI: report only without a clock above 100 MHz")
_PAIR = {"pcie": Limit(0.127, 4, None, True, "PCIe intra-pair 5 mil (TI)"),
         "usb2": Limit(1.27, 4, None, True, "USB2 intra-pair 50 mil (TI SPRAAR7J)"),
         "ethernet_mdi": Limit(1.27, None, None, False, "Ethernet MDI intra-pair 50 mil (10/100, TI, Pulse); 1G would be 0.51 mm"),
         "usb3": Limit(0.127, 2, None, True, "USB3 intra-pair 5 mil (TI)"),
         "hdmi": Limit(3.7, 2, None, True, "HDMI intra-pair 0.15 Tbit, about 25 ps"),
         "mipi": Limit(0.7, 2, None, True, "MIPI D-PHY intra-pair (Qualcomm 0.7 mm)"),
         "lvds": Limit(7.4, None, None, True, "LVDS intra-pair about 50 ps (RSKM part-dependent)"),
         "sata": Limit(0.127, 2, None, True, "SATA intra-pair 5 mil")}


def dram_generation(text):
    """A DRAM generation from a part's value or MPN, else None."""
    for pat, gen in _DRAM_GEN:
        if re.search(pat, text or "", re.I):
            return gen
    return None


def _part_text(pi):
    fp = pi["fp"]
    f = fp.fields or {}
    return " ".join(str(x) for x in (fp.value, f.get("MPN", ""), f.get("Manufacturer Part Number", ""), f.get("Description", ""), fp.lib_id))


def for_bus(row, part):
    """The Limit for one bus record (see kae.bus.detect.enrich), from its class and its end parts."""
    kind = row["kind"]
    if kind == "pair":
        return _PAIR.get((row.get("iface") or "").lower().replace(" ", ""), NONE)
    if kind in ("ddr_byte", "ddr_addr"):
        ends = [row.get("a"), row.get("b")]
        gens = [dram_generation(_part_text(part[e])) for e in ends if e in part and part[e].get("cls") == "dram"]
        gen = next((g for g in gens if g), None)
        if kind == "ddr_addr":
            return _DDR_ADDR
        ctrl = next((e for e in ends if e in part and part[e].get("cls") in ("fpga", "mcu", "memory", "ic")
                     and part[e].get("cls") != "dram"), None)
        text = _part_text(part[ctrl]) if ctrl else ""
        for pat, g, lim in _CTRL_DDR:
            if re.search(pat, text, re.I) and (g is None or g == gen):
                return lim
        return _GEN_DEFAULT.get(gen, _DRAM_ANY)
    if kind == "sd_emmc":
        names = " ".join(row.get("names") or []).upper()
        return _EMMC if "MMC" in names else _SD
    if kind == "eth_mii":
        return _RGMII if "RGMII" in " ".join(row.get("names") or []).upper() or row.get("ifaces") == ["rgmii"] else NONE
    if kind == "qspi":
        return _QSPI
    if kind == "serdes_lanes":
        return Limit(source="lane-to-lane skew: receiver deskews; intra-pair is reported per pair")
    return NONE
