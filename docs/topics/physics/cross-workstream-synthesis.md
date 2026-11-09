# Cross-workstream synthesis: convergences, synergies and transfers

Scope: what eleven research workstreams (rules, language, solvers, power, fields, optimization, manufacturing, reasoning, critics, other fields, joint P&R) share: nine mathematical objects, convergent ideas, synergies S1–S11, transferable lessons, expert conflicts resolved. Not here: principles -> [foundations](foundations.md); kernels as built -> [physics-core-v2](physics-core-v2.md); gaps -> [research-gaps](research-gaps.md); other fields -> [cross-domain-lessons](cross-domain-lessons.md).
Keys: nine objects, screened Laplace, stream function ψ, PEEC, adjoint, reciprocity, Lagrange multipliers, prices, eigenmodes, multipole, homotopy, morphology, convergence register, chained adjoints, S1–S11, capacitance to whom, three-commodity market, Kelvin taps from equipotentials, transfers

Ids refer to the [physics-first ideas](../../ideas/physics-first/README.md). Synthesis [I] unless a number is tagged; [C] numbers come from the workstreams' scripts in [`tools/research/physics/`](../../../tools/research/physics/). Independent rediscovery (2–5 times from different directions) is the evidence an idea is fundamental [I]; record each in a convergence register and raise its priority.

## 1. The nine mathematical objects underneath everything

Physics-first layout needs these kernels, not hundreds of rules or dozens of tools; every critic, optimizer term and explanation is a query over them. Built as the eight kernels of [physics-core-v2](physics-core-v2.md) (merge existing scripts in, SIM46).

| Object | Where it appeared | One engine serves |
|---|---|---|
| **Screened Laplace on sheets** (φ, length scale λ) | IR drop and pour L (OP1); thermal fin (TM1, TM2); decap reach (XD113); via transfer length (XD22); plane spreading L (PW37, PW38); topology optimization (OP2) | IR, heat, decap placement, via rows, pour synthesis, Kelvin taps |
| **Stream function ψ** (dual of φ) | coil design (XD1–XD4); slot damage Δψ² (XD2, SIM25); streamline power routing (PW16); pin-1 check (XD70); direction fields (XD98) | cut pricing, routing through pours, shield-current checks |
| **Partial-element matrices** (R, Lp, P, τ = PEEC) | three separately written solvers (`sl_`, `pw_`, `fe_`); four primitives of [rule-basis-set](rule-basis-set.md); LA21 accounting unit; XD30 compression | loops, returns, couplings, decaps, slots, macromodels |
| **Adjoint / reciprocity** | circuit `.noise` (DR3); copper sensitivity (OP38, OP40, PW39); susceptibility maps (XD35); transfer-inductance maps (FE3); topological derivative (OP41) | susceptibility, shadow prices, explanation, "where to add copper" |
| **Lagrange multipliers / prices** | PathFinder history and pressure (JPR11, JPR12); budget shares √(k·s) (DR9); constraint price tags (JPR34); copper price (OP3, OP25, XD56); compute market (SIM40, SIM45); "nH in watts" (PW30); dB as currency (LA19) | arbitration among physics, space, compute; the LLM's interface |
| **Eigenmodes** | plane cavities (FE26–FE28); box modes (XD85); characteristic modes (XD34); energy participation (XD84); ring frequency (PW31); vibration (TM45) | resonance avoidance, stitching, frequency planning |
| **Multipole expansion** | loop + image as quadrupole (LA26); buffer distance from multipole order (XD68); figure-8 loops (XD11); opposite-current via pairs (PW36); dipole algebra for magnetics (PW47, XD71) | keep-out halos, cancellation, orientation |
| **Homotopy / topology classes** | joint state (JPR1–JPR4, JPR7); returns around slots (FE1); ψ level-set crossings (XD3) | joint P&R, return continuity, cut legality |
| **Morphology, signed distance** | fab filters (OP51, XD66, OP7, XD33); SDF clearance (XD94); acid traps (TM38); medial-axis necks (XD95); legalizer (OP50) | DRC inside the optimizer, legalization, necks |

## 2. Convergences: the same idea from different directions

