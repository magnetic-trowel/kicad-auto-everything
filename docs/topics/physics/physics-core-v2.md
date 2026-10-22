# Physics core v2: one model of what the copper is doing

**TL;DR**
- **The core models copper, not nets.** Its unit is the Piece (track segment, pad, via, pour or plane tile, part body, world conductor). Each piece has a Passport per band: current shares, energies, exact counterfactual value for every budget, topological role, and the Jobs these imply. The graph includes chassis, cables, heatsink and enclosure; budgets name closed loops; every number is a Belief with an exactness class.
- **Eight kernels:** topology, complex sheet operator, complex-image PEEC, response, floors, modal Q ledger, morphology, belief/VOI. One factorization per (operator, band, topology epoch) serves solves, adjoints, lead fields, passports and exact edit prices.
- **One number says when cheap physics holds: the spectrum of an edit's Woodbury matrix.** Exact change = Σ first-order_i/(1 − λ_i). At DC, λ_max reaches exactly 1 at a topological event; at AC, |λ| ≥ 1 is lens LS's εQ ≥ 1. On a test plane pair [C], a cut grown to a 0.5 mm neck has λ = 0.990 (first-order misses 90×); a decap removed at the anti-resonance has |λ| = 1.36 (first-order has the wrong sign); a 3 mm slit stays at 0.84 at all frequencies (crack law within 14%).
- **An objective's class belongs to a band.** A load's PDN impedance is a monotone self term at 300 MHz (no added decap raises it) but not at 1 GHz (all 150 sites raise it) [C]. Five classes (self, interaction, non-variational, damage, legal) are handled differently throughout.
- **Build order:** data model, topology, sheet and response first, accepted on brute-force exactness (≤ 4×10⁻¹¹ here), the mutation benchmark and one real board.

Tags: [C] [pc2_core_skeleton.py](../../../tools/research/physics/pc2_core_skeleton.py) on a 30 × 20 mm PWR/GND plane pair (2,384 cells, slot, two loads, Kelvin taps, six decaps; DC and telegrapher bands; uncalibrated) unless a script is named; [I] inference; [S] secondary. API: [physics-core-v2-api](physics-core-v2-api.md).

## Key facts

Lens map: [CD](lens-cd.md) pieces and counterfactuals; [CT](lens-ct.md) world and topology; [SY](lens-sy.md) loop budgets and lead fields; [VP](lens-vp.md) floors and classes; [LS](lens-ls.md) operator and dispatcher; [TH](lens-th.md) Q ledger; [IN](lens-in.md) beliefs.

### 1. Data model

| Object | Definition and key fields | Written by |
|---|---|---|
| **Piece** | The unit of copper, with an id that survives remeshing: track segment, pad, via (barrel, pads, antipads), pour or plane tile (2h to 2 mm, finer at slots and necks), part body, world conductor. The mesh below is disposable | code |
| **World conductor** | Chassis, cable (Z_cm(f)), heatsink, enclosure, LISN, test setup; bonds are branches; C_i,ext from one electrostatic solve ([CT D2](lens-ct.md)) | code; facts from humans |
| **Extended graph** | Per band: pieces, parts in band models, partial R, L, M, and C to references, victims, world | code |
| **Topology layer** | Per band: b0, b1, block–cut tree, cycle basis, holes per reference, return words ([CT29](../../ideas/physics-first/lens-ct.md)), board–world cut, closure type per port, symmetries; events bump the epoch | code (K1) |
| **Band, regime cell** | Band: a frequency interval with source spectra. Regime cell (structure × band): ℓ_m(f)/h, ℓ_m/a, ℓ_m/W, θ = ωℓ/v, Z0/Z, ωτ_e, f/f_p, edit radius r; it picks the representation (§6) | code |
| **Closed-loop budget** | Names the victim's closed observation loop (terminal pair plus closure), sources, metric, bound, criticality c/L and, per band, a class (§5) | detectors, LLM, human; class by code |
| **Passport** | Piece × band: topological role (bridge, shared edge, chord, dead end, ring, handle, cut member, linked); share per source; transport vs circulation κ; charge destination; energies; exact removal change per budget with its Woodbury spectrum; damping share per mode; jobs. Lazy, cached per epoch | code (K4) |
| **Job** | Verb (carries, returns, images, lowers or raises p→q, senses, anchors, spreads heat, holds charge, damps, radiates, bonds, shields, dead), objects, band, its exact counterfactual, value Σλ_k\|ΔB_k\|/slack_k, designed or parasitic | code; designed flag by humans or LLM |
| **Mode, floor** | Mode: complex frequency, Q, channel shares (1/Q = Σ 1/Q_k), participation per piece. Floor: value, kind, certificate, τ = bound/floor | code (K6, K5) |
| **Belief** | Value, unit, exactness class (§2), relative_to (model, assumptions, epoch), interval, model-form spread (level and shape), validity, lineage | every kernel |

