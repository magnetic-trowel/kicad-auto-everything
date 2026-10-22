# Cross-domain lessons for physics-first layout

**TL;DR**
- The most useful transplants come from fields that design how current flows, not just where wires go. Coil design gives stream functions. Power-grid engineering gives load flow, N-1 checks and I²t coordination. Planar magnetics gives the proximity effect. Contact and joint mechanics gives transfer length. They yield closed forms and O(1) checks, not just algorithms.
- Our computed checks [C] sharpen five common rules:
  - via fields work at their edges (transfer length ≈ 1 mm);
  - a slit costs about (π/4)·R_s·(Δψ/I)², where Δψ is the stream-function step across it;
  - the best width exponent depends on the objective, and IPC equal-heating widths raise the worst drop by 35%;
  - paralleled layers stop sharing AC current above about 100 kHz;
  - decaps reach about one screening length, λ = sqrt(L_c/(μ0·d·n)).
- Thermal spreading, decap reach and via current transfer are all one screened Laplace equation with a length scale: 19–64 mm, 4–24 mm and 0.4–1 mm respectively. A literal ePlace follows: FFT convolution with real physics kernels.
- Fixed-thickness copper sits exactly at the tree/loop transition of transport networks (γ = 1). Clearance overhead, moving loads, failure tolerance and free layers decide tree vs mesh vs pour. Rayleigh monotonicity makes "pour everything" free only on low-dV/dt nets.
- These do not transfer: photonic curvature rules, fractal trees, EBG as a general fix, Lorentz forces. Graphics geometry transfers for beauty: offsets of lines and arcs stay exact, offsets of clothoids do not.

All [C] numbers come from four deterministic scripts (each under a minute) in `tools/research/physics/`: [xd_sheet.py](../../../tools/research/physics/xd_sheet.py), [xd_power_tree.py](../../../tools/research/physics/xd_power_tree.py), [xd_lengths.py](../../../tools/research/physics/xd_lengths.py) and [xd_loop_coupling.py](../../../tools/research/physics/xd_loop_coupling.py). They assume 1 oz copper (R_s = 0.49 mΩ/sq) and DC unless stated. The full list of 125 ideas is in [cross-domain ideas](../../ideas/physics-first/cross-domain.md).

## Key facts

### L1. Coil design by stream functions → pours, slots, planar coils

- **Source.** MRI target-field and minimum-inductance coils (Turner 1986, 1988). Stellarator coils by REGCOIL (Landreman 2017), which regularizes current density to reach a target coil spacing [S]. bfieldtools (BSD-3) implements stream functions, inductance and resistance operators on triangle meshes [P]. A 2025 pipeline used it to build 1.5 m biplanar nulling coils as PCBs [S].
- **Math.** A sheet current is J = ∇ψ × n. The current crossing any curve from a to b is ψ(b) − ψ(a). Loss is ∫R_s|∇ψ|², and magnetic energy is quadratic in ψ, so design is a quadratic program and conductors are ψ contours. On a PCB, ψ also prices cuts: a thin slit adds ΔR ≈ (π/4)·R_s·(Δψ/I)², and an edge notch about twice that.

  | Slit in a 20 mm strip | Δψ/I | FD ΔR (sq) | (π/4)(Δψ/I)² |
  |---|---|---|---|
  | across flow, 2 / 5 / 10 mm | 0.10 / 0.25 / 0.50 | 0.009 / 0.055 / 0.233 | 0.008 / 0.049 / 0.196 |
  | along flow, 10 mm | 0 | 0.003 | 0 |
  | from edge, 5 mm | 0.25 | 0.106 | ≈ 2 × 0.049 |

  [C] xd_sheet.py `slot`.
- **Transfers.**
  - One solve scores any cut, antipad chain or keep-out in O(1).
  - Cutting along streamlines costs about 90× less than cutting across.
  - Planar coils and sense loops can be generated from contours.
  - Below cavity resonance, plane-pair spreading inductance obeys the same equation with R_s → jω·μ0·d.
- **Does not.** A coil is a free current sheet. A PCB layer is shared with other nets and has fixed terminals. Inside a given copper shape the DC current has no freedom, so the design variable is the shape.
- **First experiment.** Score 100 random cuts on real pours, Δψ prediction vs FD (target ±25%). Then compare a bfieldtools minimum-energy ψ design of one buck input loop against the hand pour, by PEEC.

### L2. Murray, Kelvin, branched transport → widths and topology of power trees

