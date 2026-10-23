# Place terms: what a placement spends, estimated fast

**TL;DR**
- **One currency.** Each structure reports spend over allocation, u = v/a, priced by φ(u): linear below budget, a quadratic barrier above, logarithmic beyond 10×. Weights are brief confidence × calibrated ownership; every allocation is the brief's budget or a documented E5 prior.
- **Loops (a, b).** Partial inductances with plane images and Hammerstad–Jensen strip self terms are within 5% (median; max 9.4%) of PEEC on 324 routed hot and decoupling loops. Each straight pad-to-pad hop is stretched by its expected detour 1 + c√ℓ, fitted on the routed copper of 69 human boards. Against that copper the estimate is unbiased: routed/estimate is 1.00 for hot loops and surge paths compared like for like and 1.19 for decaps (p10 0.66, p90 2.14) [C].
- **Other terms** (median error against a finer solver) [C]: inductive coupling 11% (PEEC), capacitive 10% (moment method), crystal C′ 4% (Field2D), thermal fin 7% (finite volume), ESD path 3.4% (PEEC), plane-pair spreading 0.4% (sheet solve).
- **Human boards (112).** Shuffles score worse than the human in 87–100% for every term but thermal (42%; 90% with all terms). Local moves are worse in 72–91% for loops, crystals and antennas, 54–61% for ESD and coupling. Over budget: decaps 29% → 11% (new priors), ESD 28% → 46% and hot loops 57% → 68% (detours). Of 1,948 material better-than-human moves, 73% are human slack or trade-offs [C].
- **Speed.** One kernel call evaluates every coupling sub-term a move touches. `delta` on sparkfun-xrp (387 parts) runs at median 48 µs, p90 173 µs (it was 131 µs and 2.1 ms); over the corpus, median 25 µs, p90 86 µs. numba and Python agree to 1e-12 [C].

Code: [`kae.physics.place_terms`](../../../kae/src/kae/physics/place_terms.py) (`Terms(board, brief)`: `total`, `delta`, `breakdown`, `parts`, `structures_of`); kernels [`_kernels.py`](../../../kae/src/kae/physics/_kernels.py); priors [`priors.py`](../../../kae/src/kae/physics/priors.py). The brief is [comprehension](comprehension.md). Tags: [C] computed by [pt_validate_kernels.py](../../../tools/research/physics/pt_validate_kernels.py), [pt_routed_calib.py](../../../tools/research/physics/pt_routed_calib.py) or [pt_human_perturb.py](../../../tools/research/physics/pt_human_perturb.py); [S] secondary.

## 1. One currency

Each structure s returns a spend v_s in physical units, with allocation a_s and u_s = v_s/a_s. The objective is

J = Σ_s c_s φ(u_s),  φ(u) = u (u ≤ 1);  u + β(u−1)² (1 < u ≤ u_sat);  φ(u_sat) + φ′(u_sat)·u_sat·ln(u/u_sat) (beyond),

with β = 4, u_sat = 10, and c_s = confidence × calibrated ownership; φ is C¹.
Over-budget structures dominate. Beyond 10× a structure has failed (on human boards, mostly misidentified structures), and the log tail keeps a gradient without swamping other terms.

| Term | Spend | Default allocation (E5) |
|---|---|---|
| (a) commutation | loop L (nH), owned input caps in parallel | overshoot: L_max = σ²/(2C_oss ln(1/a′)), σ = t_sw/2.563, a = (0.85V_abs − V_in)/V_in |
| (b) decap | loop L (nH) per power-pin cluster | n_IC·Z_t/(2π·100 MHz) per pin, Z_t = 5%·V/I(pin count); stability and module caps 10 nH |
| (c) coupling | noise (mV) = 1e3·M·dI/dt + ΔV·C_m/(C_m + C_v + t_sw/Z_v) | feedback 10, sense 1, analog 1 mV |
| (d) crystal | pulling (ppm) = S·C′·ℓ/4, S = C1/(2(C0 + C_L)²) | 5 ppm |
| (e) thermal | rise above the board mean (K) | sources 20 K; victims by class |
| (f) world | cable CM (µA); ESD surge path (nH); feed loss (dB) | 5 µA (Ott); 5.3 nH; 0.5 dB |

