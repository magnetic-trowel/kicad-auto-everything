# Functional evaluator: code architecture (`kae.sim`)

**TL;DR**
- **`kae.sim` judges a routed board by circuit simulation.** For every test in a testbench, ngspice runs:
  - the ideal circuit (each net one node);
  - the routed circuit (the test's nets replaced by their extracted copper);
  
  each at every corner of the test's parameter intervals. Out come verdicts, the layout's effect (routed minus ideal), capability, and questions for an LLM or a human.
- **Extraction (`extract.py`) turns copper into R, L, C, mutual L and coupling C,** built on the repo's closed forms (Hammerstad–Jensen L′ and C′, Grover/Neumann mutuals with plane images, patch coupling). There are two profiles: `signal` (line C, coupling, 0.5–5 mm sections) and `power` (long R–L sections, pour and via parasitics).
- **The simulator never sees a KiCad name.** `names.py` generates every node and element name, and the evaluator rejects anything it cannot resolve. A missing measurement is a failure, never a silent pass.
- **Built and tested:**
  - 8 modules, 19 unit tests (analytic R and L of a track, I × R drop end to end through ngspice, coupling sign, format round trip);
  - runs on two corpus boards (§7).
  
  No existing module, score or evaluator changed.

Semantics: [functional-evaluation](../physics/functional-evaluation.md). Format and its history: [intent-interchange](intent-interchange.md). Kernels and exactness classes: [physics-engine-design](physics-engine-design.md). Tags: [M] measured here, [I] design choice.

## Key facts

### 1. Modules

| Module | Role |
|---|---|
| [`testbench.py`](../../../kae/src/kae/sim/testbench.py) | the testbench format: parse (errors carry line numbers), render, SPICE numbers |
| [`autotb.py`](../../../kae/src/kae/sim/autotb.py) | a default testbench from the board and its brief, no LLM: rail DC drop and load step, I2C, buck switch node, differential-pair delay and skew |
| [`design.py`](../../../kae/src/kae/sim/design.py) | the board's passives as elements: values from the value field, ESR and ESL by package (E5), ferrites as R + L |
| [`schematic.py`](../../../kae/src/kae/sim/schematic.py) | values and fields from a KiCad 6+ schematic through `kicad-cli sch export netlist` |
| [`extract.py`](../../../kae/src/kae/sim/extract.py) | copper → Network of R, L, C, K between node keys; copper islands per net |
| [`names.py`](../../../kae/src/kae/sim/names.py) | safe, case-proof, dot-free simulator names, kept both ways |
| [`ngspice.py`](../../../kae/src/kae/sim/ngspice.py) | batch runs (PATH or the KiCad container); reads `.meas`; keeps warnings and errors |
| [`evaluate.py`](../../../kae/src/kae/sim/evaluate.py) | decks per test, mode and corner; parallel runs; verdicts, capability, questions |
| [`cli.py`](../../../kae/src/kae/sim/cli.py) | `testbench`, `evaluate`, `questions` |

### 2. Data flow

```
board.kicad_pcb ─┬─ load (+ pintypes.json, + schematic values when the footprints carry none)
                 ├─ brief (kae.circuit.brief: roles, rails and sources, structures, diff pairs)
                 ├─ design (passives)                         ┌─ ideal deck  ─┐
testbench.tb.cir ┴─ tests ─▶ per test × corner ───────────────┤               ├─▶ ngspice ─▶ .meas
                             (RoutedBoard + kicad-cli fills) ─┴─ routed deck ─┘
                                                  └─ extract(nets of the test, profile)
  ─▶ verdicts (ideal, routed), layout effect, capability, incomplete/unknown/error ─▶ eval.json ─▶ questions
```

### 3. Extraction

**Per piece of copper:**

| Piece | Model |
|---|---|
| Track of length l, width w, at height h over the nearest plane layer of any net | R = ρl/(wt); L = L′(w, h)·l; C = C′(w, h, ε_r)·l split to both ends. Split into sections of at most `lmax`, so delay √(LC) and impedance √(L/C) follow the line |
| Via | barrel R and partial self-L between the layers it joins |
| Pour of a non-ground net | the copper graph's pour links (2 mm strips) for R and L; plate capacitance εA/h over its contacts (coarse) |
| Ground net | its pours are the reference node; tracks and vias between pads and pours are extracted |
| Neighbours (signal profile) | same-layer pieces of different nets within 1 mm: mutual L with plane images (K, clamped at ±0.9) and coupling C from patch potential coefficients |

**Profiles:**

| Profile | Sections | Short pieces (< lmin) | Line C | Coupling | Used by |
|---|---|---|---|---|---|
| `signal` | ≤ 5 mm | R only (L and C to the ends), lmin 0.5 mm | yes | yes | I2C, pairs |
| `power` | ≤ 20 mm | none | no (0.1 pF/mm against µF of decoupling) | no | rails, converters |

**Reduction and robustness:**
- **Micrometre pieces:** the copper graph splits tracks at junctions into pieces micrometres long. As full sections they put femtofarads behind micro-ohms and the matrix goes near-singular: ngspice reported "timestep too small" at 2 ps [M]. Short pieces keep their resistance and drop only their negligible inductance. All R are at least 0.1 mΩ.
- **Connectivity:** the copper graph ([`kae.route.copper`](../../../kae/src/kae/route/copper.py)) connects items as KiCad does: shapes that collide on a shared layer, with round-ended tracks, jumper pad groups, net-carrying copper shapes and pours that are one conductor each. On 150 human boards it splits 5 nets that KiCad reports connected, where the earlier graph split 353 [M]. Custom pad primitives are still modelled as the pad's rectangle.
- **Copper islands:** each test's pins are checked against the copper islands before simulating. A split test is reported as `incomplete`, with the stranded pins listed, and its routed runs are skipped. A load on an island has no return but the 10¹² Ω leak, and the solver would chase 10¹¹ V.

**Limits:** ideal plane under each piece (slots and splits are for geometric checks); power planes as AC ground for line C; no broadside coupling across layers; no pad copper or thermal spokes; no skin effect; coarse pours.

### 4. Decks

- **Ideal deck:** every pin of a net on one node; ground nets are node 0.
- **Routed deck:** each pin of an extracted net is its own node, joined by the extracted copper.
- **Board passives** enter a test only when every terminal is on one of the test's nets, on ground, or on a net the testbench names. A capacitor into an undriven net would leave its ESL feeding a node that nothing holds.
- **Guards** [M]:
  - KiCad names → generated names;
  - `<…>` tokens that resolve to nothing are an error;
  - `v(a,b)` becomes a B-source probe, because batch `.meas` cannot read it;
  - `.option rshunt=1e12 method=gear`;
  - every requested `.meas` must come back.

### 5. Verdicts

- **Per requirement, per mode:**
  - pass: it holds at every corner;
  - fail: it holds at none;
  - marginal: otherwise.
- **Test status:** `unknown` (the testbench says what is missing), `incomplete` (copper islands), `error` (a measurement did not return), else the worst requirement.
- **Capability:**
  - `rail_dc`: the load multiple at which the first pin reaches its bound, from the line through the low and high corners (DC with current loads is linear);
  - `i2c`: the fastest mode whose limit holds, or, with the pull-up off board, the bus capacitance and the largest pull-up per mode;
  - `pair`: delay and skew.
- **`questions`** ranks:
  1. marginal verdicts and their prior inputs;
  2. unknowns;
  3. verdicts resting on priors alone.

### 6. Command line

```
python -m kae.sim.cli testbench BOARD.kicad_pcb [--pintypes F] [--schematic ROOT.kicad_sch] -o board.tb.cir
python -m kae.sim.cli evaluate  BOARD.kicad_pcb --testbench board.tb.cir [--pintypes F] [--schematic ROOT]
                                [--input TASK_INPUT.kicad_pcb] [-j 8] [--only ID ...] --workdir DIR -o eval.json
python -m kae.sim.cli questions eval.json
```

`--input` builds the brief from the task's input board, so two layouts of one task share their tests.

### 7. Results [M]

- **`balazsbencs-ardor-ardor-io`** (Raspberry Pi HAT, 99 footprints, fully connected; values from its schematic):
  - 8 tests, 44 simulations, 6 s. Rails +5V_PI and +5V_A (derived through ferrite FB101) pass DC drop and load step.
  - Copper adds about 8 mV to the ferrite's 11 mV on +5V_A at the load prior, with capability 7.2× the prior before the first op-amp pin reaches 3%.
  - The I2C buses measure about 11.4 pF routed (9.9 pF from pins), which allows pull-ups up to about 31 kΩ in Fast-mode.
  - Four tests are unknown: I2C pull-ups off board, and +3V3_PI with no recognised load.
- **`azlan-works-argo-argo-v2`** (CM carrier, 80 footprints): the human board is unfinished.
  - KiCad reports 132 unconnected items, including GND, VBUS and the buck's switch node. The tests that touch them come back `incomplete`, with the stranded pins listed.
  - 50 tests, 199 simulations, 338 s.
  - 23 differential pairs report delay and skew: 75–260 ps routed against a 100 ps driver-and-load ideal. CRX1 has 30 ps of intra-pair skew, USB31_TX 6 ps.
  - Two pairs still time out, and one reports a singular matrix at a ground node.
- **LLM pilot on ardor** (one agent, 146k tokens, about 10 web lookups, 9 minutes). It replaced the priors with cited datasheet intervals and bounds:
  - ADS1115, OPA2320, TPA6132A2, Omron G5V-1, H11L1M;
  - the Raspberry Pi's 1.8 kΩ I2C pull-ups, which the schematic confirms with "Pi has them".
  
  Result: 4 pass / 4 unknown became 8 pass / 0 unknown. It found 8 errors in the automatic testbench:
  1. loads behind a ferrite on +3V3_PI missed;
  2. a relay's current returned at a contact pin instead of through its coil and driver;
  3. an IC's current returned at a grounded input instead of PGND;
  4. rail trees split into separate tests;
  5. the I2C bus stopped at a 33 Ω series resistor;
  6. resistor loads (pull-ups, dividers) ignored;
  7. audio-rate loads stepped in nanoseconds;
  8. two ideal sources on one rail make the ideal deck singular.

### 8. Next

1. ~~Fix the pilot's eight generator errors.~~ Done: supply trees through ferrites, fuses and small resistors (also finding supplies the brief did not name); an IC's current returns at its ground pin nearest the supply pin, other loads at the reference; only logic ICs step in ns; dividers simulated and pull-ups counted at V/R; I2C lines followed through series resistors; parallel ideal sources merged. On ardor the automatic testbench now judges the 3.3 V tree (it was unknown); only the off-board I2C pull-ups still need an outside fact.
2. Add crosstalk victim tests on routed copper, leakage and creepage, the excitation and radiator inventories with the source-to-radiator check, and the antenna feed. Fix the known limits:
   - add boost and half-bridge stand-ins;
   - find the cause of the slow and singular signal runs (scaling the couplings to keep the inductance matrix positive definite did not cure them).
3. Hook into kaeres as a new evaluator (the evaluator id hashes the code tree), beside the legacy `physics_total`. Report per category, never inside cp1, cpk or `score.py`.
4. Re-run the routed-physics baselines under the new connectivity (it changes the evaluator id); model custom pad primitives.
5. Before KiCad 11, port the SWIG `pcbnew` users (the fills, the board writer) to the IPC API.

## Conflicts and open questions

- **Stand-in fidelity:** the buck stand-in has ideal switches and an inductor held as a current source. It shows hot-loop ringing but not control behaviour. Vendor or Verilog-A models would replace it.
- **Coarse pours:** a sheet solver (the engine's K2 operator) would replace the 2 mm strip mesh.
- **Runtime:** most signal tests take about a second per corner, but a few large pairs reach the 300 s cap. Power tests take milliseconds to seconds.
- **LLM cost:** about 150k tokens per board for the questions-only pass. A per-part fact cache should lower it on later boards.

## Sources

- Code and tests: [`kae/src/kae/sim/`](../../../kae/src/kae/sim/), [`kae/tests/test_sim.py`](../../../kae/tests/test_sim.py).
- Reused: [`critical_recheck.py`](../../../kae/src/kae/route/critical_recheck.py) (RoutedBoard, fills), [`copper.py`](../../../kae/src/kae/route/copper.py) (NetGraph), [`kernels.py`](../../../kae/src/kae/physics/kernels.py), [`fastloop.py`](../../../kae/src/kae/physics/fastloop.py), [`priors.py`](../../../kae/src/kae/physics/priors.py), [`brief.py`](../../../kae/src/kae/circuit/brief.py).

See also: [functional-evaluation](../physics/functional-evaluation.md), [intent-interchange](intent-interchange.md), [physics-critics](../physics/physics-critics.md), [physics-engine-design](physics-engine-design.md).
