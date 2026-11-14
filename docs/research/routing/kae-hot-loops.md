<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# kae hot loops: closing the gap to expert switching-converter layouts

Scope: hot-loop (commutation-cell) copper: expert practice, kae's shortfall, evaluator fidelity, design options, a pre-registered A/B. Not here: hot-loop rules and membership → [hot-loops](../../topics/rules/power/hot-loops.md); loop physics tables → [pdn-and-commutation § 1](../../topics/physics/pdn-and-commutation.md#1-commutation-loop-geometry); critical router mechanism → [critical-net routing](../../topics/routing/critical-net-routing.md).
Keys: hot loop, commutation cell, loss.loop, loss.loop_ac, loss.swnode, R_loop, L_loop, open cell, cells-first, hot-loop pour, return-via array, reference keep-out, trim_tol, mesh bias, lumped cap body, PowerSynth, hotloop-ab

**Status:** design (no code). **First published:** 2026-11-14, branch `hotloop-research` (off `power-copper-tht` 4392518).

**Results**
1. The default router (bridge + finish) has no hot-loop stage. The gap (loss.loop_ac ≈ 1.8×, loss.loop 1.1–1.3× human) comes from class-width tracks, return detours, layer changes, open hops and foreign tracks on the return layer, not from mesh bias [C].
2. The gap is understated: cells whose copper is open have no value and drop out of the ratio; of the 38 cells with a value on the human layouts of 24 converter boards, 13 have none in arm A and 15 none in arm C; 4 and 7 of them on boards where the arm's other cells have values (open hops, as on nekoink) [C].
3. On bq25306, removing foreign tracks from the return layer under the loop, one cap ground via and a 0.5 mm VIN hop bring arm A from 5.04 nH / 13.1 mΩ to 1.57 nH / 3.65 mΩ (human 1.55 / 3.1) [C].
4. The critical cell module already reached cells 0.85–0.89× human in crit-v6 ([kae-critical-copper](kae-critical-copper.md#results)) but prices L only and narrows copper by `trim_tol`, raising R. Run it for cells only, ahead of the bridge, priced in watts (L and R), with via arrays, a reference keep-out and pours.
5. The evaluator ranks layouts faithfully enough (raster PEEC with solved plane currents; mesh bias moves kae/human ratios by ≤ 0.1 on 7 of 8 boards) but drops open cells and cannot see cap orientation (lumped bodies). Fix both before the A/B.

## What experts do, and why (quantified)

| # | Practice | Number | Source |
|---|---|---|---|
| X1 | Smallest-package ceramic CIN_HF at VIN/PGND pins, same layer, no vias | < 2 mm from the pins | MPS AN065 [P] via [buck](../../topics/rules/power/buck.md) |
| X2 | Solid ground on the next layer, thin dielectric | ground plane +4 dBµV/m margin; cutting it under the high-current path −6 dB; cap placement −3.6 V spike, −28 mV ripple | TI SNVA638 [P] |
| X3 | Vertical loop through L2 | 2 mm² < 0.5 nH vs 20 mm² lateral > 1 nH; ~4 V less overshoot | TI SNVA803 [P] |
| X4 | First inner layer as return ("optimal" loop) | ~65 % below best conventional; L +80 % when board 31 → 62 mil | EPC WP009/WP010 [P] |
| X5 | Wide VIN/PGND copper, minimal SW copper | SW > 2.54 mm "too much capacitive loading" (LM10504); doubling SW length < 1 dB far field | TI [P]; SNVA638 [P] |
| X6 | Many vias, spread, outside the CIN–IC path | ≥ 1 via/A; > 20 between input caps (NB675); 4 vias at 2 mm pitch = 16 at 0.6 mm | SLYT614, AN065 [P]; [pdn § 2](../../topics/physics/pdn-and-commutation.md#2-vias-parallel-count-pitch-and-current-sharing) [C] |
| X7 | Split CIN symmetric about the IC | −6 dB H-field (MPS); field cancellation (Silent Switcher) | [Hedrich, MPS](https://media.monolithicpower.com/mps_cms_document/2/0/2019-aip-pcb-design-for-low-emi-dc-dc-converters_r1.0.pdf) [P]; [ADI](https://www.analog.com/en/resources/analog-dialogue/articles/is-it-possible-to-fit-low-emi-power-supplies-onto-crowded-boards.html) [S] |
| X8 | Alternate orientation of paralleled caps | 0.38–0.46× vs 0.54–0.62× of a single cap | [pdn § 3](../../topics/physics/pdn-and-commutation.md#3-decoupling-capacitors-mounting-orientation-spreading) [C] |
| X9 | Never route foreign nets on the reference layer under the loop | the −6 dB of X2; "it is the interrupted return path" (SW on two layers) | SNVA638 [P] |

Why, in one line each [I, from the cited physics]:
- With a plane within ~0.2 mm, L ≈ Σ μ0·h·l/w per conductor: length, width and h decide, gap barely matters ([pdn § 1](../../topics/physics/pdn-and-commutation.md#1-commutation-loop-geometry)). Experts shorten (X1), widen (X5) and lower h (X2–X4).
- R_loop at f_sw (≤ 3 MHz) is near DC: R ≈ ρl/(wt) + vias; the return gathers under the trace above f_c ≈ 0.6 MHz (h = 0.1 mm), so the hot-loop trace width sets most of R ([power-copper § 5](../../topics/physics/power-copper.md#5-ac-effects)).
- Loss sensitivity: EPC measures > 4 % efficiency for 0.4 → 2.9 nH (12 → 1.2 V, 1 MHz); at an assumed 20 A that is ~0.4 W/nH against ½·L·I²·f's 0.2 W/nH, the rest being slower commutation and overshoot [P, I]. For packaged discrete FETs common-source inductance dominates switching loss (EPC WP009 [P]).
- The stakes on corpus boards are overshoot and EMI, not watts: human loss.loop is 0.008–14 mW on 20 of 21 boards with a value, 117 mW on one (diagnosis run) [C].

## Prior art in automated power-stage layout

| Work | What it optimizes | Model | Relevance |
|---|---|---|---|
| PowerSynth 2 (Sanjabiasasi et al., IEEE OJPEL 2025, [PDF](https://par.nsf.gov/servlets/purl/10595462)) [P] | Manhattan constraint-graph floorplans (HCG/VCG), NSGA-II/MOPSO; modules: loop L + T; converters: efficiency + T | PEEC/FastHenry (modules), loss model (converters, 200 kHz, EMI ignored) | 100 layouts in 100 s generate + 380 s evaluate; open source. Converter loop L not optimized |
| CURENT 2024 conference paper, simulated-annealing switching-loop layout [S, snippet only] | simulated annealing of switches + decaps | rules | same move set as kae's joint modules |
| [Quilter](https://quilter.ai/blog/5-ways-ai-simplifies-power-supply-pcb-layout) [V] | ranks loops by di/dt, minimises area | not published | no data |

No published work routes hot loops inside a general PCB router judged by a field solver [I].

## Where kae falls short

### The default pipeline has no hot-loop router
- Default = Freerouting bridge + last mile + finish (taut, power copper, one DRC gate) ([routing-stages § 7](../../topics/routing/routing-stages.md)). `kae.route.critical` is a separate router; the bridge "never runs" tighten (route-finish-ab `PLAN.md` § 1, branch `origin/route-finish-ab`).
- Power copper widens rails and grounds to ≤ 3 mm `max_width` but never a switch node, adds no pours (`power_copper.py` docstring), and puts one ground via per SMD cap or IC ground pad without a barrel within `via_reach`.
- Route tasks keep the human zones and strip human tracks and vias, so human hot-loop copper that is a track or a via array is what kae must rebuild.

### Measured gap, per cell (diagnosis, 24 boards, evaluator at 0.25 mm) [C]
Data: the parallel diagnosis run (per-cell evaluator terms; hop geometry from `critical_recheck.hop_pieces`; not committed), arms A (legacy) and C (route-finish default) of route-finish-ab against the human layout.

| Measure | A / human | C / human |
|---|---|---|
| Per-cell L_loop, median (cells valued in both) | 1.25 (25 cells; 7 > 1.5×) | 1.31 (23 cells; 10 > 1.5×) |
| Per-cell loss.loop_ac, median | 1.84 | 1.95 |
| Cells with no value (of 38 valued on human): on boards with other values / boards with none (open copper or physics not run, not yet separated) | 4 / 9 | 7 / 8 |

Hop geometry (estimator `hop_pieces`) on the first 10–11 boards read (preliminary) [C]:

| Hop property | human (40 hops) | A (38) | C (38) |
|---|---|---|---|
| open hop | 0 | 3 | 6 |
| contains a strip < 0.3 mm wide | 12 | 20 | 19 |
| contains pour copper | 31 | 28 | 22 |
| ground hop without a via | 7 of 19 | 6 of 18 | 6 of 17 |

Mechanisms, each seen on a named board:
- **M1 class-width hot-loop tracks.** bq25306 VIN hop: human 0.4–0.6 mm, A and C 0.2–0.3 mm over the same 1.8 mm; gecko5 C: ground hop a 9.8 mm, 0.1 mm surface track (human: 3 mm of 0.3–0.5 mm plus 2 vias to the plane). R ∝ 1/w explains most of the loop_ac gap [I].
- **M2 return detours.** bq25306 A: the ground hop runs 22 mm through pours and 12.7 mm on the plane for a 5 mm gap (L 11.0 nH vs C 4.6 nH, human loop 1.55 nH per the evaluator).
- **M3 layer changes inside the loop.** gecko5 C: the VIN hop dives to In4 through 2 vias and 0.1 mm strips (cell L 9.1 nH vs human 5.4 nH by the estimator); experts never change layer in the hot loop (AN-136).
- **M4 open hot-loop hops.** nekoink A and C leave the IPSOUT hop of the buck cells open; the evaluator then reports nothing for those cells.
- Where kae matches human (martinberlin boost, 0.25 vs 0.4 mm tracks, same path), the estimator's L is within 3 %.

**What-if on bq25306 (arm A's board, evaluator at 0.25 mm, one cell)** [C]: the diagnosis run edited A's copper and re-evaluated.

| Edit | L_loop (nH) | R_loop (mΩ) |
|---|---|---|
| A as routed | 5.04 | 13.1 |
| E1: foreign tracks removed from B.Cu (the return layer) under the loop | 2.19 | 5.3 |
| E2: one ground via at the CIN ground pad | 4.66 | 12.9 |
| E4: VIN hop widened 0.2 → 0.5 mm | 4.95 | 11.7 |
| E1 + E2 | 1.67 | 5.0 |
| E1 + E2 + E4 | 1.57 | 3.65 |
| C (route-finish default) / human | 4.06 / 1.55 | 7.5 / 3.1 |

The cut return plane (X9) is the largest single cause on this board; the three edits together reach human. Each edit is one of R5, R4, R2 below.

### What the router's own objective does wrong
1. `quote` prices loop L only; `_return_vias` adds a via only for ≥ 2 % L gain, ≤ 4 vias. DC resistance and ampacity never enter.
2. `trim_widths` narrows each hop to the narrowest width within 5 % of the wide loop's L. Over a close plane L′ falls slower than 1/w, R as 1/w: the lambdakb example 1.41 → 0.98 mm costs +4.5 % L and +44 % R [C, from [topic](../../topics/routing/critical-net-routing.md#keeping-critical-copper-out-of-the-routers-way)].
3. Hops are tracks capped by `rail_max_mm` = 3 mm, and power copper writes zones only above 5 A (`zone_above_a`): the pad-span-wide VIN/PGND pour experts draw at a few amps never appears.
4. Nothing reserves the reference layer under the loop; on 6 C boards the bridge around critical copper put 872 mm of foreign track on inner layers vs 282 mm human ([validation](../../topics/routing/critical-net-routing.md#validation)), the X9 failure.

## Evaluator fidelity

| Question | Answer | Evidence |
|---|---|---|
| 3-D return currents? | Modelled: every copper layer is a raster of x/y bars with `nsub` filaments, vias are barrels, partial inductances by FFT; plane currents are solved, not imaged ([mesh.py](../../../kae/src/kae/em/mesh.py)) | refinement to 0.0625 mm converges (E7) [C]; no lab measurement |
| 0.25 mm mesh bias | Hot loops +5 to +12 % high, from above; narrow (< 3 p = 0.75 mm) tracks under-resolved, so track loops read higher than pour loops ([field-solver-accuracy § 3](../physics/field-solver-accuracy.md#3-mesh-bias-at-025-mm-e7)) | pitch sweep 0.0625–0.25 mm on 8 boards: kae/human loss.loop ratio moves ≤ 0.1 on 7 (bq25306 3.25 → 3.20, powerboost 1.49 → 1.54, max98357 1.64 → 1.52); flips on circuitmonkey (1.24 → 0.91); loop_ac ratios stable [C] |
| Frequency | L at the edge band capped at 10 MHz: return gathered under the trace (f_c = R_s/(2π·μ0·h) ≈ 0.6 MHz at h = 0.1 mm, 35 µm) | [power-copper § 5](../../topics/physics/power-copper.md#5-ac-effects) |
| loop_ac harmonics | fundamental only, I²·D(1−D)·R: a lower bound, same direction for both arms [I] | evaluate.py |
| Cap bodies | lumped branches, no mutual inductance: cap orientation and alternating pairs (X8, 15–40 %) are invisible | mesh.py docstring |
| Open cells | an open loop gives no value, so it leaves the ratio | evaluate.py "copper open … not computed" |
| loss.loop in W | ½·L·I²·f underrates EPC's measured sensitivity ~2×; a per-cell constant, so ratios hold | above |

Verdict [I]: the evaluator's L and R respond to length, width, vias and plane continuity, the levers kae lacks, so optimizing them is real improvement. Before it judges the A/B:
- **E1 open cells count.** Report cells evaluated per arm; an arm's open cell is a loss in the paired table (rank-based test: worst rank), never a dropped row. Separate commit; it makes no score easier.
- **E2 local refinement.** Re-solve each cell's window (hull + 3 mm) at 0.0625 mm (16× cells of a ~10 × 10 mm window, seconds) and report `L_loop`, `R_loop` from it beside the 0.25 mm board solve.
- **E3 cap bodies as bars.** Replace the lumped L of 2-pad caps on cell and decap loops by a bar at body height between the pads (as the router's `Loop.body` in `critical_physics`), so orientation and alternation count. Validate on the [pdn § 3](../../topics/physics/pdn-and-commutation.md#3-decoupling-capacitors-mounting-orientation-spreading) cases.
- Report `overshoot.peak` and `L_loop`/`R_loop` per cell as the hot-loop primaries; watts stay as the cost view.

## Design options

Gain is against the default arm N, per cell, on the converter boards; [I] unless stated.

| Id | Option | Expected gain | Cost | Risk |
|---|---|---|---|---|
| R1 | **Cells first**: run the critical cell module (cells and power paths only, no decaps, rails, chains) before the bridge, soft-locked (`soft_critical`), guards on | L to ~0.85–0.9× human (crit-v6 cells 0.888) [C]; no open hot loops | small: code exists; 0.4–60 s/board | completion: locked copper walled routing in crit-v3; cells are 1–4 per board, so far fewer walls than decaps/rails |
| R2 | **Price watts**: quote = loss.loop + loss.loop_ac with the intent's I, D, f_sw (fallback E5 priors); `trim_tol` judged on watts; via additions on watts | loop_ac 1.8× → ≤ 1.2× human; L unchanged or better | small (quote change, R from `critical_physics.r_track`, `R_via`) | priors wrong for some cells; widening crowds neighbours (guard by escape check, exists) |
| R3 | **Hot-loop pours**: VIN and PGND hops written as zones (score v10 allows added zones) spanning the terminal width (cap pad length to pin group), solid connection; SW stays a track at IPC width | R_loop −30 to −60 % where tracks were 0.25–0.5 mm [I from R ∝ 1/w]; L −10 to −30 % (width term) | medium: zone writer exists (`vector_out="zones"`) | zone priority deadlocks (prepare rule 6), thermal-relief starvation (`starved_thermal`), DRC refill time |
| R4 | **Return-via arrays**: vias at CIN ground and IC PGND/EP spread over the pad span (cluster outer size), count = max(ceil(I), L-optimal), on watts; outside the CIN–IC strip (SLYT614); the KKT split already picks vertical vs surface return (X3) | L −10 to −30 % where only one via exists (pdn § 2: 4 spread vias ≈ 0.51× one) [C]; arm E (ground vias before routing) gave loss.loop 0.71× A, median over 17 terms [C] | small (via_candidates exists) | E arm lost 2 clean boards: place vias inside the critical stage, legality-checked, not as a separate pass |
| R5 | **Reference keep-out**: rule area on the cell's return layer (the ground fill under it, also B.Cu of a 2-layer board), hull + 1 mm, forbidding foreign tracks (not vias) for the bridge; dropped from output like guards | bq25306: L 5.04 → 2.19 nH, R 13.1 → 5.3 mΩ alone [C]; SNVA638's 6 dB class | small | routability: foreign nets lose a few mm² of the return layer per cell; measure completion |
| T1 | **Tighten** (`critical_taut`) on cell copper, guarded by watts | length −2 to −5 % [I from taut −2.7 % copper] | none (exists, off) | small; keep off unless R1–R4 pass |
| J1 | **Joint modules** in joint/place tasks: `optimize_modules` on cells with the watts quote, plus HF-cap choice (which owned cap sits nearest) | median −4 %, up to −26 % on L (12 human placements) [C] | small | joint tasks only: route tasks fix placement |
| P1 | **Placement hand-off** (placement session) | largest lever: L scales with cap-to-pin length; human L 0.3–2 nH on integrated cells | their cost | see below |
| E1–E3 | Evaluator fixes (above) | makes the A/B honest | small–medium | none |

### P1. What to hand the placement session
1. CIN_HF = the smallest-package owned cap (brief role `cin_hf`); place it on the IC's side with its pads facing the VIN and PGND pins, terminal axis parallel to the pin pair, gap = clearance; target hop length ≤ 1 mm, never > 2 mm (X1).
2. Reserve return-via sites: a keep-free strip ≥ via diameter + clearance beside the CIN ground pad and the IC PGND/EP, on the side away from the CIN–IC path (X6).
3. Two VIN/PGND pin pairs (or a Silent-Switcher-style pinout): split CIN symmetrically, one HF cap per side (X7).
4. Inductor next to SW, outside the CIN–IC strip.
5. Paralleled HF caps alternate orientation (X8), once E3 lets the evaluator see it.
6. Price all of this with the existing commutation term in `place_terms`, not a mm rule.

## Recommended plan and A/B (hotloop-ab)

Rank by expected gain per cost: R5 > R1 + R2 > R4 > R3 > J1 > T1. Order: E1 + E2 first → R5 alone as the cheapest arm → R1 + R2 + R4 + R5 → R3 → T1, J1, P1 later.

**Boards.** The 24 boards of the physics set with a commutation cell and compiled intents 42 cells (38 valued on the human layout); plus a twin of N on all 24 for noise. Route tasks (human placement), KiCad 10.0.7, intents `compiled-9867d0b`, score v12, same restart portfolio and budgets as confirm-default-ab.

| Arm | What |
|---|---|
| N | default (`--final`, `--finish`), power-copper-tht |
| N2 | twin of N (noise) |
| K | N + reference keep-out only (R5) |
| H | N + cells-first (R1) with watts quote (R2), via arrays (R4), reference keep-out (R5) |
| HP | H + hot-loop pours (R3) |

**Pre-registered criteria** (α = 0.05, Holm over secondaries; per-cell values from the E2 window solve, cross-checked at 0.25 mm):
1. Primary, physics: per-cell R_loop median H/N ≤ 0.75 and L_loop median H/N ≤ 0.90, each with signal-better ≥ 2× signal-worse beyond N2–N noise. Open cells: H not more than N.
2. Primary, routing: completion H − N CI lower bound > −0.005; cp1 and clean_strict not worse (McNemar); no new DRC error type with > 5 occurrences; no invalid output.
3. Secondary: against human, per-cell L_loop median ≤ 1.0 and R_loop median ≤ 1.2; `overshoot.peak`, `supply.peak`, `pickup.peak`, `loss.swnode` not worse beyond floors.
4. K is judged by criteria 1–3 against N on its own (it may be adopted alone). HP adopted over H only if R_loop falls further ≥ 15 % with criteria 2 and 3 holding, `starved_thermal` not up.
5. Before concluding, read per-type DRC errors and the cell renders of every board where H loses.

**Cost.** 5 arms × 24 boards × one portfolio attempt (900 s × √(footprints/40)) ≈ 30–50 core-hours plus physics (~70 evaluations); through kaeq at priority ≤ 5, owner `hotloop-r`.

## Open questions
- Absolute loss scale: ½·L·I²·f vs EPC's ~2× measured sensitivity; needs a switching model per cell class (integrated vs discrete).
- Does the router quote (fastloop, image plane) rank cells as the evaluator does? Measure Spearman ρ on the A/B's cells before trusting R2's quote.

## Sources
- Repo docs linked above; reports `bench/results/2026-11-11-route-finish-ab.md`, `2026-11-13-confirm-default-ab.md` (branch `origin/route-finish-ab`).
- TI SNVA638 (AN-2155) "Layout Tips for EMI Reduction in DC/DC Converters", [PDF](https://www.ti.com/lit/pdf/snva638) [P]; SNVA803, SLYT614, SLYT682, LM10504 [P via hot-loops/buck].
- EPC WP009 "Impact of Parasitics on Performance" (Reusch), [PDF](https://epc-co.com/epc/Portals/0/epc/documents/papers/Impact%20of%20Parasitcs%20on%20Performance.pdf) [P]; EPC WP010 [P via hot-loops]; EPC first-inner-layer return ≈ 150 pH measured on a monolithic half-bridge ([Electronic Design](https://www.electronicdesign.com/technologies/power/article/21199487/best-practices-part-1-integrating-egan-fets)) [S].
- MPS Hedrich #0030 [P]; ADI Silent Switcher article [S] (linked in the table).
- M. Sanjabiasasi et al., "PowerSynth 2", IEEE OJPEL 6 (2025) 899–, doi:10.1109/OJPEL.2025.3567148 [P].