A null input voltage (13 of 64 cells) takes 24 V, above 90% of the corpus's named inputs. Ownership is recalibrated, logit q = 0.67 + 0.515·logit p, to kae.circuit's measured reliability (p 0.24 right 52%, p 0.96 91%).

## 2. Loop inductance (a, b)

**Theorem 1.** For a closed chain of straight segments over a perfectly conducting plane, L = Σ_ij [M(s_i, s_j) + M(s_i, s_j*)]. Here s_j* is the mirror image of s_j, horizontal parts reversed and vertical kept. Self terms use the conductor's geometric mean distance (GMD), and a chain that ends on the plane is closed by it. *Proof:* images replace the plane, and a partial inductance is ∫A·dl over a segment (Ruehli [S]). For parallel filaments, M = (μ0/4π)[G(e1) − G(e1−l1) − G(e0) + G(e0−l1)] with G(u) = u·asinh(u/d) − √(u² + d²) (Grover [S]).

**Strip self term.** A filament overstates wide strips over a near plane by 20–107% [C]. Taking L_self = M(ℓ, a) − M(ℓ, d_eff), with a = 0.2235(w + t) and d_eff = a·exp(L′_HJ/0.2), gives a per-length slope equal to Hammerstad–Jensen's L′ = Z0,air/c0 (within 1%) while keeping the end terms.

**Estimator.** Terminals are pad-group centroids, taken in current order.
- *Board hops* are strips at the height h of the nearest plane: the median of five samples along the hop. A notch of the outline takes the plane beside it, and a side whose hops lie mostly over a plane is referenced throughout, so a straight hop across a hole cannot turn the loop into a free-space loop.
- *Detour.* A hop of length ℓ is stretched about its midpoint by 1 + c√ℓ (ℓ in mm; §2a).
- *Body hops* inside a part (capacitor electrodes, IC lead frame) sit at h + z_body with vertical ties. *Side changes* add a via.
- *Pairs* with |cos θ| ≥ 0.3 use the parallel-filament formula at the GMD of the linearly varying offset: ln GMD = [F(d2) − F(d1)]/(d2 − d1), F(p) = ½p·ln(p² + z²) − p + z·atan(p/z), finite for crossing hops. Adjacent oblique pairs use Grover's corner formula.
- *Ground return.* A ground hop over its own plane runs in parallel with the via return C: L = A + M_AB + (B + M_AB)(C − M_AB)/(B + C).

**Guards** keep every human-board loop positive [C]: conductors on one layer stay ≥ (w1 + w2)/2 + clearance apart, image included; a part's internal path spans at least one pin pitch; a hop under a part's own path runs on the far layer or behind a plane; L ≥ the parts' internal loops over an ideal surface return.

**Validation [C]**: PEEC (pw_peec, filaments across the width) against Theorem 1 on the A*-routed segments and the estimator on straight hops (no detour).

| Comparison | n | median \|err\| | p90 | max | bias | Spearman |
|---|---|---|---|---|---|---|
| Closed forms vs PEEC, hot loops | 180 | 5.0% | 7.6% | 9.2% | +5.0% | 0.998 |
| Closed forms vs PEEC, decap loops | 144 | 5.3% | 7.9% | 9.4% | +5.3% | 0.999 |
| Estimator vs PEEC, hot loops | 180 | 11.3% | 29.2% | 36.4% | −11.3% | 0.964 |
| Estimator vs PEEC, decap loops | 144 | 8.2% | 26.7% | 33.6% | −8.2% | 0.968 |
| Pair rules vs all-pair quadrature, oblique | 400 | 0.5% | 1.6% | 4.0% | +0.1% | 0.999 |
| ESD strip + via vs PEEC | 16 | 3.4% | 7.1% | 8.3% | +3.4% | 0.994 |

Geometries: a 1206 or 0402 cap 1.5–7 mm from an IC pin pair; h 0.1–1.5 mm, w 0.25–2 mm, four orientations. Straight hops read low because routes detour, but cap positions and orientations come out in PEEC's order in 93–94% of pairs whose PEEC values differ by > 2%.

