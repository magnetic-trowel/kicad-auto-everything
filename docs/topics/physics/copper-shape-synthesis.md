# Copper shape synthesis: topology optimization for pours, planes and power copper

**TL;DR**
- **A pour is a conductivity field, and three of its physics share one operator.** DC IR drop, the inductive limit of a pour over a reference plane, and heat spreading are each a 2-D (screened) Laplace problem with a different sheet coefficient: 1/R_s, 1/(μ0·h_eff), or k·t plus convection. Structural topology optimization (SIMP, level set, phase field, ESO) transfers almost unchanged. The nearest published analogues are busbars, solar-cell metallization and volume-to-point heat conduction. The only PCB-pour precedent we found is an expired IBM heuristic patent.
- **Proof of concept** ([op_topopt_pour.py](../../../tools/research/physics/op_topopt_pour.py)): a 24×14 mm 1 oz region where a 6 A source feeds three loads. At equal copper area (105 mm²), topology optimization gives 1.79 mΩ loss resistance against 2.09 mΩ for a well-drawn trunk-and-branch layout (−14.5%). A full pour (323 mm²) gives 0.68 mΩ [C].
- **Honest magnitude: area matters more than shape.** A competent tree is already on the 1-D optimum for its topology (width ∝ current). Shape optimization was worth about 15% at equal area, and 18% over uniform widening at +25% area. It pays where amps are high (≳5 A), where IR or thermal margins are tight, or where several rails compete for one layer. For most low-current rails it does not matter [C/I].
- **DC-optimal is not HF-optimal once the reference is cut.** Above f_c = R_s/(2π·μ0·h) (0.3–0.6 MHz for 1 oz over 0.1–0.2 mm, ~40 kHz on 2-layer 1.6 mm), current in a pour spreads by inductance. Over a uniform plane, the DC- and HF-optimal shapes coincide. Across a reference slot they differ: in the POC the slot-aware shape cut L_eff by 10% for +9% R [C].
- **Fab rules map cleanly and belong in the optimizer, not only after it.** Filter radius and robust erode/dilate give minimum width, space and etch tolerance; contour plus Minkowski open/close removes slivers and acid traps; island removal enforces connectivity. Legalization cost 0.0–2.8% in R, but an opening wider than a drawn neck disconnected one design, so the minimum width must set the filter radius [C].

## Key facts

### One operator, three physics

| Physics | Sheet coefficient (per square) | Sources / sinks | Objective (self-adjoint form) | Valid when |
|---|---|---|---|---|
| DC conduction | G = 1/R_s, R_s = ρ_Cu/t = 0.491 mΩ/□ at 1 oz | pad currents; regulator pad at 0 V | loss P = Σ I_k·V_k (= I²·R_loss) | f < f_c, t < 2δ |
| Inductive limit, pour over a plane at depth h_eff | 1/(μ0·h_eff); μ0·h = 0.126 nH/□ at 0.1 mm | same, as AC currents | magnetic energy, L_eff = Σ I_k·Φ_k / I² | f ≫ f_c, w ≫ h, plane continuous or h_eff mapped |
| Heat spreading | k·t (copper + FR-4) + convection 2·h_c per area | dissipating parts | thermal compliance Σ P·T | steady state |

- **Crossover.** For a wide conductor over a plane, R′ = R_s/w and L′ = μ0·h/w, so f_c = R_s/(2π·μ0·h) does not depend on width [C]:

| Copper | h = 0.1 mm | 0.2 mm | 0.36 mm | 1.5 mm |
|---|---|---|---|---|
| 0.5 oz | 1.2 MHz | 622 kHz | 346 kHz | 83 kHz |
| 1 oz | 622 kHz | 311 kHz | 173 kHz | 41 kHz |
| 2 oz | 311 kHz | 156 kHz | 86 kHz | 21 kHz |

- **Consequence:** converter ripple and edges (≥100 kHz) see the inductive problem; DC load current sees the resistive one. Skin depth is 66 µm at 1 MHz, so 1 oz copper stays thickness-uniform up to about 4 MHz [C].
- **Where the analogy breaks:** narrow traces (w ≲ h) have fringing fields; boards without a plane need a 3-D partial-inductance model (PEEC/FastHenry); above the plane-pair resonance the shunt C matters. Signal nets carry no loss objective, so they stay paths ([physics-in-the-loop-optimization](physics-in-the-loop-optimization.md)) [I].

### Methods worth borrowing

