# Lens CT: conservation, continuity and topology

**TL;DR**
- **Kirchhoff's laws never fail; they are the exact, metric-free half of Maxwell's equations.** Total current (conduction plus displacement) always closes, and a cycle's EMF is its flux. What fails is the assumption that all C, L and M sit inside the parts. Layout adds displacement edges to conductors the schematic never names (chassis, heatsink, cable, earth), flux shares and holes. A current-aware system carries this extended graph.
- **Split every physics question into an exact topological part and a metric part.** Topology (cycles, cuts, the holes a return winds round, regions hanging on one point) needs no solver and changes only by discrete moves; 13 of round 1's 39 critics have such a core. Gradients hold only between topological events.
- **A cut costs the square of the current it intercepts, not the copper it removes** [C]: (2/π)·R_s·ln sec(πx/2) for a centred slit taking a fraction x of a strip's current, exactly twice that for an edge notch. A first-order adjoint misses a cut by its aspect ratio (29× on round 1's slot); a crack form from the same solve is within 9% there and within ±25% on 75% of 36 random cuts.
- **Charge conservation on the board's boundary gives one-cable CM current exactly:** I_CM = −jω·Σ C_i,ext·V_i. One electrostatic solve gives every C_ext. Bonds and Y-capacitors move a displacement edge inside the boundary: a 10 nH heatsink strap to DC− instead of chassis gives −39 dB at 30 MHz but only −20 dB at 100 MHz [C].
- **"Single point" is exact only as an articulation point.** A neck of width w leaks ~w² on a flank of the aggressor's flow but ~w⁴ at its stagnation point, 1,300× less at 1.6 mm [C]. Partial-inductance "bounce" depends on the victim's closure: 30–96% of L_p [C].

Tags as usual; [C]: [ct_cut_topology.py](../../../tools/research/physics/ct_cut_topology.py). CT ids: [ideas: lens-ct](../../ideas/physics-first/lens-ct.md); others: round 1 ([catalog](../../ideas/physics-first/README.md)).

## Key facts

### 1. Principles

