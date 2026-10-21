# Buck converter layout rules

**TL;DR**
- **Placement order (TI SLYT614):** IC → CIN (route it immediately, no vias) → L with minimal SW copper (+ snubber) → COUT and VOS → small-signal parts (EN/PG last) → single-point ground. Datasheet ordered lists override this.
- **CIN distance:** MPS's "<2 mm" is the only numeric primary CIN distance. Other vendors say "every millimetre matters". Hard-gate the topology (same layer, 0 vias); soft-score the distance.
- **FB/VOS** is Kelvin-sensed at the COUT pad, kept off the power plane, never under L or beside SW on any layer. No vendor gives a numeric clearance.
- **AGND/PGND** join once, at the EP or the datasheet point; TPS62130 calls this "mandatory".
- **Contested defaults** need a context switch: copper under the inductor, CIN/COUT ground separation, PMIC ground cuts.

## Key facts

**Numeric quick reference** ([interface_rule_packs.md § 8](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md), cross-checked with VR):

| Item | Value | Source |
|---|---|---|
| HF input cap to IC | **<2 mm** (VCC cap also <2 mm, same layer, no via) | [MPS AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf) [P] |
| Power vias | 10 mil drill / 20 mil pad; 1–2 per VIN/PGND pin (NB670/1), ≥3 (NB675); >20 between the input caps; ≥1 per A (TI) | MPS AN065; [TI SLYT614](https://www.ti.com/lit/an/slyt614/slyt614.pdf) [P] |
| Bulk CIN | may sit ~2 cm from CBYPASS (0.1–0.47 µF) | [Rohm 60AN066E](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf) [P] |
| CIN vs COUT ground | Rohm: **1–2 cm apart**. TI/MPS: short common return. **CONTESTED** | Rohm, [TI SNVA803](https://www.ti.com/lit/pdf/snva803), MPS [P] |
| Power trace width | **>1 mm/A (1 oz)**, >0.7 mm/A (2 oz); 2 A → 0.53 mm for a 20 °C rise | Rohm [P] |
| Thermal vias | **0.3 mm ID at ~1.2 mm pitch** (TI/Renesas: 0.3 mm at 1.0–1.2 mm) | Rohm [P]; [../thermal.md](../thermal.md) |
| SW trace width | ≤100 mil (2.54 mm) | [TI LM10504](https://ti.com/document-viewer/LM10504/datasheet/layout) [P] |
| Loop anchors | SNVA803: ~20 mm² lateral >1 nH; 2 mm² vertical <0.5 nH, ~4 V less overshoot. EPC: 0.4→2.9 nH costs >4% efficiency; overshoot 100% of V_in at 1.6 nH vs 30% at 0.4 nH. AN-139: 187 nH single-layer → 13 nH with a plane 0.12 mm below; next-layer plane >3× better than a 1.5 mm 2-layer board | [SNVA803](https://www.ti.com/lit/pdf/snva803); [EPC WP010](https://epc-co.com/epc/Portals/0/epc/documents/papers/Optimizing%20PCB%20Layout%20with%20eGaN%20FETs.pdf); [AN-139](https://theengineer.markallengroup.com/production/content/uploads/2015/01/an139f.pdf) [P]. Detail: [hot-loops.md](hot-loops.md) |
| Overshoot | 5 A/ns × 2 nH = 10 V | [TI SLYT682](https://www.ti.com/lit/pdf/slyt682) [P] |
| L1–L2 dielectric | ≤0.127 mm (5 mil) | SLYT682 [P] |
| Loop tiers | ≤2 mm² excellent, ≤10 mm² acceptable, >20 mm² fail | [I], anchored on SNVA803 |

**Order and CIN.**
- **SLYT614** ([PDF](https://www.ti.com/lit/an/slyt614/slyt614.pdf)) [P], VERIFIED:
  - CIN is "the first component placed in the layout after the IC. Route the capacitor to the IC immediately"; "as close to the IC as allowed by manufacturing rules"; "no vias".
  - Keep all components on one side.
  - Put system vias "outside the circuit, versus between the input capacitor and IC".
  - Route quiet-component grounds directly back to AGND rather than via'ing them into the plane.
  - EN/PG are "the least important … do these last".
- **WCSP exception** (SLYT614 p.3–4) [P], VERIFIED+CTX: when SW sits between VIN and PGND, route SW underneath the input cap. Vias in the SW→L path are "a better choice than moving the input capacitor".
- **Distances:**
  - MPS AN065 says "<2 mm distance from the Chip" for the input cap. The VCC cap is also <2 mm, on the same layer with no via ([AN065](https://media.monolithicpower.com/document/PCB_Layout_Design_Guidelines_for_NB67xSeries.pdf)) [P].
  - SLVA818: "Every millimeter makes a difference!" ([SLVA818](https://www.ti.com/lit/pdf/slva818)) [P]. Rohm: "Shortening the wiring even by 1 mm is highly recommended" [P].
- **MPS via counts** [P]:
  - VIN/PGND on ≥2 layers with 10 mil drill / 20 mil pad vias: 1–2 under each pin on NB670/1, ≥3 on NB675; >20 vias between the two input caps.
  - VCC cap: ≥4 vias to AGND and 8 to PGND (NB675).
  - ≥4 layers, with Inner1 used only for PGND.
- **Rohm 60AN066E Rev.004** ([PDF](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf)) [P]:
  - CBYPASS is 0.1–0.47 µF X5R/X7R at the IC on the top layer; bulk CIN may sit about 2 cm away.
  - Never put CBYPASS on the reverse side through vias ("operates as a reverse effect"), and never put the freewheel diode on the bottom through vias.
  - The inductor should be close, but there is "no need to be as close as input capacitor".
  - Via inductance: L ≈ (h/5)(ln(4h/d)+1) nH (Johnson).
- **AN-136** (Zhang; [mirror](https://docs.ampnuts.ru/analog.com.datasheet/ltc3729l-6/related_data/an136f.pdf)) [P from mirror; VR verified only via snippet]:
  - Power stage first, small-signal after. C_HF is a 0.1–10 µF low-ESL ceramic.
  - Power parts on one side, power traces on one layer. Change layers only in continuous-current paths, never in the hot loop, and with multiple vias.
  - "Always have a ground layer next to the outside power stage layer". Ground or DC planes go between the power and small-signal layers. Never segment planes. Thick outer copper.
  - No thermal-relief pads or vias on power parts. Keep each cap's ± vias close together.
  - The controller sits near VOUT+, away from the hot loop, decoupled at its pins with no vias.
  - Multiphase [S]: one 1 µF HF cap per phase kept waveforms stable to 30 A.
- **≥1 via per amp** (SLYT614: "more is better") for power vias. They go outside the CIN–IC path (VR +CTX).

**Switch node.**
- Minimise it:
  - SLYT614: "All copper connected to the SW node is one plate of a parasitic capacitor".
  - Rohm: an enlarged SW area "may work as an antenna".
  - [TI SLYT682](https://www.ti.com/lit/pdf/slyt682): short, wide pour with a full ground plane under SW on multilayer boards.
  - AN-136: ground under SW adds shielding.
  - No source gives a numeric area.
- A SW trace wider than 100 mil (2.54 mm) "cause[s] too much capacitive loading" ([TI LM10504](https://ti.com/document-viewer/LM10504/datasheet/layout)) [P].
- SW copper on one layer only ("Do not use multiple layers in parallel", [BQ25895](chargers-bms.md)) [P].
- Cooling vs EMI conflict ([USPTO 10763221](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10763221)): cool through PGND/EP vias, never by enlarging SW copper (Rohm; [HS Electronik](https://hs-electronik.com/news/buck-converter-pcb-layout-hot-loops-feedback-guide) [V]).
- RC snubber: "the shortest possible routing between the SW and PGND pins" (SLYT614 gives no values, [E2E](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/927858/tps62130a-snubber)). Rohm: put it at the IC SW/GND terminals; "Placing it at the both ends of diode will not absorb spike noise." The freewheel diode goes on the same surface, close to the IC.

**Inductor.**
- **Dot on SW** gives up to 8 dB lower E-field emissions; the outer winding at VOUT shields the inner one. H-field is unaffected.
  - VR +CTX: measured on **one shielded WE-LHMI 74437368022** ([ANP047 republication](https://www.powersystemsdesign.com/articles/the-behavior-of-electromagnetic-radiation-of-power-inductors-in-power-management/22/11575)) [P].
  - Shielding is magnetic only, so orientation still matters ([NextPCB](https://www.nextpcb.com/blog/shielded-vs-unshielded-inductors-emi-pcb-placement)) [V].
  - A DigiKey forum thread dissents; it is not a measurement.
- **No sensitive nets under or next to the inductor or SW on any layer.** TI SPRAAR7J also forbids high-speed traces "under or near … switching power regulators … magnetic devices" ([SPRAAR7J p.9](https://www.ti.com/lit/pdf/spraar7)) [P].

**Feedback.**
- TPS62130 ([DS p.28](https://www.ti.com/lit/ds/symlink/tps62130.pdf)) [P]: "connect the VOS pin in the shortest way to VOUT at the output capacitor … separated from the VOUT power line/plane". SLYT614: VOS is "the most critical small-signal connection".
- MPS: FB resistors "next to the FB PIN … Do not connect FB to these resistors through vias". R2 goes to AGND, R1 to COUT at the regulation point.
- Rohm: "Do not wire directly below the inductor and diode, and not parallel to power supply line."
- LM5163 / TPS560430 [S]: route the FB trace on another layer, shielded by GND, especially when R_FB > 100 kΩ.
- No vendor gives a numeric SW-to-FB clearance (IRP §8). The ≥1–2 mm clearance and "divider ≤2–3 mm" figures are [I] heuristics.

**Grounds.**
- TPS62130: "the direct common connection of AGND and PGND to the exposed thermal pad and the system ground (ground plane) is **mandatory**". SLYT614: join at a single point, typically the EP.
- MPS: AGND–PGND link close to the VCC decoupling cap, with ≥2 vias.
- AN-136: one SGND–PGND link under the controller; solder the EP with multiple vias.
- A small AGND pour around the FB parts, not shared with PGND returns ([SchematicsHub](https://schematicshub.com/articles/buck-layout)) [V].
- "Star ground everything" is context-dependent. On multilayer boards, a plane + local hot loop + AGND island + single tie works; a literal star of traces adds inductance [I].

**PMIC.** Renesas DA9080 ([AN](https://www.renesas.com/en/document/apn/da9080-pcb-layout-recommendations)) [P]: input caps on the device layer; L2 as the power-GND return, **with GND cuts between bucks**; output current on the top layer without vias.

**Rule IDs** (RPA §1; full classes in [../datasheet-to-constraints.md](../datasheet-to-constraints.md)):

| ID | Rule | Class |
|---|---|---|
| PWR-01 | CIN_HF first, IC layer, 0 vias; ≤2 mm (MPS) | Topology hard; distance soft |
| PWR-02 | Solid GND on the next layer, ≤0.127 mm | Soft, strong ([hot-loops.md](hot-loops.md)) |
| PWR-03 | SW area ≤ k × (SW pads + L pad) | Soft |
| PWR-04 | Inductor dot on SW (needs a footprint pin-1 = dot convention) | Soft, +CTX |
| PWR-05 | Sensitive keep-out = L courtyard + 1–2 mm, all layers | S1 for FB; distance [I] |
| PWR-06 | FB/VOS sensed at the COUT pad | Hard |
| PWR-07 | One AGND–PGND net tie at the EP | Hard where "mandatory" |
| PWR-08 | COUT GND near CIN GND | CONTESTED, removed as a default |
| PWR-10 | ≥ceil(I) vias in parallel arrays | Soft, strong |
| PWR-13 | Snubber loop {R, C, switch pins} tight | Soft |
| PWR-17 | FB/comp parts outside the SW/L half-plane (angular-sector test) | [I] |

**IRP `buck_sync` rule pack** (precedence 20), summarised:
- **Roles:** `cin_hf` ≤1 µF on VIN/PGND, preferring the smallest package; `cin_bulk` >1 µF; `ind` on SW; `cout`; `rfb_top` / `rfb_bot`.
- **Parameters:** cin ≤2 mm (hard window); bulk ≤20 mm; loop 2 / 10 / 20 mm²; di/dt 5 A/ns; L1–L2 ≤0.127 mm; 1 via/A; 1 mm/A; SW width ≤2.54 mm; FB ≤3 mm [I].
- **Placement:** priority order; same side; F.Cu keep-out ring around the inductor.
- **Routing:** SW = pad + minimum link, 0 vias. FB with 0 vias, on a different layer from SW, shielded, not parallel to SW or VIN.
- **Override:** a datasheet reference layout (precedence 40) sets the target loop area measured from the eval board.

## Recommendations for our system
- **Emit the SLYT614 order as `placement_priority`.** Parse datasheet ordered lists and let them override.
- **Hard-gate the topology** (CIN on the IC layer, 0 hot-loop vias, FB from the COUT pad, tie count = 1). Soft-score distances with the [loop-inductance estimator](../checkers-power.md).
- **Pre-assign net classes** `PWR_HOT`, `SW` and `SENSITIVE` (FB/COMP/RT/SS) and emit DRU clearance SENSITIVE↔SW ≥1 mm as a soft default.
- **Check the inductor dot net** only when the footprint follows the pin-1 = dot convention.

## Conflicts and open questions
- **CIN/COUT ground separation.**
  - Rohm: "separated from each other by at least 1cm to 2cm", because several hundred MHz reaches the CIN ground even with CBYPASS close.
  - MPS: output-cap GND "close to the IC's PGND".
  - TI SNVA803: U-shaped layout with a short common return.
  - CONTESTED; not a default.
- **Copper under the inductor.**
  - TI SLYT682: top-layer keep-out to limit SW→VOUT coupling, with L2 GND kept.
  - Rohm: "Not placing ground layer directly below the inductor" (eddy currents lower L and raise loss).
  - Hubing: a plane under some chokes is "not a good idea".
  - Context switch. The IRP pack uses an F.Cu keep-out ("stricter").
- **TI internal tension:** the TPS62130 datasheet ties the FB resistors straight to the system plane, while SLYT614 says not to via quiet grounds into it.
- **PMIC ground cuts** (DA9080) conflict with the one-ground doctrine. Honour them only when the datasheet mandates them.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 1, § 7, § 8](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B, § 2](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [interface_rule_packs.md § 8, § 11](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)

See also: [hot-loops.md](hot-loops.md), [gate-drive-bootstrap.md](gate-drive-bootstrap.md), [current-sense-kelvin.md](current-sense-kelvin.md), [../thermal.md](../thermal.md), [../datasheet-to-constraints.md](../datasheet-to-constraints.md)
