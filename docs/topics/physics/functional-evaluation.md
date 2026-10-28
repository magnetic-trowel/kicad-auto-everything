# Functional evaluation: what a board does, when its intent is unknown

**TL;DR**
- **Today's routed physics score cannot say whether a board works.** It sums capped utilizations of five module kinds and counts an unmeasured module as 3. Half of a human board's total is that constant, and a quarter of evaluations find nothing and score a perfect 0 [M].
- **Judge function by simulation.** A testbench states the operating conditions as SPICE. Each test runs on the ideal circuit and on the routed copper (R, L, C, mutual L, coupling C), at every corner of its parameter intervals. The verdict comes from the routed run. The layout's effect is routed minus ideal.
- **Report capability and distance from ideal, not pass/fail against guessed budgets.** For example: "within 3% up to 7× the load prior", "bus capacitance 11 pF, so pull-ups up to 31 kΩ in Fast-mode". Absolute pass/fail applies only where a bound has a source.
- **Unknown is a value, never a number.** Every test is pass, marginal, fail, unknown, incomplete or error, with its reasons. Nothing is imputed.
- **Compare layouts in pairs on the same board and testbench.** Guessed values cancel, so the comparison holds even when the human board is poor; some corpus boards are unfinished.

Tags: [M] measured in this repo; [I] inference. Format: [intent-interchange](../architecture/intent-interchange.md). Code and results: [functional-evaluator](../architecture/functional-evaluator.md). What to measure on routed copper beyond circuits: [physics-critics](physics-critics.md).

## Key facts

### 1. The current evaluator [M]

`tools/kaeres/physics_board.py` runs `kae.route.critical_recheck.board_physics` and sums `min(u, 5)` per module (`kae.joint.scorecard.physics_total`). Evaluator `c3e877f84ac4`, 2026-10-27:

| Finding | Number |
|---|---|
| Kinds scored | `cell`, `path`, `decap`, `crystal`, `chain`. Coupling, thermal, cable common mode and antenna exist only in the placement terms ([place-terms](place-terms.md)); their total (`place_terms`) is stored, never reported |
| Evaluations with no module found (scored 0) | 1,308 of 5,529 (23.7%); 388 of 1,718 boards |
| Share of human boards' total that is the constant 3 | 46.8% (4,307 modules, none with an error) |
| Decap modules unmeasured | 48%. In a 40-board sample, about 76% had every candidate capacitor below ownership 0.5, which `decap_pairs` drops (approximate: briefs rebuilt without schematic pin types) |
| Share of the total by kind | decap 69%, ESD chain 24%, hot loop 3%, power path 2.5%, crystal 1.3% |
| Length, skew and diff-pair DRC violations | 6, 7 and 32 of 11,758 boards; ordinary error counts. Nothing reads the brief's `Zdiff` budgets |
| Copper connectivity (before the fix in `kae.route.copper`) | `NetGraph` split 353 nets on 150 boards that KiCad reports connected (overlapping round track ends, pours with distant contact clusters, jumper pads, net copper shapes); now 5 |

### 2. Principles

1. **Layout property × excitation.** The copper gives R, L, C, coupling, delay and resonances exactly. The excitation (currents, edges, modes, frequencies) is an interval with a source. Simulation multiplies the two.
2. **Ideal against routed.** The ideal run is the schematic: the floor the copper can only worsen. "Routed minus ideal" is the layout's effect, with no invented budget.
3. **Capability:** where the excitation is unknown, report the excitation the layout tolerates (largest load, fastest mode, largest pull-up, fastest aggressor edge).
4. **Paired comparison:** two layouts of one board share the testbench. The human board is a competitor, not ground truth, and is triaged by KiCad's own connectivity.
5. **Lexicographic report, per category:** coverage, hard fails, capability, findings, layout effect, paired result. No blended total; a number for an optimizer is labelled as a choice ([physics-critics](physics-critics.md) §3).

### 3. Checks

| Category | Test | What it runs | Status |
|---|---|---|---|
| Power | `rail_dc` | loads at their current priors from a source through the rail's copper (and series ferrites to the root rail); voltage at each load pin against 3% (prior) | built |
| | `rail_step` | logic loads stepping in T_STEP with the board's decoupling (ESR, ESL); droop against 5% (prior) | built |
| | `sw` (buck) | switches in the controller's place, inductor as a current source, C_oss; switch-node peak against 85% of the next rating above 1.25 V_in | built (buck only) |
| | converter loss curve, current capacity of necks and vias | I²R and ½·L·I²·f_sw from the same circuits; IPC-2152 style limits | planned |
| Signal | `i2c` | the pull-up (or a probe), pin capacitance, routed copper; 30–70% rise against 1000/300/120 ns; with off-board pull-ups, bus capacitance and the largest pull-up per mode | built |
| | `pair` | a 50 Ω driver into each half; delay to every pin and skew | built |
| | crosstalk | aggressors from the excitation inventory into victims (sense, feedback, ADC inputs) through coupling C and mutual L; noise against the victim's margin | planned |
| | return path | voids, reference changes and plane slots under nets with edges ([physics-critics-catalog](physics-critics-catalog.md) RET-*, PLANE-PERF) | planned (geometric) |
| Leakage, safety | leakage, creepage | high-impedance exposure against surface resistivity; creepage and clearance against working voltage | planned |
| EMI, RF | source to radiator; antenna feed | §4; feed loss and mismatch from the extracted line | planned |
| Thermal | hot spots, victims | dissipation from the simulated currents ([thermal-physics](thermal-physics.md)) | planned |

