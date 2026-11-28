<!-- SPDX-FileCopyrightText: 2026 HaslamPCB contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# width-metric-human: a class-independent power-net width metric, measured on the stored control

Status: planned 2026-11-28, written before any result was read. Branch `width/metric-human` (off main 8a0f51e1).
Question 1 of docs/research/routing/power-net-track-width.md (branch obd-solar-e2e), "Open questions".

## Question

Does haslam draw power copper narrower than the human did **on the same net**, on corpus boards, or only on designs
with current-sized net classes (obd-solar)? The earlier corpus check (R43, freerouting-settings-2611) compared to the
**class width** and found no gap (13.5 % bridge vs 14.6 % human); human classes rarely exceed pad widths, so that
reference cannot see the problem.

## The change

No router change: a measuring tool, `haslam.route.width_human` (+ driver
`tools/research/routing/width_human_corpus.py`). Pure Python, no KiCad, ~1 s per run. No new routing.

Power nets (from the human board): brief role rail / ground / switch_node, or human width w_h >= 1.2 x the board's
signal width w_sig (length-weighted medians), with >= 2 mm of human track. Headline subset `power` drops wide nets
whose role is impedance-driven (high_speed, rf, clock). A segment is narrow when w < (1 - tol) w_h.

Definitions (pooled per board: sum of numerators / sum of denominators over its nets):
- `share`: narrow length / routed length
- `share_x`: same, without pad-entry segments (both ends within `reach` of a same-net pad)
- `deficit`: sum L max(0, 1 - w/w_h) / routed length
- `share_i`: `share_x` weighted by branch current (power_copper.branch_currents under the evaluator's DC plan; only
  nets with a source and a load in the plan)
Option sets: d (tol 0.05, reach 1.0), tol15 (tol 0.15), reach05 (reach 0.5). Human floor: the human board measured
against itself.

## Data

Stored runs of control-w48 (bridge 288a499c28d9, staged 85993b60a886; seeds 0, 1): its 140 boards plus the boards of
`bench/suites/mech/` power-distribution, buck, boost, battery-charging that carry stored runs of the same methods
(control fill), 293 board ids considered. Human reference: the corpus board. Plus obd-solar's handoff boards
(handoff/README.md), where there is no human layout: the reference there is each net's class width (stated as such).

## Endpoints (decided now)

1. **Answer to the question:** corpus mean over boards of `share_x` on subset `power` for the bridge (human
   placement), paired per board against the human floor (bridge - floor), 95 % board bootstrap interval of the mean
   difference. "Corpus-wide under-width" if the interval's lower bound is > 0.05; "no corpus gap" if its upper bound
   is < 0.05; else undecided. Also by mech suite (power-distribution, buck,
   boost, battery-charging) to see whether current-sized boards differ.
2. **Which definition to recommend:** most stable = highest seed-0 vs seed-1 Spearman correlation across boards
   (bridge and staged separately), and smallest change between option sets (d vs tol15, d vs reach05) in the corpus
   mean; ties go to the simpler definition. share_i also needs coverage (share of boards with a value) >= 50 % to be
   recommended as the headline.
3. Report per definition: boards with a value, mean, median, bootstrap CI, seed correlation, option sensitivity.

## Cost

Measured smoke: 2 boards, 5 runs each, 3 option sets, 9 s wall on 2 workers. Estimate for 293 boards: < 1 CPU-h.
One haslamq job, 16 CPUs, priority 5, owner exp-width-metric-human.

## Amendment (2026-11-28, before any corpus result; only obd-solar's handoff boards and 2 smoke boards seen)

Found while testing the definitions; job #140771 was cancelled unstarted and resubmitted as #140772 (code ba02daf):
1. `share_x` leaves out the **length within `reach` of a same-net pad**, not whole segments whose two ends are near
   pads (that exempted a straight pad-to-pad run of any length; width_check.py has the same flaw).
2. Pour credit (`pour`, default on): narrow length inside a same-net zone outline on the track's layer counts as wide
   (kept in the denominator, never in the numerator) in `share_x` and `share_i`. Outlines stand in for fills, so this
   over-credits pours cut by clearances. First version dropped poured length from the denominator, which made the
   zones-into-pads variant look worse (0.74 -> 0.81); fixed. Option set `nopour` turns it off.
3. obd-solar: reference = class width (`--ref class`), DC plan from the design's intent plus `width_injections.json`.

## Amendment 2 (2026-11-28, after the 80 % look at the first run)

The first run (16/20 chunks, kept in `corpus-v1-partial/`) showed a large gap, and a split of bridge seed-0 narrow
length by class width (`/var/tmp` script, 145 boards) showed 73 % of it at or above the net's own class width. Added
definition `share_neck` (narrow and below the class width, from the human board's `.kicad_pro`), code 31c8710; the 3
unfinished chunks were cancelled and all 20 re-queued (#141031-#141050) so every row carries every definition. The
endpoints are unchanged; `share_neck` is reported beside them, not as a new decision rule.
