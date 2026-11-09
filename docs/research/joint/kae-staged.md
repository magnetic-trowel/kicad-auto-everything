# kae staged: place, then route with the bridge

**Status:** worked on splits A+B; partial on split C (our placements route worse than the human ones).
**First published:** 2026-10-23, commit [7bd163f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7bd163f432a0ce4aeb115e0bc87f3777f70f4e2e) on branch `claude/vigilant-mayer-i91rrr` (as `--max-iters 0` of the joint loop; pipeline A/B at [c9c49d6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c9c49d6bd21128a526a9b1386a56e8ec875068db)).

Scope: the sequential kae baseline: [`kae place`](../placement/kae-placer.md) with physics, then the [kae Freerouting bridge](../routing/kae-freerouting-bridge.md) with [last mile](../routing/kae-last-mile.md); no module stage, windows or finishing stage. Not here: staged arms of the joint A/B runs (4814e11, 0465818, last-mile local) -> [kae-joint-loop.md](kae-joint-loop.md#results); fixed-interface tasks (`place-fixed`, `joint-fixed`) -> [kae-fixed-interface](../placement/kae-fixed-interface.md).
Keys: kae staged, staged pipeline, kae staged (restarts), `--max-iters 0 --no-modules`, place task, bridge probe, last mile, split C, connectors moved

Merit method **"kae staged (restarts)"**: `kae.joint.cli run --max-iters 0 --no-modules`, `joint-fixed`, 900 s, code at `1650f8e`, 4-way restart wrapper (`tools/kaeres/experiments/merit-restart.sh`); 500-board comparison (experiments merit-500r3 / merit-500r3k) running, results pending.

## Idea and how it works

1. `kae place` (seed, macros, CP-SAT floorplan, annealer with the [fast physics terms](../placement/kae-physics-terms.md), [exact legality and the KiCad DRC loop](../placement/kae-exact-legality.md)); 30% of the wall budget inside `kae.joint.cli`.
2. Bridge: KiCad rules → constraint-complete Specctra DSN, hardened Freerouting, DRC-driven [repair rounds](../routing/kae-repair-loop.md), then the grid last mile (bridge default since [c9c49d6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c9c49d6bd21128a526a9b1386a56e8ec875068db)).
3. Judge: kicad-cli DRC on the re-opened board (kaebench scorer).

Same code = the joint loop's iteration 0 ([kae-joint-loop](kae-joint-loop.md)), so the loop's worst case equals staged. Pipeline runs below ran placer and router as two kaebench steps (`place` task scored with the router as probe); 9,000 s runs used the `joint` task kind.

## What we tried

- `place` tasks (connectors free, task spec 6), routed by the bridge + last mile as kaebench probe, vs the human placement routed by the same probe: A+B (33 boards, k = 2, 1800 s) and split C (78 tasks with movable parts, k = 1, 3600 s).
- Full benchmark at [03096d9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/03096d9fa4203cb6983f39592438c88410c674b7): A+B placements routed by the 4-way restart portfolio.
- `joint` tasks at [4814e11](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4814e11fbd34efeeaca6646f631083f54d9713df) (staged vs joint vs human + Freerouting, 33 boards, k = 2, 9,000 s) and local 6 split-B boards, seeds 0/1, 900 s, with and without the last mile: → [kae-joint-loop.md](kae-joint-loop.md#results).

## Results

| run | ours (kae place) | human placement | source |
|---|---|---|---|
| A+B, bridge + last mile probe, 1800 s, k = 2: legal, cp1, cpk, completion | 65/66, **0.909**, 0.939, 0.997 | 66/66, 0.909, 0.939, 0.998 | [pipeline-ab-c9c49d6](../../../bench/results/2026-10-24-pipeline-ab-c9c49d6.md) |
| A+B, 4-way portfolio probe, k = 2: cp1, cpk, completion | 0.939, 0.939, 0.997; HPWL 0.724x human | **1.000**, 1.000, 1.0 | [full-benchmark-03096d9](../../../bench/results/2026-10-24-full-benchmark-03096d9.md) |
| split C, bridge + last mile, 3600 s, k = 1: legal, clean, completion | 77/78, **30/78** (0.385), 0.907 | 78/78, **43/78** (0.551), 0.964 | [pipeline-c-c9c49d6](../../../bench/results/2026-10-24-pipeline-c-c9c49d6.md) |
| A+B `joint` kind, 9,000 s (staged arm): cp1, cpk; module ratio vs human | 0.879, **0.939** (best cpk of all arms); 0.824 | → [kae-joint-loop.md](kae-joint-loop.md#results) | [joint-ab-4814e11](../../../bench/results/2026-10-24-joint-ab-4814e11.md) |

- A+B per board (bridge probe): ours worse on paw3395, badjeff-pmw3610 and paw3222 attempt 0 (illegal placement); better on emmc-interposer, olimex dcdc-50-5-12 and siderakb-pmw3610 (the board no router had closed on the human placement).
- Split C: 15 boards route clean only on the human placement, 2 only on ours; our placements add silk_overlap 15, solder_mask_bridge 2, hole_clearance 2, copper_edge_clearance 2 to the starved_thermal 23 both share.
- One single-run benchmark each; split C is k = 1. Rows not all comparable: task specs (6 vs 8), router versions and budgets differ.

## Verdict

- **A+B: worked.** Our placement costs nothing in routability and carries better physics (module ratio 0.824x human after routing at 9,000 s). Part of the A+B advantage came from moving connectors, which a designer cannot do ("placer advantage from moving connectors is not real", [status-2026-10-25](../../topics/architecture/status-2026-10-25.md)); this led to the fixed-interface task kinds.
- **Split C: did not hold.** On dense sensor boards our placer crowds the strip between sensor pins and edge, and no estimator predicted the failures → [kae-placer open problems](../placement/kae-placer.md#open-problems). The joint loop is the attempt to close the gap ([kae-joint-loop](kae-joint-loop.md)).

## Code

- `PYTHONPATH=kae/src python -m kae.joint.cli run IN OUT --time S --seed N --max-iters 0 --no-modules` (the merit command), or `python -m kae.cli place` followed by `python -m kae.route.cli route`.
- `kae/src/kae/joint/{cli,loop,stages}.py`, `kae/src/kae/place/`, `kae/src/kae/route/`. A/B driver: `tools/research/joint/run_joint_ab.sh`; physics read-out `tools/research/joint/joint_physics.py`.

## Related

[kae-joint-loop](kae-joint-loop.md), [kae-placer](../placement/kae-placer.md), [kae-fixed-interface](../placement/kae-fixed-interface.md), [restart portfolio](../routing/kae-restart-portfolio.md).
