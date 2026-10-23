# Place terms: what a placement spends, estimated fast

**TL;DR**
- **One currency.** Every structure reports spend over allocation, u = v/a, priced by φ(u): linear below budget, a quadratic barrier above it, a logarithmic tail beyond 10×. Weights are the brief's confidence times calibrated ownership; every allocation is the brief's budget or a documented E5 prior.
- **Loops (a, b).** The closed forms (partial inductances with plane images, Hammerstad–Jensen strip self terms) are within 5% (median; max 9.4%) of PEEC on 324 routed hot and decoupling loops. On straight pad-to-pad hops the estimator reads 8–11% low because real routes detour, but it orders cap positions as PEEC does in 93–94% of pairs [C].
- **The other terms.** Inductive coupling is within 11% (median) of PEEC-induced EMF and capacitive coupling within 10% of a moment-method solve. Crystal C′ is within 4% of Field2D, the thermal fin with edge images within 7% of the FV solver, the ESD surge path within 3.4% of PEEC, and plane-pair spreading within 0.4% of a sheet solve [C].
- **Human boards (112).** Shuffling a term's parts at random scores worse than the human placement in 89–99% of shuffles for every term but thermal (42%; but 94% worse once all terms count, so clustering heat is a trade-off). Local 1–5 mm moves and rotations score worse in 75–92% for loops, crystals and antennas and 61–65% for coupling. Of 2,191 material better-than-human moves, 76% are human slack or trade-offs and 24% trace to the estimator or the brief [C].
- **Speed.** `delta` takes a median 23 µs (p90 159 µs; aggressor moves 200–300 µs); a cold `total` is ≤ 2 ms up to 300 parts; construction is ≤ 0.25 s on split-B boards and 5 ms without structures. numba and the pure-Python fallback agree to 1.4e-13 [C].

Code: [`kae.physics.place_terms`](../../../kae/src/kae/physics/place_terms.py) (`Terms(board, brief)`: `total`, `delta`, `breakdown`, `parts`, `structures_of`), kernels in [`_kernels.py`](../../../kae/src/kae/physics/_kernels.py), priors in [`priors.py`](../../../kae/src/kae/physics/priors.py). Tags: [C] computed by [pt_validate_kernels.py](../../../tools/research/physics/pt_validate_kernels.py) or [pt_human_perturb.py](../../../tools/research/physics/pt_human_perturb.py), [I] inference, [S] secondary source. The brief that names the structures is [comprehension](comprehension.md).

## 1. One currency

Each structure s (a hot loop, a decoupling loop, a victim, a crystal, a thermal target, a world-node path) returns a spend v_s in physical units. Its allocation a_s comes from the brief's budget or an E5 prior, and u_s = v_s/a_s. The objective is

J = Σ_s c_s φ(u_s),  φ(u) = u for u ≤ 1;  u + β(u−1)² for 1 < u ≤ u_sat;  φ(u_sat) + φ′(u_sat)·u_sat·ln(u/u_sat) beyond,

with β = 4, u_sat = 10, and c_s = brief confidence × calibrated ownership. φ is C¹. Below budget, spend is priced linearly in budget units, so a nanohenry on a tight decap costs more than one on a loose one. Above it, the quadratic barrier makes the over-budget structure dominate. Beyond 10× budget the estimate says "fails" whatever its value, and on the human boards such values came from estimator outliers or misidentified structures, so the tail keeps a gradient without swamping every other term.

| Term | Spend | Default allocation (E5, `priors.py`) |
|---|---|---|
| (a) commutation | loop L (nH) through each owned input cap, in parallel | overshoot: L_max = σ²/(2 C_oss ln(1/a′)), σ = t_sw/2.563, a = (0.85 V_abs − V_in)/V_in |
| (b) decap | loop L (nH) per power-pin cluster | target impedance: n_pins Z_t/(2π·100 MHz), Z_t = 5% V/I(pin count) |
| (c) coupling | victim noise (mV) = 1e3·M·dI/dt + ΔV·C_m/(C_m + C_v + t_sw/Z_v) | per victim class: feedback 10, sense 1, analog 1 mV |
| (d) crystal | pulling (ppm) = S·C′·ℓ, S = C1/(2(C0 + C_L)²) | 5 ppm |
| (e) thermal | local rise above the board mean (K) | sources 20 K; victims per class (electrolytic 10 K) |
| (f) world | cable CM current (µA); ESD surge path (nH); antenna feed loss (dB) | 5 µA (Ott, class B); 5.3 nH; 0.5 dB |

