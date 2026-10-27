# kae critical copper: physics-first routing of loops, rails and modules

**Status:** partial. Physics is better than the bridge's and the human boards'; completion is worse.
**First published:** 2026-10-23, commit [c5c53c4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c5c53c40404a972ba3ede1e0d3ab1a5dcc3e58a0) on branch `claude/vigilant-mayer-i91rrr` (grid router [6b36f77](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6b36f779771940134a3baaca01538a4df501ef1e); recheck and topic doc [6b5447e](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6b5447ea3b6b23930743f8d2caba1358d3cd7c1d)).

A few connections decide a board's physics: commutation cells, decoupling loops, crystal nets, protection chains, power rails. `kae.route.critical` routes them first on the placed board at the geometry the physics wants, prices them with the same objective as the placer, locks them, and lets the [bridge](kae-freerouting-bridge.md) route the rest around them. Decap loops come out about 0.74× the bridge's and rail drop about a third, but the locked copper walls off paths: A+B cp1 0.667 vs 0.727 for the bridge (k = 3, 1800 s).

This is the merit method **"kae critical+bridge (restarts)"** (`kae.route.critical_cli route`); the variant with the soft last-mile tier is **"kae critical soft (restarts)"** ([last mile](kae-last-mile.md)). Results on the 500-board comparison: pending (merit-500r3 / merit-500r3k running).

## Idea and how it works

**Modules** come from the physics brief (`kae.circuit.brief`, see [kae-comprehension-brief](../placement/kae-comprehension-brief.md)) in priority order: cell, path, decap, rgroup, crystal, chain; then rails.

- **Commutation cell / power path.** Every board hop of the hot loop (C_in → switch → return) is as wide as its terminals allow, never below IPC-2221 for the cell current, on the layer next to the reference plane; the switch node stays at class width. A ground hop longer than 1.5× straight + 1 mm is left to the plane. Return vias: up to 4 (more at ≥ 2 A), sites from 24 directions × 4 gaps, added while each lowers routed L by ≥ 2 %.
- **Decap.** Cap rail pad → IC power pin, cap and IC ground into the plane by vias. Pairing from the brief; a cap the IC owns with p < 0.5, or more than `decap_max_mm` = 10 mm away, is left to the bridge. Over its own inner rail plane, a hop longer than `decap_plane_mm` = 2 mm becomes a via into the plane ([759f0e8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/759f0e88554741e7b83c6c25f99279304c3be9a1)).
- **rgroup:** each cap to the nearest identical load's rail pin. **Crystal:** IC pin → crystal → load caps, minimising pulling S·C_trace/4. **Protection chain:** connector → protector → protected part, minimising surge-path L′(w,h)·ℓ plus the protector's ground via.
- `width_ladder` tries widths from widest down; `route_hop` commits the first route that walls off no other net's pin.

**Engine.** The exact grid A* router described on the [last mile](kae-last-mile.md) page (`critical_grid.py`, 0.05 mm, margin-inflated blocking, exact shapely verification), with all numbers from the shared rules API `effective.py`.

**Routed-copper physics** (`critical_physics.py`). A loop is a chain of horizontal strips at height h above the nearest reference plane plus vertical pieces (vias, terminations at body height), evaluated with the placer's closed forms (`kae.physics.fastloop`: partial inductances with plane images, Hammerstad-Jensen self terms, Grover mutuals). Where current has alternatives, the split minimises stored energy xᵀMx under Kirchhoff's current law (a small KKT system; P clipped to positive definite; an active set forbids reverse current). For one alternative pair: L(x) = P_AA + 2xP_AB + 2(1−x)P_AC + x²P_BB + (1−x)²P_CC + 2x(1−x)P_BC. DC: R_track = ρl/(wt), R_via = ρh/(π(d+t_p)t_p) with t_p = 20 µm; widths from IPC-2221 (I = k·ΔT^0.44·A^0.725, k = 0.048 external / 0.024 internal, ΔT = 10 K), the drop budget w ≥ ρlI/(tΔV), and the feed width. Each module is priced as spend/allocation u against `kae.physics.place_terms` with the same structure ids, so placer, module router and recheck optimise one number ([c6ae9be](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c6ae9be0d935bea6e481386ee2863f35a3c62206)).

**Rails** (`critical_rails.py`). Each rail with a source and loads gets E5 current priors by part class (FPGA 1.0 A, motor driver 1.5, PMIC 1.0, LDO 0.3, MCU by pin count, LED 0.02; converter inputs V_out·I_out/(0.88·V_in)). Source ratings by family regex (barrel 5 A, USB-C 3, terminal block 10, XT30/60 15, JST PH 2; LDOs 0.3-1.5 by package; switchers 1). Design current = min(source rating, max(3Σ, Σ + 0.1 A)); drop budget 2 % of rail voltage (1.6 % to the rail when the return is a pour); width = max(drop width, IPC, class, feed). Zones first: a pad in a rail zone on its layer connects by fill, a pad under a zone on another layer gets a via, only the rest get tracks — a trunk to the farthest load at design current, then a branch per load. `rails=auto` routes tracks only where the rail needs more than class width and rips back branches ≤ 1.05× class width (on suzyqboard a 17 mm VBUS track had cut D− and CC).

