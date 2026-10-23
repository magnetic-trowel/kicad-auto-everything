# Critical-net routing: the decisive copper first, at its physical optimum

**TL;DR**
- A few connections decide a board's physics: a converter's commutation loop, decoupling loops, crystal nets, the surge path ahead of a protector, and high-current rails. `kae.route.critical` routes them first on the placed board, at the geometry the physics wants, and locks them. The Freerouting bridge then routes everything else around them as fixed wiring.
- Each connection is drawn by a grid A* search and verified exactly against KiCad's effective constraints (`kae.route.effective`, the bridge's rule port). Candidates are judged on routed copper:
  - the loop inductance of the actual segments, with plane images and the current split between parallel vias;
  - the copper resistance against a drop budget;
  - the trace capacitance under a crystal.
- Guard pours (`kae-crit:` zones) keep other nets off the ground plane under hot loops and crystals while the bridge runs. A recheck recomputes every module on the finished board, including how much of its plane survived. Modules that lost more than 15 % of budget or 10 % of plane cover are re-tweaked, for up to three rounds.
- On the 33 boards of splits A and B and on 6 C boards with converters, the critical copper adds **0 KiCad DRC errors** and takes 0.4–18 s per board [C]. The A/B run against the bridge alone (completion, cp1, cpk, physics) is set up. On four local boards the critical stage helped two, matched one and hurt one.
- `optimize_modules` moves a module's parts (any angle; right angles for heatsink tabs) while routing its copper. On 12 human placements it lowered converter hot loops by a median 4 % (up to 26 %) and decoupling loops by a median 9 % (up to 61 %), with 0 DRC errors [C].

## Key facts

### What is routed, and how

Modules come from the physics brief (`kae.circuit.brief`) and are routed in brief priority order; rails follow ([critical_modules.py](../../../kae/src/kae/route/critical_modules.py), [critical_rails.py](../../../kae/src/kae/route/critical_rails.py)).

| Module | Copper drawn | Objective and rule |
|---|---|---|
| Commutation cell (buck, boost, half bridge) | Every board hop of the hot loop (input cap → switch → return), forward hops first; return vias | Loop L. Each hop is as wide as its terminals allow (the pad's extent across the hop), never below IPC-2221 for the cell current, on the layer next to the reference plane. The switch-node hop stays at class width. A ground hop longer than 1.5× the straight distance + 1 mm is not drawn; the plane carries it. |
| Return and stitching vias | Up to 4 vias (more for ≥ 2 A) at the cap's and the switch's ground pads | Candidate sites: 24 directions × 4 gaps. The best pair comes from a 6 × 6 search on the routed loop L; vias are added while each lowers L by ≥ 2 %. |
| Decoupling | Cap rail pad → IC power pin; cap ground and IC ground into the plane | Loop L per power pin, parallel caps combined. A cap on the far side of the IC is joined through a via, and the IC ground pin gets a via into the pour the cap sits in. A cap more than 10 mm from its pin is not local decoupling; the bridge routes it. |
| Crystal | IC pin → crystal → load caps on both nets; load-cap ground vias | Pulling = S·C′·ℓ (ppm). Both nets' IC-to-crystal hops go first, so neither detours around the other. |
| Protection chain | Connector → protector → protected part, in that order; the protector's ground via | Surge path ahead of the protector: L′(w, h)·ℓ plus the via. A protector hanging off the line is inserted after the connector. Power lines get their E5 current width. `chain_tail=False` leaves the hops after the protector to the bridge. |
| Power rail | Trunk to the farthest load, a branch per load; vias into rail and ground zones | DC drop, zones first. Tracks only where the E5 current needs more than the class width (`rails="auto"`). |

Differential pairs and high-speed buses are left to the bridge, which carries their coupling rules ([diff-pair-routing](diff-pair-routing.md)).

### The router: grid search with exact verification

`GridRouter.connect(net, sources, targets, width, layers)` ([critical_grid.py](../../../kae/src/kae/route/critical_grid.py)):

1. **Raster.** One grid per allowed layer at 0.05 mm (coarsened in 1.25× steps above 1.5 M cells), in a window around the anchors. A cell is blocked when a track centred there would come closer to an obstacle than R = w/2 + KiCad's requirement for that pair, plus a margin m = √(R² + res²/2) − R. A point at R + m or more from both ends of a move of length L = res·√2 is at least √((R+m)² − L²/4) = R from all of it, so every move between free neighbours is legal. For R = 0.3 mm, m is 2 µm. A flat 0.71-cell margin (35 µm) closes 0.5 mm-pitch escapes (an LQFP-100's VCAP hops) [C].
2. **Costs.** Crossing another net's pour adds 0.4 per cell (the cut costs that pour); a 0.4 mm halo around other nets' pads adds 0.6 (their escape space); a via costs 1.5 cells, 3–5 for rails and fallbacks.
3. **Search.** A* (8-connected, octile heuristic, numba-compiled with a Python fallback) from source to target cells, through vias where one fits on every layer ([critical_kernels.py](../../../kae/src/kae/route/critical_kernels.py)). A diagonal move needs both orthogonal neighbours free.
4. **Geometry.** The cell path becomes one polyline per layer, its ends move onto the pad centres where legal, and it is string-pulled, keeping a shortcut only if the exact check passes. Every segment and via is checked once more with shapely distances, 2 µm above each requirement; a route that fails is refused, never committed. Terminals keep each layer's own copper. A castellated pad (a through-hole pad and an SMD twin under one number) can be reached on the back only at its hole; ending inside the twin there would leave a dangling track.

