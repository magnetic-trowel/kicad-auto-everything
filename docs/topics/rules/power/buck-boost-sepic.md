# Inverting buck-boost, 4-switch buck-boost, SEPIC and Ćuk

**TL;DR**
- **Inverting buck-boost:** CIN, switch, rectifier and COUT form *one* series hot loop. Put both cap grounds side by side at the IC.
- **4-switch buck-boost:** two hot loops, one per half-bridge. Each half-bridge gets its own HF cap at its FETs.
- **SEPIC/Ćuk:** switch → coupling cap → rectifier → COUT → GND. This is inference only; confirm it against the controller datasheet.
- **Driver-supply loop:** in AN-139's buck-boost example, the input-cap loop carried >20 dB more RF energy than the INTVCC loop. The driver loop is the second priority.

## Key facts

| Topology | Hot loop members | Continuous (not hot) | Placement implication | Evidence |
|---|---|---|---|---|
| Inverting buck-boost | CIN, switch, diode/sync FET, COUT in one series loop | L | CIN and COUT grounds adjacent at the IC | [I] from circuit analysis (RPA §1) |
| 4-switch buck-boost | Input half-bridge + CIN; output half-bridge + COUT | L | One HF cap right at each half-bridge | [I] |
| SEPIC / Ćuk | Switch → coupling cap → rectifier → COUT → GND → switch | L1, L2, CIN | Coupling cap inside the tight loop | [I], unconfirmed |

- **AN-139** (Kueck, buck-boost example; [mirror](https://theengineer.markallengroup.com/production/content/uploads/2015/01/an139f.pdf)) [P]:
  - RF energy in the input-cap hot loop was >20 dB higher than in the INTVCC decoupling loop.
  - Make the INTVCC/driver loop the second priority, with a solid next-layer plane.
- **Classifier hints** (RPA §20) [I]:
  - L from SW to GND with a negative output → inverting buck-boost.
  - Two SW nodes with one L between them → 4-switch buck-boost.
- **General rules** (CIN-first, SW, FB, grounds) follow [buck.md](buck.md) and [boost.md](boost.md).

## Recommendations for our system
- **Emit one `loop_area` constraint per hot loop:** one for inverting, two for 4-switch.
- **For SEPIC/Ćuk,** emit the loop constraint as soft and flag "unverified topology inference" until a datasheet layout section confirms it.
- **Add a proximity constraint** between the CIN and COUT ground pads for the inverting topology.

## Conflicts and open questions
- **No primary layout note** for SEPIC/Ćuk or 4-switch buck-boost was read. Pull guidance from the specific controller datasheet's Layout Guidelines (see [../datasheet-to-constraints.md](../datasheet-to-constraints.md)).

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 1, § 20](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)

See also: [hot-loops.md](hot-loops.md), [buck.md](buck.md), [boost.md](boost.md)
