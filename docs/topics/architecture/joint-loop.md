# The joint loop: routing feedback into local re-placement

**TL;DR**
- Placement and routing depend on each other: the placer cannot see where the router will fail, and the router cannot move a part. `kae.joint` closes the loop at the granularity that scales on PCBs: place and route the whole board once, then repair **windows** (a few parts and the nets touching them) where routing failed, DRC complained or a module's routed physics shifted.
- One iteration = re-anneal the window's parts with everything else fixed (the placer's `subset`/`window` API) under a congestion penalty built from where routing failed, rip up only the nets touching the window, redo the window's modules (critical copper), re-route with everything else locked, judge with KiCad DRC and the routed-physics recheck.
- An iteration is kept only if it is lexicographically better: legality, then completion and DRC, then routed physics. Legality, unconnected items and DRC errors may never get worse. A board that becomes clean is always kept. Any other completion gain may cost at most 10 % of routed physics per item gained, and with equal completion physics must improve. Otherwise it is reverted, so the output is never worse than the staged pipeline.
- On 6 split-B boards (kaebench `joint`, 900 s, one shared 4-core host), the loop's repairs cut unconnected items + errors from 32 to 23 within its runs and turned 2 unfinished boards clean. Across arms, though, run-to-run noise from time-bound Freerouting (1–13 unconnected on one board) is larger than every difference: all kae arms have cp1 0.5, as does the human placement routed by the bridge. Each window costs 100–220 s of bridge time, so 900 s buys 1–4 windows [C].

## Key facts

### Why a loop, and why windows

The [joint place-route](../physics/joint-place-route.md) survey names three reasons staged place-then-route gets stuck: placement proxies do not rank near-equal placements (RUDY at chance on PCBs), the router cannot move parts, and the physics that decides quality exists only once copper exists. Fully joint search pays a route per move (PROXI: 6–11× CPU); what scaled in VLSI is partial: global routing inside placement (IPR, SimPLR) or cell moves with partial reroute (Starfish). The loop here is the Starfish pattern at PCB scale. The unit of work is a window, the cost of a move is one bridge run with almost everything locked, and the judge is the same KiCad DRC the benchmark uses.

It is also the month plan's module loop ([month-plan § joint loop](month-plan.md)) generalized. The re-tweak of [critical-net routing](../routing/critical-net-routing.md) rips up neighbours around a flagged module but cannot move parts, and on the A/B suite its rounds never paid (unconnected rose each time). Here a flagged module's window re-places its parts too.

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
| 5. Re-route | the bridge with everything else locked | stages.route |
| 6. Judge | DRC + recheck; accept or revert | [scorecard.py](../../../kae/src/kae/joint/scorecard.py) |

Steps 1–6 repeat until the board is clean with no module flagged, no window is left, the iteration cap is reached (12), or the time left (minus a reserve of max(25 s, 4 %) for the final write) is below what an iteration has been taking.

### Feedback: from KiCad's report to parts

- **Unrouted connections.** Each `unconnected_items` entry names two items with positions. A pad's description ends in "of *ref*", which names the part whose pose decides the corridor. The corridor is the segment between the two items, as wide as a fifth of its length (the router's detour room), clamped to 1–4 mm.
- **DRC errors.** Each error-level violation (library-environment checks excluded, as kaebench) is attributed to the parts its pads belong to and to the routing items (by uuid) involved. A placement-type error (kaebench's list: courtyards, clearance, hole clearance, edge, keepouts) whose items are only pads and footprints belongs to the placement. Its spot carries KiCad's shortfall (required minus actual clearance). The window's re-anneal bumps those parts by the shortfall plus 0.15 mm, and the bump is kept even when the routing bumps are dropped. The placer's model judged them legal, so this is a constraint it missed. On olimex the placer left 7 hole-clearance errors of 0.19–0.63 mm (pads against mounting-hole NPTHs, 1.85 mm required), and a fixed 0.15 mm bump did not clear them.
- **Physics shifts.** The recheck flags a module whose routed utilization rose more than 15 % over its module-stage value, crossed 1, or lost more than 0.10 of plane cover. Its spot sits at its parts.

Spot weights are 4 (placement), 3 (unrouted), 2 (other errors) and 1 + rise + cover loss (physics), so legality is repaired first, then completion, which matches the acceptance order.

**Windows.** A spot's window holds its own unlocked parts plus the unlocked parts whose centres lie within a 2 mm margin of the region they and the spot's points span, nearest first, at most 8 and at most 35 % of the board's movable parts (at least 3). On a 15-part board a 12-part window was a global re-place, and it lost completion (17 → 28 unconnected). Locked parts, parts that carry Edge.Cuts and staged parts never move. On a first attempt, parts with more than 12 connected pads stay fixed too, unless nothing smaller can move: moving an MCU rips up every net it has. In the first smoke run, a window that moved the MCU ripped 15 nets (132 items) and cost one bridge run of 270 s. The rectangle covers every movable part's current courtyard box, so the annealer starts inside it. Overlapping windows merge while the union stays within the part cap. A spot with no movable part within reach gets a **re-route window**: no part moves, the nets touching the region are ripped up and the bridge routes them again in a new order. An example is two track ends of a rail that never met. Its retry is a normal, larger window. A rejected window is retried once with the margin ×1.5, two more parts, ICs allowed, the congestion weight ×1.5 and the physics weight ×2, then it is exhausted. On that retry the window's modules are not redone: their nets go to the bridge, since their locked copper and guard pours may be what blocks the corridor. The acceptance rule prices the physics this costs.

### Congestion penalty

`CongestionHistory` is PathFinder's history cost on a 1 mm grid: every routed evaluation, accepted or not, adds 1 (in units of a bin's routing supply) along each failed connection's corridor. A region where routing failed stays expensive after one re-placement. RUDY marks how crowded the failed region is: the placer's own RUDY map of the routed placement adds 0.5·max(0, u − 0.5) to history bins within 3 mm of a failure. Alone, RUDY ranks PCB routability near chance ([joint-place-route](../physics/joint-place-route.md)), so it never opens a window by itself. Applying it uses the placer's own congestion model, `kae.place.cost.Congestion`, a RUDY map with pin-escape demand priced as Σ max(0, u − 0.5)² over bins. The history, resampled to the annealer's bins and limited to the window plus two bins, is added to the static demand array:

