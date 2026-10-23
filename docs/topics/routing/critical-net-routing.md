# Critical-net routing: the decisive copper first, at its physical optimum

**TL;DR**
- A few connections decide a board's physics: commutation loops, power paths, decoupling loops, crystal nets, the surge path ahead of a protector, and high-current rails. `kae.route.critical` routes them first on the placed board, at the geometry the physics wants, and locks them. The Freerouting bridge then routes everything else around them as fixed wiring.
- Each connection is drawn by a grid A* search and verified exactly against KiCad's effective constraints (`kae.route.effective`, the bridge's rule port). Every module is priced on routed copper against the **placer's own allocations** (`kae.physics.place_terms`), so placement, module routing and the recheck optimize one objective.
- Physics wins (33 boards of splits A and B, k = 1, against the bridge alone): decoupling loops at a median 0.71×, surge paths 0.71×, rail resistance 0.97×. The worst rail drop falls from 2.21× the human board's to 0.72× [C].
- The critical copper cost completion: cp1 fell from 0.606 to 0.576. The main cause was joins the router could not see. Freerouting connects a wire to a pad only at the pad's centre and to another wire only at a corner. KiCad's DSN export also rounds half-micrometres at coordinates ≥ 100 mm. The stage now makes every join a centre or corner join and leaves non-physics copper to the bridge, and the bridge snaps fixed wiring onto pin centres.
- `optimize_modules` moves a module's parts while routing its copper, at any angle, with right angles for heatsink tabs. On 12 human placements it lowered hot loops by a median 4 % and decoupling loops by a median 9 % [C]. It and the recheck are window-scoped, for the joint place-and-route loop.

## Key facts

### What is routed

Modules come from the physics brief (`kae.circuit.brief`) in priority order; rails follow ([critical_modules.py](../../../kae/src/kae/route/critical_modules.py), [critical_rails.py](../../../kae/src/kae/route/critical_rails.py)).

| Module | Copper drawn | Objective and rule |
|---|---|---|
| Commutation cell | Every board hop of the hot loop (input cap → switch → return); return vias | Loop L. Each hop is as wide as its terminals allow, never below IPC-2221 for the cell current, on the layer next to the reference plane; the switch node stays at class width. A ground hop longer than 1.5× the straight distance + 1 mm is left to the plane. |
| Power path | The loop C_in → pass elements → C_out (load switch, eFuse, ideal diode) | As a cell. Widths come from the upper bound of the brief's current interval. |
| Return vias | Up to 4 (more for ≥ 2 A) at the ground pads | 24 directions × 4 gaps; vias are added while each lowers the routed L by ≥ 2 %. |
| Decoupling | Cap rail pad → IC power pin; cap and IC ground into the plane | Loop L, against the place terms' structure. Pairing comes from the brief: `pin`, or `nearest_pin`. A cap the IC owns with p < 0.5 is not its own and is not paired. A cap more than 10 mm from its pin is left to the bridge. |
| Rail group | Each cap's rail pad → the nearest group load's rail pin; ground via | A rail feeding many identical loads. No loop is quoted, because which cap serves which load is the layout's choice. |
| Crystal | IC pin → crystal → load caps; load-cap ground vias | Pulling = S·C_trace/4 (ppm): each net's C adds to one load cap. |
| Protection chain | Connector → protector → protected part; the protector's ground via | Surge path L′(w, h)·ℓ plus the via down to the plane. Hops after the protector are left to the bridge. |
| Power rail | A trunk to the farthest load, then branches | DC drop, zones first. A track is drawn only where it beats the class width; see the next section. |

Differential pairs and buses stay with the bridge ([diff-pair-routing](diff-pair-routing.md)).

### Keeping critical copper out of the router's way

Locked copper is a wall for Freerouting. The stage therefore draws only what buys physics, and draws it so the router can join to it.

