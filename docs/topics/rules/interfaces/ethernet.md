# Ethernet 10/100/1000BASE-T (MDI, magnetics, PHY placement, Bob Smith) and RGMII/MII

*Tags: [P] = primary source read; [S] = snippet only; [I] = our inference.*

**TL;DR**
- **Points of agreement** across four primary vendors (TI SNLA387 / AN-1469 / DP83867, Microchip AN2054, Pulse):
  - 100 Ω (±10–15%) MDI pairs;
  - ≤2 vias per trace;
  - void the planes under the magnetics;
  - a chassis island bridged by caps, resistors or 1206 pads;
  - Bob Smith termination of 75 Ω + 1000 pF (≥2 kV per TI, 3 kV per Microchip);
  - digital signals kept ≥0.3 in from the pairs.
- **Conflict: PHY↔magnetics distance.** Pulse says ≥25 mm "for EMI". Microchip says <1 in (≤3 in max). TI says total MDI <2 in. Model it as a **soft window**: target about 25 mm, error above 76 mm.
- **Agreed: magnetics↔RJ45 <1 in.**
- **Conflict: ESD location.** TI's Ethernet note puts ESD on the PHY side of the magnetics. The generic rule (also TI) puts it at the connector. Make this a pack parameter.
- **RGMII (DP83867):** 50 Ω; TXD/RXD skew <11 ps (~60 mil); <2 in recommended, <6 in maximum.
- **Board edge:** keep the PHY and TX pairs ≥25 mm from the edge (Pulse).

## Key facts
| Param | Value | **Conflicts** / notes | Check |
|---|---|---|---|
| MDI impedance | 100 Ω ±10% ([TI SNLA387](https://www.ti.com/lit/pdf/snla387) [P]); 50 Ω to ground / 100 Ω diff ([AN-1469](https://www.ti.com/lit/pdf/snla079)) | 100 Ω ±15% ([Pulse](https://www.farnell.com/datasheets/2699973.pdf) [P]). Pairs closer than 30 mil edge-to-edge lower Zdiff by up to 10 Ω | K + S |
| MDI length | TI SNLA387: total <2 in | Microchip [AN2054](https://ww1.microchip.com/downloads/en/Appnotes/00002054A.pdf): PHY→magnetics <1 in (≤3 in if unavoidable), magnetics→RJ45 <1 in, total <4 in. Pulse: total <4 in. TI forum: PHY→RJ45 ≲3 in [S] | K `length` with `fromTo(PHY, RJ45)` |
| Skew | Intra-pair 20 mil (1G) / 50 mil (10/100) (TI); AN2054: intra <50 mil, inter <600 mil; Pulse: 50 mil (1.25 mm) | Johnson: magnetics + CMC balanced to 1:1000 give a ≈0.1" layout/connector budget | K |
| Vias / stubs | ≤2 per trace, matched (AN2054, Pulse); minimal vias and stubs; ideally no crossover or via (AN-1469) | — | K `via_count (max 2)` |
| Spacing | TI: different pairs ≥30 mil apart. Pulse: TX–RX ≥50 mil (100 mil preferred), no digital signal within 300 mil (7.5 mm). AN2054: others ≥0.3 in, pairs ≥0.3 in apart except near the PHY, magnetics and RJ45 | — | K `clearance` |
| **PHY↔magnetics** | **Pulse:** "the distance between them needs to be 25 mm … or greater … considered good design practice for EMI" | **Microchip:** <1 in (≤3 in). **TI:** total MDI <2 in | G; vendor switch; default soft window 25–76 mm [I] |
| Magnetics↔RJ45 | <1 in / <25 mm (all sources) | — | hard |
| Board edge | Pulse: PHY and TX pairs ≥25 mm from the PCB edge. A Pulse figure suggests LAN traces ≥1 in from the edge (2 in preferred) and LAN silicon 1–4 in from the connector. "Route traces away from board edges by a distance greater than the trace height above the ground plane" | — | G; K `edge_clearance` |
| Plane voids | SNLA387: void only under in-line parts (magnetics, chokes, AC caps, ESD); 2-layer void for standard designs, all layers for automotive; void edge ~20 mil past the component; no metal under the magnetics on any layer (integrated-magnetics RJ45 excepted). DP83867: void supplies and ground beneath the magnetics. AN2054: clear planes from halfway through the magnetics to the RJ45 (HV barrier, discrete magnetics only) | — | G zone keep-outs |
| Bob Smith | 75 Ω + 1000 pF ≥2 kV (TI; not for PoE). Microchip: 1000 pF 3 kV (or 1500 pF/2 kV), with ≥50 mil clearance around that cap | — | M + K clearance |
| Chassis | SNLA387: isolate earth ground with a ≥20 mil keep-out on all layers, bridged by a cap and ≥1 MΩ. AN-1469: never overlap chassis and circuit planes; bridge with two 1206 0 Ω resistors on either side of the RJ45, replaceable by caps or beads at EMC test. DP83867: 1206 R and C on either side of the connector. AN2054: 2–3 1206 pads across the void | — | K `clearance` GND↔CHASSIS |
| **ESD location** | **TI SNLA387:** protection on the **PHY side** of the magnetics, because of common-mode swings on the cable side | **Generic (TI SLVA680A):** at the connector | vendor switch |
| PHY details | AN-1469: 49.9 Ω 1% terminations and 0.1 µF near the TD/RD pins; MII/RMII ideally <6 in, matched within 2 in; 25 MHz crystal C_L1 ≈ 2·C_L − 7 pF. DP83867: MDI routed to the transformer on the same layer; no floating metal or metal between differential traces; ≥4 layers (6 recommended). AN2054: bypass pad-to-via <10 mil. SNLA387: MII <6 in, 50 Ω ±10% | — | M / G |
| RGMII / GMII | [DP83867](https://www.ti.com/lit/ds/symlink/dp83867ir.pdf): 50 Ω; TXD[3:0] and RXD[3:0] skew <11 ps (~60 mil on FR4); length <2 in recommended, <6 in maximum; GMII uses the same lengths | — | K `skew (max 11ps)`, `length` |

## Recommendations for our system
- **Placer.**
  - Anchor the RJ45 on the edge.
  - Magnetics within 25 mm (hard).
  - PHY in a soft window from the magnetics: target ~25 mm, error >76 mm. Use the vendor profile to choose Pulse vs Microchip.
  - PHY ≥25 mm from the board edge where possible.
- **Zones.**
  - Plane voids under the magnetics and in-line parts.
  - Chassis island keep-out ≥0.51 mm on all layers.
  - Bob Smith cap with ≥1.27 mm clearance.
- **ESD location.** Make it a pack parameter.
- **RGMII.** Emit skew in ps.

## Conflicts and open questions
- **PHY↔magnetics distance.** Opposite directions (Pulse vs Microchip).
- **ESD side.** TI contradicts itself across two notes.
- **Missing source.** No IEEE 802.3 primary text on PCB isolation clearance was read.

## Sources
- Research notes: [interface_rule_packs.md § 4](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md), [rules_highspeed_emi.md § 3, 4](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)

See also:
- [../emc-placement.md](../emc-placement.md)
- [../diff-pairs.md](../diff-pairs.md)
- [../crystals-clocks.md](../crystals-clocks.md)
