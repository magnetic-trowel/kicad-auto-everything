# The joint loop: routing feedback into local re-placement

**TL;DR**
- Placement and routing depend on each other: the placer cannot see where the router will fail, and the router cannot move a part. `kae.joint` closes the loop at the granularity that scales on PCBs: place and route the whole board once, then repair **windows** (a few parts and the nets touching them) where routing failed, DRC complained or a module's routed physics shifted.
- One iteration = re-anneal the window's parts with everything else fixed (the placer's `subset`/`window` API) under a congestion penalty built from where routing failed, rip up only the nets touching the window, redo the window's modules (critical copper), re-route with everything else locked, judge with KiCad DRC and the routed-physics recheck.
- An iteration is kept only if it is lexicographically better: legality, then completion and DRC, then routed physics. Legality, unconnected items and DRC errors may never get worse. A board that becomes clean is always kept. Any other completion gain may cost at most 10 % of routed physics per item gained, and with equal completion physics must improve. Otherwise it is reverted, so the output is never worse than the staged pipeline.
- Windows are re-routed by `kae.route.incremental`: only the open connections, one Freerouting pass, no optimizer. That cut a window's routing from a median 107–124 s (the full bridge) to 7 s, and a whole window to ~19 s. On 6 split-B boards (kaebench `joint`, k = 2, 900 s), the loop cuts unconnected + errors 38 → 23 within its runs. But the staged pipeline without the module stage still finishes more boards' connections (3–5 unconnected against 10–13), and all kae arms have 3–4 clean boards of 6 [C].

## Key facts

### Why a loop, and why windows

Staged place-then-route gets stuck because placement proxies cannot see routing, the router cannot move parts, and the physics exists only once copper does ([joint-place-route](../physics/joint-place-route.md)). Fully joint search pays a route per move. What scaled in VLSI is cell moves with partial reroute (Starfish), and this loop is that pattern at PCB scale, judged by the benchmark's KiCad DRC. It generalizes the month plan's module loop ([month-plan](month-plan.md)): the critical router's re-tweak cannot move parts, and its rounds never paid.

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
| 5. Re-route | open connections only, everything else locked | [incremental.py](../../../kae/src/kae/route/incremental.py) |
| 6. Judge | DRC + recheck; accept or revert | [scorecard.py](../../../kae/src/kae/joint/scorecard.py) |
| 7. Finish | the full bridge (repair rounds) over the whole board, critical copper locked; judged the same way | stages.route(finish=True) |