**Regime.** Quasi-static (loops ≪ λ/10, a few cm at 200 MHz); planes act as PEC above about 1 MHz.

### 2a. Routed copper

[pt_routed_calib.py](../../../tools/research/physics/pt_routed_calib.py) follows each hop of 693 modules on 69 human boards along its least-L′ copper path (the critical router's recheck, KiCad-refilled zones) [C]. Routed length over straight length:

| Hop class | Hops | Median | p90 | c in 1 + c√ℓ (90% board bootstrap) |
|---|---|---|---|---|
| decap rail | 614 | 1.17 | 2.22 | 0.127 (0.100–0.145) |
| surge path | 297 | 1.17 | 2.45 | 0.110 (0.065–0.130) |
| hot loop | 32 | 1.02 | 1.51 | 0.087 (0.035–0.155) |
| crystal net | 41 | 0.97 | 1.97 | 0.048 (0.010–0.100) |

The detour grows with distance (decap hops: 1.13 below 2 mm, 1.67 beyond 15 mm), as round obstacles in a random field; √ℓ fits better than a constant. A pad-avoiding single-layer route alone gives 1.14 at 2–5 mm. Inductance routed/estimate, median (p10–p90), before → after the stretch:

| Kind | n | Straight hops | With detour |
|---|---|---|---|
| decap | 379 | 1.35 (0.73–2.50) | 1.19 (0.66–2.14) |
| hot loop, loop's own cap | 32 | 1.08 (0.72–1.75) | 1.00 (0.67–1.60) |
| surge path, reference's via | 214 | 1.23 (0.78–2.86) | 1.00 (0.63–1.77) |

Like for like means the reference's definitions: a cell's loop through the brief loop's capacitor only (Terms: owned caps in parallel; 1.46 otherwise), a protector via through the whole board (Terms: down to the plane; 1.44), a crystal pulled by the whole trace capacitance (Terms: the Pierce load's (ΔC1 + ΔC2)/4; 4.0).

The outliers (routed/estimate) were estimator faults:
- *bldcm U2 (3.8), aftonsparv U1 (3.4).* The plane-pair branch paired the rail plane with an outer ground pour 0.24 mm away; the return runs in the inner plane 1.08 mm away. Now 1.2 and 3.1; the human reaches aftonsparv's capacitor over 14 mm of trace instead of a via at the pin.
- *doorman D3 (0.15).* A straight hop crossed a notch of the outline, where one plane lookup at the loop centroid found no plane. Now 0.52: the 27 mm hop's expected detour (1.65) overshoots the human's (1.17).
- *pmw3610 U2 +1V8 (0.41).* An unpaired capacitor 2 mm from the pin serves it. Now 1.5.

## 3. Decoupling (b)

- *Clusters.* Power pins cluster at 1.6 mm. Each cluster is a structure whose return is the nearest ground pin; parts without one (inductors, diodes, fuses) close through the plane under the power pin, and split_supply returns on V−.
- *Caps.* The cluster's paired caps and every unpaired cap of the spec act in parallel, so the nearest dominates; caps whose calibrated ownership is below ½·p_max drop out. With the brief's pairing nearest_load (rail groups, entry bulk), each cap is charged its loop to the nearest load pin at the current poses.
- *Pours.* When a zone of the rail joins the power pin and the cap's rail pad, and a ground zone joins the cap's ground pad and the return, at the current poses, L = L_mount,cap + L_mount,IC + (μ0d/π)·ln(D/r). The mountings run down to the nearer layer of the pair. Inner pairs come first, since an outer pour under the parts is perforated by their pads; thinner dielectrics next. Otherwise the loop is the straight-hop one. The spreading term matches a sheet solve to 0.4% median [C]. On routed boards this form reads 1.30× below the copper (98 decaps), the straight-hop form 1.16×: humans often reach the plane over a trace rather than a via at the pin, and the reference treats pours as 2 mm strips. `Knobs(pour_decaps=False)` turns it off.
- *Budgets.* An IC's transient splits over all its power pins on every rail: each pin may present n_IC·Z_t up to the 100 MHz handover to package and die capacitance. Before, a 100-pin MCU's lone VDDA pin carried all 300 mA (0.9 nH). A 100 nF 0402 (ESL 0.5 nH) on 1 nH of loop resonates near 16 MHz; above that it meets n_IC·Z_t to 100 MHz while L_loop ≤ L_pin − ESL, 3–8 nH per MCU pin. A regulator's stability capacitor (VCAP bypass, linear regulator output) and a module's bulk capacitor get 10 nH. They need C and ESR at the regulator's crossover (≤ 1 MHz), where 10 nH adds 63 mΩ, below the 0.1–1 Ω ESR windows of LDO datasheets. Under the HF rule, human VCAP loops sat at u 3.2 (64% over budget).

