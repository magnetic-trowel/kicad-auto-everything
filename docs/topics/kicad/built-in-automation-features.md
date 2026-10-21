# KiCad's built-in automation levers (9.0 and 10.0)

**TL;DR**
- **KiCad has no routing or placement API.** Its built-in automation is reachable only through the GUI or the unstable `RunAction`. The actions are "Attempt Finish Selected (Autoroute)" (push-and-shove), a 2011–12 legacy autoplacer, Specctra export/import, multichannel rule areas, and Repeat Layout [P].
- **Repeat Layout matches channels by topology isomorphism**: refdes prefix plus pin connectivity, with ties broken by sheet instance and then proximity. Once one channel is done, the rest are almost free [P].
- **PCB Design Blocks (10.0)** save and re-apply known-good sub-layouts. **Component classes (9.0)** and **tuning profiles (10.0)** are native constraint vocabulary the agent can write [P].
- **Variants (10.0)** are served over IPC (8 commands). DNP is per variant [P].
- **The KiCad project has long declined to build an autorouter**; the forum moderator line is "not in the foreseeable future" [P].

## Key facts

### Release features relevant to automation
| Release | Features |
|---|---|
| 9.0.0 (2025-02-20) | Jobsets; multichannel design (Tomasz Wlostowski: "repeat PCB layout elements from one channel to create identical copies"); component classes (set from rule-area directive labels; expressions `A.ComponentClass`, `A.hasComponentClass('X')`, `A.memberOfFootprint('${Class:X}')`); multiple net classes per net with `hasNetclass`; net-class rule areas; schematic design blocks; zone manager; multi-track drag in the push-and-shove router; the IPC API [P] ([9.0 notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)) |
| 10.0.0 (2026-03-20) | Time-domain tuning (James Jackson: "time-domain constraints instead of just length constraints, and … Tuning Profiles"); **PCB Design Blocks**; inner-layer objects in footprints; unconstrained pin and gate swap with back-annotation; **graphical DRC rule editor** ("fully compatible with the existing Custom Rules language"); suggested-fix actions for DRC errors; variants, jumpers, schematic grouping; Allegro, PADS and gEDA importers; barcodes; 3D PDF [P] ([10.0 notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)) |
| 10.0.4 (2026-06-21) | The router enforces `physical_clearance` and `physical_hole_clearance`; tuning patterns are excluded from uncoupled length [P] |
| 10.0.5 / .6 / .7 | Profiles no longer always imply time domain; DSN export quoting, duplicate-reference and layer-name fixes; `FlipItems` used natively by Konnect; the rule editor stops breaking time-domain rules; length tolerance may equal the optimum [P] |

### Action names (confirmed on 10.0 and master)
Source: [pcb_actions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp) [P].

| Action | What it does |
|---|---|
| `pcbnew.InteractiveRouter.Autoroute` | "Attempt Finish Selected (Autoroute)": "Sequentially attempt to automatically route all selected pads". It exists in 8.0, 9.0, 10.0 and master. |
| `pcbnew.Autoplacer.autoplaceSelected`, `…autoplaceOffboard` | Legacy autoplacer: `pcbnew/autorouter/ar_autoplacer.cpp` (copyright 2011–2012, Charras/Hollenbeck) plus `spread_footprints.cpp`. It needs an Edge.Cuts outline and skips locked footprints. Still in master. |
| `pcbnew.EditorControl.exportSpecctraDSN`, `importSpecctraSession` | Specctra round trip in the GUI. **SES import is destructive in 10.0**; see [specctra-freerouting-integration.md](specctra-freerouting-integration.md). |
| `pcbnew.Multichannel.generatePlacementRuleAreas` | "Creates best-fit placement rule areas" named `auto-placement-area-<source>` |
| `pcbnew.Multichannel.repeatLayout` | "Clones placement & routing across multiple identical channels" |
| `pcbnew.InteractiveDrawing.placeDesignBlock`, `…applyDesignBlockLayout`, `pcbnew.PcbDesignBlockControl.saveSelectionAsDesignBlock` | Design Blocks |

