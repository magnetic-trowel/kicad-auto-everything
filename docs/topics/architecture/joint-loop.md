# The joint loop: routing feedback into local re-placement

**TL;DR**
- Placement and routing depend on each other: the placer cannot see where the router will fail, and the router cannot move a part. `kae.joint` closes the loop at the granularity that scales on PCBs: place and route the whole board once, then repair **windows** (a few parts and the nets touching them) where routing failed, DRC complained or a module's routed physics shifted.
- One iteration = re-anneal the window's parts with everything else fixed (the placer's `subset`/`window` API) under a congestion penalty built from where routing failed, rip up only the nets touching the window, redo the window's modules (critical copper), re-route with everything else locked, judge with KiCad DRC and the routed-physics recheck.
- An iteration is kept only if it is lexicographically better: legality, then completion and DRC, then routed physics. Legality, unconnected items and DRC errors may never get worse. A board that becomes clean is always kept. Any other completion gain may cost at most 10 % of routed physics per item gained, and with equal completion physics must improve. Otherwise it is reverted, so the output is never worse than the staged pipeline.
- Windows are re-routed by `kae.route.incremental` (only the open connections, no optimizer), then the grid last mile (`kae.route.lastmile`) on the window's nets. A window's routing fell from a median 107–124 s (the full bridge) to 10–12 s. On 6 split-B boards (kaebench `joint`, score v7, k = 2, 900 s) the loop has 4 / 5 clean boards and module values 0.75 / 0.88× the human's; the staged pipeline with the bridge's last mile has 5 / 5 at 1.24 / 1.33×. One board (PMW3610) holds the completion gap [C].

## Key facts

### Why a loop, and why windows

Staged place-then-route gets stuck because placement proxies cannot see routing, the router cannot move parts, and the physics exists only once copper does ([joint-place-route](../physics/joint-place-route.md)). Fully joint search pays a route per move. What scaled in VLSI is cell moves with partial reroute (Starfish), and this loop is that pattern at PCB scale, judged by the benchmark's KiCad DRC. It generalizes the [month plan](month-plan.md)'s module loop, whose re-tweak cannot move parts.

### The loop

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
| 5. Re-route | open connections only, everything else locked; then `lastmile.close` on the window's nets | [incremental.py](../../../kae/src/kae/route/incremental.py) |
| 6. Judge | DRC + recheck; accept or revert | [scorecard.py](../../../kae/src/kae/joint/scorecard.py) |
| 7. Finish | the full bridge (repair rounds `auto`, then the last mile) over the whole board, critical copper locked; judged the same way | stages.route(finish=True) |