u_b = (D_nets + D_escape + h_b·S_b) / S_b.

The extra demand never moves with a part, so both engines (the reference `Annealer` and the compiled `FastAnnealer`, which copies the arrays at build time) stay exactly incremental. Moves that keep a window's nets and pins out of failed bins become cheaper, as a history cost makes a congested node dearer for every net in PathFinder. In a window the congestion weight is doubled (30 → 60). Parts named by an unrouted connection are bumped 0.25 mm (`Problem.bump`, more occupancy on every side) and the routing margin is 0.3 mm. Both are dropped if they are what makes the window illegal.

The re-anneal also carries the placer's physics terms (`kae.physics.place_terms`, calibrated against routed copper) and protection-order rules, and nets of the window's unrouted connections weigh 2× (the hook `local_replace(net_weights=…)` offers). Legality stays hard and closes with the placer's own loop. KiCad's placement errors on the current board become exact constraints (`exact.kicad_feedback`). Then come grid legality and the greedy legalizer if needed, then the exact check, repaired by `exact.repair(allowed=window parts)` as `local_replace` ends. The rip-up region grows to cover wherever that repair moved a part. An illegal window is discarded before any routing. The annealer runs a fixed move count (6,000 per part), so a window is reproducible whenever its time budget does not bind.

### Rip-up: only what the move invalidates

| Copper | Ripped |
|---|---|
| Unlocked, net on a moved part, small net | the whole net. A fragment left behind is fixed wiring Freerouting will not join in its middle |
| Unlocked, net on a moved part, poured or ≥ 20 pads | items inside the window or touching the moved parts' old pads; the rest stays joined through the pour |
| Unlocked, other nets inside the window | those items; the 4 shortest such nets whole |
| Critical, owned by a module with a moved part or with copper in the window | all of that module's copper; the module stage runs again for it |
| Critical, no module (rails, joins) | inside the window or at a moved pad |

The window's modules are re-optimized with `optimize_modules(modules=…)`, with every part outside the window locked. Their guard pours are recomputed, and the other modules' guards stay. The bridge then routes with every remaining item locked (fixed wiring for Freerouting, untouched by its repair loop) and the guards in place. A window route caps Freerouting at 16 passes and the repair loop at 3 rounds. Afterwards everything except the critical copper is unlocked again.

### Acceptance

| Order | Criterion | Rule |
|---|---|---|
| 1 | legality: KiCad placement-type errors whose items are only pads and footprints | must not rise |
| 2 | completion and DRC: unconnected + errors, then unconnected | neither may rise; a board that becomes clean is kept; another strict gain is kept if physics rises by at most 10 % per item gained |
| 3 | routed physics: Σ_modules min(u, 5), a module without a value counted as 3 | with equal completion and DRC, must fall by more than 0.5 % |

The slack and the clean rule interpret "lexicographic" in the request. On ch552g a window made the board clean (1 unconnected → 0) while its decoupling loops, now routed by the bridge, raised Σu from 1.17 to 2.88. A 10 % flat slack reverted it. The strict reading (physics never worse, `--set phys_slack=0`) reverted the first smoke run's only window, which had halved the unconnected items (15 → 7) at +33 % physics. The MCU moved there and lengthened its decoupling loop.

A rejected candidate is dropped, and the incumbent board, its bookkeeping and its feedback stay. Its failures still enter the congestion history.

### Determinism and budgets

Every stage seed derives from the run's seed and the iteration number (`derive_seed`). Windows are ordered by priority, then by position. Freerouting is deterministic for a given item order. The window anneal uses a fixed move count. So the same seed gives the same result whenever no time budget binds. On a loaded host the placer's, the bridge's and the loop's clocks can bind and change the result. The budget is wall seconds: 30 % for the placer, 60 % of what is left after it and the module stage for the first route, the rest for iterations, and a reserve for the final write.

