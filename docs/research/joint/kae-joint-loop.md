# kae joint place-and-route loop

**Status:** worked on splits A+B; clock-bound on split C; synthetic precursor ties an equal-CPU restart portfolio.
**First published:** 2026-10-23, commit [7bd163f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7bd163f432a0ce4aeb115e0bc87f3777f70f4e2e) on branch `claude/vigilant-mayer-i91rrr` (feedback, windows and scorecard [c6ae9be](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c6ae9be0d935bea6e481386ee2863f35a3c62206); theory and synthetic experiment [ba45def](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ba45defde956f7d73cf07929345b86e4793cd1aa)).

A loop that places, routes, asks KiCad what went wrong and then re-places and re-routes only small windows around the problems, keeping a change only if a lexicographic scorecard (legality, completion, DRC, then physics) says it is better. Its worst case is the staged result (place, then route). On the 33 boards of splits A+B at 9,000 s it is clean on attempt 1 on 0.909 of boards (staged 0.879, human placement + Freerouting 2.5.0 0.455) with routed module physics at 0.78x the human layout's. On split C the first place-and-route alone eats 1,200-1,500 s and the loop runs out of clock.

This is the merit method **"kae joint loop (restarts)"** (`joint-fixed`, 900 s, code at `1650f8e`, wrapped in a 4-way restart; `tools/kaeres/experiments/merit-restart.sh`). The 500-board comparison (experiments merit-500r3 / merit-500r3k) is running. Results on the 500-board comparison: pending.

## Idea and how it works

Starfish-style cell moves with partial re-route at PCB scale, judged by KiCad. Design doc: [joint-loop](../../topics/architecture/joint-loop.md).

**Theory and synthetic precursor.** Staged place-then-route gets stuck for three reasons: objective mismatch (HPWL or RUDY for placement, length and vias for routing, loop L for physics), asymmetric authority (the placer cannot see copper, the router cannot move parts) and physics observability (loop L and plane cuts exist only once copper exists). A synthetic experiment (`jpr_joint_vs_sequential.py`) on generated 2-layer grid boards (N = 30 and 50 parts, seeds 0-4, utilization 0.6; R/C, SOT-23, SOIC-8, QFN-32, TQFP-64, headers, keep-outs; 1-3 hot loops VIN -> C0603 -> GND) used a PathFinder referee (0.5 mm grid, via = 4 steps, bottom layer cost 2x, <= 40 passes) that re-routes every final placement from scratch. Routed objective J = wirelength + 2 vias + bottom length + 4 hot-loop area + 40 failed nets + 100 violations. Arms at equal CPU (50 s): sequential SA (HPWL + straight loop area), with a crossing proxy, longer, a restart portfolio, and joint SA (start from sequential; each move rejected if illegal, else rip-up and A* re-route of the affected nets, accepted on routed J). Lessons used in kae: keep hard constraints hard (reject illegal moves before routing: 3-7x more routed moves), incremental route state drifts (renegotiate), and use joint search as a refinement after a converged sequential start. Theory: [joint-place-route](../../topics/physics/joint-place-route.md); experiment: [joint-place-route-experiment](../../topics/physics/joint-place-route-experiment.md).

**Iteration 0 = staged pipeline.** [`kae place`](../placement/kae-placer.md) -> **module stage** (`kae.route.critical_joint.optimize_modules`: module parts and their critical copper optimized together, then locked, with guard pours named `kae-crit:`; see [critical copper](../routing/kae-critical-copper.md)) -> the [Freerouting bridge](../routing/kae-freerouting-bridge.md) routes the rest around the locked copper -> **judge**: kicad-cli DRC with zone refill, plus the routed-physics recheck against the module-stage values.

**Feedback spots** (`joint/feedback.py`). From KiCad's report on the routed board:
- unrouted (`unconnected_items` -> two items, parts from "of REF"; corridor = segment between them, width = length / 5 clamped to 1-4 mm);
- DRC errors, attributed to parts and routing uuids; placement-type errors between pads or footprints become placement spots carrying KiCad's shortfall (required - actual);
- physics, from the recheck: routed u up > 15%, u crossing 1, or > 0.10 of plane cover lost.