- **Source.**
  - Murray's law (1926) and Kelvin's law (1881) for economic conductors.
  - Gilbert (1967) and Xia (2003) on flow-dependent Steiner trees.
  - Transport networks are trees when cost ∝ C^γ with γ < 1, and sheets when γ > 1. Loops appear under fluctuating loads or damage (Bohn and Magnasco 2007; Katifori et al. 2010; Corson 2010) [S].
- **Math.** At fixed copper area A, minimizing loss gives w ∝ I, and the loss is R_s·(Σ|I|·L)²/A: Beckmann's W1 transport. For a series path, minimizing the drop gives w ∝ √I. Copper's conductance and its cost both scale with width, so γ = 1 exactly.

  | 5-load comb tree, fixed area | Loss | Worst drop |
  |---|---|---|
  | equal width | 100% | 100% |
  | w ∝ I (Kelvin) | 52% | 89% |
  | w ∝ √I | 62% | 76% |
  | minimax-drop optimum | 76% | 60% |
  | w ∝ I^1.38 (IPC-2221 equal ΔT) | 58% | 135% |

  [C] xd_power_tree.py. A star of separate conductors beats a shared trunk (61 vs 96 mW) until the clearance overhead per conductor exceeds about 0.43 mm.
- **Transfers.** Widths follow from the declared objective, with IPC as a floor only. Branch points come from a balance of tensions T(I) = c0 + a·I. The choice of tree, mesh or pour comes from overhead, load fluctuation and failure tolerance.
- **Does not.** Biology pays for volume. Copper on a free layer costs nothing, and Rayleigh monotonicity says adding copper never raises DC resistance, so there the answer is a pour. The exception is high-dV/dt nodes. A 10×10 mm switch-node pour 0.2 mm over ground is about 19 pF, which injects 0.38 A at 20 V/ns [C]. Fill quiet nets and shrink switch nodes.
- **First experiment.** Re-size the power nets of 10 open boards at equal copper for each objective, and report loss, worst drop and peak temperature.

### L3. Transfer length (semiconductor contacts, bonded joints) → via fields

- **Source.** Berger's contact transmission-line model (1972) and Volkersen's shear lag (1938) [S]. Current or load moves between overlapping layers within a transfer length L_T.
- **Math.** For vias at pitch p, L_T = p·sqrt(R_via/(R_s1 + R_s2)). A 1.6 mm board with a 0.3 mm drill and 25 µm plating gives R_via ≈ 1.08 mΩ and L_T ≈ 1.05 mm. A 0.2 mm blind via gives L_T ≈ 0.37 mm.

  | 10 × 4 vias, 1 mm pitch | End columns | Middle 6 columns | R: 40 vias vs only the 8 end vias |
  |---|---|---|---|
  | through vias | 59% | 16% | 3.20 vs 3.26 mΩ |
  | blind vias | 86% | 2% | 3.14 vs 3.14 mΩ |

  [C] xd_sheet.py `vias`. This matches Siemens' observation that "a handful of vias in one corner" carry the current [V], and the research-note advice to put vias where current enters or leaves.
- **Transfers.** Put via rows across the flow at the entry and exit edges, and rate each via by its share, not by I/N. The same model covers overlapping pours, wide terminals and bolted lugs.
- **Does not.** Thermal vias under an exposed pad get heat over the whole pad, so the whole array works there.
- **First experiment.** Check per-via current at 20 high-current transitions on open boards against the via ampacity in [high-current](../rules/power/high-current.md).

### L4. Screening lengths (Debye, fin theory) → decap reach, thermal reach, physical placement kernels

- **Source.** Debye screening and fin theory both give ∇²u − u/λ² = −s, whose point response is K0(r/λ). ePlace (TODAES 2015) treats density as charge and solves Poisson by FFT [S].
- **Math.**
  - Thermal: λ_th = sqrt(Σk·t/h). A 2-layer board in still air gives λ = 37 mm; a pour radius of 55 mm already reaches 90% of the infinite-plate conductance for a 5 mm source. For 4 layers, 52 mm and 74 mm. Forced air halves λ [C].
  - PDN: a plane pair (μ0·d per square) with n decaps per m², each of mounting inductance L_c, has λ = sqrt(L_c/(μ0·d·n)) while the decaps are inductive. The share of load current within R = x·λ is 1 − x·K1(x).
    - With L_c = 0.7 nH: λ = 24 mm for d = 0.1 mm at 10 mm pitch, 17 mm for 0.2 mm at 10 mm, and 3.7 mm for 1 mm at 5 mm.
    - A lattice FD check gives 22/42/66/88% within 0.5/1/2/3 λ, against 17/40/72/88% from the formula [C].
