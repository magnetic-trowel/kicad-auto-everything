# Cross-workstream synthesis: convergences, synergies and transfers

**TL;DR**
- **Eleven workstreams started from rules, language, solvers, power, fields, optimization, manufacturing, reasoning, critics, other fields and joint P&R. They kept arriving at the same nine mathematical objects**, listed in §1, implemented as the eight kernels of [physics-core-v2](physics-core-v2.md). Physics-first layout needs a handful of kernels, not hundreds of rules or dozens of tools.
- **Several ideas were invented two to five times from different directions.** Examples: reverse-return feeding (power and hydronic heating), inductor orientation by dipole algebra (power and NMR), "curves only where physics pays" (five workstreams), calibration coupons (five), electro-thermal coupling (five) and per-pad thermal-relief decisions (three). Independent rediscovery is the strongest evidence that an idea is fundamental.
- **The biggest synergy is two adjoints chained.** A circuit adjoint (SPICE `.noise`: which parasitic moves which output) times a field adjoint (which copper edit moves which parasitic) gives the gradient from the circuit specification to the copper geometry in two extra solves. No single workstream proposed the whole chain.
- **Several conflicts dissolve when two workstreams' results are combined.** "SW copper area: heat vs EMI" becomes "capacitance *to whom*". "Pours vs routing space" becomes "cut along streamlines, priced by the stream function". "Keep-out distance" becomes "which field couples, and where its null points".
- **Lessons transfer.** OP and JPR both found that post-hoc legalization destroys results, so hard constraints go inside the loop. Evaluators whose error does not shrink as candidates converge fail among near-equal candidates, which is where to escalate fidelity. Grid rank-1 updates, reservoir well models, robust topology-optimization filters and data assimilation each solve a named problem elsewhere.

The principles behind these objects are in [foundations](foundations.md). Ids refer to the [physics-first ideas](../../ideas/physics-first/README.md). [C] numbers are from the workstreams' scripts. This doc is synthesis [I] unless a number is tagged.

## Key facts

### 1. The nine mathematical objects underneath everything

| Object | Where it appeared, from which direction | One engine serves |
|---|---|---|
| **Screened Laplace operator on sheets** (φ, with length scale λ) | IR drop and pour L (OP1); thermal fin (TM1, TM2); decap reach (XD113); via transfer length (XD22); plane spreading L (PW37, PW38); topology optimization (OP2) | IR, heat, decap placement, via rows, pour synthesis, Kelvin taps |
| **Stream function ψ** (the dual of φ) | Coil design (XD1–XD4); slot damage Δψ² (XD2, SIM25); streamline power routing (PW16); pin-1 check (XD70); direction fields (XD98) | Cut pricing, routing through pours, shield-current checks |
| **Partial-element matrices** (R, Lp, P, τ = PEEC) | Three solvers written separately (`sl_`, `pw_`, `fe_`); the basis set's "four primitives" ([rule-basis-set](rule-basis-set.md)); LA21 accounting unit; XD30 compression | Loops, returns, couplings, decaps, slots, macromodels |
| **Adjoint / reciprocity** | Circuit `.noise` (DR3); copper sensitivity (OP38, OP40, PW39); susceptibility maps (XD35); transfer-inductance maps (FE3); topological derivative (OP41) | Susceptibility, shadow prices, explanation, "where to add copper" |
| **Lagrange multipliers / prices** | PathFinder history and pressure forces (JPR11, JPR12); budget shares √(k·s) (DR9); constraint price tags (JPR34); copper price (OP3, OP25, XD56); compute market (SIM40, SIM45); "nH in watts" (PW30); dB as currency (LA19) | Arbitration among physics, space and compute; the LLM's interface |
| **Eigenmodes** | Plane cavities (FE26–FE28); box modes (XD85); characteristic modes (XD34); energy participation (XD84); ring frequency (PW31); vibration modes (TM45) | Resonance avoidance, stitching, frequency planning |
| **Multipole expansion** | Loop with image as a quadrupole (LA26); buffer distance from multipole order (XD68); figure-8 loops (XD11); opposite-current via pairs (PW36); dipole algebra for magnetics (PW47, XD71) | Keep-out halos, cancellation primitives, orientation |
| **Homotopy and topology classes** | Joint state (JPR1–JPR4, JPR7); returns around slots (FE1); ψ level-set crossings (XD3) | Joint P&R, return continuity, cut legality |
| **Morphology and signed distance** | Fab filters (OP51, XD66, OP7, XD33); SDF clearance (XD94); acid traps (TM38); medial-axis necks (XD95); legalizer (OP50) | DRC inside the optimizer, legalization, neck finding |