Spot weights: placement 4, unrouted 3, errors 2, physics 1 + rise + cover loss.

**Windows.** The spot's own unlocked parts plus parts within a 2 mm margin of the spanned region, nearest first, <= 8 parts and <= 35% of movable parts (>= 3). Locked, Edge.Cuts-carrying and staged parts never move; on a first attempt parts with > 12 connected pads stay fixed (moving an MCU rips every net). Overlapping windows merge within the cap; spots with no movable part get re-route-only windows; rejected windows retry larger (margin x1.5, <= 2x), congestion weight x1.5, physics weight x2; odd retries send the window's module nets to the bridge.

**Congestion history** (`joint/penalty.py`). PathFinder-style history on a 1 mm grid: +1 (in units of bin supply) along each failed corridor for every routed evaluation, accepted or not, plus 0.5 max(0, u - 0.5) of the placer's RUDY within 3 mm of a failure. Resampled to the annealer's bins, it enters the placer's congestion as static extra demand, u_b = (D_nets + D_escape + h_b S_b) / S_b, so both engines stay exactly incremental; the congestion weight doubles (30 -> 60) inside a window. RUDY alone never opens a window.

**Local re-place** (`joint/replace.py`). A Problem built from the current board with everything outside the window locked (exact poses, any angle). Window parts start at their current poses; parts named by placement errors are bumped by shortfall + 0.15 mm (`Problem.bump`), parts named by unrouted connections by 0.25 mm with a 0.3 mm routing margin (both dropped if they make the window illegal); KiCad's errors become exact constraints; nets of unrouted connections weigh 2x. The annealer runs with physics, order rules and history; a fixed move count (6,000 per part) keeps it reproducible. Legality closes with grid legality, the greedy legalizer and `exact.repair(allowed=window)` ([kae-exact-legality](../placement/kae-exact-legality.md)); illegal windows are dropped before routing.

**Local rip-up** (`joint/ripup.py`). Small nets on moved parts are ripped whole (Freerouting will not join a fragment in its middle); poured, ground, rail or >= 20-pad nets only inside the window or at moved pads; other nets' items inside the window, the 4 shortest whole; critical copper of modules with a moved part or copper in the window is removed and the module stage re-run with outside parts locked; guards recomputed. For the window router the rip-up is fully local.

**Window router.** `route_open` (`kae/src/kae/route/incremental.py`): the bridge's constraint translation, only open connections, <= 3 autorouter passes, optimizer off, item order from the seed, no repair rounds; then `lastmile.close` ([last mile](../routing/kae-last-mile.md): grid router with negotiated rip-up of unlocked tracks, critical copper fixed). Windows left with <= 8 open get 2 extra seeded `route_open` runs under `--route-parallel`. The window router budget starts at 60 s, doubles after a timeout (<= 5% of the total), halves after a fast run.

**Acceptance** (`joint/scorecard.py`). Scorecard: legality (KiCad placement-type errors), completion (unconnected items), DRC errors (library-environment checks excluded), routed physics sum over modules of min(u, 5) with a missing module counted 3. Lexicographic accept: legality, unconnected and errors must never rise; a board that becomes clean is always kept; another strict completion or DRC gain is kept if physics rises by <= 10% of the incumbent per item gained; at equal completion and DRC, physics must fall > 0.5%. Rejected candidates still feed the history. `exact.configure("exact")` makes module values PEEC ([exact physics](../placement/kae-exact-physics-before-routing.md)).

**Finishing stage** (`joint/stages.py`). A full bridge (repair rounds auto, last mile) over the whole board with critical copper locked; if connections stay open, a second try releases module copper on their corridors, priced by the accept rule. The first route skips the last mile when a finishing stage follows. With `--route-parallel P` the finish is the [restart portfolio](../routing/kae-restart-portfolio.md) on the current placement with the loop's routing removed.