**Rules** come from the bridge's rule engine, never re-derived ([critical_space.py](../../../kae/src/kae/route/critical_space.py)):
- track width min/opt/max per net and layer; via size, drill and same-net via pitch;
- track-track, track-via and via-via clearance per net pair and layer;
- each pad's clearance class from `constraints.plan`;
- edge clearance, the via edge band, hole-to-hole, thermal-spoke corridors, rule areas;
- via-in-pad only on thermal pads (> 4 mm², > 1.5 mm wide) or when the option allows it.

Committed copper is written locked. The bridge sends it to Freerouting as `(type fix)`, and its repair loop never touches it ([freerouting-constraint-bridge](freerouting-constraint-bridge.md)). Two consequences shape the stage:
- **Other nets' pins keep an escape.** Before a hop is committed, every unrouted single-layer pin of another net within 1.5 mm is checked. The test is whether a class-width track of its net can still reach the edge of a 3.5 mm window or a via site, keeping at least a quarter of the room it had. If not, the hop is retried with a keep-out around that pin. An optional hop (a ground hop over its own plane, a net join) is dropped instead; on the olimex DC-DC that freed the FB pin.
- **Critical nets leave no islands.** Freerouting does not join an island to the middle of a fixed track. So every pad of a critical net within 8 mm of its critical copper is joined at class width (bipolar supply: 1 unconnected → clean).

### Physics on routed copper

**Loops** ([critical_physics.py](../../../kae/src/kae/route/critical_physics.py)). A loop is a chain of strips (x0, y0, x1, y1, w, h) at height h above the reference plane and vertical pieces (vias, part terminations). It is evaluated with the place terms' closed forms (`kae.physics.fastloop`: partial inductances with plane images, Hammerstad–Jensen strip self terms), within 5 % of PEEC on routed loops ([place-terms § 2](../physics/place-terms.md)). Inside a part the current runs as a strip at the body height.

Where the current has alternatives (the surface ground track, the vias at each end of the return), the loop is a network of elements with currents x_e. The series part carries 1; the alternatives obey Kirchhoff's current law. The split minimizes the stored energy xᵀPx, a small KKT system. For one pair of alternatives it reduces to L(x) = P_AA + 2x·P_AB + 2(1−x)·P_AC + x²P_BB + (1−x)²P_CC + 2x(1−x)·P_BC. A second via pair 0.7 mm from the first lowers a test loop from 1.080 to 1.064 nH and takes 21 % of the current [C: `test_route_critical.py`].

Two safeguards keep the network physical:
- P is clipped to positive definite. Closed forms overstate the mutual of wide strips leaving one pad side by side, which once gave −36.7 nH.
- An active set keeps alternatives from carrying reverse current.

