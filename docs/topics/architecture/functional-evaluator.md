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
| [`autotb.py`](../../../kae/src/kae/sim/autotb.py) | a default testbench from the board and its brief, no LLM: rail DC drop and load step, I2C, switching cells (buck, boost, half-bridge and motor-driver phases) and their hot loops, differential-pair delay and skew |
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
- **Dissipation:** a test that names `kae_pdiss` in its `.control` block gets a vector holding the power in every resistance the deck holds from the board: copper, resistors, capacitor ESR, inductor DCR. It is computed after the run, never as a probe node. Loss is summed from the dissipating elements, never from the sources' delivered power. That would also count energy still flowing into the bus capacitors while the off-board feed settles, which takes about 100 µs against a 12-period run, and it gave −3.5 W on a 1 W cell [M].

### 5. Verdicts

- **Per requirement, per mode:**
  - pass: it holds at every corner;
  - fail: it holds at none;
  - marginal: otherwise.
- **Test status:** `unknown` (the testbench says what is missing), `incomplete` (copper islands), `error` (a measurement did not return), else the worst requirement.
- **Capability:**
  - `rail_dc`: the load multiple at which the first pin reaches its bound, from the line through the low and high corners (DC with current loads is linear);
  - `i2c`: the fastest mode whose limit holds, or, with the pull-up off board, the bus capacitance and the largest pull-up per mode;
  - `pair`: delay and skew;
  - `cell`: the layout's power loss per corner, routed minus ideal dissipation, also as a share of the output;
  - `loop`: hot-loop inductance, routed and ideal, and their difference.
- **`questions`** ranks:
  1. marginal verdicts and their prior inputs;
  2. unknowns;
  3. verdicts resting on priors alone.

### 5a. Budgets (`kae.sim.budget`)

The placer and the critical router price every structure as spend over allocation, with the allocation taken from a closed form unless the brief's structure carries a `budget`. `kae.sim.cli budgets` derives that budget from the board's own testbench: for a cell, a series inductance is swept at the cell's loop insertion point (`Vloop`) on the ideal circuit, at every corner. The budget is the loop's ideal inductance plus the largest addition at which the requirement holds at every corner. Budgets are written to `board.budgets.json` and applied only by methods that opt in (`critical_cli route --budgets`). Evaluators never apply them, so a method's budgets cannot change its score.

A budget is applied only if all three hold; otherwise the closed-form allocation stays, and the file records every reason:
1. **The requirement comes from a trusted source:** human, board rule, datasheet, board value, schematic or standard. A budget derived from a prior bound is no better than the closed-form allocation, and on the boost below it was worse.
2. **It is achievable:** at least the loop inductance of the parts' own internal paths alone (`critical_recheck.cell_body_floor`, the router's model). No layout of those parts can go lower.
3. **It does not depend on the stand-in:** the sweep runs with a conservative stand-in (body-diode transit 20 ns, C_oss loss 0.05 Ω) and a lenient one (2 ns, 1 Ω). The budget is the conservative value, and is used only if the lenient one is within 3× of it.

On the two smoke boards, no budget passes [M]. Both bounds are priors.
- **Boost:** 1.16 nH, against a floor of 3.12 nH.
- **Motor driver:** 0.24 to 1.78 nH across the stand-ins, against a floor of 7.1 nH. Its prior, a ring that never reaches the rating at 50 ns edges and so is capped at 50 nH, ignores recovery altogether.

The boost's closed-form allocation, 2.08 nH, is itself below its floor: the router can never meet it there.

**Loop measures, cross-checked** [M]. On the boost's routed loop, the router's closed form gives 13.2 nH, and PEEC on the same pieces gives 13.1 nH. Without the parts' bodies it gives 9.4 nH of copper. The SPICE loop test, once it covers the whole commutation loop (switch-node copper included), gives 6.6 nH of copper plus 1.0 nH of capacitor ESL. An earlier loop test stopped at the switch pins and gave 2.7 nH; it was not the same loop, and comparing the two was wrong. The copper, drawn: the switch-node trace cuts IC1's ground pad off from C5's on F.Cu, so the return detours to a via 6.5 mm away, as the router models it. A B.Cu track slots the reference plane under the loop, which both fast models ignore. `tools/research/physics/pt_mesh_loop.py` is the reference. It is a nodal PEEC of all the copper in a window, with planes meshed and no plane assumed; it reads −2.4% against an image plane at 0.5 mm pitch.

| Copper-only loop, boost | nH | vs reference |
|---|---|---|
| Reference, F.Cu 0.25 mm, B.Cu 0.5 mm (0.35 / 0.7 mm: 10.96) | 10.59 | |
| Reference with B.Cu filled solid (0.35 / 0.7 mm) | 9.25 | the slot adds about 1.7 nH (+18%) |
| Router's closed form | 9.37 | −11%; within about 5% of the solid-plane reference |
| SPICE extraction, power profile | 6.57 | −38% |

