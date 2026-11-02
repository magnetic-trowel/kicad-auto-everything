# Critical-net routing: the decisive copper first, at its physical optimum

Scope: mechanism reference for `kae.route.critical`: which modules are routed, how locked copper is kept routable, the exact grid router, routed-copper physics, current priors, guards, recheck, joint module optimization, validation. Not here: provenance, benchmark runs and verdict -> [research: kae critical copper](../../research/routing/kae-critical-copper.md); recovering completion -> [last mile and restarts](last-mile-and-restarts.md).
Keys: kae.route.critical, critical copper, commutation cell, hot loop, power path, return vias, decoupling, decap, rail group, rgroup, crystal pulling, protection chain, surge path, power rail, E5 priors, join_at_corners, snap_wiring, thermal_spokes, escape corridors, trim_tol, rails=auto, complete_mm, island_mm, decap_plane_mm, GridRouter, critical_grid.py, margin m, place_terms, u = spend/allocation, KKT current split, IPC-2221, guard pours, kae-crit, stitch_ground, critical_recheck, re-tweak, optimize_modules, plane cover

**Results** ([C]; runs and verdict → [research page](../../research/routing/kae-critical-copper.md#results))
1. A few connections decide a board's physics (commutation loops, power paths, decoupling loops, crystal nets, surge path ahead of a protector, high-current rails). `kae.route.critical` routes them first on the placed board at the physics optimum and locks them; the Freerouting bridge routes the rest around them as fixed wiring.
2. Each connection: grid A* + exact verification against KiCad's effective constraints (`kae.route.effective`, the bridge's rule port); each module priced on routed copper against the placer's own allocations (`kae.physics.place_terms`), so placement, module routing and recheck optimize one objective.
3. Physics (33 boards A+B, k = 1, vs bridge alone): decoupling loops median 0.71×, surge paths 0.71×, rail resistance 0.97×; worst rail drop 2.21× human → 0.72×.
4. Locked copper is a wall for the router, so critical copper costs completion; mostly recovered by visible joins, spokes first, the soft last mile and a mixed restart portfolio. Split C at 2ec702e: critical + soft last mile was the first arm to route libresolar-bms-c1 clean; on A+B decaps 0.961 and cells 0.877 of human ([C6](../../../bench/results/2026-10-24-last-mile-c6-57487e6.md)).
5. `optimize_modules` (move module parts while routing their copper, any angle, right angles for heatsink tabs) on 12 human placements: hot loops median −4%, decoupling loops median −9%.

## What is routed

Modules from the physics brief (`kae.circuit.brief`) in priority order (cell, path, decap, rgroup, crystal, chain), then rails ([critical_modules.py](../../../kae/src/kae/route/critical_modules.py), [critical_rails.py](../../../kae/src/kae/route/critical_rails.py)). `width_ladder` tries widths widest-first; `route_hop` commits the first route that walls off no other net's pin.

| Module | Copper drawn | Objective and rule |
|---|---|---|
| Commutation cell | Every board hop of the hot loop (input cap → switch → return); return vias | Loop L. Each hop as wide as its terminals allow, never below IPC-2221 for the cell current, on the layer next to the reference plane; switch node at class width. A ground hop longer than 1.5× straight distance + 1 mm is left to the plane |
| Power path | Loop C_in → pass elements → C_out (load switch, eFuse, ideal diode) | As a cell; widths from the upper bound of the brief's current interval |
| Return vias | Up to 4 (more for ≥ 2 A) at the ground pads | Sites 24 directions × 4 gaps; added while each lowers routed L by ≥ 2% |
| Decoupling | Cap rail pad → IC power pin; cap and IC ground into the plane | Loop L vs the place terms' structure. Pairing from the brief (`pin` or `nearest_pin`). A cap the IC owns with p < 0.5 is not paired; a cap > 10 mm (`decap_max_mm`) from its pin is left to the bridge |
| Rail group | Each cap's rail pad → nearest group load's rail pin; ground via | Rail feeding many identical loads; no loop quoted (which cap serves which load is the layout's choice) |
| Crystal | IC pin → crystal → load caps; load-cap ground vias | Pulling = S·C_trace/4 (ppm): each net's C adds to one load cap |
| Protection chain | Connector → protector → protected part; protector's ground via | Surge path L′(w, h)·ℓ + via to plane; hops after the protector left to the bridge |
| Power rail | Trunk to the farthest load, then branches | DC drop, zones first; tracks only where they beat class width (below) |

Differential pairs and buses stay with the bridge → [diff pairs](diff-pair-routing.md).

## Keeping critical copper out of the router's way

- Joins Freerouting can see ([critical.py](../../../kae/src/kae/route/critical.py) `join_at_corners`): Freerouting joins a wire to a pin/via only at its centre and to another wire only at a corner (KiCad joins anything overlapping). A track ending in a pad off-centre gets a neck to the centre; a track ending on another track's body splits that body. Before: 101 ends on bodies and 70 off-centre pad ends on 24 of 28 boards.
- DSN rounding: at ≥ 100 mm KiCad's DSN loses half a micrometre and fixed wires ending on pin centres float for Freerouting (167 of 1,598 locked track ends on 10 boards); the bridge snaps them back (`translate.snap_wiring`, [bridge](freerouting-constraint-bridge.md)).
- Spokes first: `Session.thermal_spokes` (on) runs before modules. KiCad DRC on the bare board names pads the placement already starves of thermal spokes; each gets its missing spokes as short legal tracks into the fill. paw3395: C11's GND pad starved on the bare board, critical VIN copper took its second spoke's room; crit seed 1 went from 2 starved_thermal + 6 open to 0 errors + 1 open [C]. Spoke corridors (`constraints.thermal_corridors`) keep other nets' critical copper out of every pad's best spoke strips.
- Escape corridors (`escape_mm`, off): strips out of a dense IC's signal pins avoided by other nets' critical copper; on canhw no reduction in unconnected items (19–33 vs 13–29, k = 1–2), decap loops within 1% [C] → [dead ends](../../research/routing/kae-routing-dead-ends.md#3-escape-corridors-out-of-dense-ics-did-not-work).
- Width that buys physics (`trim_tol` 5%): after routing, each loop hop is narrowed to the narrowest width whose loop stays within 5% of the wide one; never below class width or the hop current's IPC width; same centre line, so clearances hold. lambdakb VDDPIX hop: 1.41 → 0.98 mm for +4.5% nH.
- Rails only where they beat class width (`rails=auto`): a branch fitting only at ≤ 1.05× class width has no drop physics over the router's track and is ripped up (suzyqboard: a 17 mm VBUS track between USB connectors had cut D− and CC). Trunk to the farthest load carries the design current; other branches their own load's current.
- Joins of a critical net: nearby pads (`complete_mm` 8) and islands (`island_mm` 20) joined at class width. Shared host (crit-v3): A+B cp1 0.636 with joins vs 0.515 without; locally oasis 9 → 1 unconnected [C]. `soft` writes them unlocked.
- Decaps over their rail plane: rail is an inner plane under both cap and pin and the hop > 2 mm (`decap_plane_mm`) → via into the plane instead of a surface track around the IC.
- Other nets' pins keep an escape: before committing a hop, nearby unrouted pins of other nets must still reach the edge of a 3.5 mm window or a via site, keeping a quarter of their room; else retry with a keep-out around them; an optional hop is dropped instead.
- Ground pours stay whole: crossing a ground pour costs 3× a foreign pour in the search. After routing (`stitch_ground`), every ground fill piece cut off on its layer that holds ground pads and is tied by fewer than 3 barrels gets stitching vias (legal, ≥ 2 mm apart) into the same net's fill on another layer.

## The router: grid search with exact verification

`GridRouter.connect(net, sources, targets, width, layers)` ([critical_grid.py](../../../kae/src/kae/route/critical_grid.py)); also the engine of the [last mile](../../research/routing/kae-last-mile.md):
1. Raster: one grid per layer at 0.05 mm (coarsened above 1.5 M cells). Cell blocked when a centred track would come closer to an obstacle than R = w/2 + KiCad's requirement, plus margin m = √(R² + res²/2) − R, which makes every move between free neighbours legal; m = 2 µm at R = 0.3 mm.
2. Costs: foreign pour 0.4 per cell, ground pour 1.2; 0.4 mm halo around other nets' pads 0.6; via 1.5 cells (3–5 for rails and fallbacks).
3. Search: A* over 8 neighbours, octile heuristic, numba-compiled; vias where one fits on every layer ([critical_kernels.py](../../../kae/src/kae/route/critical_kernels.py)).
4. Geometry: cell path → polylines; ends moved onto pad centres where legal; string-pulled; every segment and via re-checked with exact distances, 2 µm above each requirement; a failing route is refused.
- Rules from the bridge's rule engine, never re-derived ([critical_space.py](../../../kae/src/kae/route/critical_space.py)): track widths per net and layer; via size, drill, same-net pitch; clearances per net pair and layer and each pad's clearance class; edge clearance, hole-to-hole, thermal-spoke corridors, rule areas. The task's `.kicad_dru` must sit beside the board for DRC, or custom drill and edge rules read as errors.

## Physics on routed copper

- Loops ([critical_physics.py](../../../kae/src/kae/route/critical_physics.py)): chain of strips at height h above the nearest reference plane + vertical pieces (vias, terminations at body height), evaluated with the place terms' closed forms (`kae.physics.fastloop`: partial inductances with plane images, Hammerstad-Jensen self terms, Grover mutuals), within 5% of PEEC ([place-terms § 2](../physics/place-terms.md)). A strip with no plane under it is free-space copper.
- Current split where alternatives exist (surface ground track, vias at each end of a return): minimize stored energy xᵀMx under Kirchhoff's current law (small KKT system); P clipped to positive definite; active set forbids reverse current. One alternative pair: L(x) = P_AA + 2xP_AB + 2(1−x)P_AC + x²P_BB + (1−x)²P_CC + 2x(1−x)P_BC.
- One objective with the placer: each module's allocation is its `place_terms.Terms` structure (same id); u = spend/allocation.
  - Decap: a spec splits into pin clusters (`id#k`) or, for `nearest_pin`, one structure per capacitor (`id#ref`); each cluster has a calibrated per-pin budget and careful-layout clamp; `decap_spend` prices the cluster's caps in parallel, each at its mean loop to the cluster's pins; the worst u counts.
  - Cell: loops through every input cap with calibrated ownership ≥ half the best count, in parallel, as in `build._commutation`.
  - Crystal and surge path: `CrystalComp` (the /4) and `EsdComp` (via to the plane under the protector). Without Terms: E5 priors per pin.
- DC: R_track = ρl/(wt); R_via = ρh/(π(d + t_p)t_p), t_p = 20 µm. Width = max of ([power-copper § 3](../physics/power-copper.md)): IPC-2221 ([rule](../rules/power/high-current.md#trace-width): I = k·ΔT^0.44·A^0.725, k = 0.048 external / 0.024 internal, ΔT = 10 K; 1 A needs 0.30 mm, 5 A 2.77 mm on 35 µm); drop budget w ≥ ρlI/(tΔV); feed width (a ≥ 0.25 A branch as wide as its narrower pad, up to 3 mm); class width.

## Currents: the E5 priors

Used when the brief carries no currents; priors, not datasheet values ([critical_rails.py](../../../kae/src/kae/route/critical_rails.py)).

| Part class | Load current (A) | As a source (A) |
|---|---|---|
| Connector | rating by family | barrel jack 5, USB-C 3, micro/mini USB 1.8, USB A/B 1.5, terminal block 10, XT30/60 15, JST VH / Mini-Fit 5, XH 3, PH 2, SH/GH 1, pin header 3; unknown: 5 if drill ≥ 1 mm, else 1 |
| IC (supply pins only) | FPGA 1.0, motor driver 1.5, PMIC 1.0, audio amp 0.5, load switch 0.5, LDO 0.3, PHY 0.15, RF 0.12, memory 0.05, interface 0.03, logic 0.01, sensor 0.005; MCU by pin count | LDO by package 0.3–1.5, switcher 1, module 0.3 |
| Converter input | V_out·I_out/(0.88·V_in) | cell current from the brief |
| Others | module 0.35, LED 0.02, FET 0.5, BJT 0.1, relay 0.08, resistor V/R ≤ 0.05 | inductor 0.6 × rating |

- Rail design current = min(source rating, max(3Σ, Σ + 0.1 A)); drop budget 2% of rail voltage split between rail and ground (1.6% to the rail when the return is a pour).
- Zones first: a pad in a rail zone on its layer connects by fill; a pad under a zone on another layer gets a via; only the rest get tracks.
- Bipolar supply: ±rails 1.7 mm wide at ≈ 12 mΩ; human board 11 mΩ; Freerouting alone 93–96 mΩ [C].

## Guards, recheck and re-tweak

- Guard pours: for each routed cell, power path and crystal, zone `kae-crit:<module>` over the ground plane under the module = hull of the module's copper and terminals + 0.5 mm, clipped to the plane's zone, cut into hole-free pieces, merged per net and layer, one priority above the layer's zones. The bridge treats its fill as a hard obstacle for other nets; the output never carries guards.
- Board physics ([critical_recheck.py](../../../kae/src/kae/route/critical_recheck.py)), for any finished board, whoever routed it: each net's copper = graph of pads, track ends split at T-junctions, vias, refilled zone regions; a hop follows its least L′-weighted path; a strip's reference = nearest layer with refilled copper under it; cells also report plane cover (share of the loop's hull covered by ground fill).
- Recheck: compare each routed module with its module-stage value (critical copper alone); flag when u grew > 15%, crossed 1, or plane cover fell > 0.10.
- Re-tweak (`--rounds N`, default 0): rip the nets crossing a flagged module's region (at most the 4 shortest, whole), guard the plane, let the bridge re-route; keep a round only if unconnected items and errors do not rise and the flagged modules improve. Rip-ups have not paid: shared host, 2 boards flagged, no round kept; paw3395 round 1 restored a decap from u 0.83 to 0.53 but raised unconnected 3 → 7 [C] → [dead ends](../../research/routing/kae-routing-dead-ends.md#4-routed-physics-recheck-and-re-tweak-loop-re-tweak-did-not-work-recheck-kept-as-a-measurement).

## Joint module optimization and the joint loop

`optimize_modules(board, brief, terms=None, locked=(), …, session=None, window=None, modules=None) -> (poses, copper, report)` ([critical_joint.py](../../../kae/src/kae/route/critical_joint.py)):
- Moves parts not locked, not shared with another module, not connectors; heatsink-tab packages keep right angles.
- Candidates: translations 0.25–2 mm, rotations 15–345°, the aligned pose (terminals facing partners).
- Legality exact at any angle: courtyards with KiCad's 5 µm deflation, pad clearances, committed copper, outline, rule areas.
- Judging: screen by `terms.delta`; route and quote the best 6; keep a move when the module's u falls > 1%.
- `window` (geometry or bounds) and `modules` scope the work; `board_physics`, `recheck`, `stage_values`, `modules_to_retweak` take the same `window`, so the joint loop can re-place and re-route locally → [joint place-route](../physics/joint-place-route.md), [month-plan § The joint loop](../architecture/month-plan.md).
- 12 human placements (120 s each, 0 DRC errors): hot loops changed on 7 of 8 converters, median −4%, up to −26%; decoupling loops changed in 19 structures, median −9%, up to −61% [C]; completion not measured.

## Validation

| Check | Boards | Result [C] |
|---|---|---|
| DRC errors on critical copper, KiCad 10.0.7, with the task's `.kicad_dru` | 33 A+B, 6 C | 0 attributable |
| A/B on shared host (k = 1, 600 s A+B / 900 s C6), bridge alone vs critical + bridge, earlier stage | 33 A+B | cp1 0.606 vs 0.576; completion 0.956 vs 0.943; 0 errors both. Physics vs bridge alone: decaps 0.71 (12 better, 3 worse), chains 0.71, rail R 0.97; vs human: decaps 0.87, rail R 0.95 |
| Same | 6 C | complete 2/6 vs 0/6; completion 0.891 vs 0.854; decaps 0.84, rail R 0.72, cells 1.05; 11 new ground islands on 5 boards (before stitching) |
| Inner-plane foreign track | 6 C | Critical copper puts 0 mm on inner layers; the bridge routing around it puts 872 mm there, vs 473 mm for the bridge alone and 282 mm on human boards |
| Critical stage runtime | 39 | 0.4–60 s per board, one shared core |
| 10× budgets (6000 / 9000 s), k = 3 | 33 A+B, 6 C | cpk 0.697 (A+B), 0 (C); stops never on the clock; physics vs human: decap 0.961, cells 0.888 ([10x](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md)) |
| Last mile, soft tier (2ec702e), k = 2, 3600 s | 6 C | 6/12 clean vs 8/12 for the bridge, on different boards; 0 errors ([C6](../../../bench/results/2026-10-24-last-mile-c6-57487e6.md)) |
| Unit tests | synthetic converter, MCU, crystal, TVS | KiCad-free and KiCad tests; one regression test per bug fixed |

`tools/research/routing/run_crit_v4.sh` runs the A/B, with `crit_compare.py` and passports.

Design rules [I]: route physics first, one engine judges legality (shared rule port), one objective judges physics (`place_terms`); lock only copper that buys physics and make every join visible to the router (trim widths, leave class-width rails and joins to the router, end on centres and corners); protect planes (guards, stitching) rather than repair them (rip-up has not paid).

## Open questions

- Routability vs physics: critical copper still trails the bridge on clean boards; worst on the dense pmw3610 sensor boards, where every last-mile join forces rip-ups nothing absorbs → [last mile and restarts](last-mile-and-restarts.md). Use a mixed portfolio with the critical router first.
- Return coverage: `suite_physics` finds more RET-COV issues on critical arms (A+B 241 vs 185, C 92 vs 74) although critical copper wins every inductance metric ([10x](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md)); candidate causes: critical copper on the reference layer, guards cutting pours, bridge routing around locked copper.
- Estimator vs passport: the routed-copper estimator ranks layouts; the rb HF passport decides absolute values (olimex human board: 10.97 vs 6.4 nH).
- Re-tweak needs a cheaper form than rip-up: pre-route reservation (decap guards) or local re-placement through the joint loop.

## Sources

- Code: [kae/src/kae/route/critical.py](../../../kae/src/kae/route/critical.py) and `critical_*.py` beside it; tests [kae/tests/test_route_critical.py](../../../kae/tests/test_route_critical.py), [kae/tests/test_route_critical_kicad.py](../../../kae/tests/test_route_critical_kicad.py).
- Tools: [tools/research/routing/run_crit_v3.sh](../../../tools/research/routing/run_crit_v3.sh), [tools/research/physics/crit_compare.py](../../../tools/research/physics/crit_compare.py), [tools/research/physics/suite_physics.py](../../../tools/research/physics/suite_physics.py).
- Physics: [place-terms](../physics/place-terms.md), [power-copper](../physics/power-copper.md), [pdn-and-commutation](../physics/pdn-and-commutation.md), [real-board-passports](../physics/real-board-passports.md); IPC-2221 as in [rules/power/high-current](../rules/power/high-current.md).