- **Transfers.**
  - "As close as possible" becomes "within about λ/2".
  - Location matters on thick cavities and two-layer boards, where λ is a few mm. This agrees with Hubing and Altium that location matters little on tight plane pairs [S].
  - A placer can convolve power maps with the thermal kernel, decap maps with the PDN kernel, and aggressor maps with coupling kernels, all by FFT.
- **Does not.** The PDN λ ignores plane capacitance and cavity modes. It is valid above the decaps' series resonance and below the first cavity mode.
- **First experiment.** Add plane capacitance to the lattice and compare with a PDN tool on 3 stackups. Then compare a kernel placer against HPWL plus density on 10 boards.

### L5. Proximity effect (planar magnetics) → paralleled layers, interleaving

- **Source.** Dowell (1966) [S]: AC current crowds toward the conductor facing its return.
- **Math.** Paralleled layers split current as the inverse of their loop impedance R + jωL. The corner is about R/(2πL), roughly 60 kHz for 1 oz at mm spacing. [C] xd_lengths.py: in a 4-layer board with the net on L1, L3 and L4 and the return on L2, L1 carries 33% at DC, 75% at 100 kHz and 86% at ≥ 1 MHz.
- **Transfers.** Paralleling a net on several layers helps DC only. Ripple current needs an adjacent return. Interleaving + − + − cuts both AC resistance and loop L.
- **First experiment.** A 2-D PEEC cross-section vs the lumped split.

### L6. Multipoles and image planes (NMR, RFIC, MRI shielding) → orientation, mirrored loops

- **Source.** Dipole coupling is ∝ m1·m2 − 3(m1·r̂)(m2·r̂) (the NMR magic angle). RFIC figure-8 inductors [S]. Shielded gradient coils (Mansfield and Chapman 1986) [S]. TI's symmetric input capacitors measured about 4 dB lower FM-band noise [V].
- **Math.** [C] xd_loop_coupling.py:
  - Flat 3 mm loops 0.5 mm over a plane couple as about h²/r⁵: −26 dB at 10 mm and −50 dB at 40 mm relative to free space.
  - Standing loops are doubled by the plane, not cancelled.
  - In-plane-axis dipoles null at 54.7°.
  - A mirrored loop pair is null on its symmetry plane and −7/−13/−19 dB along its axis at 10/20/40 mm; a 60/40 imbalance leaves −20 dB.
- **Transfers.** Buffer distance should come from the aggressor's multipole order, not a fixed mm. Mirrored hot loops become a placement option. Inductor orientation follows dipole algebra. Two-layer boards can have a designed "shield" return.
- **Does not.** A plane acts as an image only above its thin-sheet eddy frequency, about 1/(μ0·σ·t·ℓ): tens of kHz for 5 mm features in 1 oz [I]. See [vocabulary](vocabulary.md) for the computed regime. At 50 Hz or DC the plane does nothing.

### L7. Power-grid engineering → load flow, N-1, fast what-ifs, protection, step voltage

- **Load flow and N-1.** DC load flow gives the IR map. N-1 means losing any one via, neck or pin keeps the remaining copper within limits.
- **Fast what-ifs.** LODF-style Sherman–Morrison updates score an edit without a new solve.
- **I²t withstand.** Cables are checked with k²S² ≥ I²t (IEC 60949 form). [C] 1 oz traces heated from 25 to 180 °C withstand 1.2, 7.3 and 29 A²s at 0.2, 0.5 and 1 mm width; compare with the upstream fuse's let-through I²t.
- **Step voltage** (IEEE Std 80). [C] a 10 A return 10 mm from a 5 mm ADC footprint puts 400 µV (8 LSB at 16 bit, 3.3 V) across it radially, and ≈ 0 tangentially.
- **First experiment.** Single-via fault injection on 5 high-current boards, and an equipotential-orientation critic on 5 mixed-signal boards.

### L8. Plumbing and HVAC → reverse return, tapers, sizing modes

- **Reverse return** (Tichelmann: feed at one end, return from the other). [C] 8 paralleled elements with a rail-segment/element resistance ratio of 0.1: max/min current share 13.6 when fed and returned at the same end, 2.4 with reverse return. With 4 elements: 2.4 vs 1.2.
- **Tapers.** A linearly accumulating collector with w ∝ I loses 25% less than uniform width at equal copper.
- **Sizing modes.** Duct sizing becomes named rail strategies: equal friction (equal mV per mm), static regain (equal load voltage), and velocity reduction (J limits).

### L9. Topology optimization with manufacturing filters → DRC-clean, etch-robust copper