So the router's loop model is the authority for loop inductance. Its error on this loop is the plane slot, which it cannot see. The SPICE extraction has no mutual inductance in the power profile and an ideal plane under each piece, so it must not judge loops (it stays for DC drop and loss, where it was checked). One loop is one data point: the next step is a sample of hot loops across the corpus, to put an error band on the closed form.

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
- **Switching cells** (stand-ins; no LLM, no schematic):
  - `acarpm-chesslab-powerboard`, an MT3608 boost from a 3.7 V cell to 5 V. Hot loop (D3, C5, IC1 ground): 2.7 nH routed against 1.0 nH for the capacitor alone. The cell dissipates 0.28 W ideal and 0.29 W routed. Conduction rises by 15 mW, while the edges lose less (5.1 against 9.8 nJ a period, because the loop's inductance slows the turn-on current). The switch node peaks at 8.5 V routed against 5.6 V ideal, so it is marginal on the prior bound, which needs the MT3608's switch rating to judge.
  - `aarondennis-mup-astro-cat-hardware-astro-cat`, a DRV88xx with four motor phases on 12 V, PWM prior 20 kHz. Hot loop 1.66 nH against 0.24 nH for four capacitors in parallel. Loss is 0.22 W ideal and 0.23 W routed, with conduction 0.206 W against I²·R_on = 0.200 W. Each phase rings to 26 V against 11.9 V ideal, an upper bound (see Stand-in fidelity).
  - Every corner of both boards converges. Each corner takes 1–3 minutes routed.
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
   - ~~add boost and half-bridge stand-ins~~ (done: generic cells and the hot-loop test); next flyback, buck-boost, charge pumps, LDO and load-switch dissipation, and creepage and clearance against working voltage;
   - find the cause of the slow and singular signal runs (scaling the couplings to keep the inductance matrix positive definite did not cure them).
3. Hook into kaeres as a new evaluator (the evaluator id hashes the code tree), beside the legacy `physics_total`. Report per category, never inside cp1, cpk or `score.py`.
4. Re-run the routed-physics baselines under the new connectivity (it changes the evaluator id); model custom pad primitives.
5. Before KiCad 11, port the SWIG `pcbnew` users (the fills, the board writer) to the IPC API.

## Conflicts and open questions

- **Stand-in fidelity:** the cell stand-in has log-linear switches (50 mΩ to 1 MΩ), body diodes (20 mΩ, 10 ns transit time), 100 pF across each switch, and the inductor or winding held as a constant current source. It gives the copper's share of loss and the hot-loop ring, but not control behaviour or ripple. The ring's peak is an upper bound, for three reasons: the SPICE diode recovers abruptly where body diodes recover softly; C_oss is linear and lossless; and copper and capacitor resistance stay at their DC values (no skin effect). The loop inductance does not depend on any of these. Vendor or Verilog-A models would replace the stand-in.
- **Numerics, checked by refinement** [M]: every change to how a cell is solved is checked against a finer reference, and one that alters the circuit's physics is not accepted.
  - **Integration:** the Gear method holds p_loss within 0.01% from a 0.25 ns step down to 2 ps. Trapezoidal moved the peak by up to 3.5×, which is numerical ringing, so it is not used.
  - **Step:** the step is the smaller of T_SW/20 and 0.25 ns, forced everywhere. That is within 0.2% of a 25 ps reference; leaving the step to error control read the peak 6% low.
  - **Loss:** loss is computed after the run, in a `.control` block, from the converged waveforms. As a B-source probe node, the v·i sum stalled solves that converge without it, because it carries the solver's sub-nA noise. An aborted run reports nothing, never a partial-waveform value.
  - **Diode resistance:** without its series resistance the diode is a bare exponential on a ring with Q ≈ 30, and Newton fails. Restored at 20 mΩ, every corner converges, and the result moves by under 1.5% between 5 and 20 mΩ.
  - **C_oss loss:** at 1 ns edges, four of the fixture's nine corners failed to converge with any solver setting, even `itl4=500`, and a 0 V link placed in the loop flipped the typical corner. The cell was at the edge of convergence: an ideal C_oss ringing with Q ≈ 30. Real C_oss charges through the switch's spreading resistance (its hysteresis loss), which is what damps measured switch-node rings to Q ≈ 3–10. With 0.05 Ω, the low end of 0.05–1 Ω, every corner converges. Loss moves under 0.5%, and the peak drops 0.2% (fixture), 0.2% (boost) and 1.5% (motor driver); at 1 Ω the motor driver's peak is 10% lower.
  - **Low frequencies:** the cell is simulated at max(F_SW, 300 kHz). With a constant winding current, a period's loss is conduction (read on the settled middles of the on and off intervals) plus edge energy `e_sw`, and `p_loss` = p_cond + e_sw·F_SW. Each ring decays in about 25 ns, against flats of at least 1 µs.
- **Frequency priors** when the part table has none: motor drivers 1–100 kHz (typical 20 kHz), discrete half-bridges 20–500 kHz, integrated converters 150 kHz–3 MHz. A single 0.3–3 MHz prior had put motor drivers at converter frequencies, where a 100 ns edge and its dead time left a negative on-time, and the switch never turned on.
- **Coarse pours:** a sheet solver (the engine's K2 operator) would replace the 2 mm strip mesh.
- **Runtime:** most signal tests take about a second per corner, but a few large pairs reach the 300 s cap. Power tests take milliseconds to seconds.
- **LLM cost:** about 150k tokens per board for the questions-only pass. A per-part fact cache should lower it on later boards.

## Sources

- Code and tests: [`kae/src/kae/sim/`](../../../kae/src/kae/sim/), [`kae/tests/test_sim.py`](../../../kae/tests/test_sim.py).
- Reused: [`critical_recheck.py`](../../../kae/src/kae/route/critical_recheck.py) (RoutedBoard, fills), [`copper.py`](../../../kae/src/kae/route/copper.py) (NetGraph), [`kernels.py`](../../../kae/src/kae/physics/kernels.py), [`fastloop.py`](../../../kae/src/kae/physics/fastloop.py), [`priors.py`](../../../kae/src/kae/physics/priors.py), [`brief.py`](../../../kae/src/kae/circuit/brief.py).

See also: [functional-evaluation](../physics/functional-evaluation.md), [intent-interchange](intent-interchange.md), [physics-critics](../physics/physics-critics.md), [physics-engine-design](physics-engine-design.md).
