# Switching-converter hot loops: membership, measured loop inductance, plane proximity

**TL;DR**
- **Every source ranks the hot loop first.** The hot loop is the set of branches whose current steps from 0 to I at each switching edge. Make it as small as possible, place it first, keep it on one layer, and put a solid plane on the next layer.
- **Membership follows from the topology** (table below). Code can derive it from the netlist; the LLM only confirms the topology from the datasheet.
- **Score loop inductance, not millimetres.** Measured anchors (AN-139, TI SNVA803, EPC) let us estimate nH from area and plane distance, then derive overshoot and efficiency loss.
- **No primary source gives a pass/fail loop area.** Area tiers are our inference and should be soft scores.
- **Exceptions:** supplies of 100 W or more may need an isolated return (Hubing). Vertical loops beat lateral loops on multilayer boards.

## Key facts

**Principle.**
- AN-139 calls the loop carrying fully switched AC current the "hot loop" and the dominant EMI source. The on- and off-cycle loops are not the ones to optimise. CIN sources all the AC currents, and they end at COUT ([AN-139 mirror](https://theengineer.markallengroup.com/production/content/uploads/2015/01/an139f.pdf) [P]).
- After the hot loop, the order is: small SW copper → inductor next to SW → COUT → FB by Kelvin connection at COUT, away from SW and L → one quiet AGND tie.
- Physics: V = L·di/dt. At more than 5 A/ns, 2 nH gives 10 V of overshoot ([TI SLYT682](https://www.ti.com/lit/pdf/slyt682) [P]). 1 nH × 1 A/ns = 1 V.

**Hot-loop membership by topology** [I] (derived from circuit analysis; consistent with AN-139 and [TI SNVA731](https://www.ti.com/lit/an/snva731/snva731.pdf) [P]):

| Topology | Hot loop (place first, tightest) | Not hot (continuous current) | Notes / doc |
|---|---|---|---|
| Buck | CIN_HF+ → HS switch / VIN pin → SW → LS switch or diode / PGND → CIN_HF− | L, COUT | Integrated parts: CIN_HF + PVIN + PGND. CIN_HF is the smallest-package ceramic. [buck.md](buck.md) |
| Boost | LS switch (SW→PGND) → rectifier / HS (SW→VOUT) → COUT_HF → PGND | L, CIN | SNVA731: "the most critical PCB feature". [boost.md](boost.md) |
| Inverting buck-boost | CIN, switch, rectifier and COUT in one series loop | L | Both caps are hot. [buck-boost-sepic.md](buck-boost-sepic.md) |
| 4-switch buck-boost | Input half-bridge + CIN; output half-bridge + COUT | L | One HF cap per half-bridge. |
| SEPIC / Ćuk | Switch → coupling cap → rectifier → COUT → GND → switch | L1, L2, CIN | Inference only. |
| Flyback | Primary, clamp, secondary and bias loops | Output LC post-filter | [flyback-offline.md](flyback-offline.md) |
| Half-bridge gate | Driver OUT → gate → Kelvin source → return; C_BOOT ↔ HB/HS | — | [gate-drive-bootstrap.md](gate-drive-bootstrap.md) |
| LDO | No switching loop | — | Thermal dominates. [ldo.md](ldo.md) |

**Measured loop inductance vs plane distance.** AN-139 Table 1, a 10 × 10 cm loop at 27 MHz [P], VERIFIED by VR:

| Configuration | Plane distance | L | Factor vs 0.12 mm |
|---|---|---|---|
| Single-layer open loop | — | 187 nH | 14.4× |
| Inner-copper shorted loop | — | 141 nH | 10.85× |
| Solid plate | 1.5 mm | 42 nH | 3.23× |
| Rectangle, no overlap | 1.5 mm | 53 nH | 4.08× |
| Thin plane | 0.5 mm | 23 nH | 1.77× |
| Thin plane | 0.27 mm | 21 nH | 1.61× |
| Paper-thin insulation (text says 0.13 mm) | 0.12 mm | 13 nH | 1.0× |

- A next-layer plane on a ≥4-layer board has ">3× less" inductance than a 1.5 mm 2-layer board and ">14× less" than a single-layer board. The mechanism is mirror eddy currents in the plane.
- [Kueck Pt 2](https://www.analog.com/media/en/technical-documentation/technical-articles/Kueck_Layout_power_supply_part_2.pdf) recommends ≥4 layers, because a 2-layer board's shield sits more than 1 mm away.

**Second hot loop.** The INTVCC/driver decoupling loop carries about 20 dB less RF energy than the input-cap loop. Make it small and shield it with a solid next-layer plane (AN-139 p.6; [Kueck Pt 1](https://www.analog.com/media/en/technical-documentation/technical-articles/kueck_layout_power_supply_part_1.pdf)) [P].

**Lateral vs vertical loops.**
- **TI SNVA803** (LM5146-Q1, [PDF](https://www.ti.com/lit/pdf/snva803)) [P]:
  - A lateral loop of about 20 mm² is still >1 nH, even over an L2 image plane.
  - A vertical loop using L2 as the return measures 2 mm² and <500 pH, with about 4 V less overshoot.
  - Four 10 nF 0402/0603 caps at the HS drain, grounded to L2 through multiple 12 mil (0.3 mm) vias.
  - SW polygon = inductor pad + minimum FET connection; SW and BST routed on one layer.
- **EPC** ([WP010](https://epc-co.com/epc/Portals/0/epc/documents/papers/Optimizing%20PCB%20Layout%20with%20eGaN%20FETs.pdf); [slides](https://epc-co.com/epc/Portals/0/epc/documents/presentations/High-Performance%20Layout%20Techniques%20to%20Maximize%20GaN%20Device%20Performance.pdf)) [P]:
  - Raising loop inductance from 0.4 to 2.9 nH costs more than 4% efficiency (1 MHz, 12→1.2 V).
  - Overshoot is 100% of V_in at 1.6 nH vs 30% at 0.4 nH.
  - The "internal vertical" layout, called "optimal", uses the first inner layer as the return. It gives about 65% lower inductance than the best conventional loop, and +0.8% / +1% full-load efficiency over the vertical and lateral loops.
  - A vertical loop's inductance rises by up to 80% when board thickness doubles from 31 to 62 mil.
  - Lateral loops depend on shield distance: 4, 12 and 26 mil were tested, and 4 mil was best.
  - Benchmark loops: Si MOSFET about 2 nH, eGaN about 1 nH.
- **DTU** ([IAS 2020](https://orbit.dtu.dk/files/236953218/IAS_accepted_PCB_for_GaN_2020.pdf)) [S] prefers vertical loops on multilayer boards, but notes they are harder to characterise (via effects).
- **TI SLYT682** [P]: use a minimum-thickness shield dielectric (for example a 5-mil core) and avoid vias in the hot loop, so noise current stays on the top layer.

**Loop-area thresholds.**

| Threshold | Value | Evidence |
|---|---|---|
| Anchors | 20 mm² lateral → >1 nH; 2 mm² vertical → <0.5 nH | SNVA803 [P] |
| Tiers (IRP §8) | ≤2 mm² excellent, ≤10 mm² acceptable, >20 mm² fail | [I] |
| Blog target | <10 mm² | [embeddedhardwaredesign](https://embeddedhardwaredesign.com/dc-dc-buck-converter-pcb-layout-design-guidelines/) [V] |
| Boost target | <1 cm² | [Firgelli calculator](https://www.firgelliauto.com/blogs/engineering-calculators/boost-converter-calculator) [V] |
| `max_mm2: 15` | YAML example in RPA | Unsourced |

**Edge rate.** LearnEMC: transition times longer than about 1% of the switching period noticeably reduce efficiency [P]. Slowing edges (for example a series bootstrap resistor) trades efficiency for EMI ([Richtek AN045](https://www.richtek.com/Design%20Support/Technical%20Document/AN045)) [S].

## Recommendations for our system
- **Hot-loop detector:** topology classifier (see [../checkers-power.md](../checkers-power.md)) → the member list from the table → an ordered pad polygon.
- **Loop-inductance estimator:**
  - Inputs: area, L1→L2 dielectric, via count.
  - Calibrate on the AN-139, SNVA803 and EPC data.
  - Report nH, overshoot = L_est × di/dt (warn if >0.2 × V_DS,max, IRP §11), and EPC-style efficiency impact.
- **Hard constraints:** same layer, 0 vias in the loop, a solid GND zone under the loop hull + 1 mm on the next layer.
- **Soft constraints:** area tiers. Never treat a millimetre number as DRC.
- **Rank priorities:** the INTVCC/driver loop second.
- **Stack-up advice:** ≥4 layers with an L1–L2 dielectric ≤0.127 mm under power stages (soft, strong); prefer vertical loops when there is room.

## Conflicts and open questions
- **Hubing** ([LearnEMC](https://learnemc.com/not-so-good-emc-design-guidelines)) [P]: the "one layer over an adjacent plane" advice "can be misleading … supplies generating 100 Watts or more may require an isolated return". This needs a power-level context switch.
- **No primary loop-area limit.** EPC's 0.4 vs 1.6 nH and AN-139's 13 vs 187 nH are performance data, not limits (VR §3).
- **The estimator is uncalibrated.** Calibrate it on vendor eval-board layouts.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 1, § 20](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B, § 2, § 3](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [interface_rule_packs.md § 8](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
- primary: AN-139, SNVA803, EPC WP010, SLYT682, SNVA731 (linked above)

See also: [buck.md](buck.md), [boost.md](boost.md), [../checkers-power.md](../checkers-power.md), [../decoupling-pdn.md](../decoupling-pdn.md)