The loop is time-driven, with no iteration cap. Steps 1–6 repeat until the board is clean with no module flagged, or until the time left for windows is below what a window has been taking. That time excludes two reserves set aside up front: the finishing stage's, max(120 s, 20 %), and the final write's, max(25 s, 4 %). When every window is exhausted, a new cycle samples them again with new seeds and the history so far. Two cycles in a row that keep nothing end the loop ("no improvement (cycle k)"), as does a cycle in which nothing could be routed (< 5 s). No stage burns the clock: each reports why it stopped (placer: planned moves done or clock; closed-loop legality: legal or round cap; Freerouting: COMPLETED, STAGNATION, NO_IMPROVEMENT or TIMED_OUT, plus the optimizer's reason; bridge repair: clean, no improvement, time; the loop's own reason). `tools/research/joint/joint_stops.py` tabulates them per arm. Step 7 then runs in its reserve. It is where the staged pipeline gets its completion (many Freerouting passes, the bridge's repair rounds), and the loop gets it without giving up its module copper. If connections stay open, a second finishing try releases the critical copper of the modules on their corridors, priced by the acceptance rule. The staged baseline (`--max-iters 0`) has no finishing stage. Longer budgets also allow more tries per window (2 + one per 30 min) and more module-stage time (5 % of the budget).

### Feedback: from KiCad's report to parts

- **Unrouted connections.** Each `unconnected_items` entry names two items with positions. A pad's description ends in "of *ref*", which names the part whose pose decides the corridor. The corridor is the segment between the two items, as wide as a fifth of its length (the router's detour room), clamped to 1–4 mm.
- **DRC errors.** Each error-level violation (library-environment checks excluded, as kaebench) is attributed to the parts its pads belong to and to the routing items (by uuid) involved. A placement-type error (kaebench's list: courtyards, clearance, hole clearance, edge, keepouts) whose items are only pads and footprints belongs to the placement. Its spot carries KiCad's shortfall (required minus actual clearance). The window's re-anneal bumps those parts by the shortfall plus 0.15 mm, and the bump is kept even when the routing bumps are dropped. The placer's model judged them legal, so this is a constraint it missed. On olimex the placer left 7 hole-clearance errors of 0.19–0.63 mm (pads against mounting-hole NPTHs, 1.85 mm required), and a fixed 0.15 mm bump did not clear them.
- **Physics shifts.** The recheck flags a module whose routed utilization rose more than 15 % over its module-stage value, crossed 1, or lost more than 0.10 of plane cover. Its spot sits at its parts.

Spot weights are 4 (placement), 3 (unrouted), 2 (other errors) and 1 + rise + cover loss (physics), so legality is repaired first, then completion, which matches the acceptance order.

**Windows.** A spot's window holds its own unlocked parts plus the unlocked parts whose centres lie within a 2 mm margin of the region they and the spot's points span, nearest first, at most 8 and at most 35 % of the board's movable parts (at least 3). On a 15-part board a 12-part window was a global re-place (17 → 28 unconnected). Locked parts, parts that carry Edge.Cuts and staged parts never move. On a first attempt, parts with more than 12 connected pads stay fixed too, unless nothing smaller can move: moving an MCU rips up every net it has. The rectangle covers every movable part's current courtyard box, so the annealer starts inside it. Overlapping windows merge while the union stays within the part cap. A spot with no movable part within reach gets a **re-route window**: no part moves, the nets touching the region are ripped up and the bridge routes them again in a new order. Its retry is a normal, larger window. A rejected window is retried up to its try count, larger (margin ×1.5, at most twice) and with the congestion weight ×1.5 and the physics weight ×2. An accepted window resets every count, since the board changed. On odd retries the window's modules are not redone: their nets go to the bridge, since their locked copper and guard pours may be what blocks the corridor.

### Congestion penalty

`CongestionHistory` is PathFinder's history cost on a 1 mm grid: every routed evaluation, accepted or not, adds 1 (in units of a bin's routing supply) along each failed connection's corridor. A region where routing failed stays expensive after one re-placement. RUDY marks how crowded the failed region is: the placer's own RUDY map of the routed placement adds 0.5·max(0, u − 0.5) to history bins within 3 mm of a failure. RUDY alone never opens a window: on PCBs it ranks routability near chance. Applying it uses the placer's own congestion model, `kae.place.cost.Congestion`, a RUDY map with pin-escape demand priced as Σ max(0, u − 0.5)² over bins. The history, resampled to the annealer's bins and limited to the window plus two bins, enters through the placer's `cong_history` hook (`make_annealer`, `local_replace`). It is added to the static demand array:

u_b = (D_nets + D_escape + h_b·S_b) / S_b.

The extra demand never moves with a part, so both engines (the reference `Annealer` and the compiled `FastAnnealer`) stay exactly incremental. Moves that keep a window's nets and pins out of failed bins become cheaper, as a history cost makes a congested node dearer for every net in PathFinder. In a window the congestion weight is doubled (30 → 60). Parts named by an unrouted connection are bumped 0.25 mm (`Problem.bump`, more occupancy on every side) and the routing margin is 0.3 mm. Both are dropped if they are what makes the window illegal.

