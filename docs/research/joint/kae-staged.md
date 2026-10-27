# kae staged: place, then route with the bridge

**Status:** worked on splits A+B; partial on split C (our placements route worse than the human ones).
**First published:** 2026-10-23, commit [7bd163f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7bd163f432a0ce4aeb115e0bc87f3777f70f4e2e) on branch `claude/vigilant-mayer-i91rrr` (as `--max-iters 0` of the joint loop; pipeline A/B at [c9c49d6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c9c49d6bd21128a526a9b1386a56e8ec875068db)).

The sequential baseline: [`kae place`](../placement/kae-placer.md) places the board with physics, then the [kae Freerouting bridge](../routing/kae-freerouting-bridge.md) with [last mile](../routing/kae-last-mile.md) routes it. No module stage, no windows, no finishing stage. On splits A+B it routes our placements as well as the human ones (cp1 0.909 for both with the same router) and at 9,000 s it has the best cpk of all arms (0.939). On split C, 30 of 78 of our placements route clean against 43 of 78 human placements.

This is the merit method **"kae staged (restarts)"** (`kae.joint.cli run --max-iters 0 --no-modules`, `joint-fixed`, 900 s, code at `1650f8e`, wrapped in a 4-way restart; `tools/kaeres/experiments/merit-restart.sh`). The 500-board comparison (experiments merit-500r3 / merit-500r3k) is running. Results on the 500-board comparison: pending.

## Idea and how it works

1. `kae place` (seed, macros, CP-SAT floorplan, annealer with the [fast physics terms](../placement/kae-physics-terms.md), [exact legality and the KiCad DRC loop](../placement/kae-exact-legality.md)); 30% of the wall budget when run inside `kae.joint.cli`.
2. The bridge: KiCad rules translated into a constraint-complete Specctra DSN, hardened Freerouting, DRC-driven [repair rounds](../routing/kae-repair-loop.md), then the grid last mile (the bridge default since [c9c49d6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c9c49d6bd21128a526a9b1386a56e8ec875068db)).
3. Judge with kicad-cli DRC on the re-opened board (the kaebench scorer).

The same code runs as the joint loop's iteration 0 ([kae-joint-loop](kae-joint-loop.md)), so the loop's worst case equals staged. In the earlier pipeline runs below, the placer and the router ran as two kaebench steps (`place` task scored with the router as probe); the 9,000 s runs used the `joint` task kind.

## What we tried

- `place` tasks (connectors free, task spec 6), routed by the kae bridge with last mile as the kaebench probe, against the human placement routed by the same probe: A+B (33 boards, k = 2, 1800 s) and split C (78 tasks with movable parts, k = 1, 3600 s).
- Full benchmark at [03096d9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/03096d9fa4203cb6983f39592438c88410c674b7): placements on A+B routed by the 4-way restart portfolio.
- `joint` tasks at [4814e11](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4814e11fbd34efeeaca6646f631083f54d9713df): staged vs joint vs human + Freerouting, 33 boards, k = 2, 9,000 s.
- Local, 6 split-B boards, seeds 0/1, 900 s, with and without the last mile.
- Fixed-interface tasks (`place-fixed`, `joint-fixed`): see [kae-fixed-interface](../placement/kae-fixed-interface.md).

## Results

| run | ours (kae place) | human placement | source |
|---|---|---|---|
| A+B, bridge + last mile probe, 1800 s, k = 2: legal, cp1, cpk, completion | 65/66, **0.909**, 0.939, 0.997 | 66/66, 0.909, 0.939, 0.998 | [pipeline-ab-c9c49d6](../../../bench/results/2026-10-24-pipeline-ab-c9c49d6.md) |
| A+B, 4-way portfolio probe, k = 2: cp1, cpk, completion | 0.939, 0.939, 0.997; HPWL 0.724x human | **1.000**, 1.000, 1.0 | [full-benchmark-03096d9](../../../bench/results/2026-10-24-full-benchmark-03096d9.md) |
| split C, bridge + last mile, 3600 s, k = 1: legal, clean, completion | 77/78, **30/78** (0.385), 0.907 | 78/78, **43/78** (0.551), 0.964 | [pipeline-c-c9c49d6](../../../bench/results/2026-10-24-pipeline-c-c9c49d6.md) |
| A+B `joint` kind, 9,000 s, k = 2: cp1, cpk, errors; module ratio vs human | staged 0.879, **0.939**, 0; 0.824 | human + Freerouting 2.5.0: 0.455, 0.455, 2.61; 0.926 | [joint-ab-4814e11](../../../bench/results/2026-10-24-joint-ab-4814e11.md) |
| 6 split C boards, 9,000 s: clean, legal, unconnected, errors | staged 3/6, 5/6, 86, 6 (joint 3/6, 6/6, 44, 0) | human + FR 0/6, 6/6, 131, 121 | [portfolio-ab-0465818](../../../bench/results/2026-10-24-portfolio-ab-0465818.md) |
| 6 split-B boards, 900 s, local, seeds 0/1: clean; module value vs human | with last mile 5 / 5; 1.24 / 1.33 (without: 3 / 4; 1.18 / 1.39) | | [joint-last-mile-local](../../../bench/results/2026-10-24-joint-last-mile-local.md) |

Per board on A+B (bridge probe): ours worse on paw3395, badjeff-pmw3610 and paw3222 attempt 0 (illegal placement); better on emmc-interposer, olimex dcdc-50-5-12 and siderakb-pmw3610 (the board no router had closed on the human placement). On split C, 15 boards route clean only on the human placement and 2 only on ours; the error mix on our placements adds silk_overlap 15, solder_mask_bridge 2, hole_clearance 2 and copper_edge_clearance 2 to the starved_thermal 23 both share. One single-run benchmark each; split C is k = 1.

## Verdict

Worked on A+B: our placement costs nothing in routability there and carries much better physics (module ratio 0.824x human after routing at 9,000 s). It did not hold on split C: on dense sensor boards our placer puts capacitors in the strip between the sensor pins and the edge, Freerouting's first pass takes about 500 s instead of 13-155 s on the human placement ([kae-place](../../topics/placement/kae-place.md)), and no estimator predicted the failures ([kae-routability-estimators](../placement/kae-routability-estimators.md)). Part of the A+B advantage came from moving connectors, which a designer cannot do ("placer advantage from moving connectors is not real", [status-2026-10-25](../../topics/architecture/status-2026-10-25.md)); that led to the fixed-interface task kinds. Results across these runs are not all comparable: task specs (6 vs 8), router versions and budgets differ between rows. The joint loop is the attempt to close the split-C gap ([kae-joint-loop](kae-joint-loop.md)).

## Code

- `PYTHONPATH=kae/src python -m kae.joint.cli run IN OUT --time S --seed N --max-iters 0 --no-modules` (the merit command), or `python -m kae.cli place` followed by `python -m kae.route.cli route`.
- `kae/src/kae/joint/{cli,loop,stages}.py`, `kae/src/kae/place/`, `kae/src/kae/route/`. A/B driver: `tools/research/joint/run_joint_ab.sh`; physics read-out `tools/research/joint/joint_physics.py`.

## Related

[kae-joint-loop](kae-joint-loop.md), [kae-placer](../placement/kae-placer.md), [kae-fixed-interface](../placement/kae-fixed-interface.md), [restart portfolio](../routing/kae-restart-portfolio.md).
