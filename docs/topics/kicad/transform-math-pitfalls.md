# Footprint transform math pitfalls (rotation, flip, mirror, coordinate frames)

**TL;DR**
- **Rotation, flip and mirror bugs are the most consistent bug class across all four leading KiCad MCP servers.** Fix commits: KMS 19, Konnect 12, PRO 5, POA 12 [P].
- **The textbook rotation matrix is wrong for KiCad's Y-down frame.** It agrees at 0° and 180° and fails at ±90°. It hides on symmetric parts and square courtyards [P].
- **IPC serializes footprint children in absolute board coordinates, contrary to the proto comment.** Moving only the anchor corrupts the board [P].
- **Test against KiCad's own output** (drill and Gerber coordinates, `kicad-cli` netlists, live readback) on asymmetric footprints, at all four orientations, on both sides [P/I].
- **`kae.board` reproduces pcbnew 10.0.7 to 0.56 nm on 80,908 pads (224 files).** Floating point is enough. Write through `PCB_IO_MGR`, never `LoadBoard`/`SaveBoard`, which re-net copper under pads ([§ Conventions verified](#conventions-verified-against-pcbnew-1007)) [M].
- Keep exactly one transform module; under GPL-3.0-or-later it may port KiCad's own `RotatePoint`/`Flip` with notices kept [I].

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
  - writes angles "the way KiCad formats them" (270, not −90; omitted at 0). That holds for pads, which KiCad keeps in [0, 360). Footprint `(at)` angles differ: KiCad normalizes them to (−180, 180], so a footprint at 270° is written as −90 [P] ([footprint.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/footprint.cpp) `SetOrientation`, [padstack.h @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/padstack.h));
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

## Conventions verified against pcbnew 10.0.7
Measured with [`kae/scripts/board_acceptance.py`](../../../kae/scripts/board_acceptance.py) (`verify`, `roundtrip`) on the 112 kaebench boards of task spec 4 (reference and place input: 224 files) and the fixture [`kae/tests/data/board/`](../../../kae/tests/data/board/); first written in [36ea144](https://github.com/magnetic-trowel/kicad-auto-everything/commit/36ea144833e87c32c75cab8fd6500788091c2215) [M]. Code: [`kae/src/kae/board/`](../../../kae/src/kae/board/); design in [kae-board-model](../../research/placement/kae-board-model.md).

| Area | Fact | Evidence [M] | Assumption it overturns |
|---|---|---|---|
| Frame | Child `(at u v)` is in the placed frame: `board = (x, y) + R(rot)(u, v)`, `R(a)(u, v) = (u cos a + v sin a, −u sin a + v cos a)`. Pad angle in `(at u v a)` is absolute. Back-side children are stored already mirrored: library frame `(lx, ly) = (u, −v)`, `lrot = −(a − rot)`, layers F↔B, In k ↔ In n−1−k. Any pose: `board = (x, y) + R(rot)(lx, s·ly)`, pad angle `rot + s·lrot`, `s = −1` on the back. Left-right flip of angle a reports 180 − a; top-bottom flip −a. Footprint zones are in board coordinates | 80,908 pads: max error 0.56 nm, angles exact. Round trip of 576 random poses on 20 boards (166 flips, 194 non-orthogonal angles, 11,657 pads): max 1.5 nm. KiCad rounds children to integer nm, so floats suffice | B.Cu children are not library coordinates (negating y again doubles the flip, POA's bug above); pad angles are not relative; footprint zones are not footprint-relative |
| Courtyard | DRC tests a cache (`FOOTPRINT::BuildCourtyardCaches`): deflated by a fixed 5 µm (`maxError = mmToIU(0.005)`), whatever the board's `max_error`, so touching courtyards are legal; outlines that overlap, touch or repeat are kept raw, not deflated. Pieces chain when endpoints lie within 20 µm (`chainingEpsilon`; 10 µm for Edge.Cuts); at a gap the chain keeps its own point. A contour inside an odd number of others is a hole, so a second rectangle starting inside the first cuts a notch. Arcs polygonized at 5 µm | 14,554 courtyards: straight-edged within 2.3 nm of pcbnew's cache, the 1,288 with arcs within 3.9 µm (KiCad 5 µm chords vs our 1 µm). Seven controlled variants on the fixture within 0.3 nm. Board outlines within 5.1 µm, except a zero-width spike pcbnew keeps in one slot (same area) | The DRC courtyard is neither the drawn one nor deflated by `max_error`; overlapping shapes do not simply unite (even-odd would cancel a duplicate); a gap < 20 µm still closes |
| Netclass name | A net's class collects every explicit and pattern match. One class keeps its name only if it sets all of `clearance`, `track_width`, `via_diameter`, `via_drill`, `microvia_diameter`, `microvia_drill`, `diff_pair_width`, `diff_pair_gap`, `wire_width`, `bus_width`; otherwise names join in priority order plus `Default`: `HS,Default`, `Power,HS,Default`. Patterns are regexes anchored by plain concatenation (`^` + p + `$`, no group) or anchored wildcards, so `/SW*\|/RST` matches every net starting `/S` | Equal to `GetNetClassName()` for every net of 224 files; field list found by deleting one key at a time | A class is not always one declared name; patterns are not full-match regexes |
| Read/write | `LoadBoard`/`SaveBoard` build connectivity and give copper overlapping a pad that pad's net (a GND segment under a moved pad saved as `Net-(U1B-K)`). `PCB_IO_MGR.Load/Save` with `KICAD_SEXP` does not. `PCB_IO_MGR.Load` aborts the process ("Failed to read image data") on a board with an embedded image unless `LoadBoard` ran once; a minimal warm-up board (~5 ms) fixes it | `SaveBoard` re-netted tracks or vias on 12 of 20 routed boards; with `PCB_IO_MGR` the output differs from a plain re-save only in moved footprints on all 20; one image board aborted without warm-up | A pcbnew load and save is not a no-op |
| Rotation artifacts | An off-axis rotation turns `fp_rect` into a 4-point `fp_poly` for good. Text is kept upright (angle may return 180° off, justification swapped). Items are re-sorted on save. A no-op save may add default layer user names (`"F.Adhesive"`). `GetLayerName` returns user names (`GND` for In1.Cu); use `GetStandardLayerName`. Footprints load in file order; pads of one footprint may share a uuid (four pads `2`); teardrop zones have no uuid and no fixed order | Moving the 576 footprints back restored all 20 files except 131 differences, all of these kinds | +a then −a does not restore the file; pad uuids are not unique; index pairing fails after a save |

Code relying on each row: `transform.{pad_xy,pads_xy,courtyard}` and `kicad_file` (library frame); `transform.courtyard(..., deflate=KICAD_COURTYARD_DEFLATE)`, `kicad_file.COURTYARD_CHAIN_EPS` = 0.02, `CHAIN_EPS` = 0.01, flags `courtyard_overlap`/`courtyard_gap`/`courtyard_degenerate`; `kicad_file.netclass_of`; `kicad_scripts/pcbnew_bridge.py` `_load_plain` (`write-poses`, `resave`, `edit-routing`, `text-shapes`) and `_save` (every writer); `sdiff.same/diff(..., rotation_artifacts=True)`, `pcbnew_io.pair_pads`, `kicad_file.synth_uuid`. Still loaded with `LoadBoard`: `extract` (needs the project's rules and net classes), `export-dsn`, `zone-fills`, and `import-ses` (its output goes through `_save`, but connectivity built on load may already have re-netted copper under pads, kept pre-routes included). `_load_plain`/`_save` fall back to `LoadBoard`/`SaveBoard` when `PCB_IO_MGR` is missing.

## Recommendations for our system
- **Exactly one transform module** (local↔board, rotate, flip, mirror). `kae.board.transform` is it: floating point stays within 1.5 nm of pcbnew's integer-nm results, so integer arithmetic and KiROUND-by-format-era (POA's approach) are not needed for positions [M]. A direct port of KiCad's `trigo`/`RotatePoint`/`FOOTPRINT::Rotate`/`Flip` (copyright notices kept) and POA's `tests/kicad_ref` remain options under GPL-3.0-or-later [I].
- **Write through KiCad's plain reader and writer** (`PCB_IO_MGR`, `KICAD_SEXP`), never `LoadBoard`/`SaveBoard`, whenever nothing but poses or routing may change [M].
- **Oracle-pin it:** compare against `kicad-cli` drill and Gerber coordinates and against IPC readback, on asymmetric fixtures (e.g. Antmicro boards) at 0/90/180/270°, on both sides [I].
- **Prefer native IPC operations** (`FlipItems`, rigid moves via KiCad) over re-computing child geometry. Never trust proto comments about frames; verify by readback [I].
- **Reject angle inputs KiCad cannot parse.** Normalize angles to KiCad's spelling before writing: footprints in (−180, 180], pads in [0, 360), omitted at 0 [I].

## Conflicts and open questions
- The conventions were measured on 10.0.7 only. Re-run `board_acceptance.py verify` and `roundtrip` for each KiCad release.
- Does `UpdateItems` on 10.0.x still need the client to transform children, or does a native rigid move exist for every item type? Not exhaustively tested.

## Sources
- research notes:
  - [kicad_mcp_codebases.md § 2A, § 2 Inferences, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
  - [licensing.md § 2 (porting = derivative; fine under GPL)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- measured [M]: [`kae/scripts/board_acceptance.py`](../../../kae/scripts/board_acceptance.py), [`kae/tests/`](../../../kae/tests/) (`test_board_*.py`), fixture and pcbnew golden data in [`kae/tests/data/board/`](../../../kae/tests/data/board/); KiCad source [footprint.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/footprint.cpp) `BuildCourtyardCaches` (5 µm `maxError`, 20 µm `chainingEpsilon`)
- primary: commit links above; [POA tests/kicad_ref](https://github.com/ProductOfAmerica/mcp-server-kicad/tree/f5f82e02ffe17bbcba806fec35f3302ee332fefc/tests/kicad_ref)

See also: [file-format-and-version-hazards.md](file-format-and-version-hazards.md), [mcp-server-testing-practices.md](mcp-server-testing-practices.md), [ipc-api-10-vs-11.md](ipc-api-10-vs-11.md)
