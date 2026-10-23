# Critical-net routing: the decisive copper first, at its physical optimum

**TL;DR**
- A few connections decide a board's physics: the commutation loop of a converter, decoupling loops, crystal nets, the surge path ahead of a protector and high-current rails. `kae.route.critical` routes them first on the placed board, at the geometry the physics wants, and locks them. The Freerouting bridge then routes everything else around them, as fixed wiring it never rips up.
- Each connection is drawn by a grid A* search and verified exactly against KiCad's effective constraints (`kae.route.effective`, the bridge's rule port). Every candidate is judged on routed copper: the loop inductance of the actual segments with plane images and the current split between parallel vias, the copper resistance against a drop budget, and the trace capacitance under a crystal.
- Guard pours (`kae-crit:` zones) keep other nets off the ground plane under hot loops and crystals while the bridge runs. A recheck on the finished board recomputes every module, including how much of its plane survived; modules that lost more than 15 % of budget or 10 % of plane cover are re-tweaked in up to three rounds.
- On the 33 boards of splits A and B and on 6 C boards with converters, the critical copper adds **0 KiCad DRC errors** and takes 0.3–21 s per board [C]. The A/B comparison against the bridge alone (completion, cp1, cpk, physics) is set up but not yet run on the big host.
- `optimize_modules` moves a module's parts (any angle; right angles for heatsink tabs) while routing its copper and judges every move on the routed physics. On human placements it lowered the hot loop of two converters by 5–11 % and a decoupling loop by 6 % with zero DRC errors [C].

## Key facts

### What is routed, and how

Modules come from the physics brief (`kae.circuit.brief`) and are routed in brief priority order. Rails follow ([critical_modules.py](../../../kae/src/kae/route/critical_modules.py), [critical_rails.py](../../../kae/src/kae/route/critical_rails.py)).

| Module | Copper drawn | Objective and rule |
|---|---|---|
| Commutation cell (buck, boost, half bridge) | Every board hop of the hot loop (input cap → switch → return), forward hops first. Return vias to the plane. | Loop L. Each hop is as wide as its terminals allow (the extent of the pad across the hop direction) and never below IPC-2221 for the cell current. It runs on the layer next to the cell's reference plane. The switch-node hop is drawn at class width. A ground hop that can only return over its own plane, and is longer than 1.5× the straight distance + 1 mm, is not drawn: the plane carries it. |
| Return and stitching vias | Up to 4 vias (more for ≥2 A) at the cap's and the switch's ground pads | 24 directions × 4 gaps give candidate sites. The best pair comes from a 6 × 6 search on the routed loop L. More vias are added while each still lowers L by ≥ 2 %. |
| Decoupling | Cap rail pad → IC power pin, the cap's and the IC's ground into the plane | Loop L per power pin, with parallel caps combined. A through via joins a cap on the far side of the IC. A cap more than 10 mm from its pin is not local decoupling and is left to the bridge. |
| Crystal | IC pin → crystal → load caps on both nets, then the load caps' ground vias | Pulling = S·C′·ℓ (ppm). The IC-to-crystal hops of both nets go first, so neither detours around the other. |
| Protection chain | Connector → protector → protected part, in that order. The protector's ground via. | The surge path ahead of the protector: L′(w, h)·ℓ plus the via. A protector hanging off the line is inserted right after the connector. Power lines are drawn at their E5 current width. |
| Power rail | Trunk to the farthest load, then a branch per load. Vias into rail and ground zones. | DC drop. Zones are used first. A track is drawn only where the E5 current needs more than the class width (`rails="auto"`). |

Differential pairs and high-speed buses are left to the bridge, which carries their coupling rules ([diff-pair-routing](diff-pair-routing.md)).

### The router: grid search with exact verification

`GridRouter.connect(net, sources, targets, width, layers)` ([critical_grid.py](../../../kae/src/kae/route/critical_grid.py)):

