# Place terms: what a placement spends, estimated fast

**TL;DR**
- **One currency.** Each structure reports spend over allocation, u = v/a, priced by φ(u): linear below budget, a quadratic barrier above, logarithmic beyond 10×. Weights are brief confidence × calibrated ownership; every allocation is the brief's budget or a documented E5 prior.
- **Loops (a, b).** Partial inductances with plane images and Hammerstad–Jensen strip self terms are within 5% (median; max 9.4%) of PEEC on 324 routed hot and decoupling loops. The estimator, on straight pad-to-pad hops, reads 8–11% low because routes detour, yet orders cap positions as PEEC does in 93–94% of pairs [C].
- **Other terms** (median error against a finer solver) [C]: inductive coupling 11% (PEEC), capacitive 10% (moment method), crystal C′ 4% (Field2D), thermal fin 7% (finite volume), ESD path 3.4% (PEEC), plane-pair spreading 0.4% (sheet solve).
- **Human boards (112).** Shuffling a term's parts scores worse than the human in 85–99% of shuffles for every term but thermal (42%; 94% once all terms count). Local 1–5 mm moves and rotations are worse in 75–92% for loops, crystals and antennas, 61–65% for coupling. Of 2,191 material better-than-human moves, 76% are human slack or trade-offs, 24% trace to the estimator or the brief [C].
- **Speed.** `delta` median 23 µs (p90 159 µs). Cold `total` ≤ 2 ms up to 300 parts. Construction ≤ 0.25 s on split B, 5 ms without structures. numba and Python agree to 1.4e-13 [C].

Code: [`kae.physics.place_terms`](../../../kae/src/kae/physics/place_terms.py) (`Terms(board, brief)`: `total`, `delta`, `breakdown`, `parts`, `structures_of`); kernels [`_kernels.py`](../../../kae/src/kae/physics/_kernels.py); priors [`priors.py`](../../../kae/src/kae/physics/priors.py). The brief is [comprehension](comprehension.md). Tags: [C] computed by [pt_validate_kernels.py](../../../tools/research/physics/pt_validate_kernels.py) or [pt_human_perturb.py](../../../tools/research/physics/pt_human_perturb.py); [S] secondary.

## 1. One currency

Each structure s returns a spend v_s in physical units, with allocation a_s and u_s = v_s/a_s. The objective is

J = Σ_s c_s φ(u_s),  φ(u) = u (u ≤ 1);  u + β(u−1)² (1 < u ≤ u_sat);  φ(u_sat) + φ′(u_sat)·u_sat·ln(u/u_sat) (beyond),

with β = 4, u_sat = 10, and c_s = confidence × calibrated ownership; φ is C¹.
Over-budget structures dominate. Beyond 10× a structure has failed (on human boards, mostly misidentified structures), and the log tail keeps a gradient without swamping other terms.

| Term | Spend | Default allocation (E5) |
|---|---|---|
| (a) commutation | loop L (nH), owned input caps in parallel | overshoot: L_max = σ²/(2C_oss ln(1/a′)), σ = t_sw/2.563, a = (0.85V_abs − V_in)/V_in |
| (b) decap | loop L (nH) per power-pin cluster | n·Z_t/(2π·100 MHz), Z_t = 5%·V/I(pin count) |
| (c) coupling | noise (mV) = 1e3·M·dI/dt + ΔV·C_m/(C_m + C_v + t_sw/Z_v) | feedback 10, sense 1, analog 1 mV |
| (d) crystal | pulling (ppm) = S·C′·ℓ, S = C1/(2(C0 + C_L)²) | 5 ppm |
| (e) thermal | rise above the board mean (K) | sources 20 K; victims by class |
| (f) world | cable CM (µA); ESD surge path (nH); feed loss (dB) | 5 µA (Ott); 5.3 nH; 0.5 dB |

A null input voltage (13 of 64 cells) takes 24 V, above 90% of the corpus's named inputs. Ownership is recalibrated, logit q = 0.67 + 0.515·logit p, to kae.circuit's measured reliability (p 0.24 right 52%, p 0.96 91%). Components are cached against their parts' pose epochs, so `delta` recomputes only what a move touches.

## 2. Loop inductance (a, b)