- **Joins Freerouting can see** ([critical.py](../../../kae/src/kae/route/critical.py) `join_at_corners`). Freerouting joins a wire to a pin or via only at its centre, and to another wire only at a corner; KiCad joins anything that overlaps. A track ending inside a pad off its centre gets a neck to the centre. A track ending on another track's body splits that body there. Before this, 101 ends on bodies and 70 off-centre pad ends sat on 24 of 28 boards.
- **DSN rounding.** KiCad writes DSN coordinates with `%.6g`, so at ≥ 100 mm a pad centre such as 137.2875 mm is written as 137288 µm. Freerouting computes the pin centre as placement + pin offset = 137287.5 µm, so the fixed wire floats. On lambdakb, Freerouting logged the decap stub's pads as "unrouted" and left R2.1 open. 167 of 1,598 locked track ends on 10 boards are affected. The bridge now snaps DSN wiring onto pin centres (`translate.snap_wiring`); the same board is then clean in 24 s [C].
- **Width that buys physics.** After routing, each loop hop is narrowed to the narrowest width whose loop stays within 5 % of the wide one (`trim_tol`). It never goes below the class width or the hop current's IPC width. Same centre line, so every clearance holds. On lambdakb's VDDPIX hop: 1.41 → 0.98 mm for +4.5 % nH.
- **Rails only where they beat the class width.** A branch that fits only at about the class width (≤ 1.05×) has no drop physics over the router's track, so it is ripped up and left to the router. On suzyqboard a 17 mm VBUS track between the USB connectors had cut D− and CC. The trunk to the farthest load carries the design current; every other branch carries its own load's current.
- **No non-physics joins by default.** Joining a critical net's nearby pads (`complete_mm`) and its islands (`island_mm`) is class-width copper with no physics. These joins were a workaround for the invisible joins above. With joins visible, the bipolar supply and suzyqboard are clean without them. They stay available as options, and `soft` writes them unlocked so Freerouting may keep or rip them.
- **Other nets' pins keep an escape.** Before a hop is committed, nearby unrouted pins of other nets must still reach the edge of a 3.5 mm window or a via site, keeping a quarter of their room. If not, the hop is retried with a keep-out around them. An optional hop is dropped instead.
- **Ground pours stay whole.** Crossing a ground pour costs 3× a foreign pour in the search. After routing, every ground fill piece cut off on its layer gets stitching vias into the same net's fill on another layer, legal and ≥ 2 mm apart. This applies to pieces that hold ground pads and are tied by fewer than 3 barrels.

### The router: grid search with exact verification

`GridRouter.connect(net, sources, targets, width, layers)` ([critical_grid.py](../../../kae/src/kae/route/critical_grid.py)):

1. **Raster.** One grid per layer at 0.05 mm (coarsened above 1.5 M cells). A cell is blocked when a track centred there would come closer to an obstacle than R = w/2 + KiCad's requirement, plus a margin m = √(R² + res²/2) − R. With that margin, every move between free neighbours is legal; m is 2 µm at R = 0.3 mm.
2. **Costs.** Crossing a foreign pour costs 0.4 per cell, a ground pour 1.2. A 0.4 mm halo around other nets' pads costs 0.6. A via costs 1.5 cells, or 3–5 for rails and fallbacks.
3. **Search.** A* over 8 neighbours with an octile heuristic, numba-compiled, through vias where one fits on every layer ([critical_kernels.py](../../../kae/src/kae/route/critical_kernels.py)).
4. **Geometry.** The cell path becomes polylines. Their ends move onto pad centres where legal, and the lines are string-pulled. Every segment and via is checked again with exact distances, 2 µm above each requirement. A failing route is refused.

**Rules** come from the bridge's rule engine and are never re-derived ([critical_space.py](../../../kae/src/kae/route/critical_space.py)):
- track widths per net and layer;
- via size, drill and same-net pitch;
- clearances per net pair and layer, and each pad's clearance class;
- edge clearance, hole-to-hole distance, thermal-spoke corridors, rule areas.

The task's `.kicad_dru` must sit beside the board for DRC, or custom drill and edge rules read as errors.

### Physics on routed copper

**Loops** ([critical_physics.py](../../../kae/src/kae/route/critical_physics.py)). A loop is a chain of strips at height h above the reference plane plus vertical pieces (vias, part terminations). It is evaluated with the place terms' closed forms (`kae.physics.fastloop`), which agree with PEEC within 5 % ([place-terms § 2](../physics/place-terms.md)). Where the current has alternatives (a surface ground track, the vias at each end of a return), the split minimizes stored energy under Kirchhoff's law (a small KKT system). P is clipped to positive definite, and an active set forbids reverse current. A strip with no plane under it is free-space copper.

