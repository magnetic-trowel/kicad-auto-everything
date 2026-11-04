# Ethernet 10/100/1000BASE-T (MDI, magnetics, PHY placement, Bob Smith) and RGMII/MII

Scope: BASE-T MDI pairs, magnetics/RJ45 placement, chassis island, Bob Smith, PHY-side buses (MII/RMII/RGMII). Not here: shared interface rules -> [common.md](common.md); crystals -> [../crystals-clocks.md](../crystals-clocks.md).
Keys: Ethernet, MDI, magnetics, RJ45, Bob Smith, chassis ground, PHY, RGMII, GMII, MII, RMII, DP83867, SNLA387, AN-1469, AN2054, Pulse, PoE
Tags: [P] primary, [S] snippet, [I] inference.

Agreed across TI SNLA387 / AN-1469 / DP83867, Microchip AN2054, Pulse: 100 Ω (±10–15%) MDI, ≤2 vias/trace, void planes under magnetics, chassis island bridged by caps/R/1206 pads, Bob Smith 75 Ω + 1000 pF, digital ≥0.3 in from pairs, magnetics↔RJ45 <1 in.

## Ethernet rules table
| Param | Value | **Conflicts** / notes | Check |
|---|---|---|---|
| MDI impedance | 100 Ω ±10% ([TI SNLA387](https://www.ti.com/lit/pdf/snla387) [P]); 50 Ω to ground / 100 Ω diff ([AN-1469](https://www.ti.com/lit/pdf/snla079)) | 100 Ω ±15% ([Pulse](https://www.farnell.com/datasheets/2699973.pdf) [P]). Pairs closer than 30 mil edge-to-edge lower Zdiff by up to 10 Ω | K + S |
| MDI length | TI SNLA387: total <2 in | Microchip [AN2054](https://ww1.microchip.com/downloads/en/Appnotes/00002054A.pdf): PHY→magnetics <1 in (≤3 in if unavoidable), magnetics→RJ45 <1 in, total <4 in. Pulse: total <4 in. TI forum: PHY→RJ45 ≲3 in [S] | K `length` with `fromTo(PHY, RJ45)` |
| Skew | Intra-pair 20 mil (1G) / 50 mil (10/100) (TI); AN2054: intra <50 mil, inter <600 mil; Pulse: 50 mil (1.25 mm) | Johnson: magnetics + CMC balanced to 1:1000 give a ≈0.1" layout/connector budget | K |
| Vias / stubs | ≤2 per trace, matched (AN2054, Pulse); minimal vias and stubs; ideally no crossover or via (AN-1469) | — | K `via_count (max 2)` |
| Spacing | TI: pairs ≥30 mil apart. Pulse: TX–RX ≥50 mil (100 mil preferred), no digital within 300 mil (7.5 mm). AN2054: others ≥0.3 in, pairs ≥0.3 in apart except near PHY, magnetics, RJ45 | — | K `clearance` |
| **PHY↔magnetics** | **Pulse:** "the distance between them needs to be 25 mm … or greater … considered good design practice for EMI" | **Microchip:** <1 in (≤3 in). **TI:** total MDI <2 in. Opposite directions | G; vendor switch; default soft window: target ~25 mm, error >76 mm [I] |
| Magnetics↔RJ45 | <1 in / <25 mm (all sources) | — | hard |
| Board edge | Pulse: PHY and TX pairs ≥25 mm from PCB edge. Pulse figure: LAN traces ≥1 in from edge (2 in preferred), LAN silicon 1–4 in from connector. "Route traces away from board edges by a distance greater than the trace height above the ground plane" | — | G; K `edge_clearance` |
| Plane voids | SNLA387: void only under in-line parts (magnetics, chokes, AC caps, ESD); 2-layer void standard, all layers automotive; void edge ~20 mil past component; no metal under magnetics on any layer (integrated-magnetics RJ45 excepted). DP83867: void supplies and ground beneath magnetics. AN2054: clear planes from halfway through magnetics to RJ45 (HV barrier, discrete magnetics only) | — | G zone keep-outs |
| Bob Smith | 75 Ω + 1000 pF ≥2 kV (TI; not for PoE). Microchip: 1000 pF 3 kV (or 1500 pF/2 kV), ≥50 mil (1.27 mm) clearance around that cap | — | M + K clearance |
| Chassis | SNLA387: isolate earth ground with ≥20 mil (0.51 mm) keep-out on all layers, bridged by a cap and ≥1 MΩ. AN-1469: never overlap chassis and circuit planes; bridge with two 1206 0 Ω resistors either side of RJ45, replaceable by caps or beads at EMC test. DP83867: 1206 R and C either side of connector. AN2054: 2–3 1206 pads across the void | — | K `clearance` GND↔CHASSIS |
| **ESD location** | **TI SNLA387:** **PHY side** of the magnetics (cable-side common-mode swings) | **Generic (TI SLVA680A):** at the connector. TI contradicts itself; make it a pack parameter | vendor switch |
| PHY details | AN-1469: 49.9 Ω 1% terminations and 0.1 µF near TD/RD pins; MII/RMII ideally <6 in, matched within 2 in; 25 MHz crystal C_L1 ≈ 2·C_L − 7 pF. DP83867: MDI to transformer on same layer; no floating metal or metal between differential traces; ≥4 layers (6 recommended). AN2054: bypass pad-to-via <10 mil. SNLA387: MII <6 in, 50 Ω ±10% | — | M / G |
| RGMII / GMII | [DP83867](https://www.ti.com/lit/ds/symlink/dp83867ir.pdf): 50 Ω; TXD[3:0] and RXD[3:0] skew <11 ps (~60 mil on FR4); length <2 in recommended, <6 in maximum; GMII same lengths | Emit skew in ps | K `skew (max 11ps)`, `length` |

Placer: RJ45 anchored on edge; magnetics within 25 mm (hard); PHY in the soft window (vendor profile picks Pulse vs Microchip); PHY ≥25 mm from board edge where possible.

## Open questions
- PHY↔magnetics distance: Pulse vs Microchip point opposite ways.
- ESD side: TI contradicts itself across two notes.
- No IEEE 802.3 primary text on PCB isolation clearance read.

## Sources
- [interface_rule_packs.md § 4](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md), [rules_highspeed_emi.md § 3, 4](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
- See also [../emc-placement.md](../emc-placement.md), [../diff-pairs.md](../diff-pairs.md).
