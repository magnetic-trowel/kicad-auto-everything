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
Up to 100 boards where the detector fires (matrix of 16 or more, or bus of 6 or more), one per `repo_family`, merit boards first (gecko5education and nekoink among them), at most 2,000 pads, `usable_route_test`.

## Metrics (paired, attempt 0)
`cp1`, `cpk`, completion, open connections, `legal`, per-type DRC, CPU. Own: open connections on the array's own row, column and bus nets (DRC unconnected items by net), the lattice deviation of the output (rms from the best-fit grid, parts in the array), `no_legal_spot` (arrays the pre-step could not pin). Report by tag: `repeated_matrix.*`, `parallel_bus`.

Noise: the A/A joint-loop twins (`aa-joint`; no staged A/A exists): total opens about 3%, cp1 about 0.5 pp at 200 boards. At 100 boards, opens ratios under about 1.07 and cp1 under about 7 pp are not visible; the board-level sign test on opens is the primary test.

## Decision rule (pre-registered)
`array_macros` becomes the default if A lowers total opens by at least 5% (paired sign test p < 0.05), lowers opens on the array nets on at least 60% of boards with arrays, and does not lower `legal` or cp1 beyond the noise floor (3 pp). If only array-net opens fall while other opens rise by as much, it stays off and the cost is the finding: the rigid block took room.
Extension: if undecided at 100 boards, run the rest of the pool.
