# kae board model and pcbnew bridge

Scope: defensive publication of the pure-Python board model, KiCad reader, geometry, structural diff, pcbnew bridge, pose writers and edge-mate. Not here: frame-convention pitfalls -> [transform-math-pitfalls](../../topics/kicad/transform-math-pitfalls.md).
Keys: Contract 1, board model, library frame, pose transform, RotatePoint, kicad_file.load, S-expression tokenizer, geom.py, ConvertOutlineToPolygon, sdiff.py, on_board, pcbnew bridge, KAE_KICAD_PYTHON, KAE_KICAD_WRAP, write_poses, verify, TransformTextToPolySet, KAE_PCBNEW_WORKER, sexpr writer, edge-mate, board_acceptance.py

**Status:** worked (infrastructure); edge-mate not finished.
**First published:** 2026-10-22, commit [39f8d17](https://github.com/magnetic-trowel/kicad-auto-everything/commit/39f8d1707be0300dfce0d6b81d33dd09b494c4f0) on branch `claude/vigilant-mayer-i91rrr`.

A pure-Python board model and KiCad reader, plus a bridge to KiCad's own Python (pcbnew) for the few things only KiCad can do. Every other kae path (placer, comprehension, physics, router, joint loop) reads boards through it. It matches pcbnew pad by pad to under a nanometre on the 112-board suite.

## Idea and how it works

**Board model ("Contract 1").** Frozen dataclasses in mm and degrees, KiCad's y-down frame: footprints with pads, front and back courtyards, body, Edge.Cuts pieces; nets, zones, keepouts, stackup and rules (net classes, pad-local clearance and mask overrides, rule severities, the `.kicad_dru` file). The footprint uuid is the part key (the loader synthesizes a stable one when a file has none or repeats one).

**Library frame.** Pads and courtyards are stored as the footprint is drawn (front side, 0 degrees). A pose `(x, y, rot, side)` maps a local point by

`(x, y) + R(rot) (lx, s*ly)`, with `R(a)(u, v) = (u cos a + v sin a, -u sin a + v cos a)` (KiCad's `RotatePoint`), `s = -1` on the back,

a pad's angle is `rot + s*lrot`, and layers map F<->B and In k <-> In(n-1-k). The facts this relies on were measured against pcbnew: children of a placed footprint are stored in the placed frame (back-side ones already mirrored), pad angles are absolute, footprint zones are in board coordinates, KiCad 10 names nets in place. See [transform-math-pitfalls § Conventions verified](../../topics/kicad/transform-math-pitfalls.md#conventions-verified-against-pcbnew-1007).

**Reader.** `kicad_file.load` parses `.kicad_pcb` (KiCad 10, tolerant of 5-9) with the sibling `.kicad_pro` and `.kicad_dru`. A fast S-expression tokenizer first strips zone fills and embedded files using the pretty-printer's indentation (checked by balanced-paren counts, with an exact scan as fallback). Median load 0.05 s per board, 1.1 s for a 17.7 MB file ([kae/README.md](../../../kae/README.md)).

**Geometry.** `geom.py` turns arcs into polygons with chord error <= tol and chains Edge.Cuts or courtyard pieces into polygons with holes the way KiCad's `ConvertOutlineToPolygon` does (endpoints within eps, odd nesting = hole, union of outlines). Courtyard caching follows KiCad (5 um deflation, 20 um chaining).

**Structural diff.** `sdiff.py` diffs two boards keyed by (head, uuid) with a numeric tolerance and an optional equivalence for pcbnew's rotation artefacts (an off-axis `fp_rect` stored as `fp_poly`, upright text flipped by 180 degrees). `on_board` decides whether a footprint is placed or staged (kaebench stages unplaced parts 10 mm right of the board).

**pcbnew bridge.** KiCad's Python runs as a subprocess (`KAE_KICAD_PYTHON` or the `KAE_KICAD_WRAP` prefix, for example an Apptainer command) executing `kicad_scripts/pcbnew_bridge.py`: `extract` (poses, pads, courtyards, outline, rules as pcbnew sees them), `write_poses` (KiCad's own Flip, SetOrientation, SetPosition, then save, so nothing but poses changes), `verify` (reader and transform vs pcbnew, pad by pad) and text-to-polygon glyph outlines (`TransformTextToPolySet`) used by the copper-text and silkscreen legality checks ([kae-exact-legality](kae-exact-legality.md)). Since [9247e8b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/9247e8b6c2c0eb488a76af041bcacb8d2f8ea3ad) one long-lived KiCad Python per calling thread imports pcbnew once and forks a child per call: fresh pcbnew state each call without KiCad's ~1 s start-up (`KAE_PCBNEW_WORKER=0` restores one process per call).

**Pose writers.** `place/writer.py` has a `pcbnew` writer (reference) and a `sexpr` writer: a pure-text edit of the footprint's `(at x y rot)`, every pad's and text's absolute angle and the board-frame zones and points the footprint owns (same-side moves only). `auto` falls back to `sexpr` when KiCad's Python does not answer (for example inside a sandbox).

**Edge-mate (not finished).** Card-edge connectors and sensor notches carry open Edge.Cuts pieces; staged off-board they leave the outline open, or closed without the notch. `edges.mate(board)` finds the near-unique pose: with an open outline, a 90-degree-multiple rotation and translation that put every free end of the footprint's pieces on a dangling end of the board's pieces; with a closed outline, the free ends on one straight boundary segment with the pieces inside (a notch), nearest the segment middle. Mated parts become fixed and their pieces join the outline. `kae/scripts/edgecuts_place_audit.py` lists such carriers per task.

## What we tried

`kae/scripts/board_acceptance.py {verify,roundtrip,place,loadtime,loadall}` on the prepared kaebench tasks: verify reader and transform on every pad against pcbnew; round-trip random poses through `write_poses` and re-read them.

## Results

| check | n | result | source |
|---|---|---|---|
| reader + transform vs pcbnew | 224 files (112 boards, reference + place input, task spec 4), 80,908 pads | max error 0.56 nm, angles exact | [transform-math-pitfalls](../../topics/kicad/transform-math-pitfalls.md#conventions-verified-against-pcbnew-1007) |
| pose round trip | 20 boards, 576 random poses (166 flips, 194 non-orthogonal) | max error 1.5 nm | same |
| edge-mate | 6 outline-incomplete split-C tasks | not run with `--edge-mate`; all sweeps hold these 6 out (0/6 legal) | [place-split-c-e171267](../../../bench/results/2026-10-23-place-split-c-e171267.md) |

The worker change is a speed change with the same output; no isolated timing is recorded.

## Writing boards

Decisions from the 2026-11 audit (K6, K8, K11 and the I/O items), measured with [`tools/research/kicad-io/`](../../../tools/research/kicad-io/) on KiCad 10.0.7.

**KiCad's plain writer stays (K6).** kae writes poses, SES imports and routing edits through `PCB_IO_MGR.Load`/`Save` (KICAD_SEXP), not through a byte-preserving splice as [file-format-and-version-hazards](../../topics/kicad/file-format-and-version-hazards.md) recommends:
- Only KiCad can do the work: `ImportSpecctraSES` and `FOOTPRINT::Flip` (pads, layers, padstacks, 3D models) have no stdlib equivalent, and the splice writer (`place/writer.py` `sexpr`) handles same-side moves only.
- The losses reported for `SaveBoard` come from two places. Its connectivity step (`BuildConnectivity` + `SynchronizeNets...`, [pcbnew_scripting_helpers.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/python/scripting/pcbnew_scripting_helpers.cpp)) re-nets copper; the plain writer skips it. The writer's `std::set`s ([pcb_io_kicad_sexpr.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcb_io/kicad_sexpr/pcb_io_kicad_sexpr.cpp)) merge exact duplicates in both.
- Round trip on 27 corpus boards (`roundtrip_audit.py`: 4 each stamped 20171130, 20211014, 20221018, 20240108, 20241229; 7 stamped 20260206, 3 of them with embedded files or images): pcbnew's inventory (footprints, pads and their nets, tracks and vias and their nets, zones and their nets, nets) was identical after load+save on all 27, and a second save was idempotent. Changes found: the stamp went to 20260206 on all 20 older boards; 24 of 98 `gr_poly` on one KiCad 7 board (exact duplicates on B.SilkS) were merged; KiCad 10 boards differed only in duplicate polygon points and regenerated dimension texts; embedded-file and image counts were unchanged. `LoadBoard`+`SaveBoard` re-netted nothing on these unedited boards; the 12-of-20 re-netting was measured after moving parts (transform-math-pitfalls at [5e730bd](https://github.com/magnetic-trowel/kicad-auto-everything/blob/5e730bdc92074d2dd0a7f6bcdf82ff456f805d47/docs/topics/kicad/transform-math-pitfalls.md#reading-and-writing-with-pcbnew)).
- What guards it now: the bridge never falls back to `LoadBoard`/`SaveBoard` (it fails instead). Every write re-reads the file it wrote and compares it with the board in memory: stamp, counts, every pad's, routing item's and zone's net, and every drawing. A file whose copper items, copper drawings or nets differ is never moved into place (`PcbnewError`). The report gets `data` hazards for a format upgrade (`kicad_format_upgraded`), merged duplicates (`kicad_write_merged_duplicate_drawings`) and lost non-copper drawings (`kicad_write_lost_items`).

**Pre-10 boards (K8).** The pcbnew writers upgrade the stamp (a warn hazard says so); the text writers in `route/critical_write.py` refuse boards stamped 20241229 or lower (`KiCadVersionError`), because KiCad 9 rejects named nets and KiCad 6/7 a `(locked yes)` on a track. Refusing is simpler and safer than emitting a second dialect nobody tests: by the time those writers run, every kae route board except the original input has already been written by KiCad 10. Removing items stays allowed in any format, and `routing()` reads both lock spellings.

**SES import (#7, routing #7).** `import_ses` reads with the plain reader like the other writers; nothing in `FromSESSION` needs the project. `ImportSpecctraSession` itself ends with `BOARD::BuildConnectivity`, whose net propagation moves copper that touches a single pad onto that pad's net ([connectivity_algo.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/connectivity/connectivity_algo.cpp)). So the bridge records the net of every item on the board before the import, puts back any that changed (`renetted`; hazard `preroute_overlaps_foreign_pad`), and `route.bridge.import_session` compares the session's segments, arcs and vias per net with what landed: copper on a net the session did not route is a block hazard (`ses_import_wrong_net`, and the repair round is discarded); skipped items are a warn (`ses_import_incomplete`). On 30 real repair-round imports (38k kept items) counts matched exactly and nothing was re-netted.

**Routing edits (#9).** `edit_routing` refuses, before writing, a track on a net the board does not have (or no net) or on a layer that is not an enabled copper layer (`PcbnewRefused`); the repair loop drops that round and reports it. Before, such a track went in on net 0. The round trip above shows one way it happens: kae's reader keeps KiCad 5 net names such as `~RTS` that KiCad 10 reads as `~{RTS}` (13 nets on one board).

**Footprint keys (#12).** The splice writer finds footprints by `kicad_file.footprint_keys`, the loader's own keys (KiCad 5 tstamps as KIIDs, synthesized keys for missing or repeated uuids).

**Angles and KeepUpright (K11).** The splice writer writes footprint angles in (−180, 180] as KiCad's `FOOTPRINT::SetOrientation` does (measured: 270 and −90 both written −90; pads and texts stay in [0, 360)). Neither writer applies `KeepUpright`, unlike KiCad's rotate command and properties dialog (`FOOTPRINT::Rotate`). For keep-upright footprint texts KiCad draws the glyphs readable anyway (`PCB_TEXT::GetDrawRotation`); the written angle and, for left/right-justified texts, the side of the anchor the glyphs fall on differ. `text_shapes` models the turned glyphs with `Rotate`, so for justified texts kae's silk legality model and the written board can disagree. `pcbnew_io.write_poses(keep_upright=True)` (env `KAE_WRITER_KEEP_UPRIGHT=1`) is the A/B arm; the default is unchanged until it runs.

## Verdict

Worked, and is the base of every kae result. Conventions were measured on KiCad 10.0.7 only; re-run `board_acceptance.py verify` per KiCad release. A 45-degree footprint round-trips text positions 1 nm off in the harness's `transplant_placement` (harness side; seen in [joint-loop-b6](../../../bench/results/2026-10-24-joint-loop-b6.md)). Edge-mate is implemented but off and unmeasured.

## Code

- `kae/src/kae/board/{model,kicad_file,sexpr,geom,transform,sdiff,pcbnew_io}.py`, `kae/src/kae/board/kicad_scripts/pcbnew_bridge.py`, `kae/src/kae/place/{writer,edges}.py`.
- Usage and frame conventions: [kae/README.md](../../../kae/README.md). Tests `kae/tests/test_board_*.py` on the synthetic fixture `kae/tests/data/board/`.
- First appearances: model and reader [39f8d17](https://github.com/magnetic-trowel/kicad-auto-everything/commit/39f8d1707be0300dfce0d6b81d33dd09b494c4f0), sdiff [64a6858](https://github.com/magnetic-trowel/kicad-auto-everything/commit/64a6858cca92b72ead01cdf56e3b5667a71cb2bc), bridge [83afe1b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/83afe1bb6bf8e270158b12c45059aad014f0f759) (expanded in [bde4bc4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/bde4bc4ac8f15c6dfe21aee47d4b14a868c0d9da)), edge-mate [1120fc0](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1120fc039a1dbb970fe7f05bfe731f6513094e5d) and flag `--edge-mate` [d21d4a7](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d21d4a77273bad3c6ad79a97286e3aef0c4dd40e), persistent worker [9247e8b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/9247e8b6c2c0eb488a76af041bcacb8d2f8ea3ad).

## Related

[kae-placer](kae-placer.md), [kae-exact-legality](kae-exact-legality.md), [kae-comprehension-brief](kae-comprehension-brief.md), [routing area](../routing/README.md).
