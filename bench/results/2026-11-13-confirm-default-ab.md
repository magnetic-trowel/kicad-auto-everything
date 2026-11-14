<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Confirmation A/B of the routing default (confirm-default-ab, power-copper-tht 4392518): verdicts

The question is whether kae's default, finish in the time left, keeps legacy completion. Plan and pre-registered gates: [confirm-default-ab/PLAN.md](../../tools/kaeres/experiments/confirm-default-ab/PLAN.md).
- **Arms:** A is legacy (centre entries, no finish); N is the default (`--final` and `--finish`, no reserve); A2 is A's twin.
- **Boards:** 86 boards: 50 open in stage 2, 20 complete physics boards and 16 slow-physics boards. A2 ran on the 17 large open boards plus the 16.
- **Setup:** KiCad 10.0.7, restart portfolio as route-finish-ab, Freerouting fork 2e1125a, intents `compiled-9867d0b`, deterministic evaluator with the re-measured floors (loss.copper 0.6 %, drop.rail 0.4 %, supply.peak 0.5 %).
- **Run health:** 205 routing jobs and 70 physics jobs, none frozen, failed or timed out.

## Verdicts

| Gate | Verdict |
|---|---|
| **Primary: completion, N against A** (CI lower bound above -0.005) | **PASS**: 0.9369 → 0.9363, diff -0.0006, CI -0.0042 to 0.0028, 86 boards. Stage 2's completion loss is gone |
| Noise reference, on the 33 boards A2 ran | N - A mean -0.0017 (11 boards worse, 6 better); A2 - A mean -0.0034, CI -0.0078 to 0.0006 (10 worse, 5 better). N - A lies inside the twin's spread |
| cp1, clean_strict, DRC errors (reported) | cp1 0.140 → 0.163 (+2 boards); clean_strict 0.140 → 0.151; errors 43.0 → 44.0 per board (p 0.25); no invalid output |
| **Secondary: loss.copper**, 20 complete boards | **PASS**: median N/A 0.701, 19 terms better and 1 worse. Also passes at the 90th-percentile floors |
| **Secondary: drop.rail** | **PASS**: median 0.722, 29 better and 6 worse; also passes at the 90th-percentile floors |
| **SMD overhang** | **PASS**: entries 55 → 37; area 14.7 → 4.9 mm² |
| **THT overhang** | **FAIL**: entries 2 → 99, area 1.4 → 559 mm², higher on 13 of 20 boards and lower on none |
| Notches below 80°, at least 50 µm deep, per metre (reported) | A 14.9, N 10.2, human 13.7 |
| Finish skipped or time-limited (reported) | Skipped on 28 boards, all open (`finish_part_skipped`: the last mile used the time). It ran on every complete board; no `taut_time_limited` or `finish_failed` |

## What drives the results

- **THT overhang:** A has no power copper, so almost any widened rail into a through-hole land counts against it. The gate compares N with A, not with the human layout.
  - The largest rises: zx2-backplane +238 mm² (11 entries), fortitude60 +129, secsense +42, aquarium sensor +36, btmessbox +32, ostr +20, servo bonnet +19.
  - On zx2-backplane, 5V is widened to 2.5 mm into 1.7 mm connector lands (J3, J4, J5). That is the wide-rail-into-THT practice the plan treats as normal, but it is a pre-registered rise, so the gate fails.
  - The THT neck did not bring N to A's level on these boards. Human THT overhang on the same boards: zx2-backplane 0, fortitude60 2.5 mm².
- **Completion:** the per-board changes cancel out.
  - Better in N: arvsom (-73 open, but A2 is +39 from A), dilemma (-11), kestrel (-8).
  - Worse in N: jetson J2032 (+57; A2 +32), usbarmory (+21; A2 +16), PolarFire (+9; A2 +4), mystorm and sstv (+7).
  - The twin moves by similar amounts on the same boards.
- **Against the human layout (context):** loss.copper median 1.23 (8 better, 11 worse), drop.rail 0.94 (16, 15), supply.peak 1.00 (9, 16).

## Full tables

Arms A0, A0r, A, A2, B, N; methods A `591ae9f64339`, N `361bb5d7bfdb`, A2 `1effb2f4e3a5`; DRC evaluator `afa09d34bc94`; 86 boards.

## Pre-registered gates

### Confirmation: N (the default) against A (legacy)

