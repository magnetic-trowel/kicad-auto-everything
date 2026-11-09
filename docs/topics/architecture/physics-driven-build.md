<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Physics-driven design: what is built and how well it holds

Scope: built pieces of [physics-driven-design](physics-driven-design.md) on branch `physics-functional-eval` (`kae.em` tier-2 field solver; `kae.excite` circuit and prices W; `kae.em.t1`/`kae.em.pnr` router prices and router), their checks, first routing A/Bs. Not here: problem, tiers, gates G1–G5 (still the acceptance criteria) -> [physics-driven-design](physics-driven-design.md); spectral prices -> [physics-frequency-coverage](physics-frequency-coverage.md); later results -> [field-solver-routing-and-intent](../../research/physics/field-solver-routing-and-intent.md).
Keys: kae.em, kae.excite, kae.em.t1, kae.em.pnr, kae.em.cprice, em.solve, FastHenry, Hoer–Love, COCG, flux term, crossing term, transfer term, capacitive prices E3, boost board, acarpm-chesslab-powerboard, MT3608, Σφ(u), lump_into, `--verify`, `--no-capacitive`

All numbers model against model [C]. All A/Bs re-route priced nets inside the human layout (other nets' human copper kept): re-routing, not routing a board ([validity caveat](../../research/physics/field-solver-routing-and-intent.md)).

## 1. What each piece does

| Piece | Physics | Method | Cost (one core, loaded host) |
|---|---|---|---|
| `em.kernels` | partial inductance of rectangular bars | exact Hoer–Love form within 6 cells (= 12-point Gauss quadrature to 1e-9); filaments beyond (0.3% at the seam) | µs per table entry |
| `em.mesh`, `em.kicad` | every net's copper in a window (tracks, arcs, pads, vias, refilled zones) on the stackup | square raster per layer; bars split through thickness into `nsub` filaments (graded toward faces from nsub 3; the default 2 are equal halves: [field-solver-accuracy](../../research/physics/field-solver-accuracy.md)); tracks < 3 cells -> 4-connected chains with true width and length; pads, via landings equipotential | seconds |
| `em.solve` | magneto-quasi-static R + jωL network | FFT products of block-Toeplitz L_p; projected COCG on the KCL constraint, preconditioned by 2×2-cell stacks; batched right-hand sides | boost window 0.25 mm: ~25 s per pattern |
| `em.fields`, `em.t1` | what new copper would couple to | L_p operator read without the mask (flux), reference layer's flux subtracted, gap-crossing potential | one extra FFT pass per pattern |
| `excite.models`, `.sources`, `.observe` | the board's small-signal circuit and its harms | MNA over nets + part internals; aggressors: switch as current source, IC cores, clocks; observers through one adjoint each | ms |
| `excite.evaluate` | every harm of a laid-out board | each aggressor's pad currents injected into `em.solve`; observers read as J_kᵀv | one solve per aggressor |
| `em.pnr` | physics-priced routing | GridRouter legality + `em.route` (A* with signed directional costs and the crossing term) | minutes per net (refresh-bound) |

## 2. Checks of the field solver

Closed forms ([test_em](../../../kae/tests/test_em.py)):
- Strip DC resistance: exact.
- Isolated strip HF L: 1.7–2.5% below uniform-current value (edge crowding, right sign).
- Microstrip vs Hammerstad–Jensen, from above: +6.2% at 4 cells across, +4.2% at 8 (~2 points of it internal inductance HJ omits).
- Raster restricts current distributions -> its L is an upper bound.

Refinement, boost hot loop, all nets meshed:

| Pitch | 0.25 mm | 0.125 mm | 0.0625 mm | extrapolated |
|---|---|---|---|---|
| Loop L | 8.76 nH | 8.20 nH | 7.92 nH | 7.65 nH |

First-order convergence (differences halve); 0.25 mm reads 15% high; the evaluators state this bias and the priced nets under 3 cells (`mesh` in their output; [field-solver-accuracy](../../research/physics/field-solver-accuracy.md)). Only the loop's 3 nets meshed: 8.85 / 8.32 nH (other copper screens ~1%).

FastHenry (3.0wr, built from source; wrapper [ref_fasthenry](../../../tools/research/physics/ref_fasthenry.py); harness [em_vs_fasthenry](../../../tools/research/physics/em_vs_fasthenry.py)):

| Case | em at p and p/2 | Extrapolated | FastHenry | Error |
|---|---|---|---|---|
| microstrip 20 mm | 5.313 / 5.233 nH | 5.153 ± 0.080 | 5.097 | +1.1% |
| microstrip 30 mm | 7.980 / 7.850 | 7.721 ± 0.130 | 7.639 | +1.1% |
| 0.3 mm trace, solid plane | 6.947 / 6.823 | 6.699 ± 0.124 | 6.660 | +0.6% |

Queued: slot crossing, coupled pair, via-and-hole two-port, plane pair. FastHenry's automatic filaments ran out of memory on slotted planes (0.85M); its planes are now banded: 0.1 mm under traces, 0.4 mm elsewhere, 3 filaments through thickness.

## 3. Checks of the router prices

[em_t1_check](../../../tools/research/physics/em_t1_check.py): aggressor over a plane, victim at offset d; prediction from the aggressor's solve alone vs two-port solve; M in pH.

| Plane | d = 0.6 | 1 | 2 | 4 | 8 mm |
|---|---|---|---|---|---|
| solid: exact | 1217 | 457 | 114 | 27.6 | 6.5 |
| solid: t1 / exact | 1.04 | 1.05 | 1.06 | 1.06 | 1.06 |
| slot under both: exact | 3905 | 3047 | 2483 | 2028 | 1370 |
| flux only / exact | 0.29 | 0.13 | 0.03 | 0.00 | 0.00 |
| flux + crossing / exact | 0.94 | 0.94 | 0.95 | 0.97 | 0.98 |
| slot under the victim only: t1 / exact | 1.04 | 1.05 | 1.02 | 1.01 | 1.02 |

Traces crossing one slot couple through the shared detour around its ends, nearly independent of d (a plane-unaware router misleads). **Flux term**: the aggressor's own detour (in its solve). **Crossing term**: aggressor voltage across the gap where the victim crosses, from the solve's node potentials, telescoped to be additive per move.

**Multilayer**: striplines between ground planes tied only by edge vias, ends returning on the lower plane:

| Planes | d = 0.6 | 2 | 8 mm |
|---|---|---|---|
| solid: exact (pH) | 372 | 67 | 19 |
| one-plane model / exact | 0.72 | 0.04 | 0.04 |
| two-sided + transfer term / exact | 1.01 | 1.04 | 1.04 |
| slot in the upper plane only | 1.01 | 1.04 | 1.06 |
| slot in the lower plane only | 0.98 | 0.98 | 0.99 |

One-plane model misses that the upper plane's return share cannot close under the track (it runs to the nearest stitching via). **Transfer term**: psi = Σ a_k φ_k over the planes the return uses (a_k by inverse distance, as a stripline's charge divides); a via pays Δpsi, an end pays psi − potential of the plane its terminal's return enters; both from the aggressor's node potentials, telescoping along a path.