1. **Raster.** One grid per allowed layer at 0.05 mm, coarsened by 1.25× steps above 1.5 M cells, inside a window around the anchors. A cell is blocked when a track centred there would come closer to an obstacle than R = w/2 + KiCad's requirement for that pair. An extra margin m = √(R² + res²/2) − R makes the straight move between two free neighbouring cells legal too. A point at R + m or more from both ends of a move of length L = res·√2 is at least √((R+m)² − L²/4) = R from all of it. For R = 0.3 mm, m is 2 µm. A flat 0.71-cell margin (35 µm) would close the 0.2 mm gaps between 0.5 mm-pitch pins: before the change, 12 decoupling and 2 protection hops on QFP and opposite-side parts failed, and after it they route [C].
2. **Costs.** Free cells cost their layer factor. Crossing another net's pour adds 0.4 (the cut costs that pour). A 0.4 mm halo around other nets' pads adds 0.6, which keeps their escape space. A via costs 1.5 cells, or 3–5 for rails and fallbacks.
3. **Search.** A* (8-connected, octile heuristic; numba-compiled, with a pure-Python fallback) runs from source cells to target cells through vias where a via of the net fits on every layer ([critical_kernels.py](../../../kae/src/kae/route/critical_kernels.py)). A diagonal move needs both of its orthogonal neighbours free.
4. **Geometry.** The cell path becomes one polyline per layer. Its ends move onto the pad centres when that piece is legal, then it is string-pulled: each shortcut is kept only if the exact check passes. Every segment and via is then checked once more with shapely distances, 2 µm above each requirement. A route that fails is refused, never committed.

**Rules.** Every requirement comes from the bridge's rule engine, never re-derived ([critical_space.py](../../../kae/src/kae/route/critical_space.py)):
- track width min/opt/max per net and layer;
- via size and drill, and same-net via pitch;
- track-track, track-via and via-via clearance per net pair and layer;
- each pad's clearance class from `constraints.plan` (relative to the pad shape the DSN carries);
- edge clearance, the via edge band, hole-to-hole, thermal-spoke corridors, rule areas;
- via-in-pad only on thermal pads (> 4 mm², > 1.5 mm wide) or when the option allows it.

Committed copper is written locked. The bridge sends locked items to Freerouting as `(type fix)`, and its repair loop never touches them ([freerouting-constraint-bridge](freerouting-constraint-bridge.md)).

### Physics on routed copper

**Loops** ([critical_physics.py](../../../kae/src/kae/route/critical_physics.py)). A loop is a chain of strips (x0, y0, x1, y1, w, h) at height h above the reference plane and vertical pieces (vias, part terminations). It is evaluated with the place terms' closed forms (`kae.physics.fastloop`: partial inductances with plane images, Hammerstad–Jensen strip self terms). These are within 5 % of PEEC on routed loops ([place-terms § 2](../physics/place-terms.md)). Inside a part the current runs as a strip at the body height.

Where the current has alternatives, the loop is a network of elements with currents x_e. Examples are the surface ground track and the vias at each end of the return. The series part carries 1, and the alternatives obey Kirchhoff's current law. The split minimizes the stored energy xᵀPx under those constraints, a small KKT system. For one pair of alternatives it reduces to L(x) = P_AA + 2x·P_AB + 2(1−x)·P_AC + x²P_BB + (1−x)²P_CC + 2x(1−x)·P_BC. A second via pair 0.7 mm from the first lowers a test loop from 1.080 to 1.064 nH and takes 21 % of the current [C: `test_route_critical.py`]. A strip with no plane under it, in a loop that has one, is evaluated at 2× the loop's highest strip (at least 3.2 mm), so a missing plane costs inductance.

**Allocations** are the place terms' ([place-terms § 1](../physics/place-terms.md)):
- hot loop: the overshoot budget L_max = σ²/(2C_oss·ln(1/a′));
- decap: n·Z_t/(2π·100 MHz), with Z_t = 5 % of V over the pin-count current;
- crystal: 5 ppm;
- surge path: 5.3 nH.

Each module reports u = value/allocation.

**DC.** A track has R = ρl/(wt) and a via barrel R = ρh/(π(d + t_p)t_p) with t_p = 20 µm, as in the DC passports. Widths come from:
- IPC-2221, I = k·ΔT^0.44·A^0.725 with k = 0.048 external and 0.024 internal, at ΔT = 10 K: 1 A needs 0.30 mm and 5 A needs 2.77 mm on 35 µm copper;
- the drop budget, w ≥ ρlI/(tΔV);
- the feed width: a branch carrying ≥ 0.25 A is at least as wide as its narrower pad, up to 3 mm ([power-copper § 3](../physics/power-copper.md)).

### Currents: the E5 priors

The brief names rails, sources and loads. When it carries no currents, part classes give them (E5: a documented prior, not a datasheet value) ([critical_rails.py](../../../kae/src/kae/route/critical_rails.py)):

