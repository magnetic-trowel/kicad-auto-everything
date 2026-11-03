# Review checklist (full): thermal, routing, zones, paste, assembly, test

Scope: 55 items (THM 6, RTE 11, ZON 7, PST 5, ASM 13, DFT 13) of the 299 layout-review items, full rows. Not here: structure, statistics, codes and the Critical/most-agreed summary -> [review-checklist.md](review-checklist.md); source keys -> [checklist-sources.md](checklist-sources.md).
Keys: review checklist, thermal relief, routing, zones, paste, via-in-pad, assembly, fiducials, test points, DFT, THM-01, ZON-01, ASM-13

Thermal reliefs, zone refill, paste segmentation and via-in-pad rules are DRC-checkable; assembly items depend on assembler tables (spacing, fiducials) and load from an assembler profile; test/debug items are mostly judgment but cheap to suggest automatically (test points per rail, GND hooks). [I]

Columns and codes (Sev C/M/m, Auto A/S/J) -> [review-checklist.md#severity-and-automation-codes](review-checklist.md#severity-and-automation-codes). Thresholds are the cited sources' values: fab-specific, conflicting, treat as profile parameters. KiCad DRC key names follow the source note except where marked "KiCad 10 keys" (verified list: [../kicad/drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md)).

## Checklist items
| ID | Category | What to check | Why | Sev | Auto | Sources |
|---|---|---|---|---|---|---|
| THM-01 | Thermal | Thermal reliefs on plane connections for solderability/rework (except heat-sinking or high-current pads) | Cold joints | M | A (zone_connection); KiCad 10 keys: `zone_connection` | AZ, GD, PK, JN, UW, PP |
| THM-02 | Thermal | Solid connections plus thermal-via arrays under dissipating pads; copper area for regulators, SMPS, LED drivers, FETs, motor drivers, CPUs, PAs | Junction temperature | M | S | AZ, JN, HH, AL, SCR |
| THM-03 | Thermal | Thermal balance on 2-terminal chips (UWARG: copper on one pad <2× the other for ≤0805; KH heuristic: copper ratio <0.3 high risk) | Tombstoning | M | S | AZ, GD, UW, KH |
| THM-04 | Thermal | Thermal lands unmasked; exposed pads on the correct net | Heat transfer, function | M | S | JN, HH, SCD |
| THM-05 | Thermal | Thermal-relief spokes fully resolved | Weak connection | M | A (min_resolved_spokes) | KD |
| THM-06 | Thermal | Relief geometry within fab spec (PCB Power: 10 mil gap, 8 mil spoke) | Solderability | m | A (thermal_relief_gap, thermal_spoke_width) | PP |
| RTE-01 | Routing | No acute trace angles | Acid traps | m | A (track_angle) | HH, KD, UW |
| RTE-02 | Routing | Adjacent IC pins never bridged directly; traces leave pad ends (U-shape) | Looks like a short | m | A/S | GD, HH, JN |
| RTE-03 | Routing | No dangling tracks/vias, wandering traces or antennas | Stubs | m | A (Track has unconnected end; via_dangling) | GD, KD, VSE, SCR |
| RTE-04 | Routing | Traces off the outline and depanel zones | Damage | m | A (edge_clearance) | GD |
| RTE-05 | Routing | Superfluous vias removed | Reliability, cost | m | A | HH |
| RTE-06 | Routing | Teardrops where stress is expected (MacroFab: prevent neck-down) | Cracks | m | A | AZ, MF |
| RTE-07 | Routing | Unconstrained traces generously wide | Yield | m | A | GD |
| RTE-08 | Routing | No routing between/under fine-pitch (QFP/QFN/BGA) pads unless planned | Bridging, inspection | m | S | SCR |
| RTE-09 | Routing | Tracks enter/exit pads at the pad center ("route from pads") | Solderability | m | A | SF |
| RTE-10 | Routing | Critical/tuned routes locked after completion | Accidental edits | m | A | BO |
| RTE-11 | Routing | Final per-net visual sanity pass (highlight each net) | Catches odd routes | m | J | BO |
| ZON-01 | Zones | Zones refilled after the last edit and before CAM; pours enabled; none shelved | Stale fills | C | A | AZ, GD, UW, AL |
| ZON-02 | Zones | No pour between adjacent IC pins | Inspection confusion | m | S | HH |
| ZON-03 | Zones | Zone priorities correct; no unintended intersections; same-net overlaps merged | Unexpected shorts/voids | M | A (Copper zones intersect) | KD, UW |
| ZON-04 | Zones | Planes as solid filled contours (not hatch-painted); small pads flashed. Note: PCB Power warns hatch planes cause lamination microvoids, while jnoss recommends hatched pours — sources conflict | CAM, lamination | M | A | PP, JN |
| ZON-05 | Zones | Pour isolation larger than track clearance (SparkFun: 12 mil) | Pour creeping onto traces | m | A | SF |
| ZON-06 | Zones | No polygon angles <45° | Slivers, acid traps | m | A | UW |
| ZON-07 | Zones | Leftover auto-generated zones, dangling stubs and single-layer vias removed | Junk copper | m | A | AD |
| PST-01 | Paste/mask | No untented/unfilled vias in pads (except low-power QFNs) | Solder wicking, voids | C | A | AZ, GD |
| PST-02 | Paste/mask | Paste on large exposed pads segmented (~70% area unless the datasheet says otherwise) | Float, voids | M | A (solder_paste_rel_margin) | AZ, PK, GD, SC |
| PST-03 | Paste/mask | Small pads 100% aperture; large pads reduced | Solder volume | m | A | AZ |
| PST-04 | Paste/mask | No paste on edge fingers, test points, fiducials or DNP parts | Contamination | M | A/S | AZ, GD |
| PST-05 | Paste/mask | Mask clearance around pads (~50 µm typical; Sierra 1.6 mil) | Mask on pad / bridging | m | A (solder_mask_expansion) | AZ, SCD |
| ASM-01 | Assembly | Fiducials: ≥3 global (asymmetric), on both sides if double-sided, 2 local diagonal at fine pitch; 40–118 mil diameter, ~118 mil from edge, with clearance | Machine vision | M | A/S | AZ, AL, GD, FD, SCD, SC |
| ASM-02 | Assembly | Pin-1/polarity marks present and visible after assembly (not under the part) | Orientation errors | M | S | GD, JN, HH, AL, PP, SC |
| ASM-03 | Assembly | BOM and pick-and-place consistent with the board (DNP/DNI marked, centroid rotation convention checked) | Assembly errors | M | S | GD, SC |
| ASM-04 | Assembly | No unnecessarily tiny parts (SparkFun: 0603+ passives) | Yield, hand soldering | m | J | GD, SF |
| ASM-05 | Assembly | Plastic connectors rated for reflow | Melting | m | J | GD |
| ASM-06 | Assembly | Layer-number markers in copper | Layer-order errors | m | A | AZ, PP |
| ASM-07 | Assembly | Assembly order feasible | Buildability | m | J | HH |
| ASM-08 | Assembly | Footprints accept alternate packages/dual footprints for swap-prone parts | Supply chain | m | J | GD, AL6 |
| ASM-09 | Assembly | Passive part-to-part spacing per assembler table (Sierra: 0402 S=12 mil, 0603 21 mil, 0805 30 mil) | Pick-and-place, rework | M | A (courtyard_clearance) | SCD, VSE |
| ASM-10 | Assembly | Component-to-hole wall ≥8 mil (50–100 mil for manual soldering); component-to-annular-ring ≥7 mil | Soldering | m | A | SCD |
| ASM-11 | Assembly | Rework/inspection access: 80 mil for rework tools; 60° inspection angle (rule of thumb: spacing = tallest neighbor's height) | Inspection | m | S | BO, ICD, AL |
| ASM-12 | Assembly | Assembly drawing: top/bottom instructions, outlines matching pick-and-place, ESD/heatsink/connector handling notes | Assembly intent | M | S | SCD, SC |
| ASM-13 | Assembly | IC/diode orientation checked in the assembler's placement preview; option/DNP parts not auto-matched by the assembler's catalog | Common PCBA ordering mistake | C | J | Tanner |
| DFT-01 | Test/debug | Test points on power rails and critical signals; hidden nets made accessible | Bring-up | M | S | GD, HH, PK, AL, UW, VSE |
| DFT-02 | Test/debug | GND test/hook points next to critical test points | Short probe ground loops | m | S | GD, HH, PK, UW |
| DFT-03 | Test/debug | Probe clearance; test pads away from edge (JN: not within 5 mm) for fixturing | Fixture access | m | A | AZ, JN, AL |
| DFT-04 | Test/debug | Programming/debug headers, jumpers and reset accessible | Development | M | J | GD, HH, JN, AL |
| DFT-05 | Test/debug | Status LEDs (UWARG: one per power rail, optional per bus line) | Debug | m | J | JN, PK, UW |
| DFT-06 | Test/debug | Software-readable board-revision straps | Field support | m | J | HH |
| DFT-07 | Test/debug | 0 Ω links to isolate sections; DNP pull options | Staged bring-up | m | J | GD, PK |
| DFT-08 | Test/debug | Caps oriented with power nets facing the same way | Probe shorts | m | S | PK |
| DFT-09 | Test/debug | Test-point distance from components by height (Sierra: L = 0.29·H + 0.7 mm; UWARG ≥1 mm) | Probe access | m | S | SCD, UW |
| DFT-10 | Test/debug | Test-point silk shows the net name; test points on bus lines and enable/shutdown/reset nets | Bring-up | m | S | UW |
| DFT-11 | Test/debug | Test points on one side (bottom for bed-of-nails, top for manual probing) | Fixturing | m | A | AL |
| DFT-12 | Test/debug | No test points under BGAs; ≥5.08 mm between adjacent BGAs for test-point access | Probe access | m | A | SCD |
| DFT-13 | Test/debug | Test point on every node where feasible; dedicated pad ≥1 mm | Testability | m | S | MF |

## Sources
- [expert_workflow_and_checklists.md § Q4 Master checklist table](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md); corrections: [verification_kicad_and_tools.md § 1 Corrections table](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
