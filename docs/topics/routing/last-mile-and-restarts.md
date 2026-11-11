# Last mile and restarts: closing what the router leaves open

Scope: why more router time does not close the last connections, what does (last mile, restarts), the `blocked` report, host memory/slot limits. Not here: last-mile mechanism, parameters and runs -> [research: last mile](../../research/routing/kae-last-mile.md); portfolio runs -> [research: restart portfolio](../../research/routing/kae-restart-portfolio.md); rip-errors -> [research: repair loop](../../research/routing/kae-repair-loop.md); later rule fixes -> [research: closing open connections](../../research/routing/kae-closing-open-connections.md).
Keys: last mile, lastmile.py, restarts, restart portfolio, kae.route.portfolio, waves, first_s, budgets, COMPLETED, STAGNATION, autorouter_stop, plane-net islands, rounds=auto, router_share=auto, repair_reserve_s, blocked report, kae.route.blocked, congestion, fixed copper, binding rule, soft critical tier, --last-mile-soft, mixed portfolio, KAE_FR_XMX, KAE_FR_SLOTS, OOM rc=-9, slot_gave_up, pmw3610

**Results**
1. More time does not close the last connections: at 10× budgets on A+B the bridge stopped on its own (COMPLETED or STAGNATION) on every attempt; clean attempts stayed 70/99, as at 1× ([10x sweep](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md); → [dead ends § 1](../../research/routing/kae-routing-dead-ends.md#1-longer-budgets-did-not-work)).
2. What closes them: a last mile after the repair rounds (joins each open net with the critical router's exactly checked grid search, rips only what it must) and restarts (short, differently seeded attempts in parallel, first clean one kept).
3. Last mile, A+B k=3: bridge cp1 0.727 → 0.909, cpk 0.818 → 0.970, 0 errors, no physics cost ([A+B](../../../bench/results/2026-10-24-last-mile-ab-57487e6.md)); split C (C6): cpk 0.50 → 0.833 ([C6](../../../bench/results/2026-10-24-last-mile-c6-57487e6.md)). On by default (`--[no-]last-mile`).
4. Restart portfolio (`kae.route.portfolio`), A+B k=3: 99/99 clean attempts vs 91/99 for one attempt; worst case 224 s vs 1,626 s; C6 12/12 ([portfolio](../../../bench/results/2026-10-24-portfolio-ab-0465818.md)).
5. The bridge alone and critical copper with the soft last mile fail on different boards; a mixed portfolio gets the union.

## Why budgets do not help

- Freerouting stops by itself on COMPLETED or STAGNATION, after its own last-mile rip-up; its log says which (`router.report.autorouter_stop` / `optimizer_stop`, [freerouting.py](../../../kae/src/kae/route/freerouting.py)).
- What is left is of two kinds: signal connections Freerouting found no legal path for although one exists (paw3395 MOSI); plane-net copper only KiCad sees as cut off (a pad outside its fill, a fill island of a split pour). Freerouting treats a plane as one conduction area, so it reports 0 incomplete connections on such boards.
- A fork patch running Freerouting's last-mile rip-up also on COMPLETED with open connections never triggered on the target boards and closed nothing [C]; kept unpushed on fork branch `fix/last-mile-on-completed` → [dead ends § 2](../../research/routing/kae-routing-dead-ends.md#2-freerouting-fork-patch-fixlast-mile-on-completed-did-not-work).
- Repair rounds stop on improvement, not the clock; `rounds="auto"` lifts the cap of 5; a loop ending on the cap records `stopped: "round cap"`. On bms-c1 the "free" rounds were still gaining (29 → 15 open) when the cap hit.
- `router_share="auto"` and `repair_reserve_s` give the first route all but 600 s of a long budget; opt-in until a suite run confirms them ([bridge.py](../../../kae/src/kae/route/bridge.py)).

## Last mile in brief

[lastmile.py](../../../kae/src/kae/route/lastmile.py), driven by `repair._last_mile`; full steps, constants (`RIP_COST` 20, `HIST_WEIGHT`, `HIST_MAX` 3, `MAX_JOINS` 40 except in the repair loop, where a round has no join cap and stops at its deadline, about half the time left; window margins 1/3/8/15 mm) and fixed bugs → [research: last mile](../../research/routing/kae-last-mile.md#idea-and-how-it-works).
Reload board as KiCad sees it (zones refilled) → split each open net into connected parts → join smaller parts by `GridRouter.connect` in growing windows → if none, rip only the foreign unlocked items the new copper violates (≤ 40 per join) → negotiated re-route of ripped nets with rising rip prices → via-in-pad escape for walled-in pads → accept a round only if KiCad DRC is better with no more errors (or no more beyond the input's). No cap on open connections (`LAST_MILE_MAX` removed in c78dfb8) and no 0-error precondition (db8c15d): `repair._rip_errors` first takes out the router copper that remaining errors name, then the last mile routes what is open whether or not errors remain → [repair loop](../../research/routing/kae-repair-loop.md). Rounds stop after 2 rip-up rounds in a row are not kept, or with < 30 s left.

## What stays open: the `blocked` report

[blocked.py](../../../kae/src/kae/route/blocked.py). The router never relaxes a board rule. After the last mile each still-open connection is tested in lastmile's grid and Space:
1. Path exists without our other copper → `congestion`; also without the input's pre-routes → `fixed copper`.
2. Otherwise a relaxed search (only overlap hard, every clearance a price per cell) finds the cheapest path; its narrowest real gap names the binding rule.
3. A finer search tries narrower tracks, so a track-width minimum is told apart from a clearance.
4. Report: the rule's source, or the kae default and its override; the caller decides ([kae README](../../../kae/README.md#kaeroute)).

Checked on the merge2 final boards [C]:
- bcecoop rmlv1616a: all 4 blocked by SRAM1's solder-mask openings (margin 0.1 + mask-to-copper 0.1).
- fona-800: 2 by the 0.2 mm board-minimum track width, 2 by kae's thermal corridors at U1.12, 1 by a no-net copper graphic over U1.77.
- atlantis can485: A4's U1.57 lies under the no-net pad U1.66.
- smol-esp32: 37 of 56 by the 0.2 mm minimum width at the 0.4 mm-pitch U2 (0.127–0.16 mm would pass).
- fm4dd, siderakb and noggin: all congestion.

## Soft tier and mixed portfolio

- Soft critical tier (`--last-mile-soft`, crit only): when only critical copper blocks a join, a last tier may rip it at 3× price, guarded by the joint loop's accept rule → [research: last mile § Soft critical tier](../../research/routing/kae-last-mile.md#soft-critical-tier---last-mile-soft). Locally on six A+B boards it made paw3222 clean with better physics (1.857 → 1.699), no help on pmw3610 boards [C]; at 2ec702e critical + soft was the first arm to route libresolar-bms-c1 clean ([C6](../../../bench/results/2026-10-24-last-mile-c6-57487e6.md)).
- Restart portfolio ([portfolio.py](../../../kae/src/kae/route/portfolio.py)): `python -m kae.route.portfolio route IN OUT --parallel P --first-s F [--router M[:ARGS]]...`; waves of `parallel` seeds, wave budget starts at `first_s` and doubles; attempts rank as the restart wrapper's judge and the harness do: fewer open connections first, then fewer DRC errors beyond the input's own (`repair.input_errors`); the first attempt routed fully (0 open, no error beyond the input's) stops the rest, else the best is kept. Final last mile: the kept board gets one more (`bridge.last_mile_only`), with time reserved from the start and all time left at the end, however late its attempt ended; kept only if it ranks better (`--no-final` turns it off; the restart wrapper's `--final` does the same for any method). Then finish (stage 7, `kae.route.cli finish`) on the kept board, clean or not, in the time left; nothing reserved, kept when no worse (`--no-finish` turns it off; the restart wrapper's `--finish`) → [routing stages § 7.1](routing-stages.md#71-finish-runs-in-the-time-left). Routing time is heavy-tailed and winners come from deep in the seed sequence (paw3395 won with its 9th and 10th seeds): item-order diversity closes the last connections, not attempt length; canhw-processor's "clock-bound" first route was a bad order (other seeds clean in 128–190 s). Cost: up to `parallel` cores and JVMs per board → [research: restart portfolio](../../research/routing/kae-restart-portfolio.md).
- Mixed routers: attempts cycle through listed routers; among equal results the first-listed wins and its running attempts finish before a later router's clean result ends the run. List the physics-first router first, else the faster bridge wins every board and the physics edge is lost → [dead ends § 5](../../research/routing/kae-routing-dead-ends.md#5-mixed-router-portfolio-critical-router-first-bridge-second-not-finished).

## Hosts

Memory and slots:
- Heap: a Freerouting JVM grows toward its heap cap (`KAE_FR_XMX`, default 6g) whether or not the board needs it: ~6.5 GB on canhw.
- OOM kills: several JVMs on a 16 GB host get OOM-killed (`rc=-9`), silently turning results into quick-pass or failed-repair boards; check `rc` in every report.
- Slots: `freerouting.route` takes one of N host-wide flock slots (`KAE_FR_SLOTS`, else 60% of memory over heap + 0.5 GB); the wait is subtracted from Freerouting's deadline, warning logged past 10% of the budget; after the whole budget it runs without a slot (`slot_gave_up`) rather than hang.
- Sandboxes: kaebench gives each attempt a private /tmp, so there `-j` and the heap cap govern memory.

## Operating rules

- Last mile on, with the no-new-error rule; route through the portfolio (or the restart wrapper with `--final` and `--finish`) when cores allow, so the kept board gets a last mile of its own; on small hosts `KAE_FR_XMX=3g` and at most two JVMs.
- Mixed portfolio for physics: `kae.route.critical_cli … --last-mile-soft` first, `kae.route.cli` second.
- Do not tune budgets; spend effort on diversity (seeds, routers) and exact local repair.
- Make `rounds="auto"` the default if the suite run confirms it.

## Open questions

- pmw3610 boards: on siderakb-pmw3610 and badjeff-pmw3610 every last-mile join forces rip-ups neither Freerouting nor the negotiated re-route can absorb (1–5 open with critical copper); the portfolio closes siderakb sometimes.
- The guard's clean exemption follows the joint loop (a board that becomes clean is kept whatever its physics); whether critical copper re-laid that way costs physics on the suite is unmeasured.
- Unreproduced HV clearance: in one critical attempt on libresolar-bms-c1 at 57487e6, a Freerouting `/Power Part/CHG_G` track sat 0.19 mm from Q2's 0.3 mm HV tab (a large custom-polygon pad); DSN polygon and pin class verified correct (0.3 mm); two local runs did not reproduce it. `_rip_errors` now removes such copper for the last mile. A Freerouting clearance fault on large polygon pads is suspected, not shown.

## Sources

- Results: [10x sweep](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md), [last mile A+B](../../../bench/results/2026-10-24-last-mile-ab-57487e6.md), [last mile C6](../../../bench/results/2026-10-24-last-mile-c6-57487e6.md), [portfolio](../../../bench/results/2026-10-24-portfolio-ab-0465818.md)
- Code: [lastmile.py](../../../kae/src/kae/route/lastmile.py), [repair.py](../../../kae/src/kae/route/repair.py), [portfolio.py](../../../kae/src/kae/route/portfolio.py), [freerouting.py](../../../kae/src/kae/route/freerouting.py); tests [test_route_lastmile.py](../../../kae/tests/test_route_lastmile.py), [test_route_repair.py](../../../kae/tests/test_route_repair.py), [test_route_kicad.py](../../../kae/tests/test_route_kicad.py)
