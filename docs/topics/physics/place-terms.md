# Place terms: what a placement spends, estimated fast

**TL;DR**
- **One currency.** Each structure reports spend over allocation, u = v/a, priced by φ(u): linear below budget, a quadratic barrier above, logarithmic beyond 10×. Allocations are the brief's budgets or documented E5 priors.
- **Loops.** Partial inductances with plane images are within 5% (median; max 9.4%) of PEEC on 324 routed loops. Straight hops are stretched by an expected detour 1 + c√ℓ fitted on 69 human boards' copper; routed/estimate is then 1.00 for hot loops and surge paths (like for like), 1.07 for decaps [C].
- **Other terms** (median error against a finer solver) [C]: coupling 10–11%, crystal C′ 4%, thermal fin 7%, ESD path 3.4%.
- **Human boards (112).** Shuffles score worse than the human in 87–99% for every term but thermal (41%; 93% counting all terms). Decap budgets sit at the careful-designer loop: median u 0.82, 35% over, 6% beyond 2× [C].
- **Speed.** `delta` on sparkfun-xrp (387 parts): median 40 µs, p90 137 µs (was 131 µs, 2.1 ms); over 82 boards, median 22 µs, p90 70 µs [C].

Code: [`kae.physics.place_terms`](../../../kae/src/kae/physics/place_terms.py) (`Terms(board, brief)`: `total`, `delta`, `breakdown`, `parts`, `structures_of`); kernels [`_kernels.py`](../../../kae/src/kae/physics/_kernels.py); priors [`priors.py`](../../../kae/src/kae/physics/priors.py). The brief is [comprehension](comprehension.md). Tags: [C] computed by [pt_validate_kernels.py](../../../tools/research/physics/pt_validate_kernels.py), [pt_routed_calib.py](../../../tools/research/physics/pt_routed_calib.py) or [pt_human_perturb.py](../../../tools/research/physics/pt_human_perturb.py); [S] secondary.

## 1. One currency

Each structure s returns a spend v_s in physical units, with allocation a_s and u_s = v_s/a_s:

J = Σ_s c_s φ(u_s),  φ(u) = u (u ≤ 1);  u + β(u−1)² (1 < u ≤ u_sat);  φ(u_sat) + φ′(u_sat)·u_sat·ln(u/u_sat) (beyond),

with β = 4, u_sat = 10 and c_s = confidence × calibrated ownership; φ is C¹. Over-budget structures dominate; beyond 10× a structure has failed (usually a misidentified one), and the log tail keeps a gradient without swamping other terms.

| Term | Spend | Default allocation (E5) |
|---|---|---|
| (a) commutation | loop L (nH), owned input caps in parallel | overshoot: L_max = σ²/(2C_oss ln(1/a′)), σ = t_sw/2.563, a = (0.85V_abs − V_in)/V_in |
| (a′) power path | loop L (nH) C_in → pass elements → C_out | load step: L ≤ 5%·V·100 ns/I, ≤ 50 nH |
| (b) decap | loop L (nH) per power-pin cluster or capacitor | n_IC·Z_t/(2π·100 MHz) per pin, held to [L_c, 2L_c]; stability and module caps max(10 nH, L_c) |
| (c) coupling | noise (mV) = 1e3·M·dI/dt + ΔV·C_m/(C_m + C_v + t_sw/Z_v) | feedback 10, sense 1, analog 1 mV |
| (d) crystal | pulling (ppm) = S·C′·ℓ/4, S = C1/(2(C0 + C_L)²) | 5 ppm |
| (e) thermal | rise above the board mean (K) | sources 20 K; victims by class |
| (f) world | cable CM (µA); ESD surge path (nH); feed loss (dB) | 5 µA (Ott); 5.3 nH; 0.5 dB |

A cell without an input voltage takes 24 V, above 90% of the corpus's named inputs. A power path (load switch, eFuse, ideal diode) is priced like a cell, each stage's elements in parallel; it does not commutate, so its budget comes from a full-load step, L·I/t ≤ 5% of V at t = 100 ns. Ownership is recalibrated, logit q = 0.67 + 0.515·logit p, to kae.circuit's measured reliability.

## 2. Loop inductance (a, b)

**Theorem 1.** For a closed chain of straight segments over a perfectly conducting plane, L = Σ_ij [M(s_i, s_j) + M(s_i, s_j*)], where s_j* is the mirror image of s_j (horizontal parts reversed, vertical kept). Self terms use the conductor's geometric mean distance (GMD); a chain ending on the plane is closed by it. *Proof:* images replace the plane, and a partial inductance is ∫A·dl over a segment (Ruehli [S]). Parallel filaments give M = (μ0/4π)[G(e1) − G(e1−l1) − G(e0) + G(e0−l1)], G(u) = u·asinh(u/d) − √(u² + d²) (Grover [S]).