- `RunAction` returns immediately with `RAS_OK` or `RAS_INVALID`. The proto warns: "Command names may change as code is refactored, and commands may disappear. This API method is provided for low-level prototyping purposes only" [P].
- A third-party claim of "122 actions added, 47 removed between 9.0 and 10.0" could not be verified (NOT FOUND, VK).

### Multichannel (10.0 docs)
- **Channel sources:** hierarchical sheets ("most common and convenient"), component classes, or named groups.
- **Repeat Layout options:** anchor footprint; copy placement; copy routing (fully enclosed only; existing target routing is removed); restrict to connected routing; copy other items; group items; include locked.
- **Matching** is by topology isomorphism (refdes prefix plus pin-connectivity preservation), with ties broken by sheet instance, then proximity [P] ([pcbnew_multichannel.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_multichannel.adoc)).
- **Plugin superseded.** Mitja Nemec's ReplicateLayout (GPL-2.0) says "The functionality of this plugin is now available in KiCad natively". The PCM still carries a KiCad 10 build, 5.0.1 [P].

### PCB Design Blocks (10.0 docs)
- Libraries are `.kicad_blocks` folders listed in global or project tables. A block can be saved from the whole board or a selection.
- "Apply Design Block Layout" applies a saved layout to footprints grouped from a schematic design block. This needs "Place as group" and a group library link [P] ([pcbnew_design_blocks.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_design_blocks.adoc)).

### Variants (10.0)
- Variants are defined in the schematic and transferred by Update PCB. The PCB toolbar has a variant selector; DNP is per variant; `${VARIANT}` and `${VARIANT_DESC}` text variables are available.
- IPC commands: `GetVariants`, `AddVariant`, `DeleteVariant`, `RenameVariant`, `CopyVariant`, `SetVariantDescription`, `SetCurrentVariant`, `GetCurrentVariant` [P] ([pcbnew_variants.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_variants.adoc); [variant_commands.proto](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/variant_commands.proto)).

### Related tools outside KiCad core
- **Horizon EDA** embeds the same push-and-shove router and lists an autorouter as a non-goal: "an autorouter is rarely useful for small to medium-sized boards" [P] ([non-goals](https://docs.horizon-eda.org/en/latest/non-goals.html)).
- **Forum stance:** the KiCad forum thread "Autoroute? Is it coming?" (2021–22, 201 posts) carries the moderator edit "short answer is not in the foreseeable future" [P] ([forum](https://forum.kicad.info/t/autoroute-is-it-coming/30441)).

## Recommendations for our system
- **Treat these as levers, not engines** [I, from ET]:
  - component classes and custom DRC for constraints;
  - rule areas plus Repeat Layout for multichannel reuse;
  - Design Blocks for known-good sub-layouts;
  - tuning profiles for timing;
  - "Attempt Finish Selected" for local completion of a few nets.
- **Multichannel as a placement multiplier:** place and route one channel, then generate rule areas and Repeat Layout. Use `RunAction`, or replicate the logic with IPC CRUD. Prefer hierarchical-sheet channels [I, from VK].
- **Wrap every `RunAction` behind a version-checked adapter** with a fallback, because the names can change [I].
- **Use legacy autoplacer output only as a weak baseline**, not as a seed [I].

## Conflicts and open questions
- Did the KiCad 10 interactive router gain automation features beyond tuning? Unconfirmed (ET gap).
- Is there a reliable headless way to invoke Repeat Layout on 10.x without the GUI? Not documented.

## Sources
- research notes:
  - [verification_kicad_and_tools.md § 3.4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [existing_tools_and_apis.md § 1, § 2 (PCM), § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
- primary: [pcb_actions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp), [pcbnew/autorouter @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/pcbnew/autorouter), [10.0.4 notes](https://www.kicad.org/blog/2026/06/KiCad-10.0.4-Release/)

See also: [ipc-api-10-vs-11.md](ipc-api-10-vs-11.md), [drc-rule-language-reference.md](drc-rule-language-reference.md), [../landscape/open-source-placers.md](../landscape/open-source-placers.md)
