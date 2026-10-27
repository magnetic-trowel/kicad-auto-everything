# kae fast physics place terms

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

**Loop inductance.** A closed chain of straight segments over a perfectly conducting plane: L = sum_ij [M(s_i, s_j) + M(s_i, s_j*)] with mirror images s_j*, Grover's parallel-filament and corner formulas, strip self term M(l, a) - M(l, d_eff) with a = 0.2235 (w + t) and d_eff tuned to the Hammerstad-Jensen L'. Terminals are pad-group centroids; hops sit at the nearest-plane height (median of 5 samples), body hops at h + z_body, vias on side changes, oblique pairs by the geometric mean distance of a linearly varying offset, a ground hop in parallel with a via return. Derivation in [place-terms](../../topics/physics/place-terms.md).

**Routed-detour calibration.** Straight pad-to-pad hops under-read routed loops. `pt_routed_calib.py` follows each hop of 693 modules on 69 human boards along its least-L' copper path (on KiCad-refilled zones) and fits a stretch 1 + c sqrt(l) (l in mm) per hop class, with a 90% board bootstrap: decap rail c = 0.127, surge path 0.110, hot loop 0.087, crystal 0.048.

**Decap model.** Power pins cluster at 1.6 mm, each returning through its nearest ground pin. Pairing follows the brief: `pin` -> paired caps in parallel; `nearest_pin` -> the loop to the IC's nearest pin cluster at current poses; unowned (caps_p < 0.5) and `nearest_load` -> the nearest load pin on the rail. **Pour mode:** when rail and ground zones join the pins, L = L_mount,cap + L_mount,IC + (mu0 d / pi) ln(D / r) (plane-pair spreading, within 0.4% of a sheet solve). **Budget:** an IC's transient splits over its power pins (n_IC Z_t to 100 MHz), held to [L_c, 2 L_c] where L_c is the loop with the cap right beside its pin (4 rotations evaluated on the board), so u = 1 is careful practice; stability and bulk caps get max(10 nH, L_c).

**Thermal excess.** The board as a fin: G_s = sum k_cu t_i f_i + k_FR4 t (f = 1 for layers at least half covered by zones, else 0.2), lambda = sqrt(G_s / h_tot), h = 10 W/m^2K per side; a point source gives T = P K0(r/lambda) / (2 pi G_s), its own disk (1 - x K1(x)) / (pi a^2 h_tot); adiabatic edges by one ring of 36 images plus a continuum tail. The board-mean rise sum P / (h_tot A) does not depend on placement, so budgets apply to the excess T - T_mean (sources <= 20 K; victims by class). Losses: converter rectifier 0.5 V I (1 - D), inductor 15%, the rest in switches.

**Fast kernels.** `fastloop.py` is a scalar evaluator specialized for horizontal straight segments at known heights plus vertical pieces. `jit.py` loads `_kernels.py` twice, as plain Python and with every function wrapped in `numba.njit(cache=True)`, so both run the same source (they agree to 1e-12); `KAE_NO_NUMBA=1` forces Python. One kernel call prices all coupling sub-terms of a move; cable pickup is zero outside its window; a thermal move updates one row and column.

## What we tried

- Kernel validation (`pt_validate_kernels.py`) against a multi-filament PEEC (`pw_peec`) on A*-routed loops, and against a 2-layer finite-volume thermal model.
- Speed: 29,040 random moves on 82 boards; a 387-part board (sparkfun-xrp, 87 physics structures).
- "Does the physics prefer the human placement?" (`pt_human_perturb.py`): per term kind, move each involved part (three 1-5 mm translations, three rotations) and do 20 global shuffles; count worse / (worse + better) over material moves (>= 1% of an allocation) of credible structures; triage the better-than-human moves (grid-route check with `pt_grid_route.py`).

## Results

| measure | result | source |
|---|---|---|
| loop L vs PEEC on routed loops | median 5.0% (hot, n 180), 5.3% (decap, n 144), max 9.4%; same cap-pose ordering as PEEC in 93-94% of pairs | [place-terms](../../topics/physics/place-terms.md) |
| other kernels vs reference | coupling 10.6% / 9.8% median (inductive / capacitive), crystal C' 3.8%, thermal fin 7.2% (p90 13.4%), ESD 3.4% | same |
| detour calibration, routed / estimate median | decaps 1.17 -> 1.07, hot loops 1.08 -> 1.00, surge 1.23 -> 1.00 | same |
| decap budgets on human boards (1,471 structures) | median u 0.82; 35% over budget; 6% beyond 2x; pour mode routed / estimate 1.04 (41 decaps) vs 0.94 straight | same |
| delta speed, 82 boards | median 22 us, p90 70 us; delta equals total difference to 2.4e-7 | same |
| delta speed, 387-part board | median 40 us, p90 137 us, p99 0.68 ms (before numba: 131 us, 2.1 ms, 7.4 ms); Python 12x slower | same |
| construction | median 9 ms (split B), 35 ms (split C) | same |
| shuffles worse than human | decap 97%, crystal 99%, antenna 98%, commutation 99%, power path 95%, ESD 97%, world CM 87%, coupling 90%, **thermal 41%** | same |
| 2,321 better-than-human local moves | 22% explained by estimator or brief faults, 78% by human trade-offs or slack | same |
| placer with vs without terms (split C, 71 boards) | physics 1,410 vs 35,380 (human 4,392) | [place-physics-ablation-1ef5bf1](../../../bench/results/2026-10-24-place-physics-ablation-1ef5bf1.md) |

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
