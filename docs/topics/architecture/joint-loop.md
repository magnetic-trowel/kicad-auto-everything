# The joint loop: routing feedback into local re-placement

Scope: design of `kae.joint`: place and route the whole board once, then repair **windows** (a few parts and the nets touching them) where routing failed, DRC complained or a module's routed physics shifted; parameters, feedback, windows, congestion penalty, rip-up, acceptance rule, budgets. Not here: measured numbers and the evidence behind each design rule -> [kae-joint-loop](../../research/joint/kae-joint-loop.md); theory -> [joint-place-route](../physics/joint-place-route.md); the month-plan precursor -> [month-plan](month-plan.md#the-joint-loop-modules-routed-physics-re-tweak).
Keys: `kae.joint`, `kae.route.incremental`, `joint_stops.py`, windows, feedback spots, `CongestionHistory`, RUDY, `cong_history`, shortfall bump, rip-up, guard pours, `route_open`, `lastmile.close`, lexicographic acceptance, per-item physics slack, finishing stage, `--route-parallel`, `freerouting._Slot`, Starfish

## Why a loop, and why windows

The placer cannot see where the router will fail; the router cannot move a part. Staged place-then-route gets stuck: placement proxies cannot see routing, and the physics exists only once copper does ([joint-place-route](../physics/joint-place-route.md)). Fully joint search pays a route per move; a full re-place would lose the copper that already works, so repair only where it failed. What scaled in VLSI is cell moves with partial reroute (Starfish); this loop is that pattern at PCB scale, judged by the benchmark's KiCad DRC. It generalizes the [month plan](month-plan.md)'s module loop, whose re-tweak cannot move parts. Worst case = the staged pipeline, because every iteration is judged by KiCad and accepted lexicographically.

## The loop

`python -m kae.joint.cli run IN OUT --time S --seed N` ([loop.py](../../../kae/src/kae/joint/loop.py), [stages.py](../../../kae/src/kae/joint/stages.py)):

| Step | What | Module |
|---|---|---|
| 0. Place | `kae.place.pipeline.place` (brief macros, seed, compiled annealer, legalize), written by `kae.place.writer` | kae.place |
| 0. Modules | `optimize_modules`: module parts and critical copper together, locked; guard pours (`kae-crit:`) per module | kae.route.critical |
| 0. Route | the bridge around all locked copper and the guards; afterwards non-critical copper unlocked, guards dropped | kae.route |
| 0. Judge | kicad-cli DRC (zones refilled) and `critical_recheck.recheck` against the module-stage values | kae.route |
| 1. Feedback | spots from unrouted items, DRC errors, flagged modules; corridors into the congestion history | [feedback.py](../../../kae/src/kae/joint/feedback.py) |
| 2. Window | spots clustered into windows; the least-tried, highest-priority one is repaired | feedback.plan_windows |
| 3. Re-place | window parts re-annealed, rest fixed, history as RUDY demand | [replace.py](../../../kae/src/kae/joint/replace.py), [penalty.py](../../../kae/src/kae/joint/penalty.py) |
| 4. Rip up | only nets touching the window; modules in the window redone | [ripup.py](../../../kae/src/kae/joint/ripup.py) |
| 5. Re-route | open connections only, everything else locked; then `lastmile.close` (`kae.route.lastmile`) on the window's nets | [incremental.py](../../../kae/src/kae/route/incremental.py) |
| 6. Judge | DRC + recheck; accept or revert | [scorecard.py](../../../kae/src/kae/joint/scorecard.py) |
| 7. Finish | full bridge (repair rounds `auto`, then the last mile) over the whole board, critical copper locked; judged the same way | stages.route(finish=True) |

**Stopping (time-driven, no iteration cap).** Steps 1–6 repeat until the board is clean with no module flagged, or the time left for windows is below what a window has been taking. Reserves set aside up front: finishing stage max(120 s, 20 %), final write max(25 s, 4 %). When every window is exhausted, a new cycle samples them again with new seeds and the history so far. End the loop after two consecutive cycles that keep nothing ("no improvement (cycle k)") or a cycle in which nothing could be routed (< 5 s).

