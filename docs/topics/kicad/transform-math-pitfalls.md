# Footprint transform math pitfalls (rotation, flip, mirror, frames)

Scope: KiCad's local↔board transform, angle spelling, flip semantics, bugs the four MCP servers hit, how to test transforms. Not here: other file hazards -> [file-format-and-version-hazards.md](file-format-and-version-hazards.md); test strategy -> [mcp-server-testing-practices.md](mcp-server-testing-practices.md).
Keys: rotation matrix, Y-down frame, RotatePoint, FOOTPRINT::Rotate, FOOTPRINT::Flip, KiROUND, mirror before rotation, absolute child coordinates, anchor-only move, KeepUpright, angle normalization, FlipItems, drill oracle, Gerber oracle, Kria K26, 2,970/2,970

Fix commits for rotation/flip/mirror/transform: KMS 19, Konnect 12, PRO 5, POA 12, the most consistent bug class across the four servers ([counts](mcp-server-lessons.md#recurring-bug-classes)) [P].

## KiCad local-to-board formula (Y-down)
```
board_x = fp_x + lx·cosθ + ly·sinθ
board_y = fp_y − lx·sinθ + ly·cosθ
```
- The textbook matrix agrees at 0° and 180°, fails at ±90° ("e.g. reporting a connector's pin 1 at the far end of the connector"); it hides on symmetric parts and square courtyards [P].
- **Konnect** (`get_component_pads`, `get_pad_position`, `route_pad_to_pad`) used the textbook form; regression ground truth = routed copper on Antmicro's Kria K26 board (Apache-2.0), because "a purely geometric check cannot catch this on a symmetric pad grid" [P] ([2581b40](https://github.com/mixelpixx/Konnect/commit/2581b40d76d57a1ccaf77f24862df81478f54f4d)).
- **POA (#59), ten weeks later:** `_transform_local_to_board` used the textbook form, so "every footprint at a non-180 degree angle came back mirrored", corrupting bounds, keepout scans, thermal-via pad centres, dangling-track detection, autoroute keepout promotion. Back side: KiCad already stores B.Cu children in the flipped frame, so negating `local_x` moved them by twice their offset. Survived because "every rotated fixture used a square courtyard". Oracle `kicad-cli pcb export drill`: new transform matches **2,970/2,970** drilled through-hole pads on every KiCad 9 demo board (old: 2,292) and all **1,231** B.Cu SMD pads against Gerber flashes [P] ([b588906](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/b58890613d8c7abb061db916dc814f7438042f78)).

## Mirror before rotation
POA `get_pin_positions` misreported 28 of 84 pin positions across a 12-orientation sweep; `connect_pins(R1:1, R9:1)` joined R1 pad 2; non-orthogonal angles now raise [P] ([fff4209](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/fff42098b5a291c85e753acdebdb1d8e4903c405)). KMS fixed the same order in `pin_world_xy` ([29b213e](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/29b213ec6e2be3d685bdc89d1e3d0822d157d1c2), [7e67cb9](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/7e67cb91c465c77e7c5a01ebadefa8b6b5603a08)).

## Anchor-only moves over IPC
"KiCAD 10 serializes a FootprintInstance's children … in ABSOLUTE board coordinates — despite the proto comment on Pad.position claiming footprint-relative." Updating only position or orientation moved the anchor while copper, silk and text stayed, "permanently corrupting the .kicad_pcb on save". Fix: apply KiCad's `SetPosition`/`SetOrientation` rigid transform to every child ("off-axis rectangles become polygons"); reject unknown item types [P] ([37adcaa](https://github.com/mixelpixx/Konnect/commit/37adcaaf148f6ae68bbc424fab8637700b15a7b1)). Never trust proto comments about frames; verify by readback [I].

## Rotation: pads and text, angle spelling, rounding
POA bugs 2, 53, 63, 87, 89 of #110 (pads and text left behind) [P] ([cf501c7](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/cf501c7faf7069757cd479211b221334b5b74290)):
- apply `FOOTPRINT::Rotate` with the KeepUpright text rule;
- **angle spelling:** pads in [0, 360) (270, not −90; omitted at 0); footprint `(at)` angles normalized to (−180, 180], so a footprint at 270° is written −90 [P] ([footprint.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/footprint.cpp) `SetOrientation`, [padstack.h @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/padstack.h));
- compute in integer nm like `RotatePoint`, KiROUND chosen by format version ("KiCad 10's for a board stamped above 20241229").

Reject angle inputs KiCad cannot parse; normalize to KiCad's spelling before writing [I].

## Flip semantics (FOOTPRINT::Flip)
- angle → (180 − angle) % 360; local Y negated; layers through the board's flip map; tenting swapped on KiCad 10 boards only; zones, KiCad 10 padstacks and partial inner stacks refused before any edit [P] ([2d4a55f](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/2d4a55fdb0de987fcd67c63d88eaa5ae150d9e91)).
- Earlier POA `move_footprint(layer=…)` rewrote only the footprint's layer atom, "leaving pads on F.Cu … and kicad-cli loaded it without complaint". Two of the author's own probes measured the wrong thing: at 90° the angle rule is invisible, and KiCad re-sorts items so index pairing failed [P] ([45ba30b](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/45ba30b462b28d95f35d9585dd0e3b5740d486ff)).
- **Native:** Konnect `flip_component` uses KiCad 10.0.6's `FlipItems`, which includes the 3D-model transform [P]. Prefer native IPC operations (`FlipItems`, KiCad rigid moves) over recomputing child geometry [I].

## Smaller transform bugs
[P]
- KMS IPC `rotate_component` treated the angle as relative while the schema said absolute (#159).
- KMS: `Flip()` before `board.Add()` hung KiCad 9 for 30 s.
- POA: `check_placement`'s `rotation` parameter removed, "rotating about the origin cannot move the origin".
- Konnect: JLCPCB pick-and-place rotation corrections needed a separate fix (CPL rotation table from PRO, MIT).

## One transform module, oracle-pinned
[I]
- Exactly one module (local↔board, rotate, flip, mirror) in integer nm, KiROUND by format era. Under GPL-3.0-or-later it may port KiCad's `trigo`/`RotatePoint`/`FOOTPRINT::Rotate`/`Flip`, keeping KiCad's copyright notices; POA's `tests/kicad_ref` ports and October fixes are reusable likewise.
- Pin it against `kicad-cli` drill and Gerber coordinates and IPC readback on asymmetric fixtures (e.g. Antmicro boards) at 0/90/180/270°, both sides.

## Open questions
- Does `UpdateItems` on 10.0.x still need the client to transform children, or is there a native rigid move for every item type? Not exhaustively tested.

## Sources
- [kicad_mcp_codebases.md § 2A, § 2 Inferences, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md); [licensing.md § 2 (porting = derivative; fine under GPL)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- commit links above; [POA tests/kicad_ref](https://github.com/ProductOfAmerica/mcp-server-kicad/tree/f5f82e02ffe17bbcba806fec35f3302ee332fefc/tests/kicad_ref)