Test-board passports [C]: the tile beside the slot tip lowers the Kelvin-tap coupling Z_SA (+47% if removed) and carries Z_AA (+15%) at DC; decap C3 at 300 MHz lowers Z_BA (+25.5% if removed) but raises Z_SA (−19%), a job conflict for `separate_jobs` ([CD22](../../ideas/physics-first/lens-cd.md)).

### 2. Exactness ladder

The fidelity tiers F0–F4 ([solver-ladder](solver-ladder.md)) grade accuracy; this ladder grades guarantees, relative to a stated model.

| Class | Meaning | Examples |
|---|---|---|
| E0 topological | Metric-free, for any geometry with this connectivity | b0, b1, articulation points, cut sets, return words |
| E1 algebraic | Exact on the discretized model, to round-off | Woodbury, Thevenin, Tellegen, Foster: within 4×10⁻¹¹ of re-factorization [C] |
| E2 certified | A variational bound on the continuum model | floors, Prager–Synge brackets, HS, capacity hull, coarse-PEEC L ≥ L, §4's DC bounds |
| E3 asymptotic | A closed form with a known error law | crack laws, complex images (0.4–3.5%), MS2, wedge exponents |
| E4 calibrated | A spread from calibration data | surrogates, conformal σ |
| E5 conjectured | Unchecked | LLM hypotheses; unknown world conductors |

E1 is not E2: on a notched strip the cell-graph resistance lies 0.1–0.6% above the certified Prager–Synge upper bound at 2–8 cells/mm, where the bracket is about 0.2% wide [C, reusing vp_floors]. Compliance verdicts on class-A quantities quote the bracket; E1 counterfactuals inherit their mesh's error.

### 3. Kernels

| Kernel | In → out | Exactness | Cost, one core | Incremental rule | Merges |
|---|---|---|---|---|---|
| K1 Topology | band graph → invariants, return words, board–world cut, closure types, events, symmetry checks | E0 | O(V + E), ms [I] | recheck the dirty component; an event is a changed invariant | ct_cut_topology, pc_refplane connectivity, CT27–CT29, LA12, JPR2's physics events |
| K2 Sheet operator | stack, band → ∇·(Z_s⁻¹∇φ) − Y_p·φ = −s, complex γ² = Z_s·Y_p: DC, heat, diffusion, screening, waves, posts (wire medium), eigenmodes; φ and ψ solves for brackets | E1; brackets E2 | factor 6 ms (2.4k cells) to 1.2 s (153k); solve 0.2–41 ms [C] | rank-k Woodbury in an epoch; refactor reusing the symbolic analysis | pw_sheet, op_topopt_pour, xd_sheet, tm_board_thermal_fv, ls_post_lattice; objects 1, 2, 6 of [cross-workstream-synthesis](cross-workstream-synthesis.md) |
| K3 Complex-image PEEC | pieces, stackup, band → partial R, L_p, P; 4–6 complex images per intact plane, meshed planes only at slots and edges; C with C_ext; Foster eddy models; passive SPICE reduction | E1; images E3; coarse L ≥ L (E2) | 0.1–1.7 ms per loop [sl_loop_peec]; 4.4k branches 1.5–3 s per band [cd_conductor_passport] | bordered updates; windows refactor in seconds | sl_loop_peec, pw_peec, fe_peec_plane, cd, ls_thin_sheet (SIM46, LS1) |
| K4 Response | any factored reciprocal operator (sheet, PEEC, thermal, MNA, harmonic balance) → states, adjoints (also periodic), lead fields, attribution and χ, exact removals (Woodbury) and additions (Thevenin) with their spectrum, leverage, Foster check; crack screens | E1; screens E3; DC first-order E2 | rank-32 quote 5 ms–1.4 s, or 0.2 ms from a cached window; Thevenin 0.2–53 ms [C] | one Woodbury update moves states, adjoints and cached blocks | cd, ct, sy and vp edit laws; dr_noise_adjoint; SIM24, SIM25, OP38, OP41, CD2–CD6 |
| K5 Floors | net or structure → Beckmann, convex relaxation with dual certificate, capacity hull, HS, cavity bound, fab floor; τ | E2 | Beckmann 150 µs, convex minutes [vp_floors] | Beckmann every move; convex warm-started per epoch | vp_floors, DR18, OP57, JPR30 |
| K6 Modal Q ledger | energy matrices plus one dissipation matrix → complex modes, Q and channel shares, noise temperature, εQ estimates of r, damper menus | E1; cavity forms E3 | ms–s [th_damping_ledger] | Rayleigh-quotient shifts; recompute at events | th_damping_ledger, fe_cavity, th_dissipation_noise |
| K7 Morphology | geometry → signed distance, open/close at minimum width and space, ±etch corners, necks, acid traps, legalizing projection, critical area | exact geometry | ms per 10⁶ pixels [I] | local signed distance in the dirty box | OP50, OP51, XD66, XD94, XD95, TM38 |
| K8 Belief and VOI | beliefs, sensitivities → propagated spread, lineage-aware fusion, EVPPI per cost (robustify included), escalation z = Φ⁻¹(1 − c/L) | bookkeeping | seconds per decision [in_emi_voi] | only decisions whose footprint changed | in_*, SIM1, SIM8, SIM10 |