The loop is time-driven, with no iteration cap. Steps 1–6 repeat until the board is clean with no module flagged, or until the time left for windows is below what a window has been taking. That time excludes two reserves set aside up front: the finishing stage's, max(120 s, 20 %), and the final write's, max(25 s, 4 %). When every window is exhausted, a new cycle samples them again with new seeds and the history so far. A cycle in which nothing could be routed (< 5 s) ends the loop. Step 7 then runs in its reserve. It is where the staged pipeline gets its completion (many Freerouting passes, the bridge's repair rounds), and the loop gets it without giving up its module copper. If connections stay open, a second finishing try releases the critical copper of the modules on their corridors, priced by the acceptance rule. The staged baseline (`--max-iters 0`) has no finishing stage. Longer budgets also allow more tries per window (2 + one per 30 min) and more module-stage time (5 % of the budget).

### Feedback: from KiCad's report to parts

- **Unrouted connections.** Each `unconnected_items` entry names two items with positions. A pad's description ends in "of *ref*", which names the part whose pose decides the corridor. The corridor is the segment between the two items, as wide as a fifth of its length (the router's detour room), clamped to 1–4 mm.
- **DRC errors.** Each error-level violation (library-environment checks excluded, as kaebench) is attributed to the parts its pads belong to and to the routing items (by uuid) involved. A placement-type error (kaebench's list: courtyards, clearance, hole clearance, edge, keepouts) whose items are only pads and footprints belongs to the placement. Its spot carries KiCad's shortfall (required minus actual clearance). The window's re-anneal bumps those parts by the shortfall plus 0.15 mm, and the bump is kept even when the routing bumps are dropped. The placer's model judged them legal, so this is a constraint it missed. On olimex the placer left 7 hole-clearance errors of 0.19–0.63 mm (pads against mounting-hole NPTHs, 1.85 mm required), and a fixed 0.15 mm bump did not clear them.
- **Physics shifts.** The recheck flags a module whose routed utilization rose more than 15 % over its module-stage value, crossed 1, or lost more than 0.10 of plane cover. Its spot sits at its parts.

Spot weights are 4 (placement), 3 (unrouted), 2 (other errors) and 1 + rise + cover loss (physics), so legality is repaired first, then completion, which matches the acceptance order.

**Windows.** A spot's window holds its own unlocked parts plus the unlocked parts whose centres lie within a 2 mm margin of the region they and the spot's points span, nearest first, at most 8 and at most 35 % of the board's movable parts (at least 3). On a 15-part board a 12-part window was a global re-place, and it lost completion (17 → 28 unconnected). Locked parts, parts that carry Edge.Cuts and staged parts never move. On a first attempt, parts with more than 12 connected pads stay fixed too, unless nothing smaller can move: moving an MCU rips up every net it has. In the first smoke run, a window that moved the MCU ripped 15 nets (132 items) and cost one bridge run of 270 s. The rectangle covers every movable part's current courtyard box, so the annealer starts inside it. Overlapping windows merge while the union stays within the part cap. A spot with no movable part within reach gets a **re-route window**: no part moves, the nets touching the region are ripped up and the bridge routes them again in a new order. An example is two track ends of a rail that never met. Its retry is a normal, larger window. A rejected window is retried up to its try count, larger (margin ×1.5, at most twice) and with the congestion weight ×1.5 and the physics weight ×2. An accepted window resets every count, since the board changed. On odd retries the window's modules are not redone: their nets go to the bridge, since their locked copper and guard pours may be what blocks the corridor.

### Congestion penalty

`CongestionHistory` is PathFinder's history cost on a 1 mm grid: every routed evaluation, accepted or not, adds 1 (in units of a bin's routing supply) along each failed connection's corridor. A region where routing failed stays expensive after one re-placement. RUDY marks how crowded the failed region is: the placer's own RUDY map of the routed placement adds 0.5·max(0, u − 0.5) to history bins within 3 mm of a failure. Alone, RUDY ranks PCB routability near chance ([joint-place-route](../physics/joint-place-route.md)), so it never opens a window by itself. Applying it uses the placer's own congestion model, `kae.place.cost.Congestion`, a RUDY map with pin-escape demand priced as Σ max(0, u − 0.5)² over bins. The history, resampled to the annealer's bins and limited to the window plus two bins, enters through the placer's `cong_history` hook (`make_annealer`, `local_replace`). It is added to the static demand array:

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

Because the cost grows with the open connections, the window's rip-up is local: every net loses only the items inside the window and at the moved pads, and none is ripped whole. Afterwards everything except the critical copper is unlocked again. `--set window_router=bridge` restores the full bridge for windows.

### Acceptance

| Order | Criterion | Rule |
|---|---|---|
| 1 | legality: KiCad placement-type errors whose items are only pads and footprints | must not rise |
| 2 | completion and DRC: unconnected + errors, then unconnected | neither may rise; a board that becomes clean is kept; another strict gain is kept if physics rises by at most 10 % per item gained |
| 3 | routed physics: Σ_modules min(u, 5), a module without a value counted as 3 | with equal completion and DRC, must fall by more than 0.5 % |

The clean rule and the per-item slack are the user's decision (confirmed after the first A/B), and they are the default. On ch552g a window made the board clean (1 unconnected → 0) while its decoupling loops, now routed by the bridge, raised Σu from 1.17 to 2.88. A 10 % flat slack reverted it. The strict reading (physics never worse, `--set phys_slack=0`) reverted the first smoke run's only window, which had halved the unconnected items (15 → 7) at +33 % physics. The MCU moved there and lengthened its decoupling loop.

A rejected candidate is dropped, and the incumbent board, its bookkeeping and its feedback stay. Its failures still enter the congestion history.

### Determinism and budgets

Stage seeds derive from the run's seed and the iteration (`derive_seed`), windows are ordered by priority then position, Freerouting is deterministic for an item order, and the window anneal uses a fixed move count. So a seed repeats whenever no time budget binds; on a loaded host the clocks can bind. The budget is wall seconds: 30 % for the placer, 60 % of the rest for the first route, then windows, the finishing reserve and the write reserve.

### Measured

kaebench `joint` (score v6, in-tree harness), KiCad 10.0.7, 6 split-B boards (olimex DC-DC, noisecard, PMW3610, XIAO base, bipolar supply, CH552G), seeds 0 and 1 (k = 2), 900 s, `-j 1` on a shared 4-core host. Σu is the routed-physics total of the scored board (`critical_recheck.board_physics`, brief from the human placement, Σ min(u, 5)). It is unreliable where hops are open [C: `tools/research/joint/joint_physics.py`].