| criterion | verdict | detail |
|---|---|---|
| PRIMARY completion: N not worse than A (CI lower bound > -0.005) | PASS | A 0.9369 N 0.9363 diff -0.0006 CI (-0.0042, 0.0028) p 0.7453 n 86 |
| noise check, large open boards: N - A against A2 - A (reported; read as PLAN.md says) | no data | N-A mean -0.0017 (boards worse 11, better 6); A2-A mean -0.0034 CI [-0.0078, 0.0006] (worse 10, better 5); median |A2-A| 0.0000; N-A inside the twin's CI; n 33 |
| cp1 (reported) | PASS | A 0.1395 N 0.1628 diff 0.0233 CI (0.0, 0.0581) p 0.5 +2/-0 n 86 |
| clean_strict (reported) | PASS | A 0.1395 N 0.1512 diff 0.0116 CI (0.0, 0.0349) p 1.0 +1/-0 n 86 |
| DRC errors / board (reported) | PASS | A 42.9535 N 44.0465 diff 1.093 CI (-0.0814, 3.1628) p 0.2513 n 86 |
| check: no invalid outputs | PASS | {'A': (0, []), 'N': (0, [])} |
| SECONDARY loss.copper: median N/A at most 1, more signal-better than signal-worse | PASS | median 0.701, signal better 19, signal worse 1; 20 boards |
| SECONDARY drop.rail: median N/A at most 1, more signal-better than signal-worse | PASS | median 0.722, signal better 29, signal worse 6; 20 boards |
| overhang on THT lands, entries: no rise beyond noise | FAIL | A 2 N 99 mean diff 4.85 CI [1.95, 8.4] p 0.000244 boards up 13 down 0 |
| overhang on THT lands, mm2: no rise beyond noise | FAIL | A 1.44 N 559.38 mean diff 27.8973 CI [8.2277, 56.5494] p 0.000244 boards up 13 down 0 |
| overhang on SMD lands, entries: no rise beyond noise | PASS | A 55 N 37 mean diff -0.9 CI [-2.15, 0.0] p 0.172 boards up 2 down 5 |
| overhang on SMD lands, mm2: no rise beyond noise | PASS | A 14.68 N 4.91 mean diff -0.4881 CI [-1.3315, -0.0134] p 0.0586 boards up 2 down 7 |
| notches < 80 deg, >= 50 um per m, A (reported) | no data | 14.87 on 20 boards |
| notches < 80 deg, >= 50 um per m, N (reported) | PASS | 10.24 on 20 boards |
| notches < 80 deg, >= 50 um per m, human (reported) | no data | 13.68 on 21 boards |
| finish skipped or time-limited on N's kept boards (reported) | no data | 28 boards; finish_part_skipped 28, no finish record 0 |



## Routing (kaebench score; A0 under the old scorer, cited only)

Score sources (per arm, board-reads): A stored 86; N stored 86; A2 stored 33

| arm | boards | cp1 | cpk (k=1) | clean_strict | completion | not closed | errors / board | unconnected (sum) | invalid |
|---|---|---|---|---|---|---|---|---|---|
| A0 | 86/86 | 0.151 | 0.151 | - | 0.918 | 48 | 45.29 | 4601 | 0 |
| A | 86/86 | 0.140 | 0.140 | 0.140 | 0.937 | 47 | 42.95 | 2831 | 0 |
| A2 | 33/86 | 0.212 | 0.212 | 0.212 | 0.920 | 16 | 41.64 | 2666 | 0 |
| N | 86/86 | 0.163 | 0.163 | 0.151 | 0.936 | 48 | 44.05 | 2850 | 0 |


### DRC errors by type (sum over boards)

| type | A0 | A | A2 | N |
|---|---|---|---|---|
| solder_mask_bridge | 1439 | 1433 | 603 | 1439 |
| copper_edge_clearance | 682 | 681 | 166 | 680 |
| clearance | 502 | 491 | 236 | 491 |
| courtyards_overlap | 289 | 289 | 113 | 289 |
| annular_width | 210 | 210 | 8 | 210 |
| pth_inside_courtyard | 202 | 202 | 3 | 202 |
| starved_thermal | 259 | 65 | 101 | 153 |
| shorting_items | 103 | 112 | 34 | 112 |
| zones_intersect | 65 | 65 | 54 | 65 |
| hole_clearance | 56 | 56 | 8 | 56 |
| footprint_type_mismatch | 32 | 32 | 19 | 32 |
| items_not_allowed | 14 | 16 | 11 | 19 |
| unresolved_variable | 16 | 16 | 3 | 16 |
| invalid_outline | 10 | 10 | 8 | 10 |
| npth_inside_courtyard | 5 | 5 | 2 | 5 |
| padstack | 4 | 4 | 4 | 4 |
| track_dangling | 3 | 2 | 1 | 1 |
| text_on_edge_cuts | 2 | 2 | 0 | 2 |
| malformed_courtyard | 2 | 2 | 0 | 2 |
| via_dangling | 0 | 1 | 0 | 0 |


