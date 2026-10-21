# USB 2.0 High-Speed (480 Mb/s) layout rules

*Tags:*
- [P] primary source read
- [S] snippet
- [I] our inference

*Vendor values differ, so select by the PHY vendor's profile.*

**TL;DR**
- **The forgiving interface.**
  - Default 90 Ω ±15% differential and 45 Ω ±15% single-ended.
  - Intra-pair mismatch ≤1.27 mm (50 mil).
  - ≤4 vias, zero stubs or test points, no AC caps, no P/N swap.
- **Vendors span wide ranges:**
  - Zdiff: 75–105 Ω (Qualcomm) to 90 +5/−10 Ω (Microchip).
  - Skew: 2 mil (TI, 2013 guide) to 150 mil (TI controller datasheets) or 2 mm (Qualcomm).
  - Maximum length: 4 in (TI, 2013) to 250 mm (Qualcomm) or 304.8 mm (TI, 2023).
- **Spacing:** ≥30 mil to other nets and ≥50 mil to clocks (TI). Keep a continuous GND under the pair, extending ≥5× the pair gap each side.
- **Chain order at the connector:** connector → ESD → (CMC) → PHY. ESD topology rules apply: no via or stub before the TVS.
- **Cable-shield termination conflicts across vendors.** Ask the user.