| Principle | Equation | Circuit limit, and where layout bends it |
|---|---|---|
| CT-P1 Total current closes | ∇·(J + ∂D/∂t) = 0; on any closed surface, Σ I_k = −jω·Q_S | KCL needs K_C = ω·C_par·\|Z_node\| ≪ 1; high-Z nodes break first (100 kΩ, 0.2 pF: 8 MHz) |
| CT-P2 Faraday with topology | ∮_γ E·dl = −jω·Φ_γ; Φ_γ depends only on γ (∇·B = 0) | KVL needs K_L = ω·L_γ/\|Z_γ\| ≪ 1; low-Z loops break first (1 mΩ shunt, 1 nH: 160 kHz). A partial inductance is a gauge-dependent share of Φ_γ |
| CT-P3 Ampère with topology | ∮_γ H·dl = current through any surface bounded by γ | Metric-free: a cable's CM current is the net current through a cut of the bundle |
| CT-P4 Graph homology | b1 = E − V + b0 independent cycles, V − b0 cuts; loop currents live on the chords of a spanning tree | Cycles couple conductively iff they share an edge (topological), otherwise only via M and C (metric) |
| CT-P5 Sheet topology (Hodge) | J = ∇ψ × n + Σ α_i·h_i, one circulation h_i per hole; Δψ is the current across a curve; ψ jumps by the via current around a via | Hole circulations: zero EMF at DC, flux through the hole at AC; every hole is a potential shorted turn |
| CT-P6 Block–cut theorem | With no mutual coupling across a cut vertex, s→t current is zero in every block off the s–t path of the block–cut tree | The only exact "no foreign current"; a real neck leaks as a power of its width |
| CT-P7 Topology exact, metric approximate | Incidence laws hold exactly on any cell complex; constitutive laws carry all approximation (Tonti; Gross and Kotiuga [S]). "Homology is the bridge between field theory and circuit theory" ([Kotiuga and Lahtinen](https://arxiv.org/abs/1809.01002) [P]) | Topological checks are exact and cheap; topological moves need event costs, not derivatives |

The circuit is the limit that lumps each edge's metric into a part; layout adds edges and conductors, and PEEC is the graph on which Kirchhoff's laws hold again ([vocabulary](vocabulary.md#the-physics-graph)).

### 2. Derivation map

| Round-1 result or rule of thumb | From | What this lens adds |
|---|---|---|
| Every current has a return; half-ports; FastHenry NaN (LA1, [vocabulary](vocabulary.md)) | P1 | The return may be displacement; a port closing only through the world is an antenna (CT15) |
| Δψ² slit law with edge factor "about 2", 12–19% low (XD2); adjoint misses a slot 30× ([solver-ladder](solver-ladder.md), SIM25) | P5, P7 | Exact ln sec law; factor 2 by mirror symmetry; the miss is the cut's aspect ratio (D1) |
| "Capacitance to whom", heatsink to DC−, voltage-driven CM (S4, DR28, FE17) | P1 | I_CM = −jω·Σ C_ext·V (D2) |
| ΔZ_ret·I between cable points (README P6, FE1, DR24) | P2 | EMF of the external cycle; the partial form assumes the cable closes far away |
| Star ground, one AGND–PGND tie, peninsula, crossover ground map (P11, DR26, RG19) | P6 | Zero only at an articulation point; neck leakage w² vs w⁴ (D3) |
| Kelvin; "no foreign current between the two points of any voltage that matters" (XD72, [research-gaps](research-gaps.md)) | P2, P4, P6 | DC: edge-disjoint cycles or equipotential taps; AC: budget the cycle (D4) |
| Height × squares (README P3, LA26); "no loop inside another" (P17) | P2 | Over a plane each conductor closes through its image; nesting keeps only its sign (D5) |
| Don't cross splits; "one ground"; "bond everything that leaves the board at RF"; no ferrite in a return; pin-1 ([emc-placement](../rules/emc-placement.md)) | P1, P4 | Which cycles exist and where they cross the boundary: exact, solver-free |

### 3. Five derivations

**D1. The cut-flux law.** A crack of length 2a across uniform sheet current J_n carries a potential jump φ⁺ − φ⁻ = 2R_s·J_n·√(a² − s²) (flat-plate flow). By reciprocity the extra loss is ∫J_n·(φ⁺ − φ⁻) ds = πa²·R_s·J_n² = (π/4)·R_s·Δψ², with Δψ = 2a·J_n the intercepted current. An insulating edge is a streamline, so a notch of depth ℓ is half of a mirrored slit of length 2ℓ intercepting 2Δψ: (π/2)·R_s·Δψ², exactly twice. In a strip, conformal mapping (behind Johnson's crack gauge, [Tarnowski et al.](https://spiral.imperial.ac.uk/handle/10044/1/59331) [S]) gives (2/π)·R_s·ln sec(πx/2) for a centred slit and twice that for a notch, x = Δψ/I. For non-uniform J_n, ΔP = πa²·R_s·Σc_k²/k over its Chebyshev U_{k−1} coefficients. The exact cost over the k cut edges (base voltages v, conductances D) is vᵀ(D⁻¹ − UᵀG⁻¹U)⁻¹v (Woodbury); the adjoint is its first Neumann term vᵀDv, and the cut's collective response multiplies that by (π/4)(ℓ/w)·F(x) (w: cut width; F: ln sec correction). Lenses [SY](lens-sy.md) (images) and [CD](lens-cd.md) (spanning-tree leverage) reached the same law independently.

| [C] | Result |
|---|---|
| strip, W = 20 mm, zero-width cuts (two grids, Richardson) | Both ln sec forms within 0.15% (x = 0.1–0.9); notch/slit 2.000 at every x. Round 1's "12–19% low" = ln sec term (+0.4 to +12%) plus cell-wide-cut error (+6 to +14%). Off-centre slits +3–7% at equal Δψ |
| pour, round 1's 6 × 0.2 mm slot | exact +8.06 mW; adjoint +0.27 mW (29× low; aspect-ratio law 33×); Δψ² law 6.40 mW; crack form × width × ligament factors 8.76 mW (+9%) |
| pour, 36 random zero-width cuts, 1–8 mm | median ratio to exact: adjoint 0.021, none within 2×; Δψ² law 0.90, 72% within ±25%; crack form × ligament 0.95, 75% within ±25%, all within 2×. The miss grows as (ℓ/cell)^1.02; theory says 1 |

**D2. The board–world cut.** Let a surface S around the board be pierced by one cable. CT-P1 gives Σ cable currents = −jω·Q_S. In the capacitance matrix (the outside world as one more conductor) the mutual terms between board conductors cancel, so Q_S = Σ_i C_i,ext·(V_i − V_ext) and **I_CM = −jω·Σ_i C_i,ext·V_i**. One electrostatic solve (outside at 1 V, board at 0 V) gives every C_ext. Only capacitance to the outside counts (S4); antiphase nodes cancel (CT10); a heatsink bonded to DC− moves its 22 pF inside S. Shim and Hubing's V·C_part/C_board ([fields-emi-budget](fields-emi-budget.md)) is the one-node case; current-driven CM is the dual: KVL on the cycle through two cables.

| [C] share of the SW–heatsink displacement current reaching the LISN (lumped: 22 pF tab, 30 pF board–chassis, 25 Ω LISN) | 3 MHz | 30 MHz | 100 MHz |
|---|---|---|---|
| Heatsink bonded to chassis | 1.00 | 1.11 | 1.98 |
| 10 nH strap to DC− | 0.0001 | 0.013 | 0.073 |
| Strap plus 4.7 nF Y-capacitor DC−–chassis | 0.00004 | 0.0002 | 0.003 |

The cut-set identity holds to 10⁻⁷. A minimum-|Z| cycle census shows the driven cycle moving inside; it leaks again as ωL_strap nears the chassis path's impedance.

**D3. Articulation and the neck law.** A block on one cut vertex has one terminal, so its current is exactly zero. A neck of width w is an aperture in an insulating wall. With the outside potential along the mouth φ(s) = φ₀ + E_t·s + ½φ″·s², the linear term drives a boundary dipole ∝ E_t·w² (field inside ∝ 1/r). On an equipotential (E_t = 0, the aggressor flow's stagnation point) only the quadrupole ∝ φ″·w⁴/r² remains.

| [C] 12 mm island, 0.4 mm slot ring, uniform field: centre spread / solid sheet | w = 0.4 mm | 0.8 | 1.6 | 3.2 | 6.4 |
|---|---|---|---|---|---|
| Neck on a flank (mouth along the flow) | 3.0×10⁻⁵ | 6.0×10⁻⁴ | 5.6×10⁻³ | 3.4×10⁻² | 0.15 |
| Neck at the upstream stagnation point | <10⁻⁹ | 5.5×10⁻⁸ | 4.3×10⁻⁶ | 1.5×10⁻⁴ | 2.6×10⁻³ |

Local slopes fall to 2.2 and 4.1 at 3.2–6.4 mm (theory: 2 and 4): whether DR26's 4 mm neck "still leaks" depends on where it is. At HF an articulation point feeds the cable antenna, which is why LearnEMC calls a single-point I/O tie "one of the worst" ([myths](../rules/myths-and-contested.md)).

**D4. Partial inductance depends on the victim's closure.** A victim cycle sharing segment S with an aggressor and closing through its own conductor V sees EMF = jωI·[L_p(S) − M_p(S, V) + …], not jωI·L_p(S). Partial inductances are shares of ∮A·dl in one gauge; a gauge change moves voltage between segments but never changes a cycle sum.

| [C] victim closes at | 0.5 mm | 1 mm | 2 mm | 5 mm | 10 mm |
|---|---|---|---|---|---|
| TVS ground via, 1.6 mm (L_p 0.69 nH); victim's own via | 47% | 68% | 82% | 93% | 96% |
| Shared 20 × 0.5 mm ground trace (L_p 19.5 nH); victim's parallel return | 30% | 44% | 57% | 73% | 83% |

Round 1 saw this for Kelvin routes (0.55–0.87 nH by route, [pdn-and-commutation](pdn-and-commutation.md)) yet kept shared-segment ledger rows (LA6, LA21, DR47).

**D5. Why loop area fails near a plane.** Over a close plane each conductor closes through its own image, so flux rides on thin ribbons, not on the plan-view area. [C nest] (10 mm aggressor, 3 mm victim): in free space, nested and centred gives 1,060 pH against −32 pH at an 8.5 mm outside gap. Over a plane 0.1 mm below: 2.5 pH nested and centred, 45 pH 0.5 mm inside the edge, −43 pH 0.5 mm outside. Nesting then fixes only the sign.

### 4. Convergences and synergies round 1 missed

- **One cut-flux law, found five times:** pour slits (XD2, XD3, SIM25); slots and merged antipads under signals (FE2, FE4, PC11); "a cut across the heat flow costs 20–30× one along it" ([thermal-physics](thermal-physics.md), TM5); hatch along streamlines (XD61); Ott's aperture rule, where the longest dimension sets leakage. Each is κ·Φ²/σ with its own flux (CT1).
- **One boundary surface, nine ideas:** S4, PW4, DR28, LA5, LA10, FE14, FE17, PC22 and XD73 all apply KCL to the board–world cut; with DR1's passports, CT9 gives each conductor's CM share and phase.
- **One cycle-space choice per band:** P11, DR26, LA7, LA20, LA34, RG19, XD121, LearnEMC's "at LF limit the options, at HF provide one good path" and Hubing's "one ground" say one thing: a tree below f_x, a mesh above, with capacitor and ferrite ties making the topology band-dependent (CT13, CT20).
- **One family of events:** JPR2/JPR3, the adjoint's cut miss, OP41, PC8 and FE4 are discrete changes of the conductor complex. Pricing them as events (CT28) gives S1's chained adjoint its trust region.
- **Cells are cuts:** DR22, DR42, S6, XD12 and XD73 define a region by what crosses its boundary (CT31).

### 5. Transfers

- Pour slits (XD2), crack polarization and grid outage factors (XD51) → slots, shields, seams, heat spreaders (CT1, CT2, CT5).
- Magnetics (slit shields, no shorted turns) → pours and cut-outs under inductors (CT6, CT7); fluid stagnation points → star points (CT19).
- Kelvin route dependence → every common-impedance budget; ESD paths → all compliance tests as relative cycles (CT22, CT17).

### 6. What each conductor is doing

A netlist is H0 of the copper: which pins share a conductor. Round 1's atoms are the next layer in disguise. A Port is the boundary of a relative 1-cycle (a terminal pair); a Loop, a 1-cycle with its flux surface; a Node, a conductor whose current closes by displacement; a Reference, the subcomplex chosen per band to carry returns; a Discontinuity, a reference hole under a shadow; a Cavity, a region between references whose vias are handles; an Antenna, a cycle closing through the world; a Barrier, a cut with only displacement edges. Body, Channel and Heat path are mainly metric. Each conductor also has a per-band role, found without a solver (fields for [lens-cd](lens-cd.md)'s passport):

| Role | Detected by | Physics | Example |
|---|---|---|---|
| Bridge | removing it raises b0 | carries all current between two regions; N-1 critical | single AGND–DGND tie, pour neck |
| Shared edge | on two or more active cycles | common-impedance coupling | ground trace shared by hot loop and FB return |
| Chord | closes one cycle of the reference tree | one loop current; that cycle is its return | a signal trace |
| Dead end at this band | in no conduction cycle | displacement current only: a Node or stub | switch node at HF, floating fill |
| Ring | removing it lowers b1 | circulation driven by flux through its hole | pour around a cut-out |
| Handle | via joining copper already connected | adds a cycle: local return, cavity damping | stitching via |
| Cut member | crosses a declared boundary | must be filtered, bonded, balanced or budgeted | connector pins, Y-capacitor |
| Linked | its flux threads an external cycle | drives CM EMF | fast trace between cable connectors |

### 7. Critique of round 1's synthesis

1. **Principle 1 and the half-port validator equate a return with a conductive return.** FastHenry's NaN is a property of magnetoquasistatics, which cannot see CM. Name each port's closure per band: conduction, internal displacement or displacement to the world (CT15).
2. **"Voltage between two points" is used at AC without a path** (Principle 6, DR24, LA6, LA21, DR47, research-gaps; lens SY agrees). It is exact at DC and path-dependent at AC. Budget cycles, not segments (D4, CT22).
3. **S1 claims gradients for "every copper cell, via and pad pose".** That holds within one topology; vias, cuts and new connections are events, where round 1's data show a 29× miss (CT2, CT28).
4. **The nine objects treat topology shallowly.** Missing: cycle and cut spaces with tree–cotree (ground loops, Kelvin, star points, filters), relative cycles (ports, antennas), H1 of the copper (holes, rings, handles), and the Hodge decomposition that makes φ, ψ and per-hole circulations one object.
5. **The basis quantity M lumps two couplings** ([rule-basis-set](rule-basis-set.md)). Shared-path coupling needs a shared edge, and re-routing zeroes it exactly; field coupling never vanishes. Return-path continuity is a topological invariant with an exact gate (CT29).
6. **Principle 7 uses "topology" for "early, big decisions".** Some evidence is metric (cables on one edge, 40 dB), some topological (a split, 38 dB; the heatsink bond, 39 dB here); only the latter are discrete.
7. **Principle 14's locality is an unwritten cut statement.** KCL zeroes the net current across any boundary; measure the circulation crossing it, Σ|I_k| per band (CT31).
8. **The invisibility index is blind to CM as specified:** without a world node, KCL on the board's boundary forces zero external current (CT16).
9. **The f_x convergence lacks its topological reading:** f_x is where the best reference topology turns from tree to mesh, so star and plane camps both have real cases.

## Recommendations for our system

1. Add a topological layer to the board physics model (PC1): per-band conduction graph, block–cut tree, extended-graph cycle basis, b0/b1 and holes per reference, return words; run it before every metric critic (CT27, CT29).
2. Before trusting LII, budget couplings on cycles (CT22) and add the world node (CT16).
3. Put the cut-flux price (CT1, CT2) into the occupancy market (S2) and the optimizer's price map.
4. Add the board–world charge ledger (CT9) beside the MREMC chain.
5. Synthesize grounding as a per-band cycle space (CT20, CT19, CT13); make physics events part of the joint state (CT28).

## Conflicts and open questions

- The cut constants are DC sheet results; for a slot under a trace at HF (3-D field, ℓ·ln ℓ growth, [physics-critics-validation](physics-critics-validation.md)) only the topology carries over.
- C_ext depends on the environment: rank by it; validate with a cable model.
- The block–cut theorem fails when M or C bridges the cut vertex (CT13 says where); the neck and CM models are idealized.

## Sources

- P. R. Kotiuga and V. Lahtinen, [arXiv:1809.01002](https://arxiv.org/abs/1809.01002) [P]; P. W. Gross and P. R. Kotiuga, *Electromagnetic Theory and Computation: A Topological Approach*, Cambridge, 2004 [S]; the cell method, [Alotto, Freschi and Repetto 2013](https://link.springer.com/978-3-642-36100-5) [S].
- Johnson's crack formula: [Tarnowski et al., Exp. Mech. 2018](https://spiral.imperial.ac.uk/handle/10044/1/59331) [S], checked here by finite differences [C].
- Shim and Hubing and LearnEMC, via [fields-emi-budget](fields-emi-budget.md) and [myths-and-contested](../rules/myths-and-contested.md).
- Round-1 numbers: [solver-ladder](solver-ladder.md), [cross-domain-lessons](cross-domain-lessons.md), [worked-thought-experiments](worked-thought-experiments.md), [pdn-and-commutation](pdn-and-commutation.md).

See also: [README](README.md) · [cross-workstream-synthesis](cross-workstream-synthesis.md) · [research-gaps](research-gaps.md) · lenses [VP](lens-vp.md), [SY](lens-sy.md), [LS](lens-ls.md), [TH](lens-th.md), [IN](lens-in.md), [CD](lens-cd.md)