### Paired (treatment - control; McNemar for clean, sign-flip otherwise; 95 % CI resamples repositories)

| pair | metric | n | control | treatment | diff | 95 % CI | p | flips |
|---|---|---|---|---|---|---|---|---|
| A2 vs A | clean | 33 | 0.2121 | 0.2121 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| A2 vs A | clean_strict | 33 | 0.2121 | 0.2121 | 0.0 | [0.000, 0.000] | 1.0 | +0/-0 |
| A2 vs A | completion | 33 | 0.923 | 0.9196 | -0.0034 | [-0.008, 0.001] | 0.1309 | - |
| A2 vs A | errors | 33 | 39.4848 | 41.6364 | 2.1515 | [-0.273, 6.758] | 0.7188 | - |


## Geometry (kae.route.taut stats of the kept boards)

| arm | boards | perpendicular (sum) | oblique (sum) | acute_entries (sum) | overhanging (sum) | overhang_mm2 (sum) | length_mm (sum) | corners (sum) | acute (sum) | arcs (sum) | oblique+acute share |
|---|---|---|---|---|---|---|---|---|---|---|---|
| human | 21 | 4119 | 613 | 217 | 138 | 39.3 | 53574.0 | 9391 | 168 | 0 | 0.168 |
| A | 20 | 3557 | 519 | 120 | 57 | 16.1 | 32623.1 | 5647 | 30 | 0 | 0.152 |
| N | 20 | 4004 | 234 | 50 | 136 | 564.3 | 31641.4 | 2163 | 81 | 3221 | 0.066 |


### Paired against A (boards both have): median per-board ratio, boards lower / higher

| pair | measure | n | median ratio | lower | higher |
|---|---|---|---|---|---|
| N / A | oblique | 20 | 0.355 | 15 | 3 |
| N / A | acute_entries | 20 | 0.187 | 15 | 2 |
| N / A | overhanging | 20 | 1.000 | 4 | 13 |
| N / A | length_mm | 20 | 0.979 | 19 | 1 |
| N / A | corners | 20 | 0.306 | 19 | 1 |
| N / A | arcs | 20 | - | 0 | 18 |
| human / A | oblique | 20 | 1.520 | 7 | 13 |
| human / A | acute_entries | 20 | 1.000 | 5 | 9 |
| human / A | overhanging | 20 | 1.600 | 2 | 11 |
| human / A | length_mm | 20 | 1.113 | 4 | 16 |
| human / A | corners | 20 | 1.227 | 5 | 15 |
| human / A | arcs | 20 | - | 0 | 0 |


## Overhang by land type and exposed acute notches

| arm | boards | entries | mm2 | SMD two-terminal n / mm2 | other SMD n / mm2 | THT n / mm2 |
|---|---|---|---|---|---|---|
| human | 21 | 138 | 39.3 | 45 / 10.9 | 76 / 22.5 | 17 / 5.9 |
| A | 20 | 57 | 16.1 | 12 / 4.1 | 43 / 10.6 | 2 / 1.4 |


| arm | boards | notches < 80 deg, >= 50 um | track m | per m |
|---|---|---|---|---|
| human | 21 | 733 | 53.6 | 13.68 |
| A | 20 | 485 | 32.6 | 14.87 |

## Physics (fixed evaluator, per term)

A term's difference is judged on its raw value (else its contribution): |ratio - 1| <= floor is noise; floor .. 2 x floor is ambiguous (offset-average it); > 2 x floor is a signal. With all four offsets measured, the means are compared and the difference must exceed 2 x the pooled offset SD.

| arm | boards | total mW_eq (sum) | median total / A |
|---|---|---|---|
| human | 21 | 444788.7 | 0.594 |
| A | 20 | 342878.5 | 1.000 |
| N | 20 | 287521.9 | 0.857 |


