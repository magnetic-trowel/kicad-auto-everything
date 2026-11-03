# kae critical copper: physics-first routing of loops, rails and modules

Scope: defensive publication of physics-first critical routing: provenance, mechanism summary with parameters, runs, physics ratios, verdict. Not here: full mechanism reference (module table, router, physics, current priors, guards, validation) -> [critical-net routing topic](../../topics/routing/critical-net-routing.md).
Keys: kae critical+bridge (restarts), kae.route.critical, critical_cli, modules, commutation cell, decap, rgroup, crystal, protection chain, rails, width_ladder, route_hop, routed-copper physics, fastloop, KKT split, IPC-2221, E5 priors, join_at_corners, trim_tol, spokes first, guards, stitch_ground, optimize_modules, crit-v3, crit-v6, crit_compare.py, RET-COV

**Status:** partial. Physics better than the bridge's and the human boards'; completion worse.
**First published:** 2026-10-23, commit [c5c53c4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c5c53c40404a972ba3ede1e0d3ab1a5dcc3e58a0) on branch `claude/vigilant-mayer-i91rrr` (grid router [6b36f77](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6b36f779771940134a3baaca01538a4df501ef1e); recheck and topic doc [6b5447e](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6b5447ea3b6b23930743f8d2caba1358d3cd7c1d)).
**Merit methods:** **"kae critical+bridge (restarts)"** (`kae.route.critical_cli route`); soft last-mile variant **"kae critical soft (restarts)"** ([last mile](kae-last-mile.md)). 500-board comparison: pending (merit-500r3 / merit-500r3k running).

`kae.route.critical` routes the few physics-deciding connections first on the placed board at the geometry the physics wants, prices them with the placer's objective, locks them, and lets the [bridge](kae-freerouting-bridge.md) route the rest. Decap loops ~0.74× the bridge's, rail drop about a third; locked copper walls off paths: A+B cp1 0.667 vs 0.727 for the bridge (k = 3, 1800 s).

## Idea and how it works