## Key facts
| Param | Default | Variants / conflicts | Check |
|---|---|---|---|
| Impedance | 90 Ω ±15% diff, 45 Ω ±15% SE; no AC caps; no polarity reversal; 5 m cable ([TI SLLA414A](https://www.ti.com/lit/pdf/slla414) [P]) | SPRAAR7J: 81–90–99 Ω, Zcm 40.5–49.5 Ω. Qualcomm: 75–105 Ω. Microchip AN26.2: 90 +5/−10 Ω, Z0 40–55 Ω. AN13.10: SE 42–78 Ω "acceptable" (Zcm 21–39). SPRAAR7A: SE 45 Ω ±10% | K net class; width and gap from the stackup solver; S to verify |
| Intra-pair skew | ≤1.27 mm (50 mil) ([TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P; VERIFIED+CTX]; [AN26.2](https://ww1.microchip.com/downloads/en/AppNotes/00001876.pdf)) | SPRAAR7A (2013): within 2 mil, measured from the package boundary; TUSB9261/SLLU149E: 150 mil; [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/usb-2dot0-routing-constraints.html): 2 mm | K `skew (max 1.27mm) (within_diff_pairs)` |
| Length | Warn >150 mm (Microchip: "~15 cm may significantly degrade"); error >250 mm (Qualcomm) or >304.8 mm (TI Rev J; typical 101.6 mm) | SPRAAR7A: "no more than 4 inches". SLLU149E: >8 in → "contact TI". TI loosened sharply between Rev A (2013) and Rev J (2023) | K `length` with `fromTo('J*-*','U*-*')` |
| Vias | ≤4 per trace | — | K `via_count (max 4)` |
| Stubs / test points | 0 / 0 | Legacy: a stub <200 mil if unavoidable; keep 1 kΩ resistor stubs short (Qualcomm) | G: no T-junctions or TP pads |
| Spacing | ≥30 mil (0.76 mm) to other nets; ≥50 mil (1.27 mm) to clock or periodic nets (TI) | Microchip: ≥3X, X = max(W, dielectric H) (W 8/H 4.3 → 24 mil; W 12/H 22 → 66 mil); Qualcomm: 3× line width. Meanders: amplitude ≤3X, gap ≥5X | K `clearance` between classes |
| Reference | Continuous GND under DP/DM, ≥5× the pair spacing to each side; parts ≥5× the spacing away; no routing under parts ([AN13.10](https://ww1.microchip.com/downloads/en/Appnotes/AN13.10-Application-Note-DS00002972A.pdf) [P]) | Example: 14 mil traces, 7 mil gap, 13 mil to reference | G: zone covers the offset polygon |
| Topology | No extra components on DP/DM; one pair cannot be routed to two connectors; external parts near the connector | SPRAAR7A; Qualcomm [P] | M/G |
| Connector entry | Through-hole receptacle: connect on the bottom layer so the TH pin is in the signal path, not a stub. SMT receptacle: top layer, no vias. ≥0.5 mm clearance around TH pins on all layers; remove unused-layer pads | SPRAAR7J §3.5; AN26.2 [P; VERIFIED] | G |
| Keep-aways | PHY JTAG <6 in; switching regulators away from DP/DM, the crystal and the PHY (SPRAAR7A) | — | G |
| **Shield termination** | **Conflict, resolution `ask`:** Microchip AN26.2 uses 330 Ω ∥ 0.1 µF shield-to-GND at each connector. Microchip AN13.10: ground the host side only; a device should AC-couple the housing. TI SPRAAR7A: short the shell to a small chassis strap (signal GND kept under pins 1–6), with a 10–50 Ω at 100 MHz ferrite in series with the shield (resistive to ~1 GHz) and an optional 47–1000 Ω at 100 MHz ferrite in VBUS | [P] | ask |
| ESD / CMC | ESD closest to the connector, then the CMC (TUSB9261). No via between the connector and the TVS; no stub; GND via immediately adjacent to the TVS GND pin; ESD-path corners curved or ≤45° | [SLVA680A](https://www.ti.com/lit/pdf/slva680); [TPD6S300A](https://www.ti.com/lit/ds/symlink/tpd6s300a.pdf) [P] | G: path order |

### Worked pack (condensed from [IF] §11)
```yaml
pack: {id: usb2_hs, precedence: 20, vendor_profile: unknown}
applies_when:
  parts: [conn: lib_regex "USB_(A|B|C|Micro|Mini).*", phy: pins [USB_DP, USB_DM],
          esd: "(TPD|USBLC|PESD|ESD).*" optional, cmc: common_mode_choke optional]
parameters:
  zdiff: 90 ohm ±15% (P, SLLA414A)      by_vendor {qualcomm: 75-105, microchip: "90 +5/-10"}
  intra_skew_max: 1.27 mm (P, SPRAAR7J)  by_vendor {qualcomm: 2.0, ti_usb_controllers: 3.81}
  len_warn: 150 mm (P, AN26.2); len_max: 250 mm (P, Qualcomm) by_vendor {ti: 304.8}
  via_max: 4; gap_other_min: 0.762 mm; gap_clock_min: 1.27 mm; gnd_overhang: 5*pair_gap (AN13.10)
  esd_conn_max: 5.0 mm (D/I heuristic; TI says only "as close as possible")
conflicts: intra_skew_max -> vendor_profile; shield_termination -> ask
placement: anchor conn on board_edge; order_along_path [conn.DP, esd, cmc, phy.USB_DP] (and DM)
checks:
  - USB2-SKEW kicad_dru: (rule "USB2 intra-pair skew" (condition "A.hasNetclass('USB2')")
                          (constraint skew (max 1.27mm) (within_diff_pairs)))   # verify token form
  - USB2-VIA  kicad_dru: (constraint via_count (max 4))
  - USB2-LEN  kicad_dru: (condition "A.fromTo('${conn}-*','${phy}-*') && A.hasNetclass('USB2')") length max
  - USB2-SP   kicad_dru: USB2 vs !USB2 clearance (min 0.762mm)
  - geometric: no_t_junctions_or_testpoints; gnd_zone_covers(offset_polygon); ESD path order, 0 vias, GND via ≤1.0 mm
  - bom: no_series_caps(dp, dm)
```

## Recommendations for our system
- **Default to TI's 50 mil skew**, overridden by the PHY vendor's profile.
- **Emit length as `fromTo(connector, PHY)`.** Warn at 150 mm; error at the vendor maximum.
- **Placer:**
  - anchor the connector on the board edge;
  - place ESD, then the CMC, at the pins;
  - keep the PHY close by, within the I/O zone ([../emc-placement.md](../emc-placement.md)).
- **Ask the user about the shield-termination scheme** (host vs device), and log the choice.

## Conflicts and open questions
- **Skew, length and impedance ranges:** select by vendor profile.
- **Shield termination:** three vendor schemes, so ask.
- **TVS distance in mm:** there is none in the primary sources, so the 5 mm figure is [I] and soft.

## Sources
- research notes: [interface_rule_packs.md § 1 USB](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md); [verification_rules.md § 1A DP-2, DP-6](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- TI SPRAAR7A (2013): https://e2echina.ti.com/cfs-file/__key/telligent-evolution-components-attachments/13-106-00-00-00-00-33-10/USB-2.0-Board-Design-and-Layout-Guidelines.pdf

See also: [usb3-usb4-typec.md](usb3-usb4-typec.md), [../diff-pairs.md](../diff-pairs.md), [../emc-placement.md](../emc-placement.md), [../rule-pack-format.md](../rule-pack-format.md)