SPICE and full-wave solvers stay external engines that K4 and the dispatcher call; prices are the optimizer's duals.

### 4. The edit spectrum: when cheap physics holds

For an edit that removes branches B, let P_B = diag(y_B)·A_Bᵀ·Y⁻¹·A_B (k solves); for one added impedance z, λ = −Z_th/z. Over the eigenpairs of P_B,

 ΔZ_qp (exact) = Σ_i c_i/(1 − λ_i), where Σ_i c_i is the first-order (adjoint) price.

Four lens results are special cases: CD's 1/(1 − ρ) is k = 1; the crack laws of CT, SY and VP are its closed-form sum for slits; at DC, 0 ≤ λ ≤ 1, and λ = 1 exactly when the edit cuts copper off (a K1 event: an infinite price if that copper holds a terminal, none if it merely floats); at AC, |λ| ≥ 1 means the edit moves a mode by more than its bandwidth, LS's εQ ≥ 1.

The radius r = max|λ| comes free with each exact quote, which thus says whether first-order was safe. At DC, two certified bounds follow: 1 ≤ exact/first-order ≤ 1/(1 − λ_max) for self terms, and |exact − first-order| ≤ ‖w_q‖‖w_p‖·λ_max/(1 − λ_max) for any term, with w = diag(y_B)^½·A_Bᵀ·u. Both held on all 444 and 296 tile removals [C].

| Edit on the test board [C] | r | First-order price | Crack-law screen |
|---|---|---|---|
| 2 × 2 mm tile removals, DC | 0.51–0.83 | self terms 1.5–5.7× low; Kelvin-tap coupling wrong sign twice in 148 | — |
| cut grown to a 0.5 mm neck, DC | 0.990 | +2.2% against +197% exact | — |
| the same cut through, DC | 1.000 | finite; exact infinite (K1: disconnects A, B, S) | — |
| the same cut, 300 MHz | 0.993 | — (exact +27%: the island floats on displacement current) | — |
| 3 mm slit, DC to 2.8 GHz | 0.84 | 0.16–0.18 of exact | 1.00–1.14 of exact |
| new 6 mm edge notch, DC | — | 0.05 of exact | 1.04–1.18 of exact |
| decap removed, 300 MHz; at the 900 MHz anti-resonance | 0.28; 1.36 | 0.73 of exact; 0.43 at 143°, wrong sign | — |
| decap added, 1 GHz | 1.45 | 0.55 at −137°, wrong sign | — |

### 5. Objective classes

