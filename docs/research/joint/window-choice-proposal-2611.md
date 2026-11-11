<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Proposal: windows that choose better (untested)

Scope: designs for choosing the joint loop's windows, each with a cheap test, motivated by
[window-budget-2611](window-budget-2611.md) and J3. Nothing here is built.
Keys: joint loop, window choice, kae.route.blocked, tabu, repeated windows, illegal after repair, legal spot, window sizing, J15, J16

**Status:** untested idea. Written 2026-11-10, branch `loop-exp`.

## The evidence these answer
- **Choice is the limit, not budget.** Skipping futile windows (J3) did not raise useful windows; the loop ran out of windows sooner. From two to four budgets of window time, the median gain fell to 0.5 opens a board.
- **Repeats.** 42 % of windows at two budgets, and 53 % at four, reuse a part set an earlier window on the same board already tried. The loop recycles the same windows under new seeds once every window is exhausted.
- **Illegal windows.** About a third of windows end "illegal after repair" in every arm. More legalizer time and an incumbent fallback (J4) did not change that much: 423 down to 394. Greedy finds no spot for the window's parts inside the window.
- **Blame on the wrong parts.** A window is the parts near a spot. For an open connection that means the parts at its two ends, not the copper or parts that block the corridor. `kae.route.blocked` names those per open connection (rule, fixed copper, congestion), but only for the final board. The windows never see it.

## Designs, cheapest first

### 1. Tabu on tried part sets
Keep the outcome of every window by part set, across cycles. A part set tried twice with no improvement is tabu until the board changes nearby, meaning a kept window touches one of its parts or its rectangle. A new cycle then must try something else: grow the window (design 3) or take the next spot.
- Test: replay from stored reports first. On `loop-window-bench-v2`'s w2 and w4 runs, count the windows a tabu rule would have skipped, and how many of the kept windows were repeats. If kept repeats are rare (under 10 % of kept), tabu loses nothing.
- Then an A/B, `w2 ctl` against `w2 tabu`, on the 40 bench boards. Expected: about 40 % fewer windows, the same opens or better, CPU freed or spent on new windows.

### 2. Windows from the blocked-connection diagnosis
Run `kae.route.blocked` on the incumbent after every kept board, capped at its time budget (`diagnose_s`), not only at the end. For each open connection it names the blocking items.
- The window becomes the movable parts that own those items (the part in the corridor, or the copper's endpoints), plus the two ends.
- Connections diagnosed as "rule" (board rules forbid any route) open no window, the same reasoning as J3.
- Test: offline first, on the final boards of `loop-window-bench-v2` (the diagnosis is already stored in each report's `final.blocked`). For each open connection, check whether the blocking part sets are disjoint from the endpoint windows the loop used; if they mostly overlap, the change buys little. Then an A/B on the bench boards, `w2 ctl` against `w2 blocked`, measuring kept windows and opens.

### 3. Windows sized to contain a legal spot
Before re-placing, check that the window's rectangle has at least one grid-free spot for each of its parts, given the fixed geometry and everything outside the window. This is the same `_candidates` test as tight-part anchoring, run per window.
- If it has none, grow the window by the parts that occupy the missing room, up to the part-share cap, or drop the part from the window.
- This targets the third of windows that end illegal: they are asked to fit parts where no spot exists.
- Test: replay the illegal windows of the stored reports through `_candidates`, with no routing. If most of them have no spot in their rectangle, the check would have predicted them. Then an A/B, `w2 ctl` against `w2 sized`, with "illegal after repair" as primary and opens as secondary.

### 4. Spend saved budget on the first route's last mile
J14 (`first_last_mile=1`) cut opens 11 % at today's budget (24 of 37 boards, undecided at 40, extension running). It is not a window design. It says what time not spent on poor windows should buy.

## Order and cost
- Designs 1 and 3 replay offline from stored reports, at a few CPU-minutes each, and decide whether an A/B is worth running.
- Design 2's offline check reads `final.blocked`, already stored.
- Each A/B is two arms on the 40 bench boards, about 50 CPU-h per arm at two window budgets.
- Run after `loop-compute-matched` decides whether windows are worth their compute at all. If restarts win at equal compute, these designs must beat restarts too, not only the current windows.

## Offline replay against restarts (2026-11-10)
Script: `tools/kaeres/experiments/loop-window-bench/replay_choice.py`, run on stored loop reports. The bar is the restarts' lead in `loop-compute-matched`: R left 1,170 fewer open connections than W over the 69 boards at equal allowance. These are upper bounds: each assumes the design turns wasted window time into windows as productive as the loop's best ones.

On the 69 boards, W ran 2,146 windows:
- 1,227 new part sets: 163 kept, removing 1,220 opens in 33.9 h.
- 919 repeats: 47 kept, removing 157 opens in 14.7 h.
- 811 ended illegal.
- 1,177 were routed, removing 1,377 opens (1.17 per routed window).

| design | what the replay can bound | bound on extra opens removed | against the 1,170 needed |
|---|---|---|---|
| 1. tabu on tried part sets | repeats' 14.7 h spent at the new windows' yield (36 opens/h), minus the 157 repeats removed | ≤ +373 | a third, and only if new windows exist to fill the time: the loop stops because it has none ("no window left", J3) |
| 3. windows sized to contain a legal spot | the 811 illegal windows made legal and as productive as routed ones | ≤ +949 | under, and generous: illegal windows sit where the board is crowded |
| 2. windows from the blocked diagnosis | the stored diagnosis covers 784 of 4,038 final opens (614 congestion, 170 blocked; 3,254 undiagnosed, time-capped) and names a cause, not the blocking parts | not boundable without new diagnosis code | n/a |

Even added together with every optimistic assumption, 1 and 3 reach about +1,320, just past the gap. A realistic fraction does not. The same data on the 40 bench boards gives the same picture: at two budgets the tabu bound is +328 − 53 and sizing +415; at four budgets +516 − 76 and +440.

**Verdict: build none of them now.** None shows a plausible path to beating restarts as a replacement for them. The one design the data leaves open is a different arrangement: windows as polish on the best restart attempt (restarts first, then windows on the kept board within the same allowance), measured against restarts alone. That would test whether windows add anything on top of restarts, which is the only role this data still allows them.
