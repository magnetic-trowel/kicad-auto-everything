<!-- SPDX-FileCopyrightText: 2026 HaslamPCB contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# width-metric-human: verdict

Status: done 2026-11-28. Code: branch `width/metric-human` (31c8710 ran the corpus; tool `haslam.route.width_human`,
driver `tools/research/routing/width_human_corpus.py`, summary `tools/research/routing/width_human_report.py`).
Plan and its two amendments: PLAN.md. Full tables: REPORT.md (from `rows.jsonl`, 4,744 rows). Cost: 20 jobs of 2 CPUs,
< 1 CPU-h, no routing.

## Answer: haslam under-widths power copper corpus-wide, not only with current-sized classes

Stored runs of control-w48 (bridge 288a499c on the human placement, staged 85993b60), seeds 0-1, subset `power`,
option set d (tol 0.05, reach 1 mm, pour credit), mean of the two seeds per board, paired against the human layout
measured against itself (floor):

| method | definition | boards | mean | floor | method - floor [95 % board bootstrap] |
|---|---|---|---|---|---|
| bridge | share_x | 145 | 0.442 | 0.056 | **0.386 [0.339, 0.434]** |
| bridge | deficit | 145 | 0.249 | 0.044 | 0.204 [0.178, 0.230] |
| bridge | share_neck | 145 | 0.092 | 0.017 | 0.076 [0.052, 0.100] |
| staged | share_x | 248 | 0.637 | 0.063 | 0.574 [0.533, 0.616] |
| staged | share_neck | 248 | 0.130 | 0.016 | 0.114 [0.091, 0.137] |

1. Endpoint 1: the lower bound 0.339 is > 0.05, so **corpus-wide under-width**. On the human placement 44 % of the
   power-net length beyond pad entry is narrower than the human drew it on the same net (human: 6 %).
2. Not specific to current-heavy boards: mech power suites are in the same range as the sprint suites (bridge share_x:
   sprint-frontier 0.48, sprint-quality 0.42, power-distribution 0.44, buck 0.50, boost 0.32, battery-charging 0.33;
   REPORT.md section 4). Staged placement is worse everywhere (longer power paths at the same widths).
3. **Most of it is the class width, not necks.** `share_neck` (narrow and below the net's own KiCad class) is 0.09 of
   0.44 for the bridge: about a fifth. The rest is haslam drawing at a class width the human widened past by hand
   (by-hand split of bridge seed 0, 145 boards: 73 % of narrow length at or above class; the human drew wider than
   the class on 1,116 of 1,705 power nets). R43's class-relative metric (13.5 % vs 14.6 %) could not see this part.
4. obd-solar is the other regime: its classes are sized from current, so all of its narrow length is necking
   (`--ref class`, pooled power: share_x = share_neck 0.70 routed seed 1, 0.45 after `power_copper` widen, 0.31 after
   zones into pads). There a neck fix is the whole problem; on corpus boards it addresses about a fifth.

Consequence for the router line (`gfix-route-width`, start_necked off / neck floor / pin-local neck): on corpus boards
its ceiling is the `share_neck` gap (0.076 bridge, 0.114 staged). Closing the other ~0.3 needs a width source other
than the class: current-based sizing of nets (haslamsynth already does it for its designs; the corpus has no load
facts) or post-route widening into free space (`power_copper`).

## Which definition (endpoint 2)

| definition | Spearman s0-s1 bridge / staged | mean abs s0-s1 bridge | tol15 - d | reach05 - d | nopour - d | coverage (bridge) |
|---|---|---|---|---|---|---|
| deficit | **0.97 / 0.98** | 0.023 | 0.000 | 0.000 | 0.000 | 145/145 |
| share | 0.96 / 0.98 | 0.045 | -0.002 | 0.000 | 0.000 | 145/145 |
| share_x | 0.93 / 0.92 | 0.065 | -0.002 | 0.001 | +0.034 | 145/145 |
| share_i | 0.92 / 0.87 | 0.067 | -0.001 | +0.015 | +0.010 | 123/145 |
| share_neck | 0.92 / 0.82 | 0.037 | -0.000 | -0.002 | +0.014 | 145/145 |

1. **Most stable: `deficit`** (highest seed correlation, smallest seed difference, insensitive to every option).
   Recommended as the scalar for router A/Bs (paired per board and seed, like opens).
2. Report **`share_neck` beside it** for any neck experiment: it is the part a router neck change can move, and the
   only definition that separates necks from class widths. Its seed noise is higher on staged (0.82).
3. `share_x` reads best ("share of the run, beyond the pad, narrower than the human") and is the only track-based one
   that credits pours; use it when a method adds zones. `deficit` and `share` count tracks only, so they cannot see a
   pour (zones-into-pads: deficit 0.59 vs 0.58 before).
4. `share_i` adds little on the corpus: without load facts the evaluator's DC plan injects default currents, and it
   is the least stable on staged (0.87). Keep it for designs with intent (obd-solar), not as the corpus headline.
5. Tolerance and pad reach do not matter (<= 0.015 change); pour credit moves share_x by 0.03-0.05.

## Caveats

1. Bridge outputs exist on 145 of the 293 boards (the mech suites mostly carry staged runs only); staged on 249.
2. The human floor is not 0: humans neck too (share 0.10, share_x 0.06), and a median reference puts up to half of a
   two-width net below it. The paired difference handles that.
3. Pour credit uses zone outlines (router outputs store no fills), so it over-credits pours cut by clearances.
4. "Power" comes from the circuit brief's roles plus human-drawn width; the brief misses some rails (e.g. `/3V3`
   labelled signal on omgs3-carrier), which the width rule catches. Impedance-wide nets (high_speed, rf, clock) are left out of `power`.
5. Human width is not an input to a route task, so on the corpus this measures haslam against human practice, not
   against a rule the router was given.