- **Source.** Robust erode/nominal/dilate projection (Wang, Lazarov and Sigmund 2011). Foundry-rule-constrained photonic optimization with differentiable morphology (Hammond et al. 2021) [S].
- **Transfers.** Put minimum width, clearance and area inside the optimizer. Optimize the worst of ±etch bias. Use multi-load-case objectives (light load, full load, fault). The solver is in [copper-shape-synthesis](copper-shape-synthesis.md); this adds the manufacturing discipline.
- **Does not.** Compliance problems are self-adjoint and well conditioned. Inductance-weighted multi-net problems with keep-outs are not; expect local minima.

### L10. Antenna engineering → characteristic modes and reciprocity

- **Source.** Characteristic mode analysis (Garbacz 1971; Harrington and Mautz 1971). A heatsink EMI study placed dipole sources by modal weighting, with < 3 dB error against full-wave [S].
- **Transfers.** The ground structure, cable shield and heatsink form an antenna with modes fixed by geometry. Place aggressors where the dominant modes' weighting is small. By reciprocity, one solve per victim gives a susceptibility map, so coupling from any position becomes a lookup.
- **First experiment.** MoM modes of a board plus cable stub; rank 5 source positions; check with openEMS (GPL-3).

### L11. Superconducting quantum layout → stitching, participation, box modes

- **Source.** Airbridges tie CPW grounds, and spacing below λ/4 pushes slotline resonances out of band [S]. Energy participation ratios come from one eigenmode solve (Minev et al. 2021) [S].
- **Transfers.** Set stitching pitch from the slot-mode resonance. Use EPR for loss, coupling and detuning. Check enclosure modes early: [C] a 30×20 mm can resonates at 9.0 GHz, a 200×100 mm box at 1.68 GHz.

### L12. Graphics and robotics geometry → beautiful, exact curves

- **Transfers.**
  - Line-and-arc (G1) geometry keeps pair spacing exact under offsetting; clothoids do not.
  - Elastic-rod relaxation (Bergou 2008) with SDF repulsion gives smooth, legal traces.
  - Maximal Poisson-disk sampling bounds the largest empty circle between stitching vias.
- **Does not.** Curvature is not physics below several GHz. [C] a sharp 90° corner counts as 0.56 squares at DC, consistent with R01 in [rule-genealogy-routing-style-dfm](rule-genealogy-routing-style-dfm.md).

## Recommendations for our system

1. **One screened-Laplace engine** for DC IR, plane-pair spreading L, thermal K0, PDN reach and harmonic flows (complex R_s + jωμ0·d). It outputs potential, current and ψ, so the critics below share one solve. Coordinate with [solver-ladder](solver-ladder.md) and [power-copper](power-copper.md).
2. **Critics** for [physics-critics-catalog](physics-critics-catalog.md):
   - Δψ² slit cost;
   - per-via share;
   - N-1 via and neck;
   - I²t coordination;
   - step voltage;
   - paralleled-layer AC share;
   - decap within λ_pdn;
   - multipole buffer distance;
   - dipole orientation.
3. **IR fields** for [physics-ir](physics-ir.md):
   - `sizing: loss | worst_drop | heating`;
   - `feed: reverse_return | h_tree | comb`;
   - zones where "no noisy streamline crosses";
   - `mirror_loops`;
   - per-net `fill: maximize | minimize` from dV/dt.
4. **Placer kernels:** FFT convolution with thermal K0, PDN K0, dipole 1/r³ or h²/r⁵, and crosstalk 1/(1+(d/h)²).
5. **Generators:** via rows sized by L_T, mirrored hot loops, laminated busbars, coaxial via cages, Poisson-disk stitching, arc-only curves, elastic-rod polish.
6. **Reuse:**
   - bfieldtools (BSD-3);
   - SIMSOPT (MIT from v1.0);
   - PowerSynth 2 (GPL-3.0);
   - ceviche (MIT);
   - openEMS (GPL-3);
   - Qiskit Metal (Apache-2.0) and KQCircuits (GPL-3.0) as architecture references.

   FastHenry and Meep licences: see [open-solvers](open-solvers.md).

## Conflicts and open questions

