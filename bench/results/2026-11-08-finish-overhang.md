<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Finish: pad-entry overhang by land kind, and two physics regressions of route-finish-ab stage 1

Boards: the 9 of route-finish-ab stage 1 with the most overhang (or the regressions below). Arms as there: A (legacy), B (finish on A's board, stage 1 code), C (route-finish defaults, finish in the portfolio); B2 = finish on A's board with this branch (`python -m kae.route.cli finish`, 1,200 s). Overhang: `kae.route.taut stats` `overhang_mm2`, split by `tools/research/routing/overhang_diag.py` into two-terminal SMD lands, other SMD lands and plated through-hole pads.

## Overhang (mm², sum over the 9 boards)

| arm | total (the stage-1 measure) | SMD lands | of them two-terminal | THT pads |
|---|---|---|---|---|
| A | 17 | 12.8 | 2.5 | 4 |
| B | 554 | 118.2 | 88.7 | 436 |
| C | 901 | 121.2 | 76.4 | 780 |
| B2 | 1,509 | 6.9 | 0.3 | 1,502 |

- **Two-terminal SMD lands (a real DFM problem):** 3 mm rails into 1206 capacitor lands (1.15 mm), 9-11 mm² each (backplane C1/C2, btmessbox C18/C19/C22, endstop C8). The neck table leaves 1206 and up unnecked in reflow, so nothing capped them. `power_copper.neck_rule` now caps such lands at their width; where a series current needs more, `land_enlarged_by_track` is raised (none on these boards).
- **Other SMD lands (also a DFM problem):** 1-2.5 mm power copper into 0.6 mm SOIC pins (gos2022 U11 pin 8: 16 mm²) and into resistors whose footprints carry alternate pads (jiran R29/R30). Power copper now keeps grown copper within `neck_len` of every SMD land at most the land's width (`land_cap`).
- **THT pads (normal practice):** 2-3 mm rails into screw-terminal and header pads (pumpbot, zx backplane, cdjc, ferro-dactyl). The measure counts them as overhang; it is unchanged here. B2's larger total is finish completing: on pumpbot stage 1's B skipped power copper for time and reverted every change.
- DRC (errors/unconnected) equal to A's on all 9 boards; entries kept, B2: endstop 15/16, gos2022 409/409, btmessbox 170/170, backplane 25/25, jiran 112/112, rhymestone 375/590, cdjc 101/101, ferro-dactyl 40/40, pumpbot 324/460.

## marksard rhymestone: copper loss A 16.1, B 15.9, C 42.2 mW_eq

`drop.rail` VCC from its source to J1 (the TRRS link to the other half): A 54.7 mV, B 54.0, C 143.6, human 25.3. Finish is not the cause (B = finish on A: -1 %). C's portfolio kept a fresh attempt (seed 11, the first clean one) whose VCC reaches J1 only along the chain of 20 LED supply pads: 292 mm, 188 mm of it 0.25 mm wide, about 440 mOhm against the human's direct 67 mm at 0.5 mm (66 mOhm). Taut keeps each branch's topology and power copper only widened VCC (up to 3 mm), so the routing made the path. The router does not know that VCC carries J1's current; that is a routing-stage question (a rail's source-to-load path), not finish.

## hbend63 btmessbox: pickup.peak A 19.7, B 17.6, C 40.8 mV (V7, LM385 reference U5 <- U3's +3.3 V core current)

The evaluator prices it as copper impedance shared by the victim port (U5's ground to ADC0) and U3's supply loop. ADC0 is in power copper's and taut's victim set (victim gaps apply), and no +3.3 V copper lies within 1 mm of it in any arm. What differs: in C, ADC0 changes layer through a third via and runs 13.6 mm on B.Cu, the only ground plane, 9.8 mm of it in the corridor between U3's and U5's ground pins (A and B: none). The via-to-via chord already crosses the corridor for 7.4 mm, so the routing placed it; taut only straightened it. Victim gaps do not model a victim cutting the return path of an aggressor's ground: keeping analog victims off the plane layer is a plan or routing rule.
