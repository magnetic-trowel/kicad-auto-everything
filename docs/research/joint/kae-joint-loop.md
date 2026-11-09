# kae joint place-and-route loop

**Status:** worked on splits A+B; clock-bound on split C; synthetic precursor ties an equal-CPU restart portfolio.
**First published:** 2026-10-23, commit [7bd163f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7bd163f432a0ce4aeb115e0bc87f3777f70f4e2e) on branch `claude/vigilant-mayer-i91rrr` (feedback, windows and scorecard [c6ae9be](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c6ae9be0d935bea6e481386ee2863f35a3c62206); theory and synthetic experiment [ba45def](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ba45defde956f7d73cf07929345b86e4793cd1aa)).

Scope: measured numbers of the kae joint loop (place, route, ask KiCad what went wrong, re-place and re-route small windows, keep a change only if a lexicographic scorecard improves), including the staged and human arms of the same A/B runs. Not here: loop design -> [joint-loop](../../topics/architecture/joint-loop.md); staged-only runs -> [kae-staged.md](kae-staged.md); synthetic setup -> [joint-place-route-experiment](../../topics/physics/joint-place-route-experiment.md); theory -> [joint-place-route](../../topics/physics/joint-place-route.md).
Keys: kae joint loop, `kae.joint`, joint-fixed, windows, feedback spots, congestion history, local re-place, local rip-up, `route_open`, lexicographic accept, per-item physics slack, finishing stage, `--route-parallel`, `--physics-fidelity`, cp1, cpk, module ratio, split C clock-bound, kae joint loop (restarts)

Merit method **"kae joint loop (restarts)"**: `joint-fixed`, 900 s, code at `1650f8e`, 4-way restart wrapper (`tools/kaeres/experiments/merit-restart.sh`); 500-board comparison (experiments merit-500r3 / merit-500r3k) running, results pending.

## Idea and how it works

Starfish-style cell moves with partial re-route at PCB scale, judged by KiCad; worst case = staged result. Full design (parameters, rules): [joint-loop](../../topics/architecture/joint-loop.md). Component map:

