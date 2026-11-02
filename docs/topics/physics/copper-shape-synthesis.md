# Copper shape synthesis: topology optimization for pours, planes and power copper

Scope: synthesizing pour/plane shapes by topology optimization (SIMP, level set, phase field, ESO), its DFM mapping, the 24×14 mm proof of concept and KiCad zone export. Not here: copper physics and cut pricing -> [power-copper](power-copper.md); loop/PDN physics -> [pdn-and-commutation](pdn-and-commutation.md); optimizer integration -> [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md); solvers -> [solver-ladder](solver-ladder.md).
Keys: topology optimization, SIMP, level set, phase field, ESO, BESO, density filter, Heaviside projection, robust erode/dilate, pour synthesis, R_loss, L_eff, f_c crossover, h_eff, adjoint advisor, legalization, kicad_zone, thermal relief spokes, op_topopt_pour.py, OP18, OP29, OP55, OP56, US10546089B1

**Results** [C] (all from [op_topopt_pour.py](../../../tools/research/physics/op_topopt_pour.py)):
- Area matters more than shape: a competent tree is on the 1-D optimum for its topology (width ∝ current); shape is worth ~15% at equal area (−14.5% in the POC), 18% over uniform widening at +25% area. Pays at ≳ 5 A, tight IR/thermal margins, or several rails competing for a layer; irrelevant for most low-current rails [C/I].
- Above f_c = R_s/(2π·μ0·h) (0.3–0.6 MHz for 1 oz over 0.1–0.2 mm, ~40 kHz on 2-layer 1.6 mm) pour current spreads by inductance. DC- and HF-optimal shapes coincide over a uniform plane, differ across a reference slot: slot-aware shape −10% L_eff for +9% R.
- Legalization is nearly free in R, but an opening wider than a drawn neck disconnected one design: minimum width must set the filter radius.
- No PCB-pour precedent except an expired IBM heuristic patent; nearest analogues: busbars, solar-cell metallization, volume-to-point heat conduction [S].

## One operator, three physics

Each is a 2-D (screened) Laplace problem on the sheet with a different coefficient.

| Physics | Sheet coefficient (per square) | Sources / sinks | Objective (self-adjoint) | Valid when |
|---|---|---|---|---|
| DC conduction | G = 1/R_s, R_s = ρ_Cu/t = 0.491 mΩ/□ at 1 oz | pad currents; regulator pad at 0 V | P = Σ I_k·V_k (= I²·R_loss) | f < f_c, t < 2δ |
| Inductive limit, pour over a plane at depth h_eff | 1/(μ0·h_eff); μ0·h = 0.126 nH/□ at 0.1 mm | same, as AC currents | L_eff = Σ I_k·Φ_k / I² | f ≫ f_c, w ≫ h, plane continuous or h_eff mapped |
| Heat spreading | k·t (copper + FR-4) + convection 2·h_c per area | dissipating parts | thermal compliance Σ P·T | steady state |

**Crossover** f_c = R_s/(2π·μ0·h), independent of width (R′ = R_s/w, L′ = μ0·h/w) [C]:

| Copper | h = 0.075 mm | 0.1 mm | 0.2 mm | 0.36 mm | 1.5 mm | 1.6 mm |
|---|---|---|---|---|---|---|
| 0.5 oz (17.5 µm) | 1.66 MHz | 1.2 MHz (1.25) | 622 kHz (0.62 MHz) | 346 kHz | 83 kHz | 78 kHz |
| 1 oz (35 µm) | 830 kHz | 622 kHz | 311 kHz | 173 kHz | 41 kHz | 39 kHz |
| 2 oz (70 µm) | 415 kHz | 311 kHz | 156 kHz | 86 kHz | 21 kHz | 19 kHz |

Same quantity as the return-band crossing f_x (band crosses ℓ = h; R_s = ρ_Cu/t); the 0.075 and 1.6 mm columns and bracketed values come from [research-gaps](research-gaps.md) gap 2 (numpy) [C].

- Converter ripple and edges (≥ 100 kHz) see the inductive problem; DC load current the resistive one. δ = 66 µm at 1 MHz, so 1 oz stays thickness-uniform to ~4 MHz [C].
- Analogy breaks for: narrow traces (w ≲ h, fringing); boards without a plane (need 3-D PEEC/FastHenry); above the plane-pair resonance (shunt C). Signal nets carry no loss objective and stay paths [I].

