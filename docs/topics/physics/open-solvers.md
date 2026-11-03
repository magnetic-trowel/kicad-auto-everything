# Open solvers for physics-first layout: inventory, licences, speed, KiCad paths

Scope: inventory of open engines per fidelity rung (closed forms, 2-D, quasi-static 3-D, full-wave, circuit, bridges, surrogates) with licence verdicts, measured speed and KiCad paths. Not here: rung definitions, escalation, trust radii -> [solver-ladder](solver-ladder.md); independent checks -> [verification-and-limits](verification-and-limits.md); licence policy -> [reuse-matrix](../licensing/reuse-matrix.md).
Keys: FastHenry licence, FastCap2, FasterCap, PyPEEC, Palace, openEMS, openEMS GPU engine, Meep, gprMax, EMerge, Elmer, padne, KiPI, Ki-PIDA AGPL, Tidy3D, Hammerstad-Jensen, IPC-2141, Grover, Ruehli, Goldfarb-Pucel, Johnson via formula, cavity model, image-plane PEEC, PEEC1, MS, MS2, vector fitting, scikit-rf, ngspice, Xyce, gerber2ems, kicad-si-simulation-wrapper, CNN-Cap, surrogates

**Results:**
- Every fidelity rung has a licence-compatible open engine; the gap is plumbing (KiCad copper → geometry + ports → solver → budget ledger), not solvers. No maintained KiCad → PEEC/FastHenry-deck exporter exists; our physics graph fills it ([physics-ir](physics-ir.md)).
- Licence traps: FastHenry, Ki-PIDA, Tidy3D; clean quasi-static engines: PyPEEC, FasterCap, Palace, our PEEC [P].
- Closed forms are accurate inside their range and useless outside it [C].
- Image-plane PEEC (numpy, 0.1–1.7 ms per loop) is the loop workhorse: within 1.3% of FastHenry (7–115 s) on 4 loops [C]; filament caveats -> [verification-and-limits](verification-and-limits.md#1-claims-verified-by-an-independent-method). FDTD is the wrong tool for electrically small structures (a hot loop needs ~2×10⁵ time steps).
- GPU options exist today for most rungs (list below) [P].

Tags: [P] read in repo/primary, [S] snippet/abstract, [I] inference, [C] computed by [sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py) or [sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py) (numpy/scipy, 1 thread, shared 4-core VM). "Last commit" = default-branch HEAD on 2026-10-22, shallow clones. Actions as in [reuse-matrix](../licensing/reuse-matrix.md): IN (vendor/link), PROC (separate process), REF (patterns only), AVOID.

## Licence verdicts

| Item | Finding | Action |
|---|---|---|
| FastHenry 3.0 ([ediloren/FastHenry2](https://github.com/ediloren/FastHenry2), master and WRCad branches; last commit 2015-09) | 1994 notice in `src/fasthenry/induct.h` and 17 other files (18 files): "Permission to use, copy and modify for internal, noncommercial purposes … Any distribution … strictly prohibited without prior written consent of M.I.T." No file has a permissive grant. FreeBSD port labels it MIT ([FreshPorts](https://freshports.org/science/fasthenry/)) [P]/[S] | REF; at most a user-installed calibration tool; never vendor or redistribute; generating decks is fine (internal cross-checks only) |
| FastCap2 ([repo](https://github.com/ediloren/FastCap2), 2015) | 42 files carry the 2003 MIT grant ("use, copy, modify, sell and/or distribute … without royalty", plus indemnity); 1 file keeps the 1994 non-commercial header [P] | audit file by file before vendoring; prefer FasterCap |
| Ki-PIDA ([repo](https://github.com/kbralten/KiPIDA)) | LICENSE AGPL-3.0 [P] | REF (same rule as Konnect) |
| Tidy3D ([client](https://github.com/flexcompute/tidy3d)) | pyproject says LGPLv2+, COPYRIGHT file AGPL-3.0+; solver runs in Flexcompute's cloud [P] | commercial reference only |

Re-run the clone-and-grep licence audit before each release [I].

## F1: closed forms (µs, vectorizable)

Treat each as a function with a validity domain (w/h, εr, frequency, geometry class); refuse to evaluate outside it, or escalate ([solver-ladder](solver-ladder.md)) [C].

| Formula | Quantity | Validity and measured error | Cost |
|---|---|---|---|
| Hammerstad-Jensen 1980 | microstrip Z0, ε_eff (t = 0; thickness and dispersion add-ons exist) | vs 2-D FD (16h box, Richardson from 10/20 cells per h), FR-4 εr 4.3, w/h 0.2–6: Z0 within 0.2–0.7%, ε_eff 0.1–0.5% [C] | 1–2.5 µs Python; ~0.05 µs vectorized [C] |
| IPC-2141 (87/√(εr+1.41)·ln(5.98h/(0.8w+t))) | microstrip Z0 | same reference: +2.2…+2.5% at w/h 0.2–1, −1.5% at 1.9, **−12% at 3, −65% at 6** [C]; stated range 0.1 < w/h < 2 | µs |
| Wheeler, Cohn, Kirschning-Jansen | wide strips, stripline, coupled microstrip | published ~1% in range [S] | µs |
| Grover / Ruehli parallel-filament M; rectangle GMD 0.2235(w+t); Hoer-Love exact bar | partial L of trace segments | exact for filaments; GMD self term fails for short wide pads [I] | sub-µs per pair |
| Image-plane PEEC1 (one filament per segment) | loop L over an ideal plane | 3–5% when w/h < 1; **fails for w/h ≥ 3** (median −55%): filament-to-image distance 2h < strip GMD [C] | 0.3–0.8 µs per rectangle batched [C] |
| MS = Σ length·L′(w,h), L′ = Z0,air/c; MS2 = MS + coupled-line mutual −2·overlap·(µ0/4π)·ln(1+(2h/s)²) (ours) | loop L over a plane | MS2: Spearman 0.999 vs multi-filament PEEC on 600 random loops; median bias +9…+14%, p90 +12…+31% [C]; ranking quality -> [solver-ladder](solver-ladder.md#measured-trust-radii-for-loop-inductance-c) | µs |
| Goldfarb-Pucel; Rosa straight wire (HF: ln(2h/r) − 1) | via partial L | 1.6 mm, 0.3 mm drill: 0.54 and 0.66 nH; Johnson's 5.08h[ln(4h/d)+1] gives 1.30 nH, 2–6× these across 0.2–1.6 mm vias [C]. None is a loop inductance | µs |
| Plane-pair cavity model (Okoshi; Lei/Pan; Novak) | Z(f) between ports on rectangular planes | first mode of a 50×40 mm FR-4 pair 1438 MHz = c/(2a√εr) [C]; rectangles only | 2–10 / 9–23 ms / 0.1–0.3 s per 600-point sweep at 20² / 40² / 80² modes [C] |
| Johnson K = 1/(1+(D/H)²) | crosstalk coefficient | order of magnitude; NEXT/FEXT need t_r and length terms ([checkers-si-emi](../rules/checkers-si-emi.md)) | µs |
| Ott/Hubing radiation (E ≈ 2.63×10⁻¹⁴·f²AI/r differential; E ≈ 1.26×10⁻⁶·fLI/r CM) | far-field bound | worst-case ranking bound; CM cable term dominates real boards ([checkers-si-emi](../rules/checkers-si-emi.md) D, F) | µs |

## F2a: 2-D cross-section solvers (ms–s)

| Tool | Method | Licence → action | Status | Notes |
|---|---|---|---|---|
| Own FD/FV Laplace (numpy/scipy) | node FV, εr on edges, SuperLU | ours | [sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py) | w/h 1.9: 5 cells/h 20–64 ms (3.9k unknowns, Z0 −2%); 10 → 0.16–0.23 s; 20 → 0.8–1.5 s; 40 → 4.6–12 s (257k unknowns, still −1.2% in an 8h box) [C]; ranges over shared-VM runs. Zero-thickness edges converge at first order: extrapolate, don't refine |
| scikit-rf `media` | closed forms (MLine, CPW, coax) + Touchstone tooling | BSD-3 → IN | active (2026-10) | no field solve |
| KiCad PCB Calculator (Transcalc) | closed forms | GPL-3 → IN | in KiCad | microstrip, CPW, GCPW, stripline, coupled |
| atlc | bitmap FD, arbitrary 2-conductor cross-sections | GPL → PROC | dormant ~10 years ([KiCad forum](https://forum.kicad.info/t/atlc-arbitrary-transmission-line-calculator-for-transmission-lines-and-directional-couplers/60362)) [S] | independent check |
| TNT-MMTL ([sourceforge](https://mmtl.sourceforge.net/)) | 2-D/2.5-D MoM → RLGC, SPICE | GPL (version unverified) → PROC | dormant [S] | multiconductor RLGC for MTL/SPICE |
| OpenParEM2D/3D (Brian Young) | MFEM port solver, 3-D FEM | **unverified**: openparem.org bot-walled; [2022 MFEM slides](https://mfem.org/pdf/workshop22/08_Young_OpenParEM2D.pdf) only [S] | ? | check before use |
| Elmer 2-D, FEniCSx (dolfinx LGPL-3.0), scikit-fem (BSD-3) | general FEM | IN | active | DIY electrostatics; FEniCSx GPUs via PETSc [I] |
| PCB_SI_Toolkit ([repo](https://github.com/ugo-silato/PCB_SI_Toolkit)) | 2-D Z0 solver in a KiCad 10 toolkit | MIT → IN | active (2026-10) | also an openEMS tab |

## F2b: quasi-static 3-D and 2.5-D (ms–min)

Quasi-static is the default for anything electrically small (largest dimension < λ/10 at the top frequency): hot loops, decap mounts, via fields go to PEEC, not FDTD [C/I].

| Tool | Method | Licence → action | Status, GPU | Input / KiCad path |
|---|---|---|---|---|
| Own image-plane PEEC ([sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py)) | N filaments across width, HF current split solved, PEC image | ours | 0.25–0.8 ms (7 filaments), 0.8–1.7 ms (15) per loop [C] | Manhattan polylines from KiCad tracks |
| FastHenry 3.0 | multipole-accelerated PEEC, meshed ground planes, frequency sweep | non-commercial header → REF | 2015; CPU, 1 core | text deck; this VM: 11k–30k filaments in 7–115 s; 0.1 mm plane mesh (181k filaments) unfinished at 900 s [C] |
| [PyPEEC](https://github.com/otvam/pypeec) 5.8 ([JOSS](https://joss.theoj.org/papers/10.21105/joss.06644)) | FFT-accelerated voxel PEEC, magnetic materials | MPL-2.0, multi-licensed LGPL/GPL → IN | 2025-11; GPU (CuPy), multithread [P] | voxels (STL, PNG layers); thin wide copper voxelizes poorly [S] |
| [FasterCap](https://github.com/ediloren/FasterCap) | 2-D/3-D capacitance, BEM with FMM/hierarchical | LGPL-2.1 → IN | 2019; CPU | FastCap-style deck |
| [Palace](https://github.com/awslabs/palace) electrostatic/magnetostatic | FEM (MFEM/libCEED) lumped C and L matrices, AMR | Apache-2.0 → IN | active; NVIDIA/AMD GPU, multi-GPU [P] | gmsh mesh; no KiCad path |
| [Elmer](https://github.com/ElmerCSC/elmerfem) | static current conduction, magnetodynamics (Whitney), heat | GPL-2.0-or-later; ElmerSolver sources LGPL-2.1+ [P] → IN | active (2026-10) | kicad-cli XAO/STEP → Salome or gmsh → Elmer ("a bit tedious", [jrainimo](https://jrainimo.com/build/2024/11/oss-thermal-simulation-of-pcbs/)) |
| [padne](https://github.com/atx/padne) | KiCad-native 2.5-D FEM DC IR drop | GPL-3.0 → IN | active (2026-10) | reads KiCad; schematic directives |
| [KiPI](https://github.com/drewsum/KiPI) | DC drop, AC PDN impedance, coupled noise | GPL-3.0 → IN | active (2026-10) | KiCad + YAML |
| [tm_board_thermal_fv.py](../../../tools/research/physics/tm_board_thermal_fv.py) | multi-layer 2-D FV thermal, via barrels, convection | ours | ~1 s at 0.5 mm, 2 layers ([thermal-physics](thermal-physics.md)) | copper raster per layer |
| Own 2.5-D FV IR drop | sheet FV + SuperLU | ours | 40×30 mm pour: 27k cells 0.08–0.2 s, 109k 0.6–1.5 s, 436k 6–9 s factorization; 6–300 ms per extra RHS [C] | raster of filled zones |

**Merge the three PEEC prototypes** behind the evaluator contract, keeping FastHenry decks as regression tests: [sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py) (image plane, proxies), [pw_peec.py](../../../tools/research/physics/pw_peec.py) (nodal R + jωL with vias and capacitor bodies), [fe_peec_plane.py](../../../tools/research/physics/fe_peec_plane.py) (meshed plane, slot crossings); they share the Grover kernels [I]. Own the F1/F2 kernels (each < 300 lines, ms-fast); wrap openEMS (gerber2ems/si-wrapper slices) and Palace for F3 [I].

## F3: full-wave (minutes–hours)

GPU budget goes to F3 FDTD/FEM and batched F1/surrogate evaluation, not to 2-D solves already ms–s on CPU [I].

| Tool | Method | Licence → action | Status, GPU | KiCad path |
|---|---|---|---|---|
| [openEMS](https://github.com/thliebig/openEMS) | EC-FDTD, Python/Octave | GPL-3.0+; CSXCAD LGPL-3.0 [P] → IN | active (2026-10-21); CPU SSE/multithread; **unreleased GPU engine** `--engine=gpu`: HIP (AMD, NVIDIA via CUDA) and Metal, checked against a CPU reference backend ([CHANGELOG](https://github.com/thliebig/openEMS/blob/master/CHANGELOG.md)) [P] | gerber2ems, si-wrapper, pcbmodelgen, PCB_SI_Toolkit |
| [Meep](https://github.com/NanoComp/meep) | FDTD, MPI, adjoint inverse design | GPL-2.0-or-later [P] → IN | active; no GPU | none; photonics |
| [gprMax](https://github.com/gprMax/gprMax) 4.0 | FDTD | GPL-3.0 → IN | active; CUDA, OpenCL, Metal, MPI [P]; 1194 / 3405 Mcell/s on Kepler / Pascal ([2019 paper](https://repository.uwl.ac.uk/id/eprint/5755/)) [S] | none; GPR |
| [Palace](https://github.com/awslabs/palace) | FEM: eigenmode, driven (lumped/wave ports, adaptive fast sweep), transient | Apache-2.0 → IN | active; GPU [P] | gmsh |
| [EMerge](https://github.com/FennisRobert/EMerge) 3.0b | Python FEM, time-harmonic, AMR, direct solvers | GPL-2.0-or-later (source headers) [P] → IN | active (2026-10-22); GPU via cuDSS/SPARTA [P] | Gerber, ODB++ via `emcad` add-on [P] |
| Elmer vector Helmholtz | FEM | GPL-2.0+ → IN | active | as above |
| [scuff-em](https://github.com/HomerReid/scuff-em) | surface BEM | GPL-2.0+ headers → IN | stale (2018) | — |
| [necpp](https://github.com/tmolteno/necpp) / [xnec2c](https://github.com/KJ7LNW/xnec2c) | NEC2 thin-wire MoM | GPL-2 / GPL-3 → PROC | active | cables, attached wires as CM antennas |
| [fdtdx](https://github.com/ymahlau/fdtdx) | JAX FDTD, autodiff, time-reversal gradients | MIT → IN | active; GPU/multi-GPU [P] | none; photonics scale |
| [ceviche](https://github.com/fancompute/ceviche), [flaport/fdtd](https://github.com/flaport/fdtd), [jax-fem](https://github.com/deepmodeling/jax-fem) | 2-D FDFD/FDTD autograd; PyTorch FDTD; differentiable FEM | MIT, MIT, GPL-3.0 → IN | ceviche stale (2023) | prototyping differentiable physics |
| OpenFOAM ([openfoam.org](https://openfoam.org)) | FV CFD; `chtMultiRegionFoam` conjugate heat transfer | GPL-3.0 [S] → PROC | active; CPU/MPI | STEP → snappyHexMesh; hours per case [I]. Antmicro's FreeCAD/gmsh/CalculiX flow is the lighter thermal F3 ([evaluation-stack](../verification/evaluation-stack.md)) |
| Own numpy Yee | 3-D FDTD | ours | 20–46 Mcell-updates/s [C] vs openEMS 294 Mcell/s in a gerber2ems log ([README](https://github.com/antmicro/gerber2ems)) [P] | — |

## Circuit, channel and macromodel tools

| Tool | Role | Licence → action |
|---|---|---|
| ngspice | in KiCad's schematic simulator (op, DC, AC, transient, noise); lossy lines LTRA/TXL/CPL | modified BSD core with GPL/LGPL exceptions per file ([Debian copyright](https://sources.debian.org/src/ngspice/24-1/COPYING)) [S] → check per component |
| [Xyce](https://github.com/Xyce/Xyce) | MPI-parallel SPICE for large back-annotated netlists | GPL-3.0 [P] → IN/PROC |
| [Qucs-S](https://github.com/ra3xdh/qucs_s) | GUI over ngspice/Xyce/Qucsator; S-parameters | GPL-2 file, "or later" headers [I] → PROC |
| [scikit-rf](https://github.com/scikit-rf/scikit-rf) | Touchstone, de-embedding, `VectorFitting` with passivity test and enforcement | BSD-3 → IN |
| [SignalIntegrity](https://github.com/TeledyneLeCroy/SignalIntegrity) | S-parameter netlists, simulation, de-embedding | GPL-3.0-or-later [P] → IN |
| [PyBERT](https://github.com/capn-freako/PyBERT) | serial-link and IBIS-AMI eye simulation | BSD [P] → IN |

**Vector fitting is not push-button** [C]. Damped 1-port PDN (cavity + 12 MLCCs, 600 points, 100 kHz–3 GHz, S referenced to 1 Ω): passive fit with 6 complex pairs + 2 real poles in 2–4 s, 9 pairs + 2 real in 3–7 s (rms 2×10⁻³, 1×10⁻⁴). Bare, nearly lossless cavity (|S11| ≈ 1): 6–76 s for 10–30 pairs at rms 1–2×10⁻², non-passive; `passivity_enforce()` failed at default settings.

## KiCad bridges

| Bridge | What | Licence | State |
|---|---|---|---|
| [gerber2ems](https://github.com/antmicro/gerber2ems) | Gerbers + stackup + ports → openEMS → S-params | Apache-2.0 | active (2026-10) |
| [kicad-si-simulation-wrapper](https://github.com/antmicro/kicad-si-simulation-wrapper) | slices nets and neighbours, places ports, shorts 0 Ω and big caps | Apache-2.0 | 2026-04; KiCad 9.0.x only |
| [pcbmodelgen](https://github.com/jcyrax/pcbmodelgen) | KiCad → openEMS Octave models | GPL-3.0 | stale (2023) |
| [KiCad Electrodynamic & Static Studio](https://github.com/ravid1323/KiCad-Electrodynamic-Static-Studio) | kipy extraction, headless openEMS, MNA DC, vector fitting | **no licence file** | REF only |
| [emcvisual](https://github.com/tombueng/emcvisual) | Biot–Savart near field with images; reads KiCad 6–10 | 0BSD-style | active |
| EMerge + `emcad` | Gerber/ODB++ → FEM | GPL-2.0+ | active |
| kicad-cli STEP/XAO/BREP → gmsh/Salome → Elmer, Palace, CalculiX | meshing route for FEM | — | works, multi-tool |
| KiCad core | ngspice only. FEM-in-pcbnew proposal [#8398](https://gitlab.com/kicad/code/kicad/-/issues/8398) (April 2021, KiCad 5.99) [P]; "not much progress in 6 years" per a forum user [S]; no SI/PI roadmap ([forum](https://forum.kicad.info/t/future-plans-for-basic-signal-integrity-si-power-integrity-pi-funtionality/70585)) | GPL-3 | — |

## Learned surrogates

| Work | Result | Tag |
|---|---|---|
| CNN-Cap (Tsinghua; [arXiv 2107.06511](https://arxiv.org/abs/2107.06511)) | 2-D pattern capacitances: total C error < 1.3%, > 99.5% of couplings within 10%; 4693× faster than a 2-D field solver on a GPU server; retrained per process node | [S] |
| 3-D CNN-Cap / NAS-Cap ([arXiv 2408.13195](https://arxiv.org/html/2408.13195v1)) | < 5% error with ~99% probability, 191× faster than a random-walk solver; 4.1% of couplings > 10% error | [S] |
| ParaGraph (NVIDIA 2020, [page](https://research.nvidia.com/publication/2020-07_paragraph-layout-parasitics-and-device-parameter-prediction-using-graph-neural)) | GNN predicts pre-layout net parasitics from schematics, R² 0.772 | [S] |
| PDN-impedance DNN (Missouri S&T, [arXiv 2106.10693](https://arxiv.org/abs/2106.10693)) | > 1M random boards labelled by BEM; 0.1 s per board, > 100× faster than BEM, 10⁴× faster than full-wave | [S] |
| PCB thermal DeepONet ([POSTECH thesis](https://poasis.postech.ac.kr/handle/2014.oak/124072)); FNO EM surrogates (photonics) | operator learning exists; nothing open, PCB-generic and maintained | [S] |
| Libraries | [neuraloperator](https://github.com/neuraloperator/neuraloperator) (MIT), [PhysicsNeMo](https://github.com/NVIDIA/physicsnemo) (Apache-2.0), [DeepXDE](https://github.com/lululxvi/deepxde) (LGPL-2.1) | [P] |
| Ours: residual on MS2 vs black box | 300 PEEC labels, 1,200 held out: log-linear correction of MS2 median 3.5%, p95 9.8% (one outlier 114%); same model on raw features 28% and 100% [C] | [C] |

## Commercial references (calibration and literature only)

Ansys HFSS, SIwave, Q3D; Cadence Sigrity, Clarity; Siemens HyperLynx; Dassault CST; Keysight ADS/Momentum; Sonnet (free Lite tier); Simberian Simbeor; Flexcompute Tidy3D (cloud GPU FDTD). Use published app notes and validation cases; never put them in the loop.

## Open questions

- **FastHenry:** [physics-ir](physics-ir.md), [vocabulary](vocabulary.md) and [V4](../../ideas/original/verification.md) use it only as an internal, unshipped calibration solver. Does MIT's 2003 FastCap-style grant also cover FastHenry? The FreeBSD "MIT" label suggests it might; FastFieldSolvers or MIT could answer.
- **Johnson's via formula** ([checkers-power](../rules/checkers-power.md) loop estimator) gives 2–6× Rosa/Goldfarb-Pucel partial L; replace with a loop model including the return via or plane.
- **Unverified:** OpenParEM licence and repository; openEMS GPU throughput (unreleased, no numbers); Palace and EMerge PCB runtimes; whether ngspice's S-parameter analysis is exposed in KiCad.
- **Ideal-plane PEEC** is the HF limit: below ~1 MHz for 35 µm planes the return spreads ([vo_return_spread.py](../../../tools/research/physics/vo_return_spread.py)) and image PEEC underestimates L.

## Sources

- Research notes: [constraints_verification_benchmarks.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md); [licensing.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md).
- Repos: licence files, source headers and READMEs from shallow clones, 2026-10-22 (table links).
- Classic formulas: Hammerstad & Jensen, IEEE MTT-S 1980; Grover, *Inductance Calculations* (1946); Ruehli, IBM J. R&D 16(5), 1972; Hoer & Love, J. Res. NBS 69C, 1965; Goldfarb & Pucel, IEEE MGWL 1(6), 1991; Kamon, Tsuk & White, "FASTHENRY", IEEE T-MTT 42(9), 1994; Gustavsen & Semlyen (vector fitting), IEEE TPWRD 14(3), 1999.
- Related: [simulation ideas](../../ideas/physics-first/simulation.md), [physics-critics-catalog](physics-critics-catalog.md).
