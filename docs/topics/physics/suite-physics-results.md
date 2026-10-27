# Suite physics: passports and critics on the 112 qualified boards

**TL;DR**
- **Coverage is complete and cheap.** Passports and critics ran on all 112 boards of the KiCad 10.0.7 qualified suite with no tool failure: 15.2 min at three jobs, median 8.8 s per board, peak 3.3 GB. DC passports cover 335 rails on 90 boards; hot loops, 22 cells on 19 boards [C].
- **Solver cost is set by terminals, not board size.** The DC networks have up to 260k unknowns and factor in at most 4.5 s with COLAMD. Minimum-degree ordering took up to 413 s and over 4 GB on the same matrices, because each pad electrode is a row with up to 5,788 entries. Hot-loop windows (up to 98k sheet cells, 107 s) are the cost tail [C].
- **Human power copper is thin at the vias.** On 102 of 335 rails one via or plated lead carries all of the supply current (on 27, all of the ground return), and 49% of loads take at least 90% of their current through one via. The median rail has 9.7 mΩ of copper; the worst load sees a median 21 mV per ampere (p90 96 mV/A) [C].
- **Hot loops are set by plane order more than by vias.** Model-relative loop L is 5.5 nH median (p10–p90 2.1–17.9 nH). The best added via cuts it 5% median, 16% at most; where a foreign plane lies between the cell and ground (6 cells), swapping planes cuts it 19–65% [C].
- **Freerouting's DRC-clean failure is power copper.** On the 18 complete A+B boards it adds no return-path faults, but it doubles the worst rail drop (median ×1.9, up to ×8.4) and turns a 12 V, 5 A breakout's 2.8 mΩ supply copper into 49 mΩ [C].

Tags: [S] secondary, [C] computed by the scripts in Sources; quasi-static and uncalibrated. "Per A" is per ampere of that load, since load currents are unknown. Physics is a separate scorecard; cp1/cpk are not read.

## Key facts

### 1. Method

**Pipeline.** For each board the runner copies the board and its reference rules to a scratch directory, refills and saves the zones (`kicad-cli pcb drc --refill-zones --save-board`), and runs the passports and the critics in separate processes (600 s timeout, 4 GB resident-memory watchdog). An aggregation step writes `summary.json` and `summary.md` under `kae-work/physics/<run>/`, never into kaebench's `results/` or `score/`. `--boards-glob` runs the same physics on router outputs, paired with the human board by task id.

**Roles.** Each role carries its evidence and a confidence (high, medium, low).

| Role | Evidence (for / against) |
|---|---|
| Ground | name, copper area, capacitors, pins named GND/VSS/EP |
| Rail | name, pins typed `power_out`/`power_in` in the board file, regulator and inductor outputs, capacitors to ground, pours, wide tracks / control names, IC pins typed only as signals |
| Source | regulator outputs > inductor outputs > battery holders > connectors with ≤ 6 nets > series parts (fuse, diode cathode, bead, R ≤ 1 Ω) from a sourced rail > any connector |
| Load | IC pins on the rail (`power_in` pins when typed); connectors that are not the source |
| Switching cell | IC pin on an inductor ≥ 0.2 µH; bridge IC on ≥ 2 shunts (as in [rb_board_passports.py](../../../tools/research/physics/rb_board_passports.py)); two transistors sharing a node between a rail and ground, driving an inductor, connector or power packages |

Decaps are 2-pin capacitors between a rail and a ground; shunts are 2-pin resistors of 0 < R ≤ 0.2 Ω. The critics take ground and power nets from the inferred roles where present and from name regexes otherwise, recording `role_src` on each marker.

**DC passport.** Ground and every medium- or high-confidence rail with a source and a load share one conductance network: per-net grids of 0.05–0.2 mm coarsened together to ≤ 300k nodes, via barrels, equipotential pad electrodes, one sparse LU per component ([real-board-passports](real-board-passports.md) §2). For each load (the 12 farthest at most), 1 A flows from the source pads to its rail pins and 1 A from its ground pins back to the source's. Per rail:
- **R_eff** (loss-equivalent, all loads drawing equal shares) and the **worst drop per ampere** (rail plus ground) of any one load;
- **peak current density**, and **necks**: 1 mm tiles over 0.5 mm from any terminal holding ≥ 20% of R_eff;
- **via bottlenecks**: one via or lead carrying ≥ 50% of the rail's current with exact leverage ρ ≥ 0.8; at ρ ≥ 0.999 it is a sole path;
- **dead copper**: the share of cells carrying < 0.1% of every modelled current;
- with a pour, the **Beckmann floor** R_B = W1²/Σ_l(A_l/R_s,l) ([lens-vp](lens-vp.md)): at most 1 − R_B/R_eff is avoidable at equal area.

