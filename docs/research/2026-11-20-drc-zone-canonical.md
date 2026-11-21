<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Zone islands in the canonical form of DRC's unconnected pairs (2026-11-20)

**Problem.** KiCad's DRC names different unconnected pairs for one file from run to run. Under counted work,
`drc.canonical_unconnected` renamed pairs to a fixed form, except in nets with a pair that names a zone.

**Mechanism.** Every filled zone island is now an item (`copper_items`, clusters). A pair's zone is mapped
to the island that holds its position. A zone net's pairs then become a minimum spanning tree between its
parts, as other nets' pairs already were.

**A/A** (kaeq job 116709, branch commit 7c91b4cd vs main's drc, KAE_BUDGET=work, 16 KiCad threads). The
board was atrivatech ch32v003's round-0 routed board: stripped input, one Freerouting session. Each code
ran 6 DRCs of the same file.

| code | distinct reports (6 runs) | GND pair as named |
|---|---|---|
| main (c2dd008a) | 2 (3 + 3) | zone-zone at (93.736, 76.59), or pad C2.1 with a track |
| this branch | 1 | zone-zone, island to island at (95.466, 69.117)-(96.705, 69.131) |

All 28 pairs are the same in every run on this branch. On main, GND's pair alone changed, and that one
pair decided whether repair round 1 split GND's plane.

**Verdict.** The pairs are now stable. Every reader of the pairs (repair `analyse`, joint journal, critical
gate, power_copper, pad_reroute and pad_trim, region_rip) sees different pairs than on main for zone nets,
so this is a method change. It needs an A/B: zone-clusters-ab's kept boards, as a fourth arm, once the
branch can be pushed.
