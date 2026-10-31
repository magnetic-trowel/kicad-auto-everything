# Last mile and restarts: closing what the router leaves open

**TL;DR**
- More time does not close the last connections. At 10× budgets on splits A+B the bridge stopped on its own (COMPLETED or STAGNATION) on every attempt, and clean attempts stayed at 70/99, as at 1× ([10x sweep](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md)).
- What does close them: a **last mile** after the repair rounds, and **restarts**. The last mile joins each open net with the critical router's exactly checked grid search and rips up only what it must. Restarts run short, differently seeded attempts in parallel and keep the first clean one.
- Last mile, A+B k=3: bridge cp1 0.727 → 0.909, cpk 0.818 → 0.970, 0 errors, no physics cost ([A+B](../../../bench/results/2026-10-24-last-mile-ab-57487e6.md)). Split C: cpk 0.50 → 0.833 ([C6](../../../bench/results/2026-10-24-last-mile-c6-57487e6.md)). It is on by default (`--[no-]last-mile`).
- Restart portfolio (`kae.route.portfolio`), A+B k=3: 99/99 clean attempts, against 91/99 for one attempt, with a 224 s worst case against 1,626 s. Split C: 12/12 ([portfolio](../../../bench/results/2026-10-24-portfolio-ab-0465818.md)).
- Two router families fail on different boards: the bridge alone versus critical copper with the soft last mile. A mixed portfolio gets the union.

## Key facts

### Why budgets do not help
- **Freerouting stops by itself.** It ends on COMPLETED or STAGNATION, and its own last-mile rip-up has already run. Its log reports which (`router.report.autorouter_stop` / `optimizer_stop`, [freerouting.py](../../../kae/src/kae/route/freerouting.py)).
- **What is left is of two kinds:**
  - signal connections Freerouting found no legal path for, although one exists (paw3395 MOSI);
  - plane-net copper that only KiCad sees as cut off: a pad outside its fill, or a fill island of a split pour. Freerouting treats a plane as one conduction area, so it reports 0 incomplete connections on such boards.
- **A fork patch was tried and rejected.** Running Freerouting's last-mile rip-up also when the pass loop ends COMPLETED with open connections never triggered on the target boards and closed nothing [C]. It is kept unpushed on fork branch `fix/last-mile-on-completed`.
- **Repair rounds stop on improvement, not the clock.** `rounds="auto"` lifts the cap of 5. A loop that ends on the cap records `stopped: "round cap"`. On bms-c1 the "free" rounds were still gaining (29 → 15 open) when the cap hit.
- **`router_share="auto"` and `repair_reserve_s`** give the first route all but 600 s of a long budget. They are opt-in until a suite run confirms them ([bridge.py](../../../kae/src/kae/route/bridge.py)).

### Last mile ([lastmile.py](../../../kae/src/kae/route/lastmile.py), driven by `repair._last_mile`)
1. **Parts as KiCad sees them.** The routed board is reloaded and every zone refilled with the project's rules. Each open net is split into connected parts:
   - pads, vias and fills join what they overlap on a shared layer;
   - a track joins only where one of its ends lies on other copper.
   A part counts when it holds a pad, or a fill that a track or via of the net reaches. Track-only parts are tails.
