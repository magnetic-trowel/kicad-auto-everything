# Footprint transform math pitfalls (rotation, flip, mirror, coordinate frames)

**TL;DR**
- **Rotation, flip and mirror bugs are the most consistent bug class across all four leading KiCad MCP servers.** Fix commits: KMS 19, Konnect 12, PRO 5, POA 12 [P].
- **The textbook rotation matrix is wrong for KiCad's Y-down frame.** It agrees at 0° and 180° and fails at ±90°. It hides on symmetric parts and square courtyards [P].
- **IPC serializes footprint children in absolute board coordinates, contrary to the proto comment.** Moving only the anchor corrupts the board [P].
- **Test against KiCad's own output** (drill and Gerber coordinates, `kicad-cli` netlists, live readback) on asymmetric footprints, at all four orientations, on both sides [P/I].
- **`kae.board` reproduces pcbnew 10.0.7 to 0.56 nm on 80,908 pads of 224 boards.** Several pcbnew behaviours contradict common assumptions: a fixed 5 µm courtyard deflation, composite netclass names, and `LoadBoard`/`SaveBoard` giving copper under a pad that pad's net ([§ Conventions verified](#conventions-verified-against-pcbnew-1007)) [C].

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

## Conventions verified against pcbnew 10.0.7
Measured with [`kae/scripts/board_acceptance.py`](../../../kae/scripts/board_acceptance.py) (`verify`, `roundtrip`) on the 112 kaebench boards prepared with task spec 4 (reference and place inputs, 224 files) and on the fixture in [`kae/tests/data/board/`](../../../kae/tests/data/board/) [C]. Code: [`kae/src/kae/board/`](../../../kae/src/kae/board/). Each item gives the fact, the evidence, the code that relies on it, and the assumption it overturns.

### Frames and the transform
- **Fact.** A footprint child's `(at u v)` is in the placed footprint frame: `board = (x, y) + R(rot)(u, v)`, `R(a)(u, v) = (u cos a + v sin a, −u sin a + v cos a)`.
  - A pad's angle in `(at u v a)` is absolute: the footprint angle is included.
  - Children of a back-side footprint are stored already mirrored about the footprint's x axis. The library frame is `(lx, ly) = (u, −v)`, `lrot = −(a − rot)`, with layers flipped (F↔B; In k ↔ In n−1−k for n copper layers).
  - For any pose, `board = (x, y) + R(rot)(lx, s·ly)` and the pad angle is `rot + s·lrot`, with `s = −1` on the back.
  - A left-right flip of a part at angle a reports 180 − a; a top-bottom flip reports −a.
  - Zones inside a footprint are stored in board coordinates.
- **Evidence.** 80,908 pads: max |transform − pcbnew| 0.56 nm, pad angles exact. A 20-board round trip set 576 random poses (166 flips, 194 non-orthogonal angles; 11,657 pads): max 1.5 nm. KiCad rounds children to integer nm, so floating point is enough [C].
- **Code.** `transform` (`pad_xy`, `pads_xy`, `courtyard`), `kicad_file` (library frame), `pcbnew_io.write_poses`.
- **Assumption overturned.**
  - The file does not hold library coordinates with the side applied on load: B.Cu children are already mirrored, so negating y again doubles the flip (POA's bug above).
  - Pad angles are not relative: treating them so adds the footprint angle twice.
  - Footprint zones are not footprint-relative.

### Courtyards
- **Fact.** KiCad's DRC tests a cached copy of each courtyard (`FOOTPRINT::BuildCourtyardCaches`):
  - It is deflated by a fixed 5 µm, whatever the board's `max_error` (measured at 0.005 and 0.01 mm), so touching courtyards are legal. Outlines that overlap, touch or repeat are kept raw and not deflated.
  - Shapes are chained when endpoints lie within 20 µm (10 µm for Edge.Cuts). At a gap the chain keeps the point it reached first and drops the joining shape's near endpoint; an arc whose start was snapped is redrawn through (chain point, mid, end).
  - Each closed contour is nested by its first point. A contour inside an odd number of others is a hole of its parent, so a second rectangle whose first corner lies in the first cuts a notch instead of adding area. The remaining outlines are united.
  - Arcs and circles are polygonized at 5 µm.
- **Evidence.**
  - 14,554 courtyards: straight-edged ones within 2.3 nm of pcbnew's cache; the 1,288 with arcs within 3.9 µm (KiCad's 5 µm chords against our 1 µm).
  - Seven controlled variants on the fixture (duplicated, touching, crossing, disjoint and notched outlines; a 10 µm gap) match within 0.3 nm.
  - Reference-board outlines match within 5.1 µm, except one where pcbnew keeps a zero-width spike in a slot hole (same area). Place inputs differ where staged footprints carry Edge.Cuts, which the loader leaves out of `Board.outline` by design [C].
- **Code.** `geom` (chaining, nesting), `transform.courtyard(..., deflate=KICAD_COURTYARD_DEFLATE)`, footprint flags `courtyard_overlap`, `courtyard_gap`, `courtyard_degenerate`.
- **Assumption overturned.**
  - The DRC courtyard is neither the drawn one nor deflated by `max_error`.
  - Overlapping shapes do not simply unite; an even-odd fill would even cancel a duplicated outline.
  - A gap under 20 µm still yields a courtyard.

