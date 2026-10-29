<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Physics-driven design: what is built and how well it holds

**TL;DR**
- **Built.** Three pieces exist, each with a CLI. All are on branch `physics-functional-eval`.
  - [`kae.em`](../../../kae/src/kae/em/): a field solver for the whole board's copper (tier 2).
  - [`kae.excite`](../../../kae/src/kae/excite/): the board's own circuit, with its aggressors, observers and prices (the W of [physics-driven-design](physics-driven-design.md) §2).
  - [`kae.em.t1`](../../../kae/src/kae/em/t1.py) and [`kae.em.pnr`](../../../kae/src/kae/em/pnr.py): router prices taken from one solve per pattern, and a router that uses them.
- **Field solver against FastHenry** on identical geometry: within 1.1% after a two-pitch extrapolation, on three cases so far. The rest of the suite is queued. Mesh refinement converges at first order.
- **Router prices against exact two-port solves** (trace over plane, plus a victim at 0.6–8 mm):
  - solid plane: 1.04–1.06×;
  - slot under both traces: the flux term alone reads 0.29× down to 0×, because it misses the shared detour; with the gap-crossing term, 0.94–0.98×.
- **The first routing A/B was negative** (boost board, human placement, the 6 priced nets re-routed). Total Σφ(u): physics 506, plain router (no physics) 227, human 1006.
  - The physics router sent the switch node on a 19 mm detour (12.4 mm plain), chasing bogus crossing gains from other nets' copper islands.
  - That is fixed, and the A/B is re-running on five boards (§5).
- **Multilayer:** the two-sided price model with its transfer term holds at 0.98–1.06× against two-port solves of striplines, with solid planes and with a slot in either plane (§3).
- **Every number here is model against model.** Gates G1–G5 of the design doc stay the acceptance criteria.

## 1. What each piece does

| Piece | Physics | Method | Cost (one core, loaded host) |
|---|---|---|---|
| `em.kernels` | partial inductance of rectangular bars | exact Hoer–Love form within 6 cells (matches 12-point Gauss quadrature to 1e-9); filaments beyond (0.3% at the seam) | µs per table entry |
| `em.mesh`, `em.kicad` | every net's copper in a window: tracks, arcs, pads, vias, refilled zones, on the stackup | square raster per layer; bars split through the thickness (graded toward the faces); tracks under 3 cells become 4-connected chains with their true width and length; pads and via landings are equipotential | seconds |
| `em.solve` | magneto-quasi-static R + jωL network | FFT products of the block-Toeplitz L_p; projected COCG on the KCL constraint, preconditioned by 2×2-cell stacks; batched right-hand sides | boost window 0.25 mm: ~25 s per pattern |
| `em.fields`, `em.t1` | what new copper would couple to | the L_p operator read without the mask (flux), the reference layer's flux subtracted, and the gap-crossing potential | one extra FFT pass per pattern |
| `excite.models`, `.sources`, `.observe` | the board's small-signal circuit and its harms | MNA over nets plus part internals; aggressors: switch as current source, IC cores, clocks; observers through one adjoint each | ms |
| `excite.evaluate` | every harm of a laid-out board | each aggressor's pad currents injected into `em.solve`; observers read as J_kᵀv | one solve per aggressor |
| `em.pnr` | physics-priced routing | GridRouter legality plus `em.route`, an A* with signed directional costs and the crossing term | minutes per net (refresh-bound) |

## 2. Checks of the field solver

**Closed forms** ([test_em](../../../kae/tests/test_em.py)):
- DC resistance of a strip is exact.
- High-frequency L of an isolated strip lies 1.7–2.5% below the uniform-current value. That is edge crowding, and its direction is right.
- A microstrip approaches Hammerstad–Jensen from above:

  | Cells across the strip | Excess over HJ |
  |---|---|
  | 4 | +6.2% |
  | 8 | +4.2% |

  Of the excess at 8 cells, about 2 points are internal inductance the closed form leaves out.
- A raster restricts the space of current distributions, so its inductance is an upper bound.