**Theorem 1.** For a closed chain of straight segments over a perfectly conducting plane, L = Σ_ij [M(s_i, s_j) + M(s_i, s_j*)]. Here s_j* is the mirror image of s_j, horizontal parts reversed and vertical kept. Self terms use the conductor's geometric mean distance (GMD), and a chain that ends on the plane is closed by it. *Proof:* images replace the plane, and a partial inductance is ∫A·dl over a segment (Ruehli [S]). For parallel filaments, M = (μ0/4π)[G(e1) − G(e1−l1) − G(e0) + G(e0−l1)] with G(u) = u·asinh(u/d) − √(u² + d²) (Grover [S]).

**Strip self term.** A filament overstates wide strips over a near plane by 20–107% [C]. Taking L_self = M(ℓ, a) − M(ℓ, d_eff), with a = 0.2235(w + t) and d_eff = a·exp(L′_HJ/0.2), gives a per-length slope equal to Hammerstad–Jensen's L′ = Z0,air/c0 (within 1% in the unit test) while keeping the end terms.

**Estimator.** Terminals are pad-group centroids, taken in current order.
- *Board hops* are straight strips at the height h of the nearest plane, read from a per-side raster at the loop centroid.
- *Body hops* inside a part (capacitor electrodes, IC lead frame) sit at h + z_body with vertical ties.
- *Side changes* add a via.
- *Pairs* with |cos θ| ≥ 0.3 use the parallel-filament formula at the GMD of the linearly varying offset: ln GMD = [F(d2) − F(d1)]/(d2 − d1), F(p) = ½p·ln(p² + z²) − p + z·atan(p/z), which stays finite for crossing hops. Adjacent oblique pairs use Grover's corner formula.
- *Ground return.* A ground hop over its own plane runs in parallel with the via return C: L = A + M_AB + (B + M_AB)(C − M_AB)/(B + C).

**Guards.** With them, none of the 1,286 human-board loops is non-positive [C].

- *Separation:* conductors on one layer stay ≥ (w1 + w2)/2 + clearance apart, image included.
- *Pin pitch:* a part's internal path is at least the nearest pin-to-pin distance, so a cluster centroid cannot sit on a ground ball.
- *Under-part hops:* a hop under a part's own internal path runs on the far layer or behind a plane, so it cannot cancel that path.
- *Floor:* L ≥ the parts' internal loops over an ideal surface return.

**Validation [C]** compares each geometry three ways: PEEC (pw_peec, filaments across the width), Theorem 1 on the A*-routed segments, and the estimator on straight hops.

| Comparison | n | median \|err\| | p90 | max | bias | Spearman |
|---|---|---|---|---|---|---|
| Closed forms vs PEEC, hot loops | 180 | 5.0% | 7.6% | 9.2% | +5.0% | 0.998 |
| Closed forms vs PEEC, decap loops | 144 | 5.3% | 7.9% | 9.4% | +5.3% | 0.999 |
| Estimator vs PEEC, hot loops | 180 | 11.3% | 29.2% | 36.4% | −11.3% | 0.964 |
| Estimator vs PEEC, decap loops | 144 | 8.2% | 26.7% | 33.6% | −8.2% | 0.968 |
| Pair rules vs all-pair quadrature, oblique | 400 | 0.5% | 1.6% | 4.0% | +0.1% | 0.999 |
| ESD strip + via vs PEEC | 16 | 3.4% | 7.1% | 8.3% | +3.4% | 0.994 |

Geometries: a 1206 (hot) or 0402 (decap) cap 1.5–7 mm from an IC pin pair; h 0.1–1.5 mm, w 0.25–2 mm, four orientations, lateral or via return; oblique loops with sides ≥ w + 0.5 mm apart.

The estimator's bias is the route: a straight hop is shorter than the routed one. Ranking survives. Within each (h, w, return) set, it orders cap positions and orientations as PEEC does in 92.9% of 954 pairs (hot loops) and 94.1% of 760 (decaps), counting pairs whose PEEC values differ by more than 2%.

On human boards, pad-avoiding routes are 1.14× the straight length (median). Against [rb passports](real-board-passports.md)' HF loop on 15 cells, the estimate is 0.39× rb (median; p10 0.17, p90 1.11), Spearman 0.51: rb follows the human's real copper and overstates narrow strips 1.5–3×, so only ranks count.

