# One month: physics-first joint placement and routing

**TL;DR**
- **Goal at day 30.** `kae` places and routes real boards end to end, starting from the kaebench place task (fixed parts locked, the rest off-board). The placer is physics-first: it reads what each structure of the circuit does, places the physically decisive structures at their optimum, and trades the rest against routability. The routing is done inside the same loop.
- **Done means three numbers** on the 112-board qualified suite and a corpus dev set, all against the same harness commit:
  - routed clean rate at least that of human placement plus Freerouting on splits A and B;
  - a physics scorecard at least the human placement's on the binding budgets of most boards;
  - an ablation showing that the physics terms improve physics without costing routability.
- **One pipeline:** board I/O → comprehension → physics brief → fast physics terms → cells-first seed → legalize → anneal → route critical nets → route the rest → repair loop → judge. Every stage is a module of the `kae` package ([system-design](system-design.md) §2) with a file contract.
- **Compute.** Code and smoke tests run in the cloud session. Suite and corpus runs go to sk-tibia (at most 50 cores and 96 GB, detached, under its cgroup).

Status 2026-10-22. This plan replaces milestones M1–M6 of [system-design-build-plan](system-design-build-plan.md) for the first month; the physics engine ([physics-engine-design](physics-engine-design.md)) supplies the judges and, from week 3, the exact quotes.

## Key facts

### Why physics first changes the placer

A placer that minimizes wirelength and congestion treats every net alike. The decisive physics of a board sits in a few structures whose geometry is fixed by placement, before any track exists:

| Structure | What placement fixes | Budget it spends | Estimator (week 1) |
|---|---|---|---|
| Commutation cell (buck, boost, bridge) | input-cap–switch–return path length, side, layer change | loop inductance → ringing, overshoot, radiated dipole | height × squares over the reference plane, plus via terms ([pdn-and-commutation](../physics/pdn-and-commutation.md)) |
| Switch node | copper extent near quiet nets | capacitive dv/dt injection | node area × coupling to victims ([lens-sy](../physics/lens-sy.md)) |
| Decoupling | pin–capacitor distance, via sharing, capacitor order | loop inductance per power pin | mounting L plus μ0·h·ℓ/w ([decoupling-pdn](../rules/decoupling-pdn.md)) |
| Crystal, clock | loop length, distance to aggressors | phase noise, start-up margin, emission | loop length and aggressor coupling |
| Aggressor–victim pairs | separation and orientation | mutual inductance and capacitance | loop–loop coupling ∝ h_a·h_v over a plane ([lens-sy](../physics/lens-sy.md)) |
| Connectors, cables, antenna | order of protection and filters, keep-outs, feed length | common-mode current on the world node, ESD path, RF mismatch | world-node ledger ([lens-ct](../physics/lens-ct.md)) |
| Heat sources | spacing, copper and edge access | junction temperature, drift of sensitive parts | kernel plus images ([thermal-physics](../physics/thermal-physics.md)) |