**Refinement on a real loop** (the boost hot loop, all nets meshed):

| Pitch | Loop L |
|---|---|
| 0.25 mm | 8.76 nH |
| 0.125 mm | 8.20 nH |
| 0.0625 mm | 7.92 nH |

- The differences halve with the pitch (first order). Extrapolating gives 7.65 nH, and the 0.25 mm value reads 15% high.
- Meshing only the loop's three nets gives 8.85 / 8.32 nH: other copper screens the loop by about 1%.

**FastHenry** (3.0wr, built from source; wrapper [ref_fasthenry](../../../tools/research/physics/ref_fasthenry.py); harness [em_vs_fasthenry](../../../tools/research/physics/em_vs_fasthenry.py)):

| Case | em at p and p/2 | Extrapolated | FastHenry | Error |
|---|---|---|---|---|
| microstrip 20 mm | 5.313 / 5.233 nH | 5.153 ± 0.080 | 5.097 | +1.1% |
| microstrip 30 mm | 7.980 / 7.850 | 7.721 ± 0.130 | 7.639 | +1.1% |
| 0.3 mm trace, solid plane | 6.947 / 6.823 | 6.699 ± 0.124 | 6.660 | +0.6% |

Still queued: the slot crossing, the coupled pair, the via-and-hole two-port and the plane pair.

FastHenry's automatic filament count ran out of memory on slotted planes (0.85M filaments). Its planes are now banded: 0.1 mm under the traces, 0.4 mm elsewhere, 3 filaments through the thickness.

## 3. Checks of the router prices

[em_t1_check](../../../tools/research/physics/em_t1_check.py): an aggressor trace over a plane, and a victim trace at offset d. The prediction uses only the aggressor's own solve; the exact value is a two-port solve with both traces present. Values are mutual inductance in pH.

| Plane | d = 0.6 | 1 | 2 | 4 | 8 mm |
|---|---|---|---|---|---|
| solid: exact | 1217 | 457 | 114 | 27.6 | 6.5 |
| solid: t1 / exact | 1.04 | 1.05 | 1.06 | 1.06 | 1.06 |
| slot under both: exact | 3905 | 3047 | 2483 | 2028 | 1370 |
| flux only / exact | 0.29 | 0.13 | 0.03 | 0.00 | 0.00 |
| flux + crossing / exact | 0.94 | 0.94 | 0.95 | 0.97 | 0.98 |
| slot under the victim only: t1 / exact | 1.04 | 1.05 | 1.02 | 1.01 | 1.02 |

The slotted rows show why a plane-unaware router misleads. Two traces crossing the same slot couple through the shared detour around its ends, and that coupling barely falls with distance. Two terms capture it:
- the **flux term**, which uses the aggressor's own detour (included in its solve);
- the **crossing term**: the voltage the aggressor develops across the gap where the victim would cross. It is read from node potentials the solve already has, and telescoped so that it is additive per move.

**Multilayer** (striplines between ground planes tied only by edge vias; the traces' ends return
on the lower plane), from the aggressor's solve alone, against two-port solves:

| planes | d = 0.6 | 2 | 8 mm |
|---|---|---|---|
| solid: exact (pH) | 372 | 67 | 19 |
| one-plane model / exact | 0.72 | 0.04 | 0.04 |
| two-sided + transfer term / exact | 1.01 | 1.04 | 1.04 |
| slot in the upper plane only | 1.01 | 1.04 | 1.06 |
| slot in the lower plane only | 0.98 | 0.98 | 0.99 |

The one-plane model misses that the upper plane's share of the return cannot close under the track:
it runs to the nearest stitching via. The **transfer term** prices it: with psi = Σ a_k φ_k over
the planes a track's return uses (shares a_k by inverse distance, as a stripline's charge divides),
a via pays its change in psi and an end pays psi minus the potential of the plane its terminal's
return enters. Both read the aggressor's own node potentials and telescope along a path.

## 3b. Capacitive prices (stage E3)

