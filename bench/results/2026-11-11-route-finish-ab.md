<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Routing-pipeline redesign A/B (route-finish-ab, c8188eb): verdicts

Plan and pre-registered criteria: [PLAN.md §§4, 9, 10](../../tools/kaeres/experiments/route-finish-ab/PLAN.md). Experiments `route-finish-ab` (A, C, D, E on the 213 physics-set boards) and `route-finish-ab-twin` (A's twin on the 40 stage-1 boards), code c8188eb (score v12, task spec 10), KiCad 10.0.7, intents `compiled-9867d0b`. B is kae.route.cli finish on A's kept boards, scored in its own kaebench run. A0r is merge3-ab's arm re-scored at this harness. Tables: `tools/kaeres/experiments/route-finish-ab/analyze.py --exp route-finish-ab --twin route-finish-ab-twin` (all boards below), then the same for `route-finish-ab-s1r` (the 40 stage-1 boards, same runs).

## Verdicts

| Question | Verdict |
|---|---|
| Check: A/A twin | No flips in cp1 or clean_strict on the 40 boards; completion and errors within ±0.002 and ±0.15. The twin covers small boards only; there is no noise estimate for the large ones |
| Q1 finish alone (B vs A) | Routing: **passes** (no board more unconnected, 1 board with more DRC errors, cp1, clean_strict and completion equal). Entries: oblique + acute 8,474 → 5,076 (**pass**). SMD overhang: entries down, area 60 → 88 mm² not beyond noise (**pass**). Time: **fails** the < 5 % rule (16 of 211 boards skipped a part; B's budget is restart.py's estimate). Physics: **not called**, B has no offsets (floor-only reading: loss.copper 99 better / 4 worse, drop.rail 118 / 5) |
| Q2 redesign as default (C vs A) | **Fails on completion**: 0.9719 → 0.9672, CI lower bound -0.0092 below the -0.005 margin (26 boards worse, 8 better). The losses sit on large boards (dilemma 210 → 383 open, gecko5, jetson J2032, zotino, sdi-mipi, mystorm, kestrel, PolarFire), where the twin gives no noise estimate. All other gates pass: cp1 +1 board, errors equal, no invalid output, entries -77 %, SMD overhang (entries down, area 63 → 101 mm² not beyond noise), notches, loss.copper (median 0.65; 99 better / 4 worse, offsets used) and drop.rail (0.65; 137 / 16) |
| Q2 on the 40 stage-1 boards | **Passes every gate**, including completion (-0.0016, CI to -0.0045). All 10 boards excluded in stage 1 for uuid churn are in, and none is invalid in A or C |
| Q3 C vs B (descriptive) | C adds one clean board and entries fall a further 38 % against B; completion and errors are not significantly different |
| Q4 import tails (D vs C) | **Not adopted**: routing not worse, but entries do not fall further (median ratio 1.00). Physics not called (no offsets for D; floor-only reading is mixed) |
| Q5 ground vias (E vs C) | **Not adopted**: cp1 loses 2 boards (CI to -0.024) and DRC errors rise (p 0.046). supply.peak 34 better / 16 worse on the 50 boards with vias, floor-only (no offsets for E) |
| Notches (gap < 80°, ≥ 50 µm, per m) | C 17.7, human 14.9, A 21.5: C is 19 % above human, but the CI of the difference (-0.9 to 6.7) includes 0, so the gate **passes** as registered. 40-board subset: C 12.1, human 10.0, CI -4.5 to 10.0 |
| THT overhang (reported, not gated) | 168 mm² in A, 4,085 in C, 1,037 in human: power copper's wide rails into THT pads |

## Gaps and artefacts

- B is missing on zotino and sycamore (the gate crash, fixed after the run). Four further B outputs read invalid (cmnybo chip-lcd-dip, krzys zx2-backplane, usbarmory, amoeba stabilizer). Their copper outside routing is identical to A's valid outputs. The cause is the fork's own prepare: zones and footprints without unique uuids (legacy tstamps, missing zone uuids) are re-keyed in file order, and that order differs between two prepares of the same board. They are left out of B (`--drop`). Task spec 10 does not make uuids deterministic for duplicates; this needs a prepare fix of its own.
- dasduino has no A physics and FONA-800 no D physics (intent status crash, fixed in 76d6aad after the run). PolarFire and sdi-mipi have no human physics. usbarmory's zone refill hangs. kocer and J2032 are out of physics. Base physics exists on about 150 boards per arm. Offsets exist for human, A and C only; the user stopped the B, D and E offsets.
- A0r: 49 boards are uuid churn (old outputs against spec-10 tasks) and are left out; 3 more read invalid by the same re-keying.
- Suspicious: 23 `drop.rail` terms have negative values (e.g. -1.6 mV) with zero contribution. A ratio across a sign change is meaningless, so the evaluator's drop sign needs a look.
- Seven boards declare inner layers no copper uses ("route only on layers the board uses", spec 11, was not in main): PLAN.md §10.


# Full tables, all 213 boards
Arms A0, A0r, A, A2, B, C, D, E; methods A `a7157c78c659`, C `1f103cfc208c`, D `ce768d6a918b`, E `dec0bef13f19`, A2 `962cf139f3d4`; DRC evaluator `a35ac71c2313`; 213 boards.

#### Pre-registered gates

#### Check: A/A twin of A (flips expected from noise alone)

| criterion | verdict | detail |
|---|---|---|
| cp1 | PASS | A 0.325 A2 0.325 diff 0.0 CI (0.0, 0.0) p 1.0 +0/-0 n 40 |
| clean_strict | PASS | A 0.325 A2 0.325 diff 0.0 CI (0.0, 0.0) p 1.0 +0/-0 n 40 |
| completion | PASS | A 0.9881 A2 0.9876 diff -0.0005 CI (-0.0015, 0.0) p 0.5 n 40 |
| DRC errors / board | PASS | A 25.5 A2 25.525 diff 0.025 CI (-0.075, 0.15) p 1.0 n 40 |


#### Q1: finish alone (B against A)

| criterion | verdict | detail |
|---|---|---|
| no board with more unconnected than A | PASS | 0 of 207: [] |
| at most 2 boards with more DRC errors than A | PASS | 1 of 207: ['feastorg-protokit-protoplus'] |
| B loses at most 1 clean board | PASS | +0/-0 |
| cp1 | PASS | A 0.2754 B 0.2754 diff 0.0 CI (0.0, 0.0) p 1.0 +0/-0 n 207 |
| clean_strict | PASS | A 0.2754 B 0.2754 diff 0.0 CI (0.0, 0.0) p 1.0 +0/-0 n 207 |
| completion | PASS | A 0.9728 B 0.973 diff 0.0002 CI (0.0, 0.0005) p 0.25 n 207 |
| DRC errors / board | PASS | A 29.4058 B 29.3768 diff -0.029 CI (-0.0625, 0.0) p 0.1094 n 207 |
| oblique + acute entries fall | PASS | sum A 8474 B 5076, median ratio 0.457, p 5e-05, n 205 |
| overhang on SMD lands, entries: no rise beyond noise | PASS | A 598 B 482 mean diff -0.5631 CI [-0.8971, -0.2524] p 0.00055 boards up 21 down 46 |
| overhang on SMD lands, mm2: no rise beyond noise | PASS | A 59.98 B 87.88 mean diff 0.1354 CI [-0.0247, 0.3169] p 0.13 boards up 33 down 47 |
| loss.copper: median at most 1, more signal-better than signal-worse | PASS | median 0.730, ambiguous 6, noise 11, signal better 99, signal worse 4 |
| drop.rail: median at most 1, more signal-better than signal-worse | PASS | median 0.798, ambiguous 10, noise 39, signal better 118, signal worse 5 |
| no observable with signal-worse above signal-better by more than 2 | PASS | none |
| finish median seconds within its estimate | PASS | median seconds/estimate 0.423 |
| under 5 % of boards with a part skipped for time | FAIL | 16 of 211 |


#### Q2: the redesign as the default (C against A)

| criterion | verdict | detail |
|---|---|---|
| cp1 | PASS | A 0.2676 C 0.2723 diff 0.0047 CI (0.0, 0.0142) p 1.0 +1/-0 n 213 |
| clean_strict | PASS | A 0.2676 C 0.2723 diff 0.0047 CI (0.0, 0.0142) p 1.0 +1/-0 n 213 |
| completion | FAIL | A 0.9719 C 0.9672 diff -0.0047 CI (-0.0092, -0.0017) p 0.0008 n 213 |
| DRC errors / board | PASS | A 30.6103 C 31.0 diff 0.3897 CI (-0.1132, 1.23) p 0.4607 n 213 |
| no new error type with more than 5 occurrences | PASS | none |
| check: no invalid outputs | PASS | {'A': (0, []), 'C': (0, [])} |
| oblique + acute entries fall | PASS | sum A 9508 C 3283, median ratio 0.235, p 5e-05, n 211 |
| overhang on SMD lands, entries: no rise beyond noise | PASS | A 652 C 479 mean diff -0.8199 CI [-1.2952, -0.3962] p 5e-05 boards up 33 down 66 |
| overhang on SMD lands, mm2: no rise beyond noise | PASS | A 63.08 C 101.37 mean diff 0.1815 CI [-0.0279, 0.4345] p 0.129 boards up 41 down 71 |
| notches < 80 deg, >= 50 um, per m: C not above human beyond noise | PASS | C 17.68 human 14.89 diff 2.79 CI [-0.86, 6.65] (209 boards) |
| loss.copper: median at most 1, more signal-better than signal-worse | PASS | median 0.654, ambiguous 1, noise (offsets) 13, signal better 99, signal worse 4 |
| drop.rail: median at most 1, more signal-better than signal-worse | PASS | median 0.648, ambiguous 3, noise 3, noise (offsets) 9, signal better 137, signal worse 16 |
| no observable with signal-worse above signal-better by more than 2 | PASS | none |


#### Q3: what born-right copper adds (C against B, descriptive)

| criterion | verdict | detail |
|---|---|---|
| cp1 | PASS | B 0.2754 C 0.2802 diff 0.0048 CI (0.0, 0.0146) p 1.0 +1/-0 n 207 |
| clean_strict | PASS | B 0.2754 C 0.2802 diff 0.0048 CI (0.0, 0.0146) p 1.0 +1/-0 n 207 |
| completion | FAIL | B 0.973 C 0.9684 diff -0.0046 CI (-0.0095, -0.0013) p 0.0017 n 207 |
| DRC errors / board | PASS | B 29.3768 C 29.8019 diff 0.4251 CI (-0.0922, 1.3155) p 0.3661 n 207 |
| entries fall against B | PASS | sum B 5076 C 3034, median ratio 0.622, p 5e-05, n 205 |


#### Q4: import tails (D against C)

| criterion | verdict | detail |
|---|---|---|
| cp1 | PASS | C 0.2723 D 0.2723 diff 0.0 CI (0.0, 0.0) p 1.0 +0/-0 n 213 |
| clean_strict | PASS | C 0.2723 D 0.2723 diff 0.0 CI (0.0, 0.0) p 1.0 +0/-0 n 213 |
| completion | PASS | C 0.9672 D 0.9671 diff -0.0001 CI (-0.0019, 0.0015) p 0.9402 n 213 |
| DRC errors / board | PASS | C 31.0 D 30.6667 diff -0.3333 CI (-1.1362, 0.1116) p 0.9172 n 213 |
| entries a further 10 % down | FAIL | sum C 3283 D 2881, median ratio 1.000, p 0.2546, n 211 |
| loss.copper: median at most 1, more signal-better than signal-worse | FAIL | median 1.000, ambiguous 10, noise 18, noise (offsets) 39, signal better 23, signal worse 29 |
| drop.rail: median at most 1, more signal-better than signal-worse | FAIL | median 1.000, ambiguous 10, noise 48, noise (offsets) 54, signal better 24, signal worse 34 |
| no observable with signal-worse above signal-better by more than 2 | FAIL | {'loss.copper': (29, 23), 'drop.rail': (34, 24)} |
| ADOPT import_tails (cp1, clean_strict, completion not worse; and entries or physics) | FAIL |  |


#### Q5: ground vias before routing (E against C, boards where E laid them)

| criterion | verdict | detail |
|---|---|---|
| cp1 | FAIL | C 0.2723 E 0.2629 diff -0.0094 CI (-0.0236, 0.0) p 0.5 +0/-2 n 213 |
| clean_strict | FAIL | C 0.2723 E 0.2629 diff -0.0094 CI (-0.0236, 0.0) p 0.5 +0/-2 n 213 |
| completion | PASS | C 0.9672 E 0.9655 diff -0.0017 CI (-0.0046, 0.0007) p 0.2136 n 213 |
| DRC errors / board | FAIL | C 31.0 E 31.2864 diff 0.2864 CI (0.0374, 0.5877) p 0.0461 n 213 |
| supply.peak or loss.loop_ac: signal-better at least twice signal-worse | PASS | [('supply.peak', 34, 16), ('loss.loop_ac', 0, 0)] |
| ADOPT escape_ground_vias | FAIL | 50 boards |



#### Routing (kaebench score; A0 under the old scorer, cited only)

Score sources (per arm, board-reads): A stored 213; A2 stored 40; B dropped 4, fork 207; C stored 213; D stored 213; E stored 213; A0r left out (uuid churn) 49, rescore 164

| arm | boards | cp1 | cpk (k=1) | clean_strict | completion | not closed | errors / board | unconnected (sum) | invalid |
|---|---|---|---|---|---|---|---|---|---|
| A0 | 213/213 | 0.268 | 0.268 | - | 0.967 | 50 | 31.12 | 4603 | 0 |
| A0r | 164/213 | 0.274 | 0.274 | 0.274 | 0.946 | 43 | 26.32 | 4077 | 3 |
| A | 213/213 | 0.268 | 0.268 | 0.268 | 0.972 | 47 | 30.61 | 3107 | 0 |
| A2 | 40/213 | 0.325 | 0.325 | 0.325 | 0.988 | 4 | 25.52 | 57 | 0 |
| B | 207/213 | 0.275 | 0.275 | 0.275 | 0.973 | 45 | 29.38 | 2823 | 0 |
| C | 213/213 | 0.272 | 0.272 | 0.272 | 0.967 | 49 | 31.00 | 3653 | 0 |
| D | 213/213 | 0.272 | 0.272 | 0.272 | 0.967 | 48 | 30.67 | 3664 | 0 |
| E | 213/213 | 0.263 | 0.263 | 0.263 | 0.965 | 56 | 31.29 | 3703 | 0 |


#### Invalid outputs (integrity checks that failed; foreign objects)

| arm | board | failed | foreign | first items |
|---|---|---|---|---|
| A0r | tinkerforge-motion-detector-bricklet-mot | untouched | {'footprint': 2, 'gr_arc': 8, 'gr_line': 8, 'gr_text': 8} | footprint changed; footprint changed; gr_arc added; gr_arc removed |
| A0r | tinkerforge-temperature-bricklet-tempera | untouched | {'footprint': 3, 'gr_arc': 8, 'gr_line': 8, 'gr_text': 8} | footprint changed; footprint changed; footprint changed; gr_arc removed |
| A0r | uselessful-keyboard-things-amoeba-stabil | untouched | {'dimension': 6, 'footprint': 4, 'gr_arc': 18, 'gr_circle': 2, 'gr_line': 98, 'gr_text': 30} | dimension added; dimension removed; dimension added; dimension removed |


#### DRC errors by type (sum over boards)

| type | A0 | A0r | A | A2 | B | C | D | E |
|---|---|---|---|---|---|---|---|---|
| solder_mask_bridge | 2137 | 1378 | 2123 | 411 | 1848 | 2133 | 2136 | 2156 |
| copper_edge_clearance | 1335 | 797 | 1324 | 323 | 1253 | 1324 | 1324 | 1325 |
| clearance | 1137 | 1035 | 1121 | 76 | 1076 | 1121 | 1121 | 1121 |
| courtyards_overlap | 407 | 198 | 407 | 55 | 402 | 407 | 407 | 407 |
| hole_clearance | 272 | 222 | 272 | 71 | 273 | 273 | 275 | 275 |
| annular_width | 306 | 37 | 306 | 12 | 306 | 306 | 306 | 306 |
| starved_thermal | 293 | 264 | 209 | 11 | 202 | 287 | 201 | 321 |
| pth_inside_courtyard | 262 | 3 | 262 | 0 | 262 | 262 | 262 | 262 |
| shorting_items | 159 | 129 | 173 | 15 | 159 | 173 | 173 | 173 |
| footprint_type_mismatch | 65 | 65 | 65 | 22 | 65 | 65 | 65 | 65 |
| zones_intersect | 68 | 50 | 68 | 2 | 65 | 68 | 68 | 68 |
| items_not_allowed | 56 | 56 | 62 | 6 | 59 | 56 | 66 | 56 |
| invalid_outline | 48 | 23 | 48 | 7 | 39 | 48 | 48 | 48 |
| unresolved_variable | 34 | 34 | 34 | 9 | 34 | 34 | 34 | 34 |
| malformed_courtyard | 19 | 3 | 19 | 0 | 11 | 19 | 19 | 19 |
| padstack | 12 | 12 | 12 | 0 | 12 | 12 | 12 | 12 |
| npth_inside_courtyard | 6 | 3 | 6 | 0 | 6 | 6 | 6 | 6 |
| drill_out_of_range | 4 | 0 | 4 | 0 | 4 | 4 | 4 | 4 |
| text_on_edge_cuts | 3 | 3 | 3 | 1 | 3 | 3 | 3 | 3 |
| silk_over_copper | 2 | 2 | 2 | 0 | 2 | 2 | 2 | 2 |
| track_dangling | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 1 |


#### Paired (treatment - control; McNemar for clean, sign-flip otherwise; 95 % CI resamples repositories)

| pair | metric | n | control | treatment | diff | 95 % CI | p | flips |
|---|---|---|---|---|---|---|---|---|
| A2 vs A | clean | 40 | 0.325 | 0.325 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| A2 vs A | clean_strict | 40 | 0.325 | 0.325 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| A2 vs A | completion | 40 | 0.9881 | 0.9876 | -0.0005 | [-0.002, 0.000] | 0.5 | - |
| A2 vs A | errors | 40 | 25.5 | 25.525 | 0.025 | [-0.075, 0.150] | 1.0 | - |
| B vs A | clean | 207 | 0.2754 | 0.2754 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| B vs A | clean_strict | 207 | 0.2754 | 0.2754 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| B vs A | completion | 207 | 0.9728 | 0.973 | 0.0002 | [0.000, 0.001] | 0.25 | - |
| B vs A | errors | 207 | 29.4058 | 29.3768 | -0.029 | [-0.062, 0.000] | 0.1094 | - |
| C vs B | clean | 207 | 0.2754 | 0.2802 | 0.0048 | [0.000, 0.015] | 1.0 | +1/-0 |
| C vs B | clean_strict | 207 | 0.2754 | 0.2802 | 0.0048 | [0.000, 0.015] | 1.0 | +1/-0 |
| C vs B | completion | 207 | 0.973 | 0.9684 | -0.0046 | [-0.009, -0.001] | 0.0017 | - |
| C vs B | errors | 207 | 29.3768 | 29.8019 | 0.4251 | [-0.092, 1.315] | 0.3661 | - |
| C vs A | clean | 213 | 0.2676 | 0.2723 | 0.0047 | [0.000, 0.014] | 1.0 | +1/-0 |
| C vs A | clean_strict | 213 | 0.2676 | 0.2723 | 0.0047 | [0.000, 0.014] | 1.0 | +1/-0 |
| C vs A | completion | 213 | 0.9719 | 0.9672 | -0.0047 | [-0.009, -0.002] | 0.0008 | - |
| C vs A | errors | 213 | 30.6103 | 31.0 | 0.3897 | [-0.113, 1.230] | 0.4607 | - |
| D vs C | clean | 213 | 0.2723 | 0.2723 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| D vs C | clean_strict | 213 | 0.2723 | 0.2723 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| D vs C | completion | 213 | 0.9672 | 0.9671 | -0.0001 | [-0.002, 0.002] | 0.9402 | - |
| D vs C | errors | 213 | 31.0 | 30.6667 | -0.3333 | [-1.136, 0.112] | 0.9172 | - |
| E vs C | clean | 213 | 0.2723 | 0.2629 | -0.0094 | [-0.024, 0.000] | 0.5 | +0/-2 |
| E vs C | clean_strict | 213 | 0.2723 | 0.2629 | -0.0094 | [-0.024, 0.000] | 0.5 | +0/-2 |
| E vs C | completion | 213 | 0.9672 | 0.9655 | -0.0017 | [-0.005, 0.001] | 0.2136 | - |
| E vs C | errors | 213 | 31.0 | 31.2864 | 0.2864 | [0.037, 0.588] | 0.0461 | - |
| A vs A0r | clean | 164 | 0.2744 | 0.2744 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| A vs A0r | clean_strict | 164 | 0.2744 | 0.2744 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| A vs A0r | completion | 164 | 0.9457 | 0.9712 | 0.0255 | [0.005, 0.051] | 0.0304 | - |
| A vs A0r | errors | 164 | 26.3232 | 25.7866 | -0.5366 | [-1.650, 0.104] | 0.3491 | - |


#### Geometry (kae.route.taut stats of the kept boards)

| arm | boards | perpendicular (sum) | oblique (sum) | acute_entries (sum) | overhanging (sum) | overhang_mm2 (sum) | length_mm (sum) | corners (sum) | acute (sum) | arcs (sum) | oblique+acute share |
|---|---|---|---|---|---|---|---|---|---|---|---|
| human | 210 | 39119 | 6103 | 2027 | 1670 | 1307.3 | 372870.4 | 115548 | 1519 | 6376 | 0.172 |
| A | 211 | 36636 | 7699 | 1809 | 723 | 231.0 | 316755.8 | 67785 | 918 | 0 | 0.206 |
| B | 205 | 37068 | 4135 | 941 | 1115 | 3129.4 | 280606.1 | 31707 | 1081 | 25141 | 0.120 |
| C | 211 | 43178 | 2578 | 705 | 1340 | 4186.0 | 298353.8 | 33702 | 1314 | 28115 | 0.071 |
| D | 211 | 43419 | 2303 | 578 | 1306 | 4131.0 | 297865.4 | 33370 | 1366 | 28610 | 0.062 |
| E | 211 | 41912 | 3382 | 557 | 1281 | 3995.7 | 295645.7 | 31477 | 1195 | 29302 | 0.086 |


#### Paired against A (boards both have): median per-board ratio, boards lower / higher

| pair | measure | n | median ratio | lower | higher |
|---|---|---|---|---|---|
| B / A | oblique | 205 | 0.500 | 139 | 17 |
| B / A | acute_entries | 205 | 0.440 | 112 | 7 |
| B / A | overhanging | 205 | 1.000 | 40 | 79 |
| B / A | length_mm | 205 | 0.983 | 152 | 21 |
| B / A | corners | 205 | 0.401 | 165 | 5 |
| B / A | arcs | 205 | - | 0 | 169 |
| C / A | oblique | 211 | 0.252 | 174 | 13 |
| C / A | acute_entries | 211 | 0.170 | 144 | 7 |
| C / A | overhanging | 211 | 1.000 | 53 | 107 |
| C / A | length_mm | 211 | 0.974 | 166 | 38 |
| C / A | corners | 211 | 0.342 | 190 | 13 |
| C / A | arcs | 211 | - | 0 | 191 |
| D / A | oblique | 211 | 0.250 | 174 | 12 |
| D / A | acute_entries | 211 | 0.182 | 142 | 7 |
| D / A | overhanging | 211 | 1.000 | 50 | 104 |
| D / A | length_mm | 211 | 0.971 | 168 | 37 |
| D / A | corners | 211 | 0.360 | 193 | 10 |
| D / A | arcs | 211 | - | 0 | 192 |
| E / A | oblique | 211 | 0.340 | 167 | 22 |
| E / A | acute_entries | 211 | 0.222 | 143 | 9 |
| E / A | overhanging | 211 | 1.000 | 54 | 105 |
| E / A | length_mm | 211 | 0.969 | 171 | 34 |
| E / A | corners | 211 | 0.337 | 188 | 13 |
| E / A | arcs | 211 | - | 0 | 193 |
| human / A | oblique | 210 | 0.740 | 112 | 77 |
| human / A | acute_entries | 210 | 0.667 | 89 | 82 |
| human / A | overhanging | 210 | 1.000 | 56 | 83 |
| human / A | length_mm | 210 | 1.080 | 48 | 157 |
| human / A | corners | 210 | 1.100 | 78 | 126 |
| human / A | arcs | 210 | - | 0 | 16 |


#### Overhang by land type and exposed acute notches

| arm | boards | entries | mm2 | SMD two-terminal n / mm2 | other SMD n / mm2 | THT n / mm2 |
|---|---|---|---|---|---|---|
| human | 210 | 1670 | 1307.3 | 432 / 69.8 | 945 / 200.3 | 293 / 1037.2 |
| A | 211 | 723 | 231.0 | 235 / 26.1 | 417 / 36.9 | 71 / 167.9 |
| B | 206 | 1117 | 3132.4 | 176 / 56.9 | 306 / 31.0 | 635 / 3044.5 |
| C | 211 | 1340 | 4186.0 | 200 / 73.3 | 279 / 28.1 | 861 / 4084.6 |
| D | 211 | 1306 | 4131.0 | 188 / 78.7 | 275 / 25.9 | 843 / 4026.4 |
| E | 211 | 1281 | 3995.7 | 178 / 56.1 | 254 / 24.0 | 849 / 3915.5 |


| arm | boards | notches < 80 deg, >= 50 um | track m | per m |
|---|---|---|---|---|
| human | 209 | 5473 | 367.5 | 14.89 |
| A | 211 | 6804 | 316.8 | 21.48 |
| B | 206 | 5149 | 280.8 | 18.33 |
| C | 211 | 5293 | 298.3 | 17.74 |
| D | 211 | 4860 | 297.9 | 16.32 |
| E | 211 | 4606 | 295.6 | 15.58 |

#### Physics (fixed evaluator, per term)

A term's difference is judged on its raw value (else its contribution): |ratio - 1| <= floor is noise; floor .. 2 x floor is ambiguous (offset-average it); > 2 x floor is a signal. With all four offsets measured, the means are compared and the difference must exceed 2 x the pooled offset SD.

| arm | boards | total mW_eq (sum) | median total / A |
|---|---|---|---|
| human | 155 | 4480193.5 | 0.787 |
| A | 154 | 4188940.2 | 1.000 |
| B | 146 | 3825475.5 | 0.907 |
| C | 151 | 4439469.3 | 0.863 |
| D | 153 | 4082177.0 | 0.859 |
| E | 143 | 3712738.4 | 0.844 |


#### Per observable: median ratio, and verdicts against the noise floor

| pair | observable | floor | terms | median ratio | min | max | verdicts |
|---|---|---|---|---|---|---|---|
| A / human | drop.rail | 0.02 | 158 | 1.668 | -2.715 | 15.607 | ambiguous 1, noise 1, noise (offsets) 8, signal better 29, signal worse 119 |
| A / human | emission.cable_E | 0.05 | 17 | 0.890 | 0.032 | 5.801 | noise (offsets) 1, signal better 8, signal worse 8 |
| A / human | heat.track | ? | 107 | 2.756 | 0.067 | 73.510 | floor ? 107 |
| A / human | loss.copper | 0.005 | 111 | 1.688 | 0.372 | 11.155 | noise (offsets) 4, signal better 17, signal worse 90 |
| A / human | loss.loop | ? | 19 | 1.295 | 0.411 | 3.278 | floor ? 19 |
| A / human | loss.loop_ac | ? | 19 | 1.827 | 0.329 | 4.699 | floor ? 19 |
| A / human | loss.part | ? | 34 | 1.000 | 1.000 | 1.000 | floor ? 34 |
| A / human | loss.swnode | ? | 19 | 0.996 | 0.343 | 1.379 | floor ? 19 |
| A / human | pickup.peak | ? | 13 | 0.868 | 0.025 | 2.749 | floor ? 13 |
| A / human | supply.peak | 0.04 | 363 | 1.070 | 0.000 | 234.394 | ambiguous 6, noise 24, noise (offsets) 67, signal better 91, signal worse 175 |
| A / human | temp.junction | ? | 256 | 1.000 | 0.966 | 1.091 | floor ? 256 |
| B / A | drop.rail | 0.02 | 172 | 0.798 | -0.088 | 6.596 | ambiguous 10, noise 39, signal better 118, signal worse 5 |
| B / A | emission.cable_E | 0.05 | 17 | 0.941 | 0.552 | 1.153 | ambiguous 1, noise 7, signal better 8, signal worse 1 |
| B / A | heat.track | ? | 119 | 1.000 | 0.023 | 17.680 | floor ? 119 |
| B / A | loss.copper | 0.005 | 120 | 0.730 | 0.098 | 1.037 | ambiguous 6, noise 11, signal better 99, signal worse 4 |
| B / A | loss.loop | ? | 17 | 0.981 | 0.602 | 1.276 | floor ? 17 |
| B / A | loss.loop_ac | ? | 17 | 0.965 | 0.588 | 1.141 | floor ? 17 |
| B / A | loss.part | ? | 36 | 1.000 | 1.000 | 1.000 | floor ? 36 |
| B / A | loss.swnode | ? | 17 | 1.000 | 0.951 | 1.059 | floor ? 17 |
| B / A | pickup.peak | ? | 11 | 0.989 | 0.704 | 1.049 | floor ? 11 |
| B / A | supply.peak | 0.04 | 332 | 0.983 | 0.000 | 10.694 | ambiguous 16, noise 162, signal better 131, signal worse 23 |
| B / A | temp.junction | ? | 286 | 0.999 | 0.694 | 1.057 | floor ? 286 |
| B / human | drop.rail | 0.02 | 157 | 1.131 | -1.177 | 15.607 | ambiguous 2, noise 3, signal better 61, signal worse 91 |
| B / human | emission.cable_E | 0.05 | 16 | 0.937 | 0.031 | 5.801 | ambiguous 2, noise 1, signal better 8, signal worse 5 |
| B / human | heat.track | ? | 107 | 2.002 | 0.051 | 73.510 | floor ? 107 |
| B / human | loss.copper | 0.005 | 111 | 1.138 | 0.157 | 11.155 | noise 1, signal better 49, signal worse 61 |
| B / human | loss.loop | ? | 15 | 1.143 | 0.404 | 2.934 | floor ? 15 |
| B / human | loss.loop_ac | ? | 15 | 1.757 | 0.330 | 4.802 | floor ? 15 |
| B / human | loss.part | ? | 33 | 1.000 | 1.000 | 1.000 | floor ? 33 |
| B / human | loss.swnode | ? | 15 | 0.985 | 0.339 | 1.379 | floor ? 15 |
| B / human | pickup.peak | ? | 11 | 0.762 | 0.026 | 1.434 | floor ? 11 |
| B / human | supply.peak | 0.04 | 300 | 1.000 | 0.000 | 141.219 | ambiguous 15, noise 73, signal better 98, signal worse 114 |
| B / human | temp.junction | ? | 251 | 1.000 | 0.873 | 1.084 | floor ? 251 |
| C / A | drop.rail | 0.02 | 168 | 0.648 | -0.112 | 13.894 | ambiguous 3, noise 3, noise (offsets) 9, signal better 136, signal worse 17 |
| C / A | emission.cable_E | 0.05 | 17 | 0.877 | 0.331 | 7.727 | noise 1, noise (offsets) 3, signal better 8, signal worse 5 |
| C / A | heat.track | ? | 116 | 1.000 | 0.023 | 31.281 | floor ? 116 |
| C / A | loss.copper | 0.005 | 117 | 0.654 | 0.101 | 3.096 | ambiguous 1, noise (offsets) 13, signal better 99, signal worse 4 |
| C / A | loss.loop | ? | 18 | 0.866 | 0.422 | 2.833 | floor ? 18 |
| C / A | loss.loop_ac | ? | 18 | 0.921 | 0.395 | 5.453 | floor ? 18 |
| C / A | loss.part | ? | 35 | 1.000 | 1.000 | 1.000 | floor ? 35 |
| C / A | loss.swnode | ? | 19 | 1.001 | 0.680 | 1.551 | floor ? 19 |
| C / A | pickup.peak | ? | 13 | 0.998 | 0.635 | 10.795 | floor ? 13 |
| C / A | supply.peak | 0.04 | 367 | 0.943 | 0.000 | 644.539 | ambiguous 11, noise 28, noise (offsets) 78, signal better 185, signal worse 65 |
| C / A | temp.junction | ? | 282 | 0.999 | 0.698 | 1.066 | floor ? 282 |
| C / human | drop.rail | 0.02 | 155 | 0.992 | -0.266 | 15.419 | ambiguous 1, noise (offsets) 5, signal better 74, signal worse 75 |
| C / human | emission.cable_E | 0.05 | 17 | 1.018 | 0.074 | 18.504 | noise (offsets) 2, signal better 8, signal worse 7 |
| C / human | heat.track | ? | 106 | 1.620 | 0.056 | 51.043 | floor ? 106 |
| C / human | loss.copper | 0.005 | 110 | 0.965 | 0.158 | 9.755 | ambiguous 1, noise (offsets) 4, signal better 54, signal worse 51 |
| C / human | loss.loop | ? | 17 | 1.094 | 0.596 | 5.975 | floor ? 17 |
| C / human | loss.loop_ac | ? | 17 | 1.816 | 0.679 | 7.591 | floor ? 17 |
| C / human | loss.part | ? | 33 | 1.000 | 1.000 | 1.000 | floor ? 33 |
| C / human | loss.swnode | ? | 18 | 0.971 | 0.450 | 1.444 | floor ? 18 |
| C / human | pickup.peak | ? | 15 | 0.917 | 0.244 | 2.163 | floor ? 15 |
| C / human | supply.peak | 0.04 | 353 | 1.000 | 0.000 | 148.310 | ambiguous 3, noise 22, noise (offsets) 83, signal better 133, signal worse 112 |
| C / human | temp.junction | ? | 259 | 1.000 | 0.952 | 1.081 | floor ? 259 |
| D / A | drop.rail | 0.02 | 169 | 0.670 | -0.088 | 13.703 | ambiguous 3, noise 7, noise (offsets) 4, signal better 140, signal worse 15 |
| D / A | emission.cable_E | 0.05 | 16 | 0.743 | 0.434 | 1.574 | noise 1, noise (offsets) 2, signal better 12, signal worse 1 |
| D / A | heat.track | ? | 117 | 1.000 | 0.023 | 12.915 | floor ? 117 |
| D / A | loss.copper | 0.005 | 118 | 0.659 | 0.101 | 3.181 | ambiguous 1, noise 1, noise (offsets) 7, signal better 103, signal worse 6 |
| D / A | loss.loop | ? | 19 | 0.822 | 0.378 | 2.131 | floor ? 19 |
| D / A | loss.loop_ac | ? | 19 | 0.867 | 0.270 | 2.497 | floor ? 19 |
| D / A | loss.part | ? | 36 | 1.000 | 1.000 | 1.000 | floor ? 36 |
| D / A | loss.swnode | ? | 19 | 1.002 | 0.680 | 2.253 | floor ? 19 |
| D / A | pickup.peak | ? | 13 | 0.951 | 0.000 | 2.310 | floor ? 13 |
| D / A | supply.peak | 0.04 | 364 | 0.890 | 0.000 | 192.595 | ambiguous 18, noise 58, noise (offsets) 40, signal better 197, signal worse 51 |
| D / A | temp.junction | ? | 284 | 0.999 | 0.695 | 1.057 | floor ? 284 |
| D / human | drop.rail | 0.02 | 168 | 1.061 | -1.207 | 15.419 | ambiguous 2, noise (offsets) 2, signal better 77, signal worse 87 |
| D / human | emission.cable_E | 0.05 | 17 | 0.830 | 0.076 | 2.421 | ambiguous 1, noise (offsets) 1, signal better 9, signal worse 6 |
| D / human | heat.track | ? | 112 | 1.847 | 0.056 | 51.043 | floor ? 112 |
| D / human | loss.copper | 0.005 | 116 | 1.035 | 0.174 | 9.950 | noise (offsets) 3, signal better 54, signal worse 59 |
| D / human | loss.loop | ? | 19 | 1.081 | 0.089 | 2.692 | floor ? 19 |
| D / human | loss.loop_ac | ? | 19 | 1.320 | 0.104 | 3.153 | floor ? 19 |
| D / human | loss.part | ? | 36 | 1.000 | 1.000 | 1.000 | floor ? 36 |
| D / human | loss.swnode | ? | 19 | 0.960 | 0.220 | 1.636 | floor ? 19 |
| D / human | pickup.peak | ? | 16 | 0.841 | 0.006 | 2.613 | floor ? 16 |
| D / human | supply.peak | 0.04 | 352 | 1.000 | 0.000 | 148.310 | ambiguous 11, noise 59, noise (offsets) 31, signal better 154, signal worse 97 |
| D / human | temp.junction | ? | 324 | 1.000 | 0.873 | 1.079 | floor ? 324 |
| E / A | drop.rail | 0.02 | 159 | 0.593 | -0.621 | 6.621 | ambiguous 3, noise 5, signal better 132, signal worse 19 |
| E / A | emission.cable_E | 0.05 | 16 | 0.766 | 0.043 | 4.845 | noise 2, signal better 11, signal worse 3 |
| E / A | heat.track | ? | 112 | 1.000 | 0.023 | 259.213 | floor ? 112 |
| E / A | loss.copper | 0.005 | 113 | 0.612 | 0.098 | 2.494 | ambiguous 1, noise 2, signal better 97, signal worse 13 |
| E / A | loss.loop | ? | 17 | 0.711 | 0.451 | 2.106 | floor ? 17 |
| E / A | loss.loop_ac | ? | 17 | 0.802 | 0.340 | 2.879 | floor ? 17 |
| E / A | loss.part | ? | 33 | 1.000 | 1.000 | 1.000 | floor ? 33 |
| E / A | loss.swnode | ? | 17 | 1.013 | 0.649 | 2.071 | floor ? 17 |
| E / A | pickup.peak | ? | 8 | 2.066 | 1.012 | 28.069 | floor ? 8 |
| E / A | supply.peak | 0.04 | 319 | 0.911 | 0.000 | 18.139 | ambiguous 17, noise 87, signal better 162, signal worse 53 |
| E / A | temp.junction | ? | 259 | 0.998 | 0.695 | 1.057 | floor ? 259 |
| E / human | drop.rail | 0.02 | 150 | 1.060 | -0.078 | 8.307 | ambiguous 1, noise 4, signal better 68, signal worse 77 |
| E / human | emission.cable_E | 0.05 | 16 | 1.056 | 0.001 | 12.590 | ambiguous 1, signal better 7, signal worse 8 |
| E / human | heat.track | ? | 104 | 1.873 | 0.052 | 34.465 | floor ? 104 |
| E / human | loss.copper | 0.005 | 108 | 1.036 | 0.155 | 5.323 | ambiguous 1, signal better 51, signal worse 56 |
| E / human | loss.loop | ? | 16 | 1.139 | 0.507 | 2.007 | floor ? 16 |
| E / human | loss.loop_ac | ? | 16 | 1.419 | 0.367 | 2.575 | floor ? 16 |
| E / human | loss.part | ? | 33 | 1.000 | 1.000 | 1.000 | floor ? 33 |
| E / human | loss.swnode | ? | 16 | 0.972 | 0.394 | 1.418 | floor ? 16 |
| E / human | pickup.peak | ? | 9 | 1.480 | 0.041 | 13.750 | floor ? 9 |
| E / human | supply.peak | 0.04 | 313 | 1.000 | 0.000 | 142.677 | ambiguous 14, noise 76, signal better 112, signal worse 111 |
| E / human | temp.junction | ? | 257 | 0.999 | 0.873 | 1.084 | floor ? 257 |


#### Hazards raised on the kept boards (by code, sum over boards; boards with any)

Boards where E laid ground vias before routing (Q5's set, 50): adafruit-adafruit-apds9999-proximity-light-and-color-sensor-pcb-adafruit-apds9999-proximity-light-color-sensor adafruit-adafruit-max98357-i2s-amp-breakout-adafruit-max98357-breakout adafruit-adafruit-mcp4728-pcb-adafruit-mcp4728 adafruit-adafruit-metro-m7-with-microsd-pcb-adafruit-metro-m7-with-microsd adafruit-adafruit-servo-hat-bonnet-pcb-servo-bonnet-rev-b adafruit-adafruit-tpa2012-or-ts2012-breakout-pcb-adafruit-ts2012-tpa2012-class-d-audio-amp aifryz-sensor-hub-sensor-hub baldengineer-c64-1351-to-ps2-mouse-pcb-c64-mouse-adapter bastardkb-dilemma-dilemma-3 berkeleyauv-robosub-hw-noggin bkw777-mount-mount-wp2-feather buildacubesat-project-bac-hardware-bq25306-charger-module-v1 circuitmonkey-chips-0123-class-d-amp-max98365 cmnybo-chip-lcd-dip-chip-lcd-dip dvhx-smd-soldering-exercise-0805-ultimate-soldering-exercise fpga-theremin-theremin-opamp-sine-oscillator freetronics-secsense-secsense govish-fusion-pack-buck-converter-subboard-0-2 having11-connector-x-connectorx hbend63-mesknecht23-btmessbox henrysg1-solar-car-dcdc-dcdcpcb hussamkoman-devotchi-devotchi imseanconroy-disturbance-free-calling-disturbance-free-calling kelu124-pic0rick-max14866-pmod kotbenek-mini-geiger-counter-lcd-board loredavid-hapticpad-macropad-controller-board martinberlin-h-cinread-it8951-mini-pcb-3-to-5v-booster mlab-modules-acomp01-acomp01 openremise-sniffer-sniffer pantsforbirds-adsbee-proto-lna-board protocentral-protocentral-pulse-express-hardware-pc-pulse-express-v3 rave-saber-rave-saber-hardware-ravesaber ravinrabbid-doncon2040-donconpad rjrouquette-gpsdo-tcxo robertpheller-rpi-rrcircuits-stm32f767zi-lcc-pnet-router seeed-studio-oshw-jetson-series-reserver-j2032-v1 siderakb-ergo-snm-keyboard-ergosnm-right sinara-hw-dio-sma16-diot-dio-sma16-mezz solderedelectronics-dasduino-coreplus-hardware-design-dasduino-coreplus sparkfun-micro-bit-moto-bit-sparkfun-micro-bit-moto-bit sparkfunx-qwiic-sgp30-breakout-sgp30-breakout the-hybrid-atelier-rheoboard-rheoboard-altium-reimport tinkerforge-motion-detector-bricklet-motion-detector tinkerforge-temperature-bricklet-temperature tpcarlson-synth-diy-sycamore unaldevelopment-rf-design-rf-design unexpectedmaker-esp32s3-omgs3-carrier-r1 yamanseyravan-undercontrol-hardware-design-undercontrol-v6 yu2924-xps-xpower zenodo-15039399-powersenor3

| code | A | A2 | B | C | D | E |
|---|---|---|---|---|---|---|
| drc_silk_over_copper | 119 | 21 | 71 | 117 | 118 | 117 |
| drc_silk_overlap | 117 | 23 | 68 | 117 | 117 | 115 |
| drc_silk_edge_clearance | 99 | 17 | 58 | 100 | 98 | 98 |
| below_fab_floor | 88 | 10 | 88 | 88 | 88 | 88 |
| drc_text_height | 87 | 14 | 51 | 87 | 86 | 87 |
| drc_copper_edge_clearance | 69 | 10 | 40 | 69 | 70 | 70 |
| drc_solder_mask_bridge | 60 | 10 | 29 | 60 | 60 | 60 |
| drc_text_thickness | 58 | 13 | 30 | 60 | 59 | 58 |
| drc_track_dangling | 61 | 9 | 30 | 61 | 64 | 51 |
| drc_clearance | 47 | 7 | 24 | 47 | 48 | 48 |
| drc_unconnected_items | 44 | 4 | 27 | 46 | 45 | 54 |
| drc_check_downgraded | 36 | 5 | 35 | 36 | 36 | 36 |
| drc_courtyards_overlap | 35 | 6 | 18 | 35 | 36 | 36 |
| drc_starved_thermal | 31 | 5 | 15 | 33 | 31 | 33 |
| drc_shorting_items | 31 | 4 | 17 | 31 | 31 | 31 |
| recheck_skipped | 8 | 1 | 75 | 10 | 10 | 11 |
| drc_isolated_copper | 22 | 3 | 18 | 22 | 23 | 21 |
| land_enlarged_by_track | 0 | 0 | 102 | 0 | 0 | 0 |
| drc_via_dangling | 19 | 2 | 11 | 17 | 16 | 14 |
| drc_pth_inside_courtyard | 14 | 3 | 10 | 14 | 15 | 14 |
| drc_hole_clearance | 13 | 4 | 8 | 13 | 14 | 15 |
| drc_annular_width | 13 | 2 | 10 | 13 | 13 | 13 |
| drc_items_not_allowed | 13 | 2 | 6 | 13 | 14 | 14 |
| drc_invalid_outline | 12 | 3 | 6 | 12 | 12 | 12 |
| finish_reverted | 0 | 0 | 56 | 0 | 0 | 0 |
| drc_zones_intersect | 9 | 1 | 5 | 10 | 10 | 11 |
| drc_npth_inside_courtyard | 8 | 0 | 5 | 8 | 9 | 9 |
| relaxation_beyond_standard_fab | 12 | 0 | 0 | 7 | 5 | 8 |
| drc_copper_sliver | 3 | 0 | 14 | 2 | 1 | 2 |
| drc_hole_to_hole | 4 | 2 | 3 | 4 | 4 | 4 |
| finish_part_skipped | 0 | 0 | 17 | 0 | 0 | 0 |
| drc_holes_co_located | 3 | 1 | 3 | 3 | 3 | 3 |
| drc_drill_out_of_range | 2 | 0 | 2 | 2 | 2 | 2 |
| escape_infeasible | 4 | 0 | 0 | 2 | 1 | 2 |
| drc_connection_width | 2 | 0 | 1 | 2 | 1 | 2 |
| drc_noisy_checks | 0 | 0 | 5 | 0 | 0 | 0 |
| recheck_failed | 1 | 0 | 2 | 0 | 0 | 1 |
| drc_diff_pair_uncoupled_length_too_long | 1 | 0 | 0 | 1 | 1 | 1 |
| drc_skew_out_of_range | 1 | 0 | 0 | 0 | 1 | 1 |
| drc_diff_pair_gap_out_of_range | 0 | 0 | 0 | 1 | 0 | 1 |
| boards with any | 203 | 37 | 205 | 200 | 200 | 203 |


#### Seconds per stage (restart.py summary; sums over boards, and medians)

Route attempts run 4 at a time, so their summed wall exceeds the run's wall.

| arm | stage | boards | hours (sum) | median s |
|---|---|---|---|---|
| A | cpu | 213 | 108.72 | 351.4 |
| A | final | 55 | 1.74 | 132.8 |
| A | judge | 213 | 3.37 | 20.8 |
| A | route attempts | 213 | 94.8 | 353.7 |
| A | wall | 213 | 26.9 | 99.7 |
| A2 | cpu | 40 | 8.28 | 105.9 |
| A2 | final | 5 | 0.11 | 29.3 |
| A2 | judge | 40 | 0.29 | 12.2 |
| A2 | route attempts | 40 | 10.04 | 266.0 |
| A2 | wall | 40 | 2.53 | 47.7 |
| B | finish.gate | 211 | 0.64 | 4.3 |
| B | finish.power | 195 | 0.27 | 1.8 |
| B | finish.replan | 13 | 0.03 | 4.1 |
| B | finish.tails | 211 | 0.48 | 3.9 |
| B | finish.taut | 210 | 1.49 | 7.8 |
| B | finish.total | 211 | 2.91 | 20.0 |
| B | wall | 211 | 3.09 | 23.0 |
| C | cpu | 213 | 98.51 | 390.7 |
| C | final | 56 | 1.79 | 124.2 |
| C | finish | 213 | 4.83 | 33.1 |
| C | finish.gate | 207 | 1.07 | 3.1 |
| C | finish.power | 206 | 0.37 | 2.6 |
| C | finish.replan | 22 | 0.28 | 27.2 |
| C | finish.tails | 207 | 0.53 | 5.0 |
| C | finish.taut | 205 | 1.6 | 10.2 |
| C | finish.total | 207 | 3.85 | 25.8 |
| C | judge | 213 | 3.33 | 24.4 |
| C | route attempts | 213 | 84.18 | 360.4 |
| C | wall | 213 | 28.66 | 144.9 |
| D | cpu | 213 | 82.74 | 266.2 |
| D | final | 55 | 1.92 | 134.7 |
| D | finish | 213 | 4.98 | 32.1 |
| D | finish.gate | 207 | 0.99 | 3.0 |
| D | finish.power | 203 | 0.3 | 2.4 |
| D | finish.replan | 26 | 0.37 | 28.4 |
| D | finish.tails | 207 | 0.53 | 5.1 |
| D | finish.taut | 206 | 1.77 | 10.8 |
| D | finish.total | 207 | 3.95 | 26.4 |
| D | judge | 213 | 3.19 | 24.6 |
| D | route attempts | 213 | 84.95 | 346.8 |
| D | wall | 213 | 28.3 | 134.0 |
| E | cpu | 213 | 102.86 | 360.0 |
| E | final | 64 | 2.11 | 134.8 |
| E | finish | 213 | 4.72 | 32.1 |
| E | finish.gate | 210 | 1.1 | 3.0 |
| E | finish.power | 207 | 0.34 | 2.4 |
| E | finish.replan | 16 | 0.14 | 21.6 |
| E | finish.tails | 210 | 0.53 | 5.0 |
| E | finish.taut | 209 | 1.86 | 11.0 |
| E | finish.total | 210 | 3.97 | 24.3 |
| E | judge | 213 | 3.41 | 23.0 |
| E | route attempts | 213 | 87.09 | 350.6 |
| E | wall | 213 | 29.49 | 144.2 |



# Full tables, the 40 stage-1 boards
Arms A0, A0r, A, A2, B, C; methods A `a7157c78c659`, C `1f103cfc208c`, A2 `962cf139f3d4`; DRC evaluator `a35ac71c2313`; 40 boards.

### Pre-registered gates

### Check: A/A twin of A (flips expected from noise alone)

| criterion | verdict | detail |
|---|---|---|
| cp1 | PASS | A 0.325 A2 0.325 diff 0.0 CI (0.0, 0.0) p 1.0 +0/-0 n 40 |
| clean_strict | PASS | A 0.325 A2 0.325 diff 0.0 CI (0.0, 0.0) p 1.0 +0/-0 n 40 |
| completion | PASS | A 0.9881 A2 0.9876 diff -0.0005 CI (-0.0015, 0.0) p 0.5 n 40 |
| DRC errors / board | PASS | A 25.5 A2 25.525 diff 0.025 CI (-0.075, 0.15) p 1.0 n 40 |


### Q1: finish alone (B against A)

| criterion | verdict | detail |
|---|---|---|
| no board with more unconnected than A | PASS | 0 of 39: [] |
| at most 2 boards with more DRC errors than A | PASS | 0 of 39: [] |
| B loses at most 1 clean board | PASS | +0/-0 |
| cp1 | PASS | A 0.3333 B 0.3333 diff 0.0 CI (0.0, 0.0) p 1.0 +0/-0 n 39 |
| clean_strict | PASS | A 0.3333 B 0.3333 diff 0.0 CI (0.0, 0.0) p 1.0 +0/-0 n 39 |
| completion | PASS | A 0.9878 B 0.9878 diff 0.0 CI (0.0, 0.0) p 1.0 n 39 |
| DRC errors / board | PASS | A 26.1282 B 26.1282 diff 0.0 CI (0.0, 0.0) p 1.0 n 39 |
| oblique + acute entries fall | PASS | sum A 1316 B 567, median ratio 0.359, p 5e-05, n 40 |
| overhang on SMD lands, entries: no rise beyond noise | PASS | A 232 B 200 mean diff -0.8 CI [-1.65, -0.075] p 0.0737 boards up 5 down 8 |
| overhang on SMD lands, mm2: no rise beyond noise | PASS | A 30.24 B 28.6 mean diff -0.0408 CI [-0.3926, 0.2759] p 0.836 boards up 10 down 8 |
| loss.copper: median at most 1, more signal-better than signal-worse | PASS | median 0.731, ambiguous 2, noise 2, signal better 24, signal worse 1 |
| drop.rail: median at most 1, more signal-better than signal-worse | PASS | median 0.781, ambiguous 2, noise 6, signal better 25, signal worse 3 |
| no observable with signal-worse above signal-better by more than 2 | PASS | none |
| finish median seconds within its estimate | PASS | median seconds/estimate 0.383 |
| under 5 % of boards with a part skipped for time | FAIL | 3 of 40 |


### Q2: the redesign as the default (C against A)

| criterion | verdict | detail |
|---|---|---|
| cp1 | PASS | A 0.325 C 0.35 diff 0.025 CI (0.0, 0.075) p 1.0 +1/-0 n 40 |
| clean_strict | PASS | A 0.325 C 0.35 diff 0.025 CI (0.0, 0.075) p 1.0 +1/-0 n 40 |
| completion | PASS | A 0.9881 C 0.9866 diff -0.0016 CI (-0.0045, 0.0) p 0.5 n 40 |
| DRC errors / board | PASS | A 25.5 C 25.675 diff 0.175 CI (-0.15, 0.625) p 0.625 n 40 |
| no new error type with more than 5 occurrences | PASS | none |
| check: no invalid outputs | PASS | {'A': (0, []), 'C': (0, [])} |
| oblique + acute entries fall | PASS | sum A 1316 C 324, median ratio 0.184, p 5e-05, n 40 |
| overhang on SMD lands, entries: no rise beyond noise | PASS | A 232 C 196 mean diff -0.9 CI [-1.775, -0.125] p 0.043 boards up 7 down 14 |
| overhang on SMD lands, mm2: no rise beyond noise | PASS | A 30.24 C 27.06 mean diff -0.0795 CI [-0.5788, 0.3426] p 0.83 boards up 8 down 14 |
| notches < 80 deg, >= 50 um, per m: C not above human beyond noise | PASS | C 12.13 human 10.04 diff 2.08 CI [-4.47, 10.04] (40 boards) |
| loss.copper: median at most 1, more signal-better than signal-worse | PASS | median 0.546, noise (offsets) 6, signal better 23 |
| drop.rail: median at most 1, more signal-better than signal-worse | PASS | median 0.639, noise (offsets) 3, signal better 30, signal worse 3 |
| no observable with signal-worse above signal-better by more than 2 | PASS | none |


### Q3: what born-right copper adds (C against B, descriptive)

| criterion | verdict | detail |
|---|---|---|
| cp1 | PASS | B 0.3333 C 0.359 diff 0.0256 CI (0.0, 0.0769) p 1.0 +1/-0 n 39 |
| clean_strict | PASS | B 0.3333 C 0.359 diff 0.0256 CI (0.0, 0.0769) p 1.0 +1/-0 n 39 |
| completion | PASS | B 0.9878 C 0.9862 diff -0.0016 CI (-0.0046, 0.0) p 0.5 n 39 |
| DRC errors / board | PASS | B 26.1282 C 26.3077 diff 0.1795 CI (-0.1538, 0.641) p 0.625 n 39 |
| entries fall against B | PASS | sum B 567 C 324, median ratio 0.800, p 0.0002, n 40 |



### Routing (kaebench score; A0 under the old scorer, cited only)

Score sources (per arm, board-reads): A stored 40; A2 stored 40; B dropped 1, fork 39; C stored 40; A0r left out (uuid churn) 10, rescore 30

| arm | boards | cp1 | cpk (k=1) | clean_strict | completion | not closed | errors / board | unconnected (sum) | invalid |
|---|---|---|---|---|---|---|---|---|---|
| A0 | 40/40 | 0.325 | 0.325 | - | 0.988 | 4 | 25.73 | 53 | 0 |
| A0r | 30/40 | 0.400 | 0.400 | 0.400 | 0.985 | 4 | 16.10 | 53 | 0 |
| A | 40/40 | 0.325 | 0.325 | 0.325 | 0.988 | 3 | 25.50 | 54 | 0 |
| A2 | 40/40 | 0.325 | 0.325 | 0.325 | 0.988 | 4 | 25.52 | 57 | 0 |
| B | 39/40 | 0.333 | 0.333 | 0.333 | 0.988 | 3 | 26.13 | 54 | 0 |
| C | 40/40 | 0.350 | 0.350 | 0.350 | 0.987 | 4 | 25.68 | 62 | 0 |


### DRC errors by type (sum over boards)

| type | A0 | A0r | A | A2 | B | C |
|---|---|---|---|---|---|---|
| solder_mask_bridge | 418 | 167 | 410 | 411 | 410 | 419 |
| copper_edge_clearance | 323 | 105 | 323 | 323 | 323 | 323 |
| clearance | 76 | 72 | 76 | 76 | 76 | 76 |
| hole_clearance | 71 | 30 | 71 | 71 | 71 | 71 |
| courtyards_overlap | 55 | 27 | 55 | 55 | 55 | 55 |
| footprint_type_mismatch | 22 | 22 | 22 | 22 | 22 | 22 |
| shorting_items | 15 | 13 | 15 | 15 | 15 | 15 |
| annular_width | 12 | 12 | 12 | 12 | 12 | 12 |
| starved_thermal | 12 | 12 | 11 | 11 | 11 | 9 |
| unresolved_variable | 9 | 9 | 9 | 9 | 9 | 9 |
| invalid_outline | 7 | 5 | 7 | 7 | 6 | 7 |
| items_not_allowed | 6 | 6 | 6 | 6 | 6 | 6 |
| zones_intersect | 2 | 2 | 2 | 2 | 2 | 2 |
| text_on_edge_cuts | 1 | 1 | 1 | 1 | 1 | 1 |


### Paired (treatment - control; McNemar for clean, sign-flip otherwise; 95 % CI resamples repositories)

| pair | metric | n | control | treatment | diff | 95 % CI | p | flips |
|---|---|---|---|---|---|---|---|---|
| A2 vs A | clean | 40 | 0.325 | 0.325 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| A2 vs A | clean_strict | 40 | 0.325 | 0.325 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| A2 vs A | completion | 40 | 0.9881 | 0.9876 | -0.0005 | [-0.002, 0.000] | 0.5 | - |
| A2 vs A | errors | 40 | 25.5 | 25.525 | 0.025 | [-0.075, 0.150] | 1.0 | - |
| B vs A | clean | 39 | 0.3333 | 0.3333 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| B vs A | clean_strict | 39 | 0.3333 | 0.3333 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| B vs A | completion | 39 | 0.9878 | 0.9878 | 0.0 | [0.000, 0.000] | 1.0 | - |
| B vs A | errors | 39 | 26.1282 | 26.1282 | 0.0 | [0.000, 0.000] | 1.0 | - |
| C vs B | clean | 39 | 0.3333 | 0.359 | 0.0256 | [0.000, 0.077] | 1.0 | +1/-0 |
| C vs B | clean_strict | 39 | 0.3333 | 0.359 | 0.0256 | [0.000, 0.077] | 1.0 | +1/-0 |
| C vs B | completion | 39 | 0.9878 | 0.9862 | -0.0016 | [-0.005, 0.000] | 0.5 | - |
| C vs B | errors | 39 | 26.1282 | 26.3077 | 0.1795 | [-0.154, 0.641] | 0.625 | - |
| C vs A | clean | 40 | 0.325 | 0.35 | 0.025 | [0.000, 0.075] | 1.0 | +1/-0 |
| C vs A | clean_strict | 40 | 0.325 | 0.35 | 0.025 | [0.000, 0.075] | 1.0 | +1/-0 |
| C vs A | completion | 40 | 0.9881 | 0.9866 | -0.0016 | [-0.004, 0.000] | 0.5 | - |
| C vs A | errors | 40 | 25.5 | 25.675 | 0.175 | [-0.150, 0.625] | 0.625 | - |
| A vs A0r | clean | 30 | 0.4 | 0.4 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| A vs A0r | clean_strict | 30 | 0.4 | 0.4 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| A vs A0r | completion | 30 | 0.9845 | 0.9842 | -0.0004 | [-0.002, 0.001] | 1.0 | - |
| A vs A0r | errors | 30 | 16.1 | 15.9 | -0.2 | [-0.600, 0.000] | 1.0 | - |


### Geometry (kae.route.taut stats of the kept boards)

| arm | boards | perpendicular (sum) | oblique (sum) | acute_entries (sum) | overhanging (sum) | overhang_mm2 (sum) | length_mm (sum) | corners (sum) | acute (sum) | arcs (sum) | oblique+acute share |
|---|---|---|---|---|---|---|---|---|---|---|---|
| human | 40 | 6887 | 896 | 376 | 233 | 155.4 | 79081.7 | 11867 | 262 | 112 | 0.156 |
| A | 40 | 6180 | 1074 | 242 | 262 | 114.7 | 67976.0 | 10657 | 94 | 0 | 0.176 |
| B | 40 | 7029 | 463 | 104 | 328 | 741.5 | 66395.9 | 4430 | 179 | 5083 | 0.075 |
| C | 40 | 7406 | 264 | 60 | 382 | 1121.4 | 67204.0 | 4655 | 183 | 5340 | 0.042 |


### Paired against A (boards both have): median per-board ratio, boards lower / higher

| pair | measure | n | median ratio | lower | higher |
|---|---|---|---|---|---|
| B / A | oblique | 40 | 0.369 | 26 | 2 |
| B / A | acute_entries | 40 | 0.444 | 22 | 1 |
| B / A | overhanging | 40 | 1.000 | 8 | 15 |
| B / A | length_mm | 40 | 0.983 | 30 | 3 |
| B / A | corners | 40 | 0.430 | 32 | 0 |
| B / A | arcs | 40 | - | 0 | 31 |
| C / A | oblique | 40 | 0.226 | 34 | 2 |
| C / A | acute_entries | 40 | 0.125 | 29 | 0 |
| C / A | overhanging | 40 | 0.765 | 13 | 18 |
| C / A | length_mm | 40 | 0.980 | 29 | 9 |
| C / A | corners | 40 | 0.441 | 34 | 3 |
| C / A | arcs | 40 | - | 0 | 35 |
| human / A | oblique | 40 | 0.857 | 21 | 15 |
| human / A | acute_entries | 40 | 1.111 | 15 | 18 |
| human / A | overhanging | 40 | 0.654 | 13 | 12 |
| human / A | length_mm | 40 | 1.094 | 9 | 30 |
| human / A | corners | 40 | 1.053 | 17 | 22 |
| human / A | arcs | 40 | - | 0 | 3 |


### Overhang by land type and exposed acute notches

| arm | boards | entries | mm2 | SMD two-terminal n / mm2 | other SMD n / mm2 | THT n / mm2 |
|---|---|---|---|---|---|---|
| human | 40 | 233 | 155.4 | 61 / 11.2 | 125 / 41.5 | 47 / 102.8 |
| A | 40 | 262 | 114.7 | 79 / 10.0 | 153 / 20.3 | 30 / 84.5 |
| B | 40 | 328 | 741.5 | 70 / 10.6 | 130 / 18.0 | 128 / 712.9 |
| C | 40 | 382 | 1121.4 | 68 / 11.1 | 128 / 16.0 | 186 / 1094.3 |


| arm | boards | notches < 80 deg, >= 50 um | track m | per m |
|---|---|---|---|---|
| human | 40 | 791 | 78.7 | 10.04 |
| A | 40 | 912 | 68.0 | 13.42 |
| B | 40 | 716 | 66.4 | 10.78 |
| C | 40 | 815 | 67.2 | 12.13 |

### Physics (fixed evaluator, per term)

A term's difference is judged on its raw value (else its contribution): |ratio - 1| <= floor is noise; floor .. 2 x floor is ambiguous (offset-average it); > 2 x floor is a signal. With all four offsets measured, the means are compared and the difference must exceed 2 x the pooled offset SD.

| arm | boards | total mW_eq (sum) | median total / A |
|---|---|---|---|
| human | 31 | 2184887.4 | 0.780 |
| A | 33 | 2054518.8 | 1.000 |
| B | 33 | 1965325.8 | 0.908 |
| C | 33 | 2233111.4 | 0.897 |


### Per observable: median ratio, and verdicts against the noise floor

| pair | observable | floor | terms | median ratio | min | max | verdicts |
|---|---|---|---|---|---|---|---|
| A / human | drop.rail | 0.02 | 32 | 1.408 | -0.038 | 6.460 | noise (offsets) 4, signal better 6, signal worse 22 |
| A / human | emission.cable_E | 0.05 | 4 | 0.876 | 0.114 | 2.037 | signal better 2, signal worse 2 |
| A / human | heat.track | ? | 23 | 1.482 | 1.000 | 4.645 | floor ? 23 |
| A / human | loss.copper | 0.005 | 26 | 1.533 | 0.814 | 6.478 | signal better 2, signal worse 24 |
| A / human | loss.loop | ? | 1 | 1.606 | 1.606 | 1.606 | floor ? 1 |
| A / human | loss.loop_ac | ? | 1 | 2.029 | 2.029 | 2.029 | floor ? 1 |
| A / human | loss.part | ? | 8 | 1.000 | 1.000 | 1.000 | floor ? 8 |
| A / human | loss.swnode | ? | 1 | 1.090 | 1.090 | 1.090 | floor ? 1 |
| A / human | pickup.peak | ? | 1 | 0.227 | 0.227 | 0.227 | floor ? 1 |
| A / human | supply.peak | 0.04 | 59 | 1.000 | 0.015 | 96.332 | noise 3, noise (offsets) 17, signal better 15, signal worse 24 |
| A / human | temp.junction | ? | 81 | 1.001 | 0.984 | 1.080 | floor ? 81 |
| B / A | drop.rail | 0.02 | 36 | 0.781 | 0.152 | 1.299 | ambiguous 2, noise 6, signal better 25, signal worse 3 |
| B / A | emission.cable_E | 0.05 | 4 | 0.812 | 0.666 | 1.000 | noise 1, signal better 3 |
| B / A | heat.track | ? | 29 | 1.000 | 0.148 | 1.052 | floor ? 29 |
| B / A | loss.copper | 0.005 | 29 | 0.731 | 0.138 | 1.037 | ambiguous 2, noise 2, signal better 24, signal worse 1 |
| B / A | loss.loop | ? | 1 | 0.619 | 0.619 | 0.619 | floor ? 1 |
| B / A | loss.loop_ac | ? | 1 | 0.659 | 0.659 | 0.659 | floor ? 1 |
| B / A | loss.part | ? | 8 | 1.000 | 1.000 | 1.000 | floor ? 8 |
| B / A | loss.swnode | ? | 1 | 1.028 | 1.028 | 1.028 | floor ? 1 |
| B / A | pickup.peak | ? | 1 | 0.883 | 0.883 | 0.883 | floor ? 1 |
| B / A | supply.peak | 0.04 | 65 | 0.985 | 0.116 | 2.484 | ambiguous 4, noise 37, signal better 20, signal worse 4 |
| B / A | temp.junction | ? | 91 | 0.997 | 0.915 | 1.006 | floor ? 91 |
| B / human | drop.rail | 0.02 | 36 | 1.194 | -0.015 | 10.947 | ambiguous 1, signal better 11, signal worse 24 |
| B / human | emission.cable_E | 0.05 | 4 | 0.676 | 0.076 | 2.037 | ambiguous 1, signal better 2, signal worse 1 |
| B / human | heat.track | ? | 24 | 1.262 | 0.168 | 9.821 | floor ? 24 |
| B / human | loss.copper | 0.005 | 27 | 1.244 | 0.225 | 9.740 | signal better 9, signal worse 18 |
| B / human | loss.loop | ? | 1 | 0.994 | 0.994 | 0.994 | floor ? 1 |
| B / human | loss.loop_ac | ? | 1 | 1.337 | 1.337 | 1.337 | floor ? 1 |
| B / human | loss.part | ? | 8 | 1.000 | 1.000 | 1.000 | floor ? 8 |
| B / human | loss.swnode | ? | 1 | 1.120 | 1.120 | 1.120 | floor ? 1 |
| B / human | pickup.peak | ? | 1 | 0.201 | 0.201 | 0.201 | floor ? 1 |
| B / human | supply.peak | 0.04 | 59 | 1.000 | 0.014 | 92.824 | ambiguous 2, noise 18, signal better 17, signal worse 22 |
| B / human | temp.junction | ? | 86 | 1.000 | 0.915 | 1.084 | floor ? 86 |
| C / A | drop.rail | 0.02 | 36 | 0.639 | 0.146 | 1.338 | noise (offsets) 3, signal better 29, signal worse 4 |
| C / A | emission.cable_E | 0.05 | 4 | 0.825 | 0.652 | 1.622 | signal better 3, signal worse 1 |
| C / A | heat.track | ? | 29 | 1.000 | 0.148 | 1.445 | floor ? 29 |
| C / A | loss.copper | 0.005 | 29 | 0.546 | 0.134 | 1.029 | noise (offsets) 6, signal better 23 |
| C / A | loss.loop | ? | 1 | 0.771 | 0.771 | 0.771 | floor ? 1 |
| C / A | loss.loop_ac | ? | 1 | 0.916 | 0.916 | 0.916 | floor ? 1 |
| C / A | loss.part | ? | 8 | 1.000 | 1.000 | 1.000 | floor ? 8 |
| C / A | loss.swnode | ? | 1 | 0.975 | 0.975 | 0.975 | floor ? 1 |
| C / A | pickup.peak | ? | 1 | 2.219 | 2.219 | 2.219 | floor ? 1 |
| C / A | supply.peak | 0.04 | 65 | 0.905 | 0.049 | 25.417 | ambiguous 1, noise 4, noise (offsets) 20, signal better 36, signal worse 4 |
| C / A | temp.junction | ? | 91 | 0.999 | 0.976 | 1.015 | floor ? 91 |
| C / human | drop.rail | 0.02 | 32 | 1.023 | -0.015 | 4.273 | noise (offsets) 1, signal better 15, signal worse 16 |
| C / human | emission.cable_E | 0.05 | 4 | 0.886 | 0.074 | 1.576 | signal better 2, signal worse 2 |
| C / human | heat.track | ? | 23 | 1.259 | 0.168 | 6.113 | floor ? 23 |
| C / human | loss.copper | 0.005 | 26 | 1.041 | 0.269 | 3.320 | signal better 13, signal worse 13 |
| C / human | loss.loop | ? | 1 | 1.238 | 1.238 | 1.238 | floor ? 1 |
| C / human | loss.loop_ac | ? | 1 | 1.859 | 1.859 | 1.859 | floor ? 1 |
| C / human | loss.part | ? | 8 | 1.000 | 1.000 | 1.000 | floor ? 8 |
| C / human | loss.swnode | ? | 1 | 1.063 | 1.063 | 1.063 | floor ? 1 |
| C / human | pickup.peak | ? | 1 | 0.505 | 0.505 | 0.505 | floor ? 1 |
| C / human | supply.peak | 0.04 | 59 | 1.000 | 0.005 | 92.368 | noise 3, noise (offsets) 21, signal better 16, signal worse 19 |
| C / human | temp.junction | ? | 81 | 1.000 | 0.974 | 1.079 | floor ? 81 |


### Hazards raised on the kept boards (by code, sum over boards; boards with any)

| code | A | A2 | B | C |
|---|---|---|---|---|
| drc_silk_overlap | 23 | 23 | 14 | 24 |
| drc_silk_over_copper | 21 | 21 | 12 | 22 |
| drc_silk_edge_clearance | 17 | 17 | 10 | 18 |
| drc_text_height | 14 | 14 | 8 | 15 |
| drc_text_thickness | 12 | 13 | 7 | 13 |
| below_fab_floor | 10 | 10 | 10 | 10 |
| drc_copper_edge_clearance | 10 | 10 | 6 | 10 |
| drc_track_dangling | 9 | 9 | 5 | 10 |
| drc_solder_mask_bridge | 10 | 10 | 3 | 10 |
| drc_clearance | 7 | 7 | 3 | 7 |
| drc_courtyards_overlap | 7 | 6 | 3 | 7 |
| drc_check_downgraded | 5 | 5 | 5 | 5 |
| recheck_skipped | 1 | 1 | 15 | 0 |
| drc_starved_thermal | 5 | 5 | 2 | 5 |
| drc_isolated_copper | 4 | 3 | 3 | 4 |
| drc_shorting_items | 4 | 4 | 2 | 4 |
| drc_hole_clearance | 4 | 4 | 1 | 4 |
| land_enlarged_by_track | 0 | 0 | 13 | 0 |
| drc_pth_inside_courtyard | 4 | 3 | 2 | 4 |
| drc_unconnected_items | 3 | 4 | 2 | 4 |
| drc_invalid_outline | 3 | 3 | 2 | 3 |
| finish_reverted | 0 | 0 | 8 | 0 |
| drc_hole_to_hole | 2 | 2 | 1 | 2 |
| drc_annular_width | 2 | 2 | 1 | 2 |
| drc_items_not_allowed | 2 | 2 | 1 | 2 |
| drc_via_dangling | 0 | 2 | 0 | 4 |
| drc_holes_co_located | 1 | 1 | 1 | 1 |
| drc_copper_sliver | 0 | 0 | 2 | 1 |
| finish_part_skipped | 0 | 0 | 3 | 0 |
| drc_zones_intersect | 1 | 1 | 0 | 1 |
| drc_noisy_checks | 0 | 0 | 2 | 0 |
| drc_npth_inside_courtyard | 1 | 0 | 0 | 1 |
| escape_infeasible | 1 | 0 | 0 | 0 |
| drc_connection_width | 0 | 0 | 1 | 0 |
| boards with any | 37 | 37 | 38 | 36 |


### Seconds per stage (restart.py summary; sums over boards, and medians)

Route attempts run 4 at a time, so their summed wall exceeds the run's wall.

| arm | stage | boards | hours (sum) | median s |
|---|---|---|---|---|
| A | cpu | 40 | 8.09 | 112.9 |
| A | final | 5 | 0.06 | 30.9 |
| A | judge | 40 | 0.3 | 13.8 |
| A | route attempts | 40 | 9.92 | 273.5 |
| A | wall | 40 | 2.45 | 56.8 |
| A2 | cpu | 40 | 8.28 | 105.9 |
| A2 | final | 5 | 0.11 | 29.3 |
| A2 | judge | 40 | 0.29 | 12.2 |
| A2 | route attempts | 40 | 10.04 | 266.0 |
| A2 | wall | 40 | 2.53 | 47.7 |
| B | finish.gate | 40 | 0.09 | 4.1 |
| B | finish.power | 37 | 0.03 | 1.6 |
| B | finish.replan | 1 | 0.0 | 2.1 |
| B | finish.tails | 40 | 0.06 | 3.8 |
| B | finish.taut | 40 | 0.22 | 7.0 |
| B | finish.total | 40 | 0.39 | 17.9 |
| B | wall | 40 | 0.42 | 20.7 |
| C | cpu | 40 | 8.48 | 164.7 |
| C | final | 5 | 0.08 | 35.4 |
| C | finish | 40 | 0.66 | 24.1 |
| C | finish.gate | 40 | 0.14 | 3.0 |
| C | finish.power | 40 | 0.06 | 2.5 |
| C | finish.replan | 4 | 0.06 | 48.4 |
| C | finish.tails | 40 | 0.07 | 5.5 |
| C | finish.taut | 40 | 0.26 | 8.5 |
| C | finish.total | 40 | 0.6 | 19.9 |
| C | judge | 40 | 0.34 | 16.1 |
| C | route attempts | 40 | 9.6 | 303.2 |
| C | wall | 40 | 3.07 | 88.7 |


