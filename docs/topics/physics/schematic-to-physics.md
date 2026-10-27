# Simulating the schematic: net physics, sensitivities and budgets

**TL;DR**
- **Simulate the schematic before any geometry.** Run ngspice or Xyce with vendor models or behavioural stand-ins and measure each net's and branch's physical character: swing, dv/dt, current, di/dt, spectrum envelope, impedance level and susceptibility. This replaces name-based net roles with measured aggressor strength and victim susceptibility per band [I].
- **Susceptibility is nearly free.** One adjoint solve per output and frequency gives the transfer from every candidate injection site. SPICE's `.noise` analysis is that adjoint method (Rohrer et al. 1971). Our check reproduces direct AC transfer functions to 6e-13 and ngspice 42's per-device `.noise` output to four digits [C].
- **A layout is a perturbation.** Extract parasitics with fast estimators, back-annotate them into a physical netlist (ground becomes many nodes), re-simulate, and score the deviation from the floor-parasitic design. The **layout invisibility index** LII = max over outputs of deviation ÷ budget is the master objective [I].
- **Budgets come from sensitivities.** With worst-case summation and a cost k_i/p_i for squeezing parasitic p_i, the optimal split gives each structure a share of the budget proportional to √(k_i·s_i). Linearised budgets hold only near the operating point: 1.01 vs 1.05 nH exact for a 12 V buck hot loop, but badly wrong for a slow 48 V bridge [C].
- **Limits:** missing or encrypted models, switching nonlinearity and rectification, corners, and cost. The fast path is AC/adjoint sensitivities in the inner loop, closed forms for edges, re-simulation at checkpoints, and field solves only for finalists [I].

## Key facts

### What the schematic simulation measures ("net passport")

| Quantity | Analysis | Feeds |
|---|---|---|
| DC voltage and branch current | operating point | IR-drop budgets, copper width, I²R heat, injections for the plane DC-flow solve |
| Swing ΔV and peak dv/dt | transient | C·dv/dt aggressor strength; HV field (V/mm) |
| Branch current and peak di/dt | transient | L·di/dt aggressor strength; **hot-loop membership measured, not looked up** |
| Spectrum envelope | FFT of one period, or a trapezoid fit with corners 1/(π·τ) and 1/(π·t_r) | bands, EMI proxies, spur maps |
| Node impedance \|Z(f)\| | AC, 1 A injected | victim susceptibility to capacitive coupling; "is this node high-Z?" |
| Transfer H_k(f) from site k to each output | AC adjoint or `.noise` | sensitivities, coupling budgets |
| Ripple, PSRR, loop gain | averaged-model AC, transient | supply-impedance and PDN budgets |

Hot-loop membership is a good example. [hot-loops](../rules/power/hot-loops.md) derives it per topology by hand. In simulation, the branches whose current steps at each edge are the ones with large di/dt, so the same table falls out of a transient run, including for topologies no table covers [I].

### Where models come from

