# DDR3, DDR4 and LPDDR4 layout rules (controller-keyed)

*Tags: [P] primary source read, [S] snippet only, [I] our inference.*

**TL;DR**
- **Rules depend on the controller, and vendors differ greatly.**
  - DQ↔DQS: 2 ps (TI AM62x), 3.5 ps (Intel Agilex 5, [S]), 10 ps (Intel DDR3, [S]), 25 ps (Microchip PolarFire).
  - ADDR↔CK: 4 ps (TI) to 100 ps (Microchip).
  - Pick the pack for the actual controller. Fall back to the tightest value when the controller is unknown.
- **Fly-by matching is per SDRAM.** Emit one `fromTo()` length or skew rule per SDRAM per group, plus `within_diff_pairs` for CK and DQS. A single net-class-wide skew rule cannot express fly-by.
- **Match only within a byte lane.** Cross-byte matching is "neither required nor recommended" for DDR4/LPDDR4.
- **Policy (TI):** match in the layout tool to <20% of each limit, keep the full limit as `max`, then confirm with power-aware IBIS simulation across PVT.
  - Micron's principled default allocates about 1% of the clock period to matching: ±1 mm for address and ±0.5 mm for data at 800 MHz.
- **Delay-to-length conversions differ by vendor** (5–6.1 mil/ps). Use KiCad 10's stackup-based delay model instead of any fixed constant.

## Key facts

### DDR3 (TI KeyStone, [SPRABI1D](https://www.ti.com/lit/pdf/sprabi1) Rev. Jul 2022 [P])

| Group | Rules |
|---|---|
| Impedance | 50 Ω ±5% SE; 100 Ω ±5% on DQS and CK pairs |
| ADDR/CMD/CTRL fly-by | Same path, controller → each SDRAM in sequence → VTT. Each net matched to CK **within ±20 mil (0.51 mm) to each SDRAM separately**. Same via count per matched segment. Stubs <80 mil (2.03 mm); stub skew ±10 mil. Solid GND (or DVDD15) reference on close layers |
| CK fly-by | Matched controller → each SDRAM within ±1 mil; stubs <40 mil; AC VTT termination at the end |
| Byte lanes | DQS ±1 mil; byte nets ±10 mil; ≤2 vias, equal count across the byte; one layer per byte; no mid-point vias; ODT only (no VTT on data); bit swaps within a byte allowed |
| Spacing | Centre-to-centre ≥5W, including serpentine (4W allowed, but not above 1066 MT/s). All matching uses stripline-equivalent length |
| Termination | 39–42 Ω (39 Ω 1% preferred) to VTT = VDDQ/2 = 0.75 V, at the **last SDRAM**. Each trace ≤500 mil (12.7 mm) to its termination; the resistor's far side goes directly to the VTT rail |
| VREF | 0.01 µF + 0.1 µF at each Vref pin, plus 0.1 µF at the source. Trace ≥30 mil (0.76 mm), ≥15 mil (0.38 mm) from other nets, top layer, shielded with GND. ±1% tolerance |
| VTT supply | VTT regulator close to the SDRAMs; VTT island on the component side; ≥1 × 0.1 µF per VTT pin plus ≥1 × 10–22 µF bulk |
| Write leveling | Limit 2500 ps (theoretical). DDR3-1333 example: max <2135 ps (or <1385 ps), min >365 ps, assuming 180 ps/in |

