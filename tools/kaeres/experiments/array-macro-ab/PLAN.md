<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# array-macro-ab: rigid array and bus macros (pre-registered plan)

Written 2026-11-09, before any run of this experiment. Ledger J47. Code: the commit `setup.sh` records.

## Question
gecko5education's 12 x 10 RGB LED matrix accounts for about 165 of its 247 open connections when the placer scatters it (board study); locking the LEDs to the human grid removed about 110.
nekoink's series-resistor arrays ended 20-30 mm from both their ends. Does keeping such groups as rigid blocks, found from the netlist alone, lower open connections on the boards that have them, and what does it cost the parts around them?
Assembly: a regular lattice is a short pick-and-place path, one orientation and a solder joint pattern AOI can compare. A rigid block cannot be nudged, so if it takes space the rest of the board wants, the cost shows in legality and opens.

## Mechanism (`array_macros=1`, `kae.place.arrays`)
Detected on the movable parts: matrices (identical parts whose two pad nets form a product, signal nets only, fill at least 0.8, at least 16 parts) and series buses (at least 6 identical two-pin parts between the same two parts). Each block gets three gaps (0.5, 0.25, 1.0 mm) and is pinned on a legal spot near the quadratic seed before the annealer and legalizers; a soft macro did not survive (the seed legalizer scattered gecko5's LEDs, rms 11.8 mm). Radial arrays and daisy chains are not detected.

## Arms (joint-fixed, staged: `kae.joint.cli --max-iters 0 --no-modules`, restart `--resume 0.5 --final`, 900 s x sqrt(fp/40); interleaved per board)
C control; A `array_macros=1`.

## Boards: `boards.txt` (`select_boards.py`, seed `array-macro-ab-2026-11-09`)
Every board where the detector fires (matrix of 16 or more, or bus of 6 or more), one per `repo_family`, merit boards first, at most 2,000 pads,
`usable_route_test`: the scan of 4,848 tagged boards (repeated_matrix, repeated_cells aligned, line_array, radial_array, parallel_bus) finds a
matrix on 82 and a bus on 103; after the filters the whole pool is run (`boards.txt`). The tags fire far more often than the detector: keyboard
matrices put a diode in every cell, so switch nets are not a product, and they are left out by design. gecko5education is in; nekoink is not:
its series arrays are not detected (each resistor's nets reach more than its two ends), so the board-study idea for it is untested here.

## Metrics (paired, attempt 0)
`cp1`, `cpk`, completion, open connections, `legal`, per-type DRC, CPU. Own: open connections on the array's own row, column and bus nets (DRC unconnected items by net), the lattice deviation of the output (rms from the best-fit grid, parts in the array), `no_legal_spot` (arrays the pre-step could not pin). Report by tag: `repeated_matrix.*`, `parallel_bus`.

Noise: the A/A joint-loop twins (`aa-joint`; no staged A/A exists): total opens about 3%, cp1 about 0.5 pp at 200 boards. At about 150 boards, opens ratios under about 1.05 and cp1 under about 6 pp are not visible; the board-level sign test on opens is the primary test. Expected cost, as information: about 200 CPU-h.

## Decision rule (pre-registered)
`array_macros` becomes the default if A lowers total opens by at least 5% (paired sign test p < 0.05), lowers opens on the array nets on at least 60% of boards with arrays, and does not lower `legal` or cp1 beyond the noise floor (3 pp). If only array-net opens fall while other opens rise by as much, it stays off and the cost is the finding: the rigid block took room.
The whole pool runs at once; if undecided, widen the detector's pool (pads above 2,000, or more tagged boards) rather than relax the rule.

## Addendum 2026-11-13: analyse boards with an array; a fixed detector as a second arm pair (before any result is compared)
An interim plumbing check (44 boards, no decision rule applied) found that the in-run detector misses arrays the
selection found. `kae.place.arrays.macros()` reads net pins from the **movable** parts only, so a series bus whose far
end is a task-fixed connector loses its partner and is dropped. Selection scanned the human board, where nothing is fixed.
On those boards A runs the control's code path: a de-facto A/A pair.

**Which boards have the mechanism.** `scan_task_inputs.py` runs the detector on every board's task input (the corpus
board with the task's fixed parts locked: the spec-11 task record's `fixed_mech`, else the prepare step's own
`classify-mech` via `classify_fixed.py`, which matched the task record on all 4 boards that have both). Result in
`detector-scan.jsonl`: the detector as run (caeb1e0) fires on **85 of 181** boards (`boards-fire.txt`); it agrees with
the groups found on the stored control outputs on all 44 boards run so far. 85 boards is well under the plan's ~150, at
which a 5 % opens effect was already marginal.

**Amended analysis of `array-macro-ab` (C vs A):** the primary test (all three conditions of the decision rule) runs on
the 85 boards of `boards-fire.txt`. The other 96 boards are reported apart as an A/A noise check (A = C's code path
there), not pooled into the primary test. The all-board result is still shown, labelled as diluted.

**Second arm pair, `array-macro-ab2` (C2 vs A2):** the detector fixed at the commit that adds this addendum: bus ends
are looked up among every part, members are still movable parts only (`buses(..., pin_fps=all parts)`; test added).
Fixed, it fires on 140 boards; 56 of them are boards where the first detector found nothing (`boards-ab2.txt`). C2 and
A2 are `setup.sh` at that commit (control and `array_macros=1`), same chassis, run side by side on those 56 boards,
attempt 0. C2 is a new control (same code path as C, new commit), so A2 is compared with C2 only.
(mornepousse-niphargus loses its 6-part "bus" under the fix: one end net reaches a fixed part as well, so it is not a
series bus; it stays in `boards-fire.txt` for C vs A, as run.)

**Decision.** The pre-registered rule is applied to the pooled pairs (85 C/A + 56 C2/A2 = 141 boards, each paired within
its own board and arm pair), and to each set separately as a check: the default changes only if the pooled test passes
and neither set alone moves the other way beyond the noise floor. Array-net opens are counted with the detector of the
arm (`analyze.py`, `detected(..., all_pins=True)` for ab2). Cost, as information: about 56 x 2 x 1.8 CPU-h = 200 CPU-h.
