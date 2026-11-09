# KiCad built-in automation levers (9.0 and 10.0)

Scope: GUI/`RunAction` automation in KiCad core (autoroute action, legacy autoplacer, multichannel Repeat Layout, Design Blocks, variants) and release features that matter for automation. Not here: IPC coverage -> [ipc-api-10-vs-11.md](ipc-api-10-vs-11.md); rule syntax -> [drc-rule-language-reference.md](drc-rule-language-reference.md); DSN round trip -> [specctra-freerouting-integration.md](specctra-freerouting-integration.md).
Keys: RunAction, Attempt Finish Selected, Autoroute action, autoplacer, ar_autoplacer, multichannel, Repeat Layout, rule areas, PCB Design Blocks, component classes, tuning profiles, variants, DNP, ReplicateLayout, Horizon EDA, no autorouter

**KiCad has no routing or placement API.** Built-in automation is reachable only through the GUI or the unstable `RunAction` [P]. The project has long declined to build an autorouter: forum thread "Autoroute? Is it coming?" (2021–22, 201 posts), moderator edit "short answer is not in the foreseeable future" [P] ([forum](https://forum.kicad.info/t/autoroute-is-it-coming/30441)).

## Release features relevant to automation
| Release | Features |
|---|---|
| 9.0.0 (2025-02-20) | Jobsets; multichannel design (Tomasz Wlostowski: "repeat PCB layout elements from one channel to create identical copies"); component classes (set from rule-area directive labels; expressions `A.ComponentClass`, `A.hasComponentClass('X')`, `A.memberOfFootprint('${Class:X}')`); multiple net classes per net with `hasNetclass`; net-class rule areas; schematic design blocks; zone manager; multi-track drag in push-and-shove; the IPC API [P] ([9.0 notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)) |
| 10.0.0 (2026-03-20) | Time-domain tuning (James Jackson: "time-domain constraints instead of just length constraints, and … Tuning Profiles"); **PCB Design Blocks**; inner-layer objects in footprints; unconstrained pin and gate swap with back-annotation; **graphical DRC rule editor** ("fully compatible with the existing Custom Rules language"); suggested-fix actions for DRC errors; variants, jumpers, schematic grouping; Allegro, PADS, gEDA importers; barcodes; 3D PDF [P] ([10.0 notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)) |
| 10.0.4 (2026-06-21) | Router enforces `physical_clearance` and `physical_hole_clearance`; tuning patterns excluded from uncoupled length [P] ([10.0.4 notes](https://www.kicad.org/blog/2026/06/KiCad-10.0.4-Release/)) |
| 10.0.5 / .6 / .7 | Profiles no longer always imply time domain; DSN export quoting, duplicate-reference and layer-name fixes; `FlipItems` (used natively by Konnect); rule editor stops breaking time-domain rules; length tolerance may equal the optimum [P] |

## Action names (10.0 and master)
Source: [pcb_actions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp) [P].

| Action | What it does |
|---|---|
| `pcbnew.InteractiveRouter.Autoroute` | "Attempt Finish Selected (Autoroute)" (push-and-shove): "Sequentially attempt to automatically route all selected pads"; in 8.0, 9.0, 10.0, master |
| `pcbnew.Autoplacer.autoplaceSelected`, `…autoplaceOffboard` | Legacy autoplacer `pcbnew/autorouter/ar_autoplacer.cpp` (copyright 2011–2012, Charras/Hollenbeck) + `spread_footprints.cpp`; needs an Edge.Cuts outline, skips locked footprints; still in master |
| `pcbnew.EditorControl.exportSpecctraDSN`, `importSpecctraSession` | GUI Specctra round trip; **SES import is destructive in 10.0** ([specctra](specctra-freerouting-integration.md#kicad-side-dsnses)) |
| `pcbnew.Multichannel.generatePlacementRuleAreas` | "Creates best-fit placement rule areas" named `auto-placement-area-<source>` |
| `pcbnew.Multichannel.repeatLayout` | "Clones placement & routing across multiple identical channels" |
| `pcbnew.InteractiveDrawing.placeDesignBlock`, `…applyDesignBlockLayout`, `pcbnew.PcbDesignBlockControl.saveSelectionAsDesignBlock` | Design Blocks |

- `RunAction` returns immediately with `RAS_OK` or `RAS_INVALID`; proto: "Command names may change as code is refactored, and commands may disappear. This API method is provided for low-level prototyping purposes only" [P]. Wrap every `RunAction` in a version-checked adapter with a fallback [I].
- A third-party claim "122 actions added, 47 removed between 9.0 and 10.0" is unverified (NOT FOUND, VK).
- Use legacy autoplacer output only as a weak baseline, not as a seed [I].

## Multichannel Repeat Layout (10.0 docs)
- **Channel sources:** hierarchical sheets ("most common and convenient"; prefer these [I]), component classes, named groups.
- **Options:** anchor footprint; copy placement; copy routing (fully enclosed only; existing target routing is removed); restrict to connected routing; copy other items; group items; include locked.
- **Matching:** topology isomorphism (refdes prefix + pin-connectivity preservation); ties broken by sheet instance, then proximity [P] ([pcbnew_multichannel.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_multichannel.adoc)).
- **Placement multiplier:** place and route one channel, generate rule areas, Repeat Layout; the rest are almost free. Drive via `RunAction` or replicate the logic with IPC CRUD [I, from VK].
- Mitja Nemec's ReplicateLayout plugin (GPL-2.0): "The functionality of this plugin is now available in KiCad natively"; PCM still carries a KiCad 10 build, 5.0.1 [P].

## PCB Design Blocks (10.0 docs)
- Libraries are `.kicad_blocks` folders listed in global or project tables; save from the whole board or a selection.
- "Apply Design Block Layout" applies a saved layout to footprints grouped from a schematic design block; needs "Place as group" and a group library link [P] ([pcbnew_design_blocks.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_design_blocks.adoc)).

## Variants (10.0)
- Defined in the schematic, transferred by Update PCB; PCB toolbar variant selector; DNP per variant; text variables `${VARIANT}`, `${VARIANT_DESC}`.
- 8 IPC commands: `GetVariants`, `AddVariant`, `DeleteVariant`, `RenameVariant`, `CopyVariant`, `SetVariantDescription`, `SetCurrentVariant`, `GetCurrentVariant` [P] ([pcbnew_variants.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_variants.adoc); [variant_commands.proto](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/variant_commands.proto)).

## Lever map
Treat these as levers, not engines [I, from ET]: component classes + custom DRC → constraints; rule areas + Repeat Layout → multichannel reuse; Design Blocks → known-good sub-layouts; tuning profiles → timing; "Attempt Finish Selected" → local completion of a few nets.

**Horizon EDA** embeds the same push-and-shove router and lists an autorouter as a non-goal: "an autorouter is rarely useful for small to medium-sized boards" [P] ([non-goals](https://docs.horizon-eda.org/en/latest/non-goals.html)). Placers: [../landscape/open-source-placers.md](../landscape/open-source-placers.md).

## Open questions
- Did the KiCad 10 interactive router gain automation features beyond tuning? Unconfirmed (ET gap).
- Is there a reliable headless way to invoke Repeat Layout on 10.x? Not documented.

## Sources
- [verification_kicad_and_tools.md § 3.4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); [existing_tools_and_apis.md § 1, § 2 (PCM), § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
- [pcb_actions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp), [pcbnew/autorouter @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/pcbnew/autorouter)
