# Boost converter layout rules

**TL;DR**
- **The hot loop is LS switch → rectifier/HS switch → COUT_HF → PGND.** The *output* cap is the critical cap, not the input cap.
- **COUT_HF ground returns to the IC PGND by the shortest path.** Use a small cap at the IC and bulk farther out.
- **VIN copper is quiet,** so large VIN area is fine. Keep SW small and keep FB away from SW.
- **Single AGND tie** close to the PGND pin.
- Everything else follows [buck.md](buck.md): FB, SW and snubber rules.

## Key facts
- **Hot loop:**
  - [TI SNVA731](https://www.ti.com/lit/an/snva731/snva731.pdf) [P], VERIFIED: "In a boost converter, the most critical PCB feature is the loop formed by the output capacitor, diode and the regulator ground."
  - AN-136 [P]: C_HF goes on the output side, close to the MOSFET and the diode.
- **TI SLVA773** ("Five Steps to a Good PCB Layout of the Boost Converter", [PDF](https://www.ti.com/lit/an/slva773/slva773.pdf)) [P]:
  - Output cap close to the IC with short, wide traces.
  - "One via per amp of current if the via is required."
  - A small-package cap can sit next to the IC, with bulk caps farther away.
  - Input-cap ground close to PGND. CIN ground, COUT ground and IC ground "form a Power-Ground".
  - A large VIN copper area is acceptable, because VIN is quiet.
  - "Any trace of a sensitive node, such as FB, should be far away from the SW node"; do not run FB parallel to SW.
  - AGND "connected to the Power-Ground of the IC through a single point … close to the PGND pin".
- **Loop-area target:** "under 1 cm² if possible" appears only on a calculator page ([Firgelli](https://www.firgelliauto.com/blogs/engineering-calculators/boost-converter-calculator)) [V]. Use the [hot-loops.md](hot-loops.md) tiers instead.
- **Rule PWR-09** (RPA §1): COUT_HF tight to the rectifier and PGND. Hot-loop area {LS FET, D, COUT_HF}. Severity S1. Also applies to flyback secondaries.
- **Boost LED drivers** use the SW–D–COUT loop ([led-drivers.md](led-drivers.md)).

## Recommendations for our system
- **Topology detector:** an inductor between the input rail and SW, plus a diode or sync FET from SW to the output → boost. Assign COUT_HF = the smallest-package cap on VOUT/PGND.
- **Hot-loop polygon** {SW pin / LS FET, rectifier, COUT_HF, PGND}: hard same-layer and 0-via topology; soft area score.
- **Cap rank:** the COUT_HF ground pad must be the closest cap to PGND.
- **Do not flag a large VIN pour as an EMI risk** in boost designs.

## Conflicts and open questions
- **SEPIC/Ćuk loop membership** is inference only ([buck-boost-sepic.md](buck-boost-sepic.md)).
- **No numeric FB–SW clearance** exists in any vendor document.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 1](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [interface_rule_packs.md § 8](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)

See also: [hot-loops.md](hot-loops.md), [buck.md](buck.md), [led-drivers.md](led-drivers.md)