| Arm (seed 0 / seed 1) | clean boards | legal | unconnected | DRC errors | Σu (mean) | module value / human (median) | worst rail mΩ (median) | time s |
|---|---|---|---|---|---|---|---|---|
| human layout | 6 / 6 | 6 / 6 | 0 / 0 | 0 / 0 | 3.45 | 1.00 | 42 | — |
| human placement + Freerouting | 2 / 2 | 6 / 6 | 23 / 23 | 7 / 7 | 3.16 | 0.99 | 101 | 24 / 29 |
| kae place + bridge (staged) | 3 / 3 | 6 / 5 | 3 / 5 | 0 / 5 | 4.48 / 4.01 | 1.33 / 1.08 | 102 / 107 | 118 / 104 |
| loop, no module stage | 3 / 4 | 5 / 6 | 5 / 3 | 1 / 0 | 5.16 / 5.03 | 1.37 / 1.35 | 127 / 97 | 130 / 127 |
| joint loop | 3 / 3 | 6 / 6 | 13 / 10 | 0 / 0 | 2.22 / 3.51 | 0.65 / 0.88 | 55 / 59 | 241 / 300 |

**Window cost, before and after `kae.route.incremental`** (all windows of all runs):

| Window router | windows routed | iteration s (median, range) | of which routing s | kept |
|---|---|---|---|---|
| full bridge, 16 passes, repair rounds (joint v5 + v6, k = 1) | 21 | 113–131 (13–201) | 107–124 (11–192) | 10 |
| incremental, 1 pass, no optimizer (joint, k = 2) | 30 | 19 (8–158) | 7.4 (5.1–58) | 4 |
| incremental (loop without modules, k = 2) | 9 | 12 (8–21) | 6.5 (5.6–7.6) | 0 |

A window's routing now costs a JVM start, the DSN load and one pass of 1–2 s over 8–13 open connections. The rest of a window is the re-anneal (~8 s) and, when its modules are redone, their stage (capped at 20 s). A 900 s run now gets 5–7 windows on the boards that need them, where it got 1–4.

What the numbers say:
- **Cheap windows, few wins.** The loop with modules cut unconnected + errors from 38 to 23 inside its 12 runs (5 → 6 clean). Noisecard went 11 → 6 in one 21 s window. Without the module stage, the staged result is nearly finished (3–5 unconnected on 6 boards), and 0 of 9 windows beat it. One Freerouting pass leaves 1–2 connections of a window open, and the acceptance rule then reverts it.
- **The module stage still costs completion and buys physics.** It gives the lowest routed physics (module values 0.65–0.88× the human's, worst rail 55–59 mΩ against ~100 for every other arm) and the most unconnected items (10–13 against 3–5).
- **Noise.** Freerouting itself repeats (the human-placement arm is identical across seeds and runs). The kae arms vary with their seeds and with where time budgets bind: staged gave 3 and 5 unconnected, the loop 13 and 10. On 6 boards the differences in clean count (3 for every kae arm but one seed) are within that.

## Recommendations for our system

1. **Judge every iteration by KiCad, accept lexicographically.** The loop can then only help: its worst case is the staged pipeline.
2. **Repair where it failed, not everywhere.** A window costs one bridge run with almost everything locked. A full re-place would lose the copper that already works.
3. **Keep the history.** Failures accumulate as congestion cost. A window that failed once keeps steering the placer away even when the next routing succeeds by luck elsewhere.

## Conflicts and open questions

- **What a window cannot fix in one pass.** One Freerouting pass leaves the hardest 1–2 connections of a window open. More passes or our own grid router (the critical router's exactly verified A*) for the last connections are the next step.
- **Freerouting's cost per open connection** is 1–2 CPU s (noisecard: 28 open, 17–19 CPU s, ~15 GB allocated; heap and GC settings change nothing). So a window stays cheap only while its rip-up stays local.
- **Window choice** is greedy (least-tried, highest priority). An LNS over several disjoint windows per bridge run, or a bandit over window kinds, may pay on larger boards.

See also: [month-plan](month-plan.md) · [joint-place-route](../physics/joint-place-route.md) · [critical-net-routing](../routing/critical-net-routing.md) · [freerouting-constraint-bridge](../routing/freerouting-constraint-bridge.md) · [pathfinder-negotiated-congestion](../routing/pathfinder-negotiated-congestion.md)