### Measured

kaebench `joint` kind (harness cc5e564, score v6), KiCad 10.0.7, 6 split-B boards (olimex DC-DC, noisecard, PMW3610, XIAO base, bipolar supply, CH552G), k = 1, 900 s, `-j 1` on a shared 4-core host (load 6–8). Σu is the loop's routed-physics total (`critical_recheck.board_physics` on the scored board, brief from the human placement, Σ min(u, 5)). It is unreliable on boards with open hops [C: `tools/research/joint/joint_physics.py`].

| Arm | cp1 | legal | completion | unconnected | DRC errors | Σu (mean) | module value / human (median) | worst rail mΩ (median) | time s |
|---|---|---|---|---|---|---|---|---|---|
| human layout (`reference`) | 1.00 | 1.00 | 1.000 | 0 | 0 | 3.45 | 1.00 | 42 | — |
| human placement + Freerouting (`human-freerouting`) | 0.33 | 1.00 | 0.891 | 23 | 7 | 3.16 | 0.99 | 101 | 44 |
| human placement + bridge (route kind) | 0.50 | 1.00 | 0.960 | 7 | 0 | 3.79 | 1.05 | 118 | 184 |
| kae place + bridge (staged, `--max-iters 0 --no-modules`) | 0.50 | 1.00 | 0.940 | 12 | 0 | 4.07 | 0.93 | 69 | 219 |
| loop without module stage (`--no-modules`) | 0.50 | 1.00 | 0.956 | 10 | 0 | 4.41 | 1.18 | 92 | 312 |
| joint loop, first full version (v5) | 0.50 | 1.00 | 0.927 | 17 | 0 | 2.38 | 0.81 | 60 | 468 |
| joint loop, final code (v6) | 0.50 | 1.00 | 0.907 | 23 | 0 | 3.14 | 0.86 | 57 | 547 |

Inside the loop's own runs (iteration 0 is the staged pipeline with the module stage):

| Run | unconnected + errors, iteration 0 → final | clean boards | windows kept |
|---|---|---|---|
| joint v6 | 32 → 23 | 1 → 3 | 5 of 12 |
| joint v5 | 25 → 17 | 1 → 3 | 5 of 13 |
| loop without modules | 11 → 10 | 3 → 3 | 1 of 11 |

What the numbers say:
- **The loop works where it gets iterations.** On the bipolar supply a re-route window joined a rail's two track ends in 12 s, and the board became clean. On the CH552G three-part windows made the board clean in 18 s, then a physics window cut Σu from 2.10 to 1.67 at equal completion. On the PMW3610 two windows took 13 → 9 → 8 unconnected while Σu fell.
- **Time is the binding constraint.** Iteration 0 takes 360–570 s on the larger boards (placer ~110 s, module stage ~80 s, bridge 250–400 s). A window then costs 100–220 s, mostly Freerouting, which times out even with everything else locked. Noisecard and olimex got one or two windows.
- **Noise.** Five runs of near-identical code gave noisecard 1, 4, 7, 10 and 13 unconnected after iteration 0, because the time-bound Freerouting stops at a load-dependent point. Arm-level differences on 6 boards are inside that band. The 50-core run (33 boards, unloaded cores) is needed to separate them.
- **The module stage costs completion and buys physics.** The module-stage arms reach the lowest routed physics: module values 0.81–0.86× the human's, worst rail drop 57–60 mΩ against 69–118 for the staged and bridge arms. They also leave the most unconnected items. With modules, the loop's slack rule kept a window that made CH552G clean at Σu 1.5 → 5.2.

## Recommendations for our system

1. **Judge every iteration by KiCad, accept lexicographically.** The loop can then only help: its worst case is the staged pipeline.
2. **Repair where it failed, not everywhere.** A window costs one bridge run with almost everything locked. A full re-place would lose the copper that already works.
3. **Keep the history.** Failures accumulate as congestion cost. A window that failed once keeps steering the placer away even when the next routing succeeds by luck elsewhere.

## Conflicts and open questions

- **The bridge's wall time dominates.** Each iteration runs Freerouting and the bridge's DRC repair rounds, ~30–120 s on A/B boards, so a 900 s budget buys a handful of windows. A bridge mode that routes only the open nets, with no repair rounds unless DRC finds errors, would multiply the iterations.
- **Interface requests** (owners asked; workarounds in kae/joint until then): a public congestion-history hook in the placer (`cong_args={"history": ndarray}`, today penalty.py adds to the arrays), and a public `Problem.add_obstacle`.
- **Window choice** is greedy (least-tried, highest priority). An LNS over several disjoint windows per bridge run, or a bandit over window kinds, may pay on larger boards.

See also: [month-plan](month-plan.md) · [joint-place-route](../physics/joint-place-route.md) · [critical-net-routing](../routing/critical-net-routing.md) · [freerouting-constraint-bridge](../routing/freerouting-constraint-bridge.md) · [pathfinder-negotiated-congestion](../routing/pathfinder-negotiated-congestion.md)