| Class | Examples | Structure | Optimizer | Ledger and explanation |
|---|---|---|---|---|
| A self, one dominant energy in the band | R, inductive-limit L, thermal R, 1/C, PDN \|Z\| off resonance | convex in relaxed copper, monotone, certified floors, free gradients | convex first; floors give τ, warm starts, stop rules | Tellegen attribution (χ = 0.89–1.00 here); avoidable share |
| A′ self, raised by copper | C of a dv/dt node | concave, monotone | shrink to needed copper | attribution |
| B interaction | M, C_m, transfer Z, a sense loop's reading, one part's ΔT, CM share | bilinear, sign-indefinite (χ = 0.34–0.48 here, 0.08 in CD) | one lead field per budget prices every aggressor site; after A; Braess screen on additions | exact counterfactuals when χ < 0.5 |
| C non-variational | EMI mask, PDN \|Z\| near anti-resonance, eye, thresholds | stationary, not minimal | binding frequencies; modal terms where r ≥ 1 | per binding frequency and mode |
| D damage | J_max, E_max, I²t, fatigue, life | local high-p norms; corners r^(π/α−1) | smoothed p-norms, regime-gated (t < w²/α; HV) | hotspots with locations |
| L legal and fab | creepage, clearance, width, space, keep-outs | hard sets | projection inside the loop (K7), never a penalty | pass or fail with its multiplier |

The class belongs to a (budget, band) pair: at 300 MHz no added decap raised |Z_AA| (0/150 sites), at 1 GHz all did [C]. K6 assigns it: class A needs one dominant energy in the band. Any class may carry a chance constraint P(pass) ≥ 1 − α ([IN13](../../ideas/physics-first/lens-in.md)).

### 6. The joint place-and-route optimizer on the core

The state stays (P, T, C) of [joint-place-route](joint-place-route.md).
- **Outer loop (minutes).** Decide by spatial scale ([LS24](../../ideas/physics-first/lens-ls.md)): world bonds, stackup and connector edges, then cells, then copper; within a scale, least slack first (τ from K5). K8 picks ask, measure or robustify for the world; K6 keeps resonances out of protected bands.
- **Middle loop (seconds).** Continuous poses. Class-A gradients are free (energy density at moving boundaries); class B costs one lead field per budget, then each aggressor site is an inner product; C uses binding frequencies; D is smoothed; L is projected. A step stops at the next K1 certificate or where its copper change reaches r ≈ 0.5.
- **Inner loop (milliseconds).** Each discrete edit gets a three-stage quote: E2/E3 screens (µs); an exact quote with spectrum and events (0.2 ms in a cached window, 5 ms–1.4 s otherwise); commit, bumping the epoch at events and diffing passports for role-change alarms (CD15). Accept or reject on stage-2 numbers; their r values recalibrate stage-1 trust.
- **Convex first.** Each power net starts from its class-A relaxation (floor, warm start), then continues into B and C terms; morphology stays inside the loop.
- **Regime dispatcher.** The regime cell picks the representation: a resistive sheet where ℓ_m exceeds the structure; complex-image PEEC across the transition band on intact planes, meshed thin-sheet PEEC on slotted or finite ones (gap 2); the telegrapher sheet with posts below f_p, modes above it; lines where θ ≳ 0.1 (delay-only at Z0 = Z, LS6); circuit co-simulation of a reduced macromodel where inserting the parasitic has r ≥ 1; full-wave slices for radiation.

### 7. The LLM and the human

The LLM reads priced menus (exact changes per binding budget, exactness, cost, events), binding budgets with τ and P(pass), job verbs and conflicts, and VOI-ranked unknowns. It writes mechanism hypotheses with registered predictions, allocations, menu choices, symmetry declarations and world facts; never geometry, regimes, spend or classes. Humans ask why copper is here, what breaks if they cut, where a via or decap helps, and why to trust a number ([API § 5](physics-core-v2-api.md)).

### 8. Compute budget

On one core, factor and solve times both grow about as n^1.2 between 2.4k and 153k cells [C].