### Per observable: median ratio, and verdicts against the noise floor

| pair | observable | floor | terms | median ratio | min | max | verdicts |
|---|---|---|---|---|---|---|---|
| A / human | drop.rail | 0.004 | 31 | 1.860 | 0.000 | 8.187 | signal better 6, signal worse 25 |
| A / human | emission.cable_E | 0.05 | 6 | 1.764 | 0.118 | 5.861 | signal better 1, signal worse 5 |
| A / human | heat.track | ? | 19 | 3.252 | 0.331 | 21.871 | floor ? 19 |
| A / human | loss.copper | 0.006 | 19 | 2.039 | 0.968 | 8.014 | signal better 2, signal worse 17 |
| A / human | loss.loop | ? | 1 | 1.367 | 1.367 | 1.367 | floor ? 1 |
| A / human | loss.loop_ac | ? | 1 | 0.968 | 0.968 | 0.968 | floor ? 1 |
| A / human | loss.part | ? | 7 | 1.000 | 1.000 | 1.000 | floor ? 7 |
| A / human | loss.swnode | ? | 1 | 1.041 | 1.041 | 1.041 | floor ? 1 |
| A / human | pickup.peak | ? | 4 | 1.070 | 0.221 | 3.109 | floor ? 4 |
| A / human | supply.peak | 0.005 | 35 | 1.121 | 0.570 | 87.430 | noise 11, signal better 4, signal worse 20 |
| A / human | temp.junction | ? | 56 | 0.999 | 0.980 | 1.037 | floor ? 56 |
| N / A | drop.rail | 0.004 | 35 | 0.722 | 0.135 | 1.253 | signal better 29, signal worse 6 |
| N / A | emission.cable_E | 0.05 | 6 | 0.911 | 0.644 | 2.342 | ambiguous 1, noise 1, signal better 3, signal worse 1 |
| N / A | heat.track | ? | 20 | 1.000 | 0.148 | 1.000 | floor ? 20 |
| N / A | loss.copper | 0.006 | 20 | 0.701 | 0.168 | 1.228 | signal better 19, signal worse 1 |
| N / A | loss.loop | ? | 1 | 0.932 | 0.932 | 0.932 | floor ? 1 |
| N / A | loss.loop_ac | ? | 1 | 0.768 | 0.768 | 0.768 | floor ? 1 |
| N / A | loss.part | ? | 7 | 1.000 | 1.000 | 1.000 | floor ? 7 |
| N / A | loss.swnode | ? | 1 | 1.006 | 1.006 | 1.006 | floor ? 1 |
| N / A | pickup.peak | ? | 4 | 0.855 | 0.364 | 2.330 | floor ? 4 |
| N / A | supply.peak | 0.005 | 39 | 1.000 | 0.046 | 7.036 | ambiguous 1, noise 11, signal better 18, signal worse 9 |
| N / A | temp.junction | ? | 63 | 1.000 | 0.972 | 1.005 | floor ? 63 |
| N / human | drop.rail | 0.004 | 31 | 0.942 | 0.000 | 5.637 | signal better 16, signal worse 15 |
| N / human | emission.cable_E | 0.05 | 6 | 1.576 | 0.076 | 13.725 | noise 1, signal better 1, signal worse 4 |
| N / human | heat.track | ? | 19 | 3.133 | 0.168 | 10.478 | floor ? 19 |
| N / human | loss.copper | 0.006 | 19 | 1.232 | 0.269 | 5.501 | signal better 8, signal worse 11 |
| N / human | loss.loop | ? | 1 | 1.273 | 1.273 | 1.273 | floor ? 1 |
| N / human | loss.loop_ac | ? | 1 | 0.743 | 0.743 | 0.743 | floor ? 1 |
| N / human | loss.part | ? | 7 | 1.000 | 1.000 | 1.000 | floor ? 7 |
| N / human | loss.swnode | ? | 1 | 1.048 | 1.048 | 1.048 | floor ? 1 |
| N / human | pickup.peak | ? | 4 | 0.915 | 0.514 | 1.133 | floor ? 4 |
| N / human | supply.peak | 0.005 | 35 | 1.000 | 0.309 | 81.215 | noise 10, signal better 9, signal worse 16 |
| N / human | temp.junction | ? | 56 | 0.997 | 0.979 | 1.011 | floor ? 56 |