The re-anneal also carries the placer's physics terms (`kae.physics.place_terms`, calibrated against routed copper) and protection-order rules, and nets of the window's unrouted connections weigh 2× (the hook `local_replace(net_weights=…)` offers). Legality stays hard and closes with the placer's own loop. KiCad's placement errors on the current board become exact constraints (`exact.kicad_feedback`). Then come grid legality and the greedy legalizer if needed, then the exact check, repaired by `exact.repair(allowed=window parts)` as `local_replace` ends. The rip-up region grows to cover wherever that repair moved a part. An illegal window is discarded before any routing. The annealer runs a fixed move count (6,000 per part), so a window is reproducible whenever its time budget does not bind.

### Rip-up: only what the move invalidates

| Copper | Ripped |
|---|---|
| Unlocked, net on a moved part, small net | the whole net. A fragment left behind is fixed wiring Freerouting will not join in its middle |
| Unlocked, net on a moved part, poured or ≥ 20 pads | items inside the window or touching the moved parts' old pads; the rest stays joined through the pour |
| Unlocked, other nets inside the window | those items; the 4 shortest such nets whole |
| Critical, owned by a module with a moved part or with copper in the window | all of that module's copper; the module stage runs again for it |
| Critical, no module (rails, joins) | inside the window or at a moved pad |

