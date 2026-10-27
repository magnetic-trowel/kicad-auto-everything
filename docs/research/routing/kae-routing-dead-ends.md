# kae routing dead ends: longer budgets, a Freerouting fork patch, escape corridors, re-tweak, mixed routers

**Status:** did not work (longer budgets, fork patch, escape corridors, re-tweak); not finished (mixed-router portfolio).
**First published:** 2026-10-23 to 2026-10-25 on branch `claude/vigilant-mayer-i91rrr`: re-tweak [c5c53c4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c5c53c40404a972ba3ede1e0d3ab1a5dcc3e58a0), budget runner [a13b909](https://github.com/magnetic-trowel/kicad-auto-everything/commit/a13b9096f608dfc36ee038bf7a3ee6cf70ead2d1), escape corridors [50ff693](https://github.com/magnetic-trowel/kicad-auto-everything/commit/50ff693f691d148be262b7c4715bf96680cc8296), mixed portfolio [ff641dd](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ff641dd981113f64c424d68215f75e295584aa9b), fork patch noted in [88bb658](https://github.com/magnetic-trowel/kicad-auto-everything/commit/88bb6580c67299baa3031e78b4e76c460c34c042).

Five things we tried around the [bridge](kae-freerouting-bridge.md) and [critical copper](kae-critical-copper.md) that did not pay or were not finished. The common lesson: what closes the last connections is a different item order or an exact local join, not more router time or rip-ups of neighbouring nets.

## 1. Longer budgets (did not work)

**Idea.** If routing failures were clock-bound, 10× budgets would close them; the 2026-10-21 plan's R1 ("per-split budgets with partial output", [strategy-candidates.md](../../topics/routing/strategy-candidates.md)) assumed so.

**Tried.** crit-v6 at [1ef5bf1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1ef5bf10ffb86704afc8c1dd40836b2ac33ad28c): `tools/research/routing/run_crit_v4.sh`, V=v6, T_AB = 6000 s (10× the 600 s runs), T_C = 9000 s (10× 900 s), k = 3, bridge and critical arms with and without plane costs, 52,572 s wall. The fork's StopReason is parsed from its log (`freerouting._autorouter_stop`, [0865c48](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0865c488a3e90241fb1f2268c56edcf953bda657)).

**Results** ([crit-v6-10x-1ef5bf1](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md)). A+B bridge cp1 0.727, cpk 0.818: the same 70/99 clean attempts as at 1×. No A+B attempt used more than 90 % of 6,000 s; bridge stops were COMPLETED 91 / STAGNATION 8, critical arms 63 / 36. On split C only canhw-processor's first route ran long (completing after 7,000-8,500 s, still 2-9 open); other seeds route it clean in 128-190 s. The stock k = 10 baseline also has cp1 = cpk on every split ([qualified-k10-baseline](../../../bench/results/2026-10-22-qualified-k10-baseline.md)). Single run; predates the last mile.

**Verdict.** Freerouting stops on its own long before the clock. Effort moved to seed diversity ([restart portfolio](kae-restart-portfolio.md)) and exact local repair ([last mile](kae-last-mile.md)).

## 2. Freerouting fork patch `fix/last-mile-on-completed` (did not work)

**Idea.** Freerouting's own last-mile rip-up runs only on some pass-loop exits. The patch also ran it when the pass loop ends COMPLETED with connections still open, hoping Freerouting would close its own leftovers.

**Results.** "Never triggered on the target boards and closed nothing" [C] ([last-mile-and-restarts.md](../../topics/routing/last-mile-and-restarts.md)); no numbers or results file. Consistent with what the last mile found: much of what is left open is plane-net copper that Freerouting counts as connected (it treats a plane as one conduction area), so its loop sees nothing open.

**Code.** Not in this repository: a branch of the project's Freerouting fork (magnetic-trowel/freerouting), kept for the record, not for merge (handoff [70e9b41](https://github.com/magnetic-trowel/kicad-auto-everything/commit/70e9b41c5b7418cddf1f58967beef87e1c3c9bee)).

## 3. Escape corridors out of dense ICs (did not work)

**Idea.** For ICs with ≥ `escape_pins` = 32 pads, strips `escape_mm` long running out from their signal pins are priced at `escape_cost` = 3 per cell for other nets' critical copper, so the critical stage leaves fan-out room for Freerouting.

**Results.** On canhw-processor it did not reduce unconnected items (19-33 with corridors vs 13-29 without, k = 1-2) and left decap loops within 1 % [C] ([critical-net-routing.md](../../topics/routing/critical-net-routing.md)). One board, small n. Off by default (`escape_mm=0`).

**Code.** `kae/src/kae/route/critical.py`, `Session.escape_corridors`; options `escape_mm`, `escape_pins`, `escape_cost`.

## 4. Routed-physics recheck and re-tweak loop (re-tweak did not work; recheck kept as a measurement)

**Idea.** `critical_recheck.board_physics(board)` measures every module on any finished board, whoever routed it. Each net's copper becomes a graph of pads, track ends (T-junctions split tracks), vias and refilled zone regions; a hop follows the least L′(w)-weighted path; a strip's reference is the nearest layer with refilled copper of any net under it, so cuts and antipads raise L where they are; cells also report plane cover (ground-fill share of the loop hull). `recheck` flags a module whose u grew > 15 %, crossed 1, or whose plane cover fell > 0.10 against the module stage. `retweak_loop` (`--rounds N`, default 0) then rips at most the 4 shortest whole nets that cut the flagged module's planes or crowd its layer, adds a guard, lets the bridge re-route, and keeps the round only if unconnected and errors do not rise and the flagged modules improve.

**Results** ([crit-v3-4e88308](../../../bench/results/2026-10-23-crit-v3-4e88308.md), [4e88308](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4e883086fd5da7c90cbec0f41586b1d67644ad94)). A+B: 5 boards flagged, 0 kept (ripping the module's neighbours lost connections every time). C6: 4 flagged, 2 kept (libresolar-bms-c1's power path recovered 38 % of its routed loss; oasis-pcb's converter decap recovered 40 % and closed 2 connections). On paw3395 round 1 restored a decap from u 0.83 to 0.53 but raised unconnected items from 3 to 7 [C]. Re-tweak arm `r3` on A+B (k = 1): cp1 0.515, the same as without it.

**Verdict.** Rip-up of neighbours costs connections more often than it buys physics. Proposed instead: a pre-route reservation, or local re-placement through the [joint loop](../joint/kae-joint-loop.md), which reuses `modules_to_retweak` window-scoped. The recheck is the routed-physics measurement used by the soft last-mile guard and the joint loop.

**Code.** `kae/src/kae/route/critical_recheck.py` (`RoutedBoard`, `NetGraph`, `LoopBuilder`, `plane_cover`, `rail_drops`, `recheck`, `retweak_loop`, `modules_to_retweak`).

## 5. Mixed-router portfolio: critical router first, bridge second (not finished)

**Idea.** The two router families fail on different boards (on C6 the bridge closes bldcm-power and aftonsparv, critical + soft closes libresolar-bms-c1), so one [portfolio](kae-restart-portfolio.md) cycles attempts through both: `--router "kae.route.critical_cli:--planes cost --last-mile-soft" --router "kae.route.cli:--planes cost"`. Among equal results the first-listed router wins; since [03096d9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/03096d9fa4203cb6983f39592438c88410c674b7) a clean result from a later router does not end the run at once — the first router's running attempts finish first and their clean board is preferred, to keep the physics edge. Ranking fixes: critical attempts ranked by `bridge.repair.final` ([583c096](https://github.com/magnetic-trowel/kicad-auto-everything/commit/583c0961a5ff1b983b4a5a70a86a6b5a6ba531bd)); attempts too short for repair rounds ranked by their `drc` ([5b590c0](https://github.com/magnetic-trowel/kicad-auto-everything/commit/5b590c0a90b946a292415d8439a8a1fa0076878b)).

**Results.** C6 at ff641dd: 12/12 clean, 0 errors, 25-451 s per attempt, but the bridge won all 12 because it finishes first, so the physics matched the bridge (critical + soft over mixed: cells 0.783, decap 0.952) ([portfolio-ab-0465818](../../../bench/results/2026-10-24-portfolio-ab-0465818.md), section "Mixed routers on split C"). Full benchmark A+B at 03096d9: cp1 1.000, equal to the bridge portfolio, because a ranking bug marked every critical attempt failed ([full-benchmark-03096d9](../../../bench/results/2026-10-24-full-benchmark-03096d9.md)). A corrected arm at 5b590c0 on all 112 boards was queued; no result is on the branch.

**Verdict.** Not finished: the mechanism works for completion, but whether the preference rule keeps the critical router's physics has not been measured after the fix.

**Code.** `kae/src/kae/route/portfolio.py` (`run(router=[…])`, `_rank`).

## Related

[Bridge](kae-freerouting-bridge.md), [restart portfolio](kae-restart-portfolio.md), [last mile](kae-last-mile.md), [critical copper](kae-critical-copper.md), [joint loop](../joint/kae-joint-loop.md).