A strip with no plane under it is free-space copper, coplanar with the rest of the loop and without an image (fastloop's rule), so a missing plane costs inductance: 3.24 instead of 2.86 nH when one side of a 4 × 2 mm loop loses its plane [C].

**Allocations** are the place terms' ([place-terms § 1](../physics/place-terms.md)): hot loop L_max = σ²/(2C_oss·ln(1/a′)); decap n·Z_t/(2π·100 MHz) with Z_t = 5 % of V over the pin-count current; crystal 5 ppm; surge path 5.3 nH. Each module reports u = value/allocation.

**DC.** A track has R = ρl/(wt); a via barrel R = ρh/(π(d + t_p)t_p) with t_p = 20 µm, as in the DC passports. Widths come from:
- IPC-2221, I = k·ΔT^0.44·A^0.725 (k = 0.048 external, 0.024 internal, ΔT = 10 K): 1 A needs 0.30 mm, 5 A needs 2.77 mm on 35 µm copper;
- the drop budget, w ≥ ρlI/(tΔV);
- the feed width: a branch carrying ≥ 0.25 A is at least as wide as its narrower pad, up to 3 mm ([power-copper § 3](../physics/power-copper.md)).

### Currents: the E5 priors

When the brief carries no currents, part classes give them (E5: a documented prior, not a datasheet value) ([critical_rails.py](../../../kae/src/kae/route/critical_rails.py)):

| Part class | Load current (A) | As a source (A) |
|---|---|---|
| Connector | rating by family | barrel jack 5, USB-C 3, micro/mini USB 1.8, USB A/B 1.5, terminal block 10, XT30/60 15, JST VH / Mini-Fit 5, XH 3, PH 2, SH/GH/Qwiic 1, pin header 3, battery 1; unknown: 5 if drill ≥ 1 mm, else 1 |
| IC, through supply pins only (never FB, EN, sense) | FPGA 1.0, motor driver 1.5, PMIC/charger/regulator module 1.0, audio amp 0.5, load switch 0.5, linear regulator 0.3, PHY 0.15, RF 0.12, memory, gate driver, charge pump 0.05, interface 0.03, logic, ADC/DAC 0.01, sensor, op-amp 0.005, current sense 0.002, reference 0.001; MCU by pin count (place-terms prior) | linear regulator by package 0.3–1.5, switcher 1, module 0.3 |
| Converter input | V_out·I_out/(0.88·V_in) | cell current from the brief |
| Others | module 0.35 (radio 0.2), LED 0.02 (power LED 0.06), FET 0.5, BJT 0.1, relay 0.08, resistor V/R ≤ 0.05 | inductor 0.6 × its rating |

A rail's design current is min(source rating, max(3Σ, Σ + 0.1 A)): its loads with a 3× margin for the prior's uncertainty, capped by what the source can deliver. Each branch carries its own load's current. The drop budget is 2 % of the rail voltage at the design current, split 1 % rail and 1 % ground (1.6 % rail when the return is a pour). On the 12 V / 5 A breakout this draws a 2.77 mm trunk (6.6 mΩ) with 1.7 mm branches. On the bipolar supply the ±rails come out 1.7 mm and ≈ 12 mΩ; the human board has 11 mΩ and Freerouting alone 93–96 mΩ [C].

### Guards, recheck and re-tweak

**Guard pours.** For every routed cell and crystal, a zone named `kae-crit:<module>` covers the ground plane layer under the module:
- its outline is the hull of the module's copper and loop terminals plus 0.5 mm;
- it is clipped to the plane's own zone and kept clear of other nets' zones;
- it is cut into hole-free pieces, one priority above every zone on the layer (KiCad flags equal-priority overlaps as `zones_intersect`, even within one net).

The bridge treats its fill as a hard obstacle for other nets. The output never carries a guard: the transplant onto the input keeps tracks and vias only. Guards are 20–25 mm² on 2-layer boards and up to 150 mm² on inner planes [C].

**Board physics** ([critical_recheck.py](../../../kae/src/kae/route/critical_recheck.py)) measures any finished board, whoever routed it:
- Each net's copper is a graph: pads, track ends split at T-junctions, vias, and refilled zone regions joined through the pour.
- A hop follows its least L′-weighted path, as the HF current does.
- A strip's reference is the nearest layer with refilled copper (any net) under it.
- Cells also report **plane cover**: the share of the loop's hull covered by ground fill, within the ground zone outlines. A foreign track slicing the plane shows there even where strips still see copper.

**Recheck** compares each routed module with its value at the module stage (its critical copper alone). It flags the module when:
- u grew by more than 15 %;
- u crossed 1;
- or plane cover fell by more than 0.10.

**Re-tweak**, up to 3 rounds:
1. Rip up other nets' unlocked copper in the flagged region (plane layers and the module's layer).
2. Lock the rest and add guards.
3. Let the bridge re-route what was ripped.
4. Run KiCad DRC.

A round is kept only if errors + unconnected items do not rise and the flagged modules improve. The module's own copper stays: its neighbours worsened it. Each round logs u, cover, errors and unconnected items.

### Joint module optimization

`optimize_modules(board, brief, terms, locked) -> (poses, copper, report)` ([critical_joint.py](../../../kae/src/kae/route/critical_joint.py)):
- **Movable:** parts not in `locked` (task-locked, or on a described heatsink), not shared with another routed module, not connectors or mounting holes. Heatsink-tab packages (TO-220, TO-247, TO-3P, TO-218, TO-264, TO-126 with a drilled tab) keep 0/90/180/270°.
- **Candidates:**
  - translations of 0.25–2 mm in 8 directions;
  - rotations of 15–345°;
  - the aligned pose: a two-terminal part turned so its pads face their partners, then slid toward them.