Mechanism detail and every parameter → [topic](../../topics/routing/critical-net-routing.md). Summary:
1. Modules from the physics brief (`kae.circuit.brief`, see [comprehension brief](../placement/kae-comprehension-brief.md)) in priority order cell, path, decap, rgroup, crystal, chain; then rails ([what is routed](../../topics/routing/critical-net-routing.md#what-is-routed)). Cell/path hops as wide as terminals allow, ≥ IPC-2221 for cell current, next to the reference plane; ≤ 4 return vias (more at ≥ 2 A) from 24 directions × 4 gaps, each kept if it lowers L by ≥ 2%. Decaps: cap > `decap_max_mm` = 10 mm or owned with p < 0.5 left to the bridge; over its inner rail plane a hop > `decap_plane_mm` = 2 mm becomes a via ([759f0e8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/759f0e88554741e7b83c6c25f99279304c3be9a1)). `width_ladder` tries widths widest-first; `route_hop` commits the first route walling off no other net's pin.
2. Engine: exact grid A* (`critical_grid.py`, 0.05 mm, margin-inflated blocking, exact shapely verification), numbers from the shared rules API `effective.py` → [router](../../topics/routing/critical-net-routing.md#the-router-grid-search-with-exact-verification).
3. Routed-copper physics (`critical_physics.py`): strips above the nearest reference plane + vertical pieces with `kae.physics.fastloop` (partial inductances with plane images, Hammerstad-Jensen self terms, Grover mutuals); current split minimizing xᵀMx under KCL (KKT, active set); DC R_track = ρl/(wt), R_via = ρh/(π(d+t_p)t_p), t_p = 20 µm; IPC-2221 I = k·ΔT^0.44·A^0.725 (k 0.048 ext / 0.024 int, ΔT 10 K). Each module priced as u = spend/allocation against `kae.physics.place_terms` with the same structure ids, so placer, module router and recheck optimize one number ([c6ae9be](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c6ae9be0d935bea6e481386ee2863f35a3c62206)) → [physics](../../topics/routing/critical-net-routing.md#physics-on-routed-copper).
4. Rails (`critical_rails.py`): E5 current priors by part class; design current = min(source rating, max(3Σ, Σ + 0.1 A)); drop budget 2% (1.6% to rail when return is a pour); width = max(drop, IPC, class, feed); zones first; trunk at design current then a branch per load; `rails=auto` rips branches ≤ 1.05× class width → [currents](../../topics/routing/critical-net-routing.md#currents-the-e5-priors).
5. Routability of locked copper: corner joins (`join_at_corners`), width trim (`trim_tol` 5%), pin escape check (3.5 mm window, quarter of room), net and island joins (`complete_mm` 8, `island_mm` 20; [ae8ce1c](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ae8ce1c45c06f30b205b40723f56dc3ab5f70383), default in [876f8a9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/876f8a9a159d7a18a8599c2e24f2b9b0f487f935)), spokes first (`Session.thermal_spokes`, `constraints.thermal_corridors`; [a28bd84](https://github.com/magnetic-trowel/kicad-auto-everything/commit/a28bd84fca0c45f669f144479b004b674bacaa26)) → [topic](../../topics/routing/critical-net-routing.md#keeping-critical-copper-out-of-the-routers-way).
6. Guards and stitching ([6d731a8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6d731a8168626034c1c30f3954f8e346a2507f53), [e171267](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e171267e73ad11b230df15ac32a9ef9e2e832be0)): zone `kae-crit:<module>` (hull + 0.5 mm, clipped to plane zone, one priority above, merged per net and layer) is a hard obstacle for the bridge, dropped from output; `stitch_ground` adds vias (≥ 2 mm apart) to ground fill pieces with ground pads tied by < 3 barrels.
7. Joint modules (`critical_joint.optimize_modules`): 0.25–2 mm translations, 15–345° rotations, aligned pose; exact legality at any angle; screen by `terms.delta`, route best 6, keep if u falls > 1%.
- Pipeline `critical.run` = critical stage → bridge (with guards) → optional re-tweak ([dead ends § 4](kae-routing-dead-ends.md#4-routed-physics-recheck-and-re-tweak-loop-re-tweak-did-not-work-recheck-kept-as-a-measurement)). Output = input plus routing only (`critical_write.transplant` keeps every other byte).

## What we tried

crit-v3 ([4e88308](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4e883086fd5da7c90cbec0f41586b1d67644ad94)): A+B k = 3 at 600 s, C6 at 900 s, plus single-attempt variants (r3 re-tweak, `c` joins). 57487e6: A+B k = 3 at 1800 s with and without the last mile. crit-v6 at 10× budgets ([1ef5bf1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1ef5bf10ffb86704afc8c1dd40836b2ac33ad28c)). Joint modules on 12 human placements. Physics compared with `tools/research/physics/crit_compare.py` and `suite_physics.py` (median ratios, lower is better).

## Results

| Run | Arm | cp1 | cpk | Source |
|---|---|---|---|---|
| crit-v3, A+B k=3 600 s | bridge / critical | 0.606 / 0.515 | 0.727 / 0.545 | [crit-v3-4e88308](../../../bench/results/2026-10-23-crit-v3-4e88308.md) |
| crit-v3, A+B k=1 | critical + joins (`c`) | **0.636** | — | same |
| crit-v3, C6 k=3 900 s | bridge / critical | 0.333 / 0.000 | 0.333 / 0.167 | same |
| 57487e6, A+B k=3 1800 s | bridge + last mile / critical + last mile | 0.909 / 0.758 | 0.970 / 0.818 | [last-mile-ab-57487e6](../../../bench/results/2026-10-24-last-mile-ab-57487e6.md) |
| crit-v6 10×, A+B k=3 | bridge / critical | 0.727 / 0.667 | 0.818 / 0.697 | [crit-v6-10x-1ef5bf1](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md) |

Physics (median ratio, `crit_compare`):
| Run | Structure | critical / bridge | critical / human | bridge / human |
|---|---|---|---|---|
| crit-v3 A+B | decap | 0.742 (10 better / 2 worse) | 0.794 | 1.052 |
| crit-v3 A+B | chain | 0.691 | 1.891 | 2.877 |
| crit-v3 A+B | rail R | 1.0 | 0.949 | 1.211 |
| crit-v3 A+B | rail drop on complete boards | — | 0.736 | 2.21 |
| crit-v6 10× A+B | decap / cells / rail | — | 0.961 / 0.888 / 0.948 | 1.179 / 1.299 / 1.129 |
| crit-v6 10× C | decap / cells / power paths | — | 0.889 / 0.849 / 0.764 | 1.008 / 1.136 / rail 1.494 |

Single-board or doc-only evidence [C] (from the [topic](../../topics/routing/critical-net-routing.md#validation)): bipolar supply ±rails 1.7 mm at ≈ 12 mΩ (human 11 mΩ, Freerouting alone 93–96 mΩ); paw3395 spokes-first seed 1 from 2 starved_thermal + 6 open to 0 errors + 1 open; oasis joins 9 → 1 unconnected; joint modules on 12 human placements (120 s each, 0 DRC errors): hot loops changed on 7 of 8 converters (median −4%, up to −26%), decoupling loops in 19 structures (median −9%, up to −61%), no completion measurement. 0 attributable DRC errors on 39 boards. Runtime 0.4–60 s per board on one core.

## Verdict

Partial. The physics gain is real and consistent across runs (model-measured, see [physics](../physics/README.md); no lab measurement), but every locked hop is a wall for Freerouting and the last mile, so completion trails the bridge on every run. Corner joins, trimming, joins and spokes-first recovered part; the soft last-mile tier recovers one more board.
Open: return-coverage findings (RET-COV) higher on critical arms (A+B 241 vs 185, C 92 vs 74) although every inductance metric is better, unexplained (candidates: copper on the reference layer, guards cutting pours, detours round locked copper). Current priors are priors, not datasheet values. The estimator ranks layouts rather than predicting absolute inductance (olimex human: 10.97 vs 6.4 nH against another passport). Guards and stitching have no isolated A/B. Next step proposed on the branch: local re-placement through the [joint loop](../joint/kae-joint-loop.md).

## Code

`kae/src/kae/route/`: `critical.py` (`Session`, `route_critical`, `run`, `join_at_corners`, `soft_critical`), `critical_modules.py`, `critical_rails.py`, `critical_physics.py`, `critical_grid.py`, `critical_kernels.py`, `critical_space.py`, `critical_recheck.py`, `critical_joint.py`, `critical_write.py`, `critical_cli.py`. Entry point: `python -m kae.route.critical_cli route IN OUT --seed N --time S [--kinds …] [--rails auto|all|none] [--guards …] [--complete-mm] [--island-mm] [--trim-tol] [--last-mile-soft] [--rounds N] [--physics-fidelity fast|exact|multi]`; `critical_cli physics BOARD` measures a finished board. Runners: `tools/research/routing/run_crit_v{2,3,4}.sh` (v2 has no results file). Tests: `kae/tests/test_route_critical*.py`.

## Related

[Bridge](kae-freerouting-bridge.md), [last mile](kae-last-mile.md) (soft tier), [dead ends](kae-routing-dead-ends.md) (escape corridors, re-tweak, mixed portfolio), [physics terms in the placer](../placement/README.md), [physics models](../physics/README.md).
