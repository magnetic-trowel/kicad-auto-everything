<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# R6: `plane_as_obstacle` on pour boards where Freerouting and KiCad disagree

Pre-registered 2026-11-09, before any run of this experiment. Ledger R6, on R5's finding: Freerouting
says routed and KiCad says open on 2,545 of 10,655 pour boards (69 % zone-involved).

## Root cause, measured before this test
On R5's 30 boards (fork 06d2686 stored runs, `tools/research/routing/fr_pour_truth/`, KiCad's real
connectivity of the board and of the same board stripped of routing):
- 124 of the 141 open connections (88 %) are pads the bare fill connected and the routing cut off; 17
  (12 %) were already separate in the fill of the bare board.
- Pour rules Freerouting's model lacks: with zone minimum width near zero the 141 opens fall to 89; with
  thermal reliefs replaced by solid connections, to 104; with both, to 67. The other 67 are plain cuts.
- The fork's fill model (`PlaneFillConnectivity`) reports 0 cut-offs on most boards where KiCad finds them.

## Question
Does treating pours as obstacles to foreign nets (`--router.plane_as_obstacle=true`, ConductionArea
obstacle) remove those opens without costing completion? Expected: on pours covering a layer it blocks
foreign nets from the layer, so opens rise; the test says by how much. It decides whether code that
models fill rules in the router (R36, the E14 package) is worth writing at all.

## Arms, one Freerouting run per board per arm (kaeres methods; never seeds)
| Arm | Method | What |
|---|---|---|
| control | `fr-fork 2e1125a nomp r6` | Fork 2e1125a, no `-mp` cap (R11's wrapper), 900 s, 1 thread |
| plane obstacle | `fr-fork 2e1125a nomp planeobs r6` | The same plus `--router.plane_as_obstacle=true` |

Side by side: one kaeq job per board, both arms in it (`merge_jobs.py` from R11). Harness and kae at
7f17a5d (main + telemetry + bridge options; task spec 11).

## Boards
90 boards (`boards.txt`), one per `repo_family`, `usable_route_test` true, all with pours:
- 30 R5 boards (FR=0 and DRC>0 under the fork; **selected on the control's failure**, reported apart).
- 30 from `complex_pours`, 30 from `power_pours.n100`, chosen before any result, not selected on outcome.

## Measures and noise
Freerouting is deterministic for boards that finish inside the job timeout, so paired differences are
real, not noise; only boards that time out in either arm can move with host load. Reported per arm: cp1,
completion, opens (`unconnected`), zone-involved opens, per-type DRC errors, CPU, timeouts.

## Decision rule
Bar for "promising, keep investigating as a setting": on the 60 unselected boards, opens lower by at
least 10 % in total, sign test p < 0.05, DRC errors not higher in total, and cp1 not lower. If it fails,
plane_as_obstacle stays off and is not a setting to build on. The R5 boards are reported as the selected
population only.

Separately, independent of the arms, the root-cause result above decides R36/E14: the bridge's own
repair closes nearly all of these on the merit boards (zone-only opens block 1 of 213 boards under kae
bridge final), so a fork patch for fill rules helps only the plain Freerouting control. Expected cost: 90
boards x 2 arms, small boards, about 20 CPU-h.