**Regime.** Quasi-static (loops ≪ λ/10, a few cm at 200 MHz); planes act as PEC above about 1 MHz.

## 3. Decoupling (b)

- *Clusters.* Power pins cluster at 1.6 mm. Each cluster is a structure whose return is the nearest ground pin.
- *No return pin.* Parts without one close through the plane under the power pin: inductors (converter_output and converter_input), diodes and fuses (entry). split_supply returns on V−.
- *Owned caps.* Caps with calibrated ownership ≥ ½·p_max act in parallel, so the nearest dominates.
- *Many identical loads.* On rails with ≥ 3 loads and raw p ≤ 0.35 (keyboards, LED strings), each cap is charged its loop to the nearest load pin at the current poses.
- *Plane pair.* An adjacent rail/ground plane pair gives L = L_mount,cap + L_mount,IC + (μ0d/π)·ln(D/r). The spreading term matches a finite-plane sheet solve to 0.4% median (max 4.2%, edge effects) [C].

## 4. Coupling (c)

**Theorem 2.** At r ≫ h, a closed loop of area A at height h over a plane is a quadrupole: dipoles +Aẑ at +h and −Aẑ at −h. A path closed through the plane by vias is a horizontal dipole 2hẑ × chord. Two closed loops thus couple as M ∝ h_a·h_v·A_a·A_v/r⁵ ([lens-sy](lens-sy.md) D1).

**Near field.** M = (μ0/4π)Σ∫∫ds·dt/|r| over segment pairs, with the aggressor imaged. The inner integral is closed-form, asinh((l−t0)/ρ) + asinh(t0/ρ), and the outer uses 3–6 Gauss points. ρ ≥ 0.3 mm, since distinct conductors' axes cannot meet. Point-to-point quadrature overstates crossing pairs up to 12× [C].

**Capacitive.** First order in potential coefficients with the image: C_m = Σ C_a C_v p_av, with p_av = (1/4πε0)(1/r − 1/√(r² + 4h²)). Patch strength comes from the air side, because a patch's external dipole is set by ε0 ([lens-sy](lens-sy.md) D1): C_x = s(2C′_air(s, h) − ε0s/h), within 4% of a moment-method solve for s/h ≥ 1.5 [C]. Victim loops with a ground return close through the plane.

**Validation [C].**
- *Inductive:* against the EMF a PEEC-solved 6 mm loop (h 0.1, 0.4 mm) induces in closed and via-legged probes 4–20 mm away. Median 10.6%, p90 36%, Spearman 0.996. Dipoles read up to 40% low at 1–2 loop sizes.
- *Capacitive:* against moment-method patches 0.5–1 mm at h 0.1–0.5 mm, 2–20 sides apart. Median 9.8%, p90 16%, max 24%.

## 5. Crystal (d)

C′(w, h, εr) × half-perimeter of the XIN/XOUT nets pulls the crystal by S: 16 ppm/pF for an AT-cut MHz crystal, 8 ppm/pF at 32 kHz. Hammerstad–Jensen C′ reads 3.8% low (max 5.7%) against fe_field2d for w 0.15–0.5 mm, h 0.1–1.5 mm [C].

## 6. Thermal (e)

**Fin.** G_s = Σ k_cu t_i f_i + k_FR4 t_FR4, with f = 1 for layers half covered by zones and 0.2 otherwise. λ = √(G_s/h_tot), with h = 10 W/m²K per side.
- *Point source:* T = P·K0(r/λ)/(2πG_s).
- *Own disk:* (1 − xK1(x))/(πa²h_tot), with x = a/λ.
- *Edges:* adiabatic, as images. One ring (36 images) is computed; the rest is a continuum adding λR·K1(R/λ)/(G_s L_x L_y).

**Theorem 3 (heat balance).** The board-average rise is ΣP/(h_tot·A) for every placement. Placement moves only the excess T − T̄, so budgets apply to the excess: a hot spot ≤ 20 K above the mean, and victims' rise from neighbours. Example: olimex-dcdc (5.4 W on 51 × 36 mm) peaks 157 K above ambient, of which the mean is 149 K; the local excess is 18 K (u 0.9).

