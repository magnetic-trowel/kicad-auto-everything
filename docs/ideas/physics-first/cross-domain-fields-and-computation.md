# Cross-domain ideas: structures, practice, fields, geometry and computation (XD59–XD125)

Scope: XD59–XD125, transplants from structures and mechanics, harness/aerospace/automotive/audio practice, cavities and acoustics, quantum chips, biology, graphics, game physics and robotics, multiscale modelling, city planning, electrochemistry. Not here: XD1–XD58 (coils, power modules, IC grids, inverse design, flow networks), the XD top 10 and non-transferring analogies -> [cross-domain](cross-domain.md); worked analogies and their numbers -> [cross-domain-lessons](../../topics/physics/cross-domain-lessons.md) (authoritative where it overlaps).
Keys: XD59–XD125, shear lag, current crowding at holes, Michell texture, multi-load-case copper, Steinberg, warpage, neutral-axis flex, separation tables, multipole buffer, magic angle 54.7°, pin-1 problem, protection zones, bond impedance, shim loops, bass traps, EBG, wire-mesh shield, Maekawa, airbridge stitching, energy participation ratio EPR, box modes, Windkessel, myelin, reticulate pours, SDF, medial axis, clothoid, elastic rods, Poisson-disk stitching, centroidal Voronoi, geodesic creepage, XPBD, CHOMP, Dubins, homogenization, data assimilation, screening length λ, ePlace kernels, decap reach, fin length, road hierarchy, Rayleigh monotonicity, Wagner number, multi-tab feeding

Entry format, tags, effort and [C] scripts: [cross-domain](cross-domain.md).

## F. Structures: topology optimization, mechanics, additive manufacturing

- **XD59** Shear lag for every overlapping joint (sharp, S): XD22 math for wide-terminal joints, bolted lugs, overlapping pours on adjacent layers, thermal vias under distributed sources; overlap beyond ~2–3 L_T adds almost nothing. T: FD sweep of overlap length.
- **XD60** Stress-concentration charts as current-crowding charts (new, S): current around an insulating hole is potential flow: round hole J_max = 2·J0, ellipse (semi-axis a across, b along flow) J_max = J0·(1 + a/b) [I, standard results]; Peterson-style charts → closed-form hot-spot checks at holes, antipads, slots. T: FD vs formula, 10 hole shapes.
- **XD61** Align copper texture with current (Michell analogy) (combo, S): hatch, slots, via rows, thermal-relief spokes along ψ contours cost nothing electrically. T: XD2 cost of hatch at 0°/45°/90° to flow.
- **XD62** Multi-load-case copper (combo, S–M): optimize copper over operating modes (light, full, transient, fault, standby), weighted or worst-case. T: worst-case drop vs single-case design.
- **XD63** Steinberg displacement limits for placement (sharp, S–M): Steinberg board-deflection limits by part size and position [S]; a plate modal model places large/brittle/heavy parts (MLCCs, BGAs, crystals, transformers) at low curvature, MLCCs along low-strain axes. T: plate FE on 5 boards with their mounting holes.
- **XD64** Warpage from copper imbalance (sharp, S): laminate theory predicts bow/twist from per-layer copper-density asymmetry about the mid-plane; warpage critic, balance pours. T: predicted vs fab-reported bow.
- **XD65** Neutral-axis flex routing (sharp, S): strain = y/R; flex traces at the neutral axis, perpendicular to the bend, staggered across layers, computed from bend radius (known practice). T: strain estimate vs IPC-2223.
- **XD66** Manufacturing filters double as DFM (sharp, S): AM overhang/min-feature filters ↔ PCB slivers, min area, min annular ring, run on optimized copper; acid traps mostly legacy with modern etching, keep soft.

## G. Harness, aerospace, automotive, audio and instrumentation practice