Unknown converter input voltage (excite.V null in 13 of 64 cells) takes the documented high prior V_in = 24 V, above 90% of the 51 named inputs. Ownership is recalibrated: kae.circuit's p = 0.24 is right 52% of the time and p = 0.96 91%, so logit q = 0.67 + 0.515·logit p.

**Incrementality.** A structure is a reduction (sum, parallel, single) of components, each depending on a few parts. Component values are cached against those parts' pose epochs, so `delta` re-evaluates only what a move touches. The thermal Green matrix updates one column and one row.

## 2. Loop inductance (a, b)

**Theorem 1 (loop over a plane).** For a closed chain of straight segments above a perfectly conducting plane, L = Σ_i Σ_j [M(s_i, s_j) + M(s_i, s_j*)]. Here s_j* is the mirror image of s_j with horizontal components reversed and vertical kept, and M(s_i, s_i) uses the conductor's geometric mean distance (GMD). A chain that starts and ends on the plane is closed by it. *Proof:* replace the PEC by image currents; a partial inductance is ∫A·dl over one segment (Ruehli [S]). For parallel filaments, M = (μ0/4π)[G(e1) − G(e1−l1) − G(e0) + G(e0−l1)] with G(u) = u·asinh(u/d) − √(u² + d²) (Grover [S]).

**Strip self term.** The thin-filament per-length term 0.2·ln(2h/a) overstates wide strips over a close plane (+20% to +107% against PEEC [C]). The self term L_self(ℓ) = M(ℓ, a) − M(ℓ, d_eff), with a = 0.2235(w + t) and d_eff = a·exp(L′_HJ/0.2), has per-length slope exactly the Hammerstad–Jensen L′ = Z0,air/c0 (unit test: within 1%) and keeps the filament end terms.