### Netclass names
- **Fact.** A net's effective netclass collects every class from explicit assignments and matching patterns.
  - A single class keeps its own name if it sets all of `clearance`, `track_width`, `via_diameter`, `via_drill`, `microvia_diameter`, `microvia_drill`, `diff_pair_width`, `diff_pair_gap`, `wire_width` and `bus_width`.
  - Otherwise the name joins the classes in priority order, plus `Default` to fill the gaps, with commas: `HS,Default`, `Power,HS,Default`. `diff_pair_via_gap`, `line_style`, colours and `tuning_profile` do not count.
  - A pattern matches as a regex anchored by plain concatenation (`^` + pattern + `$`, no group), or as an anchored wildcard. So `/SW*|/RST` matches every net that starts with `/S`.
- **Evidence.** Names equal pcbnew's `GetNetClassName()` for every net on 224 files. The field list was found by deleting one key at a time on the fixture [C].
- **Code.** `kicad_file.netclass_of`; `Rules.netclasses` holds merged entries for composite names.
- **Assumption overturned.** A net's class is not always one declared name (a lookup of `HS,Default` fails), and patterns are not full-match regexes.

### Reading and writing with pcbnew
- **Fact.** `pcbnew.LoadBoard` and `SaveBoard` build connectivity, which gives copper overlapping a pad that pad's net: a GND segment under a moved pad was saved as `Net-(U1B-K)`.
  - KiCad's plain reader and writer, `pcbnew.PCB_IO_MGR.Load`/`Save` with `PCB_IO_MGR.KICAD_SEXP`, do not.
  - `PCB_IO_MGR.Load` aborts the process ("Failed to read image data", an uncaught `IO_ERROR`) on a board with an embedded image, unless `LoadBoard` has run once in the process. Loading a minimal board first (about 5 ms) sets up the image handlers.
- **Evidence.**
  - With `SaveBoard`, writing random poses re-netted tracks or vias on 12 of 20 routed boards.
  - With the plain reader and writer, the written file differs from a plain re-save of the input only in the moved footprints, on all 20 boards.
  - One board with an image aborted without the warm-up [C].
- **Code.** `kicad_scripts/pcbnew_bridge.py` (`write-poses`, `resave`). `extract` still uses `LoadBoard`, because it also needs the project's rules and net classes.
- **Assumption overturned.** A load and save through pcbnew is not a no-op, and `SaveBoard` does not write the board as it was in memory.

### Rotation artifacts, identities and order
- **Fact.**
  - Rotating to an off-axis angle turns an `fp_rect` into a 4-point `fp_poly` for good.
  - Text is kept upright, so a field's angle may come back 180° off with left and right justification swapped.
  - A footprint's items are re-sorted on save.
  - A no-op save can add default user names to the layer table (`"F.Adhesive"`).
  - `GetLayerName` returns user names (`GND` for In1.Cu); use `GetStandardLayerName` for canonical names.
  - Footprints load in file order.
  - Pads of one footprint may share a uuid (four pads `2` of one connector).
  - Teardrop zones have no uuid and are saved in no fixed order.
- **Evidence.** Moving the 576 footprints back restored all 20 files except 131 differences, all of these kinds [C].
- **Code.** `sdiff.diff(..., rotation_artifacts=True)` (teardrops keyed by content); `pcbnew_io.pair_pads` (file order, else uuid, number and position); `kicad_file.synth_uuid`.
- **Assumption overturned.** Rotating by +a then −a does not restore the file, pad uuids are not unique, and items cannot be paired by index after a save.

## Recommendations for our system
- **Exactly one transform module** (local↔board, rotate, flip, mirror). Under GPL-3.0-or-later it may be a direct port of KiCad's `trigo`/`RotatePoint`/`FOOTPRINT::Rotate`/`Flip`, keeping KiCad's copyright notices; POA's `tests/kicad_ref` ports and its October fixes are reusable for the same reason [I]. `kae.board.transform` is that module: floating point stays within 1.5 nm of pcbnew's integer-nm results, so integer arithmetic is not needed for positions [C].
- **Write poses through KiCad's plain reader and writer** (`PCB_IO_MGR`), never `LoadBoard`/`SaveBoard`, when nothing but poses may change [C].
- **Oracle-pin it:** compare against `kicad-cli` drill and Gerber coordinates and against IPC readback, on asymmetric fixtures (e.g. Antmicro boards) at 0/90/180/270°, on both sides [I].
- **Prefer native IPC operations** (`FlipItems`, rigid moves via KiCad) over re-computing child geometry. Never trust proto comments about frames; verify by readback [I].
- **Reject angle inputs KiCad cannot parse.** Normalize angles to KiCad's spelling before writing [I].

## Conflicts and open questions
- Does `UpdateItems` on 10.0.x still need the client to transform children, or does a native rigid move exist for every item type? Not exhaustively tested.
- The conventions above were measured on 10.0.7 only. Re-run `board_acceptance.py verify` and `roundtrip` for each KiCad release.

## Sources
- research notes:
  - [kicad_mcp_codebases.md § 2A, § 2 Inferences, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
  - [licensing.md § 2 (porting = derivative; fine under GPL)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- primary: commit links above; [POA tests/kicad_ref](https://github.com/ProductOfAmerica/mcp-server-kicad/tree/f5f82e02ffe17bbcba806fec35f3302ee332fefc/tests/kicad_ref)
- computed [C]: [`kae/scripts/board_acceptance.py`](../../../kae/scripts/board_acceptance.py) (`verify`, `roundtrip`), [`kae/tests/test_board_*.py`](../../../kae/tests/), fixture and pcbnew golden data in [`kae/tests/data/board/`](../../../kae/tests/data/board/)

See also: [file-format-and-version-hazards.md](file-format-and-version-hazards.md), [mcp-server-testing-practices.md](mcp-server-testing-practices.md), [ipc-api-10-vs-11.md](ipc-api-10-vs-11.md)