- **XD67** Separation tables derived from coupling (sharp, S): per aggressor–victim pair from a coupling kernel and dB budget, not fixed mm; [I] crosstalk over a plane ∝ 1/(1+(d/h)²). T: derived vs fixed tables, 10 boards.
- **XD68** Buffer distance from multipole order (new, S): aggressor order sets decay (acoustics: point 6 dB, line 3 dB per doubling): parallel lines over a plane 1/(d/h)², −12 dB/doubling; free dipole loop 1/r³, −18 dB/doubling; flat loops over a plane h²/r⁵, −30 dB/doubling; image-plane dB numbers: [L6](../../topics/physics/cross-domain-lessons.md#l6-multipoles-and-image-planes-nmr-rfic-mri-shielding--orientation-mirrored-loops) [C]. Buffer distance from order + budget. T: Neumann vs openEMS, 4 geometries.
- **XD69** Ground-tap ordering on a shared return (sharp, S): audio practice (Self) [S]: most sensitive reference nearest the star, largest currents join last; solve as an assignment minimizing Σ(current × shared impedance × victim sensitivity). T: SPICE harmonic distortion, best vs worst order, class-AB layout.
- **XD70** Pin-1 rule as a stream check (sharp, S): the pin-1 problem = shield current into circuit ground inside the box (Muncy, JAES 1995) [S]; check that no chassis/shield streamline crosses the analog ground region. T: seeded violations, 5 audio boards.
- **XD71** Orient magnetics by dipole algebra (new, S): coupling ∝ m1·m2 − 3(m1·r̂)(m2·r̂). [C] two in-plane-axis dipoles at 20 mm: M = 3.75 pH at 0°, 0.0003 pH at 54.7° (NMR magic angle), −2.0 pH at 90°; a flat victim beside an in-plane-axis aggressor at the same height couples only via the plane image. Orientation from the formula, not "rotate 90°". T: near-field, drum-core inductor vs sense loop at 5 angles.
- **XD72** Current-free sense paths (Kelvin generalized) (sharp, S): every voltage that matters (feedback, shunt sense, reference, ADC ground) has a sense path with no load current; a DC solve verifies |J| ≈ 0 under load. T: seeded violations.
- **XD73** Lightning protection zones → board protection zones (sharp, S): IEC 62305 nested zones [S]; draw board zones (connector, filtered, quiet core), check that every crossing conductor passes a filter or bond at the boundary. T: ESD/surge paths, 10 interface boards.
- **XD74** Bond-impedance budgets (sharp, S): aerospace bond resistance (2.5 mΩ class R bond, MIL-B-5087 practice) [S] → board-to-chassis bonds (screws, standoffs, spring fingers, stitched vias) get a nH budget at the frequency of concern from geometry. T: PEEC of 3 mounting-hole styles.
- **XD75** Ground-offset budgets between blocks (sharp, S): automotive ground-offset tolerances → DC and AC mV budgets per interconnected block pair, checked by the copper solve. T: offsets on 5 mixed-signal boards.
- **XD76** Twisted and gradiometric sense traces (sharp, S): low-level differential sense near magnetics with layer swaps every segment or figure-8 loops; pickup falls to the residual imbalance. T: Neumann M inductor → straight vs twisted pair.
- **XD77** Shim loops (NMR shimming analogy) (new, S–M): after layout add a small compensating loop on a sense path, sized/oriented to cancel the computed residual M from a nearby aggressor. T: residual M before/after; near-field verify.

## H. Cavities, metamaterials and acoustics

- **XD78** Damp cavity modes at corners and edges, like bass traps (sharp, S): plane-pair voltage antinodes sit at open edges/corners; place lossy damping (RC edge terminations, lossy-ESR caps) there, weighted by modal participation; known PDN practice ([decoupling-pdn](../../topics/rules/decoupling-pdn.md)), the transplant adds computed placement. T: cavity Q with/without corner damping.
- **XD79** EBG only for islands (sharp, M): planar EBG gives wide stop bands [S] but perforates the return, hurts SI, can radiate [S]; use only to isolate a noisy island (PA, clock) from a sensitive one with no fast signal crossing. T: isolation vs eye opening, shared-plane test board.
- **XD80** Hatched planes by wire-mesh shield theory (sharp, S): hatch/mesh plane (flex, rigid-flex) as a wire-mesh screen with effective sheet and transfer impedance; predicts Z0 ripple and return L from pitch and fill. T: 2-D field solve, microstrip over hatch.
- **XD81** Tuned resonant absorbers (sharp, S–M): Helmholtz absorber → lossy stub or series RC tuned to one cavity/enclosure mode at its antinode. T: S21 between two cavity ports.
- **XD82** Finite guard edges and diffraction (new, S): Maekawa end leakage; score finite guard traces/via fences by the aggressor field reaching the victim around the ends. T: 2-D/3-D solve, guard length vs isolation.

## I. Superconducting quantum chip layout

→ [L11](../../topics/physics/cross-domain-lessons.md#l11-superconducting-quantum-layout--stitching-participation-box-modes)

- **XD83** Stitching spacing from slot-mode resonance (airbridge rule) (sharp, S): airbridge spacing < λ/4 pushes slotline resonances above band (Chen et al. 2014; strong-coupling waveguide work) [S]; apply to CPWG stitching and pour fragments flanking any slot or trace, spacing from slot resonance vs aggressor spectrum, not λ/20. T: slot-mode S21, 3 spacings.
- **XD84** Energy participation ratio as a layout metric (new, M): EPR = fraction of mode energy in an element/region from one eigenmode solve (Minev et al., npj QI 2021) [S]; participation in solder mask/FR-4 (loss), a neighbour region (coupling), near a lid (detuning) ranks sensitivity. T: EPR vs measured insertion loss, 3 trace variants.
- **XD85** Box modes early (sharp, S): compute TE_mn0 modes of shield cans/enclosures before layout (can and box values: L11 [C]); keep strong harmonics off them or add absorber/partitions. T: harmonic table vs can modes, 5 RF boards.
- **XD86** Crossovers keep the ground continuous (sharp, S): a 0 Ω jumper or bottom-layer crossover for a fast net needs a parallel ground bridge (stitching vias both sides); check return continuity. T: R2 shadow-return check on 0 Ω jumpers.
- **XD87** Component-plus-analysis architecture (combo, M): Qiskit Metal (Apache-2.0 [S]), KQCircuits (GPL-3.0 [S]) attach analyses (EPR, lumped oscillator) to parametric components; build PCB primitives (hot-loop cell, busbar, via cage) as geometry + analysis hook. T: three primitives with analyses.

## J. Biology

- **XD88** Windkessel hierarchy → damped PDN hierarchy (sharp, S): controlled ESR (or a resistive link) at the bulk-to-local transition flattens anti-resonances, instead of more caps. T: impedance profile with/without controlled-ESR parts.
- **XD89** Neurovascular co-routing (new framing, S): separate nets only where a coupling mechanism exists (dI/dt, dV/dt, shared impedance, thermal); slow DC control may share a corridor with a DC trunk, not a switch node. T: share of separation rules on 10 boards not backed by a computed mechanism.
- **XD90** Myelin and nodes of Ranvier (sharp, S): low-Dk routing + repeaters; place retimers/redrivers at budgeted loss intervals, not mid-way by habit. T: per-segment channel loss budget.
- **XD91** Wiring economy as a benchmark (combo, S): C. elegans ganglia minimize wire (Cherniak 1994) [S]; count random block permutations of a good human layout that beat it on physics cost (does our cost agree with good practice?). T: 10 boards, 10⁴ permutations each.
- **XD92** Reticulate pours (combo, M): trunk + fine loop mesh for very large high-current pours that must survive voids/cracks (with N-1, XD50). T: worst drop after random void injection, trunk vs trunk + mesh.
- **XD93** Developmental pruning (combo, S): Hu–Cai pruning [S]: remove low-|J| copper only when another net needs the room, give it back after. T: freed area vs loss increase (greedy trim in [power-copper](../../topics/physics/power-copper.md#3-trace-vs-pour-vs-plane)).

## K. Computer graphics and computational geometry

- **XD94** SDF clearance and physics on GPU (sharp, S–M): per-net signed distance fields give exact clearance, push-apart gradients, distance coupling kernels in one texture. T: speed/accuracy vs polygon DRC, 5 boards.
- **XD95** Medial-axis neck finder (new, S): medial-axis radius = local pour width; its minimum along each high-|J| path (from ψ) = bottleneck; flag by current/width. T: neck flags vs FD hot spots.
- **XD96** Arcs over clothoids (sharp, S): an arc's offset is an arc (line-arc G1 keeps pair spacing/clearance exact), a clothoid's is not; G2 matters for aesthetics and mm-wave, not below several GHz; sharp-corner squares at DC: [L12](../../topics/physics/cross-domain-lessons.md#l12-graphics-and-robotics-geometry--beautiful-exact-curves) [C]. T: pair-spacing error, offset clothoids vs arcs.
- **XD97** Discrete elastic rods for trace relaxation (combo, M): Kirchhoff rods (Bergou et al. 2008) [S] with tension (length), bending stiffness (curvature), SDF repulsion + physics penalties; "rubber band with stiffness" router post-pass. T: aesthetic judge and DRC, relaxed vs raw.
- **XD98** Streamline-aligned direction fields (combo, M): cross fields (Instant Meshes) seeded from current streamlines in power regions and signal flow elsewhere as preferred routing directions. T: via and crossing count vs no field.
- **XD99** Blue-noise stitching vias (new, S): maximal Poisson-disk sampling guarantees min spacing (DRC) and max empty circle (leakage/resonance metric) around arbitrary obstacles; replaces grids that break at obstacles. T: largest empty circle and via count vs grid.
- **XD100** Weighted centroidal Voronoi allocation (combo, S): Lloyd relaxation weighted by load-current density spaces decaps/return vias for equal current per cell; cells capped at the screening length (XD112). T: worst-pin impedance vs uniform spacing.
- **XD101** Geodesic creepage (sharp, S): creepage = surface geodesic around slots/edges, exact by the heat method (Crane et al. 2013) [S] or fast marching on a 2-D mesh. T: vs hand measurement, 10 HV boards.
- **XD102** Differentiable copper rasterization (new, M): a soft rasterizer maps polygon vertices → density grid, so physics gradients reach CAD polygons. T: gradient check; convergence vs SIMP-then-polygonize.
- **XD103** Contour-styled outlines (new, S): where a pour edge has no physics cost (low |J|, slow node), snap it to smoothed equipotential or stream contours; looks designed, shows current flow, zero physics cost. T: VLM aesthetic preference.

## L. Game physics and robotics

- **XD104** XPBD interactive placement (sharp, M): extended position-based dynamics (Macklin et al. 2016) [S] with clearance (inequality), max hot-loop length (distance), symmetry, alignment constraints, stiffness from budget slack; drag-and-feel for U1. T: frame rate and violations during drag, 200-part board.
- **XD105** CHOMP/TrajOpt trace shaping (combo, M): CHOMP trajectory functional (SDF obstacle + smoothness), TrajOpt hard constraints by SQP [S]; coupling, reference-gap, clearance and curvature costs on critical traces after topology is fixed. T: coupling and length vs router output.
- **XD106** Dubins primitives for minimum bend radius (sharp, S): closed-form shortest curvature-bounded arc-line paths for flex, RF, HV traces. T: router integration, 3 flex boards.
- **XD107** Broad-phase coupling search (sharp, S): BVH/spatial hashing finds aggressor–victim pairs within a coupling radius from kernel + dB budget, O(n log n). T: pairs found vs brute force.

## M. Multiscale modelling, sparse fields, inverse problems (weather, climate, geophysics)

Screening lengths, kernels and [C] values: [L4](../../topics/physics/cross-domain-lessons.md#l4-screening-lengths-debye-fin-theory--decap-reach-thermal-reach-physical-placement-kernels).

- **XD108** Subgrid homogenization of perforated planes (sharp, S): BGA via fields / antipad "Swiss cheese" as an anisotropic effective sheet-conductance tensor per pattern for coarse board solves ([power-copper](../../topics/physics/power-copper.md#3-trace-vs-pour-vs-plane) computes the scalar case). T: homogenized vs fine solve.
- **XD109** Nested grids (sharp, M): coarse board solve, fine local solves (hot loop, BGA escape) on its boundary values, two-way feedback. T: error vs fully fine solve at 10× less cost.
- **XD110** Tolerance ensembles (sharp, M): run each physics check over fab/material/part variation ensembles (Dk, etch, ESL, ESR, registration) and report the spread; robust layouts minimize the worst member. T: how often the nominal pass fails in the ensemble.
- **XD111** Data assimilation for model calibration (combo, M): 4D-Var-style adjoint fit of stackup Dk, roughness, via ESL, h coefficients to TDR, VNA, thermal-camera data of built boards, fed back as priors. T: prediction error before/after on a second board.
- **XD112** Physical screening kernels in an ePlace-style placer (new, M): ePlace (Lu et al., TODAES 2015) [S] density-as-charge Poisson by FFT → real FFT-convolvable kernels: thermal K0(r/λ_th), PDN decap reach K0(r/λ_pdn), magnetic dipole 1/r³ or h²/r⁵ over a plane, crosstalk 1/(1+(d/h)²) (λ ranges: L4). T: physics-budget violations vs HPWL + density placer, 10 boards.
- **XD113** Decap reach set by a screening length (new, S): λ = sqrt(L_c/(μ0·d·n)) while decaps are inductive, share within R = 1 − x·K1(x), x = R/λ (L4); [C] d = 0.2 mm, 10 mm pitch: λ = 16.7 mm. "Within λ/2" replaces "as close as possible"; location matters in thick cavities. T: extend [xd_lengths.py](../../../tools/research/physics/xd_lengths.py) with plane capacitance, compare with a PDN tool.
- **XD114** Thermal fin length as a pour-size rule (sharp, S): λ_th = sqrt(Σk·t/h) bounds useful pour radius (2- and 4-layer values: L4 [C]); bigger pours buy little, and parts closer than ~λ heat each other. T: thermal FV ([thermal-physics](../../topics/physics/thermal-physics.md#the-board-as-a-fin)) vs formula.
- **XD115** Compressed-sensing near-field scans (new, M): reconstruct board H-field from few probe points by sparsity in a dipole basis; cheap model validation on built boards. T: reconstruction error vs dense scan.
- **XD116** Near-to-far-field transformation (sharp, S–M): transform board currents' near field to far field for early 3 m emission estimates. T: vs openEMS far field.
- **XD117** Thermal-image source inversion (combo, M): inverse heat conduction recovers sources from an IR image; check the predicted dissipation map vs the built board. T: one board, known loads.
- **XD118** Resistivity tomography for copper defects (new, M): ERT-style 4-wire test-point voltages detect plating voids and cracked necks in power copper. T: seeded-void boards.
- **XD119** Implicit neural fields for copper and potential (new, L): SIREN-style resolution-free differentiable copper and field functions for multiscale optimization. T: accuracy/speed vs grids at equal parameters.

## N. City and transport planning

- **XD120** Road hierarchy for current (combo, S): arterials/collectors/local streets = inner planes and wide pours / branches / twigs; forbid through traffic (large return crossing a quiet zone), divert by calming (slots along streamlines, XD3). T: ψ check of large returns crossing quiet zones.
- **XD121** Zones defined by current loops, not net names (sewer separation) (new framing, S): a zone is quiet iff no noisy current's streamline (at the relevant frequency) crosses it, whatever net names say; replaces split-ground folklore with a check. T: ψ zone audit, 10 mixed-signal boards.
- **XD122** Pour-everything only where Rayleigh allows (new framing, S): added copper never raises DC R, so fill is free on quiet nets; switch-node area = capacitance + antenna (19 pF case: [L2](../../topics/physics/cross-domain-lessons.md#l2-murray-kelvin-branched-transport--widths-and-topology-of-power-trees) [C]). Maximize copper on low-dV/dt nets (VIN, GND, VOUT), minimize on high-dV/dt nodes. T: switch-node area vs conducted/radiated emissions in simulation.

## O. Electrochemistry, batteries, solar

- **XD123** Plating thickness from the primary current distribution (sharp, S–M): bath Laplace (Wagner number) plates isolated outer features thicker; predict thickness from local copper density, correct outer-layer impedance and capacity, place thieving to even it. T: fab cross-sections.
- **XD124** Multi-tab feeding (sharp, S): feed large pours from several edge entries placed to minimize peak |J| and IR drop. T: FD, 30 A pour, 1 vs 3 entries.
- **XD125** Solar-grid finger optimization for shared layers (combo, S): finger pitch/width of comb collectors priced by routing-space opportunity cost (XD56), like shading vs loss. T: loss vs freed routing area.