The window's modules are re-optimized with `optimize_modules(modules=…)`, with every part outside the window locked. Their guard pours are recomputed, and the other modules' guards stay. Every remaining item is then locked (fixed wiring for Freerouting) and the guards go in place. The window is re-routed by **`kae.route.incremental.route_open`**. It uses the bridge's constraint translation (`constraints.plan`, `translate.apply`, its router settings), but the run is made cheap:
- only the open connections are routed;
- up to 3 autorouter passes in one run (the fork's `autorouter.max_passes`), more than one only while connections are open, with the optimizer off (`optimizer.enabled=false`). A pass that routes nothing new costs ~0.3 s, less than a second JVM start;
- the item order comes from the seed (`autorouter.item_order_seed`);
- there are no repair rounds, and the loop's evaluation is the single DRC.

Because the cost grows with the open connections, the window's rip-up is local: every net loses only the items inside the window and at the moved pads, and none is ripped whole. Afterwards everything except the critical copper is unlocked again, and `lastmile.close` joins what is still split on the window's nets (grid router with negotiated rip-up of unlocked tracks, critical copper fixed; 16–24 s on PMW3610). `--set window_router=bridge` restores the full bridge for windows. The first route skips the bridge's last mile (on by default since c9c49d6) when a finishing stage follows: there it only took the windows' time (PMW3610: iteration 0 234 s without, 381–518 s with). The staged baseline keeps it.

### Acceptance

| Order | Criterion | Rule |
|---|---|---|
| 1 | legality: KiCad placement-type errors whose items are only pads and footprints | must not rise |
| 2 | completion and DRC: unconnected + errors, then unconnected | neither may rise; a board that becomes clean is kept; another strict gain is kept if physics rises by at most 10 % per item gained |
| 3 | routed physics: Σ_modules min(u, 5), a module without a value counted as 3 | with equal completion and DRC, must fall by more than 0.5 % |

The clean rule and the per-item slack are the user's decision (confirmed after the first A/B), and they are the default. On ch552g a window made the board clean (1 unconnected → 0) while its decoupling loops, now routed by the bridge, raised Σu from 1.17 to 2.88. A 10 % flat slack reverted it.

A rejected candidate is dropped, and the incumbent board, its bookkeeping and its feedback stay. Its failures still enter the congestion history.

### Determinism and budgets

Stage seeds derive from the run's seed and the iteration (`derive_seed`), windows are ordered by priority then position, Freerouting is deterministic for an item order, and the window anneal uses a fixed move count. So a seed repeats whenever no time budget binds; on a loaded host the clocks can bind. The budget is wall seconds: 30 % for the placer, 60 % of the rest for the first route, then windows, the finishing reserve and the write reserve.

### Measured

kaebench `joint` (score v7), KiCad 10.0.7, 6 split-B boards (olimex DC-DC, noisecard, PMW3610, XIAO base, bipolar supply, CH552G), seeds 0 and 1, 900 s, `-j 1`, shared 4-core host, 3 GB Freerouting heap (no OOM-hit attempt). Σu and module values come from `critical_recheck.board_physics` on the scored board (brief from the human placement); they are unreliable where hops are open [C: `tools/research/joint/joint_physics.py`, `joint_stops.py`]. "Last mile" for staged is the bridge's default since c9c49d6; for the joint loop, windows and the finishing stage.

| Arm (seed 0 / seed 1) | clean | unconnected | DRC errors | module value / human (median) | worst rail mΩ (median) | Σu | time s |
|---|---|---|---|---|---|---|---|
| human placement + Freerouting | 2 / 2 | 23 / 23 | 7 / 7 | 1.00 | 101 | 3.16 | 24 |
| staged, no last mile | 3 / 4 | 3 / 3 | 0 / 0 | 1.18 / 1.39 | 108 / 87 | 4.23 / 4.46 | 160 / 112 |
| staged, last mile | 5 / 5 | 4 / 5 | 0 / 0 | 1.24 / 1.33 | 104 / 103 | 5.45 / 4.59 | 199 / 178 |
| joint loop, no last mile | 3 / 3 | 11 / 8 | 0 / 0 | 0.81 / 0.96 | 43 / 58 | 2.56 / 3.38 | 394 / 331 |
| joint loop, last mile | 4 / 5 | 9 / 6 | 0 / 0 | 0.75 / 0.88 | 47 / 68 | 2.10 / 3.61 | 342 / 349 |

kaebench cp1 / cpk: joint 0.667 / 0.833, staged with last mile 0.833 / 0.833. A whole window takes ~40 s with its last mile.

What the numbers say:
- **Physics holds.** The loop's boards have module values 0.75–0.88× the human's and half the rail resistance of either staged arm.
- **Completion is one board.** Off PMW3610 the loop is clean on 9 of 10 attempts (noisecard seed 0 keeps 2). PMW3610 keeps 7 / 6 open where staged keeps 4 / 5, at Σu 22.3 / 17.0 against the loop's 5.5 / 14.5. There the finishing bridge's last mile joined 5–7 nets but ripped 19–22 items, ending 8–9 unconnected (not better), and window last miles joined 9–12 and failed 5–6, ending one or two worse than the incumbent.
- **Stops.** Loop: clean 8, time 4 of 12. Window Freerouting: COMPLETED 25 of 29. Finishing bridge: STAGNATION 4, TIMED_OUT 2. Runs used 38 % of their budget (up to 91 %).
## Recommendations for our system

1. **Judge every iteration by KiCad, accept lexicographically.** The loop can then only help: its worst case is the staged pipeline.
2. **Repair where it failed, not everywhere.** A window re-routes only its open connections, everything else locked. A full re-place would lose the copper that already works.
3. **Keep the history.** Failures accumulate as congestion cost. A window that failed once keeps steering the placer away even when the next routing succeeds by luck elsewhere.

## Conflicts and open questions

- **PMW3610 has no room to move into.** The board is 15 × 30 mm, 2 layers, no pours. The locked sensor U1 (PTH, 16 pins) fills the lower half, and every small part sits in y ≈ 82–95 mm. The open connections run from that cluster to U1's pad columns (x = 144.7 and 155.3). Windows do pick the parts that wall them off (C10, C7, C5, C2, R1 at y ≈ 91–92), and they are the most-tried windows, but the band between the cluster and U1 is full. A window that frees one corridor closes another (7 → 8–12 unconnected). Closing it needs a re-place that spreads the cluster upward, more than a window's 5–8 parts.
- **Freerouting's cost per open connection** is 1–2 CPU s (noisecard: 28 open, 17–19 CPU s, ~15 GB allocated; heap and GC settings change nothing). So a window stays cheap only while its rip-up stays local.

See also: [month-plan](month-plan.md) · [joint-place-route](../physics/joint-place-route.md) · [critical-net-routing](../routing/critical-net-routing.md) · [freerouting-constraint-bridge](../routing/freerouting-constraint-bridge.md) · [pathfinder-negotiated-congestion](../routing/pathfinder-negotiated-congestion.md)