**Stop reasons.** No stage burns the clock; each reports why it stopped: placer (planned moves done or clock); closed-loop legality (legal or round cap); Freerouting (COMPLETED, STAGNATION, NO_IMPROVEMENT or TIMED_OUT, plus the optimizer's reason); bridge repair (clean, no improvement, time); the loop's own reason. `tools/research/joint/joint_stops.py` tabulates them per arm.

**Finishing stage (step 7)** runs in its reserve: it brings the staged pipeline's completion without giving up the module copper. If connections stay open, a second finishing try releases the critical copper of the modules on their corridors, priced by the acceptance rule. The staged baseline (`--max-iters 0`) has no finishing stage.

**Scaling with budget.** Tries per window = 2 + one per 30 min; module-stage time = 5 % of the budget. Window router budget starts at 60 s, doubles after each window whose router ran out of time (cap 5 % of the budget), halves back after a fast one.

**`--route-parallel P`** (default 1 = all of the above). With P > 1 the finishing stage is [`kae.route.portfolio`](../../../kae/src/kae/route/portfolio.py): the current placement, the loop's routing removed, routed by P parallel, growing, differently seeded restarts of `critical_cli --last-mile-soft` (listed first, so its clean board is preferred) and the bridge; judged on the incumbent's modules; no release try. A window left with ≤ 8 open connections, and not stopped by its clock, gets two more seeded `route_open` runs at once, keeping the one with the fewest open.

## Feedback: from KiCad's report to parts

- **Unrouted connections.** Each `unconnected_items` entry names two items with positions. A pad's description ends in "of *ref*", naming the part whose pose decides the corridor. Corridor = segment between the two items, width = length/5 (the router's detour room), clamped to 1–4 mm.
- **DRC errors.** Each error-level violation is attributed to the parts its pads belong to and the routing items (by uuid) involved. A placement-type error (kaebench's list: courtyards, clearance, hole clearance, edge, keepouts) whose items are only pads and footprints belongs to the placement; its spot carries KiCad's shortfall (required − actual clearance). The window's re-anneal bumps those parts by shortfall + 0.15 mm, kept even when the routing bumps are dropped (a fixed 0.15 mm bump failed on olimex: [evidence](../../research/joint/kae-joint-loop.md#results)).
- **Physics shifts.** The recheck flags a module whose routed utilization rose > 15 % over its module-stage value, crossed 1, or lost > 0.10 of plane cover; its spot sits at its parts.

Spot weights (match the acceptance order): placement 4, unrouted 3, other errors 2, physics 1 + rise + cover loss.

**Windows.**
- Content: the spot's own unlocked parts + unlocked parts whose centres lie within a 2 mm margin of the region they and the spot's points span, nearest first; ≤ 8 parts and ≤ 35 % of the board's movable parts (≥ 3). (Cap reason: a 12-part window on a 15-part board was a global re-place, [evidence](../../research/joint/kae-joint-loop.md#results).)
- Never move: locked parts, parts carrying Edge.Cuts, staged parts. On a first attempt parts with > 12 connected pads stay fixed too, unless nothing smaller can move (moving an MCU rips up every net it has).
- Overlapping windows merge while the union stays within the part cap.
- **Re-route window:** a spot with no movable part within reach: no part moves; nets touching the region are ripped up and the bridge routes them in a new order. Its retry is a normal, larger window.
- **Retries:** a rejected window is retried up to its try count, larger (margin ×1.5, at most twice), congestion weight ×1.5, physics weight ×2. An accepted window resets every count (the board changed). On odd retries the window's modules are not redone: their nets go to the bridge, since their locked copper and guard pours may be what blocks the corridor.

## Congestion penalty

- `CongestionHistory` = PathFinder's history cost on a 1 mm grid: every routed evaluation, accepted or not, adds 1 (unit: a bin's routing supply) along each failed connection's corridor, so a failed region stays expensive after one re-placement. Rejected candidates' failures still enter it.
- RUDY marks how crowded the failed region is: the placer's RUDY map of the routed placement adds 0.5·max(0, u − 0.5) to history bins within 3 mm of a failure. RUDY alone never opens a window: on PCBs it ranks routability near chance.
- Placer congestion model (`kae.place.cost.Congestion`): RUDY + pin-escape demand priced as Σ max(0, u − 0.5)². The history, resampled to the annealer's bins and limited to the window plus two bins, enters through the `cong_history` hook (`make_annealer`, `local_replace`) as static demand:

  `u_b = (D_nets + D_escape + h_b·S_b) / S_b`

  The extra demand never moves with a part, so both engines (reference `Annealer`, compiled `FastAnnealer`) stay exactly incremental.
