# Gate drive, bootstrap and driver-supply decoupling

**TL;DR**
- **Driver next to the FET.** Gate and return are routed as a pair, wide and short. The Kelvin source return is top priority, because common-source inductance causes false turn-on and ringing.
- **EPC overshoot-free criterion:** L_G ≤ ¼·(R_G + R_Source)²·C_GS.
- **Bootstrap (CORRECTED):** C_boot **≥** 10 × C_g and C_VDD **≥** 10 × C_boot. These are minimums, not "about 10×". Place them at the driver pins with the smallest cap nearest.
- **The driver-supply (INTVCC) loop is a second hot loop,** about 20 dB below the input loop.
- **Edge-rate control** (series bootstrap R) is a deliberate EMI-vs-efficiency knob.

## Key facts
- **EPC WP008** ([PDF](https://epc-co.com/epc/Portals/0/epc/documents/papers/eGaN%20FET%20Drivers%20and%20Layout%20Considerations.pdf)) [P], VERIFIED + formula:
  - Avoid "long narrow leads … by widening and shortening the traces".
  - Overshoot is avoided if L_G ≤ ¼·(R_G + R_Source)²·C_GS.
  - "CSI [common-source inductance] is more important to eGaN FETs … should be minimized through careful layout".
- **TI SLUAAM3 and SLYP754** ([SLUAAM3](https://www.ti.com/lit/pdf/sluaam3); [SLYP754](https://www.ti.com/lit/ml/slyp754/slyp754.pdf)) [P]:
  - "Place the FETs close to the driver"; the driver output ground and power FET source path "as short as" possible; minimal driver output loop.
  - GaN: two VDD bypass caps, the smaller nearest the IC; boot cap close to the HB/HS pins; input-side RC parts close to LI/HI.
- **Bootstrap sizing** ([TI SLUA887A p.3–4, p.7](https://www.ti.com/lit/pdf/slua887)) [P], CORRECTED by VR: "This bootstrap cap should be **at least** 10 times greater than the gate capacitance … without being depleted by more than 10%"; "CVDD ≥ 10 × CBoot"; place "as close as possible to the gate driver supply pins".
- **AN-136** (EDN reprint) [S]: give the top-FET gate trace and the SW trace a minimal shared loop area; run the bottom-FET gate trace next to a PGND trace; keep current-sense traces away from switching nodes.
- **Motor predrivers** ([TI SLVA959B](https://www.ti.com/lit/pdf/slva959)) [P]: gate traces start at 20 mil for 1 oz; route the HS gate trace as close as possible to the SW (SHx) trace; see [motor-drivers.md](motor-drivers.md).
- **Half-bridge gate loop** [I]: driver OUT → gate → Kelvin source → driver return; bootstrap loop C_BOOT ↔ HB/HS. The gate loop must not share power-source inductance.
- **INTVCC loop:** AN-139 measured >20 dB less RF energy than the input-cap loop, so it ranks second. Shield it with a solid plane on the next layer ([hot-loops.md](hot-loops.md)).
- **Edge-rate trade:** a series resistor in the bootstrap path lowers dV/dt and EMI at an efficiency cost ([Richtek AN045](https://www.richtek.com/Design%20Support/Technical%20Document/AN045)) [S].

**Rules** (RPA §1):

| ID | Rule | Check | Class |
|---|---|---|---|
| PWR-11 | Driver adjacent to the FET; gate and return paired; Kelvin source pin used | Gate trace length; gate/return separation; Kelvin pin connected | S1, VERIFIED |
| PWR-12 | Boot cap at BOOT/SW, VDD bypass at the driver pins, smallest nearest; C_boot ≥10 C_g, C_VDD ≥10 C_boot | Pad distance + schematic value check | S2, soft strong |
| MOT-03 | Gate ≥20 mil @ 1 oz, paired with SHx / LS source | Parallel-run coupling; width | S2 |

## Recommendations for our system
- **Schematic (BOM) check** of the bootstrap and VDD ratios, using the FET Q_g/C_g from datasheets (LLM extraction, code compare).
- **Treat gate and return as a pseudo differential pair** (coupled routing). Verify the Kelvin source pin is used when the FET has one.
- **Add the INTVCC/VDD decoupling loop** as a second `loop_area` constraint, ranked after the main hot loop.
- **Compute the EPC L_G bound** from extracted R_G and C_GS, and compare it with estimated trace inductance.

## Conflicts and open questions
- **No numeric gate-trace length limit** exists beyond "wide, short" and the EPC inequality.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 1, § 11](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B, § 2](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [hot-loops.md](hot-loops.md), [motor-drivers.md](motor-drivers.md), [buck.md](buck.md)