## Methods worth borrowing

| Method | Representation | PCB fit | Source |
|---|---|---|---|
| SIMP + density filter + Heaviside projection, OC or MMA | ρ ∈ [0,1], conductivity ∝ ρ^p | default: simple, adjoint-cheap; threshold grey cells | Bendsøe–Sigmund; top88 (Andreassen 2011); Svanberg 1987 (MMA) [S] |
| Robust erode/nominal/dilate | three projections of one field | etch tolerance (±20% width at JLCPCB), strict min width/space | Wang, Lazarov, Sigmund 2011; Qian & Sigmund 2013 [S] |
| Level set (SDF moved by shape derivative) | crisp boundary | polish after SIMP; arc-friendly outlines | Wang, Wang, Guo 2003; Allaire et al. 2004 [S] |
| Phase field (Allen–Cahn) | diffuse interface, multi-phase | several rails on one layer (sum-to-one per cell) | Takezawa et al. 2010 [S] |
| ESO/BESO (hard-kill by sensitivity) | binary cells | fast screening; within 5% of SIMP in our POC | Xie & Steven 1993; Huang & Xie 2007 [S] |
| Constructal / growth heuristics | trees grown from the sink | seeds, intuition | Bejan; Ikonen & Sobester [S] |
| IBM power-plane heuristic | equal-resistance blocks via a current "centre" | minimum copper under an IR limit; expired | [US10546089B1](https://patents.google.com/patent/US10546089B1/en) [P] |

Scale: topology optimization has run at 1.1 × 10⁹ voxels (Aage et al., *Nature* 2017) [S]; ours: 10⁴–10⁶ cells per layer.

## Prior art closest to PCB copper

| Domain | What was optimized | Result / note |
|---|---|---|
| Busbars | conductivity per element vs temperature; topology vs eddy loss, stray L | > 50% copper saved at a temperature limit (laminated busbar, HAL); "inductance" ill-defined for multi-contact bars (TUM, Augsburg) [S] |
| Solar-cell front metallization (Gupta et al., TU Delft) | grid resistive loss vs shading | nearest analogue of a pour; > 50% output gain on free-form cells; code [topsol](https://github.com/dkgupta90/topsol) [S] |
| Volume-to-point heat conduction | high-k inserts draining a heated area | SIMP and constructal trees, same Laplace structure [S] |
| Metallic antennas, microwave devices | conductivity per cell under Maxwell | Hassan et al., IEEE TAP 2014; Aage et al., IJNME 2010 [S] |
| mm-wave passives (Princeton) | pixelated multi-port EM, deep-learning inverse design | designs in minutes (Karahan et al., *Nat. Commun.* 15:10734, 2024) [S] |
| Silicon photonics | foundry rules inside topology optimization | width, space, area, enclosed area via differentiable morphology (Hammond et al. 2021) [S] |
| Photonic legalization | morphological, differentiable legalizers | violations "from thousands to zero" (OptiClear, [arXiv 2607.03632](https://arxiv.org/abs/2607.03632)) [P] |
| IC power grids | wire widths under IR and EM limits | sequence-of-LPs sizing (Tan, Shi); EM- and lifetime-aware SLP (TVLSI 2018) [S] |
| Power modules | die placement, traces vs parasitic L and temperature | PowerSynth (Arkansas): **academic/non-commercial licence, reference only** [S] |

No open tool synthesizes PCB pours from physics. Altium PDN Analyzer and Sigrity analyze copper; Sigrity OptimizePI searches decap sets; plane shapes stay manual [S/V].

## Manufacturing constraints mapped to PCB DFM

Put fab rules inside the optimizer, not only after it: filter radius / robust thresholds from minimum width, then legalize by contour + close + open with connectivity and physics re-check; reject a legalization that breaks connectivity or moves a budget by more than its margin [C].

| Topology-optimization device | PCB rule | KiCad mechanism | Note |
|---|---|---|---|
| Density-filter radius r_min | min width/space (0.10–0.15 mm signal; ≥ 0.25–0.5 mm sensible for power) | `track_width`, zone `min_thickness` | nominal-only SIMP has no strict length scale; robust or geometric constraints (Zhou et al. 2015) guarantee one [S] |
| Robust erode/dilate (η_e, η_d) | etch tolerance | none (fab) | η from the fab's ±20% width tolerance [I] |
| Morphological opening by w_min | sliver, neck removal | zone fill removes sub-`min_thickness` copper | KiCad's filler is a last-resort opening, not a design method |
| Closing by gap_min | acid traps, narrow notches, slots | `clearance` | close before open so notches do not survive |
| Curvature limit (level set, arc fit) | acute-angle avoidance | none | physics prefers rounded inside corners (current crowding) |
| Connectivity / no islands | floating copper removal | `island_removal_mode` | check source → every load, not only "touches a pad" |
| Passive solid / void cells | pads, keep-outs, holes, antenna regions | rule areas, keep-out zones | fixed before filtering |
| Per-cell area price | soft keep-out, routing corridor | none | our "price" variant |
| Thermal relief | solderability vs resistance | `thermal_gap`, `thermal_bridge_width`, `connect_pads` | 2×2 mm pad: 4 spokes +0.22 mΩ, 2 spokes +0.52 mΩ [C] |
| Copper-density band | plating balance, warp | none | region constraint ([OP18](../../ideas/physics-first/optimization.md)) |

## Proof of concept

**Setup** ([op_topopt_pour.py](../../../tools/research/physics/op_topopt_pour.py); numpy/scipy/shapely/contourpy; deterministic):
- 24×14 mm, single layer, 1 oz. Source pad 3×3 mm at left, 0 V. Loads A 3 A (bottom right), B 2 A (top right), C 1 A (top middle). 2 mm-radius mounting-hole keep-out on the axis.
- Q4 elements at 0.1 mm (34k nodes); SIMP p = 3, contrast 10⁻⁶; linear-hat filter r = 0.5 mm; Heaviside β 1 → 32 (doubling); OC update; 200 iterations.
- Baseline: trunk 4 mm (6 A), branches 2 mm (3 A) and 1.5 mm (2 A), 45° bends (~0.67 mm/A, generous by IPC-2221).

**Results** [C]

| Layout | Copper area | R_loss = P/I² | Drop A / B / C | Loss at 6 A |
|---|---|---|---|---|
| Trunk and branches (human-style) | 104.9 mm² | 2.092 mΩ | 13.9 / 13.2 / 7.1 mV | 75 mW |
| Topology-optimized, same area | 104.7 mm² | **1.789 mΩ** (−14.5%) | 11.8 / 11.5 / 6.1 mV | 64 mW |
| Same, legalized (w, gap ≥ 0.5 mm) | 104.8 mm² | 1.790 mΩ | — | — |
| Greedy energy-ranked removal from full pour (14 solves) | 104.9 mm² | 1.882 mΩ | — | — |
| Full pour | 323.4 mm² | 0.677 mΩ | 4.5 / 4.2 / 2.5 mV | 24 mW |

Optimized shape at equal area ('#' copper, 'o' keep-out; source left, A bottom right, B top right, C top middle):

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

- Two straight tapered limbs split at the source around the hole; upper absorbs C and continues to B, lower runs straight to A.
- Every pad entry flares; no constant-width runs, no 45° doglegs.
- Grey measure 0.6%, minimum feature 1.5 mm: DC favours thick members, so min-width rules rarely bind at this area.

**Area sweep** (DC; area includes 34.5 mm² of pads) [C]: the last 30% of area buys 15%.

| Area | 20% (63 mm²) | 30% (96 mm²) | 50% (161 mm²) | 70% (226 mm²) | 100% |
|---|---|---|---|---|---|
| R_loss / full pour | 6.2× | 3.0× | 1.6× | 1.17× | 1 |

**Routing-corridor price** [C]: copper in a 2 mm vertical corridor costs 4× area; corridor copper 8.0 → 4.0 mm², R 2.221 mΩ (+24%), partly from the smaller physical area.

**Reference slot** [C]: 1×6.5 mm slot in L2 (h_eff 0.1 → 1.5 mm) in the path to A; 100 iterations.

| Objective | R_loss | L_eff | Copper over slot |
|---|---|---|---|
| DC only | 1.821 mΩ | 0.659 nH | 2.3 mm² |
| 50/50 DC + L | 1.979 mΩ | **0.592 nH** | 2.5 mm² (wider, shorter crossing) |
| L only | 2.359 mΩ | 0.604 nH | 0 (routes around the slot end) |
| Human trunk and branches | 2.092 mΩ | 0.755 nH | — |

L-only worse than 50/50 = local optimum; non-convex mixes need multi-start, continuation or QD over seeds.

**Adjoint "where to add copper"** on the human layout [C]:
- Adjoint vs central-difference gradient of the drop at A: agree to 3.5 × 10⁻⁷.
- +26 mm² (+25%) at boundary cells ranked by energy density → 1.531 mΩ; uniform widening → 1.666 mΩ; re-optimized at that area → 1.370 mΩ.
- Removing the 20% least-loaded copper: R +21% (little dead copper).
- Run this adjoint advisor on every layout, human or agent: where copper buys mΩ, K or nH, and where it is dead [C].

**Legalization stress test** (area = pads + 15% of free area, 77 mm²) [C]:

| Filter radius | Raw R_loss, min feature | Legalized at 0.5 mm | Legalized at 1.0 mm |
|---|---|---|---|
| 0.2 mm | 2.843 mΩ, 0.70 mm neck | 2.921 mΩ (+2.8%) | **disconnected** (C/B limb cut) |
| 1.0 mm | 2.952 mΩ, 0.9 mm | — | 2.946 mΩ (−0.2%) |

Min width in the filter costs 3.8% up front; legalization is then free and cannot cut the net.

**Runtime** (CPU, one core, loaded shared VM, ±20% run to run; `--timing`) [C]:

| Grid | Nodes | Assemble + LU + solve | Adjoint back-substitution | Optimization iteration | Human-layout R |
|---|---|---|---|---|---|
| 0.4 mm | 2.2k | 9 ms | 0.3 ms | 9 ms | 2.170 mΩ |
| 0.2 mm | 8.6k | 27 ms | 1.0 ms | 39 ms | 2.102 mΩ |
| 0.1 mm | 34k | 0.18 s | 4.7 ms | 0.40 s | 2.092 mΩ |
| 0.05 mm | 135k | 0.88 s | 30 ms | 3.1 s | 2.083 mΩ |

- R converges to 0.5% at 0.1 mm; 200 iterations at 0.1 mm ≈ 80 s; an adjoint costs 2–6% of a factorization.
- A 0.4–0.5 mm grid solves in ~10 ms, so the joint optimizer can carry per-layer copper-density and price fields while parts move ([joint-place-route](joint-place-route.md), [OP56](../../ideas/physics-first/optimization.md)) [C/I].
- Smoothed-aggregation AMG (pyamg, MIT): grid-independent 12–17 CG iterations from 33k to 524k unknowns (scratch benchmark), the route to O(n) GPU solves; in Python its setup made LU faster at these sizes [C].

## Where synthesis pays

- Use synthesis for power nets above ~3–5 A, sense and Kelvin paths, heat-spreading copper, multi-rail plane partitions; below that a width-∝-current tree ([OP29](../../ideas/physics-first/optimization.md)) is within noise of optimal [C/I].
- One sheet solver with three coefficient maps and an adjoint covers DC, HF-inductive and thermal; validate against padne (DC, GPL-3.0) and PEECN or FastHenry (plane-pair L; licence caveat in [open-solvers](open-solvers.md)) [I].
- Map h_eff from stackup and reference-layer copper before any HF objective; cross-check the 2-D model with PEEC on first boards ([power-copper](power-copper.md)) [I].

## Export to KiCad zones

`kicad_zone()` writes the largest polygon as a zone S-expression (y flipped, ~230 vertices for the POC):

```
(zone (net 0) (net_name "+5V") (layer "F.Cu") (hatch edge 0.5)
  (connect_pads yes (clearance 0.2)) (min_thickness 0.25)
  (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5) (island_removal_mode 0))
  (polygon (pts (xy 100.3600 108.3983) (xy 100.3401 108.0019) ...)))
```

- Write through the IPC API (zone create + refill), never by hand-editing fills ([file-format hazards](../kicad/file-format-and-version-hazards.md)).
- `connect_pads yes` (solid) suits power pads; hand-soldered or THT pads need relief (cost above).
- `min_thickness` ≤ legalizer w_min, so KiCad's filler does not erode the shape again.
- Keep the synthesis recipe (terminals, currents, area or price, filter radius) as intent, to re-synthesize after parts move ([OP55](../../ideas/physics-first/optimization.md)).

## Open questions

- Parallel-plate inductive model is a proxy across slots: it drops the return to the next plane, while real return current detours around the slot end (L depends on slot length). Check slot magnitudes with FastHenry or openEMS [I].
- Is −14.5% worth the complexity? Larger against sloppy layouts, modest against an expert tree; the stronger case (multi-rail partitions, thermal coupling, HF return awareness) is not shown by this single-net DC POC [I].
- Grey cells are not manufacturable; all results above are on thresholded designs [C].
- Arc support in KiCad 10/11 zone outlines not verified; export segments at ≤ 0.01 mm deviation [I].
- No published PCB-pour topology optimization beyond the IBM heuristic; Quilter and Cadence internals unknown [S].

## Sources

- Research note: [constraints_verification_benchmarks.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md) (padne DC solver).
- Scripts: [op_topopt_pour.py](../../../tools/research/physics/op_topopt_pour.py) (all [C] here), [op_placement_kernels.py](../../../tools/research/physics/op_placement_kernels.py).
- IBM US10546089B1: https://patents.google.com/patent/US10546089B1/en [P]
- OptiClear, arXiv 2607.03632: https://arxiv.org/abs/2607.03632 [P]
- Hammond, Oskooi, Johnson, Ralph, *Opt. Express* 29(15):23916, 2021: https://dspace.mit.edu/handle/1721.1/131097 [S]
- Qian & Sigmund, CMAME 253:237, 2013: https://orbit.dtu.dk/en/publications/topological-design-of-electromechanical-actuators-with-robustness/ [S]
- Lazarov, Wang, Sigmund, Arch. Appl. Mech. 86:189, 2016: https://backend.orbit.dtu.dk/ws/files/140201797/main.pdf [S]
- Zhou, Lazarov, Wang, Sigmund, CMAME 293:266, 2015: https://orbit.dtu.dk/en/publications/minimum-length-scale-in-topology-optimization-by-geometric-constr/ [S]
- Hassan, Wadbro, Berggren, IEEE TAP 62(5):2488, 2014: https://people.cs.umu.se/martinb/downloads/Papers/HaWaBe14a.pdf [S]
- Aage, Mortensen, Sigmund, IJNME 83(2):228, 2010: https://orbit.dtu.dk/en/publications/topology-optimization-of-metallic-devices-for-microwave-applicati/ [S]
- Karahan et al., *Nat. Commun.* 15:10734, 2024: https://www.nature.com/nature-index/article/10.1038/s41467-024-54178-1 [S]
- Busbars: https://bibliotheque.univ-catholille.fr/doc/OAI_1/oai-HAL-hal-01735587v1 ; https://opus.bibliothek.uni-augsburg.de/opus4/files/29666/29666.pdf ; https://www.ee.cit.tum.de/msa/forschung/leistungselektronik/busbar/ [S]
- Gupta et al.: https://research.tudelft.nl/en/publications/optimizing-front-metallization-patterns-efficiency-with-aesthetic [S]
- Ikonen & Sobester: https://eprints.soton.ac.uk/422930/1/manuscript_ikonen_sobester.pdf [S]
- Zhou et al., TVLSI 2018: https://par.nsf.gov/servlets/purl/10104322 [S]
- PowerSynth: https://e3da.csce.uark.edu/release/PowerSynth [S]
- Sigrity OptimizePI: https://pcdandf.com/pcdesign/index.php/editorial/menu-new-indust-prod/6096-sigrity-introduces-optimizepi-v-21-power-delivery-software [V]
- Related: [rules/power/high-current](../rules/power/high-current.md), [rules/dfm-fab-limits](../rules/dfm-fab-limits.md), [ideas: optimization](../../ideas/physics-first/optimization.md).