| component | file | one line |
|---|---|---|
| iteration 0 | `joint/stages.py` | [`kae place`](../placement/kae-placer.md) → module stage (`kae.route.critical_joint.optimize_modules`, guard pours `kae-crit:`, [critical copper](../routing/kae-critical-copper.md)) → [Freerouting bridge](../routing/kae-freerouting-bridge.md) → judge (kicad-cli DRC + routed-physics recheck) = the staged pipeline |
| feedback spots | `joint/feedback.py` | unrouted corridors, DRC errors (placement-type with KiCad's shortfall), physics flags; weights 4 / 3 / 2 / 1 + rise + cover loss |
| windows | `joint/feedback.py` | spot parts + 2 mm margin, ≤ 6 parts and ≤ 35% of movable; re-route-only windows; growing retries (margin ×1.5 and +2 parts, ≤ 2×, within the 35% share) |
| congestion history | `joint/penalty.py` | PathFinder-style history on a 1 mm grid as static extra placer demand, u_b = (D_nets + D_escape + h_b S_b) / S_b |
| local re-place | `joint/replace.py` | annealer on the window, rest locked, 6,000 moves per part, `exact.repair(allowed=window)` ([kae-exact-legality](../placement/kae-exact-legality.md)); error-named parts bumped by shortfall + 0.15 mm, unrouted-named by 0.25 mm with a 0.3 mm routing margin (see below) |
| local rip-up | `joint/ripup.py` | only copper the move invalidates; window modules re-run |
| window router | `kae/src/kae/route/incremental.py` | `route_open` (open connections, ≤ 3 passes, optimizer off) + `lastmile.close` ([last mile](../routing/kae-last-mile.md)) |
| acceptance | `joint/scorecard.py` | legality, unconnected, errors never rise; a board that becomes clean is always kept; another strict completion or DRC gain is kept if physics rises ≤ 10% of the incumbent per item gained; at equal completion and DRC, physics must fall > 0.5%; routed physics = Σ over modules of min(u, 5), missing module counted 3; rejected candidates still feed the history. `exact.configure("exact")` makes module values PEEC ([exact physics](../placement/kae-exact-physics-before-routing.md)) |
| finishing stage | `joint/stages.py` | full bridge, critical copper locked; with `--route-parallel P` the [restart portfolio](../routing/kae-restart-portfolio.md) |
| budget | `joint/loop.py` | wall clock: 30% placer, 60% of rest first route, then windows; no iteration cap; stop reasons via `tools/research/joint/joint_stops.py` |

**Bump and window margin are not the pnr dead ends.** [Bloat](forces-and-fields.md) inflated every part near a failed net and re-placed the whole board by HPWL; completion fell from 0.863 to 0.748 and dense boards stopped fitting. [`seq_margin`](sequential-controls.md) grew every keep-out a priori. Here the growth stays inside one window and is dropped before it costs legality; the result is kept only if acceptance prefers the re-routed board, so the worst case is a wasted iteration. Not ablated yet: `--set bump_mm=0` and `--set replace_margin=0` are the arms in [`placement-decide-ab.sh`](../../../tools/kaeres/experiments/placement-decide-ab.sh).

**Acceptance thresholds have an absolute floor.** The 0.5 % tolerance and the 10 %-per-item slack scale by max(1, Σu), not by Σu: one unit of Σu is one module at its full allocation, so below that the thresholds are 0.005 and 0.1 per item in absolute terms (a relative tolerance with an absolute floor, as in Python's `math.isclose`, PEP 485: "no value is small relative to zero"). Σu is 0 on boards where no module was measured, and a purely relative rule would then reject any physics rise at all. In the 136 single-run joint reports stored in `~/kae-baselines` (`kae-joint-loop` 6145a3cd; restart-wrapped runs keep no loop report), 68 % of decisions that carried physics had Σu < 1, and 33 had Σu = 0. Scaling by Σu alone would change none of the 172 equal-completion decisions and 1 of the 56 completion gains (0.334 → 0.371, +11 %, for one item: kept now, reverted under the relative rule). The floor is kept.

**Copper is reported; the copper tie-break is an A/B arm.** Each scorecard and iteration row carries `track_length_mm` and `vias`, the efficiency layer of [quality-metrics](../../topics/verification/quality-metrics.md). With `--set eff_tiebreak=1`, a candidate that ties on everything above is kept when its copper dominates: no more vias and over 1 % shorter, or fewer vias and no longer. PCBWorld's potential prices the same terms lightly (0.5 × WL / board size and 0.2 per via, against 1 per unconnected net). 157 of the 172 equal-completion decisions above were exact physics ties, which is where the tie-break would act. It is off until the A/B (decide-eval) shows it helps rather than only spending the loop's clock.

**Synthetic precursor** (`jpr_joint_vs_sequential.py`; setup, arms and numbers in [joint-place-route-experiment](../../topics/physics/joint-place-route-experiment.md)). Diagnosis of staged failure: objective mismatch (HPWL or RUDY vs length and vias vs loop L), asymmetric authority (placer cannot see copper, router cannot move parts), physics observability (loop L, plane cuts exist only with copper). Lessons used in kae (keep hard constraints hard, renegotiate drifting route state, joint search refines a converged sequential start) → [method lessons](../../topics/physics/joint-place-route-experiment.md#method-lessons-c).

## What we tried

- A+B at [4814e11](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4814e11fbd34efeeaca6646f631083f54d9713df): 33 boards, k = 2, 9,000 s, score v7, KiCad 10.0.7, `joint` kind; arms staged, joint, human + Freerouting 2.5.0. Physics from `tools/research/joint/joint_physics.py` (Σu and module values from `critical_recheck.board_physics` on the scored board; unreliable where hops are open).
- Six split-C boards with switching cells at [a28bd84](https://github.com/magnetic-trowel/kicad-auto-everything/commit/a28bd84fca0c45f669f144479b004b674bacaa26), k = 1, 9,000 s.
- Local, 6 split-B boards, seeds 0/1, 900 s: with and without the last mile in the loop, `--physics-fidelity multi`; `--route-parallel 2` on the six split-C boards (2,400 s, seed 0).

## Results

| run | joint | staged | other | source |
|---|---|---|---|---|
| A+B, 9,000 s, cp1 / cpk | **0.909** / 0.909 | 0.879 / **0.939** | human + FR 0.455 / 0.455 | [joint-ab-4814e11](../../../bench/results/2026-10-24-joint-ab-4814e11.md) |
| A+B completion; errors per board | 0.989; 0 | 0.988; 0 | 0.896; 2.61 | same |
| A+B routed physics, attempt 0: module ratio vs human (median), sum u, worst rail | **0.78**, **1.011**, 56.8 mOhm | 0.824, 1.225, 64.0 | human layout 1.0, 1.292, 47.2; human + FR 0.926 | same |
| A+B loop behaviour | stops "clean" 53x, "no improvement" 11x; never > 77% of budget; 504 windows routed, 37 kept; 12 finishing tries, 3 kept | | | same |
| split C, 6 boards, 9,000 s: clean, legal, unconnected, errors; module value | 3/6, 6/6, 44, 0; 1.01x | 3/6, 5/6, 86, 6; 1.06x | human + FR 0/6, 6/6, 131, 121 | [portfolio-ab-0465818](../../../bench/results/2026-10-24-portfolio-ab-0465818.md) |
| split C loop behaviour | 4 of 6 stop on time; 52 window and 3 finishing router timeouts | | restart portfolio with the bridge: all 12 split-C attempts clean in ≤ 450 s (why `--route-parallel` exists) | same |
| 6 split-B, 900 s, last mile in loop (seeds 0/1): clean; module value vs human | 4 / 5; 0.75 / 0.88 | with last mile 5 / 5; 1.24 / 1.33 (without: 3 / 4; 1.18 / 1.39) | | [joint-last-mile-local](../../../bench/results/2026-10-24-joint-last-mile-local.md), earlier [joint-loop-b6](../../../bench/results/2026-10-24-joint-loop-b6.md) |
| same, kaebench cp1 / cpk | 0.667 / 0.833 | 0.833 / 0.833 | | same |
| same, completion gap | PMW3610 7 / 6 unconnected | 4 / 5 | | same |
| `--route-parallel 2`, 6 split-C boards, 2,400 s | 3/6 clean; iteration 0 took 1,214-1,471 s on four boards; window routers timed out 4 of 53 times (doubling budget); window restarts improved 7 of 21 windows; portfolio finish at P = 2 never beat the loop's board (libresolar 98 vs 44 open, canhw 49 vs 18) | | | same |
| synthetic precursor (N = 30/50, 5 seeds, equal CPU) | beats its own sequential start 10/10; ties an equal-CPU restart portfolio 5/10; proxies miss near-equal placements | | | [joint-place-route-experiment](../../topics/physics/joint-place-route-experiment.md#results-c) |

Per board, A+B: joint beat staged on olimex dcdc-50-5-12 (staged illegal → joint clean), paw3395 (9 → 2 unconnected), ch552g (sum u 3.71 → 1.03); worse on badjeff-pmw3610 (4 → 5 unconnected) and bipolar-power-supply (sum u 0.87 → 1.28).

Evidence behind design rules:
- Per-item physics slack: on ch552g a window made the board clean (1 → 0 unconnected) while sum u rose 1.17 → 2.88 (a flat 10% slack reverted it); on noisecard a strict physics-never-worse rule reverted 15 → 7 open at +33% physics.
- Window size cap: a 12-part window on a 15-part board was a global re-place (17 → 28 open).
- Shortfall bump: on olimex a fixed 0.15 mm bump had not cleared 7 hole-clearance errors of 0.19–0.63 mm.
- First route without last mile when a finishing stage follows: PMW3610 iteration 0 234 s without, 381–518 s with; `lastmile.close` on a window 16–24 s on PMW3610.
- Freerouting cost per open connection 1–2 CPU s (noisecard: 28 open, 17–19 CPU s): a window is cheap only while its rip-up stays local.

All A+B and split-C runs are one benchmark run each (k attempts); local runs are 2 seeds on 6 boards.

## Verdict

Worked on small and medium boards: better first-attempt clean rate than staged and much better module physics, with staged as a guaranteed floor. Staged has the better cpk on A+B (0.939 vs 0.909). Not shown on large boards: on split C iteration 0 takes most of the budget and windows with many open connections run out of router time. The synthetic study says joint search refines, does not cold-start, and does not beat restarts at equal CPU; real boards agree that it refines. The slack and "clean is always kept" rules are design choices (confirmed by the user after the first A/B). Headline runs `joint-*-fixed-d0bdb9d` and `joint-pf` were not recorded on the branch; the merit runs replace them.

## Open questions

- Large boards: the first place-and-route alone takes 1,200-1,500 s even locally. Does `--route-parallel` stop on time at 9,000 s (queued joint-pf arm on the shared benchmark host, not measured)?
- The portfolio finish routes from scratch and loses the loop's work; restarting the bridge from the loop's own board (critical copper locked): untried.
- Boards with no room: PMW3610 sensor boards. Board 15 × 30 mm, 2 layers, no pours; the locked sensor U1 (PTH, 16 pins) fills the lower half; every small part sits at y ≈ 82–95 mm. Open connections run from that cluster to U1's pad columns (x = 144.7 and 155.3). Windows pick the parts that wall them off (C10, C7, C5, C2, R1 at y ≈ 91–92) and are the most-tried windows, but the band between cluster and U1 is full. Closing it needs a re-place that spreads the cluster upward, more than a window's 5–8 parts.
- Clean boards with a flagged module run to the clock (oasis, aftonsparv locally).
- Placement errors the placer leaves (libresolar: 2 clearance errors) are repaired first, but on a clock-bound board few windows run.

## Code

- `kae/src/kae/joint/{cli,loop,stages,feedback,penalty,replace,ripup,scorecard}.py` (about 2,100 lines); uses `kae.place`, `kae.route.{critical_joint,bridge,incremental,lastmile,portfolio}`.
- Run: `PYTHONPATH=kae/src python -m kae.joint.cli run IN OUT --time S --seed N [--max-iters N] [--no-modules] [--no-physics] [--start PLACED] [--route-parallel P] [--physics-fidelity fast|exact|multi] [--no-finish] [--set KEY=VALUE]`.
- Study tools: `tools/research/joint/{joint_physics.py,joint_stops.py,run_joint_ab.sh}`; synthetic experiment `tools/research/physics/jpr_joint_vs_sequential.py`, `rt_jpr_stats.py` (instances from `tools/research/solver-bench`). Tests: `kae/tests/test_joint_*.py`.
- First appearances: loop, stages, rip-up, CLI [7bd163f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7bd163f432a0ce4aeb115e0bc87f3777f70f4e2e); feedback, penalty, replace, scorecard [c6ae9be](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c6ae9be0d935bea6e481386ee2863f35a3c62206); per-item slack [db05af5](https://github.com/magnetic-trowel/kicad-auto-everything/commit/db05af54d04792d0132b44e0ca33334d94f650d6); history hook [759f0e8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/759f0e88554741e7b83c6c25f99279304c3be9a1); `route_open` [93f0f47](https://github.com/magnetic-trowel/kicad-auto-everything/commit/93f0f47504cd945ddf0022dc67bd26ede7b85989); `--route-parallel` [9ae9507](https://github.com/magnetic-trowel/kicad-auto-everything/commit/9ae95073129de4f4ff83ecfc8fb371872230b0e2); month-plan precursor (module stage -> routing -> recheck -> re-tweak) [beb47b4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/beb47b41286f5628feffa88bad45ab691fc28375); synthetic study [ba45def](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ba45defde956f7d73cf07929345b86e4793cd1aa), stats [0dfe51a](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0dfe51aadd1968b83f8425a2197befc98c3d32ea).

## Related

[kae-staged](kae-staged.md), [kae-placer](../placement/kae-placer.md), [critical copper](../routing/kae-critical-copper.md), [routing dead ends: re-tweak loop](../routing/kae-routing-dead-ends.md), [status 2026-10-25](../../topics/architecture/status-2026-10-25.md).