**One objective with the placer.** Each module's allocation is its `place_terms.Terms` structure (same id):
- **Decap.** A spec splits into pin clusters (`id#k`), or for `nearest_pin` into one structure per capacitor (`id#ref`). Each cluster carries a calibrated per-pin budget and a careful-layout clamp. `decap_spend` prices the routed loops per structure: a cluster's caps in parallel, each at its mean loop to the cluster's pins. The worst u counts.
- **Cell.** The loops through every input cap with calibrated ownership ≥ half the best count in parallel, as in `build._commutation`.
- **Crystal and surge path.** These follow `CrystalComp` (the /4) and `EsdComp` (the via to the plane under the protector).
- **Without Terms.** The E5 priors apply, per pin.

**DC.** A track has R = ρl/(wt) and a via barrel R = ρh/(π(d + t_p)t_p). Widths come from three rules ([power-copper § 3](../physics/power-copper.md)):
- IPC-2221: 1 A needs 0.30 mm and 5 A 2.77 mm on 35 µm copper;
- the drop budget, w ≥ ρlI/(tΔV);
- the feed width: a ≥ 0.25 A branch is as wide as its narrower pad, up to 3 mm.

### Currents: the E5 priors

When the brief carries no currents, part classes give them. These are E5 priors, not datasheet values ([critical_rails.py](../../../kae/src/kae/route/critical_rails.py)):

| Part class | Load current (A) | As a source (A) |
|---|---|---|
| Connector | rating by family | barrel jack 5, USB-C 3, micro/mini USB 1.8, USB A/B 1.5, terminal block 10, XT30/60 15, JST VH / Mini-Fit 5, XH 3, PH 2, SH/GH 1, pin header 3; unknown: 5 if drill ≥ 1 mm, else 1 |
| IC (supply pins only) | FPGA 1.0, motor driver 1.5, PMIC 1.0, audio amp 0.5, load switch 0.5, LDO 0.3, PHY 0.15, RF 0.12, memory 0.05, interface 0.03, logic 0.01, sensor 0.005; MCU by pin count | LDO by package 0.3–1.5, switcher 1, module 0.3 |
| Converter input | V_out·I_out/(0.88·V_in) | cell current from the brief |
| Others | module 0.35, LED 0.02, FET 0.5, BJT 0.1, relay 0.08, resistor V/R ≤ 0.05 | inductor 0.6 × rating |

A rail's design current is min(source rating, max(3Σ, Σ + 0.1 A)). The drop budget is 2 % of the rail voltage, split between rail and ground (1.6 % to the rail when the return is a pour). On the bipolar supply the ±rails come out 1.7 mm wide at ≈ 12 mΩ; the human board has 11 mΩ and Freerouting alone 93–96 mΩ [C].

### Guards, recheck and re-tweak

**Guard pours.** For each routed cell, power path and crystal, a zone named `kae-crit:<module>` covers the ground plane under the module. It is the hull of the module's copper and terminals plus 0.5 mm, clipped to the plane's zone and cut into hole-free pieces one priority above the layer's zones. The bridge treats its fill as a hard obstacle for other nets. The output never carries guards.

**Board physics** ([critical_recheck.py](../../../kae/src/kae/route/critical_recheck.py)) measures any finished board, whoever routed it:
- each net's copper is a graph of pads, track ends split at T-junctions, vias and refilled zone regions;
- a hop follows its least L′-weighted path;
- a strip's reference is the nearest layer with refilled copper under it;
- cells also report **plane cover**, the share of the loop's hull covered by ground fill.

**Recheck** compares each routed module with its value at the module stage (its critical copper alone). It flags the module when u grew by > 15 %, crossed 1, or plane cover fell by > 0.10.

**Re-tweak** (`--rounds N`, default 0) rips the nets that cross the flagged module's region, at most the 4 shortest, whole. It guards the plane and lets the bridge re-route them. A round is kept only if unconnected items and errors do not rise and the flagged modules improve. Rip-ups have not paid. On sk-tibia, 2 boards were flagged and no round was kept. On paw3395, round 1 restored a decap from u 0.83 to 0.53 but raised unconnected items from 3 to 7 [C].

### Joint module optimization and the joint loop

`optimize_modules(board, brief, terms=None, locked=(), …, session=None, window=None, modules=None) -> (poses, copper, report)` ([critical_joint.py](../../../kae/src/kae/route/critical_joint.py)):
- **What moves.** Parts that are not locked, not shared with another module, and not connectors. Heatsink-tab packages keep right angles.
- **Candidates.** Translations of 0.25–2 mm, rotations of 15–345°, and the aligned pose (terminals facing their partners).
- **Legality, exact at any angle.** Courtyards with KiCad's 5 µm deflation, pad clearances, committed copper, the outline and rule areas.
- **Judging.** Candidates are screened by `terms.delta`. The best 6 are routed and quoted, and a move is kept when the module's u falls by > 1 %.
- **Scoping.** `window` (geometry or bounds) and `modules` scope the work. `board_physics`, `recheck`, `stage_values` and `modules_to_retweak` take the same `window`, so the joint loop can re-place and re-route locally.