**Making locked copper routable for Freerouting.** Corner joins (`join_at_corners`): a track end inside a pad but off-centre gets a neck to the centre; one landing on another track's body splits that body, because Freerouting joins only at pin centres and wire corners (before this, 101 body ends and 70 off-centre ends sat on 24 of 28 boards). Trim widths (`trim_tol` 5 %): each loop hop is narrowed to the narrowest width whose loop stays within 5 % of the wide one (lambdakb VDDPIX 1.41 → 0.98 mm for +4.5 % nH). Pin escape check: before committing a hop, nearby unrouted pins of other nets must still reach a 3.5 mm window edge or via site keeping a quarter of their room. Net and island joins (`complete_mm` 8, `island_mm` 20) join a critical net's nearby pads and islands at class width ([ae8ce1c](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ae8ce1c45c06f30b205b40723f56dc3ab5f70383), default in [876f8a9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/876f8a9a159d7a18a8599c2e24f2b9b0f487f935)).

**Spokes first** ([a28bd84](https://github.com/magnetic-trowel/kicad-auto-everything/commit/a28bd84fca0c45f669f144479b004b674bacaa26)). DRC on the bare placed board names pads already starved of thermal spokes; `Session.thermal_spokes` gives each its missing spokes as short legal tracks before any module is routed, and `constraints.thermal_corridors` strips are keepouts for other nets' critical copper.

**Guards and stitching** ([6d731a8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6d731a8168626034c1c30f3954f8e346a2507f53), [e171267](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e171267e73ad11b230df15ac32a9ef9e2e832be0)). For each routed cell, power path and crystal, a zone `kae-crit:<module>` (hull of copper and terminals + 0.5 mm, clipped to the plane zone, one priority above the layer's zones, merged per net and layer) is a hard obstacle for the bridge and is dropped from the output. `stitch_ground` adds vias (≥ 2 mm apart) to every ground fill piece with ground pads tied by fewer than 3 barrels.

**Joint modules** (`critical_joint.optimize_modules`). Unlocked, unshared, non-connector module parts are moved (0.25-2 mm translations, 15-345° rotations, the aligned pose) with exact legality at any angle; candidates are screened by `terms.delta`, the best 6 routed and quoted, a move kept if u falls > 1 %.

The pipeline `critical.run` is critical stage → bridge (with guards) → optional re-tweak ([dead ends](kae-routing-dead-ends.md)). The output is the input plus routing only (`critical_write.transplant` keeps every other byte).

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

Single-board or doc-only evidence [C] from [critical-net-routing.md](../../topics/routing/critical-net-routing.md): bipolar supply ±rails 1.7 mm at ≈ 12 mΩ (human 11 mΩ, Freerouting alone 93-96 mΩ); paw3395 spokes-first seed 1 from 2 starved_thermal + 6 open to 0 errors + 1 open; oasis joins 9 → 1 unconnected; joint modules on 12 human placements (120 s each, 0 DRC errors): hot loops changed on 7 of 8 converters (median −4 %, up to −26 %), decoupling loops in 19 structures (median −9 %, up to −61 %), with no completion measurement. Critical copper had 0 attributable DRC errors on 39 boards. Runtime 0.4-60 s per board on one core.

## Verdict

Partial. The physics gain is real and consistent across runs (it is model-measured: see [physics](../physics/README.md), no lab measurement), but every locked hop is a wall for Freerouting and for the last mile, so completion trails the bridge on every run. Corner joins, trimming, joins and spokes-first recovered part of it; the soft last-mile tier recovers one more board. Open questions: return-coverage findings (RET-COV) are higher on critical arms (A+B 241 vs 185, C 92 vs 74) although every inductance metric is better — unexplained (candidates: copper on the reference layer, guards cutting pours, detours round locked copper). Current priors are priors, not datasheet values. The estimator ranks layouts rather than predicting absolute inductance (olimex human: 10.97 vs 6.4 nH against another passport). Guards and stitching have no isolated A/B. The next step proposed on the branch was local re-placement through the [joint loop](../joint/kae-joint-loop.md).

## Code

`kae/src/kae/route/`: `critical.py` (`Session`, `route_critical`, `run`, `join_at_corners`, `soft_critical`), `critical_modules.py`, `critical_rails.py`, `critical_physics.py`, `critical_grid.py`, `critical_kernels.py`, `critical_space.py`, `critical_recheck.py`, `critical_joint.py`, `critical_write.py`, `critical_cli.py`. Entry point: `python -m kae.route.critical_cli route IN OUT --seed N --time S [--kinds …] [--rails auto|all|none] [--guards …] [--complete-mm] [--island-mm] [--trim-tol] [--last-mile-soft] [--rounds N] [--physics-fidelity fast|exact|multi]`; `critical_cli physics BOARD` measures a finished board. Runners: `tools/research/routing/run_crit_v{2,3,4}.sh` (v2 has no results file). Tests: `kae/tests/test_route_critical*.py`. Topic doc: [critical-net-routing.md](../../topics/routing/critical-net-routing.md).

## Related

[Bridge](kae-freerouting-bridge.md), [last mile](kae-last-mile.md) (soft tier), [dead ends](kae-routing-dead-ends.md) (escape corridors, re-tweak, mixed portfolio), [physics terms in the placer](../placement/README.md), [physics models](../physics/README.md).