- In a window: congestion weight doubled (30 → 60); parts named by an unrouted connection bumped 0.25 mm (`Problem.bump`, more occupancy on every side); routing margin 0.3 mm. Both bumps dropped if they make the window illegal.
- The re-anneal also carries the placer's physics terms and protection-order rules; nets of the window's unrouted connections weigh 2× (`local_replace(net_weights=…)`).
- Legality stays hard and closes with the placer's own loop: KiCad placement errors → exact constraints (`exact.kicad_feedback`) → grid legality → greedy legalizer → exact check repaired by `exact.repair(allowed=window parts)`. The rip-up region grows to cover wherever that repair moved a part. An illegal window is discarded before any routing.
- Annealer runs a fixed move count (6,000 per part), so a window is reproducible whenever its time budget does not bind.

## Rip-up: only what the move invalidates

| Copper | Ripped |
|---|---|
| Unlocked, net on a moved part, small net | the whole net (a fragment left behind is fixed wiring Freerouting will not join in its middle) |
| Unlocked, net on a moved part, poured or ≥ 20 pads | items inside the window or touching the moved parts' old pads; the rest stays joined through the pour |
| Unlocked, other nets inside the window | those items; the 4 shortest such nets whole |
| Critical, owned by a module with a moved part or with copper in the window | all of that module's copper; the module stage runs again for it |
| Critical, no module (rails, joins) | inside the window or at a moved pad |

Sequence after rip-up:
1. Window modules re-optimized with `optimize_modules(modules=…)`, every part outside the window locked; their guard pours recomputed, other modules' guards stay.
2. Every remaining item locked; guards in place.
3. Re-route by **`kae.route.incremental.route_open`**: the bridge's constraint translation, but cheap: only open connections; up to 3 autorouter passes in one run (the fork's `autorouter.max_passes`), > 1 only while connections are open; optimizer off (`optimizer.enabled=false`); item order from the seed (`autorouter.item_order_seed`); no repair rounds; the loop's evaluation is the single DRC.
4. Everything except critical copper unlocked; `lastmile.close` joins what is still split on the window's nets (grid router with negotiated rip-up of unlocked tracks, critical copper fixed).

Because `route_open`'s cost grows with open connections (Freerouting ≈ 1–2 CPU s per open connection, [evidence](../../research/joint/kae-joint-loop.md#results)), the window's rip-up is local: every net loses only the items inside the window and at the moved pads; none is ripped whole. `--set window_router=bridge` restores the full bridge for windows. The first route skips the bridge's last mile (on by default since c9c49d6) when a finishing stage follows, because there it only took the windows' time; the staged baseline keeps it.

## Acceptance

| Order | Criterion | Rule |
|---|---|---|
| 1 | legality: KiCad placement-type errors whose items are only pads and footprints | must not rise |
| 2 | completion and DRC: unconnected + errors, then unconnected | neither may rise; a board that becomes clean is kept; another strict gain is kept if physics rises ≤ 10 % per item gained |
| 3 | routed physics: Σ_modules min(u, 5), a module without a value counted as 3 | with equal completion and DRC, must fall by > 0.5 % |

Otherwise the candidate is reverted (dropped). The clean rule and per-item slack are the user's decision (confirmed after the first A/B) and the default; a flat 10 % slack reverted a board-cleaning window on ch552g ([evidence](../../research/joint/kae-joint-loop.md#results)).

## Determinism and budgets

- Stage seeds derive from the run's seed and the iteration (`derive_seed`); windows ordered by priority then position; Freerouting is deterministic for an item order; window anneal uses a fixed move count. So a seed repeats whenever no time budget binds; on a loaded host the clocks can bind.
- Budget = wall seconds: 30 % placer, 60 % of the rest for the first route, then windows, the finishing reserve and the write reserve.
- A Freerouting slot wait (`freerouting._Slot`) is subtracted from the budget; after the budget the router runs without a slot (`slot_gave_up`). Reason: outside the kaebench sandbox, where slot locks are shared with other jobs, a finishing bridge once ran past its budget waiting for one.

## Measured

→ [kae-joint-loop#results](../../research/joint/kae-joint-loop.md#results) (A+B 4814e11, split C a28bd84, last-mile local, `--route-parallel 2`).

## Open questions

- PMW3610 boards have no room to move into (5–8-part windows cannot spread the cluster), split C clock-bound, portfolio finish routing from scratch, clean boards with a flagged module running to the clock, placement errors left by the placer: → [kae-joint-loop#open-questions](../../research/joint/kae-joint-loop.md#open-questions).

Related: [critical-net-routing](../routing/critical-net-routing.md), [freerouting-constraint-bridge](../routing/freerouting-constraint-bridge.md), [pathfinder-negotiated-congestion](../routing/pathfinder-negotiated-congestion.md).