**Strip self term.** A filament overstates wide strips over a near plane by 20–107% [C]. L_self = M(ℓ, a) − M(ℓ, d_eff), with a = 0.2235(w + t) and d_eff = a·exp(L′_HJ/0.2), has the Hammerstad–Jensen slope L′ = Z0,air/c0 (within 1%) and keeps the end terms.

**Estimator.** Terminals are pad-group centroids in current order.
- *Board hops* are strips at the height h of the nearest plane, the median of five samples along the hop; a side whose hops lie mostly over a plane is referenced throughout, so a hop across a hole or notch is not a free-space loop.
- *Detour.* A hop of length ℓ (mm) is stretched about its midpoint by 1 + c√ℓ (§2a).
- *Body hops* inside a part sit at h + z_body; side changes add a via.
- *Pairs* with |cos θ| ≥ 0.3 use the parallel-filament formula at the GMD of the linearly varying offset, ln GMD = [F(d2) − F(d1)]/(d2 − d1), F(p) = ½p·ln(p² + z²) − p + z·atan(p/z), finite for crossing hops; adjacent oblique pairs use Grover's corner formula.
- *Ground return.* A ground hop over its own plane runs in parallel with the via return C: L = A + M_AB + (B + M_AB)(C − M_AB)/(B + C).

**Guards** keep every human-board loop positive [C]: same-layer conductors stay ≥ (w1 + w2)/2 + clearance apart, and L is at least the parts' internal loops over an ideal return.

**Validation [C]** against PEEC (pw_peec) on A*-routed loops (a cap 1.5–7 mm from an IC pin pair; h 0.1–1.5 mm, w 0.25–2 mm): the closed forms are within 5.0% (hot, n 180) and 5.3% (decap, n 144) median, max 9.4%. Straight hops read 8–11% low but order cap poses as PEEC does in 93–94% of pairs. Oblique pair rules are within 0.5% of quadrature. The regime is quasi-static (loops ≪ λ/10); planes act as PEC above about 1 MHz.

### 2a. Routed copper

