# Expert placement methodology (power/RF/analog perspective) and practitioner input

**TL;DR**
- **Experts place in order of constraint rigidity:** mechanical → stack-up and plane plan → anchor ICs → critical sub-circuits as rigid templates → decoupling → signal flow → DFM pass → route critical nets first.
- **Template-first, then global.** Locally optimised macros for critical blocks, then a global placer with cost = ratsnest + crossings + severity-weighted violations (S1 ≫ S2 ≫ S3).
- **Score placement before routing** (ratsnest length, crossings, congestion, violation counts), so iteration is cheap. Altium's "90% placement, 10% routing" is self-described as debatable.
- **Knowing which circuits are critical is tacit expertise (Pease).** The LLM's highest-value job is producing a reviewable criticality map.
- **Following rules blindly is itself a failure mode (Hubing).** Every rule needs scope and rationale.

## Key facts

**Order of operations** (RPA §7 synthesis of [EMA](https://www.ema-eda.com/ema-resources/blog/best-practices-for-pcb-component-placement-emd/), [Sierra](https://www.protoexpress.com/kb/pcb-component-placement-rules/), SLYT614) [S]/[I]:
1. **Board and mechanical:** outline, mounting holes and keep-outs, connectors at fixed edge coordinates, user-facing parts (buttons, LEDs, displays), height zones, antenna/module edge placement + keep-out polygons. Lock them.
2. **Stack-up and plane plan:** GND plane under all critical circuits; which rails become planes or pours; analog/digital/RF/power regions, with connectors feeding their own regions (I/O near connectors, Ott-style partitioning).
3. **Anchor ICs:** main MCU/SoC/FPGA, oriented so pin groups face their peripherals (fewer ratsnest crossings); reserve the fan-out area.
   - BGA central for equal access on all sides ([PCBWay](https://www.pcbway.com/blog/PCB_Design_Layout/BGA_PCB_Layout_Guidelines_Placement_Fanout_and_Routing_b8eeabdd.html)).
   - Fan-out: dog-bone for pitch ≥0.8 mm, plated-over via-in-pad for ≤0.65 mm; outer rows escape on top, inner rows on inner layers; power and ground pins first ([AtlasPCB](https://www.atlaspcb.com/blog/bga-fanout-routing-strategies-dog-bone-via-in-pad/); [Altium](https://resources.altium.com/p/which-bga-pad-and-fanout-strategy-right-your-pcb)).
4. **Critical sub-circuits as rigid templates:** switching converters (hot loop first, [power/hot-loops.md](power/hot-loops.md)), crystal and oscillator ([crystals-clocks.md](crystals-clocks.md)), RF chain and matching ([rf.md](rf.md)), ADC front end and reference, current-sense shunts. Each placed as a unit near its consumer or I/O.
5. **Decoupling** at each power pin with vias at the pads, before general routing ([decoupling-pdn.md](decoupling-pdn.md)).
6. **Remaining parts by signal flow:** connector → ESD (at the connector) → filter → transceiver/buffer → IC; schematic hierarchy sheets as clusters.
7. **DFM pass:** orientation normalisation, courtyards, fiducials, test points, silk ([dfm-fab-limits.md](dfm-fab-limits.md)).
8. **Route order:** power hot loops and RF (manual quality, frozen) → sensitive analog/feedback → clocks and HS pairs → general signals → pours, stitching, fences → DRC + custom checks.

Converter micro-order (generalises): IC → CIN (route immediately) → L/SW (+snubber) → COUT/VOS → small-signal → ground tie (SLYT614).

**Practitioners** (RPA §19):
- **Feranec** (FEDEVEL Advanced PCB Layout, via a [student review](https://helentronica.com/2017/05/03/advanced-pcb-layout-course-by-fedevel-academy/)) [S]:
  - "Put big components first, leave some room between MPU and DDRs, put the high current components as far as" possible.
  - Decoupling under the BGA, iterated with fan-out. Termination resistors at the main component; EMI and ESD parts at the connectors. Use 3-D models.
  - Fan-out: power pins first with 0.3 mm through vias to bottom-side caps. "One and only one via per each power pad. Don't share a power via among the tracks of the same net!"
  - Then data with microvias. DDR first and shortest, inner pads first; on the DDR chip, data fans outward and address inward; one topology per group; fan out every BGA pad.
  - Rules quoted: 20H for power planes, via aspect ratio ≤10.
  - Read the vendor layout guide first (NXP DDR3 order: address, differential pairs, control, data); route groups "piece by piece" from both ends.
  - FEDEVEL tip [S]: extra silk on connectors and slots.
  - A community tips list attributed to him ("smaller cap closer", 10 µF + 100 nF pairs, connectors on one edge) is third-party; compare the myths in [decoupling-pdn.md](decoupling-pdn.md).
- **Phil's Lab** [P course outlines / S summaries]:
  - Rough placement first, then section-by-section refinement, with decoupling and crystal placement as separate steps.
  - 2-layer: all parts on one side with solid ground on the other; minimise vias that cut the reference.
  - No splits under traces; decoupling close with short, wide traces and clustered power vias.
  - Advanced course: grounding, sectioning, crosstalk, stack-up, PDN for QFP/QFN/BGA, DDR3 fly-by, GbE, USB HS/eMMC ([courses](https://www.phils-lab.net/courses)).
- **Bob Pease**, "What's All This Layout Stuff, Anyhow?" (2008, [Lab Notes Pt 7](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/1023/Bob-Pease-Lab-Notes-Part-7.pdf)) [P]:
  - CAD advocates "did not want to talk about thermals. Or crosstalk. Or good grounds, even."
  - Hurried layouts gave "hot transistors … adjacent to critical transistors. Noisy busses laid out alongside (or on top of!) critical analog circuits."
  - "The art of knowing which circuits are critical isn't always written down, codified, or quantified … wrapped up in the heads of experts."
- **Jim Williams** AN47 (1991, [mirror](https://www.mit.edu/~6.331/an47fa.pdf)) [P]:
  - Ground-plane as much area as possible, especially under HF traces.
  - Mount fast-current parts (terminations, ICs, transistors, decoupling) as close to the board as possible.
  - Single-point critical components (comparator inputs) into the plane where common potential matters.
  - Keep traces short.
  - Probe ground leads ≤1 in; coaxial board-mounted probe points are best.
- **Hubing** (2019, [slides](https://r6.ieee.org/scv-emcs/wp-content/uploads/sites/111/022019ToddHubing.pdf)) [P], seven common errors: blindly following guidelines; uncontrolled transition times; not following currents; not identifying critical traces; more than one "ground"; improper decoupling; inadvertently bypassing filters.

## Recommendations for our system
- **Implement the 8-step order as the agent's state machine.** Lock mechanical parts; emit templates for critical blocks; run a global placer with severity-weighted penalties.
- **Region partitioning:** each schematic block gets a region (power, analog, digital, RF, HV). Penalise cross-region nets except at designated boundary parts (ADCs, isolators, connectors). Keep hot loops a soft distance from RF and analog regions.
- **Route critical nets first and freeze them** (hot loops, SW, RF, Kelvin sense, crystal). Then general routing, then pours, stitching and fences, then re-run all checks.
- **Generate the criticality map before any geometry** ([checkers-power.md](checkers-power.md)).
- **Feranec's fan-out rules become generator constraints** (one via per power pad, never shared; DDR inner pads first). 20H is optional/soft, not a default ([datasheet-to-constraints.md](datasheet-to-constraints.md)).

## Conflicts and open questions
- **Physics-first challenge (2026-10-22):** a fixed placement order is replaced by least-slack-first priorities, τ = budget ÷ achievable floor, computed per board inside one joint placement+routing optimizer. The expert order reappears only where the physics agrees. See [design-reasoning-architecture](../physics/design-reasoning-architecture.md) and [joint-place-route](../physics/joint-place-route.md).
- **Feranec's method** is known only through a student review and blog snippets. No Phil's Lab transcripts were read. Pease's common-centroid column was not retrieved.
- **The 20H rule** is contested (Montrose vs Shim/Hubing).

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 7, § 19, § 20](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 2, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [checkers-power.md](checkers-power.md), [datasheet-to-constraints.md](datasheet-to-constraints.md), [power/buck.md](power/buck.md)