## Hazards raised on the kept boards (by code, sum over boards; boards with any)

| code | A | A2 | N |
|---|---|---|---|
| tht_pad_kept_wide | 0 | 0 | 134 |
| drc_silk_overlap | 54 | 17 | 57 |
| drc_silk_over_copper | 51 | 17 | 55 |
| drc_track_dangling | 42 | 19 | 58 |
| below_fab_floor | 42 | 32 | 42 |
| drc_silk_edge_clearance | 47 | 16 | 50 |
| drc_unconnected_items | 43 | 13 | 46 |
| tht_pad_necked | 0 | 0 | 91 |
| drc_text_height | 40 | 9 | 41 |
| drc_solder_mask_bridge | 35 | 11 | 37 |
| drc_text_thickness | 32 | 7 | 33 |
| drc_clearance | 29 | 8 | 30 |
| drc_copper_edge_clearance | 30 | 4 | 30 |
| drc_check_downgraded | 25 | 13 | 25 |
| drc_shorting_items | 21 | 5 | 21 |
| drc_starved_thermal | 19 | 5 | 20 |
| finish_part_skipped | 0 | 0 | 42 |
| drc_courtyards_overlap | 17 | 8 | 17 |
| drc_via_dangling | 16 | 7 | 15 |
| finish_reverted | 0 | 0 | 29 |
| drc_isolated_copper | 9 | 4 | 11 |
| land_enlarged_by_track | 0 | 0 | 21 |
| drc_zones_intersect | 7 | 6 | 7 |
| drc_copper_sliver | 5 | 4 | 8 |
| relaxation_beyond_standard_fab | 10 | 0 | 7 |
| drc_pth_inside_courtyard | 7 | 3 | 7 |
| tht_pad_heatsunk | 0 | 0 | 14 |
| escape_infeasible | 2 | 5 | 6 |
| drc_annular_width | 5 | 2 | 5 |
| drc_hole_clearance | 5 | 1 | 6 |
| recheck_skipped | 6 | 2 | 4 |
| drc_items_not_allowed | 5 | 1 | 5 |
| drc_npth_inside_courtyard | 5 | 1 | 5 |
| drc_connection_width | 2 | 2 | 5 |
| drc_invalid_outline | 3 | 1 | 3 |
| recheck_failed | 2 | 2 | 1 |
| drc_hole_to_hole | 2 | 0 | 2 |
| drc_skew_out_of_range | 1 | 1 | 1 |
| drc_diff_pair_uncoupled_length_too_long | 1 | 1 | 1 |
| drc_holes_co_located | 1 | 0 | 1 |
| drc_diff_pair_gap_out_of_range | 1 | 1 | 0 |
| boards with any | 83 | 32 | 86 |


## Seconds per stage (restart.py summary; sums over boards, and medians)

Route attempts run 4 at a time, so their summed wall exceeds the run's wall.

| arm | stage | boards | hours (sum) | median s |
|---|---|---|---|---|
| A | cpu | 86 | 79.48 | 3042.5 |
| A | final | 52 | 1.6 | 132.3 |
| A | judge | 86 | 2.4 | 52.0 |
| A | route attempts | 86 | 79.34 | 2787.1 |
| A | wall | 86 | 21.85 | 797.3 |
| A2 | cpu | 33 | 45.54 | 4857.2 |
| A2 | final | 17 | 0.88 | 180.5 |
| A2 | judge | 33 | 1.49 | 60.4 |
| A2 | route attempts | 33 | 42.08 | 4887.3 |
| A2 | wall | 33 | 11.92 | 1518.8 |
| N | cpu | 86 | 83.77 | 3101.8 |
| N | final | 52 | 1.71 | 114.2 |
| N | finish | 86 | 1.22 | 28.5 |
| N | finish.gate | 68 | 0.4 | 3.8 |
| N | finish.power | 60 | 0.09 | 4.2 |
| N | finish.replan | 11 | 0.09 | 14.0 |
| N | finish.tails | 62 | 0.12 | 6.0 |
| N | finish.taut | 58 | 0.42 | 16.6 |
| N | finish.total | 68 | 1.13 | 37.0 |
| N | judge | 86 | 2.39 | 53.2 |
| N | route attempts | 86 | 79.04 | 2807.6 |
| N | wall | 86 | 23.09 | 830.6 |


