# Digest: physics-first placement and routing

Executive statements from the physics-first pass (eleven workstreams). Every statement links to the topic doc that holds the numbers, sources and caveats. The philosophy is in [physics/README](../topics/physics/README.md); the ~650 ideas are in the [physics-first catalog](../ideas/physics-first/README.md). [C] means computed by our scripts in `tools/research/physics/`.

## The idea
- **A layout is what the schematic leaves out:** a parasitic R, L, M and C network, field structures, heat paths and a manufactured object. Physics-first layout makes it invisible to the circuit and the outside world, within budgets in physical units. → [physics/README](../topics/physics/README.md), [schematic-to-physics](../topics/physics/schematic-to-physics.md)
- **About 160 rules reduce to 12 quantities:** L, M, Cm, R, Z, Bal, Vcm, Res, Ins, Th, Mech, Fab. The electrical ones come from four PEEC primitives. Rules fail by regime, not direction. → [rule-basis-set](../topics/physics/rule-basis-set.md)
- **Most rules are cheap to replace:** 143 of 160 need only a closed form, a 2-D solve, PEEC, a thermal network or SPICE; 8 need full-wave. → [rule-basis-set](../topics/physics/rule-basis-set.md), [genealogy: power](../topics/physics/rule-genealogy-power-analog-thermal.md), [SI/EMI/RF](../topics/physics/rule-genealogy-si-emi-rf.md), [routing/DFM](../topics/physics/rule-genealogy-routing-style-dfm.md)

## The language and the reasoning
- **12 atoms and 5 value types:**
  - Atoms: Port, Node, Loop, Body, Reference, Channel, Cavity, Discontinuity, Antenna, Heat path, Barrier, Coupling.
  - Value types: Spectrum, Sensitivity, Budget, Band, Regime.
  - A net is half a port: every port names its return.
  
  → [vocabulary](../topics/physics/vocabulary.md)
- **`pcb-intent/0.3` adds bands, symbols, physics entities and operators to 0.2.** `intent.yaml` holds what is required, `ledger.json` what is observed. The LLM never writes geometry or spend. → [physics-ir](../topics/physics/physics-ir.md), [examples](../topics/physics/physics-ir-examples.md)
- **Simulate the schematic first.** Measured dv/dt, di/dt and spectra replace name-based roles. SPICE `.noise` gives every susceptibility in one adjoint solve. Budgets are allocated in proportion to √(cost × sensitivity), and priority goes to least slack (τ). → [schematic-to-physics](../topics/physics/schematic-to-physics.md), [design-reasoning-architecture](../topics/physics/design-reasoning-architecture.md)
- **Ask which output binds.** In the four worked cases the physics-first answer differs from the rules: a 0.1 mm prepreg, heatsink common-mode current, plane gradients for a 24-bit ADC, the slew plan for an antenna. → [worked-thought-experiments](../topics/physics/worked-thought-experiments.md)

## What the physics says
- **Power: classify copper by waveform.** Width trades L, C and R against each other; only length lowers all three. Near a plane, loop L follows height × squares, not area (equal-area loops differ 1.7×) [C]. → [power-copper](../topics/physics/power-copper.md), [pdn-and-commutation](../topics/physics/pdn-and-commutation.md)
- **Pours, vias and decaps:**
  - Widen pour entries first: 31% of the loss sits within 3 mm of the pads [C].
  - Via fields conduct at their edges.
  - 4 vias at 0.6 mm pitch give 0.71× one via's inductance, not 0.25× [C].
  - Internal-vertical hot loops are ~3.5× lower in L than lateral ones [C].
  
  → [pdn-and-commutation](../topics/physics/pdn-and-commutation.md), [cross-domain-lessons](../topics/physics/cross-domain-lessons.md)
- **SI/EMI: one metric, ΔZ_ret × I(f), replaces about a dozen plane rules.** In the EMI chain topology beats tweaks by 20–40 dB. The 1 mV and 5 µA rules are one rule. → [fields-si-emi](../topics/physics/fields-si-emi.md), [fields-emi-budget](../topics/physics/fields-emi-budget.md)
- **Geometry is regime-gated.** Corners and arcs are cosmetic for SI above ~30 ps edges; pads, stubs and vias are not. Fibre weave justifies angled routing. Pad voids are solved per stackup. → [rf-geometry](../topics/physics/rf-geometry.md)
- **Thermal:** a board is a fin with a spreading length of 8 mm (bare FR-4) to 38–64 mm (copper). A kernel plus edge images scores placements within ~2% [C]. → [thermal-physics](../topics/physics/thermal-physics.md)
- **HV and manufacturing:**
  - HV corner fields scale as (g/r)^(1/3).
  - Altitude factors are air-pressure ratios.
  - Fab limits decompress into etch, plating, lamination, drilling, soldering and stress physics.
  
  → [hv-and-manufacturing-physics](../topics/physics/hv-and-manufacturing-physics.md)

## The machine
- **Placement and routing in one optimizer:**
  - The state carries topology: part poses, route homotopy classes, layers and vias.
  - Rubber bands re-tighten as parts move.
  - Congestion and physics prices act as placement forces.
  - LNS windows repair parts and copper together.
  
  → [joint-place-route](../topics/physics/joint-place-route.md), [experiment](../topics/physics/joint-place-route-experiment.md)
- **Physics enters as spend models with gradients.** One adjoint solve prices every copper edit. Topology optimization gives pours shaped by physics, with fab rules as filters inside the optimizer: −14.5% loss at equal area [C]. → [physics-in-the-loop-optimization](../topics/physics/physics-in-the-loop-optimization.md), [copper-shape-synthesis](../topics/physics/copper-shape-synthesis.md)
- **Fidelity ladder F0–F4 plus surrogates, escalated on value of information:**
  - Numpy PEEC agrees with FastHenry within 1.3% at ~1 ms [C].
  - Residual surrogates reach 3.5% median error from 300 labels [C].
  - FastHenry is internal-only (non-commercial notice).
  
  → [solver-ladder](../topics/physics/solver-ladder.md), [open-solvers](../topics/physics/open-solvers.md)
- **A separate physics scorecard, never blended into cp1/cpk.** A DRC-equivalent mutation benchmark provides the ground truth. The prototype found 31/31 planted faults with 0/7 false alarms on 4 boards (same author for critic and faults). → [physics-critics](../topics/physics/physics-critics.md), [catalog](../topics/physics/physics-critics-catalog.md), [validation](../topics/physics/physics-critics-validation.md)
- **Cross-domain transplants:** stream functions, transfer length, Murray-type width laws, screening lengths and power-module commutation cells. → [cross-domain-lessons](../topics/physics/cross-domain-lessons.md)