- **Via counts.** [high-current](../rules/power/high-current.md) counts vias as I divided by per-via ampacity, which assumes even sharing. Current arriving from the side is not shared evenly. Exposed-pad thermal arrays ([thermal](../rules/thermal.md) TH-01) are unaffected.
- **Decap placement.** [decoupling-pdn](../rules/decoupling-pdn.md) quotes "as close as possible" (MT-101). L4 supports the contested view with a formula that is not yet validated against a PDN tool with plane capacitance.
- **IPC sizing.** IPC widths are a heating limit, not an optimum. The 35% figure comes from one synthetic tree.
- **Slit law validity.** The Δψ² law is for spread-out sheet current (pours, plane pairs). A narrow return stream under a trace crossing a slot is a different regime: there Δψ = I, and the cost grows roughly as ℓ·ln ℓ, which matches the Ott-slot fit in [physics-critics-validation](physics-critics-validation.md). Interior slits came out 12–19% under the formula in a finite strip; the edge factor of about 2 is empirical.
- **Thermal λ.** It depends on assumptions: in-plane FR-4 k = 0.3 and h = 10 W/m²K per side. Cross-check with [thermal-physics](thermal-physics.md).
- **Star vs trunk.** The result depends on the clearance-overhead model.
- **Unverified.** Peeren (2003) details; the KQCircuits and Qiskit Metal licences ([S]); characteristic-mode analysis applied to PCB grounds (only the heatsink precedent found).

## Sources

- Research notes:
  - [cross_domain_ideas.md § Q4, Q11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md);
  - [rules_power_rf_analog_dfm.md § 2, § 14](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md).
- Coils:
  - [bfieldtools (BSD-3)](https://github.com/bfieldtools/bfieldtools) [P];
  - [arXiv 2005.10060](https://arxiv.org/abs/2005.10060);
  - [REGCOIL arXiv 1609.04378](https://arxiv.org/abs/1609.04378);
  - [SIMSOPT JOSS](https://joss.theoj.org/papers/10.21105/joss.03525);
  - [minimax J arXiv 1002.3413](https://arxiv.org/abs/1002.3413);
  - [PCB nulling coils](https://www.biorxiv.org/content/10.1101/2025.02.19.638883.full.pdf).
- Networks:
  - [Katifori arXiv 0906.0006](https://arxiv.org/abs/0906.0006);
  - [Corson arXiv 0905.4947](https://arxiv.org/abs/0905.4947);
  - [Bohn–Magnasco arXiv cond-mat/0607819](https://arxiv.org/abs/cond-mat/0607819);
  - [Tero, Science 2010](https://pubmed.ncbi.nlm.nih.gov/20093467/);
  - Hu and Cai, PRL 111:138701.
- Optimization:
  - [Hammond 2021](https://dspace.mit.edu/handle/1721.1/131097);
  - Wang, Lazarov and Sigmund, doi:10.1007/s00158-010-0602-y;
  - ePlace, doi:10.1145/2699873;
  - [busbar thermal TO](https://syracusepreprod.univ-catholille.fr/doc/OAI_1/oai-HAL-hal-01735587v1).
- Power:
  - [P-cell/N-cell, ECCE 2010](https://web.eecs.utk.edu/~tolbert/publications/ecce2010_shengnan_final_paper.pdf);
  - [PowerSynth 2 (GPL-3.0)](https://github.com/e3da/PowerSynth2-core) [P];
  - [Siemens via arrays](https://blogs.sw.siemens.com/electronic-systems-design/2023/05/18/understanding-distribution-of-current-in-via-arrays) [V];
  - [TI SNVAA93](https://ti.com/document-viewer/lit/html/SNVAA93/GUID-B4AD942C-CE4C-44AD-B59B-68B10ADED91B) [V];
  - [Altium decap location](https://resources.altium.com/p/when-does-decoupling-capacitor-location-matter-pcb) [S].
- Antennas and quantum chips:
  - [CMA of heatsinks](https://cdn.amazon.science/27/76/2f7cfcd24758b33a97c210d6bd69/investigation-of-the-radiation-mechanism-of-heatsinks-based-on-characteristic-mode-theory.pdf);
  - [airbridges arXiv 1310.2325](https://arxiv.org/abs/1310.2325);
  - [EPR arXiv 2010.00620](https://arxiv.org/abs/2010.00620).
- Classics, from secondary knowledge [S]: Murray 1926; Kelvin 1881; Gilbert 1967; Berger 1972; Volkersen 1938; Dowell 1966; Turner 1986 and 1988; Mansfield and Chapman 1986; IEC 60949; IEEE Std 80.

See also: [cross-domain ideas](../../ideas/physics-first/cross-domain.md) · [power-copper](power-copper.md) · [pdn-and-commutation](pdn-and-commutation.md) · [copper-shape-synthesis](copper-shape-synthesis.md) · [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md) · [fields-si-emi](fields-si-emi.md) · [vocabulary](vocabulary.md) · [README](README.md)