**The estimator.** Terminals are pad-group centroids in current order.
- *Board hops* between parts are straight strips at the height h of the nearest plane under that side, read from a raster at the loop centroid.
- *Body hops* inside a part (capacitor electrodes, an IC's lead frame) are strips at h + z_body (E5 by package) with vertical terminations.
- *Side changes* add a via.
- *Pairs* with |cos θ| ≥ 0.3 use the parallel-filament formula over the projected overlap. The distance is the GMD of the linearly varying offset, ln GMD = [F(d2) − F(d1)]/(d2 − d1) with F(p) = ½p·ln(p² + z²) − p + z·atan(p/z), which stays finite for crossing hops. Adjacent pairs at an angle use Grover's corner formula.
- *Ground return.* A ground hop over a plane of its own net runs in parallel with the via return C through the plane, combined by the two-mesh reduction L = A + M_AB + (B + M_AB)(C − M_AB)/(B + C).

**Guards.** Each comes from a failure on a human board:
- *Separation floor.* Two conductors on one layer cannot overlap, so the lateral GMD is floored at (w1 + w2)/2 + clearance, and the image sees the same floored offset. Straight hops through each other gave −15.7 nH on emberone.
- *Pin-pitch floor.* A part's internal path between two pin groups is at least their nearest pin-to-pin distance. On obsidian a BGA's power-cluster centroid sat on a ground ball: −0.64 nH.
- *Under-part hops.* A hop that runs under a part's own internal path is taken on the far layer (board thickness below, on two-layer boards) or behind a plane (pair dropped). On siderakb, a cap beyond the far ground pin gave 0.006 nH; it now gives 13.9 nH, against 13.7 nH for the human's cap.
- *Floor.* L ≥ the parts' internal loops with an ideal return at the board surface.

After the guards, none of the 1286 human-board loops is non-positive [C].

**Validation [C].** Same geometry, three ways. The exact solver is PEEC (pw_peec: filaments across the width, PEC plane). "Closed forms" is Theorem 1 on the routed segments. The estimator works on straight pad-to-pad hops, and the loops are routed around their pads by grid A*.

| Comparison [C] | n | median \|err\| | p90 | max | bias | Spearman |
|---|---|---|---|---|---|---|
| Closed forms vs PEEC, hot loops (routed) | 180 | 5.0% | 7.6% | 9.2% | +5.0% | 0.998 |
| Closed forms vs PEEC, decap loops (routed) | 144 | 5.3% | 7.9% | 9.4% | +5.3% | 0.999 |
| Estimator (straight hops) vs PEEC, hot loops | 180 | 11.3% | 29.2% | 36.4% | −11.3% | 0.964 |
| Estimator vs PEEC, decap loops | 144 | 8.2% | 26.7% | 33.6% | −8.2% | 0.968 |
| Fast pair rules vs all-pair quadrature, oblique loops | 400 | 0.5% | 1.6% | 4.0% | +0.1% | 0.999 |
| ESD surge path (strip + via) vs PEEC | 16 | 3.4% | 7.1% | 8.3% | +3.4% | 0.994 |

Inputs: hot loops use a 1206 cap 2.5–7 mm from an IC pin pair; decap loops an 0402 1.5–5 mm from QFN pins; h = 0.1–1.5 mm, w = 0.25–2 mm, four orientations, lateral or via return. Oblique loops have opposite sides at least w + 0.5 mm apart. Where sides nearly coincide, the guards deliberately depart from the bare filament sum (median 18%), because there the filament sum heads to zero or below while a routable loop cannot.

The estimator's error is mostly the route: a straight hop is shorter than the routed loop. Ranking survives: within each geometry (h, w, return), the estimator orders cap positions and orientations as PEEC does in 92.9% of 954 pairs (hot loops) and 94.1% of 760 (decaps) whose PEEC values differ by more than 2%. Two checks on the human boards:
- *Routed detour.* Pad-avoiding routes measure 1.14× the straight length (median) on emberone's decap hops.
- *rb passports.* Against [rb_board_passports](real-board-passports.md)' HF loop on 15 human-board cells, the estimate is 0.39× rb (median; p10 0.17, p90 1.11) with Spearman 0.51, and within 15% on 4 cells. rb follows the human's actual copper and, by its own account, overstates narrow strips 1.5–3×, so only its ranks are evidence.

**Regime.** The model is quasi-static: loop size ≪ λ/10, i.e. a few cm at 200 MHz. Planes act as PEC above about 1 MHz (1 oz). Routes are straight: a real route's extra length adds L′ per mm, which the perturbation study prices with a router.

## 3. Decoupling specifics (b)

- *Pin clusters.* Power pins cluster by single linkage at 1.6 mm. Each cluster is a structure, with the nearest ground pin as its return.
- *Parts without a return pin.* Inductors (converter_output, converter_input), diodes and fuses (entry) close the loop through the plane under the power pin. split_supply uses the V− rail as its return.
- *Owned caps.* Caps with calibrated ownership ≥ ½ p_max act in parallel, so the nearest dominates.
- *Many identical loads.* On rails with ≥ 3 loads and raw p ≤ 0.35 (keyboards, LED strings), each cap is charged its loop to the nearest load power pin at the current poses.
- *Plane pair.* When rail and ground are an adjacent plane pair, L = L_mount,cap + L_mount,IC + (μ0 d/π)·ln(D/r). The spreading term agrees with a finite-plane sheet solve: 0.4% median (max 4.2%, from edge effects at D = 10–20 mm in a 30–60 mm plane) [C].

## 4. Coupling (c)

**Theorem 2 (loops over a plane, far field).** At r ≫ h, a closed loop of area A at height h is a magnetic quadrupole: dipoles +A ẑ at +h and −A ẑ at −h. A path closed through the plane by vias is a horizontal dipole 2h ẑ × chord. Two closed loops therefore couple as M ∝ h_a h_v A_a A_v/r⁵, falling 30 dB per doubling of distance ([lens-sy](lens-sy.md) D1).

**Near field.** M = (μ0/4π) Σ_ij ∫∫ ds·dt/|r| over segment pairs, with the aggressor imaged in the plane. The inner integral is closed-form, ∫_0^l dt/√((t−t0)² + ρ²) = asinh((l−t0)/ρ) + asinh(t0/ρ), and the outer one uses 3- or 6-point Gauss–Legendre. ρ ≥ 0.3 mm, the closest approach of two distinct conductors' axes. Point-to-point Gauss quadrature had overestimated a crossing pair 12× (2.1 nH against 0.18 nH from refined quadrature) [C].

**Capacitive.** First order in potential coefficients with the plane image: C_m = Σ C_a C_v p_av, with p_av = (1/4πε0)(1/r − 1/√(r² + 4h²)). Patch strengths are seen from the air side, because a patch over a plane radiates as a dipole set by ε0 whatever the dielectric ([lens-sy](lens-sy.md) D1). C_x = s(2C′_air(s, h) − ε0 s/h) for a square of side s, with C′_air from Hammerstad–Jensen; this is within 4% of a moment-method solve for s/h ≥ 1.5 [C]. The victim sees V = ΔV·C_m/(C_m + C_v + t_sw/Z_v): charge division into a high-impedance victim, C_m·dV/dt·Z_v into a low-impedance one.

**Victim loops.** A return hop between two ground terminals runs in the plane, so the victim is the signal path closed through the plane.

**Validation [C].**
- *Inductive.* loop_mutual_core against the EMF that a PEEC-solved aggressor (6 mm loop, h = 0.1 and 0.4 mm) induces in closed and via-legged probe victims 4–20 mm away: median 10.6%, p90 36%, max 45%, Spearman 0.996. The far-field dipoles read up to 40% low at 1–2 loop sizes, where neither the dipole nor the quadrature is exact.
- *Capacitive.* Against a method-of-moments solve for 0.5–1 mm patches at h = 0.1–0.5 mm, 2–20 sides apart: median 9.8%, p90 16%, max 24%, Spearman 0.998.

## 5. Crystal (d)

Trace capacitance C′(w, h, εr)·ℓ is the Hammerstad–Jensen per-length value times the half-perimeter of the XIN and XOUT nets, and it pulls the crystal by S ppm/pF. S is 16 ppm/pF for an AT-cut MHz crystal and 8 ppm/pF for 32 kHz. Against fe_field2d, Hammerstad–Jensen C′ reads 3.8% low (median; max 5.7%) for w = 0.15–0.5 mm, h = 0.1–1.5 mm, εr = 4.3 [C].

## 6. Thermal (e)

**Fin model.** The board is a fin with sheet conductance G_s = Σ k_cu t_i f_i + k_FR4 t_FR4, with f = 1 for layers whose zones cover half the board and 0.2 otherwise. With h_tot = h_top + h_bot (10 W/m²K each), λ = √(G_s/h_tot). A point source gives T(r) = P·K0(r/λ)/(2πG_s), and the source's own disk of radius a gives (1 − x·K1(x))/(πa²h_tot), x = a/λ. Adiabatic edges are images. One ring is computed (36 images); the rest is a continuum of density 1/(L_x L_y) beyond radius R, which adds λR·K1(R/λ)/(G_s L_x L_y), the same at every target.

**Theorem 3 (heat balance).** The board-average rise is ΣP/(h_tot·A) for every placement. Placement moves only the local excess T − T̄, so the budgets apply to the excess (sources: hot spot ≤ 20 K above the board mean; victims: rise from neighbours). This is why a 5.4 W converter on olimex-dcdc (51 × 36 mm) read 157 K: its board mean is 149 K, which no placement changes. Its local excess is 18 K (u = 0.9).

**Loss split.** kae.circuit puts a converter's whole loss on its controller. Terms splits it (E5):
- *Rectifier:* P_D = 0.5 V·I_out·(1 − D).
- *Inductor:* 15%.
- *Switches:* the rest, at least 20%, split 60/40 when discrete.

On olimex-dcdc: U1 3.3 W, D2 1.3 W, L1 0.8 W.

**Validation [C].** Against tm_board_thermal_fv (60 × 40 mm two-layer board, five 0.3–1 W sources, four probes):
- one ring of images plus the continuum tail: 7.2% median, 13.4% p90;
- no images: 17% median, 33% max;
- two rings: 5.6% median.

The fin reads 10–13% low at the sources themselves. On a 1.5 mm core, the source layer runs hotter than the far layer within λ_d = √(G_layer/g_z) ≈ 8 mm of the source, which a single fin cannot represent.

**Human boards** (h = 10 W/m²K per side, the brief's powers split as above):
- board mean rise: median 17.7 K, p90 61 K, max 196 K (51 boards);
- sources: 46 K absolute (p90 101 K), of which 10 K is local excess (p90 39 K);
- victims: local excess median 0.2 K (p90 15 K).

## 7. World node (f)

- *CM current.* I_cm = ω·M·I/Z_cm + ω·C_m·V at 100 MHz, with trapezoid envelopes for a 1 MHz switch and Z_cm = 150 Ω; the budget is 5 µA on a ≥ 1 m cable (Ott [S]). On human boards it is 3–4 orders below budget (median 0.002 µA): it rarely binds.
- *ESD surge path.* L′·ℓ(connector pin → protector) + L_via, with any distance beyond the protected pin's projection charged twice. Routing the protected net through the protector's pad makes a lateral offset free. The budget: a trace at minimum spacing picks up k·L·dI/dt with k ≈ 0.2. Keeping that within the 40 V a protected pin's clamp absorbs at 37.5 A/ns (IEC 61000-4-2 level 4) gives 5.3 nH. Against PEEC: 3.4% median, max 8.3% (h = 0.1–0.8 mm, ℓ = 2–20 mm) [C].
- *Antenna feed.* α (0.015 dB/mm at 2.4 GHz) times the Euclidean minimum spanning tree of the feed terminals, independent of the brief's order.

## 8. Human boards: does the physics prefer the human placement? [C]

On all 112 reference boards (kaebench suite) we perturb the human placement:
- *Local, per involved part:* three translations of 1–5 mm and rotations of 90°, 180° and 270°.
- *Global:* 20 shuffles of all of a term's parts to random legal-ish poses (no added courtyard overlap, inside the outline).

The reported share is worse/(worse + better). A move is *material* if it changes some structure by ≥ 1% of its allocation. A structure is *credible* if some component has all its pad-to-pad hops ≤ 15 mm in the human placement.

| Term | Boards | Translate, worse | Rotate, worse | Shuffle, worse | Shuffle, all terms worse |
|---|---|---|---|---|---|
| commutation | 30 | 79% (234) | 75% (160) | 99% (562) | 88% |
| decap | 78 | 84% (1950) | 80% (1047) | 99% (1459) | 90% |
| coupling | 32 | 61% (851) | 65% (527) | 89% (640) | 95% |
| crystal | 24 | 82% (163) | 92% (146) | 99% (480) | 100% |
| thermal | 49 | 45% (335) | – | 42% (821) | 94% |
| ESD | 27 | 61% (275) | 78% (221) | 97% (436) | 92% |
| world CM | 32 | 63% (94) | 46% (80) | 85% (639) | 92% |
| antenna | 6 | 84% (171) | 77% (87) | 98% (112) | 89% |

Local columns count material moves on credible structures, with the decided count in brackets; the shuffle column counts credible structures.

Reading the table:
- **Shuffles.** For every term, scattering its parts makes the physics worse than the human did, in 85–99% of shuffles; thermal is the exception.
- **Thermal shuffles.** Scattering heat sources lowers hot spots, but the same shuffles are worse in 94% once every term counts: the human clusters a converter's parts for its hot loop and pays in heat.
- **Local moves.** They are decided less often. Human decaps sit a median 6 mm (centre to centre) from their partners, and a better move improves the term by a median 5% of budget.

Where the budgets go (human placements):

| Term | Structures | Median spend (p90) | Median u | Over budget |
|---|---|---|---|---|
| commutation | 63 | 2.6 (7.1) nH | 1.3 | 57% |
| decap | 1214 | 2.9 (10.3) nH | 0.47 | 29% |
| coupling | 245 | 0.24 (30) mV | 0.18 | 25% |
| crystal | 29 | 2.6 (6.7) ppm | 0.51 | 21% |
| thermal (local excess) | 250 | 6.8 (35) K | 0.37 | 27% |
| ESD | 486 | 3.5 (18) nH | 0.65 | 28% |
| world CM | 272 | 0.004 (0.14) µA | 0.0008 | 0.4% |
| antenna | 25 | 0.84 (3.8) dB | 1.7 | 68% |

**Every material better-than-human local move is classified:**
- *estimator: route.* With hops routed around other nets' pads (45° grid router, L′ per mm of detour), the move is no longer better.
- *estimator: assignment.* The moved part sits > 15 mm from every partner in the human placement, so the brief's pairing is doubtful.
- *unroutable.* Some hop has no single-layer route.
- *human: trade-off.* The move worsens other physics or the part's signal wirelength.
- *human: slack.* It worsens nothing.

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

- **Estimator or brief: 526 of 2,191 (24%).**
  - *assignment (357):* bulk caps paired as HF decoupling, a module's 3V3 output treated as a load, protectors 20+ mm from their connector.
  - *unroutable (114):* BGA escapes and enclosed pins.
  - *route (55):* the straight hop runs through other pads.
- **Human: 1,665 (76%).**
  - *Slack:* small (median 5% of budget). 39% are rotations, which the human aligns for assembly rather than for the loop.
  - *Trade-off:* the move worsens other physics or wirelength.

## 9. Performance [C]

Measured on 29,040 random single-part moves on all boards, numba path, with the 4-core host loaded:
- *`delta`:* median 23 µs, p90 159 µs, p99 1.0 ms. It matches the change in `total` to 3e-8.
- *By what the part belongs to:* decap 17 µs, ESD 14, crystal 13, commutation 20, thermal 48, coupling 70, world CM 54.
- *Aggressor-loop members* touch every victim and connector: 200–300 µs.

Cold `total` (every cache invalid):
- median 0.11 ms;
- ≤ 2.1 ms up to 300 parts;
- 7 ms at 395 parts, 11–13 ms at 452–621.

Construction (fresh process, numba cache warm):

| Boards | Median | Max |
|---|---|---|
| no structures | 5 ms | 33 ms |
| split B | 6 ms | 0.25 s |
| split C | 0.18 s | 0.63 s |

The kernels load from numba's on-disk cache in 0.25 s; compiling them the first time on a checkout takes 3–5 s. The pure-Python fallback runs the same source about 12× slower (a loop takes 69 µs against 4.7 µs).

## 10. Priors that matter, and open questions

Within one term, rankings do not depend on its budget, since u is linear in spend below budget. Budgets set the balance between terms. Share of human structures over budget at half, nominal and double budget:

| Term | 0.5× budget | nominal | 2× budget | Prior that sets the budget |
|---|---|---|---|---|
| commutation | 73% | 57% | 30% | C_oss and t_sw by class (L_max ∝ t_sw²/C_oss); GaN 100 pF |
| decap | 49% | 29% | 16% | 5% ripple, current by pin count, hand-over at 100 MHz |
| ESD | 65% | 28% | 18% | 40 V, k = 0.2 |
| coupling | 35% | 25% | 20% | victim budgets (sense, analog 1 mV) and dI/dt = I/t_sw |
| thermal | 43% | 27% | 9% | h = 10 W/m²K per side; the brief's P_W |
| crystal | 55% | 21% | 3% | 5 ppm; C1, C0, C_L by class |

Priors that matter most:
- the hot-loop class priors, since 57% of human cells sit over budget;
- the victim budgets and excitations, whose heavy tail is mostly driven by brief classes (an open-drain alert line classed as analog);
- the converter loss split and h.

**Open questions:**
- *Route detour.* Straight hops read about 10% low; a detour factor of 1.1–1.14 (measured on emberone) would remove the bias without changing ranks.
- *Multi-drop victims.* Victim loops are drawn through multi-drop nets in netlist order.
- *CM and antenna.* CM never binds (3–4 orders under budget). Antenna overruns come from misidentified feeds.
- *Speed.* Aggressor moves are slow; batching all of one aggressor's victims in one kernel call is the next step.

## Sources

- Grover, *Inductance Calculations* (parallel and corner filaments) [S]; Ruehli 1972, partial inductance [S]; Hammerstad and Jensen 1980, microstrip [S]; Ott, *EMC Engineering* (5 µA CM limit) [S]; Abramowitz and Stegun 9.8 (K0, K1) [S].
- Scripts: [pt_validate_kernels.py](../../../tools/research/physics/pt_validate_kernels.py), [pt_human_perturb.py](../../../tools/research/physics/pt_human_perturb.py), [pt_grid_route.py](../../../tools/research/physics/pt_grid_route.py); exact solvers [pw_peec.py](../../../tools/research/physics/pw_peec.py), [pw_sheet.py](../../../tools/research/physics/pw_sheet.py), [fe_field2d.py](../../../tools/research/physics/fe_field2d.py), [tm_board_thermal_fv.py](../../../tools/research/physics/tm_board_thermal_fv.py).

See also: [pdn-and-commutation](pdn-and-commutation.md), [fields-si-emi](fields-si-emi.md), [thermal-physics](thermal-physics.md), [lens-sy](lens-sy.md), [schematic-to-physics](schematic-to-physics.md), [joint-place-route](joint-place-route.md), [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md).