## 4. Coupling (c)

**Theorem 2.** At r ≫ h, a closed loop of area A at height h over a plane is a quadrupole: dipoles +Aẑ at +h and −Aẑ at −h. A path closed through the plane by vias is a horizontal dipole 2hẑ × chord. Two closed loops thus couple as M ∝ h_a·h_v·A_a·A_v/r⁵ ([lens-sy](lens-sy.md) D1).

**Near field.** M = (μ0/4π)Σ∫∫ds·dt/|r| over segment pairs, with the aggressor imaged. The inner integral is closed-form, asinh((l−t0)/ρ) + asinh(t0/ρ), and the outer uses 3–6 Gauss points; ρ ≥ 0.3 mm, since distinct conductors' axes cannot meet. Point-to-point quadrature overstates crossing pairs up to 12× [C].

**Capacitive.** First order in potential coefficients with the image: C_m = Σ C_a C_v p_av, with p_av = (1/4πε0)(1/r − 1/√(r² + 4h²)). Patch strength comes from the air side, because a patch's external dipole is set by ε0 ([lens-sy](lens-sy.md) D1): C_x = s(2C′_air(s, h) − ε0s/h), within 4% of a moment-method solve for s/h ≥ 1.5 [C].

**Validation [C].** Inductive, against the EMF a PEEC-solved 6 mm loop induces in probes 4–20 mm away: median 10.6%, p90 36%, Spearman 0.996. Capacitive, against moment-method patches 2–20 sides apart: median 9.8%, p90 16%.

## 5. Crystal (d)

C′(w, h, εr) × the XIN and XOUT nets' half-perimeters, stretched by 1 + 0.05√ℓ, changes the Pierce load by (ΔC1 + ΔC2)/4 and pulls by S: 16 ppm/pF for an AT-cut MHz crystal, 8 ppm/pF at 32 kHz. Hammerstad–Jensen C′ reads 3.8% low (max 5.7%) against fe_field2d [C].

## 6. Thermal (e)

**Fin.** G_s = Σ k_cu t_i f_i + k_FR4 t_FR4 (f = 1 for layers half covered by zones, else 0.2); λ = √(G_s/h_tot), h = 10 W/m²K per side. A point source raises T = P·K0(r/λ)/(2πG_s), its own disk (1 − xK1(x))/(πa²h_tot), x = a/λ. Adiabatic edges are images: one ring (36) computed, the rest a continuum λR·K1(R/λ)/(G_s L_x L_y).

**Theorem 3 (heat balance).** The board-average rise is ΣP/(h_tot·A) for every placement. Placement moves only the excess T − T̄, so budgets apply to it: a hot spot ≤ 20 K above the mean, and victims' rise from neighbours. olimex-dcdc (5.4 W on 51 × 36 mm) peaks 157 K above ambient, 149 K of it the mean; the local excess is 18 K (u 0.9).

**Loss split (E5).** A converter's loss goes 0.5 V·I_out·(1 − D) to the rectifier, 15% to the inductor and the rest (≥ 20%) to the switches: on olimex U1 3.3 W, D2 1.3 W, L1 0.8 W.

**Validation [C]** against tm_board_thermal_fv (60 × 40 mm two-layer board, five sources): 7.2% median (p90 13.4%) with one ring plus the tail; 17% without images. At the sources the fin reads 10–13% low.

## 7. World node (f)