Self terms of these structures (one cell's loop) are near-convex in its own parts' poses and are solved first, as rigid micro-placements. Interaction terms (aggressor–victim, thermal coupling) and routability are traded in the global stage. This is the order [physics-in-the-loop-optimization](../physics/physics-in-the-loop-optimization.md) derives.

### Package layout (created in week 1)

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

`kae` never imports `kaebench`, and `kaebench` never imports `kae`; methods plug in through `--command`.

### Contract 1: the board model (`kae.board.model`)

Units are mm and degrees; coordinates are KiCad board coordinates (y down). Field names are fixed so every module codes against them from day one.

| Type | Fields |
|---|---|
| `Board` | `path`, `version`, `footprints`, `nets` (name → `Net`), `outline` (polygons with holes, from Edge.Cuts), `keepouts` (rule areas with their flags and layers), `zones`, `tracks`, `vias`, `stackup`, `rules` |
| `Footprint` | `ref`, `value`, `lib_id`, `uuid`, `x`, `y`, `rot`, `side` ('F' or 'B'), `locked`, `attrs` (smd, through_hole, board_only, dnp, …), `fields` (MPN, datasheet), `pads`, `courtyard` (polygons in the footprint frame), `body` (fallback extent when no courtyard), `on_board` |
| `Pad` | `number`, `net`, `kind` (smd, thru_hole, np_thru_hole, connect), `shape`, `size`, `lx`, `ly`, `lrot` (footprint frame), `x`, `y` (absolute, from pcbnew when available), `layers`, `drill`, `pinfunction`, `pintype` |
| `Net` | `name`, `netclass`, `pads` (ref, number) |
| `Stackup` | `copper` (ordered layer names), `cu_thickness`, `gaps` (dielectric between adjacent copper, mm), `er` |
| `Rules` | `clearance`, `track_min`, `via_min`, `edge_clearance`, `hole_clearance`, netclasses with widths and clearances |

`kae.board.transform.pad_xy(fp, pad, x, y, rot, side)` gives a pad's absolute position for any trial pose. It is verified against pcbnew pad-by-pad on all 112 boards, flipped parts included, and the annealer uses it in its inner loop.

### Contract 2: the physics brief (`kae.circuit.brief`)

A JSON document per board: net roles (ground, rails with voltage, switch nodes, clocks, high-speed pairs, analog-sensitive, RF), part roles, and structures (commutation cells with their loop members in order, decap assignments per IC power pin, crystal circuits, connector–protection chains, feedback dividers, sense resistors with Kelvin taps, RF chains). Every entry carries a confidence and its evidence (name, value, footprint, pin function, topology). Budgets attach to structures as Beliefs (E5 until a datasheet or simulation fixes them).

### Contract 3: placement terms (`kae.physics.place_terms`)

`Terms(board, brief)` exposes `total(poses)`, `delta(poses, moved_refs, new_poses)` for incremental moves, and `breakdown(poses)` per structure in physical units (nH, pF, K, dB) with the budget each spends. Each estimator cites its derivation and its validation against an exact kernel ([solver-ladder](../physics/solver-ladder.md)). The annealer's cost is budget utilization summed over structures, plus routability (signal-net wirelength with ground and power down-weighted, RUDY congestion, escape space), plus legality.

### Weeks

| Week | Build | Runs on sk-tibia | Exit |
|---|---|---|---|
| 1 | board I/O with verified transforms and writer; comprehension v1; place terms v1; `kae place` returning a legal placement; baselines | baseline (human, noop, Freerouting k = 3) | pads match pcbnew on 112/112 boards; human placement scores better than ≥ 90% of its own perturbations under the place terms; legal placements on split A |
| 2 | cells-first seed; CP-SAT legalizer; annealer on physics plus routability; `kae place` as a kaebench `--command` adapter; physics scorecard on placements | suite with Freerouting probe; physics-off ablation | legal ≥ 0.95 on A+B; probe clean ≥ human + Freerouting − 0.10 on A+B; physics better than the ablation |
| 3 | critical nets routed by our physics-aware router (cells, decaps, crystals); Freerouting for the rest with them locked; router failures and congestion feed back into placement; `joint` task kind (separate harness commit) | joint runs on the suite | clean ≥ human + Freerouting on A+B |
| 4 | copper in the loop (pours, stitching, decap vias) priced by exact quotes; split C; corpus dev set; report | full suite plus corpus dev set | the three numbers of the TL;DR |

### The joint loop: modules, routed physics, re-tweak

A **module** is a physics structure from the brief (commutation cell, decap group, crystal circuit, protection chain) together with its parts and its critical copper. Routing it is joint with placing it:

1. **Module stage.** The module's parts move and rotate freely (any angle) while its critical copper is routed; physics is evaluated on the routed segments, not straight hops. Parts are fixed only when the task locks them or a described heatsink holds them; parts that mount to a heatsink keep right-angle orientations aligned to it.
2. **General routing.** The bridge routes every other net around the module's locked copper.
3. **Routed physics check.** Each module's physics is recomputed on the finished copper: other nets' tracks, vias perforating planes, and nearby aggressors.
4. **Second tweak.** A module whose budget utilization changed beyond a threshold is unlocked and re-optimized in place (parts, its copper, and the conflicting neighbouring nets), and only that region is re-routed.
5. **Iterate** until no module changes beyond the threshold or an iteration cap is reached; every pass is judged by KiCad DRC.

### How results are judged

- kaebench scoring is never changed to improve a score; the `joint` kind and any fixes go in separate commits with baselines re-run (CLAUDE.md).
- Every comparison uses the same harness commit, KiCad version, manifest and suite, and reports cp1, cpk, completion and per-type errors.
- The board's mechanical interface stays where the design puts it: connectors, mounting holes and fiducials, and user-facing parts (switches, buttons, potentiometers and encoders, displays, panel LEDs, buzzers) are fixed at their given poses and everything else is placed. A placement that moves them can beat the human board on the metrics while failing to fit its enclosure and cables, so results on the task that frees them are not the headline (user's decision, 2026-10-24).
- Place and joint runs include every task with at least one movable part (`kaebench run --min-movable 1`); tasks that lock every footprint are held out, since there is nothing to place.
- Physics is judged apart from cp1/cpk: the passports and critics on the routed board, plus the place terms' breakdown, against the human board.

## Recommendations for our system

1. Build the three contracts first; every later week depends on them.
2. Validate each estimator against an exact kernel before the annealer uses it, and rank human placements against their own perturbations as a sanity check on the brief and the terms together.
3. Keep the physics-off ablation in every run, so the physics terms are shown to pay.

## Conflicts and open questions

- **Definition of "good".** The day-30 thresholds above are proposals; the user decides.
- **Harness ownership.** Scoring v2 is in progress on the `harness-integrity` branch ([dev-eval-plan](../verification/dev-eval-plan.md)); baselines are re-run when it lands.
- **Inputs without a schematic.** The place task carries nets, values, footprints and pin functions but no schematic or datasheets, so budgets start as E5 priors.

See also: [system-design](system-design.md) · [physics-engine-design](physics-engine-design.md) · [joint-place-route](../physics/joint-place-route.md) · [placement strategy candidates](../placement/strategy-candidates.md)
