# One month: physics-first joint placement and routing

Scope: the first-month plan (status 2026-10-22) for `kae` to place and route real boards end to end from the kaebench place task (fixed parts locked, the rest off-board); it replaces milestones M1–M6 of [system-design-build-plan](system-design-build-plan.md) for month 1, and the physics engine ([physics-engine-design](physics-engine-design.md)) supplies the judges and, from week 3, exact quotes. Not here: what was built and measured -> [status-2026-10-25](status-2026-10-25.md); the loop as built -> [joint-loop](joint-loop.md).
Keys: month plan, day-30 goal, physics-first placer, self vs interaction terms, `kae.board.model`, `pad_xy`, physics brief, `kae.physics.place_terms`, module, re-tweak, physics-off ablation, `--min-movable 1`

## Day-30 goal and pipeline

The placer is physics-first: it reads what each circuit structure does, places the physically decisive structures at their optimum, and trades the rest against routability; routing runs inside the same loop.

**Done = three numbers** on the 112-board qualified suite and a corpus dev set, all against the same harness commit (thresholds are proposals; the user decides):
1. routed clean rate ≥ human placement + Freerouting on splits A and B;
2. physics scorecard ≥ the human placement's on the binding budgets of most boards;
3. ablation: physics terms improve physics without costing routability.

