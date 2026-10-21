# Footprint transform math pitfalls (rotation, flip, mirror, coordinate frames)

**TL;DR**
- **Rotation, flip and mirror bugs are the most consistent bug class across all four leading KiCad MCP servers.** Fix commits: KMS 19, Konnect 12, PRO 5, POA 12 [P].
- **The textbook rotation matrix is wrong for KiCad's Y-down frame.** It agrees at 0° and 180° and fails at ±90°. It hides on symmetric parts and square courtyards [P].
- **IPC serializes footprint children in absolute board coordinates, contrary to the proto comment.** Moving only the anchor corrupts the board [P].
- **Test against KiCad's own output** (drill and Gerber coordinates, `kicad-cli` netlists, live readback) on asymmetric footprints, at all four orientations, on both sides [P/I].
- With GPL-3.0-or-later code we may **port KiCad's own `RotatePoint`/`Flip` routines** with notices kept, and should keep exactly one transform module [I].

## Key facts
- **The correct KiCad formula.** Konnect's `get_component_pads`, `get_pad_position` and `route_pad_to_pad` used the textbook matrix. KiCad's Y-down frame needs:
  - `board_x = fp_x + lx·cosθ + ly·sinθ`
  - `board_y = fp_y − lx·sinθ + ly·cosθ`
  - The forms disagree at ±90°, "e.g. reporting a connector's pin 1 at the far end of the connector".
  - The regression test uses routed copper from Antmicro's Kria K26 board (Apache-2.0) as ground truth, because "a purely geometric check cannot catch this on a symmetric pad grid" [P] ([2581b40](https://github.com/mixelpixx/Konnect/commit/2581b40d76d57a1ccaf77f24862df81478f54f4d)).
- **POA hit the same bug (#59) ten weeks later.** `_transform_local_to_board` used the textbook matrix, so "every footprint at a non-180 degree angle came back mirrored". It corrupted bounds, keepout scans, thermal-via pad centres, dangling-track detection and autoroute keepout promotion.
  - Back side: KiCad already stores B.Cu children in the flipped frame, so negating `local_x` moved them by twice their offset.
  - The bug survived because "every rotated fixture used a square courtyard".
  - Oracle: `kicad-cli pcb export drill`. Across every KiCad 9 demo board the new transform matches **2,970/2,970** drilled through-hole pads (the old one matched 2,292) and all **1,231** B.Cu SMD pads against Gerber flashes [P] ([b588906](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/b58890613d8c7abb061db916dc814f7438042f78)).
- **Mirror applied before rotation.** POA's `get_pin_positions` misreported 28 of 84 pin positions across a 12-orientation sweep, and `connect_pins(R1:1, R9:1)` joined R1 pad 2. Non-orthogonal angles now raise an error [P] ([fff4209](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/fff42098b5a291c85e753acdebdb1d8e4903c405)). KMS fixed the same order in `pin_world_xy` ([29b213e](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/29b213ec6e2be3d685bdc89d1e3d0822d157d1c2), [7e67cb9](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/7e67cb91c465c77e7c5a01ebadefa8b6b5603a08)).
- **Anchor-only moves over IPC.** "KiCAD 10 serializes a FootprintInstance's children … in ABSOLUTE board coordinates — despite the proto comment on Pad.position claiming footprint-relative." Updating only position or orientation moved the anchor while copper, silk and text stayed behind, "permanently corrupting the .kicad_pcb on save". The fix applies KiCad's `SetPosition`/`SetOrientation` rigid transform to every child; "off-axis rectangles become polygons", and unknown item types are rejected [P] ([37adcaa](https://github.com/mixelpixx/Konnect/commit/37adcaaf148f6ae68bbc424fab8637700b15a7b1)).
- **Pads and text left behind on rotation** (POA bugs 2, 53, 63, 87, 89 of #110). The fix:
  - applies `FOOTPRINT::Rotate` with the KeepUpright text rule;
  - writes angles as KiCad does (270, not −90; omitted at 0);
  - computes in integer nanometres like `RotatePoint`, choosing KiROUND by format version ("KiCad 10's for a board stamped above 20241229") [P] ([cf501c7](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/cf501c7faf7069757cd479211b221334b5b74290)).
- **Flip** follows `FOOTPRINT::Flip`:
  - angle → (180 − angle) % 360, local Y negated, layers through the board's flip map;
  - tenting swapped on KiCad 10 boards only;
  - zones, KiCad 10 padstacks and partial inner stacks refused before any edit [P] ([2d4a55f](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/2d4a55fdb0de987fcd67c63d88eaa5ae150d9e91)).
  - The earlier `move_footprint(layer=…)` rewrote only the footprint's layer atom, "leaving pads on F.Cu … and kicad-cli loaded it without complaint".
  - Two of the author's own probes measured the wrong thing: at 90° the angle rule is invisible, and KiCad re-sorts items so index pairing failed [P] ([45ba30b](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/45ba30b462b28d95f35d9585dd0e3b5740d486ff)).
- **Native flip.** Konnect's `flip_component` uses KiCad 10.0.6's native `FlipItems`, which includes the 3D-model transform [P].
- **Smaller bugs:**
  - KMS IPC `rotate_component` treated the angle as relative while the schema said absolute (#159).
  - KMS: `Flip()` before `board.Add()` hung KiCad 9 for 30 s.
  - POA: `check_placement`'s `rotation` parameter was removed because "rotating about the origin cannot move the origin".
  - Konnect: JLCPCB pick-and-place rotation corrections needed a separate fix (the CPL rotation table came from PRO, MIT) [P].

## Recommendations for our system
- **Exactly one transform module** (local↔board, rotate, flip, mirror) in integer nm, with KiROUND by format era. Under GPL-3.0-or-later it may be a direct port of KiCad's `trigo`/`RotatePoint`/`FOOTPRINT::Rotate`/`Flip`, keeping KiCad's copyright notices. POA's `tests/kicad_ref` ports and its October fixes are reusable for the same reason [I].
- **Oracle-pin it:** compare against `kicad-cli` drill and Gerber coordinates and against IPC readback, on asymmetric fixtures (e.g. Antmicro boards) at 0/90/180/270°, on both sides [I].
- **Prefer native IPC operations** (`FlipItems`, rigid moves via KiCad) over re-computing child geometry. Never trust proto comments about frames; verify by readback [I].
- **Reject angle inputs KiCad cannot parse.** Normalize angles to KiCad's spelling before writing [I].

## Conflicts and open questions
- Does `UpdateItems` on 10.0.x still need the client to transform children, or does a native rigid move exist for every item type? Not exhaustively tested.

## Sources
- research notes:
  - [kicad_mcp_codebases.md § 2A, § 2 Inferences, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
  - [licensing.md § 2 (porting = derivative; fine under GPL)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- primary: commit links above; [POA tests/kicad_ref](https://github.com/ProductOfAmerica/mcp-server-kicad/tree/f5f82e02ffe17bbcba806fec35f3302ee332fefc/tests/kicad_ref)

See also: [file-format-and-version-hazards.md](file-format-and-version-hazards.md), [mcp-server-testing-practices.md](mcp-server-testing-practices.md), [ipc-api-10-vs-11.md](ipc-api-10-vs-11.md)