### 4. Excitations and radiators (planned)

**Excitation inventory.** Every source gets a trapezoid spectrum: flat to 1/(π·τ), −20 dB/decade to 1/(π·t_r), −40 dB/decade beyond. Switching cells add a ringing peak at f_ring = 1/(2π√(L_loop·C_oss)), with L_loop from the routed copper.

| Source | Parameters and evidence |
|---|---|
| Switching regulators | f_sw from the part or its timing resistor, else ~0.3–3 MHz [I]; t_r, I, V_in |
| Crystals, oscillators | frequency from the value field |
| MCU clocks, digital buses | rates and edges by interface and logic family, 1–5 ns default [I] |
| High-speed interfaces | rate and rise time from the standard |
| PWM, motor, LED drivers, charge pumps | f, edge, current by part class |
| Radios | TX band and power; RX band and sensitivity |
| ESD and surge | IEC 61000-4-2 level 4, 37.5 A/ns |

**Radiator inventory:**
- traces and stubs (λ/4, about 14 cm at 300 MHz on FR-4);
- plane slots (half-wave);
- plane-pair cavities (100 mm at ε_r 4.5 ≈ 0.7 GHz);
- floating copper;
- cables at connectors (~30–300 MHz);
- on-board receivers.

A regulator's harmonics are spaced at f_sw, so what counts is the envelope or the ringing band at each resonance × coupling × the resonance's Q, not exact coincidence.

### 5. Gaps

1. **Inputs are intervals with a source:** human, board rule, datasheet, board value, schematic, standard, inferred, or prior.
2. **Verdicts:**
   - pass: holds at every corner;
   - fail: holds at none;
   - marginal: otherwise;
   - unknown: the testbench says what is missing; values are still reported;
   - incomplete: the test's pins sit on separate copper islands;
   - error: a measurement did not return.
3. **Questions:** inputs whose range flips a verdict, unknowns, and verdicts resting on priors are listed for research, so only those need an LLM.
4. **Uncertain structure** (ownership, sources, loads) is a testbench choice anyone can correct, and is recorded as inferred.
5. **Coverage comes first.** A board with no recognised structure is "unevaluated".

### 6. Trusting the evaluator

- **Analytic tests:** the extracted R and L of a track match the closed forms, and the simulated DC drop equals I × R within 5% ([test_sim.py](../../../kae/tests/test_sim.py)).
- **Mutation benchmark** ([physics-critics-validation](physics-critics-validation.md)): DRC-neutral planted faults with oracle deltas and benign twins, before any test becomes a reward.
- **LLM subset:** 10–30 stratified boards where an agent replaces priors with cited facts. It measures the automatic testbench's errors, checks the cheap verdicts, and allows absolute pass/fail there. Facts are cached per part number.
- **Robust conclusions only:** a method ranking is reported only if it holds across the prior ranges.

## Recommendations for our system

1. Use `kae.sim` as the functional evaluator. Add it to kaeres as a new evaluator beside the legacy total, and never inside cp1, cpk or `score.py` (CLAUDE.md).
2. Build the planned checks in this order:
   1. converter loss and current capacity;
   2. crosstalk victims;
   3. return path;
   4. leakage and creepage;
   5. inventories and source-to-radiator;
   6. antenna feed;
   7. thermal.
3. Re-run the routed-physics baselines under the new copper connectivity.
4. Pilot the LLM pass on one board, measure its cost, then decide the subset size.

## Conflicts and open questions

- **Human copper as intent evidence** would bias place and joint tasks toward the human's choices.
- **No exchange rate across categories** without stated intent.
- **Edge-rate priors dominate crosstalk and EMI:** a 1–5 ns interval spans up to 14 dB above both spectral corners.
- **Stand-in fidelity** (ideal switches, current-held inductor) sets the ceiling for converter tests.

## Sources

- In-repo measurements: kaeres index, evaluator `c3e877f84ac4` (kae `dfe6260`, `physics_board.py` `cd4ab2e`), 2026-10-27; `kae.sim` runs, 2026-10-28.
- NXP UM10204, I2C-bus specification (rise-time limits, pin capacitance).

See also: [physics-critics](physics-critics.md), [physics-critics-catalog](physics-critics-catalog.md), [physics-ir](physics-ir.md), [comprehension](comprehension.md), [schematic-to-physics](schematic-to-physics.md), [fields-emi-budget](fields-emi-budget.md).