**Budget and stopping** (wall clock). 30% placer, 60% of the rest for the first route, then windows; reserves for finishing max(120 s, 20%) and the final write max(25 s, 4%). No iteration cap: stop when clean with no module flagged, when the time left is below what a window takes, or after two cycles in a row keep nothing; exhausted windows are resampled with new seeds; more tries per window with longer budgets (2 + one per 30 minutes). Every stage reports its stop reason (`tools/research/joint/joint_stops.py`).

## What we tried

- A+B at [4814e11](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4814e11fbd34efeeaca6646f631083f54d9713df): 33 boards, k = 2, 9,000 s, score v7; arms staged, joint, human + Freerouting 2.5.0.
- Six split-C boards with switching cells at [a28bd84](https://github.com/magnetic-trowel/kicad-auto-everything/commit/a28bd84fca0c45f669f144479b004b674bacaa26), k = 1, 9,000 s.
- Local runs on 6 split-B boards, seeds 0/1, 900 s: with and without the last mile in the loop, `--physics-fidelity multi`; `--route-parallel 2` on the six split-C boards (2,400 s, seed 0).
- Synthetic experiment, 5 seeds x 2 sizes.

## Results

| run | joint | staged | other | source |
|---|---|---|---|---|
| A+B, 9,000 s, cp1 / cpk | **0.909** / 0.909 | 0.879 / **0.939** | human + FR 0.455 / 0.455 | [joint-ab-4814e11](../../../bench/results/2026-10-24-joint-ab-4814e11.md) |
| A+B completion; errors per board | 0.989; 0 | 0.988; 0 | 0.896; 2.61 | same |
| A+B routed physics, attempt 0: module ratio vs human (median), sum u, worst rail | **0.78**, **1.011**, 56.8 mOhm | 0.824, 1.225, 64.0 | human layout 1.0, 1.292, 47.2; human + FR 0.926 | same |
| A+B loop behaviour | stops "clean" 53x, "no improvement" 11x; never > 77% of budget; 504 windows routed, 37 kept; 12 finishing tries, 3 kept | | | same |
| split C, 6 boards, 9,000 s: clean, legal, unconnected, errors | 3/6, 6/6, 44, 0 | 3/6, 5/6, 86, 6 | human + FR 0/6, 131 unconnected, 121 errors | [portfolio-ab-0465818](../../../bench/results/2026-10-24-portfolio-ab-0465818.md) |
| 6 split-B, 900 s, last mile in loop (seeds 0/1): clean; module value vs human | 4 / 5; 0.75 / 0.88 | with last mile 5 / 5; 1.24 / 1.33 | | [joint-last-mile-local](../../../bench/results/2026-10-24-joint-last-mile-local.md) |
| same, kaebench cp1 / cpk | 0.667 / 0.833 | 0.833 / 0.833 | | same |
| `--route-parallel 2`, 6 split-C boards, 2,400 s | 3/6 clean; iteration 0 took 1,214-1,471 s on four boards; window restarts improved 7 of 21 windows; portfolio finish never beat the loop's board (libresolar 98 vs 44 open, canhw 49 vs 18) | | | same |
| synthetic, joint vs its own sequential start | better 10/10 (median -18% J, p = 0.002) | | | [joint-place-route-experiment](../../topics/physics/joint-place-route-experiment.md) |
| synthetic, joint vs equal-CPU restart portfolio | tie 5/10, median J ratio 0.96 (95% CI 0.83-1.24); physics term effect 0.99 (0.93-1.05) | | | same |
| synthetic proxies | HPWL vs routed J Spearman 0.87-0.94, but 44% of pairs within 3% HPWL differ > 10% in J; straight vs routed loop area 0.23-0.79; a routed move costs ~25x an HPWL move | | | [joint-place-route](../../topics/physics/joint-place-route.md) |

Per board on A+B: joint beat staged on olimex dcdc-50-5-12 (staged illegal -> joint clean), paw3395 (9 -> 2 unconnected), ch552g (sum u 3.71 -> 1.03); worse on badjeff-pmw3610 (4 -> 5 unconnected) and bipolar-power-supply (sum u 0.87 -> 1.28). Evidence for the per-item physics slack: on ch552g a window made the board clean while sum u rose 1.17 -> 2.88 (a flat 10% slack reverted it); on noisecard a strict physics-never-worse rule reverted 15 -> 7 open at +33% physics. Window size cap: a 12-part window on a 15-part board was a global re-place (17 -> 28 open). All A+B and split-C runs are one benchmark run each (k attempts); the local runs are 2 seeds on 6 boards.

## Verdict

Worked on small and medium boards: better first-attempt clean rate than staged and much better module physics, with staged as a guaranteed floor. Not shown on large boards: on split C iteration 0 takes most of the budget and windows with many open connections run out of router time; the portfolio finish routes from scratch and loses the loop's work (restarting from the loop's own board was not tried). Known weak spots: boards with no room (PMW3610 sensor boards, 15 x 30 mm, the locked sensor fills half; 5-8-part windows cannot spread the cluster); clean boards with a flagged module run to the clock; staged has the better cpk on A+B (0.939 vs 0.909). The synthetic study says joint search is a refiner, not a cold start, and does not beat restarts at equal CPU; real boards agree that it refines. The slack and "clean is always kept" rules are design choices. Headline runs `joint-*-fixed-d0bdb9d` and `joint-pf` were not recorded on the branch; the merit runs replace them.

