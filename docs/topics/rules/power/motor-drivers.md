# Motor drivers and H-bridges

**TL;DR**
- **Critical loop:** supply+ → HS FET → winding → opposite LS FET → supply−, plus the per-half-bridge commutation loop. Put small ceramics (<10 µF) right at each half-bridge and bulk electrolytics (>10 µF) at the power entry.
- **Switch node short and wide** (HS source to LS drain). Ringing is an LC effect of PCB and FET parasitics.
- **Gate traces ≥20 mil,** routed with their return (SHx for the high side).
- **Shunts and VDRAIN use Kelvin connections enforced with net ties.**
- **TI SLVA959 contains errors:** its per-via thermal resistance, a unit typo and a "90° bends reflect" claim. Do not encode them.

## Key facts

**TI SLVA959B "Best Practices for Board Layout of Motor Drivers"** (Oct 2021; [PDF](https://www.ti.com/lit/pdf/slva959)) [P]:
- **Grounding:**
  - Single-point distribution for power traces, star ground for signals.
  - Partition into areas; do not physically split.
  - On 2-layer boards, "grid" the ground (connect fills and traces at both ends into a mesh). Use a plane on 4-layer or large 2-layer boards.
  - Keep vias apart so they don't break the plane.
  - With a predriver, isolate its high-current ground and join it at the star.
  - On 2-layer boards, keep FETs, bootstrap and charge pumps away from sensitive signals.
- **Capacitors:**
  - Bulk electrolytics (>10 µF) at the power module or power entry, with multiple vias and low ESR.
  - Charge-pump and bootstrap caps as close to the driver as possible.
  - Bypass: on the IC's layer; no via between cap and pin (vias go into the cap first, then to the IC); most vias and widest traces practical; "less than 0.5 cm (0.2 in)"; L/W ≤3:1.
  - Power-stage ceramics (<10 µF) as close as possible to the FETs and motor connection.
  - ~1 nF at integrated CSA sensing pins.
- **Routing:**
  - Gate drive starts at 20 mil for 1 oz. Route the HS gate as close as possible to the switch-node trace (minimum loop, dv/dt).
  - Teardrops at thin-to-thick and via-to-pad transitions.
  - Sense pairs routed in parallel around obstacles.
  - In-path passives (series R, AC caps) side by side, not staggered.
- **Power stage:**
  - Half-bridge "stack" or "side-by-side". Minimise length and maximise width of the HS-source → LS-drain link.
  - High-current loop: correct widths, minimal distance, minimal layer jumps, enough vias where jumps are unavoidable.
- **Sensing:**
  - High-side shunt near the star between supply and HS sources; first gain resistor nearest the shunt.
  - Low-side shunt between LS source and the power-stage star ground, one per phase.
  - Tightly coupled pair to the CSA with a net tie between device and shunt; never parallel to switching nets.
  - 20 A × 1 mΩ = 400 mW for a 20 mV signal.
- **VDRAIN** (V_DS overcurrent monitoring): a single Kelvin trace straight to the HS drain, with a net tie near the drain to avoid false OCP trips.
- **Thermal and vias:**
  - Continuous top pours from the thermal pad to the planes; 1.5–2 oz copper.
  - Direct-connect thermal vias, never spokes, not mask-covered (voiding). 20 mil pad / 8 mil hole vias.
  - IPC-2152 via current (1 oz, 10 °C): 6 mil 0.2 A; 8 mil 0.55 A; 10 mil 0.81 A; 12 mil 0.84 A; 16 mil 1.1 A.
  - Multiple vias where current enters or leaves pins; no via clusters that split the plane.
  - Doubling copper thickness halves lateral thermal resistance.

**Errors in SLVA959** (RPA §11 analysis) [I]:
- Its Eq. 4 claims **5.73 °C/W** for one 20/8 mil via. That treats the pad diameter and hole as radii and the annulus as solid copper. A plated barrel is far worse: SNVA419 gives 261 °C/W (12 mil, 0.5 oz), blogs about 150 °C/W.
- Its Eq. 2 prints λ as "25 °C·cm/W", but Eq. 3 uses 0.25. The 71.4 °C/W result for 1 cm² of 1 oz copper matches 0.25.
- "90° bend … can cause the current to reflect" is not credible at motor-drive frequencies (see the HS/EMI myths docs). Obtuse corners are fine.
- Its via-current table (0.84 A at 12 mil) is about half the calculators' figure (~1.9 A for 0.3 mm). It remains the conservative default ([high-current.md](high-current.md)).

**Rules** (RPA §11) [I]:

| ID | Rule | Numeric | Check | Sev |
|---|---|---|---|---|
| MOT-01 | Per half-bridge HF bypass from HS drain to LS source, same layer, no vias | ≤~5 mm (TI <0.5 cm); L/W ≤3 | Loop polygon {C_byp, Q_HS.D, Q_LS.S}; via count | S1 |
| MOT-02 | Switch node short and wide | Minimise length/width | Per-phase SW length / minimum width | S2 |
| MOT-03 | Gate paired with its return | ≥20 mil @ 1 oz | GHx/SHx coupling; width | S2 |
| MOT-04 | Shunt to star; Kelvin pair via net ties; ~1 nF at the CSA | No parallel run with SW or gate | Net-tie presence; diff pair; coupling | S1 |
| MOT-05 | VDRAIN Kelvin trace + net tie | Single trace | Not shared with the VM pour | S1 |
| MOT-06 | Bulk at the entry, ceramics at the bridge | >10 µF / <10 µF | Value/type classification + distances | S2 |
| MOT-07 | Thermal pad: continuous pour + direct-connect vias | 2 oz if possible | Via count; zone connection = solid | S2 |

## Recommendations for our system
- **H-bridge / 3-phase detector:** N-FET pairs sharing an SH node that goes to a connector; gate-driver pins GHx/SHx/GLx/SLx/SPx/SNx/VDRAIN/VCP. Roles: per-phase bypass cap, shunt, CSA filter caps, bulk cap.
- **Propose net ties** for shunt Kelvin pairs and VDRAIN as schematic changes; KiCad net ties need a symbol ([current-sense-kelvin.md](current-sense-kelvin.md)).
- **Use the conservative via-current table,** and flag SLVA959's thermal equation as an erroneous source in provenance.

## Conflicts and open questions
- **No stepper- or BLDC-specific notes** beyond SLVA959, and no motor-connector or cable-shielding data, were read.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 11, § 20](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)

See also: [gate-drive-bootstrap.md](gate-drive-bootstrap.md), [current-sense-kelvin.md](current-sense-kelvin.md), [high-current.md](high-current.md), [../thermal.md](../thermal.md)