**Ground topology:** ground islands per layer with their vias and parts, exposed pads without vias, and whether a switching cell's input capacitors share top-side ground with the IC.

**HF hot loop.** For up to three cells per board, rb's stack-local inductive-limit model (window ≤ 120k cell-layers) gives loop L, the remove-plane and swap-plane counterfactuals and the best added ground via over every legal site. A loop that does not close inside the window counts as a failure.

Findings are counted with screening thresholds, not budgets: drop 100 mV/A, dead copper 50%, Beckmann gap 90%, HF gain 10%.

### 2. Coverage

| Analysis | Boards | Why not on the rest |
|---|---|---|
| Refill, passports, critics | 112 / 112 | none failed; KiCad refilled every board |
| Ground identified | 109 | an LED string, an LED board and a battery pack have no ground net |
| DC passport, ≥ 1 rail | 90 (335 rails: 223 high, 112 medium) | 19 boards have no rail with both a source and a load (ground topology only); 3 have neither |
| Switching cell found | 27 boards, 38 cells (35 regulator + inductor, 2 half-bridge, 1 bridge) | no such stage |
| HF hot loop | 22 cells on 19 boards | 5 open loops in the window; 5 with no drive cut (lead strips merge on the raster); 3 boosts with an external diode; 1 without an input capacitor within 12 mm; 2 over the cell limit |
| Critics with edge-critical nets | 70 | no net matches the fast-net regex |

108 rails have no identified source: EmberOne's 24 series-stacked ASIC domains, IC-internal supply pins, and rails fed through uncovered parts.

### 3. Measured cost

| Step | Median | p90 | Max | Note |
|---|---|---|---|---|
| KiCad refill + DRC | 1.6 s | 10.2 s | 196 s | Latent Red linecard (3,082 vias, 9,900 tracks) |
| Passports | 5.2 s | 21.8 s | 147 s | max: 128 s in one 98k-cell HF window |
| Critics | 0.9 s | 4.6 s | 100 s | max: the linecard's 448 edge-critical nets |
| Whole board | 8.8 s | 41.8 s | 315 s | 2,461 s summed over 112 boards |
| Peak RSS, passports | 557 MB | 1.23 GB | 3.3 GB | the same HF window |
| Peak RSS, critics | 83 MB | 132 MB | 446 MB | |
| DC nodes (branches) | 121k (237k) | 236k (467k) | 260k (505k) | |
| DC factorization (COLAMD) | 0.50 s | 1.5 s | 4.5 s | 82 s summed |
| HF sheet cells / time per cell | 37k / 12.5 s | 87k / 38 s | 98k / 107 s | |

The ordering matters more than the size [C]. On the same matrices, minimum-degree ordering on AᵀA:
- took 2,749 s summed instead of 82 s;
- took 413 s and over 4 GB on one 6-layer board;
- did not finish a 2-layer board in 600 s.

An electrode links a pad to every cell under it, up to 5,788 entries in one row. Minimum degree handles such dense rows badly, while COLAMD defers them [S].

An address-space cap is the wrong memory guard: SuperLU grows its buffers by realloc, so a factorization with 1.3 GB resident fails under a 4 GB address-space cap [C].

### 4. Distributions

**DC passports (335 rails)**

| Quantity | Median | p10–p90 | Max |
|---|---|---|---|
| R_eff, rail copper (mΩ) | 9.7 | 1.5–50 | 296 |
| Ground return R_eff (mΩ; 227 rails) | 1.3 | 0.23–7.0 | 125 |
| Worst drop, rail + ground (mV per A) | 21 | 2.5–96 | 439 |
| Peak current density (A/mm² per A) | 77 | 20–243 | 745 |
| Dead copper share | 0.36 | 0.10–0.72 | 0.95 |
| Beckmann avoidable bound (161 rails with pours) | 0.84 | 0.57–0.97 | 0.99 |

- **Via bottlenecks.** 236 are flagged on 142 rails. A via or plated lead is the sole path of the whole supply current on 102 rails, and of the whole ground return on 27. The rest carry ≥ 50% with ρ between 0.8 and 0.999. 427 of 873 modelled loads take ≥ 90% of their current through one via.
- **Necks are rare:** 13 tiles on 12 rails. Loss concentrates at terminals and vias, not in pours.
- **Ground.** 139 islands on 45 boards hold the ground pins of two or more parts and reach the rest of ground through ≤ 2 vias. Median dead ground copper is 26%. Ten ICs on 9 boards have an exposed pad without a via (three power ICs). On 9 boards, 25 input capacitors of a switching cell sit on a top-side ground island apart from the IC's ground pins.
- **The Beckmann bound is too loose to rank pours:** it imposes no shape and calls a median 84% avoidable, where convex floors put real pours 4% above theirs ([validation-program](validation-program.md)).