### DDR3 point-to-point and other vendors
- **Micron** ([TN-41-13](https://cdn.hackaday.io/files/19354828041536/tn4113_ddr3_point_to_point_design.pdf) [P]):
  - Allocate about 1% of the timing budget to matching. At 800 MHz, 6.25 ps ≈ ±1 mm at 6.5 ps/mm.
  - Data with a 625 ps bit: ±0.5 mm.
  - Address branches matched within 1 mm.
  - Outer-layer propagation is about 10% faster than inner.
  - "To match all traces within 10 ps, traces must be held within a range of 1.5 mm, 60 mils."
  - Keep via counts equal; consider up to 20 ps per via.
- **Snippet-level values from other vendors** [S]:
  - Intel: byte lane ±10 ps (FPGAs cannot reliably deskew >20 ps); ADDR/CMD to CK ±20 ps per device.
  - ISSI: ±10 ps ≈ ±50 mil.
  - PCBWay blog: ±25 mil; stubs <200 mil (ideally <100 mil).

### DDR4 (TI AM62x/AM62Lx, [SPRAD06C](https://www.ti.com/lit/pdf/sprad06) Rev. Mar 2025 [P])

| Group | Rules |
|---|---|
| CK + ADDR_CTRL (Table 2-6) | A1+A2 (SoC → first SDRAM) ≤500 ps, ADDR_CTRL-to-CK skew ≤3 ps. A3 (between SDRAMs) ≤125 ps, skew ≤3 ps. AS (stub) 5–17 ps, skew 1.3–3 ps. AT (to termination) ≤75 ps, skew ≤14 ps. CK P/N ≤0.4 ps per segment, ≤0.8 ps total. Total CK-to-ADDR_CTRL per SDRAM ≤4 ps. ≤3 vias per trace, via-count difference ≤1. Spacing 4w (to other DDR4) and 3w (within ADDR_CTRL); 2w allowed within ≤500 mil of endpoints. Rcp = Zo ±1 Ω; Rtt = Zo ±5 Ω. **Series termination not allowed** |
| Data (Table 2-7) | BYTE ≤500 ps; DQS P/N ≤0.4 ps; **DQS-to-DQ ≤2 ps**. ≤2 vias, count difference 0. Spacing 4w/3w. Match only within a byte. Byte swaps allowed; bit swaps within a byte only without CRC. "1 ps can be equated to 5 mils" of stripline-equivalent length |
| VREF / VTT | VREFCA nominal 20 mil trace with 0.1 µF near each device pin. VTT as a power sub-plane at the end of the bus, decoupled near the terminators. VTT optional with one memory device, but CK termination is still required |

**DDR4, other controllers:**
- **Microchip PolarFire / PolarFire SoC** (≤1600 MT/s on HSIO banks) ([skew page](https://onlinedocs.microchip.com/oxy/GUID-FF8061A7-7A15-470F-A6F5-E733C24D85F0-en-US-11/GUID-07D00815-AB98-4174-B330-DAD67471AD0C.html) [P]):
  - ADDR/CMD groups within **±100 ps** of CK; DQ/DM within **±25 ps** of DQS. Read training adjusts DQS for the residual skew.
  - Fly-by ADDR/CMD and CK, terminated at the last device (VDD/2 or VDDI/2).
  - R_T 30–50 Ω; Z0 typically 50 Ω; Zdiff 100 Ω; ODT 80/120/240 Ω; DQ needs no VTT.
- **Intel Agilex 5 down-memory:** DQ-to-DQS within a byte ±3.5 ps; DQS-to-DQS <1 ps; package length included [S].

### LPDDR4 (TI AM62x, SPRAD06C Tables 3-6/3-7 [P])

| Group | Rules |
|---|---|
| CK0 + ADDR_CTRL | Propagation ≤450 ps each (assumes Dk ≈3.7–3.9, Df ≈0.002). **CK0 P/N ≤0.75 ps.** ADDR_CTRL relative to CK0 within ±312.5 ps, measured die pad to DRAM pin including package. ≤3 vias; via stub ≤20 mil; via-count difference ≤1. Spacing 5w (to other LPDDR4 and non-DDR nets), 3w within ADDR_CTRL |
| Data | DQS and BYTE ≤450 ps. CK0 delay − DQS delay = 0 to 3 tCK (CK longer). DQS P/N ≤1.5 ps; DQS-to-BYTE ≤150 ps (per-bit deskew); shortest DQ/DM − DQS ≥ −49 ps. ≤2 vias; via stub ≤40 mil; count difference 0 |
| Policy | Match in the tool to <20% of each limit, then confirm by power-aware IBIS simulation across PVT |

### Delay-to-length conversions (vendor-specific)

| Source | Conversion |
|---|---|
| TI SPRAD06C | 1 ps ≈ 5 mil |
| TI SPRABI1D | 180 ps/in ≈ 5.6 mil/ps [I] |
| Micron | 6.5 ps/mm ≈ 6.1 mil/ps [I] |
| Renesas | 1 mm ≈ 6 ps |
| NXP forum | 6 mil/ps for package delay [S] |

### Rule summary for emission

| ID | Rule | Check |
|---|---|---|
| DDR3-FLY | ADDR/CMD/CTRL vs CK per SDRAM: ±0.51 mm (TI) / ±1 mm (Micron) / ±20 ps (Intel) | K `skew` with `fromTo('Usoc-*','UdramN-*')` per SDRAM |
| DDR3-STUB | Stubs <2.03 mm (ADDR/CMD), <1.02 mm (CK); stub skew ±0.25 mm | G |
| DDR3-BYTE | DQS ±0.025 mm; DQ/DM ±0.25 mm (TI) or ±0.5 mm (Micron); ≤2 equal vias; one layer | K `skew`, `via_count`; G same-layer |
| DDR3-TERM / VREF | 39 Ω at last SDRAM ≤12.7 mm; VREF width and clearance | G; K `track_width`, `clearance` |
| DDR-SP | Centre-to-centre spacing; edge gap = (k−1)·W | K `clearance` |
| DDR4-SEG / SKEW | Segment delays and skews in ps (vendor-selected) | K `length`/`skew` (ps) + `fromTo` |
| LP4-DLY / STUB | Delays in ps; CA stub ≤0.51 mm, data stub ≤1.02 mm | K + S; G |
| DDR-VIA | ≤20 ps per via when counts differ | G / K time-domain via model |
| DDR-XBYTE | Never emit cross-byte skew rules | Pack policy |
| DDR-DERATE | `opt` = 20% of each ps limit; `max` = the limit | Pack policy |

## Recommendations for our system
- **Placement.** Use fly-by order (controller → SDRAM1 → … → termination), keeping the VTT regulator and termination resistors at the far end.
- **Constraints.** Generate per-SDRAM `fromTo` rules in ps (KiCad 10 time domain), with the per-layer and via delay coming from the stackup. Apply byte-lane-only matching.
- **Scaling.** Scale the Micron 1% rule linearly with clock period when no controller pack exists.

## Conflicts and open questions
- **Vendor spread:** 12.5–25× between vendors. Key every pack by controller vendor.
- **Missing sources:**
  - No JEDEC primary document was read.
  - ST AN5122, the NXP i.MX8M guides, Xilinx UG583 and the Intel EMIF tables were not reachable as primary text.

## Sources
- Research notes: [interface_rule_packs.md § 3](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md).

See also:
- [../diff-pairs.md](../diff-pairs.md)
- [../rule-pack-format.md](../rule-pack-format.md)
- [../checkers-si-emi.md](../checkers-si-emi.md)