| Part class | Load current (A) | As a source (A) |
|---|---|---|
| Connector | rating by family | barrel jack 5, USB-C 3, micro/mini USB 1.8, USB A/B 1.5, terminal block 10, XT30/60 15, JST VH / Mini-Fit 5, XH 3, PH 2, SH/GH/Qwiic 1, pin header 3, battery 1; unknown: 5 if drill ≥ 1 mm, else 1 |
| IC, through its supply pins only (never FB, EN, sense) | FPGA 1.0, motor driver 1.5, PMIC/charger/regulator module 1.0, audio amp 0.5, load switch 0.5, linear regulator 0.3, PHY 0.15, RF 0.12, memory 0.05, gate driver 0.05, charge pump 0.05, interface 0.03, logic and ADC/DAC 0.01, sensor and op-amp 0.005, current sense 0.002, reference 0.001; MCU by pin count (place-terms prior) | linear regulator by package 0.3–1.5, switcher 1, module 0.3 |
| Converter input | V_out·I_out/(0.88·V_in) | cell current from the brief |
| Others | module 0.35 (radio 0.2), LED 0.02 (power LED 0.06), FET 0.5, BJT 0.1, relay 0.08, resistor V/R ≤ 0.05 | inductor 0.6 × its rating |

The design current of a rail is min(source rating, max(3Σ, Σ + 0.1 A)): the sum of its loads with a 3× margin for the prior's uncertainty, capped by what the source can deliver. Each branch carries its own load's current. The drop budget is 2 % of the rail voltage at the design current, split 1 % rail and 1 % ground, or 1.6 % rail when the return is a pour. On the 12 V / 5 A breakout this draws a 2.77 mm trunk (6.6 mΩ) with 1.7 mm branches. On the bipolar supply the ±rails come out 1.7 mm and ≈ 12 mΩ against 11 mΩ on the human board and 93–96 mΩ from Freerouting alone [C].

### Guards, recheck and re-tweak

**Guard pours.** For every routed cell and crystal, a zone named `kae-crit:<module>` covers the ground plane layer under the module. Its outline is the hull of the module's copper and terminals plus 0.5 mm, clipped to the plane's own zone outline. The bridge treats its fill as a hard obstacle for other nets, so no foreign track or via perforates the plane under a hot loop. The output never carries a guard: the transplant onto the input keeps tracks and vias only. Typical guards are 20–25 mm² on a 2-layer board and up to 150 mm² on an inner plane [C].

**Board physics** ([critical_recheck.py](../../../kae/src/kae/route/critical_recheck.py)) measures any finished board, whoever routed it:
- Each net's copper is read as a graph: pads, track end points split at T-junctions, vias, and refilled zone regions joined through the pour.
- A hop follows its least L′-weighted path, as the HF current does.
- Each strip's reference is the nearest layer whose refilled copper (any net) lies under it.
- Cells also report **plane cover**: the share of the loop's hull covered by ground fill, out of the part inside the ground zone outlines. A foreign track that slices the plane under the loop shows up there even where the strips still see copper.

**Recheck** flags a module when, against its value at the module stage (its critical copper alone):
- u grew by more than 15 %;
- u crossed 1;
- or plane cover fell by more than 0.10.

**Re-tweak**, for each flagged module, in up to 3 rounds:
1. Rip up the unlocked copper of other nets inside its region, on its plane layers and its own layer.
2. Lock everything else and add guard pours over the region.
3. Let the bridge re-route what was ripped.
4. Score with KiCad DRC. The round is kept only if errors + unconnected do not rise and the flagged modules improve (u down or cover up).

The module's own copper stays: it was optimal at the module stage, and what worsened it is its neighbours. Each round logs u and cover before and after, errors and unconnected items.

### Joint module optimization

`optimize_modules(board, brief, terms, locked) -> (poses, copper, report)` ([critical_joint.py](../../../kae/src/kae/route/critical_joint.py)):

**Movable parts:**
- not task-locked or in `locked` (parts on a described heatsink);
- not shared with another routed module;
- not connectors or mounting holes.

**Heatsink tabs.** TO-220, TO-247, TO-3P, TO-218, TO-264 and TO-126 packages with a drilled tab keep 0/90/180/270°.

**Candidates:**
- translations of 0.25–2 mm in 8 directions;
- rotations of 15–345°;
- the aligned pose: a two-terminal part turned so its pads face their partners, then slid toward them.

**Legality** is exact at any angle:
- courtyards from `kae.board.transform.courtyard` with KiCad's 5 µm deflation, on both sides, never boxes;
- pad-to-pad clearance at each pad's own KiCad clearance;
- clearance to committed copper and other nets' thermal corridors;
- outline at edge clearance, rule areas.

**Judging.** Candidates are screened with `terms.delta` when given. The best 6 are routed and quoted, and a move is kept when the routed value falls by more than 1 %.