| Method | Representation | PCB fit | Source |
|---|---|---|---|
| SIMP + density filter + Heaviside projection, OC or MMA update | density ρ ∈ [0,1], conductivity ∝ ρ^p | Default: simple, adjoint-cheap; threshold grey cells | Bendsøe–Sigmund; top88 (Andreassen 2011); Svanberg 1987 (MMA) [S] |
| Robust erode/nominal/dilate | three projections of one field | Etch tolerance (±20% width at JLCPCB), strict min width/space | Wang, Lazarov, Sigmund 2011; Qian & Sigmund 2013 [S] |
| Level set (SDF moved by shape derivative) | crisp boundary | Polish after SIMP; smooth, arc-friendly outlines | Wang, Wang, Guo 2003; Allaire et al. 2004 [S] |
| Phase field (Allen–Cahn) | diffuse interface, multi-phase | Several rails on one layer (sum-to-one per cell) | Takezawa et al. 2010 [S] |
| ESO/BESO (hard-kill by sensitivity) | binary cells | Fast screening; within 5% of SIMP in our POC | Xie & Steven 1993; Huang & Xie 2007 [S] |
| Constructal / growth heuristics | trees grown from the sink | Seeds and intuition | Bejan; Ikonen & Sobester [S] |
| IBM power-plane heuristic | equal-resistance blocks via a current "centre" | Minimum copper under an IR limit; expired | [US10546089B1](https://patents.google.com/patent/US10546089B1/en) [P] |

Topology optimization has run at 1.1 × 10⁹ voxels (Aage et al., *Nature* 2017) [S]; ours are 10⁴–10⁶ cells per layer.

### Prior art closest to PCB copper

| Domain | What was optimized | Result / note |
|---|---|---|
| Busbars | conductivity per element vs temperature; topology vs eddy loss and stray L | >50% copper saved at a temperature limit (laminated busbar, HAL); "inductance" ill-defined for multi-contact bars (TUM, Augsburg) [S] |
| Solar-cell front metallization (Gupta et al., TU Delft) | metal grid: resistive loss vs shading area | nearest analogue of a pour; >50% output gain on free-form cells; code [topsol](https://github.com/dkgupta90/topsol) [S] |
| Volume-to-point heat conduction | high-k inserts draining a heated area | SIMP and constructal trees; same Laplace structure [S] |
| Metallic antennas, microwave devices | conductivity per cell under Maxwell | Hassan et al., IEEE TAP 2014; Aage et al., IJNME 2010 [S] |
| mm-wave passives (Princeton) | pixelated multi-port EM structures, deep-learning inverse design | designs in minutes (Karahan et al., *Nat. Commun.* 15:10734, 2024) [S] |
| Silicon photonics | foundry rules inside topology optimization | width, space, area, enclosed area via differentiable morphology (Hammond et al. 2021) [S] |
| Photonic legalization | morphological and differentiable legalizers | design-rule violations "from thousands to zero" (OptiClear, [arXiv 2607.03632](https://arxiv.org/abs/2607.03632)) [P] |
| IC power grids | wire widths under IR and EM limits | sequence-of-linear-programs sizing (Tan, Shi); EM- and lifetime-aware SLP (TVLSI 2018) [S] |
| Power modules | die placement and traces vs parasitic L and temperature | PowerSynth (Arkansas): **academic/non-commercial licence, reference only** [S] |

No open tool synthesizes PCB pours from physics. Commercial PDN tools (Altium PDN Analyzer, Sigrity) analyze copper, and Sigrity OptimizePI searches decap sets; plane shapes stay manual [S/V].

### Manufacturing constraints mapped to PCB DFM

| Topology-optimization device | PCB rule | KiCad mechanism | Note |
|---|---|---|---|
| Density-filter radius r_min | minimum width/space (0.10–0.15 mm signal; ≥0.25–0.5 mm sensible for power) | `track_width`, zone `min_thickness` | Nominal-only SIMP has no strict length scale; use robust or geometric constraints (Zhou et al. 2015) for a guarantee [S] |
| Robust erode/dilate (η_e, η_d) | etch tolerance, over/under-etch | none (fab) | Set η from the fab's ±20% width tolerance [I] |
| Morphological opening by w_min | sliver and neck removal | zone fill removes sub-`min_thickness` copper | KiCad's filler is a last-resort opening, not a design method |
| Closing by gap_min | acid traps, narrow notches and slots | `clearance` | Close before open so notches do not survive |
| Curvature limit (level set, arc fit) | acute-angle avoidance | none | Physics prefers rounded inside corners anyway (current crowding) |
| Connectivity / no islands | floating copper removal | `island_removal_mode` | Must check source→every load, not only "touches a pad" |
| Passive solid / void cells | pads, keep-outs, mounting holes, antenna regions | rule areas, keep-out zones | Fixed before filtering |
| Per-cell area price | soft keep-out, routing corridor | none | Our "price" variant |
| Thermal relief | solderability vs resistance | `thermal_gap`, `thermal_bridge_width`, `connect_pads` | 4 spokes add 0.22 mΩ, 2 spokes 0.52 mΩ on a 2×2 mm pad [C] |
| Copper-density band | plating balance, warp | none | Add as a region constraint ([OP18](../../ideas/physics-first/optimization.md)) |

### Proof of concept

**Setup** ([op_topopt_pour.py](../../../tools/research/physics/op_topopt_pour.py), numpy/scipy/shapely/contourpy, deterministic):
- Region and copper: 24×14 mm, single layer, 1 oz.
- Source pad 3×3 mm at the left, held at 0 V. Loads: A 3 A (bottom right), B 2 A (top right), C 1 A (top middle).
- A 2 mm-radius mounting-hole keep-out on the axis.
- Q4 elements at 0.1 mm (34k nodes); SIMP p = 3, contrast 10⁻⁶.
- Linear-hat density filter r = 0.5 mm; Heaviside β doubled from 1 to 32; OC update; 200 iterations.
- Baseline: trunk 4 mm (6 A), branches 2 mm (3 A) and 1.5 mm (2 A), 45° bends. That is about 0.67 mm/A, generous by IPC-2221.

**Results** [C]

| Layout | Copper area | R_loss = P/I² | Drop at A / B / C | Loss at 6 A |
|---|---|---|---|---|
| Trunk and branches (human-style) | 104.9 mm² | 2.092 mΩ | 13.9 / 13.2 / 7.1 mV | 75 mW |
| Topology-optimized, same area | 104.7 mm² | **1.789 mΩ** (−14.5%) | 11.8 / 11.5 / 6.1 mV | 64 mW |
| Same, legalized (w, gap ≥ 0.5 mm) | 104.8 mm² | 1.790 mΩ | — | — |
| Greedy energy-ranked removal from full pour (14 solves) | 104.9 mm² | 1.882 mΩ | — | — |
| Full pour | 323.4 mm² | 0.677 mΩ | 4.5 / 4.2 / 2.5 mV | 24 mW |

Topology-optimized shape at equal area ('#' copper, 'o' keep-out; source at left, A bottom right, B top right, C top middle):

```
..........................########.................########.
........................###################################.
....................#######################################.
................#############......................########.
............#############...................................
.........############.......................................
..##############..........oooooooo..........................
.###########.............oooooooooo.........................
.########................oooooooooo.........................
.##################.......oooooooo..........................
........####################oooo............................
...........#########################........................
...................###########################..............
............................###############################.
....................................#######################.
................................................###########.
```

What the optimizer found:
- Two straight, tapered limbs split at the source around the hole; the upper one absorbs C and continues to B, the lower one runs straight to A.
- Every pad entry flares; there are no constant-width runs and no 45° doglegs.
- Grey measure 0.6%, minimum feature 1.5 mm: DC conduction favours thick members, so minimum-width rules rarely bind at this area.

**Area sweep** (DC only; area includes 34.5 mm² of pads) [C]:

| Area | 20% (63 mm²) | 30% (96 mm²) | 50% (161 mm²) | 70% (226 mm²) | 100% |
|---|---|---|---|---|---|
| R_loss / full pour | 6.2× | 3.0× | 1.6× | 1.17× | 1 |

Returns diminish: the last 30% of the area buys 15%.

**Multi-physics variants** [C]:
- **Routing-corridor price.** Copper in a 2 mm vertical corridor costs 4× area. Corridor copper halves (8.0 → 4.0 mm²) and R rises to 2.221 mΩ (+24%). Part of that rise is simply the smaller physical area the price leaves.
- **Reference slot.** A 1×6.5 mm slot in the L2 plane (h_eff 0.1 → 1.5 mm) lies in the path to A. Results at 100 iterations:

| Objective | R_loss | L_eff | Copper over slot |
|---|---|---|---|
| DC only | 1.821 mΩ | 0.659 nH | 2.3 mm² |
| 50/50 DC + L | 1.979 mΩ | **0.592 nH** | 2.5 mm² (wider, shorter crossing) |
| L only | 2.359 mΩ | 0.604 nH | 0 (routes around the slot end) |
| Human trunk and branches | 2.092 mΩ | 0.755 nH | — |

The L-only result is worse than 50/50, a local optimum. Multi-start or continuation is needed for non-convex mixes.

**Adjoint "where to add copper"** on the human layout [C]:
- Adjoint and central-difference gradients of the drop at A agree to 3.5 × 10⁻⁷.
- Adding 26 mm² (+25%) at the boundary cells ranked by energy density gives 1.531 mΩ. Uniform widening gives 1.666 mΩ. Re-optimizing at that total area gives 1.370 mΩ.
- Removing the 20% least-loaded copper raises R by 21%: this layout has little dead copper.

**Legalization stress test** (area = pads + 15% of the free area, 77 mm²) [C]:

| Filter radius | Raw R_loss, min feature | Legalized at 0.5 mm | Legalized at 1.0 mm |
|---|---|---|---|
| 0.2 mm | 2.843 mΩ, 0.70 mm neck | 2.921 mΩ (+2.8%) | **disconnected** (C/B limb cut) |
| 1.0 mm | 2.952 mΩ, 0.9 mm | — | 2.946 mΩ (−0.2%) |

A minimum width built into the filter costs 3.8% up front. Afterwards legalization is free and cannot cut the net.

**Runtime** (CPU time, one core, loaded shared VM, ±20% run to run; `--timing`) [C]:

| Grid | Nodes | Assemble + LU + solve | Extra back-substitution (adjoint) | Optimization iteration | Human-layout R |
|---|---|---|---|---|---|
| 0.4 mm | 2.2k | 9 ms | 0.3 ms | 9 ms | 2.170 mΩ |
| 0.2 mm | 8.6k | 27 ms | 1.0 ms | 39 ms | 2.102 mΩ |
| 0.1 mm | 34k | 0.18 s | 4.7 ms | 0.40 s | 2.092 mΩ |
| 0.05 mm | 135k | 0.88 s | 30 ms | 3.1 s | 2.083 mΩ |

- R converges to 0.5% at 0.1 mm; a 200-iteration run at 0.1 mm takes about 80 s. An adjoint costs 2–6% of a factorization.
- Smoothed-aggregation AMG (pyamg, MIT) needed a grid-independent 12–17 CG iterations from 33k to 524k unknowns (scratch benchmark), the route to O(n) GPU solves; in Python its setup made LU faster at these sizes [C].

### Export to KiCad zones

`kicad_zone()` writes the largest polygon as a zone S-expression (y flipped, about 230 vertices for the POC):

```
(zone (net 0) (net_name "+5V") (layer "F.Cu") (hatch edge 0.5)
  (connect_pads yes (clearance 0.2)) (min_thickness 0.25)
  (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5) (island_removal_mode 0))
  (polygon (pts (xy 100.3600 108.3983) (xy 100.3401 108.0019) ...)))
```

- Write it through the IPC API (zone create + refill), never by hand-editing fills ([file-format hazards](../kicad/file-format-and-version-hazards.md)).
- `connect_pads yes` (solid) suits power pads; hand-soldered or THT pads need relief (cost above).
- Set `min_thickness` ≤ the legalizer's w_min so KiCad's filler does not erode the shape again.
- Keep the synthesis recipe (terminals, currents, area or price, filter radius) as intent, so the zone can be re-synthesized after parts move ([OP55](../../ideas/physics-first/optimization.md)).

## Recommendations for our system

- **Ship one sheet solver with three coefficient maps and an adjoint.** DC, HF-inductive and thermal need no extra tools. Validate against padne (DC, GPL-3.0) and PEECN or FastHenry (plane-pair L; FastHenry licence caveat in [open-solvers](open-solvers.md)) ([solver-ladder](solver-ladder.md)) [I].
- **Use synthesis for power nets above about 3–5 A, sense and Kelvin paths, heat-spreading copper, and multi-rail plane partitions.** Below that, a width-∝-current tree ([OP29](../../ideas/physics-first/optimization.md)) is within noise of optimal [C/I].
- **Run the adjoint advisor on every layout,** human or agent-made: the cheapest physics feature with direct value (where copper buys mΩ, K or nH; where it is dead) [C].
- **Put fab rules in the optimizer.** Set the filter radius or robust thresholds from minimum width, then legalize by contour + close + open with a connectivity and physics re-check. Reject any legalization that breaks connectivity or moves a budget by more than its margin [C].
- **Evaluate pours while parts move.** A coarse 0.4–0.5 mm grid solves in about 10 ms, so the joint optimizer can carry copper-density and price fields per layer ([joint-place-route](joint-place-route.md), [OP56](../../ideas/physics-first/optimization.md)) [C/I].
- **Map h_eff from the stackup and reference-layer copper before any HF objective.** Cross-check the 2-D model with PEEC on the first boards ([power-copper](power-copper.md), [pdn-and-commutation](pdn-and-commutation.md)) [I].

## Conflicts and open questions

- **The parallel-plate inductive model is a proxy across slots.** It assumes the return drops to the next plane; real return current detours around the slot end, so L depends on slot length. Check with FastHenry or openEMS before trusting the slot magnitudes [I].
- **Is −14.5% worth the complexity?** It is larger against sloppy layouts and modest against an expert tree. The stronger case (multi-rail partitions, thermal coupling, HF return awareness) is not shown by this single-net DC POC [I].
- **Non-convexity.** Mixed objectives found local optima (L-only worse than 50/50). Production needs multi-start, continuation or QD over seeds [C].
- **Grey-cell physics.** SIMP's intermediate densities are not manufacturable copper. Results above are evaluated on thresholded designs only [C].
- **KiCad zone outlines are polygons.** Arc support in zone outlines was not verified for KiCad 10/11. Export segments at ≤0.01 mm deviation until it is [I].
- **No published PCB-pour topology optimization** beyond the IBM heuristic; commercial internals (Quilter, Cadence) are unknown [S].

## Sources

- Research notes: [constraints_verification_benchmarks.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md) (padne DC solver)
- Scripts: [op_topopt_pour.py](../../../tools/research/physics/op_topopt_pour.py) (all [C] numbers here), [op_placement_kernels.py](../../../tools/research/physics/op_placement_kernels.py)
- IBM power-plane shape patent US10546089B1: https://patents.google.com/patent/US10546089B1/en [P]
- OptiClear, arXiv 2607.03632: https://arxiv.org/abs/2607.03632 [P]
- Hammond, Oskooi, Johnson, Ralph, *Opt. Express* 29(15):23916, 2021: https://dspace.mit.edu/handle/1721.1/131097 [S]
- Qian & Sigmund, CMAME 253:237, 2013 (etching robustness): https://orbit.dtu.dk/en/publications/topological-design-of-electromechanical-actuators-with-robustness/ [S]
- Lazarov, Wang, Sigmund, "Length scale and manufacturability…", Arch. Appl. Mech. 86:189, 2016: https://backend.orbit.dtu.dk/ws/files/140201797/main.pdf [S]
- Zhou, Lazarov, Wang, Sigmund, CMAME 293:266, 2015: https://orbit.dtu.dk/en/publications/minimum-length-scale-in-topology-optimization-by-geometric-constr/ [S]
- Hassan, Wadbro, Berggren, IEEE TAP 62(5):2488, 2014: https://people.cs.umu.se/martinb/downloads/Papers/HaWaBe14a.pdf [S]
- Aage, Mortensen, Sigmund, IJNME 83(2):228, 2010: https://orbit.dtu.dk/en/publications/topology-optimization-of-metallic-devices-for-microwave-applicati/ [S]
- Karahan et al., *Nat. Commun.* 15:10734, 2024: https://www.nature.com/nature-index/article/10.1038/s41467-024-54178-1 [S]
- Busbars: https://bibliotheque.univ-catholille.fr/doc/OAI_1/oai-HAL-hal-01735587v1 ; https://opus.bibliothek.uni-augsburg.de/opus4/files/29666/29666.pdf ; https://www.ee.cit.tum.de/msa/forschung/leistungselektronik/busbar/ [S]
- Gupta et al., solar-cell metallization: https://research.tudelft.nl/en/publications/optimizing-front-metallization-patterns-efficiency-with-aesthetic [S]
- Volume-to-point SIMP vs constructal (Ikonen & Sobester): https://eprints.soton.ac.uk/422930/1/manuscript_ikonen_sobester.pdf [S]
- IC P/G sizing with SLP, EM-aware (Zhou et al., TVLSI 2018): https://par.nsf.gov/servlets/purl/10104322 [S]
- PowerSynth (licence: academic/non-commercial): https://e3da.csce.uark.edu/release/PowerSynth [S]
- Sigrity OptimizePI (vendor): https://pcdandf.com/pcdesign/index.php/editorial/menu-new-indust-prod/6096-sigrity-introduces-optimizepi-v-21-power-delivery-software [V]

See also: [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md) · [joint-place-route](joint-place-route.md) · [power-copper](power-copper.md) · [pdn-and-commutation](pdn-and-commutation.md) · [solver-ladder](solver-ladder.md) · [rules/power/high-current](../rules/power/high-current.md) · [rules/dfm-fab-limits](../rules/dfm-fab-limits.md) · [ideas: optimization](../../ideas/physics-first/optimization.md)