## 3b. Capacitive prices (stage E3)

[`kae.em.cprice`](../../../kae/src/kae/em/cprice.py): electric-field analogue of §3. Pair = victim observer (feedback, analog, crystal, reset, ...) × aggressor net (switch node, clock).

- **Harm** (voltage-forced): swing V in t_v drives C_m V/t_v into R (circuit's) ∥ C_node (circuit's at the edge band + own copper): v = C_m (V/t_v) R (1 − e^(−t_v/(R C_node))), linear in C_m at every ledger corner. Boost FB node (28.6 kΩ, 5.5–5.9 pF, 0.2–8 ns edges) acts as divider C_m V / C_node: u = 2.6 at the human 17.9 fF (bound 6 mV). The evaluator's circuit reads those 18 fF as u = 1.0: its cell is a current source with the rectifier conducting, so the switch node moves by the loop's ring, not the commutation swing.
- **Price**: φ_a = static potential, aggressor 1 V, other copper 0 V. Victim piece adds ΔC_m = C′(x) φ_a(x) dl (C′ = its capacitance per length to everything); reciprocally an aggressor piece adds C′ φ_victim dl. A* self term gains C′ Σ W φ_other per mm (W = robust objective's derivative per farad). C′ = microstrip over nearest copper above and below + coplanar share fitted to raster solves, scaled to the raster's own strip C.
- **Pours**: φ = 0 on copper, so a hop over another net's pour priced zero; the first smoke route exploited it (switch node through the plane under the divider, 58 fF). Such a hop now takes over the charge those cells hold in the other net's drive (exact on the raster: they stay 0 V) + half the charge of the clearance band the refill opens.
- **Refresh**: re-solves every capacitive net; after a hop its copper is painted in and its field re-solved (CG from its last charges); predicted vs solved ΔC_m logged.

[em_cap_price_check](../../../tools/research/physics/em_cap_price_check.py): predicted ΔC_m vs fresh static solve; 1 mm aggressor strip over a plane, 10 mm victim one pitch (0.25 mm) wide at edge gap d.

| Case | d = 0.25 | 0.5 | 1 | 2 | 4 mm |
|---|---|---|---|---|---|
| h = 1.51 mm: solved (fF) | 232 | 164 | 95.7 | 39.5 | 9.3 |
| h = 1.51 mm: predicted / solved | 0.91 | 0.94 | 0.95 | 0.95 | 0.95 |
| h = 0.2 mm: predicted / solved | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 |

Remainder at 1.51 mm = free ends' fringe (end-on track 0.83; routed hops end on pads). Aggressor cut through the plane under/beside the victim: 1.07–1.14. Aggressor copper beside a victim strip: 1.04–1.12 at 1.51 mm, 0.99 at 0.2 mm (screening by the net's earlier copper, omitted at first order).

