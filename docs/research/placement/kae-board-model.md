# kae board model and pcbnew bridge

**Status:** worked (infrastructure); edge-mate not finished.
**First published:** 2026-10-22, commit [39f8d17](https://github.com/magnetic-trowel/kicad-auto-everything/commit/39f8d1707be0300dfce0d6b81d33dd09b494c4f0) on branch `claude/vigilant-mayer-i91rrr`.

A pure-Python board model and KiCad reader, plus a bridge to KiCad's own Python (pcbnew) for the few things only KiCad can do. Every other kae path (placer, comprehension, physics, router, joint loop) reads boards through it. It matches pcbnew pad by pad to under a nanometre on the 112-board suite.

## Idea and how it works

**Board model ("Contract 1").** Frozen dataclasses in mm and degrees, KiCad's y-down frame: footprints with pads, front and back courtyards, body, Edge.Cuts pieces; nets, zones, keepouts, stackup and rules (net classes, pad-local clearance and mask overrides, rule severities, the `.kicad_dru` file). The footprint uuid is the part key (the loader synthesizes a stable one when a file has none or repeats one).

**Library frame.** Pads and courtyards are stored as the footprint is drawn (front side, 0 degrees). A pose `(x, y, rot, side)` maps a local point by

`(x, y) + R(rot) (lx, s*ly)`, with `R(a)(u, v) = (u cos a + v sin a, -u sin a + v cos a)` (KiCad's `RotatePoint`), `s = -1` on the back,

a pad's angle is `rot + s*lrot`, and layers map F<->B and In k <-> In(n-1-k). The facts this relies on were measured against pcbnew: children of a placed footprint are stored in the placed frame (back-side ones already mirrored), pad angles are absolute, footprint zones are in board coordinates, KiCad 10 names nets in place. See [transform-math-pitfalls](https://github.com/magnetic-trowel/kicad-auto-everything/blob/5e730bdc92074d2dd0a7f6bcdf82ff456f805d47/docs/topics/kicad/transform-math-pitfalls.md) (the branch's version of the topic doc; main's copy predates these checks).

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
| reader + transform vs pcbnew | 224 files (112 boards, reference + place input, task spec 4), 80,908 pads | max error 0.56 nm, angles exact | [transform-math-pitfalls at 5e730bd](https://github.com/magnetic-trowel/kicad-auto-everything/blob/5e730bdc92074d2dd0a7f6bcdf82ff456f805d47/docs/topics/kicad/transform-math-pitfalls.md) (branch version) |
| pose round trip | 20 boards, 576 random poses (166 flips, 194 non-orthogonal) | max error 1.5 nm | same |
| edge-mate | 6 outline-incomplete split-C tasks | not run with `--edge-mate`; all sweeps hold these 6 out (0/6 legal) | [place-split-c-e171267](../../../bench/results/2026-10-23-place-split-c-e171267.md) |

The worker change is a speed change with the same output; no isolated timing is recorded.

## Verdict

Worked, and is the base of every kae result. Conventions were measured on KiCad 10.0.7 only; re-run `board_acceptance.py verify` per KiCad release. A 45-degree footprint round-trips text positions 1 nm off in the harness's `transplant_placement` (harness side; seen in [joint-loop-b6](../../../bench/results/2026-10-24-joint-loop-b6.md)). Edge-mate is implemented but off and unmeasured.

## Code

- `kae/src/kae/board/{model,kicad_file,sexpr,geom,transform,sdiff,pcbnew_io}.py`, `kae/src/kae/board/kicad_scripts/pcbnew_bridge.py`, `kae/src/kae/place/{writer,edges}.py`.
- Usage and frame conventions: [kae/README.md](../../../kae/README.md). Tests `kae/tests/test_board_*.py` on the synthetic fixture `kae/tests/data/board/`.
- First appearances: model and reader [39f8d17](https://github.com/magnetic-trowel/kicad-auto-everything/commit/39f8d1707be0300dfce0d6b81d33dd09b494c4f0), sdiff [64a6858](https://github.com/magnetic-trowel/kicad-auto-everything/commit/64a6858cca92b72ead01cdf56e3b5667a71cb2bc), bridge [83afe1b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/83afe1bb6bf8e270158b12c45059aad014f0f759) (expanded in [bde4bc4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/bde4bc4ac8f15c6dfe21aee47d4b14a868c0d9da)), edge-mate [1120fc0](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1120fc039a1dbb970fe7f05bfe731f6513094e5d) and flag `--edge-mate` [d21d4a7](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d21d4a77273bad3c6ad79a97286e3aef0c4dd40e), persistent worker [9247e8b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/9247e8b6c2c0eb488a76af041bcacb8d2f8ea3ad).

## Related

[kae-placer](kae-placer.md), [kae-exact-legality](kae-exact-legality.md), [kae-comprehension-brief](kae-comprehension-brief.md), [routing area](../routing/README.md).
