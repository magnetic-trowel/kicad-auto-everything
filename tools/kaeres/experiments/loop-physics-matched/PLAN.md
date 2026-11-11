<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# loop-physics-matched: does the joint loop win physics at equal compute on boards that route? (pre-registered)

Written 2026-11-10, before any run of this experiment. Follows `loop-compute-matched`: on boards that the joint loop leaves open,
staged + restarts beat joint + windows on open connections by 26 % at equal allowance, and physics could not be judged (4 boards
fully routed in both arms). The joint loop's remaining case is physics: the module stage and the windows' physics acceptance. This tests that case directly.

## Arms (the same two methods as `loop-compute-matched`, commit f2f4151)
- **W:** joint plus two budgets of window time.
- **R:** the staged pipeline under the restart wrapper, `--parallel 1`.

Both get the same timeout (3.15 B, B = 900 s x sqrt(fp/40)), so compute is matched by allowance. They run interleaved, seed 0, k = 1.

## Boards (`select_boards.py`, seeded)
- **Pool:** `physics_inputs_ok` and `route_demand` easy or moderate, usable and qualified, one per repo family: 1,044 boards.
  - The physics tag was spot-checked before use: 106 of 114 tagged merit boards get valued physics modules, against 24 of 96 untagged.
  - The routing tag is chosen so both arms usually route fully, which makes physics comparable.
- **Intents:** a full intent exists for only 17 of these boards, so the physics evaluator's own brief (kae.circuit.brief, from the board) defines the modules, as in every kaeres physics run. Full-intent boards are reported as a subset.
- **Batches:** the first 160 boards in sha256 order (`boards.txt`). Then batches of 160 (`boards-extension.txt`, more from `boards-all.txt`) until the physics test is decided, or until 80 or more boards with differing physics are in hand without a decision.

## Primary: physics
Unit per board, on boards both arms route fully (0 open connections): over the modules valued in both arms (u known, no open hop), `x = ln(Σ min(u, 5) of W / Σ min(u, 5) of R)`. Boards with identical sums are left out.
- **W better:** median ratio below 1 by more than the J21 floor for that n (n ≥ 80: 1.04; 50: 1.05; 38: 1.06), and sign-flip p < 0.05.
- **R better:** the mirror case.
- **Equivalent:** every ratio outside [1/1.04, 1.04] rejected, with n ≥ 80.
- **Otherwise undecided:** extend.

Per structure kind (decap, crystal, converter loop, ...): the same statistic, reported but not decided. Full-intent boards: reported.

## Opens guard and other outcomes
- **The case for joint** needs W better on physics and opens not lost. On all boards with both arms: W's total opens at most 3 % above R's, and the paired opens test (sign-flip on `d`) not significantly against W.
- **Reported:** cp1, completion, DRC errors total and per type, placement errors, CPU used per arm (ratio), W's windows and kept windows, R's attempts.

## Costs (information only)
About 1 CPU-h per board and arm on small boards: about 320 CPU-h for the first 160 boards.