**HF hot loops (22 cells; model-relative)**

| Quantity | Median | Range |
|---|---|---|
| Loop L (nH) | 5.5 | 0.99–35.6 |
| Best added ground via | −5.1% | −0.002% to −15.7% |
| Median legal via site | −0.01% | 0 to −1.2% |
| Swap the plane nearest the cell with ground (6 cells) | −22% | −19% to −65% |
| Remove the nearest foreign plane (11 cells) | ×1.03 | ×1.0 to ×3.9 |
| Loop current induced in nets outside the loop | 3.9% | 0.1% to 70% |

**Critics**

| Quantity | Value |
|---|---|
| Edge-critical length over the near reference (70 boards) | median 46% (p25 9%, p75 85%); 74 of the 112 boards are 2-layer |
| Void crossings | median 11 per board; 60 of 70 boards have one or more |
| RPQF-lite, worst net | median 1.79, p90 6.8, max 42 |
| Inner plane layers with foreign tracks | 36 of 88, on 38 boards; median 13 mm, p90 1.2 m, max 5.1 m |
| Longest plane slot | median 41 mm (93 boards) |
| First cavity mode | median 2.8 GHz, minimum 0.25 GHz |

### 5. The most informative findings

No geometry is reproduced [C].

| Board (licence) | Finding |
|---|---|
| BLDCM-Power (MIT) | Every HF number of [real-board-passports](real-board-passports.md) is reproduced from inferred roles: 9.14 nH, ×2.78 without the 3.3 V plane, −14.7% for one via in the exposed pad. Two power ICs' exposed pads have no via |
| AFTONSPARV (CERN-OHL-S-2.0) | Buck loop 12.7 nH; swapping the 3.3 V plane with ground cuts it 62% |
| Rocket FMC USB/GPIO (Apache-2.0) | Buck loop 8.3 nH; plane swap −65%; 43% of the loop current is induced in nets outside the loop |
| CAN processor, Waterloo Rocketry (GPL-3.0-only) | Buck loop 3.1 nH with the 3.3 V plane as image conductor (×3.9 without it); swap −22% |
| DCDC-50-5-12 (CERN-OHL-S-2.0) | Loop 6.5 nH; one added via −10.8%, plane swap −19% |
| Ping dev kit (CERN-OHL-P-2.0) | The four input capacitors of the STM32H5's internal SMPS share one 4–6 mm² ground island with a single via, 7.8 mm from the IC. A buck loop of 22.5 nH has 70% of its current induced in other nets |
| Obsidian (CERN-OHL-W-2.0) | Six input capacitors of the RTL8211F's switching regulator each sit on their own 0.5–0.7 mm² ground island with one via |
| Kit-dev ColdFire (CC-BY-SA-4.0) | The LT1129 regulator's 101 mm² tab pad has no via |
| 12 V 5 A breakout (MIT), Freerouting | Supply copper 2.8 → 49 mΩ with zero DRC errors: 0.25 V and 1.2 W at 5 A instead of 14 mV and 0.07 W |
| Bipolar supply (CERN-OHL-P-2.0), Freerouting | Both rails 11 → 93–96 mΩ, each now running through other parts' leads as sole paths |

### 6. Role inference: what it got right and wrong

**Inputs.** 99 of 112 boards carry pin types in the board file, 89 of them with `power_in`/`power_out` pins. 590 of 1,090 loads were found through typed `power_in` pins. Sources: 221 high, 160 medium and 79 low confidence.

**Right [C].**
- **Hand-checked boards.** On BLDCM-Power it finds the hand check's driver, rail, bridge-return pins and capacitors, and the HF numbers agree to the printed digit; on oasis the buck loop is 2.38 nH (2.4 nH in [real-board-passports](real-board-passports.md) §5).
- **Random sample of 8 boards.** Ground was right on 8/8, and the main rails and sources were plausible on all 8, including ferrite-bead sources on a video decoder whose `/VIN1`–`/VIN8` analogue inputs were correctly rejected as signals.
- **Converters inside other ICs** are found: an MCU's internal SMPS and an Ethernet PHY's regulator.
- **Critic roles.** Inference changed 319 nets against the regexes: 289 signal → power (rails named without a voltage pattern: 3P3V, VADJ, DDRVTT), 27 power → signal (power-good, enable, sense, video inputs) and 3 signal → ground. 1,536 of 7,179 markers rest on an inferred role.

**Failure modes observed on suite boards.** The tool guards against the first five:
1. package codes in values ("10k/R0402" read as 0.0402 Ω) make every resistor a shunt;
2. GND_RE misses letter-prefixed grounds (XADCGND, CHASSISGND);
3. discrete transistor logic matches the half-bridge pattern;
4. a pad count alone, or "ADC" in ADC_AVDD, is too weak to reject a named supply (30 cases);
5. an open loop in the HF window reads as 10¹⁰ nH, and a small Edge.Cuts cut-out can pass for the outline.