| Idea | Found by | Consequence |
|---|---|---|
| Reverse-return feeding of paralleled parts | PW14 (sharing 9.8:1 → 1.8:1 [C]); XD47 hydronic heating (13.6 → 2.4 [C]) | equal path length is a law of parallel flow; make it a generator |
| Orient magnetics by dipole coupling | PW47 (Dodd–Deeds field); XD71 (NMR magic angle, null at 54.7° [C]) | dipole algebra replaces "rotate 90°"; 90° is not the null for in-plane axes |
| Curves only where physics pays | RG44, OP35, PW18, TM47, FE39/FE45 | regime-gated operator; fabs make curves at no extra cost |
| Calibration coupons | SIM12, PC37, RG35, TM29, PW50 | one coordinated coupon program, each coupon isolating one kernel's prediction ([research-gaps](research-gaps.md) gap 1) |
| Mine vendor eval boards for budgets | RG7/RG8 (back-solve a rule's budget), DR50 (EVMs as floors), SIM13 (vendor data, de-embedded) | EVMs are the cheapest F4 data and floor oracle |
| Electro-thermal coupling | TM16, PW49, OP11, LA28, RG50, XD20 | one graph; coupled solve cheap away from runaway |
| Per-pad thermal-relief decision | RG28 (L, R, R_th vs budgets), OP9 (spokes vs heat flow), TM42 (assembly process) | one multi-objective per-pad choice; WS7: reliefs barely move reflow balance |
| Loop area is the wrong proxy | LA26, SIM15, PW25, OP22 | area tiers near planes retired ([hot-loops](../rules/power/hot-loops.md)) |
| Cells / locality as the unit | DR22 (HF current closure), LA9 (typed molecules), XD12 (P/N cells), JPR20 (exact cell micro-solve), DR42 (locality index) | cell = unit of hierarchy, beauty, explanation (S6) |
| Keep foreign current out of measurements | LA7, LA8, LA33, XD72, PW41, PW42, RG16, DR26, XD69 | a checkable invariant, not a rule family |
| Physics kernels replace HPWL and density | XD112, OP23, OP24, TM2, FE3, FE11 | placer objective of FFT convolutions with real kernels |
| Rules as warm starts and move generators | RG41–RG43, JPR7, JPR10, OP19 | human practice seeds, physics judges |
| Frequency planning | FE13, FE50, DR36, PW31, OP16, PC12 | spectral coincidence (source × structure × victim) is one check (S8) |

## 3. Synergies: combinations worth more than their parts

**S1. Chained adjoints (end-to-end differentiable invisibility).** ∂output/∂geometry = (∂output/∂parasitic: circuit adjoint DR3, SPICE `.noise`, one solve) · (passive macromodels SIM33, LA22, XD28 linking partial elements to the PEEC graph) · (∂parasitic/∂geometry: field adjoint OP38, OP40, PW39). Result: ∂(invisibility index)/∂(every copper cell, via, pad pose) for 2 extra solves, within one topology and one linearization. Vias, cuts, new connections are topological events priced by exact rank-k updates; switching or sampled circuits need a periodic adjoint ([lens-ct](lens-ct.md), [lens-cd](lens-cd.md), [lens-sy](lens-sy.md)). Proposed by no single workstream. First integrated demo: one buck + ADC board, checked against finite differences, direct AC (DR3 matched to 6e-13 [C]) and one openEMS or FastHenry run (internal only).

**S2. Pours and routes trade through ψ.** The Δψ² cut price (XD2, SIM25; law and along/across ratio: [cross-domain-lessons L1](cross-domain-lessons.md#l1-coil-design-by-stream-functions--pours-slots-planar-coils)) and the low value of a pour's last area (PW10, [power-copper §3](power-copper.md#3-trace-vs-pour-vs-plane)) [C] let the occupancy market (JPR8, OP32) price pour cells for routing by Δψ², PW16 route power along streamlines, and signals cross pours where it costs nothing.

**S3. All-pairs coupling from one solve per victim plus one per aggressor.** Victim susceptibility fields by reciprocity (XD35); aggressor near fields as convolution kernels (OP24, XD112); connector-pair transfer-inductance maps, one solve per pair (FE3); victims weighted by circuit-adjoint output sensitivity (DR3). Each pair's coupling is an inner product, a placer lookup, replacing O(N²) Neumann integrals and "keep away" rules. Implement S2 and S3 in the joint optimizer before tuning: they change what it can find.

**S4. "Capacitance to whom" dissolves the switch-node conflict** ("SW area: Cm vs Th vs R", P07/P08).
- PW4: a fast node's C splits into local return (harmless, inside the loop), outside world, victims.
- PW5: heat through a thin dielectric at G/C = k/ε costs switching loss, negligible at 12 V and binding at 400 V ([power-copper §1](power-copper.md#1-node-and-branch-classification-the-decision-procedure)) [C].
- DR28: bond the heatsink to DC−, so its ~22 pF goes to a quiet node [C].
- Rule: spread SW heat into the node's own return plane; bond external metal to quiet nodes; EMI budget counts only C leaving the cell. Low voltage: conflict largely gone; 400 V: ½CV²f binds. Replaces "never heatsink through SW copper".

**S5. Cancellation aims nulls.** Primitives: LA35 `cancel`, XD11 figure-8, PW36 opposite-current via pairs, PW51 interdigitated fingers, XD76 gradiometric sense, XD15 orthogonal gate loop; each raises multipole order. XD68: dipole ∝ 1/r³, quadrupole ∝ 1/r⁴. Over a plane the near halo barely changes (radius −2%); cancellation buys an exact null plane and a quieter far field (−22 dB at 100 mm), capped near 20·log ε by imbalance ε ([lens-sy](lens-sy.md)) [C].

**S6. The cell as one unit for four jobs.** Hierarchy: DR22 cells → JPR macros (JPR20 exact in-cell solve, JPR16 multigrid across cells). Beauty: DR42 locality index. Explanation: cell ports = LA1 half-ports. Protection: XD73 lightning-style zones (every conductor crossing a boundary filtered or bonded). ESD/immunity pieces DR47, RG22, FE44, XD52, XD73 fit this framework; partly closes [research-gaps](research-gaps.md) gap 6.

**S7. Unified via theory** (one band-indexed objective for return, decap, power-field, thermal and stitching vias; today five rules):

| Facet | Source |
|---|---|
| partial L ∝ ln(s/r), weak | FE, RG11 |
| cavity launch ∝ (ks)², strong at HF | FE5 |
| cluster perimeter, not count, sets spreading L | PW32, PW35 |
| transfer length sets DC sharing | XD22 |
| Peaceman well index for vias in coarse grids | PW13 |
| CAF spacing under bias | TM24 |

**S8. One frequency plan.** PW31 steers hot-loop ring frequency (90–290 MHz [C]) with L and snubber (PW29); OP16 moves cavity modes by plane shape; FE27, FE28 by stitching; FE13, FE50 plan clock harmonics against resonances and radio channels; PC12 scores overlaps. Choose L, C_snub, plane shape, stitching pitch and clock frequencies together so no strong line lands on a structural resonance or protected band.

**S9. Floors do three jobs.** floor = max(physics floor DR18, fab floor TM52: min width, space, dielectric cap loop size). It sets priority (τ, DR17), prunes moves (JPR30 admissible bounds), stops refinement (OP57). A budget below its fab floor is a requirement conflict for the human, not an optimizer failure.

**S10. Three-commodity market; prices are the LLM interface.** Goods: space (area, channels, layers: JPR8, OP3, OP6), physics budgets (nH, mV, K: DR9, I1), compute (solver calls: SIM40, SIM45). Multipliers = exchange rates ("1 mm² is worth x pH here", OP25, PW30). SIM44, DR14, LA40 independently: the LLM reads sensitivities and prices, not raw fields. With LA27/XD51 low-rank previews every menu operator comes priced in all three goods.

**S11. Kelvin taps from equipotentials.** OP1 computes φ for aggressor currents; taps on one aggressor equipotential see no foreign drop. DR26 (current-free peninsula synthesis), LA8 (sense ports), XD70 (no shield streamline across analog ground) reduce to reading φ and ψ from the same solve.

## 4. Transfers: learned in one place, needed in another

| Lesson | Learned in | Apply in |
|---|---|---|
| Post-hoc legalization destroys optimized results; hard constraints inside the loop | OP (an opening disconnected a load); JPR (final legalizer turned 602 into 1,164) | LLM repair proposals (legalize inside the generator), critic-driven repairs, pour synthesis, RL policies |
| Proxies with a non-shrinking error component fail among near-equal candidates (44% of pairs within 3% HPWL differ > 10% routed) | JPR; Cadence 12k-placement data; [lens-in](lens-in.md) | SIM10 VOI escalation at near-ties (where F2/F3 pays); JPR41 delayed acceptance with MS2 and decision-calibrated surrogates (SIM7) as first stage |
| Joint search refines; restarts find basins | JPR: improves its start 10/10, ties equal-CPU restarts ([joint-place-route-experiment](joint-place-route-experiment.md)) | OP (non-convex pours: multi-start, OP44 QD); DR40 continuation by τ. Protocol: diverse coarse starts → joint refinement → physics continuation |
| Robust erode/nominal/dilate | topology optimization (XD33, OP7) | impedance tolerance (TM35), σ-margin maps (TM31), critics at ±etch |
| Rank-1 (Sherman–Morrison) updates of a factored network | power-grid PTDF/LODF (XD51) | incremental critics (PC20 via-field min-cut, OP39 neck finder), LA27 previews, JPR move screening, U1 live HUD |
| Well index for sub-grid vias | reservoir simulation (PW13) | thermal vias in TM2/TM3, decap via fields (PW35), whole-board IR in placement (SIM47) |
| Lattices beat random stitching up to 2.2× at equal count | FE27 [C] | judge XD99 blue noise against a lattice, not random; FE28 eigenvalue gradients polish either |
| Data assimilation fits parameters to sparse observations | weather (XD111) | calibration ledger (FE56), conformal σ (SIM8), residual surrogates (SIM34) from coupons |
| Measured net passports replace name-based roles | DR1 | critic precision: role-blind critics raised 11 irrelevant warnings on one board (PC) |
| Regime gating removes inactive physics | RG2, FE39, SIM4, LA11 | drop inactive terms from JPR's objective per structure, not just from reports |
| Planes typed `signal` invite routers to perforate them | PC44 | cheapest bench experiment: retype planes, measure physics scorecard and vias (JPR's gains came from fewer vias) |
| Pinout sets the return at the cable boundary | ball maps (XD24), pin swaps (JPR22), half-ports (LA1) | connector pinout as CM-chain lever ([fields-emi-budget](fields-emi-budget.md)) |
| Air density drives breakdown and cooling | TM21 (Paschen); [research-gaps](research-gaps.md) gap 9 (convection ∝ ρ^0.5) | one environment regime parameter shifting HV and thermal budgets together |

## 5. Expert conflicts that physics resolves

| Conflict | Resolution |
|---|---|
| Ott (perimeter stitching) vs Hubing (distributed) | different outputs: edge radiation vs first cavity mode; perimeter-only raises the first mode only ~1.5× (FE33, [fields-si-emi](fields-si-emi.md)) |
| Rohm vs MPS: copper under the inductor | shield class: −0.2% L shielded, ~6% open drum cores (PW46) |
| Minimize loop area vs loop length | plane distance: close plane → L ∝ height × squares; no plane → area ([pdn-and-commutation](pdn-and-commutation.md)) |
| Thermal reliefs: balance vs inductance | process decides (TM42); reflow balance depends on what the pad's plane carries, not the relief (TM39) |
| "Keep high current away" vs dense placement | loops over a close plane: height dominates distance; wide dv/dt copper: height barely helps, use distance or bury the victim ([lens-sy](lens-sy.md)) |
| Pours vs routing space | cut along streamlines, priced by ψ (S2) |
| Keep-out distance | which field couples, and where its null points (S3, S5) |

## Open questions

- S1 assumes a circuit linearizable at its operating point; linear budgets fail for a slow 48 V bridge ([schematic-to-physics](schematic-to-physics.md)): needs trust-region re-linearization (DR11) or transient adjoints.
- S2's Δψ² law holds for spread sheet current; a narrow return under a trace is a different regime (ℓ·ln ℓ) ([cross-domain-lessons](cross-domain-lessons.md)).
- S10's market may not converge on non-convex problems; duals are local, so every price needs a "valid within" margin ([physics-in-the-loop-optimization](physics-in-the-loop-optimization.md)).
- Convergence counts are a judgement [I].

## Sources

The eleven idea files in [docs/ideas/physics-first/](../../ideas/physics-first/README.md) and topic docs linked inline.
