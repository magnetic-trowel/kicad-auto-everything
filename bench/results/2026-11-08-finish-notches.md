<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Acute junctions in finish outputs: centrelines against exposed copper

A count of same-net centrelines meeting below 45° (legacy 0.12/m, finish 4.38/m, human 3.52/m) rose sharply under finish. An acid trap is an acute notch in the outline of a net's merged copper, so `tools/research/routing/notch_stats.py` merges each net's tracks and arcs at their widths, vias, pads and KiCad-refilled zones per layer, and counts concave outline vertices touching a track with an exposed wedge below the angle given and a depth of at least 50 or 100 µm (50 µm: about the etch-back of 1 oz copper; 100 µm: a typical minimum feature). Boards: the 40 of route-finish-ab stage 1; A legacy, B finish on A's board, C finish in the portfolio.

| 40 boards | track m | gap < 89.5°, ≥ 50 µm (per m) | gap < 80°, ≥ 50 µm (per m) | gap < 80°, ≥ 100 µm (per m) |
|---|---|---|---|---|
| A | 67.5 | 1,010 (14.96) | 875 (12.96) | 797 (11.80) |
| B | 66.5 | 1,184 (17.81) | 713 (10.72) | 665 (10.00) |
| C | 66.4 | 1,281 (19.29) | 648 (9.76) | 615 (9.26) |
| human | 78.7 | 902 (11.45) | 791 (10.04) | 735 (9.33) |

The strictest-looking column is the misleading one: entries that rule D makes square to within its 10° tolerance read 80-89.5° on one side. Below 80°, finish has fewer notches than legacy and as few as the human.

What the stages do (6 boards, notches below 80°, ≥ 50 µm; finish on A's boards at this branch): input 340, rule D tails 165, taut 151, power copper 220, after the gate 206. Power copper adds them (pads, fills, width steps); the pad ones are mostly shallow (55-95 µm) where the round end of a land-width track meets the pad corner. A rule that skipped widening inside the net's own fill did not reduce them and cost changes, so it was dropped; those notches stay.

## Fixed (finish on 6 of A's boards, DRC unchanged)

| | before | after |
|---|---|---|
| Notches below 80°, ≥ 50 µm | 252 | 206 |
| Same, all below 89.5° | 460 | 413 |
| Micro-tracks under 10 µm at a junction | 188 | 1 |

- **Taut judged an entry against the smallest of a pad's stacked shapes:** a line radial to a hotswap diode's 0.8 mm hole pad crossed the 0.9 x 1.2 mm shape around it at 65°. It now judges the merged land, as `pad_reroute` does.
- **Micro-tracks:** taut left 0.1-10 µm segments between tangent points, whose direction is noise (they were most of the "folds" and many acute pairs). Straight pieces under 10 µm are absorbed by a neighbour.
- **Folds:** a straight out-and-back inside one taut chain is cut, and a rule D tail that doubles back over the copper it joins is rejected. No dangling spike remains on the 6 boards. The 18 overlaps left are two branches along one line at a T or pad, inside the same copper.

Why the centreline count misled: on the 6 boards, finish before these fixes had 310 same-net pairs below 45°, 255 of them with a leg under 10 µm and only 2 near an exposed notch below 80° (63 pairs after the fixes, again 2 near one). The other pairs lie inside solid copper.

The 40-board table is from the stored stage-1 outputs, before these fixes; the fixes were measured on the 6 boards only.