Two remain open:

6. **Library pin types mislead.** Connector, fuse, bead and resistor pins typed `power_out` become "regulator outputs" (Latent Red PDU, linecard); Kelvin sense lines named after their rail become rails.
7. **Some stages have no model:** 108 sourceless rails get no DC passport; boosts with an external diode and discrete half-bridges get no HF model.

### 7. Router against human (Freerouting, splits A and B)

33 boards are paired by task id. 18 reached completion 1.0 and are electrically comparable; all 18 are 2-layer. Split C was still routing at the time of this run (8 of 79 attempts, 3 with output, none complete).

| Complete boards (18) | Human | Router |
|---|---|---|
| Void crossings (RET-COV) | 106 | 94 |
| RET-VIA markers | 0 | 1 |
| Inner planes with foreign tracks | 0 | 0 |
| Worst rail drop, router / human (11 rails) | 1 | median ×1.9 (p10–p90 ×1.0–×8.1; max ×8.4) |

Router-introduced faults that DRC does not see [C]: thin power tracks (PWR-TRACE) on 5 boards, worst drops above 100 mV/A on 3, and sole-path leads on 2, where the rail runs through other parts' pins. It also removed 22 void crossings, so return-path quality is a wash on these boards. Reported apart: on two incomplete boards the hot loop is worse (DCDC-50-5-12 6.5 → 10.6 nH, Noisecard 9.6 → 39 nH).

## Recommendations for our system

1. **Model terminals as constraints, not dense rows.** Use multipoint constraints or a Schur complement for equipotential pads, choose orderings that defer dense rows, and test every solver on the suite's electrode-heavy boards. A whole-board exact DC passport then costs seconds; HF windows need Schur-windowed or reduced-order solves ([physics-core-v2](physics-core-v2.md)).
2. **Make roles an input with provenance.** Pin types carry inference on 89% of boards, but libraries mistype pins and sense lines borrow rail names: infer, show the evidence, and have a human confirm sources, Kelvin pairs and stacked domains ([physics-critics](physics-critics.md) §2).
3. **Grade DC findings by current.** 36% of rails have a sole-path via: normal for milliamp rails, a fault for amp rails. Until the schematic supplies load currents, rank by per-ampere values and do not count them as violations.
4. **Gate router output on DC passports.** Net current classes that set trace width, and a post-route DC passport against the human board, would catch the ×2–×17 resistance rises that DRC passes.
5. **Rank hot-loop fixes by counterfactual, after a closure test.** Plane order is the largest lever where it applies; the model needs body models for boosts and discrete half-bridges, and calibration before its nanohenries are used.
6. **Rank pours with convex floors, not Beckmann.**

## Conflicts and open questions

- **Calibration.** No number is calibrated. The HF model over-estimates narrow strips (×1.5 at w/h = 5); DC grids coarsen to 0.47–0.63 mm on the largest boards, under-resolving thin tracks.
- **Currents.** Per-ampere metrics cannot say which findings matter.
- **Role errors.** Counts inherit the errors of §6, and the screening thresholds are defaults, not budgets.
- **Router audit scope.** One run on small 2-layer boards; split C, where plane perforation was predicted, is pending.
- **Critic roles.** Edge-critical roles in the critics still come from names.

## Sources

- Scripts: [suite_physics.py](../../../tools/research/physics/suite_physics.py) (runner, aggregation, pairing), [suite_passports.py](../../../tools/research/physics/suite_passports.py) (roles, DC, ground, HF), [pc_refplane.py](../../../tools/research/physics/pc_refplane.py) (critics), [rb_board_passports.py](../../../tools/research/physics/rb_board_passports.py) (network, terminals, HF model).
- Outputs (not committed; third-party boards): `kae-work/physics/human-k10/` and `fr-ab-k10/`, with per-board JSON and logs and per-run `summary.json`/`.md` and `compare.json`/`.md`.
- Suite and licences: [qualified-kicad-10.0.7.txt](../../../bench/suites/qualified-kicad-10.0.7.txt), `bench/manifests/candidates.jsonl`.
- T. A. Davis et al., "A column approximate minimum degree ordering algorithm", ACM TOMS 30(3), 2004 (dense-row handling in COLAMD) [S].

See also: [real-board-passports](real-board-passports.md) · [physics-critics](physics-critics.md) · [physics-critics-catalog](physics-critics-catalog.md) · [lens-cd](lens-cd.md) · [validation-program](validation-program.md) · [physics-core-v2](physics-core-v2.md)