- *Cable CM.* ωMI/Z_cm + ωC_mV at 100 MHz (trapezoid envelopes, Z_cm 150 Ω), against 5 µA (Ott [S]), windowed by the gap between the aggressor's and the connector's copper: 1 to 15 mm, 0 beyond 30 mm, a cubic step between. Beyond 15 mm it is below 10⁻³ of the budget; a move far from a connector then costs nothing to evaluate. Human boards run 3–4 orders below the budget.
- *ESD surge path.* L′·ℓ·(1 + 0.11√ℓ) (connector → protector) + L_via; distance past the protected pin counts twice; a lateral offset is free (route through the pad). Budget: an adjacent trace picks up k·L·dI/dt (k ≈ 0.2); ≤ 40 V at 37.5 A/ns (IEC 61000-4-2 level 4) gives 5.3 nH.
- *Antenna feed.* 0.015 dB/mm × the feed terminals' minimum spanning tree.

## 8. Human boards: does the physics prefer the human placement? [C]

On all 112 kaebench boards, each term's parts are perturbed: three 1–5 mm translations and 90°/180°/270° rotations per part (local), and 20 shuffles of a term's parts to random legal-ish poses (global). Share is worse/(worse + better); a move is *material* if some structure moves by ≥ 1% of its allocation; a structure is *credible* if some component has all pad-to-pad hops ≤ 15 mm in the human placement.

| Term | Boards | Translate worse | Rotate worse | Shuffle worse | Shuffle, all terms worse |
|---|---|---|---|---|---|
| commutation | 30 | 80% (261) | 72% (188) | 99% (562) | 88% |
| decap | 78 | 87% (1493) | 87% (781) | 97% (1485) | 87% |
| coupling | 32 | 61% (831) | 61% (531) | 90% (640) | 96% |
| crystal | 24 | 80% (167) | 91% (147) | 100% (480) | 98% |
| thermal | 52 | 44% (377) | – | 42% (890) | 90% |
| ESD | 27 | 54% (282) | 78% (221) | 97% (438) | 91% |
| world CM | 32 | 65% (101) | 46% (79) | 87% (617) | 90% |
| antenna | 6 | 81% (167) | 77% (87) | 98% (112) | 99% |

Brackets give decided counts: material moves (local) and credible structures (shuffle). Against the straight-hop estimator with the earlier priors, decap moves agree more with the human (87% vs 84% of translations, 87% vs 80% of rotations) and ESD moves less (54% vs 61%): the surge detour grows as ℓ^1.5, so shortening a long human surge path gains more. Scattering beats the human only for thermal, by spreading heat; with every term counted the same shuffles are worse in 90%.

Where human boards spend their budgets (over-budget share before the routed-copper calibration and the decap priors in brackets; then at half and twice the budget):

| Term | Structures | Median spend (p90) | Median u | Over budget | At 0.5× | At 2× |
|---|---|---|---|---|---|---|
| commutation | 63 | 2.7 (9.5) nH | 1.41 | 68% (57%) | 75% | 32% |
| decap | 1176 | 2.3 (10.1) nH | 0.17 | 11% (29%) | 19% | 6% |
| coupling | 243 | 0.24 (32) mV | 0.18 | 26% (25%) | 37% | 21% |
| crystal | 29 | 2.9 (7.7) ppm | 0.58 | 24% (21%) | 62% | 7% |
| thermal (excess) | 284 | 7.6 (36) K | 0.41 | 29% (27%) | 45% | 11% |
| ESD | 487 | 4.7 (31) nH | 0.89 | 46% (28%) | 74% | 21% |
| world CM | 272 | 0.0001 (0.11) µA | 0.00002 | 0.4% (0.4%) | 0% | 0% |
| antenna | 25 | 0.84 (3.8) dB | 1.68 | 68% (68%) | 80% | 44% |

On the same briefs, the detours alone raise ESD from 28% to 46%, hot loops from 62% to 68% and crystals from 21% to 24%; the decap priors alone lower decaps from 23% to 11% (VCAP bypass 64% → 25%, median u 3.2 → 0.41; load 24% → 11%).

