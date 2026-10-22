# Open solvers for physics-first layout: inventory, licences, speed, KiCad paths

**TL;DR**
- Every fidelity tier has a licence-compatible open engine. The gap is plumbing (KiCad copper → geometry + ports → solver → budget ledger), not solvers. Fidelity tiers F0–F4 are defined in [solver-ladder](solver-ladder.md).
- **Licence traps that change existing docs:** FastHenry's MIT source carries a 1994 notice, "internal, noncommercial purposes … any distribution … strictly prohibited", in 18 files and no permissive notice. Ki-PIDA is **AGPL-3.0**. Tidy3D's solver is proprietary. The clean quasi-static engines are PyPEEC (MPL-2.0 or GPL), FasterCap (LGPL-2.1), Palace (Apache-2.0) and our own PEEC [P].
- **Closed forms are accurate inside their range and useless outside it.** Hammerstad-Jensen matches an extrapolated 2-D field solve within 0.2–0.7% at 1–2.5 µs per call. IPC-2141 is −12% off at w/h = 3 and −65% at w/h = 6 [C].
- **Quasi-static PEEC is the workhorse for loops.** Image-plane PEEC in numpy (0.1–1.7 ms per loop) agrees with FastHenry on a meshed plane within 1.3% (FastHenry: 7–115 s) [C]. For electrically small structures FDTD is the wrong tool: a hot loop needs ~2×10⁵ time steps.
- **GPU today:** Palace (CUDA/HIP), gprMax (CUDA/OpenCL/Metal), fdtdx (JAX), PyPEEC (CuPy), EMerge (GPU direct solvers), plus an unreleased openEMS GPU engine (HIP/Metal, master branch, Oct 2026) [P].

## Key facts

Tags: [P] read in repo/primary, [S] snippet/abstract, [I] inference, [C] computed here by [sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py) or [sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py) (numpy/scipy, 1 thread, shared 4-core VM). "Last commit" is the default-branch HEAD on 2026-10-22, from shallow clones. Action key as in [reuse-matrix](../licensing/reuse-matrix.md): IN (vendor/link), PROC (separate process), REF (patterns only), AVOID.

### Licence verdicts that correct earlier docs