- **Legality, exact at any angle:**
  - courtyards from `kae.board.transform.courtyard` with KiCad's 5 µm deflation, on both sides (never boxes);
  - each pad's own clearance;
  - committed copper and other nets' thermal corridors;
  - the outline, rule areas.
- **Judging:** `terms.delta` screens when given. The best 6 are routed and quoted. A move is kept when the routed value falls by more than 1 %, and only positive, finite values count.

On 12 human placements (120 s each; KiCad DRC 0 errors on every written board) [C]:

| Structure | Changed | Median | Largest |
|---|---|---|---|
| Hot loop | 7 of 8 converters | −4 % | −26 % (CAN processor, 3.76 → 2.77 nH) |
| Decoupling loop | 19 | −9 % | −61 % (mouse sensor regulator output, 4.23 → 1.64 nH) |

### Validation so far

| Check | Boards | Result [C] |
|---|---|---|
| DRC errors on a locked critical item, critical copper alone, KiCad 10.0.7 | 33 (A+B) | 0; 298 tracks, 48 vias; 26 modules routed, 11 skipped (decap pairs > 10 mm) |
| Same | 6 C boards with cells (BLDC, BMS, doorman, CAN processor, Oasis, Aftonsparv) | 0; 316 tracks, 107 vias; 46 modules routed, 7 skipped |
| Critical stage runtime | 39 | 0.4–18 s per board, one shared core |
| olimex DC-DC, routed-copper estimator: hot loop C2 → U1 → D2 (u), plane cover, worst V_out drop path | 1 | human 10.97 nH (1.19), 0.85, 17.9 mΩ; bridge alone 9.10 nH (0.98), 0.99, 149 mΩ; critical + bridge (240 s, incomplete) 6.68 nH (0.72), 1.00, 42.6 mΩ |
| Re-tweak, noisecard, guards off | 1 | the bridge cut the cell's plane cover from 1.00 to 0.74 (flagged); round 1 restored it but left 4 unconnected items (99 s of Freerouting) and was discarded |
| Unit tests | synthetic 2-layer converter, MCU, crystal, TVS | 33 KiCad-free and 5 KiCad tests, with a regression test for each bug fixed |

`tools/research/physics/crit_compare.py` compares human, bridge-alone and critical + bridge boards per module and rail and summarizes re-tweak rounds; `suite_physics.py --compare-to` gives the independent rb HF loop and DC passports.

## Recommendations for our system

1. **Route physics first; let one engine judge legality.** It costs seconds, and exact verification against the shared rule port keeps critical copper DRC-clean.
2. **Judge moves on routed copper.** Straight hops miss the detours and vias that decide a loop; a routed quote costs milliseconds per hop.
3. **Protect planes, don't just measure them.** Guards during general routing are cheaper than rip-up afterwards; plane cover catches what still gets through.

## Conflicts and open questions

- **Routability.** Locked copper and guards take space the bridge would have used. Only the A/B run (same snapshot, k = 1, 600 s) can show whether completion or clean passes fall. Four local boards (k = 1, 600 s, loaded VM, against an older bridge-alone run): unconnected items fell from 5 to 1 on noisecard and from 4 to 0 on the XIAO board. The bipolar supply is clean once rails join their nearby pads. The olimex DC-DC kept 2–3 unconnected items even without chain tails or rails, where the bridge alone was clean.
- **Estimator vs passport.** The routed-copper estimator ranks layouts; its absolute values differ from the rb HF passport (olimex human: 10.97 vs 6.4 nH), and a loop closed by pours reads the same on every board sharing them. The passports decide.
- **Decap pairing** in the brief maps some caps to pins 11–70 mm away. The router skips them; the brief needs a distance check.
- **Re-tweak statistics** (how often round 2 triggers, recovery, convergence) need the big-host `--rounds 3` run.

## Sources

- Code: [kae/src/kae/route/critical.py](../../../kae/src/kae/route/critical.py) and the `critical_*.py` modules beside it; tests [kae/tests/test_route_critical.py](../../../kae/tests/test_route_critical.py), [kae/tests/test_route_critical_kicad.py](../../../kae/tests/test_route_critical_kicad.py).
- Tools: [tools/research/physics/crit_compare.py](../../../tools/research/physics/crit_compare.py), [tools/research/physics/suite_physics.py](../../../tools/research/physics/suite_physics.py).
- Physics: [place-terms](../physics/place-terms.md), [power-copper](../physics/power-copper.md), [pdn-and-commutation](../physics/pdn-and-commutation.md), [real-board-passports](../physics/real-board-passports.md); IPC-2221 as in [rules/power/high-current](../rules/power/high-current.md).

See also: [freerouting-constraint-bridge](freerouting-constraint-bridge.md), [joint-place-route](../physics/joint-place-route.md), [month-plan § The joint loop](../architecture/month-plan.md).