[`kae.em.cprice`](../../../kae/src/kae/em/cprice.py) prices the electric field the way §3 prices
the magnetic one. Each pair is a victim observer (feedback, analog, crystal, reset...) and an aggressor net
(a switch node, a clock).

- **Harm.** Capacitive coupling is voltage-forced. The swing V in t_v drives C_m V/t_v into the
  victim node. To the edge that node is R (the circuit's, at low frequency) in parallel with C_node:
  the circuit's capacitance at the edge band plus the net's own copper capacitance. The peak is
  v = C_m (V/t_v) R (1 − e^(−t_v/(R C_node))), which is linear in C_m at every corner of the ledger.
  - On boost the feedback node is 28.6 kΩ, 5.0 pF circuit plus 0.5–0.7 pF copper, against edges of
    0.2–8 ns. That is the divider C_m V / C_node: u = 2.6 at the human layout's 17.9 fF (bound 6 mV).
  - The evaluator's linear circuit sees the same 18 fF as u = 1.0. There a cell is a current
    source with its rectifier conducting, so the switch node moves by the loop's ring and not by its
    commutation swing.
- **Price.** φ_a is the potential on every cell with the aggressor at 1 V and all other copper at
  0 V (the static solve). A victim piece at x adds ΔC_m = C′(x) φ_a(x) dl, where C′ is its capacitance per length to
  everything else. By reciprocity an aggressor piece adds C′ φ_victim dl.
  - The A* self term gains C′ Σ W φ_other per mm. W is the robust objective's derivative per farad.
  - C′ is microstrip (Hammerstad–Jensen) over the nearest copper above and below, plus a coplanar
    share fitted to raster solves. It is scaled to the raster's own strip capacitance at the layer's
    height.
- **Refresh.** Every field refresh re-solves every capacitive net. After each hop of an aggressor or
  victim net, its copper is painted into the static raster and that net's own field re-solved (CG from its
  last charges). So the next hop sees it, and every hop logs its predicted ΔC_m against the solved one.
  The other fields miss the new copper's screening until the next refresh.

[em_cap_price_check](../../../tools/research/physics/em_cap_price_check.py): ΔC_m predicted from the
fields before a hop, against a fresh static solve with it. The synthetic case is a 1 mm aggressor strip
over a plane and a 10 mm victim track one pitch (0.25 mm) wide at edge gap d.

| case | d = 0.25 | 0.5 | 1 | 2 | 4 mm |
|---|---|---|---|---|---|
| h = 1.51 mm: solved (fF) | 232 | 164 | 95.7 | 39.5 | 9.3 |
| h = 1.51 mm: predicted / solved | 0.91 | 0.94 | 0.95 | 0.95 | 0.95 |
| h = 0.2 mm: predicted / solved | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 |

- The 5% left at h = 1.51 mm is the free ends' fringe: an end-on track reads 0.83. A routed hop
  ends on pads.
- Aggressor copper beside a victim strip (reciprocity) reads 1.04–1.12 at h = 1.51 mm and 0.99 at 0.2 mm. The excess is the screening of the
  net's own earlier copper, which first order leaves out.

On the boost board the feedback net's tracks were removed and then added back one hop at a time:

| hop | solved ΔC_m (fF) | predicted / solved |
|---|---|---|
| IC1.3 west, 1.8 mm | +0.91 | 0.82 |
| diagonal to R4, 2.6 mm | +0.79 | 1.23 |
| R5 to R4, 2.2 mm | +0.54 | 1.04 |
| all three | +2.24 | 1.02 |
| a stub 0.25 mm from the switch node, 3.3 mm | +38.8 | 0.91 |

- The hops change C_m little (15.6 → 17.9 fF) because the pins dominate it: FB sits two pins
  from SW on the SOT-23.
- The stub raises u from 2.4 to 8.0. This is what the price keeps the router from doing.
- A board re-meshed from scratch with all hops gives the same C_m as painting them in turn (17.856 fF both).

## 4. The circuit side