**Pipeline:** board I/O → comprehension → physics brief → fast physics terms → cells-first seed → legalize → anneal → route critical nets → route the rest → repair loop → judge. Each stage is a `kae` module ([system-design](system-design.md#packages)) with a file contract.

**Compute:** code and smoke tests in the cloud session; suite and corpus runs on the shared benchmark host (≤ 50 cores and 96 GB, detached, under its cgroup).

## Why physics first changes the placer

A wirelength/congestion placer treats every net alike. The decisive physics sits in a few structures whose geometry placement fixes before any track exists:

| Structure | What placement fixes | Budget it spends | Estimator (week 1) |
|---|---|---|---|
| Commutation cell (buck, boost, bridge) | input-cap–switch–return path length, side, layer change | loop inductance → ringing, overshoot, radiated dipole | height × squares over the reference plane, plus via terms ([pdn-and-commutation](../physics/pdn-and-commutation.md)) |
| Switch node | copper extent near quiet nets | capacitive dv/dt injection | node area × coupling to victims ([lens-sy](../physics/lens-sy.md)) |
| Decoupling | pin–capacitor distance, via sharing, capacitor order | loop inductance per power pin | mounting L + μ0·h·ℓ/w ([decoupling-pdn](../rules/decoupling-pdn.md)) |
| Crystal, clock | loop length, distance to aggressors | phase noise, start-up margin, emission | loop length and aggressor coupling |
| Aggressor–victim pairs | separation and orientation | mutual inductance and capacitance | loop–loop coupling ∝ h_a·h_v over a plane ([lens-sy](../physics/lens-sy.md)) |
| Connectors, cables, antenna | order of protection and filters, keep-outs, feed length | common-mode current on the world node, ESD path, RF mismatch | world-node ledger ([lens-ct](../physics/lens-ct.md)) |
| Heat sources | spacing, copper and edge access | junction temperature, drift of sensitive parts | kernel plus images ([thermal-physics](../physics/thermal-physics.md)) |

Order ([physics-in-the-loop-optimization](../physics/physics-in-the-loop-optimization.md)): self terms (one cell's loop) are near-convex in that structure's own part poses → solved first as rigid micro-placements; interaction terms (aggressor–victim, thermal coupling) and routability → traded in the global stage.

## Package layout (created in week 1)

```
kae/pyproject.toml
kae/src/kae/board/     model, KiCad file loader, pcbnew extractor and writer, transforms
kae/src/kae/circuit/   roles, structures, decap assignment, physics brief
kae/src/kae/physics/   place_terms (fast estimators); judges wrap tools/research/physics until promoted
kae/src/kae/place/     seed, CP-SAT legalizer, annealer, cost assembly
kae/src/kae/route/     critical-net router, Freerouting bridge, repair loop
kae/src/kae/cli.py     kae place | route | joint | brief | score; kaebench --command adapter
kae/tests/
```

`kae` and `kaebench` never import each other; methods plug in through `--command`. Build the three contracts below first: every later week depends on them.

## Contract 1: the board model (`kae.board.model`)

Units mm and degrees; KiCad board coordinates (y down). Field names fixed from day one.

| Type | Fields |
|---|---|
| `Board` | `path`, `version`, `footprints`, `nets` (name → `Net`), `outline` (polygons with holes, from Edge.Cuts), `keepouts` (rule areas with flags and layers), `zones`, `tracks`, `vias`, `stackup`, `rules` |
| `Footprint` | `ref`, `value`, `lib_id`, `uuid`, `x`, `y`, `rot`, `side` ('F' or 'B'), `locked`, `attrs` (smd, through_hole, board_only, dnp, …), `fields` (MPN, datasheet), `pads`, `courtyard` (polygons in the footprint frame), `body` (fallback extent when no courtyard), `on_board` |
| `Pad` | `number`, `net`, `kind` (smd, thru_hole, np_thru_hole, connect), `shape`, `size`, `lx`, `ly`, `lrot` (footprint frame), `x`, `y` (absolute, from pcbnew when available), `layers`, `drill`, `pinfunction`, `pintype` |
| `Net` | `name`, `netclass`, `pads` (ref, number) |
| `Stackup` | `copper` (ordered layer names), `cu_thickness`, `gaps` (dielectric between adjacent copper, mm), `er` |
| `Rules` | `clearance`, `track_min`, `via_min`, `edge_clearance`, `hole_clearance`, netclasses with widths and clearances |

`kae.board.transform.pad_xy(fp, pad, x, y, rot, side)`: a pad's absolute position for any trial pose; used in the annealer's inner loop; built model and its verification against pcbnew (112 boards, flipped parts included) → [kae-board-model](../../research/placement/kae-board-model.md#results).

## Contract 2: the physics brief (`kae.circuit.brief`)

One JSON document per board:
- net roles: ground, rails with voltage, switch nodes, clocks, high-speed pairs, analog-sensitive, RF;
- part roles;
- structures: commutation cells (loop members in order), decap assignments per IC power pin, crystal circuits, connector–protection chains, feedback dividers, sense resistors with Kelvin taps, RF chains.

Every entry carries a confidence and its evidence (name, value, footprint, pin function, topology). Budgets attach to structures as Beliefs (E5 until a datasheet or simulation fixes them). The place task has nets, values, footprints and pin functions but no schematic or datasheets, so budgets start as E5 priors.

## Contract 3: placement terms (`kae.physics.place_terms`)

`Terms(board, brief)` exposes `total(poses)`, `delta(poses, moved_refs, new_poses)` (incremental moves) and `breakdown(poses)` per structure in physical units (nH, pF, K, dB) with the budget each spends. Each estimator cites its derivation and its validation against an exact kernel ([solver-ladder](../physics/solver-ladder.md)); validate each before the annealer uses it. Annealer cost = Σ budget utilization over structures + routability (signal-net wirelength with ground and power down-weighted, RUDY congestion, escape space) + legality.

## Weeks

| Week | Build | Runs on the shared benchmark host | Exit |
|---|---|---|---|
| 1 | board I/O with verified transforms and writer; comprehension v1; place terms v1; `kae place` returning a legal placement; baselines | baseline (human, noop, Freerouting k = 3) | pads match pcbnew on 112/112 boards; human placement scores better than ≥ 90% of its own perturbations under the place terms (sanity check of brief and terms together); legal placements on split A |
| 2 | cells-first seed; CP-SAT legalizer; annealer on physics plus routability; `kae place` as kaebench `--command` adapter; physics scorecard on placements | suite with Freerouting probe; physics-off ablation (keep it in every run) | legal ≥ 0.95 on A+B; probe clean ≥ human + Freerouting − 0.10 on A+B; physics better than the ablation |
| 3 | critical nets routed by our physics-aware router (cells, decaps, crystals); Freerouting for the rest with them locked; router failures and congestion feed back into placement; `joint` task kind (separate harness commit) | joint runs on the suite | clean ≥ human + Freerouting on A+B |
| 4 | copper in the loop (pours, stitching, decap vias) priced by exact quotes; split C; corpus dev set; report | full suite + corpus dev set | the three day-30 numbers |

## The joint loop: modules, routed physics, re-tweak

**Module** = a physics structure from the brief (commutation cell, decap group, crystal circuit, protection chain) + its parts + its critical copper. Routing it is joint with placing it:
1. **Module stage.** Module parts move and rotate freely (any angle) while its critical copper is routed; physics evaluated on routed segments, not straight hops. Parts are fixed only when the task locks them or a described heatsink holds them; heatsink-mounted parts keep right-angle orientations aligned to it.
2. **General routing.** The bridge routes every other net around the module's locked copper.
3. **Routed physics check.** Each module's physics recomputed on finished copper: other nets' tracks, vias perforating planes, nearby aggressors.
4. **Second tweak.** A module whose budget utilization changed beyond a threshold is unlocked and re-optimized in place (parts, its copper, conflicting neighbouring nets); only that region is re-routed.
5. **Iterate** until no module changes beyond the threshold or an iteration cap; every pass judged by KiCad DRC.

The built loop generalizes this to windows that can move parts → [joint-loop](joint-loop.md).

## How results are judged

- kaebench scoring is never changed to improve a score; the `joint` kind and fixes go in separate commits with baselines re-run; same harness commit, KiCad version, manifest, suite; report cp1, cpk, completion, per-type errors (CLAUDE.md).
- Mechanical interface fixed at its given poses (connectors, mounting holes, fiducials, user-facing parts); everything else placed. A placement that moves them can beat the human board on the metrics while failing its enclosure and cables, so the task that frees them is not the headline (user's decision, 2026-10-24). Class list → [status-2026-10-25](status-2026-10-25.md#user-decisions-binding).
- Place and joint runs include every task with ≥ 1 movable part (`kaebench run --min-movable 1`); tasks that lock every footprint are held out.
- Physics judged apart from cp1/cpk: passports and critics on the routed board, plus the place terms' breakdown, against the human board.

## Open questions

- **Harness ownership.** Scoring v2 in progress on the `harness-integrity` branch ([dev-eval-plan](../verification/dev-eval-plan.md)); baselines re-run when it lands.

Related: [joint-place-route](../physics/joint-place-route.md), [placement strategy candidates](../placement/strategy-candidates.md).