| Source | Coverage | Notes |
|---|---|---|
| Vendor SPICE models | many regulators, op-amps, references, FETs | ngspice loads many PSpice/LTspice models with `set ngbehavior=ltpsa`, "not 100% effective" ([Qucs-S help](https://qucs-s-help.readthedocs.io/en/latest/subckts-and-ext-models/spice-models/spice-troubleshooting-and-compatibility-modes.html)) [S]. Encrypted models "cannot be used by open source ngspice" ([ngspice models](https://ngspice.sourceforge.io/modelparams.html)) [S] |
| IBIS | MCU, FPGA and PHY I/O: edge rates, drive, pin parasitics | KiCad's simulator reads IBIS ([net-role-classification](../llm/net-role-classification.md)) [P] |
| Behavioural stand-ins | switch + dead time + Coss for converters; averaged models for regulation; Butterworth–Van Dyke crystal; current-profile sources for digital loads; sensor bridges | the LLM picks them; a validation test against datasheet curves must pass first |
| Datasheet envelopes | anything else | (V, I, t_r, f) with intervals; propagate the intervals into budgets |

Simulators: ngspice (KiCad's engine; per-file licences, check each, see [reuse-matrix](../licensing/reuse-matrix.md)) and Xyce (GPL-3.0 per Sandia's [About Xyce](https://xyce.sandia.gov/about-xyce/); its binary installers add proprietary compact models, so build from source) [S]. Both are usable from our GPL-3.0-or-later code. ngspice 42 ran here in batch mode from the Ubuntu package, unpacked without root [C]. Vendor models stay under vendor terms; never redistribute them [I]. Simulator selection: [open-solvers](open-solvers.md).

### Susceptibility from one adjoint solve

For a linear(ized) network Y(f)·x = b with output y = eᵀx, the transfer from an injection vector b_k is eᵀY⁻¹b_k = λᵀb_k, where Yᵀλ = e. One transposed solve per output gives every site (Director and Rohrer, "The generalized adjoint network and network sensitivities", 1969) [S]. SPICE's noise analysis is built on it: the adjoint-network method of Rohrer et al. (IEEE JSSC 1971) is "the basis of computer-aided noise analysis in most, if not all circuit simulation routines" ([Vasudevan, IIT Madras](https://www.ee.iitm.ac.in/vinita/pdf/ee2015/adjoint-final.pdf)) [S].

**Trick:** put a fictitious noise resistor at each candidate site (large and shunt for current injection, small and series for voltage injection) and run one `.noise`. With a summary interval, ngspice writes `onoise_<device>`, and |H_k| = onoise_k ÷ (that resistor's own noise density) [C].

Demonstration on a bridge-sensor front end for a 24-bit ADC, with an RC anti-alias filter (1 kΩ, 100 nF differential, 1.0/1.1 nF common mode) and a 1 mΩ + 5 nH sensor-to-ADC ground path. The output is v(AINP) − v(AINN) ([dr_noise_adjoint.py](../../../tools/research/physics/dr_noise_adjoint.py)) [C]:

| Injection site (what layout couples there) | \|H\| at 10 Hz | \|H\| at 500 kHz | Allowed coupling at 500 kHz for 9.3 nV |
|---|---|---|---|
| current into AINP, ADC side (C·dv/dt from a 12 V switch node) | 1.1 kΩ | 1.65 Ω | C_m ≤ 0.23 fF |
| current into the P filter input, sensor side | 88 Ω | 0.13 Ω | C_m ≤ 2.9 fF |
| series voltage in the AINN trace (M·di/dt into the input loop) | 1.0 | 1.4e-3 | M ≤ 1.7 pH (fundamental) |
| series voltage in the ground path (shared impedance, common mode) | 6.8e-6 | 1.3e-4 | M ≤ 18 pH |

Three things this shows at once:
- The ADC side of the filter is about 10× more exposed than the sensor side, so the expert habit "filter at the ADC" gets a number.
- The common-mode path reaches the output only through the 10% capacitor mismatch, about 78 dB of rejection at 500 kHz. Tighter C0G matching is a circuit lever that buys layout freedom.
- The budgets are before the ADC's digital filter. They bind only where switching harmonics alias into the passband (see [worked-thought-experiments](worked-thought-experiments.md) case C).

### Layout as a perturbation: the physical netlist

Replace each schematic net with a graph: pins → trace segments → vias → plane nodes. Ground becomes many nodes, because the schematic's single ground symbol hides every shared impedance. Insert elements from fast estimators, then calibrate them against T3 solvers before trusting them as rewards ([evaluation-stack](../verification/evaluation-stack.md)).

| Element | T0 estimator | Calibrate against |
|---|---|---|
| trace R | ρℓ/(w·t), with IPC-2152 heating | measurement |
| partial L of a trace over a plane | per-length L = Z0·√ε_eff / c, or μ0·h·ℓ/w for wide strips | FastHenry/PEEC |
| loop L | area plus plane depth, anchored on AN-139, SNVA803 and EPC data ([hot-loops](../rules/power/hot-loops.md)) | FastHenry, openEMS |
| via L | Johnson: 5.08·h·[ln(4h/d)+1] nH (h, d in inches) | 3-D solver |
| loop-to-loop M | Neumann integral with plane images ([dr_coupling_oracles.py](../../../tools/research/physics/dr_coupling_oracles.py)) | FastHenry |
| C to plane, mutual C | ε·A/h; K = 1/(1+(s/h)²) times self capacitance | 2-D field solver |
| plane spreading R | 2-D finite-difference Laplace | — |
| capacitor mounting L | pads + vias + depth to the plane pair | vendor S-parameters |
| thermal R and ∇T | fin model in the board sheet; finite volume | FEM, IR camera |

Mutual inductances go in as SPICE `K` couplings; capacitive coupling as capacitors between net graphs; thermal networks as electrical analogues in the same run. The [solver ladder](solver-ladder.md) picks the solver for each, and the [physics critics](physics-critics-catalog.md) read them.

### Outputs, deviation and the invisibility index

| Output | Analysis | Parasitics that move it |
|---|---|---|
| switch-node peak and ringing | transient | hot-loop L, Coss, damping |
| output ripple and load-step response | AC + transient | capacitor ESL/ESR, mounting L, plane R |
| supply noise at a pin, PSRR | AC | PDN impedance ([decoupling-pdn](../rules/decoupling-pdn.md)) |
| ADC offset, noise, SNR | DC, AC, noise | shared R, M, C, ∇T (thermal EMF) |
| jitter | noise at threshold ÷ slew | coupling into clock nets |
| eye and loss | T-line models, S-parameters | impedance, stubs, vias |
| radiated proxy, differential mode | Ott: E = 263e-16·f²·A·I/r (V/m; f in Hz, A in m², r in m; includes ground reflection) [S] | loop area × current |
| radiated proxy, common mode | Ott: E = 12.6e-7·f·L·I_cm/r [S]; CM voltage between connector references | plane partial L × current crossing between connectors |
| RF desense | spur power at the antenna port vs sensitivity | clock harmonics × isolation |

Ott's constants are quoted via a [patent citing Ott](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/5157531); check the textbook before relying on the units.

**Layout invisibility index.** LII = max_y |y(layout) − y(floor)| ÷ B_y over all outputs y, where "floor" is the schematic simulated with only the unavoidable parasitics (packages, minimum mounting). Comparing against an ideal zero-parasitic netlist would make budgets infeasible by construction. LII ≤ 1 means every output is in budget. The joint optimizer uses the same ratios through its barrier φ(spend/budget) ([joint-place-route](joint-place-route.md)), and the per-output ratios are the ledger's "spent" column ([intent-and-why I1](../../ideas/original/intent-and-why.md), [physics-ir](physics-ir.md)) [I].

### Budgets from sensitivities

First order: Δy ≈ Σ_i s_i·p_i ≤ B, with s_i = ∂y/∂p_i from the adjoint and p_i the parasitic of structure i. Squeezing an inductance or a coupling capacitance costs roughly area or distance in inverse proportion, so take cost c_i = k_i/p_i.
- **Worst-case sum.** Minimizing Σ k_i/p_i subject to Σ s_i·p_i = B gives p_i ∝ √(k_i/s_i). Each structure's spend s_i·p_i is a share of B proportional to √(k_i·s_i).
- **Independent random contributions (RSS).** Spend is proportional to (k_i·s_i)^(1/3).
- **Several outputs.** Each parasitic takes the tightest of its per-output limits, per band.

Highly sensitive, costly structures get a larger share; cheap ones are squeezed. This formula is the allocation step of the I1 ledger [I].

Demonstration, switch-node overshoot vs commutation-loop inductance with an erf-shaped edge, ring Q = 8 and no reverse recovery ([dr_switch_cell_budget.py](../../../tools/research/physics/dr_switch_cell_budget.py)) [C]:

| Case | Allowed peak | Exact budget | Closed form | Linearised (at) |
|---|---|---|---|---|
| 12 V buck, Coss 120 pF, t_sw 1.5 ns, 2 A | 17 V (0.85 × 20 V abs max, 13.2 V input) | 1.05 nH | 1.36 nH | 1.01 nH (at 0.8 nH) |
| 48 V bridge, Coss 700 pF, t_sw 15 ns, 20 A | 80 V (0.8 × 100 V) | not binding up to 40 nH | 46 nH | 16.5 nH (at 10 nH) |

- The closed form is L_max ≈ σ²/(2·C·ln(1/a′)), with σ = t_sw/2.563, a the allowed overshoot fraction and a′ = a·e^(π/2Q). Overshoot is a sigmoid in L: negligible while the ring period is short compared with the edge, then rising towards 100%. This is the shape EPC measured (30% at 0.4 nH, 100% at 1.6 nH on eGaN; [hot-loops](../rules/power/hot-loops.md)) [P].
- Above about V_in·t_sw/I_L the loop inductance itself limits di/dt, and the voltage-driven model stops applying.
- The square-root split of the buck's 1.05 nH, with a fixed 0.3 nH package and relative squeeze costs 1 : 0.5 : 2, gives C_IN mounting 0.24, vias 0.17 and lateral loop 0.34 nH [C].
- The half-bridge row is the more useful lesson. With 15 ns edges, overshoot is not what binds, so its loop budget must come from another output: the ring at 45–63 MHz feeding common-mode current through the heatsink, or the shunt signal ([worked cases](worked-thought-experiments.md)).

**Nonlinearity.** Use a sensitivity only inside a trust region around the point where it was computed; re-linearise after every optimizer round. For edges, prefer the closed form or a short transient [I].

### Cost and the fast path

| Analysis (netlist of 100–500 nodes) | Cost | Where it runs |
|---|---|---|
| operating point; AC sweep with adjoint; `.noise` | ms | inner loop, every candidate |
| switching-cell transient (100 ns) | < 1 s (our ODE) | per structure, per round |
| converter transient over ms with ns edges | s–min | checkpoints |
| periodic steady state / harmonic balance (Xyce `.HB`) | s–min | checkpoints |
| field solves (FastHenry, openEMS, FEM thermal) | min–h | finalists, calibration |

The fast path:
1. Precompute sensitivities and closed forms. The optimizer sees only spend models and linear or closed-form maps to output deviation.
2. Separate time scales: averaged models for regulation, switching-cell models for edges, and linear time-invariant networks driven by trapezoid sources for EMI.
3. Re-simulate the back-annotated netlist at checkpoints and update the sensitivities.
4. Cache sensitivities per block type, so a buck seen once warm-starts the next one.

## Recommendations for our system

1. Add a `characterize` stage that writes a net/branch passport and an output list with budgets; the human confirms the outputs, not the passport [I].
2. Implement susceptibility with a numpy MNA adjoint (ms per frequency), and cross-check with ngspice `.noise` on every new block type [C demo].
3. Build the physical-netlist back-annotator (pins as nodes, ground as many nodes, K couplings) as a shared service for critics and optimizer [I].
4. Use LII as the master physics objective and per-output ratios as the ledger's spend; allocate budgets with the √(k·s) rule, and log the allocation as a derivation trace (I2) [I].
5. Every model and stand-in passes an LLM-written validation test (datasheet efficiency, ripple, edge rate within tolerance) before its sensitivities are used ([V1](../../ideas/original/verification.md)) [I].

## Conflicts and open questions

- **Validation ≠ simulation**: 10.7% of LLM-built circuits failed a topology validator yet ran in ngspice, and 4.7% passed it but failed in ngspice ([block-recognition](../llm/block-recognition.md)) [P]. A model that runs is not a model that is right.
- Linear sensitivities miss rectification (EMI rectified by op-amp inputs into DC offsets) and saturation. Flag op-amp and PGA inputs, and use EMIRR data or a transient with the RF tone.
- Encrypted vendor models block the ngspice route for many power ICs; stand-ins must be validated against datasheet curves, and their uncertainty widens budgets.
- How often a full schematic simulates at all is unknown; expect to simulate blocks, not boards.
- Estimator errors in the parasitic table are uncalibrated; every one needs a T3 comparison before it steers an optimizer.

## Sources

- Rohrer et al., "Computationally efficient electronic-circuit noise calculations", IEEE JSSC 1971; Director and Rohrer, IEEE Trans. Circuit Theory 1969 (both via [Vasudevan](https://www.ee.iitm.ac.in/vinita/pdf/ee2015/adjoint-final.pdf) and [CMU bio](https://www.ece.cmu.edu/directory/bios/rohrer-ronald.html)) [S]
- ngspice: [ANALYSES](https://sources.debian.org/src/ngspice/26-1/ANALYSES), [models and encryption](https://ngspice.sourceforge.io/modelparams.html) [S]; Xyce: [About Xyce](https://xyce.sandia.gov/about-xyce/), [Sensitivity Analysis in Xyce](https://www.sandia.gov/research/publications/details/sensitivity-analysis-in-xyce-2016-09-01/) [S]
- EPC and TI loop data via [hot-loops](../rules/power/hot-loops.md) [P]
- research notes: [netlist_datasheet_understanding.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)
- our scripts: [dr_noise_adjoint.py](../../../tools/research/physics/dr_noise_adjoint.py), [dr_switch_cell_budget.py](../../../tools/research/physics/dr_switch_cell_budget.py), [dr_coupling_oracles.py](../../../tools/research/physics/dr_coupling_oracles.py) [C]

See also: [design-reasoning-architecture](design-reasoning-architecture.md), [worked-thought-experiments](worked-thought-experiments.md), [solver-ladder](solver-ladder.md), [physics-critics](physics-critics-catalog.md), [reasoning ideas](../../ideas/physics-first/reasoning.md), [net-role-classification](../llm/net-role-classification.md)