**Loss split (E5).** kae.circuit charges a converter's loss to its controller; Terms splits it:
- *rectifier:* 0.5 V·I_out·(1 − D);
- *inductor:* 15%;
- *switches:* the rest, at least 20%, split 60/40 when discrete.

On olimex this gives U1 3.3 W, D2 1.3 W, L1 0.8 W.

**Validation [C]** against tm_board_thermal_fv (60 × 40 mm two-layer board, five sources, four probes): 7.2% median (p90 13.4%) with one ring plus the tail; 17% without images; 5.6% with two rings. At the sources the fin reads 10–13% low: within λ_d ≈ 8 mm the source layer runs hotter than the far layer.

**Human boards:** board mean rise 17.7 K median (p90 61 K, max 196 K; 51 boards); sources 46 K absolute (p90 101 K), of which 10 K local excess (p90 39 K); victims' local excess 0.2 K (p90 15 K).

## 7. World node (f)

- *Cable CM.* ωMI/Z_cm + ωC_mV at 100 MHz (trapezoid envelopes, Z_cm 150 Ω), against 5 µA (Ott [S]). Human boards run 3–4 orders below it.
- *ESD surge path.* L′·ℓ(connector → protector) + L_via; distance past the protected pin counts twice; a lateral offset is free (route through the pad). Budget: an adjacent trace picks up k·L·dI/dt (k ≈ 0.2); ≤ 40 V at 37.5 A/ns (IEC 61000-4-2 level 4) gives 5.3 nH. PEEC: 3.4% median [C].
- *Antenna feed.* 0.015 dB/mm × the feed terminals' minimum spanning tree.

## 8. Human boards: does the physics prefer the human placement? [C]

On all 112 kaebench boards, each term's parts are perturbed:
- *local:* three 1–5 mm translations and 90°/180°/270° rotations per part;
- *global:* 20 shuffles of a term's parts to random legal-ish poses.

Share is worse/(worse + better); a move is *material* if some structure moves by ≥ 1% of its allocation; a structure is *credible* if some component has all pad-to-pad hops ≤ 15 mm in the human placement.

| Term | Boards | Translate worse | Rotate worse | Shuffle worse | Shuffle, all terms worse |
|---|---|---|---|---|---|
| commutation | 30 | 79% (234) | 75% (160) | 99% (562) | 88% |
| decap | 78 | 84% (1950) | 80% (1047) | 99% (1459) | 90% |
| coupling | 32 | 61% (851) | 65% (527) | 89% (640) | 95% |
| crystal | 24 | 82% (163) | 92% (146) | 99% (480) | 100% |
| thermal | 49 | 45% (335) | – | 42% (821) | 94% |
| ESD | 27 | 61% (275) | 78% (221) | 97% (436) | 92% |
| world CM | 32 | 63% (94) | 46% (80) | 85% (639) | 92% |
| antenna | 6 | 84% (171) | 77% (87) | 98% (112) | 89% |

Brackets give decided counts: material moves (local) and credible structures (shuffle).
- *Shuffles.* Scattering beats the human only for thermal, by spreading heat; with every term counted the same shuffles are worse in 94%. Humans cluster a converter for its hot loop and pay in heat.
- *Local moves.* These are closer calls. Human decaps sit a median 6 mm (centre to centre) from their partners, and better moves gain a median 5% of budget.

Where human boards spend their budgets:

| Term | Structures | Median spend (p90) | Median u | Over budget |
|---|---|---|---|---|
| commutation | 63 | 2.6 (7.1) nH | 1.3 | 57% |
| decap | 1214 | 2.9 (10.3) nH | 0.47 | 29% |
| coupling | 245 | 0.24 (30) mV | 0.18 | 25% |
| crystal | 29 | 2.6 (6.7) ppm | 0.51 | 21% |
| thermal (excess) | 250 | 6.8 (35) K | 0.37 | 27% |
| ESD | 486 | 3.5 (18) nH | 0.65 | 28% |
| world CM | 272 | 0.004 (0.14) µA | 0.0008 | 0.4% |
| antenna | 25 | 0.84 (3.8) dB | 1.7 | 68% |