| Item | Finding | Earlier claim | Action |
|---|---|---|---|
| FastHenry 3.0 ([ediloren/FastHenry2](https://github.com/ediloren/FastHenry2), master and WRCad branches; last commit 2015-09) | `src/fasthenry/induct.h` and 17 other files: "Permission to use, copy and modify for internal, noncommercial purposes … Any distribution … strictly prohibited without prior written consent of M.I.T." No file carries a permissive grant. The FreeBSD port labels it MIT ([FreshPorts](https://freshports.org/science/fasthenry/)) [P]/[S] | "MIT-origin" ([evaluation-stack](../verification/evaluation-stack.md)); "keep FastHenry decks as first solver targets … check the MIT licence" ([physics-ir](physics-ir.md)) | REF; at most a user-installed calibration tool. Never vendor or redistribute. Generating decks is fine |
| FastCap2 ([repo](https://github.com/ediloren/FastCap2), 2015) | 42 files carry the 2003 MIT grant ("use, copy, modify, sell and/or distribute … without royalty", plus an indemnity clause); 1 file still has the 1994 non-commercial header [P] | "MIT-origin" | Audit file by file before vendoring; prefer FasterCap |
| Ki-PIDA ([repo](https://github.com/kbralten/KiPIDA)) | LICENSE is AGPL-3.0 [P] | Listed as a T2 tool without a flag | REF (same rule as Konnect) |
| Tidy3D ([client](https://github.com/flexcompute/tidy3d)) | pyproject says LGPLv2+, the COPYRIGHT file says AGPL-3.0+; the solver runs in Flexcompute's cloud [P] | — | Commercial reference only |

### F1: closed forms (µs, vectorizable)

| Formula | Quantity | Validity and measured error | Cost |
|---|---|---|---|
| Hammerstad-Jensen 1980 | Microstrip Z0, ε_eff (t = 0; thickness and dispersion add-ons exist) | Against a 2-D FD solve (16h box, Richardson from 10/20 cells per h), FR-4 εr 4.3, w/h 0.2–6: Z0 within 0.2–0.7%, ε_eff within 0.1–0.5% [C] | 1–2.5 µs Python; ~0.05 µs vectorized [C] |
| IPC-2141 (87/√(εr+1.41)·ln(5.98h/(0.8w+t))) | Microstrip Z0 | Same reference: +2.2…+2.5% at w/h 0.2–1, −1.5% at 1.9, **−12% at 3, −65% at 6** [C]. Its stated range is 0.1 < w/h < 2 | µs |
| Wheeler, Cohn, Kirschning-Jansen | Wide strips, stripline, coupled microstrip | Published accuracy ~1% in range [S] | µs |
| Grover / Ruehli parallel-filament M; rectangle GMD 0.2235(w+t); Hoer-Love exact bar | Partial inductance of trace segments | Exact for filaments; the GMD self term fails for short wide pads [I] | sub-µs per pair |
| Image-plane PEEC ("PEEC1", one filament per segment) | Loop L over an ideal plane | Within 3–5% when w/h < 1; **fails for w/h ≥ 3** (median −55%) because the filament-to-image distance 2h is below the strip's GMD [C] | 0.3–0.8 µs per rectangle batched [C] |
| Σ length·L′(w,h) with L′ = Z0,air/c ("MS"), plus a coupled-line mutual term −2·overlap·(µ0/4π)·ln(1+(2h/s)²) ("MS2", ours) | Loop L over a plane | MS2: Spearman 0.999 against multi-filament PEEC on 600 random loops; systematic median bias +9…+14%, p90 +12…+31% [C] | µs |
| Goldfarb-Pucel; Rosa straight wire (HF: ln(2h/r) − 1) | Via partial L | 1.6 mm, 0.3 mm drill: 0.54 and 0.66 nH. Johnson's 5.08h[ln(4h/d)+1] gives 1.30 nH, i.e. 2–6× these values across 0.2–1.6 mm vias [C]. None is a loop inductance | µs |
| Plane-pair cavity model (Okoshi; Lei/Pan; Novak) | Z(f) between ports on rectangular planes | First mode of a 50×40 mm FR-4 pair at 1438 MHz = c/(2a√εr) [C]; rectangles only | 2–10 ms / 9–23 ms / 0.1–0.3 s per 600-point sweep at 20² / 40² / 80² modes [C] |
| Johnson K = 1/(1+(D/H)²) | Crosstalk coefficient | Order of magnitude; NEXT/FEXT need t_r and length terms ([checkers-si-emi](../rules/checkers-si-emi.md)) | µs |
| Ott/Hubing radiation (E ≈ 2.63×10⁻¹⁴·f²AI/r differential; E ≈ 1.26×10⁻⁶·fLI/r common-mode) | Far-field bound | Worst-case bound for ranking; the common-mode cable term dominates real boards ([checkers-si-emi](../rules/checkers-si-emi.md) D, F) | µs |

### F2a: 2-D cross-section solvers (ms–s)

| Tool | Method | Licence → action | Status | Notes |
|---|---|---|---|---|
| Own FD/FV Laplace (numpy/scipy) | Node FV, εr on edges, SuperLU | ours | [sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py) | At w/h 1.9: 5 cells/h 20–64 ms (3.9k unknowns, Z0 −2%); 10 → 0.16–0.23 s; 20 → 0.8–1.5 s; 40 → 4.6–12 s (257k unknowns, still −1.2% in an 8h box) [C]. Times are ranges over runs on a shared VM. Zero-thickness edges converge to first order, so extrapolate rather than refine |
| scikit-rf `media` | Closed forms (MLine, CPW, coax) plus Touchstone tooling | BSD-3 → IN | active (2026-10) | Uses the same closed forms; no field solve |
| KiCad PCB Calculator (Transcalc) | Closed forms | GPL-3 → IN | in KiCad | Microstrip, CPW, GCPW, stripline, coupled |
| atlc | Bitmap FD, arbitrary 2-conductor cross-sections | GPL → PROC | dormant ~10 years ([KiCad forum](https://forum.kicad.info/t/atlc-arbitrary-transmission-line-calculator-for-transmission-lines-and-directional-couplers/60362)) [S] | Useful as an independent check |
| TNT-MMTL ([sourceforge](https://mmtl.sourceforge.net/)) | 2-D/2.5-D MoM → RLGC and SPICE | GPL (version unverified) → PROC | dormant [S] | Multiconductor RLGC is what MTL/SPICE needs |
| OpenParEM2D/3D (Brian Young) | MFEM-based port solver and 3-D FEM | **Unverified**: openparem.org was bot-walled; [2022 MFEM slides](https://mfem.org/pdf/workshop22/08_Young_OpenParEM2D.pdf) only [S] | ? | Check before use |
| Elmer 2-D, FEniCSx (dolfinx LGPL-3.0), scikit-fem (BSD-3) | General FEM | IN | active | DIY electrostatics; FEniCSx gets GPUs through PETSc [I] |
| PCB_SI_Toolkit ([repo](https://github.com/ugo-silato/PCB_SI_Toolkit)) | 2-D Z0 solver inside a KiCad 10 toolkit | MIT → IN | active (2026-10) | Also an openEMS tab |

### F2b: quasi-static 3-D and 2.5-D (ms–min)

| Tool | Method | Licence → action | Status, GPU | Input / KiCad path |
|---|---|---|---|---|
| Own image-plane PEEC ([sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py)) | N filaments across width, HF current split solved, PEC image | ours | 0.25–0.8 ms (7 filaments), 0.8–1.7 ms (15) per loop [C] | Manhattan polylines from KiCad tracks |
| FastHenry 3.0 | Multipole-accelerated PEEC, meshed ground planes, frequency sweep | Non-commercial header → REF | 2015; CPU, 1 core | Text deck. On this VM: 11k–30k filaments in 7–115 s; a 0.1 mm plane mesh (181k filaments) did not finish in 900 s [C] |
| [PyPEEC](https://github.com/otvam/pypeec) 5.8 ([JOSS](https://joss.theoj.org/papers/10.21105/joss.06644)) | FFT-accelerated voxel PEEC, magnetic materials | MPL-2.0, multi-licensed LGPL/GPL → IN | 2025-11; GPU (CuPy), multithread [P] | Voxels (STL, PNG layers). Voxelizing thin, wide copper is inefficient [S] |
| [FasterCap](https://github.com/ediloren/FasterCap) | 2-D/3-D capacitance, BEM with FMM/hierarchical | LGPL-2.1 → IN | 2019; CPU | FastCap-style deck |
| [Palace](https://github.com/awslabs/palace) electrostatic/magnetostatic | FEM (MFEM/libCEED) lumped C and L matrices, AMR | Apache-2.0 → IN | active; NVIDIA/AMD GPU, multi-GPU [P] | gmsh mesh; no KiCad path |
| [Elmer](https://github.com/ElmerCSC/elmerfem) | Static current conduction, magnetodynamics (Whitney), heat | GPL-2.0-or-later; ElmerSolver sources LGPL-2.1+ [P] → IN | active (2026-10) | kicad-cli XAO/STEP → Salome or gmsh → Elmer ("a bit tedious", [jrainimo](https://jrainimo.com/build/2024/11/oss-thermal-simulation-of-pcbs/)) |
| [padne](https://github.com/atx/padne) | KiCad-native 2.5-D FEM DC IR drop | GPL-3.0 → IN | active (2026-10) | Reads KiCad directly; schematic directives |
| [KiPI](https://github.com/drewsum/KiPI) | DC drop, AC PDN impedance, coupled noise | GPL-3.0 → IN | active (2026-10) | KiCad + YAML |
| [tm_board_thermal_fv.py](../../../tools/research/physics/tm_board_thermal_fv.py) (workstream 7) | Multi-layer 2-D FV thermal with via barrels and convection | ours | ~1 s at 0.5 mm, 2 layers ([thermal-physics](thermal-physics.md)) | Raster of copper per layer |
| Own 2.5-D FV IR drop | Sheet FV + SuperLU | ours | 40×30 mm pour: 27k cells 0.08–0.2 s, 109k 0.6–1.5 s, 436k 6–9 s factorization; 6–300 ms per extra right-hand side [C] | Raster of filled zones |

### F3: full-wave (minutes–hours)

| Tool | Method | Licence → action | Status, GPU | KiCad path |
|---|---|---|---|---|
| [openEMS](https://github.com/thliebig/openEMS) | EC-FDTD, Python/Octave | GPL-3.0+; CSXCAD LGPL-3.0 [P] → IN | active (2026-10-21). CPU SSE/multithread. **Unreleased GPU engine** `--engine=gpu`: HIP (AMD, NVIDIA via CUDA) and Metal, checked against a CPU reference backend ([CHANGELOG](https://github.com/thliebig/openEMS/blob/master/CHANGELOG.md)) [P] | gerber2ems, si-wrapper, pcbmodelgen, PCB_SI_Toolkit |
| [Meep](https://github.com/NanoComp/meep) | FDTD, MPI, adjoint inverse design | GPL-2.0-or-later [P] → IN | active; no GPU | None; photonics-oriented |
| [gprMax](https://github.com/gprMax/gprMax) 4.0 | FDTD | GPL-3.0 → IN | active; CUDA, OpenCL, Metal, MPI [P]; 1194 / 3405 Mcell/s on Kepler / Pascal ([2019 paper](https://repository.uwl.ac.uk/id/eprint/5755/)) [S] | None; GPR-oriented |
| [Palace](https://github.com/awslabs/palace) | FEM: eigenmode, driven (lumped/wave ports, adaptive fast sweep), transient | Apache-2.0 → IN | active; GPU [P] | gmsh |
| [EMerge](https://github.com/FennisRobert/EMerge) 3.0b | Python FEM, time-harmonic, AMR, direct solvers | GPL-2.0-or-later (source headers) [P] → IN | active (2026-10-22); GPU via cuDSS/SPARTA [P] | Gerber and ODB++ via its `emcad` add-on [P] |
| Elmer vector Helmholtz | FEM | GPL-2.0+ → IN | active | as above |
| [scuff-em](https://github.com/HomerReid/scuff-em) | Surface BEM | GPL-2.0+ headers → IN | stale (2018) | — |
| [necpp](https://github.com/tmolteno/necpp) / [xnec2c](https://github.com/KJ7LNW/xnec2c) | NEC2 thin-wire MoM | GPL-2 / GPL-3 → PROC | active | Cables and attached wires as common-mode antennas |
| [fdtdx](https://github.com/ymahlau/fdtdx) | JAX FDTD, autodiff, time-reversal gradients | MIT → IN | active; GPU/multi-GPU [P] | None; photonics scale |
| [ceviche](https://github.com/fancompute/ceviche), [flaport/fdtd](https://github.com/flaport/fdtd), [jax-fem](https://github.com/deepmodeling/jax-fem) | 2-D FDFD/FDTD autograd; PyTorch FDTD; differentiable FEM | MIT, MIT, GPL-3.0 → IN | ceviche stale (2023) | Prototyping differentiable physics |
| OpenFOAM ([openfoam.org](https://openfoam.org)) | FV CFD; `chtMultiRegionFoam` conjugate heat transfer for convection-limited parts | GPL-3.0 [S] → PROC | active; CPU/MPI | STEP → snappyHexMesh; hours per case [I]. Antmicro's FreeCAD/gmsh/CalculiX flow is the lighter thermal F3 ([evaluation-stack](../verification/evaluation-stack.md)) |
| Own numpy Yee | 3-D FDTD | ours | 20–46 Mcell-updates/s [C] versus openEMS 294 Mcell/s in a gerber2ems log ([README](https://github.com/antmicro/gerber2ems)) [P] | — |

### Circuit, channel and macromodel tools

| Tool | Role | Licence → action |
|---|---|---|
| ngspice | Embedded in KiCad's schematic simulator (op, DC, AC, transient, noise); lossy lines LTRA/TXL/CPL | Modified BSD core with GPL/LGPL exceptions per file ([Debian copyright](https://sources.debian.org/src/ngspice/24-1/COPYING)) [S] → check per component |
| [Xyce](https://github.com/Xyce/Xyce) | MPI-parallel SPICE for large back-annotated netlists | GPL-3.0 [P] → IN/PROC |
| [Qucs-S](https://github.com/ra3xdh/qucs_s) | GUI over ngspice/Xyce/Qucsator; S-parameter analysis | GPL-2 file, "or later" headers [I] → PROC |
| [scikit-rf](https://github.com/scikit-rf/scikit-rf) | Touchstone, de-embedding, `VectorFitting` with passivity test and enforcement | BSD-3 → IN |
| [SignalIntegrity](https://github.com/TeledyneLeCroy/SignalIntegrity) | S-parameter netlists, simulation, de-embedding | GPL-3.0-or-later [P] → IN |
| [PyBERT](https://github.com/capn-freako/PyBERT) | Serial-link and IBIS-AMI eye simulation | BSD [P] → IN |

Vector fitting is not push-button [C]. A damped 1-port PDN (the cavity plus 12 MLCCs, 600 points, 100 kHz–3 GHz, S referenced to 1 Ω) fits passively with 6 complex pairs + 2 real poles in 2–4 s and 9 pairs + 2 real in 3–7 s (rms 2×10⁻³ and 1×10⁻⁴). The bare, nearly lossless cavity (|S11| ≈ 1) took 6–76 s for 10–30 pairs at rms 1–2×10⁻², came out non-passive, and `passivity_enforce()` failed at default settings.

### KiCad bridges

| Bridge | What | Licence | State |
|---|---|---|---|
| [gerber2ems](https://github.com/antmicro/gerber2ems) | Gerbers + stackup + ports → openEMS → S-params | Apache-2.0 | active (2026-10) |
| [kicad-si-simulation-wrapper](https://github.com/antmicro/kicad-si-simulation-wrapper) | Slices nets and neighbours, places ports, shorts 0 Ω and big caps | Apache-2.0 | 2026-04; KiCad 9.0.x only |
| [pcbmodelgen](https://github.com/jcyrax/pcbmodelgen) | KiCad → openEMS Octave models | GPL-3.0 | stale (2023) |
| [KiCad Electrodynamic & Static Studio](https://github.com/ravid1323/KiCad-Electrodynamic-Static-Studio) | kipy extraction, headless openEMS, MNA DC, vector fitting | **no licence file** | REF only |
| [emcvisual](https://github.com/tombueng/emcvisual) | Biot–Savart near field with images; reads KiCad 6–10 | 0BSD-style | active |
| EMerge + `emcad` | Gerber/ODB++ → FEM | GPL-2.0+ | active |
| kicad-cli STEP/XAO/BREP → gmsh/Salome → Elmer, Palace, CalculiX | Meshing route for FEM | — | Works, multi-tool |
| KiCad core | ngspice simulator only. FEM-in-pcbnew proposal [#8398](https://gitlab.com/kicad/code/kicad/-/issues/8398) (April 2021, KiCad 5.99) [P]; "not much progress in 6 years" per a forum user [S]; no SI/PI roadmap ([forum](https://forum.kicad.info/t/future-plans-for-basic-signal-integrity-si-power-integrity-pi-funtionality/70585)) | GPL-3 | — |

No maintained KiCad → PEEC/FastHenry-deck exporter exists. That is the gap our physics graph fills ([physics-ir](physics-ir.md)).

### Learned surrogates

| Work | Result | Tag |
|---|---|---|
| CNN-Cap (Tsinghua; [arXiv 2107.06511](https://arxiv.org/abs/2107.06511)) | 2-D pattern capacitances: total C error < 1.3%, > 99.5% of couplings within 10%; 4693× faster than a 2-D field solver on a GPU server; retrained per process node | [S] |
| 3-D CNN-Cap / NAS-Cap ([arXiv 2408.13195](https://arxiv.org/html/2408.13195v1)) | < 5% error with ~99% probability, 191× faster than a random-walk solver; 4.1% of couplings > 10% error | [S] |
| ParaGraph (NVIDIA 2020, [page](https://research.nvidia.com/publication/2020-07_paragraph-layout-parasitics-and-device-parameter-prediction-using-graph-neural)) | GNN predicts pre-layout net parasitics from schematics, R² 0.772 | [S] |
| PDN-impedance DNN (Missouri S&T, [arXiv 2106.10693](https://arxiv.org/abs/2106.10693)) | > 1M random boards labelled by BEM; 0.1 s per board, > 100× faster than BEM, 10⁴× faster than full-wave | [S] |
| PCB thermal DeepONet ([POSTECH thesis](https://poasis.postech.ac.kr/handle/2014.oak/124072)); FNO EM surrogates (photonics) | Operator learning exists, but nothing open, PCB-generic and maintained | [S] |
| Libraries | [neuraloperator](https://github.com/neuraloperator/neuraloperator) (MIT), [PhysicsNeMo](https://github.com/NVIDIA/physicsnemo) (Apache-2.0), [DeepXDE](https://github.com/lululxvi/deepxde) (LGPL-2.1) | [P] |
| Ours: residual on MS2 vs black box | 300 PEEC labels, 1,200 held out: a log-linear correction of MS2 reaches median 3.5%, p95 9.8% (one outlier at 114%). The same model fitted to raw features reaches 28% and 100% [C] | [C] |

### Commercial references (calibration and literature only)

Ansys HFSS, SIwave and Q3D; Cadence Sigrity and Clarity; Siemens HyperLynx; Dassault CST; Keysight ADS/Momentum; Sonnet (free Lite tier); Simberian Simbeor; Flexcompute Tidy3D (cloud GPU FDTD). Use their published app notes and validation cases. Never put them in the loop.

## Recommendations for our system

- **Own the F1/F2 kernels; wrap F3.** Closed forms, image-plane PEEC, 2-D FD cross-sections and 2.5-D FV sheets are each under 300 lines and ms-fast ([sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py), [sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py)). Wrap openEMS (via gerber2ems/si-wrapper slices) and Palace for F3 [I].
- **Merge the three PEEC prototypes.** [sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py) (image plane, proxies), [pw_peec.py](../../../tools/research/physics/pw_peec.py) (workstream 4: nodal R + jωL with vias and capacitor bodies) and [fe_peec_plane.py](../../../tools/research/physics/fe_peec_plane.py) (workstream 5: meshed plane, slot crossings) share the same Grover kernels. Put one library behind the evaluator contract and keep the FastHenry decks as its regression tests [I].
- **Quasi-static default for anything electrically small** (largest dimension < λ/10 at the top frequency of interest). Hot loops, decap mounts and via fields go to PEEC, not FDTD [C/I].
- **Licences:** generate FastHenry decks for internal cross-checks only. Ship PyPEEC or our PEEC. Keep Ki-PIDA, Tidy3D and the unlicensed Studio as REF. Re-run the clone-and-grep audit before each release [I].
- **Treat every closed form as a function with a validity domain** (w/h, εr, frequency, geometry class). Refuse to evaluate outside it, or escalate (see [solver-ladder](solver-ladder.md)) [C].
- **GPU budget goes to F3 FDTD/FEM and to batched F1/surrogate evaluation**, not to 2-D solves that already take ms–s on CPU [I].

## Conflicts and open questions

- **FastHenry:** [physics-ir](physics-ir.md), [vocabulary](vocabulary.md) and [V4](../../ideas/original/verification.md) use it as a calibration solver. That is acceptable only as an internal, unshipped tool. Someone should ask FastFieldSolvers or MIT whether the 2003 FastCap-style grant also covers FastHenry. The FreeBSD "MIT" label suggests it might.
- **[evaluation-stack](../verification/evaluation-stack.md)** lists Ki-PIDA as T2 without an AGPL flag, and calls FastHenry/FastCap "MIT-origin".
- **Johnson's via formula** ([checkers-power](../rules/checkers-power.md) loop estimator) gives 2–6× the partial inductance of Rosa/Goldfarb-Pucel. Replace it with a loop model that includes the return via or plane.
- **Unverified:** OpenParEM licence and repository; openEMS GPU throughput (unreleased, no published numbers); Palace and EMerge PCB runtimes; whether ngspice's S-parameter analysis is exposed in KiCad.
- **Ideal-plane PEEC** is the high-frequency limit. Below roughly 1 MHz for 35 µm planes the return spreads out ([vo_return_spread.py](../../../tools/research/physics/vo_return_spread.py)), and image PEEC underestimates L.

## Sources

- research notes: [constraints_verification_benchmarks.md § Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md); [licensing.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- repos (licence files, source headers and READMEs read from shallow clones, 2026-10-22): see the table links.
- classic formulas: Hammerstad & Jensen, "Accurate models for microstrip computer-aided design", IEEE MTT-S 1980; Grover, *Inductance Calculations* (1946); Ruehli, IBM J. R&D 16(5), 1972; Hoer & Love, J. Res. NBS 69C, 1965; Goldfarb & Pucel, IEEE MGWL 1(6), 1991; Kamon, Tsuk & White, "FASTHENRY", IEEE T-MTT 42(9), 1994; Gustavsen & Semlyen (vector fitting), IEEE TPWRD 14(3), 1999.

See also: [solver-ladder](solver-ladder.md) · [simulation ideas](../../ideas/physics-first/simulation.md) · [physics-critics-catalog](physics-critics-catalog.md) · [physics-ir](physics-ir.md) · [reuse-matrix](../licensing/reuse-matrix.md) · [evaluation-stack](../verification/evaluation-stack.md)