The consequence for building: one physics core with these nine kernels. Every critic, optimizer term and explanation becomes a query over them.

### 2. Convergences: the same idea from different directions

| Idea | Found by (direction) | What the convergence tells us |
|---|---|---|
| Reverse-return feeding of paralleled parts | PW14 (circuit physics: sharing 9.8:1 → 1.8:1 [C]); XD47 (hydronic heating: 13.6 → 2.4 [C]) | Equal path length is a universal law of parallel flow; make it a generator |
| Orient magnetics from dipole coupling | PW47 (power, the Dodd–Deeds field); XD71 (NMR magic angle: null at 54.7° [C]) | Replace "rotate 90°" with dipole algebra; 90° is not the null for in-plane axes |
| Curves only where physics pays | RG44, OP35, PW18, TM47, FE39/FE45 (rules, optimization, pulsed power, HV/fab, SI) | The answer to "curves vs corners" is consistent: a regime-gated operator. Fabs make curves at no extra cost |
| Calibration coupons | SIM12, PC37, RG35, TM29, PW50 | Measurement is everyone's blocker: one coordinated coupon program ([research-gaps](research-gaps.md) gap 1) |
| Mine vendor eval boards for budgets | RG7/RG8 (back-solve a rule's implied budget), DR50 (EVMs as floors), SIM13 (vendor data with de-embedding) | EVMs are the cheapest F4 data and floor oracle at once |
| Electro-thermal coupling | TM16, PW49, OP11, LA28, RG50 (and XD20) | Share one graph; the coupled solve is cheap away from runaway |
| Per-pad thermal-relief decision | RG28 (L, R, R_th vs budgets), OP9 (spokes vs heat flow), TM42 (by assembly process) | One multi-objective per-pad choice; WS7 adds that reliefs barely move reflow balance |
| Loop area is the wrong proxy | LA26, SIM15, PW25, OP22 | Retire area tiers near planes (done in [hot-loops](../rules/power/hot-loops.md)) |
| Cells / locality as the unit | DR22 (HF current closure), LA9 (typed molecules), XD12 (power-module P/N cells), JPR20 (exact cell micro-solve), DR42 (locality index) | The cell is the unit of hierarchy, beauty and explanation (synergy S6) |
| Keep foreign current out of measurements | LA7, LA8, LA33, XD72, PW41, PW42, RG16, DR26, XD69 | A checkable invariant, not a rule family |
| Physics kernels replace HPWL and density | XD112, OP23, OP24, TM2, FE3, FE11 | A placer objective of FFT convolutions with real kernels |
| Rules as warm starts and move generators | RG41–RG43, JPR7, JPR10, OP19 | Human practice seeds the search; physics judges |
| Frequency planning | FE13, FE50, DR36, PW31, OP16, PC12 | Spectral coincidence (source × structure × victim) is one check (S8) |

### 3. Synergies: combinations worth more than their parts

**S1. End-to-end differentiable invisibility.** Chain three pieces:
1. The circuit adjoint, DR3 (`.noise`), gives ∂output/∂parasitic for every partial element in one solve.
2. The passive macromodels (SIM33, LA22, XD28) connect that partial element to the PEEC graph.
3. The field adjoint (OP38, OP40, PW39) gives ∂parasitic/∂geometry.

The product is ∂(layout invisibility index)/∂(every copper cell, via and pad pose), for two extra solves, within one topology and one linearization. Vias, cuts and new connections are topological events priced by exact rank-k updates, and switching or sampled circuits need a periodic adjoint ([lens-ct](lens-ct.md), [lens-cd](lens-cd.md), [lens-sy](lens-sy.md)). Check it against direct AC (DR3 matched to 6e-13 [C]) on one buck plus ADC board.

**S2. Pours and routes trade through ψ.** Copper-shape synthesis, the router and the critics each met the same conflict: signals need channels through power pours.
- XD2 and SIM25 price any cut as ΔR ≈ (π/4)·R_s·(Δψ/I)². A cut along a streamline is nearly free, while across one it costs ~90× more [C].
- PW10 found the last 28% of a pour's area buys only 9% of its R [C].

So the unified occupancy market (JPR8, OP32) should price pour cells for routing by Δψ², and PW16 should route power along streamlines. Signals then cross pours in the direction that costs nothing. None of the three workstreams had the whole loop.

**S3. All-pairs coupling from one solve per victim plus one per aggressor.**
- XD35 (reciprocity) gives each victim's susceptibility field in one solve.
- OP24 and XD112 give each aggressor's near field as a convolution kernel.
- FE3 gives connector-pair transfer-inductance maps in one solve per pair.
- DR3 tells which victims matter: the circuit adjoint weights each victim field by its output sensitivity.

The coupling of every aggressor–victim pair is then an inner product, a lookup inside the placer. This replaces O(N²) Neumann integrals and "keep away" rules with one objective that knows which couplings the circuit cares about.

**S4. "Capacitance to whom" dissolves the switch-node conflict.**
- Rule genealogy flagged the conflict "SW area: Cm vs Th vs R" (P07/P08).
- PW4 splits a fast node's capacitance into three parts: to its local return (harmless, inside the loop), to the outside world, and to victims.
- PW5 prices heat through a thin dielectric at G/C = k/ε: 1.4 mW/cm² of switching loss at 12 V, 0.3 W/cm² at 400 V [C].
- DR28 bonds the heatsink to DC−, so its ~22 pF goes to a quiet node [C].

Together: spread switch-node heat into the node's *own return plane* and bond external metal to quiet nodes. The EMI budget then counts only the capacitance that leaves the cell. At low voltage the conflict largely disappears; at 400 V the ½CV²f term binds. That replaces "never heatsink through SW copper" with a computed trade.

**S5. Cancellation aims nulls.** The cancellation primitives come from several places: LA35 the `cancel` operator, XD11 figure-8 loops, PW36 opposite-current via pairs, PW51 interdigitated fingers, XD76 gradiometric sense traces and XD15 the orthogonal gate loop. Each raises the aggressor's multipole order. XD68 shows that the order sets how fast coupling decays far away: a dipole falls as 1/r³, a quadrupole as 1/r⁴. Over a plane the near halo barely changes (radius −2%); what cancellation buys is an exact null plane and a quieter far field (−22 dB at 100 mm), capped near 20·log ε by imbalance ε ([lens-sy](lens-sy.md)) [C]. Use cancellation to aim nulls at victims.

**S6. The cell as one unit for four jobs.**
- **Hierarchy:** DR22's cells, closed by HF current, become JPR's macros. JPR20 solves inside a cell exactly, and JPR16 handles the multigrid across cells.
- **Beauty:** DR42's locality index.
- **Explanation:** a cell's ports are the half-ports of LA1.
- **Protection:** XD73's lightning-style zones, where every conductor crossing a zone boundary is filtered or bonded.

The ESD and immunity pieces scattered across five workstreams (DR47, RG22, FE44, XD52, XD73) assemble into this one zone and cell framework. That partly closes the immunity gap ([research-gaps](research-gaps.md) gap 6).

**S7. A unified via theory.** Each workstream saw a different side of the via:
- partial L ∝ ln(s/r), which is weak (FE, RG11);
- cavity launch ∝ (ks)², which is strong at high frequency (FE5);
- cluster perimeter, not count, sets spreading L (PW32, PW35);
- transfer length sets DC current sharing (XD22);
- Peaceman well index represents vias in coarse grids (PW13);
- CAF spacing under bias (TM24).

One via-placement objective with band-indexed terms covers return vias, decap vias, power via fields, thermal vias and stitching. Today they are five separate rules.

**S8. One frequency plan across power, cavities, clocks and radios.** The pieces come from different workstreams:
- PW31 steers the hot-loop ring frequency (90–290 MHz [C]) with L and the snubber (PW29).
- OP16 moves cavity modes with plane shape.
- FE27 and FE28 move them with stitching.
- FE13 and FE50 plan clock harmonics against resonances and radio channels.
- PC12 scores the overlaps.

Combined: choose L, C_snub, plane shape, stitching pitch and clock frequencies together, so that no strong line lands on a structural resonance or a protected band. No single workstream owned all the knobs.

**S9. Floors do three jobs.** DR18's floor oracles combine with TM52's fab-imposed floors (minimum width, space and dielectric cap how small a loop can be): floor = max(physics floor, fab floor). That one number sets priority (τ, DR17), prunes moves (JPR30 admissible bounds) and stops refinement (OP57). A budget below its fab floor is a requirement conflict for the human, not an optimizer failure.

**S10. A three-commodity market, with prices as the LLM's interface.** The goods are **space** (area, channels, layers: JPR8, OP3, OP6), **physics budgets** (nH, mV, K: DR9, I1) and **compute** (solver calls: SIM40, SIM45). The multipliers between them are the exchange rates: "1 mm² of area is worth x pH here" (OP25, PW30). Three workstreams independently said the LLM should read sensitivities and prices, not raw fields (SIM44, DR14, LA40). With LA27/XD51 low-rank previews, every operator on the LLM's menu comes priced in all three goods before anything moves.

**S11. Kelvin taps from equipotentials.** OP1 already computes φ for the aggressor currents. A sense tap pair sees no foreign drop when both taps sit on the same aggressor equipotential. So DR26 (current-free peninsula synthesis), LA8 (sense ports) and XD70 (no shield streamline across analog ground) reduce to reading φ and ψ maps from the same solve.

### 4. Transfers: learned in one place, needed in another

| Lesson | Learned in | Apply in |
|---|---|---|
| Post-hoc legalization destroys optimized results; keep hard constraints inside the loop | OP (an opening disconnected a load); JPR (the final legalizer turned 602 into 1,164) | LLM repair proposals (legalize inside the generator), critic-driven repairs, pour synthesis, any RL policy |
| Proxies rank coarse differences but not near-equal candidates when their error has a component that does not shrink (44% of pairs within 3% HPWL differ >10% routed) | JPR; Cadence 12k-placement data; [lens-in](lens-in.md) | SIM10 value-of-information escalation: near-ties are exactly where F2/F3 pays. JPR41 delayed acceptance should use MS2 and decision-calibrated surrogates (SIM7) as its first stage |
| Joint search refines; restarts find basins | JPR: joint refinement improves its start 10/10 and ties an equal-CPU restart portfolio ([joint-place-route-experiment](joint-place-route-experiment.md)) | OP (non-convex pours need multi-start, OP44 QD); DR40 continuation by τ. One protocol: diverse coarse starts → joint refinement → physics continuation |
| Robust erode/nominal/dilate optimization | Topology optimization (XD33, OP7) | Impedance tolerance (TM35), σ-margin maps (TM31), critics: evaluate every physics term at ±etch for free robustness |
| Rank-1 (Sherman–Morrison) updates of a factored network | Power-grid PTDF/LODF (XD51) | Incremental critics (PC20 via-field min-cut, OP39 neck finder), LA27 operator previews, JPR move screening, the U1 live HUD |
| Well index for sub-grid vias | Reservoir simulation (PW13) | Thermal vias in TM2/TM3 kernels, decap via fields (PW35), whole-board IR inside placement (SIM47) |
| Lattices beat random stitching up to 2.2× at equal count | FE27 [C] | XD99 blue noise should be judged against a lattice, not against random. FE28 eigenvalue gradients can polish either |
| Data assimilation fits model parameters to sparse observations | Weather (XD111) | The calibration ledger (FE56), conformal σ (SIM8) and residual surrogates (SIM34) from coupon measurements |
| Measured net passports replace name-based roles | DR1 | Critic precision: role-blind critics raised 11 irrelevant warnings on one board (PC). Passports remove them |
| Regime gating removes inactive physics | RG2, FE39, SIM4, LA11 | Compute: drop inactive terms from JPR's objective per structure, not just from reports |
| Planes typed `signal` invite routers to perforate them | PC44 | Cheapest bench experiment: retype planes, then measure the physics scorecard and vias (JPR's gains came from fewer vias) |
| Pinout sets the return at the cable boundary | Ball-map logic (XD24), pin swaps (JPR22), half-ports (LA1) | EMI: connector pinout is a lever in the CM chain ([fields-emi-budget](fields-emi-budget.md)) |
| Air density drives both breakdown and cooling | TM21 (Paschen), [research-gaps](research-gaps.md) gap 9 (convection ∝ ρ^0.5) | Make one environment regime parameter that shifts HV and thermal budgets together |

### 5. Expert conflicts that physics resolves

| Conflict in practice | Resolution |
|---|---|
| Ott (perimeter stitching) vs Hubing (distributed) | They optimise different outputs: edge radiation vs the first cavity mode. Perimeter-only raises the first mode only ~1.5× (FE33, [fields-si-emi](fields-si-emi.md)) |
| Rohm vs MPS: copper under the inductor | Shield class decides it: −0.2% L for shielded parts, ~6% for open drum cores (PW46) |
| "Minimize loop area" vs "minimize loop length" | Plane distance decides: with a close plane, L follows height × squares; without one, area ([pdn-and-commutation](pdn-and-commutation.md)) |
| Thermal reliefs: balance vs inductance | Process decides (TM42). Reflow balance depends on what the pad's plane carries, not the relief (TM39) |
| "Keep high current away" vs dense placement | For loops over a close plane, height dominates distance. For wide dv/dt copper, height barely helps, so distance or burying the victim matters ([lens-sy](lens-sy.md)) |

## Recommendations for our system

1. **Build the physics core as the nine kernels in §1**, starting with the sheet operator (φ and ψ together), PEEC and adjoints. Merge the existing scripts into them (SIM46).
2. **Make S1 the first integrated demonstration:** circuit adjoint × field adjoint on one buck plus ADC board, checked against finite differences and one openEMS or FastHenry run (internal only).
3. **Implement S2 and S3 inside the joint optimizer before tuning anything else.** They change what the optimizer *can* find, not only how fast.
4. **Run one coupon program for all five workstreams that asked for one**, designed so each coupon isolates one kernel's prediction.
5. **Keep a convergence register.** When a new idea duplicates an existing one from another direction, record both. Independent rediscovery is evidence and should raise the idea's priority.

## Conflicts and open questions

- S1 assumes the circuit is linearizable around its operating point. Linear budgets fail for a slow 48 V bridge ([schematic-to-physics](schematic-to-physics.md)), so the chain needs trust-region re-linearization (DR11) or transient adjoints there.
- S2's Δψ² law holds for spread sheet current; a narrow return under a trace is a different regime (ℓ·ln ℓ) ([cross-domain-lessons](cross-domain-lessons.md)).
- S10's market may not converge on non-convex problems, and duals are local. Every price needs a "valid within" margin ([physics-in-the-loop-optimization](physics-in-the-loop-optimization.md)).
- Convergence counts are a judgement [I].

## Sources

The eleven idea files in [docs/ideas/physics-first/](../../ideas/physics-first/README.md) and the topic docs linked inline. [C] values are quoted from the scripts in [`tools/research/physics/`](../../../tools/research/physics/).

See also: [physics/README](README.md) · [research-gaps](research-gaps.md) · [cross-domain-lessons](cross-domain-lessons.md)