**Better-than-human local moves, classified:** *route* (no longer better once its hops are grid-routed around other nets' pads), *assignment* (the part sits > 15 mm from every human partner: doubtful pairing), *unroutable* (no single-layer route), *trade-off* (worsens other physics or wirelength), *slack* (worsens nothing).

| Term | route | assignment | unroutable | trade-off | slack |
|---|---|---|---|---|---|
| commutation | 7 | 24 | 6 | 33 | 48 |
| decap | 26 | 217 | 95 | 126 | 436 |
| coupling | 0 | 0 | 0 | 377 | 144 |
| crystal | 0 | 1 | 0 | 17 | 23 |
| thermal | 0 | 0 | 0 | 160 | 24 |
| ESD | 22 | 115 | 13 | 61 | 91 |
| world CM | 0 | 0 | 0 | 55 | 23 |
| antenna | 0 | 0 | 0 | 13 | 34 |

Estimator or brief: 526 of 2,191 (24%), mostly assignment (bulk caps paired as HF, a module's 3V3 output taken as a load, protectors 20+ mm from their connector) and BGA escapes. Human: 1,665 (76%); slack is small (median 5% of budget) and 39% of it is rotations, which humans align for assembly.

## 9. Performance [C]

`delta` over 29,040 random single-part moves (numba, loaded 4-core host): median 23 µs, p90 159 µs, p99 1.0 ms, equal to the `total` difference to 3e-8. By moved part: 13–20 µs for decap, commutation, ESD and crystal parts; 48–70 µs for thermal, coupling and world CM; 200–300 µs for aggressor-loop members. Cold `total`: ≤ 2.1 ms up to 300 parts, 7–13 ms at 395–621. Construction: 5 ms without structures, 6 ms on split B, 0.18 s on split C (max 0.63 s); numba's disk cache loads in 0.25 s, a first compile takes 3–5 s. The Python fallback is about 12× slower.

## 10. Priors that matter, and open questions

Within a term, rankings ignore the budget (u is linear in spend below budget). Budgets set the balance between terms. Share of human structures over budget:

| Term | 0.5× budget | nominal | 2× budget | Prior |
|---|---|---|---|---|
| commutation | 73% | 57% | 30% | C_oss, t_sw by class (L_max ∝ t_sw²/C_oss) |
| decap | 49% | 29% | 16% | 5% ripple, current by pin count, 100 MHz |
| ESD | 65% | 28% | 18% | 40 V, k = 0.2 |
| coupling | 35% | 25% | 20% | victim budgets; dI/dt = I/t_sw |
| thermal | 43% | 27% | 9% | h, the brief's P_W |
| crystal | 55% | 21% | 3% | 5 ppm; C1, C0, C_L |

The priors that matter most are the hot-loop class priors, the victim budgets and excitations (their heavy tail comes from brief classes), and the converter loss split and h.

Open questions: straight hops read about 10% low (a 1.1–1.14 detour factor removes the bias, not the ranks); multi-drop victims follow netlist order; CM never binds and antenna overruns come from misidentified feeds; batching an aggressor's victims in one kernel call is the next speed step.

## Sources

- Grover, *Inductance Calculations* [S]; Ruehli 1972 [S]; Hammerstad and Jensen 1980 [S]; Ott, *EMC Engineering* [S]; Abramowitz and Stegun 9.8 [S].
- Scripts: [pt_validate_kernels.py](../../../tools/research/physics/pt_validate_kernels.py), [pt_human_perturb.py](../../../tools/research/physics/pt_human_perturb.py), [pt_grid_route.py](../../../tools/research/physics/pt_grid_route.py); solvers [pw_peec.py](../../../tools/research/physics/pw_peec.py), [pw_sheet.py](../../../tools/research/physics/pw_sheet.py), [fe_field2d.py](../../../tools/research/physics/fe_field2d.py), [tm_board_thermal_fv.py](../../../tools/research/physics/tm_board_thermal_fv.py).

See also: [pdn-and-commutation](pdn-and-commutation.md), [fields-si-emi](fields-si-emi.md), [thermal-physics](thermal-physics.md), [lens-sy](lens-sy.md), [schematic-to-physics](schematic-to-physics.md), [joint-place-route](joint-place-route.md), [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md).