Boost FB tracks removed and re-added hop by hop:

| Hop | Solved ΔC_m (fF) | Predicted / solved |
|---|---|---|
| IC1.3 west, 1.8 mm | +0.91 | 0.82 |
| diagonal to R4, 2.6 mm | +0.79 | 1.23 |
| R5 to R4, 2.2 mm | +0.54 | 1.04 |
| all three | +2.24 | 1.02 |
| stub 0.25 mm from the switch node, 3.3 mm | +38.8 | 0.91 |
| switch node through the plane under the divider (first smoke route's), 18.5 mm | +25.8 | 1.07 |

Pins dominate C_m (15.6 fF of 17.9; FB two pins from SW on the SOT-23). The stub raises u from 2.4 to 8.0. Re-meshing from scratch reproduces hop-by-hop C_m exactly. KiCad-refilled zones: switch-node route +35.3 fF vs +28.0 predicted (refill also drops slivers and islands of the cut plane).

**Smoke route**: boost, `kae.em.pnr` without `--verify`, 7 priced nets, vs `--no-capacitive`; measured by fresh static solve, KiCad-refilled zones:

| | C_m SW–FB (fF) | u feedback, typical (here / `wideband`) | `wideband` total, robust | `evaluate` total, robust | Route time |
|---|---|---|---|---|---|
| without capacitive prices | 57.5 | 7.85 / 6.0 | 5207 | 852 | 263 s |
| with capacitive prices | 6.3 | 0.89 / 1.1 | 3338 | 933 | 284 s |
| human layout | 17.9 | 2.6 / 1.6 | 10844 | – | – |

- Without the term the switch node runs through the plane under the divider; with it, a straighter path 3 mm away. Per hop predicted / solved 1.26, 0.75, 1.05, 1.13; refreshed mesh 4.4 fF vs 3.1 fF hop by hop (other nets' copper, refill).
- `excite.wideband` (each coupling a circuit part) scores the feedback victim 5× lower and every cable CM lower; `excite.evaluate` (no capacitance) single-band total +9.5%.
- Fields: 3 CG solves per refresh + 1 per capacitive hop, ~2 s each at 8 threads = 8% of the route.

## 4. The circuit side

acarpm-chesslab-powerboard (MT3608 boost, TP4056 charger, LDO; 2 layers):
- Aggressors: boost cell (switch as current source, D3 conducting), charger core. Hot loop: SW → D3 → C5 → GND → IC1; C4, C6 share 5% via the VIN pin.
- Pattern frequency 10 MHz: clean ±1 loop (above capacitor self-resonance, below parasitic resonance), as first-order pricing requires; at 50 MHz resonant gain 1.07–1.2 A/A (switch-node C with loop L).
- Circuit-pattern loop 8.77 nH vs hand-built port solve 8.76 nH, same pitch.
- Weakest input = observer bounds (priors): supply 5%, feedback 1% of Vref, analog 1 mV, CISPR 32 class B via Ott's cable model at 150 Ω. 1 mV on the charger's PROG pin is too strict: shifts trade-offs between structures, not ranking within one ([design §3](physics-driven-design.md#3-why-w-and-z-do-different-damage)).

## 5. First routing A/B

§4 board; six priced nets (+5V, VBAT, VBUS, switch node, FB, PROG) re-routed in the human layout; scored by `kae.excite.evaluate` at 0.25 mm, never the router's prices.

| | Human | Physics, refresh every 4 nets |
|---|---|---|
| total Σφ(u) | 1006 | 506 |
| IC1 VIN–GND bounce from the cell | u 7.8 (2.37 nH) | 2.0 (0.60 nH) |
| PROG pickup from the cell | 11.4 | 3.8 |
| VBUS loop (charger core) | 13.8 nH | 7.05 nH |
| cell overshoot (copper loop) | 8.77 nH | 10.19 nH |
| cable common mode J2–J3 from the cell | u 5.1 | 8.6 |
| DRC errors (refilled) | 5 shorts, 1 starved thermal, 1 unconnected | 2 shorts, 1 starved thermal, 1 unconnected |

Shorts are between untouched nets (the human board's own). Plain router (same nets, order, legality, no physics): Σφ(u) 227 -> physics A/B **negative**, caused by the 19 mm switch-node detour (§5a). Fixed; re-running on five boards, plus physics with per-net refresh.

## 5a. Co-simulation and the fixes it forced

- Two-pad parts are copper-model branches (`kae.excite.circuit.lump_into`); only active parts' pads injected, so geometry decides which capacitor closes a loop or carries a plane transition. Harm = solve − same parts with ideal copper (without it a crystal pin "saw" its load C as −6.9 µH of coupling).
- Through vias land on every layer between their ends (before: end layers only; every multilayer board cut into islands).
- Return reference = return-net copper only (grounds, decoupled rails); differencing other nets' islands (unrelated potentials) sent the first A/B's switch-node hop on a 19 mm detour (12.4 mm plain) chasing bogus crossing gains.
- Fractional cell coverage: a 0.3 mm trace at 0.1 mm pitch had been meshed 2 cells wide (−33%), putting one coupled-pair case 22% off FastHenry.

## 6. Known limits and next steps

- **Speed**: refresh of 11 patterns ~6–7 min at 0.25 mm, loaded host; iterations 60–240, growing with refinement; local preconditioner. Next: two-level coarse correction; mesh only the priced nets' windows.
- **Self cost**: closed form over local reference height, with coplanar return to a same-layer ground pour in parallel; a hop's own gap detour only local.
- **Widths** fixed per hop (class width; 0.8 mm for commutation currents); width search (wider lowers L′) not built.
- **Capacitive prices** (§3b): first order in the new piece; C′ fitted to the raster; thin tracks priced at one pitch; the evaluator's circuit does not drive the switch node's voltage edge.
- Not modelled yet: DC IR drop (resistive patterns); placement on W.
