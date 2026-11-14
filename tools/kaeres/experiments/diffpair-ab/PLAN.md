<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# diffpair-ab: route differential pairs as pairs (pre-registered plan)

Written 2026-11-09, before any run of this experiment. Ledger E36, E37, R60, R61. Code: the commit recorded by `setup.sh`.

## Amendment, 2026-11-11 (before any result was read)
The primary pair measures are now the bus scorecard's (`kae.bus.scorecard`, merged in #51): **`coupled_3w`** (share of each leg's pad-to-pad length whose partner runs within 3 trace widths edge to edge, same layer) replaces the coupled share within 0.5 mm over all copper, and **pad-to-pad skew** (`skew_mm`, difference of the two legs' pad-to-pad path lengths) replaces the difference of the legs' total copper. Vias per pair are 2 x `vias_lane`; the 4 mm minimum applies to the control's `len_mean`.

Why: the repository now measures pairs once, in the scorecard; `kae.route.pairs` (#42, merged) dropped its second measurement and `tools/kaeres/pair_report.py` with it. Keeping the old measure for this experiment alone would mean two definitions of the same quantity. Decided on 2026-11-11, when 4 of 240 jobs had finished (two boards with all three arms) and no pair of any run had been measured. While checking which runs existed, the DRC columns of `results.csv` for those two boards were seen; this change does not touch the guardrails, which come from those columns. Thresholds, guardrails, arms, boards and the decision rule are unchanged. What the scorecard measures differently: only pairs with a pad-to-pad path between two common end parts in both arms (fewer pairs than all copper), and no stubs. The tier is still `kae.route.pairs`, read from the human board with its project rules (`analyze.py`).

How to read it now: `kaeres exp report diffpair-ab3`; `kaeres bus submit diffpair-ab3 --boards @tools/kaeres/experiments/diffpair-ab/boards.txt --method "kae bridge dp-control 486f2f1" --method "kae bridge dp-first 486f2f1" --method "kae bridge dp-post 486f2f1" --kae <this branch's head>`; then, in a kae venv, `analyze.py diffpair-ab3 "<control>" "<arm>"` once per arm. The experiment's name is `diffpair-ab3` (three arms); `diffpair-ab` below is the plan's original name.

## Question
Does routing high-speed differential pairs as pairs first (`kae.route.pair_route`, locked copper) give coupled, length-matched pairs at no cost in opens or DRC errors, compared with the bridge routing them as unrelated nets? From bare placement (the benchmark's route task); no human copper is kept or restored.

## Boards (`boards.txt`, `select_boards.py`, seed `diffpair-ab-2026-11-09`)
Pool: union of the n100 suites `diffpair_nets`, `diffpair_rules`, `if_usb2`, `if_usb3`, `if_hdmi.tmds_pairs`, `if_mipi`, `if_pcie`, `if_ethernet`, `if_lvds` (663 boards), scanned on their human layouts. A board qualifies with at least one real pair that matters: tier rule or interface (`kae.route.pairs`), KiCad's own suffix rule, both legs at least 4 mm, human coupled share at least 0.5 (a pair the designer ran as one), the pads of the pair within 2 mm on one footprint, `usable_route_test`, 30 to 500 footprints. One board per `repo_family`, ordered by sha256(seed, id), first 120 (of 367 qualifying families). This selects on the human layout only, never on an arm's result. Extension: the next 120 of the same order (rule below).

## Arms (same commit, interleaved in each board's jobs, kaeq timed class, k = 1, 900 s, seed 0)
- control: `kae.route.cli route {input} {output} --seed {attempt} --time {timeout}` (current bridge, Freerouting fork 2e1125a)
- first: the same with `--pairs first` (pairs routed and locked before the bridge)
- post: the same with `--pairs post` (240 s of the repair rounds kept for it; re-lays the routed board's pairs as pairs, then the last mile, and keeps that board only when KiCad finds it no worse in opens and errors)

Nothing else differs. Each of `first` and `post` is compared with `control`, separately. Freerouting is deterministic for a fixed input (run once per board per arm; no seeds).

A small comparison on 9 boards before this plan (not part of this experiment, code at `diffpair-route` before the `post` option; `post` there had an extra last mile): control opens 641, errors 161, coupled 0.146, skew 2.14 mm; first opens 669, errors 190, coupled 0.615, skew 1.20 mm; post opens 594, errors 157, coupled 0.476, skew 2.07 mm. Neither dominated, so both run here.

## Outcomes
Pairs measured: tier rule or interface, both legs routed in both arms, each leg at least 4 mm in the control (`analyze.py`, on `pair_report.py`'s `pairs.csv`). Paired by (board, pair). Intervals bootstrap over boards.

Primary, for each arm against control, directional and sized in advance, larger than any ambiguity of the measures:
- **Coupled share**: median paired change at least +0.30. Control expected about 0.1-0.15; a working pair router should reach at least 0.5-0.6.
- **Skew**: median paired ratio arm/control at most 0.5. Control expected about 1.3-2 mm.

Guardrails (no worse), evaluated on every board where both arms ran, from `results.csv` (KiCad DRC on the re-opened board):
- **Open connections**: total change at most +5 % (95 % bootstrap interval over boards entirely at or below +5 %). A/A noise of a total on merit boards is 2.8 % (`aa-joint`), so 5 % is the smallest effect a +0 change can be told from.
- **DRC errors**: total error count change at most +5 % by the same test. Read by type: any new `shorting_items`, `tracks_crossing`, or `clearance` error on the pair nets is a defect, whatever the total does.
- `cp1` not lower by more than the noise at this n (A/A 0.5 pp at 213 boards), reported with flips.

Secondary, reported, not deciding: vias per pair; physics Σu on both-complete boards (kaeres routed physics, ratio against J21's floor for the number of such boards); CPU; share of pairs the router closed; per interface; the subsets pairs crossing a plane change or a layer change in the control (`ref_changes`, vias > 0).

## Decision (each arm against control, then between them)
- **Pass**: both primaries reached (intervals exclude the thresholds' failing side) and both guardrails hold: the arm is a candidate for the recommended bridge option (default stays off until the user chooses).
- If both pass, compare `first` and `post` on the primaries; a choice is the user's.
- **Partial**: primaries reached, a guardrail fails: report by board size and tier; look at the worst per-board loss before any default change.
- **Fail**: a primary not reached: report the distribution and the router's failure reasons. No default change.

## Extension
If a guardrail's interval straddles +5 % while the primaries pass for an arm, run the next 120 boards of the same order and report the combined interval; one extension only, read once.

## Cost (as information)
Estimated 120 boards x 2 arms x up to 900 s, Freerouting and DRC; about 100-180 CPU-h through kaeq (three arms), all board sizes capped at 500 footprints.

## Afterwards
`pair_report.py diffpair-ab -j 8`, `kaeres exp report diffpair-ab`, `analyze.py diffpair-ab "<control>" "<pairs>"`. Results and verdict in `docs/research/routing/` on the PR branch.
