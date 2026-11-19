# Functional evaluation: what a board does, when its intent is unknown

Scope: judging whether a routed board works by simulating testbenches on ideal vs routed copper (`kae.sim`), and why today's routed-physics total cannot. Not here: format -> [intent-interchange](../architecture/intent-interchange.md); code and results -> [functional-evaluator](../architecture/functional-evaluator.md); geometric critics -> [physics-critics](physics-critics.md).
Keys: functional evaluator, kae.sim, testbench, ideal vs routed, layout effect, capability, paired comparison, verdict (pass, marginal, fail, unknown, incomplete, error), rail_dc, rail_step, cell, loop, i2c, pair, excitation inventory, radiator inventory, physics_total, min(u, 5), evaluator c3e877f84ac4

Tags: [M] measured in this repo; [I] inference.

## 1. The current evaluator [M]

`tools/kaeres/physics_board.py` runs `kae.route.critical_recheck.board_physics` and sums `min(u, 5)` per module (`kae.joint.scorecard.physics_total`), counting an unmeasured module as 3. It cannot say whether a board works. Evaluator `c3e877f84ac4`, 2026-10-27:

| Finding | Number |
|---|---|
| Kinds scored | `cell`, `path`, `decap`, `crystal`, `chain`. Coupling, thermal, cable CM, antenna exist only in placement terms ([place-terms](place-terms.md)); their total (`place_terms`) is stored, never reported |
| Evaluations with no module found (scored a perfect 0) | 1,308 of 5,529 (23.7%); 388 of 1,718 boards |
| Share of human boards' total that is the constant 3 | 46.8% (4,307 modules, none with an error) |
| Decap modules unmeasured | 48%; in a 40-board sample ~76% had every candidate cap below ownership 0.5, which `decap_pairs` drops (approximate: briefs rebuilt without schematic pin types) |
| Share of total by kind | decap 69%, ESD chain 24%, hot loop 3%, power path 2.5%, crystal 1.3% |
| Length, skew, diff-pair DRC violations | 6, 7, 32 of 11,758 boards; ordinary error counts; nothing reads the brief's `Zdiff` budgets |
| Copper connectivity (before the fix in `kae.route.copper`) | 353 falsely split nets on 150 boards, now 5 ([functional-evaluator §3](../architecture/functional-evaluator.md#3-extraction)) |

## 2. Principles

1. **Layout property × excitation.** Copper gives R, L, C, coupling, delay, resonances exactly; excitation (currents, edges, modes, frequencies) is an interval with a source; simulation multiplies them.
2. **Ideal vs routed.** Each test runs on the ideal circuit (the schematic: the floor copper can only worsen) and on routed copper (R, L, C, mutual L, coupling C) at every corner of its parameter intervals. Verdict from the routed run; layout effect = routed − ideal, no invented budget.
3. **Capability.** Where excitation is unknown, report what the layout tolerates (largest load, fastest mode, largest pull-up, fastest aggressor edge), e.g. "within 3% up to 7× the load prior", "bus capacitance 11 pF, so pull-ups up to 31 kΩ in Fast-mode". Absolute pass/fail only where a bound has a source.
4. **Paired comparison.** Two layouts of one board share the testbench, so guessed values cancel. The human board is a competitor, not ground truth (some corpus boards are unfinished), triaged by KiCad's own connectivity.
5. **Lexicographic report per category:** coverage, hard fails, capability, findings, layout effect, paired result. No blended total; a number for an optimizer is labelled as a choice ([physics-critics](physics-critics.md) §3).

## 3. Checks

| Category | Test | What it runs | Status |
|---|---|---|---|
| Power | `rail_dc` | loads at current priors from a source through the rail's copper (and series ferrites to the root rail); voltage at each load pin vs 3% (prior) | built |
| | `rail_step` | logic loads stepping in T_STEP with the board's decoupling (ESR, ESL); droop vs 5% (prior) | built |
| | `cell` | buck, boost, half-bridge, motor-driver phases: generic switch pair (or switch + rectifier) with body diodes and C_oss, inductor/winding as current source, off-board feeds behind 1 µH. Switch-node peak vs 85% of the next rating above 1.25 V_bus (prior); dissipation per corner, routed − ideal = layout loss | built |
| | `loop` | hot-loop inductance from the switch's bus pin through bus caps (shorted to ESR, ESL) to its ground pin; no switch model or bus voltage needed | built |
| | current capacity of necks and vias; flyback, buck-boost, charge pump, LDO, load-switch dissipation | IPC-2152-style limits; stand-ins per topology | planned |
| Signal | `i2c` | pull-up (or probe), pin capacitance, routed copper; 30–70% rise vs 1000/300/120 ns; with off-board pull-ups: bus capacitance and largest pull-up per mode | built |
| | `pair` | 50 Ω driver into each half; delay to every pin and skew | built |
| | crosstalk | aggressors from the excitation inventory into victims (sense, feedback, ADC inputs) through coupling C and mutual L; noise vs victim margin | planned |
| | return path | voids, reference changes, plane slots under nets with edges ([physics-critics-catalog](physics-critics-catalog.md) RET-*, PLANE-PERF) | planned (geometric) |
| Leakage, safety | leakage, creepage | high-impedance exposure vs surface resistivity; creepage and clearance vs working voltage | planned |
| EMI, RF | source to radiator; antenna feed | §4; feed loss and mismatch from the extracted line | planned |
| Thermal | hot spots, victims | dissipation from simulated currents ([thermal-physics](thermal-physics.md)) | planned |

Build order for planned checks: current capacity (converter loss and hot loops are built) → crosstalk victims → return path → leakage and creepage → inventories and source-to-radiator → antenna feed → thermal.

## 4. Excitations and radiators (planned)

Every source gets a trapezoid spectrum ([fields-emi-budget §1](fields-emi-budget.md#1-the-chain)). Switching cells add a ringing peak f_ring = 1/(2π√(L_loop·C_oss)), L_loop from routed copper.

| Source | Parameters and evidence |
|---|---|
| Switching regulators | f_sw from part or timing resistor, else ~0.3–3 MHz [I]; t_r, I, V_in |
| Crystals, oscillators | frequency from the value field |
| MCU clocks, digital buses | rates and edges by interface and logic family, 1–5 ns default [I] |
| High-speed interfaces | rate and rise time from the standard |
| PWM, motor, LED drivers, charge pumps | f, edge, current by part class |
| Radios | TX band and power; RX band and sensitivity |
| ESD and surge | IEC 61000-4-2 level 4, 37.5 A/ns |

Radiators: traces and stubs (λ/4 ≈ 14 cm at 300 MHz on FR-4); plane slots (half-wave); plane-pair cavities (100 mm at ε_r 4.5 ≈ 0.7 GHz); floating copper; cables at connectors (~30–300 MHz); on-board receivers. Regulator harmonics are spaced at f_sw, so what counts is the envelope or ringing band at each resonance × coupling × the resonance's Q, not exact coincidence.

## 5. Inputs, verdicts, unknowns

- **Unknown is a value, never a number:** nothing is imputed.
- Inputs are intervals with a source: human, board rule, datasheet, board value, schematic, standard, inferred, prior.
- Verdicts: pass (holds at every corner), fail (at none), marginal (otherwise), unknown (testbench names what is missing; values still reported), incomplete (test pins on separate copper islands), error (a measurement did not return). Each carries its reasons.
- Questions for research (the only ones needing an LLM): inputs whose range flips a verdict, unknowns, verdicts resting on priors.
- Uncertain structure (ownership, sources, loads) is a correctable testbench choice, recorded as inferred.
- Coverage first: a board with no recognised structure is "unevaluated".

## 6. Trusting the evaluator

- **Analytic tests:** extracted R and L of a track match closed forms; simulated DC drop = I × R within 5% ([test_sim.py](../../../kae/tests/test_sim.py)).
- **Mutation benchmark** ([physics-critics-validation](physics-critics-validation.md)): DRC-neutral planted faults with oracle deltas and benign twins, before any test becomes a reward.
- **LLM subset:** 10–30 stratified boards where an agent replaces priors with cited facts (cached per part number); measures the automatic testbench's errors, checks cheap verdicts, allows absolute pass/fail there. Pilot on one board, measure cost, then size the subset.
- **Robust conclusions only:** a method ranking is reported only if it holds across the prior ranges.

Deployment: add `kae.sim` to kaeres as a new evaluator beside the legacy total, never inside cp1, cpk or `score.py` (CLAUDE.md); re-run routed-physics baselines under the new copper connectivity.

## Open questions

- Human copper as intent evidence would bias place and joint tasks toward the human's choices.
- No exchange rate across categories without stated intent.
- Edge-rate priors dominate crosstalk and EMI: a 1–5 ns interval spans up to 14 dB above both spectral corners.
- Stand-in fidelity (ideal switches, current-held inductor) caps converter tests ([functional-evaluator §9](../architecture/functional-evaluator.md#9-cell-stand-in-and-numerics)).

## Sources

- In-repo: kaeres index, evaluator `c3e877f84ac4` (kae `dfe6260`, `physics_board.py` `cd4ab2e`), 2026-10-27; `kae.sim` runs, 2026-10-28.
- NXP UM10204, I2C-bus specification (rise-time limits, pin capacitance).
- Related: [physics-set-coverage](physics-set-coverage.md), [physics-ir](physics-ir.md), [comprehension](comprehension.md), [schematic-to-physics](schematic-to-physics.md), [fields-emi-budget](fields-emi-budget.md).
