# Cross-domain ideas for physics-first layout (XD1–XD58)

Scope: XD1–XD58, transplants from coils, power modules, IC grids, inverse design, flow networks; XD top 10; analogies that do not transfer. Not here: XD59–XD125 (structures, practice, cavities, quantum chips, biology, graphics, robotics, multiscale, planning, electrochemistry) -> [cross-domain-fields-and-computation](cross-domain-fields-and-computation.md); search/LLM-workflow transplants -> [cross-domain-transplants](../cross-domain-transplants.md), [routing transplants](../../topics/routing/cross-domain-routing-transplants.md), [packing transplants](../../topics/placement/packing-and-graph-drawing-transplants.md), [scene transplants](../../topics/placement/scene-layout-transplants.md); worked analogies and their numbers -> [cross-domain-lessons](../../topics/physics/cross-domain-lessons.md) (authoritative where it overlaps).
Keys: XD1–XD58, stream function ψ, Δψ² slit law, transfer length L_T, shear lag, Murray/Kelvin width exponent, γ rule, Tichelmann reverse return, N-1, PTDF/LODF, I²t, step voltage, Physarum, constructal, laminated busbar, commutation cell, Rayleigh monotonicity

Entry format: `**id** name (tag, effort): mechanism; result; T: test`. Tags **new** (no PCB use found), **combo** (new combination), **sharp** (made buildable or quantitative); effort S days, M weeks, L months; evidence tags: [CONVENTIONS](../../CONVENTIONS.md#evidence-tags-and-links).
[C] numbers (deterministic, < 1 min each): [xd_sheet.py](../../../tools/research/physics/xd_sheet.py) (FD copper sheets: corners, pours, slots, via fields), [xd_power_tree.py](../../../tools/research/physics/xd_power_tree.py) (width exponents, star vs trunk, reverse return), [xd_lengths.py](../../../tools/research/physics/xd_lengths.py) (thermal/PDN screening lengths, paralleled layers, I²t, step voltage), [xd_loop_coupling.py](../../../tools/research/physics/xd_loop_coupling.py) (Neumann M with plane images). Defaults: 1 oz (35 µm, R_s = 0.49 mΩ/sq), DC.

## A. Coil design by stream functions (MRI gradient coils, stellarator coils, magnetometry)

Sheet current J = ∇ψ × n; ψ contours are streamlines and become conductors. Math, slit table and validity regime: [lessons L1](../../topics/physics/cross-domain-lessons.md#l1-coil-design-by-stream-functions--pours-slots-planar-coils).

- **XD1** Stream-function pour designer (new, M): on a triangle mesh of the allowed region, solve ψ minimizing loss + frequency-weighted magnetic energy s.t. terminal currents and keep-outs (bfieldtools operators, BSD-3 [P]); copper where |∇ψ| > threshold, outlines along ψ contours. T: 5 converter boards, DC loss + PEEC loop L vs existing pours at equal area.
- **XD2** Slot damage = Δψ² check (new, S): one ψ solve prices any slit, antipad chain or keep-out at ΔR ≈ (π/4)·R_s·(Δψ/I)², O(1) per cut, 12–19% low vs FD [C] (L1; regime limits: [lessons Open questions](../../topics/physics/cross-domain-lessons.md#open-questions)). T: 100 random cuts on real pours, predicted vs FD ΔR; then router cost for antipad chains.
- **XD3** Cut along streamlines (sharp, S): orient unavoidable cuts (via rows, isolation gaps, connector cut-outs) along ψ of the dominant currents, ~90× cheaper than across [C, L1]: "never slot across the current that matters, at the frequency that matters". T: XD2 harness, orientation choices.
- **XD4** Contours as conductors (sharp, M): planar coils (wireless power, inductive sensors, nulling/calibration coils) as traces on equally spaced ψ contours, as a 2025 OPM-MEG pipeline did for 1.5 m biplanar PCB coils [S]. T: reproduce a published PCB coil; field error vs hand-wound spiral.
- **XD5** REGCOIL regularization knob (sharp, S–M): a Tikhonov term on current density sets coil spacing (Landreman 2017) [S]; sweeping it traces a Pareto front of physics error vs copper complexity (peak J, feature count) for the LLM. T: sweep one hot loop, loop L vs feature count.
- **XD6** Minimum-inductance return design (combo, M): Turner minimum-inductance coils (1988) [S]: with the forward conductor fixed, the least-energy return-sheet current on the adjacent layer shows where return copper must stay continuous and where voids are free. T: predicted free-void regions vs PEEC loop L after voiding.
- **XD7** Active shielding of hot loops (new, M): Mansfield–Chapman shielded gradient coils (1986) [S]; on 2-layer boards without a full plane, shape bottom return copper so the hot loop's net dipole moment ≈ 0. T: Biot–Savart far field at 3 m vs "return under it".
- **XD8** Minimax current density (sharp, M): L∞ coil design minimizes peak |J|, not power (arXiv 1002.3413) [S]; apply to hot-spot-limited pours (necks, pad-entry corners) to show where fillets/widening pay. T: peak |J| and thermal hot spot vs loss-optimal copper.
- **XD9** Coil-curve penalties for critical traces (new, M): FOCUS/SIMSOPT (MIT from v1.0 [S]) Fourier-curve coils with differentiable Biot–Savart + curvature/length/distance penalties → PCB bend radius, length, clearance, plus coupling to a victim/magnetometer. T: reshape a sense trace near an inductor, M before/after.
- **XD10** Winding surface ↔ stackup height (combo, M): adjoint winding-surface optimization (Paul et al. 2018) [S] → sensitivity of each physics budget to each dielectric thickness; choose the stackup with the layout. T: FD check of adjoint sensitivities on 3 stackups.
- **XD11** Figure-8 and mirrored loops (sharp, S): RFIC figure-8 inductors cancel far field [S]; TI LMR38020 symmetric input caps, ~4 dB lower FM-band noise [V]; pair numbers: [L6](../../topics/physics/cross-domain-lessons.md#l6-multipoles-and-image-planes-nmr-rfic-mri-shielding--orientation-mirrored-loops) [C]. Placement option "mirrored halves" with an imbalance budget. T: PEEC + near-field scan, dual-cap vs single-cap buck.

## B. Power modules, busbars, planar magnetics

- **XD12** Commutation cells as the placement unit (sharp, S): P-cell/N-cell (Li, Tolbert, Wang, Peng, ECCE 2010) [S] = switch + complementary device + loop-closing cap; N7 places cells, not parts. T: count cell-placed loops on 20 open converter boards vs overshoot data in [hot-loops](../../topics/rules/power/hot-loops.md).
- **XD13** Laminated-busbar primitive (combo, S–M): stacked "+ over −" pour pair, L′ ≈ μ0·d/w + fringing, as a typed placer object (width, overlap margin, layer pair, current). [I] d = 0.2 mm, w = 10 mm: L′ ≈ 25 nH/m (0.25 nH/cm). T: PEEC vs closed form, 5 aspect ratios.
- **XD14** Equalize paralleled loops, not just minimize them (sharp, S): minimize the spread of per-device power- and gate-loop L of paralleled FETs (unequal L → unequal switching current). T: PEEC on a 4-FET bank, current spread in SPICE.
- **XD15** Gate loop orthogonal to power loop (sharp, S): Neumann M between gate and power loop under a budget (e.g. |M| < 0.1 nH); perpendicular planes or the power loop's magnetic null line give M ≈ 0. T: [xd_loop_coupling.py](../../../tools/research/physics/xd_loop_coupling.py)-style M on 10 gate-driver layouts.
- **XD16** PowerSynth as a reference engine (sharp, M): PowerSynth 2 (GPL-3.0, compatible) [P] power-module layout with electrical + thermal models; mine its fast parasitic models and optimization loop for converter cells. T: its models on a PCB half-bridge vs PEEC.
- **XD17** Proximity check for paralleled layers (sharp, S): above f ≈ R/(2πL) ripple crowds into the layer nearest the return ([L5](../../topics/physics/cross-domain-lessons.md#l5-proximity-effect-planar-magnetics--paralleled-layers-interleaving) [C]); check ripple current per layer. T: lumped model vs 2-D PEEC cross-section.
- **XD18** Interleaved current layers (sharp, S): Dowell-style interleaving + − + − for high-ripple paths lowers AC R and loop L (L5). T: XD17 model, interleaved stackup.
- **XD19** Damping set by sqrt(L/C) (sharp, S): RC snubber R ≈ sqrt(L_loop/C_oss) across the loop, from extracted L, not a datasheet default. T: SPICE with the extracted loop.
- **XD20** Electrothermal topology optimization of busbars → pours (combo, M): thermal TO of a 3-layer laminated busbar (HAL hal-01735587) [S] is the closest prior art to electrothermal copper TO; share a benchmark with [copper-shape-synthesis](../../topics/physics/copper-shape-synthesis.md).

## C. IC power grids, interconnect and packaging

- **XD21** Signoff-style IR and current-density maps (sharp, S–M): per rail, worst mV drop at each load pin + |J| vs ampacity map (on-chip IR/EM signoff); local queries by random-walk solvers (Qian, Nassif, Sapatnekar 2005) [S]. T: vs commercial DC-drop tool, 3 boards.
- **XD22** Via rows across the flow, sized by transfer length (new for PCB, S): vias transfer current within L_T = p·sqrt(R_via/(R_s1 + R_s2)) of the entry and exit edges (Berger 1972; Volkersen 1938) [S]; deleting 32 of 40 inner vias costs +1.8% R, HyperLynx agrees [V]; values and column shares: [L3](../../topics/physics/cross-domain-lessons.md#l3-transfer-length-semiconductor-contacts-bonded-joints--via-fields) [C]. Replaces "N vias per amp". T: [xd_sheet.py vias](../../../tools/research/physics/xd_sheet.py) on real transitions; thermal-camera via heating.
- **XD23** Short-neck immunity (Blech analogy) (sharp, S): a neck shorter than its thermal spreading length sinks heat into wide copper on both sides and runs cooler than IPC tables imply; rate necks by length and width. T: FD electrothermal sweep, neck length vs peak T.
- **XD24** Ball-map logic for connector pinouts (sharp, S): package checkerboard power/ground → each fast signal or current pin gets an adjacent return, scored by computed loop L; extends P9. T: score 20 open-hardware connector pinouts.
- **XD25** Shield insertion and net ordering (SINO) (sharp, M): He and Lepak (ISPD 2000) [S] on PCB bus corridors with crosstalk kernel 1/(1+(d/h)²) (Johnson). T: worst-pair coupling vs random order, 10 buses.
- **XD26** Etch-aware geometry (OPC analogy) (sharp, M): design RF filters/couplers/impedance lines for the as-etched trapezoid and bias; score with the fab etch factor applied. T: openEMS (GPL-3), drawn vs as-etched coupled-line filters.
- **XD27** Physics-aware copper thieving (CMP fill analogy) (sharp, S): density rules + no floating copper near antennas/RF (detunes, resonates); grounded, stitched fill elsewhere. T: count floating fill islands in RF zones on open boards.
- **XD28** Passive macromodels per copper region (sharp, M): reduced-order pour/plane models for SPICE co-simulation of PDN and hot loops: PRIMA (Odabasioglu 1998) [S], vector fitting (Gustavsen and Semlyen 1999, from power systems) [S]. T: macromodel vs full PEEC, one buck.
- **XD29** Slack-reweighted nets (timing-driven → budget-driven placement) (combo, S): reweight placement nets by remaining physics-budget slack (nH, mV, dB) after each evaluation; builds on I1, I5. T: violations after 5 rounds vs static weights.
- **XD30** Hierarchical compression of coupling matrices (sharp, M): FMM/H-matrix (FastCap, FastHenry lineage) in board PEEC, O(N log N); licences in [open-solvers](../../topics/physics/open-solvers.md).

## D. Microwave, antenna and photonic inverse design

- **XD31** Adjoint copper heat maps (sharp, M): one adjoint solve → sensitivity of IR drop, loop L or an S-parameter to copper per cell (cuts need the polarization tensor, finite edits rank-k updates), shown as "add here / remove here"; [physics-in-the-loop-optimization](../../topics/physics/physics-in-the-loop-optimization.md#adjoint-sensitivities).
- **XD32** DRC rules inside the optimizer (sharp, M): differentiable morphological transforms for foundry min width/spacing/area (Hammond, Oskooi, Johnson, Ralph, Opt. Express 2021) [S] → PCB min width, clearance, min area inside density optimization, DRC-clean before polygonization. T: DRC violations after legalization with/without.
- **XD33** Robust etch optimization (eroded, nominal, dilated) (sharp, M): optimize the worst of three projections (Wang, Lazarov, Sigmund 2011) [S] with ±etch bias (e.g. ±25 µm) and registration. T: Monte Carlo over bias, nominal- vs robust-optimized filters.
- **XD34** Characteristic modes of the ground structure (new for PCB, M–L): place noise sources where the dominant modes of board + cable shield + heatsink have small weighting ([L10](../../topics/physics/cross-domain-lessons.md#l10-antenna-engineering--characteristic-modes-and-reciprocity)). T: MoM on board + cable stub, rank 5 source positions, check with openEMS.
- **XD35** Reciprocity susceptibility maps (sharp, S–M): solve the field of a unit current in each victim (ADC loop, crystal, antenna feed) once; any aggressor coupling is an inner product, a lookup ([L10](../../topics/physics/cross-domain-lessons.md#l10-antenna-engineering--characteristic-modes-and-reciprocity)). Complements the schematic adjoint in [design reasoning](../../topics/physics/design-reasoning-architecture.md). T: map M vs Neumann M, 50 aggressor positions.
- **XD36** Bloch analysis for periodic features (new, M): via fences, BGA via fields, stitching grids, hatched planes as periodic structures; pick pitch so a stop band covers aggressor harmonics, not λ/20. T: unit-cell eigen-solve vs full via-fence simulation.
- **XD37** Coaxial via cages (sharp, S): return vias on a circle for target Z0 ≈ (60/√εr)·ln(D/d), not "one ground via nearby". T: TDR simulation, 0/1/2/4/6-via cages.
- **XD38** Level-set copper boundaries (sharp, M): pour outlines as level sets moved by shape derivatives (natural topology change), CAD-like output. T: polygon count and smoothness vs SIMP at equal objective.

## E. Flow networks: Murray, Kelvin, transport networks, plumbing, power grids

Math and [C] tables: [L2](../../topics/physics/cross-domain-lessons.md#l2-murray-kelvin-branched-transport--widths-and-topology-of-power-trees), [L7](../../topics/physics/cross-domain-lessons.md#l7-power-grid-engineering--load-flow-n-1-fast-what-ifs-protection-step-voltage), [L8](../../topics/physics/cross-domain-lessons.md#l8-plumbing-and-hvac--reverse-return-tapers-sizing-modes).

- **XD39** Width exponent chosen by objective (electrical Murray's law) (new, S): w ∝ I (Kelvin 1881) minimizes loss at fixed area, minimax drop wants wider trunks, IPC w ∝ I^1.38 is a thermal limit, not an optimum (5-load comb table: L2); size from the declared objective, IPC as floor. T: re-size power nets of 10 open boards at equal area.
- **XD40** Junction conservation check (sharp, S): at loss-optimal branching, parent width = Σ child widths (da Vinci area rule; Murray = cube law for blood); flag narrower parents as bottlenecks. T: count violations on open boards.
- **XD41** Varignon junction relaxation (new, S–M): branch points where tensions T(I) = c0 + a·I balance (c0 clearance overhead per conductor; Gilbert 1967, Xia; L2), by string-tension relaxation; [C] the star that wins at zero overhead loses at 0.6 mm overhead, 126 vs 96 mW. T: relaxed vs hand-drawn trees, 5 boards.
- **XD42** Tree, mesh or pour by the γ rule (new, S): copper has γ = 1, at the tree/sheet transition; clearance overhead → trees, fluctuating loads and failure tolerance → loops, free layer → pour (L2); make the choice explicit per rail. T: classify rails on open boards vs IR and thermal performance.
- **XD43** Loops for moving loads (combo, M): leaf venation loops (Katifori, Szöllősi, Magnasco 2010; Corson 2010) [S]: for moving load current (FPGA regions, motor phases, multiphase) optimize over load scenarios so meshes appear where they pay. T: worst-scenario drop, tree vs scenario-optimized mesh, equal copper.
- **XD44** Physarum and Hu–Cai adaptive copper growth (new for PCB, M): iterate current solves over load scenarios on a fine conductance grid, grow each conductance as |I|^μ − decay, renormalize to the copper budget (Tero et al., Science 2010, Tokyo-rail network [S]; Bonifaci et al.: Physarum minimizes network + routing cost [S]); local, parallel, GPU-friendly; seeds or replaces SIMP. T: loss and drop vs SIMP at equal area on the OP2 benchmark ([optimization](optimization.md)).
- **XD45** Constructal area-to-point collectors (sharp, M): Bejan constructal trees (1997) [S] for distributed loads/sources sharing a layer (LED arrays, paralleled cells, distributed power pins); compare with a full pour when the layer is free. T: drop and copper vs pour, 64-LED array.
- **XD46** Tapered collectors (sharp, S): solar-busbar taper, width ∝ accumulated current (FET rows, LED strips, battery tabs): 25% less loss at equal copper (L8), or equal loss with ~25% area freed [C]. T: FD, 10-FET row.
- **XD47** Reverse-return (Tichelmann) feeding (sharp, S): hydronic equal-path feeding for paralleled FETs, LED strings, cells, multiphase outputs: 5.7× better max/min current share for 8 elements [C] (L8). T: SPICE + FD.
- **XD48** HVAC duct-sizing modes as named rail strategies (sharp, S): the LLM names the mode (L8), the solver executes. T: implement all three in [xd_power_tree.py](../../../tools/research/physics/xd_power_tree.py).
- **XD49** Surge tank sizing (water hammer ↔ hot-plug ringing) (sharp, S): Joukowsky ΔP = ρ·c·Δv ↔ ΔV = Z0·ΔI on a long input cable; size the damped bulk cap from cable L and ceramic input C for ζ ≥ 0.5, not "add a 47 µF electrolytic". T: SPICE hot-plug overshoot vs ζ.
- **XD50** DC load flow with N-1 contingency (new, S–M): losing any one via, neck or connector pin (void, crack, cold joint) keeps remaining copper within current/thermal limits (L7). T: fault-inject single vias, 5 high-current boards.
- **XD51** Rank-1 what-if updates (PTDF/LODF analogy) (sharp, S): factor the conductance matrix once, score via deletion, slot, neck by Sherman–Morrison/Woodbury; makes N-1 (XD50) and the live HUD (U1) fast. T: timing and accuracy vs re-solve, 200k-node sheet.
- **XD52** Protection coordination for copper (I²t) (new, S): every trace downstream of a fuse/eFuse/limiter withstands its let-through I²t, k²S² ≥ I²t (IEC 60949 form) [S]; widths in L7, plus 264 A²s at 3 mm [C]. T: audit fused rails, 20 open boards.
- **XD53** Ground-grid step voltage → equipotential placement (new, S): IEEE Std 80 [S]; E = R_s·I/(2πr) around a return injection (8 LSB case: L7); orient sensitive ground-pin pairs along equipotentials or steer the return. T: FD on 5 mixed-signal boards; bench measurement.
- **XD54** Horton–Strahler orders for power trees (combo, S): label power-tree segments by stream order so intents say "order-3 trunk on L3, order-1 twigs on top". T: does the label predict width and layer on good open boards?
- **XD55** Harmonic load flow on copper (sharp, M): complex sheet problem (R_s + jω·μ0·d per square) per switching harmonic maps where ripple flows in pours (e.g. under an ADC). T: vs near-field scans of a buck board.
- **XD56** Copper's shadow price (combo, S): Lagrange multiplier of the XD39 copper-area constraint = marginal value of 1 mm² per region in mW or mV; published to resource market N1. T: price stability across re-solves.
- **XD57** Kelvin's law for battery products (sharp, S): size main rails where a mm² (or a layer) of copper costs the same as the runtime it buys. T: worked example on an open battery board.
- **XD58** H-tree feeds for paralleled loads (sharp, S): H-tree or reverse-return (XD47) topologies for devices that must share current or switch together. T: FD current share vs comb feed.

## Top 10 to try first

1. **XD22** (S): one script, contradicts a common rule, vendor data agree.
2. **XD2** (S): O(1) scoring of every cut; feeds router and critics.
3. **XD39** (S): ~half the loss, or 40% less worst drop, at equal copper.
4. **XD113** (S): "as close as possible" → computed radius.
5. **XD47** (S): 5.7× better current sharing for free.
6. **XD53** (S): 8 LSB → ~0 by rotation.
7. **XD52** (S): missing safety check.
8. **XD112** (M): ePlace's analogy made literal.
9. **XD1** (M): MRI pipeline applied to pours.
10. **XD34** (M–L): sources placed against the board's real antenna modes.

XD112, XD113: [cross-domain-fields-and-computation § M](cross-domain-fields-and-computation.md#m-multiscale-modelling-sparse-fields-inverse-problems-weather-climate-geophysics).

## Analogies that do not transfer (so nobody tries)

- Fractal lung/vascular trees for BGA power: a free layer's plane beats any tree (γ = 1, copper not paid per volume; XD42).
- Photonic bend-loss curvature rules: PCB bends do not radiate meaningfully below mm-wave; corner effects small below several GHz ([rule genealogy R01](../../topics/physics/rule-genealogy-routing-style-dfm.md)).
- Busbar Lorentz-force design: negligible at PCB currents except kA pulses.
- Physarum "living wires": the algorithm transfers, the organism does not.