## Code

- `kae/src/kae/joint/{cli,loop,stages,feedback,penalty,replace,ripup,scorecard}.py` (about 2,100 lines); uses `kae.place`, `kae.route.{critical_joint,bridge,incremental,lastmile,portfolio}`.
- Run: `PYTHONPATH=kae/src python -m kae.joint.cli run IN OUT --time S --seed N [--max-iters N] [--no-modules] [--no-physics] [--start PLACED] [--route-parallel P] [--physics-fidelity fast|exact|multi] [--no-finish] [--set KEY=VALUE]`.
- Study tools: `tools/research/joint/{joint_physics.py,joint_stops.py,run_joint_ab.sh}`; synthetic experiment `tools/research/physics/jpr_joint_vs_sequential.py`, `rt_jpr_stats.py` (instances from `tools/research/solver-bench`). Tests: `kae/tests/test_joint_*.py`.
- First appearances: loop, stages, rip-up, CLI [7bd163f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7bd163f432a0ce4aeb115e0bc87f3777f70f4e2e); feedback, penalty, replace, scorecard [c6ae9be](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c6ae9be0d935bea6e481386ee2863f35a3c62206); per-item slack [db05af5](https://github.com/magnetic-trowel/kicad-auto-everything/commit/db05af54d04792d0132b44e0ca33334d94f650d6); history hook [759f0e8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/759f0e88554741e7b83c6c25f99279304c3be9a1); `route_open` [93f0f47](https://github.com/magnetic-trowel/kicad-auto-everything/commit/93f0f47504cd945ddf0022dc67bd26ede7b85989); `--route-parallel` [9ae9507](https://github.com/magnetic-trowel/kicad-auto-everything/commit/9ae95073129de4f4ff83ecfc8fb371872230b0e2); month-plan precursor (module stage -> routing -> recheck -> re-tweak) [beb47b4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/beb47b41286f5628feffa88bad45ab691fc28375); synthetic study [ba45def](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ba45defde956f7d73cf07929345b86e4793cd1aa), stats [0dfe51a](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0dfe51aadd1968b83f8425a2197befc98c3d32ea).

## Related

[kae-staged](kae-staged.md), [kae-placer](../placement/kae-placer.md), [critical copper](../routing/kae-critical-copper.md), [routing dead ends: re-tweak loop](../routing/kae-routing-dead-ends.md), [status 2026-10-25](../../topics/architecture/status-2026-10-25.md).