**Better-than-human local moves, classified:** *route* (no longer better once its hops are grid-routed around other nets' pads, instead of the expected detour), *assignment* (the part sits > 15 mm from every human partner: doubtful pairing), *unroutable* (no single-layer route), *trade-off* (worsens other physics or wirelength), *slack* (worsens nothing).

| Term | route | assignment | unroutable | trade-off | slack |
|---|---|---|---|---|---|
| commutation | 19 | 13 | 1 | 33 | 48 |
| decap | 42 | 223 | 69 | 59 | 191 |
| coupling | 0 | 0 | 0 | 397 | 138 |
| crystal | 0 | 2 | 0 | 14 | 31 |
| thermal | 0 | 0 | 0 | 175 | 37 |
| ESD | 22 | 118 | 12 | 72 | 103 |
| world CM | 0 | 0 | 0 | 54 | 24 |
| antenna | 0 | 0 | 0 | 21 | 30 |

Estimator or brief: 521 of 1,948 (27%), mostly assignment (bulk caps paired as HF, protectors 20+ mm from their connector) and BGA escapes. Human: 1,427 (73%); decap slack fell from 436 to 191 as the looser decap budgets made fewer moves material.

## 9. Performance [C]

Caches are invalidated by dirty flags per sub-term, so moving a switch-node part recomputes only capacitive halves. Every coupling sub-term a move touches, aggressor or victim side, goes to one kernel call that lays shapes out once and reads poses from arrays; cable pickup beyond its window is exactly zero; a thermal move updates T by one column and row.

`delta`, random single-part moves after warm-up (numba, loaded 4-core host): on sparkfun-xrp (387 parts, 87 with physics), median 48 µs, p90 173 µs, p99 0.53 ms, down from 131 µs, 2.1 ms and 7.4 ms; its worst part, an MCU in 50 structures, takes 0.6 ms (was 2.2 ms). Over 29,240 moves on the 82 boards with physics, median 25 µs, p90 86 µs, p99 0.34 ms (was 23 µs, 159 µs, 1.0 ms); the slowest board's p90 is 0.35 ms. `delta` equals the `total` difference to 1e-7 with accepted moves in between. Construction takes 9 ms without structures, 16 ms on split B and 0.38 s on split C (median; 0.33 s of it imports numba, once per process); plane rasters are built on first use. The Python fallback is about 12× slower.

## 10. Priors that matter, and open questions

Within a term, rankings ignore the budget (u is linear in spend below budget); budgets set the balance between terms (§8 gives the shares at half and twice them). The priors that matter most are the hot-loop class priors (C_oss, t_sw: L_max ∝ t_sw²/C_oss), the ESD pickup (k, 40 V), the victim budgets and excitations, and the converter loss split and h.

Open questions: whether the objective should assume a via at every decap pin (the pour form) or human-like routing (1.30× more on routed boards); multi-drop victims follow netlist order; CM never binds and antenna overruns come from misidentified feeds.

## Sources

- Grover, *Inductance Calculations* [S]; Ruehli 1972 [S]; Hammerstad and Jensen 1980 [S]; Ott, *EMC Engineering* [S]; Abramowitz and Stegun 9.8 [S].
- Scripts: [pt_validate_kernels.py](../../../tools/research/physics/pt_validate_kernels.py), [pt_routed_calib.py](../../../tools/research/physics/pt_routed_calib.py), [pt_human_perturb.py](../../../tools/research/physics/pt_human_perturb.py), [pt_grid_route.py](../../../tools/research/physics/pt_grid_route.py); solvers [pw_peec.py](../../../tools/research/physics/pw_peec.py), [pw_sheet.py](../../../tools/research/physics/pw_sheet.py), [fe_field2d.py](../../../tools/research/physics/fe_field2d.py), [tm_board_thermal_fv.py](../../../tools/research/physics/tm_board_thermal_fv.py).

See also: [pdn-and-commutation](pdn-and-commutation.md), [fields-si-emi](fields-si-emi.md), [thermal-physics](thermal-physics.md), [lens-sy](lens-sy.md), [schematic-to-physics](schematic-to-physics.md), [joint-place-route](joint-place-route.md), [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md), [exact-physics-options](exact-physics-options.md) (using exact physics instead).
