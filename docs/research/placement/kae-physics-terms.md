# kae fast physics place terms

Scope: defensive publication of the fast incremental physics place terms (one currency u = spend/allocation), their kernels, calibration, validation and the human-perturbation study. Not here: derivations and reference numbers -> [place-terms](../../topics/physics/place-terms.md); exact solvers in the loop -> [exact physics before routing](kae-exact-physics-before-routing.md).
Keys: Terms, delta, breakdown, one currency, phi(u), beta = 4, ownership logit, commutation loop L, power path, decap loop, coupling, Neumann integral, crystal pulling, thermal excess, fin model, K0, cable common-mode, ESD surge path, antenna feed, Grover, Hammerstad-Jensen, routed-detour calibration, pt_routed_calib.py, pour mode, fastloop.py, jit.py, KAE_NO_NUMBA, pt_human_perturb.py

**Status:** worked (thermal term partial).
**First published:** 2026-10-22, commit [64a6858](https://github.com/magnetic-trowel/kicad-auto-everything/commit/64a6858cca92b72ead01cdf56e3b5667a71cb2bc) on branch `claude/vigilant-mayer-i91rrr` (thermal local-excess budget and decap floor [d28e7de](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d28e7de1e031ceb3475000ab47c777d56ab9a198), routed-detour calibration [e171267](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e171267e73ad11b230df15ac32a9ef9e2e832be0)).

Incremental physics estimates of a placement, in one currency, cheap enough for a simulated annealer: loop inductance of hot loops, power paths and decaps, inductive and capacitive coupling, crystal pulling, thermal excess, cable common-mode, ESD surge path and antenna feed. Each structure from the [brief](kae-comprehension-brief.md) gets a budget and a utilization u = spend / allocation. Loop inductance lands within 5% median of PEEC on routed copper and a move is priced in tens of microseconds. All budgets are uncalibrated priors and all checks are model against model.

## Idea and how it works

**API.** `Terms(board, brief)` exposes `total`, `delta(poses, moved, new_poses)`, `breakdown`, `parts`, `structures_of`. Every component is cached against its parts' pose epochs, so a move recomputes only what it touches.

**One currency.** Structure s reports physical spend v_s, allocation a_s, u_s = v_s / a_s. Cost J = sum_s c_s phi(u_s), with phi(u) = u for u <= 1, u + beta (u-1)^2 for 1 < u <= 10, then a logarithmic tail (C1-continuous; beta = 4). Weight c_s = confidence x calibrated ownership, logit q = 0.67 + 0.515 logit p.

**Terms.**
- (a) Commutation loop L; budget from overshoot, L_max = sigma^2 / (2 C_oss ln(1/a')).
- (a') Power-path loop L; budget from a 100 ns load step (<= 5% of V, <= 50 nH).
- (b) Decap loop L (see decap model below).
- (c) Coupling noise 1e3 * M * dI/dt plus a capacitive term; image-quadrupole far field and Neumann-integral near field (closed-form inner integral, 3-6 Gauss points).
- (d) Crystal pulling S * C' * l / 4.
- (e) Thermal excess rise (below).
- (f) World node: cable common-mode current (omega M I / Z_cm + omega C_m V, windowed by connector distance); ESD surge path L' l (1 + 0.11 sqrt(l)) + L_via against 5.3 nH (IEC 61000-4-2 level 4); antenna feed loss 0.015 dB/mm x MST length.

**Loop inductance.** Closed segment chain over a PEC plane, L = Σ_ij [M(s_i, s_j) + M(s_i, s_j*)] with mirror images, Grover filament and corner formulas, Hammerstad–Jensen-tuned strip self term; terminals at pad-group centroids, hops at nearest-plane height, vias on side changes. Full estimator -> [place-terms §2](../../topics/physics/place-terms.md#2-loop-inductance-a-b).

**Routed-detour calibration.** Straight pad-to-pad hops under-read routed loops. `pt_routed_calib.py` follows each hop of 693 modules on 69 human boards along its least-L' copper path (on KiCad-refilled zones) and fits a stretch 1 + c sqrt(l) (l in mm) per hop class, with a 90% board bootstrap: decap rail c = 0.127, surge path 0.110, hot loop 0.087, crystal 0.048.

**Decap model.** Power pins cluster at 1.6 mm; pairing follows the brief (`pin`, `nearest_pin`, `nearest_load`); pour mode adds plane-pair spreading (μ0d/π)·ln(D/r); budget n_IC·Z_t per pin held to [L_c, 2L_c], stability and bulk caps max(10 nH, L_c). Details -> [place-terms §3](../../topics/physics/place-terms.md#3-decoupling-b).

**Thermal excess.** Board as a fin, λ = √(G_s/h_tot), point source T = P·K0(r/λ)/(2πG_s), image ring for adiabatic edges; the board-mean rise ΣP/(h_tot·A) is placement-independent, so budgets apply to T − T_mean (sources ≤ 20 K). Details -> [place-terms §6](../../topics/physics/place-terms.md#6-thermal-e).

**Fast kernels.** `fastloop.py` is a scalar evaluator specialized for horizontal straight segments at known heights plus vertical pieces. `jit.py` loads `_kernels.py` twice, as plain Python and with every function wrapped in `numba.njit(cache=True)`, so both run the same source (they agree to 1e-12); `KAE_NO_NUMBA=1` forces Python. One kernel call prices all coupling sub-terms of a move; cable pickup is zero outside its window; a thermal move updates one row and column.

## What we tried

- Kernel validation (`pt_validate_kernels.py`) against a multi-filament PEEC (`pw_peec`) on A*-routed loops, and against a 2-layer finite-volume thermal model.
- Speed: 29,040 random moves on 82 boards; a 387-part board (sparkfun-xrp, 87 physics structures).
- "Does the physics prefer the human placement?" (`pt_human_perturb.py`): per term kind, move each involved part (three 1-5 mm translations, three rotations) and do 20 global shuffles; count worse / (worse + better) over material moves (>= 1% of an allocation) of credible structures; triage the better-than-human moves (grid-route check with `pt_grid_route.py`).

## Results

| measure | result | source |
|---|---|---|
| loop L vs PEEC on routed loops | median 5.0% (hot, n 180), 5.3% (decap, n 144), max 9.4%; same cap-pose ordering as PEEC in 93-94% of pairs | [place-terms §2](../../topics/physics/place-terms.md#2-loop-inductance-a-b) |
| other kernels vs reference | coupling 10.6% / 9.8% median (inductive / capacitive), crystal C' 3.8%, thermal fin 7.2% (p90 13.4%), ESD 3.4% | place-terms §4–7 |
| detour calibration, routed / estimate median | decaps 1.17 -> 1.07, hot loops 1.08 -> 1.00, surge 1.23 -> 1.00 | [§2a](../../topics/physics/place-terms.md#2a-routed-copper) |
| placer with vs without terms (split C, 71 boards) | physics 1,410 vs 35,380 (human 4,392) | [place-physics-ablation-1ef5bf1](../../../bench/results/2026-10-24-place-physics-ablation-1ef5bf1.md) |

### Human-board perturbation study

On all 112 kaebench boards, each term's parts get three 1–5 mm translations and three rotations each, and 20 shuffles to random legal-ish poses. Share is worse/(worse + better) over *material* moves (some structure changes by ≥ 1% of its allocation) of *credible* structures (some component's pad-to-pad hops all ≤ 15 mm); brackets give the decided counts.

| Term | Boards | Translate worse | Rotate worse | Shuffle worse | Shuffle, all terms |
|---|---|---|---|---|---|
| decap | 78 | 86% (2574) | 82% (1640) | 97% (1485) | 92% |
| crystal | 24 | 81% (165) | 91% (147) | 99% (480) | 98% |
| antenna | 6 | 83% (171) | 77% (87) | 98% (112) | 99% |
| commutation | 30 | 80% (261) | 72% (188) | 99% (562) | 88% |
| power path | 14 | 75% (24) | 64% (14) | 95% (140) | 85% |
| ESD | 27 | 57% (284) | 78% (221) | 97% (434) | 92% |
| world CM | 32 | 66% (103) | 46% (80) | 87% (617) | 91% |
| coupling | 32 | 59% (822) | 62% (530) | 90% (640) | 95% |
| thermal | 52 | 44% (378) | – | 41% (899) | 93% |

Only thermal shuffles beat the human, by spreading heat. Where human boards spend their budgets (over-budget share before the routed-copper calibration and decap priors in brackets; then the share over half and over twice the budget):

| Term | Structures | Median spend (p90) | Median u | Over budget | > 0.5× | > 2× |
|---|---|---|---|---|---|---|
| commutation | 63 | 2.7 (9.5) nH | 1.41 | 68% (57%) | 75% | 32% |
| power path | 21 | 8.7 (27) nH | 0.34 | 19% | 33% | 14% |
| decap | 1471 | 2.9 (7.7) nH | 0.82 | 35% (29%) | 87% | 6% |
| coupling | 243 | 0.24 (32) mV | 0.18 | 26% (25%) | 37% | 21% |
| crystal | 29 | 2.9 (7.7) ppm | 0.58 | 24% (21%) | 62% | 7% |
| thermal (excess) | 284 | 7.6 (36) K | 0.41 | 29% (27%) | 45% | 11% |
| ESD | 487 | 4.7 (31) nH | 0.89 | 46% (28%) | 74% | 21% |
| world CM | 272 | 0.0001 (0.11) µA | 0.00002 | 0.4% (0.4%) | 0% | 0% |
| antenna | 25 | 0.84 (3.8) dB | 1.68 | 68% (68%) | 80% | 44% |

On the same briefs, detours alone raise ESD from 28% to 46%, hot loops 62% to 68%, crystals 21% to 24%. Decaps fell from 29% to 11% under the per-IC split and stability prior, then rose to 35% under the careful-layout budget; the share beyond 2× stayed at 6%.

Decap budgets by class (1,471 structures): median u 0.82 (p10 0.44, p90 1.61). Load caps are 39% over budget (median u 0.88), VCAP bypass 23% (64% and u 3.2 under the HF rule), regulator outputs 2%, converter outputs 5%.

Of 2,321 material better-than-human local moves, the estimator or brief explains 506 (22%): *assignment* 274 (the part sits > 15 mm from every human partner: bulk caps paired as HF, far protectors), *unroutable* 135 (no single-layer route, mostly BGA escapes) and *route* 97 (no longer better once grid-routed around other nets' pads). The human explains 1,815: *trade-offs* 920 that worsen other physics or wirelength (coupling 393, thermal 181) and *slack* 895 that worsens nothing (decap 481).

### Delta speed

`delta` on random single-part moves (numba, shared 4-core host): sparkfun-xrp (87 physics parts) median 40 µs, p90 137 µs, p99 0.68 ms, from 131 µs, 2.1 ms and 7.4 ms. Over 29,040 moves on 82 boards, median 22 µs, p90 70 µs, p99 0.32 ms; the slowest board's p90 is 0.36 ms (buspirate5, whose 25-LED rail took 0.77 ms before the candidate cache). `delta` equals the `total` difference to 2.4e-7 with accepted moves in between. Construction takes 9 ms on split B and 35 ms on split C (median; max 0.39 s), plus 0.5–0.8 s once per process to import numba and load its cached kernels. The Python fallback is about 12× slower.

## Verdict

Worked: the terms rank placements the way PEEC does most of the time and are fast enough for an annealer at about 10k moves per second. Caveats:
- Everything is model against model. PEEC and FV are references, not measurements; budgets are E5 priors ([physics area](../physics/README.md)).
- Thermal is weak: it is the only term where random shuffles beat the human layout (41% worse), and fast vs FV decisions flip 26-30% (the kernel misses partial pours). The proposed fix, a cached finite-volume model, was built but not wired in ([kae-exact-physics-before-routing](kae-exact-physics-before-routing.md)).
- The detour calibration removes only about a tenth of fast-vs-PEEC decision flips.
- Unpriced: snubber, bootstrap and charge-pump loops; multi-drop victims follow netlist order; antenna overruns come from misidentified feeds.

## Code

- `kae/src/kae/physics/{place_terms,structures,kernels,_kernels,build,boardview,priors,fastloop,jit}.py`.
- Validation: `tools/research/physics/pt_validate_kernels.py`, `pt_grid_route.py`, `pt_routed_calib.py`, `pt_human_perturb.py`. Tests: `kae/tests/test_place_terms*.py`.
- First appearances: terms [64a6858](https://github.com/magnetic-trowel/kicad-auto-everything/commit/64a6858cca92b72ead01cdf56e3b5667a71cb2bc); fastloop [64a6858](https://github.com/magnetic-trowel/kicad-auto-everything/commit/64a6858cca92b72ead01cdf56e3b5667a71cb2bc), jit [1120fc0](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1120fc039a1dbb970fe7f05bfe731f6513094e5d), `_kernels.py` [f7673bd](https://github.com/magnetic-trowel/kicad-auto-everything/commit/f7673bd54e143a57ad7f709a5ada732f0467b674); thermal excess and decap floor [d28e7de](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d28e7de1e031ceb3475000ab47c777d56ab9a198); detour and pour-aware decaps [e171267](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e171267e73ad11b230df15ac32a9ef9e2e832be0), calibration script [d311588](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d311588bc8ee60bce0fb13543e8992bc4dab980b); perturbation study [1120fc0](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1120fc039a1dbb970fe7f05bfe731f6513094e5d).
- Physics on is part of both merit kae methods.

## Related

[kae-placer](kae-placer.md), [kae-comprehension-brief](kae-comprehension-brief.md), [kae-exact-physics-before-routing](kae-exact-physics-before-routing.md), [physics models](../physics/README.md), [critical copper routing](../routing/kae-critical-copper.md).