On acarpm-chesslab-powerboard (MT3608 boost, TP4056 charger, LDO; 2 layers):
- **Aggressors found:** the boost cell (the switch is a current source and D3 conducts) and the charger's core. The hot loop the circuit solve finds is SW → D3 → C5 → GND → IC1, with C4 and C6 sharing 5% through the VIN pin.
- **Pattern frequency.** Taken at 50 MHz, the pattern showed resonant gain (1.07–1.2 A per amp) from the switch node's capacitance with the loop's inductance. At 10 MHz it is the clean ±1 loop: above the capacitors' self-resonance and below the parasitic resonance, as first-order pricing requires.
- **Consistency.** The loop the circuit pattern sees (8.77 nH) matches a hand-built port solve (8.76 nH) at the same pitch.
- **Weakest input: the observers' bounds.** They are priors (supply 5%, feedback 1% of Vref, analog 1 mV, CISPR 32 class B through Ott's cable model at 150 Ω). An analog prior of 1 mV on a charger's PROG pin is too strict. That changes the trade-off between structures, but not the ranking within one structure (design doc §3).

## 5. First routing A/B

Board as above, human placement and human routing of every other net. The six priced nets (+5V, VBAT, VBUS, the switch node, FB, PROG) were ripped up and re-routed. Every board is scored by `kae.excite.evaluate` at 0.25 mm, never by the router's own prices.

| | Human | Physics, refresh every 4 nets |
|---|---|---|
| total Σφ(u) | 1006 | 506 |
| IC1 VIN–GND bounce from the cell | u 7.8 (2.37 nH) | 2.0 (0.60 nH) |
| PROG pickup from the cell | 11.4 | 3.8 |
| VBUS loop (charger core) | 13.8 nH | 7.05 nH |
| cell overshoot (copper loop) | 8.77 nH | 10.19 nH |
| cable common mode J2–J3 from the cell | u 5.1 | 8.6 |
| DRC errors (refilled) | 5 shorts, 1 starved thermal, 1 unconnected | 2 shorts, 1 starved thermal, 1 unconnected |

The shorts are between nets the router does not touch; they are the human board's own. Two A/B runs are pending:
- the plain router: the same nets, order and legality, with no physics;
- physics with a per-net refresh.

## 5a. Co-simulation and the fixes it forced

- Two-pad parts are now branches of the copper model (`kae.excite.circuit.lump_into`), and only
  active parts' pads are injected, so the geometry decides which capacitor closes a loop or carries a
  plane transition. A harm is the solve minus the same parts with ideal copper; without that
  subtraction a crystal pin "saw" its own load capacitance as −6.9 µH of coupling.
- Through vias listed only their end layers; they now land on every layer between. Every multilayer
  board was cut into islands before.
- The return reference is return-net copper (grounds and decoupled rails) only: other nets' copper
  islands have unrelated potentials, and differencing them sent the first boost A/B's switch-node
  hop on a 19 mm detour (12.4 mm plain).
- Cells carry fractional coverage: a 0.3 mm trace at 0.1 mm pitch had been meshed 2 cells wide
  (−33%), which put one coupled-pair case 22% off FastHenry.

## 6. Known limits and next steps

- **Speed.** A field refresh of 11 patterns takes about 6–7 minutes at 0.25 mm on the loaded host. Iterations grow with refinement (60–240), and the preconditioner is local.
  - Next: a two-level coarse correction; meshing only the windows the priced nets need.
- **Self cost.** The router's self term is a closed form over the local reference height. The coplanar return to a ground pour on the routing layer is now included, in parallel with it. A hop's own detour across a gap is still only local.
- **Widths** are fixed per hop: the class width, or 0.8 mm for commutation currents. Width choice is part of the physics (wider copper lowers L′) and is not yet searched.
- **Capacitive prices** (§3b) are first order in the new piece, the C′ closed form is fitted to the raster, and
  thin tracks are priced at one pitch, which is the raster's width for them. The evaluator's circuit does not drive
  the switch node's voltage edge.
- **Not modelled yet:**
  - DC IR drop (resistive patterns);
  - placement on W.