2. **Joins.** Each smaller part is joined to the rest with `GridRouter.connect` (0.05 mm grid, exact checks against `kae.route.effective`). The search windows grow: around the part and the nearest other part (1, 3, 8 mm), then 15 mm in every direction.
3. **Rip-up.** If the joins find nothing, the window's unlocked tracks and vias of other nets are taken out and priced per cell crossed (`RIP_COST` 20 per cell: crossing a 0.25 mm track at 0.2 mm clearance costs as much as an 18 mm detour). Only the items the new copper actually violates are ripped, at most 40 per join.
4. **Negotiated re-route.** A ripped net goes back on the queue and is joined by the same search. Each time a net is ripped its copper gets dearer to rip again (`HIST_WEIGHT`). After 3 rip-ups (`HIST_MAX`) it is left alone. `MAX_JOINS` bounds a pass at 40 joins. What stays open goes to a nested repair loop, which routes it with the new copper fixed.
5. **Via in pad.** A pad walled in by its own footprint (a microphone's centre pad inside its ring) is left through a via in the pad. The human board does the same.
6. **Acceptance.** A round replaces the output only when KiCad's DRC on the re-opened board is better and has no more errors. The next round works on the previous round's board, so a join can open the net it ripped and the next round closes it.

Bugs that hid the last mile's effect, all fixed by 2ec702e:

| Bug | Effect | Fix |
|---|---|---|
| Open cap of 8 | skipped bms-c1 (15/11 open); offline the last mile alone took 27 → 0 in 25 s [C] | `LAST_MILE_MAX = 40`; a pour net in many pieces is re-queued |
| Escaped net names | KiCad's DRC report shows `A/B` for the board's `A{slash}B`, so nothing matched (noisecard after critical copper) | `lastmile.unescape` maps report names back |
| Rounds that trade an open for an error | the repair key summed errors and opens, so olimex kept a round with a starved thermal. The last mile then never ran, since it needs 0 errors | a round is kept only if its errors do not rise |
| Two route vias closer than the same-net pitch | hole-to-hole errors | the route is searched again with dearer vias, or refused |

### Errors the router keeps making
Before the last mile, `repair._rip_errors` takes out the unlocked router copper that each remaining error names: clearance, short, mask bridge, track width, edge and similar types. A starved thermal names a pad and a zone, not the copper causing it, so there the foreign unlocked copper in the pad's spoke corridors (`constraints.thermal_corridors`) is taken out instead. When the result has 0 errors, the last mile routes it with exact checks. Pre-routes and critical copper are never taken out here.

### What stays open: the `blocked` report ([blocked.py](../../../kae/src/kae/route/blocked.py))
The router never relaxes a board rule. After the last mile, each connection still open is tested in lastmile's grid and Space: a path without our other copper is `congestion`; one without the input's pre-routes too is `fixed copper`. Otherwise a relaxed search (only overlap hard, every clearance a price per cell) finds the cheapest path, and its narrowest real gap names the binding rule. A finer search then tries narrower tracks, so a track-width minimum is told apart from a clearance. The report gives the rule's source, or the kae default and its override, and leaves the decision to the caller ([kae README](../../../kae/README.md#kaeroute)).

Checked on the merge2 final boards [C]:
- bcecoop rmlv1616a: all 4 blocked by SRAM1's solder-mask openings (margin 0.1 + mask-to-copper 0.1).
- fona-800: 2 by the 0.2 mm board-minimum track width, 2 by kae's thermal corridors at U1.12, 1 by a no-net copper graphic over U1.77.
- atlantis can485: A4's U1.57 lies under the no-net pad U1.66.
- smol-esp32: 37 of 56 by the 0.2 mm minimum width at the 0.4 mm-pitch U2 (0.127-0.16 mm would pass).
- fm4dd, siderakb and noggin are all congestion.

### Soft critical tier (`--last-mile-soft`, crit only)
`critical.soft_critical` passes the critical copper uuids and a physics guard to the bridge:
- **Last resort.** When only critical copper blocks a join, a last tier may rip it, at 3× the price (`SOFT_FACTOR`). The ripped critical net is then re-joined by the grid search.
- **Guard.** The result is kept by the joint loop's rule (`kae.joint.scorecard.accept`): completion and errors never worse, routed physics (`critical_recheck.board_physics`) at most 10 % worse per connection gained. A board that becomes clean is always kept.
- **Retry.** If the guard rejects, the next round runs without the soft tier.

Locally, on six A+B boards the soft tier made paw3222 clean with better physics (1.857 → 1.699). It did not help the pmw3610 boards [C]. At 2ec702e, critical + soft was the first arm to route libresolar-bms-c1 clean ([C6](../../../bench/results/2026-10-24-last-mile-c6-57487e6.md)).

### Restart portfolio ([portfolio.py](../../../kae/src/kae/route/portfolio.py))
`python -m kae.route.portfolio route IN OUT --parallel P --first-s F [--router M[:ARGS]]...`
- **Waves.** Attempts run in waves of `parallel` seeds. The wave budget starts at `first_s` and doubles, so a board that needs a long attempt still gets one. The first clean attempt (0 errors, 0 open) stops the rest; otherwise the best (errors, unconnected) is kept.
- **Why it works.** Routing time is heavy-tailed, and the winners come from deep in the seed sequence (paw3395 won with its 9th and 10th seeds). Item-order diversity closes the last connections, not attempt length. canhw-processor's "clock-bound" first route was a bad order: other seeds route it clean in 128–190 s.
- **Mixed routers.** Attempts cycle through the listed routers. Among equal results the first-listed router wins, and its running attempts finish before a later router's clean result ends the run. List the physics-first router first; otherwise the faster bridge wins every board and the physics edge is lost.
- **Cost.** Up to `parallel` cores and JVMs per board.

### Hosts: memory and slots
- **Heap.** A Freerouting JVM grows toward its heap cap (`KAE_FR_XMX`, default 6g) whether or not the board needs it: about 6.5 GB on canhw.
- **OOM kills.** Several JVMs on a 16 GB host get OOM-killed (`rc=-9`). That silently turns results into quick-pass or failed-repair boards; check `rc` in every report.
- **Slots.** `freerouting.route` takes one of N host-wide flock slots before starting (`KAE_FR_SLOTS`, else 60 % of memory over heap + 0.5 GB). The wait is subtracted from Freerouting's own deadline, and a warning is logged past 10 % of the budget. After the whole budget it runs without a slot (`slot_gave_up`) rather than hang.
- **Sandboxes.** kaebench gives each attempt a private /tmp, so there `-j` and the heap cap govern memory.

## Recommendations for our system
- **Last mile on.** Keep it on, with the no-new-error rule. Route through the portfolio when cores allow. On small hosts use `KAE_FR_XMX=3g` and at most two JVMs.
- **Mixed portfolio for physics.** List `kae.route.critical_cli … --last-mile-soft` first and `kae.route.cli` second: the union of what each closes, with the critical router's physics.
- **Don't tune budgets.** Spend effort on diversity (seeds, routers) and exact local repair.

## Conflicts and open questions
- **pmw3610 boards.** On siderakb-pmw3610 and badjeff-pmw3610 every last-mile join forces rip-ups that neither Freerouting nor the negotiated re-route can absorb (1–5 open with critical copper). The portfolio closes siderakb sometimes.
- **The guard's clean exemption.** It follows the joint loop: a board that becomes clean is kept whatever its physics. Whether critical copper re-laid that way costs physics on the suite is unmeasured.
- **Unreproduced HV clearance.** In one critical attempt on libresolar-bms-c1 at 57487e6, a Freerouting `/Power Part/CHG_G` track sat 0.19 mm from Q2's 0.3 mm HV tab, which is a large custom-polygon pad. The DSN polygon and pin class were verified correct (0.3 mm). Two local runs did not reproduce it. `_rip_errors` now removes such copper for the last mile. A Freerouting clearance fault on large polygon pads is suspected, not shown.
- **Repair round cap.** Make `rounds="auto"` the default if the suite run confirms it.

## Sources
- results: [10x sweep](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md), [last mile A+B](../../../bench/results/2026-10-24-last-mile-ab-57487e6.md), [last mile C6](../../../bench/results/2026-10-24-last-mile-c6-57487e6.md), [portfolio](../../../bench/results/2026-10-24-portfolio-ab-0465818.md)
- code: [lastmile.py](../../../kae/src/kae/route/lastmile.py), [repair.py](../../../kae/src/kae/route/repair.py), [portfolio.py](../../../kae/src/kae/route/portfolio.py), [freerouting.py](../../../kae/src/kae/route/freerouting.py); tests [test_route_lastmile.py](../../../kae/tests/test_route_lastmile.py), [test_route_repair.py](../../../kae/tests/test_route_repair.py), [test_route_kicad.py](../../../kae/tests/test_route_kicad.py)

See also: [freerouting-constraint-bridge](freerouting-constraint-bridge.md), [critical-net-routing](critical-net-routing.md), [pathfinder-negotiated-congestion](pathfinder-negotiated-congestion.md)