[pt_routed_calib.py](../../../tools/research/physics/pt_routed_calib.py) follows each hop of 693 modules on 69 human boards along its least-L′ copper path (the critical router's recheck, KiCad-refilled zones) [C].

| Hop class | Hops | Routed/straight length, median (p90) | c in 1 + c√ℓ (90% board bootstrap) |
|---|---|---|---|
| decap rail | 614 | 1.17 (2.22) | 0.127 (0.100–0.145) |
| surge path | 297 | 1.17 (2.45) | 0.110 (0.065–0.130) |
| hot loop | 32 | 1.02 (1.51) | 0.087 (0.035–0.155) |
| crystal net | 41 | 0.97 (1.97) | 0.048 (0.010–0.100) |

The detour grows with distance (decap hops 1.13 below 2 mm, 1.67 beyond 15 mm). Inductance routed/estimate, median (p10–p90):

| Kind | n | Straight hops | With detour |
|---|---|---|---|
| decap, all | 211 | 1.17 (0.49–1.87) | 1.07 (0.45–1.68) |
| decap, pin clusters | 158 | 1.28 (0.79–2.04) | 1.16 (0.71–1.84) |
| hot loop, loop's own cap | 32 | 1.08 (0.72–1.75) | 1.00 (0.67–1.60) |
| surge path, reference's via | 214 | 1.23 (0.78–2.86) | 1.00 (0.63–1.77) |

Like for like uses the reference's definitions: a cell loop through the brief loop's capacitor only (Terms: owned caps in parallel, 1.46), a protector via through the whole board (Terms: to the plane, 1.44), a crystal pulled by the whole trace capacitance (Terms: (ΔC1 + ΔC2)/4, 4.0).

Outliers were estimator faults: an outer pour taken for the return plane (bldcm U2, 3.8 → 1.2) and a hop across an outline notch that found no plane (doorman D3, 0.15 → 0.52).

## 3. Decoupling (b)

- *Clusters.* Power pins cluster at 1.6 mm, each returning through its nearest ground pin. Parts without one (inductors, diodes, fuses) close through the plane under the power pin; split_supply returns on V−.
- *Pairing* follows the brief. With 'pin', the pin's paired caps and the spec's other owned caps act in parallel, so the nearest dominates. With 'nearest_pin', each cap is charged its loop to the IC's nearest pin cluster at the current poses. Unowned caps (caps_p < 0.5) and 'nearest_load' caps go to the nearest load pin on the rail (in a rail group, of its loads).
- *Pours.* When, at the current poses, a rail zone joins the power pin and the cap's rail pad and a ground zone joins the cap's ground pad and the return, L = L_mount,cap + L_mount,IC + (μ0d/π)·ln(D/r), mountings down to the nearer layer of the pair. Inner pairs come first (an outer pour under the parts is perforated by their pads), then thinner dielectrics; otherwise the straight-hop loop applies, for near and far caps alike. The spreading term matches a sheet solve to 0.4% median. On 41 routed decaps in pour mode, routed/estimate is 1.04, against 0.94 for straight hops [C].
- *Budgets.* An IC's transient splits over all its power pins on every rail, so each pin may present n_IC·Z_t (Z_t = 5%·V/I) up to the 100 MHz handover to package and die capacitance; before, a 100-pin MCU's lone VDDA pin carried all 300 mA (0.9 nH). A 100 nF 0402 (ESL 0.5 nH) meets that target while L_loop ≤ L_pin − ESL, 3–8 nH per MCU pin, so it rarely binds. The budget is therefore held between L_c, the loop with the capacitor beside its pin (four rotations, evaluated on the board), and 2L_c: u = 1 marks careful practice, since the loop also carries HF current that radiates and couples. Stability capacitors (VCAP, LDO output) and module bulk capacitors get max(10 nH, L_c): they need C and ESR at the regulator's crossover (≤ 1 MHz), where 10 nH adds 63 mΩ, below LDO ESR windows of 0.1–1 Ω.
- *Human boards* (1,471 structures): median u 0.82 (p10 0.44, p90 1.61). Load caps are 39% over budget (median u 0.88), VCAP bypass 23% (64% and u 3.2 under the HF rule), regulator outputs 2%, converter outputs 5%.

## 4. Coupling (c)

**Theorem 2.** At r ≫ h, a closed loop of area A at height h over a plane is a quadrupole, dipoles +Aẑ at +h and −Aẑ at −h; a path closed through the plane by vias is a horizontal dipole 2hẑ × chord. Two closed loops couple as M ∝ h_a·h_v·A_a·A_v/r⁵ ([lens-sy](lens-sy.md) D1).

**Near field.** M = (μ0/4π)Σ∫∫ds·dt/|r| over segment pairs, the aggressor imaged: the inner integral is closed-form, asinh((l−t0)/ρ) + asinh(t0/ρ), the outer uses 3–6 Gauss points, ρ ≥ 0.3 mm. Point-to-point quadrature overstates crossing pairs up to 12× [C].

**Capacitive.** First order in potential coefficients with the image: C_m = Σ C_a C_v p_av, p_av = (1/4πε0)(1/r − 1/√(r² + 4h²)). Patch strength comes from the air side: C_x = s(2C′_air(s, h) − ε0s/h), within 4% of a moment-method solve for s/h ≥ 1.5 [C].

**Validation [C].** Inductive, against PEEC-solved loops with probes 4–20 mm away: median 10.6%, p90 36%. Capacitive, against moment-method patches: median 9.8%, p90 16%.

## 5. Crystal (d)

C′(w, h, εr) times the XIN and XOUT nets' half-perimeters, stretched by 1 + 0.05√ℓ, changes the Pierce load by (ΔC1 + ΔC2)/4 and pulls by S: 16 ppm/pF for an AT-cut MHz crystal, 8 ppm/pF at 32 kHz. Hammerstad–Jensen C′ reads 3.8% low (max 5.7%) against fe_field2d [C].

## 6. Thermal (e)

**Fin.** G_s = Σ k_cu t_i f_i + k_FR4 t_FR4 (f = 1 for layers half covered by zones, else 0.2); λ = √(G_s/h_tot), h = 10 W/m²K per side. A point source raises T = P·K0(r/λ)/(2πG_s), its own disk (1 − xK1(x))/(πa²h_tot), x = a/λ. Adiabatic edges are images: one ring (36) computed, the rest a continuum λR·K1(R/λ)/(G_s L_x L_y).

**Theorem 3 (heat balance).** The board-average rise is ΣP/(h_tot·A) for every placement. Placement moves only the excess T − T̄, so budgets apply to it: a hot spot ≤ 20 K above the mean, and victims' rise from neighbours. olimex-dcdc (5.4 W) peaks 157 K above ambient, 149 K of it the mean (excess 18 K, u 0.9).

**Loss split (E5).** A converter's loss goes 0.5 V·I_out·(1 − D) to the rectifier, 15% to the inductor and the rest to the switches; power-path heat, (I/n)²R_on per element, comes from the brief. Against tm_board_thermal_fv (two-layer board, five sources) the fin is within 7.2% median (p90 13.4%) [C].

## 7. World node (f)

- *Cable CM.* ωMI/Z_cm + ωC_mV at 100 MHz (Z_cm 150 Ω), against 5 µA (Ott [S]), windowed by the copper gap between aggressor and connector: 1 to 15 mm, 0 beyond 30 mm, a cubic step between (beyond 15 mm it is below 10⁻³ of the budget). Human boards run 3–4 orders below the budget.
- *ESD surge path.* L′·ℓ·(1 + 0.11√ℓ) (connector → protector) + L_via; distance past the protected pin counts twice, a lateral offset is free. An adjacent trace picks up k·L·dI/dt (k ≈ 0.2); ≤ 40 V at 37.5 A/ns (IEC 61000-4-2 level 4) gives 5.3 nH.
- *Antenna feed.* 0.015 dB/mm × the feed terminals' minimum spanning tree.

## 8. Human boards: does the physics prefer the human placement? [C]

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

Of 2,321 material better-than-human local moves, the estimator or brief explains 506 (22%): *assignment* 274 (the part sits > 15 mm from every human partner: bulk caps paired as HF, far protectors), *unroutable* 135 (no single-layer route, mostly BGA escapes) and *route* 97 (no longer better once grid-routed around other nets' pads). The human explains 1,815: *trade-offs* 920 that worsen other physics or wirelength (coupling 393, thermal 181) and *slack* 895 that worsens nothing (decap 481).

## 9. Performance [C]

Caches are invalidated per sub-term. Every coupling sub-term a move touches goes to one kernel call; cable pickup beyond its window is exactly zero; a thermal move updates one column and row. A cap serving the nearest of n loads caches each candidate loop against its parts' pose ids, so a load move that keeps the cap's nearest load costs only the search.

`delta` on random single-part moves (numba, shared 4-core host): sparkfun-xrp (87 physics parts) median 40 µs, p90 137 µs, p99 0.68 ms, from 131 µs, 2.1 ms and 7.4 ms. Over 29,040 moves on 82 boards, median 22 µs, p90 70 µs, p99 0.32 ms; the slowest board's p90 is 0.36 ms (buspirate5, whose 25-LED rail took 0.77 ms before the candidate cache). `delta` equals the `total` difference to 2.4e-7 with accepted moves in between. Construction takes 9 ms on split B and 35 ms on split C (median; max 0.39 s), plus 0.5–0.8 s once per process to import numba and load its cached kernels. The Python fallback is about 12× slower.

## 10. Priors that matter, and open questions

Within a term, rankings ignore the budget (u is linear below it); budgets set the balance between terms. The priors that matter most are the hot-loop class priors (L_max ∝ t_sw²/C_oss), the ESD pickup (k, 40 V), the victim budgets and the converter loss split. Open: snubber, bootstrap and charge-pump loops are unpriced; multi-drop victims follow netlist order; antenna overruns come from misidentified feeds.

## Sources

- Grover, *Inductance Calculations* [S]; Ruehli 1972 [S]; Hammerstad and Jensen 1980 [S]; Ott, *EMC Engineering* [S]; Abramowitz and Stegun 9.8 [S].
- Scripts: [pt_validate_kernels.py](../../../tools/research/physics/pt_validate_kernels.py), [pt_routed_calib.py](../../../tools/research/physics/pt_routed_calib.py), [pt_human_perturb.py](../../../tools/research/physics/pt_human_perturb.py), [pt_grid_route.py](../../../tools/research/physics/pt_grid_route.py); solvers [pw_peec.py](../../../tools/research/physics/pw_peec.py), [pw_sheet.py](../../../tools/research/physics/pw_sheet.py), [fe_field2d.py](../../../tools/research/physics/fe_field2d.py), [tm_board_thermal_fv.py](../../../tools/research/physics/tm_board_thermal_fv.py).

See also: [pdn-and-commutation](pdn-and-commutation.md), [fields-si-emi](fields-si-emi.md), [thermal-physics](thermal-physics.md), [lens-sy](lens-sy.md), [schematic-to-physics](schematic-to-physics.md), [joint-place-route](joint-place-route.md), [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md), [exact-physics-options](exact-physics-options.md) (using exact physics instead).