| Item | Cost |
|---|---|
| Sheet factor / solve | 6 ms / 0.2 ms at 2.4k cells; 0.8–1.2 s / 20–41 ms at 153k [C] |
| Exact rank-32 quote | 5 ms–1.4 s direct; 0.19–0.23 ms inside a hot window whose 1,600-node Green block costs 5–6 s per epoch at 38k cells (agreement 4×10⁻¹⁵) [C] |
| Thevenin quote | 0.2–53 ms [C] |
| Leverage sketch, 24–48 solves | 0.01–1.4 s; median error 12% [C] |
| Full model, 4-layer 60 × 40 mm at 0.1 mm (about 1M cells), 5 bands, 20 sources | 5–15 CPU-min: 20 factorizations of 10–25 s, 100 solves of 0.2–0.4 s, PEEC windows [I] |
| Exact passports | lazy; caching a hot window at 1M cells takes 5–10 core-min [I] |
| Inner loop | about 4,000 exact quotes per core-second in hot windows [I] |
| GPU | batched right-hand sides; F1 and surrogates at 10⁶–10⁸ per s; full-wave finalists [I; [solver-ladder](solver-ladder.md)] |

### 9. Build order and acceptance tests

| Step | Build | Accept when |
|---|---|---|
| 1 | Data model, K1, K2 (DC, thermal), K4 | identities agree with re-factorization to ≤ 10⁻¹⁰ on 1,000 random edits (the skeleton: ≤ 4×10⁻¹¹); DC bounds never fail; λ = 1 exactly at K1 disconnects |
| 2 | Critics on the core; mutation benchmark | 31/31 planted faults found, 0/7 benign twins flagged ([pc_refplane](physics-critics.md)); each mutant changes a job verb at its site (CD16) |
| 3 | K2 complex, K6 | f_p within 2% of ls_post_lattice; Q = h/δ; r flags every wrong-sign first-order quote in 1,000 PDN edits |
| 4 | K3 | within 3.5% of ls_thin_sheet, 1.3% of PEECN/FastHenry at w/h 0.3–5; cd passports to 10⁻⁹ |
| 5 | K5, K7, K8 | vp_floors and in_emi_voi reproduced; legalization keeps connectivity |
| 6 | One real board | an open 4-layer bench board: passports for every piece (DC, thermal) and two HF windows within budget; an engineer reviews 20 why_here answers |
| 7 | Optimizer | beats the equal-CPU sequential portfolio on the JPR boards (JPR46) |

## Recommendations for our system

1. Build K1, K2, K4 and the data model first, under `tools/`, with the skeleton's checks as unit tests.
2. Return r with every exact quote; no first-order price decides where r ≥ 0.5.
3. Classify every budget per band (K6) before optimizing; PDN impedance near anti-resonances is class C.
4. Keep E1 and E2 apart; compliance verdicts on class-A quantities quote the bracket.
5. Put world conductors in the graph from day one, as E5 beliefs K8 asks about; cache Green blocks for hot windows.

## Conflicts and open questions

- **One synthetic board**, lumped posts, no via inductance. The identity is exact; the thresholds (r = 0.5, χ = 0.5) need real boards.
- **Dense PEEC.** K4 needs PEEC's mesh form (as in CD); compressed L must stay E1-accurate.
- **Pieces are a convention:** tiles are stable but arbitrary; functional segments ([CD14](../../ideas/physics-first/lens-cd.md)) are views.
- **Periodic adjoints** need a harmonic-balance operator; no open SPICE has one ([lens-sy](lens-sy.md)).
- **The world model** needs facts no board file holds; until answered, it stays E5.

## Sources

- [C]: [pc2_core_skeleton.py](../../../tools/research/physics/pc2_core_skeleton.py), reusing [cd_conductor_passport.py](../../../tools/research/physics/cd_conductor_passport.py), [ct_cut_topology.py](../../../tools/research/physics/ct_cut_topology.py) and [vp_floors.py](../../../tools/research/physics/vp_floors.py); other [C] values from the scripts named in each row.
- Prager and Synge, Q. Appl. Math. 5 (1947); Tellegen, Philips Res. Rep. 7 (1952) [S]; Spielman and Srivastava, [arXiv:0803.0929](https://arxiv.org/abs/0803.0929) [S]; Kotiuga and Lahtinen, [arXiv:1809.01002](https://arxiv.org/abs/1809.01002) [P].

See also: [physics-core-v2-api](physics-core-v2-api.md) · [README](README.md) · [cross-workstream-synthesis](cross-workstream-synthesis.md) · [solver-ladder](solver-ladder.md) · [joint-place-route](joint-place-route.md) · [physics-critics](physics-critics.md) · [vocabulary](vocabulary.md) · [physics-ir](physics-ir.md)