On human placements [C]:
- noisecard: hot loop 2.41 → 2.15 nH; the microphone's decoupling loop 5.40 → 5.07 nH;
- olimex DC-DC: hot loop 7.83 → 7.42 nH;
- KiCad DRC: 0 errors on both written boards (`write_joint`: KiCad's own writer for any angle).

### Validation so far

| Check | Boards | Result [C] |
|---|---|---|
| DRC errors attributable to critical copper (uuid of a locked item in a violation), critical copper alone, KiCad 10.0.7 | 33 (A+B) | 0; 288 tracks, 47 vias; 25 modules routed, 12 skipped (decap pairs > 10 mm, left to the bridge) |
| Same | 6 C boards with cells (BLDC power stage, BMS, doorman, CAN processor, Oasis, Aftonsparv) | 0; 45 modules routed, 9 skipped (same reason) |
| Runtime, critical stage | 39 | 0.3–21 s per board on one shared core |
| Hot loop, olimex DC-DC, routed-copper estimator | 1 | human 10.97 nH (u 1.19); critical + bridge 6.86 nH (u 0.74). The rb HF passport of the human board gives 6.4–6.5 nH: the estimator overstates the human loop, so the ratio, not the absolute value, is the claim |
| Unit tests | synthetic 2-layer converter, MCU, crystal, TVS | 17 KiCad-free and 2 KiCad tests: routed copper exactly legal, loop physics equals fastloop, KCL split, guards, perforation flag |

How to compare arms: `tools/research/physics/crit_compare.py` puts the human board, the bridge alone and critical + bridge side by side per module and rail. `suite_physics.py --compare-to` gives the independent rb HF loop and DC R_eff and worst drop per amp.

## Recommendations for our system

1. **Route physics first, and let one engine judge legality.** Routing the decisive copper before the general router costs seconds. Exact verification against the shared rule port keeps it free of DRC errors, so it can never be the reason a board fails.
2. **Judge moves on routed copper.** Straight-hop estimates miss the detours and vias that decide a loop. The routed quote costs milliseconds per hop.
3. **Protect planes, don't just measure them.** Guard pours during general routing are cheaper than ripping up afterwards. The recheck's plane cover catches what still gets through.
4. **Keep currents honest.** E5 priors with a 3× margin and a source cap size rails sensibly. A brief that states currents overrides them, and the DC passport is the check.

## Conflicts and open questions

- **Routability.** Locked copper and guards take space the bridge would have used, and only the A/B run (bridge alone vs critical + bridge, same snapshot, k = 1, 600 s) can show whether completion or clean passes fall. Early local runs were mixed: noisecard became clean, and a trackball board kept 2 unconnected items that the bridge alone completes.
- **Estimator vs passport.** The routed-copper estimator ranks layouts. Its absolute values differ from the rb HF passport (olimex: 10.97 vs 6.4 nH). A pour-heavy loop is identical on every board that shares the pours: noisecard's hot loop reads 1.98 nH on human and critical boards alike. The passports decide.
- **fastloop** returns NaN for a loop that mixes h = ∞ with finite heights (`abs(hj − hk)` when only hk is infinite). `critical_physics.Loop` works around it; the fix belongs in `kae.physics.fastloop`.
- **Decap pairing.** The brief pairs some caps with pins 11–70 mm away. They are skipped as doubtful, which is right for the router but means the brief's pin-to-cap map needs a distance check.
- **Re-tweak rounds** have run end to end on single boards only. How often round 2 triggers, how much it recovers and how fast it converges need the big-host run with `--rounds 3`.

## Sources

- Code: [kae/src/kae/route/critical.py](../../../kae/src/kae/route/critical.py) and the `critical_*.py` modules beside it; tests [kae/tests/test_route_critical.py](../../../kae/tests/test_route_critical.py), [kae/tests/test_route_critical_kicad.py](../../../kae/tests/test_route_critical_kicad.py).
- Comparison tool: [tools/research/physics/crit_compare.py](../../../tools/research/physics/crit_compare.py); passports: [tools/research/physics/suite_physics.py](../../../tools/research/physics/suite_physics.py).
- Physics: [place-terms](../physics/place-terms.md) (allocations, loop estimator, PEEC validation), [power-copper](../physics/power-copper.md) (feed width, trace vs pour), [pdn-and-commutation](../physics/pdn-and-commutation.md), [real-board-passports](../physics/real-board-passports.md).
- IPC-2221 current-capacity chart as used in [rules/power/high-current](../rules/power/high-current.md).

See also: [freerouting-constraint-bridge](freerouting-constraint-bridge.md), [joint-place-route](../physics/joint-place-route.md), [month-plan § The joint loop](../architecture/month-plan.md).