On 12 human placements (120 s each, 0 DRC errors): hot loops changed on 7 of 8 converters, median −4 %, up to −26 %. Decoupling loops changed in 19 structures, median −9 %, up to −61 % [C].

### Validation

| Check | Boards | Result [C] |
|---|---|---|
| DRC errors on critical copper, KiCad 10.0.7, with the task's `.kicad_dru` | 33 A+B, 6 C | 0 attributable |
| A/B on sk-tibia (k = 1, 600 s A+B / 900 s C6), bridge alone vs critical + bridge, earlier stage | 33 A+B | cp1 0.606 vs 0.576; completion 0.956 vs 0.943; 0 errors both. Physics vs bridge alone: decaps 0.71 (12 better, 3 worse), chains 0.71, rail R 0.97; vs human: decaps 0.87, rail R 0.95 |
| Same | 6 C | complete 2/6 vs 0/6; completion 0.891 vs 0.854; decaps 0.84, rail R 0.72, cells 1.05; 11 new ground islands on 5 boards (before stitching) |
| Inner-plane foreign track | 6 C | critical copper puts 0 mm on inner layers. The bridge routing around it puts 872 mm there, against 473 mm for the bridge alone and 282 mm on the human boards |
| Local A/B, earlier stage, 10 boards (k = 1, 600 s) | 10 | bridge alone 9 clean; critical + bridge 7. Losses traced to invisible joins (lambdakb), a class-width rail (suzyqboard) and an island join (noisecard) |
| Critical stage runtime | 39 | 0.4–60 s per board, one shared core |
| Unit tests | synthetic converter, MCU, crystal, TVS | 51 KiCad-free and 5 KiCad tests, a regression test per bug fixed |

`tools/research/routing/run_crit_v3.sh` runs the A/B (k = 3), the re-tweak arm, `crit_compare.py` and the passports.

## Recommendations for our system

1. **Route physics first; let one engine judge legality and one objective judge physics.** Exact checks against the shared rule port keep critical copper DRC-clean. Pricing against `place_terms` keeps placer, router and recheck in agreement.
2. **Lock only copper that buys physics, and make every join visible to the router.** Trim widths, leave class-width rails and joins to the router, and end on centres and corners.
3. **Protect planes rather than repair them.** Guards and stitching cost less than rip-up, which has not paid yet.

## Conflicts and open questions

- **DSN rounding** is fixed in `translate`. The bridge's repair rounds re-export routed boards, so bridge-alone runs should gain as well; the k = 3 A/B measures both.
- **Routability vs physics** needs the k = 3 A/B. At k = 1 a one-board difference is within Freerouting's noise.
- **Estimator vs passport.** The routed-copper estimator ranks layouts; the rb HF passport decides absolute values (olimex human board: 10.97 vs 6.4 nH).
- **Re-tweak** needs a cheaper form than rip-up: a pre-route reservation (decap guards), or local re-placement through the joint loop.

## Sources

- Code: [kae/src/kae/route/critical.py](../../../kae/src/kae/route/critical.py) and the `critical_*.py` modules beside it; tests [kae/tests/test_route_critical.py](../../../kae/tests/test_route_critical.py), [kae/tests/test_route_critical_kicad.py](../../../kae/tests/test_route_critical_kicad.py).
- Tools: [tools/research/routing/run_crit_v3.sh](../../../tools/research/routing/run_crit_v3.sh), [tools/research/physics/crit_compare.py](../../../tools/research/physics/crit_compare.py), [tools/research/physics/suite_physics.py](../../../tools/research/physics/suite_physics.py).
- Physics: [place-terms](../physics/place-terms.md), [power-copper](../physics/power-copper.md), [pdn-and-commutation](../physics/pdn-and-commutation.md), [real-board-passports](../physics/real-board-passports.md); IPC-2221 as in [rules/power/high-current](../rules/power/high-current.md).

See also: [freerouting-constraint-bridge](freerouting-constraint-bridge.md), [joint-place-route](../physics/joint-place-route.md), [month-plan § The joint loop](../architecture/month-plan.md).
